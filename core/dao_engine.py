import random
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DaoLawCatalog, PlayerDaoFragment
from core.game_logic import get_progress_bar
from core.i18n import t

logger = logging.getLogger(__name__)

DAO_UNLOCK_REALM = 5  # Soul Transformation (index 5) — first Dao Laws unlock here

REALM_NAMES_FOR_DAO = {
    5: "Soul Transformation",
    6: "Void Refinement",
    7: "Body Integration",
    8: "Mahayana",
    9: "Tribulation Transcendence",
}

INSIGHT_LEVELS = {
    0: {"name": "None",          "name_pt": "Nenhum",        "name_es": "Ninguno",        "dao_mult": 1.0,  "trib_bonus": 0},
    1: {"name": "Glimpse",       "name_pt": "Vislumbre",     "name_es": "Vislumbre",      "dao_mult": 1.15, "trib_bonus": 0.05},
    2: {"name": "Understanding", "name_pt": "Entendimento",  "name_es": "Entendimiento",  "dao_mult": 1.30, "trib_bonus": 0.10},
    3: {"name": "Mastery",       "name_pt": "Maestria",      "name_es": "Maestría",       "dao_mult": 1.50, "trib_bonus": 0.15},
    4: {"name": "Enlightenment", "name_pt": "Iluminação",    "name_es": "Iluminación",    "dao_mult": 2.0,  "trib_bonus": 0.25},
}


def _is_eternal_law(law: DaoLawCatalog) -> bool:
    """
    Avoid hardcoding Eternal Dao by a fixed ID.
    Live/beta databases can diverge in insertion order.
    """
    return bool(law and law.effect_type == "all_stats" and (law.total_fragments or 0) >= 100)


async def get_player_dao_bonuses(session: AsyncSession, player_id: int, player_realm: int = 0) -> dict:
    """Get combined bonuses from Supreme Laws (fragments) + 3000 Laws (discoveries)."""
    stmt = (
        select(PlayerDaoFragment, DaoLawCatalog)
        .join(DaoLawCatalog, PlayerDaoFragment.dao_law_id == DaoLawCatalog.id)
        .where(PlayerDaoFragment.player_id == player_id, PlayerDaoFragment.fragments_count > 0)
    )
    rows = (await session.execute(stmt)).all()

    bonuses = {
        "cb_mult": 1.0,
        "bp_mult": 1.0,
        "hp_regen": 0.0,
        "cooldown_reduction": 0.0,
        "pill_quality": 0.0,
        "all_stats_mult": 1.0,
    }

    # Supreme Laws (existing fragment system)
    for frag, law in rows:
        count = frag.fragments_count
        per = law.effect_per_fragment
        completed_multiplier = 2.0 if frag.is_completed else 1.0

        insight_mult = INSIGHT_LEVELS.get(frag.insight_level, INSIGHT_LEVELS[0])["dao_mult"]
        total_effect = count * per * completed_multiplier * insight_mult

        if law.effect_type == "cb_mult":
            bonuses["cb_mult"] += total_effect
        elif law.effect_type == "bp_mult":
            bonuses["bp_mult"] += total_effect
        elif law.effect_type == "hp_regen":
            bonuses["hp_regen"] += total_effect
        elif law.effect_type == "cooldown_reduction":
            bonuses["cooldown_reduction"] += total_effect
        elif law.effect_type == "pill_quality":
            bonuses["pill_quality"] += total_effect
        elif law.effect_type == "all_stats":
            bonuses["all_stats_mult"] += total_effect

    # 3000 Dao Laws (discovery/tier system)
    if player_realm >= DAO_UNLOCK_REALM:
        try:
            from core.dao_laws_engine import get_dao_laws_bonuses
            laws_bonuses = await get_dao_laws_bonuses(session, player_id, player_realm)
            bonuses["cb_mult"] += laws_bonuses.get("cb_mult", 0)
            bonuses["bp_mult"] += laws_bonuses.get("bp_mult", 0)
            bonuses["hp_regen"] += laws_bonuses.get("hp_regen", 0)
            bonuses["cooldown_reduction"] += laws_bonuses.get("cooldown_reduction", 0)
            bonuses["pill_quality"] += laws_bonuses.get("craft_quality", 0)
            bonuses["all_stats_mult"] += laws_bonuses.get("all_stats", 0)
            # all_mult from Supreme category applies as global multiplier
            all_mult = laws_bonuses.get("all_mult", 0)
            if all_mult > 0:
                bonuses["cb_mult"] += all_mult
                bonuses["bp_mult"] += all_mult
                bonuses["all_stats_mult"] += all_mult
        except Exception as e:
            logger.warning("Failed to get 3000 laws bonuses: %s", e)

    # Heavenly Dao (Mahayana+) — F-11
    if player_realm >= 8:
        try:
            from core.celestial_engine import get_heavenly_dao_bonus
            hd = await get_heavenly_dao_bonus(session, player_id, player_realm)
            hd_bonus = hd.get("all_mult_bonus", 0.0)
            if hd_bonus > 0:
                bonuses["cb_mult"] += hd_bonus
                bonuses["bp_mult"] += hd_bonus
                bonuses["all_stats_mult"] += hd_bonus
        except Exception as e:
            logger.warning("Failed to get Heavenly Dao bonus: %s", e)

    # Celestial Resonance (Mahayana+) — F-11.5
    # Set bonus from wearing grade-8 Celestial artifacts. Cap at 3 pieces.
    if player_realm >= 8:
        try:
            from core.celestial_engine import get_celestial_resonance
            reso = await get_celestial_resonance(session, player_id)
            r_bonus = reso.get("bonus", 0.0)
            if r_bonus > 0:
                bonuses["cb_mult"] += r_bonus
                bonuses["bp_mult"] += r_bonus
                bonuses["all_stats_mult"] += r_bonus
        except Exception as e:
            logger.warning("Failed to get Celestial Resonance: %s", e)

    return bonuses


