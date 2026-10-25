import asyncio
import logging
import time
from functools import wraps
from datetime import datetime, timezone
from telegram import Update
from telegram.error import RetryAfter, TimedOut, NetworkError
from sqlalchemy import select, update as sa_update, func, and_

from database.models import Player, PlayerArtifact, PlayerInventory, PlayerOre, PlayerSpatialRing

logger = logging.getLogger(__name__)


async def safe_telegram_send(coro_factory, retries=3, base_delay=1.0):
    """Execute a Telegram API coroutine with retry on transient errors.

    Usage: await safe_telegram_send(lambda: bot.send_message(...))
    """
    for attempt in range(retries):
        try:
            return await coro_factory()
        except RetryAfter as e:
            wait = e.retry_after + 0.5
            logger.warning("Flood control: waiting %.1fs (attempt %d/%d)", wait, attempt + 1, retries)
            await asyncio.sleep(wait)
        except (TimedOut, NetworkError) as e:
            if attempt == retries - 1:
                raise
            wait = base_delay * (2 ** attempt)
            logger.warning("Transient error (attempt %d/%d): %s, retrying in %.1fs",
                          attempt + 1, retries, type(e).__name__, wait)
            await asyncio.sleep(wait)
    # Final attempt without catching
    return await coro_factory()

# Basic rate limit tracking (in-memory) with periodic cleanup
_rate_limits: dict[tuple[int, str], float] = {}
_rate_limit_cleanup_counter = 0


def _cleanup_rate_limits():
    """Every 500 calls, purge entries older than 300 seconds to prevent memory leak."""
    global _rate_limit_cleanup_counter
    _rate_limit_cleanup_counter += 1
    if _rate_limit_cleanup_counter >= 500:
        _rate_limit_cleanup_counter = 0
        now = time.time()
        expired = [k for k, v in _rate_limits.items() if now - v > 300]
        for k in expired:
            del _rate_limits[k]

def safe_parse_callback_int(data: str, prefix: str) -> int | None:
    """Safely extract int from callback data like 'prefix123'."""
    try:
        return int(data.removeprefix(prefix))
    except (ValueError, IndexError):
        return None


def safe_parse_callback_uuid(data: str, prefix: str):
    """Safely extract UUID from callback data like 'prefix<uuid>'."""
    import uuid as _uuid
    try:
        return _uuid.UUID(data.removeprefix(prefix))
    except (ValueError, IndexError):
        return None


def get_display_name(player) -> str:
    """Returns the player's Dao Name, falling back to username, then 'Cultivator'."""
    if player.dao_name:
        return player.dao_name
    if player.username:
        return player.username
    return "Cultivator"


def escape_markdown(text: str) -> str:
    """Strips Markdown v1 special characters from user-controlled strings.

    Markdown v1 does NOT support backslash escaping, so we strip instead.
    Characters removed: * _ [ ] `
    """
    if not text:
        return ""
    for char in ('*', '_', '[', ']', '`'):
        text = text.replace(char, '')
    return text

async def resolve_chat_player_id(telegram_id: int) -> int:
    """O `player_id` que este `telegram_id` abre — a versão do chat do que o
    middleware do mini-app já faz (`core/webserver.py`, ramo do `init_data`).

    ⚠️ LEI DUAL-SURFACE. Desde a WEB-B F2 o `telegram_id` **deixou de ser** o
    `player_id` por definição: `auth_identities (provider, provider_uid) →
    player_id` é a verdade, e um resgate de código (`core/account_link.py`)
    pode re-apontar `telegram:<id>` a OUTRO personagem. Sem esta resolução o
    chat continuaria a servir o personagem do id cru — o vazio que o
    `telegram_id` deixou para trás.

    **Fail-safe absoluto:** qualquer dúvida devolve o id cru. Um erro aqui
    nunca pode virar "o jogador vê o personagem de outra pessoa" nem tirar-lhe
    o comando (Lei §1). `resolve_identity_player_id` já não levanta; o
    try/except é cinto-e-suspensórios para o import e para o control plane em
    baixo.

    **Ids negativos saltam a consulta.** Um `player_id` sintético (nascido na
    web, `SYNTHETIC_ID_BASE`) nunca tem linha `telegram:<negativo>` — resolver
    seria uma ida garantida a vazio por chamada. É o mesmo `> 0` que o ramo do
    `init_data` faz.
    """
    try:
        tid = int(telegram_id)
    except (TypeError, ValueError):
        return telegram_id
    if tid <= 0:
        return tid
    try:
        from database.control_db import resolve_identity_player_id
        return await resolve_identity_player_id("telegram", str(tid), tid)
    except Exception:
        logger.warning("resolução de identidade falhou no chat — a usar o id cru",
                       exc_info=True)
        return tid


