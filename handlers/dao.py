from core.utils import safe_handler, rate_limit, _get_player, safe_answer, normalize_lang
import logging
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

from config import DAO_MEDITATION_TYPES, REALM_NAMES
from database.db import get_session_factory
from database.models import Player, DaoLawCatalog, PlayerDaoFragment
from core.dao_engine import build_dao_display, DAO_UNLOCK_REALM
from core.dao_laws_engine import (
    get_category_summary, get_path_discovered_laws,
    get_total_discoveries, get_tier_info,
)
from core.i18n import t

logger = logging.getLogger(__name__)


# ── Main /dao command ─────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def dao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    user = update.effective_user
    if not user:
        return

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            lang = normalize_lang(getattr(user, 'language_code', None))
            msg = update.message or update.callback_query.message
            await msg.reply_text(t(lang, "dao_start_prompt"), parse_mode="Markdown")
            return

        lang = normalize_lang(player.language)
        if player.realm < DAO_UNLOCK_REALM:
            text = t(lang, "milestone_locked_dao")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")]])
            msg = update.message or update.callback_query.message
            await msg.reply_text(text, parse_mode="Markdown", reply_markup=kb)
            return

        # Get 3000 Laws summary (graceful if tables not seeded yet)
        try:
            total_disc = await get_total_discoveries(session, player.telegram_id)
            categories = await get_category_summary(session, player.telegram_id, player.realm, lang)
        except Exception as e:
            logger.warning("3000 Laws query failed (tables may not be seeded): %s", e)
            total_disc = 0
            categories = []
        realm = player.realm
        is_meditating = player.is_meditating

        # TAPETE QoL §5 item 11 ([jogador]: "percepção não parece alterar a
        # velocidade") — disclosure-only breakdown, canonical helper shared
        # with the mini-app /dao/summary endpoint.
        try:
            from core.dao_engine import compute_comprehension_breakdown
            comp = await compute_comprehension_breakdown(session, player)
        except Exception as e:
            logger.warning("dao comprehension breakdown failed: %s", e)
            comp = None

    # Build summary text
    lines = [t(lang, "dao_main_title")]
    lines.append("")

    # 3000 Laws overview
    if categories:
        lines.append(t(lang, "dao_3000_header", total=total_disc))
        for cat in categories:
            if cat["locked"]:
                realm_name = REALM_NAMES[cat["min_realm"]] if cat["min_realm"] < len(REALM_NAMES) else f"R{cat['min_realm']}"
                lines.append(f"🔒 {cat['emoji']} *{cat['name']}* — {t(lang, 'dao_cat_locked', realm=realm_name)}")
            else:
                # Find best tier across paths
                best_tier = max((p["tier"] for p in cat["paths"]), default=0)
                tier_info = get_tier_info(best_tier, lang)
                stars = tier_info["stars"]
                lines.append(f"{cat['emoji']} *{cat['name']}* — {cat['discovered']}/{cat['total_laws']} {stars}")
        lines.append("")

    # Supreme Laws brief
    lines.append(t(lang, "dao_supreme_header"))
    lines.append(t(lang, "dao_supreme_hint"))

    # Comprehension-speed disclosure (Lei §1): each component with its number.
    if comp:
        lines.append("")
        lines.append(t(lang, "dao_comp_header"))
        lines.append(t(lang, "dao_comp_fragments",
                       perception=comp["perception_total"],
                       pct=comp["fragment_chance_pct"]))
        if comp.get("fragment_capped"):
            lines.append(t(lang, "dao_comp_frag_capped"))
        if comp.get("laws_accessible"):
            lines.append(t(lang, "dao_comp_discovery",
                           remaining=comp["laws_accessible"] - comp["laws_discovered"],
                           total=comp["laws_accessible"],
                           pct=comp["discovery_chance_pct"]))
        lines.append(t(lang, "dao_comp_rarity", factor=comp["perception_rarity_factor"]))
        if comp.get("perception_rarity_capped"):
            lines.append(t(lang, "dao_comp_rarity_capped"))
        # review 2026-06-12: the numbers above are the ×1 baseline — say so.
        lines.append(t(lang, "dao_comp_chat_note"))

    text = "\n".join(lines)

    # Buttons
    buttons = []
    if categories:
        buttons.append([InlineKeyboardButton(t(lang, "btn_dao_3000"), callback_data="dao_laws")])
    buttons.append([InlineKeyboardButton(t(lang, "btn_dao_supreme"), callback_data="dao_supreme")])
    if realm >= DAO_UNLOCK_REALM:
        if is_meditating:
            buttons.append([InlineKeyboardButton(t(lang, "btn_dao_cancel"), callback_data="dao_cancel_med")])
        else:
            buttons.append([InlineKeyboardButton(t(lang, "btn_dao_comprehend"), callback_data="dao_comprehend")])
    buttons.append([InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")])
    kb = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            if "Message is not modified" not in str(e):
                await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ── Supreme Laws (existing display) ──────────────────────────────────────────

async def _show_supreme_laws(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = normalize_lang(player.language)
        text = await build_dao_display(session, player.telegram_id, player.realm, lang=lang)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_dao_back"), callback_data="cmd_dao")],
    ])
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


# ── 3000 Laws Category List ──────────────────────────────────────────────────

async def _show_laws_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = normalize_lang(player.language)
        categories = await get_category_summary(session, player.telegram_id, player.realm, lang)
        total_disc = await get_total_discoveries(session, player.telegram_id)

    lines = [t(lang, "dao_laws_title")]
    lines.append(t(lang, "dao_laws_total", total=total_disc, max=3000))
    lines.append("")

    buttons = []
    for cat in categories:
        if cat["locked"]:
            realm_name = REALM_NAMES[cat["min_realm"]] if cat["min_realm"] < len(REALM_NAMES) else f"R{cat['min_realm']}"
            lines.append(f"🔒 {cat['emoji']} *{cat['name']}* — {t(lang, 'dao_cat_locked', realm=realm_name)}")
        else:
            best_tier = max((p["tier"] for p in cat["paths"]), default=0)
            tier_info = get_tier_info(best_tier, lang)
            lines.append(f"{cat['emoji']} *{cat['name']}* — {cat['discovered']}/{cat['total_laws']} | {tier_info['stars'] or t(lang, 'dao_tier_none')}")
            buttons.append([InlineKeyboardButton(
                f"{cat['emoji']} {cat['name']} ({cat['discovered']}/{cat['total_laws']})",
                callback_data=f"dao_cat_{cat['id']}"
            )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_dao_back"), callback_data="cmd_dao")])
    kb = InlineKeyboardMarkup(buttons)

    text = "\n".join(lines)
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


# ── Category Detail (paths) ──────────────────────────────────────────────────

async def _show_category(update: Update, context: ContextTypes.DEFAULT_TYPE, cat_id: int):
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = normalize_lang(player.language)
        categories = await get_category_summary(session, player.telegram_id, player.realm, lang)

    cat = next((c for c in categories if c["id"] == cat_id), None)
    if not cat:
        await safe_answer(query, "Category not found", show_alert=True)
        return

    lines = [f"{cat['emoji']} *{cat['name']}*"]
    lines.append(t(lang, "dao_cat_discovered", discovered=cat['discovered'], total=cat['total_laws']))
    lines.append(t(lang, "dao_cat_bonus_type", bonus=_bonus_label(cat['bonus_type'], lang)))
    lines.append("")

    buttons = []
    for path in cat["paths"]:
        if path["locked"]:
            realm_name = REALM_NAMES[path["min_realm"]] if path["min_realm"] < len(REALM_NAMES) else f"R{path['min_realm']}"
            lines.append(f"🔒 {path['emoji']} *{path['name']}* — {t(lang, 'dao_cat_locked', realm=realm_name)}")
        else:
            ti = path["tier_info"]
            stars = ti["stars"] or "—"
            lines.append(f"{path['emoji']} *{path['name']}* — {path['discovered']}/{path['total']} | {stars} {ti['name']}")
            if ti["bonus"] > 0:
                lines.append(f"   {t(lang, 'dao_path_bonus', pct=int(ti['bonus'] * 100), bonus=_bonus_label(cat['bonus_type'], lang))}")
            buttons.append([InlineKeyboardButton(
                f"{path['emoji']} {path['name']} ({path['discovered']}/{path['total']})",
                callback_data=f"dao_path_{path['id']}"
            )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_dao_back_laws"), callback_data="dao_laws")])
    buttons.append([InlineKeyboardButton(t(lang, "btn_dao_back"), callback_data="cmd_dao")])
    kb = InlineKeyboardMarkup(buttons)

    text = "\n".join(lines)
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


# ── Path Detail (discovered laws, paginated) ─────────────────────────────────

async def _show_path(update: Update, context: ContextTypes.DEFAULT_TYPE, path_id: int, page: int = 1):
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = normalize_lang(player.language)

        from database.models import DaoPath, DaoCategory
        path = (await session.execute(
            select(DaoPath).where(DaoPath.id == path_id)
        )).scalar_one_or_none()
        if not path:
            await safe_answer(query, "Path not found", show_alert=True)
            return

        category = (await session.execute(
            select(DaoCategory).where(DaoCategory.id == path.category_id)
        )).scalar_one()

        laws, total_discovered, total_pages = await get_path_discovered_laws(
            session, player.telegram_id, path_id, page=page
        )

        from core.dao_laws_engine import get_path_tier
        tier = get_path_tier(total_discovered, path.total_laws)
        tier_info = get_tier_info(tier, lang)

    lang_key = {"en": "name", "pt": "name_pt", "es": "name_es"}.get(lang, "name")
    path_name = getattr(path, lang_key, None) or path.name

    lines = [f"{path.emoji} *{path_name}*"]
    lines.append(t(lang, "dao_path_progress", discovered=total_discovered, total=path.total_laws))
    lines.append(t(lang, "dao_path_tier", stars=tier_info['stars'] or '—', name=tier_info['name']))
    if tier_info["bonus"] > 0:
        lines.append(t(lang, "dao_path_bonus", pct=int(tier_info['bonus'] * 100), bonus=_bonus_label(category.bonus_type, lang)))
    lines.append("")

    if not laws:
        lines.append(t(lang, "dao_path_no_laws"))
    else:
        lines.append(t(lang, "dao_path_laws_header"))
        for law in laws:
            law_name = law.get(f"name_{lang}") or law["name"]
            lines.append(f"  {law['rarity_emoji']} {law_name}")

    if total_pages > 1:
        lines.append(f"\n📄 {page}/{total_pages}")

    text = "\n".join(lines)

    buttons = []
    # Pagination
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"dao_pp_{path_id}_{page - 1}"))
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("➡️", callback_data=f"dao_pp_{path_id}_{page + 1}"))
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(t(lang, "btn_dao_back_cat"), callback_data=f"dao_cat_{category.id}")])
    buttons.append([InlineKeyboardButton(t(lang, "btn_dao_back"), callback_data="cmd_dao")])
    kb = InlineKeyboardMarkup(buttons)

    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


