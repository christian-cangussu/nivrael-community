import logging
from sqlalchemy import select, update
from database.models import TechniqueCatalog

logger = logging.getLogger(__name__)

# v15.1 — Qi cost per technique for turn-based duels.
# Tier guideline (matches master plan v15 §5):
#   Common (realm 1-2):            10-15
#   Rare (realm 3-4):              25-40
#   Legendary (realm 5+):          50-80
#   Faction techniques:            30-60 (scales with rank)
#   Meditation/Interior (passive): 0 (never consumed in combat)
QI_COSTS = {
    # Common combat — realm 1-2
    1: 10,  4: 15,  3: 12,  6: 12,  8: 10,
    # Rare combat — realm 3-4
    2: 30,  7: 25,  5: 35,
    # Special spirit-root
    11: 80,
    # Legendary — realm 5-8
    9: 40, 13: 45, 14: 50, 10: 60, 15: 55, 12: 70, 16: 65, 17: 80, 18: 60,
    # Celestial faction
    19: 20, 20: 35, 21: 55,
    # Demonic faction
    22: 25, 23: 35, 24: 60,
    # Meditation + interior — never consumed in combat
    25: 0, 26: 0, 27: 0, 28: 0, 29: 0, 30: 0,
}

# v15.2 — intent affinity per combat technique (Sword/Fist/Body/Dao/Killing).
# Meditation + interior techs stay absent (NULL in DB) — they don't fight.
# Faction techs map by elemental archetype (light → Dao/Body, chaos → Killing).
# Mapping rationale documented in master plan §3 + techniques_expanded.md §Intent.
INTENT_AFFINITIES = {
    # Sword — cutting / precision / blade essence
    1:  "killing",   # Thunder Step — assassin's blink (re-mapped from Sword to Killing per master plan)
    5:  "sword",     # Void Slash
    15: "sword",     # Heaven Rend
    14: "sword",     # Storm Fist (wind blade-cuts)
    # Fist — raw impact / will
    2:  "fist",      # Dragon Fist
    10: "fist",      # Phoenix Strike
    17: "fist",      # Eternal Strike
    # Body — endurance / regen / fortress
    3:  "body",      # Iron Body
    7:  "body",      # Frost Shield
    13: "body",      # Absolute Defense
    16: "body",      # Undying Fortress
    # Dao — essence / perception / soul
    12: "dao",       # Soul Devourer
    9:  "dao",       # Divine Finger
    6:  "dao",       # Celestial Palm
    11: "dao",       # Heavenly Root Technique (universal essence)
    # Killing — assassination / evasion / vanish-before-strike
    4:  "killing",   # Shadow Step
    18: "killing",   # Boundless Evasion
    # Faction Celestial (light archetype) — defensive/judgment → Body/Dao
    19: "body",      # Radiant Guard (defensive aura)
    20: "body",      # Heaven's Mandate (damage reduce)
    21: "dao",       # Divine Judgment (heaven's verdict)
    # Faction Demonic (chaos archetype) — frenzy/rend/annihilate → Killing
    22: "killing",   # Blood Frenzy
    23: "killing",   # Soul Rend
    24: "killing",   # Abyssal Annihilation
    # Meditation (25-27) + Interior (28-30) — intentionally absent (NULL).
}

# ── Dao Law IDs (from dao_seeds.py) ───────────────────────────────────────────
# 1 = Dao of Speed (Lightning)   min_realm 5
# 2 = Dao of Destruction (Fire)  min_realm 5
# 3 = Dao of Life (Wood)         min_realm 5
# 4 = Dao of Time (Chaos)        min_realm 6
# 5 = Dao of Creation (Earth)    min_realm 6
# 6 = Eternal Dao (Chaos)        min_realm 8

