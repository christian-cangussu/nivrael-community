"""Seeds for the Faction System — factions, quests, shop items."""

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import FactionCatalog, FactionQuestCatalog, FactionShopItem

logger = logging.getLogger(__name__)

# ── Factions ────────────────────────────────────────────────────────

FACTIONS = [
    {
        "id": 1,
        "name": "Celestial",
        "emoji": "☀️",
        "bonuses": {
            "dao_bonus": 0.20,
            "foundation_bonus": 0.15,
        },
        "description": "The Celestial Faction walks the righteous path. Members gain enhanced Dao comprehension and stronger Foundations.",
    },
    {
        "id": 2,
        "name": "Demonic",
        "emoji": "👹",
        "bonuses": {
            "combat_damage_bonus": 0.30,
            "pill_potency_bonus": 0.20,
        },
        "description": "The Demonic Faction embraces raw power. Members deal devastating combat damage and brew potent pills.",
    },
]

# ── Faction Quests ──────────────────────────────────────────────────
# Both factions share the same quest templates (mirrored with faction_id)

_QUEST_TEMPLATES = [
    # -- Dungeon quests --
    {
        "name": "Clear Mortal Catacombs Floor 5",
        "quest_type": "dungeon",
        "target": {"dungeon_id": 1, "floor": 5, "count": 1},
        "reward_rep": 50,
        "reward_items": {"spirit_stones": 5000},
        "min_realm": 0,
        "cooldown_hours": 24,
        "emoji": "💀",
        "description": "Reach floor 5 of the Mortal Catacombs. (Any difficulty)",
    },
    {
        "name": "Complete Spirit Mine (Hard)",
        "quest_type": "dungeon",
        # BUG [jogador] 2026-08-11: desde 2026-04-02 este target apontava dungeon_id 2
        # — mas a 2 é "Haunted Mines"; a "Spirit Mine" é a id 9. O matcher exige
        # igualdade exata de dungeon_id, então completar a Spirit Mine (hard)
        # NUNCA progrediu a quest (e completar a Haunted Mines progredia).
        # O seed runner reescreve rows existentes a cada boot ⇒ propaga sozinho.
        "target": {"dungeon_id": 9, "difficulty": "hard", "count": 1},
        "reward_rep": 100,
        "reward_items": {"spirit_stones": 10000},
        "min_realm": 2,
        "cooldown_hours": 48,
        "emoji": "⛏️",
        "description": "Complete the Spirit Mine on Hard difficulty.",
    },
    {
        "name": "Conquer 3 Different Dungeons",
        "quest_type": "dungeon_any",
        "target": {"count": 3},
        "reward_rep": 80,
        "reward_items": {"spirit_stones": 8000},
        "min_realm": 1,
        "cooldown_hours": 48,
        "emoji": "🗺️",
        "description": "Complete any 3 different dungeons. (Any difficulty)",
    },
    # -- Combat quests --
    {
        "name": "Win 5 Arena Battles",
        "quest_type": "pvp_win",
        "target": {"count": 5},
        "reward_rep": 40,
        "reward_items": {"spirit_stones": 3000},
        "min_realm": 1,
        "cooldown_hours": 24,
        "emoji": "⚔️",
        "description": "Win 5 PvP arena battles.",
    },
    {
        "name": "Defeat 10 NPCs",
        "quest_type": "npc_kill",
        "target": {"count": 10},
        "reward_rep": 30,
        "reward_items": {"spirit_stones": 2000, "herbs": [{"id": 1, "qty": 3}]},
        "min_realm": 0,
        "cooldown_hours": 24,
        "emoji": "👊",
        "description": "Defeat 10 NPC cultivators.",
    },
    # Review adversarial 03/08 — esta era a MESMA classe de defeito do lote das
    # quests de seita, e a pior versão dela: `spar_win` só é alimentado pelo
    # settle de um duelo PvP consentido entre dois jogadores vivos
    # (core/pvp_duel_settle.py:179/184), `accept_quest` recusa re-aceitar uma
    # quest já ativa e NÃO existe abandono nem expiração — logo, aceite uma vez
    # num servidor sem parceiros, a linha ficava 0/1 para SEMPRE, ocupando o
    # slot. Trocado para `pvp_win`, que a arena também alimenta
    # (core/arena_duel_settle.py:305) e a arena tem fallback de NPC ao expirar
    # a fila ⇒ solo-completável em qualquer população. Ao contrário do runner
    # das quests, ESTE runner reescreve todos os campos das rows existentes
    # (linhas ~396-405), logo a mudança propaga sem bloco de SYNC.
    {
        "name": "Win a Duel in the Arena",
        "quest_type": "pvp_win",
        "target": {"count": 1},
        "reward_rep": 25,
        "reward_items": {"spirit_stones": 2000},
        "min_realm": 1,
        "cooldown_hours": 24,
        "emoji": "🤺",
        "description": "Win a single arena duel.",
    },
    # -- Alchemy quests --
    {
        "name": "Craft 5 Pills",
        "quest_type": "craft_pill",
        "target": {"count": 5},
        "reward_rep": 40,
        "reward_items": {"spirit_stones": 4000},
        "min_realm": 1,
        "cooldown_hours": 24,
        "emoji": "💊",
        "description": "Successfully craft 5 pills of any type.",
    },
    {
        "name": "Craft a High-Quality Pill",
        "quest_type": "craft_pill_hq",
        "target": {"count": 1},
        "reward_rep": 60,
        "reward_items": {"spirit_stones": 6000},
        "min_realm": 2,
        "cooldown_hours": 48,
        "emoji": "✨",
        "description": "Craft a pill with quality bonus.",
    },
    # -- Gathering quests --
    {
        "name": "Gather 20 Herbs",
        "quest_type": "gather_herb",
        "target": {"count": 20},
        "reward_rep": 35,
        "reward_items": {"spirit_stones": 3000},
        "min_realm": 0,
        "cooldown_hours": 24,
        "emoji": "🌿",
        "description": "Gather 20 herbs from any source.",
    },
    {
        "name": "Collect 10 Ores",
        "quest_type": "gather_ore",
        "target": {"count": 10},
        "reward_rep": 35,
        "reward_items": {"spirit_stones": 3000},
        "min_realm": 1,
        "cooldown_hours": 24,
        "emoji": "🪨",
        "description": "Collect 10 ores from any source.",
    },
    # -- Beast quests --
    {
        "name": "Complete 2 Beast Expeditions",
        "quest_type": "expedition",
        "target": {"count": 2},
        "reward_rep": 45,
        "reward_items": {"spirit_stones": 4000},
        "min_realm": 1,
        "cooldown_hours": 48,
        "emoji": "🐉",
        "description": "Complete 2 beast expeditions.",
    },
    # -- Boss quests --
    {
        "name": "Deal Damage to World Boss",
        "quest_type": "boss_hit",
        "target": {"count": 1},
        "reward_rep": 70,
        "reward_items": {"spirit_stones": 7000},
        "min_realm": 2,
        "cooldown_hours": 72,
        "emoji": "🐲",
        "description": "Deal damage to the World Boss.",
    },
]

