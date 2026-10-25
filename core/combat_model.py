"""v16.7 — Combat Model (Três Tesouros). SINGLE SOURCE OF TRUTH for the
damage / HP / mitigation math, shared by BOTH combat engines so they can never
diverge (the historical root cause of spar≠arena imbalance):

  - core/duel_engine.py        (turn-based PvP + PvE — the [jogadores] path)
  - core/combat_engine.py:simulate_combat (auto-resolve spar/hunt/dungeon trash)

Design + rationale: Cerebro/Nivrael/Prompts/v16.7_combat_vision.md
Owner decisions:    Cerebro/Nivrael/DESIGN_DECISIONS_v14.md §8
Offline validation: tools/combat_sim_v16_7.py  (imports THIS module — parity)

The identity: combat is the externalization of cultivation depth across the
Three Treasures. 神 Shen (soul + Dao + Intent) STRIKES; 氣 Qi sustains (combat
pool); 精 Jing (body/tempering) ENDURES as proportional, capped mitigation. The
Dao is the apex multiplier and pierces the wall. HP is a buffer, never the win
condition. A duel never stalls (Heavenly Pressure ramp) and every blow draws
meaningful blood (no "1 HP chip" — owner's hard requirement).
"""
from __future__ import annotations

import math
import random

from config import REALM_MULTIPLIERS

# ── TUNABLE CONSTANTS (owner-approved, validated in tools/combat_sim_v16_7.py) ──
DAO_WEIGHT       = 1.6      # apex term weight — Dao "claramente o melhor caminho"
DAO_SAT_S        = 2.0      # saturation S: caps endgame Dao ~2.6x (no runaway)
SOUL_W, BP_W, QI_W      = 0.6, 0.3, 0.1   # STRIKE weights (soul = offense king)
HP_BP_W, HP_QI_W, HP_SOUL_W = 6.0, 5.0, 1.8  # CORE_HP weights (body/qi tank; soul barely)
CORE_BASE        = 5000.0  # realm-anchored vitality floor (pre-realm units)
SHIELD_FRAC      = 0.40    # Soul-Shield hard cap = 40% of CORE_HP
SHIELD_K         = 120.0   # Soul-Shield = min(cap, SHIELD_K*sqrt(soul))*realm_mult
ARMOR_K0         = 900.0   # K_realm = ARMOR_K0 * realm_mult (proportional mitigation)
REDUCTION_CAP    = 0.70    # ONE global clamp over ALL mitigation sources
MEANINGFUL_MIN   = 0.018   # min net hit = 1.8% of target effective HP (kills the 1-HP chip)
RAMP_PER_ROUND   = 0.15    # Heavenly Pressure: +15%/round (linear)
RAMP_DAO_SLICE   = 0.04    # the deeper-Dao fighter's pressure grows faster
PENETRATION_FRAC = 0.5     # penetration can bypass at most half the wall
PENETRATION_CAP  = 0.45    # absolute cap on a fighter's penetration fraction
CRIT_MULT        = 1.5     # luck → crit (modest: flavors variance, never decides)
CRIT_CHANCE_CAP  = 0.25
REALM_PRESS      = 0.02     # higher realm chips lower: gap*2%/round of max HP
REALM_PRESS_CAP  = 3        # capped at the +3-realm practical ceiling


def realm_mult(realm) -> float:
    """Realm curve multiplier. An INTEGER realm indexes REALM_MULTIPLIERS exactly
    as the legacy lookup did (byte-identical on `main`). A FLOAT realm (Combate
    Unificado sub_layer, gated) linearly interpolates between the two bracketing
    realm entries, so grinding sub-levels 1→9 inside a realm smoothly scales
    strike / HP / mitigation instead of only the whole-realm jump counting.

    For an integral realm the fractional part is 0 → the interpolation is a
    no-op and the value is IDENTICAL to the old lookup (OFF intact by
    construction). Out-of-range and None inputs clamp the same way they used to
    (max→RM[last], ≤0/None→RM[0])."""
    r = float(realm or 0)
    n = len(REALM_MULTIPLIERS)
    if r <= 0.0:
        return REALM_MULTIPLIERS[0]
    if r >= n - 1:
        return REALM_MULTIPLIERS[n - 1]
    lo = int(r)
    frac = r - lo
    if frac <= 0.0:
        return REALM_MULTIPLIERS[lo]
    return REALM_MULTIPLIERS[lo] + frac * (REALM_MULTIPLIERS[lo + 1] - REALM_MULTIPLIERS[lo])


