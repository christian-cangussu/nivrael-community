"""Handler for the Celestial System — Mahayana progression gates."""

import logging
from datetime import datetime, timezone
from sqlalchemy import select
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

from core.celestial_engine import (
    MAHAYANA_REALM, MAX_TRIALS, TRIALS, TRIAL_GATES,
    can_attempt_trial, attempt_trial, estimate_trial_chance,
    get_heavenly_dao_bonus, HEAVENLY_DAO_MIN_PATHS,
    get_celestial_resonance, RESONANCE_BONUS_BY_PIECES,
)
from core.body_tempering_engine import TEMPERING_LEVELS, CELESTIAL_TEMPERING_MIN, MAX_TEMPERING_LEVEL
from core.dao_laws_engine import count_heavenly_discoveries
from core.i18n import t
from database.db import get_session_factory
from database.models import PlayerArtifact, PlayerBuff
from core.utils import _ensure_player, safe_handler, rate_limit, safe_answer


def _fmt_cooldown(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


async def _load_trial_context(session, player):
    """
    Compute everything the trial needs: total stats, Heavenly Dao bonus,
    3000-laws tribulation bonus, Tribulation Blessing buff, and insurance flag.
    Does NOT consume buffs — only reads. Consumption happens on attempt.
    """
    from core.game_logic import calculate_total_stats, get_player_equipment_stats
    from core.beast_engine import get_companion_beast, get_companion_bonuses
    from core.dao_engine import get_player_dao_bonuses
    from core.dao_laws_engine import get_dao_laws_bonuses

    arts = (await session.execute(
        select(PlayerArtifact).where(
            PlayerArtifact.player_id == player.telegram_id,
            PlayerArtifact.is_equipped == True,
        )
    )).scalars().all()
    equip_stats = get_player_equipment_stats(arts) if arts else None

    comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
    comp_bonus = get_companion_bonuses(comp_beast, comp_catalog) if (comp_beast and comp_catalog) else None

    dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)
    total_stats = calculate_total_stats(player, equip_stats, companion_bonus=comp_bonus, dao_bonuses=dao_bonuses)

    heavenly = await get_heavenly_dao_bonus(session, player.telegram_id, player.realm)
    laws_b = await get_dao_laws_bonuses(session, player.telegram_id, player.realm)
    trib_3000 = laws_b.get("tribulation_bonus", 0.0) if laws_b else 0.0

    now = datetime.now(timezone.utc)
    trib_blessing_buff = (await session.execute(
        select(PlayerBuff).where(
            PlayerBuff.player_id == player.telegram_id,
            PlayerBuff.buff_type == "trib_blessing",
            PlayerBuff.expires_at > now,
        )
    )).scalar_one_or_none()
    blessing_bonus = float(trib_blessing_buff.buff_value) if trib_blessing_buff else 0.0

    insurance_buff = (await session.execute(
        select(PlayerBuff).where(
            PlayerBuff.player_id == player.telegram_id,
            PlayerBuff.buff_type == "trib_insurance",
            PlayerBuff.expires_at > now,
        )
    )).scalar_one_or_none()

    return {
        "total_soul": total_stats["soul_strength"],
        "total_bp": total_stats["total_battle_power"],
        "heavenly_dao_bonus": heavenly["all_mult_bonus"],
        "heavenly_info": heavenly,
        "trib_3000_bonus": trib_3000,
        "trib_blessing_bonus": blessing_bonus,
        "trib_blessing_buff": trib_blessing_buff,
        "insurance_buff": insurance_buff,
    }


