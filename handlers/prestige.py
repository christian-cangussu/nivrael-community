import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

logger = logging.getLogger(__name__)

from database.db import get_session_factory
from database.models import Player
from core.prestige_engine import can_prestige, process_prestige, get_prestige_title, get_player_techniques
from core.i18n import t

from core.utils import escape_markdown, _ensure_player, safe_handler, rate_limit, safe_answer, normalize_lang

@safe_handler
@rate_limit(1)
async def renascer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = normalize_lang(player.language)

        if not can_prestige(player):
            text = t(lang, "prestige_req_not_met", req_realm="True Immortal IX")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_premium")]])
            if update.callback_query:
                await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
            return

        text = t(lang, "prestige_confirm_warning")
        
        # O jogador pode escolher reter uma técnica. Mostrar a lista.
        techs = await get_player_techniques(session, player.telegram_id)
        
        buttons = []
        if techs:
            for pt, ct in techs:
                buttons.append([InlineKeyboardButton(t(lang, "prestige_retain_tech", emoji=ct.emoji, name=ct.name), callback_data=f"prestige_confirm_{ct.id}")])
            buttons.append([InlineKeyboardButton(t(lang, "btn_prestige_no_tech"), callback_data="prestige_confirm_none")])
        else:
            text += t(lang, "prestige_no_techs_retained")
            buttons.append([InlineKeyboardButton("⚠️ " + t(lang, "btn_confirm_prestige"), callback_data="prestige_confirm_none")])

        # QoL 09/08 Item D (report [jogador]) — a geografia dita ANTES do tap.
        # Renascer é irreversível e não muda o continente: com
        # `dungeons_regionais` ON, quem renasce em Mòyǔ fica até ao reino 5 sem
        # UMA porta. O aviso é a última linha antes dos botões (Lei §1).
        from core.dungeon_regions import rebirth_portal_warning
        _geo_warn = await rebirth_portal_warning(session, player, lang)
        if _geo_warn:
            text += "\n\n" + _geo_warn

        # 轮回 (pergunta do [jogador] 14/08) — o Caminho re-deriva do karma que a alma
        # carrega. Dito ANTES do tap, com antes→depois: renascer é irreversível,
        # e uma mudança de caminho por SURPRESA seria pior do que o dead-end que
        # esta correção paga. None quando não muda (o caso normal).
        from core.karma_engine import rebirth_path_preview
        _path_warn = await rebirth_path_preview(session, player, lang)
        if _path_warn:
            text += "\n\n" + _path_warn

        buttons.append([InlineKeyboardButton("❌ " + t(lang, "btn_cancel"), callback_data="nav_premium")])
        kb = InlineKeyboardMarkup(buttons)

        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

@safe_handler
async def prestige_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)

    data = query.data.replace("prestige_confirm_", "")
    retained_technique = int(data) if data != "none" else None

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = normalize_lang(player.language)

        if not can_prestige(player):
            await safe_answer(query, t(lang, "prestige_req_not_met", req_realm="True Immortal IX"), show_alert=True)
            return

        try:
            _, unequipped_count = await process_prestige(session, player, retained_technique)
            from core.achievement_engine import check_achievements
            prestige_ach = await check_achievements(session, player.telegram_id, "prestige_count", player.prestige_level)
            await session.commit()

            if prestige_ach:
                from handlers.achievements import notify_achievements
                await notify_achievements(context, player.telegram_id, prestige_ach)

            p_level = player.prestige_level
            title = get_prestige_title(p_level)

            text = t(lang, "prestige_success", level=p_level, title=title)
            if unequipped_count > 0:
                text += "\n" + t(lang, "prestige_artifacts_unequipped", count=unequipped_count)
            
            # Global Announcement — only active players (last 7 days)
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            stmt_all = select(Player.telegram_id, Player.language).where(Player.last_online >= cutoff)
            all_players = (await session.execute(stmt_all)).all()

            sent, failed = 0, 0
            for pid, plang in all_players:
                try:
                    announcement = t(plang or "en", "prestige_global_announcement", name=escape_markdown(player.dao_name or player.display_name or player.username), level=p_level)
                    await context.bot.send_message(chat_id=pid, text=announcement, parse_mode="Markdown")
                    sent += 1
                except Exception as e:
                    failed += 1
                await asyncio.sleep(0.05)
            logger.info("📢 Prestige broadcast: %d sent, %d failed, %d total", sent, failed, len(all_players))

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_prestige_menu"), callback_data="cmd_prestige")],
                [InlineKeyboardButton(t(lang, "btn_status"), callback_data="cmd_status")]
            ])

            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

        except Exception as e:
            await session.rollback()
            logger.error(f"Prestige error for {update.effective_user.id}: {e}", exc_info=True)
            await query.message.edit_text(t(lang, "err_generic"))

