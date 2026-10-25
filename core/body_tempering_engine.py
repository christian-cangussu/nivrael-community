"""
Body Tempering — Nine Transformations (九转炼体)

Each transformation strengthens the cultivator's physical body.
Unlocks at Realm 7 (Body Integration). Requires increasing resources per level.
Bonus: +5% HP/defense (qi_capacity, battle_power) per level.
Pre-requisite: body_tempering >= 3 to advance to Realm 8 (Mahayana).
"""

import os

TEMPERING_LEVELS = {
    0: {
        "name_key": "tempering_level_0",
        "emoji": "🪨",
        "hp_def_mult": 1.00,
        "cost_stones": 0,
        "cost_qi": 0,
        "min_battle_power": 0,
        "progress_required": 0,
    },
    1: {
        "name_key": "tempering_level_1",
        "emoji": "🔥",
        "hp_def_mult": 1.05,
        "cost_stones": 50000,
        "cost_qi": 500,
        "min_battle_power": 500000,
        "progress_required": 100,
    },
    2: {
        "name_key": "tempering_level_2",
        "emoji": "🔥",
        "hp_def_mult": 1.10,
        "cost_stones": 120000,
        "cost_qi": 800,
        "min_battle_power": 1000000,
        "progress_required": 250,
    },
    3: {
        "name_key": "tempering_level_3",
        "emoji": "⚡",
        "hp_def_mult": 1.15,
        "cost_stones": 250000,
        "cost_qi": 1200,
        "min_battle_power": 2000000,
        "progress_required": 500,
    },
    4: {
        "name_key": "tempering_level_4",
        "emoji": "⚡",
        "hp_def_mult": 1.20,
        "cost_stones": 500000,
        "cost_qi": 1800,
        "min_battle_power": 4000000,
        "progress_required": 1000,
    },
    5: {
        "name_key": "tempering_level_5",
        "emoji": "💎",
        "hp_def_mult": 1.25,
        "cost_stones": 1000000,
        "cost_qi": 2500,
        "min_battle_power": 8000000,
        "progress_required": 2000,
    },
    6: {
        "name_key": "tempering_level_6",
        "emoji": "💎",
        "hp_def_mult": 1.30,
        "cost_stones": 2000000,
        "cost_qi": 3500,
        "min_battle_power": 15000000,
        "progress_required": 4000,
    },
    7: {
        "name_key": "tempering_level_7",
        "emoji": "🌟",
        "hp_def_mult": 1.35,
        "cost_stones": 4000000,
        "cost_qi": 5000,
        "min_battle_power": 30000000,
        "progress_required": 6000,
    },
    8: {
        "name_key": "tempering_level_8",
        "emoji": "🌟",
        "hp_def_mult": 1.40,
        "cost_stones": 8000000,
        "cost_qi": 7000,
        "min_battle_power": 60000000,
        "progress_required": 10000,
    },
    9: {
        "name_key": "tempering_level_9",
        "emoji": "🌸",
        "hp_def_mult": 1.45,
        "cost_stones": 15000000,
        "cost_qi": 10000,
        "min_battle_power": 120000000,
        "progress_required": 20000,
    },
    # ── Celestial Body Transformation (Mahayana+) ──
    # F-11 (initial): tiers 10/11/12 with 2.00 / 2.25 / 2.50 hp_def_mult.
    # F-11.5 (refinement): renamed to Skin / Bones / Body, extra passives
    # (tribulation survival, combat HP regen). Multipliers preserved so beta
    # players who already reached these tiers keep their investment.
    10: {
        "name_key": "tempering_level_10",     # "Celestial Skin"
        "emoji": "✨",
        "hp_def_mult": 2.00,
        "cost_stones": 30000000,
        "cost_qi": 15000,
        "min_battle_power": 300000000,
        "progress_required": 40000,
        "min_realm": 8,
        "essence_cost": 100,
        "transforms_body": True,
    },
    11: {
        "name_key": "tempering_level_11",     # "Celestial Bones"
        "emoji": "🦴",
        "hp_def_mult": 2.25,
        "cost_stones": 60000000,
        "cost_qi": 25000,
        "min_battle_power": 600000000,
        "progress_required": 65000,
        "min_realm": 8,
        "essence_cost": 250,
        "trib_survival_bonus": 0.10,   # +10% tribulation survival
    },
    12: {
        "name_key": "tempering_level_12",     # "Supreme Celestial Body"
        "emoji": "☀️",
        "hp_def_mult": 2.50,
        "cost_stones": 120000000,
        "cost_qi": 40000,
        "min_battle_power": 1200000000,
        "progress_required": 100000,
        "min_realm": 8,
        "essence_cost": 400,
        "combat_hp_regen_pct": 0.05,   # regen 5% max HP/round in combat
    },
}


