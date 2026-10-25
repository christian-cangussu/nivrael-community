"""v15.1.5 — Settle arena-queue-sourced duels after termination.

When an arena match fires (`core/arena_engine.try_match`), it spawns a
DuelSession with `pve_source=None` (it's PvP — real player vs player) but
linked back to the ArenaQueue row via `arena_queue.duel_id`. Once the
duel terminates, `apply_post_duel_effects` discovers the link, looks up
the queue row, and calls `settle_arena_duel`.

What this mirrors from the legacy `_run_arena_match` chat-side path:
  - ELO delta via `calculate_elo_change` (winner+, loser-)
  - Spirit-stones reward via `calculate_arena_reward` (tier-scaled)
  - Arena scroll drop every 10 wins (`_maybe_award_arena_scroll`)
  - Achievements (`arena_wins`, `win_streak` + reset on loss)
  - Quests: `arena_win`, `arena_top3` (top-3 weekly), `pvp_win` faction
  - Body tempering progress (winner +12, both +0 on tie path)
  - `CombatLog` row with mode='arena' for history parity

Idempotency: the linked `ArenaQueue` row flips `status='completed'` as
the final stamp. Re-entrant calls (polling, sweeper) short-circuit on
that status.

PvE arena (chat-side `_arena_timeout` NPC fight) is NOT covered here —
that path stays inside `handlers/combat.py` because it auto-fires when
the queue times out without finding a match. The new sweeper preserves
that behaviour by calling `check_expirations` then opportunistically
trying to match remaining rows.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from core.combat_engine import (
    CURRENT_SEASON,
    MASTERY_STAGES,
    calculate_arena_reward,
    calculate_elo_change,
)
from database.models import (
    ArenaQueue,
    ArenaRanking,
    CombatLog,
    DuelSession,
    Player,
    PlayerTechnique,
)

logger = logging.getLogger(__name__)


def _count_tech_activations(action_log: list, side_key: str) -> dict[int, int]:
    """Mirror of pvp_duel_settle._count_tech_activations — kept local to
    avoid leaking that module's internals."""
    counts: dict[int, int] = {}
    for entry in action_log or []:
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


async def _get_or_create_arena_ranking(session, player_id: int) -> ArenaRanking:
    row = (await session.execute(
        select(ArenaRanking).where(
            ArenaRanking.player_id == player_id,
            ArenaRanking.season == CURRENT_SEASON,
        ).with_for_update()
    )).scalar_one_or_none()
    if row is None:
        row = ArenaRanking(
            player_id=player_id,
            season=CURRENT_SEASON,
            elo_points=1000,
            wins=0,
            losses=0,
        )
        session.add(row)
        await session.flush()
    return row


async def _get_arena_rank_pos(session, player_id: int) -> int | None:
    from sqlalchemy import func
    own = (await session.execute(
        select(ArenaRanking).where(
            ArenaRanking.player_id == player_id,
            ArenaRanking.season == CURRENT_SEASON,
        )
    )).scalar_one_or_none()
    if own is None:
        return None
    higher = (await session.execute(
        select(func.count()).select_from(ArenaRanking).where(
            ArenaRanking.season == CURRENT_SEASON,
            ArenaRanking.elo_points > own.elo_points,
        )
    )).scalar() or 0
    return int(higher) + 1


