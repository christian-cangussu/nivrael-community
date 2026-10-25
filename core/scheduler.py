import asyncio
import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, update, or_, text
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter
from core.utils import escape_markdown, normalize_lang


async def _safe_send(bot: Bot, chat_id: int, text: str, **kwargs):
    """Send a message with RetryAfter handling.

    ⚠️ WEB-B Fase 2 — recusa `chat_id <= 0` DE IMEDIATO. O jogador que entra
    pelo Google/Apple/e-mail tem `telegram_id` negativo (id sintético), e este
    ficheiro manda DM com esse valor como `chat_id`. Um negativo é um id de
    GRUPO para o Telegram: o risco não é só a chamada desperdiçada por jogador
    por ciclo, é acertar num chat que não é o dele.
    """
    if not chat_id or int(chat_id) <= 0:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 0.5)
        try:
            await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except Exception:
            logging.getLogger(__name__).warning("Retry send failed for %s after flood wait", chat_id)
    except Exception as e:
        logging.getLogger(__name__).warning("Failed to send to %s: %s", chat_id, e)

from config import TICK_INTERVAL_SECONDS, OFFLINE_CAP_SECONDS, CULTIVATION_BATCH_SIZE, ONLINE_THRESHOLD_SECONDS, ADMIN_USERS
from core.game_logic import process_tick, build_breakthrough_message
from core.economy import finalize_auction, cancel_trade
from core.i18n import t
from database.db import get_session_factory, current_world_key
from database.models import Player, MarketplaceListing, P2PTrade, BattlePass

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_bot: Bot | None = None
# Rate-limit admin alerts: only notify once per player per 5 minutes
_tick_fail_notified: dict[int, datetime] = {}
_TICK_FAIL_ALERT_COOLDOWN = timedelta(minutes=5)
# Rate-limit progression block notifications: once per 24h per player per block type
_bt_block_notified: dict[tuple[int, str], datetime] = {}
_BT_BLOCK_COOLDOWN = timedelta(hours=24)


def _should_notify_block(player_id: int, block_type: str, now: datetime) -> bool:
    key = (player_id, block_type)
    last = _bt_block_notified.get(key)
    if last and (now - last) <= _BT_BLOCK_COOLDOWN:
        return False
    _bt_block_notified[key] = now
    return True


def _scheduler_job_listener(event):
    """Log ALL scheduler job errors — catches silent crashes in background jobs."""
    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
    if event.code == EVENT_JOB_ERROR:
        logger.error(
            "SCHEDULER JOB CRASHED: job_id=%s exception=%s",
            event.job_id, event.exception, exc_info=event.exception,
        )
        # Also write to stderr directly
        import sys, traceback
        sys.stderr.write(f"\n!!! SCHEDULER JOB CRASHED: {event.job_id}: {event.exception}\n")
        if event.exception:
            traceback.print_exception(type(event.exception), event.exception, event.exception.__traceback__, file=sys.stderr)
        sys.stderr.flush()
    elif event.code == EVENT_JOB_MISSED:
        logger.warning("SCHEDULER JOB MISSED: job_id=%s scheduled=%s", event.job_id, event.scheduled_run_time)


# A half-provisioned / paused / unreachable secondary world makes its per-world
# jobs fail EVERY cycle. We THROTTLE each (job, world) failure to at most one log
# per window, so a broken world can never flood the logs (2026-06-24 incident: a
# world whose `players` table did not exist made cultivation_tick churn ~1100
# failing batches per 30s tick).
#
# THROTTLE, not permanent mute: a TRANSIENT blip (pool/lock/connection timeout —
# which the broad `except Exception` also catches, INCLUDING on `main`) is
# reported once and then RE-reported if it recurs after the window, so main's own
# scheduler errors are never silenced for the whole process. A persistently-broken
# world just logs ~once per window (self-documenting, not a flood).
import time as _time

_REPORT_THROTTLE_SECONDS = 600.0  # at most one report per (job, world) per 10 min
_world_job_last_report: dict = {}  # (job, world) -> monotonic ts of last report


def reset_world_degraded_state(world_key: str) -> None:
    """Forget the throttle timestamps for a world (call when it is (re)provisioned
    / re-activated) so a later failure is reported immediately, not after the
    window."""
    for pair in [p for p in _world_job_last_report if p[1] == world_key]:
        _world_job_last_report.pop(pair, None)


def _report_world_job_failure(jobname: str, world_key: str, exc: Exception) -> None:
    """Log a per-world scheduler failure, THROTTLED to at most once per
    ``_REPORT_THROTTLE_SECONDS`` per (job, world). Each emitted line carries the
    full traceback + the world's creds-free DB target so a broken world is
    self-diagnosing."""
    pair = (jobname, world_key)
    now = _time.monotonic()
    last = _world_job_last_report.get(pair)
    if last is not None and (now - last) < _REPORT_THROTTLE_SECONDS:
        return
    _world_job_last_report[pair] = now
    try:
        from database.db import world_db_target
        target = world_db_target(world_key)
    except Exception:
        target = "?"
    logger.error(
        "scheduler job %s skipped for world %r (db=%s): %s — the world's schema is "
        "missing or its DB is unreachable. Set it to 'maintenance' (and restart) or "
        "re-provision it. Throttling repeats for this (job, world) to once per %.0fs.",
        jobname, world_key, target, exc, _REPORT_THROTTLE_SECONDS, exc_info=True,
    )


def _multiworld(fn):
    """Wrap a scheduler job so it runs once PER ACTIVE world (Sistema
    Multi-Servidor — Fase 3).

    SINGLE-WORLD FAST PATH: when only ``main`` is active (today's deployment),
    the job runs EXACTLY as before — ``await fn()`` with NO contextvar bound,
    resolving to main. Only when an ACTIVE secondary world exists does it iterate,
    binding ``current_world`` per world (task-local) so every
    ``get_session_factory()()`` inside routes to that world. Background senders the
    job spawns via ``asyncio.create_task(...)`` inherit a COPY of the current
    context, so their DMs/queries stay on the right world too.

    A world that is still building ('maintenance'), paused, or left over from a
    FAILED provision is NOT active → it is never ticked (a half-built world has no
    schema; ticking it would spin/spam). A failure in one world is reported (once)
    and never blocks the other worlds or main."""
    import functools

    @functools.wraps(fn)
    async def _wrapped(*args, **kwargs):
        from database.db import iter_active_world_keys, use_world
        keys = iter_active_world_keys()
        if len(keys) == 1:
            await fn(*args, **kwargs)  # byte-identical to the old single-world path
            return
        for key in keys:
            try:
                with use_world(key):
                    await fn(*args, **kwargs)
            except Exception as exc:
                _report_world_job_failure(getattr(fn, "__name__", str(fn)), key, exc)

    return _wrapped


class _WorldLabelBot:
    """Proxy fino sobre o Bot dos jobs (hotfix "A Volta" 2026-07-07): toda DM
    disparada por um job rodando no contexto de um mundo SECUNDÁRIO ganha a
    linha `🌐 <mundo>` no topo — mata a confusão main/test quando a mesma conta
    joga em 2 servidores. Jobs do main ficam byte-idênticos (sem prefixo).
    Só send_message é interceptado; qualquer outro atributo delega ao Bot real."""

    def __init__(self, bot: Bot):
        self._raw = bot

    def __getattr__(self, name):
        return getattr(self._raw, name)

    async def send_message(self, chat_id=None, text=None, **kwargs):
        try:
            wk = current_world_key()
        except Exception:
            wk = "main"
        if text and wk != "main":
            text = f"🌐 {wk}\n{text}"
        return await self._raw.send_message(chat_id=chat_id, text=text, **kwargs)


