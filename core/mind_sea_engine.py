"""Track A (B4) — Mind Sea 识海 ("Mar da Consciência"): the seat of the soul and
the wellspring of the Divine Sense (神識), revealed as VISIBLE DATA.

The pillar of spiritual identity in Xianxia (Reverend Insanity / Coiling Dragon /
A Will Eternal): every cultivator carries a Sea of Consciousness — the inner ocean
where the soul (元神) dwells, from which the Divine Sense radiates, where the heart
demon attacks, and where alchemy concentrates. Grand Design Apêndice A / B4 / Gap 6.

This wave is a **REFRAME** (the item-6 precedent — the Comprehension axis already
existed as `mastery_level`), NOT a new column. The fine audit confirmed the Mind
Sea is already the SUM of two LIVE stats:
  * ``Player.soul_strength`` — the soul that dwells in the sea (its VOLUME).
  * ``Player.perception``    — the Divine Sense clarity that reads its surface; the
    SAME stat ``core.divine_sense_engine`` already uses to raise exploration clue
    clarity (神識 is already alive in the loop).
plus the realm STRATUM each breakthrough carves wider. So there is NO migration:
this module DERIVES a read-only "depth tier" from those existing values and reveals
it, exactly as items 5/6/B4 revealed root composition / comprehension / longevity.

DISCLOSURE-ONLY (Lei §1, §3, §5). NOTHING here applies a modifier — no number in
combat, cultivation, alchemy, or exploration changes or newly reads the Mind Sea.
The Track B (wipe-bound) mechanics are explicitly labelled as FUTURE: soul defense
vs the heart demon (Heart Demon Phase R6+), the alchemy/comprehension focus boost,
the Soul Lamp 命灯 (life detector, tied to the real Lifespan death), and Mind Sea
turbidity from Forbidden cultivation / Qi Deviation. A defensive grep guarantees no
gameplay path reads ``project_mind_sea_*`` for a modifier — keep it that way.

Derivation is pure + parity-safe: it reads the RAW ``player.soul_strength`` /
``player.perception`` (NOT the equipment/buff-boosted display totals) so the chat
``/status`` card and the mini ``CultivationTab`` card — which only has the raw
payload values — always agree on the same tier.
"""
from __future__ import annotations

from config import REALM_NAMES

# ══════════════════════════════════════════════════════════════════════════
# Depth tiers (engine-not-DB, wipe-safe). The Sea DEEPENS as the soul grows and
# the realm stratum widens. Ordered ascending: pick the highest tier whose
# `min_depth` the cultivator's depth score meets. Labels + lore are localized via
# the `mind_sea_tier_<key>` / `_lore` i18n keys (chat + mini parity).
#
#   4 tiers (Lei §3 — depth over variety): Raso → Profundo → Vasto → Sem-Fundo.
#   Calibrated to TODAY's stat ranges (soul/perception reset to 50/40 each life,
#   grow to ~1963 capped; realm 0..10): a fresh mortal reads Shallow, a near-cap
#   late-realm cultivator reads Fathomless, with Vast covering the long mid-game.
# ══════════════════════════════════════════════════════════════════════════
MIND_SEA_TIERS: list[tuple[str, int, str]] = [
    # key,          min_depth, emoji
    ("shallow",     0,         "🌫️"),
    ("deep",        500,       "🌊"),
    ("vast",        1800,      "🌌"),
    ("fathomless",  4500,      "♾️"),
]

# Per-realm contribution to the depth score: the breakthrough carves the sea
# wider while soul + perception fill it. Tunable at the wipe (when the real
# mechanics attach); never read by any live modifier.
_REALM_WEIGHT = 250

# Realm floors for an NPC's tier (the echo row carries no soul/perception, so the
# realm IS the honest anchor for a generic cultivator's sea). Ordered high→low;
# the first floor `realm` meets wins. Calibrated to roughly where a typical player
# of that realm lands on the score ladder above.
_NPC_REALM_TIER: list[tuple[int, str]] = [
    (8, "fathomless"),   # realm >= 8
    (5, "vast"),         # realm 5..7
    (2, "deep"),         # realm 2..4
    (0, "shallow"),      # realm 0..1
]

_EMOJI_BY_TIER = {k: e for k, _m, e in MIND_SEA_TIERS}


def _clamp_realm(realm) -> int:
    try:
        r = int(realm or 0)
    except (TypeError, ValueError):
        r = 0
    return max(0, min(r, len(REALM_NAMES) - 1))


def _tier_for_depth(depth: int) -> tuple[str, str]:
    """The (key, emoji) of the highest tier whose threshold `depth` meets."""
    chosen = MIND_SEA_TIERS[0]
    for tier in MIND_SEA_TIERS:
        if depth >= tier[1]:
            chosen = tier
    return chosen[0], chosen[2]


def mind_sea_depth(player) -> int:
    """The composite depth score: soul (volume) + perception (Divine Sense clarity)
    + the realm stratum. PURE reading — never a modifier; only picks the tier."""
    soul = max(0, int(getattr(player, "soul_strength", 0) or 0))
    perc = max(0, int(getattr(player, "perception", 0) or 0))
    realm = _clamp_realm(getattr(player, "realm", 0))
    return soul + perc + realm * _REALM_WEIGHT


def project_mind_sea_for_display(player) -> dict:
    """Structural projection for the chat + mini surfaces (the "Mar da Consciência"
    card). PURE: the derived depth tier + the raw component stats (for grounding) +
    the realm. ZERO modifier — it REVEALS what soul_strength + perception + realm
    already are; nothing new is tracked or applied (the soul-defense / alchemy-focus
    / Soul Lamp mechanics are wipe-bound, Lei §1)."""
    soul = max(0, int(getattr(player, "soul_strength", 0) or 0))
    perc = max(0, int(getattr(player, "perception", 0) or 0))
    realm = _clamp_realm(getattr(player, "realm", 0))
    depth = soul + perc + realm * _REALM_WEIGHT
    tier_key, tier_emoji = _tier_for_depth(depth)
    return {
        "tier": tier_key,
        "tier_emoji": tier_emoji,
        "depth": depth,        # internal composite — not rendered as a raw number
        "soul": soul,
        "perception": perc,
        "realm": realm,
    }


def npc_mind_sea_tier(realm) -> dict:
    """A deterministic, no-PII Mind Sea tier for an NPC cultivator — FLAVOR ONLY
    (the NpcCultivatorModal chip). The echo row carries no soul/perception, so the
    realm (its sea's vastness anchor) decides the band. Pure projection; no NPC is
    mutated and nothing reads this for a modifier (Lei §5)."""
    r = _clamp_realm(realm)
    for floor, key in _NPC_REALM_TIER:
        if r >= floor:
            return {"tier": key, "tier_emoji": _EMOJI_BY_TIER.get(key, "🌫️")}
    return {"tier": "shallow", "tier_emoji": "🌫️"}
