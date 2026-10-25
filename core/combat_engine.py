import random
import math
import logging
from datetime import datetime, timezone

# 2026-09-15 — os dois `logger.exception` do `_unified_bonuses` viviam DENTRO
# de um `except`: sem este nome, um erro a buscar bonus virava NameError e
# derrubava a montagem do lutador em vez de degradar. O modulo nunca teve
# logger; os outros de `core/` usam este mesmo padrao.
logger = logging.getLogger(__name__)

MASTERY_STAGES = {
    1: {"name": "Beginner",          "name_pt": "Iniciante",          "name_es": "Principiante",  "mult": 1.0,  "xp_req": 0,     "emoji": "🔰"},
    2: {"name": "Small Achievement", "name_pt": "Pequena Realização", "name_es": "Pequeño Logro", "mult": 1.15, "xp_req": 100,   "emoji": "⭐"},
    3: {"name": "Large Achievement", "name_pt": "Grande Realização",  "name_es": "Gran Logro",    "mult": 1.35, "xp_req": 500,   "emoji": "🌟"},
    4: {"name": "Perfection",        "name_pt": "Perfeição",          "name_es": "Perfección",    "mult": 1.60, "xp_req": 2000,  "emoji": "💎"},
    5: {"name": "Transcendence",     "name_pt": "Transcendência",     "name_es": "Transcendencia","mult": 2.0,  "xp_req": 10000, "emoji": "🌸"},
}


def get_mastery_stage(mastery_level: int) -> dict:
    return MASTERY_STAGES.get(mastery_level, MASTERY_STAGES[1])


# ─── Technique Grades (F-8 — Mastery Evolution) ────────────────────────────

TECHNIQUE_GRADES = {
    "common":       {"mult": 1.0, "emoji": "⬜", "order": 0},
    "refined":      {"mult": 1.2, "emoji": "🟩", "order": 1},
    "perfected":    {"mult": 1.5, "emoji": "🟦", "order": 2},
    "transcendent": {"mult": 2.0, "emoji": "🟪", "order": 3},
    "celestial":    {"mult": 3.0, "emoji": "🟨", "order": 4},
}

# Requirements to upgrade to each grade: (min_mastery, stones_cost, scrolls_cost, needs_pill)
GRADE_UPGRADE_REQS = {
    "refined":      {"min_mastery": 3, "stones": 500,   "scrolls": 0,  "pill": None},
    "perfected":    {"min_mastery": 4, "stones": 2000,  "scrolls": 5,  "pill": None},
    "transcendent": {"min_mastery": 5, "stones": 10000, "scrolls": 10, "pill": "Transcendence Pill"},
    "celestial":    {"min_mastery": 5, "stones": 50000, "scrolls": 0,  "pill": None, "requires_tribulation": True},
}

GRADE_ORDER = ["common", "refined", "perfected", "transcendent", "celestial"]


def get_grade_info(grade: str) -> dict:
    return TECHNIQUE_GRADES.get(grade, TECHNIQUE_GRADES["common"])


def get_next_grade(current_grade: str) -> str | None:
    idx = GRADE_ORDER.index(current_grade) if current_grade in GRADE_ORDER else 0
    if idx + 1 < len(GRADE_ORDER):
        return GRADE_ORDER[idx + 1]
    return None


# ─── Combat Technique Equip Limits (F-8) ───────────────────────────────────

def get_max_combat_techniques(realm: int) -> int:
    """Return maximum number of combat techniques a player can equip based on realm."""
    if realm <= 2:
        return 2
    elif realm <= 5:
        return 3
    elif realm <= 8:
        return 4
    else:
        return 5


# ─── Stances (Combat v2 — Etapa 1) ─────────────────────────────────────────

STANCES = {
    "offensive":  {"atk_mult": 1.20, "def_mult": 0.85, "emoji": "🗡️"},
    "balanced":   {"atk_mult": 1.00, "def_mult": 1.00, "emoji": "⚖️"},
    "defensive":  {"atk_mult": 0.90, "def_mult": 1.25, "emoji": "🛡️"},
}


def apply_stance_and_focus(fighter: dict, stance: str = "balanced", focus_tech_id: int = 0) -> dict:
    """Apply pre-battle stance and technique focus modifiers to fighter data (mutates in place)."""
    st = STANCES.get(stance, STANCES["balanced"])
    fighter["bp"] = int(fighter["bp"] * st["atk_mult"])
    fighter["defense_boost"] = fighter.get("defense_boost", 1.0) * st["def_mult"]
    fighter["stance"] = stance
    # v16.7 — the shared damage core (core/combat_model) reads the combat_profile,
    # NOT fighter['bp']/['defense_boost']. Mirror the stance onto the profile so
    # offensive/defensive picks actually bite: atk_mult → STRIKE (pill_strike),
    # def_mult → mitigation (pill_red, signed so offensive stance is squishier;
    # effective_reduction clamps the total to ≥0).
    prof = fighter.get("combat_profile")
    if isinstance(prof, dict):
        prof["pill_strike"] = float(prof.get("pill_strike", 1.0)) * st["atk_mult"]
        prof["pill_red"] = float(prof.get("pill_red", 0.0)) + (st["def_mult"] - 1.0)

    if focus_tech_id and fighter.get("techniques"):
        for tech in fighter["techniques"]:
            if tech["id"] == focus_tech_id:
                tech["effect_value"] = tech["effect_value"] * 1.50
            else:
                tech["effect_value"] = tech["effect_value"] * 0.75
        fighter["focus_tech_id"] = focus_tech_id

    return fighter


def _accumulate_tech_activations(activations: dict, techniques: list, round_num: int, effect_types: list):
    for tech in techniques:
        if tech["effect_type"] in effect_types:
            if tech["effect_round"] == 0 or tech["effect_round"] == round_num:
                tid = tech["id"]
                activations[tid] = activations.get(tid, 0) + 1


from core.game_logic import (
    get_player_equipment_stats,
    calculate_total_stats,
    format_number,
    get_realm_display,
)
from core.i18n import t
from config import (
    REALM_NAMES,
    REALM_MULTIPLIERS,
    MAX_ROUNDS,
    SPARRING_REWARD_MIN,
    SPARRING_REWARD_MAX,
    ELO_K_FACTOR,
    ARENA_BASE_REWARD,
    CURRENT_SEASON,
    ARENA_QUEUE_TIMEOUT_SECONDS,
    ARENA_ELO_RANGE,
    CHALLENGE_EXPIRY_SECONDS
)

def calculate_hp(player) -> float:
    """v16.7 — Três Tesouros two-pool HP (CORE_HP + sqrt-capped Soul-Shield).

    Replaces the old `(soul*100 + qi*50)*realm_mult` where soul gave ~250x more
    HP/point than offense (the root of the HP-stack meta). Now durability comes
    from body/qi/tempering (CORE_HP) and soul adds only a capped Soul-Shield, so
    stacking soul is a DAMAGE play, not an invincibility play. Single formula
    shared with combat via core/combat_model.combat_hp."""
    from core.combat_model import combat_hp, qi_band
    from core.body_tempering_engine import body_durability_mult
    # v16.7-K (keystone, server-gated): band the qi feeding the HP pool so an
    # uncapped qi pill can't dominate HP. main → defaults (qi_band_s=0) → raw qi
    # (byte-for-byte legacy). Any failure → legacy passthrough (never break HP).
    try:
        from database.db import get_world_balance
        _qbs = float(get_world_balance().get("qi_band_s", 0.0) or 0.0)
    except Exception:
        _qbs = 0.0
    # Sprint 3: band-aware body durability (R7+ Nine Transformations · R0–R6 Mortal
    # band, server-gated). main/OFF → 1.0 for R<7 and the legacy mult for R7+ → the
    # 57 stay byte-identical; only a `cultivo_corpo_r0` world feels the Mortal band.
    tempering_hp = body_durability_mult(player)
    return combat_hp(
        soul=player.soul_strength or 0,
        qi=qi_band(player.qi_capacity or 0, _qbs),
        bp=getattr(player, "battle_power", 0) or 0,
        realm=player.realm or 0,
        tempering_hp=tempering_hp,
    )


