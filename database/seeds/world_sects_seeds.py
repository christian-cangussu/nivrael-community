"""v16.4 — Seeds for the 9 NPC World Sects (eternal lore-canon institutions).

Single source of truth lives in ``core.world_sects_engine.WORLD_SECT_META``
(absorbed verbatim from the v16.1 lineage engine). This seeder mirrors that
META into the ``world_sects`` table so ``Player.sect_id`` and the recruiter
pending rows have valid FK targets.

Idempotent: re-runs skip rows that already exist (by id). ``rival_id`` is set
in a SECOND pass because the rivalries form mutual cycles (azure_cloud ↔
blazing_sun, etc.) — inserting with rival_id up front would violate the
self-FK before the rival row exists. ``signature_techs`` is populated by a
THIRD force-update pass (v16.4c Sect Library) — the insert pass above is
insert-only, so the 9 already-seeded prod rows need an explicit UPDATE to pick
up the Library without a wipe (CLAUDE.md §4 seed-sync; mirrors the alchemy
``_PILL_FORCE_UPDATES`` idiom).
"""

import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WorldSect
from core.world_sects_engine import (
    WORLD_SECT_KEYS, WORLD_SECT_META, get_sect_signature_techs,
    SECT_SOUL_SCALARS, get_sect_soul,
)

logger = logging.getLogger(__name__)


async def run_world_sects_seed(session: AsyncSession) -> None:
    """Idempotently seed the 9 NPC sects into ``world_sects``."""
    existing_ids = set(
        (await session.execute(select(WorldSect.id))).scalars().all()
    )

    # ── Pass 1: insert missing rows (rival_id NULL for now) ──────────────
    added = 0
    for key in WORLD_SECT_KEYS:
        if key in existing_ids:
            continue
        meta = WORLD_SECT_META[key]
        session.add(WorldSect(
            id=key,
            name_key=meta["name_key"],
            emoji=meta["emoji"],
            tier=meta["tier"],
            continent_key=meta["continent_key"],
            rival_id=None,
            philosophy_key=meta["philosophy_key"],
            bonuses=dict(meta.get("bonuses") or {}),
            signature_techs=get_sect_signature_techs(key),  # v16.4c Sect Library
        ))
        added += 1

    if added:
        # Flush so the rows exist before the rival_id update pass references them.
        await session.flush()
        logger.info("🏯 Seeded %d world sects", added)

    # ── Pass 2: wire rival_id (idempotent — fixes any NULL holdovers too) ──
    rows = (await session.execute(select(WorldSect))).scalars().all()
    by_id = {r.id: r for r in rows}
    fixed = 0
    for key, meta in WORLD_SECT_META.items():
        rival = meta.get("rival")
        row = by_id.get(key)
        if row is not None and rival in by_id and row.rival_id != rival:
            row.rival_id = rival
            fixed += 1
    if fixed:
        logger.info("🏯 Wired %d world sect rivalries", fixed)

    # ── Pass 3: force-update signature_techs (v16.4c Sect Library) ───────────
    # The insert pass skips existing rows, so the 9 prod houses (seeded in
    # v16.4 with signature_techs=[]) need an explicit UPDATE to receive the
    # Library. Canonical data (SECT_LIBRARY) — safe to overwrite every boot;
    # the `!=` guard skips no-op writes so it stays quiet once synced.
    lib_updates = 0
    for key in WORLD_SECT_KEYS:
        techs = get_sect_signature_techs(key)
        row = by_id.get(key)
        if row is not None and row.signature_techs != techs:
            await session.execute(
                update(WorldSect).where(WorldSect.id == key).values(signature_techs=techs)
            )
            lib_updates += 1
    if lib_updates:
        logger.info("📜 Synced Sect Library onto %d world sect(s)", lib_updates)

    # ── Pass 4: World Pulse souls (force-update scalars; init strength once) ──
    # The 5 personality scalars (ambition/honor/greed/zeal/aggression) are
    # CANONICAL — force-synced from WORLD_SECT_SOUL every boot with a `!=` guard
    # (zero writes once synced). `strength` is the ACCRUING sim state: it is
    # initialized to the per-sect baseline ONLY the first time (last_pulse_at IS
    # NULL ⇒ the pulse never ran for this house), then never overwritten here —
    # preserving accrual (lesson das Cavernas). `momentum`/`last_pulse_at` are
    # NEVER touched by the seed (pure runtime state). The migration default for
    # the scalars is 0.5, so a freshly-migrated row picks up its true soul here.
    soul_updates = 0
    strength_inits = 0
    for key in WORLD_SECT_KEYS:
        row = by_id.get(key)
        if row is None:
            continue
        soul = get_sect_soul(key)
        for scalar in SECT_SOUL_SCALARS:
            target = float(soul[scalar])
            if abs(float(getattr(row, scalar) or 0.0) - target) > 1e-9:
                setattr(row, scalar, target)
                soul_updates += 1
        # One-time strength baseline init (never clobbers an accrued strength).
        if row.last_pulse_at is None:
            baseline = int(soul["strength"])
            if int(row.strength or 0) != baseline:
                row.strength = baseline
                strength_inits += 1
    if soul_updates:
        logger.info("💓 Synced World Pulse souls onto world sect(s) (%d scalar write(s))", soul_updates)
    if strength_inits:
        logger.info("💓 Initialized World Pulse strength baseline on %d house(s)", strength_inits)

    await session.commit()
