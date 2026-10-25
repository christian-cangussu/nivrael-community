from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from database.db import get_session_factory
from database.models import Player, GachaBanner
from core.monetization import (
    perform_gacha_pull,
    get_gacha_pity,
    GACHA_COST,
    ensure_default_banner
)
from sqlalchemy import select

from core.utils import _ensure_player, safe_handler, rate_limit, escape_markdown, safe_answer
from core.i18n import t
from database.models import PlayerInventory


async def _get_ticket_count(session, player_id: int) -> int:
    """Get the number of gacha tickets in player's inventory."""
    ticket_inv = (await session.execute(
        select(PlayerInventory).where(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "gacha_ticket",
            PlayerInventory.item_id == 0,
        )
    )).scalar_one_or_none()
    return ticket_inv.quantity if ticket_inv else 0


def _gacha_menu_text(lang: str, banner, player, pity: int, tickets: int = 0) -> str:
    cost_10 = int(GACHA_COST * 10 * 0.9)
    text = (
        f"🎁 *{escape_markdown(banner.name)}* 🎁\n\n"
        f"_{escape_markdown(banner.description)}_\n\n"
        f"{t(lang, 'gacha_jade_balance', amount=player.spirit_jade)}\n"
        f"{t(lang, 'gacha_pity_current', current=pity, max=banner.pity_at)}\n\n"
        f"{t(lang, 'gacha_pull_desc', cost=GACHA_COST, cost_10=cost_10)}"
    )
    if tickets > 0:
        text += "\n" + t(lang, "gacha_tickets_balance", tickets=tickets)
    return text


def _gacha_menu_keyboard(lang: str, banner_id, tickets: int = 0) -> InlineKeyboardMarkup:
    cost_10 = int(GACHA_COST * 10 * 0.9)
    rows = [
        [
            InlineKeyboardButton(t(lang, "btn_gacha_1", cost=GACHA_COST), callback_data=f"gacha_pull_1_{banner_id}"),
            InlineKeyboardButton(t(lang, "btn_gacha_10", cost_10=cost_10), callback_data=f"gacha_pull_10_{banner_id}"),
        ],
    ]
    if tickets >= 1:
        ticket_row = [InlineKeyboardButton(t(lang, "btn_gacha_ticket_1", tickets=tickets), callback_data=f"gacha_ticket_1_{banner_id}")]
        if tickets >= 10:
            ticket_row.append(InlineKeyboardButton(t(lang, "btn_gacha_ticket_10"), callback_data=f"gacha_ticket_10_{banner_id}"))
        rows.append(ticket_row)
    rows.append([
        InlineKeyboardButton(t(lang, "btn_shop_vip"), callback_data="shop_main"),
        InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_status"),
    ])
    return InlineKeyboardMarkup(rows)


def _format_pull_results(lang: str, res: dict) -> str:
    from core.visual_engine import gacha_legendary_art
    from config import ARTIFACT_GRADES

    GRADE_EMOJIS = {
        0: "🪨", 1: "🟡", 2: "🔮", 3: "🌍",
        4: "☁️", 5: "👻", 6: "💎", 7: "🌌",
    }

    lines = [t(lang, "gacha_pull_results"), ""]

    legendary_arts = []
    for i, item in enumerate(res["results"]):
        pity_tag = " *(PITY)*" if item["is_pity"] else ""

        # Artifacts: show catalog grade instead of gacha rarity
        if item.get("type") == "artifact" and item.get("art_grade") is not None:
            grade = item["art_grade"]
            grade_name = ARTIFACT_GRADES.get(grade, f"G{grade}")
            grade_emoji = GRADE_EMOJIS.get(grade, "🤍")
            lines.append(f"{i+1}. {grade_emoji} {item['name']} ({grade_name}){pity_tag}")
        else:
            rarity_emoji = {
                "legendary": "🌟",
                "epic": "💜",
                "rare": "💙",
                "common": "🤍",
            }.get(item["rarity"], "🤍")
            lines.append(f"{i+1}. {rarity_emoji} {item['name']} ({item['rarity'].title()}){pity_tag}")

        if item["rarity"] == "legendary":
            legendary_arts.append(gacha_legendary_art(item["name"], lang=lang))

    lines.append("")
    lines.append(t(lang, "gacha_new_pity", pity=res["new_pity"]))
    if "cost" in res:
        lines.append(t(lang, "gacha_jade_spent", cost=res["cost"], remaining=res["remaining_jade"]))
    else:
        lines.append(t(lang, "gacha_jade_remaining", remaining=res["remaining_jade"]))

    if legendary_arts:
        lines.append("")
        lines.extend(legendary_arts)

    return "\n".join(lines)


