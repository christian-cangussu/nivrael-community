"""core/environment_engine.py — Sprint 6: Ambiental 环境 (the world tempers the flesh).

The THIRD input source for the Mortal-flesh band: meditating/remaining at
extreme-environment SITES (ice cavern, volcano peak, dense-qi abyss…) yields
TEMPER PROGRESS toward the next Mortal tier (player.mortal_temper_progress) — the
SAME patient currency the Horta (Sprint 4, idle) and the Caça (Sprint 5,
expeditions) fill. That banked progress DISCOUNTS the qi cost of the next "Temperar
a Carne" (body_tempering_engine.HORTA_QI_DISCOUNT) — so Ambiental is a 3rd faucet
into the existing progress→qi-discount pipe, NOT a new system.

The PACER here is different from its siblings (Lei §3 — depth via distinct pacers):
no stone cost, no idle wait — the "cost" is TIME (a global cooldown) + being in the
right PLACE (the site's continent). Horta = idle; Caça = active expeditions;
Ambiental = situational travel. Each site lives in an existing continent (Onda 4b);
one site per spawnable continent so wherever a cultivator stands the world offers
something (Lei §1 — never a dead-end). The forbidden continent (`moyu`) has none —
disclosed, not a void (the UI shows where to roam).

Server-gated by `cultivo_corpo_r0` (same Corpo axis — NO new flag) AND realm < 7,
exactly like the temper ACTION. Tempering NEVER grants qi or qi_capacity (BC-5).
Wipe-safe: TEMPER_SITES is an engine constant; the only DB state is one nullable
cooldown stamp (player.env_last_temper_at, Migration 126). On `main` (flag OFF) the
endpoint refuses and nothing is ever written → the 57 are untouched.

Concurrency / atomicity: the WRITE assumes the CALLER holds ``player`` FOR UPDATE
and owns the commit; do_temper_env re-validates the gate (incl. the cooldown) and
fails atomically (a disclosed no-op that mutates nothing) if it no longer holds, so
a double-tap inside the cooldown can never double-credit.
"""

import os
from datetime import datetime, timezone

from core.body_tempering_engine import MIN_REALM_REQUIRED, _cultivo_corpo_on

# --- knobs (engine constants → wipe-safe; owner tunes per server via env) --------
# The cooldown IS the anti-farm pacer (there is no stone cost). One global window:
# one environmental temper per ENV_COOLDOWN_SECONDS, anywhere. Conservative bake.
ENV_COOLDOWN_SECONDS = int(os.getenv("ENV_COOLDOWN_SECONDS", "21600"))  # 6h

