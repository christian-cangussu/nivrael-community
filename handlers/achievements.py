import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

from core.achievement_engine import (
    get_player_achievements,
    get_unlocked_titles,
    equip_title,
    toggle_shadow_mode,
    sync_player_snapshot,
)
from core.i18n import t
from core.utils import safe_handler, rate_limit, _ensure_player, escape_markdown, safe_answer, normalize_lang, resolve_chat_player_id
from database.db import get_session_factory
from database.models import Player, PlayerVIP

logger = logging.getLogger(__name__)


def _build_achievements_text(player: Player, achievements: list[tuple], lang: str = "pt") -> str:
    unlocked = sum(1 for _, pa in achievements if pa and pa.unlocked_at)
    total = len(achievements)

    active_title = player.active_title or t(lang, "ach_none")
    lines = [
        t(lang, "ach_title_header", unlocked=unlocked, total=total),
        t(lang, "ach_active_title", title=active_title),
        "————————————————————————",
    ]

    for ach, pa in achievements:
        if pa and pa.unlocked_at:
            status = "✅"
            prog = f"{pa.progress}/{ach.target_value}"
        elif pa and pa.progress > 0:
            status = "🔄"
            prog = f"{pa.progress}/{ach.target_value}"
        else:
            status = "🔒"
            prog = f"0/{ach.target_value}"

        # QoL 04/08 (report [jogador]) — o título é HONORÍFICO e o bônus é da
        # CONQUISTA. Antes as duas coisas colavam na mesma linha e ensinavam
        # "vestir o título dá o bônus"; agora o título traz a marca do que é.
        title_str = (f" → *[{ach.title_granted}]* {t(lang, 'ach_title_honorary_tag')}"
                     if ach.title_granted else "")
        # E o número só aparece se ESTE mundo aplicar o bônus (uma verdade:
        # achievement_engine.bonus_display). Na main isto silencia o "+105%".
        bonus_str = ""
        try:
            from core.achievement_engine import bonus_display as _bd
            _rows = _bd(ach.stat_bonus)
        except Exception:
            _rows = []
        if _rows:
            parts = [f"+{r['pct']:.0f}% {t(lang, r['label_key'])}" for r in _rows]
            bonus_str = f" ({', '.join(parts)})"

        # Escape underscores in description to avoid Markdown parse errors
        safe_desc = ach.description.replace("_", "\\_")
        lines.append(f"{status} {ach.emoji} *{ach.name}* ({prog}){title_str}{bonus_str}")
        lines.append(f"   _{safe_desc}_")

    return "\n".join(lines)


def _build_titles_keyboard(player: Player, titles: list[str], lang: str) -> InlineKeyboardMarkup:
    rows = []
    for title in titles:
        active_marker = " ✓" if player.active_title == title else ""
        rows.append([InlineKeyboardButton(
            f"[{title}]{active_marker}",
            callback_data=f"ach_equip_{title[:32]}",
        )])

    if player.active_title:
        rows.append([InlineKeyboardButton(t(lang, "btn_remove_title"), callback_data="ach_equip_none")])

    rows.append([InlineKeyboardButton(t(lang, "btn_back_achievements"), callback_data="ach_main")])
    return InlineKeyboardMarkup(rows)


