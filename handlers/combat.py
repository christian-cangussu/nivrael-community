from core.utils import escape_markdown, safe_handler, rate_limit, safe_answer, safe_parse_callback_int, add_item_to_inventory, normalize_lang
import logging
import random
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, func

from config import REALM_NAMES
from core.game_logic import (
    get_player_equipment_stats,
    calculate_total_stats,
    format_number,
    get_realm_display,
)
from core.combat_engine import (
    build_fighter_data,
    simulate_combat,
    generate_combat_narration,
    generate_npc_fighter,
    apply_hp_drain,
    apply_hp_drain_scaled,
    get_current_hp,
    get_max_hp,
    apply_stance_and_focus,
    MASTERY_STAGES,
    get_mastery_stage,
    STANCES,
    CURRENT_SEASON,
    ARENA_ELO_RANGE,
    ARENA_QUEUE_TIMEOUT_SECONDS,
    CHALLENGE_EXPIRY_SECONDS,
    NPC_DIFFICULTIES,
    NPC_LOOT_TABLE,
    get_max_combat_techniques,
    GRADE_UPGRADE_REQS,
    get_grade_info,
    get_next_grade,
)
from core.i18n import t
# 名 2026-09-14 — o nome da arte deixa de sair CRU no chat. O conteudo ja' existia
# (129 x 2 campos x 3 linguas desde o TEC-1/TEC-4/TEC-5) e chegava a 9 de 41
# sitios; as 12 leituras deste ficheiro eram as piores, porque e' aqui que o
# jogador ESCOLHE a arte. Dono unico em `core/i18n.py` (Lei F-7 §2).
from core.i18n import catalog_name as _cname, catalog_desc as _cdesc
from core.i18n import catalog_text
from database.db import get_session_factory
from database.models import (
    Player, PlayerArtifact, PlayerTechnique, TechniqueCatalog,
    CombatLog, ArenaRanking, PlayerInventory, PlayerNPCCooldown,
    DaoLawCatalog, PlayerDaoFragment,
)


async def _get_arena_rank(session, player_id: int) -> int | None:
    """Return the 1-based rank position of a player in the current arena season, or None."""
    player_ranking = (await session.execute(
        select(ArenaRanking).where(
            ArenaRanking.player_id == player_id,
            ArenaRanking.season == CURRENT_SEASON,
        )
    )).scalar_one_or_none()
    if not player_ranking:
        return None
    higher_count = (await session.execute(
        select(func.count()).select_from(ArenaRanking).where(
            ArenaRanking.season == CURRENT_SEASON,
            ArenaRanking.elo_points > player_ranking.elo_points,
        )
    )).scalar() or 0
    return higher_count + 1


async def _maybe_award_arena_scroll(session, player_id: int, wins: int) -> str | None:
    # NOTA (recon TEC-2, 2026-07-27): esta cópia está MORTA — o faucet vivo é o
    # gêmeo em core/arena_duel_settle.py:131 (grep: aqui só existe a definição).
    # Mantida em lockstep de propósito: um futuro caller que a ressuscitasse com
    # o passo antigo reabriria o faucet que o TEC-2 fechou.
    from core.scroll_economy_engine import arena_scroll_step
    step = arena_scroll_step()
    if wins == 0 or wins % step != 0:
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

    # v16.4c — exclude house signature arts (sect_key): Library-only, never a scroll drop (Lei §5).
    all_techs = (await session.execute(
        select(TechniqueCatalog).where(TechniqueCatalog.sect_key.is_(None))
    )).scalars().all()
    candidates = [tech for tech in all_techs if tech.id not in learned_ids and tech.id not in owned_ids]

    if not candidates:
        return None

    chosen = random.choice(candidates)

    added = await add_item_to_inventory(session, player_id, "technique_scroll", chosen.id)
    if not added:
        return None

    return f"{chosen.emoji} {chosen.name}"

logger = logging.getLogger(__name__)

RANKING_PAGE_SIZE = 50
# v15.1.5 — Arena queue lives in `arena_queue` table (core/arena_engine.py).
# The chat handler is a thin adapter on top of the engine; both surfaces
# share the same pool. Legacy `context.bot_data["arena_queue"]` removed.


# ─── Helper ──────────────────────────────────────────────────────────────────

from core.utils import escape_markdown, _get_player, _ensure_player, get_display_name

REALM_HIERARCHY_GAP = 3  # block sparring if realm difference >= this value


async def _get_equipped_artifacts(session, telegram_id: int) -> list:
    stmt = select(PlayerArtifact).where(
        PlayerArtifact.player_id == telegram_id,
        PlayerArtifact.is_equipped == True,
    )
    return (await session.execute(stmt)).scalars().all()


async def _get_active_combat_techniques(session, telegram_id: int) -> list:
    """Fetch only active COMBAT techniques (not meditation/interior) for fighter data."""
    stmt = (
        select(
            PlayerTechnique.technique_id,
            PlayerTechnique.mastery_level,
            PlayerTechnique.mastery_xp,
            PlayerTechnique.is_active_combat,
            # 名-CRU: alimenta o simulador, e o nome acaba no
            # `combat_log.rounds_data` PERSISTIDO, lido pelos DOIS lutadores.
            # Mesmo motivo do `core/combat_engine.py`.
            TechniqueCatalog.name,
            TechniqueCatalog.emoji,
            TechniqueCatalog.effect_type,
            TechniqueCatalog.effect_value,
            TechniqueCatalog.effect_round,
            PlayerTechnique.grade,
            TechniqueCatalog.intent_affinity,
        )
        .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
        .where(
            PlayerTechnique.player_id == telegram_id,
            PlayerTechnique.is_active_combat == True,
            TechniqueCatalog.tech_type == "combat",
        )
    )
    rows = (await session.execute(stmt)).all()

    class _TechRow:
        def __init__(self, row):
            self.technique_id = row[0]
            self.mastery_level = row[1]
            self.mastery_xp = row[2]
            self.is_active_combat = row[3]
            self.name = row[4]
            self.emoji = row[5]
            self.effect_type = row[6]
            self.effect_value = row[7]
            self.effect_round = row[8]
            self.grade = row[9] if len(row) > 9 else "common"
            # D3 (v16.6): intent affinity so simulate_combat applies the passive aura.
            self.intent_affinity = row[10] if len(row) > 10 else None

    return [_TechRow(r) for r in rows]


async def _get_or_create_arena_ranking(session, telegram_id: int) -> ArenaRanking:
    stmt = select(ArenaRanking).where(
        ArenaRanking.player_id == telegram_id,
        ArenaRanking.season == CURRENT_SEASON,
    )
    ranking = (await session.execute(stmt)).scalar_one_or_none()
    if not ranking:
        ranking = ArenaRanking(
            player_id=telegram_id,
            season=CURRENT_SEASON,
            elo_points=1000,
            wins=0,
            losses=0,
        )
        session.add(ranking)
    return ranking


async def _build_fighter(session, player: Player) -> dict:
    arts = await _get_equipped_artifacts(session, player.telegram_id)
    techs = await _get_active_combat_techniques(session, player.telegram_id)
    from core.combat_engine import get_combat_buff_mults
    buff_mults = await get_combat_buff_mults(session, player.telegram_id)
    from core.beast_engine import get_companion_beast, get_companion_bonuses, get_pet_combat_ability
    comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
    comp_bonus = get_companion_bonuses(comp_beast, comp_catalog)
    # [jogador] 2026-06-11: the companion's special ability (the round-1 strike
    # simulate_combat already implements) was NEVER wired on ANY surface — the
    # builder existed with zero callers. NOTE the arg order: (catalog, beast).
    pet_ability = get_pet_combat_ability(comp_catalog, comp_beast,
                                         player.language or "pt")
    from core.dao_engine import get_player_dao_bonuses
    dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)
    from core.faction_engine import get_faction_bonuses
    fac_bonuses = await get_faction_bonuses(session, player.telegram_id)
    from core.combat_engine import get_unified_combat_bonuses
    interior_b, ach_b = await get_unified_combat_bonuses(session, player.telegram_id)
    fighter = build_fighter_data(player, arts, techs, pet_ability=pet_ability, buff_mults=buff_mults, companion_bonus=comp_bonus, dao_bonuses=dao_bonuses, faction_bonuses=fac_bonuses, interior_bonuses=interior_b, achievement_bonuses=ach_b)
    # D3 (v16.6): inject Intent ranks so the passive aura applies in spar/npc-hunt
    # (parity with duel_engine). NPC opponents are built elsewhere with no aura.
    from core.intent_engine import snapshot_intent_ranks
    fighter["intent_ranks"] = await snapshot_intent_ranks(session, player)
    return fighter


async def _award_mastery_xp(session, player_id: int, tech_activations: dict, won: bool, lang: str) -> list[str]:
    """Award mastery XP to techniques that activated. Returns list of level-up messages."""
    levelup_msgs = []
    for tech_id, activations in tech_activations.items():
        if activations <= 0:
            continue
        stmt = (
            select(PlayerTechnique, TechniqueCatalog.name, TechniqueCatalog.emoji)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
            .where(
                PlayerTechnique.player_id == player_id,
                PlayerTechnique.technique_id == tech_id,
            )
        )
        row = (await session.execute(stmt)).first()
        if not row:
            continue
        pt, tech_name, tech_emoji = row
        tech_name = catalog_text(lang, "tech", pt.technique_id, "name", tech_name)

        xp_gain = activations * 5 + (20 if won else 0)
        pt.mastery_xp += xp_gain

        # Check for level-ups
        while pt.mastery_level < 5:
            next_stage = MASTERY_STAGES.get(pt.mastery_level + 1)
            if next_stage and pt.mastery_xp >= next_stage["xp_req"]:
                pt.mastery_level += 1
                new_stage = MASTERY_STAGES[pt.mastery_level]
                stage_name = t(lang, f"technique_mastery_stage_{pt.mastery_level}")
                levelup_msgs.append(
                    t(lang, "technique_mastery_up",
                      emoji=tech_emoji, name=tech_name,
                      stage_emoji=new_stage["emoji"], stage=stage_name)
                )
            else:
                break
    return levelup_msgs


async def _send_or_edit(update: Update, text: str, kb: InlineKeyboardMarkup):
    from telegram.error import RetryAfter, TimedOut, NetworkError, BadRequest
    try:
        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    except RetryAfter as e:
        import asyncio
        await asyncio.sleep(e.retry_after + 0.5)
        try:
            if update.callback_query:
                await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            logger.warning("Retry after flood failed in _send_or_edit")
    except BadRequest as e:
        msg = str(e)
        if "Message is not modified" in msg:
            return
        # N-28 (v14.3): When Markdown is broken (truncation cut mid-entity, or
        # an unescaped `*` / `_` in a catalog name), Telegram rejects with
        # "can't parse entities" / "Can't find end of the entity". Retry once
        # without parse_mode so the player still sees something instead of a
        # silent failure. [jogadores] both hit this on Gerir Técnicas.
        if "parse" in msg.lower() or "entity" in msg.lower() or "entities" in msg.lower():
            try:
                if update.callback_query:
                    await update.callback_query.message.edit_text(text, reply_markup=kb)
                else:
                    await update.message.reply_text(text, reply_markup=kb)
                logger.warning("combat: Markdown broken, retried plain-text. err=%s", e)
                return
            except Exception as e2:
                logger.warning("combat: plain-text fallback also failed: %s", e2)
                return
        logger.warning("combat send BadRequest: %s", e)
    except (TimedOut, NetworkError) as e:
        logger.warning("combat send transient error: %s", type(e).__name__)
    except Exception as e:
        logger.error("combat send error: %s", e)
        try:
            if update.callback_query:
                await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
        except Exception:
            logger.warning("combat fallback reply also failed")


