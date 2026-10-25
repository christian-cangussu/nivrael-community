import logging
import sys
import asyncio

# Force unbuffered output BEFORE anything else (critical for container logs)
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, "reconfigure") else None

# Install global crash catchers (signal handlers, excepthooks, etc.)
import resource_monitor

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, TypeHandler, filters, ContextTypes

from config import BOT_TOKEN, WEBHOOK_URL, WEBHOOK_PATH, PORT, WEBHOOK_SECRET, ADMIN_USERS
from database.db import init_db
from core.scheduler import init_scheduler
from handlers.start import (
    start_command, help_command, nav_router, feedback_menu_callback,
    onboard_lang_callback, onboard_enter_qiankun_callback,
    onboard_confirm_name_callback, process_dao_name_input,
)
from handlers.moderation import setup_moderation_handlers
from handlers.cultivation import (
    status_command,
    cultivar_command,
    corpo_command,
    horta_command,
    cerimonia_command,
    guia_command,
    meditar_command,
    ranking_command,
    idioma_command,
    notif_command,
    notif_toggle_callback,
    config_command,
    button_router,
)
from handlers.alchemy import (
    alquimia_command,
    craftar_command,
    ervas_command,
    pilulas_command,
    alchemy_button_router,
)
from handlers.artifacts import (
    artifacts_command,
    artifact_button_router,
)
from handlers.inventory import (
    inventory_command,
    inventory_button_router,
)
from handlers.market import (
    market_command,
    market_button_router,
    trade_command,
    sell_wizard,
    process_price_input,
    process_qty_input,
    process_bid_input,
    process_trade_stones_input,
    process_trd_qty_input,
    process_trade_daoname_input,
)
from handlers.tribulation import (
    tribulacao_command,
    historico_tribulacao,
    trib_callback_handler
)
from handlers.sect import (
    seita_menu,
    criarseita_command,
    doarseita_command,
    ranking_sects_command,
    entrarseita_command,
    sairseita_command,
    world_sect_command,
    whispers_command,
    cronica_command,
    praca_command,
    viajar_command,
    travel_button_router,
    rival_button_router,
    jianghu_button_router,
    caravan_button_router,
    explorar_command,
    explore_button_router,
    caverna_command,
    formacoes_command,
    cavern_button_router,
    world_sect_button_router,
    promotemembro_command,
    expulmembro_command,
    sect_buildings_menu,
    sect_upgrade_callback,
    loja_seita_command,
    sect_create_init_callback,
    process_sect_name_input,
    sect_vault_menu,
    sect_donate_init_callback,
    process_sect_donation_input,
    sect_edit_desc_callback,
    process_sect_desc_input,
    sect_war_attack_callback,
    admin_startwar_command,
    admin_resolvewar_command,
    sect_bulletin_callback,
    sect_bulletin_write_callback,
    process_sect_bulletin_input,
    sect_group_link_callback,
    sect_group_link_set_callback,
    process_sect_group_link_input,
    # v14.2 D-3 — Sect Leader patch.
    decreto_supremo_command,
    passar_tocha_command,
    sect_torch_accept_callback,
    sect_torch_refuse_callback,
    # v14.2 D-3 discoverability: in-menu wizard handlers.
    sect_decree_init_callback,
    process_sect_decree_input,
    sect_torch_menu_callback,
    sect_torch_pick_callback,
    sect_torch_fire_callback,
)
from handlers.combat import (
    combat_command,
    desafiar_command,
    combat_button_router,
    process_wager_input,
)
from handlers.quests import (
    missoes_command,
    quests_button_router,
    storylet_button_router,
)
from handlers.profession import (
    oficio_command,
    profession_button_router,
)
from handlers.library import (
    biblioteca_command,
    library_button_router,
)
from handlers.scrolls import (
    pergaminhos_command,
    scroll_button_router,
)
from handlers.forbidden import (
    coracao_command,
    forbidden_button_router,
)
from handlers.beasts import (
    bestiario_command,
    beasts_button_router,
)
from handlers.dao import (
    dao_command,
    dao_button_router,
)
from handlers.world_boss import (
    boss_command,
    boss_button_router,
)
from handlers.dungeons import (
    dungeons_command,
    dungeon_button_router,
)
from handlers.achievements import (
    conquistas_command,
    achievements_button_router,
)
from handlers.events import (
    events_command,
    events_button_router,
)
from handlers.partner import (
    partner_menu,
    partner_button_router,
    process_partner_proposal_input,
)
from handlers.prestige import (
    renascer_command,
    prestige_command,
    loja_prestige_command,
    prestige_button_router,
)
from handlers.faction import (
    faction_command,
    faction_button_router,
)
from handlers.celestial import (
    celestial_command,
    celestial_button_router,
    # v14.3 D-6b — Apex Reflection Chamber.
    camara_reflexao_command,
)
from handlers.foundation import (
    recomeco_command,
    quebrar_fundacao_command,
    foundation_button_router,
)
from handlers.shop import setup_shop_handlers
from handlers.gacha import setup_gacha_handlers
from handlers.admin_monetization import setup_admin_monetization_handlers
from handlers.miniapp import miniapp_command
from core.utils import safe_handler, rate_limit
from database.db import get_session_factory

# ─── Logging setup: DEBUG for our code, WARNING for noisy libs ────────────────
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.DEBUG,
    stream=sys.stderr,  # Ensure logs go to stderr (Coolify captures this)
    force=True,
)
# Silence noisy third-party loggers
for _noisy in ("httpx", "httpcore", "hpack", "telegram.ext", "apscheduler", "asyncio", "sqlalchemy.engine"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
# Keep telegram errors visible
logging.getLogger("telegram.error").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)
resource_monitor.log_startup_info()


