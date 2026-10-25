# -*- coding: utf-8 -*-
"""Teste isolado MV-4 — meridian_engine + refino ancorado (COMMITTED desta vez;
a lição do MV-3 foi que o teste 54/54 era efémero e se perdeu).

Cobre:
  * OFF-identity: flag OFF → TODA função pública devolve o neutro SEM tocar a
    sessão (sessão-que-explode) · body_durability_mult inalterado.
  * Curvas: channels_allowed por reino · custo/circulação monotónicos ·
    break_chance (floor/cap/bónus por falha).
  * refine_place_mult: os 3 lugares (caverna+formação viva / sítio / estrada)
    + formação expirada + caverna noutro continente + festival modulando.
  * Ritual ponta-a-ponta: preparar (débito all-or-nothing + recusas honestas)
    → circular (idle) → romper (sucesso força +durabilidade na Alma; falha
    honesta NÃO perde nada e sobe a próxima chance).
  * mortal_temper_cost com place_mult (1.25 barateia · 0.75 encarece ·
    default 1.0 byte-idêntico).

Correr: python -X utf8 scripts/_test_mv4_meridians.py  (exit 1 se falhar)
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import core.meridian_engine as mer  # noqa: E402
import core.body_tempering_engine as bte  # noqa: E402

PASS = 0
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {('— ' + detail) if detail else ''}")


class ExplodingSession:
    """Sessão que EXPLODE em qualquer uso — prova OFF = zero queries."""
    def execute(self, *a, **k):
        raise AssertionError("query executada com flag OFF")

    def add(self, *a, **k):
        raise AssertionError("add executado com flag OFF")


class FakeResult:
    def __init__(self, value):
        self._v = value

    def scalar_one_or_none(self):
        return self._v

    def scalar(self):
        return self._v


class FakeSession:
    """Sessão ON: devolve a caverna configurada para o SELECT de PlayerCavern;
    o probe first-open devolve `first_probe`; resto explode (nada mais deve
    tocar a sessão — notify/chronicle são try/except no engine e podem falhar)."""
    def __init__(self, cavern=None, first_probe=None):
        self.cavern = cavern
        self.first_probe = first_probe

    async def execute(self, stmt, params=None):
        s = str(stmt)
        if "player_cavern" in s:
            return FakeResult(self.cavern)
        if "pg_advisory_xact_lock" in s:
            return FakeResult(1)  # review fix — o lock serializa o mer_first
        if "jsonb_exists" in s:
            return FakeResult(self.first_probe)
        raise AssertionError(f"query inesperada: {s[:80]}")


def fake_player(**over):
    p = SimpleNamespace(
        telegram_id=1001, realm=3, spirit_stones=50_000,
        mortal_temper_progress=500, hunt_essence=100,
        current_continent="linghe", meridians_opened={}, meridian_ritual=None,
        language="pt", qi=500.0, qi_capacity=1000.0, battle_power=1000,
        soul_strength=100, perception=10, luck=10,
        body_tempering_level=0, mortal_body_level=0,
    )
    for k, v in over.items():
        setattr(p, k, v)
    return p


def fake_cavern(continent="linghe", live=True, formation=4):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        player_id=1001, continent_key=continent,
        active_formation_id=formation if formation else None,
        formation_set_at=now - timedelta(hours=1),
        formation_expires_at=(now + timedelta(hours=1)) if live else (now - timedelta(minutes=5)),
    )


async def main():
    # ══ 1. OFF-identity (sessão-que-explode) ══════════════════════════════
    mer.corpo_profundo_on = lambda *a, **k: False
    boom = ExplodingSession()
    p = fake_player()

    r = await mer.refine_place_mult(boom, p)
    check("OFF refine_place_mult neutro", r == {"mult": 1.0, "place_key": None,
                                                "place_mult": 1.0, "festival_mult": 1.0}, str(r))
    check("OFF refine_place_view None", (await mer.refine_place_view(boom, p, "pt")) is None)
    check("OFF durability_bonus 0", mer.meridian_durability_bonus(p) == 0.0)
    r = await mer.start_ritual(boom, p)
    check("OFF start_ritual mer_locked", r == {"ok": False, "reason": "mer_locked"}, str(r))
    r = await mer.attempt_break(boom, p)
    check("OFF attempt_break mer_locked", r == {"ok": False, "reason": "mer_locked"}, str(r))
    # A Alma OFF: body_durability_mult idêntico ao pré-MV-4 (1.0 no mortal 0).
    check("OFF body_durability_mult 1.0", bte.body_durability_mult(p) == 1.0)
    p9 = fake_player(realm=8, body_tempering_level=3)
    check("OFF body_durability_mult R8 = tempering", bte.body_durability_mult(p9) == 1.15)
    # Colunas com "lixo" + flag OFF → ainda neutro (defesa em profundidade).
    pjunk = fake_player(meridians_opened={"pulmao": {"opened_at": "2026-01-01T00:00:00+00:00"}})
    check("OFF ignora meridians_opened sujo", mer.meridian_durability_bonus(pjunk) == 0.0)
    check("OFF body mult ignora canais", bte.body_durability_mult(pjunk) == 1.0)

    # ══ 2. Curvas (puras) ═════════════════════════════════════════════════
    mer.corpo_profundo_on = lambda *a, **k: True
    check("allowed R0=0", mer.channels_allowed(0) == 0)
    check("allowed R1=0", mer.channels_allowed(1) == 0)
    check("allowed R2=2", mer.channels_allowed(2) == 2)
    check("allowed R3=4", mer.channels_allowed(3) == 4)
    check("allowed R6=10", mer.channels_allowed(6) == 10)
    check("allowed R7=12", mer.channels_allowed(7) == 12)
    check("allowed R10=12", mer.channels_allowed(10) == 12)
    costs = [mer.channel_cost(i) for i in range(12)]
    check("custo pedras monotónico", all(costs[i + 1]["stones"] > costs[i]["stones"] for i in range(11)))
    check("custo progresso monotónico", all(costs[i + 1]["progress"] > costs[i]["progress"] for i in range(11)))
    check("custo essência monotónico", all(costs[i + 1]["essence"] > costs[i]["essence"] for i in range(11)))
    check("circulação cresce", mer.circulate_hours(11) > mer.circulate_hours(0))
    check("chance cai por canal", mer.break_chance(11, 0) < mer.break_chance(0, 0))
    check("chance sobe por falha", mer.break_chance(0, 2) > mer.break_chance(0, 0))
    check("chance cap 0.90", mer.break_chance(0, 50) <= 0.90)
    check("chance floor 0.30", mer.break_chance(200, 0) >= 0.30)
    check("12 canais únicos", len({c["key"] for c in mer.MERIDIAN_CHANNELS}) == 12)

    # ══ 3. refine_place_mult — os 3 lugares + festival ════════════════════
    # (estados_regionais OFF neste ambiente → festival_mult 1.0 sem query)
    r = await mer.refine_place_mult(FakeSession(cavern=fake_cavern()), fake_player())
    check("caverna+formação viva = 1.25", r["place_key"] == "cavern" and r["mult"] == 1.25, str(r))
    r = await mer.refine_place_mult(FakeSession(cavern=fake_cavern(live=False)), fake_player())
    check("formação EXPIRADA → sítio 1.0", r["place_key"] == "site" and r["mult"] == 1.0, str(r))
    r = await mer.refine_place_mult(FakeSession(cavern=fake_cavern(continent="qianhe")), fake_player())
    check("caverna NOUTRO continente → sítio", r["place_key"] == "site", str(r))
    r = await mer.refine_place_mult(FakeSession(cavern=None), fake_player(current_continent="moyu"))
    check("Mòyǔ sem âncora = 0.75", r["place_key"] == "road" and r["mult"] == 0.75, str(r))
    r = await mer.refine_place_mult(FakeSession(cavern=fake_cavern(formation=None)), fake_player())
    check("caverna SEM formação → sítio", r["place_key"] == "site", str(r))
    # Festival modulando em cima (patch region_overrides)
    import core.region_state_engine as rst
    orig_ro = rst.region_overrides

    async def _fest(session, cont):
        return {"price_mult": 0.95, "explore_risk_bump": 0, "qi_tick_mult": 1.05}
    rst.region_overrides = _fest
    r = await mer.refine_place_mult(FakeSession(cavern=fake_cavern()), fake_player())
    check("festival modula (1.25×1.05)", abs(r["mult"] - 1.3125) < 1e-9, str(r))
    rst.region_overrides = orig_ro

    # ══ 4. mortal_temper_cost com place_mult ══════════════════════════════
    pt = fake_player(mortal_temper_progress=0)
    base = bte.mortal_temper_cost(pt, 1, eff_qi_cap=1000.0)
    cheap = bte.mortal_temper_cost(pt, 1, eff_qi_cap=1000.0, place_mult=1.25)
    dear = bte.mortal_temper_cost(pt, 1, eff_qi_cap=1000.0, place_mult=0.75)
    check("temper default = byte-idêntico", base == bte.mortal_temper_cost(pt, 1, eff_qi_cap=1000.0, place_mult=1.0))
    check("caverna barateia o qi", cheap["qi"] < base["qi"], f"{cheap['qi']} !< {base['qi']}")
    check("estrada encarece o qi", dear["qi"] > base["qi"], f"{dear['qi']} !> {base['qi']}")
    check("pedras nunca mudam com o lugar", cheap["stones"] == base["stones"] == dear["stones"])

    # ══ 5. Ritual ponta-a-ponta ═══════════════════════════════════════════
    ses = FakeSession(cavern=fake_cavern(), first_probe=None)  # None = 1º do servidor
    p = fake_player()
    r = await mer.start_ritual(ses, p)
    check("start ok", r.get("ok") is True, str(r))
    check("débito pedras", p.spirit_stones == 50_000 - r["cost"]["stones"])
    check("débito progresso", p.mortal_temper_progress == 500 - r["cost"]["progress"])
    check("débito essência", p.hunt_essence == 100 - r["cost"]["essence"])
    check("ritual estampado", p.meridian_ritual and p.meridian_ritual["channel"] == "pulmao")
    check("caverna acelera a circulação", r["circulate_hours"] < mer.circulate_hours(0), str(r))
    r2 = await mer.start_ritual(ses, p)
    check("2º start recusa (ativo)", r2 == {"ok": False, "reason": "mer_ritual_active"}, str(r2))
    r3 = await mer.attempt_break(ses, p)
    check("romper cedo recusa", r3.get("reason") == "mer_still_circulating", str(r3))

    # Circulação completa → falha FORÇADA (rng=1.0) — nada se perde.
    p.meridian_ritual = {**p.meridian_ritual,
                         "ends_at": mer._iso(datetime.now(timezone.utc) - timedelta(minutes=1))}
    stones_before = p.spirit_stones
    import random as _random
    class RngHi:
        def random(self):
            return 0.999
    class RngLo:
        def random(self):
            return 0.0
    orig_rng = _random.Random
    _random.Random = lambda *a, **k: RngHi()
    r4 = await mer.attempt_break(ses, p)
    check("falha honesta", r4.get("ok") is True and r4.get("opened") is False, str(r4))
    check("falha não perde nada", p.spirit_stones == stones_before and p.meridian_ritual is not None)
    check("falha sobe a chance", r4["next_chance_pct"] > r4["chance_pct"], str(r4))
    check("re-circulação mais curta", r4["recirculate_hours"] < mer.circulate_hours(0), str(r4))

    # Nova circulação completa → sucesso FORÇADO (rng=0.0) — antes→depois real.
    p.meridian_ritual = {**p.meridian_ritual,
                         "ends_at": mer._iso(datetime.now(timezone.utc) - timedelta(minutes=1))}
    dur_before = bte.body_durability_mult(p)
    _random.Random = lambda *a, **k: RngLo()
    r5 = await mer.attempt_break(ses, p)
    _random.Random = orig_rng
    check("sucesso abre o canal", r5.get("opened") is True and r5["opened_count"] == 1, str(r5))
    check("ritual limpo", p.meridian_ritual is None)
    check("1º do servidor → chronicle flag", r5.get("first_on_server") is True, str(r5))
    dur_after = bte.body_durability_mult(p)
    check("Alma folda o canal (+2%)", abs((dur_after - dur_before) - 0.02) < 1e-9,
          f"{dur_before} -> {dur_after}")
    check("delta exposto", "durability_pct_after" in r5 and r5["durability_pct_after"] == 2.0, str(r5))

    # Cooldown entre rituais (dias) — o corpo assenta.
    r6 = await mer.start_ritual(ses, p)
    check("cooldown pós-open", r6.get("reason") == "mer_cooldown", str(r6))

    # Gate por reino: R2 com 2 canais → capped.
    p_cap = fake_player(realm=2, meridians_opened={
        "pulmao": {"opened_at": "2020-01-01T00:00:00+00:00"},
        "intestino_grosso": {"opened_at": "2020-01-02T00:00:00+00:00"},
    })
    # (cooldown antigo já passou — 2020)
    r7 = await mer.start_ritual(ses, p_cap)
    check("realm gate morde", r7.get("reason") == "mer_realm_capped", str(r7))
    p_poor = fake_player(spirit_stones=10)
    r8 = await mer.start_ritual(ses, p_poor)
    check("sem pedras recusa", r8.get("reason") == "mer_need_stones", str(r8))
    p_r1 = fake_player(realm=1)
    r9 = await mer.start_ritual(ses, p_r1)
    check("R1 recusa (min R2)", r9.get("reason") == "mer_need_realm", str(r9))

    # Review fix — o headline R7+ folda SÓ o incremento dos meridianos
    # (1 + bonus), nunca re-quadrando o tempering já foldado no total.
    from core.game_logic import display_combat_power
    p_hd = fake_player(realm=8, body_tempering_level=3, meridians_opened={
        "pulmao": {"opened_at": "2020-01-01T00:00:00+00:00"},
        "intestino_grosso": {"opened_at": "2020-01-02T00:00:00+00:00"},
    })
    check("headline R7+ folda meridianos", display_combat_power(10_000, p_hd) == 10_400,
          str(display_combat_power(10_000, p_hd)))
    mer.corpo_profundo_on = lambda *a, **k: False
    check("headline R7+ OFF byte-idêntico", display_combat_power(10_000, p_hd) == 10_000)
    mer.corpo_profundo_on = lambda *a, **k: True
    p_hd6 = fake_player(realm=3, mortal_body_level=0, meridians_opened={
        "pulmao": {"opened_at": "2020-01-01T00:00:00+00:00"}})
    check("headline R0-R6 folda meridianos", display_combat_power(10_000, p_hd6) == 10_200,
          str(display_combat_power(10_000, p_hd6)))

    # R7+ dead-end morto (Lei §1): faucets de progresso/essência são realm<7,
    # então no ápex o preparo troca de moeda — pedras ×3, progresso/essência 0.
    apex_cost = mer.channel_cost(10, realm=7)
    mortal_cost = mer.channel_cost(10, realm=6)
    check("R7+ progresso waived", apex_cost["progress"] == 0 and apex_cost["essence"] == 0)
    check("R7+ pedras escalam", apex_cost["stones"] == int(round(mortal_cost["stones"] * 3.0)),
          f"{apex_cost['stones']} vs {mortal_cost['stones']}")
    p_apex = fake_player(realm=7, spirit_stones=10_000_000, mortal_temper_progress=0,
                         hunt_essence=0, meridians_opened={
                             c["key"]: {"opened_at": "2020-01-01T00:00:00+00:00"}
                             for c in mer.MERIDIAN_CHANNELS[:10]})
    r_apex = await mer.start_ritual(ses, p_apex)
    check("R7+ sem faucets consegue iniciar", r_apex.get("ok") is True, str(r_apex))

    # 12/12 → all_open + start recusa.
    p_all = fake_player(realm=9, meridians_opened={
        c["key"]: {"opened_at": "2020-01-01T00:00:00+00:00"} for c in mer.MERIDIAN_CHANNELS})
    check("12/12 conta", mer.meridian_count(p_all) == 12)
    check("12/12 bónus +24%", abs(mer.meridian_durability_bonus(p_all) - 0.24) < 1e-9)
    r10 = await mer.start_ritual(ses, p_all)
    check("12/12 start recusa", r10.get("reason") == "mer_all_open", str(r10))

    print(f"\n{PASS} passed · {len(FAIL)} failed")
    if FAIL:
        for f in FAIL:
            print(f"  FAIL: {f}")
        sys.exit(1)
    print("All green ✅")


asyncio.run(main())