def get_celestial_body_bonuses(level: int) -> dict:
    """
    F-11.5: aggregate Celestial Body passive bonuses for the given tempering
    level. Lower celestial tiers inherit the higher-level passives once reached.
    """
    out = {"trib_survival_bonus": 0.0, "combat_hp_regen_pct": 0.0}
    if level <= 0:
        return out
    for lv, info in TEMPERING_LEVELS.items():
        if lv <= level:
            out["trib_survival_bonus"] += info.get("trib_survival_bonus", 0.0)
            out["combat_hp_regen_pct"] += info.get("combat_hp_regen_pct", 0.0)
    return out

MAX_TEMPERING_LEVEL = 12  # Tiers 10-12 are Celestial (F-11)
CELESTIAL_TEMPERING_MIN = 10
MIN_REALM_REQUIRED = 7  # Body Integration
QI_CAP_BONUS_PER_LEVEL = 200  # Permanent qi_capacity bonus per tempering level


def get_tempering_multiplier(level: int) -> float:
    """Returns the HP/defense multiplier for the given tempering level."""
    if level <= 0:
        return 1.0
    info = TEMPERING_LEVELS.get(level)
    if not info:
        return 1.0
    return info["hp_def_mult"]


def get_tempering_info(level: int) -> dict:
    """Returns full info dict for the given tempering level."""
    return TEMPERING_LEVELS.get(level, TEMPERING_LEVELS[0])


