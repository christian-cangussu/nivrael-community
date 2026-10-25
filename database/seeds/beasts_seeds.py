import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import BeastCatalog, ExpeditionCatalog

logger = logging.getLogger(__name__)

BEASTS = [
    {
        "id": 1,
        "name": "Thunder Ox",
        "rank": "Common",
        "element": "Lightning",
        "emoji": "⚡",
        "base_stats": {"cb_mult": 1.02},
        "special_ability": "Minor Thunder — +2% passive CB as companion",
        "catch_rate": 0.80,
        "description": "A massive ox whose fur crackles with static electricity. A faithful companion to novice cultivators.",
    },
    {
        "id": 2,
        "name": "Jade Turtle",
        "rank": "Uncommon",
        "element": "Earth",
        "emoji": "🌍",
        "base_stats": {"hp_mult": 1.10},
        "special_ability": "Jade Shell — +10% HP in combat",
        "catch_rate": 0.65,
        "description": "A centuries-old turtle whose shell has crystallized into pure jade. Protects its master with unwavering resilience.",
    },
    {
        "id": 3,
        "name": "Bamboo Panda",
        "rank": "Uncommon",
        "element": "Wood",
        "emoji": "🌿",
        "base_stats": {"qi_recovery_mult": 1.08},
        "special_ability": "Bamboo Breath — +8% Qi recovery",
        "catch_rate": 0.60,
        "description": "A spiritual panda that meditates among celestial bamboo groves. Its purring restores the Qi of those around it.",
    },
    {
        "id": 4,
        "name": "Fire Fox",
        "rank": "Rare",
        "element": "Fire",
        "emoji": "🔥",
        "base_stats": {"cb_mult": 1.05},
        "special_ability": "Fox Flame — +5% CB and launches fireball in combat",
        "catch_rate": 0.45,
        "description": "A young nine-tailed fox whose flames burn with the passion of the Dao. Each tail promises more power.",
    },
    {
        "id": 5,
        "name": "Shadow Wolf",
        "rank": "Rare",
        "element": "Shadow",
        "emoji": "🌑",
        "base_stats": {"evasion_mult": 1.05},
        "special_ability": "Shadow Step — +5% evasion and sneak attack in combat",
        "catch_rate": 0.40,
        "description": "A wolf born from the shadows between worlds. Invisible until the moment of attack.",
    },
    {
        "id": 6,
        "name": "Storm Eagle",
        "rank": "Epic",
        "element": "Lightning",
        "emoji": "⚡",
        "base_stats": {"bp_mult": 1.08},
        "special_ability": "Storm Claw — +8% BP and lightning in combat",
        "catch_rate": 0.25,
        "description": "A colossal eagle that rides stormy winds. Its claws cut like celestial lightning.",
    },
    {
        "id": 7,
        "name": "Frost Bear",
        "rank": "Epic",
        "element": "Ice",
        "emoji": "❄️",
        "base_stats": {"soul_mult": 1.12},
        "special_ability": "Glacial Roar — +12% Soul Strength and freezes enemy for 1 round",
        "catch_rate": 0.20,
        "description": "An ancient bear from the frozen mountains. Its roar freezes the souls of the bravest.",
    },
    {
        "id": 8,
        "name": "Golden Carp",
        "rank": "Legendary",
        "element": "Gold",
        "emoji": "💛",
        "base_stats": {"luck_mult": 1.15},
        "special_ability": "Dragon's Leap — +15% Luck and double drop chance",
        "catch_rate": 0.10,
        "description": "A golden carp swimming against the celestial current. It is said to transform into a dragon when it leaps the Dao gate.",
    },
    {
        "id": 9,
        "name": "Phoenix Chick",
        "rank": "Mythic",
        "element": "Fire",
        "emoji": "🔥",
        "base_stats": {"cb_mult": 1.25},
        "special_ability": "Rebirth — +25% CB and revives 1x per tribulation",
        "catch_rate": 0.05,
        "description": "A phoenix hatchling still burning with the primordial fire of creation. Dies and is reborn eternally.",
    },
    {
        "id": 10,
        "name": "Chaos Dragon",
        "rank": "Divine",
        "element": "Chaos",
        "emoji": "☯️",
        "base_stats": {"cb_mult": 1.30, "bp_mult": 1.30, "soul_mult": 1.30, "luck_mult": 1.30, "hp_mult": 1.30},
        "special_ability": "Chaos Breath — +30% all stats and total devastation in combat",
        "catch_rate": 0.01,
        "description": "A primordial dragon born of Chaos before the separation of Yin and Yang. Its power transcends mortal understanding.",
    },
    {
        "id": 11,
        "name": "River Serpent",
        "rank": "Common",
        "element": "Water",
        "emoji": "🌊",
        "base_stats": {"soul_mult": 1.03},
        "special_ability": "River Flow — +3% Soul Strength as companion",
        "catch_rate": 0.75,
        "description": "A serpent that dwells in spiritual rivers.",
    },
    {
        "id": 12,
        "name": "Wind Hawk",
        "rank": "Uncommon",
        "element": "Wind",
        "emoji": "🌪️",
        "base_stats": {"bp_mult": 1.06},
        "special_ability": "Gale Dive — +6% Battle Power in combat",
        "catch_rate": 0.55,
        "description": "A hawk that rides the spiritual winds.",
    },
    {
        "id": 13,
        "name": "Crystal Spider",
        "rank": "Rare",
        "element": "Earth",
        "emoji": "🕷️",
        "base_stats": {"luck_mult": 1.08},
        "special_ability": "Crystal Web — +8% Luck and traps enemy for 1 round",
        "catch_rate": 0.35,
        "description": "A spider whose web is made of crystal Qi threads.",
    },
    {
        "id": 14,
        "name": "Infernal Salamander",
        "rank": "Epic",
        "element": "Fire",
        "emoji": "🔥",
        "base_stats": {"bp_mult": 1.10, "cb_mult": 1.05},
        "special_ability": "Infernal Blaze — +10% BP and +5% CB in combat",
        "catch_rate": 0.18,
        "description": "A salamander born from volcanic vents.",
    },
    {
        "id": 15,
        "name": "Celestial Crane",
        "rank": "Legendary",
        "element": "Wind",
        "emoji": "🕊️",
        "base_stats": {"perception_mult": 1.20, "cb_mult": 1.10},
        "special_ability": "Heaven's Gaze — +20% Perception and +10% CB",
        "catch_rate": 0.08,
        "description": "A crane that carries the wisdom of the heavens.",
    },
]