def unified_combat_hp(player, eff_soul, eff_qi, eff_bp, realm_eff=None) -> float:
    """Combate Unificado (gated) HP — IDENTICAL two-pool model as calculate_hp
    (same qi_band keystone + body durability), but reads the EFFECTIVE
    (equip/foundation/core/Dao-all-stats/companion-folded) soul/qi/bp instead of the
    RAW player fields. This closes the structural lie the audit found: legacy
    calculate_hp reads raw stats, so gear/foundation/Dao raised your STRIKE but never
    your HP pool. Called ONLY from build_fighter_data behind `combate_unificado`;
    `main` never reaches it → the 57 keep the raw-stat HP byte-for-byte.

    Wave 3 — ``realm_eff`` (the fractional realm+sub_layer) is passed so the HP
    pool scales with the sub-level grind too (combat_hp → realm_mult interpolates).
    ``None`` (default) falls back to the raw integer realm (an integral realm_eff
    interpolates to the exact same value → no change for sub_layer 1)."""
    from core.combat_model import combat_hp, qi_band
    from core.body_tempering_engine import body_durability_mult, get_tempering_multiplier
    try:
        from database.db import get_world_balance
        _qbs = float(get_world_balance().get("qi_band_s", 0.0) or 0.0)
    except Exception:
        _qbs = 0.0
    tempering_hp = body_durability_mult(player)
    # HONESTY (apply body tempering EXACTLY ONCE): calculate_total_stats already folds
    # get_tempering_multiplier(body_tempering_level) into eff_bp + eff_qi (NOT soul).
    # At R7+ that equals tempering_hp, so combat_hp's own tempering_hp would SQUARE it
    # on the bp/qi terms — the exact double-count display_combat_power warns about.
    # Strip the folded copy so tempering_hp is the sole application, matching legacy
    # calculate_hp semantics (which reads raw, un-tempered bp/qi). R0-R6: folded=1.0 → no-op.
    _folded = get_tempering_multiplier(int(getattr(player, "body_tempering_level", 0) or 0))
    if _folded and _folded != 1.0:
        eff_bp = float(eff_bp or 0) / _folded
        eff_qi = float(eff_qi or 0) / _folded
    return combat_hp(
        soul=eff_soul or 0,
        qi=qi_band(eff_qi or 0, _qbs),
        bp=eff_bp or 0,
        realm=(realm_eff if realm_eff is not None else (player.realm or 0)),
        tempering_hp=tempering_hp,
    )


def get_max_hp(player) -> float:
    """Calculate the player's max HP pool."""
    return calculate_hp(player)


def get_current_hp(player) -> float:
    """Return current HP; NULL in DB means full HP."""
    max_hp = get_max_hp(player)
    if player.current_hp is None:
        return max_hp
    return min(player.current_hp, max_hp)


def apply_hp_drain(player, damage_taken: float, drain_pct: float = 0.3):
    """Apply persistent HP loss after combat. Returns HP lost."""
    current = get_current_hp(player)
    hp_loss = damage_taken * drain_pct
    new_hp = max(0.0, current - hp_loss)
    player.current_hp = new_hp
    return hp_loss


def apply_hp_drain_scaled(player, damage_taken: float, combat_max_hp: float,
                          drain_pct: float = 0.3):
    """Post-combat HP drain, RECONCILED to the pool ``current_hp`` lives in.

    BUGFIX 2026-07-26 ([jogador], s2 Explore): ``player.current_hp`` is persisted on the
    RAW ``calculate_hp`` scale, but under ``combate_unificado`` the combat pool
    (``duel.hp_a_max`` / ``simulate_combat`` fighter hp) is the EFFECTIVE pool —
    gear/foundation/Dao/companion-folded, often ≥2× the raw pool. Draining an
    effective-unit ``damage_taken`` straight off the raw ``current_hp`` (legacy
    ``apply_hp_drain``) over-drains: a comfortable WIN (plenty of combat HP left)
    could floor the raw pool to 0. We drain the same *fraction* of health lost,
    mapped onto the raw pool: ``damage × raw_max / combat_max``.

    GATED by ``combate_unificado`` (the flag that created the two-scale world) so
    ``main``/OFF keeps the EXACT legacy drain — byte-identical for the 57
    (Lei §11). On OFF the effective pool is unused, so no reconciliation is owed.
    """
    dmg = float(damage_taken or 0.0)
    try:
        from database.db import feature_enabled_for_world
        if feature_enabled_for_world("combate_unificado") and combat_max_hp and float(combat_max_hp) > 0:
            raw_max = get_max_hp(player)
            dmg = dmg * (raw_max / float(combat_max_hp))
    except Exception:
        # Any failure → legacy passthrough (never break the drain / current_hp).
        dmg = float(damage_taken or 0.0)
    return apply_hp_drain(player, dmg, drain_pct=drain_pct)


def restore_hp(player, amount: float) -> float:
    """Restore HP by a flat amount. Returns actual HP restored."""
    max_hp = get_max_hp(player)
    current = get_current_hp(player)
    new_hp = min(max_hp, current + amount)
    actual = new_hp - current
    player.current_hp = new_hp
    return actual


def restore_hp_pct(player, pct: float) -> float:
    """Restore HP by a percentage of max HP. Returns actual HP restored."""
    max_hp = get_max_hp(player)
    return restore_hp(player, max_hp * pct)


# Wave 3 cleanup — the legacy `get_armor_bonus` (bp_flat×0.002 → armor_a/b
# columns) was dead: the value was written to the fighter dict + the DuelSession
# armor_a/armor_b columns but NEVER read by any damage math (mitigation lives in
# combat_model.effective_reduction via bp/qi/armor_rating). Removed; the fighter
# `armor_bonus` field is now a constant 0.0 and the armor_a/b writes are gone
# (the columns remain, defaulting to 0.0, since we never DROP columns on a live DB).


