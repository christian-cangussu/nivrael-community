"""v16.0 — Continent Engine (the geographic spine of Nivrael).

Pillar 1 of the v16 Living World refactor. Defines the five canonical
continents and exposes the read/write API that every other v16 system
(sect lineage, path trinity, karma spine, dungeon gating, world boss
rotation, scroll economy, rivalry events) will build on top of.

Five continents (lore-canonical, see `Cerebro/Nivrael/GameDesign/world_lore.md`
§3):

    Línghé   (灵河)  🏔️  Centro sagrado, balanceado, universal.
    Qiānhé   (千河)  ⛰️  Norte, corpo + resistência. Water/Ice/Earth.
    Yǎnshān  (燕山)  🌸  Leste, técnica + alchemy. Wind/Wood/Light.
    Fēnghuǒ  (烽火)  🌋  Sul, fogo + forja. Fire/Lightning/Chaos.
    Mòyǔ     (墨雨)  🌑  Oeste, proibido (Demonic). Shadow/Chaos/Death.

v16.0 scope: this engine is read-mostly. `set_player_continent` exists
as the future write path (travel mechanic), but v16.0 itself never
calls it — players spawn in (and stay in) Línghé. Travel ships in
v16.0b.

Mòyǔ is geographically present but `spawn_allowed=False` and
`demonic_only=True`: it appears in the mini-app continent list with a
🔒 lock badge until the player walks the Demonic Path (v16.2).

Design parallel to `core/intent_engine.py`:
  - Tuple of canonical keys.
  - Meta dict with display + gating attributes.
  - Pure helper functions for validation and lookup.
  - One mutator with SAVEPOINT (begin_nested) for safe error recovery
    inside a larger transaction.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from database.models import Player

logger = logging.getLogger(__name__)


# ── Canonical keys + display metadata ─────────────────────────────────────────

CONTINENT_KEYS: tuple[str, ...] = ("linghe", "qianhe", "yanshan", "fenghuo", "moyu")

# Onda 4b — Continent IDENTITY (specialty + native content tags) is engine
# data, NOT DB (wipe-safe, Lei §5). It is pure DISCLOSURE today (Lei §1): the
# Travel surface reveals what each continent is FOR (its lore specialty + the
# content that is "native" to it — dungeons/herbs/ores/forge/beasts) so the
# player understands why they'd move. The mechanical HARD-GATE of that content
# behind the continent is DEFERRED to the WIPE (Onda 5/6) — `native_tags` is a
# label set, never a lock. `native_tags` keys resolve via i18n `native_tag_*`.
CONTINENT_META: dict[str, dict[str, Any]] = {
    "linghe": {
        "emoji": "🏔️",
        "name_key": "continent_linghe",
        "subtitle_key": "continent_linghe_subtitle",
        "lore_key": "continent_lore_linghe",
        "elements": ("universal",),
        "specialty_key": "continent_spec_linghe",
        "native_tags": ("universal", "sects"),
        "demonic_only": False,
        "spawn_allowed": True,
    },
    "qianhe": {
        "emoji": "⛰️",
        "name_key": "continent_qianhe",
        "subtitle_key": "continent_qianhe_subtitle",
        "lore_key": "continent_lore_qianhe",
        "elements": ("water", "ice", "earth"),
        "specialty_key": "continent_spec_qianhe",
        "native_tags": ("body", "ores"),
        "demonic_only": False,
        "spawn_allowed": True,
    },
    "yanshan": {
        "emoji": "🌸",
        "name_key": "continent_yanshan",
        "subtitle_key": "continent_yanshan_subtitle",
        "lore_key": "continent_lore_yanshan",
        "elements": ("wind", "wood", "light"),
        "specialty_key": "continent_spec_yanshan",
        "native_tags": ("herbs", "alchemy"),
        "demonic_only": False,
        "spawn_allowed": True,
    },
    "fenghuo": {
        "emoji": "🌋",
        "name_key": "continent_fenghuo",
        "subtitle_key": "continent_fenghuo_subtitle",
        "lore_key": "continent_lore_fenghuo",
        "elements": ("fire", "lightning", "chaos"),
        "specialty_key": "continent_spec_fenghuo",
        "native_tags": ("forge", "combat"),
        "demonic_only": False,
        "spawn_allowed": True,
    },
    "moyu": {
        "emoji": "🌑",
        "name_key": "continent_moyu",
        "subtitle_key": "continent_moyu_subtitle",
        "lore_key": "continent_lore_moyu",
        "elements": ("shadow", "chaos", "death"),
        "specialty_key": "continent_spec_moyu",
        "native_tags": ("forbidden", "demonic"),
        "demonic_only": True,
        "spawn_allowed": False,
    },
}

DEFAULT_SPAWN_CONTINENT = "linghe"


# ── Validation + lookup ───────────────────────────────────────────────────────

def is_valid_continent(key: str | None) -> bool:
    return isinstance(key, str) and key in CONTINENT_META


def get_continent_meta(key: str) -> dict[str, Any]:
    """Return the meta dict for `key`. Raises KeyError if `key` is invalid."""
    if not is_valid_continent(key):
        raise KeyError(f"unknown continent: {key!r}")
    return CONTINENT_META[key]


def is_spawn_allowed(key: str) -> bool:
    """True if a brand-new player can spawn in this continent."""
    if not is_valid_continent(key):
        return False
    return bool(CONTINENT_META[key]["spawn_allowed"])


def is_demonic_only(key: str) -> bool:
    """True if this continent is locked to Demonic Path players (Mòyǔ)."""
    if not is_valid_continent(key):
        return False
    return bool(CONTINENT_META[key]["demonic_only"])


def get_default_spawn_continent() -> str:
    """Línghé — the lore-canonical neutral starter continent."""
    return DEFAULT_SPAWN_CONTINENT


# ── Player accessors ──────────────────────────────────────────────────────────

async def get_player_continent(session, player_id: int) -> str:
    """Return the player's current_continent (where they ARE).

    Falls back to the default spawn continent if the player has no value
    set or doesn't exist — never raises, so callers can use this in
    display paths without try/except.
    """
    row = (await session.execute(
        select(Player.current_continent).where(Player.telegram_id == player_id)
    )).first()
    key = (row[0] if row else None) or DEFAULT_SPAWN_CONTINENT
    return key if is_valid_continent(key) else DEFAULT_SPAWN_CONTINENT


async def get_player_home_continent(session, player_id: int) -> str:
    """Return the player's home_continent (where they were BORN)."""
    row = (await session.execute(
        select(Player.home_continent).where(Player.telegram_id == player_id)
    )).first()
    key = (row[0] if row else None) or DEFAULT_SPAWN_CONTINENT
    return key if is_valid_continent(key) else DEFAULT_SPAWN_CONTINENT


