"""
3000 Dao Laws Engine — discovery, tiers, category bonuses.

Works alongside the existing Supreme Laws system (dao_engine.py).
Supreme Laws = fragment-based (6 existing laws).
3000 Laws = discovery-based (binary: known or unknown).
"""
import math
import random
import logging
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    DaoCategory, DaoPath, DaoPathLaw, PlayerDaoDiscovery,
)

logger = logging.getLogger(__name__)

# ── Tier System ───────────────────────────────────────────────────────────────

TIER_THRESHOLDS = {
    # tier: (min_pct, name_en, name_pt, name_es, stars, bonus)
    0: (0.00, "None",          "Nenhum",       "Ninguno",       "",          0.00),
    1: (0.10, "Insight",       "Vislumbre",    "Vislumbre",     "★",         0.03),
    2: (0.30, "Comprehension", "Compreensão",  "Comprensión",   "★★",        0.06),
    3: (0.50, "Mastery",       "Maestria",     "Maestría",      "★★★",       0.10),
    4: (0.90, "Perfection",    "Perfeição",    "Perfección",    "★★★★",      0.15),
    5: (1.00, "Dao Heart",     "Coração Dao",  "Corazón Dao",   "★★★★★",     0.25),
}

RARITY_WEIGHTS = {
    "common": 50,
    "uncommon": 30,
    "rare": 15,
    "epic": 4,
    "legendary": 1,
}

RARITY_EMOJIS = {
    "common": "⬜",
    "uncommon": "🟩",
    "rare": "🟦",
    "epic": "🟪",
    "legendary": "🟧",
}

# Base chance per tick (30s) of discovering a law during Dao meditation
# Calibrated for 3000 laws: dao_basic ~3/session, dao_transcend ~22/session
BASE_DISCOVERY_CHANCE = 0.015


def get_path_tier(discovered: int, total: int) -> int:
    """Calculate tier based on discovered/total ratio."""
    if total <= 0:
        return 0
    pct = discovered / total
    tier = 0
    for t_level in range(5, -1, -1):
        if pct >= TIER_THRESHOLDS[t_level][0]:
            tier = t_level
            break
    return tier


def get_tier_info(tier: int, lang: str = "en") -> dict:
    """Get tier name, stars, and bonus for a given tier."""
    info = TIER_THRESHOLDS.get(tier, TIER_THRESHOLDS[0])
    lang_idx = {"en": 1, "pt": 2, "es": 3}.get(lang, 1)
    return {
        "tier": tier,
        "name": info[lang_idx],
        "stars": info[4],
        "bonus": info[5],
    }


# ── Discovery Logic ───────────────────────────────────────────────────────────

