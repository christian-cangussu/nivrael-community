import logging
from sqlalchemy import select
from database.models import DungeonCatalog

logger = logging.getLogger(__name__)

DUNGEON_SEEDS = [
    # ─── Existing Dungeons ────────────────────────────────────────────────────
    {
        "id": 1,
        "continent": "linghe",  # MV-1
        "name": "Mortal Catacombs",
        "min_realm": 0,
        "max_realm": 10,
        "floor_count": 10,
        "qi_cost_per_floor": 5,
        "base_bp": 200,
        "floor_counts": {"easy": 5, "normal": 10, "hard": 12, "nightmare": 15},
        "drops": {
            "herbs": [
                {"id": 1, "weight": 8},   # Qi Root Herb — essential for crafting
                {"id": 2, "weight": 6},   # Spirit Grass — common crafting herb
                {"id": 12, "weight": 3},  # Spirit Vine — moderate
                {"id": 9, "weight": 2},   # Moonlight Moss — rare
                {"id": 3, "weight": 2},   # Foundation Lotus
            ],
            "ores": [
                {"id": 1, "weight": 4},
                {"id": 2, "weight": 2},
            ],
            "stones": {"min": 30, "max": 120},
            "qi_pill_chance": 0.08,
            "pills": [
                {"id": 27, "weight": 3},  # Minor Healing Pill
            ],
            "pill_chance": 0.10,
        },
        "description": "Ancient burial grounds beneath the mortal city. Weak undead cultivators roam these dim halls, hoarding scraps of spiritual energy.",
        "emoji": "💀",
    },
    {
        "id": 2,
        "continent": "qianhe",  # MV-1
        "name": "Haunted Mines",
        "min_realm": 2,
        "max_realm": 10,
        "floor_count": 15,
        "qi_cost_per_floor": 8,
        "base_bp": 1500,
        "floor_counts": {"easy": 8, "normal": 15, "hard": 18, "nightmare": 22},
        "drops": {
            "herbs": [
                {"id": 3, "weight": 4},
                {"id": 4, "weight": 3},
                {"id": 5, "weight": 2},
            ],
            "ores": [
                {"id": 2, "weight": 4},
                {"id": 3, "weight": 3},
                {"id": 4, "weight": 1},
            ],
            "stones": {"min": 80, "max": 300},
            "qi_pill_chance": 0.12,
            "pills": [
                {"id": 27, "weight": 3},  # Minor Healing Pill
                {"id": 28, "weight": 1},  # Healing Pill
            ],
            "pill_chance": 0.12,
        },
        "description": "Collapsed spirit ore mines haunted by the ghosts of fallen miners. Veins of second-tier ore glint through cracked stone walls.",
        "emoji": "⛏️",
    },
    {
        "id": 3,
        "continent": "yanshan",  # MV-1
        "name": "Nascent Void",
        "min_realm": 3,
        "max_realm": 10,
        "floor_count": 20,
        "qi_cost_per_floor": 12,
        "base_bp": 15000,
        "floor_counts": {"easy": 10, "normal": 20, "hard": 24, "nightmare": 30},
        "drops": {
            "herbs": [
                {"id": 5, "weight": 4},
                {"id": 6, "weight": 3},
                {"id": 7, "weight": 2},
            ],
            "ores": [
                {"id": 3, "weight": 3},
                {"id": 4, "weight": 3},
                {"id": 5, "weight": 1},
            ],
            "stones": {"min": 200, "max": 700},
            "qi_pill_chance": 0.15,
            "scroll_chance": 0.05,
            "pills": [
                {"id": 27, "weight": 2},  # Minor Healing Pill
                {"id": 28, "weight": 3},  # Healing Pill
                {"id": 29, "weight": 1},  # Greater Healing Pill
            ],
            "pill_chance": 0.12,
        },
        "description": "A rift between realms where nascent soul fragments drift. Spatial anomalies make each floor a new challenge for the senses.",
        "emoji": "🌀",
    },
    {
        "id": 4,
        "continent": "moyu",  # MV-1
        "name": "Abyssal Rift",
        "min_realm": 5,
        "max_realm": 10,
        "floor_count": 25,
        "qi_cost_per_floor": 18,
        "base_bp": 200000,
        "floor_counts": {"easy": 12, "normal": 25, "hard": 30, "nightmare": 38},
        "drops": {
            "herbs": [
                {"id": 7, "weight": 3},
                {"id": 8, "weight": 3},
                {"id": 10, "weight": 2},
            ],
            "ores": [
                {"id": 5, "weight": 3},
                {"id": 6, "weight": 3},
                {"id": 7, "weight": 2},
            ],
            "stones": {"min": 500, "max": 2000},
            "qi_pill_chance": 0.18,
            "scroll_chance": 0.08,
            "pills": [
                {"id": 28, "weight": 2},  # Healing Pill
                {"id": 29, "weight": 3},  # Greater Healing Pill
                {"id": 30, "weight": 1},  # Supreme Healing Pill
            ],
            "pill_chance": 0.15,
        },
        "description": "A tear in the fabric of space where ancient void beasts nest. Tier 4-5 herbs cling to the abyss walls, imbued with void essence.",
        "emoji": "🕳️",
    },
    {
        "id": 5,
        "continent": "linghe",  # MV-1
        "name": "Immortal Trial",
        "min_realm": 7,
        "max_realm": 10,
        "floor_count": 50,
        "qi_cost_per_floor": 25,
        "base_bp": 5000000,
        "floor_counts": {"easy": 25, "normal": 50, "hard": 60, "nightmare": 75},
        "drops": {
            "herbs": [
                {"id": 8, "weight": 3},
                {"id": 10, "weight": 3},
            ],
            "ores": [
                {"id": 7, "weight": 5},
            ],
            "stones": {"min": 2000, "max": 8000},
            "qi_pill_chance": 0.22,
            "scroll_chance": 0.12,
            "dao_fragment_chance": 0.05,
            "pills": [
                {"id": 29, "weight": 2},  # Greater Healing Pill
                {"id": 30, "weight": 3},  # Supreme Healing Pill
            ],
            "pill_chance": 0.18,
        },
        "description": "The supreme trial left by ancient immortals. Only those at the peak of the Dao can endure all 50 floors. Legendary Dao materials await.",
        "emoji": "⚡",
    },

    # ─── NEW — Tier 1 (Realm 0) ──────────────────────────────────────────────
    {
        "id": 6,
        "continent": "linghe",  # MV-1
        "name": "Misty Cave",
        "min_realm": 0,
        "max_realm": 10,
        "floor_count": 8,
        "qi_cost_per_floor": 3,
        "base_bp": 150,
        "floor_counts": {"easy": 4, "normal": 8, "hard": 10, "nightmare": 12},
        "drops": {
            "herbs": [
                {"id": 1, "weight": 7},   # Qi Root Herb
                {"id": 2, "weight": 5},   # Spirit Grass
                {"id": 12, "weight": 4},  # Spirit Vine
            ],
            "ores": [
                {"id": 1, "weight": 6},   # Mortal Iron
                {"id": 2, "weight": 2},   # Spirit Copper
            ],
            "stones": {"min": 20, "max": 80},
            "qi_pill_chance": 0.06,
            "pills": [
                {"id": 27, "weight": 3},  # Minor Healing Pill
            ],
            "pill_chance": 0.08,
        },
        "description": "A shallow cave hidden behind a waterfall of morning mist. The damp walls are rich with low-grade ore and wild herbs.",
        "emoji": "🌫️",
    },
    {
        "id": 7,
        "continent": "linghe",  # MV-1
        "name": "Forgotten Tomb",
        "min_realm": 0,
        "max_realm": 10,
        "floor_count": 10,
        "qi_cost_per_floor": 5,
        "base_bp": 250,
        "floor_counts": {"easy": 5, "normal": 10, "hard": 14, "nightmare": 18},
        "drops": {
            "herbs": [
                {"id": 1, "weight": 4},   # Qi Root Herb
                {"id": 9, "weight": 3},   # Moonlight Moss
            ],
            "ores": [
                {"id": 1, "weight": 3},   # Mortal Iron
            ],
            "stones": {"min": 50, "max": 200},
            "qi_pill_chance": 0.10,
            "scroll_chance": 0.04,
            "pills": [
                {"id": 27, "weight": 3},  # Minor Healing Pill
            ],
            "pill_chance": 0.10,
        },
        "description": "The sealed tomb of a forgotten elder. Ancient scrolls line the dusty shelves, and spirit stones litter the offering altar.",
        "emoji": "🪦",
    },
    {
        "id": 8,
        "continent": "yanshan",  # MV-1
        "name": "Bamboo Forest",
        "min_realm": 0,
        "max_realm": 10,
        "floor_count": 9,
        "qi_cost_per_floor": 4,
        "base_bp": 180,
        "floor_counts": {"easy": 4, "normal": 9, "hard": 11, "nightmare": 14},
        "drops": {
            "herbs": [
                {"id": 1, "weight": 6},   # Qi Root Herb
                {"id": 2, "weight": 5},   # Spirit Grass
                {"id": 12, "weight": 4},  # Spirit Vine
                {"id": 9, "weight": 3},   # Moonlight Moss
            ],
            "ores": [
                {"id": 1, "weight": 3},   # Mortal Iron
            ],
            "stones": {"min": 25, "max": 100},
            "qi_pill_chance": 0.08,
            "pills": [
                {"id": 27, "weight": 3},  # Minor Healing Pill
            ],
            "pill_chance": 0.08,
        },
        "description": "A dense bamboo grove where spirit beasts prowl among the stalks. Rich in natural herbs and beast cores left by fallen creatures.",
        "emoji": "🎋",
    },

    # ─── NEW — Tier 2 (Realm 1-2) ────────────────────────────────────────────
    {
        "id": 9,
        "continent": "qianhe",  # MV-1
        "name": "Spirit Mine",
        "min_realm": 1,
        "max_realm": 10,
        "floor_count": 12,
        "qi_cost_per_floor": 6,
        "base_bp": 1200,
        "floor_counts": {"easy": 6, "normal": 12, "hard": 15, "nightmare": 19},
        "drops": {
            "herbs": [
                {"id": 2, "weight": 3},   # Spirit Grass
                {"id": 3, "weight": 2},   # Foundation Lotus
            ],
            "ores": [
                {"id": 2, "weight": 5},   # Spirit Copper
                {"id": 3, "weight": 3},   # Mystic Silver
            ],
            "stones": {"min": 60, "max": 250},
            "qi_pill_chance": 0.10,
            "pills": [
                {"id": 27, "weight": 3},  # Minor Healing Pill
                {"id": 28, "weight": 1},  # Healing Pill
            ],
            "pill_chance": 0.10,
        },
        "description": "A crystalline mine where spirit energy has concentrated into veins of precious ore. Miners who ventured too deep never returned.",
        "emoji": "💎",
    },
    {
        "id": 10,
        "continent": "linghe",  # MV-1
        "name": "Haunted Library",
        "min_realm": 1,
        "max_realm": 10,
        "floor_count": 14,
        "qi_cost_per_floor": 7,
        "base_bp": 1500,
        "floor_counts": {"easy": 7, "normal": 14, "hard": 17, "nightmare": 21},
        "drops": {
            "herbs": [
                {"id": 3, "weight": 3},   # Foundation Lotus
                {"id": 6, "weight": 2},   # Azure Cloud Flower
            ],
            "ores": [
                {"id": 2, "weight": 3},   # Spirit Copper
            ],
            "stones": {"min": 70, "max": 280},
            "qi_pill_chance": 0.10,
            "scroll_chance": 0.08,
            "dao_fragment_chance": 0.02,
            "pills": [
                {"id": 27, "weight": 3},  # Minor Healing Pill
                {"id": 28, "weight": 1},  # Healing Pill
            ],
            "pill_chance": 0.10,
        },
        "description": "An ancient library where spectral scholars guard forbidden knowledge. Technique scrolls and fragments of Dao wisdom drift between the aisles.",
        "emoji": "📚",
    },
    {
        "id": 11,
        "continent": "qianhe",  # MV-1
        "name": "Underground River",
        "min_realm": 2,
        "max_realm": 10,
        "floor_count": 16,
        "qi_cost_per_floor": 9,
        "base_bp": 2000,
        "floor_counts": {"easy": 8, "normal": 16, "hard": 20, "nightmare": 25},
        "drops": {
            "herbs": [
                {"id": 3, "weight": 4},   # Foundation Lotus
                {"id": 6, "weight": 4},   # Azure Cloud Flower
                {"id": 11, "weight": 3},  # Frost Dew Herb
                {"id": 9, "weight": 2},   # Moonlight Moss
            ],
            "ores": [
                {"id": 2, "weight": 3},   # Spirit Copper
                {"id": 3, "weight": 2},   # Mystic Silver
            ],
            "stones": {"min": 90, "max": 350},
            "qi_pill_chance": 0.12,
            "pills": [
                {"id": 27, "weight": 2},  # Minor Healing Pill
                {"id": 28, "weight": 2},  # Healing Pill
            ],
            "pill_chance": 0.12,
        },
        "description": "A subterranean river flowing with spirit-infused water. Rare aquatic herbs grow along the banks, nourished by the spiritual current.",
        "emoji": "🌊",
    },

    # ─── NEW — Tier 3 (Realm 3-4) ────────────────────────────────────────────
    {
        "id": 12,
        "continent": "yanshan",  # MV-1
        "name": "Phoenix Nest",
        "min_realm": 3,
        "max_realm": 10,
        "floor_count": 16,
        "qi_cost_per_floor": 10,
        "base_bp": 12000,
        "floor_counts": {"easy": 8, "normal": 16, "hard": 20, "nightmare": 25},
        "drops": {
            "herbs": [
                {"id": 5, "weight": 3},   # Breakthrough Flower
                {"id": 10, "weight": 4},  # Phoenix Tear Petal
                {"id": 7, "weight": 2},   # Dragon Blood Grass
            ],
            "ores": [
                {"id": 8, "weight": 5},   # Phoenix Ash
                {"id": 3, "weight": 3},   # Mystic Silver
                {"id": 4, "weight": 2},   # Stellar Gold
            ],
            "stones": {"min": 150, "max": 600},
            "qi_pill_chance": 0.14,
            "scroll_chance": 0.05,
            "pills": [
                {"id": 27, "weight": 1},  # Minor Healing Pill
                {"id": 28, "weight": 3},  # Healing Pill
                {"id": 29, "weight": 1},  # Greater Healing Pill
            ],
            "pill_chance": 0.12,
        },
        "description": "The smoldering nest of an ancient phoenix high atop a volcanic peak. Phoenix Ash and fire-touched herbs grow amid the eternal flames.",
        "emoji": "🔥",
    },
    {
        "id": 13,
        "continent": "fenghuo",  # MV-1
        "name": "Dragon's Lair",
        "min_realm": 3,
        "max_realm": 10,
        "floor_count": 20,
        "qi_cost_per_floor": 14,
        "base_bp": 18000,
        "floor_counts": {"easy": 10, "normal": 20, "hard": 25, "nightmare": 32},
        "drops": {
            "herbs": [
                {"id": 7, "weight": 4},   # Dragon Blood Grass
                {"id": 5, "weight": 3},   # Breakthrough Flower
                {"id": 4, "weight": 2},   # Soul Herb
            ],
            "ores": [
                {"id": 9, "weight": 5},   # Dragon Scale
                {"id": 4, "weight": 3},   # Stellar Gold
                {"id": 3, "weight": 2},   # Mystic Silver
            ],
            "stones": {"min": 200, "max": 750},
            "qi_pill_chance": 0.15,
            "scroll_chance": 0.06,
            "pills": [
                {"id": 28, "weight": 3},  # Healing Pill
                {"id": 29, "weight": 1},  # Greater Healing Pill
            ],
            "pill_chance": 0.12,
        },
        "description": "The lair of an ancient dragon, deep within a mountain of hoarded treasures. Dragon Scales and precious ores line the cavern floor.",
        "emoji": "🐲",
    },
    {
        "id": 14,
        "continent": "linghe",  # MV-1
        "name": "Sect Ruins",
        "min_realm": 4,
        "max_realm": 10,
        "floor_count": 22,
        "qi_cost_per_floor": 16,
        "base_bp": 25000,
        "floor_counts": {"easy": 12, "normal": 22, "hard": 28, "nightmare": 35},
        "drops": {
            "herbs": [
                {"id": 4, "weight": 3},   # Soul Herb
                {"id": 5, "weight": 3},   # Breakthrough Flower
                {"id": 6, "weight": 2},   # Azure Cloud Flower
            ],
            "ores": [
                {"id": 4, "weight": 3},   # Stellar Gold
                {"id": 5, "weight": 2},   # Celestial Jade
            ],
            "stones": {"min": 250, "max": 900},
            "qi_pill_chance": 0.16,
            "scroll_chance": 0.10,
            "pills": [
                {"id": 28, "weight": 2},  # Healing Pill
                {"id": 29, "weight": 2},  # Greater Healing Pill
            ],
            "pill_chance": 0.14,
        },
        "description": "The ruins of a once-mighty cultivation sect, destroyed in an ancient war. Technique scrolls and forgotten artifacts lie buried in the rubble.",
        "emoji": "🏚️",
    },

    # ─── NEW — Tier 4 (Realm 5-6) ────────────────────────────────────────────
    {
        "id": 15,
        "continent": "moyu",  # MV-1
        "name": "Void Rift",
        "min_realm": 5,
        "max_realm": 10,
        "floor_count": 20,
        "qi_cost_per_floor": 15,
        "base_bp": 150000,
        "floor_counts": {"easy": 10, "normal": 20, "hard": 26, "nightmare": 33},
        "drops": {
            "herbs": [
                {"id": 8, "weight": 4},   # Void Root
                {"id": 7, "weight": 3},   # Dragon Blood Grass
            ],
            "ores": [
                {"id": 6, "weight": 5},   # Void Crystal
                {"id": 5, "weight": 3},   # Celestial Jade
            ],
            "stones": {"min": 400, "max": 1500},
            "qi_pill_chance": 0.16,
            "scroll_chance": 0.06,
            "pills": [
                {"id": 28, "weight": 2},  # Healing Pill
                {"id": 29, "weight": 3},  # Greater Healing Pill
            ],
            "pill_chance": 0.14,
        },
        "description": "A crackling rift in the void between dimensions. Void Crystals grow like stalagmites, pulsing with chaotic spatial energy.",
        "emoji": "🌑",
    },
    {
        "id": 16,
        "continent": "fenghuo",  # MV-1
        "name": "Demon Palace",
        "min_realm": 5,
        "max_realm": 10,
        "floor_count": 28,
        "qi_cost_per_floor": 20,
        "base_bp": 200000,
        "floor_counts": {"easy": 14, "normal": 28, "hard": 34, "nightmare": 42},
        "drops": {
            "herbs": [
                {"id": 7, "weight": 3},   # Dragon Blood Grass
                {"id": 8, "weight": 3},   # Void Root
                {"id": 10, "weight": 2},  # Phoenix Tear Petal
            ],
            "ores": [
                {"id": 5, "weight": 3},   # Celestial Jade
                {"id": 6, "weight": 3},   # Void Crystal
                {"id": 7, "weight": 1},   # Dao Essence Stone
            ],
            "stones": {"min": 600, "max": 2200},
            "qi_pill_chance": 0.18,
            "scroll_chance": 0.07,
            "pills": [
                {"id": 29, "weight": 3},  # Greater Healing Pill
                {"id": 30, "weight": 1},  # Supreme Healing Pill
            ],
            "pill_chance": 0.15,
        },
        "description": "A palace of dark obsidian where demonic cultivators once held court. The halls reek of corruption, but hold materials of immense power.",
        "emoji": "👹",
    },
    {
        "id": 17,
        "continent": "fenghuo",  # MV-1
        "name": "Celestial Tower",
        "min_realm": 6,
        "max_realm": 10,
        "floor_count": 30,
        "qi_cost_per_floor": 22,
        "base_bp": 350000,
        "floor_counts": {"easy": 16, "normal": 30, "hard": 38, "nightmare": 48},
        "drops": {
            "herbs": [
                {"id": 8, "weight": 3},   # Void Root
                {"id": 10, "weight": 3},  # Phoenix Tear Petal
            ],
            "ores": [
                {"id": 10, "weight": 5},  # Celestial Iron
                {"id": 5, "weight": 3},   # Celestial Jade
                {"id": 6, "weight": 2},   # Void Crystal
            ],
            "stones": {"min": 800, "max": 3000},
            "qi_pill_chance": 0.20,
            "scroll_chance": 0.08,
            "pills": [
                {"id": 29, "weight": 2},  # Greater Healing Pill
                {"id": 30, "weight": 2},  # Supreme Healing Pill
            ],
            "pill_chance": 0.16,
        },
        "description": "A tower that pierces the heavens, built from Celestial Iron by ancient gods. Each floor tests a different aspect of cultivation mastery.",
        "emoji": "🗼",
    },

    # ─── NEW — Tier 5 (Realm 7-8) ────────────────────────────────────────────
    {
        "id": 18,
        "continent": "qianhe",  # MV-1
        "name": "Primordial Abyss",
        "min_realm": 7,
        "max_realm": 10,
        "floor_count": 40,
        "qi_cost_per_floor": 22,
        "base_bp": 2000000,
        "floor_counts": {"easy": 20, "normal": 40, "hard": 50, "nightmare": 65},
        "drops": {
            "herbs": [
                {"id": 8, "weight": 3},   # Void Root
                {"id": 10, "weight": 3},  # Phoenix Tear Petal
            ],
            "ores": [
                {"id": 7, "weight": 4},   # Dao Essence Stone
                {"id": 6, "weight": 3},   # Void Crystal
                {"id": 11, "weight": 1},  # Heavenly Jade (F-11.5 — rare drop, celestial gear material)
            ],
            "stones": {"min": 1500, "max": 6000},
            "qi_pill_chance": 0.20,
            "scroll_chance": 0.10,
            "dao_fragment_chance": 0.06,
            "pills": [
                {"id": 29, "weight": 2},  # Greater Healing Pill
                {"id": 30, "weight": 3},  # Supreme Healing Pill
            ],
            "pill_chance": 0.18,
        },
        "description": "The primordial abyss where creation itself began. Essence from the dawn of the universe seeps through cracks in reality.",
        "emoji": "🕳️",
    },
    {
        "id": 19,
        "continent": "fenghuo",  # MV-1
        "name": "Tribulation Ground",
        "min_realm": 8,
        "max_realm": 10,
        "floor_count": 45,
        "qi_cost_per_floor": 24,
        "base_bp": 4000000,
        "floor_counts": {"easy": 22, "normal": 45, "hard": 55, "nightmare": 70},
        "drops": {
            "herbs": [
                {"id": 8, "weight": 4},   # Void Root
                {"id": 10, "weight": 4},  # Phoenix Tear Petal
                {"id": 7, "weight": 2},   # Dragon Blood Grass
            ],
            "ores": [
                {"id": 7, "weight": 4},   # Dao Essence Stone
                {"id": 10, "weight": 3},  # Celestial Iron
                {"id": 9, "weight": 2},   # Dragon Scale
                {"id": 11, "weight": 2},  # Heavenly Jade (F-11.5 — slightly better rate here since realm 8+)
            ],
            "stones": {"min": 2000, "max": 7500},
            "qi_pill_chance": 0.22,
            "scroll_chance": 0.10,
            "dao_fragment_chance": 0.05,
            "pills": [
                {"id": 29, "weight": 1},  # Greater Healing Pill
                {"id": 30, "weight": 3},  # Supreme Healing Pill
            ],
            "pill_chance": 0.18,
        },
        "description": "A scarred wasteland where heavenly tribulations strike endlessly. Materials tempered by tribulation lightning hold extraordinary power.",
        "emoji": "⛈️",
    },
    {
        "id": 20,
        "continent": "qianhe",  # MV-1
        "name": "Immortal's Tomb",
        "min_realm": 8,
        "max_realm": 10,
        "floor_count": 50,
        "qi_cost_per_floor": 28,
        "base_bp": 6000000,
        "floor_counts": {"easy": 25, "normal": 50, "hard": 62, "nightmare": 78},
        "drops": {
            "herbs": [
                {"id": 10, "weight": 4},  # Phoenix Tear Petal
                {"id": 8, "weight": 3},   # Void Root
            ],
            "ores": [
                {"id": 7, "weight": 5},   # Dao Essence Stone
                {"id": 10, "weight": 3},  # Celestial Iron
                {"id": 11, "weight": 2},  # Heavenly Jade (F-11.5)
            ],
            "stones": {"min": 2500, "max": 9000},
            "qi_pill_chance": 0.24,
            "scroll_chance": 0.14,
            "dao_fragment_chance": 0.07,
            "pills": [
                {"id": 30, "weight": 4},  # Supreme Healing Pill
            ],
            "pill_chance": 0.20,
        },
        "description": "The hidden tomb of a true immortal, sealed with formations that could destroy worlds. Priceless artifacts and Dao fragments lie within.",
        "emoji": "👑",
    },

    # ─── NEW — Tier 6 (Realm 9-10) ───────────────────────────────────────────
    # v14.4 D-1c: Mahayana dungeons (21/22/23) drop the new T5 herb 13
    # "Eternal Spring Petal" ONLY on Nightmare difficulty (gated by
    # `min_difficulty` filter in handlers/dungeons._roll_floor_loot).
    # Spec: ingredient for the Eternal Foundation Pill, lore says it
    # blooms only where an Immortal's essence was cremated.
    {
        "id": 21,
        "continent": "moyu",  # MV-1
        "name": "Chaos Realm",
        "min_realm": 9,
        "max_realm": 10,
        "floor_count": 55,
        "qi_cost_per_floor": 30,
        "base_bp": 20000000,
        "floor_counts": {"easy": 30, "normal": 55, "hard": 68, "nightmare": 85},
        "drops": {
            "herbs": [
                {"id": 10, "weight": 4},  # Phoenix Tear Petal
                {"id": 8, "weight": 3},   # Void Root
                {"id": 13, "weight": 1, "min_difficulty": "nightmare"},  # Eternal Spring Petal (D-1c)
            ],
            "ores": [
                {"id": 7, "weight": 5},   # Dao Essence Stone
            ],
            "stones": {"min": 5000, "max": 15000},
            "qi_pill_chance": 0.25,
            "scroll_chance": 0.12,
            "dao_fragment_chance": 0.08,
            "pills": [
                {"id": 30, "weight": 4},  # Supreme Healing Pill
            ],
            "pill_chance": 0.20,
        },
        "description": "A realm of pure chaos where the laws of nature break down. Chaos Essence permeates every surface, warping reality itself.",
        "emoji": "🌪️",
    },
    {
        "id": 22,
        "continent": "fenghuo",  # MV-1
        "name": "Ancient Battlefield",
        "min_realm": 9,
        "max_realm": 10,
        "floor_count": 60,
        "qi_cost_per_floor": 35,
        "base_bp": 30000000,
        "floor_counts": {"easy": 32, "normal": 60, "hard": 75, "nightmare": 95},
        "drops": {
            "herbs": [
                {"id": 10, "weight": 4},  # Phoenix Tear Petal
                {"id": 8, "weight": 3},   # Void Root
                {"id": 13, "weight": 1, "min_difficulty": "nightmare"},  # Eternal Spring Petal (D-1c)
            ],
            "ores": [
                {"id": 7, "weight": 5},   # Dao Essence Stone
                {"id": 10, "weight": 3},  # Celestial Iron
                {"id": 11, "weight": 3},  # Heavenly Jade (F-11.5 — best non-boss rate)
            ],
            "stones": {"min": 6000, "max": 20000},
            "qi_pill_chance": 0.25,
            "scroll_chance": 0.14,
            "dao_fragment_chance": 0.08,
            "pills": [
                {"id": 30, "weight": 4},  # Supreme Healing Pill
            ],
            "pill_chance": 0.22,
        },
        "description": "An ancient battlefield where immortal cultivators once clashed. Their weapons and techniques still echo across the blood-soaked earth.",
        "emoji": "⚔️",
    },
    {
        "id": 23,
        "continent": "linghe",  # MV-1
        "name": "Dao Origin",
        "min_realm": 10,
        "max_realm": 10,
        "floor_count": 65,
        "qi_cost_per_floor": 40,
        "base_bp": 50000000,
        "floor_counts": {"easy": 35, "normal": 65, "hard": 80, "nightmare": 100},
        "drops": {
            "herbs": [
                {"id": 10, "weight": 5},  # Phoenix Tear Petal
                {"id": 8, "weight": 3},   # Void Root
                {"id": 13, "weight": 2, "min_difficulty": "nightmare"},  # Eternal Spring Petal (D-1c) — best rate, max realm
            ],
            "ores": [
                {"id": 7, "weight": 6},   # Dao Essence Stone
            ],
            "stones": {"min": 8000, "max": 30000},
            "qi_pill_chance": 0.28,
            "scroll_chance": 0.15,
            "dao_fragment_chance": 0.12,
            "pills": [
                {"id": 30, "weight": 4},  # Supreme Healing Pill
            ],
            "pill_chance": 0.22,
        },
        "description": "The origin point of all Dao in existence. Only those who have reached the pinnacle of cultivation can survive the overwhelming pressure of raw Dao Law.",
        "emoji": "☯️",
    },
]


