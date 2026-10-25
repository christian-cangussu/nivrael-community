"""v15.1 — Turn-Based Duel State Machine.

Canonical engine for PvP duels with qi consumption, simultaneous round
submission, and sudden-death tiebreaker. NPC/dungeon/boss combat keeps using
`simulate_combat` in `core/combat_engine.py` — this engine is duel-only.

State flow per duel:
    create            → state='pending_acceptance', defender must accept first
    accept (defender) → state='waiting_actions', round_idx=1 (duel begins)
    decline (defender)→ state='declined' (no winner)
    cancel  (attacker)→ state='cancelled' (no winner, before accept)
    submit (A)        → pending_action_a set, state stays 'waiting_actions'
    submit (B)        → pending_action_b set, resolve_round() fires automatically
    resolve_round     → applies both actions simultaneously, appends to action_log,
                        +10% qi regen, round_idx += 1, clears pending actions
                        → if HP<=0 on either side: state='finished', winner_id set
                        → if round_idx > max_rounds and both alive: sudden_death=True
                        → if sudden_death and tiebreak fires: winner via luck+dao_heart
    forfeit (in-duel) → state='forfeited', winner_id = opponent
    expire (idle)     → state='expired' after expires_at

v15.1.3 — Stances removed. The technique itself encodes attack/defense/utility
intent now (damage_mult / damage_reduce / evasion / dodge / armor_ignore), so
the offensive/balanced/defensive picker became redundant. `simulate_combat`
(NPC/dungeon/boss) keeps STANCES for Phase 2 (v15.1.4) until those paths go
turn-based.

Engine reuse 100%: builds fighter_data via `build_fighter_data` from
combat_engine, reuses technique bonus primitives.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from config import MAX_ROUNDS, REALM_MULTIPLIERS
from core.combat_engine import (
    MASTERY_STAGES,
    apply_hp_drain,
    apply_hp_drain_scaled,
    build_fighter_data,
    get_grade_info,
)
from database.models import (
    DuelSession,
    Player,
    PlayerArtifact,
    PlayerTechnique,
    TechniqueCatalog,
)

logger = logging.getLogger(__name__)

# Combat Pool = COMBAT_POOL_PCT × qi_capacity, regen REGEN_PCT/round.
# Sudden Death after max_rounds with both alive.
COMBAT_POOL_PCT = 0.20
COMBAT_POOL_MIN = 20
REGEN_PCT_PER_ROUND = 0.10
# v15.1b — per-state timeouts. The `expires_at` column is repurposed: while
# state='pending_acceptance' it's the acceptance window (defender must accept
# in 5 min); once duel is live ('waiting_actions'), it's the per-round clock
# (15 s) after which missing submissions auto-fill with "basic strike".
ACCEPTANCE_TIMEOUT_SECONDS = 5 * 60
ROUND_TIMEOUT_SECONDS = 15
SUDDEN_DEATH_DEF_MULT = 0.50
SUDDEN_DEATH_DMG_TAKEN_MULT = 1.20
SUDDEN_DEATH_MAX_EXTRA_ROUNDS = 3  # tiebreak via luck if still alive after this


# ─── Build fighter snapshot for duel persistence ─────────────────────────────


async def _build_duel_fighter(session, player: Player) -> dict:
    """Snapshot fighter for the duel — equipment, techniques, hp, bp, armor.

    Persisted in fighter_a / fighter_b JSONB so resolve_round can run
    deterministically off the snapshot (no live player-state drift).
    """
    artifacts = (await session.execute(
        select(PlayerArtifact).where(
            PlayerArtifact.player_id == player.telegram_id,
            PlayerArtifact.is_equipped == True,  # noqa: E712
        )
    )).scalars().all()

    pts = (await session.execute(
        select(PlayerTechnique, TechniqueCatalog)
        .join(TechniqueCatalog, PlayerTechnique.technique_id == TechniqueCatalog.id)
        .where(
            PlayerTechnique.player_id == player.telegram_id,
            PlayerTechnique.is_active_combat == True,  # noqa: E712
            TechniqueCatalog.tech_type == "combat",
        )
    )).all()

    techniques = []
    for pt, cat in pts:
        techniques.append({
            "id": cat.id,
            # Alimenta o `simulate_combat`, cujos eventos vao para o
            # `combat_log.rounds_data` persistido e lido pelos DOIS lutadores.
            # Mesmo motivo, e mesma saida futura, do `core/combat_engine.py`.
            # 名-CRU: log de combate persistido, dois espectadores, sem id.
            "name": cat.name,
            "emoji": cat.emoji,
            "effect_type": cat.effect_type,
            "effect_value": float(cat.effect_value),
            "effect_round": cat.effect_round,
            "qi_cost": int(cat.qi_cost or 10),
            "mastery_level": pt.mastery_level,
            "grade": pt.grade,
            "grade_mult": get_grade_info(pt.grade)["mult"],
            # v15.2 — intent affinity snapshot. NULL for techs not yet
            # tagged in the seed (the seed runner backfills on every boot).
            "intent_affinity": getattr(cat, "intent_affinity", None),
        })

    # v16.7 Fase 1 — wire-in (combat rebalance). Até aqui o duelo construía o
    # fighter SEM dao/buff/faction/companion → as Leis, pílulas e bónus de
    # facção/companion não aplicavam em PvP/PvE turn-based (auditoria
    # v16.7_combat_audit.md). Agora passamos os mesmos bónus que o spar já usa
    # (handlers/combat.py:_build_fighter), tornando "Leis é superior" verdadeiro
    # no duelo. Cada fetch é best-effort: um erro de leitura nunca pode falhar a
    # criação do duelo (Lei §1 — jogador nunca preso).
    buff_mults = None
    comp_bonus = None
    dao_bonuses = None
    fac_bonuses = None
    try:
        from core.combat_engine import get_combat_buff_mults
        buff_mults = await get_combat_buff_mults(session, player.telegram_id)
    except Exception:
        logger.exception("duel buff_mults fetch failed player=%s", player.telegram_id)
    try:
        from core.beast_engine import get_companion_beast, get_companion_bonuses
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        comp_bonus = get_companion_bonuses(comp_beast, comp_catalog)
    except Exception:
        logger.exception("duel companion fetch failed player=%s", player.telegram_id)
    try:
        from core.dao_engine import get_player_dao_bonuses
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, player.realm)
    except Exception:
        logger.exception("duel dao_bonuses fetch failed player=%s", player.telegram_id)
    try:
        from core.faction_engine import get_faction_bonuses
        fac_bonuses = await get_faction_bonuses(session, player.telegram_id)
    except Exception:
        logger.exception("duel faction fetch failed player=%s", player.telegram_id)

    interior_b = ach_b = None
    try:
        from core.combat_engine import get_unified_combat_bonuses
        interior_b, ach_b = await get_unified_combat_bonuses(session, player.telegram_id)
    except Exception:
        logger.exception("duel unified bonuses fetch failed player=%s", player.telegram_id)
    fighter = build_fighter_data(
        player, artifacts, [], pet_ability=None,
        buff_mults=buff_mults, companion_bonus=comp_bonus,
        dao_bonuses=dao_bonuses, faction_bonuses=fac_bonuses,
        interior_bonuses=interior_b, achievement_bonuses=ach_b,
    )
    fighter["techniques"] = techniques
    fighter["telegram_id"] = player.telegram_id
    fighter["dao_name"] = player.dao_name or player.display_name or player.username or "Cultivator"

    # v15.2 — Intent ranks snapshot. Pinned at duel-create time so the
    # matchup modifier + passive bonus resolve deterministically from JSONB
    # (no live PlayerIntent read on each round). Lazy: only intents with a
    # row are loaded; others default to rank 0 in calculate_intent_modifier.
    #
    # v15.2b — Two values per intent: `true_rank` (soul mastery, persistent)
    # and `effective_rank` (after realm cap). Combat uses effective_rank;
    # UI shows both so the player sees what's available *now* vs the cap.
    try:
        from database.models import PlayerIntent
        from core.intent_engine import INTENT_KEYS, get_effective_rank
        rows = (await session.execute(
            select(PlayerIntent).where(PlayerIntent.player_id == player.telegram_id)
        )).scalars().all()
        true_ranks = {r.intent: int(r.rank) for r in rows if r.intent in INTENT_KEYS}
        realm = int(getattr(player, "realm", 0) or 0)
        # intent_ranks now holds the EFFECTIVE rank used in damage compute.
        fighter["intent_ranks"] = {
            k: get_effective_rank(true_ranks.get(k, 0), realm) for k in INTENT_KEYS
        }
        fighter["intent_true_ranks"] = {k: int(true_ranks.get(k, 0)) for k in INTENT_KEYS}
    except Exception:
        logger.exception("intent rank snapshot failed player=%s", player.telegram_id)
        fighter["intent_ranks"] = {}
        fighter["intent_true_ranks"] = {}
    return fighter


def _combat_pool_max(qi_capacity: float) -> int:
    """Combat Qi pool = max(20, qi_capacity × 0.20)."""
    return max(COMBAT_POOL_MIN, int(qi_capacity * COMBAT_POOL_PCT))


# ─── Create a new duel ───────────────────────────────────────────────────────


async def start_duel(
    session,
    attacker: Player,
    defender: Player,
    auto_accept: bool = False,
) -> DuelSession:
    """Create a new duel session between two players.

    Caller must validate that both players are eligible (not meditating, HP>0,
    not already in another active duel) before calling.

    v15.1.5 — `auto_accept=True` is used by the arena ELO matchmaker: both
    players already consented by joining the queue, so the duel skips the
    acceptance step and starts at 'waiting_actions' with a round clock.
    The challenge-bell notification is also suppressed (both sides are
    notified via the arena-match path instead).
    """
    fa = await _build_duel_fighter(session, attacker)
    fb = await _build_duel_fighter(session, defender)

    cqi_a_max = _combat_pool_max(attacker.qi_capacity)
    cqi_b_max = _combat_pool_max(defender.qi_capacity)

    state = "waiting_actions" if auto_accept else "pending_acceptance"
    expires_seconds = ROUND_TIMEOUT_SECONDS if auto_accept else ACCEPTANCE_TIMEOUT_SECONDS

    duel = DuelSession(
        attacker_id=attacker.telegram_id,
        defender_id=defender.telegram_id,
        # v15.1b — defender must accept before round 1 for direct PvP
        # challenges. Arena matches (auto_accept=True) skip straight to
        # 'waiting_actions' — both players consented via the queue.
        state=state,
        round_idx=1,
        max_rounds=MAX_ROUNDS,
        combat_qi_a=cqi_a_max,
        combat_qi_b=cqi_b_max,
        combat_qi_a_max=cqi_a_max,
        combat_qi_b_max=cqi_b_max,
        hp_a=float(fa["hp"]),
        hp_b=float(fb["hp"]),
        hp_a_max=float(fa["hp"]),
        hp_b_max=float(fb["hp"]),
        bp_a=int(fa["bp"]),
        bp_b=int(fb["bp"]),
        fighter_a=fa,
        fighter_b=fb,
        pending_action_a=None,
        pending_action_b=None,
        action_log=[{"round": 0, "type": "accepted", "accepted_by": "arena_queue"}] if auto_accept else [],
        winner_id=None,
        sudden_death=False,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_seconds),
    )
    session.add(duel)
    await session.flush()

    # v15.1.2 — fire bell notification on the defender's side so they see the
    # challenge even without polling the CombatTab/Duel seg. Persistent so it
    # survives if the defender is offline. Dedup via duel.id ref so retries
    # don't double-notify. Skipped for auto-accept (arena) — the match
    # notification is fired by the arena engine for both sides.
    if not auto_accept:
        try:
            from core.notification_engine import notify as _notify
            attacker_name = fa.get("dao_name") or fa.get("name") or "?"
            await _notify(
                session, defender.telegram_id, "duel_challenge",
                title_key="notif_duel_challenge_title",
                body_key="notif_duel_challenge_body",
                payload={"name": attacker_name},
                ref_id=str(duel.id),
                icon="⚔️",
                target_tab="combat",
                priority=1,  # urgent — toast + bell pulse
            )
        except Exception:
            logger.exception("duel_challenge notify failed for duel=%s", duel.id)

    return duel


# ─── Submit a player's action for the current round ──────────────────────────


def _side_of(duel: DuelSession, player_id: int) -> str | None:
    if player_id == duel.attacker_id:
        return "a"
    if player_id == duel.defender_id:
        return "b"
    return None


def _find_technique(fighter: dict, tech_id: int) -> dict | None:
    if not tech_id:
        return None
    for t in fighter.get("techniques", []):
        if t["id"] == tech_id:
            return t
    return None


async def submit_action(
    session,
    duel: DuelSession,
    player_id: int,
    technique_id: int,
) -> dict:
    """Record a player's action for the current round.

    Returns {ok: bool, reason?: str, both_submitted?: bool}.
    technique_id == 0 means "basic strike" (no qi cost, no technique bonus).
    If both players submit, the round resolves automatically and the new
    state is reflected in the duel row.
    """
    # Defensive: if previous round already timed out, resolve it first so the
    # incoming submit applies to the NEW round (not the stale one).
    await check_and_handle_timeout(session, duel)

    if duel.state != "waiting_actions":
        return {"ok": False, "reason": "duel_not_open"}

    side = _side_of(duel, player_id)
    if side is None:
        return {"ok": False, "reason": "not_a_participant"}

    fighter = duel.fighter_a if side == "a" else duel.fighter_b
    current_qi = duel.combat_qi_a if side == "a" else duel.combat_qi_b

    qi_cost = 0
    tech = None
    if technique_id:
        tech = _find_technique(fighter, technique_id)
        if not tech:
            return {"ok": False, "reason": "technique_not_equipped"}
        qi_cost = int(tech.get("qi_cost", 10))
        if current_qi < qi_cost:
            return {"ok": False, "reason": "not_enough_combat_qi"}
        # TEC-5 — o relógio do Caminho Proibido: com o Mar de Longevidade
        # esgotado a arte proibida RECUSA o uso, com o motivo NOMEADO e ANTES
        # da rodada (padrão not_enough_combat_qi — nunca um golpe silencioso).
        # É a ÚNICA trava pré-uso possível: o custo real é cobrado no settle e
        # nada é reembolsável depois que a rodada resolve. Arte comum ou flag
        # OFF ⇒ zero query (o gate sai no 1º `if`).
        from core.forbidden_path_engine import forbidden_use_gate
        _fp = await forbidden_use_gate(session, player_id, technique_id,
                                       duel=duel, side_key=side)
        if not _fp.get("ok"):
            return {"ok": False, "reason": _fp.get("reason", "forbidden_lifespan_spent"),
                    "age_years": _fp.get("age_years"), "ceiling": _fp.get("ceiling"),
                    "years_per_use": _fp.get("years_per_use")}

    # Idempotent overwrite — player can re-pick before opponent submits.
    action = {
        "technique_id": technique_id,
        "qi_cost": qi_cost,
    }
    if side == "a":
        duel.pending_action_a = action
        flag_modified(duel, "pending_action_a")
    else:
        duel.pending_action_b = action
        flag_modified(duel, "pending_action_b")

    # v15.1.4 — PvE auto-NPC: when the player submits and the duel is PvE,
    # immediately fill the NPC's side via `pick_npc_action` so the round
    # can resolve in a single round-trip (no polling for the AI to think).
    # Only the side='a' branch can be the player in PvE; defender_id is
    # always NULL so side='b' submissions wouldn't reach this point.
    if _is_pve(duel) and side == "a" and duel.pending_action_b is None:
        try:
            from core.npc_ai import pick_npc_action
            npc_action = pick_npc_action(
                npc_fighter=duel.fighter_b,
                npc_state=_npc_state_snapshot(duel),
                opp_state=_player_state_snapshot(duel),
                round_num=duel.round_idx,
            )
            duel.pending_action_b = {
                "technique_id": int(npc_action["technique_id"]),
                "qi_cost": int(npc_action["qi_cost"]),
                "ai_reason": npc_action.get("ai_reason"),
            }
            flag_modified(duel, "pending_action_b")
        except Exception:
            logger.exception("pick_npc_action failed duel=%s round=%s", duel.id, duel.round_idx)
            # Defensive fallback — NPC defaults to basic strike.
            duel.pending_action_b = {
                "technique_id": 0, "qi_cost": 0, "ai_reason": "exception_fallback",
            }
            flag_modified(duel, "pending_action_b")

    # Both submitted → resolve.
    if duel.pending_action_a is not None and duel.pending_action_b is not None:
        await _resolve_round(session, duel)
        return {"ok": True, "both_submitted": True}

    return {"ok": True, "both_submitted": False}


# ─── Resolve the current round ───────────────────────────────────────────────


def _tech_bonus_from_action(fighter: dict, action: dict | None, round_num: int, effect_type: str) -> float:
    """Return bonus for the selected technique if it matches effect_type and round.

    Unlike simulate_combat which scans all equipped techniques, the duel
    engine only counts the technique actively chosen this round (one action
    per round per side). Bonus = effect_value × mastery_mult × grade_mult.
    """
    if not action or not action.get("technique_id"):
        return 0.0
    tech = _find_technique(fighter, action["technique_id"])
    if not tech or tech["effect_type"] != effect_type:
        return 0.0
    target_round = tech.get("effect_round", 0)
    if target_round != 0 and target_round != round_num:
        return 0.0
    mastery_mult = MASTERY_STAGES.get(tech["mastery_level"], MASTERY_STAGES[1])["mult"]
    grade_mult = tech.get("grade_mult", 1.0)
    return float(tech["effect_value"]) * mastery_mult * grade_mult


def _compute_one_side_damage(
    attacker_fighter: dict,
    attacker_action: dict | None,
    defender_fighter: dict,
    defender_action: dict | None,
    attacker_bp: int,
    defender_bp: int,
    round_num: int,
    sudden_death: bool,
) -> dict:
    """Compute damage dealt by attacker side this round.

    Returns {damage, evaded, dodged, raw, blocked, tech_used}.
    """
    # Defender evasion / dodge — chance to fully evade incoming hit.
    evasion = _tech_bonus_from_action(defender_fighter, defender_action, round_num, "evasion")
    # v15.2b — Killing intent stacks +1%/rank evasion passively on whatever
    # the defender is swinging *if it's a Killing tech*. "Vanish before the
    # blow" lore — the killer's footwork applies even mid-strike.
    from core.intent_engine import get_passive_bonus as _gpb_ev
    _def_t = _find_technique(defender_fighter, (defender_action or {}).get("technique_id"))
    _def_i = (_def_t or {}).get("intent_affinity")
    _def_r = defender_fighter.get("intent_ranks") or {}
    _ev_pb = _gpb_ev(_def_i, int(_def_r.get(_def_i, 0))) if _def_i else {}
    evasion += float(_ev_pb.get("evasion", 0.0))
    evasion += float(defender_fighter.get("companion_evasion", 0.0) or 0.0)  # Wave 3: companion evasion_mult (gated → 0 OFF)
    evasion = min(evasion, 0.90)
    if evasion > 0 and random.random() < evasion:
        return {
            "damage": 0,
            "evaded": True,
            "dodged": False,
            "raw": 0,
            "blocked": 0,
            "tech_used": None,
        }

    dodge = _tech_bonus_from_action(defender_fighter, defender_action, round_num, "dodge")
    if dodge > 0 and random.random() < 0.5:
        return {
            "damage": 0,
            "evaded": False,
            "dodged": True,
            "raw": 0,
            "blocked": 0,
            "tech_used": None,
        }

    # Damage build — v15.1.3 stances removed; technique encodes attack vs
    # defense intent (damage_mult / damage_reduce). Base attack = full bp,
    # base defense = bp × 0.4 (mirrors simulate_combat's defender-mass).
    dmg_mult = _tech_bonus_from_action(attacker_fighter, attacker_action, round_num, "damage_mult")
    armor_ignore = _tech_bonus_from_action(attacker_fighter, attacker_action, round_num, "armor_ignore")
    dmg_reduce = _tech_bonus_from_action(defender_fighter, defender_action, round_num, "damage_reduce")

    # v15.2b — Intent passive bonus. Stacks on top of technique values based
    # on the attacker/defender's RANK in the intent of the tech they're
    # swinging this round. Always-on (no matchup gate) — this is the soul-
    # mastery aura that grows with every spar.
    from core.intent_engine import get_passive_bonus
    _atk_tech_pb = _find_technique(attacker_fighter, (attacker_action or {}).get("technique_id"))
    _atk_int = (_atk_tech_pb or {}).get("intent_affinity")
    _atk_ranks_pb = attacker_fighter.get("intent_ranks") or {}
    _atk_pb = get_passive_bonus(_atk_int, int(_atk_ranks_pb.get(_atk_int, 0))) if _atk_int else {}
    if _atk_pb:
        dmg_mult += float(_atk_pb.get("damage_mult", 0.0))
        armor_ignore += float(_atk_pb.get("armor_ignore", 0.0))

    _def_tech_pb = _find_technique(defender_fighter, (defender_action or {}).get("technique_id"))
    _def_int = (_def_tech_pb or {}).get("intent_affinity")
    _def_ranks_pb = defender_fighter.get("intent_ranks") or {}
    _def_pb = get_passive_bonus(_def_int, int(_def_ranks_pb.get(_def_int, 0))) if _def_int else {}
    if _def_pb:
        dmg_reduce += float(_def_pb.get("damage_reduce", 0.0))
        # Body cap evasion stack handled inside the evasion branch above (we
        # already checked evasion before reaching here — for v15.2b the
        # Killing evasion bonus is folded in there via the same passive map).

    # v15.2 — Intent matchup modifier (attacker offensive intent vs defender
    # defensive intent). Resolved first so it can feed the shared damage core.
    from core.intent_engine import calculate_intent_modifier
    atk_tech = _find_technique(attacker_fighter, (attacker_action or {}).get("technique_id"))
    def_tech = _find_technique(defender_fighter, (defender_action or {}).get("technique_id"))
    atk_intent = (atk_tech or {}).get("intent_affinity")
    def_intent = (def_tech or {}).get("intent_affinity")
    atk_ranks = attacker_fighter.get("intent_ranks") or {}
    def_ranks = defender_fighter.get("intent_ranks") or {}
    atk_rank = int(atk_ranks.get(atk_intent, 0)) if atk_intent else 0
    def_rank = int(def_ranks.get(def_intent, 0)) if def_intent else 0
    intent_info = calculate_intent_modifier(atk_intent, atk_rank, def_intent, def_rank)

    # v16.7 — damage via the shared Três Tesouros core (core/combat_model). The
    # technique's damage_mult / armor_ignore and the defender's damage_reduce feed
    # in as per-round overrides on top of the fighters' stat profiles:
    #   STRIKE × DAO × INTENT × PREP × CRIT, then proportional mitigation + capped
    #   Dao-penetration, then the Heavenly-Pressure ramp (round_num) + the
    #   meaningful-minimum floor (kills the "1 HP chip" — owner requirement).
    # Sudden-death is subsumed by the ramp (a high round_num ⇒ high pressure), so
    # the legacy SUDDEN_DEATH_* multipliers are no longer applied here.
    from core import combat_model as _cm
    # Fallback only for pre-deploy in-flight duels whose JSONB snapshot predates
    # combat_profile. attacker_bp/defender_bp here are duel.bp_a/bp_b = the OLD
    # display total_battle_power, which is ALREADY realm-scaled — so realm=0 (the
    # model must NOT re-multiply), mirroring combat_engine._profile_of's contract.
    atk_profile = (attacker_fighter or {}).get("combat_profile") or _cm.make_profile(
        soul=0, qi=0, bp=float(attacker_bp), realm=0)
    def_profile = (defender_fighter or {}).get("combat_profile") or _cm.make_profile(
        soul=0, qi=0, bp=float(defender_bp), realm=0)
    _hit = _cm.compute_attack(
        atk_profile, def_profile, round_num,
        intent_matchup=float(intent_info["modifier"]),
        tech_dmg=dmg_mult, tech_reduce=dmg_reduce, tech_armor_ignore=armor_ignore,
        rng=random,
    )
    net = max(1.0, _hit["net"])
    raw = _hit["raw"]

    tech_used = None
    if attacker_action and attacker_action.get("technique_id"):
        t = _find_technique(attacker_fighter, attacker_action["technique_id"])
        if t:
            tech_used = {"id": t["id"], "name": t["name"], "emoji": t["emoji"]}

    return {
        "damage": int(net),
        "evaded": False,
        "dodged": False,
        "raw": int(raw),
        "blocked": int(max(0, raw * _hit.get("reduction", 0.0))),  # v16.7: actual mitigation (raw-net reads 0 once the ramp lifts net>raw)
        "tech_used": tech_used,
        # v15.2 — intent payload surfaced in action_log for the UI chip
        # "[⚔️ Sword × 🛡️ Body → +15%]". Keys mirror calculate_intent_modifier.
        "intent": intent_info,
        # v16.7 — combat-model metadata for the legibility chips in the duel log.
        "crit": bool(_hit.get("crit")),
        "penetrated": int(_hit.get("penetrated", 0)),
        "pressure": round(float(_hit.get("pressure", 1.0)), 2),
    }


async def _resolve_round(session, duel: DuelSession) -> None:
    """Apply both pending actions simultaneously and advance round.

    Mutates duel in place. Caller must be holding the row lock.
    """
    action_a = duel.pending_action_a
    action_b = duel.pending_action_b
    round_num = duel.round_idx

    # Spend qi (both sides) before resolution so a fatal strike that runs the
    # pool dry still pays its cost.
    qi_a_spent = int((action_a or {}).get("qi_cost", 0))
    qi_b_spent = int((action_b or {}).get("qi_cost", 0))
    duel.combat_qi_a = max(0, duel.combat_qi_a - qi_a_spent)
    duel.combat_qi_b = max(0, duel.combat_qi_b - qi_b_spent)

    # Compute simultaneous damages.
    a_result = _compute_one_side_damage(
        duel.fighter_a, action_a, duel.fighter_b, action_b,
        duel.bp_a, duel.bp_b,
        round_num, duel.sudden_death,
    )
    b_result = _compute_one_side_damage(
        duel.fighter_b, action_b, duel.fighter_a, action_a,
        duel.bp_b, duel.bp_a,
        round_num, duel.sudden_death,
    )

    duel.hp_b = max(0.0, duel.hp_b - a_result["damage"])
    duel.hp_a = max(0.0, duel.hp_a - b_result["damage"])

    # v16.7 — Supreme Celestial Body regen (tier-12, now read in-duel — was
    # computed-then-dropped) + Realm-Pressure suppression chip (a higher realm
    # crushes a lower one each round). Applied AFTER damage so regen can save a
    # fighter and the chip can finish one, then logged with the post-state HP.
    from core.combat_model import realm_pressure_chip as _rp_chip
    _a_regen = float((duel.fighter_a or {}).get("celestial_hp_regen_pct", 0.0) or 0.0)
    _b_regen = float((duel.fighter_b or {}).get("celestial_hp_regen_pct", 0.0) or 0.0)
    if _a_regen and duel.hp_a > 0:
        duel.hp_a = min(duel.hp_a_max, duel.hp_a + duel.hp_a_max * _a_regen)
    if _b_regen and duel.hp_b > 0:
        duel.hp_b = min(duel.hp_b_max, duel.hp_b + duel.hp_b_max * _b_regen)
    _ra = int((duel.fighter_a or {}).get("realm", 0) or 0)
    _rb = int((duel.fighter_b or {}).get("realm", 0) or 0)
    duel.hp_a = max(0.0, duel.hp_a - _rp_chip(_rb, _ra, duel.hp_a_max))
    duel.hp_b = max(0.0, duel.hp_b - _rp_chip(_ra, _rb, duel.hp_b_max))

    # TEC-5 — o SWING proibido tem de ficar no log mesmo quando a rodada não
    # aterra: `_compute_one_side_damage` devolve `tech_used=None` quando o alvo
    # ESQUIVA ou DESVIA, e o qi já foi gasto acima. Sem esta marca o custo seguia
    # os golpes que ACERTARAM — o adversário escolhia, com a técnica dele, quanto
    # o proibido custava (achado do review adversarial). Key CONDICIONAL e só
    # para arte proibida ⇒ com a flag OFF o action_log é byte-idêntico.
    _fp_ids = ()
    try:
        from core.forbidden_path_engine import forbidden_ids as _fpi
        _fp_ids = _fpi()
    except Exception:
        logger.debug("forbidden swing tag failed duel=%s", duel.id, exc_info=True)
    _fp_a = int((action_a or {}).get("technique_id") or 0) if _fp_ids else 0
    _fp_b = int((action_b or {}).get("technique_id") or 0) if _fp_ids else 0

    # Append to action log (visible to both players via get_duel_state).
    duel.action_log = (duel.action_log or []) + [{
        "round": round_num,
        "sudden_death": duel.sudden_death,
        "a": {
            "tech": a_result["tech_used"],
            "damage": a_result["damage"],
            "evaded": a_result["evaded"],
            "dodged": a_result["dodged"],
            "blocked": a_result["blocked"],
            "qi_spent": qi_a_spent,
            # v15.2 — intent matchup metadata for UI chip + history reads.
            "intent": a_result.get("intent"),
        },
        "b": {
            "tech": b_result["tech_used"],
            "damage": b_result["damage"],
            "evaded": b_result["evaded"],
            "dodged": b_result["dodged"],
            "blocked": b_result["blocked"],
            "qi_spent": qi_b_spent,
            "intent": b_result.get("intent"),
        },
        "hp_a_after": int(duel.hp_a),
        "hp_b_after": int(duel.hp_b),
    }]
    if _fp_a in _fp_ids:
        duel.action_log[-1]["a"]["fpd"] = _fp_a
    if _fp_b in _fp_ids:
        duel.action_log[-1]["b"]["fpd"] = _fp_b
    flag_modified(duel, "action_log")

    # Clear pending actions for next round.
    duel.pending_action_a = None
    duel.pending_action_b = None

    # Check end conditions.
    a_dead = duel.hp_a <= 0
    b_dead = duel.hp_b <= 0
    if a_dead and b_dead:
        # Simultaneous KO — resolve via _apply_tiebreak (v16.7 order:
        # damage-dealt → dao_index → luck+perception; HP% demoted; no dao_heart).
        await _apply_tiebreak(session, duel)
        return
    if a_dead:
        duel.state = "finished"
        # PvE: defender_id is NULL — set winner to 0 sentinel so settle
        # can distinguish player-loss (0) from player-win (attacker.id).
        # PvP: defender_id is the real defender.
        duel.winner_id = 0 if _is_pve(duel) else duel.defender_id
        duel.resolved_at = datetime.now(timezone.utc)
        await _notify_duel_result(session, duel)
        return
    if b_dead:
        duel.state = "finished"
        duel.winner_id = duel.attacker_id
        duel.resolved_at = datetime.now(timezone.utc)
        await _notify_duel_result(session, duel)
        return

    # Qi regen +10% of max combat pool, capped.
    duel.combat_qi_a = min(duel.combat_qi_a_max,
                           duel.combat_qi_a + int(duel.combat_qi_a_max * REGEN_PCT_PER_ROUND))
    duel.combat_qi_b = min(duel.combat_qi_b_max,
                           duel.combat_qi_b + int(duel.combat_qi_b_max * REGEN_PCT_PER_ROUND))

    duel.round_idx = round_num + 1

    # Sudden Death trigger — entering round > max_rounds with both alive.
    if duel.round_idx > duel.max_rounds:
        if not duel.sudden_death:
            duel.sudden_death = True
            duel.action_log = (duel.action_log or []) + [{
                "round": duel.round_idx,
                "type": "sudden_death_start",
                "sudden_death": True,
            }]
            flag_modified(duel, "action_log")
        elif duel.round_idx > duel.max_rounds + SUDDEN_DEATH_MAX_EXTRA_ROUNDS:
            # Still alive after sudden death window — force tiebreak.
            await _apply_tiebreak(session, duel)
            return

    duel.state = "waiting_actions"
    # Reset round clock for the next round.
    duel.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ROUND_TIMEOUT_SECONDS)


async def _apply_tiebreak(session, duel: DuelSession) -> None:
    """Resolve a duel that hit the round/sudden-death cap, or a simultaneous KO.

    v16.7 (combat rebalance): order is damage-dealt → dao_index → luck+perception.
    HP% was demoted (the 2026-06-01 HP%-primary fix solved [jogador]'s "100% HP loses
    by luck" symptom but cemented the HP-stack disease — remaining-HP% is exactly
    what a soul/qi stacker maximizes). With the Heavenly-Pressure ramp duels KO
    before the cap, so this path is a rare fallback that rewards offense/Dao.

    v15.1.4 PvE handling preserved: NPCs have no Player row, so an NPC win is
    recorded as the 0 sentinel and the player keeps a small default edge on a
    true tie.
    """
    pve = _is_pve(duel)

    # v16.7 — HP% is NO LONGER the primary tiebreak (it rewarded HP-stacking, the
    # exact meta this rebalance kills). With the Heavenly-Pressure ramp + the
    # meaningful-minimum floor a duel almost always KOs before the cap, so this is
    # a rare fallback. Order: (1) absolute damage DEALT (rewards offense/Dao, not a
    # big HP pool), (2) Dao comprehension (dao_index from the snapshot — "Leis é
    # superior"), (3) luck + perception (Heaven's favor + Dao-sight). The phantom
    # dao_heart column is gone.
    dmg_by_a = max(0.0, (duel.hp_b_max or 0) - duel.hp_b)   # HP A removed from B
    dmg_by_b = max(0.0, (duel.hp_a_max or 0) - duel.hp_a)
    a_dao = float(((duel.fighter_a or {}).get("combat_profile") or {}).get("dao_index", 0.0))
    b_dao = float(((duel.fighter_b or {}).get("combat_profile") or {}).get("dao_index", 0.0))
    _ref = max(dmg_by_a, dmg_by_b, 1.0)
    if abs(dmg_by_a - dmg_by_b) / _ref > 0.02:
        tiebreak_kind = "damage"
        a_wins = dmg_by_a > dmg_by_b
    elif abs(a_dao - b_dao) > 0.01:
        tiebreak_kind = "dao"
        a_wins = a_dao > b_dao
    else:
        tiebreak_kind = "luck"
        a = (await session.execute(select(Player).where(Player.telegram_id == duel.attacker_id))).scalar_one_or_none()
        a_score = (getattr(a, "luck", 0) or 0) + (getattr(a, "perception", 0) or 0) + random.random()
        if pve:
            # NPC has no Player row — assume neutral score; player edge applies.
            b_score = 50.0 + random.random()
        else:
            b = (await session.execute(select(Player).where(Player.telegram_id == duel.defender_id))).scalar_one_or_none()
            b_score = (getattr(b, "luck", 0) or 0) + (getattr(b, "perception", 0) or 0) + random.random()
        a_wins = a_score >= b_score

    duel.state = "finished"
    if a_wins:
        duel.winner_id = duel.attacker_id
    else:
        # 0 = NPC sentinel (no real player has telegram_id 0); PvP uses defender.
        duel.winner_id = 0 if pve else duel.defender_id
    duel.resolved_at = datetime.now(timezone.utc)
    duel.action_log = (duel.action_log or []) + [{
        "round": duel.round_idx,
        "type": "tiebreak",
        "tiebreak": tiebreak_kind,
        "winner_id": duel.winner_id,
    }]
    flag_modified(duel, "action_log")
    await _notify_duel_result(session, duel)


async def _grant_combat_insight(session, duel: DuelSession, player_id: int, *,
                                won: bool, hp_frac: float, my_bp: float, opp_bp: float) -> None:
    """Sprint 7 — Combate 顿悟: POST-SETTLE, gated, ADDITIVE. A worthy win tempers the flesh
    (+mortal_temper_progress) and a near-death worthy win grants a 顿悟 charge (Sprint 8 BT-4).
    NEVER changes the duel result; any failure is swallowed so combat is never affected. On
    `main` (cultivo_corpo_r0 OFF) it's a no-op → byte-identical duels for the 57."""
    try:
        from core.insight_engine import insight_on, award_combat_insight
        if not insight_on():
            return
        player = (await session.execute(
            select(Player).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()
        if not player:
            return
        res = award_combat_insight(player, won=won, hp_frac=hp_frac, my_bp=my_bp, opp_bp=opp_bp)
        if not (res.get("progress_added") or res.get("got_charge")):
            return
        try:
            from core.notification_engine import notify as _notify
            if res.get("got_charge"):
                await _notify(session, player_id, "insight_charge_gained",
                              title_key="notif_insight_charge_title",
                              body_key="notif_insight_charge_body",
                              ref_id=f"{duel.id}:insight_charge:{player_id}",
                              icon="✨", target_tab="combat", priority=2)
            elif res.get("progress_added"):
                await _notify(session, player_id, "insight_gained",
                              title_key="notif_insight_title",
                              body_key="notif_insight_body",
                              payload={"n": res["progress_added"]},
                              ref_id=f"{duel.id}:insight:{player_id}",
                              icon="🥋", target_tab="combat", priority=1)
        except Exception:
            logger.exception("insight notify failed duel=%s player=%s", duel.id, player_id)
    except Exception:
        logger.exception("combat insight hook failed duel=%s player=%s", duel.id, player_id)


async def _notify_duel_result(session, duel: DuelSession) -> None:
    """v15.1.2 — emit bell notifications to both players when a duel ends.

    Called from every terminal path: HP-zero, tiebreak, forfeit. Uses
    duel.id as ref_id so notify() dedups on engine retries.
    """
    try:
        from core.notification_engine import notify as _notify
    except Exception:
        return  # engine missing — non-critical, just skip

    winner_id = duel.winner_id
    if winner_id is None:
        return  # cancelled/declined paths have no result to announce

    a_name = (duel.fighter_a or {}).get("dao_name") or (duel.fighter_a or {}).get("name") or "?"
    b_name = (duel.fighter_b or {}).get("dao_name") or (duel.fighter_b or {}).get("name") or "?"

    # Sprint 7 — Combate 顿悟: grant body insight to the REAL player(s) BEFORE the notify
    # branches (the PvE path returns early). winner_id != None here. Gated + try/except.
    fa_bp = float((duel.fighter_a or {}).get("bp") or 0)
    fb_bp = float((duel.fighter_b or {}).get("bp") or 0)
    hp_a_frac = (float(duel.hp_a or 0) / float(duel.hp_a_max)) if duel.hp_a_max else 1.0
    hp_b_frac = (float(duel.hp_b or 0) / float(duel.hp_b_max)) if duel.hp_b_max else 1.0
    await _grant_combat_insight(session, duel, duel.attacker_id,
                                won=(winner_id == duel.attacker_id),
                                hp_frac=hp_a_frac, my_bp=fa_bp, opp_bp=fb_bp)
    if not _is_pve(duel) and duel.defender_id:
        await _grant_combat_insight(session, duel, duel.defender_id,
                                    won=(winner_id == duel.defender_id),
                                    hp_frac=hp_b_frac, my_bp=fb_bp, opp_bp=fa_bp)

    # v15.1.4 — PvE: only notify the attacker (NPC has no inbox). The
    # win/loss flag is derived from winner_id == attacker_id (0 sentinel
    # = NPC won, player lost).
    if _is_pve(duel):
        won = (winner_id == duel.attacker_id)
        try:
            await _notify(
                session, duel.attacker_id,
                "duel_result_win" if won else "duel_result_loss",
                title_key="notif_duel_won_title" if won else "notif_duel_lost_title",
                body_key="notif_duel_won_body" if won else "notif_duel_lost_body",
                payload={"name": b_name},
                ref_id=f"{duel.id}:{duel.attacker_id}",
                icon="🌟" if won else "💀",
                target_tab="combat",
                priority=2 if won else 3,
            )
        except Exception:
            logger.exception("duel_result notify (PvE) failed duel=%s", duel.id)
        return

    for player_id, opp_name in (
        (duel.attacker_id, b_name),
        (duel.defender_id, a_name),
    ):
        won = (winner_id == player_id)
        try:
            await _notify(
                session, player_id,
                "duel_result_win" if won else "duel_result_loss",
                title_key="notif_duel_won_title" if won else "notif_duel_lost_title",
                body_key="notif_duel_won_body" if won else "notif_duel_lost_body",
                payload={"name": opp_name},
                ref_id=f"{duel.id}:{player_id}",
                icon="🌟" if won else "💀",
                target_tab="combat",
                priority=2 if won else 3,
            )
        except Exception:
            logger.exception("duel_result notify failed duel=%s player=%s", duel.id, player_id)


# ─── Accept (defender) / Decline-Cancel / Forfeit ────────────────────────────


async def accept_duel(session, duel: DuelSession, player_id: int) -> dict:
    """Defender accepts the challenge — duel transitions to waiting_actions.

    Returns {ok, reason?}. Only the defender can accept. If the duel is
    already past pending_acceptance, the call is a no-op (idempotent ok).
    """
    if duel.state == "waiting_actions":
        return {"ok": True, "already_started": True}
    if duel.state != "pending_acceptance":
        return {"ok": False, "reason": "duel_not_pending"}
    if player_id != duel.defender_id:
        return {"ok": False, "reason": "only_defender_can_accept"}
    duel.state = "waiting_actions"
    # Round 1 clock starts now.
    duel.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ROUND_TIMEOUT_SECONDS)
    duel.action_log = (duel.action_log or []) + [{
        "round": 0,
        "type": "accepted",
        "accepted_by": player_id,
    }]
    flag_modified(duel, "action_log")
    return {"ok": True}


# ─── Round / acceptance timeout (auto-resolve when player AFK) ───────────────


def golpe_padrao_on(world_key: str | None = None) -> bool:
    """Gate estavel da flag per-world `golpe_padrao` (padrao `forbidden_on`).

    Fail-safe -> False, e com ela OFF a funcao abaixo devolve o golpe basico
    SEM tocar na base de dados: o duelo do `main` fica byte-identico ao de hoje.
    """
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("golpe_padrao", world_key))
    except Exception:
        return False