# ─── Main Combat Menu ────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def combat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = normalize_lang(player.language)
        equip_stats = get_player_equipment_stats(await _get_equipped_artifacts(session, player.telegram_id))
        # Onda C (A Alma do Cultivador) — /combate stops lying. ON → the aggregated
        # Poder de Combate (== the header) + the Alma's effective HP (== the arena/
        # profile); the old calculate_total_stats(player, equip_stats) here dropped
        # companion/Dao/interior/achievement → showed 20-50% too little. OFF (main) →
        # legacy path byte-identical (the 57 grandfathered until the world flips a flag).
        from database.db import feature_enabled_for_world as _ffe
        if _ffe("combate_unificado") or _ffe("progressao_visivel"):
            from core.cultivator_soul import compute_cultivator_soul, soul_current_hp
            _soul = await compute_cultivator_soul(session, player)
            _bp_val = _soul["display_power"]          # internally gated by progressao_visivel
            _max_hp = float(_soul["max_hp"])           # internally gated by combate_unificado
            _cur_hp = soul_current_hp(player, _max_hp)
        else:
            total_stats = calculate_total_stats(player, equip_stats)
            _bp_val = total_stats["total_battle_power"]
            _max_hp = float(get_max_hp(player))
            _cur_hp = float(get_current_hp(player))
        realm_display = get_realm_display(player.realm, player.sub_layer)

        ranking = await _get_or_create_arena_ranking(session, player.telegram_id)
        await session.commit()

    bp_display = format_number(_bp_val)
    cur_hp = _cur_hp
    max_hp_val = _max_hp
    hp_pct = int(cur_hp / max_hp_val * 100) if max_hp_val > 0 else 100

    text = (
        t(lang, "combat_main_title") +
        f"🏯 *{escape_markdown(get_display_name(player))}*\n"
        f"{realm_display}\n\n"
        f"{t(lang, 'combat_main_bp')}*{bp_display}*\n"
        f"❤️ HP: *{format_number(cur_hp)}* / *{format_number(max_hp_val)}* ({hp_pct}%)\n"
        f"{t(lang, 'combat_main_elo')}*{ranking.elo_points}* ({ranking.wins}V / {ranking.losses}D)\n\n"
        + t(lang, "combat_main_prompt")
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(lang, "btn_combat_sparring"), callback_data="pvp_sparring_menu"),
            InlineKeyboardButton(t(lang, "btn_combat_arena"), callback_data="pvp_arena_menu"),
        ],
        [
            InlineKeyboardButton(t(lang, "btn_combat_npc"), callback_data="npc_menu"),
            InlineKeyboardButton(t(lang, "btn_combat_techniques"), callback_data="pvp_techniques_menu"),
        ],
        [
            InlineKeyboardButton(t(lang, "btn_ranking"), callback_data="pvp_ranking"),
        ],
        [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="nav_combate")],
    ])

    await _send_or_edit(update, text, kb)


# ─── Sparring ─────────────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def desafiar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    await _sparring_menu(update, context)


async def _sparring_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = normalize_lang(player.language)

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        stmt = (
            select(Player)
            .where(
                Player.telegram_id != player.telegram_id,
                Player.last_online >= cutoff,
            )
            .order_by(Player.battle_power.desc())
            .limit(10)
        )
        targets = (await session.execute(stmt)).scalars().all()
        await session.commit()

    if not targets:
        text = t(lang, "combat_sparring_empty")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")],
        ])
        await _send_or_edit(update, text, kb)
        return

    text = t(lang, "combat_sparring_title") + "\n" + t(lang, "combat_pvp_chat_miniapp_hint") + "\n\n"

    buttons = []
    for target in targets:
        realm_display = get_realm_display(target.realm, target.sub_layer)
        name = escape_markdown(get_display_name(target))
        bp_display = format_number(target.battle_power)
        btn_text = f"⚔️ {name} | {realm_display} | BP: {bp_display}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"pvp_ch_menu_{target.telegram_id}")])

    buttons.append([InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")])

    kb = InlineKeyboardMarkup(buttons)
    await _send_or_edit(update, text, kb)


async def _handle_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int = None):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)

    if target_id is None:
        target_id = safe_parse_callback_int(query.data, "pvp_challenge_")
        if target_id is None:
            return
    challenger_id = update.effective_user.id

    if target_id == challenger_id:
        await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_não_podes_desafiarte_a"), show_alert=True)
        return

    async with get_session_factory()() as session:
        challenger = await _get_player(challenger_id, session)
        target = await _get_player(target_id, session)

        if not challenger or not target:
            await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_jogador_não_encontrado"), show_alert=True)
            return

        lang = normalize_lang(challenger.language)

        # Block combat if HP is 0
        if get_current_hp(challenger) <= 0:
            await query.message.edit_text(
                t(lang, "hp_too_low_combat"),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")]]),
            )
            return

        if abs(challenger.realm - target.realm) >= REALM_HIERARCHY_GAP:
            await safe_answer(query, t(challenger.language, "realm_too_low_for_interaction"), show_alert=True)
            return

        challenger_name = escape_markdown(get_display_name(challenger))
        target_name = escape_markdown(get_display_name(target))
        challenger_realm = get_realm_display(challenger.realm, challenger.sub_layer)

        context.user_data["wager_prep"] = {
            "target_id": target_id,
        }

        await session.commit()
        
    challenger_ss = challenger.spirit_stones

    text = t(lang, "spar_wager_select", target_name=target_name) + f"\n\n💰 *{t(lang, 'your_spirit_stones')}:* {challenger_ss}"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(lang, "btn_wager_none"), callback_data=f"spar_wager_{target_id}_0"),
            InlineKeyboardButton(t(lang, "btn_wager_100"), callback_data=f"spar_wager_{target_id}_100"),
        ],
        [
            InlineKeyboardButton(t(lang, "btn_wager_500"), callback_data=f"spar_wager_{target_id}_500"),
            InlineKeyboardButton(t(lang, "btn_wager_1000"), callback_data=f"spar_wager_{target_id}_1000"),
        ],
        [
            InlineKeyboardButton(t(lang, "btn_wager_5000"), callback_data=f"spar_wager_{target_id}_5000"),
            InlineKeyboardButton(t(lang, "btn_wager_custom"), callback_data=f"spar_wager_{target_id}_custom"),
        ],
        [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_sparring_menu")]
    ])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

async def _handle_challenge_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)
    
    target_id = safe_parse_callback_int(query.data, "pvp_ch_menu_")
    if target_id is None:
        return
    challenger_id = update.effective_user.id
    
    if target_id == challenger_id:
        await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_não_podes_desafiarte_a"), show_alert=True)
        return
        
    async with get_session_factory()() as session:
        challenger_player = await _get_player(challenger_id, session)
        target = await _get_player(target_id, session)
        if not target:
            return
        if challenger_player:
            lang = normalize_lang(challenger_player.language)
        target_name = escape_markdown(get_display_name(target))
    
    text = t(lang, "combat_sparring_mode_select", target_name=target_name)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_combat_sparring_normal"), callback_data=f"pvp_challenge_normal_{target_id}")],
        [InlineKeyboardButton(t(lang, "btn_combat_sparring_wager"), callback_data=f"pvp_challenge_wager_{target_id}")],
        [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_sparring_menu")],
    ])
    
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

async def _route_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("pvp_challenge_normal_"):
        target_id = safe_parse_callback_int(data, "pvp_challenge_normal_")
        if target_id is None:
            return
        await _send_challenge_with_wager(update, context, target_id, 0, query.message)
    elif data.startswith("pvp_challenge_wager_"):
        target_id = safe_parse_callback_int(data, "pvp_challenge_wager_")
        if target_id is None:
            return
        await _handle_challenge(update, context, target_id=target_id)


async def _handle_wager_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)

    parts = query.data.replace("spar_wager_", "").split("_")
    if len(parts) != 2:
        return
    
    target_id = int(parts[0])
    amount_str = parts[1]
    
    if amount_str == "custom":
        context.user_data["awaiting_wager"] = {"target_id": target_id}
        
        async with get_session_factory()() as session:
            challenger = await _get_player(update.effective_user.id, session)
            challenger_ss = challenger.spirit_stones if challenger else 0
            if challenger:
                lang = normalize_lang(challenger.language)
            
        custom_prompt = t(lang, "spar_wager_custom_prompt") + f"\n\n💰 *{t(lang, 'your_spirit_stones')}:* {challenger_ss}"
        
        await query.message.edit_text(
            custom_prompt,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_combat_cancel_challenge"), callback_data="pvp_sparring_menu")]])
        )
        return
    
    amount = int(amount_str)
    await _send_challenge_with_wager(update, context, target_id, amount, query.message)


async def process_wager_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    state = context.user_data.pop("awaiting_wager", None)
    if not state:
        return
        
    text = update.message.text.strip()
    if text.lower() == "/cancelar" or text.lower() == "/cancel":
        await update.message.reply_text(t(lang, "combat_cancelled"), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_sparring_menu")]]))
        return
        
    try:
        amount = int(text)
        if amount < 0:
            raise ValueError
    except ValueError:
        context.user_data["awaiting_wager"] = state
        await update.message.reply_text(t(lang, "spar_wager_invalid"))
        return
        
    await _send_challenge_with_wager(update, context, state["target_id"], amount, None, update.message)


async def _send_challenge_with_wager(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int, wager: int, query_msg=None, src_msg=None):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    challenger_id = update.effective_user.id
    
    async with get_session_factory()() as session:
        challenger = await _get_player(challenger_id, session)
        target = await _get_player(target_id, session)
        
        if not challenger or not target:
            msg = t(normalize_lang(update.effective_user.language_code), "ans_jogador_não_encontrado")
            if query_msg: await query_msg.edit_text(msg)
            elif src_msg: await src_msg.reply_text(msg)
            return

        lang = normalize_lang(challenger.language)
            
        if wager > 0:
            if challenger.spirit_stones < wager:
                msg = t(lang, "spar_wager_no_funds")
                if query_msg: await query_msg.edit_text(msg)
                elif src_msg: await src_msg.reply_text(msg)
                return
            
            max_wager_challenger = int(challenger.spirit_stones * 0.5)
            max_wager_target = int(target.spirit_stones * 0.5)
            
            if wager > max_wager_challenger:
                msg = t(lang, "spar_wager_limit", limit=max_wager_challenger)
                if query_msg: await query_msg.edit_text(msg)
                elif src_msg: await src_msg.reply_text(msg)
                return
                
            if target.spirit_stones < wager:
                msg = t(lang, "spar_wager_target_no_funds")
                if query_msg: await query_msg.edit_text(msg)
                elif src_msg: await src_msg.reply_text(msg)
                return
                
            if wager > max_wager_target:
                msg = t(lang, "spar_wager_target_limit")
                if query_msg: await query_msg.edit_text(msg)
                elif src_msg: await src_msg.reply_text(msg)
                return
                
        challenger_name = escape_markdown(get_display_name(challenger))
        target_name = escape_markdown(get_display_name(target))
        challenger_realm = get_realm_display(challenger.realm, challenger.sub_layer)
        
        challenge_key = f"pvp_pending_{challenger_id}_{target_id}"
        context.bot_data[challenge_key] = {
            "challenger_id": challenger_id,
            "target_id": target_id,
            "wager": wager,
            "created_at": datetime.now(timezone.utc),
        }
        await session.commit()
        
    if wager > 0:
        challenger_text = t(lang, "combat_sparring_challenge_source_wager", target_name=target_name, wager=wager)
        target_text = t(lang, "combat_sparring_challenge_target_wager", challenger_name=challenger_name, challenger_realm=challenger_realm, target_name=target_name, wager=wager)
    else:
        challenger_text = t(lang, "combat_sparring_challenge_source", target_name=target_name)
        target_text = t(lang, "combat_sparring_challenge_target", challenger_name=challenger_name, challenger_realm=challenger_realm, target_name=target_name)
        
    challenger_kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_combat_cancel_challenge"), callback_data=f"pvp_decline_{challenger_id}_{target_id}")]])
    target_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(lang, "btn_combat_accept"), callback_data=f"pvp_accept_{challenger_id}_{target_id}"),
            InlineKeyboardButton(t(lang, "btn_combat_decline"), callback_data=f"pvp_decline_{challenger_id}_{target_id}"),
        ],
    ])
    
    if query_msg:
        await query_msg.edit_text(challenger_text, parse_mode="Markdown", reply_markup=challenger_kb)
    elif src_msg:
        await src_msg.reply_text(challenger_text, parse_mode="Markdown", reply_markup=challenger_kb)
        
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=target_text,
            parse_mode="Markdown",
            reply_markup=target_kb,
        )
    except Exception:
        pass
        
    if context.job_queue:
        context.job_queue.run_once(
            _expire_challenge,
            when=CHALLENGE_EXPIRY_SECONDS,
            data={"key": challenge_key, "chat_id": challenger_id},
            name=challenge_key,
        )


