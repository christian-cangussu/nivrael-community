from core.utils import safe_handler, rate_limit, build_pagination_keyboard, escape_markdown, safe_answer, safe_parse_callback_int, normalize_lang, resolve_chat_player_id
from core.i18n import t
import logging
from datetime import datetime, timezone
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

from core.beast_engine import (
    get_player_beasts,
    get_beast_catalog,
    get_beast_catalog_by_id,
    get_expedition_catalog,
    expedition_display_name as _exp_name,
    expedition_display_desc as _exp_desc,
    get_companion_beast,
    set_companion,
    remove_companion,
    train_beast,
    train_beast_bulk,
    evolve_beast,
    send_on_expedition,
    collect_expedition,
    attempt_capture,
    # 獸 2026-09-15 — o dono único do nome da besta. O chat imprimia "Thunder Ox"
    # nas sete telas abaixo enquanto o mini-app já estava pronto para o traduzir:
    # a inconsistência que a Lei 0 diz ser pior do que a ausência.
    beast_display_name,
    # 🐾 3.3 (2026-10-01) — o limiar de XP e a habilidade tem dono no motor:
    # o detalhe abaixo fazia `beast.level * 100` e imprimia a frase inglesa.
    limiar_xp,
    beast_ability_text,
)
from core.i18n import catalog_desc
from core.game_logic import format_number, get_time_display
from config import BEAST_RANKS, BEAST_RANK_INDEX
from database.db import get_session_factory
from database.models import PlayerBeast, BeastCatalog, Player, PlayerInventory

logger = logging.getLogger(__name__)


