import logging
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, desc
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database.db import get_session_factory
from database.models import (
    Player, Sect, SectMember, SectBuildingLog, SectTerritory, SectWarLog,
    PlayerInventory, TechniqueCatalog, PlayerTechnique, SectContributionLog,
    WorldSectRecruiterPending,
)
from core.utils import escape_markdown, _ensure_player, safe_handler, rate_limit, build_pagination_keyboard, get_display_name, safe_answer, safe_parse_callback_int, add_item_to_inventory, normalize_lang, resolve_chat_player_id
from core.i18n import t, t_optional
# 名 2026-09-14 — o nome da quest vem do dono unico (era `t_optional` a` mao).
from core.i18n import catalog_name, catalog_desc, catalog_text
import math
from core.sect_engine import (
    calculate_upgrade_cost,
    get_training_bonus,
    get_herb_garden_yield,
    get_forge_discount,
    get_library_techniques,
    get_defense_bonus,
    get_spirit_vein_bonus,
    format_building_effect,
    upgrade_building,
    get_player_sect_info,
    is_war_active,
    get_war_state,
    register_war_attack,
    log_sect_contribution,
)
from core.game_logic import format_number

logger = logging.getLogger(__name__)

RANK_KEYS = {
    "master": "rank_master",
    "elder": "rank_elder",
    "disciple": "rank_disciple",
    "member": "rank_member",
}

SCROLL_SHOP_ITEMS = {
    1: {"name": "⚡ Thunder Step", "cost": 500, "req_library": 1},
    4: {"name": "🌑 Shadow Step", "cost": 500, "req_library": 1},
    3: {"name": "🌍 Iron Body", "cost": 800, "req_library": 2},
    2: {"name": "🔥 Dragon Fist", "cost": 2000, "req_library": 3},
    5: {"name": "☯️ Void Slash", "cost": 5000, "req_library": 5},
}

async def seita_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return

        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)

        if not info:
            text = t(lang, "sect_no_sect")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "sect_create_button"), callback_data="sect_create_init")],
                [InlineKeyboardButton(t(lang, "sect_join_button"), callback_data="sect_list")],
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_start")]
            ])
        else:
            member = info["member"]
            sect = info["sect"]
            
            stmt = select(Player).where(Player.telegram_id == sect.master_id)
            master_player = (await session.execute(stmt)).scalar_one_or_none()
            if master_player:
                master_name = master_player.dao_name or get_display_name(master_player)
            else:
                master_name = t(lang, "sect_master_unknown")

            text = (
                t(lang, "sect_title", name=escape_markdown(sect.name)) + "\n" +
                t(lang, "sect_description", desc=escape_markdown(sect.description) if sect.description else "---") + "\n\n" +
                t(lang, "sect_master", name=escape_markdown(master_name)) + "\n" +
                t(lang, "sect_members_count", current=sect.member_count, max=sect.max_members) + "\n" +
                t(lang, "sect_vault_stones", amount=format_number(sect.spirit_stones)) + "\n" +
                t(lang, "sect_my_contribution", amount=format_number(member.contribution_points)) + "\n" +
                t(lang, "sect_my_rank", rank=t(lang, RANK_KEYS.get(member.rank, "rank_member")))
            )

            # v16.1 — Sect Lineage display. NULL → honest disclosure (Lei §1)
            # nudges master to open the mini-app chooser; SET → ancestral
            # name + emoji as a single discreet line. Mini-app first: NO
            # standalone command for lineage choice on chat.
            try:
                from core.sect_lineage_engine import (
                    LINEAGE_META, is_valid_lineage,
                )
                if is_valid_lineage(sect.lineage_key):
                    _ln_meta = LINEAGE_META[sect.lineage_key]
                    _ln_name = t(lang, _ln_meta["name_key"])
                    text += "\n" + t(lang, "sect_lineage_line",
                                     emoji=_ln_meta["emoji"], name=_ln_name)
                else:
                    text += "\n" + t(lang, "sect_lineage_none_warning")
            except Exception:
                logger.debug("sect lineage line render failed", exc_info=True)

            # v14.2 D-3a — surface active /decreto_supremo at the top of the menu.
            from core.sect_engine import get_active_decree
            _decree = get_active_decree(sect)
            if _decree:
                hours_left = max(1, int((_decree["expires_at"] - datetime.now(timezone.utc)).total_seconds() // 3600))
                text += "\n\n" + t(lang, "sect_decree_active",
                                   text=escape_markdown(_decree["text"]),
                                   hours=hours_left)
            
            buttons = [
                [
                    InlineKeyboardButton(t(lang, "btn_sect_info"), callback_data="sect_info"),
                    InlineKeyboardButton(t(lang, "btn_sect_members"), callback_data="sect_members_list")
                ],
                [
                    InlineKeyboardButton(t(lang, "btn_sect_buildings"), callback_data="sect_buildings"),
                    InlineKeyboardButton(t(lang, "btn_sect_vault"), callback_data="sect_vault")
                ],
                [
                    InlineKeyboardButton(t(lang, "btn_sect_war"), callback_data="sect_war_info"),
                    InlineKeyboardButton(t(lang, "btn_sect_shop"), callback_data="sect_shop")
                ],
                [
                    InlineKeyboardButton(t(lang, "btn_sect_bulletin"), callback_data="sect_bulletin"),
                    InlineKeyboardButton(t(lang, "btn_sect_group"), callback_data="sect_group_link")
                ],
            ]
            buttons.append([InlineKeyboardButton(t(lang, "btn_sect_contrib_ranking"), callback_data="sect_contrib_ranking")])
            if member.rank in ("master", "elder"):
                buttons.append([InlineKeyboardButton(t(lang, "btn_sect_contributions"), callback_data="sect_contributions")])
            if member.rank == "master":
                # v14.2 D-3 — discoverability: master-only buttons for the new
                # /decreto_supremo + /passar_tocha rituals.
                buttons.append([
                    InlineKeyboardButton(t(lang, "btn_sect_decree"), callback_data="sect_decree_init"),
                    InlineKeyboardButton(t(lang, "btn_sect_torch"), callback_data="sect_torch_menu"),
                ])
                buttons.append([InlineKeyboardButton(t(lang, "btn_sect_edit_desc"), callback_data="sect_edit_desc")])
            buttons.append([InlineKeyboardButton(t(lang, "btn_sect_leave"), callback_data="sect_leave_confirm")])
            buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_start")])
            kb = InlineKeyboardMarkup(buttons)

        # Pedra 2 — Seita-de-Cultivo/Guild disambiguation (fim do "lio"): a one-line
        # header clarifying THIS is the player Guild (clã); the 9 eternal Seitas de
        # Cultivo that COURT you live in /seita_cultivo. Both branches share it.
        text = t(lang, "sect_guild_disambig") + "\n\n" + text

        try:
            if update.callback_query:
                await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            if "Message is not modified" not in str(e):
                raise

async def sect_edit_desc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank != "master":
            await safe_answer(query, t(update.effective_user.language_code or "en", "ans_apenas_o_mestre_pode"), show_alert=True)
            return

        current = info["sect"].description or "---"
        context.user_data["awaiting_sect_desc"] = True
        await query.message.edit_text(
            t(lang, "sect_desc_edit_prompt", current=current),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")]])
        )

async def process_sect_desc_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    new_desc = update.message.text.strip()[:200]
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank != "master":
            await update.message.reply_text(t(lang, "sect_error_no_permission"))
            return

        info["sect"].description = new_desc
        await session.commit()
        context.user_data.pop("awaiting_sect_desc", None)
        await update.message.reply_text(
            t(lang, "sect_desc_success", new_desc=new_desc),
            parse_mode="Markdown",
        )

async def sect_create_init_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        
        context.user_data["awaiting_sect_name"] = True
        await update.callback_query.message.edit_text(
            t(lang, "sect_create_prompt"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")]])
        )

async def process_sect_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    name = update.message.text
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        # Lock player row to prevent double-spend race condition
        stmt_lock = select(Player).where(Player.telegram_id == player.telegram_id).with_for_update()
        player = (await session.execute(stmt_lock)).scalar_one()

        if player.spirit_stones < 10000:
            await update.message.reply_text(t(lang, "sect_error_stones"))
            return

        stmt = select(SectMember).where(SectMember.player_id == player.telegram_id)
        if (await session.execute(stmt)).scalar_one_or_none():
            await update.message.reply_text(t(lang, "sect_error_in_sect"))
            return

        stmt_n = select(Sect).where(Sect.name == name)
        if (await session.execute(stmt_n)).scalar_one_or_none():
            await update.message.reply_text(t(lang, "sect_error_name_taken"))
            return

        player.spirit_stones -= 10000
        new_sect = Sect(name=name, master_id=player.telegram_id)
        session.add(new_sect)
        await session.flush()

        member = SectMember(sect_id=new_sect.id, player_id=player.telegram_id, rank="master")
        session.add(member)
        from core.achievement_engine import check_achievements
        sect_ach = await check_achievements(session, player.telegram_id, "sect_founded", 1)
        await session.commit()

        context.user_data.pop("awaiting_sect_name", None)
        await update.message.reply_text(t(lang, "sect_create_success", name=escape_markdown(name)), parse_mode="Markdown")
        if sect_ach:
            from handlers.achievements import notify_achievements
            await notify_achievements(context, player.telegram_id, sect_ach)

async def sect_vault_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return

        sect = info["sect"]
        text = (
            t(lang, "btn_sect_vault") + "\n\n" +
            t(lang, "sect_vault_stones", amount=format_number(sect.spirit_stones)) + "\n" +
            t(lang, "sect_my_contribution", amount=format_number(info["member"].contribution_points))
        )
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_sect_donate"), callback_data="sect_donate_init")],
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")]
        ])
        if query:
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def sect_donate_init_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        
        context.user_data["awaiting_sect_donation"] = True
        await update.callback_query.message.edit_text(
            t(lang, "sect_donate_prompt"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_vault")]])
        )

async def process_sect_donation_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A doação por chat. ⚠️ BUG do [jogador] (2026-08-13, s2): *"filled amount,
    clicked donate, return to same window without any confirmation or quest
    completion"* — e o [jogador] confirmou que a escrita funcionava para ele.

    A causa eram QUATRO `return` MUDOS neste handler:
      · `int(update.message.text)` a levantar — "1,000", "1000 pedras" ou um
        espaço a mais e o bot engolia a mensagem sem dizer nada;
      · `amount <= 0` — silêncio;
      · sem jogador — silêncio;
      · **`if not info: return`** — quem NÃO está numa seita de jogador (por
        exemplo quem só pertence a uma Casa NPC) digitava o valor e não recebia
        absolutamente nada de volta.
    Nenhum deles limpava a flag `awaiting_sect_donation`, portanto a mensagem
    seguinte era comida outra vez. Lei §1: nada de void silencioso — cada saída
    diz o motivo, e todas limpam a flag."""
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))

    def _clear() -> None:
        context.user_data.pop("awaiting_sect_donation", None)

    # Parse TOLERANTE: aceita "1.000", "1,000", "1 000" e "1000 pedras".
    raw = (update.message.text or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        _clear()
        await update.message.reply_text(t(lang, "sect_donate_err_number"))
        return
    amount = int(digits)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            _clear()
            await update.message.reply_text(t(lang, "not_registered"))
            return
        lang = player.language or "en"

        if amount <= 0:
            _clear()
            await update.message.reply_text(t(lang, "sect_donate_err_number"))
            return

        # Lock player row to prevent double-spend race condition
        stmt_lock = select(Player).where(Player.telegram_id == player.telegram_id).with_for_update()
        player = (await session.execute(stmt_lock)).scalar_one()

        if player.spirit_stones < amount:
            _clear()
            await update.message.reply_text(t(lang, "sect_error_stones"))
            return

        info = await get_player_sect_info(session, player.telegram_id)
        if not info:
            _clear()
            await update.message.reply_text(t(lang, "sect_donate_err_no_sect"))
            return

        player.spirit_stones -= amount
        info["sect"].spirit_stones += amount
        cp_gained = amount // 100
        info["member"].contribution_points += cp_gained

        await log_sect_contribution(session, player.telegram_id, info["sect"].id, "donation", amount)

        from core.quest_engine import track_quest
        await track_quest(session, player.telegram_id, "sect_contribution", amount)

        await session.commit()
        context.user_data.pop("awaiting_sect_donation", None)
        await update.message.reply_text(t(lang, "sect_donate_success", amount=format_number(amount), cp=cp_gained))

async def sect_buildings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return

        sect = info["sect"]
        # D (2026-06-16): effect strings come from sect_engine.format_building_effect
        # (single source of truth — same formulas the mini-app's api_sect now ships).
        buildings = [
            ("training", "🧘 Training", sect.training_lvl, format_building_effect("training", sect.training_lvl), t(lang, "sect_build_desc_training")),
            ("herb_garden", "🌿 Herb Garden", sect.herb_garden_lvl, format_building_effect("herb_garden", sect.herb_garden_lvl), t(lang, "sect_build_desc_herb_garden")),
            ("forge", "⚒️ Forge", sect.forge_lvl, format_building_effect("forge", sect.forge_lvl), t(lang, "sect_build_desc_forge")),
            ("library", "📜 Library", sect.library_lvl, format_building_effect("library", sect.library_lvl), t(lang, "sect_build_desc_library")),
            ("defense", "🛡️ Defense", sect.defense_lvl, format_building_effect("defense", sect.defense_lvl), t(lang, "sect_build_desc_defense")),
            ("spirit_vein", "💎 Spirit Vein", sect.spirit_vein_lvl, format_building_effect("spirit_vein", sect.spirit_vein_lvl), t(lang, "sect_build_desc_spirit_vein"))
        ]

        text = t(lang, "sect_buildings_title") + "\n\n"
        buttons = []
        for key, name, lvl, effect, desc in buildings:
            cost = calculate_upgrade_cost(lvl)
            text += f"*{name}* (Lvl {lvl})\n└ _{desc}_\n└ *{t(lang, 'sect_build_effect')}:* {effect}\n   💰 Upgrade: {format_number(cost)} 🪨\n\n"
            if info["member"].rank in ["master", "elder"]:
                buttons.append([InlineKeyboardButton(f"Upgrade {name}", callback_data=f"sect_upgrade_{key}")])

        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])
        kb = InlineKeyboardMarkup(buttons)
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

async def sect_upgrade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    building = query.data.replace("sect_upgrade_", "")
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank not in ["master", "elder"]:
            await safe_answer(query, t(lang, "sect_error_rank"), show_alert=True)
            return

        res = await upgrade_building(session, info["sect"].id, building, player.telegram_id)
        if res["success"]:
            await safe_answer(query, t(lang, "sect_upgrade_success", name=building.capitalize(), level=res["new_level"]))
            await session.commit()
            await sect_buildings_menu(update, context)
        else:
            await safe_answer(query, f"❌ {res['error']}", show_alert=True)

async def sect_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        page = 0
        if context.args and len(context.args) > 0 and context.args[0].isdigit():
            page = int(context.args[0])
            
        ITEMS_PER_PAGE = 10
        stmt = select(Sect).order_by(Sect.member_count.desc())
        all_sects = (await session.execute(stmt)).scalars().all()
        
        total_items = len(all_sects)
        total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
        paginated_sects = all_sects[page * ITEMS_PER_PAGE : (page + 1) * ITEMS_PER_PAGE]

        text = t(lang, "sect_list_title", count=total_items) + "\n\n"
        buttons = []
        for s in paginated_sects:
            text += f"🏯 *{escape_markdown(s.name)}* ({s.member_count}/{s.max_members})\n"
            buttons.append([InlineKeyboardButton(t(lang, "btn_join_sect", name=s.name), callback_data=f"sect_join_{s.id}")])
            
        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, "sect_list_page_", lang))
        
        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def sect_list_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    _raw = safe_parse_callback_int(query.data, "sect_list_page_")
    if _raw is None:
        return
    page = _raw - 1
    context.args = [str(page)]
    await sect_list_callback(update, context)

async def sect_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    sect_id = query.data.replace("sect_join_", "")
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        stmt = select(SectMember).where(SectMember.player_id == player.telegram_id)
        if (await session.execute(stmt)).scalar_one_or_none():
            await safe_answer(query, t(lang, "sect_error_in_sect"), show_alert=True)
            return

        stmt_s = select(Sect).where(Sect.id == sect_id)
        sect = (await session.execute(stmt_s)).scalar_one_or_none()
        if not sect:
            await safe_answer(query, t(update.effective_user.language_code or "en", "ans_sect_not_found"), show_alert=True)
            return

        if sect.member_count >= sect.max_members:
            await safe_answer(query, t(update.effective_user.language_code or "en", "ans_sect_is_full"), show_alert=True)
            return

        member = SectMember(sect_id=sect.id, player_id=player.telegram_id, rank="disciple")
        sect.member_count += 1
        session.add(member)
        await session.commit()
        
        await safe_answer(query, t(lang, "sect_join_success", name=sect.name))
        await seita_menu(update, context)

async def sect_members_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """H-13 (v13): accept explicit page so pagination survives re-entry.

    Old version relied on `context.args` mutation which silently failed in
    several flows (list called via "Back" button leaves page=0 and ignores the
    user's clicked page). Now both entry points pass page directly.
    """
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return

        sect = info["sect"]
        my_rank = info["member"].rank

        # Backwards-compat: the original handler still consumed context.args.
        if page == 0 and context.args and len(context.args) > 0 and str(context.args[0]).lstrip("-").isdigit():
            try:
                page = int(context.args[0])
            except ValueError:
                page = 0
        page = max(0, page)

        ITEMS_PER_PAGE = 10
        stmt = (
            select(SectMember, Player)
            .join(Player, SectMember.player_id == Player.telegram_id)
            .where(SectMember.sect_id == sect.id)
            .order_by(SectMember.rank.desc(), SectMember.joined_at.asc())
        )
        members = (await session.execute(stmt)).all()

        total_items = len(members)
        total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
        if page >= total_pages:
            page = total_pages - 1
        paginated_members = members[page * ITEMS_PER_PAGE : (page + 1) * ITEMS_PER_PAGE]

        text = f"👥 *{t(lang, 'sect_members_of', name=escape_markdown(sect.name))}*\n\n"
        if my_rank in ["master", "elder"]:
            text += f"_{t(lang, 'sect_manage_hint')}_"

        # H-14: surface "last seen" so masters/elders can spot inactive members.
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)

        buttons = []
        for m, p in paginated_members:
            rank_emoji = "👑" if m.rank == "master" else "🎖️" if m.rank == "elder" else "👥"
            label = f"{rank_emoji} {escape_markdown(get_display_name(p))}"
            last_active = getattr(p, "last_active_at", None)
            if last_active is not None:
                if last_active.tzinfo is None:
                    last_active = last_active.replace(tzinfo=timezone.utc)
                days = max(0, (now_utc - last_active).days)
                if days >= 1:
                    label += f" · 💤{days}d"
            member_label = f"{label} ({m.rank.capitalize()})"

            can_manage = False
            if m.player_id != player.telegram_id:
                if my_rank == "master":
                    can_manage = True
                elif my_rank == "elder" and m.rank == "disciple":
                    can_manage = True

            if can_manage:
                buttons.append([InlineKeyboardButton(member_label, callback_data=f"sect_manage_{m.player_id}")])
            else:
                buttons.append([InlineKeyboardButton(member_label, callback_data="none")])

        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, "sect_members_page_", lang))

        # H-14: kick-inactive button for masters.
        if my_rank == "master" and total_items > 1:
            buttons.append([InlineKeyboardButton(
                t(lang, "sect_kick_inactive_btn"),
                callback_data="sect_kick_inactive_30",
            )])

        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])
        kb = InlineKeyboardMarkup(buttons)
        if query:
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def sect_members_list_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse the 1-indexed page from the callback and call the list with explicit page."""
    query = update.callback_query
    _raw = safe_parse_callback_int(query.data, "sect_members_page_")
    if _raw is None:
        return
    page_zero_indexed = max(0, _raw - 1)
    await sect_members_list_callback(update, context, page=page_zero_indexed)

async def sect_manage_member_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    target_id = safe_parse_callback_int(query.data, "sect_manage_")
    if target_id is None:
        return
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return
        
        my_rank = info["member"].rank
        if my_rank not in ["master", "elder"]: return
        
        stmt = select(SectMember, Player).join(Player, SectMember.player_id == Player.telegram_id).where(SectMember.player_id == target_id)
        res = (await session.execute(stmt)).first()
        if not res: return
        target_member, target_player = res
        
        text = t(lang, "sect_manage_member_title", name=escape_markdown(get_display_name(target_player)))
        buttons = []
        
        if my_rank == "master":
            if target_member.rank == "disciple":
                buttons.append([InlineKeyboardButton(t(lang, "sect_manage_promote"), callback_data=f"sect_action_promote_{target_id}")])
            elif target_member.rank == "elder":
                buttons.append([InlineKeyboardButton(t(lang, "sect_manage_demote"), callback_data=f"sect_action_demote_{target_id}")])
            
            buttons.append([InlineKeyboardButton(t(lang, "sect_manage_kick"), callback_data=f"sect_action_kick_{target_id}")])
        elif my_rank == "elder" and target_member.rank == "disciple":
            buttons.append([InlineKeyboardButton(t(lang, "sect_manage_kick"), callback_data=f"sect_action_kick_{target_id}")])
            
        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_members_list")])
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def sect_member_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    data = query.data.replace("sect_action_", "")
    parts = data.split("_")
    action = parts[0]
    target_id = int(parts[1])
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return
        
        my_rank = info["member"].rank
        stmt = select(SectMember).where(SectMember.player_id == target_id)
        target_member = (await session.execute(stmt)).scalar_one_or_none()
        if not target_member: return

        if action == "promote" and my_rank == "master":
            target_member.rank = "elder"
            await safe_answer(query, t(update.effective_user.language_code or "en", "ans_promovido_a_elder"))
        elif action == "demote" and my_rank == "master":
            target_member.rank = "disciple"
            await safe_answer(query, t(update.effective_user.language_code or "en", "ans_despromovido_a_discípulo"))
        elif action == "kick":
            if my_rank == "master" or (my_rank == "elder" and target_member.rank == "disciple"):
                info["sect"].member_count -= 1
                await session.delete(target_member)
                await safe_answer(query, t(update.effective_user.language_code or "en", "ans_membro_expulso"))
            else:
                await safe_answer(query, t(update.effective_user.language_code or "en", "ans_sem_permissão"))
        
        await session.commit()
        await sect_members_list_callback(update, context)


async def sect_kick_inactive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """H-14: Master can kick all members inactive for >= N days.

    Two-step: first click → confirmation list, second click → execute.
    """
    from datetime import datetime, timezone, timedelta
    query = update.callback_query
    if query:
        await safe_answer(query)
    parts = query.data.split("_")
    days = 30
    confirmed = False
    for token in parts[3:]:
        if token == "confirm":
            confirmed = True
        elif token.isdigit():
            days = int(token)
    days = max(7, min(180, days))

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return
        if info["member"].rank != "master":
            await safe_answer(query, t(lang, "sect_kick_inactive_master_only"), show_alert=True)
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(SectMember, Player)
            .join(Player, SectMember.player_id == Player.telegram_id)
            .where(
                SectMember.sect_id == info["sect"].id,
                SectMember.rank != "master",
                Player.last_active_at < cutoff,
            )
            .order_by(Player.last_active_at.asc())
        )
        candidates = (await session.execute(stmt)).all()

        if not candidates:
            await query.message.edit_text(
                t(lang, "sect_kick_inactive_none", days=days),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_members_list")],
                ]),
            )
            return

        if not confirmed:
            lines = [t(lang, "sect_kick_inactive_preview", days=days, count=len(candidates))]
            for m, p in candidates[:20]:
                lines.append(f"• {escape_markdown(get_display_name(p))} — 💤{(datetime.now(timezone.utc) - p.last_active_at).days}d")
            if len(candidates) > 20:
                lines.append(t(lang, "sect_kick_inactive_more", n=len(candidates) - 20))
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "sect_kick_inactive_confirm"),
                                      callback_data=f"sect_kick_inactive_{days}_confirm")],
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_members_list")],
            ])
            await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
            return

        # Execute the kicks.
        kicked = 0
        for m, p in candidates:
            await session.delete(m)
            kicked += 1
        info["sect"].member_count = max(1, info["sect"].member_count - kicked)
        await session.commit()

    await query.message.edit_text(
        t(lang, "sect_kick_inactive_done", count=kicked, days=days),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_members_list")],
        ]),
    )


