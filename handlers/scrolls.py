"""TEC-2 — /pergaminhos: o DESTINO do pergaminho no chat.

Superfície LEVE (a canônica é o mini — TechniqueDetailModal → seção 📜). Lista
a arca inteira de pergaminhos e, por pergaminho, os dois destinos novos:

    📚 Doar à Biblioteca da casa → contribuição (SALDO do Pavilhão; a escada
       de posto NUNCA se move — Lei §4, o jade entrega pergaminho).
    🔥 Queimar no Ritual de Compreensão → XP de Intenção no caminho que a
       PRÓPRIA arte carrega (+ fragmento de Dao no topo da escada).

Ambos funcionam em pergaminho APRENDIDO ou não — é aqui que morre o beco sem
saída vivo desde sempre: o pergaminho de uma arte que você não pode aprender
(reino baixo / raiz errada / Dao trancado) não tinha botão NENHUM em superfície
alguma e entupia o anel para sempre (Lei §1).

Prefixo de callback `scr_` (registrado no combined_button_router ANTES de
qualquer botão emitir — lição MV-2). UM answer por callback (lição A Volta).
Gated `escassez_scrolls` (OFF → mensagem honesta; main nunca emite botões scr_).
"""

import logging
import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.i18n import t
from core.utils import (_ensure_player, build_pagination_keyboard,
                        escape_markdown, normalize_lang, rate_limit,
                        safe_answer, safe_handler)
from database.db import get_session_factory

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 6


def _tier_label(lang: str, tier: int) -> str:
    return t(lang, f"scr_tier_{tier}")


# De onde o cultivador entrou na arca — o "Voltar" tem de o devolver ao MESMO
# lugar (review TEC-2: quem entrava pela Biblioteca era despejado no menu de
# combate). Guardado por jogador em context.user_data; default = combate.
_BACK_TARGETS = {"lib": "lib_menu", "pvp": "pvp_techniques_menu"}


def _back_target(context) -> str:
    try:
        return _BACK_TARGETS.get(context.user_data.get("scr_back"), "pvp_techniques_menu")
    except Exception:
        return "pvp_techniques_menu"


