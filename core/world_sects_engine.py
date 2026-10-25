"""v16.4 — World Sects engine (the 9 eternal NPC institutions).

Single source of truth for the 9 Great Houses of Wuxia canon. These are NPC
institutions — DISTINCT from player guilds (the `sects` table, renamed
lexically to "Guild"). A cultivator is RECRUITED into an NPC sect by living
the world (Path + Continent + Karma + Lineage holdover → affinity), never by
a menu picker and never with jade (Lei §4).

Design lineage: this engine ABSORBS the v16.1 `sect_lineage_engine` seed —
the 9 lineage keys (azure_cloud .. abyssal_depths) become the canonical NPC
sect ids verbatim, so existing guild `lineage_key` values are valid FK
targets + affinity holdover signals without any re-mapping.

Mirrors the canonical engine pattern of `core/path_engine.py`,
`core/continent_engine.py`, `core/karma_engine.py`:
    * module-level META dict keyed by canonical lowercase key
    * pure validation/lookup helpers
    * async DB accessors (session first arg, defensive try/except)
    * SAVEPOINT-wrapped mutator via ``session.begin_nested()``
    * display projection resolving i18n via ``core.i18n.t``

i18n reuse: the 9 sects share the v16.1 lineage strings, so name/philosophy/
bonus labels reuse the existing ``lineage_<key>`` / ``lineage_<key>_phil`` /
``lineage_bonus_<bk>`` keys (already shipped + translated in 3 locales).
Display projections resolve them server-side, so the mini-app receives ready
strings (it does not need the lineage keys in its own i18n bundle).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from database.models import Player, WorldSect

logger = logging.getLogger(__name__)

# ── Canonical keys (lore order: Líng → Qiān → Yǎn → Fēng → Mòyǔ; demonic last)
WORLD_SECT_KEYS: tuple[str, ...] = (
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

# ── Sect rank ladder. v16.4 only granted `disciple` on join; v16.4c (Sect
# Library + Ranks) builds the climb: disciple (the canon "Outer Disciple") →
# inner → core → elder → heir (the canon "Successor"; player-attainable cap —
# Grand Elder / Sect Master stay NPC-reserved, lore §2). 'elder' is inserted
# BEFORE 'heir', which is additive: every existing member is 'disciple', so no
# stored sect_rank value is invalidated (only 'heir' would shift, and no player
# has it yet). The tuple ORDER is the promotion order; a rank's index is its
# ordinal — used as the `sect_rank_reached` achievement target_value.
SECT_RANKS: tuple[str, ...] = ("disciple", "inner", "core", "elder", "heir")
DEFAULT_SECT_RANK = "disciple"

# ── Rank progression tuning (engine constants, not DB — per CLAUDE.md DB rules).
# Promotion is SILENT + automatic: every contribution gain re-evaluates the
# highest rank whose `sect_contribution` threshold AND realm gate are both met,
# and advances to it (never demotes — wipe-safe, never strips a paying player).
# Disclosed in the Hall (Lei §1) so the cultivator always sees the next gate.
SECT_RANK_THRESHOLDS: dict[str, int] = {
    "disciple": 0, "inner": 50, "core": 200, "elder": 600, "heir": 1500,
}
SECT_RANK_REALM_GATES: dict[str, int] = {
    "disciple": 0, "inner": 1, "core": 3, "elder": 5, "heir": 7,
}

# Per-rank perk scale. The Hall DISCLOSES each house's `bonuses` scaled by this
# fraction (Lei §1 — the cultivator sees their growing favour). The MECHANICAL
# application of these bonuses is deliberately DEFERRED to the wipe (v16.5),
# where the whole sect/technique/combat economy re-tunes together — wiring a new
# combat modifier mid-beta would perturb the just-shipped v16.7 balance and is a
# balance change the owner reserved for the wipe (Lei §5). The concrete v16.4c
# mechanical reward for climbing is the Sect Library (rank-gated technique
# unlocks, additive + safe) + the rank prestige/achievements.
RANK_PERK_SCALE: dict[str, float] = {
    "disciple": 0.25, "inner": 0.50, "core": 0.75, "elder": 1.00, "heir": 1.25,
}

# Tribute: a stone sink that lets a cultivator BUY contribution toward the next
# rank (agency — never wait-only, Lei §1). Deliberately steep so ranks still
# mean dedication; quests are the cheaper, narrative path.
TRIBUTE_STONES_PER_POINT = 25

# ── The 9 Great Houses ────────────────────────────────────────────────────
# Mirror of v16.1 LINEAGE_META verbatim (emoji / tier / continent / rival /
# bonuses). name_key / philosophy_key reuse the existing lineage i18n keys.
WORLD_SECT_META: dict[str, dict[str, Any]] = {
    "azure_cloud": {
        "emoji": "☁️",
        "name_key": "lineage_azure_cloud",
        "philosophy_key": "lineage_azure_cloud_phil",
        "continent_key": "linghe",
        "tier": "righteous",
        "rival": "blazing_sun",
        "bonuses": {"mobility": 0.10, "qi_regen": 0.05},
    },
    "eternal_flame": {
        "emoji": "🔥",
        "name_key": "lineage_eternal_flame",
        "philosophy_key": "lineage_eternal_flame_phil",
        "continent_key": "linghe",
        "tier": "righteous",
        "rival": "thousand_bloom",
        "bonuses": {"alchemy_quality": 0.08, "fire_dmg": 0.10},
    },
    "jade_harmony": {
        "emoji": "🪷",
        "name_key": "lineage_jade_harmony",
        "philosophy_key": "lineage_jade_harmony_phil",
        "continent_key": "linghe",
        "tier": "righteous",
        "rival": "abyssal_depths",
        "bonuses": {"defense": 0.10, "healing": 0.15},
    },
    "iron_mountain": {
        "emoji": "🏔️",
        "name_key": "lineage_iron_mountain",
        "philosophy_key": "lineage_iron_mountain_phil",
        "continent_key": "qianhe",
        "tier": "righteous",
        "rival": "silent_wind",
        "bonuses": {"body_tempering": 0.15, "hp_max": 0.10},
    },
    "frozen_peak": {
        "emoji": "❄️",
        "name_key": "lineage_frozen_peak",
        "philosophy_key": "lineage_frozen_peak_phil",
        "continent_key": "qianhe",
        "tier": "righteous",
        "rival": "eternal_flame",
        "bonuses": {"ice_dmg": 0.20, "defense": 0.10},
    },
    "thousand_bloom": {
        "emoji": "🌸",
        "name_key": "lineage_thousand_bloom",
        "philosophy_key": "lineage_thousand_bloom_phil",
        "continent_key": "yanshan",
        "tier": "righteous",
        "rival": "eternal_flame",
        "bonuses": {"herb_yield": 0.20, "pill_potency": 0.10},
    },
    "silent_wind": {
        "emoji": "🌬️",
        "name_key": "lineage_silent_wind",
        "philosophy_key": "lineage_silent_wind_phil",
        "continent_key": "yanshan",
        "tier": "righteous",
        "rival": "iron_mountain",
        "bonuses": {"speed": 0.15, "first_strike": 0.10},
    },
    "blazing_sun": {
        "emoji": "☀️",
        "name_key": "lineage_blazing_sun",
        "philosophy_key": "lineage_blazing_sun_phil",
        "continent_key": "fenghuo",
        "tier": "righteous",
        "rival": "azure_cloud",
        "bonuses": {"fire_dmg": 0.20, "forge_quality": 0.10},
    },
    "abyssal_depths": {
        "emoji": "💀",
        "name_key": "lineage_abyssal_depths",
        "philosophy_key": "lineage_abyssal_depths_phil",
        "continent_key": "moyu",
        "tier": "demonic",
        "rival": "jade_harmony",
        "bonuses": {"forbidden_unlock": True, "dao_dark": 0.15},
    },
}


# ── World Pulse Fase 1 — the soul of each house (Crusader Kings scalars) ──────
# 5 hidden personality scalars (0..1) + a per-sect `strength` baseline, seeded
# into world_sects by the seed-sync (Pass 4 of run_world_sects_seed) and read by
# the deterministic `world_pulse_job` to bias each house's weighted-utility action
# menu. "Cada uma com a sua alma" (Lei §3 depth) — NOT a generic default:
#   * ambition   → drives recruit / claim_node
#   * honor      → high = stable righteous defenders; low = enables internal_strife
#   * greed      → drives raid_rival (with aggression)
#   * zeal       → the Dao-devout default (fortify / seek_inheritance)
#   * aggression → drives raid_rival
# Demonic Abyssal Depths = high ambition/greed/aggression, low honor; the
# righteous houses lean honor/zeal. `strength` is an ABSTRACT new number (Lei §5)
# that does NOT buff players — only the world's narrative. These scalars are
# CANONICAL (force-synced every boot); `strength`/`momentum`/`last_pulse_at`
# ACCRUE at runtime and are preserved (lesson das Cavernas).
WORLD_SECT_SOUL: dict[str, dict[str, float]] = {
    #                 ambition  honor  greed  zeal  aggression  strength
    "azure_cloud":    {"ambition": 0.55, "honor": 0.80, "greed": 0.25, "zeal": 0.65, "aggression": 0.45, "strength": 110},
    "eternal_flame":  {"ambition": 0.80, "honor": 0.60, "greed": 0.45, "zeal": 0.75, "aggression": 0.70, "strength": 130},
    "jade_harmony":   {"ambition": 0.40, "honor": 0.92, "greed": 0.20, "zeal": 0.82, "aggression": 0.22, "strength": 120},
    "iron_mountain":  {"ambition": 0.55, "honor": 0.80, "greed": 0.35, "zeal": 0.70, "aggression": 0.58, "strength": 135},
    "frozen_peak":    {"ambition": 0.50, "honor": 0.75, "greed": 0.30, "zeal": 0.72, "aggression": 0.50, "strength": 115},
    "thousand_bloom": {"ambition": 0.45, "honor": 0.82, "greed": 0.52, "zeal": 0.70, "aggression": 0.24, "strength": 110},
    "silent_wind":    {"ambition": 0.66, "honor": 0.58, "greed": 0.46, "zeal": 0.60, "aggression": 0.66, "strength": 115},
    "blazing_sun":    {"ambition": 0.82, "honor": 0.64, "greed": 0.40, "zeal": 0.64, "aggression": 0.82, "strength": 140},
    "abyssal_depths": {"ambition": 0.95, "honor": 0.15, "greed": 0.90, "zeal": 0.55, "aggression": 0.90, "strength": 130},
}

# The 5 personality scalars (canonical, force-synced) vs the accruing state.
SECT_SOUL_SCALARS: tuple[str, ...] = ("ambition", "honor", "greed", "zeal", "aggression")
SECT_SOUL_STRENGTH_DEFAULT = 100


def get_sect_soul(key: str | None) -> dict[str, float]:
    """Return a house's personality soul ({ambition,honor,greed,zeal,aggression,
    strength}), or a neutral default for an unknown key."""
    soul = WORLD_SECT_SOUL.get(key or "")
    if soul is not None:
        return dict(soul)
    return {s: 0.5 for s in SECT_SOUL_SCALARS} | {"strength": SECT_SOUL_STRENGTH_DEFAULT}


# ── O Chamado (Pedra 2) — the soul-derived invitation tone ──────────────────
# The recruiter no longer DMs a cold "affinity >= 75"; the house COURTS the
# cultivator in its own voice, derived from the Pedra 1 soul scalars (Lei §3
# reuse, Lei §2 Wuxia): an ambitious/aggressive house calls with urgency and
# challenge, an honourable/zealous one with ceremony and respect, a greedy one
# with the promise of treasure. Each house maps DETERMINISTICALLY to one of 3
# tones, so the Chamado is pure narrative + disclosure — ZERO balance (Lei §5).
CALL_TONES: tuple[str, ...] = ("urgent", "honor", "greed")


def select_call_tone(sect_key: str | None) -> str:
    """Pick a house's Chamado tone from its soul scalars (deterministic).

    'urgent' (ambition+aggression) · 'honor' (honor+zeal) · 'greed' (greed,
    weighted so the single greediest house — Abyssal Depths — courts with the
    treasure voice rather than the urgent one)."""
    s = get_sect_soul(sect_key)
    scores = {
        "urgent": s["ambition"] + s["aggression"],
        "honor": s["honor"] + s["zeal"],
        "greed": 2.1 * s["greed"],
    }
    return max(CALL_TONES, key=lambda k: scores[k])


def project_sect_call(sect_id: str | None, lang: str, *, score: int | None = None) -> dict[str, Any] | None:
    """The Chamado — a soul-derived invitation for a house. Returns
    ``{tone, text, emoji}`` (text server-resolved so the mini-app receives it
    ready, like sect names), or None for an unknown house. Pure narrative +
    disclosure; the affinity SCORE is shown (Lei §1)."""
    if not is_valid_sect(sect_id):
        return None
    from core.i18n import t as i18n_t

    meta = WORLD_SECT_META[sect_id]
    emoji = meta.get("emoji") or "🏯"
    name = i18n_t(lang, meta.get("name_key") or "")
    tone = select_call_tone(sect_id)
    text = i18n_t(lang, f"wsect_call_{tone}", emoji=emoji, sect=name, score=int(score or 0))
    return {"tone": tone, "text": text, "emoji": emoji}


def resolve_master_name(player) -> str | None:
    """The cultivator's named shifu 师徒 (Pedra 2). Returns the persisted
    ``sect_master_name`` or, for a member whose column is still NULL (every
    existing member), a DETERMINISTIC Wuxia name seeded by (sect_id,
    telegram_id) — stable across renders and identical to what
    :func:`join_player_to_sect` would persist. None when unaffiliated."""
    sect_id = getattr(player, "sect_id", None)
    if not is_valid_sect(sect_id):
        return None
    stored = getattr(player, "sect_master_name", None)
    if stored:
        return stored
    return master_name_for(sect_id, getattr(player, "telegram_id", 0) or 0)


def master_name_for(sect_id: str, player_id: int) -> str:
    """Deterministic shifu name for (sect, cultivator). Seeded so the same
    cultivator always sees the same master (idempotent persist + display)."""
    import random as _random
    from core.npc_cultivator_engine import generate_npc_name
    return generate_npc_name(_random.Random(f"shifu:{sect_id}:{player_id}"))


# ── Sect Library (v16.4c) ──────────────────────────────────────────────────
# Each house guards 5 signature arts, one unlockable at each rank. The catalog
# rows (ids 500-544) live in database/seeds/combat_seeds.SECT_TECHNIQUES; this
# dict is the SINGLE SOURCE for the rank→tech unlock map AND the seed that
# force-updates world_sects.signature_techs. Learning is ADDITIVE (a normal
# player_techniques row, no scroll) and the techs are EXCLUDED from drop/scroll
# pools via TechniqueCatalog.sect_key — the "Library = primary source + drop-cut"
# switch stays DEFERRED to the wipe (v16.5), so the live scroll economy of the
# 57 paying players is untouched (Lei §5). Entry: {tech_id, rank, tier}.
SECT_LIBRARY: dict[str, list[dict[str, Any]]] = {
    "azure_cloud": [
        {"tech_id": 500, "rank": "disciple", "tier": 1},
        {"tech_id": 501, "rank": "inner", "tier": 2},
        {"tech_id": 502, "rank": "core", "tier": 3},
        {"tech_id": 503, "rank": "elder", "tier": 4},
        {"tech_id": 504, "rank": "heir", "tier": 5},
    ],
    "eternal_flame": [
        {"tech_id": 505, "rank": "disciple", "tier": 1},
        {"tech_id": 506, "rank": "inner", "tier": 2},
        {"tech_id": 507, "rank": "core", "tier": 3},
        {"tech_id": 508, "rank": "elder", "tier": 4},
        {"tech_id": 509, "rank": "heir", "tier": 5},
    ],
    "jade_harmony": [
        {"tech_id": 510, "rank": "disciple", "tier": 1},
        {"tech_id": 511, "rank": "inner", "tier": 2},
        {"tech_id": 512, "rank": "core", "tier": 3},
        {"tech_id": 513, "rank": "elder", "tier": 4},
        {"tech_id": 514, "rank": "heir", "tier": 5},
    ],
    "iron_mountain": [
        {"tech_id": 515, "rank": "disciple", "tier": 1},
        {"tech_id": 516, "rank": "inner", "tier": 2},
        {"tech_id": 517, "rank": "core", "tier": 3},
        {"tech_id": 518, "rank": "elder", "tier": 4},
        {"tech_id": 519, "rank": "heir", "tier": 5},
    ],
    "frozen_peak": [
        {"tech_id": 520, "rank": "disciple", "tier": 1},
        {"tech_id": 521, "rank": "inner", "tier": 2},
        {"tech_id": 522, "rank": "core", "tier": 3},
        {"tech_id": 523, "rank": "elder", "tier": 4},
        {"tech_id": 524, "rank": "heir", "tier": 5},
    ],
    "thousand_bloom": [
        {"tech_id": 525, "rank": "disciple", "tier": 1},
        {"tech_id": 526, "rank": "inner", "tier": 2},
        {"tech_id": 527, "rank": "core", "tier": 3},
        {"tech_id": 528, "rank": "elder", "tier": 4},
        {"tech_id": 529, "rank": "heir", "tier": 5},
    ],
    "silent_wind": [
        {"tech_id": 530, "rank": "disciple", "tier": 1},
        {"tech_id": 531, "rank": "inner", "tier": 2},
        {"tech_id": 532, "rank": "core", "tier": 3},
        {"tech_id": 533, "rank": "elder", "tier": 4},
        {"tech_id": 534, "rank": "heir", "tier": 5},
    ],
    "blazing_sun": [
        {"tech_id": 535, "rank": "disciple", "tier": 1},
        {"tech_id": 536, "rank": "inner", "tier": 2},
        {"tech_id": 537, "rank": "core", "tier": 3},
        {"tech_id": 538, "rank": "elder", "tier": 4},
        {"tech_id": 539, "rank": "heir", "tier": 5},
    ],
    "abyssal_depths": [
        {"tech_id": 540, "rank": "disciple", "tier": 1},
        {"tech_id": 541, "rank": "inner", "tier": 2},
        {"tech_id": 542, "rank": "core", "tier": 3},
        {"tech_id": 543, "rank": "elder", "tier": 4},
        {"tech_id": 544, "rank": "heir", "tier": 5},
    ],
}


def get_sect_signature_techs(sect_id: str | None) -> list[dict[str, Any]]:
    """Return the house's Library list ({tech_id, rank, tier}), or []."""
    return list(SECT_LIBRARY.get(sect_id or "", []))


