"""core/cavern_engine.py — Onda 5 (Fase 2): Cavernas Pessoais 洞府.

The cultivator's home inside the world (vision §4): ONE cavern per player
(PK = player_id), established on the continent they are standing on, that
"cultivates energy" while they are away — a CAPPED idle qi accrual (the
retention net; conservative by design, NEVER pay-to-win — DESIGN_DECISIONS
§8.4) — plus ONE Formação slot: a cultivation-natured Formação (qi_regen_boost
/ dao_fragment_chance) can hum in the cavern instead of on the body — the
player's CHOICE (Lei §1) — boosting the idle yield or granting Dao-fragment
comprehension on claim.

Numbers (env-tunable, owner reviews — §8.4):
  * rate/h    = CAVERN_QI_PER_HOUR_BASE + CAVERN_QI_PER_HOUR_PER_REALM·realm
                (defaults 8 + 4·realm → realm 5 ≈ 28 qi/h ≈ HALF an hour of
                natural online regen per ENTIRE 10h cap — truly conservative).
  * cap       = CAVERN_CAP_HOURS of accrual (default 10h) — idle, not a faucet.
  * establish = stones (500 + 100·realm) + T1 commons — materials+stones ONLY,
                NEVER jade (Lei §4).
Claim credits qi up to qi_capacity; a full tank is a DISCLOSED no-op (the
accrual is not silently burned — Lei §1); partial credit reports `truncated`.

Concurrency / idempotency: every WRITE assumes the CALLER holds ``player`` FOR
UPDATE and owns the commit (the ``claim_bounty`` pattern); the cavern row is
additionally locked here. The claim is idempotent BY TIMESTAMP: it pays
``last_claimed_at → now`` exactly once (the stamp only moves when qi is
credited); establish/set/clear re-runs are disclosed no-ops.
"""

import logging
import os
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from core.continent_engine import CONTINENT_META, DEFAULT_SPAWN_CONTINENT, is_valid_continent
from core.formation_engine import (
    _consume_one,
    _recipe_parts,
    get_formation,
    is_cavern_effect,
)
from core.game_logic import get_effective_qi_capacity
from database.models import FormationCatalog, PlayerCavern

logger = logging.getLogger(__name__)

# ── Tuning (env-overridable — conservative defaults, owner reviews §8.4) ───────
CAVERN_CAP_HOURS = float(os.getenv("CAVERN_CAP_HOURS", "10"))
CAVERN_QI_PER_HOUR_BASE = float(os.getenv("CAVERN_QI_PER_HOUR_BASE", "8"))
CAVERN_QI_PER_HOUR_PER_REALM = float(os.getenv("CAVERN_QI_PER_HOUR_PER_REALM", "4"))
CAVERN_COST_STONES_BASE = int(os.getenv("CAVERN_COST_STONES_BASE", "500"))
CAVERN_COST_STONES_PER_REALM = int(os.getenv("CAVERN_COST_STONES_PER_REALM", "100"))
# Dao-comprehension Formação in the slot: chance per claim of +1 fragment of a
# random law = min(CAVERN_DAO_CHANCE_CAP, CAVERN_DAO_CHANCE_PER_HOUR · boosted
# hours · effect_value). One fragment max per claim — conservative.
CAVERN_DAO_CHANCE_PER_HOUR = float(os.getenv("CAVERN_DAO_CHANCE_PER_HOUR", "0.08"))
CAVERN_DAO_CHANCE_CAP = float(os.getenv("CAVERN_DAO_CHANCE_CAP", "0.6"))

