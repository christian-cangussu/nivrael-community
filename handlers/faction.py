"""Handler for the Faction system — join, quests, shop, status."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from core.faction_engine import (
    get_factions, get_player_faction, join_faction, get_faction_catalog,
    get_available_quests, get_active_quests, accept_quest, claim_quest,
    get_shop_items, get_shop_item as _get_shop_item, buy_shop_item,
    FACTION_RANKS, rank_for_rep, rank_index,
    # 門 P6 — o limiar tem UM dono; este nome fica porque o resto do
    # ficheiro o usa (era `MIN_REALM_FACTION = 3`, uma segunda copia).
    FACTION_MIN_REALM as MIN_REALM_FACTION,
)
from core.game_logic import format_number
from core.i18n import t
from database.db import get_session_factory
from core.utils import (
    _ensure_player, safe_handler, rate_limit, safe_answer,
    safe_parse_callback_int, normalize_lang,
)

ITEMS_PER_PAGE = 5


def _progress_bar(current: int, target: int, length: int = 8) -> str:
    ratio = min(current / target, 1.0) if target > 0 else 0
    filled = int(ratio * length)
    return "█" * filled + "░" * (length - filled)


def _rep_bar(rep: int) -> str:
    """Show progress toward next rank."""
    for i, (name, threshold) in enumerate(FACTION_RANKS):
        if i + 1 < len(FACTION_RANKS):
            next_name, next_threshold = FACTION_RANKS[i + 1]
            if rep < next_threshold:
                return _progress_bar(rep - threshold, next_threshold - threshold) + f" {rep}/{next_threshold}"
    return f"████████ {rep} (MAX)"


# ── Main menu ───────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def faction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        if player.realm < MIN_REALM_FACTION:
            msg = t(lang, "faction_realm_too_low", realm=MIN_REALM_FACTION)
            if update.callback_query:
                await safe_answer(update.callback_query)
                await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
            else:
                await update.effective_message.reply_text(msg, parse_mode="Markdown")
            return

        pf = await get_player_faction(session, player.telegram_id)
        await session.commit()

    # v16.2.1 (Path Trinity pivot) — soft-disable. Players already in a
    # faction keep their dashboard intact (rep / quests / shop). New
    # players see only the legacy banner explaining the migration to
    # Path Trinity — we don't offer the picker, to avoid accumulating
    # new memberships in a system being absorbed by v16.4 Sect Recruitment.
    if pf:
        await _faction_dashboard(update, context)
    else:
        msg = t(lang, "faction_legacy_banner_chat")
        if update.callback_query:
            await safe_answer(update.callback_query)
            await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(msg, parse_mode="Markdown")


async def _faction_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show faction selection screen."""
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        factions = await get_factions(session)
        await session.commit()

    lines = [t(lang, "faction_choose_title"), ""]
    buttons = []
    for f in factions:
        lines.append(f"{f.emoji} *{f.name}*")
        lines.append(f"_{f.description}_")
        bonuses = f.bonuses or {}
        bonus_parts = []
        for k, v in bonuses.items():
            label = k.replace("_", " ").title()
            bonus_parts.append(f"+{int(v*100)}% {label}")
        if bonus_parts:
            lines.append(f"  {', '.join(bonus_parts)}")
        lines.append("")
        buttons.append([InlineKeyboardButton(
            f"{f.emoji} {t(lang, 'btn_join_faction', name=f.name)}",
            callback_data=f"fac_join_{f.id}",
        )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_comunica")])
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await safe_answer(update.callback_query)
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def _faction_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show faction membership dashboard."""
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        pf = await get_player_faction(session, player.telegram_id)
        if not pf:
            await session.commit()
            await _faction_choose(update, context)
            return
        faction = await get_faction_catalog(session, pf.faction_id)
        active_quests = await get_active_quests(session, player.telegram_id)
        await session.commit()

    active_count = len(active_quests)
    claimable = sum(1 for pfq, _ in active_quests if pfq.is_completed and not pfq.claimed)

    # Current rank index
    cur_rank_idx = rank_index(pf.rank)
    rank_emoji = ["🔰", "⭐", "🌟", "💎", "👑"]

    total_earned = pf.total_rep_earned

    lines = [
        t(lang, "faction_dashboard_title"),
        "",
        f"{faction.emoji} *{faction.name}*",
        f"————————————————",
        f"{rank_emoji[cur_rank_idx]} {t(lang, 'faction_rank_label')}: *{pf.rank}*",
        f"⭐ {t(lang, 'faction_rep_label')}: *{format_number(total_earned)}*",
        f"  {_rep_bar(total_earned)}",
    ]

    # Show next rank info (based on total earned)
    if cur_rank_idx + 1 < len(FACTION_RANKS):
        next_name, next_threshold = FACTION_RANKS[cur_rank_idx + 1]
        remaining = max(0, next_threshold - total_earned)
        lines.append(f"  ➡️ {t(lang, 'faction_next_rank', rank=next_name, rep=format_number(remaining))}")
    else:
        lines.append(f"  👑 {t(lang, 'faction_max_rank')}")

    # Spendable reputation
    lines.append(f"💰 {t(lang, 'faction_spendable_rep')}: *{format_number(pf.reputation)}*")

    # Show faction bonuses
    bonuses = faction.bonuses or {}
    if bonuses:
        lines.append("")
        lines.append(f"🔮 *{t(lang, 'faction_bonuses_label')}:*")
        for k, v in bonuses.items():
            label = k.replace("_", " ").title()
            lines.append(f"  +{int(v*100)}% {label}")

    lines.append("")
    lines.append(f"📋 {t(lang, 'faction_active_quests')}: {active_count}")
    if claimable > 0:
        lines.append(f"✅ {t(lang, 'faction_claimable', count=claimable)}")

    text = "\n".join(lines)

    buttons = [
        [
            InlineKeyboardButton(t(lang, "btn_faction_quests"), callback_data="fac_quests"),
            InlineKeyboardButton(t(lang, "btn_faction_active"), callback_data="fac_active"),
        ],
        [InlineKeyboardButton(t(lang, "btn_faction_shop"), callback_data="fac_shop")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_comunica")],
    ]
    kb = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await safe_answer(update.callback_query)
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ── Join Faction ────────────────────────────────────────────────────

async def _handle_join(update: Update, context: ContextTypes.DEFAULT_TYPE, faction_id: int):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        try:
            pf = await join_faction(session, player.telegram_id, faction_id)
            faction = await get_faction_catalog(session, faction_id)
            await session.commit()
            msg = t(lang, "faction_joined", name=faction.name, emoji=faction.emoji)
        except ValueError:
            await session.rollback()
            msg = t(lang, "faction_already_joined")

    await query.edit_message_text(msg, parse_mode="Markdown")
    # Redirect to dashboard after a moment
    await _faction_dashboard(update, context)


# ── Quest List (available) ──────────────────────────────────────────

async def _show_available_quests(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    query = update.callback_query
    if query:
        await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        pf = await get_player_faction(session, player.telegram_id)
        if not pf:
            await session.commit()
            return

        quests = await get_available_quests(session, player.telegram_id, pf.faction_id, player.realm)
        await session.commit()

    if not quests:
        text = t(lang, "faction_no_quests")
        buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_faction")]]
        if query:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    total_pages = (len(quests) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = max(0, min(page, total_pages - 1))
    page_quests = quests[page * ITEMS_PER_PAGE : (page + 1) * ITEMS_PER_PAGE]

    lines = [t(lang, "faction_quests_title"), ""]
    buttons = []

    for q in page_quests:
        target_count = q.target.get("count", 1)
        lines.append(f"{q.emoji} *{q.name}*")
        lines.append(f"  ⭐ +{q.reward_rep} rep | 🪨 {format_number(q.reward_items.get('spirit_stones', 0))} SS")
        lines.append(f"  🔄 {q.cooldown_hours}h cd | 🎯 x{target_count}")
        lines.append("")
        buttons.append([InlineKeyboardButton(
            f"{q.emoji} {t(lang, 'btn_accept_quest')}",
            callback_data=f"fac_accept_{q.id}",
        )])

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"fac_qp_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"fac_qp_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_faction")])
    text = "\n".join(lines)

    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ── Active Quests ───────────────────────────────────────────────────

async def _show_active_quests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        active = await get_active_quests(session, player.telegram_id)
        await session.commit()

    if not active:
        text = t(lang, "faction_no_active_quests")
        buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_faction")]]
        if query:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    lines = [t(lang, "faction_active_title"), ""]
    buttons = []

    for pfq, quest_cat in active:
        target_count = quest_cat.target.get("count", 1)
        bar = _progress_bar(pfq.progress, target_count)
        status = ""
        if pfq.is_completed:
            status = " ✅"

        lines.append(f"{quest_cat.emoji} *{quest_cat.name}*{status}")
        lines.append(f"  {bar} {pfq.progress}/{target_count}")
        lines.append(f"  🎁 +{quest_cat.reward_rep} rep")
        lines.append("")

        if pfq.is_completed and not pfq.claimed:
            buttons.append([InlineKeyboardButton(
                f"✅ {t(lang, 'btn_claim_faction_quest', name=quest_cat.name)}",
                callback_data=f"fac_claim_{pfq.id}",
            )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_faction")])
    text = "\n".join(lines)

    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ── Accept Quest ────────────────────────────────────────────────────

async def _handle_accept(update: Update, context: ContextTypes.DEFAULT_TYPE, quest_id: int):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        result = await accept_quest(session, player.telegram_id, quest_id)
        await session.commit()

    if result:
        await _show_active_quests(update, context)
    else:
        # Cooldown or already active
        text = t(lang, "faction_quest_unavailable")
        buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="fac_quests")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ── Claim Quest ─────────────────────────────────────────────────────

async def _handle_claim(update: Update, context: ContextTypes.DEFAULT_TYPE, pfq_id: int):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        success, rewards = await claim_quest(session, player.telegram_id, pfq_id)
        await session.commit()

    if success:
        parts = []
        if rewards.get("reputation"):
            parts.append(f"⭐ +{rewards['reputation']} rep")
        if rewards.get("spirit_stones"):
            parts.append(f"🪨 +{format_number(rewards['spirit_stones'])} SS")
        if rewards.get("spirit_jade"):
            parts.append(f"💎 +{rewards['spirit_jade']} Jade")

        reward_text = ", ".join(parts) if parts else "—"
        text = t(lang, "faction_quest_claimed", rewards=reward_text)

        buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="fac_active")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        text = t(lang, "faction_quest_claim_fail")
        buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="fac_active")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ── Shop ────────────────────────────────────────────────────────────

SHOP_CATEGORIES = [
    ("technique", "📜", "faction_shop_cat_techniques"),
    ("weapon",    "⚔️", "faction_shop_cat_weapons"),
    ("armor",     "🛡️", "faction_shop_cat_armor"),
    ("accessory", "💍", "faction_shop_cat_accessories"),
]

RANK_EMOJI = ["🔰", "⭐", "🌟", "💎", "👑"]


def _item_category(item) -> str:
    """Map shop item to display category."""
    if item.item_type == "technique":
        return "technique"
    # artifacts → sub-categorize by the description hint or item_data
    desc_lower = item.description.lower()
    if "weapon" in desc_lower or "blade" in desc_lower or "sword" in desc_lower or "fang" in desc_lower or "cleaver" in desc_lower:
        return "weapon"
    if "armor" in desc_lower or "robe" in desc_lower or "plate" in desc_lower or "vestment" in desc_lower or "mail" in desc_lower or "mantle" in desc_lower or "exoskeleton" in desc_lower:
        return "armor"
    if "accessory" in desc_lower or "ring" in desc_lower or "halo" in desc_lower or "talisman" in desc_lower or "pendant" in desc_lower:
        return "accessory"
    return "weapon"  # fallback


async def _show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str | None = None):
    """Show shop main menu (categories) or a specific category."""
    query = update.callback_query
    if query:
        await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        pf = await get_player_faction(session, player.telegram_id)
        if not pf:
            await session.commit()
            return

        faction = await get_faction_catalog(session, pf.faction_id)
        items = await get_shop_items(session, pf.faction_id, pf.rank)
        await session.commit()

    if category is None:
        # ── Main shop menu with categories ──
        cat_counts = {}
        for item in items:
            cat = _item_category(item)
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        separator = "—" * 24
        lines = [
            t(lang, "faction_shop_title"),
            separator,
            f"{faction.emoji} *{faction.name}* {t(lang, 'faction_shop_label')}",
            "",
            f"🏷️ {t(lang, 'faction_rank_label')}: *{pf.rank}* {RANK_EMOJI[rank_index(pf.rank)]}",
            f"💰 {t(lang, 'faction_spendable_rep')}: *{format_number(pf.reputation)}*",
        ]

        buttons = []
        for cat_key, cat_emoji, cat_locale_key in SHOP_CATEGORIES:
            count = cat_counts.get(cat_key, 0)
            if count > 0:
                buttons.append([InlineKeyboardButton(
                    f"{cat_emoji} {t(lang, cat_locale_key)} ({count})",
                    callback_data=f"fac_sc_{cat_key}",
                )])

        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_faction")])
        text = "\n".join(lines)

        if query:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return

    # ── Category view ──
    cat_items = [item for item in items if _item_category(item) == category]

    cat_info = next((c for c in SHOP_CATEGORIES if c[0] == category), None)
    cat_emoji = cat_info[1] if cat_info else "📦"
    cat_label = t(lang, cat_info[2]) if cat_info else category

    separator = "—" * 24
    lines = [
        f"{cat_emoji} *{cat_label}*",
        separator,
        f"💰 {format_number(pf.reputation)} rep",
        "",
    ]
    buttons = []

    for item in cat_items:
        can_buy = pf.reputation >= item.rep_cost and rank_index(pf.rank) >= rank_index(item.min_rank)
        lock = "" if can_buy else "🔒 "

        lines.append(f"{lock}{item.emoji} *{item.name}*")
        lines.append(f"  {item.description}")
        lines.append(f"  💰 *{format_number(item.rep_cost)}* rep | 🏷️ {item.min_rank}")
        lines.append("")

        btn_label = f"{item.emoji} {item.name[:22]}" if can_buy else f"🔒 {item.name[:22]}"
        buttons.append([InlineKeyboardButton(
            btn_label,
            callback_data=f"fac_buy_{item.id}",
        )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="fac_shop")])
    text = "\n".join(lines)

    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def _handle_buy(update: Update, context: ContextTypes.DEFAULT_TYPE, item_id: int):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        # Fetch shop item info before buying for feedback
        item = await _get_shop_item(session, item_id)
        success, error_key = await buy_shop_item(session, player.telegram_id, item_id)
        await session.commit()

    if success:
        item_name = item.name if item else "???"
        item_emoji = item.emoji if item else "📦"
        text = t(lang, "faction_shop_bought", name=item_name, emoji=item_emoji)
    else:
        text = t(lang, error_key) if error_key else t(lang, "faction_shop_buy_fail")

    buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="fac_shop")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ── Button Router ───────────────────────────────────────────────────

async def faction_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    data = query.data

    if data == "cmd_faction":
        await faction_command(update, context)
        return True

    if data.startswith("fac_join_"):
        fid = safe_parse_callback_int(data, "fac_join_")
        if fid is not None:
            await _handle_join(update, context, fid)
        return True

    if data == "fac_quests":
        await _show_available_quests(update, context)
        return True

    if data.startswith("fac_qp_"):
        page = safe_parse_callback_int(data, "fac_qp_")
        await _show_available_quests(update, context, page or 0)
        return True

    if data == "fac_active":
        await _show_active_quests(update, context)
        return True

    if data.startswith("fac_accept_"):
        qid = safe_parse_callback_int(data, "fac_accept_")
        if qid is not None:
            await _handle_accept(update, context, qid)
        return True

    if data.startswith("fac_claim_"):
        pfq_id = safe_parse_callback_int(data, "fac_claim_")
        if pfq_id is not None:
            await _handle_claim(update, context, pfq_id)
        return True

    if data == "fac_shop":
        await _show_shop(update, context)
        return True

    if data.startswith("fac_sc_"):
        cat = data.replace("fac_sc_", "")
        await _show_shop(update, context, category=cat)
        return True

    if data.startswith("fac_buy_"):
        iid = safe_parse_callback_int(data, "fac_buy_")
        if iid is not None:
            await _handle_buy(update, context, iid)
        return True

    return False
