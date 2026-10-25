import random
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import (
    ArtifactCatalog, PlayerArtifact, PlayerOre, Player, OreCatalog,
    PlayerForgeSkill, ForgeRecipe, PlayerForgeMastery,
)
from config import ENCHANT_EFFECTS

FORGE_TIERS = {
    1: {"name": "Novice",     "name_pt": "Novato",       "name_es": "Novato",      "xp_req": 0,     "quality_bonus": 0,  "ore_discount": 0.00, "emoji": "🔰"},
    2: {"name": "Journeyman", "name_pt": "Oficial",      "name_es": "Oficial",     "xp_req": 300,   "quality_bonus": 5,  "ore_discount": 0.10, "emoji": "🔨"},
    3: {"name": "Expert",     "name_pt": "Especialista", "name_es": "Experto",     "xp_req": 1500,  "quality_bonus": 12, "ore_discount": 0.15, "emoji": "⚒️"},
    4: {"name": "Master",     "name_pt": "Mestre",       "name_es": "Maestro",     "xp_req": 6000,  "quality_bonus": 20, "ore_discount": 0.20, "emoji": "👑"},
    # Tier 5 reduzido de 25000→18000: com 10 forjas/dia (~25 XP médio) → ~72 dias = 2.4 meses ✅
    5: {"name": "Legendary",  "name_pt": "Lendário",     "name_es": "Legendario",  "xp_req": 18000, "quality_bonus": 30, "ore_discount": 0.30, "emoji": "🌟"},
}
MAX_FORGE_TIER = 5

FORGE_XP_REWARDS = {
    "success": 25,      # antes: 15
    "high_grade": 50,   # antes: 30  (grade >= 5 Spirit+)
    "spirit": 90,       # antes: 50  (spirit awakened)
    "failure": 5,
}


def get_forge_tier_name(tier: int, lang: str) -> str:
    info = FORGE_TIERS.get(tier, FORGE_TIERS[1])
    if lang == "pt":
        return info["name_pt"]
    if lang == "es":
        return info["name_es"]
    return info["name"]


async def get_blueprints(session: AsyncSession, player_realm: int):
    stmt = select(ArtifactCatalog).where(ArtifactCatalog.grade <= player_realm + 1)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_player_ores(session: AsyncSession, player_id: int):
    stmt = select(PlayerOre, OreCatalog).join(OreCatalog).where(PlayerOre.player_id == player_id)
    result = await session.execute(stmt)
    return result.all()


async def get_or_create_forge_skill(session: AsyncSession, player_id: int) -> PlayerForgeSkill:
    skill = (await session.execute(
        select(PlayerForgeSkill).where(PlayerForgeSkill.player_id == player_id)
    )).scalar_one_or_none()
    if not skill:
        skill = PlayerForgeSkill(player_id=player_id, tier=1, xp=0, total_forges=0)
        session.add(skill)
        await session.flush()
    return skill


def _check_forge_levelup(skill: PlayerForgeSkill) -> bool:
    """Returns True if the skill leveled up (mutates skill.tier in place)."""
    if skill.tier >= MAX_FORGE_TIER:
        return False
    next_tier_req = FORGE_TIERS[skill.tier + 1]["xp_req"]
    if skill.xp >= next_tier_req:
        skill.tier += 1
        return True
    return False


async def grant_forge_xp(session: AsyncSession, player_id: int, xp_amount: int) -> tuple[PlayerForgeSkill, bool]:
    """Grants XP to forge skill. Returns (skill, leveled_up)."""
    skill = await get_or_create_forge_skill(session, player_id)
    skill.xp += xp_amount
    skill.total_forges += 1
    leveled_up = _check_forge_levelup(skill)
    return skill, leveled_up


def calculate_forge_result(forge_tier: int, quality_bonus: int, ore_tier: int, sect_forge_lvl: int = 0) -> int:
    base = (forge_tier * 8 + quality_bonus) + (sect_forge_lvl * 5) + (ore_tier * 15)
    roll = random.randint(-10, 20)
    total = base + roll

    if total < 20: return 0  # Mortal
    if total < 40: return 1  # Yellow
    if total < 55: return 2  # Mystic
    if total < 70: return 3  # Earth
    if total < 85: return 4  # Heaven
    if total < 95: return 5  # Spirit
    if total < 105: return 6 # Divine
    return 7                 # Dao