def init_scheduler(bot: Bot):
    global _bot
    _bot = _WorldLabelBot(bot)

    # Fase 3: register every player/world job wrapped so it ticks each registered
    # world. `_aj` defaults to multi-world; pass mw=False for infra jobs with no
    # per-world state (keep_alive). The dynamic sect_war_resolve date job is bound
    # to its world explicitly inside sect_war_job (it's added outside this helper).
    def _aj(fn, *a, mw=True, **kw):
        scheduler.add_job(_multiworld(fn) if mw else fn, *a, **kw)

    # Listen for job errors/misses
    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
    scheduler.add_listener(_scheduler_job_listener, EVENT_JOB_ERROR | EVENT_JOB_MISSED)

    # Common kwargs: prevent job pile-up when a job runs longer than its interval
    _interval_opts = dict(
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    _cron_opts = dict(
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )

    _aj(
        cultivation_tick,
        "interval",
        seconds=TICK_INTERVAL_SECONDS,
        id="cultivation_tick",
        **_interval_opts,
    )
    _aj(
        market_cleanup,
        "interval",
        minutes=1,
        id="market_cleanup",
        **_interval_opts,
    )
    _aj(
        tribulation_cleanup,
        "interval",
        hours=1,
        id="tribulation_cleanup",
        **_interval_opts,
    )
    _aj(
        sect_war_job,
        "cron",
        day_of_week="fri",
        hour=20,
        minute=0,
        id="sect_war",
        **_cron_opts,
    )
    # 2026-06-13: recovery net — resolves any active war whose 1h window has
    # passed (covers restart-lost date jobs AND misfires). Idempotent: the
    # resolve row-locks the war and flips is_active.
    _aj(
        sect_war_sweep_job,
        "interval",
        minutes=10,
        id="sect_war_sweep",
        **_interval_opts,
    )
    _aj(
        herb_garden_job,
        "cron",
        hour=0,
        minute=0,
        id="herb_garden",
        **_cron_opts,
    )
    _aj(
        territory_bonus_job,
        "cron",
        hour=12,
        minute=0,
        id="territory_bonus",
        **_cron_opts,
    )
    _aj(reset_daily_quests, "cron", hour=0, minute=0, timezone=timezone.utc, id="daily_quests_reset", **_cron_opts)
    _aj(reset_weekly_quests, "cron", day_of_week="mon", hour=0, minute=0, timezone=timezone.utc, id="weekly_quests_reset", **_cron_opts)
    _aj(reset_battle_pass_daily, "cron", hour=0, minute=0, timezone=timezone.utc, id="daily_bp_reset", **_cron_opts)

    # Celestial Events expiry check (every 5 minutes)
    _aj(
        celestial_events_check_job,
        "interval",
        minutes=5,
        id="celestial_events_check",
        **_interval_opts,
    )

    # Keep alive job — pure log, no per-world state → single-world (mw=False).
    _aj(keep_alive_job, "interval", minutes=10, id="keep_alive", mw=False, **_interval_opts)
    _aj(
        expedition_check_job,
        "interval",
        hours=1,
        id="expedition_check",
        **_interval_opts,
    )
    # v16.4 — World Sect recruiter (a house chooses a cultivator via affinity)
    _aj(
        world_sect_recruiter_tick,
        "interval",
        hours=1,
        id="world_sect_recruiter",
        **_interval_opts,
    )
    # Onda 3 — NPC Cultivators: echo recently-active players into the persistent
    # population + top each continent back up (lifecycle refill). Low-freq.
    _aj(
        npc_cultivator_tick,
        "interval",
        hours=6,
        id="npc_cultivator",
        **_interval_opts,
    )
    # Onda 3 — Heaven's Whispers: synthesize world-events + deliver one capped,
    # opted-in, daily-deduped whisper per eligible player (anti-churn, Lei §1).
    _aj(
        heavens_whispers_tick,
        "interval",
        hours=6,
        id="heavens_whispers",
        **_interval_opts,
    )
    # Onda 4a — Bounty Board: expire stale contracts + refill each continent's
    # pool from dark-karma NPC cultivators. Low-freq, idempotent, capped.
    _aj(
        bounty_refresh_tick,
        "interval",
        hours=6,
        id="bounty_refresh",
        **_interval_opts,
    )
    # World Pulse Fase 1 — the world's heartbeat: the 9 ancient sects act on a
    # weighted-utility menu (recruit/fortify/raid/claim/inheritance/strife),
    # write the Chronicle, and the loud beats whisper + post reactive bounties.
    # NOT _interval_opts: this leans on the sect-war lesson (misfire_grace_time
    # 3600 + coalesce) so a busy loop / deploy at fire time doesn't silently drop
    # a beat; idempotency rides on the per-sect last_pulse_at guard.
    from core.world_pulse_engine import WORLD_PULSE_INTERVAL_HOURS as _WP_HOURS
    _aj(
        world_pulse_tick,
        "interval",
        hours=_WP_HOURS,
        id="world_pulse",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    _aj(
        world_boss_spawn_job,
        "cron",
        day_of_week="wed,sat",
        hour=18,
        minute=0,
        id="world_boss_spawn",
        **_cron_opts,
    )
    _aj(
        world_boss_check_job,
        "interval",
        minutes=5,
        id="world_boss_check",
        **_interval_opts,
    )
    _aj(
        world_boss_expire_job,
        "interval",
        hours=1,
        id="world_boss_expire",
        **_interval_opts,
    )
    # v14.5 — Notifications Pack (N-10 + Q-2/Q-3/Q-4). Single consolidated job
    # that DMs players when their pill is about to expire, alchemy energy
    # refilled, breakthrough threshold met, or tribulation cooldown ended.
    # Each branch honours the matching `PlayerNotificationPref` toggle.
    _aj(
        notifications_pack_tick,
        "interval",
        seconds=60,
        id="notifications_pack",
        **_interval_opts,
    )
    # v15.1.5 — Arena queue sweep. Expires overdue 'waiting' rows + tries to
    # match remaining waiters in case the per-request opportunistic try_match
    # missed a pair (e.g., 2 players joined into different webserver workers
    # and neither sweep saw the other yet). Also delivers DMs for matched +
    # expired chat-originated rows so chat players see results without polling.
    _aj(
        arena_queue_sweep,
        "interval",
        seconds=60,
        id="arena_queue_sweep",
        **_interval_opts,
    )
    # v15.1.5 hotfix — Meditation finalize sweep for OFFLINE players. The
    # main cultivation_tick skips players with last_online > OFFLINE_CAP_SECONDS
    # to save CPU, so a player who starts meditation and closes the app stays
    # with is_meditating=True forever until they come back AND the tick fires.
    # This sweep scans every meditating player whose end-time passed, finalizes
    # the row, and fires the bell so they see "🧘 Meditation finished" next
    # time they open the app (and a Telegram DM if they have the preference).
    _aj(
        meditation_sweep,
        "interval",
        seconds=60,
        id="meditation_sweep",
        **_interval_opts,
    )
    scheduler.start()
    logger.info("☯️ Scheduler started — ticking every %ds", TICK_INTERVAL_SECONDS)


async def market_cleanup():
    now = datetime.now(timezone.utc)
    try:
        async with get_session_factory()() as session:
            stmt_mkt = select(MarketplaceListing).where(
                MarketplaceListing.is_sold == False,
                MarketplaceListing.expires_at < now
            )
            listings = (await session.execute(stmt_mkt)).scalars().all()
            for listing in listings:
                await finalize_auction(session, listing.id)
                if _bot and listing.seller_id is not None:  # skip NPC listings
                    try:
                        seller = (await session.execute(select(Player).where(Player.telegram_id == listing.seller_id))).scalar_one_or_none()
                        lang = normalize_lang(seller.language if seller else None)
                        msg = t(lang, "sched_auction_expired", item_id=listing.item_id)
                        await _bot.send_message(chat_id=listing.seller_id, text=msg, parse_mode="Markdown")
                    except Exception as e:
                        logger.warning("Failed to notify seller %s on auction expire: %s", listing.seller_id, e)

            stmt_trd = select(P2PTrade).where(
                P2PTrade.status == "pending",
                P2PTrade.expires_at < now
            )
            trades = (await session.execute(stmt_trd)).scalars().all()
            for trade in trades:
                await cancel_trade(session, trade)
                if _bot:
                    try:
                        for party_id in (trade.initiator_id, trade.target_id):
                            party = (await session.execute(select(Player).where(Player.telegram_id == party_id))).scalar_one_or_none()
                            lang = normalize_lang(party.language if party else None)
                            msg = t(lang, "sched_trade_cancelled")
                            await _bot.send_message(chat_id=party_id, text=msg)
                    except Exception as e:
                        logger.warning("Failed to notify trade parties %s/%s: %s", trade.initiator_id, trade.target_id, e)

            await session.commit()
    except Exception as e:
        logger.error("market_cleanup failed: %s", e, exc_info=True)


async def tribulation_cleanup():
    from config import TRIBULATION_WINDOW_HOURS, TRIBULATION_PENALTY_RATE, get_threshold, REALM_NAMES
    from database.models import Tribulation
    
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=TRIBULATION_WINDOW_HOURS)
    
    async with get_session_factory()() as session:
        stmt = select(Tribulation).where(
            Tribulation.status == "pending",
            Tribulation.started_at < cutoff
        )
        expired = (await session.execute(stmt)).scalars().all()
        
        for trib in expired:
            trib.status = "expired"
            trib.completed_at = now
            
            stmt_p = select(Player).where(Player.telegram_id == trib.player_id)
            player = (await session.execute(stmt_p)).scalar_one_or_none()
            if player:
                threshold = get_threshold(player.realm, player.sub_layer)
                excess = player.cultivation_base - threshold
                if excess > 0:
                    player.cultivation_base -= (excess * TRIBULATION_PENALTY_RATE)
                
                if _bot:
                    try:
                        target_realm = REALM_NAMES[trib.realm]
                        lang = player.language or "en"
                        msg = t(lang, "sched_tribulation_expired", realm=target_realm, penalty=f"{TRIBULATION_PENALTY_RATE*100:.0f}")
                        await _safe_send(_bot, player.telegram_id, msg, parse_mode="Markdown")
                    except Exception as e:
                        logger.warning("Failed to notify player %s tribulation expiry: %s", player.telegram_id, e)
        
        await session.commit()


async def herb_garden_job():
    from core.sect_engine import distribute_herb_garden_rewards
    logger.info("🌿 Running Herb Garden distribution...")
    async with get_session_factory()() as session:
        await distribute_herb_garden_rewards(session)
        await session.commit()


async def sect_war_job():
    from core.sect_engine import start_sect_war
    logger.info("⚔️ Starting Sect War — opening 1h attack window...")
    async with get_session_factory()() as session:
        result = await start_sect_war(session)
        await session.commit()

    if not result.get("started"):
        logger.info("⚔️ Sect War not started: %s", result.get("reason", "unknown"))
        return

    # Fase 3: bind the dynamic resolve to THIS world so it fires against the same
    # world that started the war (the scheduler calls date jobs with no contextvar
    # set, and sect_war_job runs per-world via _multiworld). main keeps the legacy
    # id "sect_war_resolve"; secondary worlds get a world-suffixed id so they don't
    # clobber each other (replace_existing). The per-world sect_war_sweep_job is the
    # recovery net if a restart drops the in-memory date job.
    from database.db import current_world_key, use_world as _use_world
    _wkey = current_world_key()
    if _wkey == "main":
        _resolve_target = sect_war_resolve_job
        _resolve_id = "sect_war_resolve"
    else:
        async def _resolve_target():
            with _use_world(_wkey):
                await sect_war_resolve_job()
        _resolve_id = f"sect_war_resolve_{_wkey}"
    scheduler.add_job(
        _resolve_target,
        "date",
        run_date=datetime.now(timezone.utc) + timedelta(hours=1),
        id=_resolve_id,
        replace_existing=True,
        # 2026-06-13: without these, the APScheduler default grace is 1s — a
        # busy event loop at fire time silently discarded the resolve (and a
        # restart loses this in-memory job entirely; the sweep below covers
        # that). Late resolution is harmless: resolve just reads `attacks`.
        coalesce=True,
        misfire_grace_time=3600,
    )

    if _bot:
        territories = result.get("territories", [])
        terr_text = "\n".join(f"  🏴 *{t['name']}*" for t in territories)
        sect_count = result.get("sect_count", 0)
        member_ids = result.get("member_ids", [])

        if member_ids:
            # v15.3 — fire bell notifications (mini-app + persistent inbox)
            # so members see the war fire even without opening chat. Each
            # row deduped by sect_war_id so retries don't double-notify.
            async def _bell_sect_war_start():
                from core.notification_engine import notify as _notify
                from database.models import SectWarState as _SWS
                async with get_session_factory()() as session:
                    war_id = (await session.execute(
                        select(_SWS.id).where(_SWS.is_active == True)
                    )).scalar_one_or_none()
                    if war_id is None:
                        return
                    for pid in member_ids:
                        try:
                            await _notify(
                                session, pid, "sect_war_started",
                                title_key="notif_sect_war_started_title",
                                body_key="notif_sect_war_started_body",
                                payload={"sect_count": sect_count},
                                ref_id=f"sect_war:{war_id}:start",
                                icon="⚔️",
                                target_tab="sect",
                                priority=2,
                            )
                        except Exception:
                            logger.exception("notify sect_war_started failed pid=%s", pid)
                    await session.commit()
            asyncio.create_task(_bell_sect_war_start())

            async def _send_sect_war_start():
                from database.models import Player as _P_
                async with get_session_factory()() as session:
                    pp_data = (await session.execute(select(_P_.telegram_id, _P_.language).where(_P_.telegram_id.in_(member_ids)))).all()
                sent_sw, failed_sw = 0, 0
                for pid, p_lang in pp_data:
                    lang = normalize_lang(p_lang)
                    msg = t(lang, "global_sect_war_start", sect_count=sect_count, terr_text=terr_text)
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton(t(lang, "btn_sect_war"), callback_data="sect_war_info")]
                    ])
                    try:
                        await _bot.send_message(chat_id=pid, text=msg, parse_mode="Markdown", reply_markup=kb)
                        sent_sw += 1
                    except Exception:
                        failed_sw += 1
                    await asyncio.sleep(0.05)
                logger.info("📢 Sect war start broadcast: %d sent, %d failed, %d total", sent_sw, failed_sw, len(pp_data))
            asyncio.create_task(_send_sect_war_start())


