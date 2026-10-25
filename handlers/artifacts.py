import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy import select, update as sa_update
from database.db import get_session_factory
from database.models import PlayerArtifact, ArtifactCatalog, OreCatalog, ForgeRecipe
from core.i18n import t
# 名 2026-09-14 — a Forja deixa de falar ingles (6 leituras cruas aqui).
from core.i18n import catalog_name as _cname
from core.forge_engine import (
    get_player_ores, get_or_create_forge_skill, get_forge_tier_name,
    FORGE_TIERS, MAX_FORGE_TIER,
    # Recipe system
    get_recipes_by_tier, get_recipe_by_id, get_all_forge_recipes,
    check_recipe_materials, forge_recipe_item,
    get_or_create_forge_mastery, get_all_forge_masteries,
    get_forge_mastery_bonus, get_forge_mastery_name, get_forge_mastery_next_info,
    calculate_recipe_success_chance,
    FORGE_RECIPE_TIER_INFO, get_recipe_tier_name,
)
from config import ARTIFACT_GRADES, ENCHANT_EFFECTS
from core.utils import _ensure_player, safe_handler, rate_limit, safe_answer, safe_parse_callback_int, normalize_lang

logger = logging.getLogger(__name__)


def _get_art_stats_text(art):
    stats = art.custom_stats or {}
    parts = []
    if stats.get("battle_power"): parts.append(f"⚔️+{stats['battle_power']}")
    if stats.get("soul_strength"): parts.append(f"👻+{stats['soul_strength']}")
    if stats.get("luck"): parts.append(f"🍀+{stats['luck']}")
    if stats.get("perception"): parts.append(f"🔮+{stats['perception']}")
    if stats.get("qi_capacity"): parts.append(f"🌀+{stats['qi_capacity']}")
    return " | ".join(parts)


def _format_stats_short(stats: dict) -> str:
    parts = []
    if stats.get("battle_power"):  parts.append(f"+{stats['battle_power']} BP")
    if stats.get("soul_strength"): parts.append(f"+{stats['soul_strength']} Soul")
    if stats.get("luck"):          parts.append(f"+{stats['luck']} Luck")
    if stats.get("perception"):    parts.append(f"+{stats['perception']} Perc")
    if stats.get("qi_capacity"):   parts.append(f"+{stats['qi_capacity']} Qi")
    return ", ".join(parts) if parts else "—"


def _format_stats_lines(stats: dict, lang: str) -> str:
    lines = []
    if stats.get("battle_power"):  lines.append(t(lang, "art_detail_battle_power", value=stats['battle_power']))
    if stats.get("soul_strength"): lines.append(t(lang, "art_detail_soul_strength", value=stats['soul_strength']))
    if stats.get("luck"):          lines.append(t(lang, "art_detail_luck", value=stats['luck']))
    if stats.get("perception"):    lines.append(t(lang, "art_detail_perception", value=stats['perception']))
    if stats.get("qi_capacity"):   lines.append(t(lang, "art_detail_qi_capacity", value=stats['qi_capacity']))
    return "\n".join(lines)


async def _send_or_edit(update: Update, text: str, kb: InlineKeyboardMarkup):
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# ─── Main command ────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def artifacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redirects to forge menu — equipment browsing is now in inventory."""
    await forge_menu_callback(update, context)


# ─── Forge Menu (Recipe Tiers) ───────────────────────────────────────

