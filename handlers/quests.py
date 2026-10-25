from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

from core.quest_engine import (
    ensure_daily_quests,
    ensure_weekly_quests,
    get_player_quests,
    claim_quest_reward,
    claim_all_completed,
    get_login_streak,
    get_streak_rewards_table,
)
from core.game_logic import format_number
from core.i18n import t
# 名 2026-09-14 — a missao diaria deixa de sair em ingles (captura do owner:
# "Attack World Boss — toca para reclamar la recompensa", numa tela espanhola).
from core.i18n import catalog_name as _cname
from database.db import get_session_factory
from database.models import Player, QuestCatalog
from core.utils import _ensure_player, safe_handler, rate_limit, safe_answer, safe_parse_callback_int, normalize_lang, resolve_chat_player_id


def _progress_bar(current: int, target: int, length: int = 8) -> str:
    ratio = min(current / target, 1.0) if target > 0 else 0
    filled = int(ratio * length)
    return "█" * filled + "░" * (length - filled)


def _reward_display(rewards: dict) -> str:
    parts = []
    if "spirit_stones" in rewards:
        parts.append(f"🪨 {format_number(rewards['spirit_stones'])} SS")
    if "spirit_jade" in rewards:
        parts.append(f"💎 {rewards['spirit_jade']} Jade")
    if "herb_pack" in rewards:
        parts.append(f"🌿 {rewards['herb_pack']}x Herb Pack")
    if "contribution_points" in rewards:
        parts.append(f"🏯 {rewards['contribution_points']} CP")
    if "technique_scroll" in rewards:
        parts.append(f"📜 {rewards['technique_scroll']}x Scroll")
    if "core_essence" in rewards:
        parts.append(f"💠 +{rewards['core_essence']} Core Essence")
    return " + ".join(parts) if parts else "—"


@safe_handler
@rate_limit(1)
async def missoes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        await session.commit()

    await _daily_tab(update, context)


