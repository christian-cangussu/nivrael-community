import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import GachaBanner

logger = logging.getLogger(__name__)

GACHA_BANNERS = [
    {
        "id": "ancient_chest_01",
        "name": "Ancient Celestial Chest",
        "description": "An ancient chest sealed with celestial runes. Contains treasures from a forgotten era.",
        "pity_at": 90,
        "is_active": True,
        "items": {
            "legendary": {
                "weight": 1,
                "items": [
                    {"type": "artifact", "catalog_id": 10, "name": "Divine Cosmic Blade", "qty": 1},
                    {"type": "technique_scroll", "technique_id": 12, "name": "Soul Devourer", "qty": 1},
                    {"type": "beast_trap", "rarity": "mythic", "name": "Mythic Beast Trap", "qty": 1},
                ],
            },
            "epic": {
                "weight": 9,
                "items": [
                    {"type": "artifact", "catalog_id": 8, "name": "Heaven's Edge", "qty": 1},
                    {"type": "artifact", "catalog_id": 15, "name": "Heaven Guardian Mail", "qty": 1},
                    {"type": "pill", "pill_id": 10, "name": "Time Dilation Pill", "qty": 2},
                    {"type": "technique_scroll", "technique_id": 9, "name": "Divine Finger", "qty": 1},
                    {"type": "pill", "pill_id": 2, "name": "Foundation Pill", "qty": 1},
                ],
            },
            "rare": {
                "weight": 30,
                "items": [
                    {"type": "pill", "pill_id": 8, "name": "Battle Fury Pill", "qty": 3},
                    {"type": "herb", "herb_id": 7, "name": "Dragon Blood Grass", "qty": 5},
                    {"type": "ore", "ore_id": 4, "name": "Stellar Gold", "qty": 3},
                    {"type": "beast_trap", "rarity": "rare", "name": "Rare Beast Trap", "qty": 1},
                    {"type": "core_essence", "amount": 10, "name": "Core Essence ×10"},
                    {"type": "alchemy_xp", "amount": 500, "name": "Alchemy Scroll (+500 XP)"},
                    {"type": "forge_xp", "amount": 300, "name": "Forge Scroll (+300 XP)"},
                ],
            },
            "common": {
                "weight": 60,
                "items": [
                    {"type": "spirit_stones", "amount": 1000, "name": "Spirit Stones x1000", "qty": 1},
                    {"type": "herb", "herb_id": 1, "name": "Qi Root Herb", "qty": 10},
                    {"type": "pill", "pill_id": 6, "name": "Qi Amass Pill", "qty": 5},
                    {"type": "ore", "ore_id": 1, "name": "Mortal Iron", "qty": 5},
                ],
            },
        },
    },
    {
        "id": "monthly_special_01",
        "name": "Phoenix Rising Banner",
        "description": "A banner infused with the power of the Phoenix. Limited time only.",
        "pity_at": 60,
        "is_active": False,
        "items": {
            "legendary": {
                "weight": 2,
                "items": [
                    {"type": "pill", "pill_id": 13, "name": "Phoenix Rebirth Pill", "qty": 1},
                    {"type": "beast_egg", "beast_id": 9, "name": "Phoenix Chick Egg", "qty": 1},
                    {"type": "artifact", "catalog_id": 17, "name": "Divine Phoenix Cloak", "qty": 1},
                ],
            },
            "epic": {
                "weight": 8,
                "items": [
                    {"type": "herb", "herb_id": 10, "name": "Phoenix Tear Petal", "qty": 3},
                    {"type": "technique_scroll", "technique_id": 10, "name": "Phoenix Strike", "qty": 1},
                    {"type": "artifact", "catalog_id": 9, "name": "Spirit Severing Sword", "qty": 1},
                    {"type": "pill", "pill_id": 10, "name": "Time Dilation Pill", "qty": 1},
                ],
            },
            "rare": {
                "weight": 30,
                "items": [
                    {"type": "herb", "herb_id": 5, "name": "Breakthrough Flower", "qty": 3},
                    {"type": "pill", "pill_id": 8, "name": "Battle Fury Pill", "qty": 3},
                    {"type": "ore", "ore_id": 3, "name": "Mystic Silver", "qty": 5},
                    {"type": "beast_trap", "rarity": "epic", "name": "Epic Beast Trap", "qty": 1},
                ],
            },
            "common": {
                "weight": 60,
                "items": [
                    {"type": "spirit_stones", "amount": 800, "name": "Spirit Stones x800", "qty": 1},
                    {"type": "herb", "herb_id": 2, "name": "Spirit Grass", "qty": 10},
                    {"type": "pill", "pill_id": 1, "name": "Qi Gathering Pill", "qty": 5},
                    {"type": "ore", "ore_id": 1, "name": "Mortal Iron", "qty": 8},
                ],
            },
        },
    },
]


async def run_gacha_seeds(session: AsyncSession):
    existing = (await session.execute(select(GachaBanner))).scalars().all()
    existing_map = {b.id: b for b in existing}
    
    for banner_data in GACHA_BANNERS:
        if banner_data["id"] not in existing_map:
            session.add(GachaBanner(**banner_data))
        else:
            b = existing_map[banner_data["id"]]
            b.items = banner_data["items"]
            b.name = banner_data["name"]
            b.description = banner_data["description"]
            b.pity_at = banner_data["pity_at"]

    logger.info("🎰 Checked and updated gacha seeds.")
    await session.commit()
