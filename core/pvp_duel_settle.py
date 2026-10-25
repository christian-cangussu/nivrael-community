"""v15.1.3 — Settle PVPChallenge-sourced duels after termination.

When a mini-app PVPChallenge is accepted, the legacy `simulate_combat`
auto-resolve path is replaced by a turn-based `DuelSession`. The wager
stays escrowed on PVPChallenge.wager; PVPChallenge.duel_id links the row
to its duel. Once the duel reaches a terminal state, `settle_pvp_duel`
runs once (idempotent) to pay out the wager + apply all side-effects
the old simulate_combat path used to apply in one shot.

Called from `core/duel_engine.apply_post_duel_effects` so it triggers
naturally on the next `duel_state` poll after a duel ends. No scheduler
needed.

Idempotency: PVPChallenge.status flips to 'completed' as the final step;
the early-exit guard on that status prevents double-payouts on retries.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from core.combat_engine import (
    MASTERY_STAGES,
    calculate_sparring_reward,
)
from database.models import (
    CombatLog,
    DuelSession,
    Player,
    PlayerTechnique,
    PVPChallenge,
)

logger = logging.getLogger(__name__)


def _count_tech_activations(action_log: list, side_key: str) -> dict[int, int]:
    """Count how many times each technique was used by a given side across the duel.

    Mirrors simulate_combat's `*_tech_activations` output shape so we can
    feed it to the same mastery-XP awarder. `side_key` is 'a' or 'b'.
    """
    counts: dict[int, int] = {}
    for entry in action_log or []:
        # Skip non-round entries (sudden_death_start, tiebreak, forfeit, etc.)
        side = entry.get(side_key) if isinstance(entry, dict) else None
        if not isinstance(side, dict):
            continue
        tech = side.get("tech")
        if not isinstance(tech, dict):
            continue
        tid = tech.get("id")
        if tid:
            counts[int(tid)] = counts.get(int(tid), 0) + 1
    return counts


async def _award_mastery_xp(session, player_id: int, activations: dict, won: bool) -> None:
    for tid, n in (activations or {}).items():
        if not n:
            continue
        row = (await session.execute(
            select(PlayerTechnique).where(
                PlayerTechnique.player_id == player_id,
                PlayerTechnique.technique_id == int(tid),
            )
        )).scalar_one_or_none()
        if not row:
            continue
        xp_gain = int(n) * 5 + (20 if won else 0)
        row.mastery_xp = int(row.mastery_xp or 0) + xp_gain
        while int(row.mastery_level or 1) < 5:
            nxt = MASTERY_STAGES.get(int(row.mastery_level or 1) + 1)
            if nxt and row.mastery_xp >= nxt["xp_req"]:
                row.mastery_level = int(row.mastery_level or 1) + 1
            else:
                break


async def settle_pvp_duel(session, duel: DuelSession) -> bool:
    """Settle wager + side-effects for a PVPChallenge-sourced duel.

    Returns True if settlement ran, False if skipped (not PvP-sourced or
    already settled). Idempotent.

    Terminal states this acts on:
      - 'finished'  → winner takes pool (challenger.wager + target.wager)
                      × 0.95 (5% house cut) + sparring reward
      - 'forfeited' → opponent wins, same payout as finished
      - 'expired'   → only happens in pending_acceptance phase, NOT here —
                      that branch never has wager reserved (reservation
                      happens at accept-time)

    No-op on:
      - 'waiting_actions' (mid-duel)
      - 'declined' / 'cancelled' (no fight happened — accept never fired,
        wager was never reserved)
    """
    if duel.state not in ("finished", "forfeited"):
        return False

    # Find the linked PVPChallenge (NULL for direct duels created via
    # combat/duel_create — those have no wager and no side-effects path).
    challenge = (await session.execute(
        select(PVPChallenge).where(PVPChallenge.duel_id == duel.id).with_for_update()
    )).scalar_one_or_none()
    if challenge is None:
        return False

    if challenge.status == "completed":
        return False  # already settled — idempotent guard

    now_utc = datetime.now(timezone.utc)
    wager = int(challenge.wager or 0)
    winner_id = duel.winner_id

    # Lock both player rows for spirit_stones + body_tempering writes.
    rows = (await session.execute(
        select(Player).where(
            Player.telegram_id.in_([challenge.challenger_id, challenge.target_id])
        ).with_for_update()
    )).scalars().all()
    pmap = {p.telegram_id: p for p in rows}
    challenger = pmap.get(challenge.challenger_id)
    target = pmap.get(challenge.target_id)
    if not challenger or not target:
        # Defensive — shouldn't happen since rows were locked at accept.
        logger.warning("settle_pvp_duel: missing player row for duel=%s", duel.id)
        challenge.status = "completed"
        challenge.resolved_at = now_utc
        return False

    # Sparring reward (BP-based, mirrors chat-side simulate_combat output).
    atk_bp = int((duel.fighter_a or {}).get("bp", 0))
    def_bp = int((duel.fighter_b or {}).get("bp", 0))
    spirit_reward = calculate_sparring_reward(atk_bp, def_bp)
    wager_bonus = int(wager * 2 * 0.95) if wager > 0 else 0

    if winner_id is not None:
        winner_player = challenger if winner_id == challenger.telegram_id else target
        winner_player.spirit_stones = int(winner_player.spirit_stones or 0) + spirit_reward + wager_bonus
    elif wager > 0:
        # Tie path — refund both. The duel engine guarantees winner_id is
        # set on every terminal state (sudden death tiebreak forces one)
        # so this branch is mostly defensive.
        challenger.spirit_stones = int(challenger.spirit_stones or 0) + wager
        target.spirit_stones = int(target.spirit_stones or 0) + wager

    # Mastery XP from action_log (counts technique activations per side).
    activations_a = _count_tech_activations(duel.action_log or [], "a")
    activations_b = _count_tech_activations(duel.action_log or [], "b")
    try:
        await _award_mastery_xp(session, challenger.telegram_id, activations_a,
                                won=(winner_id == challenger.telegram_id))
        await _award_mastery_xp(session, target.telegram_id, activations_b,
                                won=(winner_id == target.telegram_id))
    except Exception:
        logger.exception("settle_pvp_duel: mastery XP failed duel=%s", duel.id)

    # v15.2 — Intent XP. Both sides are real players in PvP challenges.
    try:
        from core.intent_engine import award_post_duel_intent_xp
        await award_post_duel_intent_xp(session, duel, winner_id)
    except Exception:
        logger.exception("settle_pvp_duel: intent XP failed duel=%s", duel.id)


    # Side-effects (sparring parity).
    try:
        from core.bp_engine import update_bp_mission
        from core.faction_engine import update_quest_progress as fac_quest_progress
        from core.body_tempering_engine import add_tempering_progress
        from core.quest_engine import track_quest

        if winner_id == challenger.telegram_id:
            await update_bp_mission(session, challenger.telegram_id, "win_sparring")
            await fac_quest_progress(session, challenger.telegram_id, "spar_win")
            await fac_quest_progress(session, challenger.telegram_id, "pvp_win")
            add_tempering_progress(challenger, 8)
        elif winner_id == target.telegram_id:
            await update_bp_mission(session, target.telegram_id, "win_sparring")
            await fac_quest_progress(session, target.telegram_id, "spar_win")
            await fac_quest_progress(session, target.telegram_id, "pvp_win")
            add_tempering_progress(target, 8)
        await track_quest(session, challenger.telegram_id, "sparring")
        await track_quest(session, target.telegram_id, "sparring")
    except Exception:
        logger.exception("settle_pvp_duel: side-effects failed duel=%s", duel.id)

    # CombatLog row — keeps history parity with legacy simulate_combat path.
    try:
        session.add(CombatLog(
            attacker_id=challenger.telegram_id,
            defender_id=target.telegram_id,
            mode="sparring",
            winner_id=winner_id,
            wager_amount=wager,
            wager_winner_id=winner_id if wager > 0 else None,
            rounds_data={"rounds": duel.action_log or [], "turn_based": True},
            spirit_stones_reward=spirit_reward + wager_bonus,
        ))
    except Exception:
        logger.exception("settle_pvp_duel: combat_log insert failed duel=%s", duel.id)

    # Final stamp — idempotent guard for retries.
    challenge.status = "completed"
    challenge.resolved_at = now_utc
    challenge.winner_id = winner_id
    challenge.rounds_data = {"rounds": duel.action_log or [], "turn_based": True}
    # Mark both sides seen on the challenge — duel UI is the canonical
    # surface now, the inbox row is just a historic anchor.
    if challenge.challenger_seen_at is None:
        challenge.challenger_seen_at = now_utc
    if challenge.target_seen_at is None:
        challenge.target_seen_at = now_utc
    return True