def build_fighter_data(player, equipped_artifacts: list, active_techniques: list, pet_ability: dict = None, companion_bonus: dict = None, buff_mults: dict = None, dao_bonuses: dict = None, faction_bonuses: dict = None, interior_bonuses: dict = None, achievement_bonuses: dict = None) -> dict:
    equip_stats = get_player_equipment_stats(equipped_artifacts)

    # ── Combate Unificado (gated `combate_unificado`; OFF on main → identical) ──
    # Fold EVERY legit combat source into the CLEAN stats that BOTH the strike and
    # the HP pool read, so equip/foundation/core/Dao-all-stats + interior techniques
    # + achievements actually bite. OFF: total_stats has no interior, clean_stats
    # strips Dao (dao=None), HP reads raw — EXACT legacy behavior (the 57 unchanged).
    try:
        from database.db import feature_enabled_for_world as _ffe
        _unified = bool(_ffe("combate_unificado"))
    except Exception:
        _unified = False
    # ── sub_layer bites (Wave 3, gated) ──────────────────────────────────────
    # Grinding sub-levels 1→9 inside a realm was ZERO combat power (only the whole
    # realm counted). Feed a FRACTIONAL realm = realm + (sub-1)/SUB_LAYERS to the
    # strike + HP so the sub-level grind smoothly scales power (realm_mult
    # interpolates). OFF → plain integer realm → interpolation is a no-op →
    # byte-identical. sub_layer is clamped [1..SUB_LAYERS] against stray beta data.
    _realm_eff = player.realm or 0
    if _unified:
        from config import SUB_LAYERS_PER_REALM as _SLPR
        _sl = min(max(int(getattr(player, "sub_layer", 1) or 1), 1), _SLPR)
        _realm_eff = (player.realm or 0) + (_sl - 1) / _SLPR
        # Dao all_stats_mult now bites: keep it in clean stats but strip bp_mult
        # (that stays routed via the dao_index apex below → no double-count).
        _combat_dao = dict(dao_bonuses) if dao_bonuses else None
        if _combat_dao is not None:
            _combat_dao["bp_mult"] = 1.0
        # Interior/meditation technique passives (soul/percep/luck) now reach the
        # strike + HP (via clean_stats) AND the display — not just the stat panel.
        total_stats = calculate_total_stats(player, equip_stats, companion_bonus, dao_bonuses, interior_bonuses=interior_bonuses)
        clean_stats = calculate_total_stats(player, equip_stats, companion_bonus, dao_bonuses=_combat_dao, interior_bonuses=interior_bonuses)
        # Achievements: the bp_mult the UI already promises ("+X% BP") now actually
        # bites the fight — applied to the CLEAN battle_power that feeds strike + HP.
        # (Only the real combat stat, not the weighted display aggregate, so it isn't
        # over-credited onto the soul/qi components.) cb_mult stays a cultivation-
        # speed bonus (folded in the CB tick, not here); evasion is a Wave-3 wire.
        _ach_bp = float((achievement_bonuses or {}).get("bp_mult", 1.0) or 1.0)
        if _ach_bp and _ach_bp != 1.0:
            clean_stats = dict(clean_stats)
            clean_stats["battle_power"] = float(clean_stats.get("battle_power", 0)) * _ach_bp
    else:
        total_stats = calculate_total_stats(player, equip_stats, companion_bonus, dao_bonuses)
        clean_stats = calculate_total_stats(player, equip_stats, companion_bonus, dao_bonuses=None)

    # TEC-5 — as artes PROIBIDAS não despertam fora do duelo verdadeiro.
    # `simulate_combat` soma TODAS as equipadas passivamente (spar, caçada NPC,
    # pisos de masmorra, exploração): sem esta exclusão o poder proibido
    # ativaria DE GRAÇA em 5 chamadas / ~7 superfícies, sem karma e sem anos.
    # O filtro vive AQUI (o único ponto onde a lista do lutador se materializa)
    # e não no somador, senão a arte continuaria a aparecer no log de golpes e a
    # render XP de maestria — o engine diria uma coisa e a tela outra (Lei §10).
    # O duelo NÃO passa por aqui com técnicas (duel_engine chama com [] e
    # atribui a sua própria lista) — é lá que a proibição funciona e cobra.
    # Flag OFF ⇒ `_forbidden` vazio ⇒ lista byte-idêntica (OFF-identity).
    try:
        from core.forbidden_path_engine import forbidden_ids as _fp_ids
        _forbidden = _fp_ids()
    except Exception:
        _forbidden = frozenset()
    techniques = []
    for pt in active_techniques:
        if _forbidden:
            try:
                if int(getattr(pt, "technique_id", 0) or 0) in _forbidden:
                    continue
            except (TypeError, ValueError):
                pass
        grade = pt.grade if hasattr(pt, "grade") else "common"
        grade_mult = get_grade_info(grade)["mult"]
        techniques.append({
            "id": pt.technique_id,
            "effect_type": pt.effect_type if hasattr(pt, "effect_type") else None,
            "effect_value": pt.effect_value if hasattr(pt, "effect_value") else 0,
            "effect_round": pt.effect_round if hasattr(pt, "effect_round") else 0,
            "name": pt.name if hasattr(pt, "name") else "???",
            "emoji": pt.emoji if hasattr(pt, "emoji") else "⚔️",
            "mastery_level": pt.mastery_level if hasattr(pt, "mastery_level") else 1,
            "grade_mult": grade_mult,
            # D3 (v16.6): per-tech intent affinity, mirroring duel_engine. Lets
            # simulate_combat apply the Intent passive aura. None if the source
            # object doesn't carry it (NPC techs / untagged) → no passive.
            "intent_affinity": getattr(pt, "intent_affinity", None),
        })

    # ── Display battle power (WITH Dao) — used by pet damage / world boss /
    #    legacy surfaces. The v16.7 damage core does NOT read this; it reads the
    #    combat_profile below (clean STRIKE + separate DAO term). Kept so display
    #    and non-duel legacy paths stay intact.
    bp = total_stats["total_battle_power"]
    # HP pool: unified → effective clean stats (gear/foundation/Dao make you TANKIER
    # too, closing the audit's structural lie); legacy → raw-stat calculate_hp.
    hp = (unified_combat_hp(player, clean_stats["soul_strength"], clean_stats["qi_capacity"], clean_stats["battle_power"], realm_eff=_realm_eff)
          if _unified else calculate_hp(player))  # v16.7 two-pool Três Tesouros HP
    if companion_bonus:
        hp = hp * companion_bonus.get("hp_mult", 1.0)

    defense_boost = 1.0
    bp_boost = soul_boost = 1.0
    # Combate Unificado: perception/luck BUFF pills+formations (all_boost fan-out,
    # divine_eye Formação) now bite crit + penetration. Legacy (OFF): 1.0 → identical.
    percep_boost = luck_boost = 1.0
    if buff_mults:
        bp_boost = buff_mults.get("bp_boost", 1.0)
        soul_boost = buff_mults.get("soul_boost", 1.0)
        defense_boost = buff_mults.get("defense_boost", 1.0)
        bp = int(bp * bp_boost)
        if _unified:
            percep_boost = float(buff_mults.get("perception_boost", 1.0) or 1.0)
            luck_boost = float(buff_mults.get("luck_boost", 1.0) or 1.0)

    faction_dmg = 1.0
    foundation_bonus = 0.0
    if faction_bonuses:
        faction_dmg = 1.0 + float(faction_bonuses.get("combat_damage_bonus", 0) or 0)
        foundation_bonus = float(faction_bonuses.get("foundation_bonus", 0) or 0)
        if faction_dmg > 1.0:
            bp = int(bp * faction_dmg)           # display bp reflects faction
        if foundation_bonus > 0:
            hp = hp * (1 + foundation_bonus)      # celestial durability (pool + display)

    # F-11.5: Supreme Celestial Body (tempering tier 12) regenerates a % of max
    # HP per combat round.
    from core.body_tempering_engine import get_celestial_body_bonuses, body_durability_mult
    body_bonuses = get_celestial_body_bonuses(getattr(player, "body_tempering_level", 0) or 0)
    celestial_hp_regen_pct = body_bonuses.get("combat_hp_regen_pct", 0.0)

    # ── v16.7 — COMBAT PROFILE (Três Tesouros). The shared damage core
    #    (core/combat_model.compute_attack) reads THIS in BOTH engines, so spar
    #    and arena can never diverge. STRIKE uses CLEAN stats (no Dao); the Dao is
    #    routed as its own apex multiplier (dao_index); pills/faction/luck/
    #    perception become explicit model terms. Persisted in the duel JSONB
    #    snapshot so the duel resolves deterministically off it.
    from core.combat_model import make_profile
    # clean_stats computed once above (unified-aware). dao_index carries bp_mult as
    # the apex multiplier (kept separate from clean bp → never double-counted).
    dao_index = max(0.0, float((dao_bonuses or {}).get("bp_mult", 1.0)) - 1.0)
    # Sprint 3: band-aware durability (Mortal band below R7, server-gated; Nine
    # Transformations at R7+). Feeds both the HP pool (via calculate_hp) and the
    # mitigation term below. main/OFF → identical to the legacy tempering mult.
    tempering_hp = body_durability_mult(player)
    tempering_red = min(0.30, max(0.0, (tempering_hp - 1.0) * 0.25))
    # v16.7-K (keystone, server-gated): band the qi COMBAT contribution and apply
    # Limitação Corporal (body caps EXPRESSED power). main → defaults (0) → no-op.
    try:
        from database.db import get_world_balance as _gwb
        _bal = _gwb()
    except Exception:
        _bal = {}
    _qi_band_s = float(_bal.get("qi_band_s", 0.0) or 0.0)
    _throttle = 1.0
    if float(_bal.get("body_throttle_enabled", 0.0) or 0.0) > 0:
        from core.combat_model import body_throttle as _body_throttle
        from core.body_tempering_engine import body_stage_for_gap as _bsfg
        _throttle = _body_throttle(
            player.realm or 0,
            _bsfg(getattr(player, "body_tempering_level", 0) or 0, player.realm or 0,
                  getattr(player, "mortal_body_level", 0) or 0),
            base=float(_bal.get("body_throttle_base", 0.0) or 0.0),
            cap=int(float(_bal.get("body_throttle_cap", 0.0) or 0.0)),
        )
    combat_profile = make_profile(
        soul=clean_stats["soul_strength"] * soul_boost,   # soul_boost pill → Shen (strike + Soul-Shield)
        qi=clean_stats["qi_capacity"],
        bp=clean_stats["battle_power"],                    # clean kinetic bp (no Dao)
        realm=_realm_eff,                                  # sub_layer bites (gated): fractional realm; OFF → int → no-op
        dao_index=dao_index,                               # the apex multiplier
        tempering_hp=tempering_hp,
        tempering_red=tempering_red,
        armor_rating=float((equip_stats or {}).get("armor_rating", 0) or 0),
        path_red=min(0.15, foundation_bonus * 0.5),        # celestial faction → mitigation
        pill_red=max(0.0, defense_boost - 1.0),            # defense pill → mitigation
        pill_strike=bp_boost,                              # bp_boost pill → STRIKE
        faction_dmg=faction_dmg,                           # Demonic +dmg
        luck=clean_stats.get("luck", 0) * luck_boost,      # → crit chance (+luck buff when unified)
        perception=clean_stats.get("perception", 0) * percep_boost,  # → penetration + crit dmg (+percep buff)
        regen_pct=celestial_hp_regen_pct,
        qi_band_s=_qi_band_s,                              # keystone: band qi in STRIKE+mitigation (server-gated)
        tempering=_throttle,                               # Limitação Corporal: strike-only throttle (gated, OFF on main)
    )
    # Keep the meaningful-minimum floor honest vs the ACTUAL pool (which includes
    # companion hp_mult / faction foundation), not just the base combat_hp.
    combat_profile["eff_hp"] = hp

    fighter = {
        "telegram_id": player.telegram_id,
        "name": player.dao_name or player.display_name or player.username or t("en", "combat_default_name"),
        "bp": bp,
        "hp": hp,
        "armor_bonus": 0.0,  # legacy field (was bp_flat×0.002 → armor_a/b, never read) — Wave 3 zeroed it
        "realm": player.realm,
        "sub_layer": player.sub_layer,
        "techniques": techniques,
        "pet_ability": pet_ability,
        "defense_boost": defense_boost,
        "celestial_hp_regen_pct": celestial_hp_regen_pct,
        # v16.7 — the Três Tesouros combat profile (the shared damage core reads this).
        "combat_profile": combat_profile,
        # D3 (v16.6): empty by default — a caller that wants the Intent passive
        # aura applied in simulate_combat must overwrite this with the player's
        # effective intent ranks (snapshot_intent_ranks). NPC fighters leave it
        # empty → no aura.
        "intent_ranks": {},
    }
    # Companion evasion (Wave 3, gated): the pet's `evasion_mult` (e.g. Wind Sparrow
    # 1.05) was produced by get_companion_bonuses and read by NOTHING. Surface the
    # extra evasion (as a flat chance delta) so both engines' evasion rolls pick it
    # up. Key present ONLY when unified → OFF fighter dict stays byte-identical, and
    # NPCs (no companion_bonus) get 0.
    if _unified and companion_bonus:
        fighter["companion_evasion"] = max(0.0, float(companion_bonus.get("evasion_mult", 1.0) or 1.0) - 1.0)
    return fighter


