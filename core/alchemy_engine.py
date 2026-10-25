import logging
import random
from datetime import datetime, timezone, timedelta
from math import floor

from sqlalchemy import select, and_, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Player, PlayerInventory, PlayerCauldron, PlayerBuff,
    HerbCatalog, PillCatalog, CauldronCatalog, PlayerAlchemySkill,
    PlayerPillMastery, PlayerRecipe, PlayerSoulFire,
    PlayerOre,
)

logger = logging.getLogger(__name__)

# 2026-05-26 hotfix — Production timeout incident on `roll_recipe_drop`.
# PillCatalog is a static 37-row table seeded at startup; querying it on
# every recipe-drop check (~8% of dungeon-sweep floors) is wasteful AND
# made it the unlucky victim of statement_timeout under DB load.
#
# This module-level cache stores pill ids grouped by `required_alchemy_tier`
# so `roll_recipe_drop` can resolve candidate ids in O(1) without a DB
# round-trip. Filled lazily on first use; never invalidated (PillCatalog
# is immutable post-seed). A failed initial load returns an empty dict so
# the caller short-circuits to "no recipe this roll" instead of poisoning
# the outer transaction.
_PILL_IDS_BY_TIER: dict[int, list[int]] | None = None


async def _ensure_pill_ids_by_tier(session: AsyncSession) -> dict[int, list[int]]:
    """Return the {tier: [pill_id, ...]} cache, lazily loading on first call.

    Catalog cache is module-level so all subsequent calls — across players,
    across handlers — share the same in-memory map. Defensive: any error
    during the initial load returns an empty dict (caller short-circuits).
    """
    global _PILL_IDS_BY_TIER
    if _PILL_IDS_BY_TIER is not None:
        return _PILL_IDS_BY_TIER
    try:
        rows = (await session.execute(
            select(PillCatalog.id, PillCatalog.required_alchemy_tier)
        )).all()
    except Exception:
        logger.warning("PillCatalog cache load failed; recipe drops skipped this run", exc_info=True)
        # Don't latch the cache as empty — let the next call retry. Just
        # return an empty dict for THIS call so it short-circuits.
        return {}
    cache: dict[int, list[int]] = {}
    for pid, tier in rows:
        if pid is None or tier is None:
            continue
        cache.setdefault(int(tier), []).append(int(pid))
    _PILL_IDS_BY_TIER = cache
    return cache
from config import (
    ALCHEMY_ENERGY_BASE, ALCHEMY_ENERGY_REGEN_MINUTES,
    ALCHEMY_ENERGY_VIP_MAX_BONUS, ALCHEMY_ENERGY_VIP_REGEN,
    ALCHEMY_ENERGY_TIER_MAX_BONUS, ALCHEMY_ENERGY_TIER_REGEN_MULT,
    ALCHEMY_ENERGY_REGEN_FLOOR,
)


ALCHEMY_TIERS = {
    1: {"name": "Apprentice", "name_pt": "Aprendiz", "name_es": "Aprendiz", "xp_req": 0, "emoji": "🔰"},
    2: {"name": "Journeyman", "name_pt": "Oficial", "name_es": "Oficial", "xp_req": 500, "emoji": "⚗️"},
    3: {"name": "Master", "name_pt": "Mestre", "name_es": "Maestro", "xp_req": 2000, "emoji": "🏆"},
    4: {"name": "Grandmaster", "name_pt": "Grão-Mestre", "name_es": "Gran Maestro", "xp_req": 8000, "emoji": "👑"},
    # Tier 5 reduzido de 30000→15000: com 10 crafts/dia (~25 XP médio) → ~60 dias = 2 meses ✅
    5: {"name": "Celestial", "name_pt": "Celestial", "name_es": "Celestial", "xp_req": 15000, "emoji": "🌸"},
}
MAX_ALCHEMY_TIER = 5

# 冶 3.1 (2026-09-29) — O DONO DO GATE DA ALQUIMIA.
# Medido antes deste lote: o limiar estava escrito À MÃO em cinco sítios — três
# comparações `< 1` no `webserver.py` (a leitura e os dois crafts), o
# `"min_realm_required": 1` do payload e o `player.realm < 1` do chat — e o
# número vivia DENTRO do texto `alch_locked_msg` ("Reino 1"), que mentiria no
# dia em que o limiar mudasse. Agora é este número e esta função; os textos
# recebem o reino por parâmetro.
ALCHEMY_MIN_REALM = 1


def alchemy_realm_locked(player) -> bool:
    """True quando o reino do jogador ainda não abre a Alquimia."""
    return int(getattr(player, "realm", 0) or 0) < ALCHEMY_MIN_REALM


XP_REWARDS = {
    "success": 20,    # antes: 15
    "perfect": 60,    # antes: 40
    "divine": 200,    # antes: 150
    "heavenly": 500,  # novo: pill tribulation grade
    "failure": 3,
    "explosion": 1,
}


def get_tier_name(tier: int, lang: str) -> str:
    info = ALCHEMY_TIERS.get(tier, ALCHEMY_TIERS[1])
    if lang == "pt":
        return info["name_pt"]
    if lang == "es":
        return info["name_es"]
    return info["name"]


CRAFT_RESULTS = {
    "heavenly": {
        "potency_mult": 5.0,
        "quality": "heavenly",
    },
    "divine": {
        "potency_mult": 3.0,
        "quality": "divine",
    },
    "perfect": {
        "potency_mult": 1.5,
        "quality": "perfect",
    },
    "success": {
        "potency_mult": 1.0,
        "quality": "normal",
    },
    "failure": {
        "potency_mult": 0.0,
        "quality": None,
    },
    "explosion": {
        "potency_mult": 0.0,
        "quality": None,
        "durability_loss": 10,
    },
}


def calculate_success_chance(
    cauldron: CauldronCatalog | None,
    pill: PillCatalog,
    alchemy_tier: int = 1,
    mastery_bonus: float = 0.0,
    soul_fire_bonus: float = 0.0,
    profession_bonus: float = 0.0,
) -> float:
    # MV-7: profession_bonus = pontos % do Alquimista (profession_engine.
    # alchemy_success_bonus — gated, 0.0 com flag OFF). Entra AQUI, sob o
    # clamp de 98, para o display (chat/mini) nunca divergir do roll
    # (lição MV-6: o número do confirm vem da MESMA função que rola).
    cauldron_bonus = cauldron.success_bonus if cauldron else 0.0
    base = (alchemy_tier * 5.0) + cauldron_bonus
    difficulty_penalty = pill.difficulty * 8.0
    chance = max(5.0, min(98.0, base + 30.0 - difficulty_penalty + mastery_bonus + soul_fire_bonus + profession_bonus))
    return chance


async def get_or_create_alchemy_skill(session: AsyncSession, player_id: int) -> PlayerAlchemySkill:
    skill = (await session.execute(
        select(PlayerAlchemySkill).where(PlayerAlchemySkill.player_id == player_id)
    )).scalar_one_or_none()
    if not skill:
        skill = PlayerAlchemySkill(player_id=player_id, tier=1, xp=0, total_crafts=0, divine_crafts=0)
        session.add(skill)
        await session.flush()
    return skill


def _check_alchemy_levelup(skill: PlayerAlchemySkill) -> bool:
    """Returns True if the skill leveled up (mutates skill.tier in place)."""
    if skill.tier >= MAX_ALCHEMY_TIER:
        return False
    next_tier_req = ALCHEMY_TIERS[skill.tier + 1]["xp_req"]
    if skill.xp >= next_tier_req:
        skill.tier += 1
        return True
    return False


async def grant_alchemy_xp(session: AsyncSession, player_id: int, result_type: str) -> tuple[PlayerAlchemySkill, bool]:
    """Grants XP for a craft result. Returns (skill, leveled_up)."""
    skill = await get_or_create_alchemy_skill(session, player_id)
    xp_gain = XP_REWARDS.get(result_type, 0)
    skill.xp += xp_gain
    skill.total_crafts += 1
    if result_type in ("divine", "heavenly"):
        skill.divine_crafts += 1
    leveled_up = _check_alchemy_levelup(skill)
    return skill, leveled_up


def roll_craft_result(success_chance: float, alchemy_tier: int = 1, pill_tier: int = 1, quality_bonus: float = 0.0) -> str:
    roll = random.uniform(0, 100)

    if roll > success_chance:
        if roll > success_chance + ((100 - success_chance) * 0.6):
            return "explosion"
        return "failure"

    # quality_bonus = Dao "pill_quality" (e.g. 0.48 = +48% from Dao of Creation /
    # craft_quality laws). FIX 2026-06-01: this was computed + shown to players
    # but never applied — a dead mechanic. It multiplies the divine + perfect
    # ODDS (not raw success), so investing in the Dao actually yields better
    # pills. Caps keep it from swallowing the whole success band.
    qmult = 1.0 + max(0.0, float(quality_bonus or 0.0))

    # Heavenly chance: ~1% of successes (triggers pill tribulation)
    heavenly_pct = 1.0
    # Divine chance: base 1.5% of successes + 0.5% per alchemy tier above pill tier, cap 5%
    tier_bonus = max(0, alchemy_tier - pill_tier) * 0.5
    divine_pct = min((1.5 + tier_bonus) * qmult, 12.0)
    # Perfect chance: fixed 8% of successes
    perfect_pct = min(8.0 * qmult, 30.0)

    heavenly_threshold = success_chance * (heavenly_pct / 100)
    divine_threshold = heavenly_threshold + success_chance * (divine_pct / 100)
    perfect_threshold = divine_threshold + success_chance * (perfect_pct / 100)

    if roll <= heavenly_threshold:
        return "heavenly"
    if roll <= divine_threshold:
        return "divine"
    if roll <= perfect_threshold:
        return "perfect"
    return "success"