# O GOLPE PADRAO — report do [jogador] (10/09 09:59), decisao do owner (12/09).
#
#   "in Arena, give option to set 'default' technique to use (instead of
#    default regular attack). This can give the option to advance paths without
#    having to wait each time the 3 minutes counter."
#
# O QUE ELE ESTAVA A PEDIR, dito pelo que se mediu: a arena e' **100% NPC** (0
# duelos PvP em 30 dias nas duas bases; o ultimo de qualquer tipo foi a
# 2026-07-31; 16.516 `arena_npc_fallback` all-time no `main`). Quem entra na
# fila espera SEMPRE os 3 minutos e recebe um NPC no fim — e se nao estiver la'
# quando a ronda de 15 s esgota, luta a SOCO. O tempo dele passava sem que nada
# no Caminho andasse.
#
# ISTO E' O MOTOR, NAO A ARENA (Lei F-7: contar os sitios). O
# `check_and_handle_timeout` e' UM chokepoint que serve as DEZ familias PvE mais
# o PvP; tratar so' a arena deixaria a masmorra e a caca com a regra antiga, que
# e' meia-correccao — e meia-correccao e' pior do que nenhuma. A preferencia e'
# do JOGADOR, e vale onde quer que o relogio dispare por ele.
#
# AS TRAVAS, e cada uma tem um motivo escrito:
#
#   1. **ARTE PROIBIDA NUNCA DISPARA SOZINHA.** O Caminho Proibido (TEC-5)
#      cobra **karma e anos de vida POR USO**. Um automatico que a lance
#      enquanto o jogador dorme cobra-lhe um preco que ele nao escolheu naquele
#      instante — e, pior, o gate que recusaria (`forbidden_use_gate`) existe
#      para DIZER porque' recusou, e um preenchimento automatico nao tem a quem
#      dizer. Por isso ela nem sequer e' escolhivel como padrao (a tela recusa,
#      com o motivo), e aqui ha' a segunda tranca: mesmo que o id chegue, cai no
#      basico.
#   2. **Sem qi, cai no basico.** O `submit_action` recusa a ronda quando falta
#      qi; um automatico nao pode recusar (deixaria a luta pendurada — que foi
#      exactamente o bug dos 13 trancados). Cai no basico, que e' o que ele
#      faria na mesma.
#   3. **A tecnica tem de estar EQUIPADA nesta luta.** Le-se do retrato
#      (`duel.fighter_*`), como o `submit_action` le': um id que saiu do
#      catalogo, ou uma arte que ele desequipou, nao passa.
#
# E TODA recusa fica ESCRITA no `action_log` (`default_strike`, com o motivo).
# O jogador tem de poder ver porque' o automatico nao fez o que ele mandou —
# um silencio aqui seria a mesma ferida do "sua fila expirou" que nao dizia nada.
BASIC_STRIKE = {"technique_id": 0, "qi_cost": 0, "auto": True}


