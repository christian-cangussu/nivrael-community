import asyncio
import uuid as _uuid
import logging
import random
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, desc
from sqlalchemy.orm.attributes import flag_modified
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import REALM_NAMES, TRIBULATION_WINDOW_HOURS
from database.db import get_session_factory
from database.models import (
    Player, Tribulation, PlayerArtifact,
    PlayerInventory, TechniqueCatalog, PlayerTechnique,
    PlayerDaoFragment, DaoLawCatalog,
)
from core.game_logic import format_number, calculate_total_stats, get_player_equipment_stats
from core.tribulation_engine import (
    calculate_rounds,
    get_tribulation_power,
    simulate_round,
    determine_outcome,
    estimate_success_chance,
    STRATEGIES,
    TRIBULATION_PASSED_OUTCOMES,
    get_next_phase,
    get_required_phases,
    build_phases_display,
    get_heart_demon_correct_answers,
    get_heart_demon_state,
    set_heart_demon_state,
    mark_heart_demon_done,
    can_see_third_option,
    calculate_dao_chance,
    HD_QUESTIONS,
)
from core.i18n import t
from core.utils import escape_markdown, safe_handler, rate_limit, safe_answer, add_item_to_inventory, normalize_lang, resolve_chat_player_id

logger = logging.getLogger(__name__)

RARE_SCROLL_IDS = [2, 3, 5]
PERFECT_SCROLL_CHANCE = 0.30

# HD_QUESTIONS moved to core/tribulation_engine.py in v15.1.3.h2 — single
# source of truth for both chat + mini-app backends.

# Display labels for dominant Dao elements (used in Heart Demon tutorial screen)
HD_ELEMENT_LABELS = {
    "Lightning": {"pt": "⚡ Relâmpago", "en": "⚡ Lightning", "es": "⚡ Relámpago"},
    "Fire":      {"pt": "🔥 Fogo",      "en": "🔥 Fire",      "es": "🔥 Fuego"},
    "Wood":      {"pt": "🌿 Madeira",   "en": "🌿 Wood",      "es": "🌿 Madera"},
    "Chaos":     {"pt": "☯️ Caos",      "en": "☯️ Chaos",     "es": "☯️ Caos"},
    "Earth":     {"pt": "🪨 Terra",     "en": "🪨 Earth",     "es": "🪨 Tierra"},
}


async def _maybe_award_tribulation_scroll(session, player_id: int) -> str | None:
    if random.random() > PERFECT_SCROLL_CHANCE:
        return None

    learned_stmt = select(PlayerTechnique.technique_id).where(
        PlayerTechnique.player_id == player_id
    )
    learned_ids = set((await session.execute(learned_stmt)).scalars().all())

    owned_stmt = select(PlayerInventory.item_id).where(
        PlayerInventory.player_id == player_id,
        PlayerInventory.item_type == "technique_scroll",
        PlayerInventory.quantity > 0,
    )
    owned_ids = set((await session.execute(owned_stmt)).scalars().all())

    rare_techs = (await session.execute(
        select(TechniqueCatalog).where(TechniqueCatalog.id.in_(RARE_SCROLL_IDS))
    )).scalars().all()

    candidates = [tech for tech in rare_techs if tech.id not in learned_ids and tech.id not in owned_ids]
    if not candidates:
        return None

    chosen = random.choice(candidates)

    added = await add_item_to_inventory(session, player_id, "technique_scroll", chosen.id)
    if not added:
        return None

    return f"{chosen.emoji} {chosen.name}"


@safe_handler
@rate_limit(1)
async def tribulacao_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    user_id = update.effective_user.id
    async with get_session_factory()() as session:
        _pl = (await session.execute(select(Player).where(Player.telegram_id == user_id))).scalar_one_or_none()
        if _pl:
            lang = normalize_lang(_pl.language)

        stmt = select(Tribulation).where(
            Tribulation.player_id == user_id,
            Tribulation.status.in_(["pending", "in_progress"])
        ).order_by(desc(Tribulation.started_at))

        active_tribs = (await session.execute(stmt)).scalars().all()
        trib = active_tribs[0] if active_tribs else None

        # COMPAT: beta/live data may contain duplicated active tribulations.
        # Keep only the latest active record and expire older duplicates.
        if len(active_tribs) > 1:
            now = datetime.now(timezone.utc)
            for extra in active_tribs[1:]:
                extra.status = "expired"
                extra.completed_at = now
            logger.warning(
                "Tribulation dedupe for player %s: kept=%s expired=%d",
                user_id, trib.id if trib else None, len(active_tribs) - 1
            )
            await session.commit()

        if not trib:
            if update.callback_query:
                await update.callback_query.message.edit_text(t(lang, "trib_no_pending"))
                await safe_answer(update.callback_query)
            else:
                await update.message.reply_text(t(lang, "trib_no_pending"))
            return

        if trib.realm >= len(REALM_NAMES):
            trib.status = "completed"
            await session.commit()
            msg = t(lang, "trib_max_realm")
            if update.callback_query:
                await update.callback_query.message.edit_text(msg)
                await safe_answer(update.callback_query)
            else:
                await update.message.reply_text(msg)
            return

        if trib.status == "pending":
            await _show_announcement(update, trib)
        elif trib.status == "in_progress":
            await _show_next_phase(update, trib)