async def get_equipped_cauldron(session: AsyncSession, player_id: int) -> tuple[PlayerCauldron | None, CauldronCatalog | None]:
    stmt = (
        select(PlayerCauldron, CauldronCatalog)
        .join(CauldronCatalog, PlayerCauldron.cauldron_id == CauldronCatalog.id)
        .where(and_(PlayerCauldron.player_id == player_id, PlayerCauldron.is_equipped == True))
    )
    result = await session.execute(stmt)
    row = result.first()
    if row:
        return row[0], row[1]
    return None, None


async def get_all_pills(session: AsyncSession) -> list[PillCatalog]:
    result = await session.execute(select(PillCatalog).order_by(PillCatalog.id))
    return list(result.scalars().all())


async def get_all_herbs(session: AsyncSession) -> list[HerbCatalog]:
    result = await session.execute(select(HerbCatalog).order_by(HerbCatalog.id))
    return list(result.scalars().all())


async def get_all_cauldrons(session: AsyncSession) -> list[CauldronCatalog]:
    result = await session.execute(select(CauldronCatalog).order_by(CauldronCatalog.id))
    return list(result.scalars().all())


async def get_player_cauldrons(session: AsyncSession, player_id: int) -> list[tuple[PlayerCauldron, CauldronCatalog]]:
    stmt = (
        select(PlayerCauldron, CauldronCatalog)
        .join(CauldronCatalog, PlayerCauldron.cauldron_id == CauldronCatalog.id)
        .where(PlayerCauldron.player_id == player_id)
        .order_by(CauldronCatalog.grade)
    )
    result = await session.execute(stmt)
    return list(result.all())


async def get_herb_inventory(session: AsyncSession, player_id: int) -> list[tuple[PlayerInventory, HerbCatalog]]:
    stmt = (
        select(PlayerInventory, HerbCatalog)
        .join(HerbCatalog, PlayerInventory.item_id == HerbCatalog.id)
        .where(and_(PlayerInventory.player_id == player_id, PlayerInventory.item_type == "herb"))
        .order_by(HerbCatalog.tier)
    )
    result = await session.execute(stmt)
    return list(result.all())


async def get_pill_inventory(session: AsyncSession, player_id: int) -> list[tuple[PlayerInventory, PillCatalog]]:
    stmt = (
        select(PlayerInventory, PillCatalog)
        .join(PillCatalog, PlayerInventory.item_id == PillCatalog.id)
        .where(and_(PlayerInventory.player_id == player_id, PlayerInventory.item_type == "pill"))
        .order_by(PillCatalog.id)
    )
    result = await session.execute(stmt)
    return list(result.all())


async def check_ingredients(session: AsyncSession, player_id: int, pill: PillCatalog) -> dict[int, dict]:
    ingredients_status = {}
    for ingredient in pill.ingredients:
        herb_id = ingredient["herb_id"]
        required = ingredient["qty"]

        inv_stmt = select(PlayerInventory).where(and_(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "herb",
            PlayerInventory.item_id == herb_id,
        ))
        result = await session.execute(inv_stmt)
        inv_item = result.scalar_one_or_none()

        herb_stmt = select(HerbCatalog).where(HerbCatalog.id == herb_id)
        herb = (await session.execute(herb_stmt)).scalar_one_or_none()

        ingredients_status[herb_id] = {
            "herb": herb,
            "required": required,
            "owned": inv_item.quantity if inv_item else 0,
            "has_enough": (inv_item.quantity >= required) if inv_item else False,
        }

    return ingredients_status


async def consume_ingredients(session: AsyncSession, player_id: int, pill: PillCatalog):
    for ingredient in pill.ingredients:
        herb_id = ingredient["herb_id"]
        qty = ingredient["qty"]

        stmt = select(PlayerInventory).where(and_(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "herb",
            PlayerInventory.item_id == herb_id,
        ))
        result = await session.execute(stmt)
        inv_item = result.scalar_one_or_none()
        if not inv_item:
            continue

        inv_item.quantity -= qty
        if inv_item.quantity <= 0:
            await session.delete(inv_item)


from core.utils import add_item_to_inventory  # noqa: F811 — re-export for callers

# 名 2026-09-14 — o nome da peca vem do dono unico, nunca cru (Lei F-7 §2).
from core.i18n import catalog_name


async def craft_pill(session: AsyncSession, player: Player, pill: PillCatalog, alchemy_tier: int = 1) -> dict:
    pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)

    # Block crafting with a broken cauldron (0 durability)
    if pc and pc.durability <= 0:
        return {
            "success": False,
            "error": "cauldron_broken",
        }

    # Get mastery and soul fire bonuses
    mastery = await get_or_create_pill_mastery(session, player.telegram_id, pill.id)
    mastery_bonus = get_mastery_bonus(mastery.mastery_level)
    sf = await get_or_create_soul_fire(session, player.telegram_id, player.realm)
    sf_bonus = get_soul_fire_bonus(sf.fire_tier)

    # MV-7 — bônus do Alquimista (gated; 0.0 com flag OFF → byte-idêntico).
    prof_bonus = 0.0
    try:
        from core.profession_engine import alchemy_success_bonus
        prof_bonus = float(alchemy_success_bonus(player) or 0.0)
    except Exception:
        prof_bonus = 0.0

    success_chance = calculate_success_chance(cauldron, pill, alchemy_tier, mastery_bonus, sf_bonus, profession_bonus=prof_bonus)

    # Faction bonus: Demonic +20% pill potency → boosts success chance
    from core.faction_engine import get_faction_bonuses
    fac_bonuses = await get_faction_bonuses(session, player.telegram_id)
    pill_potency = fac_bonuses.get("pill_potency_bonus", 0)
    if pill_potency > 0:
        success_chance = min(100, success_chance * (1 + pill_potency))

    # Dao "pill_quality" bonus (Dao of Creation + craft_quality laws) — boosts
    # the odds of divine/perfect outcomes. FIX 2026-06-01: was a dead mechanic
    # (computed + displayed but never consumed in any craft path). Fetched here
    # so chat + single + bulk crafting (all route through craft_pill) benefit.
    quality_bonus = 0.0
    try:
        from core.dao_engine import get_player_dao_bonuses
        _dao = await get_player_dao_bonuses(session, player.telegram_id, int(player.realm or 0))
        quality_bonus = float(_dao.get("pill_quality", 0.0) or 0.0)
    except Exception:
        quality_bonus = 0.0

    result = roll_craft_result(success_chance, alchemy_tier, pill.required_alchemy_tier, quality_bonus=quality_bonus)

    # ── Pill Charm: +10% chance to upgrade success → heavenly ──
    charm_used = False
    if result in ("success", "perfect") and random.random() < 0.10:
        from database.models import PlayerBuff
        from datetime import datetime as _dt, timezone as _tz
        _now = _dt.now(_tz.utc)
        _pill_charm = (await session.execute(
            select(PlayerBuff).where(
                PlayerBuff.player_id == player.telegram_id,
                PlayerBuff.buff_type == "pill_charm",
                PlayerBuff.expires_at > _now
            )
        )).scalar_one_or_none()
        if _pill_charm:
            result = "heavenly"
            _pill_charm.buff_value -= 1
            if _pill_charm.buff_value <= 0:
                await session.delete(_pill_charm)
            charm_used = True

    result_info = CRAFT_RESULTS[result]

    craft_data = {
        "result": result,
        "pill": pill,
        "success_chance": success_chance,
        "cauldron": cauldron,
        "mastery_bonus": mastery_bonus,
        "soul_fire_bonus": sf_bonus,
        "charm_used": charm_used,
    }

    # Heavenly result triggers pill tribulation — don't add pill yet
    if result == "heavenly":
        craft_data["quality"] = "heavenly"
        craft_data["potency_mult"] = result_info["potency_mult"]
        # Consume ingredients now; pill is awarded after tribulation success
        await consume_ingredients(session, player.telegram_id, pill)
        # Increment mastery
        mastery, mastery_leveled = await increment_pill_mastery(session, player.telegram_id, pill.id)
        craft_data["mastery"] = mastery
        craft_data["mastery_leveled"] = mastery_leveled
        # Grant soul fire XP
        sf, sf_leveled = await grant_soul_fire_xp(session, player.telegram_id, player.realm, result)
        craft_data["soul_fire"] = sf
        craft_data["soul_fire_leveled"] = sf_leveled
        return craft_data

    # If craft would succeed, try adding pill BEFORE consuming ingredients
    if result in ("success", "perfect", "divine"):
        quality = result_info["quality"]
        added = await add_item_to_inventory(session, player.telegram_id, "pill", pill.id, 1, quality)
        if not added:
            craft_data["inventory_full"] = True
            return craft_data
        craft_data["quality"] = quality
        craft_data["potency_mult"] = result_info["potency_mult"]
        # MV-7 — 🧪 pílula extra do Alquimista (só pills T1-T2; nunca no
        # caminho heavenly, que tem tribulação própria). MESMA quality →
        # stack na row recém-criada, nunca falha por anel cheio. NÃO conta
        # nos trackers (1 craft = 1 crédito; a extra é presente do ofício).
        # Gated (flag OFF → roll nem acontece → main byte-idêntico).
        try:
            from core.profession_engine import roll_extra_pill
            if roll_extra_pill(player, pill.required_alchemy_tier):
                extra_ok = await add_item_to_inventory(
                    session, player.telegram_id, "pill", pill.id, 1, quality)
                if extra_ok:
                    craft_data["extra_pill"] = True
        except Exception:
            logger.exception("profession extra pill failed")

    # Consume ingredients only after inventory check passed (or craft failed/exploded)
    await consume_ingredients(session, player.telegram_id, pill)

    if result == "explosion" and pc:
        pc.durability = max(0, pc.durability - result_info.get("durability_loss", 10))
        craft_data["durability_remaining"] = pc.durability

    # Increment mastery
    mastery, mastery_leveled = await increment_pill_mastery(session, player.telegram_id, pill.id)
    craft_data["mastery"] = mastery
    craft_data["mastery_leveled"] = mastery_leveled

    # Grant soul fire XP
    sf, sf_leveled = await grant_soul_fire_xp(session, player.telegram_id, player.realm, result)
    craft_data["soul_fire"] = sf
    craft_data["soul_fire_leveled"] = sf_leveled

    return craft_data