async def sect_war_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info:
            await query.message.edit_text(
                t(lang, "sect_war_requires_sect"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_start")]])
            )
            return

        now = datetime.now(timezone.utc)
        war_active = await is_war_active(session)
        war_state = await get_war_state(session)

        stmt_terr = select(SectTerritory)
        territories = (await session.execute(stmt_terr)).scalars().all()

        if war_active:
            sect_id_str = str(info["sect"].id)
            is_participating = sect_id_str in war_state.get("participating_sects", [])
            already_attacked = player.telegram_id in war_state.get("attacked_players", [])

            elapsed = 0
            if war_state.get("started_at"):
                elapsed = int((now - war_state["started_at"]).total_seconds())
            remaining_min = max(0, (3600 - elapsed) // 60)

            text = (
                t(lang, "sect_war_active_title") + "\n\n" +
                t(lang, "sect_war_time_remaining", minutes=remaining_min) +
                t(lang, "sect_war_participating", count=len(war_state.get('participating_sects', []))) + "\n\n"
            )

            if already_attacked:
                text += t(lang, "sect_war_already_attacked")

            text += t(lang, "sect_war_territories_in_dispute") + "\n\n"
            buttons = []
            for terr in territories:
                attacks = war_state.get("attacks", {}).get(str(terr.id), {})
                my_sect_bp = attacks.get(sect_id_str, 0)
                total_attackers = sum(1 for v in attacks.values() if v > 0)

                current_owner = "—"
                if terr.sect_id:
                    owner_stmt = select(Sect.name).where(Sect.id == terr.sect_id)
                    owner_name = (await session.execute(owner_stmt)).scalar()
                    current_owner = owner_name or "—"

                text += (
                    f"🏴 *{escape_markdown(terr.name)}*\n"
                    f"{t(lang, 'sect_war_territory_current_owner', owner=current_owner)}\n"
                    f"{t(lang, 'sect_war_territory_bonus', stones=format_number(terr.bonus_stones), cb=int(terr.bonus_cb*100))}\n"
                    f"{t(lang, 'sect_war_territory_attackers', count=total_attackers)}\n"
                    f"{t(lang, 'sect_war_territory_my_bp', bp=format_number(my_sect_bp))}\n\n"
                )

                if is_participating and not already_attacked:
                    buttons.append([InlineKeyboardButton(
                        t(lang, "btn_attack_territory", name=terr.name),
                        callback_data=f"sect_war_attack_{terr.id}"
                    )])

            if not is_participating:
                text += t(lang, "sect_war_not_participating")

            buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])
            kb = InlineKeyboardMarkup(buttons)

        else:
            text = t(lang, "sect_war_inactive_title") + "\n\n"

            weekday = now.weekday()
            if weekday <= 4:
                days_until = 4 - weekday
            else:
                days_until = 4 + (7 - weekday)
            next_war = now.replace(hour=20, minute=0, second=0, microsecond=0) + timedelta(days=days_until)
            if days_until == 0 and now.hour >= 21:
                next_war += timedelta(days=7)
            hours_until = max(0, int((next_war - now).total_seconds() // 3600))

            text += (
                f"{t(lang, 'sect_war_next_war')}\n"
                f"{t(lang, 'sect_war_hours_until', hours=hours_until)}\n\n"
            ) + t(lang, "sect_war_rules")

            if territories:
                text += t(lang, "sect_war_territories_title") + "\n\n"
                for terr in territories:
                    owner = "—"
                    expired = True
                    if terr.sect_id and terr.expires_at and terr.expires_at > now:
                        owner_stmt = select(Sect.name).where(Sect.id == terr.sect_id)
                        owner_name = (await session.execute(owner_stmt)).scalar()
                        owner = owner_name or "—"
                        expired = False
                    elif terr.sect_id:
                        owner = t(lang, "sect_war_territory_expired")

                    expires_text = ""
                    if not expired and terr.expires_at:
                        days_left = max(0, (terr.expires_at - now).days)
                        expires_text = t(lang, "sect_war_territory_expires", days=days_left)

                    text += (
                        f"🏴 *{escape_markdown(terr.name)}*\n"
                        f"{t(lang, 'sect_war_territory_owner', owner=owner)}\n"
                        f"{t(lang, 'sect_war_territory_bonus', stones=format_number(terr.bonus_stones), cb=int(terr.bonus_cb*100))}"
                        f"{expires_text}\n\n"
                    )
            else:
                text += t(lang, "sect_war_no_territories") + "\n"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")]
            ])

        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def sect_war_attack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    territory_id = safe_parse_callback_int(query.data, "sect_war_attack_")
    if territory_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return

        result = await register_war_attack(session, player.telegram_id, territory_id)
        war_ach = []
        if result["success"]:
            info = await get_player_sect_info(session, player.telegram_id)
            if info:
                await log_sect_contribution(session, player.telegram_id, info["sect"].id, "war", result["bp_contributed"])
            from core.achievement_engine import check_achievements
            war_ach = await check_achievements(session, player.telegram_id, "sect_wars", 1)
        await session.commit()

        if result["success"]:
            terr_stmt = select(SectTerritory.name).where(SectTerritory.id == territory_id)
            terr_name = (await session.execute(terr_stmt)).scalar() or "???"

            await safe_answer(query, 
                t(lang, "sect_war_attacked_success", terr_name=terr_name, bp_contributed=format_number(result['bp_contributed'])),
                show_alert=True
            )
            if war_ach:
                from handlers.achievements import notify_achievements
                await notify_achievements(context, player.telegram_id, war_ach)
            await sect_war_info_callback(update, context)
        else:
            lang = player.language or "en"
            error_msg = t(lang, result.get("error_key", "err_player_not_found"), **result.get("error_params", {}))
            await safe_answer(query, error_msg, show_alert=True)


async def sect_leave_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        
        text = t(lang, "sect_leave_confirm")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_sect_leave_yes"), callback_data="sect_leave_execute")],
            [InlineKeyboardButton(t(lang, "btn_sect_leave_no"), callback_data="cmd_seita")]
        ])
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

async def sect_leave_execute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return

        if info["member"].rank == "master" and info["sect"].member_count > 1:
            await safe_answer(query, t(update.effective_user.language_code or "en", "ans_promova_alguém_antes_de"), show_alert=True)
            return

        info["sect"].member_count -= 1
        await session.delete(info["member"])
        if info["sect"].member_count == 0:
            await session.delete(info["sect"])
        
        await session.commit()
        await safe_answer(query, t(lang, "sect_left_success"))
        await seita_menu(update, context)

@safe_handler
@rate_limit(1)
async def loja_seita_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return

        sect = info["sect"]
        member = info["member"]

        learned_stmt = select(PlayerTechnique.technique_id).where(
            PlayerTechnique.player_id == player.telegram_id
        )
        learned_ids = set(
            (await session.execute(learned_stmt)).scalars().all()
        )

        owned_scrolls_stmt = select(PlayerInventory.item_id).where(
            PlayerInventory.player_id == player.telegram_id,
            PlayerInventory.item_type == "technique_scroll",
            PlayerInventory.quantity > 0,
        )
        owned_scroll_ids = set(
            (await session.execute(owned_scrolls_stmt)).scalars().all()
        )

        text = (
            t(lang, "sect_shop_title") + "\n\n" +
            t(lang, "sect_cp_balance", amount=format_number(member.contribution_points)) + "\n\n" +
            t(lang, "sect_shop_items_header")
        )

        shop_items = [
            {"id": "qi_pill", "name": t(lang, "sect_shop_item_qi"), "cost": 50, "req_lvl": 1},
            {"id": "cb_pill", "name": t(lang, "sect_shop_item_cb"), "cost": 200, "req_lvl": 5},
            {"id": "beast_trap", "name": "🪤 Beast Trap", "cost": 100, "req_lvl": 1},
            {"id": "blueprint", "name": t(lang, "sect_shop_item_blueprint"), "cost": 1000, "req_lvl": 10},
        ]

        buttons = []
        for item in shop_items:
            locked = sect.training_lvl < item["req_lvl"]
            lock_text = f" ({t(lang, 'sect_shop_req_lvl', lvl=item['req_lvl'])})" if locked else ""
            text += f"• *{item['name']}*\n└ 💰 {item['cost']} CP{lock_text}\n\n"

            if not locked:
                buttons.append([InlineKeyboardButton(t(lang, "sect_shop_buy_item", name=item['name']), callback_data=f"sect_buy_{item['id']}")])

        text += t(lang, "sect_shop_scrolls_header")
        for tech_id, scroll_info in SCROLL_SHOP_ITEMS.items():
            lib_locked = sect.library_lvl < scroll_info["req_library"]
            already_learned = tech_id in learned_ids
            already_has_scroll = tech_id in owned_scroll_ids

            status = ""
            if already_learned:
                status = t(lang, "sect_shop_learned")
            elif already_has_scroll:
                status = t(lang, "sect_shop_owned")

            lock_text = t(lang, "sect_shop_library_req", level=scroll_info['req_library']) if lib_locked else ""
            text += f"• *{scroll_info['name']}*{status}\n└ 💰 {scroll_info['cost']} CP{lock_text}\n\n"

            if not lib_locked and not already_learned and not already_has_scroll:
                buttons.append([InlineKeyboardButton(
                    t(lang, "sect_shop_buy_scroll", name=scroll_info['name']),
                    callback_data=f"sect_buy_scroll_{tech_id}"
                )])

        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])
        kb = InlineKeyboardMarkup(buttons)

        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def sect_buy_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    raw_id = query.data.replace("sect_buy_", "")

    # Cache the telegram_id BEFORE the session opens so nothing in the failure
    # paths triggers a lazy-load on an expired Player (previous bug: `rollback()`
    # expired the player, and re-reading player.telegram_id after rollback hit
    # a closed pool connection).
    player_id = update.effective_user.id

    # Output flags — decided inside the session, acted on after it closes.
    # Keeps the outer session short-lived (avoids idle_in_transaction timeout
    # we saw when `loja_seita_command` was invoked while still inside it).
    alert_msg: str | None = None
    should_refresh_shop = False

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player_id)
        if not info:
            return

        sect = info["sect"]
        member = info["member"]

        if raw_id.startswith("scroll_"):
            tech_id = int(raw_id.replace("scroll_", ""))
            scroll_info = SCROLL_SHOP_ITEMS.get(tech_id)
            if not scroll_info:
                return

            if sect.library_lvl < scroll_info["req_library"]:
                alert_msg = t(lang, "ans_biblioteca_da_seita_com")
            elif member.contribution_points < scroll_info["cost"]:
                alert_msg = t(lang, "sect_shop_error_cp")
            else:
                already_learned = (await session.execute(
                    select(PlayerTechnique).where(
                        PlayerTechnique.player_id == player_id,
                        PlayerTechnique.technique_id == tech_id,
                    )
                )).scalar_one_or_none()
                if already_learned:
                    alert_msg = t(lang, "ans_já_aprendeste_esta_técnica")
                else:
                    member.contribution_points -= scroll_info["cost"]
                    added = await add_item_to_inventory(session, player_id, "technique_scroll", tech_id)
                    if not added:
                        await session.rollback()
                        from core.utils import _get_or_create_ring, _count_used_slots
                        ring = await _get_or_create_ring(session, player_id)
                        used = await _count_used_slots(session, player_id)
                        alert_msg = t(lang, "inv_full", used=used, max=ring.max_slots)
                    else:
                        await session.commit()
                        alert_msg = t(lang, "sect_scroll_bought", name=scroll_info['name'])
                        should_refresh_shop = True
        else:
            items_db = {
                "qi_pill": {"cost": 50, "req_lvl": 1, "type": "pill", "id": 1},
                "cb_pill": {"cost": 200, "req_lvl": 5, "type": "pill", "id": 2},
                "beast_trap": {"cost": 100, "req_lvl": 1, "type": "beast_trap", "id": 0},
                "blueprint": {"cost": 1000, "req_lvl": 10, "type": "blueprint", "id": 1},
            }

            item = items_db.get(raw_id)
            if not item:
                return

            if sect.training_lvl < item["req_lvl"]:
                alert_msg = t(lang, "sect_shop_error_lvl")
            elif member.contribution_points < item["cost"]:
                alert_msg = t(lang, "sect_shop_error_cp")
            else:
                member.contribution_points -= item["cost"]
                added = await add_item_to_inventory(session, player_id, item["type"], item["id"])
                if not added:
                    await session.rollback()
                    from core.utils import _get_or_create_ring, _count_used_slots
                    ring = await _get_or_create_ring(session, player_id)
                    used = await _count_used_slots(session, player_id)
                    alert_msg = t(lang, "inv_full", used=used, max=ring.max_slots)
                else:
                    await session.commit()
                    alert_msg = t(lang, "sect_shop_success", item=raw_id.replace("_", " ").capitalize())
                    should_refresh_shop = True

    # Session is fully closed here — safe to send the alert and re-render the
    # shop without keeping a transaction open.
    if alert_msg:
        await safe_answer(query, alert_msg, show_alert=True)
    if should_refresh_shop:
        await loja_seita_command(update, context)

@safe_handler
@rate_limit(1)
async def ranking_sects_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        
        stmt = (
            select(Sect.name, func.sum(Player.battle_power).label("total_bp"), func.count(SectMember.player_id).label("members"))
            .join(SectMember, Sect.id == SectMember.sect_id)
            .join(Player, SectMember.player_id == Player.telegram_id)
            .group_by(Sect.id, Sect.name)
            .order_by(desc("total_bp")).limit(10)
        )
        results = (await session.execute(stmt)).all()
        if not results: return

        text = t(lang, "sect_ranking_title") + "\n\n"
        for i, (name, bp, members) in enumerate(results, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += t(lang, "sect_ranking_row", medal=medal, name=name, bp=format_number(bp), members=members) + "\n"
        await update.message.reply_text(text, parse_mode="Markdown")

@safe_handler
@rate_limit(1)
async def sairseita_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return
        
        if info["member"].rank == "master" and info["sect"].member_count > 1:
            await update.message.reply_text(t(lang, "sect_warn_promote_before_leave"))
            return
            
        info["sect"].member_count -= 1
        await session.delete(info["member"])
        if info["sect"].member_count == 0: await session.delete(info["sect"])
        await session.commit()
        await update.message.reply_text(t(lang, "sect_left_success"))

@safe_handler
@rate_limit(1)
async def criarseita_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    await seita_menu(update, context)

@safe_handler
@rate_limit(1)
async def doarseita_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    await sect_vault_menu(update, context)

@safe_handler
@rate_limit(1)
async def entrarseita_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    await update.message.reply_text(t(lang, "in_development"))
@safe_handler
@rate_limit(1)
async def promotemembro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    await update.message.reply_text(t(lang, "in_development"))
@safe_handler
@rate_limit(1)
async def expulmembro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    await update.message.reply_text(t(lang, "in_development"))


async def sect_bulletin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return

        sect = info["sect"]
        bulletin = escape_markdown(sect.bulletin) if sect.bulletin else t(lang, "sect_bulletin_empty")

        text = (
            t(lang, "sect_bulletin_title", name=escape_markdown(sect.name)) + "\n\n"
            f"{bulletin}\n\n"
            + t(lang, "sect_bulletin_footer")
        )

        buttons = []
        if info["member"].rank in ["master", "elder"]:
            buttons.append([InlineKeyboardButton(t(lang, "btn_sect_publish"), callback_data="sect_bulletin_write")])
        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])

        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def sect_bulletin_write_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank not in ["master", "elder"]:
            await safe_answer(query, t(update.effective_user.language_code or "en", "ans_sem_permissão"), show_alert=True)
            return

        context.user_data["awaiting_sect_bulletin"] = True
        await query.message.edit_text(
            t(lang, "sect_bulletin_prompt"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_bulletin")]])
        )


async def process_sect_bulletin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    text = update.message.text.strip()[:500]
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank not in ["master", "elder"]:
            await update.message.reply_text(t(player.language, "sect_error_no_permission"))
            return

        rank_title = t(lang, "sect_rank_master") if info["member"].rank == "master" else t(lang, "sect_rank_elder")
        now = datetime.now(timezone.utc)
        formatted = f"📢 *{rank_title} {escape_markdown(get_display_name(player))}*\n_{now.strftime('%d/%m %H:%M')} UTC_\n\n{escape_markdown(text)}"
        info["sect"].bulletin = formatted

        # M-9: DM all sect members about the new edict (filter by pref).
        from database.models import SectMember
        from core.notification_prefs import filter_recipients
        sect_id = info["sect"].id
        member_ids_rows = (await session.execute(
            select(SectMember.player_id).where(SectMember.sect_id == sect_id)
        )).all()
        member_ids = [pid for (pid,) in member_ids_rows if pid != player.telegram_id]
        recipients: set[int] = set()
        if member_ids:
            recipients = await filter_recipients(session, member_ids, "sect_edict")

        # Per-recipient language for the DM header.
        recipient_langs: dict[int, str] = {}
        if recipients:
            lang_rows = (await session.execute(
                select(Player.telegram_id, Player.language).where(Player.telegram_id.in_(recipients))
            )).all()
            recipient_langs = {pid: (lang_val or "en") for pid, lang_val in lang_rows}

        sect_name = info["sect"].name
        await session.commit()
        context.user_data.pop("awaiting_sect_bulletin", None)

        # Schedule DMs in background — never block the master's reply.
        if recipients:
            import asyncio as _aio
            from core.announcement_engine import _bot as _ann_bot
            from core.utils import normalize_lang as _norm_lang

            async def _send_edict_dms():
                if _ann_bot is None:
                    return
                for rid in recipients:
                    try:
                        rlang = _norm_lang(recipient_langs.get(rid, "en"))
                        msg = t(rlang, "sect_edict_dm", sect=escape_markdown(sect_name)) + "\n\n" + formatted
                        await _ann_bot.send_message(chat_id=rid, text=msg, parse_mode="Markdown")
                    except Exception as e:
                        logger.warning("sect edict DM to %s failed: %s", rid, e)
                    await _aio.sleep(0.05)

            _aio.create_task(_send_edict_dms())

        await update.message.reply_text(
            t(lang, "sect_bulletin_success", formatted=formatted),
            parse_mode="Markdown"
        )


async def sect_group_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info: return

        sect = info["sect"]
        buttons = []

        if sect.group_link:
            text = (
                t(lang, "sect_group_info", name=escape_markdown(sect.name)) + "\n\n" +
                t(lang, "sect_group_join_desc")
            )
            buttons.append([InlineKeyboardButton(t(lang, "btn_sect_join_group"), url=sect.group_link)])
        else:
            text = (
                t(lang, "sect_group_info", name=escape_markdown(sect.name)) + "\n\n" +
                t(lang, "sect_group_no_link")
            )

        if info["member"].rank == "master":
            buttons.append([InlineKeyboardButton(t(lang, "btn_sect_set_link"), callback_data="sect_group_link_set")])
        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])

        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def sect_group_link_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank != "master":
            await safe_answer(query, t(update.effective_user.language_code or "en", "ans_apenas_o_maestro"), show_alert=True)
            return

        context.user_data["awaiting_sect_group_link"] = True
        await query.message.edit_text(
            t(lang, "sect_group_link_prompt"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_group_link")]])
        )


async def process_sect_group_link_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', "en"))
    link = update.message.text.strip()
    if not link.startswith("https://t.me/"):
        await update.message.reply_text(t(lang, "sect_invalid_link"), parse_mode="Markdown")
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank != "master":
            await update.message.reply_text(t(player.language, "sect_error_no_permission"))
            return

        info["sect"].group_link = link
        await session.commit()
        context.user_data.pop("awaiting_sect_group_link", None)
        await update.message.reply_text(
            t(lang, "sect_group_link_success", link=link),
        )


@safe_handler
@rate_limit(1)
async def admin_startwar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_USERS
    if update.effective_user.id not in ADMIN_USERS:
        return
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return

        from core.sect_engine import start_sect_war
        result = await start_sect_war(session)
        await session.commit()

    if not result.get("started"):
        await update.message.reply_text(t(lang, "admin_war_not_started", reason=result.get('reason', 'unknown')))
        return

    territories = result.get("territories", [])
    terr_text = "\n".join(f"  🏴 *{escape_markdown(t_['name'])}*" for t_ in territories)
    sect_count = result.get("sect_count", 0)

    async with get_session_factory()() as session:
        all_ids = (await session.execute(select(Player.telegram_id, Player.language))).all()

    for pid, p_lang in all_ids:
        member_lang = normalize_lang(p_lang)
        msg = t(member_lang, "global_sect_war_start", sect_count=sect_count, terr_text=terr_text)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(member_lang, "btn_sect_war"), callback_data="sect_war_info")]
        ])
        try:
            await context.bot.send_message(chat_id=pid, text=msg, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            pass

    await update.message.reply_text(t(lang, "admin_war_started_ok", sect_count=sect_count, player_count=len(all_ids)))


@safe_handler
@rate_limit(1)
async def admin_resolvewar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_USERS
    if update.effective_user.id not in ADMIN_USERS:
        return
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return

        from core.sect_engine import resolve_sect_war
        result = await resolve_sect_war(session)
        await session.commit()

    if not result.get("resolved"):
        await update.message.reply_text(t(lang, "admin_war_not_resolved", reason=result.get('reason', 'unknown')))
        return

    results = result.get("results", [])
    async with get_session_factory()() as session:
        all_ids = (await session.execute(select(Player.telegram_id, Player.language))).all()

    for pid, p_lang in all_ids:
        member_lang = normalize_lang(p_lang)
        lines = [t(member_lang, "global_sect_war_results_title")]
        for r in results:
            if r.get("no_contestants"):
                lines.append(t(member_lang, "global_sect_war_territory_free", territory=r['territory_name']))
            else:
                lines.append(
                    t(member_lang, "global_sect_war_territory_won", territory=r['territory_name'], winner=r['winner'], bp=format_number(r.get('winner_bp', 0)))
                )
        lines.append(t(member_lang, "global_sect_war_results_footer"))
        msg = "\n".join(lines)

        try:
            await context.bot.send_message(chat_id=pid, text=msg, parse_mode="Markdown")
        except Exception as e:
            pass

    await update.message.reply_text(t(lang, "admin_war_resolved_ok", player_count=len(all_ids)))


# ── Contribution visibility handlers ──────────────────────────────────────

CONTRIB_TYPE_EMOJI = {"donation": "💰", "quest": "📜", "war": "⚔️"}

async def sect_contributions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View individual member contributions (Master/Elder only)."""
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query:
        await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info:
            return

        if info["member"].rank not in ("master", "elder"):
            await safe_answer(query, t(lang, "sect_error_no_permission"), show_alert=True)
            return

        sect = info["sect"]

        # Fetch all members with their total logged contributions
        stmt = (
            select(
                Player.telegram_id,
                Player.dao_name,
                Player.display_name,
                Player.username,
                func.coalesce(func.sum(SectContributionLog.amount), 0).label("total"),
            )
            .join(SectMember, SectMember.player_id == Player.telegram_id)
            .outerjoin(
                SectContributionLog,
                (SectContributionLog.player_id == Player.telegram_id)
                & (SectContributionLog.sect_id == sect.id),
            )
            .where(SectMember.sect_id == sect.id)
            .group_by(Player.telegram_id, Player.dao_name, Player.display_name, Player.username)
            .order_by(desc("total"))
        )
        rows = (await session.execute(stmt)).all()

        text = t(lang, "sect_contrib_title", name=escape_markdown(sect.name)) + "\n\n"
        for i, (tid, dao_name, display_name, uname, total) in enumerate(rows, 1):
            name = dao_name or display_name or uname or str(tid)
            text += f"{i}. `{escape_markdown(name)}` — {format_number(total)}\n"

        if not rows:
            text += t(lang, "sect_contrib_empty") + "\n"

        # Detail button per member (show latest 10 entries) — use pagination callback
        buttons = []
        for tid, dao_name, display_name, uname, total in rows[:10]:
            name = dao_name or display_name or uname or str(tid)
            buttons.append([InlineKeyboardButton(
                f"📋 {name}",
                callback_data=f"sect_contrib_detail_{tid}",
            )])
        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])
        kb = InlineKeyboardMarkup(buttons)

        try:
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            if "Message is not modified" not in str(e):
                raise


async def sect_contrib_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the last 15 contribution entries for a specific member (Master/Elder)."""
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query:
        await safe_answer(query)

    target_id = safe_parse_callback_int(query.data, "sect_contrib_detail_")
    if target_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank not in ("master", "elder"):
            await safe_answer(query, t(lang, "sect_error_no_permission"), show_alert=True)
            return

        sect = info["sect"]

        # Fetch target name
        target_player = (await session.execute(
            select(Player).where(Player.telegram_id == target_id)
        )).scalar_one_or_none()
        target_name = (target_player.dao_name or get_display_name(target_player)) if target_player else str(target_id)

        stmt = (
            select(SectContributionLog)
            .where(SectContributionLog.player_id == target_id, SectContributionLog.sect_id == sect.id)
            .order_by(SectContributionLog.created_at.desc())
            .limit(15)
        )
        logs = (await session.execute(stmt)).scalars().all()

        text = t(lang, "sect_contrib_detail_title", name=escape_markdown(target_name)) + "\n\n"
        if not logs:
            text += t(lang, "sect_contrib_empty") + "\n"
        else:
            for entry in logs:
                emoji = CONTRIB_TYPE_EMOJI.get(entry.type, "❓")
                date_str = entry.created_at.strftime("%m/%d %H:%M")
                text += f"{emoji} `{entry.type}` — {format_number(entry.amount)}  _{date_str}_\n"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_contributions")]
        ])

        try:
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            if "Message is not modified" not in str(e):
                raise


