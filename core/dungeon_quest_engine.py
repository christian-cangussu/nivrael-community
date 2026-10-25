"""
Dungeon Quest Engine — story-driven quests tied to specific dungeons.

Handles quest acceptance, progress tracking, cooldown management,
and reward distribution. Integrates with faction rep if player has one.
"""

# 名 2026-09-14 — nome de quest pelo dono unico.
from core.i18n import catalog_name
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_

from database.models import (
    DungeonQuestCatalog, PlayerDungeonQuest,
    Player, PlayerFaction,
)

logger = logging.getLogger(__name__)


# ── Difficulty level ordering (mirrors handlers/dungeons.py) ────────
DIFF_ORDER = {"easy": 1, "normal": 2, "hard": 3, "nightmare": 4}


async def get_dungeon_quests(session, dungeon_id: int) -> list[DungeonQuestCatalog]:
    """Get all quest catalog entries for a specific dungeon."""
    stmt = select(DungeonQuestCatalog).where(
        DungeonQuestCatalog.dungeon_id == dungeon_id
    ).order_by(DungeonQuestCatalog.id)
    return (await session.execute(stmt)).scalars().all()


async def get_player_dungeon_quests(
    session, player_id: int, dungeon_id: int
) -> list[tuple[DungeonQuestCatalog, PlayerDungeonQuest | None]]:
    """
    Get all quests for a dungeon with the player's progress (if any).
    Returns list of (quest_catalog, player_quest_or_None).
    """
    quests = await get_dungeon_quests(session, dungeon_id)
    if not quests:
        return []

    quest_ids = [q.id for q in quests]
    stmt = select(PlayerDungeonQuest).where(
        PlayerDungeonQuest.player_id == player_id,
        PlayerDungeonQuest.quest_id.in_(quest_ids),
    )
    player_quests = (await session.execute(stmt)).scalars().all()
    pq_map = {pq.quest_id: pq for pq in player_quests}

    return [(q, pq_map.get(q.id)) for q in quests]


def is_quest_on_cooldown(pdq: PlayerDungeonQuest | None, cooldown_hours: int) -> tuple[bool, int]:
    """
    Check if a repeatable quest is still on cooldown.
    Returns (on_cooldown, remaining_hours).
    """
    if pdq is None or pdq.last_completed_at is None:
        return False, 0

    now = datetime.now(timezone.utc)
    cooldown_end = pdq.last_completed_at + timedelta(hours=cooldown_hours)
    if now < cooldown_end:
        remaining = int((cooldown_end - now).total_seconds() / 3600) + 1
        return True, remaining
    return False, 0


def is_difficulty_met(current_difficulty: str, min_difficulty: str) -> bool:
    """Check if the current difficulty meets the quest's minimum requirement."""
    return DIFF_ORDER.get(current_difficulty, 1) >= DIFF_ORDER.get(min_difficulty, 1)


async def accept_dungeon_quest(
    session, player_id: int, quest_id: int
) -> tuple[bool, str]:
    """
    Accept a dungeon quest. Returns (success, error_key_or_empty).

    Handles:
    - Cooldown check for repeatable quests
    - Re-activation of previously completed quests
    - First-time acceptance
    """
    quest = await session.get(DungeonQuestCatalog, quest_id)
    if not quest:
        return False, "dng_quest_not_found"

    # Check existing progress
    stmt = select(PlayerDungeonQuest).where(and_(
        PlayerDungeonQuest.player_id == player_id,
        PlayerDungeonQuest.quest_id == quest_id,
    ))
    pdq = (await session.execute(stmt)).scalar_one_or_none()

    if pdq:
        if pdq.is_active:
            return False, "dng_quest_already_active"

        # Check cooldown for repeatable quests
        on_cd, remaining = is_quest_on_cooldown(pdq, quest.cooldown_hours)
        if on_cd:
            return False, f"dng_quest_cooldown:{remaining}"

        # Re-activate quest
        pdq.progress = 0
        pdq.is_active = True
        pdq.accepted_at = datetime.now(timezone.utc)
    else:
        # First time accepting
        session.add(PlayerDungeonQuest(
            player_id=player_id,
            quest_id=quest_id,
            progress=0,
            is_active=True,
        ))

    return True, ""


