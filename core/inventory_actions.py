"""v14.2 D-4 — Inventory misc actions.

DESIGN_DECISIONS_v14.md §D-4: players reported ([jogadores]) being stuck
with "blueprint", "ore_pack" items in the misc tab without any "Use" button.
This module is the single source of truth for the *use* action of every misc
item type that does NOT already have a deep-link to an existing flow.

Per-type actions:
  • blueprint            → +500 forge XP (study the schematic)
  • ore_pack             → roll 1d3 ores of tier N (item_id = tier)
  • pill_recipe_scroll   → unlock random alchemy recipe (T2-T4)
  • mystery_box          → roll a tier-stratified loot table

Each function:
  • takes (session, player, inv_row) where inv_row is a PlayerInventory row that
    has already been validated to belong to the player and to have qty >= 1.
  • decrements qty by 1, deletes the row on qty=0.
  • returns a dict with `ok`, `kind`, plus payload fields the handler displays.
  • does NOT commit — the caller commits the session after rendering UX.

These actions intentionally use simple loot tables (no rarity layering) — the
launch sprint will replace them with the canonical loot system once the Wuxia
content lock is decided.
"""
from __future__ import annotations

import random
from sqlalchemy import select, delete

from database.models import (
    PlayerInventory, OreCatalog, PlayerOre, HerbCatalog, PillCatalog, PlayerRecipe,
)

# 名 2026-09-14 — o que a caixa DEU diz-se na lingua de quem a abriu.
from core.i18n import catalog_name as _cname


def _lang(player) -> str:
    """A lingua do dono da caixa. Estes motores nao recebem `lang` — recebem o
    `player`, que e' a mesma verdade e sem query extra."""
    return (getattr(player, "language", None) or "pt").lower()


BLUEPRINT_FORGE_XP = 500
ORE_PACK_ROLLS_MIN = 1
ORE_PACK_ROLLS_MAX = 3
PILL_RECIPE_TIER_MIN = 2
PILL_RECIPE_TIER_MAX = 4


async def _decrement_inv(session, inv: PlayerInventory) -> None:
    """Atomic-style decrement honouring the existing inventory row idiom."""
    inv.quantity -= 1
    if inv.quantity <= 0:
        await session.delete(inv)


# ─── blueprint: study to gain forge XP ────────────────────────────────────────

async def study_blueprint(session, player, inv: PlayerInventory) -> dict:
    from core.forge_engine import grant_forge_xp

    skill, leveled_up = await grant_forge_xp(session, player.telegram_id, BLUEPRINT_FORGE_XP)
    await _decrement_inv(session, inv)
    return {
        "ok": True,
        "kind": "blueprint",
        "xp_gained": BLUEPRINT_FORGE_XP,
        "new_xp": int(skill.xp),
        "forge_tier": int(skill.tier),
        "leveled_up": leveled_up,
    }


# ─── ore_pack: open to roll 1d3 ores of tier=item_id ─────────────────────────

async def open_ore_pack(session, player, inv: PlayerInventory) -> dict:
    """`inv.item_id` encodes the ore pack tier (1..5). Rolls 1-3 different ore
    types of that tier — if a tier has fewer ores than rolls, we double-up."""
    tier = max(1, int(inv.item_id or 1))

    candidates = (await session.execute(
        select(OreCatalog).where(OreCatalog.tier == tier)
    )).scalars().all()
    if not candidates:
        # Fallback to tier 1 to never leave the player empty-handed.
        candidates = (await session.execute(
            select(OreCatalog).where(OreCatalog.tier == 1)
        )).scalars().all()
    if not candidates:
        return {"ok": False, "reason": "no_ores_seeded"}

    rolls = random.randint(ORE_PACK_ROLLS_MIN, ORE_PACK_ROLLS_MAX)
    granted: dict[int, int] = {}
    for _ in range(rolls):
        choice = random.choice(candidates)
        granted[choice.id] = granted.get(choice.id, 0) + 1

    # Apply grants
    granted_named = []
    for ore_id, qty in granted.items():
        existing = (await session.execute(
            select(PlayerOre).where(
                PlayerOre.player_id == player.telegram_id,
                PlayerOre.ore_id == ore_id,
            )
        )).scalar_one_or_none()
        if existing:
            existing.quantity += qty
        else:
            session.add(PlayerOre(player_id=player.telegram_id, ore_id=ore_id, quantity=qty))
        ore = next((c for c in candidates if c.id == ore_id), None)
        if ore:
            granted_named.append({"name": _cname(_lang(player), "ore", ore), "emoji": ore.emoji,
                                  "qty": qty, "tier": ore.tier})

    await _decrement_inv(session, inv)
    return {
        "ok": True,
        "kind": "ore_pack",
        "tier": tier,
        "total_rolls": rolls,
        "granted": granted_named,
    }


# ─── pill_recipe_scroll: unlock a random T2-T4 alchemy recipe ────────────────

