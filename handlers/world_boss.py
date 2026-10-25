from core.utils import safe_handler, rate_limit, safe_answer, normalize_lang, resolve_chat_player_id
from core.i18n import t
import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select

from core.game_logic import format_number, get_player_equipment_stats, calculate_total_stats
from core.boss_engine import (
    get_active_boss_for_tier,
    get_last_ended_boss_for_tier,
    attack_boss,
    get_boss_ranking,
    get_boss_full_ranking,
    get_player_boss_damage,
    build_boss_display,
    build_boss_results_display,
    distribute_rewards,
    get_player_tier,
    ATTACK_COOLDOWN_SECONDS,
    TIER_ORDER,
    TIER_EMOJIS,
)
from database.db import get_session_factory
from database.models import Player, PlayerArtifact

logger = logging.getLogger(__name__)


def _boss_keyboard(lang: str, can_attack: bool, player_tier: str, view_tier: str) -> InlineKeyboardMarkup:
    rows = []
    if view_tier != player_tier:
        # Viewing another tier — no attack, show locked
        rows.append([InlineKeyboardButton(t(lang, "boss_tier_locked_btn"), callback_data="boss_tier_locked")])
    elif can_attack:
        rows.append([InlineKeyboardButton(t(lang, "btn_attack_boss"), callback_data="boss_attack")])
    else:
        rows.append([InlineKeyboardButton(t(lang, "btn_boss_cooldown"), callback_data="boss_cooldown")])

    rows.append([InlineKeyboardButton(t(lang, "btn_refresh"), callback_data="boss_refresh")])

    # Tier navigation buttons (show other tiers)
    tier_buttons = []
    for tier in TIER_ORDER:
        if tier == view_tier:
            continue
        emoji = TIER_EMOJIS.get(tier, "👹")
        tier_label = t(lang, f"boss_tier_{tier}")
        tier_buttons.append(InlineKeyboardButton(
            f"{emoji} {tier_label}",
            callback_data=f"boss_tier_{tier}",
        ))
    if tier_buttons:
        rows.append(tier_buttons)

    rows.append([InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")])
    return InlineKeyboardMarkup(rows)


def _results_keyboard(lang: str, view_tier: str) -> InlineKeyboardMarkup:
    rows = []
    # Tier navigation
    tier_buttons = []
    for tier in TIER_ORDER:
        if tier == view_tier:
            continue
        emoji = TIER_EMOJIS.get(tier, "👹")
        tier_label = t(lang, f"boss_tier_{tier}")
        tier_buttons.append(InlineKeyboardButton(
            f"{emoji} {tier_label}",
            callback_data=f"boss_tier_{tier}",
        ))
    if tier_buttons:
        rows.append(tier_buttons)
    rows.append([InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")])
    return InlineKeyboardMarkup(rows)


@safe_handler
@rate_limit(1)
async def boss_command(update: Update, context: ContextTypes.DEFAULT_TYPE, tier_override: str | None = None):
    user = update.effective_user
    if not user:
        return

    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(user.id))
        )).scalar_one_or_none()
        if not player:
            lang = normalize_lang(getattr(update.effective_user, 'language_code', 'en'))
            msg = t(lang, "msg_use_start")
            if update.callback_query:
                await safe_answer(update.callback_query, msg, show_alert=True)
            else:
                await update.message.reply_text(msg, parse_mode="Markdown")
            return

        lang = player.language or "en"
        player_tier = get_player_tier(player.realm)
        view_tier = tier_override or player_tier

        boss = await get_active_boss_for_tier(session, view_tier)

        # ── No active boss — check for recent results ─────────────────────
        if not boss:
            ended_boss = await get_last_ended_boss_for_tier(session, view_tier)
            if ended_boss:
                ranking = await get_boss_full_ranking(session, ended_boss.id)
                text = await build_boss_results_display(session, ended_boss, ranking, viewer_id=user.id, lang=lang)
                kb = _results_keyboard(lang, view_tier)
            else:
                tier_name = t(lang, f"boss_tier_{view_tier}")
                text = t(lang, "boss_no_boss_for_tier", tier=tier_name)
                # Still show tier navigation
                rows = []
                tier_buttons = []
                for tier in TIER_ORDER:
                    if tier == view_tier:
                        continue
                    emoji = TIER_EMOJIS.get(tier, "👹")
                    tier_label = t(lang, f"boss_tier_{tier}")
                    tier_buttons.append(InlineKeyboardButton(
                        f"{emoji} {tier_label}",
                        callback_data=f"boss_tier_{tier}",
                    ))
                if tier_buttons:
                    rows.append(tier_buttons)
                rows.append([InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")])
                kb = InlineKeyboardMarkup(rows)

            if update.callback_query:
                await safe_answer(update.callback_query)
                await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
            return

        # ── Active boss ───────────────────────────────────────────────────
        ranking = await get_boss_ranking(session, boss.id)
        player_dmg = await get_player_boss_damage(session, boss.id, player.telegram_id)

        can_attack = (view_tier == player_tier)
        if can_attack:
            if player_dmg and player_dmg.last_hit:
                elapsed = (datetime.now(timezone.utc) - player_dmg.last_hit).total_seconds()
                if elapsed < ATTACK_COOLDOWN_SECONDS:
                    can_attack = False
            if boss.current_hp <= 0:
                can_attack = False

        text = build_boss_display(boss, player_dmg, ranking, lang=lang,
                                  viewer_tier=player_tier if view_tier != player_tier else None)
        kb = _boss_keyboard(lang, can_attack, player_tier, view_tier)

        if update.callback_query:
            await safe_answer(update.callback_query)
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


@safe_handler
@rate_limit(2)
async def boss_attack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if not user or not query:
        return

    lang = normalize_lang(getattr(update.effective_user, 'language_code', 'en'))

    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(user.id))
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query, t(lang, "not_registered"), show_alert=True)
            return

        lang = player.language or "en"

        equipped = (await session.execute(
            select(PlayerArtifact).where(
                PlayerArtifact.player_id == player.telegram_id,
                PlayerArtifact.is_equipped == True,
            )
        )).scalars().all()

        equip_stats = get_player_equipment_stats(list(equipped))

        from core.beast_engine import get_companion_beast, get_companion_bonuses
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        comp_bonus = get_companion_bonuses(comp_beast, comp_catalog)

        from core.dao_engine import get_player_dao_bonuses
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)

        stats = calculate_total_stats(player, equip_stats, comp_bonus, dao_bonuses)
        total_bp = stats["total_battle_power"]

        result = await attack_boss(session, player, total_bp)

        if not result["ok"]:
            await session.commit()
            reason = result["reason"]
            if reason == "no_boss":
                await safe_answer(query, t(lang, "ans_nenhum_boss_activo"), show_alert=True)
            elif reason == "cooldown":
                remaining = result.get("remaining_seconds", 0)
                mins = int(remaining // 60)
                secs = int(remaining % 60)
                await safe_answer(query, t(lang, "ans_cooldown_boss", mins=mins, secs=secs), show_alert=True)
            elif reason == "expired":
                await safe_answer(query, t(lang, "ans_o_boss_expirou"), show_alert=True)
            elif reason == "dead":
                await safe_answer(query, t(lang, "ans_o_boss_já_foi"), show_alert=True)
            return

        # ── Boss killed — distribute rewards immediately ───────────────────
        if result["killed"]:
            from handlers.events import get_event_multipliers
            event_mults = await get_event_multipliers(session)
            loot_mult = event_mults.get("boss_loot_mult", 1.0)

            boss_id = result["boss_id"]
            from database.models import WorldBoss
            boss_obj = (await session.execute(
                select(WorldBoss).where(WorldBoss.id == boss_id)
            )).scalar_one_or_none()

            notifications = []
            if boss_obj:
                notifications = await distribute_rewards(session, boss_obj, loot_mult=loot_mult)

            from core.quest_engine import track_quest
            await track_quest(session, player.telegram_id, "boss_attack", 1)
            await track_quest(session, player.telegram_id, "boss_damage", result["damage"])
            from core.faction_engine import update_quest_progress as fac_quest_progress
            await fac_quest_progress(session, player.telegram_id, "boss_hit")

            from core.body_tempering_engine import add_tempering_progress
            add_tempering_progress(player, 15)

            await session.commit()

            # Build results screen
            if boss_obj:
                ranking = await get_boss_full_ranking(session, boss_id)
                results_text = await build_boss_results_display(
                    session, boss_obj, ranking, viewer_id=user.id, loot_mult=loot_mult, lang=lang
                )
            else:
                results_text = f"💀 *{result['boss_emoji']} {result['boss_name']} DERROTADO!*"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")],
            ])
            await safe_answer(query, t(lang, "ans_golpe_final_boss_destruído"), show_alert=True)
            await query.message.edit_text(results_text, parse_mode="Markdown", reply_markup=kb)

            # Send personal reward DM to each participant
            if notifications:
                import asyncio
                bot = context.bot
                for notif in notifications:
                    try:
                        nlang = notif.get("lang", "en")
                        reward_text = "\n".join(f"  • {r}" for r in notif["rewards"])
                        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
                        tier_name = t(nlang, f"boss_tier_{notif.get('boss_tier', 'mortal')}")
                        if notif["rank"] <= 3:
                            medal = medals[notif["rank"]]
                            header = t(nlang, "boss_reward_medal", medal=medal, rank=notif["rank"])
                        elif notif["is_top"]:
                            header = t(nlang, "boss_reward_top10", rank=notif["rank"])
                        else:
                            header = t(nlang, "boss_participation_reward")
                        msg = (
                            f"{header}\n"
                            f"_{tier_name}_\n\n"
                            f"{t(nlang, 'boss_total_damage', damage=format_number(notif['damage']))}\n\n"
                            f"{t(nlang, 'boss_drops_label')}\n{reward_text}"
                        )
                        await bot.send_message(chat_id=notif["player_id"], text=msg, parse_mode="Markdown")
                    except Exception as e:
                        logger.warning("Failed to send boss reward to %s: %s", notif["player_id"], e)
                    await asyncio.sleep(0.05)
            return

        from core.quest_engine import track_quest
        await track_quest(session, player.telegram_id, "boss_attack", 1)
        await track_quest(session, player.telegram_id, "boss_damage", result["damage"])
        from core.faction_engine import update_quest_progress as fac_quest_progress
        await fac_quest_progress(session, player.telegram_id, "boss_hit")

        from core.body_tempering_engine import add_tempering_progress
        add_tempering_progress(player, 15)

        await session.commit()

    # ── Hit but not killed ────────────────────────────────────────────────
    damage = result["damage"]
    boss_name = result["boss_name"]
    boss_emoji = result["boss_emoji"]
    hp_pct = (result["boss_hp"] / result["boss_max_hp"] * 100) if result["boss_max_hp"] > 0 else 0

    attack_text = t(
        lang, "boss_attack_msg",
        boss_emoji=boss_emoji, boss_name=boss_name,
        damage=format_number(damage),
        hp=format_number(result["boss_hp"]),
        pct=f"{hp_pct:.1f}",
        total_dmg=format_number(result["player_total"]),
        hits=result["player_hits"],
    )
    if result.get("damage_capped"):
        attack_text += t(lang, "boss_damage_capped")
    # Phase change notification
    if result.get("phase_changed"):
        phase_name = t(lang, f"boss_phase_{result['phase']}")
        phase_desc = t(lang, f"boss_phase_desc_{result['phase']}")
        attack_text += t(lang, "boss_phase_changed_alert", phase=phase_name, desc=phase_desc)
    # Phase modifier info
    if result.get("phase_mod", 1.0) != 1.0:
        attack_text += t(lang, "boss_phase_modifier", mod=f"{result['phase_mod']:.1f}")

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_boss_refresh_view"), callback_data="boss_refresh")],
        [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")],
    ])
    await safe_answer(query, t(lang, "ans_boss_attack_damage", damage=format_number(damage)), show_alert=True)
    await query.message.edit_text(attack_text, parse_mode="Markdown", reply_markup=kb)