async def _get_player(telegram_id: int, session) -> Player | None:
    pid = await resolve_chat_player_id(telegram_id)
    stmt = select(Player).where(Player.telegram_id == pid)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()

async def _ensure_player(update: Update, session) -> Player | None:
    user = update.effective_user
    if not user:
        return None
    player = await _get_player(user.id, session)
    if not player:
        from core.i18n import t
        msg = update.message or update.callback_query.message
        # We try to determine language if possible, fallback to 'en'
        lang = _user_lang(update)
        await msg.reply_text(
            t(lang, "not_registered"),
            parse_mode="Markdown",
        )
        return None

    # Optimistic locking: atomically claim this offline window so a concurrent
    # request for the same player cannot apply offline progress twice.
    now = datetime.now(timezone.utc)
    old_last_online = player.last_online

    result = await session.execute(
        sa_update(Player)
        .where(
            Player.telegram_id == player.telegram_id,
            Player.last_online == old_last_online,
        )
        .values(last_online=now)
        .returning(Player.last_online)
    )
    claimed = result.scalar_one_or_none()

    if claimed is not None:
        # We won the race — safe to compute offline progress
        player.last_online = now

        # Load artifacts for offline progress
        # ⚠️ `player.telegram_id`, nunca `user.id`: para quem ligou a conta os
        # dois deixaram de ser o mesmo número, e o id cru traria os artefactos
        # do personagem vazio (progresso offline calculado sem equipamento).
        stmt = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.is_equipped == True)
        arts = (await session.execute(stmt)).scalars().all()

        from core.game_logic import get_player_equipment_stats, calculate_offline_progress
        equip_stats = get_player_equipment_stats(arts)

        progress = await calculate_offline_progress(player, equip_stats=equip_stats, session=session)

        elapsed_minutes = int(progress.get("elapsed_seconds", 0) / 60)
        if elapsed_minutes > 0:
            from core.quest_engine import track_quest
            await track_quest(session, player.telegram_id, "cultivate", elapsed_minutes)
    else:
        # Another request already claimed this window — refresh our copy
        player.last_online = now

    from core.quest_engine import update_login_streak, track_quest, ensure_daily_quests, ensure_weekly_quests
    await update_login_streak(session, player.telegram_id)
    await track_quest(session, player.telegram_id, "login")
    await ensure_daily_quests(session, player.telegram_id)
    await ensure_weekly_quests(session, player.telegram_id)

    # H-14 (v13): bump last_active_at at most once per 5 minutes (avoid hammering
    # the row on every callback). Sect masters use this to identify inactives.
    try:
        last_active = getattr(player, "last_active_at", None)
        if last_active is None or (now - last_active).total_seconds() > 300:
            player.last_active_at = now
    except Exception:
        # COMPAT: older players without the column on a stale schema — ignored
        # because the migration adds the column with default now().
        pass

    return player

def normalize_lang(lang: str | None) -> str:
    """Normalize a language code to one of the supported locales."""
    lang = lang or "en"
    return lang if lang in ("en", "pt", "es") else "en"

def _user_lang(update: Update) -> str:
    """Best-effort language detection from an Update without a DB session."""
    user = update.effective_user if update else None
    return normalize_lang(getattr(user, "language_code", None))


_DEAD_CONN_MARKERS = (
    "connection is closed",
    "connection was closed",
    "connection terminated",
    "server closed the connection",
    "connection has been released",
    "the connection is closed",
    # 2026-05-26 hotfix — Postgres statement_timeout (15s configured in
    # database/db.py) fires under load when a single query waits too long
    # for locks or pool. The handler's transaction rolls back cleanly so
    # the player saw a generic error and lost no state, but the exception
    # was leaking to admin DM spam because this marker was absent.
    # Add the PG-canonical message + asyncpg's QueryCanceledError shape so
    # both paths silence.
    "canceling statement due to statement timeout",
    "canceling statement due to lock timeout",
    "querycancelederror",
    # idle_in_transaction_session_timeout (30s configured) — same
    # "rollback at the end of a successful handler" pattern.
    "terminating connection due to idle-in-transaction timeout",
    "idle_in_transaction_session_timeout",
)


