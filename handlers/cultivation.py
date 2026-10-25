import logging
logger = logging.getLogger(__name__)
from core.utils import escape_markdown, safe_handler, rate_limit, get_display_name, safe_answer, normalize_lang, resolve_chat_player_id
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, desc

from config import (
    MEDITATION_TYPES,
    MEDITATION_QI_MULT,
    REALM_NAMES,
    REALM_EMOJIS,
    RANKING_MEDALS,
    RANKING_LIMIT,
    REALM_MILESTONES,
    MILESTONE_FEATURE_NAMES,
    get_threshold,
)
from core.game_logic import (
    get_spirit_root_name,
    get_spirit_root_emoji,
    get_realm_display,
    get_progress_bar,
    format_number,
    calculate_cb_per_hour,
    estimate_time_to_breakthrough,
    get_time_display,
    calculate_offline_progress,
    get_player_equipment_stats,
    calculate_total_stats,
    _roman,
)
from core.i18n import t, get_supported_languages
from database.db import get_session_factory
from database.models import Player, PlayerArtifact, Tribulation
from handlers.start import main_menu_keyboard, help_command


from core.utils import escape_markdown, _get_player, _ensure_player


def _root_resonance_lines(player: Player, lang: str) -> list[str]:
    """Track A item 5 — the 'a tua raíz ressoa…' disclosure block shown under the
    spirit root in /status. PURE display: the elemental COMPOSITION (Wuxing + rare
    variant) + an honest teaser that the mechanical affinity awakens in the new
    world. NEVER a fake % — the gating/modifiers are wipe-bound (Lei §1, §5)."""
    try:
        from core.root_engine import get_root_elements, project_root_for_display
        proj = project_root_for_display(get_root_elements(player))
    except Exception:
        logger.exception("root resonance render failed")
        return []
    els = proj.get("elements") or []
    if not els:
        return []
    elements_str = " · ".join(
        f"{e['emoji']} {t(lang, 'root_el_' + e['key'])}" for e in els
    )
    archetype = t(lang, "root_archetype_" + proj["archetype"])
    out = [t(lang, "status_root_resonance", archetype=archetype, elements=elements_str)]
    if proj.get("has_variant"):
        out.append(t(lang, "status_root_variant"))
    out.append(t(lang, "status_root_resonance_future"))
    return out


def _lifespan_lines(player: Player, lang: str) -> list[str]:
    """Track A (B4) — the "Mar de Longevidade 寿海" disclosure block in /status.
    PURE display: the current realm's longevity ceiling + the next-realm CARROT
    ("rompe para X → N anos; o cultivo é a fuga da morte") + the immortal flag.
    NEVER a fake "morre em X" — nothing ticks/ages this wave; the clock is labelled
    as FUTURE ("desperta no novo mundo — ainda não corre"). Lei §1, §5."""
    try:
        from core.lifespan_engine import project_lifespan_for_display
        proj = project_lifespan_for_display(player)
    except Exception:
        logger.exception("lifespan render failed")
        return []
    out = [t(lang, "status_lifespan_title")]
    if proj.get("is_immortal"):
        out.append(t(lang, "status_lifespan_immortal"))
        return out
    out.append(t(lang, "status_lifespan_ceiling",
                 realm=proj["realm_name"], anos=proj["ceiling"]))
    # TEC-5 — o relógio deixou de ser só promessa: cada uso de arte proibida
    # QUEIMA anos, e o número tem de aparecer aqui (custo invisível = custo
    # nenhum, Lei §1/§10). Quem nunca queimou nada lê a linha de sempre.
    burned = int(proj.get("age_years") or 0)
    if burned > 0:
        out.append(t(lang, "status_lifespan_burned",
                     anos=burned, left=max(0, int(proj["ceiling"]) - burned)))
    if proj.get("next_realm") is not None:
        if proj.get("next_is_immortal"):
            out.append(t(lang, "status_lifespan_next_immortal", next=proj["next_realm_name"]))
        else:
            out.append(t(lang, "status_lifespan_next",
                         next=proj["next_realm_name"], anos=proj["next_ceiling"]))
    # A promessa de "o relógio ainda não corre" deixa de ser verdadeira no
    # instante em que ele queima o primeiro ano — então só a dizemos a quem
    # ainda não a contrariou (Lei §1: nunca uma tela mentindo sobre a outra).
    out.append(t(lang, "status_lifespan_future") if burned <= 0
               else t(lang, "status_lifespan_running"))
    return out


def _mind_sea_lines(player: Player, lang: str) -> list[str]:
    """Track A (B4) — the "Mar da Consciência 识海" disclosure block in /status.
    PURE display (REFRAME, no column — item-6 precedent): a depth TIER derived from
    soul_strength + perception + realm, the note that the player's LIVE Sentido
    Divino (神識) flows from here, and an HONEST future teaser. NEVER a fake % nor an
    "immune to X" claim — the soul-defense / alchemy-focus mechanics are wipe-bound
    (Lei §1, §3, §5). ZERO modifier: this reveals existing stats, changes nothing."""
    try:
        from core.mind_sea_engine import project_mind_sea_for_display
        proj = project_mind_sea_for_display(player)
    except Exception:
        logger.exception("mind sea render failed")
        return []
    tier = proj["tier"]
    out = [t(lang, "status_mind_sea_title")]
    out.append(t(lang, "status_mind_sea_tier",
                 emoji=proj["tier_emoji"],
                 tier=t(lang, "mind_sea_tier_" + tier),
                 lore=t(lang, "mind_sea_tier_" + tier + "_lore")))
    out.append(t(lang, "status_mind_sea_sense"))
    out.append(t(lang, "status_mind_sea_future"))
    return out


def _dao_heart_lines(player: Player, lang: str) -> list[str]:
    """Track A (B4) — the "Coração Dao 道心" disclosure block in /status. PURE
    display (REFRAME, no column — Mind Sea / item-6 precedent): the firmeza
    (conviction) TIER + the Will's tendency + the note that the Dao Heart is what
    holds the soul against the 心魔 Heart Demon (which ALREADY warns the player on
    divergence) + an HONEST future teaser (intention-weighted karma, choice verbs,
    the 心魔劫 Judgment — [jogador]'s feedback). NEVER a fake % nor an "immune to X"
    claim — the deep mechanics are wipe-bound (Lei §1, §3, §5). ZERO modifier: this
    SYNTHESIZES path + karma + the existing divergence; it changes no number and
    does NOT repeat the KarmaModal's scalar/bands."""
    try:
        from core.dao_heart_engine import project_dao_heart_for_display
        proj = project_dao_heart_for_display(player)
    except Exception:
        logger.exception("dao heart render failed")
        return []
    firmeza = proj["firmeza"]
    out = [t(lang, "status_dao_heart_title")]
    out.append(t(lang, "status_dao_heart_firmeza",
                 emoji=proj["firmeza_emoji"],
                 tier=t(lang, "dao_heart_tier_" + firmeza),
                 lore=t(lang, "dao_heart_tier_" + firmeza + "_lore")))
    out.append(t(lang, "status_dao_heart_" + proj["tendency_variant"],
                 tendency=t(lang, "dao_heart_tend_label_" + proj["tendency"])))
    out.append(t(lang, "status_dao_heart_" + proj["demon_variant"]))
    out.append(t(lang, "status_dao_heart_future"))
    return out


def _get_med_name(player: Player) -> str:
    from config import DAO_MEDITATION_TYPES
    lang = normalize_lang(player.language)
    med_key = player.meditation_type
    key_map = {"light": "meditation_light_name", "deep": "meditation_deep_name", "void": "meditation_void_name"}
    locale_key = key_map.get(med_key)
    if locale_key:
        return t(lang, locale_key)
    dao_med = DAO_MEDITATION_TYPES.get(med_key)
    if dao_med:
        n = dao_med["name"]
        return n.get(lang, n.get("pt", "???")) if isinstance(n, dict) else n
    med_info = MEDITATION_TYPES.get(med_key, {})
    return med_info.get("name", med_key or "Unknown")


def _get_med_desc(lang: str, med_key: str) -> str:
    key_map = {"light": "meditation_light_desc", "deep": "meditation_deep_desc", "void": "meditation_void_desc"}
    locale_key = key_map.get(med_key)
    if locale_key:
        return t(lang, locale_key)
    return MEDITATION_TYPES.get(med_key, {}).get("description", "")


def _get_med_display_name(lang: str, med_key: str) -> str:
    from config import DAO_MEDITATION_TYPES
    key_map = {"light": "meditation_light_name", "deep": "meditation_deep_name", "void": "meditation_void_name"}
    locale_key = key_map.get(med_key)
    if locale_key:
        return t(lang, locale_key)
    dao_med = DAO_MEDITATION_TYPES.get(med_key)
    if dao_med:
        n = dao_med["name"]
        return n.get(lang, n.get("pt", "???")) if isinstance(n, dict) else n
    return MEDITATION_TYPES.get(med_key, {}).get("name", med_key)


