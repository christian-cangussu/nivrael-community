from core.utils import safe_handler, rate_limit, build_pagination_keyboard, escape_markdown, safe_answer, safe_parse_callback_int, resolve_chat_player_id
from datetime import datetime, timezone
import math

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, and_, update as sa_update, delete

from core.alchemy_engine import (
    alchemy_realm_locked,
    get_equipped_cauldron,
    get_all_pills,
    get_all_herbs,
    get_player_cauldrons,
    get_herb_inventory,
    get_pill_inventory,
    check_ingredients,
    craft_pill,
    apply_pill_effect,
    get_active_buffs,
    give_starter_cauldron,
    calculate_success_chance,
    get_pill_effectiveness,
    get_all_pill_resistances,
    increment_pill_usage,
    get_resistance_display,
    get_or_create_alchemy_skill,
    grant_alchemy_xp,
    get_alchemy_energy,
    consume_alchemy_energy,
    format_regen_minutes,
    get_flame_mastery,
    ensure_starter_recipes,
    get_unlocked_pill_ids,
    get_or_create_pill_mastery,
    get_mastery_bonus,
    get_mastery_name,
    get_mastery_next_info,
    get_all_pill_masteries,
    get_or_create_soul_fire,
    get_soul_fire_name,
    get_soul_fire_bonus,
    feed_beast_core_to_soul_fire,
    get_upgrade_cost_info,
    check_upgrade_materials,
    upgrade_cauldron,
    repair_cauldron,
    roll_tribulation_round,
    apply_tribulation_failure,
    ALCHEMY_TIERS,
    MAX_ALCHEMY_TIER,
    XP_REWARDS,
    MASTERY_LEVELS,
    MAX_MASTERY_LEVEL,
    SOUL_FIRE_TIERS,
    SOUL_FIRE_MIN_REALM,
    MAX_SOUL_FIRE_TIER,
    REPAIR_COST_PER_10,
    PILL_TRIBULATION_ROUNDS,
    PILL_TRIBULATION_PASS_THRESHOLD,
    PILL_TRIBULATION_CHOICES,
    get_tier_name,
)
from core.game_logic import format_number, get_time_display, calculate_offline_progress
from core.i18n import t
# 名 2026-09-14 — o Caldeirao deixa de falar ingles (13 leituras cruas aqui).
from core.i18n import catalog_name as _cname, catalog_desc as _cdesc
from database.db import get_session_factory
from database.models import Player, PillCatalog, PlayerInventory, PlayerCauldron, CauldronCatalog, PlayerOre


from core.utils import _get_player, _ensure_player


def _alchemy_menu_keyboard(lang: str, show_soul_fire: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(t(lang, "btn_craftar"), callback_data="alch_craftar"),
            InlineKeyboardButton(t(lang, "btn_trocar_cauldron"), callback_data="alch_cauldrons"),
        ],
        [
            InlineKeyboardButton(f"📜 {t(lang, 'btn_recipes')}", callback_data="alch_recipes"),
        ],
    ]
    if show_soul_fire:
        rows.append([
            InlineKeyboardButton(f"🔥 {t(lang, 'btn_soul_fire')}", callback_data="alch_soul_fire"),
        ])
    rows.append([
        InlineKeyboardButton(f"🎒 {t(lang, 'btn_inventory')}", callback_data="cmd_inventory"),
    ])
    rows.append([
        InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="nav_workshop"),
    ])
    return InlineKeyboardMarkup(rows)


async def _send_or_edit(update: Update, text: str, reply_markup, parse_mode="Markdown"):
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)