# Each tuple: (flag name, i18n key). First run after deploy sends anything not yet in
# applied_migrations. Append new patches to the end — old ones will be skipped.
_PENDING_DEPLOY_ANNOUNCEMENTS = [
    ("announce_celestial_v1", "announce_celestial_v1"),
    ("announce_patch_2026_04_24", "announce_patch_2026_04_24"),
    ("announce_heart_demon_tutorial_2026_04_24", "announce_heart_demon_tutorial"),
    ("announce_celestial_v2_2026_04_24", "announce_celestial_v2"),
    # v13 HIGH-priority sprint — auto-broadcast on first boot after deploy in
    # each player's preferred language (pt / en / es).
    ("announce_v13_high_2026_04_30", "announce_v13_high"),
    # Inventory pagination fix (RF report 2026-04-30) — auto-broadcast on
    # next deploy. Same i18n mechanism: pt / en / es per player language.
    ("announce_inv_pagination_fix_2026_04_30", "announce_inv_pagination_fix"),
    # v13 MEDIUM-priority sprint (M-6 → M-12) — broadcast in each player's
    # preferred language on the next deploy after Coolify auto-deploys.
    ("announce_v13_medium_2026_04_30", "announce_v13_medium"),
    # v14 audit (player-chat triage) — pet evolution, heavenly pill,
    # heart demon, market cancel, D7 login pack, beasts ordering. PT/EN/ES.
    ("announce_v14_2026_05_11", "announce_v14_fixes"),
    # v14.1 + v14.2 combined deploy: Qi-regen pills suite, body tempering rebirth fix,
    # celestial essence sources hint, sect master bonuses + /decreto_supremo,
    # /passar_tocha ritual, inventory misc actions. PT/EN/ES.
    ("announce_v14_1_2_2026_05_13", "announce_v14_1_2_fixes"),
    # v14.3 deploy: Apex achievement + Reflection Chamber, Qi-regen pill display
    # fix, Gerir Técnicas restored, T4+ alchemy locked disclosure, pagination
    # first/last jump, breakthrough ETA cap, full buff label coverage. PT/EN/ES.
    # NOTE: flag bumped to "_v2" because the original `announce_v14_3_2026_05_14`
    # was burned in a prior boot when the Markdown parse failed (silent BadRequest
    # on /camara_reflexao underscores) and the flag was inserted preemptively.
    # The function below now (a) escapes Markdown failures with a plain-text
    # retry, (b) only burns the flag AFTER a successful send loop. Bumping the
    # flag forces the broadcast to re-fire once on next start.
    ("announce_v14_3_2026_05_14_v2", "release_v14_3_announcement"),
    # v14.3 hotfix wave (2026-05-14 evening): owner-driven micro-update covering
    # bugs reported by [jogador] (T1 recipes locked), . (3000 Daos pace fatigue),
    # [jogador] (Boundless Evasion dao gate disclosure), [jogadores]/. (qi-regen
    # display), plus a roadmap teaser for v14.4 Foundation system + Imperial Launch.
    # In-character voice as Saint addressing the community directly.
    ("announce_v14_3_hotfix_2026_05_14", "release_v14_3_hf_announcement"),
    # v14.6 + HF deploy (2026-05-17): Q-13 Tribulation preview (chance/fases/
    # custo de falha/talismãs antes de Iniciar), pílulas Perfect+/Divine/Heavenly
    # mostram magnitude REAL escalada por qualidade no detail card (resolve
    # [jogadores]), HF crash do `/recomeço` corrigido (use `/recomeco`
    # sem ç), supressão de spam de admin DM em connection-closed mid-handler.
    # PT/EN/ES.
    ("announce_v14_6_2026_05_17", "release_v14_6_announcement"),
]


async def _maybe_send_deploy_announcement(bot):
    """One-time i18n broadcast after deploy. Uses applied_migrations table as flag.

    v14.3 — flag is inserted AFTER successful send (was: before, which caused
    silent failures to permanently block re-fire). Markdown send is wrapped
    with a plain-text fallback so a single bad character (e.g. odd `_` count
    in a command name) does not silently kill the broadcast.
    """
    import asyncio as _aio
    from telegram.error import BadRequest
    await _aio.sleep(10)  # wait for DB to be ready

    from database.db import get_session_factory
    from database.models import Player
    from sqlalchemy import text, select
    from core.i18n import t
    from core.utils import normalize_lang
    from datetime import datetime, timezone, timedelta

    try:
        # Figure out which announcements still need to be sent.
        pending: list[tuple[str, str]] = []
        async with get_session_factory()() as session:
            for flag, key in _PENDING_DEPLOY_ANNOUNCEMENTS:
                row = (await session.execute(
                    text("SELECT 1 FROM applied_migrations WHERE filename = :f"),
                    {"f": flag},
                )).scalar_one_or_none()
                if not row:
                    pending.append((flag, key))

        if not pending:
            return

        # Fetch active players with their language
        cutoff = datetime.now(timezone.utc) - timedelta(days=14)
        async with get_session_factory()() as session:
            players = (await session.execute(
                select(Player.telegram_id, Player.language).where(Player.last_online >= cutoff)
            )).all()

        for flag, key in pending:
            sent, failed = 0, 0
            for pid, lang in players:
                lang = normalize_lang(lang)
                text_msg = t(lang, key)
                # Try Markdown first; on parse error retry plain-text so a
                # single broken entity (e.g. /camara_reflexao with an unpaired
                # underscore) does not silently consume the broadcast.
                try:
                    await bot.send_message(chat_id=pid, text=text_msg, parse_mode="Markdown")
                    sent += 1
                except BadRequest as e:
                    msg = str(e).lower()
                    if "parse" in msg or "entity" in msg or "entities" in msg:
                        try:
                            await bot.send_message(chat_id=pid, text=text_msg)
                            sent += 1
                        except Exception:
                            failed += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1
                await _aio.sleep(0.05)
            logger.info("Deploy announcement '%s': %d sent, %d failed", flag, sent, failed)

            # Mark as applied AFTER the send loop. If sent==0 (e.g. zero
            # active players, or all sends failed), don't burn the flag —
            # next deploy will retry. Burning preemptively was the v13/v14.2
            # footgun that ate this v14.3 broadcast initially.
            if sent > 0:
                async with get_session_factory()() as session:
                    await session.execute(
                        text("INSERT INTO applied_migrations (filename) VALUES (:f) "
                             "ON CONFLICT (filename) DO NOTHING"),
                        {"f": flag},
                    )
                    await session.commit()

    except Exception:
        logger.exception("Failed to send deploy announcement")


async def admin_force_announcement_command(update, context):
    """Admin-only: re-fire a pending deploy announcement by clearing its flag.

    Usage: /admin_announce <flag>
    Example: /admin_announce announce_v14_3_2026_05_14_v2

    Without args, lists known flags + their applied state. With a flag, deletes
    the row from `applied_migrations` so the next post_init pass re-broadcasts.
    """
    from sqlalchemy import text as _sql_text
    from database.db import get_session_factory
    user = update.effective_user
    if not user or user.id not in ADMIN_USERS:
        return
    args = context.args or []

    async with get_session_factory()() as session:
        if not args:
            lines = ["📢 *Deploy announcements:*"]
            for flag, key in _PENDING_DEPLOY_ANNOUNCEMENTS:
                row = (await session.execute(
                    _sql_text("SELECT 1 FROM applied_migrations WHERE filename = :f"),
                    {"f": flag},
                )).scalar_one_or_none()
                state = "✅ sent" if row else "⏳ pending"
                lines.append(f"• `{flag}` → `{key}` [{state}]")
            lines.append("")
            lines.append("Usage: `/admin_announce <flag>` to clear and re-fire on next start.")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return

        flag = args[0]
        known = {f for f, _ in _PENDING_DEPLOY_ANNOUNCEMENTS}
        if flag not in known:
            await update.message.reply_text(f"❌ Unknown flag `{flag}`.", parse_mode="Markdown")
            return
        await session.execute(
            _sql_text("DELETE FROM applied_migrations WHERE filename = :f"),
            {"f": flag},
        )
        await session.commit()
    await update.message.reply_text(
        f"✅ Cleared flag `{flag}`. Restart the bot (or wait for next post_init) "
        "and the broadcast will re-fire.",
        parse_mode="Markdown",
    )


