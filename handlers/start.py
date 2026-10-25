import re
import logging
from core.utils import safe_handler, rate_limit, _get_player, get_display_name, escape_markdown, safe_answer, add_item_to_inventory, normalize_lang
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from sqlalchemy import select, func

from config import FEEDBACK_GROUP_URL, MINIAPP_URL
from core.game_logic import (
    roll_spirit_root,
    get_spirit_root_name,
    get_spirit_root_emoji,
    get_realm_display,
    calculate_offline_progress,
    format_number,
)
from core.i18n import t, detect_language
from core.beast_engine import grant_starter_beast
from core.boss_engine import get_active_boss
from database.db import get_session_factory
from database.models import Player, PlayerArtifact, ArtifactCatalog

logger = logging.getLogger(__name__)

STARTER_SCROLL_IDS = [1, 4]

# Grade 0 starter artifacts: (catalog_id, slot, custom_stats)
STARTER_ARTIFACTS = [
    (1, "weapon", {"battle_power": 50}),      # Black Iron Sword
    (2, "armor", {"soul_strength": 30}),       # Spiritual Linen Tunic
    (3, "accessory1", {"luck": 5}),            # Ancient Copper Ring
]

# Regex for Dao Name validation: starts with letter, 3–16 chars, letters + digits only
_DAO_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9]{2,15}$")


async def create_starter_player(session, *, telegram_id: int, username: str | None,
                                display_name: str | None, lang: str, dao_name: str):
    """Create a fresh ZEROED cultivator + the full starter kit in the world BOUND
    to ``session``.

    Multi-Servidor: one Telegram account gets a SEPARATE, zeroed character in
    every server it enters (each world is its own DB). This mirrors the /start
    onboarding grants EXACTLY, so a mini-app "start in this world" is identical to
    a chat /start — just world-scoped. Does NOT commit (the caller commits). The
    caller MUST have verified there is no player for ``telegram_id`` in this world
    and that ``dao_name`` is free here."""
    from core.root_engine import derive_root_elements
    root_index = roll_spirit_root()
    root_elements = derive_root_elements(telegram_id)
    now = datetime.now(timezone.utc)
    player = Player(
        telegram_id=telegram_id,
        username=username or "",
        display_name=display_name or t(lang, "start_default_name"),
        dao_name=dao_name,
        realm=0, sub_layer=1, cultivation_base=0.0,
        spirit_root=root_index, root_elements=root_elements,
        spirit_stones=500, spirit_jade=0,
        qi=100.0, qi_capacity=100.0,
        battle_power=10, soul_strength=10, perception=10, luck=10,
        is_meditating=False, meditation_multiplier=1.0,
        language=lang, last_online=now, created_at=now,
    )
    session.add(player)
    await session.flush()
    for tech_id in STARTER_SCROLL_IDS:
        await add_item_to_inventory(session, telegram_id, "technique_scroll", tech_id)
    # MV-1 §0.3 (V-4): mundos com `ftue_espinha` ON nascem com a Beggar's Palm
    # (técnica de GOLPE usável em R0). No-op em main (flag OFF).
    from core.ftue_engine import grant_ftue_strike_technique
    await grant_ftue_strike_technique(session, telegram_id)
    await add_item_to_inventory(session, telegram_id, "beast_trap", 0, 2)
    for cat_id, slot, stats in STARTER_ARTIFACTS:
        session.add(PlayerArtifact(
            player_id=telegram_id, catalog_id=cat_id, grade=0, slot=slot,
            is_equipped=True, has_spirit=False, custom_stats=stats,
        ))
    await grant_starter_beast(session, telegram_id)
    return player


# ─── Navigation Keyboards ─────────────────────────────────────────────────────