async def _expire_challenge(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    key = job_data["key"]
    if key in context.bot_data:
        del context.bot_data[key]


async def _handle_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)

    parts = query.data.replace("pvp_accept_", "").split("_")
    if len(parts) != 2:
        return

    challenger_id = int(parts[0])
    target_id = int(parts[1])
    user_id = update.effective_user.id

    if user_id != target_id:
        await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_apenas_o_desafiado_pode"), show_alert=True)
        return

    challenge_key = f"pvp_pending_{challenger_id}_{target_id}"
    pending = context.bot_data.get(challenge_key)

    if not pending:
        await query.message.edit_text(
            t(lang, "combat_sparring_expired"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")]]),
        )
        return

    del context.bot_data[challenge_key]
    wager = pending.get("wager", 0)

    async with get_session_factory()() as session:
        # Use simple get for non-wager matches, but lock rows if it's a wager
        if wager > 0:
            stmt = select(Player).where(Player.telegram_id.in_([challenger_id, target_id])).with_for_update()
            players_result = (await session.execute(stmt)).scalars().all()
            player_map = {p.telegram_id: p for p in players_result}
            challenger = player_map.get(challenger_id)
            target = player_map.get(target_id)
        else:
            challenger = await _get_player(challenger_id, session)
            target = await _get_player(target_id, session)

        if not challenger or not target:
            await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_jogador_não_encontrado"), show_alert=True)
            return

        lang = normalize_lang(target.language)

        if wager > 0:
            if challenger.spirit_stones < wager or target.spirit_stones < wager:
                await safe_answer(query, t(lang, "spar_wager_target_no_funds"), show_alert=True)
                return
            challenger.spirit_stones -= wager
            target.spirit_stones -= wager

        atk_data = await _build_fighter(session, challenger)
        def_data = await _build_fighter(session, target)

        result = simulate_combat(atk_data, def_data, mode="sparring")

        narration = generate_combat_narration(result, atk_data["name"], def_data["name"], lang=lang)

        reward = int(wager * 2 * 0.95) if wager > 0 else 0
        combat_log = CombatLog(
            attacker_id=challenger_id,
            defender_id=target_id,
            mode="sparring",
            winner_id=result["winner_id"],
            wager_amount=wager,
            wager_winner_id=result["winner_id"] if wager > 0 else None,
            rounds_data={"rounds": result["rounds"]},
            spirit_stones_reward=result["spirit_stones_reward"] + reward,
        )
        session.add(combat_log)

        if result["winner_id"]:
            winner_player = challenger if result["winner_id"] == challenger_id else target
            winner_player.spirit_stones += result["spirit_stones_reward"] + reward
        elif wager > 0:
            # Refund in case of a tie
            challenger.spirit_stones += wager
            target.spirit_stones += wager

        challenger_won = result["winner_id"] == challenger_id
        mastery_msgs_challenger = await _award_mastery_xp(
            session, challenger_id,
            result.get("attacker_tech_activations", {}),
            challenger_won, lang,
        )
        mastery_msgs_target = await _award_mastery_xp(
            session, target_id,
            result.get("defender_tech_activations", {}),
            not challenger_won and result["winner_id"] is not None, lang,
        )

        from core.bp_engine import update_bp_mission
        from core.faction_engine import update_quest_progress as fac_quest_progress
        if challenger_won:
            await update_bp_mission(session, challenger_id, "win_sparring")
            await fac_quest_progress(session, challenger_id, "spar_win")
            await fac_quest_progress(session, challenger_id, "pvp_win")
        elif result["winner_id"] == target_id:
            await update_bp_mission(session, target_id, "win_sparring")
            await fac_quest_progress(session, target_id, "spar_win")
            await fac_quest_progress(session, target_id, "pvp_win")

        from core.body_tempering_engine import add_tempering_progress
        if challenger_won:
            add_tempering_progress(challenger, 8)
        elif result["winner_id"] == target_id:
            add_tempering_progress(target, 8)

        if wager > 0:
            if result["winner_id"] == challenger_id:
                mastery_msgs_challenger.append(t(lang, "combat_reward", amount=format_number(result["spirit_stones_reward"])))
                mastery_msgs_challenger.append(t(lang, "combat_sparring_wager_won", reward=format_number(reward)))
                mastery_msgs_target.append(t(lang, "combat_sparring_wager_lost", wager=format_number(wager)))
            elif result["winner_id"] == target_id:
                mastery_msgs_target.append(t(lang, "combat_reward", amount=format_number(result["spirit_stones_reward"])))
                mastery_msgs_target.append(t(lang, "combat_sparring_wager_won", reward=format_number(reward)))
                mastery_msgs_challenger.append(t(lang, "combat_sparring_wager_lost", wager=format_number(wager)))
            else:
                mastery_msgs_challenger.append(f"\n\n💸 {t(lang, 'spar_wager_tie_refund')}")
                mastery_msgs_target.append(f"\n\n💸 {t(lang, 'spar_wager_tie_refund')}")
        else:
            if result["winner_id"] == challenger_id:
                mastery_msgs_challenger.append(t(lang, "combat_reward", amount=format_number(result["spirit_stones_reward"])))
            elif result["winner_id"] == target_id:
                mastery_msgs_target.append(t(lang, "combat_reward", amount=format_number(result["spirit_stones_reward"])))

        from core.quest_engine import track_quest
        await track_quest(session, challenger_id, "sparring")
        await track_quest(session, target_id, "sparring")

        # Apply persistent HP drain to both players
        atk_dmg = result.get("attacker_damage_taken", 0)
        def_dmg = result.get("defender_damage_taken", 0)
        # BUGFIX 2026-07-26: reconcile effective combat-pool damage → raw current_hp.
        apply_hp_drain_scaled(challenger, atk_dmg, result.get("attacker_max_hp"))
        apply_hp_drain_scaled(target, def_dmg, result.get("defender_max_hp"))

        # HP status line for both
        # Onda B/C — post-spar HP shown == the arena/profile (Alma-routed, both fighters).
        from core.cultivator_soul import soul_max_hp, soul_current_hp
        c_max = await soul_max_hp(session, challenger)
        c_hp = soul_current_hp(challenger, c_max)
        t_max = await soul_max_hp(session, target)
        t_hp = soul_current_hp(target, t_max)
        hp_line = f"\n\n❤️ {escape_markdown(get_display_name(challenger))}: {format_number(c_hp)}/{format_number(c_max)} ({int(c_hp/c_max*100) if c_max else 0}%)"
        hp_line += f"\n❤️ {escape_markdown(get_display_name(target))}: {format_number(t_hp)}/{format_number(t_max)} ({int(t_hp/t_max*100) if t_max else 0}%)"
        narration += hp_line

        await session.commit()

    mastery_suffix_challenger = ("\n" + "\n".join(mastery_msgs_challenger)) if mastery_msgs_challenger else ""
    mastery_suffix_target = ("\n" + "\n".join(mastery_msgs_target)) if mastery_msgs_target else ""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_combat_new"), callback_data="pvp_sparring_menu")],
        [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")],
    ])

    # query user is always the target
    await query.message.edit_text(narration + mastery_suffix_target, parse_mode="Markdown", reply_markup=kb)

    try:
        await context.bot.send_message(
            chat_id=challenger_id,
            text=narration + mastery_suffix_challenger,
            parse_mode="Markdown",
            reply_markup=kb,
        )
    except Exception:
        pass



async def _handle_decline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)

    parts = query.data.replace("pvp_decline_", "").split("_")
    if len(parts) != 2:
        return

    challenger_id = int(parts[0])
    target_id = int(parts[1])
    user_id = update.effective_user.id

    if user_id != target_id and user_id != challenger_id:
        await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_este_desafio_não_é"), show_alert=True)
        return

    challenge_key = f"pvp_pending_{challenger_id}_{target_id}"
    if challenge_key in context.bot_data:
        del context.bot_data[challenge_key]

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if player:
            lang = normalize_lang(player.language)

    if user_id == challenger_id:
        await query.message.edit_text(
            t(lang, "combat_sparring_declined_source"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")],
            ]),
        )
    else:
        await query.message.edit_text(
            t(lang, "combat_sparring_declined_target"),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")],
            ]),
        )


# ─── Arena (v15.1.5 — DB-backed queue, shared with mini-app) ─────────────────
#
# Chat-side arena is now a thin adapter on top of `core.arena_engine`. The
# legacy chat-only `context.bot_data["arena_queue"]` is gone — both surfaces
# read/write the same `arena_queue` table. Match-time and duel-result DMs
# are delivered by the scheduler sweep (`arena_queue_sweep`) so the chat
# player gets notified even if matched against a mini-app player.
#
# The duel itself is turn-based and lives in DuelArenaModal (mini-app) — the
# chat player receives a DM with a "open mini-app" deeplink (Lei §1: player
# never stuck, always has a path forward).


