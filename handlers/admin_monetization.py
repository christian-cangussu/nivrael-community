from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from sqlalchemy import select, desc
from database.db import get_session_factory
from database.models import Player, Transaction
from core.monetization import add_vip_spending, activate_battle_pass
from core.economy import format_currency, SUSPICIOUS_TRADE_THRESHOLD
from config import ADMIN_USERS, ADMIN_ALERT_THRESHOLD
from core.i18n import t
from core.utils import safe_handler, rate_limit, escape_markdown, normalize_lang

@safe_handler
@rate_limit(1)
async def cmd_admin_darjade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USERS:
        return
    lang = normalize_lang(update.effective_user.language_code)

    if len(context.args) < 2:
        await update.message.reply_text(t(lang, "admin_usage_darjade"))
        return
        
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text(t(lang, "admin_invalid_value"))
        return
        
    async with get_session_factory()() as session:
        from sqlalchemy import select
        stmt = select(Player).where(Player.telegram_id == target_id)
        player = (await session.execute(stmt)).scalar_one_or_none()
        
        if not player:
            await update.message.reply_text(t(lang, "admin_player_not_found"))
            return
            
        if amount > 0:
            from core.monetization import grant_jade
            await grant_jade(session, player, amount)
        else:
            # Negative = admin balance CORRECTION (debit) — the old behavior.
            # Never routes through grant_jade: lifetime_jade_earned is
            # monotonic income, and a debit is not income (review finding:
            # grant_jade silently no-ops on <=0 while the reply claimed
            # success).
            player.spirit_jade = int(player.spirit_jade or 0) + amount
        await session.commit()
        
        await update.message.reply_text(t(lang, "admin_gave_jade", amount=amount, name=(player.dao_name or player.display_name or str(player.telegram_id))))

@safe_handler
@rate_limit(1)
async def cmd_admin_setvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USERS:
        return
    lang = normalize_lang(update.effective_user.language_code)

    if len(context.args) < 2:
        await update.message.reply_text(t(lang, "admin_usage_setvip"))
        return
        
    try:
        target_id = int(context.args[0])
        amount_eur = float(context.args[1])
    except ValueError:
        await update.message.reply_text(t(lang, "admin_invalid_value"))
        return
        
    async with get_session_factory()() as session:
        from sqlalchemy import select
        stmt = select(Player).where(Player.telegram_id == target_id)
        player = (await session.execute(stmt)).scalar_one_or_none()
        
        if not player:
            await update.message.reply_text(t(lang, "admin_player_not_found"))
            return
            
        res = await add_vip_spending(session, target_id, amount_eur)
        await session.commit()
        
        await update.message.reply_text(t(lang, "admin_added_vip", amount=amount_eur, name=(player.dao_name or player.display_name or str(player.telegram_id)), level=res['new_level']))

@safe_handler
@rate_limit(1)
async def cmd_admin_ativarpass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USERS:
        return
    lang = normalize_lang(update.effective_user.language_code)

    if len(context.args) < 1:
        await update.message.reply_text(t(lang, "admin_usage_ativarpass"))
        return
        
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(t(lang, "admin_invalid_value"))
        return
        
    async with get_session_factory()() as session:
        from sqlalchemy import select
        stmt = select(Player).where(Player.telegram_id == target_id)
        player = (await session.execute(stmt)).scalar_one_or_none()
        
        if not player:
            await update.message.reply_text(t(lang, "admin_player_not_found"))
            return
            
        success = await activate_battle_pass(session, target_id)
        await session.commit()
        
        if success:
            await update.message.reply_text(t(lang, "admin_pass_activated", name=(player.dao_name or player.display_name or str(player.telegram_id))))
        else:
            await update.message.reply_text(t(lang, "admin_pass_already", name=(player.dao_name or player.display_name or str(player.telegram_id))))

