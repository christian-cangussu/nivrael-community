"""database/seeds/formation_seeds.py — Onda 5 (Fase 2): Matrizes/Formações 阵法.

The craftable Formation catalog (content, NOT migration — the seed runner
upserts on startup, so the catalog is wipe-safe and evolves without touching
the schema). LEAN by design (Lei §3 profundidade > variedade): 10 Formações
with real nuance across 6 effect types and the vision §4 duration ladder
(30min · 1h · 2h · 4h · 8h · celestial 12h) — NOT 30 renamed clones.

Effect types deliberately REUSE the live PlayerBuff vocabulary, so 4 of the 6
need ZERO new consumer code (the existing readers already apply them):
  * bp_boost           → combat strike (get_combat_buff_mults → build_fighter_data)
  * defense_boost      → combat defense (same path)
  * qi_regen_boost     → cultivation tick qi regen (game_logic.process_tick)
  * dao_fragment_chance→ Dao meditation fragment chance (scheduler tick)
  * perception_boost   → tribulation reading (existing) + NEW: Divine Sense
                          clarity in exploration scan (Onda 5 Fase 2 wire-in)
  * explore_protection → NEW consumer: reduces the exploration death-loss
                          (the 90% bag loss) — core/exploration_engine.py

Tuning intent (owner reviews numbers — DESIGN_DECISIONS §8.4 conservador):
pills stay the BURST option (e.g. Battle Fury 1.3×/1h); Formações are the
MARATHON option (lower mult, longer clock) — different niche, no power creep.
Costs are materials + spirit stones the exploration loop actually drops
(herbs 1-5, ores 1-5) — a REAL sink, NEVER jade (Lei §4).
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from database.models import FormationCatalog

logger = logging.getLogger(__name__)

# recipe JSONB: {"stones": int, "herbs": [{"herb_id", "qty"}], "ores": [{"ore_id", "qty"}]}
# herb ids: 1 Qi Root (T1) · 2 Spirit Grass (T2) · 3 Foundation Lotus (T3) ·
#           4 Soul Herb (T4) · 5 Breakthrough Flower (T5)
# ore ids:  1 Mortal Iron (T1) · 2 Spirit Copper (T2) · 3 Mystic Silver (T3) ·
#           4 Stellar Gold (T4) · 5 Celestial Jade (T5)
FORMATION_SEEDS = [
    # ── Tier 1 — the cheap staples (30min/1h) ──────────────────────────────────
    {
        "id": 1, "key": "divine_eye", "emoji": "👁️",
        "effect_type": "perception_boost", "effect_value": 1.25,
        "duration_minutes": 30, "tier": 1, "min_realm": 1,
        "recipe": {"stones": 100, "herbs": [{"herb_id": 1, "qty": 2}, {"herb_id": 2, "qty": 1}], "ores": []},
    },
    {
        "id": 2, "key": "spirit_edge", "emoji": "⚔️",
        "effect_type": "bp_boost", "effect_value": 1.10,
        "duration_minutes": 60, "tier": 1, "min_realm": 1,
        "recipe": {"stones": 150, "herbs": [{"herb_id": 1, "qty": 3}], "ores": [{"ore_id": 1, "qty": 2}]},
    },
    {
        "id": 3, "key": "stone_carapace", "emoji": "🛡️",
        "effect_type": "defense_boost", "effect_value": 1.10,
        "duration_minutes": 60, "tier": 1, "min_realm": 1,
        "recipe": {"stones": 150, "herbs": [], "ores": [{"ore_id": 1, "qty": 4}]},
    },
    # ── Tier 2 — the expedition kit (2h) ───────────────────────────────────────
    {
        "id": 4, "key": "qi_spiral", "emoji": "🌀",
        "effect_type": "qi_regen_boost", "effect_value": 1.30,
        "duration_minutes": 120, "tier": 2, "min_realm": 2,
        "recipe": {"stones": 300, "herbs": [{"herb_id": 2, "qty": 3}], "ores": [{"ore_id": 2, "qty": 1}]},
    },
    {
        "id": 5, "key": "hidden_veil", "emoji": "🌫️",
        "effect_type": "explore_protection", "effect_value": 0.35,
        "duration_minutes": 120, "tier": 2, "min_realm": 2,
        "recipe": {"stones": 350, "herbs": [{"herb_id": 2, "qty": 2}], "ores": [{"ore_id": 2, "qty": 2}]},
    },
    {
        "id": 6, "key": "dao_mirror", "emoji": "☯️",
        "effect_type": "dao_fragment_chance", "effect_value": 1.40,
        "duration_minutes": 120, "tier": 2, "min_realm": 3,
        "recipe": {"stones": 400, "herbs": [{"herb_id": 2, "qty": 2}, {"herb_id": 3, "qty": 1}], "ores": []},
    },
    # ── Tier 3 — the war footing (4h) ──────────────────────────────────────────
    {
        "id": 7, "key": "dragon_edge", "emoji": "🐉",
        "effect_type": "bp_boost", "effect_value": 1.18,
        "duration_minutes": 240, "tier": 3, "min_realm": 4,
        "recipe": {"stones": 800, "herbs": [{"herb_id": 3, "qty": 2}], "ores": [{"ore_id": 3, "qty": 2}]},
    },
    {
        "id": 8, "key": "celestial_wall", "emoji": "🏔️",
        "effect_type": "defense_boost", "effect_value": 1.18,
        "duration_minutes": 240, "tier": 3, "min_realm": 4,
        "recipe": {"stones": 800, "herbs": [], "ores": [{"ore_id": 3, "qty": 3}, {"ore_id": 2, "qty": 2}]},
    },
    # ── Tier 4 — the overnight cavern engine (8h) ──────────────────────────────
    {
        "id": 9, "key": "void_breath", "emoji": "🫧",
        "effect_type": "qi_regen_boost", "effect_value": 1.60,
        "duration_minutes": 480, "tier": 4, "min_realm": 5,
        "recipe": {"stones": 1500, "herbs": [{"herb_id": 4, "qty": 2}], "ores": [{"ore_id": 4, "qty": 1}]},
    },
    # ── Tier 5 — the celestial flex (12h) ──────────────────────────────────────
    {
        "id": 10, "key": "nine_heavens_veil", "emoji": "🌌",
        "effect_type": "explore_protection", "effect_value": 0.60,
        "duration_minutes": 720, "tier": 5, "min_realm": 6,
        "recipe": {"stones": 3000, "herbs": [{"herb_id": 4, "qty": 2}, {"herb_id": 5, "qty": 1}], "ores": [{"ore_id": 5, "qty": 1}]},
    },
]


async def run_formation_seeds(session):
    """Upsert the Formation catalog: INSERT new rows AND update existing rows'
    tuning fields (effect/duration/recipe/min_realm) so balance changes ship by
    editing this file — the dungeon-seeds pattern (seed sync, CLAUDE.md rule 4)."""
    existing = {
        f.id: f for f in (await session.execute(select(FormationCatalog))).scalars().all()
    }
    added = 0
    updated = 0
    for seed in FORMATION_SEEDS:
        row = existing.get(seed["id"])
        if row is None:
            session.add(FormationCatalog(**seed))
            added += 1
            continue
        changed = False
        for field in ("key", "emoji", "effect_type", "effect_value",
                      "duration_minutes", "tier", "min_realm"):
            if getattr(row, field) != seed[field]:
                setattr(row, field, seed[field])
                changed = True
        if row.recipe != seed["recipe"]:
            row.recipe = seed["recipe"]
            flag_modified(row, "recipe")
            changed = True
        if changed:
            updated += 1
    if added or updated:
        logger.info("🔯 Formation catalog: %d added, %d updated", added, updated)
    await session.commit()
