"""TEC-4 — teste isolado das Grutas do Legado 传承洞 (SEM DB).

Roda: python -X utf8 scripts/_test_tec4_caves.py

Padrão _test_tec3_selado: ExplodingSession prova OFF-identity (flag OFF = zero
queries em TODA função pública); FakeSession prova a lógica ON. Cobre as
armadilhas que o recon de 2026-07-30 fixou:

  · a régua das 5 artes vem das SEEDS e o teto vivo POR effect_type é contado
    do catálogo (nunca do engine) — uma seed futura acima do teto FALHA alto;
  · `sect_key="legacy_*"` em TODAS as 5 (a ÚNICA exclusão dos pools) + os
    faucets vivos continuam filtrando `sect_key IS NULL` (grep-provado);
  · o spawn: 1 ativa no mundo · cooldown global · pity 7d força · drift 70/30
    (o mapa continente→casa cobre os 5, incl. Mòyǔ/Fēnghuǒ que nunca rolam
    seek_inheritance);
  · gates do start EM ORDEM disclosed + 1 tentativa por abertura + resume;
  · o settle: sempre-paga · arte por roll + pity no 3º clear · dupe = dobro,
    nunca re-grant;
  · wiring grep-provado nas 2 superfícies + dispatcher + hook do pulse;
  · i18n ×3 ×2 com placeholders idênticos.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import types
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# python-telegram-bot não está na máquina local (só no VPS) e o teste é SEM
# rede/DB por contrato — stub mínimo satisfaz o import (padrão _test_qol_feedback);
# nada de telegram é EXERCIDO por estes asserts.
if "telegram" not in sys.modules:
    _tg = types.ModuleType("telegram")
    _tg.Update = type("Update", (), {})
    _tg_err = types.ModuleType("telegram.error")

    class _TgErr(Exception):
        retry_after = 0
    _tg_err.RetryAfter = _TgErr
    _tg_err.TimedOut = _TgErr
    _tg_err.NetworkError = _TgErr
    _tg.error = _tg_err
    sys.modules["telegram"] = _tg
    sys.modules["telegram.error"] = _tg_err

import core.legacy_cave_engine as lgc  # noqa: E402

PASS = 0
FAILS: list[str] = []
# Ancorado no relógio REAL de propósito: `_active_cave` filtra a gruta por
# `expires_at > _utcnow()`, então uma data fixa faz o teste expirar sozinho
# (aconteceu: fixture de 2026-07-30 + TTL 72h ⇒ vermelho a partir de 02/08,
# sem ninguém tocar no código). Toda a aritmética abaixo é relativa a NOW.
NOW = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


def _read(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


# ── Fakes (espelho do harness TEC-3) ─────────────────────────────────────────
class ExplodingSession:
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

    def scalar(self):
        r = self._rows[0] if self._rows else None
        return r[0] if isinstance(r, tuple) else r

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return list(rows)
        return _S()


class FakeSession:
    def __init__(self, handlers):
        self.handlers = handlers
        self.added: list = []
        self.flushed = 0

    async def execute(self, stmt, params=None):
        try:
            sql = str(stmt)
        except Exception:
            sql = repr(stmt)
        p = dict(params or {})
        for pred, rows in self.handlers:
            if pred(sql, p):
                return FakeResult(rows(p) if callable(rows) else rows)
        raise AssertionError("query inesperada: " + sql[:220].replace("\n", " "))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed += 1


def _rows_of(session, cls_name: str) -> list:
    return [o for o in session.added if type(o).__name__ == cls_name]


class ScriptedRng:
    """random() devolve a lista na ordem; choice devolve o alvo scriptado."""
    def __init__(self, randoms, choice=None):
        self._r = list(randoms)
        self._choice = choice

    def random(self):
        return self._r.pop(0) if self._r else 0.99

    def choice(self, seq):
        return self._choice if self._choice is not None else seq[0]


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _on(v: bool):
    lgc.legacy_caves_on = (lambda world_key=None: v)


_ORIG_ON = lgc.legacy_caves_on


async def main() -> None:
    # ═══ 1. OFF-identity — ExplodingSession em TODA função pública ═══
    _on(False)
    exp = ExplodingSession()
    r = await lgc.maybe_open_cave(exp, sect_id="azure_cloud", continent_key="linghe")
    check("off.maybe_open", r is None)
    r = await lgc.active_cave_view(exp, "pt")
    check("off.view", r is None)
    r = await lgc.start_cave_run(exp, 1)
    check("off.start", r == {"ok": False, "reason": "lgc_off"})
    # fail-safe real: sem monkeypatch, feature_enabled_for_world sem DB → False
    lgc.legacy_caves_on = _ORIG_ON
    check("off.failsafe", lgc.legacy_caves_on() is False)

    # ═══ 2. Registry — os 5 continentes cobertos (o fato do drift) ═══
    from core.continent_engine import CONTINENT_KEYS
    check("reg.continents", set(lgc.CONTINENT_TO_NPC.keys()) == set(CONTINENT_KEYS),
          str(lgc.CONTINENT_TO_NPC))
    check("reg.tech_ids", {h["tech_id"] for h in lgc.CAVE_HOUSES.values()} == set(range(600, 605)))
    check("reg.pve_source_len", len(lgc.CAVE_PVE_SOURCE) <= 24)
    check("reg.moyu_xueye", lgc.CONTINENT_TO_NPC.get("moyu") == "xueye")
    check("reg.fenghuo_wuming", lgc.CONTINENT_TO_NPC.get("fenghuo") == "wuming")
    for k, h in lgc.CAVE_HOUSES.items():
        check(f"reg.sectkey_len.{k}", len(f"legacy_{k}") <= 32)
        check(f"reg.npc_realm.{k}", 7 <= int(h["npc_realm"]) <= 8)

    # ═══ 3. A régua das SEEDS (teto vivo POR effect_type, contado do catálogo) ═══
    from database.seeds.combat_seeds import (
        INTENT_AFFINITIES,
        LEGACY_CAVE_TECHS,
        QI_COSTS,
        TECHNIQUES,
    )
    legacy_ids = {t["id"] for t in LEGACY_CAVE_TECHS}
    check("seed.ids", legacy_ids == set(range(600, 605)))
    all_ids = [t["id"] for t in TECHNIQUES]
    check("seed.no_dup_ids", len(all_ids) == len(set(all_ids)))
    caps: dict[str, float] = {}
    for t in TECHNIQUES:
        if t["id"] in legacy_ids:
            continue
        et, ev = t["effect_type"], float(t["effect_value"])
        caps[et] = max(caps.get(et, 0.0), ev)
    for t in LEGACY_CAVE_TECHS:
        tid = t["id"]
        check(f"seed.{tid}.sect_key", str(t.get("sect_key", "")).startswith("legacy_"), str(t.get("sect_key")))
        check(f"seed.{tid}.realm", t["req_realm"] == 7)
        check(f"seed.{tid}.qi", t["qi_cost"] == 68)
        check(f"seed.{tid}.round", t["effect_round"] == 0)
        check(f"seed.{tid}.not_dodge", t["effect_type"] != "dodge")
        check(f"seed.{tid}.in_band", float(t["effect_value"]) <= caps.get(t["effect_type"], 0.0),
              f"{t['effect_type']} {t['effect_value']} > teto vivo {caps.get(t['effect_type'])}")
        check(f"seed.{tid}.no_qi_override", tid not in QI_COSTS)
        check(f"seed.{tid}.no_intent_override", tid not in INTENT_AFFINITIES)
    engine_keys = {f"legacy_{k}" for k in lgc.CAVE_HOUSES}
    seed_keys = {t["sect_key"] for t in LEGACY_CAVE_TECHS}
    check("seed.keys_match_engine", engine_keys == seed_keys, f"{engine_keys} vs {seed_keys}")
    for k, h in lgc.CAVE_HOUSES.items():
        seed = next((t for t in LEGACY_CAVE_TECHS if t["id"] == h["tech_id"]), None)
        check(f"seed.house_tech.{k}", seed is not None and seed["sect_key"] == f"legacy_{k}")

    # ═══ 4. maybe_open_cave — guards em ordem ═══
    _on(True)

    def _mk_handlers(active_rows, count_active, last_row):
        return [
            (lambda s, p: "world_events" in s and "FOR UPDATE" in s, active_rows),
            (lambda s, p: "world_events" in s and "count" in s.lower(), [(count_active,)]),
            (lambda s, p: "world_events" in s and "ORDER BY" in s, [last_row] if last_row else []),
        ]

    # 4a. 1 ativa no mundo → None (nem chega no rng)
    ses = FakeSession(_mk_handlers([], 1, None))
    r = await lgc.maybe_open_cave(ses, sect_id="azure_cloud", continent_key="linghe",
                                  rng=ScriptedRng([0.0]), now=NOW)
    check("spawn.active_guard", r is None)
    check("spawn.active_guard_no_write", not ses.added)

    # 4b. cooldown global: última fechou há 1h → None
    last = Obj(state="expired", created_at=NOW - timedelta(hours=80),
               resolved_at=NOW - timedelta(hours=1), expires_at=NOW - timedelta(hours=1))
    ses = FakeSession(_mk_handlers([], 0, last))
    r = await lgc.maybe_open_cave(ses, sect_id="azure_cloud", continent_key="linghe",
                                  rng=ScriptedRng([0.0]), now=NOW)
    check("spawn.cooldown_guard", r is None)

    # 4c. chance falha (0.99 >= 0.20) → None
    last = Obj(state="expired", created_at=NOW - timedelta(days=3),
               resolved_at=NOW - timedelta(days=3), expires_at=NOW - timedelta(days=3))
    ses = FakeSession(_mk_handlers([], 0, last))
    r = await lgc.maybe_open_cave(ses, sect_id="azure_cloud", continent_key="linghe",
                                  rng=ScriptedRng([0.99, 0.99]), now=NOW)
    check("spawn.chance_miss", r is None)

    # 4d. chance passa + drift NÃO dispara (0.99 >= 0.30) → continente da casa
    ses = FakeSession(_mk_handlers([], 0, last))
    r = await lgc.maybe_open_cave(ses, sect_id="azure_cloud", continent_key="linghe",
                                  rng=ScriptedRng([0.10, 0.99]), now=NOW)
    check("spawn.opens", r is not None)
    if r is not None:
        check("spawn.continent_home", r.continent_key == "linghe")
        check("spawn.npc", (r.payload or {}).get("npc_key") == "tianlei")
        check("spawn.ttl", r.expires_at == NOW + timedelta(hours=lgc.LGC_TTL_H))
        check("spawn.state", r.state == "active")
        chron = _rows_of(ses, "WorldChronicle")
        check("spawn.chronicle", len(chron) == 1 and chron[0].event_type == "lgc_open")
        check("spawn.chronicle_npc", (chron[0].params or {}).get("npc") == "Shen Tianlei")
        wsp = _rows_of(ses, "HeavensWhisperLog")
        check("spawn.whisper", len(wsp) == 1 and wsp[0].theme == "cave_open")
        check("spawn.whisper_place", wsp[0].continent_key == "linghe")

    # 4e. drift dispara (0.10 < 0.30) → rng.choice decide (Mòyǔ coberta)
    ses = FakeSession(_mk_handlers([], 0, last))
    r = await lgc.maybe_open_cave(ses, sect_id="azure_cloud", continent_key="linghe",
                                  rng=ScriptedRng([0.10, 0.10], choice="moyu"), now=NOW)
    check("spawn.drift", r is not None and r.continent_key == "moyu"
          and (r.payload or {}).get("npc_key") == "xueye")

    # 4f. pity 7d: chance 0.99 seria miss, mas 8 dias sem gruta força
    old = Obj(state="expired", created_at=NOW - timedelta(days=8),
              resolved_at=NOW - timedelta(days=8), expires_at=NOW - timedelta(days=8))
    ses = FakeSession(_mk_handlers([], 0, old))
    r = await lgc.maybe_open_cave(ses, sect_id="azure_cloud", continent_key="linghe",
                                  rng=ScriptedRng([0.99, 0.99]), now=NOW)
    check("spawn.pity", r is not None)

    # 4g. mundo virgem (nenhuma gruta jamais) = pity → abre na 1ª ação
    ses = FakeSession(_mk_handlers([], 0, None))
    r = await lgc.maybe_open_cave(ses, sect_id="azure_cloud", continent_key="linghe",
                                  rng=ScriptedRng([0.99, 0.99]), now=NOW)
    check("spawn.virgin_world", r is not None)

    # 4h. continente da casa INVÁLIDO (ex.: None) → cai no choice
    ses = FakeSession(_mk_handlers([], 0, None))
    r = await lgc.maybe_open_cave(ses, sect_id="azure_cloud", continent_key=None,
                                  rng=ScriptedRng([0.99, 0.99], choice="qianhe"), now=NOW)
    check("spawn.invalid_home", r is not None and r.continent_key == "qianhe")

    # 4i. sweep expira a ativa vencida (chronicle lgc_faded) e AÍ pode abrir
    stale = Obj(id=7, state="active", created_at=NOW - timedelta(hours=80),
                resolved_at=None, expires_at=NOW - timedelta(hours=1),
                payload={"npc_key": "tianlei"}, continent_key="linghe")
    ses = FakeSession(_mk_handlers([stale], 0, old))
    r = await lgc.maybe_open_cave(ses, sect_id="azure_cloud", continent_key="linghe",
                                  rng=ScriptedRng([0.99, 0.99]), now=NOW)
    check("sweep.expired", stale.state == "expired" and stale.resolved_at == NOW)
    faded = [c for c in _rows_of(ses, "WorldChronicle") if c.event_type == "lgc_faded"]
    check("sweep.chronicle", len(faded) == 1)
    check("sweep.then_open", r is not None)

    # ═══ 5. start_cave_run — gates em ordem disclosed ═══
    import core.combat_engine as combat_engine
    import core.sect_trial_engine as sect_trial_engine
    import core.duel_engine as duel_engine

    _orig_hp = combat_engine.get_current_hp
    _orig_open = sect_trial_engine._has_open_duel
    _orig_start = duel_engine.start_duel_pve

    async def _no_open(session, pid):
        return None
    sect_trial_engine._has_open_duel = _no_open
    combat_engine.get_current_hp = (lambda p: 100)

    START_CALLS: list[dict] = []

    async def _fake_start(session, player, archetype, difficulty="normal",
                          source="npc_hunt", context=None, fighter_b_override=None,
                          npc_realm=None):
        START_CALLS.append({"archetype": archetype, "difficulty": difficulty,
                            "source": source, "context": context, "npc_realm": npc_realm})
        return Obj(id="duel-1")
    duel_engine.start_duel_pve = _fake_start

    ev = Obj(id=42, state="active", created_at=NOW - timedelta(hours=2),
             resolved_at=None, expires_at=NOW + timedelta(hours=70),
             payload={"npc_key": "tianlei"}, continent_key="linghe")
    me = Obj(telegram_id=111, language="pt", realm=7, current_continent="linghe",
             spirit_stones=0)

    def _start_handlers(*, player=me, cave=ev, last_duel=None, attempted=False):
        return [
            (lambda s, p: "players" in s, [player] if player else []),
            (lambda s, p: "world_events" in s and "ORDER BY" in s, [cave] if cave else []),
            (lambda s, p: "duel_sessions" in s and "ORDER BY" in s and "->>" not in s,
             [last_duel] if last_duel else []),
            (lambda s, p: "duel_sessions" in s and "->>" in s and "count" not in s.lower(),
             [(1,)] if attempted else []),
        ]

    r = await lgc.start_cave_run(FakeSession(_start_handlers(player=None)), 111)
    check("start.player_missing", r.get("reason") == "player_not_found")
    r = await lgc.start_cave_run(FakeSession(_start_handlers(cave=None)), 111)
    check("start.no_cave", r.get("reason") == "no_cave")
    far = Obj(telegram_id=111, language="pt", realm=7, current_continent="qianhe")
    r = await lgc.start_cave_run(FakeSession(_start_handlers(player=far)), 111)
    check("start.wrong_continent", r.get("reason") == "wrong_continent"
          and r.get("continent") == "linghe")
    r = await lgc.start_cave_run(FakeSession(_start_handlers(attempted=True)), 111)
    check("start.one_try", r.get("reason") == "already_attempted")
    # resume: duelo ABERTO desta MESMA abertura → devolve o duelo, não recusa
    open_mine = Obj(id="d-9", state="waiting_actions", pve_context={"event_id": 42})
    r = await lgc.start_cave_run(FakeSession(_start_handlers(last_duel=open_mine)), 111)
    check("start.resume", r.get("ok") is True and r.get("resumed") is True
          and r.get("duel_id") == "d-9" and r.get("npc") == "Shen Tianlei")
    # duelo aberto de OUTRA abertura → recusa honesta
    open_other = Obj(id="d-8", state="waiting_actions", pve_context={"event_id": 41})
    r = await lgc.start_cave_run(FakeSession(_start_handlers(last_duel=open_other)), 111)
    check("start.other_open", r.get("reason") == "duel_already_active")
    # HP esgotado → recusa nomeada (helper canônico, nunca player.current_hp)
    combat_engine.get_current_hp = (lambda p: 0)
    r = await lgc.start_cave_run(FakeSession(_start_handlers()), 111)
    check("start.hp", r.get("reason") == "hp_depleted")
    combat_engine.get_current_hp = (lambda p: 100)
    # feliz: cria o duelo com npc_realm FIXO da casa + contexto completo
    START_CALLS.clear()
    r = await lgc.start_cave_run(FakeSession(_start_handlers()), 111)
    check("start.ok", r.get("ok") is True and r.get("duel_id") == "duel-1")
    check("start.duel_args", len(START_CALLS) == 1 and START_CALLS[0]["source"] == "legacy_cave"
          and START_CALLS[0]["difficulty"] == lgc.LGC_NPC_DIFFICULTY
          and START_CALLS[0]["archetype"] == "elder"
          and START_CALLS[0]["npc_realm"] == 7,
          str(START_CALLS))
    check("start.duel_ctx", START_CALLS[0]["context"] == {"event_id": 42, "npc_key": "tianlei", "tech_id": 600})

    # ═══ 6. resolve — sempre-paga · roll + pity · dupe = dobro ═══
    import core.utils as core_utils
    import core.dao_engine as dao_engine

    _orig_add = core_utils.add_item_to_inventory
    _orig_frag = dao_engine.grant_random_fragments
    ADDED_ITEMS: list[tuple] = []

    async def _fake_add(session, pid, itype, iid, qty=1, quality="normal", force=False):
        ADDED_ITEMS.append((itype, iid, qty))
        return True

    async def _fake_frag(session, pid, count, realm):
        return [{"law": 1}] if realm >= 5 else []
    core_utils.add_item_to_inventory = _fake_add
    dao_engine.grant_random_fragments = _fake_frag

    tech600 = Obj(id=600, name="Last Thunder", emoji="⛈️", tech_type="combat",
                  library_tier=None, sect_key="legacy_tianlei")
    duel = Obj(id="d-1", pve_context={"event_id": 42, "npc_key": "tianlei", "tech_id": 600})

    def _resolve_handlers(*, has_art=False, clears=0, equipped=0, first_other=False,
                          prior_reg=None):
        return [
            (lambda s, p: "player_techniques" in s and "count" not in s.lower(),
             [(600,)] if has_art else []),
            (lambda s, p: "player_techniques" in s and "count" in s.lower(), [(equipped,)]),
            (lambda s, p: "duel_sessions" in s and "count" in s.lower(), [(clears,)]),
            (lambda s, p: "techniques_catalog" in s, [tech600]),
            (lambda s, p: "pg_advisory_xact_lock" in s, []),
            # prior_reg (grant) filtra por player_id ==; o check do 1º do
            # servidor (chronicle) filtra player_id != — o "!=" discrimina
            # (a lista de colunas do SELECT sempre contém sect_key).
            (lambda s, p: "player_sect_techniques" in s and "!=" not in s,
             [prior_reg] if prior_reg else []),
            (lambda s, p: "player_sect_techniques" in s and "!=" in s,
             [(999,)] if first_other else []),
        ]

    # 6a. derrota: nada além do veredito
    me.spirit_stones = 0
    ses = FakeSession(_resolve_handlers())
    r = await lgc.resolve_legacy_cave_from_duel(ses, duel, me, False)
    check("res.lost", r == {"cave": "lost"} and me.spirit_stones == 0 and not ses.added)

    # 6b. vitória sem arte no roll (0.99 >= 0.15), 1º clear → sempre-paga + missed
    me.spirit_stones = 0
    me.realm = 4  # abaixo de R5 → sem fragmento
    ADDED_ITEMS.clear()
    ses = FakeSession(_resolve_handlers(clears=0))
    r = await lgc.resolve_legacy_cave_from_duel(ses, duel, me, True, rng=ScriptedRng([0.99]))
    check("res.stones", r.get("stones") == lgc.LGC_STONES_BASE * 7 + 250
          and me.spirit_stones == r.get("stones"))  # linghe: bônus é em pedras
    check("res.no_frag_r4", "dao_fragments" not in r)
    check("res.missed", r.get("art_missed") == {"clears": 1, "pity_at": lgc.LGC_PITY_CLEARS})
    check("res.no_grant", not _rows_of(ses, "PlayerTechnique"))

    # 6c. vitória com roll (0.01 < 0.15) → grant + registro eterno + chronicle 1º
    me.spirit_stones = 0
    me.realm = 7
    ses = FakeSession(_resolve_handlers(clears=0))
    r = await lgc.resolve_legacy_cave_from_duel(ses, duel, me, True, rng=ScriptedRng([0.01]))
    check("res.frag_r7", r.get("dao_fragments") == 1)
    art = r.get("art") or {}
    check("res.art", art.get("tech_id") == 600 and art.get("auto_equipped") is True)
    pt_rows = _rows_of(ses, "PlayerTechnique")
    reg_rows = _rows_of(ses, "PlayerSectTechnique")
    check("res.grant_rows", len(pt_rows) == 1 and len(reg_rows) == 1)
    if reg_rows:
        check("res.reg_key", reg_rows[0].sect_key == "legacy_tianlei" and reg_rows[0].cp_paid == 0)
    claim = [c for c in _rows_of(ses, "WorldChronicle") if c.event_type == "lgc_claim"]
    check("res.claim_chronicle", len(claim) == 1)

    # 6d. pity: 2 clears anteriores → 3º clear GARANTE mesmo com roll 0.99
    ses = FakeSession(_resolve_handlers(clears=2))
    r = await lgc.resolve_legacy_cave_from_duel(ses, duel, me, True, rng=ScriptedRng([0.99]))
    check("res.pity", (r.get("art") or {}).get("tech_id") == 600 and r.get("clears") == 3)

    # 6e. já tem a arte → dobro DITO, nunca re-grant
    me.spirit_stones = 0
    ses = FakeSession(_resolve_handlers(has_art=True))
    r = await lgc.resolve_legacy_cave_from_duel(ses, duel, me, True, rng=ScriptedRng([0.01]))
    check("res.dupe", r.get("already_has_art") is True
          and r.get("stones") == (lgc.LGC_STONES_BASE * 7 + 250) * 2
          and not _rows_of(ses, "PlayerTechnique"))

    # 6f. slots cheios → arte vem SEM auto-equip (nunca desequipa ninguém)
    _orig_slots = combat_engine.get_max_combat_techniques
    combat_engine.get_max_combat_techniques = (lambda realm: 3)
    ses = FakeSession(_resolve_handlers(clears=0, equipped=3))
    r = await lgc.resolve_legacy_cave_from_duel(ses, duel, me, True, rng=ScriptedRng([0.01]))
    check("res.slots_full", (r.get("art") or {}).get("auto_equipped") is False)
    combat_engine.get_max_combat_techniques = _orig_slots

    # 6g. 1º do servidor JÁ existe noutro jogador → sem 2º chronicle lgc_claim
    ses = FakeSession(_resolve_handlers(clears=0, first_other=True))
    r = await lgc.resolve_legacy_cave_from_duel(ses, duel, me, True, rng=ScriptedRng([0.01]))
    claim = [c for c in _rows_of(ses, "WorldChronicle") if c.event_type == "lgc_claim"]
    check("res.claim_once", len(claim) == 0)

    # 6h-bis. RELEARN pós-renascimento (lição TEC-1 F3): registro eterno JÁ
    # existe (PlayerTechnique wipado no prestige) → re-ganha a arte SEM inserir
    # o registro de novo (PK player+tech estouraria) e SEM 2º chronicle.
    ses = FakeSession(_resolve_handlers(clears=0, prior_reg=Obj(technique_id=600)))
    r = await lgc.resolve_legacy_cave_from_duel(ses, duel, me, True, rng=ScriptedRng([0.01]))
    check("res.relearn_art", (r.get("art") or {}).get("tech_id") == 600)
    check("res.relearn_no_dup_reg", len(_rows_of(ses, "PlayerTechnique")) == 1
          and len(_rows_of(ses, "PlayerSectTechnique")) == 0)
    check("res.relearn_no_chron", not [c for c in _rows_of(ses, "WorldChronicle")
                                       if c.event_type == "lgc_claim"])

    # 6h. npc_key desconhecido no contexto → payload cru, nada roda
    bad = Obj(id="d-2", pve_context={"npc_key": "nope"})
    ses = FakeSession([])
    r = await lgc.resolve_legacy_cave_from_duel(ses, bad, me, True)
    check("res.bad_ctx", r == {"cave": "won"} and not ses.added)

    # 6i. material de continente com item (qianhe → ore id 3)
    duel_q = Obj(id="d-3", pve_context={"event_id": 43, "npc_key": "gushan", "tech_id": 601})
    tech601 = Obj(id=601, name="Nine Transformations Body", emoji="🗿", tech_type="combat",
                  library_tier=None, sect_key="legacy_gushan")
    ADDED_ITEMS.clear()
    ses = FakeSession([
        (lambda s, p: "player_techniques" in s and "count" not in s.lower(), []),
        (lambda s, p: "player_techniques" in s and "count" in s.lower(), [(0,)]),
        (lambda s, p: "duel_sessions" in s and "count" in s.lower(), [(0,)]),
        (lambda s, p: "techniques_catalog" in s, [tech601]),
        (lambda s, p: "pg_advisory_xact_lock" in s, []),
        (lambda s, p: "player_sect_techniques" in s, []),
    ])
    r = await lgc.resolve_legacy_cave_from_duel(ses, duel_q, me, True, rng=ScriptedRng([0.99]))
    check("res.material_ore", ADDED_ITEMS == [("ore", 3, 1)], str(ADDED_ITEMS))
    check("res.material_payload", r.get("materials") == [{"item_type": "ore", "item_id": 3, "qty": 1}])

    core_utils.add_item_to_inventory = _orig_add
    dao_engine.grant_random_fragments = _orig_frag
    combat_engine.get_current_hp = _orig_hp
    sect_trial_engine._has_open_duel = _orig_open
    duel_engine.start_duel_pve = _orig_start

    # ═══ 7. cave_view — vitrine honesta (display = roll) ═══
    ses = FakeSession([
        (lambda s, p: "techniques_catalog" in s, [tech600]),
        (lambda s, p: "duel_sessions" in s and "->>" in s, []),
        (lambda s, p: "player_techniques" in s, []),
    ])
    v = await lgc.cave_view(ses, ev, "pt", player=me, now=NOW)
    check("view.basic", v is not None and v["emoji"] == "🏮" and v["npc"] == "Shen Tianlei")
    if v:
        check("view.chance_is_knob", v["art_chance_pct"] == round(lgc.LGC_ART_CHANCE * 100))
        check("view.pity_is_knob", v["pity_clears"] == lgc.LGC_PITY_CLEARS)
        check("view.art_named", (v.get("art") or {}).get("tech_id") == 600)
        check("view.can_enter", v.get("can_enter") is True and v.get("here") is True)
        check("view.name_resolved", "Shen Tianlei" in (v.get("name") or ""))
    me_far = Obj(telegram_id=111, language="pt", realm=7, current_continent="moyu")
    ses = FakeSession([
        (lambda s, p: "techniques_catalog" in s, [tech600]),
        (lambda s, p: "duel_sessions" in s and "->>" in s, []),
        (lambda s, p: "player_techniques" in s, []),
    ])
    v = await lgc.cave_view(ses, ev, "pt", player=me_far, now=NOW)
    check("view.far_no_enter", v is not None and v.get("can_enter") is False)

    # ═══ 8. i18n ×3 ×2 — toda key que o código usa existe nas 3 línguas ═══
    chat_keys = [
        "lgc_cave_name", "chron_lgc_open", "chron_lgc_faded", "chron_lgc_claim",
        "wsp_cave_open_title", "wsp_cave_open_body", "lgc_chat_line", "lgc_chat_stakes",
        "lgc_chat_attempted", "lgc_chat_has_art", "lgc_chat_enter_btn", "lgc_chat_enter_toast",
        "lgc_err_wrong_continent", "lgc_err_attempted", "lgc_err_busy", "lgc_err_hp",
        "lgc_err_gone", "lgc_chat_won", "lgc_chat_won_mat", "lgc_chat_won_bagfull", "lgc_chat_won_frag",
        "lgc_chat_won_art", "lgc_chat_won_dupe", "lgc_chat_won_missed", "lgc_chat_lost",
    ] + [f"lgc_house_{k}" for k in lgc.CAVE_HOUSES] \
      + [f"tech_{i}_name" for i in range(600, 605)] + [f"tech_{i}_desc" for i in range(600, 605)]
    mini_keys = [
        "lgc_mini_art_line", "lgc_mini_one_try", "lgc_mini_has_art", "lgc_mini_attempted",
        "lgc_mini_enter", "lgc_mini_wrong", "lgc_mini_busy", "lgc_mini_hp", "lgc_mini_gone",
        "feature_legacy_caves", "feature_legacy_caves_desc",
    ]
    for lang in ("pt", "en", "es"):
        chat = json.loads(_read(f"locales/{lang}.json"))
        mini = json.loads(_read(f"miniapp/i18n/{lang}.json"))
        for k in chat_keys:
            check(f"i18n.chat.{lang}.{k}", k in chat)
        for k in mini_keys:
            check(f"i18n.mini.{lang}.{k}", k in mini)

    # ═══ 9. Wiring grep-provado ═══
    src_settle = _read("core/pve_duel_settle.py")
    check("wire.settle_branch", 'pve_source == "legacy_cave"' in src_settle)
    check("wire.settle_import", "resolve_legacy_cave_from_duel" in src_settle)
    src_pulse = _read("core/world_pulse_engine.py")
    check("wire.pulse_hook", "maybe_open_cave" in src_pulse
          and 'action == "seek_inheritance"' in src_pulse)
    src_web = _read("core/webserver.py")
    check("wire.route", "world/legacy_cave_start" in src_web)
    check("wire.api_events", "active_cave_view" in src_web and "legacy_caves_on" in src_web)
    src_chat = _read("handlers/sect.py")
    check("wire.chat_btn", '"trv_lgc_go"' in src_chat)
    check("wire.chat_view", "active_cave_view" in src_chat)
    src_mini = _read("miniapp/components/tabs.js")
    check("wire.mini_start", "world/legacy_cave_start" in src_mini)
    check("wire.mini_flag", 'featureEnabled("legacy_caves")' in src_mini)
    check("wire.mini_arena", "setCaveDuel" in src_mini and "DuelArenaModal" in src_mini)
    src_db = _read("database/db.py")
    check("wire.flag", '"legacy_caves"' in src_db)
    src_wsp = _read("core/heavens_whispers_engine.py")
    check("wire.whisper_theme", '"cave_open"' in src_wsp)
    src_duel = _read("core/duel_engine.py")
    check("wire.duel_doc", "legacy_cave" in src_duel)
    src_seeds = _read("database/seeds/combat_seeds.py")
    check("wire.seed_sync", "for tech_data in LEGACY_CAVE_TECHS" in src_seeds)

    # ═══ 10. A exclusão dos pools segue viva (sect_key IS NULL nos faucets) ═══
    for path in ("handlers/dungeons.py", "core/arena_duel_settle.py",
                 "core/pve_duel_settle.py", "core/dungeon_quest_engine.py"):
        check(f"pool.{path}", "sect_key.is_(None)" in _read(path))
    check("pool.combat_menus", _read("handlers/combat.py").count("sect_key.is_(None)") >= 2)
    check("pool.web_menus", "sect_key.is_(None)" in src_web)

    print(f"PASS {PASS} · FAIL {len(FAILS)}")
    for f in FAILS:
        print(" ✗", f)
    if FAILS:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
