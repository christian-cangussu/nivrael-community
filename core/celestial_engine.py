"""
Celestial System — Mahayana (Realm 8) progression gates.

Four pillars:
  1. Celestial Trials (sub-layers 1, 5, 9) — must pass each to advance further in Mahayana.
  2. Heavenly Dao — unlocks a tier-5 multiplier when the player has mastered enough tier-4+ Dao paths.
  3. Celestial Body Transformation — Body Tempering tier 10 flips body_transformed = True.
  4. Celestial Artifacts — grade 8 gear, only forgeable at Mahayana (see forge_seeds.py recipes 26-28).

Failure penalty is 50% CB loss within the current realm (player keeps realm 8).
6h cooldown after failure before retry (reduced from 12h — 2026-04-24 patch).
"""
import random
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DaoPath, DaoPathLaw, PlayerDaoDiscovery, PlayerArtifact, ArtifactCatalog


MAHAYANA_REALM = 8

# v14.3 D-6a — Apex constants. Trigger = realm 10 + sub_layer 9 + 100/100
# Heavenly Daos + 3/3 Celestial Trials. Reward = achievement_id 21 + title +
# 500 jade. Grants once via PlayerAchievement.unlocked_at uniqueness.
APEX_REALM = 10
APEX_SUB_LAYER = 9
APEX_TRIALS_REQ = 3
APEX_HEAVENLY_LAWS_REQ = 100
APEX_JADE_REWARD = 500
APEX_ACHIEVEMENT_ID = 21
APEX_EVENT_TYPE = "apex_reached"

# Which sub-layers need a trial cleared before advancing further.
# trial_num: 1 = first, 2 = second, 3 = third.
TRIAL_GATES = {1: 1, 5: 2, 9: 3}

# Trial metadata — used for UI + balancing.
TRIALS = {
    1: {
        "name_key": "celestial_trial_1_name",
        "desc_key": "celestial_trial_1_desc",
        "emoji": "⚡",
        "base_power": 18000,   # harder than a R8 tribulation round
        "rounds": 5,
        "essence_reward": 50,
        "trib_bonus_unlock": 0.05,   # passive +5% tribulation chance once passed
    },
    2: {
        "name_key": "celestial_trial_2_name",
        "desc_key": "celestial_trial_2_desc",
        "emoji": "🌀",
        "base_power": 28000,
        "rounds": 7,
        "essence_reward": 120,
        "trib_bonus_unlock": 0.10,
    },
    3: {
        "name_key": "celestial_trial_3_name",
        "desc_key": "celestial_trial_3_desc",
        "emoji": "☯️",
        "base_power": 45000,
        "rounds": 9,
        "essence_reward": 300,
        "trib_bonus_unlock": 0.15,
    },
}

MAX_TRIALS = 3
FAILURE_CB_LOSS = 0.50
FAILURE_CB_LOSS_INSURED = 0.10   # Heavenly Shield Talisman: 10% instead of 50%
FAILURE_COOLDOWN_HOURS = 6       # Reduced from 12h — 2026-04-24

# Heavenly Dao — requires N tier-4+ paths to grant its bonus.
HEAVENLY_DAO_MIN_PATHS = 5        # need 5 paths at Perfection/Dao-Heart to unlock
HEAVENLY_DAO_BONUS_PER_PATH = 0.05   # +5% all_mult per qualifying path
HEAVENLY_DAO_MAX_BONUS = 0.25     # capped at +25%


# ─── Trials ──────────────────────────────────────────────────────────────────

def get_next_trial_num(player) -> int | None:
    """Return the trial number (1-3) the player is currently gated by, or None."""
    if player.realm != MAHAYANA_REALM:
        return None
    passed = player.celestial_trials_passed or 0
    if passed >= MAX_TRIALS:
        return None
    gate_needed = TRIAL_GATES.get(player.sub_layer)
    if gate_needed is None or passed >= gate_needed:
        return None
    return passed + 1