async def _show_announcement(update: Update, trib: Tribulation):
    from core.visual_engine import tribulation_thunder_art
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))

    async with get_session_factory()() as _sess:
        player = (await _sess.execute(
            select(Player).where(Player.telegram_id == trib.player_id)
        )).scalar_one_or_none()
        if player:
            lang = normalize_lang(player.language)

        target_realm_idx = min(trib.realm, len(REALM_NAMES) - 1)
        target_realm = REALM_NAMES[target_realm_idx]
        expires_at = trib.started_at + timedelta(hours=TRIBULATION_WINDOW_HOURS)
        remaining = expires_at - datetime.now(timezone.utc)

        art = tribulation_thunder_art(lang=lang)
        announcement = t(lang, "trib_announcement", target_realm=target_realm,
                         expires_at=expires_at.strftime('%H:%M %d/%m'),
                         remaining=str(remaining).split('.')[0])

        # Q-13: Pre-attempt preview — phases, stats, est. chance, active
        # talismans and fail cost. The cultivator "reads the heavens" before
        # accepting the trial. Player still chooses strategy after Iniciar.
        preview = await _build_trib_preview(_sess, player, trib, target_realm_idx, lang)

    text = f"{art}\n\n{announcement}"
    if preview:
        text += "\n\n" + preview

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_trib_start"), callback_data=f"trib_start_{trib.id}")],
        [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")]
    ])

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def _build_trib_preview(session, player, trib: Tribulation, target_realm: int, lang: str) -> str:
    if player is None:
        return ""

    sections: list[str] = []

    phases_display = build_phases_display(trib.phases_completed or [], target_realm, lang)
    sections.append(t(lang, "trib_preview_phases_header", phases=phases_display))

    try:
        stmt_arts = select(PlayerArtifact).where(
            PlayerArtifact.player_id == player.telegram_id,
            PlayerArtifact.is_equipped == True,
        )
        arts = (await session.execute(stmt_arts)).scalars().all()
        equip_stats = get_player_equipment_stats(arts)
        stats = calculate_total_stats(player, equip_stats)
        sections.append(t(
            lang, "trib_preview_stats_line",
            soul=format_number(stats['soul_strength']),
            bp=format_number(stats['total_battle_power']),
            perception=format_number(stats.get('perception', player.perception)),
        ))

        rounds_total = calculate_rounds(target_realm - 1)
        # TEC-5 — o peso kármico endurece os céus (flag `forbidden_path`; sem ela
        # o multiplicador é 1.0). MESMO valor na previsão e na rolagem.
        trib_power = get_tribulation_power(target_realm - 1, int(player.karma or 0))

        from core.sect_engine import get_sect_bonuses
        sect_bonuses = await get_sect_bonuses(session, player.telegram_id)
        defense_mult = sect_bonuses.get("defense_mult", 0.0)

        from core.body_tempering_engine import get_celestial_body_bonuses
        body_bonuses = get_celestial_body_bonuses(getattr(player, "body_tempering_level", 0) or 0)
        defense_mult += body_bonuses.get("trib_survival_bonus", 0.0)

        chance_resist = estimate_success_chance(stats['soul_strength'], trib_power, "resist", rounds_total, defense_mult=defense_mult)
        chance_dodge = estimate_success_chance(stats['soul_strength'], trib_power, "dodge", rounds_total, defense_mult=defense_mult)
        chance_absorb = estimate_success_chance(stats['soul_strength'], trib_power, "absorb", rounds_total, defense_mult=defense_mult)
        sections.append(t(
            lang, "trib_preview_chances_thunder",
            resist=chance_resist, dodge=chance_dodge, absorb=chance_absorb,
        ))
        # MV-11 天时 — O TEMPO DO CÉU, ao lado das 3 chances que ele acabou de
        # mover (Lei §10: antes→depois) e com o PRÓXIMO céu escrito (o único
        # futuro que este jogo sabe dizer). `trib_power` JÁ vem multiplicado
        # pelo céu — o "antes" é derivado por divisão DENTRO do engine, nunca
        # por uma segunda chamada ao chokepoint (uma segunda chamada podia cair
        # do outro lado da fronteira do epoch e imprimir um antes→depois que
        # nunca existiu). try PRÓPRIO: o bloco inteiro acima vive num
        # `except Exception` que só loga, e uma falha aqui apagaria em silêncio
        # a secção "Trunfos + Trovão" inteira (Lei §1 — dead-end).
        try:
            from core.tianshi_engine import sky_view
            _sky = sky_view(lang, soul=stats['soul_strength'], power=trib_power,
                            rounds=rounds_total, defense_mult=defense_mult)
            if _sky:
                sections.append(_sky["line"] + "\n" + _sky["next"]["line"])
        except Exception:
            logger.exception("trib_preview: tianshi block failed")
    except Exception:
        logger.exception("trib_preview: stats/thunder block failed for player %s", getattr(player, "telegram_id", None))

    if "dao" in get_required_phases(target_realm):
        try:
            stmt_frags = select(PlayerDaoFragment).where(
                PlayerDaoFragment.player_id == player.telegram_id
            )
            fragment_rows = (await session.execute(stmt_frags)).scalars().all()
            fragments_by_law = [
                {"fragments_count": f.fragments_count,
                 "is_completed": f.is_completed,
                 "insight_level": f.insight_level}
                for f in fragment_rows
            ]
            trib_bonus = 0.0
            try:
                from core.dao_laws_engine import get_dao_laws_bonuses
                laws_b = await get_dao_laws_bonuses(session, player.telegram_id, player.realm)
                trib_bonus = laws_b.get("tribulation_bonus", 0.0)
            except Exception:
                pass
            dao_info = calculate_dao_chance(player, fragments_by_law, tribulation_bonus=trib_bonus)
            sections.append(t(
                lang, "trib_preview_chances_dao",
                chance=dao_info["chance"],
                frags=dao_info["total_fragments"],
                req=dao_info["required"],
            ))
        except Exception:
            logger.exception("trib_preview: dao chance block failed for player %s", getattr(player, "telegram_id", None))

    try:
        from database.models import PlayerBuff
        now_utc = datetime.now(timezone.utc)
        stmt_buffs = select(PlayerBuff).where(
            PlayerBuff.player_id == player.telegram_id,
            PlayerBuff.expires_at > now_utc,
            PlayerBuff.buff_type.in_(["trib_insurance", "trib_blessing", "revive"]),
        )
        active_buffs = (await session.execute(stmt_buffs)).scalars().all()
        if active_buffs:
            buff_lines = [t(lang, "trib_preview_buffs_header")]
            seen: set[str] = set()
            for b in active_buffs:
                if b.buff_type in seen:
                    continue
                seen.add(b.buff_type)
                if b.buff_type == "trib_insurance":
                    buff_lines.append(t(lang, "trib_preview_buff_insurance"))
                elif b.buff_type == "trib_blessing":
                    buff_lines.append(t(lang, "trib_preview_buff_blessing"))
                elif b.buff_type == "revive":
                    buff_lines.append(t(lang, "trib_preview_buff_revive"))
            sections.append("\n".join(buff_lines))
        else:
            sections.append(t(lang, "trib_preview_buffs_none"))
    except Exception:
        logger.exception("trib_preview: buffs block failed for player %s", getattr(player, "telegram_id", None))

    sections.append(t(lang, "trib_preview_fail_block"))

    return "\n\n".join(sections)


async def _show_next_phase(update: Update, trib: Tribulation, session=None):
    """Route to the correct phase UI based on what's already completed."""
    target_realm = min(trib.realm, len(REALM_NAMES) - 1)
    phases_completed = trib.phases_completed or []
    next_phase = get_next_phase(phases_completed, target_realm)

    if next_phase is None:
        # All phases done — grant realm advancement
        if session:
            await _grant_realm_advancement(update, trib, session)
        else:
            async with get_session_factory()() as new_session:
                trib_fresh = (await new_session.execute(
                    select(Tribulation).where(Tribulation.id == trib.id)
                )).scalar_one_or_none()
                if trib_fresh:
                    await _grant_realm_advancement(update, trib_fresh, new_session)
    elif next_phase == "thunder":
        await _show_preparation(update, trib, session)
    elif next_phase == "heart_demon":
        await _show_heart_demon_intro(update, trib, session)
    elif next_phase == "dao":
        await _show_dao_trial(update, trib, session)