def _render_list(view: dict, lang: str, page: int,
                 back: str = "pvp_techniques_menu") -> tuple[str, InlineKeyboardMarkup]:
    scrolls = view.get("scrolls", [])
    lines = [f"📜 *{t(lang, 'scr_title')}*", ""]
    buttons: list[list[InlineKeyboardButton]] = []

    if not scrolls:
        lines.append(t(lang, "scr_empty"))
        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=back)])
        return "\n".join(lines), InlineKeyboardMarkup(buttons)

    lines.append(t(lang, "scr_intro"))
    lines.append("")

    total_pages = max(1, math.ceil(len(scrolls) / ITEMS_PER_PAGE))
    page = max(0, min(page - 1, total_pages - 1))
    for s in scrolls[page * ITEMS_PER_PAGE:(page + 1) * ITEMS_PER_PAGE]:
        known = " ✅" if s["learned"] else ""
        lines.append(
            f"{s['emoji']} *{escape_markdown(s['name'])}*{known} ×{s['qty']} "
            f"· {_tier_label(lang, s['tier'])}"
        )
        buttons.append([InlineKeyboardButton(
            f"{s['emoji']} {s['name']} ×{s['qty']}",
            callback_data=f"scr_v_{s['tech_id']}",
        )])
    lines.append("")
    if view.get("in_sect"):
        lines.append(t(lang, "scr_balance_line", balance=view.get("balance", 0),
                       headroom=view.get("headroom", 0)))
    else:
        lines.append(t(lang, "scr_no_sect_hint"))

    if total_pages > 1:
        buttons.extend(build_pagination_keyboard(page + 1, total_pages, "scr_p", lang))
    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=back)])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _render_one(s: dict, view: dict, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    """A tela de destino de UM pergaminho — os dois caminhos, com os números
    ANTES do tap (o confirm é este ecrã; o commit é o botão)."""
    lines = [
        f"{s['emoji']} *{escape_markdown(s['name'])}* ×{s['qty']}",
        f"_{_tier_label(lang, s['tier'])}_",
        "",
    ]
    buttons: list[list[InlineKeyboardButton]] = []

    # 📚 Doar
    lines.append(t(lang, "scr_donate_head", cp=s["donate_cp"]))
    if s["can_donate"]:
        lines.append(t(lang, "scr_donate_after",
                       before=view.get("balance", 0),
                       after=view.get("balance", 0) + s["donate_cp"]))
        buttons.append([InlineKeyboardButton(
            t(lang, "scr_btn_donate_one", cp=s["donate_cp"]),
            callback_data=f"scr_dc_{s['tech_id']}_1",
        )])
        # "tudo" limitado pelo estoque E pelo teto do dia (o engine reclampa).
        fits = max(1, view.get("headroom", 0) // max(1, s["donate_cp"]))
        bulk = min(s["qty"], fits, view.get("max_batch", 20))
        if bulk > 1:
            buttons.append([InlineKeyboardButton(
                t(lang, "scr_btn_donate_all", n=bulk, cp=s["donate_cp"] * bulk),
                callback_data=f"scr_dc_{s['tech_id']}_{bulk}",
            )])
    elif s.get("donate_block") == "no_sect":
        lines.append(t(lang, "scr_donate_block_sect"))
    else:
        lines.append(t(lang, "scr_donate_block_cap", cap=view.get("cap", 0)))
    lines.append("")

    # 🔥 Queimar
    intent_name = t(lang, f"intent_name_{s['burn_intent']}")
    lines.append(t(lang, "scr_burn_head", xp=s["burn_xp"], intent=intent_name))
    if s.get("burn_dao"):
        lines.append(t(lang, "scr_burn_dao", n=s["burn_dao"]))
    buttons.append([InlineKeyboardButton(
        t(lang, "scr_btn_burn_one", xp=s["burn_xp"]),
        callback_data=f"scr_bc_{s['tech_id']}_1",
    )])
    if s["qty"] > 1:
        bulk = min(s["qty"], view.get("max_batch", 20))
        buttons.append([InlineKeyboardButton(
            t(lang, "scr_btn_burn_all", n=bulk, xp=s["burn_xp"] * bulk),
            callback_data=f"scr_bc_{s['tech_id']}_{bulk}",
        )])

    lines.append("")
    lines.append(t(lang, "scr_other_paths_hint"))
    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="scr_menu")])
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def _render_for(session, player, lang: str, page: int = 1):
    from core.scroll_economy_engine import escassez_on, list_scrolls
    if not escassez_on():
        return t(lang, "scr_locked_msg"), None
    view = await list_scrolls(session, int(player.telegram_id), lang)
    if not view.get("on"):
        return t(lang, "scr_locked_msg"), None
    return _render_list(view, lang, page)


@safe_handler
@rate_limit(1)
async def pergaminhos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language or "pt")
        text, kb = await _render_for(session, player, lang)
    # /pergaminhos e uma entrada propria — o "Voltar" volta ao menu de combate.
    context.user_data["scr_back"] = "pvp"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def _safe_edit(query, text: str, kb) -> None:
    """edit_text tolerante a double-tap (padrão TEC-1 F10)."""
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


def _parse_action(data: str, prefix: str) -> tuple[int, int] | None:
    """`scr_dc_<tech_id>_<qty>` → (tech_id, qty). None se malformado."""
    try:
        tech_id, qty = data[len(prefix):].split("_", 1)
        return int(tech_id), max(1, int(qty))
    except (ValueError, IndexError):
        return None


