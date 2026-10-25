"""core/insight_engine.py — Sprint 7: Combate 顿悟 (Insight), the 4th body-tempering input.

The most ACTIVE faucet: winning a WORTHY fight (the opponent's BP is at least a fraction
of yours — beating a weakling teaches nothing) tempers the flesh → +mortal_temper_progress
(the SAME currency the Horta/Caça/Ambiental fill), paced by a cooldown. And surviving a
NEAR-DEATH worthy fight (you ended on a sliver of HP) grants a 顿悟 CHARGE
(player.insight_charge_expires_at, the field Sprint 8 created) that the Cerimónia-Semente
(BT-4) consumes to Forçar without risk.

The hook is POST-SETTLE, ADDITIVE and gated (in duel_engine._notify_duel_result): the
duel's winner/damage/qi/BP are already decided and UNCHANGED — this only reads the outcome
and grants a bonus. Server-gated by `cultivo_corpo_r0` (same Corpo axis — no new flag) AND
realm < 7. NEVER touches qi/qi_capacity (BC-5). On `main` (flag OFF) it is a no-op → the
57's duels are byte-identical. Wipe-safe: knobs are engine constants; the only new state is
one nullable cooldown stamp (Migration 128).
"""
import os
from datetime import datetime, timedelta, timezone

from core.body_tempering_engine import MIN_REALM_REQUIRED, _cultivo_corpo_on

# --- knobs (engine constants → wipe-safe; owner tunes per server via env) --------
INSIGHT_PROGRESS = int(os.getenv("INSIGHT_PROGRESS", "25"))            # progress per worthy win
INSIGHT_COOLDOWN_SECONDS = int(os.getenv("INSIGHT_COOLDOWN_SECONDS", "1800"))  # 30m pacer
INSIGHT_MIN_OPP_BP_RATIO = float(os.getenv("INSIGHT_MIN_OPP_BP_RATIO", "0.7"))  # dignity gate
INSIGHT_NEARDEATH_FRAC = float(os.getenv("INSIGHT_NEARDEATH_FRAC", "0.30"))     # ≤30% HP = near-death
INSIGHT_CHARGE_HOURS = int(os.getenv("INSIGHT_CHARGE_HOURS", "24"))    # 顿悟 charge lifetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(ts):
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def insight_on(world_key=None) -> bool:
    """True iff the Corpo axis (`cultivo_corpo_r0`) is ON. Fail-safe → False."""
    try:
        return bool(_cultivo_corpo_on(world_key))
    except Exception:
        return False


def _cooldown_remaining(player, now=None) -> int:
    last = _aware(getattr(player, "last_combat_insight_at", None))
    if not last:
        return 0
    elapsed = ((now or _now()) - last).total_seconds()
    return max(0, int(INSIGHT_COOLDOWN_SECONDS - elapsed))


def award_combat_insight(player, *, won: bool, hp_frac: float, my_bp: float,
                         opp_bp: float, now=None) -> dict:
    """Grant combat insight to `player` after a settled duel. PURE w.r.t. combat (reads the
    outcome, never changes it). Mutates ONLY mortal_temper_progress / last_combat_insight_at
    / insight_charge_expires_at. NEVER touches qi/qi_capacity (BC-5). Caller (the post-settle
    hook) is gated + try/except + owns the commit. Returns what was granted (all False/0 when
    nothing qualifies — a no-op)."""
    out = {"progress_added": 0, "got_charge": False, "dignified": False}
    if not won:
        return out
    if not insight_on():
        return out
    if int(getattr(player, "realm", 0) or 0) >= MIN_REALM_REQUIRED:
        return out
    my_bp = float(my_bp or 0)
    opp_bp = float(opp_bp or 0)
    # Dignity: a real opponent, strong enough that the win is an epiphany — not a pushover.
    if my_bp <= 0 or opp_bp < INSIGHT_MIN_OPP_BP_RATIO * my_bp:
        return out
    out["dignified"] = True
    now = now or _now()
    # 4th faucet — worthy win tempers the flesh, cooldown-paced.
    if _cooldown_remaining(player, now) <= 0:
        player.mortal_temper_progress = int(getattr(player, "mortal_temper_progress", 0) or 0) + INSIGHT_PROGRESS
        player.last_combat_insight_at = now
        out["progress_added"] = INSIGHT_PROGRESS
    # 顿悟 charge — surviving a near-death worthy fight (feeds Sprint 8 BT-4). Refreshes the
    # expiry; not cooldown-gated (near-death + dignity is the limiter).
    try:
        frac = float(hp_frac)
    except (TypeError, ValueError):
        frac = 1.0
    if 0.0 <= frac <= INSIGHT_NEARDEATH_FRAC:
        player.insight_charge_expires_at = now + timedelta(hours=INSIGHT_CHARGE_HOURS)
        out["got_charge"] = True
    return out


def project_insight(player) -> dict:
    """READ — the Insight surface (folded into the garden payload): faucet cooldown + whether
    a 顿悟 charge is held. PURE; the caller gates on `cultivo_corpo_r0`."""
    now = _now()
    charge = _aware(getattr(player, "insight_charge_expires_at", None))
    return {
        "is_apex": int(getattr(player, "realm", 0) or 0) >= MIN_REALM_REQUIRED,
        "progress_per_win": INSIGHT_PROGRESS,
        "cooldown_seconds": INSIGHT_COOLDOWN_SECONDS,
        "cooldown_remaining": _cooldown_remaining(player, now),
        "has_charge": bool(charge and charge > now),
        "charge_remaining": max(0, int((charge - now).total_seconds())) if (charge and charge > now) else 0,
        "min_opp_bp_ratio": INSIGHT_MIN_OPP_BP_RATIO,
    }
