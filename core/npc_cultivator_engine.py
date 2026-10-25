"""Onda 3 — NPC Cultivator engine (the world's autonomous population).

Today the world is empty: outside the 57 real players there is no one, and PvE
duels are ephemeral ghosts (archetypes generated on-the-fly in `npc_loadouts`,
nameless, forgotten when the fight ends). This engine gives the world a
PERSISTENT population: NPC cultivators that carry a continent + sect + path +
tier + karma, populate the realms ("the hidden monsters" of the Explorable
Realms vision), fill the 9 NPC sects, and appear in leaderboards — generated
from ANONYMIZED snapshots of real players' PUBLIC combat state, plus synthetic
bootstrap cultivators so the world is never born empty.

Design (mirrors the canonical engine pattern of `world_sects_engine` /
`continent_engine` / `path_engine` / `karma_engine`):
    * module-level tuning constants (engine, not DB — wipe-safe, Lei §5)
    * pure helpers + a fighter rehydrator that feeds the SAME v16.7 combat model
      (`core.combat_model`) every real duel uses — fair by construction
    * async DB accessors (session first, defensive try/except)
    * a snapshot tick + a first-arrival bootstrap, registered in the scheduler

Anonymization (Lei §5 + PII): a snapshot is a DERIVED, READ-ONLY copy of public
combat state. It NEVER stores a telegram_id, a real dao_name, or a live FK back
to the Player. `source_hash` is a one-way, non-reversible SHA-256 of the source
telegram_id, used ONLY to upsert one echo per source — never surfaced anywhere.
NPCs are ALWAYS rendered with an honest NPC chip (Lei §1), never disguised as a
real player.

Combat coherence (v16.4c Library rule): an echo of a real player may carry a
sect-exclusive signature art (ids 500-544) they legitimately equipped. Copying a
FOREIGN house's art onto an NPC of a different sect would be a lore break and a
scroll-economy leak — so the snapshot STRIPS any 500-544 tech that does not
belong to the NPC's own sect (and ALL of them for a sect-less rogue echo). NPC
techniques live only in JSONB (never PlayerTechnique / scrolls), so the live
scroll economy of the 57 paying players stays untouched.
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update

from database.models import NpcCultivator, Player, PlayerNPCCooldown
from core.world_sects_engine import (
    SECT_LIBRARY,
    SECT_RANKS,
    WORLD_SECT_KEYS,
    WORLD_SECT_META,
    get_native_continent_for_sect,
    get_rank_label_key,
    is_demonic_sect,
    is_valid_sect,
    project_sect_for_display,
)
from core.continent_engine import CONTINENT_KEYS, CONTINENT_META, is_valid_continent
from core.path_engine import PATH_META, is_demonic_path, is_valid_path

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Tuning constants (engine, not DB — wipe-safe; env-overridable for ops tuning)
# ══════════════════════════════════════════════════════════════════════════

# The single combat tuning lever. Applied at ENCOUNTER time (not baked into the
# stored snapshot) as a strike-only multiplier on the NPC's outgoing damage
# (combat_profile['faction_dmg']), so it never touches the NPC's HP/mitigation
# or the honest leaderboard power. < 1.0 ⇒ NPC hits softer ⇒ the player wins
# more. HARNESS-VALIDATED (tools/npc_cultivator_tuning.py against the live
# combat model): at 0.95 a power-matched ECHO lands a same-tier player in the
# ~50-60% band (the matcher picks a power-peer, so the player faces a fair fight,
# not an archetype hard-counter), SEED NPCs (no Dao apex) stay approachable for
# the early world. Echoes carry the source player's real Dao (honest "a real
# cultivator's Leis"). Owner may retune via env (Lei §6).
NPC_CULTIVATOR_POWER_SCALE = float(os.getenv("NPC_CULTIVATOR_POWER_SCALE", "0.95"))

# Separate cooldown from the regular NPC-hunt farm (last_npc_fight) so cultivator
# challenges never lock the 57 players out of their grind (Lei §5).
NPC_CULTIVATOR_COOLDOWN_SECONDS = int(os.getenv("NPC_CULTIVATOR_COOLDOWN_SECONDS", "600"))

# Modest win reward (there is a cooldown — this is a challenge, not a farm).
NPC_CHALLENGE_REWARD_BASE = 40
NPC_CHALLENGE_REWARD_PER_REALM = 12

# Bootstrap: fill each continent so the world is never born empty. Idempotent —
# only tops up to the target; never deletes.
BOOTSTRAP_PER_CONTINENT = int(os.getenv("NPC_CULTIVATOR_BOOTSTRAP_PER_CONTINENT", "6"))

# Snapshot tick: how many recently-active real players to echo per run.
SNAPSHOT_MAX_PER_TICK = int(os.getenv("NPC_CULTIVATOR_SNAPSHOT_PER_TICK", "20"))
SNAPSHOT_MIN_REALM = 1  # don't echo brand-new realm-0 players (nothing to fight)

# One-way hash salt for the idempotent echo key (non-reversible; never exposed).
_HASH_SALT = os.getenv("NPC_CULTIVATOR_HASH_SALT", "nivrael_onda3_echo")

# Realm proximity window for matching a challenger to a fair opponent.
ENCOUNTER_REALM_WINDOW = 1

# Owner override (2026-06-05, Lei §6): NPC cultivators are a FUTURE surface
# (Onda 4 Plaza), not for now — they swamped the live ranking with low-realm
# entries. Keep the persistent population in the DB (jobs keep it fresh for
# Onda 4) but do NOT surface them in the player-facing leaderboard yet. Flip to
# "1" when the Plaza ships. Default OFF.
NPC_LEADERBOARD_ENABLED = os.getenv("NPC_LEADERBOARD_ENABLED", "0") == "1"

# Sect-exclusive tech ids (500-544) — for the foreign-art strip rule.
_ALL_SECT_TECH_IDS: set[int] = {
    e["tech_id"] for techs in SECT_LIBRARY.values() for e in techs
}


# ══════════════════════════════════════════════════════════════════════════
# Anonymized name generation (never the source player's real dao_name — Lei §5)
# ══════════════════════════════════════════════════════════════════════════

_SURNAMES = (
    "Bai", "Han", "Su", "Mu", "Lin", "Yun", "Xiao", "Chen", "Jiang", "Feng",
    "Gu", "Ye", "Shen", "Long", "Qin", "Zhao", "Wei", "Tang", "Luo", "Xu",
    "Duan", "Murong", "Ximen", "Nangong", "Ouyang", "Yan", "Zhou", "Lei",
)
_GIVEN = (
    "Wuji", "Lingyun", "Tianhe", "Xuanzhi", "Yumo", "Chengfeng", "Zhanyue",
    "Beixuan", "Qianyu", "Hanshuang", "Jianxin", "Yuhan", "Mochou", "Wangchen",
    "Lieyang", "Canglan", "Feihong", "Yinxue", "Shaoyu", "Tianci", "Wuque",
    "Bingyan", "Haoran", "Zixuan", "Lanyin", "Zhankong", "Yuanji", "Wangshu",
)


def generate_npc_name(rng: random.Random | None = None) -> str:
    """A plausible two-part cultivator name. Cosmetic, anonymized, ≤48 chars."""
    r = rng or random
    return f"{r.choice(_SURNAMES)} {r.choice(_GIVEN)}"


# ══════════════════════════════════════════════════════════════════════════
# Pure helpers
# ══════════════════════════════════════════════════════════════════════════

def _clamp_karma(value: Any) -> int:
    try:
        return max(-1000, min(1000, int(value or 0)))
    except (TypeError, ValueError):
        return 0


def _source_hash(telegram_id: int) -> str:
    """One-way, non-reversible echo key. NEVER exposed to any surface."""
    return hashlib.sha256(f"{_HASH_SALT}:{telegram_id}".encode("utf-8")).hexdigest()[:64]


def _sect_allowed_tech_ids(sect_id: str | None) -> set[int]:
    """The sect-exclusive tech ids an NPC of ``sect_id`` may legitimately carry."""
    return {e["tech_id"] for e in SECT_LIBRARY.get(sect_id or "", [])}


def _strip_foreign_sect_techs(techniques: list[dict], sect_id: str | None) -> list[dict]:
    """Drop any 500-544 signature art that is not this NPC's own house's (v16.4c).

    An echo of a real player may have equipped a sect art; copying a foreign
    house's art onto an NPC of a different sect is a lore break + a scroll-economy
    leak. Keep ordinary techs (sect_key NULL ⇒ id outside 500-544) untouched.
    """
    allowed = _sect_allowed_tech_ids(sect_id)
    out: list[dict] = []
    for t in techniques or []:
        try:
            tid = int(t.get("id", 0))
        except (TypeError, ValueError):
            continue
        if tid in _ALL_SECT_TECH_IDS and tid not in allowed:
            continue  # foreign house art — strip
        out.append(t)
    return out


def _npc_qi_pool(realm: int) -> int:
    """Decoupled, realm-scaled qi pool so the NPC can afford its kit across a
    duel (mirrors the 2026-06-02 NPC qi-starvation bugfix in duel_engine)."""
    return max(200, int(150 * (int(realm or 0) + 1)))


# ══════════════════════════════════════════════════════════════════════════
# Fighter rehydration — feed the SAME v16.7 combat model every real duel uses
# ══════════════════════════════════════════════════════════════════════════

def rehydrate_npc_fighter(npc: NpcCultivator) -> dict:
    """Rebuild the fighter_b dict (start_duel_pve / _resolve_round contract) from
    a stored snapshot. telegram_id=0 sentinel + is_npc=True keep every PvE branch
    (winner sentinel, HP-drain skip, tiebreak neutral score) working unchanged.

    The NPC_CULTIVATOR_POWER_SCALE tuning lever is applied HERE (not baked into
    the row) as a strike-only damage multiplier, so it never touches HP/mitigation
    or the honest leaderboard power and can be re-tuned without regenerating NPCs.
    """
    fb = dict(npc.loadout or {})
    # MV-8 — o `loadout` de uma row SEED também guarda o estado do jiānghú
    # (`jh_last`/`jh_hunt`/`jh_scale`), e este dict é copiado INTEIRO para
    # `duel_sessions.fighter_b`. Tirar as chaves aqui garante que nada do
    # mundo vivo contamina o contrato do combate — e, com a flag OFF, as
    # chaves nunca existem, então este bloco é um no-op byte-idêntico.
    for _jh_key in ("jh_last", "jh_hunt", "jh_scale"):
        fb.pop(_jh_key, None)
    fb["telegram_id"] = 0
    fb["is_npc"] = True
    fb.setdefault("name", npc.name)
    fb.setdefault("dao_name", npc.name)
    fb["realm"] = int(npc.realm or fb.get("realm", 0) or 0)
    fb.setdefault("sub_layer", int(npc.sub_layer or 1))
    fb.setdefault("armor_bonus", 0.0)
    fb.setdefault("defense_boost", 1.0)
    fb.setdefault("techniques", [])
    fb["archetype"] = "npc_cultivator"
    fb.setdefault("difficulty", "normal")

    prof = dict(fb.get("combat_profile") or {})
    if not fb.get("qi_capacity"):
        fb["qi_capacity"] = _npc_qi_pool(fb["realm"])
    # Strike-only tuning lever (does NOT touch eff_hp / mitigation).
    if NPC_CULTIVATOR_POWER_SCALE != 1.0 and prof:
        prof["faction_dmg"] = float(prof.get("faction_dmg", 1.0)) * NPC_CULTIVATOR_POWER_SCALE
    # MV-8 — a escala do feudo (o DENTE da vendeta): quem venceu dívidas de
    # sangue bate mais forte, quem perdeu bate menos. MESMO lever strike-only
    # acima, clampado em ±12%, e DISCLOSED no cartão do NPC antes do tap
    # (Lei §1). Flag OFF → 1.0 sem query ⇒ o duelo dos 57 é byte-idêntico.
    try:
        from core.jianghu_engine import jianghu_strike_mult
        _jh_mult = jianghu_strike_mult(npc)
        if _jh_mult != 1.0 and prof:
            prof["faction_dmg"] = float(prof.get("faction_dmg", 1.0)) * _jh_mult
    except Exception:
        logger.debug("rehydrate_npc_fighter: jianghu scale failed (npc=%s)",
                     getattr(npc, "id", None), exc_info=True)
    fb["combat_profile"] = prof
    if not fb.get("hp"):
        fb["hp"] = float(prof.get("eff_hp", 500.0) or 500.0)
    if not fb.get("bp"):
        fb["bp"] = int(npc.power or 50)
    return fb


# ══════════════════════════════════════════════════════════════════════════
# Snapshot generation — anonymized echo of a real player's public combat state
# ══════════════════════════════════════════════════════════════════════════

async def _build_public_fighter(session, player: Player) -> dict | None:
    """Build the player's combat fighter dict (the public state to anonymize),
    reusing the exact per-duel snapshot path so the echo fights identically."""
    try:
        from core.duel_engine import _build_duel_fighter
        return await _build_duel_fighter(session, player)
    except Exception:
        logger.debug("npc snapshot: _build_duel_fighter failed for %s", player.telegram_id, exc_info=True)
        return None


def _anonymize_fighter(fighter: dict, name: str, realm: int, sect_id: str | None) -> dict:
    """Turn a real player's fighter dict into an anonymized NPC loadout dict.

    Strips ALL identity (telegram_id→0, name/dao_name→generated), drops intent
    aura (NPCs keep the existing PvE fairness baseline — a player's Intent is a
    real edge), and removes foreign sect arts (v16.4c). Keeps the honest
    combat_profile (incl. the source's real Dao apex) so the echo fights like
    the real cultivator did.
    """
    prof = dict(fighter.get("combat_profile") or {})
    techniques = _strip_foreign_sect_techs(list(fighter.get("techniques") or []), sect_id)
    return {
        "telegram_id": 0,
        "name": name,
        "dao_name": name,
        "is_npc": True,
        "bp": int(fighter.get("bp", 50) or 50),
        "hp": float(fighter.get("hp", 500.0) or 500.0),
        "qi_capacity": _npc_qi_pool(realm),
        "armor_bonus": float(fighter.get("armor_bonus", 0.0) or 0.0),
        "realm": int(realm),
        "sub_layer": int(fighter.get("sub_layer", 1) or 1),
        "techniques": techniques,
        "defense_boost": float(fighter.get("defense_boost", 1.0) or 1.0),
        "celestial_hp_regen_pct": float(fighter.get("celestial_hp_regen_pct", 0.0) or 0.0),
        "combat_profile": prof,
        "intent_ranks": {},  # no Intent aura — keep the PvE fairness baseline
        "archetype": "npc_cultivator",
        "difficulty": "normal",
    }


async def snapshot_player_to_npc(session, player: Player) -> NpcCultivator | None:
    """Create/refresh ONE anonymized echo of a real player. Idempotent on
    source_hash (one echo per source). Defensive — never raises. Returns the row
    or None (skipped/failed)."""
    try:
        if player is None or bool(getattr(player, "shadow_mode", False)):
            return None  # respect the leaderboard privacy filter
        realm = int(player.realm or 0)
        if realm < SNAPSHOT_MIN_REALM:
            return None

        fighter = await _build_public_fighter(session, player)
        if not fighter or not fighter.get("combat_profile"):
            return None

        sect_id = player.sect_id if is_valid_sect(player.sect_id) else None
        sect_rank = player.sect_rank if (sect_id and player.sect_rank in SECT_RANKS) else None
        path = player.path if is_valid_path(player.path) else None
        continent = player.current_continent if is_valid_continent(player.current_continent) else "linghe"
        karma = _clamp_karma(player.karma)
        name = generate_npc_name()

        loadout = _anonymize_fighter(fighter, name, realm, sect_id)
        power = int(loadout.get("bp", 50) or 50)
        src = _source_hash(int(player.telegram_id))
        now = datetime.now(timezone.utc)

        def _assign(r: NpcCultivator) -> None:
            r.name = name
            r.realm = realm
            r.sub_layer = int(loadout.get("sub_layer", 1))
            r.continent_key = continent
            r.sect_id = sect_id
            r.sect_rank = sect_rank
            r.path = path
            r.karma = karma
            r.power = power
            r.loadout = loadout
            r.status = "active"
            r.updated_at = now

        existing = (await session.execute(
            select(NpcCultivator).where(NpcCultivator.source_hash == src).with_for_update()
        )).scalar_one_or_none()
        if existing is not None:
            _assign(existing)
            return existing

        row = NpcCultivator(origin="echo", source_hash=src, generated_at=now)
        _assign(row)
        # SAVEPOINT the INSERT so a unique-violation race on source_hash (a second
        # concurrent writer) rolls back only this row, never the whole batch.
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
            return row
        except Exception:
            other = (await session.execute(
                select(NpcCultivator).where(NpcCultivator.source_hash == src)
            )).scalar_one_or_none()
            if other is not None:
                _assign(other)
            return other
    except Exception:
        logger.exception("snapshot_player_to_npc failed for player_id=%s",
                         getattr(player, "telegram_id", None))
        return None


# ══════════════════════════════════════════════════════════════════════════
# Synthetic bootstrap cultivators — so the world is never born empty
# ══════════════════════════════════════════════════════════════════════════

def _archetype_for_realm(realm: int) -> str:
    if realm >= 7:
        return "boss"
    if realm >= 5:
        return "demon"
    if realm >= 2:
        return "sect_disciple"
    return "bandit"


def _materialize_techniques(tech_ids: list[int], realm: int, grade_mult: float = 1.2) -> list[dict]:
    """Index the in-memory catalog by id and build pick_npc_action-shaped tech
    dicts (mirror of duel_engine._build_npc_techniques_from_loadout). Always
    guarantees ≥1 tech so the AI can act."""
    from database.seeds.combat_seeds import TECHNIQUES as _CATALOG, QI_COSTS
    by_id = {int(t["id"]): t for t in _CATALOG}
    out: list[dict] = []
    for tid in tech_ids:
        spec = by_id.get(int(tid))
        if not spec:
            continue
        if int(spec.get("req_realm", 0)) > realm + 1:
            continue
        out.append({
            "id": int(spec["id"]), "name": spec.get("name") or "?",
            "emoji": spec.get("emoji") or "⚔️", "effect_type": spec.get("effect_type"),
            "effect_value": float(spec.get("effect_value", 0.0)),
            "effect_round": int(spec.get("effect_round", 0)),
            "qi_cost": int(QI_COSTS.get(int(spec["id"]), 10)),
            "mastery_level": 1, "grade": "common", "grade_mult": grade_mult,
        })
    if not out:
        spec = by_id.get(1)
        if spec:
            out.append({
                "id": 1, "name": spec.get("name") or "Thunder Step",
                "emoji": spec.get("emoji") or "⚡", "effect_type": spec.get("effect_type"),
                "effect_value": float(spec.get("effect_value", 0.0)),
                "effect_round": int(spec.get("effect_round", 0)),
                "qi_cost": int(QI_COSTS.get(1, 10)),
                "mastery_level": 1, "grade": "common", "grade_mult": grade_mult,
            })
    return out


def _build_seed_loadout(realm: int, sect_id: str | None, sect_rank: str | None,
                        name: str, rng: random.Random) -> tuple[dict, int]:
    """Build a synthetic NPC fighter dict (+display bp) from scratch via the
    shared combat model. Seeds carry NO Dao (dao_index 0) — same baseline as the
    existing ephemeral NPCs. Returns (loadout, power)."""
    from core import combat_model as cm
    from core.npc_loadouts import NPC_ARCHETYPES, DIFFICULTY_GRADE_MULT

    archetype = _archetype_for_realm(realm)
    arch = NPC_ARCHETYPES.get(archetype) or NPC_ARCHETYPES["bandit"]
    tier = int(realm)
    base_soul = 50 * (tier + 1) * float(arch["bp_mult"]) * rng.uniform(0.9, 1.1)
    base_qi = 50 * (tier + 1) * float(arch["qi_capacity_mult"]) * rng.uniform(0.9, 1.1)
    base_bp = 450 * (tier + 1) * float(arch["bp_mult"]) * rng.uniform(0.9, 1.1)
    prof = cm.make_profile(
        soul=base_soul, qi=base_qi, bp=base_bp, realm=tier,
        tempering_hp=float(arch["hp_mult"]), perception=30 * (tier + 1),
    )
    bp = max(50, int(cm.strike_value(base_soul, base_bp, base_qi, tier)))
    hp = max(500.0, prof["eff_hp"])

    tech_ids = list(arch["technique_ids"])
    # Give a sect member its house's rank-appropriate signature art (safe — JSONB
    # only, never a scroll; sect-matched so no foreign-art leak).
    if sect_id and is_valid_sect(sect_id):
        from core.world_sects_engine import rank_index
        cap = rank_index(sect_rank)
        sig = [e for e in SECT_LIBRARY.get(sect_id, []) if SECT_RANKS.index(e["rank"]) <= cap]
        if sig:
            tech_ids.append(rng.choice(sig)["tech_id"])
    techniques = _materialize_techniques(tech_ids, realm, grade_mult=DIFFICULTY_GRADE_MULT.get("normal", 1.2))

    loadout = {
        "telegram_id": 0, "name": name, "dao_name": name, "is_npc": True,
        "bp": bp, "hp": hp, "qi_capacity": _npc_qi_pool(realm),
        "armor_bonus": 0.0, "realm": tier, "sub_layer": rng.randint(1, 9),
        "techniques": techniques, "defense_boost": 1.0,
        "combat_profile": prof, "intent_ranks": {},
        "archetype": "npc_cultivator", "difficulty": "normal",
    }
    return loadout, bp


def _seed_karma_for_path(path: str | None, rng: random.Random) -> int:
    if path == "demonic":
        return _clamp_karma(-rng.randint(120, 620))
    if path == "righteous":
        return _clamp_karma(rng.randint(120, 620))
    return _clamp_karma(rng.randint(-90, 90))


def _make_seed_npc(continent: str, rng: random.Random, *, realm_cap: int = 8) -> NpcCultivator:
    """Compose one synthetic, world-consistent NPC for a continent. ``realm_cap``
    clamps the seed realm to the live player population's ceiling so a synthetic
    NPC never sits atop the cultivation ladder above every real player (Lei §1)."""
    # Pick a sect native to this continent (or rogue ~25% of the time).
    native_sects = [k for k in WORLD_SECT_KEYS if get_native_continent_for_sect(k) == continent]
    if continent == "moyu":
        sect_id = "abyssal_depths"  # only the demonic house calls Mòyǔ home
        path = "demonic"
    elif native_sects and rng.random() > 0.25:
        sect_id = rng.choice(native_sects)
        path = "demonic" if is_demonic_sect(sect_id) else "righteous"
    else:
        sect_id = None
        path = rng.choice(["righteous", "rogue", "rogue"])  # rogue-leaning loners

    # Realm band, clamped to the live ceiling (never above real players).
    realm = rng.randint(1, max(1, int(realm_cap)))
    sect_rank = None
    if sect_id:
        from core.world_sects_engine import eligible_rank
        sect_rank = eligible_rank(rng.randint(0, 1600), realm)
    name = generate_npc_name(rng)
    loadout, power = _build_seed_loadout(realm, sect_id, sect_rank, name, rng)
    now = datetime.now(timezone.utc)
    return NpcCultivator(
        name=name, realm=realm, sub_layer=int(loadout.get("sub_layer", 1)),
        continent_key=continent, sect_id=sect_id, sect_rank=sect_rank,
        path=path, karma=_seed_karma_for_path(path, rng), power=power,
        loadout=loadout, status="active", origin="seed", source_hash=None,
        generated_at=now, updated_at=now,
    )


async def run_npc_cultivators_bootstrap(session) -> dict[str, int]:
    """Top each continent up to BOOTSTRAP_PER_CONTINENT active NPCs. Idempotent
    (only fills the deficit; never deletes). Tolerates an empty DB. Runs once at
    startup (db.py) after the world sects seed. Returns {continent: created}."""
    created: dict[str, int] = {}
    try:
        rng = random.Random()  # cosmetic; not resume-sensitive
        rows = (await session.execute(
            select(NpcCultivator.continent_key, func.count())
            .where(NpcCultivator.status == "active")
            .group_by(NpcCultivator.continent_key)
        )).all()
        counts = {c: int(n) for c, n in rows}
        # Clamp seed realm to the live player ceiling so a synthetic NPC never
        # tops the cultivation leaderboard above every real player (Lei §1). On a
        # fresh/empty DB (no players) default to a modest mid-realm cap.
        max_player_realm = (await session.execute(
            select(func.max(Player.realm)).where(Player.shadow_mode == False)  # noqa: E712
        )).scalar()
        realm_cap = max(1, min(8, int(max_player_realm))) if max_player_realm is not None else 5
        for continent in CONTINENT_KEYS:
            have = counts.get(continent, 0)
            deficit = max(0, BOOTSTRAP_PER_CONTINENT - have)
            for _ in range(deficit):
                session.add(_make_seed_npc(continent, rng, realm_cap=realm_cap))
            if deficit:
                created[continent] = deficit
        if created:
            await session.commit()
            logger.info("npc_cultivators bootstrap created %s", created)
    except Exception:
        logger.exception("run_npc_cultivators_bootstrap failed")
        try:
            await session.rollback()
        except Exception:
            pass
    return created


async def snapshot_recent_players(session, *, limit: int = SNAPSHOT_MAX_PER_TICK) -> int:
    """Echo the N most recently-active, non-shadow players into NPC cultivators.
    Idempotent per source (upsert on source_hash). Returns the count snapshotted."""
    count = 0
    try:
        players = (await session.execute(
            select(Player)
            .where(Player.shadow_mode == False, Player.realm >= SNAPSHOT_MIN_REALM)  # noqa: E712
            .order_by(Player.last_online.desc())
            .limit(int(limit))
        )).scalars().all()
        for p in players:
            row = await snapshot_player_to_npc(session, p)
            if row is not None:
                count += 1
        await session.commit()
    except Exception:
        logger.exception("snapshot_recent_players failed")
        try:
            await session.rollback()
        except Exception:
            pass
    return count


async def retire_shadow_echoes(session) -> int:
    """Retire (status='fallen') echoes whose SOURCE player has since enabled
    shadow_mode — honoring the leaderboard-privacy opt-out for the echo population
    too (a player who goes dark shouldn't keep an anonymized combat ghost roaming
    the world). Idempotent, best-effort. Returns the count retired."""
    try:
        shadow_ids = (await session.execute(
            select(Player.telegram_id).where(Player.shadow_mode == True)  # noqa: E712
        )).scalars().all()
        if not shadow_ids:
            return 0
        hashes = [_source_hash(int(pid)) for pid in shadow_ids]
        res = await session.execute(
            update(NpcCultivator)
            .where(NpcCultivator.source_hash.in_(hashes), NpcCultivator.status == "active")
            .values(status="fallen", updated_at=datetime.now(timezone.utc))
        )
        await session.commit()
        n = res.rowcount or 0
        if n:
            logger.info("retire_shadow_echoes: retired %s echo(es)", n)
        return n
    except Exception:
        logger.exception("retire_shadow_echoes failed")
        try:
            await session.rollback()
        except Exception:
            pass
        return 0


# ══════════════════════════════════════════════════════════════════════════
# Encounter selection + cooldown
# ══════════════════════════════════════════════════════════════════════════

async def get_npc_cultivator(session, npc_id: int) -> NpcCultivator | None:
    try:
        return (await session.execute(
            select(NpcCultivator).where(NpcCultivator.id == int(npc_id))
        )).scalar_one_or_none()
    except Exception:
        logger.debug("get_npc_cultivator failed id=%s", npc_id, exc_info=True)
        return None


async def pick_encounter_npc(session, player: Player, *, window: int = ENCOUNTER_REALM_WINDOW) -> NpcCultivator | None:
    """Pick a FAIR opponent: an active NPC within ±window realms, preferring the
    player's continent. Ranks by REALM proximity (scale-free) and biases AWAY from
    higher-realm NPCs so the player is never matched into an above-tier wall — we
    deliberately do NOT compare absolute `power` because echo power (total BP),
    seed power (strike value) and the player's column are on different scales. A
    random tiebreak keeps it from always being the same face."""
    try:
        realm = int(player.realm or 0)
        continent = player.current_continent if is_valid_continent(player.current_continent) else None
        base = select(NpcCultivator).where(
            NpcCultivator.status == "active",
            NpcCultivator.realm >= max(0, realm - window),
            NpcCultivator.realm <= realm + window,
        )
        # Prefer same continent; fall back to any continent if none nearby.
        candidates: list[NpcCultivator] = []
        if continent:
            candidates = (await session.execute(
                base.where(NpcCultivator.continent_key == continent).limit(40)
            )).scalars().all()
        if not candidates:
            candidates = (await session.execute(base.limit(40))).scalars().all()
        if not candidates:
            return None
        random.shuffle(candidates)  # random tiebreak within equal realm buckets
        candidates.sort(key=lambda n: (
            1 if int(n.realm or 0) > realm else 0,   # avoid stronger-realm (wall) first
            abs(int(n.realm or 0) - realm),          # then closest realm
        ))
        return candidates[0]
    except Exception:
        logger.debug("pick_encounter_npc failed for %s", getattr(player, "telegram_id", None), exc_info=True)
        return None


def cultivator_cooldown_remaining(cd: PlayerNPCCooldown | None, now: datetime | None = None) -> int:
    """Seconds remaining on the separate cultivator-challenge cooldown (0 = ready)."""
    if cd is None or cd.last_cultivator_fight is None:
        return 0
    now = now or datetime.now(timezone.utc)
    elapsed = (now - cd.last_cultivator_fight).total_seconds()
    return max(0, int(NPC_CULTIVATOR_COOLDOWN_SECONDS - elapsed))


# ══════════════════════════════════════════════════════════════════════════
# Settle resolver (called from pve_duel_settle) + post-duel moral fork (karma)
# ══════════════════════════════════════════════════════════════════════════

async def resolve_npc_cultivator_from_duel(session, duel, player: Player, won: bool) -> dict[str, Any]:
    """Settle-hook resolver for pve_source='npc_cultivator'. Grants a modest win
    reward and flags whether a spare/execute moral choice is offered (only on a
    win). Karma is NOT applied here (the moral choice is an explicit post-duel
    player decision — see apply_combat_moral_choice). Idempotency rides on the
    engine-level pve_settled marker; this only mutates the player on a win."""
    ctx = duel.pve_context or {}
    npc_id = ctx.get("npc_id")
    payload: dict[str, Any] = {"npc_id": npc_id, "won": bool(won), "offer_moral_choice": bool(won)}
    if won:
        realm = int(player.realm or 0)
        reward = NPC_CHALLENGE_REWARD_BASE + NPC_CHALLENGE_REWARD_PER_REALM * realm
        reward = int(reward * random.uniform(0.85, 1.15))
        player.spirit_stones = int(player.spirit_stones or 0) + reward
        payload["reward_stones"] = reward
    # MV-6 — reputação + O RIVAL: gancho ÚNICO pós-settle (nascimento 8% ·
    # derrota do rival · misericórdia na derrota SUA · +1 rep local com cap
    # diário). Aditivo + gated (flag OFF → None sem query — os 57 intactos);
    # o player já está FOR UPDATE na sessão do settle. Nunca altera o duelo.
    try:
        from core.reputation_engine import on_npc_duel_settled
        _mv6 = await on_npc_duel_settled(session, player, npc_id, bool(won))
        if _mv6:
            payload["mv6"] = _mv6
    except Exception:
        logger.exception("resolve_npc_cultivator_from_duel: mv6 hook failed (duel=%s)", duel.id)
    return payload


async def apply_combat_moral_choice(session, duel_id, player_id: int, outcome: str) -> dict[str, Any]:
    """Apply the post-duel spare/execute karma choice (reuses the Karmic
    Crossroads moral-fork pattern). Idempotent per duel (gated on a
    pve_context['moral_resolved'] marker). Only valid on a duel the player WON
    vs an npc_cultivator. Returns {ok, outcome, karma:{...}} / {ok:False, reason}."""
    from sqlalchemy.orm.attributes import flag_modified
    from database.models import DuelSession

    outcome = (outcome or "").lower()
    if outcome not in ("spare", "execute"):
        return {"ok": False, "reason": "invalid_outcome"}

    duel = (await session.execute(
        select(DuelSession).where(DuelSession.id == duel_id).with_for_update()
    )).scalar_one_or_none()
    if duel is None:
        return {"ok": False, "reason": "duel_not_found"}
    # Onda 5 — the same spare/execute fork is offered after an exploration
    # Hidden-Monster win, so accept both sources (a Hidden Monster IS an NPC
    # cultivator; the karma event is identical). The win-check below still gates.
    # MV-8 — a emboscada do jiānghú também é uma vitória sobre um NpcCultivator
    # e também oferece o fork (o `offer_moral_choice` do settle dela diz que
    # sim). Sem a fonte AQUI o fork nasceria órfão: o botão apareceria e o
    # servidor responderia "not_your_duel".
    if duel.attacker_id != player_id or duel.pve_source not in (
            "npc_cultivator", "exploration", "jianghu_ambush"):
        return {"ok": False, "reason": "not_your_duel"}
    won = (duel.winner_id == duel.attacker_id and duel.state == "finished")
    if not won:
        return {"ok": False, "reason": "not_won"}
    ctx = dict(duel.pve_context or {})
    if ctx.get("moral_resolved"):
        return {"ok": False, "reason": "already_resolved", "outcome": ctx.get("moral_resolved")}

    event = "combat_spare" if outcome == "spare" else "combat_execute"
    karma_result: dict[str, Any] = {}
    try:
        from core.karma_engine import apply_karma
        karma_result = await apply_karma(
            session, player_id, event,
            # A fonte tem de ser a REAL, não a literal. Desde a Onda 5 este fork
            # também atende `exploration` (o Monstro Escondido), mas o registro
            # de karma gravava "npc_cultivator" HARDCODED — ou seja, todo fork
            # moral de exploração mentia sobre a própria origem no karma_log, e
            # nenhuma leitura conseguia distinguir os dois. (MV-8 precisa dessa
            # distinção para o pacer da emboscada; a correção vale por si.)
            metadata={"npc_id": ctx.get("npc_id"), "pve_source": duel.pve_source, "duel_id": str(duel_id)},
        )
    except Exception:
        logger.exception("apply_combat_moral_choice: apply_karma failed (player=%s, duel=%s)", player_id, duel_id)

    ctx["moral_resolved"] = outcome
    duel.pve_context = ctx
    flag_modified(duel, "pve_context")
    return {"ok": True, "outcome": outcome, "karma": karma_result}


# ══════════════════════════════════════════════════════════════════════════
# Display projections — honest NPC chip / profile / leaderboard / population
# ══════════════════════════════════════════════════════════════════════════

def _path_chip(path: str | None, lang: str) -> dict | None:
    if not is_valid_path(path):
        return None
    from core.i18n import t as i18n_t
    meta = PATH_META[path]
    return {"key": path, "emoji": meta["emoji"], "name": i18n_t(lang, meta["name_key"])}


def _continent_chip(continent: str | None, lang: str) -> dict | None:
    if not is_valid_continent(continent):
        return None
    from core.i18n import t as i18n_t
    meta = CONTINENT_META[continent]
    return {"key": continent, "emoji": meta["emoji"], "name": i18n_t(lang, meta["name_key"])}


def project_npc_for_profile(npc: NpcCultivator, lang: str = "pt", *, realm_label=None,
                            viewer_karma: int | None = None) -> dict[str, Any]:
    """An honest NPC 'profile' (ProfileModal): identity chips + power. ALWAYS
    flagged is_npc (Lei §1) — never disguised as a real player. ``realm_label`` is
    an optional ``(realm) -> (name, emoji)`` callable (the caller passes
    webserver._realm_label so the engine stays free of a webserver import).

    Track A item 4 — when ``viewer_karma`` is given (the looking player's karma),
    the profile carries a ``reaction`` block: how this NPC regards the viewer,
    crossed from (npc_karma × player_karma). Pure narrative, zero mechanics —
    the NPC is never mutated (Lei §5). Surfaces that have no viewer (leaderboard)
    simply omit the kwarg."""
    from core.karma_engine import project_karma_for_display
    realm = int(npc.realm or 0)
    realm_name, realm_emoji = (None, "🌀")
    if realm_label is not None:
        try:
            realm_name, realm_emoji = realm_label(realm)
        except Exception:
            pass
    out: dict[str, Any] = {
        "is_npc": True,
        "npc_id": int(npc.id),
        "name": npc.name,
        "realm": realm,
        "realm_name": realm_name,
        "realm_emoji": realm_emoji,
        "sub_layer": int(npc.sub_layer or 1),
        "power": int(npc.power or 0),
        "status": npc.status,
        "path": _path_chip(npc.path, lang),
        "continent": _continent_chip(npc.continent_key, lang),
        "sect": project_sect_for_display(npc.sect_id, lang) if npc.sect_id else None,
        "sect_rank_key": get_rank_label_key(npc.sect_rank) if npc.sect_id else None,
        "karma": project_karma_for_display(_clamp_karma(npc.karma), lang),
    }
    # Track A (B4) — Lifespan flavor: a deterministic, no-PII age line (seeded by
    # the stable DB id). Pure projection — the NPC never ages or dies this wave;
    # real NPC death + sect vengeance are wipe-bound (Lei §5). `None` = ageless.
    try:
        from core.lifespan_engine import derive_npc_age
        out["age"] = derive_npc_age(int(npc.id), realm)
    except Exception:
        logger.debug("project_npc_for_profile: age derive failed (npc=%s)", npc.id, exc_info=True)
    # Track A (B4) — Mind Sea flavor: a deterministic, no-PII depth tier from the
    # NPC's realm (the echo row carries no soul/perception). Pure projection — zero
    # mechanics, the NPC is never mutated (Lei §5).
    try:
        from core.mind_sea_engine import npc_mind_sea_tier
        out["mind_sea"] = npc_mind_sea_tier(realm)
    except Exception:
        logger.debug("project_npc_for_profile: mind_sea derive failed (npc=%s)", npc.id, exc_info=True)
    if viewer_karma is not None:
        try:
            from core.karma_engine import project_npc_reaction
            out["reaction"] = project_npc_reaction(_clamp_karma(npc.karma), viewer_karma, lang)
        except Exception:
            logger.debug("project_npc_for_profile: reaction failed (npc=%s)", npc.id, exc_info=True)
    # MV-8 — a VITRINE: sem ela a onda é invisível e um NPC com vontade fica
    # indistinguível de uma estátua. Uma linha server-resolved no molde dos
    # `wpulse_action_*` das 9 casas ("🚩 Marchando", "🗡️ À sua procura").
    # Key CONDICIONAL: flag OFF ou NPC sem feito → ausente ⇒ os 57 continuam
    # com o payload byte-idêntico.
    try:
        from core.jianghu_engine import npc_jianghu_view
        _jh = npc_jianghu_view(npc, lang)
        if _jh:
            out["jianghu"] = _jh
    except Exception:
        logger.debug("project_npc_for_profile: jianghu view failed (npc=%s)", npc.id, exc_info=True)
    return out


async def get_leaderboard_npcs(session, kind: str, *, limit: int = 50, realm_label=None) -> list[dict[str, Any]]:
    """Anonymized NPC rows to MERGE into a leaderboard (honest is_npc:true). Shape
    matches api_leaderboard player entries so the existing row renderer reuses
    them. 'sects' kind returns [] (NPCs don't compete in the guild ladder).
    ``realm_label`` is the optional (realm)->(name,emoji) callable from the caller."""
    # Owner override (Lei §6): NPCs are not surfaced in the ranking yet (Onda 4).
    if not NPC_LEADERBOARD_ENABLED or kind == "sects":
        return []
    try:
        # Fetch the candidate NPCs by the SAME key the ladder ranks on, so the
        # merged subset is the right "strongest" set: power for the power ladder,
        # realm/sub_layer for the cultivation ladder.
        if kind == "cultivation":
            order = (NpcCultivator.realm.desc(), NpcCultivator.sub_layer.desc())
        else:
            order = (NpcCultivator.power.desc(),)
        rows = (await session.execute(
            select(NpcCultivator)
            .where(NpcCultivator.status == "active")
            .order_by(*order)
            .limit(int(limit))
        )).scalars().all()
    except Exception:
        logger.debug("get_leaderboard_npcs failed", exc_info=True)
        return []
    out: list[dict[str, Any]] = []
    for n in rows:
        realm = int(n.realm or 0)
        rname, remoji = (None, "🌀")
        if realm_label is not None:
            try:
                rname, remoji = realm_label(realm)
            except Exception:
                pass
        # battle_power is directly comparable (NPC power IS a BP) so NPCs mix
        # naturally into the power ladder. cultivation_base = 0.0 (NPCs track no
        # real CB) so on the cultivation ladder they rank by realm/sub_layer and
        # sit below same-tier real players rather than over-ranking them.
        out.append({
            "is_npc": True,
            "npc_id": int(n.id),
            "name": n.name,
            "realm": realm,
            "realm_name": rname,
            "realm_emoji": remoji,
            "sub_layer": int(n.sub_layer or 1),
            "battle_power": int(n.power or 0),
            "cultivation_base": 0.0,
            "prestige": 0,
            "title": None,
        })
    return out


async def count_sect_npc_population(session) -> dict[str, int]:
    """Active NPC count per sect_id — the NPC half of a house's 'X discípulos'
    (the caller adds the real player members)."""
    try:
        rows = (await session.execute(
            select(NpcCultivator.sect_id, func.count())
            .where(NpcCultivator.status == "active", NpcCultivator.sect_id.is_not(None))
            .group_by(NpcCultivator.sect_id)
        )).all()
        return {s: int(n) for s, n in rows if s}
    except Exception:
        logger.debug("count_sect_npc_population failed", exc_info=True)
        return {}
