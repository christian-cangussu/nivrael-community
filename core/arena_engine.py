"""v15.1.5 — Arena ELO matchmaking on a DB-backed pool.

Replaces the legacy `context.bot_data["arena_queue"]` chat-only list with
a thin `arena_queue` table both surfaces share. Chat handler and mini-app
webserver call into this engine instead of poking process-local state.

Public surface (kept tiny — settle path is its own module):

    join_queue(session, player, chat_id=None, message_id=None)
        Insert / refresh a 'waiting' row for the player. Idempotent for an
        already-waiting player. Re-uses an old 'expired' row if one exists.

    leave_queue(session, player_id)
        Mark / delete a 'waiting' row. No-op if the player isn't queued.

    try_match(session)
        Scan 'waiting' rows ordered by elo. Returns the spawned DuelSession
        when a match fires, or None when no eligible pair exists.

    check_expirations(session)
        Flip every overdue 'waiting' row to 'expired'. Returns the count.

    get_queue_status(session, player_id)
        Project the row into {state, duel_id?, opponent?, eta?}.

State machine:
                       ┌────────── leave_queue ──────────┐
                       │                                 │
        none ─ join ─► waiting ─ try_match ─► matched ─ settle ─► (kept for audit)
                       │  └────── expires_at ──► expired
                       │
                       └─── refresh on rejoin

Match concurrency: `SELECT ... FOR UPDATE SKIP LOCKED` so two concurrent
matchmaking calls (chat handler + scheduler sweep) don't double-pair a
row. The partial index on (status='waiting') keeps the scan cheap as
historic rows accumulate.

Surface-agnostic: nothing here touches `context.bot_data`. Chat-side
notifications are delivered via `core.notification_engine.notify` so the
DM reaches the player regardless of which surface they're on.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.combat_engine import (
    ARENA_ELO_RANGE,
    ARENA_QUEUE_TIMEOUT_SECONDS,
    CURRENT_SEASON,
    get_current_hp,
)
from database.models import (
    ArenaQueue,
    ArenaRanking,
    DuelSession,
    Player,
)

logger = logging.getLogger(__name__)


# ─── Internal helpers ────────────────────────────────────────────────────────


async def _get_or_create_ranking(session, player_id: int) -> ArenaRanking:
    """Ensure the player has an ArenaRanking row in the current season."""
    row = (await session.execute(
        select(ArenaRanking).where(
            ArenaRanking.player_id == player_id,
            ArenaRanking.season == CURRENT_SEASON,
        )
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


async def _has_active_duel(session, player_id: int) -> bool:
    """True if the player is inside an unresolved duel right now.

    Blocks queueing while a PvP/PvE duel is mid-flight — the alternative
    would be a player matching in arena while still holding a
    waiting_actions row from a prior fight.
    """
    row = (await session.execute(
        select(DuelSession.id).where(
            DuelSession.state.in_(("pending_acceptance", "waiting_actions")),
            ((DuelSession.attacker_id == player_id) | (DuelSession.defender_id == player_id)),
        ).limit(1)
    )).first()
    return row is not None


# ─── join_queue ──────────────────────────────────────────────────────────────


# O ENCONTRO RAPIDO — a outra metade do report do [jogador] (10/09 09:59).
#
# Ele pediu uma tecnica padrao "*to advance paths without having to wait each
# time the 3 minutes counter*". Mas a pergunta anterior a essa e': **por que' e'
# que ele espera 3 minutos?**
#
# MEDIDO a 2026-09-12, nas duas bases:
#
#     duelos PvP de arena nos ultimos 30 dias ....    0 (main)  ·  1 (s2, expirou)
#     ultimo duelo PvP de QUALQUER tipo .......... 2026-07-31
#     arena_npc_fallback nos ultimos 7 dias ......  203 (main)  · 24 (s2)
#     arena_npc_fallback all-time ................ 16.516 (main) · 253 (s2)
#
# **A arena e' 100% NPC.** Ninguem encontra ninguem ha' seis semanas. Os 180 s
# nao sao uma procura: sao um ecra de espera por uma pessoa que nao esta' la',
# ao fim do qual chega sempre o mesmo NPC. Isso e' exactamente o que a Lei §1
# proibe — o jogador a olhar para um relogio que nao decide nada.
#
# O QUE MUDA: a espera passa a durar o que ha' para esperar. Se ha' OUTRA alma
# na fila, os 180 s de sempre (ha' de facto alguem para encontrar, e o
# `try_match` empareja quase de imediato). Se a fila esta' VAZIA, uma janela
# curta — tempo para uma segunda pessoa chegar, nao para desistir.
#
# ARENA_QUEUE_SOLO_TIMEOUT_SECONDS = 30 e nao 0 DE PROPOSITO: a zero, duas
# pessoas que toquem "entrar" com dez segundos de diferenca nunca mais se
# encontrariam — ter-se-ia matado o PvP para consertar a espera por ele, que e'
# o oposto do que se quer. Trinta segundos e' curto para quem espera e largo
# para quem chega.

# ⚠️ E a tela tem de DIZER a verdade enquanto espera (ver `get_queue_status`:
# `pool_empty`). A mensagem antiga culpava o ELO, e essa nunca foi a razao.
ARENA_QUEUE_SOLO_TIMEOUT_SECONDS = 30


def encontro_rapido_on(world_key: str | None = None) -> bool:
    """Gate estavel da flag per-world `arena_encontro_rapido`.

    Fail-safe -> False: com ela OFF a fila dura os 180 s de sempre e nada nesta
    metade do lote existe para o jogador.
    """
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("arena_encontro_rapido", world_key))
    except Exception:
        return False


async def _others_waiting(session, player_id: int) -> int:
    """Quantas OUTRAS almas estao na fila agora."""
    from sqlalchemy import func as _func
    now = datetime.now(timezone.utc)
    return int((await session.execute(
        select(_func.count()).select_from(ArenaQueue).where(
            ArenaQueue.status == "waiting",
            ArenaQueue.player_id != player_id,
            ArenaQueue.expires_at > now,
        )
    )).scalar() or 0)


async def _queue_window_seconds(session, player_id: int) -> tuple[int, bool]:
    """(segundos de espera, a fila esta' vazia?).

    Com a flag OFF devolve sempre os 180 s de hoje e `False` — e sem uma query
    a mais, para que o caminho do `main` fique identico ao de sempre.
    """
    if not encontro_rapido_on():
        return ARENA_QUEUE_TIMEOUT_SECONDS, False
    try:
        others = await _others_waiting(session, player_id)
    except Exception:
        logger.exception("arena: contagem da fila falhou player=%s", player_id)
        return ARENA_QUEUE_TIMEOUT_SECONDS, False
    if others > 0:
        return ARENA_QUEUE_TIMEOUT_SECONDS, False
    return ARENA_QUEUE_SOLO_TIMEOUT_SECONDS, True


async def join_queue(
    session,
    player: Player,
    chat_id: int | None = None,
    message_id: int | None = None,
) -> dict:
    """Place `player` into the arena pool.

    Returns one of:
      - {ok: True, state: 'waiting', queue: ArenaQueue, idempotent: bool}
      - {ok: True, state: 'matched', duel_id: str}  (already matched, not yet seen)
      - {ok: False, reason: 'hp_too_low' | 'in_active_duel'}
    """
    if get_current_hp(player) <= 0:
        return {"ok": False, "reason": "hp_too_low"}

    # Hotfix "A Volta" 2026-07-07 (#12) — Selo de Supressão: conta selada não
    # entra na fila (choke point único do chat + mini-app + sweep).
    from core.combat_engine import is_pvp_sealed
    if await is_pvp_sealed(session, player.telegram_id):
        return {"ok": False, "reason": "pvp_sealed"}

    if await _has_active_duel(session, player.telegram_id):
        return {"ok": False, "reason": "in_active_duel"}

    ranking = await _get_or_create_ranking(session, player.telegram_id)
    elo = int(ranking.elo_points or 1000)
    now = datetime.now(timezone.utc)
    # O ENCONTRO RAPIDO — a espera dura o que ha' para esperar. Flag OFF => os
    # 180 s de sempre, e sem a query da contagem.
    _window, _pool_empty = await _queue_window_seconds(session, player.telegram_id)
    expires_at = now + timedelta(seconds=_window)

    existing = (await session.execute(
        select(ArenaQueue).where(
            ArenaQueue.player_id == player.telegram_id
        ).with_for_update()
    )).scalar_one_or_none()

    if existing is not None and existing.status == "matched" and existing.duel_id:
        # Already paired — surface the live duel id instead of re-queueing.
        return {"ok": True, "state": "matched", "duel_id": str(existing.duel_id)}

    if existing is not None and existing.status == "waiting":
        # Same player tapping "join" twice — refresh chat anchor + extend
        # the expiry window so they don't time out mid-decision.
        existing.elo = elo
        existing.expires_at = expires_at
        if chat_id is not None:
            existing.chat_id = chat_id
        if message_id is not None:
            existing.message_id = message_id
        return {"ok": True, "state": "waiting", "queue": existing, "idempotent": True,
                **({"pool_empty": True} if _pool_empty else {})}

    if existing is not None:
        # Recycle an 'expired' / leftover-'matched' row.
        existing.elo = elo
        existing.joined_at = now
        existing.status = "waiting"
        existing.duel_id = None
        existing.chat_id = chat_id
        existing.message_id = message_id
        existing.expires_at = expires_at
        return {"ok": True, "state": "waiting", "queue": existing, "idempotent": False,
                **({"pool_empty": True} if _pool_empty else {})}

    row = ArenaQueue(
        player_id=player.telegram_id,
        elo=elo,
        joined_at=now,
        status="waiting",
        duel_id=None,
        chat_id=chat_id,
        message_id=message_id,
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()
    # A key so' nasce quando ha' alguma coisa a dizer => payload do `main`
    # byte-identico (licao MV-7: key sempre-presente = OFF-identity quebrada).
    return {"ok": True, "state": "waiting", "queue": row, "idempotent": False,
            **({"pool_empty": True} if _pool_empty else {})}


# ─── leave_queue ─────────────────────────────────────────────────────────────


async def leave_queue(session, player_id: int) -> bool:
    """Remove the player from the pool. Returns True if a row was removed.

    Only acts on 'waiting' rows — 'matched' rows belong to a live duel and
    have to be settled, not torn down. To bail out of an active match the
    player must forfeit the duel itself.
    """
    row = (await session.execute(
        select(ArenaQueue).where(
            ArenaQueue.player_id == player_id,
            ArenaQueue.status == "waiting",
        ).with_for_update()
    )).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    return True


# ─── try_match ───────────────────────────────────────────────────────────────


async def try_match(session) -> DuelSession | None:
    """Scan 'waiting' rows by elo and pair the first eligible duo.

    Pairs are eligible when their elo gap is within `ARENA_ELO_RANGE`.
    Locks both rows + creates the duel atomically — caller commits.

    Returns the spawned DuelSession on success, None when no pair fits.
    """
    from core.duel_engine import start_duel  # local import — circular guard

    candidates = (await session.execute(
        select(ArenaQueue)
        .where(ArenaQueue.status == "waiting")
        .order_by(ArenaQueue.elo, ArenaQueue.joined_at)
        .with_for_update(skip_locked=True)
    )).scalars().all()

    if len(candidates) < 2:
        return None

    # Linear scan: since candidates are sorted by elo, the closest pair
    # for any row is its neighbour. A single pass surfaces the smallest
    # elo gap first; only one match per call so the next sweep handles
    # subsequent waiters.
    pair: tuple[ArenaQueue, ArenaQueue] | None = None
    for i in range(len(candidates) - 1):
        a = candidates[i]
        b = candidates[i + 1]
        if abs(int(a.elo) - int(b.elo)) <= ARENA_ELO_RANGE:
            pair = (a, b)
            break

    if pair is None:
        return None

    a_row, b_row = pair
    p_a = (await session.execute(
        select(Player).where(Player.telegram_id == a_row.player_id).with_for_update()
    )).scalar_one_or_none()
    p_b = (await session.execute(
        select(Player).where(Player.telegram_id == b_row.player_id).with_for_update()
    )).scalar_one_or_none()
    if p_a is None or p_b is None:
        # Player rows vanished mid-flight — drop both queue rows defensively.
        if p_a is None:
            a_row.status = "expired"
        if p_b is None:
            b_row.status = "expired"
        return None

    # Both consented via the queue — duel starts immediately at
    # 'waiting_actions' with the round clock running.
    duel = await start_duel(session, p_a, p_b, auto_accept=True)
    now = datetime.now(timezone.utc)

    for row in (a_row, b_row):
        row.status = "matched"
        row.duel_id = duel.id
        row.expires_at = now  # zero out — match obsoletes the queue timer

    # Bell notification on both sides so the player sees the match no
    # matter which surface they're on. Mini-app polling will also pick
    # this up via `get_queue_status`.
    try:
        from core.notification_engine import notify as _notify
        a_name = (duel.fighter_a or {}).get("dao_name") or (duel.fighter_a or {}).get("name") or "?"
        b_name = (duel.fighter_b or {}).get("dao_name") or (duel.fighter_b or {}).get("name") or "?"
        await _notify(
            session, duel.attacker_id, "arena_match_found",
            title_key="notif_arena_match_title",
            body_key="notif_arena_match_body",
            payload={"name": b_name},
            ref_id=str(duel.id),
            icon="🏟️",
            target_tab="combat",
            priority=1,
        )
        await _notify(
            session, duel.defender_id, "arena_match_found",
            title_key="notif_arena_match_title",
            body_key="notif_arena_match_body",
            payload={"name": a_name},
            ref_id=str(duel.id),
            icon="🏟️",
            target_tab="combat",
            priority=1,
        )
    except Exception:
        logger.exception("arena match notify failed duel=%s", duel.id)

    return duel


# ─── NPC fallback on timeout ─────────────────────────────────────────────────


def _archetype_for_realm(realm: int) -> str:
    """Map player realm tier → NPC archetype for the arena fallback fight.

    Mirrors the heuristic used in api_combat_npc_duel_create so the
    fallback feels consistent with the explicit NPC hunt at the same
    realm tier.
    """
    r = int(realm or 0)
    if r >= 7:
        return "boss"
    if r >= 5:
        return "demon"
    if r >= 3:
        return "sect_disciple"
    return "bandit"


async def _spawn_npc_fallback(session, row: ArenaQueue) -> "DuelSession | None":
    """Replace an expired queue row with a turn-based NPC duel.

    Owner brief 2026-05-21: *"quando voce nao encontra jogador pra
    batalhar em 2 minutos, voce batalha com o npc e vai subindo seu
    elo"* — preserves the legacy chat-side fallback that v15.1.5
    removed, adapted to the new turn-based pipeline. ELO + rewards
    are halved at settle (see arena_duel_settle.py).

    The duel uses `pve_source="arena_npc_fallback"` so the settle
    dispatcher can recognise it, but the ArenaQueue.duel_id link is
    what actually routes settle to settle_arena_duel (which handles
    both PvP and NPC-fallback branches).
    """
    from core.duel_engine import start_duel_pve

    player = (await session.execute(
        select(Player).where(
            Player.telegram_id == row.player_id
        ).with_for_update()
    )).scalar_one_or_none()
    if player is None:
        return None
    # HP gate — a dead player can't auto-enter combat (Lei §1: no
    # forced losses). Row falls through to 'expired' and the player
    # can re-queue after restoring HP.
    if get_current_hp(player) <= 0:
        return None

    archetype = _archetype_for_realm(int(player.realm or 0))
    duel = await start_duel_pve(
        session, player,
        archetype=archetype,
        difficulty="normal",
        source="arena_npc_fallback",
        context={
            "elo_at_match": int(row.elo or 1000),
            "queued_at": row.joined_at.isoformat() if row.joined_at else None,
        },
    )

    row.status = "matched"
    row.duel_id = duel.id
    # Keep chat_id intact so the scheduler sweep DMs the chat-side
    # player with "abre mini-app — adversário NPC encontrado".

    try:
        from core.notification_engine import notify as _notify
        opp_name = (duel.fighter_b or {}).get("dao_name") or "?"
        await _notify(
            session, player.telegram_id, "arena_match_found",
            title_key="notif_arena_match_title",
            body_key="notif_arena_match_npc_body",
            payload={"name": opp_name},
            ref_id=str(duel.id),
            icon="🤖",
            target_tab="combat",
            priority=1,
        )
    except Exception:
        logger.exception("arena npc fallback notify failed duel=%s", duel.id)

    return duel


# ─── check_expirations ───────────────────────────────────────────────────────


async def check_expirations(session) -> int:
    """Process every overdue 'waiting' row. Returns the count of rows
    touched (NPC-fallback matched + truly expired).

    v15.1.5-hf4 — instead of marking rows as 'expired' (which was
    abandoning the player), each overdue row gets an NPC-fallback duel
    spawned via `_spawn_npc_fallback`. Players keep climbing ELO even
    when the live pool is empty. Falls back to 'expired' only when
    spawn fails (player offline-deleted, HP=0, etc.).

    Called from the scheduler sweep + opportunistically by polling
    endpoints (so even without the sweeper a polling client surfaces
    the matched/expired state correctly).
    """
    now = datetime.now(timezone.utc)
    rows = (await session.execute(
        select(ArenaQueue).where(
            ArenaQueue.status == "waiting",
            ArenaQueue.expires_at < now,
        ).with_for_update(skip_locked=True)
    )).scalars().all()
    touched = 0
    for row in rows:
        try:
            duel = await _spawn_npc_fallback(session, row)
        except Exception:
            logger.exception("arena npc fallback spawn failed player=%s", row.player_id)
            duel = None
        if duel is None:
            row.status = "expired"
        touched += 1
    return touched


# ─── get_queue_status ────────────────────────────────────────────────────────


async def get_queue_status(session, player_id: int) -> dict:
    """Project the player's queue row for the UI.

    Shapes returned:
      {state: 'none'}                              — never queued / cleaned
      {state: 'waiting', remaining_seconds, elo_range, joined_at}
      {state: 'matched', duel_id, opponent_dao_name}
      {state: 'expired'}

    The polling client uses this to switch between idle / waiting /
    redirect-to-duel / retry-banner.
    """
    row = (await session.execute(
        select(ArenaQueue).where(ArenaQueue.player_id == player_id)
    )).scalar_one_or_none()

    if row is None:
        return {"state": "none"}

    if row.status == "matched" and row.duel_id is not None:
        # Resolve opponent name + NPC-fallback flag from the linked duel.
        duel = (await session.execute(
            select(DuelSession).where(DuelSession.id == row.duel_id)
        )).scalar_one_or_none()

        # v15.3-hf — Self-heal: if the linked duel is already finished/
        # forfeited/expired/cancelled, the matched state is dead. Flip the
        # queue row to 'completed' on read so the UI doesn't get stuck on
        # "preparando arena…" forever. This also covers the case where
        # settle_arena_duel raised an exception mid-flight and the row
        # wasn't flipped — the next read repairs it.
        #
        # Owner-reported bug (player [jogador], 2026-05-22): after
        # winning a tiebreak arena duel, the mini-app Arena tab kept
        # showing "Vais lutar contra X — preparando arena..." indefinitely.
        # Root cause: arena_row.status stayed 'matched' because the settle
        # path silently failed on a downstream side-effect. The fix here
        # makes the read path the source of truth for "is this match live?"
        # — if the duel is dead, the queue row is dead.
        if duel is None or duel.state in ("finished", "forfeited", "expired", "cancelled", "declined"):
            row.status = "completed"
            # Best-effort: try settle once more in case it failed before.
            # Guarded so a hot bug here can't break the read itself.
            if duel is not None and duel.state in ("finished", "forfeited"):
                try:
                    from core.arena_duel_settle import settle_arena_duel
                    await settle_arena_duel(session, duel, row)
                except Exception:
                    logger.exception(
                        "self-heal settle_arena_duel failed duel=%s — row flipped anyway",
                        row.duel_id,
                    )
            return {"state": "none"}

        opp = None
        is_npc_fallback = False
        if duel is not None:
            is_npc_fallback = (
                duel.defender_id is None
                and (duel.pve_source or "") == "arena_npc_fallback"
            )
            opp_id = duel.defender_id if duel.attacker_id == player_id else duel.attacker_id
            opp_fighter = duel.fighter_b if duel.attacker_id == player_id else duel.fighter_a
            if isinstance(opp_fighter, dict):
                opp = opp_fighter.get("dao_name") or opp_fighter.get("name")
            if not opp and opp_id is not None:
                opp_player = (await session.execute(
                    select(Player).where(Player.telegram_id == opp_id)
                )).scalar_one_or_none()
                if opp_player is not None:
                    opp = opp_player.dao_name or opp_player.display_name or opp_player.username
        return {
            "state": "matched",
            "duel_id": str(row.duel_id),
            "opponent_dao_name": opp or "?",
            "is_npc_fallback": bool(is_npc_fallback),
        }

    if row.status == "expired":
        return {"state": "expired"}

    # v15.3-hf — 'completed' rows are historical (last duel settled). Treat
    # as if no queue exists so the UI shows the Join button again. Without
    # this, a row sitting in 'completed' status would fall through to the
    # waiting-clock branch below and render a phantom expired state.
    if row.status == "completed":
        return {"state": "none"}

    # status == 'waiting' — surface countdown so the UI can render a clock.
    now = datetime.now(timezone.utc)
    remaining = max(0, int((row.expires_at - now).total_seconds()))
    if remaining == 0:
        # Lazy-expire on read so the UI doesn't show a stale waiting state
        # while the sweeper hasn't run yet.
        row.status = "expired"
        return {"state": "expired"}
    # O ENCONTRO RAPIDO — a tela tem de DIZER por quem se espera.
    #
    # O que estava la': um relogio de 3 minutos e, no fim,
    # `combat_arena_expired_chat_hint` a dizer *"ninguem com ELO compativel foi
    # encontrado"* — e essa **nunca** foi a razao verdadeira. O NPC existe
    # precisamente para tornar o pool irrelevante: o jogador ia SEMPRE lutar. A
    # mensagem culpava um sistema (o ELO) por uma coisa que nao dependia dele,
    # que e' a forma mais cara de mentir, porque manda o jogador tentar
    # consertar o que nao esta' partido.
    #
    # `pool_empty` diz a verdade simples: nao ha' mais ninguem na fila agora, e
    # o que vem a seguir e' um adversario do mundo. A key so' nasce quando e'
    # verdade E com a flag ligada => payload do `main` byte-identico.
    _empty = False
    if encontro_rapido_on():
        try:
            _empty = (await _others_waiting(session, player_id)) == 0
        except Exception:
            logger.exception("arena: contagem da fila falhou na leitura player=%s",
                             player_id)
            _empty = False
    return {
        "state": "waiting",
        "remaining_seconds": remaining,
        "elo_range": ARENA_ELO_RANGE,
        "elo": int(row.elo),
        "joined_at": row.joined_at.isoformat() if row.joined_at else None,
        **({"pool_empty": True} if _empty else {}),
    }


__all__ = [
    "join_queue",
    "leave_queue",
    "try_match",
    "check_expirations",
    "get_queue_status",
    "encontro_rapido_on",
    "ARENA_QUEUE_SOLO_TIMEOUT_SECONDS",
]