def _build_status_text(player: Player, buffs: list = None, artifacts: list = None, tribulation: Tribulation = None, sect_mult: float = 1.0, dao_cb_mult: float = 1.0, dao_summary: str = "", companion_info: dict = None, dao_bonuses: dict = None, vip_lvl: int = 0, partner_name: str = None, partner_cb_mult: float = 1.0, cooldown_info: dict = None, achievement_cb_mult: float = 1.0, max_hp: float = None, current_hp: float = None, display_power: int = None) -> str:
    from core.alchemy_engine import get_buff_cb_multiplier

    lang = normalize_lang(player.language)
    realm_display = get_realm_display(player.realm, player.sub_layer)
    root_name = get_spirit_root_name(player.spirit_root)
    root_emoji = get_spirit_root_emoji(player.spirit_root)
    threshold = get_threshold(player.realm, player.sub_layer)
    progress = get_progress_bar(player.cultivation_base, threshold)

    equip_stats = get_player_equipment_stats(artifacts) if artifacts else None
    comp_bonus = companion_info.get("bonuses") if companion_info else None

    # M-7: aggregate active perception_boost pill buffs so /status reflects pills
    # like Soul Clarity Pill in the perception value (and shows the breakdown).
    perception_pill_boost = 0.0
    if buffs:
        from datetime import datetime as _dt2, timezone as _tz2
        _now_p = _dt2.now(_tz2.utc)
        for _b in buffs:
            if getattr(_b, "buff_type", None) == "perception_boost" and _b.expires_at and _b.expires_at > _now_p:
                # buff_value is stored as multiplier (e.g. 1.25 for +25%); convert to additive boost.
                perception_pill_boost += max(0.0, float(_b.buff_value) - 1.0)

    interior_bonuses = {"soul_boost": 0.0, "perception_boost": perception_pill_boost, "luck_boost": 0.0}
    total_stats = calculate_total_stats(
        player, equip_stats,
        companion_bonus=comp_bonus,
        dao_bonuses=dao_bonuses,
        interior_bonuses=interior_bonuses,
    )

    buff_mult = get_buff_cb_multiplier(buffs) if buffs else 1.0
    companion_cb_mult = comp_bonus.get("cb_mult", 1.0) if comp_bonus else 1.0
    cb_hour = calculate_cb_per_hour(player, buff_multiplier=buff_mult, equip_stats=equip_stats, sect_mult=sect_mult, companion_cb_mult=companion_cb_mult, dao_cb_mult=dao_cb_mult, partner_cb_mult=partner_cb_mult, achievement_cb_mult=achievement_cb_mult)
    separator = "—" * 24

    cb_hour_display = format_number(cb_hour)
    all_mult_parts = []
    if buff_mult > 1.0:
        all_mult_parts.append(f"⚗️{buff_mult:.1f}")
    if buff_mult < 1.0:
        all_mult_parts.append(f"💔{buff_mult:.1f}")
    if equip_stats and equip_stats["cb_mult"] > 1.0:
        all_mult_parts.append(f"🛡️{equip_stats['cb_mult']:.1f}")
    if sect_mult > 1.0:
        all_mult_parts.append(f"🏯{sect_mult:.1f}")
    if companion_cb_mult > 1.0:
        all_mult_parts.append(f"🐉{companion_cb_mult:.2f}")
    if dao_cb_mult > 1.0:
        all_mult_parts.append(f"☯️{dao_cb_mult:.1f}")
    if partner_cb_mult > 1.0:
        all_mult_parts.append(f"💞{partner_cb_mult:.1f}")
    if all_mult_parts:
        cb_hour_display += f" (✨ {' '.join(all_mult_parts)})"

    # Onda C (A Alma do Cultivador) — /status shows the SAME aggregated Poder de
    # Combate as the header when progressao_visivel is ON (caller passes display_power);
    # OFF → the legacy total_battle_power (byte-identical). The boost annotations below
    # still describe the folded multipliers either way.
    bp_display = format_number(display_power if display_power is not None else total_stats["total_battle_power"])
    bp_boosts = []
    if equip_stats and equip_stats["bp_flat"] > 0:
        bp_boosts.append(f"🛡️+{format_number(equip_stats['bp_flat'])}")
    if equip_stats and equip_stats["bp_mult"] > 1.0:
        bp_boosts.append(f"🛡️×{equip_stats['bp_mult']:.1f}")
    if comp_bonus and comp_bonus.get("bp_mult", 1.0) > 1.0:
        bp_boosts.append(f"🐉×{comp_bonus['bp_mult']:.2f}")
    if dao_bonuses and dao_bonuses.get("bp_mult", 1.0) > 1.0:
        bp_boosts.append(f"☯️×{dao_bonuses['bp_mult']:.1f}")
    if dao_bonuses and dao_bonuses.get("all_stats_mult", 1.0) > 1.0:
        bp_boosts.append(f"💜×{dao_bonuses['all_stats_mult']:.1f}")
    if bp_boosts:
        bp_display += f" ({' '.join(bp_boosts)})"

    def _stat_with_boosts(base_val, stat_name):
        display = format_number(base_val)
        boosts = []
        eq_flat_key = f"{stat_name}_flat"
        eq_mult_key = f"{stat_name}_mult"
        comp_mult_key = f"{stat_name}_mult"
        if equip_stats and equip_stats.get(eq_flat_key, 0) > 0:
            boosts.append(f"🛡️+{format_number(equip_stats[eq_flat_key])}")
        if equip_stats and equip_stats.get(eq_mult_key, 1.0) > 1.0:
            boosts.append(f"🛡️×{equip_stats[eq_mult_key]:.1f}")
        if comp_bonus and comp_bonus.get(comp_mult_key, 1.0) > 1.0:
            # M-7: distinguish perception companion mult with 🐾 (paw) emoji per spec.
            comp_emoji = "🐾" if stat_name == "perception" else "🐉"
            boosts.append(f"{comp_emoji}×{comp_bonus[comp_mult_key]:.2f}")
        if dao_bonuses and dao_bonuses.get("all_stats_mult", 1.0) > 1.0:
            boosts.append(f"💜×{dao_bonuses['all_stats_mult']:.1f}")
        # M-7: surface active pill perception_boost as ⚗️× multiplier.
        if stat_name == "perception" and perception_pill_boost > 0:
            boosts.append(f"⚗️×{1.0 + perception_pill_boost:.2f}")
        if boosts:
            display += f" ({' '.join(boosts)})"
        return display

    prestige_header = ""
    if player.prestige_level > 0:
        from core.prestige_engine import get_prestige_title
        p_title = escape_markdown(get_prestige_title(player.prestige_level))
        prestige_header = f"👑 *{p_title}* ({t(lang, 'prestige_level_label', level=player.prestige_level)})\n"

    vip_str = f" [VIP {vip_lvl}]" if vip_lvl > 0 else ""
    title_str = f"\n🎖️ *[{escape_markdown(player.active_title)}]*" if player.active_title else ""

    # v16.0 — discreet continent line. One row, mini-app is canonical for
    # the rich modal; chat just surfaces where the cultivator currently is.
    continent_line = ""
    try:
        from core.continent_engine import (
            CONTINENT_META,
            DEFAULT_SPAWN_CONTINENT,
            is_valid_continent,
        )
        _cur = getattr(player, "current_continent", None) or DEFAULT_SPAWN_CONTINENT
        if not is_valid_continent(_cur):
            _cur = DEFAULT_SPAWN_CONTINENT
        _meta = CONTINENT_META[_cur]
        _name = t(lang, _meta["name_key"])
        continent_line = f"{t(lang, 'continent_status_label')}: {_meta['emoji']} {escape_markdown(_name)}\n"
    except Exception:
        continent_line = ""

    # v16.2.1 (emergent-path pivot) — discreet path line. R3+ only.
    # NULL path at R3+ shows the "still forming" hint (path emerges from
    # karma + actions — there's no pick). Crystallized path shows the
    # committed alignment. Pre-R3 stays hidden.
    # Reads `player.path` directly off the model — no extra session call.
    path_line = ""
    try:
        if int(getattr(player, "realm", 0) or 0) >= 3:
            from core.path_engine import PATH_META, is_valid_path
            _raw = getattr(player, "path", None)
            if _raw is None:
                path_line = t(lang, "path_not_crystallized_chat") + "\n"
            elif is_valid_path(_raw):
                _pmeta = PATH_META[_raw]
                _pname = t(lang, _pmeta["name_key"])
                path_line = t(lang, "path_status_label",
                              emoji=_pmeta["emoji"],
                              name=escape_markdown(_pname)) + "\n"
    except Exception:
        path_line = ""

    # v16.3 — Karma Spine. Discreet karma line. Visible when realm ≥ 3
    # OR karma != 0 (already drifted). Same "minimal noise" philosophy
    # as path_line — one row, 5 emoji bands, no progress bars in /status.
    karma_line = ""
    try:
        _karma_val = int(getattr(player, "karma", 0) or 0)
        _karma_realm = int(getattr(player, "realm", 0) or 0)
        if _karma_realm >= 3 or _karma_val != 0:
            from core.karma_engine import get_karma_emoji, get_karma_label
            _kemoji = get_karma_emoji(_karma_val)
            _kband = get_karma_label(_karma_val)
            _klabel = t(lang, f"karma_label_{_kband}")
            karma_line = t(lang, "karma_status_label",
                           emoji=_kemoji,
                           value=_karma_val,
                           label=escape_markdown(_klabel)) + "\n"
    except Exception:
        karma_line = ""

    # v16.4 — NPC Sect (Seita de Cultivo). One discreet line, only when affiliated
    # with one of the 9 eternal houses (distinct from a player guild).
    sect_line = ""
    try:
        _sid = getattr(player, "sect_id", None)
        from core.world_sects_engine import (
            is_valid_sect as _vs, WORLD_SECT_META as _WSM, get_rank_label_key as _rk,
        )
        if _vs(_sid):
            _meta = _WSM.get(_sid) or {}
            _sname = t(lang, _meta.get("name_key") or "")
            _semoji = _meta.get("emoji") or "🏯"
            _rank_label = t(lang, _rk(getattr(player, "sect_rank", None)))
            sect_line = t(lang, "wsect_status_label",
                          emoji=_semoji,
                          sect=escape_markdown(_sname),
                          rank=escape_markdown(_rank_label)) + "\n"
    except Exception:
        sect_line = ""

    lines = [
        f"☯️ *{escape_markdown(get_display_name(player))}*{vip_str}{title_str}",
        prestige_header + continent_line + path_line + karma_line + sect_line + f"🏯 Realm: {realm_display}",
    ]
    
    if player.realm >= 2 or player.foundation_quality:
        from core.foundation_engine import FOUNDATION_QUALITIES
        fq = player.foundation_quality
        if not fq and player.realm >= 2:
            fq = "medium"
        if fq:
            fq_info = FOUNDATION_QUALITIES.get(fq, FOUNDATION_QUALITIES["low"])
            label = t(lang, fq_info["label_key"])
            lines.append(t(lang, "status_foundation", quality=escape_markdown(label), emoji=fq_info["emoji"], mult=fq_info["stat_mult"]))
        else:
            lines.append(t(lang, "status_foundation_none"))
            
    # v14.13b BUGFIX: status display ignored qi_regen_boost pill buffs even
    # when active (chat report 2026-05-12 — "Qi vortex PIL is not applying
    # the buff to qi generation"). The engine applies the mult correctly; the
    # bug was purely visual. The stack math now lives in ONE place —
    # game_logic.qi_regen_stack_mult (tick + this display + mini-app chip,
    # which drifted the same way: owner report 2026-06-11).
    from core.game_logic import qi_regen_stack_mult
    _qi_regen_pill_mult = qi_regen_stack_mult(buffs)
    _med_qi_mult = MEDITATION_QI_MULT.get(player.meditation_type, 1.0) if player.is_meditating else 1.0
    # Companion qi recovery (Bamboo Panda) — [jogador] 2026-06-12 proved with a
    # with/without swap that the +N% never showed; the tick now applies it, so
    # the display must too. companion_info is built by the single caller.
    _comp_qi_mult = ((companion_info or {}).get("bonuses") or {}).get("qi_recovery_mult", 1.0)
    _qi_per_sec = (1.0 / 60.0) * _med_qi_mult * _qi_regen_pill_mult * _comp_qi_mult

    lines.extend([
        separator,
        t(lang, "status_cb", current=format_number(player.cultivation_base), threshold=format_number(threshold)),
        progress,
        separator,
        t(lang, "status_spirit_root", root_emoji=root_emoji, root_name=root_name),
        *_root_resonance_lines(player, lang),
        *_lifespan_lines(player, lang),
        *_mind_sea_lines(player, lang),
        *_dao_heart_lines(player, lang),
        t(lang, "status_cb_hour", value=cb_hour_display),
        "",
        f"⚔️ {t(lang, 'status_battle_power', value=bp_display)}",
        f"👻 {t(lang, 'status_soul_strength', value=_stat_with_boosts(total_stats['soul_strength'], 'soul'))}",
        f"🔮 {t(lang, 'status_perception', value=_stat_with_boosts(total_stats['perception'], 'perception'))}",
        f"🍀 {t(lang, 'status_luck', value=_stat_with_boosts(total_stats['luck'], 'luck'))}",
        separator,
        t(lang, "status_spirit_jade", value=format_number(player.spirit_jade)),
        t(lang, "status_spirit_stones", value=format_number(player.spirit_stones)),
        t(lang, "status_qi", current=f"{player.qi:.0f}", max=f"{total_stats['qi_capacity']:.0f}", per_sec=f"{_qi_per_sec:.2f}"),
    ])

    # HP display — Onda B (A Alma do Cultivador): the async CALLER (status_command)
    # passes the Alma's max_hp/current so /status shows the SAME HP as the arena and
    # the profile. Fallback to the raw calc keeps any sync caller working (== today).
    from core.combat_engine import get_max_hp, get_current_hp
    if max_hp is None:
        max_hp = get_max_hp(player)
    if current_hp is None:
        current_hp = get_current_hp(player)
    else:
        current_hp = min(current_hp, max_hp)
    hp_pct = int(current_hp / max_hp * 100) if max_hp > 0 else 100
    lines.append(t(lang, "status_hp", current=format_number(current_hp), max=format_number(max_hp), pct=hp_pct))
    
    if artifacts:
        equipped_lines = []
        for art in artifacts:
            if art.is_equipped:
                from database.models import ArtifactCatalog
                # This is a bit inefficient to import here but works for now. 
                # Better to have it joined in the query.
                pass
        # I'll add equipment summary to the lines
        lines.append(separator)
        lines.append(f"🛡️ *{t(lang, 'status_equipment')}:* /artefactos")
    
    lines.append(separator)

    if player.is_meditating and player.meditation_end:
        remaining = (player.meditation_end - datetime.now(timezone.utc)).total_seconds()
        if remaining > 0:
            med_name = _get_med_name(player)
            lines.append(t(lang, "status_meditating", med_name=med_name))
            lines.append(t(lang, "status_ends_in", time=get_time_display(remaining)))
        else:
            lines.append(t(lang, "status_idle"))
    else:
        lines.append(t(lang, "status_idle"))

    if buffs:
        lines.append("")
        for buff in buffs:
            remaining = (buff.expires_at - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                lines.append(f"{_fmt_buff_line(buff, lang)} — {get_time_display(remaining)}")

    if tribulation:
        lines.append("")
        lines.append(f"⚡ *{t(lang, 'status_tribulation_pending')}*")
        trib_realm_name = REALM_NAMES[tribulation.realm] if tribulation.realm < len(REALM_NAMES) else "???"
        lines.append(t(lang, "status_tribulation_demand", realm=trib_realm_name))
        lines.append(t(lang, "status_tribulation_cmd"))
        lines.append(separator)

    if cooldown_info:
        if cooldown_info.get("cooldown"):
            lines.append("")
            lines.append(f"⏳ *{t(lang, 'status_tribulation_cooldown_title')}*")
            remaining = cooldown_info.get("remaining_seconds", 0)
            lines.append(t(lang, "status_tribulation_cooldown", time=get_time_display(remaining)))
            lines.append(separator)
        elif cooldown_info.get("celestial_trial_required"):
            lines.append("")
            lines.append(
                t(
                    lang,
                    "celestial_trial_gate_blocked",
                    trial=cooldown_info.get("trial_num", 1),
                    sub=cooldown_info.get("sub_layer", 1),
                )
            )
            lines.append(separator)
        elif cooldown_info.get("body_tempering_required"):
            lines.append("")
            lines.append(
                t(lang, "tempering_realm8_blocked", current=cooldown_info.get("current_level", 0))
            )
            lines.append(separator)

    if player.foundation_locked:
        lines.append("")
        lines.append(t(lang, "foundation_locked_msg"))
        lines.append(separator)

    if player.realm >= 2:
        from core.golden_core_engine import CORE_QUALITIES
        cq = player.core_quality
        if not cq and player.realm >= 3:
            cq = "normal"
        if cq:
            cq_info = CORE_QUALITIES.get(cq, CORE_QUALITIES["normal"])
            cq_label = t(lang, cq_info["label_key"])
            lines.append(t(lang, "status_core", quality=escape_markdown(cq_label), emoji=cq_info["emoji"], mult=cq_info["stat_mult"]))
        else:
            from core.golden_core_engine import get_essence_cap, FOUNDATION_ESSENCE_CAP
            cap = get_essence_cap(player.foundation_quality)
            ce = player.core_essence or 0
            # Show essence with next tier hint
            if ce < 50:
                next_tier = "Normal"
                next_val = 50
            elif ce < 150:
                next_tier = "Superior"
                next_val = 150
            elif ce < 300:
                next_tier = "Perfect"
                next_val = 300
            else:
                next_tier = None
                next_val = None
            line = t(lang, "status_core_essence", current=ce, max=cap)
            if next_tier and next_val <= cap:
                line += f" (next: {next_tier} at {next_val})"
            lines.append(line)

    if player.core_locked:
        lines.append("")
        lines.append(t(lang, "core_locked_msg"))
        lines.append(separator)

    if player.realm >= 7:
        from core.body_tempering_engine import get_tempering_info, MAX_TEMPERING_LEVEL
        bt_level = player.body_tempering_level
        bt_info = get_tempering_info(bt_level)
        lines.append(t(lang, "status_body_tempering",
                       level=bt_level, max=MAX_TEMPERING_LEVEL,
                       emoji=bt_info["emoji"],
                       name=t(lang, bt_info["name_key"]),
                       mult=bt_info["hp_def_mult"]))

    if companion_info and companion_info.get("name"):
        comp_name = escape_markdown(companion_info["name"])
        comp_emoji = companion_info.get("emoji", "🐉")
        comp_level = companion_info.get("level", 1)
        lines.append(f"{comp_emoji} *{t(lang, 'status_companion')}:* {comp_name} (Lv.{comp_level})")

    if partner_name:
        lines.append(t(lang, "partner_status_has_partner", name=partner_name))

    if dao_summary:
        lines.append(dao_summary)
        lines.append(separator)

    ttb = estimate_time_to_breakthrough(player, equip_stats=equip_stats, sect_mult=sect_mult)
    if ttb is not None and ttb > 0:
        lines.append(t(lang, "status_next_breakthrough", time=get_time_display(ttb)))

    next_realm = player.realm + 1
    if next_realm in REALM_MILESTONES and next_realm < len(REALM_NAMES):
        m = REALM_MILESTONES[next_realm]
        realm_name = REALM_NAMES[next_realm]
        unlock_key = m["unlock"]
        unlock_name = MILESTONE_FEATURE_NAMES.get(unlock_key, {}).get(lang, unlock_key.replace("_", " ").title())
        lines.append(t(lang, "milestone_next_display",
                       realm_name=realm_name,
                       emoji=m["emoji"],
                       realm_num=next_realm,
                       unlock=unlock_name))

    return "\n".join(lines)


def _fmt_buff_line(buff, lang: str) -> str:
    """One active-buff line. explore_protection (Onda 5 Fase 2) is the first
    FRACTION-semantics buff_value (0.35 = 35% of the death-loss prevented) —
    the generic 'x{value}' multiplier render would read as a 65% DEBUFF."""
    label = _get_buff_label(buff.buff_type, lang)
    if buff.buff_type == "explore_protection":
        return f"🌫️ {label} -{int(round(float(buff.buff_value or 0) * 100))}%"
    if buff.buff_type == "pvp_sealed":
        # Hotfix "A Volta" (#12) — flag, não multiplicador: "x1.0" confundiria.
        return f"🔏 {label}"
    return f"⚗️ {label} x{buff.buff_value:.1f}"


def _get_buff_label(buff_type: str, lang: str = "en") -> str:
    # Use standard locale keys -> "buff_" + buff_type
    key = f"buff_{buff_type}"
    raw = t(lang, key)
    # Fallback to key itself if missing (t returns key if not found usually)
    if raw == key:
        labels = {
            "cb_boost": "CB Boost",
            "soul_boost": "Soul Boost",
            "breakthrough_boost": "Breakthrough",
            "purity_boost": "Purity Boost",
            "qi_restore": "Qi Restore",
            "bp_boost": "BP Boost",
            "perception_boost": "Perception Boost",
            "defense_boost": "Defense Boost",
            "luck_boost": "Luck Boost",
            "heartbreak": "Heartbreak",
            "cb_instant": "CB Instant",
        }
        # Final fallback: prettify the raw buff_type ("trib_insurance" → "Trib
        # Insurance") instead of letting escape_markdown strip the underscores
        # and produce gibberish like "tribinsurance" ([jogador] reported on
        # 2026-05-08: "alguém sabe o que é esse bufftrib ai que vai durar um
        # mês?"). Telegram Markdown v1 has no backslash escape, so the prior
        # display was unsalvageable.
        raw = labels.get(buff_type, buff_type.replace("_", " ").title())
    return escape_markdown(raw)


@safe_handler
@rate_limit(1)
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.alchemy_engine import get_active_buffs
    from database.models import Sect, SectMember
    from core.sect_engine import get_training_bonus
    from core.beast_engine import get_companion_beast, get_companion_bonuses

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        buffs = await get_active_buffs(session, player.telegram_id)
        
        stmt = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.is_equipped == True)
        arts = (await session.execute(stmt)).scalars().all()
        
        stmt_trib = select(Tribulation).where(
            Tribulation.player_id == player.telegram_id,
            Tribulation.realm == player.realm + 1,
            Tribulation.status.in_(["pending", "in_progress"])
        ).order_by(desc(Tribulation.started_at)).limit(1)
        trib = (await session.execute(stmt_trib)).scalars().first()
        
        cooldown_info = None
        if not trib:
             from core.game_logic import check_breakthrough
             cooldown_info = await check_breakthrough(player, session)
        
        sect_mult = 1.0
        stmt_sect = select(Sect.training_lvl).join(SectMember, Sect.id == SectMember.sect_id).where(SectMember.player_id == player.telegram_id)
        sect_lvl = (await session.execute(stmt_sect)).scalar()
        if sect_lvl is not None:
            sect_mult = get_training_bonus(sect_lvl)

        from core.dao_engine import get_player_dao_bonuses, build_status_dao_summary
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)
        dao_cb_mult = dao_bonuses.get("cb_mult", 1.0)
        dao_summary = await build_status_dao_summary(session, player.telegram_id, player.realm, lang=lang)
        
        from core.monetization import get_player_vip_level
        vip_lvl = await get_player_vip_level(session, player.telegram_id)

        companion_info = None
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        if comp_beast and comp_catalog:
            comp_bonuses = get_companion_bonuses(comp_beast, comp_catalog)
            companion_info = {
                "name": comp_catalog.name,
                "emoji": comp_catalog.emoji or "🐉",
                "level": comp_beast.level,
                "bonuses": comp_bonuses,
            }

        from core.partner_engine import get_player_partner, get_partner_cb_mult
        partner_rec, partner_player = await get_player_partner(session, player.telegram_id)
        partner_name = None
        partner_cb_mult = 1.0
        if partner_player:
            raw_pname = partner_player.dao_name or get_display_name(partner_player)
            partner_name = f"💞 {escape_markdown(raw_pname)}"
            partner_cb_mult = await get_partner_cb_mult(session, player.telegram_id)

        # Wave 3 (gated): so /status' CB/hr matches the actual accelerated tick.
        from core.achievement_engine import get_gated_achievement_multipliers
        achievement_cb_mult = float((await get_gated_achievement_multipliers(session, player.telegram_id)).get("cb_mult", 1.0) or 1.0)

        # Onda B/C — the ONE snapshot: HP (== arena/profile) + the aggregated Poder de
        # Combate (== the header). OFF → raw (byte-identical, zero extra query).
        from core.cultivator_soul import soul_max_hp, soul_current_hp
        from database.db import feature_enabled_for_world as _ffe_s
        _status_display_power = None
        if _ffe_s("combate_unificado") or _ffe_s("progressao_visivel"):
            from core.cultivator_soul import compute_cultivator_soul
            _soul_s = await compute_cultivator_soul(session, player)
            _status_max_hp = float(_soul_s["max_hp"])
            _status_display_power = _soul_s["display_power"] if _ffe_s("progressao_visivel") else None
        else:
            _status_max_hp = await soul_max_hp(session, player)
        _status_cur_hp = soul_current_hp(player, _status_max_hp)

        text = _build_status_text(
            player, buffs, arts, trib,
            sect_mult=sect_mult,
            dao_cb_mult=dao_cb_mult,
            dao_summary=dao_summary,
            companion_info=companion_info,
            dao_bonuses=dao_bonuses,
            vip_lvl=vip_lvl,
            partner_name=partner_name,
            partner_cb_mult=partner_cb_mult,
            cooldown_info=cooldown_info,
            achievement_cb_mult=achievement_cb_mult,
            max_hp=_status_max_hp,
            current_hp=_status_cur_hp,
            display_power=_status_display_power,
        )

        # Active celestial events section
        from handlers.events import get_active_events
        from datetime import datetime as _dt, timezone as _tz
        active_evs = await get_active_events(session)
        if active_evs:
            ev_lines = ["\n————————————————————————", t(lang, "status_celestial_events")]
            for ev in active_evs:
                now_ev = _dt.now(_tz.utc)
                delta = ev.expires_at - now_ev
                h = max(0, int(delta.total_seconds() // 3600))
                m = max(0, int((delta.total_seconds() % 3600) // 60))
                ev_lines.append(f"{ev.emoji} *{escape_markdown(ev.name)}* — ⏳ {h}h {m}m")
            text += "\n".join(ev_lines)

        # MV-7 — linha do ofício no /status (gated `profissoes`; OFF → texto
        # byte-idêntico ao de hoje). i18n-only, sem input do usuário → sem
        # escape necessário.
        try:
            from core.profession_engine import get_profession_view
            _pv = await get_profession_view(session, player, lang)
            if _pv and _pv.get("has"):
                text += "\n" + t(lang, "prf_status_line",
                                 emoji=_pv["emoji"], name=_pv["name"],
                                 tier=_pv["tier_name"])
        except Exception:
            pass

        # Passive check: jade accumulated (Migration 115 — lifetime counter is
        # the canonical value; balance stays as a grandfathered floor).
        _jade_val = max(int(player.spirit_jade or 0),
                        int(getattr(player, "lifetime_jade_earned", 0) or 0))
        if _jade_val > 0:
            from core.achievement_engine import check_achievements
            jade_ach = await check_achievements(session, player.telegram_id, "jade_accumulated", _jade_val)
        else:
            jade_ach = []
        await session.commit()

    async with get_session_factory()() as session:
        kb = await main_menu_keyboard(lang, player=player, session=session)
    if trib:
        buttons = [list(row) for row in kb.inline_keyboard]
        buttons.insert(0, [InlineKeyboardButton(t(lang, "btn_tribulation"), callback_data="cmd_tribulacao")])
        kb = InlineKeyboardMarkup(buttons)
    if player.foundation_locked:
        buttons = [list(row) for row in kb.inline_keyboard]
        buttons.insert(0, [InlineKeyboardButton(t(lang, "btn_foundation_start"), callback_data="foundation_start")])
        kb = InlineKeyboardMarkup(buttons)
    if player.core_locked:
        buttons = [list(row) for row in kb.inline_keyboard]
        buttons.insert(0, [InlineKeyboardButton(t(lang, "btn_core_form"), callback_data="core_formation_start")])
        kb = InlineKeyboardMarkup(buttons)

    try:
        if update.callback_query:
            await update.callback_query.message.edit_text(
                text, parse_mode="Markdown", reply_markup=kb
            )
        else:
            await update.message.reply_text(
                text, parse_mode="Markdown", reply_markup=kb
            )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error in status_command: {e}")

    if jade_ach:
        from handlers.achievements import notify_achievements
        await notify_achievements(context, update.effective_user.id, jade_ach)


@safe_handler
@rate_limit(1)
async def cultivar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.alchemy_engine import get_active_buffs, get_buff_cb_multiplier
    from database.models import Sect, SectMember
    from core.sect_engine import get_training_bonus

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        realm_display = get_realm_display(player.realm, player.sub_layer)
        buffs = await get_active_buffs(session, player.telegram_id)
        
        stmt = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.is_equipped == True)
        arts = (await session.execute(stmt)).scalars().all()
        equip_stats = get_player_equipment_stats(arts)

        # Sect Bonus
        sect_mult = 1.0
        stmt_sect = select(Sect.training_lvl).join(SectMember, Sect.id == SectMember.sect_id).where(SectMember.player_id == player.telegram_id)
        sect_lvl = (await session.execute(stmt_sect)).scalar()
        if sect_lvl is not None:
            sect_mult = get_training_bonus(sect_lvl)

        buff_mult = get_buff_cb_multiplier(buffs) if buffs else 1.0
        # Wave 3 (gated): reflect the achievement cb bonus in the displayed rate.
        from core.achievement_engine import get_gated_achievement_multipliers
        _ach_cb = float((await get_gated_achievement_multipliers(session, player.telegram_id)).get("cb_mult", 1.0) or 1.0)
        cb_hour = calculate_cb_per_hour(player, buff_multiplier=buff_mult, equip_stats=equip_stats, sect_mult=sect_mult, achievement_cb_mult=_ach_cb)
        threshold = get_threshold(player.realm, player.sub_layer)
        progress = get_progress_bar(player.cultivation_base, threshold)
        ttb = estimate_time_to_breakthrough(player, equip_stats=equip_stats, sect_mult=sect_mult, buff_multiplier=buff_mult)

        cb_hour_display = format_number(cb_hour)
        if buff_mult > 1.0 or equip_stats["cb_mult"] > 1.0 or sect_mult > 1.0:
            total_mult = buff_mult * equip_stats["cb_mult"] * sect_mult
            cb_hour_display += f" (✨ x{total_mult:.1f})"

        lines = [
            t(lang, "cultivar_title"),
            "",
            t(lang, "cultivar_realm", realm=realm_display),
            t(lang, "status_cb", current=format_number(player.cultivation_base), threshold=format_number(threshold)),
            progress,
            "",
            t(lang, "cultivar_cb_hour", value=cb_hour_display),
        ]

        if player.is_meditating:
            med_name = _get_med_name(player)
            lines.append(t(lang, "cultivar_meditation_active", name=med_name))
            lines.append(t(lang, "cultivar_multiplier", value=f"{player.meditation_multiplier:.1f}"))

        if buffs:
            for buff in buffs:
                remaining = (buff.expires_at - datetime.now(timezone.utc)).total_seconds()
                if remaining > 0:
                    lines.append(f"{_fmt_buff_line(buff, lang)} — {get_time_display(remaining)}")

        if ttb is not None and ttb > 0:
            lines.append("")
            lines.append(t(lang, "status_next_breakthrough", time=get_time_display(ttb)))

        if player.foundation_locked:
            lines.append("")
            lines.append(t(lang, "foundation_locked_msg"))

        if player.core_locked:
            lines.append("")
            lines.append(t(lang, "core_locked_msg"))

        lines.append(t(lang, "cultivar_qi_flows"))

        await session.commit()

    buttons = [
        [
            InlineKeyboardButton(t(lang, "btn_meditar"), callback_data="cmd_meditar"),
            InlineKeyboardButton(t(lang, "btn_status"), callback_data="cmd_status"),
        ],
    ]
    if player.foundation_locked:
        buttons.insert(0, [InlineKeyboardButton(t(lang, "btn_foundation_start"), callback_data="foundation_start")])
    if player.core_locked:
        buttons.insert(0, [InlineKeyboardButton(t(lang, "btn_core_form"), callback_data="core_formation_start")])
    if player.realm >= 7:
        buttons.append([InlineKeyboardButton(t(lang, "btn_body_tempering"), callback_data="tempering_menu")])

    kb = InlineKeyboardMarkup(buttons)

    text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


@safe_handler
@rate_limit(1)
async def meditar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"

        if player.is_meditating:
            remaining = 0
            if player.meditation_end:
                remaining = max(0, (player.meditation_end - datetime.now(timezone.utc)).total_seconds())

            # Auto-end expired meditation if tick didn't catch it
            if remaining <= 0:
                # Fix 2026-08-06 (report do [jogador]): este ramo dispara EXATAMENTE
                # quando a meditação cumpriu o tempo — e era o que mais doía,
                # porque apagava o estado sem creditar o `cultivate`. "Quem
                # finaliza credita" (fix de 2026-07-21) aplica-se aqui também.
                from core.game_logic import credit_meditation_if_earned
                await credit_meditation_if_earned(
                    session, player, player.meditation_type, player.meditation_end)
                player.is_meditating = False
                player.meditation_type = None
                player.meditation_end = None
                player.meditation_multiplier = 1.0
                await session.commit()
                # Fall through to normal meditation menu below
            else:
                med_name = _get_med_name(player)
                qi_mult = MEDITATION_QI_MULT.get(player.meditation_type, 1.0)
                qi_rate = f"{0.02 * qi_mult:.2f}"
                hp_regen_rates = {"light": 1, "deep": 5, "void": 10}
                hp_rate = hp_regen_rates.get(player.meditation_type, 0)
                text = (
                    f"{t(lang, 'meditar_active_title')}\n\n"
                    f"{t(lang, 'meditar_active_type', name=med_name)}\n"
                    f"{t(lang, 'meditar_active_mult', value=f'{player.meditation_multiplier:.1f}')}\n"
                    f"{t(lang, 'meditation_qi_regen_info', rate=qi_rate, mult=f'{qi_mult:.0f}')}\n"
                )
                if hp_rate > 0:
                    text += f"{t(lang, 'meditation_hp_regen', rate=hp_rate)}\n"
                text += (
                    f"{t(lang, 'meditar_active_remaining', time=get_time_display(remaining))}\n"
                )
                text += f"\n{t(lang, 'meditar_cancel_question')}"

                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(t(lang, "btn_cancel_meditation"), callback_data="cancel_meditation")],
                    [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_cultivar")],
                ])

                await session.commit()

                if update.callback_query:
                    await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
                else:
                    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
                return

        lines = [
            t(lang, "meditar_choose_title"),
        ]

        buttons = []
        for key, med in MEDITATION_TYPES.items():
            available = player.realm >= med["min_realm"]
            has_qi = player.qi >= med["qi_cost"] if med["qi_cost"] > 0 else True

            status = ""
            if not available:
                min_realm_name = REALM_NAMES[med["min_realm"]]
                status = t(lang, "meditar_req_realm", realm=min_realm_name)
            elif not has_qi:
                status = t(lang, "meditar_req_qi")

            display_name = _get_med_display_name(lang, key)
            description = _get_med_desc(lang, key)
            qi_text = f" | 🌀 {med['qi_cost']} Qi" if med["qi_cost"] > 0 else ""
            qi_mult = MEDITATION_QI_MULT.get(key, 1.0)
            qi_rate = f"{0.02 * qi_mult:.1f}"
            lines.append(
                f"*{escape_markdown(display_name)}*{status}\n"
                f"  ✨ x{med['multiplier']:.1f} CB | ⚡ {qi_rate} QI/s ({qi_mult:.0f}x) | ⏱️ {med['duration_minutes']}min{qi_text}\n"
                f"  _{escape_markdown(description)}_\n"
            )

            if available and has_qi:
                buttons.append([InlineKeyboardButton(display_name, callback_data=f"meditate_{key}")])

        buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_cultivar")])

        text = "\n".join(lines)
        kb = InlineKeyboardMarkup(buttons)

        await session.commit()

        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def start_meditation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    med_key = query.data.replace("meditate_", "")
    med_info = MEDITATION_TYPES.get(med_key)
    if not med_info:
        return

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return

        lang = player.language or "en"

        if player.realm < med_info["min_realm"]:
            await safe_answer(query, t(lang, "meditar_alert_realm"), show_alert=True)
            return

        if med_info["qi_cost"] > 0 and player.qi < med_info["qi_cost"]:
            await safe_answer(query, t(lang, "meditar_alert_qi"), show_alert=True)
            return

        if player.is_meditating:
            # Fix 2026-08-06 (report do [jogador]): começar uma meditação nova por
            # cima de uma JÁ CUMPRIDA descartava o crédito da antiga.
            from core.game_logic import credit_meditation_if_earned
            await credit_meditation_if_earned(
                session, player, player.meditation_type, player.meditation_end)
            player.is_meditating = False
            player.meditation_type = None
            player.meditation_end = None
            player.meditation_multiplier = 1.0

        now = datetime.now(timezone.utc)
        player.is_meditating = True
        player.meditation_type = med_key
        player.meditation_end = now + timedelta(minutes=med_info["duration_minutes"])
        player.meditation_multiplier = med_info["multiplier"]
        player.last_online = now

        if med_info["qi_cost"] > 0:
            player.qi = max(0, player.qi - med_info["qi_cost"])

        # Fix 2026-07-21 — crédito-no-START removido (paridade com a decisão
        # SEC v16.6 que já o tinha removido do mini-app): creditar a duração
        # INTEIRA ao iniciar permitia start→cancelar→start = crédito infinito
        # de 'cultivate' (com os storylets do MV-5 isso virou faucet de pedras).
        # O crédito agora acontece SEMPRE na CONCLUSÃO real, por quem finalizar
        # (process_tick / meditation_sweep / poll do mini — exactly-once).
        await session.commit()

    display_name = _get_med_display_name(lang, med_key)

    mult_str = f"{med_info['multiplier']:.1f}"

    text = (
        f"{t(lang, 'meditar_started_title')}\n\n"
        f"{t(lang, 'meditar_started_type', name=display_name)}\n"
        f"{t(lang, 'meditar_started_mult', value=mult_str)}\n"
        f"{t(lang, 'meditar_started_duration', minutes=med_info['duration_minutes'])}\n\n"
        f"{t(lang, 'meditar_started_flavor')}"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(lang, "btn_status"), callback_data="cmd_status"),
            InlineKeyboardButton(t(lang, "btn_cultivar"), callback_data="cmd_cultivar"),
        ],
    ])

    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def cancel_meditation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return

        lang = player.language or "en"

        # Fix 2026-08-06 (report do [jogador]) — "cancelar" uma meditação que já
        # cumpriu o tempo é FINALIZAR: credita (anti-farm intacto — cancelar
        # antes do fim continua a valer zero).
        from core.game_logic import credit_meditation_if_earned
        await credit_meditation_if_earned(
            session, player, player.meditation_type, player.meditation_end)
        player.is_meditating = False
        player.meditation_type = None
        player.meditation_end = None
        player.meditation_multiplier = 1.0
        player.last_online = datetime.now(timezone.utc)
        await session.commit()

    text = (
        f"{t(lang, 'meditar_cancelled_title')}\n\n"
        f"{t(lang, 'meditar_cancelled_body')}"
    )

    async with get_session_factory()() as session:
        menu_kb = await main_menu_keyboard(lang, player=player, session=session)
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=menu_kb)