@safe_handler
@rate_limit(1)
async def bestiario_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    user = update.effective_user
    if not user:
        return

    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(user.id))
        )).scalar_one_or_none()
        if not player:
            msg = t(lang, "msg_use_start")
            if update.callback_query:
                await update.callback_query.message.edit_text(msg)
            else:
                await update.message.reply_text(msg)
            return

        lang = normalize_lang(player.language)

        beasts = await get_player_beasts(session, user.id)
        catalog_map = {}
        all_catalog = await get_beast_catalog(session)
        for c in all_catalog:
            catalog_map[c.id] = c

        if not beasts:
            text = t(lang, "beasts_title") + t(lang, "beasts_empty")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_beasts_capture"), callback_data="beast_capture_menu")],
                [InlineKeyboardButton(t(lang, "btn_beasts_catalog"), callback_data="beast_catalog")],
                [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")],
            ])
        else:
            page = 0
            if context.args and len(context.args) > 0 and context.args[0].isdigit():
                page = int(context.args[0])
                
            ITEMS_PER_PAGE = 5
            total_items = len(beasts)
            total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
            paginated_beasts = beasts[page * ITEMS_PER_PAGE : (page + 1) * ITEMS_PER_PAGE]
            
            lines = [
                t(lang, "beasts_title").strip("\n"),
                "",
            ]
            for b in paginated_beasts:
                c = catalog_map.get(b.catalog_id)
                emoji = c.emoji if c else "🐾"
                name = beast_display_name(lang, b, c)
                status = ""
                if b.is_companion:
                    status = t(lang, "beast_companion_label")
                elif b.is_on_expedition:
                    if b.expedition_returns_at and datetime.now(timezone.utc) >= b.expedition_returns_at:
                        status = t(lang, "beast_expedition_completed")
                    else:
                        status = f" 🗺️ _{escape_markdown(_exp_name(lang, b.expedition_type))}_"
                lines.append(f"{emoji} *{name}* — {b.rank} Lv.{b.level}{status}")

            text = "\n".join(lines)
            buttons = []
            for b in paginated_beasts:
                c = catalog_map.get(b.catalog_id)
                emoji = c.emoji if c else "🐾"
                name = beast_display_name(lang, b, c)
                short = f"{emoji} {name}"
                buttons.append([InlineKeyboardButton(short, callback_data=f"beast_detail_{b.id}")])

            if total_pages > 1:
                buttons.extend(build_pagination_keyboard(page + 1, total_pages, "bestiario_page_", player.language))

            buttons.append([
                InlineKeyboardButton(t(lang, "btn_beasts_capture"), callback_data="beast_capture_menu"),
                InlineKeyboardButton(t(lang, "btn_beasts_catalog"), callback_data="beast_catalog"),
            ])
            buttons.append([InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")])
            kb = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def bestiario_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    _raw = safe_parse_callback_int(query.data, "bestiario_page_")
    if _raw is None:
        return
    page = _raw - 1
    context.args = [str(page)]
    await bestiario_command(update, context)


async def beast_detail_view(update: Update, context: ContextTypes.DEFAULT_TYPE, beast_id: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        beast = (await session.execute(
            select(PlayerBeast).where(
                PlayerBeast.player_id == user.id,
                PlayerBeast.id == beast_id,
            )
        )).scalar_one_or_none()
        if not beast:
            await safe_answer(query, t(lang, "ans_beast_não_encontrada"), show_alert=True)
            return

        catalog = await get_beast_catalog_by_id(session, beast.catalog_id)
        name = beast_display_name(lang, beast, catalog)
        emoji = catalog.emoji if catalog else "🐾"
        rank_idx = BEAST_RANK_INDEX.get(beast.rank, 0)
        exp_needed = limiar_xp(beast.level)

        # Display the EVOLVED + LEVELED bonuses (mirror what
        # get_companion_bonuses applies at companion-time) instead of the
        # static catalog base_stats. Owner report 2026-05-10 ([jogador]):
        # "As evoluções de pet não aumentam os bônus" — Celestial Crane at
        # Legendary L1 and Divine L100 displayed identical +20% Perception
        # / +10% CB. Engine was correct (evolution_mult + level_scale apply
        # in get_companion_bonuses), but this VIEW read catalog.base_stats
        # directly and never reflected the player's evolved+leveled state.
        from core.beast_engine import get_companion_bonuses
        stats_lines = []
        if catalog:
            calc = get_companion_bonuses(beast, catalog)
            for key, base_val in (catalog.base_stats or {}).items():
                label = key.replace("_mult", "").replace("_", " ").title()
                effective = calc.get(key, base_val)
                pct = (effective - 1.0) * 100
                stats_lines.append(f"  • {label}: +{pct:.0f}%")

        status_line = t(lang, "beast_status_free")
        if beast.is_companion:
            status_line = t(lang, "beast_status_companion")
        elif beast.is_on_expedition:
            if beast.expedition_returns_at and datetime.now(timezone.utc) >= beast.expedition_returns_at:
                status_line = t(lang, "beast_expedition_completed").strip()
            else:
                remaining = ""
                if beast.expedition_returns_at:
                    delta = (beast.expedition_returns_at - datetime.now(timezone.utc)).total_seconds()
                    remaining = f" ({get_time_display(max(0, delta))})"
                status_line = f"🗺️ {_exp_name(lang, beast.expedition_type)}{remaining}"

        no_bonus = t(lang, "beast_detail_no_bonus")
        text = (
            f"{emoji} *{name}*\n"
            f"———————————————————————\n"
            f"{t(lang, 'beast_detail_rank')}*{beast.rank}* ({BEAST_RANKS[rank_idx]})\n"
            f"{t(lang, 'beast_detail_level')}*{beast.level}*\n"
            f"{t(lang, 'beast_detail_exp')}{beast.exp}/{exp_needed}\n"
            f"{t(lang, 'beast_detail_element')}{catalog.element if catalog else '?'}\n\n"
            f"{t(lang, 'beast_detail_passive')}\n"
            + ("\n".join(stats_lines) if stats_lines else no_bonus) + "\n\n"
            f"{t(lang, 'beast_detail_skill')}_{escape_markdown(beast_ability_text(lang, catalog) if catalog else '?')}_\n\n"
            f"{t(lang, 'beast_detail_status')}{status_line}\n"
            f"———————————————————————"
        )

        buttons = []
        if beast.is_companion:
            buttons.append([InlineKeyboardButton(t(lang, "btn_beasts_remove_companion"), callback_data=f"beast_uncompanion_{beast_id}")])
        elif not beast.is_on_expedition:
            buttons.append([InlineKeyboardButton(t(lang, "btn_beasts_make_companion"), callback_data=f"beast_companion_{beast_id}")])

        if not beast.is_on_expedition and not beast.is_companion:
            buttons.append([InlineKeyboardButton(t(lang, "btn_beasts_expedition"), callback_data=f"beast_exp_pick_{beast_id}")])

        if beast.is_on_expedition and beast.expedition_returns_at and datetime.now(timezone.utc) >= beast.expedition_returns_at:
            buttons.append([InlineKeyboardButton(t(lang, "btn_beasts_collect"), callback_data=f"beast_collect_{beast_id}")])

        if not beast.is_on_expedition:
            buttons.append([
                InlineKeyboardButton(t(lang, "btn_beasts_train"), callback_data=f"beast_train_{beast_id}"),
                InlineKeyboardButton(t(lang, "btn_beasts_evolve"), callback_data=f"beast_evolve_{beast_id}"),
            ])

        buttons.append([InlineKeyboardButton(t(lang, "btn_beasts_back"), callback_data="cmd_bestiario")])
        kb = InlineKeyboardMarkup(buttons)

    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_catalog_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query

    async with get_session_factory()() as session:
        catalog = await get_beast_catalog(session)
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id))
        )).scalar_one_or_none()
        lang = normalize_lang(player.language)

    page = 0
    if context.args and len(context.args) > 0 and context.args[0].isdigit():
        page = int(context.args[0])
        
    ITEMS_PER_PAGE = 5
    total_items = len(catalog)
    total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
    paginated_catalog = catalog[page * ITEMS_PER_PAGE : (page + 1) * ITEMS_PER_PAGE]

    lines = [
        t(lang, "beasts_catalog_title").strip("\n"),
        "",
    ]
    for c in paginated_catalog:
        catch_pct = c.catch_rate * 100
        lines.append(f"{c.emoji} *{beast_display_name(lang, None, c)}* — {c.rank}")
        lines.append(f"  🌀 {c.element} | 🎯 {catch_pct:.0f}% {t(lang, 'beasts_catalog_base_catch')}")
        _desc_c = catalog_desc(lang, "beast", c, fallback=c.description or "")
        lines.append(f"  _{escape_markdown(_desc_c[:60])}..._\n")

    text = "\n".join(lines)
    buttons = []
    
    if total_pages > 1:
        buttons.extend(build_pagination_keyboard(page + 1, total_pages, "beast_catalog_page_", lang))
        
    buttons.append([InlineKeyboardButton(t(lang, "btn_beasts_back"), callback_data="cmd_bestiario")])
    kb = InlineKeyboardMarkup(buttons)
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_catalog_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    _raw = safe_parse_callback_int(query.data, "beast_catalog_page_")
    if _raw is None:
        return
    page = _raw - 1
    context.args = [str(page)]
    await beast_catalog_view(update, context)


