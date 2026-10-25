"""Faction engine — join, reputation, quests, shop.

.. deprecated:: v16.2
    The binary Celestial vs Demonic faction is superseded by the Path
    Trinity (:mod:`core.path_engine`) — Righteous, Demonic, Rogue. New
    code MUST query path via ``path_engine.get_player_path`` and gate via
    ``is_demonic_path`` / ``is_righteous_path`` / ``is_rogue_path``.

    This module stays intact for backwards-compat: existing faction
    reputation, ranks, quests, and shop progress are preserved. v16.4
    (Sect-Guild Split) absorbs faction-level mechanics into NPC sect
    recruitment + rank progression and this engine retires in full.

    Until then, ``faction_engine`` remains a fallback source of "is the
    player demonic?" for the continent + lineage gates — used only when
    ``Player.path`` is NULL (player never picked / migration mid-flight).
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    FactionCatalog, PlayerFaction, FactionQuestCatalog,
    PlayerFactionQuest, FactionShopItem,
    PlayerInventory, PlayerTechnique, Player,
)

logger = logging.getLogger(__name__)

# 門 P6 (2026-09-27) — o reino a partir do qual a Facção abre. Vivia em DOIS
# sítios com o mesmo 3 escrito à mão: `webserver.FACTION_MIN_REALM` (mini-app)
# e `handlers/faction.MIN_REALM_FACTION` (chat). Dois donos do mesmo limiar
# divergem no primeiro sprint que mexer num deles — e a navegação passou a ler
# este número (`core/portas.py`), portanto um terceiro leitor tornaria a
# divergência certa. Agora é UM, aqui; os dois importam-no.
FACTION_MIN_REALM = 3

# Reputation thresholds for ranks
FACTION_RANKS = [
    ("Initiate",    0),
    ("Disciple",    500),
    ("Elder",       2_000),
    ("Core Member", 5_000),
    ("Patriarch",   15_000),
]

RANK_ORDER = {r[0]: i for i, r in enumerate(FACTION_RANKS)}


def rank_for_rep(reputation: int) -> str:
    """Return the highest rank the player qualifies for."""
    result = "Initiate"
    for name, threshold in FACTION_RANKS:
        if reputation >= threshold:
            result = name
    return result


def rank_index(rank_name: str) -> int:
    return RANK_ORDER.get(rank_name, 0)


async def get_factions(session: AsyncSession) -> list[FactionCatalog]:
    stmt = select(FactionCatalog).order_by(FactionCatalog.id)
    return list((await session.execute(stmt)).scalars().all())


async def get_player_faction(session: AsyncSession, player_id: int) -> PlayerFaction | None:
    stmt = select(PlayerFaction).where(PlayerFaction.player_id == player_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def join_faction(session: AsyncSession, player_id: int, faction_id: int) -> PlayerFaction:
    """Player joins a faction. Raises ValueError if already in one."""
    existing = await get_player_faction(session, player_id)
    if existing:
        raise ValueError("already_in_faction")

    pf = PlayerFaction(
        player_id=player_id,
        faction_id=faction_id,
        reputation=0,
        rank="Initiate",
    )
    session.add(pf)
    await session.flush()
    return pf


async def get_faction_catalog(session: AsyncSession, faction_id: int) -> FactionCatalog | None:
    return (await session.execute(
        select(FactionCatalog).where(FactionCatalog.id == faction_id)
    )).scalar_one_or_none()


async def get_faction_bonuses(session: AsyncSession, player_id: int) -> dict:
    """Return faction bonuses dict for a player, or empty dict if not in faction."""
    pf = await get_player_faction(session, player_id)
    if not pf:
        return {}
    faction = await get_faction_catalog(session, pf.faction_id)
    if not faction:
        return {}
    return dict(faction.bonuses) if faction.bonuses else {}


# ── Quests ──────────────────────────────────────────────────────────

async def get_available_quests(
    session: AsyncSession, player_id: int, faction_id: int, player_realm: int
) -> list[FactionQuestCatalog]:
    """Return faction quests the player is eligible for (by realm)."""
    stmt = (
        select(FactionQuestCatalog)
        .where(
            FactionQuestCatalog.faction_id == faction_id,
            FactionQuestCatalog.min_realm <= player_realm,
        )
        .order_by(FactionQuestCatalog.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_active_quests(
    session: AsyncSession, player_id: int
) -> list[tuple[PlayerFactionQuest, FactionQuestCatalog]]:
    """Return player's active (unclaimed) faction quests with catalog info."""
    stmt = (
        select(PlayerFactionQuest, FactionQuestCatalog)
        .join(FactionQuestCatalog, PlayerFactionQuest.quest_id == FactionQuestCatalog.id)
        .where(
            PlayerFactionQuest.player_id == player_id,
            PlayerFactionQuest.claimed == False,
        )
        .order_by(PlayerFactionQuest.accepted_at.desc())
    )
    return list((await session.execute(stmt)).all())