@safe_handler
@rate_limit(1)
async def trib_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    async with get_session_factory()() as session:
        _pl = (await session.execute(select(Player).where(Player.telegram_id == user_id))).scalar_one_or_none()
        if _pl:
            lang = normalize_lang(_pl.language)

        if data.startswith("trib_start_"):
            raw_id = data.replace("trib_start_", "")
            try:
                trib_id = _uuid.UUID(raw_id)
            except (ValueError, AttributeError):
                await safe_answer(query)
                return
            stmt = select(Tribulation).where(Tribulation.id == trib_id, Tribulation.player_id == user_id)
            trib = (await session.execute(stmt)).scalar_one_or_none()
            if trib and trib.status == "pending":
                trib.status = "in_progress"
                await session.commit()
                await _show_next_phase(update, trib, session)
            else:
                await safe_answer(query, t(lang, "ans_esta_tribulação_não_está"))

        elif data.startswith("trib_strat_"):
            parts = data.split("_")
            if len(parts) < 4:
                await safe_answer(query)
                return
            strategy = parts[2]
            try:
                trib_id = _uuid.UUID(parts[3])
            except (ValueError, AttributeError):
                await safe_answer(query)
                return

            stmt = select(Tribulation).where(Tribulation.id == trib_id, Tribulation.player_id == user_id)
            trib = (await session.execute(stmt)).scalar_one_or_none()

            if trib and trib.status == "in_progress":
                trib.strategy = strategy
                await session.commit()
                await _run_thunder_phase(update, trib, session, context)
            else:
                await safe_answer(query, t(lang, "ans_erro_ao_selecionar_estratégia"))

        elif data.startswith("trib_hd_begin_"):
            # trib_hd_begin_{trib_id} — dismiss tutorial, show first question
            raw_id = data.replace("trib_hd_begin_", "")
            try:
                trib_id = _uuid.UUID(raw_id)
            except (ValueError, AttributeError):
                await safe_answer(query)
                return

            stmt = select(Tribulation).where(Tribulation.id == trib_id, Tribulation.player_id == user_id)
            trib = (await session.execute(stmt)).scalar_one_or_none()

            if trib and trib.status == "in_progress":
                phases = list(trib.phases_completed or [])
                hd_state = get_heart_demon_state(phases)
                if hd_state is None:
                    await safe_answer(query, t(lang, "ans_erro_estado_desconhecido"), show_alert=True)
                    return
                await safe_answer(query)
                _player = (await session.execute(
                    select(Player).where(Player.telegram_id == user_id)
                )).scalar_one_or_none()
                await _send_heart_demon_question(update, trib, _player, session, hd_state.get("q", 0))
            else:
                await safe_answer(query, t(lang, "ans_esta_tribulação_não_está"), show_alert=True)

        elif data.startswith("trib_hd_answer_"):
            # trib_hd_answer_{q_idx}_{opt}_{trib_id}
            parts = data.split("_")
            try:
                q_idx = int(parts[3])
                opt_idx = int(parts[4])
                trib_id = _uuid.UUID(parts[5])
            except (ValueError, AttributeError, IndexError):
                await safe_answer(query)
                return

            stmt = select(Tribulation).where(Tribulation.id == trib_id, Tribulation.player_id == user_id)
            trib = (await session.execute(stmt)).scalar_one_or_none()

            if trib and trib.status == "in_progress":
                phases = list(trib.phases_completed or [])
                hd_state = get_heart_demon_state(phases)
                if hd_state is None or hd_state.get("q", 0) != q_idx:
                    await safe_answer(query, t(lang, "ans_erro_estado_desconhecido"), show_alert=True)
                    return
                await _process_heart_demon_answer(update, trib, session, opt_idx)
            else:
                await safe_answer(query, t(lang, "ans_esta_tribulação_não_está"), show_alert=True)

        elif data.startswith("trib_dao_go_"):
            raw_id = data.replace("trib_dao_go_", "")
            try:
                trib_id = _uuid.UUID(raw_id)
            except (ValueError, AttributeError):
                await safe_answer(query)
                return

            stmt = select(Tribulation).where(Tribulation.id == trib_id, Tribulation.player_id == user_id)
            trib = (await session.execute(stmt)).scalar_one_or_none()

            if trib and trib.status == "in_progress":
                await _run_dao_phase(update, trib, session, context)
            else:
                await safe_answer(query, t(lang, "ans_esta_tribulação_não_está"), show_alert=True)

        elif data.startswith("trib_dao_flee_"):
            await safe_answer(query)
            await query.message.edit_text(
                t(lang, "trib_dao_retreat_msg"),
                parse_mode="Markdown"
            )


# ─── Thunder Phase ────────────────────────────────────────────────────────────

