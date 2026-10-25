"""Track A item 5 — Raízes: spirit-root COMPOSITION (灵根 elemental axis).

The spirit root has TWO orthogonal axes (Grand Design §1):
  * PURITY / grade  — the existing `Player.spirit_root` (0=Heavenly..4=Low). Decides
    HOW FAST you cultivate. Untouched by this module.
  * COMPOSITION     — this module's `root_elements`: WHICH Wuxing elements (+ a rare
    variant) your root carries. Decides WHAT you can comprehend/learn.

This wave is **disclosure-only**. The catalog + derivation + display projection
live here; NOTHING applies a mechanical modifier. The real elemental gating, the
Wuxing generation/destruction cycle, and the combat/alchemy modifiers are Track B
(wipe-bound). A defensive grep guarantees no combat/cultivation/alchemy path reads
`root_elements` — keep it that way until the wipe.

Derivation is deterministic + no-PII: a seeded PRNG keyed by telegram_id (mirrors
`world_sects_engine.master_name_for`). Reproducible across reboots, so the startup
backfill is idempotent; once persisted the value is a fixed destiny (no reroll this
wave — composition is identity, Lei §4). The element KEYS are language-neutral; the
chat + mini surfaces localize names via the `root_el_*` / `root_archetype_*` i18n keys.
"""
from __future__ import annotations

import os
import random

# ══════════════════════════════════════════════════════════════════════════
# Catalog (engine-not-DB, wipe-safe). Keys are language-neutral + chosen to
# align with the existing Dao-path `element` vocabulary (fire/water/lightning/
# ice/wind/wood/earth/metal/space/chaos) so Track B gating can cross-reference
# without a rename. `rare` variants are the "illegible to the common Testing
# Stone" hidden-genius elements (Grand Design §1).
# ══════════════════════════════════════════════════════════════════════════
ROOT_ELEMENTS: dict[str, dict] = {
    # 5 Wuxing base 五行 — readable by the standard Testing Stone.
    "metal": {"emoji": "⚔️", "rare": False},
    "wood":  {"emoji": "🌳", "rare": False},
    "water": {"emoji": "💧", "rare": False},
    "fire":  {"emoji": "🔥", "rare": False},
    "earth": {"emoji": "⛰️", "rare": False},
    # Rare variants — revealed by event/Elder/treasure, not the common stone.
    "lightning": {"emoji": "⚡", "rare": True},
    "ice":       {"emoji": "❄️", "rare": True},
    "wind":      {"emoji": "🌪️", "rare": True},
    "dark":      {"emoji": "🌑", "rare": True},
    "chaos":     {"emoji": "🌀", "rare": True},
    "space":     {"emoji": "🌌", "rare": True},
    "time":      {"emoji": "⏳", "rare": True},
}

_CATALOG_ORDER = list(ROOT_ELEMENTS.keys())
BASE_ELEMENTS = [k for k, v in ROOT_ELEMENTS.items() if not v["rare"]]   # 5
RARE_VARIANTS = [k for k, v in ROOT_ELEMENTS.items() if v["rare"]]       # 7

# One-way seed salt for the deterministic derivation (never exposed; only used to
# seed the PRNG). Mirrors core.npc_cultivator_engine._HASH_SALT.
_HASH_SALT = os.getenv("ROOT_ELEMENT_HASH_SALT", "nivrael_trackA_roots")

# The Han Li inversion (Grand Design §1, Lei §3): single-element roots are rare
# PRODIGIES (fast, but locked out of most arts); penta roots are RARE (slow early,
# but the only ones that fuse all five into the supreme arts). The common middle is
# 2-3 elements. Tails are deliberately scarce so single/penta stay special.
_COUNT_WEIGHTS: list[tuple[int, float]] = [
    (1, 15.0),  # single — prodigy
    (2, 35.0),
    (3, 28.0),
    (4, 15.0),
    (5, 7.0),   # penta — rare
]
# Chance the root also carries a DORMANT rare variant (the hidden genius reveal).
_VARIANT_CHANCE = float(os.getenv("ROOT_ELEMENT_VARIANT_CHANCE", "0.08"))