async def resolve_default_strike(session, duel: DuelSession, side: str) -> dict:
    """A accao com que o relogio preenche o lado `side` ('a' ou 'b').

    Devolve sempre um dict pronto a gravar em `pending_action_*`. Com a flag
    OFF (ou sem preferencia gravada) devolve o golpe basico de sempre.
    """
    basic = dict(BASIC_STRIKE)
    if not golpe_padrao_on():
        return basic

    player_id = duel.attacker_id if side == "a" else duel.defender_id
    if not player_id:
        # o lado do NPC num duelo PvE — nunca teve preferencia nenhuma
        return basic

    try:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == int(player_id))
        )).scalar_one_or_none()
    except Exception:
        logger.exception("default strike: player read failed duel=%s side=%s",
                         duel.id, side)
        return basic
    if player is None:
        return basic

    tech_id = int(getattr(player, "default_technique_id", 0) or 0)
    if not tech_id:
        return basic

    fighter = duel.fighter_a if side == "a" else duel.fighter_b
    tech = _find_technique(fighter or {}, tech_id)
    if not tech:
        return dict(basic, fell_back="not_equipped", wanted=tech_id)

    # trava 1 — a arte proibida nao dispara sozinha. `is_forbidden` e' sync e
    # devolve False com a flag `forbidden_path` OFF => zero custo no caminho comum.
    try:
        from core.forbidden_path_engine import is_forbidden
        if is_forbidden(tech_id):
            return dict(basic, fell_back="forbidden_never_auto", wanted=tech_id)
    except Exception:
        logger.exception("default strike: forbidden check failed tech=%s", tech_id)
        return dict(basic, fell_back="forbidden_never_auto", wanted=tech_id)

    # trava 2 — sem qi de combate, o basico. Nunca recusar a ronda: uma ronda
    # recusada aqui deixa o duelo aberto para sempre (os 13 trancados de 03/09).
    qi_cost = int(tech.get("qi_cost", 10))
    current_qi = duel.combat_qi_a if side == "a" else duel.combat_qi_b
    if float(current_qi or 0) < qi_cost:
        return dict(basic, fell_back="not_enough_combat_qi", wanted=tech_id)

    return {"technique_id": tech_id, "qi_cost": qi_cost, "auto": True,
            "default_strike": True}


