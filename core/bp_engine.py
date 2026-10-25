"""
Battle Pass Mission Engine.

Call update_bp_mission() from any game event to track player progress.
Supported objective_types:
  craft_pills, win_npc_fight, forge_artifact, win_sparring, complete_quests,
  foundation_trial, alchemy_tier, win_tribulation, complete_dungeon, golden_core

Missions can be:
  reset_type="none"   — one-time (complete once, worth 2 tier points)
  reset_type="daily"  — resets every day (worth 1 tier point per completion)
  reset_type="weekly" — resets every Monday (worth 1 tier point per completion)
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import CURRENT_SEASON
from database.models import BattlePassMission, PlayerBPMission, Player
from core.activity_indicators import _invalidate_cache as _inv_cache

# 名 2026-09-14 — o premio do Passe diz-se na lingua de quem o reclamou.
from core.i18n import catalog_name as _cname

logger = logging.getLogger(__name__)


# ── Reset helpers ────────────────────────────────────────────────────────────

def _should_reset(mission: BattlePassMission, pm: PlayerBPMission) -> bool:
    """Check if a repeatable mission should reset based on last_completed_at."""
    if mission.reset_type == "none":
        return False
    if not pm.is_completed:
        return False
    if not pm.last_completed_at:
        return False  # COMPAT: old rows without timestamp

    now = datetime.now(timezone.utc)
    last = pm.last_completed_at

    if mission.reset_type == "daily":
        # Reset if completed on a previous UTC day
        return last.date() < now.date()

    if mission.reset_type == "weekly":
        # Reset every Monday: find start of current week (Monday 00:00 UTC)
        today = now.date()
        week_start = today - timedelta(days=today.weekday())  # Monday
        return last.date() < week_start

    return False


def _reset_mission(pm: PlayerBPMission) -> None:
    """Reset a repeatable mission for a new period. times_completed stays."""
    pm.progress = 0
    pm.is_completed = False
    pm.claimed = False


async def _auto_reset_repeatables(session: AsyncSession, player_id: int) -> None:
    """Auto-reset any expired daily/weekly missions for a player."""
    stmt = (
        select(PlayerBPMission, BattlePassMission)
        .join(BattlePassMission, PlayerBPMission.mission_id == BattlePassMission.id)
        .where(
            PlayerBPMission.player_id == player_id,
            PlayerBPMission.season == CURRENT_SEASON,
            PlayerBPMission.is_completed == True,
            BattlePassMission.reset_type != "none",
        )
    )
    rows = (await session.execute(stmt)).all()
    for pm, mission in rows:
        if _should_reset(mission, pm):
            _reset_mission(pm)
            logger.debug("Reset repeatable mission %s (%s) for player %s",
                         mission.id, mission.reset_type, player_id)


# ── Core mission tracking ────────────────────────────────────────────────────

async def update_bp_mission(
    session: AsyncSession,
    player_id: int,
    objective_type: str,
    increment: int = 1,
) -> list[int]:
    """
    Increment progress for all active BP missions matching objective_type.
    Returns list of mission IDs that were just completed by this call.
    Auto-resets expired repeatables, then advances tier.
    """
    # Auto-reset expired repeatables before processing
    await _auto_reset_repeatables(session, player_id)

    stmt = select(BattlePassMission).where(BattlePassMission.objective_type == objective_type)
    missions = (await session.execute(stmt)).scalars().all()
    if not missions:
        return []

    pm_stmt = select(PlayerBPMission).where(
        PlayerBPMission.player_id == player_id,
        PlayerBPMission.season == CURRENT_SEASON,
        PlayerBPMission.mission_id.in_([m.id for m in missions]),
    )
    pm_map = {pm.mission_id: pm for pm in (await session.execute(pm_stmt)).scalars().all()}

    just_completed = []
    for mission in missions:
        pm = pm_map.get(mission.id)
        if pm is None:
            pm = PlayerBPMission(
                player_id=player_id,
                mission_id=mission.id,
                season=CURRENT_SEASON,
                progress=0,
                is_completed=False,
                claimed=False,
                times_completed=0,
            )
            session.add(pm)

        if pm.is_completed:
            continue

        pm.progress = min(pm.progress + increment, mission.objective_value)
        if pm.progress >= mission.objective_value:
            pm.is_completed = True
            pm.times_completed = (pm.times_completed or 0) + 1
            pm.last_completed_at = datetime.now(timezone.utc)
            just_completed.append(mission.id)
            logger.debug("Player %s completed BP mission %s (%s) [x%s]",
                         player_id, mission.id, mission.description_key, pm.times_completed)

    # Auto-advance tier when missions are completed
    if just_completed:
        await recalculate_bp_tier(session, player_id)
        _inv_cache(player_id)

    return just_completed


async def recalculate_bp_tier(session: AsyncSession, player_id: int) -> int | None:
    """
    Calculate BP tier from mission completions.
    - One-time missions (reset_type='none'): 2 tier points each (max 1 completion)
    - Daily/weekly missions: 1 tier point per completion (unlimited)
    Returns the new tier or None if no active BP.
    """
    from core.monetization import get_active_battle_pass

    bp = await get_active_battle_pass(session, player_id)
    if not bp:
        return None

    # Fetch all player missions with their mission definition
    stmt = (
        select(PlayerBPMission, BattlePassMission)
        .join(BattlePassMission, PlayerBPMission.mission_id == BattlePassMission.id)
        .where(
            PlayerBPMission.player_id == player_id,
            PlayerBPMission.season == CURRENT_SEASON,
        )
    )
    rows = (await session.execute(stmt)).all()

    total_points = 0
    for pm, mission in rows:
        tc = pm.times_completed or 0
        if tc <= 0:
            continue
        if mission.reset_type == "none":
            # One-time: max 1 completion, worth 2 tier points (backwards compatible)
            total_points += min(tc, 1) * 2
        else:
            # Repeatable: each completion worth 1 tier point
            total_points += tc

    if total_points > bp.tier:
        bp.tier = total_points
        logger.info("Player %s BP tier advanced to %s", player_id, total_points)

    return bp.tier


async def retroactive_bp_progress(session: AsyncSession, player_id: int) -> list[int]:
    """
    Check the player's current game state and auto-complete BP missions
    they already passed before activating the Celestial Pass.
    Handles both one-time milestone missions and cumulative count missions.
    Returns list of mission IDs that were retroactively completed.
    """
    from sqlalchemy import func as sqlfunc
    from database.models import Transaction, CombatLog, Tribulation

    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()
    if not player:
        return []

    completed_ids = []

    # ── One-time milestone missions ──────────────────────────────────────────
    one_time_checks: dict[str, bool] = {}

    # Foundation trial: realm >= 2 means they passed Foundation Establishment
    if player.realm >= 2:
        one_time_checks["foundation_trial"] = True

    # Golden core: realm >= 3 means they passed Core Formation
    if player.realm >= 3:
        one_time_checks["golden_core"] = True

    if one_time_checks:
        missions_stmt = select(BattlePassMission).where(
            BattlePassMission.objective_type.in_(list(one_time_checks.keys())),
            BattlePassMission.reset_type == "none",
        )
        missions = (await session.execute(missions_stmt)).scalars().all()

        pm_stmt = select(PlayerBPMission).where(
            PlayerBPMission.player_id == player_id,
            PlayerBPMission.season == CURRENT_SEASON,
            PlayerBPMission.mission_id.in_([m.id for m in missions]),
        )
        pm_map = {pm.mission_id: pm for pm in (await session.execute(pm_stmt)).scalars().all()}

        now = datetime.now(timezone.utc)
        for mission in missions:
            if mission.objective_type not in one_time_checks:
                continue
            pm = pm_map.get(mission.id)
            if pm is None:
                pm = PlayerBPMission(
                    player_id=player_id,
                    mission_id=mission.id,
                    season=CURRENT_SEASON,
                    progress=mission.objective_value,
                    is_completed=True,
                    claimed=False,
                    times_completed=1,
                    last_completed_at=now,
                )
                session.add(pm)
                completed_ids.append(mission.id)
            elif not pm.is_completed:
                pm.progress = mission.objective_value
                pm.is_completed = True
                pm.times_completed = max(pm.times_completed or 0, 1)
                pm.last_completed_at = now
                completed_ids.append(mission.id)

    # ── Cumulative missions (replay N increments for past activity) ──────────
    # Only apply to one-time missions — skip repeatables for retroactive
    pill_count = (await session.execute(
        select(sqlfunc.count()).select_from(Transaction).where(
            Transaction.from_player == player_id,
            Transaction.type == "craft_pill"
        )
    )).scalar() or 0
    if pill_count > 0:
        for _ in range(pill_count):
            ids = await update_bp_mission(session, player_id, "craft_pills")
            completed_ids.extend(ids)

    # NPC wins count
    npc_wins = (await session.execute(
        select(sqlfunc.count()).select_from(CombatLog).where(
            CombatLog.attacker_id == player_id,
            CombatLog.defender_id == None,
            CombatLog.winner_id == player_id
        )
    )).scalar() or 0
    if npc_wins > 0:
        for _ in range(npc_wins):
            ids = await update_bp_mission(session, player_id, "win_npc_fight")
            completed_ids.extend(ids)

    # Tribulation wins — a regra "passou a tribulacao" tem UM dono (30/09).
    from core.tribulation_engine import tribulation_passed_clause
    trib_wins = (await session.execute(
        select(sqlfunc.count()).select_from(Tribulation).where(
            tribulation_passed_clause(player_id)
        )
    )).scalar() or 0
    if trib_wins > 0:
        for _ in range(trib_wins):
            ids = await update_bp_mission(session, player_id, "win_tribulation")
            completed_ids.extend(ids)

    # Quests completed
    from database.models import PlayerQuest
    quest_count = (await session.execute(
        select(sqlfunc.count()).select_from(PlayerQuest).where(
            PlayerQuest.player_id == player_id,
            PlayerQuest.claimed == True
        )
    )).scalar() or 0
    if quest_count > 0:
        for _ in range(quest_count):
            ids = await update_bp_mission(session, player_id, "complete_quests")
            completed_ids.extend(ids)

    # Alchemy tier (SET, not increment)
    from database.models import PlayerAlchemySkill
    alch_skill = (await session.execute(
        select(PlayerAlchemySkill).where(PlayerAlchemySkill.player_id == player_id)
    )).scalar_one_or_none()
    if alch_skill and alch_skill.tier > 1:
        alch_missions = (await session.execute(
            select(BattlePassMission).where(
                BattlePassMission.objective_type == "alchemy_tier",
                BattlePassMission.reset_type == "none",
            )
        )).scalars().all()
        now = datetime.now(timezone.utc)
        for am in alch_missions:
            pm = (await session.execute(
                select(PlayerBPMission).where(
                    PlayerBPMission.player_id == player_id,
                    PlayerBPMission.mission_id == am.id,
                    PlayerBPMission.season == CURRENT_SEASON,
                )
            )).scalar_one_or_none()
            if pm is None:
                pm = PlayerBPMission(
                    player_id=player_id, mission_id=am.id,
                    season=CURRENT_SEASON, progress=0, is_completed=False,
                    claimed=False, times_completed=0,
                )
                session.add(pm)
            if not pm.is_completed:
                pm.progress = min(alch_skill.tier, am.objective_value)
                if pm.progress >= am.objective_value:
                    pm.is_completed = True
                    pm.times_completed = max(pm.times_completed or 0, 1)
                    pm.last_completed_at = now
                    completed_ids.append(am.id)

    if completed_ids:
        await recalculate_bp_tier(session, player_id)
        logger.info("Player %s retroactively completed %s BP missions", player_id, len(completed_ids))

    return completed_ids


async def get_player_missions(session: AsyncSession, player_id: int) -> list[dict]:
    """
    Returns all BP missions with the player's current season progress.
    Auto-resets expired repeatables before returning.
    Each entry: {"mission": BattlePassMission, "progress": int, "is_completed": bool,
                 "claimed": bool, "times_completed": int}
    """
    await _auto_reset_repeatables(session, player_id)

    missions_stmt = select(BattlePassMission).order_by(BattlePassMission.reset_type.desc(), BattlePassMission.tier, BattlePassMission.id)
    missions = (await session.execute(missions_stmt)).scalars().all()

    pm_stmt = select(PlayerBPMission).where(
        PlayerBPMission.player_id == player_id,
        PlayerBPMission.season == CURRENT_SEASON,
    )
    pm_map = {pm.mission_id: pm for pm in (await session.execute(pm_stmt)).scalars().all()}

    result = []
    for mission in missions:
        pm = pm_map.get(mission.id)
        result.append({
            "mission": mission,
            "progress": pm.progress if pm else 0,
            "is_completed": pm.is_completed if pm else False,
            "claimed": pm.claimed if pm else False,
            "times_completed": pm.times_completed if pm else 0,
        })
    return result


async def claim_bp_mission_reward(session: AsyncSession, player_id: int, mission_id: int) -> dict:
    """
    Claim the reward of a completed mission. Returns {"success": bool, "error": str, "granted": list}.
    """
    mission = (await session.execute(
        select(BattlePassMission).where(BattlePassMission.id == mission_id)
    )).scalar_one_or_none()
    if not mission:
        return {"success": False, "error": "not_found"}

    # SEC (2026-06-01): lock the row so concurrent claims serialize — the second
    # txn blocks, re-reads claimed=True under the lock, and bails (no double-grant).
    pm = (await session.execute(
        select(PlayerBPMission).where(
            PlayerBPMission.player_id == player_id,
            PlayerBPMission.mission_id == mission_id,
            PlayerBPMission.season == CURRENT_SEASON,
        ).with_for_update()
    )).scalar_one_or_none()

    if not pm or not pm.is_completed:
        return {"success": False, "error": "not_completed"}
    if pm.claimed:
        return {"success": False, "error": "already_claimed"}

    # All Celestial Pass mission claims require the active premium pass
    from core.monetization import get_active_battle_pass
    bp = await get_active_battle_pass(session, player_id)
    if not bp or not bp.is_premium:
        return {"success": False, "error": "premium_required"}

    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()
    if not player:
        return {"success": False, "error": "player_not_found"}

    _bp_lang = (player.language or "pt").lower()
    granted = []

    if mission.reward_jade > 0:
        # grant_jade = balance + lifetime counter + Achievement #12 (the BP
        # mission jade was invisible to Jade Collector — [jogador] 2026-06-12).
        from core.monetization import grant_jade
        await grant_jade(session, player, mission.reward_jade)
        granted.append(f"\U0001f48e {mission.reward_jade}")

    for reward in (mission.reward_items or []):
        r_type = reward.get("type")

        if r_type == "spirit_stones":
            amount = reward.get("amount", 0)
            player.spirit_stones += amount
            granted.append(f"\U0001faa8 {amount}")

        elif r_type == "herb":
            herb_id, qty = reward["herb_id"], reward.get("qty", 1)
            from core.utils import add_item_to_inventory
            await add_item_to_inventory(session, player_id, "herb", herb_id, qty)
            from database.models import HerbCatalog
            _herb = await session.get(HerbCatalog, herb_id)
            _herb_name = _cname(_bp_lang, "herb", _herb) if _herb else f"Herb #{herb_id}"
            granted.append(f"\U0001f33f {_herb_name} \u00d7{qty}")

        elif r_type == "pill":
            pill_id, qty = reward["pill_id"], reward.get("qty", 1)
            from core.utils import add_item_to_inventory
            await add_item_to_inventory(session, player_id, "pill", pill_id, qty)
            from database.models import PillCatalog
            _pill = await session.get(PillCatalog, pill_id)
            _pill_name = _cname(_bp_lang, "pill", _pill) if _pill else f"Pill #{pill_id}"
            granted.append(f"\U0001f48a {_pill_name} \u00d7{qty}")

        elif r_type == "ore":
            from database.models import PlayerOre
            ore_id, qty = reward["ore_id"], reward.get("qty", 1)
            p_ore = (await session.execute(
                select(PlayerOre).where(
                    PlayerOre.player_id == player_id,
                    PlayerOre.ore_id == ore_id,
                )
            )).scalar_one_or_none()
            if p_ore:
                p_ore.quantity += qty
            else:
                session.add(PlayerOre(player_id=player_id, ore_id=ore_id, quantity=qty))
            from database.models import OreCatalog
            _ore = await session.get(OreCatalog, ore_id)
            _ore_name = _cname(_bp_lang, "ore", _ore) if _ore else f"Ore #{ore_id}"
            granted.append(f"\u26cf\ufe0f {_ore_name} \u00d7{qty}")

        elif r_type == "technique_scroll":
            tech_id, qty = reward["technique_id"], reward.get("qty", 1)
            from core.utils import add_item_to_inventory
            await add_item_to_inventory(session, player_id, "technique_scroll", tech_id, qty)
            granted.append(f"\U0001f4dc\u00d7{qty}")

        elif r_type == "title":
            title_val = reward.get("value", "")
            titles = list(player.unlocked_titles or [])
            if title_val and title_val not in titles:
                titles.append(title_val)
                player.unlocked_titles = titles
                from sqlalchemy.orm.attributes import flag_modified as fm_titles
                fm_titles(player, "unlocked_titles")
            player.active_title = title_val
            granted.append(f"\U0001f3f7\ufe0f {title_val}")

    pm.claimed = True
    _inv_cache(player_id)
    return {"success": True, "granted": granted}