# ── Pure helpers ────────────────────────────────────────────────────────────
def is_valid_sect(key: str | None) -> bool:
    """True if ``key`` is one of the 9 canonical NPC sect keys."""
    return isinstance(key, str) and key in WORLD_SECT_META


def get_sect_meta(key: str) -> dict[str, Any]:
    """Return meta dict for ``key``; raises KeyError if invalid."""
    return WORLD_SECT_META[key]


def is_demonic_sect(key: str | None) -> bool:
    """True if this NPC sect is Demonic (tier == 'demonic')."""
    return is_valid_sect(key) and WORLD_SECT_META[key]["tier"] == "demonic"


def is_righteous_sect(key: str | None) -> bool:
    """True if this NPC sect is Righteous (tier == 'righteous')."""
    return is_valid_sect(key) and WORLD_SECT_META[key]["tier"] == "righteous"


def get_native_continent_for_sect(key: str) -> str | None:
    """Return the continent_key this NPC sect calls home, or None."""
    meta = WORLD_SECT_META.get(key)
    return meta["continent_key"] if meta else None


def get_rival_sect(key: str) -> str | None:
    """Return the rival NPC sect key, or None."""
    meta = WORLD_SECT_META.get(key)
    return meta.get("rival") if meta else None


def get_rank_label_key(rank: str | None) -> str:
    """Return the i18n key for a sect rank label (defaults to disciple)."""
    r = rank if rank in SECT_RANKS else DEFAULT_SECT_RANK
    return f"wsect_rank_{r}"