# Generate quest IDs: faction 1 gets 1-12, faction 2 gets 13-24
FACTION_QUESTS = []
_id = 1
for faction_id in (1, 2):
    for tmpl in _QUEST_TEMPLATES:
        q = dict(tmpl)
        q["id"] = _id
        q["faction_id"] = faction_id
        FACTION_QUESTS.append(q)
        _id += 1

# ── Shop Items ──────────────────────────────────────────────────────

SHOP_ITEMS = [
    # ═══════════════════════════════════════════════════════════════════════
    # CELESTIAL FACTION SHOP (☀️)
    # Tier 1 — Disciple (500 rep) — Grade 2 gear, T1 technique, Realm 3
    # Tier 2 — Elder (2000 rep)   — Grade 3 gear, T2 technique, Realm 4
    # Tier 3 — Core Member (5000) — Grade 4 gear, Realm 5
    # Tier 4 — Patriarch (15000)  — Grade 5 gear, T3 technique, Realm 7
    # ═══════════════════════════════════════════════════════════════════════

    # ── Tier 1: Disciple ──────────────────────────────────────────────────
    {"id": 1, "faction_id": 1, "item_type": "technique", "emoji": "📜",
     "name": "Radiant Guard Scroll",
     "item_data": {"technique_id": 19},
     "rep_cost": 200, "min_rank": "Disciple",
     "description": "☀️ Technique: -15% damage all rounds. Realm 3+. (Grade 2)"},

    {"id": 2, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Radiant Silk Robe",
     "item_data": {"artifact_id": 26},
     "rep_cost": 300, "min_rank": "Disciple",
     "description": "☀️ Armor G2: SS 250, Perc 30. Realm 3+."},

    {"id": 3, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Purifier's Blade",
     "item_data": {"artifact_id": 27},
     "rep_cost": 350, "min_rank": "Disciple",
     "description": "☀️ Weapon G2: BP 300, SS 50. Realm 3+."},

    {"id": 4, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Halo of Clarity",
     "item_data": {"artifact_id": 28},
     "rep_cost": 250, "min_rank": "Disciple",
     "description": "☀️ Accessory G2: Perc 40, Luck 20, SS 30. Realm 3+."},

    # ── Tier 2: Elder ─────────────────────────────────────────────────────
    {"id": 5, "faction_id": 1, "item_type": "technique", "emoji": "📜",
     "name": "Heaven's Mandate Scroll",
     "item_data": {"technique_id": 20},
     "rep_cost": 1000, "min_rank": "Elder",
     "description": "☀️ Technique: -30% damage all rounds. Realm 4+. (Grade 3)"},

    {"id": 6, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Heaven Warden Plate",
     "item_data": {"artifact_id": 29},
     "rep_cost": 1200, "min_rank": "Elder",
     "description": "☀️ Armor G3: SS 500, BP 120, Perc 40. Realm 4+."},

    {"id": 7, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Celestial Arbiter Sword",
     "item_data": {"artifact_id": 30},
     "rep_cost": 1400, "min_rank": "Elder",
     "description": "☀️ Weapon G3: BP 580, SS 80, Perc 25. Realm 4+."},

    # ── Tier 3: Core Member ───────────────────────────────────────────────
    {"id": 8, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Seraph's Vestment",
     "item_data": {"artifact_id": 31},
     "rep_cost": 3000, "min_rank": "Core Member",
     "description": "☀️ Armor G4: SS 900, BP 250, Perc 60. Realm 5+."},

    {"id": 9, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Sword of the Morning Star",
     "item_data": {"artifact_id": 32},
     "rep_cost": 3500, "min_rank": "Core Member",
     "description": "☀️ Weapon G4: BP 1050, SS 200, Perc 40. Realm 5+."},

    {"id": 10, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Mandate of Heaven Ring",
     "item_data": {"artifact_id": 33},
     "rep_cost": 2500, "min_rank": "Core Member",
     "description": "☀️ Accessory G4: Perc 100, Luck 80, SS 150. Realm 5+."},

    # ── Tier 4: Patriarch ─────────────────────────────────────────────────
    {"id": 11, "faction_id": 1, "item_type": "technique", "emoji": "📜",
     "name": "Divine Judgment Scroll",
     "item_data": {"technique_id": 21},
     "rep_cost": 5000, "min_rank": "Patriarch",
     "description": "☀️ LEGENDARY Technique: 2.8x damage round 1. Realm 6+."},

    {"id": 12, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Empyrean Holy Armor",
     "item_data": {"artifact_id": 34},
     "rep_cost": 8000, "min_rank": "Patriarch",
     "description": "☀️ Armor G5: SS 1600, BP 450, Perc 100. Realm 7+."},

    {"id": 13, "faction_id": 1, "item_type": "artifact", "emoji": "☀️",
     "name": "Blade of Ten Thousand Virtues",
     "item_data": {"artifact_id": 35},
     "rep_cost": 10000, "min_rank": "Patriarch",
     "description": "☀️ Weapon G5: BP 1800, SS 350, Perc 80. Realm 7+."},

    # ═══════════════════════════════════════════════════════════════════════
    # DEMONIC FACTION SHOP (👹)
    # ═══════════════════════════════════════════════════════════════════════

    # ── Tier 1: Disciple ──────────────────────────────────────────────────
    {"id": 14, "faction_id": 2, "item_type": "technique", "emoji": "📜",
     "name": "Blood Frenzy Scroll",
     "item_data": {"technique_id": 22},
     "rep_cost": 200, "min_rank": "Disciple",
     "description": "👹 Technique: +20% damage all rounds. Realm 3+. (Grade 2)"},

    {"id": 15, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Bloodweave Mantle",
     "item_data": {"artifact_id": 36},
     "rep_cost": 300, "min_rank": "Disciple",
     "description": "👹 Armor G2: SS 180, BP 80, Luck 20. Realm 3+."},

    {"id": 16, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Fanged Shadow Blade",
     "item_data": {"artifact_id": 37},
     "rep_cost": 350, "min_rank": "Disciple",
     "description": "👹 Weapon G2: BP 320, Luck 15. Realm 3+."},

    {"id": 17, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Skull Bone Talisman",
     "item_data": {"artifact_id": 38},
     "rep_cost": 250, "min_rank": "Disciple",
     "description": "👹 Accessory G2: BP 60, Luck 35, SS 20. Realm 3+."},

    # ── Tier 2: Elder ─────────────────────────────────────────────────────
    {"id": 18, "faction_id": 2, "item_type": "technique", "emoji": "📜",
     "name": "Soul Rend Scroll",
     "item_data": {"technique_id": 23},
     "rep_cost": 1000, "min_rank": "Elder",
     "description": "👹 Technique: Ignore 40% armor all rounds. Realm 4+. (Grade 3)"},

    {"id": 19, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Infernal Scale Mail",
     "item_data": {"artifact_id": 39},
     "rep_cost": 1200, "min_rank": "Elder",
     "description": "👹 Armor G3: SS 380, BP 200, Luck 30. Realm 4+."},

    {"id": 20, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Asura's Cleaver",
     "item_data": {"artifact_id": 40},
     "rep_cost": 1400, "min_rank": "Elder",
     "description": "👹 Weapon G3: BP 620, Luck 25. Realm 4+."},

    # ── Tier 3: Core Member ───────────────────────────────────────────────
    {"id": 21, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Abyssal Exoskeleton",
     "item_data": {"artifact_id": 41},
     "rep_cost": 3000, "min_rank": "Core Member",
     "description": "👹 Armor G4: SS 700, BP 350, Luck 50. Realm 5+."},

    {"id": 22, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Demonlord's Fang",
     "item_data": {"artifact_id": 42},
     "rep_cost": 3500, "min_rank": "Core Member",
     "description": "👹 Weapon G4: BP 1150, Luck 50. Realm 5+."},

    {"id": 23, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Ring of the Blood Pact",
     "item_data": {"artifact_id": 43},
     "rep_cost": 2500, "min_rank": "Core Member",
     "description": "👹 Accessory G4: BP 150, Luck 100, SS 80. Realm 5+."},

    # ── Tier 4: Patriarch ─────────────────────────────────────────────────
    {"id": 24, "faction_id": 2, "item_type": "technique", "emoji": "📜",
     "name": "Abyssal Annihilation Scroll",
     "item_data": {"technique_id": 24},
     "rep_cost": 5000, "min_rank": "Patriarch",
     "description": "👹 LEGENDARY Technique: 3.0x damage round 1. Realm 6+."},

    {"id": 25, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Nethervoid Warlord Armor",
     "item_data": {"artifact_id": 44},
     "rep_cost": 8000, "min_rank": "Patriarch",
     "description": "👹 Armor G5: SS 1300, BP 600, Luck 80. Realm 7+."},

    {"id": 26, "faction_id": 2, "item_type": "artifact", "emoji": "👹",
     "name": "Godslayer's Eclipse",
     "item_data": {"artifact_id": 45},
     "rep_cost": 10000, "min_rank": "Patriarch",
     "description": "👹 Weapon G5: BP 2000, Luck 80, SS 200. Realm 7+."},
]