async def main_menu_keyboard(lang: str = "pt", player=None, session=None) -> InlineKeyboardMarkup:
    """Central Hub - Top Level Categories"""

    cultivo_btn = t(lang, "nav_cultivo")
    combate_btn = t(lang, "nav_combate")
    workshop_btn = t(lang, "nav_workshop")
    premium_btn = t(lang, "nav_premium")

    if player and session:
        # Cultivation badge (Foundation Locked or Meditation ending < 5min)
        cultivo_alert = False
        if player.foundation_locked:
            cultivo_alert = True
        elif player.is_meditating and player.meditation_end:
            time_left = player.meditation_end - datetime.now(timezone.utc)
            if timedelta(seconds=0) < time_left <= timedelta(minutes=5):
                cultivo_alert = True

        if cultivo_alert:
            cultivo_btn += " ❗"

        # Combat badge (Tribulation Pending)
        from database.models import Tribulation
        stmt = select(Tribulation).where(
            Tribulation.player_id == player.telegram_id,
            Tribulation.status == "pending"
        )
        trib_pending = await session.scalar(stmt)
        if trib_pending:
            combate_btn += " ❗"

        # Activity indicators (cached 5 min)
        from core.activity_indicators import get_activity_indicators
        from core.monetization import get_player_vip_level
        vip_lvl = await get_player_vip_level(session, player.telegram_id)
        indicators = await get_activity_indicators(session, player, vip_lvl)

        # Quests → Cultivation category
        if indicators["quests"] and not cultivo_alert:
            cultivo_btn += f" {indicators['quests']}"

        # Expedition + Dungeon → Combat category
        combat_ind = indicators["expedition"] or indicators["dungeon"]
        if combat_ind and not trib_pending:
            combate_btn += f" {combat_ind}"

        # Alchemy → Workshop category
        if indicators["alchemy"]:
            workshop_btn += f" {indicators['alchemy']}"

        # Battle Pass → Premium category
        if indicators["bp"]:
            premium_btn += f" {indicators['bp']}"

    rows = [
        [InlineKeyboardButton(cultivo_btn, callback_data="nav_cultivo")],
        [InlineKeyboardButton(combate_btn, callback_data="nav_combate")],
        [InlineKeyboardButton(t(lang, "nav_comunica"), callback_data="nav_comunica")],
        [
            InlineKeyboardButton(workshop_btn, callback_data="nav_workshop"),
            InlineKeyboardButton(t(lang, "btn_inventory"), callback_data="cmd_inventory"),
        ],
        [
            InlineKeyboardButton(premium_btn, callback_data="nav_premium"),
            InlineKeyboardButton(t(lang, "btn_ranking"), callback_data="cmd_ranking")
        ],
    ]

    # Show celestial events button — highlight if any are active
    if session:
        from handlers.events import get_active_events
        active_events = await get_active_events(session)
        if active_events:
            rows.append([InlineKeyboardButton(t(lang, "btn_events_active"), callback_data="cmd_events")])
        else:
            rows.append([InlineKeyboardButton(t(lang, "btn_events"), callback_data="cmd_events")])
    else:
        rows.append([InlineKeyboardButton(t(lang, "btn_events"), callback_data="cmd_events")])

    if player and player.realm >= 8:
        rows.append([InlineKeyboardButton(t(lang, "btn_celestial"), callback_data="cmd_celestial")])

    rows.append([
        InlineKeyboardButton(t(lang, "btn_settings"), callback_data="cmd_settings"),
        InlineKeyboardButton(t(lang, "btn_help"), callback_data="cmd_help"),
        InlineKeyboardButton(t(lang, "btn_feedback"), url=FEEDBACK_GROUP_URL),
    ])

    if MINIAPP_URL:
        rows.append([InlineKeyboardButton(t(lang, "btn_open_miniapp"), web_app=WebAppInfo(url=MINIAPP_URL))])
    return InlineKeyboardMarkup(rows)