async def sect_war_resolve_job():
    from core.sect_engine import resolve_sect_war
    logger.info("⚔️ Resolving Sect War — calculating winners...")
    async with get_session_factory()() as session:
        result = await resolve_sect_war(session)
        await session.commit()

    if not result.get("resolved"):
        logger.info("⚔️ War resolve skipped: %s", result.get("reason", "unknown"))
        return

    if _bot:
        results = result.get("results", [])
        p_ids = result.get("all_participant_ids", [])
        if p_ids:
            # v15.3 — bell notification per participant. Uses the war's
            # resolved_at timestamp as ref_id discriminator so notify()'s
            # dedup won't collapse multiple weekly wars together.
            async def _bell_sect_war_resolved():
                from core.notification_engine import notify as _notify
                # Concise summary: count territories won + any going free.
                territories_won = sum(1 for r in results if not r.get("no_contestants"))
                territories_free = sum(1 for r in results if r.get("no_contestants"))
                ts_ref = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                async with get_session_factory()() as session:
                    for pid in p_ids:
                        try:
                            await _notify(
                                session, pid, "sect_war_resolved",
                                title_key="notif_sect_war_resolved_title",
                                body_key="notif_sect_war_resolved_body",
                                payload={"won": territories_won, "free": territories_free},
                                ref_id=f"sect_war:{ts_ref}:resolved",
                                icon="🏆",
                                target_tab="sect",
                                priority=3,
                            )
                        except Exception:
                            logger.exception("notify sect_war_resolved failed pid=%s", pid)
                    await session.commit()
            asyncio.create_task(_bell_sect_war_resolved())

            async def _send_sect_war_results():
                from database.models import Player as _P_
                from core.game_logic import format_number
                async with get_session_factory()() as session:
                    pp_data = (await session.execute(select(_P_.telegram_id, _P_.language).where(_P_.telegram_id.in_(p_ids)))).all()
                sent_swr, failed_swr = 0, 0
                for pid, p_lang in pp_data:
                    lang = normalize_lang(p_lang)
                    lines = [t(lang, "global_sect_war_results_title")]
                    for r in results:
                        if r.get("no_contestants"):
                            lines.append(t(lang, "global_sect_war_territory_free", territory=r['territory_name']))
                        else:
                            lines.append(t(lang, "global_sect_war_territory_won", territory=r['territory_name'], winner=r['winner'], bp=format_number(r.get('winner_bp', 0))))
                    lines.append(t(lang, "global_sect_war_results_footer"))
                    msg = "\n".join(lines)
                    try:
                        await _bot.send_message(chat_id=pid, text=msg, parse_mode="Markdown")
                        sent_swr += 1
                    except Exception:
                        failed_swr += 1
                    await asyncio.sleep(0.05)
                logger.info("📢 Sect war resolve broadcast: %d sent, %d failed, %d total", sent_swr, failed_swr, len(pp_data))
            asyncio.create_task(_send_sect_war_results())


async def sect_war_sweep_job():
    """Recovery net for orphaned Sect Wars (2026-06-13, [jogador] report).

    The resolve is an in-memory "date" job scheduled at war start +1h — any
    bot restart/deploy inside that window loses it FOREVER (and pre-fix the
    job also had the 1s default misfire grace). Evidence from prod: wars of
    2026-05-15→06-12 (ids 11–15) all recorded attacks and never resolved —
    territories stayed with the 2026-05-08 winner ("Wuxia Brasil") for a
    month while real attackers (Origem Absoluta 11.4K on Crystal Lake) got
    nothing. This sweep resolves any active war past its 1h window using the
    SAME resolve+broadcast path; resolve_sect_war row-locks the war, so the
    sweep and the date job can never double-resolve.
    """
    from database.models import SectWarState
    async with get_session_factory()() as session:
        war = (await session.execute(
            select(SectWarState).where(SectWarState.is_active == True)  # noqa: E712
        )).scalar_one_or_none()
        if not war or not war.started_at:
            return
        elapsed = (datetime.now(timezone.utc) - war.started_at).total_seconds()
    if elapsed <= 3600:
        return
    logger.warning(
        "⚔️ Sect War sweep: active war started %s (%.0f min ago) was never "
        "resolved — resolving now with the recorded attacks.",
        war.started_at, elapsed / 60,
    )
    await sect_war_resolve_job()


async def territory_bonus_job():
    from core.sect_engine import distribute_territory_bonus
    logger.info("🌍 Distributing territory bonuses...")
    async with get_session_factory()() as session:
        notifications = await distribute_territory_bonus(session)
        await session.commit()

    if _bot and notifications:
        # Send territory bonus notifications in background
        async def _send_territory_notifications():
            for n in notifications:
                try:
                    async with get_session_factory()() as session:
                        player = (await session.execute(select(Player).where(Player.telegram_id == n["player_id"]))).scalar_one_or_none()
                    lang = player.language or "en" if player else "en"
                    msg = t(lang, "sched_territory_bonus", territory=n['territory_name'], stones=n['stones'])
                    await _bot.send_message(chat_id=n["player_id"], text=msg, parse_mode="Markdown")
                except Exception as e:
                    logger.warning("Failed to send territory bonus to %s: %s", n["player_id"], e)
                await asyncio.sleep(0.05)
        asyncio.create_task(_send_territory_notifications())


async def _send_messages_background(messages: list[tuple[int, str]], label: str = "tick"):
    """Send queued Telegram messages in background without blocking the event loop."""
    if not _bot or not messages:
        return
    sent, failed = 0, 0
    for chat_id, msg_text in messages:
        try:
            await _bot.send_message(chat_id=chat_id, text=msg_text, parse_mode="Markdown")
            sent += 1
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
            try:
                await _bot.send_message(chat_id=chat_id, text=msg_text, parse_mode="Markdown")
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    if sent or failed:
        logger.info("📢 %s notifications: %d sent, %d failed", label, sent, failed)


# Max time a single tick cycle is allowed to run before yielding to next cycle
_TICK_BUDGET_SECONDS = TICK_INTERVAL_SECONDS - 5  # leave 5s headroom


