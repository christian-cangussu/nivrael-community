import random
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import WorldBoss, WorldBossDamage, Player, HerbCatalog, OreCatalog, TechniqueCatalog
from database.seeds.boss_seeds import WORLD_BOSS_POOL
from core.game_logic import format_number, get_progress_bar
# 名 2026-09-14 — o nome do chefe deixa de sair cru (captura do owner).
from core.i18n import catalog_name
from core.i18n import catalog_text
from core.i18n import t
from core.utils import escape_markdown, add_item_to_inventory

logger = logging.getLogger(__name__)

BOSS_DURATION_HOURS = 24
ATTACK_COOLDOWN_SECONDS = 1800  # 30 min
TOP_CONTRIBUTORS_COUNT = 10
RESULTS_VISIBLE_HOURS = 24

# Track A item 4 — Karma: the killing blow on a *demon/corrupt* world boss is the
# archetypal Righteous deed (rogue_kill_demonic +30). World bosses carry no
# alignment column, so we scope to the clearly-villainous names from
# WORLD_BOSS_POOL (engine-level, wipe-safe, no migration). The neutral primal
# beasts (Ancient Dragon, Void Beast, Shadow Wolf Alpha, Primordial Chaos Beast)
# are deliberately EXCLUDED — slaying a beast is not a moral act (Lei §2). Only
# the single player who lands killed=True earns it; one global kill / ~24h
# spawn = the scarcest event in the game, so it is not remotely farmable.
DEMONIC_BOSS_NAMES = {
    "Demonic Emperor",
    "Celestial Demon",
    "Void Wraith",
    "Corrupted Immortal",
    "Heaven-Devouring Serpent",
}

# ── Tier Configuration ─────────────────────────────────────────────────────

TIER_CONFIG = {
    "mortal":   {"realm_min": 0, "realm_max": 4,  "hp_factor": 0.3, "has_phases": False},
    "spirit":   {"realm_min": 5, "realm_max": 7,  "hp_factor": 0.5, "has_phases": True},
    "immortal": {"realm_min": 8, "realm_max": 10, "hp_factor": 1.0, "has_phases": True},
}

TIER_ORDER = ["mortal", "spirit", "immortal"]

TIER_EMOJIS = {"mortal": "🪨", "spirit": "⚡", "immortal": "🌸"}

# ── Phase Configuration ────────────────────────────────────────────────────
# Checked from lowest HP first

PHASE_THRESHOLDS = [
    ("final",  0.0,  0.25),
    ("shield", 0.25, 0.50),
    ("enrage", 0.50, 0.75),
    ("normal", 0.75, 1.01),
]

PHASE_DAMAGE_MODIFIERS = {
    "normal": 1.0,
    "enrage": 1.5,   # Boss drops defenses -> players deal +50%
    "shield": 0.3,   # Boss shields up -> players deal -70%
    "final":  1.0,   # Back to normal for the finish
}

PHASE_EMOJIS = {
    "normal": "⚔️",
    "enrage": "🔥",
    "shield": "🛡️",
    "final":  "💀",
}


# ── Tier / Phase Helpers ───────────────────────────────────────────────────

def get_player_tier(realm: int) -> str:
    if realm <= 4:
        return "mortal"
    elif realm <= 7:
        return "spirit"
    return "immortal"


def get_boss_phase(boss: WorldBoss) -> str:
    cfg = TIER_CONFIG.get(boss.tier, {})
    if not cfg.get("has_phases", False):
        return "normal"
    hp_pct = boss.current_hp / boss.hp if boss.hp > 0 else 0
    for phase, low, high in PHASE_THRESHOLDS:
        if low <= hp_pct < high:
            return phase
    return "normal"


def get_phase_damage_modifier(phase: str) -> float:
    return PHASE_DAMAGE_MODIFIERS.get(phase, 1.0)


# ── Boss Queries ───────────────────────────────────────────────────────────

