"""TEC-1 — teste isolado da Biblioteca da Seita (SEM DB).

Roda: python -X utf8 scripts/_test_tec1_library.py

Padrão _test_mv7_professions: ExplodingSession prova OFF = zero queries em
TODA função pública do engine; FakeSession (dispatch por substring do SQL
compilado) prova a lógica ON; seeds 27/27 (estrutura + régua + sect_key +
unicidade + i18n ×3); débito = SALDO nunca earned; leave locka tier 3 sem
apagar; equip-gate; wiring grep-provável (lição "flag sem call-site").
"""
from __future__ import annotations

import asyncio
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import core.sect_library_engine as lib  # noqa: E402
from database.models import PlayerSectTechnique, PlayerTechnique  # noqa: E402

PASS = 0
FAILS: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


# ── Fakes ────────────────────────────────────────────────────────────────────
class ExplodingSession:
    """Qualquer toque no DB explode — prova OFF = zero queries."""

    def __getattr__(self, name):
        if name == "rollback":
            async def _noop():
                return None
            return _noop

        def _boom(*a, **k):
            raise AssertionError(f"query executada com flag OFF ({name})")
        return _boom


class FakeResult:
    def __init__(self, rows):
        self._rows = rows if isinstance(rows, list) else [rows]

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)

    def scalar(self):
        r = self.first()
        return r[0] if isinstance(r, (tuple, list)) else r

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return list(rows)
        return _S()


class FakeSession:
    """Dispatch por substring do SQL compilado (padrão MV-7)."""

    def __init__(self, handlers):
        self.handlers = handlers  # list[(predicate(sql, params), rows_or_fn)]
        self.added: list = []
        self.committed = False

    async def execute(self, stmt, params=None):
        try:
            sql = str(stmt)
        except Exception:
            sql = repr(stmt)
        try:
            p = dict(stmt.compile().params) if hasattr(stmt, "compile") else dict(params or {})
        except Exception:
            p = dict(params or {})
        if params:
            p.update(params)
        for pred, rows in self.handlers:
            if pred(sql, p):
                return FakeResult(rows(p) if callable(rows) else rows)
        raise AssertionError("query inesperada: " + sql[:180].replace("\n", " "))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None

    def begin_nested(self):
        """SAVEPOINT fake (o F9 do review envolve o lock-on-leave num nested)."""
        class _SP:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False
        return _SP()


def T(**kw):
    """Fake TechniqueCatalog row."""
    d = dict(id=0, name="X", emoji="⚔️", effect_type="damage_mult", effect_value=0.2,
             effect_round=0, req_realm=1, qi_cost=20, tech_type="combat",
             description="d", sect_key=None, library_tier=None, library_cp_cost=None)
    d.update(kw)
    return types.SimpleNamespace(**d)


def P(**kw):
    d = dict(telegram_id=111, sect_id="azure_cloud", sect_rank="core",
             sect_contribution=5000, sect_contribution_earned=9000, realm=5,
             language="pt", spirit_stones=0,
             # TEC-3: colunas que get_library_shelves passou a ler.
             karma=0, scroll_econ=None, current_hp=100)
    d.update(kw)
    return types.SimpleNamespace(**d)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


NOTIFY_CALLS: list = []
CHRON_CALLS: list = []


def main() -> None:  # noqa: C901
    import core.notification_engine as ne
    import core.world_pulse_engine as wpe
    _orig_notify, _orig_chron = ne.notify, wpe.emit_chronicle

    async def _spy_notify(session, pid, kind, **kw):
        NOTIFY_CALLS.append((pid, kind, kw.get("title_key"), kw.get("target_tab")))
        return None

    async def _spy_chron(session, **kw):
        CHRON_CALLS.append(kw)
        return None

    ne.notify = _spy_notify
    wpe.emit_chronicle = _spy_chron

    try:
        _run_blocks()
    finally:
        ne.notify, wpe.emit_chronicle = _orig_notify, _orig_chron

    print(f"\n{PASS} PASS · {len(FAILS)} FAIL")
    if FAILS:
        for f in FAILS:
            print(" ✗", f)
        sys.exit(1)
    print("All green — TEC-1 Biblioteca da Seita.")