def can_attempt_trial(player) -> dict:
    """Check whether the player can attempt their next Celestial Trial right now."""
    if player.realm != MAHAYANA_REALM:
        return {"can": False, "reason_key": "celestial_need_mahayana", "trial_num": None}
    passed = player.celestial_trials_passed or 0
    if passed >= MAX_TRIALS:
        return {"can": False, "reason_key": "celestial_all_passed", "trial_num": None}
    trial_num = passed + 1

    expected_sub = {1: 1, 2: 5, 3: 9}.get(trial_num)
    if expected_sub is not None and player.sub_layer < expected_sub:
        return {"can": False, "reason_key": "celestial_need_sublayer", "trial_num": trial_num, "need_sub": expected_sub}

    cd = player.celestial_trial_cooldown_until
    if cd and cd > datetime.now(timezone.utc):
        remaining = int((cd - datetime.now(timezone.utc)).total_seconds())
        return {"can": False, "reason_key": "celestial_on_cooldown", "trial_num": trial_num, "remaining": remaining}

    return {"can": True, "reason_key": None, "trial_num": trial_num}


def _compute_per_round_chance(
    total_soul: int,
    total_bp: int,
    trial_info: dict,
    heavenly_dao_bonus: float = 0.0,
    tribulation_bonus_3000: float = 0.0,
    trib_blessing_bonus: float = 0.0,
) -> float:
    """
    Per-round survival chance. Uses POST-multiplier stats (foundation, core,
    companion, equipment, dao, body) so a well-geared Mahayana player actually
    feels stronger than a naked one. Heavenly Dao, 3000 Dao Tribulation path,
    and Tribulation Blessing pill all add to the final chance.

    Tuning target: moderate Mahayana gear ≈ 75% trial 1, 60% trial 2, 45% trial 3.
    With Heavenly Dao + Blessing, trial 3 moves up to ~70%.
    """
    power = trial_info["base_power"]
    # Scale: soul weighs ~45 points of mitigation, bp weighs ~0.25 point (bp is already huge).
    mitigation = max(total_soul * 45 + total_bp * 0.25, 1.0)

    # Base chance scaled to what Mahayana players actually have.
    # power / mitigation is typically small (0.001–0.05) for trial 1,
    # slightly higher for trial 3. Multiply by 4 so the gap feels real.
    base = 1.0 - (power / mitigation) * 4.0

    bonus = heavenly_dao_bonus + tribulation_bonus_3000 + trib_blessing_bonus
    chance = base + bonus
    # F-11.5 tuning: cap bumped from 0.97 to 0.99. At 0.97 per-round, trial 3
    # (9 rounds) caps at 76% full-clear even with max gear — a handful of
    # well-prepared players hit long failure streaks. At 0.99 per-round, trial 3
    # caps at ~91%, which is what endgame players actually feel they've earned.
    return max(0.25, min(0.99, chance))


def estimate_trial_chance(
    player,
    total_soul: int,
    total_bp: int,
    heavenly_dao_bonus: float = 0.0,
    tribulation_bonus_3000: float = 0.0,
    trib_blessing_bonus: float = 0.0,
) -> dict:
    """Preview the chance of clearing the next trial with given stats + bonuses."""
    passed_so_far = player.celestial_trials_passed or 0
    trial_num = passed_so_far + 1
    info = TRIALS.get(trial_num)
    if not info:
        return {"available": False, "trial_num": None}

    per_round = _compute_per_round_chance(
        total_soul, total_bp, info,
        heavenly_dao_bonus=heavenly_dao_bonus,
        tribulation_bonus_3000=tribulation_bonus_3000,
        trib_blessing_bonus=trib_blessing_bonus,
    )
    full_clear = per_round ** info["rounds"]
    return {
        "available": True,
        "trial_num": trial_num,
        "rounds": info["rounds"],
        "base_power": info["base_power"],
        "per_round_chance": per_round,
        "full_clear_chance": full_clear,
        "heavenly_dao_bonus": heavenly_dao_bonus,
        "tribulation_bonus_3000": tribulation_bonus_3000,
        "trib_blessing_bonus": trib_blessing_bonus,
    }


