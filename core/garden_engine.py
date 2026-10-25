"""core/garden_engine.py — Sprint 4: Horta 灵田 (Spiritual Field).

The first RICH input source for the Mortal-flesh band (BC-6): a small grid of
plots where the R0–R6 cultivator plants spiritual herbs that mature over time
(idle, timestamp-based like the Cavern — NO per-player job) and, on harvest,
yield TEMPER PROGRESS toward the next Mortal tier (player.mortal_temper_progress).
That banked progress DISCOUNTS the qi cost of the next "Temperar a Carne"
(body_tempering_engine.HORTA_QI_DISCOUNT) — so the Horta is the PATIENT path that
paces the body with TIME instead of Qi (BC-4), next to Sprint 3's fast pedras+qi.

Server-gated by `cultivo_corpo_r0` (same Corpo axis — NO new flag) at the CALLER
(endpoint/handler), exactly like the temper ACTION. Harvest NEVER grants qi or
qi_capacity (BC-5). Wipe-safe: GARDEN_HERBS is an engine constant; the plots are
light per-player state (player_garden_plots). On `main` (flag OFF) the endpoints
refuse and nothing is ever written → the 57 are untouched.

Concurrency / atomicity: every WRITE assumes the CALLER holds ``player`` FOR
UPDATE and owns the commit; the plot rows are additionally locked here. Plant
debits stones all-or-nothing; harvest is idempotent (an unready/empty slot is a
disclosed no-op that mutates nothing).
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from database.models import PlayerGardenPlot

logger = logging.getLogger(__name__)

# ── Tuning (env-overridable — owner reviews; Lei §6) ───────────────────────────
GARDEN_PLOTS = int(os.getenv("GARDEN_PLOTS", "4"))

# The herb catalog (engine-not-DB → wipe-safe). grow_seconds scales with the
# reward so all herbs are ~equally efficient per real-hour but differ in cadence
# (short = more attention, long = set-and-forget). cost_stones is cheap; harvest
# yields `temper_progress` points toward the next Mortal tier (NEVER qi — BC-5).
GARDEN_HERBS = {
    "erva_serena":  {"emoji": "🌿", "grow_seconds": 1800,  "cost_stones": 100,  "temper_progress": 20,  "min_realm": 0},
    "lotus_jade":   {"emoji": "🪷", "grow_seconds": 5400,  "cost_stones": 300,  "temper_progress": 70,  "min_realm": 0},
    "raiz_ferro":   {"emoji": "🌰", "grow_seconds": 14400, "cost_stones": 800,  "temper_progress": 220, "min_realm": 0},
    "flor_sangue":  {"emoji": "🌺", "grow_seconds": 43200, "cost_stones": 2000, "temper_progress": 700, "min_realm": 0},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def garden_plot_count() -> int:
    return GARDEN_PLOTS


def _herb(herb_key):
    return GARDEN_HERBS.get(herb_key) if herb_key else None


def is_ready(plot, now: datetime = None) -> bool:
    """True iff the plot holds a planted herb that has finished growing."""
    if plot is None or not plot.herb_key or not plot.planted_at:
        return False
    info = _herb(plot.herb_key)
    if not info:
        return False
    now = now or _now()
    return (now - plot.planted_at).total_seconds() >= float(info["grow_seconds"])


async def _get_plots(session, player_id: int, *, for_update: bool = False) -> dict:
    stmt = select(PlayerGardenPlot).where(PlayerGardenPlot.player_id == int(player_id))
    if for_update:
        stmt = stmt.with_for_update()
    rows = (await session.execute(stmt)).scalars().all()
    return {int(r.slot_index): r for r in rows}


def _remaining_seconds(plot, info, now: datetime) -> int:
    if not plot.planted_at:
        return 0
    return max(0, int(float(info["grow_seconds"]) - (now - plot.planted_at).total_seconds()))


# ── Projection (READ) ──────────────────────────────────────────────────────────

async def project_garden(session, player) -> dict:
    """READ — the Horta surface: the N plots (empty / growing / ready) + the Mortal
    temper-progress bar toward the next tier + the plantable catalog with
    affordability. No state change. The caller gates on `cultivo_corpo_r0`."""
    from core.body_tempering_engine import (
        MIN_REALM_REQUIRED, MORTAL_BAND_MAX, mortal_progress_required,
    )
    now = _now()
    plots = await _get_plots(session, player.telegram_id)
    realm = int(getattr(player, "realm", 0) or 0)

    slots = []
    for i in range(GARDEN_PLOTS):
        p = plots.get(i)
        if p is None or not p.herb_key:
            slots.append({"slot": i, "state": "empty"})
            continue
        info = _herb(p.herb_key) or {}
        ready = is_ready(p, now)
        slots.append({
            "slot": i,
            "state": "ready" if ready else "growing",
            "herb_key": p.herb_key,
            "herb_emoji": info.get("emoji", "🌱"),
            "temper_progress": int(info.get("temper_progress", 0)),
            "remaining_seconds": 0 if ready else _remaining_seconds(p, info, now),
            "ready_at_ms": (
                int((p.planted_at + timedelta(seconds=float(info.get("grow_seconds", 0)))).timestamp() * 1000)
                if p.planted_at else None
            ),
        })

    mlvl = max(0, min(int(getattr(player, "mortal_body_level", 0) or 0), MORTAL_BAND_MAX))
    target = (mlvl + 1) if mlvl < MORTAL_BAND_MAX else None
    req = mortal_progress_required(target)
    progress = int(getattr(player, "mortal_temper_progress", 0) or 0)

    catalog = []
    for key, info in GARDEN_HERBS.items():
        catalog.append({
            "herb_key": key,
            "emoji": info["emoji"],
            "cost_stones": int(info["cost_stones"]),
            "grow_seconds": int(info["grow_seconds"]),
            "temper_progress": int(info["temper_progress"]),
            "can_afford": int(getattr(player, "spirit_stones", 0) or 0) >= int(info["cost_stones"]),
        })

    # Sprint 5 — Caça 狩猎: fold the hunt-essence refine surface into the same
    # payload so the HortaCard shows both input sources from ONE poll (both feed
    # mortal_temper_progress). PURE (the caller gates on cultivo_corpo_r0).
    from core.hunt_engine import project_hunt
    # Sprint 6 — Ambiental 环境: fold the extreme-environment site surface into the
    # same payload so the HortaCard shows all THREE input sources from ONE poll
    # (Horta/Caça/Ambiental all feed mortal_temper_progress). PURE; lazy import to
    # avoid a load-time cycle (environment_engine ← body_tempering_engine).
    from core.environment_engine import project_environment
    # Sprint 7 — Combate 顿悟: fold the insight surface (4th faucet cooldown + whether a 顿悟
    # charge is held) into the same payload. PURE; the caller gates on cultivo_corpo_r0.
    from core.insight_engine import project_insight
    return {
        "ok": True,
        "is_apex": realm >= MIN_REALM_REQUIRED,
        "plot_count": GARDEN_PLOTS,
        "plots": slots,
        "stones": int(getattr(player, "spirit_stones", 0) or 0),
        "mortal_level": mlvl,
        "max_level": MORTAL_BAND_MAX,
        "temper_progress": progress,
        "progress_required": req,
        "progress_ready": bool(req is not None and progress >= req),
        "catalog": catalog,
        "hunt": project_hunt(player),
        "environment": project_environment(player),
        "insight": project_insight(player),
    }


# ── WRITE — plant ───────────────────────────────────────────────────────────────

async def do_plant(session, player, slot_index: int, herb_key: str) -> dict:
    """WRITE — plant an herb in an EMPTY slot. Debits stones all-or-nothing. Caller
    holds ``player`` FOR UPDATE + owns the commit. Refuses (no mutation) on a bad
    slot/herb, an occupied slot, or insufficient stones."""
    try:
        slot_index = int(slot_index)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "garden_bad_slot"}
    if slot_index < 0 or slot_index >= GARDEN_PLOTS:
        return {"ok": False, "reason": "garden_bad_slot"}
    info = _herb(herb_key)
    if not info:
        return {"ok": False, "reason": "garden_bad_herb"}

    # Concurrency note: the CALLER holds the PLAYER row FOR UPDATE — that lock is the
    # real serialization point for a never-planted slot (you cannot FOR UPDATE a row
    # that does not exist yet, so _get_plots(for_update) only locks already-existing
    # plot rows). Two concurrent first-plants on the same slot serialize on the player
    # lock: the second sees the committed row and hits the busy guard below. Keep the
    # caller's player FOR UPDATE if this is ever refactored.
    plots = await _get_plots(session, player.telegram_id, for_update=True)
    p = plots.get(slot_index)
    if p is not None and p.herb_key:
        return {"ok": False, "reason": "garden_slot_busy", "slot": slot_index}

    cost = int(info["cost_stones"])
    if int(getattr(player, "spirit_stones", 0) or 0) < cost:
        return {"ok": False, "reason": "garden_need_stones", "cost_stones": cost,
                "stones": int(getattr(player, "spirit_stones", 0) or 0)}

    player.spirit_stones = max(0, int(player.spirit_stones or 0) - cost)
    now = _now()
    if p is None:
        session.add(PlayerGardenPlot(
            player_id=player.telegram_id, slot_index=slot_index,
            herb_key=herb_key, planted_at=now,
        ))
    else:
        # Re-use the existing (previously harvested) row for this slot.
        p.herb_key = herb_key
        p.planted_at = now
    return {"ok": True, "planted": True, "slot": slot_index, "herb_key": herb_key,
            "cost_stones": cost, "grow_seconds": int(info["grow_seconds"]),
            "stones": int(player.spirit_stones or 0)}


# ── WRITE — harvest ─────────────────────────────────────────────────────────────

async def do_harvest(session, player, slot_index: int) -> dict:
    """WRITE — harvest a MATURED plot → +temper_progress to mortal_temper_progress,
    then clear the slot. NEVER grants qi/qi_capacity (BC-5). Caller holds ``player``
    FOR UPDATE + owns the commit. Idempotent: an empty/unready slot is a disclosed
    no-op that mutates NOTHING (so a double-tap can't double-credit)."""
    try:
        slot_index = int(slot_index)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "garden_bad_slot"}
    if slot_index < 0 or slot_index >= GARDEN_PLOTS:
        return {"ok": False, "reason": "garden_bad_slot"}

    plots = await _get_plots(session, player.telegram_id, for_update=True)
    p = plots.get(slot_index)
    if p is None or not p.herb_key:
        return {"ok": False, "reason": "garden_empty", "slot": slot_index}
    now = _now()
    if not is_ready(p, now):
        info = _herb(p.herb_key) or {}
        return {"ok": False, "reason": "garden_not_ready", "slot": slot_index,
                "remaining_seconds": _remaining_seconds(p, info, now)}

    info = _herb(p.herb_key) or {}
    gain = int(info.get("temper_progress", 0))
    herb_key = p.herb_key
    player.mortal_temper_progress = int(getattr(player, "mortal_temper_progress", 0) or 0) + gain
    p.herb_key = None
    p.planted_at = None
    return {"ok": True, "harvested": True, "slot": slot_index, "herb_key": herb_key,
            "temper_progress_gained": gain,
            "temper_progress": int(player.mortal_temper_progress)}