async def forge_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows forge skill info + recipe tier buttons."""
    if update.callback_query:
        await safe_answer(update.callback_query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"

        if player.realm < 2:
            text = t(lang, "milestone_locked_forge")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_workshop")]])
            await _send_or_edit(update, text, kb)
            return

        ores = await get_player_ores(session, player.telegram_id)
        forge_skill = await get_or_create_forge_skill(session, player.telegram_id)
        all_recipes = await get_all_forge_recipes(session)
        await session.commit()

    tier_data = FORGE_TIERS[forge_skill.tier]
    tier_name = get_forge_tier_name(forge_skill.tier, lang)
    tier_emoji = tier_data["emoji"]

    text = t(lang, "art_forge_title") + "\n\n"
    text += t(lang, "forge_skill_title") + "\n"
    text += t(lang, "forge_skill_tier", emoji=tier_emoji, name=tier_name, tier=forge_skill.tier) + "\n"
    if forge_skill.tier < MAX_FORGE_TIER:
        next_xp = FORGE_TIERS[forge_skill.tier + 1]["xp_req"]
        text += t(lang, "forge_skill_xp", current=forge_skill.xp, next=next_xp) + "\n"
    else:
        text += t(lang, "forge_skill_xp_max", current=forge_skill.xp) + "\n"
    text += t(lang, "forge_skill_total", total=forge_skill.total_forges) + "\n\n"

    if ores:
        text += t(lang, "art_ores_available") + "\n"
        for p_ore, cat in ores:
            text += f"• {cat.emoji} {_cname(lang, 'ore', cat)} (T{cat.tier}): {p_ore.quantity}\n"
        text += "\n"

    text += t(lang, "frg_menu_desc")
    # 2026-05-23 owner request after [jogadores] thread: tell chat users that
    # refine/enchant/bulk-dismantle live only in the mini-app so they don't
    # think the feature is missing or broken. Mini-app is canonical surface.
    text += "\n\n" + t(lang, "frg_menu_miniapp_hint")

    # Count recipes per tier
    tier_counts = {}
    for r in all_recipes:
        tier_counts[r.tier] = tier_counts.get(r.tier, 0) + 1

    buttons = []
    for tier_num in sorted(FORGE_RECIPE_TIER_INFO.keys()):
        info = FORGE_RECIPE_TIER_INFO[tier_num]
        count = tier_counts.get(tier_num, 0)
        if count == 0:
            continue
        tier_n = get_recipe_tier_name(tier_num, lang)
        emoji = info["emoji"]
        is_locked = tier_num > forge_skill.tier + 1
        if is_locked:
            label = t(lang, "frg_tier_btn_locked", tier=tier_num, name=tier_n, req=tier_num - 1)
            buttons.append([InlineKeyboardButton(label, callback_data=f"art_frg_t_{tier_num}")])
        else:
            label = t(lang, "frg_tier_btn", emoji=emoji, tier=tier_num, name=tier_n, count=count)
            buttons.append([InlineKeyboardButton(label, callback_data=f"art_frg_t_{tier_num}")])

    buttons.append([InlineKeyboardButton(t(lang, "frg_btn_mastery"), callback_data="art_frg_mast")])
    buttons.append([InlineKeyboardButton(f"🎒 {t(lang, 'btn_inventory')}", callback_data="cmd_inventory")])
    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_workshop")])
    await _send_or_edit(update, text, InlineKeyboardMarkup(buttons))


# ─── Tier Recipe List ────────────────────────────────────────────────

async def forge_tier_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows all recipes in a tier with stats and materials."""
    query = update.callback_query
    await safe_answer(query)

    tier_num = safe_parse_callback_int(query.data, "art_frg_t_")
    if tier_num is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        forge_skill = await get_or_create_forge_skill(session, player.telegram_id)

        # Check tier access
        if tier_num > forge_skill.tier + 1:
            req_tier_name = get_forge_tier_name(tier_num - 1, lang)
            text = t(lang, "frg_tier_locked_msg", tier=tier_num, req_tier=tier_num - 1, req_name=req_tier_name)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="art_menu_forge")]])
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return

        recipes = await get_recipes_by_tier(session, tier_num)
        # Eagerly load artifact catalog for each recipe
        art_ids = [r.artifact_id for r in recipes]
        arts_result = await session.execute(
            select(ArtifactCatalog).where(ArtifactCatalog.id.in_(art_ids))
        )
        art_map = {a.id: a for a in arts_result.scalars().all()}

        # Load ore catalog for material names
        ore_ids = set()
        for r in recipes:
            for mat in r.materials:
                ore_ids.add(mat["ore_id"])
        ores_result = await session.execute(select(OreCatalog).where(OreCatalog.id.in_(ore_ids)))
        ore_map = {o.id: o for o in ores_result.scalars().all()}

        player_realm = player.realm
        await session.commit()

    tier_n = get_recipe_tier_name(tier_num, lang)
    tier_emoji = FORGE_RECIPE_TIER_INFO[tier_num]["emoji"]
    text = t(lang, "frg_tier_header", tier=tier_num, name=tier_n, emoji=tier_emoji) + "\n\n"

    buttons = []
    for recipe in recipes:
        art = art_map.get(recipe.artifact_id)
        if not art:
            continue
        realm_ok = player_realm >= recipe.required_realm
        stats_str = _format_stats_short(art.base_stats or {})
        mat_parts = []
        for mat in recipe.materials:
            ore = ore_map.get(mat["ore_id"])
            ore_name = _cname(lang, "ore", ore) if ore else f"Ore#{mat['ore_id']}"
            mat_parts.append(f"{mat['qty']}x {ore_name}")
        mat_str = " + ".join(mat_parts)

        realm_icon = "" if realm_ok else " 🔒"
        text += f"{art.emoji} *{art.name}* (G{art.grade}){realm_icon}\n"
        text += f"  📊 {stats_str}\n"
        text += f"  🛠️ {mat_str}\n"
        text += f"  ✅ {int(recipe.base_success_rate)}% {t(lang, 'frg_base_rate')}\n\n"

        if realm_ok:
            buttons.append([InlineKeyboardButton(f"🔨 {art.name}", callback_data=f"art_frg_r_{recipe.id}")])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="art_menu_forge")])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ─── Recipe Detail ───────────────────────────────────────────────────