async def _maybe_award_arena_scroll(session, player_id: int, wins: int) -> str | None:
    """Mirrors handlers/combat.py — every 10 arena wins drop a fresh scroll.

    Kept inline (instead of importing the chat-side helper) so the settle
    path has zero handler dependency. Wuxia stays narratively intact: the
    scroll appears as a reward of mastery streaks, not surface-specific.
    """
    # TEC-2 — o marco é DETERMINÍSTICO, logo nenhum multiplicador de chance o
    # toca: sob escassez o passo estica (10 → SCR_ARENA_WIN_STEP). Sem isto o
    # faucet sobreviveria ao corte e viraria o loop "vitórias → pergaminho →
    # doação". Flag OFF ⇒ arena_scroll_step() == 10 (o valor vivo).
    from core.scroll_economy_engine import arena_scroll_step
    step = arena_scroll_step()
    if wins == 0 or wins % step != 0:
        return None
    from database.models import PlayerInventory, TechniqueCatalog
    import random as _r
    from core.utils import add_item_to_inventory

    learned_ids = set((await session.execute(
        select(PlayerTechnique.technique_id).where(
            PlayerTechnique.player_id == player_id,
        )
    )).scalars().all())
    owned_ids = set((await session.execute(
        select(PlayerInventory.item_id).where(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "technique_scroll",
            PlayerInventory.quantity > 0,
        )
    )).scalars().all())
    # v16.4c — exclude house signature arts (sect_key): Library-only (rank-gated, no
    # scroll), never an arena-streak scroll reward (Lei §5 — live drop economy untouched).
    all_techs = (await session.execute(
        select(TechniqueCatalog).where(TechniqueCatalog.sect_key.is_(None))
    )).scalars().all()
    candidates = [tech for tech in all_techs if tech.id not in learned_ids and tech.id not in owned_ids]
    if not candidates:
        return None
    chosen = _r.choice(candidates)
    added = await add_item_to_inventory(session, player_id, "technique_scroll", chosen.id)
    if not added:
        return None
    return f"{chosen.emoji} {chosen.name}"


