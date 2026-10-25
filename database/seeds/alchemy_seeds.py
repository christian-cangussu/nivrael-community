import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import HerbCatalog, PillCatalog, CauldronCatalog

logger = logging.getLogger(__name__)

HERBS = [
    {
        "id": 1,
        "name": "Qi Root Herb",
        "tier": 1,
        "description": "A humble root that pulses with primordial Qi. The foundation of all alchemy.",
        "base_price": 10,
        "emoji": "🌱",
    },
    {
        "id": 2,
        "name": "Spirit Grass",
        "tier": 2,
        "description": "Grass that grows only in places touched by the Dao. Emits a soft glow.",
        "base_price": 25,
        "emoji": "🌿",
    },
    {
        "id": 3,
        "name": "Foundation Lotus",
        "tier": 3,
        "description": "A rare lotus flower that strengthens any cultivator's foundation.",
        "base_price": 80,
        "emoji": "🪷",
    },
    {
        "id": 4,
        "name": "Soul Herb",
        "tier": 4,
        "description": "An ethereal herb that resonates with the soul. Only masters can harvest it.",
        "base_price": 200,
        "emoji": "👻",
    },
    {
        "id": 5,
        "name": "Breakthrough Flower",
        "tier": 5,
        "description": "The legendary flower that defies the Heavens. Said to bloom once every thousand years.",
        "base_price": 500,
        "emoji": "🌸",
    },
    {
        "id": 6,
        "name": "Azure Cloud Flower",
        "tier": 3,
        "description": "A flower that blooms above the clouds. Essential for clarity pills.",
        "base_price": 100,
        "emoji": "☁️",
    },
    {
        "id": 7,
        "name": "Dragon Blood Grass",
        "tier": 4,
        "description": "Grass nourished by ancient dragon blood. Amplifies combat pills.",
        "base_price": 250,
        "emoji": "🐉",
    },
    {
        "id": 8,
        "name": "Void Root",
        "tier": 5,
        "description": "A root that exists between dimensions. The rarest alchemical ingredient.",
        "base_price": 600,
        "emoji": "🌑",
    },
    {
        "id": 9,
        "name": "Moonlight Moss",
        "tier": 2,
        "description": "Moss that only grows under full moonlight. Used in healing recipes.",
        "base_price": 30,
        "emoji": "🌙",
    },
    {
        "id": 10,
        "name": "Phoenix Tear Petal",
        "tier": 5,
        "description": "A petal crystallized from the tears of a dying phoenix.",
        "base_price": 800,
        "emoji": "🔥",
    },
    {
        "id": 11,
        "name": "Frost Dew Herb",
        "tier": 3,
        "description": "An herb that secretes ice-cold dew. Used in defensive pills.",
        "base_price": 90,
        "emoji": "❄️",
    },
    {
        "id": 12,
        "name": "Spirit Vine",
        "tier": 1,
        "description": "A common vine that absorbs ambient spiritual energy.",
        "base_price": 15,
        "emoji": "🌿",
    },
    # v14.4 D-1c — endgame herbs for the Eternal Foundation Pill.
    # Both T5 + heavily gated drop sources (Mahayana Nightmare / WB top-3)
    # so the pill remains an authentic endgame chase, not a vending machine.
    {
        "id": 13,
        "name": "Eternal Spring Petal",
        "tier": 5,
        "description": "Petal of a flower that blooms only where an Immortal's essence was cremated. Drips with timeless sap.",
        "base_price": 1500,
        "emoji": "🌷",
    },
    {
        "id": 14,
        "name": "Heaven-Falling Star Dew",
        "tier": 5,
        "description": "A dewdrop said to fall from the heavens when a great cultivator dies — only those who topple world bosses witness its descent.",
        "base_price": 2000,
        "emoji": "✨",
    },
]

