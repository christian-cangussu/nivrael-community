"""v15.1.4 — NPC archetype loadouts (5 archetypes × 3-5 techniques each).

Why a Python const and NOT a DB seed (Lei §5 — WIPE-friendly):

  * Launch will redesign the technique catalog and Intent system (v15.2)
    holistically. Adding a `npc_archetype_loadouts` JSONB table now would
    create wipe overhead: migration to drop, re-seed, re-key tech IDs.
  * NPC loadouts are pure runtime config — no player-facing state, no
    save/load contract. The const can be edited without DB rewrites.
  * Technique IDs reference the existing `techniques_catalog` which IS
    seeded — so the loadout table is the only thing that would be
    redundant. Const wins.

Five archetypes:

  | archetype       | realm tier | dao flavour       | techniques                       |
  |-----------------|------------|-------------------|----------------------------------|
  | bandit          | 0-2 low    | crude, scrappy    | Thunder Step, Celestial Palm,    |
  |                 |            |                   | Shadow Step                      |
  | sect_disciple   | 2-5 mid    | disciplined       | Dragon Fist, Iron Body, Frost    |
  |                 |            |                   | Shield, Void Slash               |
  | beast           | any        | feral raw damage  | Dragon Fist, Wind Walk, Phoenix  |
  |                 |            |                   | Strike, Soul Devourer            |
  | demon           | 5-8 high   | chaos + corruption| Void Slash, Soul Devourer,       |
  |                 |            |                   | Heaven Rend, Eternal Strike      |
  | boss            | scaled     | all-rounder       | Phoenix Strike, Absolute Defense,|
  |                 |            |                   | Eternal Strike, Boundless Evasion|

Stat scaling per archetype (multiplied on top of `generate_npc_fighter`
realm-based base BP/HP):

  bp_mult / hp_mult / qi_capacity_mult — relative to player at that realm
  Bosses get hp_mult=2.5 to make the fight last (turn-based UX).

Difficulty grade_mult applies on top per-technique:

  | difficulty   | grade_mult | corresponds to    |
  |--------------|------------|-------------------|
  | easy         | 1.0        | common  ⬜       |
  | normal       | 1.2        | refined 🟩       |
  | hard         | 1.5        | perfected 🟦     |
  | nightmare    | 2.0        | transcendent 🟪  |

NPC mastery_level defaults to 1 (Beginner, mult=1.0); difficulty climbs
the grade_mult curve instead of mastery, keeping the AI predictable.

`DUNGEON_BOSS_ARCHETYPE` maps each dungeon to its boss archetype. Default
heuristic for any dungeon NOT in the map: archetype derived from
`min_realm` tier.
"""

from __future__ import annotations

import random


# ── Technique IDs by archetype (combat techniques only, must exist in
# techniques_catalog seed) ───────────────────────────────────────────────

NPC_ARCHETYPES: dict[str, dict] = {
    "bandit": {
        "emoji": "🗡️",
        "name_key": "npc_archetype_bandit",
        # crude evasion + cheap palm; realm cap 2 (mortal/qi gathering)
        "technique_ids": [1, 4, 6],          # Thunder Step, Shadow Step, Celestial Palm
        "bp_mult": 0.95,
        "hp_mult": 1.0,
        "qi_capacity_mult": 0.8,
        "realm_floor": 0,
        "realm_ceiling": 2,
    },
    "sect_disciple": {
        "emoji": "📜",
        "name_key": "npc_archetype_sect_disciple",
        # disciplined: damage + defense + utility
        "technique_ids": [2, 3, 7, 5],       # Dragon Fist, Iron Body, Frost Shield, Void Slash
        "bp_mult": 1.05,
        "hp_mult": 1.1,
        "qi_capacity_mult": 1.0,
        "realm_floor": 2,
        "realm_ceiling": 5,
    },
    "beast": {
        "emoji": "🦁",
        "name_key": "npc_archetype_beast",
        # feral: heavy damage_mult + raw evasion
        "technique_ids": [2, 8, 10, 12],     # Dragon Fist, Wind Walk, Phoenix Strike, Soul Devourer
        "bp_mult": 1.15,                      # hits hard
        "hp_mult": 1.25,                      # tankier
        "qi_capacity_mult": 0.9,              # smaller pool — burns fast
        "realm_floor": 0,
        "realm_ceiling": 10,                  # beasts can scale to any realm
    },
    "demon": {
        "emoji": "👹",
        "name_key": "npc_archetype_demon",
        # chaos + armor pierce — anti-tank profile
        "technique_ids": [5, 12, 15, 17],    # Void Slash, Soul Devourer, Heaven Rend, Eternal Strike
        "bp_mult": 1.15,
        "hp_mult": 1.1,
        "qi_capacity_mult": 1.1,
        "realm_floor": 5,
        "realm_ceiling": 8,
    },
    "boss": {
        "emoji": "👑",
        "name_key": "npc_archetype_boss",
        # all-rounder + endurance: bosses survive turn-based fights longer
        "technique_ids": [10, 13, 17, 18],   # Phoenix Strike, Absolute Defense, Eternal Strike, Boundless Evasion
        "bp_mult": 1.30,
        "hp_mult": 2.50,                      # tanky — boss fights last ~6-9 rounds
        "qi_capacity_mult": 1.5,
        "realm_floor": 0,
        "realm_ceiling": 10,
    },
    # v16.4b — Sect Elder. The recruiter trial opponent. Disciplined
    # all-rounder (offense + defense + control), scaled to the cultivator's
    # OWN realm at `normal` difficulty so the trial is FAIR but not trivial
    # (Lei §1) — a prepared cultivator wins; an underprepared one is sent home
    # to a short cooldown, never soft-locked. Slightly tanky so the duel lasts
    # a handful of legible rounds.
    "elder": {
        "emoji": "🧙",
        "name_key": "npc_archetype_elder",
        "technique_ids": [2, 3, 7, 5, 17],   # Dragon Fist, Iron Body, Frost Shield, Void Slash, Eternal Strike
        "bp_mult": 1.05,
        "hp_mult": 1.60,
        "qi_capacity_mult": 1.20,
        "realm_floor": 0,
        "realm_ceiling": 10,
    },
}