def _format_bonus_value(key: str, raw: Any) -> str:
    """Project a raw bonus value into a human-readable delta (mirror v16.1)."""
    if isinstance(raw, bool):
        return "✓" if raw else "—"
    try:
        pct = float(raw) * 100.0
    except (TypeError, ValueError):
        return str(raw)
    if pct == int(pct):
        return f"+{int(pct)}%"
    return f"+{pct:.1f}%"


# ── Display projection ──────────────────────────────────────────────────────
def project_sect_for_display(key: str | None, lang: str) -> dict[str, Any] | None:
    """Project a single NPC sect for UI. Returns None if unknown.

    Resolves name/philosophy/bonus labels server-side (chat i18n), so the
    mini-app receives ready strings.
    """
    if not is_valid_sect(key):
        return None
    from core.i18n import t as i18n_t

    meta = WORLD_SECT_META[key]
    rival_key = meta.get("rival")
    rival_meta = WORLD_SECT_META.get(rival_key) if rival_key else None
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
        "continent": meta["continent_key"],
        "rival": rival_key,
        "rival_emoji": rival_meta["emoji"] if rival_meta else None,
        "rival_name": i18n_t(lang, rival_meta["name_key"]) if rival_meta else None,
        "name": i18n_t(lang, meta["name_key"]),
        "philosophy": i18n_t(lang, meta["philosophy_key"]),
        "bonuses": bonuses_proj,
        "is_demonic": is_demonic_sect(key),
    }


def get_all_sects_for_display(lang: str) -> list[dict[str, Any]]:
    """Return all 9 NPC sects projected for UI (lore display order)."""
    out: list[dict[str, Any]] = []
    for key in WORLD_SECT_KEYS:
        proj = project_sect_for_display(key, lang)
        if proj:
            out.append(proj)
    return out