async def cultivo_menu_keyboard(lang: str = "pt", player=None, indicators: dict | None = None, session=None) -> InlineKeyboardMarkup:
    """Category 1: Cultivation and Base Stats.

    Owner UX feedback 2026-05-17: gated foundation/apex actions used to be
    standalone commands (`/recomeco`, `/quebrar_fundacao`, `/camara_reflexao`)
    — players in the wrong realm could still type them and waste taps. Now
    rendered as inline buttons that ONLY appear when the player is eligible.
    """
    rows = []
    ind = indicators or {}

    if player:
        if player.foundation_locked:
            rows.append([InlineKeyboardButton(t(lang, "btn_foundation_start"), callback_data="foundation_start")])
        elif getattr(player, "core_locked", False):
            rows.append([InlineKeyboardButton(t(lang, "btn_core_form"), callback_data="core_formation_start")])

    missoes_btn = t(lang, "btn_missoes")
    if ind.get("quests"):
        missoes_btn += f" {ind['quests']}"

    rows.extend([
        [
            InlineKeyboardButton(t(lang, "btn_status"), callback_data="cmd_status"),
            InlineKeyboardButton(t(lang, "btn_cultivar"), callback_data="cmd_cultivar"),
        ],
        [InlineKeyboardButton(t(lang, "btn_meditar"), callback_data="cmd_meditar")],
        [InlineKeyboardButton(missoes_btn, callback_data="cmd_missoes")],
        [InlineKeyboardButton(t(lang, "btn_achievements"), callback_data="cmd_conquistas")],
    ])

    player_realm = player.realm if player else 0
    if player_realm >= 5:
        rows.append([InlineKeyboardButton(t(lang, "btn_dao"), callback_data="cmd_dao")])
    if player_realm >= 8:
        rows.append([InlineKeyboardButton(t(lang, "btn_celestial"), callback_data="cmd_celestial")])

    # ── Gated foundation/apex actions (replace standalone commands) ──
    if player:
        try:
            from handlers.foundation import (
                _is_recomeco_eligible, _break_cooldown_remaining, BREAK_MIN_REALM,
            )
            ok_recomeco, _ = _is_recomeco_eligible(player)
            if ok_recomeco:
                rows.append([InlineKeyboardButton(
                    t(lang, "btn_recomeco_inline"), callback_data="cmd_recomeco")])
            if player_realm >= BREAK_MIN_REALM and _break_cooldown_remaining(player) is None:
                rows.append([InlineKeyboardButton(
                    t(lang, "btn_break_inline"), callback_data="cmd_quebrar_fund")])
        except Exception:
            pass  # foundation gating is cosmetic; never break menu rendering

        if session is not None:
            try:
                from core.celestial_engine import is_apex
                if await is_apex(session, player):
                    rows.append([InlineKeyboardButton(
                        t(lang, "btn_apex_chamber"), callback_data="apex_chamber_open")])
            except Exception:
                pass

    rows.append([InlineKeyboardButton(t(lang, "nav_main"), callback_data="nav_main")])
    return InlineKeyboardMarkup(rows)

async def combate_menu_keyboard(lang: str = "pt", player=None, session=None, indicators: dict | None = None) -> InlineKeyboardMarkup:
    """Category 2: Combat and Adventure"""
    ind = indicators or {}

    bestiario_btn = t(lang, "btn_bestiario")
    if ind.get("expedition"):
        bestiario_btn += f" {ind['expedition']}"

    dungeons_btn = t(lang, "btn_dungeons")
    if ind.get("dungeon"):
        dungeons_btn += f" {ind['dungeon']}"

    rows = [
        [
            InlineKeyboardButton(t(lang, "btn_combate"), callback_data="cmd_combate"),
        ],
        [InlineKeyboardButton(bestiario_btn, callback_data="cmd_bestiario")],
        [InlineKeyboardButton(dungeons_btn, callback_data="dng_list")],
        [InlineKeyboardButton(t(lang, "btn_npc_fight"), callback_data="npc_menu")],
    ]

    boss_active = False
    demonic_event = False
    if session:
        boss = await get_active_boss(session)
        boss_active = boss is not None and boss.current_hp > 0
        from handlers.events import get_active_events
        active_evs = await get_active_events(session)
        demonic_event = any(ev.type == "demonic_invasion" for ev in active_evs)

    if boss_active or demonic_event:
        label = t(lang, "btn_boss") if boss_active else f"💀 {t(lang, 'btn_boss')} ⚠️"
        rows.append([InlineKeyboardButton(label, callback_data="cmd_boss")])

    rows.append([InlineKeyboardButton(t(lang, "nav_main"), callback_data="nav_main")])
    return InlineKeyboardMarkup(rows)

async def comunica_menu_keyboard(lang: str = "pt", player=None) -> InlineKeyboardMarkup:
    """Category 3: Community and Trading"""
    rows = [
        [InlineKeyboardButton(t(lang, "btn_dao_partner"), callback_data="partner_menu")],
        [InlineKeyboardButton(t(lang, "btn_seita"), callback_data="cmd_seita")],
        [InlineKeyboardButton(t(lang, "btn_market"), callback_data="cmd_market")],
        [InlineKeyboardButton(t(lang, "btn_faction"), callback_data="cmd_faction")],
        [InlineKeyboardButton(t(lang, "nav_main"), callback_data="nav_main")]
    ]
    return InlineKeyboardMarkup(rows)

