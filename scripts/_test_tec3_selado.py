"""TEC-3 — teste isolado das Duas Estantes Seladas (SEM DB).

Roda: python -X utf8 scripts/_test_tec3_selado.py

Padrão _test_tec1_library: ExplodingSession prova que a flag OFF não toca o DB
e que o payload volta BYTE-IDÊNTICO ao TEC-1 (zero key nova); FakeSession prova
a lógica ON. Cobre em particular as armadilhas que o QoL-relatos ensinou:

  · a contagem de estantes vem das SEEDS (max library_tier do catálogo vivo),
    NUNCA da tupla do engine — uma seed futura falha alto em vez de sumir;
  · "fora da escala por cima" clampa para o TOPO do custo, nunca para grátis;
  · todo `block` novo (karma/rite) tem casa nos DOIS consumidores de cliente;
  · o lockout cross-sect virou `>= 3` nas CINCO cópias da regra (o helper + as
    4 sombras), e o teste lê as quatro sombras por grep.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
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

PASS = 0
FAILS: list[str] = []
DUEL_CALLS: list = []
CHRON_CALLS: list = []


def _rows_of(session, cls_name: str) -> list:
    """Linhas REAIS gravadas, por tipo — contar `len(session.added)` mistura o
    que o Chronicle enfileira com o que a transmissao grava."""
    return [o for o in session.added if type(o).__name__ == cls_name]


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


# ── Fakes (espelho do harness TEC-1) ─────────────────────────────────────────
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

    def all(self):
        return list(self._rows)

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
        self.committed = False
        self.flushed = 0

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
        raise AssertionError("query inesperada: " + sql[:200].replace("\n", " "))

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def flush(self):
        self.flushed += 1

    async def rollback(self):
        return None

    def begin_nested(self):
        class _SP:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False
        return _SP()


def T(**kw):
    d = dict(id=0, name="X", emoji="⚔️", effect_type="damage_mult", effect_value=0.2,
             effect_round=0, req_realm=1, qi_cost=20, tech_type="combat",
             description="d", sect_key=None, library_tier=None, library_cp_cost=None)
    d.update(kw)
    return types.SimpleNamespace(**d)


def P(**kw):
    d = dict(telegram_id=111, sect_id="azure_cloud", sect_rank="heir",
             sect_contribution=9000, sect_contribution_earned=9000, realm=8,
             language="pt", spirit_stones=0, karma=400, scroll_econ=None,
             current_hp=100)
    d.update(kw)
    return types.SimpleNamespace(**d)


def D(**kw):
    """Fake DuelSession row (o rito lê state/resolved_at/id)."""
    d = dict(id="d-1", state="finished", resolved_at=None, pve_source="hidden_rite",
             attacker_id=111, winner_id=111, round_idx=3, pve_context={})
    d.update(kw)
    return types.SimpleNamespace(**d)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _src(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


# ══ 1. OFF-identity — a flag desligada não toca o DB nem muda o payload ══════
def _off_blocks() -> None:
    check("off.gate", lib.selado_on() is False, "sem DB o gate fail-safe é False")
    check("off.tiers", lib.library_tiers() == (1, 2, 3),
          "OFF ⇒ só as 3 estantes-base (Lei §5)")
    es = ExplodingSession()
    r = run(lib.start_hidden_rite(es, 1, 590))
    check("off.rite_start", r == {"ok": False, "reason": "sel_off"}, str(r))
    # o gate do TEC-3 é conjunção: só `estantes_seladas` não abre nada
    _orig_feat = None
    try:
        import database.db as _db
        _orig_feat = _db.feature_enabled_for_world
        _db.feature_enabled_for_world = lambda f, w=None: f == "estantes_seladas"
        check("off.dependency", lib.selado_on() is False,
              "estantes_seladas sem biblioteca_seitas NÃO abre (dependência é conjunção)")
        _db.feature_enabled_for_world = lambda f, w=None: True
        check("off.dependency_both", lib.selado_on() is True,
              "as duas ON ⇒ abre")
    finally:
        if _orig_feat is not None:
            import database.db as _db2
            _db2.feature_enabled_for_world = _orig_feat


# ══ 2. Puras — custo, karma alinhado, lockout ═══════════════════════════════
def _pure_blocks() -> None:
    check("pure.cp4", lib.tier_default_cp(4) == lib.SEL_T4_CP == 6000,
          str(lib.tier_default_cp(4)))
    check("pure.cp5", lib.tier_default_cp(5) == lib.SEL_T5_CP == 0,
          "a Oculta NÃO se compra (Lei §4/§12)")
    # TEC-5 — o tier 6 deixou de ser hipotético: é o Cofre Proibido, e ele NÃO se
    # compra (Lei §4/§12, como a Oculta). A entrada explícita `6: 0` no _TIER_CP é
    # justamente o que impede o clamp-para-o-topo de o precificar a 6000.
    check("pure.cp6", lib.tier_default_cp(6) == 0,
          "o Cofre Proibido não se compra — o segredo não tem preço")
    # Lição QoL-relatos §0.0.2 — o tier AINDA desconhecido (7+) vai para o TOPO da
    # escala, nunca para o neutro/grátis.
    check("pure.cp_above_scale", lib.tier_default_cp(7) == max(6000, 3000, 750, 0) == 6000,
          "um library_tier futuro e DESCONHECIDO NÃO pode degradar para grátis")
    check("pure.cp_absent", lib.tier_default_cp(0) == 0 and lib.tier_default_cp(None) == 0,
          "ausente/lixo segue neutro — isso é 'não é estante'")
    check("pure.cost_col_t4", lib.tier_cp_cost(T(library_tier=4, library_cp_cost=1234)) == 1234)
    check("pure.cost_fallback_t4", lib.tier_cp_cost(T(library_tier=4)) == 6000)
    check("pure.cost_fallback_t5", lib.tier_cp_cost(T(library_tier=5)) == 0)

    # karma ALINHADO — o achado que derrubou o default do prompt
    check("pure.karma_righteous", lib.aligned_karma(400, "azure_cloud") == 400)
    check("pure.karma_demonic", lib.aligned_karma(-400, "abyssal_depths") == 400,
          "casa demoníaca lê o karma NEGATIVO")
    check("pure.karma_demonic_positive", lib.aligned_karma(400, "abyssal_depths") == -400,
          "um demoníaco 'santo' está fora do caminho da casa")
    check("pure.karma_unknown_house", lib.aligned_karma(400, None) == 400)
    check("pure.karma_gate_r", lib.karma_gate_ok(250, "azure_cloud") is True)
    check("pure.karma_gate_r_low", lib.karma_gate_ok(249, "azure_cloud") is False)
    check("pure.karma_gate_d", lib.karma_gate_ok(-250, "abyssal_depths") is True,
          "a casa demoníaca TEM porta — o gate cru `karma>=X` a trancaria para sempre")
    check("pure.karma_gate_d_low", lib.karma_gate_ok(-249, "abyssal_depths") is False)
    check("pure.karma_gate_neutral", lib.karma_gate_ok(0, "azure_cloud") is False
          and lib.karma_gate_ok(0, "abyssal_depths") is False,
          "o indeciso não entra em câmara nenhuma")
    check("pure.karma_min", lib.SEL_KARMA_MIN == 250,
          "default = o mesmo número em que o CAMINHO cristaliza")

    # lockout cross-sect >= 3 (o helper)
    p = P(sect_id="azure_cloud")
    for tier in (3, 4, 5):
        check(f"pure.lock_t{tier}_other",
              lib.is_library_locked(T(library_tier=tier, sect_key="iron_mountain"), p) is True)
        check(f"pure.lock_t{tier}_same",
              lib.is_library_locked(T(library_tier=tier, sect_key="azure_cloud"), p) is False)
    check("pure.lock_t2", lib.is_library_locked(T(library_tier=2, sect_key="iron_mountain"), p) is False,
          "tiers 1-2 NUNCA trancam (lições básicas não se desaprendem)")
    check("pure.lock_legacy", lib.is_library_locked(T(library_tier=None, sect_key="iron_mountain"), p) is False,
          "as 45 legadas v16.4c seguem sem lockout (decisão owner 2026-06-16)")
    check("pure.lock_floor", lib.LOCK_TIER_FLOOR == 3)
    check("pure.rite_tier", lib.RITE_TIER == 5 and lib.RITE_PVE_SOURCE == "hidden_rite")
    check("pure.pve_source_len", len(lib.RITE_PVE_SOURCE) <= 24,
          "duel_sessions.pve_source é VARCHAR(24)")

    # rank gap — o caminho quantificado
    g = lib._rank_gap(0, 0, "elder")
    check("pure.gap_both", g == {"contribution": 600, "realm": 5,
                                 "need_contribution": 600, "need_realm": 5}, str(g))
    g = lib._rank_gap(600, 0, "elder")
    check("pure.gap_realm_only", g["contribution"] == 0 and g["realm"] == 5, str(g))
    check("pure.gap_none", lib._rank_gap(1500, 7, "heir") is None,
          "quem já está no degrau não vê caminho nenhum")


# ══ 3. ON — a view com as 5 estantes ════════════════════════════════════════
LEGACY = {"disciple": 500, "inner": 501, "core": 502, "elder": 503, "heir": 504}


def _mk_session(*, player=None, learned=(), pst_rows=(), duel_rows=(), quest_done=True):
    pl = player or P()
    legacy_rows = [T(id=i, name=f"L{i}", sect_key="azure_cloud", req_realm=1)
                   for i in LEGACY.values()]
    new_rows = [
        T(id=550, name="N550", sect_key="azure_cloud", library_tier=1, library_cp_cost=0, req_realm=1),
        T(id=551, name="N551", sect_key="azure_cloud", library_tier=2, library_cp_cost=750, req_realm=2),
        T(id=552, name="N552", sect_key="azure_cloud", library_tier=3, library_cp_cost=3000, req_realm=4),
        T(id=580, name="N580", sect_key="azure_cloud", library_tier=4, library_cp_cost=6000, req_realm=5),
        T(id=590, name="N590", sect_key="azure_cloud", library_tier=5, library_cp_cost=0, req_realm=7),
    ]

    def catalog_rows(params):
        allr = legacy_rows + new_rows
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
            return [r for r in allr if r.sect_key == want
                    and r.library_tier in lib.library_tiers()]
        return allr

    h = lambda pred, rows: (pred, rows)  # noqa: E731
    return FakeSession([
        h(lambda s, p: "pg_advisory_xact_lock" in s, [None]),
        h(lambda s, p: "FROM duel_sessions" in s, list(duel_rows)),
        h(lambda s, p: "player_sect_techniques" in s, list(pst_rows)),
        h(lambda s, p: "quests_catalog" in s, [(1,)] if quest_done else []),
        h(lambda s, p: "is_active_combat" in s and "player_techniques" in s
          and "techniques_catalog" in s, []),
        h(lambda s, p: "player_techniques" in s and "techniques_catalog" not in s,
          list(learned)),
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


def _on_blocks() -> None:  # noqa: C901
    # ── a view: 5 estantes, sealed VAZIO ──
    s, pl = _mk_session()
    view = run(lib.get_library_shelves(s, 111))
    check("on.tiers", lib.library_tiers() == (1, 2, 3, 4, 5))
    check("on.view.shelves", [sh["tier"] for sh in view["shelves"]] == [1, 2, 3, 4, 5],
          str([sh["tier"] for sh in view["shelves"]]))
    check("on.view.sealed_empty", view["sealed"] == [],
          "as câmaras viraram estantes REAIS — o teaser some, mas a key fica (nunca nova)")
    check("on.view.selado_key", view.get("selado") is True)
    check("on.view.rite_key", isinstance(view.get("rite"), dict))

    sh4 = view["shelves"][3]
    sh5 = view["shelves"][4]
    check("on.sh4.label_key", sh4["min_rank_key"] == "wsect_rank_elder")
    check("on.sh5.label_key", sh5["min_rank_key"] == "wsect_rank_heir")
    check("on.sh4.arts", len(sh4["arts"]) == 2 and sh4["arts"][0]["legacy"] is True
          and sh4["arts"][1]["legacy"] is False,
          "câmara = arte legada (grátis por posto) + arte nova")
    a580 = sh4["arts"][1]
    a590 = sh5["arts"][1]
    check("on.t4.cost", a580["cost"] == 6000, str(a580["cost"]))
    check("on.t4.can_learn", a580["can_learn"] is True and a580["block"] is None,
          "heir com 9000 de saldo compra a do Ancião")
    check("on.t5.cost_zero", a590["cost"] == 0, "a Oculta não se compra")
    check("on.t5.block_rite", a590["block"] == "rite", str(a590["block"]))
    check("on.t5.needs_rite_key", a590.get("needs_rite") is True)
    check("on.t5.karma_keys", a590.get("karma_have") == 400 and a590.get("karma_need") == 250)
    check("on.t4.no_rite_keys", "needs_rite" not in a580 and "karma_have" not in a580,
          "key nova SÓ na arte que a usa (payload condicional)")
    check("on.t5.legacy_free", sh5["arts"][0]["legacy"] is True
          and "needs_rite" not in sh5["arts"][0],
          "a arte legada do Herdeiro segue grátis por posto (decisão v16.4c intacta)")

    # ── karma barra ANTES do rito, e a casa demoníaca tem porta ──
    s, _ = _mk_session(player=P(karma=0))
    view = run(lib.get_library_shelves(s, 111))
    check("on.karma_block", view["shelves"][4]["arts"][1]["block"] == "karma",
          "karma insuficiente é dito ANTES do rito (ordem disclosed)")
    check("on.karma_block_numbers",
          view["shelves"][4]["arts"][1]["karma_have"] == 0,
          "o número é DITO, não só o bloqueio")

    # ── o caminho quantificado quando o posto ainda não chegou ──
    s, _ = _mk_session(player=P(sect_rank="core", sect_contribution_earned=200,
                               sect_contribution=200, realm=4))
    view = run(lib.get_library_shelves(s, 111))
    sh4 = view["shelves"][3]
    check("on.gap.present", sh4.get("rank_gap") is not None and sh4["rank_ok"] is False)
    check("on.gap.numbers", sh4["rank_gap"]["contribution"] == 400
          and sh4["rank_gap"]["realm"] == 1, str(sh4.get("rank_gap")))
    check("on.gap.absent_when_ok", view["shelves"][0].get("rank_gap") is None,
          "estante já alcançada não mostra caminho")
    check("on.gap.block_rank", sh4["arts"][1]["block"] == "rank")

    # ── a escada lê `earned`, NUNCA o saldo (Lei §4) ──
    s, _ = _mk_session(player=P(sect_rank="core", sect_contribution=999999,
                                sect_contribution_earned=200, realm=4))
    view = run(lib.get_library_shelves(s, 111))
    check("on.gap.uses_earned", view["shelves"][3]["rank_gap"]["contribution"] == 400,
          "saldo gigante NÃO encurta o caminho do posto")

    # ── learn: a Oculta recusa sem o rito e NÃO debita ──
    s, pl = _mk_session()
    r = run(lib.learn_library_technique(s, 111, 590))
    check("on.learn.t5_needs_rite", r == {"ok": False, "reason": "rite_required"}, str(r))
    check("on.learn.t5_no_debit", pl.sect_contribution == 9000,
          "recusa NÃO toca o saldo")
    check("on.learn.t5_no_rows", not s.added, "recusa não grava nada")

    s, pl = _mk_session(player=P(karma=10))
    r = run(lib.learn_library_technique(s, 111, 590))
    check("on.learn.t5_karma", r.get("reason") == "karma_too_low"
          and r.get("karma_need") == 250 and r.get("karma_have") == 10, str(r))

    # ── learn: a Oculta APÓS o rito é grátis e não mexe na escada ──
    s, pl = _mk_session(pst_rows=[types.SimpleNamespace(player_id=111, technique_id=590)])
    r = run(lib.learn_library_technique(s, 111, 590))
    # registro prévio ⇒ re-aprender grátis (mesmo perdão do renascimento, F3)
    check("on.learn.t5_prior_reg", r.get("ok") is True and r.get("cp_spent") == 0, str(r))
    check("on.learn.t5_ladder_intact", pl.sect_contribution_earned == 9000,
          "a escada de posto NUNCA é tocada por aprender arte (Lei §4)")
    check("on.learn.t5_balance_intact", pl.sect_contribution == 9000,
          "a Oculta custa 0 — nem o saldo se move")

    # ── learn: a do Ancião debita o SALDO e só o saldo ──
    s, pl = _mk_session()
    r = run(lib.learn_library_technique(s, 111, 580))
    check("on.learn.t4_ok", r.get("ok") is True and r.get("tier") == 4, str(r))
    check("on.learn.t4_debit", r.get("cp_spent") == 6000 and pl.sect_contribution == 3000)
    check("on.learn.t4_ladder", pl.sect_contribution_earned == 9000,
          "earned intocado — comprar arte nunca recua nem avança posto")
    check("on.learn.t4_rows",
          len(_rows_of(s, "PlayerTechnique")) == 1
          and len(_rows_of(s, "PlayerSectTechnique")) == 1,
          "PlayerTechnique + o registro eterno em player_sect_techniques")

    s, pl = _mk_session(player=P(sect_contribution=10))
    r = run(lib.learn_library_technique(s, 111, 580))
    check("on.learn.t4_poor", r.get("reason") == "insufficient_merit"
          and r.get("cost") == 6000, str(r))

    # ── posto abaixo: a ordem disclosed é posto ANTES de tudo ──
    s, _ = _mk_session(player=P(sect_rank="core", realm=8))
    r = run(lib.learn_library_technique(s, 111, 580))
    check("on.learn.t4_rank", r.get("reason") == "rank_too_low"
          and r.get("req_rank_key") == "wsect_rank_elder", str(r))

    # ── o rito ──
    s, pl = _mk_session()
    r = run(lib.start_hidden_rite(s, 111, 590))
    check("on.rite.start", r.get("ok") is True and r.get("tech_id") == 590, str(r))
    check("on.rite.duel_contract", DUEL_CALLS and DUEL_CALLS[-1].get("source") == "hidden_rite"
          and DUEL_CALLS[-1]["context"].get("tech_id") == 590
          and DUEL_CALLS[-1]["context"].get("sect_id") == "azure_cloud",
          str(DUEL_CALLS[-1:]))
    check("on.rite.duel_hard", DUEL_CALLS[-1].get("difficulty") == "hard"
          and DUEL_CALLS[-1].get("archetype") == "elder",
          "a Prova e mais dura que o rito de entrada (normal)")

    # double-tap: com um duelo aberto o rito RETOMA, não abre um segundo
    s, pl = _mk_session(duel_rows=[D(state="waiting_actions", resolved_at=None)])
    r = run(lib.start_hidden_rite(s, 111, 590))
    check("on.rite.resume", r.get("ok") is True and r.get("resumed") is True
          and r.get("duel_id") == "d-1", str(r))

    # cooldown honesto após uma derrota recente
    from datetime import datetime, timedelta, timezone
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    s, pl = _mk_session(duel_rows=[D(state="finished", resolved_at=recent, winner_id=None)])
    st = run(lib.hidden_rite_state(s, 111, "azure_cloud"))
    check("on.rite.cooldown", st.get("cooldown_ms") and st.get("can_start") is False, str(st))
    old = datetime.now(timezone.utc) - timedelta(hours=lib.SEL_RITE_COOLDOWN_H + 1)
    s, pl = _mk_session(duel_rows=[D(state="finished", resolved_at=old, winner_id=None)])
    st = run(lib.hidden_rite_state(s, 111, "azure_cloud"))
    check("on.rite.cooldown_expired", st.get("cooldown_ms") is None
          and st.get("can_start") is True, str(st))

    # o rito recusa arte que não é da Oculta
    s, _ = _mk_session()
    r = run(lib.start_hidden_rite(s, 111, 580))
    check("on.rite.wrong_tier", r.get("reason") == "tech_not_in_library", str(r))
    s, _ = _mk_session(player=P(karma=0))
    r = run(lib.start_hidden_rite(s, 111, 590))
    check("on.rite.karma", r.get("reason") == "karma_too_low", str(r))
    s, _ = _mk_session(player=P(sect_rank="elder"))
    r = run(lib.start_hidden_rite(s, 111, 590))
    check("on.rite.rank", r.get("reason") == "rank_too_low", str(r))
    import core.combat_engine as ce
    _orig_hp = ce.get_current_hp
    ce.get_current_hp = lambda pl: int(getattr(pl, "current_hp", 100) or 0)
    try:
        s, _ = _mk_session(player=P(current_hp=0))
        r = run(lib.start_hidden_rite(s, 111, 590))
        check("on.rite.hp", r.get("reason") == "hp_depleted", str(r))
    finally:
        ce.get_current_hp = _orig_hp

    # settle: derrota NÃO transmite; vitória transmite pelo MESMO helper
    s, pl = _mk_session()
    r = run(lib.resolve_hidden_rite_from_duel(
        s, D(pve_context={"sect_id": "azure_cloud", "tech_id": 590}), pl, False))
    check("on.settle.lost", r == {"rite": "lost"}, str(r))
    check("on.settle.lost_no_rows", not s.added, "derrota não grava nada")

    s, pl = _mk_session()
    r = run(lib.resolve_hidden_rite_from_duel(
        s, D(pve_context={"sect_id": "azure_cloud", "tech_id": 590}), pl, True))
    check("on.settle.won", r.get("rite") == "won" and r.get("tech_id") == 590, str(r))
    check("on.settle.won_rows",
          len(_rows_of(s, "PlayerTechnique")) == 1
          and len(_rows_of(s, "PlayerSectTechnique")) == 1,
          "a vitória grava a arte + o registro eterno")
    check("on.settle.chronicle", any(c.get("event_type") == "sel_first" for c in CHRON_CALLS),
          "o 1º segredo do servidor por casa vira Crônica")
    check("on.settle.no_cp", pl.sect_contribution == 9000,
          "vencer não debita contribuição (a Oculta não tem preço)")

    # sair de casa no meio da Prova NÃO transmite o segredo de uma casa alheia
    s, pl = _mk_session(player=P(sect_id="iron_mountain"))
    r = run(lib.resolve_hidden_rite_from_duel(
        s, D(pve_context={"sect_id": "azure_cloud", "tech_id": 590}), pl, True))
    check("on.settle.wrong_house", r.get("rite") == "wrong_house" and not s.added, str(r))

    # já aprendida: idempotente, zero linha nova (double-settle)
    s, pl = _mk_session(learned=[(590,)])
    r = run(lib.resolve_hidden_rite_from_duel(
        s, D(pve_context={"sect_id": "azure_cloud", "tech_id": 590}), pl, True))
    check("on.settle.idempotent", r.get("already_learned") is True and not s.added, str(r))

    # leave: tier >= 3 tranca (o helper lê o piso, não um 3 fixo)
    s, _ = _mk_session()
    check("on.leave.floor_in_sql", lib.LOCK_TIER_FLOOR == 3)

    # promoção a elder/heir passa a notificar (com a flag ON)
    import core.notification_engine as ne
    calls: list = []
    _orig = ne.notify

    async def _spy(session, pid, kind, **kw):
        calls.append((pid, kw.get("payload", {}).get("rank_key")))
        return None
    ne.notify = _spy
    try:
        s, _ = _mk_session()
        run(lib.notify_shelf_unlocked(s, 111, "elder"))
        run(lib.notify_shelf_unlocked(s, 111, "heir"))
        check("on.notify.elder_heir", len(calls) == 2, str(calls))
    finally:
        ne.notify = _orig


# ══ 4. Seeds — a régua e a CONTAGEM que vem das SEEDS ═══════════════════════
def _seed_blocks() -> None:  # noqa: C901
    from core.world_sects_engine import SECT_LIBRARY, WORLD_SECT_KEYS
    from database.seeds.combat_seeds import (SECT_LIBRARY_TEC1,
                                             SECT_LIBRARY_TEC3, TECHNIQUES)

    check("seed.count", len(SECT_LIBRARY_TEC3) == 18, str(len(SECT_LIBRARY_TEC3)))
    ids = sorted(t["id"] for t in SECT_LIBRARY_TEC3)
    check("seed.ids", ids == list(range(580, 589)) + list(range(590, 599)),
          "580-588 (Ancião) + 590-598 (Oculta); 589 fica de reserva")

    per_house: dict = {}
    for t in SECT_LIBRARY_TEC3:
        per_house.setdefault(t["sect_key"], []).append(t["library_tier"])
    check("seed.houses", set(per_house) == set(WORLD_SECT_KEYS),
          "as 9 casas, sem exceção")
    check("seed.one_per_chamber", all(sorted(v) == [4, 5] for v in per_house.values()),
          "1 arte por câmara por casa (Lei §3: profundidade > variedade)")

    # ⚠️ LIÇÃO QoL-relatos §0.0.1 — a contagem vem das SEEDS, não da tupla do engine.
    # Se uma seed futura introduzir um library_tier 6, ISTO falha alto em vez de
    # o tier sumir em silêncio da Biblioteca.
    seeded_tiers = sorted({int(t["library_tier"]) for t in SECT_LIBRARY_TEC1 + SECT_LIBRARY_TEC3})
    check("seed.tiers_from_seeds", seeded_tiers == [1, 2, 3, 4, 5], str(seeded_tiers))
    max_seed_tier = max(int(t.get("library_tier") or 0) for t in TECHNIQUES)
    # TEC-5 acrescentou o tier 6 (Cofre Proibido) — o teto do CATÁLOGO tem de
    # continuar coberto pelas tuplas do engine, senão a estante some em silêncio.
    known = max(lib.LIBRARY_TIERS + lib.SEALED_TIERS + lib.FORBIDDEN_TIERS)
    check("seed.max_tier_known", max_seed_tier == known,
          f"catálogo vivo tem tier {max_seed_tier}; o engine conhece {known} — "
          "se divergir, a estante some")
    check("seed.tier_min_rank_covers", all(t in lib.TIER_MIN_RANK for t in seeded_tiers),
          "todo tier seedado tem posto mínimo (senão KeyError no learn)")

    # A RÉGUA IN-BAND — medida contra os degraus legados da MESMA casa.
    BUDGET = {
        4: {"qi": 52, "realm": 5, "damage_mult": (0.46, 0.50), "damage_reduce": (0.40, 0.44),
            "evasion": (0.28, 0.32), "armor_ignore": (0.42, 0.46)},
        5: {"qi": 68, "realm": 7, "damage_mult": (0.62, 0.68), "damage_reduce": (0.50, 0.55),
            "evasion": (0.36, 0.40), "armor_ignore": (0.52, 0.56)},
    }
    # Tetos GLOBAIS do catálogo vivo por efeito (anti power creep, Lei §12):
    # nenhuma arte nova pode passar do que o jogo já tem.
    caps: dict = {}
    for t in TECHNIQUES:
        if t["id"] in {x["id"] for x in SECT_LIBRARY_TEC3}:
            continue
        caps[t["effect_type"]] = max(caps.get(t["effect_type"], 0.0), float(t["effect_value"]))
    for t in SECT_LIBRARY_TEC3:
        b = BUDGET[t["library_tier"]]
        lo, hi = b.get(t["effect_type"], (None, None))
        ok_stats = t["qi_cost"] == b["qi"] and t["req_realm"] == b["realm"]
        ok_val = lo is not None and lo <= t["effect_value"] <= hi and t["effect_round"] == 0
        check(f"seed.{t['id']}.regua", ok_stats and ok_val,
              f"{t['effect_type']}={t['effect_value']} qi={t['qi_cost']} r={t['req_realm']}")
        check(f"seed.{t['id']}.in_band", t["effect_value"] <= caps.get(t["effect_type"], 0.0),
              f"{t['effect_value']} > teto vivo {caps.get(t['effect_type'])} — power creep")
        check(f"seed.{t['id']}.cp", t["library_cp_cost"] == lib.tier_default_cp(t["library_tier"]))
        check(f"seed.{t['id']}.combat",
              t["tech_type"] == "combat" and t["sect_key"] in WORLD_SECT_KEYS)
        check(f"seed.{t['id']}.no_dodge", t["effect_type"] != "dodge",
              "dodge>0 é binário 50% no engine — subir o número não significaria nada")

    # element/intent COPIAM a casa (a convenção 500-576 é 100% consistente)
    house_el: dict = {}
    for t in TECHNIQUES:
        if t.get("sect_key") in WORLD_SECT_KEYS and t["id"] < 580:
            house_el.setdefault(t["sect_key"], set()).add((t["element"], t["intent_affinity"]))
    for t in SECT_LIBRARY_TEC3:
        pairs = house_el.get(t["sect_key"], set())
        check(f"seed.{t['id']}.house_flavour",
              (t["element"], t["intent_affinity"]) in pairs,
              f"{t['element']}/{t['intent_affinity']} não é par da casa {t['sect_key']}")

    names = [t["name"] for t in TECHNIQUES]
    check("seed.unique_names", len(names) == len(set(names)), "coluna name é UNIQUE")
    check("seed.name_len", all(len(t["name"]) <= 64 for t in SECT_LIBRARY_TEC3),
          "name é String(64)")
    check("seed.emoji_len", all(len(t["emoji"]) <= 8 for t in SECT_LIBRARY_TEC3),
          "emoji é String(8)")
    check("seed.in_techniques", all(t in TECHNIQUES for t in SECT_LIBRARY_TEC3),
          "as 18 entram na lista que o runner semeia")
    legacy_ids = {e["tech_id"] for v in SECT_LIBRARY.values() for e in v}
    tec1_ids = {t["id"] for t in SECT_LIBRARY_TEC1}
    check("seed.no_id_clash", not (set(ids) & (legacy_ids | tec1_ids)),
          "sem colisão com 500-544 nem 550-576")
    check("seed.force_sync", "SECT_LIBRARY_TEC1 + SECT_LIBRARY_TEC3"
          in _src("database", "seeds", "combat_seeds.py"),
          "o force-sync de boot tem de re-aplicar as colunas das 18 também")

    # i18n ×3 + o % da desc PT bate com effect_value (anti drift de conteúdo)
    for lang in ("pt", "en", "es"):
        data = json.load(open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8"))
        missing = [i for i in ids if f"tech_{i}_name" not in data or f"tech_{i}_desc" not in data]
        check(f"i18n.content.{lang}", not missing, str(missing[:5]))
    data_pt = json.load(open(os.path.join(ROOT, "locales", "pt.json"), encoding="utf-8"))
    seen_names: set = set()
    for t in SECT_LIBRARY_TEC3:
        pct = int(round(t["effect_value"] * 100))
        desc = data_pt.get(f"tech_{t['id']}_desc", "")
        check(f"i18n.{t['id']}.pct", str(pct) in re.sub(r"[^0-9 ]", " ", desc),
              f"{pct}% não citado na desc pt")
        nm = data_pt.get(f"tech_{t['id']}_name", "")
        check(f"i18n.{t['id']}.name_unique", nm and nm not in seen_names, nm)
        seen_names.add(nm)
    # as duas estantes novas têm rótulo (o engine deriva lib_shelf_<tier>)
    for lang in ("pt", "en", "es"):
        data = json.load(open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8"))
        for tier in lib.SEALED_TIERS:
            check(f"i18n.shelf_{tier}.{lang}", f"lib_shelf_{tier}" in data,
                  "sem a key o jogador lê lib_shelf_4 cru (lição R6)")


# ══ 5. Wiring grep-provável (flag sem call-site = promessa vazia) ═══════════
def _wiring_blocks() -> None:  # noqa: C901
    check("wire.flag", '"estantes_seladas":' in _src("database", "db.py"))
    check("wire.no_migration",
          not os.path.exists(os.path.join(ROOT, "migrations", "138_estantes_seladas.sql")),
          "TEC-3 é ZERO migration por desenho (library_tier já é INT; o estado do "
          "rito vive em duel_sessions)")

    # As 4 SOMBRAS da regra do lockout têm de ter movido para >= (lição: 4
    # reimplementações independentes de "tier 3 = trancada" vivem fora do helper)
    hc = _src("handlers", "combat.py")
    ws = _src("core", "webserver.py")
    hs = _src("handlers", "sect.py")
    tj = _src("miniapp", "components", "tabs.js")
    check("wire.shadow_chat", "library_tier >= _lib_floor" in hc,
          "handlers/combat.py — o 🔒 da lista de técnicas")
    check("wire.shadow_api", "library_tier >= _lib_floor" in ws,
          "core/webserver.py — a key lib_locked do payload")
    check("wire.shadow_leave", "library_tier >= _lib_floor" in hs,
          "handlers/sect.py — o aviso ao sair da casa")
    check("wire.shadow_mini", "s.tier >= 3" in tj,
          "miniapp — o aviso de leave derivado das estantes")
    check("wire.no_stale_eq3",
          "library_tier == 3" not in hc and "library_tier == 3" not in ws
          and "_TC.library_tier == 3" not in hs,
          "nenhuma sombra ficou fixada no 3")

    # o rito: source registrado no dispatcher (source ausente = recompensa MORTA)
    ps = _src("core", "pve_duel_settle.py")
    check("wire.settle_branch", '"hidden_rite"' in ps
          and "resolve_hidden_rite_from_duel" in ps)
    check("wire.duel_doc", "hidden_rite" in _src("core", "duel_engine.py"),
          "o docstring do start_duel_pve lista os sources")
    check("wire.endpoint", "world/hidden_rite_start" in ws
          and "api_world_hidden_rite_start" in ws)

    # superfícies: os DOIS clientes leem as keys NOVAS (lição QoL-relatos §0.0.3 —
    # emitir a key no payload NÃO é mostrar ao jogador)
    hl = _src("handlers", "library.py")
    check("wire.chat_block_karma", '"karma": "sel_block_karma"' in hl)
    check("wire.chat_block_rite", '"rite": "sel_block_rite"' in hl)
    check("wire.chat_gap", "rank_gap" in hl and "sel_gap_cp" in hl)
    check("wire.chat_rite_btn", 'lib_rite_' in hl and "start_hidden_rite" in hl)
    check("wire.chat_rite_cd", "sel_rite_cooldown" in hl)
    check("wire.mini_block_karma", "sel_mini_block_karma" in tj)
    check("wire.mini_rite_btn", "sel_mini_rite_btn" in tj and "startRite" in tj)
    check("wire.mini_rite_call", '"world/hidden_rite_start"' in tj)
    check("wire.mini_gap", "shelf.rank_gap" in tj and "sel_mini_gap_cp" in tj)
    check("wire.mini_rite_cd", "sel_mini_rite_cooldown" in tj)
    check("wire.mini_arena", "riteDuel" in tj and "DuelArenaModal" in tj)
    # `find` cru acharia a DEFINIÇÃO da função; queremos o call site do JSX.
    _i = tj.find("() => startRite(art)")
    check("wire.mini_btn_style", _i > 0 and "ActionBtn" in tj[max(0, _i - 400):_i],
          "botão da Prova usa ActionBtn — className='btn' não existe em folha servida")

    # a auto-documentação do painel (Lei §6) — sem as keys o painel mostra a crua
    for lang in ("pt", "en", "es"):
        mini = json.load(open(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"),
                              encoding="utf-8"))
        check(f"i18n.feature.{lang}", "feature_estantes_seladas" in mini
              and "feature_estantes_seladas_desc" in mini)
        desc = mini.get("feature_estantes_seladas_desc", "")
        check(f"i18n.feature_warn.{lang}", "LAUNCH-SERVER-BOUND" in desc, desc[:60])
        check(f"i18n.feature_dep.{lang}", "biblioteca_seitas" in desc,
              "a desc TEM de dizer a dependência")
        for knob in ("SEL_T4_CP", "SEL_T5_CP", "SEL_KARMA_MIN", "SEL_RITE_COOLDOWN_H"):
            check(f"i18n.knob.{lang}.{knob}", knob in desc,
                  "o painel se auto-documenta (Lei §6)")
        # os knobs citados na prosa TÊM de bater com os defaults reais do engine
        check(f"i18n.knob_value.{lang}", f"({lib.SEL_T4_CP})" in desc
              and f"({lib.SEL_KARMA_MIN})" in desc,
              "a desc mente se o default mudar e a prosa não")


def main() -> None:
    _off_blocks()
    _pure_blocks()

    _orig_bib, _orig_sel = lib.biblioteca_on, lib.selado_on
    lib.biblioteca_on = lambda *a, **k: True
    lib.selado_on = lambda *a, **k: True

    # O duelo real monta o fighter a partir do DB (artefatos, buffs, ...) — fora
    # do escopo de um teste SEM DB. Stub: provamos que o rito CHAMA o motor com
    # o `pve_source` e o contexto certos, que e o contrato do dispatcher.
    import core.duel_engine as de
    import core.world_pulse_engine as wpe
    _orig_start, _orig_chron = de.start_duel_pve, wpe.emit_chronicle

    async def _spy_start(session, player, **kw):
        DUEL_CALLS.append(kw)
        return D(id="new-duel", state="waiting_actions", resolved_at=None,
                 pve_context=kw.get("context") or {})

    async def _spy_chron(session, **kw):
        CHRON_CALLS.append(kw)
        return None

    de.start_duel_pve = _spy_start
    wpe.emit_chronicle = _spy_chron
    try:
        _on_blocks()
    finally:
        lib.biblioteca_on, lib.selado_on = _orig_bib, _orig_sel
        de.start_duel_pve, wpe.emit_chronicle = _orig_start, _orig_chron

    check("off.restored", lib.selado_on() is False and lib.library_tiers() == (1, 2, 3),
          "o teste devolveu o engine ao estado OFF")

    _seed_blocks()
    _wiring_blocks()

    print(f"\n{PASS} PASS · {len(FAILS)} FAIL")
    if FAILS:
        for f in FAILS:
            print(" ✗", f)
        sys.exit(1)
    print("All green — TEC-3 As Duas Estantes Seladas.")


if __name__ == "__main__":
    main()