async def cultivation_tick():
    tick_start = datetime.now(timezone.utc)
    now = tick_start
    cutoff_seconds = OFFLINE_CAP_SECONDS
    # Threshold: skip if last_tick_at is within this cycle (with 5s buffer)
    tick_threshold = now - timedelta(seconds=TICK_INTERVAL_SECONDS - 5)
    batch = 0
    players_processed = 0

    # MV-3 — Estados Regionais: densidade de qi por continente (festival =
    # cultivo tick +5% ALI). Prefetch de UMA query por mundo por tick (nunca
    # 1/jogador); gated `estados_regionais` — OFF → {} sem query, e o kwarg
    # default 1.0 mantém process_tick byte-idêntico. Fail-safe: o tick nunca
    # quebra por causa do estado.
    region_qi_mults: dict = {}
    try:
        from core.region_state_engine import estados_on, qi_tick_mult_map
        if estados_on():
            async with get_session_factory()() as session:
                region_qi_mults = await qi_tick_mult_map(session)
    except Exception:
        logger.debug("region qi mult prefetch failed", exc_info=True)
        region_qi_mults = {}

    while True:
        # ── Time budget check: stop if we've used too much time ──
        elapsed_tick = (datetime.now(timezone.utc) - tick_start).total_seconds()
        if elapsed_tick > _TICK_BUDGET_SECONDS:
            logger.warning(
                "cultivation_tick: time budget exhausted (%.1fs > %ds), "
                "processed %d players across %d batches — rest deferred to next tick",
                elapsed_tick, _TICK_BUDGET_SECONDS, players_processed, batch,
            )
            break

        # Collect all notifications to send AFTER DB transactions commit
        pending_messages = []  # list of (chat_id, text)
        pending_broadcasts = []  # list of (key, kwargs)

        # ── Step 1: Load batch of player IDs (short read-only transaction) ──
        try:
            async with get_session_factory()() as session:
                stmt = (
                    select(Player.telegram_id, Player.last_online)
                    .order_by(Player.id)
                    .limit(CULTIVATION_BATCH_SIZE)
                    .offset(batch * CULTIVATION_BATCH_SIZE)
                )
                rows = (await session.execute(stmt)).all()
            if not rows:
                break
        except Exception as e:
            # A batch LOAD failure means this world's DB is unreachable or its
            # schema is missing (e.g. a half-provisioned / broken secondary world
            # whose `players` table does not exist). Higher offsets hit the SAME
            # broken DB, so the old `batch += 1; continue` spun through THOUSANDS
            # of failing batches per tick — one traceback each — until the time
            # budget (2026-06-24 incident: offset climbed past 110k in a single
            # 30s tick). Abort this world's tick instead; the next cycle retries
            # from batch 0. A persistent break logs ~once per throttle window; a
            # transient blip (incl. on `main`) re-reports if it recurs after the
            # window, so main's scheduler errors are never permanently muted.
            _report_world_job_failure("cultivation_tick", current_world_key(), e)
            break

        # ── Step 2: Process each player in its own short transaction ─────────
        for pid, last_online in rows:
            # Yield to event loop between players so handlers can respond
            await asyncio.sleep(0)

            # Time budget check per-player
            elapsed_tick = (datetime.now(timezone.utc) - tick_start).total_seconds()
            if elapsed_tick > _TICK_BUDGET_SECONDS:
                logger.warning(
                    "cultivation_tick: time budget hit mid-batch (%.1fs), "
                    "processed %d players — rest deferred",
                    elapsed_tick, players_processed,
                )
                break

            elapsed = (now - last_online).total_seconds()
            if elapsed > cutoff_seconds:
                continue

            is_online = elapsed < ONLINE_THRESHOLD_SECONDS
            player_msgs = []
            player_bcasts = []

            try:
              async with get_session_factory()() as session:
               try:
                await session.execute(text("SET LOCAL lock_timeout = '3000'"))

                # Lock player row; SKIP LOCKED = instantly skip if locked by another session
                player = (await session.execute(
                    select(Player)
                    .where(
                        Player.telegram_id == pid,
                        or_(
                            Player.last_tick_at == None,
                            Player.last_tick_at < tick_threshold,
                        ),
                    )
                    .with_for_update(skip_locked=True)
                )).scalar_one_or_none()
                if player is None:
                    continue  # Already ticked or locked — skip

                player.last_tick_at = now

                tick_result = await process_tick(
                    player, is_online=is_online, session=session,
                    region_cb_mult=float(region_qi_mults.get(player.current_continent, 1.0) or 1.0),
                )

                from config import DAO_MEDITATION_TYPES as _DAO_TYPES
                is_dao_meditation = (
                    player.is_meditating
                    and player.meditation_type
                    and player.meditation_type in _DAO_TYPES
                )
                if is_dao_meditation and player.realm >= 5:
                    from core.dao_engine import try_grant_fragment
                    from core.alchemy_engine import get_active_buffs as _get_dao_buffs
                    dao_med_info = _DAO_TYPES.get(player.meditation_type, {})
                    frag_mult = dao_med_info.get("dao_fragment_mult", 1.0)
                    _dao_buffs = await _get_dao_buffs(session, player.telegram_id)
                    for _db in _dao_buffs:
                        if _db.buff_type == "dao_fragment_chance":
                            frag_mult *= _db.buff_value
                            break
                    # Faction bonus: Celestial +20% Dao comprehension
                    from core.faction_engine import get_faction_bonuses
                    _fac_bonuses = await get_faction_bonuses(session, player.telegram_id)
                    _dao_fac_bonus = _fac_bonuses.get("dao_bonus", 0)
                    if _dao_fac_bonus > 0:
                        frag_mult *= (1 + _dao_fac_bonus)

                    # Use TOTAL perception (base + equipment + multipliers + pills),
                    # so investing in better gear actually accelerates Dao insights.
                    try:
                        from core.game_logic import calculate_total_stats, get_player_equipment_stats
                        from database.models import PlayerArtifact as _PA
                        _arts = (await session.execute(
                            select(_PA).where(_PA.player_id == player.telegram_id, _PA.is_equipped == True)
                        )).scalars().all()
                        _eq_stats = get_player_equipment_stats(_arts)
                        _stats = calculate_total_stats(player, _eq_stats)
                        _total_perc = _stats.get("perception", player.perception)
                        for _b in _dao_buffs:
                            if _b.buff_type == "perception_boost":
                                _total_perc *= _b.buff_value
                        meditation_perception = int(_total_perc)
                    except Exception:
                        meditation_perception = player.perception

                    dao_result = await try_grant_fragment(session, player.telegram_id, meditation_perception, player.realm, fragment_mult=frag_mult)
                    if dao_result and _bot:
                        lang = player.language or "en"
                        if dao_result["completed"]:
                            frag_msg = t(lang, "sched_dao_complete", emoji=dao_result['law_emoji'], name=dao_result['law_name'])
                            if dao_result["is_eternal"]:
                                from core.achievement_engine import check_achievements
                                dao_ach = await check_achievements(session, player.telegram_id, "dao_completed", 1)
                                if dao_ach:
                                    for ach in dao_ach:
                                        lines = [t(lang, "sched_achievement_unlocked", emoji=ach.emoji, name=ach.name, description=ach.description)]
                                        if ach.title_granted:
                                            lines.append(t(lang, "sched_achievement_title", title=ach.title_granted))
                                        player_msgs.append((player.telegram_id, "\n".join(lines)))
                                from database.models import Player as _P
                                dao_cutoff = now - timedelta(days=7)
                                all_pps = (await session.execute(
                                    select(_P.telegram_id, _P.language)
                                    .where(_P.last_online >= dao_cutoff)
                                )).all()
                                player_display = escape_markdown(player.dao_name or player.display_name or player.username or "???")
                                for uid, p_lang in all_pps:
                                    a_lang = normalize_lang(p_lang)
                                    announcement = t(a_lang, "global_dao_completion", player_name=player_display, law_name=dao_result['law_name'])
                                    player_msgs.append((uid, announcement))
                        else:
                            frag_msg = t(lang, "sched_dao_fragment", emoji=dao_result['law_emoji'], name=dao_result['law_name'], fragments=dao_result['fragments'], total=dao_result['total'])
                        player_msgs.append((player.telegram_id, frag_msg))

                    # 3000 Dao Laws — law discovery during Dao meditation
                    # F-11.5: Celestial Meditation restricts the pool to Heavenly paths.
                    try:
                        from core.dao_laws_engine import try_discover_law
                        heavenly_only = bool(dao_med_info.get("heavenly_only", False))
                        discovery = await try_discover_law(
                            session, player.telegram_id, player.realm,
                            dao_fragment_mult=frag_mult,
                            perception=meditation_perception,
                            heavenly_only=heavenly_only,
                        )
                        if discovery and _bot:
                            lang = player.language or "en"
                            law_name = discovery.get(f"law_name_{lang}") or discovery["law_name"]
                            path_name = discovery.get(f"path_name_{lang}") or discovery["path_name"]
                            cat_name = discovery.get(f"category_name_{lang}") or discovery["category_name"]
                            disc_msg = t(lang, "sched_dao_law_discovered",
                                         rarity_emoji=discovery["rarity_emoji"],
                                         law_name=law_name,
                                         cat_emoji=discovery["category_emoji"],
                                         cat_name=cat_name,
                                         path_emoji=discovery["path_emoji"],
                                         path_name=path_name,
                                         discovered=discovery["path_discovered"],
                                         total=discovery["path_total"])
                            # F-11.5: append essence gain line when a Heavenly Law is discovered
                            if discovery.get("celestial_essence_gained", 0) > 0:
                                disc_msg += "\n" + t(
                                    lang, "sched_celestial_essence_gain",
                                    amount=discovery["celestial_essence_gained"],
                                )
                            player_msgs.append((player.telegram_id, disc_msg))
                            if discovery["tier_up"]:
                                from core.dao_laws_engine import get_tier_info
                                tier_info = get_tier_info(discovery["new_tier"], lang)
                                tier_msg = t(lang, "sched_dao_tier_up",
                                             path_emoji=discovery["path_emoji"],
                                             path_name=path_name,
                                             stars=tier_info["stars"],
                                             tier_name=tier_info["name"],
                                             bonus_pct=int(tier_info["bonus"] * 100))
                                player_msgs.append((player.telegram_id, tier_msg))

                            # v14.3 D-6a — Apex check after a heavenly discovery.
                            # Last law of the 100 fires the achievement here if
                            # all other gates are satisfied.
                            try:
                                from core.celestial_engine import try_grant_apex, APEX_JADE_REWARD
                                apex_grant = await try_grant_apex(session, player)
                                if apex_grant:
                                    p_lang = player.language or "en"
                                    # v14.3 audit: emit BOTH the canonical achievement
                                    # card (sched_achievement_unlocked + title line, same
                                    # framing as realm_reached achievements) AND the
                                    # apex-specific banner explaining /conquistas to
                                    # equip the title and /camara_reflexao to enter the
                                    # chamber. Players were confused with banner-only
                                    # delivery (". ." chat 2026-05-08).
                                    for ach in apex_grant.get("achievements", []):
                                        ach_lines = [t(p_lang, "sched_achievement_unlocked",
                                                       emoji=ach.emoji, name=ach.name,
                                                       description=ach.description)]
                                        if ach.title_granted:
                                            ach_lines.append(t(p_lang, "sched_achievement_title",
                                                               title=ach.title_granted))
                                        player_msgs.append((player.telegram_id, "\n".join(ach_lines)))
                                    apex_msg = t(p_lang, "apex_unlock_banner", jade=APEX_JADE_REWARD)
                                    player_msgs.append((player.telegram_id, apex_msg))
                            except Exception as _ax:
                                logger.warning("Apex grant check failed for %s: %s", player.telegram_id, _ax)
                    except Exception as _e:
                        logger.warning("Dao law discovery error for player %s: %s", player.telegram_id, _e)

                if tick_result.get("meditation_ce", 0) > 0 and _bot:
                    p_lang = player.language or "en"
                    ce_msg = t(p_lang, "core_essence_gain", amount=tick_result["meditation_ce"], total=player.core_essence or 0)
                    player_msgs.append((player.telegram_id, ce_msg))

                if tick_result.get("meditation_ended") and tick_result.get("meditation_hp_recovered", 0) > 0 and _bot:
                    p_lang = player.language or "en"
                    from core.game_logic import format_number as _fmt
                    hp_msg = t(p_lang, "meditation_hp_recovered", hp=_fmt(tick_result["meditation_hp_recovered"]))
                    player_msgs.append((player.telegram_id, hp_msg))

                if tick_result["breakthrough"] and _bot:
                    bt = tick_result["breakthrough"]
                    if not bt.get("tribulation_required"):
                        from core.achievement_engine import check_achievements
                        unlocked = await check_achievements(session, player.telegram_id, "realm_reached", player.realm)
                        if unlocked:
                            p_lang = player.language or "en"
                            for ach in unlocked:
                                lines = [t(p_lang, "sched_achievement_unlocked", emoji=ach.emoji, name=ach.name, description=ach.description)]
                                if ach.title_granted:
                                    lines.append(t(p_lang, "sched_achievement_title", title=ach.title_granted))
                                player_msgs.append((player.telegram_id, "\n".join(lines)))
                        # v14.3 audit: 3rd Apex hook — covers the path where the
                        # player already had 100/100 daos + 3/3 trials but was at
                        # sub_layer 8, then breakthrough'd to sub_layer 9. Without
                        # this hook the achievement would never fire (only the
                        # heavenly-discovery and trial-success paths existed).
                        try:
                            from core.celestial_engine import try_grant_apex, APEX_JADE_REWARD
                            apex_grant = await try_grant_apex(session, player)
                            if apex_grant:
                                p_lang = player.language or "en"
                                for ach in apex_grant.get("achievements", []):
                                    ach_lines = [t(p_lang, "sched_achievement_unlocked",
                                                   emoji=ach.emoji, name=ach.name,
                                                   description=ach.description)]
                                    if ach.title_granted:
                                        ach_lines.append(t(p_lang, "sched_achievement_title",
                                                           title=ach.title_granted))
                                    player_msgs.append((player.telegram_id, "\n".join(ach_lines)))
                                player_msgs.append((player.telegram_id,
                                    t(p_lang, "apex_unlock_banner", jade=APEX_JADE_REWARD)))
                        except Exception as _ax:
                            logger.warning("Apex grant on breakthrough failed for %s: %s",
                                           player.telegram_id, _ax)
                    if bt.get("tribulation_required"):
                        from config import REALM_NAMES
                        target_realm = REALM_NAMES[bt["target_realm"]]
                        p_lang = player.language or "en"
                        msg = t(p_lang, "sched_tribulation_warning", name=escape_markdown(player.dao_name or player.display_name or player.username or "???"), realm=target_realm)
                    elif bt.get("foundation_required"):
                        p_lang = player.language or "en"
                        msg = t(p_lang, "foundation_locked_msg")
                    elif bt.get("core_required"):
                        p_lang = player.language or "en"
                        msg = t(p_lang, "core_locked_msg")
                    elif bt.get("body_tempering_required"):
                        # Rate-limit: only notify once per 24h for this block type
                        if _should_notify_block(player.telegram_id, "body_tempering_required", now):
                            p_lang = player.language or "en"
                            msg = t(p_lang, "tempering_realm8_blocked", current=bt.get("current_level", 0))
                        else:
                            msg = None
                    elif bt.get("celestial_trial_required"):
                        # Rate-limit: only notify once per 24h for this block type
                        if _should_notify_block(player.telegram_id, "celestial_trial_required", now):
                            p_lang = player.language or "en"
                            # Hotfix "A Volta" 2026-07-07 (#6): a key antiga manda
                            # usar /celestial, mas o chat é SEMPRE main — num mundo
                            # secundário a instrução abre o personagem errado.
                            # Fora do main, aponta para o mini-app (🌠 Celestial).
                            key = ("celestial_trial_gate_blocked"
                                   if current_world_key() == "main"
                                   else "celestial_trial_gate_blocked_world")
                            msg = t(
                                p_lang,
                                key,
                                trial=bt.get("trial_num", 1),
                                sub=bt.get("sub_layer", 1),
                            )
                        else:
                            msg = None
                    elif bt.get("cooldown"):
                        msg = None # Silently wait during cooldown
                    elif bt.get("ceremony_required"):
                        # Sprint 8 — the early realm-up paused for the Cerimónia-Semente
                        # (Consolidar/Forçar). Rate-limited so the tick doesn't nag; the
                        # player resolves it in the mini-app or via /cerimonia (Lei §1 —
                        # the path is disclosed, never a silent void).
                        if _should_notify_block(player.telegram_id, "ceremony_required", now):
                            p_lang = player.language or "en"
                            msg = t(p_lang, "bt_ceremony_ready")
                        else:
                            msg = None
                    else:
                        msg = build_breakthrough_message(bt, lang=(player.language or "en"))

                    if msg:
                        player_msgs.append((player.telegram_id, msg))

                    if bt.get("realm_up") and player.realm == 5:
                        p_lang = player.language or "en"
                        dao_unlock_msg = t(p_lang, "sched_dao_unlock")
                        player_msgs.append((player.telegram_id, dao_unlock_msg))

                    # Global realm-up announcement for Nascent Soul (realm 4)
                    if bt.get("realm_up") and player.realm >= 4:
                        from config import REALM_NAMES as _RNAMES
                        _realm_name = _RNAMES[min(player.realm, len(_RNAMES) - 1)]
                        player_bcasts.append((
                            "realm_up_announcement",
                            {
                                "name": escape_markdown(player.dao_name or player.display_name or player.username or "???"),
                                "realm": _realm_name,
                            },
                        ))

                await session.commit()
                players_processed += 1
               except Exception:
                # Explicit rollback to release row locks before connection returns to pool
                try:
                    await session.rollback()
                except Exception:
                    pass
                raise

              # Transaction committed — safe to queue messages
              pending_messages.extend(player_msgs)
              pending_broadcasts.extend(player_bcasts)

            except OSError as e:
                # Connection-level error (DNS failure, network unreachable, etc.)
                # No point retrying other players — DB is unreachable
                logger.warning("cultivation_tick: DB connection error, skipping rest of batch %d: %s", batch, e)
                break
            except Exception as e:
                # Roll back FIRST: a failure that escaped the inner per-player
                # savepoint (or whose inner rollback itself failed) leaves the
                # shared batch session in a 'pending rollback' state. Without
                # this, EVERY subsequent player in the batch cascades into
                # PendingRollbackError (the contagion the admin alerts showed).
                # Idempotent — a no-op if the session is already clean.
                try:
                    await session.rollback()
                except Exception:
                    pass
                logger.error("cultivation_tick: player %s failed: %s", pid, e, exc_info=True)
                # Alert admins via Telegram (rate-limited per player)
                if _bot and ADMIN_USERS:
                    last = _tick_fail_notified.get(pid)
                    if not last or (now - last) > _TICK_FAIL_ALERT_COOLDOWN:
                        _tick_fail_notified[pid] = now
                        err_type = type(e).__name__
                        # 2026-09-15 — O ALERTA TEM DE DIZER A CAUSA.
                        #
                        # Ate' hoje mandava so' `type(e).__name__`.
                        # `DBAPIError` e' o INVOLUCRO generico do SQLAlchemy:
                        # a causa real (deadlock, timeout, violacao, ligacao
                        # cortada) vive em `e.orig` e ficava so' no log.
                        # Chegaram dois destes em dois meses (21/07 e 15/09) e
                        # das duas vezes o alerta nao deu para diagnosticar
                        # nada: foi preciso ir a base a mao para descobrir que
                        # o de 15/09 era transitorio e ja' tinha recuperado.
                        #
                        # E o Markdown e' uma armadilha aqui: a mensagem do
                        # Postgres traz `_` e `*` (nomes de coluna, SQL), o
                        # `send_message` rebenta com "can't parse entities" e
                        # o `except Exception: pass` la' em baixo ENGOLE -- o
                        # alerta desaparecia INTEIRO, que e pior do que nao ter
                        # detalhe nenhum. Por isso a causa vai num bloco de
                        # codigo, com os acentos graves trocados.
                        _orig = getattr(e, "orig", None)
                        _causa = type(_orig).__name__ if _orig is not None else ""
                        _msg = str(_orig if _orig is not None else e)
                        # So' a 1a linha: o SQLAlchemy anexa o SQL inteiro e os
                        # parametros a seguir, e isso nem cabe nem se manda.
                        _msg = _msg.split(chr(10))[0].replace("`", chr(39))[:220]
                        _nl = chr(10)   # quebra REAL. Escrita como literal ela COLAPSA a
                        # caminho deste ficheiro (a armadilha ja documentada
                        # no _sabota_os_nomes.py): ficava a string '\\n'
                        # e o admin lia um \\n literal em vez de uma linha.
                        alert = (
                            "⚠️ *cultivation\\_tick failure*" + _nl
                            + f"Player: `{pid}`" + _nl
                            + f"Error: `{err_type}`"
                            + (f" / `{_causa}`" if _causa else "") + _nl
                            + f"Batch: {batch}" + _nl
                            + "```" + _nl + _msg + _nl + "```"
                        )
                        for admin_id in ADMIN_USERS:
                            try:
                                await _bot.send_message(chat_id=admin_id, text=alert, parse_mode="Markdown")
                            except Exception:
                                pass
                continue

        # ── Send all queued notifications in background (non-blocking) ────────
        if pending_messages:
            asyncio.create_task(_send_messages_background(
                pending_messages, f"tick batch {batch}"
            ))

        if pending_broadcasts:
            from core.announcement_engine import broadcast
            for key, kwargs in pending_broadcasts:
                asyncio.create_task(broadcast(key, **kwargs))

        batch += 1

    # Log tick duration for monitoring
    tick_duration = (datetime.now(timezone.utc) - tick_start).total_seconds()
    if tick_duration > 5:
        logger.warning(
            "cultivation_tick: slow tick — %.1fs, %d players processed",
            tick_duration, players_processed,
        )
    else:
        logger.debug("cultivation_tick: %.1fs, %d players", tick_duration, players_processed)