# ── Comprehend Menu (existing) ────────────────────────────────────────────────

async def _show_comprehend_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"

        if player.is_meditating:
            await safe_answer(query, t(lang, "ans_já_estás_a_meditar"), show_alert=True)
            return

        realm = player.realm
        qi = player.qi
        trials_passed = player.celestial_trials_passed or 0

    lines = [t(lang, "meditar_choose_title")]
    lines.append(t(lang, "dao_comprehend_desc") + "\n")

    buttons = []
    for med_key, med_info in DAO_MEDITATION_TYPES.items():
        name_data = med_info["name"]
        name = name_data.get(lang, name_data.get("pt", "???")) if isinstance(name_data, dict) else name_data
        dur = med_info["duration_minutes"]
        qi_cost = med_info["qi_cost"]
        min_realm = med_info["min_realm"]
        frag_mult = med_info["dao_fragment_mult"]
        needs_trial = bool(med_info.get("requires_first_trial"))

        realm_ok = realm >= min_realm
        qi_ok = qi >= qi_cost
        trial_ok = (not needs_trial) or (trials_passed >= 1)

        status_parts = []
        if not realm_ok:
            realm_name = REALM_NAMES[min_realm] if min_realm < len(REALM_NAMES) else f"Realm {min_realm}"
            status_parts.append(f"⛔ Req: {realm_name}")
        if not trial_ok and realm_ok:
            status_parts.append("⛔ " + t(lang, "celestial_med_needs_trial_short"))
        if not qi_ok and realm_ok:
            status_parts.append(f"⛔ Qi: {qi_cost}")

        status_str = " ".join(status_parts)
        line = f"{name} ({dur}min) — {qi_cost} Qi | ×{frag_mult:.0f} chance"
        if status_str:
            line += f"\n  {status_str}"
        lines.append(line)

        if realm_ok and qi_ok and trial_ok:
            buttons.append([InlineKeyboardButton(f"{name}", callback_data=f"dao_start_{med_key}")])

    lines.append("\n" + t(lang, "dao_comprehend_warning"))

    buttons.append([InlineKeyboardButton(t(lang, "btn_dao_back"), callback_data="cmd_dao")])
    kb = InlineKeyboardMarkup(buttons)

    text = "\n".join(lines)
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


