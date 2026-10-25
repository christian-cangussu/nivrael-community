"""v16.1 — Sect Lineage Engine (Pilar 2 do v16 Living World).

Sects player-created (actuais "guildas genéricas") agora **herdam uma das
8 sects anciãs** ao criar. Cada lineage define:

  • filosofia (i18n string)
  • bónus (display-only em v16.1; aplicação real em v16.8)
  • continente nativo (linghe / qianhe / yanshan / fenghuo / moyu)
  • rival ancestral (key da sect anciã rival)
  • tier (`righteous` | `demonic`)

8 lineages righteous + 1 demonic (Abyssal Depths) = 9 lineages total. A
demonic só é escolhível por players já alinhados ao Demonic Path
(faction_engine; em v16.2 isto migra para path_engine).

Espelha 100% a arquitectura do `core/continent_engine.py` (v16.0):
  - tuple de keys canónicas + meta dict (display + gating)
  - helpers puros para validação e lookup
  - 1 mutator com SAVEPOINT (begin_nested) — falha local não envenena
    a transacção do caller (mesmo padrão dos engines v15+).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from database.models import Sect, SectMember

logger = logging.getLogger(__name__)


# ── Canonical keys + display metadata ─────────────────────────────────────────

LINEAGE_KEYS: tuple[str, ...] = (
    "azure_cloud",
    "eternal_flame",
    "jade_harmony",
    "iron_mountain",
    "frozen_peak",
    "thousand_bloom",
    "silent_wind",
    "blazing_sun",
    "abyssal_depths",
)

LINEAGE_META: dict[str, dict[str, Any]] = {
    "azure_cloud": {
        "emoji": "☁️",
        "name_key": "lineage_azure_cloud",
        "philosophy_key": "lineage_azure_cloud_phil",
        "continent": "linghe",
        "tier": "righteous",
        "rival": "blazing_sun",
        "bonuses": {"mobility": 0.10, "qi_regen": 0.05},
    },
    "eternal_flame": {
        "emoji": "🔥",
        "name_key": "lineage_eternal_flame",
        "philosophy_key": "lineage_eternal_flame_phil",
        "continent": "linghe",
        "tier": "righteous",
        "rival": "thousand_bloom",
        "bonuses": {"alchemy_quality": 0.08, "fire_dmg": 0.10},
    },
    "jade_harmony": {
        "emoji": "🪷",
        "name_key": "lineage_jade_harmony",
        "philosophy_key": "lineage_jade_harmony_phil",
        "continent": "linghe",
        "tier": "righteous",
        "rival": "abyssal_depths",
        "bonuses": {"defense": 0.10, "healing": 0.15},
    },
    "iron_mountain": {
        "emoji": "🏔️",
        "name_key": "lineage_iron_mountain",
        "philosophy_key": "lineage_iron_mountain_phil",
        "continent": "qianhe",
        "tier": "righteous",
        "rival": "silent_wind",
        "bonuses": {"body_tempering": 0.15, "hp_max": 0.10},
    },
    "frozen_peak": {
        "emoji": "❄️",
        "name_key": "lineage_frozen_peak",
        "philosophy_key": "lineage_frozen_peak_phil",
        "continent": "qianhe",
        "tier": "righteous",
        "rival": "eternal_flame",
        "bonuses": {"ice_dmg": 0.20, "defense": 0.10},
    },
    "thousand_bloom": {
        "emoji": "🌸",
        "name_key": "lineage_thousand_bloom",
        "philosophy_key": "lineage_thousand_bloom_phil",
        "continent": "yanshan",
        "tier": "righteous",
        "rival": "eternal_flame",
        "bonuses": {"herb_yield": 0.20, "pill_potency": 0.10},
    },
    "silent_wind": {
        "emoji": "🌬️",
        "name_key": "lineage_silent_wind",
        "philosophy_key": "lineage_silent_wind_phil",
        "continent": "yanshan",
        "tier": "righteous",
        "rival": "iron_mountain",
        "bonuses": {"speed": 0.15, "first_strike": 0.10},
    },
    "blazing_sun": {
        "emoji": "☀️",
        "name_key": "lineage_blazing_sun",
        "philosophy_key": "lineage_blazing_sun_phil",
        "continent": "fenghuo",
        "tier": "righteous",
        "rival": "azure_cloud",
        "bonuses": {"fire_dmg": 0.20, "forge_quality": 0.10},
    },
    "abyssal_depths": {
        "emoji": "💀",
        "name_key": "lineage_abyssal_depths",
        "philosophy_key": "lineage_abyssal_depths_phil",
        "continent": "moyu",
        "tier": "demonic",
        "rival": "jade_harmony",
        "bonuses": {"forbidden_unlock": True, "dao_dark": 0.15},
    },
}

# Rivalry multiplier applied to BP contributed in Sect War when attacker
# and defender are ancestral rivals. Narrative-coded: lineage hostility
# bleeds into the modern era.
RIVAL_BP_MULTIPLIER = 1.5


# ── Validation + lookup ───────────────────────────────────────────────────────

def is_valid_lineage(key: str | None) -> bool:
    return isinstance(key, str) and key in LINEAGE_META


def get_lineage_meta(key: str) -> dict[str, Any]:
    """Return the meta dict for `key`. Raises KeyError if unknown."""
    if not is_valid_lineage(key):
        raise KeyError(f"unknown lineage: {key!r}")
    return LINEAGE_META[key]


def get_rival_lineage(key: str) -> str | None:
    """Return the canonical rival key for `key`, or None if unknown."""
    if not is_valid_lineage(key):
        return None
    return LINEAGE_META[key].get("rival")


def is_demonic_lineage(key: str | None) -> bool:
    """True if this lineage is demonic-only (Abyssal Depths)."""
    if not is_valid_lineage(key):
        return False
    return LINEAGE_META[key].get("tier") == "demonic"


def get_lineage_continent(key: str) -> str | None:
    if not is_valid_lineage(key):
        return None
    return LINEAGE_META[key].get("continent")


# ── Player faction gate (for demonic lineage) ─────────────────────────────────

async def _player_is_demonic(session, player_id: int) -> bool:
    """True if the player walks the Demonic Path.

    v16.2: ``path_engine`` is the canonical source of truth. We resolve
    via ``get_player_path_raw`` first (raw value, so NULL stays NULL and
    we don't gate a never-picked player out of an Abyssal Depths choice
    they're entitled to pick later). Only when path is unset do we fall
    back to the legacy ``faction_engine`` for backwards-compat with
    pre-v16.2 players whose path migration may not have completed yet.

    Defensive at every layer: any failure → treat as non-demonic
    (safe default — denies the gate, never grants it).
    """
    # Primary: path_engine.
    try:
        from core.path_engine import get_player_path_raw, is_demonic_path
        raw_path = await get_player_path_raw(session, player_id)
        if raw_path is not None:
            return is_demonic_path(raw_path)
    except Exception:
        logger.debug("path lookup failed for player_id=%s", player_id, exc_info=True)

    # Fallback: legacy faction (pre-v16.2 players who never had a path
    # row backfilled, or installations where the migration is mid-deploy).
    try:
        from core.faction_engine import get_player_faction
    except Exception:
        return False
    try:
        faction = await get_player_faction(session, player_id)
    except Exception:
        logger.debug("faction lookup failed for player_id=%s", player_id, exc_info=True)
        return False
    if faction is None:
        return False
    fid = (
        getattr(faction, "faction_id", None)
        or getattr(faction, "id", None)
        or getattr(faction, "key", None)
    )
    return str(fid or "").lower().startswith("demon")


# ── Sect accessors ────────────────────────────────────────────────────────────

async def get_sect_lineage(session, sect_id) -> str | None:
    """Return the lineage_key stored on `sect_id`, or None if unset/missing.

    Never raises — used in display paths.
    """
    try:
        row = (await session.execute(
            select(Sect.lineage_key).where(Sect.id == sect_id)
        )).first()
    except Exception:
        logger.debug("get_sect_lineage failed for sect_id=%s", sect_id, exc_info=True)
        return None
    if not row:
        return None
    key = row[0]
    return key if is_valid_lineage(key) else None


async def set_sect_lineage(
    session,
    sect_id,
    lineage_key: str,
    actor_player_id: int,
) -> dict[str, Any]:
    """Persist the lineage choice for `sect_id`.

    Gating (server-authoritative):
      • Actor must be a member of `sect_id` AND rank in {master, elder}.
      • `lineage_key` must be a known LINEAGE_KEYS entry.
      • Demonic lineages (Abyssal Depths) require the actor to be on the
        Demonic Path. Faction lookup is defensive — failure denies, not
        allows.
      • Sect must not already have a lineage set (irreversible in v16.1;
        v16.x might add "lineage reborn" via quest).

    Returns: ``{"ok": True, "lineage_key": str, "chosen_at": datetime}``
    or ``{"ok": False, "reason": str, ...}``.

    Uses ``session.begin_nested()`` (SAVEPOINT) so a partial failure (e.g.,
    a defensive validation rejecting the write mid-way) does not poison
    the outer transaction. Caller commits.
    """
    if not is_valid_lineage(lineage_key):
        return {"ok": False, "reason": "invalid_lineage"}

    sect = (await session.execute(
        select(Sect).where(Sect.id == sect_id).with_for_update()
    )).scalar_one_or_none()
    if sect is None:
        return {"ok": False, "reason": "sect_not_found"}

    if sect.lineage_key:
        # Lineage is irreversible in v16.1. Surface gracefully so the
        # mini-app can render an info modal instead of an error toast.
        return {
            "ok": False,
            "reason": "lineage_already_set",
            "current": sect.lineage_key,
        }

    member = (await session.execute(
        select(SectMember).where(
            SectMember.sect_id == sect_id,
            SectMember.player_id == actor_player_id,
        )
    )).scalar_one_or_none()
    if member is None:
        return {"ok": False, "reason": "not_in_sect"}
    if member.rank not in ("master", "elder"):
        return {"ok": False, "reason": "rank_too_low"}

    # v16.2 — Rogue path cannot host any lineage. Done before the demonic
    # check so the error message stays specific to the player's path.
    try:
        from core.path_engine import (
            can_path_join_lineage_tier, get_player_path_raw, is_rogue_path,
        )
        raw_path = await get_player_path_raw(session, actor_player_id)
        if is_rogue_path(raw_path):
            return {"ok": False, "reason": "rogue_no_lineage"}
        if raw_path is not None:
            target_tier = LINEAGE_META[lineage_key].get("tier")
            if not can_path_join_lineage_tier(raw_path, target_tier):
                return {"ok": False, "reason": "path_lineage_mismatch"}
    except Exception:
        # Defensive: fall through to legacy demonic check below.
        logger.debug("path gate failed for actor=%s", actor_player_id, exc_info=True)

    if is_demonic_lineage(lineage_key):
        if not await _player_is_demonic(session, actor_player_id):
            return {"ok": False, "reason": "demonic_locked"}

    now = datetime.now(timezone.utc)
    async with session.begin_nested():
        sect.lineage_key = lineage_key
        sect.lineage_chosen_at = now

    logger.info(
        "sect_lineage_set: sect_id=%s lineage=%s actor=%s",
        sect_id, lineage_key, actor_player_id,
    )
    return {"ok": True, "lineage_key": lineage_key, "chosen_at": now}


# ── Sect-War rival hit calculation ────────────────────────────────────────────

def compute_rival_bonus(
    attacker_lineage: str | None,
    defender_lineage: str | None,
) -> float:
    """Return the BP multiplier for a Sect War hit between two sects.

    Returns ``RIVAL_BP_MULTIPLIER`` (1.5) when the attacker's lineage names
    the defender's lineage as its ancestral rival. Otherwise 1.0.

    Asymmetry is intentional: the spec defines rivalry per-lineage (e.g.,
    Frozen Peak grudges Eternal Flame, but Eternal Flame's bigger feud is
    with Thousand Bloom). Caller passes ``(attacker, defender)`` in that
    order; the bonus applies only to the attacking side.
    """
    if not is_valid_lineage(attacker_lineage):
        return 1.0
    if not is_valid_lineage(defender_lineage):
        return 1.0
    if attacker_lineage == defender_lineage:
        return 1.0
    if LINEAGE_META[attacker_lineage].get("rival") == defender_lineage:
        return RIVAL_BP_MULTIPLIER
    return 1.0


# ── Display helpers (mini-app + chat) ─────────────────────────────────────────

# Pretty labels for bonus keys — surfaced informational-only in v16.1.
# Each maps to an i18n key (`lineage_bonus_<key>`). When v16.8 ships the
# real gameplay application, this map stays the source of truth for
# display naming.
BONUS_KEYS: tuple[str, ...] = (
    "mobility", "qi_regen", "alchemy_quality", "fire_dmg",
    "defense", "healing", "body_tempering", "hp_max",
    "ice_dmg", "herb_yield", "pill_potency", "speed",
    "first_strike", "forge_quality", "forbidden_unlock", "dao_dark",
)


def _format_bonus_value(key: str, raw: Any) -> str:
    """Project the raw bonus value into a human-readable delta string.

    Numeric bonuses → ``+10%`` (no decimals beyond what's needed).
    Boolean bonuses → ``✓`` (unlock indicators have their own label).
    """
    if isinstance(raw, bool):
        return "✓" if raw else "—"
    try:
        pct = float(raw) * 100.0
    except (TypeError, ValueError):
        return str(raw)
    # Show integers without trailing .0 (most bonuses are 5/10/15/20%).
    if pct == int(pct):
        return f"+{int(pct)}%"
    return f"+{pct:.1f}%"


def get_all_lineages_for_display(lang: str) -> list[dict[str, Any]]:
    """Return all 9 lineages projected for UI consumption.

    Each entry::

        {
            key, emoji, tier, continent, rival,
            name, philosophy,
            bonuses: [{key, label, value}],
            is_demonic: bool,
        }

    Display order matches ``LINEAGE_KEYS`` (Líng / Qiān / Yǎn / Fēng /
    Mòyǔ — lore-canonical, demonic last).
    """
    from core.i18n import t as i18n_t

    out: list[dict[str, Any]] = []
    for key in LINEAGE_KEYS:
        meta = LINEAGE_META[key]
        bonuses_proj = []
        for bk, bv in (meta.get("bonuses") or {}).items():
            bonuses_proj.append({
                "key": bk,
                "label": i18n_t(lang, f"lineage_bonus_{bk}"),
                "value": _format_bonus_value(bk, bv),
                "raw": bv,
            })
        out.append({
            "key": key,
            "emoji": meta["emoji"],
            "tier": meta["tier"],
            "continent": meta["continent"],
            "rival": meta.get("rival"),
            "name": i18n_t(lang, meta["name_key"]),
            "philosophy": i18n_t(lang, meta["philosophy_key"]),
            "bonuses": bonuses_proj,
            "is_demonic": is_demonic_lineage(key),
        })
    return out


def project_lineage_for_display(key: str | None, lang: str) -> dict[str, Any] | None:
    """Project a single lineage (by key) for UI. Returns None if unknown.

    Used by ``api_sect`` to embed ``lineage_meta_resolved`` directly in
    the sect payload, so the SectTab can render the lineage card without
    a second round-trip to ``world/lineage_info``.
    """
    if not is_valid_lineage(key):
        return None
    from core.i18n import t as i18n_t

    meta = LINEAGE_META[key]
    rival_key = meta.get("rival")
    rival_meta = LINEAGE_META.get(rival_key) if rival_key else None
    bonuses_proj = []
    for bk, bv in (meta.get("bonuses") or {}).items():
        bonuses_proj.append({
            "key": bk,
            "label": i18n_t(lang, f"lineage_bonus_{bk}"),
            "value": _format_bonus_value(bk, bv),
            "raw": bv,
        })
    return {
        "key": key,
        "emoji": meta["emoji"],
        "tier": meta["tier"],
        "continent": meta["continent"],
        "rival": rival_key,
        "rival_emoji": rival_meta["emoji"] if rival_meta else None,
        "rival_name": i18n_t(lang, rival_meta["name_key"]) if rival_meta else None,
        "name": i18n_t(lang, meta["name_key"]),
        "philosophy": i18n_t(lang, meta["philosophy_key"]),
        "bonuses": bonuses_proj,
        "is_demonic": is_demonic_lineage(key),
    }