# ── DB accessors ──────────────────────────────────────────────────────────
async def get_player_sect_raw(session, player_id: int) -> str | None:
    """Return the player's NPC sect_id, or None (unaffiliated). Defensive."""
    try:
        row = (await session.execute(
            select(Player.sect_id).where(Player.telegram_id == player_id)
        )).first()
    except Exception:
        logger.debug("get_player_sect_raw failed for player_id=%s", player_id, exc_info=True)
        return None
    if not row:
        return None
    key = row[0]
    return key if is_valid_sect(key) else None


# Alias kept for symmetry with path/continent engines (no default fallback —
# being in no NPC sect is a valid state, unlike path/continent).
get_player_sect = get_player_sect_raw


async def get_player_sect_full(session, player_id: int, lang: str = "pt") -> dict[str, Any] | None:
    """Return the player's NPC sect membership projection, or None.

    {sect_id, rank, rank_key, joined_at_ms, meta: project_sect_for_display}
    """
    try:
        row = (await session.execute(
            select(Player.sect_id, Player.sect_rank, Player.sect_joined_at)
            .where(Player.telegram_id == player_id)
        )).first()
    except Exception:
        logger.debug("get_player_sect_full failed for player_id=%s", player_id, exc_info=True)
        return None
    if not row or not is_valid_sect(row[0]):
        return None
    sect_id, rank, joined_at = row[0], row[1], row[2]
    joined_ms = int(joined_at.timestamp() * 1000) if joined_at else None
    return {
        "sect_id": sect_id,
        "rank": rank or DEFAULT_SECT_RANK,
        "rank_key": get_rank_label_key(rank),
        "joined_at_ms": joined_ms,
        "meta": project_sect_for_display(sect_id, lang),
    }


async def join_player_to_sect(
    session,
    player_id: int,
    sect_id: str,
    *,
    rank: str = DEFAULT_SECT_RANK,
    affinity_score: int | None = None,
    source: str = "recruiter",
) -> dict[str, Any]:
    """Persist NPC sect membership. SAVEPOINT-wrapped, one-shot per player.

    A cultivator may belong to at most one NPC sect (Wuxia canon — the house
    that chose them). Re-joining while already affiliated is rejected. The
    Path hard-gate (Righteous cannot enter a Demonic house, vice-versa) is
    re-checked here defensively even though the recruiter only fires on a
    valid affinity. Fires Achievement #28 (Sect Heir) on first join.

    Returns ``{ok, reason?, sect_id?, rank?, previous?}``.
    """
    if not is_valid_sect(sect_id):
        return {"ok": False, "reason": "sect_invalid"}
    if rank not in SECT_RANKS:
        rank = DEFAULT_SECT_RANK

    try:
        async with session.begin_nested():
            player = (await session.execute(
                select(Player).where(Player.telegram_id == player_id).with_for_update()
            )).scalar_one_or_none()
            if player is None:
                return {"ok": False, "reason": "player_not_found"}

            previous = player.sect_id if is_valid_sect(player.sect_id) else None
            if previous is not None:
                return {"ok": False, "reason": "sect_already_joined", "current": previous}

            # Path hard-gate (defensive — affinity already enforces this).
            from core.path_engine import is_demonic_path
            player_path = player.path
            sect_is_demonic = is_demonic_sect(sect_id)
            path_is_demonic = is_demonic_path(player_path)
            if sect_is_demonic != path_is_demonic and (sect_is_demonic or path_is_demonic):
                # Demonic sect requires demonic path; non-demonic sect rejects
                # a demonic-path cultivator.
                if sect_is_demonic and not path_is_demonic:
                    return {"ok": False, "reason": "sect_path_mismatch"}
                if (not sect_is_demonic) and path_is_demonic:
                    return {"ok": False, "reason": "sect_path_mismatch"}

            player.sect_id = sect_id
            player.sect_rank = rank
            player.sect_joined_at = datetime.now(timezone.utc)
            # Pedra 2 — the Elder who courted you becomes your named shifu 师徒
            # (deterministic by (sect, cultivator); cosmetic identity, the bond's
            # mechanical bonus is DEFERRED to the wipe §4). Idempotent on re-join.
            if not getattr(player, "sect_master_name", None):
                player.sect_master_name = master_name_for(sect_id, player_id)
    except Exception:
        logger.exception(
            "join_player_to_sect SAVEPOINT failed (player_id=%s, sect=%s)",
            player_id, sect_id,
        )
        return {"ok": False, "reason": "internal_error"}

    logger.info(
        "world_sect_joined: player_id=%s sect=%s rank=%s source=%s affinity=%s",
        player_id, sect_id, rank, source, affinity_score,
    )

    # Achievement #28 Sect Heir — fired outside the SAVEPOINT, defensive.
    try:
        from core.achievement_engine import check_achievements
        await check_achievements(session, player_id, "world_sect_joined", 1)
    except Exception:
        logger.exception(
            "achievement bus failed inside join_player_to_sect (player_id=%s)", player_id,
        )

    # TEC-1 — auto-offer da Biblioteca: "as primeiras estantes se abrem".
    # Gated (biblioteca_seitas OFF ⇒ no-op sem query) + best-effort, fora do
    # SAVEPOINT como o achievement acima.
    try:
        from core.sect_library_engine import notify_library_opened
        await notify_library_opened(session, player_id, sect_id)
    except Exception:
        logger.debug("library auto-offer failed (player_id=%s)", player_id, exc_info=True)

    return {"ok": True, "sect_id": sect_id, "rank": rank, "previous": previous}


async def leave_player_from_sect(session, player_id: int) -> dict[str, Any]:
    """Leave / betray the NPC cultivation Sect (Pedra 2 follow-up — simple version).

    Clears the whole membership (sect_id / sect_rank / sect_joined_at /
    sect_contribution / sect_master_name) and applies the ``betray_sect_oath``
    karma (−75, already seeded). Quitting a Cultivation Sect IS breaking an oath —
    the world reads it (the karma drop lowers affinity to the just houses, so
    the Abyss grows more likely to court next; emergent, Wuxia).

    Owner decision (2026-06-16): NO technique lockout — ``PlayerTechnique`` is
    LEFT UNTOUCHED (techniques are wipe-bound; their re-economy lands at the
    wipe, not here). No cooldown column either — the recruiter's 7d dedup +
    affinity re-courts the cultivator naturally (⇒ zero migration).

    SAVEPOINT-wrapped + row-locked (mirrors join_player_to_sect). Idempotent:
    a cultivator with no sect → ``{ok: False, reason: "not_in_sect"}``. The
    karma write + audit run OUTSIDE the SAVEPOINT (defensive). Caller commits.

    Returns ``{ok, reason?, previous?, karma_delta?}``.
    """
    try:
        async with session.begin_nested():
            player = (await session.execute(
                select(Player).where(Player.telegram_id == player_id).with_for_update()
            )).scalar_one_or_none()
            if player is None:
                return {"ok": False, "reason": "player_not_found"}

            previous = player.sect_id if is_valid_sect(player.sect_id) else None
            if previous is None:
                return {"ok": False, "reason": "not_in_sect"}

            previous_rank = player.sect_rank
            # TEC-1 — as artes do Núcleo da casa LOCKAM ao sair (desequipa; o
            # registro em player_sect_techniques fica — voltar à MESMA casa
            # re-destranca). Gated (OFF ⇒ zero queries, main byte-idêntico) +
            # fail-safe interno; roda ANTES de limpar o vínculo para saber a
            # casa, dentro do mesmo SAVEPOINT (atômico com o leave).
            locked_arts: list[dict[str, Any]] = []
            try:
                from core.sect_library_engine import lock_core_arts_on_leave
                locked_arts = (await lock_core_arts_on_leave(
                    session, player_id, previous,
                    (getattr(player, "language", None) or "pt").lower()
                )).get("locked", [])
            except Exception:
                logger.debug("library lock-on-leave failed (player_id=%s)", player_id, exc_info=True)
            player.sect_id = None
            player.sect_rank = None
            player.sect_joined_at = None
            player.sect_contribution = 0
            player.sect_contribution_earned = 0  # wave 3 — leaving forfeits rank progress too
            player.sect_master_name = None
    except Exception:
        logger.exception("leave_player_from_sect SAVEPOINT failed (player_id=%s)", player_id)
        return {"ok": False, "reason": "internal_error"}

    logger.info(
        "world_sect_left: player_id=%s sect=%s rank=%s",
        player_id, previous, previous_rank,
    )

    # The betrayal — break the oath. Fired OUTSIDE the SAVEPOINT (defensive,
    # mirrors join_player_to_sect's achievement placement) so a karma failure
    # can never roll back the membership clear itself.
    karma_delta = -75
    try:
        from core.karma_engine import apply_karma
        kres = await apply_karma(
            session, player_id, "betray_sect_oath", metadata={"sect_id": previous}
        )
        if isinstance(kres, dict) and kres.get("delta") is not None:
            karma_delta = int(kres["delta"])
    except Exception:
        logger.exception("betray_sect_oath karma failed (player_id=%s)", player_id)

    # TEC-1 — key CONDICIONAL (lição MV-7): este dict é o payload do
    # world/sect_leave; com flag OFF locked_arts é sempre [] e a key fica
    # AUSENTE — main byte-idêntico.
    return {"ok": True, "previous": previous, "karma_delta": karma_delta,
            **({"locked_arts": locked_arts} if locked_arts else {})}