async def get_combat_buff_multiplier(session, player_id: int, buff_type: str) -> float:
    """Returns the multiplier of an active buff for combat."""
    from core.alchemy_engine import get_active_buffs
    buffs = await get_active_buffs(session, player_id)
    for b in buffs:
        if b.buff_type == buff_type:
            return b.buff_value
    return 1.0


async def get_combat_buff_mults(session, player_id: int) -> dict:
    """Fetches all combat-relevant buff multipliers for a player."""
    from core.alchemy_engine import get_active_buffs
    buffs = await get_active_buffs(session, player_id)
    mults = {}
    for b in buffs:
        # perception_boost/luck_boost are read ONLY by the unified fighter (gated);
        # legacy build_fighter_data ignores them, so adding them here is harmless OFF.
        if b.buff_type in ("bp_boost", "soul_boost", "defense_boost", "perception_boost", "luck_boost"):
            mults[b.buff_type] = b.buff_value
    return mults


async def is_pvp_sealed(session, player_id: int) -> bool:
    """Hotfix "A Volta" 2026-07-07 (#12) — "Selo de Supressão Celestial".

    Um buff-flag `pvp_sealed` (row em player_buffs com expiry distante, ex.
    2099) EXCLUI a conta de iniciar/receber PvP (arena, desafios, duelos e
    guerra de seita) SEM tocar nos stats dela (Lei: não punir beta — caso
    [jogador], único a escapar do reset). É DATA, não schema: aplicado/removido
    pelo owner via INSERT/DELETE em player_buffs; nenhum outro sistema lê o
    tipo (get_combat_buff_mults usa whitelist; consumo de buff é
    type-specific; só buffs EXPIRADOS são purgados)."""
    from core.alchemy_engine import get_active_buffs
    buffs = await get_active_buffs(session, player_id)
    return any(b.buff_type == "pvp_sealed" for b in buffs)


# H-12 (v13): hard cap for evasion (prevents 100% vs 100% stalemate loops).
EVASION_HARD_CAP = 0.90
# After this many consecutive rounds where neither side took damage, force a hit.
NO_DAMAGE_BREAK_AFTER = 5


def _get_technique_bonus(techniques: list, round_num: int, effect_type: str) -> float:
    bonus = 0.0
    for tech in techniques:
        if tech["effect_type"] != effect_type:
            continue
        target_round = tech["effect_round"]
        if target_round == 0 or target_round == round_num:
            mastery_mult = MASTERY_STAGES.get(tech["mastery_level"], MASTERY_STAGES[1])["mult"]
            grade_mult = tech.get("grade_mult", 1.0)
            bonus += tech["effect_value"] * mastery_mult * grade_mult
    return bonus


