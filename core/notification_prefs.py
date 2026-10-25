"""M-9: per-player notification preferences.

Defaults: every notification is ON. Players opt OUT via /notif. The helpers
below all return safe defaults (everything enabled) when no row exists, so
callers do not have to special-case missing prefs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PlayerNotificationPref

logger = logging.getLogger(__name__)

# Canonical pref keys → default value. Used by the /notif UI and by callers
# that want to query / mutate prefs without leaking SQLAlchemy column names.
PREF_KEYS: dict[str, bool] = {
    "anomaly_global": True,
    "sect_edict": True,
    "pill_finished": True,
    "alchemy_energy_full": True,
    "breakthrough_ready": True,
    "trib_cooldown_done": True,
    # Onda 3 — Heaven's Whispers (atmospheric world-event notifications). Default
    # ON for the 57 live players; the matching Boolean column lives on
    # PlayerNotificationPref (migration 110). /conf + mini-app prefs auto-wire it.
    "whisper": True,
}


async def get_prefs(session: AsyncSession, player_id: int) -> dict[str, bool]:
    row = (await session.execute(
        select(PlayerNotificationPref).where(PlayerNotificationPref.player_id == player_id)
    )).scalar_one_or_none()
    if not row:
        return dict(PREF_KEYS)
    return {key: bool(getattr(row, key, default)) for key, default in PREF_KEYS.items()}


async def is_enabled(session: AsyncSession, player_id: int, key: str) -> bool:
    if key not in PREF_KEYS:
        return True  # unknown key → don't filter
    prefs = await get_prefs(session, player_id)
    return prefs.get(key, PREF_KEYS[key])


async def set_pref(session: AsyncSession, player_id: int, key: str, value: bool) -> bool:
    if key not in PREF_KEYS:
        return False
    row = (await session.execute(
        select(PlayerNotificationPref).where(PlayerNotificationPref.player_id == player_id)
    )).scalar_one_or_none()
    if not row:
        row = PlayerNotificationPref(player_id=player_id)
        session.add(row)
        await session.flush()
    setattr(row, key, bool(value))
    row.updated_at = datetime.now(timezone.utc)
    return True


async def toggle_pref(session: AsyncSession, player_id: int, key: str) -> bool | None:
    """Flip the pref and return the new value. Returns None if key is invalid."""
    if key not in PREF_KEYS:
        return None
    prefs = await get_prefs(session, player_id)
    new_value = not prefs.get(key, PREF_KEYS[key])
    await set_pref(session, player_id, key, new_value)
    return new_value


async def filter_recipients(session: AsyncSession, player_ids: list[int], key: str) -> set[int]:
    """Return the subset of player_ids that have `key` enabled (or no row)."""
    if key not in PREF_KEYS or not player_ids:
        return set(player_ids)
    rows = (await session.execute(
        select(PlayerNotificationPref.player_id, getattr(PlayerNotificationPref, key))
        .where(PlayerNotificationPref.player_id.in_(player_ids))
    )).all()
    explicit_off = {pid for pid, val in rows if val is False}
    return set(player_ids) - explicit_off