async def beast_capture_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        trap_rows = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == user.id,
                PlayerInventory.item_type == "beast_trap",
            )
        )).scalars().all()
        trap_count = sum(r.quantity for r in trap_rows) if trap_rows else 0

        catalog = await get_beast_catalog(session)

    lines = [
        t(lang, "beasts_capture_title").strip("\n"),
        "",
        f"{t(lang, 'beasts_capture_available')}*{trap_count}*\n",
    ]
    if trap_count == 0:
        lines.append(t(lang, "beasts_capture_no_traps"))

    text = "\n".join(lines)
    buttons = []
    if trap_count > 0:
        for c in catalog:
            catch_pct = c.catch_rate * 100
            buttons.append([InlineKeyboardButton(
                f"{c.emoji} {beast_display_name(lang, None, c)} "
                f"({c.rank}, {catch_pct:.0f}%)",
                callback_data=f"beast_catch_{c.id}",
            )])
    buttons.append([InlineKeyboardButton(t(lang, "btn_beasts_back"), callback_data="cmd_bestiario")])
    kb = InlineKeyboardMarkup(buttons)
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_catch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, catalog_id: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    beast_ach = []
    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        result = await attempt_capture(session, user.id, catalog_id)
        if result.get("captured"):
            from sqlalchemy import select as _sel, func as _func
            from database.models import PlayerBeast as _PB
            total_captured = (await session.execute(
                _sel(_func.count()).select_from(_PB).where(_PB.player_id == user.id)
            )).scalar() or 0
            from core.achievement_engine import check_achievements
            beast_ach += await check_achievements(session, user.id, "beasts_captured", 1)
            beast_ach += await check_achievements(session, user.id, "beasts_owned", total_captured)
        await session.commit()

    if beast_ach:
        from handlers.achievements import notify_achievements
        await notify_achievements(context, user.id, beast_ach)

    if not result["success"] and not result.get("captured", True):
        chance_str = t(lang, "beasts_capture_chance", chance=f"{result['chance']*100:.1f}")
        text = (
            t(lang, "beasts_capture_attempt") +
            f"{result['emoji']} *{result['beast_name']}*{t(lang, 'beasts_capture_escaped')}" +
            chance_str
        )
    elif result.get("captured"):
        text = (
            t(lang, "beasts_capture_success") +
            f"{result['emoji']} *{result['beast_name']}*{t(lang, 'beasts_capture_caught')}" +
            f"{t(lang, 'beast_detail_rank')}*{result['rank']}*\n\n" +
            t(lang, "beasts_capture_manage")
        )
    else:
        error_key = result.get("error_key", "err_player_not_found")
        error_params = result.get("error_params", {})
        text = f"❌ {t(lang, error_key, **error_params)}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_beasts_capture_another"), callback_data="beast_capture_menu")],
        [InlineKeyboardButton(t(lang, "btn_beasts_back"), callback_data="cmd_bestiario")],
    ])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_companion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, beast_id: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        success = await set_companion(session, user.id, beast_id)
        await session.commit()

    if success:
        await safe_answer(query, t(lang, "ans_companion_equipado"), show_alert=True)
    else:
        await safe_answer(query, t(lang, "ans_não_foi_possível_equipar"), show_alert=True)

    await beast_detail_view(update, context, beast_id)