async def reset_daily_quests():
    logger.info("⏳ Starting daily quests reset...")
    async with get_session_factory()() as session:
        try:
            from core.quest_engine import reset_daily_quests_global
            await reset_daily_quests_global(session)
            await session.commit()
            logger.info("✅ Daily quests reset completed.")
        except Exception as e:
            logger.error(f"❌ Error in reset_daily_quests: {e}")
            await session.rollback()


async def reset_weekly_quests():
    logger.info("⏳ Starting weekly quests reset...")
    async with get_session_factory()() as session:
        try:
            from core.quest_engine import reset_weekly_quests_global
            await reset_weekly_quests_global(session)
            await session.commit()
            logger.info("✅ Weekly quests reset completed.")
        except Exception as e:
            logger.error(f"❌ Error in reset_weekly_quests: {e}")
            await session.rollback()

async def reset_battle_pass_daily():
    logger.info("⏳ Starting daily Battle Pass reset...")
    async with get_session_factory()() as session:
        try:
            await session.execute(update(BattlePass).values(daily_jade_claimed_at=None))
            await session.commit()
            logger.info("✅ Daily Battle Pass reset completed.")
        except Exception as e:
            logger.error(f"❌ Error in reset_battle_pass_daily: {e}")
            await session.rollback()

async def keep_alive_job():
    logger.debug("Scheduler keep-alive job running...")
    # This job simply runs to ensure the scheduler is active and logs its activity.


async def expedition_check_job():
    from core.beast_engine import check_finished_expeditions
    logger.info("🗺️ Checking finished expeditions...")
    async with get_session_factory()() as session:
        notifications = await check_finished_expeditions(session)
        await session.commit()

    if _bot and notifications:
        async def _send_expedition_notifications():
            for notif in notifications:
                try:
                    async with get_session_factory()() as session:
                        player = (await session.execute(select(Player).where(Player.telegram_id == notif["player_id"]))).scalar_one_or_none()
                    lang = player.language or "en" if player else "en"
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            t(lang, "sched_expedition_collect_btn", name=notif['beast_name']),
                            callback_data=f"beast_collect_{notif['beast_id']}",
                        )],
                    ])
                    msg = t(lang, "sched_expedition_done", beast=notif['beast_name'], type=notif['expedition_type'])
                    await _bot.send_message(
                        chat_id=notif["player_id"],
                        text=msg,
                        parse_mode="Markdown",
                        reply_markup=kb,
                    )
                except Exception as e:
                    logger.warning("Failed to send expedition notification to %s: %s", notif["player_id"], e)
                await asyncio.sleep(0.05)
        asyncio.create_task(_send_expedition_notifications())


# v16.4 — World Sect recruiter. A house chooses a cultivator (not vice-versa).
RECRUITER_ENCOUNTER_TTL_HOURS = 72   # encounter expires after 72h (matches karma grace)
RECRUITER_DEDUP_DAYS = 7             # at most one encounter offered per player per week
RECRUITER_MAX_PLAYERS_PER_TICK = 300 # safety cap (57 players today; cheap headroom)