async def _build_dashboard(player, session, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    lines = [t(lang, "celestial_title"), ""]

    passed = player.celestial_trials_passed or 0
    lines.append(t(lang, "celestial_trials_header", passed=passed, total=MAX_TRIALS))
    for n in range(1, MAX_TRIALS + 1):
        info = TRIALS[n]
        icon = "✅" if passed >= n else "⏳"
        name = t(lang, info["name_key"])
        lines.append(f"  {icon} {info['emoji']} {name}")
    lines.append("")

    hd = await get_heavenly_dao_bonus(session, player.telegram_id, player.realm)
    lines.append(t(lang, "celestial_heavenly_header"))
    if hd["unlocked"]:
        pct = int(hd["all_mult_bonus"] * 100)
        lines.append(t(lang, "celestial_heavenly_active", paths=hd["qualifying"], bonus=pct))
    else:
        lines.append(t(lang, "celestial_heavenly_locked",
                       paths=hd["paths"], need=HEAVENLY_DAO_MIN_PATHS))
    lines.append("")

    lines.append(t(lang, "celestial_body_header"))
    body_level = getattr(player, "body_tempering_level", 0) or 0
    if body_level >= CELESTIAL_TEMPERING_MIN:
        body_info = TEMPERING_LEVELS.get(body_level, {})
        body_name = t(lang, body_info.get("name_key", "tempering_level_10"))
        body_emoji = body_info.get("emoji", "✨")
        lines.append(t(lang, "celestial_body_transformed_named",
                       emoji=body_emoji, name=body_name, level=body_level))
        # Show unlocked passives
        if body_level >= 11:
            lines.append(t(lang, "celestial_body_trib_passive", bonus=10))
        if body_level >= 12:
            lines.append(t(lang, "celestial_body_regen_passive", bonus=5))
    else:
        lines.append(t(lang, "celestial_body_untransformed"))
    lines.append("")

    # Celestial Resonance — set bonus from grade-8 equipped pieces.
    reso = await get_celestial_resonance(session, player.telegram_id)
    r_pieces = reso.get("pieces", 0)
    r_bonus_pct = int(reso.get("bonus", 0.0) * 100)
    lines.append(t(lang, "celestial_resonance_header"))
    if r_pieces > 0:
        lines.append(t(lang, "celestial_resonance_active",
                       pieces=min(r_pieces, 3), bonus=r_bonus_pct))
    else:
        lines.append(t(lang, "celestial_resonance_inactive"))
    lines.append("")

    # Heavenly Laws (F-11.5 — 100 new laws, gated by 1st trial)
    lines.append(t(lang, "celestial_heavenly_laws_header"))
    trials_passed = player.celestial_trials_passed or 0
    heavenly_complete = False  # D2 (v16.6): gates the meditate quick-launch below
    if trials_passed < 1:
        lines.append(t(lang, "celestial_heavenly_laws_locked"))
    else:
        discovered, total = await count_heavenly_discoveries(session, player.telegram_id)
        total = total or 100
        lines.append(t(lang, "celestial_heavenly_laws_progress",
                       discovered=discovered, total=total))
        if discovered >= total and total > 0:
            heavenly_complete = True
            lines.append(t(lang, "celestial_heavenly_laws_complete"))
            # D2: explain why the celestial meditation is gone — it only ever
            # discovered Heavenly Laws (none left). Point them at Dao meditation
            # for the 3000 Laws. Honest disclosure (lei §1), never a silent trap.
            lines.append(t(lang, "celestial_heavenly_laws_all_done"))
    lines.append("")

    lines.append(t(lang, "celestial_essence_balance", value=player.celestial_essence or 0))

    buttons = []
    check = can_attempt_trial(player)
    if check["can"]:
        # Preview block — show the player their actual chance with active bonuses.
        ctx = await _load_trial_context(session, player)
        preview = estimate_trial_chance(
            player,
            total_soul=ctx["total_soul"],
            total_bp=ctx["total_bp"],
            heavenly_dao_bonus=ctx["heavenly_dao_bonus"],
            tribulation_bonus_3000=ctx["trib_3000_bonus"],
            trib_blessing_bonus=ctx["trib_blessing_bonus"],
        )
        if preview["available"]:
            trial_name = t(lang, TRIALS[preview["trial_num"]]["name_key"])
            lines.append("")
            lines.append(t(lang, "celestial_preview_header", trial=trial_name))
            lines.append(t(lang, "celestial_preview_chance",
                           pct=int(preview["full_clear_chance"] * 100),
                           per=int(preview["per_round_chance"] * 100),
                           rounds=preview["rounds"]))
            bonus_lines = []
            if ctx["heavenly_dao_bonus"] > 0:
                bonus_lines.append(t(lang, "celestial_preview_heavenly",
                                     bonus=int(ctx["heavenly_dao_bonus"] * 100)))
            if ctx["trib_3000_bonus"] > 0:
                bonus_lines.append(t(lang, "celestial_preview_trib3000",
                                     bonus=int(ctx["trib_3000_bonus"] * 100)))
            if ctx["trib_blessing_bonus"] > 0:
                bonus_lines.append(t(lang, "celestial_preview_blessing",
                                     bonus=int(ctx["trib_blessing_bonus"] * 100)))
            if ctx["insurance_buff"]:
                bonus_lines.append(t(lang, "celestial_preview_insurance"))
            if bonus_lines:
                lines.append(t(lang, "celestial_preview_active_bonuses"))
                lines.extend(bonus_lines)

        trial_name = t(lang, TRIALS[check["trial_num"]]["name_key"])
        buttons.append([InlineKeyboardButton(
            t(lang, "btn_celestial_attempt_trial", trial=trial_name),
            callback_data=f"cel_attempt_{check['trial_num']}",
        )])
    elif check.get("reason_key") == "celestial_on_cooldown":
        lines.append("")
        lines.append(t(lang, "celestial_trial_cooldown",
                       time=_fmt_cooldown(check["remaining"])))
    elif check.get("reason_key") == "celestial_need_sublayer":
        lines.append("")
        lines.append(t(lang, "celestial_trial_need_sublayer",
                       sub=check["need_sub"]))

    # F-11.5 — Celestial Meditation quick-launch (visible once 1st trial passed
    # and player is not already meditating). D2 (v16.6): hidden once all 100
    # Heavenly Laws are mastered — the meditation has nothing left to discover
    # and would just burn 800 qi / 8h vs the cheaper Dao meditation.
    if (player.celestial_trials_passed or 0) >= 1 and not player.is_meditating and not heavenly_complete:
        buttons.append([InlineKeyboardButton(
            t(lang, "btn_celestial_meditate"),
            callback_data="cel_start_celestial_med",
        )])

    # v14.3 D-6b — Apex Reflection Chamber: surface the entry point on the
    # /celestial dashboard for cultivators who passed all 4 gates. Otherwise
    # the command is undiscoverable except via the unlock banner.
    from core.celestial_engine import is_apex
    if await is_apex(session, player):
        buttons.append([InlineKeyboardButton(
            t(lang, "btn_apex_chamber"),
            callback_data="apex_chamber_open",
        )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="nav_main")])

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


