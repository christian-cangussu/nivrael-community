"""QoL-Feedback 2026-07-29 — teste isolado do lote dos 4 reports (SEM DB).

Roda: python -X utf8 scripts/_test_qol_feedback.py

Padrão _test_qol_relatos: FakeSession (dispatch por substring do SQL compilado)
prova a lógica; wiring grep-provável (helper novo sem call-site = promessa
vazia); i18n do lote presente ×3 ×2 com placeholders coerentes.

O que este teste protege, em ordem de gravidade:
  1. **Item A — o display nunca mais mente "Pureza +0".** `purity_gain` é a
     UMA verdade (o apply a chama — provado por grep) e o preview compõe por
     ela. Para TODA pílula purity/essence viva nas SEEDS (lição QoL-relatos: o
     teto vem das seeds, não do engine) o preview é > 0 em TODAS as
     qualidades × fundações. E a escala usa buff_potency (1.3/1.6/2.2), não
     a potency de display (1.5/3/5) — o erro original era exatamente esse.
  2. **Item C — o claim sem facção DIZ o que se perdeu (Lei §1).** O engine
     devolve `reputation_missed` como chave CONDICIONAL (com facção ela não
     existe — payload-shape intacto para quem tem facção), e as 3 pontas
     (chat/API/mini) leem e rotulam a moeda como facção (🔱).
  3. **Item D — o feed espelha o chat.** Engine: sem núcleo = None; feed
     consome 1, +20 XP, level-up no limiar exato. Endpoint: gate de realm
     ANTES do engine + row-lock + rota registrada. Mini: botão + contagem +
     toast antes→depois.
  4. **Item B — o refetch de verdade.** `reloadKey` viaja CombatTab →
     CombatLoadoutPanel → ScrollEconomyCard e é a dep do useEffect (deps []
     era o bug). Grade-up devolve old_grade e as 2 superfícies mostram
     antes→depois por keys NOVAS (as antigas ficam de fallback — só-adições).
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
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# core.alchemy_engine importa core.utils → telegram. A lib não existe na
# máquina local (só no VPS) e o teste é SEM rede/DB por contrato — um stub
# mínimo satisfaz o import; nada de telegram é EXERCIDO por estes asserts.
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

import core.alchemy_engine as alch  # noqa: E402
import core.dungeon_quest_engine as dqe  # noqa: E402
from database.seeds.alchemy_seeds import PILLS  # noqa: E402

PASS = 0
FAILS: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


# ── Fakes (padrão _test_qol_relatos) ───────────────────────────────────────────────
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
            def first(self):
                return rows[0] if rows else None

            def all(self):
                return list(rows)
        return _S()


class FakeSession:
    def __init__(self, handlers):
        self.handlers = handlers
        self.added: list = []
        self.deleted: list = []
        self.committed = False
        self.seen_sql: list[str] = []

    async def execute(self, stmt, params=None):
        try:
            sql = str(stmt)
        except Exception:
            sql = repr(stmt)
        self.seen_sql.append(sql)
        for pred, rows in self.handlers:
            if pred(sql):
                return FakeResult(rows() if callable(rows) else rows)
        raise AssertionError("query inesperada: " + sql[:200].replace("\n", " "))

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        return None


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _src(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


QUALITIES = ("normal", "perfect", "divine", "heavenly")
FOUNDATIONS = (None, "low", "medium", "high", "perfect", "sacred")


# ══════════════════════════════════════════════════════════════════════════
# Item A — purity_gain: a UMA verdade, e o preview nunca mais 0
# ══════════════════════════════════════════════════════════════════════════
def item_a_pure() -> None:
    g = alch.purity_gain
    # O caso do report: Cleansing Pill (0.05) normal/low → 500, não 0.
    check("a.report_relato", g(0.05, "normal", 1.0, "low") == 500,
          str(g(0.05, "normal", 1.0, "low")))
    # Escala por QUALIDADE usa buff_potency (o preview antigo usava a potency
    # de display — o dobro do erro).
    check("a.q_perfect", g(0.05, "perfect", 1.0, "low") == 650)     # ×1.3
    check("a.q_divine", g(0.05, "divine", 1.0, "low") == 800)       # ×1.6
    check("a.q_heavenly", g(0.05, "heavenly", 1.0, "low") == 1100)  # ×2.2
    # Fundação: perfect ×3, sacred == perfect (o BUGFIX 2026-07-07 preservado),
    # None (sem fundação) → 1.0.
    check("a.fq_perfect", g(0.05, "normal", 1.0, "perfect") == 1500)
    check("a.fq_sacred", g(0.05, "normal", 1.0, "sacred") == 1500)
    check("a.fq_none", g(0.05, "normal", 1.0, None) == 500)
    # Resistência e facção entram no MESMO número (preview == roll).
    check("a.eff", g(0.05, "normal", 0.5, "low") == 250)
    check("a.fac", g(0.05, "normal", 1.0, "low", 1.2) == 600)
    # Qualidade desconhecida cai no 1.0 (não explode, não zera).
    check("a.q_unknown", g(0.05, "weird", 1.0, "low") == 500)


def item_a_seeds() -> None:
    """Preview > 0 para TODA pílula purity/essence viva nas seeds, em TODAS
    as combinações qualidade × fundação (purity) / qualidade (flat)."""
    flat_family = ("core_essence", "body_tempering_progress", "qi_capacity",
                   "cb_instant", "stat_boost")
    seen_purity = 0
    for pill in PILLS:
        et = pill["effect_type"]
        ev = pill["effect_value"]
        if et == "purity_boost":
            seen_purity += 1
            for q in QUALITIES:
                for fq in FOUNDATIONS:
                    v = alch.purity_gain(ev, q, 1.0, fq)
                    check(f"a.seed{pill['id']}.{q}.{fq}", v > 0, str(v))
        elif et in flat_family:
            # O ramo flat usa potency (>=1.0) — int(ev × 1.0) é o piso.
            check(f"a.seed{pill['id']}.floor", int(ev * 1.0) > 0, str(ev))
    check("a.seeds_have_purity", seen_purity >= 2, str(seen_purity))


def item_a_wiring() -> None:
    eng = _src("core", "alchemy_engine.py")
    check("a.apply_calls_helper", "gain = purity_gain(" in eng,
          "o apply TEM de compor pelo helper — senão são duas verdades")
    inv = _src("handlers", "inventory.py")
    check("a.chat_marker", '"kind": "purity"' in inv)
    check("a.chat_composes", "purity_gain(" in inv)
    check("a.chat_note_key", "inv_pill_detail_purity_note" in inv)
    check("a.chat_no_flat_purity",
          re.search(r'in \("qi_capacity", "cb_instant", "purity_boost"', inv) is None,
          "purity_boost não pode continuar no ramo flat do chat")
    web = _src("core", "webserver.py")
    check("a.api_marker", '"kind": "purity"' in web)
    check("a.api_composes", "purity_gain(" in web)
    check("a.api_note_flag", '"purity_foundation"' in web)
    check("a.api_no_flat_purity",
          re.search(r'in \("qi_capacity", "cb_instant", "purity_boost"', web) is None)
    tabs = _src("miniapp", "components", "tabs.js")
    check("a.mini_note", "pill_panel_purity_note" in tabs)
    check("a.mini_note_gated", "scaled.purity_foundation" in tabs,
          "a nota só liga quando o servidor manda a chave condicional")


# ══════════════════════════════════════════════════════════════════════════
# Item B — reloadKey + antes→depois do grau
# ══════════════════════════════════════════════════════════════════════════
def item_b_wiring() -> None:
    tabs = _src("miniapp", "components", "tabs.js")
    check("b.card_prop", "function ScrollEconomyCard({ onChanged, reloadKey })" in tabs)
    check("b.card_dep", "}, [reloadKey]);" in tabs,
          "useEffect deps [] era o bug — a dep TEM de ser o reloadKey")
    check("b.panel_prop", "function CombatLoadoutPanel({ data, onChanged, reloadKey })" in tabs)
    check("b.panel_passes", "<ScrollEconomyCard onChanged={onChanged} reloadKey={reloadKey} />" in tabs)
    check("b.tab_passes", "reloadKey={reload}" in tabs,
          "CombatTab tem de passar o contador `reload` (o que refreshAll bumpa)")
    # antes→depois — payload + as 2 superfícies (keys NOVAS; antigas de fallback)
    web = _src("core", "webserver.py")
    for k in ('"old_grade"', '"old_grade_emoji"', '"old_grade_mult"'):
        check(f"b.payload.{k}", k in web)
    check("b.mini_delta", "combat_grade_upgrade_delta" in tabs)
    check("b.mini_fallback", "combat_grade_upgrade_success" in tabs,
          "payload antigo sem old_grade cai na mensagem de sempre")
    combat = _src("handlers", "combat.py")
    check("b.chat_delta", "tech_grade_upgraded_delta" in combat)


# ══════════════════════════════════════════════════════════════════════════
# Item C — rep de facção: dita quando pulada, nomeada quando paga
# ══════════════════════════════════════════════════════════════════════════
def _fake_quest(**kw):
    d = dict(id=42, name="Eco da Masmorra", reward_stones=0, reward_rep=10,
             reward_items=None, objective_count=1)
    d.update(kw)
    return types.SimpleNamespace(**d)


def _fake_pdq():
    return types.SimpleNamespace(player_id=111, quest_id=42, progress=1,
                                 is_active=True, completed_count=0,
                                 last_completed_at=None)


def item_c_engine() -> None:
    # SEM facção: reputation_missed aparece, reputation NÃO.
    pdq, quest = _fake_pdq(), _fake_quest()
    s = FakeSession([
        (lambda q: "dungeon_quest" in q, [(pdq, quest)]),
        (lambda q: "faction" in q, []),
    ])
    rewards, name = run(dqe.claim_dungeon_quest_reward(s, 111, 42))
    check("c.missed_present", rewards is not None and rewards.get("reputation_missed") == 10,
          str(rewards))
    check("c.missed_no_rep", rewards is not None and "reputation" not in rewards,
          "sem facção não pode fingir crédito")
    check("c.quest_name", name == "Eco da Masmorra")
    check("c.pdq_settled", pdq.is_active is False and pdq.completed_count == 1)

    # COM facção: reputation creditada, reputation_missed AUSENTE (chave
    # condicional — payload-shape de quem tem facção fica byte-idêntico).
    pdq2, quest2 = _fake_pdq(), _fake_quest()
    pf = types.SimpleNamespace(reputation=5, total_rep_earned=100, rank="outer")
    s2 = FakeSession([
        (lambda q: "dungeon_quest" in q, [(pdq2, quest2)]),
        (lambda q: "faction" in q, [pf]),
    ])
    rewards2, _ = run(dqe.claim_dungeon_quest_reward(s2, 111, 42))
    check("c.credited", rewards2 is not None and rewards2.get("reputation") == 10, str(rewards2))
    check("c.credited_no_missed", rewards2 is not None and "reputation_missed" not in rewards2)
    check("c.pf_mutated", pf.reputation == 15 and pf.total_rep_earned == 110)

    # reward_rep == 0: nem reputation nem reputation_missed (nada prometido).
    pdq3, quest3 = _fake_pdq(), _fake_quest(reward_rep=0)
    s3 = FakeSession([(lambda q: "dungeon_quest" in q, [(pdq3, quest3)])])
    rewards3, _ = run(dqe.claim_dungeon_quest_reward(s3, 111, 42))
    check("c.zero_rep_clean", rewards3 is not None
          and "reputation" not in rewards3 and "reputation_missed" not in rewards3,
          str(rewards3))


def item_c_wiring() -> None:
    dg = _src("handlers", "dungeons.py")
    check("c.chat_preview_key", "dng_quest_rep_preview" in dg)
    check("c.chat_preview_nofaction", "dng_quest_rep_preview_nofaction" in dg)
    check("c.chat_gain_key", "dng_quest_rep_gain" in dg)
    check("c.chat_missed_key", "dng_quest_rep_missed" in dg)
    check("c.chat_queries_faction", "PlayerFaction" in dg)
    check("c.chat_hardcoded_dead", "Faction Rep\"" not in dg and "- Rep: {rep}" not in dg,
          "as strings hardcoded do preview/claim têm de morrer")
    web = _src("core", "webserver.py")
    check("c.api_has_faction", '"has_faction": has_faction' in web)
    check("c.api_missed", '"reputation_missed"' in web)
    tabs = _src("miniapp", "components", "tabs.js")
    check("c.mini_label", "dng_quest_rep_faction_short" in tabs)
    check("c.mini_needs", "dng_quest_rep_needs_faction" in tabs)
    check("c.mini_missed", "dng_quest_rep_missed_toast" in tabs)
    check("c.mini_preview_wired", "_dungeonQuestRewards(q, data.has_faction)" in tabs)
    check("c.mini_undefined_safe", "hasFaction === false" in tabs,
          "payload antigo (sem has_faction) não pode virar aviso falso")


# ══════════════════════════════════════════════════════════════════════════
# Item D — alimentar a Chama: engine + endpoint + mini
# ══════════════════════════════════════════════════════════════════════════
def _sf(tier=1, exp=0):
    return types.SimpleNamespace(player_id=111, fire_tier=tier, fire_exp=exp)


def item_d_engine() -> None:
    # Sem núcleo → (None, 0, False): a recusa disclosed nasce daqui.
    s = FakeSession([(lambda q: "player_inventory" in q, [])])
    sf, xp, lv = run(alch.feed_beast_core_to_soul_fire(s, 111, 5))
    check("d.no_cores", sf is None and xp == 0 and lv is False)

    # Feed consome 1 núcleo (row a 1 → deletada), +20 XP.
    inv = types.SimpleNamespace(player_id=111, item_type="beast_core", quantity=1)
    fire = _sf(tier=1, exp=100)
    s2 = FakeSession([
        (lambda q: "soul_fire" in q, [fire]),
        (lambda q: "player_inventory" in q, [inv]),
    ])
    sf2, xp2, lv2 = run(alch.feed_beast_core_to_soul_fire(s2, 111, 5))
    check("d.fed_xp", xp2 == 20 and sf2 is fire and fire.fire_exp == 120, str(xp2))
    check("d.core_consumed", inv.quantity == 0 and inv in s2.deleted)
    check("d.no_levelup_below", lv2 is False)

    # Level-up no limiar EXATO (tier 1→2 a 500 — o número vem das SEEDS do
    # engine, SOUL_FIRE_TIERS).
    t2_req = alch.SOUL_FIRE_TIERS[2]["xp_req"]
    inv3 = types.SimpleNamespace(player_id=111, item_type="beast_core", quantity=3)
    fire3 = _sf(tier=1, exp=t2_req - 20)
    s3 = FakeSession([
        (lambda q: "soul_fire" in q, [fire3]),
        (lambda q: "player_inventory" in q, [inv3]),
    ])
    _, xp3, lv3 = run(alch.feed_beast_core_to_soul_fire(s3, 111, 5))
    check("d.levelup", lv3 is True and fire3.fire_tier == 2, str(fire3.fire_tier))
    check("d.core_left", inv3.quantity == 2 and inv3 not in s3.deleted)

    # Gate de realm no ENGINE: devolve (sf, 0, False) — não None. O endpoint
    # tem de recusar ANTES (senão "sem reino" viraria silêncio, não recusa).
    fire4 = _sf(tier=0, exp=0)
    s4 = FakeSession([(lambda q: "soul_fire" in q, [fire4])])
    sf4, xp4, lv4 = run(alch.feed_beast_core_to_soul_fire(s4, 111, 1))
    check("d.realm_gate_engine", sf4 is fire4 and xp4 == 0 and lv4 is False,
          "abaixo do reino o engine NÃO consome nem dá XP")


def item_d_wiring() -> None:
    web = _src("core", "webserver.py")
    check("d.endpoint_exists", "async def api_alchemy_feed_core(" in web)
    check("d.route", '"/api/miniapp/alchemy/feed_core"' in web)
    # O gate de realm vive ANTES do engine e a recusa é nomeada.
    fn = web.split("async def api_alchemy_feed_core(", 1)[1].split("\nasync def ", 1)[0]
    check("d.gate_named", '"soul_fire_locked"' in fn and '"no_cores"' in fn)
    check("d.row_lock", "with_for_update()" in fn,
          "WRITE row-locked — o decremento do engine é read-modify-write")
    check("d.before_after", '"xp_before"' in fn and '"xp_after"' in fn,
          "Lei §10: o resultado diz antes→depois")
    check("d.recipes_cores", '"cores": beast_cores' in web,
          "o card precisa da contagem no payload do alchemy_recipes")
    tabs = _src("miniapp", "components", "tabs.js")
    check("d.mini_calls", 'api("alchemy/feed_core"' in tabs)
    check("d.mini_btn", "alch_sf_feed_btn" in tabs)
    check("d.mini_count", "alch_sf_cores_label" in tabs)
    check("d.mini_toast", "alch_sf_fed_toast" in tabs)
    check("d.mini_levelup", "alch_sf_levelup_toast" in tabs)
    check("d.mini_reasons", "alch_sf_no_cores_toast" in tabs and "alch_sf_locked_toast" in tabs)
    check("d.mini_gated_old_payload", "sf.cores !== undefined" in tabs,
          "payload antigo sem `cores` esconde a linha, não mostra ×undefined")
    check("d.mini_refresh", "onChanged={refresh}" in tabs)


# ══════════════════════════════════════════════════════════════════════════
# Round 2 (feedback 30/07) — pílula no cap · hooks do advance do mini ·
# snapshot da cristalização · sync do nível no CultivationTab
# ══════════════════════════════════════════════════════════════════════════
def round2_cap_state() -> None:
    g = alch.stat_boost_cap_state
    pill21 = types.SimpleNamespace(id=21, effect_type="stat_boost")  # soul cap 80
    below = types.SimpleNamespace(soul_strength=79)
    at = types.SimpleNamespace(soul_strength=80)
    check("r2.cap_below", g(below, pill21)["at_cap"] is False)
    check("r2.cap_at", g(at, pill21)["at_cap"] is True)
    check("r2.cap_value", g(at, pill21)["cap"] == 80)
    # O GRAU levanta o teto (D1 v16.6): heavenly ×2 → 160; a 80 NÃO está no cap.
    check("r2.cap_grade", g(at, pill21, "heavenly") == {
        "stat": "soul_strength", "cap": 160, "current": 80, "at_cap": False})
    # Não-stat_boost e id sem config → None (nunca bloqueia outros tipos).
    check("r2.cap_none_type", g(at, types.SimpleNamespace(id=5, effect_type="purity_boost")) is None)
    check("r2.cap_none_id", g(at, types.SimpleNamespace(id=999, effect_type="stat_boost")) is None)


def round2_wiring() -> None:
    inv = _src("handlers", "inventory.py")
    check("r2.chat_precheck", inv.count("stat_boost_cap_state") >= 2,
          "os DOIS fluxos do chat (single + bulk) checam antes do débito")
    check("r2.chat_kept_key", "pill_stat_at_cap_kept" in inv)
    web = _src("core", "webserver.py")
    check("r2.api_refusal", '"reason": "stat_at_cap"' in web)
    check("r2.api_cap_stopped", '"cap_stopped": True' in web)
    tabs = _src("miniapp", "components", "tabs.js")
    check("r2.mini_refusal", "pill_panel_at_cap_refused" in tabs)
    check("r2.mini_kept", "pill_panel_at_cap_kept" in tabs)

    # Os 4 hooks por andar do advance do mini (report [jogador]: quest do andar 5
    # em nightmare nunca creditava — o chat é main-only, o s2 vive no mini).
    adv = web.split("async def api_dungeons_advance(", 1)[1].split("\nasync def ", 1)[0]
    check("r2.adv_faction", '"floor": next_floor' in adv,
          "faction quest com floor=andar VENCIDO, não floor_count")
    check("r2.adv_floor_win", '"floor_win", next_floor' in adv)
    check("r2.adv_achievement", '"dungeon_floors", 1' in adv)
    check("r2.adv_core_essence", "add_core_essence(player, 3)" in adv)

    # Snapshot da cristalização: o engine grava, o endpoint prefere a linha
    # nova, e a heurística velha (karma ATUAL rotulado de cristalização) morreu.
    karma = _src("core", "karma_engine.py")
    check("r2.karma_snapshot", 'event_type="path_crystallized"' in karma)
    check("r2.karma_api_reads", 'KarmaLog.event_type == "path_crystallized"' in web)
    check("r2.karma_heuristic_dead", '"sect_donate_contribution", "tribulation_survive"' not in web,
          "a lista de eventos da heurística display-lie tem de sumir")

    # Sync do nível (report [jogador]: header 30s vs barra 5s).
    check("r2.cult_sync", "_lvlSyncRef" in tabs)
    check("r2.cult_sync_guard", '_lvlSyncRef.current = ""' in tabs,
          "o ref precisa RESETAR quando os dois concordam (senão 1 disparo só por sessão)")


# ══════════════════════════════════════════════════════════════════════════
# Lote 31/07 Item A — sweep do fix de grid: o padrão era o bug, não a instância
# ══════════════════════════════════════════════════════════════════════════
def _component(src: str, name: str) -> str:
    # fatia do componente até a PRÓXIMA declaração top-level (4 espaços de
    # indent) — o grid-raiz vive nas primeiras linhas, antes de qualquer
    # function interna.
    try:
        return src.split("function " + name + "(", 1)[1].split("\n    function ", 1)[0]
    except IndexError:
        return ""


MINMAX = 'gridTemplateColumns:"minmax(0, 1fr)"'


def lote31_grid_sweep() -> None:
    tabs = _src("miniapp", "components", "tabs.js")
    ui = _src("miniapp", "components", "ui.js")
    html = _src("miniapp", "index.html")
    # os 5 modais da família Track-A confirmados com filho nowrap (recon 31/07)
    for comp in ("KarmaModal", "WorldSectDirectoryModal", "ContinentModal",
                 "LineageInfoModal", "PathModal"):
        check(f"g.root.{comp}", MINMAX in _component(tabs, comp),
              "grid-raiz sem template = coluna auto esticável (o bug do Salão)")
    # o inner das casas do diretório também (nomes de seita longos)
    wsd = _component(tabs, "WorldSectDirectoryModal")
    check("g.inner.wsect_dir", wsd.count(MINMAX) >= 2,
          "o grid interno das casas também precisa do clamp")
    # DeltaPanel (ui.js) — o ÚNICO nowrap desprotegido do sweep; Lei §10:
    # o número antes→depois nunca é cortado, o rótulo é quem cede.
    dp = _component(ui, "DeltaPanel")
    check("g.deltapanel.minmax", 'gridTemplateColumns: "minmax(0, 1fr)"' in dp)
    check("g.deltapanel.value_whole", "flexShrink: 0" in dp,
          "o span do valor não pode encolher (número inteiro sempre visível)")
    check("g.deltapanel.label_yields", "minWidth: 0" in dp,
          "o rótulo precisa poder encolher/quebrar")
    # fixes originais de hoje intactos + rede global
    for comp in ("SectHallModal", "ProfileModal"):
        check(f"g.root.{comp}", MINMAX in _component(tabs, comp),
              "o fix original do 31/07 tem de continuar de pé")
    check("g.css_net", "overflow-wrap: anywhere" in html,
          ".scroll-area{overflow-wrap:anywhere} é a rede de segurança global")
    # a passada de consistência (mesma família de raiz, conteúdo server/i18n)
    check("g.family_count", tabs.count(MINMAX) >= 17,
          f"esperava >=17 raízes clampadas em tabs.js, achei {tabs.count(MINMAX)}")


# ══════════════════════════════════════════════════════════════════════════
# Lote 31/07 Item B — sweep credita quest (decisão [jogador]): engine `amount`
# ══════════════════════════════════════════════════════════════════════════
def _dq(**kw):
    d = dict(min_difficulty="easy", objective_type="floor_count",
             objective_target=None, objective_count=10)
    d.update(kw)
    return types.SimpleNamespace(**d)


def _dq_pdq(progress=0):
    return types.SimpleNamespace(progress=progress)


def lote31_sweep_amount_engine() -> None:
    # floor_count cumulativo: amount comprime N varreduras numa chamada, com
    # CAP no objetivo dentro do engine.
    pdq, q = _dq_pdq(), _dq()
    s = FakeSession([(lambda x: "dungeon_quest" in x, [(pdq, q)])])
    done = run(dqe.track_dungeon_quest_progress(s, 1, 7, "floor_win", 3, "hard",
                                                False, amount=4))
    check("s.amount_adds", pdq.progress == 4 and done == [], str(pdq.progress))
    done = run(dqe.track_dungeon_quest_progress(s, 1, 7, "floor_win", 3, "hard",
                                                False, amount=50))
    check("s.amount_caps", pdq.progress == 10, "cap no objective_count")
    check("s.amount_completes", done == [(pdq, q)], "no cap, a quest fecha")
    # default amount=1 — os ~10 call sites posicionais antigos ficam intactos
    pdq2, q2 = _dq_pdq(), _dq()
    s2 = FakeSession([(lambda x: "dungeon_quest" in x, [(pdq2, q2)])])
    run(dqe.track_dungeon_quest_progress(s2, 1, 7, "floor_win", 3, "hard", False))
    check("s.amount_default", pdq2.progress == 1)
    # amount NUNCA vaza para thresholds binários: complete_floor abaixo do alvo
    # não anda nem com amount=50; no alvo, pula para completo (comportamento
    # de sempre) — a armadilha QoL-relatos ("forje 5" fechando em 1) não pode
    # renascer aqui.
    pdq3, q3 = _dq_pdq(), _dq(objective_type="complete_floor", objective_target=5,
                              objective_count=1)
    s3 = FakeSession([(lambda x: "dungeon_quest" in x, [(pdq3, q3)])])
    run(dqe.track_dungeon_quest_progress(s3, 1, 7, "floor_win", 3, "hard",
                                         False, amount=50))
    check("s.threshold_immune", pdq3.progress == 0,
          "amount não pode empurrar threshold de andar")
    run(dqe.track_dungeon_quest_progress(s3, 1, 7, "floor_win", 5, "hard",
                                         False, amount=1))
    check("s.threshold_met", pdq3.progress == 1)
    # complete_dungeon: só o flag move; amount irrelevante
    pdq4, q4 = _dq_pdq(), _dq(objective_type="complete_dungeon", objective_count=1)
    s4 = FakeSession([(lambda x: "dungeon_quest" in x, [(pdq4, q4)])])
    run(dqe.track_dungeon_quest_progress(s4, 1, 7, "floor_win", 5, "hard",
                                         False, amount=50))
    check("s.dungeon_flag_only", pdq4.progress == 0)
    run(dqe.track_dungeon_quest_progress(s4, 1, 7, "dungeon_complete", 5, "hard",
                                         True))
    check("s.dungeon_done", pdq4.progress == 1)
    # dificuldade abaixo do mínimo continua não creditando (sweep easy não
    # paga quest nightmare) — o gate do engine sobrevive ao amount.
    pdq5, q5 = _dq_pdq(), _dq(min_difficulty="nightmare")
    s5 = FakeSession([(lambda x: "dungeon_quest" in x, [(pdq5, q5)])])
    run(dqe.track_dungeon_quest_progress(s5, 1, 7, "floor_win", 3, "easy",
                                         False, amount=50))
    check("s.diff_gate_holds", pdq5.progress == 0)
    # assinatura: keyword-only (lição QoL-relatos — posicional não pode engolir)
    dqs = _src("core", "dungeon_quest_engine.py")
    check("s.kwonly", "*, amount: int = 1" in dqs)
    check("s.amount_guard", "max(1, int(amount))" in dqs,
          "amount<=0 não pode congelar o contador")


def lote31_sweep_hooks_wiring() -> None:
    dg = _src("handlers", "dungeons.py")
    web = _src("core", "webserver.py")
    sweep_chat = dg.split("async def dungeon_sweep_exec(", 1)[1].split("\nasync def ", 1)[0]
    sweep_api = web.split("async def api_dungeons_sweep(", 1)[1].split("\nasync def ", 1)[0]

    # CHAT — os 2 hooks que faltavam para a paridade com o advance (o resto
    # credita desde 2026-04, 54ad520b — a premissa "sweep não credita nada"
    # do 30/07 estava errada para o chat).
    check("w.chat_ach",
          'check_achievements(session, player.telegram_id, "dungeon_floors", floor_count)' in sweep_chat)
    check("w.chat_track",
          'track_quest(session, player.telegram_id, "dungeon_floor", floor_count)' in sweep_chat)
    check("w.chat_notify", "notify_achievements(context, player.telegram_id, sweep_ach)" in sweep_chat)
    check("w.chat_notify_after_commit",
          sweep_chat.find("await session.commit()") < sweep_chat.find("notify_achievements("),
          "achievement notifica DEPOIS do commit (padrão do advance)")
    check("w.chat_hooks_before_commit",
          sweep_chat.find('"dungeon_floors"') < sweep_chat.find("await session.commit()"))
    # os hooks históricos continuam de pé
    check("w.chat_faction_kept", '"dungeon_any"' in sweep_chat)
    check("w.chat_floorwin_kept", '"floor_win", f, difficulty, False' in sweep_chat)

    # API — o espelho completo, amount=sweep_count comprime as N varreduras
    check("w.api_fac_any", '_fac_qp(session, user_id, "dungeon_any", amount=sweep_count)' in sweep_api)
    check("w.api_fac_floor", '"floor": _f' in sweep_api)
    check("w.api_floorwin", '"floor_win", _f, difficulty, False, amount=sweep_count' in sweep_api)
    check("w.api_complete", '"dungeon_complete", floor_count, difficulty, True' in sweep_api)
    check("w.api_ach", 'check_achievements(session, user_id, "dungeon_floors", total_floors)' in sweep_api)
    check("w.api_track", 'track_quest(session, user_id, "dungeon_floor", total_floors)' in sweep_api)
    # a ORDEM é a prova dos 100%: os gates (not_completed/diff_gate/run_here)
    # têm de vir ANTES de qualquer hook — o gate JÁ garante a dificuldade
    # 100% completada (expressão canônica; max_floor_reached cru mentiria
    # para runs antigas fechadas no boss).
    for gate in ('"not_completed"', '"diff_gate"', '"run_here"'):
        check(f"w.api_gate_first.{gate}",
              0 < sweep_api.find(gate) < sweep_api.find('"dungeon_any"'),
              "o gate é a prova da ida — hooks só depois dele")
    check("w.api_hooks_before_finalize",
          sweep_api.find('"dungeon_any"') < sweep_api.find("_dungeons_finalize_state"))
    # a linha EN hardcoded morreu nos 3 lugares → key ×3
    check("w.faction_line_dead", "*Faction Quest:*" not in dg,
          "a linha EN hardcoded tinha 3 cópias (advance/entrada/sweep)")
    check("w.faction_line_key", dg.count('"dng_faction_quest_completed"') == 3,
          f"esperava a key nos 3 lugares, achei {dg.count(chr(34) + 'dng_faction_quest_completed' + chr(34))}")


# ══════════════════════════════════════════════════════════════════════════
# Lote 31/07 Item C — o espólio da gruta dito no mini (dívida TEC-4)
# ══════════════════════════════════════════════════════════════════════════
def lote31_cave_loot_wiring() -> None:
    web = _src("core", "webserver.py")
    tabs = _src("miniapp", "components", "tabs.js")
    duel_state = web.split("async def api_combat_duel_state(", 1)[1].split("\nasync def ", 1)[0]
    # key CONDICIONAL: só para pve_source="legacy_cave" E payload carimbado —
    # OFF-identity byte-idêntica para todo outro duelo.
    check("l.guard", 'duel.pve_source == "legacy_cave"' in duel_state)
    check("l.key", '"legacy_cave_result"' in duel_state)
    check("l.marker", '"pve_settled"' in duel_state)
    check("l.payload_conditional", 'if _e.get("payload")' in duel_state,
          "payload vazio não pode virar key presente")
    check("l.guard_before_key",
          duel_state.find('pve_source == "legacy_cave"') < duel_state.find('"legacy_cave_result"'))
    # modal: a seção de espólio lê a key condicional e usa as 9 keys mini
    check("l.mini_reads", "state.legacy_cave_result" in tabs)
    for k in ("lgc_mini_loot_title", "lgc_mini_won_stones", "lgc_mini_won_mat",
              "lgc_mini_won_bagfull", "lgc_mini_won_frag", "lgc_mini_won_art",
              "lgc_mini_won_dupe", "lgc_mini_won_missed", "lgc_mini_lost_try"):
        check(f"l.mini_key.{k}", f'"{k}"' in tabs)
    # params coerentes com o payload do settle (legacy_cave_engine)
    check("l.mini_stones_fmt", "fmtNum(lc.stones)" in tabs)
    check("l.mini_missed_params",
          "lc.art_missed.clears" in tabs and "lc.art_missed.pity_at" in tabs)
    check("l.mini_dupe_branch", "lc.already_has_art" in tabs)
    check("l.mini_lost_branch", 'lc.cave === "lost"' in tabs,
          "derrota também fala (Lei §1: a tentativa consumida é dita)")


# ══════════════════════════════════════════════════════════════════════════
# i18n do lote — presente ×3 ×2, placeholders coerentes
# ══════════════════════════════════════════════════════════════════════════
CHAT_KEYS = (
    "inv_pill_detail_purity_note", "tech_grade_upgraded_delta",
    "dng_quest_rep_preview", "dng_quest_rep_preview_nofaction",
    "dng_quest_rep_gain", "dng_quest_rep_missed",
    "pill_stat_at_cap_kept", "karma_event_path_crystallized",
    "dng_faction_quest_completed",
)
MINI_KEYS = (
    "pill_panel_purity_note", "combat_grade_upgrade_delta",
    "dng_quest_rep_faction_short", "dng_quest_rep_needs_faction",
    "dng_quest_rep_missed_toast",
    "alch_sf_cores_label", "alch_sf_feed_btn", "alch_sf_fed_toast",
    "alch_sf_levelup_toast", "alch_sf_no_cores_toast", "alch_sf_locked_toast",
    "alch_sf_feed_failed",
    "pill_panel_at_cap_refused", "pill_panel_at_cap_kept",
    "lgc_mini_loot_title", "lgc_mini_won_stones", "lgc_mini_won_mat",
    "lgc_mini_won_bagfull", "lgc_mini_won_frag", "lgc_mini_won_art",
    "lgc_mini_won_dupe", "lgc_mini_won_missed", "lgc_mini_lost_try",
)


def i18n_batch() -> None:
    for surface, parts, keys in (("chat", ("locales",), CHAT_KEYS),
                                 ("mini", ("miniapp", "i18n"), MINI_KEYS)):
        data = {}
        for lang in ("pt", "en", "es"):
            with open(os.path.join(ROOT, *parts, f"{lang}.json"), encoding="utf-8") as f:
                data[lang] = json.load(f)
        check(f"i.{surface}_parity",
              set(data["pt"]) == set(data["en"]) == set(data["es"]),
              "paridade global quebrada")
        for k in keys:
            for lang in ("pt", "en", "es"):
                check(f"i.{surface}.{lang}.{k}", k in data[lang])
            toks = {lang: set(re.findall(r"\{(\w+)\}", data[lang].get(k, "")))
                    for lang in ("pt", "en", "es")}
            check(f"i.{surface}.tok.{k}",
                  toks["pt"] == toks["en"] == toks["es"], str(toks))


# ══════════════════════════════════════════════════════════════════════════
def main() -> None:
    item_a_pure()
    item_a_seeds()
    item_a_wiring()
    item_b_wiring()
    item_c_engine()
    item_c_wiring()
    item_d_engine()
    item_d_wiring()
    round2_cap_state()
    round2_wiring()
    lote31_grid_sweep()
    lote31_sweep_amount_engine()
    lote31_sweep_hooks_wiring()
    lote31_cave_loot_wiring()
    i18n_batch()

    print(f"\n{PASS} PASS · {len(FAILS)} FAIL")
    if FAILS:
        for f in FAILS:
            print(" FAIL:", f)
        sys.exit(1)
    print("All green — QoL-Feedback: preview honesto · refetch · rep disclosed · Chama no mini"
          " · grids clampados · sweep credita · espólio da gruta dito.")


if __name__ == "__main__":
    main()