def generate_spirit_name(lang: str = "pt") -> str:
    _spirit_data = {
        "pt": {
            "prefixes": ["Alma de ", "Espírito de ", "Essência de ", "Sombra de ", "Brilho de "],
            "suffixes": ["Dragão", "Fênix", "Tigre", "Lótus", "Vazio", "Trovão", "Luz"],
        },
        "en": {
            "prefixes": ["Soul of ", "Spirit of ", "Essence of ", "Shadow of ", "Glow of "],
            "suffixes": ["Dragon", "Phoenix", "Tiger", "Lotus", "Void", "Thunder", "Light"],
        },
        "es": {
            "prefixes": ["Alma de ", "Espíritu de ", "Esencia de ", "Sombra de ", "Brillo de "],
            "suffixes": ["Dragón", "Fénix", "Tigre", "Loto", "Vacío", "Trueno", "Luz"],
        },
    }
    data = _spirit_data.get(lang, _spirit_data["pt"])
    return random.choice(data["prefixes"]) + random.choice(data["suffixes"])


async def forge_artifact(session: AsyncSession, player: Player, blueprint_id: int, ore_id: int):
    from core.sect_engine import get_sect_bonuses

    # 1. Check blueprint
    stmt = select(ArtifactCatalog).where(ArtifactCatalog.id == blueprint_id)
    blueprint = (await session.execute(stmt)).scalar_one_or_none()
    if not blueprint:
        return None, "blueprint_not_found", None, False, 0

    # 2. Get forge skill + sect bonuses
    forge_skill = await get_or_create_forge_skill(session, player.telegram_id)
    forge_tier_data = FORGE_TIERS[forge_skill.tier]
    quality_bonus = forge_tier_data["quality_bonus"]
    ore_discount = forge_tier_data["ore_discount"]

    sect_bonuses = await get_sect_bonuses(session, player.telegram_id)
    sect_forge_lvl = sect_bonuses["forge_lvl"]
    sect_discount = sect_bonuses["forge_discount"]

    # 3. Check ore
    stmt = select(PlayerOre, OreCatalog).join(OreCatalog).where(
        PlayerOre.player_id == player.telegram_id,
        PlayerOre.ore_id == ore_id
    )
    res = (await session.execute(stmt)).first()

    # Ore cost: base 5, reduced by forge mastery (ore_discount stacks with sect discount)
    combined_discount = min(0.75, ore_discount + sect_discount)
    actual_cost = max(2, int(5 * (1.0 - combined_discount)))

    if not res or res.PlayerOre.quantity < actual_cost:
        return None, "not_enough_ores", None, False, 0

    player_ore, ore_catalog = res
    player_ore.quantity -= actual_cost

    # 4. Calculate grade
    grade_idx = calculate_forge_result(forge_skill.tier, quality_bonus, ore_catalog.tier, sect_forge_lvl)

    # 5. Create artifact
    new_art = PlayerArtifact(
        player_id=player.telegram_id,
        catalog_id=blueprint.id,
        grade=grade_idx,
        custom_stats=blueprint.base_stats.copy()
    )

    # Scale stats based on grade
    multiplier = 1.0 + (grade_idx * 0.5)
    for stat in new_art.custom_stats:
        new_art.custom_stats[stat] = int(new_art.custom_stats[stat] * multiplier)

    # 6. Spirit check (5% for Divine+)
    spirit_awakened = False
    if grade_idx >= 6 and random.random() < 0.05:
        new_art.has_spirit = True
        new_art.spirit_name = generate_spirit_name(lang=getattr(player, "language", "pt") or "pt")
        for stat in new_art.custom_stats:
            new_art.custom_stats[stat] = int(new_art.custom_stats[stat] * 1.2)
        spirit_awakened = True

    session.add(new_art)

    # 7. Grant forge XP
    if spirit_awakened:
        xp_gain = FORGE_XP_REWARDS["spirit"]
    elif grade_idx >= 5:
        xp_gain = FORGE_XP_REWARDS["high_grade"]
    else:
        xp_gain = FORGE_XP_REWARDS["success"]

    skill, leveled_up = await grant_forge_xp(session, player.telegram_id, xp_gain)

    return new_art, "success", skill, leveled_up, xp_gain