PILLS = [
    {
        "id": 1,
        "name": "Qi Gathering Pill",
        "ingredients": [{"herb_id": 1, "qty": 3}],
        "difficulty": 1,
        "effect_type": "cb_boost",
        "effect_value": 1.5,
        "duration_minutes": 60,
        "description": "Accelerates Qi absorption. +50% CB/tick for 1 hour.",
        "emoji": "💊",
        "min_realm": 0,
        "required_alchemy_tier": 1,
    },
    {
        "id": 2,
        "name": "Foundation Pill",
        "ingredients": [{"herb_id": 1, "qty": 2}, {"herb_id": 3, "qty": 1}],
        "difficulty": 2,
        "effect_type": "cb_instant",
        "effect_value": 1000.0,
        "duration_minutes": 0,
        "description": "Instantly grants 1000 CB. Strengthens the foundation.",
        "emoji": "🏯",
        "min_realm": 1,
        "required_alchemy_tier": 1,
    },
    {
        "id": 3,
        "name": "Soul Strength Pill",
        "ingredients": [{"herb_id": 2, "qty": 2}, {"herb_id": 4, "qty": 1}],
        "difficulty": 3,
        "effect_type": "soul_boost",
        "effect_value": 1.2,
        "duration_minutes": 120,
        "description": "Amplifies soul strength. +20% Soul Strength for 2 hours.",
        "emoji": "👻",
        "min_realm": 2,
        "required_alchemy_tier": 2,
    },
    {
        "id": 4,
        "name": "Breakthrough Pill",
        "ingredients": [{"herb_id": 3, "qty": 2}, {"herb_id": 5, "qty": 1}],
        "difficulty": 4,
        "effect_type": "breakthrough_boost",
        "effect_value": 1.3,
        "duration_minutes": 30,
        "description": "Reduces the breakthrough barrier. +30% success chance for 30min.",
        "emoji": "⚡",
        "min_realm": 3,
        "required_alchemy_tier": 2,
    },
    {
        "id": 5,
        "name": "Cleansing Pill",
        "ingredients": [{"herb_id": 1, "qty": 2}, {"herb_id": 9, "qty": 1}],
        "difficulty": 1,
        "effect_type": "purity_boost",
        "effect_value": 0.05,
        "duration_minutes": 0,
        "description": "Purifies impurities in the meridians. +5% Foundation Purity.",
        "emoji": "✨",
        "min_realm": 0,
        "required_alchemy_tier": 1,
    },
    {
        "id": 6,
        "name": "Qi Amass Pill",
        "ingredients": [{"herb_id": 1, "qty": 3}, {"herb_id": 12, "qty": 2}],
        "difficulty": 1,
        "effect_type": "qi_restore",
        "effect_value": 30.0,
        "duration_minutes": 0,
        "description": "Instantly restores 30 Qi points.",
        "emoji": "💧",
        "min_realm": 0,
        "required_alchemy_tier": 1,
    },
    {
        "id": 7,
        "name": "Heavenly Qi Restoration Pill",
        "ingredients": [{"herb_id": 3, "qty": 2}, {"herb_id": 6, "qty": 1}],
        "difficulty": 3,
        "effect_type": "qi_restore",
        "effect_value": 80.0,
        "duration_minutes": 0,
        "description": "Restores 80 Qi. Favored by dungeon explorers.",
        "emoji": "☁️",
        "min_realm": 3,
        "required_alchemy_tier": 2,
    },
    {
        "id": 8,
        "name": "Battle Fury Pill",
        "ingredients": [{"herb_id": 7, "qty": 2}, {"herb_id": 2, "qty": 1}],
        "difficulty": 3,
        "effect_type": "bp_boost",
        "effect_value": 1.3,
        "duration_minutes": 60,
        "description": "+30% Battle Power for 1 hour.",
        "emoji": "⚔️",
        "min_realm": 3,
        "required_alchemy_tier": 2,
    },
    {
        "id": 9,
        "name": "Soul Clarity Pill",
        "ingredients": [{"herb_id": 4, "qty": 2}, {"herb_id": 6, "qty": 1}],
        "difficulty": 3,
        "effect_type": "perception_boost",
        "effect_value": 1.25,
        "duration_minutes": 120,
        "description": "+25% Perception for 2 hours. Enhances Dao fragment chance.",
        "emoji": "👁️",
        "min_realm": 4,
        "required_alchemy_tier": 2,
    },
    {
        "id": 10,
        "name": "Time Dilation Pill",
        "ingredients": [{"herb_id": 5, "qty": 1}, {"herb_id": 8, "qty": 1}],
        "difficulty": 5,
        "effect_type": "cb_boost",
        "effect_value": 3.0,
        "duration_minutes": 30,
        "description": "+200% CB for 30 minutes. Extremely potent.",
        "emoji": "⏳",
        "min_realm": 6,
        "required_alchemy_tier": 3,  # antes: 1 — poder muito alto para tier 1
    },
    {
        "id": 11,
        "name": "Iron Skin Pill",
        "ingredients": [{"herb_id": 11, "qty": 3}, {"herb_id": 2, "qty": 2}],
        "difficulty": 2,
        "effect_type": "defense_boost",
        "effect_value": 1.2,
        "duration_minutes": 90,
        "description": "+20% damage reduction for 90 minutes.",
        "emoji": "🛡️",
        "min_realm": 2,
        "required_alchemy_tier": 1,
    },
    {
        "id": 12,
        "name": "Lucky Star Pill",
        "ingredients": [{"herb_id": 9, "qty": 2}, {"herb_id": 3, "qty": 1}],
        "difficulty": 2,
        "effect_type": "luck_boost",
        "effect_value": 1.15,
        "duration_minutes": 120,
        "description": "+15% Luck for 2 hours.",
        "emoji": "⭐",
        "min_realm": 1,
        "required_alchemy_tier": 1,
    },
    {
        "id": 13,
        "name": "Phoenix Rebirth Pill",
        "ingredients": [{"herb_id": 10, "qty": 2}, {"herb_id": 5, "qty": 1}, {"herb_id": 8, "qty": 1}],
        "difficulty": 5,
        "effect_type": "revive",
        "effect_value": 1.0,
        "duration_minutes": 0,
        "description": "Consume before combat: revive once at 50% HP if killed.",
        "emoji": "🔥",
        "min_realm": 7,
        "required_alchemy_tier": 4,  # tier 5 ingredients + revive effect = Grandmaster+
    },
    {
        "id": 14,
        "name": "Heaven Defying Pill",
        "ingredients": [{"herb_id": 10, "qty": 3}, {"herb_id": 8, "qty": 2}, {"herb_id": 5, "qty": 2}],
        "difficulty": 6,
        "effect_type": "cb_instant",
        "effect_value": 100000.0,
        "duration_minutes": 0,
        "description": "Grants 100,000 CB instantly. A pill that defies the heavens.",
        "emoji": "💜",
        "min_realm": 8,
        "required_alchemy_tier": 4,  # antes: 1 — 100k CB instantâneo exige Grandmaster+
    },
    # ── Tier 3 pills ──────────────────────────────────────────────────────────
    {
        "id": 15,
        "name": "Celestial Qi Pill",
        "ingredients": [{"herb_id": 10, "qty": 2}, {"herb_id": 7, "qty": 1}],
        "difficulty": 4,
        "effect_type": "cb_boost",
        "effect_value": 3.0,
        "duration_minutes": 120,
        "description": "+200% CB/tick for 2 hours. Only a true Master can refine this.",
        "emoji": "🌠",
        "min_realm": 4,
        "required_alchemy_tier": 3,
    },
    {
        "id": 16,
        "name": "Spirit Vein Pill",
        "ingredients": [{"herb_id": 3, "qty": 2}, {"herb_id": 4, "qty": 1}, {"herb_id": 8, "qty": 1}],
        "difficulty": 3,
        "effect_type": "qi_capacity",
        # Player report 2026-05-11 ([jogador]): "a pirula de ki T3 ta com
        # poder menos que a T2, ta 200 acho que o correto seria 2000". T3
        # Spirit Vein was +200 while T2 Qi Condensation (id=31, F-4 expansion)
        # is +500 — a clear tier inversion. Bumped to +1000 (between T2 and
        # the +2000 owner suggested) so progression makes sense. Seed runner
        # (below) also force-updates this row for existing players.
        "effect_value": 1000.0,
        "duration_minutes": 0,
        "description": "Permanently expands the Qi meridians. +1000 Qi Capacity.",
        "emoji": "🌊",
        "min_realm": 3,
        "required_alchemy_tier": 3,
    },
    # ── Tier 4 pills ──────────────────────────────────────────────────────────
    {
        "id": 17,
        "name": "Nascent Soul Pill",
        "ingredients": [{"herb_id": 4, "qty": 3}, {"herb_id": 10, "qty": 2}],
        "difficulty": 5,
        "effect_type": "soul_boost",
        "effect_value": 2.0,
        "duration_minutes": 180,
        "description": "+100% Soul Strength for 3 hours. Favored by soul cultivators.",
        "emoji": "👁️",
        "min_realm": 5,
        "required_alchemy_tier": 4,
    },
    {
        "id": 18,
        "name": "Void Cleansing Pill",
        "ingredients": [{"herb_id": 8, "qty": 2}, {"herb_id": 11, "qty": 2}],
        "difficulty": 4,
        "effect_type": "purity_boost",
        "effect_value": 0.20,
        "duration_minutes": 0,
        "description": "Purifies deep-seated impurities. +20% Foundation Purity.",
        "emoji": "🌑",
        "min_realm": 5,
        "required_alchemy_tier": 4,
    },
    # ── Tier 5 pills ──────────────────────────────────────────────────────────
    {
        "id": 19,
        "name": "Immortal Ascension Pill",
        "ingredients": [{"herb_id": 10, "qty": 3}, {"herb_id": 8, "qty": 2}, {"herb_id": 5, "qty": 2}],
        "difficulty": 6,
        "effect_type": "all_boost",
        "effect_value": 1.5,
        "duration_minutes": 240,
        "description": "+50% to all stats for 4 hours. The pinnacle of mortal alchemy.",
        "emoji": "🌸",
        "min_realm": 7,
        "required_alchemy_tier": 5,
    },
    {
        "id": 20,
        "name": "Dao Comprehension Pill",
        "ingredients": [{"herb_id": 4, "qty": 2}, {"herb_id": 6, "qty": 2}, {"herb_id": 8, "qty": 1}],
        "difficulty": 5,
        "effect_type": "dao_fragment_chance",
        "effect_value": 5.0,
        "duration_minutes": 120,
        "description": "5x Dao fragment drop chance for 2 hours. Enlightenment awaits.",
        "emoji": "☯️",
        "min_realm": 6,
        "required_alchemy_tier": 5,
    },
    # ── Qi Pills (stat boost) ────────────────────────────────────────────────
    {
        "id": 21,
        "name": "Soul Condensation Pill",
        "ingredients": [{"herb_id": 1, "qty": 5}, {"herb_id": 12, "qty": 3}],
        "difficulty": 1,
        "effect_type": "stat_boost",
        "effect_value": 5.0,
        "duration_minutes": 0,
        "description": "Permanently increases Soul Strength by 5 (cap: 80).",
        "emoji": "👻",
        "min_realm": 0,
        "required_alchemy_tier": 1,
    },
    {
        "id": 22,
        "name": "Mind Clarity Pill",
        "ingredients": [{"herb_id": 1, "qty": 4}, {"herb_id": 9, "qty": 3}],
        "difficulty": 1,
        "effect_type": "stat_boost",
        "effect_value": 5.0,
        "duration_minutes": 0,
        "description": "Permanently increases Perception by 5 (cap: 65).",
        "emoji": "👁️",
        "min_realm": 0,
        "required_alchemy_tier": 1,
    },
    {
        "id": 23,
        "name": "Fortune Pill",
        "ingredients": [{"herb_id": 12, "qty": 3}, {"herb_id": 2, "qty": 2}],
        "difficulty": 1,
        "effect_type": "stat_boost",
        "effect_value": 3.0,
        "duration_minutes": 0,
        "description": "Permanently increases Luck by 3 (cap: 50).",
        "emoji": "🍀",
        "min_realm": 0,
        "required_alchemy_tier": 1,
    },
    {
        "id": 24,
        "name": "Greater Soul Pill",
        "ingredients": [{"herb_id": 2, "qty": 5}, {"herb_id": 3, "qty": 3}],
        "difficulty": 2,
        "effect_type": "stat_boost",
        "effect_value": 10.0,
        "duration_minutes": 0,
        "description": "Permanently increases Soul Strength by 10 (cap: 120).",
        "emoji": "👻",
        "min_realm": 2,
        "required_alchemy_tier": 2,
    },
    {
        "id": 25,
        "name": "Greater Mind Pill",
        "ingredients": [{"herb_id": 9, "qty": 4}, {"herb_id": 6, "qty": 3}],
        "difficulty": 2,
        "effect_type": "stat_boost",
        "effect_value": 10.0,
        "duration_minutes": 0,
        "description": "Permanently increases Perception by 10 (cap: 100).",
        "emoji": "👁️",
        "min_realm": 3,
        "required_alchemy_tier": 2,
    },
    {
        "id": 26,
        "name": "Greater Fortune Pill",
        "ingredients": [{"herb_id": 3, "qty": 3}, {"herb_id": 11, "qty": 3}],
        "difficulty": 3,
        "effect_type": "stat_boost",
        "effect_value": 6.0,
        "duration_minutes": 0,
        "description": "Permanently increases Luck by 6 (cap: 80).",
        "emoji": "🍀",
        "min_realm": 3,
        "required_alchemy_tier": 3,
    },
    # ── Healing Pills ────────────────────────────────────────────────────────
    {
        "id": 27,
        "name": "Minor Healing Pill",
        "ingredients": [{"herb_id": 9, "qty": 2}],
        "difficulty": 1,
        "effect_type": "hp_restore",
        "effect_value": 0.30,
        "duration_minutes": 0,
        "description": "Restores 30% of max HP. A basic healing remedy.",
        "emoji": "❤️",
        "min_realm": 0,
        "required_alchemy_tier": 1,
    },
    {
        "id": 28,
        "name": "Healing Pill",
        "ingredients": [{"herb_id": 3, "qty": 3}],
        "difficulty": 2,
        "effect_type": "hp_restore",
        "effect_value": 0.50,
        "duration_minutes": 0,
        "description": "Restores 50% of max HP. Standard healing for cultivators.",
        "emoji": "❤️",
        "min_realm": 1,
        "required_alchemy_tier": 2,
    },
    {
        "id": 29,
        "name": "Greater Healing Pill",
        "ingredients": [{"herb_id": 10, "qty": 2}, {"herb_id": 7, "qty": 1}],
        "difficulty": 4,
        "effect_type": "hp_restore",
        "effect_value": 0.80,
        "duration_minutes": 0,
        "description": "Restores 80% of max HP. Infused with phoenix tears.",
        "emoji": "❤️",
        "min_realm": 4,
        "required_alchemy_tier": 3,
    },
    {
        "id": 30,
        "name": "Supreme Healing Pill",
        "ingredients": [{"herb_id": 10, "qty": 3}, {"herb_id": 8, "qty": 2}],
        "difficulty": 5,
        "effect_type": "hp_restore",
        "effect_value": 1.00,
        "duration_minutes": 0,
        "description": "Fully restores HP + 10% shield. The ultimate healing pill.",
        "emoji": "💖",
        "min_realm": 6,
        "required_alchemy_tier": 4,
    },
    # ── F-4: Alchemy Expansion — New Recipes ─────────────────────────────────
    {
        "id": 31,
        "name": "Qi Condensation Pill",
        "ingredients": [{"herb_id": 3, "qty": 3}, {"herb_id": 6, "qty": 2}],
        "difficulty": 3,
        "effect_type": "qi_capacity",
        "effect_value": 500.0,
        "duration_minutes": 0,
        "description": "Permanently expands the Qi meridians. +500 Qi Capacity.",
        "emoji": "🌊",
        "min_realm": 2,
        "required_alchemy_tier": 2,
    },
    {
        "id": 32,
        "name": "Body Refining Pill",
        "ingredients": [{"herb_id": 7, "qty": 2}, {"herb_id": 11, "qty": 3}],
        "difficulty": 3,
        "effect_type": "body_tempering_progress",
        "effect_value": 100.0,
        "duration_minutes": 0,
        "description": "Infuses the body with primal energy. +100 Body Tempering progress.",
        "emoji": "💪",
        "min_realm": 7,
        "required_alchemy_tier": 2,
    },
    {
        "id": 33,
        "name": "Soul Expansion Pill",
        "ingredients": [{"herb_id": 4, "qty": 3}, {"herb_id": 6, "qty": 2}, {"herb_id": 8, "qty": 1}],
        "difficulty": 4,
        "effect_type": "stat_boost",
        "effect_value": 200.0,
        "duration_minutes": 0,
        "description": "Permanently increases Soul Strength by 200 (cap: 300). A supreme soul pill.",
        "emoji": "👻",
        "min_realm": 4,
        "required_alchemy_tier": 3,
    },
    {
        "id": 34,
        "name": "Foundation Repair Pill",
        "ingredients": [{"herb_id": 10, "qty": 2}, {"herb_id": 4, "qty": 2}, {"herb_id": 8, "qty": 2}],
        "difficulty": 5,
        "effect_type": "foundation_reroll",
        "effect_value": 1.0,
        "duration_minutes": 0,
        "description": "Rerolls Foundation Quality. A second chance to rebuild your path.",
        "emoji": "🏯",
        "min_realm": 2,
        "required_alchemy_tier": 4,
    },
    {
        "id": 35,
        "name": "Core Essence Pill",
        "ingredients": [{"herb_id": 10, "qty": 3}, {"herb_id": 7, "qty": 2}, {"herb_id": 4, "qty": 1}],
        "difficulty": 5,
        "effect_type": "core_essence",
        "effect_value": 50.0,
        "duration_minutes": 0,
        "description": "Infuses pure essence into the Golden Core. +50 Core Essence.",
        "emoji": "💎",
        "min_realm": 2,
        "required_alchemy_tier": 4,
    },
    {
        "id": 36,
        "name": "Realm Insight Pill",
        "ingredients": [{"herb_id": 10, "qty": 2}, {"herb_id": 5, "qty": 2}, {"herb_id": 6, "qty": 1}],
        "difficulty": 5,
        "effect_type": "cb_instant",
        "effect_value": 5000.0,
        "duration_minutes": 0,
        "description": "Grants 5,000 CB instantly. A pill of pure cultivation insight.",
        "emoji": "📖",
        "min_realm": 4,
        "required_alchemy_tier": 4,
    },
    {
        "id": 37,
        "name": "Transcendence Pill",
        "ingredients": [{"herb_id": 12, "qty": 3}, {"herb_id": 10, "qty": 2}, {"herb_id": 9, "qty": 2}],
        "difficulty": 7,
        "effect_type": "special",
        "effect_value": 0.0,
        "duration_minutes": 0,
        "description": "A legendary pill that pushes a technique beyond mortal limits. Required for Transcendent grade evolution.",
        "emoji": "🌸",
        "min_realm": 5,
        "required_alchemy_tier": 5,
    },
    # D-2 (DESIGN_DECISIONS_v14): suite de 3 pílulas Qi regen — players reportaram
    # Qi regen lento late-game ([jogadores]).
    # Stack: 3 simultâneas com diminishing returns (1.0/0.5/0.25) — ver
    # core/game_logic.py cultivation_tick.
    {
        "id": 38,
        "name": "Qi Vortex Pill",
        "ingredients": [{"herb_id": 1, "qty": 3}, {"herb_id": 3, "qty": 1}, {"herb_id": 11, "qty": 1}],
        "difficulty": 3,
        "effect_type": "qi_regen_boost",
        "effect_value": 1.5,
        "duration_minutes": 60,
        "description": "Spins a vortex of Qi within the dantian. +50% Qi regen for 1 hour.",
        "emoji": "🌀",
        "min_realm": 3,
        "required_alchemy_tier": 3,
    },
    {
        "id": 39,
        "name": "Heavenly Spring Pill",
        "ingredients": [{"herb_id": 3, "qty": 2}, {"herb_id": 4, "qty": 2}, {"herb_id": 7, "qty": 1}],
        "difficulty": 5,
        "effect_type": "qi_regen_boost",
        "effect_value": 2.0,
        "duration_minutes": 120,
        "description": "Channels a heavenly spring of Qi through the meridians. +100% Qi regen for 2 hours.",
        "emoji": "🌊",
        "min_realm": 6,
        "required_alchemy_tier": 4,
    },
    {
        "id": 40,
        "name": "Eternal River Pill",
        "ingredients": [{"herb_id": 10, "qty": 1}, {"herb_id": 8, "qty": 2}, {"herb_id": 4, "qty": 1}],
        "difficulty": 7,
        "effect_type": "qi_regen_boost",
        "effect_value": 3.0,
        "duration_minutes": 240,
        "description": "Opens a flowing river of celestial Qi. +200% Qi regen for 4 hours. Endgame staple.",
        "emoji": "🌌",
        "min_realm": 8,
        "required_alchemy_tier": 5,
    },
    # v14.4 D-1c: Eternal Foundation Pill — Heavenly-grade endgame craft.
    # NOTE: spec called for id=38 but that conflicts with D-2 Qi Vortex; we
    # use id=41 to avoid renumbering live PlayerInventory rows. Spec also
    # listed Spirit Copper Ore + Heavenly Jade as ingredients, but PillCatalog
    # ingredients schema is herb-only. Adding ore-typed ingredients would
    # require modifying check_ingredients/consume_ingredients/UI renderers
    # — out of scope for this sprint. The pill remains brutally gated by
    # the two new T5 herbs (Eternal Spring Petal from Mahayana Nightmare
    # only, Heaven-Falling Star Dew from World Boss top-3) which is more
    # than enough to keep it endgame-only.
    #
    # Effect resolution (apply_pill_effect "eternal_foundation_reroll"):
    #   heavenly: 90% Perfect / 10% High; if current=Perfect → SACRED tier
    #   divine:   70% Perfect / 25% High / 5% Medium
    #   perfect:  50% Perfect / 40% High / 10% Medium
    #   normal:   30% Perfect / 50% High / 20% Medium
    {
        "id": 41,
        "name": "Eternal Foundation Pill",
        "ingredients": [
            {"herb_id":  3, "qty": 3},   # Foundation Lotus (T3)
            {"herb_id": 13, "qty": 2},   # Eternal Spring Petal (T5, Mahayana Nightmare)
            {"herb_id": 14, "qty": 1},   # Heaven-Falling Star Dew (T5, WB top-3)
        ],
        "difficulty": 5,
        "effect_type": "eternal_foundation_reroll",
        "effect_value": 1.0,
        "duration_minutes": 0,
        "description": "Reforges the foundation at the level of the Heavens. At Heavenly grade with a Perfect base, awakens the Sacred Foundation — the pinnacle of mortal cultivation.",
        "emoji": "🌌",
        "min_realm": 8,
        "required_alchemy_tier": 4,
    },
]

