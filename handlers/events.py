import logging
import random
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

from core.utils import safe_handler, rate_limit, _get_player, escape_markdown, safe_answer, normalize_lang
from core.i18n import t
from database.db import get_session_factory
from database.models import CelestialEvent

logger = logging.getLogger(__name__)

# Artifact grades injected: Heaven (4), Spirit (5), Divine (6), Dao (7)
_AUCTION_MIN_GRADE = 4

# Price per artifact grade (Spirit Stones)
_ARTIFACT_GRADE_PRICES = {4: 15_000, 5: 40_000, 6: 100_000, 7: 300_000}
# Price per pill difficulty level
_PILL_DIFFICULTY_PRICES = {3: 5_000, 4: 12_000, 5: 30_000}


def _format_countdown(expires_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    delta = expires_at - now
    if delta.total_seconds() <= 0:
        return "Expired"
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    if hours >= 24:
        days = hours // 24
        h = hours % 24
        return f"{days}d {h}h {minutes}m"
    return f"{hours}h {minutes}m"


async def get_active_events(session) -> list[CelestialEvent]:
    now = datetime.now(timezone.utc)
    stmt = select(CelestialEvent).where(
        CelestialEvent.is_active == True,
        CelestialEvent.expires_at > now,
    )
    return (await session.execute(stmt)).scalars().all()


async def get_event_multipliers(session) -> dict:
    """Return merged multipliers from all currently active events."""
    events = await get_active_events(session)
    merged: dict = {}
    for ev in events:
        for key, val in (ev.multipliers or {}).items():
            if key in merged:
                merged[key] = max(merged[key], val)
            else:
                merged[key] = val
    return merged


@safe_handler
@rate_limit(1)
async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            if query:
                await safe_answer(query, t(normalize_lang(user.language_code), "not_registered"), show_alert=True)
            return

        lang = player.language or "en"
        active_events = await get_active_events(session)

        if active_events:
            lines = [t(lang, "events_title"), ""]
            for ev in active_events:
                countdown = _format_countdown(ev.expires_at)
                lines.append(f"{ev.emoji} *{escape_markdown(ev.name)}*")
                lines.append(f"_{escape_markdown(ev.description)}_")
                # Show multiplier info
                mults = ev.multipliers or {}
                effects = []
                if mults.get("cb_mult"):
                    effects.append(t(lang, "events_effect_cb", mult=mults["cb_mult"]))
                if mults.get("loot_mult"):
                    effects.append(t(lang, "events_effect_loot", mult=mults["loot_mult"]))
                if mults.get("qi_regen_mult"):
                    effects.append(t(lang, "events_effect_qi", mult=mults["qi_regen_mult"]))
                if mults.get("boss_hp_mult"):
                    effects.append(t(lang, "events_effect_boss_hp", mult=mults["boss_hp_mult"]))
                if mults.get("boss_loot_mult"):
                    effects.append(t(lang, "events_effect_boss_loot", mult=mults["boss_loot_mult"]))
                if mults.get("market_npc"):
                    effects.append(t(lang, "events_effect_market_npc"))
                if effects:
                    lines.append("✨ " + " | ".join(effects))
                lines.append(t(lang, "events_expires_in", time=countdown))
                lines.append("")
        else:
            lines = [t(lang, "events_title"), "", t(lang, "events_calm")]

        text = "\n".join(lines)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_main")]
        ])

        if query:
            await safe_answer(query)
            await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


async def inject_immortal_auction_items(session, event_expires_at: datetime) -> int:
    """Inject rare NPC items into the marketplace for the Immortal Auction event.
    Returns the number of listings created.
    """
    from database.models import ArtifactCatalog, PillCatalog, MarketplaceListing

    now = datetime.now(timezone.utc)
    created = 0

    # ── Rare Artifacts (grade >= Heaven) — auctioned ──────────────────────────
    art_stmt = select(ArtifactCatalog).where(ArtifactCatalog.grade >= _AUCTION_MIN_GRADE)
    artifacts = (await session.execute(art_stmt)).scalars().all()

    chosen_arts = random.sample(artifacts, min(len(artifacts), 6))
    for art in chosen_arts:
        starting_bid = _ARTIFACT_GRADE_PRICES.get(art.grade, 50_000)
        listing = MarketplaceListing(
            seller_id=None,                   # NPC listing
            item_type="artifact",
            item_id=art.id,
            item_data={
                "npc": True, 
                "seller_name": "🏮 Immortal Merchant", 
                "art_name": art.name, 
                "grade": art.grade,
                "custom_stats": art.base_stats.copy() if art.base_stats else {}
            },
            quantity=1,
            unit_price=starting_bid,
            is_auction=True,
            current_bid=None,
            highest_bidder=None,
            expires_at=event_expires_at,
            is_sold=False,
            created_at=now,
        )
        session.add(listing)
        created += 1

    # ── Rare Pills (difficulty >= 3) — auctioned ──────────────────────────────
    pill_stmt = select(PillCatalog).where(PillCatalog.difficulty >= 3)
    pills = (await session.execute(pill_stmt)).scalars().all()

    chosen_pills = random.sample(pills, min(len(pills), 4))
    for pill in chosen_pills:
        starting_bid = _PILL_DIFFICULTY_PRICES.get(pill.difficulty, 8_000)
        listing = MarketplaceListing(
            seller_id=None,
            item_type="pill",
            item_id=pill.id,
            # Gravado na BASE, num anuncio que todas as linguas veem; ninguem o le (a
            # montra resolve o nome pelo `item_id` na leitura). Traduzir aqui cozia
            # 名-CRU: uma lingua num dado partilhado — fica o canonico.
            item_data={"npc": True, "seller_name": "🏮 Immortal Merchant", "pill_name": pill.name},
            quantity=1,
            unit_price=starting_bid,
            is_auction=True,
            current_bid=None,
            highest_bidder=None,
            expires_at=event_expires_at,
            is_sold=False,
            created_at=now,
        )
        session.add(listing)
        created += 1

    logger.info("🏮 Immortal Auction: injected %d NPC listings", created)
    return created




async def broadcast_message(bot, text: str, _session=None) -> None:
    """Send a pre-formatted message to all players (same text for all languages).
    Kept for backward compatibility — prefer core.announcement_engine.broadcast() for i18n-aware sends.
    """
    import asyncio as _asyncio
    from sqlalchemy import select as _select
    from database.models import Player as _Player

    async with get_session_factory()() as s:
        player_ids = (await s.execute(_select(_Player.telegram_id))).scalars().all()

    for pid in player_ids:
        try:
            await bot.send_message(chat_id=pid, text=text, parse_mode="Markdown")
            await _asyncio.sleep(0.05)
        except Exception:
            pass

async def events_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    data = query.data

    if data in ("cmd_events", "events_list"):
        await events_command(update, context)
        return True

    return False