async def refine_artifact(session: AsyncSession, player_id: int, artifact_id: int):
    stmt = select(PlayerArtifact).where(PlayerArtifact.id == artifact_id, PlayerArtifact.player_id == player_id)
    target = (await session.execute(stmt)).scalar_one_or_none()
    if not target: return None, "artifact_not_found"
    if target.grade >= 7: return None, "max_grade"

    stmt = select(PlayerArtifact).where(
        PlayerArtifact.player_id == player_id,
        PlayerArtifact.catalog_id == target.catalog_id,
        PlayerArtifact.grade == target.grade,
        PlayerArtifact.id != artifact_id,
        PlayerArtifact.is_equipped == False
    ).limit(1)
    duplicate = (await session.execute(stmt)).scalar_one_or_none()
    if not duplicate: return None, "no_duplicate_found"

    # MV-7 — ⚒️ refino grátis do Ferreiro: UM roll por tentativa, ANTES do
    # charm (o proc do ofício nunca consome o Forge Protection Charm). Se
    # procar, a duplicata SOBREVIVE à tentativa — sucesso ou falha. Gated
    # (flag OFF → chance 0.0 → zero roll → byte-idêntico).
    prof_free = False
    try:
        from core.profession_engine import profissoes_on, roll_free_refine
        if profissoes_on():
            _pl = (await session.execute(
                select(Player).where(Player.telegram_id == player_id)
            )).scalar_one_or_none()
            if _pl is not None:
                prof_free = roll_free_refine(_pl)
    except Exception:
        prof_free = False

    if random.random() < 0.6:
        if not prof_free:
            await session.delete(duplicate)
        else:
            target._prof_free_refine = True  # transiente — só quando procou
        target.grade += 1
        stmt = select(ArtifactCatalog).where(ArtifactCatalog.id == target.catalog_id)
        blueprint = (await session.execute(stmt)).scalar_one()

        multiplier = 1.0 + (target.grade * 0.5)
        new_stats = blueprint.base_stats.copy()
        for stat in new_stats:
            new_stats[stat] = int(new_stats[stat] * multiplier)

        if target.has_spirit:
            for stat in new_stats:
                new_stats[stat] = int(new_stats[stat] * 1.2)

        target.custom_stats = new_stats
        return target, "refine_success"

    # MV-7 — falha com proc do ofício: a duplicata sobrevive SEM tocar o charm.
    if prof_free:
        return target, "refine_fail_prof"

    # ── Refinement failed: check for Forge Protection Charm buff ──
    from database.models import PlayerBuff
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    charm = (await session.execute(
        select(PlayerBuff).where(
            PlayerBuff.player_id == player_id,
            PlayerBuff.buff_type == "forge_protection",
            PlayerBuff.expires_at > now
        )
    )).scalar_one_or_none()

    if charm:
        # Charm protects: duplicate is NOT consumed, charm is used up
        await session.delete(charm)
        return target, "refine_fail_protected"

    # No protection — duplicate is lost
    await session.delete(duplicate)
    return target, "refine_fail"


async def enchant_artifact(session: AsyncSession, player_id: int, artifact_id: int, rune_type: str):
    stmt = select(PlayerArtifact).where(PlayerArtifact.id == artifact_id, PlayerArtifact.player_id == player_id)
    target = (await session.execute(stmt)).scalar_one_or_none()
    if not target: return None, "artifact_not_found"

    if rune_type not in ENCHANT_EFFECTS: return None, "invalid_rune"

    target.enchant_rune = rune_type
    return target, "enchant_success"


def get_artifact_total_stats(artifact: PlayerArtifact):
    stats = artifact.custom_stats.copy() if artifact.custom_stats else {}
    if artifact.enchant_rune:
        pass  # Rune applied in game_logic.py
    return stats