def attempt_trial(
    player,
    total_soul: int,
    total_bp: int = 0,
    heavenly_dao_bonus: float = 0.0,
    tribulation_bonus_3000: float = 0.0,
    trib_blessing_bonus: float = 0.0,
    insurance_active: bool = False,
) -> dict:
    """
    Simulate the trial roll. Uses the player's TOTAL stats (post-multiplier),
    matching what they see in /status — so equipment, foundation, core, body,
    companion and dao actually count.

    Bonuses (all additive on per-round chance):
      - heavenly_dao_bonus: from 5+ tier-4 Dao paths (capped 0.25)
      - tribulation_bonus_3000: from 3000 Dao Laws "Tribulation" category paths
      - trib_blessing_bonus: Tribulation Blessing pill (0.15 when active)

    insurance_active=True consumes a Heavenly Shield Talisman externally and
    reduces the failure CB loss from 50% to 10%.
    """
    passed_so_far = player.celestial_trials_passed or 0
    trial_num = passed_so_far + 1
    info = TRIALS.get(trial_num)
    if not info:
        return {"success": False, "reason_key": "celestial_all_passed"}

    per_round = _compute_per_round_chance(
        total_soul, total_bp, info,
        heavenly_dao_bonus=heavenly_dao_bonus,
        tribulation_bonus_3000=tribulation_bonus_3000,
        trib_blessing_bonus=trib_blessing_bonus,
    )
    rounds = info["rounds"]

    success_rounds = 0
    for _ in range(rounds):
        if random.random() < per_round:
            success_rounds += 1
        else:
            break

    passed = success_rounds >= rounds
    now = datetime.now(timezone.utc)

    if passed:
        player.celestial_trials_passed = trial_num
        player.celestial_essence = (player.celestial_essence or 0) + info["essence_reward"]
        player.celestial_trial_cooldown_until = None
        return {
            "success": True,
            "trial_num": trial_num,
            "essence_gained": info["essence_reward"],
            "rounds_total": rounds,
            "rounds_survived": success_rounds,
            "survival_chance": per_round,
        }

    # Failure: CB loss within realm + cooldown. Insurance softens the blow.
    cb_loss = FAILURE_CB_LOSS_INSURED if insurance_active else FAILURE_CB_LOSS
    player.cultivation_base = max(0.0, (player.cultivation_base or 0.0) * (1.0 - cb_loss))
    player.celestial_trial_cooldown_until = now + timedelta(hours=FAILURE_COOLDOWN_HOURS)
    return {
        "success": False,
        "trial_num": trial_num,
        "rounds_total": rounds,
        "rounds_survived": success_rounds,
        "survival_chance": per_round,
        "cb_loss_pct": int(cb_loss * 100),
        "cooldown_hours": FAILURE_COOLDOWN_HOURS,
        "insurance_used": insurance_active,
    }


# ─── Heavenly Dao ────────────────────────────────────────────────────────────

async def count_heavenly_paths(session: AsyncSession, player_id: int) -> int:
    """Count how many Dao paths the player has at tier 4+ (Perfection or Dao Heart)."""
    # A path has `total_laws` laws; tier 4 requires >= 90%.
    paths = (await session.execute(select(DaoPath))).scalars().all()
    if not paths:
        return 0
    count = 0
    for path in paths:
        discovered = (await session.execute(
            select(func.count(PlayerDaoDiscovery.law_id))
            .where(
                PlayerDaoDiscovery.player_id == player_id,
                PlayerDaoDiscovery.law_id.in_(
                    select(DaoPathLaw.id).where(DaoPathLaw.path_id == path.id)
                ),
            )
        )).scalar() or 0
        if path.total_laws > 0 and discovered / path.total_laws >= 0.90:
            count += 1
    return count


async def get_heavenly_dao_bonus(session: AsyncSession, player_id: int, player_realm: int) -> dict:
    """
    Return Heavenly Dao bonus info for a player. Only active at Mahayana+.
    { "paths": int, "qualifying": int, "all_mult_bonus": float, "unlocked": bool }
    """
    if player_realm < MAHAYANA_REALM:
        return {"paths": 0, "qualifying": 0, "all_mult_bonus": 0.0, "unlocked": False}
    qualifying = await count_heavenly_paths(session, player_id)
    if qualifying < HEAVENLY_DAO_MIN_PATHS:
        return {"paths": qualifying, "qualifying": 0, "all_mult_bonus": 0.0, "unlocked": False}
    extra = qualifying - HEAVENLY_DAO_MIN_PATHS + 1
    bonus = min(HEAVENLY_DAO_MAX_BONUS, extra * HEAVENLY_DAO_BONUS_PER_PATH)
    return {"paths": qualifying, "qualifying": qualifying, "all_mult_bonus": bonus, "unlocked": True}


# ─── Celestial Resonance (F-11.5) ────────────────────────────────────────────