async def set_player_continent(session, player_id: int, continent: str) -> bool:
    """Set the player's `current_continent`. Returns True on success.

    Validates the target continent + the player's eligibility (Demonic-
    only continents reject non-Demonic players via ValueError).

    Uses SAVEPOINT (`begin_nested`) so a failed write does not poison
    an outer transaction — lesson from v15.3-hf3 inventory ops where
    a single bad row would abort the whole bulk batch.

    v16.0 does NOT call this anywhere — travel mechanic arrives in
    v16.0b. It exists so v16.0b can drop in without re-touching the
    engine surface area.
    """
    if not is_valid_continent(continent):
        raise ValueError(f"invalid continent: {continent!r}")

    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()
    if player is None:
        return False

    if is_demonic_only(continent):
        # Demonic gating: only players on the Demonic Path may enter Mòyǔ.
        # v16.2: path_engine is now the canonical source of truth. Faction
        # lookup remains as a defensive fallback for pre-v16.2 players
        # whose path backfill may not have landed yet.
        is_demonic = False
        try:
            from core.path_engine import get_player_path_raw, is_demonic_path
            raw_path = await get_player_path_raw(session, player_id)
            if raw_path is not None:
                is_demonic = is_demonic_path(raw_path)
        except Exception:
            logger.debug("path lookup failed during continent gate", exc_info=True)

        if not is_demonic:
            # Fallback: legacy faction. Same shape as v16.0.
            try:
                from core.faction_engine import get_player_faction
            except Exception:
                get_player_faction = None  # type: ignore[assignment]
            if get_player_faction is not None:
                try:
                    faction = await get_player_faction(session, player_id)
                    if faction is not None:
                        fid = getattr(faction, "faction_id", None) \
                            or getattr(faction, "id", None) \
                            or getattr(faction, "key", None)
                        is_demonic = str(fid or "").lower().startswith("demon")
                except Exception:
                    logger.debug("faction lookup failed during continent gate", exc_info=True)
                    is_demonic = False

        if not is_demonic:
            raise ValueError("continent_locked_demonic_only")

    async with session.begin_nested():
        player.current_continent = continent
    return True


# ── Display helpers (mini-app + chat) ─────────────────────────────────────────

def get_all_continents_for_display(lang: str) -> list[dict[str, Any]]:
    """Return all five continents projected for UI consumption.

    Each entry: {key, emoji, name, subtitle, lore, elements, locked,
    demonic_only, spawn_allowed}.

    The display order matches `CONTINENT_KEYS` (lore-canonical: central
    first, then cardinal points clockwise, then the forbidden one last).
    """
    # Local import avoids a hard module-level dependency on core.i18n
    # for callers that only need the meta dict.
    from core.i18n import t as i18n_t

    out: list[dict[str, Any]] = []
    for key in CONTINENT_KEYS:
        meta = CONTINENT_META[key]
        out.append({
            "key": key,
            "emoji": meta["emoji"],
            "name": i18n_t(lang, meta["name_key"]),
            "subtitle": i18n_t(lang, meta["subtitle_key"]),
            "lore": i18n_t(lang, meta["lore_key"]),
            "elements": list(meta["elements"]),
            "demonic_only": bool(meta["demonic_only"]),
            "spawn_allowed": bool(meta["spawn_allowed"]),
            # `locked` is the UI-side flag the mini-app reads to render
            # the 🔒 badge. v16.0: only Mòyǔ is locked. v16.2 will flip
            # it dynamically per-player based on Path.
            "locked": bool(meta["demonic_only"]),
        })
    return out


def project_continent_identity(key: str, lang: str) -> dict[str, Any]:
    """Onda 4b — the localized IDENTITY of one continent (name, emoji, subtitle,
    specialty, raw elements, localized native-content tags). Pure disclosure
    (Lei §1) — shared by the Travel endpoint and the /viajar chat surface.
    Never raises: an unknown key falls back to the spawn continent."""
    from core.i18n import t as i18n_t

    if not is_valid_continent(key):
        key = DEFAULT_SPAWN_CONTINENT
    meta = CONTINENT_META[key]
    native = [
        {"key": tag, "label": i18n_t(lang, f"native_tag_{tag}")}
        for tag in meta.get("native_tags", ())
    ]
    return {
        "key": key,
        "emoji": meta["emoji"],
        "name": i18n_t(lang, meta["name_key"]),
        "subtitle": i18n_t(lang, meta["subtitle_key"]),
        "specialty": i18n_t(lang, meta["specialty_key"]) if meta.get("specialty_key") else "",
        "elements": list(meta.get("elements", ())),
        "native_tags": native,
        "demonic_only": bool(meta["demonic_only"]),
    }
