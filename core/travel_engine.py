"""Onda 4b — Travel engine (the piece that makes the living world CONTROLLABLE).

Onda 3 gave the world a persistent NPC population; Onda 4a gave it a home (the
continental plaza) + a hunt (the bounty board) — all scoped to the player's
``current_continent``. But the player was stuck in the continent they were born
in: ``set_player_continent`` existed in ``core/continent_engine.py`` and was
NEVER called. This engine wires it into a real action.

Travelling between the five continents changes ``current_continent`` — and with
that single field, EVERYTHING the earlier waves built already follows: the
plaza (4a), the bounty board (4a), the NPC encounter preference
(``pick_encounter_npc``), and the *Continent presence* component of sect
affinity (``core/affinity_engine.py``). No new code makes that happen — it
emerges. We just tell the player it does (Lei §1).

Design (mirrors core/bounty_engine + core/npc_cultivator_engine):
    * module-level env-tunable constants (engine, not DB — wipe-safe, Lei §5)
    * pure cost/cooldown helpers
    * an async ``can_travel`` (validation, with disclosure reasons)
    * one defensive ``do_travel`` mutator — the caller (endpoint / chat handler)
      locks the player row FOR UPDATE and owns the commit, exactly like
      ``bounty_engine.claim_bounty``.
    * a ``list_travel_destinations`` read for the Travel map (identity +
      presence + cost + per-destination eligibility).

Production safety (57 live players — Lei §5 + §1 + §4):
    * ADDITIVE — travel never locks any farm. ``current_continent`` only ADDS
      context; it removes access to nothing. The per-continent content
      hard-gate is deferred to the WIPE (Onda 5/6).
    * COST in spirit_stones ONLY — NEVER jade (Lei §4: jade is acceleration /
      cosmetic, not a grind faucet; we never sell "travel faster").
    * OWN cooldown (``Player.last_travel_at``) — never shared with any
      combat/farm cooldown (Lei §5).
    * IDEMPOTENT — travelling to the continent you're already in is a no-op
      disclosed reason ("already_here"), it costs nothing; a double-click that
      lands after the move sees the new current_continent and no-ops.
    * PRIVACY — the presence map reuses the plaza's ``shadow_mode == False``
      filter; shadow players never count.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from core.continent_engine import (
    CONTINENT_KEYS,
    DEFAULT_SPAWN_CONTINENT,
    is_demonic_only,
    is_valid_continent,
    project_continent_identity,
    set_player_continent,
)
from database.models import Player

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Tuning constants (engine, not DB — wipe-safe; env-overridable for ops tuning)
# ══════════════════════════════════════════════════════════════════════════

# Cost in spirit_stones, scaled to the traveller's realm (a higher cultivator
# carries more, but the road between continents is always meaningful). Modest,
# NOT punitive — at realm 0 it's 200 (players start with 500 and earn far more);
# at realm 10 it's 700. Comparable to a couple of bounty rewards, never a wall.
TRAVEL_COST_BASE = int(os.getenv("TRAVEL_COST_BASE", "200"))
TRAVEL_COST_PER_REALM = int(os.getenv("TRAVEL_COST_PER_REALM", "50"))

# The passage between continents takes time (Wuxia). Its OWN cooldown — never
# shared with combat/farm cooldowns (Lei §5). A few hours: long enough that
# travel is a deliberate choice, short enough that it never feels like a jail.
TRAVEL_COOLDOWN_HOURS = float(os.getenv("TRAVEL_COOLDOWN_HOURS", "4"))

# Presence window for the destination map (mirrors the plaza's 14-day "recently
# online" cut). Shadow players are never counted regardless.
TRAVEL_PRESENCE_DAYS = int(os.getenv("TRAVEL_PRESENCE_DAYS", "14"))


# ══════════════════════════════════════════════════════════════════════════
# Pure cost / cooldown helpers
# ══════════════════════════════════════════════════════════════════════════

def travel_cost(player, dest: str | None = None) -> int:
    """Spirit-stone cost to travel, scaled to the player's realm. ``dest`` is
    accepted for forward-compat (per-destination pricing) but unused today."""
    realm = int(getattr(player, "realm", 0) or 0)
    return int(TRAVEL_COST_BASE + TRAVEL_COST_PER_REALM * max(0, realm))


def travel_cooldown_remaining(player, now: datetime | None = None) -> int:
    """Seconds left on the travel cooldown (0 if ready / never travelled)."""
    last = getattr(player, "last_travel_at", None)
    if last is None:
        return 0
    now = now or datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    remain = TRAVEL_COOLDOWN_HOURS * 3600 - (now - last).total_seconds()
    return int(remain) if remain > 0 else 0


async def _tiandao_travel_mult(session, origin: str | None, dest: str | None) -> float:
    """MV-2 — 'estrada fechada': uma Maré de Bestas IGNORADA encarece a viagem
    DE/PARA aquele continente por um tempo (gated ``tiandao_director``;
    fail-safe 1.0 — a viagem nunca quebra por causa do evento).

    MV-3 — com ``estados_regionais`` ON, o ESTADO absorve a penalidade (UMA
    verdade: sitiada = estrada cara); OFF → o derivado do MV-2 continua a
    valer. O dispatch vive em region_state_engine.road_penalized_continents."""
    try:
        from core.region_state_engine import road_penalized_continents
        from core.tiandao_engine import TRAVEL_PENALTY_MULT
        pen = await road_penalized_continents(session)
        if pen and ((origin and origin in pen) or (dest and dest in pen)):
            return float(TRAVEL_PENALTY_MULT)
    except Exception:
        logger.debug("tiandao travel mult lookup failed", exc_info=True)
    return 1.0


async def _is_demonic_eligible(session, player_id: int) -> bool:
    """True if the player walks the Demonic Path (allowed into Mòyǔ). Mirrors
    the gate inside continent_engine.set_player_continent — pre-checked here so
    the Travel surface can DISCLOSE the lock (Lei §1) instead of crashing."""
    try:
        from core.path_engine import get_player_path_raw, is_demonic_path
        raw = await get_player_path_raw(session, player_id)
        return bool(raw is not None and is_demonic_path(raw))
    except Exception:
        logger.debug("travel demonic eligibility lookup failed", exc_info=True)
        return False


# ══════════════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════════════

async def can_travel(session, player, dest: str) -> tuple[bool, str | None]:
    """(ok, reason). ``reason`` is a stable key the surfaces localize:
    ``invalid_dest`` / ``already_here`` / ``locked_demonic`` / ``on_cooldown`` /
    ``not_enough_stones``."""
    if not is_valid_continent(dest):
        return False, "invalid_dest"
    current = player.current_continent if is_valid_continent(player.current_continent) else DEFAULT_SPAWN_CONTINENT
    if dest == current:
        return False, "already_here"
    if is_demonic_only(dest) and not await _is_demonic_eligible(session, player.telegram_id):
        return False, "locked_demonic"
    if travel_cooldown_remaining(player) > 0:
        return False, "on_cooldown"
    # MV-2 — o preço honesto inclui a estrada fechada (mult 1.0 com a flag OFF).
    mult = await _tiandao_travel_mult(session, current, dest)
    if int(player.spirit_stones or 0) < int(travel_cost(player, dest) * mult):
        return False, "not_enough_stones"
    return True, None


# ══════════════════════════════════════════════════════════════════════════
# Travel — defensive, idempotent. Caller locks player FOR UPDATE + owns commit.
# ══════════════════════════════════════════════════════════════════════════

async def do_travel(session, player, dest: str) -> dict[str, Any]:
    """Move the player to ``dest``: validate, debit stones, set continent, stamp
    the cooldown. Best-effort (never raises). The caller (endpoint / chat
    handler) locks the ``player`` row FOR UPDATE and owns the commit — exactly
    like ``bounty_engine.claim_bounty`` — so the stone debit can't lost-update."""
    try:
        # MV-2 — estrada fechada: o mesmo mult de can_travel infla o débito real.
        current = player.current_continent if is_valid_continent(player.current_continent) else DEFAULT_SPAWN_CONTINENT
        mult = await _tiandao_travel_mult(session, current, dest)
        ok, reason = await can_travel(session, player, dest)
        if not ok:
            out: dict[str, Any] = {"ok": False, "reason": reason}
            if reason == "not_enough_stones":
                out["cost"] = int(travel_cost(player, dest) * mult)
                out["have"] = int(player.spirit_stones or 0)
            elif reason == "on_cooldown":
                out["cooldown_remaining_ms"] = travel_cooldown_remaining(player) * 1000
            return out
        cost = int(travel_cost(player, dest) * mult)
        # set_player_continent re-enforces the demonic gate (raises ValueError)
        # and writes current_continent inside a SAVEPOINT. We pre-checked, so it
        # should pass; guard the gate race defensively.
        try:
            moved = await set_player_continent(session, player.telegram_id, dest)
        except ValueError:
            return {"ok": False, "reason": "locked_demonic"}
        if not moved:
            return {"ok": False, "reason": "player_not_found"}
        # Debit + stamp on the caller's locked instance (same identity-map row
        # set_player_continent just updated). Committed by the caller.
        player.spirit_stones = int(player.spirit_stones or 0) - cost
        player.last_travel_at = datetime.now(timezone.utc)
        # Achievement #22 Continent Explorer — any successful travel proves the
        # player has stood on 2 distinct continents (can_travel rejects
        # dest == current). SET event, value = distinct count. The inner
        # try/except is load-bearing: a raise here would hit the outer except
        # AFTER the debit mutations, so the caller would commit a paid travel
        # while reporting failure ([jogador] report 2026-06-12 — the event was
        # never fired anywhere since Onda 4b shipped).
        try:
            from core.achievement_engine import check_achievements
            await check_achievements(session, player.telegram_id, "continents_visited", 2)
        except Exception:
            logger.warning("continents_visited fire failed (player=%s)",
                           player.telegram_id, exc_info=True)
        # MV-5 — ao CHEGAR, o mundo pode te chamar: oferta de storylet se houver
        # um verdadeiro AQUI (pacer/cooldown no engine). Aditivo + flag-gated
        # (quests_vivas OFF → None sem query); um erro aqui nunca desfaz a
        # viagem já debitada (mesmo contrato do fire de achievement acima).
        storylet_offer = None
        try:
            from core.storylet_engine import maybe_offer
            storylet_offer = await maybe_offer(session, player, source="travel")
        except Exception:
            logger.warning("storylet travel offer failed (player=%s)",
                           player.telegram_id, exc_info=True)
        # MV-8 — quem te procurava naquele destino te encontra na CHEGADA. O
        # mapa já avisou (chip `hunted`), então nada aqui é surpresa (Lei §1).
        # MESMO contrato pós-débito dos dois blocos acima: o try/except interno
        # é load-bearing — um raise aqui cairia no except externo DEPOIS das
        # mutações e o caller comitaria uma viagem paga reportando falha.
        ambush = None
        try:
            from core.jianghu_engine import ambush_offer
            ambush = await ambush_offer(session, player, source="travel")
        except Exception:
            logger.warning("jianghu ambush travel offer failed (player=%s)",
                           player.telegram_id, exc_info=True)
        # MV-9.5 — QUEM FINALIZA CREDITA. A carga da Caravana chega pelo
        # relógio, não pela porta: quem encomendou e depois viajou tem de a
        # receber na chegada, senão o progresso espera por uma visita à praça
        # que pode nunca acontecer. A carga é do JOGADOR, não da cidade —
        # segue-o para onde ele for. MESMO contrato pós-débito: try/except
        # interno load-bearing.
        caravan_delivered = None
        try:
            from core.caravan_engine import credit_arrived
            caravan_delivered = await credit_arrived(session, player) or None
        except Exception:
            logger.warning("caravan credit on travel failed (player=%s)",
                           player.telegram_id, exc_info=True)
        out = {
            "ok": True,
            "continent": dest,
            "spent_stones": cost,
            "spirit_stones": int(player.spirit_stones or 0),
            "cooldown_remaining_ms": int(TRAVEL_COOLDOWN_HOURS * 3600 * 1000),
        }
        if storylet_offer:
            out["storylet_offer"] = storylet_offer
        if ambush:
            out["jianghu_ambush"] = ambush
        if caravan_delivered:
            out["caravan_delivered"] = caravan_delivered
        return out
    except Exception:
        logger.exception("do_travel failed (player=%s, dest=%s)",
                         getattr(player, "telegram_id", None), dest)
        return {"ok": False, "reason": "internal_error"}