async def beast_uncompanion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        await remove_companion(session, user.id)
        await session.commit()

    await safe_answer(query, t(lang, "ans_companion_removido"), show_alert=True)
    await bestiario_command(update, context)


async def beast_train_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, beast_id: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        result = await train_beast(session, user.id, beast_id)
        await session.commit()

    if not result["success"]:
        error_msg = t(lang, result.get("error_key", "err_player_not_found"), **result.get("error_params", {}))
        await safe_answer(query, error_msg, show_alert=True)
        return

    text = (
        t(lang, "beasts_train_title") +
        f"{t(lang, 'beasts_train_cost')}*{format_number(result['cost'])}* {t(lang, 'beasts_train_cost_currency')}\n"
    )
    if result["levels_gained"] > 0:
        text += t(lang, "beasts_train_level_up", levels_gained=result['levels_gained'])
    text += (
        f"{t(lang, 'beasts_train_current_level')}*{result['new_level']}*\n"
        f"{t(lang, 'beast_detail_exp')}{result['exp']}/{result['exp_needed']}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_beasts_train_again"), callback_data=f"beast_train_{beast_id}")],
        [
            InlineKeyboardButton(t(lang, "btn_beasts_train_10"), callback_data=f"beast_trainx_{beast_id}_10"),
            InlineKeyboardButton(t(lang, "btn_beasts_train_max"), callback_data=f"beast_trainx_{beast_id}_max"),
        ],
        [InlineKeyboardButton(t(lang, "btn_beasts_view_back"), callback_data=f"beast_detail_{beast_id}")],
    ])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_train_bulk_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, beast_id: int, mode: str):
    """H-9: train pet +10 levels or until resources run out (MAX)."""
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    target = None if mode == "max" else 10
    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)
        result = await train_beast_bulk(session, user.id, beast_id, target_levels=target)
        await session.commit()

    if not result["success"] and result["levels_gained"] == 0:
        last = result.get("last_error") or {}
        error_msg = t(lang, last.get("error_key", "err_player_not_found"), **last.get("error_params", {}))
        await safe_answer(query, error_msg, show_alert=True)
        return

    text = (
        t(lang, "beasts_train_title") +
        t(lang, "beasts_train_bulk_summary",
          iterations=result["iterations"],
          levels=result["levels_gained"],
          cost=format_number(result["cost"]),
          xp=format_number(result["xp_gained"]),
          new_level=result.get("new_level") or "?")
    )
    if result.get("last_error"):
        text += "\n" + t(lang, "beasts_train_bulk_stopped",
                         reason=t(lang, result["last_error"].get("error_key", "err_player_not_found"),
                                  **result["last_error"].get("error_params", {})))

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_beasts_train_again"), callback_data=f"beast_train_{beast_id}")],
        [
            InlineKeyboardButton(t(lang, "btn_beasts_train_10"), callback_data=f"beast_trainx_{beast_id}_10"),
            InlineKeyboardButton(t(lang, "btn_beasts_train_max"), callback_data=f"beast_trainx_{beast_id}_max"),
        ],
        [InlineKeyboardButton(t(lang, "btn_beasts_view_back"), callback_data=f"beast_detail_{beast_id}")],
    ])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_evolve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, beast_id: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        beast = (await session.execute(
            select(PlayerBeast).where(
                PlayerBeast.player_id == user.id,
                PlayerBeast.id == beast_id,
            )
        )).scalar_one_or_none()
        if not beast:
            await safe_answer(query, t(lang, "ans_beast_não_encontrada"), show_alert=True)
            return

        catalog = await get_beast_catalog_by_id(session, beast.catalog_id)
        name = beast_display_name(lang, beast, catalog)
        emoji = catalog.emoji if catalog else "🐾"

        from core.beast_engine import get_evolution_requirements
        reqs = get_evolution_requirements(beast)

        if reqs.get("at_max"):
            text = (
                f"{emoji} *{name}*{t(lang, 'beasts_evolve_title')}"
                f"{t(lang, 'beasts_evolve_max', rank=beast.rank)}"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_beasts_view_back"), callback_data=f"beast_detail_{beast_id}")],
            ])
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return

        core_inv = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == user.id,
                PlayerInventory.item_type == "beast_core",
            )
        )).scalars().first()
        cores_have = core_inv.quantity if core_inv else 0
        cores_met = cores_have >= reqs["cores_needed"]

        lvl_icon = "✅" if reqs["level_met"] else "❌"
        core_icon = "✅" if cores_met else "❌"
        all_met = reqs["level_met"] and cores_met

        text = (
            f"{emoji} *{name}*{t(lang, 'beasts_evolve_title')}"
            f"🏷️ *{reqs['current_rank']}* → *{reqs['next_rank']}*\n\n"
            f"{t(lang, 'beasts_evolve_reqs')}"
            f"{lvl_icon}{t(lang, 'beasts_evolve_level')}*{beast.level}* / {reqs['level_needed']}\n"
            f"{core_icon}{t(lang, 'beasts_evolve_cores')}*{cores_have}* / {reqs['cores_needed']}\n\n"
        )

        if all_met:
            text += t(lang, "beasts_evolve_ready")
        else:
            if not reqs["level_met"]:
                text += t(lang, "beasts_evolve_hint_level", level_needed=reqs['level_needed'])
            if not cores_met:
                text += t(lang, "beasts_evolve_hint_cores")

        buttons = []
        if all_met:
            buttons.append([InlineKeyboardButton(
                t(lang, "beasts_evolve_btn", next_rank=reqs['next_rank']),
                callback_data=f"beast_evolve_confirm_{beast_id}",
            )])
        buttons.append([InlineKeyboardButton(t(lang, "btn_beasts_view_back"), callback_data=f"beast_detail_{beast_id}")])
        kb = InlineKeyboardMarkup(buttons)

    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_evolve_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, beast_id: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        result = await evolve_beast(session, user.id, beast_id)
        await session.commit()

    if not result["success"]:
        error_msg = t(lang, result.get("error_key", "err_player_not_found"), **result.get("error_params", {}))
        await safe_answer(query, error_msg, show_alert=True)
        return

    text = (
        t(lang, "beasts_evolve_success") +
        f"🏷️ {result['old_rank']} → *{result['new_rank']}*\n"
        f"{t(lang, 'beasts_evolve_cores_used')}*{result['cores_used']}*\n\n"
        + t(lang, "beasts_evolve_power")
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_beasts_view_back"), callback_data=f"beast_detail_{beast_id}")],
    ])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_expedition_pick(update: Update, context: ContextTypes.DEFAULT_TYPE, beast_id: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query

    async with get_session_factory()() as session:
        player = await session.get(Player, update.effective_user.id)
        if player:
            lang = normalize_lang(player.language)

        beast = (await session.execute(
            select(PlayerBeast).where(
                PlayerBeast.id == beast_id,
                PlayerBeast.player_id == update.effective_user.id
            )
        )).scalar_one_or_none()
        if not beast:
            await safe_answer(query, t(lang, "ans_beast_não_encontrada"), show_alert=True)
            return

        expeditions = await get_expedition_catalog(session)
        beast_rank_idx = BEAST_RANK_INDEX.get(beast.rank, 0)

    lines = [
        t(lang, "beasts_expedition_pick_title").strip("\n"),
        "",
    ]
    buttons = []
    for exp in expeditions:
        req_idx = BEAST_RANK_INDEX.get(exp.req_beast_rank, 0)
        if beast_rank_idx >= req_idx:
            status = "✅"
        else:
            status = "🔒"
        lines.append(f"{exp.emoji} *{escape_markdown(_exp_name(lang, exp))}* — {exp.duration_hours}h | {t(lang, 'beasts_expedition_req')}{exp.req_beast_rank}+ {status}")
        lines.append(f"  _{escape_markdown(_exp_desc(lang, exp)[:50])}..._\n")
        if beast_rank_idx >= req_idx:
            buttons.append([InlineKeyboardButton(
                f"{exp.emoji} {_exp_name(lang, exp)} ({exp.duration_hours}h)",
                callback_data=f"beast_exp_go_{beast_id}_{exp.id}",
            )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_beasts_view_back"), callback_data=f"beast_detail_{beast_id}")])

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_expedition_send(update: Update, context: ContextTypes.DEFAULT_TYPE, beast_id: int, exp_id: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        result = await send_on_expedition(session, user.id, beast_id, exp_id)
        if result["success"]:
            from core.quest_engine import track_quest
            await track_quest(session, user.id, "beast_expedition", 1)
        await session.commit()

    if not result["success"]:
        error_msg = t(lang, result.get("error_key", "err_player_not_found"), **result.get("error_params", {}))
        await safe_answer(query, error_msg, show_alert=True)
        return

    await safe_answer(query)
    text = (
        t(lang, "beasts_expedition_start") +
        f"📍 {result['expedition_name']}\n"
        f"{t(lang, 'beasts_expedition_duration')}*{result['duration_hours']}h*\n"
        + t(lang, "beasts_expedition_notify")
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_beasts_back"), callback_data="cmd_bestiario")],
    ])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def beast_collect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, beast_id: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await session.get(Player, user.id)
        if player:
            lang = normalize_lang(player.language)

        result = await collect_expedition(session, user.id, beast_id, lang=lang)
        if result["success"]:
            from core.faction_engine import update_quest_progress as fac_quest_progress
            await fac_quest_progress(session, user.id, "expedition")
        await session.commit()

    if not result["success"]:
        error_msg = t(lang, result.get("error_key", "err_player_not_found"), **result.get("error_params", {}))
        await safe_answer(query, error_msg, show_alert=True)
        return

    drops_display = "\n".join(f"  • {d}" for d in result["drops"]) if result["drops"] else t(lang, "beasts_collect_no_drops")
    text = (
        t(lang, "beasts_collect_title") +
        f"🐾 *{result['beast_name']}*{t(lang, 'beasts_collect_returned')}"
        f"{t(lang, 'beasts_collect_drops')}{drops_display}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_beasts_back"), callback_data="cmd_bestiario")],
    ])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