# ─────────────────────────────────────────────────────────────────────────────
# v14.2 D-3 — discoverability buttons in seita_menu.
# Master-only entry points to /decreto_supremo and /passar_tocha so leaders
# don't need to memorise slash commands.
# ─────────────────────────────────────────────────────────────────────────────

async def sect_decree_init_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master taps '📜 Emitir Decreto' → text wizard prompt (mirrors bulletin)."""
    from core.sect_engine import DECREE_MAX_LEN, DECREE_DURATION_HOURS, get_active_decree

    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank != "master":
            await safe_answer(query, t(lang, "decree_master_only"), show_alert=True)
            return

        active = get_active_decree(info["sect"])
        active_block = ""
        if active:
            hrs = max(1, int((active["expires_at"] - datetime.now(timezone.utc)).total_seconds() // 3600))
            active_block = "\n\n" + t(lang, "decree_init_active_hint",
                                       hours=hrs,
                                       text=escape_markdown(active["text"]))

        context.user_data["awaiting_sect_decree"] = True
        await query.message.edit_text(
            t(lang, "decree_init_prompt",
              max=DECREE_MAX_LEN, hours=DECREE_DURATION_HOURS) + active_block,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")]
            ]),
        )


async def process_sect_decree_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master sent the decree text via DM → reuse the same engine path the
    /decreto_supremo command uses, including the background DM broadcast."""
    from core.sect_engine import set_sect_decree, DECREE_DURATION_HOURS, DECREE_MAX_LEN

    if not update.message or not update.message.text:
        return
    raw = update.message.text.strip()

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        result = await set_sect_decree(session, player.telegram_id, raw)
        if not result["ok"]:
            reason = result.get("reason", "unknown")
            if reason == "not_in_sect":
                await update.message.reply_text(t(lang, "sect_no_sect_short"))
            elif reason == "master_only":
                await update.message.reply_text(t(lang, "decree_master_only"))
            elif reason == "empty_text":
                await update.message.reply_text(
                    t(lang, "decree_usage", max=DECREE_MAX_LEN), parse_mode="Markdown",
                )
            elif reason == "text_too_long":
                await update.message.reply_text(
                    t(lang, "decree_too_long", max=result.get("max", DECREE_MAX_LEN)),
                )
            else:
                await update.message.reply_text(t(lang, "decree_failed"))
            context.user_data.pop("awaiting_sect_decree", None)
            return

        info = await get_player_sect_info(session, player.telegram_id)
        sect_id = info["sect"].id
        sect_name = info["sect"].name
        decree_text = result["text"]

        from core.notification_prefs import filter_recipients
        member_ids_rows = (await session.execute(
            select(SectMember.player_id).where(SectMember.sect_id == sect_id)
        )).all()
        member_ids = [pid for (pid,) in member_ids_rows if pid != player.telegram_id]
        recipients: set[int] = set()
        if member_ids:
            recipients = await filter_recipients(session, member_ids, "sect_edict")

        recipient_langs: dict[int, str] = {}
        if recipients:
            lang_rows = (await session.execute(
                select(Player.telegram_id, Player.language).where(Player.telegram_id.in_(recipients))
            )).all()
            recipient_langs = {pid: (l_val or "en") for pid, l_val in lang_rows}

        master_name = player.dao_name or get_display_name(player)
        await session.commit()
        context.user_data.pop("awaiting_sect_decree", None)

    await update.message.reply_text(
        t(lang, "decree_success", hours=DECREE_DURATION_HOURS, text=escape_markdown(decree_text)),
        parse_mode="Markdown",
    )

    if recipients:
        import asyncio as _aio
        from core.announcement_engine import _bot as _ann_bot

        async def _send_decree_dms():
            if _ann_bot is None:
                return
            for rid in recipients:
                try:
                    rlang = normalize_lang(recipient_langs.get(rid, "en"))
                    msg = t(rlang, "decree_dm",
                            sect=escape_markdown(sect_name),
                            master=escape_markdown(master_name),
                            text=escape_markdown(decree_text),
                            hours=DECREE_DURATION_HOURS)
                    await _ann_bot.send_message(chat_id=rid, text=msg, parse_mode="Markdown")
                except Exception as e:
                    logger.warning("decree DM to %s failed: %s", rid, e)
                await _aio.sleep(0.05)

        _aio.create_task(_send_decree_dms())


async def sect_torch_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master taps '🔥 Passar a Tocha' → list of Elders with cooldown info."""
    from core.sect_engine import torch_cooldown_remaining, _torch_pending_is_fresh, TORCH_COOLDOWN_DAYS

    query = update.callback_query
    if query: await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank != "master":
            await safe_answer(query, t(lang, "torch_master_only"), show_alert=True)
            return

        sect = info["sect"]

        # Render header — cooldown / pending state surface explicitly.
        cooldown = torch_cooldown_remaining(sect)
        is_pending = sect.pending_torch_to_id and _torch_pending_is_fresh(sect)

        text_lines = [t(lang, "torch_menu_title", sect=escape_markdown(sect.name))]
        text_lines.append("")

        if cooldown is not None:
            days_left = max(1, int(cooldown.total_seconds() // 86400))
            text_lines.append(t(lang, "torch_cooldown_active",
                                cooldown=TORCH_COOLDOWN_DAYS, days=days_left))
            text_lines.append("")

        if is_pending:
            pending_player = (await session.execute(
                select(Player).where(Player.telegram_id == sect.pending_torch_to_id)
            )).scalar_one_or_none()
            pname = (pending_player.dao_name or get_display_name(pending_player)) if pending_player else "—"
            text_lines.append(t(lang, "torch_menu_pending", target=escape_markdown(pname)))
            text_lines.append("")

        # Fetch elders only.
        elder_rows = (await session.execute(
            select(SectMember, Player)
            .join(Player, SectMember.player_id == Player.telegram_id)
            .where(SectMember.sect_id == sect.id, SectMember.rank == "elder")
            .order_by(Player.dao_name.asc())
        )).all()

        buttons = []
        if not elder_rows:
            text_lines.append(t(lang, "torch_no_elders"))
        elif cooldown is None and not is_pending:
            text_lines.append(t(lang, "torch_menu_pick"))
            for m, p in elder_rows:
                pname = p.dao_name or get_display_name(p)
                buttons.append([InlineKeyboardButton(
                    f"🎖️ {pname}",
                    callback_data=f"sect_torch_pick_{p.telegram_id}",
                )])

        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])
        await query.message.edit_text(
            "\n".join(text_lines), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )


async def sect_torch_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master picked an Elder → confirmation screen before firing the ritual."""
    query = update.callback_query
    target_id = safe_parse_callback_int(query.data, "sect_torch_pick_")
    if target_id is None:
        return
    if query: await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info or info["member"].rank != "master":
            await safe_answer(query, t(lang, "torch_master_only"), show_alert=True)
            return

        # Validate target still belongs and is elder.
        row = (await session.execute(
            select(SectMember, Player)
            .join(Player, SectMember.player_id == Player.telegram_id)
            .where(SectMember.sect_id == info["sect"].id,
                   SectMember.player_id == target_id)
        )).first()
        if not row:
            await safe_answer(query, t(lang, "torch_target_not_in_sect"), show_alert=True)
            return
        target_member, target_player = row
        if target_member.rank != "elder":
            await safe_answer(query, t(lang, "torch_target_not_elder"), show_alert=True)
            return

        target_name = target_player.dao_name or get_display_name(target_player)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            t(lang, "btn_torch_fire"),
            callback_data=f"sect_torch_fire_{target_id}",
        )],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_torch_menu")],
    ])
    await query.message.edit_text(
        t(lang, "torch_confirm_screen", target=escape_markdown(target_name)),
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def sect_torch_fire_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Master confirmed → call initiate_torch_pass + DM the Elder.
    Reuses the same engine path the /passar_tocha command uses."""
    from core.sect_engine import initiate_torch_pass, TORCH_COOLDOWN_DAYS

    query = update.callback_query
    target_id = safe_parse_callback_int(query.data, "sect_torch_fire_")
    if target_id is None:
        return
    if query: await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player: return
        lang = player.language or "en"

        # We need the dao_name for initiate_torch_pass; look it up by id.
        target_player = (await session.execute(
            select(Player).where(Player.telegram_id == target_id)
        )).scalar_one_or_none()
        if not target_player or not target_player.dao_name:
            await safe_answer(query, t(lang, "torch_target_not_in_sect"), show_alert=True)
            return

        result = await initiate_torch_pass(session, player.telegram_id, target_player.dao_name)
        if not result["ok"]:
            reason = result.get("reason", "unknown")
            msg_map = {
                "not_in_sect": t(lang, "sect_no_sect_short"),
                "master_only": t(lang, "torch_master_only"),
                "cooldown": t(lang, "torch_cooldown",
                              days=result.get("days_remaining", TORCH_COOLDOWN_DAYS)),
                "already_pending": t(lang, "torch_already_pending"),
                "target_not_in_sect": t(lang, "torch_target_not_in_sect"),
                "cannot_target_self": t(lang, "torch_cannot_target_self"),
                "target_not_elder": t(lang, "torch_target_not_elder"),
            }
            await safe_answer(query, msg_map.get(reason, t(lang, "torch_failed")), show_alert=True)
            return

        target_name = result["target_name"]
        sect_name = result["sect_name"]
        master_name = player.dao_name or get_display_name(player)

        target_lang_row = (await session.execute(
            select(Player.language).where(Player.telegram_id == target_id)
        )).scalar_one_or_none()
        target_lang = normalize_lang(target_lang_row or "en")

        await session.commit()

    # DM the Elder with consent buttons.
    dm_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(target_lang, "btn_torch_accept"), callback_data="sect_torch_accept"),
            InlineKeyboardButton(t(target_lang, "btn_torch_refuse"), callback_data="sect_torch_refuse"),
        ]
    ])
    dm_text = t(target_lang, "torch_dm_offer",
                master=escape_markdown(master_name),
                sect=escape_markdown(sect_name))

    sent_ok = True
    try:
        await context.bot.send_message(
            chat_id=target_id, text=dm_text,
            parse_mode="Markdown", reply_markup=dm_kb,
        )
    except Exception as e:
        sent_ok = False
        logger.warning("torch DM to %s failed: %s", target_id, e)

    if sent_ok:
        await query.message.edit_text(
            t(lang, "torch_initiated_ok", target=escape_markdown(target_name)),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")]
            ]),
        )
    else:
        # DM blocked → roll back the pending state so the master can retry.
        async with get_session_factory()() as session:
            player2 = await _ensure_player(update, session)
            info2 = await get_player_sect_info(session, player2.telegram_id) if player2 else None
            if info2 and info2["sect"].pending_torch_to_id == target_id:
                info2["sect"].pending_torch_to_id = None
                info2["sect"].pending_torch_at = None
                await session.commit()
        await query.message.edit_text(
            t(lang, "torch_dm_blocked", target=escape_markdown(target_name)),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="sect_torch_menu")]
            ]),
        )


# ─────────────────────────────────────────────────────────────────────────────
# v14.2 D-3a — /decreto_supremo (Sect Edict, master only, 24h sect-wide).
# ─────────────────────────────────────────────────────────────────────────────

@safe_handler
@rate_limit(2)
async def decreto_supremo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/decreto_supremo <texto>` — master sets a 24h sect-wide edict.

    Mirrors the bulletin DM mechanic (handlers/sect.py:1228-1268) for parity:
    every member receives the decree in their language preference.
    """
    from core.sect_engine import set_sect_decree, DECREE_MAX_LEN, DECREE_DURATION_HOURS

    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    raw = " ".join(context.args).strip() if context.args else ""

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        if not raw:
            await update.message.reply_text(
                t(lang, "decree_usage", max=DECREE_MAX_LEN),
                parse_mode="Markdown",
            )
            return

        result = await set_sect_decree(session, player.telegram_id, raw)
        if not result["ok"]:
            reason = result.get("reason", "unknown")
            if reason == "not_in_sect":
                await update.message.reply_text(t(lang, "sect_no_sect_short"))
            elif reason == "master_only":
                await update.message.reply_text(t(lang, "decree_master_only"))
            elif reason == "empty_text":
                await update.message.reply_text(
                    t(lang, "decree_usage", max=DECREE_MAX_LEN),
                    parse_mode="Markdown",
                )
            elif reason == "text_too_long":
                await update.message.reply_text(
                    t(lang, "decree_too_long", max=result.get("max", DECREE_MAX_LEN)),
                )
            else:
                await update.message.reply_text(t(lang, "decree_failed"))
            return

        # Collect recipients + langs while inside the session.
        info = await get_player_sect_info(session, player.telegram_id)
        sect = info["sect"]
        sect_id = sect.id
        sect_name = sect.name
        decree_text = result["text"]

        from core.notification_prefs import filter_recipients
        member_ids_rows = (await session.execute(
            select(SectMember.player_id).where(SectMember.sect_id == sect_id)
        )).all()
        member_ids = [pid for (pid,) in member_ids_rows if pid != player.telegram_id]
        recipients: set[int] = set()
        if member_ids:
            recipients = await filter_recipients(session, member_ids, "sect_edict")

        recipient_langs: dict[int, str] = {}
        if recipients:
            lang_rows = (await session.execute(
                select(Player.telegram_id, Player.language).where(Player.telegram_id.in_(recipients))
            )).all()
            recipient_langs = {pid: (l_val or "en") for pid, l_val in lang_rows}

        master_name = player.dao_name or get_display_name(player)
        await session.commit()

    await update.message.reply_text(
        t(lang, "decree_success", hours=DECREE_DURATION_HOURS, text=escape_markdown(decree_text)),
        parse_mode="Markdown",
    )

    if recipients:
        import asyncio as _aio
        from core.announcement_engine import _bot as _ann_bot

        async def _send_decree_dms():
            if _ann_bot is None:
                return
            for rid in recipients:
                try:
                    rlang = normalize_lang(recipient_langs.get(rid, "en"))
                    msg = t(rlang, "decree_dm",
                            sect=escape_markdown(sect_name),
                            master=escape_markdown(master_name),
                            text=escape_markdown(decree_text),
                            hours=DECREE_DURATION_HOURS)
                    await _ann_bot.send_message(chat_id=rid, text=msg, parse_mode="Markdown")
                except Exception as e:
                    logger.warning("decree DM to %s failed: %s", rid, e)
                await _aio.sleep(0.05)

        _aio.create_task(_send_decree_dms())


# ─────────────────────────────────────────────────────────────────────────────
# v14.2 D-3b — /passar_tocha ritual (master → elder, consent flow, 30d cooldown).
# ─────────────────────────────────────────────────────────────────────────────

@safe_handler
@rate_limit(2)
async def passar_tocha_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """`/passar_tocha @dao_name` — Master initiates torch ritual.

    The target Elder receives a DM with Aceitar/Recusar buttons. On accept:
    • outgoing master → elder (preserves voice in council)
    • target elder → master (sect.master_id updated)
    • last_torch_passed_at = now (30-day cooldown)
    """
    from core.sect_engine import initiate_torch_pass, TORCH_COOLDOWN_DAYS

    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    if not context.args:
        await update.message.reply_text(t(lang, "torch_usage"), parse_mode="Markdown")
        return

    target_dao = " ".join(context.args).strip().lstrip("@")

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        result = await initiate_torch_pass(session, player.telegram_id, target_dao)
        if not result["ok"]:
            reason = result.get("reason", "unknown")
            msg_map = {
                "not_in_sect": t(lang, "sect_no_sect_short"),
                "master_only": t(lang, "torch_master_only"),
                "cooldown": t(lang, "torch_cooldown",
                              days=result.get("days_remaining", TORCH_COOLDOWN_DAYS)),
                "already_pending": t(lang, "torch_already_pending"),
                "target_not_in_sect": t(lang, "torch_target_not_in_sect"),
                "cannot_target_self": t(lang, "torch_cannot_target_self"),
                "target_not_elder": t(lang, "torch_target_not_elder"),
            }
            await update.message.reply_text(msg_map.get(reason, t(lang, "torch_failed")))
            return

        target_id = result["target_id"]
        target_name = result["target_name"]
        sect_name = result["sect_name"]
        master_name = player.dao_name or get_display_name(player)

        # Lookup target language for DM
        target_lang_row = (await session.execute(
            select(Player.language).where(Player.telegram_id == target_id)
        )).scalar_one_or_none()
        target_lang = normalize_lang(target_lang_row or "en")

        await session.commit()

    # DM the target Elder with consent buttons.
    dm_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(target_lang, "btn_torch_accept"), callback_data="sect_torch_accept"),
            InlineKeyboardButton(t(target_lang, "btn_torch_refuse"), callback_data="sect_torch_refuse"),
        ]
    ])
    dm_text = t(target_lang, "torch_dm_offer",
                master=escape_markdown(master_name),
                sect=escape_markdown(sect_name))

    sent_ok = True
    try:
        await context.bot.send_message(
            chat_id=target_id, text=dm_text,
            parse_mode="Markdown", reply_markup=dm_kb,
        )
    except Exception as e:
        sent_ok = False
        logger.warning("torch DM to %s failed: %s", target_id, e)

    if sent_ok:
        await update.message.reply_text(
            t(lang, "torch_initiated_ok", target=escape_markdown(target_name)),
            parse_mode="Markdown",
        )
    else:
        # DM blocked → roll back the pending state so master can retry later.
        async with get_session_factory()() as session:
            player2 = await _ensure_player(update, session)
            info2 = await get_player_sect_info(session, player2.telegram_id) if player2 else None
            if info2 and info2["sect"].pending_torch_to_id == target_id:
                info2["sect"].pending_torch_to_id = None
                info2["sect"].pending_torch_at = None
                await session.commit()
        await update.message.reply_text(
            t(lang, "torch_dm_blocked", target=escape_markdown(target_name)),
            parse_mode="Markdown",
        )