def _is_dead_connection_error(exc: Exception) -> bool:
    """True for asyncpg/SQLAlchemy errors raised when the underlying TCP
    connection died (PostgreSQL statement_timeout, idle_in_transaction_timeout,
    server restart, etc.). The handler typically completed successfully and
    the pool will recycle the dead conn on the next request — we suppress these
    to avoid admin DM spam + misleading the player with a generic error.
    """
    from sqlalchemy.exc import InterfaceError, OperationalError
    if not isinstance(exc, (InterfaceError, OperationalError)):
        return False
    msg = str(exc).lower()
    return any(marker in msg for marker in _DEAD_CONN_MARKERS)


def safe_handler(func):
    """
    Decorator to catch exceptions in handlers and log them, preventing bot crashes.
    """
    @wraps(func)
    async def wrapper(update: Update, context, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except RetryAfter as e:
            # Telegram flood control — wait and retry once
            logger.warning("Flood control in %s: waiting %ds", func.__name__, e.retry_after)
            await asyncio.sleep(e.retry_after + 0.5)
            try:
                return await func(update, context, *args, **kwargs)
            except Exception:
                logger.warning("Retry after flood control failed in %s", func.__name__)
            return
        except (TimedOut, NetworkError) as e:
            from telegram.error import BadRequest
            if isinstance(e, BadRequest):
                is_modified_err = (
                    "Message is not modified" in str(e)
                    or "query is too old" in str(e).lower()
                    or "query id is invalid" in str(e).lower()
                )
                if is_modified_err:
                    logger.warning("Ignored error in %s: %s", func.__name__, "Message is not modified.")
                    return
                # If it's a real BadRequest (like Markdown error), it must be logged fully!
                logger.error("BadRequest in handler %s: %s", func.__name__, str(e))
                return

            # Transient network errors (non-BadRequest)
            logger.warning("Transient error in %s: %s - %s", func.__name__, type(e).__name__, str(e))
            from core.i18n import t
            lang = _user_lang(update)
            try:
                if update and hasattr(update, "callback_query") and update.callback_query:
                    await update.callback_query.answer(t(lang, "err_network"), show_alert=True)
                elif update and hasattr(update, "message") and update.message:
                    await update.message.reply_text(t(lang, "err_network"))
            except Exception:
                pass
            return
        except Exception as e:
            # 2026-05-17: PostgreSQL/asyncpg drops the underlying connection
            # when statement_timeout / idle_in_transaction_session_timeout fire
            # mid-handler. The handler usually completed successfully — the
            # error surfaces only when SQLAlchemy tries to rollback() during
            # `async with session` cleanup. Suppress these: the pool's
            # pool_pre_ping recycles the dead conn on the next request, and
            # the player already saw the correct UI.
            if _is_dead_connection_error(e):
                logger.warning(
                    "DB connection dropped during/after %s (pool will recycle): %s",
                    func.__name__, type(e).__name__,
                )
                return

            logger.exception("Error in handler %s: %s", func.__name__, e)

            from config import ADMIN_USERS
            if ADMIN_USERS:
                try:
                    import traceback
                    import html
                    from telegram.constants import ParseMode

                    error_trace = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                    user_info = ""
                    if update and update.effective_user:
                        u = update.effective_user
                        user_info = f"\n<b>User:</b> <code>{u.id}</code> ({html.escape(u.username or u.first_name or 'Unknown')})"

                    error_msg = (
                        f"🚨 <b>Bot Error in <code>{func.__name__}</code></b>{user_info}\n\n"
                        f"<pre><code class='language-python'>\n{html.escape(error_trace)}\n</code></pre>"
                    )

                    if len(error_msg) > 4000:
                        error_msg = error_msg[:3950] + "\n... (truncated)</code></pre>"

                    if context and hasattr(context, "bot"):
                        await safe_telegram_send(lambda: context.bot.send_message(
                            chat_id=ADMIN_USERS[0],
                            text=error_msg,
                            parse_mode=ParseMode.HTML
                        ))
                except Exception as ex:
                    logger.error("Failed to send error trace to admin: %s", ex)
            
            from core.i18n import t
            lang = _user_lang(update)
            if update and hasattr(update, "message") and update.message:
                try:
                    await update.message.reply_text(t(lang, "err_generic"))
                except Exception:
                    pass
            elif update and hasattr(update, "callback_query") and update.callback_query:
                try:
                    await update.callback_query.answer(t(lang, "err_generic"), show_alert=True)
                except Exception:
                    pass
    return wrapper

async def safe_answer(query, *args, **kwargs):
    """Answer a callback query, silently ignoring 'Query is too old' errors."""
    from telegram.error import BadRequest
    try:
        await query.answer(*args, **kwargs)
    except BadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg:
            logger.debug("Ignored stale callback query: %s", e)
        else:
            raise


def rate_limit(limit_seconds: int = 1):
    """
    Decorator to prevent user spamming commands.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context, *args, **kwargs):
            user = update.effective_user
            if not user:
                return await func(update, context, *args, **kwargs)

            now = datetime.now(timezone.utc).timestamp()
            user_id = user.id
            last_called = _rate_limits.get((user_id, func.__name__), 0)

            if now - last_called < limit_seconds:
                if update.callback_query:
                    from core.i18n import t
                    lang = _user_lang(update)
                    await update.callback_query.answer(t(lang, "err_rate_limit"), show_alert=False)
                return

            _rate_limits[(user_id, func.__name__)] = now
            _cleanup_rate_limits()
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

# ─── Inventory slot enforcement ──────────────────────────────────────────────

async def _get_or_create_ring(session, player_id: int) -> PlayerSpatialRing:
    ring = (await session.execute(
        select(PlayerSpatialRing).where(PlayerSpatialRing.player_id == player_id)
    )).scalar_one_or_none()
    if not ring:
        ring = PlayerSpatialRing(player_id=player_id, tier=1, max_slots=50)
        session.add(ring)
        await session.flush()
    return ring


async def _count_used_slots(session, player_id: int) -> int:
    inv = (await session.execute(
        select(func.count()).select_from(PlayerInventory).where(
            PlayerInventory.player_id == player_id,
            PlayerInventory.quantity > 0,
        )
    )).scalar() or 0
    ores = (await session.execute(
        select(func.count()).select_from(PlayerOre).where(
            PlayerOre.player_id == player_id,
            PlayerOre.quantity > 0,
        )
    )).scalar() or 0
    from database.models import PlayerArtifact as PA
    arts = (await session.execute(
        select(func.count()).select_from(PA).where(
            PA.player_id == player_id,
        )
    )).scalar() or 0
    return inv + ores + arts


async def _add_ore(session, player_id: int, ore_id: int, quantity: int) -> bool:
    """Credit ore into `player_ores` — the one store the game actually reads.

    Two subtleties, both learned the hard way:

    * **Never filter `quantity > 0` when deciding insert-vs-update.**
      `handlers/inventory.py:_do_sell_ore` ZEROES the row instead of deleting it
      (unlike `_do_sell_herb`, which deletes), so rows with `quantity = 0` exist
      in production. A helper that skipped them would try to INSERT and blow up
      against `uq_player_ore`.
    * **Opportunistic fold of the orphans.** Whatever this ore_id has stranded
      in `player_inventory` from the three old writers gets folded in here and
      the source row is ZEROED (never deleted — Lei: nothing of a real player is
      erased; and zeroing mirrors the convention `_do_sell_ore` already uses).
      This heals incrementally, per ore_id, with ZERO migration. The residue for
      ore ids that never drop again stays visible in the inventory payload,
      which now reads BOTH stores.
    """
    row = (await session.execute(
        select(PlayerOre).where(and_(
            PlayerOre.player_id == player_id,
            PlayerOre.ore_id == ore_id,
        ))
    )).scalar_one_or_none()

    folded = 0
    orphans = (await session.execute(
        select(PlayerInventory).where(and_(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "ore",
            PlayerInventory.item_id == ore_id,
            PlayerInventory.quantity > 0,
        ))
    )).scalars().all()
    for orphan in orphans:
        folded += int(orphan.quantity or 0)
        orphan.quantity = 0

    if row is not None:
        row.quantity = int(row.quantity or 0) + int(quantity) + folded
    else:
        session.add(PlayerOre(
            player_id=player_id,
            ore_id=ore_id,
            quantity=int(quantity) + folded,
        ))
    if folded:
        logger.info("ore fold: player=%s ore=%s folded=%s from player_inventory",
                    player_id, ore_id, folded)
    return True


async def add_item_to_inventory(session, player_id: int, item_type: str, item_id: int, quantity: int = 1, quality: str = "normal", force: bool = False) -> bool:
    """Add item to inventory with spatial ring slot check.

    Returns True if added (or stacked), False if inventory is full.
    Stacking onto an existing row never fails.

    `force=True` bypasses the slot cap. Use it ONLY for delivery of OWED items
    (P2P trade settle/cancel, marketplace payouts, escrow returns) — refusing to
    deliver something the player already earned/traded-for would silently DESTROY
    it (the giver already paid). MA-39a review 2026-06-13: `_give_item` discarded
    this bool, so a full ring meant permanent loss. The cap governs active
    acquisition (loot/craft), not settlement of obligations.

    ⚠️ ORE IS NOT AN INVENTORY ITEM (MV-9.5, 2026-08-09). Ore lives in its OWN
    table, `player_ores` — and that is the ONLY table the forge, the cauldron
    upgrade, the marketplace escrow and the P2P trade picker ever read
    (`forge_engine.get_player_ores:43`, `alchemy_engine:1491`, `economy.py:82`,
    `webserver.py:19593`). Three writers were still handing `item_type="ore"`
    to this helper, so the ore landed in `player_inventory`, where the player
    could SEE it and nothing could USE it — 1.995 orphan units measured in
    `main`. Worse, the announcement was already right and only the deposit was
    wrong: `boss_engine._drop_description` resolves the name from `OreCatalog`
    and says "Spirit Copper x3" while depositing into the wrong store.

    Fixing the three call sites would not have been enough — a fourth was
    already latent (`quest_choice_engine:188` takes the type from JSONB). So
    the redirect lives HERE, at the chokepoint: every caller keeps its
    signature and ore silently goes home. The ring cap does not apply — no ore
    writer in the game has ever respected it, and starting now would be an
    unrequested behaviour change.
    """
    if str(item_type) == "ore":
        return await _add_ore(session, player_id, int(item_id), int(quantity))

    stmt = select(PlayerInventory).where(and_(
        PlayerInventory.player_id == player_id,
        PlayerInventory.item_type == item_type,
        PlayerInventory.item_id == item_id,
        PlayerInventory.quality == quality,
    ))
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.quantity += quantity
        return True

    # New distinct item — check slot capacity (skipped for owed-item delivery).
    if not force:
        ring = await _get_or_create_ring(session, player_id)
        used = await _count_used_slots(session, player_id)
        if used >= ring.max_slots:
            return False

    session.add(PlayerInventory(
        player_id=player_id,
        item_type=item_type,
        item_id=item_id,
        quantity=quantity,
        quality=quality,
    ))
    return True


def build_pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str,
    lang: str = "pt"
) -> list:
    """
    Builds a generic pagination row for inline menus.

    Returns a list of InlineKeyboardButton objects intended to be appended
    as a row to an InlineKeyboardMarkup.

    N-19 (Sprint v14.3): When `total_pages > 3`, prepend a `⏮` jump-to-first
    and append a `⏭` jump-to-last so deep inventories don't require N clicks
    to scan from the start ([jogador] reported this 2026-05-08). Hidden when
    total_pages <= 3 (Prev/Next already covers the whole range).
    """
    from telegram import InlineKeyboardButton
    from core.i18n import t

    current_page = max(1, min(current_page, total_pages))

    row = []

    show_jumpers = total_pages > 3

    # First Button (only when worth jumping)
    if show_jumpers:
        if current_page > 2:
            row.append(InlineKeyboardButton(
                t(lang, "btn_first_page"),
                callback_data=f"{callback_prefix}1",
            ))
        else:
            row.append(InlineKeyboardButton(" ", callback_data="ignore"))

    # Previous Button
    if current_page > 1:
        row.append(
            InlineKeyboardButton(
                f"⬅️ {t(lang, 'btn_previous')}",
                callback_data=f"{callback_prefix}{current_page - 1}"
            )
        )
    else:
        # Placeholder to keep button layout stable
        row.append(InlineKeyboardButton(" ", callback_data="ignore"))

    # Page Indicator
    row.append(
        InlineKeyboardButton(
            f"{t(lang, 'page_indicator', current=current_page, total=total_pages)}",
            callback_data="ignore"
        )
    )

    # Next Button
    if current_page < total_pages:
        row.append(
            InlineKeyboardButton(
                f"{t(lang, 'btn_next')} ➡️",
                callback_data=f"{callback_prefix}{current_page + 1}"
            )
        )
    else:
        # Placeholder to keep button layout stable
        row.append(InlineKeyboardButton(" ", callback_data="ignore"))

    # Last Button (only when worth jumping)
    if show_jumpers:
        if current_page < total_pages - 1:
            row.append(InlineKeyboardButton(
                t(lang, "btn_last_page"),
                callback_data=f"{callback_prefix}{total_pages}",
            ))
        else:
            row.append(InlineKeyboardButton(" ", callback_data="ignore"))

    return [row]