EXPEDITIONS = [
    {
        "id": 1,
        "name": "Herb Expedition",
        "duration_hours": 2,
        "req_beast_rank": "Common",
        "drops": {
            "guaranteed": [
                {"type": "herb", "item_id": 1, "qty_min": 1, "qty_max": 3},   # Qi Root — nerfed (was 3-6)
                {"type": "herb", "item_id": 2, "qty_min": 1, "qty_max": 2},   # Spirit Grass — nerfed (was 2-4)
                {"type": "herb", "item_id": 12, "qty_min": 0, "qty_max": 1},  # Spirit Vine — nerfed (was 1-2)
            ],
            "bonus": [
                {"type": "spirit_stones", "amount_min": 30, "amount_max": 100, "chance": 0.4}
            ],
            "beast_egg_chance": 0.02,  # was 0.05 — low tier = low egg
        },
        "description": "Send your beast to gather herbs in the spiritual meadows. Requires Common+ beast.",
        "emoji": "🌿",
    },
    {
        "id": 2,
        "name": "Spirit Mountain",
        "duration_hours": 4,
        "req_beast_rank": "Rare",
        "drops": {
            "guaranteed": [
                {"type": "herb", "item_id": 2, "qty_min": 1, "qty_max": 3},   # Spirit Grass — nerfed (was 2-4)
                {"type": "herb", "item_id": 3, "qty_min": 1, "qty_max": 2},   # Foundation Lotus — unchanged
            ],
            "bonus": [
                {"type": "ore", "ore_id": 1, "qty_min": 1, "qty_max": 2, "chance": 0.5},  # nerfed (was 1-3, 0.6)
                {"type": "spirit_stones", "amount_min": 80, "amount_max": 250, "chance": 0.45},  # adjusted
            ],
            "beast_egg_chance": 0.05,  # was 0.08
        },
        "description": "The Spiritual Mountain hides treasures among its peaks. Requires Rare+ beast.",
        "emoji": "🏔️",
    },
    {
        "id": 3,
        "name": "Ancient Ruins",
        "duration_hours": 8,
        "req_beast_rank": "Epic",
        "drops": {
            "guaranteed": [
                {"type": "herb", "item_id": 3, "qty_min": 1, "qty_max": 3},   # Foundation Lotus — nerfed (was 2-4)
                {"type": "herb", "item_id": 4, "qty_min": 1, "qty_max": 2},   # Soul Herb — unchanged
            ],
            "bonus": [
                {"type": "beast_core", "qty_min": 1, "qty_max": 2, "chance": 0.35},  # was 0.4
                {"type": "ore", "ore_id": 2, "qty_min": 1, "qty_max": 2, "chance": 0.3},
                {"type": "spirit_stones", "amount_min": 200, "amount_max": 500, "chance": 0.5},  # was 200-600
            ],
            "beast_egg_chance": 0.07,  # was 0.10
        },
        "description": "Ruins of a forgotten civilization. Artifacts and beast cores await the brave. Requires Epic+ beast.",
        "emoji": "🏛️",
    },
    {
        "id": 4,
        "name": "Celestial Expedition",
        "duration_hours": 24,
        "req_beast_rank": "Legendary",
        "drops": {
            "guaranteed": [
                {"type": "herb", "item_id": 4, "qty_min": 2, "qty_max": 4},   # Soul Herb — nerfed (was 2-5)
                {"type": "herb", "item_id": 5, "qty_min": 1, "qty_max": 2},   # Breakthrough Flower — nerfed (was 1-3)
            ],
            "bonus": [
                {"type": "beast_core", "qty_min": 2, "qty_max": 3, "chance": 0.5},  # was 2-4, 0.6
                {"type": "ore", "ore_id": 3, "qty_min": 1, "qty_max": 3, "chance": 0.4},
                {"type": "spirit_stones", "amount_min": 500, "amount_max": 1500, "chance": 0.65},  # was 500-2000, 0.7
            ],
            "beast_egg_chance": 0.10,  # was 0.15
            # 2026-07-10 "ativar as pills de tier 4" — topo das expedições
            # (Legendary, 24h) passa a poder dropar receitas T4 (default é 3).
            "recipe_max_tier": 4,
        },
        "description": "Expedition to the celestial domains. Only legendary beasts survive the pressure of pure Qi. Requires Legendary+ beast.",
        "emoji": "🌌",
    },
    {
        "id": 5,
        "name": "Demon Wastes",
        "duration_hours": 6,
        "req_beast_rank": "Rare",
        "drops": {
            "guaranteed": [
                {"type": "herb", "item_id": 7, "qty_min": 1, "qty_max": 2},   # Dragon Blood Grass — unchanged
                {"type": "ore", "ore_id": 2, "qty_min": 1, "qty_max": 2},     # Spirit Copper — unchanged
            ],
            "bonus": [
                {"type": "beast_core", "qty_min": 1, "qty_max": 1, "chance": 0.25},  # was 0.3
                {"type": "spirit_stones", "amount_min": 120, "amount_max": 350, "chance": 0.45},  # was 150-400, 0.5
            ],
            "beast_egg_chance": 0.04,  # was 0.07
        },
        "description": "A wasteland tainted by demonic energy. Rich in rare materials but dangerous. Requires Rare+ beast.",
        "emoji": "💀",
    },
    {
        "id": 6,
        "name": "Immortal Sanctum",
        "duration_hours": 12,
        "req_beast_rank": "Epic",
        "drops": {
            "guaranteed": [
                {"type": "herb", "item_id": 8, "qty_min": 1, "qty_max": 2},   # Void Root — unchanged
                {"type": "herb", "item_id": 10, "qty_min": 0, "qty_max": 1},  # Phoenix Tear — unchanged
                {"type": "ore", "ore_id": 4, "qty_min": 1, "qty_max": 2},     # Stellar Gold — unchanged
            ],
            "bonus": [
                {"type": "beast_core", "qty_min": 1, "qty_max": 2, "chance": 0.4},  # was 2-3, 0.5
                {"type": "spirit_stones", "amount_min": 250, "amount_max": 800, "chance": 0.55},  # was 300-1000, 0.6
            ],
            "beast_egg_chance": 0.08,  # was 0.12
            # 2026-07-10 — idem Celestial: Epic 12h também abre a porta T4.
            "recipe_max_tier": 4,
        },
        "description": "A hidden sanctum left by an ancient Immortal. The rewards match the danger. Requires Epic+ beast.",
        "emoji": "🌟",
    },
]


