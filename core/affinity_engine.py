"""v16.4 — Affinity engine. The ONLY path into an NPC sect.

Affinity is a 0–100 score per (player, NPC sect) measuring how strongly the
cultivator's lived journey aligns with a house. There is no menu picker:
a sect *chooses* the cultivator (Lei §2 — Wuxia, not WoW). When affinity
crosses the threshold, the hourly recruiter scheduler spawns an encounter
(the Elder on the pine tree).

Formula (carte-blanche tuned so it is REACHABLE today; the Actions component
was wired in v16.4b so demonstrated moral choices now move recruitment):

    Path hard-gate ── mismatch ⇒ 0 (a Righteous soul cannot be courted by a
        Demonic house, and vice-versa; rogue souls are courted by Righteous
        houses only).
    Path alignment ── up to +35
        • exact tier match (righteous↔righteous, demonic↔demonic): +35
        • rogue cultivator drawn to a righteous house (partial): +20
    Continent presence ── up to +35  (this is the recruiter *spawn* signal —
        the cultivator must walk the house's mountains)
        • currently standing in the sect's native continent: +25
        • born there (home_continent): +10
    Karma–tier alignment ── up to +20
        • righteous house ← positive karma  (+1 per 25, cap +20 at ≥+500)
        • demonic house  ← negative karma   (+1 per 25, cap +20 at ≤−500)
    v16.1 lineage holdover ── +15
        • the cultivator's guild already bore this house's lineage_key
    Actions (demonstrated moral choices) ── up to +15, DIRECTED (v16.4b)
        • aggregates the cultivator's Karmic Crossroads history
          (``quest_choice_log``): every righteous fork (karma_delta > 0) and
          every demonic fork (karma_delta < 0) accumulates a signed signal.
        • righteous_sum = Σ karma_delta  (choices where karma_delta > 0)
          demonic_sum   = Σ −karma_delta (choices where karma_delta < 0)
        • actions_righteous = min(15, righteous_sum // 20)  (+1 per 20)
          actions_demonic   = min(15, demonic_sum   // 20)
        • a RIGHTEOUS house adds actions_righteous; a DEMONIC house adds
          actions_demonic — so the cultivator's *deeds* steer WHO courts them.
        Distinct from the Karma-tier term: that reads the ambient karma total
        (who you are now); Actions reads the deliberate forks you chose (what
        you did). Both reward alignment by design (§3 of the sect spec).

A devoted, continent-present, path-aligned cultivator reaches the threshold;
a cultivator whose moral choices lean hard toward a tier is now courted by it
even before continent/karma fully line up. The breakdown is exposed verbatim
to the player (Lei §1 — they see exactly why a house is eligible).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from database.models import Player, Sect, SectMember
from core.world_sects_engine import (
    WORLD_SECT_KEYS,
    WORLD_SECT_META,
    is_demonic_sect,
)

logger = logging.getLogger(__name__)

# Threshold the recruiter requires before spawning an encounter.
AFFINITY_THRESHOLD = 75
AFFINITY_MAX = 100

# ── Actions component (v16.4b) ────────────────────────────────────────────
# Demonstrated moral choices (quest_choice_log) feed a DIRECTED ≤15 term.
ACTIONS_MAX = 15            # cap per direction (righteous / demonic)
ACTIONS_KARMA_PER_POINT = 20  # +1 Action point per 20 cumulative directed karma


def get_affinity_threshold() -> int:
    """Return the recruiter affinity threshold (75)."""
    return AFFINITY_THRESHOLD


def compute_affinity_breakdown(
    *,
    path: str | None,
    karma: int,
    current_continent: str | None,
    home_continent: str | None,
    guild_lineage_key: str | None,
    sect_key: str,
    actions_righteous: int = 0,
    actions_demonic: int = 0,
) -> dict[str, Any]:
    """Return the per-component affinity breakdown for one (player, NPC sect).

    Pure function — all inputs are scalars so it is trivially testable and has
    no DB dependency. The breakdown is the Lei §1 disclosure surface: the
    cultivator sees exactly which forces (path / continent / karma / lineage /
    deeds) make a house court them.

    ``actions_righteous`` / ``actions_demonic`` are the pre-aggregated Actions
    points (≤15 each) from :func:`compute_player_actions_signal`; only the one
    matching the house's tier is applied.

    Shape: ``{path_gate, path_alignment, continent, karma_tier, lineage,
    actions, total}``. A path hard-gate failure zeroes everything (total 0,
    ``path_gate=False``). Unknown sect_key ⇒ all-zero.
    """
    out = {
        "path_gate": False, "path_alignment": 0, "continent": 0,
        "karma_tier": 0, "lineage": 0, "actions": 0, "total": 0,
    }
    if sect_key not in WORLD_SECT_META:
        return out

    from core.path_engine import is_demonic_path, is_righteous_path, is_rogue_path

    meta = WORLD_SECT_META[sect_key]
    sect_is_demonic = is_demonic_sect(sect_key)
    path_demonic = is_demonic_path(path)
    path_righteous = is_righteous_path(path)
    path_rogue = is_rogue_path(path)

    # ── Path hard-gate ────────────────────────────────────────────────────
    if sect_is_demonic:
        if not path_demonic:
            return out  # only the fallen may enter the Abyss
    else:
        if path_demonic:
            return out  # a demonic soul is barred from righteous houses
    out["path_gate"] = True

    # ── Path alignment (≤35) ──────────────────────────────────────────────
    if sect_is_demonic and path_demonic:
        out["path_alignment"] = 35
    elif (not sect_is_demonic) and path_righteous:
        out["path_alignment"] = 35
    elif (not sect_is_demonic) and path_rogue:
        out["path_alignment"] = 20  # the unaligned wanderer, courted but not yet sworn

    # ── Continent presence (≤35) ──────────────────────────────────────────
    native = meta["continent_key"]
    cont = 0
    if current_continent and current_continent == native:
        cont += 25
    if home_continent and home_continent == native:
        cont += 10
    out["continent"] = cont

    # ── Karma–tier alignment (≤20) ────────────────────────────────────────
    try:
        k = int(karma or 0)
    except (TypeError, ValueError):
        k = 0
    if sect_is_demonic:
        out["karma_tier"] = min(20, max(0, -k) // 25)
    else:
        out["karma_tier"] = min(20, max(0, k) // 25)

    # ── v16.1 lineage holdover (+15) ──────────────────────────────────────
    if guild_lineage_key and guild_lineage_key == sect_key:
        out["lineage"] = 15

    # ── Actions (≤15, directed — v16.4b) ──────────────────────────────────
    # The cultivator's deeds steer WHO courts them: righteous forks pull
    # toward righteous houses, demonic forks toward the Abyss.
    if sect_is_demonic:
        out["actions"] = max(0, min(ACTIONS_MAX, int(actions_demonic or 0)))
    else:
        out["actions"] = max(0, min(ACTIONS_MAX, int(actions_righteous or 0)))

    out["total"] = min(AFFINITY_MAX, (
        out["path_alignment"] + out["continent"] + out["karma_tier"]
        + out["lineage"] + out["actions"]
    ))
    return out


def compute_affinity(
    *,
    path: str | None,
    karma: int,
    current_continent: str | None,
    home_continent: str | None,
    guild_lineage_key: str | None,
    sect_key: str,
    actions_righteous: int = 0,
    actions_demonic: int = 0,
) -> int:
    """Return the 0–100 affinity score for one (player, NPC sect) pair.

    Thin wrapper over :func:`compute_affinity_breakdown` (back-compat — the
    new ``actions_*`` kwargs default to 0, so old callers are unaffected).
    """
    return int(compute_affinity_breakdown(
        path=path, karma=karma,
        current_continent=current_continent, home_continent=home_continent,
        guild_lineage_key=guild_lineage_key, sect_key=sect_key,
        actions_righteous=actions_righteous, actions_demonic=actions_demonic,
    )["total"])


async def compute_player_actions_signal(session, player_id: int) -> dict[str, int]:
    """Aggregate the player's Karmic Crossroads history into Actions points.

    Reads ``quest_choice_log`` (v16.3.5) and splits the signed karma_delta of
    every moral fork into a righteous sum and a demonic sum, then converts each
    to ≤15 directed Actions affinity points (+1 per ``ACTIONS_KARMA_PER_POINT``
    cumulative karma in that direction). Append-only + all-time: matches the
    "your lived deeds" framing and survives prestige (the log is the record).

    Defensive: any failure yields an all-zero signal so the recruiter / the
    directory never crash. Returns
    ``{righteous, demonic, righteous_sum, demonic_sum, choices}``.
    """
    out = {"righteous": 0, "demonic": 0, "righteous_sum": 0, "demonic_sum": 0, "choices": 0}
    try:
        from sqlalchemy import func, case
        from database.models import QuestChoiceLog, QuestCatalog
        row = (await session.execute(
            select(
                func.coalesce(func.sum(case(
                    (QuestChoiceLog.karma_delta > 0, QuestChoiceLog.karma_delta), else_=0)), 0),
                func.coalesce(func.sum(case(
                    (QuestChoiceLog.karma_delta < 0, -QuestChoiceLog.karma_delta), else_=0)), 0),
                func.count(),
            ).where(
                QuestChoiceLog.player_id == player_id,
                # v16.4c — recruitment Actions = deeds done as a FREE cultivator.
                # Exclude sect-quest forks (member-only, materialized only after
                # joining a house) so post-join deeds never steer recruitment
                # toward a rival house. No-op for actual targets today (only
                # non-members are recruited, and they have no sect-quest logs);
                # future-proofs a sect-leave/switch feature.
                QuestChoiceLog.quest_id.notin_(
                    select(QuestCatalog.id).where(QuestCatalog.type == "sect")
                ),
            )
        )).first()
    except Exception:
        logger.debug("compute_player_actions_signal failed (player_id=%s)", player_id, exc_info=True)
        return out
    if not row:
        return out
    r_sum, d_sum, n = int(row[0] or 0), int(row[1] or 0), int(row[2] or 0)
    out["righteous_sum"] = r_sum
    out["demonic_sum"] = d_sum
    out["choices"] = n
    out["righteous"] = min(ACTIONS_MAX, r_sum // ACTIONS_KARMA_PER_POINT)
    out["demonic"] = min(ACTIONS_MAX, d_sum // ACTIONS_KARMA_PER_POINT)
    return out


async def _get_player_guild_lineage(session, player_id: int) -> str | None:
    """Return the lineage_key of the player's guild (v16.1), or None.

    A guild's lineage_key is the affinity holdover signal — it means the
    cultivator already walked beside this house once.
    """
    try:
        row = (await session.execute(
            select(Sect.lineage_key)
            .join(SectMember, SectMember.sect_id == Sect.id)
            .where(SectMember.player_id == player_id)
        )).first()
    except Exception:
        logger.debug("_get_player_guild_lineage failed for player_id=%s", player_id, exc_info=True)
        return None
    return row[0] if row else None


async def compute_all_affinity_breakdowns(session, player_id: int) -> dict[str, dict[str, Any]]:
    """Return {sect_key: breakdown} for all 9 NPC sects for a player.

    The full per-component breakdown (path / continent / karma / lineage /
    actions / total) for every house — the Lei §1 disclosure surface. The
    Actions signal is computed ONCE per player (one extra aggregate query) and
    fanned out to all 9 houses. Defensive: any failure yields an all-zero map.
    """
    empty = {
        "path_gate": False, "path_alignment": 0, "continent": 0,
        "karma_tier": 0, "lineage": 0, "actions": 0, "total": 0,
    }
    out: dict[str, dict[str, Any]] = {k: dict(empty) for k in WORLD_SECT_KEYS}
    try:
        row = (await session.execute(
            select(
                Player.path,
                Player.karma,
                Player.current_continent,
                Player.home_continent,
            ).where(Player.telegram_id == player_id)
        )).first()
    except Exception:
        logger.debug("compute_all_affinity_breakdowns player fetch failed (player_id=%s)", player_id, exc_info=True)
        return out
    if not row:
        return out

    path, karma, current_continent, home_continent = row[0], row[1], row[2], row[3]
    guild_lineage = await _get_player_guild_lineage(session, player_id)
    signal = await compute_player_actions_signal(session, player_id)
    a_right = int(signal.get("righteous", 0))
    a_dem = int(signal.get("demonic", 0))

    for key in WORLD_SECT_KEYS:
        try:
            out[key] = compute_affinity_breakdown(
                path=path,
                karma=karma or 0,
                current_continent=current_continent,
                home_continent=home_continent,
                guild_lineage_key=guild_lineage,
                sect_key=key,
                actions_righteous=a_right,
                actions_demonic=a_dem,
            )
        except Exception:
            logger.debug("compute_affinity_breakdown failed (player_id=%s, sect=%s)", player_id, key, exc_info=True)
            out[key] = dict(empty)
    return out


async def compute_all_affinities(session, player_id: int) -> dict[str, int]:
    """Return {sect_key: affinity} for all 9 NPC sects for a player.

    Defensive: any failure yields an all-zero map so callers (recruiter tick,
    directory endpoint) never crash. Derived from
    :func:`compute_all_affinity_breakdowns` (single source of truth — Actions
    is computed once per player, not 9 times).
    """
    breakdowns = await compute_all_affinity_breakdowns(session, player_id)
    return {k: int(v.get("total", 0)) for k, v in breakdowns.items()}


async def get_top_affinity_sects(session, player_id: int, n: int = 3) -> list[dict[str, Any]]:
    """Return the top-n NPC sects by affinity for a player (desc), score > 0."""
    affinities = await compute_all_affinities(session, player_id)
    ranked = sorted(
        ({"sect_id": k, "score": v} for k, v in affinities.items() if v > 0),
        key=lambda r: r["score"],
        reverse=True,
    )
    return ranked[: max(1, int(n))]


# ── Disclosure do bloqueio (fix 2026-07-28 — pergunta do jogador [jogador]) ─────
# O `get_top_affinity_sects` acima filtra `score > 0`, e o hard-gate de caminho
# ZERA a casa do outro lado. Resultado: quem não é demoníaco NUNCA via as
# Profundezas Abissais na lista do /seita — nem o nome, nem o requisito. O
# jogador teve de perguntar no grupo como entrar na seita demoníaca, porque o
# jogo escondia a existência dela.
#
# Isso é pior que um dead-end comum: a escolha de caminho é de UMA VEZ SÓ
# (`path_already_set`) e abre no Reino 3 — dá para cristalizar Justo sem
# nunca saber que se fechou a porta do Abismo para sempre. Lei §1: a recusa
# tem de DIZER o motivo e o caminho.
#
# UM helper puro para as duas superfícies (chat + mini).

BLOCK_NEEDS_DEMONIC = "needs_demonic"   # casa demoníaca, cultivador não-caído
BLOCK_BARRED_DEMONIC = "barred_demonic"  # casa justa, cultivador demoníaco


def path_block_reason(path: str | None, sect_key: str) -> str | None:
    """Por que esta casa está barrada para este caminho. None = não está.

    Espelha EXATAMENTE o hard-gate de `compute_affinity_breakdown` (mesma
    pergunta, uma verdade) — se o gate mudar, muda aqui e as duas telas
    seguem juntas.
    """
    if sect_key not in WORLD_SECT_META:
        return None
    from core.path_engine import is_demonic_path

    if is_demonic_sect(sect_key):
        return None if is_demonic_path(path) else BLOCK_NEEDS_DEMONIC
    return BLOCK_BARRED_DEMONIC if is_demonic_path(path) else None


async def get_affinity_overview(session, player_id: int, n: int = 3) -> dict[str, Any]:
    """As casas que te cortejam E as que estão barradas, com o motivo.

    ``{"eligible": [{sect_id, score}], "blocked": [{sect_id, reason}],
       "threshold": int, "path": str|None}``

    `eligible` = as top-n com score > 0 (o comportamento de sempre).
    `blocked`  = as barradas pelo hard-gate de caminho, com o motivo — o que
    faltava. Uma casa de score 0 que NÃO está barrada (só não pontuou ainda)
    fica de fora das duas listas: ela não é um segredo, é só um "ainda não".
    """
    out: dict[str, Any] = {
        "eligible": [], "blocked": [], "threshold": AFFINITY_THRESHOLD,
        "path": None,
    }
    try:
        path = (await session.execute(
            select(Player.path).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()
    except Exception:
        logger.debug("get_affinity_overview path fetch failed (player_id=%s)",
                     player_id, exc_info=True)
        path = None
    out["path"] = path

    affinities = await compute_all_affinities(session, player_id)
    out["eligible"] = sorted(
        ({"sect_id": k, "score": v} for k, v in affinities.items() if v > 0),
        key=lambda r: r["score"], reverse=True,
    )[: max(1, int(n))]

    blocked = []
    for key in WORLD_SECT_KEYS:
        reason = path_block_reason(path, key)
        if reason:
            blocked.append({"sect_id": key, "reason": reason})
    out["blocked"] = blocked
    return out
