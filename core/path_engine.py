"""v16.2 — Path Trinity Engine (Pillar 3 of the v16 Living World).

Successor to the binary ``PlayerFaction`` system. Defines three first-class
paths a cultivator can walk:

    Righteous (正道) ☀️  — the 8 elder righteous sects (Azure Cloud,
                            Eternal Flame, Jade Harmony, Iron Mountain,
                            Frozen Peak, Thousand Bloom, Silent Wind,
                            Blazing Sun). +10% sect XP.
    Demonic   (魔道) 👹  — Abyssal Depths, exclusive to Mòyǔ. Unlocks
                            forbidden techniques + +10% dark qi.
    Rogue     (散修) 🐺  — no sect, no faction. +10% raw loot. Trades
                            freely with both sides but cannot host a
                            lineaged sect.

Where this lives in the v16 stack
=================================
This engine is the **bridge** between Path, Lineage (v16.1), and Continent
(v16.0):

    Player.path  ──→  set_player_path  ──→  policed by realm gate (R3+)
                                     │
                                     ├──→  unlocks Mòyǔ continent (Demonic)
                                     │     [continent_engine queries us]
                                     │
                                     └──→  bounds sect lineage tier
                                          [sect_lineage_engine queries us]

v16.3 will couple Karma → Path (auto-demotion to Rogue when karma diverges
from path alignment). v16.2 only delivers the Trinity; the karma spine
lands next sprint.

Architecture mirrors :mod:`core.continent_engine` and
:mod:`core.sect_lineage_engine`:
    • Tuple of canonical keys + meta dict (display + gating).
    • Pure helper functions for validation and lookup.
    • One mutator with SAVEPOINT (`begin_nested`) for safe error recovery
      inside a larger transaction.

NULL semantics: ``Player.path = NULL`` means *the player has never picked*,
not "the player is on no path." Reads default to ``"rogue"`` so unset
players still get a valid identity (Lei §1 — never silent void). But the
mutator can tell the difference: "first pick free" only fires when the
column is NULL.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from database.models import Player

logger = logging.getLogger(__name__)


# ── Canonical keys + display metadata ─────────────────────────────────────────

PATH_KEYS: tuple[str, ...] = ("righteous", "demonic", "rogue")

PATH_META: dict[str, dict[str, Any]] = {
    "righteous": {
        "emoji": "☀️",
        "name_key": "path_righteous",
        "philosophy_key": "path_righteous_phil",
        "tier": "celestial",
        # Which lineage tiers this path may join. Righteous walks among the
        # 8 elder righteous sects; demonic lineages refuse them.
        "allows_lineage_tiers": ("righteous",),
        "bonus": {"sect_xp": 0.10},
        "demonic_only_continent": False,
    },
    "demonic": {
        "emoji": "👹",
        "name_key": "path_demonic",
        "philosophy_key": "path_demonic_phil",
        "tier": "demonic",
        "allows_lineage_tiers": ("demonic",),
        "bonus": {"forbidden_unlock": True, "dark_qi": 0.10},
        # Unlocks Mòyǔ travel — continent_engine reads this flag indirectly
        # through is_demonic_path() to gate set_player_continent().
        "demonic_only_continent": True,
    },
    "rogue": {
        "emoji": "🐺",
        "name_key": "path_rogue",
        "philosophy_key": "path_rogue_phil",
        "tier": "neutral",
        # Rogue cultivators are solitary by canon — they may join no
        # lineaged sect (can still create/join lineage-NULL guild-style
        # sects, but the lineage chooser is permanently gated off for the
        # sect they belong to).
        "allows_lineage_tiers": (),
        "bonus": {"loot_raw": 0.10},
        "demonic_only_continent": False,
    },
}

DEFAULT_PATH = "rogue"

# Realm gate. A player must be at least at this realm before they can pick
# (or change) a path. Mirrors the legacy faction join gate (R3 = Core
# Formation) — the moment in cultivation when the inner alignment of the
# cultivator becomes externally legible.
PATH_PICK_MIN_REALM = 3


# ── Validation + lookup ───────────────────────────────────────────────────────

def is_valid_path(key: str | None) -> bool:
    return isinstance(key, str) and key in PATH_META


def get_path_meta(key: str) -> dict[str, Any]:
    """Return the meta dict for ``key``. Raises KeyError if unknown."""
    if not is_valid_path(key):
        raise KeyError(f"unknown path: {key!r}")
    return PATH_META[key]


def is_demonic_path(key: str | None) -> bool:
    """True if this path is the Demonic Path (魔道).

    Single source of truth for "is this player demonic?" — replaces the
    legacy faction-name string match (`fid.startswith("demon")`). Both
    ``continent_engine.set_player_continent`` (Mòyǔ gate) and
    ``sect_lineage_engine.set_sect_lineage`` (Abyssal Depths gate) call
    through here.
    """
    if not is_valid_path(key):
        return False
    return PATH_META[key].get("tier") == "demonic"


def is_righteous_path(key: str | None) -> bool:
    if not is_valid_path(key):
        return False
    return PATH_META[key].get("tier") == "celestial"


def is_rogue_path(key: str | None) -> bool:
    if not is_valid_path(key):
        return False
    return PATH_META[key].get("tier") == "neutral"


# ── Player accessors ──────────────────────────────────────────────────────────

async def get_player_path(session, player_id: int) -> str:
    """Return the player's current path, resolving NULL → ``DEFAULT_PATH``.

    Used by every gate that needs a definitive answer ("can this player
    walk into Mòyǔ?", "can this player's sect take Abyssal lineage?").
    Never raises — callers can use this in display paths without
    try/except.

    NULL in the DB means "never picked". For *gating* purposes that's
    equivalent to Rogue (the most permissive path on the demonic gate,
    the most restrictive on lineage joining). For *display* purposes the
    UI should still show the chooser if the player is R3+ and NULL — see
    :func:`get_player_path_state` for that drill-down.
    """
    try:
        row = (await session.execute(
            select(Player.path).where(Player.telegram_id == player_id)
        )).first()
    except Exception:
        logger.debug("get_player_path failed for player_id=%s", player_id, exc_info=True)
        return DEFAULT_PATH
    if not row:
        return DEFAULT_PATH
    key = row[0]
    return key if is_valid_path(key) else DEFAULT_PATH


async def get_player_path_raw(session, player_id: int) -> str | None:
    """Return the raw column value (NULL preserved).

    Used by the UI to distinguish "never picked" from "actively Rogue":
    the chooser appears for NULL but is hidden when the column already
    holds 'rogue' (player committed).
    """
    try:
        row = (await session.execute(
            select(Player.path).where(Player.telegram_id == player_id)
        )).first()
    except Exception:
        return None
    if not row:
        return None
    key = row[0]
    return key if is_valid_path(key) else None


async def set_player_path(session, player_id: int, path: str, *,
                          allow_recrystallize: bool = False) -> dict[str, Any]:
    """Persist the path choice for ``player_id``.

    .. note:: **INTERNAL-ONLY after v16.3.**
       The public HTTP picker (``/api/miniapp/path/pick``) became a 410
       dead-route in v16.2.1. As of v16.3 the *sole* legitimate caller
       is :func:`core.karma_engine.crystallize_path_for_player`, which
       fires automatically when a cultivator reaches R3 and the karma
       engine reads accumulated karma to derive the path. The function
       signature is preserved so the karma engine can call it; no other
       code (handlers, endpoints, scheduler jobs) should invoke it
       directly.

    Gating (server-authoritative):
        • ``path`` must be a known ``PATH_KEYS`` entry.
        • Player must be at ``PATH_PICK_MIN_REALM`` (R3+).
        • One-shot: if the column is already set, the write is rejected
          with ``path_already_set``. There are exactly **TWO** legitimate
          re-derivation channels, and both pass ``allow_recrystallize=True``:

          1. **TEC-5 Heart Demon Rite** (2026-08-03) — after a won rite whose
             winner chose ⚔️ ATRAVESSAR. Flag-gated (`forbidden_path`) inside
             :mod:`core.forbidden_path_engine`, so on a world with the flag OFF
             this channel does not exist. The rite owns the consistency of the
             flip (sect eviction with the price stated up front) — see
             ``forbidden_path_engine.choose_heart_demon``.
          2. **轮回 Rebirth** (2026-08-14, report do [jogador]) —
             :func:`core.prestige_engine.process_prestige` re-derives the path
             from the karma the soul carries across lives. NOT flag-gated: it
             is the fix for a permanent dead end (a cultivator who crystallized
             Rogue with near-zero karma could never change path again on a world
             with `forbidden_path` OFF, and Rogue has no divergence trigger, so
             the game never even told him). It runs BEFORE the realm reset so
             the R3 gate below still passes.

    Returns: ``{"ok": True, "path": str, "previous": str|None}`` on
    success, or ``{"ok": False, "reason": str, ...}`` on rejection.

    Uses ``session.begin_nested()`` (SAVEPOINT) — failures don't poison
    the outer transaction. Caller commits.
    """
    if not is_valid_path(path):
        return {"ok": False, "reason": "path_invalid"}

    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id).with_for_update()
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}

    realm = int(player.realm or 0)
    if realm < PATH_PICK_MIN_REALM:
        return {"ok": False, "reason": "realm_too_low",
                "required_realm": PATH_PICK_MIN_REALM, "current_realm": realm}

    previous = player.path if is_valid_path(player.path) else None
    if previous is not None and not allow_recrystallize:
        # v16.2: first pick is free, but re-picks land in v16.3 with the
        # karma cooldown. Reject explicitly so the UI shows the right CTA.
        return {"ok": False, "reason": "path_already_set", "current": previous}
    if previous is not None and previous == path:
        # TEC-5 — atravessar para o caminho que já se anda não é travessia.
        return {"ok": False, "reason": "path_already_set", "current": previous}

    async with session.begin_nested():
        player.path = path

    logger.info(
        "player_path_set: player_id=%s path=%s previous=%s",
        player_id, path, previous,
    )
    return {"ok": True, "path": path, "previous": previous}


# ── Bridges to lineage + continent gates ──────────────────────────────────────

def can_path_join_lineage_tier(path: str | None, lineage_tier: str | None) -> bool:
    """True if a player on ``path`` may join a sect whose lineage has
    ``lineage_tier``.

    Used by :mod:`core.sect_lineage_engine` (Abyssal Depths gate) and by
    the future Sect-Guild Split (v16.4) when wiring NPC sect recruitment.

    Rules:
        • Righteous → only ``righteous`` lineages.
        • Demonic   → only ``demonic`` lineages.
        • Rogue     → no lineage at all (rogues are solitary by canon).
        • None/invalid path → treat as Rogue (most restrictive on join).
    """
    if not is_valid_path(path):
        path = DEFAULT_PATH
    allowed = PATH_META[path].get("allows_lineage_tiers") or ()
    return lineage_tier in allowed if lineage_tier else False


async def can_player_join_lineage(
    session, player_id: int, lineage_key: str | None
) -> bool:
    """Convenience: resolves player's path + lineage tier, then checks.

    Returns False on any lookup failure (defensive — denies access, never
    grants it implicitly).
    """
    if not lineage_key:
        return False
    try:
        from core.sect_lineage_engine import get_lineage_meta, is_valid_lineage
        if not is_valid_lineage(lineage_key):
            return False
        tier = get_lineage_meta(lineage_key).get("tier")
    except Exception:
        return False
    try:
        path = await get_player_path(session, player_id)
    except Exception:
        return False
    return can_path_join_lineage_tier(path, tier)


# ── Display helpers (mini-app + chat) ─────────────────────────────────────────

# Bonus key labels — same pattern as `lineage_bonus_*`. Server-rendered via
# `lineage_bonus_*` reuse where the key already exists (forbidden_unlock,
# dark_qi); new bonus keys (sect_xp, loot_raw) get their own i18n entries.
PATH_BONUS_LABEL_KEYS: dict[str, str] = {
    "sect_xp": "path_bonus_sect_xp",
    "loot_raw": "path_bonus_loot_raw",
    "dark_qi": "path_bonus_dark_qi",
    "forbidden_unlock": "path_bonus_forbidden_unlock",
}


def _format_bonus_value(raw: Any) -> str:
    """Match the lineage engine's bonus formatting (``+10%`` / ``✓``)."""
    if isinstance(raw, bool):
        return "✓" if raw else "—"
    try:
        pct = float(raw) * 100.0
    except (TypeError, ValueError):
        return str(raw)
    if pct == int(pct):
        return f"+{int(pct)}%"
    return f"+{pct:.1f}%"


def get_all_paths_for_display(lang: str) -> list[dict[str, Any]]:
    """Return all three paths projected for UI consumption.

    Each entry::

        {
            key, emoji, tier,
            name, philosophy,
            bonuses: [{key, label, value, raw}],
            allowed_lineage_tiers: [...],
            is_demonic: bool,
            is_righteous: bool,
            is_rogue: bool,
        }

    Display order matches ``PATH_KEYS`` (Righteous → Demonic → Rogue —
    canonical: light, shadow, freedom).
    """
    from core.i18n import t as i18n_t

    out: list[dict[str, Any]] = []
    for key in PATH_KEYS:
        meta = PATH_META[key]
        bonuses_proj = []
        for bk, bv in (meta.get("bonus") or {}).items():
            label_key = PATH_BONUS_LABEL_KEYS.get(bk, f"path_bonus_{bk}")
            bonuses_proj.append({
                "key": bk,
                "label": i18n_t(lang, label_key),
                "value": _format_bonus_value(bv),
                "raw": bv,
            })
        out.append({
            "key": key,
            "emoji": meta["emoji"],
            "tier": meta["tier"],
            "name": i18n_t(lang, meta["name_key"]),
            "philosophy": i18n_t(lang, meta["philosophy_key"]),
            "bonuses": bonuses_proj,
            "allowed_lineage_tiers": list(meta.get("allows_lineage_tiers") or ()),
            "is_demonic": is_demonic_path(key),
            "is_righteous": is_righteous_path(key),
            "is_rogue": is_rogue_path(key),
        })
    return out


def project_path_for_display(key: str | None, lang: str) -> dict[str, Any] | None:
    """Project a single path (by key) for UI. Returns None if unknown.

    Used by ``api_player`` to embed ``path_meta_resolved`` directly in
    the player payload so PlayerHeader can render the chip without a
    second round-trip.
    """
    if not is_valid_path(key):
        return None
    from core.i18n import t as i18n_t

    meta = PATH_META[key]
    bonuses_proj = []
    for bk, bv in (meta.get("bonus") or {}).items():
        label_key = PATH_BONUS_LABEL_KEYS.get(bk, f"path_bonus_{bk}")
        bonuses_proj.append({
            "key": bk,
            "label": i18n_t(lang, label_key),
            "value": _format_bonus_value(bv),
            "raw": bv,
        })
    return {
        "key": key,
        "emoji": meta["emoji"],
        "tier": meta["tier"],
        "name": i18n_t(lang, meta["name_key"]),
        "philosophy": i18n_t(lang, meta["philosophy_key"]),
        "bonuses": bonuses_proj,
        "allowed_lineage_tiers": list(meta.get("allows_lineage_tiers") or ()),
        "is_demonic": is_demonic_path(key),
        "is_righteous": is_righteous_path(key),
        "is_rogue": is_rogue_path(key),
    }