async def _show_preparation(update: Update, trib: Tribulation, session=None):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    user_id = update.effective_user.id

    close_session = False
    if session is None:
        session = get_session_factory()()
        close_session = True

    try:
        stmt = select(Player).where(Player.telegram_id == user_id)
        player = (await session.execute(stmt)).scalar_one_or_none()
        lang = normalize_lang(player.language)

        stmt_arts = select(PlayerArtifact).where(PlayerArtifact.player_id == user_id, PlayerArtifact.is_equipped == True)
        arts = (await session.execute(stmt_arts)).scalars().all()
        equip_stats = get_player_equipment_stats(arts)
        stats = calculate_total_stats(player, equip_stats)

        rounds = calculate_rounds(min(trib.realm, len(REALM_NAMES) - 1) - 1)
        # TEC-5 — severidade por |karma| (gated); previsão == rolagem.
        trib_power = get_tribulation_power(min(trib.realm, len(REALM_NAMES) - 1) - 1,
                                           int(player.karma or 0))
        target_name = REALM_NAMES[min(trib.realm, len(REALM_NAMES) - 1)]

        from core.sect_engine import get_sect_bonuses
        sect_bonuses = await get_sect_bonuses(session, player.telegram_id)
        defense_mult = sect_bonuses["defense_mult"]

        # F-11.5: Celestial Bones/Body (body tier 11+) adds +10% tribulation survival.
        from core.body_tempering_engine import get_celestial_body_bonuses
        body_bonuses = get_celestial_body_bonuses(getattr(player, "body_tempering_level", 0) or 0)
        defense_mult = defense_mult + body_bonuses.get("trib_survival_bonus", 0.0)

        chance_resist = estimate_success_chance(stats['soul_strength'], trib_power, "resist", rounds, defense_mult=defense_mult)
        chance_dodge = estimate_success_chance(stats['soul_strength'], trib_power, "dodge", rounds, defense_mult=defense_mult)
        chance_absorb = estimate_success_chance(stats['soul_strength'], trib_power, "absorb", rounds, defense_mult=defense_mult)

        # Show phase progress header
        target_realm = min(trib.realm, len(REALM_NAMES) - 1)
        phases_display = build_phases_display(trib.phases_completed or [], target_realm, lang)

        text = t(lang, "trib_thunder_title") + "\n"
        text += t(lang, "trib_phases_progress", phases=phases_display) + "\n\n"
        text += t(lang, "trib_prep_title", target_realm=target_name, soul=format_number(stats['soul_strength']), bp=format_number(stats['total_battle_power']), rounds=rounds)
        if defense_mult > 0:
            text += t(lang, "trib_prep_sect_bonus", discount=int(defense_mult*100), level=int(sect_bonuses['defense_mult']/0.05))

        text += t(lang, "trib_prep_strategy", resist=chance_resist, dodge=chance_dodge, absorb=chance_absorb)

        # MV-11 天时 — a SEGUNDA porta do chat, e a que importa: é AQUI que o
        # tap acontece (os 3 botões logo abaixo). O spec só nomeava a preview;
        # sem esta linha o céu movia o número dos botões sem nunca se explicar
        # — exatamente o "número mudou e ninguém disse porquê" que a régua §8
        # proíbe ("se mudar, tem de o DIZER antes do tap").
        try:
            from core.tianshi_engine import sky_view
            _sky = sky_view(lang, soul=stats['soul_strength'], power=trib_power,
                            rounds=rounds, defense_mult=defense_mult)
            if _sky:
                text += "\n" + _sky["line"] + "\n" + _sky["next"]["line"]
        except Exception:
            logger.exception("trib_prep: tianshi block failed")

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_trib_resist", chance=chance_resist), callback_data=f"trib_strat_resist_{trib.id}")],
            [InlineKeyboardButton(t(lang, "btn_trib_dodge", chance=chance_dodge), callback_data=f"trib_strat_dodge_{trib.id}")],
            [InlineKeyboardButton(t(lang, "btn_trib_absorb", chance=chance_absorb), callback_data=f"trib_strat_absorb_{trib.id}")]
        ])

        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    finally:
        if close_session:
            await session.close()


async def _run_thunder_phase(update: Update, trib: Tribulation, session, _context):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    user_id = update.effective_user.id
    trib_id = trib.id
    strategy = trib.strategy

    # --- Load all needed data from DB before the animation loop ---
    stmt = select(Player).where(Player.telegram_id == user_id)
    player = (await session.execute(stmt)).scalar_one_or_none()
    lang = normalize_lang(player.language)
    player_name = player.display_name

    stmt_arts = select(PlayerArtifact).where(PlayerArtifact.player_id == user_id, PlayerArtifact.is_equipped == True)
    arts = (await session.execute(stmt_arts)).scalars().all()
    equip_stats = get_player_equipment_stats(arts)
    stats = calculate_total_stats(player, equip_stats)

    target_realm = min(trib.realm, len(REALM_NAMES) - 1)
    rounds_total = calculate_rounds(target_realm - 1)
    # TEC-5 — severidade por |karma| (gated): a MESMA que a preview mostrou.
    trib_power = get_tribulation_power(target_realm - 1, int(player.karma or 0))
    from core.sect_engine import get_sect_bonuses
    sect_bonuses = await get_sect_bonuses(session, player.telegram_id)
    defense_mult = sect_bonuses["defense_mult"]

    # F-11.5: Celestial Bones/Body tempering adds +10% tribulation survival.
    from core.body_tempering_engine import get_celestial_body_bonuses
    _body_bonuses = get_celestial_body_bonuses(getattr(player, "body_tempering_level", 0) or 0)
    defense_mult = defense_mult + _body_bonuses.get("trib_survival_bonus", 0.0)

    # Check for Tribulation Blessing buff (+15% survival)
    from database.models import PlayerBuff
    from datetime import datetime as _dt, timezone as _tz
    _now = _dt.now(_tz.utc)
    _trib_bless = (await session.execute(
        select(PlayerBuff).where(
            PlayerBuff.player_id == user_id,
            PlayerBuff.buff_type == "trib_blessing",
            PlayerBuff.expires_at > _now
        )
    )).scalar_one_or_none()
    blessing_bonus = 0.0
    if _trib_bless:
        blessing_bonus = _trib_bless.buff_value  # 0.15
        await session.delete(_trib_bless)
        await session.commit()

    # --- Release the session before the long animation loop ---
    # The loop takes ~2.5s * rounds + 2s which can exceed idle_in_transaction_session_timeout
    await session.close()

    query = update.callback_query
    await query.message.edit_text(t(lang, "trib_started", name=escape_markdown(player_name)), parse_mode="Markdown")
    await asyncio.sleep(2)

    survived = 0
    for r in range(1, rounds_total + 1):
        round_res = await simulate_round(stats["soul_strength"], trib_power, strategy, defense_mult=defense_mult, blessing_bonus=blessing_bonus)
        msg = t(lang, "trib_round_title", round=r, total=rounds_total, msg=t(lang, round_res['message']))
        if round_res["success"]:
            msg += t(lang, "trib_round_survived", damage=format_number(round_res['damage']))
            survived += 1
            await query.message.edit_text(msg, parse_mode="Markdown")
        else:
            msg += t(lang, "trib_round_hit", damage=format_number(round_res['damage']))
            await query.message.edit_text(msg, parse_mode="Markdown")

        await asyncio.sleep(2.5)

    outcome = determine_outcome(strategy, survived, rounds_total)

    # --- Open a fresh session to persist results ---
    async with get_session_factory()() as new_session:
        trib = (await new_session.execute(
            select(Tribulation).where(Tribulation.id == trib_id)
        )).scalar_one_or_none()
        player = (await new_session.execute(
            select(Player).where(Player.telegram_id == user_id)
        )).scalar_one_or_none()

        if not trib or not player:
            await query.message.reply_text("⚠️ Error: tribulation data not found.")
            return

        trib.rounds_total = rounds_total
        trib.rounds_survived = survived

        if outcome in TRIBULATION_PASSED_OUTCOMES:
            # Mark thunder phase complete
            phases = list(trib.phases_completed or [])
            if "thunder" not in phases:
                phases.append("thunder")
            trib.phases_completed = phases
            flag_modified(trib, "phases_completed")

            strat = STRATEGIES[strategy]
            bp_bonus = strat["bp_bonus"]
            soul_bonus = strat["soul_bonus"]

            # Apply strategy bonuses to player now (partial reward)
            if bp_bonus > 0:
                player.battle_power = int(player.battle_power * (1 + bp_bonus))
            if soul_bonus > 0:
                player.soul_strength = int(player.soul_strength * (1 + soul_bonus))
            await new_session.commit()

            result_text = t(lang, "trib_phase_complete", phase=t(lang, "trib_thunder_title"))
            # Show next phase progress
            phases_display = build_phases_display(trib.phases_completed, target_realm, lang)
            result_text += "\n" + t(lang, "trib_phases_progress", phases=phases_display)

            if outcome == "perfect":
                result_text = t(lang, "trib_thunder_perfect") + "\n" + result_text

            await query.message.reply_text(result_text, parse_mode="Markdown")
            await asyncio.sleep(2)

            # Continue to next phase
            await _show_next_phase(update, trib, session=new_session)

        else:
            # Thunder failed → full failure with cooldown
            trib.outcome = outcome
            trib.status = "failed"
            trib.completed_at = datetime.now(timezone.utc)

            from config import get_threshold
            threshold = get_threshold(player.realm, player.sub_layer)

            from core.alchemy_engine import get_active_buffs
            _trib_buffs = await get_active_buffs(new_session, player.telegram_id)
            _revive_buff = next((b for b in _trib_buffs if b.buff_type == "revive"), None)

            # Check for Heavenly Shield Talisman (tribulation insurance)
            _insurance_buff = next((b for b in _trib_buffs if b.buff_type == "trib_insurance"), None)

            if _revive_buff:
                player.qi = int(player.qi_capacity * 0.5)
                await new_session.delete(_revive_buff)
                await new_session.flush()
                result_text = t(lang, "pill_revive_triggered")
            elif _insurance_buff:
                # Insurance: only lose 5% CB instead of 20%
                player.cultivation_base = threshold * 0.95
                await new_session.delete(_insurance_buff)
                await new_session.flush()
                result_text = t(lang, "trib_insurance_triggered")
            elif outcome == "failure_grave":
                player.cultivation_base = threshold * 0.50
                result_text = t(lang, "trib_failure_grave")
            else:
                player.cultivation_base = threshold * 0.80
                result_text = t(lang, "trib_failure_light")

            # Track A item 4 — Karma: a failed trial breeds resentment (-10).
            try:
                from core.karma_engine import apply_tribulation_karma
                await apply_tribulation_karma(
                    new_session, player.telegram_id, survived=False,
                    metadata={"trib_id": str(trib.id)})
            except Exception:
                logger.warning("trib thunder fail: karma wire failed", exc_info=True)

            await new_session.commit()
            await query.message.reply_text(result_text, parse_mode="Markdown")