async def _arena_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.arena_engine import get_queue_status

    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = normalize_lang(player.language)
        ranking = await _get_or_create_arena_ranking(session, player.telegram_id)
        status = await get_queue_status(session, player.telegram_id)
        await session.commit()

    text = (
        t(lang, "combat_arena_title") +
        f"{t(lang, 'combat_arena_elo')}*{ranking.elo_points}*\n"
        f"{t(lang, 'combat_arena_wins')}*{ranking.wins}*\n"
        f"{t(lang, 'combat_arena_losses')}*{ranking.losses}*\n"
        f"{t(lang, 'combat_arena_season')}*{CURRENT_SEASON}*\n\n"
        f"{t(lang, 'combat_pvp_chat_miniapp_hint')}\n\n"
    )

    state = status.get("state")
    if state == "waiting":
        # O ENCONTRO RAPIDO — o chat nao pode prometer "3 minutos" quando a
        # espera e' de 30 s. `pool_empty` so' chega com a flag ligada; sem ela,
        # a linha de sempre, com os mesmos parametros de sempre.
        if status.get("pool_empty"):
            text += t(lang, "combat_arena_queue_solo",
                      secs=int(status.get("remaining_seconds") or 0))
        else:
            text += t(
                lang, "combat_arena_queue",
                mins=ARENA_QUEUE_TIMEOUT_SECONDS // 60,
                range=ARENA_ELO_RANGE,
            )
        buttons = [
            [InlineKeyboardButton(t(lang, "btn_combat_dequeue"), callback_data="pvp_arena_cancel")],
        ]
    elif state == "matched":
        # The match already fired — chat player goes to mini-app to fight.
        text += t(lang, "combat_arena_matched_chat_hint",
                  opponent=status.get("opponent_dao_name", "?"))
        buttons = [
            [InlineKeyboardButton(t(lang, "btn_combat_arena_open_miniapp"),
                                  callback_data="pvp_arena_menu")],
        ]
    elif state == "expired":
        text += t(lang, "combat_arena_expired_chat_hint")
        buttons = [
            [InlineKeyboardButton(t(lang, "btn_combat_queue"), callback_data="pvp_arena_join")],
        ]
    else:
        text += t(lang, "combat_arena_info", mins=ARENA_QUEUE_TIMEOUT_SECONDS // 60)
        buttons = [
            [InlineKeyboardButton(t(lang, "btn_combat_queue"), callback_data="pvp_arena_join")],
        ]

    buttons.append([InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")])
    kb = InlineKeyboardMarkup(buttons)
    await _send_or_edit(update, text, kb)


async def _handle_arena_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.arena_engine import join_queue, try_match

    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if not player:
            return
        lang = normalize_lang(player.language)

        res = await join_queue(
            session, player,
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
        )

        if not res.get("ok"):
            reason = res.get("reason")
            if reason == "hp_too_low":
                await query.message.edit_text(
                    t(lang, "hp_too_low_combat"),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")],
                    ]),
                )
            elif reason == "in_active_duel":
                await safe_answer(
                    query,
                    t(lang, "combat_arena_in_active_duel"),
                    show_alert=True,
                )
            elif reason == "pvp_sealed":
                await safe_answer(query, t(lang, "combat_arena_pvp_sealed"), show_alert=True)
            else:
                await safe_answer(query, t(lang, "err_generic"), show_alert=True)
            await session.commit()
            return

        # Opportunistic synchronous match — same surface as legacy chat flow.
        await try_match(session)
        await session.commit()

    await _arena_menu(update, context)


async def _handle_arena_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.arena_engine import leave_queue

    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if player:
            lang = normalize_lang(player.language)
        await leave_queue(session, user_id)
        await session.commit()

    await query.message.edit_text(
        t(lang, "combat_arena_cancelled"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_combat_arena"), callback_data="pvp_arena_menu")],
            [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")],
        ]),
    )


# ─── Techniques ───────────────────────────────────────────────────────────────

async def _techniques_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = normalize_lang(player.language)
        stmt = (
            select(
                PlayerTechnique.technique_id,
                PlayerTechnique.mastery_level,
                PlayerTechnique.mastery_xp,
                PlayerTechnique.is_active_combat,
                TechniqueCatalog.name,
                TechniqueCatalog.emoji,
                TechniqueCatalog.effect_type,
                TechniqueCatalog.description,
                TechniqueCatalog.req_realm,
                TechniqueCatalog.tech_type,
                PlayerTechnique.grade,
                TechniqueCatalog.element,  # Track A item 6 — Art↔Root resonance flavor
            )
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
            .where(PlayerTechnique.player_id == player.telegram_id)
        )
        learned = (await session.execute(stmt)).all()

        # TEC-1 — artes do Núcleo de OUTRA casa estão TRANCADAS (cross-sect §3):
        # a lista mostra 🔒 e troca o botão de equipar pelo detalhe (a recusa
        # server-side em _handle_equip_technique é defense-in-depth). Gated:
        # flag OFF ⇒ set vazio SEM query — main byte-idêntico.
        _lib_locked_ids: set[int] = set()
        try:
            # TEC-3: o piso vem do engine (LOCK_TIER_FLOOR) — esta query é uma
            # SOMBRA de `is_library_locked` e tem de mover com ela, senão o 🔒
            # da lista mente sobre as artes do Ancião/Oculta.
            from core.sect_library_engine import LOCK_TIER_FLOOR as _lib_floor
            from core.sect_library_engine import biblioteca_on as _lib_on
            if _lib_on() and learned:
                _lrows = (await session.execute(
                    select(TechniqueCatalog.id, TechniqueCatalog.sect_key).where(
                        TechniqueCatalog.id.in_([r[0] for r in learned]),
                        TechniqueCatalog.library_tier >= _lib_floor,
                        TechniqueCatalog.sect_key.isnot(None),
                    )
                )).all()
                _lib_locked_ids = {int(r[0]) for r in _lrows if r[1] != player.sect_id}
        except Exception:
            _lib_locked_ids = set()

        # v16.4c — the learnable/locked catalog excludes house signature arts
        # (sect_key): those are learned via the Sect Hall (rank-gated, no scroll),
        # not this scroll menu. Learned sect arts still show (from `learned` above).
        stmt_all = select(TechniqueCatalog).where(
            TechniqueCatalog.sect_key.is_(None)
        ).order_by(TechniqueCatalog.req_realm)
        all_techs = (await session.execute(stmt_all)).scalars().all()

        scrolls_stmt = select(PlayerInventory).where(
            PlayerInventory.player_id == player.telegram_id,
            PlayerInventory.item_type == "technique_scroll",
            PlayerInventory.quantity > 0,
        )
        scrolls = (await session.execute(scrolls_stmt)).scalars().all()

        # Dao fragments: {dao_law_id: fragments_count}
        dao_frags_rows = (await session.execute(
            select(PlayerDaoFragment).where(PlayerDaoFragment.player_id == player.telegram_id)
        )).scalars().all()
        dao_frags = {r.dao_law_id: r.fragments_count for r in dao_frags_rows}

        # Dao law names: {id: "emoji name"}
        dao_laws_rows = (await session.execute(select(DaoLawCatalog))).scalars().all()
        dao_laws = {d.id: d for d in dao_laws_rows}

        await session.commit()

    learned_ids = {row[0] for row in learned}

    # Group learned techniques by type
    combat_learned = [r for r in learned if r[9] == "combat"]
    meditation_learned = [r for r in learned if r[9] == "meditation"]
    interior_learned = [r for r in learned if r[9] == "interior"]

    max_combat = get_max_combat_techniques(player.realm)
    active_combat_count = sum(1 for r in combat_learned if r[3])

    # Track A item 6 — Art↔Root resonance (disclosure-only flavor, zero modifier).
    from core.root_engine import get_root_elements
    from core.technique_engine import technique_root_resonance
    root_set = set(get_root_elements(player))

    text = t(lang, "combat_tech_title")

    def _render_learned_row(row):
        tech_id, mastery, mastery_xp, is_active, name, emoji, effect_type, desc, req_realm, tech_type, grade, element = row
        # 名 2026-09-14 — COLUNA desempacotada, nao atributo: o varredor de
        # `.name` nao via isto e a lista de artes APRENDIDAS saia crua.
        name = catalog_text(lang, "tech", tech_id, "name", name)
        desc = catalog_text(lang, "tech", tech_id, "desc", desc)
        status = t(lang, "combat_tech_equipped") if is_active else t(lang, "combat_tech_unequipped")
        # TEC-1 — o estado trancado É dito (Lei §1; set vazio com flag OFF).
        if tech_id in _lib_locked_ids and not is_active:
            status = "🔒 " + t(lang, "lib_tech_locked_status")
        stage = get_mastery_stage(mastery)
        next_stage = MASTERY_STAGES.get(mastery + 1)
        next_xp = str(next_stage["xp_req"]) if next_stage else t(lang, "technique_mastery_maxed")
        stage_name = t(lang, f"technique_mastery_stage_{mastery}")
        grade_info = get_grade_info(grade)
        grade_name = t(lang, f"technique_grade_{grade}")
        # N-28: catalog `name` may contain `*`/`_` (e.g. an i18n localized variant)
        # which would break Markdown bold and produce a Telegram parse error.
        name = escape_markdown(name)
        line = f"{emoji} *{name}* — {status}\n"
        line += f"  {stage['emoji']} {stage_name} ({mastery_xp}/{next_xp} XP) ×{stage['mult']}\n"
        # 内功 (report do [jogador] 2026-08-11) — a tela DIZ como esta arte ganha
        # Compreensão. Antes não dizia, e para as internas/de meditação a única
        # fonte era absorver um pergaminho repetido: o jogador concluía, com
        # razão, que "não tem como ganhar XP" (Lei §1).
        if next_stage:
            from core.technique_engine import technique_gain_key
            line += f"  {t(lang, technique_gain_key(tech_type))}\n"
        if grade != "common":
            line += f"  {grade_info['emoji']} {grade_name} ×{grade_info['mult']}\n"
        # Track A item 6 — resonance line only when the art's element is in the root
        # (compact: most arts won't match a 1-3 element root). Pure flavor, no number.
        reson = technique_root_resonance(element, root_set)
        if reson:
            el_name = t(lang, f"root_el_{reson['element']}")
            line += f"  {reson['emoji']} {t(lang, 'tech_root_resonance', element=el_name)}\n"

        next_g = get_next_grade(grade)
        if next_g:
            reqs = GRADE_UPGRADE_REQS.get(next_g)
            if reqs and mastery < reqs["min_mastery"]:
                g_info = get_grade_info(next_g)
                g_name = t(lang, f"technique_grade_{next_g}")
                extras = ""
                if reqs.get("stones"): extras += f" | {reqs['stones']} 🪨"
                # TEC-2 — display = custo real (o mesmo helper que o débito).
                from core.scroll_economy_engine import grade_scroll_cost as _sgc
                _sc = _sgc(int(reqs.get("scrolls", 0) or 0))
                if _sc: extras += f" | {_sc} 📜"
                if reqs.get("pill"): extras += f" | 1 💊"
                if reqs.get("requires_tribulation"): extras += f" | ⚡"
                line += t(lang, "tech_upgrade_locked", grade=f"{g_info['emoji']} {g_name}", mastery=reqs["min_mastery"], extras=extras) + "\n"
        return line

    # ── Combat techniques ──
    if combat_learned:
        text += t(lang, "tech_section_combat", active=active_combat_count, max=max_combat)
        for row in combat_learned:
            text += _render_learned_row(row)
        # Track A item 6 — disclose the already-enforced loadout cap honestly
        # (the Sea of Qi caps active arts; it grows with the realm). No fake %.
        text += t(lang, "tech_loadout_cap_hint", max=max_combat) + "\n"
        text += "\n"

    # ── Meditation techniques ──
    if meditation_learned:
        text += t(lang, "tech_section_meditation")
        for row in meditation_learned:
            text += _render_learned_row(row)
        text += "\n"

    # ── Interior techniques ──
    if interior_learned:
        text += t(lang, "tech_section_interior")
        for row in interior_learned:
            text += _render_learned_row(row)
        text += "\n"

    if not learned:
        text += t(lang, "combat_tech_empty")

    def _dao_status(tech) -> str:
        """Return empty string if Dao requirement met, else a warning tag."""
        if not tech.required_dao_law_id:
            return ""
        law = dao_laws.get(tech.required_dao_law_id)
        # N-28: same escape — DaoLawCatalog.name is free text catalog data.
        law_name_safe = escape_markdown(law.name) if law else f"Dao #{tech.required_dao_law_id}"
        law_label = f"{law.emoji} {law_name_safe}" if law else law_name_safe
        current = dao_frags.get(tech.required_dao_law_id, 0)
        if current >= tech.required_dao_insight:
            return f" ☯️ {law_label} ✅"
        return f" ☯️ {law_label} {current}/{tech.required_dao_insight}"

    # N-30 (Sprint v14.3): [jogador] reported 2026-05-08 "não consigo
    # equipar Boundless Evasion — fala que requer dao 6, mas já to avancado em
    # todos os Daos". Investigation: tech requires fragments of *Eternal Dao*
    # (Supreme Dao Law id=6, separate system from 3000 Dao Paths and Heavenly
    # Daos). Player meditated celestial_dao (heavenly_only=True) which only
    # discovers Heavenly laws — never grants Supreme fragments. Surface a
    # one-liner footer so any player with at-least-one locked-by-dao tech
    # sees the path forward without having to find /dao in the help.
    _has_dao_locked_tech = any(
        t_.required_dao_law_id and (dao_frags.get(t_.required_dao_law_id, 0) < (t_.required_dao_insight or 0))
        for t_ in all_techs
    )

    TYPE_ICONS = {"combat": "⚔️", "meditation": "🧘", "interior": "🏔️"}

    learnable = [
        t_ for t_ in all_techs
        if t_.id not in learned_ids
        and player.realm >= t_.req_realm
        and (t_.req_spirit_root is None or player.spirit_root <= t_.req_spirit_root)
    ]
    if learnable:
        text += t(lang, "combat_tech_learnable")
        for tech in learnable:
            has_scroll = any(s.item_id == tech.id for s in scrolls)
            scroll_status = t(lang, "combat_tech_has_scroll") if has_scroll else t(lang, "combat_tech_no_scroll")
            dao_tag = _dao_status(tech)
            type_icon = TYPE_ICONS.get(tech.tech_type, "⚔️")
            text += f"{tech.emoji} *{escape_markdown(_cname(lang, 'tech', tech))}* {type_icon} — {t(lang, 'combat_tech_req')}{REALM_NAMES[tech.req_realm]} [{scroll_status}]{dao_tag}\n"

    learnable_ids = {t_.id for t_ in learnable}
    locked = [t_ for t_ in all_techs if t_.id not in learned_ids and t_.id not in learnable_ids]

    # Telegram caps messages at 4096 chars. Players who learned many techniques
    # (esp. high realms with maxed mastery + grade upgrade hints) blow past this
    # — `_send_or_edit` then silently swallows BadRequest("Message_too_long")
    # and the user sees the click do nothing. [jogador] reported this
    # 2026-05-02. Budget defensively: prefer the actionable sections (learned,
    # learnable, spare scrolls) and trim/skip Locked (ruído — só lista o que
    # NÃO PODE aprender ainda).
    MSG_BUDGET = 3800

    locked_text = ""
    if locked:
        locked_text = t(lang, "combat_tech_locked")
        for tech in locked:
            dao_tag = _dao_status(tech)
            type_icon = TYPE_ICONS.get(tech.tech_type, "⚔️")
            locked_text += f"{tech.emoji} {escape_markdown(_cname(lang, 'tech', tech))} {type_icon} — {t(lang, 'combat_tech_req')}{REALM_NAMES[tech.req_realm]}{dao_tag}\n"

    # Spare scrolls: player already learned the technique but still has the scroll
    spare_scrolls = [s for s in scrolls if s.item_id in learned_ids]
    spare_text = ""
    if spare_scrolls:
        spare_text = t(lang, "combat_tech_spare_scrolls")
        for s in spare_scrolls:
            tech_obj = next((t_ for t_ in all_techs if t_.id == s.item_id), None)
            name_str = escape_markdown(tech_obj.name) if tech_obj else f"#{s.item_id}"
            emoji_str = tech_obj.emoji if tech_obj else "📜"
            spare_text += f"{emoji_str} {name_str} ×{s.quantity} — ✅ {t(lang, 'combat_tech_spare_known')}\n"

    # Spare scrolls have action buttons (absorb / discard) — append before
    # locked so they're never dropped silently.
    if len(text) + len(spare_text) <= MSG_BUDGET:
        text += spare_text
    else:
        text += t(lang, "combat_tech_truncated", fallback="\n_… mensagem demasiado longa, ver botões abaixo._\n")

    if len(text) + len(locked_text) <= MSG_BUDGET:
        text += locked_text
    elif locked:
        # Skip the locked block silently — buttons aren't generated for it
        # anyway. Players see the count via the "(req. realm X)" hints in
        # learnable, which is enough info.
        pass

    # N-30: footer hint when at least one tech is locked by a Supreme Dao
    # fragment requirement. Tells the player WHERE to farm — `/dao` meditation
    # types are the only path to Supreme fragments (`celestial_dao` doesn't
    # count, it's `heavenly_only`).
    if _has_dao_locked_tech:
        hint = t(lang, "combat_tech_dao_lock_hint")
        if len(text) + len(hint) + 2 <= MSG_BUDGET:
            text += "\n" + hint

    # Final defensive clamp — Markdown can still render slightly larger than
    # raw chars due to entity tags. Keep some headroom under the hard limit.
    if len(text) > 4000:
        # N-28: a naive cut at 3950 can land mid-`*bold*` and leave an
        # unclosed `*`, which Telegram rejects with "can't parse entities".
        # Cut on a newline whenever possible AND ensure no odd count of `*`
        # / `_` survives the cut (drop the trailing line if it would).
        text = text[:3950]
        nl = text.rfind("\n")
        if nl > 3000:
            text = text[:nl]
        if text.count("*") % 2 != 0:
            text = text.rsplit("*", 1)[0]
        if text.count("_") % 2 != 0:
            text = text.rsplit("_", 1)[0]
        text += "\n… (truncado)"

    buttons = []

    for row in learned:
        # 12-col row (item-6 added TechniqueCatalog.element for resonance); this
        # loop ignores element — name it _element so the unpack stays in lockstep
        # with the query + _render_learned_row (was 11 → ValueError crash for [jogador]).
        tech_id, mastery, _mxp, is_active, name, emoji, _eff, _desc, _realm, tech_type, grade, _element = row
        row_btns = []
        if is_active:
            row_btns.append(InlineKeyboardButton(f"{t(lang, 'combat_tech_btn_unequip')} {emoji} {name}", callback_data=f"pvp_unequip_{tech_id}"))
        elif tech_id in _lib_locked_ids:
            # TEC-1 — arte trancada: o botão vira o 🔒 que abre o detalhe
            # (nunca um botão morto — Lei §1; com flag OFF o set é vazio).
            row_btns.append(InlineKeyboardButton(f"🔒 {emoji} {name}", callback_data=f"pvp_techinfo_{tech_id}"))
        else:
            row_btns.append(InlineKeyboardButton(f"{t(lang, 'combat_tech_btn_equip')} {emoji} {name}", callback_data=f"pvp_equip_{tech_id}"))
        # M-10: detail card for learned technique — players asked for the
        # description/effect to remain visible after learning, not only on the
        # scroll preview.
        row_btns.append(InlineKeyboardButton("ℹ️", callback_data=f"pvp_techinfo_{tech_id}"))
        buttons.append(row_btns)

        # Grade upgrade button
        next_g = get_next_grade(grade)
        if next_g:
            reqs = GRADE_UPGRADE_REQS.get(next_g)
            if reqs and mastery >= reqs["min_mastery"]:
                grade_emoji = get_grade_info(next_g)["emoji"]
                grade_label = t(lang, f"technique_grade_{next_g}")
                buttons.append([InlineKeyboardButton(
                    f"⬆️ {grade_emoji} {grade_label} — {emoji} {name}",
                    callback_data=f"pvp_grade_{tech_id}",
                )])

    for tech in learnable:
        has_scroll = any(s.item_id == tech.id for s in scrolls)
        dao_met = (not tech.required_dao_law_id) or (dao_frags.get(tech.required_dao_law_id, 0) >= tech.required_dao_insight)
        if has_scroll and dao_met:
            buttons.append([InlineKeyboardButton(
                f"{t(lang, 'combat_tech_btn_learn')} {tech.emoji} {_cname(lang, 'tech', tech)}",
                callback_data=f"pvp_learn_{tech.id}",
            )])

    for s in spare_scrolls:
        tech_obj = next((t_ for t_ in all_techs if t_.id == s.item_id), None)
        name_str = tech_obj.name if tech_obj else f"#{s.item_id}"
        emoji_str = tech_obj.emoji if tech_obj else "📜"
        buttons.append([
            InlineKeyboardButton(
                f"{t(lang, 'combat_tech_btn_absorb_scroll')} {emoji_str} {name_str}",
                callback_data=f"pvp_absorb_scroll_{s.item_id}",
            ),
            InlineKeyboardButton(
                f"🗑️ {t(lang, 'combat_tech_btn_discard_scroll')}",
                callback_data=f"pvp_discard_scroll_{s.item_id}",
            ),
        ])
        if s.quantity > 1:
            buttons.append([InlineKeyboardButton(
                f"📖📖 {t(lang, 'combat_tech_btn_absorb_all')} (×{s.quantity})",
                callback_data=f"pvp_absorb_all_{s.item_id}",
            )])

    # TEC-2 — a porta do DESTINO do pergaminho (doar/queimar). Gated: com a flag
    # OFF nenhum botão scr_ é emitido (main byte-idêntico). Vive aqui e não na
    # lista acima porque a lista só oferece ação a pergaminho APRENDIDO — o ecrã
    # novo cobre a arca inteira, incl. o pergaminho inaprendível que hoje não
    # tem botão nenhum em superfície alguma (Lei §1).
    try:
        from core.scroll_economy_engine import escassez_on as _scr_on
        if _scr_on() and scrolls:
            buttons.append([InlineKeyboardButton(
                f"📜 {t(lang, 'scr_entry_btn', n=len(scrolls))}",
                callback_data="scr_open_pvp",
            )])
    except Exception:
        logger.debug("scroll economy entry button failed", exc_info=True)

    buttons.append([InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")])
    kb = InlineKeyboardMarkup(buttons)
    await _send_or_edit(update, text, kb)


async def _handle_equip_technique(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)

    tech_id = safe_parse_callback_int(query.data, "pvp_equip_")
    if tech_id is None:
        return
    user_id = update.effective_user.id

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if not player:
            return
        lang = normalize_lang(player.language)

        tech = (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
        )).scalar_one_or_none()
        if not tech:
            return

        if player.realm < tech.req_realm:
            await safe_answer(query, t(lang, "ans_realm_insuficiente_tech"), show_alert=True)
            return
        if tech.req_spirit_root is not None and player.spirit_root > tech.req_spirit_root:
            await safe_answer(query, t(lang, "combat_tech_root_required"), show_alert=True)
            return

        # TEC-1 — arte do Núcleo de OUTRA casa está lockada (cross-sect §3):
        # recusa server-side (defense-in-depth; a disclosure visível vive na
        # lista, que rende 🔒 sem botão de equipar). Gated: OFF ⇒ inerte.
        try:
            from core.sect_library_engine import biblioteca_on, is_library_locked
            if biblioteca_on() and is_library_locked(tech, player):
                return
        except Exception:
            pass

        # F-8: Enforce combat technique equip limit
        if tech.tech_type == "combat":
            max_slots = get_max_combat_techniques(player.realm)
            active_count_stmt = (
                select(func.count())
                .select_from(PlayerTechnique)
                .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
                .where(
                    PlayerTechnique.player_id == user_id,
                    PlayerTechnique.is_active_combat == True,
                    TechniqueCatalog.tech_type == "combat",
                )
            )
            active_count = (await session.execute(active_count_stmt)).scalar() or 0
            if active_count >= max_slots:
                await safe_answer(query, t(lang, "tech_equip_limit_reached", max=max_slots), show_alert=True)
                return

        stmt = select(PlayerTechnique).where(
            PlayerTechnique.player_id == user_id,
            PlayerTechnique.technique_id == tech_id,
        )
        pt = (await session.execute(stmt)).scalar_one_or_none()
        if pt:
            pt.is_active_combat = True
            await session.commit()

    await _techniques_menu(update, context)


async def _handle_unequip_technique(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)

    tech_id = safe_parse_callback_int(query.data, "pvp_unequip_")
    if tech_id is None:
        return
    user_id = update.effective_user.id

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if player:
            lang = normalize_lang(player.language)
        stmt = select(PlayerTechnique).where(
            PlayerTechnique.player_id == user_id,
            PlayerTechnique.technique_id == tech_id,
        )
        pt = (await session.execute(stmt)).scalar_one_or_none()
        if pt:
            pt.is_active_combat = False
            await session.commit()

    await _techniques_menu(update, context)


async def _handle_learn_technique(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)

    tech_id = safe_parse_callback_int(query.data, "pvp_learn_")
    if tech_id is None:
        return
    user_id = update.effective_user.id

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if not player:
            return

        lang = normalize_lang(player.language)

        tech = (await session.execute(select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id))).scalar_one_or_none()
        if not tech:
            await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_técnica_não_encontrada"), show_alert=True)
            return

        if player.realm < tech.req_realm:
            await safe_answer(query, t(lang, "ans_realm_insuficiente_tech").format(req_realm=REALM_NAMES[tech.req_realm]), show_alert=True)
            return

        if tech.req_spirit_root is not None and player.spirit_root > tech.req_spirit_root:
            await safe_answer(query, t(lang, "combat_tech_root_required"), show_alert=True)
            return

        if tech.required_dao_law_id:
            frag = (await session.execute(
                select(PlayerDaoFragment).where(
                    PlayerDaoFragment.player_id == user_id,
                    PlayerDaoFragment.dao_law_id == tech.required_dao_law_id,
                )
            )).scalar_one_or_none()
            current_fragments = frag.fragments_count if frag else 0
            if current_fragments < tech.required_dao_insight:
                dao_law = (await session.execute(
                    select(DaoLawCatalog).where(DaoLawCatalog.id == tech.required_dao_law_id)
                )).scalar_one_or_none()
                dao_name = f"{dao_law.emoji} {dao_law.name}" if dao_law else "Dao Law"
                await safe_answer(query, 
                    t(lang, "ans_dao_req_not_met",
                      dao_name=dao_name,
                      required=tech.required_dao_insight,
                      current=current_fragments),
                    show_alert=True,
                )
                return

        scroll_stmt = select(PlayerInventory).where(
            PlayerInventory.player_id == user_id,
            PlayerInventory.item_type == "technique_scroll",
            PlayerInventory.item_id == tech_id,
            PlayerInventory.quantity > 0,
        )
        scroll = (await session.execute(scroll_stmt)).scalar_one_or_none()
        if not scroll:
            await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_não_tens_o_scroll"), show_alert=True)
            return

        existing = (await session.execute(
            select(PlayerTechnique).where(
                PlayerTechnique.player_id == user_id,
                PlayerTechnique.technique_id == tech_id,
            )
        )).scalar_one_or_none()

        if existing:
            await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_já_conheces_esta_técnica"), show_alert=True)
            return

        scroll.quantity -= 1
        if scroll.quantity <= 0:
            await session.delete(scroll)

        # F-8: Auto-equip if slot available for combat, always auto-equip for meditation/interior
        auto_equip = True
        if tech.tech_type == "combat":
            max_slots = get_max_combat_techniques(player.realm)
            active_combat = (await session.execute(
                select(func.count())
                .select_from(PlayerTechnique)
                .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
                .where(
                    PlayerTechnique.player_id == user_id,
                    PlayerTechnique.is_active_combat == True,
                    TechniqueCatalog.tech_type == "combat",
                )
            )).scalar() or 0
            if active_combat >= max_slots:
                auto_equip = False

        new_pt = PlayerTechnique(
            player_id=user_id,
            technique_id=tech_id,
            mastery_level=1,
            is_active_combat=auto_equip,
        )
        session.add(new_pt)
        await session.commit()

    await safe_answer(query, t(lang, "ans_tech_learned_success", emoji=tech.emoji, name=_cname(lang, "tech", tech)), show_alert=True)
    await _techniques_menu(update, context)


# ─── Grade Evolution (F-8) ───────────────────────────────────────────────────

async def _handle_grade_upgrade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    tech_id = safe_parse_callback_int(query.data, "pvp_grade_")
    if tech_id is None:
        return
    user_id = update.effective_user.id

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if not player:
            return
        lang = normalize_lang(player.language)

        pt = (await session.execute(
            select(PlayerTechnique).where(
                PlayerTechnique.player_id == user_id,
                PlayerTechnique.technique_id == tech_id,
            )
        )).scalar_one_or_none()
        if not pt:
            return

        tech = (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
        )).scalar_one_or_none()
        if not tech:
            return

        next_g = get_next_grade(pt.grade)
        if not next_g:
            await safe_answer(query, t(lang, "tech_grade_already_max"), show_alert=True)
            return

        reqs = GRADE_UPGRADE_REQS.get(next_g)
        if not reqs:
            return

        # Check mastery level
        if pt.mastery_level < reqs["min_mastery"]:
            await safe_answer(query, t(lang, "tech_grade_mastery_low", required=reqs["min_mastery"]), show_alert=True)
            return

        # Check spirit stones
        if player.spirit_stones < reqs["stones"]:
            await safe_answer(query, t(lang, "tech_grade_not_enough_stones", cost=reqs["stones"], have=player.spirit_stones), show_alert=True)
            return

        # Check scrolls (same technique scrolls from inventory)
        # TEC-2 — sob escassez o custo é dividido (Lei §1: com o faucet cortado,
        # 10 duplicatas de UMA arte seriam inalcançáveis). OFF ⇒ o valor original.
        from core.scroll_economy_engine import grade_scroll_cost
        scroll_cost = grade_scroll_cost(reqs["scrolls"])
        if scroll_cost > 0:
            scroll_inv = (await session.execute(
                select(PlayerInventory).where(
                    PlayerInventory.player_id == user_id,
                    PlayerInventory.item_type == "technique_scroll",
                    PlayerInventory.item_id == tech_id,
                    PlayerInventory.quantity >= scroll_cost,
                )
            )).scalar_one_or_none()
            if not scroll_inv:
                await safe_answer(query, t(lang, "tech_grade_not_enough_scrolls", cost=scroll_cost), show_alert=True)
                return

        # Check pill requirement
        pill_name = reqs.get("pill")
        pill_inv = None
        if pill_name:
            from database.models import PillCatalog
            pill_cat = (await session.execute(
                # 名-CRU: COMPARACAO com o nome canonico vindo da config de
                # requisitos (`reqs["pill"]`), nunca do cliente. Traduzir aqui
                # partiria a subida de grau em pt e es, calada.
                select(PillCatalog).where(PillCatalog.name == pill_name)
            )).scalar_one_or_none()
            if pill_cat:
                pill_inv = (await session.execute(
                    select(PlayerInventory).where(
                        PlayerInventory.player_id == user_id,
                        PlayerInventory.item_type == "pill",
                        PlayerInventory.item_id == pill_cat.id,
                        PlayerInventory.quantity > 0,
                    )
                )).scalar_one_or_none()
            if not pill_inv:
                await safe_answer(query, t(lang, "tech_grade_not_enough_pill", pill=pill_name), show_alert=True)
                return

        # Check tribulation requirement (for celestial grade)
        if reqs.get("requires_tribulation"):
            # ⚠️ Ate' 30/09 aqui estava `Tribulation.result`, uma coluna que NAO
            # existe (a coluna e' `outcome`): subir uma tecnica a celestial pelo
            # chat rebentava. A regra "passou a tribulacao" tem UM dono, o mesmo
            # do mini-app e do passe — e a PERFEITA conta.
            from database.models import Tribulation
            from core.tribulation_engine import tribulation_passed_clause
            trib = (await session.execute(
                select(Tribulation.id).where(
                    tribulation_passed_clause(user_id),
                ).limit(1)
            )).first()
            if not trib:
                await safe_answer(query, t(lang, "tech_grade_needs_tribulation"), show_alert=True)
                return

        # All requirements met — deduct costs
        player.spirit_stones -= reqs["stones"]
        if scroll_cost > 0:
            scroll_inv = (await session.execute(
                select(PlayerInventory).where(
                    PlayerInventory.player_id == user_id,
                    PlayerInventory.item_type == "technique_scroll",
                    PlayerInventory.item_id == tech_id,
                )
            )).scalar_one_or_none()
            scroll_inv.quantity -= scroll_cost
            if scroll_inv.quantity <= 0:
                await session.delete(scroll_inv)
        if pill_inv:
            pill_inv.quantity -= 1
            if pill_inv.quantity <= 0:
                await session.delete(pill_inv)

        old_g = pt.grade
        pt.grade = next_g
        await session.commit()

    # QoL-Feedback 2026-07-29 Item B (Lei §10): dizer o grau antes→depois.
    grade_info = get_grade_info(next_g)
    old_info = get_grade_info(old_g)
    await safe_answer(query, t(lang, "tech_grade_upgraded_delta",
                               emoji=tech.emoji, name=_cname(lang, "tech", tech),
                               old_grade_emoji=old_info["emoji"],
                               old_grade=t(lang, f"technique_grade_{old_g}"),
                               old_mult=old_info["mult"],
                               grade_emoji=grade_info["emoji"],
                               grade=t(lang, f"technique_grade_{next_g}"),
                               mult=grade_info["mult"]), show_alert=True)
    await _techniques_menu(update, context)