async def settle_arena_duel(session, duel: DuelSession, arena_row: ArenaQueue) -> bool:
    """Apply ELO + rewards + side-effects for an arena-sourced duel.

    v15.1.5-hf4 — also handles the NPC-fallback branch (`defender_id IS
    NULL`, `pve_source="arena_npc_fallback"`). NPC fallback is identical
    in shape to a PvP arena duel except:
      • Only the attacker is a real Player row
      • ELO delta is halved (smaller stake when fighting AI)
      • Spirit-stones reward is halved
      • Loser side (NPC) has no ranking, no streak reset to apply
      • CombatLog.defender_id is NULL

    Idempotent: short-circuits when `arena_row.status == 'completed'`.
    Returns True if settlement ran, False if skipped.
    """
    if duel.state not in ("finished", "forfeited"):
        return False
    if arena_row.status == "completed":
        return False

    is_npc_fallback = duel.defender_id is None
    now = datetime.now(timezone.utc)
    winner_id = duel.winner_id

    # Lock the real Player rows (one for NPC fallback, two for PvP).
    real_ids = [duel.attacker_id]
    if not is_npc_fallback:
        real_ids.append(duel.defender_id)
    rows = (await session.execute(
        select(Player).where(
            Player.telegram_id.in_(real_ids)
        ).with_for_update()
    )).scalars().all()
    pmap = {p.telegram_id: p for p in rows}
    p_a = pmap.get(duel.attacker_id)
    p_b = pmap.get(duel.defender_id) if not is_npc_fallback else None

    if not p_a:
        logger.warning("settle_arena_duel: missing attacker player_id=%s duel=%s",
                       duel.attacker_id, duel.id)
        arena_row.status = "completed"
        return False
    if not is_npc_fallback and not p_b:
        logger.warning("settle_arena_duel: missing defender player_id=%s duel=%s",
                       duel.defender_id, duel.id)
        arena_row.status = "completed"
        return False

    rk_a = await _get_or_create_arena_ranking(session, p_a.telegram_id)
    rk_b = (await _get_or_create_arena_ranking(session, p_b.telegram_id)) if p_b else None

    # Other ArenaQueue row only exists for real PvP. For NPC fallback,
    # there's only one row (the attacker's).
    other_arena = None
    if not is_npc_fallback:
        other_arena = (await session.execute(
            select(ArenaQueue).where(
                ArenaQueue.duel_id == duel.id,
                ArenaQueue.player_id != arena_row.player_id,
            ).with_for_update()
        )).scalar_one_or_none()

    win_delta = 0
    lose_delta = 0
    arena_reward = 0
    scroll_name: str | None = None

    # Resolve winner/loser among the real participants. For NPC fallback,
    # winner_id is either p_a.telegram_id (player won) or 0 (NPC sentinel,
    # player lost — set by duel_engine._resolve_round).
    player_won = (winner_id == p_a.telegram_id)
    player_lost = is_npc_fallback and winner_id == 0
    pvp_player_b_won = (not is_npc_fallback) and p_b is not None and winner_id == p_b.telegram_id

    if player_won:
        # Winner side ELO + reward. For NPC fallback, opponent ELO is
        # the attacker's snapshot (no opp ranking row) — calculate_elo_change
        # gets a roughly-balanced delta, then we halve it.
        opp_elo = int(rk_b.elo_points) if rk_b is not None else int(rk_a.elo_points)
        win_delta, lose_delta = calculate_elo_change(int(rk_a.elo_points), opp_elo)
        if is_npc_fallback:
            win_delta = max(1, win_delta // 2)
            lose_delta = lose_delta // 2  # signed negative — halve magnitude
        rk_a.elo_points = int(rk_a.elo_points) + win_delta
        rk_a.wins = int(rk_a.wins or 0) + 1
        rk_a.last_combat = now

        if rk_b is not None:
            rk_b.elo_points = max(0, int(rk_b.elo_points) + lose_delta)
            rk_b.losses = int(rk_b.losses or 0) + 1
            rk_b.last_combat = now

        arena_reward = calculate_arena_reward(rk_a.elo_points)
        if is_npc_fallback:
            arena_reward = arena_reward // 2
        p_a.spirit_stones = int(p_a.spirit_stones or 0) + arena_reward

        # NOTE (2026-06-01): the scroll milestone counts TOTAL wins (every 10th).
        # A prior attempt to award scrolls only on PvP wins caused milestones to be
        # silently skipped when the 10th win was an NPC fallback, so it was reverted.
        # The NPC-fallback scroll-farm is instead throttled structurally: the per-user
        # rate limiter + the 180s arena queue timeout (≈1 fallback/3min → ~30min per
        # scroll) + the launch wipe. A hard PvP-only milestone needs a pvp_wins column
        # (deferred — wipe-bound, low value).
        try:
            scroll_name = await _maybe_award_arena_scroll(
                session, p_a.telegram_id, rk_a.wins
            )
        except Exception:
            logger.exception("settle_arena_duel: scroll award failed duel=%s", duel.id)

        try:
            from core.achievement_engine import check_achievements, reset_achievement_progress
            await check_achievements(session, p_a.telegram_id, "arena_wins", rk_a.wins)
            await check_achievements(session, p_a.telegram_id, "win_streak", 1)
            if p_b is not None:
                await reset_achievement_progress(session, p_b.telegram_id, "win_streak")
        except Exception:
            logger.exception("settle_arena_duel: achievements failed duel=%s", duel.id)

        try:
            from core.quest_engine import track_quest
            from core.faction_engine import update_quest_progress as fac_quest_progress
            from core.body_tempering_engine import add_tempering_progress
            await track_quest(session, p_a.telegram_id, "arena_win", 1)
            rank_pos = await _get_arena_rank_pos(session, p_a.telegram_id)
            if rank_pos is not None and rank_pos <= 3:
                await track_quest(session, p_a.telegram_id, "arena_top3", 1)
            await fac_quest_progress(session, p_a.telegram_id, "pvp_win")
            add_tempering_progress(p_a, 12)
        except Exception:
            logger.exception("settle_arena_duel: quest/faction/tempering failed duel=%s", duel.id)
    elif player_lost:
        # NPC fallback, player lost. D-Combat #3 (v16.6): the LOSS is now FULL
        # (honest) — only the WIN is halved (anti-farm). Previously both were
        # halved, so an empty-pool player (the norm at ~57 players) climbed AND
        # fell at half rate, making their ELO a different currency from a PvP
        # grinder's. Half gain + full loss keeps NPC-farming unattractive without
        # discounting the downside of a real loss.
        _, lose_delta = calculate_elo_change(int(rk_a.elo_points), int(rk_a.elo_points))
        rk_a.elo_points = max(0, int(rk_a.elo_points) + lose_delta)
        rk_a.losses = int(rk_a.losses or 0) + 1
        rk_a.last_combat = now
        try:
            from core.achievement_engine import reset_achievement_progress
            await reset_achievement_progress(session, p_a.telegram_id, "win_streak")
        except Exception:
            logger.exception("settle_arena_duel: streak reset failed duel=%s", duel.id)
    elif pvp_player_b_won and p_b is not None and rk_b is not None:
        # PvP, attacker lost — mirror "player_won" but flipped sides.
        win_delta, lose_delta = calculate_elo_change(int(rk_b.elo_points), int(rk_a.elo_points))
        rk_b.elo_points = int(rk_b.elo_points) + win_delta
        rk_b.wins = int(rk_b.wins or 0) + 1
        rk_b.last_combat = now
        rk_a.elo_points = max(0, int(rk_a.elo_points) + lose_delta)
        rk_a.losses = int(rk_a.losses or 0) + 1
        rk_a.last_combat = now
        arena_reward = calculate_arena_reward(rk_b.elo_points)
        p_b.spirit_stones = int(p_b.spirit_stones or 0) + arena_reward
        try:
            scroll_name = await _maybe_award_arena_scroll(session, p_b.telegram_id, rk_b.wins)
        except Exception:
            logger.exception("settle_arena_duel: scroll award failed duel=%s", duel.id)
        try:
            from core.achievement_engine import check_achievements, reset_achievement_progress
            await check_achievements(session, p_b.telegram_id, "arena_wins", rk_b.wins)
            await check_achievements(session, p_b.telegram_id, "win_streak", 1)
            await reset_achievement_progress(session, p_a.telegram_id, "win_streak")
        except Exception:
            logger.exception("settle_arena_duel: achievements failed duel=%s", duel.id)
        try:
            from core.quest_engine import track_quest
            from core.faction_engine import update_quest_progress as fac_quest_progress
            from core.body_tempering_engine import add_tempering_progress
            await track_quest(session, p_b.telegram_id, "arena_win", 1)
            rank_pos = await _get_arena_rank_pos(session, p_b.telegram_id)
            if rank_pos is not None and rank_pos <= 3:
                await track_quest(session, p_b.telegram_id, "arena_top3", 1)
            await fac_quest_progress(session, p_b.telegram_id, "pvp_win")
            add_tempering_progress(p_b, 12)
        except Exception:
            logger.exception("settle_arena_duel: quest/faction/tempering failed duel=%s", duel.id)
    else:
        # No winner / unrecognised — defensive only (duel engine guarantees tiebreak).
        rk_a.last_combat = now
        if rk_b is not None:
            rk_b.last_combat = now

    # Mastery XP — both real sides (NPC has no PlayerTechnique row to update).
    try:
        activations_a = _count_tech_activations(duel.action_log or [], "a")
        await _award_mastery_xp(
            session, p_a.telegram_id, activations_a, won=player_won,
        )
        if p_b is not None:
            activations_b = _count_tech_activations(duel.action_log or [], "b")
            await _award_mastery_xp(
                session, p_b.telegram_id, activations_b,
                won=(winner_id == p_b.telegram_id),
            )
    except Exception:
        logger.exception("settle_arena_duel: mastery XP failed duel=%s", duel.id)

    # v15.2 — Intent XP. PvE NPC fallback path skips side B internally (no
    # defender Player row). Errors are isolated by SAVEPOINTs inside the
    # helper so a hot conflict on the (player_id, intent) PK cannot poison
    # the ELO/rewards write.
    try:
        from core.intent_engine import award_post_duel_intent_xp
        await award_post_duel_intent_xp(session, duel, winner_id)
    except Exception:
        logger.exception("settle_arena_duel: intent XP failed duel=%s", duel.id)

    # CombatLog row — preserves chat-side history-parity (mode='arena').
    # For NPC fallback, defender_id is NULL (matches legacy chat-side
    # `_arena_timeout` CombatLog with `defender_id=None`).
    try:
        session.add(CombatLog(
            attacker_id=p_a.telegram_id,
            defender_id=p_b.telegram_id if p_b is not None else None,
            mode="arena",
            winner_id=winner_id if winner_id and winner_id != 0 else (None if is_npc_fallback else winner_id),
            rounds_data={
                "rounds": duel.action_log or [],
                "turn_based": True,
                "npc_fallback": bool(is_npc_fallback),
                "elo_delta": {
                    "winner": win_delta,
                    "loser": lose_delta,
                },
                "scroll": scroll_name,
            },
            spirit_stones_reward=arena_reward,
        ))
    except Exception:
        logger.exception("settle_arena_duel: combat_log insert failed duel=%s", duel.id)

    # Final stamp — idempotent guard.
    arena_row.status = "completed"
    if other_arena is not None:
        other_arena.status = "completed"
    return True


__all__ = ["settle_arena_duel"]