# ══════════════════════════════════════════════════════════════════════════
# Reads — the destination map (identity + presence + cost + eligibility)
# ══════════════════════════════════════════════════════════════════════════

async def _presence_by_continent(session, exclude_id: int) -> dict[str, int]:
    """Non-shadow players recently online, grouped by continent (privacy: shadow
    never counts — same filter as the plaza). Self excluded."""
    out: dict[str, int] = {}
    try:
        cut = datetime.now(timezone.utc) - timedelta(days=TRAVEL_PRESENCE_DAYS)
        rows = (await session.execute(
            select(Player.current_continent, func.count())
            .where(
                Player.shadow_mode == False,  # noqa: E712
                Player.last_online >= cut,
                Player.telegram_id != exclude_id,
            ).group_by(Player.current_continent)
        )).all()
        for c, n in rows:
            if c:
                out[str(c)] = int(n)
    except Exception:
        logger.debug("travel _presence_by_continent failed", exc_info=True)
    return out


async def _npc_count_by_continent(session) -> dict[str, int]:
    """Active NPC cultivators grouped by continent (the plaza's population)."""
    out: dict[str, int] = {}
    try:
        from database.models import NpcCultivator
        rows = (await session.execute(
            select(NpcCultivator.continent_key, func.count())
            .where(NpcCultivator.status == "active")
            .group_by(NpcCultivator.continent_key)
        )).all()
        for c, n in rows:
            if c:
                out[str(c)] = int(n)
    except Exception:
        logger.debug("travel _npc_count_by_continent failed", exc_info=True)
    return out