async def get_active_boss(session: AsyncSession) -> WorldBoss | None:
    """Legacy: return any active boss (first found)."""
    stmt = select(WorldBoss).where(WorldBoss.is_active == True)
    return (await session.execute(stmt)).scalars().first()


async def get_active_boss_for_tier(session: AsyncSession, tier: str) -> WorldBoss | None:
    stmt = select(WorldBoss).where(
        WorldBoss.is_active == True,
        WorldBoss.tier == tier,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_all_active_bosses(session: AsyncSession) -> list[WorldBoss]:
    stmt = select(WorldBoss).where(WorldBoss.is_active == True)
    return list((await session.execute(stmt)).scalars().all())


async def get_last_ended_boss(session: AsyncSession) -> WorldBoss | None:
    """Legacy: return most recently ended boss within RESULTS_VISIBLE_HOURS."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RESULTS_VISIBLE_HOURS)
    stmt = (
        select(WorldBoss)
        .where(WorldBoss.is_active == False, WorldBoss.ended_at >= cutoff)
        .order_by(desc(WorldBoss.ended_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_last_ended_boss_for_tier(session: AsyncSession, tier: str) -> WorldBoss | None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RESULTS_VISIBLE_HOURS)
    stmt = (
        select(WorldBoss)
        .where(
            WorldBoss.is_active == False,
            WorldBoss.ended_at >= cutoff,
            WorldBoss.tier == tier,
        )
        .order_by(desc(WorldBoss.ended_at))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ── HP Calculation ─────────────────────────────────────────────────────────

async def _calculate_tier_hp(session: AsyncSession, tier: str, hp_mult: float = 1.0) -> int:
    """Calculate boss HP = sum(top10_approx_bp) * tier_factor * hp_mult."""
    from config import REALM_MULTIPLIERS
    cfg = TIER_CONFIG[tier]

    stmt = (
        select(Player.cultivation_base, Player.soul_strength, Player.battle_power, Player.realm)
        .where(Player.realm.between(cfg["realm_min"], cfg["realm_max"]))
        .order_by(desc(Player.cultivation_base))
        .limit(10)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return 0

    total_bp = 0
    for cb, soul, bp, realm in rows:
        realm_mult = REALM_MULTIPLIERS[min(realm, len(REALM_MULTIPLIERS) - 1)]
        approx = (cb * 0.3 + soul * 0.4 + bp * 0.3) * realm_mult
        total_bp += approx

    return max(10_000, int(total_bp * cfg["hp_factor"] * hp_mult))


# ── Spawn ──────────────────────────────────────────────────────────────────

async def spawn_bosses(session: AsyncSession, hp_mult: float = 1.0) -> list[WorldBoss]:
    """Spawn one boss per tier. Skips tiers with no players or already active."""
    spawned = []
    now = datetime.now(timezone.utc)

    for tier in TIER_ORDER:
        existing = await get_active_boss_for_tier(session, tier)
        if existing:
            continue

        pool = [b for b in WORLD_BOSS_POOL if b.get("tier") == tier]
        if not pool:
            continue

        hp = await _calculate_tier_hp(session, tier, hp_mult)
        if hp <= 0:
            logger.info("👹 Skipping %s boss — no players in tier", tier)
            continue

        template = random.choice(pool)
        boss = WorldBoss(
            name=template["name"],
            emoji=template["emoji"],
            tier=tier,
            phase="normal",
            hp=hp,
            current_hp=hp,
            loot_table=template["loot_table"],
            is_active=True,
            started_at=now,
            expires_at=now + timedelta(hours=BOSS_DURATION_HOURS),
        )
        session.add(boss)
        spawned.append(boss)

    if spawned:
        await session.flush()
    return spawned


async def spawn_boss(session: AsyncSession, hp_mult: float = 1.0) -> WorldBoss | None:
    """Legacy wrapper: spawn all tier bosses, return first spawned."""
    bosses = await spawn_bosses(session, hp_mult)
    return bosses[0] if bosses else None


# ── Attack ─────────────────────────────────────────────────────────────────

async def attack_boss(session: AsyncSession, player: Player, total_bp: int) -> dict:
    player_tier = get_player_tier(player.realm)

    # Lock the boss row for this player's tier
    stmt_boss = select(WorldBoss).where(
        WorldBoss.is_active == True,
        WorldBoss.current_hp > 0,
        WorldBoss.tier == player_tier,
    ).with_for_update()
    boss = (await session.execute(stmt_boss)).scalar_one_or_none()
    if not boss:
        return {"ok": False, "reason": "no_boss"}

    now = datetime.now(timezone.utc)
    if now >= boss.expires_at:
        return {"ok": False, "reason": "expired"}

    if boss.current_hp <= 0:
        return {"ok": False, "reason": "dead"}

    # Cooldown check (lock damage row)
    stmt = select(WorldBossDamage).where(
        WorldBossDamage.boss_id == boss.id,
        WorldBossDamage.player_id == player.telegram_id,
    ).with_for_update()
    dmg_row = (await session.execute(stmt)).scalar_one_or_none()

    if dmg_row and dmg_row.last_hit:
        elapsed = (now - dmg_row.last_hit).total_seconds()
        remaining = ATTACK_COOLDOWN_SECONDS - elapsed
        if remaining > 0:
            return {"ok": False, "reason": "cooldown", "remaining_seconds": remaining}

    # Phase damage modifier
    old_phase = get_boss_phase(boss)
    phase_mod = get_phase_damage_modifier(old_phase)

    technique_bonus = await _get_technique_bonus(session, player.telegram_id)
    raw_damage = int(total_bp * random.uniform(0.8, 1.2) * technique_bonus * phase_mod)
    raw_damage = max(1, raw_damage)

    # Cap damage at 5% of boss max HP
    max_damage_per_hit = max(1, int(boss.hp * 0.05))
    capped = raw_damage > max_damage_per_hit
    if capped:
        raw_damage = max_damage_per_hit

    # Atomic HP update
    boss.current_hp = max(0, boss.current_hp - raw_damage)

    # Detect phase change
    new_phase = get_boss_phase(boss)
    if new_phase != boss.phase:
        boss.phase = new_phase

    if dmg_row:
        dmg_row.total_damage += raw_damage
        dmg_row.hits += 1
        dmg_row.last_hit = now
    else:
        dmg_row = WorldBossDamage(
            boss_id=boss.id,
            player_id=player.telegram_id,
            total_damage=raw_damage,
            hits=1,
            last_hit=now,
        )
        session.add(dmg_row)

    killed = boss.current_hp <= 0
    if killed:
        boss.is_active = False
        boss.ended_at = now
        # Track A item 4 — Karma: the killing blow on a demon/corrupt boss is a
        # Righteous deed (+30). Scoped to DEMONIC_BOSS_NAMES (neutral beasts grant
        # nothing — not a moral act). Defensive: apply_karma owns a SAVEPOINT, so
        # a karma failure NEVER aborts the kill/loot. Caller commits.
        # Isto e' uma COMPARACAO, nao um texto. `DEMONIC_BOSS_NAMES` e' um
        # conjunto de nomes canonicos em ingles; traduzir aqui partiria o karma
        # do golpe final em pt e es, calado.
        # 名-CRU: comparacao de logica, nao texto de ecra.
        if boss.name in DEMONIC_BOSS_NAMES:
            try:
                from core.karma_engine import apply_karma
                await apply_karma(
                    session, player.telegram_id, "rogue_kill_demonic",
                    # 名-CRU: metadado de auditoria do karma, nao texto de ecra.
                    metadata={"boss_id": int(boss.id), "boss_name": boss.name},
                )
            except Exception:
                logger.warning("boss kill: karma wire failed (boss=%s)", boss.id, exc_info=True)

    return {
        "ok": True,
        "damage": raw_damage,
        "damage_capped": capped,
        "boss_id": boss.id,
        "boss_name": catalog_name((getattr(player, "language", None) or "pt").lower(),
                                  "boss", boss),
        "boss_emoji": boss.emoji,
        "boss_tier": boss.tier,
        "boss_hp": boss.current_hp,
        "boss_max_hp": boss.hp,
        "killed": killed,
        "player_total": dmg_row.total_damage,
        "player_hits": dmg_row.hits,
        "phase": new_phase,
        "phase_changed": new_phase != old_phase,
        "old_phase": old_phase,
        "phase_mod": phase_mod,
    }


async def _get_technique_bonus(session: AsyncSession, player_id: int) -> float:
    from database.models import PlayerTechnique, TechniqueCatalog
    stmt = (
        select(TechniqueCatalog.effect_value)
        .join(PlayerTechnique, PlayerTechnique.technique_id == TechniqueCatalog.id)
        .where(
            PlayerTechnique.player_id == player_id,
            PlayerTechnique.is_active_combat == True,
            TechniqueCatalog.effect_type == "damage_mult",
        )
    )
    # TEC-5 — o Chefe do Mundo também soma PASSIVAMENTE tudo o que está
    # equipado: a arte proibida bateria nele sem karma e sem anos. Flag OFF ⇒
    # conjunto vazio ⇒ query byte-idêntica (nenhum WHERE extra).
    try:
        from core.forbidden_path_engine import forbidden_ids as _fp_ids
        _forbidden = _fp_ids()
        if _forbidden:
            stmt = stmt.where(TechniqueCatalog.id.notin_(list(_forbidden)))
    except Exception:
        logger.debug("boss forbidden exclusion failed (player=%s)", player_id, exc_info=True)
    rows = (await session.execute(stmt)).scalars().all()
    bonus = 1.0
    for val in rows:
        bonus += val
    return bonus


# ── Rankings ───────────────────────────────────────────────────────────────

async def get_boss_ranking(session: AsyncSession, boss_id: int, limit: int = 10) -> list[dict]:
    stmt = (
        select(WorldBossDamage, Player.dao_name, Player.username, Player.display_name, Player.shadow_mode)
        .join(Player, Player.telegram_id == WorldBossDamage.player_id)
        .where(WorldBossDamage.boss_id == boss_id)
        .order_by(desc(WorldBossDamage.total_damage))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    ranking = []
    for i, (dmg, dao_name, username, display_name, shadow_mode) in enumerate(rows, 1):
        name = "???" if shadow_mode else (dao_name or username or display_name or "???")
        ranking.append({
            "rank": i,
            "player_id": dmg.player_id,
            "name": name,
            "damage": dmg.total_damage,
            "hits": dmg.hits,
        })
    return ranking


async def get_boss_full_ranking(session: AsyncSession, boss_id: int) -> list[dict]:
    """Full ranking with no limit (for results display)."""
    stmt = (
        select(WorldBossDamage, Player.dao_name, Player.username, Player.display_name, Player.shadow_mode)
        .join(Player, Player.telegram_id == WorldBossDamage.player_id)
        .where(WorldBossDamage.boss_id == boss_id)
        .order_by(desc(WorldBossDamage.total_damage))
    )
    rows = (await session.execute(stmt)).all()
    ranking = []
    for i, (dmg, dao_name, username, display_name, shadow_mode) in enumerate(rows, 1):
        name = "???" if shadow_mode else (dao_name or username or display_name or "???")
        ranking.append({
            "rank": i,
            "player_id": dmg.player_id,
            "name": name,
            "damage": dmg.total_damage,
            "hits": dmg.hits,
        })
    return ranking


async def get_player_boss_damage(session: AsyncSession, boss_id: int, player_id: int) -> WorldBossDamage | None:
    stmt = select(WorldBossDamage).where(
        WorldBossDamage.boss_id == boss_id,
        WorldBossDamage.player_id == player_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ── Loot Helpers ───────────────────────────────────────────────────────────

async def _load_item_names(session: AsyncSession, loot_table: dict,
                           lang: str = "pt") -> dict:
    """Pre-load catalog names for all items referenced in a loot_table."""
    herb_ids, ore_ids, tech_ids = set(), set(), set()
    for tier_drops in loot_table.values():
        for drop in tier_drops:
            dtype = drop.get("type")
            iid = drop.get("item_id")
            if iid is None:
                continue
            if dtype == "herb":
                herb_ids.add(iid)
            elif dtype == "ore":
                ore_ids.add(iid)
            elif dtype == "technique_scroll":
                tech_ids.add(iid)

    names: dict = {}

    if herb_ids:
        rows = (await session.execute(
            select(HerbCatalog.id, HerbCatalog.name, HerbCatalog.emoji)
            .where(HerbCatalog.id.in_(herb_ids))
        )).all()
        for rid, rname, remoji in rows:
            names[("herb", rid)] = (catalog_text(lang, "herb", rid, "name", rname), remoji or "🌿")

    if ore_ids:
        rows = (await session.execute(
            select(OreCatalog.id, OreCatalog.name, OreCatalog.emoji)
            .where(OreCatalog.id.in_(ore_ids))
        )).all()
        for rid, rname, remoji in rows:
            names[("ore", rid)] = (catalog_text(lang, "ore", rid, "name", rname), remoji or "⛏️")

    if tech_ids:
        rows = (await session.execute(
            select(TechniqueCatalog.id, TechniqueCatalog.name, TechniqueCatalog.emoji)
            .where(TechniqueCatalog.id.in_(tech_ids))
        )).all()
        for rid, rname, remoji in rows:
            names[("technique_scroll", rid)] = (catalog_text(lang, "tech", rid, "name", rname), remoji or "📜")

    return names


def _get_tier_drops(loot: dict, rank: int) -> list[dict]:
    """Return the correct loot tier for the given rank."""
    if rank == 1:
        key = "rank_1"
    elif rank == 2:
        key = "rank_2"
    elif rank == 3:
        key = "rank_3"
    elif rank <= 10:
        key = "rank_4_10"
    else:
        key = "participant"
    if key not in loot:
        return loot.get("top_10", []) if rank <= 10 else loot.get("participant", [])
    return loot[key]


# ── Reward Distribution ───────────────────────────────────────────────────

async def distribute_rewards(session: AsyncSession, boss: WorldBoss, loot_mult: float = 1.0) -> list[dict]:
    """Distribute tiered rewards to all participants. Marks rewards_given=True."""
    boss = (await session.execute(
        select(WorldBoss).where(WorldBoss.id == boss.id).with_for_update()
    )).scalar_one_or_none()
    if not boss or boss.rewards_given:
        return []

    loot = boss.loot_table
    # 名 2026-09-14 — ⚠️ O ESPOLIO DO CHEFE VAI PARA MUITA GENTE, e cada um tem a
    # SUA lingua: um `item_names` unico aqui daria o nome na lingua errada a
    # toda a gente menos a um. Carrega-se UM mapa POR LINGUA presente no
    # ranking (sao 3 no maximo), em cache, e cada linha de recompensa e'
    # composta com o mapa do seu destinatario.
    _names_by_lang: dict[str, dict] = {}

    async def _names_for(lg: str) -> dict:
        lg = (lg or "pt").lower()
        if lg not in _names_by_lang:
            _names_by_lang[lg] = await _load_item_names(session, loot, lg)
        return _names_by_lang[lg]

    ranking = await get_boss_full_ranking(session, boss.id)
    notifications = []

    total_damage = sum(entry["damage"] for entry in ranking) or 1
    num_participants = len(ranking) or 1

    for entry in ranking:
        pid = entry["player_id"]
        player = (await session.execute(select(Player).where(Player.telegram_id == pid))).scalar_one_or_none()
        if not player:
            continue

        damage_share = entry["damage"] / total_damage
        proportional_mult = damage_share * num_participants
        proportional_mult = max(0.5, min(proportional_mult, 3.0))

        from core.monetization import get_player_vip_level, get_vip_perks
        vip_lvl = await get_player_vip_level(session, pid)
        vip_perks = get_vip_perks(vip_lvl)
        player_loot_mult = loot_mult * (1.25 if vip_perks["priority_world_boss"] else 1.0) * proportional_mult

        tier_drops = _get_tier_drops(loot, entry["rank"])
        reward_lines = []
        for drop in tier_drops:
            scaled = _scale_drop(drop, player_loot_mult)
            await _apply_drop(session, player, scaled)
            reward_lines.append(
                _drop_description(scaled, await _names_for(player.language)))

        # C-5: Immortal-tier bosses grant Celestial Essence to top-3 damage
        # ranks (30 / 20 / 10) so endgame players have an extra source for
        # body tempering tiers 10/11/12 cap.
        if boss.tier == "immortal" and entry["rank"] in (1, 2, 3):
            essence_amounts = {1: 30, 2: 20, 3: 10}
            essence_gain = essence_amounts[entry["rank"]]
            player.celestial_essence = (player.celestial_essence or 0) + essence_gain
            reward_lines.append(t(player.language or "en", "boss_reward_celestial_essence", amount=essence_gain))

        notifications.append({
            "player_id": pid,
            "rank": entry["rank"],
            "name": entry["name"],
            "damage": entry["damage"],
            "rewards": reward_lines,
            "is_top": entry["rank"] <= 10,
            "lang": player.language or "en",
            "boss_tier": boss.tier,
        })

    boss.rewards_given = True
    return notifications


def _scale_drop(drop: dict, mult: float) -> dict:
    if mult <= 1.0:
        return drop
    scaled = dict(drop)
    if "amount" in scaled:
        scaled["amount"] = max(1, int(scaled["amount"] * mult))
    return scaled


async def _apply_drop(session, player: Player, drop: dict) -> bool:
    dtype = drop["type"]
    if dtype == "spirit_stones":
        player.spirit_stones += drop["amount"]
        return True
    elif dtype in ("herb", "ore", "technique_scroll", "beast_core"):
        item_id = drop.get("item_id", 0)
        amount = drop.get("amount", 1)
        return await add_item_to_inventory(session, player.telegram_id, dtype, item_id, amount)
    return True


def _drop_description(drop: dict, item_names: dict | None = None, lang: str = "en") -> str:
    dtype = drop["type"]
    amount = drop.get("amount", 1)
    item_id = drop.get("item_id")

    if dtype == "spirit_stones":
        return t(lang, "boss_reward_spirit_stones", amount=format_number(amount))
    if dtype == "beast_core":
        return t(lang, "boss_reward_beast_core", amount=amount)

    if item_names and item_id and (dtype, item_id) in item_names:
        name, emoji = item_names[(dtype, item_id)]
        return f"{emoji} ×{amount} {escape_markdown(name)}"

    fallback = {
        "herb": t(lang, "boss_reward_herb", amount=amount),
        "ore": t(lang, "boss_reward_ore", amount=amount),
        "technique_scroll": t(lang, "boss_reward_technique_scroll", amount=amount),
    }
    return fallback.get(dtype, f"{dtype} ×{amount}")


def _loot_tier_summary(loot: dict, rank: int, loot_mult: float = 1.0, item_names: dict | None = None, lang: str = "en") -> str:
    """One-line summary of what a rank tier receives."""
    drops = _get_tier_drops(loot, rank)
    parts = []
    for drop in drops:
        scaled = _scale_drop(drop, loot_mult)
        parts.append(_drop_description(scaled, item_names, lang=lang))
    return " + ".join(parts) if parts else "—"


# ── Display Builders ───────────────────────────────────────────────────────

def build_boss_display(
    boss: WorldBoss,
    player_dmg: WorldBossDamage | None,
    ranking: list[dict],
    lang: str = "en",
    viewer_tier: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    time_left = boss.expires_at - now
    hours_left = max(0, int(time_left.total_seconds() // 3600))
    mins_left = max(0, int((time_left.total_seconds() % 3600) // 60))

    hp_bar = get_progress_bar(boss.current_hp, boss.hp, length=15)
    sep = "—" * 28

    tier_emoji = TIER_EMOJIS.get(boss.tier, "👹")
    tier_name = t(lang, f"boss_tier_{boss.tier}")
    safe_boss_name = escape_markdown(catalog_name(lang, "boss", boss))

    lines = [
        t(lang, "boss_display_tier_title", tier_emoji=tier_emoji, tier=tier_name, boss_emoji=boss.emoji, name=safe_boss_name),
        sep,
        t(lang, "boss_display_hp", current=format_number(boss.current_hp), max=format_number(boss.hp)),
        f"{hp_bar}",
    ]

    # Phase display (Spirit/Immortal only)
    phase = get_boss_phase(boss)
    cfg = TIER_CONFIG.get(boss.tier, {})
    if cfg.get("has_phases", False):
        phase_emoji = PHASE_EMOJIS.get(phase, "⚔️")
        phase_name = t(lang, f"boss_phase_{phase}")
        phase_desc = t(lang, f"boss_phase_desc_{phase}")
        lines.append(t(lang, "boss_phase_line", emoji=phase_emoji, phase=phase_name, desc=phase_desc))

    lines.append(t(lang, "boss_display_expires", hours=hours_left, mins=mins_left))

    # Tier lock notice
    if viewer_tier and viewer_tier != boss.tier:
        vcfg = TIER_CONFIG.get(boss.tier, {})
        lines.append(t(lang, "boss_tier_locked_notice",
                       tier=tier_name,
                       min=vcfg.get("realm_min", 0),
                       max=vcfg.get("realm_max", 10)))

    lines.append(sep)

    if player_dmg:
        lines.append(t(lang, "boss_display_your_damage", damage=format_number(player_dmg.total_damage)))
        lines.append(t(lang, "boss_display_your_attacks", hits=player_dmg.hits))

        if player_dmg.last_hit:
            elapsed = (now - player_dmg.last_hit).total_seconds()
            remaining = ATTACK_COOLDOWN_SECONDS - elapsed
            if remaining > 0:
                cd_min = int(remaining // 60)
                cd_sec = int(remaining % 60)
                lines.append(t(lang, "boss_display_cooldown", mins=cd_min, secs=cd_sec))
            else:
                lines.append(t(lang, "boss_display_ready"))
        else:
            lines.append(t(lang, "boss_display_ready"))
    else:
        lines.append(t(lang, "boss_display_not_attacked"))
        lines.append(t(lang, "boss_display_ready"))

    lines.append(sep)

    if ranking:
        lines.append(t(lang, "boss_display_top_contributors"))
        medals = ["🥇", "🥈", "🥉"]
        for entry in ranking[:10]:
            medal = medals[entry["rank"] - 1] if entry["rank"] <= 3 else f"#{entry['rank']}"
            safe_name = escape_markdown(entry["name"])
            lines.append(f"{medal} {safe_name} — {format_number(entry['damage'])}")
    else:
        lines.append(t(lang, "boss_display_no_attackers"))

    return "\n".join(lines)


async def build_boss_results_display(
    session: AsyncSession,
    boss: WorldBoss,
    ranking: list[dict],
    viewer_id: int | None = None,
    loot_mult: float = 1.0,
    lang: str = "en",
) -> str:
    """Post-battle results screen: full ranking + tiered rewards preview."""
    sep = "—" * 28
    loot = boss.loot_table
    item_names = await _load_item_names(session, loot, lang)

    tier_emoji = TIER_EMOJIS.get(boss.tier, "👹")
    tier_name = t(lang, f"boss_tier_{boss.tier}")
    safe_boss_name = escape_markdown(catalog_name(lang, "boss", boss))

    killed = boss.current_hp <= 0
    if killed:
        header = t(lang, "boss_results_defeated_tier", tier_emoji=tier_emoji, tier=tier_name, boss_emoji=boss.emoji, name=safe_boss_name)
        status_line = t(lang, "boss_results_defeated_desc")
    else:
        header = t(lang, "boss_results_expired_tier", tier_emoji=tier_emoji, tier=tier_name, boss_emoji=boss.emoji, name=safe_boss_name)
        status_line = t(lang, "boss_results_expired_desc")

    time_note = ""
    if boss.ended_at:
        delta = datetime.now(timezone.utc) - boss.ended_at
        h = int(delta.total_seconds() // 3600)
        m = int((delta.total_seconds() % 3600) // 60)
        time_note = f"\n{t(lang, 'boss_results_ended_ago', hours=h, mins=m)}"

    lines = [header, sep, status_line + time_note, ""]

    if ranking:
        lines.append(t(lang, "boss_results_ranking_title"))
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        shown = ranking[:10]
        for entry in shown:
            rank = entry["rank"]
            medal = medals.get(rank, f"#{rank}")
            marker = " 👈" if entry["player_id"] == viewer_id else ""
            safe_name = escape_markdown(entry["name"])
            lines.append(f"{medal} {safe_name} — {format_number(entry['damage'])} dmg{marker}")

        if len(ranking) > 10:
            viewer_entry = next((e for e in ranking if e["player_id"] == viewer_id), None)
            if viewer_entry and viewer_entry["rank"] > 10:
                safe_viewer_name = escape_markdown(viewer_entry["name"])
                lines.append(f"  ...")
                lines.append(f"#{viewer_entry['rank']} {safe_viewer_name} — {format_number(viewer_entry['damage'])} dmg 👈")
            elif len(ranking) > 10:
                lines.append(t(lang, "boss_results_other_participants", count=len(ranking) - 10))
    else:
        lines.append(t(lang, "boss_results_no_participants"))

    lines.append(sep)

    lines.append(t(lang, "boss_results_rewards_title"))
    lines.append(t(lang, "boss_results_1st", rewards=_loot_tier_summary(loot, 1, loot_mult, item_names, lang=lang)))
    lines.append(t(lang, "boss_results_2nd", rewards=_loot_tier_summary(loot, 2, loot_mult, item_names, lang=lang)))
    lines.append(t(lang, "boss_results_3rd", rewards=_loot_tier_summary(loot, 3, loot_mult, item_names, lang=lang)))
    lines.append(t(lang, "boss_results_4_10", rewards=_loot_tier_summary(loot, 4, loot_mult, item_names, lang=lang)))
    lines.append(t(lang, "boss_results_participants", rewards=_loot_tier_summary(loot, 11, loot_mult, item_names, lang=lang)))

    return "\n".join(lines)


def build_boss_killed_display(boss: WorldBoss, lang: str = "en") -> str:
    safe_name = escape_markdown(catalog_name(lang, "boss", boss))
    return (
        t(lang, "boss_killed_title", emoji=boss.emoji, name=safe_name) + "\n\n"
        + t(lang, "boss_killed_desc", name=safe_name) + "\n\n"
        + t(lang, "boss_killed_rewards") + "\n"
        + t(lang, "boss_killed_top", count=TOP_CONTRIBUTORS_COUNT)
    )


# ── Expire ─────────────────────────────────────────────────────────────────

async def expire_bosses(session: AsyncSession) -> list[WorldBoss]:
    """Expire all active bosses past their expiry time. Returns list of expired."""
    now = datetime.now(timezone.utc)
    stmt = select(WorldBoss).where(
        WorldBoss.is_active == True,
    )
    all_active = list((await session.execute(stmt)).scalars().all())
    expired = []
    for boss in all_active:
        if now >= boss.expires_at or boss.current_hp <= 0:
            boss.is_active = False
            if not boss.ended_at:
                boss.ended_at = now
            expired.append(boss)
    return expired


async def expire_boss(session: AsyncSession) -> WorldBoss | None:
    """Legacy: expire single boss."""
    bosses = await expire_bosses(session)
    return bosses[0] if bosses else None