async def check_and_handle_timeout(session, duel: DuelSession) -> bool:
    """If round/acceptance window expired, auto-fill missing actions + resolve.

    Called from `submit_action` and `get_duel_state` so any poll can trigger
    the auto-resolution — no background scheduler needed.

    - pending_acceptance + expires_at < now  → state='expired' (no winner)
    - waiting_actions   + expires_at < now  → missing side(s) auto-fill with
      basic strike (technique_id=0), then resolve round.

    Returns True if duel state changed.
    """
    now = datetime.now(timezone.utc)
    if not duel.expires_at or duel.expires_at > now:
        return False

    if duel.state == "pending_acceptance":
        duel.state = "expired"
        duel.resolved_at = now
        duel.action_log = (duel.action_log or []) + [{
            "round": 0,
            "type": "expired_acceptance",
        }]
        flag_modified(duel, "action_log")
        return True

    if duel.state == "waiting_actions":
        autofilled = []
        # O GOLPE PADRAO — o preenchimento deixa de ser SEMPRE o soco e passa a
        # ser a tecnica que o jogador escolheu (quando ha' uma, quando ela passa
        # nas travas, e quando a flag esta' ligada). Com a flag OFF o
        # `resolve_default_strike` devolve exactamente o dict de hoje, sem sequer
        # ir a' base de dados.
        _strikes = {}
        if duel.pending_action_a is None:
            duel.pending_action_a = await resolve_default_strike(session, duel, "a")
            flag_modified(duel, "pending_action_a")
            autofilled.append("a")
            _strikes["a"] = duel.pending_action_a
        if duel.pending_action_b is None:
            duel.pending_action_b = await resolve_default_strike(session, duel, "b")
            flag_modified(duel, "pending_action_b")
            autofilled.append("b")
            _strikes["b"] = duel.pending_action_b
        if autofilled:
            _entry = {
                "round": duel.round_idx,
                "type": "round_timeout",
                "autofilled": autofilled,
            }
            # A key so' nasce quando ha' alguma coisa para contar (OFF-identity:
            # o `action_log` do `main` fica byte-identico). E quando nasce, DIZ o
            # que aconteceu — inclusive quando o automatico NAO pode usar a arte
            # escolhida e porque'. Um automatico silencioso que nao faz o que lhe
            # mandaram e' a mesma ferida do "sua fila expirou" sem razao.
            _said = {k: {kk: vv for kk, vv in v.items()
                         if kk in ("technique_id", "fell_back", "wanted")}
                     for k, v in _strikes.items()
                     if v.get("default_strike") or v.get("fell_back")}
            if _said:
                _entry["default_strike"] = _said
            duel.action_log = (duel.action_log or []) + [_entry]
            flag_modified(duel, "action_log")
        await _resolve_round(session, duel)
        return True

    return False