@safe_handler
@rate_limit(1)
async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main ranking menu with category selection."""
    lang = "en"
    category = None

    # Check if a category was specified via callback
    if update.callback_query and update.callback_query.data:
        data = update.callback_query.data
        if data.startswith("ranking_"):
            category = data.replace("ranking_", "")

    async with get_session_factory()() as session:
        user = update.effective_user
        player = None
        if user:
            player = await _get_player(user.id, session)
            if player:
                lang = normalize_lang(player.language)

        if category == "power":
            text = await _ranking_power(session, player, lang)
        elif category == "sects":
            text = await _ranking_sects(session, player, lang)
        elif category == "arena":
            text = await _ranking_arena(session, player, lang)
        elif category == "cultivation":
            text = await _ranking_cultivation(session, player, lang)
        else:
            # Default: show cultivation ranking
            text = await _ranking_cultivation(session, player, lang)

    # Category buttons
    buttons = [
        [
            InlineKeyboardButton(f"🧘 {t(lang, 'rank_cat_cultivation')}", callback_data="ranking_cultivation"),
            InlineKeyboardButton(f"⚔️ {t(lang, 'rank_cat_power')}", callback_data="ranking_power"),
        ],
        [
            InlineKeyboardButton(f"🏯 {t(lang, 'rank_cat_sects')}", callback_data="ranking_sects"),
            InlineKeyboardButton(f"🏟️ {t(lang, 'rank_cat_arena')}", callback_data="ranking_arena"),
        ],
        [InlineKeyboardButton(t(lang, "btn_main_menu"), callback_data="nav_main")],
    ]
    kb = InlineKeyboardMarkup(buttons)

    try:
        if update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise


async def _ranking_cultivation(session, player, lang):
    """Ranking by realm + sub_layer + cultivation base."""
    from database.models import Sect, SectMember

    stmt = (
        select(Player, Sect.name.label("sect_name"))
        .outerjoin(SectMember, Player.telegram_id == SectMember.player_id)
        .outerjoin(Sect, SectMember.sect_id == Sect.id)
        .order_by(Player.prestige_level.desc(), Player.realm.desc(), Player.sub_layer.desc(), Player.cultivation_base.desc())
        .limit(RANKING_LIMIT)
    )
    result = await session.execute(stmt)
    players_data = result.all()

    if not players_data:
        return t(lang, "ranking_empty")

    lines = [f"🧘 *{t(lang, 'rank_cultivation_title')}*", "─" * 24]

    for i, (p, sect_name) in enumerate(players_data):
        position = RANKING_MEDALS[i] if i < len(RANKING_MEDALS) else f"`{i + 1}.`"
        realm_emoji = REALM_EMOJIS[min(p.realm, len(REALM_EMOJIS) - 1)]
        realm_name = REALM_NAMES[min(p.realm, len(REALM_NAMES) - 1)]
        name = "???" if p.shadow_mode else escape_markdown(get_display_name(p))
        cb_display = format_number(p.cultivation_base)
        title_str = f" *[{escape_markdown(p.active_title)}]*" if p.active_title else ""

        prestige_str = f"💠R{p.prestige_level} " if p.prestige_level > 0 else ""
        sect_str = f"\n     🏯 {escape_markdown(sect_name)}" if sect_name else ""
        is_me = " 👈" if player and p.telegram_id == player.telegram_id else ""

        lines.append(
            f"{position} {prestige_str}{realm_emoji} *{name}*{title_str}{is_me}\n"
            f"     {realm_name} {_roman(p.sub_layer)} | CB: {cb_display}{sect_str}"
        )

    return "\n".join(lines)


async def _ranking_power(session, player, lang):
    """Ranking by total battle power (approximated from DB stats)."""
    from database.models import Sect, SectMember
    stmt = (
        select(Player, Sect.name.label("sect_name"))
        .outerjoin(SectMember, Player.telegram_id == SectMember.player_id)
        .outerjoin(Sect, SectMember.sect_id == Sect.id)
        .order_by(Player.battle_power.desc())
        .limit(RANKING_LIMIT)
    )
    result = await session.execute(stmt)
    players_data = result.all()

    if not players_data:
        return t(lang, "ranking_empty")

    lines = [f"⚔️ *{t(lang, 'rank_power_title')}*", "─" * 24]

    for i, (p, sect_name) in enumerate(players_data):
        position = RANKING_MEDALS[i] if i < len(RANKING_MEDALS) else f"`{i + 1}.`"
        name = "???" if p.shadow_mode else escape_markdown(get_display_name(p))
        bp_display = format_number(p.battle_power)
        realm_emoji = REALM_EMOJIS[min(p.realm, len(REALM_EMOJIS) - 1)]
        title_str = f" *[{escape_markdown(p.active_title)}]*" if p.active_title else ""

        prestige_str = f"💠R{p.prestige_level} " if p.prestige_level > 0 else ""
        sect_str = f"\n     🏯 {escape_markdown(sect_name)}" if sect_name else ""
        is_me = " 👈" if player and p.telegram_id == player.telegram_id else ""

        lines.append(
            f"{position} {prestige_str}{realm_emoji} *{name}*{title_str}{is_me}\n"
            f"     ⚔️ BP: {bp_display}{sect_str}"
        )

    return "\n".join(lines)


async def _ranking_sects(session, player, lang):
    """Ranking of sects by member count and total buildings."""
    from database.models import Sect

    stmt = (
        select(Sect)
        .order_by(Sect.member_count.desc())
        .limit(15)
    )
    sects = (await session.execute(stmt)).scalars().all()

    if not sects:
        return t(lang, "ranking_empty")

    lines = [f"🏯 *{t(lang, 'rank_sects_title')}*", "─" * 24]

    for i, s in enumerate(sects):
        position = RANKING_MEDALS[i] if i < len(RANKING_MEDALS) else f"`{i + 1}.`"
        total_lvl = s.training_lvl + s.herb_garden_lvl + s.forge_lvl + s.library_lvl + s.defense_lvl + s.spirit_vein_lvl
        lines.append(
            f"{position} 🏯 *{escape_markdown(s.name)}*\n"
            f"     👥 {s.member_count}/{s.max_members} | 🏗️ Lvl {total_lvl} | 💎 {format_number(s.spirit_stones)}"
        )

    return "\n".join(lines)


async def _ranking_arena(session, player, lang):
    """Ranking by arena ELO."""
    from database.models import ArenaRanking, Sect, SectMember
    stmt = (
        select(Player, ArenaRanking.elo_points, ArenaRanking.wins, ArenaRanking.losses, Sect.name.label("sect_name"))
        .join(ArenaRanking, Player.telegram_id == ArenaRanking.player_id)
        .outerjoin(SectMember, Player.telegram_id == SectMember.player_id)
        .outerjoin(Sect, SectMember.sect_id == Sect.id)
        .where((ArenaRanking.wins + ArenaRanking.losses) > 0)
        .order_by(ArenaRanking.elo_points.desc())
        .limit(RANKING_LIMIT)
    )
    result = await session.execute(stmt)
    players_data = result.all()

    if not players_data:
        return t(lang, "ranking_empty")

    lines = [f"🏟️ *{t(lang, 'rank_arena_title')}*", "─" * 24]

    for i, (p, elo, wins, losses, sect_name) in enumerate(players_data):
        position = RANKING_MEDALS[i] if i < len(RANKING_MEDALS) else f"`{i + 1}.`"
        name = "???" if p.shadow_mode else escape_markdown(get_display_name(p))
        title_str = f" *[{escape_markdown(p.active_title)}]*" if p.active_title else ""
        
        prestige_str = f"💠R{p.prestige_level} " if p.prestige_level > 0 else ""
        sect_str = f"\n     🏯 {escape_markdown(sect_name)}" if sect_name else ""
        is_me = " 👈" if player and p.telegram_id == player.telegram_id else ""

        lines.append(
            f"{position} {prestige_str}*{name}*{title_str}{is_me}\n"
            f"     🏆 ELO: {elo} | W: {wins} L: {losses}{sect_str}"
        )

    return "\n".join(lines)


@safe_handler
@rate_limit(1)
async def idioma_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        await session.commit()

    languages = get_supported_languages()
    buttons = []
    for lng in languages:
        buttons.append([InlineKeyboardButton(
            f"{lng['flag']} {lng['name']}",
            callback_data=f"set_lang_{lng['code']}"
        )])
    buttons.append([InlineKeyboardButton(t(lang, "btn_back_settings"), callback_data="cmd_settings")])

    text = t(lang, "language_title")
    kb = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    new_lang = query.data.replace("set_lang_", "")

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return

        player.language = new_lang
        await session.commit()

    text = t(new_lang, "language_changed")
    async with get_session_factory()() as session:
        menu_kb = await main_menu_keyboard(new_lang, player=player, session=session)
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=menu_kb)


# M-9: notification preferences UI
async def _render_notif_menu(update, context, player, session):
    from core.notification_prefs import get_prefs, PREF_KEYS
    lang = player.language or "en"
    prefs = await get_prefs(session, player.telegram_id)

    buttons = []
    for key in PREF_KEYS.keys():
        on = prefs.get(key, True)
        emoji = "🔔" if on else "🔕"
        label = t(lang, f"notif_pref_{key}")
        buttons.append([InlineKeyboardButton(
            f"{emoji} {label}",
            callback_data=f"notif_toggle_{key}",
        )])
    # v14.5 Q-1 — auto-progress dungeon lives on the Player table (not in
    # PlayerNotificationPref). Render its row inline with a distinct emoji so
    # players can tell automations apart from notification toggles.
    auto_on = bool(getattr(player, "auto_progress_dungeon", False))
    auto_emoji = "🤖" if auto_on else "🚫"
    buttons.append([InlineKeyboardButton(
        f"{auto_emoji} {t(lang, 'notif_pref_auto_progress_dungeon')}",
        callback_data="notif_toggle_auto_progress_dungeon",
    )])
    buttons.append([InlineKeyboardButton(t(lang, "btn_back_settings"), callback_data="cmd_settings")])
    text = t(lang, "notif_menu_title") + "\n\n" + t(lang, "notif_menu_hint")

    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(
                text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.warning("notif menu edit failed: %s", e)
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
        )


async def notif_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        await _render_notif_menu(update, context, player, session)
        await session.commit()


# v16.2 — Path sub-menu (Settings Hub canonical entry-point for path).
# Renders the current path + philosophy and points to the Mini-App for the
# actual pick. No standalone /path command — Mini-app first per Lei §1 +
# `feedback_miniapp_canonical_surface` memory.
async def path_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.path_engine import PATH_META, is_valid_path, DEFAULT_PATH

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        realm = int(getattr(player, "realm", 0) or 0)
        raw = getattr(player, "path", None)
        await session.commit()

    title = f"☯️ *{t(lang, 'path_modal_title')}*"
    subtitle = t(lang, "settings_path_subtitle")

    body_parts = [title, "", subtitle, ""]

    if realm < 3:
        body_parts.append(t(lang, "path_not_crystallized_pre_r3_chat"))
    elif raw is None:
        body_parts.append(t(lang, "path_not_crystallized_post_r3_chat"))
    else:
        if is_valid_path(raw):
            meta = PATH_META[raw]
            name = t(lang, meta["name_key"])
            phil = t(lang, meta["philosophy_key"])
            body_parts.append(t(lang, "path_status_label",
                                emoji=meta["emoji"],
                                name=escape_markdown(name)))
            body_parts.append("")
            body_parts.append(f"_{escape_markdown(phil)}_")

    text = "\n".join(body_parts)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_back_settings"), callback_data="cmd_settings")],
    ])

    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(
                text, parse_mode="Markdown", reply_markup=kb
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.warning("path menu edit failed: %s", e)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


# v16.3 — Karma sub-menu (Settings Hub canonical entry-point for karma).
# Renders the current karma + band + a CTA pointing to the Mini-App
# KarmaModal for the full gauge / recent log / divergence view. No
# standalone /karma command — mini-app first per the same Lei §1 rule
# that governs path_command. Chat surface is intentionally minimal:
# 1 status line in /status + 1 sub-menu in /conf for drill-in.
async def karma_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from core.karma_engine import (
        get_karma_emoji, get_karma_label, KARMA_EVENTS, project_world_reactions,
    )

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        karma_val = int(getattr(player, "karma", 0) or 0)
        karma_raw_path = getattr(player, "path", None)
        await session.commit()

    emoji = get_karma_emoji(karma_val)
    band = get_karma_label(karma_val)
    band_label = t(lang, f"karma_label_{band}")

    title = f"⚖️ *{t(lang, 'karma_status_label', emoji=emoji, value=karma_val, label=escape_markdown(band_label))}*"
    subtitle = t(lang, "settings_karma_subtitle")
    intro = t(lang, "karma_emergent_chat_intro")

    # Track A item 4 — chat parity for "o que o mundo vê": distance to the next
    # karmic threshold + a one-line hint that the world reacts to karma (Lei §1).
    nxt = (project_world_reactions(karma_val, karma_raw_path) or {}).get("next") or {}
    if nxt.get("kind") == "crystallize":
        # projected = the Path the CURRENT karma would lock as at R3 (rogue for
        # the neutral band) — the honest disclosure, not a karma "distance".
        proj = nxt.get("projected") or "rogue"
        if proj not in ("rogue", "righteous", "demonic"):
            proj = "rogue"
        prog = t(lang, f"karma_chat_progress_crystallize_{proj}")
    elif nxt.get("kind") == "diverge":
        prog = t(lang, "karma_chat_progress_diverge", n=int(nxt.get("distance") or 0))
    else:
        prog = t(lang, "karma_chat_progress_settled")
    reacts_hint = t(lang, "karma_chat_world_reacts")

    body_parts = [
        title, "", subtitle, "", f"_{escape_markdown(intro)}_",
        "", escape_markdown(prog), "", f"_{escape_markdown(reacts_hint)}_",
    ]

    text = "\n".join(body_parts)
    # TEC-5 — quando o Coração-Demônio tem porta (divergência / escolha
    # pendente), o /karma LEVA lá. Gated: sem a flag o teclado é o de sempre
    # (Lei §1 — nunca prometer um botão que não existe).
    rows = []
    try:
        from core.forbidden_path_engine import forbidden_on
        if forbidden_on():
            rows.append([InlineKeyboardButton(
                t(lang, "fpd_btn_open"), callback_data="fpd_menu")])
    except Exception:
        logger.debug("karma menu fpd CTA failed", exc_info=True)
    rows.append([InlineKeyboardButton(t(lang, "btn_back_settings"),
                                      callback_data="cmd_settings")])
    kb = InlineKeyboardMarkup(rows)

    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(
                text, parse_mode="Markdown", reply_markup=kb
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.warning("karma menu edit failed: %s", e)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def notif_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    key = query.data.replace("notif_toggle_", "", 1)
    from core.notification_prefs import toggle_pref, PREF_KEYS
    # v14.5 Q-1 — auto_progress_dungeon is stored on Player, not the prefs row.
    if key == "auto_progress_dungeon":
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            if not player:
                return
            player.auto_progress_dungeon = not bool(getattr(player, "auto_progress_dungeon", False))
            await session.commit()
            await _render_notif_menu(update, context, player, session)
        return
    if key not in PREF_KEYS:
        return
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        await toggle_pref(session, player.telegram_id, key)
        await session.commit()
        await _render_notif_menu(update, context, player, session)


# Settings hub — central /conf menu where all player-side configurations live.
# When adding a new player-controllable toggle (privacy, display, audio, etc.),
# add a row here that opens the sub-menu. See CLAUDE.md "Configurações de jogador".
async def _render_config_menu(update, context, player):
    lang = player.language or "en"
    text = t(lang, "settings_menu_title") + "\n\n" + t(lang, "settings_menu_hint")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_settings_language"), callback_data="cmd_idioma")],
        [InlineKeyboardButton(t(lang, "btn_settings_notifications"), callback_data="cmd_notif")],
        # v16.2 — Path sub-menu. Identity entry-point (mini-app first); the
        # sub-menu shows the current path + a CTA to open the picker in the
        # mini-app. Settings hub stays the canonical discoverable surface
        # per CLAUDE.md (no standalone /path command).
        [InlineKeyboardButton(t(lang, "btn_settings_path"), callback_data="cmd_path")],
        # v16.3 — Karma sub-menu. Same pattern as Path; the chat shows
        # the current value + band + emergent explanation, the mini-app
        # KarmaModal has the gauge / recent log / divergence card.
        [InlineKeyboardButton(t(lang, "btn_settings_karma"), callback_data="cmd_karma")],
        # 性 2026-09-07 — a escolha do genero vive AQUI porque a regra da casa
        # (CLAUDE.md) diz que toda preferencia do jogador vive no hub `/conf`,
        # nunca num comando avulso. So' aparece com `cultivador` ON: com a flag
        # OFF nao ha figura para o genero escolher, e um menu que nao muda nada
        # visivel seria um beco (Lei §1).
    ] + ([[InlineKeyboardButton(t(lang, "btn_settings_gender"), callback_data="cmd_genero")]]
         if _gender_on() else []) + [
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_main")],
    ])
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(
                text, parse_mode="Markdown", reply_markup=kb
            )
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.warning("config menu edit failed: %s", e)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


def _gender_on() -> bool:
    """A flag `cultivador` deste mundo. Import local: o topo deste modulo nao
    importa `feature_enabled_for_world`, e importa-lo la' arrastaria o router
    de mundos para um ficheiro que nao precisa dele."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("cultivador"))
    except Exception:
        return False