def body_stage_for_gap(level: int, realm: int = 0, mortal_level: int = 0) -> int:
    """Maps body tempering to a 'body stage' comparable to the qi realm, for the
    Limitação Corporal gap D = realm − stage (core/combat_model.body_throttle).

    Sprint 3 — below R7 the body stage is the MORTAL BAND level (mortal_body_level),
    so the gap D = realm − mortal_level is a REAL gap the player CLOSES by tempering
    the Carne Mortal. This is now DEAD-END-SAFE (Lei §1) because the temper ACTION
    exists: we only open the gap where that path EXISTS (`cultivo_corpo_r0` ON);
    in any world without it the body tracks the realm (D = 0 → throttle dormant) so
    a player with no temper path is NEVER throttled. On `main` the flag is OFF →
    this returns the realm (D=0) AND the live BITE is gated behind the separate
    per-world `body_throttle_enabled` knob in combat (OFF on main → never invoked).
    From R7+ a NEGLECTED body opens the gap via the Nine Transformations. Curve = KNOB.

    NOTE: the DISCLOSURE panel (project_body_for_display) computes its own body↔realm
    gap for display; this combat-facing stage is gated independently."""
    realm = int(realm or 0)
    level = int(level or 0)
    if realm < MIN_REALM_REQUIRED:
        # Open the closeable Mortal gap only where the temper path ships; else D=0.
        if _cultivo_corpo_on():
            return int(mortal_level or 0)
        return realm  # no temper path → body tracks realm → no dead-end
    return min(MIN_REALM_REQUIRED + level // 2, MAX_TEMPERING_LEVEL)


# ── Sprint 2 — Cultivo do Corpo @ R0: the Mortal Flesh band (BC-1/BC-7) ──────────
# Seven QUALITATIVE thresholds (Pele → Vísceras) the body crosses in the R0–R6
# early game, ORTHOGONAL to (and below) the R7+ Nine Transformations — "one axis,
# two bands". DISPLAY-ONLY this wave: the tier names + the Qi↔Body gap disclosure.
# The temper ACTION at R0 (a cheap Mortal cost curve + the Spiritual Field 灵田
# input) is the next sprint; until then the body stays at the base tier and the
# panel discloses the path honestly (Lei §1 — never a silent void).
MORTAL_TIERS = (
    ("body_tier_pele",     "🩹"),
    ("body_tier_carne",    "💪"),
    ("body_tier_sangue",   "🩸"),
    ("body_tier_tendoes",  "🪢"),
    ("body_tier_ossos",    "🦴"),
    ("body_tier_medula",   "🧬"),
    ("body_tier_visceras", "🫀"),
)


def mortal_tier(level: int) -> tuple[str, int]:
    """Map a body level to a Mortal-band tier (i18n key, index 0..6) for display."""
    idx = max(0, min(int(level or 0), len(MORTAL_TIERS) - 1))
    return MORTAL_TIERS[idx][0], idx


def project_body_for_display(player, eff_qi_cap=None, place_mult: float = 1.0) -> dict:
    """Cultivo do Corpo — the Mortal Flesh band card. Reads `mortal_body_level` (the
    R0–R6 band, Migration 123).

    Disclosure (always): the achieved tier (base → Pele → … → Vísceras) + the Qi↔Body
    gap (Limitação Corporal) + risk band. Below R7 in an ON world it ALSO carries the
    temper ACTION state (can_temper + next_cost in stones+qi) so the card renders the
    'Temperar a Carne' button with honest cost-before. At R7+ it flips to is_apex (the
    Nine Transformations) and carries the current transformation tier for the card to
    show WITHOUT the Mortal button.

    Combat reads NONE of this: the live Limitação Corporal bite is the separate
    `body_throttle_enabled` knob, and the durability buff is body_durability_mult. The
    temper ACTION is the only writer of mortal_body_level (Sprint 3)."""
    realm = int(getattr(player, "realm", 0) or 0)
    mlvl = max(0, min(int(getattr(player, "mortal_body_level", 0) or 0), MORTAL_BAND_MAX))
    is_apex = realm >= MIN_REALM_REQUIRED
    # Current tier name: level 0 = base flesh (next = Pele); level L = MORTAL_TIERS[L-1].
    if mlvl >= 1:
        tier_key = MORTAL_TIERS[mlvl - 1][0]
        tier_emoji = MORTAL_TIERS[mlvl - 1][1]
    else:
        tier_key = "body_tier_base"
        tier_emoji = "🧍"
    next_tier_key = MORTAL_TIERS[mlvl][0] if mlvl < len(MORTAL_TIERS) else None
    gap = max(0, realm - mlvl)
    risk = "safe" if gap <= 1 else ("warn" if gap <= 3 else "danger")
    out = {
        "tier_key": tier_key,
        "tier_emoji": tier_emoji,
        "tier_index": mlvl,
        "tier_count": MORTAL_BAND_MAX,
        "mortal_level": mlvl,
        "max_level": MORTAL_BAND_MAX,
        "next_tier_key": next_tier_key,
        "gap": gap,
        "risk_band": risk,
        "is_apex": is_apex,
        # 星 2.1 O CORPO — a ORDEM das sete etapas, dita pelo dono. O cliente
        # desenha um ponto por etapa e precisa do nome de cada uma; sem esta
        # lista teria de a escrever à mão (um segundo dono da sequência) ou de
        # a adivinhar pela ordem alfabética do i18n — que o Astra proibiu por
        # não provar nada. Aditivo: só existe onde `body_cultivation` existe.
        "tier_keys": [k for k, _e in MORTAL_TIERS],
    }
    if is_apex:
        # R7+ in an ON world — show the Nine Transformations state, no Mortal button.
        tl = int(getattr(player, "body_tempering_level", 0) or 0)
        tinfo = get_tempering_info(tl)
        out["can_temper"] = False
        out["transformation_level"] = tl
        out["transformation_name_key"] = tinfo["name_key"]
        out["transformation_emoji"] = tinfo["emoji"]
    else:
        st = can_temper_mortal(player, eff_qi_cap=eff_qi_cap, place_mult=place_mult)
        out["can_temper"] = bool(st["can"])
        out["temper_reason_key"] = st.get("reason_key")
        out["next_cost"] = st.get("cost")  # carries via_progress (Horta discount)
        # Sprint 4 — Horta progress toward the next tier (for the card's "via Horta" hint).
        out["temper_progress"] = int(getattr(player, "mortal_temper_progress", 0) or 0)
        out["progress_required"] = mortal_progress_required(st.get("next_level"))
        # VISIBLE state + realm pacing (research: always show the number). The card shows
        # current max HP + defense % so the player SEES what the body bought, the realm
        # cap so they know "temper to here, then break through", and the NEXT tier's HP/DEF.
        cap = mortal_realm_cap(realm)
        out["realm_cap"] = cap
        out["at_realm_cap"] = bool(mlvl >= cap and mlvl < MORTAL_BAND_MAX)
        try:
            from core.combat_engine import get_max_hp
            out["max_hp"] = int(round(get_max_hp(player)))
        except Exception:
            out["max_hp"] = None
        cur_mult = float(MORTAL_BAND.get(mlvl, {}).get("hp_def_mult", 1.0)) if mlvl else 1.0
        out["def_mult"] = round(cur_mult, 3)
        out["def_pct"] = round(max(0.0, (cur_mult - 1.0)) * 100, 1)
        nxt = MORTAL_BAND.get(mlvl + 1) if mlvl < MORTAL_BAND_MAX else None
        out["next_def_pct"] = round(max(0.0, (float(nxt["hp_def_mult"]) - 1.0)) * 100, 1) if nxt else None
        # Body-aware COMBAT POWER (research §2: one number that climbs on every upgrade).
        # A tougher body = more effective combat power; show it so tempering visibly moves
        # the headline. Display proxy (combat itself uses the Três Tesouros pools); tunable.
        bp = int(getattr(player, "battle_power", 0) or 0)
        out["combat_power"] = int(round(bp * cur_mult))
        out["next_combat_power"] = int(round(bp * float(nxt["hp_def_mult"]))) if nxt else None
    return out


# ── Sprint 3 — Cultivo do Corpo @ R0: the AÇÃO (temper the Mortal Flesh) ──────────
# The seven crossable thresholds (1=Pele .. 7=Vísceras) the R0–R6 cultivator tempers,
# gaining DURABILITY (hp_def_mult) and NEVER qi_capacity (the Wall, not the fuel —
# BC-5). Engine-not-DB (wipe-safe). Costs are CHEAP + scaled (stones ~200→12k) and
# the qi cost is a fraction of the EFFECTIVE qi capacity (qi_pct) — that fraction,
# burned from current qi, is the natural pacer (BC-4: medita → tempera → medita).
# hp_def_mult is gentle + conservative (~1.02→1.15). All values are tunable later.
# `progress_required` (Sprint 4) — Horta 灵田 points that, once banked, DISCOUNT the
# qi cost of crossing that threshold (the patient path; the Horta did the tempering).
MORTAL_BAND = {
    1: {"name_key": "body_tier_pele",     "emoji": "🩹", "cost_stones": 300,   "qi_pct": 0.30, "hp_def_mult": 1.06,  "progress_required": 120},
    2: {"name_key": "body_tier_carne",    "emoji": "💪", "cost_stones": 800,   "qi_pct": 0.34, "hp_def_mult": 1.13,  "progress_required": 200},
    3: {"name_key": "body_tier_sangue",   "emoji": "🩸", "cost_stones": 2000,  "qi_pct": 0.38, "hp_def_mult": 1.21,  "progress_required": 320},
    4: {"name_key": "body_tier_tendoes",  "emoji": "🪢", "cost_stones": 4500,  "qi_pct": 0.43, "hp_def_mult": 1.30,  "progress_required": 480},
    5: {"name_key": "body_tier_ossos",    "emoji": "🦴", "cost_stones": 9000,  "qi_pct": 0.48, "hp_def_mult": 1.40,  "progress_required": 700},
    6: {"name_key": "body_tier_medula",   "emoji": "🧬", "cost_stones": 16000, "qi_pct": 0.54, "hp_def_mult": 1.52,  "progress_required": 1000},
    7: {"name_key": "body_tier_visceras", "emoji": "🫀", "cost_stones": 28000, "qi_pct": 0.60, "hp_def_mult": 1.65,  "progress_required": 1400},
}
MORTAL_BAND_MAX = 7  # Vísceras — the apex of the Mortal band (then R7 → Transformations)
# The body must NOT out-pace the realm (else you max it in minutes and the Anomalia
# never bites). You can temper at most BODY_REALM_LEAD tiers ahead of your realm, so
# the 7 tiers SPREAD across R0–R6 (~1 per realm): R0→tier1, R1→tier2, … R6→tier7. The
# loop becomes: temper to the realm's cap → break through → unlock the next tier. Env-
# tunable; the durability mults above are STRONGER (1.06→1.65) so each tier is FELT
# (a visible HP/DEF jump), not decorative. All values gated by `cultivo_corpo_r0`.
BODY_REALM_LEAD = int(os.getenv("BODY_REALM_LEAD", "1"))


def mortal_realm_cap(realm: int) -> int:
    """The highest mortal_body_level allowed at this realm (≤ realm + BODY_REALM_LEAD,
    capped at MORTAL_BAND_MAX). Keeps the body in step with the realm."""
    return max(1, min(MORTAL_BAND_MAX, int(realm or 0) + BODY_REALM_LEAD))

# Sprint 4 — Horta 灵田: banking ≥ progress_required points for a tier drops its qi
# burn to this fraction of full (the body was tempered patiently with TIME, not Qi —
# BC-4/BC-6). Stones are unchanged; the Horta saves QI specifically. Tunable later.
HORTA_QI_DISCOUNT = 0.35


def mortal_progress_required(target_level) -> int | None:
    """Horta points needed to discount the qi cost of reaching `target_level` (1..7).
    None for invalid/maxed (target_level None or out of band)."""
    if not target_level:
        return None
    info = MORTAL_BAND.get(int(target_level))
    return int(info["progress_required"]) if info else None


def _has_progress_for(player, target_level) -> bool:
    """True iff the player has banked enough Horta progress to discount this tier."""
    req = mortal_progress_required(target_level)
    return bool(req is not None and int(getattr(player, "mortal_temper_progress", 0) or 0) >= req)


def _cultivo_corpo_on(world_key: str | None = None) -> bool:
    """True iff the per-world `cultivo_corpo_r0` flag is ON for the active (or given)
    world. Fail-safe → False (main / any error → the band is invisible + inert)."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("cultivo_corpo_r0", world_key))
    except Exception:
        return False


def body_min_realm(world_key: str | None = None) -> int:
    """The realm at which the body axis becomes temperable: 0 where the Mortal band
    is ON (`cultivo_corpo_r0`), else MIN_REALM_REQUIRED (7 — the Nine Transformations
    gate). `main`/OFF → 7 (the 57 keep the legacy R7 gate)."""
    return 0 if _cultivo_corpo_on(world_key) else MIN_REALM_REQUIRED


def _eff_qi_cap_for(player, eff_qi_cap=None) -> float:
    """Effective qi capacity used to price a Mortal temper. Prefer the value the
    caller computed (raw+equip×tempering — same as the regen target); fall back to
    raw qi_capacity when not supplied (R0–R6 players have no tempering mult, so
    raw≈effective there anyway)."""
    if eff_qi_cap is not None:
        try:
            return float(eff_qi_cap)
        except (TypeError, ValueError):
            pass
    return float(getattr(player, "qi_capacity", 0) or 0)


def mortal_temper_cost(player, target_level: int, eff_qi_cap=None, place_mult: float = 1.0) -> dict | None:
    """Cost to reach `target_level` (1..7): {stones, qi, via_progress}. qi = qi_pct ×
    effective qi capacity, burned from current qi (BC-4). HORTA discount (Sprint 4):
    when the player banked ≥ progress_required points (from the Spiritual Field 灵田),
    the qi burn drops to HORTA_QI_DISCOUNT of full and the points are consumed on
    advance — the patient path (BC-6). Stones are the same either way; the Horta
    saves QI specifically.

    MV-4 — refino ancorado em LUGAR: `place_mult` (meridian_engine.refine_place_mult)
    DIVIDES the qi burn — the cavern channels the qi (1.25 → ~20% cheaper), the
    road drags it (0.75 → ~33% dearer). Default 1.0 keeps every existing call
    site (and any `corpo_profundo`-OFF world) byte-identical. Stones untouched
    (the place refines QI, not commerce)."""
    info = MORTAL_BAND.get(int(target_level))
    if not info:
        return None
    via_progress = _has_progress_for(player, target_level)
    qi_full = info["qi_pct"] * _eff_qi_cap_for(player, eff_qi_cap)
    qi_cost = int(round(qi_full * (HORTA_QI_DISCOUNT if via_progress else 1.0)
                        / max(0.1, float(place_mult or 1.0))))
    return {"stones": int(info["cost_stones"]), "qi": qi_cost, "via_progress": via_progress}


def can_temper_mortal(player, eff_qi_cap=None, place_mult: float = 1.0) -> dict:
    """Can this player temper the Carne Mortal one tier? Gated by `cultivo_corpo_r0`
    AND realm < 7 (the Mortal band is the R0–R6 path; R7+ uses the Nine
    Transformations — a PARALLEL function, never this one). Returns
    {can, reason_key, next_level, cost, next_tier_key}. `place_mult` (MV-4)
    prices the qi burn for WHERE the player stands (default 1.0 = identical)."""
    realm = int(getattr(player, "realm", 0) or 0)
    if not _cultivo_corpo_on():
        return {"can": False, "reason_key": "body_temper_locked", "next_level": None, "cost": None, "next_tier_key": None}
    if realm >= MIN_REALM_REQUIRED:
        return {"can": False, "reason_key": "body_temper_apex", "next_level": None, "cost": None, "next_tier_key": None}
    lvl = max(0, min(int(getattr(player, "mortal_body_level", 0) or 0), MORTAL_BAND_MAX))
    if lvl >= MORTAL_BAND_MAX:
        return {"can": False, "reason_key": "body_temper_maxed", "next_level": None, "cost": None, "next_tier_key": None}
    cap = mortal_realm_cap(realm)
    if lvl >= cap:
        # The body is at the limit for this realm — break through to temper further.
        return {"can": False, "reason_key": "body_temper_realm_capped", "next_level": None,
                "cost": None, "next_tier_key": None, "realm_cap": cap}
    target = lvl + 1
    nxt = MORTAL_BAND[target]
    cost = mortal_temper_cost(player, target, eff_qi_cap, place_mult)
    base = {"next_level": target, "cost": cost, "next_tier_key": nxt["name_key"]}
    if int(getattr(player, "spirit_stones", 0) or 0) < cost["stones"]:
        return {"can": False, "reason_key": "body_temper_need_stones", **base}
    if float(getattr(player, "qi", 0) or 0) < cost["qi"]:
        return {"can": False, "reason_key": "body_temper_need_qi", **base}
    return {"can": True, "reason_key": None, **base}


def perform_mortal_temper(player, eff_qi_cap=None, place_mult: float = 1.0) -> dict:
    """Execute one Mortal temper: debit stones + qi (current), raise mortal_body_level
    by 1. NEVER touches qi_capacity (BC-5 — durability, not fuel). Caller MUST call
    can_temper_mortal() first inside a row-locked transaction; this re-validates
    defensively and fails atomically ({success: False}, no mutation) if the gate no
    longer holds — so the débito is all-or-nothing. `place_mult` (MV-4) must be the
    SAME value the caller priced the check with (default 1.0 = identical)."""
    realm = int(getattr(player, "realm", 0) or 0)
    if not _cultivo_corpo_on() or realm >= MIN_REALM_REQUIRED:
        return {"success": False, "reason_key": "body_temper_locked"}
    lvl = max(0, min(int(getattr(player, "mortal_body_level", 0) or 0), MORTAL_BAND_MAX))
    if lvl >= MORTAL_BAND_MAX:
        return {"success": False, "reason_key": "body_temper_maxed"}
    cap = mortal_realm_cap(realm)
    if lvl >= cap:
        return {"success": False, "reason_key": "body_temper_realm_capped", "realm_cap": cap}
    target = lvl + 1
    info = MORTAL_BAND[target]
    cost = mortal_temper_cost(player, target, eff_qi_cap, place_mult)
    if int(getattr(player, "spirit_stones", 0) or 0) < cost["stones"]:
        return {"success": False, "reason_key": "body_temper_need_stones", "cost": cost}
    if float(getattr(player, "qi", 0) or 0) < cost["qi"]:
        return {"success": False, "reason_key": "body_temper_need_qi", "cost": cost}
    player.spirit_stones = max(0, int(player.spirit_stones or 0) - cost["stones"])
    player.qi = max(0.0, float(player.qi or 0) - cost["qi"])
    via_progress = bool(cost.get("via_progress"))
    if via_progress:
        # Horta path: consume EXACTLY the requirement, carrying any overflow to the
        # next tier (no wasted harvests). Stones/qi already debited above.
        req = mortal_progress_required(target) or 0
        player.mortal_temper_progress = max(0, int(getattr(player, "mortal_temper_progress", 0) or 0) - req)
    # VISIBLE INCREASE (research: "a gain the player can't see = no progress"). Snapshot
    # max HP + mitigation BEFORE and AFTER raising the tier so the UI can show the
    # before→after delta ("❤️ HP máx 1.200 → 1.380 (+180)"). body_durability_mult feeds
    # calculate_hp, so a higher tier is a real, now-SHOWN HP/DEF jump.
    _bp = int(getattr(player, "battle_power", 0) or 0)
    try:
        from core.combat_engine import get_max_hp
        hp_before = float(get_max_hp(player))
    except Exception:
        hp_before = 0.0
    prev_mult = float(MORTAL_BAND.get(lvl, {}).get("hp_def_mult", 1.0)) if lvl else 1.0
    player.mortal_body_level = target
    try:
        hp_after = float(get_max_hp(player))
    except Exception:
        hp_after = hp_before
    new_mult = float(info["hp_def_mult"])
    return {
        "success": True,
        "new_level": target,
        "mult": new_mult,
        "prev_mult": prev_mult,
        "tier_key": info["name_key"],
        "tier_emoji": info["emoji"],
        "stones": cost["stones"],
        "qi": cost["qi"],
        "via_progress": via_progress,
        # before→after for the visible delta
        "hp_before": int(round(hp_before)),
        "hp_after": int(round(hp_after)),
        "hp_gain": int(round(hp_after - hp_before)),
        "def_pct_before": round(max(0.0, (prev_mult - 1.0)) * 100, 1),
        "def_pct_after": round(max(0.0, (new_mult - 1.0)) * 100, 1),
        # body-aware Combat Power before→after (so the headline visibly jumps)
        "power_before": int(round(_bp * prev_mult)),
        "power_after": int(round(_bp * new_mult)),
        "power_gain": int(round(_bp * new_mult) - round(_bp * prev_mult)),
    }


def body_durability_mult(player) -> float:
    """Band-aware HP/DEF multiplier for combat — the single source the HP pool and
    mitigation read. R7+ → the Nine Transformations mult (get_tempering_multiplier,
    EXACTLY as before → the 57 are byte-identical). Below R7 → the Mortal band mult,
    but ONLY in a `cultivo_corpo_r0` world; otherwise 1.0. On `main` (flag OFF):
    R<7 players have mortal_body_level=0 AND body_tempering_level=0 → 1.0, and R7+
    players hit the same get_tempering_multiplier path as before → combat identical.

    MV-4 — the MERIDIANS fold here (a Alma única: this is the ONE chokepoint
    calculate_hp, unified_combat_hp, make_profile mitigation AND
    display_combat_power all read, so an opened channel bites EVERY surface).
    ADDITIVE +2%/channel over the band mult, at any realm (channels persist
    past R7). Gated inside meridian_durability_bonus by `corpo_profundo` —
    OFF world → +0.0 → byte-identical."""
    realm = int(getattr(player, "realm", 0) or 0)
    _mer = 0.0
    try:
        from core.meridian_engine import meridian_durability_bonus
        _mer = meridian_durability_bonus(player)
    except Exception:
        _mer = 0.0
    if realm >= MIN_REALM_REQUIRED:
        return get_tempering_multiplier(int(getattr(player, "body_tempering_level", 0) or 0)) + _mer
    if not _cultivo_corpo_on():
        return 1.0 + _mer
    lvl = max(0, min(int(getattr(player, "mortal_body_level", 0) or 0), MORTAL_BAND_MAX))
    info = MORTAL_BAND.get(lvl)
    return (float(info["hp_def_mult"]) if info else 1.0) + _mer


def get_next_level_info(current_level: int) -> dict | None:
    """Returns info for the next tempering level, or None if maxed."""
    if current_level >= MAX_TEMPERING_LEVEL:
        return None
    return TEMPERING_LEVELS.get(current_level + 1)


def project_tempering_status(player, total_battle_power: int | None = None) -> dict:
    """星 2.1 — the ONE owner of the `body_tempering/status` payload (the Nine
    Transformations + celestial 10-12). Pure: reads only the loaded row.

    The endpoint used to build this dict inline; the mini-app dev harness and
    the §25 guard need the SAME shape without a DB, and a hand-copied shape
    diverges (Lei 0 §2). The caller owns the expensive part: the TOTAL battle
    power (equipment/companion/dao/interior folds need the session). With
    `total_battle_power=None` and a next level to show, `next` is omitted — the
    endpoint only calls that way to learn whether it must compute the power.

    `levels` (additive, 2.1): each level 1..MAX with its name key and min realm,
    so the client lights one point per level without rebuilding the
    `tempering_level_N` convention on its side."""
    current = int(getattr(player, "body_tempering_level", 0) or 0)
    current_info = get_tempering_info(current)
    out = {
        "ok": True,
        "unlocked": bool(int(getattr(player, "realm", 0) or 0) >= MIN_REALM_REQUIRED),
        "min_realm_required": int(MIN_REALM_REQUIRED),
        "realm": int(getattr(player, "realm", 0) or 0),
        "current_level": current,
        "max_level": int(MAX_TEMPERING_LEVEL),
        "current_info": {
            "name_key": current_info["name_key"],
            "emoji": current_info.get("emoji", "🪨"),
            "hp_def_mult": float(current_info["hp_def_mult"]),
        },
        "body_tempering_progress": int(getattr(player, "body_tempering_progress", 0) or 0),
        "spirit_stones": int(getattr(player, "spirit_stones", 0) or 0),
        "qi": float(getattr(player, "qi", 0) or 0),
        "celestial_essence": int(getattr(player, "celestial_essence", 0) or 0),
        "levels": [
            {"level": int(lv), "name_key": inf["name_key"],
             "min_realm": int(inf.get("min_realm", MIN_REALM_REQUIRED))}
            for lv, inf in sorted(TEMPERING_LEVELS.items())
            if 1 <= int(lv) <= int(MAX_TEMPERING_LEVEL)
        ],
    }
    next_info = get_next_level_info(current)
    if next_info is None:
        out["next"] = None
        return out
    if total_battle_power is None:
        return out
    check = can_temper(player, total_battle_power=int(total_battle_power))
    out["total_battle_power"] = int(total_battle_power)
    out["next"] = {
        "level": current + 1,
        "name_key": next_info["name_key"],
        "emoji": next_info.get("emoji", "🔥"),
        "hp_def_mult": float(next_info["hp_def_mult"]),
        "cost_stones": int(next_info["cost_stones"]),
        "cost_qi": int(next_info["cost_qi"]),
        "min_battle_power": int(next_info["min_battle_power"]),
        "progress_required": int(next_info["progress_required"]),
        "min_realm": int(next_info.get("min_realm", MIN_REALM_REQUIRED)),
        "essence_cost": int(next_info.get("essence_cost", 0)),
        "can_ascend": bool(check["can"]),
        "blocked_reason_key": check.get("reason_key"),
    }
    return out


def can_temper(player, total_battle_power: int = None) -> dict:
    """
    Check if a player can attempt the next body tempering transformation.
    Uses total_battle_power (with equipment) if provided, otherwise falls back to base.
    Returns {"can": bool, "reason_key": str|None, "next_info": dict|None}
    """
    if player.realm < MIN_REALM_REQUIRED:
        return {"can": False, "reason_key": "tempering_need_realm", "next_info": None}

    current = player.body_tempering_level
    if current >= MAX_TEMPERING_LEVEL:
        return {"can": False, "reason_key": "tempering_max_reached", "next_info": None}

    next_info = TEMPERING_LEVELS[current + 1]

    # Celestial tempering (tier 10+) requires Mahayana realm + celestial essence.
    next_min_realm = next_info.get("min_realm", MIN_REALM_REQUIRED)
    if player.realm < next_min_realm:
        return {"can": False, "reason_key": "tempering_need_celestial_realm", "next_info": next_info}

    essence_cost = next_info.get("essence_cost", 0)
    if essence_cost > 0 and (getattr(player, "celestial_essence", 0) or 0) < essence_cost:
        return {"can": False, "reason_key": "tempering_need_essence", "next_info": next_info}

    effective_bp = total_battle_power if total_battle_power is not None else player.battle_power
    if effective_bp < next_info["min_battle_power"]:
        return {"can": False, "reason_key": "tempering_need_power", "next_info": next_info}

    if player.spirit_stones < next_info["cost_stones"]:
        return {"can": False, "reason_key": "tempering_need_stones", "next_info": next_info}

    if player.qi < next_info["cost_qi"]:
        return {"can": False, "reason_key": "tempering_need_qi", "next_info": next_info}

    if player.body_tempering_progress < next_info["progress_required"]:
        return {"can": False, "reason_key": "tempering_need_progress", "next_info": next_info}

    return {"can": True, "reason_key": None, "next_info": next_info}


def perform_tempering(player) -> dict:
    """
    Execute body tempering transformation. Deducts resources, levels up.
    Must call can_temper() first to validate.
    Returns {"success": True, "new_level": int, "mult": float}
    """
    next_level = player.body_tempering_level + 1
    info = TEMPERING_LEVELS[next_level]

    player.spirit_stones = max(0, player.spirit_stones - info["cost_stones"])
    player.qi = max(0.0, player.qi - info["cost_qi"])
    essence_cost = info.get("essence_cost", 0)
    if essence_cost > 0:
        player.celestial_essence = max(0, (player.celestial_essence or 0) - essence_cost)
    player.body_tempering_progress = 0
    player.body_tempering_level = next_level

    # Permanent qi_capacity bonus per tempering level
    player.qi_capacity += QI_CAP_BONUS_PER_LEVEL

    # Celestial transformation flag — set on first celestial tempering level (10).
    if info.get("transforms_body"):
        player.body_transformed = True

    return {
        "success": True,
        "new_level": next_level,
        "mult": info["hp_def_mult"],
        "emoji": info["emoji"],
        "name_key": info["name_key"],
        "qi_cap_bonus": QI_CAP_BONUS_PER_LEVEL,
        "body_transformed": bool(info.get("transforms_body", False)),
        "essence_cost": essence_cost,
    }


def add_tempering_progress(player, amount: int) -> int:
    """
    Add progress toward the next body tempering transformation.
    Only works if player has unlocked tempering (realm >= 7) and isn't maxed.
    Returns the amount actually added.
    """
    if player.realm < MIN_REALM_REQUIRED:
        return 0
    if player.body_tempering_level >= MAX_TEMPERING_LEVEL:
        return 0
    next_info = TEMPERING_LEVELS.get(player.body_tempering_level + 1)
    if not next_info:
        return 0
    cap = next_info["progress_required"]
    old = player.body_tempering_progress or 0
    if old >= cap:
        return 0
    actual = min(amount, cap - old)
    player.body_tempering_progress = old + actual
    return actual