# Set bonus from equipping grade-8 Celestial artifacts. Maxes out at 3 pieces;
# additional pieces beyond 3 do not stack further.
RESONANCE_BONUS_BY_PIECES = {
    0: 0.00,
    1: 0.05,
    2: 0.12,
    3: 0.20,
}


async def get_celestial_resonance(session: AsyncSession, player_id: int) -> dict:
    """
    Count equipped grade-8 (Celestial) artifacts and return the set bonus.
    Bonus applies as an additive multiplier on cb_mult, bp_mult and all_stats.
    """
    pieces = (await session.execute(
        select(func.count(PlayerArtifact.id))
        .join(ArtifactCatalog, PlayerArtifact.catalog_id == ArtifactCatalog.id)
        .where(
            PlayerArtifact.player_id == player_id,
            PlayerArtifact.is_equipped == True,
            ArtifactCatalog.grade == 8,
        )
    )).scalar() or 0
    pieces = int(pieces)
    capped = min(pieces, 3)
    bonus = RESONANCE_BONUS_BY_PIECES.get(capped, 0.20)
    return {"pieces": pieces, "bonus": bonus}


# ─── Aggregated passive bonuses from trials ──────────────────────────────────

def get_trial_passive_bonuses(player) -> dict:
    """Passive bonuses unlocked by passing trials (applied outside combat)."""
    passed = player.celestial_trials_passed or 0
    trib_bonus = 0.0
    for i in range(1, passed + 1):
        trib_bonus += TRIALS[i]["trib_bonus_unlock"]
    return {"tribulation_bonus": trib_bonus}


# ─── Apex unlock (D-6a) ──────────────────────────────────────────────────────

async def is_apex(session: AsyncSession, player) -> bool:
    """Check whether a player meets ALL Apex conditions right now.

    Pure read — no state change. Used both as a precondition for the Reflection
    Chamber (D-6b) and as the trigger predicate for the achievement (D-6a).
    """
    if (player.realm or 0) < APEX_REALM:
        return False
    if (player.sub_layer or 0) < APEX_SUB_LAYER:
        return False
    if (player.celestial_trials_passed or 0) < APEX_TRIALS_REQ:
        return False
    # Heavenly path discoveries: 100/100 → all_paths_complete
    from core.dao_laws_engine import count_heavenly_discoveries
    discovered, total = await count_heavenly_discoveries(session, player.telegram_id)
    if total <= 0 or discovered < APEX_HEAVENLY_LAWS_REQ or discovered < total:
        return False
    return True


async def try_grant_apex(session: AsyncSession, player) -> dict | None:
    """Idempotent grant. Returns dict with achievement + jade, or None if not eligible
    or already granted. Caller is responsible for sending the DM and committing.

    Wired in:
      - handlers/celestial.py after a successful trial 3 attempt
      - core/scheduler.py after a heavenly Dao law discovery
    Either path can be the "last" one — the achievement is unique so duplicate
    calls naturally short-circuit.
    """
    from sqlalchemy import select as _select
    from database.models import PlayerAchievement, AchievementCatalog

    # Skip if achievement already unlocked (idempotent — safe to call from
    # multiple sites without double-granting jade).
    pa = (await session.execute(
        _select(PlayerAchievement).where(
            PlayerAchievement.player_id == player.telegram_id,
            PlayerAchievement.achievement_id == APEX_ACHIEVEMENT_ID,
        )
    )).scalar_one_or_none()
    if pa is not None and pa.unlocked_at is not None:
        return None

    if not await is_apex(session, player):
        return None

    from core.achievement_engine import check_achievements
    unlocked = await check_achievements(session, player.telegram_id, APEX_EVENT_TYPE, 1)
    if not unlocked:
        # Race: another path already incremented to >= target. Resolve from DB.
        ach = (await session.execute(
            _select(AchievementCatalog).where(AchievementCatalog.id == APEX_ACHIEVEMENT_ID)
        )).scalar_one_or_none()
        if ach is None:
            return None
        unlocked = [ach]

    # 500 jade reward — only granted on the FIRST unlock. Once unlocked_at is
    # set, the early-return above ensures we never reach this branch again.
    from core.monetization import grant_jade
    await grant_jade(session, player, APEX_JADE_REWARD)

    return {
        "achievements": unlocked,
        "jade_reward": APEX_JADE_REWARD,
    }