async def try_grant_fragment(session: AsyncSession, player_id: int, perception: int, player_realm: int, fragment_mult: float = 1.0) -> dict | None:
    chance = (perception / 10000.0) * fragment_mult
    if random.random() > chance:
        return None

    if player_realm < DAO_UNLOCK_REALM:
        return None

    laws = (await session.execute(
        select(DaoLawCatalog).where(DaoLawCatalog.min_realm <= player_realm)
    )).scalars().all()
    if not laws:
        return None

    incomplete = []
    for law in laws:
        stmt = select(PlayerDaoFragment).where(
            PlayerDaoFragment.player_id == player_id,
            PlayerDaoFragment.dao_law_id == law.id,
        )
        frag = (await session.execute(stmt)).scalar_one_or_none()
        if not frag or not frag.is_completed:
            incomplete.append((law, frag))

    if not incomplete:
        return None

    weights = []
    for law, frag in incomplete:
        if law.total_fragments <= 9:
            weights.append(10)
        elif law.total_fragments <= 12:
            weights.append(5)
        else:
            weights.append(1)

    chosen_law, chosen_frag = random.choices(incomplete, weights=weights, k=1)[0]

    if chosen_frag is None:
        chosen_frag = PlayerDaoFragment(
            player_id=player_id,
            dao_law_id=chosen_law.id,
            fragments_count=0,
            is_completed=False,
            insight_level=0,
        )
        session.add(chosen_frag)

    chosen_frag.fragments_count += 1
    
    if chosen_frag.fragments_count % 3 == 0 and chosen_frag.insight_level < 4:
        chosen_frag.insight_level += 1

    just_completed = False
    if chosen_frag.fragments_count >= chosen_law.total_fragments:
        chosen_frag.is_completed = True
        just_completed = True

    return {
        "law_name": chosen_law.name,
        "law_emoji": chosen_law.emoji,
        "fragments": chosen_frag.fragments_count,
        "total": chosen_law.total_fragments,
        "completed": just_completed,
        "is_eternal": _is_eternal_law(chosen_law),
    }


async def grant_random_fragments(session: AsyncSession, player_id: int, count: int, player_realm: int) -> list[dict]:
    if player_realm < DAO_UNLOCK_REALM:
        return []

    laws = (await session.execute(
        select(DaoLawCatalog).where(DaoLawCatalog.min_realm <= player_realm)
    )).scalars().all()
    if not laws:
        return []

    results = []
    for _ in range(count):
        incomplete = []
        for law in laws:
            stmt = select(PlayerDaoFragment).where(
                PlayerDaoFragment.player_id == player_id,
                PlayerDaoFragment.dao_law_id == law.id,
            )
            frag = (await session.execute(stmt)).scalar_one_or_none()
            if not frag or not frag.is_completed:
                incomplete.append((law, frag))

        if not incomplete:
            break

        weights = [10 if law.total_fragments <= 9 else (5 if law.total_fragments <= 12 else 1) for law, _ in incomplete]
        chosen_law, chosen_frag = random.choices(incomplete, weights=weights, k=1)[0]

        if chosen_frag is None:
            chosen_frag = PlayerDaoFragment(
                player_id=player_id,
                dao_law_id=chosen_law.id,
                fragments_count=0,
                is_completed=False,
                insight_level=0,
            )
            session.add(chosen_frag)
            await session.flush()

        chosen_frag.fragments_count += 1
        
        if chosen_frag.fragments_count % 3 == 0 and chosen_frag.insight_level < 4:
            chosen_frag.insight_level += 1

        just_completed = False
        if chosen_frag.fragments_count >= chosen_law.total_fragments:
            chosen_frag.is_completed = True
            just_completed = True

        results.append({
            "law_name": chosen_law.name,
            "law_emoji": chosen_law.emoji,
            "fragments": chosen_frag.fragments_count,
            "total": chosen_law.total_fragments,
            "completed": just_completed,
            "is_eternal": _is_eternal_law(chosen_law),
        })

    return results


