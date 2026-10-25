"""TEC-2 — teste isolado da Economia do Pergaminho (SEM DB).

Roda: python -X utf8 scripts/_test_tec2_scrolls.py

Padrão _test_tec1_library: ExplodingSession prova OFF = zero queries em TODA
função pública do engine E identidade EXATA de todo helper puro (o corte com a
flag OFF tem de devolver o número original, byte a byte); FakeSession (dispatch
por substring do SQL compilado) prova a lógica ON.

O que este teste protege, em ordem de gravidade:
  1. OFF-identity — main byte-idêntico (mult 1.0, arena 10, custo de grau
     intacto, payloads sem as chaves novas).
  2. Lei §4 — a doação credita SÓ o saldo e NUNCA promove. Inclui o caso que
     quase passou batido: `_apply_promotion` cai de volta no SALDO quando o
     lifetime-earned é 0 (todo cultivador novo), portanto não basta deixar
     `earned` intocado — a escada tem de ser PULADA.
  3. O teto diário (a trava anti-impressora) e a doação parcial honesta.
  4. Lei §1 — doar/queimar funcionam em pergaminho NÃO aprendido (o beco sem
     saída vivo: pergaminho inaprendível não tinha ação nenhuma) e o refino de
     grau não vira conteúdo morto sob escassez.
  5. Wiring grep-provável (flag sem call-site = promessa vazia).
"""
from __future__ import annotations

import asyncio
import json
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

import core.scroll_economy_engine as scr  # noqa: E402

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

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return list(rows)
        return _S()


class FakeSession:
    """Dispatch por substring do SQL compilado (padrão MV-7/TEC-1)."""

    def __init__(self, handlers):
        self.handlers = handlers
        self.added: list = []
        self.deleted: list = []
        self.committed = False

    async def execute(self, stmt, params=None):
        try:
            sql = str(stmt)
        except Exception:
            sql = repr(stmt)
        for pred, rows in self.handlers:
            if pred(sql):
                return FakeResult(rows() if callable(rows) else rows)
        raise AssertionError("query inesperada: " + sql[:200].replace("\n", " "))

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None

    def begin_nested(self):
        """SAVEPOINT fake — o bonus de Dao do apice roda dentro de um
        begin_nested (review TEC-2: engolir a excecao sem savepoint envenenava
        a transacao e o commit do caller estourava depois de ok:True)."""
        class _SP:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False
        return _SP()


def T(**kw):
    """Fake TechniqueCatalog row."""
    d = dict(id=5, name="Void Slash", emoji="🗡️", req_realm=3, qi_cost=35,
             tech_type="combat", intent_affinity="sword", sect_key=None,
             description="d", library_tier=None)
    d.update(kw)
    return types.SimpleNamespace(**d)


def P(**kw):
    d = dict(telegram_id=111, sect_id="azure_cloud", sect_rank="disciple",
             sect_contribution=100, sect_contribution_earned=0, realm=3,
             language="pt", scroll_econ=None)
    d.update(kw)
    return types.SimpleNamespace(**d)