# ─── 性 O GENERO (2026-09-07, Mig 140) ───────────────────────────────────────
#
# Ordem do owner: escolhido, nao sorteado — **excepcao declarada** a espinha
# "nascer e' destino" (raca, raizes e mundo continuam dados que ninguem escolhe).
#
# ⚠️ O que este menu NAO faz: NADA fica gated por genero. Em particular o
# casamento (`dao_partners`), que existe desde antes desta coluna e continua
# gender-free — fazer o par exigir masculino/feminino REMOVERIA algo que
# jogadores reais fazem hoje.
#
# ⚠️ "Ainda nao escolhi" e' uma opcao de primeira classe, nao a ausencia de
# resposta: os ~248 do beta nascem assim, e o jogo desenha-os com o 背影.
_GENDER_CHOICES = ("male", "female", None)


@safe_handler
@rate_limit(1)
async def genero_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"
        cur = getattr(player, "gender", None)
        cur_label = (t(lang, "gender_" + cur) if cur in ("male", "female")
                     else t(lang, "gender_unset"))
        text = "\n\n".join([
            t(lang, "gender_title"),
            t(lang, "gender_current", value=cur_label),
            t(lang, "gender_hint"),
        ])
        rows = []
        for g in ("male", "female"):
            mark = " ✓" if cur == g else ""
            rows.append([InlineKeyboardButton(t(lang, "gender_" + g) + mark,
                                              callback_data="set_gender_" + g)])
        rows.append([InlineKeyboardButton(t(lang, "gender_unset") + (" ✓" if not cur else ""),
                                          callback_data="set_gender_none")])
        rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_settings")])
        kb = InlineKeyboardMarkup(rows)
        if update.callback_query:
            try:
                await update.callback_query.message.edit_text(
                    text, parse_mode="Markdown", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning("gender menu edit failed: %s", e)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def set_gender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    raw = (query.data or "").replace("set_gender_", "")
    value = raw if raw in ("male", "female") else None
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        # ⚠️ Nao ha' custo, nao ha' cooldown e nao ha' consequencia mecanica:
        # o genero e' COSMETICO (Lei §4 — jade compra aceleracao, flex cosmetico
        # ou caminho alternativo; nunca poder). Se um dia custar, e' decisao do
        # owner e escreve-se aqui.
        player.gender = value
        await session.commit()
        lang = player.language or "pt"
    await safe_answer(query, t(lang, "gender_saved"))
    await genero_command(update, context)


@safe_handler
@rate_limit(1)
async def config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        await _render_config_menu(update, context, player)
        await session.commit()


async def foundation_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player or not player.foundation_locked:
            return
            
        lang = player.language or "en"
        from core.foundation_engine import get_scaled_thresholds
        from core.game_logic import calculate_total_stats, get_player_equipment_stats, get_active_technique_bonuses
        from core.alchemy_engine import get_active_buffs
        from core.beast_engine import get_companion_beast, get_companion_bonuses
        from core.dao_engine import get_player_dao_bonuses
        from database.models import PlayerArtifact
        
        # Calculate total stats with all multipliers
        buffs = await get_active_buffs(session, player.telegram_id)
        stmt_arts = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.is_equipped == True)
        arts = (await session.execute(stmt_arts)).scalars().all()
        equip_stats = get_player_equipment_stats(arts)
        
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        comp_bonus = get_companion_bonuses(comp_beast, comp_catalog) if (comp_beast and comp_catalog) else None
        
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)
        interior_bonuses = await get_active_technique_bonuses(session, player.telegram_id)
        
        total_stats = calculate_total_stats(
            player, 
            equip_stats=equip_stats, 
            companion_bonus=comp_bonus, 
            dao_bonuses=dao_bonuses,
            interior_bonuses=interior_bonuses
        )

        text = t(lang, "foundation_trial_title") + "\n\n" + t(lang, "foundation_trial_intro")
        text += "\n\n" + t(lang, "foundation_system_explanation")

        # Calculate chances using prestige-scaled thresholds
        scaled = get_scaled_thresholds(player)
        base_soul = scaled["soul"]
        base_perception = scaled["perception"]
        base_luck = scaled["luck"]
        
        soul_val = total_stats["soul_strength"]
        perc_val = total_stats["perception"]
        luck_val = total_stats["luck"]
        
        soul_ready = t(lang, "foundation_status_ready") if soul_val >= base_soul else t(lang, "foundation_status_not_ready")
        perc_ready = t(lang, "foundation_status_ready") if perc_val >= base_perception else t(lang, "foundation_status_not_ready")
        
        luck_contrib = (luck_val / base_luck) * 0.6
        needed_rand = 0.7 - luck_contrib
        if needed_rand <= 0:
            luck_chance = 100
        elif needed_rand > 0.4:
            luck_chance = 0
        else:
            luck_chance = int(((0.4 - needed_rand) / 0.4) * 100)
            
        stats_text = [
            t(lang, "foundation_chances_title"),
            t(lang, "foundation_chance_soul", current=int(soul_val), req=base_soul, status=soul_ready),
            t(lang, "foundation_chance_perception", current=int(perc_val), req=base_perception, status=perc_ready),
            t(lang, "foundation_chance_luck", current=int(luck_val), chance=luck_chance)
        ]
        if luck_chance < 100:
            stats_text.append(t(lang, "foundation_luck_tip"))

        text += "\n" + "\n".join(stats_text)
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_foundation_start"), callback_data="foundation_confirm")],
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="cmd_status")]
        ])
        
        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def foundation_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player or not player.foundation_locked:
            return

        lang = player.language or "en"
        from core.foundation_engine import calculate_foundation_trial, FOUNDATION_QUALITIES
        from core.game_logic import calculate_total_stats, get_player_equipment_stats, get_active_technique_bonuses
        from core.alchemy_engine import get_active_buffs
        from core.beast_engine import get_companion_beast, get_companion_bonuses
        from core.dao_engine import get_player_dao_bonuses
        from database.models import PlayerArtifact

        # Calculate total stats with all multipliers for the actual trial
        buffs = await get_active_buffs(session, player.telegram_id)
        stmt_arts = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.is_equipped == True)
        arts = (await session.execute(stmt_arts)).scalars().all()
        equip_stats = get_player_equipment_stats(arts)
        
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        comp_bonus = get_companion_bonuses(comp_beast, comp_catalog) if (comp_beast and comp_catalog) else None
        
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)
        interior_bonuses = await get_active_technique_bonuses(session, player.telegram_id)
        
        total_stats = calculate_total_stats(
            player, 
            equip_stats=equip_stats, 
            companion_bonus=comp_bonus, 
            dao_bonuses=dao_bonuses,
            interior_bonuses=interior_bonuses
        )
        
        trial_info = calculate_foundation_trial(player, total_stats)
        player.foundation_quality = trial_info["quality"]
        player.foundation_locked = False

        # Avançar para realm 2 (sub_layer reseta para 1 no breakthrough regular, mas como pulamos o check, fazemos manualmente)
        player.realm = 2
        player.sub_layer = 1
        from core.game_logic import _apply_realm_up_bonus
        _apply_realm_up_bonus(player)
        player.qi = player.qi_capacity

        # BUG [jogador] 2026-08-11 — resistência a pílulas é POR REINO (contrato da
        # docstring); só o breakthrough simples resetava. Todo realm-up limpa.
        try:
            from core.alchemy_engine import reset_medicine_resistance
            await reset_medicine_resistance(session, player.telegram_id)
        except Exception:
            logger.warning("foundation trial: medicine resistance reset failed", exc_info=True)

        from core.bp_engine import update_bp_mission
        await update_bp_mission(session, player.telegram_id, "foundation_trial")
        await session.commit()
        
        from core.visual_engine import foundation_art
        quality = trial_info["quality"]
        fq_info_result = FOUNDATION_QUALITIES.get(quality, FOUNDATION_QUALITIES["low"])
        quality_label = t(lang, fq_info_result["label_key"])
        art = foundation_art(quality, quality_label, lang=lang)

        lines = [art, "", t(lang, "foundation_trial_title"), ""]

        for res in trial_info["results"]:
            if res["trial"] == "soul":
                lines.append(t(lang, "foundation_trial_soul_pass" if res["passed"] else "foundation_trial_soul_fail"))
            elif res["trial"] == "perception":
                lines.append(t(lang, "foundation_trial_perception_pass" if res["passed"] else "foundation_trial_perception_fail"))
            elif res["trial"] == "luck":
                lines.append(t(lang, "foundation_trial_luck_pass" if res["passed"] else "foundation_trial_luck_fail"))

        lines.append("")

        # Show final result text
        quality_key = f"foundation_result_{quality}"
        lines.append(t(lang, quality_key))
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_status"), callback_data="cmd_status")]])
        
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
        
        # Announcement Se perfect
        if trial_info["quality"] == "perfect":
            from database.models import Sect, SectMember
            sect_name = ""
            stmt = select(Sect.name).join(SectMember, Sect.id == SectMember.sect_id).where(SectMember.player_id == player.telegram_id)
            s_name = (await session.execute(stmt)).scalar_one_or_none()
            if s_name:
                sect_name = f" [{s_name}]"
                
            from core.announcement_engine import broadcast
            import asyncio
            asyncio.create_task(broadcast("foundation_announcement_perfect", pref_key="anomaly_global", name=escape_markdown(player.dao_name or get_display_name(player)) + escape_markdown(sect_name)))