# Global readiness flag used by the health server.
_READY = False


async def post_init(application: Application):
    # Start the aiohttp webserver FIRST so Coolify/Docker can reach :8080
    # immediately — migrations + seeds below can take a minute or two and
    # the healthcheck retry budget (10 × 5s) would otherwise expire.
    # Serves: /healthz, /miniapp, /api/miniapp/*, and the website at /.
    from core.webserver import start_webserver
    asyncio.create_task(start_webserver(8080))

    logger.info("post_init: starting DB init...")
    await init_db()
    logger.info("🏯 Database tables created")
    init_scheduler(application.bot)
    from core.announcement_engine import set_bot as _set_announcement_bot
    _set_announcement_bot(application.bot)

    # Install asyncio exception handler to catch orphan task crashes
    resource_monitor.install_asyncio_exception_handler()

    # One-time startup announcement (runs once per deploy via DB flag)
    asyncio.create_task(_maybe_send_deploy_announcement(application.bot))

    # v15.2b — Intent Tree release broadcast. Uses `broadcast_once` which:
    #   • Persists to GlobalAnnouncement → appears in mini-app Announcements
    #     tab automatically (mural do game).
    #   • Idempotent on the key — won't re-fire on subsequent boots.
    #   • Translates per-player (each receives in their own language).
    async def _v15_2b_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(15)  # let DB + announcement_engine settle
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_v15_2b_intent_tree",
                kind="release",
                icon="🌳",
            )
        except Exception:
            logger.exception("Failed to fire v15.2b Intent Tree broadcast")
    asyncio.create_task(_v15_2b_release_broadcast())

    # 星 2026-09-23 — O CORPO QUE ACENDE. Mesmo mecanismo do v15.2b: persiste no
    # mural (aba Avisos do mini-app) E chega a cada jogador na língua dele.
    # Idempotente pela chave — não re-dispara a cada reinício do contentor.
    async def _corpo_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(20)  # depois do v15.2b, para as duas não competirem
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_2026_09_23_corpo",
                kind="release",
                icon="🫀",
            )
        except Exception:
            logger.exception("Failed to fire 2026-09-23 Corpo broadcast")
    asyncio.create_task(_corpo_release_broadcast())

    # 至 2026-09-23 (2a) — A MACANETA + o nome do [jogador]. Chave PROPRIA (nao
    # acrescentada a' nota do Corpo) porque nao se sabe, daqui, se essa ja'
    # disparou num arranque anterior: `broadcast_once` e' idempotente pela
    # CHAVE, portanto editar o texto de uma nota ja' enviada perde-se em
    # silencio. Duas notas curtas sao honestas; uma nota perdida nao e'.
    async def _macaneta_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(25)  # depois do v15.2b (15s) e do Corpo (20s)
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_2026_09_23b_macaneta",
                kind="release",
                icon="🧭",
            )
        except Exception:
            logger.exception("Failed to fire 2026-09-23b macaneta broadcast")
    asyncio.create_task(_macaneta_release_broadcast())

    # 門 2026-09-27 — AS PORTAS (P6) e o COMBATE COMO CENA (2.2), que vao no
    # MESMO deploy. Chave PROPRIA pela mesma razao da macaneta: `broadcast_once`
    # e' idempotente pela chave. O texto diz que as duas coisas vivem no
    # Nivrael Beta — o `main` (Legado) recebe a nota e tem a onda OFF, e
    # `NAO_PROMETER.md` proibe dizer "esta' ligado no seu servidor".
    async def _portas_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(30)  # depois do v15.2b (15s), do Corpo (20s) e da macaneta (25s)
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_2026_09_27_portas",
                kind="release",
                icon="🚪",
            )
        except Exception:
            logger.exception("Failed to fire 2026-09-27 portas broadcast")
    asyncio.create_task(_portas_release_broadcast())

    # 減 2026-09-29 — A REDUCAO PROGRESSIVA (P7). Chave PROPRIA: `broadcast_once`
    # e' idempotente pela chave, e a nota das portas ja' saiu. O texto diz que
    # vive no Nivrael Beta — o `main` (Legado) recebe a nota e tem a onda OFF
    # (nenhuma frase recolhe la'), e `NAO_PROMETER.md` proibe dizer "esta'
    # ligado no seu servidor".
    async def _reducao_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(35)  # depois do v15.2b (15s), Corpo (20s), macaneta (25s) e portas (30s)
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_2026_09_29_reducao",
                kind="release",
                icon="📖",
            )
        except Exception:
            logger.exception("Failed to fire 2026-09-29 reducao broadcast")
    asyncio.create_task(_reducao_release_broadcast())

    # 冶 2026-09-29 — OS OFICIOS FALAM A SUA LINGUA (3.1). Chave PROPRIA. Ao
    # contrario das notas da onda, o que ela anuncia e' GLOBAL (nomes
    # traduzidos, o verbo "refinar", os caldeiroes) e chega tambem ao `main` —
    # por isso nao fala de "Nivrael Beta". A forma do Atelie (a luz) ainda nao
    # foi construida e a nota nao a promete (`NAO_PROMETER.md`).
    async def _oficios_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(40)  # depois do v15.2b (15s), Corpo (20s), macaneta (25s), portas (30s) e reducao (35s)
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_2026_09_29b_oficios",
                kind="release",
                icon="⚒️",
            )
        except Exception:
            logger.exception("Failed to fire 2026-09-29 oficios broadcast")
    asyncio.create_task(_oficios_release_broadcast())

    # 🎒 2026-09-30 — O INVENTARIO (3.2). Chave PROPRIA. A tabela e o anel que
    # acende sao da ONDA (so' no Nivrael Beta) e a nota di-lo, como as notas da
    # onda 2; as correccoes de baixo (os nomes dos "outros", a raridade da
    # armadilha, o detalhe no idioma, o botao do anel no chat, a tribulacao
    # perfeita) valem para TODOS os mundos e vao num bloco a parte.
    async def _inventario_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(45)  # depois do v15.2b (15s), Corpo (20s), macaneta (25s), portas (30s), reducao (35s) e oficios (40s)
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_2026_09_30_inventario",
                kind="release",
                icon="🎒",
            )
        except Exception:
            logger.exception("Failed to fire 2026-09-30 inventario broadcast")
    asyncio.create_task(_inventario_release_broadcast())

    # 🐾 2026-10-01 — AS BESTAS (3.3). Chave PROPRIA. O corpo da besta e o selo
    # que acende sao da ONDA (so' no Nivrael Beta) e a nota di-lo; o bloco de
    # baixo (a habilidade no idioma, o espolio sem ingles, a recolha recusada com
    # a frase certa) vale para TODOS os mundos. Nao promete a Arena de Bestas
    # (decisao do owner) nem a forma final (pergunta ao Astra).
    async def _bestas_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(50)  # depois do v15.2b (15s), Corpo (20s), macaneta (25s), portas (30s), reducao (35s), oficios (40s) e inventario (45s)
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_2026_10_01_bestas",
                kind="release",
                icon="🐾",
            )
        except Exception:
            logger.exception("Failed to fire 2026-10-01 bestas broadcast")
    asyncio.create_task(_bestas_release_broadcast())

    # 宗 2026-10-05 — A SEITA (4.1) + a correccao da Arena PvE (o report do [jogador]).
    # Chave PROPRIA. O selo das insignias e a cena do duelo sao da ONDA (so' no
    # Nivrael Beta) e a nota di-lo. Nao promete a forma final (pergunta ao Astra)
    # nem a Faccao (adiada — e' legado no proprio jogo, `O_MUNDO.md` §1).
    async def _seita_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(55)  # depois das bestas (50s) e de todas as de antes
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_2026_10_05_seita",
                kind="release",
                icon="🏯",
            )
        except Exception:
            logger.exception("Failed to fire 2026-10-05 seita broadcast")
    asyncio.create_task(_seita_release_broadcast())

    # 幫 2026-10-08 — A GUILDA (4.2). Chave PROPRIA. A planta das seis
    # instalacoes e a luz da melhoria sao da ONDA (so' no Nivrael Beta) e a nota
    # di-lo; o numero exacto do efeito vale para TODOS os mundos. Nao fala do que
    # os efeitos fazem acima de certos niveis (balance — decisao do owner,
    # `O_MUNDO.md` §4.6) nem promete a forma final (pergunta ao Astra).
    async def _guilda_release_broadcast():
        import asyncio as _aio
        await _aio.sleep(60)  # depois da Seita (55s) e de todas as de antes
        try:
            from core.announcement_engine import broadcast_once
            await broadcast_once(
                "release_2026_10_08_guilda",
                kind="release",
                icon="🤝",
            )
        except Exception:
            logger.exception("Failed to fire 2026-10-08 guilda broadcast")
    asyncio.create_task(_guilda_release_broadcast())

    # Start event loop health watchdog
    async def _event_loop_watchdog():
        """Detect event loop stalls. If the loop is blocked for >10s, log a warning."""
        while True:
            start = asyncio.get_event_loop().time()
            await asyncio.sleep(5)
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > 10:
                logger.error(
                    "EVENT LOOP STALL DETECTED: sleep(5) took %.1fs — "
                    "something is blocking the event loop!",
                    elapsed,
                )
            elif elapsed > 7:
                logger.warning(
                    "Event loop slow: sleep(5) took %.1fs",
                    elapsed,
                )
    asyncio.create_task(_event_loop_watchdog())

    # Start health + DB pool monitors
    asyncio.create_task(resource_monitor.health_watchdog())
    asyncio.create_task(resource_monitor.db_pool_monitor())

    # Flip the readiness flag so the health server reports 200 OK instead of 503.
    global _READY
    _READY = True

    logger.info("☯️ Nivrael — Bot online (PID=%d)", __import__("os").getpid())