def saturate(x: float, s: float = DAO_SAT_S) -> float:
    x = max(0.0, float(x))
    return x / (1.0 + x / s)


def qi_band(qi: float, s: float = 0.0) -> float:
    """v16.7-K (keystone) — server-gated saturation of the qi COMBAT contribution.

    s<=0  → passthrough (frozen main / legacy: qi enters raw, EXACT current math).
    s>0   → qi saturates toward the band scale `s` (in raw-qi units), so an
    UNCAPPED qi_capacity pill can no longer dominate HP / strike / mitigation —
    qi sits in the same magnitude band as capped soul + bp. Reuses saturate().
    Banded ONCE at the entry points (make_profile, combat_engine.calculate_hp);
    the pure math functions below always receive the already-banded value (no
    double-band). `s` is a per-world KNOB (database.db balance_config)."""
    if s and s > 0:
        return saturate(qi, s)
    return max(0.0, float(qi))


def body_throttle(qi_realm: int, body_stage: int, base: float = 0.0, cap: int = 0) -> float:
    """Limitação Corporal — the body caps the combat power a runaway qi-realm can
    EXPRESS (走火入魔 as a soft, telegraphed throttle, never silent death).

    gap D = realm − body_stage; returns a STRIKE multiplier 1/base**min(D,cap)
    that scales ~1× (D=0) → ~10× less (D≈3) → ~100× less (D≈6) with base≈2.15.
    base<=1 → neutral (OFF). STRIKE-only: HP / mitigation are untouched (the body
    still BUFFS durability via tempering_hp/tempering_red — opposite channel)."""
    if base <= 1.0:
        return 1.0
    d = max(0, int(qi_realm or 0) - int(body_stage or 0))
    if cap and cap > 0:
        d = min(d, int(cap))
    return 1.0 / (base ** d)


def dao_mult(dao_index: float, realm: int) -> float:
    """The APEX multiplier. dao_index = get_player_dao_bonuses['bp_mult'] - 1."""
    # realm clamped to the same bound as realm_mult so Dao can't silently exceed
    # its endgame ceiling if a future realm cap is raised or a snapshot has realm>10.
    r = min(int(realm or 0), len(REALM_MULTIPLIERS) - 1)
    return 1.0 + DAO_WEIGHT * saturate(dao_index) * (1.0 + 0.03 * max(0, r - 5))


def combat_hp(soul: float, qi: float, bp: float, realm: int, tempering_hp: float = 1.0) -> float:
    """Two-pool effective HP (CORE_HP + sqrt-capped SOUL_SHIELD), combined.

    Soul gives a soft, capped shield (NOT 250x raw HP) — durability comes from
    body/qi/tempering. This is the single fix that ends the "stack soul to win"
    meta: doubling soul barely moves survival but roughly doubles damage.
    """
    rm = realm_mult(realm)
    core = (bp * HP_BP_W + qi * HP_QI_W + soul * HP_SOUL_W + CORE_BASE) * rm * max(0.1, tempering_hp)
    shield = min(SHIELD_FRAC * core, SHIELD_K * math.sqrt(max(0.0, soul)) * rm)
    return core + shield


