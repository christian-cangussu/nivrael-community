"""core/divine_sense_engine.py — Onda 5 (Fase 1): Sentido Divino (神識).

The exploration loop is GUIDED BY PERCEPTION, not a map. The player's Divine
Sense "reads" each direction (whispers, pressures, auras) and surfaces a handful
of CLUES — each a hint (emoji + flavour + a destination node + a risk), never the
full reveal (Lei §1: honest disclosure, never frustrating). This module is the
clue generator: pure, deterministic-but-varied, and self-contained.

Design (matches the prompt):
  * ``perception`` raises CLARITY → the number of clues (3..5).
  * ``luck`` rolls RARITY → the chance a clue is a rare Hidden Monster
    (= an active NPC Cultivator from Onda 3).
  * Deterministic per (player, continent, depth) via a LOCAL ``random.Random``
    (never the module-global ``random`` — mirrors ``bounty_engine`` so tests
    that rely on the global generator are never perturbed). The SAME seed feeds
    both the READ scan and the WRITE advance, so the clue the player picked
    resolves to the clue they were shown.

It is PURE (no DB): the caller (``exploration_engine``) passes the continent's
node metadata (id + min_realm, loaded from ``DungeonCatalog``) and the fork-key
catalog; this module decides WHICH nodes, WHICH encounter types, and the risk.
"""

import os
import random

from core.continent_engine import CONTINENT_KEYS

# ── Tuning (env-overridable, like the other Onda engines) ──────────────────────
DIVINE_BASE_DIRECTIONS = int(os.getenv("DIVINE_BASE_DIRECTIONS", "3"))
DIVINE_PERCEPTION_T1 = int(os.getenv("DIVINE_PERCEPTION_T1", "70"))
DIVINE_PERCEPTION_T2 = int(os.getenv("DIVINE_PERCEPTION_T2", "160"))
DIVINE_HIDDEN_BASE = float(os.getenv("DIVINE_HIDDEN_BASE", "0.045"))
DIVINE_HIDDEN_LUCK_DIV = float(os.getenv("DIVINE_HIDDEN_LUCK_DIV", "2400"))
DIVINE_HIDDEN_CAP = float(os.getenv("DIVINE_HIDDEN_CAP", "0.16"))
DIVINE_REALM_REACH = int(os.getenv("DIVINE_REALM_REACH", "2"))
# Onda 5 Fase 3 — Ecos Míticos: an order of magnitude rarer than a Hidden Monster
# ("quanto mais fundo, mais misterioso"), luck-weighted, gated by a minimum depth.
DIVINE_MYTHIC_BASE = float(os.getenv("DIVINE_MYTHIC_BASE", "0.012"))
DIVINE_MYTHIC_LUCK_DIV = float(os.getenv("DIVINE_MYTHIC_LUCK_DIV", "9000"))
DIVINE_MYTHIC_CAP = float(os.getenv("DIVINE_MYTHIC_CAP", "0.05"))
DIVINE_MYTHIC_MIN_DEPTH = int(os.getenv("DIVINE_MYTHIC_MIN_DEPTH", "3"))

# Base encounter weights BEFORE the luck-gated Hidden Monster upgrade.
#   cache = ✨ safe materials (no combat) · trash = ⚠️ a quick fight ·
#   fork  = a Karmic-Crossroads-style moral choice.
_BASE_TYPES = ("cache", "trash", "fork")
_BASE_WEIGHTS = (0.34, 0.46, 0.20)

RISK_BY_TYPE = {"cache": "safe", "trash": "danger", "fork": "choice",
                "hidden": "ominous", "mythic": "mythic"}

# Flavour emoji pools per type (the Divine Sense "shape" of the direction).
_DIR_EMOJI = {
    "cache": ("🌿", "💎", "🪶", "🍃", "🫧"),
    "trash": ("⚔️", "🩸", "🐺", "🗡️", "🏹"),
    "fork":  ("🔀", "🧭", "🙏", "⚖️", "🕯️"),
    "hidden": ("☠️", "👁️", "🌑", "🔥", "🩻"),
    "mythic": ("👁️‍🗨️", "🪞", "🌀", "☯️"),
}

# Number of flavour variants per (type) clue line — keep in sync with the i18n
# keys explore_clue_<type>_1.._N (×3 locales).
CLUE_VARIANTS = 3


def _seed(player_id: int, continent: str, depth: int) -> int:
    """Stable integer seed from (player, continent, depth). NOT salted by a
    process-random string hash (PYTHONHASHSEED-safe) so scan and advance agree."""
    try:
        cidx = CONTINENT_KEYS.index(continent)
    except (ValueError, TypeError):
        cidx = 0
    return (int(player_id) * 2654435761 + cidx * 40503 + int(depth) * 2246822519) & 0x7FFFFFFF