async def sect_torch_accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elder taps Aceitar — promote target to master, demote outgoing master to elder."""
    from core.sect_engine import accept_torch_pass

    query = update.callback_query
    if query: await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        result = await accept_torch_pass(session, player.telegram_id)
        if not result["ok"]:
            reason = result.get("reason", "unknown")
            await session.rollback()
            msg_map = {
                "not_in_sect": t(lang, "sect_no_sect_short"),
                "no_pending_for_you": t(lang, "torch_no_pending"),
                "expired": t(lang, "torch_expired"),
                "race_master_changed": t(lang, "torch_failed"),
                "members_missing": t(lang, "torch_failed"),
            }
            try:
                await query.edit_message_text(
                    msg_map.get(reason, t(lang, "torch_failed")),
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            return

        outgoing_id = result["outgoing_master_id"]
        sect_name = result["sect_name"]
        new_master_name = player.dao_name or get_display_name(player)

        # Outgoing master language for DM
        outgoing_lang_row = (await session.execute(
            select(Player.language).where(Player.telegram_id == outgoing_id)
        )).scalar_one_or_none()
        outgoing_lang = normalize_lang(outgoing_lang_row or "en")

        await session.commit()

    # Confirm to the new master in the original DM.
    try:
        await query.edit_message_text(
            t(lang, "torch_accepted_self", sect=escape_markdown(sect_name)),
            parse_mode="Markdown",
        )
    except Exception:
        pass

    # DM outgoing master.
    try:
        await context.bot.send_message(
            chat_id=outgoing_id,
            text=t(outgoing_lang, "torch_accepted_outgoing",
                   sect=escape_markdown(sect_name),
                   new_master=escape_markdown(new_master_name)),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("torch accept DM to outgoing %s failed: %s", outgoing_id, e)


async def sect_torch_refuse_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elder taps Recusar — clear pending state, master may retry with another elder."""
    from core.sect_engine import refuse_torch_pass

    query = update.callback_query
    if query: await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        result = await refuse_torch_pass(session, player.telegram_id)
        if not result["ok"]:
            reason = result.get("reason", "unknown")
            await session.rollback()
            msg_map = {
                "not_in_sect": t(lang, "sect_no_sect_short"),
                "no_pending_for_you": t(lang, "torch_no_pending"),
            }
            try:
                await query.edit_message_text(
                    msg_map.get(reason, t(lang, "torch_failed")),
                )
            except Exception:
                pass
            return

        outgoing_id = result["outgoing_master_id"]
        sect_name = result["sect_name"]
        elder_name = player.dao_name or get_display_name(player)

        outgoing_lang_row = (await session.execute(
            select(Player.language).where(Player.telegram_id == outgoing_id)
        )).scalar_one_or_none()
        outgoing_lang = normalize_lang(outgoing_lang_row or "en")

        await session.commit()

    try:
        await query.edit_message_text(
            t(lang, "torch_refused_self", sect=escape_markdown(sect_name)),
            parse_mode="Markdown",
        )
    except Exception:
        pass

    try:
        await context.bot.send_message(
            chat_id=outgoing_id,
            text=t(outgoing_lang, "torch_refused_outgoing",
                   elder=escape_markdown(elder_name),
                   sect=escape_markdown(sect_name)),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning("torch refuse DM to outgoing %s failed: %s", outgoing_id, e)


async def sect_contrib_ranking_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Contribution ranking visible to all sect members."""
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    if query:
        await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        info = await get_player_sect_info(session, player.telegram_id)
        if not info:
            return

        sect = info["sect"]

        stmt = (
            select(
                Player.telegram_id,
                Player.dao_name,
                Player.display_name,
                Player.username,
                func.coalesce(func.sum(SectContributionLog.amount), 0).label("total"),
            )
            .join(SectMember, SectMember.player_id == Player.telegram_id)
            .outerjoin(
                SectContributionLog,
                (SectContributionLog.player_id == Player.telegram_id)
                & (SectContributionLog.sect_id == sect.id),
            )
            .where(SectMember.sect_id == sect.id)
            .group_by(Player.telegram_id, Player.dao_name, Player.display_name, Player.username)
            .order_by(desc("total"))
            .limit(20)
        )
        rows = (await session.execute(stmt)).all()

        text = t(lang, "sect_contrib_ranking_title", name=escape_markdown(sect.name)) + "\n\n"
        for i, (tid, dao_name, display_name, uname, total) in enumerate(rows, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            name = dao_name or display_name or uname or str(tid)
            highlight = " 👈" if tid == player.telegram_id else ""
            text += f"{medal} `{escape_markdown(name)}` — {format_number(total)}{highlight}\n"

        if not rows:
            text += t(lang, "sect_contrib_empty") + "\n"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")]
        ])

        try:
            if query:
                await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            if "Message is not modified" not in str(e):
                raise


# ─────────────────────────────────────────────────────────────────────────────
# v16.4 — World Sects (Seita de Cultivo). NPC eternal houses, joined ONLY via the
# affinity recruiter (no manual picker — Lei §2). The mini-app
# WorldSectDirectoryModal is the canonical surface; this chat menu mirrors the
# membership + pending encounters and lets a player accept/decline a recruiter
# DM inline. /status shows a 🏯 line; the recruiter DM (scheduler) routes its
# accept/decline buttons back through `world_sect_button_router` below.
# ─────────────────────────────────────────────────────────────────────────────


async def _render_world_sect_menu(update, context, session, player):
    """Render the Seita de Cultivo menu (membership + pending encounters + affinity)."""
    from core.world_sects_engine import (
        get_player_sect_full, WORLD_SECT_META, get_rank_label_key, resolve_master_name,
    )
    from core.affinity_engine import get_top_affinity_sects, get_affinity_threshold
    from database.models import WorldSectRecruiterPending

    lang = normalize_lang(player.language or "pt")
    pid = player.telegram_id
    now = datetime.now(timezone.utc)

    lines = [f"🏯 *{t(lang, 'wsect_menu_title')}*", "", t(lang, "wsect_split_banner"), ""]
    kb_rows = []

    membership = await get_player_sect_full(session, pid, lang)
    if membership and membership.get("meta"):
        # v16.4c — the member now sees the SECT HALL: rank ladder + contribution
        # progress to the next rung + drill-ins for the Library / Quests / Tribute.
        from core.world_sects_engine import get_sect_hall_state, recompute_player_rank
        # Promote FIRST (if a realm gate cleared since the last contribution gain)
        # so the rank line below renders the fresh rank.
        try:
            if await recompute_player_rank(session, pid):
                await session.commit()
                membership = await get_player_sect_full(session, pid, lang)
        except Exception:
            logger.debug("sect rank recompute failed for player_id=%s", pid, exc_info=True)
        m = membership["meta"]
        rank_label = t(lang, membership.get("rank_key") or get_rank_label_key(membership.get("rank")))
        lines.append(t(lang, "wsect_menu_member", emoji=m["emoji"], sect=m["name"], rank=rank_label))
        lines.append(f"_{m['philosophy']}_")
        # Pedra 2 — the named shifu 师徒 (persisted or deterministic fallback).
        _master = resolve_master_name(player)
        if _master:
            lines.append(t(lang, "wsect_master_line", master=_master, sect=m["name"]))
        try:
            hall = await get_sect_hall_state(session, pid, lang)
            contrib = int(hall.get("contribution", 0))
            nxt = hall.get("next_rank")
            lines.append("")
            if nxt:
                need = int(nxt["contribution_needed"])
                lines.append(t(lang, "wsect_hall_contrib", have=contrib, need=need,
                               next=t(lang, nxt["rank_key"]), bar=_contrib_bar(contrib, need)))
                if not nxt.get("realm_met"):
                    lines.append(t(lang, "wsect_hall_realm_gate", realm=int(nxt["realm_gate"])))
            else:
                lines.append(t(lang, "wsect_hall_maxed", contrib=contrib))
            # TEC-1 — a linha das estantes (gated; OFF = byte-idêntico). Diz
            # quantas artes novas estão ao alcance AGORA (0 é resposta válida).
            try:
                from core.sect_library_engine import biblioteca_on, count_learnable_now
                if biblioteca_on():
                    _n = await count_learnable_now(session, pid)
                    lines.append(t(lang, "lib_menu_line", n=_n))
            except Exception:
                logger.debug("library menu line failed for player_id=%s", pid, exc_info=True)
            kb_rows.append([
                InlineKeyboardButton(t(lang, "wsect_btn_library"), callback_data="wsect_lib"),
                InlineKeyboardButton(t(lang, "wsect_btn_quests"), callback_data="wsect_quests"),
            ])
            kb_rows.append([InlineKeyboardButton(t(lang, "wsect_btn_tribute"), callback_data="wsect_tribute")])
            kb_rows.append([InlineKeyboardButton(t(lang, "merit_pavilion_title"), callback_data="wsect_merit")])
        except Exception:
            logger.debug("sect hall summary failed for player_id=%s", pid, exc_info=True)
        # B (2026-06-16) — leave / betray this Cultivation Sect (simple version, no
        # technique lockout). Always offered to a member, even if the hall
        # summary above failed (Lei §1 — the door is never hidden).
        kb_rows.append([InlineKeyboardButton(t(lang, "wsect_leave_btn"), callback_data="wsect_leave_confirm")])
    else:
        # Live pending recruiter encounters (the Elder is waiting).
        rows = (await session.execute(
            select(WorldSectRecruiterPending).where(
                WorldSectRecruiterPending.player_id == pid,
                WorldSectRecruiterPending.accepted_at.is_(None),
                WorldSectRecruiterPending.declined_at.is_(None),
                WorldSectRecruiterPending.expires_at > now,
            ).order_by(desc(WorldSectRecruiterPending.affinity_score))
        )).scalars().all()

        if rows:
            lines.append(t(lang, "wsect_menu_pending"))
            for r in rows:
                meta = WORLD_SECT_META.get(r.sect_id) or {}
                sname = t(lang, meta.get("name_key") or "")
                emoji = meta.get("emoji") or "🏯"
                lines.append(f"{emoji} *{sname}* — {int(r.affinity_score)}/100")
                kb_rows.append([
                    InlineKeyboardButton(t(lang, "wsect_btn_accept", sect=sname), callback_data=f"wsect_accept_{r.id}"),
                    InlineKeyboardButton(t(lang, "wsect_btn_decline"), callback_data=f"wsect_decline_{r.id}"),
                ])
        else:
            # No sect, no pending — explain the affinity system + show the teaser.
            lines.append(t(lang, "wsect_menu_none"))
            lines.append("")
            lines.append(t(lang, "wsect_menu_explain"))
            try:
                # Fix 2026-07-28 (pergunta do jogador [jogador]: "como entro pra
                # seita demoníaca?") — o teaser mostrava só as casas com score
                # > 0, e o hard-gate de caminho ZERA a casa do outro lado.
                # Quem não era demoníaco nunca via as Profundezas Abissais:
                # nem o nome, nem o requisito. Agora as barradas aparecem com
                # o motivo DITO (Lei §1) — e o motivo diz que a escolha de
                # caminho é de uma vez só, porque é (`path_already_set`).
                from core.affinity_engine import get_affinity_overview
                ov = await get_affinity_overview(session, pid, n=3)
                threshold = int(ov.get("threshold") or get_affinity_threshold())
                if ov.get("eligible"):
                    lines.append("")
                    lines.append(t(lang, "wsect_menu_affinity_teaser", threshold=threshold))
                    for row in ov["eligible"]:
                        meta = WORLD_SECT_META.get(row["sect_id"]) or {}
                        sname = t(lang, meta.get("name_key") or "")
                        emoji = meta.get("emoji") or "🏯"
                        lines.append(f"{emoji} {sname} — {int(row['score'])}/100")
                if ov.get("blocked"):
                    lines.append("")
                    lines.append(t(lang, "wsect_menu_blocked_head"))
                    for row in ov["blocked"]:
                        meta = WORLD_SECT_META.get(row["sect_id"]) or {}
                        sname = t(lang, meta.get("name_key") or "")
                        emoji = meta.get("emoji") or "🏯"
                        lines.append(
                            f"🔒 {emoji} {sname} — "
                            + t(lang, f"wsect_block_{row['reason']}")
                        )
                    lines.append("")
                    lines.append(t(lang, "wsect_menu_path_warning"))
            except Exception:
                logger.debug("affinity teaser failed for player_id=%s", pid, exc_info=True)

    kb_rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita")])
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(kb_rows)

    query = update.callback_query
    try:
        if query:
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


@safe_handler
@rate_limit(1)
async def world_sect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/seita_ancia (+ aliases /seita_cultivo, /seita_de_cultivo) — the Seita de Cultivo (NPC sect) menu."""
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        await _render_world_sect_menu(update, context, session, player)


async def whispers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Onda 3 — /sussurros — Heaven's Whispers (atmospheric world-event feed).

    Chat parity for the mini-app Whispers feed. Read-only, cosmetic. The
    server-rendered whisper bodies are already localized per the reader's lang.
    """
    from core.heavens_whispers_engine import list_recent_whispers
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = (player.language or "pt").lower()
        whispers = await list_recent_whispers(session, limit=8, lang=lang)
    header = f"🌌 {t(lang, 'wsp_feed_title')}"
    if not whispers:
        await update.message.reply_text(f"{header}\n\n{t(lang, 'wsp_feed_empty')}")
        return
    lines = [header, ""]
    for w in whispers:
        lines.append(f"{w.get('icon', '🌌')} {w.get('body', '')}")
    await update.message.reply_text("\n\n".join(lines))


async def cronica_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """World Pulse Fase 1 — /cronica — Os Registos Celestiais (the living world log).

    Chat parity for the mini-app Chronicle feed (canonical surface). Read-only,
    cosmetic. The chronicle lines are rendered server-side, already localized per
    the reader's language (the {sect}/{rival}/{continent} names are merged in)."""
    from core.world_pulse_engine import list_recent_chronicle
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = (player.language or "pt").lower()
        # MV-8 — o `viewer_continent` faz a Crônica virar RUMOR: notícia de
        # longe só chega depois da estrada (`jianghu` OFF → parâmetro ignorado,
        # feed byte-idêntico).
        entries = await list_recent_chronicle(
            session, limit=10, lang=lang,
            viewer_continent=getattr(player, "current_continent", None))
    header = f"📜 {t(lang, 'cronica_feed_title')}"
    if not entries:
        await update.message.reply_text(f"{header}\n\n{t(lang, 'cronica_feed_empty')}")
        return
    lines = [header, ""]
    for e in entries:
        lines.append(f"{e.get('icon', '📜')} {e.get('text', '')}")
    await update.message.reply_text("\n".join(lines))


async def praca_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Onda 4a — /praca — the Continental Plaza (Wànshì), chat parity.

    Read-only mirror of the mini-app PlazaTab (canonical surface): the open
    bounty contracts for the player's continent + a deep-link to the mini-app
    for the full plaza (presence, services, feed, the hunt). Lei §1 — every NPC
    line carries the honest 🤖 chip; nothing here is forced PvP.
    """
    from core.bounty_engine import list_active_bounties
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = (player.language or "pt").lower()
        bounties = await list_active_bounties(session, player, lang=lang)
        # MV-2 — Tiandao: evento NESTE continente (linha local acionável — fix
        # do review, Lei §1) + rumor de evento NOUTRO continente. Gated, fail-safe.
        wev_rumors = []
        wev_local = []
        rst_local = None
        try:
            from core.continent_engine import is_valid_continent as _ivc
            from core.tiandao_engine import (
                director_on as _wev_on, local_event_lines as _wev_ll, rumor_views as _wev_rv,
            )
            _cont = player.current_continent if _ivc(player.current_continent) else "linghe"
            if _wev_on():
                wev_local = await _wev_ll(session, _cont, lang)
                wev_rumors = await _wev_rv(session, _cont, lang)
            # MV-4 §0 (dívida MV-3) — a linha do estado LOCAL na praça (mesmo
            # padrão do world_event_local; flag OFF → None, nada muda).
            from core.region_state_engine import local_state_view
            rst_local = await local_state_view(session, _cont, lang)
        except Exception:
            logger.exception("praca tiandao rumor failed")
        # MV-5 — o encontro na praça: um NPC "te chama" (mint sujeito ao pacer
        # do engine; commit SÓ quando mintou). Gated + fail-safe: flag OFF →
        # zero queries, zero linhas novas.
        sty_offer = None
        try:
            from core.storylet_engine import quests_vivas_on, maybe_offer, open_offer_view
            if quests_vivas_on():
                sty_offer = await maybe_offer(session, player, source="plaza")
                if sty_offer is not None:
                    await session.commit()
                else:
                    sty_offer = await open_offer_view(session, player, lang)
        except Exception:
            logger.exception("praca storylet offer failed")
        # MV-6 — a rep local (chip + reverência/desprezo) e O RIVAL na praça.
        # Gated + fail-safe: flag OFF → None → zero linhas novas.
        rep_local = None
        rival_card = None
        try:
            from core.reputation_engine import local_rep_view, rival_view
            rep_local = await local_rep_view(session, player, lang)
            rival_card = await rival_view(session, player, lang)
        except Exception:
            logger.exception("praca reputation/rival failed")
        # MV-8 — a emboscada na praça (o 2º cano por volume). Gated + fail-safe:
        # flag OFF → None sem query → zero linhas novas.
        jh_ambush = None
        try:
            from core.jianghu_engine import ambush_offer
            jh_ambush = await ambush_offer(session, player, source="plaza", lang=lang)
        except Exception:
            logger.exception("praca jianghu ambush failed")
        # MV-9 — A CIDADE: nome/traço do lugar + o encargo vigente. Gated +
        # fail-safe: flag OFF → None → zero linhas novas (o /praca fica
        # byte-idêntico). ⚠️ Este bloco tem try PRÓPRIO: o /praca já junta
        # tiandao e estado regional num só try (linhas 2581-2594) e uma falha
        # ali cala os dois — não repetir o padrão.
        _city = None
        try:
            from core.city_engine import city_plaza_view
            _city = await city_plaza_view(session, player, lang)
        except Exception:
            logger.exception("praca city view failed")
        # MV-9.5 商队 — A CARAVANA: o velho da cidade manda vir o que a montanha
        # do outro lado guarda. Gate = AND duro (caravana ∧ cidades ∧
        # dungeons_regionais) → None SEM uma única query ⇒ o /praca fica
        # byte-idêntico para quem tem as flags OFF. try PRÓPRIO (o try das
        # linhas acima já junta tiandao + estado regional e uma falha ali cala
        # os dois — não repetir o padrão).
        _crv = None
        try:
            from core.caravan_engine import caravan_view
            _crv = await caravan_view(session, player, lang)
        except Exception:
            logger.exception("praca caravan view failed")
        # ⚠️ QUEM FINALIZA CREDITA: `caravan_view` entrega as cargas que já
        # chegaram e por isso SUJA a sessão. O único commit desta função (acima)
        # só acontece no ramo em que o MV-5 minta uma oferta — sem este, o
        # crédito da carga ficava refém desse ramo e evaporava no fecho do
        # `async with`, comendo o progresso em silêncio.
        if _crv and (_crv.get("delivered") or _crv.get("bag_full")):
            try:
                await session.commit()
            except Exception:
                logger.exception("praca caravan credit commit failed")
        # MV-11 天时 — O TEMPO DO CÉU. PURO e SÍNCRONO: zero query, zero await,
        # zero escrita — mesmo com a flag ON (o céu é derivado do relógio, não
        # de uma tabela). Fica aqui, na fase de dados, só para respeitar a
        # divisão da função (a montagem do texto abaixo não tem sessão) e para
        # que a guarda do espaçador possa vê-lo. try PRÓPRIO — o try partilhado
        # do tiandao acima cala dois blocos quando um falha (comentário :2630).
        _sky = None
        try:
            from core.tianshi_engine import sky_plaza_view
            _sky = sky_plaza_view(lang)
        except Exception:
            logger.exception("praca tianshi view failed")
    # MV-9 — o cabeçalho diz o nome do lugar ONDE VOCÊ ESTÁ. Até aqui dizia
    # "Praça de Wànshì" nos CINCO continentes: para os 53% dos ativos que estão
    # fora de Línghé isso era mentira (Lei §1), e Wànshì fica em Línghé pelo
    # lore. Flag OFF → `_city` é None → a linha de sempre, byte-idêntica.
    header = f"🏙️ {t(lang, 'city_wanshi')}"
    _city_intro = None
    if _city:
        header = f"{_city['emoji']} {_city['name']}"
        _city_intro = _city.get("trait")
    lines = [header, _city_intro or t(lang, "plaza_chat_intro"), ""]
    # MV-11 天时 — o céu é do MUNDO, não do chão: vem ANTES da linha do estado
    # regional porque é a única linha desta praça que é verdadeira nos cinco
    # continentes (inclusive em Mòyǔ, que está fora de TIDE_CONTINENTS e de
    # METEOR_CONTINENTS e nunca teve um evento em toda a sua história).
    # ⚠️ Texto PLANO: esta função não passa `parse_mode` (o reply_text no fim
    # dela), logo um `*negrito*` sairia com os asteriscos na cara do jogador.
    if _sky:
        lines.append(_sky["line"])
        lines.append(_sky["next"]["line"])
    if rst_local:
        lines.append(f"{rst_local.get('emoji', '🌾')} {rst_local.get('text', '')}")
        # MV-8 — o lugar onde a ocupação CUSTA (+10% no mercado, +1 de risco) é
        # o lugar onde o ocupante tem de ter NOME. Sem esta linha a bandeira era
        # anônima justamente para quem está debaixo dela.
        if rst_local.get("occupant_line"):
            lines.append(rst_local["occupant_line"])
    if rep_local:
        _chip = rep_local.get("chip") or {}
        if _chip.get("line"):
            lines.append(f"{t(lang, 'rep_plaza_prefix')} {_chip['line']}")
        if rep_local.get("line"):
            lines.append(rep_local["line"])
    for r in (wev_local + wev_rumors):
        lines.append(f"{r.get('emoji', '🌀')} {r.get('text', '')}")
    # MV-9 — o ENCARGO 城务: o que esta cidade pede AGORA. Aparece sempre que a
    # flag está ON — inclusive a RECUSA nomeada quando `quests_vivas` está OFF
    # (Lei §1: a porta trancada aparece trancada, com o motivo dito).
    _enc = (_city or {}).get("encargo")
    if _enc:
        lines.append("")
        lines.append(t(lang, "cid_plaza_encargo_title"))
        if _enc.get("locked"):
            lines.append(_enc.get("line", ""))
        else:
            lines.append(f"{_enc['icon']} {_enc['name']}")
            lines.append(_enc.get("desc", ""))
            # ⚠️ `_mine` é lido pela linha de objetivo (abaixo) E pelo bloco de
            # progresso; tem de ser atribuído ANTES dos dois.
            _mine = _enc.get("mine") or {}
            # QoL 07/08 (report [jogador]) — o OBJETIVO dito, e o comando que leva ao
            # lugar dele. Antes daqui saía só o nome, a atmosfera e "0 / 3": um
            # contador sem substantivo. No chat não há salto de aba — diz-se o
            # comando (precedente do 03/08: apontar o caminho em texto é melhor
            # do que largar o jogador no sítio errado).
            # O PONTEIRO some quando o encargo já está pronto: aí o caminho é
            # entregar, não repetir (mesma regra do `not is_completed` das
            # quests). A FRASE do objetivo fica sempre — ela é o contrato.
            if _enc.get("objective_line"):
                _obj = _enc["objective_line"]
                if _enc.get("objective_cmd") and _mine.get("status") != "ready":
                    _obj += f"  ·  {_enc['objective_cmd']}"
                lines.append(_obj)
            if _mine.get("status") in ("accepted", "ready"):
                lines.append(t(lang, "cid_plaza_progress",
                               n=_mine.get("progress", 0),
                               total=_mine.get("count") or _enc.get("objective_count", 1)))
            elif _mine.get("reason_line"):
                lines.append(_mine["reason_line"])
            else:
                lines.append(t(lang, "cid_plaza_accept_hint"))
    # MV-9.5 商队 — A CARAVANA. Flag OFF → `_crv` é None → zero linhas novas.
    # ⚠️ Texto PLANO: o reply_text no fim desta função NÃO passa `parse_mode` —
    # um `*negrito*` sairia com os asteriscos na cara do jogador.
    # ⚠️ Os botões NÃO podem ir directos para `rows`: `rows` só nasce dezenas de
    # linhas abaixo. Ficam aqui em `_crv_rows` e MERGEM lá (o mesmo contrato do
    # bloco da emboscada — só existe UM reply_markup nesta função).
    _crv_rows: list[list[InlineKeyboardButton]] = []
    if _crv:
        lines.append("")
        lines.append(t(lang, "crv_plaza_title"))
        # `npc_name` / `npc_intro` JÁ vêm localizados do servidor (padrão
        # Crônica/cidades) — imprimir CRUS, nunca passar por t(). O chip 🤖 é a
        # marca honesta de "isto é um NPC" desta praça — e por isso NÃO entra em
        # Mòyǔ, onde o `npc_name` é literalmente "Nenhum caravaneiro": chipar a
        # ausência de gente como se fosse gente era o display-lie ao contrário.
        lines.append(f"{'🤖 ' if _crv.get('has_caravan') else ''}{_crv.get('npc_name', '')}")
        if _crv.get("npc_intro"):
            lines.append(_crv["npc_intro"])
        # Quem finaliza credita — e o que foi creditado é DITO na hora.
        for _d in (_crv.get("delivered") or []):
            lines.append(t(lang, "crv_plaza_arrived", emoji=_d.get("emoji", ""),
                           name=_d.get("name", ""), n=_d.get("qty", 0)))
        for _d in (_crv.get("bag_full") or []):
            lines.append(t(lang, "crv_plaza_bagfull", emoji=_d.get("emoji", ""),
                           name=_d.get("name", "")))
        if (_crv.get("in_transit") or {}).get("line"):
            lines.append(_crv["in_transit"]["line"])
        if (_crv.get("soul_locked") or {}).get("line"):
            lines.append(_crv["soul_locked"]["line"])
        if not _crv.get("has_caravan") and _crv.get("locked_line"):
            lines.append(_crv["locked_line"])
        # O velho NUNCA se vende como o melhor caminho — isto é o desenho, não
        # um aviso legal: a estrada rende mais do que a mula dele.
        if _crv.get("honest_line"):
            lines.append(_crv["honest_line"])
        # Lei §1 — a rota trancada APARECE trancada, com o motivo dito, e nunca
        # como botão morto. Agrupada por motivo: quando a alma recusa (ou já há
        # carga na estrada) TODAS as rotas partilham a mesma frase, e repeti-la
        # quatro vezes seria ruído, não honestidade.
        _crv_locked: dict[str, list[str]] = {}
        for _r in (_crv.get("routes") or []):
            # ⚠️ `pays` vazio numa rota ABERTA cai aqui de propósito: medido, o
            # caso não acontece com as seeds de hoje (as 9 rotas vivas têm 9 a
            # 16 pagamentos), mas se o Encargo do dia esvaziasse a lista a rota
            # SUMIA da tela sem uma palavra — o apagador de existência que o
            # jogo já apanhou uma vez. Fica trancada e visível; sem motivo
            # inventado, porque nenhuma frase da casa diz esta situação.
            if not _r.get("locked") and (_r.get("pays") or []):
                continue
            _crv_locked.setdefault(_r.get("reason_line") or "", []).append(
                f"{_r.get('emoji', '')} {_r.get('name', '')}".strip())
        for _reason, _names in _crv_locked.items():
            _ln = f"🔒 {' · '.join(_names)}"
            if _reason:
                _ln += f" — {_reason}"
            lines.append(_ln)
        for _r in (_crv.get("routes") or []):
            _pays = _r.get("pays") or []
            if _r.get("locked") or not _pays:
                continue
            _pay = _pays[0]
            # `crv_s_<k><id>_<k><id>` (ex.: crv_s_h11_o2) — bem dentro dos 64
            # bytes de callback_data.
            _crv_rows.append([InlineKeyboardButton(
                t(lang, "crv_btn_send", emoji=_r.get("emoji", ""),
                  name=_r.get("name", ""), n=int(_r.get("units") or 0),
                  cost=int(_r.get("cost") or 0), pay=_pay.get("name", "")),
                callback_data=(
                    f"crv_s_{str(_r.get('kind') or '')[:1]}{int(_r.get('item_id') or 0)}"
                    f"_{str(_pay.get('kind') or '')[:1]}{int(_pay.get('item_id') or 0)}"),
            )])
        # A geografia dita — o valor que serve todos, de graça, mesmo a quem a
        # caravana não traz nada. Era a linha que faltava ao jogo inteiro.
        _atlas = _crv.get("atlas") or []
        if _atlas:
            lines.append("")
            lines.append(t(lang, "crv_plaza_atlas_title"))
            for _a in _atlas:
                _ln = f"{_a.get('emoji', '')} {_a.get('name', '')} — {_a.get('origin_line', '')}"
                if _a.get("here"):
                    _ln += f" ({t(lang, 'crv_atlas_here')})"
                lines.append(_ln)
        # A dica fala de botões — só sai quando existem botões (sem ela a frase
        # mandaria tocar num material que não está lá).
        if _crv_rows:
            lines.append(t(lang, "crv_plaza_hint"))
    if rst_local or rep_local or wev_local or wev_rumors or _enc or _crv or _sky:
        lines.append("")
    lines.append(f"🏴 {t(lang, 'bounty_board_title')}")
    if bounties:
        # Track A item 3 — distinguish 🏴 world-issued vs 🎁 player-posted ("a
        # prêmio") contracts; the latter name the poster (public handle, no PII).
        # Interleave both origins so player-posted ones always surface in chat
        # even when world contracts fill the head of the list (list_active_bounties
        # returns world rows first); else the wbounty_post_chat_hint contradicts
        # an all-world board on a busy continent.
        world_b = [b for b in bounties if b.get("source") != "player"]
        player_b = [b for b in bounties if b.get("source") == "player"]
        shown = world_b[:3] + player_b[:3]
        for b in shown:
            npc = b.get("npc") or {}
            is_player = b.get("source") == "player"
            line = (
                f"{'🎁' if is_player else '🏴'} 🤖 {npc.get('name', '?')} · "
                f"{npc.get('realm_emoji', '🌀')}{npc.get('realm_name', '')} · 🪨 {b.get('reward_stones', 0)}"
            )
            # MV-3 §0 fix — the viewer's OWN contract is chipped (and, when it
            # hangs on ANOTHER continent's board, says where — Lei §1).
            if b.get("mine"):
                line += f" · {t(lang, 'wbounty_yours_chip')}"
                if b.get("elsewhere") and b.get("continent_name"):
                    line += f" ({b.get('continent_emoji', '')} {b['continent_name']})"
            elif is_player and b.get("posted_by_name"):
                line += f" · {t(lang, 'wbounty_posted_by', name=b['posted_by_name'])}"
            lines.append(line)
    else:
        lines.append(t(lang, "bounty_board_empty"))
        # MV-3 §0 fix — the empty board teaches the geography (each continent
        # hangs its own cartazes; travel to hunt others), never a mute void.
        lines.append(t(lang, "bounty_board_empty_hint"))
    # MV-5 — a oferta viva na praça: o giver te chama pelo nome + CTA honesto
    # (o diálogo/aceite vive em /missoes — a praça do chat é um espelho).
    if sty_offer:
        lines += ["", f"📜 {t(lang, 'sty_plaza_call', giver=sty_offer.get('giver', '?'), name=sty_offer.get('name', ''))}",
                  t(lang, "sty_plaza_call_hint")]
    # MV-6 — O RIVAL na praça: presença 😤 + botão (prefixo rvl_ — registrado
    # no combined_button_router ANTES de usar, lição MV-2). O duelo vive no
    # mini-app (onde TODO duelo vs NpcCultivator vive — destinos nunca mudam);
    # o botão do chat abre a memória (taunt + estado).
    rows: list[list[InlineKeyboardButton]] = []
    if rival_card:
        lines += ["", f"😤 {t(lang, 'rvl_plaza_line', name=rival_card.get('name', '?'))}"]
        rows.append([InlineKeyboardButton(
            f"😤 {t(lang, 'rvl_btn_view')}", callback_data="rvl_view",
        )])
    # MV-8 — a emboscada na praça. ⚠️ Só EXISTE um reply_markup nesta função e
    # até aqui era o do rival: sobrescrevê-lo apagaria o botão dele. Por isso
    # os dois blocos MERGEM em `rows`.
    if jh_ambush:
        _amb_lines, _amb_rows = jianghu_ambush_block(lang, jh_ambush)
        lines += _amb_lines
        rows += _amb_rows
    # MV-9.5 — os botões da caravana MERGEM (nunca reatribuem `rows`): o texto
    # dela sai lá em cima, junto do Encargo, mas o teclado é UM só.
    rows += _crv_rows
    # MV-9 — o quadro é DESTE continente (`bounty_engine` filtra por
    # `continent_key`), logo os arquivos são os DESTA cidade. Antes esta linha
    # dizia "Arquivos de Wànshì" com o nome COZIDO no valor da string: um
    # jogador em Mòyǔ lia "Cidade dos Ecos" no cabeçalho e, dezenas de linhas
    # abaixo, era mandado a uma cidade de outro continente — no MESMO bloco de
    # `lines`. Flag OFF → `_city` é None → cai no nome de sempre.
    lines += ["", t(lang, "wbounty_post_chat_hint",
                    city=(_city or {}).get("name") or "Wànshì"),
              t(lang, "plaza_open_miniapp")]
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(rows) if rows else None,
    )


# ── MV-8 江湖 — a EMBOSCADA no chat (prefixo jha_) ───────────────────────────
# O chat não tem arena: ⚔️ diz honestamente que a luta abre no mini-app (o
# padrão `explore_finish_duel`); 💰 e 🏃 resolvem INTEIROS aqui. Nunca um botão
# que não faz nada — e nunca um encontro sem saída (Lei §1).

def jianghu_ambush_block(lang: str, ambush: dict) -> tuple[list[str], list[list[InlineKeyboardButton]]]:
    """As linhas + os 3 botões de UMA emboscada. Fonte ÚNICA das 3 superfícies
    de chat (praça, chegada de viagem, exploração) — nenhuma delas reescreve o
    texto."""
    npc_id = int(ambush.get("npc_id") or 0)
    cost = int(ambush.get("bribe_cost") or 0)
    qi = int(ambush.get("qi_cost") or 25)
    hours = int(ambush.get("travel_cooldown_hours") or 4)
    # ⚠️ Texto PLANO: nenhuma das superfícies que consomem este bloco
    # (praca_command / _travel_safe_edit / _maybe_send_ambush) passa
    # `parse_mode` — um `*negrito*` sairia com os asteriscos na cara do jogador.
    lines = [
        "",
        # (o título já traz o 🗡️ dentro — prefixá-lo dava "🗡️ 🗡️ Emboscada")
        ambush.get("title") or t(lang, "jh_amb_title"),
        ambush.get("intro") or "",
        ambush.get("reason_line") or "",
        t(lang, "jh_amb_hint", qi=qi, cost=cost, hours=hours),
    ]
    rows = [[
        InlineKeyboardButton(t(lang, "jh_amb_btn_fight"), callback_data=f"jha_f:{npc_id}"),
        InlineKeyboardButton(t(lang, "jh_amb_btn_bribe", cost=cost), callback_data=f"jha_b:{npc_id}"),
        InlineKeyboardButton(t(lang, "jh_amb_btn_flee"), callback_data=f"jha_r:{npc_id}"),
    ]]
    return [ln for ln in lines if ln != ""] + [""], rows


async def jianghu_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `jha_*` (MV-8). Returns True if handled.

    UM answer por callback (lição A Volta: um safe_answer vazio ANTES do alerta
    engole o alerta). O lock do jogador vive AQUI — é o mesmo contrato de
    `do_travel`/`claim_bounty`, e sem ele um duplo-tap em 💰 debitaria duas vezes.
    """
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("jha_"):
        return False
    from core.utils import safe_answer
    try:
        kind, raw = query.data.split(":", 1)
        npc_id = int(raw)
    except (ValueError, TypeError):
        await safe_answer(query)
        return True
    branch = {"jha_f": "fight", "jha_b": "bribe", "jha_r": "flee"}.get(kind)
    if branch is None:
        await safe_answer(query)
        return True
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id))
            .with_for_update()
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query)
            return True
        lang = normalize_lang(player.language or "pt")
        from core.jianghu_engine import ambush_resolve
        res = await ambush_resolve(session, player, npc_id=npc_id, branch=branch, lang=lang)
        if not res.get("ok"):
            reason = res.get("reason")
            if reason == "not_enough_stones":
                msg = t(lang, "jh_amb_no_stones", cost=res.get("cost", 0), have=res.get("have", 0))
            elif reason == "hp_depleted":
                msg = t(lang, "jh_amb_hp")
            elif reason == "qi_insufficient":
                msg = t(lang, "jh_amb_qi", qi=res.get("qi_cost", 25))
            elif reason in ("already_resolved", "duel_already_active"):
                msg = t(lang, "jh_amb_already")
            else:   # hunter_gone / off / internal_error
                msg = t(lang, "jh_amb_gone")
            await safe_answer(query, msg, show_alert=True)
            return True
        # ⚔️ O chat NÃO tem tabuleiro de duelo. Antes esta linha só dizia "abre
        # no mini-app" — mas o duelo já existia, com rodadas de 15s, e o sweep
        # de 60s jogava-o SOZINHO pelo jogador (golpe básico dos dois lados) e
        # nunca contava o resultado: uma derrota forçada e muda, exatamente o
        # que a arena recusa citando a Lei §1. Molde da casa (`trv_lgc_go` do
        # TEC-4): auto-play + settle + resultado NA HORA, no chat.
        auto_payload: dict = {}
        auto_won = False
        if branch == "fight":
            from database.models import DuelSession as _DS
            duel = (await session.execute(
                select(_DS).where(_DS.id == res["duel_id"])
            )).scalar_one_or_none()
            if duel is None:
                await safe_answer(query, t(lang, "jh_amb_gone"), show_alert=True)
                return True
            try:
                from core.duel_engine import apply_post_duel_effects
                from core.sect_trial_engine import auto_play_trial_duel
                await auto_play_trial_duel(session, duel, int(player.telegram_id))
                await apply_post_duel_effects(session, duel)
            except Exception:
                logger.exception("jianghu ambush auto-play failed (player=%s)",
                                 player.telegram_id)
                await session.rollback()
                await safe_answer(query, t(lang, "jh_amb_gone"), show_alert=True)
                return True
            auto_won = (duel.winner_id == player.telegram_id and duel.state == "finished")
            for _e in reversed(duel.action_log or []):
                if isinstance(_e, dict) and _e.get("type") == "pve_settled":
                    auto_payload = _e.get("payload") or {}
                    break
        await session.commit()
    await safe_answer(query)
    # O teclado do encontro morre com o encontro: deixá-lo vivo era o que
    # permitia um 2º toque em 💰 (o pacer no engine já recusa, mas um botão que
    # só sabe dizer "não" é lixo na tela).
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if branch == "bribe":
        await query.message.reply_text(
            t(lang, "jh_amb_bribe_ok", cost=res.get("spent_stones", 0), npc=res.get("name", "?")))
    elif branch == "flee":
        hours = int((res.get("travel_cooldown_ms") or 0) / 3600000) or 4
        await query.message.reply_text(
            t(lang, "jh_amb_flee_ok", npc=res.get("name", "?"), hours=hours))
    else:
        parts = [t(lang, "jh_amb_fight_won" if auto_won else "jh_amb_fight_lost",
                   npc=res.get("name", "?"),
                   stones=int(auto_payload.get("reward_stones") or 0))]
        # O fork moral vive no mini-app (é lá que a decisão tem tela). No chat
        # dizemos que ele EXISTE — nunca um "ganhou" que esconde uma escolha.
        if auto_won and auto_payload.get("offer_moral_choice"):
            parts.append(t(lang, "jh_amb_fight_moral"))
        await query.message.reply_text("\n".join(parts))
    return True