@safe_handler
@rate_limit(1)
async def beasts_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    data = query.data or ""

    if data == "cmd_bestiario":
        await safe_answer(query)
        await bestiario_command(update, context)
        return True

    if data.startswith("bestiario_page_"):
        await safe_answer(query)
        await bestiario_page_callback(update, context)
        return True

    if data.startswith("beast_catalog_page_"):
        await safe_answer(query)
        await beast_catalog_page_callback(update, context)
        return True

    if data == "beast_catalog":
        await safe_answer(query)
        await beast_catalog_view(update, context)
        return True

    if data == "beast_capture_menu":
        await safe_answer(query)
        await beast_capture_menu(update, context)
        return True

    if data.startswith("beast_catch_"):
        await safe_answer(query)
        catalog_id = safe_parse_callback_int(data, "beast_catch_")
        if catalog_id is None:
            return True
        await beast_catch_handler(update, context, catalog_id)
        return True

    if data.startswith("beast_detail_"):
        await safe_answer(query)
        beast_id = safe_parse_callback_int(data, "beast_detail_")
        if beast_id is None:
            return True
        await beast_detail_view(update, context, beast_id)
        return True

    if data.startswith("beast_companion_"):
        await safe_answer(query)
        beast_id = safe_parse_callback_int(data, "beast_companion_")
        if beast_id is None:
            return True
        await beast_companion_handler(update, context, beast_id)
        return True

    if data.startswith("beast_uncompanion_"):
        await safe_answer(query)
        await beast_uncompanion_handler(update, context)
        return True

    if data.startswith("beast_trainx_"):
        await safe_answer(query)
        rest = data[len("beast_trainx_"):]
        try:
            beast_id_str, mode = rest.rsplit("_", 1)
            beast_id = int(beast_id_str)
        except (ValueError, IndexError):
            return True
        if mode not in ("10", "max"):
            return True
        await beast_train_bulk_handler(update, context, beast_id, mode)
        return True

    if data.startswith("beast_train_"):
        await safe_answer(query)
        beast_id = safe_parse_callback_int(data, "beast_train_")
        if beast_id is None:
            return True
        await beast_train_handler(update, context, beast_id)
        return True

    if data.startswith("beast_evolve_confirm_"):
        await safe_answer(query)
        beast_id = safe_parse_callback_int(data, "beast_evolve_confirm_")
        if beast_id is None:
            return True
        await beast_evolve_confirm_handler(update, context, beast_id)
        return True

    if data.startswith("beast_evolve_"):
        await safe_answer(query)
        beast_id = safe_parse_callback_int(data, "beast_evolve_")
        if beast_id is None:
            return True
        await beast_evolve_handler(update, context, beast_id)
        return True

    if data.startswith("beast_exp_pick_"):
        await safe_answer(query)
        beast_id = safe_parse_callback_int(data, "beast_exp_pick_")
        if beast_id is None:
            return True
        await beast_expedition_pick(update, context, beast_id)
        return True

    if data.startswith("beast_exp_go_"):
        parts = data.split("_")
        try:
            beast_id = int(parts[-2])
            exp_id = int(parts[-1])
        except (ValueError, IndexError):
            return True
        await beast_expedition_send(update, context, beast_id, exp_id)
        return True

    if data.startswith("beast_collect_"):
        await safe_answer(query)
        beast_id = safe_parse_callback_int(data, "beast_collect_")
        if beast_id is None:
            return True
        await beast_collect_handler(update, context, beast_id)
        return True

    return False