@safe_handler
@rate_limit(1)
async def boss_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    if not query or not query.data:
        return False

    data = query.data

    if data in ("boss_refresh", "cmd_boss"):
        await boss_command(update, context)
        return True
    elif data == "boss_attack":
        await boss_attack_handler(update, context)
        return True
    elif data.startswith("boss_tier_"):
        tier = data.replace("boss_tier_", "")
        if tier in ("mortal", "spirit", "immortal"):
            await boss_command(update, context, tier_override=tier)
            return True
        elif tier == "locked":
            # Player clicked the locked button
            user = update.effective_user
            async with get_session_factory()() as session:
                player = (await session.execute(select(Player).where(Player.telegram_id == await resolve_chat_player_id(user.id)))).scalar_one_or_none()
                lang = normalize_lang(player.language if player and player.language else getattr(user, 'language_code', 'en'))
            await safe_answer(query, t(lang, "ans_boss_tier_locked"), show_alert=True)
            return True
    elif data == "boss_cooldown":
        user = update.effective_user
        async with get_session_factory()() as session:
            player = (await session.execute(select(Player).where(Player.telegram_id == await resolve_chat_player_id(user.id)))).scalar_one_or_none()
            lang = normalize_lang(player.language if player and player.language else getattr(user, 'language_code', 'en'))
        await safe_answer(query, t(lang, "ans_tens_de_esperar_30"), show_alert=True)
        return True

    return False