@safe_handler
@rate_limit(1)
async def cmd_admin_evento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to manually trigger a celestial event.
    Usage: /admin_evento <event_type>
    Types: meteor_shower, dao_convergence, immortal_auction, spirit_tide, demonic_invasion
    """
    if update.effective_user.id not in ADMIN_USERS:
        return

    if len(context.args) < 1:
        await update.message.reply_text(
            "Usage:\n"
            "  /admin_evento list\n"
            "  /admin_evento <type>         — activate\n"
            "  /admin_evento stop <type>    — deactivate one\n"
            "  /admin_evento stop all       — deactivate all\n\n"
            "Types: meteor_shower, dao_convergence, immortal_auction, spirit_tide, demonic_invasion"
        )
        return

    event_type = context.args[0].lower()

    if event_type == "list":
        from sqlalchemy import select
        from database.models import CelestialEvent
        from datetime import datetime, timezone
        async with get_session_factory()() as session:
            events = (await session.execute(select(CelestialEvent))).scalars().all()
        now = datetime.now(timezone.utc)
        lines = ["🌌 *Celestial Events*\n"]
        for ev in events:
            if ev.is_active and ev.expires_at and ev.expires_at > now:
                delta = ev.expires_at - now
                h = int(delta.total_seconds() // 3600)
                m = int((delta.total_seconds() % 3600) // 60)
                status = f"✅ ACTIVE — {h}h {m}m left"
            else:
                status = "⏸ Inactive"
            lines.append(f"{ev.emoji} `{ev.type}` — {ev.name}\n   {status}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # ── stop <type|all> ───────────────────────────────────────────────────────
    if event_type == "stop":
        stop_target = context.args[1].lower() if len(context.args) > 1 else "all"
        from sqlalchemy import select
        from database.models import CelestialEvent
        async with get_session_factory()() as session:
            if stop_target == "all":
                stmt = select(CelestialEvent).where(CelestialEvent.is_active == True)
                active = (await session.execute(stmt)).scalars().all()
                stopped = [ev.type for ev in active]
                for ev in active:
                    ev.is_active = False
                    ev.expires_at = None
                await session.commit()
                if stopped:
                    await update.message.reply_text(
                        f"⏹ Stopped {len(stopped)} event(s): {', '.join(f'`{ev}`' for ev in stopped)}",
                        parse_mode="Markdown"
                    )
                else:
                    await update.message.reply_text("ℹ️ No active events to stop.")
            else:
                ev = (await session.execute(
                    select(CelestialEvent).where(CelestialEvent.type == stop_target)
                )).scalar_one_or_none()
                if not ev:
                    await update.message.reply_text(f"❌ Unknown event type: `{stop_target}`", parse_mode="Markdown")
                    return
                if not ev.is_active:
                    await update.message.reply_text(f"ℹ️ `{stop_target}` is already inactive.", parse_mode="Markdown")
                    return
                ev.is_active = False
                ev.expires_at = None
                await session.commit()
                await update.message.reply_text(f"⏹ Event `{stop_target}` stopped.", parse_mode="Markdown")
        return

    from sqlalchemy import select
    from database.models import CelestialEvent, Player
    from datetime import datetime, timezone, timedelta
    from core.i18n import t

    async with get_session_factory()() as session:
        ev = (await session.execute(
            select(CelestialEvent).where(CelestialEvent.type == event_type)
        )).scalar_one_or_none()

        if not ev:
            await update.message.reply_text(f"❌ Event type `{event_type}` not found.", parse_mode="Markdown")
            return

        now = datetime.now(timezone.utc)
        ev.is_active = True
        ev.started_at = now
        ev.expires_at = now + timedelta(hours=ev.duration_hours)
        await session.commit()

        # ── Event-specific side effects ───────────────────────────────────────
        side_note = ""
        if event_type == "immortal_auction":
            from handlers.events import inject_immortal_auction_items
            injected = await inject_immortal_auction_items(session, ev.expires_at)
            await session.commit()
            side_note = f"\n🏮 Injected {injected} NPC listings into the marketplace."
        elif event_type == "demonic_invasion":
            from core.boss_engine import spawn_bosses
            hp_mult = 2.0  # Demonic Invasion doubles boss HP
            spawned_list = await spawn_bosses(session, hp_mult=hp_mult)
            await session.commit()
            if spawned_list:
                names = ", ".join(f"{b.tier}={escape_markdown(b.name)}" for b in spawned_list)
                side_note = f"\n💀 {len(spawned_list)} World Boss(es) spawned with {hp_mult}× HP! ({names})"
            else:
                side_note = "\n⚠️ All tier bosses already active (no new spawn)."

        event_name = ev.name
        event_emoji = ev.emoji
        event_desc = ev.description
        expires_at = ev.expires_at
        duration_hours = ev.duration_hours

        # Broadcast to all players
        all_pps = (await session.execute(select(Player.telegram_id, Player.language))).all()

    import asyncio
    bot = update.get_bot()
    for pid, p_lang in all_pps:
        lang = normalize_lang(p_lang)
        msg = t(lang, "event_started_broadcast",
                emoji=event_emoji, name=event_name,
                description=event_desc, hours=duration_hours)
        try:
            await bot.send_message(chat_id=pid, text=msg, parse_mode="Markdown")
        except Exception:
            pass
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"✅ Event *{event_name}* activated for {duration_hours}h!\nExpires: `{expires_at.strftime('%Y-%m-%d %H:%M UTC')}`{side_note}",
        parse_mode="Markdown"
    )


@safe_handler
@rate_limit(1)
async def cmd_admin_suspicious(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent high-value trades that exceeded the suspicious threshold.
    Usage: /admin_suspicious [limit]
    """
    if update.effective_user.id not in ADMIN_USERS:
        return

    limit = 10
    if context.args:
        try:
            limit = max(1, min(50, int(context.args[0])))
        except ValueError:
            pass

    async with get_session_factory()() as session:
        # High-value trades
        stmt = (
            select(Transaction)
            .where(Transaction.type == "trade", Transaction.price >= SUSPICIOUS_TRADE_THRESHOLD)
            .order_by(desc(Transaction.created_at))
            .limit(limit)
        )
        txs = (await session.execute(stmt)).scalars().all()

    if not txs:
        await update.message.reply_text(
            f"✅ No trades above {format_currency(SUSPICIOUS_TRADE_THRESHOLD)} stones found."
        )
        return

    lines = [f"🚨 *Suspicious Trades (≥{format_currency(SUSPICIOUS_TRADE_THRESHOLD)} stones)*\n"]
    for tx in txs:
        ts = tx.created_at.strftime("%m/%d %H:%M")
        lines.append(
            f"• `{str(tx.id)[:8]}` {tx.from_player} → {tx.to_player} | "
            f"*{format_currency(tx.price)}* stones | {ts}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def alert_admins_suspicious_trade(bot, trade_id: str, initiator_id: int,
                                        target_id: int, total_stones: int):
    """Send a direct alert to all configured admins for very large trades (>= 1M stones)."""
    if total_stones < ADMIN_ALERT_THRESHOLD:
        return
    msg = (
        f"⚠️ *Large Trade Alert*\n"
        f"Trade `{str(trade_id)[:8]}` — {format_currency(total_stones)} stones\n"
        f"Initiator: `{initiator_id}` → Target: `{target_id}`"
    )
    for admin_id in ADMIN_USERS:
        try:
            await bot.send_message(chat_id=admin_id, text=msg, parse_mode="Markdown")
        except Exception:
            pass