# ── Start/Cancel Meditation (existing) ────────────────────────────────────────

async def _start_dao_meditation(update: Update, context: ContextTypes.DEFAULT_TYPE, med_key: str):
    query = update.callback_query
    user = update.effective_user

    med_info = DAO_MEDITATION_TYPES.get(med_key)
    if not med_info:
        lang_fallback = normalize_lang(getattr(user, 'language_code', None))
        await safe_answer(query, t(lang_fallback, "ans_meditação_inválida"), show_alert=True)
        return

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"

        if player.realm < med_info["min_realm"]:
            realm_name = REALM_NAMES[med_info["min_realm"]] if med_info["min_realm"] < len(REALM_NAMES) else "???"
            await safe_answer(query, t(lang, "ans_req_realm", realm=realm_name), show_alert=True)
            return

        if med_info.get("requires_first_trial") and (player.celestial_trials_passed or 0) < 1:
            await safe_answer(query, t(lang, "celestial_med_needs_trial"), show_alert=True)
            return

        if med_info["qi_cost"] > 0 and player.qi < med_info["qi_cost"]:
            await safe_answer(query, t(lang, "ans_qi_insuficiente"), show_alert=True)
            return

        if player.is_meditating:
            # Fix 2026-08-06 (report do [jogador]): trocar de meditação de Dao por
            # cima de uma JÁ CUMPRIDA descartava o crédito de `cultivate`.
            from core.game_logic import credit_meditation_if_earned
            await credit_meditation_if_earned(
                session, player, player.meditation_type, player.meditation_end)
            player.is_meditating = False
            player.meditation_type = None
            player.meditation_end = None
            player.meditation_multiplier = 1.0

        now = datetime.now(timezone.utc)
        player.is_meditating = True
        player.meditation_type = med_key
        player.meditation_end = now + timedelta(minutes=med_info["duration_minutes"])
        player.meditation_multiplier = 0.0  # Zero CB
        player.last_online = now

        if med_info["qi_cost"] > 0:
            player.qi = max(0, player.qi - med_info["qi_cost"])

        await session.commit()

    frag_mult = med_info["dao_fragment_mult"]
    text = "\n".join([
        t(lang, "meditar_started_title"),
        "",
        t(lang, "meditar_started_type", name=med_info["name"].get(lang, med_info["name"].get("pt", "???")) if isinstance(med_info["name"], dict) else med_info["name"]),
        t(lang, "meditar_started_duration", minutes=med_info["duration_minutes"]),
        t(lang, "dao_started_frag", mult=f"{frag_mult:.0f}"),
        t(lang, "dao_started_cb_zero"),
        t(lang, "dao_started_laws_hint"),
        "",
        t(lang, "meditar_started_flavor"),
    ])

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_dao_view"), callback_data="cmd_dao")],
        [InlineKeyboardButton(t(lang, "btn_status"), callback_data="cmd_status")],
    ])

    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def _cancel_dao_meditation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"

        # Fix 2026-08-06 (report do [jogador]) — o cancelamento do cultivo do Dao no
        # CHAT: mesma regra dos outros seis caminhos (quem finaliza credita).
        from core.game_logic import credit_meditation_if_earned
        await credit_meditation_if_earned(
            session, player, player.meditation_type, player.meditation_end)
        player.is_meditating = False
        player.meditation_type = None
        player.meditation_end = None
        player.meditation_multiplier = 1.0
        player.last_online = datetime.now(timezone.utc)
        await session.commit()

    text = t(lang, "meditar_cancelled_title") + "\n\n" + t(lang, "meditar_cancelled_body")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_dao_view"), callback_data="cmd_dao")],
        [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")],
    ])

    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bonus_label(bonus_type: str, lang: str) -> str:
    """Human-readable label for a bonus type."""
    labels = {
        "cb_mult": {"en": "Cultivation Speed", "pt": "Velocidade de Cultivo", "es": "Velocidad de Cultivo"},
        "bp_mult": {"en": "Battle Power", "pt": "Poder de Batalha", "es": "Poder de Batalla"},
        "hp_regen": {"en": "HP Regen", "pt": "Regeneração HP", "es": "Regeneración HP"},
        "cooldown_reduction": {"en": "Cooldown Reduction", "pt": "Redução de Cooldown", "es": "Reducción de Cooldown"},
        "tribulation_bonus": {"en": "Tribulation Success", "pt": "Sucesso em Tribulação", "es": "Éxito en Tribulación"},
        "craft_quality": {"en": "Crafting Quality", "pt": "Qualidade de Crafting", "es": "Calidad de Crafting"},
        "all_stats": {"en": "All Stats", "pt": "Todos os Stats", "es": "Todos los Stats"},
        "all_mult": {"en": "All Bonuses", "pt": "Todos os Bónus", "es": "Todos los Bonus"},
    }
    return labels.get(bonus_type, {}).get(lang, bonus_type)


