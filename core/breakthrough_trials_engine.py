"""core/breakthrough_trials_engine.py — Sprint 8: Cerimónia-Semente (Breakthrough Trials, BT-1..4).

Turns the silent early realm-up into a felt MOMENT with stakes. Because the Foundation
(R1→R2) and Core (R2→R3) gates already own those two transitions (with their own quality
rolls), the ceremony naturally governs the realm-ups they DON'T pre-empt — R0→R1 (the very
first breakthrough) and R3→R4 (the threshold of the tribulation tier):

  • BT-1/BT-2 — a CHOICE: Consolidar (稳, safe, guaranteed) vs Forçar (冲, gamble for a
    CB head-start + stones) right at the threshold.
  • BT-3 — the ANOMALIA: if the Cultivo do Corpo lags the realm (gap D = realm −
    mortal_body_level), Forçar's odds WORSEN — the Old Beggar's warning becomes true, so
    the 4 body faucets (Horta/Caça/Ambiental/Combate) finally MATTER at breakthrough.
  • BT-4 — the 顿悟 charge: a recent near-death battle (Sprint 7) grants a temporal charge
    that lets you Forçar WITHOUT the failure risk; consumed here.

Lei §1: Consolidar is ALWAYS available (you advance no matter what); a failed Forçar NEVER
loses CB/progress — the realm-up still happens, the only cost is a recoverable SETBACK (the
next Forçar is locked until it expires). Server-gated by `breakthrough_trials` (OFF on main
→ the gate in check_breakthrough never fires → byte-identical for the 57). Wipe-safe: the
knobs are engine constants; the only state is two nullable timestamps (Migration 127).
"""
import os
from datetime import datetime, timedelta, timezone

# Ceremony realm-band: player.realm in {0,1,2,3}. R4+ routes through Heavenly Tribulation
# (TRIBULATION_START_REALM=4) — untouched. In practice the Foundation/Core gates pre-empt
# realm 1 and 2 (they `return` before the ceremony gate in check_breakthrough), so the
# ceremony fires at R0→R1 and R3→R4.
BT_CEREMONY_MAX_REALM = int(os.getenv("BT_CEREMONY_MAX_REALM", "4"))
BT_FORCE_BASE_CHANCE = float(os.getenv("BT_FORCE_BASE_CHANCE", "0.55"))
BT_ANOMALIA_PENALTY = float(os.getenv("BT_ANOMALIA_PENALTY", "0.12"))      # per gap point
BT_MIN_FORCE_CHANCE = float(os.getenv("BT_MIN_FORCE_CHANCE", "0.10"))
BT_SETBACK_SECONDS = int(os.getenv("BT_SETBACK_SECONDS", "21600"))         # 6h
BT_FORCE_CB_BONUS_FRAC = float(os.getenv("BT_FORCE_CB_BONUS_FRAC", "0.25"))  # head-start
BT_FORCE_STONES = int(os.getenv("BT_FORCE_STONES", "300"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(ts):
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def bt_ceremony_on(world_key=None) -> bool:
    """True iff `breakthrough_trials` is ON for the (active or given) world. Fail-safe →
    False on any error (so a bug can never silently change the 57's breakthroughs)."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("breakthrough_trials", world_key))
    except Exception:
        return False


def body_gap(player) -> int:
    """The Anomalia gap D = realm − mortal_body_level (≥0). Only a REAL gap where the
    temper path ships (`cultivo_corpo_r0` ON); else 0 — no body path → no penalty (a
    player who CANNOT temper is never punished for a gap, Lei §1)."""
    try:
        from core.body_tempering_engine import _cultivo_corpo_on
        if not _cultivo_corpo_on():
            return 0
    except Exception:
        return 0
    realm = int(getattr(player, "realm", 0) or 0)
    body = int(getattr(player, "mortal_body_level", 0) or 0)
    return max(0, realm - body)


def has_insight(player, now=None) -> bool:
    """A valid (non-expired) 顿悟 charge (Sprint 7 grants it)."""
    exp = _aware(getattr(player, "insight_charge_expires_at", None))
    return bool(exp and exp > (now or _now()))


def setback_remaining(player, now=None) -> int:
    """Seconds left on the Forçar-failure setback (0 = none)."""
    until = _aware(getattr(player, "breakthrough_setback_until", None))
    if not until:
        return 0
    return max(0, int((until - (now or _now())).total_seconds()))


def force_chance(player) -> float:
    """Forçar success chance: base − anomalia·gap, floored at BT_MIN_FORCE_CHANCE. A valid
    顿悟 charge guarantees it (1.0)."""
    if has_insight(player):
        return 1.0
    gap = body_gap(player)
    return max(BT_MIN_FORCE_CHANCE, min(1.0, BT_FORCE_BASE_CHANCE - BT_ANOMALIA_PENALTY * gap))


def ceremony_eligible(player) -> bool:
    """Realm-band gate: flag ON AND realm in {0..BT_CEREMONY_MAX_REALM-1}. The CB-threshold
    check stays in check_breakthrough (this is just the band + flag)."""
    realm = int(getattr(player, "realm", 0) or 0)
    return bt_ceremony_on() and 0 <= realm < BT_CEREMONY_MAX_REALM


def project_ceremony(player) -> dict:
    """READ — the ceremony disclosure (gap, odds, charge, setback). PURE. Consolidar is
    ALWAYS available; Forçar is gated only by an active setback (Lei §1 — never stuck)."""
    rem = setback_remaining(player)
    return {
        "realm": int(getattr(player, "realm", 0) or 0),
        "body_gap": body_gap(player),
        "force_chance": round(force_chance(player), 3),
        "has_insight": has_insight(player),
        "in_setback": rem > 0,
        "setback_remaining": rem,
        "force_available": rem <= 0,
        "force_cb_bonus_frac": BT_FORCE_CB_BONUS_FRAC,
        "force_stones": BT_FORCE_STONES,
    }


def resolve_force(player, roll: float, now=None) -> dict:
    """Resolve a FORÇAR choice given a roll in [0,1). Mutates ONLY the player's charge/
    setback fields here (the realm-up + the CB/stones reward are applied by the caller).
    NEVER touches qi/CB; NEVER raises. Caller holds the player FOR UPDATE + owns the commit.
    A valid 顿悟 charge guarantees success and is consumed."""
    now = now or _now()
    insight = has_insight(player, now)
    chance = force_chance(player)
    success = bool(insight or (roll < chance))
    if insight:
        player.insight_charge_expires_at = None  # consume the charge
    if success:
        return {"choice": "forcar", "success": True, "used_insight": insight,
                "chance": round(chance, 3)}
    # Recoverable setback — the realm-up STILL happens (Lei §1); only the next Forçar is
    # locked until this expires.
    player.breakthrough_setback_until = now + timedelta(seconds=BT_SETBACK_SECONDS)
    return {"choice": "forcar", "success": False, "used_insight": False,
            "chance": round(chance, 3), "setback_seconds": BT_SETBACK_SECONDS}