# ── MV-9.5 商队 — A CARAVANA no chat (prefixo crv_) ──────────────────────────
# Escambo puro: nenhuma pedra atravessa o fluxo. O botão da praça manda vir UMA
# carga; toda recusa é NOMEADA pelo engine (Lei §1) e chega ao jogador como
# alerta — nunca um clique silencioso.

_CRV_KINDS = {"h": "herb", "o": "ore"}


async def caravan_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `crv_*` (MV-9.5). Returns True if handled.

    `crv_s_<k><id>_<k><id>` (ex.: `crv_s_h11_o2`) — o alvo e o material com que
    se paga, ambos abreviados pela inicial do tipo para caber nos 64 bytes.

    UM answer por callback (lição A Volta: um `safe_answer` vazio ANTES do
    alerta faz o Telegram ENGOLIR o alerta). O lock do jogador vive AQUI — é o
    contrato de `send_load` (o caller trava a row FOR UPDATE e é dono do
    commit); sem ele um duplo-tap debitaria o material duas vezes.
    """
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("crv_"):
        return False
    from core.utils import safe_answer
    if not query.data.startswith("crv_s_"):
        await safe_answer(query)
        return True
    # Nunca um `int()` nu sobre callback_data.
    try:
        _raw_t, _raw_p = query.data[len("crv_s_"):].split("_", 1)
        target_kind = _CRV_KINDS[_raw_t[:1]]
        target_id = int(_raw_t[1:])
        pay_kind = _CRV_KINDS[_raw_p[:1]]
        pay_id = int(_raw_p[1:])
    except (ValueError, TypeError, KeyError, IndexError):
        await safe_answer(query)
        return True
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id))
            .with_for_update()
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query)
            return True
        lang = normalize_lang(player.language or "pt")
        from core.caravan_engine import send_load
        result = await send_load(
            session, player,
            target_kind=target_kind, target_id=target_id,
            pay_kind=pay_kind, pay_id=pay_id, lang=lang,
        )
        # COMITA SEMPRE — e é seguro por construção, não por sorte.
        # `send_load` foi escrito para que a recusa NUNCA mute nada: o débito é
        # `debit_materials`, all-or-nothing row-locked, e é a ÚLTIMA coisa que
        # acontece; toda recusa retorna antes dele, e um débito insuficiente
        # devolve False sem ter mutado uma linha. Portanto, num ramo de recusa,
        # a única coisa pendente na sessão é o CRÉDITO oportunista das cargas
        # que chegaram (`credit_arrived`, chamado no início).
        #
        # ⚠️ Fazer `rollback()` aqui desfazia esse crédito. Era idempotente e
        # voltaria a acontecer — mas só na próxima abertura da praça. Quem joga
        # pelo botão e nunca abre o /praca ficava com a carga entregue a ser
        # desfeita a cada toque recusado. "Quem finaliza credita" não admite um
        # ramo que descredita.
        await session.commit()
    # O alerta é a ÚNICA resposta deste callback.
    await safe_answer(query, result.get("line") or t(lang, "crv_refuse_busy"),
                      show_alert=True)
    return True


# ── MV-6 — O RIVAL no chat (prefixo rvl_; o duelo vive no mini-app) ──────────

async def rival_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `rvl_*` callbacks (MV-6). Returns True if handled.

    UM answer por callback (lição A Volta): no caminho stale o ALERTA é a
    resposta — nunca um safe_answer vazio antes dele. `rvl_view` abre a
    memória do rival (taunt + estado + escala honesta); o CTA de duelo vive no
    mini-app, onde TODO duelo vs NpcCultivator vive (destinos nunca mudam).
    """
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("rvl_"):
        return False
    from core.utils import safe_answer
    if query.data != "rvl_view":
        await safe_answer(query)
        return True
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id))
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query)
            return True
        lang = normalize_lang(player.language or "pt")
        card = None
        try:
            from core.reputation_engine import rival_view
            card = await rival_view(session, player, lang)
        except Exception:
            logger.exception("rvl_view failed")
    if not card:
        # Stale (o estado mudou entre o render e o tap) — o alerta É a
        # resposta (Lei §1 + UM answer). Review MV-6: distinguir AUSENTE
        # (ele ainda é seu rival, só lambe as feridas — voltará) de SUMIDO
        # (rivalidade acabou); dizer "acabou" a um rival vivo era mentira.
        _away = False
        try:
            from core.reputation_engine import reputacao_on as _rep_on
            _away = bool(getattr(player, "rival_npc_id", None)) and _rep_on()
        except Exception:
            pass
        await safe_answer(query, t(lang, "rvl_away_alert" if _away else "rvl_gone_alert"),
                          show_alert=True)
        return True
    await safe_answer(query)
    lines = [
        f"😤 {card.get('name', '?')}",
        "",
        f"“{card.get('taunt', '')}”",
        "",
        t(lang, "rvl_view_defeats", n=card.get("defeats", 1)),
    ]
    if card.get("power_bonus_pct"):
        lines.append(t(lang, "rvl_view_power", pct=card["power_bonus_pct"]))
    if card.get("spared"):
        lines.append(t(lang, "rvl_view_spared"))
    lines += ["", t(lang, "rvl_open_app_hint")]
    await query.message.reply_text("\n".join(lines))
    return True