def _affinity_breakdown_line(lang: str, bd: dict) -> str:
    """Pedra 2 — a compact one-line affinity disclosure for the Chamado DM
    ("Caminho +35 · Continente +25 · Karma +10 · Atos +5"). Only non-zero
    components, in display order. Reuses the breakdown the recruiter already
    computed (Lei §1). Returns "" if nothing courts the cultivator yet."""
    comps = (
        ("wsect_bd_path", int(bd.get("path_alignment", 0) or 0)),
        ("wsect_bd_continent", int(bd.get("continent", 0) or 0)),
        ("wsect_bd_karma", int(bd.get("karma_tier", 0) or 0)),
        ("wsect_bd_lineage", int(bd.get("lineage", 0) or 0)),
        ("wsect_bd_actions", int(bd.get("actions", 0) or 0)),
    )
    return " · ".join(f"{t(lang, k)} +{v}" for k, v in comps if v > 0)


async def world_sect_recruiter_tick():
    """v16.4 — hourly: the Elder on the pine tree finds a worthy cultivator.

    For each eligible cultivator (path crystallized, R3+, active in the last
    14 days, not already in an NPC sect), compute affinity for all 9 houses.
    If the top house clears the threshold (75) AND no encounter was offered in
    the last 7 days, spawn a Recruiter encounter: a DB row in
    ``world_sect_recruiter_pending`` + a Telegram DM with accept/decline inline
    buttons + a mini-app inbox notification (canonical surface). One new
    encounter per cultivator per tick (the top-affinity house only).
    """
    from core.affinity_engine import compute_all_affinity_breakdowns, get_affinity_threshold
    from core.world_sects_engine import WORLD_SECT_META, select_call_tone
    from database.models import WorldSectRecruiterPending

    now = datetime.now(timezone.utc)
    threshold = get_affinity_threshold()
    cutoff_active = now - timedelta(days=14)
    cutoff_dedup = now - timedelta(days=RECRUITER_DEDUP_DAYS)
    expires_at = now + timedelta(hours=RECRUITER_ENCOUNTER_TTL_HOURS)

    pending_to_dm = []  # (player_id, lang, sect_id, score, pending_id, emoji, sect_name, tone, bd)
    try:
        async with get_session_factory()() as session:
            from core.notification_engine import notify as _notify
            rows = (await session.execute(
                select(Player.telegram_id, Player.language)
                .where(
                    Player.sect_id.is_(None),
                    Player.path.is_not(None),
                    Player.realm >= 3,
                    # FIX 2026-06-01: use last_online (updated on BOTH chat + the
                    # canonical mini-app surface) not last_active_at (only written
                    # chat-side via _ensure_player). With last_active_at, players
                    # who play exclusively in the mini-app were silently excluded
                    # from recruitment after 14 days. Matches every other job.
                    Player.last_online >= cutoff_active,
                )
                .limit(RECRUITER_MAX_PLAYERS_PER_TICK)
            )).all()

            for pid, lang in rows:
                try:
                    recent = (await session.execute(
                        select(WorldSectRecruiterPending.id).where(
                            WorldSectRecruiterPending.player_id == pid,
                            WorldSectRecruiterPending.created_at >= cutoff_dedup,
                        ).limit(1)
                    )).first()
                    if recent:
                        continue

                    # Pedra 2 — compute the full per-house breakdown ONCE and
                    # derive both the top house AND its component breakdown (so
                    # the Chamado can disclose WHY it courts you — Lei §1).
                    breakdowns = await compute_all_affinity_breakdowns(session, pid)
                    ranked = sorted(
                        ((k, int(v.get("total", 0) or 0)) for k, v in breakdowns.items()),
                        key=lambda kv: kv[1], reverse=True,
                    )
                    if not ranked or ranked[0][1] < threshold:
                        continue
                    sect_id, score = ranked[0][0], int(ranked[0][1])
                    bd = breakdowns.get(sect_id) or {}
                    meta = WORLD_SECT_META.get(sect_id) or {}
                    nlang = normalize_lang(lang or "pt")
                    emoji = meta.get("emoji") or "🏯"
                    sect_name = t(nlang, meta.get("name_key") or "")
                    tone = select_call_tone(sect_id)

                    prow = WorldSectRecruiterPending(
                        player_id=pid, sect_id=sect_id,
                        affinity_score=score, expires_at=expires_at,
                    )
                    session.add(prow)
                    await session.flush()  # populate prow.id

                    try:
                        await _notify(
                            session, pid, "world_sect_recruiter",
                            title_key="wsect_recruiter_notif_title",
                            body_key="wsect_recruiter_notif_body",
                            payload={"sect_id": sect_id, "score": score, "pending_id": prow.id},
                            ref_id=f"wsect:{sect_id}:{now.strftime('%Y%m%d')}",
                            icon=emoji, target_tab="sect", priority=4,
                        )
                    except Exception:
                        logger.debug("recruiter inbox notify failed for player_id=%s", pid, exc_info=True)

                    pending_to_dm.append((pid, nlang, sect_id, score, prow.id, emoji, sect_name, tone, bd))
                except Exception:
                    logger.debug("recruiter eval failed for player_id=%s", pid, exc_info=True)
                    continue

            await session.commit()
    except Exception as e:
        logger.error("world_sect_recruiter_tick failed: %s", e, exc_info=True)
        return

    if not _bot or not pending_to_dm:
        return

    async def _send_recruiter_dms():
        for pid, nlang, sect_id, score, pending_id, emoji, sect_name, tone, bd in pending_to_dm:
            try:
                # Pedra 2 — O Chamado: the house courts you in its own voice
                # (soul-derived tone) + discloses WHY (the affinity breakdown,
                # Lei §1). Falls back to the legacy generic DM if the tone key
                # is somehow missing (t() returns the key → still ships text).
                msg = t(nlang, f"wsect_call_{tone}", emoji=emoji, sect=sect_name, score=score)
                parts = _affinity_breakdown_line(nlang, bd)
                if parts:
                    msg += "\n\n" + t(nlang, "wsect_call_courts", parts=parts)
                kb = InlineKeyboardMarkup([[
                    InlineKeyboardButton(t(nlang, "wsect_recruiter_accept_btn"), callback_data=f"wsect_accept_{pending_id}"),
                    InlineKeyboardButton(t(nlang, "wsect_recruiter_decline_btn"), callback_data=f"wsect_decline_{pending_id}"),
                ]])
                await _safe_send(_bot, pid, msg, parse_mode="Markdown", reply_markup=kb)
            except Exception as e:
                logger.warning("Failed to send recruiter DM to %s: %s", pid, e)
            await asyncio.sleep(0.05)
    asyncio.create_task(_send_recruiter_dms())


async def npc_cultivator_tick():
    """Onda 3 — keep the world populated: echo recently-active players into the
    persistent NPC-cultivator population (anonymized, idempotent per source) and
    top each continent back up to target (lifecycle refill after ascensions).
    Each engine helper owns its own commit; the whole job is best-effort."""
    try:
        async with get_session_factory()() as session:
            from core.npc_cultivator_engine import (
                snapshot_recent_players,
                run_npc_cultivators_bootstrap,
                retire_shadow_echoes,
            )
            snapped = await snapshot_recent_players(session)   # commits internally
            await retire_shadow_echoes(session)                 # commits internally (privacy)
            await run_npc_cultivators_bootstrap(session)        # commits internally (refill)
            logger.info("npc_cultivator_tick: snapshotted %s player echo(es)", snapped)
    except Exception as e:
        logger.error("npc_cultivator_tick failed: %s", e, exc_info=True)


async def heavens_whispers_tick():
    """Onda 3 — the world breathes: synthesize a couple of world-event whispers,
    then deliver one capped, opted-in, daily-deduped whisper to each eligible
    player's inbox (anti-churn, in-app only — no DM). Single commit."""
    try:
        async with get_session_factory()() as session:
            from core.heavens_whispers_engine import generate_world_whispers, deliver_whispers
            created = await generate_world_whispers(session)
            written = await deliver_whispers(session)
            await session.commit()
            logger.info("heavens_whispers_tick: %s new whisper(s), %s delivered", len(created), written)
    except Exception as e:
        logger.error("heavens_whispers_tick failed: %s", e, exc_info=True)


async def bounty_refresh_tick():
    """Onda 4a — refresh the Bounty Board: expire stale contracts and top each
    continent's open pool back up from notorious (dark-karma) NPC cultivators.
    The engine helper owns its commits; the whole job is best-effort."""
    try:
        async with get_session_factory()() as session:
            from core.bounty_engine import refresh_bounties
            stats = await refresh_bounties(session)   # commits internally
            logger.info("bounty_refresh_tick: %s", stats)
    except Exception as e:
        logger.error("bounty_refresh_tick failed: %s", e, exc_info=True)