def divine_direction_count(perception: int) -> int:
    """3..5 clues, scaling with perception clarity."""
    n = DIVINE_BASE_DIRECTIONS
    if int(perception or 0) >= DIVINE_PERCEPTION_T1:
        n += 1
    if int(perception or 0) >= DIVINE_PERCEPTION_T2:
        n += 1
    return max(3, min(5, n))


def hidden_chance(luck: int) -> float:
    """Per-clue probability a direction is a rare Hidden Monster (luck-gated)."""
    return max(DIVINE_HIDDEN_BASE,
               min(DIVINE_HIDDEN_CAP,
                   DIVINE_HIDDEN_BASE + (max(0, int(luck or 0)) / DIVINE_HIDDEN_LUCK_DIV)))


def mythic_chance(luck: int) -> float:
    """Per-clue probability a direction is a raríssimo Mythic Echo (luck-gated,
    an order of magnitude rarer than a Hidden Monster)."""
    return max(DIVINE_MYTHIC_BASE,
               min(DIVINE_MYTHIC_CAP,
                   DIVINE_MYTHIC_BASE + (max(0, int(luck or 0)) / DIVINE_MYTHIC_LUCK_DIV)))


def scan_directions(*, player_id, perception, luck, realm, continent, depth,
                    nodes, fork_keys=None, mythic_keys=None):
    """Pure, deterministic clue generator.

    ``nodes``     : list of {"id": int, "min_realm": int} for the continent.
    ``fork_keys`` : the ordered list of exploration-fork template keys (so a
                    "fork" clue can name a concrete fork deterministically).

    Returns a list of 3..5 direction dicts:
      {idx, node_id, type, risk, emoji, clue_variant, fork_key?}
    The encounter type and node are fixed per (player, continent, depth) so the
    advance resolves to what the scan showed; loot AMOUNTS are rolled later
    (non-deterministically) at resolve time, like dungeon floors.
    """
    realm = int(realm or 0)
    rng = random.Random(_seed(player_id, continent, depth))
    n = divine_direction_count(int(perception or 0))

    # Eligible nodes: within reach (min_realm <= realm + reach). Fall back to the
    # lowest-tier nodes so a clue ALWAYS points somewhere (Lei §1 — never empty).
    elig = [nd for nd in nodes if int(nd.get("min_realm", 0)) <= realm + DIVINE_REALM_REACH]
    if not elig:
        elig = sorted(nodes, key=lambda nd: int(nd.get("min_realm", 0)))[:max(1, DIVINE_BASE_DIRECTIONS)]
    if not elig:
        return []

    hp = hidden_chance(int(luck or 0))
    mp = mythic_chance(int(luck or 0))
    fork_keys = list(fork_keys or [])
    mythic_keys = list(mythic_keys or [])
    mythic_eligible = bool(mythic_keys) and int(depth) >= DIVINE_MYTHIC_MIN_DEPTH
    directions = []
    for i in range(n):
        # Node pick — bias toward the player's own realm tier.
        node_weights = [1.0 / (1.0 + abs(int(nd.get("min_realm", 0)) - realm)) for nd in elig]
        node = rng.choices(elig, weights=node_weights, k=1)[0]
        etype = rng.choices(list(_BASE_TYPES), weights=list(_BASE_WEIGHTS), k=1)[0]
        # ALWAYS draw both rare rolls (keep the rng stream type-independent so scan
        # and advance — which run this identical pure function — never diverge; the
        # Fase 1 double-settle lesson).
        hidden_roll = rng.random()
        mythic_roll = rng.random()
        within_reach = int(node.get("min_realm", 0)) <= realm + 1
        if within_reach and hidden_roll < hp:
            etype = "hidden"
        # A Mythic Echo is rarer still and OVERRIDES the hidden upgrade.
        if mythic_eligible and within_reach and mythic_roll < mp:
            etype = "mythic"
        emoji_pool = _DIR_EMOJI.get(etype, ("🧭",))
        clue_variant = rng.randint(1, CLUE_VARIANTS)
        emoji = emoji_pool[rng.randrange(len(emoji_pool))]
        d = {
            "idx": i,
            "node_id": int(node["id"]),
            "type": etype,
            "risk": RISK_BY_TYPE.get(etype, "danger"),
            "emoji": emoji,
            "clue_variant": clue_variant,
        }
        if etype == "fork" and fork_keys:
            d["fork_key"] = fork_keys[rng.randrange(len(fork_keys))]
        elif etype == "mythic" and mythic_keys:
            d["mythic_key"] = mythic_keys[rng.randrange(len(mythic_keys))]
        directions.append(d)
    return directions