def _aggregate_intent_passive(fighter: dict) -> dict:
    """Intent passive aura for a fighter in simulate_combat (D3, v16.6).

    duel_engine applies the passive of the single technique swung that round;
    simulate_combat has no "swung" tech (it sums all equipped techniques), so
    we aggregate across the intents the fighter's active techniques carry,
    taking the MAX per bonus-type. Each bonus type is owned by one intent family
    (sword/fist/killing→damage_mult, body→damage_reduce, dao→armor_ignore,
    killing→evasion), so MAX = "that intent family's rank" and a fighter who has
    mastered two families gets both — bounded to one family's contribution per type.

    Returns {} (no-op) when intent_ranks is absent — which is how NPC fighters
    and surfaces that don't opt in (e.g. World Boss) stay aura-free.
    """
    ranks = fighter.get("intent_ranks") or {}
    if not ranks:
        return {}
    from core.intent_engine import get_passive_bonus
    seen = {t.get("intent_affinity") for t in fighter.get("techniques", []) if t.get("intent_affinity")}
    agg: dict[str, float] = {}
    for intent in seen:
        pb = get_passive_bonus(intent, int(ranks.get(intent, 0)))
        for k, v in pb.items():
            if float(v) > agg.get(k, 0.0):
                agg[k] = float(v)
    return agg


from core import combat_model as _cm


def _profile_of(fighter: dict) -> dict:
    """v16.7 — the fighter's Três Tesouros combat profile, or a safe fallback.

    Players/NPCs built post-v16.7 carry 'combat_profile'. The fallback (realm=0
    so the model does NOT re-multiply an already-scaled bp) keeps a legacy fighter
    dict from crashing the shared damage core."""
    p = (fighter or {}).get("combat_profile")
    if p:
        return p
    return _cm.make_profile(soul=0.0, qi=0.0, bp=float((fighter or {}).get("bp", 0) or 0), realm=0)


async def get_unified_combat_bonuses(session, player_id: int):
    """Combate Unificado (gated) — fetch the interior-technique + achievement stat
    bonuses that the unified fighter folds into combat. Returns (None, None) when
    `combate_unificado` is OFF so `main`/legacy paths pay ZERO extra queries and
    stay byte-identical. Best-effort: a lookup failure degrades to None, never
    crashes fighter assembly."""
    try:
        from database.db import feature_enabled_for_world
        if not feature_enabled_for_world("combate_unificado"):
            return None, None
    except Exception:
        return None, None
    interior = ach = None
    try:
        from core.game_logic import get_active_technique_bonuses
        interior = await get_active_technique_bonuses(session, player_id)
    except Exception:
        logger.exception("unified interior bonuses fetch failed player=%s", player_id)
    try:
        # Wave 3 — use the DELTA-correct multipliers (1+Σ(val-1)), not the legacy
        # additive-raw get_achievement_stat_bonuses (1.05+1.05=2.10 would wreck bp).
        # For today's single bp_mult achievement this equals the old value (1.10);
        # it only diverges (correctly) once a second bp_mult achievement stacks.
        from core.achievement_engine import get_achievement_combat_multipliers
        ach = await get_achievement_combat_multipliers(session, player_id)
    except Exception:
        logger.exception("unified achievement bonuses fetch failed player=%s", player_id)
    return interior, ach


async def build_player_combat_fighter(session, player, *, lang: str = "pt") -> dict:
    """Assemble a player's full combat fighter dict for simulate_combat / PvE.

    This is the canonical assembly that spar / npc-hunt / dungeon-floor each
    duplicate inline (equipped artifacts + active combat techniques + buff mults
    + companion + Dao + faction bonuses + Intent aura). Onda 5 factors it into a
    single shared helper so the Reinos Exploráveis trash encounters fight with
    the SAME power the player has everywhere else (a subtly-weaker fighter would
    make the player lose "trash" fights and feel like a bug). Purely ADDITIVE:
    existing callers keep their inline assembly; only new surfaces call this.

    Best-effort: each optional bonus source is guarded so a single lookup
    failure never produces a crippled fighter."""
    from sqlalchemy import select as _select
    from database.models import PlayerArtifact, PlayerTechnique, TechniqueCatalog

    arts = (await session.execute(
        _select(PlayerArtifact).where(
            PlayerArtifact.player_id == player.telegram_id,
            PlayerArtifact.is_equipped == True,  # noqa: E712
        )
    )).scalars().all()

    tech_rows = (await session.execute(
        _select(PlayerTechnique, TechniqueCatalog)
        .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
        .where(
            PlayerTechnique.player_id == player.telegram_id,
            PlayerTechnique.is_active_combat == True,  # noqa: E712
            TechniqueCatalog.tech_type == "combat",
        )
    )).all()
    active_techs = []
    for pt, tc in tech_rows:
        obj = type("_T", (), {})()
        obj.technique_id = tc.id
        obj.effect_type = tc.effect_type
        obj.effect_value = tc.effect_value
        obj.effect_round = tc.effect_round
        # O nome vai para `combat_log.rounds_data` (JSONB PERSISTIDO) e esse log
        # e' lido pelos DOIS lutadores, que podem falar linguas diferentes. O
        # evento gravado e' uma string JA' composta (`"tech": "⚔️ Thunder Step"`)
        # e NAO leva o id, portanto nao ha' como resolver por espectador no
        # momento de desenhar. Traduzir aqui gravaria a lingua do atacante no
        # ecra do defensor — a mesma classe de erro de "notificacao NUNCA ganha
        # placeholder novo". Fechar isto e' por o `tech_id` no evento (aditivo;
        # as rows antigas continuam a cair na string) e resolver no
        # renderizador: trabalho proprio, nao deste lote.
        # 名-CRU: log de combate persistido, lido por dois espectadores, sem id.
        obj.name = tc.name
        obj.emoji = tc.emoji
        obj.mastery_level = pt.mastery_level
        obj.intent_affinity = getattr(tc, "intent_affinity", None)  # D3 (v16.6)
        active_techs.append(obj)

    buff_mults = await get_combat_buff_mults(session, player.telegram_id)
    comp_bonus = None
    pet_ability = None
    try:
        from core.beast_engine import get_companion_beast, get_companion_bonuses, get_pet_combat_ability
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        comp_bonus = get_companion_bonuses(comp_beast, comp_catalog)
        # [jogador] 2026-06-11: pet special ability was never wired anywhere.
        pet_ability = get_pet_combat_ability(comp_catalog, comp_beast,
                                             player.language or "pt")
    except Exception:
        pass
    dao_bonuses = None
    try:
        from core.dao_engine import get_player_dao_bonuses
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, int(player.realm or 0))
    except Exception:
        pass
    fac_bonuses = None
    try:
        from core.faction_engine import get_faction_bonuses
        fac_bonuses = await get_faction_bonuses(session, player.telegram_id)
    except Exception:
        pass

    interior_b, ach_b = await get_unified_combat_bonuses(session, player.telegram_id)
    fighter = build_fighter_data(
        player, arts, active_techs,
        pet_ability=pet_ability,
        buff_mults=buff_mults, companion_bonus=comp_bonus,
        dao_bonuses=dao_bonuses, faction_bonuses=fac_bonuses,
        interior_bonuses=interior_b, achievement_bonuses=ach_b,
    )
    try:
        from core.intent_engine import snapshot_intent_ranks
        fighter["intent_ranks"] = await snapshot_intent_ranks(session, player)
    except Exception:
        pass
    return fighter