# ─── Craft-quality inference (TAPETE QoL §5 — [jogador] 25.05) ───────────────────
# Craft quality (success/perfect/divine ×1.0/×1.5/×2.0, spirit ×1.2 extra) is
# baked into custom_stats at forge time and NEVER persisted as a column;
# refine_artifact() overwrites custom_stats with base×(1.0+grade·0.5), erasing
# the quality multiplier. So quality can only be inferred post-hoc. The order
# below is the player's mental model ("Perfeito < Divino < Espírito").
# "refined" is OUTSIDE the order on purpose: refined rows lost their craft
# quality but represent real investment — every quality cut must treat them
# as above-the-cut (never dismantlable by a quality filter; review 2026-06-12).
ARTIFACT_QUALITY_ORDER = ["normal", "perfect", "divine", "spirit"]


def artifact_quality_rank(quality: str) -> int:
    """Rank for below_quality cuts. "refined"/unknown rank ABOVE every cut so
    a quality filter can never select them (only "Todas" reaches them)."""
    try:
        return ARTIFACT_QUALITY_ORDER.index(quality)
    except ValueError:
        return len(ARTIFACT_QUALITY_ORDER)


def infer_artifact_quality(
    custom_stats: dict | None,
    base_stats: dict | None,
    grade: int | None = None,
    catalog_grade: int | None = None,
    has_spirit: bool = False,
) -> str:
    """Best-effort craft-quality label for a PlayerArtifact.

    Returns one of ARTIFACT_QUALITY_ORDER or "refined" (grade above catalog —
    refine erased the craft multiplier; disclosed as its own chip and ranked
    above every quality cut). Caveats found in adversarial review 2026-06-12:
    gacha/fragment-shop grants write custom_stats = base×(1+grade·0.5) with
    grade == catalog_grade — for grade ≥ 3 that ratio (≥2.5) is impossible
    for any craft (max ×2.0 non-spirit), so ratios above 2.05 label "normal".
    G1 (×1.5) and G2 (×2.0) grade-scaled grants are mathematically
    indistinguishable from perfect/divine crafts AND carry identical stats,
    so the craft label stands there (conservative for the dismantle filter;
    economically equivalent for market disclosure).
    """
    if has_spirit:
        return "spirit"
    if not custom_stats or not base_stats:
        return "normal"
    if grade is not None and catalog_grade is not None and int(grade) > int(catalog_grade):
        # Refined: custom_stats = base×(1+grade·0.5) — craft quality is gone,
        # but the row is treasure (duplicates burned). Own label, never below
        # a quality cut.
        return "refined"
    # Use the largest base stat for precision (int() truncation at craft time
    # skews small stats: base 3 × 1.5 → 4 → ratio 1.33).
    ref_key = None
    ref_val = 0
    for k, v in base_stats.items():
        if isinstance(v, (int, float)) and v > ref_val:
            ref_key, ref_val = k, v
    if not ref_key or ref_val <= 0:
        return "normal"
    cur = custom_stats.get(ref_key)
    if not isinstance(cur, (int, float)) or cur <= 0:
        return "normal"
    ratio = cur / ref_val
    if ratio >= 2.05:
        # Impossible for a non-spirit craft → grade-scaled grant (gacha /
        # fragment shop / legacy ore-forge), not a divine roll.
        return "normal"
    if ratio >= 1.9:
        return "divine"
    if ratio >= 1.4:
        return "perfect"
    return "normal"


# ─── Forge Recipe System ─────────────────────────────────────────────

FORGE_RECIPE_TIER_INFO = {
    1: {"name": "Basic",        "name_pt": "Básico",      "name_es": "Básico",     "emoji": "🪨"},
    2: {"name": "Intermediate", "name_pt": "Intermédio",  "name_es": "Intermedio", "emoji": "⚡"},
    3: {"name": "Advanced",     "name_pt": "Avançado",    "name_es": "Avanzado",   "emoji": "🌟"},
    4: {"name": "Expert",       "name_pt": "Perito",      "name_es": "Perito",     "emoji": "💎"},
    5: {"name": "Legendary",    "name_pt": "Lendário",    "name_es": "Legendario", "emoji": "💜"},
    # F-11.5 — Celestial / G8 recipes. Without this entry the forge menu hid
    # the entire tier even when players had Legendary mastery and the recipes
    # were seeded in the DB.
    6: {"name": "Celestial",    "name_pt": "Celestial",   "name_es": "Celestial",  "emoji": "🌠"},
}