async def _create_or_extend_buff(
    session: AsyncSession,
    player: Player,
    buff_type: str,
    buff_value: float,
    duration_minutes: int,
    source: str,
    permanent_until_triggered: bool = False,
) -> None:
    now = datetime.now(timezone.utc)
    if permanent_until_triggered:
        expires = now + timedelta(days=365)
    else:
        expires = now + timedelta(minutes=max(1, duration_minutes))

    existing_stmt = select(PlayerBuff).where(and_(
        PlayerBuff.player_id == player.telegram_id,
        PlayerBuff.buff_type == buff_type,
        # Never merge into a Formação's row: extending its clock at pill price
        # is the value leak the formation anti-stack refusal exists to prevent,
        # and for the coexist types (FORMATION_PILL_COEXIST_TYPES) the pill
        # must live as its OWN row so the tick's diminishing stack governs the
        # pair. NULL-safe: legacy rows without source are still merge targets.
        or_(PlayerBuff.source.is_(None), PlayerBuff.source.notlike("formation:%")),
    )).with_for_update()
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()

    if existing:
        if not permanent_until_triggered:
            remaining_seconds = max(0, (existing.expires_at - now).total_seconds())
            existing.expires_at = now + timedelta(seconds=remaining_seconds + duration_minutes * 60)
        if buff_value > existing.buff_value:
            existing.buff_value = buff_value
        existing.source = source
        # v14.5 N-10: extending a buff resets its pre-expiry alert flag, so
        # the player gets a fresh DM as the new expires_at approaches.
        existing.expiry_notified = False
    else:
        session.add(PlayerBuff(
            player_id=player.telegram_id,
            buff_type=buff_type,
            buff_value=buff_value,
            source=source,
            expires_at=expires,
        ))


# Stat boost config for Qi Pills: pill_id → {stat, cap}
STAT_BOOST_CONFIG = {
    21: {"stat": "soul_strength", "cap": 80},
    22: {"stat": "perception", "cap": 65},
    23: {"stat": "luck", "cap": 50},
    24: {"stat": "soul_strength", "cap": 120},
    25: {"stat": "perception", "cap": 100},
    26: {"stat": "luck", "cap": 80},
    33: {"stat": "soul_strength", "cap": 300},  # Soul Expansion Pill (T3)
}

# D1 (v16.6, [jogador] 2026-05-31): the stat cap is on the PLAYER's stat, so once
# near the cap a high-grade craft (Divine ×3 / Heavenly ×5) was wasted — it filled
# to the same ceiling as a Normal pill. A higher-grade elixir should temper a
# DEEPER foundation, so the GRADE now raises the ceiling itself. cap stays the
# Normal (Common) ceiling; grade multiplies it. Soul Expansion: 300/375/450/600.
STAT_BOOST_GRADE_CAP_MULT = {"normal": 1.0, "perfect": 1.25, "divine": 1.5, "heavenly": 2.0}


# ─── purity_boost: UMA verdade do ganho (QoL-Feedback 2026-07-29, report ─────
# [jogador] "Pureza +0"). O apply E os previews (chat ℹ️ _show_pill_detail +
# api_pill_info do mini) compõem o número por esta função — o preview antigo
# fazia int(effect_value × potency) = int(0.05×N) = 0 nas duas superfícies.
PILL_BUFF_POTENCY = {"normal": 1.0, "perfect": 1.3, "divine": 1.6, "heavenly": 2.2}
# BUGFIX 2026-07-07: "sacred" faltava (fallback 1.0 = pior que "low").
# Conservador: sacred == perfect (3.0); buff acima disso = decisão de balance.
PURITY_FQ_MULT = {"low": 1.0, "medium": 1.5, "high": 2.0, "perfect": 3.0, "sacred": 3.0}
PURITY_CB_SCALE = 10000


def purity_gain(effect_value, quality: str, effectiveness: float,
                foundation_quality, fac_pot_mult: float = 1.0) -> int:
    """Cultivation-base gain of a purity_boost pill — mirror-proof: the apply
    branch below calls this, so any preview using it equals the roll exactly."""
    buff_potency = PILL_BUFF_POTENCY.get((quality or "normal").lower(), 1.0)
    fq_mult = PURITY_FQ_MULT.get(foundation_quality, 1.0)
    return int(float(effect_value or 0) * buff_potency * float(effectiveness)
               * fq_mult * float(fac_pot_mult) * PURITY_CB_SCALE)


def stat_boost_cap_state(player, pill, quality: str = "normal"):
    """QoL-Feedback 2 2026-07-30 (report [jogador]): pílula de stat no cap era
    CONSUMIDA com efeito zero — os 3 fluxos de uso debitavam o inventário
    ANTES do apply, e o `at_cap` do apply não devolve o item.

    Consultar ANTES do débito. None se a pílula não é stat_boost com config;
    senão {stat, cap, current, at_cap}. O cap escala com o GRAU da craft
    (STAT_BOOST_GRADE_CAP_MULT), igual ao apply — mesmo teto, mesma verdade.
    O `at_cap` interno do apply continua como backstop de corrida."""
    if getattr(pill, "effect_type", None) != "stat_boost":
        return None
    config = STAT_BOOST_CONFIG.get(pill.id)
    if not config:
        return None
    cap = int(config["cap"] * STAT_BOOST_GRADE_CAP_MULT.get((quality or "normal").lower(), 1.0))
    current = int(getattr(player, config["stat"], 0) or 0)
    return {"stat": config["stat"], "cap": cap, "current": current,
            "at_cap": current >= cap}


#: Os tipos de pílula que o LOTE cobre. Só "consumível de reposição" — os
#: únicos onde mil unidades fazem sentido (report [jogador] 06/08). Fora, de
#: propósito: `qi_capacity` (resistência a remédio é qi_capacity-only; mexer no
#: lote dela mexe no cap 300) e tudo o que é temporizado (`duration_minutes>0`),
#: onde 50 usos seriam 49 desperdícios silenciosos.
BULK_REFILL_TYPES: frozenset[str] = frozenset({"qi_restore", "hp_restore"})

#: A Supreme Healing Pill (id 30) é a ÚNICA que passa do teto: enche o HP e põe
#: +10% de escudo por cima (`apply_pill_effect`). Logo, para ELA, "HP cheio" NÃO
#: é "não faz nada" — e um guard que só olhasse `get_current_hp >= get_max_hp`
#: recusaria o lote onde o uso unitário funcionaria (dead-end novo, Lei §1).
#: As duas pontas — o guard e o apply — leem daqui: uma verdade, um número.
HP_SHIELD_PILL_ID = 30
HP_SHIELD_CEILING_MULT = 1.10


async def refill_cap_state(session, player, pill):
    """QoL-Feedback 07/08 (report [jogador]) — o irmão de `stat_boost_cap_state`
    para os consumíveis de REPOSIÇÃO.

    Consultar ANTES do débito de cada iteração do lote: cheio ⇒ o lote pára e as
    restantes ficam no anel (nunca queimadas com efeito zero). None quando a
    pílula não é de reposição.

    ⚠️ O teto do qi é a capacidade **EFETIVA** (`get_effective_qi_capacity` —
    raw + `qi_flat` de equipamento × multiplicador de têmpera), nunca
    `player.qi_capacity` cru: a regeneração enche o qi PARA ALÉM do cru em quem
    tem têmpera/equipamento, e um gate pelo cru diria "cheio" para sempre. É a
    mesma conta que o ramo `qi_restore` de `apply_pill_effect` faz — e tem de
    continuar a ser, senão o lote recusa onde o uso unitário funcionaria.

    ⚠️ O HP é a EXCEÇÃO declarada à regra da casa "ler HP só por
    `get_current_hp`": aqui o valor tem de vir CRU de `player.current_hp`,
    porque `get_current_hp` faz `min(current, max)` e apagaria o escudo da
    Supreme Healing Pill — um jogador já escudado pareceria "exatamente cheio"
    para sempre. O teto também é POR PÍLULA (`HP_SHIELD_*`), senão o guard
    recusava o lote da id 30 no HP cheio, onde o uso unitário ainda dá escudo."""
    etype = getattr(pill, "effect_type", None)
    if etype not in BULK_REFILL_TYPES:
        return None
    try:
        if etype == "qi_restore":
            from core.game_logic import get_effective_qi_capacity
            cap = float(await get_effective_qi_capacity(session, player))
            cur = float(getattr(player, "qi", 0) or 0)
            return {"kind": "qi", "cap": cap, "current": cur, "at_cap": cur >= cap}
        from core.combat_engine import get_max_hp
        max_hp = float(get_max_hp(player))
        # ⚠️ O teto desta pílula, não o teto genérico: a id 30 sobe até
        # `max × 1.10` com o escudo. E o `current` tem de ser LIDO CRU —
        # `get_current_hp` faz `min(current_hp, max_hp)` e apagaria o escudo,
        # fazendo um jogador já escudado parecer "exatamente cheio" para sempre.
        cap = max_hp * (HP_SHIELD_CEILING_MULT
                        if getattr(pill, "id", None) == HP_SHIELD_PILL_ID else 1.0)
        raw = getattr(player, "current_hp", None)
        cur = max_hp if raw is None else float(raw)   # NULL no DB = HP cheio
        return {"kind": "hp", "cap": cap, "current": cur, "at_cap": cur >= cap}
    except Exception:
        # Fail-OPEN: em dúvida, deixa o lote correr — o `at_cap` interno do
        # apply continua como backstop e devolve `value: 0`. Recusar por causa
        # de um erro de leitura seria inventar um dead-end (Lei §1).
        logger.warning("refill_cap_state failed player=%s pill=%s",
                       getattr(player, "telegram_id", "?"), getattr(pill, "id", "?"),
                       exc_info=True)
        return None