@safe_handler
@rate_limit(1)
async def alquimia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"

        # 冶 3.1 — o mesmo dono dos três endpoints do mini-app. O texto tem o
        # reino cozido (o chat não tem nome de reino localizado); a guarda §31
        # amarra esse "(Reino N)" ao `ALCHEMY_MIN_REALM` nas três línguas.
        if alchemy_realm_locked(player):
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            text = t(lang, "milestone_locked_alchemy")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="cmd_start")]])
            if update.callback_query:
                await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
            else:
                await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
            return

        await give_starter_cauldron(session, player.telegram_id)
        await ensure_starter_recipes(session, player.telegram_id)

        pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)
        skill = await get_or_create_alchemy_skill(session, player.telegram_id)
        sf = await get_or_create_soul_fire(session, player.telegram_id, player.realm)
        unlocked_ids = await get_unlocked_pill_ids(session, player.telegram_id)
        all_pills = await get_all_pills(session)
        total_pills = len(all_pills)
        unlocked_count = len([p for p in all_pills if p.id in unlocked_ids])

        # Only show buffs that actually help in Alchemy
        all_buffs = await get_active_buffs(session, player.telegram_id)
        buffs = [b for b in all_buffs if b.buff_type in ("craft_speed", "craft_success", "alch_yield")]

        from core.monetization import get_player_vip_level
        vip_lvl = await get_player_vip_level(session, player.telegram_id)
        energy_current, energy_max, regen_minutes = get_alchemy_energy(player, vip_lvl, skill.tier)

        skill_tier = skill.tier
        skill_xp = skill.xp
        skill_emoji = ALCHEMY_TIERS[skill_tier]["emoji"]
        tier_name = get_tier_name(skill_tier, lang)
        player_realm = player.realm
        if skill_tier < MAX_ALCHEMY_TIER:
            next_xp = ALCHEMY_TIERS[skill_tier + 1]["xp_req"]
        else:
            next_xp = None

        await session.commit()

    separator = "—" * 24

    if cauldron:
        cauldron_line = t(lang, "alch_equipped_cauldron",
                          emoji=cauldron.emoji, name=_cname(lang, 'cauldron', cauldron),
                          bonus=f"{cauldron.success_bonus:.0f}",
                          durability=f"{pc.durability}/{cauldron.max_durability}")
    else:
        cauldron_line = t(lang, "alch_no_cauldron")

    if next_xp is not None:
        skill_line = t(lang, "alchemy_skill_display",
                       tier_name=tier_name, emoji=skill_emoji,
                       xp=skill_xp, next_xp=next_xp)
    else:
        skill_line = t(lang, "alchemy_skill_display_max",
                       tier_name=tier_name, emoji=skill_emoji, xp=skill_xp)

    # Energy bar
    filled = round((energy_current / energy_max) * 10) if energy_max > 0 else 0
    bar = "█" * filled + "░" * (10 - filled)
    energy_line = t(lang, "alch_energy_bar", bar=bar, current=energy_current, max=energy_max, regen=format_regen_minutes(regen_minutes))

    # 火候 — o posto tem de ser VISÍVEL na chama, senão o buff não existe para
    # quem o ganhou. Tier 1 não vê "+0" (celebrar no-op é pior que silêncio): vê
    # o degrau SEGUINTE, dito em palavras, com o número do antes→depois.
    _tier_max_bonus, _tier_regen_mult = get_flame_mastery(skill_tier)
    if _tier_max_bonus > 0:
        flame_line = t(lang, "alch_flame_mastery",
                       tier_name=tier_name,
                       max_bonus=_tier_max_bonus,
                       pct=f"{(1.0 - _tier_regen_mult) * 100:.0f}")
    elif skill_tier < MAX_ALCHEMY_TIER:
        _nb, _nm = get_flame_mastery(skill_tier + 1)
        flame_line = t(lang, "alch_flame_mastery_next",
                       next_tier=get_tier_name(skill_tier + 1, lang),
                       max_bonus=_nb,
                       pct=f"{(1.0 - _nm) * 100:.0f}")
    else:
        flame_line = None

    # Soul fire line
    sf_name = get_soul_fire_name(sf.fire_tier, lang)
    sf_bonus = get_soul_fire_bonus(sf.fire_tier)
    if sf.fire_tier > 0 and sf.fire_tier < MAX_SOUL_FIRE_TIER:
        next_sf_xp = SOUL_FIRE_TIERS[sf.fire_tier + 1]["xp_req"]
        soul_fire_line = t(lang, "alch_soul_fire_display",
                           name=sf_name, bonus=f"{sf_bonus:.0f}",
                           xp=sf.fire_exp, next_xp=next_sf_xp)
    elif sf.fire_tier >= MAX_SOUL_FIRE_TIER:
        soul_fire_line = t(lang, "alch_soul_fire_max", name=sf_name, bonus=f"{sf_bonus:.0f}")
    else:
        soul_fire_line = t(lang, "alch_soul_fire_dormant")

    # Recipes line
    recipes_line = t(lang, "alch_recipes_count", unlocked=unlocked_count, total=total_pills)

    lines = [
        t(lang, "alch_title"),
        separator,
        skill_line,
        cauldron_line,
        energy_line,
    ]
    if flame_line:
        lines.append(flame_line)
    lines += [
        f"🔥 {soul_fire_line}",
        f"📜 {recipes_line}",
        separator,
    ]

    if buffs:
        lines.append(t(lang, "alch_active_buffs"))
        for buff in buffs:
            remaining = (buff.expires_at - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                source_clean = buff.source.replace("_", " ").title() if buff.source else "Unknown"
                lines.append(f"  ✨ {source_clean} — {get_time_display(remaining)}")
        lines.append(separator)

    lines.append(t(lang, "alch_menu_hint"))

    show_sf = player_realm >= SOUL_FIRE_MIN_REALM
    await _send_or_edit(update, "\n".join(lines), _alchemy_menu_keyboard(lang, show_soul_fire=show_sf))


@safe_handler
@rate_limit(1)
async def craftar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tier overview: one button per tier, player taps to drill into that tier."""
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        pills = await get_all_pills(session)
        skill = await get_or_create_alchemy_skill(session, player.telegram_id)
        unlocked_ids = await get_unlocked_pill_ids(session, player.telegram_id)
        player_tier = skill.tier
        await session.commit()

    # Group pills by tier (no expensive ingredient checks here)
    tier_groups: dict = {}
    for pill in pills:
        req_tier = pill.required_alchemy_tier or 1
        tier_groups.setdefault(req_tier, []).append(pill)
    sorted_tiers = sorted(tier_groups.keys())

    tier_name = get_tier_name(player_tier, lang)
    tier_emoji = ALCHEMY_TIERS.get(player_tier, ALCHEMY_TIERS[1])["emoji"]
    lines = [
        t(lang, "alch_craftar_title"),
        t(lang, "alchemy_skill_display",
          tier_name=tier_name, emoji=tier_emoji,
          xp=skill.xp,
          next_xp=ALCHEMY_TIERS[player_tier + 1]["xp_req"] if player_tier < MAX_ALCHEMY_TIER else skill.xp),
        "",
    ]

    buttons = []
    for req_tier in sorted_tiers:
        tier_pills = tier_groups[req_tier]
        unlocked_in_tier = sum(1 for p in tier_pills if p.id in unlocked_ids)
        total_in_tier = len(tier_pills)
        t_name = get_tier_name(req_tier, lang)
        t_emoji = ALCHEMY_TIERS.get(req_tier, ALCHEMY_TIERS[1])["emoji"]
        is_locked = req_tier > player_tier
        is_current = req_tier == player_tier

        if is_locked:
            label = f"🔒 Tier {req_tier} — {t_name}"
        elif is_current:
            label = f"{t_emoji} Tier {req_tier} — {t_name} ★ ({unlocked_in_tier}/{total_in_tier})"
        else:
            label = f"{t_emoji} Tier {req_tier} — {t_name} ({unlocked_in_tier}/{total_in_tier})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"alch_craftar_tier_{req_tier}")])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_menu")])
    await _send_or_edit(update, "\n".join(lines), InlineKeyboardMarkup(buttons))


async def alch_craftar_tier_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Level 2: compact pill list for a tier — name + status only, each pill is a button."""
    query = update.callback_query
    await safe_answer(query)

    req_tier = safe_parse_callback_int(query.data, "alch_craftar_tier_")
    if req_tier is None:
        return

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return

        lang = player.language or "en"
        pills = await get_all_pills(session)
        pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)
        skill = await get_or_create_alchemy_skill(session, player.telegram_id)
        unlocked_ids = await get_unlocked_pill_ids(session, player.telegram_id)
        masteries = await get_all_pill_masteries(session, player.telegram_id)
        player_tier = skill.tier

        tier_pills = [p for p in pills if (p.required_alchemy_tier or 1) == req_tier]
        is_locked = req_tier > player_tier
        tier_name = get_tier_name(req_tier, lang)
        tier_emoji = ALCHEMY_TIERS.get(req_tier, ALCHEMY_TIERS[1])["emoji"]
        is_current = req_tier == player_tier

        if is_locked:
            lines = [t(lang, "alchemy_tier_locked", tier=req_tier, name=tier_name), ""]
            for pill in tier_pills:
                lines.append(f"🔒 {_cname(lang, 'pill', pill)}")
            await session.commit()
            buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_craftar")]]
            await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(buttons))
            return

        # Quick ingredient check for status icons only (only for unlocked pills)
        pill_statuses = []
        for pill in tier_pills:
            is_unlocked = pill.id in unlocked_ids
            if is_unlocked:
                ingredients_info = await check_ingredients(session, player.telegram_id, pill)
                realm_ok = player.realm >= pill.min_realm
                all_have = all(info["has_enough"] for info in ingredients_info.values()) and realm_ok
            else:
                all_have = False
            pill_statuses.append((pill, all_have, is_unlocked))

        # U3 (v16.6): owned-count per pill (SUM across quality rows) for the list.
        pill_owned_map: dict[int, int] = {}
        for inv_row, _pc in await get_pill_inventory(session, player.telegram_id):
            pill_owned_map[inv_row.item_id] = pill_owned_map.get(inv_row.item_id, 0) + int(inv_row.quantity or 0)

        await session.commit()

    current_marker = f" ← {t(lang, 'alchemy_your_tier')}" if is_current else ""
    header = t(lang, "alchemy_tier_header", tier=req_tier, name=tier_name, emoji=tier_emoji) + current_marker

    unlocked_pills = [(p, ok) for p, ok, u in pill_statuses if u]
    craftable = sum(1 for _, ok in unlocked_pills if ok)
    lines = [header, f"_{craftable}/{len(unlocked_pills)} craftable_", ""]

    buttons = []
    for pill, all_have, is_unlocked in pill_statuses:
        if is_unlocked:
            mastery = masteries.get(pill.id)
            mastery_tag = ""
            if mastery and mastery.mastery_level > 1:
                mastery_tag = f" ⭐{mastery.mastery_level}"
            status_icon = "✅" if all_have else "❌"
            owned = pill_owned_map.get(pill.id, 0)  # U3 (v16.6)
            owned_tag = f" · 📦{owned}" if owned else ""
            # TAPETE QoL §5 item 6 ([jogador]: "reloginho"): ⏱️ = buff temporizado.
            timed_tag = " ⏱️" if (int(pill.duration_minutes or 0) > 0 or pill.effect_type == "revive") else ""
            lines.append(f"{pill.emoji} {_cname(lang, 'pill', pill)}{timed_tag} {status_icon}{mastery_tag}{owned_tag}")
            label = f"{pill.emoji} {_cname(lang, 'pill', pill)}" + (" ✅" if all_have else "")
            buttons.append([InlineKeyboardButton(label, callback_data=f"alch_pill_detail_{pill.id}")])
        else:
            # v14.3 D-6c — T4+ recipes use the launch-teaser flavor instead of
            # the curt "??? não descoberta" — gives Mahayana players context for
            # why their slots are empty ([jogador] reported on 2026-05-XX).
            # Lower tiers keep the short hint to avoid spamming Foundation
            # players with launch-only flavor.
            if req_tier >= 4:
                lines.append(t(lang, "alch_recipe_locked_apex"))
            else:
                lines.append(f"🔒 ??? — {t(lang, 'alch_recipe_locked')}")

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_craftar")])
    await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


