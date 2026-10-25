"""Track A (B4) — Lifespan 寿命: the mortality clock as VISIBLE DATA (寿海).

The pillar that defines Xianxia (Mortal's Journey / Coiling Dragon / Reverend
Insanity): a cultivator's longevity is FINITE, and each realm raises the ceiling.
Cultivation is the race against that clock; becoming immortal (ascending past the
mortal path) is escaping it — 无量, the boundless. Grand Design Apêndice A / B4.

This wave shipped **disclosure-only** (the Raízes/item-5 pattern): the per-realm
ceiling table + the display projection live here; nothing ticked, aged or killed.

**TEC-5 Forbidden Path (2026-08-03) gave the clock its first tooth** — and it is
the ONLY one. With the per-world flag `forbidden_path` ON, every use of a
forbidden art burns years of `age_years` at the settle
(:mod:`core.forbidden_path_engine`), the surfaces show the burn with
before→after, and an exhausted Sea makes the forbidden art REFUSE the swing.
Everything else remains untouched: no passive ageing tick, no death, no
modifier, and on every world with the flag OFF (including `main`) NOTHING reads
or writes these columns — the old invariant holds there byte-for-byte. The real
ageing tick (World Pulse), the Twilight → reincarnation/pill/demonic-escape
(never delete), real NPC death and sect vengeance are still Track B.

NB: the ceiling list below covers TODAY's realms; ∞ is not "a realm" but the
moment you become immortal. If the realm ladder ever changes, this list
realigns to it. So the copy says "ao tornar-se imortal" — the moment, not a
realm name.
"""
from __future__ import annotations

import os
import random

from config import REALM_NAMES

# ══════════════════════════════════════════════════════════════════════════
# Per-realm longevity ceiling, in years (engine-not-DB, wipe-safe). Indexed in
# lockstep with config.REALM_NAMES (0 Mortal .. 10 True Immortal). `None` = ∞:
# the cultivator escaped the clock by becoming immortal. Tunable at the wipe.
#
#   The danger BITES at realms 0–3 (100–500y) — a stagnant base ages and meets
#   the end. From Nascent Soul on you have millennia (effectively safe); the top
#   escapes entirely. Pressure at the base, freedom at the peak, ∞ as the prize.
# ══════════════════════════════════════════════════════════════════════════
REALM_LIFESPAN: list[int | None] = [
    100,      # 0  Mortal — the clock bites early
    150,      # 1  Qi Condensation
    250,      # 2  Foundation Establishment
    500,      # 3  Core Formation
    1_000,    # 4  Nascent Soul — centuries
    2_500,    # 5  Soul Transformation
    6_000,    # 6  Void Refinement
    15_000,   # 7  Body Integration
    50_000,   # 8  Mahayana — nearly free
    120_000,  # 9  Tribulation Transcendence — at the brink
    None,     # 10 True Immortal — ∞ (无量): you became immortal, escaped the cycle
]

# One-way seed salt for the deterministic NPC age (flavor only; never exposed).
# Mirrors core.root_engine._HASH_SALT / npc_cultivator_engine._HASH_SALT.
_NPC_AGE_SALT = os.getenv("LIFESPAN_NPC_AGE_SALT", "nivrael_trackA_lifespan")


def _clamp_realm(realm) -> int:
    try:
        r = int(realm or 0)
    except (TypeError, ValueError):
        r = 0
    return max(0, min(r, len(REALM_LIFESPAN) - 1))


def _realm_name(realm: int) -> str:
    """Canonical (English, language-neutral) realm name — the game shows these
    raw everywhere via config.REALM_NAMES / webserver._realm_label (NOT i18n)."""
    return REALM_NAMES[realm] if 0 <= realm < len(REALM_NAMES) else "Mortal"


def realm_ceiling_base(realm) -> int | None:
    """The bare per-realm ceiling (no bonus). `None` for the immortal tier."""
    return REALM_LIFESPAN[_clamp_realm(realm)]


def lifespan_ceiling(player) -> int | None:
    """The player's effective longevity ceiling: realm ceiling + earned bonus.
    `None` when immortal (the bonus is meaningless past the clock). ZERO modifier
    — this is the future tick's reference value, not a live number this wave."""
    base = realm_ceiling_base(getattr(player, "realm", 0))
    if base is None:
        return None
    bonus = int(getattr(player, "lifespan_bonus_years", 0) or 0)
    return base + bonus


def project_lifespan_for_display(player) -> dict:
    """Structural projection for the chat + mini surfaces (the "Mar de Longevidade"
    card). PURE: current-realm ceiling + the next-realm CARROT + the immortal flag.
    ZERO modifier, NO passive clock. `age_years` is 0 for everyone until a world
    turns on `forbidden_path` — there it is the years BURNED by forbidden arts
    (TEC-5), and the surfaces must show it instead of the "the clock does not run
    yet" teaser (Lei §1: never one screen lying about another). Still never a fake
    "you die in X". Realm names are the canonical English game constants."""
    realm = _clamp_realm(getattr(player, "realm", 0))
    base = REALM_LIFESPAN[realm]
    bonus = int(getattr(player, "lifespan_bonus_years", 0) or 0)
    age = int(getattr(player, "age_years", 0) or 0)
    is_immortal = base is None
    next_realm = realm + 1 if (realm + 1) < len(REALM_LIFESPAN) else None
    next_base = REALM_LIFESPAN[next_realm] if next_realm is not None else None
    next_is_immortal = next_realm is not None and next_base is None
    return {
        "realm": realm,
        "realm_name": _realm_name(realm),
        "ceiling": None if is_immortal else base + bonus,
        "is_immortal": is_immortal,
        "next_realm": next_realm,
        "next_realm_name": _realm_name(next_realm) if next_realm is not None else None,
        "next_ceiling": None if next_is_immortal else next_base,
        "next_is_immortal": next_is_immortal,
        "age_years": age,
        "bonus_years": bonus,
    }


def derive_npc_age(npc_id: int, realm) -> int | None:
    """A deterministic, no-PII, idempotent age for an NPC cultivator — FLAVOR ONLY
    (the ProfileModal "Idade: N anos" line). Seeded by the stable DB id (not PII),
    so it's the same every run and nothing ages. Falls between 30%–85% of the NPC's
    realm ceiling (an established cultivator, never past it). `None` for an immortal
    NPC (ageless). Pure projection; no real death until the wipe."""
    base = realm_ceiling_base(realm)
    if base is None:
        return None
    rng = random.Random(f"{_NPC_AGE_SALT}:{int(npc_id)}")
    return max(16, int(base * rng.uniform(0.30, 0.85)))