async def core_formation_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player or not player.core_locked:
            return

        lang = player.language or "en"
        from core.golden_core_engine import calculate_core_quality, FOUNDATION_TO_MAX_CORE, CORE_QUALITIES
        from core.foundation_engine import FOUNDATION_QUALITIES

        result = calculate_core_quality(player)
        foundation = player.foundation_quality or "medium"
        max_core = FOUNDATION_TO_MAX_CORE.get(foundation, "normal")

        fq_info = FOUNDATION_QUALITIES.get(foundation, FOUNDATION_QUALITIES["medium"])
        foundation_label = t(lang, fq_info["label_key"])
        max_core_info = CORE_QUALITIES.get(max_core, CORE_QUALITIES["normal"])
        max_core_label = t(lang, max_core_info["label_key"])
        predicted_info = CORE_QUALITIES.get(result["quality"], CORE_QUALITIES["normal"])
        predicted_label = t(lang, predicted_info["label_key"])

        text = t(lang, "core_formation_title") + "\n\n" + t(
            lang, "core_formation_intro",
            essence=player.core_essence or 0,
            foundation=escape_markdown(foundation_label),
            max_core=escape_markdown(max_core_label),
            predicted=escape_markdown(predicted_label),
        )

        if result["was_capped"]:
            text += "\n\n" + t(lang, "core_capped_warning",
                               foundation=escape_markdown(foundation_label),
                               max_core=escape_markdown(max_core_label))

        text += "\n\n" + t(lang, "core_essence_guide")

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_core_form"), callback_data="core_form_confirm")],
            [InlineKeyboardButton(t(lang, "btn_core_wait"), callback_data="nav_cultivo")],
        ])

        await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def core_form_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player or not player.core_locked:
            return

        lang = player.language or "en"
        from core.golden_core_engine import calculate_core_quality, CORE_QUALITIES
        from core.foundation_engine import FOUNDATION_QUALITIES

        result = calculate_core_quality(player)
        quality = result["quality"]

        player.core_quality = quality
        player.core_locked = False
        player.realm = 3
        player.sub_layer = 1
        player.cultivation_base = 0.0
        from core.game_logic import _apply_realm_up_bonus
        _apply_realm_up_bonus(player)
        player.qi = player.qi_capacity  # Full qi on golden core formation

        # BUG [jogador] 2026-08-11 — resistência a pílulas é POR REINO; todo realm-up limpa.
        try:
            from core.alchemy_engine import reset_medicine_resistance
            await reset_medicine_resistance(session, player.telegram_id)
        except Exception:
            logger.warning("core formation: medicine resistance reset failed", exc_info=True)

        from core.bp_engine import update_bp_mission
        await update_bp_mission(session, player.telegram_id, "golden_core")
        await session.commit()

        from core.visual_engine import core_formation_art
        cq_info_result = CORE_QUALITIES.get(quality, CORE_QUALITIES["normal"])
        core_label = t(lang, cq_info_result["label_key"])
        art = core_formation_art(quality, core_label, lang=lang)

        lines = [art, "", t(lang, "core_formation_title"), "", t(lang, f"core_result_{quality}")]

        if result["was_capped"]:
            fq_info = FOUNDATION_QUALITIES.get(player.foundation_quality or "medium", FOUNDATION_QUALITIES["medium"])
            foundation_label = t(lang, fq_info["label_key"])
            max_core_info = CORE_QUALITIES.get(result["max_allowed"], CORE_QUALITIES["normal"])
            max_core_label = t(lang, max_core_info["label_key"])
            lines.append("\n" + t(lang, "core_capped_warning",
                                  foundation=escape_markdown(foundation_label),
                                  max_core=escape_markdown(max_core_label)))

        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_status"), callback_data="cmd_status")]])
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)

        if quality == "perfect":
            from database.models import Sect, SectMember
            stmt = select(Sect.name).join(SectMember, Sect.id == SectMember.sect_id).where(SectMember.player_id == player.telegram_id)
            s_name = (await session.execute(stmt)).scalar_one_or_none()
            sect_suffix = f" [{s_name}]" if s_name else ""
            from core.announcement_engine import broadcast
            import asyncio
            asyncio.create_task(broadcast("core_announcement_perfect", pref_key="anomaly_global", name=escape_markdown(player.dao_name or get_display_name(player)) + escape_markdown(sect_suffix)))