async def _daily_tab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        await ensure_daily_quests(session, player.telegram_id)
        quests = await get_player_quests(session, player.telegram_id, "daily")
        # MV-5 — Quests VIVAS: a seção dinâmica (gated; flag OFF → None sem
        # UMA query → /missoes byte-idêntico). O sync lazy da expiração ride
        # no commit já existente deste tab (padrão ensure_daily_quests).
        sty_data = None
        try:
            from core.storylet_engine import quests_vivas_on, project_storylets
            if quests_vivas_on():
                sty_data = await project_storylets(session, player, lang=lang)
        except Exception:
            pass  # nunca derruba /missoes
        await session.commit()

    separator = "—" * 24
    lines = [
        t(lang, "quest_daily_title"),
        separator,
        "",
    ]

    buttons = []
    has_claimable = False

    for pq, quest in quests:
        status = ""
        if pq.claimed:
            status = " ✅ " + t(lang, "quest_claimed")
        elif pq.is_completed:
            status = t(lang, "quest_status_complete")
            has_claimable = True

        bar = _progress_bar(pq.progress, quest.objective_value)
        lines.append(f"{quest.emoji} *{_cname(lang, 'q', quest)}*{status}")
        lines.append(f"  {bar} {pq.progress}/{quest.objective_value}")
        lines.append(f"  🎁 {_reward_display(quest.rewards)}")
        lines.append("")

        if pq.is_completed and not pq.claimed:
            # v16.3.5 — fork quests carry a ⚖️ marker so the player knows the
            # claim opens a moral choice (the reward shown above is just a hint).
            _fork = "⚖️ " if getattr(quest, "choices", None) else ""
            buttons.append([InlineKeyboardButton(
                _fork + t(lang, "btn_claim_quest", name=_cname(lang, "q", quest)),
                callback_data=f"quest_claim_{quest.id}",
            )])

    # MV-5 — o bloco "Quests aceitas" (só existe com a flag ON).
    if sty_data:
        _sty_lines, _sty_buttons = _storylet_block(lang, sty_data)
        lines += _sty_lines
        buttons += _sty_buttons

    if has_claimable:
        buttons.insert(0, [InlineKeyboardButton(
            t(lang, "btn_claim_all"),
            callback_data="quest_claim_all",
        )])

    buttons.append([
        InlineKeyboardButton(t(lang, "btn_weekly"), callback_data="quest_tab_weekly"),
        InlineKeyboardButton(t(lang, "btn_streak"), callback_data="quest_tab_streak"),
    ])
    buttons.append([InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")])

    kb = InlineKeyboardMarkup(buttons)
    text = "\n".join(lines)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def _weekly_tab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        await ensure_weekly_quests(session, player.telegram_id)
        quests = await get_player_quests(session, player.telegram_id, "weekly")
        await session.commit()

    separator = "—" * 24
    lines = [
        t(lang, "quest_weekly_title"),
        separator,
        "",
    ]

    buttons = []
    has_claimable = False

    for pq, quest in quests:
        status = ""
        if pq.claimed:
            status = " ✅ " + t(lang, "quest_claimed")
        elif pq.is_completed:
            status = t(lang, "quest_status_complete")
            has_claimable = True

        bar = _progress_bar(pq.progress, quest.objective_value)
        lines.append(f"{quest.emoji} *{_cname(lang, 'q', quest)}*{status}")
        lines.append(f"  {bar} {pq.progress}/{quest.objective_value}")
        lines.append(f"  🎁 {_reward_display(quest.rewards)}")
        lines.append("")

        if pq.is_completed and not pq.claimed:
            # v16.3.5 — fork quests carry a ⚖️ marker so the player knows the
            # claim opens a moral choice (the reward shown above is just a hint).
            _fork = "⚖️ " if getattr(quest, "choices", None) else ""
            buttons.append([InlineKeyboardButton(
                _fork + t(lang, "btn_claim_quest", name=_cname(lang, "q", quest)),
                callback_data=f"quest_claim_{quest.id}",
            )])

    if has_claimable:
        buttons.insert(0, [InlineKeyboardButton(
            t(lang, "btn_claim_all"),
            callback_data="quest_claim_all",
        )])

    buttons.append([
        InlineKeyboardButton(t(lang, "btn_daily"), callback_data="quest_tab_daily"),
        InlineKeyboardButton(t(lang, "btn_streak"), callback_data="quest_tab_streak"),
    ])
    buttons.append([InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")])

    kb = InlineKeyboardMarkup(buttons)
    text = "\n".join(lines)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def _streak_tab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        streak = await get_login_streak(session, player.telegram_id)
        await session.commit()

    separator = "—" * 24
    current = streak.current_streak if streak else 0
    longest = streak.longest_streak if streak else 0
    total = streak.total_logins if streak else 0

    lines = [
        t(lang, "quest_streak_title"),
        separator,
        "",
        t(lang, "quest_streak_current", days=current),
        t(lang, "quest_streak_longest", days=longest),
        t(lang, "quest_streak_total", total=total),
        "",
        separator,
        t(lang, "quest_streak_rewards_hdr"),
        "",
    ]

    milestones = get_streak_rewards_table()
    for day, rewards in sorted(milestones.items()):
        reached = current >= day
        marker = "✅" if reached else "⬜"
        reward_parts = []
        if "spirit_jade" in rewards:
            reward_parts.append(f"💎 {rewards['spirit_jade']} Jade")
        if "item" in rewards:
            reward_parts.append(f"🎁 {rewards['item']}")
        if "title" in rewards:
            reward_parts.append(f"🏷️ {rewards['title']}")
        reward_text = " + ".join(reward_parts)
        lines.append(f"{marker} *D{day}:* {reward_text}")

    lines.append("")
    lines.append(f"_{_streak_flavor(current, lang)}_")

    buttons = [
        [
            InlineKeyboardButton(t(lang, "btn_daily"), callback_data="quest_tab_daily"),
            InlineKeyboardButton(t(lang, "btn_weekly"), callback_data="quest_tab_weekly"),
        ],
        [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")],
    ]

    kb = InlineKeyboardMarkup(buttons)
    text = "\n".join(lines)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


def _streak_flavor(streak: int, lang: str = "pt") -> str:
    if streak >= 30:
        return t(lang, "streak_flavor_30")
    elif streak >= 14:
        return t(lang, "streak_flavor_14")
    elif streak >= 7:
        return t(lang, "streak_flavor_7")
    elif streak >= 3:
        return t(lang, "streak_flavor_3")
    elif streak >= 1:
        return t(lang, "streak_flavor_1")
    return t(lang, "streak_flavor_0")


async def _claim_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    quest_id = safe_parse_callback_int(query.data, "quest_claim_")
    if quest_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        result = await claim_quest_reward(session, player.telegram_id, quest_id)
        # v16.3.5 — a fork quest returns {"needs_choice": True, "choices": [...]}
        # WITHOUT granting anything (claimed stays False). Only flat-reward quests
        # advance the BP mission here; fork quests advance it when the choice lands.
        is_choice_prompt = isinstance(result, dict) and result.get("needs_choice")
        if result is not None and not is_choice_prompt:
            from core.bp_engine import update_bp_mission
            await update_bp_mission(session, player.telegram_id, "complete_quests")

        player_lang = normalize_lang(player.language)
        picker = None
        if is_choice_prompt:
            quest = (await session.execute(
                select(QuestCatalog).where(QuestCatalog.id == quest_id)
            )).scalar_one_or_none()
            picker = {
                "quest_id": quest_id,
                "title": f"{quest.emoji} *{_cname(player_lang, 'q', quest)}*" if quest else "",
                "type": quest.type if quest else "daily",
                "choices": result.get("choices") or [],
            }
        await session.commit()

    if result is None:
        await safe_answer(query, t(player_lang, "quest_no_available"), show_alert=True)
        return

    if is_choice_prompt:
        await _render_choice_picker(update, player_lang, picker)
        return

    reward_text = _reward_display(result)
    await safe_answer(query, t(player_lang, "quest_reward_ans", reward=reward_text), show_alert=True)

    await _daily_tab(update, context)


async def _render_choice_picker(update: Update, lang: str, picker: dict):
    """v16.3.5 — edit the claim message into the moral-choice picker."""
    lines = [picker["title"], "", t(lang, "qc_prompt")]
    buttons = []
    for c in picker["choices"]:
        label = t(lang, c["label_key"]) if c.get("label_key") else c.get("id", "?")
        buttons.append([InlineKeyboardButton(
            label, callback_data=f"qch_{picker['quest_id']}_{c['id']}"
        )])
    back_cb = "quest_tab_weekly" if picker.get("type") == "weekly" else "quest_tab_daily"
    back_label = t(lang, "btn_weekly") if picker.get("type") == "weekly" else t(lang, "btn_daily")
    buttons.append([InlineKeyboardButton(back_label, callback_data=back_cb)])

    kb = InlineKeyboardMarkup(buttons)
    text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


def _build_outcome_text(lang: str, cr: dict) -> str:
    """v16.3.5 — render the outcome narrative + a compact delta summary."""
    lines = [t(lang, "qc_outcome_title"), ""]
    if cr.get("result_key"):
        lines.append(t(lang, cr["result_key"]))
        lines.append("")

    karma = cr.get("karma") or {}
    kdelta = int(karma.get("delta") or 0)
    if kdelta:
        sign = "+" if kdelta > 0 else "−"
        band_key = karma.get("label")
        band_label = t(lang, f"karma_label_{band_key}") if band_key else ""
        lines.append(t(lang, "qc_outcome_karma", delta=f"{sign}{abs(kdelta)}", label=band_label))

    stones = int(cr.get("stones_delta") or 0)
    if stones:
        lines.append(t(lang, "qc_outcome_stones", amount=format_number(stones)))

    if cr.get("item_gained"):
        lines.append(t(lang, "qc_bag_full") if cr.get("item_gained_failed") else t(lang, "qc_outcome_item_gained"))
    if cr.get("item_lost"):
        lines.append(t(lang, "qc_outcome_item_lost"))

    return "\n".join(lines)


async def _choose_quest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """v16.3.5 — handle a moral-choice callback ``qch_<quest_id>_<choice_id>``."""
    query = update.callback_query
    await safe_answer(query)

    data = query.data or ""
    rest = data[len("qch_"):]
    head, sep, choice_id = rest.partition("_")  # choice_id may itself contain "_"
    if not sep or not choice_id:
        return
    try:
        quest_id = int(head)
    except ValueError:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        result = await claim_quest_reward(session, player.telegram_id, quest_id, choice_id=choice_id)
        applied = isinstance(result, dict) and "choice_result" in result
        if applied:
            from core.bp_engine import update_bp_mission
            await update_bp_mission(session, player.telegram_id, "complete_quests")

        player_lang = normalize_lang(player.language)
        qtype = "daily"
        if applied:
            quest = (await session.execute(
                select(QuestCatalog).where(QuestCatalog.id == quest_id)
            )).scalar_one_or_none()
            qtype = quest.type if quest else "daily"
        await session.commit()

    # Already claimed (re-click / race) or an error reason → safe, idempotent: no
    # second grant. Surface the same "nothing to claim" message and refresh.
    if not applied:
        await safe_answer(query, t(player_lang, "quest_no_available"), show_alert=True)
        if qtype == "sect":
            # v16.4c — Sect Quests are claimed inside the Sect Hall; keep the
            # member there instead of dumping them onto the generic daily tab.
            # NOTE: get_session_factory is imported at module level (line 16) —
            # a local re-import here would make it a function-local and raise
            # UnboundLocalError at the earlier `async with get_session_factory()`.
            from handlers.sect import _render_sect_quests
            async with get_session_factory()() as session:
                await _render_sect_quests(query, session, player.telegram_id, player_lang)
        elif qtype == "weekly":
            await _weekly_tab(update, context)
        else:
            await _daily_tab(update, context)
        return

    cr = result["choice_result"]
    text = _build_outcome_text(player_lang, cr)
    if qtype == "sect":
        # v16.4c — the moral-fork outcome of a Sect Quest returns to the Sect
        # Hall (cmd_seita_ancia), not the daily quest tab.
        back_cb, back_label = "cmd_seita_ancia", t(player_lang, "btn_back")
    else:
        back_cb = "quest_tab_weekly" if qtype == "weekly" else "quest_tab_daily"
        back_label = t(player_lang, "btn_weekly") if qtype == "weekly" else t(player_lang, "btn_daily")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(back_label, callback_data=back_cb)],
        [InlineKeyboardButton(t(player_lang, "btn_main_menu"), callback_data="cmd_start")],
    ])
    if query.message:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def _claim_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        from core.monetization import get_active_battle_pass
        bp = await get_active_battle_pass(session, player.telegram_id)
        is_premium = bp and bp.is_premium

        rewards, claimed_count = await claim_all_completed(session, player.telegram_id)
        if rewards and claimed_count > 0:
            from core.bp_engine import update_bp_mission
            for _ in range(claimed_count):
                await update_bp_mission(session, player.telegram_id, "complete_quests")
        await session.commit()

    player_lang = normalize_lang(player.language)
    if not rewards:
        await safe_answer(query, t(player_lang, "quest_none_to_claim"), show_alert=True)
        return

    reward_text = _reward_display(rewards)
    await safe_answer(query, t(player_lang, "quest_all_reward_ans", reward=reward_text), show_alert=True)

    await _daily_tab(update, context)


# ═══════════════════════════════════════════════════════════════════════════
# MV-5 — Quests VIVAS (storylets): o bloco no /missoes + o fluxo sty_
# (oferta → diálogo → aceitar/recusar → "Quests aceitas" → concluir).
# Tudo gated por quests_vivas (OFF → o bloco nem renderiza — byte-idêntico).
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_sty_dur(seconds) -> str:
    """segundos -> 'Xh Ym' / 'Ym' compacto (prazo honesto no chat)."""
    s = max(0, int(seconds or 0))
    h, m = s // 3600, (s % 3600) // 60
    if h > 0:
        return f"{h}h{(' ' + str(m) + 'm') if m else ''}"
    return f"{m}m" if m > 0 else f"{s}s"


def _storylet_block(lang: str, sty_data: dict) -> tuple[list, list]:
    """As linhas + botões do bloco 'Quests aceitas' do /missoes."""
    lines = [f"📜 *{t(lang, 'sty_section_title')}*"]
    buttons = []
    offer = sty_data.get("offer")
    if offer:
        lines.append(t(lang, "sty_offer_line", giver=offer.get("giver", "?"), name=offer.get("name", "")))
        buttons.append([InlineKeyboardButton(
            "📜 " + t(lang, "sty_view_offer_btn"), callback_data="sty_view",
        )])
    accepted = sty_data.get("accepted") or []
    for a in accepted:
        status = t(lang, "quest_status_complete") if a.get("is_completed") else ""
        bar = _progress_bar(a.get("progress", 0), a.get("objective_count", 1))
        lines.append(f"{a.get('emoji', '📜')} *{a.get('name', '')}*{status}")
        # QoL 07/08 (report [jogador]) — o OBJETIVO dito + o comando que leva lá. Uma
        # barra "0/3" sem substantivo não é informação (o report nasceu disso).
        if a.get("objective_line"):
            _l = f"  {a['objective_line']}"
            if not a.get("is_completed") and a.get("objective_cmd"):
                _l += f"  ·  {a['objective_cmd']}"
            lines.append(_l)
        lines.append(f"  {bar} {a.get('progress', 0)}/{a.get('objective_count', 1)}")
        if not a.get("is_completed") and a.get("expires_in") is not None:
            lines.append(f"  ⌛ {t(lang, 'sty_deadline', time=_fmt_sty_dur(a['expires_in']))}")
        lines.append(f"  🎁 {a.get('reward_line', '—')}")
        if a.get("is_completed"):
            buttons.append([InlineKeyboardButton(
                "🎁 " + t(lang, "sty_claim_btn", name=a.get("name", "")),
                callback_data=f"sty_claim_{a['id']}",
            )])
    if not offer and not accepted:
        # Empty-state honesto (Lei §1): o mundo fala com quem se move.
        lines.append(t(lang, "sty_empty_chat"))
    lines.append("")
    return lines, buttons


async def _sty_view_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """O diálogo do encontro: 2 falas do giver + Aceitar / Recusar.

    UM answer por callback (lição A Volta: answer vazio ANTES do alerta =
    alerta engolido pelo Telegram) — cada caminho responde exatamente 1 vez."""
    query = update.callback_query
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            await safe_answer(query)
            return
        lang = normalize_lang(player.language)
        from core.storylet_engine import open_offer_view
        offer = await open_offer_view(session, player, lang)
    if not offer:
        # A oferta expirou/já foi respondida entre o render e o tap — o alerta
        # é a ÚNICA resposta deste callback (nunca answer vazio antes).
        await safe_answer(query, t(lang, "sty_offer_gone"), show_alert=True)
        await _daily_tab(update, context)
        return
    await safe_answer(query)
    lines = [
        f"{offer.get('emoji', '📜')} *{offer.get('name', '')}*",
        t(lang, "sty_offer_by", giver=offer.get("giver", "?")),
        "",
        f"_{(offer.get('dialogue') or ['', ''])[0]}_",
        f"_{(offer.get('dialogue') or ['', ''])[1]}_",
        "",
        f"🎯 {offer.get('desc', '')}",
        # QoL 07/08 ([jogador]) — o que a proposta EXIGE, antes de aceitar.
        *([f"*{offer['objective_line']}*"] if offer.get("objective_line") else []),
        f"🎁 {offer.get('reward_line', '—')}",
        f"⌛ {t(lang, 'sty_offer_deadline', hours=offer.get('deadline_hours', 48))}",
    ]
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ " + t(lang, "sty_accept_btn"), callback_data=f"sty_acc_{offer['id']}"),
            InlineKeyboardButton("🚶 " + t(lang, "sty_decline_btn"), callback_data=f"sty_dec_{offer['id']}"),
        ],
        [InlineKeyboardButton(t(lang, "btn_daily"), callback_data="quest_tab_daily")],
    ])
    if query.message:
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