# Establish cost — materials are flat T1 commons (everyone can farm them in
# their first expeditions); the stone cost is what scales with realm.
CAVERN_COST_RECIPE = {
    "herbs": [{"herb_id": 1, "qty": 5}],
    "ores": [{"ore_id": 1, "qty": 5}],
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def establish_cost_stones(player) -> int:
    return CAVERN_COST_STONES_BASE + CAVERN_COST_STONES_PER_REALM * max(0, int(player.realm or 0))


def _rate_per_hour(player) -> float:
    return CAVERN_QI_PER_HOUR_BASE + CAVERN_QI_PER_HOUR_PER_REALM * max(0, int(player.realm or 0))


async def _get_cavern(session, player_id: int, *, for_update: bool = False):
    stmt = select(PlayerCavern).where(PlayerCavern.player_id == int(player_id))
    if for_update:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


def _accrual(cavern, player, now: datetime) -> dict:
    """Pure accrual math for the [last_claimed_at, now] window, capped at
    CAVERN_CAP_HOURS. The Formação boost applies only over the OVERLAP of the
    accrual window with [formation_set_at, formation_expires_at] (an expired
    Formação still pays for the hours it actually hummed — Lei §1)."""
    rate = _rate_per_hour(player)
    start = cavern.last_claimed_at or cavern.established_at or now
    hours = max(0.0, (now - start).total_seconds() / 3600.0)
    capped_hours = min(hours, CAVERN_CAP_HOURS)
    # The cap eats the OLDEST hours: the paid window is [now - capped, now].
    win_start = now - timedelta(hours=capped_hours)

    boosted_hours = 0.0
    f_mult = 1.0
    effect_type = None
    effect_value = 1.0
    if cavern.active_formation_id and cavern.formation_set_at and cavern.formation_expires_at:
        o_start = max(win_start, cavern.formation_set_at)
        o_end = min(now, cavern.formation_expires_at)
        boosted_hours = max(0.0, (o_end - o_start).total_seconds() / 3600.0)

    base_qi = rate * capped_hours
    bonus_qi = 0.0
    return {
        "rate_per_hour": rate,
        "hours": capped_hours,
        "boosted_hours": boosted_hours,
        "base_qi": base_qi,
        "bonus_qi": bonus_qi,  # filled by the caller once the Formação row is known
        "cap_hours": CAVERN_CAP_HOURS,
        "cap_qi": rate * CAVERN_CAP_HOURS,
        "at_cap": hours >= CAVERN_CAP_HOURS,
    }


async def _accrual_with_formation(session, cavern, player, now: datetime) -> tuple[dict, object]:
    """Accrual + the resolved active-Formação row (or None). qi_regen_boost
    multiplies the boosted overlap; dao_fragment_chance never adds qi (its
    payoff is the fragment roll at claim time)."""
    acc = _accrual(cavern, player, now)
    formation = None
    if cavern.active_formation_id:
        formation = await get_formation(session, cavern.active_formation_id)
    if formation is not None and formation.effect_type == "qi_regen_boost" and acc["boosted_hours"] > 0:
        acc["bonus_qi"] = acc["rate_per_hour"] * acc["boosted_hours"] * (float(formation.effect_value or 1.0) - 1.0)
    return acc, formation


def _formation_expired(cavern, now: datetime) -> bool:
    return bool(cavern.active_formation_id and
                (cavern.formation_expires_at is None or cavern.formation_expires_at <= now))


# ── Projection (READ) ──────────────────────────────────────────────────────────

async def project_cavern(session, player, *, lang: str = "pt") -> dict:
    """READ — the full cavern surface. No state change (an expired slot is
    REPORTED expired here and physically cleared on the next WRITE)."""
    now = _now()
    cavern = await _get_cavern(session, player.telegram_id)
    # EFFECTIVE cap (raw + equip qi_flat × tempering) — the regen tick fills qi
    # past the raw cap, so a raw-cap "full" gate locks tempered players out of
    # their own claim forever ([jogador]'s report, 2026-06-11).
    eff_qi_cap = await get_effective_qi_capacity(session, player)
    out = {
        "ok": True,
        "has_cavern": cavern is not None,
        "continent": getattr(player, "current_continent", None) or DEFAULT_SPAWN_CONTINENT,
        "qi": float(player.qi or 0),
        "qi_capacity": eff_qi_cap,
        "stones": int(player.spirit_stones or 0),
    }
    if cavern is None:
        cost = establish_cost_stones(player)
        _, r_herbs, r_ores = _recipe_parts(CAVERN_COST_RECIPE)
        from core.formation_engine import _material_names, _owned_materials
        herb_names, ore_names = await _material_names(
            session, [m["herb_id"] for m in r_herbs], [m["ore_id"] for m in r_ores])
        have_h, have_o = await _owned_materials(
            session, player.telegram_id,
            [m["herb_id"] for m in r_herbs], [m["ore_id"] for m in r_ores])
        mats = []
        affordable = int(player.spirit_stones or 0) >= cost
        for m in r_herbs:
            hid, qty = int(m["herb_id"]), int(m["qty"])
            have = int(have_h.get(hid, 0))
            mats.append({"kind": "herb", "id": hid, "name": herb_names.get(hid, f"Herb #{hid}"),
                         "qty": qty, "owned": have, "has_enough": have >= qty})
            affordable = affordable and have >= qty
        for m in r_ores:
            oid, qty = int(m["ore_id"]), int(m["qty"])
            have = int(have_o.get(oid, 0))
            mats.append({"kind": "ore", "id": oid, "name": ore_names.get(oid, f"Ore #{oid}"),
                         "qty": qty, "owned": have, "has_enough": have >= qty})
            affordable = affordable and have >= qty
        out.update({
            "establish_cost_stones": cost,
            "establish_materials": mats,
            "can_establish": affordable,
            "rate_per_hour_preview": _rate_per_hour(player),
            "cap_hours": CAVERN_CAP_HOURS,
        })
        return out

    acc, formation = await _accrual_with_formation(session, cavern, player, now)
    accrued = acc["base_qi"] + acc["bonus_qi"]
    space = max(0.0, eff_qi_cap - float(player.qi or 0))
    # Localized continent identity, server-resolved (the travel/plaza pattern —
    # the mini-app has no continent_* keys of its own).
    meta = CONTINENT_META.get(cavern.continent_key) or {}
    try:
        from core.i18n import t as i18n_t
        continent_name = i18n_t(lang, meta.get("name_key", "")) if meta.get("name_key") else cavern.continent_key
    except Exception:
        continent_name = cavern.continent_key
    out.update({
        "cavern_continent": cavern.continent_key,
        "cavern_continent_name": f"{meta.get('emoji', '')} {continent_name}".strip(),
        "established_at_ms": int(cavern.established_at.timestamp() * 1000) if cavern.established_at else None,
        "total_qi_claimed": int(cavern.total_qi_claimed or 0),
        "rate_per_hour": acc["rate_per_hour"],
        "cap_hours": acc["cap_hours"],
        "cap_qi": acc["cap_qi"],
        "accrued_qi": round(accrued, 1),
        "accrued_hours": round(acc["hours"], 2),
        "at_cap": acc["at_cap"],
        "claimable_qi": round(min(accrued, space), 1),
        "qi_full": space <= 0,
        "slot": None,
    })
    if formation is not None:
        expired = _formation_expired(cavern, now)
        out["slot"] = {
            "formation_id": int(formation.id),
            "key": formation.key,
            "emoji": formation.emoji,
            "name_key": f"formation_name_{formation.key}",
            "effect_type": formation.effect_type,
            "effect_key": f"formation_effect_{formation.effect_type}",
            "effect_value": float(formation.effect_value or 1.0),
            "expired": expired,
            "remaining_ms": (
                0 if expired or not cavern.formation_expires_at
                else max(0, int((cavern.formation_expires_at - now).total_seconds() * 1000))
            ),
        }
        if formation.effect_type == "dao_fragment_chance":
            out["slot"]["dao_chance"] = round(min(
                CAVERN_DAO_CHANCE_CAP,
                CAVERN_DAO_CHANCE_PER_HOUR * acc["boosted_hours"] * float(formation.effect_value or 1.0),
            ), 3)
    return out


# ── WRITE — establish ──────────────────────────────────────────────────────────

async def establish_cavern(session, player) -> dict:
    """WRITE — establish THE cavern (one per player) on the player's current
    continent. Costs stones + T1 commons (never jade). Caller holds ``player``
    FOR UPDATE and owns the commit. Re-running is a disclosed no-op."""
    existing = await _get_cavern(session, player.telegram_id, for_update=True)
    if existing is not None:
        return {"ok": False, "reason": "already_established",
                "cavern_continent": existing.continent_key}

    cost = establish_cost_stones(player)
    if int(player.spirit_stones or 0) < cost:
        return {"ok": False, "reason": "not_enough_stones", "cost_stones": cost,
                "stones": int(player.spirit_stones or 0)}

    # Materials — the shared, strictly all-or-nothing row-locked debit.
    from core.formation_engine import debit_materials
    _, r_herbs, r_ores = _recipe_parts(CAVERN_COST_RECIPE)
    if not await debit_materials(session, player.telegram_id, r_herbs, r_ores):
        return {"ok": False, "reason": "not_enough_materials"}

    player.spirit_stones = int(player.spirit_stones or 0) - cost

    continent = getattr(player, "current_continent", None)
    if not is_valid_continent(continent):
        continent = DEFAULT_SPAWN_CONTINENT
    now = _now()
    cavern = PlayerCavern(
        player_id=player.telegram_id,
        continent_key=continent,
        established_at=now,
        last_claimed_at=now,
    )
    session.add(cavern)
    return {"ok": True, "established": True, "cavern_continent": continent,
            "cost_stones": cost, "stones": int(player.spirit_stones or 0)}


# ── WRITE — claim the idle accrual ─────────────────────────────────────────────

async def _settle_accrual(session, cavern, player, now) -> dict:
    """The claim CORE, shared by claim_cavern AND every slot mutation
    (set/clear): credit the pending accrual (base + Formação bonus) up to
    qi_capacity, move ``last_claimed_at`` (only when something is credited),
    and roll the Dao-comprehension Formação. Because the boosted-hours bonus
    is overlap math over the LIVE slot timestamps, any code that nulls or
    overwrites those fields MUST settle through here first — otherwise hummed
    hours are silently burned (the adversarial-review HIGH). Returns
    {accrued, settled_qi, truncated, qi_capacity, dao_fragment?} — mutates
    only when credit ≥ 1."""
    acc, formation = await _accrual_with_formation(session, cavern, player, now)
    accrued = acc["base_qi"] + acc["bonus_qi"]
    # EFFECTIVE cap, never raw — see project_cavern ([jogador]'s report 2026-06-11).
    eff_qi_cap = await get_effective_qi_capacity(session, player)
    out = {"accrued": round(accrued, 1), "settled_qi": 0.0, "truncated": False,
           "qi_capacity": eff_qi_cap}
    if accrued < 1.0:
        return out
    space = max(0.0, eff_qi_cap - float(player.qi or 0))
    if space < 1.0:
        # Nothing (whole) fits — no mutation; the CALLER decides whether that
        # means "refuse and preserve" (claim) or "disclosed loss" (explicit
        # clear). The < 1.0 floor (mirror of the accrued floor above) matters:
        # a sub-1 space would mutate + move the stamp yet round to a
        # settled_qi of 0.0, so the claim would report "preserved" while the
        # whole window burned for pennies (adversarial-review finding).
        out["truncated"] = True
        return out

    credit = min(accrued, space)
    player.qi = float(player.qi or 0) + credit
    cavern.last_claimed_at = now
    cavern.total_qi_claimed = int(cavern.total_qi_claimed or 0) + int(credit)
    out["settled_qi"] = round(credit, 1)
    out["truncated"] = credit < accrued

    # Dao-comprehension roll — at most ONE fragment per settle (conservative).
    if formation is not None and formation.effect_type == "dao_fragment_chance" and acc["boosted_hours"] > 0:
        chance = min(CAVERN_DAO_CHANCE_CAP,
                     CAVERN_DAO_CHANCE_PER_HOUR * acc["boosted_hours"] * float(formation.effect_value or 1.0))
        rng = random.Random()
        if rng.random() < chance:
            frag = await _grant_random_dao_fragment(session, player.telegram_id, rng)
            if frag:
                out["dao_fragment"] = frag
    return out


async def claim_cavern(session, player) -> dict:
    """WRITE — bank the accrued idle qi (capped) + roll the Dao-comprehension
    Formação, if one hums in the slot. Idempotent BY TIMESTAMP: pays the
    ``last_claimed_at → now`` window exactly once — the stamp only moves when
    something is credited, so a full tank is a disclosed no-op that KEEPS the
    accrual (Lei §1: never silently burn). Caller holds ``player`` FOR UPDATE
    and owns the commit."""
    cavern = await _get_cavern(session, player.telegram_id, for_update=True)
    if cavern is None:
        return {"ok": False, "reason": "no_cavern"}

    now = _now()
    settle = await _settle_accrual(session, cavern, player, now)
    if settle["accrued"] < 1.0:
        return {"ok": False, "reason": "nothing_accrued", "accrued_qi": settle["accrued"]}
    if settle["settled_qi"] <= 0:
        # Full tank — refuse WITHOUT mutating; the accrual stays banked.
        return {"ok": False, "reason": "qi_full", "accrued_qi": settle["accrued"]}

    out = {"ok": True, "claimed": True, "claimed_qi": settle["settled_qi"],
           "truncated": settle["truncated"], "qi": float(player.qi or 0),
           "qi_capacity": settle["qi_capacity"]}
    if settle.get("dao_fragment"):
        out["dao_fragment"] = settle["dao_fragment"]

    # Lazy slot GC — a Formação that already expired is cleared on this WRITE
    # (its hours were just paid by the settle above — nothing is lost).
    if _formation_expired(cavern, now):
        cavern.active_formation_id = None
        cavern.formation_set_at = None
        cavern.formation_expires_at = None
        out["slot_expired"] = True
    return out


async def _grant_random_dao_fragment(session, player_id: int, rng) -> dict | None:
    """+1 fragment of a random law — the canonical PlayerDaoFragment upsert
    (dungeon_quest_engine pattern). Defensive: never raises."""
    try:
        from sqlalchemy import and_
        from database.models import DaoLawCatalog, PlayerDaoFragment
        laws = (await session.execute(select(DaoLawCatalog))).scalars().all()
        if not laws:
            return None
        law = laws[rng.randrange(len(laws))]
        frag = (await session.execute(
            select(PlayerDaoFragment).where(and_(
                PlayerDaoFragment.player_id == int(player_id),
                PlayerDaoFragment.dao_law_id == law.id,
            ))
        )).scalar_one_or_none()
        if frag and not frag.is_completed:
            frag.fragments_count = min(frag.fragments_count + 1, law.total_fragments)
            if frag.fragments_count >= law.total_fragments:
                frag.is_completed = True
        elif not frag:
            session.add(PlayerDaoFragment(
                player_id=int(player_id), dao_law_id=law.id, fragments_count=1))
        else:
            return None  # law already completed — quietly no fragment
        return {"law_id": int(law.id), "law_name": getattr(law, "name", None)}
    except Exception:
        logger.exception("cavern dao fragment grant failed (player=%s)", player_id)
        return None


# ── WRITE — the Formação slot ──────────────────────────────────────────────────

async def set_cavern_formation(session, player, formation_id: int) -> dict:
    """WRITE — consume 1 Formação from the pouch into the cavern slot (the
    "in the cavern" choice). Only cultivation-natured effects fit the slot
    (Lei §1 — combat/exploration Formações are body-only and say so). REFUSES
    while the slot is occupied by a LIVE Formação (anti-stack + idempotency:
    a double-tap gets a disclosed ``slot_occupied``). Every refusal path
    mutates NOTHING (the endpoints commit even ok:false results). On success
    the pending accrual is SETTLED via ``_settle_accrual`` BEFORE the slot
    timestamps are overwritten — an expired occupant's hummed hours are paid,
    never silently burned. Caller holds ``player`` FOR UPDATE + owns commit."""
    cavern = await _get_cavern(session, player.telegram_id, for_update=True)
    if cavern is None:
        return {"ok": False, "reason": "no_cavern"}

    f = await get_formation(session, formation_id)
    if f is None:
        return {"ok": False, "reason": "formation_not_found"}
    if not is_cavern_effect(f.effect_type):
        return {"ok": False, "reason": "not_cavern_type", "effect_type": f.effect_type}
    if int(player.realm or 0) < int(f.min_realm or 0):
        return {"ok": False, "reason": "realm_too_low", "min_realm": int(f.min_realm or 0)}

    now = _now()
    # An expired occupant counts as an EMPTY slot, but it is NOT cleared here —
    # no mutation may precede the last failure point (the pouch debit below).
    if cavern.active_formation_id and not _formation_expired(cavern, now):
        return {"ok": False, "reason": "slot_occupied",
                "remaining_ms": max(0, int((cavern.formation_expires_at - now).total_seconds() * 1000))
                if cavern.formation_expires_at else 0}

    if not await _consume_one(session, player.telegram_id, f.id):
        return {"ok": False, "reason": "not_owned"}

    # Pay the old window (incl. an expired occupant's boosted hours) BEFORE
    # overwriting the slot timestamps the overlap math depends on.
    settle = await _settle_accrual(session, cavern, player, now)

    cavern.active_formation_id = int(f.id)
    cavern.formation_set_at = now
    cavern.formation_expires_at = now + timedelta(minutes=max(1, int(f.duration_minutes or 60)))
    out = {"ok": True, "activated": "cavern", "formation_id": int(f.id), "key": f.key,
           "effect_type": f.effect_type, "effect_value": float(f.effect_value or 1.0),
           "duration_minutes": int(f.duration_minutes or 60)}
    if settle["settled_qi"] > 0:
        out["settled_qi"] = settle["settled_qi"]
    if settle["truncated"]:
        out["settle_truncated"] = True
    if settle.get("dao_fragment"):
        out["dao_fragment"] = settle["dao_fragment"]
    return out


async def clear_cavern_formation(session, player) -> dict:
    """WRITE — clear the slot. NO refund of the consumed Formação (disclosed —
    swapping mid-burn is a choice, not a free reroll), but the hours it
    already hummed ARE paid: the pending accrual is settled via
    ``_settle_accrual`` BEFORE the slot timestamps are nulled. Whatever can't
    fit a full tank is reported as ``settle_truncated`` — a disclosed
    consequence of the player's explicit clear, never a silent burn.
    Idempotent: an empty slot is a disclosed no-op."""
    cavern = await _get_cavern(session, player.telegram_id, for_update=True)
    if cavern is None:
        return {"ok": False, "reason": "no_cavern"}
    if not cavern.active_formation_id:
        return {"ok": True, "cleared": False, "empty": True}

    settle = await _settle_accrual(session, cavern, player, _now())
    cavern.active_formation_id = None
    cavern.formation_set_at = None
    cavern.formation_expires_at = None
    out = {"ok": True, "cleared": True}
    if settle["settled_qi"] > 0:
        out["settled_qi"] = settle["settled_qi"]
    if settle["truncated"]:
        out["settle_truncated"] = True
    if settle.get("dao_fragment"):
        out["dao_fragment"] = settle["dao_fragment"]
    return out
