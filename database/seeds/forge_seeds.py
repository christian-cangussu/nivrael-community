import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import ForgeRecipe

logger = logging.getLogger(__name__)

# Ores reference (from artifacts_seeds.py):
# 1: Mortal Iron (T1)    2: Spirit Copper (T2)    3: Mystic Silver (T3)
# 4: Stellar Gold (T4)   5: Celestial Jade (T5)   6: Void Crystal (T6)
# 7: Dao Essence Stone (T7)  8: Phoenix Ash (T3)  9: Dragon Scale (T4)
# 10: Celestial Iron (T5)

FORGE_RECIPES = [
    # ── TIER 1 — Basic (Grade 0-1, Realm 0, 80% success) ──
    {
        "id": 1, "artifact_id": 1, "tier": 1,  # Black Iron Sword (G0, weapon)
        "materials": [{"ore_id": 1, "qty": 4}],
        "required_realm": 0, "base_success_rate": 80.0, "bp_bonus": 500,
    },
    {
        "id": 2, "artifact_id": 2, "tier": 1,  # Spiritual Linen Tunic (G0, armor)
        "materials": [{"ore_id": 1, "qty": 3}],
        "required_realm": 0, "base_success_rate": 80.0, "bp_bonus": 400,
    },
    {
        "id": 3, "artifact_id": 3, "tier": 1,  # Ancient Copper Ring (G0, accessory)
        "materials": [{"ore_id": 1, "qty": 2}],
        "required_realm": 0, "base_success_rate": 80.0, "bp_bonus": 300,
    },
    {
        "id": 4, "artifact_id": 5, "tier": 1,  # Spirit Wind Blade (G1, weapon)
        "materials": [{"ore_id": 1, "qty": 5}],
        "required_realm": 0, "base_success_rate": 80.0, "bp_bonus": 800,
    },
    {
        "id": 5, "artifact_id": 12, "tier": 1,  # Iron Scale Vest (G1, armor)
        "materials": [{"ore_id": 1, "qty": 4}],
        "required_realm": 0, "base_success_rate": 80.0, "bp_bonus": 600,
    },
    {
        "id": 6, "artifact_id": 19, "tier": 1,  # Jade Pendant (G1, accessory)
        "materials": [{"ore_id": 1, "qty": 3}],
        "required_realm": 0, "base_success_rate": 80.0, "bp_bonus": 500,
    },

    # ── TIER 2 — Intermediate (Grade 2, Realm 2, 65% success) ──
    {
        "id": 7, "artifact_id": 4, "tier": 2,  # Flaming Sword (G2, weapon)
        "materials": [{"ore_id": 1, "qty": 6}, {"ore_id": 2, "qty": 2}],
        "required_realm": 2, "base_success_rate": 65.0, "bp_bonus": 2000,
    },
    {
        "id": 8, "artifact_id": 6, "tier": 2,  # Mystic Tiger Fang (G2, weapon)
        "materials": [{"ore_id": 1, "qty": 5}, {"ore_id": 2, "qty": 3}],
        "required_realm": 2, "base_success_rate": 65.0, "bp_bonus": 2200,
    },
    {
        "id": 9, "artifact_id": 13, "tier": 2,  # Azure Dragon Robe (G2, armor)
        "materials": [{"ore_id": 2, "qty": 4}, {"ore_id": 1, "qty": 2}],
        "required_realm": 2, "base_success_rate": 65.0, "bp_bonus": 1800,
    },
    {
        "id": 10, "artifact_id": 20, "tier": 2,  # Spirit Bead Bracelet (G2, accessory)
        "materials": [{"ore_id": 2, "qty": 3}, {"ore_id": 1, "qty": 2}],
        "required_realm": 2, "base_success_rate": 65.0, "bp_bonus": 1500,
    },

    # ── TIER 3 — Advanced (Grade 3, Realm 4, 50% success) ──
    {
        "id": 11, "artifact_id": 7, "tier": 3,  # Earth Cleaver (G3, weapon)
        "materials": [{"ore_id": 3, "qty": 4}, {"ore_id": 8, "qty": 3}],
        "required_realm": 4, "base_success_rate": 50.0, "bp_bonus": 8000,
    },
    {
        "id": 12, "artifact_id": 14, "tier": 3,  # Earth Core Plate (G3, armor)
        "materials": [{"ore_id": 3, "qty": 5}, {"ore_id": 8, "qty": 2}],
        "required_realm": 4, "base_success_rate": 50.0, "bp_bonus": 7000,
    },
    {
        "id": 13, "artifact_id": 21, "tier": 3,  # Earth Heart Amulet (G3, accessory)
        "materials": [{"ore_id": 3, "qty": 3}, {"ore_id": 8, "qty": 3}],
        "required_realm": 4, "base_success_rate": 50.0, "bp_bonus": 6000,
    },

    # ── TIER 4 — Expert (Grade 4-5, Realm 6, 40% success) ──
    {
        "id": 14, "artifact_id": 8, "tier": 4,  # Heaven's Edge (G4, weapon)
        "materials": [{"ore_id": 4, "qty": 5}, {"ore_id": 9, "qty": 2}],
        "required_realm": 6, "base_success_rate": 40.0, "bp_bonus": 15000,
    },
    {
        "id": 15, "artifact_id": 15, "tier": 4,  # Heaven Guardian Mail (G4, armor)
        "materials": [{"ore_id": 4, "qty": 4}, {"ore_id": 9, "qty": 3}],
        "required_realm": 6, "base_success_rate": 40.0, "bp_bonus": 13000,
    },
    {
        "id": 16, "artifact_id": 22, "tier": 4,  # Void Eye Pendant (G4, accessory)
        "materials": [{"ore_id": 4, "qty": 3}, {"ore_id": 9, "qty": 3}],
        "required_realm": 6, "base_success_rate": 40.0, "bp_bonus": 12000,
    },
    {
        "id": 17, "artifact_id": 9, "tier": 4,  # Spirit Severing Sword (G5, weapon)
        "materials": [{"ore_id": 5, "qty": 4}, {"ore_id": 9, "qty": 3}],
        "required_realm": 6, "base_success_rate": 40.0, "bp_bonus": 30000,
    },
    {
        "id": 18, "artifact_id": 16, "tier": 4,  # Spirit Emperor Robe (G5, armor)
        "materials": [{"ore_id": 5, "qty": 5}, {"ore_id": 10, "qty": 2}],
        "required_realm": 6, "base_success_rate": 40.0, "bp_bonus": 25000,
    },
    {
        "id": 19, "artifact_id": 23, "tier": 4,  # Spirit Dragon Ring (G5, accessory)
        "materials": [{"ore_id": 5, "qty": 3}, {"ore_id": 10, "qty": 2}],
        "required_realm": 6, "base_success_rate": 40.0, "bp_bonus": 22000,
    },

    # ── TIER 5 — Legendary (Grade 6-7, Realm 8, 30% success) ──
    {
        "id": 20, "artifact_id": 10, "tier": 5,  # Divine Cosmic Blade (G6, weapon)
        "materials": [{"ore_id": 10, "qty": 3}, {"ore_id": 6, "qty": 2}, {"ore_id": 7, "qty": 1}],
        "required_realm": 8, "base_success_rate": 30.0, "bp_bonus": 60000,
    },
    {
        "id": 21, "artifact_id": 17, "tier": 5,  # Divine Phoenix Cloak (G6, armor)
        "materials": [{"ore_id": 10, "qty": 4}, {"ore_id": 6, "qty": 2}],
        "required_realm": 8, "base_success_rate": 30.0, "bp_bonus": 55000,
    },
    {
        "id": 22, "artifact_id": 24, "tier": 5,  # Divine Star Earring (G6, accessory)
        "materials": [{"ore_id": 10, "qty": 3}, {"ore_id": 6, "qty": 2}],
        "required_realm": 8, "base_success_rate": 30.0, "bp_bonus": 50000,
    },
    {
        "id": 23, "artifact_id": 11, "tier": 5,  # Dao Annihilation Lance (G7, weapon)
        "materials": [{"ore_id": 6, "qty": 3}, {"ore_id": 7, "qty": 2}, {"ore_id": 10, "qty": 2}],
        "required_realm": 8, "base_success_rate": 30.0, "bp_bonus": 100000,
    },
    {
        "id": 24, "artifact_id": 18, "tier": 5,  # Dao Immortal Vestment (G7, armor)
        "materials": [{"ore_id": 6, "qty": 4}, {"ore_id": 7, "qty": 2}],
        "required_realm": 8, "base_success_rate": 30.0, "bp_bonus": 90000,
    },
    {
        "id": 25, "artifact_id": 25, "tier": 5,  # Dao Crown Fragment (G7, accessory)
        "materials": [{"ore_id": 7, "qty": 3}, {"ore_id": 6, "qty": 3}, {"ore_id": 10, "qty": 1}],
        "required_realm": 8, "base_success_rate": 30.0, "bp_bonus": 100000,
    },

    # ── TIER 6 — Celestial (Grade 8, Realm 8, 20% success) — F-11 ──
    # Requires Celestial Iron (10) + Heavenly Jade (11) + Dao Essence Stone (7).
    {
        "id": 26, "artifact_id": 46, "tier": 6,  # Celestial Sundering Blade (G8, weapon)
        "materials": [{"ore_id": 10, "qty": 5}, {"ore_id": 11, "qty": 3}, {"ore_id": 7, "qty": 2}],
        "required_realm": 8, "base_success_rate": 20.0, "bp_bonus": 180000,
    },
    {
        "id": 27, "artifact_id": 47, "tier": 6,  # Celestial Empyrean Vestment (G8, armor)
        "materials": [{"ore_id": 11, "qty": 5}, {"ore_id": 10, "qty": 3}, {"ore_id": 7, "qty": 2}],
        "required_realm": 8, "base_success_rate": 20.0, "bp_bonus": 160000,
    },
    {
        "id": 28, "artifact_id": 48, "tier": 6,  # Celestial Dao Ring (G8, accessory)
        "materials": [{"ore_id": 11, "qty": 4}, {"ore_id": 7, "qty": 3}, {"ore_id": 10, "qty": 2}],
        "required_realm": 8, "base_success_rate": 20.0, "bp_bonus": 150000,
    },

    # ── TIER 6 (F-11.5 addition) — Celestial set expansion (G8) ──
    # Uses the same tier-6 materials as the first triad. Slightly different
    # ratios so the recipes feel distinct.
    {
        "id": 29, "artifact_id": 49, "tier": 6,  # Celestial Ascension Spear (G8, weapon)
        "materials": [{"ore_id": 11, "qty": 4}, {"ore_id": 10, "qty": 4}, {"ore_id": 7, "qty": 2}],
        "required_realm": 8, "base_success_rate": 20.0, "bp_bonus": 180000,
    },
    {
        "id": 30, "artifact_id": 50, "tier": 6,  # Celestial Aegis Plate (G8, armor)
        "materials": [{"ore_id": 11, "qty": 6}, {"ore_id": 10, "qty": 2}, {"ore_id": 7, "qty": 2}],
        "required_realm": 8, "base_success_rate": 20.0, "bp_bonus": 160000,
    },
    {
        "id": 31, "artifact_id": 51, "tier": 6,  # Celestial Karma Pendant (G8, accessory)
        "materials": [{"ore_id": 11, "qty": 5}, {"ore_id": 7, "qty": 4}, {"ore_id": 10, "qty": 1}],
        "required_realm": 8, "base_success_rate": 20.0, "bp_bonus": 150000,
    },
]


async def run_forge_seeds(session: AsyncSession):
    existing_ids = set((await session.execute(select(ForgeRecipe.id))).scalars().all())
    added = 0
    for recipe_data in FORGE_RECIPES:
        if recipe_data["id"] not in existing_ids:
            session.add(ForgeRecipe(**recipe_data))
            added += 1
    if added:
        logger.info("🔨 Seeded %d new forge recipes (skipped %d existing)", added, len(FORGE_RECIPES) - added)
    await session.commit()