async def apply_pill_effect(session: AsyncSession, player: Player, pill: PillCatalog, quality: str = "normal", effectiveness: float = 1.0):
    potency = CRAFT_RESULTS.get(quality, CRAFT_RESULTS["success"])["potency_mult"]
    # Gentler scaling for multiplier-valued buffs.
    # Heavenly was missing from the dict — fell through to default 1.0 — meaning
    # a Heavenly Soul Clarity Pill restored the same Qi/HP and gave the same
    # buff magnitude as a Normal one. Players who waited weeks for the pill
    # tribulation got nothing extra over a basic craft.
    buff_potency = PILL_BUFF_POTENCY.get(quality, 1.0)

    # v14.13b BUGFIX ([jogador] 2026-05-12): Demonic faction's `pill_potency_bonus`
    # was only being applied to alchemy CRAFT success chance (line ~287).
    # Players reasonably expected it to also amplify the EFFECT magnitude of
    # consumed pills ("brew potent pills" — faction tag). Apply it here as a
    # multiplicative boost on top of quality + effectiveness scaling. Only
    # raises the BONUS portion of multiplier buffs (keeps base 1.0); raw flat
    # values are scaled directly.
    from core.faction_engine import get_faction_bonuses
    _fac_bonuses = await get_faction_bonuses(session, player.telegram_id)
    fac_pot = float(_fac_bonuses.get("pill_potency_bonus", 0.0) or 0.0)
    fac_pot_mult = 1.0 + max(0.0, fac_pot)

    # 名 2026-09-14 — o `source` do buff e' TEXTO QUE O JOGADOR LE': a caixa de
    # avisos desenha-o em `_pretty_label` (core/webserver.py) e a aba de alquimia
    # em `handlers/alchemy.py`. Ficava em ingles cru ("Minor Healing Pill
    # (perfect)") para os 125 jogadores pt do main.
    #
    # Traduz-se na ESCRITA, e nao na leitura, por uma razao medida: o `source` e'
    # uma string livre, sem id, e a coluna ja' tem rows gravadas — por-lhe um id
    # seria mudar a forma do payload e varrer TODOS os consumidores. Escrever ja'
    # traduzido e' seguro aqui porque quem LE' este buff e' sempre o DONO dele
    # (nao e' um log de dois espectadores como o `combat_log`), e a unica
    # imperfeicao que sobra e' um buff criado antes de o jogador mudar de lingua,
    # que expira sozinho.
    # ⚠️ O `notlike("formation:%")` do merge continua a valer: um nome de
    # pilula traduzido nunca comeca por "formation:".
    _pill_lang = (getattr(player, "language", None) or "pt").lower()
    _pill_src = f"{catalog_name(_pill_lang, 'pill', pill)} ({quality})"

    if pill.effect_type == "stat_boost":
        config = STAT_BOOST_CONFIG.get(pill.id)
        if not config:
            return {"type": "stat_boost", "at_cap": True, "stat": "unknown", "cap": 0}
        stat_name = config["stat"]
        base_cap = config["cap"]
        # D1: grade raises the ceiling (Normal 1.0 / Perfeito 1.25 / Divino 1.5 /
        # Celestial 2.0). The effective cap is what the player can actually reach
        # with THIS pill's grade — a higher-grade craft pushes the soul further.
        cap = int(base_cap * STAT_BOOST_GRADE_CAP_MULT.get(quality, 1.0))
        amount = int(pill.effect_value * potency * effectiveness * fac_pot_mult)
        current = getattr(player, stat_name, 0)
        if current >= cap:
            return {"type": "stat_boost", "at_cap": True, "stat": stat_name, "cap": cap, "base_cap": base_cap}
        new_val = min(current + amount, cap)
        actual_gain = new_val - current
        setattr(player, stat_name, new_val)
        return {"type": "stat_boost", "at_cap": False, "stat": stat_name, "gain": actual_gain, "new_value": new_val, "cap": cap, "base_cap": base_cap}

    if pill.effect_type == "cb_instant":
        cb_gain = pill.effect_value * potency * effectiveness * fac_pot_mult
        player.cultivation_base += cb_gain
        return {"type": "cb_instant", "value": cb_gain, "effectiveness": effectiveness}

    if pill.effect_type == "qi_capacity":
        gain = pill.effect_value * potency * effectiveness * fac_pot_mult
        player.qi_capacity += gain
        return {"type": "qi_capacity", "value": gain, "effectiveness": effectiveness}

    if pill.effect_type == "qi_restore":
        # Use effective_qi_cap (qi_capacity + equipment qi_flat) * body_tempering_mult,
        # mirroring core.game_logic cultivation_tick. Without this, players whose qi
        # grew above raw qi_capacity (via equipment/tempering) would have their qi
        # clamped DOWN by min(), producing negative "restored" values — observed in
        # prod when a player lost ~380K qi to a Qi Amass Pill (2026-05-06).
        from database.models import PlayerArtifact
        from core.game_logic import get_player_equipment_stats
        from core.body_tempering_engine import get_tempering_multiplier
        _arts = (await session.execute(
            select(PlayerArtifact).where(PlayerArtifact.player_id == player.telegram_id)
        )).scalars().all()
        _eq_stats = get_player_equipment_stats(_arts) if _arts else None
        _qi_flat = (_eq_stats or {}).get("qi_flat", 0)
        _temp_mult = get_tempering_multiplier(getattr(player, "body_tempering_level", 0))
        effective_qi_cap = (player.qi_capacity + _qi_flat) * _temp_mult
        restore = int(pill.effect_value * buff_potency * effectiveness * fac_pot_mult)
        old_qi = player.qi
        if old_qi >= effective_qi_cap:
            return {"type": "qi_restore", "value": 0, "at_cap": True, "effectiveness": effectiveness}
        player.qi = min(old_qi + restore, effective_qi_cap)
        actual = int(player.qi - old_qi)
        return {"type": "qi_restore", "value": actual, "effectiveness": effectiveness}

    if pill.effect_type == "hp_restore":
        from core.combat_engine import get_max_hp, get_current_hp, restore_hp_pct, restore_hp
        pct = pill.effect_value * buff_potency * effectiveness * fac_pot_mult
        # MV-7 — 🩺 Médico: cura de pílula HP ×(1+bônus do tier) em SI MESMO
        # (o heal_ally do profession_engine usa a mesma curva no alvo).
        # Gated (0.0 com flag OFF → byte-idêntico).
        _prof_heal = 0.0
        try:
            from core.profession_engine import medic_heal_bonus
            _prof_heal = float(medic_heal_bonus(player) or 0.0)
        except Exception:
            _prof_heal = 0.0
        pct *= (1.0 + _prof_heal)
        restored = restore_hp_pct(player, pct)
        result_data = {"type": "hp_restore", "value": int(restored), "pct": int(pct * 100), "effectiveness": effectiveness}
        if _prof_heal > 0.0:
            result_data["prof_heal_bonus"] = _prof_heal
        # Supreme Healing Pill: +10% shield (overheal above max). O id e o teto
        # vêm das constantes acima — o guard do LOTE (`refill_cap_state`) lê os
        # mesmos números, senão ele recusaria onde isto ainda faz efeito.
        if pill.id == HP_SHIELD_PILL_ID:
            max_hp = get_max_hp(player)
            shield = max_hp * (HP_SHIELD_CEILING_MULT - 1.0) * buff_potency * effectiveness * fac_pot_mult
            player.current_hp = min((player.current_hp if player.current_hp is not None else max_hp) + shield,
                                    max_hp * HP_SHIELD_CEILING_MULT)
            result_data["shield"] = int(shield)
        return result_data

    if pill.effect_type == "body_tempering_progress":
        from core.body_tempering_engine import add_tempering_progress
        amount = int(pill.effect_value * potency * effectiveness * fac_pot_mult)
        actual = add_tempering_progress(player, amount)
        return {"type": "body_tempering_progress", "value": actual, "requested": amount, "effectiveness": effectiveness}

    if pill.effect_type == "foundation_reroll":
        # Foundation Repair Pill (id=34) — uses the original trial-based reroll
        # (3 stat-checks against scaled thresholds, no quality input).
        from core.foundation_engine import calculate_foundation_trial, get_scaled_thresholds  # noqa: F401
        from core.game_logic import calculate_total_stats
        if player.foundation_quality is None:
            return {"type": "foundation_reroll", "rerolled": False, "reason": "no_foundation"}
        # GUARD 2026-07-07 (hotfix "A Volta"): o trial desta pílula só vai até
        # "perfect" — um jogador SACRED que a use PERDERIA o tier pináculo
        # permanentemente. Mesmo princípio anti-downgrade do eternal (id=41).
        if player.foundation_quality == "sacred":
            return {"type": "foundation_reroll", "rerolled": False, "reason": "sacred_protected"}
        old_quality = player.foundation_quality
        # calculate_foundation_trial expects (player, total_stats); read stats
        # off the player directly (no equip/companion bonuses — keeps the old
        # pill cheap, doesn't double-count vs. its trial-original semantics).
        total_stats = calculate_total_stats(player)
        trial = calculate_foundation_trial(player, total_stats)
        new_quality = trial["quality"]
        player.foundation_quality = new_quality
        # Review adversarial 03/08 — a irmã (id 34) sofre do MESMO problema:
        # a prova pode devolver a mesma qualidade (ou pior) e o texto celebrava.
        from core.foundation_engine import foundation_delta
        return {"type": "foundation_reroll", "rerolled": True,
                "old": old_quality, "new": new_quality,
                **foundation_delta(old_quality, new_quality)}

    if pill.effect_type == "eternal_foundation_reroll":
        # v14.4 D-1c: Eternal Foundation Pill (id=41). Quality of the craft
        # picks a different reroll table; Heavenly grade with a current
        # Perfect foundation awakens SACRED tier (the pinnacle).
        from core.foundation_engine import (
            PILL_REROLL_TABLES, roll_from_table, FOUNDATION_QUALITIES,
        )
        old_quality = player.foundation_quality
        sacred_awakened = False

        if quality == "heavenly" and old_quality == "perfect":
            # Special branch: Sacred Foundation — only path to the new tier.
            new_quality = "sacred"
            sacred_awakened = True
        else:
            table = PILL_REROLL_TABLES.get(quality, PILL_REROLL_TABLES["normal"])
            new_quality = roll_from_table(table)

        # Don't downgrade Sacred (would be cruel and lore-breaking — Sacred
        # is the pinnacle, you don't lose it from re-using the pill).
        if old_quality == "sacred":
            new_quality = "sacred"
            sacred_awakened = False

        player.foundation_quality = new_quality
        new_mult = FOUNDATION_QUALITIES.get(new_quality, FOUNDATION_QUALITIES["low"])["stat_mult"]
        # Review adversarial 03/08 — `direction`/`old_mult` são a diferença entre
        # dizer a verdade e celebrar o nada: `old == new` é o resultado MAIS
        # PROVÁVEL (70% numa divine sobre Perfeita) e era anunciado como
        # "Fundação Reforjada!"; um downgrade permanente vinha em card verde.
        # Keys ADITIVAS — quem só lê old/new/sacred_awakened continua igual.
        from core.foundation_engine import foundation_delta
        _delta = foundation_delta(old_quality, new_quality)
        return {
            "type": "eternal_foundation_reroll",
            "rerolled": True,
            "old": old_quality,
            "new": new_quality,
            "sacred_awakened": sacred_awakened,
            "new_mult": new_mult,
            "quality": quality,
            **_delta,
        }

    if pill.effect_type == "core_essence":
        from core.golden_core_engine import add_core_essence, get_essence_cap
        amount = int(pill.effect_value * potency * effectiveness * fac_pot_mult)
        # Only works if core not yet formed and player is at realm 2
        if player.realm != 2 or getattr(player, "core_quality", None):
            return {"type": "core_essence", "value": 0, "reason": "not_applicable"}
        actual = add_core_essence(player, amount)
        return {"type": "core_essence", "value": actual, "total": player.core_essence or 0, "effectiveness": effectiveness}

    if pill.effect_type == "purity_boost":
        gain = purity_gain(pill.effect_value, quality, effectiveness,
                           player.foundation_quality, fac_pot_mult)
        player.cultivation_base += gain
        return {"type": "purity_boost", "value": gain, "effectiveness": effectiveness}

    if pill.effect_type == "revive":
        await _create_or_extend_buff(
            session, player, "revive", 1.0, duration_minutes=0,
            source=_pill_src, permanent_until_triggered=True,
        )
        return {"type": "revive", "value": 1, "effectiveness": effectiveness}

    if pill.effect_type == "all_boost":
        duration = pill.duration_minutes or 240
        buff_value = pill.effect_value * buff_potency * effectiveness * fac_pot_mult
        # Onda 5 Fase 2 review: the per-type pill conflict gates compare against
        # the literal 'all_boost' and never see these 5 constituent types, so
        # without this guard the composite pill would EXTEND an active Formação
        # row's clock at max value (the exact leak the formation anti-stack
        # refusal exists to prevent). Skip types a Formação currently holds.
        now_ts = datetime.now(timezone.utc)
        skipped = []
        for bt in ["bp_boost", "soul_boost", "perception_boost", "defense_boost", "luck_boost"]:
            existing = (await session.execute(select(PlayerBuff).where(and_(
                PlayerBuff.player_id == player.telegram_id,
                PlayerBuff.buff_type == bt,
                PlayerBuff.expires_at > now_ts,
            )))).scalars().first()
            if existing is not None and (existing.source or "").startswith("formation:"):
                skipped.append(bt)
                continue
            await _create_or_extend_buff(session, player, bt, buff_value, duration_minutes=duration, source=_pill_src)
        return {"type": "all_boost", "value": buff_value, "duration_minutes": duration,
                "effectiveness": effectiveness, "skipped_formation_types": skipped}

    if pill.effect_type == "dao_fragment_chance":
        duration = pill.duration_minutes or 120
        buff_value = pill.effect_value * buff_potency * effectiveness * fac_pot_mult
        await _create_or_extend_buff(session, player, "dao_fragment_chance", buff_value, duration_minutes=duration, source=_pill_src)
        return {"type": "dao_fragment_chance", "value": buff_value, "duration_minutes": duration, "effectiveness": effectiveness}

    # Generic temporary buffs (cb_boost, soul_boost, bp_boost, breakthrough_boost, etc.)
    # Heavenly was missing here too — buff_value silently fell through to base
    # pill.effect_value, making a Heavenly Soul Clarity Pill identical to Normal
    # for perception_boost and friends. Player report 2026-05-06: "Minha heavenly
    # pill bugou? mostra mesma magnitude que a base".
    buff_value = pill.effect_value
    if quality == "perfect":
        buff_value = 1 + (pill.effect_value - 1) * 1.5 if pill.effect_value > 1 else pill.effect_value * 1.5
    elif quality == "divine":
        buff_value = 1 + (pill.effect_value - 1) * 3.0 if pill.effect_value > 1 else pill.effect_value * 3.0
    elif quality == "heavenly":
        buff_value = 1 + (pill.effect_value - 1) * 5.0 if pill.effect_value > 1 else pill.effect_value * 5.0

    # Apply resistance: scale the bonus portion by effectiveness (keep base of 1.0, reduce bonus)
    if effectiveness < 1.0 and buff_value > 1.0:
        buff_value = 1.0 + (buff_value - 1.0) * effectiveness

    # v14.13b BUGFIX: Demonic faction +20% pill potency — amplify the BONUS
    # portion of multiplier-form buffs (keeps base 1.0). For non-multiplier
    # generic buffs (rare — most timed buffs are multiplier form here), scale
    # the raw value directly so the player sees a meaningful difference too.
    if fac_pot_mult > 1.0:
        if buff_value > 1.0:
            buff_value = 1.0 + (buff_value - 1.0) * fac_pot_mult
        else:
            buff_value = buff_value * fac_pot_mult

    # Heavenly grade also doubles duration — meaningful payoff for surviving the
    # pill tribulation mini-game.
    base_duration = max(1, pill.duration_minutes)
    if quality == "heavenly":
        duration = base_duration * 2
    elif quality == "divine":
        duration = int(base_duration * 1.5)
    else:
        duration = base_duration
    await _create_or_extend_buff(session, player, pill.effect_type, buff_value, duration_minutes=duration, source=_pill_src)

    return {
        "type": pill.effect_type,
        "value": buff_value,
        "duration_minutes": duration,
        "quality": quality,
        "effectiveness": effectiveness,
    }