# ── 鎖 O REGISTO DAS FAMÍLIAS PvE (2026-09-04) ────────────────────────────────
#
# PORQUE ISTO EXISTE: a 2026-09-03 havia **27 duelos expirados a prender 13
# jogadores**, o mais antigo desde 23/05 (103 dias). A causa não foi um bug de
# lógica — foi que os varredores de recuperação nasceram **um a um, para a fonte
# que reclamou**: `exploration` (report do [jogador]), `dungeon_boss` (o mesmo),
# `jianghu_ambush` (nasceu com a onda). Contadas as fontes que o código
# realmente cria, eram **DEZ** — e **sete não tinham varredor nenhum**,
# incluindo:
#
#   • `arena_npc_fallback` — a MAIOR fonte PvE do jogo (1.352 lutas/30d);
#   • `npc_hunt` — que é o **valor por omissão** de `start_duel_pve`, ou seja,
#     qualquer chamador novo que esqueça `source=` cai numa família sem varredor.
#
# Este tuplo é a **fonte única**. O varredor percorre-o inteiro, e há um teste
# que falha se aparecer no código um `pve_source` que não esteja aqui. É a única
# coisa que impede a 6ª recorrência de "quem finaliza credita" / "job dinâmico
# exige sweep de recovery".
#
# ⚠️ Fonte nova ⇒ acrescentar AQUI no mesmo commit. Não há segunda lista.
PVE_SOURCES = (
    "arena_npc_fallback",   # core/arena_engine.py
    "dungeon_boss",         # core/webserver.py
    "exploration",          # core/exploration_engine.py
    "heart_demon",          # core/forbidden_path_engine.py  (HD_PVE_SOURCE)
    "hidden_rite",          # core/sect_library_engine.py    (RITE_PVE_SOURCE)
    "jianghu_ambush",       # core/jianghu_engine.py         (JH_AMBUSH_SOURCE)
    "legacy_cave",          # core/legacy_cave_engine.py     (CAVE_PVE_SOURCE)
    "npc_cultivator",       # core/webserver.py
    "npc_hunt",             # core/webserver.py + o DEFAULT de start_duel_pve
    "sect_trial",           # core/sect_trial_engine.py
)

# ⚠️ FONTES QUE NAO LIQUIDAM POR `pve_duel_settle` (2026-09-12).
#
# O `arena_npc_fallback` liquida por `arena_duel_settle.settle_arena_duel` (ELO
# + recompensas de arena, a metade) e esse caminho **nunca carimba
# `pve_settled`** — o carimbo e' do `pve_duel_settle` e so' dele. Consequencia
# medida em producao a 2026-09-12: **16.483 duelos de arena do `main`** (e 229
# do `s2`) parecem "por liquidar" para sempre, quando estao pagos ha' meses.
#
# 🔴 Porque e' que isto e' uma MINA e nao uma curiosidade: o despachante de
# `apply_post_duel_effects` escolhe o caminho da arena por **haver uma linha em
# `arena_queue` ligada ao duelo** — e `arena_queue` tem UMA linha por jogador,
# reciclada a cada nova fila. Medido: **so' 28 dos 16.483** ainda tem linha. Os
# outros 16.455 cairiam no `settle_pve_duel`, que para esta fonte nao tem ramo
# nenhum (cai em `unknown_source`, sem loot) — **mas nao antes de voltar a dar
# XP de maestria e XP de Intencao**, que o `settle_arena_duel` ja' tinha dado.
# Uma varredura desatenta inflacionaria a maestria e a Intencao da populacao
# inteira de uma so' vez.
#
# ⚠️ Isto NAO tira a arena do varredor: ela continua na metade que **DESTRANCA**
# (e' precisamente a fonte que estava a prender jogadores). Sai so' da metade
# que **PAGA**.
PVE_SOURCES_SETTLED_ELSEWHERE = ("arena_npc_fallback",)

# Estados em que um duelo ainda TRANCA o jogador (o guard recusa outra luta).
DUEL_OPEN_STATES = ("waiting_actions", "pending_acceptance")
# Estados terminais que ainda podem dever crédito ao jogador (loot, carimbo de
# masmorra, progresso de quest) enquanto não tiverem o marcador `pve_settled`.
DUEL_TERMINAL_STATES = ("finished", "forfeited")


async def resolve_pve_duel_to_end(session, duel: DuelSession) -> bool:
    """Leva um duelo PvE expirado a um estado TERMINAL, nao so' a' ronda seguinte.

    ⚠️ ISTO E' O CORACAO DO BUG DOS 103 DIAS. `check_and_handle_timeout` resolve
    **uma ronda**: preenche as accoes em falta, chama `_resolve_round`, e se
    ninguem morrer o `_resolve_round` poe `state='waiting_actions'` outra vez com
    um `expires_at` NOVO. O duelo continua aberto, o guard volta a recusar, e o
    jogador tem de tentar tantas vezes quantas as rondas que faltavam.

    A base de producao provou o mecanismo sozinha: linhas criadas a 2026-06-28
    06:29 com `expires_at` a 2026-07-18 04:47 — vinte dias a' frente. E' a
    impressao digital de alguem que tentou, resolveu uma ronda, e foi recusado.

    **Termina por construcao**, sem depender de a luta ser "boa": ao entrar na
    ronda > `max_rounds` liga-se a Morte Subita e, passados
    `SUDDEN_DEATH_MAX_EXTRA_ROUNDS`, o `_resolve_round` chama `_apply_tiebreak`.
    O tecto abaixo e' so' um cinto de seguranca contra um futuro em que essa
    saida se parta — nunca deve ser ele a disparar.

    ⚠️ **So' PvE.** Num duelo PvP o prazo de ronda e' um relogio partilhado entre
    duas pessoas: resolver a luta inteira porque UMA ronda expirou roubaria ao
    outro humano as rondas que ainda tinha. Ai' o comportamento de
    uma-ronda-por-chamada e' o correcto e fica como esta'.

    **O que acontece a quem abandonou:** as accoes em falta sao preenchidas com
    o golpe basico (`technique_id=0`), exactamente como o timeout de sempre — o
    build do jogador continua a lutar, so' que sem tecnicas. Pode ganhar, pode
    perder. Nao e' vitoria gratis nem derrota gratis, e e' **o mesmo precedente**
    que `sweep_orphan_dungeon_boss_duels` ja' aplicava desde 2026-07.

    Devolve True se o estado mudou. O caller e' dono do commit.
    """
    if not _is_pve(duel):
        return await check_and_handle_timeout(session, duel)

    # ⚠️ O PRIMEIRO passo decide se isto e' sequer um orfao.
    # `check_and_handle_timeout` devolve False quando o prazo AINDA NAO passou —
    # e' assim que uma luta viva fica intocada. So' se ele devolver True e' que
    # sabemos que ninguem apareceu a tempo.
    if not await check_and_handle_timeout(session, duel):
        return False

    # ⚠️ E AQUI ESTAVA O DEFEITO QUE O ENSAIO EM PRODUCAO APANHOU (2026-09-04).
    # A primeira versao deste laco voltava a chamar `check_and_handle_timeout` e
    # parava, porque o `_resolve_round` acabara de por um `expires_at` NOVO no
    # FUTURO. Resultado: resolvia UMA ronda e devolvia — exactamente o que o
    # codigo antigo ja' fazia. No ensaio contra a base real, **18 dos 27 duelos
    # sairam `waiting_actions(r1) -> waiting_actions(r2)`**, ainda presos. Os 9
    # que fecharam so' fecharam porque a ronda calhou ser letal.
    #
    # Um teste com mock teria passado. Foi correr contra as linhas verdadeiras
    # que mostrou.
    #
    # A correccao: uma vez estabelecido que o duelo E' orfao, empurra-se o prazo
    # para o passado antes de cada ronda seguinte, de modo a reutilizar o MESMO
    # caminho de auto-preenchimento em vez de escrever um segundo. O duelo fecha
    # sozinho quando `_resolve_round` chegar ao KO ou ao desempate da Morte
    # Subita.
    changed = True
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    # max_rounds + janela de morte subita + folga. Se isto esgotar, ha' um
    # defeito no terminador do `_resolve_round` — dai' o warning ruidoso.
    budget = int(duel.max_rounds or MAX_ROUNDS) + SUDDEN_DEATH_MAX_EXTRA_ROUNDS + 4
    for _ in range(budget):
        if duel.state not in DUEL_OPEN_STATES:
            return changed
        duel.expires_at = past
        if not await check_and_handle_timeout(session, duel):
            # Nao devia acontecer (acabamos de por o prazo no passado), mas se
            # acontecer e' melhor sair do que ciclar em silencio.
            return changed
    if duel.state in DUEL_OPEN_STATES:
        logger.warning(
            "resolve_pve_duel_to_end: duelo %s ainda aberto apos %d rondas "
            "(state=%s round=%s) - o terminador do _resolve_round nao fechou",
            duel.id, budget, duel.state, duel.round_idx,
        )
    return changed