async def run_dungeon_seeds(session):
    existing_ids = set((await session.execute(select(DungeonCatalog.id))).scalars().all())

    added = 0
    updated = 0
    for seed in DUNGEON_SEEDS:
        if seed["id"] in existing_ids:
            # Update base_bp and floor_counts for existing dungeons
            dungeon = (await session.execute(
                select(DungeonCatalog).where(DungeonCatalog.id == seed["id"])
            )).scalar_one_or_none()
            if dungeon:
                changed = False
                if dungeon.base_bp != seed.get("base_bp", 200):
                    dungeon.base_bp = seed.get("base_bp", 200)
                    changed = True
                if dungeon.floor_counts != seed.get("floor_counts"):
                    dungeon.floor_counts = seed.get("floor_counts")
                    changed = True
                if dungeon.drops != seed.get("drops"):
                    dungeon.drops = seed.get("drops")
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(dungeon, "drops")
                    changed = True
                # MV-1: ancoragem por continente sincroniza também em registos
                # existentes (regra de seed sync — não só inserts).
                if dungeon.continent != seed.get("continent"):
                    dungeon.continent = seed.get("continent")
                    changed = True
                if changed:
                    updated += 1
            continue
        session.add(DungeonCatalog(
            id=seed["id"],
            name=seed["name"],
            min_realm=seed["min_realm"],
            max_realm=seed["max_realm"],
            floor_count=seed["floor_count"],
            qi_cost_per_floor=seed["qi_cost_per_floor"],
            drops=seed["drops"],
            description=seed["description"],
            emoji=seed["emoji"],
            base_bp=seed.get("base_bp", 200),
            floor_counts=seed.get("floor_counts"),
            continent=seed.get("continent"),
        ))
        added += 1

    if added:
        logger.info("🗺️ Seeded %d dungeons", added)
    if updated:
        logger.info("🗺️ Updated %d dungeons with base_bp/floor_counts", updated)

    await session.commit()