async def get_active_buffs(session: AsyncSession, player_id: int) -> list[PlayerBuff]:
    now = datetime.now(timezone.utc)

    expired_stmt = select(PlayerBuff).where(and_(
        PlayerBuff.player_id == player_id,
        PlayerBuff.expires_at <= now,
    ))
    expired = (await session.execute(expired_stmt)).scalars().all()
    for buff in expired:
        await session.delete(buff)

    stmt = select(PlayerBuff).where(and_(
        PlayerBuff.player_id == player_id,
        PlayerBuff.expires_at > now,
    )).order_by(PlayerBuff.expires_at)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def get_buff_cb_multiplier(buffs: list[PlayerBuff]) -> float:
    mult = 1.0
    for buff in buffs:
        if buff.buff_type == "cb_boost":
            mult *= buff.buff_value
        elif buff.buff_type == "heartbreak":
            mult *= buff.buff_value
        # NOTE: perception_boost is applied separately on perception (not CB) —
        # see calculate_total_stats() call sites in handlers/tribulation.py and
        # core/scheduler.py. DO NOT include it here.
    return mult


# ─── Medicine Resistance ─────────────────────────────────────────────────────

# Thresholds: uses < 3 → 100%, < 6 → 75%, < 9 → 50%, 9+ → 25%
_RESISTANCE_TABLE = [
    (3, 1.00),
    (6, 0.75),
    (9, 0.50),
    (float("inf"), 0.25),
]


def _effectiveness_from_count(count: int) -> float:
    for threshold, eff in _RESISTANCE_TABLE:
        if count < threshold:
            return eff
    return 0.25


def get_resistance_display(count: int) -> dict:
    """Return dict with effectiveness, next_threshold, next_pct for UI."""
    eff = _effectiveness_from_count(count)
    pct = int(eff * 100)
    # Find next threshold
    next_threshold = None
    next_pct = None
    for threshold, next_eff in _RESISTANCE_TABLE:
        if count < threshold and next_eff < eff:
            next_threshold = threshold
            next_pct = int(next_eff * 100)
            break
    # Simpler: walk the table to find where count is and what's next
    for i, (thr, e) in enumerate(_RESISTANCE_TABLE):
        if count < thr:
            # This is the current tier
            if i + 1 < len(_RESISTANCE_TABLE):
                next_threshold = thr
                next_pct = int(_RESISTANCE_TABLE[i + 1][1] * 100) if i + 1 < len(_RESISTANCE_TABLE) else pct
            break
    return {"effectiveness": eff, "pct": pct, "uses": count, "next_threshold": next_threshold, "next_pct": next_pct}