async def world_pulse_tick():
    """World Pulse Fase 1 — one deterministic world heartbeat. The 9 ancient
    sects each act on a weighted-utility menu biased by their hidden personality
    souls; the Chronicle records every beat; the loud beats fire a Heaven's
    Whisper + post a reactive bounty. Idempotent (per-sect last_pulse_at guard) +
    best-effort; run_world_pulse owns its commit. ZERO balance, wipe-safe."""
    try:
        async with get_session_factory()() as session:
            from core.world_pulse_engine import run_world_pulse
            summary = await run_world_pulse(session)   # commits internally
            logger.info("world_pulse_tick: %s", summary)
            # MV-2 — Tiandao Director pega carona no MESMO pulse (gated
            # `tiandao_director`; OFF → no-op sem queries). Sweep resolve/
            # expira (recovery net, lição sect_war) + talvez nascer 1 evento.
            try:
                from core.tiandao_engine import director_pulse
                dsummary = await director_pulse(session)   # commits internally
                if dsummary is not None:
                    logger.info("tiandao_director: %s", dsummary)
            except Exception:
                logger.exception("tiandao director pulse failed")
            # MV-3 — Estados Regionais sincronizam APÓS o Director (eventos são
            # a causa, estados o efeito persistente; o decay vive no MESMO
            # passo, lição sect_war). Gated `estados_regionais`; OFF → no-op
            # sem queries. Commit próprio; falha nunca derruba o pulse.
            try:
                from core.region_state_engine import sync_region_states
                rsummary = await sync_region_states(session)   # commits internally
                if rsummary is not None:
                    logger.info("region_states: %s", rsummary)
            except Exception:
                logger.exception("region states sync failed")
            # MV-6 — Reputação (decay semanal rumo a zero, âncora por row —
            # mesma disciplina do decay do MV-3) + O RIVAL (kill-switch
            # honesto + a VOLTA com taunt). Gated `reputacao_rival`; OFF →
            # no-op sem queries. Commits próprios; falha nunca derruba o pulse.
            try:
                from core.reputation_engine import decay_region_rep, rival_pulse
                repsummary = await decay_region_rep(session)   # commits internally
                if repsummary is not None:
                    logger.info("region_rep_decay: %s", repsummary)
                rvsummary = await rival_pulse(session)         # commits internally
                if rvsummary is not None:
                    logger.info("rival_pulse: %s", rvsummary)
            except Exception:
                logger.exception("reputation/rival pulse failed")
            # MV-7 — Relatório do Mercado Imperial 📜 (passo 5): snapshot dos
            # últimos 7d por continente em region_states.payload (MERGE — o
            # sync do MV-3 preserva). Gated `profissoes`; OFF → no-op sem
            # queries. Commit próprio; falha nunca derruba o pulse.
            try:
                from core.profession_engine import generate_market_reports
                mrsummary = await generate_market_reports(session)   # commits internally
                if mrsummary is not None:
                    logger.info("market_report: %s", mrsummary)
            except Exception:
                logger.exception("market report pulse failed")
            # MV-8 — O JIĀNGHÚ 江湖 (passo 6, o ÚLTIMO): os npc_cultivators
            # deixam de ser estátuas e passam a QUERER coisas. Depois do
            # relatório de mercado de propósito — o Quadro lê o mundo já
            # sincronizado deste batimento (eventos do Director, estados do
            # MV-3, gruta do TEC-4), nunca a foto do batimento anterior.
            # Gated `jianghu`; OFF → no-op sem UMA query. Commit próprio;
            # falha nunca derruba o pulse. Único passo O(N) do batimento —
            # daí o `ms` no log (o pulse não tinha instrumentação nenhuma).
            try:
                from core.jianghu_engine import jianghu_pulse
                jhsummary = await jianghu_pulse(session)   # commits internally
                if jhsummary is not None:
                    logger.info("jianghu: %s", jhsummary)
            except Exception:
                logger.exception("jianghu pulse failed")
            # MV-9 — AS CINCO CIDADES 城 (passo 7, o último): se o encargo de
            # uma cidade virou desde o batimento anterior, a Crônica anuncia —
            # e a latência de leitura do MV-8 faz a notícia demorar 6-12h a
            # chegar a quem está longe. Vem DEPOIS do jiānghú de propósito: o
            # anúncio lê o mundo já sincronizado deste batimento (estado
            # regional do MV-3, evento do Céu do MV-2, marcha do MV-8). Gated
            # `cidades`; OFF → no-op sem UMA query. Zero estado: o "anterior" é
            # derivado, não guardado. Commit próprio; falha nunca derruba o
            # pulse.
            try:
                from core.city_engine import pulse_cities
                cidsummary = await pulse_cities(session)
                if cidsummary is not None:
                    await session.commit()
                    logger.info("cidades: %s", cidsummary)
            except Exception:
                logger.exception("cidades pulse failed")
            # MV-11 天时 — O TEMPO DO CÉU (passo 8, o último): se o céu virou
            # desde o batimento anterior, a Crônica anuncia — UMA linha, e só
            # quando vira. Orçamento medido: main escreve 18-36 linhas/dia e s2
            # 23-53; o céu vira 2×/dia ⇒ +2 linhas/dia.
            # ⚠️ O céu NÃO depende deste passo para existir: ele é derivado do
            # relógio e já mordeu a tribulação e já apareceu na praça antes de
            # qualquer pulse correr. Este passo só escreve a NOTÍCIA. Se o
            # pulse nunca mais correr (ou se o drift de boot o empurrar), o céu
            # continua exato — ao contrário do MV-3, que precisa do batimento
            # para o estado sequer mudar. Gated `tempo_do_ceu`; OFF → no-op sem
            # UMA query. Commit próprio (emit_chronicle só faz flush); falha
            # nunca derruba o pulse.
            try:
                from core.tianshi_engine import pulse_sky
                tshsummary = await pulse_sky(session)
                if tshsummary is not None:
                    await session.commit()
                    logger.info("tempo_do_ceu: %s", tshsummary)
            except Exception:
                logger.exception("tianshi pulse failed")
    except Exception as e:
        logger.error("world_pulse_tick failed: %s", e, exc_info=True)


async def world_boss_spawn_job():
    from core.boss_engine import spawn_bosses, get_player_tier, TIER_EMOJIS
    logger.info("👹 Attempting to spawn World Bosses (multi-tier)...")
    async with get_session_factory()() as session:
        from handlers.events import get_event_multipliers
        event_mults = await get_event_multipliers(session)
        hp_mult = event_mults.get("boss_hp_mult", 1.0)
        bosses = await spawn_bosses(session, hp_mult=hp_mult)
        await session.commit()

    if not bosses:
        logger.info("👹 Boss spawn skipped — all tiers already active or no players")
        return

    boss_by_tier = {b.tier: b for b in bosses}
    tier_names_log = ", ".join(f"{b.tier}={b.name}" for b in bosses)
    logger.info("👹 World Bosses spawned: %s", tier_names_log)

    if _bot:
        # Send boss spawn notifications in background to not block event loop
        async def _send_boss_spawn_notifications():
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            async with get_session_factory()() as session:
                all_pps = (await session.execute(
                    select(Player.telegram_id, Player.language, Player.realm)
                    .where(Player.last_online >= cutoff)
                )).all()

            sent, failed = 0, 0
            for pid, p_lang, p_realm in all_pps:
                lang = normalize_lang(p_lang)
                player_tier = get_player_tier(p_realm)
                boss = boss_by_tier.get(player_tier)
                if not boss:
                    if bosses:
                        boss = bosses[0]
                    else:
                        continue
                tier_emoji = TIER_EMOJIS.get(boss.tier, "👹")
                tier_label = t(lang, f"boss_tier_{boss.tier}")
                msg = t(lang, "global_boss_spawn_tier",
                        tier_emoji=tier_emoji, tier=tier_label,
                        emoji=boss.emoji, name=boss.name, hp=f"{boss.hp:,}")
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"👹 {boss.name}", callback_data="cmd_boss")]
                ])
                try:
                    await _bot.send_message(chat_id=pid, text=msg, parse_mode="Markdown", reply_markup=kb)
                    sent += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.05)
            logger.info("📢 Boss spawn broadcast: %d sent, %d failed, %d total", sent, failed, len(all_pps))
        asyncio.create_task(_send_boss_spawn_notifications())


async def world_boss_check_job():
    """Safety net: check all active bosses with HP <= 0 and distribute rewards."""
    from core.boss_engine import get_all_active_bosses, distribute_rewards
    all_notifications = []
    async with get_session_factory()() as session:
        active_bosses = await get_all_active_bosses(session)
        for boss in active_bosses:
            if boss.current_hp > 0:
                continue
            # Boss HP is 0 but still flagged active
            boss.is_active = False
            if not boss.ended_at:
                boss.ended_at = datetime.now(timezone.utc)

            if boss.rewards_given:
                continue

            from handlers.events import get_event_multipliers
            event_mults = await get_event_multipliers(session)
            loot_mult = event_mults.get("boss_loot_mult", 1.0)

            notifications = await distribute_rewards(session, boss, loot_mult=loot_mult)
            all_notifications.extend(notifications)
        await session.commit()

    if _bot and all_notifications:
        await _send_boss_reward_notifications(all_notifications, "sched_boss_reward")


async def world_boss_expire_job():
    from core.boss_engine import expire_bosses, distribute_rewards
    all_notifications = []
    async with get_session_factory()() as session:
        expired = await expire_bosses(session)
        if not expired:
            return

        for boss in expired:
            if boss.rewards_given:
                continue

            logger.info("⏳ World Boss '%s' (%s) expired — distributing rewards...", boss.name, boss.tier)
            from handlers.events import get_event_multipliers
            event_mults = await get_event_multipliers(session)
            loot_mult = event_mults.get("boss_loot_mult", 1.0)
            notifications = await distribute_rewards(session, boss, loot_mult=loot_mult)
            all_notifications.extend(notifications)
        await session.commit()

    if _bot and all_notifications:
        await _send_boss_reward_notifications(all_notifications, "sched_boss_expire")


