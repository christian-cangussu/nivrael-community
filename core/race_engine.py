"""Sprint 1 — Raça: the PEOPLE the soul was born into (KEYSTONE A, 灵根 sibling).

The 3rd birth axis (races_and_cosmic_scale.md §KEYSTONE A, travada 2026-06-29),
ORTHOGONAL to the two that already exist:
  * spirit_root   — PURITY / grade (0=Heavenly..4=Low): HOW FAST you cultivate.
  * root_elements — Wuxing COMPOSITION: WHAT you can comprehend (core.root_engine).
  * race          — THIS module: the 6 peoples (humano/celeste/primordial/tita/
                    demonio/draconato). FATE, not choice (D-EG-3): rolled, never
                    selected, so the underdog drama survives the birth roll.

This wave is **disclosure-only**, exactly like root_engine. The catalog + the
derivation + the display projection live here; NOTHING applies a mechanical
modifier. The real depth — techniques-by-origin (KEYSTONE C), rock-paper-scissors
continent access (KEYSTONE B), the reroll ritual ("desafiar o Céu"), the
karma-locked demon — is Track B (wipe-bound).

⚠️ DEFENSIVE GREP (keep true until the wipe): NO path in combat / cultivation /
alchemy / travel reads `race`. The only readers are this engine and the
display-only `race` field in core.webserver.api_player. Adding a modifier that
reads `race` before the wipe BREAKS Lei §5 (wipe-friendliness) — don't.

⚠️ NO `backfill_*` (deliberate, unlike root_engine). Lei §1 + the "regra de ferro
dos 57": race is NEVER auto-assigned to a player who already exists. The column is
DEFAULT NULL and the 57 beta players on `main` stay NULL forever. The ONLY write
is at the BIRTH of a NEW character in a world where the `racas` flag is ON
(api_world_start on a secondary world). For DISPLAY in such a world, a still-NULL
row derives a race WITHOUT persisting (get_player_race) — mirrors root_engine's
display fallback; the panel is Surface-Manifest-gated so `main` never renders it.

Derivation is deterministic + no-PII: a seeded PRNG keyed by telegram_id (the same
`random.Random(f"{salt}:{telegram_id}")` pattern as core.root_engine.derive_root_
elements). Reproducible across reboots → the birth assignment is idempotent. The
race KEYS are language-neutral; the chat + mini surfaces localize names/lore via
the `race_*` i18n keys. project_race_for_display returns PURE structural data
(zero i18n, zero modifier).
"""
from __future__ import annotations

import os
import random

# ══════════════════════════════════════════════════════════════════════════
# Catalog (engine-not-DB, wipe-safe). Keys are language-neutral (≤16 chars → fit
# VARCHAR(16)). Each entry carries display-only data: a race emoji, the home
# continent (emoji + the canon proper-noun name — proper nouns are NOT translated,
# so they live as data, like the emojis), and the rarity band. Continent names
# mirror races_and_cosmic_scale.md §KEYSTONE B (the 5 elemental continents +
# Línghé's sealed 秘境). NO weight field here — weights live in _RACE_WEIGHTS.
# ══════════════════════════════════════════════════════════════════════════
RACES: dict[str, dict] = {
    # The 70% canvas — common BY DESIGN (the underdog screen). Home: the centre.
    "humano":     {"emoji": "🧑", "home": "🏔️ Línghé", "band": "common"},
    # The four peoples of the elemental continents — rare.
    "celeste":    {"emoji": "🕊️", "home": "🌸 Yǎnshān", "band": "rare"},
    "primordial": {"emoji": "🌀", "home": "🌋 Fēnghuǒ", "band": "rare"},
    "tita":       {"emoji": "🗿", "home": "⛰️ Qiānhé", "band": "rare"},
    "demonio":    {"emoji": "👹", "home": "🌑 Mòyǔ", "band": "rare"},
    # The server legend — legendary, sealed in Línghé's 秘境 (mirrors the 0.01
    # weight of the Heavenly spirit root).
    "draconato":  {"emoji": "🐲", "home": "🐲 Línghé 秘境", "band": "legendary"},
}

_CATALOG_ORDER = list(RACES.keys())
VALID_BANDS = ("common", "rare", "legendary")

# Fate distribution (relative weights; sum need not be 100). PROPOSED — Track B
# may tune it (the spec marks the % "afinável"). Humano dominates as the underdog
# canvas; draconato is the <0.5% server legend. The rock-paper-scissors continent
# access + karma-locked demon are Track B; the roll itself is pure here.
_RACE_WEIGHTS: list[tuple[str, float]] = [
    ("humano",     70.0),  # comum POR DESIGN — a tela do underdog
    ("celeste",     9.0),
    ("primordial",  9.0),
    ("tita",        9.0),
    ("demonio",     3.0),  # karma-locked é Track B; o roll é puro aqui
    ("draconato",   0.4),  # <0,5% — "lenda do servidor" (espelha o 0.01 da Heavenly root)
]

# One-way seed salt for the deterministic derivation (never exposed; only used to
# seed the PRNG). Mirrors core.root_engine._HASH_SALT.
_HASH_SALT = os.getenv("RACE_HASH_SALT", "nivrael_trackA_races")


def derive_race(telegram_id: int) -> str:
    """The fixed PEOPLE for a cultivator, derived from telegram_id (FATE).

    Pure + deterministic: same id -> same race, every run (string-seeded PRNG, the
    same pattern as root_engine.derive_root_elements). Returns exactly one of the 6
    catalog keys. No mechanical meaning — identity data only. Reroll ("desafiar o
    Céu") is Track B; here the birth roll is destiny.
    """
    rng = random.Random(f"{_HASH_SALT}:{telegram_id}")
    keys, weights = zip(*_RACE_WEIGHTS)
    return rng.choices(keys, weights=weights, k=1)[0]


def get_player_race(player) -> str | None:
    """The player's stored race, or a deterministic derived fallback for DISPLAY.

    Mirrors root_engine.get_root_elements: display never shows empty in a world
    where the feature is ON, so a still-NULL row derives from telegram_id WITHOUT
    persisting here (the birth assignment in api_world_start owns the only write).
    Defensively returns None for an unknown stored key. Never writes the object.

    NB: this DOES derive for `main` players too if a caller asks — but the race
    panel is Surface-Manifest-gated (`racas` OFF on main) and api_player only emits
    the projection when the feature is ON, so the 57 never see a derived race.
    """
    stored = getattr(player, "race", None)
    if stored:
        return stored if stored in RACES else None
    telegram_id = getattr(player, "telegram_id", None)
    if telegram_id is None:
        return None
    return derive_race(telegram_id)


def project_race_for_display(race_key: str | None) -> dict | None:
    """Structural projection for the chat + mini surfaces. ZERO i18n, ZERO modifier.

    Takes a resolved race key (typically project_race_for_display(get_player_race(
    player))) and returns PURE display data, or None for a missing/unknown key. When
    the `racas` feature is ON but this returns None (corrupt/missing key), the
    RaceCard shows the honest `race_none` line (Lei §1 — never a silent void); `main`
    keeps the feature OFF so the panel never renders there at all. The mini-app
    localizes `key` -> `race_<key>` / `race_<key>_lore` and `band` -> `race_rarity_<band>`.
    """
    info = RACES.get(race_key or "")
    if not info:
        return None
    return {
        "key": race_key,
        "emoji": info["emoji"],
        "home_continent": info["home"],
        "rarity_band": info["band"],
    }