async def tempering_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return

        lang = player.language or "en"
        from core.body_tempering_engine import (
            get_tempering_info, get_next_level_info, can_temper,
            MAX_TEMPERING_LEVEL, MIN_REALM_REQUIRED,
        )

        if player.realm < MIN_REALM_REQUIRED:
            await query.message.edit_text(t(lang, "tempering_need_realm"), parse_mode="Markdown")
            return

        # Calculate total battle power using the same components shown in /status
        # (equipment + companion + dao bonuses), so UI values stay consistent.
        stmt_arts = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.is_equipped == True)
        arts = (await session.execute(stmt_arts)).scalars().all()
        equip_stats = get_player_equipment_stats(arts) if arts else None

        from core.beast_engine import get_companion_beast, get_companion_bonuses
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        comp_bonus = get_companion_bonuses(comp_beast, comp_catalog) if (comp_beast and comp_catalog) else None

        from core.dao_engine import get_player_dao_bonuses
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)

        total_stats = calculate_total_stats(
            player,
            equip_stats,
            companion_bonus=comp_bonus,
            dao_bonuses=dao_bonuses,
        )
        total_bp = total_stats["total_battle_power"]

        current = player.body_tempering_level
        current_info = get_tempering_info(current)
        next_info = get_next_level_info(current)

        lines = [
            t(lang, "tempering_title"),
            "",
            t(lang, "tempering_current_level",
              level=current,
              max=MAX_TEMPERING_LEVEL,
              emoji=current_info["emoji"],
              name=t(lang, current_info["name_key"])),
            t(lang, "tempering_current_bonus", mult=current_info["hp_def_mult"]),
        ]

        if next_info:
            check = can_temper(player, total_battle_power=total_bp)
            progress = player.body_tempering_progress or 0
            essence_cost = next_info.get("essence_cost", 0)
            next_min_realm = next_info.get("min_realm", 0)
            player_essence = getattr(player, "celestial_essence", 0) or 0

            def _tick(ok: bool) -> str:
                return "✅" if ok else "❌"

            req_lines = [
                "",
                t(lang, "tempering_next_title", level=current + 1, name=t(lang, next_info["name_key"])),
            ]
            # Realm requirement (only surfaced for celestial tiers)
            if next_min_realm > MIN_REALM_REQUIRED:
                req_lines.append(t(lang, "tempering_req_realm",
                                   tick=_tick(player.realm >= next_min_realm),
                                   required=next_min_realm))
            req_lines.extend([
                t(lang, "tempering_req_stones",
                  tick=_tick(player.spirit_stones >= next_info["cost_stones"]),
                  current=format_number(player.spirit_stones),
                  required=format_number(next_info["cost_stones"])),
                t(lang, "tempering_req_qi",
                  tick=_tick(player.qi >= next_info["cost_qi"]),
                  current=f"{player.qi:.0f}",
                  required=str(next_info["cost_qi"])),
                t(lang, "tempering_req_power",
                  tick=_tick(total_bp >= next_info["min_battle_power"]),
                  current=format_number(total_bp),
                  required=format_number(next_info["min_battle_power"])),
                t(lang, "tempering_req_progress",
                  tick=_tick(progress >= next_info["progress_required"]),
                  current=format_number(progress),
                  required=format_number(next_info["progress_required"])),
            ])
            # Celestial Essence requirement (only from tier 10+)
            if essence_cost > 0:
                req_lines.append(t(lang, "tempering_req_essence",
                                   tick=_tick(player_essence >= essence_cost),
                                   current=format_number(player_essence),
                                   required=format_number(essence_cost)))
            lines.extend(req_lines)

            # D-5 (DESIGN_DECISIONS_v14): Celestial Essence sources discoverability.
            # Players reportaram repetidamente "como consigo essência celestial?"
            # ([jogadores]). Mostrar fontes inline só
            # quando bloqueado por essência insuficiente — não polui o ecrã quando
            # tudo ✅.
            if essence_cost > 0 and player_essence < essence_cost:
                lines.append("")
                lines.append(t(lang, "tempering_essence_sources_hint"))

            # If blocked, tell the player what's missing.
            if not check["can"] and check.get("reason_key"):
                lines.append("")
                lines.append(t(lang, "tempering_blocked_by", reason=t(lang, check["reason_key"])))

            buttons = []
            if check["can"]:
                buttons.append([InlineKeyboardButton(
                    t(lang, "btn_tempering_advance"), callback_data="tempering_confirm")])
            buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_cultivo")])
            kb = InlineKeyboardMarkup(buttons)
        else:
            lines.extend(["", t(lang, "tempering_max_reached")])
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_cultivo")]])

        await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


async def tempering_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)

    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return

        lang = player.language or "en"
        from core.body_tempering_engine import can_temper, perform_tempering

        # Calculate total BP for the check using the same components as /status.
        stmt_arts = select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id, PlayerArtifact.is_equipped == True)
        arts = (await session.execute(stmt_arts)).scalars().all()
        equip_stats = get_player_equipment_stats(arts) if arts else None

        from core.beast_engine import get_companion_beast, get_companion_bonuses
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        comp_bonus = get_companion_bonuses(comp_beast, comp_catalog) if (comp_beast and comp_catalog) else None

        from core.dao_engine import get_player_dao_bonuses
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)

        total_stats = calculate_total_stats(
            player,
            equip_stats,
            companion_bonus=comp_bonus,
            dao_bonuses=dao_bonuses,
        )
        total_bp = total_stats["total_battle_power"]

        check = can_temper(player, total_battle_power=total_bp)
        if not check["can"]:
            await query.message.edit_text(t(lang, check["reason_key"]), parse_mode="Markdown")
            return

        result = perform_tempering(player)
        await session.commit()

        # Clear body tempering notification cooldown so next block re-notifies
        from core.scheduler import _bt_block_notified
        for key in list(_bt_block_notified.keys()):
            if (isinstance(key, tuple) and key and key[0] == player.telegram_id) or key == player.telegram_id:
                _bt_block_notified.pop(key, None)

        lines = [
            t(lang, "tempering_success_title"),
            "",
            t(lang, "tempering_success_body",
              level=result["new_level"],
              emoji=result["emoji"],
              name=t(lang, result["name_key"]),
              mult=result["mult"]),
            t(lang, "tempering_qi_cap_bonus", bonus=result["qi_cap_bonus"]),
        ]

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_body_tempering"), callback_data="tempering_menu")],
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_cultivo")],
        ])
        await query.message.edit_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)


def _fmt_hm(seconds: int) -> str:
    """Compact 'Xh Ym' / 'Ym' for meridian waits (chat disclosure)."""
    s = max(0, int(seconds or 0))
    h, m = s // 3600, (s % 3600) // 60
    if h > 0:
        return f"{h}h {m}m" if m else f"{h}h"
    return f"{max(1, m)}m" if s >= 60 else f"{s}s"