TECHNIQUES = [
    # ── Realm 1 ───────────────────────────────────────────────────────────────
    {
        "id": 1,
        "name": "Thunder Step",
        "element": "lightning",
        "emoji": "⚡",
        "effect_type": "evasion",
        "effect_value": 0.30,
        "effect_round": 1,
        "req_realm": 1,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Lightning-fast steps that grant 30% evasion in the first round.",
    },
    {
        "id": 4,
        "name": "Shadow Step",
        "element": "universal",
        "emoji": "🌑",
        "effect_type": "dodge",
        "effect_value": 1.0,
        "effect_round": 0,
        "req_realm": 1,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Shadow Step — completely dodges an attack.",
    },
    # ── Realm 2 ───────────────────────────────────────────────────────────────
    {
        "id": 3,
        "name": "Iron Body",
        "element": "earth",
        "emoji": "🌍",
        "effect_type": "damage_reduce",
        "effect_value": 0.50,
        "effect_round": 0,
        "req_realm": 2,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Iron Body — reduces received damage by 50% in all rounds.",
    },
    {
        "id": 6,
        "name": "Celestial Palm",
        "element": "universal",
        "emoji": "✋",
        "effect_type": "damage_mult",
        "effect_value": 0.5,
        "effect_round": 0,
        "req_realm": 2,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Celestial Palm — +50% damage all rounds.",
    },
    {
        "id": 8,
        "name": "Wind Walk",
        "element": "wind",
        "emoji": "🌪️",
        "effect_type": "evasion",
        "effect_value": 0.20,
        "effect_round": 0,
        "req_realm": 2,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Wind Walk — +20% evasion all rounds.",
    },
    # ── Realm 3 ───────────────────────────────────────────────────────────────
    {
        "id": 2,
        "name": "Dragon Fist",
        "element": "fire",
        "emoji": "🔥",
        "effect_type": "damage_mult",
        "effect_value": 1.0,
        "effect_round": 3,
        "req_realm": 3,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Dragon Fist — deals 2x damage on round 3.",
    },
    {
        "id": 7,
        "name": "Frost Shield",
        "element": "ice",
        "emoji": "❄️",
        "effect_type": "damage_reduce",
        "effect_value": 0.35,
        "effect_round": 0,
        "req_realm": 3,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Frost Shield — reduces damage taken by 35% all rounds.",
    },
    # ── Realm 4 ───────────────────────────────────────────────────────────────
    {
        "id": 5,
        "name": "Void Slash",
        "element": "chaos",
        "emoji": "☯️",
        "effect_type": "armor_ignore",
        "effect_value": 0.50,
        "effect_round": 0,
        "req_realm": 4,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Void Slash — ignores 50% of enemy armor.",
    },
    # ── Special (Heavenly Spirit Root only) ───────────────────────────────────
    {
        "id": 11,
        "name": "Heavenly Root Technique",
        "element": "universal",
        "emoji": "🌸",
        "effect_type": "damage_mult",
        "effect_value": 2.0,
        "effect_round": 1,
        "req_realm": 0,
        "req_spirit_root": 0,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Heavenly Root Technique — 3x damage on round 1. Heavenly Spirit Root ONLY.",
    },
    # ── Realm 5 — requires Dao fragments ─────────────────────────────────────
    {
        "id": 9,
        "name": "Divine Finger",
        "element": "universal",
        "emoji": "☝️",
        "effect_type": "armor_ignore",
        "effect_value": 0.30,
        "effect_round": 0,
        "req_realm": 5,
        "req_spirit_root": None,
        "required_dao_law_id": 1,   # Dao of Speed
        "required_dao_insight": 3,
        "description": "Divine Finger — ignores 30% armor all rounds. Requires Dao of Speed insight.",
    },
    {
        "id": 13,
        "name": "Absolute Defense",
        "element": "earth",
        "emoji": "🛡️",
        "effect_type": "damage_reduce",
        "effect_value": 0.70,
        "effect_round": 1,
        "req_realm": 5,
        "req_spirit_root": None,
        "required_dao_law_id": 3,   # Dao of Life
        "required_dao_insight": 3,
        "description": "Absolute Defense — reduces damage by 70% on round 1. Requires Dao of Life insight.",
    },
    {
        "id": 14,
        "name": "Storm Fist",
        "element": "wind",
        "emoji": "🌪️",
        "effect_type": "damage_mult",
        "effect_value": 0.70,
        "effect_round": 0,
        "req_realm": 5,
        "req_spirit_root": None,
        "required_dao_law_id": 1,   # Dao of Speed
        "required_dao_insight": 2,
        "description": "Storm Fist — +70% damage all rounds. Speed turns to destruction.",
    },
    # ── Realm 6 — requires Dao fragments ─────────────────────────────────────
    {
        "id": 10,
        "name": "Phoenix Strike",
        "element": "fire",
        "emoji": "🔥",
        "effect_type": "damage_mult",
        "effect_value": 1.5,
        "effect_round": 5,
        "req_realm": 6,
        "req_spirit_root": None,
        "required_dao_law_id": 2,   # Dao of Destruction
        "required_dao_insight": 5,
        "description": "Phoenix Strike — 2.5x damage on round 5. Requires Dao of Destruction mastery.",
    },
    {
        "id": 15,
        "name": "Heaven Rend",
        "element": "chaos",
        "emoji": "💠",
        "effect_type": "armor_ignore",
        "effect_value": 0.65,
        "effect_round": 0,
        "req_realm": 6,
        "req_spirit_root": None,
        "required_dao_law_id": 4,   # Dao of Time
        "required_dao_insight": 4,
        "description": "Heaven Rend — ignores 65% of enemy armor. Time unmakes all defenses.",
    },
    # ── Realm 7 — requires deep Dao fragments ────────────────────────────────
    {
        "id": 12,
        "name": "Soul Devourer",
        "element": "chaos",
        "emoji": "💀",
        "effect_type": "damage_mult",
        "effect_value": 0.8,
        "effect_round": 0,
        "req_realm": 7,
        "req_spirit_root": None,
        "required_dao_law_id": 4,   # Dao of Time
        "required_dao_insight": 7,
        "description": "Soul Devourer — +80% damage all rounds. Requires deep Dao of Time comprehension.",
    },
    {
        "id": 16,
        "name": "Undying Fortress",
        "element": "earth",
        "emoji": "⛰️",
        "effect_type": "damage_reduce",
        "effect_value": 0.80,
        "effect_round": 1,
        "req_realm": 7,
        "req_spirit_root": None,
        "required_dao_law_id": 3,   # Dao of Life
        "required_dao_insight": 6,
        "description": "Undying Fortress — reduces damage by 80% on round 1. Endures through the Dao of Life.",
    },
    # ── Realm 8 — Eternal Dao required ───────────────────────────────────────
    {
        "id": 17,
        "name": "Eternal Strike",
        "element": "universal",
        "emoji": "💜",
        "effect_type": "damage_mult",
        "effect_value": 2.5,
        "effect_round": 1,
        "req_realm": 8,
        "req_spirit_root": None,
        "required_dao_law_id": 6,   # Eternal Dao
        "required_dao_insight": 8,
        "description": "Eternal Strike — 3.5x damage on round 1. Only the Eternal Dao grants such power.",
    },
    {
        "id": 18,
        "name": "Boundless Evasion",
        "element": "universal",
        "emoji": "🌀",
        "effect_type": "evasion",
        "effect_value": 0.60,
        "effect_round": 0,
        "req_realm": 8,
        "req_spirit_root": None,
        "required_dao_law_id": 6,   # Eternal Dao
        "required_dao_insight": 6,
        "description": "Boundless Evasion — 60% evasion all rounds. Transcend the limits of form.",
    },
    # ── Faction: Celestial Techniques (☀️) ──────────────────────────────────
    # T1 — Disciple rank (rep 200), Realm 3
    {
        "id": 19,
        "name": "Radiant Guard",
        "element": "light",
        "emoji": "☀️",
        "effect_type": "damage_reduce",
        "effect_value": 0.15,
        "effect_round": 0,
        "req_realm": 3,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Celestial breathing wraps the body in holy light, reducing all damage by 15%.",
    },
    # T2 — Elder rank (rep 1000), Realm 4
    {
        "id": 20,
        "name": "Heaven's Mandate",
        "element": "light",
        "emoji": "☀️",
        "effect_type": "damage_reduce",
        "effect_value": 0.30,
        "effect_round": 0,
        "req_realm": 4,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "The Heavens shield the righteous. -30% damage taken in all rounds.",
    },
    # T3 — Patriarch rank (rep 5000), Realm 6
    {
        "id": 21,
        "name": "Divine Judgment",
        "element": "light",
        "emoji": "☀️",
        "effect_type": "damage_mult",
        "effect_value": 1.8,
        "effect_round": 1,
        "req_realm": 6,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Call down Heaven's wrath — 2.8x damage on round 1. The Celestial Court's final verdict.",
    },
    # ── Faction: Demonic Techniques (👹) ─────────────────────────────────
    # T1 — Disciple rank (rep 200), Realm 3
    {
        "id": 22,
        "name": "Blood Frenzy",
        "element": "chaos",
        "emoji": "👹",
        "effect_type": "damage_mult",
        "effect_value": 0.20,
        "effect_round": 0,
        "req_realm": 3,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Demonic qi fuels a blood frenzy — +20% damage in all rounds.",
    },
    # T2 — Elder rank (rep 1000), Realm 4
    {
        "id": 23,
        "name": "Soul Rend",
        "element": "chaos",
        "emoji": "👹",
        "effect_type": "armor_ignore",
        "effect_value": 0.40,
        "effect_round": 0,
        "req_realm": 4,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Demonic claws tear through defenses — ignores 40% of enemy armor in all rounds.",
    },
    # T3 — Patriarch rank (rep 5000), Realm 6
    {
        "id": 24,
        "name": "Abyssal Annihilation",
        "element": "chaos",
        "emoji": "👹",
        "effect_type": "damage_mult",
        "effect_value": 2.0,
        "effect_round": 1,
        "req_realm": 6,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "description": "Unleash the Abyss — 3.0x damage on round 1. Nothing survives the Demonic annihilation.",
    },
    # ── Meditation Techniques (tech_type: meditation) ──────────────────────────
    {
        "id": 25,
        "name": "Tranquil Mind",
        "element": "universal",
        "emoji": "🧘",
        "effect_type": "cb_boost",
        "effect_value": 0.20,
        "effect_round": 0,
        "req_realm": 1,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "tech_type": "meditation",
        "description": "A serene breathing method that calms the mind and accelerates Cultivation Base gains by 20% during meditation.",
    },
    {
        "id": 26,
        "name": "Soul Gathering",
        "element": "universal",
        "emoji": "🌌",
        "effect_type": "qi_regen_boost",
        "effect_value": 0.30,
        "effect_round": 0,
        "req_realm": 2,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "tech_type": "meditation",
        "description": "Draws ambient spiritual energy inward, boosting Qi regeneration by 30% while meditating.",
    },
    {
        "id": 27,
        "name": "Body Restoration",
        "element": "earth",
        "emoji": "💫",
        "effect_type": "hp_regen_boost",
        "effect_value": 0.50,
        "effect_round": 0,
        "req_realm": 3,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "tech_type": "meditation",
        "description": "Channels Qi through wounded meridians during meditation, increasing HP regeneration by 50%.",
    },
    # ── Interior Techniques (tech_type: interior, passive) ───────────────────
    {
        "id": 28,
        "name": "Iron Will",
        "element": "earth",
        "emoji": "🏔️",
        "effect_type": "soul_boost",
        "effect_value": 0.10,
        "effect_round": 0,
        "req_realm": 2,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "tech_type": "interior",
        "description": "Tempers the soul through unwavering resolve. Permanently increases Soul Strength by 10%.",
    },
    {
        "id": 29,
        "name": "Eagle Eye",
        "element": "wind",
        "emoji": "🦅",
        "effect_type": "perception_boost",
        "effect_value": 0.10,
        "effect_round": 0,
        "req_realm": 3,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "tech_type": "interior",
        "description": "Sharpens spiritual sense beyond mortal limits. Permanently increases Perception by 10%.",
    },
    {
        "id": 30,
        "name": "Fortune's Favor",
        "element": "universal",
        "emoji": "🍀",
        "effect_type": "luck_boost",
        "effect_value": 0.10,
        "effect_round": 0,
        "req_realm": 4,
        "req_spirit_root": None,
        "required_dao_law_id": None,
        "required_dao_insight": 0,
        "tech_type": "interior",
        "description": "Aligns one's Dao with the flow of fortune. Permanently increases Luck by 10%.",
    },
]