CAULDRONS = [
    {
        "id": 1,
        "name": "Copper Cauldron",
        "grade": 1,
        "success_bonus": 5.0,
        "slots": 3,
        "max_durability": 100,
        "description": "A basic copper cauldron. Every alchemist starts here.",
        "base_price": 100,
        "emoji": "🟤",
    },
    {
        "id": 2,
        "name": "Iron Cauldron",
        "grade": 2,
        "success_bonus": 10.0,
        "slots": 4,
        "max_durability": 150,
        "description": "Forged in celestial iron. Distributes heat evenly.",
        "base_price": 500,
        "emoji": "⚙️",
    },
    {
        "id": 3,
        "name": "Silver Cauldron",
        "grade": 3,
        "success_bonus": 15.0,
        "slots": 5,
        "max_durability": 200,
        "description": "Silver refined with Qi. Purifies impurities during crafting.",
        "base_price": 2000,
        "emoji": "🪙",
    },
    {
        "id": 4,
        "name": "Gold Cauldron",
        "grade": 4,
        "success_bonus": 25.0,
        "slots": 6,
        "max_durability": 300,
        "description": "Legendary gold cauldron. Used only by Great Alchemy Masters.",
        "base_price": 10000,
        "emoji": "🥇",
    },
    {
        "id": 5,
        "name": "Crystal Cauldron",
        "grade": 5,
        "success_bonus": 35.0,
        "slots": 7,
        "max_durability": 400,
        "description": "A cauldron carved from spiritual crystal. Resonates with pill essences.",
        "base_price": 30000,
        "emoji": "💎",
    },
    {
        "id": 6,
        "name": "Immortal Cauldron",
        "grade": 6,
        "success_bonus": 45.0,
        "slots": 8,
        "max_durability": 500,
        "description": "A legendary cauldron used by Immortal Alchemists. Near-perfect success.",
        "base_price": 100000,
        "emoji": "🌟",
    },
    {
        "id": 7,
        "name": "Dao Cauldron",
        "grade": 7,
        "success_bonus": 50.0,
        "slots": 10,
        "max_durability": 600,
        "description": "The supreme cauldron. Said to be forged from the essence of the Dao itself.",
        "base_price": 500000,
        "emoji": "💜",
    },
]