async def forge_recipe_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows full recipe details: materials, success rate, mastery, forge button."""
    query = update.callback_query
    await safe_answer(query)

    recipe_id = safe_parse_callback_int(query.data, "art_frg_r_")
    if recipe_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        recipe = await get_recipe_by_id(session, recipe_id)
        if not recipe:
            return

        art = (await session.execute(
            select(ArtifactCatalog).where(ArtifactCatalog.id == recipe.artifact_id)
        )).scalar_one_or_none()
        if not art:
            return

        # MV-7 — o detalhe da receita mostra o custo COM o desconto do
        # Ferreiro (mesma matemática que o engine debita — lição MV-6).
        try:
            from core.profession_engine import forge_ore_discount as _prf_ore_disc
            _prf_disc = float(_prf_ore_disc(player) or 0.0)
        except Exception:
            _prf_disc = 0.0
        materials = await check_recipe_materials(session, player.telegram_id, recipe,
                                                 discount=_prf_disc)
        forge_skill = await get_or_create_forge_skill(session, player.telegram_id)
        mastery = await get_or_create_forge_mastery(session, player.telegram_id, recipe_id)

        from core.alchemy_engine import get_or_create_soul_fire
        sf = await get_or_create_soul_fire(session, player.telegram_id, player.realm)
        # MV-9.5 商队 §1 — o `here` da disclosure precisa de saber ONDE o
        # jogador está; lido DENTRO da sessão (o texto é montado depois dela).
        _cont = getattr(player, "current_continent", None)
        await session.commit()

    mastery_bonus = get_forge_mastery_bonus(mastery.mastery_level)
    fire_bonus = sf.fire_tier * 3.0
    tier_bonus = (forge_skill.tier - 1) * 2.0
    total_chance = calculate_recipe_success_chance(
        recipe.base_success_rate, mastery_bonus, sf.fire_tier, forge_skill.tier
    )

    grade_name = ARTIFACT_GRADES.get(art.grade, f"G{art.grade}")
    text = t(lang, "frg_detail_title", name=art.name) + "\n\n"
    text += f"{art.emoji} {t(lang, 'frg_detail_grade', grade_name=grade_name, grade=art.grade)}\n"
    text += f"📊 {_format_stats_short(art.base_stats or {})}\n\n"

    text += t(lang, "frg_detail_materials") + "\n"
    has_all = True
    # MV-9.5 商队 §1 — A DISCLOSURE: onde nasce cada minério da receita. Import
    # LOCAL e fail-safe: `origin_note` devolve None com a flag OFF ⇒ nenhuma
    # linha nova ⇒ o detalhe fica idêntico ao de hoje para quem está em `main`.
    try:
        from core.caravan_engine import origin_note as _origin_note
    except Exception:
        _origin_note = None
    for ore_id, info in materials.items():
        ore = info["ore"]
        ok = "✅" if info["has_enough"] else "❌"
        if not info["has_enough"]:
            has_all = False
        ore_name = _cname(lang, "ore", ore) if ore else f"Ore#{ore_id}"
        ore_emoji = ore.emoji if ore else "🪨"
        text += f"  {ore_emoji} {ore_name} × {info['required']} {ok} ({info['owned']})\n"
        _og = _origin_note("ore", int(ore_id), lang, _cont) if _origin_note else None
        if _og and _og.get("line"):
            # `line` já vem localizada do servidor — NUNCA passar por t().
            text += f"    ↳ {_og['line']}\n"

    text += "\n"
    text += t(lang, "frg_detail_rate",
              total=int(total_chance),
              base=int(recipe.base_success_rate),
              mastery=int(mastery_bonus),
              fire=int(fire_bonus),
              tier=int(tier_bonus)) + "\n\n"

    mastery_name = get_forge_mastery_name(mastery.mastery_level, lang)
    mast_info = get_forge_mastery_next_info(mastery)
    if mast_info["at_max"]:
        text += t(lang, "frg_detail_mastery_max", name=mastery_name, count=mast_info["forges"]) + "\n"
    else:
        text += t(lang, "frg_detail_mastery", name=mastery_name, level=mastery.mastery_level,
                  count=mast_info["forges"], next=mast_info["next_forges"]) + "\n"

    text += "\n" + t(lang, "frg_detail_warning")

    buttons = []
    if has_all and player.realm >= recipe.required_realm:
        buttons.append([InlineKeyboardButton(t(lang, "frg_btn_craft"), callback_data=f"art_frg_do_{recipe.id}")])
    elif not has_all:
        buttons.append([InlineKeyboardButton(t(lang, "frg_not_enough_mats_btn"), callback_data="noop")])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"art_frg_t_{recipe.tier}")])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ─── Execute Forge ───────────────────────────────────────────────────

async def forge_recipe_craft(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute a recipe forge and show results."""
    query = update.callback_query
    await safe_answer(query)

    recipe_id = safe_parse_callback_int(query.data, "art_frg_do_")
    if recipe_id is None:
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        craft_data = await forge_recipe_item(session, player, recipe_id)

        if craft_data.get("error"):
            error = craft_data["error"]
            text = t(lang, f"frg_err_{error}")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="art_menu_forge")]])
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return

        result = craft_data["result"]
        recipe = craft_data["recipe"]
        skill = craft_data["skill"]
        mastery = craft_data["mastery"]

        # Get artifact name
        art_cat = None
        if craft_data.get("blueprint"):
            art_cat = craft_data["blueprint"]
        else:
            art_cat = (await session.execute(
                select(ArtifactCatalog).where(ArtifactCatalog.id == recipe.artifact_id)
            )).scalar_one_or_none()

        art_name = _cname(lang, "art", art_cat) if art_cat else "???"
        art_emoji = art_cat.emoji if art_cat else "🔨"

        if result == "failure":
            if craft_data.get("charm_saved"):
                text = t(lang, "frg_result_failure_protected") + "\n\n"
            else:
                text = t(lang, "frg_result_failure") + "\n\n"
        elif result == "perfect":
            stats_text = _format_stats_short(craft_data["artifact"].custom_stats or {})
            text = t(lang, "frg_result_perfect", emoji=art_emoji, name=art_name, stats=stats_text) + "\n"
        elif result == "divine":
            stats_text = _format_stats_short(craft_data["artifact"].custom_stats or {})
            text = t(lang, "frg_result_divine", emoji=art_emoji, name=art_name, stats=stats_text) + "\n"
            if craft_data.get("spirit_awakened"):
                text += t(lang, "frg_result_spirit", name=craft_data["artifact"].spirit_name) + "\n"
        else:
            stats_text = _format_stats_short(craft_data["artifact"].custom_stats or {})
            text = t(lang, "frg_result_success", emoji=art_emoji, name=art_name, stats=stats_text) + "\n"

        # XP line
        text += "\n"
        xp_gain = craft_data["xp_gain"]
        if craft_data.get("xp_capped"):
            text += t(lang, "frg_result_xp_capped", tier=recipe.tier, cap=craft_data["xp_cap"]) + "\n"
        elif skill.tier < MAX_FORGE_TIER:
            next_xp = FORGE_TIERS[skill.tier + 1]["xp_req"]
            text += t(lang, "frg_result_xp", xp=xp_gain, current=skill.xp, next=next_xp) + "\n"
        else:
            text += t(lang, "frg_result_xp_max", xp=xp_gain, current=skill.xp) + "\n"

        if craft_data.get("leveled_up"):
            tier_name = get_forge_tier_name(skill.tier, lang)
            tier_emoji = FORGE_TIERS[skill.tier]["emoji"]
            text += t(lang, "forge_level_up", tier_name=tier_name, emoji=tier_emoji) + "\n"

        # Mastery line
        mastery_name = get_forge_mastery_name(mastery.mastery_level, lang)
        mast_info = get_forge_mastery_next_info(mastery)
        if mast_info["at_max"]:
            text += t(lang, "frg_result_mastery_max", name=mastery_name, count=mast_info["forges"]) + "\n"
        else:
            text += t(lang, "frg_result_mastery", name=mastery_name, count=mast_info["forges"],
                      next=mast_info["next_forges"]) + "\n"

        if craft_data.get("mastery_leveled"):
            new_name = get_forge_mastery_name(mastery.mastery_level, lang)
            text += t(lang, "frg_result_mastery_up", name=new_name) + "\n"

        # Battle pass mission
        if result != "failure":
            from core.bp_engine import update_bp_mission
            await update_bp_mission(session, player.telegram_id, "forge_artifact")

        # MV-7 (melhoria-estrita, precedente moyu): o chat NUNCA disparava
        # track_quest("forge_artifact") — só o mini-app (webserver:6876).
        # Forjar pelo chat não contava quest/storylet (e não contaria XP de
        # ofício). Gate alinhado ao do mini-app: success/perfect/divine.
        # TEC-1 §0.1 (pedido [jogador]) — XP do ofício VISÍVEL no resumo da forja.
        from core.profession_engine import prof_xp_delta, prof_xp_snapshot
        _prof_xp_before = prof_xp_snapshot(player)
        if result in ("success", "perfect", "divine"):
            try:
                from core.quest_engine import track_quest
                # QoL-relatos — ⚒️ ferreiro: pesa pelo tier da RECEITA (1..5,
                # MAX_FORGE_TIER), não pelo grade do artefato (0..8, que é
                # rolado e diria "sorte", não "esforço").
                await track_quest(session, player.telegram_id, "forge_artifact",
                                  prof_weight_tier=getattr(recipe, "tier", None))
            except Exception:
                logger.exception("chat forge track_quest failed")
        _prof_xp_gain = prof_xp_delta(player, _prof_xp_before)
        if _prof_xp_gain > 0:
            # QoL-relatos — o peso explica o número (Lei §10).
            from core.profession_engine import prof_weight as _prof_weight
            _wt, _ww = _prof_weight(getattr(recipe, "tier", None))
            text += (t(lang, "prf_xp_gain_line_tier", xp=_prof_xp_gain,
                       tier=_wt, w=f"{_ww:g}") if _wt
                     else t(lang, "prf_xp_gain_line", xp=_prof_xp_gain)) + "\n"

        await session.commit()

    buttons = [
        [InlineKeyboardButton(t(lang, "frg_btn_again"), callback_data=f"art_frg_r_{recipe_id}")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="art_menu_forge")],
    ]
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