async def scroll_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `scr_*` callbacks (TEC-2). Returns True if handled.

    TODO scr_* responde e retorna True — um sub-callback desconhecido nunca cai
    no router genérico (botão girando = violação Lei §1)."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("scr_"):
        return False
    data = query.data

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            await safe_answer(query)
            return True
        lang = normalize_lang(player.language or "pt")
        pid = int(player.telegram_id)

        from core.scroll_economy_engine import (burn_scroll, donate_scroll,
                                                escassez_on, list_scrolls)
        if not escassez_on():
            await safe_answer(query, t(lang, "scr_locked_msg"), show_alert=True)
            return True

        # ── lista / paginação (scr_open_<origem> memoriza o "Voltar") ──
        if data.startswith("scr_open_"):
            try:
                context.user_data["scr_back"] = data[len("scr_open_"):]
            except Exception:
                pass
            data = "scr_menu"
        if data == "scr_menu" or data.startswith("scr_p"):
            page = 1
            if data.startswith("scr_p"):
                try:
                    page = max(1, int(data[len("scr_p"):]))
                except ValueError:
                    page = 1
            await safe_answer(query)
            view = await list_scrolls(session, pid, lang)
            text, kb = _render_list(view, lang, page, _back_target(context))
            await _safe_edit(query, text, kb)
            return True

        # ── o ecrã de destino de um pergaminho ──
        if data.startswith("scr_v_"):
            try:
                tech_id = int(data[len("scr_v_"):])
            except ValueError:
                await safe_answer(query)
                return True
            view = await list_scrolls(session, pid, lang)
            s = next((x for x in view.get("scrolls", []) if x["tech_id"] == tech_id), None)
            if s is None:
                await safe_answer(query, t(lang, "scr_stale"), show_alert=True)
                return True
            await safe_answer(query)
            text, kb = _render_one(s, view, lang)
            await _safe_edit(query, text, kb)
            return True

        # ── commit: doar ──
        if data.startswith("scr_dc_"):
            parsed = _parse_action(data, "scr_dc_")
            if parsed is None:
                await safe_answer(query)
                return True
            tech_id, qty = parsed
            res = await donate_scroll(session, pid, tech_id, qty)
            if not res.get("ok"):
                reason = res.get("reason") or ""
                if reason == "not_in_sect":
                    msg = t(lang, "scr_donate_block_sect")
                elif reason == "daily_cap":
                    msg = t(lang, "scr_donate_block_cap", cap=res.get("cap", 0))
                else:
                    msg = t(lang, "scr_stale")
                await safe_answer(query, msg, show_alert=True)
                return True
            await session.commit()
            await safe_answer(query, t(lang, "scr_donated_toast", cp=res["cp_gained"]))
            lines = [
                t(lang, "scr_donated_header", emoji=res["emoji"],
                  name=escape_markdown(res["name"]), n=res["qty"]),
                "",
                t(lang, "scr_donated_delta", before=res["balance_before"],
                  after=res["balance_after"], cp=res["cp_gained"]),
                t(lang, "scr_donated_rank_note"),
            ]
            if res.get("partial"):
                key = ("scr_partial_cap" if res.get("capped_by") == "cap"
                       else "scr_partial_stock")
                lines.append(t(lang, key, n=res["qty"], asked=res["requested"]))
            lines.append(t(lang, "scr_headroom_left", headroom=res["headroom_after"]))
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(t(lang, "btn_back"), callback_data="scr_menu")]])
            await _safe_edit(query, "\n".join(lines), kb)
            return True

        # ── commit: queimar ──
        if data.startswith("scr_bc_"):
            parsed = _parse_action(data, "scr_bc_")
            if parsed is None:
                await safe_answer(query)
                return True
            tech_id, qty = parsed
            res = await burn_scroll(session, pid, tech_id, qty)
            if not res.get("ok"):
                await safe_answer(query, t(lang, "scr_stale"), show_alert=True)
                return True
            await session.commit()
            await safe_answer(query, t(lang, "scr_burned_toast", xp=res["xp_gained"]))
            intent_name = t(lang, f"intent_name_{res['intent']}")
            lines = [
                t(lang, "scr_burned_header", emoji=res["emoji"],
                  name=escape_markdown(res["name"]), n=res["qty"]),
                "",
                t(lang, "scr_burned_delta", intent=intent_name,
                  xp=res["xp_gained"], before=res["rank_before"],
                  after=res["rank_after"]),
            ]
            if res.get("leveled_up"):
                lines.append(t(lang, "scr_burned_rankup", intent=intent_name,
                               rank=res["rank_after"]))
            for f in res.get("dao_fragments", []):
                lines.append(t(lang, "scr_burned_dao_line",
                               emoji=f.get("emoji") or "💠",
                               law=f.get("law") or "?",
                               frag=f.get("fragments") or 0,
                               total=f.get("total") or 0))
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(t(lang, "btn_back"), callback_data="scr_menu")]])
            await _safe_edit(query, "\n".join(lines), kb)
            return True

        # Sub-callback scr_ desconhecido: responde e MORRE aqui (lição MV-2).
        await safe_answer(query)
        return True