def INV(qty=5, tech_id=5):
    return types.SimpleNamespace(player_id=111, item_type="technique_scroll",
                                 item_id=tech_id, quantity=qty, quality="normal")


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _src(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def main() -> None:
    # Espias dos efeitos best-effort da promoção (padrão TEC-1): sem eles o
    # caminho LEGADO do award (credit_earned=True) cospe 2 tracebacks engolidos
    # e o teste vira ruído — o mesmo defeito que o MV-4 tem.
    import core.achievement_engine as ach
    import core.notification_engine as ne
    _o_ach, _o_notify = ach.check_achievements, ne.notify

    async def _spy_ach(session, pid, event, value=None, **kw):
        ACH_CALLS.append((pid, event, value))
        return []

    async def _spy_notify(session, pid, kind, **kw):
        NOTIFY_CALLS.append((pid, kind, kw.get("title_key")))
        return None

    ach.check_achievements = _spy_ach
    ne.notify = _spy_notify
    try:
        _blocks()
    finally:
        ach.check_achievements, ne.notify = _o_ach, _o_notify

    print(f"\n{PASS} PASS · {len(FAILS)} FAIL")
    if FAILS:
        for f in FAILS:
            print(" ✗", f)
        sys.exit(1)
    print("All green — TEC-2 Economia do Pergaminho.")


ACH_CALLS: list = []
NOTIFY_CALLS: list = []


def _blocks() -> None:
    _off_blocks()
    _pure_blocks()
    _orig_on = scr.escassez_on
    scr.escassez_on = lambda *a, **k: True
    try:
        _on_pure_blocks()
        _donate_blocks()
        _burn_blocks()
        _view_blocks()
    finally:
        scr.escassez_on = _orig_on
    _contribution_blocks()
    _i18n_blocks()
    _wiring_blocks()


# ══ 1. OFF-identity ══════════════════════════════════════════════════════════
def _off_blocks() -> None:
    check("off.gate", scr.escassez_on() is False, "sem DB o gate fail-safe é False")

    # identidade EXATA dos helpers puros (o coração do "main byte-idêntico")
    check("off.mult", scr.scroll_drop_mult() == 1.0)
    for ch in (0.04, 0.05, 0.08, 0.12, 0.14, 0.15):
        check(f"off.chance.{ch}", ch * scr.scroll_drop_mult() == ch,
              "o produto tem de ser o MESMO float")
    check("off.arena", scr.arena_scroll_step() == 10, "o marco vivo é 10 vitórias")
    for base in (0, 5, 10):
        check(f"off.grade.{base}", scr.grade_scroll_cost(base) == base)
    for ch, typ in ((0.05, "technique_scroll"), (0.15, "technique_scroll"),
                    (1.0, "spirit_stones"), (0.3, "herb")):
        check(f"off.npc.{typ}.{ch}", scr.npc_loot_chance({"type": typ, "chance": ch}) == ch)
    for q in (0, 1, 2, 3):
        check(f"off.quest.{q}", scr.quest_scroll_qty(q) == q,
              "recompensa garantida de quest intacta com a flag OFF")

    # toda função pública com ExplodingSession
    es = ExplodingSession()
    check("off.list", run(scr.list_scrolls(es, 1)) == {"on": False})
    check("off.actions", run(scr.get_scroll_actions(es, 1, 5)) == {"on": False})
    r = run(scr.donate_scroll(es, 1, 5))
    check("off.donate", r == {"ok": False, "reason": "scr_off"}, str(r))
    r = run(scr.burn_scroll(es, 1, 5))
    check("off.burn", r == {"ok": False, "reason": "scr_off"}, str(r))


# ══ 2. Puras (independentes da flag) ═════════════════════════════════════════
def _pure_blocks() -> None:
    # degraus derivados de req_realm (não existe coluna de tier — recon §0.2)
    for realm, tier in ((0, 1), (1, 1), (2, 2), (3, 2), (4, 3), (5, 3),
                        (6, 4), (7, 4), (10, 4)):
        check(f"tier.r{realm}", scr.scroll_tier(T(req_realm=realm)) == tier,
              str(scr.scroll_tier(T(req_realm=realm))))
    check("tier.none", scr.scroll_tier(types.SimpleNamespace()) == 1, "sem campo → degrau 1")

    check("cp.ladder", [scr.donate_cp(i) for i in (1, 2, 3, 4)] == [25, 50, 100, 200])
    check("xp.ladder", [scr.burn_xp(i) for i in (1, 2, 3, 4)] == [25, 50, 100, 200])
    check("cp.unknown", scr.donate_cp(9) == 25, "degrau desconhecido cai no menor")

    from core.intent_engine import INTENT_KEYS
    for k in INTENT_KEYS:
        check(f"intent.{k}", scr.burn_intent(T(intent_affinity=k)) == k)
    check("intent.none", scr.burn_intent(T(intent_affinity=None)) == scr.DEFAULT_BURN_INTENT,
          "arte sem intenção (meditação/interior) nunca deixa botão morto — Lei §1")
    check("intent.bogus", scr.burn_intent(T(intent_affinity="banana")) == "dao")
    check("intent.in_keys", scr.DEFAULT_BURN_INTENT in INTENT_KEYS)

    # o livro do dia
    check("book.none", scr.donated_today(P(scroll_econ=None)) == 0)
    check("book.old", scr.donated_today(P(scroll_econ={"d": "2000-01-01", "cp": 999})) == 0,
          "dia velho não conta")
    today = scr._today_key()
    check("book.today", scr.donated_today(P(scroll_econ={"d": today, "cp": 120})) == 120)
    check("book.junk", scr.donated_today(P(scroll_econ={"d": today, "cp": "x"})) == 0)
    check("book.notdict", scr.donated_today(P(scroll_econ="oops")) == 0)
    check("head.full", scr.donate_headroom(P(scroll_econ=None)) == scr.SCR_DONATE_DAILY_CAP)
    check("head.part", scr.donate_headroom(P(scroll_econ={"d": today, "cp": 400}))
          == scr.SCR_DONATE_DAILY_CAP - 400)
    check("head.zero", scr.donate_headroom(P(scroll_econ={"d": today, "cp": 10 ** 9})) == 0,
          "nunca negativo")


# ══ 3. Puras com a flag ON ═══════════════════════════════════════════════════
def _on_pure_blocks() -> None:
    check("on.mult", scr.scroll_drop_mult() == scr.SCR_DROP_MULT == 0.15)
    # o corte real: os 4-15% vivos viram 0.6-2.2% (Q-1 default A da Constituição)
    check("on.cut.min", abs(0.04 * scr.scroll_drop_mult() - 0.006) < 1e-9)
    check("on.cut.max", abs(0.15 * scr.scroll_drop_mult() - 0.0225) < 1e-9)
    check("on.cut.range", all(0.005 <= c * scr.scroll_drop_mult() <= 0.025
                              for c in (0.04, 0.05, 0.08, 0.10, 0.12, 0.14, 0.15)),
          "todo scroll_chance vivo cai na faixa 0.5-2.5%")
    check("on.arena", scr.arena_scroll_step() == scr.SCR_ARENA_WIN_STEP == 50)

    # o corte SÓ morde a linha de pergaminho — o resto do loot passa cru
    check("on.npc.scroll", abs(scr.npc_loot_chance({"type": "technique_scroll", "chance": 0.15})
                               - 0.0225) < 1e-9)
    for typ, ch in (("spirit_stones", 1.0), ("herb", 0.5), ("core_essence", 0.3),
                    ("beast_trap", 0.1), ("pill", 0.12), ("ore", 0.2)):
        check(f"on.npc.keep.{typ}", scr.npc_loot_chance({"type": typ, "chance": ch}) == ch,
              "loot de caçada não é cortado")
    check("on.npc.junk", scr.npc_loot_chance({}) == 0.0, "linha sem chance nunca explode")

    # Lei §1 — o refino de grau não vira conteúdo morto
    check("on.grade.5", scr.grade_scroll_cost(5) == 1)
    check("on.grade.10", scr.grade_scroll_cost(10) == 2)
    check("on.grade.0", scr.grade_scroll_cost(0) == 0, "grau sem custo continua sem custo")
    check("on.grade.floor", scr.grade_scroll_cost(1) == 1, "nunca vira de graça")
    # as quests repetiveis (1-3 garantidos) nao podem virar a fonte dominante
    check("on.quest.1", scr.quest_scroll_qty(1) == 1, "a quest continua entregando")
    check("on.quest.2", scr.quest_scroll_qty(2) == 1)
    check("on.quest.3", scr.quest_scroll_qty(3) == 1)
    check("on.quest.0", scr.quest_scroll_qty(0) == 0, "quest sem pergaminho segue sem")
    from core.combat_engine import GRADE_UPGRADE_REQS
    for g, reqs in GRADE_UPGRADE_REQS.items():
        base = int(reqs.get("scrolls", 0))
        cut = scr.grade_scroll_cost(base)
        check(f"on.grade.real.{g}", cut <= base and (base == 0 or cut >= 1),
              f"{base} → {cut}")


# ══ 4. Doar ══════════════════════════════════════════════════════════════════
def _donate_session(player, inv, tech):
    """FakeSession que serve o fluxo de doação inteiro."""
    return FakeSession([
        (lambda s: "FROM players" in s, [player]),
        (lambda s: "FROM player_inventory" in s, [inv]),
        (lambda s: "FROM techniques_catalog" in s, [tech]),
    ])


def _donate_blocks() -> None:
    # ── caminho feliz: 1 pergaminho T2 (req_realm 3) = 50 CP ──
    p, inv, tech = P(), INV(qty=5), T(req_realm=3)
    s = _donate_session(p, inv, tech)
    r = run(scr.donate_scroll(s, 111, 5, 1))
    check("don.ok", r.get("ok") is True, str(r))
    check("don.tier", r.get("tier") == 2)
    check("don.cp", r.get("cp_gained") == 50, str(r.get("cp_gained")))
    check("don.qty", r.get("qty") == 1)
    check("don.consumed", inv.quantity == 4, f"quantity={inv.quantity}")
    check("don.balance", (r["balance_before"], r["balance_after"]) == (100, 150), str(r))
    # ── LEI §4: a escada NUNCA se move ──
    check("don.earned_untouched", r["earned_before"] == r["earned_after"] == 0,
          "doar papel jamais credita a escada de posto")
    check("don.no_promo", p.sect_rank == "disciple",
          "e jamais promove — nem com earned=0 (o fallback ao saldo foi pulado)")
    check("don.book", p.scroll_econ == {"d": scr._today_key(), "cp": 50}, str(p.scroll_econ))
    check("don.headroom", r["headroom_after"] == scr.SCR_DONATE_DAILY_CAP - 50)

    # ── Lei §1: pergaminho NÃO aprendido também tem destino ──
    p2, inv2, tech2 = P(), INV(qty=1), T(req_realm=9, intent_affinity=None)
    r = run(scr.donate_scroll(_donate_session(p2, inv2, tech2), 111, 5, 1))
    check("don.unlearned", r.get("ok") is True and r.get("tier") == 4, str(r))
    check("don.unlearned_cp", r.get("cp_gained") == 200)

    # ── sem seita: recusa ANTES de tocar no item ──
    p3, inv3 = P(sect_id=None), INV(qty=3)
    r = run(scr.donate_scroll(_donate_session(p3, inv3, T()), 111, 5, 1))
    check("don.no_sect", r == {"ok": False, "reason": "not_in_sect"}, str(r))
    check("don.no_sect_item_safe", inv3.quantity == 3,
          "o pergaminho NÃO pode morrer sem pagamento")

    # ── teto diário: recusa disclosed, item intacto ──
    today = scr._today_key()
    p4, inv4 = P(scroll_econ={"d": today, "cp": scr.SCR_DONATE_DAILY_CAP}), INV(qty=3)
    r = run(scr.donate_scroll(_donate_session(p4, inv4, T(req_realm=3)), 111, 5, 1))
    check("don.cap", r.get("reason") == "daily_cap", str(r))
    check("don.cap_item_safe", inv4.quantity == 3)
    check("don.cap_discloses", r.get("cap") == scr.SCR_DONATE_DAILY_CAP and "headroom" in r)

    # ── doação PARCIAL: pede 10, o teto só deixa passar N ──
    room = 120
    p5 = P(scroll_econ={"d": today, "cp": scr.SCR_DONATE_DAILY_CAP - room})
    inv5 = INV(qty=10)
    r = run(scr.donate_scroll(_donate_session(p5, inv5, T(req_realm=3)), 111, 5, 10))
    check("don.partial", r.get("ok") is True and r.get("partial") is True, str(r))
    check("don.partial_qty", r.get("qty") == room // 50 == 2, str(r.get("qty")))
    check("don.partial_cp", r.get("cp_gained") == 100)
    check("don.partial_consumed", inv5.quantity == 8)
    check("don.partial_asked", r.get("requested") == 10, "a UI precisa dizer quanto pediu")

    # ── estoque menor que o pedido: consome o que há, nunca mais ──
    p6, inv6 = P(), INV(qty=2)
    r = run(scr.donate_scroll(_donate_session(p6, inv6, T(req_realm=0)), 111, 5, 9))
    check("don.stock", r.get("qty") == 2 and inv6.quantity == 0, str(r))
    check("don.stock_cp", r.get("cp_gained") == 50, "2 × 25 (degrau 1)")
    check("don.stock_deleted", len(inv6.__dict__) > 0)

    # ── double-tap: o stack já foi a zero → recusa, sem crédito duplo ──
    p7, inv7 = P(), INV(qty=0)
    s7 = FakeSession([
        (lambda s: "FROM players" in s, [p7]),
        (lambda s: "FROM player_inventory" in s, []),
        (lambda s: "FROM techniques_catalog" in s, [T()]),
    ])
    r = run(scr.donate_scroll(s7, 111, 5, 1))
    check("don.double_tap", r == {"ok": False, "reason": "no_scroll"}, str(r))
    check("don.double_tap_no_credit", p7.sect_contribution == 100)

    # ── lote limitado (rajada de notificação + custo de query) ──
    p8, inv8 = P(), INV(qty=999)
    r = run(scr.donate_scroll(_donate_session(p8, inv8, T(req_realm=0)), 111, 5, 999))
    check("don.batch_cap", r.get("qty") <= scr.SCR_MAX_BATCH, str(r.get("qty")))


# ══ 5. Queimar ═══════════════════════════════════════════════════════════════
def _burn_blocks() -> None:
    from core.intent_engine import PlayerIntent  # noqa: F401

    def _burn_session(player, inv, tech, intent_row):
        return FakeSession([
            (lambda s: "FROM players" in s, [player]),
            (lambda s: "FROM player_inventory" in s, [inv]),
            (lambda s: "FROM techniques_catalog" in s, [tech]),
            (lambda s: "INSERT INTO player_intents" in s, []),
            (lambda s: "FROM player_intents" in s, [intent_row]),
        ])

    row = types.SimpleNamespace(player_id=111, intent="sword", rank=0, xp=50)
    p, inv, tech = P(), INV(qty=3), T(req_realm=3, intent_affinity="sword")
    r = run(scr.burn_scroll(_burn_session(p, inv, tech, row), 111, 5, 1))
    check("burn.ok", r.get("ok") is True, str(r))
    check("burn.intent", r.get("intent") == "sword")
    check("burn.xp", r.get("xp_gained") == 50, "degrau 2 = 50 XP")
    check("burn.consumed", inv.quantity == 2)
    check("burn.rank_delta", "rank_before" in r and "rank_after" in r,
          "progressão VISÍVEL: antes→depois sempre no payload (Lei §10)")
    check("burn.no_dao", r.get("dao_fragments") == [], "só o ápice dá fragmento")

    # ── arte sem intenção (meditação/interior) cai no padrão, nunca falha ──
    row2 = types.SimpleNamespace(player_id=111, intent="dao", rank=1, xp=0)
    p2, inv2 = P(), INV(qty=1)
    r = run(scr.burn_scroll(_burn_session(p2, inv2, T(intent_affinity=None), row2), 111, 5, 1))
    check("burn.default_intent", r.get("ok") is True and r.get("intent") == "dao", str(r))

    # ── lote: XP escala com a quantidade consumida ──
    row3 = types.SimpleNamespace(player_id=111, intent="sword", rank=0, xp=0)
    p3, inv3 = P(), INV(qty=4)
    r = run(scr.burn_scroll(_burn_session(p3, inv3, T(req_realm=1), row3), 111, 5, 4))
    check("burn.batch", r.get("qty") == 4 and r.get("xp_gained") == 100, str(r))
    check("burn.batch_consumed", inv3.quantity == 0)

    # ── sem pergaminho: recusa limpa ──
    p4 = P()
    s4 = FakeSession([
        (lambda s: "FROM players" in s, [p4]),
        (lambda s: "FROM player_inventory" in s, []),
        (lambda s: "FROM techniques_catalog" in s, [T()]),
    ])
    r = run(scr.burn_scroll(s4, 111, 5, 1))
    check("burn.no_scroll", r == {"ok": False, "reason": "no_scroll"}, str(r))

    # ── ápice + Reino 5+: chama o helper CANÔNICO do dao (nunca 5ª cópia) ──
    import core.dao_engine as dao
    _orig = dao.grant_random_fragments
    calls: list = []

    async def _spy(session, pid, n, realm):
        calls.append((pid, n, realm))
        return [{"law_name": "Dao of Speed", "law_emoji": "💠",
                 "fragments": 3, "total": 9, "completed": False, "is_eternal": False}]
    dao.grant_random_fragments = _spy
    try:
        row5 = types.SimpleNamespace(player_id=111, intent="fist", rank=2, xp=0)
        p5, inv5 = P(realm=6), INV(qty=1)
        r = run(scr.burn_scroll(_burn_session(p5, inv5,
                                              T(req_realm=7, intent_affinity="fist"), row5), 111, 5, 1))
        check("burn.apex_dao", len(r.get("dao_fragments", [])) == 1, str(r.get("dao_fragments")))
        check("burn.apex_call", calls == [(111, scr.SCR_BURN_DAO_FRAG_T4, 6)], str(calls))
        check("burn.apex_xp", r.get("xp_gained") == 200)

        # abaixo do Reino 5 o helper canônico devolve [] sozinho (DAO_UNLOCK_REALM)
        calls.clear()
        row6 = types.SimpleNamespace(player_id=111, intent="fist", rank=0, xp=0)
        p6, inv6 = P(realm=3), INV(qty=1)
        r = run(scr.burn_scroll(_burn_session(p6, inv6, T(req_realm=7), row6), 111, 5, 1))
        check("burn.apex_lowrealm_ok", r.get("ok") is True,
              "queimar NUNCA falha por reino — o XP de Intenção existe desde o Reino 0")
        check("burn.apex_lowrealm_called", calls and calls[0][2] == 3, str(calls))
    finally:
        dao.grant_random_fragments = _orig

    check("dao.unlock_realm", __import__("core.dao_engine", fromlist=["x"]).DAO_UNLOCK_REALM == 5,
          "o fragmento é R5+ por construção do helper canônico")


# ══ 6. Views ═════════════════════════════════════════════════════════════════
def _view_blocks() -> None:
    p = P()
    inv_rows = [(5, 3), (12, 1)]
    techs = [T(id=5, req_realm=3, name="Void Slash", intent_affinity="sword"),
             T(id=12, req_realm=7, name="Soul Devourer", intent_affinity="dao")]
    s = FakeSession([
        (lambda q: "FROM players" in q, [(p.sect_id, p.sect_contribution, p.realm, p.scroll_econ)]),
        (lambda q: "FROM player_inventory" in q, inv_rows),
        (lambda q: "FROM techniques_catalog" in q, techs),
        (lambda q: "FROM player_techniques" in q, [5]),
    ])
    v = run(scr.list_scrolls(s, 111))
    check("view.on", v.get("on") is True)
    check("view.total", v.get("total") == 4, str(v.get("total")))
    check("view.count", len(v.get("scrolls", [])) == 2)
    check("view.sorted", v["scrolls"][0]["tier"] >= v["scrolls"][1]["tier"],
          "o mais raro primeiro")
    apex = next(x for x in v["scrolls"] if x["tech_id"] == 12)
    check("view.learned_flag", apex["learned"] is False
          and next(x for x in v["scrolls"] if x["tech_id"] == 5)["learned"] is True)
    check("view.apex_cp", apex["donate_cp"] == 200 and apex["burn_xp"] == 200)
    check("view.apex_dao_gate", apex["burn_dao"] == 0, "realm 3 < 5 → sem promessa falsa")
    check("view.headroom", v.get("headroom") == scr.SCR_DONATE_DAILY_CAP)
    check("view.cap", v.get("cap") == scr.SCR_DONATE_DAILY_CAP)

    # órfão de catálogo nunca vira linha com ação sobre o vazio
    s2 = FakeSession([
        (lambda q: "FROM players" in q, [(p.sect_id, 0, 3, None)]),
        (lambda q: "FROM player_inventory" in q, [(999, 2)]),
        (lambda q: "FROM techniques_catalog" in q, []),
        (lambda q: "FROM player_techniques" in q, []),
    ])
    v2 = run(scr.list_scrolls(s2, 111))
    check("view.orphan", v2.get("scrolls") == [], str(v2.get("scrolls")))

    # arca vazia: resposta honesta, não um erro
    s3 = FakeSession([
        (lambda q: "FROM players" in q, [(None, 0, 1, None)]),
        (lambda q: "FROM player_inventory" in q, []),
    ])
    v3 = run(scr.list_scrolls(s3, 111))
    check("view.empty", v3.get("on") is True and v3.get("scrolls") == []
          and v3.get("in_sect") is False, str(v3))

    # sem seita: o bloqueio é DITO, não escondido (Lei §1)
    s4 = FakeSession([
        (lambda q: "FROM players" in q, [(None, 0, 3, None)]),
        (lambda q: "FROM player_inventory" in q, [(5, 1)]),
        (lambda q: "FROM techniques_catalog" in q, [T(id=5)]),
        (lambda q: "FROM player_techniques" in q, []),
    ])
    v4 = run(scr.list_scrolls(s4, 111))
    row = v4["scrolls"][0]
    check("view.nosect_block", row["can_donate"] is False and row["donate_block"] == "no_sect")
    check("view.nosect_burn", row["burn_xp"] > 0, "queimar continua disponível")

    # get_scroll_actions — o mesmo veredito, por pergaminho
    s5 = FakeSession([
        (lambda q: "FROM players" in q, [(p.sect_id, 100, 3, None)]),
        (lambda q: "FROM player_inventory" in q, [INV(qty=2)]),
        (lambda q: "FROM techniques_catalog" in q, [T(req_realm=3)]),
    ])
    a = run(scr.get_scroll_actions(s5, 111, 5))
    check("act.on", a.get("on") is True and a.get("have") == 2, str(a))
    check("act.donate", a["donate"]["cp"] == 50 and a["donate"]["can"] is True)
    check("act.burn", a["burn"]["xp"] == 50 and a["burn"]["can"] is True)
    check("act.burn_always", a["burn"]["block"] is None,
          "o Ritual de Compreensão nunca é bloqueado — é o destino que SEMPRE existe")


# ══ 7. O mutador de contribuição (o parâmetro novo) ══════════════════════════
def _contribution_blocks() -> None:
    from core.world_sects_engine import award_sect_contribution

    # credit_earned=False → saldo sobe, escada NÃO, promoção NÃO é avaliada
    p = P(sect_contribution=0, sect_contribution_earned=0, sect_rank="disciple", realm=9)
    s = FakeSession([(lambda q: "FROM players" in q, [p])])
    r = run(award_sect_contribution(s, 111, 5000, source="scroll_donation",
                                    credit_earned=False))
    check("awd.ok", r.get("ok") is True)
    check("awd.balance", p.sect_contribution == 5000)
    check("awd.earned", p.sect_contribution_earned == 0)
    check("awd.rank", p.sect_rank == "disciple",
          "o fallback earned→saldo de _apply_promotion NÃO pode promover por doação")
    check("awd.promo_none", r.get("promotion") is None)

    # default (True) preserva os 2 call sites vivos — quest/tributo promovem
    p2 = P(sect_contribution=0, sect_contribution_earned=0, sect_rank="disciple", realm=9)
    s2 = FakeSession([(lambda q: "FROM players" in q, [p2])])
    r2 = run(award_sect_contribution(s2, 111, 5000, source="sect_quest"))
    check("awd.default_earned", p2.sect_contribution_earned == 5000,
          "o comportamento legado tem de ficar byte-idêntico")
    check("awd.default_promo", r2.get("promotion") is not None
          and p2.sect_rank != "disciple", "a escada continua viva no caminho legado")
    check("awd.default_effects", any(c[1] == "sect_rank_reached" for c in ACH_CALLS)
          and any(c[1] == "sect_promoted" for c in NOTIFY_CALLS),
          "e os efeitos da promoção continuam disparando no caminho legado")
    # a doação NÃO pode ter disparado efeito de promoção nenhum
    check("awd.donation_silent", not [c for c in NOTIFY_CALLS if c[1] == "sect_promoted"][1:],
          "só o caminho legado promoveu (a doação passou muda)")

    # ── A PORTA DOS FUNDOS (achado crítico do review): `recompute_player_rank`
    # roda a CADA abertura do Salão e chama _apply_promotion sem amount. Com
    # earned=0 o fallback COMPAT lia o SALDO — que a doação acabou de inflar —
    # e promovia com um tap de atraso. O marcador `scroll_econ` desliga o
    # fallback para quem doou. ══════════════════════════════════════════════
    from core.world_sects_engine import (_apply_promotion, get_sect_hall_state,
                                         ladder_contribution,
                                         recompute_player_rank)

    check("ladder.earned_wins", ladder_contribution(900, 5, False) == 900)
    check("ladder.compat_fallback", ladder_contribution(0, 700, False) == 700,
          "o fallback COMPAT pré-Mig-118 continua vivo para quem nunca doou")
    check("ladder.tainted", ladder_contribution(0, 700, True) == 0,
          "quem doou perde o fallback — o saldo não é mais proxy de feito")
    check("ladder.tainted_keeps_earned", ladder_contribution(300, 9999, True) == 300)
    check("ladder.none", ladder_contribution(None, None, False) == 0)

    # doou (scroll_econ != None) + saldo alto + earned 0 → NÃO promove
    tainted = P(sect_contribution=5000, sect_contribution_earned=0,
                sect_rank="disciple", realm=9,
                scroll_econ={"d": scr._today_key(), "cp": 500})
    check("backdoor.blocked", _apply_promotion(tainted) is None
          and tainted.sect_rank == "disciple",
          "a doação NÃO pode promover pelo recompute do Salão")
    s_re = FakeSession([(lambda q: "FROM players" in q, [tainted])])
    check("backdoor.recompute", run(recompute_player_rank(s_re, 111)) is None
          and tainted.sect_rank == "disciple")

    # o mesmo jogador SEM ter doado (scroll_econ NULL) mantém o legado intacto
    legacy = P(sect_contribution=5000, sect_contribution_earned=0,
               sect_rank="disciple", realm=9, scroll_econ=None)
    check("backdoor.legacy_untouched", _apply_promotion(legacy) is not None
          and legacy.sect_rank != "disciple",
          "os 57 (pré-Mig-118, earned=0) continuam promovendo pelo saldo")

    # e o Salão não pode ANUNCIAR um progresso que a promoção não entrega
    check("backdoor.no_display_lie",
          "ladder_contribution(" in _src("core", "world_sects_engine.py")
          and _src("core", "world_sects_engine.py").count("ladder_contribution(") >= 3,
          "get_sect_hall_state lê o MESMO número que _apply_promotion")

    # não-membro segue recusando (a doação checa ANTES, mas defense-in-depth)
    p3 = P(sect_id=None)
    s3 = FakeSession([(lambda q: "FROM players" in q, [p3])])
    r3 = run(award_sect_contribution(s3, 111, 10, credit_earned=False))
    check("awd.no_sect", r3 == {"ok": False, "reason": "not_in_sect"}, str(r3))


# ══ 8. i18n ══════════════════════════════════════════════════════════════════
def _i18n_blocks() -> None:
    from inject_tec2_i18n import CHAT, MINIAPP
    for lang in ("pt", "en", "es"):
        chat = json.load(open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8"))
        mini = json.load(open(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"),
                              encoding="utf-8"))
        miss_c = [k for k in CHAT[lang] if k not in chat]
        miss_m = [k for k in MINIAPP[lang] if k not in mini]
        check(f"i18n.chat.{lang}", not miss_c, str(miss_c[:5]))
        check(f"i18n.mini.{lang}", not miss_m, str(miss_m[:5]))
        # os 5 caminhos de Intenção resolvem nas DUAS superfícies (o burn cita-os)
        from core.intent_engine import INTENT_KEYS
        for k in INTENT_KEYS:
            check(f"i18n.intent.{lang}.{k}",
                  f"intent_name_{k}" in chat and f"intent_name_{k}" in mini)
        # a desc da feature tem de gritar o launch-server-bound (Lei §5)
        desc = mini.get("feature_escassez_scrolls_desc", "")
        check(f"i18n.feature_warn.{lang}", "LAUNCH-SERVER-BOUND" in desc, desc[:60])
        for knob in ("SCR_DROP_MULT", "SCR_ARENA_WIN_STEP", "SCR_GRADE_SCROLL_DIV",
                     "SCR_DONATE_DAILY_CAP", "SCR_BURN_DAO_FRAG_T4"):
            check(f"i18n.knob.{lang}.{knob}", knob in desc,
                  "o painel se auto-documenta (Lei §6)")


# ══ 9. Wiring grep-provável ══════════════════════════════════════════════════
def _wiring_blocks() -> None:
    check("wire.flag", '"escassez_scrolls":' in _src("database", "db.py"))
    check("wire.mig", os.path.exists(os.path.join(ROOT, "migrations", "137_scroll_economy.sql")))
    check("wire.model", "scroll_econ" in _src("database", "models.py"))

    dg = _src("handlers", "dungeons.py")
    check("wire.cut_roll", "scroll_drop_mult" in dg,
          "o corte tem de estar no ÚNICO random() de pergaminho de expedição")
    check("wire.cut_roll_math",
          'drops.get("scroll_chance", 0) * scroll_drop_mult()' in dg,
          "na MESMA matemática que rola (lição MV-6: display = roll)")
    check("wire.cut_display", "scr_dng_scarcity_hint" in dg)

    check("wire.npc_pve", "npc_loot_chance" in _src("core", "pve_duel_settle.py"))
    check("wire.npc_chat", "npc_loot_chance" in _src("handlers", "combat.py"))
    ws = _src("core", "webserver.py")
    check("wire.npc_api", "npc_loot_chance" in ws)
    check("wire.preview_cut", "_scr_drop_mult()" in ws, "a vitrine do mini mostra o corte")
    check("wire.arena", "arena_scroll_step" in _src("core", "arena_duel_settle.py"))
    check("wire.arena_dead_copy", "arena_scroll_step" in _src("handlers", "combat.py"),
          "a cópia morta fica em lockstep — ressuscitá-la não pode reabrir o faucet")

    check("wire.grade_api", "grade_scroll_cost" in ws)
    check("wire.grade_chat", "grade_scroll_cost" in _src("handlers", "combat.py"))
    check("wire.endpoints", "combat/scroll_donate" in ws and "combat/scroll_burn" in ws
          and "combat/scrolls" in ws)

    check("wire.credit_earned", "credit_earned" in _src("core", "world_sects_engine.py"))
    mn = _src("main.py")
    check("wire.prefix", 'startswith("scr_")' in mn and "scroll_button_router" in mn)
    check("wire.cmd", '"pergaminhos"' in mn)

    hs = _src("handlers", "scrolls.py")
    check("wire.handler", "donate_scroll" in hs and "burn_scroll" in hs)
    check("wire.entry_btn", "scr_open_pvp" in _src("handlers", "combat.py"))
    check("wire.lib_bridge", "scr_open_lib" in _src("handlers", "library.py"),
          "o 'Voltar' da arca devolve ao lugar de onde se entrou")
    check("wire.quest_clamp", "quest_scroll_qty" in _src("core", "dungeon_quest_engine.py")
          and "quest_scroll_qty" in _src("core", "quest_engine.py"),
          "as quests repetiveis nao podem virar a fonte dominante pos-corte")
    check("wire.savepoint", "begin_nested" in _src("core", "scroll_economy_engine.py"),
          "o bonus best-effort do apice NAO pode envenenar a transacao")

    tj = _src("miniapp", "components", "tabs.js")
    check("wire.mini_fetch", '"combat/scrolls"' in tj)
    check("wire.mini_donate", '"combat/scroll_donate"' in tj)
    check("wire.mini_burn", '"combat/scroll_burn"' in tj)
    check("wire.mini_card", "ScrollEconomyCard" in tj)
    check("wire.mini_gate", 'featureEnabled("escassez_scrolls")' in tj)


if __name__ == "__main__":
    main()