def simulate_combat(attacker: dict, defender: dict, mode: str = "sparring") -> dict:
    atk_hp = attacker["hp"]
    def_hp = defender["hp"]
    atk_max_hp = atk_hp
    def_max_hp = def_hp

    rounds = []
    winner = None
    shadow_step_atk = any(tech["effect_type"] == "dodge" for tech in attacker["techniques"])
    shadow_step_def = any(tech["effect_type"] == "dodge" for tech in defender["techniques"])
    dodge_used_atk = False
    dodge_used_def = False
    pet_used_atk = False
    pet_used_def = False
    no_damage_streak = 0  # H-12: anti-stalemate counter

    atk_tech_act: dict = {}
    def_tech_act: dict = {}

    # D3 (v16.6): Intent passive aura — applied here so a player's soul-mastery
    # matters in farm (chat spar/hunt, dungeon trash), not only in formal duels.
    # Empty for NPCs and for surfaces that don't inject intent_ranks.
    atk_ipb = _aggregate_intent_passive(attacker)
    def_ipb = _aggregate_intent_passive(defender)

    for round_num in range(1, MAX_ROUNDS + 1):
        round_data = {"round": round_num, "events": []}
        atk_hp_round_start = atk_hp
        def_hp_round_start = def_hp

        if round_num == 1:
            atk_pet = attacker.get("pet_ability")
            if atk_pet and not pet_used_atk:
                pet_used_atk = True
                pet_dmg = attacker["bp"] * atk_pet["damage_mult"] * random.uniform(0.9, 1.1)
                pet_dmg = max(1, pet_dmg)
                def_hp -= pet_dmg
                round_data["events"].append({
                    "type": "pet_attack",
                    "who": "attacker",
                    "damage": int(pet_dmg),
                    "pet_name": f"{atk_pet['emoji']} {atk_pet['name']}",
                    "ability": atk_pet["special_ability"],
                })
            def_pet = defender.get("pet_ability")
            if def_pet and not pet_used_def:
                pet_used_def = True
                pet_dmg = defender["bp"] * def_pet["damage_mult"] * random.uniform(0.9, 1.1)
                pet_dmg = max(1, pet_dmg)
                atk_hp -= pet_dmg
                round_data["events"].append({
                    "type": "pet_attack",
                    "who": "defender",
                    "damage": int(pet_dmg),
                    "pet_name": f"{def_pet['emoji']} {def_pet['name']}",
                    "ability": def_pet["special_ability"],
                })

            if def_hp <= 0:
                def_hp = 0
                round_data["defender_hp"] = 0
                round_data["attacker_hp"] = int(atk_hp)
                rounds.append(round_data)
                winner = "attacker"
                break
            if atk_hp <= 0:
                atk_hp = 0
                round_data["attacker_hp"] = 0
                round_data["defender_hp"] = int(def_hp)
                rounds.append(round_data)
                winner = "defender"
                break

        # --- Attacker's turn ---
        evasion_bonus = _get_technique_bonus(defender["techniques"], round_num, "evasion")
        evasion_bonus += def_ipb.get("evasion", 0.0)  # D3: Killing-intent evasion aura
        evasion_bonus += float(defender.get("companion_evasion", 0.0) or 0.0)  # Wave 3: companion evasion_mult (gated → 0 OFF)
        # H-12: cap evasion roll so combat cannot hit infinite-dodge stalemate.
        evasion_bonus = min(evasion_bonus, EVASION_HARD_CAP)
        if evasion_bonus > 0 and random.random() < evasion_bonus:
            tech_names = [tc["emoji"] + " " + tc["name"] for tc in defender["techniques"] if tc["effect_type"] == "evasion"]
            round_data["events"].append({
                "type": "evasion",
                "who": "defender",
                "tech": tech_names[0] if tech_names else "Evasion",
            })
            _accumulate_tech_activations(def_tech_act, defender["techniques"], round_num, ["evasion"])
        else:
            if not dodge_used_def and shadow_step_def and round_num <= 3 and random.random() < 0.5:
                dodge_used_def = True
                tech_names = [tech["emoji"] + " " + tech["name"] for tech in defender["techniques"] if tech["effect_type"] == "dodge"]
                round_data["events"].append({
                    "type": "dodge",
                    "who": "defender",
                    "tech": tech_names[0] if tech_names else "Shadow Step",
                })
                _accumulate_tech_activations(def_tech_act, defender["techniques"], round_num, ["dodge"])
            else:
                dmg_mult_bonus = _get_technique_bonus(attacker["techniques"], round_num, "damage_mult")
                armor_ignore = _get_technique_bonus(attacker["techniques"], round_num, "armor_ignore")
                # D3: attacker's offensive intent aura (sword/fist/killing → dmg, dao → armor_ignore)
                dmg_mult_bonus += atk_ipb.get("damage_mult", 0.0)
                armor_ignore += atk_ipb.get("armor_ignore", 0.0)
                technique_bonus = dmg_mult_bonus

                dmg_reduce = _get_technique_bonus(defender["techniques"], round_num, "damage_reduce")
                dmg_reduce += def_ipb.get("damage_reduce", 0.0)  # D3: body-intent defense aura
                # v16.7 — shared Três Tesouros damage core (parity with duel_engine):
                # technique damage_mult/armor_ignore + defender damage_reduce feed in
                # as per-round overrides on top of the stat profiles. Proportional
                # mitigation + capped Dao-penetration + Heavenly-Pressure ramp +
                # meaningful-minimum floor (no 1-HP chip). (simulate has no per-swing
                # matchup → intent_matchup defaults 1.0; the passive aura is in
                # technique_bonus via _aggregate_intent_passive above.)
                _hit = _cm.compute_attack(
                    _profile_of(attacker), _profile_of(defender), round_num,
                    tech_dmg=technique_bonus, tech_reduce=dmg_reduce, tech_armor_ignore=armor_ignore,
                    rng=random,
                )
                net_dmg = max(1, _hit["net"])
                atk_dmg = _hit["raw"]

                def_hp -= net_dmg
                _accumulate_tech_activations(atk_tech_act, attacker["techniques"], round_num, ["damage_mult", "armor_ignore"])
                _accumulate_tech_activations(def_tech_act, defender["techniques"], round_num, ["damage_reduce"])
                round_data["events"].append({
                    "type": "attack",
                    "who": "attacker",
                    "damage": int(net_dmg),
                    "raw_damage": int(atk_dmg),
                    "blocked": int(max(0, atk_dmg * _hit.get("reduction", 0.0))),
                    "techniques_used": [
                        tech["emoji"] + " " + tech["name"]
                        for tech in attacker["techniques"]
                        if tech["effect_type"] in ("damage_mult", "armor_ignore")
                        and (tech["effect_round"] == 0 or tech["effect_round"] == round_num)
                    ],
                })

        if def_hp <= 0:
            def_hp = 0
            round_data["defender_hp"] = 0
            round_data["attacker_hp"] = int(atk_hp)
            rounds.append(round_data)
            winner = "attacker"
            break

        # --- Defender's turn ---
        evasion_bonus_atk = _get_technique_bonus(attacker["techniques"], round_num, "evasion")
        evasion_bonus_atk += atk_ipb.get("evasion", 0.0)  # D3: Killing-intent evasion aura
        evasion_bonus_atk += float(attacker.get("companion_evasion", 0.0) or 0.0)  # Wave 3: companion evasion_mult (gated → 0 OFF)
        # H-12: cap evasion roll so combat cannot hit infinite-dodge stalemate.
        evasion_bonus_atk = min(evasion_bonus_atk, EVASION_HARD_CAP)
        if evasion_bonus_atk > 0 and random.random() < evasion_bonus_atk:
            tech_names = [tc["emoji"] + " " + tc["name"] for tc in attacker["techniques"] if tc["effect_type"] == "evasion"]
            round_data["events"].append({
                "type": "evasion",
                "who": "attacker",
                "tech": tech_names[0] if tech_names else "Evasion",
            })
            _accumulate_tech_activations(atk_tech_act, attacker["techniques"], round_num, ["evasion"])
        else:
            if not dodge_used_atk and shadow_step_atk and round_num <= 3 and random.random() < 0.5:
                dodge_used_atk = True
                tech_names = [tech["emoji"] + " " + tech["name"] for tech in attacker["techniques"] if tech["effect_type"] == "dodge"]
                round_data["events"].append({
                    "type": "dodge",
                    "who": "attacker",
                    "tech": tech_names[0] if tech_names else "Shadow Step",
                })
                _accumulate_tech_activations(atk_tech_act, attacker["techniques"], round_num, ["dodge"])
            else:
                dmg_mult_bonus = _get_technique_bonus(defender["techniques"], round_num, "damage_mult")
                armor_ignore = _get_technique_bonus(defender["techniques"], round_num, "armor_ignore")
                # D3: defender's offensive intent aura (now they swing back)
                dmg_mult_bonus += def_ipb.get("damage_mult", 0.0)
                armor_ignore += def_ipb.get("armor_ignore", 0.0)
                technique_bonus = dmg_mult_bonus

                dmg_reduce = _get_technique_bonus(attacker["techniques"], round_num, "damage_reduce")
                dmg_reduce += atk_ipb.get("damage_reduce", 0.0)  # D3: attacker's body-intent defense aura
                # v16.7 — shared Três Tesouros damage core (parity with duel_engine).
                _hit = _cm.compute_attack(
                    _profile_of(defender), _profile_of(attacker), round_num,
                    tech_dmg=technique_bonus, tech_reduce=dmg_reduce, tech_armor_ignore=armor_ignore,
                    rng=random,
                )
                net_dmg = max(1, _hit["net"])
                def_dmg = _hit["raw"]

                atk_hp -= net_dmg
                _accumulate_tech_activations(def_tech_act, defender["techniques"], round_num, ["damage_mult", "armor_ignore"])
                _accumulate_tech_activations(atk_tech_act, attacker["techniques"], round_num, ["damage_reduce"])
                round_data["events"].append({
                    "type": "attack",
                    "who": "defender",
                    "damage": int(net_dmg),
                    "raw_damage": int(def_dmg),
                    "blocked": int(max(0, def_dmg * _hit.get("reduction", 0.0))),
                    "techniques_used": [
                        tech["emoji"] + " " + tech["name"]
                        for tech in defender["techniques"]
                        if tech["effect_type"] in ("damage_mult", "armor_ignore")
                        and (tech["effect_round"] == 0 or tech["effect_round"] == round_num)
                    ],
                })

        if atk_hp <= 0:
            atk_hp = 0
            round_data["attacker_hp"] = 0
            round_data["defender_hp"] = int(def_hp)
            rounds.append(round_data)
            winner = "defender"
            break

        # F-11.5: Celestial Body (tempering tier 12) — passive HP regen per round.
        atk_regen_pct = attacker.get("celestial_hp_regen_pct", 0.0)
        def_regen_pct = defender.get("celestial_hp_regen_pct", 0.0)
        if atk_regen_pct > 0 and atk_hp < atk_max_hp:
            atk_hp = min(atk_max_hp, atk_hp + atk_max_hp * atk_regen_pct)
        if def_regen_pct > 0 and def_hp < def_max_hp:
            def_hp = min(def_max_hp, def_hp + def_max_hp * def_regen_pct)

        # H-12: detect stalemate streak and force a hit after NO_DAMAGE_BREAK_AFTER rounds.
        if atk_hp >= atk_hp_round_start - 0.5 and def_hp >= def_hp_round_start - 0.5:
            no_damage_streak += 1
        else:
            no_damage_streak = 0

        if no_damage_streak >= NO_DAMAGE_BREAK_AFTER:
            forced_pct = 0.05 * (no_damage_streak - (NO_DAMAGE_BREAK_AFTER - 1))
            atk_pct = atk_hp / max(atk_max_hp, 1)
            def_pct = def_hp / max(def_max_hp, 1)
            if atk_pct <= def_pct:
                forced = atk_max_hp * forced_pct
                atk_hp = max(0.0, atk_hp - forced)
                round_data["events"].append({
                    "type": "stalemate_break",
                    "who": "attacker",
                    "damage": int(forced),
                })
            else:
                forced = def_max_hp * forced_pct
                def_hp = max(0.0, def_hp - forced)
                round_data["events"].append({
                    "type": "stalemate_break",
                    "who": "defender",
                    "damage": int(forced),
                })

        round_data["attacker_hp"] = int(atk_hp)
        round_data["defender_hp"] = int(def_hp)
        rounds.append(round_data)

        # End immediately if stalemate-break killed somebody.
        if atk_hp <= 0:
            winner = "defender"
            break
        if def_hp <= 0:
            winner = "attacker"
            break

    if winner is None:
        # H-12: round limit reached — compare % HP remaining (more meaningful
        # than absolute HP for asymmetric matchups). True ties fall back to draw.
        atk_pct = atk_hp / max(atk_max_hp, 1)
        def_pct = def_hp / max(def_max_hp, 1)
        if atk_pct > def_pct:
            winner = "attacker"
        elif def_pct > atk_pct:
            winner = "defender"
        else:
            winner = "draw"

    winner_id = None
    loser_id = None
    if winner == "attacker":
        winner_id = attacker["telegram_id"]
        loser_id = defender["telegram_id"]
    elif winner == "defender":
        winner_id = defender["telegram_id"]
        loser_id = attacker["telegram_id"]

    reward = 0
    if mode == "sparring":
        reward = calculate_sparring_reward(attacker["bp"], defender["bp"])
    elif mode == "arena":
        reward = ARENA_BASE_REWARD

    return {
        "winner": winner,
        "winner_id": winner_id,
        "loser_id": loser_id,
        "rounds": rounds,
        "attacker_hp_final": int(max(0, atk_hp)),
        "defender_hp_final": int(max(0, def_hp)),
        "attacker_max_hp": int(atk_max_hp),
        "defender_max_hp": int(def_max_hp),
        "attacker_damage_taken": max(0, atk_max_hp - max(0, atk_hp)),
        "defender_damage_taken": max(0, def_max_hp - max(0, def_hp)),
        "spirit_stones_reward": reward,
        "total_rounds": len(rounds),
        "attacker_tech_activations": atk_tech_act,
        "defender_tech_activations": def_tech_act,
    }