async def learn_pill_recipe(session, player, inv: PlayerInventory) -> dict:
    """Picks a random pill in T2-T4 (`required_alchemy_tier`) that the player
    has NOT yet unlocked via PlayerRecipe. If everything is already known,
    returns `all_known` so the caller can refund / substitute reward."""
    known_ids = set((await session.execute(
        select(PlayerRecipe.item_id).where(
            PlayerRecipe.player_id == player.telegram_id,
            PlayerRecipe.item_type == "pill",
        )
    )).scalars().all())

    candidates = (await session.execute(
        select(PillCatalog).where(
            PillCatalog.required_alchemy_tier >= PILL_RECIPE_TIER_MIN,
            PillCatalog.required_alchemy_tier <= PILL_RECIPE_TIER_MAX,
        )
    )).scalars().all()
    pool = [p for p in candidates if p.id not in known_ids]
    if not pool:
        # Refund: substitute with 1× T2 herb so the scroll is never wasted.
        herb = (await session.execute(
            select(HerbCatalog).where(HerbCatalog.tier == 2).order_by(HerbCatalog.id).limit(1)
        )).scalar_one_or_none()
        if herb:
            from core.utils import add_item_to_inventory
            await add_item_to_inventory(session, player.telegram_id, "herb", herb.id, 1)
            await _decrement_inv(session, inv)
            return {
                "ok": True,
                "kind": "pill_recipe_scroll",
                "all_known": True,
                "refund": {"name": _cname(_lang(player), "herb", herb), "emoji": herb.emoji, "qty": 1},
            }
        # No T2 herb seeded? Just consume so player isn't stuck.
        await _decrement_inv(session, inv)
        return {"ok": True, "kind": "pill_recipe_scroll", "all_known": True, "refund": None}

    chosen = random.choice(pool)
    session.add(PlayerRecipe(
        player_id=player.telegram_id,
        item_type="pill",
        item_id=chosen.id,
    ))
    await _decrement_inv(session, inv)
    return {
        "ok": True,
        "kind": "pill_recipe_scroll",
        "all_known": False,
        "pill": {
            "id": chosen.id,
            "name": chosen.name,
            "emoji": chosen.emoji,
            "tier": chosen.required_alchemy_tier,
        },
    }


# ─── mystery_box: roll tier-stratified loot ──────────────────────────────────

# Loot table — keep deterministic so balance audits are easy.
# Each entry: (weight, callable that produces a result dict on hit).
async def open_mystery_box(session, player, inv: PlayerInventory) -> dict:
    """Roll 1 reward from a tiered loot table. The box never returns junk —
    every outcome is at least worth a perfect-grade T1 pill. Authentic Wuxia:
    "the heavens reward the seeker"."""
    from core.utils import add_item_to_inventory

    roll = random.random()
    # 50% T2 herb, 25% spirit stones (200..500), 15% T3 herb, 10% perfect-grade T2 pill
    if roll < 0.50:
        herbs = (await session.execute(
            select(HerbCatalog).where(HerbCatalog.tier == 2)
        )).scalars().all()
        if herbs:
            herb = random.choice(herbs)
            await add_item_to_inventory(session, player.telegram_id, "herb", herb.id, 1)
            await _decrement_inv(session, inv)
            return {"ok": True, "kind": "mystery_box", "result": "herb",
                    "name": _cname(_lang(player), "herb", herb), "emoji": herb.emoji, "qty": 1}
        # fall through to stones
        roll = 0.6
    if roll < 0.75:
        amount = random.randint(200, 500)
        player.spirit_stones += amount
        await _decrement_inv(session, inv)
        return {"ok": True, "kind": "mystery_box", "result": "stones",
                "amount": amount}
    if roll < 0.90:
        herbs = (await session.execute(
            select(HerbCatalog).where(HerbCatalog.tier == 3)
        )).scalars().all()
        if herbs:
            herb = random.choice(herbs)
            await add_item_to_inventory(session, player.telegram_id, "herb", herb.id, 1)
            await _decrement_inv(session, inv)
            return {"ok": True, "kind": "mystery_box", "result": "herb",
                    "name": _cname(_lang(player), "herb", herb), "emoji": herb.emoji, "qty": 1}
        # fall through to pill
    # 10% (or fallback): perfect-grade T2 pill
    pills = (await session.execute(
        select(PillCatalog).where(PillCatalog.required_alchemy_tier == 2)
    )).scalars().all()
    if pills:
        pill = random.choice(pills)
        await add_item_to_inventory(
            session, player.telegram_id, "pill", pill.id, 1, quality="perfect",
        )
        await _decrement_inv(session, inv)
        return {"ok": True, "kind": "mystery_box", "result": "pill",
                "name": _cname(_lang(player), "pill", pill), "emoji": pill.emoji, "quality": "perfect", "qty": 1}

    # ultimate fallback — never strand the player without reward
    player.spirit_stones += 500
    await _decrement_inv(session, inv)
    return {"ok": True, "kind": "mystery_box", "result": "stones", "amount": 500}
