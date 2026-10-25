import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── World Boss Pool — Tier-based ───────────────────────────────────────────
#
# Each boss belongs to a tier: mortal (realm 0-4), spirit (realm 5-7), immortal (realm 8-10).
# HP is calculated dynamically from sum(top10_bp) * tier_factor at spawn time.
# Loot tables scale with tier difficulty.
#
# Reward tiers per rank:
#   rank_1      -> 1st place
#   rank_2      -> 2nd place
#   rank_3      -> 3rd place
#   rank_4_10   -> 4th-10th
#   participant -> 11th+

WORLD_BOSS_POOL = [
    # ── MORTAL TIER (realm 0-4) ───────────────────────────────────────────
    {
        "name": "Demonic Emperor",
        "emoji": "💀",
        "tier": "mortal",
        "loot_table": {
            "rank_1": [
                {"type": "spirit_stones", "amount": 40_000},
                {"type": "technique_scroll", "item_id": 5, "amount": 1},
                {"type": "herb", "item_id": 3, "amount": 4},
                {"type": "beast_core", "amount": 2},
            ],
            "rank_2": [
                {"type": "spirit_stones", "amount": 30_000},
                {"type": "herb", "item_id": 3, "amount": 3},
                {"type": "ore", "item_id": 2, "amount": 2},
            ],
            "rank_3": [
                {"type": "spirit_stones", "amount": 25_000},
                {"type": "herb", "item_id": 2, "amount": 3},
            ],
            "rank_4_10": [
                {"type": "spirit_stones", "amount": 15_000},
                {"type": "herb", "item_id": 1, "amount": 2},
            ],
            "participant": [
                {"type": "spirit_stones", "amount": 5_000},
            ],
        },
    },
    {
        "name": "Void Beast",
        "emoji": "☯️",
        "tier": "mortal",
        "loot_table": {
            "rank_1": [
                {"type": "spirit_stones", "amount": 45_000},
                {"type": "technique_scroll", "item_id": 4, "amount": 1},
                {"type": "herb", "item_id": 4, "amount": 3},
                {"type": "ore", "item_id": 2, "amount": 3},
            ],
            "rank_2": [
                {"type": "spirit_stones", "amount": 35_000},
                {"type": "herb", "item_id": 3, "amount": 3},
            ],
            "rank_3": [
                {"type": "spirit_stones", "amount": 28_000},
                {"type": "herb", "item_id": 2, "amount": 3},
                {"type": "ore", "item_id": 1, "amount": 2},
            ],
            "rank_4_10": [
                {"type": "spirit_stones", "amount": 16_000},
            ],
            "participant": [
                {"type": "spirit_stones", "amount": 6_000},
            ],
        },
    },
    {
        "name": "Shadow Wolf Alpha",
        "emoji": "🐺",
        "tier": "mortal",
        "loot_table": {
            "rank_1": [
                {"type": "spirit_stones", "amount": 38_000},
                {"type": "herb", "item_id": 4, "amount": 4},
                {"type": "beast_core", "amount": 2},
            ],
            "rank_2": [
                {"type": "spirit_stones", "amount": 28_000},
                {"type": "herb", "item_id": 3, "amount": 3},
                {"type": "beast_core", "amount": 1},
            ],
            "rank_3": [
                {"type": "spirit_stones", "amount": 22_000},
                {"type": "herb", "item_id": 2, "amount": 2},
            ],
            "rank_4_10": [
                {"type": "spirit_stones", "amount": 14_000},
            ],
            "participant": [
                {"type": "spirit_stones", "amount": 5_000},
            ],
        },
    },

    # ── SPIRIT TIER (realm 5-7) ───────────────────────────────────────────
    {
        "name": "Ancient Dragon",
        "emoji": "🐉",
        "tier": "spirit",
        "loot_table": {
            "rank_1": [
                {"type": "spirit_stones", "amount": 160_000},
                {"type": "technique_scroll", "item_id": 8, "amount": 2},
                # N-34 (v14.3 hotfix 2026-05-14): tech 13 (Absolute Defense,
                # dao=3 req_realm=5) had no drop source anywhere in seeds —
                # locked behind a Dao gate but unobtainable. Same for techs
                # 14, 15, 16, 17, 18 (wired across the 6 spirit/immortal
                # bosses). [jogador] reported the visible symptom on
                # Boundless Evasion (id=18) at 17:40.
                {"type": "technique_scroll", "item_id": 13, "amount": 1},
                {"type": "ore", "item_id": 5, "amount": 6},
                {"type": "beast_core", "amount": 5},
            ],
            "rank_2": [
                {"type": "spirit_stones", "amount": 120_000},
                {"type": "technique_scroll", "item_id": 7, "amount": 1},
                {"type": "ore", "item_id": 4, "amount": 4},
            ],
            "rank_3": [
                {"type": "spirit_stones", "amount": 100_000},
                {"type": "ore", "item_id": 4, "amount": 3},
                {"type": "herb", "item_id": 5, "amount": 3},
            ],
            "rank_4_10": [
                {"type": "spirit_stones", "amount": 60_000},
                {"type": "herb", "item_id": 4, "amount": 2},
            ],
            "participant": [
                {"type": "spirit_stones", "amount": 20_000},
            ],
        },
    },
    {
        "name": "Celestial Demon",
        "emoji": "⚡",
        "tier": "spirit",
        "loot_table": {
            "rank_1": [
                {"type": "spirit_stones", "amount": 180_000},
                {"type": "technique_scroll", "item_id": 6, "amount": 2},
                {"type": "technique_scroll", "item_id": 14, "amount": 1},  # N-34: Storm Fist (dao=1 req_realm=5)
                {"type": "herb", "item_id": 5, "amount": 5},
                {"type": "beast_core", "amount": 4},
            ],
            "rank_2": [
                {"type": "spirit_stones", "amount": 135_000},
                {"type": "technique_scroll", "item_id": 6, "amount": 1},
                {"type": "herb", "item_id": 5, "amount": 3},
            ],
            "rank_3": [
                {"type": "spirit_stones", "amount": 110_000},
                {"type": "herb", "item_id": 5, "amount": 2},
                {"type": "ore", "item_id": 4, "amount": 3},
            ],
            "rank_4_10": [
                {"type": "spirit_stones", "amount": 65_000},
                {"type": "ore", "item_id": 3, "amount": 2},
            ],
            "participant": [
                {"type": "spirit_stones", "amount": 22_000},
            ],
        },
    },
    {
        "name": "Void Wraith",
        "emoji": "👻",
        "tier": "spirit",
        "loot_table": {
            "rank_1": [
                {"type": "spirit_stones", "amount": 150_000},
                {"type": "technique_scroll", "item_id": 7, "amount": 2},
                {"type": "technique_scroll", "item_id": 15, "amount": 1},  # N-34: Heaven Rend (dao=4 req_realm=6)
                {"type": "herb", "item_id": 5, "amount": 4},
                {"type": "ore", "item_id": 5, "amount": 4},
            ],
            "rank_2": [
                {"type": "spirit_stones", "amount": 115_000},
                {"type": "herb", "item_id": 5, "amount": 3},
                {"type": "ore", "item_id": 4, "amount": 3},
            ],
            "rank_3": [
                {"type": "spirit_stones", "amount": 95_000},
                {"type": "herb", "item_id": 4, "amount": 3},
                {"type": "ore", "item_id": 3, "amount": 2},
            ],
            "rank_4_10": [
                {"type": "spirit_stones", "amount": 55_000},
                {"type": "herb", "item_id": 3, "amount": 2},
            ],
            "participant": [
                {"type": "spirit_stones", "amount": 18_000},
            ],
        },
    },

    # ── IMMORTAL TIER (realm 8-10) ────────────────────────────────────────
    # v14.4 D-1c: Heaven-Falling Star Dew (herb 14) is wired here on top-3
    # ranks of every immortal-tier boss. Lore: it falls when a great
    # cultivator dies — only world-boss kills witness its descent.
    # Rate scales with rank (rank_1 best). Required ingredient for the
    # Eternal Foundation Pill alongside Eternal Spring Petal (herb 13).
    {
        "name": "Corrupted Immortal",
        "emoji": "👹",
        "tier": "immortal",
        "loot_table": {
            "rank_1": [
                {"type": "spirit_stones", "amount": 400_000},
                {"type": "technique_scroll", "item_id": 3, "amount": 2},
                {"type": "technique_scroll", "item_id": 16, "amount": 1},  # N-34: Undying Fortress (dao=3 req_realm=7)
                {"type": "beast_core", "amount": 8},
                {"type": "herb", "item_id": 5, "amount": 6},
                {"type": "herb", "item_id": 14, "amount": 1},  # D-1c: Heaven-Falling Star Dew
                {"type": "ore", "item_id": 5, "amount": 6},
                {"type": "ore", "item_id": 11, "amount": 2},  # Heavenly Jade (F-11.5 — rank 1 reward)
            ],
            "rank_2": [
                {"type": "spirit_stones", "amount": 300_000},
                {"type": "technique_scroll", "item_id": 3, "amount": 1},
                {"type": "beast_core", "amount": 5},
                {"type": "herb", "item_id": 5, "amount": 4},
                {"type": "herb", "item_id": 14, "amount": 1},  # D-1c: Heaven-Falling Star Dew
                {"type": "ore", "item_id": 11, "amount": 1},  # Heavenly Jade (F-11.5 — rank 2)
            ],
            "rank_3": [
                {"type": "spirit_stones", "amount": 250_000},
                {"type": "beast_core", "amount": 4},
                {"type": "herb", "item_id": 14, "amount": 1},  # D-1c: Heaven-Falling Star Dew
                {"type": "ore", "item_id": 5, "amount": 4},
            ],
            "rank_4_10": [
                {"type": "spirit_stones", "amount": 150_000},
                {"type": "beast_core", "amount": 2},
                {"type": "herb", "item_id": 5, "amount": 2},
            ],
            "participant": [
                {"type": "spirit_stones", "amount": 50_000},
            ],
        },
    },
    {
        "name": "Primordial Chaos Beast",
        "emoji": "🌀",
        "tier": "immortal",
        "loot_table": {
            "rank_1": [
                {"type": "spirit_stones", "amount": 450_000},
                {"type": "technique_scroll", "item_id": 2, "amount": 2},
                {"type": "technique_scroll", "item_id": 17, "amount": 1},  # N-34: Eternal Strike (dao=6 req_realm=8)
                {"type": "beast_core", "amount": 10},
                {"type": "herb", "item_id": 14, "amount": 2},  # D-1c: Heaven-Falling Star Dew (best rate)
                {"type": "ore", "item_id": 5, "amount": 8},
                {"type": "ore", "item_id": 11, "amount": 3},  # Heavenly Jade (F-11.5)
            ],
            "rank_2": [
                {"type": "spirit_stones", "amount": 340_000},
                {"type": "technique_scroll", "item_id": 2, "amount": 1},
                {"type": "beast_core", "amount": 6},
                {"type": "herb", "item_id": 14, "amount": 1},  # D-1c: Heaven-Falling Star Dew
                {"type": "ore", "item_id": 5, "amount": 5},
                {"type": "ore", "item_id": 11, "amount": 1},  # Heavenly Jade (F-11.5)
            ],
            "rank_3": [
                {"type": "spirit_stones", "amount": 280_000},
                {"type": "beast_core", "amount": 4},
                {"type": "herb", "item_id": 5, "amount": 4},
                {"type": "herb", "item_id": 14, "amount": 1},  # D-1c: Heaven-Falling Star Dew
            ],
            "rank_4_10": [
                {"type": "spirit_stones", "amount": 170_000},
                {"type": "beast_core", "amount": 3},
            ],
            "participant": [
                {"type": "spirit_stones", "amount": 55_000},
            ],
        },
    },
    {
        "name": "Heaven-Devouring Serpent",
        "emoji": "🐍",
        "tier": "immortal",
        "loot_table": {
            "rank_1": [
                {"type": "spirit_stones", "amount": 420_000},
                {"type": "technique_scroll", "item_id": 1, "amount": 2},
                {"type": "technique_scroll", "item_id": 18, "amount": 1},  # N-34: Boundless Evasion (dao=6 req_realm=8) — [jogador]'s exact case
                {"type": "beast_core", "amount": 9},
                {"type": "herb", "item_id": 5, "amount": 7},
                {"type": "herb", "item_id": 14, "amount": 1},  # D-1c: Heaven-Falling Star Dew
                {"type": "ore", "item_id": 11, "amount": 2},  # Heavenly Jade (F-11.5)
            ],
            "rank_2": [
                {"type": "spirit_stones", "amount": 320_000},
                {"type": "technique_scroll", "item_id": 1, "amount": 1},
                {"type": "beast_core", "amount": 6},
                {"type": "herb", "item_id": 14, "amount": 1},  # D-1c: Heaven-Falling Star Dew
                {"type": "ore", "item_id": 11, "amount": 1},  # Heavenly Jade (F-11.5)
            ],
            "rank_3": [
                {"type": "spirit_stones", "amount": 260_000},
                {"type": "beast_core", "amount": 4},
                {"type": "herb", "item_id": 14, "amount": 1},  # D-1c: Heaven-Falling Star Dew
                {"type": "ore", "item_id": 5, "amount": 3},
            ],
            "rank_4_10": [
                {"type": "spirit_stones", "amount": 160_000},
                {"type": "beast_core", "amount": 2},
                {"type": "ore", "item_id": 4, "amount": 2},
            ],
            "participant": [
                {"type": "spirit_stones", "amount": 52_000},
            ],
        },
    },
]


async def run_boss_seeds(session: AsyncSession):
    # World bosses are spawned dynamically by the scheduler from WORLD_BOSS_POOL.
    # No rows are inserted — only the WORLD_BOSS_POOL constant is used at runtime.
    mortal = sum(1 for b in WORLD_BOSS_POOL if b["tier"] == "mortal")
    spirit = sum(1 for b in WORLD_BOSS_POOL if b["tier"] == "spirit")
    immortal = sum(1 for b in WORLD_BOSS_POOL if b["tier"] == "immortal")
    logger.info(
        "👹 Boss pool loaded (%d total: %d mortal, %d spirit, %d immortal)",
        len(WORLD_BOSS_POOL), mortal, spirit, immortal,
    )