# ── v16.4c — Sect Library signature techniques ────────────────────────────────
# Each of the 9 NPC houses guards 5 signature arts, one unlockable at each rank
# (disciple→inner→core→elder→heir == tiers 1-5). These are LIBRARY-EXCLUSIVE:
# learned only via the Sect Hall (rank-gated, additive PlayerTechnique, NO
# scroll), and EXCLUDED from the live drop/scroll pools via `sect_key` so they
# never collide with the scrolls the 57 paying players already own (Lei §5).
# Values are deliberately IN-BAND with the catalog above (damage_mult is the
# bonus fraction, not a multiplier) and slow-gated, so they add depth without
# perturbing the just-shipped v16.7 combat balance (Lei §3). The rank→tech map
# lives in core.world_sects_engine.SECT_LIBRARY (single source for the unlock).
def _sig(tid, name, element, emoji, etype, eval_, eround, realm, intent, qi, sect, desc):
    return {
        "id": tid, "name": name, "element": element, "emoji": emoji,
        "effect_type": etype, "effect_value": eval_, "effect_round": eround,
        "req_realm": realm, "req_spirit_root": None,
        "required_dao_law_id": None, "required_dao_insight": 0,
        "tech_type": "combat", "description": desc,
        "qi_cost": qi, "intent_affinity": intent, "sect_key": sect,
    }