def get_recipe_tier_name(tier: int, lang: str) -> str:
    info = FORGE_RECIPE_TIER_INFO.get(tier, FORGE_RECIPE_TIER_INFO[1])
    if lang == "pt":
        return info["name_pt"]
    if lang == "es":
        return info["name_es"]
    return info["name"]


FORGE_MASTERY_LEVELS = {
    1: {"forges_req": 0,   "success_bonus": 0.0},
    2: {"forges_req": 10,  "success_bonus": 5.0},
    3: {"forges_req": 30,  "success_bonus": 12.0},
    4: {"forges_req": 75,  "success_bonus": 20.0},
    5: {"forges_req": 150, "success_bonus": 30.0},
}
MAX_FORGE_MASTERY = 5

FORGE_MASTERY_NAMES = {
    1: {"en": "Initiate",   "pt": "Iniciante",     "es": "Iniciado"},
    2: {"en": "Apprentice", "pt": "Aprendiz",      "es": "Aprendiz"},
    3: {"en": "Skilled",    "pt": "Habilidoso",    "es": "Habilidoso"},
    4: {"en": "Expert",     "pt": "Especialista",  "es": "Especialista"},
    5: {"en": "Master",     "pt": "Mestre",        "es": "Maestro"},
}

FORGE_RECIPE_XP = {
    "success": 15,
    "perfect": 40,
    "divine": 150,
    "failure": 3,
}

# H-7 (v13): cap forge XP earnable from each recipe tier — prevents grinding
# T1 recipes to push the smith to Legendary. Once player.xp >= cap[tier],
# crafting that tier yields zero XP (item is still produced).
FORGE_XP_CAP_PER_RECIPE_TIER = {
    1: 1500,   # T1 caps at start of Expert (was Journeyman→1500)
    2: 4000,
    3: 9000,
    4: 18000,
    5: 50000,
    6: 999999,  # Celestial uncapped
}


def get_forge_mastery_name(level: int, lang: str) -> str:
    names = FORGE_MASTERY_NAMES.get(level, FORGE_MASTERY_NAMES[1])
    return names.get(lang, names["en"])


# ─── Recipe queries ──────────────────────────────────────────────────

async def get_all_forge_recipes(session: AsyncSession) -> list[ForgeRecipe]:
    result = await session.execute(select(ForgeRecipe).order_by(ForgeRecipe.tier, ForgeRecipe.id))
    return list(result.scalars().all())


async def get_recipes_by_tier(session: AsyncSession, tier: int) -> list[ForgeRecipe]:
    result = await session.execute(
        select(ForgeRecipe).where(ForgeRecipe.tier == tier).order_by(ForgeRecipe.id)
    )
    return list(result.scalars().all())


async def get_recipe_by_id(session: AsyncSession, recipe_id: int) -> ForgeRecipe | None:
    return (await session.execute(
        select(ForgeRecipe).where(ForgeRecipe.id == recipe_id)
    )).scalar_one_or_none()


# ─── Recipe materials ────────────────────────────────────────────────

async def check_recipe_materials(session: AsyncSession, player_id: int, recipe: ForgeRecipe,
                                 discount: float = 0.0) -> dict:
    """Returns {ore_id: {ore, required, owned, has_enough}} for each material.

    MV-7: `discount` = fração do Ferreiro Espiritual (profession_engine.
    forge_ore_discount — gated, 0.0 com flag OFF → byte-idêntico). O required
    exibido AQUI é o mesmo que _consume_recipe_materials debita (lição MV-6:
    o número do confirm vem da mesma matemática que debita)."""
    from core.profession_engine import discounted_qty
    materials_status = {}
    for mat in recipe.materials:
        ore_id = mat["ore_id"]
        required = discounted_qty(mat["qty"], discount)

        row = (await session.execute(
            select(PlayerOre, OreCatalog).join(OreCatalog).where(
                PlayerOre.player_id == player_id,
                PlayerOre.ore_id == ore_id,
            )
        )).first()

        if row:
            owned = row.PlayerOre.quantity
            ore_cat = row.OreCatalog
        else:
            owned = 0
            ore_cat = (await session.execute(
                select(OreCatalog).where(OreCatalog.id == ore_id)
            )).scalar_one_or_none()

        materials_status[ore_id] = {
            "ore": ore_cat,
            "required": required,
            "owned": owned,
            "has_enough": owned >= required,
        }
    return materials_status


