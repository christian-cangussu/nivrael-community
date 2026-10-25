# -*- coding: utf-8 -*-
"""MV-7 — teste isolado do profession_engine (SEM DB — padrão _test_mv6).

Cobre:
  1. OFF-identity: TODA função pública com a sessão-que-explode (flag OFF =
     zero queries — os 57 do main byte-idênticos por construção).
  2. Puras: thresholds/tiers, xp_progress, discounted_qty (floor + mínimo 1 —
     visível), delta do level-up.
  3. Leitores de bônus: curvas por tier, caps PROVADOS, ofício errado = neutro.
  4. xp_multiplier: nativo ×1.5 · rep ≥25 no nativo +0.5 (clamp 2.0) ·
     profession_speed multiplica TUDO (o consumidor único do knob).
  5. track_profession: prefiltro estático (login/cultivate NUNCA tocam a
     sessão, mesmo ON) · tracker errado = zero XP · cap de amount ·
     tier-up notifica com o delta (progressão visível).
  6. Escolha/troca: refusas honestas + débito + XP zerado + prf_first.
  7. heal_ally: recusas em ordem (pílula NUNCA debitada antes da última
     recusa) · locks ascendentes · cura = valor×qualidade×(1+bônus) ·
     karma/tracker/notify best-effort.
  8. Relatório do Mercado Imperial: agregação determinística · carimbo de
     continente preferido ao join · sinks honestos · MERGE preserva o payload
     do MV-3 · commit próprio · vazio honesto.
  9. i18n: toda key referenciada pelo engine/handlers existe ×3 (chat e mini).

Rodar: python -X utf8 scripts/_test_mv7_professions.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import core.profession_engine as prf  # noqa: E402

PASS = 0
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {('— ' + detail) if detail else ''}")


def now_utc():
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════
# Fakes (padrão _test_mv6: dispatch por substring do SQL compilado)
# ══════════════════════════════════════════════════════════════════════════

class ExplodingSession:
    """Sessão que EXPLODE em qualquer uso — prova OFF = zero queries."""
    def execute(self, *a, **k):
        raise AssertionError("query executada com flag OFF")
    def add(self, *a, **k):
        raise AssertionError("add executado com flag OFF")
    def get(self, *a, **k):
        raise AssertionError("get executado com flag OFF")
    async def commit(self):
        raise AssertionError("commit executado com flag OFF")
    async def rollback(self):
        pass
    async def delete(self, obj):
        raise AssertionError("delete executado com flag OFF")


class FakeResult:
    def __init__(self, value):
        self.value = value
    def scalars(self):
        return self
    def all(self):
        if self.value is None:
            return []
        return list(self.value) if isinstance(self.value, list) else [self.value]
    def scalar_one_or_none(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value
    def scalar(self):
        return self.scalar_one_or_none()
    def first(self):
        return self.scalar_one_or_none()


class FakeSession:
    """Sessão ON: responde por substring da statement compilada."""
    def __init__(self, players=None, invs=None, pills=None, region_rows=None,
                 txs=None, rep_by_cont=None, first_probe=None):
        self.players = list(players or [])
        self.invs = list(invs or [])
        self.pills = list(pills or [])
        self.region_rows = list(region_rows or [])
        self.txs = list(txs or [])           # [(tx, buyer_cont)]
        self.rep_by_cont = dict(rep_by_cont or {})
        self.first_probe = first_probe        # None = ninguém tem ofício
        self.added = []
        self.deleted = []
        self.commits = 0
        self.rollbacks = 0
        self.locked_order: list[int] = []

    def _params(self, stmt):
        try:
            return dict(stmt.compile().params)
        except Exception:
            return {}

    async def execute(self, stmt, params=None):
        s = str(stmt)
        p = self._params(stmt)
        p.update(params or {})
        if "pg_advisory_xact_lock" in s:
            return FakeResult(None)
        if "SELECT 1 FROM players WHERE profession IS NOT NULL" in s:
            return FakeResult(self.first_probe)
        if "player_region_rep" in s:
            cont = p.get("continent_key_1")
            return FakeResult(self.rep_by_cont.get(cont))
        if "player_inventory" in s:
            iid = p.get("id_1")
            hit = [i for i in self.invs if int(i.id) == int(iid or 0) and int(i.quantity) > 0]
            return FakeResult(hit[0] if hit else None)
        if "pills_catalog" in s:
            pid = p.get("id_1")
            hit = [c for c in self.pills if int(c.id) == int(pid or 0)]
            return FakeResult(hit[0] if hit else None)
        if "FROM transactions" in s or "transactions.created_at" in s:
            return FakeResult(list(self.txs))
        if "region_states" in s:
            head = s.split("FROM")[0]
            if "region_states.payload" in head and head.count("region_states.") == 1:
                cont = p.get("continent_key_1")
                hit = [r for r in self.region_rows if r.continent_key == cont]
                return FakeResult(hit[0].payload if hit else None)
            return FakeResult(list(self.region_rows))
        if "lower(players.dao_name)" in s:
            name = None
            for k, v in p.items():
                if k.startswith("lower_"):
                    name = v
            hits = [pl for pl in self.players
                    if str(getattr(pl, "dao_name", "") or "").lower() == str(name or "").lower()]
            return FakeResult(hits[0] if hits else None)
        if "FROM players" in s:
            pid = p.get("telegram_id_1")
            if pid is not None:
                if "FOR UPDATE" in s.upper():
                    self.locked_order.append(int(pid))
                hit = [pl for pl in self.players if int(pl.telegram_id) == int(pid)]
                return FakeResult(hit[0] if hit else None)
            return FakeResult(self.players)
        raise AssertionError(f"query inesperada: {s[:140]}")

    def add(self, obj):
        self.added.append(obj)
        if type(obj).__name__ == "RegionState":
            self.region_rows.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def fake_player(pid=1, prof=None, xp=0, cont="linghe", stones=50000, realm=3,
                dao="Kuu", shadow=False, hp=None, lang="pt"):
    return SimpleNamespace(
        telegram_id=pid, profession=prof, profession_xp=xp,
        profession_started_at=None, current_continent=cont,
        spirit_stones=stones, realm=realm, dao_name=dao, username=dao.lower(),
        shadow_mode=shadow, current_hp=hp, language=lang, karma=0,
    )


def fake_region_row(cont="linghe", payload=None):
    return SimpleNamespace(continent_key=cont, state="prospera", since=now_utc(),
                           payload=dict(payload or {}))


def fake_tx(price=100, qty=1, item_type="pill", to_player=2, details=None,
            created=None):
    return SimpleNamespace(price=price, quantity=qty, item_type=item_type,
                           to_player=to_player, tax_paid=int(price * 0.05),
                           details=details, created_at=created or now_utc())


NOTIFY_CALLS: list[tuple] = []
CHRON_CALLS: list[dict] = []
KARMA_CALLS: list[tuple] = []
TRACK_CALLS: list[tuple] = []
TRACK_WEIGHTS: list = []  # QoL-relatos — o tier que o call site mandou (peso)


async def _fake_notify(session, pid, kind, **kw):
    NOTIFY_CALLS.append((int(pid), kind, kw))
    return None


async def _fake_chronicle(session, **kw):
    CHRON_CALLS.append(kw)
    return None


async def main():
    import core.notification_engine as ne
    import core.world_pulse_engine as wpe
    import core.reputation_engine as repmod
    import core.karma_engine as karmamod
    import core.quest_engine as questmod
    import core.combat_engine as combatmod
    import database.db as dbmod
    _orig = (ne.notify, wpe.emit_chronicle, repmod.reputacao_on,
             repmod.get_region_rep, karmamod.apply_karma, questmod.track_quest,
             dbmod.get_world_balance, combatmod.get_max_hp,
             combatmod.get_current_hp, combatmod.restore_hp_pct)
    ne.notify = _fake_notify
    wpe.emit_chronicle = _fake_chronicle

    async def _fake_karma(session, pid, event, *a, **k):
        KARMA_CALLS.append((int(pid), event))
        return {"ok": True}

    # QoL-relatos — o track_quest real ganhou o canal keyword-only
    # `prof_weight_tier` (o peso do ofício). Sem o **kw aqui a chamada de
    # heal_ally levanta TypeError, é engolida pelo try/except best-effort do
    # engine e o tracker parece nunca ter disparado. A tupla fica na MESMA
    # forma (o peso viaja em TRACK_WEIGHTS) para não mexer nas asserções.
    async def _fake_track(session, pid, ot, amount=1, **kw):
        TRACK_CALLS.append((int(pid), ot, amount))
        TRACK_WEIGHTS.append(kw.get("prof_weight_tier"))

    karmamod.apply_karma = _fake_karma
    questmod.track_quest = _fake_track
    combatmod.get_max_hp = lambda pl: 1000.0
    combatmod.get_current_hp = lambda pl: 1000.0 if pl.current_hp is None else float(pl.current_hp)

    def _fake_restore(pl, pct):
        maxhp = 1000.0
        cur = maxhp if pl.current_hp is None else float(pl.current_hp)
        new = min(maxhp, cur + maxhp * pct)
        pl.current_hp = new
        return new - cur
    combatmod.restore_hp_pct = _fake_restore
    dbmod.get_world_balance = lambda *a, **k: {"profession_speed": 1.0}

    # ══ 1. OFF-identity — TODA função pública, sessão-que-explode ══════════
    prf.profissoes_on = lambda *a, **k: False
    x = ExplodingSession()
    pl = fake_player(prof="alquimista", xp=500)
    check("OFF xp_multiplier neutro", (await prf.xp_multiplier(x, pl))["mult"] == 1.0)
    check("OFF track_profession no-op", await prf.track_profession(x, 1, "craft_pill") is None)
    r = await prf.choose_profession(x, pl, "alquimista")
    check("OFF choose=prf_locked", r.get("reason") == "prf_locked")
    r = await prf.switch_profession(x, pl, "ferreiro")
    check("OFF switch=prf_locked", r.get("reason") == "prf_locked")
    check("OFF view=None", await prf.get_profession_view(x, pl, "pt") is None)
    r = await prf.heal_ally(x, pl, "Alvo", 1)
    check("OFF heal=prf_locked", r.get("reason") == "prf_locked")
    check("OFF report=None", await prf.generate_market_reports(x) is None)
    check("OFF report_view=None", await prf.market_report_view(x, pl, "pt") is None)
    check("OFF tx_details=None", await prf.transaction_continent_details(x, pl) is None)
    check("OFF alch_bonus=0", prf.alchemy_success_bonus(pl) == 0.0)
    check("OFF extra_chance=0", prf.extra_pill_chance(pl, 1) == 0.0)
    check("OFF roll_extra=False", prf.roll_extra_pill(pl, 1) is False)
    check("OFF forge_disc=0", prf.forge_ore_discount(pl) == 0.0)
    check("OFF refine_chance=0", prf.free_refine_chance(pl) == 0.0)
    check("OFF roll_refine=False", prf.roll_free_refine(pl) is False)
    check("OFF heal_bonus=0", prf.medic_heal_bonus(fake_player(prof="medico")) == 0.0)
    check("OFF circulate=1.0", prf.medic_circulate_mult(fake_player(prof="medico")) == 1.0)

    # ══ 2. Puras ═══════════════════════════════════════════════════════════
    prf.profissoes_on = lambda *a, **k: True
    ths = prf.tier_thresholds()
    check("thresholds crescentes", ths[0] == 0 and ths[0] < ths[1] < ths[2] < ths[3])
    check("tier xp=0 → 1", prf.tier_for_xp(0) == 1)
    check("tier xp=99 → 1", prf.tier_for_xp(ths[1] - 1) == 1)
    check("tier xp=T2 → 2", prf.tier_for_xp(ths[1]) == 2)
    check("tier xp=T3 → 3", prf.tier_for_xp(ths[2]) == 3)
    check("tier xp=T4 → 4", prf.tier_for_xp(ths[3]) == 4)
    check("tier xp gigante → 4 (cap)", prf.tier_for_xp(10 ** 9) == 4)
    check("tier None → 1", prf.tier_for_xp(None) == 1)
    prog = prf.xp_progress(ths[3] + 50)
    check("progress T4 next=None (teto honesto)", prog["next"] is None and prog["tier"] == 4)
    prog = prf.xp_progress(ths[1] + 1)
    check("progress T2 floor/next", prog["floor"] == ths[1] and prog["next"] == ths[2])
    check("meta inválida=None", prf.profession_meta("xamã") is None)
    check("meta alquimista nativo=yanshan", prf.profession_meta("alquimista")["native"] == "yanshan")
    check("meta ferreiro nativo=fenghuo", prf.profession_meta("ferreiro")["native"] == "fenghuo")
    check("meta medico nativo=linghe", prf.profession_meta("medico")["native"] == "linghe")
    check("nativo nunca é moyu (demonic_only — dead-end)",
          all(m["native"] != "moyu" for m in prf.PROFESSIONS.values()))
    # discounted_qty: floor + mínimo 1 (VISÍVEL — regra da progressão)
    check("disc 0 → intacto", prf.discounted_qty(7, 0.0) == 7)
    check("disc qty1 nunca 0", prf.discounted_qty(1, 0.15) == 1)
    check("disc qty3@5% → 2 (visível)", prf.discounted_qty(3, 0.05) == 2)
    check("disc qty10@15% → 8", prf.discounted_qty(10, 0.15) == 8)
    check("disc qty0 → 0", prf.discounted_qty(0, 0.15) == 0)
    d = prf._bonus_delta("alquimista", 1, 2)
    check("delta alquimista 1→2", "+2%" in d and "+4%" in d, d)
    d = prf._bonus_delta("ferreiro", 2, 3)
    check("delta ferreiro 2→3", "-8%" in d and "-12%" in d, d)

    # ══ 3. Leitores de bônus (curvas + caps + ofício errado) ═══════════════
    for tier, xp_v in ((1, 0), (2, ths[1]), (3, ths[2]), (4, ths[3])):
        alq = fake_player(prof="alquimista", xp=xp_v)
        check(f"alch T{tier} = +{tier * 2}%", prf.alchemy_success_bonus(alq) == min(10.0, tier * 2.0))
        check(f"extra T{tier} pill T1", abs(prf.extra_pill_chance(alq, 1) - min(0.16, tier * 0.04)) < 1e-9)
        fer = fake_player(prof="ferreiro", xp=xp_v)
        check(f"forge T{tier}", abs(prf.forge_ore_discount(fer) - prf.PROF_FORGE_DISCOUNTS[tier - 1]) < 1e-9)
        check(f"refine T{tier}", abs(prf.free_refine_chance(fer) - min(0.16, tier * 0.04)) < 1e-9)
        med = fake_player(prof="medico", xp=xp_v)
        check(f"heal T{tier}", abs(prf.medic_heal_bonus(med) - prf.PROF_HEAL_BONUSES[tier - 1]) < 1e-9)
        check(f"circulate T{tier} = 0.9", prf.medic_circulate_mult(med) == 0.9)
    alq = fake_player(prof="alquimista", xp=0)
    check("extra pill T3+ = 0 (só T1-T2)", prf.extra_pill_chance(alq, 3) == 0.0)
    check("ofício errado: alch de ferreiro = 0", prf.alchemy_success_bonus(fake_player(prof="ferreiro")) == 0.0)
    check("ofício errado: forge de médico = 0", prf.forge_ore_discount(fake_player(prof="medico")) == 0.0)
    check("ofício errado: heal de alquimista = 0", prf.medic_heal_bonus(fake_player(prof="alquimista")) == 0.0)
    check("sem ofício: tudo neutro", prf.alchemy_success_bonus(fake_player()) == 0.0
          and prf.medic_circulate_mult(fake_player()) == 1.0)
    # rolls determinísticos via random module-level
    _orig_random = prf.random
    prf.random = SimpleNamespace(random=lambda: 0.0)
    check("roll_extra proca com chance>0", prf.roll_extra_pill(fake_player(prof="alquimista", xp=0), 1) is True)
    check("roll_refine proca", prf.roll_free_refine(fake_player(prof="ferreiro", xp=0)) is True)
    prf.random = SimpleNamespace(random=lambda: 0.999)
    check("roll_extra falha em 0.999", prf.roll_extra_pill(fake_player(prof="alquimista", xp=0), 1) is False)
    prf.random = _orig_random

    # ══ 4. xp_multiplier (a verdade ÚNICA do mult) ═════════════════════════
    repmod.reputacao_on = lambda *a, **k: False
    s = FakeSession()
    info = await prf.xp_multiplier(s, fake_player(prof="alquimista", cont="linghe"))
    check("fora do nativo: 1.0", info["mult"] == 1.0 and not info["native"])
    info = await prf.xp_multiplier(s, fake_player(prof="alquimista", cont="yanshan"))
    check("no nativo: 1.5", info["mult"] == 1.5 and info["native"] and not info["rep_synergy"])

    async def _rep30(session, pid, cont):
        return 30
    repmod.reputacao_on = lambda *a, **k: True
    repmod.get_region_rep = _rep30
    info = await prf.xp_multiplier(s, fake_player(prof="alquimista", cont="yanshan"))
    check("nativo+rep: 2.0 (1.5+0.5 clamp)", info["mult"] == 2.0 and info["rep_synergy"])

    async def _rep10(session, pid, cont):
        return 10
    repmod.get_region_rep = _rep10
    info = await prf.xp_multiplier(s, fake_player(prof="alquimista", cont="yanshan"))
    check("nativo+rep<25: 1.5", info["mult"] == 1.5 and not info["rep_synergy"])
    dbmod.get_world_balance = lambda *a, **k: {"profession_speed": 2.0}
    info = await prf.xp_multiplier(s, fake_player(prof="alquimista", cont="yanshan"))
    check("profession_speed multiplica (1.5×2=3.0)", info["mult"] == 3.0 and info["speed"] == 2.0)
    info = await prf.xp_multiplier(s, fake_player(prof="alquimista", cont="linghe"))
    check("speed fora do nativo (1×2=2.0)", info["mult"] == 2.0)
    dbmod.get_world_balance = lambda *a, **k: {"profession_speed": 1.0}
    repmod.reputacao_on = lambda *a, **k: False

    # ══ 5. track_profession (o gancho do chokepoint) ═══════════════════════
    # PREFILTRO: tipo não-rastreado NUNCA toca a sessão — mesmo com flag ON.
    await prf.track_profession(ExplodingSession(), 1, "login")
    check("prefiltro: login zero-query", True)
    await prf.track_profession(ExplodingSession(), 1, "cultivate", 120)
    check("prefiltro: cultivate zero-query", True)
    await prf.track_profession(ExplodingSession(), 1, "boss_damage", 99999)
    check("prefiltro: boss_damage zero-query", True)
    # tracker errado para o ofício → sem XP
    pl = fake_player(pid=7, prof="alquimista", xp=0, cont="linghe")
    s = FakeSession(players=[pl])
    await prf.track_profession(s, 7, "forge_artifact")
    check("tracker errado: 0 XP", pl.profession_xp == 0)
    # tracker certo → XP = base × mult (fora do nativo = base)
    await prf.track_profession(s, 7, "craft_pill")
    check("XP base fora do nativo", pl.profession_xp == prf.PROF_XP_BASE)
    # amount cap
    pl2 = fake_player(pid=8, prof="medico", xp=0, cont="qianhe")
    s2 = FakeSession(players=[pl2])
    await prf.track_profession(s2, 8, "use_pill", 999)
    check("amount capado", pl2.profession_xp == prf.PROF_XP_BASE * prf.PROF_XP_AMOUNT_CAP)
    # jogador sem ofício → nada
    pl3 = fake_player(pid=9, prof=None)
    s3 = FakeSession(players=[pl3])
    await prf.track_profession(s3, 9, "craft_pill")
    check("sem ofício: 0 XP", pl3.profession_xp == 0)
    # tier-up → notify com delta (progressão visível)
    NOTIFY_CALLS.clear()
    pl4 = fake_player(pid=10, prof="ferreiro", xp=ths[1] - 1, cont="fenghuo")
    dbmod.get_world_balance = lambda *a, **k: {"profession_speed": 1.0}
    s4 = FakeSession(players=[pl4])
    await prf.track_profession(s4, 10, "forge_artifact")
    check("tier-up creditou XP", pl4.profession_xp >= ths[1])
    check("tier-up notificou", len(NOTIFY_CALLS) == 1)
    if NOTIFY_CALLS:
        _pid, _kind, kw = NOTIFY_CALLS[0]
        check("notify ref namespaced", kw.get("ref_id") == "prf:10:2")
        check("notify tem delta", "→" in kw.get("payload", {}).get("delta", ""))
        check("notify target_tab=profile", kw.get("target_tab") == "profile")

    # ══ 6. Escolha / troca ═════════════════════════════════════════════════
    CHRON_CALLS.clear()
    pl = fake_player(pid=20, prof=None, stones=50000)
    s = FakeSession(players=[pl], first_probe=None)
    r = await prf.choose_profession(s, pl, "alquimista")
    check("choose ok", r.get("ok") and pl.profession == "alquimista" and pl.profession_xp == 0)
    check("choose carimbou started_at", pl.profession_started_at is not None)
    check("choose prf_first Chronicle", len(CHRON_CALLS) == 1
          and CHRON_CALLS[0].get("event_type") == "prf_first")
    r = await prf.choose_profession(s, pl, "ferreiro")
    check("choose 2ª vez = prf_has", r.get("reason") == "prf_has")
    r = await prf.choose_profession(s, fake_player(pid=21), "xamã")
    check("choose key inválida", r.get("reason") == "prf_bad_key")
    # troca
    pl.profession_xp = 777
    r = await prf.switch_profession(s, pl, "alquimista")
    check("switch p/ o mesmo = prf_same", r.get("reason") == "prf_same")
    pobre = fake_player(pid=22, prof="alquimista", xp=500, stones=10)
    r = await prf.switch_profession(s, pobre, "medico")
    check("switch sem pedras: recusa + intacto", r.get("reason") == "prf_no_stones"
          and pobre.profession == "alquimista" and pobre.profession_xp == 500)
    rico = fake_player(pid=23, prof="alquimista", xp=900, stones=prf.PROF_SWITCH_COST + 5)
    r = await prf.switch_profession(s, rico, "ferreiro")
    check("switch ok: debita + zera", r.get("ok") and rico.spirit_stones == 5
          and rico.profession == "ferreiro" and rico.profession_xp == 0)
    # sem ofício → switch vira escolha (sem custo)
    novo = fake_player(pid=24, prof=None, stones=100)
    s_novo = FakeSession(players=[novo], first_probe=1)
    r = await prf.switch_profession(s_novo, novo, "medico")
    check("switch sem ofício = escolha grátis", r.get("ok") and novo.spirit_stones == 100)

    # ══ 7. heal_ally (a 1ª mecânica social) ════════════════════════════════
    def _mk_heal_world(target_hp=400.0, pill_qty=2, effect="hp_restore",
                       t_cont="linghe", t_realm=3, shadow=False):
        healer = fake_player(pid=30, prof="medico", xp=0, cont="linghe", dao="Kuu")
        target = fake_player(pid=31, prof=None, cont=t_cont, dao="Mingyu",
                             realm=t_realm, shadow=shadow, hp=target_hp)
        inv = SimpleNamespace(id=500, player_id=30, item_type="pill", item_id=27,
                              quantity=pill_qty, quality="normal")
        pill = SimpleNamespace(id=27, effect_type=effect, effect_value=0.30,
                               name="Pílula Menor", required_alchemy_tier=3)
        return healer, target, inv, pill

    healer, target, inv, pill = _mk_heal_world()
    check("heal não-médico", (await prf.heal_ally(
        FakeSession(), fake_player(prof="ferreiro"), "Mingyu", 500)).get("reason") == "prf_not_medico")
    s = FakeSession(players=[healer, target], invs=[inv], pills=[pill])
    r = await prf.heal_ally(s, healer, "Ninguem", 500)
    check("heal alvo inexistente", r.get("reason") == "prf_heal_not_found")
    _h, sh_target, _i, _p = _mk_heal_world(shadow=True)
    s_sh = FakeSession(players=[healer, sh_target], invs=[inv], pills=[pill])
    r = await prf.heal_ally(s_sh, healer, "Mingyu", 500)
    check("heal shadow ≡ not_found", r.get("reason") == "prf_heal_not_found")
    r = await prf.heal_ally(s, healer, "Kuu", 500)
    check("heal em si mesmo", r.get("reason") == "prf_heal_self")
    _h, far, _i, _p = _mk_heal_world(t_realm=8)
    s_far = FakeSession(players=[healer, far], invs=[inv], pills=[pill])
    r = await prf.heal_ally(s_far, healer, "Mingyu", 500)
    check("heal gap de reino", r.get("reason") == "prf_heal_realm_gap")
    _h, longe, _i, _p = _mk_heal_world(t_cont="yanshan")
    s_lo = FakeSession(players=[healer, longe], invs=[inv], pills=[pill])
    r = await prf.heal_ally(s_lo, healer, "Mingyu", 500)
    check("heal outro continente (disclosed)", r.get("reason") == "prf_heal_continent")
    r = await prf.heal_ally(s, healer, "Mingyu", 999)
    check("heal pílula fora do anel", r.get("reason") == "prf_heal_no_pill")
    healer2, target2, inv2, notpill = _mk_heal_world(effect="qi_restore")
    s_np = FakeSession(players=[healer2, target2], invs=[inv2], pills=[notpill])
    r = await prf.heal_ally(s_np, healer2, "Mingyu", 500)
    check("heal pílula não-HP", r.get("reason") == "prf_heal_not_hp")
    healer3, full, inv3, pill3 = _mk_heal_world(target_hp=None)
    s_full = FakeSession(players=[healer3, full], invs=[inv3], pills=[pill3])
    r = await prf.heal_ally(s_full, healer3, "Mingyu", 500)
    check("heal alvo cheio: recusa ANTES do débito", r.get("reason") == "prf_heal_full"
          and inv3.quantity == 2)
    # sucesso: débito + cura + locks ascendentes + side-effects
    NOTIFY_CALLS.clear()
    KARMA_CALLS.clear()
    TRACK_CALLS.clear()
    TRACK_WEIGHTS.clear()
    healer4, target4, inv4, pill4 = _mk_heal_world(target_hp=400.0, pill_qty=1)
    healer4.profession_xp = ths[3]  # Grão-Mestre: bônus 25%
    s_ok = FakeSession(players=[healer4, target4], invs=[inv4], pills=[pill4])
    r = await prf.heal_ally(s_ok, healer4, "mingyu", 500)   # case-insensitive
    check("heal ok", bool(r.get("ok")), str(r))
    # 0.30 × 1.0 (normal) × 1.25 = 0.375 → 375 HP
    check("heal valor = 0.30×1.25 = 375", r.get("restored") == 375, str(r.get("restored")))
    check("heal debita a pílula (row deletada em 0)", len(s_ok.deleted) == 1)
    check("heal locks ascendentes", s_ok.locked_order == sorted(s_ok.locked_order))
    check("heal karma wire", KARMA_CALLS and KARMA_CALLS[0][1] == "heal_ally_combat")
    check("heal tracker use_pill do médico", TRACK_CALLS
          and TRACK_CALLS[0] == (30, "use_pill", 1))
    # QoL-relatos — curar com uma pílula alta pesa mais: o tier da pílula tem de
    # viajar no canal do ofício, e o contador (amount) tem de ficar em 1.
    check("heal manda o peso (tier da pílula), não o contador",
          TRACK_WEIGHTS and TRACK_WEIGHTS[0] == 3, str(TRACK_WEIGHTS))
    check("heal notifica o alvo", NOTIFY_CALLS and NOTIFY_CALLS[0][0] == 31)

    # ══ 8. Relatório do Mercado Imperial ═══════════════════════════════════
    buyer_a = fake_player(pid=40, cont="linghe")
    txs = [
        (fake_tx(price=100, item_type="pill", details={"continent": "yanshan"}), "linghe"),
        (fake_tx(price=300, item_type="pill", details={"continent": "yanshan"}), "linghe"),
        (fake_tx(price=200, item_type="herb", details=None), "linghe"),
        (fake_tx(price=1000, item_type="artifact", to_player=None, details=None), None),
    ]
    rows = [fake_region_row("linghe", payload={"prev": "tensa"})]
    s = FakeSession(txs=txs, region_rows=rows)
    summary = await prf.generate_market_reports(s)
    check("report gerou 5 continentes", summary and summary["continents"] == 5)
    check("report commit próprio", s.commits == 1)
    yan = next((x for x in s.region_rows if x.continent_key == "yanshan"), None)
    lin = next((x for x in s.region_rows if x.continent_key == "linghe"), None)
    check("carimbo vence o join (pills em yanshan)", yan
          and yan.payload["market_report"]["sales"] == 2)
    if yan:
        top = yan.payload["market_report"]["top_items"][0]
        check("mediana determinística (100,300→200)", top["median"] == 200
              and top["item_type"] == "pill")
    check("fallback join (herb+npc em linghe)", lin
          and lin.payload["market_report"]["sales"] == 2)
    check("npc burn honesto (sink)", lin
          and lin.payload["market_report"]["npc_burned"] == 1000)
    check("MERGE preserva payload do MV-3", lin and lin.payload.get("prev") == "tensa")
    check("rows ausentes lazy-upserted", len(s.region_rows) == 5)
    # vista
    viewer = fake_player(pid=41, cont="yanshan")
    s_v = FakeSession(region_rows=s.region_rows)
    v = await prf.market_report_view(s_v, viewer, "pt")
    check("report_view lines", v is not None and len(v["lines"]) >= 1)
    empty_viewer = fake_player(pid=42, cont="moyu")
    v2 = await prf.market_report_view(FakeSession(region_rows=s.region_rows), empty_viewer, "pt")
    check("report_view vazio honesto (0 vendas → linha empty)", v2 is not None
          and len(v2["lines"]) == 1)
    v3 = await prf.market_report_view(FakeSession(region_rows=[]), viewer, "pt")
    check("report_view sem snapshot = None", v3 is None)
    # carimbo de transação
    d = await prf.transaction_continent_details(FakeSession(), fake_player(cont="fenghuo"))
    check("tx stamp objeto", d == {"continent": "fenghuo"})
    tgt = fake_player(pid=50, cont="qianhe")
    d = await prf.transaction_continent_details(FakeSession(players=[tgt]), 50)
    check("tx stamp por id", d == {"continent": "qianhe"})
    d = await prf.transaction_continent_details(FakeSession(), fake_player(cont="atlantida"))
    check("tx stamp cont inválido → linghe", d == {"continent": "linghe"})

    # ══ 9. get_profession_view + i18n ══════════════════════════════════════
    repmod.reputacao_on = lambda *a, **k: False
    v = await prf.get_profession_view(FakeSession(), fake_player(prof=None), "pt")
    check("view cerimônia: 3 escolhas + 6 futuros", v and not v["has"]
          and len(v["choices"]) == 3 and len(v["future"]) == 6)
    v = await prf.get_profession_view(FakeSession(), fake_player(prof="medico", xp=ths[2]), "pt")
    check("view status: tier 3 + bônus", v and v["has"] and v["tier"] == 3
          and len(v["bonuses"]) == 3)
    check("view sem rep: sem linha de sinergia", v and "rep_synergy_line" not in v)

    # i18n — toda key referenciada existe ×3 (chat e mini)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from inject_mv7_i18n import CHAT, MINIAPP
    chat_needed = [
        "prf_name_alquimista", "prf_name_ferreiro", "prf_name_medico",
        "prf_name_talismancista", "prf_name_domador", "prf_name_cozinheiro",
        "prf_name_cartografo", "prf_name_mercador", "prf_name_mestre_formacoes",
        "prf_desc_alquimista", "prf_desc_ferreiro", "prf_desc_medico",
        "prf_future_teaser", "prf_tier_1", "prf_tier_2", "prf_tier_3", "prf_tier_4",
        "prf_tier_max", "prf_bonus_alch_success", "prf_bonus_alch_extra",
        "prf_bonus_forge_ore", "prf_bonus_forge_refine", "prf_bonus_medic_heal",
        "prf_bonus_medic_ally", "prf_bonus_medic_meridians",
        "prf_rep_synergy_on", "prf_rep_synergy_off", "prf_in_native",
        "prf_native_travel", "prf_locked_msg", "prf_ceremony_title",
        "prf_ceremony_intro", "prf_native_line", "prf_btn_confirm", "prf_btn_swap",
        "prf_confirm_warn", "prf_swap_title", "prf_swap_warn", "prf_already",
        "prf_gone", "prf_no_stones", "prf_chosen_toast", "prf_chosen_header",
        "prf_swapped_toast", "prf_status_line", "notif_prf_tier_title",
        "notif_prf_tier_body", "notif_prf_healed_title", "notif_prf_healed_body",
        "prf_alch_extra_line", "prf_chron_first", "prf_report_title",
        "prf_report_window", "prf_report_empty", "prf_report_sales",
        "prf_report_item", "prf_report_burned", "prf_item_herb", "prf_item_pill",
        "prf_item_ore", "prf_item_artifact", "prf_item_cauldron",
        "wev_chat_mine_ok_loot",
    ]
    for lang in ("pt", "en", "es"):
        with open(os.path.join(ROOT, "locales", f"{lang}.json"), encoding="utf-8") as f:
            data = json.load(f)
        for k in chat_needed:
            check(f"i18n chat/{lang}: {k}", k in data)
    mini_needed = list(MINIAPP["pt"].keys())
    for lang in ("pt", "en", "es"):
        with open(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), encoding="utf-8") as f:
            data = json.load(f)
        for k in mini_needed:
            check(f"i18n mini/{lang}: {k}", k in data)

    # restaurar
    (ne.notify, wpe.emit_chronicle, repmod.reputacao_on,
     repmod.get_region_rep, karmamod.apply_karma, questmod.track_quest,
     dbmod.get_world_balance, combatmod.get_max_hp,
     combatmod.get_current_hp, combatmod.restore_hp_pct) = _orig

    print(f"\n{PASS} passed · {len(FAIL)} failed")
    for f in FAIL:
        print("  FAIL:", f)
    if FAIL:
        sys.exit(1)
    print("All green")


asyncio.run(main())
