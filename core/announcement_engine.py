import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from database.db import get_session_factory, current_world_key
from database.models import Player
from core.i18n import t
from core.utils import escape_markdown, normalize_lang

logger = logging.getLogger(__name__)

_bot = None
# Rate-limit cache: (world_key, announcement_key) -> last datetime. Keyed by world
# (Multi-Servidor Fase 3) so a broadcast in one world can't rate-limit / suppress
# the SAME announcement in another world (e.g. two worlds each having an R4+
# breakthrough within the cooldown). Single-world deployments are unaffected —
# the world component is always "main".
_last_announce: dict = {}


def set_bot(bot) -> None:
    global _bot
    _bot = bot


async def broadcast(
    key: str,
    cooldown_minutes: int = 5,
    pref_key: str | None = None,
    *,
    persist: bool = True,
    kind: str = "system",
    icon: str = "📜",
    **kwargs,
) -> None:
    """Send announcement to all active players in their own language.

    M-9: when ``pref_key`` is provided, players who explicitly disabled that
    notification preference are skipped. Default is no filter (compat with
    existing callers).

    Mini-app feed: when ``persist`` is True (default), an entry is written to
    ``global_announcements`` so the mini-app Announcements tab can show it.
    Pass ``persist=False`` for purely transient pings (e.g. test broadcasts).
    """
    if _bot is None:
        logger.warning("broadcast() called before set_bot() — skipping '%s'", key)
        return

    now = datetime.now(timezone.utc)
    dedup_key = (current_world_key(), key)
    last = _last_announce.get(dedup_key)
    if last and (now - last) < timedelta(minutes=cooldown_minutes):
        logger.debug("broadcast '%s' rate-limited (world=%s), skipping", key, dedup_key[0])
        return
    _last_announce[dedup_key] = now

    cutoff = now - timedelta(days=7)
    async with get_session_factory()() as session:
        players = (await session.execute(
            select(Player.telegram_id, Player.language)
            .where(Player.last_online >= cutoff)
        )).all()
        opted_out: set[int] = set()
        if pref_key:
            from core.notification_prefs import filter_recipients, PREF_KEYS
            if pref_key in PREF_KEYS:
                allowed = await filter_recipients(session, [p[0] for p in players], pref_key)
                opted_out = {p[0] for p in players} - allowed

        if persist:
            try:
                from database.models import GlobalAnnouncement
                rendered = t("pt", key, **kwargs)
                session.add(GlobalAnnouncement(
                    kind=kind,
                    icon=icon,
                    message_key=key,
                    params={k: v for k, v in kwargs.items() if isinstance(v, (str, int, float, bool))},
                    rendered_text=rendered,
                ))
                await session.commit()
            except Exception:
                logger.exception("Failed to persist announcement '%s'", key)
                await session.rollback()

    sent = 0
    failed = 0
    skipped = 0
    total = len(players)
    for pid, lang in players:
        if pid in opted_out:
            skipped += 1
            continue
        lang = normalize_lang(lang)
        try:
            text = escape_markdown(t(lang, key, **kwargs))
            await _bot.send_message(chat_id=pid, text=text, parse_mode="Markdown")
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning("Failed to send announcement '%s' to %d: %s", key, pid, e)
        # Yield to event loop + anti-flood
        await asyncio.sleep(0.05)

    logger.info(
        "📢 Broadcast '%s': %d sent, %d failed, %d skipped (pref), %d total",
        key, sent, failed, skipped, total,
    )


async def broadcast_once(
    key: str,
    *,
    kind: str = "release",
    icon: str = "📜",
    pref_key: str | None = None,
    cooldown_minutes: int = 0,
    **kwargs,
) -> bool:
    """One-shot broadcast — sends only if no GlobalAnnouncement with this
    `message_key` exists yet. Used for release notes / version announcements
    that must NOT re-fire on every container restart.

    Returns True if the broadcast actually went out, False if skipped.
    """
    if _bot is None:
        logger.warning("broadcast_once() called before set_bot() — skipping '%s'", key)
        return False

    from sqlalchemy import select as _select, func as _func
    from database.models import GlobalAnnouncement

    async with get_session_factory()() as session:
        existing = (await session.execute(
            _select(_func.count(GlobalAnnouncement.id))
            .where(GlobalAnnouncement.message_key == key)
        )).scalar() or 0
    if existing > 0:
        logger.info("broadcast_once '%s' already sent (count=%d), skipping", key, existing)
        return False

    await broadcast(
        key,
        cooldown_minutes=cooldown_minutes,
        pref_key=pref_key,
        persist=True,
        kind=kind,
        icon=icon,
        **kwargs,
    )
    return True