# ─── Heart Demon Phase ────────────────────────────────────────────────────────

async def _show_heart_demon_intro(update: Update, trib: Tribulation, session=None):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    user_id = update.effective_user.id

    close_session = False
    if session is None:
        session = get_session_factory()()
        close_session = True
        # Reload trib inside this session so ORM changes are tracked
        trib = (await session.execute(
            select(Tribulation).where(Tribulation.id == trib.id)
        )).scalar_one_or_none()
        if not trib:
            if close_session:
                await session.close()
            return

    try:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == user_id)
        )).scalar_one_or_none()
        lang = normalize_lang(player.language)

        # Determine dominant Dao element from player's highest-fragment law
        dominant_element = await _get_dominant_dao_element(session, user_id)
        correct_answers = get_heart_demon_correct_answers(dominant_element)

        # Init state in DB
        phases = list(trib.phases_completed or [])
        hd_state = get_heart_demon_state(phases)
        fresh_state = hd_state is None or hd_state.get("q", 0) >= 3
        if fresh_state:
            hd_state = {"q": 0, "score": 0, "ca": correct_answers}
            phases = set_heart_demon_state(phases, hd_state)
            trib.phases_completed = phases
            flag_modified(trib, "phases_completed")
            await session.commit()

        # First entry (no question answered yet) → show tutorial + dominant dao + Begin button.
        # Returning mid-phase → go straight to current question.
        if hd_state["q"] == 0 and hd_state.get("score", 0) == 0:
            target_realm = min(trib.realm, len(REALM_NAMES) - 1)
            phases_display = build_phases_display(trib.phases_completed, target_realm, lang)

            text = t(lang, "trib_heart_demon_title") + "\n"
            text += t(lang, "trib_phases_progress", phases=phases_display) + "\n\n"
            text += t(lang, "trib_heart_demon_tutorial")

            if dominant_element:
                elem_label = HD_ELEMENT_LABELS.get(dominant_element, {}).get(lang, dominant_element)
                text += "\n\n" + t(lang, "trib_hd_your_dao", element=elem_label)
            else:
                text += "\n\n" + t(lang, "trib_hd_no_dao")

            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    t(lang, "btn_trib_hd_begin"),
                    callback_data=f"trib_hd_begin_{trib.id}",
                )
            ]])

            if update.callback_query:
                await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
            return

        # Show current question
        await _send_heart_demon_question(update, trib, player, session, hd_state["q"])
        return

    finally:
        if close_session:
            await session.close()