async def run_beasts_seeds(session: AsyncSession):
    existing_beast_ids = set((await session.execute(select(BeastCatalog.id))).scalars().all())
    added_beasts = 0
    for b in BEASTS:
        if b["id"] not in existing_beast_ids:
            session.add(BeastCatalog(**b))
            added_beasts += 1
    if added_beasts:
        logger.info("🐉 Seeded %d new beasts (skipped %d existing)", added_beasts, len(BEASTS) - added_beasts)

    existing_exp_ids = set((await session.execute(select(ExpeditionCatalog.id))).scalars().all())
    added_exps = 0
    updated_exps = 0
    for e in EXPEDITIONS:
        if e["id"] not in existing_exp_ids:
            session.add(ExpeditionCatalog(**e))
            added_exps += 1
        else:
            # Update existing expedition drops (for balance patches)
            stmt = select(ExpeditionCatalog).where(ExpeditionCatalog.id == e["id"])
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if existing and existing.drops != e["drops"]:
                existing.drops = e["drops"]
                updated_exps += 1
    if added_exps:
        logger.info("🗺️ Seeded %d new expeditions (skipped %d existing)", added_exps, len(EXPEDITIONS) - added_exps)
    if updated_exps:
        logger.info("🗺️ Updated drops for %d expeditions", updated_exps)

    await session.commit()