@safe_handler
@rate_limit(1)
async def celestial_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"

        if player.realm < MAHAYANA_REALM:
            msg = t(lang, "celestial_sealed",
                    realm=t(lang, "realm_name_8", fallback="Mahayana"))
            if update.callback_query:
                await safe_answer(update.callback_query)
                await update.callback_query.edit_message_text(msg, parse_mode="Markdown")
            else:
                await update.effective_message.reply_text(msg, parse_mode="Markdown")
            await session.commit()
            return

        text, kb = await _build_dashboard(player, session, lang)
        await session.commit()

    if update.callback_query:
        await safe_answer(update.callback_query)
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def _attempt_trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"

        check = can_attempt_trial(player)
        if not check["can"]:
            reason_key = check.get("reason_key")
            if reason_key == "celestial_need_sublayer":
                msg = t(lang, "celestial_trial_need_sublayer", sub=check.get("need_sub", "?"))
            else:
                msg = t(lang, reason_key or "celestial_trial_not_available")
            await query.edit_message_text(msg, parse_mode="Markdown")
            await session.commit()
            return

        ctx = await _load_trial_context(session, player)
        insurance_active = ctx["insurance_buff"] is not None

        result = attempt_trial(
            player,
            total_soul=ctx["total_soul"],
            total_bp=ctx["total_bp"],
            heavenly_dao_bonus=ctx["heavenly_dao_bonus"],
            tribulation_bonus_3000=ctx["trib_3000_bonus"],
            trib_blessing_bonus=ctx["trib_blessing_bonus"],
            insurance_active=insurance_active,
        )

        # Consume Tribulation Blessing (single-use) regardless of outcome.
        if ctx["trib_blessing_buff"] is not None:
            await session.delete(ctx["trib_blessing_buff"])

        # Consume insurance only on failure (same rule as normal tribulation).
        if not result["success"] and insurance_active and ctx["insurance_buff"] is not None:
            await session.delete(ctx["insurance_buff"])

        # v14.3 D-6a — after a successful trial, check Apex unlock. The third
        # trial is the last gate; if the player also has 100/100 Heavenly Daos
        # at realm 10 IX, this fires the Apex achievement + 500 jade.
        apex_grant = None
        if result["success"]:
            from core.celestial_engine import try_grant_apex
            apex_grant = await try_grant_apex(session, player)

        await session.commit()

    if result["success"]:
        msg = t(lang, "celestial_trial_success",
                trial=result["trial_num"],
                essence=result["essence_gained"])
    else:
        key = "celestial_trial_failure_insured" if result.get("insurance_used") else "celestial_trial_failure"
        msg = t(lang, key,
                trial=result["trial_num"],
                rounds=result["rounds_survived"],
                total=result["rounds_total"],
                loss=result["cb_loss_pct"],
                cooldown=result["cooldown_hours"])

    # v14.3 D-6a — append Apex unlock banner to the trial success message.
    if apex_grant is not None:
        from core.celestial_engine import APEX_JADE_REWARD
        msg += "\n\n" + t(lang, "apex_unlock_banner", jade=APEX_JADE_REWARD)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_celestial")
    ]])
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)

    # v14.3 (audit fix): also fire the canonical achievement notification with
    # the 🏆 framing, title chip and stat-bonus list. Reuses notify_achievements
    # so the badge/title/+25%CB+20%BP show in the same DM format as every other
    # unlock — players were confused ("não recebi o achievement" — they got the
    # banner but missed the formal achievement card).
    if apex_grant is not None and apex_grant.get("achievements"):
        try:
            from handlers.achievements import notify_achievements
            await notify_achievements(context, update.effective_user.id, apex_grant["achievements"])
        except Exception as _e:
            logger.warning("Apex achievement notification failed: %s", _e)