async def _meridian_block(session, player, lang):
    """MV-4 — the compact meridian block for /corpo (both bands): status line +
    the ritual/next step + the CTA buttons. Gated by `corpo_profundo` — OFF →
    ([], []) and the menu is byte-identical. Server errors degrade to nothing
    (the temper verb NEVER breaks because of the new axis)."""
    from database.db import feature_enabled_for_world
    if not feature_enabled_for_world("corpo_profundo"):
        return [], []
    try:
        from core.meridian_engine import project_meridians
        data = await project_meridians(session, player, lang=lang)
    except Exception:
        logger.exception("corpo meridian block failed")
        return [], []
    lines = ["", t(lang, "mer_block_title", n=data["opened_count"], total=data["total"])]
    if data["opened_count"] > 0:
        lines.append(t(lang, "mer_block_bonus", pct=data["durability_bonus_pct"]))
    buttons = []
    ritual = data.get("ritual")
    nxt = data.get("next")
    if data.get("all_open"):
        lines += [t(lang, "mer_all_open"), t(lang, "mer_teaser")]
    elif ritual:
        if ritual["ready"]:
            lines.append(t(lang, "mer_ritual_ready", name=ritual["name"], chance=ritual["chance_pct"]))
            buttons.append([InlineKeyboardButton(t(lang, "mer_break_btn"), callback_data="mer_break")])
        else:
            lines.append(t(lang, "mer_ritual_circulating", name=ritual["name"],
                           time=_fmt_hm(ritual["remaining_seconds"])))
        # QoL 05/08 (report do [jogador]) — a cicatriz PERSISTENTE, paridade com o
        # mini-app. Vale para os DOIS ramos (pronto e circulando): a memória da
        # falha e o antes→depois da chance têm de sobreviver ao toast que some.
        if int(ritual.get("attempts") or 0) > 0:
            lines.append(t(lang, "mer_retry_memory", n=ritual["attempts"],
                           was=ritual["base_chance_pct"], now=ritual["chance_pct"]))
    elif nxt:
        c = nxt["cost"]
        lines.append(t(lang, "mer_next_line", emoji=nxt["emoji"], name=nxt["name"],
                       stones=format_number(c["stones"]), progress=c["progress"], essence=c["essence"]))
        lines.append(t(lang, "mer_next_detail", hours=nxt["circulate_hours"], chance=nxt["chance_pct"]))
        if nxt.get("can_start"):
            buttons.append([InlineKeyboardButton(t(lang, "mer_start_btn"), callback_data="mer_start")])
        elif nxt.get("reason_key") == "mer_cooldown":
            lines.append(t(lang, "mer_cooldown", time=_fmt_hm(nxt.get("cooldown_remaining", 0))))
        elif nxt.get("reason_key") == "mer_need_realm":
            lines.append(t(lang, "mer_need_realm", realm=data["min_realm"]))
        elif nxt.get("reason_key"):
            lines.append(t(lang, nxt["reason_key"]))
    return lines, buttons


async def _render_corpo_menu(update, context, session, player, lang, edit):
    """Sprint 3 — render the Cultivo do Corpo @ R0 menu (the Mortal temper verb).
    Reuses project_body_for_display so the chat shows the SAME tier/gap/cost/can the
    mini-app card does. Gated: OFF world / R7+ → honest message (Lei §1, never void).
    MV-4: + the refino place line (the qi cost is f(WHERE you stand)) + the
    meridian block (both additive; `corpo_profundo` OFF → byte-identical)."""
    from core.body_tempering_engine import project_body_for_display, MIN_REALM_REQUIRED
    from database.db import feature_enabled_for_world
    from core.game_logic import get_effective_qi_capacity

    async def _send(text, kb=None):
        if edit and update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    if not feature_enabled_for_world("cultivo_corpo_r0"):
        await _send(t(lang, "body_temper_locked"))
        return

    # MV-4 — WHERE you stand prices the refino (Lei §1: the screen says the
    # place + the mult; OFF world → None + 1.0 → byte-identical).
    place = None
    place_mult = 1.0
    if feature_enabled_for_world("corpo_profundo"):
        try:
            from core.meridian_engine import refine_place_view
            place = await refine_place_view(session, player, lang)
            place_mult = float((place or {}).get("mult", 1.0) or 1.0)
        except Exception:
            logger.exception("corpo refine_place failed")

    if (player.realm or 0) >= MIN_REALM_REQUIRED:
        # R7+ — the Mortal band is behind them; point to the Nine Transformations.
        # The meridian block still applies (channels persist past R7).
        mer_lines, mer_buttons = await _meridian_block(session, player, lang)
        kb_rows = [[InlineKeyboardButton(
            t(lang, "btn_body_tempering"), callback_data="tempering_menu")]] + mer_buttons
        await _send("\n".join([t(lang, "body_temper_apex")] + mer_lines),
                    InlineKeyboardMarkup(kb_rows))
        return

    eff_qi_cap = await get_effective_qi_capacity(session, player)
    view = project_body_for_display(player, eff_qi_cap=eff_qi_cap, place_mult=place_mult)
    lines = [
        t(lang, "body_corpo_title"),
        "",
        t(lang, "body_corpo_status", emoji=view["tier_emoji"], tier=t(lang, view["tier_key"]),
          level=view["mortal_level"], max=view["max_level"]),
        t(lang, "body_corpo_gap", gap=view["gap"]),
    ]
    if place and place.get("line"):
        lines.append(f"{place['emoji']} {place['line']}")
    kb_rows = []
    nc = view.get("next_cost")
    if nc:
        next_name = t(lang, view["next_tier_key"]) if view.get("next_tier_key") else ""
        lines += ["", t(lang, "body_corpo_next", tier=next_name,
                        stones=format_number(nc["stones"]), qi=format_number(nc["qi"]))]
        if view.get("can_temper"):
            kb_rows.append([InlineKeyboardButton(
                t(lang, "body_temper_btn"), callback_data="corpo_confirm")])
        elif view.get("temper_reason_key"):
            lines += ["", t(lang, view["temper_reason_key"])]
    else:
        lines += ["", t(lang, "body_temper_maxed")]
    mer_lines, mer_buttons = await _meridian_block(session, player, lang)
    lines += mer_lines
    kb_rows += mer_buttons
    await _send("\n".join(lines), InlineKeyboardMarkup(kb_rows) if kb_rows else None)


