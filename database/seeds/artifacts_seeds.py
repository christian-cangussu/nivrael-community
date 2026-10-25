import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import ArtifactCatalog, OreCatalog

logger = logging.getLogger(__name__)

ARTIFACTS = [
    # ── WEAPONS (slot: weapon) ──
    {
        "id": 1,
        "name": "Black Iron Sword",
        "type": "weapon",
        "grade": 0,
        "emoji": "⚔️",
        "base_stats": {"battle_power": 50},
        "description": "A common sword forged in black iron.",
    },
    {
        "id": 4,
        "name": "Flaming Sword",
        "type": "weapon",
        "grade": 2,
        "emoji": "🔥",
        "base_stats": {"battle_power": 250},
        "description": "A sword that glows with the power of fire.",
    },
    {
        "id": 5,
        "name": "Spirit Wind Blade",
        "type": "weapon",
        "grade": 1,
        "emoji": "🗡️",
        "base_stats": {"battle_power": 120},
        "description": "A blade forged with the essence of spiritual wind.",
    },
    {
        "id": 6,
        "name": "Mystic Tiger Fang",
        "type": "weapon",
        "grade": 2,
        "emoji": "⚔️",
        "base_stats": {"battle_power": 280, "luck": 8},
        "description": "A curved fang-blade that carries the ferocity of a mystic tiger.",
    },
    {
        "id": 7,
        "name": "Earth Cleaver",
        "type": "weapon",
        "grade": 3,
        "emoji": "🪓",
        "base_stats": {"battle_power": 500, "soul_strength": 50},
        "description": "A massive axe that can split the earth with a single swing.",
    },
    {
        "id": 8,
        "name": "Heaven's Edge",
        "type": "weapon",
        "grade": 4,
        "emoji": "⚡",
        "base_stats": {"battle_power": 900, "perception": 30},
        "description": "A sword touched by heavenly lightning. Cuts through all defenses.",
    },
    {
        "id": 9,
        "name": "Spirit Severing Sword",
        "type": "weapon",
        "grade": 5,
        "emoji": "🌟",
        "base_stats": {"battle_power": 1600, "soul_strength": 200},
        "description": "A sword that can sever the soul from the body. Feared by all cultivators.",
    },
    {
        "id": 10,
        "name": "Divine Cosmic Blade",
        "type": "weapon",
        "grade": 6,
        "emoji": "💎",
        "base_stats": {"battle_power": 3000, "luck": 50, "soul_strength": 300},
        "description": "A blade forged from cosmic dust. Resonates with the universe itself.",
    },
    {
        "id": 11,
        "name": "Dao Annihilation Lance",
        "type": "weapon",
        "grade": 7,
        "emoji": "💜",
        "base_stats": {"battle_power": 6000, "soul_strength": 600, "perception": 100},
        "description": "A lance that embodies the destructive aspect of the Dao. The ultimate weapon.",
    },
    # ── ARMOR (slot: armor) ──
    {
        "id": 2,
        "name": "Spiritual Linen Tunic",
        "type": "armor",
        "grade": 0,
        "emoji": "🥋",
        "base_stats": {"soul_strength": 30},
        "description": "A light tunic that protects the spirit.",
    },
    {
        "id": 12,
        "name": "Iron Scale Vest",
        "type": "armor",
        "grade": 1,
        "emoji": "🥋",
        "base_stats": {"soul_strength": 80},
        "description": "A vest made of overlapping iron scales. Sturdy and reliable.",
    },
    {
        "id": 13,
        "name": "Azure Dragon Robe",
        "type": "armor",
        "grade": 2,
        "emoji": "🐉",
        "base_stats": {"soul_strength": 200, "battle_power": 40},
        "description": "A robe woven with Azure Dragon silk. Radiates protective Qi.",
    },
    {
        "id": 14,
        "name": "Earth Core Plate",
        "type": "armor",
        "grade": 3,
        "emoji": "🪨",
        "base_stats": {"soul_strength": 400, "battle_power": 100},
        "description": "Armor forged from the core of the earth. Nearly indestructible.",
    },
    {
        "id": 15,
        "name": "Heaven Guardian Mail",
        "type": "armor",
        "grade": 4,
        "emoji": "⚡",
        "base_stats": {"soul_strength": 750, "battle_power": 200},
        "description": "Mail blessed by the Heavenly Guardians. Deflects spiritual attacks.",
    },
    {
        "id": 16,
        "name": "Spirit Emperor Robe",
        "type": "armor",
        "grade": 5,
        "emoji": "🌟",
        "base_stats": {"soul_strength": 1400, "battle_power": 350},
        "description": "A robe worn by Spirit Emperors of old. Commands respect and fear.",
    },
    {
        "id": 17,
        "name": "Divine Phoenix Cloak",
        "type": "armor",
        "grade": 6,
        "emoji": "🔥",
        "base_stats": {"soul_strength": 2600, "battle_power": 600, "luck": 40},
        "description": "A cloak woven from phoenix feathers. Burns those who dare attack its wearer.",
    },
    {
        "id": 18,
        "name": "Dao Immortal Vestment",
        "type": "armor",
        "grade": 7,
        "emoji": "💜",
        "base_stats": {"soul_strength": 5000, "battle_power": 1000, "perception": 80},
        "description": "Vestments of a true Dao Immortal. Transcends mortal protection.",
    },
    # ── ACCESSORIES (slot: accessory) ──
    {
        "id": 3,
        "name": "Ancient Copper Ring",
        "type": "accessory",
        "grade": 0,
        "emoji": "💍",
        "base_stats": {"luck": 5},
        "description": "A simple ring carrying an aura of luck.",
    },
    {
        "id": 19,
        "name": "Jade Pendant",
        "type": "accessory",
        "grade": 1,
        "emoji": "💚",
        "base_stats": {"luck": 12, "perception": 8},
        "description": "A jade pendant that sharpens the senses of its wearer.",
    },
    {
        "id": 20,
        "name": "Spirit Bead Bracelet",
        "type": "accessory",
        "grade": 2,
        "emoji": "📿",
        "base_stats": {"luck": 25, "soul_strength": 40},
        "description": "A bracelet of spirit beads. Each bead contains a fragment of Qi.",
    },
    {
        "id": 21,
        "name": "Earth Heart Amulet",
        "type": "accessory",
        "grade": 3,
        "emoji": "💛",
        "base_stats": {"luck": 45, "perception": 30, "soul_strength": 80},
        "description": "An amulet containing the heart of the earth. Grounds and empowers.",
    },
    {
        "id": 22,
        "name": "Void Eye Pendant",
        "type": "accessory",
        "grade": 4,
        "emoji": "👁️",
        "base_stats": {"perception": 80, "luck": 60},
        "description": "A pendant with an eye that sees through the void. Reveals hidden truths.",
    },
    {
        "id": 23,
        "name": "Spirit Dragon Ring",
        "type": "accessory",
        "grade": 5,
        "emoji": "🐉",
        "base_stats": {"luck": 100, "battle_power": 300, "perception": 60},
        "description": "A ring containing the spirit of an ancient dragon. Immense power.",
    },
    {
        "id": 24,
        "name": "Divine Star Earring",
        "type": "accessory",
        "grade": 6,
        "emoji": "⭐",
        "base_stats": {"luck": 150, "perception": 120, "soul_strength": 400},
        "description": "An earring forged from a fallen divine star. Radiates cosmic energy.",
    },
    {
        "id": 25,
        "name": "Dao Crown Fragment",
        "type": "accessory",
        "grade": 7,
        "emoji": "👑",
        "base_stats": {"luck": 250, "battle_power": 800, "soul_strength": 800, "perception": 200},
        "description": "A fragment of the Dao Crown. Grants dominion over all elements.",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # FACTION EXCLUSIVE — Celestial (☀️)
    # Identity: defensive, soul, perception — "The Righteous Path"
    # Slightly better than standard items at same grade (faction perk)
    # ═══════════════════════════════════════════════════════════════════════
    # Grade 2 — Disciple rank, Realm 3
    {
        "id": 26,
        "name": "Radiant Silk Robe",
        "type": "armor",
        "grade": 2,
        "emoji": "☀️",
        "base_stats": {"soul_strength": 250, "perception": 30},
        "min_realm": 3,
        "description": "A robe woven from Celestial silk. Shields the spirit and sharpens the mind.",
    },
    {
        "id": 27,
        "name": "Purifier's Blade",
        "type": "weapon",
        "grade": 2,
        "emoji": "☀️",
        "base_stats": {"battle_power": 300, "soul_strength": 50},
        "min_realm": 3,
        "description": "A blade that burns with holy fire. Purifies corruption on contact.",
    },
    {
        "id": 28,
        "name": "Halo of Clarity",
        "type": "accessory",
        "grade": 2,
        "emoji": "☀️",
        "base_stats": {"perception": 40, "luck": 20, "soul_strength": 30},
        "min_realm": 3,
        "description": "A floating halo that grants celestial vision. Sees through all deception.",
    },
    # Grade 3 — Elder rank, Realm 4
    {
        "id": 29,
        "name": "Heaven Warden Plate",
        "type": "armor",
        "grade": 3,
        "emoji": "☀️",
        "base_stats": {"soul_strength": 500, "battle_power": 120, "perception": 40},
        "min_realm": 4,
        "description": "Plate armor blessed by the Celestial Court. Each hit echoes through the heavens.",
    },
    {
        "id": 30,
        "name": "Celestial Arbiter Sword",
        "type": "weapon",
        "grade": 3,
        "emoji": "☀️",
        "base_stats": {"battle_power": 580, "soul_strength": 80, "perception": 25},
        "min_realm": 4,
        "description": "The blade of a Celestial judge. Cuts with the weight of divine law.",
    },
    # Grade 4 — Core Member rank, Realm 5
    {
        "id": 31,
        "name": "Seraph's Vestment",
        "type": "armor",
        "grade": 4,
        "emoji": "☀️",
        "base_stats": {"soul_strength": 900, "battle_power": 250, "perception": 60},
        "min_realm": 5,
        "description": "Vestment of the Six-Winged Seraphs. Light bends around the wearer.",
    },
    {
        "id": 32,
        "name": "Sword of the Morning Star",
        "type": "weapon",
        "grade": 4,
        "emoji": "☀️",
        "base_stats": {"battle_power": 1050, "soul_strength": 200, "perception": 40},
        "min_realm": 5,
        "description": "Forged in the light of the first dawn. Burns brightest in the darkest hour.",
    },
    {
        "id": 33,
        "name": "Mandate of Heaven Ring",
        "type": "accessory",
        "grade": 4,
        "emoji": "☀️",
        "base_stats": {"perception": 100, "luck": 80, "soul_strength": 150},
        "min_realm": 5,
        "description": "A ring carrying the Mandate of Heaven. Its wearer commands celestial authority.",
    },
    # Grade 5 — Patriarch rank, Realm 7
    {
        "id": 34,
        "name": "Empyrean Holy Armor",
        "type": "armor",
        "grade": 5,
        "emoji": "☀️",
        "base_stats": {"soul_strength": 1600, "battle_power": 450, "perception": 100},
        "min_realm": 7,
        "description": "Armor from the Empyrean Realm. Said to withstand the wrath of Immortals.",
    },
    {
        "id": 35,
        "name": "Blade of Ten Thousand Virtues",
        "type": "weapon",
        "grade": 5,
        "emoji": "☀️",
        "base_stats": {"battle_power": 1800, "soul_strength": 350, "perception": 80},
        "min_realm": 7,
        "description": "Each virtue strengthens the blade. The righteous path made manifest in steel.",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # FACTION EXCLUSIVE — Demonic (👹)
    # Identity: offensive, battle_power, luck (crit) — "The Path of Carnage"
    # ═══════════════════════════════════════════════════════════════════════
    # Grade 2 — Disciple rank, Realm 3
    {
        "id": 36,
        "name": "Bloodweave Mantle",
        "type": "armor",
        "grade": 2,
        "emoji": "👹",
        "base_stats": {"soul_strength": 180, "battle_power": 80, "luck": 20},
        "min_realm": 3,
        "description": "A mantle dyed in the blood of fallen cultivators. Grows stronger with each battle.",
    },
    {
        "id": 37,
        "name": "Fanged Shadow Blade",
        "type": "weapon",
        "grade": 2,
        "emoji": "👹",
        "base_stats": {"battle_power": 320, "luck": 15},
        "min_realm": 3,
        "description": "A jagged blade that drinks qi from wounds. The more it cuts, the thirstier it becomes.",
    },
    {
        "id": 38,
        "name": "Skull Bone Talisman",
        "type": "accessory",
        "grade": 2,
        "emoji": "👹",
        "base_stats": {"battle_power": 60, "luck": 35, "soul_strength": 20},
        "min_realm": 3,
        "description": "A talisman carved from the skull of a fallen elder. Whispers battle secrets.",
    },
    # Grade 3 — Elder rank, Realm 4
    {
        "id": 39,
        "name": "Infernal Scale Mail",
        "type": "armor",
        "grade": 3,
        "emoji": "👹",
        "base_stats": {"soul_strength": 380, "battle_power": 200, "luck": 30},
        "min_realm": 4,
        "description": "Armor of scales from an infernal beast. Burns those who strike the wearer.",
    },
    {
        "id": 40,
        "name": "Asura's Cleaver",
        "type": "weapon",
        "grade": 3,
        "emoji": "👹",
        "base_stats": {"battle_power": 620, "luck": 25},
        "min_realm": 4,
        "description": "The weapon of a war-Asura. Each swing tears through space itself.",
    },
    # Grade 4 — Core Member rank, Realm 5
    {
        "id": 41,
        "name": "Abyssal Exoskeleton",
        "type": "armor",
        "grade": 4,
        "emoji": "👹",
        "base_stats": {"soul_strength": 700, "battle_power": 350, "luck": 50},
        "min_realm": 5,
        "description": "Living armor from the Abyss. Feeds on the wearer's killing intent to grow harder.",
    },
    {
        "id": 42,
        "name": "Demonlord's Fang",
        "type": "weapon",
        "grade": 4,
        "emoji": "👹",
        "base_stats": {"battle_power": 1150, "luck": 50},
        "min_realm": 5,
        "description": "A fang ripped from a Demonlord. Howls for blood with every swing.",
    },
    {
        "id": 43,
        "name": "Ring of the Blood Pact",
        "type": "accessory",
        "grade": 4,
        "emoji": "👹",
        "base_stats": {"battle_power": 150, "luck": 100, "soul_strength": 80},
        "min_realm": 5,
        "description": "Sealed with a blood oath. Grants devastating critical strikes.",
    },
    # Grade 5 — Patriarch rank, Realm 7
    {
        "id": 44,
        "name": "Nethervoid Warlord Armor",
        "type": "armor",
        "grade": 5,
        "emoji": "👹",
        "base_stats": {"soul_strength": 1300, "battle_power": 600, "luck": 80},
        "min_realm": 7,
        "description": "Armor worn by the Warlord of the Nethervoid. Radiates an aura of absolute destruction.",
    },
    {
        "id": 45,
        "name": "Godslayer's Eclipse",
        "type": "weapon",
        "grade": 5,
        "emoji": "👹",
        "base_stats": {"battle_power": 2000, "luck": 80, "soul_strength": 200},
        "min_realm": 7,
        "description": "A blade that has tasted divine blood. Even the Heavens tremble at its edge.",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # CELESTIAL GRADE (8) — F-11: Only forgeable at Mahayana (Realm 8+)
    # Requires Celestial Iron + Heavenly Jade materials.
    # Stats slightly above grade-7 Dao gear, but gated behind celestial content.
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": 46,
        "name": "Celestial Sundering Blade",
        "type": "weapon",
        "grade": 8,
        "emoji": "☀️",
        "base_stats": {"battle_power": 9000, "soul_strength": 800, "perception": 150},
        "min_realm": 8,
        "description": "A blade forged from Heavenly Jade in celestial flames. Each swing echoes through the nine heavens.",
    },
    {
        "id": 47,
        "name": "Celestial Empyrean Vestment",
        "type": "armor",
        "grade": 8,
        "emoji": "☀️",
        "base_stats": {"soul_strength": 7500, "battle_power": 1500, "perception": 120},
        "min_realm": 8,
        "description": "Robe woven from the first rays of the Celestial Dawn. Said to turn aside the blades of Immortals themselves.",
    },
    {
        "id": 48,
        "name": "Celestial Dao Ring",
        "type": "accessory",
        "grade": 8,
        "emoji": "☀️",
        "base_stats": {"luck": 400, "battle_power": 1200, "soul_strength": 1000, "perception": 300},
        "min_realm": 8,
        "description": "A ring carrying a seed of Celestial Dao. Whispers the secret laws of the universe to its wearer.",
    },
    # ═══════════════════════════════════════════════════════════════════════
    # F-11.5 — Second triad of Celestial artifacts (G8). Same Celestial set
    # for Resonance (set bonus engages at 1/2/3 pieces equipped). Players can
    # mix-and-match: wear an old G8 weapon + a new G8 armor + a new G8 accessory
    # and still get the 3-piece resonance bonus.
    # ═══════════════════════════════════════════════════════════════════════
    {
        "id": 49,
        "name": "Celestial Ascension Spear",
        "type": "weapon",
        "grade": 8,
        "emoji": "🌠",
        "base_stats": {"battle_power": 9500, "soul_strength": 700, "luck": 180},
        "min_realm": 8,
        "description": "A spear whose tip touches the ninth heaven. Its every thrust carries the weight of an ascending star.",
    },
    {
        "id": 50,
        "name": "Celestial Aegis Plate",
        "type": "armor",
        "grade": 8,
        "emoji": "🌠",
        "base_stats": {"soul_strength": 7800, "battle_power": 1300, "luck": 150},
        "min_realm": 8,
        "description": "Plate armor bound with Heavenly Jade runes. The Heavenly Will itself refuses to let its wearer fall.",
    },
    {
        "id": 51,
        "name": "Celestial Karma Pendant",
        "type": "accessory",
        "grade": 8,
        "emoji": "🌠",
        "base_stats": {"luck": 450, "battle_power": 1000, "soul_strength": 1200, "perception": 250},
        "min_realm": 8,
        "description": "A pendant holding a seed of Karmic Dao. It shifts misfortune back to its source, one breath at a time.",
    },
]

ORES = [
    {"id": 1, "name": "Mortal Iron", "tier": 1, "emoji": "🪨", "description": "Common ore found in shallow mines."},
    {"id": 2, "name": "Spirit Copper", "tier": 2, "emoji": "🟧", "description": "Copper that has absorbed Qi from the earth."},
    {"id": 3, "name": "Mystic Silver", "tier": 3, "emoji": "⬜", "description": "Bright metal with high magical affinity."},
    {"id": 4, "name": "Stellar Gold", "tier": 4, "emoji": "✨", "description": "Ore that fell from the stars."},
    {"id": 5, "name": "Celestial Jade", "tier": 5, "emoji": "💚", "description": "Jade imbued with celestial energy. Shines with inner light."},
    {"id": 6, "name": "Void Crystal", "tier": 6, "emoji": "🌑", "description": "Crystal from the void between worlds. Warps space around it."},
    {"id": 7, "name": "Dao Essence Stone", "tier": 7, "emoji": "💜", "description": "A stone containing a fragment of the Dao. The ultimate forging material."},
    {"id": 8, "name": "Phoenix Ash", "tier": 3, "emoji": "🔥", "description": "Ashes left behind by a reborn phoenix. Essential for cauldron refinement."},
    {"id": 9, "name": "Dragon Scale", "tier": 4, "emoji": "🐉", "description": "A scale shed by an ancient dragon. Imbued with primal fire essence."},
    {"id": 10, "name": "Celestial Iron", "tier": 5, "emoji": "⚙️", "description": "Iron forged in celestial flames. Only Immortal-tier beings can handle it."},
    {"id": 11, "name": "Heavenly Jade", "tier": 6, "emoji": "🟢", "description": "Jade condensed from the essence of the nine heavens. Required to forge Celestial-grade artifacts."},
]


async def run_artifact_seeds(session: AsyncSession):
    existing_art_ids = set((await session.execute(select(ArtifactCatalog.id))).scalars().all())
    added_arts = 0
    updated_arts = 0
    for art_data in ARTIFACTS:
        if art_data["id"] not in existing_art_ids:
            session.add(ArtifactCatalog(**art_data))
            added_arts += 1
        else:
            row = (await session.execute(
                select(ArtifactCatalog).where(ArtifactCatalog.id == art_data["id"])
            )).scalar_one()
            changed = False
            for k, v in art_data.items():
                if k != "id" and getattr(row, k) != v:
                    setattr(row, k, v)
                    changed = True
            if changed:
                updated_arts += 1
    if added_arts or updated_arts:
        logger.info("⚔️ Seeded %d new artifacts, updated %d existing", added_arts, updated_arts)

    existing_ore_ids = set((await session.execute(select(OreCatalog.id))).scalars().all())
    added_ores = 0
    for ore_data in ORES:
        if ore_data["id"] not in existing_ore_ids:
            session.add(OreCatalog(**ore_data))
            added_ores += 1
    if added_ores:
        logger.info("🪨 Seeded %d new ores (skipped %d existing)", added_ores, len(ORES) - added_ores)

    await session.commit()