@safe_handler
@rate_limit(1)
async def cmd_gacha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        from core.monetization import gacha_enabled
        if not gacha_enabled():
            await update.message.reply_text(t(lang, "err_gacha_official_only"))
            return
        await ensure_default_banner(session)

        stmt = select(GachaBanner).where(GachaBanner.is_active == True)
        banners = (await session.execute(stmt)).scalars().all()

        if not banners:
            await update.message.reply_text(t(lang, "gacha_no_banner"))
            return

        banner = banners[0]
        pity = await get_gacha_pity(session, player.telegram_id, banner.id)
        tickets = await _get_ticket_count(session, player.telegram_id)

    text = _gacha_menu_text(lang, banner, player, pity, tickets)
    keyboard = _gacha_menu_keyboard(lang, banner.id, tickets)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def handle_gacha_pulls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    data = query.data.split("_")

    # Expected: gacha, pull, <num>, <banner_id>
    if len(data) < 4:
        return

    try:
        num_pulls = int(data[2])
    except (ValueError, IndexError):
        return
    if num_pulls not in (1, 10):
        return
    banner_id = "_".join(data[3:])

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        res = await perform_gacha_pull(session, player.telegram_id, num_pulls, banner_id)
        pity = await get_gacha_pity(session, player.telegram_id, banner_id)
        stmt = select(GachaBanner).where(GachaBanner.id == banner_id)
        banner = (await session.execute(stmt)).scalar_one_or_none()
        await session.commit()

    if not res["success"]:
        error_msg = t(lang, res.get("error_key", "err_player_not_found"), **res.get("error_params", {}))
        await safe_answer(query, error_msg, show_alert=True)
        return

    header_text = _gacha_menu_text(lang, banner, player, pity)
    pull_text = _format_pull_results(lang, res)
    results_text = f"{header_text}\n\n{'—'*24}\n\n{pull_text}"

    cost_10 = int(GACHA_COST * 10 * 0.9)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(lang, "btn_gacha_more_1"), callback_data=f"gacha_pull_1_{banner_id}"),
            InlineKeyboardButton(t(lang, "btn_gacha_more_10"), callback_data=f"gacha_pull_10_{banner_id}"),
        ],
        [InlineKeyboardButton(t(lang, "btn_gacha_back"), callback_data="gacha_menu")],
    ])

    await query.edit_message_text(results_text, parse_mode="Markdown", reply_markup=keyboard)


@safe_handler
@rate_limit(1)
async def cmd_pull(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Route /pull directly to the inline menu
    await cmd_gacha(update, context)


async def handle_gacha_ticket_pulls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle gacha pulls paid with tickets instead of jade."""
    query = update.callback_query
    await safe_answer(query)
    data = query.data.split("_")

    # Expected: gacha, ticket, <num>, <banner_id>
    if len(data) < 4:
        return

    try:
        num_pulls = int(data[2])
    except (ValueError, IndexError):
        return
    if num_pulls not in (1, 10):
        return
    banner_id = "_".join(data[3:])

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        res = await perform_gacha_pull(session, player.telegram_id, num_pulls, banner_id, use_tickets=True)
        pity = await get_gacha_pity(session, player.telegram_id, banner_id)
        stmt = select(GachaBanner).where(GachaBanner.id == banner_id)
        banner = (await session.execute(stmt)).scalar_one_or_none()
        tickets = await _get_ticket_count(session, player.telegram_id)
        await session.commit()

    if not res["success"]:
        error_key = res.get("error_key", "err_player_not_found")
        error_msg = t(lang, error_key, **res.get("error_params", {}))
        await safe_answer(query, error_msg, show_alert=True)
        return

    header_text = _gacha_menu_text(lang, banner, player, pity, tickets)
    pull_text = _format_pull_results(lang, res)
    results_text = f"{header_text}\n\n{'—'*24}\n\n{pull_text}"

    rows = [
        [
            InlineKeyboardButton(t(lang, "btn_gacha_more_1"), callback_data=f"gacha_pull_1_{banner_id}"),
            InlineKeyboardButton(t(lang, "btn_gacha_more_10"), callback_data=f"gacha_pull_10_{banner_id}"),
        ],
    ]
    if tickets >= 1:
        ticket_row = [InlineKeyboardButton(t(lang, "btn_gacha_ticket_1", tickets=tickets), callback_data=f"gacha_ticket_1_{banner_id}")]
        if tickets >= 10:
            ticket_row.append(InlineKeyboardButton(t(lang, "btn_gacha_ticket_10"), callback_data=f"gacha_ticket_10_{banner_id}"))
        rows.append(ticket_row)
    rows.append([InlineKeyboardButton(t(lang, "btn_gacha_back"), callback_data="gacha_menu")])
    keyboard = InlineKeyboardMarkup(rows)

    await query.edit_message_text(results_text, parse_mode="Markdown", reply_markup=keyboard)


async def return_gacha_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        from core.monetization import gacha_enabled
        if not gacha_enabled():
            await query.edit_message_text(t(lang, "err_gacha_official_only"))
            return
        stmt = select(GachaBanner).where(GachaBanner.is_active == True)
        banners = (await session.execute(stmt)).scalars().all()

        if not banners:
            await query.edit_message_text(t(lang, "gacha_no_banner"))
            return

        banner = banners[0]
        pity = await get_gacha_pity(session, player.telegram_id, banner.id)
        tickets = await _get_ticket_count(session, player.telegram_id)

    text = _gacha_menu_text(lang, banner, player, pity, tickets)
    keyboard = _gacha_menu_keyboard(lang, banner.id, tickets)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)


def secure_cmd(func, limit=1):
    from core.utils import safe_handler, rate_limit
    return safe_handler(rate_limit(limit)(func))


def setup_gacha_handlers(application):
    application.add_handler(CommandHandler("gacha", secure_cmd(cmd_gacha)))
    application.add_handler(CommandHandler("pull", secure_cmd(cmd_pull)))

    application.add_handler(CallbackQueryHandler(secure_cmd(handle_gacha_pulls), pattern="^gacha_pull_.*$"))
    application.add_handler(CallbackQueryHandler(secure_cmd(handle_gacha_ticket_pulls), pattern="^gacha_ticket_.*$"))
    application.add_handler(CallbackQueryHandler(secure_cmd(return_gacha_menu), pattern="^gacha_menu$"))