async def _bounty_count_by_continent(session) -> dict[str, int]:
    """Open, non-expired bounty contracts grouped by continent (the hunt)."""
    out: dict[str, int] = {}
    try:
        from database.models import Bounty
        now = datetime.now(timezone.utc)
        rows = (await session.execute(
            select(Bounty.continent_key, func.count())
            .where(
                Bounty.status == "open",
                (Bounty.expires_at.is_(None)) | (Bounty.expires_at > now),
            ).group_by(Bounty.continent_key)
        )).all()
        for c, n in rows:
            if c:
                out[str(c)] = int(n)
    except Exception:
        logger.debug("travel _bounty_count_by_continent failed", exc_info=True)
    return out


async def list_travel_destinations(session, player, *, lang: str = "pt") -> dict[str, Any]:
    """The Travel map: every continent with its IDENTITY (name/specialty/native
    tags — Lei §1 disclosure) + live presence (players + NPCs + open bounties) +
    the cost + per-destination eligibility (so the surface can disable + explain
    each locked destination). Defensive — never raises."""
    current = player.current_continent if is_valid_continent(player.current_continent) else DEFAULT_SPAWN_CONTINENT
    presence = await _presence_by_continent(session, player.telegram_id)
    npc_counts = await _npc_count_by_continent(session)
    bounty_counts = await _bounty_count_by_continent(session)
    demonic_ok = await _is_demonic_eligible(session, player.telegram_id)
    cost = travel_cost(player)
    cd = travel_cooldown_remaining(player)
    stones = int(player.spirit_stones or 0)

    # MV-2 — estrada fechada: destinos (ou a origem) sob Maré ignorada custam
    # +50% e ganham a flag de disclosure `event_penalty` (Lei §1). Flag OFF →
    # set vazio, custos de hoje, NENHUMA key nova (byte-idêntico).
    # MV-3 — com `estados_regionais` ON o set vem do ESTADO (sitiada); ver
    # road_penalized_continents (uma verdade, fallback derivado do MV-2).
    penalized: set[str] = set()
    pen_mult = 1.0
    try:
        from core.region_state_engine import road_penalized_continents
        from core.tiandao_engine import TRAVEL_PENALTY_MULT
        penalized = await road_penalized_continents(session)
        pen_mult = float(TRAVEL_PENALTY_MULT)
    except Exception:
        logger.debug("tiandao penalty lookup failed (travel map)", exc_info=True)
        penalized = set()

    # MV-3 — Estados Regionais: a linha de estado por continente no mapa de
    # viagem ("🏚️ Sitiada — estradas caras, mercados nervosos"). Flag OFF →
    # {} sem query → NENHUMA key nova no payload (byte-idêntico).
    state_by_cont: dict[str, dict[str, Any]] = {}
    try:
        from core.region_state_engine import state_views
        state_by_cont = await state_views(session, lang)
    except Exception:
        logger.debug("region state lookup failed (travel map)", exc_info=True)
        state_by_cont = {}

    # MV-6 — Reputação regional: o chip de rep por destino ("como o lugar te
    # recebe"). Flag OFF → {} sem query → NENHUMA key nova (byte-idêntico).
    rep_by_cont: dict[str, dict[str, Any]] = {}
    try:
        from core.reputation_engine import rep_chip_map
        rep_by_cont = await rep_chip_map(session, player, lang)
    except Exception:
        logger.debug("region rep lookup failed (travel map)", exc_info=True)
        rep_by_cont = {}

    # MV-8 — "há quem te procure em X": o disclosure ANTES (Lei §1), no mesmo
    # idioma dos chips event_penalty/region_state/region_rep que já vivem aqui.
    # UMA verdade: é a MESMA marca `jh_hunt` que a emboscada lê. Flag OFF → {}
    # sem query → NENHUMA key nova (byte-idêntico).
    hunted_by_cont: dict[str, int] = {}
    try:
        from core.jianghu_engine import hunters_by_continent
        hunted_by_cont = await hunters_by_continent(session)
    except Exception:
        logger.debug("jianghu hunters lookup failed (travel map)", exc_info=True)
        hunted_by_cont = {}

    # MV-9 — A CIDADE de cada destino: o NOME (sempre) + o que ela QUER (sujeito
    # à latência de leitura — quem está longe vê o pedido de 6-12h atrás, com a
    # idade dita na linha). É o que torna a chegada legível ANTES de pagar a
    # estrada. Flag OFF → {} sem query → NENHUMA key nova (byte-idêntico).
    city_by_cont: dict[str, dict[str, Any]] = {}
    try:
        from core.city_engine import city_map_overlay
        city_by_cont = await city_map_overlay(session, lang, current)
    except Exception:
        logger.debug("city overlay lookup failed (travel map)", exc_info=True)
        city_by_cont = {}

    dests: list[dict[str, Any]] = []
    for key in CONTINENT_KEYS:
        ident = project_continent_identity(key, lang)
        is_current = (key == current)
        has_penalty = bool(penalized and (key in penalized or current in penalized))
        dcost = int(cost * pen_mult) if has_penalty else cost
        eligible = True
        reason: str | None = None
        if is_current:
            eligible, reason = False, "already_here"
        elif ident["demonic_only"] and not demonic_ok:
            eligible, reason = False, "locked_demonic"
        elif cd > 0:
            eligible, reason = False, "on_cooldown"
        elif stones < dcost:
            eligible, reason = False, "not_enough_stones"
        _rst = state_by_cont.get(key)
        dests.append({
            **ident,
            "is_current": is_current,
            "presence": presence.get(key, 0),
            "npc_count": npc_counts.get(key, 0),
            "bounty_count": bounty_counts.get(key, 0),
            "cost": dcost,
            "eligible": eligible,
            "reason": reason,
            **({"event_penalty": True} if has_penalty else {}),
            **({"region_state": _rst["state"], "region_state_emoji": _rst["emoji"],
                "region_state_line": _rst["line"]} if _rst else {}),
            **({"region_rep": rep_by_cont[key]["rep"],
                "region_rep_line": rep_by_cont[key]["line"]}
               if rep_by_cont.get(key) else {}),
            **({"hunted": int(hunted_by_cont[key])} if hunted_by_cont.get(key) else {}),
            **({"region_state_occupant": _rst["occupant"]["line"]}
               if _rst and _rst.get("occupant") else {}),
            # MV-9 — as duas linhas por destino: 🏙️ a cidade e 📜 o que ela quer.
            **(city_by_cont[key] if city_by_cont.get(key) else {}),
        })

    return {
        "current": current,
        "cost": cost,
        "cooldown_remaining_ms": cd * 1000,
        "cooldown_full_ms": int(TRAVEL_COOLDOWN_HOURS * 3600 * 1000),
        "spirit_stones": stones,
        "destinations": dests,
    }