# ─── Ranking Arena ────────────────────────────────────────────────────────────

async def _ranking_arena(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if player:
            lang = normalize_lang(player.language)

        stmt = (
            select(ArenaRanking, Player.dao_name, Player.username, Player.display_name, Player.realm, Player.sub_layer, Player.shadow_mode)
            .join(Player, Player.telegram_id == ArenaRanking.player_id)
            .where(ArenaRanking.season == CURRENT_SEASON)
            .order_by(ArenaRanking.elo_points.desc())
            .limit(RANKING_PAGE_SIZE)
        )
        rows = (await session.execute(stmt)).all()
        await session.commit()

    medals = ["🥇", "🥈", "🥉"]

    text = t(lang, "combat_ranking_title", season=CURRENT_SEASON)

    if not rows:
        text += t(lang, "combat_ranking_empty")
    else:
        for i, (ranking, dao_name, username, display_name, realm, sub_layer, shadow_mode) in enumerate(rows):
            if i < len(medals):
                pos = medals[i]
            else:
                pos = f"`{i + 1}.`"

            raw_name = "???" if shadow_mode else (dao_name or username or display_name or "???")
            name = escape_markdown(raw_name)
            realm_display = get_realm_display(realm, sub_layer)
            text += f"{pos} *{name}* — 🏅 {ranking.elo_points} ELO\n"
            
            wl = t(lang, 'arena_wins_losses').split('/')
            w_str = wl[0].strip() if len(wl) > 1 else "W"
            l_str = wl[1].strip() if len(wl) > 1 else "L"
            
            text += f"   {realm_display} | {ranking.wins}{w_str} / {ranking.losses}{l_str}\n\n"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="pvp_main")],
    ])

    await _send_or_edit(update, text, kb)