async def sweep_orphan_pve_duels(session, *, limit: int = 200) -> int:
    """UM varredor para TODAS as familias PvE (`PVE_SOURCES`).

    Substitui a coleccao de varredores por-fonte que deixou 7 familias a
    descoberto. Faz duas coisas, ambas idempotentes:

      1. **Destranca** — leva duelos expirados a um estado terminal
         (`resolve_pve_duel_to_end`), libertando o jogador.
      2. **Paga** — liquida os terminais que ainda nao tem o marcador
         `pve_settled`, para que o loot, o carimbo da masmorra e o progresso de
         quest cheguem a quem os ganhou.

    ⚠️ Uma luta **dentro do prazo** nunca e' tocada: `check_and_handle_timeout`
    devolve False e o duelo fica exactamente como esta'.

    ⚠️ **Nunca apaga uma linha.** Alguns destes duelos estao GANHOS e nunca foram
    liquidados — um DELETE roubaria o jogador duas vezes (perdia a luta e o
    premio). Resolver pelo caminho normal e' o que devolve o que e' dele.

    Caller e' dono do commit. Devolve quantos foram liquidados.
    """
    from core.pve_duel_settle import _already_settled

    # ⚠️ UMA query para as dez familias, nao dez.
    # Este varredor corre no tick de 60 s. A primeira versao percorria
    # `PVE_SOURCES` com uma query por fonte = 10 queries/tick = 14.400/dia, quase
    # todas vazias — e foi exactamente por isso que o autor do MV-8 tinha posto
    # um gate de flag no varredor dele. Com `IN (...)` o custo volta a ser UMA
    # query indexada por tick e **nenhuma familia precisa de gate**, que e' o que
    # permite a este varredor cobrir as sete que nunca tiveram rede.
    #
    # `created_at ASC` de proposito: o mais ANTIGO primeiro. Quem esta' preso ha'
    # 103 dias sai a' frente de quem fechou a app ha' cinco minutos.
    # 🔴 2026-09-12 — DUAS VARREDURAS, E ESTE E' O CONSERTO.
    #
    # A versao de 04/09 fazia UMA query com `state IN (abertos + terminais)`,
    # `created_at ASC`, `limit 200`. Parecia certa e nunca funcionou: no `main`
    # esse conjunto tem **23.842 linhas, das quais 23.840 sao TERMINAIS**. As 200
    # que a query devolvia eram, todos os ticks, **as 200 mais antigas da base —
    # de 17 a 21 de Maio, 200/200 ja' carimbadas**. Os dois duelos ABERTOS
    # estavam nas posicoes **23.601 e 23.639** da mesma ordenacao.
    #
    # Ou seja: o varredor correu de 60 em 60 segundos durante oito dias — ~11.500
    # passagens — e **nunca chegou a um unico duelo aberto**. Enquanto isso havia
    # tres jogadores trancados, o mais antigo desde **04/09** e **activo hoje**.
    #
    # ⚠️ O `created_at ASC` estava CERTO e fica: quem esta' preso ha' mais tempo
    # sai a' frente. O que estava errado era misturar no mesmo orcamento de 200
    # um conjunto de 2 com um conjunto de 23.840. Separadas, cada metade tem o
    # seu orcamento e nenhuma pode matar a outra a' fome.
    #
    # ⚠️ E a metade que PAGA filtra o carimbo **em SQL**. Sem isso ela gastava as
    # 200 linhas a reler duelos ja' liquidados — que era exactamente a outra
    # forma de a matar a' fome. O predicado JSONB foi verificado contra o
    # `_already_settled` em producao: **0 discordancias em 23.840 linhas**.
    settled = 0
    # (a) DESTRANCA — o conjunto que prende gente. Pequeno por natureza.
    try:
        abertos = (await session.execute(
            select(DuelSession.id).where(
                DuelSession.pve_source.in_(PVE_SOURCES),
                DuelSession.state.in_(DUEL_OPEN_STATES),
            ).order_by(DuelSession.created_at.asc()).limit(limit)
        )).scalars().all()
    except Exception:
        logger.exception("sweep PvE: scan dos ABERTOS falhou")
        abertos = []
    # (b) PAGA — terminais por liquidar, sem as fontes que liquidam noutro sitio.
    try:
        pagaveis = (await session.execute(
            select(DuelSession.id).where(
                DuelSession.pve_source.in_(
                    [f for f in PVE_SOURCES if f not in PVE_SOURCES_SETTLED_ELSEWHERE]
                ),
                DuelSession.state.in_(DUEL_TERMINAL_STATES),
                ~DuelSession.action_log.contains([{"type": "pve_settled"}]),
            ).order_by(DuelSession.created_at.asc()).limit(limit)
        )).scalars().all()
    except Exception:
        logger.exception("sweep PvE: scan dos PAGAVEIS falhou")
        pagaveis = []
    # ⚠️ Um `id` pode aparecer nas duas listas ao longo do tempo (um aberto que
    # esta varredura fecha vira pagavel na proxima). Dentro de UMA passagem a
    # lista e' unica, e o `_already_settled` continua a ser o dono da decisao.
    ids = list(dict.fromkeys(list(abertos) + list(pagaveis)))
    if not ids:
        return 0
    for did in ids:
        try:
            duel = (await session.execute(
                select(DuelSession).where(DuelSession.id == did).with_for_update()
            )).scalar_one_or_none()
            if duel is None:
                continue
            if duel.state in DUEL_OPEN_STATES:
                await resolve_pve_duel_to_end(session, duel)
            if duel.state in DUEL_TERMINAL_STATES and not _already_settled(duel):
                await apply_post_duel_effects(session, duel)
                settled += 1
        except Exception:
            logger.exception("sweep PvE: settle falhou duel=%s", did)
    return settled


async def unlock_stuck_duels_for_player(session, player_id: int) -> int:
    """Destranca TODOS os duelos abertos deste jogador, nao `.limit(1)`.

    ⚠️ O guard do chefe de masmorra (e os irmaos dele) resolvia **um** duelo por
    chamada e recusava na mesma. Medido a 2026-09-03: um jogador tinha **15**
    linhas presas — precisaria de 15 tentativas x as rondas de cada uma.

    Devolve quantos deixaram de estar abertos.
    """
    from sqlalchemy import or_ as _or

    ids = (await session.execute(
        select(DuelSession.id).where(
            _or(DuelSession.attacker_id == int(player_id),
                DuelSession.defender_id == int(player_id)),
            DuelSession.state.in_(DUEL_OPEN_STATES),
        ).order_by(DuelSession.created_at.asc()).limit(50)
    )).scalars().all()
    freed = 0
    for did in ids:
        try:
            duel = (await session.execute(
                select(DuelSession).where(DuelSession.id == did).with_for_update()
            )).scalar_one_or_none()
            if duel is None or duel.state not in DUEL_OPEN_STATES:
                continue
            await resolve_pve_duel_to_end(session, duel)
            if duel.state not in DUEL_OPEN_STATES:
                freed += 1
        except Exception:
            logger.exception("unlock: falhou duel=%s jogador=%s", did, player_id)
    return freed


async def forfeit_duel(session, duel: DuelSession, player_id: int) -> dict:
    """Bifurcates based on current state:

      - pending_acceptance + attacker → state='cancelled' (attacker pulls challenge)
      - pending_acceptance + defender → state='declined' (defender refuses)
      - waiting_actions               → state='forfeited' (in-duel surrender)

    No winner is set for cancelled/declined (no combat happened). Forfeit
    sets winner_id = opponent (counts as a loss for the surrenderer).
    """
    side = _side_of(duel, player_id)
    if side is None:
        return {"ok": False, "reason": "not_a_participant"}

    now = datetime.now(timezone.utc)

    if duel.state == "pending_acceptance":
        if side == "a":  # attacker cancels their own challenge
            duel.state = "cancelled"
            entry_type = "cancelled"
        else:            # defender declines the challenge
            duel.state = "declined"
            entry_type = "declined"
        duel.resolved_at = now
        duel.action_log = (duel.action_log or []) + [{
            "round": 0,
            "type": entry_type,
            "by": player_id,
        }]
        flag_modified(duel, "action_log")
        return {"ok": True}

    if duel.state == "waiting_actions":
        duel.state = "forfeited"
        if side == "a":
            # Player forfeited in PvE (no defender) → NPC sentinel.
            duel.winner_id = 0 if _is_pve(duel) else duel.defender_id
        else:
            duel.winner_id = duel.attacker_id
        duel.resolved_at = now
        duel.action_log = (duel.action_log or []) + [{
            "round": duel.round_idx,
            "type": "forfeit",
            "forfeited_by": player_id,
            "winner_id": duel.winner_id,
        }]
        flag_modified(duel, "action_log")
        await _notify_duel_result(session, duel)
        return {"ok": True}

    return {"ok": False, "reason": "duel_not_open"}


# ─── State projection (viewer-aware) ─────────────────────────────────────────


def _tech_lido(tech, lang):
    """Uma técnica do LOG, lida na língua de QUEM olha — e com a chave da arte.

    🔴 O LOG GRAVA CRU, DE PROPÓSITO, e isso não muda aqui. O `combat_log`
    é persistido e lido pelos DOIS lutadores, que podem ter línguas diferentes
    (o comentário `名-CRU` no construtor das técnicas diz porquê). O que estava
    errado era a LEITURA: o jogador `pt` lia "Thunder Step" dentro do duelo
    enquanto a aba Técnicas lhe mostrava "Passo do Trovão" — a mesma arte com
    dois nomes em duas telas, que a Lei 0 diz ser pior do que a ausência. É a
    lição de 卷獸圖 (15/09): **interpretar na LEITURA**.

    ⚠️ NUNCA MUTAR. O `action_log` e o `fighter_a/b` que chegam aqui SÃO as
    colunas JSON da sessão, ainda ligadas ao SQLAlchemy. Traduzir no sítio
    gravaria a tradução no log — e o log é lido pelo OUTRO lutador, na outra
    língua, para sempre. Devolve-se sempre um dicionário NOVO.

    `lang=None` ⇒ devolve o mesmo objecto, sem tocar: é o payload de hoje,
    chave a chave.
    """
    if not isinstance(tech, dict):
        return tech
    raw = tech.get("name")
    if lang is None or not raw:
        return tech
    from core.i18n import catalog_text as _ct
    out = dict(tech)
    tid = tech.get("id")
    if tid is not None:
        try:
            out["name"] = _ct(lang, "tech", int(tid), "name", raw)
        except (TypeError, ValueError):
            pass
    # A chave É o cru — o nome com que a arte foi indexada. Sempre presente,
    # mesmo quando a tradução não existe: quem desenha lê SEMPRE daqui.
    out["art_key"] = raw
    return out