SECT_TECHNIQUES = [
    # ── Azure Cloud ☁️ (mobility + sword) ──
    _sig(500, "Cloud Step", "wind", "☁️", "evasion", 0.12, 0, 1, "sword", 15, "azure_cloud",
         "The first art of the Azure Cloud — feet that never quite touch the earth. +12% evasion."),
    _sig(501, "Azure Sword Form", "wind", "🗡️", "damage_mult", 0.18, 0, 1, "sword", 25, "azure_cloud",
         "The sword rides the wind. +18% damage in all rounds."),
    _sig(502, "Cloud Dragon Slash", "wind", "🐉", "damage_mult", 0.35, 0, 3, "sword", 38, "azure_cloud",
         "A dragon coils within the clouds and descends. +35% damage in all rounds."),
    _sig(503, "Heaven Cloud Severance", "wind", "☁️", "armor_ignore", 0.40, 0, 5, "sword", 52, "azure_cloud",
         "The Elder's signature — a cut that the heavens cannot guard against. Ignores 40% armor."),
    _sig(504, "Yún Step Reborn", "wind", "🌀", "evasion", 0.35, 0, 7, "sword", 68, "azure_cloud",
         "Founder Bái's lost art, returned to the worthy Heir. +35% evasion in all rounds."),
    # ── Eternal Flame 🔥 (alchemy + fire) ──
    _sig(505, "Ember Palm", "fire", "🔥", "damage_mult", 0.15, 0, 1, "dao", 15, "eternal_flame",
         "A palm kindled with the pavilion's eternal coal. +15% damage."),
    _sig(506, "Soul Fire", "fire", "🔥", "damage_mult", 0.22, 0, 1, "dao", 25, "eternal_flame",
         "Flame that burns the spirit, not the flesh. +22% damage."),
    _sig(507, "Pill Emperor's Touch", "fire", "⚗️", "damage_reduce", 0.25, 0, 3, "dao", 38, "eternal_flame",
         "The alchemist's body becomes its own cauldron, tempered against harm. -25% damage taken."),
    _sig(508, "Phoenix Flame Body", "fire", "🦅", "damage_mult", 0.45, 0, 5, "dao", 52, "eternal_flame",
         "Wreathed in undying phoenix fire. +45% damage in all rounds."),
    _sig(509, "Nirvana Rebirth Flame", "fire", "🔥", "damage_reduce", 0.40, 0, 7, "dao", 68, "eternal_flame",
         "The Heir burns and is reborn, again and again. -40% damage taken."),
    # ── Jade Harmony 🪷 (defense + healing) ──
    _sig(510, "Jade Shield", "earth", "🪷", "damage_reduce", 0.15, 0, 1, "body", 15, "jade_harmony",
         "Harmony begins with stillness. -15% damage taken."),
    _sig(511, "Mercy Pulse", "universal", "💧", "damage_reduce", 0.22, 0, 1, "body", 25, "jade_harmony",
         "A pulse of mercy that softens every blow. -22% damage taken."),
    _sig(512, "Jade Formation", "earth", "🪷", "damage_reduce", 0.32, 0, 3, "body", 38, "jade_harmony",
         "Nine jade pillars rise around the cultivator. -32% damage taken."),
    _sig(513, "Harmony of Ten Thousand", "earth", "🪷", "damage_reduce", 0.42, 0, 5, "body", 52, "jade_harmony",
         "All things in balance; nothing may break it. -42% damage taken."),
    _sig(514, "Lotus of Rebirth", "universal", "🪷", "damage_reduce", 0.50, 0, 7, "body", 68, "jade_harmony",
         "The Heir blooms untouched at the heart of the storm. -50% damage taken."),
    # ── Iron Mountain 🏔️ (body + fist) ──
    _sig(515, "Iron Fist Basics", "earth", "👊", "damage_mult", 0.15, 0, 1, "fist", 15, "iron_mountain",
         "The first lesson of the Mountain — strike like falling stone. +15% damage."),
    _sig(516, "Mountain Stance", "earth", "🏔️", "damage_reduce", 0.25, 0, 1, "fist", 25, "iron_mountain",
         "Root yourself; the mountain does not move. -25% damage taken."),
    _sig(517, "Avalanche Fist", "earth", "🏔️", "damage_mult", 0.40, 0, 3, "fist", 38, "iron_mountain",
         "One blow, and the whole slope comes down. +40% damage."),
    _sig(518, "Mountain Heart Dao", "earth", "🏔️", "damage_reduce", 0.40, 0, 5, "fist", 52, "iron_mountain",
         "The Elder's heart is the mountain's heart — unbreakable. -40% damage taken."),
    _sig(519, "Nine Mountains Body", "earth", "🗿", "damage_mult", 0.60, 0, 7, "fist", 68, "iron_mountain",
         "The Heir carries nine mountains in each fist. +60% damage in all rounds."),
    # ── Frozen Peak ❄️ (defense + ice) ──
    _sig(520, "Frost Guard", "ice", "❄️", "damage_reduce", 0.18, 0, 1, "body", 15, "frozen_peak",
         "A thin rime of frost turns the first blows aside. -18% damage taken."),
    _sig(521, "Glacial Shell", "ice", "🧊", "damage_reduce", 0.28, 0, 1, "body", 25, "frozen_peak",
         "Ice armours the meridians. -28% damage taken."),
    _sig(522, "Winter's Silence", "ice", "❄️", "evasion", 0.20, 0, 3, "body", 38, "frozen_peak",
         "Move as the snowfall — unheard, unseen. +20% evasion."),
    _sig(523, "Frozen Heart Dao", "ice", "❄️", "damage_reduce", 0.40, 0, 5, "body", 52, "frozen_peak",
         "A heart of glacier feels neither pain nor fear. -40% damage taken."),
    _sig(524, "Eternal Glacier Body", "ice", "🧊", "damage_reduce", 0.50, 0, 7, "body", 68, "frozen_peak",
         "The Heir's flesh is the unmelting peak itself. -50% damage taken."),
    # ── Thousand Bloom 🌸 (herb + pill + wood) ──
    _sig(525, "Spirit Garden", "earth", "🌸", "damage_reduce", 0.15, 0, 1, "dao", 15, "thousand_bloom",
         "A garden grows within, soft and resilient. -15% damage taken."),
    _sig(526, "Flower Communion", "earth", "🌸", "evasion", 0.18, 0, 1, "dao", 25, "thousand_bloom",
         "Sway with the petals; let the blow pass through. +18% evasion."),
    _sig(527, "Hundred Herb Body", "earth", "🌿", "damage_reduce", 0.30, 0, 3, "dao", 38, "thousand_bloom",
         "A body steeped in a hundred spirit herbs endures much. -30% damage taken."),
    _sig(528, "Blooming Dao Heart", "earth", "🌸", "evasion", 0.28, 0, 5, "dao", 52, "thousand_bloom",
         "The Elder's Dao blossoms, and the world bends around it. +28% evasion."),
    _sig(529, "Spring of Ten Thousand Blooms", "earth", "🌷", "damage_reduce", 0.45, 0, 7, "dao", 68, "thousand_bloom",
         "Where the Heir walks, ten thousand flowers shield the way. -45% damage taken."),
    # ── Silent Wind 🌬️ (speed + assassinate) ──
    _sig(530, "Wind Walk Art", "wind", "🌬️", "evasion", 0.18, 0, 1, "killing", 15, "silent_wind",
         "The palace's first breath — walk without sound. +18% evasion."),
    _sig(531, "Silent Shadow Step", "wind", "🌑", "evasion", 0.25, 0, 1, "killing", 25, "silent_wind",
         "Become the shadow between heartbeats. +25% evasion."),
    _sig(532, "Last Breath", "wind", "🗡️", "damage_mult", 1.00, 3, 3, "killing", 38, "silent_wind",
         "Strike on the enemy's exhale — 2x damage on round 3."),
    _sig(533, "Windless Assassination", "wind", "🌪️", "armor_ignore", 0.45, 0, 5, "killing", 52, "silent_wind",
         "A blade that finds the gap no armour covers. Ignores 45% armour."),
    _sig(534, "Death Without Sound", "wind", "💀", "dodge", 1.00, 1, 7, "killing", 68, "silent_wind",
         "The Heir's killing art — for one breath, no attack can touch them (full dodge, round 1)."),
    # ── Blazing Sun ☀️ (fire + forge) ──
    _sig(535, "Sun Strike", "fire", "☀️", "damage_mult", 0.16, 0, 1, "fist", 15, "blazing_sun",
         "A fist that carries the morning sun. +16% damage."),
    _sig(536, "Solar Flare Fist", "fire", "🔥", "damage_mult", 0.24, 0, 1, "fist", 25, "blazing_sun",
         "Flare bright enough to blind, hot enough to burn. +24% damage."),
    _sig(537, "Forge of Eternity", "fire", "🔨", "armor_ignore", 0.30, 0, 3, "fist", 38, "blazing_sun",
         "The sect's forge-fire melts any guard. Ignores 30% armour."),
    _sig(538, "Sunfire Body", "fire", "☀️", "damage_mult", 0.48, 0, 5, "fist", 52, "blazing_sun",
         "The Elder's body is a small sun. +48% damage in all rounds."),
    _sig(539, "Eternal Sun Dao", "fire", "🌟", "armor_ignore", 0.50, 0, 7, "fist", 68, "blazing_sun",
         "The Heir's blaze unmakes every defence. Ignores 50% armour."),
    # ── Abyssal Depths 💀 (soul devour + forbidden — Demonic) ──
    _sig(540, "Demon Mark", "chaos", "💀", "damage_mult", 0.18, 0, 1, "killing", 15, "abyssal_depths",
         "A brand of the Abyss that hungers. +18% damage."),
    _sig(541, "Soul Eater", "chaos", "👁️", "armor_ignore", 0.25, 0, 1, "killing", 25, "abyssal_depths",
         "Devour the soul beneath the armour. Ignores 25% armour."),
    _sig(542, "Abyssal Grasp", "chaos", "🕳️", "armor_ignore", 0.38, 0, 3, "killing", 38, "abyssal_depths",
         "A hand from the deep that no defence escapes. Ignores 38% armour."),
    _sig(543, "Demonic Devourer", "chaos", "💀", "damage_mult", 0.55, 0, 5, "killing", 52, "abyssal_depths",
         "The Elder feasts on the enemy's strength. +55% damage in all rounds."),
    _sig(544, "Sovereign of the Abyss", "chaos", "😈", "damage_mult", 0.70, 0, 7, "killing", 68, "abyssal_depths",
         "The Heir of the Abyss — all that lives is prey. +70% damage in all rounds."),
]

# Append the sect signatures to the catalog the seed runner walks.
TECHNIQUES = TECHNIQUES + SECT_TECHNIQUES