# ══════════════════════════════════════════════════════════════════════════
# v16.4c — Sect Library + Ranks: contribution, promotion, perks, learn, Hall
# ══════════════════════════════════════════════════════════════════════════

def rank_index(rank: str | None) -> int:
    """Ordinal of a rank in the ladder (0 = disciple). Invalid → 0."""
    r = rank if rank in SECT_RANKS else DEFAULT_SECT_RANK
    return SECT_RANKS.index(r)


def next_rank(rank: str | None) -> str | None:
    """The rank above ``rank``, or None if already at the cap (heir)."""
    idx = rank_index(rank)
    return SECT_RANKS[idx + 1] if idx + 1 < len(SECT_RANKS) else None


def eligible_rank(contribution: int, realm: int) -> str:
    """Highest rank whose contribution threshold AND realm gate are both met.

    Both ladders are monotonic, so the first rung that fails caps the climb
    (a huge contribution still can't outrun the realm gate — and vice versa).
    """
    contribution = int(contribution or 0)
    realm = int(realm or 0)
    best = DEFAULT_SECT_RANK
    for r in SECT_RANKS:
        if contribution >= SECT_RANK_THRESHOLDS.get(r, 0) and realm >= SECT_RANK_REALM_GATES.get(r, 0):
            best = r
        else:
            break
    return best


def ladder_contribution(earned: int | None, balance: int | None,
                        balance_tainted: bool = False) -> int:
    """A ÚNICA definição do número que a escada de posto lê.

    Regra base (Pedra 2 wave 3): a escada lê o LIFETIME-earned, para que uma
    compra no Pavilhão (que debita o saldo) nunca recue o posto. O fallback ao
    SALDO existe só como COMPAT para as linhas anteriores à Migration 118, que
    ainda têm `sect_contribution_earned = 0`.

    `balance_tainted` (TEC-2) desliga esse fallback. Motivo: a partir da doação
    de pergaminhos existe um faucet que credita SÓ o saldo (Lei §4 — jade
    entrega pergaminho, logo pergaminho não pode comprar posto). Para quem já
    doou, o saldo deixou de ser um proxy honesto do que foi GANHO, e o fallback
    passaria a promover pela porta dos fundos — não no instante da doação
    (`award_sect_contribution(credit_earned=False)` já pula a escada), mas na
    próxima vez que `recompute_player_rank` roda, o que acontece a CADA abertura
    do Salão. Sem esta linha, doar promove com um tap de atraso.

    Ninguém mais é afetado: para quem nunca doou (todos em `main`, todos hoje)
    `balance_tainted` é False e o comportamento fica byte-idêntico.
    """
    e = int(earned or 0)
    if e > 0 or balance_tainted:
        return e
    return max(0, int(balance or 0))


def _balance_is_tainted(player: Player) -> bool:
    """True se o saldo deste cultivador contém crédito que NÃO é escada.

    Marcador durável e de graça: `players.scroll_econ` (Migration 137) é
    não-NULL exatamente quando o cultivador já doou um pergaminho. Mora na
    MESMA row já travada — zero query extra. Defensivo por getattr para que
    uma row antiga (ou um fake de teste) nunca levante."""
    return getattr(player, "scroll_econ", None) is not None


def _apply_promotion(player: Player) -> dict[str, Any] | None:
    """Advance ``player.sect_rank`` to the highest eligible rung (never demote).

    Pure mutation on the (already-locked) Player row. Returns the promotion
    descriptor ({old, new, ordinal}) or None if no advance happened.
    """
    cur = player.sect_rank if player.sect_rank in SECT_RANKS else DEFAULT_SECT_RANK
    # UMA verdade do número da escada (ver ladder_contribution): lifetime-earned,
    # com o fallback COMPAT ao saldo — desligado para quem já doou pergaminho
    # (TEC-2), senão a doação promoveria pela porta dos fundos no próximo
    # recompute_player_rank. O > guard abaixo nunca rebaixa.
    earned = ladder_contribution(player.sect_contribution_earned,
                                 player.sect_contribution,
                                 _balance_is_tainted(player))
    target = eligible_rank(earned, player.realm or 0)
    if rank_index(target) > rank_index(cur):
        player.sect_rank = target
        return {"old": cur, "new": target, "ordinal": rank_index(target)}
    return None


async def _fire_promotion_effects(session, player_id: int, promo: dict[str, Any], source: str) -> None:
    """Achievement + narrative DM for a rank promotion. Defensive, fired OUTSIDE
    any SAVEPOINT (mirrors join_player_to_sect's achievement placement) so an
    effect failure can never roll back the promotion itself."""
    # Achievement #29/#30 — `sect_rank_reached` is a SET event (the value is the
    # absolute rank ordinal), so re-firing on a later promotion only ever raises
    # progress (see core/achievement_engine._SET_EVENTS).
    try:
        from core.achievement_engine import check_achievements
        await check_achievements(session, player_id, "sect_rank_reached", int(promo["ordinal"]))
    except Exception:
        logger.exception("sect promotion achievement bus failed (player_id=%s)", player_id)
    # Narrative note (Lei §1 — the cultivator is told the house recognized them).
    try:
        from core.notification_engine import notify
        await notify(
            session, player_id, "sect_promoted",
            title_key="wsect_promoted_title",
            body_key="wsect_promoted_body",
            payload={"rank_key": get_rank_label_key(promo["new"])},
            ref_id=f"sect_promo:{promo['new']}",
            icon="🏯", target_tab="profile", priority=3,
        )
    except Exception:
        logger.debug("sect promotion notify failed (player_id=%s)", player_id, exc_info=True)
    # TEC-1 — a promoção que abre estante REAL avisa (inner → Interna,
    # core → Núcleo). Gated + best-effort, aditivo.
    try:
        from core.sect_library_engine import notify_shelf_unlocked
        await notify_shelf_unlocked(session, player_id, promo["new"])
    except Exception:
        logger.debug("library shelf notify failed (player_id=%s)", player_id, exc_info=True)


