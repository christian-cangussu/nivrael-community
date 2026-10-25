import logging
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BattlePassMission

logger = logging.getLogger(__name__)

# All reward_items reference real DB item IDs (see alchemy_seeds.py / artifacts_seeds.py).
# description_key maps to locale files (en/pt/es.json) — DB stays in English.
# objective_types: craft_pills, win_npc_fight, forge_artifact, win_sparring,
#   complete_quests, foundation_trial, alchemy_tier, win_tribulation,
#   complete_dungeon, golden_core
BP_MISSIONS = [
    # ── Tier 5 ──────────────────────────────────────────────────────────────
    {
        "id": 1,
        "tier": 5,
        "objective_type": "craft_pills",
        "objective_value": 5,
        "reward_jade": 10,
        "reward_items": [],
        "is_premium_only": False,
        "description_key": "bp_miss_craft_pills",
    },
    {
        "id": 2,
        "tier": 5,
        "objective_type": "win_sparring",
        "objective_value": 2,
        "reward_jade": 0,
        "reward_items": [{"type": "pill", "pill_id": 1, "qty": 5}],  # Qi Gathering Pill
        "is_premium_only": False,
        "description_key": "bp_miss_win_sparring",
    },
    {
        "id": 3,
        "tier": 5,
        "objective_type": "complete_quests",
        "objective_value": 3,
        "reward_jade": 10,
        "reward_items": [{"type": "herb", "herb_id": 1, "qty": 10}],  # Qi Root Herb
        "is_premium_only": False,
        "description_key": "bp_miss_complete_quests",
    },
    # ── Tier 10 ─────────────────────────────────────────────────────────────
    {
        "id": 4,
        "tier": 10,
        "objective_type": "win_npc_fight",
        "objective_value": 3,
        "reward_jade": 20,
        "reward_items": [{"type": "herb", "herb_id": 3, "qty": 3}],  # Foundation Lotus
        "is_premium_only": False,
        "description_key": "bp_miss_win_npc_fight",
    },
    {
        "id": 5,
        "tier": 10,
        "objective_type": "forge_artifact",
        "objective_value": 1,
        "reward_jade": 20,
        "reward_items": [{"type": "ore", "ore_id": 2, "qty": 5}],  # Spirit Copper
        "is_premium_only": False,
        "description_key": "bp_miss_forge_artifact",
    },
    {
        "id": 6,
        "tier": 10,
        "objective_type": "craft_pills",
        "objective_value": 15,
        "reward_jade": 15,
        "reward_items": [{"type": "spirit_stones", "amount": 2000}],
        "is_premium_only": False,
        "description_key": "bp_miss_craft_pills",
    },
    # ── Tier 15 ─────────────────────────────────────────────────────────────
    {
        "id": 7,
        "tier": 15,
        "objective_type": "foundation_trial",
        "objective_value": 1,
        "reward_jade": 30,
        "reward_items": [{"type": "pill", "pill_id": 4, "qty": 1}],  # Breakthrough Pill
        "is_premium_only": True,
        "description_key": "bp_miss_foundation_trial",
    },
    {
        "id": 8,
        "tier": 15,
        "objective_type": "complete_quests",
        "objective_value": 10,
        "reward_jade": 25,
        "reward_items": [{"type": "ore", "ore_id": 3, "qty": 3}],  # Mystic Silver
        "is_premium_only": False,
        "description_key": "bp_miss_complete_quests",
    },
    {
        "id": 9,
        "tier": 15,
        "objective_type": "win_sparring",
        "objective_value": 5,
        "reward_jade": 25,
        "reward_items": [{"type": "herb", "herb_id": 5, "qty": 1}],  # Breakthrough Flower
        "is_premium_only": False,
        "description_key": "bp_miss_win_sparring",
    },
    # ── Tier 20 ─────────────────────────────────────────────────────────────
    {
        "id": 10,
        "tier": 20,
        "objective_type": "alchemy_tier",
        "objective_value": 2,
        "reward_jade": 50,
        "reward_items": [{"type": "herb", "herb_id": 7, "qty": 3}],  # Dragon Blood Grass
        "is_premium_only": False,
        "description_key": "bp_miss_alchemy_tier",
    },
    {
        "id": 11,
        "tier": 20,
        "objective_type": "win_npc_fight",
        "objective_value": 10,
        "reward_jade": 40,
        "reward_items": [{"type": "technique_scroll", "technique_id": 3, "qty": 1}],  # Iron Body
        "is_premium_only": False,
        "description_key": "bp_miss_win_npc_fight",
    },
    {
        "id": 12,
        "tier": 20,
        "objective_type": "forge_artifact",
        "objective_value": 3,
        "reward_jade": 40,
        "reward_items": [{"type": "ore", "ore_id": 4, "qty": 3}],  # Stellar Gold
        "is_premium_only": False,
        "description_key": "bp_miss_forge_artifact",
    },
    # ── Tier 25 ─────────────────────────────────────────────────────────────
    {
        "id": 13,
        "tier": 25,
        "objective_type": "win_tribulation",
        "objective_value": 1,
        "reward_jade": 100,
        "reward_items": [{"type": "technique_scroll", "technique_id": 5, "qty": 1}],  # Void Slash
        "is_premium_only": False,
        "description_key": "bp_miss_win_tribulation",
    },
    {
        "id": 14,
        "tier": 25,
        "objective_type": "complete_dungeon",
        "objective_value": 1,
        "reward_jade": 75,
        "reward_items": [{"type": "herb", "herb_id": 8, "qty": 2}],  # Void Root
        "is_premium_only": True,
        "description_key": "bp_miss_complete_dungeon",
    },
    # ── Tier 30 ─────────────────────────────────────────────────────────────
    {
        "id": 15,
        "tier": 30,
        "objective_type": "golden_core",
        "objective_value": 1,
        "reward_jade": 200,
        "reward_items": [{"type": "title", "value": "Core Forger"}],
        "is_premium_only": True,
        "description_key": "bp_miss_golden_core",
    },
    # ── Daily Missions (reset every day, 1 tier point each) ────────────────
    {
        "id": 16,
        "tier": 0,
        "objective_type": "craft_pills",
        "objective_value": 2,
        "reward_jade": 5,
        "reward_items": [{"type": "spirit_stones", "amount": 500}],
        "is_premium_only": False,
        "description_key": "bp_miss_daily_craft",
        "reset_type": "daily",
    },
    {
        "id": 17,
        "tier": 0,
        "objective_type": "win_npc_fight",
        "objective_value": 1,
        "reward_jade": 5,
        "reward_items": [],
        "is_premium_only": False,
        "description_key": "bp_miss_daily_npc",
        "reset_type": "daily",
    },
    {
        "id": 18,
        "tier": 0,
        "objective_type": "complete_quests",
        "objective_value": 1,
        "reward_jade": 5,
        "reward_items": [],
        "is_premium_only": False,
        "description_key": "bp_miss_daily_quest",
        "reset_type": "daily",
    },
    # ── Weekly Missions (reset every Monday, 1 tier point each) ────────────
    {
        "id": 19,
        "tier": 0,
        "objective_type": "craft_pills",
        "objective_value": 10,
        "reward_jade": 15,
        "reward_items": [{"type": "spirit_stones", "amount": 2000}],
        "is_premium_only": False,
        "description_key": "bp_miss_weekly_craft",
        "reset_type": "weekly",
    },
    {
        "id": 20,
        "tier": 0,
        "objective_type": "win_npc_fight",
        "objective_value": 5,
        "reward_jade": 15,
        "reward_items": [{"type": "herb", "herb_id": 1, "qty": 5}],
        "is_premium_only": False,
        "description_key": "bp_miss_weekly_npc",
        "reset_type": "weekly",
    },
    {
        "id": 21,
        "tier": 0,
        "objective_type": "win_sparring",
        "objective_value": 3,
        "reward_jade": 15,
        "reward_items": [{"type": "spirit_stones", "amount": 1500}],
        "is_premium_only": False,
        "description_key": "bp_miss_weekly_spar",
        "reset_type": "weekly",
    },
    {
        "id": 22,
        "tier": 0,
        "objective_type": "complete_quests",
        "objective_value": 5,
        "reward_jade": 15,
        "reward_items": [{"type": "herb", "herb_id": 3, "qty": 3}],
        "is_premium_only": False,
        "description_key": "bp_miss_weekly_quest",
        "reset_type": "weekly",
    },
]


async def run_battle_pass_seeds(session: AsyncSession):
    existing = (await session.execute(select(BattlePassMission))).scalars().all()
    existing_map = {m.id: m for m in existing}

    for data in BP_MISSIONS:
        if data["id"] not in existing_map:
            session.add(BattlePassMission(**data))
        else:
            # Sync any changes to existing missions
            m = existing_map[data["id"]]
            m.tier = data["tier"]
            m.objective_type = data["objective_type"]
            m.objective_value = data["objective_value"]
            m.reward_jade = data["reward_jade"]
            m.reward_items = data["reward_items"]
            m.is_premium_only = data["is_premium_only"]
            m.description_key = data["description_key"]
            m.reset_type = data.get("reset_type", "none")

    await session.commit()
    logger.info("🗺️ Battle pass missions seeded (%d total).", len(BP_MISSIONS))