async def _sty_respond(update: Update, context: ContextTypes.DEFAULT_TYPE, accept: bool):
    """Aceitar/recusar (row-locked; recusar é livre — Lei §1)."""
    query = update.callback_query
    prefix = "sty_acc_" if accept else "sty_dec_"
    sid = safe_parse_callback_int(query.data, prefix)
    if sid is None:
        await safe_answer(query)
        return
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query)
            return
        lang = normalize_lang(player.language)
        from core.storylet_engine import respond_offer
        result = await respond_offer(session, player, sid, accept)
        await session.commit()
    # UM answer por callback (lição A Volta: safe_answer vazio antes engole o
    # alerta) — o alerta é a ÚNICA resposta aqui.
    if not result.get("ok"):
        reason = result.get("reason", "sty_offer_gone")
        await safe_answer(query, t(lang, reason if reason.startswith("sty_") else "sty_offer_gone"), show_alert=True)
    elif result.get("accepted"):
        await safe_answer(query, t(lang, "sty_accepted_ans"), show_alert=True)
    else:
        await safe_answer(query, t(lang, "sty_declined_ans"), show_alert=True)
    await _daily_tab(update, context)


async def _sty_claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Concluir a quest viva (player row-locked — a recompensa mexe em pedras)."""
    query = update.callback_query
    sid = safe_parse_callback_int(query.data, "sty_claim_")
    if sid is None:
        await safe_answer(query)
        return
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query)
            return
        lang = normalize_lang(player.language)
        from core.storylet_engine import claim_storylet
        result = await claim_storylet(session, player, sid)
        await session.commit()
    if not result.get("ok"):
        reason = result.get("reason", "sty_nothing_to_claim")
        await safe_answer(query, t(lang, reason if reason.startswith("sty_") else "sty_nothing_to_claim"), show_alert=True)
    else:
        msg = t(lang, "sty_claimed_ans", reward=result.get("reward_line", "—"))
        if result.get("bag_full"):
            msg += "\n" + t(lang, "sty_bag_full")
        await safe_answer(query, msg, show_alert=True)
    await _daily_tab(update, context)


@safe_handler
@rate_limit(1)
async def storylet_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """MV-5 — prefixo sty_ (registrado no combined_button_router do main.py —
    lição MV-2 trv_wev_mine: o prefixo TEM de estar no dispatch antes de usar)."""
    query = update.callback_query
    data = query.data or ""

    if data == "sty_view":
        await _sty_view_offer(update, context)
        return True
    elif data.startswith("sty_acc_"):
        await _sty_respond(update, context, accept=True)
        return True
    elif data.startswith("sty_dec_"):
        await _sty_respond(update, context, accept=False)
        return True
    elif data.startswith("sty_claim_"):
        await _sty_claim(update, context)
        return True

    return False


@safe_handler
@rate_limit(1)
async def quests_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    data = query.data

    if data == "quest_tab_daily":
        await safe_answer(query)
        await _daily_tab(update, context)
        return True
    elif data == "quest_tab_weekly":
        await safe_answer(query)
        await _weekly_tab(update, context)
        return True
    elif data == "quest_tab_streak":
        await safe_answer(query)
        await _streak_tab(update, context)
        return True
    elif data.startswith("quest_claim_all"):
        await _claim_all(update, context)
        return True
    elif data.startswith("quest_claim_"):
        await _claim_quest(update, context)
        return True
    elif data.startswith("qch_"):  # v16.3.5 Karmic Crossroads moral choice
        await _choose_quest(update, context)
        return True

    return False