def calculate_sparring_reward(atk_bp: int, def_bp: int) -> int:
    ratio = min(def_bp, atk_bp) / max(def_bp, atk_bp, 1)
    base = SPARRING_REWARD_MIN + int((SPARRING_REWARD_MAX - SPARRING_REWARD_MIN) * ratio)
    return max(0, base + random.randint(-50, 50))


def calculate_arena_reward(winner_elo: int) -> int:
    tier_bonus = max(0, (winner_elo - 1000)) // 100 * 50
    return ARENA_BASE_REWARD + tier_bonus + random.randint(0, 100)


def calculate_elo_change(winner_elo: int, loser_elo: int) -> tuple[int, int]:
    expected_win = 1.0 / (1.0 + math.pow(10, (loser_elo - winner_elo) / 400.0))
    expected_lose = 1.0 - expected_win

    winner_delta = int(ELO_K_FACTOR * (1 - expected_win))
    loser_delta = int(ELO_K_FACTOR * (0 - expected_lose))

    return max(1, winner_delta), min(-1, loser_delta)


def generate_combat_narration(result: dict, attacker_name: str, defender_name: str, lang: str = "en") -> str:
    lines = []
    lines.append(t(lang, "combat_narration_header", attacker=attacker_name, defender=defender_name))
    lines.append(t(lang, "combat_narration_separator"))
    lines.append("")

    for rnd in result["rounds"]:
        round_num = rnd["round"]
        lines.append(t(lang, "combat_narration_round", round=round_num))

        for event in rnd["events"]:
            actor = attacker_name if event["who"] == "attacker" else defender_name
            target = defender_name if event["who"] == "attacker" else attacker_name

            if event["type"] == "pet_attack":
                lines.append(t(lang, "combat_pet_attack", actor=actor, pet_name=event['pet_name'], damage=format_number(event['damage']), ability=event['ability']))
            elif event["type"] == "evasion":
                lines.append(t(lang, "combat_evasion", target=target, tech=event['tech']))
            elif event["type"] == "stalemate_break":
                # H-12: heavens force a hit when both sides keep dodging.
                victim = attacker_name if event["who"] == "attacker" else defender_name
                lines.append(t(lang, "combat_stalemate_break", target=victim, damage=format_number(event['damage'])))
            elif event["type"] == "dodge":
                lines.append(t(lang, "combat_dodge", target=target, tech=event['tech']))
            elif event["type"] == "attack":
                tech_text = ""
                if event.get("techniques_used"):
                    tech_text = " " + " ".join(event["techniques_used"]) + " →"

                if event["blocked"] > 0:
                    lines.append(t(lang, "combat_attack_blocked", actor=actor, tech_text=tech_text, damage=format_number(event['damage']), blocked=format_number(event['blocked'])))
                else:
                    lines.append(t(lang, "combat_attack", actor=actor, tech_text=tech_text, damage=format_number(event['damage'])))

        atk_hp_display = format_number(rnd.get("attacker_hp", 0))
        def_hp_display = format_number(rnd.get("defender_hp", 0))
        lines.append(t(lang, "combat_hp_display", name=attacker_name, hp=atk_hp_display))
        lines.append(t(lang, "combat_hp_display", name=defender_name, hp=def_hp_display))
        lines.append("")

    lines.append(t(lang, "combat_narration_separator"))

    if result["winner"] == "draw":
        lines.append(t(lang, "combat_draw"))
        lines.append(t(lang, "combat_draw_desc"))
    elif result["winner"] == "attacker":
        lines.append(t(lang, "combat_winner", name=attacker_name))
        lines.append(t(lang, "combat_winner_desc", name=attacker_name))
    else:
        lines.append(t(lang, "combat_winner", name=defender_name))
        lines.append(t(lang, "combat_winner_desc", name=defender_name))

    return "\n".join(lines)


