"""
Activity indicators for the main menu.

Checks pending activities and returns emoji indicators:
  🔴 = action required (unclaimed reward, expired expedition)
  🟡 = activity available (energy full, dungeon in progress)
  "" = nothing pending
"""

import time
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func

from database.models import (
    PlayerQuest, QuestCatalog,
    PlayerBPMission,
    PlayerBeast,
    PlayerDungeon,
    SectMember,
)

logger = logging.getLogger(__name__)

# ─── Cache ────────────────────────────────────────────────────────────────────
_cache: dict[int, tuple[float, dict[str, str]]] = {}
CACHE_TTL = 300  # 5 minutes


def _invalidate_cache(player_id: int):
    """Call after an action that changes indicator state."""
    _cache.pop(player_id, None)


async def get_activity_indicators(session, player, vip_level: int = 0) -> dict[str, str]:
    """
    Returns a dict of indicator emojis keyed by activity area.

    Keys:
      quests      – unclaimed daily/weekly quest rewards
      bp          – unclaimed battle pass mission rewards
      expedition  – beast expedition ready to collect
      dungeon     – dungeon in progress (can advance)
      alchemy     – alchemy energy is full
      sect        – player is in a sect (placeholder, no urgent indicator)

    Values: "🔴", "🟡", or ""
    """
    pid = player.telegram_id
    now = time.time()

    cached = _cache.get(pid)
    if cached and (now - cached[0]) < CACHE_TTL:
        return cached[1]

    indicators: dict[str, str] = {
        "quests": "",
        "bp": "",
        "expedition": "",
        "dungeon": "",
        "alchemy": "",
    }

    try:
        await _check_quests(session, pid, indicators)
        await _check_bp(session, pid, indicators)
        await _check_expedition(session, pid, indicators)
        await _check_dungeon(session, pid, indicators)
        await _check_alchemy(session, player, vip_level, indicators)
    except Exception:
        logger.exception("Error computing activity indicators for %s", pid)

    _cache[pid] = (now, indicators)
    return indicators


# ─── Individual checks ────────────────────────────────────────────────────────

async def _check_quests(session, player_id: int, ind: dict):
    """🔴 if any completed-but-unclaimed daily/weekly quests."""
    stmt = (
        select(func.count())
        .select_from(PlayerQuest)
        .where(
            PlayerQuest.player_id == player_id,
            PlayerQuest.is_completed == True,
            PlayerQuest.claimed == False,
        )
    )
    count = await session.scalar(stmt) or 0
    if count > 0:
        ind["quests"] = "🔴"


async def _check_bp(session, player_id: int, ind: dict):
    """🔴 if any completed-but-unclaimed battle pass missions."""
    from config import CURRENT_SEASON

    stmt = (
        select(func.count())
        .select_from(PlayerBPMission)
        .where(
            PlayerBPMission.player_id == player_id,
            PlayerBPMission.season == CURRENT_SEASON,
            PlayerBPMission.is_completed == True,
            PlayerBPMission.claimed == False,
        )
    )
    count = await session.scalar(stmt) or 0
    if count > 0:
        ind["bp"] = "🔴"


async def _check_expedition(session, player_id: int, ind: dict):
    """🔴 if any beast expedition has finished and is ready to collect."""
    now_utc = datetime.now(timezone.utc)
    stmt = (
        select(func.count())
        .select_from(PlayerBeast)
        .where(
            PlayerBeast.player_id == player_id,
            PlayerBeast.is_on_expedition == True,
            PlayerBeast.expedition_returns_at <= now_utc,
        )
    )
    count = await session.scalar(stmt) or 0
    if count > 0:
        ind["expedition"] = "🔴"
    else:
        # 🟡 if expedition still running (not finished yet)
        stmt2 = (
            select(func.count())
            .select_from(PlayerBeast)
            .where(
                PlayerBeast.player_id == player_id,
                PlayerBeast.is_on_expedition == True,
                PlayerBeast.expedition_returns_at > now_utc,
            )
        )
        running = await session.scalar(stmt2) or 0
        if running > 0:
            ind["expedition"] = "🟡"


async def _check_dungeon(session, player_id: int, ind: dict):
    """🟡 if player has a dungeon run in progress."""
    stmt = (
        select(func.count())
        .select_from(PlayerDungeon)
        .where(
            PlayerDungeon.player_id == player_id,
            PlayerDungeon.current_floor > 0,
        )
    )
    count = await session.scalar(stmt) or 0
    if count > 0:
        ind["dungeon"] = "🟡"


async def _check_alchemy(session, player, vip_level: int, ind: dict):
    """🟡 if alchemy energy is full."""
    from core.alchemy_engine import get_alchemy_energy, get_alchemy_tier

    # O tecto depende do tier (火候) — sem ele o ponto amarelo acendia a 100
    # para um Celestial cujo tecto real é 240 (o indicador mentiria).
    a_tier = await get_alchemy_tier(session, player.telegram_id)
    current, energy_max, _ = get_alchemy_energy(player, vip_level, a_tier)
    if current >= energy_max:
        ind["alchemy"] = "🟡"
