"""TEC-5 — /coracao: o Rito do Coração-Demônio 心魔 no chat.

Superfície LEVE (a canônica é o mini — KarmaModal → card da divergência): diz o
estado do Coração (divergiu? quanto falta? o Rito está de castigo?), abre o
duelo contra O REFLEXO com auto-play (padrão `lib_rite_` do TEC-3) e oferece a
ESCOLHA depois da vitória — ⚔️ ATRAVESSAR (re-cristaliza o Caminho, com o preço
da casa DITO antes) ou 🧘 REAFIRMAR (livre).

Prefixo de callback `fpd_` (registrado no combined_button_router ANTES de
qualquer botão o emitir — lição MV-2). UM answer por callback (lição A Volta):
no caminho stale/erro o ALERTA é a resposta. Gated `forbidden_path` (OFF →
mensagem honesta, Lei §1 — nenhum mundo vivo emite botões `fpd_`).
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.i18n import t
from core.utils import (_ensure_player, normalize_lang, rate_limit,
                        safe_answer, safe_handler)
from database.db import get_session_factory

logger = logging.getLogger(__name__)


def _hours_until(ms: int) -> int:
    """Horas (arredondadas para cima, piso 1) até um timestamp em ms."""
    try:
        from datetime import datetime, timezone
        delta = int(ms) / 1000.0 - datetime.now(timezone.utc).timestamp()
        return max(1, int(-(-delta // 3600)))
    except Exception:
        return 1


def forbidden_cost_line(lang: str, cost: dict) -> str:
    """O cartão do custo no resumo de duelo do CHAT (o mini rende o banner
    próprio). UMA função — os dois lugares que mostram resultado de duelo com
    DuelSession no chat (a Gruta e o Rito) leem daqui, e nunca re-derivam
    (display = roll). Cost = o payload `forbidden_cost` do settle."""
    try:
        parts = [t(lang, "fpd_chat_cost_karma",
                   uses=int(cost.get("uses") or 0),
                   karma=abs(int(cost.get("karma_delta") or 0)),
                   before=int(cost.get("karma_before") or 0),
                   after=int(cost.get("karma_after") or 0))]
        if not cost.get("immortal") and int(cost.get("years_burned") or 0) > 0:
            parts.append(t(lang, "fpd_chat_cost_years",
                           years=int(cost.get("years_burned") or 0),
                           before=int(cost.get("age_before") or 0),
                           after=int(cost.get("age_after") or 0),
                           ceiling=int(cost.get("ceiling") or 0)))
        if cost.get("exhausted"):
            parts.append(t(lang, "fpd_chat_cost_exhausted"))
        return "\n".join(parts)
    except Exception:
        logger.debug("forbidden_cost_line failed", exc_info=True)
        return ""


def _path_label(lang: str, path: str | None) -> str:
    if path in ("righteous", "demonic", "rogue"):
        return t(lang, f"path_{path}")   # path_righteous/_demonic/_rogue (já existem)
    return "—"


async def _render_state(session, player, lang: str):
    """A tela do Coração-Demônio (texto + teclado). Nunca levanta."""
    from core.forbidden_path_engine import (
        forbidden_on, heart_demon_state, lifespan_state, sect_cross_preview,
    )
    if not forbidden_on():
        return t(lang, "fpd_locked_msg"), None

    st = await heart_demon_state(session, player)
    life = lifespan_state(player)
    lines = [f"👁️ *{t(lang, 'fpd_title')}*", ""]
    buttons: list[list[InlineKeyboardButton]] = []

    lines.append(t(lang, "fpd_path_line",
                   path=_path_label(lang, st.get("current_path")),
                   karma=int(st.get("karma") or 0)))

    # O Mar de Longevidade — o relógio, sempre DITO (Lei §1/§10).
    if life.get("immortal"):
        lines.append(t(lang, "fpd_life_immortal"))
    else:
        lines.append(t(lang, "fpd_life_line",
                       age=int(life.get("age_years") or 0),
                       ceiling=int(life.get("ceiling") or 0),
                       per_use=int(life.get("years_per_use") or 0)))
        if life.get("uses_left") is not None:
            lines.append(t(lang, "fpd_life_uses", uses=int(life["uses_left"])))
    lines.append("")

    if st.get("pending_choice_duel_id"):
        # Venceu e ainda não escolheu — a escolha É o próximo passo. Sem
        # divergência não há para onde atravessar (você JÁ é isso): só reafirmar.
        target = st.get("target_path")
        if target:
            lines.append(t(lang, "fpd_choice_header",
                           target=_path_label(lang, target)))
            cost = await sect_cross_preview(session, player)
            if cost:
                lines.append(t(lang, "fpd_choice_sect_cost",
                               karma=abs(int(cost.get("karma_cost") or 0))))
            buttons.append([InlineKeyboardButton(
                t(lang, "fpd_btn_cross"), callback_data="fpd_cross")])
        else:
            lines.append(t(lang, "fpd_choice_header_deep"))
        buttons.append([InlineKeyboardButton(
            t(lang, "fpd_btn_stand"), callback_data="fpd_stand")])
    elif st.get("open_duel_id"):
        lines.append(t(lang, "fpd_open_duel"))
        buttons.append([InlineKeyboardButton(
            t(lang, "fpd_btn_start"), callback_data="fpd_start")])
    elif st.get("cooldown_ms"):
        lines.append(t(lang, "fpd_cooldown",
                       hours=_hours_until(st["cooldown_ms"])))
    elif st.get("diverged"):
        lines.append(t(lang, "fpd_diverged",
                       target=_path_label(lang, st.get("target_path"))))
        buttons.append([InlineKeyboardButton(
            t(lang, "fpd_btn_start"), callback_data="fpd_start")])
    elif st.get("deep"):
        # A 2ª porta: fundo demais na PRÓPRIA estrada — o Reflexo levanta-se
        # para perguntar se é mesmo isso que você é.
        lines.append(t(lang, "fpd_deep", have=int(st.get("deep_have") or 0),
                       need=int(st.get("deep_need") or 0)))
        buttons.append([InlineKeyboardButton(
            t(lang, "fpd_btn_start"), callback_data="fpd_start")])
    else:
        # Não divergiu: o Coração não tem porta — mas o caminho é DITO.
        lines.append(t(lang, "fpd_not_diverged",
                       threshold=abs(int(st.get("threshold") or 500))))

    if st.get("faced"):
        lines.append("")
        lines.append(t(lang, "fpd_faced_note"))

    kb = InlineKeyboardMarkup(buttons) if buttons else None
    return "\n".join(lines), kb


@safe_handler
@rate_limit(1)
async def coracao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language or "pt")
        text, kb = await _render_state(session, player, lang)
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(
                text, parse_mode="Markdown", reply_markup=kb)
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.warning("coracao edit failed: %s", e)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def _safe_edit(query, text: str, kb) -> None:
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


async def forbidden_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `fpd_*` callbacks (TEC-5). Returns True if handled.

    TODO `fpd_*` responde e retorna True — um sub-callback desconhecido nunca
    cai no router genérico (botão girando = violação Lei §1)."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("fpd_"):
        return False
    data = query.data

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            await safe_answer(query)
            return True
        lang = normalize_lang(player.language or "pt")

        from core.forbidden_path_engine import forbidden_on
        if not forbidden_on():
            await safe_answer(query, t(lang, "fpd_locked_msg"), show_alert=True)
            return True

        if data == "fpd_menu":
            await safe_answer(query)
            text, kb = await _render_state(session, player, lang)
            await _safe_edit(query, text, kb)
            return True

        # ── abrir o Rito (auto-play, espelho do lib_rite_ do TEC-3) ──
        if data == "fpd_start":
            from core.forbidden_path_engine import start_heart_demon_rite
            res = await start_heart_demon_rite(session, int(player.telegram_id))
            if not res.get("ok"):
                reason = res.get("reason") or ""
                if reason == "rite_cooldown":
                    msg = t(lang, "fpd_err_cooldown",
                            hours=_hours_until(res.get("cooldown_ms") or 0))
                elif reason == "not_diverged":
                    msg = t(lang, "fpd_err_not_diverged")
                elif reason == "choice_pending":
                    msg = t(lang, "fpd_err_choice_pending")
                elif reason == "duel_already_active":
                    msg = t(lang, "fpd_err_busy")
                elif reason == "hp_depleted":
                    msg = t(lang, "fpd_err_hp")
                else:
                    msg = t(lang, "fpd_stale")
                await safe_answer(query, msg, show_alert=True)
                return True

            await safe_answer(query, t(lang, "fpd_rite_toast"), show_alert=False)
            from sqlalchemy import select as _select

            from database.models import DuelSession
            duel = (await session.execute(
                _select(DuelSession).where(DuelSession.id == res["duel_id"])
            )).scalar_one_or_none()
            if duel is None:
                await _safe_edit(query, t(lang, "fpd_stale"), None)
                return True
            try:
                from core.duel_engine import apply_post_duel_effects
                from core.sect_trial_engine import auto_play_trial_duel
                await auto_play_trial_duel(session, duel, int(player.telegram_id))
                await apply_post_duel_effects(session, duel)
            except Exception:
                logger.exception("heart demon auto-play failed (player_id=%s)",
                                 player.telegram_id)
                await session.rollback()
                await _safe_edit(query, t(lang, "fpd_stale"), None)
                return True
            won = (duel.winner_id == player.telegram_id and duel.state == "finished")
            rounds = int(duel.round_idx or 1)
            # A mordida da derrota (soul_strength) é lida do payload do settle
            # ANTES do commit — o chat não tem poll (convenção v16.4b).
            lost_soul = 0
            cost_line = ""
            for entry in reversed(duel.action_log or []):
                if isinstance(entry, dict) and entry.get("type") == "pve_settled":
                    _pay = entry.get("payload") or {}
                    lost_soul = int(_pay.get("soul_lost") or 0)
                    if _pay.get("forbidden_cost"):
                        cost_line = forbidden_cost_line(lang, _pay["forbidden_cost"])
                    break
            await session.commit()
            await session.refresh(player)

            head = t(lang, "fpd_rite_won" if won else "fpd_rite_lost", rounds=rounds)
            if not won and lost_soul:
                head += "\n" + t(lang, "fpd_rite_soul_lost", soul=lost_soul)
            if cost_line:
                head += "\n" + cost_line
            text, kb = await _render_state(session, player, lang)
            await _safe_edit(query, head + "\n\n" + text, kb)
            return True

        # ── a escolha: confirm 2-tap com a consequência DITA ──
        if data in ("fpd_cross", "fpd_stand"):
            from core.forbidden_path_engine import (
                diverged_target_path, heart_demon_state, sect_cross_preview,
            )
            st = await heart_demon_state(session, player)
            if not st.get("pending_choice_duel_id"):
                await safe_answer(query, t(lang, "fpd_stale"), show_alert=True)
                return True
            await safe_answer(query)
            if data == "fpd_cross" and not st.get("target_path"):
                await safe_answer(query, t(lang, "fpd_stale"), show_alert=True)
                return True
            if data == "fpd_stand":
                lines = [t(lang, "fpd_confirm_stand")]
                cb = "fpd_do_stand"
            else:
                target = diverged_target_path(
                    getattr(player, "path", None), int(getattr(player, "karma", 0) or 0))
                lines = [t(lang, "fpd_confirm_cross",
                           before=_path_label(lang, getattr(player, "path", None)),
                           after=_path_label(lang, target))]
                cost = await sect_cross_preview(session, player)
                if cost:
                    lines.append("")
                    lines.append(t(lang, "fpd_confirm_sect",
                                   karma=abs(int(cost.get("karma_cost") or 0))))
                cb = "fpd_do_cross"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "fpd_btn_confirm"), callback_data=cb)],
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="fpd_menu")],
            ])
            await _safe_edit(query, "\n".join(lines), kb)
            return True

        if data in ("fpd_do_cross", "fpd_do_stand"):
            from core.forbidden_path_engine import choose_heart_demon
            choice = "cross" if data == "fpd_do_cross" else "stand"
            res = await choose_heart_demon(session, int(player.telegram_id), choice)
            if not res.get("ok"):
                await safe_answer(query, t(lang, "fpd_stale"), show_alert=True)
                return True
            await session.commit()
            await session.refresh(player)
            await safe_answer(query, t(lang, "fpd_choice_toast"), show_alert=False)
            if choice == "stand":
                head = t(lang, "fpd_stood",
                         path=_path_label(lang, res.get("path_before")))
            else:
                head = t(lang, "fpd_crossed",
                         before=_path_label(lang, res.get("path_before")),
                         after=_path_label(lang, res.get("path_after")))
                sect = res.get("sect") or {}
                if sect.get("left"):
                    head += "\n" + t(lang, "fpd_crossed_sect_left")
                    # As artes que a redenção TRANCA são NOMEADAS: é o momento
                    # em que ele perde o mais caro do jogo (Lei §1).
                    _names = ", ".join(
                        f"{a.get('emoji', '')} {a.get('name', '')}".strip()
                        for a in (sect.get("locked") or []))
                    if _names:
                        head += "\n" + t(lang, "fpd_crossed_sect_locked", arts=_names)
                if res.get("xueye"):
                    head += "\n" + t(lang, "fpd_xueye_woke")
            text, kb = await _render_state(session, player, lang)
            await _safe_edit(query, head + "\n\n" + text, kb)
            return True

        # Sub-callback fpd_ desconhecido: responde e MORRE aqui (lição MV-2).
        await safe_answer(query)
        return True