@safe_handler
@rate_limit(1)
async def conquistas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"

        # Sync current stats retroactively (realm, jade, prestige, beasts)
        await sync_player_snapshot(session, player)
        await session.commit()

        achievements = await get_player_achievements(session, player.telegram_id)
        text = _build_achievements_text(player, achievements, lang)

        vip_row = (await session.execute(
            select(PlayerVIP).where(PlayerVIP.player_id == player.telegram_id)
        )).scalar_one_or_none()
        vip_level = vip_row.vip_level if vip_row else 0

        kb_rows = [
            [InlineKeyboardButton(t(lang, "btn_equip_title"), callback_data="ach_titles")],
        ]
        if vip_level >= 3:
            shadow_label = t(lang, "btn_shadow_on") if player.shadow_mode else t(lang, "btn_shadow_off")
            kb_rows.append([InlineKeyboardButton(shadow_label, callback_data="ach_shadow")])
        kb_rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_cultivo")])

        kb = InlineKeyboardMarkup(kb_rows)

        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def achievements_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("ach_"):
        return False

    await safe_answer(query)
    data = query.data
    user = update.effective_user

    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(user.id))
        )).scalar_one_or_none()
        if not player:
            lang = normalize_lang(getattr(user, "language_code", None))
            await query.message.edit_text(t(lang, "ach_start_required"))
            return True

        lang = player.language or "en"

        vip_row = (await session.execute(
            select(PlayerVIP).where(PlayerVIP.player_id == user.id)
        )).scalar_one_or_none()
        vip_level = vip_row.vip_level if vip_row else 0

        # ── Main achievement list ──────────────────────────────────────────
        if data == "ach_main":
            achievements = await get_player_achievements(session, player.telegram_id)
            text = _build_achievements_text(player, achievements, lang)
            kb_rows = [
                [InlineKeyboardButton(t(lang, "btn_equip_title"), callback_data="ach_titles")],
            ]
            if vip_level >= 3:
                shadow_label = t(lang, "btn_shadow_on") if player.shadow_mode else t(lang, "btn_shadow_off")
                kb_rows.append([InlineKeyboardButton(shadow_label, callback_data="ach_shadow")])
            kb_rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_cultivo")])
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb_rows))
            return True

        # ── Title list ────────────────────────────────────────────────────
        if data == "ach_titles":
            titles = await get_unlocked_titles(session, player.telegram_id)
            if not titles:
                await query.message.edit_text(
                    t(lang, "ach_no_titles"),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(t(lang, "btn_back_achievements"), callback_data="ach_main")
                    ]]),
                )
                return True

            active_title = player.active_title or t(lang, "ach_none")
            text = t(lang, "ach_titles_menu", title=active_title)
            # QoL 04/08 (report [jogador]: "titles are not indicating their
            # benefits") — a resposta honesta é que o benefício é PRESTÍGIO.
            # Título é honorífico por decisão de design (Lei §4: jade nunca
            # compra poder, e há títulos que vêm de marcos VIP/Passe) — o que
            # faltava era a tela DIZER isso (Lei §1).
            text += "\n\n" + t(lang, "ach_title_honorary_note")
            # TAPETE QoL §5 item 10 ([jogador]): extra titles (monetization/BP/
            # prestige) used to be bare buttons — now each lists what it is.
            from core.achievement_engine import EXTRA_TITLE_DESC_KEYS
            desc_lines = []
            for title_name in titles:
                key = EXTRA_TITLE_DESC_KEYS.get(title_name)
                if key:
                    desc_lines.append(f"🎖️ *[{title_name}]*\n  _{t(lang, key)}_")
            if desc_lines:
                text += "\n\n" + "\n".join(desc_lines)
            kb = _build_titles_keyboard(player, titles, lang)
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return True

        # ── Equip title ───────────────────────────────────────────────────
        if data.startswith("ach_equip_"):
            raw = data[len("ach_equip_"):]
            title_to_equip = None if raw == "none" else raw

            success = await equip_title(session, player.telegram_id, title_to_equip)
            await session.commit()

            if success:
                msg = (
                    t(lang, "ach_equip_success", title=title_to_equip) if title_to_equip
                    else t(lang, "ach_remove_success")
                )
            else:
                msg = t(lang, "ach_equip_fail")

            await query.message.edit_text(
                msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t(lang, "btn_back_achievements"), callback_data="ach_main")
                ]]),
            )
            return True

        # ── Shadow mode toggle ────────────────────────────────────────────
        if data == "ach_shadow":
            success, new_state = await toggle_shadow_mode(session, player.telegram_id, vip_level)
            await session.commit()

            if not success:
                await safe_answer(query, t(lang, "ach_shadow_vip_req"), show_alert=True)
                return True

            msg = t(lang, "ach_shadow_on") if new_state else t(lang, "ach_shadow_off")
            await query.message.edit_text(
                msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t(lang, "btn_back_achievements"), callback_data="ach_main")
                ]]),
            )
            return True

    return False


async def notify_achievements(context, chat_id: int, unlocked: list) -> None:
    """Send a notification message for newly unlocked achievements."""
    if not unlocked:
        return

    # Fetch player language for notification
    try:
        async with get_session_factory()() as session:
            player = (await session.execute(
                select(Player).where(Player.telegram_id == chat_id)
            )).scalar_one_or_none()
            lang = player.language or "en"
    except Exception:
        lang = "en"

    lines = [t(lang, "ach_unlocked_notification")]
    for ach in unlocked:
        lines.append(f"{ach.emoji} *{escape_markdown(ach.name)}*")
        lines.append(f"_{escape_markdown(ach.description)}_")
        if ach.title_granted:
            lines.append(f"🎖️ *[{escape_markdown(ach.title_granted)}]*")
        # QoL 04/08 — a MESMA verdade da lista: só se anuncia o bônus que este
        # mundo aplica. Era aqui a 3ª cópia da conta que dizia "+105%" na main,
        # e no momento em que o jogador mais presta atenção.
        try:
            from core.achievement_engine import bonus_display as _bd
            _rows = _bd(ach.stat_bonus)
        except Exception:
            _rows = []
        if _rows:
            lines.append("📈 " + ", ".join(
                f"+{r['pct']:.0f}% {t(lang, r['label_key'])}" for r in _rows))
        lines.append("")

    try:
        await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.warning("Failed to send achievement notification: %s", e)

    # v15.1.2 — also push to the mini-app bell so the player sees it without
    # opening the chat DM. Persistent + dedup'd via achievement code.
    try:
        from core.notification_engine import notify as _notify
        async with get_session_factory()() as session:
            for ach in unlocked:
                await _notify(
                    session, chat_id, "achievement_unlock",
                    title_key="notif_achievement_title",
                    body_key="notif_achievement_body",
                    payload={"name": ach.name, "emoji": ach.emoji or "🏆"},
                    ref_id=f"ach:{ach.code}" if hasattr(ach, "code") else f"ach:{ach.id}",
                    icon=ach.emoji or "🏆",
                    target_tab="achievements",
                    priority=3,
                )
                if ach.title_granted:
                    await _notify(
                        session, chat_id, "title_unlock",
                        title_key="notif_title_title",
                        body_key="notif_title_body",
                        payload={"title": ach.title_granted},
                        ref_id=f"title:{ach.title_granted}",
                        icon="🎖️",
                        target_tab="profile",
                        priority=2,
                    )
            await session.commit()
    except Exception:
        logger.exception("achievement bell notify failed for chat_id=%s", chat_id)