async def _send_heart_demon_question(update: Update, trib: Tribulation, player, _session, q_idx: int):
    lang = normalize_lang(player.language)

    q_key, opt_keys = HD_QUESTIONS[q_idx]
    question_text = t(lang, q_key)

    # Use TOTAL perception (base + equipment + multipliers + pills/buffs)
    # rather than the raw `player.perception` attribute, otherwise high-realm
    # players never reach the realm × 50 threshold to see the 3rd option.
    try:
        stmt_arts = select(PlayerArtifact).where(
            PlayerArtifact.player_id == player.telegram_id,
            PlayerArtifact.is_equipped == True,
        )
        arts = (await _session.execute(stmt_arts)).scalars().all()
        equip_stats = get_player_equipment_stats(arts)
        stats = calculate_total_stats(player, equip_stats)
        total_perception = stats.get("perception", player.perception)

        # Include active perception_boost pill buffs (e.g. Insight Pill)
        from core.alchemy_engine import get_active_buffs
        active_buffs = await get_active_buffs(_session, player.telegram_id)
        for _b in active_buffs:
            if _b.buff_type == "perception_boost":
                total_perception *= _b.buff_value
        total_perception = int(total_perception)
    except Exception:
        total_perception = player.perception

    # Always show all 3 options. Hiding option 2 punished Fire/Lightning/Earth
    # players whose correct answer for Q1/Q2/Q3 was index 2 — they could never
    # pass the trial because the right choice was invisible (multiple players
    # reported "Não tem como errar essas perguntas / Se só são 2 respostas e 3
    # perguntas e Se acerta 1 passa" — i.e., trial became a coinflip with the
    # winning option hidden).
    buttons = []
    for i, opt_key in enumerate(opt_keys):
        cb = f"trib_hd_answer_{q_idx}_{i}_{trib.id}"
        buttons.append([InlineKeyboardButton(t(lang, opt_key), callback_data=cb)])

    phases = trib.phases_completed or []
    target_realm = min(trib.realm, len(REALM_NAMES) - 1)
    phases_display = build_phases_display(phases, target_realm, lang)

    text = t(lang, "trib_heart_demon_round", q=q_idx + 1, question=question_text)
    # Perception now grants a passive nudge: high-perception players receive a
    # whisper from their dominant Dao, hinting which answer resonates with their
    # path. They still have to decide — but the gate isn't a coinflip.
    if can_see_third_option(total_perception, player.realm):
        dom_elem = getattr(player, "dominant_dao_element", None)
        if dom_elem:
            label = HD_ELEMENT_LABELS.get(dom_elem, {}).get(lang) or dom_elem
            text += f"\n_✨ {label}_"
    text += "\n" + t(lang, "trib_phases_progress", phases=phases_display)

    kb = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def _process_heart_demon_answer(update: Update, trib: Tribulation, session, opt_idx: int):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    trib_id = trib.id
    player_id = trib.player_id

    _pl = (await session.execute(select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)))).scalar_one_or_none()
    if _pl:
        lang = normalize_lang(_pl.language)

    phases = list(trib.phases_completed or [])
    hd_state = get_heart_demon_state(phases)

    if hd_state is None:
        await safe_answer(query, t(lang, "ans_erro_estado_desconhecido"), show_alert=True)
        return

    q_idx = hd_state["q"]
    correct_answers = hd_state["ca"]
    correct = correct_answers[q_idx]
    is_correct = (opt_idx == correct)

    if is_correct:
        hd_state["score"] += 1
        feedback = t(lang, "trib_heart_demon_correct")
    else:
        feedback = t(lang, "trib_heart_demon_wrong")

    hd_state["q"] = q_idx + 1
    phases = set_heart_demon_state(phases, hd_state)
    trib.phases_completed = phases
    flag_modified(trib, "phases_completed")
    await session.commit()
    await session.refresh(trib)

    await query.message.edit_text(feedback, parse_mode="Markdown")
    await asyncio.sleep(2)

    # Use the same session instead of closing and opening a new one
    # This prevents the 'State 15' asyncpg error.
    # Trib is already in this session and refreshed. 
    
    if hd_state["q"] >= 3:
        # All questions done — evaluate
        score = hd_state["score"]
        # 0 correct = fail, 1 = 50%, 2 = 80%, 3 = guaranteed
        if score == 0:
            passed = False
        elif score == 1:
            passed = random.random() < 0.50
        elif score == 2:
            passed = random.random() < 0.80
        else:
            passed = True

        phases = list(trib.phases_completed or [])
        phases = mark_heart_demon_done(phases, passed)
        trib.phases_completed = phases
        flag_modified(trib, "phases_completed")

        if passed:
            result_text = t(lang, "trib_heart_demon_success", score=score)
            target_realm = min(trib.realm, len(REALM_NAMES) - 1)
            phases_display = build_phases_display(trib.phases_completed, target_realm, lang)
            result_text += "\n" + t(lang, "trib_phases_progress", phases=phases_display)
            await session.commit()
            await query.message.reply_text(result_text, parse_mode="Markdown")
            await asyncio.sleep(2)
            await _show_next_phase(update, trib, session=session)
        else:
            # Heart Demon failure → full failure
            trib.status = "failed"
            trib.outcome = "failure_light"
            trib.completed_at = datetime.now(timezone.utc)
            player = (await session.execute(
                select(Player).where(Player.telegram_id == player_id)
            )).scalar_one_or_none()
            from config import get_threshold
            threshold = get_threshold(player.realm, player.sub_layer)
            from core.alchemy_engine import get_active_buffs
            _hd_buffs = await get_active_buffs(session, player.telegram_id)
            _revive_buff = next((b for b in _hd_buffs if b.buff_type == "revive"), None)
            _insurance_buff = next((b for b in _hd_buffs if b.buff_type == "trib_insurance"), None)
            if _revive_buff:
                player.qi = int(player.qi_capacity * 0.5)
                await session.delete(_revive_buff)
                await session.flush()
                _fail_text = t(lang, "pill_revive_triggered")
            elif _insurance_buff:
                player.cultivation_base = threshold * 0.95
                await session.delete(_insurance_buff)
                await session.flush()
                _fail_text = t(lang, "trib_insurance_triggered")
            else:
                player.cultivation_base = threshold * 0.80
                _fail_text = t(lang, "trib_heart_demon_fail")
            # Track A item 4 — Karma: a failed Heart Demon trial breeds resentment (-10).
            try:
                from core.karma_engine import apply_tribulation_karma
                await apply_tribulation_karma(
                    session, player.telegram_id, survived=False,
                    metadata={"trib_id": str(trib.id)})
            except Exception:
                logger.warning("trib heart-demon fail: karma wire failed", exc_info=True)
            await session.commit()
            await query.message.reply_text(_fail_text, parse_mode="Markdown")
    else:
        # Next question
        player = (await session.execute(
            select(Player).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()
        await _send_heart_demon_question(update, trib, player, session, hd_state["q"])


async def _get_dominant_dao_element(session, user_id: int) -> str | None:
    """Return the Dao element of the law the player has the most fragments in."""
    stmt = (
        select(PlayerDaoFragment, DaoLawCatalog)
        .join(DaoLawCatalog, PlayerDaoFragment.dao_law_id == DaoLawCatalog.id)
        .where(PlayerDaoFragment.player_id == user_id, PlayerDaoFragment.fragments_count > 0)
        .order_by(desc(PlayerDaoFragment.fragments_count))
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return None
    _, law = rows[0]
    return law.element


# ─── Dao Trial Phase ──────────────────────────────────────────────────────────

async def _show_dao_trial(update: Update, trib: Tribulation, session=None):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    user_id = update.effective_user.id

    close_session = False
    if session is None:
        session = get_session_factory()()
        close_session = True

    try:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == user_id)
        )).scalar_one_or_none()
        lang = normalize_lang(player.language)

        # Fetch dao fragments
        stmt = select(PlayerDaoFragment).where(PlayerDaoFragment.player_id == user_id)
        fragment_rows = (await session.execute(stmt)).scalars().all()
        fragments_by_law = [{"fragments_count": f.fragments_count, "is_completed": f.is_completed, "insight_level": f.insight_level} for f in fragment_rows]

        # Get 3000 Dao Laws tribulation bonus
        trib_bonus = 0.0
        try:
            from core.dao_laws_engine import get_dao_laws_bonuses
            laws_b = await get_dao_laws_bonuses(session, user_id, player.realm)
            trib_bonus = laws_b.get("tribulation_bonus", 0.0)
        except Exception:
            pass
        dao_info = calculate_dao_chance(player, fragments_by_law, tribulation_bonus=trib_bonus)

        target_realm = min(trib.realm, len(REALM_NAMES) - 1)
        phases_display = build_phases_display(trib.phases_completed or [], target_realm, lang)

        text = t(lang, "trib_dao_title") + "\n"
        text += t(lang, "trib_phases_progress", phases=phases_display) + "\n\n"
        text += t(lang, "trib_dao_intro") + "\n\n"
        text += t(lang, "trib_dao_chance_display",
                  chance=dao_info["chance"],
                  have=dao_info["total_fragments"],
                  required=dao_info["required"]) + "\n"

        if "foundation" in dao_info["penalties"]:
            text += t(lang, "trib_dao_rejection_foundation") + "\n"
        if "core" in dao_info["penalties"]:
            text += t(lang, "trib_dao_rejection_core") + "\n"
        if dao_info["perfect_bonus"]:
            text += t(lang, "trib_dao_perfect_bonus") + "\n"
        if dao_info.get("tribulation_bonus"):
            text += t(lang, "trib_dao_laws_bonus") + "\n"

        if dao_info["can_attempt"]:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "trib_dao_attempt"), callback_data=f"trib_dao_go_{trib.id}")],
                [InlineKeyboardButton(t(lang, "trib_dao_retreat"), callback_data=f"trib_dao_flee_{trib.id}")],
            ])
        else:
            text += "\n" + t(lang, "trib_dao_not_enough_fragments",
                              have=dao_info["total_fragments"],
                              required=dao_info["required"])
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "trib_dao_retreat"), callback_data=f"trib_dao_flee_{trib.id}")],
            ])

        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    finally:
        if close_session:
            await session.close()


