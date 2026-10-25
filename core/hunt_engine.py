"""core/hunt_engine.py — Sprint 5: Caça de 3 partes 狩猎.

The SECOND input source for the Mortal-flesh band (BC-3). Beast EXPEDITIONS (the
existing system) in a `cultivo_corpo_r0` world bring back body-tempering materials
distilled into `hunt_essence`; the player REFINES essence into mortal_temper_progress
(the same patient currency the Horta produces — Sprint 4). So the hunt is a 2nd
faucet into the existing progress → qi-discount pipe, NOT a new system: Horta
(passive/idle) + Caça (active/expedition) both feed the same discount.

Server-gated by the SAME flag `cultivo_corpo_r0` (the Corpo axis — no new flag) and
realm < 7 (the band is R0–R6). Refining NEVER grants qi/qi_capacity (BC-5). The drop
hook lives in core/beast_engine.collect_expedition (gated + additive — main/OFF loot
is byte-identical). Wipe-safe: all numbers are engine constants; the only state is
the hunt_essence counter (Migration 125).
"""

import os

from core.body_tempering_engine import MIN_REALM_REQUIRED, _cultivo_corpo_on

# ── Tuning (env-overridable — owner reviews; Lei §6) ───────────────────────────
# Essence an expedition brings back, scaled by its duration (a clean difficulty
# proxy: 2h Herb → ~4, 24h Celestial → ~26). Conservative — a BONUS on top of the
# expedition's normal loot, never the main source (the Horta is faster per real-hour).
HUNT_ESSENCE_BASE = int(os.getenv("HUNT_ESSENCE_BASE", "2"))
HUNT_ESSENCE_PER_HOUR = float(os.getenv("HUNT_ESSENCE_PER_HOUR", "1.0"))
# Refine: spend a batch of essence → Mortal temper progress.
HUNT_REFINE_COST = int(os.getenv("HUNT_REFINE_COST", "10"))
HUNT_REFINE_YIELD = int(os.getenv("HUNT_REFINE_YIELD", "50"))


def expedition_essence_reward(expedition) -> int:
    """Essence a collected expedition brings back (gated by the CALLER). Scales with
    the expedition's duration_hours. 0 if no expedition row."""
    if expedition is None:
        return 0
    hours = float(getattr(expedition, "duration_hours", 0) or 0)
    return max(0, int(round(HUNT_ESSENCE_BASE + HUNT_ESSENCE_PER_HOUR * hours)))


def can_refine(player) -> dict:
    """Can this player refine a batch of hunt_essence into Mortal progress? Gated by
    `cultivo_corpo_r0` AND realm < 7. Returns {can, reason_key, cost, yield}."""
    base = {"cost": HUNT_REFINE_COST, "yield": HUNT_REFINE_YIELD}
    if not _cultivo_corpo_on():
        return {"can": False, "reason_key": "hunt_locked", **base}
    if int(getattr(player, "realm", 0) or 0) >= MIN_REALM_REQUIRED:
        return {"can": False, "reason_key": "hunt_apex", **base}
    if int(getattr(player, "hunt_essence", 0) or 0) < HUNT_REFINE_COST:
        return {"can": False, "reason_key": "hunt_need_essence", **base}
    return {"can": True, "reason_key": None, **base}


def do_refine(player) -> dict:
    """Refine ONE batch: spend HUNT_REFINE_COST essence → +HUNT_REFINE_YIELD
    mortal_temper_progress. NEVER touches qi/qi_capacity (BC-5). Caller holds the
    player FOR UPDATE + owns the commit; this re-validates the gate and fails
    atomically ({success: False}, no mutation) if it no longer holds."""
    if not _cultivo_corpo_on() or int(getattr(player, "realm", 0) or 0) >= MIN_REALM_REQUIRED:
        return {"success": False, "reason_key": "hunt_locked"}
    if int(getattr(player, "hunt_essence", 0) or 0) < HUNT_REFINE_COST:
        return {"success": False, "reason_key": "hunt_need_essence",
                "hunt_essence": int(getattr(player, "hunt_essence", 0) or 0)}
    player.hunt_essence = max(0, int(player.hunt_essence or 0) - HUNT_REFINE_COST)
    player.mortal_temper_progress = int(getattr(player, "mortal_temper_progress", 0) or 0) + HUNT_REFINE_YIELD
    return {
        "success": True,
        "essence_spent": HUNT_REFINE_COST,
        "refined": HUNT_REFINE_YIELD,
        "hunt_essence": int(player.hunt_essence),
        "temper_progress": int(player.mortal_temper_progress),
    }


def project_hunt(player) -> dict:
    """READ — the Caça surface (folded into the garden payload): essence balance +
    refine affordability. PURE; the caller gates on `cultivo_corpo_r0`."""
    realm = int(getattr(player, "realm", 0) or 0)
    chk = can_refine(player)
    return {
        "is_apex": realm >= MIN_REALM_REQUIRED,
        "hunt_essence": int(getattr(player, "hunt_essence", 0) or 0),
        "refine_cost": HUNT_REFINE_COST,
        "refine_yield": HUNT_REFINE_YIELD,
        "can_refine": bool(chk["can"]),
        "refine_reason_key": chk.get("reason_key"),
        "temper_progress": int(getattr(player, "mortal_temper_progress", 0) or 0),
    }