# NOTE: the old hand-rolled HTTP server lived here. It has been replaced by
# core.webserver which uses aiohttp, validates Telegram WebApp initData via
# HMAC, and serves the marketing website at "/". See post_init() above for
# where the new server is started.



@safe_handler
@rate_limit(1)
async def combined_button_router(update, context):
    resource_monitor.track_callback()
    query = update.callback_query
    logger.debug("CB: user=%s data=%s", update.effective_user.id if update.effective_user else "?", query.data if query else "?")
    # Onboarding flow callbacks
    if query.data and query.data.startswith("onboard_lang_"):
        await onboard_lang_callback(update, context)
        return
    if query.data == "onboard_enter_qiankun":
        await onboard_enter_qiankun_callback(update, context)
        return
    if query.data == "onboard_confirm_name":
        await onboard_confirm_name_callback(update, context)
        return
    if query.data in ("noop", "none"):
        # "none" was used by 6 decorative buttons (shop pass/market/sect) but
        # never answered anywhere → Telegram spun the button until timeout
        # ("botão não está funcionando", [jogador] 2026-06-12 01:50).
        await query.answer()
        return

    if query.data and query.data.startswith("nav_"):
        await nav_router(update, context)
        return
    if query.data == "feedback_menu":
        await feedback_menu_callback(update, context)
        return
    if query.data and query.data.startswith("ranking_"):
        await ranking_command(update, context)
        return
    if query.data and query.data.startswith("notif_toggle_"):
        await notif_toggle_callback(update, context)
        return
    if query.data and query.data.startswith(("alch_", "cmd_alquimia")):
        handled = await alchemy_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("art_") or query.data == "cmd_artifacts"):
        handled = await artifact_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("inv_") or query.data == "cmd_inventory"):
        handled = await inventory_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith(("mkt_", "trd_")) or query.data == "cmd_market"):
        handled = await market_button_router(update, context)
        if handled: return
    if query.data and query.data.startswith("trib_"):
        await trib_callback_handler(update, context)
        return
    # MV-5 — Quests VIVAS: prefixo sty_ (oferta/aceitar/recusar/concluir).
    # Lição MV-2 (trv_wev_mine): o prefixo TEM de estar neste dispatch ANTES de
    # qualquer botão usá-lo. Não colide com sect_/spar_ (checa sty_ literal).
    if query.data and query.data.startswith("sty_"):
        handled = await storylet_button_router(update, context)
        if handled:
            return
    # MV-6 — O RIVAL: prefixo rvl_ (a memória na praça do chat). Lição MV-2:
    # registrado AQUI antes de qualquer botão usá-lo. Não colide (rvl_ literal).
    if query.data and query.data.startswith("rvl_"):
        handled = await rival_button_router(update, context)
        if handled:
            return
    # MV-8 — O Jiānghú: prefixo jha_ (a emboscada — ⚔️/💰/🏃). Lição MV-2:
    # registrado AQUI antes de qualquer botão usá-lo. Não colide (jha_ literal).
    if query.data and query.data.startswith("jha_"):
        handled = await jianghu_button_router(update, context)
        if handled:
            return
    # MV-9.5 商队 — A CARAVANA: prefixo crv_ (mandar vir uma carga na praça).
    # Lição MV-2, escrita cinco vezes neste ficheiro: o prefixo TEM de estar
    # neste dispatch ANTES de qualquer botão o usar — senão o callback cai no
    # fall-through lá em baixo e o botão gira até dar timeout. Não colide
    # (crv_ literal; nenhum callback existente começa por crv_).
    if query.data and query.data.startswith("crv_"):
        handled = await caravan_button_router(update, context)
        if handled:
            return
    # MV-7 — Profissões: prefixo prf_ (cerimônia/status/troca do /oficio).
    # Lição MV-2: registrado AQUI antes de qualquer botão usá-lo. Não colide
    # com prestige_/partner_/pvp_ (checa prf_ literal).
    if query.data and query.data.startswith("prf_"):
        handled = await profession_button_router(update, context)
        if handled:
            return
    # TEC-1 — Biblioteca da Seita: prefixo lib_ (estantes/learn do /biblioteca).
    # Lição MV-2: registrado AQUI antes de qualquer botão usá-lo. Não colide
    # (lib_ literal; nenhum callback existente começa por lib_).
    if query.data and query.data.startswith("lib_"):
        handled = await library_button_router(update, context)
        if handled:
            return
    # TEC-2 — Economia do Pergaminho: prefixo scr_ (arca/doar/queimar do
    # /pergaminhos). Lição MV-2: registrado AQUI antes de qualquer botão
    # usá-lo. Não colide (scr_ literal; nenhum callback existente começa
    # por scr_ — sect_/spar_/sty_ são outros prefixos).
    if query.data and query.data.startswith("scr_"):
        handled = await scroll_button_router(update, context)
        if handled:
            return
    # TEC-5 — Caminho Proibido: prefixo fpd_ (o Rito do Coracao-Demonio do
    # /coracao). Licao MV-2: registrado AQUI antes de qualquer botao usa-lo.
    # Nao colide (fpd_ literal; nenhum callback existente comeca por fpd_).
    if query.data and query.data.startswith("fpd_"):
        handled = await forbidden_button_router(update, context)
        if handled:
            return
    if query.data and (query.data.startswith("quest_") or query.data.startswith("qch_") or query.data == "cmd_missoes"):
        if query.data == "cmd_missoes":
            await query.answer()
            await missoes_command(update, context)
            return
        # v16.3.5 — qch_ is the Karmic Crossroads moral-choice callback. The
        # `if handled: return` also fixes a latent fall-through: unlike every
        # sibling branch this one never returned, so a handled quest callback
        # used to keep running the checks below (harmless today, a trap later).
        handled = await quests_button_router(update, context)
        if handled:
            return
    if query.data and (query.data.startswith("pvp_") or query.data == "cmd_combate" or query.data.startswith("npc_") or query.data.startswith("spar_wager_")):
        if query.data == "cmd_combate":
            await query.answer()
            await combat_command(update, context)
            return
        handled = await combat_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("beast_") or query.data.startswith("bestiario_") or query.data == "cmd_bestiario"):
        handled = await beasts_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("dao_") or query.data == "cmd_dao"):
        handled = await dao_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("boss_") or query.data == "cmd_boss"):
        handled = await boss_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("dng_") or query.data == "cmd_dungeons"):
        handled = await dungeon_button_router(update, context)
        if handled: return
    if query.data and (query.data in ("cmd_events", "events_list")):
        handled = await events_button_router(update, context)
        if handled: return
    if query.data and query.data.startswith("partner_"):
        handled = await partner_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("ach_") or query.data == "cmd_conquistas"):
        if query.data == "cmd_conquistas":
            await query.answer()
            await conquistas_command(update, context)
            return
        handled = await achievements_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("prestige_") or query.data in ["cmd_renascer", "cmd_prestige", "cmd_loja_prestige"]):
        handled = await prestige_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("fac_") or query.data == "cmd_faction"):
        handled = await faction_button_router(update, context)
        if handled: return
    if query.data and (query.data.startswith("cel_") or query.data == "cmd_celestial" or query.data.startswith("apex_chamber_")):
        handled = await celestial_button_router(update, context)
        if handled: return
    # v14.4 D-1 — Foundation reroll (recomeço) + ritual (quebrar_fundacao).
    if query.data and (query.data.startswith("recomeco_") or query.data.startswith("break_")):
        handled = await foundation_button_router(update, context)
        if handled: return
    if query.data and query.data == "cmd_loja":
        await query.answer()
        from handlers.shop import cmd_loja
        await cmd_loja(update, context)
        return
    # v16.4 — World Sects (Seita de Cultivo): cmd_seita_ancia + wsect_accept/decline.
    # Checked before the `sect_` block — `wsect_` does not match `sect_`.
    if query.data and (query.data.startswith("wsect_") or query.data == "cmd_seita_ancia"):
        handled = await world_sect_button_router(update, context)
        if handled:
            return
    # Onda 4b — Travel between continents: cmd_viajar + trv_d_*/trv_go_*.
    # `trv_` does not collide with `sect_`/`wsect_`.
    if query.data and (query.data.startswith("trv_") or query.data == "cmd_viajar"):
        handled = await travel_button_router(update, context)
        if handled:
            return
    # Onda 5 — Reinos Exploráveis: cmd_explorar + xpl_a_*/xpl_f_*/xpl_ret.
    # `xpl_` does not collide with `sect_`/`wsect_`/`trv_`.
    if query.data and (query.data.startswith("xpl_") or query.data == "cmd_explorar"):
        handled = await explore_button_router(update, context)
        if handled:
            return
    # Onda 5 Fase 2 — Cavernas 洞府 + Formações 阵法: cmd_caverna/cmd_formacoes +
    # cav_est/cav_claim/cav_clr/cav_set_* + frm_c_*/frm_a_*.
    # `cav_`/`frm_` do not collide with `sect_`/`wsect_`/`trv_`/`xpl_`.
    if query.data and (query.data.startswith("cav_") or query.data.startswith("frm_")
                       or query.data in ("cmd_caverna", "cmd_formacoes")):
        handled = await cavern_button_router(update, context)
        if handled:
            return
    if query.data and (query.data.startswith("sect_") or query.data == "cmd_seita"):
        if query.data == "sect_buildings": 
            await sect_buildings_menu(update, context)
            return
        elif query.data == "sect_list":
            from handlers.sect import sect_list_callback
            await sect_list_callback(update, context)
            return
        elif query.data.startswith("sect_list_page_"):
            from handlers.sect import sect_list_page_callback
            await sect_list_page_callback(update, context)
            return
        elif query.data.startswith("sect_join_"):
            from handlers.sect import sect_join_callback
            await sect_join_callback(update, context)
            return
        elif query.data.startswith("sect_members_page_"):
            from handlers.sect import sect_members_list_page_callback
            await sect_members_list_page_callback(update, context)
            return
        elif query.data == "sect_members_list":
            from handlers.sect import sect_members_list_callback
            await sect_members_list_callback(update, context)
            return
        elif query.data.startswith("sect_kick_inactive_"):
            from handlers.sect import sect_kick_inactive_callback
            await sect_kick_inactive_callback(update, context)
            return
        elif query.data == "sect_war_info":
            from handlers.sect import sect_war_info_callback
            await sect_war_info_callback(update, context)
            return
        elif query.data.startswith("sect_war_attack_"):
            await sect_war_attack_callback(update, context)
            return
        elif query.data == "sect_leave_confirm":
            from handlers.sect import sect_leave_confirm_callback
            await sect_leave_confirm_callback(update, context)
            return
        elif query.data == "sect_leave_execute":
            from handlers.sect import sect_leave_execute_callback
            await sect_leave_execute_callback(update, context)
            return
        elif query.data.startswith("sect_upgrade_"): 
            await sect_upgrade_callback(update, context)
            return
        elif query.data.startswith("sect_manage_"):
            from handlers.sect import sect_manage_member_callback
            await sect_manage_member_callback(update, context)
            return
        elif query.data.startswith("sect_action_"):
            from handlers.sect import sect_member_action_callback
            await sect_member_action_callback(update, context)
            return
        elif query.data.startswith("sect_buy_"):
            from handlers.sect import sect_buy_item_callback
            await sect_buy_item_callback(update, context)
            return
        elif query.data == "sect_member_info_none":
            await query.answer()
            return
        elif query.data == "sect_shop": 
            await loja_seita_command(update, context)
            return
        elif query.data == "sect_create_init": 
            await sect_create_init_callback(update, context)
            return
        elif query.data == "sect_vault": 
            await sect_vault_menu(update, context)
            return
        elif query.data == "sect_donate_init": 
            await sect_donate_init_callback(update, context)
            return
        elif query.data == "sect_edit_desc":
            await sect_edit_desc_callback(update, context)
            return
        elif query.data == "sect_bulletin":
            await sect_bulletin_callback(update, context)
            return
        elif query.data == "sect_bulletin_write":
            await sect_bulletin_write_callback(update, context)
            return
        elif query.data == "sect_group_link":
            await sect_group_link_callback(update, context)
            return
        elif query.data == "sect_group_link_set":
            await sect_group_link_set_callback(update, context)
            return
        elif query.data == "sect_contributions":
            from handlers.sect import sect_contributions_callback
            await sect_contributions_callback(update, context)
            return
        elif query.data.startswith("sect_contrib_detail_"):
            from handlers.sect import sect_contrib_detail_callback
            await sect_contrib_detail_callback(update, context)
            return
        elif query.data == "sect_contrib_ranking":
            from handlers.sect import sect_contrib_ranking_callback
            await sect_contrib_ranking_callback(update, context)
            return
        elif query.data == "sect_torch_accept":
            await sect_torch_accept_callback(update, context)
            return
        elif query.data == "sect_torch_refuse":
            await sect_torch_refuse_callback(update, context)
            return
        elif query.data == "sect_decree_init":
            await sect_decree_init_callback(update, context)
            return
        elif query.data == "sect_torch_menu":
            await sect_torch_menu_callback(update, context)
            return
        elif query.data.startswith("sect_torch_pick_"):
            await sect_torch_pick_callback(update, context)
            return
        elif query.data.startswith("sect_torch_fire_"):
            await sect_torch_fire_callback(update, context)
            return
        elif query.data in ["cmd_seita", "sect_info"]:
            await seita_menu(update, context)
            return
    await button_router(update, context)