async def _run_dao_phase(update: Update, trib: Tribulation, session, _context):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    user_id = update.effective_user.id
    trib_id = trib.id
    query = update.callback_query

    player = (await session.execute(
        select(Player).where(Player.telegram_id == user_id)
    )).scalar_one_or_none()
    lang = normalize_lang(player.language)

    stmt = select(PlayerDaoFragment).where(PlayerDaoFragment.player_id == user_id)
    fragment_rows = (await session.execute(stmt)).scalars().all()
    fragments_by_law = [{"fragments_count": f.fragments_count, "is_completed": f.is_completed, "insight_level": f.insight_level} for f in fragment_rows]

    # Get 3000 Dao Laws tribulation bonus
    trib_bonus = 0.0
    try:
        from core.dao_laws_engine import get_dao_laws_bonuses
        laws_b = await get_dao_laws_bonuses(session, user_id, player.realm)
        trib_bonus = laws_b.get("tribulation_bonus", 0.0)
    except Exception:
        pass
    dao_info = calculate_dao_chance(player, fragments_by_law, tribulation_bonus=trib_bonus)

    # Release session before sleep to avoid idle_in_transaction_session_timeout
    await session.close()

    await query.message.edit_text(t(lang, "trib_dao_confronting"), parse_mode="Markdown")
    await asyncio.sleep(3)

    passed = random.random() < (dao_info["chance"] / 100.0)

    # Fresh session for DB writes
    async with get_session_factory()() as new_session:
        trib = (await new_session.execute(
            select(Tribulation).where(Tribulation.id == trib_id)
        )).scalar_one_or_none()
        player = (await new_session.execute(
            select(Player).where(Player.telegram_id == user_id)
        )).scalar_one_or_none()

        if not trib or not player:
            await query.message.reply_text("⚠️ Error: tribulation data not found.")
            return

        if passed:
            phases = list(trib.phases_completed or [])
            if "dao" not in phases:
                phases.append("dao")
            trib.phases_completed = phases
            flag_modified(trib, "phases_completed")
            await new_session.commit()

            result_text = t(lang, "trib_dao_success")
            target_realm = min(trib.realm, len(REALM_NAMES) - 1)
            phases_display = build_phases_display(trib.phases_completed, target_realm, lang)
            result_text += "\n" + t(lang, "trib_phases_progress", phases=phases_display)
            await query.message.reply_text(result_text, parse_mode="Markdown")
            await asyncio.sleep(2)
            await _show_next_phase(update, trib, session=new_session)
        else:
            trib.status = "failed"
            trib.outcome = "failure_light"
            trib.completed_at = datetime.now(timezone.utc)
            from config import get_threshold
            threshold = get_threshold(player.realm, player.sub_layer)
            from core.alchemy_engine import get_active_buffs
            _dao_trib_buffs = await get_active_buffs(new_session, player.telegram_id)
            _revive_buff = next((b for b in _dao_trib_buffs if b.buff_type == "revive"), None)
            _insurance_buff = next((b for b in _dao_trib_buffs if b.buff_type == "trib_insurance"), None)
            if _revive_buff:
                player.qi = int(player.qi_capacity * 0.5)
                await new_session.delete(_revive_buff)
                await new_session.flush()
            elif _insurance_buff:
                player.cultivation_base = threshold * 0.95
                await new_session.delete(_insurance_buff)
                await new_session.flush()
            else:
                player.cultivation_base = threshold * 0.80

            # Track A item 4 — Karma: a failed Dao trial breeds resentment (-10).
            try:
                from core.karma_engine import apply_tribulation_karma
                await apply_tribulation_karma(
                    new_session, player.telegram_id, survived=False,
                    metadata={"trib_id": str(trib.id)})
            except Exception:
                logger.warning("trib dao fail: karma wire failed", exc_info=True)

            penalty_lines = []
            if "foundation" in dao_info["penalties"]:
                penalty_lines.append(t(lang, "trib_dao_rejection_foundation"))
            if "core" in dao_info["penalties"]:
                penalty_lines.append(t(lang, "trib_dao_rejection_core"))

            if _revive_buff:
                result_text = t(lang, "pill_revive_triggered")
            elif _insurance_buff:
                result_text = t(lang, "trib_insurance_triggered")
            else:
                result_text = t(lang, "trib_dao_fail")
                if penalty_lines:
                    result_text += "\n" + "\n".join(penalty_lines)

            await new_session.commit()
            await query.message.reply_text(result_text, parse_mode="Markdown")