async def award_sect_contribution(session, player_id: int, amount: int, *, source: str = "sect_quest",
                                  credit_earned: bool = True) -> dict[str, Any]:
    """Add NPC-sect contribution and auto-promote if a threshold is crossed.

    The SINGLE mutator for the NPC-sect rank currency (separate from the GUILD's
    SectMember.contribution_points). Row-locks the Player, increments, then
    re-evaluates the rank ladder. Idempotency rides on the CALLER (a quest claim
    is already one-shot under its own lock); this just serializes concurrent
    contribution writes. Returns {ok, contribution?, promotion?, reason?}.

    ``credit_earned=False`` (TEC-2) credits ONLY the spendable balance and
    SKIPS the ladder entirely — used by the scroll donation, where paper must
    buy purchasing power inside the house but never a RANK (Lei §4: jade
    hands out scrolls via Celestial Pass / Battle Pass / fragment exchange, so
    a scroll that promoted would mean jade buying progression). Skipping the
    ladder is not cosmetic: `_apply_promotion` falls back to the BALANCE when
    lifetime-earned is 0 (the state of every fresh cultivator), so merely
    leaving `earned` untouched would still promote them. Default True keeps
    the two live call sites (quest claim / sect hall) byte-identical."""
    amount = max(0, int(amount or 0))
    # populate_existing=True: callers (quest claim / Hall) pre-load this Player
    # UNLOCKED before we get here, so the identity-map copy can be stale vs a
    # concurrent committed contribution write. The FOR UPDATE acquires the lock
    # but does NOT refresh in-memory attributes by itself — populate_existing
    # overwrites them with the freshly-locked DB row so the increment is computed
    # from current truth (autoflush flushes our own pending writes first, so no
    # clobber). Closes a lost-update on earned/paid sect_contribution.
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}
    if not is_valid_sect(player.sect_id):
        return {"ok": False, "reason": "not_in_sect"}

    if amount:
        # wave 3 — credit BOTH the spendable balance and the lifetime-earned
        # accumulator (the rank ladder reads earned; the Pavilion spends balance).
        player.sect_contribution = max(0, int(player.sect_contribution or 0) + amount)
        if credit_earned:
            player.sect_contribution_earned = max(0, int(player.sect_contribution_earned or 0) + amount)
    promo = _apply_promotion(player) if credit_earned else None
    if promo:
        await _fire_promotion_effects(session, player_id, promo, source)
    return {"ok": True, "contribution": int(player.sect_contribution or 0), "promotion": promo}


async def tribute_stones(session, player_id: int, stones: int) -> dict[str, Any]:
    """Convert spirit stones into sect contribution (a stone sink + agency).

    ``stones`` is the amount the cultivator offers; we consume only the largest
    multiple of TRIBUTE_STONES_PER_POINT they can afford and credit the points.
    Row-locked + auto-promotes. Returns {ok, points?, stones_spent?,
    contribution?, promotion?, reason?}.
    """
    stones = max(0, int(stones or 0))
    # populate_existing: the chat caller pre-loads this Player UNLOCKED, so the
    # identity-map copy can be stale vs a concurrent committed write. Same
    # lost-update fix already applied to the three sibling writers
    # (award_sect_contribution / buy_merit_reward / learn_library_technique).
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}
    if not is_valid_sect(player.sect_id):
        return {"ok": False, "reason": "not_in_sect"}

    affordable = min(stones, int(player.spirit_stones or 0))
    points = affordable // TRIBUTE_STONES_PER_POINT
    if points <= 0:
        return {"ok": False, "reason": "tribute_too_small",
                "min_stones": TRIBUTE_STONES_PER_POINT}
    spent = points * TRIBUTE_STONES_PER_POINT
    player.spirit_stones = int(player.spirit_stones or 0) - spent
    # wave 3 — credit both balance + lifetime-earned (see award_sect_contribution).
    player.sect_contribution = max(0, int(player.sect_contribution or 0) + points)
    player.sect_contribution_earned = max(0, int(player.sect_contribution_earned or 0) + points)
    promo = _apply_promotion(player)
    if promo:
        await _fire_promotion_effects(session, player_id, promo, "tribute")
    return {
        "ok": True, "points": int(points), "stones_spent": int(spent),
        "contribution": int(player.sect_contribution or 0),
        "spirit_stones": int(player.spirit_stones or 0), "promotion": promo,
    }


async def recompute_player_rank(session, player_id: int, *, source: str = "recompute") -> dict[str, Any] | None:
    """Re-evaluate + apply promotion for a member (e.g. when realm rose since the
    last contribution gain). Row-locked. Returns the promotion descriptor or None."""
    # populate_existing: the Hall endpoint pre-loads this Player UNLOCKED before
    # calling us, so refresh from the locked DB row (autoflush flushes our own
    # pending writes first) — see award_sect_contribution for the full rationale.
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None or not is_valid_sect(player.sect_id):
        return None
    promo = _apply_promotion(player)
    if promo:
        await _fire_promotion_effects(session, player_id, promo, source)
    return promo