def strike_value(soul: float, bp: float, qi: float, realm: int,
                 foundation: float = 1.0, core: float = 1.0, tempering: float = 1.0,
                 tech_dmg: float = 0.0) -> float:
    """The kinetic base of a blow (pre-Dao). soul is the largest term (0.6)."""
    base = (soul * SOUL_W + bp * BP_W + qi * QI_W) * realm_mult(realm)
    return base * foundation * core * tempering * (1.0 + tech_dmg)


def effective_reduction(bp: float, qi: float, armor_rating: float, realm: int,
                        tempering_red: float = 0.0, path_red: float = 0.0,
                        pill_red: float = 0.0, tech_reduce: float = 0.0) -> float:
    """Proportional, realm-stable mitigation with ONE global cap (Jing wall).

    def_pool/(def_pool+K_realm) gives the SAME % reduction at realm 2 and realm 9
    (fixes "useless at high realm / near-invincible at extreme flat bp"). The
    0.70 cap is over ALL sources combined (not per-source) — closes the
    stacked-mitigation tank meta.
    """
    def_pool = bp * 0.4 + qi * 0.2 + max(0.0, armor_rating)
    k = ARMOR_K0 * realm_mult(realm)
    r = def_pool / (def_pool + k) if (def_pool + k) > 0 else 0.0
    r += tempering_red + path_red + pill_red + tech_reduce
    return max(0.0, min(REDUCTION_CAP, r))


def heaven_pressure(round_num: int, dao_adv: float = 0.0) -> float:
    """Tribulation-as-clock: damage escalates each round so duels NEVER stall.
    The deeper-Dao fighter's pressure grows faster ("the longer you stand before
    a higher Dao, the more it crushes you")."""
    return 1.0 + RAMP_PER_ROUND * max(0, int(round_num) - 1) * (1.0 + RAMP_DAO_SLICE * max(0.0, dao_adv) * 10.0)


def make_profile(*, soul: float, qi: float, bp: float, realm: int, dao_index: float = 0.0,
                 foundation: float = 1.0, core: float = 1.0, tempering: float = 1.0,
                 tempering_hp: float = 1.0, tempering_red: float = 0.0,
                 armor_rating: float = 0.0, path_red: float = 0.0, pill_red: float = 0.0,
                 pill_strike: float = 1.0, faction_dmg: float = 1.0, companion_mult: float = 1.0,
                 intent_passive: float = 0.0, luck: float = 0.0, perception: float = 0.0,
                 regen_pct: float = 0.0, qi_band_s: float = 0.0) -> dict:
    """Pack the combat-relevant components a fighter contributes to compute_attack.

    Stored on the fighter dict (key 'combat_profile') so it persists in the duel
    JSONB snapshot and both engines read the SAME shape. luck → crit chance;
    perception → penetration + crit damage (log-damped so 200k luck/perception
    don't explode)."""
    qi = qi_band(qi, qi_band_s)  # keystone: server-gated qi band; 0 = main/legacy passthrough
    crit_chance = min(CRIT_CHANCE_CAP, 0.03 + 0.02 * math.log10(1.0 + max(0.0, luck)))
    pen_percep = min(0.15, 0.02 * math.log10(1.0 + max(0.0, perception)))
    pen_dao = min(0.30, 0.12 * max(0.0, dao_index))
    penetration = min(PENETRATION_CAP, pen_dao + pen_percep)
    crit_dmg_bonus = min(0.5, 0.05 * math.log10(1.0 + max(0.0, perception)))
    eff_hp = combat_hp(soul, qi, bp, realm, tempering_hp)
    # Combate Unificado (sub_layer, gated): preserve a FRACTIONAL realm so
    # realm_mult can interpolate the sub-level bonus in strike / HP / mitigation.
    # An integral realm (every OFF/legacy caller, NPCs, sub_layer 1) stores the
    # exact same int as before → the JSONB snapshot stays byte-identical. Every
    # downstream reader that needs an index/gap (realm_mult, dao_mult,
    # realm_pressure_chip, duel_engine) already int()-casts, so a float here is
    # safe; only realm_mult USES the fraction (by design).
    _realm_store = (float(realm) if (realm and float(realm) % 1) else int(realm or 0))
    return {
        "soul": float(soul), "qi": float(qi), "bp": float(bp), "realm": _realm_store,
        "dao_index": float(dao_index), "foundation": float(foundation), "core": float(core),
        "tempering": float(tempering), "tempering_hp": float(tempering_hp),
        "tempering_red": float(tempering_red), "armor_rating": float(armor_rating),
        "path_red": float(path_red), "pill_red": float(pill_red), "pill_strike": float(pill_strike),
        "faction_dmg": float(faction_dmg), "companion_mult": float(companion_mult),
        "intent_passive": float(intent_passive), "penetration": float(penetration),
        "crit_chance": float(crit_chance), "crit_dmg_bonus": float(crit_dmg_bonus),
        "regen_pct": float(regen_pct), "eff_hp": float(eff_hp),
    }