async def alch_pill_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Level 3: full detail for one pill + craft button."""
    query = update.callback_query
    await safe_answer(query)

    pill_id = safe_parse_callback_int(query.data, "alch_pill_detail_")
    if pill_id is None:
        return

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return

        lang = player.language or "en"
        from config import REALM_NAMES

        pill = (await session.execute(
            select(PillCatalog).where(PillCatalog.id == pill_id)
        )).scalar_one_or_none()
        if not pill:
            await safe_answer(query, t(lang, "alchemy_pill_not_found"), show_alert=True)
            return

        pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)
        skill = await get_or_create_alchemy_skill(session, player.telegram_id)
        player_tier = skill.tier

        # Mastery & Soul Fire
        mastery = await get_or_create_pill_mastery(session, player.telegram_id, pill_id)
        m_bonus = get_mastery_bonus(mastery.mastery_level)
        sf = await get_or_create_soul_fire(session, player.telegram_id, player.realm)
        sf_bonus = get_soul_fire_bonus(sf.fire_tier)

        pill_tier = pill.required_alchemy_tier or 1
        from core.monetization import get_player_vip_level
        from config import ALCHEMY_ENERGY_COSTS, ALCHEMY_ENERGY_VIP_REGEN

        vip_lvl = await get_player_vip_level(session, player.telegram_id)
        energy_cost = ALCHEMY_ENERGY_COSTS.get(pill_tier, 10)
        energy_current, energy_max, regen_minutes = get_alchemy_energy(player, vip_lvl, skill.tier)

        ingredients_info = await check_ingredients(session, player.telegram_id, pill)
        resistances = await get_all_pill_resistances(session, player.telegram_id)
        # F (2026-06-16): resistance applies ONLY to the uncapped qi-capacity pill.
        # Exempt pills show full potency even if they carry old counters (retroactive).
        uses = resistances.get(pill.id, 0) if pill.effect_type == "qi_capacity" else 0
        res = get_resistance_display(uses)

        # MV-7 — display = roll: o bônus do Alquimista entra pela MESMA
        # função que o craft usa (gated; 0.0 com flag OFF).
        try:
            from core.profession_engine import alchemy_success_bonus
            _prof_b = float(alchemy_success_bonus(player) or 0.0)
        except Exception:
            _prof_b = 0.0
        success_chance = calculate_success_chance(cauldron, pill, player_tier, m_bonus, sf_bonus, profession_bonus=_prof_b)
        realm_ok = player.realm >= pill.min_realm
        all_have = all(info["has_enough"] for info in ingredients_info.values()) and realm_ok

        # U3 (v16.6): how many of this pill the player owns (sum across quality).
        pill_owned = 0
        for inv_row, _pc in await get_pill_inventory(session, player.telegram_id):
            if inv_row.item_id == pill_id:
                pill_owned += int(inv_row.quantity or 0)

        # MV-9.5 商队 §1 — o `here` da disclosure precisa de saber ONDE o
        # jogador está; lido DENTRO da sessão (o texto é montado depois dela).
        _cont = getattr(player, "current_continent", None)

        await session.commit()

    req_tier = pill.required_alchemy_tier or 1
    tier_name = get_tier_name(req_tier, lang)
    realm_name = REALM_NAMES[pill.min_realm] if pill.min_realm < len(REALM_NAMES) else f"R{pill.min_realm}"
    separator = "—" * 20

    lines = [
        f"{pill.emoji} *{_cname(lang, 'pill', pill)}*",
        separator,
    ]

    if pill.duration_minutes and pill.duration_minutes > 0:
        lines.append(
            f"{t(lang, 'alchemy_pill_effect', effect=_cdesc(lang, 'pill', pill))}"
            f" · {t(lang, 'alchemy_pill_duration', duration=pill.duration_minutes)}"
        )
    else:
        lines.append(t(lang, "alchemy_pill_effect", effect=_cdesc(lang, "pill", pill)))

    lines.append(f"{t(lang, 'alchemy_pill_realm', realm=realm_name)} | ⚗️ T{req_tier} {tier_name}")
    if pill_owned > 0:
        lines.append(t(lang, "alch_pill_owned", n=pill_owned))  # U3 (v16.6)

    # Success chance breakdown
    chance_parts = [f"🎯 {success_chance:.0f}%"]
    if m_bonus > 0:
        chance_parts.append(f"📖+{m_bonus:.0f}%")
    if sf_bonus > 0:
        chance_parts.append(f"🔥+{sf_bonus:.0f}%")
    lines.append(" | ".join(chance_parts) + f" | 🧪 {res['pct']}%")
    if uses > 0:
        lines.append(t(lang, "pill_resistance_info"))

    # Mastery display
    m_name = get_mastery_name(mastery.mastery_level, lang)
    m_info = get_mastery_next_info(mastery)
    if m_info["at_max"]:
        lines.append(f"📖 {t(lang, 'alch_mastery_line', name=m_name, crafts=m_info['crafts'])} ★")
    else:
        lines.append(f"📖 {t(lang, 'alch_mastery_progress', name=m_name, crafts=m_info['crafts'], next_crafts=m_info['next_crafts'])}")

    filled = round((energy_current / energy_max) * 10) if energy_max > 0 else 0
    bar = "█" * filled + "░" * (10 - filled)
    lines.append(t(lang, "alch_energy_cost_line", bar=bar, current=energy_current, max=energy_max, cost=energy_cost, regen=format_regen_minutes(regen_minutes)))
    lines.append("")
    lines.append(t(lang, "alchemy_pill_ingredients"))
    # MV-9.5 商队 §1 — A DISCLOSURE: até hoje NENHUMA tela do jogo dizia onde
    # nasce um material, e a pílula ficava impossível sem dizer porquê. Import
    # LOCAL e fail-safe: `origin_note` devolve None com a flag OFF ⇒ nenhuma
    # linha nova ⇒ o detalhe fica idêntico ao de hoje para quem está em `main`.
    try:
        from core.caravan_engine import origin_note as _origin_note
    except Exception:
        _origin_note = None
    for herb_id, info in ingredients_info.items():
        herb = info["herb"]
        herb_emoji = herb.emoji if herb else "🌿"
        herb_name = _cname(lang, "herb", herb) if herb else f"Herb #{herb_id}"
        check = "✅" if info["has_enough"] else "❌"
        lines.append(f"  {herb_emoji} {herb_name} ×{info['required']} ({info['owned']} owned) {check}")
        _og = _origin_note("herb", int(herb_id), lang, _cont) if _origin_note else None
        if _og and _og.get("line"):
            # `line` já vem localizada do servidor — NUNCA passar por t().
            lines.append(f"    ↳ {_og['line']}")

    buttons = []
    if all_have:
        buttons.append([InlineKeyboardButton(
            f"⚗️ {t(lang, 'btn_craftar')} {_cname(lang, 'pill', pill)}",
            callback_data=f"alch_craft_{pill.id}"
        )])
    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"alch_craftar_tier_{req_tier}")])

    await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


async def craft_pill_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    pill_id = safe_parse_callback_int(query.data, "alch_craft_")
    if pill_id is None:
        await safe_answer(query)
        return

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return

        lang = player.language or "en"

        pill = (await session.execute(select(PillCatalog).where(PillCatalog.id == pill_id))).scalar_one_or_none()
        if not pill:
            await safe_answer(query, t(lang, "alch_pill_not_found"), show_alert=True)
            return

        if player.realm < pill.min_realm:
            from config import REALM_NAMES
            await safe_answer(query, t(lang, "alch_realm_too_low", realm=REALM_NAMES[pill.min_realm]), show_alert=True)
            return

        skill = await get_or_create_alchemy_skill(session, player.telegram_id)
        player_tier = skill.tier
        if player_tier < pill.required_alchemy_tier:
            req_tier_name = get_tier_name(pill.required_alchemy_tier, lang)
            await safe_answer(query, 
                t(lang, "alchemy_recipe_locked", tier_name=req_tier_name, tier=pill.required_alchemy_tier),
                show_alert=True,
            )
            return

        ingredients_status = await check_ingredients(session, player.telegram_id, pill)
        if not all(info["has_enough"] for info in ingredients_status.values()):
            await safe_answer(query, t(lang, "alch_missing_ingredients"), show_alert=True)
            return

        # Block crafting with a broken cauldron before consuming energy
        pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)
        if pc and pc.durability <= 0:
            await query.message.edit_text(
                t(lang, "alchemy_cauldron_broken"),
                parse_mode="Markdown",
            )
            return

        # Energy check
        pill_tier = pill.required_alchemy_tier or 1
        from core.monetization import get_player_vip_level
        from config import ALCHEMY_ENERGY_COSTS, ALCHEMY_ENERGY_VIP_REGEN

        vip_lvl = await get_player_vip_level(session, player.telegram_id)
        energy_cost = ALCHEMY_ENERGY_COSTS.get(pill_tier, 10)
        energy_ok, energy_current, energy_max = consume_alchemy_energy(player, energy_cost, vip_lvl, skill.tier)

        if not energy_ok:
            _, _, regen_minutes = get_alchemy_energy(player, vip_lvl, skill.tier)
            await safe_answer(query, 
                t(lang, "alch_energy_not_enough",
                  current=energy_current, max=energy_max, cost=energy_cost,
                  regen=format_regen_minutes(regen_minutes)),
                show_alert=True,
            )
            return

        craft_result = await craft_pill(session, player, pill, player_tier)

        if craft_result.get("inventory_full"):
            from core.utils import _get_or_create_ring, _count_used_slots
            ring = await _get_or_create_ring(session, player.telegram_id)
            used = await _count_used_slots(session, player.telegram_id)
            await safe_answer(query, t(lang, "inv_full", used=used, max=ring.max_slots), show_alert=True)
            return

        # ── Heavenly result → Pill Tribulation mini-game ──
        if craft_result["result"] == "heavenly":
            # Grant XP immediately (ingredients already consumed in engine)
            xp_gain_amount = XP_REWARDS.get("heavenly", 0)
            skill, leveled_up = await grant_alchemy_xp(session, player.telegram_id, "heavenly")
            await session.commit()

            # Store tribulation state
            context.user_data["pill_tribulation"] = {
                "pill_id": pill.id,
                "pill_name": _cname(lang, "pill", pill),
                "pill_emoji": pill.emoji,
                "pill_tier": pill.required_alchemy_tier or 1,
                "round": 1,
                "successes": 0,
                "history": [],
                "xp_gained": xp_gain_amount,
            }
            await safe_answer(query)
            await _show_tribulation_round(query.message, lang, context.user_data["pill_tribulation"])
            return

        success_chance = craft_result["success_chance"]

        ach_unlocked = []
        # TEC-1 §0.1 (pedido [jogador]) — XP do ofício VISÍVEL no resumo do craft.
        from core.profession_engine import prof_xp_delta, prof_xp_snapshot
        _prof_xp_before = prof_xp_snapshot(player)
        if craft_result["result"] in ("success", "perfect", "divine"):
            from core.quest_engine import track_quest
            # QoL-relatos — o tier viaja no canal PRÓPRIO do ofício; `amount` fica
            # em 1 (é o contador de quest/storylet, não o peso).
            await track_quest(session, player.telegram_id, "craft_pill",
                              prof_weight_tier=pill_tier)
            from core.achievement_engine import check_achievements
            ach_unlocked = await check_achievements(session, player.telegram_id, "pills_crafted", 1)
            if player.realm == 2:
                essence_gain = {"success": 5, "perfect": 15, "divine": 30}.get(craft_result["result"], 5)
                from core.golden_core_engine import add_core_essence
                added_ce = add_core_essence(player, essence_gain)
                craft_result["core_essence_added"] = added_ce
                craft_result["core_essence_total"] = player.core_essence or 0
            from core.bp_engine import update_bp_mission
            await update_bp_mission(session, player.telegram_id, "craft_pills")
            from core.faction_engine import update_quest_progress as fac_quest_progress
            await fac_quest_progress(session, player.telegram_id, "craft_pill")
            if craft_result["result"] in ("perfect", "divine"):
                await fac_quest_progress(session, player.telegram_id, "craft_pill_hq")

        # Grant alchemy XP
        xp_gain_amount = XP_REWARDS.get(craft_result["result"], 0)
        skill, leveled_up = await grant_alchemy_xp(session, player.telegram_id, craft_result["result"])
        craft_result["xp_gained"] = xp_gain_amount
        craft_result["skill_tier"] = skill.tier
        craft_result["skill_xp"] = skill.xp
        craft_result["leveled_up"] = leveled_up
        if skill.tier < MAX_ALCHEMY_TIER:
            craft_result["skill_next_xp"] = ALCHEMY_TIERS[skill.tier + 1]["xp_req"]
        else:
            craft_result["skill_next_xp"] = None

        if leveled_up:
            # SET alchemy tier progress directly (not increment — tier 2 means progress=2, not +=2)
            from database.models import PlayerBPMission, BattlePassMission
            from config import CURRENT_SEASON
            _alch_missions = (await session.execute(
                select(BattlePassMission).where(BattlePassMission.objective_type == "alchemy_tier")
            )).scalars().all()
            for _am in _alch_missions:
                _pm = (await session.execute(
                    select(PlayerBPMission).where(
                        PlayerBPMission.player_id == player.telegram_id,
                        PlayerBPMission.mission_id == _am.id,
                        PlayerBPMission.season == CURRENT_SEASON
                    )
                )).scalar_one_or_none()
                if _pm is None:
                    _pm = PlayerBPMission(
                        player_id=player.telegram_id, mission_id=_am.id,
                        season=CURRENT_SEASON, progress=0, is_completed=False, claimed=False,
                    )
                    session.add(_pm)
                if not _pm.is_completed:
                    _pm.progress = min(skill.tier, _am.objective_value)
                    if _pm.progress >= _am.objective_value:
                        _pm.is_completed = True
                        from core.bp_engine import recalculate_bp_tier
                        await recalculate_bp_tier(session, player.telegram_id)

        # TEC-1 §0.1 — delta do ofício capturado ANTES do commit (Lei §10).
        craft_result["prof_xp_gained"] = prof_xp_delta(player, _prof_xp_before)
        # QoL-relatos — o peso que produziu esse delta, para o resumo explicar o
        # número (keys só lidas quando prof_xp_gained > 0).
        if craft_result["prof_xp_gained"] > 0:
            from core.profession_engine import prof_weight as _prof_weight
            _wt, _ww = _prof_weight(pill_tier)
            craft_result["prof_weight_tier"] = _wt
            craft_result["prof_weight"] = f"{_ww:g}"
        await session.commit()
        if ach_unlocked:
            from handlers.achievements import notify_achievements
            await notify_achievements(context, update.effective_user.id, ach_unlocked)

    result_key = craft_result["result"]
    separator = "—" * 24

    message_key = f"alch_result_{result_key}"
    result_text = t(lang, message_key, pill_name=_cname(lang, "pill", pill))

    lines = [
        t(lang, "alch_crafting_header", pill_name=_cname(lang, "pill", pill)),
        separator,
        t(lang, "alch_chance_display", chance=f"{success_chance:.1f}"),
        separator,
        result_text,
    ]

    if result_key in ("success", "perfect", "divine"):
        quality = craft_result.get("quality", "normal")
        lines.append(t(lang, "alch_quality_display", quality=quality.upper()))
        # MV-7 — 🧪 a pílula extra do Alquimista é DITA (progressão visível).
        if craft_result.get("extra_pill"):
            lines.append(t(lang, "prf_alch_extra_line"))

    if result_key == "explosion" and "durability_remaining" in craft_result:
        lines.append(t(lang, "alch_durability_loss", durability=craft_result["durability_remaining"]))

    lines.append(separator)

    # XP display
    xp_gained_amount = craft_result.get("xp_gained", 0)
    skill_xp = craft_result.get("skill_xp", 0)
    skill_next_xp = craft_result.get("skill_next_xp")
    if skill_next_xp is not None:
        lines.append(t(lang, "alchemy_xp_gain", xp=xp_gained_amount, current=skill_xp, next=skill_next_xp))
    else:
        lines.append(t(lang, "alchemy_xp_gain_max", xp=xp_gained_amount, current=skill_xp))

    ce_added = craft_result.get("core_essence_added", 0)
    if ce_added > 0:
        lines.append(t(lang, "core_essence_gain", amount=ce_added, total=craft_result.get("core_essence_total", 0)))

    # TEC-1 §0.1 — o XP do ofício ganho neste craft É dito (pedido [jogador];
    # gated por construção: o delta só existe com flag ON + ofício).
    if craft_result.get("prof_xp_gained"):
        # QoL-relatos — o PESO tem de aparecer, senão o jogador vê o número subir
        # mais e não sabe porquê (Lei §10). Tier 0/desconhecido → linha antiga.
        _wt = int(craft_result.get("prof_weight_tier") or 0)
        if _wt:
            lines.append(t(lang, "prf_xp_gain_line_tier",
                           xp=craft_result["prof_xp_gained"], tier=_wt,
                           w=craft_result.get("prof_weight", "1")))
        else:
            lines.append(t(lang, "prf_xp_gain_line", xp=craft_result["prof_xp_gained"]))

    if craft_result.get("leveled_up"):
        new_tier = craft_result["skill_tier"]
        tier_name = get_tier_name(new_tier, lang)
        tier_emoji = ALCHEMY_TIERS[new_tier]["emoji"]
        lines.append("")
        lines.append(t(lang, "alchemy_level_up", tier_name=tier_name, emoji=tier_emoji))

    # Mastery level up
    if craft_result.get("mastery_leveled"):
        m = craft_result["mastery"]
        m_name = get_mastery_name(m.mastery_level, lang)
        lines.append(t(lang, "alch_mastery_levelup", name=m_name, pill_name=_cname(lang, "pill", pill)))

    # Soul fire level up
    if craft_result.get("soul_fire_leveled"):
        sf = craft_result["soul_fire"]
        sf_name = get_soul_fire_name(sf.fire_tier, lang)
        lines.append(t(lang, "alch_soul_fire_levelup", name=sf_name))

    req_tier = pill.required_alchemy_tier or 1
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🔄 {t(lang, 'alchemy_craft_again')}",
            callback_data=f"alch_pill_detail_{pill.id}"
        )],
        [InlineKeyboardButton(
            t(lang, "btn_back"),
            callback_data=f"alch_craftar_tier_{req_tier}"
        )],
        [InlineKeyboardButton(
            t(lang, "btn_main_menu"),
            callback_data="alch_menu"
        )],
    ])

    await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


@safe_handler
@rate_limit(1)
async def ervas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        herb_inv = await get_herb_inventory(session, player.telegram_id)
        await session.commit()

    if not herb_inv:
        lines = [t(lang, "alch_ervas_title"), "", t(lang, "alch_ervas_empty")]
        buttons = []
    else:
        page = 0
        if context.args and len(context.args) > 0 and context.args[0].isdigit():
            page = int(context.args[0])
            
        ITEMS_PER_PAGE = 10
        total_items = len(herb_inv)
        total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
        paginated_inv = herb_inv[page * ITEMS_PER_PAGE : (page + 1) * ITEMS_PER_PAGE]
        
        lines = [t(lang, "alch_ervas_title"), ""]
        buttons = []
        for inv_item, herb in paginated_inv:
            tier_stars = "⭐" * herb.tier
            lines.append(f"{herb.emoji} *{_cname(lang, 'herb', herb)}* x{inv_item.quantity}")
            lines.append(f"  {tier_stars} — _{escape_markdown(_cdesc(lang, 'herb', herb))}_")
            lines.append("")
            
        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, "alch_ervas_page_", lang))

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_menu")])
    await _send_or_edit(update, "\n".join(lines), InlineKeyboardMarkup(buttons))


async def alch_ervas_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _raw = safe_parse_callback_int(query.data, "alch_ervas_page_")
    if _raw is None:
        return
    page = _raw - 1
    context.args = [str(page)]
    await ervas_command(update, context)


@safe_handler
@rate_limit(1)
async def pilulas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        pill_inv = await get_pill_inventory(session, player.telegram_id)
        resistances = await get_all_pill_resistances(session, player.telegram_id)
        await session.commit()

    if not pill_inv:
        lines = [t(lang, "alch_pilulas_title"), "", t(lang, "alch_pilulas_empty")]
        buttons = []
    else:
        page = 0
        if context.args and len(context.args) > 0 and context.args[0].isdigit():
            page = int(context.args[0])

        ITEMS_PER_PAGE = 10
        total_items = len(pill_inv)
        total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
        paginated_inv = pill_inv[page * ITEMS_PER_PAGE : (page + 1) * ITEMS_PER_PAGE]

        # F (2026-06-16): only qi-capacity pills carry resistance (others exempt).
        has_any_resistance = any(
            resistances.get(pill.id, 0) > 0
            for _, pill in paginated_inv if pill.effect_type == "qi_capacity"
        )
        lines = [t(lang, "alch_pilulas_title"), ""]
        if has_any_resistance:
            lines.append(t(lang, "pill_resistance_info"))
            lines.append("")
        buttons = []
        for inv_item, pill in paginated_inv:
            quality_tag = f" ({inv_item.quality.upper()})" if inv_item.quality != "normal" else ""
            lines.append(f"{pill.emoji} *{_cname(lang, 'pill', pill)}*{quality_tag} x{inv_item.quantity}")
            lines.append(f"  📖 _{escape_markdown(_cdesc(lang, 'pill', pill))}_")
            # Show resistance info (F 2026-06-16: qi-capacity pills only; exempt → 0)
            uses = resistances.get(pill.id, 0) if pill.effect_type == "qi_capacity" else 0
            res = get_resistance_display(uses)
            if uses > 0:
                lines.append(t(lang, "pill_effectiveness", pct=res["pct"], uses=uses))
                if res["next_threshold"] is not None:
                    lines.append(t(lang, "pill_next_threshold", next=res["next_threshold"], next_pct=res["next_pct"]))
            lines.append("")
            buttons.append([InlineKeyboardButton(
                f"💊 {t(lang, 'btn_usar')} {_cname(lang, 'pill', pill)}",
                callback_data=f"alch_use_{pill.id}_{inv_item.quality}"
            )])

        if total_pages > 1:
            buttons.extend(build_pagination_keyboard(page + 1, total_pages, "alch_pilulas_page_", lang))

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_menu")])

    await _send_or_edit(update, "\n".join(lines), InlineKeyboardMarkup(buttons))


async def alch_pilulas_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _raw = safe_parse_callback_int(query.data, "alch_pilulas_page_")
    if _raw is None:
        return
    page = _raw - 1
    context.args = [str(page)]
    await pilulas_command(update, context)


async def usar_pilula_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    parts = query.data.replace("alch_use_", "").split("_")
    pill_id = int(parts[0])
    quality = parts[1] if len(parts) > 1 else "normal"

    async with get_session_factory()() as session:
        # Onda 5 Fase 2 review: lock the player FOR UPDATE — every timed-buff
        # WRITER must serialize on this lock (the mini-app pill endpoint and
        # formation activation already do), otherwise two concurrent same-type
        # writers both pass their conflict checks and the buffs stack.
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            return

        lang = player.language or "en"

        pill = (await session.execute(select(PillCatalog).where(PillCatalog.id == pill_id))).scalar_one_or_none()
        if not pill:
            return

        if pill.effect_type not in ("cb_instant", "stat_boost", "hp_restore"):
            from core.formation_engine import FORMATION_PILL_COEXIST_TYPES
            active_buffs = await get_active_buffs(session, player.telegram_id)
            for buff in active_buffs:
                if buff.buff_type == pill.effect_type:
                    # A Formação row of a coexist type (qi_regen_boost) does
                    # NOT block the pill — separate rows; the tick's D-2
                    # diminishing stack governs the pair (mirror of the
                    # inventory/mini-app gates; [jogador] 2026-06-11).
                    if (pill.effect_type in FORMATION_PILL_COEXIST_TYPES
                            and (buff.source or "").startswith("formation:")):
                        continue
                    remaining = (buff.expires_at - datetime.now(timezone.utc)).total_seconds()
                    await safe_answer(query,
                        t(lang, "alch_buff_already_active", time=get_time_display(remaining)),
                        show_alert=True,
                    )
                    return

        # QoL 07/08 — review adversarial: este é o QUARTO caminho de uso de
        # pílula (/pilulas) e nunca teve guard de teto nenhum. Com o dantian
        # cheio a pílula era debitada por zero efeito — o mesmo defeito que
        # 30/07 fechou nos outros caminhos. Fica coerente com o /inventario, o
        # lote e o mini: recusa nomeada ANTES do débito, item no anel.
        # ⚠️ O guard de `stat_boost` (`stat_boost_cap_state`) continua a faltar
        # AQUI — é dívida anterior a esta onda, anotada no Cérebro, não corrigida
        # em silêncio junto com outra coisa.
        from core.alchemy_engine import refill_cap_state as _refill_state
        _rs = await _refill_state(session, player, pill)
        if _rs and _rs["at_cap"]:
            await safe_answer(query, t(lang, "pill_hp_full_kept" if _rs["kind"] == "hp"
                                             else "pill_qi_full_kept"), show_alert=True)
            return

        # Atomic decrement — guards against double-tap race condition
        upd = (
            sa_update(PlayerInventory)
            .where(
                PlayerInventory.player_id == player.telegram_id,
                PlayerInventory.item_type == "pill",
                PlayerInventory.item_id == pill_id,
                PlayerInventory.quality == quality,
                PlayerInventory.quantity > 0,
            )
            .values(quantity=PlayerInventory.quantity - 1)
            .returning(PlayerInventory.quantity)
        )
        new_quantity = (await session.execute(upd)).scalar_one_or_none()
        if new_quantity is None:
            await safe_answer(query, t(lang, "alch_no_pills"), show_alert=True)
            return
        if new_quantity == 0:
            await session.execute(
                delete(PlayerInventory).where(
                    PlayerInventory.player_id == player.telegram_id,
                    PlayerInventory.item_type == "pill",
                    PlayerInventory.item_id == pill_id,
                    PlayerInventory.quality == quality,
                )
            )

        effectiveness = await get_pill_effectiveness(session, player.telegram_id, pill)
        await increment_pill_usage(session, player.telegram_id, pill)
        effect_result = await apply_pill_effect(session, player, pill, quality, effectiveness=effectiveness)
        from core.achievement_engine import check_achievements
        pill_ach = await check_achievements(session, player.telegram_id, "pills_consumed", 1)
        from core.quest_engine import track_quest
        # QoL-relatos — 🩺 médico: a pílula usada pesa pelo seu tier.
        await track_quest(session, player.telegram_id, "use_pill", 1,
                          prof_weight_tier=pill.required_alchemy_tier)
        await session.commit()
        if pill_ach:
            from handlers.achievements import notify_achievements
            await notify_achievements(context, update.effective_user.id, pill_ach)

    await safe_answer(query)
    separator = "—" * 24
    quality_tag = f" ({quality.upper()})" if quality != "normal" else ""

    lines = [
        t(lang, "alch_pill_used", pill_name=_cname(lang, "pill", pill), quality=quality_tag),
        separator,
    ]

    if effect_result["type"] == "stat_boost":
        if effect_result.get("at_cap"):
            lines.append(t(lang, "pill_stat_at_cap", stat=effect_result["stat"], cap=effect_result["cap"]))
        else:
            lines.append(t(lang, "pill_stat_boost", stat=effect_result["stat"], gain=effect_result["gain"], new=effect_result["new_value"]))
    elif effect_result["type"] == "cb_instant":
        lines.append(t(lang, "alch_effect_cb_instant", value=format_number(effect_result["value"])))
    elif effect_result["type"] == "cb_boost":
        lines.append(t(lang, "alch_effect_cb_boost",
                        value=f"{(effect_result['value'] - 1) * 100:.0f}",
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "soul_boost":
        lines.append(t(lang, "alch_effect_soul_boost",
                        value=f"{(effect_result['value'] - 1) * 100:.0f}",
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "breakthrough_boost":
        lines.append(t(lang, "alch_effect_breakthrough",
                        value=f"{(effect_result['value'] - 1) * 100:.0f}",
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "qi_capacity":
        lines.append(t(lang, "alch_effect_qi_capacity", value=format_number(effect_result["value"])))
    elif effect_result["type"] == "body_tempering_progress":
        lines.append(t(lang, "pill_effect_body_tempering", value=effect_result["value"]))
    elif effect_result["type"] == "foundation_reroll":
        if effect_result.get("rerolled"):
            lines.append(t(lang, "pill_effect_foundation_reroll",
                            old=effect_result["old"], new=effect_result["new"]))
        elif effect_result.get("reason") == "sacred_protected":
            lines.append(t(lang, "pill_effect_foundation_reroll_sacred"))
        else:
            lines.append(t(lang, "pill_effect_foundation_reroll_na"))
    elif effect_result["type"] == "eternal_foundation_reroll":
        # v14.4 D-1c — Eternal Foundation Pill. Sacred awakening uses
        # a distinct line because the moment is *the* endgame payoff
        # (filosofia §5.3: profundidade > variedade — call it out).
        from core.foundation_engine import FOUNDATION_QUALITIES
        old_label = t(lang, FOUNDATION_QUALITIES.get(effect_result["old"], FOUNDATION_QUALITIES["low"])["label_key"]) if effect_result.get("old") else "—"
        new_label = t(lang, FOUNDATION_QUALITIES.get(effect_result["new"], FOUNDATION_QUALITIES["low"])["label_key"])
        if effect_result.get("sacred_awakened"):
            lines.append(t(lang, "pill_effect_eternal_sacred", old=old_label, new=new_label))
        else:
            lines.append(t(lang, "pill_effect_eternal_reroll", old=old_label, new=new_label))
    elif effect_result["type"] == "core_essence":
        if effect_result["value"] > 0:
            lines.append(t(lang, "pill_effect_core_essence",
                            value=effect_result["value"], total=effect_result["total"]))
        else:
            lines.append(t(lang, "pill_effect_core_essence_na"))
    elif effect_result["type"] == "qi_restore":
        if effect_result.get("at_cap"):
            lines.append(t(lang, "pill_effect_qi_restore_at_cap"))
        else:
            lines.append(t(lang, "pill_effect_qi_restore", value=format_number(effect_result["value"])))
    elif effect_result["type"] == "purity_boost":
        lines.append(t(lang, "pill_effect_purity", value=format_number(effect_result["value"])))
    elif effect_result["type"] == "revive":
        lines.append(t(lang, "pill_effect_revive"))
    elif effect_result["type"] == "all_boost":
        lines.append(t(lang, "pill_effect_all_boost",
                        value=effect_result["value"] - 1,
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "bp_boost":
        lines.append(t(lang, "pill_effect_bp_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "perception_boost":
        lines.append(t(lang, "pill_effect_perception_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "qi_regen_boost":
        # N-27 (Sprint v14.3): same fix as handlers/inventory.py — D-2 pills
        # ran but had no result branch, so the success message was empty.
        lines.append(t(lang, "pill_effect_qi_regen_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "defense_boost":
        lines.append(t(lang, "pill_effect_defense_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "luck_boost":
        lines.append(t(lang, "pill_effect_luck_boost",
                        value=effect_result.get("value", 1.0) - 1,
                        duration=effect_result.get("duration_minutes", 60)))
    elif effect_result["type"] == "dao_fragment_chance":
        lines.append(t(lang, "pill_effect_dao_chance",
                        value=effect_result["value"],
                        duration=effect_result["duration_minutes"]))
    elif effect_result["type"] == "hp_restore":
        lines.append(t(lang, "pill_effect_hp_restore", value=format_number(effect_result["value"]), pct=effect_result["pct"]))
        if effect_result.get("shield"):
            lines.append(t(lang, "pill_effect_hp_shield", value=format_number(effect_result["shield"])))

    if effectiveness < 1.0:
        pct = int(effectiveness * 100)
        lines.append(t(lang, "pill_effect_reduced", pct=pct))
    lines.append(separator)
    lines.append(t(lang, "alch_pill_consumed_flavor"))

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💊 {t(lang, 'inv_tab_pills')}", callback_data="inv_tab_pill_R")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="inv_main")],
    ])

    await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


@safe_handler
@rate_limit(1)
async def cauldrons_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        player_cauldrons = await get_player_cauldrons(session, player.telegram_id)
        await session.commit()

    if not player_cauldrons:
        lines = [t(lang, "alch_cauldrons_title"), "", t(lang, "alch_no_cauldron")]
        buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_menu")]]
        await _send_or_edit(update, "\n".join(lines), InlineKeyboardMarkup(buttons))
        return

    separator = "—" * 24
    lines = [t(lang, "alch_cauldrons_title"), separator, ""]
    buttons = []

    for pc, cauldron in player_cauldrons:
        equipped_mark = " ✅" if pc.is_equipped else ""
        max_dur = cauldron.max_durability
        dur_pct = int((pc.durability / max_dur) * 100) if max_dur > 0 else 0

        lines.append(f"{cauldron.emoji} *{_cname(lang, 'cauldron', cauldron)}* (Tier {cauldron.grade}){equipped_mark}")
        lines.append(f"  ⚗️ +{cauldron.success_bonus:.0f}% {t(lang, 'alch_success_bonus')} | 🔲 {cauldron.slots} slots")
        lines.append(f"  🔧 {t(lang, 'alch_durability')}: {pc.durability}/{max_dur} ({dur_pct}%)")

        if pc.is_equipped:
            if cauldron.grade < 7:
                lines.append(f"  ⬆️ _{t(lang, 'alch_can_upgrade')}_")
            else:
                lines.append(f"  ⭐ _{t(lang, 'alch_max_tier')}_")
        lines.append("")

        if not pc.is_equipped:
            buttons.append([InlineKeyboardButton(
                f"⚗️ {t(lang, 'btn_equipar')} {_cname(lang, 'cauldron', cauldron)}",
                callback_data=f"alch_equip_{cauldron.id}"
            )])

    # Buttons for equipped cauldron actions
    equipped_pc = next((pc for pc, _ in player_cauldrons if pc.is_equipped), None)
    if equipped_pc:
        equipped_cat = next((cat for pc, cat in player_cauldrons if pc.is_equipped), None)
        action_row = []
        if equipped_cat and equipped_cat.grade < 7:
            action_row.append(InlineKeyboardButton(
                f"⬆️ {t(lang, 'btn_upgrade_cauldron')}",
                callback_data="alch_upgrade_info"
            ))
        if equipped_pc.durability < equipped_cat.max_durability:
            action_row.append(InlineKeyboardButton(
                f"🔧 {t(lang, 'btn_repair_cauldron')}",
                callback_data="alch_repair_info"
            ))
        if action_row:
            buttons.append(action_row)

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_menu")])
    await _send_or_edit(update, "\n".join(lines), InlineKeyboardMarkup(buttons))


async def alch_cauldrons_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _raw = safe_parse_callback_int(query.data, "alch_cauldrons_page_")
    if _raw is None:
        return
    page = _raw - 1
    context.args = [str(page)]
    await cauldrons_command(update, context)


async def equip_cauldron_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    cauldron_id = safe_parse_callback_int(query.data, "alch_equip_")
    if cauldron_id is None:
        return

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return

        lang = player.language or "en"

        all_pc_stmt = select(PlayerCauldron).where(PlayerCauldron.player_id == player.telegram_id)
        all_pc = (await session.execute(all_pc_stmt)).scalars().all()

        target = None
        for pc in all_pc:
            if pc.cauldron_id == cauldron_id:
                target = pc
            pc.is_equipped = False

        if not target:
            await safe_answer(query, t(lang, "alch_not_owned"), show_alert=True)
            return

        target.is_equipped = True
        await session.commit()

        cauldron = (await session.execute(
            select(CauldronCatalog).where(CauldronCatalog.id == cauldron_id)
        )).scalar_one()

    text = t(lang, "alch_cauldron_equipped", emoji=cauldron.emoji, name=_cname(lang, 'cauldron', cauldron))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_menu")],
    ])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def upgrade_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show upgrade cost/requirements for the equipped cauldron."""
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)
        if not pc or not cauldron:
            await safe_answer(query, t(lang, "alch_no_cauldron"), show_alert=True)
            return

        if cauldron.grade >= 7:
            await safe_answer(query, t(lang, "alch_max_tier"), show_alert=True)
            return

        cost_info = await get_upgrade_cost_info(session, cauldron.grade, lang)
        next_cauldron = (await session.execute(
            select(CauldronCatalog).where(CauldronCatalog.grade == cauldron.grade + 1)
        )).scalar_one_or_none()

        # Check player's ore quantities
        ore_lines = []
        all_have = True
        for ore in cost_info["ores"]:
            p_ore = (await session.execute(
                select(PlayerOre).where(and_(
                    PlayerOre.player_id == player.telegram_id,
                    PlayerOre.ore_id == ore["ore_id"],
                ))
            )).scalar_one_or_none()
            owned = p_ore.quantity if p_ore else 0
            check = "✅" if owned >= ore["qty"] else "❌"
            if owned < ore["qty"]:
                all_have = False
            ore_lines.append(f"  {check} {ore['emoji']} {ore['name']}: {owned}/{ore['qty']}")

        stones_check = "✅" if player.spirit_stones >= cost_info["stones"] else "❌"
        if player.spirit_stones < cost_info["stones"]:
            all_have = False

        await session.commit()

    separator = "—" * 24
    success_pct = int(cost_info["success_rate"] * 100)
    lines = [
        f"⬆️ *{t(lang, 'alch_upgrade_title')}*",
        separator,
        f"{cauldron.emoji} {_cname(lang, 'cauldron', cauldron)} → {next_cauldron.emoji} {_cname(lang, 'cauldron', next_cauldron)}",
        "",
        f"📊 *{t(lang, 'alch_upgrade_stats')}:*",
        f"  ⚗️ +{cauldron.success_bonus:.0f}% → +{next_cauldron.success_bonus:.0f}%",
        f"  🔲 {cauldron.slots} → {next_cauldron.slots} slots",
        f"  🔧 {cauldron.max_durability} → {next_cauldron.max_durability} {t(lang, 'alch_durability')}",
        "",
        f"📦 *{t(lang, 'alch_upgrade_cost')}:*",
    ]
    lines.extend(ore_lines)
    lines.append(f"  {stones_check} 🪙 Spirit Stones: {format_number(player.spirit_stones)}/{format_number(cost_info['stones'])}")
    lines.append("")
    lines.append(f"🎯 {t(lang, 'alch_success_rate')}: *{success_pct}%*")

    if success_pct < 100:
        lines.append(f"⚠️ _{t(lang, 'alch_upgrade_fail_warning')}_")

    buttons = []
    if all_have:
        buttons.append([InlineKeyboardButton(
            f"⬆️ {t(lang, 'btn_confirm_upgrade')}",
            callback_data="alch_upgrade_confirm"
        )])
    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_cauldrons")])

    await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