# ── Onda 4b — Travel between continents (chat parity; mini-app is canonical) ──

def _fmt_travel_dur(ms):
    """ms -> compact 'Xh Ym' / 'Ym' / 'Zs' (chat duration disclosure)."""
    s = max(0, int((ms or 0) / 1000))
    h, m = s // 3600, (s % 3600) // 60
    if h > 0:
        return f"{h}h{(' ' + str(m) + 'm') if m else ''}"
    if m > 0:
        return f"{m}m"
    return f"{s}s"


def _travel_reason_line(lang, dst, cooldown_remaining_ms):
    """Localized disclosure for a destination the player can't reach yet."""
    r = dst.get("reason")
    if r == "locked_demonic":
        return t(lang, "travel_locked_demonic")
    if r == "on_cooldown":
        return t(lang, "travel_on_cooldown", time=_fmt_travel_dur(cooldown_remaining_ms))
    if r == "not_enough_stones":
        return t(lang, "travel_not_enough_stones", cost=dst.get("cost", 0))
    return None


async def _travel_safe_edit(query, text, reply_markup=None):
    """edit_text that swallows ONLY the benign 'Message is not modified'
    BadRequest (re-tap of the same button) and re-raises everything else, so a
    real failure is logged by the outer @safe_handler on combined_button_router.
    Mirrors the canonical edit pattern used across the handlers."""
    try:
        await query.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