# ─── Button Router ────────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def combat_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    data = query.data

    if data == "pvp_main":
        await safe_answer(query)
        await combat_command(update, context)
        return True
    elif data == "pvp_sparring_menu":
        await safe_answer(query)
        await _sparring_menu(update, context)
        return True
    elif data.startswith("pvp_ch_menu_"):
        await _handle_challenge_menu(update, context)
        return True
    elif data.startswith("pvp_challenge_normal_") or data.startswith("pvp_challenge_wager_"):
        await _route_challenge(update, context)
        return True
    elif data.startswith("pvp_challenge_"):
        await _handle_challenge(update, context)
        return True
    elif data.startswith("spar_wager_"):
        await _handle_wager_select(update, context)
        return True
    elif data.startswith("pvp_accept_"):
        await _handle_accept(update, context)
        return True
    elif data.startswith("pvp_decline_"):
        await _handle_decline(update, context)
        return True
    elif data == "pvp_ranking":
        await safe_answer(query)
        await _ranking_arena(update, context)
        return True
    elif data == "pvp_arena_menu":
        await safe_answer(query)
        await _arena_menu(update, context)
        return True
    elif data == "pvp_arena_join":
        await _handle_arena_join(update, context)
        return True
    elif data == "pvp_arena_cancel":
        await _handle_arena_cancel(update, context)
        return True
    elif data == "pvp_techniques_menu":
        await safe_answer(query)
        await _techniques_menu(update, context)
        return True
    elif data.startswith("pvp_techinfo_"):
        await _handle_technique_info(update, context)
        return True
    elif data.startswith("pvp_grade_"):
        await _handle_grade_upgrade(update, context)
        return True
    elif data.startswith("pvp_equip_"):
        await _handle_equip_technique(update, context)
        return True
    elif data.startswith("pvp_unequip_"):
        await _handle_unequip_technique(update, context)
        return True
    elif data.startswith("pvp_learn_"):
        await _handle_learn_technique(update, context)
        return True
    elif data.startswith("pvp_discard_scroll_"):
        await _handle_discard_scroll(update, context)
        return True
    elif data.startswith("pvp_absorb_all_"):
        await _handle_absorb_all_scrolls(update, context)
        return True
    elif data.startswith("pvp_absorb_scroll_"):
        await _handle_absorb_scroll(update, context)
        return True
    elif data == "npc_menu":
        await safe_answer(query)
        await _npc_menu(update, context)
        return True
    elif data.startswith("npc_st_"):
        await _npc_stance_menu(update, context)
        return True
    elif data.startswith("npc_ft_"):
        await _npc_focus_menu(update, context)
        return True
    elif data.startswith("npc_go_"):
        await _handle_npc_fight(update, context)
        return True

    return False