# ─── Final Realm Grant ────────────────────────────────────────────────────────

async def _grant_realm_advancement(update: Update, trib: Tribulation, session):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    user_id = trib.player_id

    player = (await session.execute(
        select(Player).where(Player.telegram_id == user_id)
    )).scalar_one_or_none()
    lang = normalize_lang(player.language)

    target_realm = min(trib.realm, len(REALM_NAMES) - 1)
    target_realm_name = REALM_NAMES[target_realm]

    from config import get_threshold
    threshold = get_threshold(player.realm, player.sub_layer)

    bonus = 1.1 + (target_realm * 0.05)

    player.cultivation_base -= threshold
    player.realm = target_realm
    player.sub_layer = 1

    player.battle_power = int(player.battle_power * bonus)
    player.soul_strength = int(player.soul_strength * bonus)
    player.perception = int(player.perception * bonus)
    player.luck = int(player.luck * bonus)
    player.qi_capacity *= bonus

    # BUG [jogador] 2026-08-11 — a resistência a pílulas é POR REINO por contrato
    # (docstring de get_pill_effectiveness: "uses this realm"), mas o único reset
    # vivia no ramo de breakthrough SIMPLES de game_logic — inalcançável para
    # realm>=4, que rompe SEMPRE por tribulação. Todo realm-up limpa o contador.
    try:
        from core.alchemy_engine import reset_medicine_resistance
        await reset_medicine_resistance(session, user_id)
    except Exception:
        logger.warning("medicine resistance reset failed on trib realm-up", exc_info=True)

    trib.status = "completed"
    trib.outcome = "success"
    trib.completed_at = datetime.now(timezone.utc)

    from core.bp_engine import update_bp_mission
    await update_bp_mission(session, user_id, "win_tribulation")

    # MV-2 §0 — a weekly quest 12 ("tribulation_survive") NUNCA progredia:
    # faucet órfão descoberto na auditoria do MV-1 (a UI mentia). Mesmo padrão
    # dos outros wires; melhoria-estrita em main (precedente moyu/bp_claimable).
    try:
        from core.quest_engine import track_quest
        await track_quest(session, user_id, "tribulation_survive", 1)
    except Exception:
        logger.warning("tribulation_survive track_quest failed", exc_info=True)

    # v16.3 — Karma wire. Surviving a heavenly trial is a Righteous-side
    # event (the heavens recognize the cultivator's resilience). Crystallization
    # fires inside apply_karma if this push tips the player past R3+ thresholds.
    try:
        from core.karma_engine import apply_karma
        await apply_karma(
            session, user_id, "tribulation_survive",
            metadata={"trib_id": str(trib.id), "target_realm": int(target_realm)},
        )
    except Exception:
        logger.warning("karma wire on tribulation success failed", exc_info=True)

    await session.commit()

    # Global broadcast for significant realm-ups (realm 5+)
    if target_realm >= 5:
        from core.announcement_engine import broadcast as _broadcast
        asyncio.create_task(_broadcast(
            "trib_global_announcement",
            pref_key="anomaly_global",
            name=escape_markdown(player.dao_name or player.display_name or player.username or "???"),
            realm=target_realm_name,
        ))

    result_text = t(lang, "trib_all_phases_complete") + "\n"
    result_text += t(lang, "trib_success_normal", target_realm_name=target_realm_name)

    # Perfect scroll chance for Realm 8+
    if target_realm >= 8:
        scroll_name = await _maybe_award_tribulation_scroll(session, user_id)
        if scroll_name:
            result_text += t(lang, "trib_perfect_scroll", scroll=scroll_name)

    # Dao fragment rewards
    from core.dao_engine import grant_random_fragments
    dao_rewards = await grant_random_fragments(session, user_id, random.randint(1, 3), player.realm)
    if dao_rewards:
        dao_lines = []
        for dr in dao_rewards:
            dao_lines.append(f"{dr['law_emoji']} {dr['law_name']} ({dr['fragments']}/{dr['total']})")
        result_text += t(lang, "trib_dao_fragments", lines="\n".join(dao_lines))

    # D5 (v16.6): guaranteed first Dao Law on reaching Soul Transformation (realm 5).
    from core.dao_laws_engine import grant_first_law_on_unlock
    _first_law_msg = await grant_first_law_on_unlock(
        session, user_id, target_realm, perception=int(player.perception or 100), lang=lang)
    if _first_law_msg:
        result_text += "\n\n" + _first_law_msg

    # Commit scroll + dao fragment rewards
    await session.commit()

    if update.callback_query:
        await update.callback_query.message.reply_text(result_text, parse_mode="Markdown")
    else:
        await update.message.reply_text(result_text, parse_mode="Markdown")



async def _global_announcement(context, key: str, **kwargs):
    from core.i18n import t as _t
    async with get_session_factory()() as session:
        stmt = select(Player.telegram_id, Player.language)
        all_pps = (await session.execute(stmt)).all()
        for uid, p_lang in all_pps:
            p_lang = normalize_lang(p_lang)
            msg = _t(p_lang, key, **kwargs)
            try:
                await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            except Exception:
                pass


async def historico_tribulacao(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        from core.utils import _ensure_player
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language)
        user_id = player.telegram_id

        stmt = select(Tribulation).where(
            Tribulation.player_id == user_id,
            Tribulation.status.in_(["completed", "failed"])
        ).order_by(desc(Tribulation.completed_at)).limit(5)
        tribs = (await session.execute(stmt)).scalars().all()

        if not tribs:
            await update.message.reply_text(t(lang, "trib_no_history"))
            return

        text = t(lang, "trib_history_title")
        for t_hist in tribs:
            realm = REALM_NAMES[min(t_hist.realm, len(REALM_NAMES) - 1)]
            status = "✅" if t_hist.status == "completed" else "❌"
            date = t_hist.completed_at.strftime("%d/%m %H:%M")
            phases_done = [p for p in (t_hist.phases_completed or []) if isinstance(p, str)]
            text += f"{status} *{realm}* — {t_hist.outcome or 'n/a'} ({date}) [{', '.join(phases_done) or '—'}]\n"

        await update.message.reply_text(text, parse_mode="Markdown")