def _lado_lido(lado, lang):
    """Um lado de uma linha do log (`entry.a` / `entry.b`), com a técnica lida.

    `tech` vale `None` quando o alvo esquiva ou desvia — estado honesto, que
    atravessa intacto: sem técnica, sem nome e sem destaque na resolução.
    """
    if lang is None or not isinstance(lado, dict) or "tech" not in lado:
        return lado
    out = dict(lado)
    out["tech"] = _tech_lido(lado.get("tech"), lang)
    return out


def _log_lido(log, lang):
    """O `action_log` inteiro, lido. Copia SÓ as linhas que têm lados."""
    if lang is None or not log:
        return log
    saida = []
    for entry in log:
        if not isinstance(entry, dict) or not (entry.get("a") or entry.get("b")):
            saida.append(entry)
            continue
        nova = dict(entry)
        if "a" in nova:
            nova["a"] = _lado_lido(nova["a"], lang)
        if "b" in nova:
            nova["b"] = _lado_lido(nova["b"], lang)
        saida.append(nova)
    return saida


def get_duel_state(duel: DuelSession, viewer_id: int, lang=None) -> dict:
    """Return the duel state as the viewer should see it.

    Hides opponent's pending_action while the round is open — preserves
    simultaneous-submission integrity.

    武 2.2 — `lang` é OPCIONAL e o default é o payload de hoje, chave a chave.
    Com língua, os nomes de técnica (em `you.techniques[]` e em cada lado do
    `action_log`) saem LIDOS na língua do espectador, com `art_key` = o nome
    canónico ao lado — que é o que faz a arte ser encontrada fora do inglês.
    Ver `_tech_lido`: o log continua a GRAVAR cru.
    """
    is_a = viewer_id == duel.attacker_id
    is_b = viewer_id == duel.defender_id
    you_side = "a" if is_a else "b" if is_b else None

    your_pending = duel.pending_action_a if is_a else duel.pending_action_b if is_b else None
    opponent_submitted = (
        (duel.pending_action_b is not None) if is_a
        else (duel.pending_action_a is not None) if is_b
        else False
    )

    your_fighter = duel.fighter_a if is_a else duel.fighter_b if is_b else duel.fighter_a
    opponent_fighter = duel.fighter_b if is_a else duel.fighter_a if is_b else duel.fighter_b

    # v15.1.4 — PvE flag for the UI (suppress wager forfeit warnings,
    # render NPC chip with archetype/difficulty labels).
    is_pve = duel.defender_id is None or bool(duel.pve_source)
    return {
        "duel_id": str(duel.id),
        "state": duel.state,
        "round_idx": duel.round_idx,
        "max_rounds": duel.max_rounds,
        "sudden_death": duel.sudden_death,
        "winner_id": duel.winner_id,
        "you_side": you_side,
        "pve": is_pve,
        "npc_archetype": duel.npc_archetype if is_pve else None,
        "npc_difficulty": duel.npc_difficulty if is_pve else None,
        "pve_source": duel.pve_source if is_pve else None,
        "you": {
            "telegram_id": your_fighter.get("telegram_id"),
            "dao_name": your_fighter.get("dao_name") or your_fighter.get("name"),
            "hp": int(duel.hp_a) if is_a else int(duel.hp_b),
            "hp_max": int(duel.hp_a_max) if is_a else int(duel.hp_b_max),
            "combat_qi": int(duel.combat_qi_a) if is_a else int(duel.combat_qi_b),
            "combat_qi_max": int(duel.combat_qi_a_max) if is_a else int(duel.combat_qi_b_max),
            # 武 2.2 — lidas, nunca mutadas: `_tech_lido` devolve dicionários
            # novos e o `fighter_a/b` da sessão fica exactamente como está.
            "techniques": [
                _tech_lido(_tt, lang) for _tt in (your_fighter.get("techniques") or [])
            ],
            "pending": your_pending,
        },
        "opponent": {
            "telegram_id": opponent_fighter.get("telegram_id"),
            "dao_name": opponent_fighter.get("dao_name") or opponent_fighter.get("name"),
            "hp": int(duel.hp_b) if is_a else int(duel.hp_a),
            "hp_max": int(duel.hp_b_max) if is_a else int(duel.hp_a_max),
            "combat_qi": int(duel.combat_qi_b) if is_a else int(duel.combat_qi_a),
            "combat_qi_max": int(duel.combat_qi_b_max) if is_a else int(duel.combat_qi_a_max),
            "submitted": opponent_submitted,
        },
        "action_log": _log_lido(duel.action_log or [], lang),
        "expires_at": duel.expires_at.isoformat() if duel.expires_at else None,
    }


# ─── Apply persistent HP drain post-duel ─────────────────────────────────────


async def apply_post_duel_effects(session, duel: DuelSession) -> None:
    """When a duel finishes, drain real HP on both players (30% of damage taken).

    v15.1.3 — also settles PVPChallenge-sourced duels (wager payout +
    mastery XP + sparring side-effects) via `core.pvp_duel_settle`. The
    settle helper is idempotent (gates on PVPChallenge.status='completed')
    so re-entrant calls from polling are safe.

    Mirrors sparring/arena HP drain pattern from combat_engine.
    """
    if duel.state not in ("finished", "forfeited") or duel.resolved_at is None:
        return

    # BUGFIX 2026-06-02 — the HP drain below is NOT idempotent (apply_hp_drain
    # mutates current_hp from damage every call). This function is called from
    # every `combat/duel_state` poll AND now the arena settle safety-net sweep, so
    # guard the drain with an action_log marker. The settle helpers further down
    # have their own idempotency (status gates), so only the drain needs this.
    _log = duel.action_log or []
    _already_drained = any(
        isinstance(e, dict) and e.get("type") == "hp_drained" for e in _log
    )
    if not _already_drained:
        a = (await session.execute(select(Player).where(Player.telegram_id == duel.attacker_id))).scalar_one_or_none()
        if a is not None:
            a_dmg = max(0.0, duel.hp_a_max - duel.hp_a)
            # v15.1.4 — PvE drain is heavier (50% mirrors legacy NPC drain;
            # boss floors share that profile). PvP keeps 30%.
            drain_pct = 0.50 if _is_pve(duel) else 0.30
            # BUGFIX 2026-07-26: scale effective combat-pool damage into the raw
            # current_hp pool (over-drain-to-0-on-win under combate_unificado).
            apply_hp_drain_scaled(a, a_dmg, duel.hp_a_max, drain_pct=drain_pct)
        # PvE: no defender Player row to drain (NPC).
        if not _is_pve(duel):
            b = (await session.execute(select(Player).where(Player.telegram_id == duel.defender_id))).scalar_one_or_none()
            if b is not None:
                b_dmg = max(0.0, duel.hp_b_max - duel.hp_b)
                apply_hp_drain_scaled(b, b_dmg, duel.hp_b_max, drain_pct=0.30)
        duel.action_log = _log + [{"type": "hp_drained", "round": duel.round_idx}]
        flag_modified(duel, "action_log")

    # TEC-5 — o custo do Caminho Proibido (karma + anos) é cobrado AQUI, e não
    # dentro dos 3 settles: este é o ÚNICO ponto por onde TODO duelo terminal
    # passa. Um duelo direto (`combat/duel_create`) não tem PVPChallenge nem
    # ArenaQueue nem pve_source, e `settle_pvp_duel` desiste antes de cobrar —
    # o poder proibido saía de graça exatamente onde dois jogadores combinam a
    # luta. Idempotente pelo marker `fpd_cost` (mesmo padrão do hp_drained).
    # Corre ANTES do dispatcher para o payload do settle PvE já o encontrar.
    try:
        from core.forbidden_path_engine import charge_all_sides
        await charge_all_sides(session, duel)
    except Exception:
        logger.exception("forbidden cost failed for duel=%s", duel.id)

    # v15.1.5-hf4 — settle dispatcher reordered. ArenaQueue lookup is now
    # FIRST regardless of pve_source, because the new arena NPC-fallback
    # duel (`pve_source="arena_npc_fallback"`, defender_id NULL) MUST
    # settle through arena_duel_settle (ELO + arena rewards, halved),
    # NOT through pve_duel_settle (loot table). The ArenaQueue.duel_id
    # link is the canonical discriminator for "this duel belongs to the
    # arena flow", PvP or NPC-fallback alike.
    #
    # Branches:
    #   1. ArenaQueue.duel_id == duel.id  → settle_arena_duel
    #   2. pve_source NOT NULL (no arena) → settle_pve_duel
    #   3. else                            → settle_pvp_duel (PVPChallenge)
    settled = False
    try:
        from database.models import ArenaQueue
        # BUGFIX 2026-06-02 (CaosPrimal arena-ELO report): a PvP arena match links
        # BOTH players' ArenaQueue rows to the same duel_id (arena_engine.try_match
        # sets row.duel_id on both), so `.scalar_one_or_none()` raised
        # MultipleResultsFound → the except swallowed it → settle NEVER ran for PvP
        # arena duels → ELO/win/loss never updated (only the 1-row NPC fallback
        # worked). Fetch all rows and pass a not-yet-completed one; settle_arena_duel
        # finds + completes the other row itself.
        arena_rows = (await session.execute(
            select(ArenaQueue).where(ArenaQueue.duel_id == duel.id).with_for_update()
        )).scalars().all()
        if arena_rows:
            arena_row = next((r for r in arena_rows if r.status != "completed"), arena_rows[0])
            from core.arena_duel_settle import settle_arena_duel
            await settle_arena_duel(session, duel, arena_row)
            settled = True
    except Exception:
        logger.exception("settle_arena_duel failed for duel=%s", duel.id)

    # 🔴 2026-09-12 — A QUEDA QUE DAVA XP DUAS VEZES.
    # Um duelo de arena cujo `ArenaQueue` foi RECICLADO (a tabela tem uma linha
    # por jogador) perde o discriminante do ramo 1 e caia aqui — e o
    # `settle_pve_duel` da' XP de maestria e de Intencao **antes** de descobrir
    # que nao conhece a fonte. O duelo ja' tinha sido pago pelo
    # `settle_arena_duel`; isto pagava-o outra vez.
    # Medido em producao: 28 de 16.483 duelos de arena do `main` ainda tem linha
    # de fila. Os outros 16.455 estavam a UM tick de varredura de serem
    # re-creditados.
    # A recusa e' explicita e fica registada: a fonte tem dono, e o dono nao e'
    # este.
    if not settled and duel.pve_source in PVE_SOURCES_SETTLED_ELSEWHERE:
        logger.info(
            "duelo %s (%s) sem linha de fila — liquidacao pertence ao caminho da "
            "arena; NAO cai no settle PvE", duel.id, duel.pve_source,
        )
    elif not settled and duel.pve_source:
        try:
            from core.pve_duel_settle import settle_pve_duel
            await settle_pve_duel(session, duel)
        except Exception:
            logger.exception("settle_pve_duel failed for duel=%s", duel.id)
    elif not settled:
        try:
            from core.pvp_duel_settle import settle_pvp_duel
            await settle_pvp_duel(session, duel)
        except Exception:
            logger.exception("settle_pvp_duel failed for duel=%s", duel.id)