async def accept_quest(
    session: AsyncSession, player_id: int, quest_id: int
) -> PlayerFactionQuest | None:
    """Accept a faction quest. Returns None if on cooldown or already active."""
    # Check if already active (unclaimed)
    existing = (await session.execute(
        select(PlayerFactionQuest).where(
            PlayerFactionQuest.player_id == player_id,
            PlayerFactionQuest.quest_id == quest_id,
            PlayerFactionQuest.claimed == False,
        )
    )).scalar_one_or_none()
    if existing:
        return None  # already active

    # Check cooldown from last completed
    quest_cat = (await session.execute(
        select(FactionQuestCatalog).where(FactionQuestCatalog.id == quest_id)
    )).scalar_one_or_none()
    if not quest_cat:
        return None

    last_completed = (await session.execute(
        select(PlayerFactionQuest)
        .where(
            PlayerFactionQuest.player_id == player_id,
            PlayerFactionQuest.quest_id == quest_id,
            PlayerFactionQuest.claimed == True,
        )
        .order_by(PlayerFactionQuest.completed_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    if last_completed and last_completed.completed_at:
        cooldown_end = last_completed.completed_at + timedelta(hours=quest_cat.cooldown_hours)
        if datetime.now(timezone.utc) < cooldown_end:
            return None  # still on cooldown

    pfq = PlayerFactionQuest(
        player_id=player_id,
        quest_id=quest_id,
    )
    session.add(pfq)
    await session.flush()
    return pfq


async def update_quest_progress(
    session: AsyncSession, player_id: int, quest_type: str, amount: int = 1,
    target_filter: dict | None = None,
) -> list[FactionQuestCatalog]:
    """Increment progress for active faction quests matching quest_type.

    Called from other engines (dungeon, combat, alchemy) when the player
    performs an action that could advance a faction quest.

    target_filter — optional dict to match specific quest targets, e.g.
    {"dungeon_id": 3} so only quests targeting that dungeon advance.
    """
    pf = await get_player_faction(session, player_id)
    newly_completed = []
    if not pf:
        return newly_completed

    active = await get_active_quests(session, player_id)
    for pfq, quest_cat in active:
        if pfq.is_completed:
            continue
        if quest_cat.quest_type != quest_type:
            continue

        # Optional target matching
        if quest_cat.target:
            match = True
            for k, v in quest_cat.target.items():
                if k == "count":
                    continue
                if target_filter is None:
                    match = False
                    break
                fv = target_filter.get(k)
                if fv is None:
                    match = False
                    break
                # floor: player floor must be >= quest target floor
                if k == "floor":
                    if not isinstance(fv, int) or fv < int(v):
                        match = False
                        break
                # difficulty: compare by ordering (easy < normal < hard < nightmare)
                elif k == "difficulty":
                    _DIFF_ORD = {"easy": 1, "normal": 2, "hard": 3, "nightmare": 4}
                    if _DIFF_ORD.get(fv, 0) < _DIFF_ORD.get(v, 0):
                        match = False
                        break
                else:
                    if fv != v:
                        match = False
                        break
            if not match:
                continue

        target_count = quest_cat.target.get("count", 1)
        pfq.progress = min(pfq.progress + amount, target_count)
        if pfq.progress >= target_count:
            pfq.is_completed = True
            pfq.completed_at = datetime.now(timezone.utc)
            newly_completed.append(quest_cat)
            
    return newly_completed


async def claim_quest(
    session: AsyncSession, player_id: int, pfq_id: int
) -> tuple[bool, dict]:
    """Claim a completed faction quest. Returns (success, rewards_dict)."""
    # SEC (2026-06-01): lock the row so concurrent claims serialize — the second
    # txn blocks, then reads claimed=True and bails (no double-grant).
    pfq = (await session.execute(
        select(PlayerFactionQuest).where(
            PlayerFactionQuest.id == pfq_id,
            PlayerFactionQuest.player_id == player_id,
        ).with_for_update()
    )).scalar_one_or_none()

    if not pfq or not pfq.is_completed or pfq.claimed:
        return False, {}

    quest_cat = (await session.execute(
        select(FactionQuestCatalog).where(FactionQuestCatalog.id == pfq.quest_id)
    )).scalar_one_or_none()
    if not quest_cat:
        return False, {}

    pfq.claimed = True

    # Add reputation — rank is based on total_rep_earned (never drops)
    player_faction = await get_player_faction(session, player_id)
    if player_faction:
        player_faction.reputation += quest_cat.reward_rep
        player_faction.total_rep_earned += quest_cat.reward_rep
        player_faction.rank = rank_for_rep(player_faction.total_rep_earned)

    # Apply item rewards
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()

    rewards = dict(quest_cat.reward_items)
    rewards["reputation"] = quest_cat.reward_rep

    if player:
        if "spirit_stones" in rewards:
            player.spirit_stones += rewards["spirit_stones"]
        if "spirit_jade" in rewards:
            from core.monetization import grant_jade
            await grant_jade(session, player, rewards["spirit_jade"])

        # Herb rewards → inventory
        if "herbs" in rewards:
            for herb_entry in rewards["herbs"]:
                herb_id = herb_entry["id"]
                qty = herb_entry.get("qty", 1)
                inv = (await session.execute(
                    select(PlayerInventory).where(
                        PlayerInventory.player_id == player_id,
                        PlayerInventory.item_type == "herb",
                        PlayerInventory.item_id == herb_id,
                    )
                )).scalar_one_or_none()
                if inv:
                    inv.quantity += qty
                else:
                    session.add(PlayerInventory(
                        player_id=player_id, item_type="herb",
                        item_id=herb_id, quantity=qty,
                    ))

    return True, rewards


# ── Shop ────────────────────────────────────────────────────────────

async def get_shop_item(session: AsyncSession, item_id: int) -> FactionShopItem | None:
    """Return a single shop item by ID."""
    return (await session.execute(
        select(FactionShopItem).where(FactionShopItem.id == item_id)
    )).scalar_one_or_none()


async def get_shop_items(
    session: AsyncSession, faction_id: int, player_rank: str
) -> list[FactionShopItem]:
    """Return shop items the player's rank qualifies for."""
    all_items = (await session.execute(
        select(FactionShopItem)
        .where(FactionShopItem.faction_id == faction_id)
        .order_by(FactionShopItem.rep_cost)
    )).scalars().all()

    return list(all_items)


async def buy_shop_item(
    session: AsyncSession, player_id: int, item_id: int
) -> tuple[bool, str]:
    """Purchase a shop item with reputation. Returns (success, error_key).

    Reputation is spent as currency — rank never drops on purchase.
    All validation happens BEFORE any state changes.
    """
    pf = await get_player_faction(session, player_id)
    if not pf:
        return False, "faction_not_joined"

    item = (await session.execute(
        select(FactionShopItem).where(FactionShopItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        return False, "faction_shop_item_not_found"

    if item.faction_id != pf.faction_id:
        return False, "faction_shop_wrong_faction"

    if rank_index(pf.rank) < rank_index(item.min_rank):
        return False, "faction_shop_rank_too_low"

    if pf.reputation < item.rep_cost:
        return False, "faction_shop_not_enough_rep"

    # ── Validate BEFORE deducting rep ──
    if item.item_type == "technique":
        tech_id = item.item_data.get("technique_id")
        if tech_id:
            from database.models import TechniqueCatalog
            tech = (await session.execute(
                select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
            )).scalar_one_or_none()
            player = (await session.execute(
                select(Player).where(Player.telegram_id == player_id)
            )).scalar_one_or_none()
            if tech and player and player.realm < tech.req_realm:
                return False, "faction_shop_realm_too_low"
            existing = (await session.execute(
                select(PlayerTechnique).where(
                    PlayerTechnique.player_id == player_id,
                    PlayerTechnique.technique_id == tech_id,
                )
            )).scalar_one_or_none()
            if existing:
                return False, "faction_shop_already_owned"

    elif item.item_type == "recipe":
        recipe_id = item.item_data.get("recipe_id", 0)
        inv = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == player_id,
                PlayerInventory.item_type == "recipe",
                PlayerInventory.item_id == recipe_id,
            )
        )).scalar_one_or_none()
        if inv:
            return False, "faction_shop_already_owned"

    elif item.item_type == "artifact":
        from database.models import PlayerArtifact, ArtifactCatalog
        artifact_id = item.item_data.get("artifact_id")
        if artifact_id:
            art_cat = (await session.execute(
                select(ArtifactCatalog).where(ArtifactCatalog.id == artifact_id)
            )).scalar_one_or_none()
            if not art_cat:
                return False, "faction_shop_item_not_found"

    # ── All validation passed — deduct reputation (rank stays) ──
    pf.reputation -= item.rep_cost

    # ── Deliver item ──
    if item.item_type == "technique":
        tech_id = item.item_data.get("technique_id")
        if tech_id:
            session.add(PlayerTechnique(
                player_id=player_id,
                technique_id=tech_id,
                mastery_level=1,
                mastery_xp=0,
                is_active_combat=False,
            ))

    elif item.item_type == "recipe":
        recipe_id = item.item_data.get("recipe_id", 0)
        session.add(PlayerInventory(
            player_id=player_id, item_type="recipe",
            item_id=recipe_id, quantity=1,
        ))

    elif item.item_type == "artifact":
        from database.models import PlayerArtifact, ArtifactCatalog
        artifact_id = item.item_data.get("artifact_id")
        if artifact_id:
            art_cat = (await session.execute(
                select(ArtifactCatalog).where(ArtifactCatalog.id == artifact_id)
            )).scalar_one_or_none()
            session.add(PlayerArtifact(
                player_id=player_id,
                catalog_id=artifact_id,
                grade=art_cat.grade,
                slot=None,
                is_equipped=False,
                custom_stats=dict(art_cat.base_stats) if art_cat.base_stats else {},
            ))

    elif item.item_type == "pill":
        pill_id = item.item_data.get("pill_id")
        qty = item.item_data.get("qty", 1)
        if pill_id:
            inv = (await session.execute(
                select(PlayerInventory).where(
                    PlayerInventory.player_id == player_id,
                    PlayerInventory.item_type == "pill",
                    PlayerInventory.item_id == pill_id,
                )
            )).scalar_one_or_none()
            if inv:
                inv.quantity += qty
            else:
                session.add(PlayerInventory(
                    player_id=player_id, item_type="pill",
                    item_id=pill_id, quantity=qty,
                ))

    return True, ""