async def run_alchemy_seeds(session: AsyncSession):
    existing_herb_ids = set((await session.execute(select(HerbCatalog.id))).scalars().all())
    added_herbs = 0
    for h in HERBS:
        if h["id"] not in existing_herb_ids:
            session.add(HerbCatalog(**h))
            added_herbs += 1
    if added_herbs:
        logger.info("🌿 Seeded %d new herbs (skipped %d existing)", added_herbs, len(HERBS) - added_herbs)

    existing_pill_ids = set((await session.execute(select(PillCatalog.id))).scalars().all())
    added_pills = 0
    for p in PILLS:
        if p["id"] not in existing_pill_ids:
            session.add(PillCatalog(**p))
            added_pills += 1
    if added_pills:
        logger.info("💊 Seeded %d new pills (skipped %d existing)", added_pills, len(PILLS) - added_pills)

    # Force-update specific pill rows whose seed values have changed since
    # initial insertion (player-reported balance regressions, fixes etc).
    # CLAUDE.md §4 "Seed sync" requires the runner to mirror catalog
    # adjustments onto live rows. Keep this list small and intentional —
    # only patch effect_value/description for rows that have a documented
    # reason to change.
    _PILL_FORCE_UPDATES = {
        # T3 Spirit Vein Pill regression ([jogador] 2026-05-11) — was
        # +200 Qi capacity, lower than T2 Qi Condensation's +500. Bumped to
        # +1000 to restore tier progression.
        16: {"effect_value": 1000.0,
             "description": "Permanently expands the Qi meridians. +1000 Qi Capacity."},
    }
    from sqlalchemy import update as _sa_update
    for pid, fields in _PILL_FORCE_UPDATES.items():
        await session.execute(
            _sa_update(PillCatalog)
            .where(PillCatalog.id == pid)
            .values(**fields)
        )
    if _PILL_FORCE_UPDATES:
        logger.info("💊 Force-updated %d pill row(s) for seed sync", len(_PILL_FORCE_UPDATES))

    existing_cauldron_ids = set((await session.execute(select(CauldronCatalog.id))).scalars().all())
    added_cauldrons = 0
    for c in CAULDRONS:
        if c["id"] not in existing_cauldron_ids:
            session.add(CauldronCatalog(**c))
            added_cauldrons += 1
    if added_cauldrons:
        logger.info("⚗️ Seeded %d new cauldrons (skipped %d existing)", added_cauldrons, len(CAULDRONS) - added_cauldrons)

    await session.commit()