async def build_dao_display(session: AsyncSession, player_id: int, player_realm: int, lang: str = "en") -> str:
    if player_realm < DAO_UNLOCK_REALM:
        realm_name = REALM_NAMES_FOR_DAO.get(DAO_UNLOCK_REALM, "Soul Transformation")
        return t(lang, "dao_sealed_title") + t(lang, "dao_sealed_desc", realm=realm_name)

    laws = (await session.execute(
        select(DaoLawCatalog).order_by(DaoLawCatalog.id)
    )).scalars().all()

    if not laws:
        return t(lang, "dao_no_laws")

    lines = [t(lang, "dao_title")]

    for law in laws:
        locked = player_realm < law.min_realm

        if locked:
            req_name = REALM_NAMES_FOR_DAO.get(law.min_realm, f"Realm {law.min_realm}")
            rarity_tag = ""
            if law.total_fragments == 12:
                rarity_tag = t(lang, "dao_rarity_rare")
            elif law.total_fragments == 108:
                rarity_tag = t(lang, "dao_rarity_endgame")

            lines.append(
                f"🔒 *{law.name}*{rarity_tag}\n"
                + t(lang, "dao_locked_requires", realm=req_name)
            )
            continue

        stmt = select(PlayerDaoFragment).where(
            PlayerDaoFragment.player_id == player_id,
            PlayerDaoFragment.dao_law_id == law.id,
        )
        frag = (await session.execute(stmt)).scalar_one_or_none()
        count = frag.fragments_count if frag else 0
        completed = frag.is_completed if frag else False
        insight_level = frag.insight_level if frag else 0

        bar = get_progress_bar(count, law.total_fragments, length=8)

        insight_info = INSIGHT_LEVELS.get(insight_level, INSIGHT_LEVELS[0])
        insight_nameKey = f"name_{lang}" if f"name_{lang}" in insight_info else "name"
        insight_name = insight_info.get(insight_nameKey, insight_info["name"])
        insight_mult = insight_info["dao_mult"]

        effect_pct = count * law.effect_per_fragment * 100
        completed_label = ""
        if completed:
            effect_pct *= 2
            completed_label = t(lang, "dao_completed_label")
            
        effect_pct *= insight_mult

        effect_display = _format_effect(law.effect_type, effect_pct, lang=lang)

        rarity_tag = ""
        if law.total_fragments == 12:
            rarity_tag = t(lang, "dao_rarity_rare")
        elif law.total_fragments == 108:
            rarity_tag = t(lang, "dao_rarity_endgame")

        # UI matching the prompt structure
        lines.append(f"{law.emoji} *{law.name}*{rarity_tag}")
        lines.append(t(lang, "dao_fragments_line", count=count, total=law.total_fragments, bar=bar, completed=completed_label))
        
        if insight_level > 0:
            stars = "⭐" * insight_level
            insight_label = t(lang, "dao_insight_label")
            effect_label = t(lang, "dao_effect_label")
            lines.append(f"   {insight_label}: {insight_name} {stars} (×{insight_mult:.2f} {effect_label})")
            
        lines.append(f"   {effect_display}")
        lines.append("") # Spacing between laws

    lines.append(t(lang, "dao_footer_fragments"))
    lines.append(t(lang, "dao_footer_perception"))

    return "\n".join(lines)