@safe_handler
@rate_limit(1)
async def cmd_admin_spawnboss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spawn World Bosses immediately (one per tier).
    Usage: /admin_spawnboss [hp_mult]
    Example: /admin_spawnboss 1.5  (bosses with 1.5× HP)
    """
    if update.effective_user.id not in ADMIN_USERS:
        return

    hp_mult = 1.0
    if context.args:
        try:
            hp_mult = max(0.1, float(context.args[0]))
        except ValueError:
            await update.message.reply_text("Usage: /admin\\_spawnboss \\[hp\\_mult\\]\nExample: `/admin_spawnboss 1.5`", parse_mode="Markdown")
            return

    from core.boss_engine import spawn_bosses, get_player_tier, TIER_EMOJIS
    from core.game_logic import format_number as _fn

    async with get_session_factory()() as session:
        bosses = await spawn_bosses(session, hp_mult=hp_mult)
        await session.commit()

        if not bosses:
            await update.message.reply_text("⚠️ All tier bosses are already active or no players in any tier.")
            return

        boss_by_tier = {b.tier: b for b in bosses}
        all_pps = (await session.execute(select(Player.telegram_id, Player.language, Player.realm))).all()

    # Broadcast to all players — each gets notified about their tier's boss
    import asyncio
    from core.i18n import t as _t
    bot = update.get_bot()
    for pid, p_lang, p_realm in all_pps:
        plang = normalize_lang(p_lang)
        player_tier = get_player_tier(p_realm)
        boss = boss_by_tier.get(player_tier)
        if not boss:
            boss = bosses[0]
        tier_emoji = TIER_EMOJIS.get(boss.tier, "👹")
        tier_label = _t(plang, f"boss_tier_{boss.tier}")
        msg = _t(plang, "global_boss_spawn_tier",
                 tier_emoji=tier_emoji, tier=tier_label,
                 emoji=boss.emoji, name=boss.name, hp=f"{boss.hp:,}")
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"👹 {boss.name}", callback_data="cmd_boss")]])
        try:
            await bot.send_message(chat_id=pid, text=msg, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            pass
        await asyncio.sleep(0.05)

    # Admin summary
    lines = [f"✅ *{len(bosses)} World Boss(es) spawned!* (×{hp_mult})"]
    for b in bosses:
        lines.append(f"  {TIER_EMOJIS.get(b.tier, '👹')} {b.tier}: *{escape_markdown(b.name)}* — HP: *{_fn(b.hp)}*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@safe_handler
@rate_limit(1)
async def cmd_admin_reset_resistance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """H-11: Manually reset medicine resistance for a player.

    Usage: /admin_reset_resistance <player_telegram_id>
    """
    if update.effective_user.id not in ADMIN_USERS:
        return
    lang = normalize_lang(update.effective_user.language_code)

    if len(context.args) < 1:
        await update.message.reply_text("Usage: /admin_reset_resistance <player_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(t(lang, "admin_invalid_value"))
        return

    async with get_session_factory()() as session:
        stmt = select(Player).where(Player.telegram_id == target_id)
        player = (await session.execute(stmt)).scalar_one_or_none()
        if not player:
            await update.message.reply_text(t(lang, "admin_player_not_found"))
            return

        from core.alchemy_engine import reset_medicine_resistance
        await reset_medicine_resistance(session, player.telegram_id)
        await session.commit()

    await update.message.reply_text(
        f"✅ Medicine resistance reset for {player.dao_name or player.display_name or target_id}"
    )


def setup_admin_monetization_handlers(application):
    application.add_handler(CommandHandler("admin_darjade", cmd_admin_darjade))
    application.add_handler(CommandHandler("admin_setvip", cmd_admin_setvip))
    application.add_handler(CommandHandler("admin_ativarpass", cmd_admin_ativarpass))
    application.add_handler(CommandHandler("admin_evento", cmd_admin_evento))
    application.add_handler(CommandHandler("admin_suspicious", cmd_admin_suspicious))
    application.add_handler(CommandHandler("admin_spawnboss", cmd_admin_spawnboss))
    application.add_handler(CommandHandler("admin_reset_resistance", cmd_admin_reset_resistance))