async def learn_sect_technique(session, player_id: int, tech_id: int) -> dict[str, Any]:
    """Learn a house signature art from the Library — ADDITIVE, rank-gated, NO
    scroll (distinct from the scroll-consuming combat learn). Row-locked +
    idempotent on the PlayerTechnique composite PK. Returns {ok, ...} / {ok:False, reason}."""
    from core.i18n import catalog_name
    from database.models import PlayerTechnique, TechniqueCatalog

    tech_id = int(tech_id)
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id).with_for_update()
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}
    if not is_valid_sect(player.sect_id):
        return {"ok": False, "reason": "not_in_sect"}

    entry = next((e for e in SECT_LIBRARY.get(player.sect_id, []) if e["tech_id"] == tech_id), None)
    if entry is None:
        return {"ok": False, "reason": "tech_not_in_library"}

    cur_idx = rank_index(player.sect_rank)
    if cur_idx < rank_index(entry["rank"]):
        return {"ok": False, "reason": "rank_too_low",
                "req_rank_key": get_rank_label_key(entry["rank"])}

    existing = (await session.execute(
        select(PlayerTechnique).where(
            PlayerTechnique.player_id == player_id,
            PlayerTechnique.technique_id == tech_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return {"ok": False, "reason": "already_learned"}

    tech = (await session.execute(
        select(TechniqueCatalog).where(TechniqueCatalog.id == tech_id)
    )).scalar_one_or_none()
    if tech is None:
        return {"ok": False, "reason": "tech_not_found"}
    if (player.realm or 0) < (tech.req_realm or 0):
        return {"ok": False, "reason": "realm_too_low", "req_realm": int(tech.req_realm or 0)}

    # Slot-aware auto-equip (mirror of api_combat_learn_technique).
    auto_equip = True
    if tech.tech_type == "combat":
        try:
            from core.combat_engine import get_max_combat_techniques
            max_slots = get_max_combat_techniques(int(player.realm or 0))
            active = (await session.execute(
                select(func.count())
                .select_from(PlayerTechnique)
                .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
                .where(
                    PlayerTechnique.player_id == player_id,
                    PlayerTechnique.is_active_combat == True,  # noqa: E712
                    TechniqueCatalog.tech_type == "combat",
                )
            )).scalar() or 0
            if int(active) >= max_slots:
                auto_equip = False
        except Exception:
            logger.debug("learn_sect_technique slot check failed (player_id=%s)", player_id, exc_info=True)

    session.add(PlayerTechnique(
        player_id=player_id, technique_id=tech_id,
        mastery_level=1, is_active_combat=auto_equip,
    ))
    return {
        "ok": True, "tech_id": tech_id,
        # 名 2026-09-14 — o toast fala a lingua da carta que acabou de mudar.
        "name": catalog_name((player.language or "pt").lower(), "tech", tech),
        "emoji": tech.emoji or "⚔️",
        "auto_equipped": bool(auto_equip), "tier": entry["tier"],
        "rank_key": get_rank_label_key(entry["rank"]),
    }


def compute_rank_perks(sect_id: str | None, rank: str | None, lang: str) -> list[dict[str, Any]]:
    """Project a house's bonuses scaled by the member's rank — for DISCLOSURE.

    Lei §1: the Hall shows the cultivator their growing favour. NOTE: mechanical
    application is DEFERRED to the wipe (see RANK_PERK_SCALE) — these values are
    the disclosed preview of the house's blessing, not a live combat modifier
    yet. Returns [{key, label, value, raw, deferred}]."""
    meta = WORLD_SECT_META.get(sect_id or "")
    if not meta:
        return []
    from core.i18n import t as i18n_t
    scale = RANK_PERK_SCALE.get(rank if rank in RANK_PERK_SCALE else DEFAULT_SECT_RANK, 0.25)
    out: list[dict[str, Any]] = []
    for bk, bv in (meta.get("bonuses") or {}).items():
        if isinstance(bv, bool):
            out.append({
                "key": bk, "label": i18n_t(lang, f"lineage_bonus_{bk}"),
                "value": _format_bonus_value(bk, bv), "raw": bv, "deferred": True,
            })
            continue
        scaled = round(float(bv) * scale, 4)
        out.append({
            "key": bk, "label": i18n_t(lang, f"lineage_bonus_{bk}"),
            "value": _format_bonus_value(bk, scaled), "raw": scaled, "deferred": True,
        })
    return out


async def get_sect_hall_state(session, player_id: int, lang: str = "pt") -> dict[str, Any]:
    """Compose the Sect Hall payload: membership + rank ladder + contribution
    progress + disclosed perks + the Library (unlocked/learned per tech). Member-
    gated — returns {in_sect: False} for non-members. Sect Quests are merged in
    by the caller (webserver/chat) to avoid a quest_engine import cycle."""
    from core.i18n import catalog_name, catalog_desc
    membership = await get_player_sect_full(session, player_id, lang)
    if membership is None:
        return {"in_sect": False}

    row = (await session.execute(
        select(Player.sect_contribution, Player.realm, Player.sect_master_name,
               Player.sect_contribution_earned, Player.scroll_econ)
        .where(Player.telegram_id == player_id)
    )).first()
    merit_balance = int((row[0] if row else 0) or 0)   # wave 3 — spendable (Merit Pavilion)
    realm = int((row[1] if row else 0) or 0)
    # O MESMO número que a escada promove (ladder_contribution) — senão o Salão
    # anunciaria um progresso de posto que a promoção não entrega (display-lie).
    contribution = ladder_contribution(
        (row[3] if row and len(row) > 3 else 0),
        merit_balance,
        bool(row[4] if row and len(row) > 4 else None),
    )

    sect_id = membership["sect_id"]
    rank = membership["rank"]
    cur_idx = rank_index(rank)

    # Pedra 2 — the named shifu (persisted, or deterministic fallback for the
    # existing members whose column is still NULL) + the house's LIVE strength
    # (World Pulse Fase 1) for the "bênção que espera" framing (Lei §1). Both are
    # pure DISPLAY — the master bond's bonus + the strength→blessing scaling stay
    # DEFERRED to the wipe (§4).
    master_name = (row[2] if row else None) or master_name_for(sect_id, player_id)
    try:
        strength = int((await session.execute(
            select(WorldSect.strength).where(WorldSect.id == sect_id)
        )).scalar() or 0)
    except Exception:
        logger.debug("sect strength read failed (player_id=%s, sect=%s)", player_id, sect_id, exc_info=True)
        strength = 0

    nxt = next_rank(rank)
    next_info = None
    if nxt:
        thr = SECT_RANK_THRESHOLDS.get(nxt, 0)
        gate = SECT_RANK_REALM_GATES.get(nxt, 0)
        next_info = {
            "rank_key": get_rank_label_key(nxt),
            "contribution_needed": int(thr),
            "contribution_have": contribution,
            "realm_gate": int(gate),
            "realm_met": realm >= gate,
            "contribution_met": contribution >= thr,
        }

    # Library: join the rank→tech map to the catalog + the player's learned set.
    from database.models import PlayerTechnique, TechniqueCatalog
    lib = SECT_LIBRARY.get(sect_id, [])
    tech_ids = [e["tech_id"] for e in lib]
    catalog: dict[int, Any] = {}
    learned_ids: set[int] = set()
    if tech_ids:
        catalog = {
            t.id: t for t in (await session.execute(
                select(TechniqueCatalog).where(TechniqueCatalog.id.in_(tech_ids))
            )).scalars().all()
        }
        learned_ids = set((await session.execute(
            select(PlayerTechnique.technique_id).where(
                PlayerTechnique.player_id == player_id,
                PlayerTechnique.technique_id.in_(tech_ids),
            )
        )).scalars().all())

    library: list[dict[str, Any]] = []
    for e in lib:
        tc = catalog.get(e["tech_id"])
        if tc is None:
            continue
        library.append({
            "tech_id": e["tech_id"],
            # 名 2026-09-14 — a Biblioteca da Casa fala a lingua do membro.
            "name": catalog_name(lang, "tech", tc),
            "emoji": tc.emoji or "⚔️",
            "tier": e["tier"],
            "rank": e["rank"],
            "rank_key": get_rank_label_key(e["rank"]),
            "req_realm": int(tc.req_realm or 0),
            "effect_type": tc.effect_type,
            "effect_value": float(tc.effect_value or 0.0),
            "description": catalog_desc(lang, "tech", tc),
            "unlocked": cur_idx >= rank_index(e["rank"]),
            "learned": e["tech_id"] in learned_ids,
        })

    return {
        "in_sect": True,
        "sect": membership.get("meta"),
        "sect_id": sect_id,
        "rank": rank,
        "rank_key": membership["rank_key"],
        "rank_index": cur_idx,
        "rank_cap_key": get_rank_label_key(SECT_RANKS[-1]),
        "contribution": contribution,
        "merit_balance": merit_balance,
        "realm": realm,
        "next_rank": next_info,
        "master_name": master_name,
        "strength": strength,
        "perks": compute_rank_perks(sect_id, rank, lang),
        "perks_deferred": True,
        "library": library,
        "tribute_rate": TRIBUTE_STONES_PER_POINT,
    }


# ══════════════════════════════════════════════════════════════════════════
# Pedra 2 wave 3 — Pavilhão de Mérito 功德阁 (spend contribution on house cosmetics)
# ══════════════════════════════════════════════════════════════════════════
# Per-house cosmetic TITLE rewards, BOUGHT with `sect_contribution` (the spendable
# balance; the rank ladder reads `sect_contribution_earned`, never touched here).
# Engine-not-DB catalog (wipe-safe, like SECT_LIBRARY / MYTHIC_ECHOES). Each reward
# grants a canonical title string into Player.unlocked_titles — the SAME cosmetic
# plumbing as VIP/BP extras (EXTRA_TITLE_DESC_KEYS + equip_title + the Honras
# section). Zero stat, zero jade (Lei §4/§5). `rank_min` gates the grand "legend"
# (DISCLOSED, Lei §1). Catalog filled by scripts/_pedra2_wave3_build.py (the title
# strings come from the content workflow); descriptions resolve via
# `title_desc_<reward_id>` (locales/*.json, server-resolved like the other titles).
MERIT_REWARDS: dict[str, list[dict[str, Any]]] = {
    "azure_cloud": [
        {"id": "azure_cloud_epithet", "title": "☁️ Andarilho das Nuvens", "cost": 150, "rank_min": None, "tier": "epithet"},
        {"id": "azure_cloud_legend", "title": "☁️ Guardião do Céu Aberto", "cost": 450, "rank_min": "core", "tier": "legend"},
    ],
    "eternal_flame": [
        {"id": "eternal_flame_epithet", "title": "🔥 Guardião da Brasa", "cost": 150, "rank_min": None, "tier": "epithet"},
        {"id": "eternal_flame_legend", "title": "🔥 Senhor das Mil Chamas Renascidas", "cost": 450, "rank_min": "core", "tier": "legend"},
    ],
    "jade_harmony": [
        {"id": "jade_harmony_epithet", "title": "🪷 Mão que Não Ergue a Lâmina", "cost": 150, "rank_min": None, "tier": "epithet"},
        {"id": "jade_harmony_legend", "title": "🪷 O Dao que Cura Mais do que Fere", "cost": 450, "rank_min": "core", "tier": "legend"},
    ],
    "iron_mountain": [
        {"id": "iron_mountain_epithet", "title": "🪨 Pele de Granito", "cost": 150, "rank_min": None, "tier": "epithet"},
        {"id": "iron_mountain_legend", "title": "🏔️ A Montanha que Caminha", "cost": 450, "rank_min": "core", "tier": "legend"},
    ],
    "frozen_peak": [
        {"id": "frozen_peak_epithet", "title": "❄️ Discípulo do Coração Sereno", "cost": 150, "rank_min": None, "tier": "epithet"},
        {"id": "frozen_peak_legend", "title": "❄️ Soberano do Gelo Imóvel", "cost": 450, "rank_min": "core", "tier": "legend"},
    ],
    "thousand_bloom": [
        {"id": "thousand_bloom_epithet", "title": "🌸 Botão de Mil Daos", "cost": 150, "rank_min": None, "tier": "epithet"},
        {"id": "thousand_bloom_legend", "title": "🌺 Jardineiro dos Mil Daos", "cost": 450, "rank_min": "core", "tier": "legend"},
    ],
    "silent_wind": [
        {"id": "silent_wind_epithet", "title": "🌬️ Passo que o Vento Engole", "cost": 150, "rank_min": None, "tier": "epithet"},
        {"id": "silent_wind_legend", "title": "🗡️ Lâmina que Ninguém Ouviu", "cost": 450, "rank_min": "core", "tier": "legend"},
    ],
    "blazing_sun": [
        {"id": "blazing_sun_epithet", "title": "🌅 Forjador do Primeiro Gume", "cost": 150, "rank_min": None, "tier": "epithet"},
        {"id": "blazing_sun_legend", "title": "☀️ Juiz Sem Sombra", "cost": 450, "rank_min": "core", "tier": "legend"},
    ],
    "abyssal_depths": [
        {"id": "abyssal_depths_epithet", "title": "💀 Faminto do Abismo", "cost": 150, "rank_min": None, "tier": "epithet"},
        {"id": "abyssal_depths_legend", "title": "👁️ Soberano do Vazio Devorador", "cost": 450, "rank_min": "core", "tier": "legend"},
    ],
}


def _merit_rewards_for(sect_id: str | None) -> list[dict[str, Any]]:
    return MERIT_REWARDS.get(sect_id or "", [])


def get_merit_reward(reward_id: str) -> dict[str, Any] | None:
    for rewards in MERIT_REWARDS.values():
        for r in rewards:
            if r.get("id") == reward_id:
                return r
    return None


async def get_merit_pavilion_state(session, player_id: int, lang: str = "pt") -> dict[str, Any]:
    """The Merit Pavilion payload: the member's spendable merit balance + their
    OWN house's cosmetic title rewards (owned / affordable / rank-locked, each with
    a server-resolved description). Member-gated → {in_sect: False} otherwise."""
    from core.i18n import t as i18n_t
    membership = await get_player_sect_full(session, player_id, lang)
    if membership is None:
        return {"in_sect": False, "rewards": []}
    row = (await session.execute(
        select(Player.sect_contribution, Player.sect_rank, Player.unlocked_titles)
        .where(Player.telegram_id == player_id)
    )).first()
    balance = int((row[0] if row else 0) or 0)
    rank = (row[1] if row else None) or DEFAULT_SECT_RANK
    owned = set(row[2] or []) if row else set()
    cur_idx = rank_index(rank)
    rewards = []
    for r in _merit_rewards_for(membership["sect_id"]):
        rmin = r.get("rank_min")
        rewards.append({
            "id": r["id"],
            "title": r["title"],
            "desc": i18n_t(lang, f"title_desc_{r['id']}"),
            "cost": int(r["cost"]),
            "tier": r.get("tier"),
            "rank_min": rmin,
            "rank_min_key": get_rank_label_key(rmin) if rmin else None,
            "owned": r["title"] in owned,
            "rank_ok": (rmin is None) or (cur_idx >= rank_index(rmin)),
            "affordable": balance >= int(r["cost"]),
        })
    return {"in_sect": True, "merit_balance": balance, "rewards": rewards}


async def buy_merit_reward(session, player_id: int, reward_id: str) -> dict[str, Any]:
    """Buy a cosmetic title from the Pavilion with `sect_contribution` (balance).

    Row-locked + idempotent (already-owned → no debit, no error-worthy state).
    Rank-gated + house-gated. Spends only the balance — the lifetime-earned rank
    currency is untouched, so a purchase NEVER recedes rank progress. Zero stat/jade.
    """
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}
    if not is_valid_sect(player.sect_id):
        return {"ok": False, "reason": "not_in_sect"}
    # House-gate: the reward must belong to the player's OWN house.
    if reward_id not in {r["id"] for r in _merit_rewards_for(player.sect_id)}:
        return {"ok": False, "reason": "invalid_reward"}
    reward = get_merit_reward(reward_id)
    titles = list(player.unlocked_titles or [])
    if reward["title"] in titles:
        return {"ok": False, "reason": "already_owned", "title": reward["title"]}
    rmin = reward.get("rank_min")
    if rmin is not None and rank_index(player.sect_rank or DEFAULT_SECT_RANK) < rank_index(rmin):
        return {"ok": False, "reason": "rank_too_low", "rank_min_key": get_rank_label_key(rmin)}
    cost = int(reward["cost"])
    if int(player.sect_contribution or 0) < cost:
        return {"ok": False, "reason": "insufficient_merit", "cost": cost,
                "balance": int(player.sect_contribution or 0)}
    player.sect_contribution = int(player.sect_contribution or 0) - cost
    titles.append(reward["title"])
    player.unlocked_titles = titles  # reassign so SQLAlchemy tracks the JSONB change
    return {"ok": True, "title": reward["title"], "tier": reward.get("tier"),
            "merit_balance": int(player.sect_contribution or 0)}