async def _render_travel_menu(update, lang, data, *, edit=False):
    """The travel list: current continent + a button per destination."""
    dests = data.get("destinations", [])
    lines = [f"🧭 {t(lang, 'travel_title')}", t(lang, "travel_intro"), ""]
    cur = next((x for x in dests if x.get("is_current")), None)
    if cur:
        lines.append(f"📍 {cur.get('emoji', '🗺️')} {cur.get('name', '')} — {cur.get('specialty', '')}")
        # MV-3 — Estados Regionais: a linha do estado do continente ATUAL
        # ("🏚️ Sitiada — estradas caras, mercados nervosos"). Só chega no
        # data com a flag ON (region_state_line — payload-gated).
        if cur.get("region_state_line"):
            lines.append(cur["region_state_line"])
        # MV-6 — Reputação: como o lugar ATUAL te recebe (payload-gated).
        if cur.get("region_rep_line"):
            lines.append(f"{t(lang, 'rep_travel_prefix')} {cur['region_rep_line']}")
    # MV-2 — Tiandao: 1 linha por evento celestial ativo ("🌊 Maré de Bestas em
    # ⛰️ Qiānhé — 31h restantes"). Só chega no data com a flag ON.
    wev_lines = data.get("world_event_lines") or []
    if wev_lines:
        lines.append("")
        lines.extend(wev_lines)
    # TEC-4 — a Gruta do Legado ativa (payload-gated: a key só chega no data
    # com a flag `legacy_caves` ON). A vitrine é honesta ANTES do tap: chance
    # da arte + tentativa única DITAS (Lei §1; display = roll).
    _cave = data.get("legacy_cave")
    if _cave:
        lines.append("")
        lines.append(t(lang, "lgc_chat_line", emoji=_cave.get("continent_emoji", ""),
                       name=_cave.get("continent_name", ""), npc=_cave.get("npc", ""),
                       time=_cave.get("time_left_label", "")))
        lines.append(t(lang, "lgc_chat_stakes", pct=_cave.get("art_chance_pct", 0),
                       pity=_cave.get("pity_clears", 3)))
        if _cave.get("attempted"):
            lines.append(t(lang, "lgc_chat_attempted"))
        elif _cave.get("has_art"):
            lines.append(t(lang, "lgc_chat_has_art"))
    lines += ["", f"✨ {t(lang, 'travel_changes_note')}"]
    rows = []
    # MV-2 — ⛏️ ação do meteoro DESTE continente (só chega no data com a flag
    # ON e meteoro aqui; fix do review — o chat age, não só lê).
    if data.get("wev_mine_cost") is not None:
        rows.append([InlineKeyboardButton(
            t(lang, "wev_chat_mine_btn", cost=data["wev_mine_cost"]),
            # prefixo trv_ = o main.py já despacha para este router (o combined
            # router só chama travel_button_router para trv_*/cmd_viajar)
            callback_data="trv_wev_mine",
        )])
    # TEC-4 — 🏮 entrar na Gruta (só quando NO continente e sem tentativa gasta;
    # o servidor re-verifica tudo — o botão é conveniência, não o gate).
    if _cave and _cave.get("can_enter"):
        rows.append([InlineKeyboardButton(
            t(lang, "lgc_chat_enter_btn"),
            callback_data="trv_lgc_go",
        )])
    for dst in dests:
        if dst.get("is_current"):
            continue
        # MV-3 — o emoji do estado no botão quando o destino NÃO está próspero
        # (⚡/🏚️/🏮 — disclosure de um tap; a linha completa vive no trv_d_).
        _st_emoji = dst.get("region_state_emoji", "")
        _st_prefix = f"{_st_emoji} " if _st_emoji and dst.get("region_state") != "prospera" else ""
        rows.append([InlineKeyboardButton(
            f"{_st_prefix}{dst.get('emoji', '🗺️')} {dst.get('name', '')} · 🪨 {dst.get('cost', 0)}",
            callback_data=f"trv_d_{dst['key']}",
        )])
    kb = InlineKeyboardMarkup(rows) if rows else None
    text = "\n".join(lines)
    if edit and update.callback_query:
        await _travel_safe_edit(update.callback_query, text, kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def viajar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Onda 4b — /viajar — travel between the five continents (chat parity).

    The mini-app (PlazaTab → 🧭 Viajar) is canonical; this is the chat door.
    The plaza, the bounty hunt, the NPCs you meet and which sects court you all
    follow current_continent — so choosing where to be is the point (Lei §1).
    Cost is spirit_stones (never jade — Lei §4) on its own cooldown.
    """
    from core.travel_engine import list_travel_destinations
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language or "pt")
        data = await list_travel_destinations(session, player, lang=lang)
        # MV-2 — Tiandao: eventos celestiais ativos no menu + ação de minerar
        # o meteoro DESTE continente (fix do review: o chat-only player tem de
        # poder agir, não só ler — Lei §1). Gated, fail-safe.
        try:
            from core.tiandao_engine import (
                EVENT_METEOR, METEOR_QI_COST, chat_event_lines, list_active_event_views,
            )
            _views = await list_active_event_views(session, player=player, lang=lang)
            _wl = await chat_event_lines(session, lang, views=_views)
            if _wl:
                data["world_event_lines"] = _wl
            if any(v["event_type"] == EVENT_METEOR
                   and v["continent"] == player.current_continent for v in _views):
                data["wev_mine_cost"] = METEOR_QI_COST
        except Exception:
            logger.exception("viajar tiandao lines failed")
        # TEC-4 — a Gruta do Legado ativa (gated no engine; OFF → None sem query).
        try:
            from core.legacy_cave_engine import active_cave_view
            _cv = await active_cave_view(session, lang, player=player)
            if _cv:
                data["legacy_cave"] = _cv
        except Exception:
            logger.exception("viajar legacy cave failed")
    await _render_travel_menu(update, lang, data)


async def travel_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `trv_*` callbacks + `cmd_viajar`. Returns True if handled."""
    from core.travel_engine import list_travel_destinations, do_travel
    from core.continent_engine import project_continent_identity

    query = update.callback_query
    if not query or not query.data:
        return False
    data = query.data

    if data == "cmd_viajar":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            payload = await list_travel_destinations(session, player, lang=lang)
            # MV-2 — Tiandao: eventos ativos no menu + ação de minerar (gated).
            try:
                from core.tiandao_engine import (
                    EVENT_METEOR, METEOR_QI_COST, chat_event_lines, list_active_event_views,
                )
                _views = await list_active_event_views(session, player=player, lang=lang)
                _wl = await chat_event_lines(session, lang, views=_views)
                if _wl:
                    payload["world_event_lines"] = _wl
                if any(v["event_type"] == EVENT_METEOR
                       and v["continent"] == player.current_continent for v in _views):
                    payload["wev_mine_cost"] = METEOR_QI_COST
            except Exception:
                logger.exception("cmd_viajar tiandao lines failed")
            # TEC-4 — a Gruta do Legado ativa (gated no engine; OFF → None).
            try:
                from core.legacy_cave_engine import active_cave_view
                _cv = await active_cave_view(session, lang, player=player)
                if _cv:
                    payload["legacy_cave"] = _cv
            except Exception:
                logger.exception("cmd_viajar legacy cave failed")
        await _render_travel_menu(update, lang, payload, edit=True)
        return True

    # TEC-4 — 🏮 entrar na Gruta do Legado pelo chat. O chat não tem poll de
    # duelo, então o padrão é o do rito TEC-3: start → auto-play → settle
    # INLINE → commit → resultado. UM answer por callback (lição A Volta).
    if data == "trv_lgc_go":
        async with get_session_factory()() as session:
            player_row = await _ensure_player(update, session)
            if not player_row:
                return True
            lang = normalize_lang(player_row.language or "pt")
            from core.legacy_cave_engine import start_cave_run
            res = await start_cave_run(session, player_row.telegram_id)
            if not res.get("ok"):
                reason = res.get("reason") or ""
                if reason == "wrong_continent":
                    msg = t(lang, "lgc_err_wrong_continent",
                            emoji=res.get("continent_emoji", ""))
                elif reason == "already_attempted":
                    msg = t(lang, "lgc_err_attempted")
                elif reason == "duel_already_active":
                    msg = t(lang, "lgc_err_busy")
                elif reason == "hp_depleted":
                    msg = t(lang, "lgc_err_hp")
                else:  # no_cave / lgc_off / internal_error
                    msg = t(lang, "lgc_err_gone")
                await safe_answer(query, msg, show_alert=True)
                return True
            await safe_answer(query, t(lang, "lgc_chat_enter_toast"), show_alert=False)
            from database.models import DuelSession as _DS
            duel = (await session.execute(
                select(_DS).where(_DS.id == res["duel_id"])
            )).scalar_one_or_none()
            if duel is None:
                await _travel_safe_edit(query, t(lang, "lgc_err_gone"), None)
                return True
            try:
                from core.duel_engine import apply_post_duel_effects
                from core.sect_trial_engine import auto_play_trial_duel
                await auto_play_trial_duel(session, duel, int(player_row.telegram_id))
                await apply_post_duel_effects(session, duel)
            except Exception:
                logger.exception("legacy cave auto-play failed (player_id=%s)",
                                 player_row.telegram_id)
                await session.rollback()
                await _travel_safe_edit(query, t(lang, "lgc_err_gone"), None)
                return True
            won = (duel.winner_id == player_row.telegram_id and duel.state == "finished")
            # O resultado vive no marker do settle (pve_settled → payload).
            _pay = {}
            for _e in reversed(duel.action_log or []):
                if isinstance(_e, dict) and _e.get("type") == "pve_settled":
                    _pay = _e.get("payload") or {}
                    break
            await session.commit()
            npc = res.get("npc", "?")
            if won:
                parts = [t(lang, "lgc_chat_won", npc=npc,
                           stones=int(_pay.get("stones") or 0))]
                if _pay.get("materials"):
                    parts.append(t(lang, "lgc_chat_won_mat"))
                if _pay.get("bag_full"):
                    # Lei §1: anel cheio = material perdido é DITO, nunca mudo.
                    parts.append(t(lang, "lgc_chat_won_bagfull"))
                if _pay.get("dao_fragments"):
                    parts.append(t(lang, "lgc_chat_won_frag", n=_pay["dao_fragments"]))
                art = _pay.get("art")
                if art:
                    parts.append(t(lang, "lgc_chat_won_art",
                                   emoji=art.get("emoji", ""), name=art.get("name", "")))
                elif _pay.get("already_has_art"):
                    parts.append(t(lang, "lgc_chat_won_dupe"))
                elif _pay.get("art_missed"):
                    _m = _pay["art_missed"]
                    parts.append(t(lang, "lgc_chat_won_missed",
                                   clears=_m.get("clears", 1), pity=_m.get("pity_at", 3)))
                # TEC-5 — "A Noite de Sangue viu você": key CONDICIONAL, só chega
                # a quem atravessou o Rito e venceu NA tumba dela.
                if _pay.get("xueye_notice"):
                    parts.append(t(lang, "fpd_chat_xueye_seen"))
                # TEC-5 — e o preço do que ele usou lá dentro (karma + anos).
                _fc = _pay.get("forbidden_cost")
                if _fc:
                    from handlers.forbidden import forbidden_cost_line
                    parts.append(forbidden_cost_line(lang, _fc))
                head = "\n".join(parts)
            else:
                head = t(lang, "lgc_chat_lost", npc=npc)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                f"🧭 {t(lang, 'travel_title')}", callback_data="cmd_viajar")]])
            await _travel_safe_edit(query, head, kb)
            return True

    # MV-2 — ⛏️ minerar o Meteoro Celestial pelo chat (fix do review: paridade
    # de AÇÃO com o mapa v2). UM answer só, com o resultado (lição safe_answer:
    # answer vazio antes do alerta = alerta engolido). NB: checado ANTES do
    # trv_d_ (startswith "trv_" mas não "trv_d_"/"trv_go_" — sem colisão).
    if data == "trv_wev_mine":
        async with get_session_factory()() as session:
            player_row = await _ensure_player(update, session)
            if not player_row:
                return True
            lang = normalize_lang(player_row.language or "pt")
            locked = (await session.execute(
                select(Player).where(Player.telegram_id == player_row.telegram_id).with_for_update()
            )).scalar_one_or_none()
            if not locked:
                return True
            from core.tiandao_engine import mine_meteor
            result = await mine_meteor(session, locked)
            if result.get("ok"):
                # Feedback do jogador (2026-07-23): o alerta dizia só "{n}x
                # material nativo" — nunca O QUE veio (o mini-app já nomeia
                # via loot_named_items). Resolve os nomes AQUI (mesmo helper
                # do mini-app — UM helper por lógica) e lista no alerta.
                loot_txt = ""
                try:
                    from core.webserver import _resolve_bag_items
                    _named = await _resolve_bag_items(session, result.get("loot") or {})
                    _parts = [f"{it.get('emoji') or ''} {it.get('count')}× {it.get('name')}".strip()
                              for it in _named]
                    _stones = (result.get("loot") or {}).get("stones")
                    if _stones:
                        _parts.insert(0, f"🪨 {int(_stones)}")
                    loot_txt = ", ".join(p for p in _parts if p)
                except Exception:
                    logger.exception("trv_wev_mine loot name resolve failed")
                await session.commit()
                if loot_txt:
                    await safe_answer(query, t(lang, "wev_chat_mine_ok_loot", loot=loot_txt),
                                      show_alert=True)
                else:
                    await safe_answer(query, t(lang, "wev_chat_mine_ok", n=result.get("hits", 1)),
                                      show_alert=True)
            else:
                reason = result.get("reason")
                if reason == "wev_cooldown":
                    h = max(1, int((result.get("remaining_seconds") or 0) + 3599) // 3600)
                    msg = t(lang, "wev_chat_mine_cooldown", time=f"{h}h")
                elif reason == "wev_no_qi":
                    msg = t(lang, "wev_chat_mine_no_qi", cost=result.get("qi_cost", 0))
                elif reason == "wev_wrong_continent":
                    cname = t(lang, f"continent_{result.get('continent', '')}")
                    msg = t(lang, "dng_wrong_continent",
                            emoji=result.get("continent_emoji", ""), name=cname)
                else:
                    msg = t(lang, "wev_chat_gone")
                await safe_answer(query, msg, show_alert=True)
        return True

    # Destination detail + cost/cooldown disclosure BEFORE confirming (Lei §1).
    if data.startswith("trv_d_"):
        await safe_answer(query)
        key = data[len("trv_d_"):]
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            payload = await list_travel_destinations(session, player, lang=lang)
        dst = next((x for x in payload.get("destinations", []) if x.get("key") == key), None)
        if not dst:
            await _travel_safe_edit(query, t(lang, "travel_failed"))
            return True
        lines = [f"{dst.get('emoji', '🗺️')} {dst.get('name', '')}", dst.get("specialty", ""), ""]
        # MV-3 — Estados Regionais: a linha do estado do destino ("🏚️ Sitiada —
        # estradas caras, mercados nervosos"). Payload-gated (flag OFF → ausente).
        if dst.get("region_state_line"):
            lines.append(dst["region_state_line"])
        # MV-6 — Reputação: como este destino te recebe (payload-gated).
        if dst.get("region_rep_line"):
            lines.append(f"{t(lang, 'rep_travel_prefix')} {dst['region_rep_line']}")
        # MV-8 — o aviso ANTES do tap pago (Lei §1). Só o mini-app o mostrava:
        # o jogador de chat pagava as pedras e o cooldown de 4h e só descobria
        # a emboscada na chegada — enquanto o comentário do engine já afirmava
        # "o mapa já avisou".
        if dst.get("region_state_occupant"):
            lines.append(dst["region_state_occupant"])
        if dst.get("hunted"):
            lines.append(t(lang, "jh_hunted_chip", n=dst["hunted"]))
        tags = ", ".join(tg.get("label", "") for tg in dst.get("native_tags", []))
        if tags:
            lines.append(f"🏷️ {tags}")
        line_presence = f"👤 {dst.get('presence', 0)} · 🤖 {dst.get('npc_count', 0)}"
        if dst.get("bounty_count"):
            line_presence += f" · 🏴 {dst.get('bounty_count')}"
        lines.append(line_presence)
        lines += [
            "",
            f"🪨 {t(lang, 'travel_cost_label')}: {dst.get('cost', 0)}",
            f"⏱️ {t(lang, 'travel_cooldown_label')}: {_fmt_travel_dur(payload.get('cooldown_full_ms'))}",
        ]
        # MV-2 — estrada fechada: o custo acima já vem inflado (+50%); esta
        # linha DIZ porquê (Lei §1 — disclosure, nunca um preço mudo).
        if dst.get("event_penalty"):
            lines.append(t(lang, "wev_travel_penalty_note"))
        rows = []
        if dst.get("eligible"):
            lines += ["", f"✨ {t(lang, 'travel_changes_note')}", f"🔒 {t(lang, 'travel_wipe_teaser')}"]
            rows.append([InlineKeyboardButton(f"🧭 {t(lang, 'travel_confirm')}", callback_data=f"trv_go_{key}")])
        else:
            rline = _travel_reason_line(lang, dst, payload.get("cooldown_remaining_ms"))
            if rline:
                lines += ["", f"🔒 {rline}"]
        rows.append([InlineKeyboardButton(t(lang, "travel_back"), callback_data="cmd_viajar")])
        await _travel_safe_edit(query, "\n".join(lines), InlineKeyboardMarkup(rows))
        return True

    # Execute: lock the player row FOR UPDATE (no lost-update on the stone debit).
    if data.startswith("trv_go_"):
        await safe_answer(query)
        key = data[len("trv_go_"):]
        async with get_session_factory()() as session:
            player = (await session.execute(
                select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
            )).scalar_one_or_none()
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            result = await do_travel(session, player, key)
            await session.commit()
        if result.get("ok"):
            ident = project_continent_identity(key, lang)
            arrival = (
                f"🧭 {t(lang, 'travel_arrived', continent=ident.get('name', ''))}\n\n"
                f"✨ {t(lang, 'travel_changes_note')}"
            )
            # MV-5 — ao chegar, o mundo pode te chamar: a oferta ride no
            # resultado do do_travel (gated no engine; ausente = nada muda).
            sty = result.get("storylet_offer")
            if sty:
                arrival += (
                    f"\n\n📜 {t(lang, 'sty_plaza_call', giver=sty.get('giver', '?'), name=sty.get('name', ''))}\n"
                    f"{t(lang, 'sty_plaza_call_hint')}"
                )
            # MV-8 — quem te procurava aqui te encontra na CHEGADA. O mapa já
            # avisou (chip 🗡️), então nada disto é surpresa (Lei §1). Os três
            # botões viajam juntos: um encontro sem saída seria o void.
            _amb = result.get("jianghu_ambush")
            if _amb:
                _amb_lines, _amb_rows = jianghu_ambush_block(lang, _amb)
                await _travel_safe_edit(query, arrival + "\n" + "\n".join(_amb_lines),
                                        InlineKeyboardMarkup(_amb_rows))
                return True
            await _travel_safe_edit(query, arrival)
        else:
            r = result.get("reason")
            if r == "not_enough_stones":
                msg = t(lang, "travel_not_enough_stones", cost=result.get("cost", 0))
            elif r == "on_cooldown":
                msg = t(lang, "travel_on_cooldown", time=_fmt_travel_dur(result.get("cooldown_remaining_ms")))
            elif r == "locked_demonic":
                msg = t(lang, "travel_locked_demonic")
            elif r == "already_here":
                msg = t(lang, "travel_already_here")
            else:
                msg = t(lang, "travel_failed")
            await _travel_safe_edit(query, f"🔒 {msg}")
        return True

    return False


# ── Onda 5 — Reinos Exploráveis (chat parity; mini-app is canonical) ──────────

_EXPLORE_RISK_EMOJI = {"safe": "✨", "danger": "⚠️", "choice": "🔀", "ominous": "☠️"}


def _explore_loot_line(lang, projected):
    """One-line loot disclosure from a projected bag {stones, items:[{name,qty}]}."""
    projected = projected or {}
    parts = []
    if projected.get("stones"):
        parts.append(f"🪨 {projected['stones']}")
    for it in (projected.get("items") or [])[:8]:
        parts.append(f"{it.get('name', '?')} x{it.get('qty', 0)}")
    return " · ".join(parts) if parts else t(lang, "dng_bag_empty")


def _explore_outcome_text(lang, res):
    """Localized banner for an advance/retreat result (includes loot)."""
    # A Hidden-Monster duel (started in the mini-app) is still unsettled — the
    # chat has no live arena, so advancing/retreating is blocked. Tell the player
    # honestly instead of falsely claiming progress (Lei §1).
    if res.get("redirect_to_duel") or res.get("reason") == "duel_in_progress":
        return t(lang, "explore_finish_duel")
    if not res.get("ok"):
        return {
            "qi_insufficient": t(lang, "explore_no_qi", cost=res.get("qi_cost", 0)),
            "cooldown": t(lang, "explore_cooldown"),
            "hp_depleted": t(lang, "explore_hp_depleted"),
            "meditation_too_deep": t(lang, "explore_meditation"),
            "stale": t(lang, "explore_stale"),
        }.get(res.get("reason"), t(lang, "explore_failed"))
    typ = res.get("type")
    # Onda 5 Fase 3 — Ecos Míticos: chat auto-resolves the encounter as a tough
    # fight (no live arena), but still narrates the reveal + grants the title on
    # a win (the engine fired the achievement). The cinematic mirror duel is mini-app.
    mythic_reveal = ""
    if res.get("mythic_key") and res.get("mythic_reveal_key"):
        mythic_reveal = "👁️‍🗨️ " + t(lang, res["mythic_reveal_key"])
    if typ == "trash" and res.get("died"):
        msg = "💀 " + t(lang, "explore_died")
        if mythic_reveal:
            msg = mythic_reveal + "\n\n" + msg
        s = res.get("survivors") or {}
        if s.get("total_items") or s.get("stones"):
            msg += "\n🎒 " + _explore_loot_line(lang, s)
        return msg
    parts = []
    if mythic_reveal:
        parts.append(mythic_reveal)
    if res.get("mythic_key") and res.get("won"):
        parts.append("🏆 " + t(lang, "explore_mythic_won"))
        if res.get("mythic_title"):
            parts.append("🏷️ " + t(lang, "explore_mythic_title_earned", title=res["mythic_title"]))
    elif typ == "fork" and res.get("result_key"):
        parts.append(t(lang, res["result_key"]))
    elif typ == "trash" and res.get("won"):
        parts.append("⚔️ " + t(lang, "explore_won"))
    elif typ == "cache":
        parts.append("🌿 " + t(lang, "explore_cache"))
    g = res.get("gained") or {}
    if g.get("total_items") or g.get("stones"):
        parts.append("🎁 " + _explore_loot_line(lang, g))
    # MV-5 — o encontro raro do explore: alguém te achou na mata (a oferta já
    # foi mintada pelo engine; aqui só a narração + CTA — ausente = nada muda).
    sty = res.get("storylet_offer")
    if sty:
        parts.append(f"📜 {t(lang, 'sty_plaza_call', giver=sty.get('giver', '?'), name=sty.get('name', ''))}")
        parts.append(t(lang, "sty_plaza_call_hint"))
    return "\n".join(parts) if parts else t(lang, "explore_advanced")


async def _render_explore_menu(update, lang, sd, banner=None, edit=False):
    """The Divine Sense reading: depth + bag + a button per direction + retreat."""
    lines = [f"🧭 {t(lang, 'explore_title')}", t(lang, "explore_intro"), ""]
    if banner:
        lines += [banner, ""]
    lines.append(t(lang, "explore_depth", depth=sd.get("depth", 0)))
    if sd.get("has_bag"):
        lines.append(f"🎒 {_explore_loot_line(lang, sd.get('bag', {}))}")
    lines.append(t(lang, "explore_qi", qi=int(sd.get("qi", 0))))
    lines += ["", f"🔒 {t(lang, 'explore_wipe_teaser')}"]

    rows = []
    for d in sd.get("directions", []):
        risk = _EXPLORE_RISK_EMOJI.get(d.get("risk"), "🧭")
        label = f"{d.get('emoji', '🧭')} {d.get('node_name', '?')} {risk} · 🌀{d.get('qi_cost', 0)}"
        rows.append([InlineKeyboardButton(label[:60], callback_data=f"xpl_a_{d['idx']}")])
    if sd.get("has_bag"):
        rows.append([InlineKeyboardButton(f"🏃 {t(lang, 'explore_retreat')}", callback_data="xpl_ret")])
    kb = InlineKeyboardMarkup(rows) if rows else None
    text = "\n".join(lines)
    if edit and update.callback_query:
        await _travel_safe_edit(update.callback_query, text, kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def _render_explore_fork(update, lang, res, idx):
    """A Karmic-Crossroads-style moral fork mid-exploration."""
    lines = [f"🔀 {t(lang, res.get('prompt_key', 'explore_failed'))}", ""]
    rows = []
    for c in res.get("choices", []):
        kd = int(c.get("karma_delta", 0))
        chip = f" ({'+' if kd > 0 else ''}{kd}⚖️)" if kd else ""
        rows.append([InlineKeyboardButton(
            f"{t(lang, c['label_key'])}{chip}"[:60],
            callback_data=f"xpl_f_{idx}_{c['id']}",
        )])
    rows.append([InlineKeyboardButton(t(lang, "explore_back"), callback_data="cmd_explorar")])
    await _travel_safe_edit(update.callback_query, "\n".join(lines), InlineKeyboardMarkup(rows))


async def explorar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Onda 5 — /explorar — Reinos Exploráveis (chat parity).

    The mini-app (🧭 Exploração tab) is canonical; this is the chat door. Explore
    the continent you are in by Divine Sense (神識): pick a direction, gather
    MATERIALS (never techniques — Lei §5), and choose safe return or go deeper.
    ADDITIVE — /dungeons is untouched. In chat, Hidden Monsters auto-resolve as a
    tough fight (the cinematic duel lives in the mini-app).
    """
    from core.exploration_engine import scan as explore_scan
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language or "pt")
        sd = await explore_scan(session, player, lang=lang)
    await _render_explore_menu(update, lang, sd)


async def _maybe_send_ambush(update: Update, lang: str, res: dict) -> None:
    """MV-8 — a emboscada do explore no chat, como MENSAGEM PRÓPRIA.

    O menu do explore é re-editado com o teclado dele; enfiar os 3 botões do
    encontro ali obrigaria a fundir dois teclados de vidas diferentes. O
    encontro é um momento próprio — e assim ele NUNCA some quando o menu é
    re-renderizado. Sem payload (flag OFF) → função muda."""
    amb = (res or {}).get("jianghu_ambush")
    if not amb:
        return
    try:
        lines, rows = jianghu_ambush_block(lang, amb)
        await update.effective_message.reply_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))
    except Exception:
        logger.exception("explore jianghu ambush render failed")


async def explore_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `xpl_*` callbacks + `cmd_explorar`. Returns True if handled."""
    from core.exploration_engine import scan as explore_scan, advance as explore_advance, retreat as explore_retreat
    query = update.callback_query
    if not query or not query.data:
        return False
    data = query.data
    uid = update.effective_user.id

    if data == "cmd_explorar":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            sd = await explore_scan(session, player, lang=lang)
        await _render_explore_menu(update, lang, sd, edit=True)
        return True

    if data.startswith("xpl_a_"):
        await safe_answer(query)
        try:
            idx = int(data[len("xpl_a_"):])
        except (TypeError, ValueError):
            return True
        async with get_session_factory()() as session:
            player = (await session.execute(
                select(Player).where(Player.telegram_id == uid).with_for_update()
            )).scalar_one_or_none()
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            res = await explore_advance(session, player, direction_idx=idx, lang=lang, allow_duel=False)
            await session.commit()
        if res.get("needs_choice"):
            await _render_explore_fork(update, lang, res, idx)
            return True
        banner = _explore_outcome_text(lang, res)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            lang = normalize_lang(player.language or "pt")
            sd = await explore_scan(session, player, lang=lang)
        await _render_explore_menu(update, lang, sd, banner=banner, edit=True)
        await _maybe_send_ambush(update, lang, res)
        return True

    if data.startswith("xpl_f_"):
        await safe_answer(query)
        idx_str, _, choice = data[len("xpl_f_"):].partition("_")
        try:
            idx = int(idx_str)
        except (TypeError, ValueError):
            return True
        async with get_session_factory()() as session:
            player = (await session.execute(
                select(Player).where(Player.telegram_id == uid).with_for_update()
            )).scalar_one_or_none()
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            res = await explore_advance(session, player, direction_idx=idx, choice_id=choice, lang=lang, allow_duel=False)
            await session.commit()
        banner = _explore_outcome_text(lang, res)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            lang = normalize_lang(player.language or "pt")
            sd = await explore_scan(session, player, lang=lang)
        await _render_explore_menu(update, lang, sd, banner=banner, edit=True)
        await _maybe_send_ambush(update, lang, res)
        return True

    if data == "xpl_ret":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = (await session.execute(
                select(Player).where(Player.telegram_id == uid).with_for_update()
            )).scalar_one_or_none()
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            res = await explore_retreat(session, player, lang=lang)
            await session.commit()
        if not res.get("ok"):
            banner = _explore_outcome_text(lang, res)   # e.g. duel_in_progress
        else:
            banner = f"🏃 {t(lang, 'explore_retreated')}"
            b = res.get("banked") or {}
            if b.get("total_items") or b.get("stones"):
                banner += "\n🎒 " + _explore_loot_line(lang, b)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            lang = normalize_lang(player.language or "pt")
            sd = await explore_scan(session, player, lang=lang)
        await _render_explore_menu(update, lang, sd, banner=banner, edit=True)
        return True

    return False


# ══════════════════════════════════════════════════════════════════════════
# Onda 5 Fase 2 — /caverna (洞府) + /formacoes (阵法) — chat parity doors.
# The mini-app (🏯 Caverna) is canonical; chat is the legacy door. Callbacks:
# cmd_caverna / cav_est / cav_claim / cav_clr / cav_set_<id> (slot) and
# cmd_formacoes / frm_c_<id> (craft) / frm_a_<id> (activate on the body).
# `cav_`/`frm_` don't prefix-collide with sect_/wsect_/trv_/xpl_.
# Every mutating step row-locks the player FOR UPDATE (the xpl_ pattern).
# ══════════════════════════════════════════════════════════════════════════

def _fmt_duration_min(minutes) -> str:
    m = int(minutes or 0)
    if m < 60:
        return f"{m}min"
    if m % 60 == 0:
        return f"{m // 60}h"
    return f"{m // 60}h{m % 60:02d}"


def _fmt_formation_effect(lang, etype, value) -> str:
    """'+10% Ataque' / '−35% perda na morte' — one line, server-resolved."""
    label = t(lang, f"formation_effect_{etype}")
    if etype == "explore_protection":
        return t(lang, "formation_fx_prot", pct=int(round(float(value or 0) * 100)), label=label)
    pct = int(round((float(value or 1.0) - 1.0) * 100))
    return t(lang, "formation_fx_mult", pct=pct, label=label)


def _cavern_reason_text(lang, res) -> str:
    # already_active / slot_occupied carry remaining_ms (+ source) from the
    # engine — append them so the player knows WHAT blocks and for HOW LONG
    # (Lei §1; review: a static "espere expirar" hides a 14h pill blocker).
    def _blocked_suffix():
        parts = []
        ms = int(res.get("remaining_ms", 0) or 0)
        if ms > 0:
            parts.append(f"⏳ {_fmt_duration_min(max(1, ms // 60000))}")
        src = res.get("source")
        if src:
            if str(src).startswith("formation:"):
                src = t(lang, f"formation_name_{str(src)[len('formation:'):]}")
            parts.append(str(src))
        return f" ({' · '.join(parts)})" if parts else ""

    reason = res.get("reason")
    if reason == "already_active":
        return t(lang, "formation_already_active") + _blocked_suffix()
    if reason == "slot_occupied":
        return t(lang, "cavern_slot_occupied") + _blocked_suffix()
    return {
        "not_enough_stones": t(lang, "formation_no_stones", cost=res.get("cost_stones", 0)),
        "not_enough_materials": t(lang, "formation_no_materials"),
        "realm_too_low": t(lang, "formation_realm_low", realm=res.get("min_realm", 0)),
        "not_owned": t(lang, "formation_not_owned"),
        "formation_not_found": t(lang, "formation_not_found"),
        "already_established": t(lang, "cavern_already"),
        "no_cavern": t(lang, "cavern_none"),
        "nothing_accrued": t(lang, "cavern_nothing_accrued"),
        "qi_full": t(lang, "cavern_qi_full"),
        "not_cavern_type": t(lang, "cavern_not_cavern_type"),
    }.get(reason, t(lang, "explore_failed"))


async def _render_cavern_menu(update, lang, cv, fl, banner=None, edit=False):
    """The cavern: idle bar + claim + the Formação slot (+ establish door)."""
    lines = [f"🏯 {t(lang, 'cavern_title')}", t(lang, "cavern_intro"), ""]
    if banner:
        lines += [banner, ""]
    rows = []
    if not cv.get("has_cavern"):
        lines.append(t(lang, "cavern_none_yet"))
        mats = " · ".join(
            f"{m.get('name', '?')} x{m.get('qty', 0)} ({m.get('owned', 0)})"
            for m in (cv.get("establish_materials") or [])
        )
        lines.append(t(lang, "cavern_establish_cost",
                       stones=cv.get("establish_cost_stones", 0)) + (f"\n{mats}" if mats else ""))
        lines.append(t(lang, "cavern_rate_preview",
                       rate=int(cv.get("rate_per_hour_preview", 0)),
                       cap=int(cv.get("cap_hours", 0))))
        if cv.get("can_establish"):
            rows.append([InlineKeyboardButton(f"⛏️ {t(lang, 'cavern_establish_btn')}",
                                              callback_data="cav_est")])
    else:
        lines.append(t(lang, "cavern_status_line",
                       continent=cv.get("cavern_continent_name") or cv.get("cavern_continent", "?"),
                       rate=int(cv.get("rate_per_hour", 0))))
        lines.append(t(lang, "cavern_idle_line",
                       accrued=int(cv.get("accrued_qi", 0)),
                       cap=int(cv.get("cap_qi", 0))) +
                     (" ⏸️" if cv.get("at_cap") else ""))
        # A full qi tank hides the claim button below — say WHY (Lei §1; the
        # engine's qi_full refusal is unreachable when the button never shows).
        if cv.get("qi_full") and int(cv.get("accrued_qi", 0)) >= 1:
            lines.append(f"⚠️ {t(lang, 'cavern_qi_full')}")
        slot = cv.get("slot")
        if slot:
            fx = _fmt_formation_effect(lang, slot.get("effect_type"), slot.get("effect_value"))
            rem = int(slot.get("remaining_ms", 0) / 60000)
            state = t(lang, "cavern_slot_expired") if slot.get("expired") else \
                t(lang, "cavern_slot_remaining", minutes=rem)
            lines.append(f"🔯 {slot.get('emoji', '')} {t(lang, slot.get('name_key', ''))} — {fx} · {state}")
            rows.append([InlineKeyboardButton(f"🧹 {t(lang, 'cavern_clear_btn')}",
                                              callback_data="cav_clr")])
        else:
            lines.append(t(lang, "cavern_slot_empty"))
            # Offer the cavern-compatible Formações the player OWNS (≤4 rows).
            compatible = [f for f in (fl.get("formations") or [])
                          if f.get("cavern_compatible") and f.get("owned", 0) > 0][:4]
            for f in compatible:
                rows.append([InlineKeyboardButton(
                    f"🔯 {f.get('emoji', '')} {t(lang, f['name_key'])} x{f['owned']}"[:60],
                    callback_data=f"cav_set_{f['id']}")])
        if int(cv.get("claimable_qi", 0)) > 0:
            rows.append([InlineKeyboardButton(
                f"🌀 {t(lang, 'cavern_claim_btn', qi=int(cv.get('claimable_qi', 0)))}"[:60],
                callback_data="cav_claim")])
    lines += ["", t(lang, "cavern_open_miniapp")]
    rows.append([InlineKeyboardButton(f"🔯 {t(lang, 'formations_title')}",
                                      callback_data="cmd_formacoes")])
    kb = InlineKeyboardMarkup(rows) if rows else None
    text = "\n".join(lines)
    if edit and update.callback_query:
        await _travel_safe_edit(update.callback_query, text, kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def _render_formations_menu(update, lang, fl, banner=None, edit=False):
    """The Formação pouch + catalog: craft (frm_c_) and body-activate (frm_a_)."""
    lines = [f"🔯 {t(lang, 'formations_title')}", t(lang, "formations_intro"), ""]
    if banner:
        lines += [banner, ""]
    lines.append(t(lang, "formations_stones", stones=fl.get("stones", 0)))
    rows = []
    for f in fl.get("formations", []):
        fx = _fmt_formation_effect(lang, f.get("effect_type"), f.get("effect_value"))
        dur = _fmt_duration_min(f.get("duration_minutes"))
        own = f" · x{f['owned']}" if f.get("owned") else ""
        lock = "" if f.get("realm_ok") else " 🔒"
        cavern_chip = " 🏯" if f.get("cavern_compatible") else ""
        lines.append(f"{f.get('emoji', '🔯')} {t(lang, f['name_key'])} T{f.get('tier', 1)}"
                     f" — {fx} · {dur} · 🪨{f.get('cost_stones', 0)}{cavern_chip}{own}{lock}")
        # 印记 Marca do Traçado — a maestria DESTA formação, visível desde a 1ª
        # ativação (Lei §10). Só chega no payload com `marca_do_tracado` ON.
        _mk = f.get("marca")
        if _mk and _mk.get("line"):
            lines.append(f"   {_mk['line']}")
        btns = []
        if f.get("craftable"):
            btns.append(InlineKeyboardButton(
                f"⚒️ {t(lang, 'formation_craft_btn')} {f.get('emoji', '')}"[:60],
                callback_data=f"frm_c_{f['id']}"))
        if f.get("owned", 0) > 0 and f.get("realm_ok"):
            btns.append(InlineKeyboardButton(
                f"✨ {t(lang, 'formation_activate_btn')} {f.get('emoji', '')}"[:60],
                callback_data=f"frm_a_{f['id']}"))
        if btns:
            rows.append(btns)
    lines += ["", t(lang, "formations_hint"), t(lang, "cavern_open_miniapp")]
    rows.append([InlineKeyboardButton(f"🏯 {t(lang, 'cavern_title')}",
                                      callback_data="cmd_caverna")])
    kb = InlineKeyboardMarkup(rows) if rows else None
    text = "\n".join(lines)
    if edit and update.callback_query:
        await _travel_safe_edit(update.callback_query, text, kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def caverna_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Onda 5 Fase 2 — /caverna — the Personal Cavern 洞府 (chat parity door;
    the mini-app 🏯 tab is canonical). Capped idle qi + the Formação slot."""
    from core.cavern_engine import project_cavern
    from core.formation_engine import list_formations
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language or "pt")
        cv = await project_cavern(session, player, lang=lang)
        fl = await list_formations(session, player, lang=lang)
    await _render_cavern_menu(update, lang, cv, fl)


async def formacoes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Onda 5 Fase 2 — /formacoes — Matrizes/Formações 阵法 (chat parity door;
    the mini-app is canonical). Craft from exploration materials, activate on
    the body (timed buff) or hum it in the cavern via /caverna."""
    from core.formation_engine import list_formations
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language or "pt")
        fl = await list_formations(session, player, lang=lang)
    await _render_formations_menu(update, lang, fl)


async def cavern_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `cav_*`/`frm_*` callbacks + `cmd_caverna`/`cmd_formacoes`."""
    from core.cavern_engine import (
        claim_cavern, clear_cavern_formation, establish_cavern,
        project_cavern, set_cavern_formation,
    )
    from core.formation_engine import activate_on_body, craft_formation, list_formations
    query = update.callback_query
    if not query or not query.data:
        return False
    data = query.data
    uid = update.effective_user.id

    async def _rerender_cavern(banner=None):
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return
            lang = normalize_lang(player.language or "pt")
            cv = await project_cavern(session, player, lang=lang)
            fl = await list_formations(session, player, lang=lang)
        await _render_cavern_menu(update, lang, cv, fl, banner=banner, edit=True)

    async def _rerender_formations(banner=None):
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return
            lang = normalize_lang(player.language or "pt")
            fl = await list_formations(session, player, lang=lang)
        await _render_formations_menu(update, lang, fl, banner=banner, edit=True)

    async def _locked_write(fn, *args):
        """Row-lock the player FOR UPDATE, run the engine write, commit.
        Returns (lang, result) — the xpl_ mutating-step pattern."""
        async with get_session_factory()() as session:
            player = (await session.execute(
                select(Player).where(Player.telegram_id == uid).with_for_update()
            )).scalar_one_or_none()
            if not player:
                return None, None
            lang = normalize_lang(player.language or "pt")
            res = await fn(session, player, *args)
            await session.commit()
            return lang, res

    if data == "cmd_caverna":
        await safe_answer(query)
        await _rerender_cavern()
        return True

    if data == "cmd_formacoes":
        await safe_answer(query)
        await _rerender_formations()
        return True

    if data == "cav_est":
        await safe_answer(query)
        lang, res = await _locked_write(establish_cavern)
        if res is None:
            return True
        banner = (f"⛏️ {t(lang, 'cavern_established', stones=res.get('cost_stones', 0))}"
                  if res.get("ok") else _cavern_reason_text(lang, res))
        await _rerender_cavern(banner)
        return True

    if data == "cav_claim":
        await safe_answer(query)
        lang, res = await _locked_write(claim_cavern)
        if res is None:
            return True
        if res.get("ok"):
            banner = f"🌀 {t(lang, 'cavern_claimed', qi=int(res.get('claimed_qi', 0)))}"
            if res.get("truncated"):
                banner += f"\n⚠️ {t(lang, 'cavern_claim_truncated')}"
            frag = res.get("dao_fragment")
            if frag and frag.get("law_name"):
                banner += f"\n☯️ {t(lang, 'cavern_dao_fragment', law=frag['law_name'])}"
        else:
            banner = _cavern_reason_text(lang, res)
        await _rerender_cavern(banner)
        return True

    if data == "cav_clr":
        await safe_answer(query)
        lang, res = await _locked_write(clear_cavern_formation)
        if res is None:
            return True
        banner = None
        if res.get("cleared"):
            banner = f"🧹 {t(lang, 'cavern_cleared')}"
            if res.get("settled_qi", 0) > 0:
                banner += f" · 🌀 +{int(res['settled_qi'])}"
        await _rerender_cavern(banner)
        return True

    if data.startswith("cav_set_"):
        await safe_answer(query)
        fid = safe_parse_callback_int(data, "cav_set_")
        if fid is None:
            return True
        lang, res = await _locked_write(set_cavern_formation, fid)
        if res is None:
            return True
        if res.get("ok"):
            banner = f"🔯 {t(lang, 'cavern_formation_set')}"
            if res.get("settled_qi", 0) > 0:
                banner += f" · 🌀 +{int(res['settled_qi'])}"
        else:
            banner = _cavern_reason_text(lang, res)
        await _rerender_cavern(banner)
        return True

    if data.startswith("frm_c_"):
        await safe_answer(query)
        fid = safe_parse_callback_int(data, "frm_c_")
        if fid is None:
            return True
        lang, res = await _locked_write(craft_formation, fid)
        if res is None:
            return True
        banner = (f"⚒️ {t(lang, 'formation_crafted')}"
                  if res.get("ok") else _cavern_reason_text(lang, res))
        # 印记 — o Sulco poupou, e diz quanto (custo invisível = custo nenhum).
        if res.get("ok") and res.get("marca_saved_stones"):
            banner += f" · {t(lang, 'marca_craft_saved', stones=int(res['marca_saved_stones']))}"
        await _rerender_formations(banner)
        return True

    if data.startswith("frm_a_"):
        await safe_answer(query)
        fid = safe_parse_callback_int(data, "frm_a_")
        if fid is None:
            return True
        lang, res = await _locked_write(activate_on_body, fid)
        if res is None:
            return True
        banner = (f"✨ {t(lang, 'formation_activated_body', duration=_fmt_duration_min(res.get('duration_minutes')))}"
                  if res.get("ok") else _cavern_reason_text(lang, res))
        # 印记 — antes→depois SEMPRE (Lei §10: avanço sem número subindo = nada),
        # e o degrau novo celebrado no momento em que cai.
        _mk = res.get("marca") if res.get("ok") else None
        if _mk:
            banner += ("\n🔯 " + t(lang, "marca_progress_delta",
                                   before=_mk.get("before", 0), after=_mk.get("after", 0)))
            if _mk.get("tier_up"):
                banner += "\n" + t(lang, f"marca_up_{_mk['tier_up']}", name=_mk.get("tier_name") or "")
            if _mk.get("title_granted"):
                banner += "\n🏆 " + t(lang, "marca_title_granted", title=_mk["title_granted"])
        await _rerender_formations(banner)
        return True

    return False


async def _resolve_recruiter_encounter(session, pid, pending_id, now):
    """Return a live (unresolved, unexpired) recruiter row for this player, or None."""
    return (await session.execute(
        select(WorldSectRecruiterPending).where(
            WorldSectRecruiterPending.id == pending_id,
            WorldSectRecruiterPending.player_id == pid,
            WorldSectRecruiterPending.accepted_at.is_(None),
            WorldSectRecruiterPending.declined_at.is_(None),
            WorldSectRecruiterPending.expires_at > now,
        )
    )).scalar_one_or_none()


async def _render_trial_intro(query, lang, pend, sname, emoji):
    """v16.4b — show the Elder's challenge screen (the trial gate).

    Replaces the old instant-join. The cultivator now faces the Elder before
    the house takes them in (Lei §1 — affinity shown; defeat = cooldown, not a
    dead-end).
    """
    text = "\n".join([
        f"{emoji} *{sname}*",
        "",
        t(lang, "wsect_trial_intro", emoji=emoji, sect=sname, score=int(pend.affinity_score or 0)),
    ])
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "wsect_trial_face_btn"), callback_data=f"wsect_trial_{pend.id}")],
        [InlineKeyboardButton(t(lang, "wsect_btn_decline"), callback_data=f"wsect_decline_{pend.id}")],
    ])
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


def _contrib_bar(have: int, need: int, width: int = 10) -> str:
    """A tiny text progress bar for the contribution-to-next-rank line."""
    if need <= 0:
        return "█" * width
    filled = max(0, min(width, int(width * have / need)))
    return "█" * filled + "░" * (width - filled)


async def _render_sect_library(query, session, pid: int, lang: str) -> None:
    """v16.4c — the Sect Library drill-in: the house's 5 signature arts, each
    flagged learned / unlockable (rank met) / locked, with learn buttons."""
    from core.world_sects_engine import get_sect_hall_state
    hall = await get_sect_hall_state(session, pid, lang)
    if not hall.get("in_sect"):
        await query.message.edit_text(t(lang, "wsect_recruiter_expired"), parse_mode="Markdown")
        return
    sect = hall.get("sect") or {}
    lines = [f"📜 *{t(lang, 'wsect_lib_title', sect=sect.get('name', ''))}*", "", t(lang, "wsect_lib_intro"), ""]
    kb_rows = []
    library = hall.get("library", [])
    if not library:
        lines.append(t(lang, "wsect_lib_empty"))
    for e in library:
        name, tier = e["name"], e["tier"]
        if e["learned"]:
            status = t(lang, "wsect_lib_learned")
        elif e["unlocked"]:
            status = t(lang, "wsect_lib_unlockable")
        else:
            status = t(lang, "wsect_lib_locked", rank=t(lang, e["rank_key"]))
        lines.append(f"{e['emoji']} *{name}* · T{tier} — {status}")
        if e["unlocked"] and not e["learned"]:
            kb_rows.append([InlineKeyboardButton(
                t(lang, "wsect_lib_learn_btn", name=name), callback_data=f"wsect_learn_{e['tech_id']}")])
    # TEC-1 — as estantes novas vivem no /biblioteca (gated; OFF byte-idêntico).
    try:
        from core.sect_library_engine import biblioteca_on
        if biblioteca_on():
            lines.append("")
            lines.append(t(lang, "lib_shelves_hint"))
            kb_rows.append([InlineKeyboardButton(
                t(lang, "lib_btn_shelves"), callback_data="lib_menu")])
    except Exception:
        logger.debug("library shelves hint failed", exc_info=True)
    kb_rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita_ancia")])
    try:
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(kb_rows))
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


async def _render_sect_quests(query, session, pid: int, lang: str) -> None:
    """v16.4c — the member-gated Sect Quests drill-in. Completed quests show a
    claim button; moral-fork quests show the Karmic Crossroads picker (reusing
    the existing `qch_` flow), so the same engine handles the choice."""
    from core.quest_engine import ensure_sect_quests, get_player_sect_quests
    from core.quest_choice_engine import get_quest_choices
    await ensure_sect_quests(session, pid)
    rows = await get_player_sect_quests(session, pid)
    await session.commit()

    lines = [f"⚔️ *{t(lang, 'wsect_quests_title')}*", ""]
    kb_rows = []
    if not rows:
        lines.append(t(lang, "wsect_quests_empty"))
    for pq, q in rows:
        emoji = q.emoji or "🏯"
        # Pedra 2 wave 2 — localize the quest name via the optional per-id key
        # (q_<id>_name in locales/*.json), falling back to the stored name for any
        # sect quest without a localized override (silent, no log spam).
        qname = catalog_name(lang, "q", q)
        if pq.claimed:
            lines.append(t(lang, "wsect_quest_status_claimed", emoji=emoji, name=qname))
        elif pq.is_completed:
            lines.append(t(lang, "wsect_quest_status_done", emoji=emoji, name=qname))
            if q.choices:
                # Hotfix "A Volta" 2026-07-07 (#7 [jogador]) — os botões de escolha
                # apareciam sem NENHUM contexto; dá a linha da Encruzilhada.
                lines.append(t(lang, "qc_prompt"))
                for c in get_quest_choices(lang, q):
                    kb_rows.append([InlineKeyboardButton(
                        c.get("label") or c["id"], callback_data=f"qch_{q.id}_{c['id']}")])
            else:
                kb_rows.append([InlineKeyboardButton(
                    t(lang, "wsect_quests_claim_btn", name=qname), callback_data=f"wsect_qc_{q.id}")])
        else:
            lines.append(t(lang, "wsect_quest_status_progress", emoji=emoji, name=qname,
                           progress=int(pq.progress), target=int(q.objective_value)))
            # Hotfix "A Volta" 2026-07-07 (#7 [jogador]) — a DESCRIÇÃO (as instruções
            # dos arcos, localizadas em q_<id>_desc) nunca era renderizada no
            # chat: "info cortada". Linha em itálico sob a quest em progresso.
            qdesc = catalog_desc(lang, "q", q)
            if qdesc:
                lines.append(f"  _{qdesc}_")
    kb_rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita_ancia")])
    try:
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(kb_rows))
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


async def _render_merit_pavilion(query, session, pid: int, lang: str) -> None:
    """wave 3 — the Pavilhão de Mérito: spend sect_contribution (the spendable
    balance) on cosmetic house titles. Owned/rank-locked rewards show status; an
    affordable one gets a claim button. Mirror of the mini SectHallModal section."""
    from core.world_sects_engine import get_merit_pavilion_state
    state = await get_merit_pavilion_state(session, pid, lang)
    lines = [f"*{t(lang, 'merit_pavilion_title')}*", "", t(lang, "merit_pavilion_intro"), ""]
    kb_rows = []
    if not state.get("in_sect"):
        lines.append(t(lang, "wsect_quests_empty"))
    else:
        lines.append(f"{t(lang, 'merit_balance_label')}: *{int(state.get('merit_balance', 0))}* 🏛️")
        lines.append("")
        # QoL 04/08 — o Pavilhão vende títulos HONORÍFICOS (zero stat, zero
        # jade). O servidor JÁ resolve o `desc` de cada um e o mini mostra;
        # o chat deitava-o fora (paridade quebrada + Lei §1). E a linha de topo
        # diz o que a compra é, para ninguém pagar 450 CP à espera de bônus.
        lines.append(t(lang, "merit_titles_honorary_note"))
        lines.append("")
        for r in state.get("rewards", []):
            if r.get("owned"):
                lines.append(f"✓ {r['title']} — {t(lang, 'merit_owned')}")
            elif not r.get("rank_ok"):
                lines.append(f"🔒 {r['title']} — {t(lang, 'merit_locked_rank', rank=t(lang, r['rank_min_key']))}")
            else:
                lines.append(f"• {r['title']} — {int(r['cost'])} 🏛️")
            if r.get("desc"):
                lines.append(f"  _{r['desc']}_")
                kb_rows.append([InlineKeyboardButton(
                    f"{t(lang, 'merit_buy_btn')} · {r['title']} · {int(r['cost'])}",
                    callback_data=f"wsect_merit_buy_{r['id']}")])
    kb_rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita_ancia")])
    try:
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(kb_rows))
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


async def _render_sect_tribute(query, session, pid: int, lang: str) -> None:
    """v16.4c — donate spirit stones for sect contribution (preset amounts)."""
    from core.world_sects_engine import TRIBUTE_STONES_PER_POINT
    player = (await session.execute(
        select(Player).where(Player.telegram_id == pid)
    )).scalar_one_or_none()
    stones = int(player.spirit_stones or 0) if player else 0
    rate = TRIBUTE_STONES_PER_POINT
    lines = [
        f"💰 *{t(lang, 'wsect_tribute_title')}*", "",
        t(lang, "wsect_tribute_intro", rate=rate), "",
        t(lang, "wsect_tribute_balance", stones=stones),
    ]
    kb_rows = []
    for amt in (250, 1000, 5000):
        if stones >= amt:
            kb_rows.append([InlineKeyboardButton(
                t(lang, "wsect_tribute_btn", stones=amt, points=amt // rate),
                callback_data=f"wsect_trib_{amt}")])
    if not kb_rows:
        lines.append("")
        lines.append(t(lang, "wsect_tribute_too_small"))
    kb_rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita_ancia")])
    try:
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(kb_rows))
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


async def world_sect_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `wsect_*` callbacks + `cmd_seita_ancia`. Returns True if handled."""
    from database.models import WorldSectRecruiterPending  # noqa: F811 (local import)
    from core.world_sects_engine import join_player_to_sect, WORLD_SECT_META

    query = update.callback_query
    if not query or not query.data:
        return False
    data = query.data

    if data == "cmd_seita_ancia":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            await _render_world_sect_menu(update, context, session, player)
        return True

    # B (2026-06-16) — Leave / Betray the Cultivation Sect (simple version).
    if data == "wsect_leave_confirm":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            # Disclosure (Lei §1): state the cost before the irreversible tap.
            confirm_text = t(lang, "wsect_leave_confirm")
            # TEC-1 — disclosure honesta ANTES de sair: as artes do Núcleo da
            # casa LOCKAM (não usa; nunca apaga; voltar re-destranca). Gated.
            try:
                # TEC-3: piso do engine — sem isto, sair da casa trancaria em
                # SILÊNCIO as artes do Ancião/Oculta (Lei §1 quebrada no aviso).
                from core.sect_library_engine import LOCK_TIER_FLOOR as _lib_floor
                from core.sect_library_engine import biblioteca_on
                if biblioteca_on() and player.sect_id:
                    from sqlalchemy import select as _select
                    from database.models import (PlayerTechnique as _PT,
                                                 TechniqueCatalog as _TC)
                    _rows = (await session.execute(
                        _select(_TC.id, _TC.name).join(_PT, _PT.technique_id == _TC.id)
                        .where(_PT.player_id == player.telegram_id,
                               _TC.sect_key == player.sect_id,
                               _TC.library_tier >= _lib_floor)
                    )).all()
                    if _rows:
                        # Nomes localizados (review TEC-1 F7 — padrão tech_<id>_name).
                        _names = [catalog_text(lang, "tech", int(r[0]), "name", r[1])
                                  for r in _rows]
                        confirm_text += "\n\n" + t(lang, "lib_leave_warn",
                                                   arts=", ".join(_names))
            except Exception:
                logger.debug("library leave disclosure failed", exc_info=True)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "wsect_leave_do_btn"), callback_data="wsect_leave_do")],
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_seita_ancia")],
            ])
            try:
                await query.message.edit_text(confirm_text, parse_mode="Markdown", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    raise
        return True

    if data == "wsect_leave_do":
        from core.world_sects_engine import leave_player_from_sect
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                await safe_answer(query)
                return True
            lang = normalize_lang(player.language or "pt")
            res = await leave_player_from_sect(session, player.telegram_id)
            if res.get("ok"):
                await session.commit()
                await safe_answer(query, t(lang, "wsect_left_ok"), show_alert=True)
            else:
                # Idempotent (already left, e.g. double-tap) — no error, just re-render.
                await safe_answer(query)
            # Re-render the (now sect-less) menu → affinity teaser, never a dead-end.
            await _render_world_sect_menu(update, context, session, player)
        return True

    # v16.4b — face the Elder (the REAL trial). Auto-plays the duel vs the
    # Sect Elder (same engine as the mini-app DuelArenaModal, AI-driven on the
    # chat surface) and narrates the outcome. Win ⇒ join; loss ⇒ 24h cooldown.
    if data.startswith("wsect_trial_"):
        await safe_answer(query)
        pending_id = safe_parse_callback_int(data, "wsect_trial_")
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            pid = player.telegram_id
            now = datetime.now(timezone.utc)
            if pending_id is None:
                await query.message.edit_text(t(lang, "wsect_recruiter_expired"), parse_mode="Markdown")
                return True
            # Lock the cultivator row before any trial write.
            locked = (await session.execute(
                select(Player).where(Player.telegram_id == pid).with_for_update()
            )).scalar_one_or_none()
            pend = await _resolve_recruiter_encounter(session, pid, pending_id, now)
            if not pend or locked is None:
                await query.message.edit_text(t(lang, "wsect_recruiter_expired"), parse_mode="Markdown")
                return True

            meta = WORLD_SECT_META.get(pend.sect_id) or {}
            sname = t(lang, meta.get("name_key") or "")
            emoji = meta.get("emoji") or "🏯"

            from core.sect_trial_engine import (
                start_sect_trial, auto_play_trial_duel, TRIAL_LOSS_COOLDOWN_HOURS,
            )
            from core.duel_engine import apply_post_duel_effects
            from database.models import DuelSession

            started = await start_sect_trial(session, locked, pend)
            if not started.get("ok"):
                reason = started.get("reason") or "engine"
                if reason == "trial_cooldown":
                    await query.message.edit_text(
                        t(lang, "wsect_trial_cooldown", emoji=emoji, sect=sname,
                          hours=TRIAL_LOSS_COOLDOWN_HOURS),
                        parse_mode="Markdown",
                    )
                elif reason == "duel_already_active":
                    await query.message.edit_text(t(lang, "wsect_trial_busy"), parse_mode="Markdown")
                elif reason in ("sect_already_joined", "sect_path_mismatch"):
                    await query.message.edit_text(t(lang, f"err_{reason}"), parse_mode="Markdown")
                else:
                    await query.message.edit_text(t(lang, "wsect_recruiter_expired"), parse_mode="Markdown")
                await session.commit()
                return True

            duel = (await session.execute(
                select(DuelSession).where(DuelSession.id == started["duel_id"])
            )).scalar_one_or_none()
            if duel is None:
                await session.rollback()
                await query.message.edit_text(t(lang, "wsect_recruiter_expired"), parse_mode="Markdown")
                return True

            await auto_play_trial_duel(session, duel, pid)
            await apply_post_duel_effects(session, duel)  # drains HP + settles (joins / cooldown)
            won = (duel.winner_id == pid and duel.state == "finished")
            rounds = int(duel.round_idx or 1)
            await session.commit()

            if won:
                await query.message.edit_text(
                    t(lang, "wsect_trial_win", emoji=emoji, sect=sname, rounds=rounds),
                    parse_mode="Markdown",
                )
            else:
                await query.message.edit_text(
                    t(lang, "wsect_trial_loss", emoji=emoji, sect=sname, rounds=rounds,
                      hours=TRIAL_LOSS_COOLDOWN_HOURS),
                    parse_mode="Markdown",
                )
        return True

    if data.startswith("wsect_accept_") or data.startswith("wsect_decline_"):
        await safe_answer(query)
        is_accept = data.startswith("wsect_accept_")
        pending_id = safe_parse_callback_int(data, "wsect_accept_" if is_accept else "wsect_decline_")
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            pid = player.telegram_id
            now = datetime.now(timezone.utc)
            if pending_id is None:
                await safe_answer(query, t(lang, "wsect_recruiter_expired"), show_alert=True)
                return True
            pend = await _resolve_recruiter_encounter(session, pid, pending_id, now)
            if not pend:
                await query.message.edit_text(t(lang, "wsect_recruiter_expired"), parse_mode="Markdown")
                return True

            meta = WORLD_SECT_META.get(pend.sect_id) or {}
            sname = t(lang, meta.get("name_key") or "")
            emoji = meta.get("emoji") or "🏯"

            if is_accept:
                # v16.4b — accepting no longer joins instantly; it opens the
                # Elder's trial. The house is earned, not granted (Lei §1: the
                # affinity is shown, defeat is a cooldown not a dead-end).
                await _render_trial_intro(query, lang, pend, sname, emoji)
            else:
                pend.declined_at = now
                await session.commit()
                await query.message.edit_text(
                    t(lang, "wsect_declined", emoji=emoji, sect=sname),
                    parse_mode="Markdown",
                )
        return True

    # ── v16.4c — Sect Hall drill-ins (member-only; the menu gates by membership).
    if data == "wsect_lib":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            await _render_sect_library(query, session, player.telegram_id,
                                       normalize_lang(player.language or "pt"))
        return True

    if data.startswith("wsect_learn_"):
        await safe_answer(query)
        tech_id = safe_parse_callback_int(data, "wsect_learn_")
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            if tech_id is None:
                await safe_answer(query, t(lang, "wsect_learn_fail"), show_alert=True)
                return True
            from core.world_sects_engine import learn_sect_technique
            res = await learn_sect_technique(session, player.telegram_id, tech_id)
            if res.get("ok"):
                await session.commit()
                await safe_answer(query, t(lang, "wsect_learn_ok", name=res.get("name", "")), show_alert=True)
            else:
                key = {
                    "rank_too_low": "wsect_learn_rank_low",
                    "already_learned": "wsect_learn_already",
                    "realm_too_low": "wsect_learn_realm_low",
                }.get(res.get("reason"), "wsect_learn_fail")
                await safe_answer(query, t(lang, key, realm=int(res.get("req_realm", 0))), show_alert=True)
            await _render_sect_library(query, session, player.telegram_id, lang)
        return True

    if data == "wsect_quests":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            await _render_sect_quests(query, session, player.telegram_id,
                                      normalize_lang(player.language or "pt"))
        return True

    if data.startswith("wsect_qc_"):
        # Hotfix "A Volta" 2026-07-07 (#7 [jogador]): NÃO responder o callback aqui —
        # um callback só aceita UM answer; o answer vazio inicial fazia o
        # Telegram rejeitar o alerta de sucesso abaixo (silenciado pelo
        # safe_answer) e o claim parecia "não funcionar".
        quest_id = safe_parse_callback_int(data, "wsect_qc_")
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                await safe_answer(query)
                return True
            lang = normalize_lang(player.language or "pt")
            res = None
            if quest_id is not None:
                from core.quest_engine import claim_quest_reward
                res = await claim_quest_reward(session, player.telegram_id, quest_id)
                await session.commit()
            if res:
                await safe_answer(query, t(lang, "wsect_quest_claimed_toast"), show_alert=True)
            else:
                await safe_answer(query)
            await _render_sect_quests(query, session, player.telegram_id, lang)
        return True

    if data == "wsect_tribute":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            await _render_sect_tribute(query, session, player.telegram_id,
                                       normalize_lang(player.language or "pt"))
        return True

    if data == "wsect_merit":
        await safe_answer(query)
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            await _render_merit_pavilion(query, session, player.telegram_id,
                                         normalize_lang(player.language or "pt"))
        return True

    if data.startswith("wsect_merit_buy_"):
        await safe_answer(query)
        reward_id = data[len("wsect_merit_buy_"):]
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            from core.world_sects_engine import buy_merit_reward
            res = await buy_merit_reward(session, player.telegram_id, reward_id)
            if res.get("ok"):
                await session.commit()
                await safe_answer(query, t(lang, "merit_buy_ok", title=res.get("title", "")), show_alert=True)
            else:
                reason = res.get("reason")
                if reason == "rank_too_low":
                    await safe_answer(query, t(lang, "merit_rank_too_low",
                                               rank=t(lang, res.get("rank_min_key", ""))), show_alert=True)
                elif reason == "insufficient_merit":
                    await safe_answer(query, t(lang, "merit_insufficient"), show_alert=True)
                elif reason == "already_owned":
                    await safe_answer(query, t(lang, "merit_already_owned"), show_alert=True)
            await _render_merit_pavilion(query, session, player.telegram_id, lang)
        return True

    if data.startswith("wsect_trib_"):
        await safe_answer(query)
        amt = safe_parse_callback_int(data, "wsect_trib_")
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return True
            lang = normalize_lang(player.language or "pt")
            if amt is not None and amt > 0:
                from core.world_sects_engine import tribute_stones, get_rank_label_key as _rk
                res = await tribute_stones(session, player.telegram_id, amt)
                if res.get("ok"):
                    await session.commit()
                    promo = res.get("promotion")
                    if promo:
                        await safe_answer(query, t(lang, "wsect_tribute_promoted",
                                                   rank=t(lang, _rk(promo["new"]))), show_alert=True)
                    else:
                        await safe_answer(query, t(lang, "wsect_tribute_ok",
                                                   stones=int(res.get("stones_spent", 0)),
                                                   points=int(res.get("points", 0))), show_alert=True)
                else:
                    await safe_answer(query, t(lang, "wsect_tribute_too_small"), show_alert=True)
            await _render_sect_tribute(query, session, player.telegram_id, lang)
        return True

    return False
