"""v15.2 — Intent System (Sword / Fist / Body / Dao / Killing).

The 5 canonical Wuxia "yì" (意, intent) paths. Each cultivator levels up
each intent independently as they fight with techniques that share that
intent's affinity. A rank 0..9 curve gates the matchup bonus magnitude.

Matchup matrix (rock-paper-scissors with cross-edges):

    Sword > Body > Fist > Sword    (classical physical loop)
    Dao   > Killing                (spirit over the assassin's intent)
    Killing > Sword                (the assassin strikes before the blade)
    Killing > Body                 (precision finds the gap in armor)

Damage modulation (applied inside duel_engine._compute_one_side_damage
AFTER damage_mult / damage_reduce but BEFORE the final clamp):

    counter active   → +(my_rank   × 5 %) damage, capped at +50 %
    counter passive  → -(opp_rank  × 3 %) damage taken, capped at -30 %

Both effects can stack (you can counter and be countered on the same
swing — e.g. Sword used offensively against Body while the defender
swings Killing back). The duel-engine resolves them on each side
independently.

XP curve (rank N → N+1):  base 100, multiplier ×1.6 per rank.
    Rank  0 →  1 :   100 xp     Rank  5 →  6 : 1049 xp
    Rank  1 →  2 :   160 xp     Rank  6 →  7 : 1678 xp
    Rank  2 →  3 :   256 xp     Rank  7 →  8 : 2685 xp
    Rank  3 →  4 :   410 xp     Rank  8 →  9 : 4295 xp
    Rank  4 →  5 :   655 xp     Rank  9      : MAX

XP gain per duel:
    winner: +25 in dominant intent (most-used affinity in action_log)
    loser : +5  consolation (Lei §1 — never softlocked)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database.models import PlayerIntent

logger = logging.getLogger(__name__)


# ── Canonical keys + display metadata ─────────────────────────────────────────

INTENT_KEYS: tuple[str, ...] = ("sword", "fist", "body", "dao", "killing")

INTENT_META: dict[str, dict] = {
    "sword":   {"emoji": "🗡️", "color": "#9fd8ff"},
    "fist":    {"emoji": "👊", "color": "#ffb169"},
    "body":    {"emoji": "🛡️", "color": "#b6d680"},
    "dao":     {"emoji": "🌀", "color": "#c997ff"},
    "killing": {"emoji": "🥷", "color": "#ff7a8a"},
}

# Wuxia-canonical rank names per intent (mirrors techniques_expanded.md).
# Index 0 = None (untrained — frontend renders via i18n key `intent_rank_untrained`).
# Ranks 1..9 are language-neutral Wuxia romanization (kept verbatim across locales,
# same convention as "Dao", "Qi", "Heaven" — these are proper nouns of the genre).
INTENT_RANK_NAMES: dict[str, tuple[str | None, ...]] = {
    "sword": (
        None, "Sword Light", "Sword Qi", "Sword Heart",
        "Sword Will", "Sword Domain", "Myriad Swords",
        "One Sword", "Sword Dao", "Heaven Splitting",
    ),
    "fist": (
        None, "Iron Fist", "Gale Fist", "Thunder Fist",
        "Mountain Fist", "Dragon Fist", "World Fist",
        "Void Fist", "Dao Fist", "Creation Fist",
    ),
    "body": (
        None, "Iron Skin", "Stone Body", "Diamond Body",
        "Phoenix Body", "Dragon Body", "Immortal Body",
        "Primordial Body", "Void Body", "Eternal Body",
    ),
    "dao": (
        None, "Dao Sensing", "Dao Echo", "Dao Whisper",
        "Dao Sight", "Dao Resonance", "Dao Communion",
        "Dao Embodiment", "Dao Sovereignty", "Dao Ancestor",
    ),
    "killing": (
        None, "Shadow Step", "Silent Edge", "Killing Aura",
        "Death Mark", "Soul Reaper", "Heaven Slayer",
        "Karma Eraser", "One Blade", "Demon of the Void",
    ),
}


# ── Rank curve ────────────────────────────────────────────────────────────────

RANK_BASE_XP = 100
RANK_CURVE_MULT = 1.6
MAX_RANK = 9


def xp_for_rank(rank: int) -> int:
    """XP required to ADVANCE from `rank` to `rank+1`.

    Returns 0 for MAX_RANK (no further progression).
    """
    if rank >= MAX_RANK:
        return 0
    return int(RANK_BASE_XP * (RANK_CURVE_MULT ** rank))


# ── Matchup matrix ────────────────────────────────────────────────────────────

# Each intent maps to the set of intents it COUNTERS (forte vs).
# Read as: "if my attacker_intent is X and opponent's defender_intent is in
# COUNTERS[X], I get +(my_rank × 5%) damage; the opponent reads the inverse
# (countered by) and takes the −(my_rank × 3%) penalty in their own swing."
COUNTERS: dict[str, frozenset[str]] = {
    "sword":   frozenset({"body"}),
    "fist":    frozenset({"sword"}),
    "body":    frozenset({"fist"}),
    "dao":     frozenset({"killing"}),
    "killing": frozenset({"sword", "body", "dao"}),  # killing trumps blade+body, but dao trumps killing
}
# Inverted lookup for "is X countered by Y?".
COUNTERED_BY: dict[str, frozenset[str]] = {
    k: frozenset(opp for opp, victims in COUNTERS.items() if k in victims)
    for k in INTENT_KEYS
}

ACTIVE_BONUS_PCT_PER_RANK = 0.05    # +5% per rank
ACTIVE_BONUS_MAX = 0.50             # +50% cap
PASSIVE_PENALTY_PCT_PER_RANK = 0.03 # -3% per opp rank
PASSIVE_PENALTY_MAX = 0.30          # -30% cap

# v15.2b — Passive rank bonus (applied regardless of matchup).
# Each rank stacks a flat passive buff on EVERY tech of the same intent.
# Sword/Fist/Killing favour offense (+2% damage / rank); Body favours defense
# (+1.5% damage_reduce / rank); Dao favours penetration (+1.5% armor_ignore /
# rank). Killing also stacks a small evasion (+1%/rank) reflecting the
# "vanish before the blow" lore. All values per the v15.2b spec.
PASSIVE_BONUS_PER_RANK: dict[str, dict[str, float]] = {
    "sword":   {"damage_mult": 0.02},
    "fist":    {"damage_mult": 0.02},
    "killing": {"damage_mult": 0.02, "evasion": 0.01},
    "body":    {"damage_reduce": 0.015},
    "dao":     {"armor_ignore": 0.015},
}


# ── Effective rank (realm cap, lore: "alma > corpo") ─────────────────────────


def get_effective_rank(true_rank: int, realm: int) -> int:
    """Realm cap for the post-reborn flow.

    The true_rank persists across prestige (Intent is soul-mastery). But a
    Realm 0 (Mortal) player who reborn'd with Sword R9 should NOT swing
    Sword Dao damage — the body cannot channel what the soul knows yet.

    Formula: `effective = min(true_rank, max(realm + 1, 3))`

    Examples:
      Realm 0 / true R9  → effective R3
      Realm 2 / true R5  → effective R3
      Realm 5 / true R7  → effective R6
      Realm 9 / true R9  → effective R9  (no cap)
    """
    cap = max(int(realm) + 1, 3)
    return min(int(true_rank), cap)


def get_passive_bonus(intent: str | None, effective_rank: int) -> dict[str, float]:
    """Total passive bonus for `effective_rank` ranks of `intent`.

    Returns a dict mapping bonus type (damage_mult/damage_reduce/
    armor_ignore/evasion) to its accumulated value. Empty dict for None
    or rank 0.
    """
    if not intent or effective_rank <= 0:
        return {}
    per = PASSIVE_BONUS_PER_RANK.get(intent) or {}
    return {key: round(val * int(effective_rank), 4) for key, val in per.items()}


async def snapshot_intent_ranks(session, player) -> dict[str, int]:
    """Return {intent: effective_rank} for a player (realm-capped).

    Shared by duel_engine._build_duel_fighter and combat_engine simulate_combat
    callers so the Intent passive aura applies in PvE farm (chat spar/hunt,
    dungeon trash), not only in formal turn-based duels (D3, v16.6). Returns
    rank 0 for untrained intents. Best-effort: returns {} on error.
    """
    try:
        rows = (await session.execute(
            select(PlayerIntent).where(PlayerIntent.player_id == player.telegram_id)
        )).scalars().all()
        true_ranks = {r.intent: int(r.rank) for r in rows if r.intent in INTENT_KEYS}
        realm = int(getattr(player, "realm", 0) or 0)
        return {k: get_effective_rank(true_ranks.get(k, 0), realm) for k in INTENT_KEYS}
    except Exception:
        logger.exception("snapshot_intent_ranks failed player=%s", getattr(player, "telegram_id", "?"))
        return {}


def calculate_intent_modifier(
    attacker_intent: str | None,
    attacker_rank: int,
    defender_intent: str | None,
    defender_rank: int,
) -> dict:
    """Compute the additive multiplier delta for this exchange.

    Returns a dict shaped for action_log persistence:
        {
            "attacker_intent": str | None,
            "defender_intent": str | None,
            "active_bonus": float,    # +x.xx (counter active)
            "passive_penalty": float, # -x.xx (counter passive)
            "modifier": float,        # final multiplier: 1 + active - passive
            "matchup": str,           # "counter" | "countered" | "neutral" | "n/a"
        }

    The duel engine multiplies the net damage by `modifier`.
    """
    out = {
        "attacker_intent": attacker_intent,
        "defender_intent": defender_intent,
        "active_bonus": 0.0,
        "passive_penalty": 0.0,
        "modifier": 1.0,
        "matchup": "n/a",
    }
    if not attacker_intent:
        return out
    if not defender_intent:
        out["matchup"] = "neutral"
        return out

    active = 0.0
    passive = 0.0
    matchup = "neutral"

    if defender_intent in COUNTERS.get(attacker_intent, frozenset()):
        active = min(ACTIVE_BONUS_MAX, max(0, attacker_rank) * ACTIVE_BONUS_PCT_PER_RANK)
        matchup = "counter"

    if attacker_intent in COUNTERS.get(defender_intent, frozenset()):
        passive = min(PASSIVE_PENALTY_MAX, max(0, defender_rank) * PASSIVE_PENALTY_PCT_PER_RANK)
        # If both fire (mutual counter), prefer "counter" — the active edge
        # is what the player feels narratively.
        if matchup == "neutral":
            matchup = "countered"

    out["active_bonus"] = round(active, 4)
    out["passive_penalty"] = round(passive, 4)
    out["modifier"] = round(1.0 + active - passive, 4)
    out["matchup"] = matchup
    return out


# ── XP award + rank-up ────────────────────────────────────────────────────────


# v15.2b — XP per technique activation in the duel action_log, on top of
# the post-duel win/loss bonus on the dominant intent. Encourages real
# specialization (using Sword 5x in a duel feeds Sword Intent directly).
XP_PER_TECH_USE = 3
WIN_INTENT_XP = 15      # bonus to dominant intent
LOSS_INTENT_XP = 3      # consolation to dominant intent (Lei §1)


def dominant_intent_from_log(
    action_log: Iterable[dict],
    side_key: str,
    technique_intent_map: dict[int, str | None],
) -> str | None:
    """Scan the duel action_log to determine which intent the side used most.

    `technique_intent_map` maps technique_id → intent_affinity (from the
    snapshot in fighter_a/fighter_b.techniques). Returns the most-used
    intent, or None if the side never used a tech with an affinity.
    """
    counts: dict[str, int] = {}
    for entry in action_log or []:
        if not isinstance(entry, dict):
            continue
        side = entry.get(side_key)
        if not isinstance(side, dict):
            continue
        tech = side.get("tech")
        if not isinstance(tech, dict):
            continue
        tid = tech.get("id")
        if not tid:
            continue
        intent = technique_intent_map.get(int(tid))
        if not intent:
            continue
        counts[intent] = counts.get(intent, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


async def award_intent_xp(
    session,
    player_id: int,
    intent: str | None,
    xp_amount: int,
) -> dict | None:
    """Grant `xp_amount` to `player_id` in `intent`, advancing rank if curve met.

    Idempotent-safe within a transaction: uses an UPSERT (ON CONFLICT DO
    UPDATE) so concurrent settlers can't collide on the (player_id, intent)
    PK. Returns the post-state {intent, rank, xp, leveled_up, prev_rank}
    or None if no XP was awarded (intent is None or xp_amount<=0).

    SAVEPOINT (lesson from hf3): caller should wrap in `async with
    session.begin_nested():` if other writes in the same transaction need
    to survive an Integrity exception here. The standard settle helpers
    already do that via a try/except around the whole settle path.
    """
    if not intent or xp_amount <= 0 or intent not in INTENT_KEYS:
        return None

    # Try upsert with +xp; on conflict, increment.
    stmt = pg_insert(PlayerIntent).values(
        player_id=player_id,
        intent=intent,
        rank=0,
        xp=int(xp_amount),
        updated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["player_id", "intent"],
        set_={
            "xp": PlayerIntent.xp + int(xp_amount),
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await session.execute(stmt)

    # Re-fetch + walk rank-up curve. Multi-level-ups are possible if the
    # award is huge (won't happen with +25 in practice, but defensive).
    row = (await session.execute(
        select(PlayerIntent).where(
            PlayerIntent.player_id == player_id,
            PlayerIntent.intent == intent,
        )
    )).scalar_one_or_none()
    if row is None:
        return None

    prev_rank = int(row.rank or 0)
    leveled = False
    while row.rank < MAX_RANK:
        need = xp_for_rank(int(row.rank))
        if need and row.xp >= need:
            row.xp = int(row.xp) - need
            row.rank = int(row.rank) + 1
            leveled = True
        else:
            break

    return {
        "intent": intent,
        "rank": int(row.rank),
        "xp": int(row.xp),
        "leveled_up": leveled,
        "prev_rank": prev_rank,
    }


# ── Status read API (used by webserver + UI) ─────────────────────────────────


async def get_player_intents(session, player_id: int, realm: int = 0) -> list[dict]:
    """Return the 5-intent status block for a player.

    Includes intents the player has never trained — represented as rank 0
    with xp 0, so the UI always shows all 5 paths (Lei §1: honest disclosure).

    Each entry exposes both `true_rank` (the persistent soul-mastery value
    that survives prestige) and `effective_rank` (after realm cap, the value
    actually used in combat). Also includes the `passive_bonus` block keyed
    by effect_type so the UI can render "+6% damage" type chips directly.
    """
    rows = (await session.execute(
        select(PlayerIntent).where(PlayerIntent.player_id == player_id)
    )).scalars().all()
    by_key: dict[str, PlayerIntent] = {r.intent: r for r in rows if r.intent in INTENT_KEYS}

    realm_cap = max(int(realm) + 1, 3)

    out: list[dict] = []
    for key in INTENT_KEYS:
        row = by_key.get(key)
        true_rank = int(row.rank) if row else 0
        xp = int(row.xp) if row else 0
        eff_rank = get_effective_rank(true_rank, realm)
        passive = get_passive_bonus(key, eff_rank)
        # Also surface the NEXT-rank passive so the UI can render
        # "next: +8% damage" cleanly.
        next_passive = get_passive_bonus(key, eff_rank + 1) if true_rank < MAX_RANK else {}
        out.append({
            "intent": key,
            "emoji": INTENT_META[key]["emoji"],
            "color": INTENT_META[key]["color"],
            "rank": true_rank,                # legacy alias for backwards compat
            "true_rank": true_rank,
            "effective_rank": eff_rank,
            "realm_cap": realm_cap,
            "capped": eff_rank < true_rank,
            "rank_name": rank_display_name(key, true_rank),
            "next_rank_name": rank_display_name(key, true_rank + 1) if true_rank < MAX_RANK else None,
            "xp": xp,
            "xp_curve": xp_for_rank(true_rank),
            "passive_bonus": passive,         # {damage_mult: 0.06, ...}
            "next_passive_bonus": next_passive,
            "vs_strong": [opp for opp in COUNTERS.get(key, frozenset())],
            "vs_weak": [opp for opp in COUNTERED_BY.get(key, frozenset())],
        })
    return out


def rank_display_name(intent: str, rank: int) -> str | None:
    """Return the canonical Wuxia rank name for ranks >= 1, None for rank 0.

    Frontend renders rank 0 via the localized i18n key `intent_rank_untrained`
    (Início / Untrained / Inexperto). Ranks 1..9 use the canon name (e.g.
    'Sword Heart') which is intentionally NOT translated — Wuxia proper noun.
    """
    names = INTENT_RANK_NAMES.get(intent)
    if not names:
        return None
    idx = max(0, min(rank, len(names) - 1))
    return names[idx]  # None for idx=0, canon name otherwise


# ── High-level settle helper (called from arena/pvp/pve _duel_settle) ────────


def _build_tech_intent_map(fighter: dict) -> dict[int, str | None]:
    """Pack the {technique_id → intent_affinity} map from a fighter snapshot."""
    out: dict[int, str | None] = {}
    for t in (fighter or {}).get("techniques", []) or []:
        try:
            out[int(t["id"])] = t.get("intent_affinity")
        except (KeyError, ValueError, TypeError):
            continue
    return out


def _count_intent_uses(
    action_log: list,
    side_key: str,
    technique_intent_map: dict[int, str | None],
) -> dict[str, int]:
    """Count technique activations per intent for one side of the duel.

    Returns {"sword": 3, "body": 1, ...} — used both to award per-use XP
    AND to derive the dominant intent (max value).
    """
    counts: dict[str, int] = {}
    for entry in action_log or []:
        if not isinstance(entry, dict):
            continue
        side = entry.get(side_key)
        if not isinstance(side, dict):
            continue
        tech = side.get("tech")
        if not isinstance(tech, dict):
            continue
        tid = tech.get("id")
        if not tid:
            continue
        intent = technique_intent_map.get(int(tid))
        if not intent:
            continue
        counts[intent] = counts.get(intent, 0) + 1
    return counts


async def award_post_duel_intent_xp(
    session,
    duel,
    winner_id: int | None,
) -> dict | None:
    """Grant per-use XP + win/loss bonus on the dominant intent.

    XP rules (v15.2b):
      - Each tech activation in the action_log with an `intent_affinity`
        grants XP_PER_TECH_USE to that intent.
      - The dominant intent (most-used) ALSO receives a win/loss bonus
        (WIN_INTENT_XP on victory, LOSS_INTENT_XP on defeat).
      - PvE NPC side has no Player row → skipped (defender_id IS NULL).

    Each upsert wraps in a SAVEPOINT (lesson hf3 — the (player_id, intent)
    PK could conflict under concurrent settle paths, and an IntegrityError
    must not poison the outer settle transaction).

    Returns {a: {dominant, per_use, results: [{intent, rank, xp, leveled_up}]},
              b: {...}} or None for cancelled/declined.
    """
    if winner_id is None:
        return None  # no winner = cancelled/declined; no XP at all

    fa = duel.fighter_a or {}
    fb = duel.fighter_b or {}
    intent_map_a = _build_tech_intent_map(fa)
    intent_map_b = _build_tech_intent_map(fb)
    action_log = duel.action_log or []

    uses_a = _count_intent_uses(action_log, "a", intent_map_a)
    uses_b = _count_intent_uses(action_log, "b", intent_map_b)

    dom_a = max(uses_a.items(), key=lambda kv: kv[1])[0] if uses_a else None
    dom_b = max(uses_b.items(), key=lambda kv: kv[1])[0] if uses_b else None

    result: dict[str, dict | None] = {"a": None, "b": None}

    async def _award_side(player_id: int, uses: dict, dominant: str | None, won: bool) -> dict:
        side_results: list[dict] = []
        # Per-use XP for every intent the side activated.
        for intent_key, count in uses.items():
            xp = int(count) * XP_PER_TECH_USE
            if xp <= 0:
                continue
            try:
                async with session.begin_nested():
                    r = await award_intent_xp(session, player_id, intent_key, xp)
                if r:
                    side_results.append(r)
            except Exception:
                logger.exception(
                    "intent per-use XP failed duel=%s player=%s intent=%s",
                    duel.id, player_id, intent_key,
                )
        # Win/loss bonus on the dominant intent.
        if dominant:
            bonus = WIN_INTENT_XP if won else LOSS_INTENT_XP
            try:
                async with session.begin_nested():
                    r = await award_intent_xp(session, player_id, dominant, bonus)
                if r:
                    # Merge bonus into the per-use result for the dominant
                    # intent so the caller sees the FINAL rank/xp once.
                    side_results = [x for x in side_results if x["intent"] != dominant]
                    side_results.append(r)
            except Exception:
                logger.exception(
                    "intent bonus XP failed duel=%s player=%s intent=%s",
                    duel.id, player_id, dominant,
                )
        return {"dominant": dominant, "per_use": uses, "results": side_results}

    # 道 07/10 — O CAMINHO QUE SOBE TEM DE SE VER (report do [jogador]: *"setting
    # default attack for PvE arena, does not increase relevant path
    # experience"*). Medido (`tools/db_readonly_golpe_caminho_1007.py`): SUBIA —
    # o golpe padrão dispara, fica no registo e os 8 duelos de arena dele foram
    # liquidados, +18 por duelo (3 por golpe que acerta + 15 de vitória ao
    # caminho dominante) —, mas NENHUM ecrã o dizia: este resultado era deitado
    # fora pelos três settles. A lei da casa: subida sem número = nada.
    #
    # Com a onda, o ganho do jogador (antes→depois, lido na MESMA transacção)
    # fica no `pve_context` do duelo e o `combat/duel_state` mostra-o. NÃO no
    # `action_log`: o settle da arena copia o registo para o `combat_log`, e o
    # histórico dos Caminhos lê a ÚLTIMA entrada dele — um marcador ali partia
    # o histórico. Só PvE (o `pve_context` de um PvP é nulo, e o PvP de arena
    # está a 0 em 30 dias); sem a onda, nem a leitura a mais.
    _ver_a = False
    try:
        from core.portas import onda_on as _onda_on
        _ver_a = bool(duel.pve_source) and bool(_onda_on())
    except Exception:
        _ver_a = False
    _antes_a = await _ler_caminhos(session, duel.attacker_id) if _ver_a else None

    # Side A — always a real player.
    result["a"] = await _award_side(
        duel.attacker_id, uses_a, dom_a,
        won=(winner_id == duel.attacker_id),
    )

    # Side B — only if a real player (PvE has defender_id NULL).
    if duel.defender_id is not None:
        result["b"] = await _award_side(
            duel.defender_id, uses_b, dom_b,
            won=(winner_id == duel.defender_id),
        )

    if _antes_a is not None and result.get("a"):
        _ganho = caminho_ganho(_antes_a, uses_a, dom_a, winner_id == duel.attacker_id, result["a"])
        if _ganho:
            try:
                from sqlalchemy.orm.attributes import flag_modified as _fm
                _ctx = dict(duel.pve_context or {})
                _ctx["caminho_ganho"] = _ganho
                duel.pve_context = _ctx
                _fm(duel, "pve_context")
            except Exception:
                logger.exception("caminho_ganho stash failed duel=%s", duel.id)

    return result


async def _ler_caminhos(session, player_id: int) -> dict[str, dict]:
    """{intent: {rank, xp}} do jogador ANTES do ganho — colunas, sem trinco (a
    própria escrita é um UPSERT atómico; o "antes" é só para o recibo)."""
    rows = (await session.execute(
        select(PlayerIntent.intent, PlayerIntent.rank, PlayerIntent.xp)
        .where(PlayerIntent.player_id == player_id)
    )).all()
    return {r[0]: {"rank": int(r[1] or 0), "xp": int(r[2] or 0)} for r in rows if r[0] in INTENT_KEYS}


def caminho_ganho(antes: dict, uses: dict, dominant: str | None, won: bool,
                  side_result: dict) -> list[dict]:
    """O recibo dos caminhos de UM lado: para cada caminho que recebeu XP, quanto
    (`xp`), o antes e o depois (`rank`, `xp` e a `curva` do posto — o
    denominador do servidor) e se o posto subiu. O dominante primeiro."""
    depois = {r["intent"]: r for r in (side_result or {}).get("results") or [] if r}
    ordem = ([dominant] if dominant else []) + sorted(k for k in (uses or {}) if k != dominant)
    out: list[dict] = []
    for intent in ordem:
        d = depois.get(intent)
        if not d:
            continue
        a = (antes or {}).get(intent) or {"rank": 0, "xp": 0}
        xp = int((uses or {}).get(intent, 0)) * XP_PER_TECH_USE
        if intent == dominant:
            xp += WIN_INTENT_XP if won else LOSS_INTENT_XP
        out.append({
            "intent": intent,
            "xp": int(xp),
            "antes": {"rank": int(a["rank"]), "xp": int(a["xp"]), "curva": int(xp_for_rank(int(a["rank"])))},
            "depois": {"rank": int(d["rank"]), "xp": int(d["xp"]), "curva": int(xp_for_rank(int(d["rank"])))},
            "subiu": int(d["rank"]) > int(a["rank"]),
        })
    return out


# ── Intent history (read API for the panel "📜 Histórico") ──────────────────


async def get_player_intent_history(session, player_id: int, limit: int = 10) -> list[dict]:
    """Scan the last N CombatLog rows where the player participated and
    derive the intent matchup of the decisive round.

    The action_log on DuelSession is gone after the row is GC'd, but
    CombatLog.rounds_data persists `{rounds: [...]}` which carries the
    `intent` payload on every round. We pick the LAST round (the killing
    swing) — that's the matchup the UI cares about narratively.
    """
    from database.models import CombatLog
    from sqlalchemy import or_, desc

    rows = (await session.execute(
        select(CombatLog)
        .where(
            or_(
                CombatLog.attacker_id == player_id,
                CombatLog.defender_id == player_id,
            )
        )
        .order_by(desc(CombatLog.created_at))
        .limit(int(limit))
    )).scalars().all()

    out: list[dict] = []
    for log in rows:
        rounds = (log.rounds_data or {}).get("rounds") or []
        if not rounds:
            continue
        last = rounds[-1]
        if not isinstance(last, dict):
            continue
        is_a = (log.attacker_id == player_id)
        my_side = last.get("a") if is_a else last.get("b")
        opp_side = last.get("b") if is_a else last.get("a")
        my_intent = ((my_side or {}).get("intent") or {})
        opp_intent = ((opp_side or {}).get("intent") or {})
        won = (log.winner_id == player_id)
        out.append({
            "log_id": str(log.id),  # CombatLog.id is a UUID — stringify for JSON
            "mode": log.mode,
            "won": won,
            "my_intent": my_intent.get("attacker_intent"),
            "opp_intent": my_intent.get("defender_intent") or opp_intent.get("attacker_intent"),
            "modifier_pct": int(round((float(my_intent.get("modifier") or 1.0) - 1.0) * 100)),
            "matchup": my_intent.get("matchup"),
            "ts": log.created_at.isoformat() if log.created_at else None,
        })
    return out
