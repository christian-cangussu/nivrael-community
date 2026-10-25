"""v15.1.2 — Notification Engine.

Canonical helper for persistent player notifications. Replaces the ad-hoc
chat-DM-only flow used by achievements/titles/etc. — every event emitter now
calls `notify(session, player_id, kind, ...)` which:

  1. Writes a row to `player_notifications` (deduped via (kind, ref_id))
  2. Surfaces in the mini-app bell via `serialize_unread`
  3. Optionally pushes a Telegram DM (if bot context + prefs allow)

The mini-app bell badge + NotifInbox modal consume `serialize_unread` /
`serialize_inbox`. Dismiss / mark-seen are simple UPDATE helpers.

Channels:
  - "db"       — always (write the row)
  - "telegram" — opt-in (caller passes bot + chat_id) — chat-side DM
  - "toast"    — handled client-side from the bell-poll diff (no server work)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select, update

from core.i18n import t
from database.models import PlayerNotification

logger = logging.getLogger(__name__)


# ─── Write ───────────────────────────────────────────────────────────────────


async def notify(
    session,
    player_id: int,
    kind: str,
    *,
    title_key: str,
    body_key: str,
    payload: dict | None = None,
    ref_id: str | None = None,
    icon: str = "🔔",
    target_tab: str | None = None,
    priority: int = 5,
) -> PlayerNotification | None:
    """Persist a notification for a player. Returns the row (or None if
    deduplicated against an existing (kind, ref_id) row).

    Dedup contract: if a notification with the same (player_id, kind, ref_id)
    already exists, this call is a no-op. The Postgres unique index
    `idx_pn_dedup` is the source of truth — the application-side check is a
    fast-path; the SAVEPOINT below is the truth-path that survives races
    between the read and the INSERT.

    v15.1.5-hf3 (CRITICAL): the INSERT now runs inside a SAVEPOINT
    (`begin_nested`). Any IntegrityError (UniqueViolation from idx_pn_dedup
    in particular) rolls back the savepoint ONLY — the caller's outer
    transaction stays alive. Before this fix, a unique-constraint collision
    (most commonly: quest re-completion after the player had dismissed the
    prior notification, since idx_pn_dedup ignores dismissed_at) propagated
    as a PendingRollbackError that poisoned every subsequent ORM call in the
    parent transaction. The cascade surfaced as 500s across world_boss
    attack, inventory pill use, cultivation status, alchemy crafting, etc.

    Caller must commit the session. Never raises — logs and returns None on
    failure to avoid breaking the engine that called us.
    """
    from sqlalchemy.exc import IntegrityError

    try:
        # Fast-path dedup — cheap SELECT, avoids the savepoint overhead in
        # the common case. We DO NOT filter by dismissed_at here because the
        # unique constraint doesn't either: an existing dismissed row would
        # still block re-insert with the same triple. The previous filter
        # (`dismissed_at IS NULL`) was the latent root cause of the cascade.
        if ref_id is not None:
            existing = (await session.execute(
                select(PlayerNotification.id).where(
                    PlayerNotification.player_id == player_id,
                    PlayerNotification.kind == kind,
                    PlayerNotification.ref_id == ref_id,
                ).limit(1)
            )).scalar_one_or_none()
            if existing is not None:
                return None

        row = PlayerNotification(
            player_id=player_id,
            kind=kind,
            ref_id=ref_id,
            title_key=title_key,
            body_key=body_key,
            payload=payload or {},
            icon=icon,
            target_tab=target_tab,
            priority=priority,
        )
        # Savepoint: if the INSERT trips the unique constraint (race with
        # another worker, or app-side check missed a tombstone-dismissed
        # row), we roll back ONLY this nested savepoint and treat the call
        # as a dedup hit. The parent transaction NEVER sees the error.
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
            return row
        except IntegrityError:
            logger.debug(
                "notify dedup (savepoint rollback): kind=%s player_id=%s ref_id=%s",
                kind, player_id, ref_id,
            )
            return None
    except Exception:
        logger.exception("notify failed: kind=%s player_id=%s ref_id=%s", kind, player_id, ref_id)
        return None


# ─── Read (server-side pre-rendered) ─────────────────────────────────────────


def _serialize(notif: PlayerNotification, lang: str) -> dict:
    """Project a PlayerNotification row as a client-ready dict. Server
    pre-renders title/body via i18n so the client never sees raw keys even
    if it has a stale i18n cache."""
    if lang not in ("pt", "en", "es"):
        lang = "pt"
    params = notif.payload or {}
    try:
        title = t(lang, notif.title_key, **params) if params else t(lang, notif.title_key)
        body = t(lang, notif.body_key, **params) if params else t(lang, notif.body_key)
    except Exception:
        # If i18n params don't match the key, fall back to bare keys rather
        # than crash — caller will at least see SOMETHING readable.
        title = t(lang, notif.title_key)
        body = t(lang, notif.body_key)
    return {
        "id": str(notif.id),
        "kind": notif.kind,
        "ref_id": notif.ref_id,
        "title": title,
        "body": body,
        "icon": notif.icon,
        "target_tab": notif.target_tab,
        "priority": notif.priority,
        "seen": notif.seen_at is not None,
        "created_at": notif.created_at.isoformat() if notif.created_at else None,
    }


async def list_inbox(session, player_id: int, lang: str, *, limit: int = 50) -> list[dict]:
    """Return undismissed notifications, newest first."""
    rows = (await session.execute(
        select(PlayerNotification).where(
            PlayerNotification.player_id == player_id,
            PlayerNotification.dismissed_at.is_(None),
        ).order_by(PlayerNotification.created_at.desc()).limit(limit)
    )).scalars().all()
    return [_serialize(r, lang) for r in rows]


async def count_unseen(session, player_id: int) -> int:
    return (await session.execute(
        select(func.count(PlayerNotification.id)).where(
            PlayerNotification.player_id == player_id,
            PlayerNotification.seen_at.is_(None),
            PlayerNotification.dismissed_at.is_(None),
        )
    )).scalar_one() or 0


# ─── Mark seen / dismiss ─────────────────────────────────────────────────────


async def mark_seen(session, player_id: int, notification_id: str) -> bool:
    import uuid as _uuid
    try:
        nid = _uuid.UUID(str(notification_id))
    except (ValueError, TypeError):
        return False
    result = await session.execute(
        update(PlayerNotification)
        .where(
            PlayerNotification.id == nid,
            PlayerNotification.player_id == player_id,
            PlayerNotification.seen_at.is_(None),
        )
        .values(seen_at=datetime.now(timezone.utc))
    )
    return result.rowcount > 0


async def mark_all_seen(session, player_id: int) -> int:
    result = await session.execute(
        update(PlayerNotification)
        .where(
            PlayerNotification.player_id == player_id,
            PlayerNotification.seen_at.is_(None),
            PlayerNotification.dismissed_at.is_(None),
        )
        .values(seen_at=datetime.now(timezone.utc))
    )
    return result.rowcount


async def dismiss(session, player_id: int, notification_id: str) -> bool:
    import uuid as _uuid
    try:
        nid = _uuid.UUID(str(notification_id))
    except (ValueError, TypeError):
        return False
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(PlayerNotification)
        .where(
            PlayerNotification.id == nid,
            PlayerNotification.player_id == player_id,
            PlayerNotification.dismissed_at.is_(None),
        )
        .values(dismissed_at=now, seen_at=func.coalesce(PlayerNotification.seen_at, now))
    )
    return result.rowcount > 0


async def dismiss_all(session, player_id: int) -> int:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(PlayerNotification)
        .where(
            PlayerNotification.player_id == player_id,
            PlayerNotification.dismissed_at.is_(None),
        )
        .values(dismissed_at=now, seen_at=func.coalesce(PlayerNotification.seen_at, now))
    )
    return result.rowcount