async def _send_boss_reward_notifications(notifications: list[dict], key_prefix: str):
    """Send reward DMs to all participants. key_prefix is 'sched_boss_reward' or 'sched_boss_expire'."""
    import asyncio
    for notif in notifications:
        try:
            reward_text = "\n".join(f"  • {r}" for r in notif["rewards"])
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            async with get_session_factory()() as session:
                player = (await session.execute(select(Player).where(Player.telegram_id == notif["player_id"]))).scalar_one_or_none()
            lang = player.language or "en" if player else "en"
            tier_label = t(lang, f"boss_tier_{notif.get('boss_tier', 'mortal')}")
            if notif["rank"] <= 3:
                medal = medals[notif["rank"]]
                msg = t(lang, f"{key_prefix}_top3", medal=medal, rank=notif['rank'], damage=f"{notif['damage']:,}", rewards=reward_text, tier=tier_label)
            elif notif["is_top"]:
                msg = t(lang, f"{key_prefix}_top10", rank=notif['rank'], damage=f"{notif['damage']:,}", rewards=reward_text, tier=tier_label)
            else:
                msg = t(lang, f"{key_prefix}_participant", damage=f"{notif['damage']:,}", rewards=reward_text, tier=tier_label)
            await _safe_send(_bot, notif["player_id"], msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning("Failed to send boss reward to %s: %s", notif["player_id"], e)
        await asyncio.sleep(0.05)


async def notifications_pack_tick():
    """v14.5 — runs the consolidated Notifications Pack job (N-10 + Q-2/3/4)."""
    if _bot is None:
        return
    try:
        from core.notifications_engine import notifications_pack_job
        await notifications_pack_job(_bot)
    except Exception as e:
        logger.error("notifications_pack_tick failed: %s", e, exc_info=True)


async def meditation_sweep():
    """v15.1.5 hotfix — finalize stale meditations for OFFLINE players.

    Main `cultivation_tick` skips players whose `last_online` is older
    than OFFLINE_CAP_SECONDS, so meditations started just before going
    offline never auto-finalize there. Without this sweep, the player
    returns days later, opens the mini-app, and sees "Cancel meditation"
    still on screen even though the timer ran out long ago.

    v15.1.5-hf3 — defensive tuning:
      • LIMIT 100 per sweep (was 500). Smaller batch = shorter lock window
        = less contention with handler transactions on Player rows.
      • lock_timeout 1s (Postgres SET LOCAL). If another transaction holds
        a row we couldn't SKIP_LOCKED, fail fast instead of joining the
        deadlock dance.
      • One transaction per batch (no per-row commit) — atomic finalize +
        notify, but the small batch keeps the transaction short.
    """
    try:
        from sqlalchemy import select as _select, text as _text
        from core.game_logic import try_finalize_meditation
        from core.notification_engine import notify as _notify

        now = datetime.now(timezone.utc)
        finalized = 0
        async with get_session_factory()() as session:
            try:
                await session.execute(_text("SET LOCAL lock_timeout = '1000'"))
            except Exception:
                logger.warning("meditation_sweep: SET LOCAL lock_timeout failed (non-fatal)")
            rows = (await session.execute(
                _select(Player).where(
                    Player.is_meditating == True,  # noqa: E712
                    Player.meditation_end.is_not(None),
                    Player.meditation_end < now,
                ).with_for_update(skip_locked=True).limit(100)
            )).scalars().all()
            for player in rows:
                med_fin = try_finalize_meditation(player)
                if med_fin is None:
                    continue
                finalized += 1
                # SEC (2026-06-01): credit the 'cultivate' daily quest on genuine
                # completion (mirror of the mini-app poll finalize) so a player
                # whose session ends while away still gets the progress.
                try:
                    from config import MEDITATION_TYPES, DAO_MEDITATION_TYPES
                    from core.quest_engine import track_quest as _track_quest
                    _et = med_fin.get("ended_type")
                    _mi = MEDITATION_TYPES.get(_et) or DAO_MEDITATION_TYPES.get(_et) or {}
                    _dur = int(_mi.get("duration_minutes", 0))
                    if _dur > 0:
                        # Hotfix 2026-07-21b — SAVEPOINT no crédito (mesma
                        # contenção do tick em process_tick): sem ele o UPDATE
                        # do progresso flusha no commit do batch, FORA deste
                        # try, e um erro de DB envenenaria o sweep inteiro.
                        async with session.begin_nested():
                            await _track_quest(session, player.telegram_id, "cultivate", _dur)
                        # 内功 (report do [jogador] 2026-08-11): quem finaliza credita —
                        # também o sweep, para quem fechou o Telegram a meditar.
                        from core.technique_engine import credit_passive_mastery
                        await credit_passive_mastery(session, player.telegram_id, _dur)
                except Exception:
                    logger.exception("cultivate quest credit on scheduler finalize failed")
                try:
                    await _notify(
                        session, player.telegram_id, "meditation_ended",
                        title_key="notif_meditation_ended_title",
                        body_key="notif_meditation_ended_body",
                        payload={
                            "type": med_fin.get("ended_type") or "",
                            "hp_recovered": int(med_fin.get("hp_recovered") or 0),
                        },
                        # Cycle-aware ref_id — minute granularity so a player
                        # whose sweep notify lands in two sequential sweeps
                        # for some pathological reason still dedups cleanly.
                        ref_id=f"med:{player.telegram_id}:{now.strftime('%Y%m%d%H%M')}",
                        icon="🧘",
                        target_tab="cultivation",
                        priority=2,
                    )
                except Exception:
                    logger.exception("meditation_sweep notify failed user=%s", player.telegram_id)
            await session.commit()
        if finalized:
            logger.info("meditation_sweep: finalized=%d", finalized)
    except Exception as e:
        logger.error("meditation_sweep failed: %s", e, exc_info=True)


async def arena_queue_sweep():
    """v15.1.5 — Arena ELO queue maintenance + chat-side DM dispatcher.

    Runs every 60s. Does three things in one short transaction:
      1. `check_expirations` — flip any overdue 'waiting' row to 'expired'.
      2. `try_match` — opportunistic pairing for rows the per-request
         sweep missed (e.g. two players joined into different workers).
      3. DM dispatcher — for chat-originated rows (`chat_id IS NOT NULL`):
            - status='matched' → DM "open mini-app, your duel is live"
            - status='expired' → DM "queue expired, retry"
         After delivering the DM we NULL out chat_id so we don't re-DM on
         the next sweep (the row stays for audit but won't trigger again).
    """
    try:
        from sqlalchemy import select as _select, or_ as _or
        from database.models import ArenaQueue, Player
        from core.arena_engine import check_expirations, try_match
        from core.i18n import t

        expired_count = 0
        matches = 0
        dispatches: list[tuple[int, int, str, str]] = []  # (chat_id, player_id, kind, body_key)
        opponent_payloads: dict[int, str] = {}            # chat_id → opp dao_name

        async with get_session_factory()() as session:
            expired_count = await check_expirations(session)
            spawned = await try_match(session)
            while spawned is not None:
                matches += 1
                spawned = await try_match(session)

            # BUGFIX 2026-06-02 (CaosPrimal arena-ELO report) — settle safety-net.
            # The arena duel settle fires from the `combat/duel_state` poll; if both
            # players close the duel modal, no poll runs and the finished duel stays
            # unsettled (ELO never updates, the 'matched' rows never flip to
            # 'completed'). Sweep terminal duels still linked to 'matched' rows and
            # settle them here. apply_post_duel_effects is idempotent (HP-drain
            # marker + settle status gates), so this is safe alongside live polls.
            from database.models import DuelSession as _DS
            from core.duel_engine import apply_post_duel_effects as _settle_duel
            pending_duel_ids = (await session.execute(
                _select(ArenaQueue.duel_id).where(
                    ArenaQueue.status == "matched",
                    ArenaQueue.duel_id.is_not(None),
                ).distinct()
            )).scalars().all()
            for _did in pending_duel_ids:
                _duel = (await session.execute(
                    _select(_DS).where(_DS.id == _did).with_for_update()
                )).scalar_one_or_none()
                if _duel is not None and _duel.state in ("finished", "forfeited"):
                    try:
                        await _settle_duel(session, _duel)
                    except Exception:
                        logger.exception("arena sweep settle failed duel=%s", _did)

            # ── 鎖 UM varredor para TODAS as familias PvE (2026-09-04) ─────
            # Antes desta data havia TRES varredores, um por fonte que se
            # queixou (exploration, dungeon_boss, jianghu_ambush) — e o codigo
            # cria DEZ fontes. As sete restantes nao tinham nenhum, incluindo a
            # MAIOR do jogo (`arena_npc_fallback`, 1.352 lutas/30d) e o proprio
            # DEFAULT de `start_duel_pve` (`npc_hunt`).
            #
            # MEDIDO a 2026-09-03: 27 duelos expirados a prender 13 jogadores, o
            # mais antigo ha' 103 dias. O varredor unico percorre `PVE_SOURCES` e
            # faz as duas coisas que faltavam: DESTRANCA (leva ate' um estado
            # terminal, nao so' ate' a' ronda seguinte) e PAGA (liquida o que
            # ainda deve loot/carimbo/quest). Idempotente pelo `pve_settled`;
            # nunca toca numa luta dentro do prazo; nunca apaga uma linha.
            try:
                from core.duel_engine import sweep_orphan_pve_duels
                await sweep_orphan_pve_duels(session)
            except Exception:
                logger.exception("sweep PvE (todas as familias) falhou")


            # DM dispatcher — only chat-originated rows.
            rows = (await session.execute(
                _select(ArenaQueue).where(
                    ArenaQueue.chat_id.is_not(None),
                    ArenaQueue.status.in_(("matched", "expired")),
                ).with_for_update(skip_locked=True)
            )).scalars().all()

            for row in rows:
                pl = (await session.execute(
                    _select(Player).where(Player.telegram_id == row.player_id)
                )).scalar_one_or_none()
                lang = normalize_lang(pl.language if pl else None)
                opp_name = "?"
                if row.status == "matched" and row.duel_id is not None:
                    from database.models import DuelSession
                    duel = (await session.execute(
                        _select(DuelSession).where(DuelSession.id == row.duel_id)
                    )).scalar_one_or_none()
                    is_npc_fallback = False
                    if duel is not None:
                        is_npc_fallback = (
                            duel.defender_id is None
                            and (duel.pve_source or "") == "arena_npc_fallback"
                        )
                        opp_fighter = (
                            duel.fighter_b if duel.attacker_id == row.player_id
                            else duel.fighter_a
                        )
                        if isinstance(opp_fighter, dict):
                            opp_name = (
                                opp_fighter.get("dao_name")
                                or opp_fighter.get("name")
                                or "?"
                            )
                    msg_key = "arena_dm_matched_npc" if is_npc_fallback else "arena_dm_matched"
                    msg = t(lang, msg_key, opponent=escape_markdown(opp_name))
                else:
                    msg = t(lang, "arena_dm_expired")
                dispatches.append((row.chat_id, row.player_id, row.status, msg))
                # Mark dispatched — chat_id NULL prevents re-DM next sweep.
                row.chat_id = None
                row.message_id = None

            await session.commit()

        if _bot and dispatches:
            for chat_id, _pid, _kind, body_text in dispatches:
                try:
                    await _safe_send(_bot, chat_id, body_text, parse_mode="Markdown")
                except Exception:
                    logger.warning("arena_queue_sweep DM failed for chat=%s", chat_id)
                await asyncio.sleep(0.05)

        if expired_count or matches or dispatches:
            logger.info(
                "arena_queue_sweep: expired=%d matched=%d dispatched=%d",
                expired_count, matches, len(dispatches),
            )
    except Exception as e:
        logger.error("arena_queue_sweep failed: %s", e, exc_info=True)


async def celestial_events_check_job():
    """Expire celestial events that have passed their expires_at time and broadcast the end."""
    from database.models import CelestialEvent
    now = datetime.now(timezone.utc)

    expired_events = []
    async with get_session_factory()() as session:
        stmt = select(CelestialEvent).where(
            CelestialEvent.is_active == True,
            CelestialEvent.expires_at <= now,
        )
        events = (await session.execute(stmt)).scalars().all()
        for ev in events:
            ev.is_active = False
            expired_events.append({"name": ev.name, "emoji": ev.emoji})
            logger.info("🌌 Celestial event '%s' expired", ev.name)
        if events:
            await session.commit()

    if _bot and expired_events:
        async def _send_event_end_broadcast():
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            async with get_session_factory()() as session:
                all_pps = (await session.execute(
                    select(Player.telegram_id, Player.language)
                    .where(Player.last_online >= cutoff)
                )).all()

            sent, failed = 0, 0
            for pid, p_lang in all_pps:
                lang = normalize_lang(p_lang)
                for ev_info in expired_events:
                    msg = t(lang, "event_ended_broadcast", emoji=ev_info["emoji"], name=ev_info["name"])
                    try:
                        await _bot.send_message(chat_id=pid, text=msg, parse_mode="Markdown")
                        sent += 1
                    except Exception:
                        failed += 1
                await asyncio.sleep(0.05)
            logger.info("📢 Celestial event end broadcast: %d sent, %d failed, %d total", sent, failed, len(all_pps))
        asyncio.create_task(_send_event_end_broadcast())