async def _consume_recipe_materials(session: AsyncSession, player_id: int, recipe: ForgeRecipe,
                                    partial: bool = False, discount: float = 0.0):
    """Consume materials. partial=True → 50% (rounded up) for failures.

    MV-7: o desconto do Ferreiro aplica ANTES do halving da falha — a falha
    de um Ferreiro nunca custa mais que 50% do custo JÁ descontado."""
    from core.profession_engine import discounted_qty
    for mat in recipe.materials:
        ore_id = mat["ore_id"]
        qty = discounted_qty(mat["qty"], discount)
        if partial:
            qty = (qty + 1) // 2

        p_ore = (await session.execute(
            select(PlayerOre).where(
                PlayerOre.player_id == player_id,
                PlayerOre.ore_id == ore_id,
            )
        )).scalar_one_or_none()
        if p_ore:
            p_ore.quantity = max(0, p_ore.quantity - qty)
            if p_ore.quantity <= 0:
                await session.delete(p_ore)


async def refund_recipe_materials(session: AsyncSession, player_id: int, catalog_id: int, ratio: float = 0.25) -> dict[int, int]:
    """U2 (v16.6): refund a fraction of an artifact's crafting materials on
    dismantle/recycle.

    Recycling used to return only spirit stones. Now it also returns `ratio`
    (default 25%, rounded up) of the ores in the artifact's forge recipe, looked
    up by catalog_id → ForgeRecipe.artifact_id. Artifacts with no recipe
    (drop/gacha-only) refund nothing — the source row can't tell a crafted item
    from a dropped one (no recipe_id column), so "no recipe ⇒ 0 materials" is the
    safe, WIPE-friendly behaviour. Returns {ore_id: qty_refunded}.
    """
    import math
    if not catalog_id:
        return {}
    recipe = (await session.execute(
        select(ForgeRecipe).where(ForgeRecipe.artifact_id == int(catalog_id))
    )).scalars().first()
    if not recipe or not recipe.materials:
        return {}
    refunded: dict[int, int] = {}
    for mat in recipe.materials:
        try:
            ore_id = int(mat["ore_id"])
            qty = int(mat.get("qty", 0))
        except (KeyError, TypeError, ValueError):
            continue
        give = max(0, math.ceil(qty * ratio))
        if give <= 0:
            continue
        p_ore = (await session.execute(
            select(PlayerOre).where(
                PlayerOre.player_id == player_id,
                PlayerOre.ore_id == ore_id,
            )
        )).scalar_one_or_none()
        if p_ore:
            p_ore.quantity = int(p_ore.quantity or 0) + give
        else:
            session.add(PlayerOre(player_id=player_id, ore_id=ore_id, quantity=give))
        refunded[ore_id] = refunded.get(ore_id, 0) + give
    return refunded


# ─── Recipe mastery ──────────────────────────────────────────────────

async def get_or_create_forge_mastery(session: AsyncSession, player_id: int, recipe_id: int) -> PlayerForgeMastery:
    mastery = (await session.execute(
        select(PlayerForgeMastery).where(and_(
            PlayerForgeMastery.player_id == player_id,
            PlayerForgeMastery.recipe_id == recipe_id,
        ))
    )).scalar_one_or_none()
    if not mastery:
        mastery = PlayerForgeMastery(player_id=player_id, recipe_id=recipe_id, mastery_level=1, forges_count=0)
        session.add(mastery)
        await session.flush()
    return mastery