# D-Combat #2 (v16.6): difficulty is a SINGLE power axis = stat_mult. realm_offset
# is now COSMETIC ONLY (the realm shown on the NPC for flavour). Previously the
# offset ALSO jumped REALM_MULTIPLIERS (~2.5x per realm) and compounded with
# stat_mult into a silent ~3.5x (hard) to ~12x (nightmare) blowout. stat_mult was
# re-tuned (hard 1.3→1.5, nightmare 1.8→2.5) so the legible single axis still feels
# overwhelming at the top end.
NPC_DIFFICULTIES = {
    "easy":      {"realm_offset": -1, "stat_mult": 0.7, "qi_cost": 10,  "loot_mult": 0.5,  "emoji": "🟢"},
    "normal":    {"realm_offset": 0,  "stat_mult": 1.0, "qi_cost": 25,  "loot_mult": 1.0,  "emoji": "🟡"},
    "hard":      {"realm_offset": 1,  "stat_mult": 1.5, "qi_cost": 50,  "loot_mult": 2.0,  "emoji": "🔴"},
    "nightmare": {"realm_offset": 2,  "stat_mult": 2.5, "qi_cost": 100, "loot_mult": 4.0,  "emoji": "💀"},
}

NPC_LOOT_TABLE = {
    "easy": [
        {"type": "spirit_stones", "min": 50, "max": 200, "chance": 1.0},
        {"type": "herb", "tier": 1, "qty": 1, "chance": 0.3},
        {"type": "pill", "id": 27, "qty": 1, "chance": 0.15},
    ],
    "normal": [
        {"type": "spirit_stones", "min": 100, "max": 500, "chance": 1.0},
        {"type": "herb", "tier": 2, "qty": 1, "chance": 0.3},
        {"type": "core_essence", "qty": 2, "chance": 0.2},
        {"type": "ore", "tier": 1, "qty": 1, "chance": 0.2},
        {"type": "pill", "id": 27, "qty": 1, "chance": 0.15},
    ],
    "hard": [
        {"type": "spirit_stones", "min": 300, "max": 1000, "chance": 1.0},
        {"type": "herb", "tier": 3, "qty": 1, "chance": 0.4},
        {"type": "core_essence", "qty": 5, "chance": 0.3},
        {"type": "technique_scroll", "qty": 1, "chance": 0.05},
        {"type": "pill", "id": 28, "qty": 1, "chance": 0.15},
    ],
    "nightmare": [
        {"type": "spirit_stones", "min": 500, "max": 2000, "chance": 1.0},
        {"type": "herb", "tier": 4, "qty": 1, "chance": 0.5},
        {"type": "core_essence", "qty": 10, "chance": 0.5},
        {"type": "technique_scroll", "qty": 1, "chance": 0.15},
        {"type": "beast_trap", "rarity": "rare", "qty": 1, "chance": 0.1},
        {"type": "pill", "id": 29, "qty": 1, "chance": 0.12},
    ],
}

def generate_npc_fighter(target_elo: int = 1000, lang: str = "en", difficulty: str = None, player_realm: int = 0) -> dict:
    npc_names = [t(lang, f"combat_npc_{i}") for i in range(1, 10)]

    if difficulty and difficulty in NPC_DIFFICULTIES:
        diff_data = NPC_DIFFICULTIES[difficulty]
        # realm_display is COSMETIC. Power scales off the PLAYER's realm × stat_mult.
        realm_display = max(0, min(10, player_realm + diff_data["realm_offset"]))
        tier = max(0, min(player_realm, len(REALM_MULTIPLIERS) - 1))
        sm = diff_data["stat_mult"]
        # v16.7 — NPCs are statted on the SAME RAW scale as a player at this realm
        # (the combat model applies realm_mult), scaled by the difficulty stat_mult.
        # NPCs carry NO Dao (dao_index 0) → a player's Leis are a real edge in PvE.
        base_soul = 50 * (tier + 1) * sm * random.uniform(0.9, 1.1)
        base_qi = 50 * (tier + 1) * sm * random.uniform(0.9, 1.1)
        base_bp = 450 * (tier + 1) * sm * random.uniform(0.9, 1.1)
        prof = _cm.make_profile(soul=base_soul, qi=base_qi, bp=base_bp, realm=tier,
                                perception=30 * (tier + 1) * sm)
        return {
            "telegram_id": 0,
            "name": f"{diff_data['emoji']} {random.choice(npc_names)}",
            "bp": max(50, int(_cm.strike_value(base_soul, base_bp, base_qi, tier))),
            "hp": max(500.0, prof["eff_hp"]),
            "armor_bonus": 0.0,
            "realm": realm_display,
            "sub_layer": random.randint(1, 9),
            "techniques": [],
            "combat_profile": prof,
        }
    else:
        tier = max(0, min(10, (target_elo - 800) // 200))
        sm = max(0.5, target_elo / 1000.0)
        base_soul = 40 * (tier + 1) * sm * random.uniform(0.9, 1.1)
        base_qi = 40 * (tier + 1) * sm * random.uniform(0.9, 1.1)
        base_bp = 360 * (tier + 1) * sm * random.uniform(0.9, 1.1)
        prof = _cm.make_profile(soul=base_soul, qi=base_qi, bp=base_bp, realm=tier,
                                perception=25 * (tier + 1) * sm)
        return {
            "telegram_id": 0,
            "name": f"🤖 {random.choice(npc_names)}",
            "bp": max(50, int(_cm.strike_value(base_soul, base_bp, base_qi, tier))),
            "hp": max(500.0, prof["eff_hp"]),
            "armor_bonus": 0.0,
            "realm": tier,
            "sub_layer": random.randint(1, 9),
            "techniques": [],
            "combat_profile": prof,
        }