# ── Difficulty → grade_mult curve ────────────────────────────────────────

DIFFICULTY_GRADE_MULT: dict[str, float] = {
    "easy":      1.0,   # common
    "normal":    1.2,   # refined
    "hard":      1.5,   # perfected
    "nightmare": 2.0,   # transcendent
}


# ── Dungeon → boss archetype mapping ─────────────────────────────────────
# Each dungeon's last floor (boss floor) spawns a duel against this
# archetype. Dungeons not in this map fall through to the realm-tier
# heuristic in `get_dungeon_boss_archetype`.

DUNGEON_BOSS_ARCHETYPE: dict[int, str] = {
    # Tier 1 (R0)
    1:  "bandit",          # Mortal Catacombs — undead/bandits
    6:  "beast",           # Misty Cave — wild beasts
    7:  "demon",           # Forgotten Tomb — undead demon
    8:  "beast",           # Bamboo Forest — beasts
    # Tier 2 (R1-2)
    9:  "bandit",          # Spirit Mine — bandit cartels
    10: "sect_disciple",   # Haunted Library — rogue scholar
    2:  "demon",           # Haunted Mines
    11: "beast",           # Underground River — aquatic beast
    # Tier 3 (R3-4)
    12: "beast",           # Phoenix Nest — fire beast
    3:  "demon",           # Nascent Void
    13: "beast",           # Dragon's Lair — dragon
    14: "sect_disciple",   # Sect Ruins — former sect master
    # Tier 4 (R5-6)
    15: "demon",           # Void Rift
    4:  "demon",           # Abyssal Rift
    16: "demon",           # Demon Palace
    17: "sect_disciple",   # Celestial Tower — celestial sect master
    # Tier 5 (R7-8)
    18: "boss",            # Primordial Abyss
    19: "boss",            # Tribulation Ground
    5:  "boss",            # Immortal Trial
    20: "boss",            # Immortal's Tomb
    # Tier 6 (R9-10)
    21: "boss",            # Chaos Realm
    22: "boss",            # Ancient Battlefield
    23: "boss",            # Dao Origin
}


def get_dungeon_boss_archetype(dungeon) -> str:
    """Pick the boss archetype for a dungeon. Falls back to realm tier.

    Pass a DungeonCatalog row (anything with `id` + `min_realm`). Uses
    DUNGEON_BOSS_ARCHETYPE first; if absent, derives from min_realm:
      R0-2 → bandit · R3-5 → sect_disciple · R6+ → demon · R7+ → boss.
    """
    dungeon_id = getattr(dungeon, "id", None)
    if dungeon_id and dungeon_id in DUNGEON_BOSS_ARCHETYPE:
        return DUNGEON_BOSS_ARCHETYPE[dungeon_id]
    realm = int(getattr(dungeon, "min_realm", 0) or 0)
    if realm >= 7:
        return "boss"
    if realm >= 5:
        return "demon"
    if realm >= 3:
        return "sect_disciple"
    return "bandit"


def get_dungeon_boss_difficulty(player_dungeon, default: str = "normal") -> str:
    """Use the player's chosen dungeon difficulty as the boss difficulty.

    Falls back to `normal` if no difficulty is set on the run.
    """
    d = getattr(player_dungeon, "difficulty", None) or default
    if d not in DIFFICULTY_GRADE_MULT:
        return default
    return d


def random_npc_name(archetype: str, lang: str = "pt") -> str:
    """Generate a flavour name for an NPC fighter card.

    Falls back to "Cultivator X" pattern if the name pool is exhausted.
    Random-seeded only — no persistence; cosmetic.
    """
    arch = NPC_ARCHETYPES.get(archetype, NPC_ARCHETYPES["bandit"])
    return f"{arch['emoji']} #{random.randint(100, 999)}"