def _pill_has_resistance(pill) -> bool:
    """F ([jogador]/owner 2026-06-16): medicine resistance is a safeguard against
    abuse of the UNCAPPED qi-capacity pill (the documented combat-degeneration
    root cause — see project-combat-rebalance-blocker). Every OTHER pill is
    either a CAPPED stat (Soul/BP/perception/luck — the cap already prevents
    abuse, so resistance there is redundant punishment) or a consumable/buff.
    So resistance applies ONLY to `qi_capacity` pills; all others are exempt.
    Classified structurally by `pill.effect_type`, never by hardcoded id.
    `getattr` fallback → exempt (fail-open: never crash a consume path)."""
    return getattr(pill, "effect_type", None) == "qi_capacity"


async def get_pill_effectiveness(session: AsyncSession, player_id: int, pill) -> float:
    """Returns effectiveness (0.25 to 1.0) based on number of uses this realm.

    Takes the PillCatalog row (not the id) so the qi-capacity exemption can be
    evaluated at consume time — meaning old counters on now-exempt pills are
    silently ignored on the next dose (retroactive, no manual reset)."""
    if not _pill_has_resistance(pill):
        return 1.0
    from database.models import PlayerMedicineResistance
    stmt = select(PlayerMedicineResistance).where(
        PlayerMedicineResistance.player_id == player_id,
        PlayerMedicineResistance.pill_id == pill.id,
    )
    resistance = (await session.execute(stmt)).scalar_one_or_none()
    if not resistance:
        return 1.0
    return _effectiveness_from_count(resistance.consumption_count)


async def get_all_pill_resistances(session: AsyncSession, player_id: int) -> dict:
    """Returns {pill_id: consumption_count} for all pills with tracked resistance."""
    from database.models import PlayerMedicineResistance
    stmt = select(PlayerMedicineResistance).where(PlayerMedicineResistance.player_id == player_id)
    rows = (await session.execute(stmt)).scalars().all()
    return {r.pill_id: r.consumption_count for r in rows}


async def increment_pill_usage(session: AsyncSession, player_id: int, pill):
    """Increments the pill usage counter using a PostgreSQL upsert.

    F (2026-06-16): only `qi_capacity` pills accrue resistance — exempt pills
    don't even track usage (no stale counters to ignore later)."""
    if not _pill_has_resistance(pill):
        return
    from database.models import PlayerMedicineResistance
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(PlayerMedicineResistance).values(
        player_id=player_id, pill_id=pill.id, consumption_count=1
    ).on_conflict_do_update(
        constraint="uq_player_pill_resistance",
        set_={"consumption_count": PlayerMedicineResistance.consumption_count + 1},
    )
    await session.execute(stmt)


async def reset_medicine_resistance(session: AsyncSession, player_id: int):
    """Resets all medicine resistance counters (called on realm-up)."""
    from database.models import PlayerMedicineResistance
    await session.execute(
        delete(PlayerMedicineResistance).where(PlayerMedicineResistance.player_id == player_id)
    )


# ─── Alchemy Energy ──────────────────────────────────────────────────────────

async def get_alchemy_tier(session: AsyncSession, player_id: int) -> int:
    """O tier de Alquimia SEM criar row (leitura pura).

    Existe separado de `get_or_create_alchemy_skill` porque os consumidores de
    energia são telas e varredores — o notificador percorre TODOS os jogadores,
    e criar uma skill row a cada passagem seria uma tempestade de escritas.
    Quem nunca sintetizou não tem row: tier 1, o mesmo jogo de ontem.
    """
    tier = (await session.execute(
        select(PlayerAlchemySkill.tier).where(PlayerAlchemySkill.player_id == player_id)
    )).scalar_one_or_none()
    return int(tier or 1)


async def get_alchemy_tiers_bulk(
    session: AsyncSession, player_ids: list[int]
) -> dict[int, int]:
    """Idem, para varredores: UMA query em vez de N (default 1 para os ausentes)."""
    if not player_ids:
        return {}
    rows = (await session.execute(
        select(PlayerAlchemySkill.player_id, PlayerAlchemySkill.tier)
        .where(PlayerAlchemySkill.player_id.in_(player_ids))
    )).all()
    return {int(pid): int(tier or 1) for pid, tier in rows}


def get_flame_mastery(alchemy_tier: int = 1) -> tuple[int, float]:
    """火候 — (bonus_de_tecto, multiplicador_de_regen) do tier de Alquimia.

    O eixo APRENDIDO da energia. Tier 1 devolve (0, 1.0), portanto quem nunca
    subiu de posto vê exactamente o jogo de ontem — nada regride.
    """
    tier = max(1, min(int(alchemy_tier or 1), MAX_ALCHEMY_TIER))
    return (
        int(ALCHEMY_ENERGY_TIER_MAX_BONUS.get(tier, 0)),
        float(ALCHEMY_ENERGY_TIER_REGEN_MULT.get(tier, 1.0)),
    )


def format_regen_minutes(regen_minutes: float) -> str:
    """O ritmo da chama para o jogador: "3" / "2.5" / "2.04" → "3" / "2,5" ...

    O multiplicador do tier produz floats (3.0 × 0.68 = 2.04); o placeholder
    `{regen}` das 3 línguas já existia e recebia int — aqui só muda o VALOR,
    nunca a chave (lição: notificação nunca ganha placeholder novo).
    """
    val = round(float(regen_minutes), 2)
    if abs(val - round(val)) < 0.005:
        return str(int(round(val)))
    return f"{val:.2f}".rstrip("0").rstrip(".")


def get_alchemy_energy(
    player: Player, vip_level: int = 0, alchemy_tier: int = 1
) -> tuple[int, int, float]:
    """Returns (current_energy, max_energy, regen_minutes_per_point).
    Computes on-the-fly regen without touching the DB.

    2026-08-18 (report do [jogador]): `alchemy_tier` é o eixo GANHO A JOGAR. Fica com
    default 1 para nenhum stub/chamador antigo rebentar — mas TODO call site
    real passa o tier, senão uma tela mostra 100 e a outra 240 (mentira de
    display). Ver POWER-of-truth: quem sabe o tier é quem o passa.
    """
    tier_max_bonus, tier_regen_mult = get_flame_mastery(alchemy_tier)
    energy_max = (
        (player.alchemy_energy_max or ALCHEMY_ENERGY_BASE)
        + ALCHEMY_ENERGY_VIP_MAX_BONUS.get(vip_level, 0)
        + tier_max_bonus
    )
    regen_minutes = max(
        ALCHEMY_ENERGY_REGEN_FLOOR,
        ALCHEMY_ENERGY_VIP_REGEN.get(vip_level, ALCHEMY_ENERGY_REGEN_MINUTES) * tier_regen_mult,
    )

    now = datetime.now(timezone.utc)
    last_update = player.alchemy_energy_updated_at
    stored = player.alchemy_energy if player.alchemy_energy is not None else energy_max

    if last_update is not None and stored < energy_max:
        elapsed_minutes = (now - last_update).total_seconds() / 60
        regen_amount = floor(elapsed_minutes / regen_minutes)
        stored = min(energy_max, stored + regen_amount)

    return stored, energy_max, regen_minutes


def consume_alchemy_energy(
    player: Player, cost: int, vip_level: int = 0, alchemy_tier: int = 1
) -> tuple[bool, int, int]:
    """Check and consume energy. Returns (ok, new_current, max_energy).
    Mutates player fields and must be followed by session.commit().
    """
    current, energy_max, regen_minutes = get_alchemy_energy(player, vip_level, alchemy_tier)

    if current < cost:
        return False, current, energy_max

    now = datetime.now(timezone.utc)
    # Determine the exact leftover regen time to not waste partial ticks
    last_update = player.alchemy_energy_updated_at
    stored = player.alchemy_energy if player.alchemy_energy is not None else energy_max

    if last_update is not None and stored < energy_max:
        elapsed_seconds = (now - last_update).total_seconds()
        regen_seconds = regen_minutes * 60
        ticks_elapsed = floor(elapsed_seconds / regen_seconds)
        remainder_seconds = elapsed_seconds - ticks_elapsed * regen_seconds
        # Adjust updated_at to preserve the partial tick
        now = now - timedelta(seconds=remainder_seconds)

    new_energy = current - cost
    player.alchemy_energy = new_energy
    player.alchemy_energy_updated_at = now
    return True, new_energy, energy_max


async def give_starter_cauldron(session: AsyncSession, player_id: int):
    existing = await get_player_cauldrons(session, player_id)
    if existing:
        return

    session.add(PlayerCauldron(
        player_id=player_id,
        cauldron_id=1,
        is_equipped=True,
        durability=100,
    ))


# ─── Pill Mastery ─────────────────────────────────────────────────────────────

MASTERY_LEVELS = {
    1: {"crafts_req": 0, "fail_reduction": 0.0},
    2: {"crafts_req": 10, "fail_reduction": 5.0},
    3: {"crafts_req": 30, "fail_reduction": 12.0},
    4: {"crafts_req": 75, "fail_reduction": 20.0},
    5: {"crafts_req": 150, "fail_reduction": 30.0},
}
MAX_MASTERY_LEVEL = 5


def get_mastery_name(level: int, lang: str) -> str:
    names = {
        1: {"en": "Initiate", "pt": "Iniciante", "es": "Iniciado"},
        2: {"en": "Apprentice", "pt": "Aprendiz", "es": "Aprendiz"},
        3: {"en": "Skilled", "pt": "Habilidoso", "es": "Habilidoso"},
        4: {"en": "Expert", "pt": "Especialista", "es": "Especialista"},
        5: {"en": "Master", "pt": "Mestre", "es": "Maestro"},
    }
    return names.get(level, names[1]).get(lang, names.get(level, names[1])["en"])