@safe_handler
@rate_limit(1)
async def corpo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chat verb for the Mortal temper (Sprint 3). Parallel to /cultivar; gated by
    `cultivo_corpo_r0` (OFF on main → honest locked message)."""
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        await _render_corpo_menu(update, context, session, player, player.language or "pt", edit=False)


async def corpo_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        await _render_corpo_menu(update, context, session, player, player.language or "pt", edit=True)


async def corpo_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    async with get_session_factory()() as session:
        # Row-lock the player so a double-tap can't double-debit (the endpoint does
        # the same). Single committed transaction → débito all-or-nothing.
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            return
        lang = player.language or "pt"
        from core.body_tempering_engine import (
            can_temper_mortal, perform_mortal_temper, MIN_REALM_REQUIRED,
        )
        from database.db import feature_enabled_for_world
        from core.game_logic import get_effective_qi_capacity
        if not feature_enabled_for_world("cultivo_corpo_r0"):
            await query.message.edit_text(t(lang, "body_temper_locked"))
            return
        if (player.realm or 0) >= MIN_REALM_REQUIRED:
            await query.message.edit_text(t(lang, "body_temper_apex"))
            return
        eff_qi_cap = await get_effective_qi_capacity(session, player)
        # MV-4 — price the qi burn for WHERE the player stands (the SAME mult
        # the menu disclosed; corpo_profundo OFF → 1.0 without a query).
        place_mult = 1.0
        try:
            from core.meridian_engine import refine_place_mult
            place_mult = float((await refine_place_mult(session, player)).get("mult", 1.0) or 1.0)
        except Exception:
            logger.exception("corpo_confirm refine_place failed")
        check = can_temper_mortal(player, eff_qi_cap=eff_qi_cap, place_mult=place_mult)
        if not check["can"]:
            await query.message.edit_text(t(lang, check["reason_key"]))
            return
        result = perform_mortal_temper(player, eff_qi_cap=eff_qi_cap, place_mult=place_mult)
        if not result.get("success"):
            await query.message.edit_text(t(lang, result.get("reason_key", "body_temper_locked")))
            return
        await session.commit()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            t(lang, "body_temper_btn"), callback_data="corpo_menu")]])
        await query.message.edit_text(
            t(lang, "body_temper_done", tier=t(lang, result["tier_key"])),
            parse_mode="Markdown", reply_markup=kb)


async def mer_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """MV-4 — start the meridian ritual from /corpo (row-locked, all-or-nothing
    débito; mirrors api_world_meridian_start). Every refusal is disclosed."""
    query = update.callback_query
    await safe_answer(query)
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            return
        lang = player.language or "pt"
        from core.meridian_engine import start_ritual
        result = await start_ritual(session, player)
        if not result.get("ok"):
            reason = result.get("reason", "mer_locked")
            if reason == "mer_cooldown":
                msg = t(lang, "mer_cooldown", time=_fmt_hm(result.get("remaining_seconds", 0)))
            elif reason == "mer_need_realm":
                msg = t(lang, "mer_need_realm", realm=result.get("min_realm", 2))
            else:
                msg = t(lang, reason)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(
                t(lang, "btn_back"), callback_data="corpo_menu")]])
            await query.message.edit_text(msg, reply_markup=kb)
            return
        await session.commit()
        name = t(lang, f"mer_ch_{result['channel']}")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            t(lang, "btn_back"), callback_data="corpo_menu")]])
        await query.message.edit_text(
            t(lang, "mer_started", emoji=result["emoji"], name=name,
              hours=result["circulate_hours"], chance=result["chance_pct"]),
            reply_markup=kb)


async def mer_break_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """MV-4 — the ROMPIMENTO from /corpo (row-locked; mirrors
    api_world_meridian_break). Success shows antes→depois (HP + resistência —
    progressão VISÍVEL); failure is honest with the boosted next chance."""
    query = update.callback_query
    await safe_answer(query)
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            return
        lang = player.language or "pt"
        from core.meridian_engine import attempt_break
        result = await attempt_break(session, player)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(
            t(lang, "btn_back"), callback_data="corpo_menu")]])
        if not result.get("ok"):
            reason = result.get("reason", "mer_locked")
            if reason == "mer_still_circulating":
                msg = t(lang, "mer_still_circulating", time=_fmt_hm(result.get("remaining_seconds", 0)))
            else:
                msg = t(lang, reason)
            await query.message.edit_text(msg, reply_markup=kb)
            return
        await session.commit()
        name = t(lang, f"mer_ch_{result['channel']}")
        if result.get("opened"):
            lines = [t(lang, "mer_break_success", emoji=result["emoji"], name=name,
                       n=result["opened_count"], total=result["total"]),
                     t(lang, "mer_break_delta",
                       hp_before=format_number(result["hp_before"]),
                       hp_after=format_number(result["hp_after"]),
                       pct=result["durability_pct_after"])]
            if result.get("all_open"):
                lines += [t(lang, "mer_all_open"), t(lang, "mer_teaser")]
            await query.message.edit_text("\n".join(lines), reply_markup=kb)
        else:
            await query.message.edit_text(
                t(lang, "mer_break_fail", name=name, chance=result["chance_pct"],
                  next_chance=result["next_chance_pct"],
                  time=_fmt_hm(int(result.get("recirculate_hours", 0) * 3600))),
                reply_markup=kb)


async def _render_horta_menu(update, context, session, player, lang, edit, pick_slot=None):
    """Sprint 4 — render the Horta 灵田 menu (plant/grow/harvest + the Mortal
    temper-progress bar). Gated by `cultivo_corpo_r0` (main OFF → garden_locked) and
    realm < 7 (the Horta feeds the R0–R6 Mortal band only)."""
    from core.garden_engine import project_garden, GARDEN_HERBS
    from core.body_tempering_engine import MIN_REALM_REQUIRED
    from database.db import feature_enabled_for_world

    async def _send(text, kb=None):
        if edit and update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    if not feature_enabled_for_world("cultivo_corpo_r0"):
        await _send(t(lang, "garden_locked"))
        return
    if (player.realm or 0) >= MIN_REALM_REQUIRED:
        await _send(t(lang, "garden_apex"))
        return

    data = await project_garden(session, player)
    lines = [t(lang, "garden_title_chat"), ""]
    if data["progress_required"] is not None:
        lines.append(t(lang, "garden_progress_chat", cur=data["temper_progress"], req=data["progress_required"]))
        lines.append("")

    # Herb picker for one slot (after "Plantar slot N"). Uses project_garden's
    # catalog so it can DISCLOSE affordability (🔒 + the stone balance) up front —
    # Lei §1, never a silent "nothing happened" when the player can't afford.
    if pick_slot is not None:
        herb_buttons = []
        for h in data["catalog"]:
            key = h["herb_key"]
            lock = "" if h["can_afford"] else "🔒 "
            herb_buttons.append([InlineKeyboardButton(
                f"{lock}{h['emoji']} {t(lang, 'herb_' + key)} · 🪨{format_number(h['cost_stones'])} · +{h['temper_progress']}",
                callback_data=f"horta_s_{pick_slot}_{key}")])
        herb_buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="horta_menu")])
        lines.append(t(lang, "garden_pick_herb", n=pick_slot + 1))
        lines.append(t(lang, "garden_your_stones", stones=format_number(data["stones"])))
        await _send("\n".join(lines), InlineKeyboardMarkup(herb_buttons))
        return

    buttons = []
    for p in data["plots"]:
        slot = p["slot"]
        if p["state"] == "empty":
            lines.append(t(lang, "garden_slot_empty", n=slot + 1))
            buttons.append([InlineKeyboardButton(
                t(lang, "garden_plant_slot", n=slot + 1), callback_data=f"horta_p_{slot}")])
        elif p["state"] == "ready":
            lines.append(t(lang, "garden_slot_ready", n=slot + 1,
                            herb=t(lang, "herb_" + p["herb_key"]), pts=p["temper_progress"]))
            buttons.append([InlineKeyboardButton(
                t(lang, "garden_harvest_slot", n=slot + 1), callback_data=f"horta_h_{slot}")])
        else:  # growing
            mins = max(1, int(p["remaining_seconds"]) // 60)
            lines.append(t(lang, "garden_slot_growing", n=slot + 1,
                            herb=t(lang, "herb_" + p["herb_key"]), mins=mins))
    # Caça 狩猎 (Sprint 5) — the 2nd input, folded into the same menu: refine the
    # hunt_essence the beast expeditions brought back into Mortal temper progress.
    h = data.get("hunt") or {}
    if not h.get("is_apex"):
        lines.append("")
        lines.append(t(lang, "hunt_status_chat", essence=h.get("hunt_essence", 0)))
        if h.get("can_refine"):
            buttons.append([InlineKeyboardButton(
                t(lang, "hunt_refine_chat", cost=h.get("refine_cost", 0), yld=h.get("refine_yield", 0)),
                callback_data="caca_refine")])
        else:
            # Not enough essence to refine — disclose WHERE it comes from (Lei §1,
            # mirrors the mini-app subtitle), never a bare "0" with no path.
            lines.append(t(lang, "hunt_hint_chat"))
    # Ambiental 环境 (Sprint 6) — the 3rd input, same menu. The world tempers the
    # flesh: temper at the extreme-environment site in your CURRENT continent
    # (situational + a global cooldown). Discloses the local site or where to roam
    # (Lei §1 — never a silent void when nothing is here / on cooldown).
    env = data.get("environment") or {}
    if not env.get("is_apex"):
        lines.append("")
        local = next((s for s in env.get("sites", []) if s.get("here")), None)
        if local is None:
            lines.append(t(lang, "env_none_here"))
        else:
            site_name = t(lang, "env_site_" + local["site_key"])
            if local.get("can_temper"):
                lines.append(t(lang, "env_status_chat", site=site_name, pts=local["progress"]))
                buttons.append([InlineKeyboardButton(
                    t(lang, "env_temper_chat", site=site_name), callback_data="env_temper")])
            else:
                rem = int(env.get("cooldown_remaining", 0))
                if rem > 0:
                    lines.append(t(lang, "env_cooldown_chat", site=site_name, mins=max(1, rem // 60)))
                else:
                    lines.append(t(lang, "env_status_chat", site=site_name, pts=local["progress"]))
    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="nav_cultivo")])
    await _send("\n".join(lines), InlineKeyboardMarkup(buttons))


async def caca_refine_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query)
            return
        lang = player.language or "pt"
        from core.hunt_engine import do_refine
        from core.body_tempering_engine import MIN_REALM_REQUIRED
        from database.db import feature_enabled_for_world
        if not feature_enabled_for_world("cultivo_corpo_r0") or (player.realm or 0) >= MIN_REALM_REQUIRED:
            await safe_answer(query)
            await query.message.edit_text(t(lang, "hunt_locked"))
            return
        result = do_refine(player)
        if result.get("success"):
            await session.commit()
            await safe_answer(query, t(lang, "hunt_refined", n=result["refined"]))
        else:
            await safe_answer(query, t(lang, result.get("reason_key", "hunt_need_essence")), show_alert=True)
        await _render_horta_menu(update, context, session, player, lang, edit=True)


async def env_temper_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sprint 6 — Ambiental 环境: temper the flesh at the extreme-environment site in
    the player's CURRENT continent (the site is derived server-side so the callback
    needs no args, <64B). Gated by `cultivo_corpo_r0` + realm < 7, row-locked,
    atomic. NEVER touches qi (BC-5)."""
    query = update.callback_query
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query)
            return
        lang = player.language or "pt"
        from core.environment_engine import do_temper_env, local_site_key
        from core.body_tempering_engine import MIN_REALM_REQUIRED
        from database.db import feature_enabled_for_world
        if not feature_enabled_for_world("cultivo_corpo_r0") or (player.realm or 0) >= MIN_REALM_REQUIRED:
            await safe_answer(query)
            await query.message.edit_text(t(lang, "env_locked"))
            return
        site_key = local_site_key(player)
        result = do_temper_env(player, site_key) if site_key else {"success": False, "reason_key": "env_none_here"}
        if result.get("success"):
            await session.commit()
            await safe_answer(query, t(lang, "env_done", n=result["temper_progress_gained"]))
        else:
            rk = result.get("reason_key", "env_none_here")
            if rk == "env_cooldown":
                rem = int(result.get("remaining_seconds", 0))
                await safe_answer(query, t(lang, "env_cooldown_alert", mins=max(1, rem // 60)), show_alert=True)
            else:
                await safe_answer(query, t(lang, rk), show_alert=True)
        await _render_horta_menu(update, context, session, player, lang, edit=True)


@safe_handler
@rate_limit(1)
async def horta_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Chat verb for the Horta 灵田 (Sprint 4). Gated by `cultivo_corpo_r0`."""
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        await _render_horta_menu(update, context, session, player, player.language or "pt", edit=False)


async def horta_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        await _render_horta_menu(update, context, session, player, player.language or "pt", edit=True)


async def horta_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    try:
        slot = int(query.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        return
    async with get_session_factory()() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        await _render_horta_menu(update, context, session, player, player.language or "pt", edit=True, pick_slot=slot)


async def horta_sow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # callback: horta_s_<slot>_<herb_key>. We answer the query LAST so a refusal
    # (e.g. not enough stones) surfaces as an alert — Lei §1, honest disclosure.
    try:
        rest = query.data[len("horta_s_"):]
        slot_str, herb_key = rest.split("_", 1)
        slot = int(slot_str)
    except (ValueError, IndexError):
        await safe_answer(query)
        return
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query)
            return
        lang = player.language or "pt"
        from core.garden_engine import do_plant
        from core.body_tempering_engine import MIN_REALM_REQUIRED
        from database.db import feature_enabled_for_world
        if not feature_enabled_for_world("cultivo_corpo_r0") or (player.realm or 0) >= MIN_REALM_REQUIRED:
            await safe_answer(query)
            await query.message.edit_text(t(lang, "garden_locked"))
            return
        result = await do_plant(session, player, slot, herb_key)
        if result.get("ok"):
            await session.commit()
            await safe_answer(query)
        else:
            await safe_answer(query, t(lang, result.get("reason", "garden_need_stones")), show_alert=True)
        await _render_horta_menu(update, context, session, player, lang, edit=True)


async def horta_harvest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    try:
        slot = int(query.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        return
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            return
        lang = player.language or "pt"
        from core.garden_engine import do_harvest
        from core.body_tempering_engine import MIN_REALM_REQUIRED
        from database.db import feature_enabled_for_world
        if not feature_enabled_for_world("cultivo_corpo_r0") or (player.realm or 0) >= MIN_REALM_REQUIRED:
            await query.message.edit_text(t(lang, "garden_locked"))
            return
        result = await do_harvest(session, player, slot)
        if result.get("ok"):
            await session.commit()
        # Feedback is the re-rendered menu (progress bar moves on success); the slot
        # state reflects an unready/empty no-op.
        await _render_horta_menu(update, context, session, player, lang, edit=True)


async def _render_ceremonia(update, context, session, player, lang, edit=False):
    """Sprint 8 — render the Cerimónia-Semente choice (Consolidar / Forçar) in chat. The
    mini-app is canonical; this keeps chat from being a dead-end (Lei §1). Gated by
    `breakthrough_trials` + an actually-pending early realm-up."""
    from core.breakthrough_trials_engine import (
        bt_ceremony_on, ceremony_eligible, project_ceremony,
    )
    from core.game_logic import get_threshold
    from config import SUB_LAYERS_PER_REALM

    async def _send(text, kb=None):
        if edit and update.callback_query:
            await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        else:
            await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

    threshold = float(get_threshold(player.realm or 0, player.sub_layer or 1))
    if not (bt_ceremony_on() and ceremony_eligible(player)
            and (player.sub_layer or 1) >= SUB_LAYERS_PER_REALM
            and float(player.cultivation_base or 0) >= threshold):
        await _send(t(lang, "bt_ceremony_none"))
        return

    cer = project_ceremony(player)
    pct = int(round(cer["force_chance"] * 100))
    lines = [t(lang, "bt_ceremony_title"), "", t(lang, "bt_ceremony_intro")]
    if cer["body_gap"] > 0:
        lines.append(t(lang, "bt_ceremony_gap", gap=cer["body_gap"]))
    if cer["has_insight"]:
        lines.append(t(lang, "bt_ceremony_insight"))
    buttons = [[InlineKeyboardButton(t(lang, "bt_btn_consolidar"), callback_data="bt_cer_consolidar")]]
    if cer["force_available"]:
        lines.append(t(lang, "bt_ceremony_force_odds", pct=pct))
        buttons.append([InlineKeyboardButton(
            t(lang, "bt_btn_forcar", pct=pct), callback_data="bt_cer_forcar")])
    else:
        mins = max(1, cer["setback_remaining"] // 60)
        lines.append(t(lang, "bt_ceremony_setback", mins=mins))
    await _send("\n".join(lines), InlineKeyboardMarkup(buttons))


@safe_handler
@rate_limit(1)
async def cerimonia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"
        await _render_ceremonia(update, context, session, player, lang, edit=False)


async def ceremonia_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resolve a chat Cerimónia choice. Mirrors api_breakthrough_ceremony (lock → gate →
    resolve → advance → commit), gated + atomic. NEVER touches qi/qi_capacity."""
    import random
    query = update.callback_query
    choice = "forcar" if query.data.endswith("forcar") else "consolidar"
    async with get_session_factory()() as session:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == await resolve_chat_player_id(update.effective_user.id)).with_for_update()
        )).scalar_one_or_none()
        if not player:
            await safe_answer(query)
            return
        lang = player.language or "pt"
        from core.breakthrough_trials_engine import (
            bt_ceremony_on, ceremony_eligible, resolve_force, setback_remaining,
            BT_FORCE_CB_BONUS_FRAC, BT_FORCE_STONES,
        )
        from core.game_logic import check_breakthrough, get_threshold
        from config import SUB_LAYERS_PER_REALM
        threshold = float(get_threshold(player.realm or 0, player.sub_layer or 1))
        if not (bt_ceremony_on() and ceremony_eligible(player)
                and (player.sub_layer or 1) >= SUB_LAYERS_PER_REALM
                and float(player.cultivation_base or 0) >= threshold):
            await safe_answer(query)
            await _render_ceremonia(update, context, session, player, lang, edit=True)
            return
        outcome = {"choice": choice, "success": True}
        if choice == "forcar":
            if setback_remaining(player) > 0:
                await safe_answer(query, t(lang, "bt_ceremony_setback_alert"), show_alert=True)
                return
            outcome = resolve_force(player, random.random())
        result = await check_breakthrough(player, session, ceremony_choice=choice)
        if not result or not result.get("realm_up"):
            await session.rollback()
            await safe_answer(query)
            await _render_ceremonia(update, context, session, player, lang, edit=True)
            return
        force_won = bool(choice == "forcar" and outcome.get("success"))
        if force_won:
            nxt = float(get_threshold(player.realm or 0, player.sub_layer or 1))
            player.cultivation_base = float(player.cultivation_base or 0) + round(nxt * BT_FORCE_CB_BONUS_FRAC, 2)
            player.spirit_stones = int(player.spirit_stones or 0) + BT_FORCE_STONES
        try:
            from core.quest_engine import track_quest
            await track_quest(session, player.telegram_id, "breakthrough", 1)
            await track_quest(session, player.telegram_id, "realm_up", 1)
        except Exception:
            pass
        await session.commit()
        from config import REALM_NAMES
        rname = REALM_NAMES[min(int(player.realm or 0), len(REALM_NAMES) - 1)]
        if choice == "consolidar":
            key = "bt_done_consolidar"
        elif force_won:
            key = "bt_done_forcar_win"
        else:
            key = "bt_done_forcar_setback"
        await safe_answer(query)
        await query.message.edit_text(t(lang, key, realm=rname), parse_mode="Markdown")


@safe_handler
@rate_limit(1)
async def guia_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """FTUE espinha — the Velho Mendigo's guided checklist in chat (server-gated, read-only)."""
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"
        from core.ftue_engine import ftue_on, project_ftue, grant_ftue_strike_technique
        if not ftue_on():
            await update.effective_message.reply_text(t(lang, "ftue_off"))
            return
        # MV-1 §0.3 — COMPAT: beta players (espelho do api_world_ftue): chars
        # criados antes do grant-de-nascimento recebem a Beggar's Palm aqui.
        if int(player.realm or 0) <= 1 and await grant_ftue_strike_technique(session, player.telegram_id):
            try:
                await session.commit()
            except Exception:
                await session.rollback()
        d = project_ftue(player)
        lines = [t(lang, "ftue_title"), ""]
        if d["complete"] or not d["current"]:
            lines.append(t(lang, "ftue_complete"))
        else:
            lines.append(t(lang, "ftue_mendigo_" + d["current"]))
            lines.append("")
            for s in d["steps"]:
                mark = "✅" if s["done"] else ("▶️" if s["key"] == d["current"] else "⚪")
                lines.append(f"{mark} {t(lang, 'ftue_step_' + s['key'])}")
            lines.append("")
            lines.append(t(lang, "ftue_progress", n=d["done_count"], total=d["total"]))
        await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


@safe_handler
@rate_limit(1)
async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data == "cmd_status":
        await safe_answer(query)
        await status_command(update, context)
    elif query.data == "cmd_cultivar":
        await safe_answer(query)
        await cultivar_command(update, context)
    elif query.data == "cmd_meditar":
        await safe_answer(query)
        await meditar_command(update, context)
    elif query.data == "cmd_ranking":
        await safe_answer(query)
        await ranking_command(update, context)
    elif query.data == "cmd_idioma":
        await safe_answer(query)
        await idioma_command(update, context)
    elif query.data == "cmd_notif":
        await safe_answer(query)
        await notif_command(update, context)
    elif query.data == "cmd_path":
        await safe_answer(query)
        await path_command(update, context)
    elif query.data == "cmd_karma":
        await safe_answer(query)
        await karma_command(update, context)
    elif query.data == "cmd_genero":
        await safe_answer(query)
        await genero_command(update, context)
    elif query.data.startswith("set_gender_"):
        await set_gender_callback(update, context)
    elif query.data == "cmd_settings":
        await safe_answer(query)
        await config_command(update, context)
    elif query.data == "cmd_start":
        await safe_answer(query)
        from handlers.start import start_command
        await start_command(update, context)
    elif query.data == "cmd_tribulacao":
        await safe_answer(query)
        from handlers.tribulation import tribulacao_command
        await tribulacao_command(update, context)
    elif query.data.startswith("meditate_"):
        await start_meditation_callback(update, context)
    elif query.data == "cancel_meditation":
        await cancel_meditation_callback(update, context)
    elif query.data.startswith("set_lang_"):
        await set_language_callback(update, context)
    elif query.data == "foundation_start":
        await foundation_start_callback(update, context)
    elif query.data == "foundation_confirm":
        await foundation_confirm_callback(update, context)
    elif query.data == "core_formation_start":
        await core_formation_start_callback(update, context)
    elif query.data == "core_form_confirm":
        await core_form_confirm_callback(update, context)
    elif query.data == "tempering_menu":
        await tempering_menu_callback(update, context)
    elif query.data == "tempering_confirm":
        await tempering_confirm_callback(update, context)
    elif query.data == "corpo_menu":
        await corpo_menu_callback(update, context)
    elif query.data == "corpo_confirm":
        await corpo_confirm_callback(update, context)
    # MV-4 — meridianos (o catch-all do main.py entrega aqui; `mer_` não
    # colide com nenhum prefixo despachado antes — lição MV-2).
    elif query.data == "mer_start":
        await mer_start_callback(update, context)
    elif query.data == "mer_break":
        await mer_break_callback(update, context)
    elif query.data == "horta_menu":
        await horta_menu_callback(update, context)
    elif query.data.startswith("horta_p_"):
        await horta_pick_callback(update, context)
    elif query.data.startswith("horta_s_"):
        await horta_sow_callback(update, context)
    elif query.data.startswith("horta_h_"):
        await horta_harvest_callback(update, context)
    elif query.data == "caca_refine":
        await caca_refine_callback(update, context)
    elif query.data == "env_temper":
        await env_temper_callback(update, context)
    elif query.data.startswith("bt_cer_"):
        await ceremonia_choice_callback(update, context)
    elif query.data == "cmd_help":
        await safe_answer(query)
        await help_command(update, context)