async def _handle_technique_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """M-10: detail card for a learned technique — name, grade, mastery, full
    description, requirements (realm + dao + spirit root). Triggered from the
    ℹ️ button in `_techniques_menu`."""
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id
    tech_id = safe_parse_callback_int(query.data, "pvp_techinfo_")
    if tech_id is None:
        return

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if not player:
            return
        lang = normalize_lang(player.language)

        tech = (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
        )).scalar_one_or_none()
        if not tech:
            await safe_answer(query, t(lang, "ans_tech_not_found"), show_alert=True)
            return

        pt = (await session.execute(
            select(PlayerTechnique).where(
                PlayerTechnique.player_id == player.telegram_id,
                PlayerTechnique.technique_id == tech_id,
            )
        )).scalar_one_or_none()

        dao_label = ""
        if tech.required_dao_law_id:
            law = (await session.execute(
                select(DaoLawCatalog).where(DaoLawCatalog.id == tech.required_dao_law_id)
            )).scalar_one_or_none()
            if law:
                dao_label = f"{law.emoji} {law.name}"

    stage = get_mastery_stage(pt.mastery_level if pt else 1)
    next_stage = MASTERY_STAGES.get((pt.mastery_level if pt else 1) + 1)
    next_xp = str(next_stage["xp_req"]) if next_stage else t(lang, "technique_mastery_maxed")
    stage_name = t(lang, f"technique_mastery_stage_{pt.mastery_level if pt else 1}")
    grade = pt.grade if pt else "common"
    grade_info = get_grade_info(grade)
    grade_name = t(lang, f"technique_grade_{grade}")
    type_label = t(lang, f"tech_type_{tech.tech_type}")

    desc = _cdesc(lang, "tech", tech) or t(lang, "combat_tech_no_desc")

    lines = [
        f"{tech.emoji} *{_cname(lang, 'tech', tech)}*",
        "—" * 20,
        t(lang, "tech_detail_type", type=type_label),
        t(lang, "tech_detail_grade", emoji=grade_info["emoji"], name=grade_name, mult=grade_info["mult"]),
        t(lang, "tech_detail_mastery",
            emoji=stage["emoji"], stage=stage_name,
            xp=(pt.mastery_xp if pt else 0), next_xp=next_xp, mult=stage["mult"]),
        "",
        f"📖 {desc}",
        "",
        t(lang, "tech_detail_req_realm", realm=REALM_NAMES[min(tech.req_realm, len(REALM_NAMES) - 1)]),
    ]
    if tech.effect_type:
        lines.append(t(lang, "tech_detail_effect", effect=tech.effect_type, value=getattr(tech, "effect_value", 0)))
    if dao_label:
        lines.append(t(lang, "tech_detail_req_dao", dao=dao_label, fragments=tech.required_dao_insight or 0))
    if tech.req_spirit_root is not None:
        from config import SPIRIT_ROOT_NAMES
        root_name = SPIRIT_ROOT_NAMES[min(tech.req_spirit_root, len(SPIRIT_ROOT_NAMES) - 1)]
        lines.append(t(lang, "tech_detail_req_root", root=root_name))

    # Track A item 6 — Art↔Root resonance disclosure (flavor only, zero modifier).
    from core.root_engine import get_root_elements
    from core.technique_engine import technique_root_resonance
    reson = technique_root_resonance(getattr(tech, "element", None), set(get_root_elements(player)))
    if reson:
        el_name = t(lang, f"root_el_{reson['element']}")
        lines.append("")
        lines.append(f"{reson['emoji']} {t(lang, 'tech_root_resonance', element=el_name)}")
        lines.append(t(lang, "tech_root_resonance_future"))

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="pvp_techniques_menu")]
    ])
    try:
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.warning("technique info edit failed: %s", e)


async def _handle_discard_scroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id
    tech_id = safe_parse_callback_int(query.data, "pvp_discard_scroll_")
    if tech_id is None:
        return

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if not player:
            return
        lang = normalize_lang(player.language)

        scroll_stmt = select(PlayerInventory).where(
            PlayerInventory.player_id == user_id,
            PlayerInventory.item_type == "technique_scroll",
            PlayerInventory.item_id == tech_id,
            PlayerInventory.quantity > 0,
        )
        scroll = (await session.execute(scroll_stmt)).scalar_one_or_none()
        if not scroll:
            await safe_answer(query, t(lang, "ans_scroll_not_found"), show_alert=True)
            return

        tech = (await session.execute(select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id))).scalar_one_or_none()
        stones_gained = (tech.req_realm + 1) * 50 if tech else 50
        player.spirit_stones += stones_gained
        scroll.quantity -= 1
        if scroll.quantity <= 0:
            await session.delete(scroll)
        await session.commit()

    await safe_answer(query, t(lang, "ans_scroll_discarded", stones=stones_gained), show_alert=True)
    await _techniques_menu(update, context)


async def _handle_absorb_scroll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id
    tech_id = safe_parse_callback_int(query.data, "pvp_absorb_scroll_")
    if tech_id is None:
        return

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if not player:
            return
        lang = normalize_lang(player.language)

        scroll = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == user_id,
                PlayerInventory.item_type == "technique_scroll",
                PlayerInventory.item_id == tech_id,
                PlayerInventory.quantity > 0,
            )
        )).scalar_one_or_none()
        if not scroll:
            await safe_answer(query, t(lang, "ans_scroll_not_found"), show_alert=True)
            return

        existing = (await session.execute(
            select(PlayerTechnique).where(
                PlayerTechnique.player_id == user_id,
                PlayerTechnique.technique_id == tech_id,
            )
        )).scalar_one_or_none()
        if not existing:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        tech = (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
        )).scalar_one_or_none()

        xp_table = {0: 50, 1: 50, 2: 100, 3: 100, 4: 200, 5: 200, 6: 400, 7: 400}
        xp_gain = xp_table.get(tech.req_realm, 750) if tech else 50
        existing.mastery_xp += xp_gain

        levelup_msg = ""
        while existing.mastery_level < 5:
            next_stage = MASTERY_STAGES.get(existing.mastery_level + 1)
            if next_stage and existing.mastery_xp >= next_stage["xp_req"]:
                existing.mastery_level += 1
                stage_name = t(lang, f"technique_mastery_stage_{existing.mastery_level}")
                stage_data = MASTERY_STAGES[existing.mastery_level]
                levelup_msg = t(lang, "inv_tech_absorb_levelup",
                                name=_cname(lang, "tech", tech), stage=stage_name,
                                mult=stage_data["mult"])
            else:
                break

        scroll.quantity -= 1
        if scroll.quantity <= 0:
            await session.delete(scroll)
        await session.commit()

    text = t(lang, "inv_tech_absorb", name=_cname(lang, "tech", tech), xp=xp_gain)
    if levelup_msg:
        text += "\n" + levelup_msg
    await safe_answer(query, text, show_alert=True)
    await _techniques_menu(update, context)


async def _handle_absorb_all_scrolls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user_id = update.effective_user.id
    tech_id = safe_parse_callback_int(query.data, "pvp_absorb_all_")
    if tech_id is None:
        return

    async with get_session_factory()() as session:
        player = await _get_player(user_id, session)
        if not player:
            return
        lang = normalize_lang(player.language)

        scroll = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == user_id,
                PlayerInventory.item_type == "technique_scroll",
                PlayerInventory.item_id == tech_id,
                PlayerInventory.quantity > 0,
            )
        )).scalar_one_or_none()
        if not scroll:
            await safe_answer(query, t(lang, "ans_scroll_not_found"), show_alert=True)
            return

        existing = (await session.execute(
            select(PlayerTechnique).where(
                PlayerTechnique.player_id == user_id,
                PlayerTechnique.technique_id == tech_id,
            )
        )).scalar_one_or_none()
        if not existing:
            await safe_answer(query, t(lang, "inv_item_not_found"), show_alert=True)
            return

        tech = (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
        )).scalar_one_or_none()

        qty = scroll.quantity
        xp_table = {0: 50, 1: 50, 2: 100, 3: 100, 4: 200, 5: 200, 6: 400, 7: 400}
        xp_per = xp_table.get(tech.req_realm, 750) if tech else 50
        total_xp = xp_per * qty
        existing.mastery_xp += total_xp

        levelup_msgs = []
        while existing.mastery_level < 5:
            next_stage = MASTERY_STAGES.get(existing.mastery_level + 1)
            if next_stage and existing.mastery_xp >= next_stage["xp_req"]:
                existing.mastery_level += 1
                stage_name = t(lang, f"technique_mastery_stage_{existing.mastery_level}")
                stage_data = MASTERY_STAGES[existing.mastery_level]
                levelup_msgs.append(t(lang, "inv_tech_absorb_levelup",
                                      name=_cname(lang, "tech", tech), stage=stage_name,
                                      mult=stage_data["mult"]))
            else:
                break

        scroll.quantity = 0
        await session.delete(scroll)
        await session.commit()

    text = t(lang, "combat_tech_absorbed_all", name=_cname(lang, "tech", tech), qty=qty, xp=total_xp)
    if levelup_msgs:
        text += "\n" + "\n".join(levelup_msgs)
    await safe_answer(query, text, show_alert=True)
    await _techniques_menu(update, context)


async def _npc_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = normalize_lang(player.language)

        stmt = select(PlayerNPCCooldown).where(PlayerNPCCooldown.player_id == player.telegram_id)
        cooldown_data = (await session.execute(stmt)).scalar_one_or_none()

    text = t(lang, "npc_menu_title") + "\n\n"

    cooldown_text = ""
    if cooldown_data and cooldown_data.last_npc_fight:
        now = datetime.now(timezone.utc)
        elapsed = (now - cooldown_data.last_npc_fight.replace(tzinfo=timezone.utc)).total_seconds()
        if elapsed < 1800:
            rem = int((1800 - elapsed) / 60)
            cooldown_text = t(lang, "npc_cooldown_msg", mins=rem) + "\n\n"

    text += cooldown_text

    buttons = []
    for diff, data in NPC_DIFFICULTIES.items():
        btn_text = f"{data['emoji']} {t(lang, f'npc_difficulty_{diff}')} (-{data['qi_cost']} Qi)"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"npc_st_{diff}")])

    buttons.append([InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="nav_combate")])
    kb = InlineKeyboardMarkup(buttons)
    await _send_or_edit(update, text, kb)


async def _npc_stance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show stance selection after choosing NPC difficulty."""
    query = update.callback_query
    await safe_answer(query)
    diff = query.data.replace("npc_st_", "")
    if diff not in NPC_DIFFICULTIES:
        return

    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language)

    diff_data = NPC_DIFFICULTIES[diff]
    text = (
        f"{diff_data['emoji']} *{t(lang, f'npc_difficulty_{diff}')}*\n\n"
        + t(lang, "stance_choose_title") + "\n\n"
        + t(lang, "stance_offensive_desc") + "\n"
        + t(lang, "stance_balanced_desc") + "\n"
        + t(lang, "stance_defensive_desc")
    )

    buttons = []
    for stance_key, st_data in STANCES.items():
        btn_text = f"{st_data['emoji']} {t(lang, f'stance_{stance_key}')}"
        # callback: npc_ft_{diff}_{stance_initial}
        stance_code = stance_key[0]  # o, b, d
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"npc_ft_{diff}_{stance_code}")])

    buttons.append([InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="npc_menu")])
    kb = InlineKeyboardMarkup(buttons)
    await _send_or_edit(update, text, kb)


STANCE_CODE_MAP = {"o": "offensive", "b": "balanced", "d": "defensive"}


async def _npc_focus_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show technique focus selection after choosing stance."""
    query = update.callback_query
    await safe_answer(query)
    # callback: npc_ft_{diff}_{stance_code}
    parts = query.data.replace("npc_ft_", "").rsplit("_", 1)
    if len(parts) != 2:
        return
    diff, stance_code = parts
    if diff not in NPC_DIFFICULTIES or stance_code not in STANCE_CODE_MAP:
        return

    stance = STANCE_CODE_MAP[stance_code]
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = normalize_lang(player.language)

        # Get active combat techniques
        active_tech_stmt = (
            select(PlayerTechnique, TechniqueCatalog)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
            .where(
                PlayerTechnique.player_id == player.telegram_id,
                PlayerTechnique.is_active_combat == True,
            )
        )
        tech_rows = (await session.execute(active_tech_stmt)).all()

    st_data = STANCES[stance]
    text = (
        f"{st_data['emoji']} *{t(lang, f'stance_{stance}')}*\n\n"
        + t(lang, "focus_choose_title")
    )

    buttons = []
    # "No focus" option — balanced technique usage
    buttons.append([InlineKeyboardButton(
        f"⚖️ {t(lang, 'focus_none')}",
        callback_data=f"npc_go_{diff}_{stance_code}_0"
    )])

    for pt, tc in tech_rows:
        btn_text = f"{tc.emoji} {_cname(lang, 'tech', tc)}"
        buttons.append([InlineKeyboardButton(
            btn_text,
            callback_data=f"npc_go_{diff}_{stance_code}_{tc.id}"
        )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data=f"npc_st_{diff}")])
    kb = InlineKeyboardMarkup(buttons)
    await _send_or_edit(update, text, kb)