async def get_or_create_pill_mastery(session: AsyncSession, player_id: int, pill_id: int) -> PlayerPillMastery:
    stmt = select(PlayerPillMastery).where(and_(
        PlayerPillMastery.player_id == player_id,
        PlayerPillMastery.pill_id == pill_id,
    ))
    mastery = (await session.execute(stmt)).scalar_one_or_none()
    if not mastery:
        mastery = PlayerPillMastery(player_id=player_id, pill_id=pill_id, mastery_level=1, crafts_count=0)
        session.add(mastery)
        await session.flush()
    return mastery


async def increment_pill_mastery(session: AsyncSession, player_id: int, pill_id: int) -> tuple[PlayerPillMastery, bool]:
    """Increment craft count and check for mastery level up. Returns (mastery, leveled_up)."""
    mastery = await get_or_create_pill_mastery(session, player_id, pill_id)
    mastery.crafts_count += 1
    leveled_up = False
    if mastery.mastery_level < MAX_MASTERY_LEVEL:
        next_req = MASTERY_LEVELS[mastery.mastery_level + 1]["crafts_req"]
        if mastery.crafts_count >= next_req:
            mastery.mastery_level += 1
            leveled_up = True
    return mastery, leveled_up


def get_mastery_bonus(mastery_level: int) -> float:
    return MASTERY_LEVELS.get(mastery_level, MASTERY_LEVELS[1])["fail_reduction"]


async def get_all_pill_masteries(session: AsyncSession, player_id: int) -> dict[int, PlayerPillMastery]:
    stmt = select(PlayerPillMastery).where(PlayerPillMastery.player_id == player_id)
    rows = (await session.execute(stmt)).scalars().all()
    return {m.pill_id: m for m in rows}


def get_mastery_next_info(mastery: PlayerPillMastery) -> dict:
    """Return info about next mastery level for UI."""
    if mastery.mastery_level >= MAX_MASTERY_LEVEL:
        return {"at_max": True, "crafts": mastery.crafts_count}
    next_req = MASTERY_LEVELS[mastery.mastery_level + 1]["crafts_req"]
    return {
        "at_max": False,
        "crafts": mastery.crafts_count,
        "next_crafts": next_req,
        "next_level": mastery.mastery_level + 1,
    }


# ─── Soul Fire ────────────────────────────────────────────────────────────────

SOUL_FIRE_MIN_REALM = 3

SOUL_FIRE_TIERS = {
    0: {"bonus": 0.0},
    1: {"bonus": 5.0, "xp_req": 0},
    2: {"bonus": 10.0, "xp_req": 500},
    3: {"bonus": 18.0, "xp_req": 2000},
    4: {"bonus": 28.0, "xp_req": 6000},
    5: {"bonus": 40.0, "xp_req": 15000},
    6: {"bonus": 50.0, "xp_req": 35000},
}
MAX_SOUL_FIRE_TIER = 6

SOUL_FIRE_NAMES = {
    0: {"en": "Dormant Ember", "pt": "Brasa Adormecida", "es": "Brasa Dormida"},
    1: {"en": "Mortal Flame", "pt": "Chama Mortal", "es": "Llama Mortal"},
    2: {"en": "Spirit Flame", "pt": "Chama Espiritual", "es": "Llama Espiritual"},
    3: {"en": "Earth Flame", "pt": "Chama Terrestre", "es": "Llama Terrestre"},
    4: {"en": "Heaven Flame", "pt": "Chama Celestial", "es": "Llama Celestial"},
    5: {"en": "Primordial Flame", "pt": "Chama Primordial", "es": "Llama Primordial"},
    6: {"en": "Dao Flame", "pt": "Chama do Dao", "es": "Llama del Dao"},
}

SOUL_FIRE_XP_REWARDS = {
    "success": 10,
    "perfect": 25,
    "divine": 60,
    "heavenly": 150,
    "failure": 2,
    "explosion": 2,
}

BEAST_CORE_FIRE_XP = {
    "common": 20,
    "rare": 50,
    "epic": 120,
    "legendary": 300,
}


def get_soul_fire_name(tier: int, lang: str) -> str:
    names = SOUL_FIRE_NAMES.get(tier, SOUL_FIRE_NAMES[0])
    return names.get(lang, names["en"])


def get_soul_fire_bonus(tier: int) -> float:
    return SOUL_FIRE_TIERS.get(tier, SOUL_FIRE_TIERS[0])["bonus"]


async def get_or_create_soul_fire(session: AsyncSession, player_id: int, realm: int) -> PlayerSoulFire:
    sf = (await session.execute(
        select(PlayerSoulFire).where(PlayerSoulFire.player_id == player_id)
    )).scalar_one_or_none()
    if not sf:
        initial_tier = 1 if realm >= SOUL_FIRE_MIN_REALM else 0
        sf = PlayerSoulFire(player_id=player_id, fire_tier=initial_tier, fire_exp=0)
        session.add(sf)
        await session.flush()
    return sf


def _check_soul_fire_levelup(sf: PlayerSoulFire) -> bool:
    if sf.fire_tier >= MAX_SOUL_FIRE_TIER:
        return False
    next_req = SOUL_FIRE_TIERS[sf.fire_tier + 1]["xp_req"]
    if sf.fire_exp >= next_req:
        sf.fire_tier += 1
        return True
    return False


async def grant_soul_fire_xp(session: AsyncSession, player_id: int, realm: int, result_type: str) -> tuple[PlayerSoulFire, bool]:
    """Grant soul fire XP from crafting. Returns (soul_fire, leveled_up)."""
    if realm < SOUL_FIRE_MIN_REALM:
        sf = await get_or_create_soul_fire(session, player_id, realm)
        return sf, False
    sf = await get_or_create_soul_fire(session, player_id, realm)
    if sf.fire_tier == 0:
        sf.fire_tier = 1
    xp = SOUL_FIRE_XP_REWARDS.get(result_type, 0)
    sf.fire_exp += xp
    leveled_up = _check_soul_fire_levelup(sf)
    return sf, leveled_up


# ─── Pill Tribulation ────────────────────────────────────────────────────────

PILL_TRIBULATION_CHOICES = {
    "protect":   {"success_rate": 0.70, "label_key": "pill_trib_protect"},
    "reinforce":  {"success_rate": 0.50, "label_key": "pill_trib_reinforce", "bonus_on_success": True},
    "sacrifice": {"success_rate": 0.90, "label_key": "pill_trib_sacrifice", "qi_cost_pct": 0.10},
}
PILL_TRIBULATION_ROUNDS = 3
PILL_TRIBULATION_PASS_THRESHOLD = 2  # need 2+ successes out of 3 rounds


def roll_tribulation_round(choice: str) -> bool:
    """Roll success for a pill tribulation choice. Returns True if passed."""
    config = PILL_TRIBULATION_CHOICES.get(choice)
    if not config:
        return False
    return random.random() <= config["success_rate"]


async def apply_tribulation_failure(session: AsyncSession, player: Player):
    """Apply penalties for failing the pill tribulation: -30 cauldron durability, -20% QI."""
    # -30 cauldron durability
    pc, cauldron = await get_equipped_cauldron(session, player.telegram_id)
    durability_lost = 0
    if pc:
        old_dur = pc.durability
        pc.durability = max(0, pc.durability - 30)
        durability_lost = old_dur - pc.durability

    # -20% QI
    qi_lost = int(player.qi * 0.20)
    player.qi = max(0, player.qi - qi_lost)

    return {"durability_lost": durability_lost, "qi_lost": qi_lost}


async def feed_beast_core_to_soul_fire(session: AsyncSession, player_id: int, realm: int) -> tuple[PlayerSoulFire, int, bool]:
    """Feed a generic beast core to soul fire. Returns (soul_fire, xp_gained, leveled_up)."""
    if realm < SOUL_FIRE_MIN_REALM:
        sf = await get_or_create_soul_fire(session, player_id, realm)
        return sf, 0, False

    # Check player has beast cores
    inv = (await session.execute(
        select(PlayerInventory).where(and_(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "beast_core",
            PlayerInventory.quantity > 0,
        ))
    )).scalars().first()
    if not inv:
        return None, 0, False

    inv.quantity -= 1
    if inv.quantity <= 0:
        await session.delete(inv)

    sf = await get_or_create_soul_fire(session, player_id, realm)
    if sf.fire_tier == 0:
        sf.fire_tier = 1
    xp = BEAST_CORE_FIRE_XP.get("common", 20)
    sf.fire_exp += xp
    leveled_up = _check_soul_fire_levelup(sf)
    return sf, xp, leveled_up


# ─── Recipes ─────────────────────────────────────────────────────────────────

# N-33 (v14.3 hotfix 2026-05-14): all T1 pills auto-unlock at /alquimia open.
# Previous list `[1, 2, 3, 21, 22, 23, 27]` had two bugs reported by [jogador]
# (chat 2026-05-08): (a) id=3 is Soul Strength Pill, a *T2* recipe — players
# auto-unlocked a recipe they could not craft until tier 2; (b) T1 pills 5
# (Cleansing), 6 (Qi Amass), 11 (Iron Skin), 12 (Lucky Star) were missing —
# they showed as "??? — Receita não descoberta" forever because
# `roll_recipe_drop` only ever uses `tier_range=(2, 3)` (dungeons/beasts).
# T1 is the entry tier — gating any of its recipes makes no design sense.
# Re-running ensure_starter_recipes on existing players retroactively grants
# the missing recipes via `on_conflict_do_nothing` (idempotent).
T1_PILL_IDS = [1, 2, 5, 6, 11, 12, 21, 22, 23, 27]  # Auto-unlocked for all players