# ── Button Router ─────────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def dao_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data:
        return False

    data = query.data

    if data == "cmd_dao":
        await safe_answer(query)
        await dao_command(update, context)
        return True

    if data == "dao_supreme":
        await safe_answer(query)
        await _show_supreme_laws(update, context)
        return True

    if data == "dao_laws":
        await safe_answer(query)
        await _show_laws_overview(update, context)
        return True

    if data.startswith("dao_cat_"):
        await safe_answer(query)
        cat_id = int(data.replace("dao_cat_", ""))
        await _show_category(update, context, cat_id)
        return True

    if data.startswith("dao_path_"):
        await safe_answer(query)
        path_id = int(data.replace("dao_path_", ""))
        await _show_path(update, context, path_id)
        return True

    # Path pagination: dao_pp_{path_id}_{page}
    if data.startswith("dao_pp_"):
        await safe_answer(query)
        parts = data.replace("dao_pp_", "").split("_")
        if len(parts) == 2:
            path_id = int(parts[0])
            page = int(parts[1])
            await _show_path(update, context, path_id, page)
        return True

    if data == "dao_comprehend":
        await safe_answer(query)
        await _show_comprehend_menu(update, context)
        return True

    if data.startswith("dao_start_"):
        await safe_answer(query)
        med_key = data.replace("dao_start_", "")
        await _start_dao_meditation(update, context, med_key)
        return True

    if data == "dao_cancel_med":
        await safe_answer(query)
        await _cancel_dao_meditation(update, context)
        return True

    return False