_ARCHETYPE_BY_COUNT = {1: "single", 2: "dual", 3: "tri", 4: "quad", 5: "penta"}


# ══════════════════════════════════════════════════════════════════════════
# Derivation (deterministic, no-PII, idempotent)
# ══════════════════════════════════════════════════════════════════════════
def derive_root_elements(telegram_id: int) -> list[str]:
    """The fixed composition for a cultivator, derived from telegram_id.

    Pure + deterministic: same id -> same list, every run (string-seeded PRNG, the
    project-approved `master_name_for` pattern). Returns a non-empty list of catalog
    keys in canonical order, e.g. ["fire", "earth"] or ["water", "wind"] (variant
    appended). No mechanical meaning — composition data only.
    """
    rng = random.Random(f"{_HASH_SALT}:{telegram_id}")
    counts, weights = zip(*_COUNT_WEIGHTS)
    n = rng.choices(counts, weights=weights, k=1)[0]
    elements = rng.sample(BASE_ELEMENTS, n)  # n distinct base elements
    if rng.random() < _VARIANT_CHANCE:
        elements.append(rng.choice(RARE_VARIANTS))
    # Canonical order for stable display + storage (base elements then variant).
    elements.sort(key=_CATALOG_ORDER.index)
    return elements


def get_root_elements(player) -> list[str]:
    """The player's stored composition, or a deterministic derived fallback.

    Display never shows empty: if the column is still NULL (pre-backfill race) we
    derive from telegram_id WITHOUT persisting here (the startup backfill + birth
    assignment own the writes). Defensively filters out any unknown key.
    """
    stored = getattr(player, "root_elements", None)
    if stored:
        known = [e for e in stored if e in ROOT_ELEMENTS]
        if known:
            known.sort(key=_CATALOG_ORDER.index)
            return known
    return derive_root_elements(player.telegram_id)


# ══════════════════════════════════════════════════════════════════════════
# Display projection (PURE — no i18n, no modifiers). Each surface localizes the
# element/archetype names via its own i18n (root_el_* / root_archetype_*).
# ══════════════════════════════════════════════════════════════════════════
def project_root_for_display(elements: list[str]) -> dict:
    """Structural projection for the chat + mini surfaces. ZERO modifiers."""
    out: list[dict] = []
    base_count = 0
    has_variant = False
    for e in elements:
        info = ROOT_ELEMENTS.get(e)
        if not info:
            continue
        rare = bool(info["rare"])
        if rare:
            has_variant = True
        else:
            base_count += 1
        out.append({"key": e, "emoji": info["emoji"], "rare": rare})
    return {
        "elements": out,
        "base_count": base_count,
        "has_variant": has_variant,
        "is_single": base_count == 1,
        "is_penta": base_count == 5,
        "archetype": _ARCHETYPE_BY_COUNT.get(base_count, "dual"),
    }


# ══════════════════════════════════════════════════════════════════════════
# Idempotent startup backfill (Python — needs the PRNG, can't be pure SQL).
# ══════════════════════════════════════════════════════════════════════════
async def backfill_root_elements(session) -> int:
    """Derive + persist `root_elements` for every player still NULL.

    Idempotent via the `IS NULL` guard + deterministic derivation: re-runs touch
    only un-derived rows and always produce the same value. Owns its commit
    (mirrors the npc_cultivator bootstrap). Returns the number of rows derived.
    """
    from sqlalchemy import select, update

    from database.models import Player

    rows = (await session.execute(
        select(Player.id, Player.telegram_id).where(Player.root_elements.is_(None))
    )).all()
    n = 0
    for pid, telegram_id in rows:
        elements = derive_root_elements(telegram_id)
        await session.execute(
            update(Player).where(Player.id == pid).values(root_elements=elements)
        )
        n += 1
    if n:
        await session.commit()
    return n