# Each site LIVES in an existing continent (continent_engine.CONTINENT_KEYS). The
# player must be THERE to temper at it (situational). One site per spawnable
# continent → never a dead-end (Lei §1): wherever a cultivator stands, the world
# offers a local site. `moyu` (the forbidden/demonic continent, spawn_allowed=False)
# has none — disclosed (travel elsewhere), not a void. Names render via the
# i18n key `env_site_<site_key>` (mirrors the herb_<key> pattern). `progress`
# varies by site/theme so there is a reason to travel; travel has its own cost +
# cooldown (Onda 4b), which keeps "station at the best site" a real trade-off.
TEMPER_SITES = {
    "abismo_qi": {"emoji": "🌌", "continent": "linghe", "progress": 30},
    "caverna_gelo": {"emoji": "❄️", "continent": "qianhe", "progress": 45},
    "bosque_raio": {"emoji": "⛈️", "continent": "yanshan", "progress": 40},
    "pico_vulcao": {"emoji": "🌋", "continent": "fenghuo", "progress": 50},
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _site(site_key):
    return TEMPER_SITES.get(site_key)


def _player_continent(player) -> str:
    return getattr(player, "current_continent", None) or "linghe"


def local_site_key(player):
    """The site_key in the player's CURRENT continent (or None — e.g. `moyu`). The
    chat surface uses this so its button needs no args (<64B)."""
    cur = _player_continent(player)
    for key, info in TEMPER_SITES.items():
        if info["continent"] == cur:
            return key
    return None


def _cooldown_remaining(player, now=None) -> int:
    """Seconds left on the GLOBAL env-temper cooldown (0 = ready)."""
    last = getattr(player, "env_last_temper_at", None)
    if not last:
        return 0
    now = now or _now()
    if last.tzinfo is None:  # tolerate a naive timestamp from the DB → treat as UTC
        last = last.replace(tzinfo=timezone.utc)
    elapsed = (now - last).total_seconds()
    return max(0, int(ENV_COOLDOWN_SECONDS - elapsed))


def can_temper_env(player, site_key) -> dict:
    """Can this player temper at `site_key` RIGHT NOW? Gated by `cultivo_corpo_r0`,
    realm < 7, being IN the site's continent, and the global cooldown. PURE; no
    side-effects. Returns {can, reason_key, site_key, progress, ...}."""
    site = _site(site_key)
    base = {"site_key": site_key, "progress": int(site["progress"]) if site else 0}
    if not site:
        return {"can": False, "reason_key": "env_bad_site", **base}
    if not _cultivo_corpo_on():
        return {"can": False, "reason_key": "env_locked", **base}
    if int(getattr(player, "realm", 0) or 0) >= MIN_REALM_REQUIRED:
        return {"can": False, "reason_key": "env_apex", **base}
    if _player_continent(player) != site["continent"]:
        return {"can": False, "reason_key": "env_wrong_place",
                "continent": site["continent"], **base}
    rem = _cooldown_remaining(player)
    if rem > 0:
        return {"can": False, "reason_key": "env_cooldown",
                "remaining_seconds": rem, **base}
    return {"can": True, "reason_key": None, **base}


def do_temper_env(player, site_key) -> dict:
    """Temper at a site: +site.progress to mortal_temper_progress, stamp the global
    cooldown. NEVER touches qi/qi_capacity (BC-5). Caller holds the player FOR UPDATE
    + owns the commit; this re-validates the gate (incl. continent + cooldown) and
    fails atomically ({success: False}, no mutation) if it no longer holds — so a
    double-tap inside the cooldown is a disclosed no-op, never a double-credit."""
    chk = can_temper_env(player, site_key)
    if not chk["can"]:
        out = {"success": False, "reason_key": chk["reason_key"]}
        if "remaining_seconds" in chk:
            out["remaining_seconds"] = chk["remaining_seconds"]
        if "continent" in chk:
            out["continent"] = chk["continent"]
        return out
    gain = int(_site(site_key)["progress"])
    player.mortal_temper_progress = int(getattr(player, "mortal_temper_progress", 0) or 0) + gain
    player.env_last_temper_at = _now()
    return {
        "success": True,
        "site_key": site_key,
        "temper_progress_gained": gain,
        "temper_progress": int(player.mortal_temper_progress),
        "cooldown_seconds": ENV_COOLDOWN_SECONDS,
    }


def project_environment(player) -> dict:
    """READ — the Ambiente surface (folded into the garden payload): every site with
    its continent + progress, which one is HERE (temperable now), and the global
    cooldown remaining. PURE; the caller gates on `cultivo_corpo_r0`."""
    realm = int(getattr(player, "realm", 0) or 0)
    cur = _player_continent(player)
    sites = []
    for key, info in TEMPER_SITES.items():
        chk = can_temper_env(player, key)
        sites.append({
            "site_key": key,
            "emoji": info["emoji"],
            "continent": info["continent"],
            "progress": int(info["progress"]),
            "here": cur == info["continent"],
            "can_temper": bool(chk["can"]),
            "reason_key": chk.get("reason_key"),
        })
    return {
        "is_apex": realm >= MIN_REALM_REQUIRED,
        "current_continent": cur,
        "cooldown_seconds": ENV_COOLDOWN_SECONDS,
        "cooldown_remaining": _cooldown_remaining(player),
        "sites": sites,
        "temper_progress": int(getattr(player, "mortal_temper_progress", 0) or 0),
    }