# ── MV-1 §0.3 (V-4 [jogador]) — a técnica de GOLPE da primeira hora ─────────────
# O Velho Mendigo ensina-a no nascimento em mundos com `ftue_espinha` ON
# (core/ftue_engine.grant_ftue_strike_technique). `sect_key="ftue_mendigo"`
# mantém-na FORA de todos os pools de scroll/drop (os filtros exigem
# sect_key IS NULL) e fora da Sect Library (o mapa SECT_LIBRARY não a lista)
# → linha INERTE em main: existe no catálogo, ninguém a concede.
# req_realm 0 de propósito: o grant é DIRETO (sem scroll, sem learn-gate) e
# o duel engine não re-verifica realm em fight-time. Humilde por design
# (+15%, igual às palmas tier-1 de seita) — a escada de upgrade continua viva.
# ── TEC-1 — A Biblioteca da Seita: as artes novas das estantes (ids 550-576) ──
# 3 por casa (1 por estante: Externa/Interna/Núcleo), COMPLEMENTANDO as 5 artes
# v16.4c da mesma casa (a estante junta a lição legada grátis-por-posto + a arte
# nova que a casa VENDE por contribuição — saldo do Pavilhão). Valores IN-BAND
# entre os degraus legados (t1 15/0.12-0.18 → t4 elder 52/0.40-0.55): a
# exclusividade é o prêmio, não power creep (Constituição §3 + Lei §12).
# `library_tier`/`library_cp_cost` (Mig 136) só mordem com `biblioteca_seitas`
# ON (core/sect_library_engine.py); em main as rows ficam DORMANTES (sect_key
# as exclui de TODOS os pools — convenção v16.4c, verificada pelo
# _verify_sect_library.py [7]). Nomes/descs canônicos EN como o resto do
# catálogo; a superfície gated resolve tech_<id>_name/_desc ×3 (padrão q_<id>).
def _lib(tid, name, element, emoji, etype, eval_, eround, realm, intent, qi, sect, tier, desc):
    d = _sig(tid, name, element, emoji, etype, eval_, eround, realm, intent, qi, sect, desc)
    d["library_tier"] = tier
    # UMA verdade do custo: o default por estante vive nos knobs LIB_* do
    # engine; o force-sync do run_combat_seeds re-aplica a cada boot.
    from core.sect_library_engine import tier_default_cp
    d["library_cp_cost"] = tier_default_cp(tier)
    return d


SECT_LIBRARY_TEC1 = [
    # ── Azure Cloud ☁️ ──
    _lib(550, "Cloudpiercer Thrust", "wind", "🗡️", "armor_ignore", 0.21, 0, 1, "sword", 18, "azure_cloud", 1,
         "The blade leaves the scabbard like a sunray splitting the overcast sky; no steel wall can veil what the sword intent has already seen. Ignores 21% of the enemy's armor."),
    _lib(551, "Drifting Nimbus Veil", "wind", "🌫️", "evasion", 0.21, 0, 2, "sword", 30, "azure_cloud", 2,
         "The disciple wraps their silhouette in wandering mist, and every strike aimed at them finds only sky. +21% evasion in every round."),
    _lib(552, "Ninefold Cloud Aegis", "wind", "☁️", "damage_reduce", 0.34, 0, 4, "sword", 44, "azure_cloud", 3,
         "Nine layers of azure cloud coil around the swordsman like a dragon guarding its rider; blows sink into softness and lose their fury. Reduces damage taken by 34%."),
    # ── Eternal Flame 🔥 ──
    _lib(553, "Crucible Palm", "fire", "🔥", "armor_ignore", 0.2, 0, 1, "dao", 18, "eternal_flame", 1,
         "The alchemist's hand carries the heat of a thousand refinements; iron softens like wax at its touch. Ignores 20% of the enemy's armor."),
    _lib(554, "Ashen Mantle", "fire", "🌋", "damage_reduce", 0.26, 0, 2, "dao", 30, "eternal_flame", 2,
         "What has already burned cannot burn again: the cultivator dons a mantle of sacred ash, and hostile force gutters out against it. Reduces damage taken by 26%."),
    _lib(555, "Pill Furnace Cataclysm", "fire", "💥", "damage_mult", 0.85, 3, 4, "dao", 44, "eternal_flame", 3,
         "Three breaths to feed the inner furnace, then the lid is thrown open: all the ambition of the Eternal Flame erupts in a single refining blast. +85% damage on round 3."),
    # ── Jade Harmony 🪷 ──
    _lib(556, "Willow Branch Lash", "earth", "🍃", "damage_mult", 0.15, 0, 1, "body", 18, "jade_harmony", 1,
         "The willow bends before the storm — then its branch answers, swift and without malice. +15% damage in all rounds."),
    _lib(557, "Petalfall Evasion", "earth", "🌸", "evasion", 0.22, 0, 2, "body", 30, "jade_harmony", 2,
         "The serene body drifts aside like a lotus petal loosed upon the breeze — present, untouched, unhurried. +22% evasion in every round."),
    _lib(558, "Still Water Piercing Art", "earth", "💧", "armor_ignore", 0.38, 0, 4, "body", 44, "jade_harmony", 3,
         "Serenity is not weakness: the drop that falls for a hundred years passes through jade without ever striking it. Ignores 38% of the enemy's armor."),
    # ── Iron Mountain 🏔️ ──
    _lib(559, "Granite Hide Tempering", "earth", "🪨", "damage_reduce", 0.16, 0, 1, "fist", 18, "iron_mountain", 1,
         "Iron Mountain disciples begin not by striking, but by enduring: skin beaten against cold stone until it forgets how to break. Reduces damage taken by 16% in all rounds."),
    _lib(560, "Cliffbreaker Fist", "earth", "👊", "damage_mult", 0.28, 0, 2, "fist", 30, "iron_mountain", 2,
         "Where the Mountain Stance teaches stillness, this art teaches the answer: one fist thrown with the whole weight of the peak behind it. +28% damage in all rounds."),
    _lib(561, "Peak-Sundering Seal", "earth", "⛰️", "armor_ignore", 0.38, 0, 4, "fist", 44, "iron_mountain", 3,
         "To the elders of Iron Mountain, armor is merely a smaller mountain — and every mountain has a fault line waiting for the right fist. Ignores 38% of the opponent's armor."),
    # ── Frozen Peak ❄️ ──
    _lib(562, "Snowdrift Step", "ice", "❄️", "evasion", 0.14, 0, 1, "body", 18, "frozen_peak", 1,
         "The novice of the Frozen Peak learns to cross fresh snow without leaving a single print — and an enemy cannot strike what leaves no trace. +14% evasion in all rounds."),
    _lib(563, "Frost That Seeps Through Iron", "ice", "🧊", "armor_ignore", 0.28, 0, 2, "body", 30, "frozen_peak", 2,
         "No breastplate has ever stopped winter: the cold of this art slips between rivets and settles in the marrow beneath the steel. Ignores 28% of the opponent's armor."),
    _lib(564, "Everfrost Bastion", "ice", "🏔️", "damage_reduce", 0.35, 0, 4, "body", 44, "frozen_peak", 3,
         "The core disciple no longer wears the cold — he becomes it, a wall of ancient ice that swallows the fury of every blow in perfect silence. Reduces damage taken by 35% in all rounds."),
    # ── Thousand Bloom 🌸 ──
    _lib(565, "Thorn Vine Lash", "earth", "🌿", "damage_mult", 0.16, 0, 1, "dao", 18, "thousand_bloom", 1,
         "Even the gentlest garden keeps thorns: the herbalist snaps a spirit vine like a whip, and its barbs remember every hand that ever plucked without asking. +16% damage in all rounds."),
    _lib(566, "Veil of a Hundred Petals", "earth", "🌸", "damage_reduce", 0.26, 0, 2, "dao", 30, "thousand_bloom", 2,
         "A hundred petals rise in a slow spiral around the cultivator, and every blade that enters the veil arrives softer than it left. Reduces damage taken by 26% in all rounds."),
    _lib(567, "Withering Pollen Dao", "earth", "🥀", "armor_ignore", 0.38, 0, 4, "dao", 44, "thousand_bloom", 3,
         "The garden's deepest secret is not the bloom but the fading: a golden pollen drifts through any breastplate as if it were morning mist, aging the metal it touches. Ignores 38% of the opponent's armor."),
    # ── Silent Wind 🌬️ ──
    _lib(568, "Whispering Gale Edge", "wind", "🍃", "damage_mult", 0.16, 0, 1, "killing", 18, "silent_wind", 1,
         "The wind does not roar before it cuts; it whispers, and the cut is already done. +16% damage in all rounds."),
    _lib(569, "Hollow Breeze Piercer", "wind", "🌬️", "armor_ignore", 0.28, 0, 2, "killing", 30, "silent_wind", 2,
         "Armor guards against blades, not against the draft that slips through every seam. Your strikes ignore 28% of the enemy's armor."),
    _lib(570, "Formless Zephyr Veil", "wind", "🌫️", "evasion", 0.25, 0, 4, "killing", 44, "silent_wind", 3,
         "To strike the wind, one must first find it — and Yanshan's wind was never anywhere at all. +25% evasion in all rounds."),
    # ── Blazing Sun ☀️ ──
    _lib(571, "Molten Dawn Guard", "fire", "🌅", "damage_reduce", 0.16, 0, 1, "fist", 18, "blazing_sun", 1,
         "The forge teaches its first lesson at dawn: steel that endures the fire fears no hammer. Reduces damage taken by 16%."),
    _lib(572, "Smelting Ray Fist", "fire", "🔥", "armor_ignore", 0.28, 0, 2, "fist", 30, "blazing_sun", 2,
         "What is armor to Fenghuo but ore that has not yet met the furnace? Your strikes ignore 28% of the enemy's armor."),
    _lib(573, "Zenith Supernova Fist", "fire", "☀️", "damage_mult", 0.85, 3, 4, "fist", 44, "blazing_sun", 3,
         "Three breaths to gather the noon sun into a single knuckle — then the sky itself goes blind. +85% damage on round 3 only."),
    # ── Abyssal Depths 💀 ──
    _lib(574, "Umbral Tide Drift", "chaos", "🌑", "evasion", 0.14, 0, 1, "killing", 18, "abyssal_depths", 1,
         "In the black water of the abyss, the disciple learns to be current, not prey — where the blade falls, only darkness remains. +14% evasion in all rounds."),
    _lib(575, "Hunger of the Deep", "chaos", "🕳️", "damage_mult", 0.28, 0, 2, "killing", 30, "abyssal_depths", 2,
         "The abyss does not strike out of anger; it strikes out of hunger, and hunger never tires. +28% damage in all rounds."),
    _lib(576, "Bulwark of Devoured Souls", "chaos", "👁️", "damage_reduce", 0.35, 0, 4, "killing", 44, "abyssal_depths", 3,
         "Every soul the abyss has swallowed becomes a silent sentinel between you and the world's wrath. Reduces damage taken by 35%."),
]