async def track_dungeon_quest_progress(
    session, player_id: int, dungeon_id: int,
    event_type: str, floor: int = 0, difficulty: str = "easy",
    dungeon_completed: bool = False, *, amount: int = 1,
):
    """
    Track progress on active dungeon quests after a floor win or dungeon completion.

    event_type: 'floor_win' or 'dungeon_complete'
    floor: the floor that was just won
    difficulty: current difficulty
    dungeon_completed: whether the dungeon was fully completed
    amount: how many wins of THIS floor the call represents (multi-sweep do
        mini comprime N varreduras numa chamada por andar). Keyword-only de
        propósito (lição QoL-relatos) e lido SÓ pelo objetivo cumulativo
        'floor_count' — os thresholds (complete_floor/complete_dungeon) são
        binários e não acumulam.
    """
    # Get active quests for this dungeon
    stmt = (
        select(PlayerDungeonQuest, DungeonQuestCatalog)
        .join(DungeonQuestCatalog, DungeonQuestCatalog.id == PlayerDungeonQuest.quest_id)
        .where(
            PlayerDungeonQuest.player_id == player_id,
            DungeonQuestCatalog.dungeon_id == dungeon_id,
            PlayerDungeonQuest.is_active == True,
        )
    )
    rows = (await session.execute(stmt)).all()

    completed_quests = []
    for pdq, quest in rows:
        # Check difficulty requirement
        if not is_difficulty_met(difficulty, quest.min_difficulty):
            continue

        objective_met = False

        if quest.objective_type == "complete_floor":
            target_floor = int(quest.objective_target) if quest.objective_target else 1
            if floor >= target_floor:
                objective_met = True

        elif quest.objective_type == "complete_dungeon":
            if dungeon_completed:
                objective_met = True

        elif quest.objective_type == "floor_count":
            # Track cumulative floor wins
            pdq.progress = min(pdq.progress + max(1, int(amount)), quest.objective_count)
            if pdq.progress >= quest.objective_count:
                objective_met = True

        if objective_met and pdq.progress < quest.objective_count:
            pdq.progress = quest.objective_count  # Mark as complete

        if pdq.progress >= quest.objective_count:
            completed_quests.append((pdq, quest))

    return completed_quests