async def ensure_starter_recipes(session: AsyncSession, player_id: int):
    """Ensure player has T1 pill recipes + tier-milestone signposts."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    for pill_id in T1_PILL_IDS:
        stmt = pg_insert(PlayerRecipe).values(
            player_id=player_id, item_type="pill", item_id=pill_id,
            unlocked_at=datetime.now(timezone.utc),
        ).on_conflict_do_nothing(constraint="uq_player_recipe")
        await session.execute(stmt)

    # v14.4 D-1c: auto-unlock the Eternal Foundation Pill (id=41) once the
    # player reaches alchemy tier 4 (Grandmaster). Lesson from N-34:
    # gating a recipe behind RNG drop sources that don't exist makes it
    # *invisible*. The actual difficulty here is the two T5 herbs (13/14,
    # Mahayana Nightmare + WB top-3 only) and the Heavenly craft grade —
    # the recipe being visible is the signpost, not the gate.
    skill = (await session.execute(
        select(PlayerAlchemySkill).where(PlayerAlchemySkill.player_id == player_id)
    )).scalar_one_or_none()
    if skill and skill.tier >= 4:
        stmt = pg_insert(PlayerRecipe).values(
            player_id=player_id, item_type="pill", item_id=41,
            unlocked_at=datetime.now(timezone.utc),
        ).on_conflict_do_nothing(constraint="uq_player_recipe")
        await session.execute(stmt)


async def get_unlocked_pill_ids(session: AsyncSession, player_id: int) -> set[int]:
    stmt = select(PlayerRecipe.item_id).where(and_(
        PlayerRecipe.player_id == player_id,
        PlayerRecipe.item_type == "pill",
    ))
    rows = (await session.execute(stmt)).scalars().all()
    return set(rows) | set(T1_PILL_IDS)


async def unlock_recipe(session: AsyncSession, player_id: int, item_type: str, item_id: int) -> bool:
    """Unlock a recipe. Returns True if newly unlocked, False if already had it."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(PlayerRecipe).values(
        player_id=player_id, item_type=item_type, item_id=item_id,
        unlocked_at=datetime.now(timezone.utc),
    ).on_conflict_do_nothing(constraint="uq_player_recipe")
    result = await session.execute(stmt)
    return result.rowcount > 0


async def roll_recipe_drop(session: AsyncSession, player_id: int, tier_range: tuple[int, int], chance: float) -> int | None:
    """Roll for a recipe drop. Returns pill_id if unlocked, None otherwise.

    2026-05-26 hotfix: previously queried PillCatalog on every roll. Under
    DB load, that SELECT became the unlucky statement_timeout victim
    (incident: pace037 dungeon_sweep_exec timeout). Now uses a module-level
    cache (:func:`_ensure_pill_ids_by_tier`) so the catalog data resolves
    in-memory with no DB round-trip. The only remaining query is
    :func:`get_unlocked_pill_ids` (per-player PlayerRecipe lookup), which
    is small and indexed.

    Wrapped in try/except defensively: if anything fails (cache load,
    unlocked lookup, upsert), the function returns None and the caller's
    sweep transaction continues — recipe drops are a bonus, never the
    critical path of a dungeon sweep.
    """
    if random.random() > chance:
        return None

    try:
        cache = await _ensure_pill_ids_by_tier(session)
        if not cache:
            return None

        min_tier, max_tier = tier_range
        candidate_ids: list[int] = []
        for tier in range(int(min_tier), int(max_tier) + 1):
            candidate_ids.extend(cache.get(tier, ()))
        if not candidate_ids:
            return None

        unlocked = await get_unlocked_pill_ids(session, player_id)
        locked_ids = [pid for pid in candidate_ids if pid not in unlocked]
        if not locked_ids:
            return None

        chosen_id = random.choice(locked_ids)
        await unlock_recipe(session, player_id, "pill", chosen_id)
        return chosen_id
    except Exception:
        # Recipe drops are a bonus — a failure here must NEVER abort the
        # outer sweep/dungeon/combat transaction. Log and return None.
        logger.warning(
            "roll_recipe_drop failed for player_id=%s; skipping recipe drop",
            player_id, exc_info=True,
        )
        return None


# ─── Cauldron Upgrade System ─────────────────────────────────────────────────

# Ore IDs: 1=Mortal Iron, 2=Spirit Copper, 6=Void Crystal,
#           8=Phoenix Ash, 9=Dragon Scale, 10=Celestial Iron
CAULDRON_UPGRADE_COSTS = {
    # grade_from → {ores: [(ore_id, qty), ...], stones: int, success_rate: float}
    1: {"ores": [(1, 5)], "stones": 10_000, "success_rate": 1.0},
    2: {"ores": [(1, 10), (2, 3)], "stones": 50_000, "success_rate": 0.90},
    3: {"ores": [(2, 8), (8, 2)], "stones": 200_000, "success_rate": 0.75},
    4: {"ores": [(8, 5), (9, 3)], "stones": 500_000, "success_rate": 0.60},
    5: {"ores": [(9, 10), (10, 1)], "stones": 2_000_000, "success_rate": 0.40},
    6: {"ores": [(10, 5), (6, 3)], "stones": 10_000_000, "success_rate": 0.25},
}

REPAIR_COST_PER_10 = 5000  # spirit stones per 10 durability, multiplied by tier


async def get_upgrade_cost_info(session: AsyncSession, grade: int,
                                lang: str = "pt") -> dict | None:
    """Return upgrade cost info with ore names resolved, or None if max grade."""
    from database.models import OreCatalog
    cost = CAULDRON_UPGRADE_COSTS.get(grade)
    if not cost:
        return None
    ore_details = []
    for ore_id, qty in cost["ores"]:
        ore = (await session.execute(
            select(OreCatalog).where(OreCatalog.id == ore_id)
        )).scalar_one_or_none()
        ore_details.append({
            "ore_id": ore_id,
            "qty": qty,
            "name": catalog_name(lang, "ore", ore) if ore else f"Ore #{ore_id}",
            "emoji": ore.emoji if ore else "🪨",
        })
    return {
        "ores": ore_details,
        "stones": cost["stones"],
        "success_rate": cost["success_rate"],
    }


async def check_upgrade_materials(session: AsyncSession, player_id: int, grade: int) -> dict:
    """Check if player has the required materials. Returns {ok, missing_ores, missing_stones}."""
    cost = CAULDRON_UPGRADE_COSTS.get(grade)
    if not cost:
        return {"ok": False, "error": "max_grade"}

    missing_ores = []
    for ore_id, qty_needed in cost["ores"]:
        player_ore = (await session.execute(
            select(PlayerOre).where(and_(
                PlayerOre.player_id == player_id,
                PlayerOre.ore_id == ore_id,
            ))
        )).scalar_one_or_none()
        owned = player_ore.quantity if player_ore else 0
        if owned < qty_needed:
            missing_ores.append((ore_id, qty_needed, owned))

    return {
        "ok": len(missing_ores) == 0,
        "missing_ores": missing_ores,
        "stones_needed": cost["stones"],
    }


async def upgrade_cauldron(session: AsyncSession, player: Player, pc: PlayerCauldron, cauldron: CauldronCatalog) -> dict:
    """Attempt to upgrade the equipped cauldron. Consumes materials. Returns result dict."""
    grade = cauldron.grade
    cost = CAULDRON_UPGRADE_COSTS.get(grade)
    if not cost:
        return {"success": False, "error": "max_grade"}

    # Check spirit stones
    if player.spirit_stones < cost["stones"]:
        return {"success": False, "error": "not_enough_stones"}

    # Check and consume ores
    for ore_id, qty_needed in cost["ores"]:
        player_ore = (await session.execute(
            select(PlayerOre).where(and_(
                PlayerOre.player_id == player.telegram_id,
                PlayerOre.ore_id == ore_id,
            ))
        )).scalar_one_or_none()
        if not player_ore or player_ore.quantity < qty_needed:
            return {"success": False, "error": "missing_materials"}

    # Consume all ores
    for ore_id, qty_needed in cost["ores"]:
        player_ore = (await session.execute(
            select(PlayerOre).where(and_(
                PlayerOre.player_id == player.telegram_id,
                PlayerOre.ore_id == ore_id,
            ))
        )).scalar_one_or_none()
        player_ore.quantity -= qty_needed
        if player_ore.quantity <= 0:
            await session.delete(player_ore)

    # Roll for success
    roll = random.random()
    if roll <= cost["success_rate"]:
        # SUCCESS — upgrade to next tier
        next_cauldron = (await session.execute(
            select(CauldronCatalog).where(CauldronCatalog.grade == grade + 1)
        )).scalar_one_or_none()
        if not next_cauldron:
            return {"success": False, "error": "no_next_tier"}

        player.spirit_stones -= cost["stones"]
        pc.cauldron_id = next_cauldron.id
        pc.durability = next_cauldron.max_durability
        return {
            "success": True,
            "new_cauldron": next_cauldron,
            "stones_spent": cost["stones"],
        }
    else:
        # FAILURE — lose materials + 50% stones + 20 durability
        stones_lost = cost["stones"] // 2
        player.spirit_stones -= stones_lost
        pc.durability = max(0, pc.durability - 20)
        return {
            "success": False,
            "error": "failed_roll",
            "stones_lost": stones_lost,
            "durability_lost": 20,
            "new_durability": pc.durability,
        }


async def repair_cauldron(session: AsyncSession, player: Player, pc: PlayerCauldron, cauldron: CauldronCatalog, amount: int = 10) -> dict:
    """Repair cauldron durability. amount = durability points to restore (multiples of 10)."""
    max_dur = cauldron.max_durability
    if pc.durability >= max_dur:
        return {"success": False, "error": "already_full"}

    # Cap the repair to not exceed max
    actual_repair = min(amount, max_dur - pc.durability)
    # Round up to nearest 10 for cost calculation
    cost_units = (actual_repair + 9) // 10
    cost = cost_units * REPAIR_COST_PER_10 * cauldron.grade

    if player.spirit_stones < cost:
        return {"success": False, "error": "not_enough_stones", "cost": cost}

    player.spirit_stones -= cost
    pc.durability += actual_repair
    return {
        "success": True,
        "repaired": actual_repair,
        "new_durability": pc.durability,
        "max_durability": max_dur,
        "cost": cost,
    }