async def workshop_menu_keyboard(lang: str = "pt", player=None, session=None) -> InlineKeyboardMarkup:
    """Category 4: Crafting and Upgrades"""
    alch_btn = t(lang, "btn_alquimia")
    forge_btn = t(lang, "btn_artifacts")
    
    if player and session:
        from core.alchemy_engine import get_or_create_alchemy_skill
        from core.forge_engine import get_or_create_forge_skill
        alch_skill = await get_or_create_alchemy_skill(session, player.telegram_id)
        forge_skill = await get_or_create_forge_skill(session, player.telegram_id)
        
        alch_btn = f"{alch_btn} (T{alch_skill.tier})"
        forge_btn = f"{forge_btn} (T{forge_skill.tier})"

    rows = [
        [InlineKeyboardButton(alch_btn, callback_data="cmd_alquimia")],
        [InlineKeyboardButton(forge_btn, callback_data="cmd_artifacts")],
        [InlineKeyboardButton(t(lang, "nav_main"), callback_data="nav_main")]
    ]
    return InlineKeyboardMarkup(rows)

async def premium_menu_keyboard(lang: str = "pt", player=None) -> InlineKeyboardMarkup:
    """Category 5: Monetization and Prestige"""
    rows = [
        [InlineKeyboardButton(t(lang, "btn_loja"), callback_data="cmd_loja")],
    ]

    from core.prestige_engine import PRESTIGE_REQ_REALM, PRESTIGE_REQ_SUB_LAYER
    if player and (player.prestige_level > 0 or (player.realm >= PRESTIGE_REQ_REALM and player.sub_layer >= PRESTIGE_REQ_SUB_LAYER)):
        if player.prestige_level > 0:
            rows.append([InlineKeyboardButton(t(lang, "btn_prestige"), callback_data="cmd_prestige")])
        else:
            rows.append([InlineKeyboardButton(t(lang, "btn_renascer"), callback_data="cmd_renascer")])

    rows.append([InlineKeyboardButton(t(lang, "nav_main"), callback_data="nav_main")])
    return InlineKeyboardMarkup(rows)


