"""MV-7 — /oficio: a Guilda dos Ofícios no chat (cerimônia + status + troca).

Profissão NÃO é setting (não vive no /conf) — é identidade: entrada pela
praça/HubMundo no mini-app e por este comando no chat. Prefixo de callback
`prf_` (registrado no combined_button_router ANTES de qualquer botão emitir —
lição MV-2). UM answer por callback (lição A Volta): no caminho stale/erro o
ALERTA é a resposta; nunca um safe_answer() vazio antes dele.

Gated `profissoes` (OFF → mensagem honesta de salões fechados, Lei §1 — o
mundo main nunca emite botões prf_ porque o /oficio responde locked)."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from sqlalchemy import select

from core.i18n import t
from core.utils import (_ensure_player, normalize_lang, rate_limit,
                        safe_answer, safe_handler)
from database.db import get_session_factory
from database.models import Player

logger = logging.getLogger(__name__)


def _bar(xp: int, floor: int, nxt: int | None, width: int = 10) -> str:
    """Barra de XP em texto (progressão visível)."""
    if nxt is None:
        return "█" * width
    span = max(1, nxt - floor)
    filled = max(0, min(width, int(round(width * (xp - floor) / span))))
    return "█" * filled + "░" * (width - filled)


def _render_status(view: dict, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        f"{view['emoji']} *{view['name']}* — {view['tier_name']} ({view['tier']}/4)",
        "",
    ]
    if view.get("xp_next") is not None:
        lines.append(f"`{_bar(view['xp'], view['xp_floor'], view['xp_next'])}` "
                     f"{view['xp']}/{view['xp_next']} XP")
    else:
        lines.append(f"`{_bar(view['xp'], view['xp_floor'], None)}` "
                     + t(lang, "prf_tier_max"))
    lines.append("")
    for b in view.get("bonuses", []):
        lines.append(f"• {b}")
    lines.append("")
    if view.get("in_native"):
        lines.append(t(lang, "prf_in_native", native=view["native_name"],
                       mult=f"{view['xp_mult']:g}"))
    else:
        lines.append(t(lang, "prf_native_travel", native=view["native_name"]))
    if view.get("rep_synergy_line"):
        lines.append(view["rep_synergy_line"])
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "prf_btn_swap"), callback_data="prf_swap"),
    ]])
    return "\n".join(lines), kb


def _render_ceremony(view: dict, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    lines = [f"🏮 *{t(lang, 'prf_ceremony_title')}*", "",
             t(lang, "prf_ceremony_intro"), ""]
    buttons = []
    for c in view.get("choices", []):
        lines.append(f"{c['emoji']} *{c['name']}* — {c['desc']}")
        lines.append(t(lang, "prf_native_line", native=c["native_name"]))
        lines.append("")
        buttons.append([InlineKeyboardButton(
            f"{c['emoji']} {c['name']}", callback_data=f"prf_pick_{c['key']}")])
    lines.append(t(lang, "prf_future_teaser"))
    lines.append("_" + ", ".join(view.get("future", [])) + "_")
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _render_view(session, player, lang: str) -> tuple[str, InlineKeyboardMarkup | None]:
    from core.profession_engine import get_profession_view
    view = await get_profession_view(session, player, lang)
    if view is None:
        return t(lang, "prf_locked_msg"), None
    if view.get("has"):
        return _render_status(view, lang)
    return _render_ceremony(view, lang)


@safe_handler
@rate_limit(1)
async def oficio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language or "pt")
        text, kb = await _render_view(session, player, lang)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


def _confirm_text(key: str, lang: str, view: dict, switching: bool) -> str:
    choice = next((c for c in view.get("choices", []) if c["key"] == key), None)
    name = choice["name"] if choice else key
    emoji = choice["emoji"] if choice else "🏮"
    native = choice["native_name"] if choice else ""
    lines = [f"{emoji} *{name}*", ""]
    if choice:
        lines.append(choice["desc"])
        lines.append(t(lang, "prf_native_line", native=native))
        lines.append("")
    if switching:
        lines.append(t(lang, "prf_swap_warn", cost=view.get("switch_cost", 0)))
    else:
        lines.append(t(lang, "prf_confirm_warn", cost=view.get("switch_cost", 0)))
    return "\n".join(lines)


async def profession_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `prf_*` callbacks (MV-7). Returns True if handled.

    TODO prf_* responde e retorna True — um sub-callback desconhecido nunca
    cai no button_router genérico (botão girando = violação Lei §1)."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("prf_"):
        return False
    data = query.data

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            await safe_answer(query)
            return True
        lang = normalize_lang(player.language or "pt")

        from core.profession_engine import (PROFESSIONS, choose_profession,
                                            get_profession_view, profissoes_on,
                                            switch_profession)
        if not profissoes_on():
            await safe_answer(query, t(lang, "prf_locked_msg"), show_alert=True)
            return True

        # ── voltar ao menu ──
        if data == "prf_menu":
            await safe_answer(query)
            text, kb = await _render_view(session, player, lang)
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return True

        # ── cerimônia: escolher (tela de confirmação) ──
        if data.startswith("prf_pick_"):
            key = data[len("prf_pick_"):]
            if key not in PROFESSIONS:
                await safe_answer(query, t(lang, "prf_gone"), show_alert=True)
                return True
            view = await get_profession_view(session, player, lang)
            if view is None or view.get("has"):
                # Stale: já tem ofício (outro clique ganhou) — o alerta É a resposta.
                await safe_answer(query, t(lang, "prf_already"), show_alert=True)
                return True
            await safe_answer(query)
            text = _confirm_text(key, lang, view, switching=False)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "prf_btn_confirm"),
                                      callback_data=f"prf_conf_{key}")],
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="prf_menu")],
            ])
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return True

        # ── cerimônia: confirmar ──
        if data.startswith("prf_conf_"):
            key = data[len("prf_conf_"):]
            locked = (await session.execute(
                select(Player).where(Player.telegram_id == player.telegram_id)
                .with_for_update()
            )).scalar_one_or_none()
            if not locked:
                await safe_answer(query)
                return True
            result = await choose_profession(session, locked, key, lang)
            if not result.get("ok"):
                reason = result.get("reason")
                msg = t(lang, "prf_already") if reason == "prf_has" else t(lang, "prf_gone")
                await safe_answer(query, msg, show_alert=True)
                return True
            await session.commit()
            await safe_answer(query, t(lang, "prf_chosen_toast"), show_alert=False)
            text, kb = await _render_view(session, locked, lang)
            text = t(lang, "prf_chosen_header") + "\n\n" + text
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return True

        # ── troca: lista de destinos ──
        if data == "prf_swap":
            view = await get_profession_view(session, player, lang)
            if view is None or not view.get("has"):
                await safe_answer(query, t(lang, "prf_gone"), show_alert=True)
                return True
            await safe_answer(query)
            from core.profession_engine import PROF_SWITCH_COST
            lines = [t(lang, "prf_swap_title"), "",
                     t(lang, "prf_swap_warn", cost=PROF_SWITCH_COST)]
            buttons = []
            for k, m in PROFESSIONS.items():
                if k == view.get("key"):
                    continue
                buttons.append([InlineKeyboardButton(
                    f"{m['emoji']} {t(lang, f'prf_name_{k}')}",
                    callback_data=f"prf_swpc_{k}")])
            buttons.append([InlineKeyboardButton(t(lang, "btn_back"),
                                                 callback_data="prf_menu")])
            await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(buttons))
            return True

        # ── troca: confirmar destino ──
        if data.startswith("prf_swpc_"):
            key = data[len("prf_swpc_"):]
            if key not in PROFESSIONS:
                await safe_answer(query, t(lang, "prf_gone"), show_alert=True)
                return True
            view = await get_profession_view(session, player, lang)
            if view is None:
                await safe_answer(query, t(lang, "prf_gone"), show_alert=True)
                return True
            # Reusa a tela de escolha (choices só existe no view sem ofício) —
            # monta um view mínimo para o texto de confirmação.
            from core.profession_engine import PROF_SWITCH_COST
            fake = {"choices": [{
                "key": key,
                "emoji": PROFESSIONS[key]["emoji"],
                "name": t(lang, f"prf_name_{key}"),
                "desc": t(lang, f"prf_desc_{key}"),
                "native_name": t(lang, f"continent_{PROFESSIONS[key]['native']}"),
            }], "switch_cost": PROF_SWITCH_COST}
            await safe_answer(query)
            text = _confirm_text(key, lang, fake, switching=True)
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "prf_btn_confirm"),
                                      callback_data=f"prf_swpx_{key}")],
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="prf_menu")],
            ])
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return True

        # ── troca: executar ──
        if data.startswith("prf_swpx_"):
            key = data[len("prf_swpx_"):]
            locked = (await session.execute(
                select(Player).where(Player.telegram_id == player.telegram_id)
                .with_for_update()
            )).scalar_one_or_none()
            if not locked:
                await safe_answer(query)
                return True
            result = await switch_profession(session, locked, key, lang)
            if not result.get("ok"):
                reason = result.get("reason")
                if reason == "prf_no_stones":
                    msg = t(lang, "prf_no_stones", cost=result.get("cost", 0),
                            have=result.get("have", 0))
                elif reason == "prf_same":
                    msg = t(lang, "prf_already")
                else:
                    msg = t(lang, "prf_gone")
                await safe_answer(query, msg, show_alert=True)
                return True
            await session.commit()
            await safe_answer(query, t(lang, "prf_swapped_toast"), show_alert=False)
            text, kb = await _render_view(session, locked, lang)
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return True

        # Sub-callback prf_ desconhecido: responde e MORRE aqui (nunca cai no
        # button_router genérico — botão girando, lição MV-2).
        await safe_answer(query)
        return True
