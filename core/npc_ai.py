"""v15.1.4 — NPC turn-based action picker.

Strategy:
  1. Reactive defensive: if NPC HP < 30% of max → 2× weight on
     damage_reduce / evasion / dodge techniques (heal-equivalent in this
     engine — they survive the next hit).
  2. Weighted random: weight = effect_value × mastery_mult × grade_mult.
     Higher-impact techniques fire more often, scaled by NPC mastery and
     difficulty grade (set in `npc_loadouts.DIFFICULTY_GRADE_MULT`).
  3. Affordability filter: only techniques with qi_cost ≤ current
     combat_qi are eligible. If none affordable → basic strike
     (technique_id=0, qi_cost=0).

No look-ahead, no opponent technique inspection. Owner brief said
"IA simples". Intent System v15.2 will replace this with intent-driven
counterplay (Sword vs Body, etc).
"""

from __future__ import annotations

import random
from typing import Iterable

from core.combat_engine import MASTERY_STAGES


# When the NPC is below this HP fraction, defensive techniques get a
# weight boost. Mirrors the player-side intuition (you'd shield up too).
REACTIVE_HP_THRESHOLD = 0.30
DEFENSIVE_WEIGHT_BONUS = 2.0
DEFENSIVE_EFFECT_TYPES = ("damage_reduce", "evasion", "dodge")


def _technique_weight(tech: dict, is_low_hp: bool) -> float:
    """Compute selection weight for a single technique.

    Returns 0 for invalid/empty entries so they get filtered out by the
    random.choices call.
    """
    try:
        effect_value = float(tech.get("effect_value", 0.0) or 0.0)
    except (TypeError, ValueError):
        effect_value = 0.0
    if effect_value <= 0:
        # Minimum weight so utility techs (e.g. armor_ignore = 0.3) still
        # get a chance even when effect_value is small.
        effect_value = 0.1

    mastery_level = int(tech.get("mastery_level", 1) or 1)
    mastery_mult = float(
        MASTERY_STAGES.get(mastery_level, MASTERY_STAGES[1])["mult"]
    )
    grade_mult = float(tech.get("grade_mult", 1.0) or 1.0)

    weight = effect_value * mastery_mult * grade_mult

    if is_low_hp and tech.get("effect_type") in DEFENSIVE_EFFECT_TYPES:
        weight *= DEFENSIVE_WEIGHT_BONUS

    return max(0.01, weight)


def pick_npc_action(
    npc_fighter: dict,
    npc_state: dict,
    opp_state: dict | None = None,
    round_num: int = 1,
) -> dict:
    """Pick a technique + qi_cost for the NPC's current round.

    Args:
        npc_fighter: fighter snapshot (same shape as duel.fighter_a/b) —
            must include `techniques` list with id/effect_type/effect_value/
            qi_cost/mastery_level/grade_mult.
        npc_state: `{ hp, hp_max, combat_qi }` — NPC's current vitals.
        opp_state: optional opponent vitals (currently unused; reserved
            for v15.2 intent counterplay).
        round_num: 1-indexed round number (used for `effect_round` filter).

    Returns:
        `{ technique_id, qi_cost, ai_reason }` — ai_reason is a debug
        label for the action_log (e.g. "reactive_defensive", "weighted",
        "fallback_basic").
    """
    techniques = list(npc_fighter.get("techniques") or [])
    combat_qi = int(npc_state.get("combat_qi") or 0)
    hp = float(npc_state.get("hp") or 0.0)
    hp_max = float(npc_state.get("hp_max") or 1.0)
    hp_pct = hp / hp_max if hp_max > 0 else 0.0
    is_low_hp = hp_pct < REACTIVE_HP_THRESHOLD

    # Filter affordable + round-eligible techniques.
    eligible: list[tuple[dict, float]] = []
    for tech in techniques:
        cost = int(tech.get("qi_cost") or 0)
        if cost > combat_qi:
            continue
        effect_round = int(tech.get("effect_round") or 0)
        if effect_round != 0 and effect_round != round_num:
            continue
        weight = _technique_weight(tech, is_low_hp)
        if weight > 0:
            eligible.append((tech, weight))

    if not eligible:
        return {
            "technique_id": 0,
            "qi_cost": 0,
            "ai_reason": "fallback_basic",
        }

    techs, weights = zip(*eligible)
    pick = random.choices(techs, weights=weights, k=1)[0]
    return {
        "technique_id": int(pick["id"]),
        "qi_cost": int(pick.get("qi_cost") or 0),
        "ai_reason": "reactive_defensive" if (
            is_low_hp and pick.get("effect_type") in DEFENSIVE_EFFECT_TYPES
        ) else "weighted",
    }


def summarize_pool(techniques: Iterable[dict]) -> list[dict]:
    """Debug helper — pure-data summary of an NPC technique pool.

    Returns [{id, name, effect_type, qi_cost, mastery_level, grade_mult}].
    Used by the duel state projection to render the opponent card chip
    "{archetype} carrying [Phoenix Strike, Iron Body, ...]".
    """
    out: list[dict] = []
    for tech in techniques or []:
        out.append({
            "id": int(tech.get("id") or 0),
            "name": tech.get("name") or "?",
            "emoji": tech.get("emoji") or "⚔️",
            "effect_type": tech.get("effect_type") or "?",
            "qi_cost": int(tech.get("qi_cost") or 0),
            "mastery_level": int(tech.get("mastery_level", 1) or 1),
            "grade_mult": float(tech.get("grade_mult", 1.0) or 1.0),
        })
    return out
