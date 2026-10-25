"""v16.4b — Sect Recruitment trial engine.

The recruiter encounter (v16.4) invites; this engine makes the cultivator
EARN the house. Accepting the Elder's challenge spawns a real turn-based duel
(``duel_engine`` + the v16.7 ``combat_model``) against a Sect Elder NPC scaled
to the cultivator's own realm. Victory ⇒ ``join_player_to_sect``; defeat ⇒ a
short cooldown before another attempt — never a soft-lock (Lei Primordial §1).

Two surfaces share ONE mechanic:
  * mini-app (canonical): ``world/sect_trial_start`` creates the duel and the
    client opens the interactive ``DuelArenaModal``.
  * chat (legacy): the ``wsect_trial_*`` callback auto-plays the SAME duel to
    completion (the Elder's AI drives both sides) and narrates the result.

Either way the outcome is resolved by :func:`resolve_trial_from_duel`, called
from ``pve_duel_settle`` when the trial duel terminates — idempotent (the
``pve_settled`` marker + the trial's ``status`` gate re-entrant settle calls).

Idempotency / safety (57+ live players):
  * one active (``pending``) trial per (player, house); re-clicking RESUMES the
    open duel rather than spawning a second.
  * the attacker Player row is locked (``with_for_update``) before any write.
  * a cultivator already in a house cannot start a trial.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, or_, select

from database.models import (
    DuelSession,
    Player,
    WorldSectRecruiterPending,
    WorldSectTrial,
)

logger = logging.getLogger(__name__)

# ── Trial tuning ──────────────────────────────────────────────────────────
ELDER_ARCHETYPE = "elder"          # core/npc_loadouts.py — disciplined all-rounder
TRIAL_DIFFICULTY = "normal"        # scaled to the player's realm, fair-but-real
TRIAL_LOSS_COOLDOWN_HOURS = 24     # gentle retry gate on defeat (Lei §1, 24-72h band)
_AUTOPLAY_ROUND_CAP = 40           # safety bound for the chat auto-resolve loop


async def latest_trial(session, player_id: int, sect_id: str) -> WorldSectTrial | None:
    """Return the most recent trial row for (player, house), or None."""
    return (await session.execute(
        select(WorldSectTrial)
        .where(
            WorldSectTrial.player_id == player_id,
            WorldSectTrial.sect_id == sect_id,
        )
        .order_by(desc(WorldSectTrial.created_at))
        .limit(1)
    )).scalar_one_or_none()


async def _has_open_duel(session, player_id: int) -> DuelSession | None:
    """Return the player's currently-open duel (PvP or PvE), if any.

    Resolves a stale (timed-out) duel first so an abandoned row never locks
    the cultivator out of a trial (mirrors the NPC-hunt start path).
    """
    open_states = ["waiting_actions", "pending_acceptance"]
    existing = (await session.execute(
        select(DuelSession).where(
            or_(DuelSession.attacker_id == player_id, DuelSession.defender_id == player_id),
            DuelSession.state.in_(open_states),
        ).limit(1)
    )).scalar_one_or_none()
    if existing is None:
        return None
    try:
        from core.duel_engine import check_and_handle_timeout
        changed = await check_and_handle_timeout(session, existing)
    except Exception:
        logger.exception("check_and_handle_timeout failed for duel=%s", existing.id)
        changed = False
    if changed:
        await session.flush()
        existing = (await session.execute(
            select(DuelSession).where(
                or_(DuelSession.attacker_id == player_id, DuelSession.defender_id == player_id),
                DuelSession.state.in_(open_states),
            ).limit(1)
        )).scalar_one_or_none()
    return existing


async def start_sect_trial(session, player: Player, pending: WorldSectRecruiterPending) -> dict[str, Any]:
    """Begin (or resume) the trial duel for a live recruiter encounter.

    ``player`` must be the caller's Player row (locked by the caller if it will
    write). ``pending`` is a live (unresolved, unexpired) recruiter encounter.

    Returns one of:
      {ok: True, duel_id, trial_id, resumed?}            — go fight the Elder
      {ok: False, reason: 'sect_already_joined'}
      {ok: False, reason: 'trial_cooldown', cooldown_until_ms}
      {ok: False, reason: 'duel_already_active', duel_id}
      {ok: False, reason: 'hp_depleted' | 'internal_error'}
    """
    from core.world_sects_engine import is_valid_sect

    sect_id = pending.sect_id
    pid = player.telegram_id
    now = datetime.now(timezone.utc)

    if not is_valid_sect(sect_id):
        return {"ok": False, "reason": "sect_invalid"}
    if is_valid_sect(player.sect_id):
        return {"ok": False, "reason": "sect_already_joined", "current": player.sect_id}

    # Resume an in-flight trial / honour a loss cooldown.
    prev = await latest_trial(session, pid, sect_id)
    if prev is not None:
        if prev.status == "pending" and prev.duel_id is not None:
            duel = (await session.execute(
                select(DuelSession).where(DuelSession.id == prev.duel_id)
            )).scalar_one_or_none()
            if duel is not None and duel.state in ("waiting_actions", "pending_acceptance"):
                return {"ok": True, "duel_id": str(duel.id), "trial_id": int(prev.id), "resumed": True}
            # Terminal but unresolved (e.g. the cultivator abandoned a winning
            # duel before the final poll could settle it). Settle it NOW so the
            # outcome is the duel's TRUTH, not a guess — then re-read membership.
            if duel is not None and duel.state in ("finished", "forfeited"):
                try:
                    from core.duel_engine import apply_post_duel_effects
                    await apply_post_duel_effects(session, duel)
                    await session.flush()
                except Exception:
                    logger.exception("start_sect_trial: stale-duel settle failed duel=%s", duel.id)
                if is_valid_sect(player.sect_id):
                    return {"ok": False, "reason": "sect_already_joined", "current": player.sect_id}
                prev = await latest_trial(session, pid, sect_id)  # re-read resolved row
            elif duel is None:
                # The duel row vanished — treat this trial row as stale.
                prev.status = "lost"
                prev.resolved_at = prev.resolved_at or now
        if prev is not None and prev.status == "lost" and prev.cooldown_until and prev.cooldown_until > now:
            return {
                "ok": False, "reason": "trial_cooldown",
                "cooldown_until_ms": int(prev.cooldown_until.timestamp() * 1000),
            }

    # One duel at a time.
    open_duel = await _has_open_duel(session, pid)
    if open_duel is not None:
        return {"ok": False, "reason": "duel_already_active", "duel_id": str(open_duel.id)}

    # Must be alive to be tested.
    try:
        from core.combat_engine import get_current_hp
        if get_current_hp(player) <= 0:
            return {"ok": False, "reason": "hp_depleted"}
    except Exception:
        logger.debug("hp gate check failed (player_id=%s)", pid, exc_info=True)

    try:
        from core.duel_engine import start_duel_pve

        trial = WorldSectTrial(
            player_id=pid,
            sect_id=sect_id,
            status="pending",
            pending_id=int(pending.id),
            affinity_score=int(pending.affinity_score or 0),
        )
        session.add(trial)
        await session.flush()  # populate trial.id

        duel = await start_duel_pve(
            session, player,
            archetype=ELDER_ARCHETYPE,
            difficulty=TRIAL_DIFFICULTY,
            source="sect_trial",
            context={
                "sect_id": sect_id,
                "pending_id": int(pending.id),
                "trial_id": int(trial.id),
                "affinity": int(pending.affinity_score or 0),
            },
        )
        trial.duel_id = duel.id
        await session.flush()
        return {"ok": True, "duel_id": str(duel.id), "trial_id": int(trial.id)}
    except Exception:
        logger.exception("start_sect_trial failed (player_id=%s, sect=%s)", pid, sect_id)
        return {"ok": False, "reason": "internal_error"}


async def resolve_trial_from_duel(session, duel: DuelSession, player: Player, won: bool) -> dict[str, Any]:
    """Resolve the trial outcome from its settled duel. Idempotent.

    Called from ``pve_duel_settle.settle_pve_duel`` for ``pve_source ==
    'sect_trial'`` (which itself runs once per duel via the ``pve_settled``
    marker). On a win the cultivator joins the house and the recruiter
    encounter is marked accepted; on a loss a 24h retry cooldown is set.
    """
    ctx = duel.pve_context or {}
    sect_id = ctx.get("sect_id")
    trial_id = ctx.get("trial_id")
    pending_id = ctx.get("pending_id")
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {"trial": "won" if won else "lost", "sect_id": sect_id}

    # Locate the trial row (by id, else by duel link).
    trial = None
    if trial_id is not None:
        trial = (await session.execute(
            select(WorldSectTrial).where(WorldSectTrial.id == int(trial_id)).with_for_update()
        )).scalar_one_or_none()
    if trial is None:
        trial = (await session.execute(
            select(WorldSectTrial).where(WorldSectTrial.duel_id == duel.id).with_for_update()
        )).scalar_one_or_none()
    if trial is None:
        logger.warning("resolve_trial_from_duel: no trial row for duel=%s", duel.id)
        return payload
    if trial.status != "pending":
        # Already resolved by a prior settle pass — idempotent no-op.
        return {"trial": trial.status, "sect_id": trial.sect_id, "already_resolved": True}

    if won:
        trial.status = "won"
        trial.resolved_at = now
        joined = False
        try:
            from core.world_sects_engine import join_player_to_sect
            res = await join_player_to_sect(
                session, trial.player_id, trial.sect_id,
                affinity_score=int(trial.affinity_score or 0), source="sect_trial",
            )
            joined = bool(res.get("ok"))
            if not joined:
                payload["join_reason"] = res.get("reason")
        except Exception:
            logger.exception("resolve_trial_from_duel: join failed duel=%s", duel.id)
        payload["joined"] = joined

        # Mark the recruiter encounter accepted (best-effort, only if still live).
        if pending_id is not None:
            try:
                pend = (await session.execute(
                    select(WorldSectRecruiterPending).where(
                        WorldSectRecruiterPending.id == int(pending_id),
                        WorldSectRecruiterPending.accepted_at.is_(None),
                        WorldSectRecruiterPending.declined_at.is_(None),
                    ).with_for_update()
                )).scalar_one_or_none()
                if pend is not None:
                    pend.accepted_at = now
            except Exception:
                logger.debug("resolve_trial_from_duel: pending mark failed duel=%s", duel.id, exc_info=True)
    else:
        trial.status = "lost"
        trial.resolved_at = now
        trial.cooldown_until = now + timedelta(hours=TRIAL_LOSS_COOLDOWN_HOURS)
        payload["cooldown_until_ms"] = int(trial.cooldown_until.timestamp() * 1000)

    return payload


async def get_trial_state(session, player_id: int, sect_id: str) -> dict[str, Any]:
    """Project the cultivator's current trial standing with a house (for UI).

    {sect_id, in_sect, status: none|pending|won|lost, duel_id?,
     cooldown_until_ms?, on_cooldown}
    """
    out: dict[str, Any] = {
        "sect_id": sect_id, "in_sect": False, "status": "none",
        "duel_id": None, "cooldown_until_ms": None, "on_cooldown": False,
    }
    try:
        from core.world_sects_engine import is_valid_sect
        psect = (await session.execute(
            select(Player.sect_id).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()
        out["in_sect"] = is_valid_sect(psect) and psect == sect_id

        trial = await latest_trial(session, player_id, sect_id)
        if trial is None:
            return out
        out["status"] = trial.status
        if trial.duel_id is not None:
            out["duel_id"] = str(trial.duel_id)
        if trial.cooldown_until is not None:
            out["cooldown_until_ms"] = int(trial.cooldown_until.timestamp() * 1000)
            now = datetime.now(timezone.utc)
            out["on_cooldown"] = trial.status == "lost" and trial.cooldown_until > now
    except Exception:
        logger.debug("get_trial_state failed (player_id=%s, sect=%s)", player_id, sect_id, exc_info=True)
    return out


async def auto_play_trial_duel(session, duel: DuelSession, player_id: int) -> None:
    """Drive the trial duel to completion (chat / legacy surface).

    The cultivator's side is auto-piloted by the same combat AI that runs the
    Elder (``pick_npc_action`` over fighter_a), and ``submit_action`` resolves
    each round (the NPC side auto-fills). Stat-decided, deterministic-enough,
    and reuses the exact v16.7 combat math — so the chat trial is a REAL fight,
    just non-interactive. Bounded by ``_AUTOPLAY_ROUND_CAP``.
    """
    from core.duel_engine import submit_action
    from core.npc_ai import pick_npc_action

    # TEC-5 — o auto-piloto NUNCA lança arte proibida: o custo (karma + ANOS do
    # Mar de Longevidade) é do JOGADOR, e aqui ele tocou UM botão. A IA escolher
    # por ele queimaria décadas que ele nunca aceitou gastar (Lei §1: nenhum
    # custo sem tap). No mini o duelo é interativo — lá cada golpe é dele.
    _fp_ids = ()
    try:
        from core.forbidden_path_engine import forbidden_ids as _fpi
        _fp_ids = _fpi()
    except Exception:
        logger.debug("auto_play forbidden filter failed duel=%s", duel.id, exc_info=True)
    _fighter_a = duel.fighter_a
    if _fp_ids:
        _fighter_a = dict(duel.fighter_a or {})
        _fighter_a["techniques"] = [t for t in (_fighter_a.get("techniques") or [])
                                    if int(t.get("id") or 0) not in _fp_ids]

    guard = 0
    while duel.state == "waiting_actions" and guard < _AUTOPLAY_ROUND_CAP:
        guard += 1
        tech_id = 0
        try:
            pick = pick_npc_action(
                npc_fighter=_fighter_a,
                npc_state={
                    "hp": float(duel.hp_a), "hp_max": float(duel.hp_a_max),
                    "combat_qi": int(duel.combat_qi_a),
                },
                opp_state={
                    "hp": float(duel.hp_b), "hp_max": float(duel.hp_b_max),
                    "combat_qi": int(duel.combat_qi_b),
                },
                round_num=int(duel.round_idx),
            )
            tech_id = int(pick.get("technique_id") or 0)
        except Exception:
            logger.debug("auto_play pick failed duel=%s round=%s", duel.id, duel.round_idx, exc_info=True)
            tech_id = 0
        res = await submit_action(session, duel, player_id, tech_id)
        if not res.get("ok") and tech_id != 0:
            # The AI picked something unaffordable/invalid — fall back to a basic strike.
            await submit_action(session, duel, player_id, 0)