@safe_handler
@rate_limit(1)
async def market_message_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data:
        return
    if context.user_data.get("awaiting_dao_name"):
        await process_dao_name_input(update, context)
        return
    if context.user_data.get("awaiting_daoname_change"):
        from handlers.shop import process_daoname_change_input
        await process_daoname_change_input(update, context)
        return
    if context.user_data.get("awaiting_price"):
        await process_price_input(update, context)
    elif context.user_data.get("awaiting_qty"):
        await process_qty_input(update, context)
    elif context.user_data.get("awaiting_bid"):
        await process_bid_input(update, context)
    elif context.user_data.get("awaiting_trade_stones"):
        await process_trade_stones_input(update, context)
    elif context.user_data.get("awaiting_trd_qty"):
        await process_trd_qty_input(update, context)
    elif context.user_data.get("awaiting_trade_daoname"):
        await process_trade_daoname_input(update, context)
    elif context.user_data.get("awaiting_sect_name"):
        await process_sect_name_input(update, context)
    elif context.user_data.get("awaiting_sect_donation"):
        await process_sect_donation_input(update, context)
    elif context.user_data.get("awaiting_sect_desc"):
        await process_sect_desc_input(update, context)
    elif context.user_data.get("awaiting_sect_bulletin"):
        await process_sect_bulletin_input(update, context)
    elif context.user_data.get("awaiting_sect_decree"):
        await process_sect_decree_input(update, context)
    elif context.user_data.get("awaiting_sect_group_link"):
        await process_sect_group_link_input(update, context)
    elif context.user_data.get("awaiting_partner_proposal"):
        await process_partner_proposal_input(update, context)
    elif context.user_data.get("awaiting_wager"):
        await process_wager_input(update, context)