@safe_handler
@rate_limit(1)
async def nav_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the Hub and Spoke navigation callbacks."""
    query = update.callback_query
    await safe_answer(query)

    user = update.effective_user
    nav_target = query.data

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)

        if not player:
            return

        lang = normalize_lang(player.language)
        text = t(lang, "nav_choose_option")

        if nav_target == "nav_main":
            realm_display = get_realm_display(player.realm, player.sub_layer)
            root_name = get_spirit_root_name(player.spirit_root)
            root_emoji = get_spirit_root_emoji(player.spirit_root)

            text = t(lang, "start_welcome_back",
                     name=escape_markdown(get_display_name(player)), realm=realm_display,
                     root_emoji=root_emoji, root_name=root_name)
            kb = await main_menu_keyboard(lang, player=player, session=session)
        elif nav_target == "nav_cultivo":
            text = t(lang, "nav_desc_cultivo")
            from core.activity_indicators import get_activity_indicators
            from core.monetization import get_player_vip_level
            vip_lvl = await get_player_vip_level(session, player.telegram_id)
            indicators = await get_activity_indicators(session, player, vip_lvl)
            kb = await cultivo_menu_keyboard(lang, player, indicators=indicators, session=session)
        elif nav_target == "nav_combate":
            text = t(lang, "nav_desc_combate")
            from core.activity_indicators import get_activity_indicators
            from core.monetization import get_player_vip_level
            vip_lvl = await get_player_vip_level(session, player.telegram_id)
            indicators = await get_activity_indicators(session, player, vip_lvl)
            kb = await combate_menu_keyboard(lang, player, session, indicators=indicators)
        elif nav_target == "nav_comunica":
            text = t(lang, "nav_desc_comunica")
            kb = await comunica_menu_keyboard(lang, player)
        elif nav_target == "nav_workshop":
            text = t(lang, "nav_desc_workshop")
            kb = await workshop_menu_keyboard(lang, player, session)
        elif nav_target == "nav_premium":
            text = t(lang, "nav_desc_premium")
            kb = await premium_menu_keyboard(lang, player)
        else:
            return

        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


# ─── Onboarding helpers ───────────────────────────────────────────────────────

def _get_root_rarity_message(root_index: int, lang: str) -> str:
    rarity_keys = {
        0: "root_rarity_heavenly",
        1: "root_rarity_superior",
        2: "root_rarity_high",
        3: "root_rarity_mid",
        4: "root_rarity_low",
    }
    key = rarity_keys.get(root_index, "root_rarity_low")
    return t(lang, key)


def _lang_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇧🇷 Português", callback_data="onboard_lang_pt"),
            InlineKeyboardButton("🇬🇧 English",  callback_data="onboard_lang_en"),
            InlineKeyboardButton("🇪🇸 Español",  callback_data="onboard_lang_es"),
        ]
    ])


def _lore_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "onboard_btn_enter"), callback_data="onboard_enter_qiankun")]
    ])


def _confirm_name_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(lang, "onboard_btn_confirm"), callback_data="onboard_confirm_name"),
            InlineKeyboardButton(t(lang, "onboard_btn_change"),  callback_data="onboard_enter_qiankun"),
        ]
    ])


# ─── /start command ───────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)

        if player:
            lang = normalize_lang(player.language)
            offline = await calculate_offline_progress(player, session=session)
            player.last_online = datetime.now(timezone.utc)
            await session.commit()

            realm_display = get_realm_display(player.realm, player.sub_layer)
            root_name = get_spirit_root_name(player.spirit_root)
            root_emoji = get_spirit_root_emoji(player.spirit_root)

            text = t(lang, "start_welcome_back",
                     name=escape_markdown(get_display_name(player)), realm=realm_display,
                     root_emoji=root_emoji, root_name=root_name)

            if offline["cb_gained"] > 0:
                text += t(lang, "start_offline_cb", cb=format_number(offline["cb_gained"]))
                if offline["breakthroughs"]:
                    text += "\n" + t(lang, "start_offline_breakthroughs",
                                     count=len(offline["breakthroughs"]))

            if offline.get("was_capped"):
                text += "\n" + t(lang, "offline_cap_warning", hours=f"{offline['lost_hours']:.1f}")

            text += t(lang, "start_dao_guide")

            menu_kb = await main_menu_keyboard(lang, player=player, session=session)

            if update.callback_query:
                await update.callback_query.message.edit_text(
                    text, parse_mode="Markdown", reply_markup=menu_kb,
                )
            else:
                await update.message.reply_text(
                    text, parse_mode="Markdown", reply_markup=menu_kb,
                )
            return

    # New user — step 1: language selection
    context.user_data["onboard_lang"] = detect_language(user.language_code)

    await update.message.reply_text(
        t("pt", "onboard_choose_lang"),
        parse_mode="Markdown",
        reply_markup=_lang_selection_keyboard(),
    )


# ─── Onboarding callback handlers ────────────────────────────────────────────

@safe_handler
async def onboard_lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1 → 2: Language chosen, show epic lore."""
    query = update.callback_query
    await safe_answer(query)

    lang_map = {"onboard_lang_pt": "pt", "onboard_lang_en": "en", "onboard_lang_es": "es"}
    lang = normalize_lang(lang_map.get(query.data))
    context.user_data["onboard_lang"] = lang

    await query.edit_message_text(
        t(lang, "onboard_lore"),
        parse_mode="Markdown",
        reply_markup=_lore_keyboard(lang),
    )


@safe_handler
async def onboard_enter_qiankun_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2 → 3: 'Enter Qiankun' clicked, ask for Dao Name."""
    query = update.callback_query
    await safe_answer(query)

    lang = normalize_lang(context.user_data.get("onboard_lang"))
    context.user_data["awaiting_dao_name"] = True
    context.user_data.pop("pending_dao_name", None)

    await query.edit_message_text(
        t(lang, "onboard_ask_dao_name"),
        parse_mode="Markdown",
    )


@safe_handler
async def process_dao_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 3 → 4: Validate name and show confirmation."""
    if not context.user_data.get("awaiting_dao_name"):
        return

    if not update.message or not update.message.text:
        return

    lang = normalize_lang(context.user_data.get("onboard_lang"))
    name = update.message.text.strip()

    if not _DAO_NAME_RE.match(name):
        await update.message.reply_text(
            t(lang, "onboard_name_invalid"),
            parse_mode="Markdown",
        )
        return

    async with get_session_factory()() as session:
        stmt = select(Player).where(func.lower(Player.dao_name) == name.lower())
        existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing:
        await update.message.reply_text(
            t(lang, "onboard_name_taken"),
            parse_mode="Markdown",
        )
        return

    context.user_data["pending_dao_name"] = name
    context.user_data["awaiting_dao_name"] = False

    await update.message.reply_text(
        t(lang, "onboard_name_preview", name=name),
        parse_mode="Markdown",
        reply_markup=_confirm_name_keyboard(lang),
    )