async def _handle_npc_fight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = normalize_lang(getattr(update.effective_user, 'language_code', None))
    query = update.callback_query
    await safe_answer(query)

    # callback: npc_go_{diff}_{stance_code}_{focus_tech_id}
    raw = query.data.replace("npc_go_", "")
    parts = raw.split("_")
    if len(parts) != 3:
        return
    diff, stance_code, focus_str = parts
    if diff not in NPC_DIFFICULTIES or stance_code not in STANCE_CODE_MAP:
        return
    stance = STANCE_CODE_MAP[stance_code]
    focus_tech_id = int(focus_str) if focus_str.isdigit() else 0

    user_id = update.effective_user.id
    diff_data = NPC_DIFFICULTIES[diff]

    async with get_session_factory()() as session:
        # Use with_for_update() to prevent stale player reads (race condition guard)
        from database.models import Player
        stmt = select(Player).where(Player.telegram_id == user_id).with_for_update()
        result = await session.execute(stmt)
        player = result.scalar_one_or_none()
        if not player:
            return

        lang = normalize_lang(player.language)

        # Block combat if HP is 0
        if get_current_hp(player) <= 0:
            await query.message.edit_text(
                t(lang, "hp_too_low_combat"),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="npc_menu")]]),
            )
            return

        stmt = select(PlayerNPCCooldown).where(PlayerNPCCooldown.player_id == player.telegram_id)
        cooldown_data = (await session.execute(stmt)).scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if cooldown_data:
            if cooldown_data.last_reset_date != now.date():
                cooldown_data.fights_today = 0
                cooldown_data.last_reset_date = now.date()

            if cooldown_data.last_npc_fight:
                elapsed = (now - cooldown_data.last_npc_fight.replace(tzinfo=timezone.utc)).total_seconds()
                if elapsed < 1800:
                    rem = int((1800 - elapsed) / 60)
                    await safe_answer(query, t(lang, "npc_cooldown_msg", mins=rem), show_alert=True)
                    return
        else:
            cooldown_data = PlayerNPCCooldown(
                player_id=player.telegram_id,
                fights_today=0,
                last_reset_date=now.date()
            )
            session.add(cooldown_data)

        qi_cost = diff_data["qi_cost"]
        if player.qi < qi_cost:
            await safe_answer(query, t(lang, "npc_qi_insufficient", cost=qi_cost), show_alert=True)
            return

        # Deduct Qi
        player.qi -= qi_cost

        # Set cooldown
        cooldown_data.last_npc_fight = now
        cooldown_data.fights_today += 1

        atk_data = await _build_fighter(session, player)
        apply_stance_and_focus(atk_data, stance, focus_tech_id)
        npc = generate_npc_fighter(difficulty=diff, player_realm=player.realm, lang=lang)

        result = simulate_combat(atk_data, npc, mode="sparring")

        # Stance header in narration
        st_data = STANCES[stance]
        stance_label = f"{st_data['emoji']} {t(lang, f'stance_{stance}')}"
        focus_label = ""
        if focus_tech_id:
            for tech in atk_data.get("techniques", []):
                if tech["id"] == focus_tech_id:
                    focus_label = f" | 🎯 {tech['name']}"
                    break

        narration = t(lang, "npc_fight_intro", npc_name=npc['name']) + "\n"
        narration += t(lang, "combat_stance_display", stance=stance_label, focus=focus_label) + "\n\n"
        narration += generate_combat_narration(result, atk_data["name"], npc["name"], lang=lang)

        mastery_msgs = await _award_mastery_xp(
            session, player.telegram_id,
            result.get("attacker_tech_activations", {}),
            result["winner"] == "attacker", lang,
        )

        if result["winner"] == "attacker":
            narration += "\n\n" + t(lang, "npc_fight_victory") + "\n"
            
            # Roll looting
            loot_list = NPC_LOOT_TABLE.get(diff, [])
            items_gained = []
            
            for drop in loot_list:
                # Skip core_essence for players beyond realm 2 (prevention at source)
                if drop["type"] == "core_essence" and player.realm > 2:
                    continue
                # TEC-2 — só a linha de technique_scroll é cortada (o resto do
                # loot de caçada passa cru). Flag OFF ⇒ a chance original.
                from core.scroll_economy_engine import npc_loot_chance
                if random.random() <= npc_loot_chance(drop):
                    qty = 0
                    if drop["type"] == "spirit_stones":
                        qty = random.randint(drop["min"], drop["max"])
                        player.spirit_stones += qty
                        items_gained.append(f"🪨 {qty} {t(lang, 'currency_spirit_stones')}")
                    else:
                        qty = drop.get("qty", 1)
                        if drop["type"] == "herb":
                            # Give random herb from tier
                            from database.models import HerbCatalog
                            herbs = (await session.execute(select(HerbCatalog).where(HerbCatalog.tier == drop["tier"]))).scalars().all()
                            if herbs:
                                item = random.choice(herbs)
                                if await _add_inventory_item(session, player.telegram_id, "herb", item.id, qty):
                                    items_gained.append(f"{item.emoji} {qty}x {item.name}")
                                else:
                                    items_gained.append(t(lang, "inv_full_loot_lost"))
                        elif drop["type"] == "ore":
                            from database.models import OreCatalog, PlayerOre
                            ores = (await session.execute(select(OreCatalog).where(OreCatalog.tier == drop["tier"]))).scalars().all()
                            if ores:
                                item = random.choice(ores)
                                ore_stmt = select(PlayerOre).where(PlayerOre.player_id == player.telegram_id, PlayerOre.ore_id == item.id)
                                pore = (await session.execute(ore_stmt)).scalar_one_or_none()
                                if pore:
                                    pore.quantity += qty
                                else:
                                    session.add(PlayerOre(player_id=player.telegram_id, ore_id=item.id, quantity=qty))
                                items_gained.append(f"{item.emoji} {qty}x {item.name}")
                        elif drop["type"] == "core_essence":
                            if player.realm <= 2:  # Core essence ONLY for early realms
                                from core.golden_core_engine import add_core_essence
                                added = add_core_essence(player, qty)
                                if added > 0:
                                    items_gained.append(t(lang, "npc_loot_core_essence", qty=added))
                        elif drop["type"] == "technique_scroll":
                            from database.models import TechniqueCatalog
                            # v16.4c — sect signature arts (sect_key) are Library-only, never NPC scroll loot.
                            techs = (await session.execute(
                                select(TechniqueCatalog).where(TechniqueCatalog.sect_key.is_(None))
                            )).scalars().all()
                            if techs:
                                item = random.choice(techs)
                                if await _add_inventory_item(session, player.telegram_id, "technique_scroll", item.id, qty):
                                    items_gained.append(t(lang, "npc_loot_scroll", qty=qty, name=item.name))
                                else:
                                    items_gained.append(t(lang, "inv_full_loot_lost"))
                        elif drop["type"] == "pill":
                            pill_id = drop["id"]
                            if await _add_inventory_item(session, player.telegram_id, "pill", pill_id, qty):
                                from database.models import PillCatalog
                                pill_cat = await session.get(PillCatalog, pill_id)
                                pill_name = _cname(lang, "pill", pill_cat, fallback=f"Pill #{pill_id}")
                                pill_emoji = pill_cat.emoji if pill_cat else "💊"
                                items_gained.append(f"{pill_emoji} {qty}x {pill_name}")
                            else:
                                items_gained.append(t(lang, "inv_full_loot_lost"))
                        elif drop["type"] == "beast_trap":
                            if await _add_inventory_item(session, player.telegram_id, "beast_trap", 0, qty):
                                items_gained.append(t(lang, "npc_loot_beast_trap", qty=qty))
                            else:
                                items_gained.append(t(lang, "inv_full_loot_lost"))
            
            if items_gained:
                narration += t(lang, "npc_loot_display", loot="\n".join(items_gained))

            from core.quest_engine import track_quest
            await track_quest(session, player.telegram_id, "npc_combat", 1)
            from core.bp_engine import update_bp_mission
            await update_bp_mission(session, player.telegram_id, "win_npc_fight")
            from core.body_tempering_engine import add_tempering_progress
            add_tempering_progress(player, 5)
            from core.faction_engine import update_quest_progress as fac_quest_progress
            await fac_quest_progress(session, player.telegram_id, "npc_kill")

            # MV-2 — Tiandao: a caçada vencida conta para a Maré de Bestas do
            # continente (gated + fail-safe; antes→depois na narração).
            try:
                from core.tiandao_engine import record_pve_victory
                _wev = await record_pve_victory(session, player)
                if _wev:
                    narration += "\n" + t(lang, "wev_tide_progress", before=_wev["before"],
                                          progress=_wev["progress"], goal=_wev["goal"])
            except Exception:
                logger.debug("tiandao npc hook failed", exc_info=True)
        else:
            narration += "\n\n" + t(lang, "npc_fight_defeat")

        # Apply persistent HP drain (NPC combat: 50%)
        atk_dmg_taken = result.get("attacker_damage_taken", 0)
        # BUGFIX 2026-07-26: reconcile effective combat-pool damage → raw current_hp.
        hp_lost = apply_hp_drain_scaled(player, atk_dmg_taken, result.get("attacker_max_hp"), drain_pct=0.50)
        # Onda B/C — post-NPC-fight HP shown == the arena/profile (Alma-routed).
        from core.cultivator_soul import soul_max_hp, soul_current_hp
        max_hp_val = await soul_max_hp(session, player)
        cur_hp = soul_current_hp(player, max_hp_val)
        hp_pct = int(cur_hp / max_hp_val * 100) if max_hp_val > 0 else 0
        narration += f"\n\n❤️ HP: {format_number(cur_hp)} / {format_number(max_hp_val)} ({hp_pct}%)"
        if hp_lost > 0:
            narration += f"  (-{format_number(hp_lost)})"
        if cur_hp <= 0:
            narration += f"\n⚠️ {t(lang, 'hp_depleted_warning')}"

        await session.commit()

    mastery_suffix = ("\n\n" + "\n".join(mastery_msgs)) if mastery_msgs else ""

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_combat_back"), callback_data="npc_menu")],
    ])

    full_text = narration + mastery_suffix
    try:
        await query.message.edit_text(full_text, parse_mode="Markdown", reply_markup=kb)
    except Exception:
        # Fallback: send without Markdown if text contains unmatched entities
        await query.message.edit_text(full_text, reply_markup=kb)

async def _add_inventory_item(session, player_id: int, item_type: str, item_id: int, quantity: int):
    return await add_item_to_inventory(session, player_id, item_type, item_id, quantity)