async def _bind_player_world(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """PIVOT 2026-08-11 — liga cada update do CHAT ao MUNDO daquele jogador.

    Até aqui o chat era `main` por construção: nenhum handler resolvia mundo
    nenhum, e `get_session_factory()` caía sempre no default do ContextVar. Isso
    esteve certo enquanto `main` era o único mundo com gente. Agora quem chega
    nasce no **mundo de nascimento** (`signup_world_key()`), e sem esta ligação o
    chat mentiria de forma cruel para quem é novo: `/status` diria "não
    registado", e o `menu_command` — que cai para o `start_command` quando não
    acha o jogador — chegaria a criar um SEGUNDO personagem em `main`.

    ⚠️ PORQUÊ ISTO É SEGURO PARA OS 240 DO `main`: o ContextVar só é escrito
    quando o mundo resolvido NÃO é `main`. Para toda a gente que já existe — os
    240 receberam `player_active_server='main'` no backfill de
    `tools/db_write_s2_abertura.py` — a resolução devolve `main` e esta função
    não toca em nada: o comportamento fica byte-idêntico ao de sempre.

    ⚠️ PORQUÊ NÃO SE FAZ `reset`: o PTB processa cada update na sua própria task
    (`concurrent_updates(True)`), e um ContextVar escrito dentro de uma task
    morre com ela. Fazer reset aqui seria pior — o valor tem de sobreviver aos
    handlers dos grupos seguintes, que são o jogo inteiro.

    Fail-safe absoluto: qualquer erro deixa o mundo como está (= `main`). Um
    plano de controlo em baixo degrada o jogo para `main`, nunca o derruba.
    """
    try:
        user = update.effective_user
        if user is None or user.is_bot:
            return
        # O chat de GRUPO é sempre `main` (invariante antiga e deliberada: a
        # praça pública é uma só). Só as DMs seguem o mundo do jogador.
        chat = update.effective_chat
        if chat is not None and chat.type != "private":
            return
        from database.control_db import resolve_active_world_cached
        from database.db import MAIN_WORLD_KEY, set_current_world
        key = await resolve_active_world_cached(user.id)
        if key and key != MAIN_WORLD_KEY:
            set_current_world(key)
    except Exception:
        logger.warning("bind_player_world falhou — a seguir em main", exc_info=True)


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(60.0)
        .write_timeout(60.0)
        .connect_timeout(30.0)
        .pool_timeout(60.0)
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    # Moderação P0 (hotfix "A Volta" 2026-07-07) — group=-100: roda ANTES de
    # qualquer handler de jogo, e SÓ em grupos (DMs passam direto).
    setup_moderation_handlers(app)

    # PIVOT 2026-08-11 — group=-99: o CHAT passa a falar com o MUNDO do jogador.
    # Corre depois da moderação e ANTES de todo o jogo. Ver `_bind_player_world`.
    app.add_handler(TypeHandler(Update, _bind_player_world), group=-99)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("cultivar", cultivar_command))
    app.add_handler(CommandHandler("corpo", corpo_command))
    app.add_handler(CommandHandler("horta", horta_command))
    app.add_handler(CommandHandler("caca", horta_command))
    app.add_handler(CommandHandler("cerimonia", cerimonia_command))
    app.add_handler(CommandHandler("guia", guia_command))
    app.add_handler(CommandHandler("meditar", meditar_command))
    app.add_handler(CommandHandler("ranking", ranking_command))
    app.add_handler(CommandHandler("idioma", idioma_command))
    app.add_handler(CommandHandler("notif", notif_command))
    app.add_handler(CommandHandler("notificacoes", notif_command))
    app.add_handler(CommandHandler("notifications", notif_command))
    app.add_handler(CommandHandler("conf", config_command))
    app.add_handler(CommandHandler("config", config_command))
    app.add_handler(CommandHandler("configuracoes", config_command))
    app.add_handler(CommandHandler("configurar", config_command))
    app.add_handler(CommandHandler("settings", config_command))
    app.add_handler(CommandHandler("definicoes", config_command))
    app.add_handler(CommandHandler("ajustes", config_command))
    app.add_handler(CommandHandler("ajuda", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("miniapp", miniapp_command))
    app.add_handler(CommandHandler("app", miniapp_command))

    app.add_handler(CommandHandler("alquimia", alquimia_command))
    app.add_handler(CommandHandler("craftar", craftar_command))
    app.add_handler(CommandHandler("ervas", ervas_command))
    app.add_handler(CommandHandler("pilulas", pilulas_command))

    app.add_handler(CommandHandler("artefactos", artifacts_command))
    app.add_handler(CommandHandler("forjar", artifacts_command))

    app.add_handler(CommandHandler("inventario", inventory_command))
    app.add_handler(CommandHandler("inventory", inventory_command))

    app.add_handler(CommandHandler("mercado", market_command))
    app.add_handler(CommandHandler("vender", sell_wizard))
    app.add_handler(CommandHandler("trocar", trade_command))

    app.add_handler(CommandHandler("tribulacao", tribulacao_command))
    app.add_handler(CommandHandler("historico_tribulacao", historico_tribulacao))
    app.add_handler(CommandHandler("iniciar_tribulacao", tribulacao_command))

    # Sects
    app.add_handler(CommandHandler("seita", seita_menu))
    app.add_handler(CommandHandler("seita_ancia", world_sect_command))  # v16.4 — Seita de Cultivo (NPC sects); legacy alias kept (muscle-memory + buttons)
    app.add_handler(CommandHandler("seita_cultivo", world_sect_command))  # 2026-06-17 — canonical alias (3-tier taxonomy lock)
    app.add_handler(CommandHandler("seita_de_cultivo", world_sect_command))  # 2026-06-17 — verbose alias
    app.add_handler(CommandHandler("sussurros", whispers_command))  # Onda 3 — Heaven's Whispers feed
    app.add_handler(CommandHandler("cronica", cronica_command))  # World Pulse — Registos Celestiais (Chronicle)
    app.add_handler(CommandHandler("praca", praca_command))  # Onda 4a — Continental Plaza (Wànshì) + Bounty Board
    app.add_handler(CommandHandler("viajar", viajar_command))  # Onda 4b — Travel between continents
    app.add_handler(CommandHandler("explorar", explorar_command))  # Onda 5 — Reinos Exploráveis
    app.add_handler(CommandHandler("caverna", caverna_command))  # Onda 5 Fase 2 — Caverna Pessoal 洞府
    app.add_handler(CommandHandler("formacoes", formacoes_command))  # Onda 5 Fase 2 — Matrizes/Formações 阵法
    app.add_handler(CommandHandler("oficio", oficio_command))  # MV-7 — Profissões Wuxia (a Guilda dos Ofícios)
    app.add_handler(CommandHandler("biblioteca", biblioteca_command))  # TEC-1 — Biblioteca da Seita (estantes)
    app.add_handler(CommandHandler("pergaminhos", pergaminhos_command))  # TEC-2 — o destino do pergaminho (doar/queimar)
    app.add_handler(CommandHandler("coracao", coracao_command))  # TEC-5 — o Rito do Coração-Demônio 心魔
    app.add_handler(CommandHandler("criarseita", criarseita_command))
    app.add_handler(CommandHandler("entrarseita", entrarseita_command))
    app.add_handler(CommandHandler("doarseita", doarseita_command))
    app.add_handler(CommandHandler("sairseita", sairseita_command))
    app.add_handler(CommandHandler("promovermembro", promotemembro_command))
    app.add_handler(CommandHandler("expulsarmembro", expulmembro_command))
    app.add_handler(CommandHandler("ranking_sects", ranking_sects_command))
    app.add_handler(CommandHandler("loja_seita", loja_seita_command))
    app.add_handler(CommandHandler("startwar", admin_startwar_command))
    app.add_handler(CommandHandler("resolvewar", admin_resolvewar_command))
    # v14.3 — admin escape-hatch to re-fire a deploy announcement that got
    # stuck (e.g. flag burned but message failed to send).
    app.add_handler(CommandHandler("admin_announce", admin_force_announcement_command))

    # v14.2 D-3 — Sect Leader patch.
    app.add_handler(CommandHandler("decreto_supremo", decreto_supremo_command))
    app.add_handler(CommandHandler("decreto", decreto_supremo_command))
    app.add_handler(CommandHandler("edict", decreto_supremo_command))
    app.add_handler(CommandHandler("passar_tocha", passar_tocha_command))
    app.add_handler(CommandHandler("pass_torch", passar_tocha_command))
    app.add_handler(CommandHandler("pasar_antorcha", passar_tocha_command))
    # v14.3 D-6b — Apex Reflection Chamber (only Apex Cultivators can enter).
    app.add_handler(CommandHandler("camara_reflexao", camara_reflexao_command))
    app.add_handler(CommandHandler("camara", camara_reflexao_command))
    app.add_handler(CommandHandler("reflection", camara_reflexao_command))
    app.add_handler(CommandHandler("camara_reflexion", camara_reflexao_command))

    # v14.4 D-1 — Foundation system completo.
    # D-1a — newbie one-shot reroll (≤ realm 2 OR ≤ 7 days).
    # NOTE: Telegram BotFather rejects non-ASCII command names (`/recomeço` with
    # `ç` would crash on startup with `ValueError: Command \`recomeço\` is not a
    # valid bot command`). The ASCII aliases below cover the same flow; players
    # who type `/recomeço` see "unknown command" but `/recomeco` works.
    app.add_handler(CommandHandler("recomeco", recomeco_command))
    app.add_handler(CommandHandler("restart_foundation", recomeco_command))
    app.add_handler(CommandHandler("restart", recomeco_command))
    # D-1b — `/quebrar_fundacao` mid-game ritual (realm 5+).
    app.add_handler(CommandHandler("quebrar_fundacao", quebrar_fundacao_command))
    app.add_handler(CommandHandler("quebrarfundacao", quebrar_fundacao_command))
    app.add_handler(CommandHandler("break_foundation", quebrar_fundacao_command))
    app.add_handler(CommandHandler("romper_cimiento", quebrar_fundacao_command))

    # Combat
    app.add_handler(CommandHandler("combate", combat_command))
    app.add_handler(CommandHandler("desafiar", desafiar_command))
    app.add_handler(CommandHandler("arena", combat_command))
    app.add_handler(CommandHandler("ranking_arena", combat_command))
    app.add_handler(CommandHandler("tecnicas", combat_command))

    app.add_handler(CommandHandler("dungeons", dungeons_command))
    app.add_handler(CommandHandler("eventos", events_command))
    app.add_handler(CommandHandler("conquistas", conquistas_command))
    app.add_handler(CommandHandler("achievements", conquistas_command))
    app.add_handler(CommandHandler("missoes", missoes_command))
    app.add_handler(CommandHandler("bestiario", bestiario_command))
    app.add_handler(CommandHandler("dao", dao_command))
    app.add_handler(CommandHandler("boss", boss_command))
    
    app.add_handler(CommandHandler("renascer", renascer_command))
    app.add_handler(CommandHandler("prestige", prestige_command))
    app.add_handler(CommandHandler("loja_prestige", loja_prestige_command))

    # Factions
    app.add_handler(CommandHandler("faction", faction_command))
    app.add_handler(CommandHandler("faccao", faction_command))

    # Celestial System (Mahayana) — F-11
    app.add_handler(CommandHandler("celestial", celestial_command))
    app.add_handler(CommandHandler("celeste", celestial_command))

    # Monetization
    setup_shop_handlers(app)
    setup_gacha_handlers(app)
    setup_admin_monetization_handlers(app)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, market_message_dispatcher))
    app.add_handler(CallbackQueryHandler(combined_button_router))

    # Global error handler for unhandled exceptions
    async def global_error_handler(_update, context):
        from telegram.error import RetryAfter, TimedOut, NetworkError
        err = context.error
        if isinstance(err, RetryAfter):
            logger.warning("Global: Flood control, retry in %ds", err.retry_after)
        elif isinstance(err, (TimedOut, NetworkError)):
            logger.warning("Global: Transient error: %s: %s", type(err).__name__, err)
        else:
            logger.error("Global unhandled error: %s: %s", type(err).__name__, err, exc_info=err)
            # Also dump to stderr directly in case logging is broken
            import traceback as _tb
            sys.stderr.write(f"\n!!! GLOBAL ERROR: {type(err).__name__}: {err}\n")
            _tb.print_exception(type(err), err, err.__traceback__, file=sys.stderr)
            sys.stderr.flush()

    app.add_error_handler(global_error_handler)

    if WEBHOOK_URL:
        logger.info("🌐 Starting webhook on %s%s", WEBHOOK_URL, WEBHOOK_PATH)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=f"{WEBHOOK_URL}{WEBHOOK_PATH}",
            secret_token=WEBHOOK_SECRET if WEBHOOK_SECRET else None,
        )
    else:
        logger.info("🔄 Starting polling mode")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        logger.info("main() starting...")
        main()
    except KeyboardInterrupt:
        logger.critical("BOT STOPPED: KeyboardInterrupt")
    except SystemExit as e:
        logger.critical("BOT STOPPED: SystemExit code=%s", e.code)
    except Exception as e:
        logger.critical("BOT CRASHED at top level: %s", e, exc_info=True)
    finally:
        logger.critical("BOT PROCESS EXITING — this should NOT happen in production!")
        sys.stderr.flush()