async def claim_dungeon_quest_reward(
    session, player_id: int, quest_id: int, lang: str = "pt"
) -> tuple[dict | None, str]:
    """
    Claim rewards for a completed dungeon quest.
    Returns (rewards_dict, quest_name) or (None, error_key).
    """
    # SEC (2026-06-01): lock the row so concurrent claims serialize — the second
    # txn blocks, re-reads is_active=False under the lock, and bails (no double-grant).
    stmt = (
        select(PlayerDungeonQuest, DungeonQuestCatalog)
        .join(DungeonQuestCatalog, DungeonQuestCatalog.id == PlayerDungeonQuest.quest_id)
        .where(
            PlayerDungeonQuest.player_id == player_id,
            PlayerDungeonQuest.quest_id == quest_id,
            PlayerDungeonQuest.is_active == True,
        )
        .with_for_update(of=PlayerDungeonQuest)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None, "dng_quest_not_active"

    pdq, quest = row

    if pdq.progress < quest.objective_count:
        return None, "dng_quest_not_completed"

    # Build rewards dict
    rewards = {}

    # Spirit Stones
    if quest.reward_stones > 0:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()
        if player:
            player.spirit_stones += quest.reward_stones
            rewards["spirit_stones"] = quest.reward_stones

    # Faction Reputation (if player has a faction)
    if quest.reward_rep > 0:
        pf_stmt = select(PlayerFaction).where(PlayerFaction.player_id == player_id)
        pf = (await session.execute(pf_stmt)).scalar_one_or_none()
        if pf:
            from core.faction_engine import rank_for_rep
            pf.reputation += quest.reward_rep
            pf.total_rep_earned += quest.reward_rep
            pf.rank = rank_for_rep(pf.total_rep_earned)
            rewards["reputation"] = quest.reward_rep
        else:
            # QoL-Feedback 2026-07-29 Item C (report [jogador]): sem facção o crédito
            # era PULADO em silêncio enquanto o preview prometia "reputação".
            # Chave condicional — os consumidores dizem o que se perdeu (Lei §1).
            rewards["reputation_missed"] = quest.reward_rep

    # Item rewards
    reward_items = quest.reward_items or {}
    if reward_items:
        await _apply_item_rewards(session, player_id, reward_items)
        rewards["items"] = reward_items

    # Mark quest as completed
    pdq.is_active = False
    pdq.completed_count += 1
    pdq.last_completed_at = datetime.now(timezone.utc)

    from core.activity_indicators import _invalidate_cache as _inv_cache
    _inv_cache(player_id)

    return rewards, catalog_name(lang, "q", quest)


async def _apply_item_rewards(session, player_id: int, items: dict):
    """Apply item reward payloads from quest reward_items JSON."""
    from core.utils import add_item_to_inventory

    # technique_scroll: int quantity
    if "technique_scroll" in items:
        import random
        from database.models import TechniqueCatalog, PlayerTechnique, PlayerInventory
        # TEC-2 — as quests de masmorra são REPETÍVEIS por cooldown e dão 1-3
        # pergaminhos garantidos; pós-corte seriam a fonte dominante. A quest
        # continua entregando o que promete, só não entrega três (Lei §1).
        # Flag OFF ⇒ a quantidade original.
        from core.scroll_economy_engine import quest_scroll_qty
        qty = quest_scroll_qty(items["technique_scroll"])
        # v16.4c — exclude house signature arts (sect_key): Library-only (rank-gated,
        # no scroll), never a quest scroll reward (Lei §5 — live drop economy untouched).
        all_techs = (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.sect_key.is_(None))
        )).scalars().all()
        known_ids = set((await session.execute(
            select(PlayerTechnique.technique_id).where(
                PlayerTechnique.player_id == player_id
            )
        )).scalars().all())
        pool = [t for t in all_techs if t.id not in known_ids] or list(all_techs)
        for _ in range(qty):
            chosen = random.choice(pool)
            await add_item_to_inventory(session, player_id, "technique_scroll", chosen.id)

    # herb_pack: int quantity (random herbs)
    if "herb_pack" in items:
        import random
        count = items["herb_pack"]
        herb_ids = [1, 2, 3, 12, 9]
        herb_weights = [35, 25, 15, 15, 10]
        for _ in range(count):
            herb_id = random.choices(herb_ids, weights=herb_weights, k=1)[0]
            await add_item_to_inventory(session, player_id, "herb", herb_id, 3)

    # dao_fragment: int quantity
    if "dao_fragment" in items:
        from database.models import DaoLawCatalog, PlayerDaoFragment
        import random
        dao_laws = (await session.execute(select(DaoLawCatalog))).scalars().all()
        if dao_laws:
            for _ in range(items["dao_fragment"]):
                law = random.choice(dao_laws)
                stmt = select(PlayerDaoFragment).where(and_(
                    PlayerDaoFragment.player_id == player_id,
                    PlayerDaoFragment.dao_law_id == law.id,
                ))
                frag = (await session.execute(stmt)).scalar_one_or_none()
                if frag and not frag.is_completed:
                    frag.fragments_count = min(frag.fragments_count + 1, law.total_fragments)
                    if frag.fragments_count >= law.total_fragments:
                        frag.is_completed = True
                elif not frag:
                    session.add(PlayerDaoFragment(
                        player_id=player_id,
                        dao_law_id=law.id,
                        fragments_count=1,
                    ))

    # ore: {"id": int, "qty": int}
    if "ore" in items and isinstance(items["ore"], dict):
        from database.models import PlayerOre
        ore_id = items["ore"]["id"]
        qty = items["ore"]["qty"]
        stmt = select(PlayerOre).where(and_(
            PlayerOre.player_id == player_id,
            PlayerOre.ore_id == ore_id,
        ))
        ore_row = (await session.execute(stmt)).scalar_one_or_none()
        if ore_row:
            ore_row.quantity += qty
        else:
            session.add(PlayerOre(player_id=player_id, ore_id=ore_id, quantity=qty))

    # herb: {"id": int, "qty": int}
    if "herb" in items and isinstance(items["herb"], dict):
        herb_id = items["herb"]["id"]
        qty = items["herb"]["qty"]
        await add_item_to_inventory(session, player_id, "herb", herb_id, qty)