@safe_handler
async def onboard_confirm_name_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 4 → 5: Confirmed — create player, roll spirit root, show welcome."""
    query = update.callback_query
    await safe_answer(query)

    user = update.effective_user
    lang = normalize_lang(context.user_data.get("onboard_lang"))
    dao_name = context.user_data.get("pending_dao_name")

    if not dao_name:
        context.user_data["awaiting_dao_name"] = True
        await query.edit_message_text(
            t(lang, "onboard_ask_dao_name"),
            parse_mode="Markdown",
        )
        return

    # PIVOT 2026-08-11 — O NASCIMENTO ACONTECE NO MUNDO DE NASCIMENTO.
    # O `main` é agora o Mundo Legado (240 personagens, compras reais, as 28
    # flags OFF por construção). Quem chega hoje nasce no mundo novo, com o jogo
    # inteiro ligado. `signup_world_key()` devolve `main` se não houver mundo
    # marcado — logo, com o switch desligado, este bloco é um no-op e o /start
    # volta a ser exatamente o de sempre.
    #
    # ⚠️ A ORDEM É LOAD-BEARING: primeiro liga-se o ContextVar (para o
    # `get_session_factory()` abaixo abrir a sessão no DB CERTO), e só DEPOIS do
    # commit se escreve a row do plano de controlo. Ao contrário, um erro na
    # criação deixaria o jogador apontado para um mundo onde ele não existe —
    # e o mini-app mostrar-lhe-ia "needs_world_start" para sempre.
    from database.db import signup_world_key, MAIN_WORLD_KEY, set_current_world
    _birth_world = signup_world_key()
    if _birth_world != MAIN_WORLD_KEY:
        set_current_world(_birth_world)

    async with get_session_factory()() as session:
        # Race condition guard (case-insensitive)
        if (await session.execute(select(Player).where(func.lower(Player.dao_name) == dao_name.lower()))).scalar_one_or_none():
            context.user_data["awaiting_dao_name"] = True
            context.user_data.pop("pending_dao_name", None)
            await query.edit_message_text(
                t(lang, "onboard_name_taken") + "\n\n" + t(lang, "onboard_ask_dao_name"),
                parse_mode="Markdown",
            )
            return

        if await _get_player(user.id, session):
            context.user_data.clear()
            await query.edit_message_text(t(lang, "not_registered"), parse_mode="Markdown")
            return

        root_index = roll_spirit_root()
        # Track A item 5 — derive the ORTHOGONAL elemental composition at birth
        # (the quality `root_index` above is a separate axis). Deterministic per
        # telegram_id so it matches the startup backfill for existing players.
        from core.root_engine import derive_root_elements
        root_elements = derive_root_elements(user.id)
        now = datetime.now(timezone.utc)

        player = Player(
            telegram_id=user.id,
            username=user.username or "",
            display_name=user.first_name or t(lang, "start_default_name"),
            dao_name=dao_name,
            realm=0,
            sub_layer=1,
            cultivation_base=0.0,
            spirit_root=root_index,
            root_elements=root_elements,
            spirit_stones=500,
            spirit_jade=0,
            qi=100.0,
            qi_capacity=100.0,
            battle_power=10,
            soul_strength=10,
            perception=10,
            luck=10,
            is_meditating=False,
            meditation_multiplier=1.0,
            language=lang,
            last_online=now,
            created_at=now,
        )
        session.add(player)
        await session.flush()

        for tech_id in STARTER_SCROLL_IDS:
            await add_item_to_inventory(session, user.id, "technique_scroll", tech_id)

        # MV-1 §0.3 (V-4): espelho do create_starter_player — mundos com
        # `ftue_espinha` ON nascem com a Beggar's Palm. No-op em main.
        from core.ftue_engine import grant_ftue_strike_technique
        await grant_ftue_strike_technique(session, user.id)

        await add_item_to_inventory(session, user.id, "beast_trap", 0, 2)

        # Grant starter artifacts (Grade 0 weapon, armor, accessory)
        for cat_id, slot, stats in STARTER_ARTIFACTS:
            session.add(PlayerArtifact(
                player_id=user.id,
                catalog_id=cat_id,
                grade=0,
                slot=slot,
                is_equipped=True,
                has_spirit=False,
                custom_stats=stats,
            ))

        await grant_starter_beast(session, user.id)

        # Sprint 1 — Raça: espelho de `api_world_start`. Só nasce com raça quem
        # nasce num mundo com `racas` ON; `main` tem a flag OFF por construção,
        # portanto NENHUM dos 240 legados ganha raça (regra de ferro dos 57).
        try:
            from database.db import feature_enabled_for_world
            from core.race_engine import derive_race
            if feature_enabled_for_world("racas", _birth_world):
                player.race = derive_race(user.id)
        except Exception:
            logger.warning("race roll on chat onboarding failed", exc_info=True)

        await session.commit()

    # Só DEPOIS do commit: o jogador existe mesmo naquele mundo, agora aponta-se
    # para lá (o mini-app segue esta row no seu middleware).
    if _birth_world != MAIN_WORLD_KEY:
        try:
            from database.control_db import set_active_world
            await set_active_world(user.id, _birth_world)
        except Exception:
            logger.warning("set_active_world on onboarding failed", exc_info=True)

    context.user_data.pop("onboard_lang", None)
    context.user_data.pop("pending_dao_name", None)
    context.user_data.pop("awaiting_dao_name", None)

    root_name = get_spirit_root_name(root_index)
    root_emoji = get_spirit_root_emoji(root_index)

    root_reveal = (
        f"{t(lang, 'root_reveal_title')}\n\n"
        f"{t(lang, 'root_reveal_format', root_emoji=root_emoji, root_name=root_name)}"
    )
    rarity_msg = _get_root_rarity_message(root_index, lang)

    full_text = t(
        lang, "onboard_complete",
        name=dao_name,
        root_reveal=root_reveal,
        rarity_msg=rarity_msg,
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_start_cultivate"), callback_data="cmd_cultivar")],
        [InlineKeyboardButton(t(lang, "btn_help"), callback_data="cmd_help")],
    ])

    await query.edit_message_text(full_text, parse_mode="Markdown", reply_markup=kb)


# ─── /menu command ────────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the main hub directly without onboarding text."""
    user = update.effective_user
    if not user:
        return

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)

        if not player:
            await start_command(update, context)
            return

        lang = normalize_lang(player.language)
        realm_display = get_realm_display(player.realm, player.sub_layer)
        root_name = get_spirit_root_name(player.spirit_root)
        root_emoji = get_spirit_root_emoji(player.spirit_root)

        text = t(lang, "start_welcome_back",
                 name=escape_markdown(get_display_name(player)), realm=realm_display,
                 root_emoji=root_emoji, root_name=root_name)

        menu_kb = await main_menu_keyboard(lang, player=player, session=session)

        if update.callback_query:
            await update.callback_query.message.edit_text(
                text, parse_mode="Markdown", reply_markup=menu_kb,
            )
        else:
            await update.message.reply_text(
                text, parse_mode="Markdown", reply_markup=menu_kb,
            )


@safe_handler
@rate_limit(1)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = "en"
    player = None

    async with get_session_factory()() as session:
        user = update.effective_user
        if user:
            player = await _get_player(user.id, session)
            if player:
                lang = normalize_lang(player.language)

        text = t(lang, "help_text")
        menu_kb = await main_menu_keyboard(lang, player=player, session=session)

    if update.callback_query:
        await update.callback_query.message.edit_text(
            text, parse_mode="Markdown", reply_markup=menu_kb
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=menu_kb
        )


@safe_handler
@rate_limit(1)
async def feedback_menu_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """Shows feedback info with a link to the community group."""
    query = update.callback_query
    await safe_answer(query)

    user = update.effective_user
    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            lang = normalize_lang(getattr(user, "language_code", None))
        else:
            lang = normalize_lang(player.language)

    text = f"*{t(lang, 'feedback_title')}*\n\n{t(lang, 'feedback_desc')}"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_feedback_group"), url=FEEDBACK_GROUP_URL)],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_main")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
