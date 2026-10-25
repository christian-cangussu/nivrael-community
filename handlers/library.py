"""TEC-1 — /biblioteca: as estantes da Biblioteca da Seita no chat.

Superfície LEVE (a canônica é o mini — SectHallModal → seção 📚): mostra as
estantes da casa (Externa/Interna/Núcleo + seladas), estado honesto por arte
(aprendida / grátis / custo em contribuição / trancada com o porquê) e o
learn das artes NOVAS com confirm antes→depois do loadout (Lei §10). As artes
legadas v16.4c continuam aprendendo pelo Salão (`/seita_cultivo` → 📚) — um
caminho por lógica.

Prefixo de callback `lib_` (registrado no combined_button_router ANTES de
qualquer botão emitir — lição MV-2). UM answer por callback (lição A Volta):
no caminho stale/erro o ALERTA é a resposta. Gated `biblioteca_seitas`
(OFF → mensagem honesta, Lei §1 — main nunca emite botões lib_)."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core.i18n import t
from core.utils import (_ensure_player, normalize_lang, rate_limit,
                        safe_answer, safe_handler)
from database.db import get_session_factory

logger = logging.getLogger(__name__)

_BLOCK_KEYS = {
    "rank": "lib_block_rank",
    "realm": "lib_block_realm",
    "quest": "lib_block_quest",
    "cp": "lib_block_cp",
    # TEC-3 — os dois bloqueios novos da Estante Oculta. Lição QoL-relatos §0.0.3:
    # um enum novo tem de entrar em TODO mapa `.get()`, senão o jogador lê o
    # motivo ERRADO (aqui o fallback silencioso era "exige posto").
    "karma": "sel_block_karma",
    "rite": "sel_block_rite",
    # TEC-5 — os três do Cofre Proibido (mesma lição: sem estas linhas o
    # jogador leria "exige posto Herdeiro" quando o que falta é o CAMINHO).
    "path": "fpd_block_path",
    "fp_karma": "fpd_block_karma",
    "hd_rite": "fpd_block_rite",
}


def _hours_until(ms: int) -> int:
    """Horas (arredondadas para cima, piso 1) até um timestamp em ms — o número
    que o cooldown DIZ. Nunca levanta."""
    try:
        from datetime import datetime, timezone
        delta = int(ms) / 1000.0 - datetime.now(timezone.utc).timestamp()
        return max(1, int(-(-delta // 3600)))
    except Exception:
        return 1


def _art_line(art: dict, lang: str) -> str:
    if art["learned"]:
        state = t(lang, "lib_state_learned")
    elif art["can_learn"]:
        state = (t(lang, "lib_state_free") if art["cost"] <= 0
                 else t(lang, "lib_state_cost", cost=art["cost"]))
    else:
        key = _BLOCK_KEYS.get(art.get("block") or "", "lib_block_rank")
        state = "🔒 " + t(lang, key, rank=t(lang, art["min_rank_key"]),
                          realm=art["req_realm"], cost=art["cost"],
                          have=art.get("karma_have", 0),
                          need=art.get("karma_need", 0))
    return f"{art['emoji']} *{art['name']}* — {state}"


def _render_shelves(view: dict, lang: str) -> tuple[str, InlineKeyboardMarkup | None]:
    lines = [f"📚 *{t(lang, 'lib_title')}*", ""]
    buttons: list[list[InlineKeyboardButton]] = []
    for shelf in view.get("shelves", []):
        gate = "" if shelf["rank_ok"] else " 🔒"
        lines.append(f"*{shelf['label']}*{gate} · {t(lang, shelf['min_rank_key'])}")
        # TEC-3 — o caminho QUANTIFICADO (Lei §1): "faltam N de contribuição".
        gap = shelf.get("rank_gap")
        if gap:
            if gap.get("contribution") and gap.get("realm"):
                lines.append(t(lang, "sel_gap_both", cp=gap["contribution"],
                               realm=gap["realm"]))
            elif gap.get("contribution"):
                lines.append(t(lang, "sel_gap_cp", cp=gap["contribution"]))
            elif gap.get("realm"):
                lines.append(t(lang, "sel_gap_realm", realm=gap["realm"]))
        for art in shelf.get("arts", []):
            lines.append(_art_line(art, lang))
            # TEC-5 — o custo DITO na vitrine: karma e anos por uso, e o aviso
            # de que a arte só desperta em duelo verdadeiro (Lei §1 — custo
            # invisível = custo nenhum). Key condicional: só artes do Cofre.
            if art.get("forbidden"):
                vault = view.get("forbidden_vault") or {}
                if vault.get("immortal"):
                    lines.append(t(lang, "fpd_art_cost_immortal",
                                   karma=int(vault.get("karma_cost") or 20)))
                else:
                    lines.append(t(lang, "fpd_art_cost",
                                   karma=int(vault.get("karma_cost") or 20),
                                   years=int(vault.get("years_per_use") or 0),
                                   uses=int(vault.get("uses_left") or 0)))
                lines.append(t(lang, "fpd_art_duel_only"))
            if art["can_learn"] and not art["legacy"]:
                label = f"{art['emoji']} {art['name']}"
                if art["cost"] > 0:
                    label += f" · {art['cost']} 🏯"
                buttons.append([InlineKeyboardButton(
                    label, callback_data=f"lib_learn_{art['tech_id']}")])
            # TEC-3 — a Prova da Sucessão: o único caminho para a Oculta. O
            # botão só aparece quando o rito É o que falta (karma já passou).
            elif art.get("block") == "rite":
                buttons.append([InlineKeyboardButton(
                    t(lang, "sel_btn_rite", name=art["name"]),
                    callback_data=f"lib_rite_{art['tech_id']}")])
        lines.append("")
    for s in view.get("sealed", []):
        lines.append(f"*{s['label']}* · {t(lang, s['min_rank_key'])}")
        if s.get("art"):
            lines.append(_art_line(s["art"], lang))
        lines.append(f"🔒 _{s['teaser']}_")
        lines.append("")
    lines.append(t(lang, "lib_balance_line", balance=view.get("merit_balance", 0)))
    if not view.get("quest_done"):
        lines.append(t(lang, "lib_quest_hint"))
    # TEC-3 — a Prova está de castigo? DIZER (Lei §1: nunca botão morto).
    rite = view.get("rite") or {}
    if rite.get("cooldown_ms"):
        lines.append(t(lang, "sel_rite_cooldown",
                       hours=_hours_until(rite["cooldown_ms"])))
    lines.append("")
    lines.append(t(lang, "lib_legacy_hint"))
    # TEC-2 — o elo: o grind de masmorra vira mérito da casa. Gated (OFF ⇒ a
    # tela do TEC-1 rende byte-idêntica).
    try:
        from core.scroll_economy_engine import escassez_on
        if escassez_on():
            lines.append(t(lang, "scr_library_hint"))
            buttons.append([InlineKeyboardButton(
                t(lang, "scr_library_btn"), callback_data="scr_open_lib")])
    except Exception:
        logger.debug("scroll donation hint failed", exc_info=True)
    kb = InlineKeyboardMarkup(buttons) if buttons else None
    return "\n".join(lines), kb


async def _render_for(session, player, lang: str) -> tuple[str, InlineKeyboardMarkup | None]:
    from core.sect_library_engine import biblioteca_on, get_library_shelves
    if not biblioteca_on():
        return t(lang, "lib_locked_msg"), None
    view = await get_library_shelves(session, int(player.telegram_id), lang)
    if not view.get("on"):
        return t(lang, "lib_locked_msg"), None
    if not view.get("in_sect"):
        return t(lang, "lib_no_sect_msg"), None
    return _render_shelves(view, lang)


@safe_handler
@rate_limit(1)
async def biblioteca_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language or "pt")
        text, kb = await _render_for(session, player, lang)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


def _loadout_names(loadout: list[dict]) -> str:
    return ", ".join(f"{x['emoji']} {x['name']}" for x in loadout) or "—"


async def _safe_edit(query, text: str, kb) -> None:
    """edit_text tolerante a double-tap (review TEC-1 F10 — 'Message is not
    modified' nunca vira exceção visível; padrão handlers/sect.py)."""
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


async def library_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Route `lib_*` callbacks (TEC-1). Returns True if handled.

    TODO lib_* responde e retorna True — um sub-callback desconhecido nunca
    cai no button_router genérico (botão girando = violação Lei §1)."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("lib_"):
        return False
    data = query.data

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            await safe_answer(query)
            return True
        lang = normalize_lang(player.language or "pt")

        from core.sect_library_engine import (biblioteca_on,
                                              get_library_shelves,
                                              learn_library_technique)
        if not biblioteca_on():
            await safe_answer(query, t(lang, "lib_locked_msg"), show_alert=True)
            return True

        # ── voltar / re-render das estantes ──
        if data == "lib_menu":
            await safe_answer(query)
            text, kb = await _render_for(session, player, lang)
            await _safe_edit(query, text, kb)
            return True

        # ── confirm de aprender (antes→depois do loadout, Lei §10) ──
        if data.startswith("lib_learn_"):
            try:
                tech_id = int(data[len("lib_learn_"):])
            except ValueError:
                await safe_answer(query)
                return True
            view = await get_library_shelves(session, int(player.telegram_id), lang)
            art = next(
                (a for s in view.get("shelves", []) for a in s.get("arts", [])
                 if a["tech_id"] == tech_id),
                None,
            )
            if art is None or art["learned"] or not art["can_learn"] or art["legacy"]:
                # Stale (outro clique ganhou / posto mudou) — o alerta É a resposta.
                await safe_answer(query, t(lang, "lib_stale"), show_alert=True)
                return True
            await safe_answer(query)
            loadout = view.get("loadout", [])
            lines = [
                f"{art['emoji']} *{art['name']}*", "",
                art["desc"], "",
            ]
            if art["cost"] > 0:
                lines.append(t(lang, "lib_confirm_cost", cost=art["cost"],
                               balance=view.get("merit_balance", 0)))
            else:
                lines.append(t(lang, "lib_confirm_free"))
            lines.append("")
            lines.append(t(lang, "lib_loadout_before", techs=_loadout_names(loadout)))
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "lib_btn_confirm"),
                                      callback_data=f"lib_conf_{tech_id}")],
                [InlineKeyboardButton(t(lang, "btn_back"), callback_data="lib_menu")],
            ])
            await _safe_edit(query, "\n".join(lines), kb)
            return True

        # ── executar o learn (row-locked no engine; commit só em ok) ──
        if data.startswith("lib_conf_"):
            try:
                tech_id = int(data[len("lib_conf_"):])
            except ValueError:
                await safe_answer(query)
                return True
            result = await learn_library_technique(
                session, int(player.telegram_id), tech_id)
            if not result.get("ok"):
                reason = result.get("reason") or ""
                if reason == "insufficient_merit":
                    msg = t(lang, "lib_err_cp", cost=result.get("cost", 0),
                            balance=result.get("balance", 0))
                elif reason == "quest_required":
                    msg = t(lang, "lib_err_quest")
                elif reason == "rank_too_low":
                    msg = t(lang, "lib_err_rank",
                            rank=t(lang, result.get("req_rank_key", "wsect_rank_core")))
                elif reason == "already_learned":
                    msg = t(lang, "lib_err_learned")
                # TEC-5 — as 3 recusas do Cofre. Sem estas linhas o jogador que
                # perdesse o gate ENTRE a vitrine e o confirm lia "este momento
                # já passou" em vez de saber QUAL porta fechou (Lei §1).
                elif reason == "path_required":
                    msg = t(lang, "fpd_err_path")
                elif reason == "fp_karma_too_low":
                    msg = t(lang, "fpd_err_karma", have=result.get("karma_have", 0),
                            need=result.get("karma_need", 0))
                elif reason == "hd_rite_required":
                    msg = t(lang, "fpd_err_rite")
                else:
                    msg = t(lang, "lib_stale")
                await safe_answer(query, msg, show_alert=True)
                return True
            await session.commit()
            await safe_answer(query, t(lang, "lib_learned_toast"), show_alert=False)
            after = _loadout_names(result.get("loadout_after", []))
            before = _loadout_names(result.get("loadout_before", []))
            lines = [
                t(lang, "lib_learned_header", emoji=result["emoji"], name=result["name"]),
                "",
            ]
            if result.get("cp_spent"):
                lines.append(t(lang, "lib_learned_cost",
                               cost=result["cp_spent"],
                               balance=result.get("merit_balance", 0)))
            lines.append(t(lang, "lib_loadout_before", techs=before))
            lines.append(t(lang, "lib_loadout_after", techs=after))
            if not result.get("auto_equipped"):
                lines.append("")
                lines.append(t(lang, "lib_slots_full_note"))
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(t(lang, "btn_back"), callback_data="lib_menu"),
            ]])
            await _safe_edit(query, "\n".join(lines), kb)
            return True

        # ── TEC-3: a Prova da Sucessão 秘传 (auto-play, espelho do rito v16.4b)
        if data.startswith("lib_rite_"):
            try:
                tech_id = int(data[len("lib_rite_"):])
            except ValueError:
                await safe_answer(query)
                return True
            from core.sect_library_engine import selado_on, start_hidden_rite
            if not selado_on():
                await safe_answer(query, t(lang, "lib_stale"), show_alert=True)
                return True
            res = await start_hidden_rite(session, int(player.telegram_id), tech_id)
            if not res.get("ok"):
                reason = res.get("reason") or ""
                if reason == "rite_cooldown":
                    msg = t(lang, "sel_err_cooldown",
                            hours=_hours_until(res.get("cooldown_ms") or 0))
                elif reason == "karma_too_low":
                    msg = t(lang, "sel_err_karma", have=res.get("karma_have", 0),
                            need=res.get("karma_need", 0))
                elif reason == "rank_too_low":
                    msg = t(lang, "lib_err_rank",
                            rank=t(lang, res.get("req_rank_key", "wsect_rank_heir")))
                elif reason == "duel_already_active":
                    msg = t(lang, "sel_err_busy")
                elif reason == "hp_depleted":
                    msg = t(lang, "sel_err_hp")
                elif reason in ("already_learned", "rite_already_passed"):
                    msg = t(lang, "lib_err_learned")
                else:
                    msg = t(lang, "lib_stale")
                await safe_answer(query, msg, show_alert=True)
                return True

            await safe_answer(query, t(lang, "sel_rite_toast"), show_alert=False)
            # Auto-play: a MESMA função do rito de entrada (uma verdade do
            # "o chat resolve o duelo sozinho"), e depois o settle INLINE —
            # o chat não tem poll, então quem liquida somos nós (lição v16.4b).
            from sqlalchemy import select as _select

            from database.models import DuelSession
            duel = (await session.execute(
                _select(DuelSession).where(DuelSession.id == res["duel_id"])
            )).scalar_one_or_none()
            if duel is None:
                await _safe_edit(query, t(lang, "lib_stale"), None)
                return True
            try:
                from core.duel_engine import apply_post_duel_effects
                from core.sect_trial_engine import auto_play_trial_duel
                await auto_play_trial_duel(session, duel, int(player.telegram_id))
                await apply_post_duel_effects(session, duel)
            except Exception:
                logger.exception("hidden rite auto-play failed (player_id=%s)",
                                 player.telegram_id)
                await session.rollback()
                await _safe_edit(query, t(lang, "lib_stale"), None)
                return True
            won = (duel.winner_id == player.telegram_id and duel.state == "finished")
            rounds = int(duel.round_idx or 1)
            await session.commit()

            head = t(lang, "sel_rite_won" if won else "sel_rite_lost", rounds=rounds)
            text, kb = await _render_for(session, player, lang)
            await _safe_edit(query, head + "\n\n" + text, kb)
            return True

        # Sub-callback lib_ desconhecido: responde e MORRE aqui (lição MV-2).
        await safe_answer(query)
        return True