# ─── Comprehension-speed disclosure (TAPETE QoL §5 item 11 — [jogador] 25.05) ────
# Disclosure-ONLY (Lei §1; the compute_affinity_breakdown pattern). ZERO
# formula change — this only EXPOSES what try_grant_fragment and
# dao_laws_engine.try_discover_law already do:
#   · Supreme fragments: chance/tick = perception/10000 (linear, can saturate
#     at 100%) × meditation mult × buffs/faction.
#   · 3000-Laws discovery: 1.5% base × √mult × (undiscovered/accessible) —
#     DECAYS as you learn (Saint's "quanto mais avanças mais difícil");
#     perception does NOT speed it up — it only shifts rarity weights for
#     rare/epic picks, capped at ×2 (saturates at 10k perception — [jogador] at
#     50k→110k was already past both caps, hence "não parece alterar").
# Canonical helper used by BOTH chat /dao and the mini-app /dao/summary
# endpoint (the qi_regen_stack_mult lesson: one place for the math).
async def compute_comprehension_breakdown(session: AsyncSession, player) -> dict:
    from database.models import PlayerArtifact as _PA

    # Total perception — mirror scheduler.py's meditation tick exactly.
    total_perc = int(player.perception or 0)
    try:
        from core.game_logic import calculate_total_stats, get_player_equipment_stats
        from core.alchemy_engine import get_active_buffs
        arts = (await session.execute(
            select(_PA).where(_PA.player_id == player.telegram_id, _PA.is_equipped == True)  # noqa: E712
        )).scalars().all()
        eq_stats = get_player_equipment_stats(arts)
        stats = calculate_total_stats(player, eq_stats)
        total_perc = stats.get("perception", player.perception)
        for b in await get_active_buffs(session, player.telegram_id):
            if b.buff_type == "perception_boost":
                total_perc *= b.buff_value
        total_perc = int(total_perc)
    except Exception:
        total_perc = int(player.perception or 0)

    frag_chance = total_perc / 10000.0  # per 30s tick, at meditation mult ×1

    laws_total = 0
    laws_disc = 0
    base_pct = 1.5
    try:
        from core.dao_laws_engine import _get_accessible_paths, BASE_DISCOVERY_CHANCE
        from database.models import DaoPathLaw, PlayerDaoDiscovery
        from sqlalchemy import func as _func
        base_pct = BASE_DISCOVERY_CHANCE * 100.0
        paths = await _get_accessible_paths(session, player.telegram_id, int(player.realm or 0))
        path_ids = [p.id for p in paths]
        if path_ids:
            laws_total = (await session.execute(
                select(_func.count(DaoPathLaw.id)).where(DaoPathLaw.path_id.in_(path_ids))
            )).scalar() or 0
            laws_disc = (await session.execute(
                select(_func.count(PlayerDaoDiscovery.law_id)).where(
                    PlayerDaoDiscovery.player_id == player.telegram_id,
                    PlayerDaoDiscovery.law_id.in_(
                        select(DaoPathLaw.id).where(DaoPathLaw.path_id.in_(path_ids))
                    ),
                )
            )).scalar() or 0
    except Exception:
        pass

    ratio = ((laws_total - laws_disc) / laws_total) if laws_total > 0 else 0.0
    rarity_factor = min(total_perc / 5000.0, 2.0)
    return {
        "perception_total": int(total_perc),
        # Display caps at 100% — a per-tick probability can't exceed certainty.
        "fragment_chance_pct": round(min(100.0, frag_chance * 100.0), 2),
        "fragment_capped": frag_chance >= 1.0,
        "discovery_base_pct": round(base_pct, 2),
        "laws_accessible": int(laws_total),
        "laws_discovered": int(laws_disc),
        "undiscovered_ratio_pct": round(ratio * 100.0, 1),
        "discovery_chance_pct": round(base_pct * ratio, 3),
        "perception_rarity_factor": round(rarity_factor, 2),
        "perception_rarity_capped": total_perc >= 10000,
    }


async def build_status_dao_summary(session: AsyncSession, player_id: int, player_realm: int, lang: str = "en") -> str:
    if player_realm < DAO_UNLOCK_REALM:
        return ""

    stmt = (
        select(PlayerDaoFragment, DaoLawCatalog)
        .join(DaoLawCatalog, PlayerDaoFragment.dao_law_id == DaoLawCatalog.id)
        .where(PlayerDaoFragment.player_id == player_id, PlayerDaoFragment.fragments_count > 0)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return ""

    parts = []
    for frag, law in rows:
        status = "✨" if frag.is_completed else ""
        parts.append(f"{law.emoji}{frag.fragments_count}/{law.total_fragments}{status}")

    return t(lang, "dao_summary_header") + " · ".join(parts)


def _format_effect(effect_type: str, pct: float, lang: str = "en") -> str:
    labels = {
        "cb_mult": f"⚡ +{pct:.0f}% CB",
        "bp_mult": f"🐉 +{pct:.0f}% BP",
        "hp_regen": f"🌸 +{pct:.0f}% HP regen/round",
        "cooldown_reduction": f"☯️ -{pct:.0f}% cooldowns",
        "pill_quality": f"💎 +{pct:.0f}% pill quality",
        "all_stats": t(lang, "dao_effect_all_stats", pct=pct),
    }
    return labels.get(effect_type, f"+{pct:.0f}%")