def compute_attack(atk: dict, dfn: dict, round_num: int = 1, *, intent_matchup: float = 1.0,
                   tech_dmg: float = 0.0, tech_reduce: float = 0.0, tech_armor_ignore: float = 0.0,
                   rng: random.Random | None = None) -> dict:
    """The shared damage core. Returns {net, raw, crit, reduction, penetrated, pressure}.

    net = STRIKE · DAO · INTENT · PREP · CRIT, then proportional mitigation +
    capped Dao-penetration, then Heavenly Pressure, then the meaningful-minimum
    floor (owner: the bar must move every round)."""
    r = rng or random
    raw = strike_value(atk["soul"], atk["bp"], atk["qi"], atk["realm"],
                        atk.get("foundation", 1.0), atk.get("core", 1.0),
                        atk.get("tempering", 1.0), tech_dmg)
    raw *= dao_mult(atk.get("dao_index", 0.0), atk["realm"])
    raw *= (1.0 + atk.get("intent_passive", 0.0)) * float(intent_matchup)
    raw *= atk.get("pill_strike", 1.0) * atk.get("faction_dmg", 1.0) * atk.get("companion_mult", 1.0)
    raw *= r.uniform(0.9, 1.1)
    crit = r.random() < atk.get("crit_chance", 0.0)
    if crit:
        raw *= CRIT_MULT + atk.get("crit_dmg_bonus", 0.0)

    red = effective_reduction(dfn["bp"], dfn["qi"], dfn.get("armor_rating", 0.0), dfn["realm"],
                              dfn.get("tempering_red", 0.0), dfn.get("path_red", 0.0),
                              dfn.get("pill_red", 0.0), tech_reduce)
    mitigated = raw * (1.0 - red)
    pen_frac = min(atk.get("penetration", 0.0) + float(tech_armor_ignore), PENETRATION_FRAC * red)
    penetrated = raw * max(0.0, pen_frac)

    dao_adv = max(0.0, dao_mult(atk.get("dao_index", 0.0), atk["realm"])
                  - dao_mult(dfn.get("dao_index", 0.0), dfn["realm"]))
    pressure = heaven_pressure(round_num, dao_adv)
    net = mitigated * pressure + penetrated  # penetration deliberately does NOT ride the ramp

    eff_hp = dfn.get("eff_hp") or combat_hp(dfn["soul"], dfn["qi"], dfn["bp"], dfn["realm"], dfn.get("tempering_hp", 1.0))
    net = max(net, MEANINGFUL_MIN * eff_hp)
    return {"net": net, "raw": raw, "crit": crit, "reduction": red,
            "penetrated": penetrated, "pressure": pressure}


def realm_pressure_chip(higher_realm: int, lower_realm: int, lower_max_hp: float) -> float:
    """Per-round HP chip a higher realm inflicts on a lower one (suppression)."""
    gap = int(higher_realm) - int(lower_realm)
    if gap <= 0:
        return 0.0
    return min(gap, REALM_PRESS_CAP) * REALM_PRESS * float(lower_max_hp)