@safe_handler
@rate_limit(1)
async def prestige_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = normalize_lang(player.language)
        p_level = player.prestige_level
        
        if p_level == 0:
            text = t(lang, "prestige_none")
        else:
            title = get_prestige_title(p_level)
            mult = p_level * 1
            pp = player.prestige_points
            
            text = t(lang, "prestige_status_menu", title=title, level=p_level, mult=mult, pp=pp)

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛍️ " + t(lang, "btn_prestige_shop"), callback_data="cmd_loja_prestige")],
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_status")],
        ])

        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

@safe_handler
@rate_limit(1)
async def loja_prestige_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v14.14c — Real Prestige Shop. Lists catalog with per-item gate/cap state.

    Engine canónica: `core.prestige_shop_engine`. Chat e mini-app partilham
    a mesma catalog list e validações.
    """
    from core.prestige_shop_engine import get_shop_view, get_item

    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = normalize_lang(player.language)
        view = await get_shop_view(session, player)

    pp = view["prestige_points"]
    p_level = view["prestige_level"]
    text = t(lang, "prestige_shop_header", pp=pp, p_level=p_level)

    buttons = []
    for it in view["items"]:
        catalog = get_item(it["id"])
        if not catalog:
            continue
        name = t(lang, f"prestige_shop_item_{it['id']}_name")
        emoji = it["emoji"]
        cost = it["cost"]
        bought = it["purchased_count"]
        cap = it["max_purchases"]
        # State badge: 🔒 locked · ✔️ cap_reached · 💸 affordable · 🚫 too poor
        if it["locked"]:
            badge = t(lang, "prestige_shop_locked_badge", min=it["min_prestige"])
        elif it["cap_reached"]:
            badge = t(lang, "prestige_shop_owned_badge")
        elif it["affordable"]:
            badge = t(lang, "prestige_shop_cost_badge", cost=cost)
        else:
            badge = t(lang, "prestige_shop_short_badge", cost=cost)
        cap_str = f" ({bought}/{cap})" if cap > 0 else (f" ({bought})" if bought > 0 else "")
        label = f"{emoji} {name}{cap_str} — {badge}"
        # Disable button by routing to a no-op-ish callback when locked/cap.
        cb = f"prestige_buy_{it['id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=cb)])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_prestige")])
    kb = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def prestige_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v14.14c — Real buy. callback_data format: prestige_buy_<item_id>."""
    from core.prestige_shop_engine import buy_shop_item, get_item

    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    item_id = query.data.replace("prestige_buy_", "", 1)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            await safe_answer(query)
            return
        lang = normalize_lang(player.language)

        if not get_item(item_id):
            await safe_answer(query, t(lang, "prestige_shop_err_unknown"), show_alert=True)
            return

        res = await buy_shop_item(session, player, item_id)
        if not res.get("ok"):
            reason = res.get("reason")
            if reason == "prestige_locked":
                msg = t(lang, "prestige_shop_err_locked", min=res.get("min_prestige", 0))
            elif reason == "cap_reached":
                msg = t(lang, "prestige_shop_err_cap")
            elif reason == "not_enough_points":
                msg = t(lang, "prestige_shop_err_short",
                        cost=res.get("cost", 0), have=res.get("have", 0))
            else:
                msg = t(lang, "prestige_shop_err_unknown")
            await safe_answer(query, msg, show_alert=True)
            await session.rollback()
            return

        await session.commit()
        name = t(lang, f"prestige_shop_item_{item_id}_name")
        await safe_answer(
            query,
            t(lang, "prestige_shop_bought_toast", name=name, cost=res["cost"]),
            show_alert=False,
        )

    # Refresh the shop menu so counts/costs update.
    await loja_prestige_command(update, context)

@safe_handler
@rate_limit(1)
async def prestige_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query.data.startswith("prestige_confirm_"):
        await prestige_confirm_callback(update, context)
        return True
    elif query.data.startswith("prestige_buy_"):
        await prestige_buy_callback(update, context)
        return True
    elif query.data in ["cmd_renascer"]:
        await safe_answer(query)
        await renascer_command(update, context)
        return True
    elif query.data in ["cmd_prestige"]:
        await safe_answer(query)
        await prestige_command(update, context)
        return True
    elif query.data in ["cmd_loja_prestige"]:
        await safe_answer(query)
        await loja_prestige_command(update, context)
        return True
    return False