TECHNIQUES = TECHNIQUES + SECT_LIBRARY_TEC1

# ── TEC-3 — As Duas Estantes Seladas: Ancião 传功 + Oculta 秘传 (580-598) ──────
# 1 arte por câmara por casa (Lei §3: profundidade > variedade — 1, não 5).
# A câmara do Ancião é o que a casa CONFIA; a Oculta é o que a casa NÃO VENDE
# (custo 0 — paga-se com a Prova da Sucessão + karma alinhado, Lei §4/§12).
#
# A RÉGUA IN-BAND (Lei §12 — a exclusividade é o prêmio, zero power creep),
# medida contra o catálogo VIVO em prod (28/07) e não contra o spec:
#   · degraus legados da mesma casa: elder qi52/R5 valor 0.28-0.55 · heir
#     qi68/R7 valor 0.35-0.70 → as artes novas ficam DENTRO dessas duas faixas;
#   · tetos globais do catálogo por efeito (o que já existe no jogo):
#     damage_mult 2.5 · damage_reduce 0.80 · armor_ignore 0.65 · evasion 0.60
#     → nenhuma das 18 chega perto de nenhum teto;
#   · `dodge` fica de fora de propósito: dodge > 0 é binário 50% no engine, não
#     uma escala — subir "o número" ali não significaria nada.
# element/intent_affinity COPIAM a casa (nunca inventar par novo — a convenção
# 500-576 é 100% consistente por casa). effect_round 0 = todas as rodadas (a
# exceção de burst 0.85/rodada-3 é do tier 3 e não se repete aqui).
# ids NÃO-contíguos de propósito (580-588 · 590-598): 589 fica de reserva.
SECT_LIBRARY_TEC3 = [
    # ── Azure Cloud ☁️ (wind / sword) ──
    _lib(580, "Sky-Severing Cloud Decree", "wind", "⚡", "armor_ignore", 0.44, 0, 5, "sword", 52, "azure_cloud", 4,
         "What the Elder signs with the sword, the heavens countersign: a single decree drawn across the sky, and the guard that was there is simply no longer part of the world. Ignores 44% of the enemy's armor."),
    _lib(590, "Bai's Unwritten Cloud", "wind", "🌥️", "damage_mult", 0.66, 0, 7, "sword", 68, "azure_cloud", 5,
         "Founder Bai never set this form to paper — he said a cloud that can be drawn is already a cloud that can be cut. Only the Successor is shown it, once, and must remember. +66% damage in all rounds."),
    # ── Eternal Flame 🔥 (fire / dao) ──
    _lib(581, "Ninth Refinement Blaze", "fire", "🕯️", "damage_mult", 0.48, 0, 5, "dao", 52, "eternal_flame", 4,
         "Eight refinements make a pill; the ninth makes a weapon. The Elder feeds their own dao into the furnace and strikes with what comes out. +48% damage in all rounds."),
    _lib(591, "Ash of the First Cauldron", "fire", "⚱️", "damage_reduce", 0.52, 0, 7, "dao", 68, "eternal_flame", 5,
         "A pinch of ash from the cauldron that started the house, kept for a thousand years. Worn on the skin, it remembers every fire it has already survived. Reduces damage taken by 52%."),
    # ── Jade Harmony 🪷 (earth / body) ──
    _lib(582, "Unbroken Jade Accord", "earth", "🛡️", "damage_reduce", 0.42, 0, 5, "body", 52, "jade_harmony", 4,
         "The Elder does not refuse the blow — they agree with it, and an agreement cannot be broken by force. Reduces damage taken by 42%."),
    _lib(592, "Mercy That Outlasts the Sword", "earth", "🪷", "damage_reduce", 0.55, 0, 7, "body", 68, "jade_harmony", 5,
         "The house's deepest secret is not a technique but a vow: harm nothing that can still be spared, and nothing that strikes you will find a place to land. Reduces damage taken by 55%."),
    # ── Iron Mountain 🏔️ (earth / fist) ──
    _lib(583, "Ten Thousand Catty Descent", "earth", "🔨", "damage_mult", 0.48, 0, 5, "fist", 52, "iron_mountain", 4,
         "The Elder does not throw the fist. They let go of it, and the mountain does the rest. +48% damage in all rounds."),
    _lib(593, "The Peak Answers Only Once", "earth", "🗻", "damage_mult", 0.68, 0, 7, "fist", 68, "iron_mountain", 5,
         "The Successor learns the name the founder carved into the summit stone. Speak it, and for one breath you are not standing on the mountain — you are the mountain. +68% damage in all rounds."),
    # ── Frozen Peak ❄️ (ice / body) ──
    _lib(584, "Winter Without Thaw", "ice", "🌨️", "damage_reduce", 0.43, 0, 5, "body", 52, "frozen_peak", 4,
         "The Elder's cold no longer waits for the season: it simply decides that spring will not be arriving here. Reduces damage taken by 43%."),
    _lib(594, "Glacier That Remembers the Sea", "ice", "🧊", "armor_ignore", 0.54, 0, 7, "body", 68, "frozen_peak", 5,
         "Before the peak froze it was water, and water has been inside everything. The Successor's strike finds the seam it knew a thousand years ago. Ignores 54% of the enemy's armor."),
    # ── Thousand Bloom 🌸 (earth / dao) ──
    _lib(585, "Garden of Ten Thousand Turnings", "earth", "🍀", "evasion", 0.30, 0, 5, "dao", 52, "thousand_bloom", 4,
         "The Elder walks a path only the garden knows, and the garden rearranges itself politely behind them. +30% evasion in all rounds."),
    _lib(595, "The Seed Kept From Every Harvest", "earth", "🌾", "damage_reduce", 0.52, 0, 7, "dao", 68, "thousand_bloom", 5,
         "Every generation set one seed aside and never planted it. The Successor carries it, and while it is unplanted nothing in this world is finished with them. Reduces damage taken by 52%."),
    # ── Silent Wind 🌬️ (wind / killing) ──
    _lib(586, "Edge That Precedes the Sound", "wind", "🗡️", "evasion", 0.31, 0, 5, "killing", 52, "silent_wind", 4,
         "The Elder arrives a half-breath before the noise of arriving; blades sent to where they are keep finding where they were. +31% evasion in all rounds."),
    _lib(596, "Name Erased From the Wind", "wind", "🫥", "armor_ignore", 0.56, 0, 7, "killing", 68, "silent_wind", 5,
         "The Successor gives up their name to the mountain wind. What has no name has no shape, and what has no shape was never outside the armor to begin with. Ignores 56% of the enemy's armor."),
    # ── Blazing Sun ☀️ (fire / fist) ──
    _lib(587, "Anvil of the Standing Noon", "fire", "🔆", "armor_ignore", 0.45, 0, 5, "fist", 52, "blazing_sun", 4,
         "The Elder holds the noon still above the forge and works the enemy's guard like ore that has not yet decided to be a blade. Ignores 45% of the enemy's armor."),
    _lib(597, "The Sun Sets For No House But Ours", "fire", "🌞", "damage_mult", 0.67, 0, 7, "fist", 68, "blazing_sun", 5,
         "Fenghuo's oldest boast, and the only art that earns it: for one exchange the Successor's fist keeps the hour the rest of the world has already lost. +67% damage in all rounds."),
    # ── Abyssal Depths 💀 (chaos / killing) ──
    _lib(588, "Covenant of the Drowned Elder", "chaos", "⚓", "armor_ignore", 0.46, 0, 5, "killing", 52, "abyssal_depths", 4,
         "Every Elder of the Abyss signs the same contract with what lies beneath, and the abyss keeps its half: nothing worn on the surface will protect them from you. Ignores 46% of the enemy's armor."),
    _lib(598, "What the Abyss Kept For Its Heir", "chaos", "👁️", "damage_mult", 0.68, 0, 7, "killing", 68, "abyssal_depths", 5,
         "The deep does not give; it lends, and it lends only to the one who has already fallen far enough to be trusted. The Successor collects. +68% damage in all rounds."),
]