async def run_faction_seeds(session: AsyncSession):
    """Seed factions, quests, and shop items."""

    # Factions
    existing_factions = set(
        (await session.execute(select(FactionCatalog.id))).scalars().all()
    )
    for f in FACTIONS:
        if f["id"] not in existing_factions:
            session.add(FactionCatalog(**f))
        else:
            # Update existing
            row = (await session.execute(
                select(FactionCatalog).where(FactionCatalog.id == f["id"])
            )).scalar_one()
            row.name = f["name"]
            row.emoji = f["emoji"]
            row.bonuses = f["bonuses"]
            row.description = f["description"]

    # Quests
    existing_quests = set(
        (await session.execute(select(FactionQuestCatalog.id))).scalars().all()
    )
    for q in FACTION_QUESTS:
        if q["id"] not in existing_quests:
            session.add(FactionQuestCatalog(**q))
        else:
            row = (await session.execute(
                select(FactionQuestCatalog).where(FactionQuestCatalog.id == q["id"])
            )).scalar_one()
            for k, v in q.items():
                if k != "id":
                    setattr(row, k, v)

    # Shop items
    existing_shop = set(
        (await session.execute(select(FactionShopItem.id))).scalars().all()
    )
    for s in SHOP_ITEMS:
        if s["id"] not in existing_shop:
            session.add(FactionShopItem(**s))
        else:
            row = (await session.execute(
                select(FactionShopItem).where(FactionShopItem.id == s["id"])
            )).scalar_one()
            for k, v in s.items():
                if k != "id":
                    setattr(row, k, v)

    await session.commit()
    logger.info("✅ Faction seeds applied (%d quests, %d shop items)",
                len(FACTION_QUESTS), len(SHOP_ITEMS))