async def _start_celestial_meditation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """F-11.5: quick-launch Celestial Meditation from the /celestial dashboard."""
    from datetime import timedelta
    from config import DAO_MEDITATION_TYPES

    query = update.callback_query
    await safe_answer(query)

    med_info = DAO_MEDITATION_TYPES.get("celestial_dao")
    if not med_info:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"

        if player.realm < med_info["min_realm"]:
            await query.edit_message_text(
                t(lang, "celestial_med_needs_mahayana"),
                parse_mode="Markdown",
            )
            await session.commit()
            return

        if (player.celestial_trials_passed or 0) < 1:
            await query.edit_message_text(
                t(lang, "celestial_med_needs_trial"),
                parse_mode="Markdown",
            )
            await session.commit()
            return

        # D2 (v16.6): block once all Heavenly Laws are mastered — nothing left to
        # discover, so the 800 qi / 8h session would be wasted vs Dao meditation.
        _hl_disc, _hl_total = await count_heavenly_discoveries(session, player.telegram_id)
        if _hl_total > 0 and _hl_disc >= _hl_total:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_celestial"),
            ]])
            await query.edit_message_text(
                t(lang, "celestial_heavenly_laws_all_done"),
                parse_mode="Markdown",
                reply_markup=kb,
            )
            await session.commit()
            return

        if player.qi < med_info["qi_cost"]:
            await query.edit_message_text(
                t(lang, "celestial_med_needs_qi", need=med_info["qi_cost"], have=int(player.qi)),
                parse_mode="Markdown",
            )
            await session.commit()
            return

        if player.is_meditating:
            await query.edit_message_text(
                t(lang, "celestial_med_already_meditating"),
                parse_mode="Markdown",
            )
            await session.commit()
            return

        now = datetime.now(timezone.utc)
        player.is_meditating = True
        player.meditation_type = "celestial_dao"
        player.meditation_end = now + timedelta(minutes=med_info["duration_minutes"])
        player.meditation_multiplier = 0.0
        player.last_online = now
        player.qi = max(0.0, player.qi - med_info["qi_cost"])
        await session.commit()

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_celestial"),
    ]])
    await query.edit_message_text(
        t(lang, "celestial_med_started", hours=med_info["duration_minutes"] // 60),
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ─── Apex Reflection Chamber (D-6b) ─────────────────────────────────────────

# 0.5%/h chance to roll an Insight (per DESIGN_DECISIONS_v14.md §D-6b).
APEX_INSIGHT_CHANCE_PER_HOUR = 0.005


def _settle_chamber(player) -> int:
    """Resolve a pending chamber session: count hours since entered_at and
    roll once per full hour for an Insight. Mutates `player.divine_law_insights`
    and clears `apex_chamber_entered_at`. Returns the number of insights gained.

    Rolling per full elapsed hour (not per arbitrary tick) keeps the math
    deterministic and avoids the "I refreshed and got 7 insights in a row"
    abuse vector. Pure stochastic at sub-hour granularity stays tied to
    /camara_reflexao polls.
    """
    import random
    if player.apex_chamber_entered_at is None:
        return 0
    now = datetime.now(timezone.utc)
    elapsed = (now - player.apex_chamber_entered_at).total_seconds()
    full_hours = int(elapsed // 3600)
    gained = 0
    for _ in range(full_hours):
        if random.random() < APEX_INSIGHT_CHANCE_PER_HOUR:
            gained += 1
    if gained:
        player.divine_law_insights = (player.divine_law_insights or 0) + gained
    return gained


def _fmt_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


@safe_handler
@rate_limit(2)
async def camara_reflexao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apex Reflection Chamber — only Apex Cultivators can enter.

    Toggle behaviour: first call enters the chamber (sets entered_at), the
    next call settles the session (rolls insights for elapsed hours, exits).
    """
    from core.celestial_engine import is_apex
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"

        if not await is_apex(session, player):
            await session.commit()
            target = update.callback_query.message if update.callback_query else update.message
            await target.reply_text(
                t(lang, "apex_chamber_locked"),
                parse_mode="Markdown",
            )
            return

        if player.is_meditating:
            await session.commit()
            target = update.callback_query.message if update.callback_query else update.message
            await target.reply_text(
                t(lang, "apex_chamber_already_active"),
                parse_mode="Markdown",
            )
            return

        # ── Already inside chamber → settle and exit ──
        if player.apex_chamber_entered_at is not None:
            entered = player.apex_chamber_entered_at
            elapsed = (datetime.now(timezone.utc) - entered).total_seconds()
            gained = _settle_chamber(player)
            player.apex_chamber_entered_at = None
            total = player.divine_law_insights or 0
            await session.commit()
            target = update.callback_query.message if update.callback_query else update.message
            await target.reply_text(
                t(lang, "apex_chamber_session_ended",
                  elapsed=_fmt_elapsed(elapsed), gained=gained, total=total),
                parse_mode="Markdown",
            )
            return

        # ── Not inside → show the chamber preview + Enter button ──
        insights = player.divine_law_insights or 0
        await session.commit()

    lines = [
        t(lang, "apex_chamber_title"),
        "",
        t(lang, "apex_chamber_status", insights=insights),
        "",
        t(lang, "apex_chamber_flavor"),
    ]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "apex_chamber_btn_enter"), callback_data="apex_chamber_enter")],
    ])
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


async def _apex_chamber_enter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"

        from core.celestial_engine import is_apex
        if not await is_apex(session, player):
            await session.commit()
            await query.edit_message_text(t(lang, "apex_chamber_locked"), parse_mode="Markdown")
            return

        if player.is_meditating:
            await session.commit()
            await query.edit_message_text(t(lang, "apex_chamber_already_active"), parse_mode="Markdown")
            return

        # If already entered, idempotent — keep the original entered_at so
        # the player doesn't lose accumulated time by re-clicking.
        if player.apex_chamber_entered_at is None:
            player.apex_chamber_entered_at = datetime.now(timezone.utc)
        await session.commit()

    pct = APEX_INSIGHT_CHANCE_PER_HOUR * 100
    await query.edit_message_text(
        t(lang, "apex_chamber_session_started", pct=f"{pct:.1f}"),
        parse_mode="Markdown",
    )


async def celestial_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data:
        return False
    data = query.data

    if data == "cmd_celestial":
        await celestial_command(update, context)
        return True
    if data.startswith("cel_attempt_"):
        await _attempt_trial_callback(update, context)
        return True
    if data == "cel_start_celestial_med":
        await _start_celestial_meditation_callback(update, context)
        return True
    if data == "apex_chamber_enter":
        await _apex_chamber_enter_callback(update, context)
        return True
    if data == "apex_chamber_open":
        # Surface from /celestial dashboard. Reuses the same toggle logic
        # as /camara_reflexao — first call shows preview + Enter button,
        # subsequent calls settle the session.
        await safe_answer(query)
        await camara_reflexao_command(update, context)
        return True
    return False