TECHNIQUES = TECHNIQUES + SECT_LIBRARY_TEC3

FTUE_TECHNIQUES = [
    _sig(45, "Beggar's Palm", "universal", "🖐️", "damage_mult", 0.15, 0, 0, "fist", 8, "ftue_mendigo",
         "The Old Beggar's only lesson — one honest palm, thrown with the whole body behind it. +15% damage in all rounds."),
]
TECHNIQUES = TECHNIQUES + FTUE_TECHNIQUES

# ── TEC-4 — Legacy Caves 传承洞: as 5 artes de legado (600-604) ────────────────
# 1 arte por NPC lendário do world_lore §5 — a fonte MAIS RARA do jogo (Lei
# §12): só sai da Gruta do Legado (roll LGC_ART_CHANCE + pity no 3º clear).
# `sect_key="legacy_<npc>"` é o que as mantém FORA de todos os pools de drop
# (recon 2026-07-30: a ÚNICA exclusão viva é sect_key IS NOT NULL — nenhum
# faucet filtra library_tier; precedente inerte: FTUE id 45 acima).
# `library_tier` fica NULL de propósito: não são artes de estante, logo o
# lockout cross-sect `is_library_locked` NUNCA as tranca (elas são do PORTADOR,
# não de uma casa).
# RÉGUA IN-BAND (banda t5 heir do catálogo vivo: qi 68 · R7 · 0.52-0.68; tetos
# globais por efeito: dm 2.5 · dr 0.80 · ai 0.65 · ev 0.60 — nenhuma passa
# nenhum teto; dodge excluído, é binário no engine). 599 fica livre de reserva.
LEGACY_CAVE_TECHS = [
    _sig(600, "Last Thunder", "wind", "⛈️", "damage_mult", 0.66, 0, 7, "sword", 68, "legacy_tianlei",
         "Shen Tianlei met his tribulation standing, and the bolt that killed him never finished falling. The cave keeps it; the worthy borrow it. +66% damage in all rounds."),
    _sig(601, "Nine Transformations Body", "earth", "🗿", "damage_reduce", 0.55, 0, 7, "body", 68, "legacy_gushan",
         "Tie Gushan tempered his body under frozen waterfalls for five hundred years without a single pill. The ninth transformation is not hardness — it is patience made flesh. Reduces damage taken by 55%."),
    _sig(602, "Pill Beyond Tribulation", "earth", "🌸", "armor_ignore", 0.55, 0, 7, "dao", 68, "legacy_wuchen",
         "Hua Wuchen refines what the Heavenly Dao cannot tax. Crushed on the fist, her essence dissolves wards, armor and certainty alike. Ignores 55% of the enemy's armor."),
    _sig(603, "Void Walk", "universal", "🌀", "evasion", 0.42, 0, 7, "dao", 68, "legacy_wuming",
         "Yun Wuming stepped between the planes and forgot to come back. Learn the first of his steps and the world will keep losing track of where you are. +42% evasion in all rounds."),
    _sig(604, "Blood Sutra", "chaos", "🩸", "damage_mult", 0.68, 0, 7, "killing", 68, "legacy_xueye",
         "Li Xueye wrote it in the only ink that never dries. Every verse recited turns the enemy's vitality against them. +68% damage in all rounds."),
]
TECHNIQUES = TECHNIQUES + LEGACY_CAVE_TECHS