async def increment_forge_mastery(session: AsyncSession, player_id: int, recipe_id: int) -> tuple[PlayerForgeMastery, bool]:
    """Increment forge count and check mastery level up. Returns (mastery, leveled_up)."""
    mastery = await get_or_create_forge_mastery(session, player_id, recipe_id)
    mastery.forges_count += 1
    leveled_up = False
    if mastery.mastery_level < MAX_FORGE_MASTERY:
        next_req = FORGE_MASTERY_LEVELS[mastery.mastery_level + 1]["forges_req"]
        if mastery.forges_count >= next_req:
            mastery.mastery_level += 1
            leveled_up = True
    return mastery, leveled_up


def get_forge_mastery_bonus(mastery_level: int) -> float:
    return FORGE_MASTERY_LEVELS.get(mastery_level, FORGE_MASTERY_LEVELS[1])["success_bonus"]


async def get_all_forge_masteries(session: AsyncSession, player_id: int) -> dict[int, PlayerForgeMastery]:
    rows = (await session.execute(
        select(PlayerForgeMastery).where(PlayerForgeMastery.player_id == player_id)
    )).scalars().all()
    return {m.recipe_id: m for m in rows}


def get_forge_mastery_next_info(mastery: PlayerForgeMastery) -> dict:
    if mastery.mastery_level >= MAX_FORGE_MASTERY:
        return {"at_max": True, "forges": mastery.forges_count}
    next_req = FORGE_MASTERY_LEVELS[mastery.mastery_level + 1]["forges_req"]
    return {
        "at_max": False,
        "forges": mastery.forges_count,
        "next_forges": next_req,
        "next_level": mastery.mastery_level + 1,
    }


# ─── Recipe success calculation ──────────────────────────────────────

def calculate_recipe_success_chance(
    base_rate: float,
    mastery_bonus: float = 0.0,
    soul_fire_tier: int = 0,
    forge_tier: int = 1,
) -> float:
    fire_bonus = soul_fire_tier * 3.0
    tier_bonus = (forge_tier - 1) * 2.0
    total = base_rate + mastery_bonus + fire_bonus + tier_bonus
    return max(5.0, min(98.0, total))


def roll_recipe_result(success_chance: float) -> str:
    """Returns 'divine', 'perfect', 'success', or 'failure'."""
    roll = random.uniform(0, 100)
    if roll <= 1.0:
        return "divine"
    if roll <= 6.0:
        return "perfect"
    if roll <= success_chance:
        return "success"
    return "failure"


# ─── Main recipe forge function ──────────────────────────────────────