async def upgrade_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute the cauldron upgrade."""
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)
        if not pc or not cauldron:
            await safe_answer(query, t(lang, "alch_no_cauldron"), show_alert=True)
            return

        result = await upgrade_cauldron(session, player, pc, cauldron)
        await session.commit()

    buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_cauldrons")]]

    if result["success"]:
        nc = result["new_cauldron"]
        text = t(lang, "alch_upgrade_success",
                 old_name=_cname(lang, 'cauldron', cauldron), new_emoji=nc.emoji, new_name=_cname(lang, 'cauldron', nc),
                 bonus=f"{nc.success_bonus:.0f}", slots=nc.slots,
                 durability=nc.max_durability,
                 stones=format_number(result["stones_spent"]))
    elif result["error"] == "failed_roll":
        text = t(lang, "alch_upgrade_failed",
                 name=_cname(lang, 'cauldron', cauldron),
                 stones_lost=format_number(result["stones_lost"]),
                 dur_lost=result["durability_lost"],
                 new_dur=result["new_durability"])
    elif result["error"] == "not_enough_stones":
        text = t(lang, "alch_not_enough_stones",
                 needed=0, current=player.spirit_stones)
    elif result["error"] == "missing_materials":
        text = t(lang, "alch_upgrade_missing_mats")
    else:
        text = t(lang, "alch_max_tier")

    await query.message.edit_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


async def repair_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show repair options for the equipped cauldron."""
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)
        if not pc or not cauldron:
            await safe_answer(query, t(lang, "alch_no_cauldron"), show_alert=True)
            return
        await session.commit()

    max_dur = cauldron.max_durability
    if pc.durability >= max_dur:
        await safe_answer(query, t(lang, "alch_repair_full"), show_alert=True)
        return

    missing = max_dur - pc.durability
    cost_per_10 = REPAIR_COST_PER_10 * cauldron.grade
    full_cost = ((missing + 9) // 10) * cost_per_10

    separator = "—" * 24
    lines = [
        f"🔧 *{t(lang, 'alch_repair_title')}*",
        separator,
        f"{cauldron.emoji} *{_cname(lang, 'cauldron', cauldron)}*",
        f"🔧 {t(lang, 'alch_durability')}: {pc.durability}/{max_dur}",
        "",
        f"💰 {t(lang, 'alch_repair_cost_info', cost_per_10=format_number(cost_per_10))}",
        f"🪙 {t(lang, 'alch_your_stones')}: {format_number(player.spirit_stones)}",
    ]

    buttons = []
    # Repair 50 points
    repair_50 = min(50, missing)
    cost_50 = ((repair_50 + 9) // 10) * cost_per_10
    if repair_50 > 0:
        buttons.append([InlineKeyboardButton(
            f"🔧 +{repair_50} ({format_number(cost_50)} SS)",
            callback_data="alch_repair_50"
        )])
    # Full repair
    if missing > 0:
        buttons.append([InlineKeyboardButton(
            f"🔧 {t(lang, 'btn_repair_full')} +{missing} ({format_number(full_cost)} SS)",
            callback_data="alch_repair_full"
        )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_cauldrons")])
    await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


async def repair_execute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute cauldron repair."""
    query = update.callback_query
    await safe_answer(query)

    amount = 50 if query.data == "alch_repair_50" else 9999  # 9999 = full repair

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)
        if not pc or not cauldron:
            return

        result = await repair_cauldron(session, player, pc, cauldron, amount)
        await session.commit()

    buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_cauldrons")]]

    if result["success"]:
        text = t(lang, "alch_repair_success",
                 emoji=cauldron.emoji, name=_cname(lang, 'cauldron', cauldron),
                 repaired=result["repaired"],
                 new_dur=result["new_durability"],
                 max_dur=result["max_durability"],
                 cost=format_number(result["cost"]))
    elif result["error"] == "not_enough_stones":
        text = t(lang, "alch_not_enough_stones",
                 needed=result["cost"], current=player.spirit_stones)
    else:
        text = t(lang, "alch_repair_full")

    await query.message.edit_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


async def _render_soul_fire(message, player_id):
    """Build and display the soul fire view on the given message."""
    async with get_session_factory()() as session:
        player = await _get_player(player_id, session)
        if not player:
            return
        lang = player.language or "en"

        sf = await get_or_create_soul_fire(session, player.telegram_id, player.realm)

        # Count beast cores
        inv = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == player.telegram_id,
                PlayerInventory.item_type == "beast_core",
                PlayerInventory.quantity > 0,
            )
        )).scalars().first()
        cores = inv.quantity if inv else 0
        await session.commit()

    sf_name = get_soul_fire_name(sf.fire_tier, lang)
    sf_bonus = get_soul_fire_bonus(sf.fire_tier)
    separator = "—" * 24

    lines = [
        f"🔥 *{t(lang, 'alch_soul_fire_title')}*",
        separator,
        f"🔥 {sf_name} (Tier {sf.fire_tier})",
        f"📈 {t(lang, 'alch_sf_bonus')}: +{sf_bonus:.0f}%",
    ]

    if sf.fire_tier < MAX_SOUL_FIRE_TIER:
        next_xp = SOUL_FIRE_TIERS[sf.fire_tier + 1]["xp_req"]
        filled = round((sf.fire_exp / next_xp) * 10) if next_xp > 0 else 10
        bar = "█" * filled + "░" * (10 - filled)
        next_name = get_soul_fire_name(sf.fire_tier + 1, lang)
        lines.append(f"{bar} {sf.fire_exp}/{next_xp} XP")
        lines.append(f"→ {next_name} (+{get_soul_fire_bonus(sf.fire_tier + 1):.0f}%)")
    else:
        lines.append(f"⭐ {t(lang, 'alch_sf_max_tier')}")

    lines.append(separator)
    lines.append(t(lang, "alch_sf_how_to_gain"))
    lines.append(f"  ⚗️ {t(lang, 'alch_sf_from_crafting')}")
    lines.append(f"  🐾 {t(lang, 'alch_sf_from_cores')}")
    lines.append("")
    lines.append(f"🐾 {t(lang, 'alch_sf_cores_owned', count=cores)}")

    buttons = []
    if cores > 0:
        buttons.append([InlineKeyboardButton(
            f"🔥 {t(lang, 'btn_feed_core')} (🐾 ×1)",
            callback_data="alch_feed_core",
        )])
    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_menu")])

    await message.edit_text("\n".join(lines), parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(buttons))


async def soul_fire_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show soul fire detail page."""
    query = update.callback_query
    await safe_answer(query)
    await _render_soul_fire(query.message, update.effective_user.id)


async def feed_core_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Feed a beast core to soul fire."""
    query = update.callback_query

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        if player.realm < SOUL_FIRE_MIN_REALM:
            await safe_answer(query, t(lang, "alch_sf_realm_too_low"), show_alert=True)
            return

        sf, xp_gained, leveled = await feed_beast_core_to_soul_fire(session, player.telegram_id, player.realm)
        if sf is None:
            await safe_answer(query, t(lang, "alch_sf_no_cores"), show_alert=True)
            return

        await session.commit()

    sf_name = get_soul_fire_name(sf.fire_tier, lang)
    text = t(lang, "alch_sf_fed_core", xp=xp_gained, name=sf_name, total_xp=sf.fire_exp)
    if leveled:
        text += "\n" + t(lang, "alch_soul_fire_levelup", name=sf_name)

    await safe_answer(query, text, show_alert=True)
    # Refresh the soul fire view
    await _render_soul_fire(query.message, update.effective_user.id)


async def recipes_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all recipes overview (unlocked/locked per tier)."""
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        pills = await get_all_pills(session)
        unlocked_ids = await get_unlocked_pill_ids(session, player.telegram_id)
        await session.commit()

    separator = "—" * 24
    lines = [
        f"📜 *{t(lang, 'alch_recipes_title')}*",
        separator,
        t(lang, "alch_recipes_total", unlocked=len([p for p in pills if p.id in unlocked_ids]), total=len(pills)),
        "",
    ]

    # Group by tier
    tier_groups: dict = {}
    for pill in pills:
        req_tier = pill.required_alchemy_tier or 1
        tier_groups.setdefault(req_tier, []).append(pill)

    for tier in sorted(tier_groups.keys()):
        tier_pills = tier_groups[tier]
        unlocked = [p for p in tier_pills if p.id in unlocked_ids]

        tier_name = get_tier_name(tier, lang)
        icons = "".join("✅" if p.id in unlocked_ids else "🔒" for p in tier_pills)
        lines.append(f"⚗️ T{tier} {tier_name}: {icons} ({len(unlocked)}/{len(tier_pills)})")

    lines.append("")
    lines.append(t(lang, "alch_recipes_hint"))

    buttons = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="alch_menu")]]
    await query.message.edit_text("\n".join(lines), parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


# ─── Pill Tribulation Mini-Game ─────────────────────────────────────────────

async def _show_tribulation_round(message, lang: str, trib_state: dict):
    """Display the current tribulation round with 3 action buttons."""
    rnd = trib_state["round"]
    pill_name = trib_state["pill_name"]
    pill_emoji = trib_state["pill_emoji"]
    successes = trib_state["successes"]
    separator = "—" * 24

    # Build round history display
    history_lines = []
    for h in trib_state["history"]:
        icon = "✅" if h["passed"] else "❌"
        history_lines.append(f"  {icon} {t(lang, h['label_key'])}")

    lines = [
        t(lang, "pill_trib_title"),
        separator,
        f"{pill_emoji} *{pill_name}*",
        "",
        t(lang, "pill_trib_round", round=rnd, total=PILL_TRIBULATION_ROUNDS),
    ]

    if history_lines:
        lines.extend(history_lines)
        lines.append("")

    progress_bar = "🟢" * successes + "⚫" * (PILL_TRIBULATION_ROUNDS - len(trib_state["history"]))
    lines.append(f"{t(lang, 'pill_trib_progress')}: {progress_bar} ({successes}/{PILL_TRIBULATION_PASS_THRESHOLD})")
    lines.append("")
    lines.append(t(lang, "pill_trib_choose"))

    buttons = [
        [InlineKeyboardButton(
            f"🛡️ {t(lang, 'pill_trib_protect')} (70%)",
            callback_data="alch_trib_protect"
        )],
        [InlineKeyboardButton(
            f"🔨 {t(lang, 'pill_trib_reinforce')} (50%, ×2)",
            callback_data="alch_trib_reinforce"
        )],
        [InlineKeyboardButton(
            f"⚡ {t(lang, 'pill_trib_sacrifice')} (90%, -10% Qi)",
            callback_data="alch_trib_sacrifice"
        )],
    ]

    await message.edit_text("\n".join(lines), parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(buttons))


async def pill_tribulation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle a pill tribulation round choice."""
    query = update.callback_query
    await safe_answer(query)

    trib_state = context.user_data.get("pill_tribulation")
    if not trib_state:
        return

    choice = query.data.replace("alch_trib_", "")
    if choice not in PILL_TRIBULATION_CHOICES:
        return

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        # Sacrifice QI costs 10% per round
        if choice == "sacrifice":
            qi_cost = int(player.qi * 0.10)
            player.qi = max(0, player.qi - qi_cost)

        # Roll the round
        passed = roll_tribulation_round(choice)
        choice_config = PILL_TRIBULATION_CHOICES[choice]

        bonus = 0
        if passed and choice_config.get("bonus_on_success"):
            bonus = 1  # Reinforce gives +1 bonus success

        trib_state["history"].append({
            "choice": choice,
            "passed": passed,
            "label_key": choice_config["label_key"],
        })

        if passed:
            trib_state["successes"] += 1 + bonus

        trib_state["round"] += 1

        # Check if tribulation is complete (all rounds played)
        if trib_state["round"] > PILL_TRIBULATION_ROUNDS:
            success = trib_state["successes"] >= PILL_TRIBULATION_PASS_THRESHOLD
            pill_id = trib_state["pill_id"]
            pill_name = trib_state["pill_name"]
            pill_emoji = trib_state["pill_emoji"]
            pill_tier = trib_state["pill_tier"]

            if success:
                # Add heavenly pill to inventory
                from core.utils import add_item_to_inventory
                added = await add_item_to_inventory(session, player.telegram_id, "pill", pill_id, 1, "heavenly")
                if not added:
                    from core.utils import _get_or_create_ring, _count_used_slots
                    ring = await _get_or_create_ring(session, player.telegram_id)
                    used = await _count_used_slots(session, player.telegram_id)
                    await session.commit()
                    del context.user_data["pill_tribulation"]
                    await safe_answer(query, t(lang, "inv_full", used=used, max=ring.max_slots), show_alert=True)
                    return

                # Track quests/achievements
                from core.quest_engine import track_quest
                # QoL-relatos — 4ª superfície de craft: a tribulação concedia XP de
                # ofício em SILÊNCIO (sem snapshot/delta, sem linha no resumo).
                # Com o peso, uma pílula celestial T4/T5 passaria a ser o maior
                # ganho do jogo sem o jogador ver — Lei §10. Fica disclosed.
                from core.profession_engine import prof_xp_delta, prof_xp_snapshot
                _prof_xp_before = prof_xp_snapshot(player)
                await track_quest(session, player.telegram_id, "craft_pill",
                                  prof_weight_tier=pill_tier)
                _prof_xp_gain = prof_xp_delta(player, _prof_xp_before)
                from core.achievement_engine import check_achievements
                ach_unlocked = await check_achievements(session, player.telegram_id, "pills_crafted", 1)
                from core.bp_engine import update_bp_mission
                await update_bp_mission(session, player.telegram_id, "craft_pills")
                from core.faction_engine import update_quest_progress as fac_quest_progress
                await fac_quest_progress(session, player.telegram_id, "craft_pill")
                await fac_quest_progress(session, player.telegram_id, "craft_pill_hq")

                await session.commit()
                del context.user_data["pill_tribulation"]

                if ach_unlocked:
                    from handlers.achievements import notify_achievements
                    await notify_achievements(context, update.effective_user.id, ach_unlocked)

                # Display success
                separator = "—" * 24
                history_lines = []
                for h in trib_state["history"]:
                    icon = "✅" if h["passed"] else "❌"
                    history_lines.append(f"  {icon} {t(lang, h['label_key'])}")

                lines = [
                    t(lang, "pill_trib_success_title"),
                    separator,
                    "",
                    t(lang, "pill_trib_success_body", pill_name=pill_name, pill_emoji=pill_emoji),
                    "",
                ] + history_lines + [
                    "",
                    t(lang, "alch_quality_display", quality="HEAVENLY"),
                ]

                # QoL-relatos — o XP de ofício desta tribulação, VISÍVEL (Lei §10).
                if _prof_xp_gain > 0:
                    from core.profession_engine import prof_weight as _prof_weight
                    _wt, _ww = _prof_weight(pill_tier)
                    lines.append(
                        t(lang, "prf_xp_gain_line_tier", xp=_prof_xp_gain,
                          tier=_wt, w=f"{_ww:g}")
                        if _wt else t(lang, "prf_xp_gain_line", xp=_prof_xp_gain)
                    )

                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"alch_craftar_tier_{pill_tier}")],
                    [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="alch_menu")],
                ])
                await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
            else:
                # Tribulation failed — apply penalties
                penalties = await apply_tribulation_failure(session, player)
                await session.commit()
                del context.user_data["pill_tribulation"]

                separator = "—" * 24
                history_lines = []
                for h in trib_state["history"]:
                    icon = "✅" if h["passed"] else "❌"
                    history_lines.append(f"  {icon} {t(lang, h['label_key'])}")

                lines = [
                    t(lang, "pill_trib_fail_title"),
                    separator,
                    "",
                    t(lang, "pill_trib_fail_body", pill_name=pill_name),
                    "",
                ] + history_lines + [
                    "",
                    t(lang, "pill_trib_fail_penalties",
                      dur=penalties["durability_lost"], qi=penalties["qi_lost"]),
                ]

                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"alch_craftar_tier_{pill_tier}")],
                    [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="alch_menu")],
                ])
                await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
            return

        # Not done yet — show next round
        await session.commit()

    await _show_tribulation_round(query.message, lang, trib_state)


@safe_handler
@rate_limit(1)
async def alchemy_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    data = query.data

    if data == "alch_menu" or data == "cmd_alquimia":
        await safe_answer(query)
        await alquimia_command(update, context)
        return True
    elif data == "alch_soul_fire":
        await soul_fire_view(update, context)
        return True
    elif data == "alch_feed_core":
        await feed_core_callback(update, context)
        return True
    elif data == "alch_recipes":
        await recipes_view(update, context)
        return True
    elif data == "alch_ervas":
        # Redirect to inventory herbs tab
        await safe_answer(query)
        from handlers.inventory import _herbs_tab
        async with get_session_factory()() as session:
            player = await _get_player(update.effective_user.id, session)
            if not player:
                return True
            lang = player.language or "en"
        await _herbs_tab(update, lang, player.telegram_id, 1)
        return True
    elif data == "alch_craftar":
        await safe_answer(query)
        await craftar_command(update, context)
        return True
    elif data == "alch_pilulas":
        # Redirect to inventory pills tab
        await safe_answer(query)
        from handlers.inventory import _pills_tab
        async with get_session_factory()() as session:
            player = await _get_player(update.effective_user.id, session)
            if not player:
                return True
            lang = player.language or "en"
        await _pills_tab(update, lang, player.telegram_id, 1)
        return True
    elif data == "alch_cauldrons":
        await safe_answer(query)
        await cauldrons_command(update, context)
        return True
    elif data.startswith("alch_trib_"):
        await pill_tribulation_callback(update, context)
        return True
    elif data.startswith("alch_craft_"):
        await craft_pill_callback(update, context)
        return True
    elif data.startswith("alch_use_"):
        await usar_pilula_callback(update, context)
        return True
    elif data.startswith("alch_equip_"):
        await equip_cauldron_callback(update, context)
        return True
    elif data == "alch_upgrade_info":
        await upgrade_info_callback(update, context)
        return True
    elif data == "alch_upgrade_confirm":
        await upgrade_confirm_callback(update, context)
        return True
    elif data == "alch_repair_info":
        await repair_info_callback(update, context)
        return True
    elif data in ("alch_repair_50", "alch_repair_full"):
        await repair_execute_callback(update, context)
        return True
    elif data.startswith("alch_craftar_tier_"):
        await alch_craftar_tier_callback(update, context)
        return True
    elif data.startswith("alch_pill_detail_"):
        await alch_pill_detail_callback(update, context)
        return True
    elif data.startswith("alch_ervas_page_"):
        await alch_ervas_page_callback(update, context)
        return True
    elif data.startswith("alch_pilulas_page_"):
        await alch_pilulas_page_callback(update, context)
        return True
    elif data.startswith("alch_cauldrons_page_"):
        # Legacy: cauldron pagination no longer used but kept for safety
        await safe_answer(query)
        await cauldrons_command(update, context)
        return True

    return False