# ── TEC-5 — O COFRE PROIBIDO 禁库: as 3 artes do Caminho Proibido (605-607) ────
# A estante 6 da Biblioteca, SÓ da `abyssal_depths` (as outras 8 casas não a
# têm). Não se compram: exigem posto heir + `path == "demonic"` + karma ALINHADO
# >= FP_KARMA_MIN (500, o número da DIVERGÊNCIA) + o registro do Rito do
# Coração-Demônio. E cada USO cobra karma (`forbidden_tech_use` −20) + anos do
# Mar de Longevidade, no settle (core/forbidden_path_engine.py).
#
# RÉGUA IN-BAND (medida no catálogo VIVO, não no spec — lição QoL-relatos "contar
# tiers nas SEEDS"): a banda t5 heir é qi 68 / R7 / dm 0.66-0.68; os tetos por
# efeito são dm 2.5 · dr 0.80 · ai 0.65 · ev 0.60, e já existe arte a qi 80 /
# R8 (o burst 2.5) — logo qi 80 / R8 NÃO é escala nova, é o topo existente.
# A banda t6 fica dm 0.72-0.77 sustentado ou <= 2.2 de burst na rodada 1.
#
# EIXO dm/burst APENAS, de propósito: `damage_mult` é o único canal SEM clamp.
# `damage_reduce` satura no teto global 0.70 (somado com têmpera/path/pílula),
# `armor_ignore` efetivo nunca passa 0.35 e `evasion` é pinçada em 0.90 — uma
# arte proibida nesses eixos cobraria karma e ANOS por um bônus que o modelo
# descarta (Lei §1: pagar por nada é pior que não ter).
#
# `sect_key="abyssal_depths"` mantém-nas fora de TODOS os pools de drop (a
# única exclusão viva é sect_key IS NOT NULL) e `library_tier=6` dá-lhes o
# lockout cross-sect de graça (>= 3): a REDENÇÃO tranca o Cofre.
# Nomes verificados contra o catálogo (TechniqueCatalog.name é UNIQUE e o
# runner é insert-only: um nome repetido mata TODO o seed no boot) — "Soul
# Devourer" (id 12) e "Demonic Devourer" (543) já existem, por isso a arte de
# Xuèyè leva o NOME DELA e não colide em nenhuma língua.
FORBIDDEN_VAULT_TECHS = [
    _lib(605, "Blood Night Devouring Art", "chaos", "🩸", "damage_mult", 0.77, 0, 8, "killing", 80, "abyssal_depths", 6,
         "The second art Li Xueye wrote, and the one no cave was allowed to keep: what enters the enemy is not force but appetite. Every exchange feeds on the cultivation base they spent a lifetime gathering. +77% damage in all rounds."),
    _lib(606, "Nine Deaths, One Breath", "chaos", "💀", "damage_mult", 2.20, 1, 8, "killing", 80, "abyssal_depths", 6,
         "The Abyss lends nine deaths and asks for one breath in return. Everything the cultivator has — years, name, the road still ahead — is spent in the opening instant. +220% damage on round 1."),
    _lib(607, "The Abyss Wears Your Name", "chaos", "👁️", "damage_mult", 0.73, 0, 8, "killing", 80, "abyssal_depths", 6,
         "There is no borrowing left at this depth: the deep stops answering to the Heir and starts answering AS them. Nothing that stands in front of you is being struck by a person any more. +73% damage in all rounds."),
]
TECHNIQUES = TECHNIQUES + FORBIDDEN_VAULT_TECHS

# Dao requirements to apply to existing DB rows (id → {dao_law_id, dao_insight})
DAO_REQUIREMENTS_PATCH = {
    9:  {"required_dao_law_id": 1, "required_dao_insight": 3},
    13: {"required_dao_law_id": 3, "required_dao_insight": 3},
    10: {"required_dao_law_id": 2, "required_dao_insight": 5},
    12: {"required_dao_law_id": 4, "required_dao_insight": 7},
}


async def run_combat_seeds(session):
    existing_ids = set((await session.execute(select(TechniqueCatalog.id))).scalars().all())
    added = 0
    for tech_data in TECHNIQUES:
        # v15.1 — inject qi_cost from QI_COSTS map (default 10 if missing)
        # v15.2 — inject intent_affinity from INTENT_AFFINITIES map (NULL for non-combat)
        tech_data_with_meta = {
            **tech_data,
            # v16.4c — sect signature techs (id >= 500) carry their own qi_cost/
            # intent in the dict; the maps stay the source of truth for ids 1-30.
            # For existing techs the id IS in the map so behaviour is unchanged.
            "qi_cost": QI_COSTS.get(tech_data["id"], tech_data.get("qi_cost", 10)),
            "intent_affinity": INTENT_AFFINITIES.get(tech_data["id"], tech_data.get("intent_affinity")),
        }
        if tech_data["id"] not in existing_ids:
            session.add(TechniqueCatalog(**tech_data_with_meta))
            added += 1
    if added:
        logger.info("⚔️ Seeded %d new techniques (skipped %d existing)", added, len(TECHNIQUES) - added)

    # Patch Dao requirements onto existing techniques that were seeded before this column existed
    for tech_id, patch in DAO_REQUIREMENTS_PATCH.items():
        if tech_id in existing_ids:
            await session.execute(
                update(TechniqueCatalog)
                .where(TechniqueCatalog.id == tech_id)
                .values(**patch)
            )

    # v15.1 — patch qi_cost on existing rows (technique balance for turn-based duels)
    for tech_id, qi_cost in QI_COSTS.items():
        await session.execute(
            update(TechniqueCatalog)
            .where(TechniqueCatalog.id == tech_id)
            .values(qi_cost=qi_cost)
        )

    # v15.2 — patch intent_affinity on every catalog row (re-applies on each
    # boot so re-balancing the map ships without a fresh migration). Missing
    # entries stay NULL — they are meditation/interior techs and never fight.
    for tech_id, intent in INTENT_AFFINITIES.items():
        await session.execute(
            update(TechniqueCatalog)
            .where(TechniqueCatalog.id == tech_id)
            .values(intent_affinity=intent)
        )

    # TEC-1 — force-sync das colunas de estante nas artes da Biblioteca
    # (re-aplica a cada boot: mudar um knob LIB_*_CP ou promover uma arte de
    # estante ship a sem migration — padrão QI_COSTS/INTENT_AFFINITIES acima).
    # Em main é inerte na prática (colunas dormantes, flag OFF).
    from core.sect_library_engine import tier_default_cp as _lib_tier_cp
    for tech_data in SECT_LIBRARY_TEC1 + SECT_LIBRARY_TEC3 + FORBIDDEN_VAULT_TECHS:
        await session.execute(
            update(TechniqueCatalog)
            .where(TechniqueCatalog.id == tech_data["id"])
            .values(
                library_tier=tech_data["library_tier"],
                library_cp_cost=_lib_tier_cp(tech_data["library_tier"]),
                sect_key=tech_data["sect_key"],
            )
        )

    # TEC-4 — force-sync do sect_key das artes de legado (a coluna que as
    # mantém FORA dos pools de drop; re-aplica a cada boot — padrão acima).
    for tech_data in LEGACY_CAVE_TECHS:
        await session.execute(
            update(TechniqueCatalog)
            .where(TechniqueCatalog.id == tech_data["id"])
            .values(sect_key=tech_data["sect_key"])
        )

    await session.commit()