async def _get_accessible_paths(session: AsyncSession, player_id: int, player_realm: int, heavenly_only: bool = False):
    """
    Return paths the player can currently discover laws in.
    Heavenly paths (F-11.5) are only accessible after passing the 1st Celestial Trial.
    """
    from database.models import Player
    player_row = (await session.execute(
        select(Player.celestial_trials_passed).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()
    trials_passed = player_row or 0

    stmt = select(DaoPath).where(DaoPath.min_realm <= player_realm)
    paths = (await session.execute(stmt)).scalars().all()
    if heavenly_only:
        paths = [p for p in paths if getattr(p, "is_heavenly", False)]
    if trials_passed < 1:
        # Filter out heavenly paths — still locked behind 1st trial.
        paths = [p for p in paths if not getattr(p, "is_heavenly", False)]
    return paths


async def try_discover_law(
    session: AsyncSession,
    player_id: int,
    player_realm: int,
    dao_fragment_mult: float = 1.0,
    perception: int = 100,
    heavenly_only: bool = False,
    force: bool = False,
) -> dict | None:
    """
    Attempt to discover a new Dao law during meditation tick.

    `heavenly_only=True` restricts the pool to Heavenly Dao paths (F-11.5);
    used by the Celestial Meditation type.

    `force=True` bypasses the random discovery roll (a discovery is granted as
    long as an undiscovered accessible law exists). Used for the guaranteed
    "first comprehension" when a cultivator reaches the Dao-unlock realm
    (D5, v16.6).

    Returns dict with discovery info or None if no discovery.
    """
    paths = await _get_accessible_paths(session, player_id, player_realm, heavenly_only=heavenly_only)
    if not paths:
        return None

    path_ids = [p.id for p in paths]

    # Count total accessible laws and already discovered
    total_accessible = (await session.execute(
        select(func.count(DaoPathLaw.id)).where(DaoPathLaw.path_id.in_(path_ids))
    )).scalar() or 0

    discovered_count = (await session.execute(
        select(func.count(PlayerDaoDiscovery.law_id))
        .where(
            PlayerDaoDiscovery.player_id == player_id,
            PlayerDaoDiscovery.law_id.in_(
                select(DaoPathLaw.id).where(DaoPathLaw.path_id.in_(path_ids))
            ),
        )
    )).scalar() or 0

    if total_accessible <= 0 or discovered_count >= total_accessible:
        return None  # All laws discovered

    # Discovery chance: decreases as more laws are discovered
    undiscovered_ratio = (total_accessible - discovered_count) / total_accessible
    chance = BASE_DISCOVERY_CHANCE * math.sqrt(dao_fragment_mult) * undiscovered_ratio

    if not force and random.random() > chance:
        return None

    # Pick an undiscovered law, weighted by rarity
    # Higher perception = better chance of rare+ laws
    perception_factor = min(perception / 5000.0, 2.0)  # cap at 2x

    # Get all undiscovered laws in accessible paths
    discovered_ids_stmt = select(PlayerDaoDiscovery.law_id).where(
        PlayerDaoDiscovery.player_id == player_id
    )
    undiscovered = (await session.execute(
        select(DaoPathLaw)
        .where(
            DaoPathLaw.path_id.in_(path_ids),
            DaoPathLaw.id.notin_(discovered_ids_stmt),
        )
    )).scalars().all()

    if not undiscovered:
        return None

    # Weight by rarity — perception shifts weights toward rarer laws
    weights = []
    for law in undiscovered:
        base_w = RARITY_WEIGHTS.get(law.rarity, 50)
        if law.rarity in ("rare", "epic"):
            # Higher perception = more weight on rare/epic
            w = base_w * perception_factor
        else:
            w = base_w
        weights.append(w)

    chosen_law = random.choices(undiscovered, weights=weights, k=1)[0]

    # Record discovery
    session.add(PlayerDaoDiscovery(
        player_id=player_id,
        law_id=chosen_law.id,
        discovered_at=datetime.now(timezone.utc),
    ))

    # Get path info for the discovered law
    path = (await session.execute(
        select(DaoPath).where(DaoPath.id == chosen_law.path_id)
    )).scalar_one()

    category = (await session.execute(
        select(DaoCategory).where(DaoCategory.id == path.category_id)
    )).scalar_one()

    # F-11.5: Discovering a Heavenly Law grants +3 Celestial Essence so players
    # aren't stuck at the post-trial essence pool (470) when needing 1400 for
    # tier-12 body tempering. 100 heavenly laws × 3 = +300 essence.
    essence_gain = 0
    if getattr(path, "is_heavenly", False):
        from database.models import Player
        pl = (await session.execute(
            select(Player).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()
        if pl is not None:
            essence_gain = 3
            pl.celestial_essence = (pl.celestial_essence or 0) + essence_gain

    # Count discoveries in this path (autoflush includes the just-added record)
    path_discovered = (await session.execute(
        select(func.count(PlayerDaoDiscovery.law_id))
        .where(
            PlayerDaoDiscovery.player_id == player_id,
            PlayerDaoDiscovery.law_id.in_(
                select(DaoPathLaw.id).where(DaoPathLaw.path_id == path.id)
            ),
        )
    )).scalar() or 0

    old_tier = get_path_tier(path_discovered - 1, path.total_laws)
    new_tier = get_path_tier(path_discovered, path.total_laws)
    tier_up = new_tier > old_tier

    return {
        "law_name": chosen_law.name,
        "law_name_pt": chosen_law.name_pt,
        "law_name_es": chosen_law.name_es,
        "law_rarity": chosen_law.rarity,
        "rarity_emoji": RARITY_EMOJIS.get(chosen_law.rarity, "⬜"),
        "path_name": path.name,
        "path_name_pt": path.name_pt,
        "path_name_es": path.name_es,
        "path_emoji": path.emoji,
        "category_name": category.name,
        "category_name_pt": category.name_pt,
        "category_name_es": category.name_es,
        "category_emoji": category.emoji,
        "path_discovered": path_discovered,
        "path_total": path.total_laws,
        "tier_up": tier_up,
        "new_tier": new_tier,
        "is_heavenly": bool(getattr(path, "is_heavenly", False)),
        "celestial_essence_gained": essence_gain,
    }


# ── Bonuses ───────────────────────────────────────────────────────────────────

async def get_dao_laws_bonuses(session: AsyncSession, player_id: int, player_realm: int) -> dict:
    """
    Calculate aggregate bonuses from all discovered Dao laws.
    Returns dict of bonus_type -> total bonus value.

    Heavenly paths (F-11.5) only contribute if the player has passed the 1st
    Celestial Trial. Otherwise their discoveries are latent.
    """
    bonuses = {
        "cb_mult": 0.0,
        "bp_mult": 0.0,
        "hp_regen": 0.0,
        "cooldown_reduction": 0.0,
        "tribulation_bonus": 0.0,
        "craft_quality": 0.0,
        "all_stats": 0.0,
        "all_mult": 0.0,
    }

    from database.models import Player
    trials_passed = (await session.execute(
        select(Player.celestial_trials_passed).where(Player.telegram_id == player_id)
    )).scalar_one_or_none() or 0

    paths = (await session.execute(
        select(DaoPath).where(DaoPath.min_realm <= player_realm)
    )).scalars().all()
    if trials_passed < 1:
        paths = [p for p in paths if not getattr(p, "is_heavenly", False)]
    if not paths:
        return bonuses

    for path in paths:
        discovered = (await session.execute(
            select(func.count(PlayerDaoDiscovery.law_id))
            .where(
                PlayerDaoDiscovery.player_id == player_id,
                PlayerDaoDiscovery.law_id.in_(
                    select(DaoPathLaw.id).where(DaoPathLaw.path_id == path.id)
                ),
            )
        )).scalar() or 0

        if discovered == 0:
            continue

        tier = get_path_tier(discovered, path.total_laws)
        if tier == 0:
            continue

        tier_bonus = TIER_THRESHOLDS[tier][5]
        bonus_type = path.bonus_type
        if bonus_type in bonuses:
            bonuses[bonus_type] += tier_bonus

    return bonuses


async def get_category_summary(session: AsyncSession, player_id: int, player_realm: int, lang: str = "en") -> list[dict]:
    """Get summary of all categories with discovery counts and tiers."""
    categories = (await session.execute(
        select(DaoCategory).order_by(DaoCategory.sort_order)
    )).scalars().all()

    result = []
    for cat in categories:
        locked = player_realm < cat.min_realm

        paths = (await session.execute(
            select(DaoPath).where(DaoPath.category_id == cat.id).order_by(DaoPath.sort_order)
        )).scalars().all()

        total_laws = sum(p.total_laws for p in paths)
        discovered = 0
        path_summaries = []

        for path in paths:
            path_locked = player_realm < path.min_realm
            p_disc = 0
            if not path_locked:
                p_disc = (await session.execute(
                    select(func.count(PlayerDaoDiscovery.law_id))
                    .where(
                        PlayerDaoDiscovery.player_id == player_id,
                        PlayerDaoDiscovery.law_id.in_(
                            select(DaoPathLaw.id).where(DaoPathLaw.path_id == path.id)
                        ),
                    )
                )).scalar() or 0
            discovered += p_disc

            tier = get_path_tier(p_disc, path.total_laws) if not path_locked else 0
            tier_info = get_tier_info(tier, lang)

            lang_key = {"en": "name", "pt": "name_pt", "es": "name_es"}.get(lang, "name")
            path_name = getattr(path, lang_key, None) or path.name

            path_summaries.append({
                "id": path.id,
                "name": path_name,
                "emoji": path.emoji,
                "discovered": p_disc,
                "total": path.total_laws,
                "tier": tier,
                "tier_info": tier_info,
                "locked": path_locked,
                "min_realm": path.min_realm,
            })

        lang_key = {"en": "name", "pt": "name_pt", "es": "name_es"}.get(lang, "name")
        cat_name = getattr(cat, lang_key, None) or cat.name

        result.append({
            "id": cat.id,
            "name": cat_name,
            "emoji": cat.emoji,
            "discovered": discovered,
            "total_laws": total_laws,
            "locked": locked,
            "min_realm": cat.min_realm,
            "bonus_type": cat.bonus_type,
            "paths": path_summaries,
        })

    return result


async def get_path_discovered_laws(
    session: AsyncSession, player_id: int, path_id: int, page: int = 1, per_page: int = 8
) -> tuple[list[dict], int, int]:
    """Get discovered laws in a path with pagination. Returns (laws, total_discovered, total_pages)."""
    total_discovered = (await session.execute(
        select(func.count(PlayerDaoDiscovery.law_id))
        .where(
            PlayerDaoDiscovery.player_id == player_id,
            PlayerDaoDiscovery.law_id.in_(
                select(DaoPathLaw.id).where(DaoPathLaw.path_id == path_id)
            ),
        )
    )).scalar() or 0

    total_pages = max(1, math.ceil(total_discovered / per_page))
    page = max(1, min(page, total_pages))
    offset = (page - 1) * per_page

    rows = (await session.execute(
        select(DaoPathLaw, PlayerDaoDiscovery.discovered_at)
        .join(PlayerDaoDiscovery, PlayerDaoDiscovery.law_id == DaoPathLaw.id)
        .where(
            PlayerDaoDiscovery.player_id == player_id,
            DaoPathLaw.path_id == path_id,
        )
        .order_by(PlayerDaoDiscovery.discovered_at.desc())
        .offset(offset)
        .limit(per_page)
    )).all()

    laws = []
    for law, disc_at in rows:
        laws.append({
            "name": law.name,
            "name_pt": law.name_pt,
            "name_es": law.name_es,
            "rarity": law.rarity,
            "rarity_emoji": RARITY_EMOJIS.get(law.rarity, "⬜"),
            "discovered_at": disc_at,
        })

    return laws, total_discovered, total_pages


async def get_total_discoveries(session: AsyncSession, player_id: int) -> int:
    """Get total number of discovered laws for a player."""
    return (await session.execute(
        select(func.count(PlayerDaoDiscovery.law_id))
        .where(PlayerDaoDiscovery.player_id == player_id)
    )).scalar() or 0


async def grant_first_law_on_unlock(session: AsyncSession, player_id: int, target_realm: int,
                                    perception: int = 100, lang: str = "pt") -> str | None:
    """D5 (v16.6): guaranteed "first comprehension" when a cultivator reaches the
    Dao-unlock realm (Soul Transformation, realm 5). Returns a ready-to-show
    message line, or None if not applicable.

    Called from the tribulation-SUCCESS paths (the 4→5 breakthrough always goes
    through Heavenly Tribulation since TRIBULATION_START_REALM=4), NOT from the
    plain breakthrough branch. Idempotent: only grants when the player has zero
    Dao discoveries, so the three trib paths can't double-grant.
    """
    try:
        from core.dao_engine import DAO_UNLOCK_REALM
        if int(target_realm) != int(DAO_UNLOCK_REALM):
            return None
        if await get_total_discoveries(session, player_id) != 0:
            return None
        fl = await try_discover_law(
            session, player_id, int(target_realm),
            dao_fragment_mult=1.0, perception=int(perception or 100),
            heavenly_only=False, force=True,
        )
        if not fl:
            return None
        from core.i18n import t
        law_name = fl.get(f"law_name_{lang}") or fl.get("law_name", "???")
        return t(lang, "dao_first_law_granted", law=law_name)
    except Exception:
        logger.exception("grant_first_law_on_unlock failed player=%s", player_id)
        return None


async def count_heavenly_discoveries(session: AsyncSession, player_id: int) -> tuple[int, int]:
    """
    Return (discovered, total) count of laws in heavenly (F-11.5) paths.
    Used by the /celestial dashboard and the Heavenly Sage title check.
    """
    heavenly_path_ids_stmt = select(DaoPath.id).where(DaoPath.is_heavenly == True)
    total = (await session.execute(
        select(func.count(DaoPathLaw.id)).where(DaoPathLaw.path_id.in_(heavenly_path_ids_stmt))
    )).scalar() or 0
    discovered = (await session.execute(
        select(func.count(PlayerDaoDiscovery.law_id))
        .where(
            PlayerDaoDiscovery.player_id == player_id,
            PlayerDaoDiscovery.law_id.in_(
                select(DaoPathLaw.id).where(DaoPathLaw.path_id.in_(heavenly_path_ids_stmt))
            ),
        )
    )).scalar() or 0
    return int(discovered), int(total)


async def count_dao_heart_paths(session: AsyncSession, player_id: int) -> int:
    """Count how many paths have reached Dao Heart (tier 5)."""
    paths = (await session.execute(select(DaoPath))).scalars().all()
    count = 0
    for path in paths:
        discovered = (await session.execute(
            select(func.count(PlayerDaoDiscovery.law_id))
            .where(
                PlayerDaoDiscovery.player_id == player_id,
                PlayerDaoDiscovery.law_id.in_(
                    select(DaoPathLaw.id).where(DaoPathLaw.path_id == path.id)
                ),
            )
        )).scalar() or 0
        if get_path_tier(discovered, path.total_laws) >= 5:
            count += 1
    return count