# ─── Mastery Overview ────────────────────────────────────────────────

async def forge_mastery_overview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows mastery progress for all recipes the player has attempted."""
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        masteries = await get_all_forge_masteries(session, player.telegram_id)
        if not masteries:
            text = t(lang, "frg_mastery_title") + "\n\n" + t(lang, "frg_mastery_empty")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="art_menu_forge")]])
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            return

        # Load recipe + artifact info
        recipe_ids = list(masteries.keys())
        recipes = (await session.execute(
            select(ForgeRecipe).where(ForgeRecipe.id.in_(recipe_ids))
        )).scalars().all()

        art_ids = [r.artifact_id for r in recipes]
        arts = (await session.execute(
            select(ArtifactCatalog).where(ArtifactCatalog.id.in_(art_ids))
        )).scalars().all()
        art_map = {a.id: a for a in arts}
        await session.commit()

    text = t(lang, "frg_mastery_title") + "\n\n"
    for recipe in sorted(recipes, key=lambda r: (r.tier, r.id)):
        mast = masteries.get(recipe.id)
        if not mast:
            continue
        art = art_map.get(recipe.artifact_id)
        if not art:
            continue
        mast_name = get_forge_mastery_name(mast.mastery_level, lang)
        bonus = int(get_forge_mastery_bonus(mast.mastery_level))
        text += t(lang, "frg_mastery_item",
                  emoji=art.emoji, name=art.name, mastery_name=mast_name,
                  level=mast.mastery_level, count=mast.forges_count, bonus=bonus) + "\n"

    kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="art_menu_forge")]])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


# ─── Artifact Detail (from inventory) ───────────────────────────────

async def show_artifact_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    try:
        art_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        stmt = select(PlayerArtifact, ArtifactCatalog).join(ArtifactCatalog).where(
            PlayerArtifact.id == art_id,
            PlayerArtifact.player_id == player.telegram_id
        )
        res = (await session.execute(stmt)).first()
        if not res:
            await safe_answer(query, t(lang, "ans_artefacto_não_encontrado"), show_alert=True)
            return

        art, cat = res
        grade_name = ARTIFACT_GRADES.get(art.grade, f"G{art.grade}")

        text = f"{cat.emoji} *{_cname(lang, 'art', cat)}* ({t(lang, 'art_detail_grade', grade=f'{art.grade} — {grade_name}')})\n"
        text += "————————————————————\n"
        text += t(lang, "art_detail_stats") + "\n"

        stats = art.custom_stats or {}
        text += _format_stats_lines(stats, lang) + "\n"

        slot_name = t(lang, f"slot_{cat.type}") if cat.type else cat.type
        text += t(lang, "art_detail_slot", slot=slot_name) + "\n"

        if hasattr(cat, 'min_realm') and getattr(cat, 'min_realm', 0) > 0:
            from config import REALM_NAMES
            realm_name = REALM_NAMES[cat.min_realm] if cat.min_realm < len(REALM_NAMES) else f"Realm {cat.min_realm}"
            text += t(lang, "art_detail_min_realm", realm=f"{realm_name} ({cat.min_realm})") + "\n"

        if art.enchant_rune:
            eff = ENCHANT_EFFECTS.get(art.enchant_rune, {}).get("name", art.enchant_rune)
            text += t(lang, "art_detail_enchant", effect=eff) + "\n"

        if art.has_spirit:
            text += t(lang, "art_detail_spirit", name=art.spirit_name) + "\n"

        text += "————————————————————\n"

        slot_to_check = cat.type
        eq_res = None
        if slot_to_check == "accessory":
            stmt_eq = select(PlayerArtifact, ArtifactCatalog).join(ArtifactCatalog).where(
                PlayerArtifact.player_id == player.telegram_id,
                PlayerArtifact.slot.in_(["accessory1", "accessory2"]),
                PlayerArtifact.is_equipped == True
            )
            eq_res = (await session.execute(stmt_eq)).first()
        else:
            stmt_eq = select(PlayerArtifact, ArtifactCatalog).join(ArtifactCatalog).where(
                PlayerArtifact.player_id == player.telegram_id,
                PlayerArtifact.slot == slot_to_check,
                PlayerArtifact.is_equipped == True
            )
            eq_res = (await session.execute(stmt_eq)).first()

        if eq_res:
            eq_art, eq_cat = eq_res
            text += f"📊 vs {eq_cat.name}:\n"
            eq_stats = eq_art.custom_stats or {}
            diff_found = False
            for key, key_name in [("battle_power", "BP"), ("soul_strength", "Soul"), ("luck", "Luck"), ("perception", "Perc"), ("qi_capacity", "Qi")]:
                cur = stats.get(key, 0)
                eq_val = eq_stats.get(key, 0)
                if cur > 0 or eq_val > 0:
                    diff_found = True
                    diff = cur - eq_val
                    icon = "⬆️" if diff > 0 else "⬇️" if diff < 0 else "➖"
                    sign = "+" if diff > 0 else ""
                    text += f"   {key_name}: {cur} vs {eq_val} ({sign}{diff} {icon})\n"
            if not diff_found:
                text += t(lang, "art_detail_no_diff") + "\n"

        buttons = []
        if not art.is_equipped:
            btn_text = t(lang, "btn_equip_compare", equipped=(eq_res[1].name if eq_res else "N/A"))
            btn_text = btn_text.replace(" (Replaces N/A)", "").replace(" (Substitui N/A)", "").replace(" (Reemplaza N/A)", "")
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"inv_equip_{art.id}")])
        else:
            buttons.append([InlineKeyboardButton(t(lang, "btn_unequip_detail") + f" {_cname(lang, 'art', cat)}", callback_data=f"inv_unequip_{art.id}")])

        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_tab_equip_R")])

        try:
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise


# ─── Equip / Unequip ─────────────────────────────────────────────────

async def equip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        art_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await safe_answer(query, "❌ Invalid data", show_alert=True)
        return

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"

        stmt = select(PlayerArtifact, ArtifactCatalog).join(ArtifactCatalog).where(
            PlayerArtifact.id == art_id,
            PlayerArtifact.player_id == player.telegram_id
        )
        res = (await session.execute(stmt)).first()
        if not res:
            await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "ans_artefacto_não_encontrado"), show_alert=True)
            return

        art, cat = res

        # Check min_realm requirement
        if hasattr(cat, 'min_realm') and getattr(cat, 'min_realm', 0) > 0:
            if player.realm < cat.min_realm:
                from config import REALM_NAMES
                realm_name = REALM_NAMES[cat.min_realm] if cat.min_realm < len(REALM_NAMES) else f"Realm {cat.min_realm}"
                await safe_answer(query, t(lang, "art_realm_too_low", realm=realm_name), show_alert=True)
                return

        slot = cat.type
        if slot == "accessory":
            stmt_acc1 = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.slot == "accessory1", PlayerArtifact.is_equipped == True)
            acc1 = (await session.execute(stmt_acc1)).scalar_one_or_none()
            if not acc1:
                slot = "accessory1"
            else:
                slot = "accessory2"

        await session.execute(
            sa_update(PlayerArtifact).where(
                PlayerArtifact.player_id == player.telegram_id,
                PlayerArtifact.slot == slot,
                PlayerArtifact.is_equipped == True
            ).values(is_equipped=False, slot=None)
        )

        art.is_equipped = True
        art.slot = slot
        await session.commit()

        await safe_answer(query, t(player.language or "en", "art_equipped_alert", name=_cname((player.language or "en"), "art", cat)), show_alert=True)
        await artifacts_command(update, context)


async def unequip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    slot = query.data.split("_")[-1]

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        await session.execute(
            sa_update(PlayerArtifact).where(
                PlayerArtifact.player_id == player.telegram_id,
                PlayerArtifact.slot == slot,
                PlayerArtifact.is_equipped == True
            ).values(is_equipped=False, slot=None)
        )
        await session.commit()
        await safe_answer(query, t(player.language or "en", "art_unequipped_alert", slot=slot), show_alert=True)
        await artifacts_command(update, context)


# ─── Button Router ───────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def artifact_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "cmd_artifacts":
        await artifacts_command(update, context)
        return True
    if data == "art_menu_forge":
        await forge_menu_callback(update, context)
        return True

    # ── New recipe-based forge callbacks ──
    if data.startswith("art_frg_t_"):
        await forge_tier_recipes(update, context)
        return True
    if data.startswith("art_frg_r_"):
        await forge_recipe_detail(update, context)
        return True
    if data.startswith("art_frg_do_"):
        await forge_recipe_craft(update, context)
        return True
    if data == "art_frg_mast":
        await forge_mastery_overview(update, context)
        return True

    # ── Old grade-band callbacks → redirect to forge menu ──
    if data.startswith("art_forge_band_") or data.startswith("art_forge_bp_") or data.startswith("art_do_forge_"):
        await forge_menu_callback(update, context)
        return True

    # ── Equip / Unequip / Detail ──
    if data.startswith("art_equip_select_"):
        await equip_callback(update, context)
        return True
    if data.startswith("art_unequip_"):
        await unequip_callback(update, context)
        return True
    if data.startswith("art_detail_"):
        await show_artifact_detail(update, context)
        return True

    # ── noop (disabled buttons) ──
    if data == "noop":
        await safe_answer(query)
        return True

    return False


# Keep commands for direct usage if needed
@safe_handler
@rate_limit(1)
async def equip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pass