def _run_blocks() -> None:  # noqa: C901
    # ══ 1. OFF-identity: toda função pública com ExplodingSession ══
    check("off.gate", lib.biblioteca_on() is False, "sem DB o gate fail-safe é False")
    es = ExplodingSession()
    r = run(lib.get_library_shelves(es, 1))
    check("off.shelves", r == {"on": False}, str(r))
    r = run(lib.learn_library_technique(es, 1, 550))
    check("off.learn", r == {"ok": False, "reason": "lib_off"}, str(r))
    check("off.notify_open", run(lib.notify_library_opened(es, 1, "azure_cloud")) is None)
    check("off.notify_shelf", run(lib.notify_shelf_unlocked(es, 1, "inner")) is None)
    r = run(lib.lock_core_arts_on_leave(es, 1, "azure_cloud"))
    check("off.lock_leave", r == {"locked": []}, str(r))
    check("off.count", run(lib.count_learnable_now(es, 1)) == 0)
    check("off.no_notify_spy", not NOTIFY_CALLS and not CHRON_CALLS)

    # ══ 2. Puras ══
    check("pure.cp1", lib.tier_default_cp(1) == 0)
    check("pure.cp2", lib.tier_default_cp(2) == lib.LIB_T2_CP == 750)
    check("pure.cp3", lib.tier_default_cp(3) == lib.LIB_T3_CP == 3000)
    check("pure.cost_col", lib.tier_cp_cost(T(library_tier=3, library_cp_cost=1234)) == 1234)
    check("pure.cost_fallback", lib.tier_cp_cost(T(library_tier=2)) == 750)
    check("pure.ranks", lib.TIER_MIN_RANK == {1: "disciple", 2: "inner", 3: "core",
                                              4: "elder", 5: "heir", 6: "heir"},
          "TEC-3 acrescentou elder/heir e o TEC-5 o Cofre (6, tambem heir — heir e o "
          "topo de SECT_RANKS). O mapa e estatico; quem gateia e library_tiers()")
    check("pure.tiers_off", lib.library_tiers() == (1, 2, 3),
          "estantes_seladas OFF => so as 3 estantes-base (Lei 5)")
    p = P(sect_id="azure_cloud")
    check("pure.lock_other", lib.is_library_locked(T(library_tier=3, sect_key="iron_mountain"), p) is True)
    check("pure.lock_same", lib.is_library_locked(T(library_tier=3, sect_key="azure_cloud"), p) is False)
    check("pure.lock_t2", lib.is_library_locked(T(library_tier=2, sect_key="iron_mountain"), p) is False)
    check("pure.lock_legacy", lib.is_library_locked(T(library_tier=None, sect_key="iron_mountain"), p) is False)
    check("pure.lock_nosect", lib.is_library_locked(T(library_tier=3, sect_key="iron_mountain"), P(sect_id=None)) is True,
          "sem seita = lockada")

    # ══ 3. ON — força a flag e monta a FakeSession ══
    _orig_on = lib.biblioteca_on
    lib.biblioteca_on = lambda *a, **k: True
    try:
        _on_blocks()
    finally:
        lib.biblioteca_on = _orig_on

    # ══ 6. Seeds 27/27 (estrutura + régua + unicidade + i18n ×3) ══
    from database.seeds.combat_seeds import SECT_LIBRARY_TEC1, TECHNIQUES
    from core.world_sects_engine import SECT_LIBRARY, WORLD_SECT_KEYS
    check("seed.count", len(SECT_LIBRARY_TEC1) == 27, str(len(SECT_LIBRARY_TEC1)))
    ids = [t["id"] for t in SECT_LIBRARY_TEC1]
    check("seed.ids", ids == list(range(550, 577)), "ids contíguos 550-576")
    per_house: dict = {}
    for t in SECT_LIBRARY_TEC1:
        per_house.setdefault(t["sect_key"], []).append(t["library_tier"])
    check("seed.houses", set(per_house) == set(WORLD_SECT_KEYS))
    check("seed.tiers", all(sorted(v) == [1, 2, 3] for v in per_house.values()))
    BUDGET = {
        1: {"qi": 18, "realm": 1, "damage_mult": (0.14, 0.18), "damage_reduce": (0.14, 0.18),
            "evasion": (0.13, 0.15), "armor_ignore": (0.20, 0.22)},
        2: {"qi": 30, "realm": 2, "damage_mult": (0.26, 0.30), "damage_reduce": (0.24, 0.28),
            "evasion": (0.20, 0.22), "armor_ignore": (0.27, 0.30)},
        3: {"qi": 44, "realm": 4, "damage_mult": (0.38, 0.42), "damage_reduce": (0.33, 0.36),
            "evasion": (0.24, 0.26), "armor_ignore": (0.36, 0.40)},
    }
    for t in SECT_LIBRARY_TEC1:
        b = BUDGET[t["library_tier"]]
        ok_stats = t["qi_cost"] == b["qi"] and t["req_realm"] == b["realm"]
        if t["library_tier"] == 3 and t["effect_round"] > 0:
            ok_val = t["effect_type"] == "damage_mult" and 0.80 <= t["effect_value"] <= 0.90 \
                and 2 <= t["effect_round"] <= 4
        else:
            lo, hi = b.get(t["effect_type"], (None, None))
            ok_val = lo is not None and lo <= t["effect_value"] <= hi and t["effect_round"] == 0
        check(f"seed.{t['id']}.regua", ok_stats and ok_val,
              f"{t['effect_type']}={t['effect_value']} qi={t['qi_cost']} r={t['req_realm']} rd={t['effect_round']}")
        check(f"seed.{t['id']}.cp", t["library_cp_cost"] == lib.tier_default_cp(t["library_tier"]))
        check(f"seed.{t['id']}.combat", t["tech_type"] == "combat" and t["sect_key"] in WORLD_SECT_KEYS)
    names = [t["name"] for t in TECHNIQUES]
    check("seed.unique_names", len(names) == len(set(names)), "coluna name é UNIQUE")
    check("seed.in_techniques", all(t in TECHNIQUES for t in SECT_LIBRARY_TEC1),
          "as 27 entram na lista que o runner semeia")
    legacy_ids = {e["tech_id"] for v in SECT_LIBRARY.values() for e in v}
    check("seed.no_id_clash", not (set(ids) & legacy_ids), "sem colisão com 500-544")

    # i18n ×3 — todas as 27 têm tech_<id>_name/_desc nas 3 línguas (chat).
    import json
    for lang in ("pt", "en", "es"):
        data = json.load(open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8"))
        missing = [i for i in ids if f"tech_{i}_name" not in data or f"tech_{i}_desc" not in data]
        check(f"i18n.content.{lang}", not missing, str(missing[:5]))
    # números da desc PT batem com effect_value (anti drift de conteúdo)
    data_pt = json.load(open(os.path.join(ROOT, "locales", "pt.json"), encoding="utf-8"))
    import re as _re
    for t in SECT_LIBRARY_TEC1:
        pct = int(round(t["effect_value"] * 100))
        desc = data_pt.get(f"tech_{t['id']}_desc", "")
        check(f"i18n.{t['id']}.pct", str(pct) in _re.sub(r"[^0-9 ]", " ", desc),
              f"{pct}% não citado na desc pt")

    # ══ 7. Wiring grep-provável (flag sem call-site = promessa vazia) ══
    def _src(*parts):
        return open(os.path.join(ROOT, *parts), encoding="utf-8").read()

    check("wire.flag", '"biblioteca_seitas":' in _src("database", "db.py"))
    check("wire.mig", os.path.exists(os.path.join(ROOT, "migrations", "136_sect_library.sql")))
    wse = _src("core", "world_sects_engine.py")
    check("wire.join_hook", "notify_library_opened" in wse)
    check("wire.promo_hook", "notify_shelf_unlocked" in wse)
    check("wire.leave_hook", "lock_core_arts_on_leave" in wse)
    check("wire.equip_chat", "is_library_locked" in _src("handlers", "combat.py"))
    ws = _src("core", "webserver.py")
    check("wire.equip_api", ws.count("is_library_locked") >= 1)
    check("wire.endpoints", "world/sect_library" in ws and "world/sect_library_learn" in ws)
    check("wire.lib_locked_key", '"lib_locked"' in ws or "entry[\"lib_locked\"]" in ws)
    mn = _src("main.py")
    check("wire.lib_prefix", 'startswith("lib_")' in mn and "library_button_router" in mn)
    check("wire.cmd", '"biblioteca"' in mn)
    tj = _src("miniapp", "components", "tabs.js")
    check("wire.mini_fetch", 'useApi("world/sect_library"' in tj)
    check("wire.mini_learn", '"world/sect_library_learn"' in tj)
    check("wire.mini_lock", "lib_locked" in tj and "lib_mini_locked_row" in tj)
    check("wire.prof_xp_mini", "prf_mini_xp_gain" in tj)
    check("wire.prof_xp_chat", "prf_xp_gain_line" in _src("handlers", "alchemy.py")
          and "prf_xp_gain_line" in _src("handlers", "artifacts.py"))


def _on_blocks() -> None:  # noqa: C901
    from core.world_sects_engine import SECT_LIBRARY

    AZ = SECT_LIBRARY["azure_cloud"]
    legacy_rows = [T(id=e["tech_id"], name=f"L{e['tech_id']}", sect_key="azure_cloud")
                   for e in AZ]
    new_rows = [
        T(id=550, name="N550", sect_key="azure_cloud", library_tier=1, library_cp_cost=0,
          req_realm=1),
        T(id=551, name="N551", sect_key="azure_cloud", library_tier=2, library_cp_cost=750,
          req_realm=2),
        T(id=552, name="N552", sect_key="azure_cloud", library_tier=3, library_cp_cost=3000,
          req_realm=4),
    ]

    def _mk_session(*, player=None, learned=(), quest_done=True, equipped=(),
                    catalog_extra=(), pst_rows=()):
        pl = player or P()

        def h(pred, rows):
            return (pred, rows)

        def catalog_rows(params):
            allr = legacy_rows + new_rows + list(catalog_extra)
            # Os params IN compilam como UMA key com valor-lista
            # (ex.: {"id_1": [500, 501]}) — achata antes de filtrar.
            ids: list = []
            for k, v in params.items():
                if k.startswith("id_") or k.startswith("pk_"):
                    if isinstance(v, (list, tuple, set)):
                        ids.extend(v)
                    else:
                        ids.append(v)
            if ids:
                return [r for r in allr if r.id in ids]
            if any(k.startswith("sect_key") for k in params):
                want = next(v for k, v in params.items() if k.startswith("sect_key"))
                # Le a UMA verdade (nao espelhar a tupla a mao: com o TEC-3 a
                # resposta passou a depender da flag).
                return [r for r in allr if r.sect_key == want
                        and r.library_tier in lib.library_tiers()]
            return allr

        return FakeSession([
            h(lambda s, p: "pg_advisory_xact_lock" in s, [None]),
            h(lambda s, p: "player_sect_techniques" in s, list(pst_rows)),
            h(lambda s, p: "quests_catalog" in s, [(1,)] if quest_done else []),
            h(lambda s, p: "is_active_combat" in s and "player_techniques" in s
              and "techniques_catalog" in s, list(equipped)),
            h(lambda s, p: "player_techniques" in s and "technique_id" in s
              and "techniques_catalog" not in s, list(learned)),
            h(lambda s, p: "FROM techniques_catalog" in s, catalog_rows),
            h(lambda s, p: "FROM players" in s and "FOR UPDATE" in s, [pl]),
            h(lambda s, p: "players.sect_id" in s,
              [(pl.sect_id, pl.sect_rank, pl.sect_contribution, pl.realm,
                pl.sect_contribution_earned, pl.karma, pl.scroll_econ,
                # TEC-5 — a view passou a ler path + o Mar de Longevidade
                # (o Cofre é path-gated e a vitrine diz os anos por uso).
                getattr(pl, "path", None), getattr(pl, "age_years", 0),
                getattr(pl, "lifespan_bonus_years", 0))]),
            h(lambda s, p: "FROM players" in s, [pl]),
        ]), pl

    # ── shelves view ──
    s, pl = _mk_session(learned=[500], quest_done=False)
    view = asyncio.get_event_loop().run_until_complete(lib.get_library_shelves(s, 111))
    check("on.view.on", view.get("on") is True and view.get("in_sect") is True)
    check("on.view.shelves", [sh["tier"] for sh in view["shelves"]] == [1, 2, 3])
    check("on.view.sealed", [x["key"] for x in view["sealed"]] == ["signature", "hidden"])
    sh1 = view["shelves"][0]
    check("on.view.sh1", len(sh1["arts"]) == 2 and sh1["arts"][0]["legacy"] is True
          and sh1["arts"][1]["legacy"] is False, "estante = legada + nova")
    check("on.view.learned", sh1["arts"][0]["learned"] is True, "500 aprendida")
    a550 = sh1["arts"][1]
    check("on.view.t1_free", a550["cost"] == 0 and a550["can_learn"] is True)
    a552 = view["shelves"][2]["arts"][1]
    check("on.view.quest_block", a552["block"] == "quest" and a552["can_learn"] is False,
          "Núcleo sem quest da casa = block quest (rank/realm ok)")
    check("on.view.quest_done_flag", view["quest_done"] is False)
    # com quest feita mas saldo curto → block cp
    s, pl = _mk_session(player=P(sect_contribution=100), quest_done=True)
    view = asyncio.get_event_loop().run_until_complete(lib.get_library_shelves(s, 111))
    a552 = view["shelves"][2]["arts"][1]
    check("on.view.cp_block", a552["block"] == "cp", str(a552["block"]))
    # posto baixo → block rank (antes de tudo)
    s, pl = _mk_session(player=P(sect_rank="disciple", realm=5), quest_done=True)
    view = asyncio.get_event_loop().run_until_complete(lib.get_library_shelves(s, 111))
    a551 = view["shelves"][1]["arts"][1]
    check("on.view.rank_block", a551["block"] == "rank" and view["shelves"][1]["rank_ok"] is False)
    # não-membro → disclosure
    s, pl = _mk_session(player=P(sect_id=None))
    view = asyncio.get_event_loop().run_until_complete(lib.get_library_shelves(s, 111))
    check("on.view.no_sect", view == {"on": True, "in_sect": False})

    # ── learn: débito SALDO nunca earned + registro + chronicle no tier 3 ──
    CHRON_CALLS.clear()
    pl = P(sect_contribution=5000, sect_contribution_earned=9000)
    s, _ = _mk_session(player=pl, learned=[], quest_done=True, equipped=[])
    res = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 552))
    check("on.learn.ok", res.get("ok") is True, str(res))
    check("on.learn.debit", pl.sect_contribution == 2000 and res["cp_spent"] == 3000)
    check("on.learn.earned_intocado", pl.sect_contribution_earned == 9000,
          "escada de rank NUNCA recua")
    added_pt = [x for x in s.added if isinstance(x, PlayerTechnique)]
    added_pst = [x for x in s.added if isinstance(x, PlayerSectTechnique)]
    check("on.learn.rows", len(added_pt) == 1 and len(added_pst) == 1)
    check("on.learn.registro", added_pst[0].sect_key == "azure_cloud"
          and added_pst[0].cp_paid == 3000)
    check("on.learn.autoequip", added_pt[0].is_active_combat is True
          and res["auto_equipped"] is True)
    check("on.learn.loadout", res["loadout_before"] == [] and len(res["loadout_after"]) == 1)
    check("on.learn.chronicle", len(CHRON_CALLS) == 1
          and CHRON_CALLS[0].get("event_type") == "lib_first")
    # 2º T3 do servidor (probe acha outro) → sem chronicle
    CHRON_CALLS.clear()
    pl = P(sect_contribution=5000)
    s, _ = _mk_session(player=pl, quest_done=True, pst_rows=[(999,)])
    res = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 552))
    check("on.learn.chron_once", res.get("ok") is True and not CHRON_CALLS)
    # T1 grátis: zero débito
    pl = P(sect_contribution=77)
    s, _ = _mk_session(player=pl, quest_done=False)
    res = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 550))
    check("on.learn.t1_free", res.get("ok") is True and pl.sect_contribution == 77
          and res["cp_spent"] == 0, str(res))
    # recusas em ordem
    s, _ = _mk_session(player=P(sect_id=None))
    r = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 550))
    check("on.learn.not_in_sect", r["reason"] == "not_in_sect")
    s, _ = _mk_session()
    r = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 500))
    check("on.learn.legacy_refused", r["reason"] == "tech_not_in_library",
          "legada aprende pelo caminho v16.4c")
    s, _ = _mk_session(player=P(sect_id="iron_mountain"))
    r = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 550))
    check("on.learn.wrong_house", r["reason"] in ("wrong_house", "tech_not_in_library"))
    s, _ = _mk_session(player=P(sect_rank="disciple"))
    r = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 551))
    check("on.learn.rank_low", r["reason"] == "rank_too_low")
    s, _ = _mk_session(player=P(realm=1))
    r = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 552))
    check("on.learn.realm_low", r["reason"] == "realm_too_low")
    s, _ = _mk_session(learned=[types.SimpleNamespace(technique_id=551)])
    r = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 551))
    check("on.learn.already", r["reason"] == "already_learned", str(r))
    s, _ = _mk_session(quest_done=False)
    r = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 552))
    check("on.learn.quest_gate", r["reason"] == "quest_required")
    s, _ = _mk_session(player=P(sect_contribution=100), quest_done=True)
    r = asyncio.get_event_loop().run_until_complete(lib.learn_library_technique(s, 111, 552))
    check("on.learn.cp_gate", r["reason"] == "insufficient_merit"
          and r["cost"] == 3000 and r["balance"] == 100)

    # ── leave lock: desequipa SÓ tier 3 da casa; devolve nomes ──
    eq_rows = [
        (types.SimpleNamespace(is_active_combat=True), "N552", "☁️"),
    ]
    s = FakeSession([
        (lambda sql, p: "player_techniques" in sql and "techniques_catalog" in sql, eq_rows),
    ])
    r = asyncio.get_event_loop().run_until_complete(
        lib.lock_core_arts_on_leave(s, 111, "azure_cloud"))
    check("on.leave.locked", [x["name"] for x in r["locked"]] == ["N552"])
    check("on.leave.unequipped", eq_rows[0][0].is_active_combat is False)

    # ── notifs gated (spies) ──
    NOTIFY_CALLS.clear()
    s = FakeSession([])
    asyncio.get_event_loop().run_until_complete(lib.notify_library_opened(s, 111, "azure_cloud"))
    check("on.notify.open", NOTIFY_CALLS and NOTIFY_CALLS[-1][2] == "notif_lib_open_title"
          and NOTIFY_CALLS[-1][3] == "profile")
    NOTIFY_CALLS.clear()
    asyncio.get_event_loop().run_until_complete(lib.notify_shelf_unlocked(s, 111, "inner"))
    check("on.notify.shelf", NOTIFY_CALLS and NOTIFY_CALLS[-1][2] == "notif_lib_shelf_title")
    NOTIFY_CALLS.clear()
    asyncio.get_event_loop().run_until_complete(lib.notify_shelf_unlocked(s, 111, "elder"))
    check("on.notify.elder_silent", not NOTIFY_CALLS, "elder/heir não abre estante real (TEC-2)")


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