# ── v15.1.4 — PvE duel generation + auto-NPC submission ─────────────────


def _build_npc_techniques_from_loadout(
    archetype: str,
    difficulty: str,
    realm: int,
) -> list[dict]:
    """Materialise the NPC's technique pool from the static loadout.

    Pulls technique stats from the engine-level catalog via lazy queries
    is too expensive — instead, we mirror the technique parameters in a
    tiny on-the-fly lookup of the canonical catalog seed. The duel state
    JSONB persists this snapshot, so even if the catalog mutates later
    the duel resolves deterministically.
    """
    from core.npc_loadouts import NPC_ARCHETYPES, DIFFICULTY_GRADE_MULT
    from database.seeds.combat_seeds import TECHNIQUES as _CATALOG_TECHS, QI_COSTS

    arch = NPC_ARCHETYPES.get(archetype) or NPC_ARCHETYPES["bandit"]
    tech_ids: list[int] = list(arch["technique_ids"])
    grade_mult = float(DIFFICULTY_GRADE_MULT.get(difficulty, 1.0))

    # Index the catalog by id once (the seed is small, ~30 entries).
    by_id = {int(t["id"]): t for t in _CATALOG_TECHS}

    out: list[dict] = []
    for tid in tech_ids:
        spec = by_id.get(int(tid))
        if not spec:
            continue
        # Skip techniques the NPC's realm cannot wield (mirrors player
        # equip-time gate). Allows the same archetype to scale from low
        # to high realm naturally — high-realm bandits drop Thunder Step
        # but still keep Celestial Palm etc.
        req_realm = int(spec.get("req_realm", 0))
        if req_realm > realm + 1:  # +1 grace so realm cap aligns with NPC offset
            continue
        out.append({
            "id": int(spec["id"]),
            "name": spec.get("name") or "?",
            "emoji": spec.get("emoji") or "⚔️",
            "effect_type": spec.get("effect_type"),
            "effect_value": float(spec.get("effect_value", 0.0)),
            "effect_round": int(spec.get("effect_round", 0)),
            "qi_cost": int(QI_COSTS.get(int(spec["id"]), 10)),
            "mastery_level": 1,
            "grade": "common",
            "grade_mult": grade_mult,
        })

    # Fallback: if the loadout filter removed everything (e.g. R0 NPC vs
    # bandit pool with req_realm=1), keep at least Thunder Step (id=1)
    # so the AI has something to swing.
    if not out:
        spec = by_id.get(1)
        if spec:
            out.append({
                "id": int(spec["id"]),
                "name": spec.get("name") or "Thunder Step",
                "emoji": spec.get("emoji") or "⚡",
                "effect_type": spec.get("effect_type"),
                "effect_value": float(spec.get("effect_value", 0.30)),
                "effect_round": int(spec.get("effect_round", 1)),
                "qi_cost": int(QI_COSTS.get(1, 10)),
                "mastery_level": 1,
                "grade": "common",
                "grade_mult": grade_mult,
            })
    return out


def generate_npc_duel_fighter(
    archetype: str,
    realm: int,
    difficulty: str,
    lang: str = "pt",
) -> dict:
    """Snapshot an NPC fighter for use as `duel.fighter_b`.

    Mirrors `generate_npc_fighter` from combat_engine (realm-scaled base
    BP/HP) but additionally:
      - applies archetype bp_mult / hp_mult / qi_capacity_mult
      - attaches the archetype technique pool with difficulty grade_mult
      - includes a synthetic `qi_capacity` so the duel engine's
        `_combat_pool_max` can compute the combat pool correctly.
    """
    from core.npc_loadouts import (
        NPC_ARCHETYPES,
        DIFFICULTY_GRADE_MULT,
        random_npc_name,
    )

    arch = NPC_ARCHETYPES.get(archetype) or NPC_ARCHETYPES["bandit"]
    realm_clamped = max(
        int(arch.get("realm_floor", 0)),
        min(int(arch.get("realm_ceiling", 10)), int(realm)),
    )
    realm_mult = REALM_MULTIPLIERS[
        min(realm_clamped, len(REALM_MULTIPLIERS) - 1)
    ]

    # Match combat_engine.NPC_DIFFICULTIES stat_mult ratios so PvE duel
    # scaling lines up with the `simulate_combat` curve (v16.6 #2: both now
    # use a single difficulty axis off the player's realm — hard 1.5, nightmare 2.5).
    diff_stat_mult = {
        "easy": 0.7, "normal": 1.0, "hard": 1.5, "nightmare": 2.5,
    }.get(difficulty, 1.0)

    # v16.7 — NPC raw stats on the SAME scale as a player at this realm (the
    # combat model applies realm_mult). Archetype bp_mult → offense (soul/bp),
    # qi_capacity_mult → qi pool, hp_mult → durability (tempering_hp). NPCs carry
    # NO Dao (dao_index 0) — a player's Leis are a real edge in PvE duels too.
    from core import combat_model as _cm
    tier = realm_clamped
    sm = diff_stat_mult
    base_soul = 50 * (tier + 1) * sm * float(arch["bp_mult"]) * random.uniform(0.9, 1.1)
    base_qi = 50 * (tier + 1) * sm * float(arch["qi_capacity_mult"]) * random.uniform(0.9, 1.1)
    base_bp = 450 * (tier + 1) * sm * float(arch["bp_mult"]) * random.uniform(0.9, 1.1)
    prof = _cm.make_profile(soul=base_soul, qi=base_qi, bp=base_bp, realm=tier,
                            tempering_hp=float(arch["hp_mult"]), perception=30 * (tier + 1) * sm)

    bp = max(50, int(_cm.strike_value(base_soul, base_bp, base_qi, tier)))
    hp = max(500.0, prof["eff_hp"])
    # BUGFIX 2026-06-02 — the combat-Qi pool (= 20% of this) must let the NPC
    # sustain ~2-3 casts of its kit across a 12-round duel; technique qi_costs are
    # fixed (10-80) regardless of realm. base_qi alone (~hundreds) gave a pool of
    # ~40-60 → NPC fell back to bonus-less basic strikes for most of the fight. Use
    # a larger, realm-scaled pool source (decoupled from the profile qi stat, which
    # stays = base_qi for HP/strike balance).
    qi_capacity = max(200, int(150 * (tier + 1) * sm * float(arch["qi_capacity_mult"])))

    name = random_npc_name(archetype, lang=lang)
    techniques = _build_npc_techniques_from_loadout(archetype, difficulty, realm_clamped)

    return {
        "telegram_id": 0,                # sentinel — NPC has no player ID
        "name": name,
        "dao_name": name,                # mirror of name so UI label code works
        "bp": bp,
        "hp": hp,
        "qi_capacity": qi_capacity,
        "armor_bonus": 0.0,
        "realm": realm_clamped,
        "sub_layer": random.randint(1, 9),
        "techniques": techniques,
        "archetype": archetype,
        "difficulty": difficulty,
        "is_npc": True,
        "defense_boost": 1.0,
        "combat_profile": prof,          # v16.7 — Três Tesouros profile for the shared core
    }


async def start_duel_pve(
    session,
    player: Player,
    archetype: str,
    difficulty: str = "normal",
    source: str = "npc_hunt",
    context: dict | None = None,
    fighter_b_override: dict | None = None,
    npc_realm: int | None = None,
) -> DuelSession:
    """Create a PvE turn-based duel (defender_id NULL → NPC).

    State starts at 'waiting_actions' immediately — no acceptance step
    needed (no human defender to consent). The NPC's first round action
    is filled lazily on the first `submit_action(player)` call.

    Args:
        session: live SQLAlchemy session
        player: attacker Player row (already locked by caller if writing)
        archetype: one of NPC_ARCHETYPES keys (or a flavour tag when an override
            fighter is supplied)
        difficulty: easy/normal/hard/nightmare
        source: 'npc_hunt' | 'dungeon_boss' | 'sect_trial' | 'npc_cultivator' |
            'exploration' | 'hidden_rite' | 'legacy_cave' — settle dispatcher uses this (a
            source absent from the chain is a SILENT dead reward: see the
            `unknown_source` branch of settle_pve_duel)
        context: opaque dict, e.g. {"dungeon_id": 4, "floor": 38}
        fighter_b_override: Onda 3 — a pre-built NPC fighter dict (e.g. an
            anonymized npc_cultivator snapshot rehydrated via
            ``npc_cultivator_engine.rehydrate_npc_fighter``). When provided it is
            used VERBATIM as fighter_b instead of generating an ephemeral
            archetype. Must carry the standard fighter keys (combat_profile, hp,
            bp, qi_capacity, techniques, is_npc, telegram_id=0).
        npc_realm: fix 2026-07-14 (report [jogadores] — boss de 2.2M numa
            dungeon r0 easy): realm explícito para o NPC gerado. Sem ele o boss
            escala pelo realm do JOGADOR — correto para npc_hunt, absurdo para
            dungeon_boss (a dungeon tem tier próprio). None → player.realm
            (comportamento de sempre; nenhum outro caller muda).
    """
    lang = (player.language or "pt").lower()
    fa = await _build_duel_fighter(session, player)
    if fighter_b_override is not None:
        fb = fighter_b_override
    else:
        fb = generate_npc_duel_fighter(
            archetype=archetype,
            realm=int(npc_realm if npc_realm is not None else (player.realm or 0)),
            difficulty=difficulty,
            lang=lang,
        )

    cqi_a_max = _combat_pool_max(player.qi_capacity)
    cqi_b_max = _combat_pool_max(fb["qi_capacity"])

    duel = DuelSession(
        attacker_id=player.telegram_id,
        defender_id=None,                # NPC sentinel
        # PvE duels skip the acceptance step — start live immediately.
        state="waiting_actions",
        round_idx=1,
        max_rounds=MAX_ROUNDS,
        combat_qi_a=cqi_a_max,
        combat_qi_b=cqi_b_max,
        combat_qi_a_max=cqi_a_max,
        combat_qi_b_max=cqi_b_max,
        hp_a=float(fa["hp"]),
        hp_b=float(fb["hp"]),
        hp_a_max=float(fa["hp"]),
        hp_b_max=float(fb["hp"]),
        bp_a=int(fa["bp"]),
        bp_b=int(fb["bp"]),
        fighter_a=fa,
        fighter_b=fb,
        pending_action_a=None,
        pending_action_b=None,
        action_log=[],
        winner_id=None,
        sudden_death=False,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ROUND_TIMEOUT_SECONDS),
        npc_archetype=archetype,
        npc_difficulty=difficulty,
        pve_source=source,
        pve_context=context or {},
    )
    session.add(duel)
    await session.flush()
    return duel


def _is_pve(duel: DuelSession) -> bool:
    """True when this is a PvE duel (NPC defender)."""
    return duel.defender_id is None or bool(duel.pve_source)


def _npc_state_snapshot(duel: DuelSession) -> dict:
    """Pack NPC vitals into the shape `pick_npc_action` expects."""
    return {
        "hp": float(duel.hp_b),
        "hp_max": float(duel.hp_b_max),
        "combat_qi": int(duel.combat_qi_b),
        "combat_qi_max": int(duel.combat_qi_b_max),
    }


def _player_state_snapshot(duel: DuelSession) -> dict:
    """Pack player (attacker) vitals — passed to npc_ai for v15.2 hooks."""
    return {
        "hp": float(duel.hp_a),
        "hp_max": float(duel.hp_a_max),
        "combat_qi": int(duel.combat_qi_a),
    }