async def forge_recipe_item(session: AsyncSession, player: Player, recipe_id: int) -> dict:
    """Recipe-based forging. Returns dict with full result info."""
    from core.alchemy_engine import get_or_create_soul_fire

    recipe = await get_recipe_by_id(session, recipe_id)
    if not recipe:
        return {"success": False, "error": "recipe_not_found"}

    if player.realm < recipe.required_realm:
        return {"success": False, "error": "realm_too_low"}

    forge_skill = await get_or_create_forge_skill(session, player.telegram_id)

    # Recipe tier must be <= forge tier + 1
    if recipe.tier > forge_skill.tier + 1:
        return {"success": False, "error": "forge_tier_too_low"}

    # MV-7 — desconto do Ferreiro Espiritual, computado UMA vez e usado no
    # gate, no débito da falha E no débito do sucesso (uma verdade; gated —
    # 0.0 com flag OFF → tudo byte-idêntico ao legado).
    try:
        from core.profession_engine import forge_ore_discount
        prof_discount = float(forge_ore_discount(player) or 0.0)
    except Exception:
        prof_discount = 0.0

    # Check materials
    materials = await check_recipe_materials(session, player.telegram_id, recipe,
                                             discount=prof_discount)
    if not all(m["has_enough"] for m in materials.values()):
        return {"success": False, "error": "not_enough_materials", "materials": materials}

    # Get mastery + soul fire
    mastery = await get_or_create_forge_mastery(session, player.telegram_id, recipe_id)
    mastery_bonus = get_forge_mastery_bonus(mastery.mastery_level)
    sf = await get_or_create_soul_fire(session, player.telegram_id, player.realm)

    success_chance = calculate_recipe_success_chance(
        recipe.base_success_rate, mastery_bonus, sf.fire_tier, forge_skill.tier
    )

    result = roll_recipe_result(success_chance)

    craft_data = {
        "result": result,
        "recipe": recipe,
        "success_chance": success_chance,
        "mastery_bonus": mastery_bonus,
        "soul_fire_tier": sf.fire_tier,
        "prof_discount": prof_discount,
    }

    # H-7: enforce XP cap per recipe tier — recipe craft yields 0 XP if cap reached.
    xp_cap = FORGE_XP_CAP_PER_RECIPE_TIER.get(recipe.tier, 0)
    xp_capped = forge_skill.xp >= xp_cap
    craft_data["xp_capped"] = xp_capped
    craft_data["xp_cap"] = xp_cap

    # ── Failure ──
    if result == "failure":
        # Check for Forge Protection Charm buff — saves materials on failure
        from database.models import PlayerBuff
        from datetime import datetime, timezone
        _now = datetime.now(timezone.utc)
        _charm = (await session.execute(
            select(PlayerBuff).where(
                PlayerBuff.player_id == player.telegram_id,
                PlayerBuff.buff_type == "forge_protection",
                PlayerBuff.expires_at > _now
            )
        )).scalar_one_or_none()

        charm_saved = False
        if _charm:
            await session.delete(_charm)
            charm_saved = True
            # Materials are NOT consumed when charm protects
        else:
            await _consume_recipe_materials(session, player.telegram_id, recipe, partial=True,
                                            discount=prof_discount)

        xp_gain = 0 if xp_capped else FORGE_RECIPE_XP["failure"]
        skill, leveled_up = await grant_forge_xp(session, player.telegram_id, xp_gain)
        mast, mast_up = await increment_forge_mastery(session, player.telegram_id, recipe_id)
        craft_data.update({
            "success": False,
            "charm_saved": charm_saved,
            "xp_gain": xp_gain,
            "skill": skill,
            "leveled_up": leveled_up,
            "mastery": mast,
            "mastery_leveled": mast_up,
        })
        return craft_data

    # ── Success / Perfect / Divine ──
    await _consume_recipe_materials(session, player.telegram_id, recipe, partial=False,
                                    discount=prof_discount)

    blueprint = (await session.execute(
        select(ArtifactCatalog).where(ArtifactCatalog.id == recipe.artifact_id)
    )).scalar_one()

    new_art = PlayerArtifact(
        player_id=player.telegram_id,
        catalog_id=blueprint.id,
        grade=blueprint.grade,
        custom_stats=blueprint.base_stats.copy() if blueprint.base_stats else {},
    )

    if result == "perfect":
        multiplier = 1.5
    elif result == "divine":
        multiplier = 2.0
    else:
        multiplier = 1.0

    for stat in new_art.custom_stats:
        new_art.custom_stats[stat] = int(new_art.custom_stats[stat] * multiplier)

    # Divine: 10% spirit chance
    spirit_awakened = False
    if result == "divine" and random.random() < 0.10:
        new_art.has_spirit = True
        new_art.spirit_name = generate_spirit_name(lang=getattr(player, "language", "pt") or "pt")
        for stat in new_art.custom_stats:
            new_art.custom_stats[stat] = int(new_art.custom_stats[stat] * 1.2)
        spirit_awakened = True

    session.add(new_art)

    xp_gain = 0 if xp_capped else FORGE_RECIPE_XP[result]
    skill, leveled_up = await grant_forge_xp(session, player.telegram_id, xp_gain)

    if result == "divine":
        skill.divine_forges = getattr(skill, "divine_forges", 0) + 1

    mast, mast_up = await increment_forge_mastery(session, player.telegram_id, recipe_id)

    craft_data.update({
        "success": True,
        "artifact": new_art,
        "blueprint": blueprint,
        "quality": result,
        "multiplier": multiplier,
        "spirit_awakened": spirit_awakened,
        "xp_gain": xp_gain,
        "skill": skill,
        "leveled_up": leveled_up,
        "mastery": mast,
        "mastery_leveled": mast_up,
    })
    return craft_data
