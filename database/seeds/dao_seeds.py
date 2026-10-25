import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DaoLawCatalog

logger = logging.getLogger(__name__)

DAO_LAWS = [
    {
        "id": 1,
        "name": "Dao of Speed",
        "emoji": "⚡",
        "element": "Lightning",
        "total_fragments": 9,
        "effect_type": "cb_mult",
        "effect_per_fragment": 0.05,
        "min_realm": 5,
        "description": "Dao of Speed (速度道則) — Permanently increases cultivation speed by +5% per fragment.",
    },
    {
        "id": 2,
        "name": "Dao of Destruction",
        "emoji": "🐉",
        "element": "Fire",
        "total_fragments": 9,
        "effect_type": "bp_mult",
        "effect_per_fragment": 0.05,
        "min_realm": 5,
        "description": "Dao of Destruction (毀滅道則) — Permanently increases Battle Power by +5% per fragment.",
    },
    {
        "id": 3,
        "name": "Dao of Life",
        "emoji": "🌸",
        "element": "Wood",
        "total_fragments": 9,
        "effect_type": "hp_regen",
        "effect_per_fragment": 0.03,
        "min_realm": 5,
        "description": "Dao of Life (生命道則) — Regenerates 3% HP per round in combat per fragment.",
    },
    {
        "id": 4,
        "name": "Dao of Time",
        "emoji": "☯️",
        "element": "Chaos",
        "total_fragments": 12,
        "effect_type": "cooldown_reduction",
        "effect_per_fragment": 0.03,
        "min_realm": 6,
        "description": "Dao of Time (時間道則) — Reduces all cooldowns by -3% per fragment. (Rare)",
    },
    {
        "id": 5,
        "name": "Dao of Creation",
        "emoji": "💎",
        "element": "Earth",
        "total_fragments": 12,
        "effect_type": "pill_quality",
        "effect_per_fragment": 0.04,
        "min_realm": 6,
        "description": "Dao of Creation (創造道則) — Improves pill crafting quality by +4% per fragment. (Rare)",
    },
    {
        "id": 6,
        "name": "Eternal Dao",
        "emoji": "💜",
        "element": "Chaos",
        "total_fragments": 108,
        "effect_type": "all_stats",
        "effect_per_fragment": 0.02,
        "min_realm": 8,
        "description": "Eternal Dao (永恆大道) — The Supreme Dao. Increases all stats by +2% per fragment. (Endgame)",
    },
]


async def run_dao_seeds(session: AsyncSession):
    existing_ids = set((await session.execute(select(DaoLawCatalog.id))).scalars().all())
    added = 0
    for d in DAO_LAWS:
        if d["id"] not in existing_ids:
            session.add(DaoLawCatalog(**d))
            added += 1
    if added:
        await session.commit()
        logger.info("☯️ Seeded %d new dao laws (skipped %d existing)", added, len(DAO_LAWS) - added)
    else:
        logger.info("☯️ All %d dao laws already exist, skipping", len(DAO_LAWS))
