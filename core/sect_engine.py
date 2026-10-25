import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from database.models import Sect, SectMember, Player, SectBuildingLog, SectTerritory, SectWarLog, SectWarState, SectContributionLog
from config import TICK_INTERVAL_SECONDS, TERRITORY_DEFINITIONS

logger = logging.getLogger(__name__)


def get_training_bonus(level: int) -> float:
    """Training building CB multiplier. Caps at +100% (level 20)."""
    effective = min(level, 20)
    return 1.0 + (effective * 0.05)

def get_herb_garden_yield(level: int) -> int:
    return 10 * level

def get_forge_discount(level: int) -> float:
    return level * 0.03

def get_library_techniques(level: int) -> int:
    return level

def get_defense_bonus(level: int) -> float:
    return level * 0.05

def get_spirit_vein_bonus(level: int) -> float:
    return 1.0 + (level * 0.05)

# 幫 4.2 (2026-10-07) — as seis instalações da guilda, pela ordem da planta.
# A ÚNICA lista: a validação da melhoria (`api_sect_upgrade`), o payload da aba
# (`api_sect`) e o dono da planta (`core/guilda.py`) lêem esta.
BUILDINGS = ("training", "herb_garden", "forge", "library", "defense", "spirit_vein")


def building_effect_value(building_key: str, level: int) -> int:
    """O NÚMERO do efeito de uma instalação no nível ``level`` — o mesmo que
    ``format_building_effect`` escreve, saído dos MESMOS getters.

    幫 4.2 (2026-10-07): a conta antiga era ``int(x * 100)`` sobre um float, e o
    float de 0,15 é 0,1499… — o ecrã dizia "+14% CB" no Treino 3 (o motor aplica
    ×1,15) e "-32% cost" na Forja 11 (o motor aplica 0,33). Medido em 0..1000:
    6 níveis do Treino, 179 da Forja e 26 da Veia saíam um ponto abaixo. ``round``
    devolve o número que o motor de facto aplica. Chave desconhecida → 0.
    """
    lv = int(level or 0)
    if building_key == "training":
        return int(round((get_training_bonus(lv) - 1) * 100))
    if building_key == "herb_garden":
        return int(get_herb_garden_yield(lv))
    if building_key == "forge":
        return int(round(get_forge_discount(lv) * 100))
    if building_key == "library":
        return int(get_library_techniques(lv))
    if building_key == "defense":
        return int(round(get_defense_bonus(lv) * 100))
    if building_key == "spirit_vein":
        return int(round((get_spirit_vein_bonus(lv) - 1) * 100))
    return 0


def format_building_effect(building_key: str, level: int) -> str:
    """Server-resolved one-line effect string for a sect building at `level`.

    D ([jogador] 2026-06-16): single source of truth for the building effect shown
    in BOTH the chat (handlers/sect.py sect_buildings_menu) and the mini-app
    (webserver.api_sect → SectTab). The unit tokens stay literal so the two
    surfaces render byte-identical strings (parity). Unknown key → "".

    幫 4.2: o número sai de ``building_effect_value`` (o mesmo que a planta da
    onda mostra nas três línguas) — uma conta, duas formas de a escrever.
    """
    v = building_effect_value(building_key, level)
    if building_key == "training":
        return f"+{v}% CB"
    if building_key == "herb_garden":
        return f"{v} items"
    if building_key == "forge":
        return f"-{v}% cost"
    if building_key == "library":
        return f"{v} techs"
    if building_key == "defense":
        return f"-{v}% dmg"
    if building_key == "spirit_vein":
        return f"+{v}% stones"
    return ""

def calculate_upgrade_cost(current_level: int) -> int:
    return 1000 * (current_level + 1)**2


async def upgrade_building(session: Session, sect_id: str, building: str, player_id: int) -> dict:
    stmt = select(Sect).where(Sect.id == sect_id)
    sect = (await session.execute(stmt)).scalar_one_or_none()

    if not sect:
        return {"success": False, "error": "Sect not found"}

    current_level = getattr(sect, f"{building}_lvl", None)
    if current_level is None:
        return {"success": False, "error": "Invalid building"}

    cost = calculate_upgrade_cost(current_level)
    if sect.spirit_stones < cost:
        return {"success": False, "error": f"Insufficient stones (Need {cost})"}

    sect.spirit_stones -= cost
    setattr(sect, f"{building}_lvl", current_level + 1)

    log = SectBuildingLog(
        sect_id=sect.id,
        building=building,
        old_level=current_level,
        new_level=current_level + 1,
        upgraded_by=player_id,
        cost=cost
    )
    session.add(log)

    return {"success": True, "new_level": current_level + 1, "cost": cost}


async def ensure_territories_exist(session: Session):
    stmt = select(func.count(SectTerritory.id))
    count = (await session.execute(stmt)).scalar() or 0
    if count >= 3:
        return
    for defn in TERRITORY_DEFINITIONS:
        existing = (await session.execute(
            select(SectTerritory).where(SectTerritory.name == defn["name"])
        )).scalar_one_or_none()
        if not existing:
            session.add(SectTerritory(
                name=defn["name"],
                bonus_stones=defn["bonus_stones"],
                bonus_cb=defn["bonus_cb"],
            ))
    await session.flush()


async def is_war_active(session) -> bool:
    stmt = select(SectWarState).where(SectWarState.is_active == True)
    war = (await session.execute(stmt)).scalar_one_or_none()
    if not war:
        return False
    if war.started_at:
        elapsed = (datetime.now(timezone.utc) - war.started_at).total_seconds()
        if elapsed > 3600:
            return False
    return True


async def get_war_state(session) -> dict:
    stmt = select(SectWarState).where(SectWarState.is_active == True)
    war = (await session.execute(stmt)).scalar_one_or_none()
    if not war:
        return {"active": False, "participating_sects": [], "attacks": {}, "attacked_players": [], "sect_names": {}, "started_at": None}
    return {
        "active": war.is_active,
        "started_at": war.started_at,
        "participating_sects": war.participating_sects,
        "sect_names": war.sect_names,
        "attacks": war.attacks,
        "attacked_players": war.attacked_players,
    }


async def start_sect_war(session: Session) -> dict:
    await ensure_territories_exist(session)

    stmt_sects = (
        select(Sect)
        .where(Sect.member_count >= 1)
        .order_by(Sect.member_count.desc())
        .limit(10)
    )
    war_sects = (await session.execute(stmt_sects)).scalars().all()

    if len(war_sects) < 1:
        return {"started": False, "reason": "No sects available"}

    sect_ids = [str(s.id) for s in war_sects]
    sect_names = {str(s.id): s.name for s in war_sects}

    stmt_terr = select(SectTerritory)
    territories = (await session.execute(stmt_terr)).scalars().all()

    # JSONB requires string keys
    attacks = {str(terr.id): {} for terr in territories}

    # Deactivate any previous war record before creating a new one
    await session.execute(update(SectWarState).where(SectWarState.is_active == True).values(is_active=False))
    war_record = SectWarState(
        is_active=True,
        started_at=datetime.now(timezone.utc),
        participating_sects=sect_ids,
        sect_names=sect_names,
        attacks=attacks,
        attacked_players=[],
    )
    session.add(war_record)

    member_ids = []
    for sect in war_sects:
        stmt_members = select(SectMember.player_id).where(SectMember.sect_id == sect.id)
        ids = (await session.execute(stmt_members)).scalars().all()
        member_ids.extend(ids)

    return {
        "started": True,
        "sect_count": len(war_sects),
        "sect_names": sect_names,
        "territories": [{"id": t.id, "name": t.name} for t in territories],
        "member_ids": member_ids,
    }


async def register_war_attack(session: Session, player_id: int, territory_id: int) -> dict:
    stmt_war = select(SectWarState).where(SectWarState.is_active == True).with_for_update()
    war = (await session.execute(stmt_war)).scalar_one_or_none()
    if not war:
        return {"success": False, "error_key": "err_war_not_active"}

    if war.started_at:
        elapsed = (datetime.now(timezone.utc) - war.started_at).total_seconds()
        if elapsed > 3600:
            return {"success": False, "error_key": "err_war_ended"}

    if player_id in war.attacked_players:
        return {"success": False, "error_key": "err_war_already_attacked"}

    stmt = select(SectMember).where(SectMember.player_id == player_id)
    member = (await session.execute(stmt)).scalar_one_or_none()
    if not member:
        return {"success": False, "error_key": "err_not_in_sect"}

    sect_id_str = str(member.sect_id)
    if sect_id_str not in war.participating_sects:
        return {"success": False, "error_key": "err_sect_not_in_war"}

    territory_key = str(territory_id)
    if territory_key not in war.attacks:
        return {"success": False, "error_key": "err_territory_invalid"}

    stmt_p = select(Player).where(Player.telegram_id == player_id)
    player = (await session.execute(stmt_p)).scalar_one_or_none()
    if not player:
        return {"success": False, "error_key": "err_player_not_found"}

    # Hotfix "A Volta" 2026-07-07 (#12) — Selo de Supressão: a guerra lê BP
    # CRU, é o único ponto PvP onde nem um debuff morderia. Gate explícito.
    from core.combat_engine import is_pvp_sealed
    if await is_pvp_sealed(session, player_id):
        return {"success": False, "error_key": "err_war_pvp_sealed"}

    raw_bp = player.battle_power or 10

    # v16.1 — rival lineage multiplier. If the attacker's sect lineage
    # names the defending territory's current owner as its ancestral
    # rival, BP contributed × 1.5. The chat-side war UI displays the
    # rival hit via the achievement (`rival_sect_wars`) + contribution
    # note; analytics can split rival vs. neutral attacks later.
    rival_mult = 1.0
    rival_hit = False
    try:
        from core.sect_lineage_engine import compute_rival_bonus
        attacker_sect = (await session.execute(
            select(Sect.lineage_key).where(Sect.id == member.sect_id)
        )).first()
        attacker_lineage = attacker_sect[0] if attacker_sect else None

        # Defending owner = current territory.sect_id (post-resolution
        # holder). When attacking an uncontested territory there is no
        # rival to compute against.
        terr_row = (await session.execute(
            select(SectTerritory.sect_id).where(SectTerritory.id == territory_id)
        )).first()
        defender_sect_id = terr_row[0] if terr_row else None
        if defender_sect_id:
            defender_sect = (await session.execute(
                select(Sect.lineage_key).where(Sect.id == defender_sect_id)
            )).first()
            defender_lineage = defender_sect[0] if defender_sect else None
            rival_mult = compute_rival_bonus(attacker_lineage, defender_lineage)
            rival_hit = rival_mult > 1.0
    except Exception:
        logger.debug("rival lineage multiplier lookup failed; defaulting to 1.0",
                     exc_info=True)
        rival_mult = 1.0
        rival_hit = False

    bp = int(raw_bp * rival_mult)

    # Mutate JSONB fields and flag them as modified
    new_attacks = {k: dict(v) for k, v in war.attacks.items()}
    new_attacks[territory_key][sect_id_str] = new_attacks[territory_key].get(sect_id_str, 0) + bp
    war.attacks = new_attacks
    war.attacked_players = list(war.attacked_players) + [player_id]
    flag_modified(war, "attacks")
    flag_modified(war, "attacked_players")

    sect_name = war.sect_names.get(sect_id_str, "???")

    return {
        "success": True,
        "bp_contributed": bp,
        "bp_raw": int(raw_bp),
        "rival_hit": rival_hit,
        "rival_multiplier": float(rival_mult),
        "sect_name": sect_name,
        "territory_id": territory_id,
    }


async def resolve_sect_war(session: Session) -> dict:
    import uuid as _uuid

    # Row-lock the active war (2026-06-13): the recovery sweep and the +1h
    # date job can race on the same war — under READ COMMITTED the WHERE is
    # re-evaluated after the lock wait, so the loser sees is_active=False and
    # returns "No war active" instead of double-resolving/double-notifying.
    stmt_war = select(SectWarState).where(SectWarState.is_active == True).with_for_update()
    war = (await session.execute(stmt_war)).scalar_one_or_none()
    if not war:
        return {"resolved": False, "reason": "No war active"}

    await ensure_territories_exist(session)

    stmt_terr = select(SectTerritory)
    territories = (await session.execute(stmt_terr)).scalars().all()

    results = []
    now = datetime.now(timezone.utc)
    notified_members = set()

    for terr in territories:
        # JSONB keys are strings
        territory_attacks = war.attacks.get(str(terr.id), {})

        adjusted_scores = {}
        for sid, total_bp in territory_attacks.items():
            defense_bonus_mult = 1.0
            if terr.sect_id and str(terr.sect_id) == sid:
                stmt_sect = select(Sect).where(Sect.id == terr.sect_id)
                defending_sect = (await session.execute(stmt_sect)).scalar_one_or_none()
                if defending_sect:
                    defense_bonus_mult = 1.0 + get_defense_bonus(defending_sect.defense_lvl)
            adjusted_scores[sid] = int(total_bp * defense_bonus_mult)

        if not adjusted_scores:
            results.append({
                "territory_name": terr.name,
                "winner": None,
                "no_contestants": True,
            })
            continue

        ranked = sorted(adjusted_scores.items(), key=lambda x: x[1], reverse=True)
        winner_sid, winner_bp = ranked[0]

        old_owner_id = terr.sect_id
        terr.sect_id = _uuid.UUID(winner_sid)
        terr.captured_at = now
        terr.expires_at = now + timedelta(days=7)

        winner_name = war.sect_names.get(winner_sid, "???")

        if old_owner_id and str(old_owner_id) != winner_sid:
            war_log = SectWarLog(
                attacker_sect=_uuid.UUID(winner_sid),
                defender_sect=old_owner_id,
                winner_sect=_uuid.UUID(winner_sid),
                territory_id=terr.id,
            )
            session.add(war_log)

        stmt_members = select(SectMember.player_id).where(
            SectMember.sect_id == _uuid.UUID(winner_sid)
        )
        winner_member_ids = (await session.execute(stmt_members)).scalars().all()
        notified_members.update(winner_member_ids)

        results.append({
            "territory_name": terr.name,
            "winner": winner_name,
            "winner_bp": winner_bp,
            "participants": len(adjusted_scores),
            "winner_member_ids": winner_member_ids,
        })

    all_participant_ids = set()
    for sid in war.participating_sects:
        stmt_m = select(SectMember.player_id).where(SectMember.sect_id == _uuid.UUID(sid))
        ids = (await session.execute(stmt_m)).scalars().all()
        all_participant_ids.update(ids)

    # Mark war as finished in DB
    war.is_active = False

    return {
        "resolved": True,
        "results": results,
        "all_participant_ids": list(all_participant_ids),
    }


async def distribute_territory_bonus(session: Session) -> list:
    now = datetime.now(timezone.utc)
    stmt = select(SectTerritory).where(
        SectTerritory.sect_id.isnot(None),
        SectTerritory.expires_at > now,
    )
    territories = (await session.execute(stmt)).scalars().all()

    notifications = []
    for terr in territories:
        stmt_members = (
            select(SectMember.player_id)
            .where(SectMember.sect_id == terr.sect_id)
        )
        member_ids = (await session.execute(stmt_members)).scalars().all()

        if not member_ids:
            continue

        stones_per_member = max(1, terr.bonus_stones // len(member_ids))
        
        stmt_update = (
            update(Player)
            .where(Player.telegram_id.in_(member_ids))
            .values(spirit_stones=Player.spirit_stones + stones_per_member)
        )
        await session.execute(stmt_update)

        for mid in member_ids:
            notifications.append({
                "player_id": mid,
                "stones": stones_per_member,
                "territory_name": terr.name,
            })

    return notifications


async def calculate_territory_bonus(session: Session, player_id: int) -> dict:
    info = await get_player_sect_info(session, player_id)
    if not info:
        return {"bonus_stones": 0, "bonus_cb": 0.0}

    now = datetime.now(timezone.utc)
    stmt = select(SectTerritory).where(
        SectTerritory.sect_id == info["sect"].id,
        SectTerritory.expires_at > now,
    )
    territories = (await session.execute(stmt)).scalars().all()

    total_stones = sum(t.bonus_stones for t in territories)
    total_cb = sum(t.bonus_cb for t in territories)

    return {"bonus_stones": total_stones, "bonus_cb": total_cb, "count": len(territories)}


async def distribute_herb_garden_rewards(session: Session):
    stmt = select(Sect).where(Sect.herb_garden_lvl > 0)
    sects = (await session.execute(stmt)).scalars().all()

    for sect in sects:
        amount = get_herb_garden_yield(sect.herb_garden_lvl)
        if amount <= 0:
            continue

        from core.utils import add_item_to_inventory
        import random
        # Distribute mixed T1/T2 herbs — crafting herbs weighted higher
        # 45% Qi Root (1), 25% Spirit Grass (2), 20% Spirit Vine (12), 10% Moonlight Moss (9)
        garden_herb_pool = [(1, 45), (2, 25), (12, 20), (9, 10)]
        herb_ids = [h[0] for h in garden_herb_pool]
        herb_weights = [h[1] for h in garden_herb_pool]
        for _ in range(amount):
            herb_id = random.choices(herb_ids, weights=herb_weights, k=1)[0]
            await add_item_to_inventory(session, sect.master_id, "herb", herb_id, 1)


async def get_player_sect_info(session: Session, player_id: int):
    stmt = select(SectMember, Sect).join(Sect, SectMember.sect_id == Sect.id).where(SectMember.player_id == player_id)
    result = (await session.execute(stmt)).first()
    if result:
        return {"member": result[0], "sect": result[1]}
    return None


async def get_sect_bonuses(session: Session, player_id: int) -> dict:
    info = await get_player_sect_info(session, player_id)
    if not info:
        return {
            "training_mult": 1.0,
            "spirit_vein_mult": 1.0,
            "forge_discount": 0.0,
            "forge_lvl": 0,
            "defense_mult": 0.0,
            "herb_yield": 0,
            "territory_cb": 0.0,
            "master_cb_mult": 1.0,
        }

    sect = info["sect"]
    member = info["member"]
    terr_bonus = await calculate_territory_bonus(session, player_id)

    # v14.2 D-3a — Sect Leader bonus passivo. Authentic Wuxia: leadership tempers
    # the cultivator. Only the Master receives both bonuses.
    #   • +10% sect production: applied to training_mult (compounds CB gain).
    #   • +5% personal CB: separate multiplier — the burden of leadership.
    is_master = member.rank == "master"
    training_mult = get_training_bonus(sect.training_lvl)
    if is_master:
        training_mult *= 1.10
    master_cb_mult = 1.05 if is_master else 1.0

    return {
        "training_mult": training_mult,
        "spirit_vein_mult": get_spirit_vein_bonus(sect.spirit_vein_lvl),
        "forge_discount": get_forge_discount(sect.forge_lvl),
        "forge_lvl": sect.forge_lvl,
        "defense_mult": get_defense_bonus(sect.defense_lvl),
        "herb_yield": get_herb_garden_yield(sect.herb_garden_lvl),
        "territory_cb": terr_bonus["bonus_cb"],
        "master_cb_mult": master_cb_mult,
    }


async def log_sect_contribution(session: Session, player_id: int, sect_id, contrib_type: str, amount: int):
    """Log a sect contribution (donation, quest, war) for visibility tracking."""
    entry = SectContributionLog(
        player_id=player_id,
        sect_id=sect_id,
        type=contrib_type,
        amount=amount,
    )
    session.add(entry)
    logger.info("SectContribution: player=%s sect=%s type=%s amount=%d", player_id, sect_id, contrib_type, amount)


# ─────────────────────────────────────────────────────────────────────────────
# MA-33 (2026-05-07) — engine functions for sect actions exposed via mini-app.
# These are the source of truth used by the mini-app endpoints. The chat
# handlers in handlers/sect.py predate this and inline the same logic; they
# are intentionally NOT refactored to avoid regression on a live bot. New
# call-sites should call these engine functions instead of duplicating.
#
# Convention: every action returns {"ok": bool, ...}. On failure also returns
# `reason` (machine code, i18n key on the client) and optionally helper data.
# Caller commits the session.
# ─────────────────────────────────────────────────────────────────────────────

# Catalog of buyable shop items. Mirrors the inline `items_db` and
# `SCROLL_SHOP_ITEMS` from handlers/sect.py:945-980 + 1052-1056. Single
# source of truth so endpoint and chat eventually converge.
SECT_SHOP_BASIC_ITEMS = [
    {"id": "qi_pill",    "cost": 50,   "req_lvl": 1,  "type": "pill",        "item_id": 1, "emoji": "💧"},
    {"id": "cb_pill",    "cost": 200,  "req_lvl": 5,  "type": "pill",        "item_id": 2, "emoji": "☯️"},
    {"id": "beast_trap", "cost": 100,  "req_lvl": 1,  "type": "beast_trap",  "item_id": 0, "emoji": "🪤"},
    {"id": "blueprint",  "cost": 1000, "req_lvl": 10, "type": "blueprint",   "item_id": 1, "emoji": "📜"},
]

SECT_SHOP_SCROLLS = {
    1: {"name_emoji": "⚡", "tech_key": "tech_thunder_step", "cost": 500,  "req_library": 1},
    4: {"name_emoji": "🌑", "tech_key": "tech_shadow_step",  "cost": 500,  "req_library": 1},
    3: {"name_emoji": "🌍", "tech_key": "tech_iron_body",    "cost": 800,  "req_library": 2},
    2: {"name_emoji": "🔥", "tech_key": "tech_dragon_fist",  "cost": 2000, "req_library": 3},
    5: {"name_emoji": "☯️", "tech_key": "tech_void_slash",   "cost": 5000, "req_library": 5},
}

NAME_MIN_LEN = 3
NAME_MAX_LEN = 32


async def donate_to_sect(session: Session, player_id: int, amount: int) -> dict:
    """Mirror of handlers.sect.process_sect_donation_input (line 273-309).
    Reuses log_sect_contribution + grants 1 CP per 100 stones."""
    from core.quest_engine import track_quest

    if amount <= 0:
        return {"ok": False, "reason": "bad_amount"}
    # Lock player row to prevent double-spend race condition (mirrors chat).
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id).with_for_update()
    )).scalar_one_or_none()
    if not player:
        return {"ok": False, "reason": "player_not_found"}
    if player.spirit_stones < amount:
        return {"ok": False, "reason": "insufficient_stones",
                "have": int(player.spirit_stones), "need": amount}
    info = await get_player_sect_info(session, player_id)
    if not info:
        return {"ok": False, "reason": "not_in_sect"}
    sect = info["sect"]
    member = info["member"]

    player.spirit_stones -= amount
    sect.spirit_stones += amount
    cp_gained = amount // 100
    member.contribution_points += cp_gained

    await log_sect_contribution(session, player_id, sect.id, "donation", amount)
    await track_quest(session, player_id, "sect_contribution", amount)

    # v16.3 — Karma wire. Material support of one's sect is a small
    # virtuous act; +5 karma per donation event (cap-naturally by stones
    # limit). Defensive try/except so karma failures NEVER crash a
    # donation — Lei §1 — money in, action committed regardless.
    try:
        from core.karma_engine import apply_karma
        await apply_karma(
            session, player_id, "sect_donate_contribution",
            metadata={"sect_id": str(sect.id), "amount": int(amount)},
        )
    except Exception:
        logger.warning("karma wire on sect donate failed", exc_info=True)

    return {
        "ok": True,
        "donated": amount,
        "cp_gained": cp_gained,
        "your_contribution": int(member.contribution_points),
        "sect_treasury": int(sect.spirit_stones),
        "stones_remaining": int(player.spirit_stones),
    }


async def create_sect_for_player(session: Session, player_id: int, name: str,
                                  description: str | None = None,
                                  lineage_key: str | None = None) -> dict:
    """Mirror of handlers.sect.process_sect_name_input (line 185-228).

    v16.1 — accepts an optional ``lineage_key``. When provided, validated
    via ``sect_lineage_engine.is_valid_lineage`` and persisted on the
    new sect. When omitted, the sect is created with ``lineage_key=NULL``
    and the master has ~30 days to pick one via the LineageChooserModal
    in the mini-app (Lei §1 — chooser surfaces a pulsing golden button).

    Demonic lineages (Abyssal Depths) only validate when the caller is
    on the Demonic Path — same gate ``set_sect_lineage`` applies later.
    """
    from config import SECT_CREATION_COST
    from datetime import datetime, timezone

    if not name or not isinstance(name, str):
        return {"ok": False, "reason": "bad_name"}
    name = name.strip()
    if len(name) < NAME_MIN_LEN or len(name) > NAME_MAX_LEN:
        return {"ok": False, "reason": "name_length",
                "min": NAME_MIN_LEN, "max": NAME_MAX_LEN}

    # v16.1 — validate lineage upfront so we can reject before charging the
    # 50K creation cost. NULL → defer to chooser; invalid string → reject.
    # v16.2 — additionally gate by path: Rogue cultivators are solitary by
    # canon (cannot host a lineaged sect; they can still create a sect with
    # lineage=NULL and operate it as a guild-style player group).
    validated_lineage: str | None = None
    if lineage_key is not None:
        from core.sect_lineage_engine import (
            _player_is_demonic, is_demonic_lineage, is_valid_lineage,
        )
        if not is_valid_lineage(lineage_key):
            return {"ok": False, "reason": "invalid_lineage"}
        # v16.2 — Rogue path cannot host any lineage.
        try:
            from core.path_engine import (
                can_path_join_lineage_tier, get_player_path_raw, is_rogue_path,
            )
            from core.sect_lineage_engine import get_lineage_meta as _get_ln_meta
            raw_path = await get_player_path_raw(session, player_id)
            if is_rogue_path(raw_path):
                return {"ok": False, "reason": "rogue_no_lineage"}
            # Stricter cross-tier check: even if path is set but the lineage
            # tier mismatches (e.g. righteous path picking demonic lineage),
            # reject before the demonic-only check. This keeps the error
            # surface localized per path tier.
            tier = _get_ln_meta(lineage_key).get("tier")
            if raw_path is not None and not can_path_join_lineage_tier(raw_path, tier):
                return {"ok": False, "reason": "path_lineage_mismatch"}
        except Exception:
            # Defensive: path engine failures fall back to the legacy
            # demonic check below (don't block sect creation on engine
            # plumbing issues).
            pass
        if is_demonic_lineage(lineage_key):
            if not await _player_is_demonic(session, player_id):
                return {"ok": False, "reason": "demonic_locked"}
        validated_lineage = lineage_key

    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id).with_for_update()
    )).scalar_one_or_none()
    if not player:
        return {"ok": False, "reason": "player_not_found"}
    if player.spirit_stones < SECT_CREATION_COST:
        return {"ok": False, "reason": "insufficient_stones",
                "have": int(player.spirit_stones), "need": SECT_CREATION_COST}

    # Already in sect?
    existing = (await session.execute(
        select(SectMember).where(SectMember.player_id == player_id)
    )).scalar_one_or_none()
    if existing:
        return {"ok": False, "reason": "already_in_sect"}

    # Name uniqueness — DB enforces it (`unique=True`) but check now for clean error.
    name_taken = (await session.execute(
        select(Sect).where(Sect.name == name)
    )).scalar_one_or_none()
    if name_taken:
        return {"ok": False, "reason": "name_taken"}

    player.spirit_stones -= SECT_CREATION_COST
    new_sect = Sect(name=name, master_id=player_id)
    if description:
        new_sect.description = description.strip()[:200]
    if validated_lineage is not None:
        new_sect.lineage_key = validated_lineage
        new_sect.lineage_chosen_at = datetime.now(timezone.utc)
    session.add(new_sect)
    await session.flush()  # populate sect.id before SectMember references it

    member = SectMember(sect_id=new_sect.id, player_id=player_id, rank="master")
    session.add(member)

    return {
        "ok": True,
        "sect_id": str(new_sect.id),
        "name": new_sect.name,
        "lineage_key": validated_lineage,
        "stones_remaining": int(player.spirit_stones),
    }


async def join_sect_for_player(session: Session, player_id: int, sect_id: str) -> dict:
    """Mirror of handlers.sect.sect_join_callback (line 409-439)."""
    import uuid as _uuid

    try:
        sect_uuid = _uuid.UUID(str(sect_id))
    except (ValueError, AttributeError):
        return {"ok": False, "reason": "bad_sect_id"}

    existing = (await session.execute(
        select(SectMember).where(SectMember.player_id == player_id)
    )).scalar_one_or_none()
    if existing:
        return {"ok": False, "reason": "already_in_sect"}

    sect = (await session.execute(
        select(Sect).where(Sect.id == sect_uuid).with_for_update()
    )).scalar_one_or_none()
    if not sect:
        return {"ok": False, "reason": "sect_not_found"}
    if sect.member_count >= sect.max_members:
        return {"ok": False, "reason": "sect_full",
                "current": int(sect.member_count), "max": int(sect.max_members)}

    member = SectMember(sect_id=sect.id, player_id=player_id, rank="disciple")
    sect.member_count += 1
    session.add(member)

    return {
        "ok": True,
        "sect_id": str(sect.id),
        "name": sect.name,
    }


async def leave_sect_for_player(session: Session, player_id: int) -> dict:
    """Mirror of handlers.sect.sect_leave_execute_callback (line 884-905)."""
    info = await get_player_sect_info(session, player_id)
    if not info:
        return {"ok": False, "reason": "not_in_sect"}
    sect = info["sect"]
    member = info["member"]
    if member.rank == "master" and sect.member_count > 1:
        return {"ok": False, "reason": "master_must_promote_first"}

    sect.member_count -= 1
    await session.delete(member)
    deleted_sect = False
    if sect.member_count <= 0:
        await session.delete(sect)
        deleted_sect = True

    return {"ok": True, "deleted_sect": deleted_sect}


async def _resolve_target_in_sect(session: Session, sect_id, target_dao_name: str):
    """Find a (SectMember, Player) pair by dao_name within the same sect.
    Returns (member, player) or (None, None). Lookup-by-dao_name is the privacy-
    safe pattern (telegram_id never crosses the API)."""
    if not target_dao_name or not isinstance(target_dao_name, str):
        return None, None
    target_dao_name = target_dao_name.strip()
    if not target_dao_name:
        return None, None

    row = (await session.execute(
        select(SectMember, Player)
        .join(Player, Player.telegram_id == SectMember.player_id)
        .where(SectMember.sect_id == sect_id, Player.dao_name == target_dao_name)
    )).first()
    if not row:
        return None, None
    return row[0], row[1]


async def promote_member(session: Session, caller_id: int, target_dao_name: str) -> dict:
    """Promote disciple→elder. Master only. Lookup target by dao_name (privacy)."""
    info = await get_player_sect_info(session, caller_id)
    if not info:
        return {"ok": False, "reason": "not_in_sect"}
    if info["member"].rank != "master":
        return {"ok": False, "reason": "master_only"}

    target_member, target_player = await _resolve_target_in_sect(
        session, info["sect"].id, target_dao_name
    )
    if not target_member or not target_player:
        return {"ok": False, "reason": "target_not_in_sect"}
    if target_member.player_id == caller_id:
        return {"ok": False, "reason": "cannot_target_self"}
    if target_member.rank == "master":
        return {"ok": False, "reason": "cannot_promote_master"}
    if target_member.rank == "elder":
        return {"ok": False, "reason": "already_elder"}

    target_member.rank = "elder"
    return {"ok": True, "target_name": target_player.dao_name, "new_rank": "elder"}


async def kick_member(session: Session, caller_id: int, target_dao_name: str) -> dict:
    """Kick member. Master kicks anyone (except themselves and other masters);
    Elder kicks disciples only."""
    info = await get_player_sect_info(session, caller_id)
    if not info:
        return {"ok": False, "reason": "not_in_sect"}
    caller_rank = info["member"].rank
    if caller_rank not in ("master", "elder"):
        return {"ok": False, "reason": "rank_too_low"}

    target_member, target_player = await _resolve_target_in_sect(
        session, info["sect"].id, target_dao_name
    )
    if not target_member or not target_player:
        return {"ok": False, "reason": "target_not_in_sect"}
    if target_member.player_id == caller_id:
        return {"ok": False, "reason": "cannot_target_self"}
    if target_member.rank == "master":
        return {"ok": False, "reason": "cannot_kick_master"}
    if caller_rank == "elder" and target_member.rank != "disciple":
        return {"ok": False, "reason": "elder_can_only_kick_disciple"}

    info["sect"].member_count -= 1
    await session.delete(target_member)
    return {"ok": True, "target_name": target_player.dao_name}


async def get_shop_catalog(session: Session, player_id: int) -> dict:
    """Read-only catalog of the sect shop for a given player. Combines the
    inline `items_db` + `SCROLL_SHOP_ITEMS` from handlers/sect.py."""
    from database.models import PlayerInventory, PlayerTechnique

    info = await get_player_sect_info(session, player_id)
    if not info:
        return {"in_sect": False}
    sect = info["sect"]
    member = info["member"]

    learned_ids = set((await session.execute(
        select(PlayerTechnique.technique_id).where(PlayerTechnique.player_id == player_id)
    )).scalars().all())
    owned_scroll_ids = set((await session.execute(
        select(PlayerInventory.item_id).where(
            PlayerInventory.player_id == player_id,
            PlayerInventory.item_type == "technique_scroll",
            PlayerInventory.quantity > 0,
        )
    )).scalars().all())

    basic = []
    for it in SECT_SHOP_BASIC_ITEMS:
        basic.append({
            "id": it["id"],
            "name_key": f"sect_shop_item_{it['id']}",  # i18n on the client
            "emoji": it["emoji"],
            "cost": it["cost"],
            "req_lvl": it["req_lvl"],
            "locked": sect.training_lvl < it["req_lvl"],
            "kind": "basic",
        })

    scrolls = []
    for tech_id, info_s in SECT_SHOP_SCROLLS.items():
        scrolls.append({
            "id": f"scroll_{tech_id}",
            "tech_id": tech_id,
            "name_key": info_s["tech_key"],
            "emoji": info_s["name_emoji"],
            "cost": info_s["cost"],
            "req_library": info_s["req_library"],
            "locked": sect.library_lvl < info_s["req_library"],
            "already_learned": tech_id in learned_ids,
            "already_owned": tech_id in owned_scroll_ids,
            "kind": "scroll",
        })

    return {
        "in_sect": True,
        "your_cp": int(member.contribution_points),
        "training_lvl": int(sect.training_lvl),
        "library_lvl": int(sect.library_lvl),
        "items": basic,
        "scrolls": scrolls,
    }


async def buy_shop_item(session: Session, player_id: int, item_id: str) -> dict:
    """Mirror of handlers.sect.sect_buy_item_callback (line 990-1086) without
    the chat-side rollback dance (the engine returns a clean failure dict so
    the caller decides what to display)."""
    from core.utils import (
        add_item_to_inventory, _get_or_create_ring, _count_used_slots,
    )

    info = await get_player_sect_info(session, player_id)
    if not info:
        return {"ok": False, "reason": "not_in_sect"}
    sect = info["sect"]
    member = info["member"]

    if not item_id or not isinstance(item_id, str):
        return {"ok": False, "reason": "bad_item_id"}

    # Scroll path
    if item_id.startswith("scroll_"):
        try:
            tech_id = int(item_id.replace("scroll_", ""))
        except ValueError:
            return {"ok": False, "reason": "bad_item_id"}
        info_s = SECT_SHOP_SCROLLS.get(tech_id)
        if not info_s:
            return {"ok": False, "reason": "item_not_found"}
        if sect.library_lvl < info_s["req_library"]:
            return {"ok": False, "reason": "library_locked",
                    "req_library": info_s["req_library"], "current": sect.library_lvl}
        if member.contribution_points < info_s["cost"]:
            return {"ok": False, "reason": "insufficient_cp",
                    "have": int(member.contribution_points), "need": info_s["cost"]}

        from database.models import PlayerTechnique
        already = (await session.execute(
            select(PlayerTechnique).where(
                PlayerTechnique.player_id == player_id,
                PlayerTechnique.technique_id == tech_id,
            )
        )).scalar_one_or_none()
        if already:
            return {"ok": False, "reason": "already_learned"}

        member.contribution_points -= info_s["cost"]
        added = await add_item_to_inventory(session, player_id, "technique_scroll", tech_id)
        if not added:
            ring = await _get_or_create_ring(session, player_id)
            used = await _count_used_slots(session, player_id)
            return {"ok": False, "reason": "inventory_full",
                    "used": used, "max": ring.max_slots}
        return {
            "ok": True, "kind": "scroll", "tech_id": tech_id,
            "remaining_cp": int(member.contribution_points),
        }

    # Basic item path
    item = next((it for it in SECT_SHOP_BASIC_ITEMS if it["id"] == item_id), None)
    if not item:
        return {"ok": False, "reason": "item_not_found"}
    if sect.training_lvl < item["req_lvl"]:
        return {"ok": False, "reason": "training_locked",
                "req_lvl": item["req_lvl"], "current": sect.training_lvl}
    if member.contribution_points < item["cost"]:
        return {"ok": False, "reason": "insufficient_cp",
                "have": int(member.contribution_points), "need": item["cost"]}

    member.contribution_points -= item["cost"]
    added = await add_item_to_inventory(session, player_id, item["type"], item["item_id"])
    if not added:
        ring = await _get_or_create_ring(session, player_id)
        used = await _count_used_slots(session, player_id)
        return {"ok": False, "reason": "inventory_full",
                "used": used, "max": ring.max_slots}
    return {
        "ok": True, "kind": "basic", "item_id": item["id"],
        "remaining_cp": int(member.contribution_points),
    }


# ─────────────────────────────────────────────────────────────────────────────
# v14.2 D-3a — /decreto_supremo (Sect Edict, master only, 24h sect-wide).
# ─────────────────────────────────────────────────────────────────────────────

DECREE_DURATION_HOURS = 24
DECREE_MAX_LEN = 280  # tweet-length: forces edicts to be punchy.


async def set_sect_decree(session: Session, master_id: int, text: str) -> dict:
    """Master sets a 24h sect-wide edict. Overwrites any active decree."""
    info = await get_player_sect_info(session, master_id)
    if not info:
        return {"ok": False, "reason": "not_in_sect"}
    if info["member"].rank != "master":
        return {"ok": False, "reason": "master_only"}

    text = (text or "").strip()
    if not text:
        return {"ok": False, "reason": "empty_text"}
    if len(text) > DECREE_MAX_LEN:
        return {"ok": False, "reason": "text_too_long", "max": DECREE_MAX_LEN}

    sect = info["sect"]
    sect.decree_text = text
    sect.decree_expires_at = datetime.now(timezone.utc) + timedelta(hours=DECREE_DURATION_HOURS)
    sect.decree_author_id = master_id

    return {
        "ok": True,
        "sect_id": str(sect.id),
        "expires_at": sect.decree_expires_at,
        "text": text,
    }


def get_active_decree(sect) -> dict | None:
    """Returns the decree dict if still active, else None. Safe with stale session
    objects (the only attribute touched is the column read)."""
    if not getattr(sect, "decree_text", None):
        return None
    expires_at = getattr(sect, "decree_expires_at", None)
    if not expires_at:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return None
    return {
        "text": sect.decree_text,
        "expires_at": expires_at,
        "author_id": getattr(sect, "decree_author_id", None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# v14.2 D-3b — /passar_tocha ritual.
# Authentic Wuxia trope: the master voluntarily abdicates to a chosen Elder.
# Master remains as Elder (preserves voice in the council). Cooldown 30 days.
# ─────────────────────────────────────────────────────────────────────────────

TORCH_COOLDOWN_DAYS = 30
TORCH_PENDING_TTL_HOURS = 24


def torch_cooldown_remaining(sect) -> timedelta | None:
    last = getattr(sect, "last_torch_passed_at", None)
    if not last:
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    end = last + timedelta(days=TORCH_COOLDOWN_DAYS)
    now = datetime.now(timezone.utc)
    if end <= now:
        return None
    return end - now


def _torch_pending_is_fresh(sect) -> bool:
    pat = getattr(sect, "pending_torch_at", None)
    if not pat:
        return False
    if pat.tzinfo is None:
        pat = pat.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - pat) < timedelta(hours=TORCH_PENDING_TTL_HOURS)


async def initiate_torch_pass(session: Session, master_id: int, target_dao_name: str) -> dict:
    """Master initiates the torch ritual. Validates cooldown + target rank.
    Stores pending state on Sect; consent comes via accept_torch_pass."""
    info = await get_player_sect_info(session, master_id)
    if not info:
        return {"ok": False, "reason": "not_in_sect"}
    if info["member"].rank != "master":
        return {"ok": False, "reason": "master_only"}

    sect = info["sect"]

    # SELECT FOR UPDATE the sect row to serialise the pending-torch slot
    # against any concurrent /passar_tocha or accept callback.
    sect = (await session.execute(
        select(Sect).where(Sect.id == sect.id).with_for_update()
    )).scalar_one()

    cooldown = torch_cooldown_remaining(sect)
    if cooldown is not None:
        days_left = max(1, int(cooldown.total_seconds() // 86400))
        return {"ok": False, "reason": "cooldown", "days_remaining": days_left}

    if sect.pending_torch_to_id and _torch_pending_is_fresh(sect):
        return {"ok": False, "reason": "already_pending",
                "pending_to_id": int(sect.pending_torch_to_id)}

    target_member, target_player = await _resolve_target_in_sect(
        session, sect.id, target_dao_name
    )
    if not target_member or not target_player:
        return {"ok": False, "reason": "target_not_in_sect"}
    if target_member.player_id == master_id:
        return {"ok": False, "reason": "cannot_target_self"}
    if target_member.rank != "elder":
        return {"ok": False, "reason": "target_not_elder"}

    sect.pending_torch_to_id = target_player.telegram_id
    sect.pending_torch_at = datetime.now(timezone.utc)

    return {
        "ok": True,
        "sect_id": str(sect.id),
        "sect_name": sect.name,
        "target_id": int(target_player.telegram_id),
        "target_name": target_player.dao_name,
        "expires_at": sect.pending_torch_at + timedelta(hours=TORCH_PENDING_TTL_HOURS),
    }


async def accept_torch_pass(session: Session, target_id: int) -> dict:
    """Elder accepts the torch. Demotes outgoing master to elder, promotes target
    to master. Updates Sect.master_id + cooldown. Returns players involved so the
    caller can DM both."""
    info = await get_player_sect_info(session, target_id)
    if not info:
        return {"ok": False, "reason": "not_in_sect"}
    sect = (await session.execute(
        select(Sect).where(Sect.id == info["sect"].id).with_for_update()
    )).scalar_one()

    if not sect.pending_torch_to_id or sect.pending_torch_to_id != target_id:
        return {"ok": False, "reason": "no_pending_for_you"}
    if not _torch_pending_is_fresh(sect):
        # Stale pending state — clear it so a new pass can be initiated.
        sect.pending_torch_to_id = None
        sect.pending_torch_at = None
        return {"ok": False, "reason": "expired"}

    outgoing_master_id = sect.master_id

    # Lock both SectMember rows to serialise rank changes.
    rows = (await session.execute(
        select(SectMember)
        .where(SectMember.sect_id == sect.id,
               SectMember.player_id.in_([outgoing_master_id, target_id]))
        .with_for_update()
    )).scalars().all()
    rank_by_pid = {m.player_id: m for m in rows}
    outgoing = rank_by_pid.get(outgoing_master_id)
    incoming = rank_by_pid.get(target_id)
    if not outgoing or not incoming:
        return {"ok": False, "reason": "members_missing"}
    if outgoing.rank != "master":
        # Concurrent change — abort cleanly.
        sect.pending_torch_to_id = None
        sect.pending_torch_at = None
        return {"ok": False, "reason": "race_master_changed"}

    outgoing.rank = "elder"
    incoming.rank = "master"
    sect.master_id = target_id
    sect.last_torch_passed_at = datetime.now(timezone.utc)
    sect.pending_torch_to_id = None
    sect.pending_torch_at = None

    return {
        "ok": True,
        "sect_id": str(sect.id),
        "sect_name": sect.name,
        "outgoing_master_id": int(outgoing_master_id),
        "new_master_id": int(target_id),
    }


async def refuse_torch_pass(session: Session, target_id: int) -> dict:
    """Elder refuses. Clears pending state. Cooldown does NOT trigger — master
    can try again with another elder."""
    info = await get_player_sect_info(session, target_id)
    if not info:
        return {"ok": False, "reason": "not_in_sect"}
    sect = (await session.execute(
        select(Sect).where(Sect.id == info["sect"].id).with_for_update()
    )).scalar_one()
    if not sect.pending_torch_to_id or sect.pending_torch_to_id != target_id:
        return {"ok": False, "reason": "no_pending_for_you"}

    outgoing_master_id = sect.master_id
    sect.pending_torch_to_id = None
    sect.pending_torch_at = None
    return {
        "ok": True,
        "sect_id": str(sect.id),
        "sect_name": sect.name,
        "outgoing_master_id": int(outgoing_master_id),
    }


async def list_open_sects(session: Session, page: int = 0, page_size: int = 10) -> dict:
    """Browse-able list of sects for non-members. Sorted by member_count desc
    so popular sects surface first. UUIDs cast to str for client safety."""
    page = max(0, int(page or 0))
    page_size = max(1, min(50, int(page_size or 10)))

    total = (await session.execute(select(func.count(Sect.id)))).scalar() or 0
    rows = (await session.execute(
        select(Sect)
        .order_by(Sect.member_count.desc(), Sect.created_at.asc())
        .offset(page * page_size).limit(page_size)
    )).scalars().all()

    sects = []
    for s in rows:
        sects.append({
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "member_count": int(s.member_count or 0),
            "max_members": int(s.max_members or 50),
            "is_full": (s.member_count or 0) >= (s.max_members or 50),
        })
    return {
        "sects": sects,
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "has_more": (page + 1) * page_size < int(total),
    }


# ── v15.3 — Sect war view for the mini-app ───────────────────────────────────

# Sect wars run every Friday 20:00 UTC (configured in scheduler.py). Window is
# 1h. Players have 1 attack each. The chat-side menu had this since v12; this
# helper packages the same data into a JSON projection the mini-app can render.

WAR_WINDOW_SECONDS = 3600  # 1h attack window after start
SECT_WAR_CRON_DAY = "fri"
SECT_WAR_CRON_HOUR = 20
SECT_WAR_CRON_MINUTE = 0


def _next_war_start_utc(now: datetime | None = None) -> datetime:
    """Return the next Friday 20:00 UTC after `now`. Defaults to now=UTC now."""
    now = now or datetime.now(timezone.utc)
    # weekday(): Mon=0..Sun=6, Fri=4
    days_ahead = (4 - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=SECT_WAR_CRON_HOUR, minute=SECT_WAR_CRON_MINUTE, second=0, microsecond=0
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


async def get_war_view_for_player(session, player_id: int) -> dict:
    """Project the full Sect War state for one viewer.

    Returns a dict shaped for the mini-app SectWarPanel:
      {
        active: bool,
        seconds_remaining: int,   // 0 when inactive
        next_war_at: ISO,         // when no active war
        my_sect_id, my_sect_name, my_sect_in_war: bool,
        already_attacked: bool,
        my_sect_bp_total: int,    // total BP of my sect members (server-snapshot)
        participating_sects: [{id, name, bp_total}],
        territories: [{
          id, name, bonus_stones, bonus_cb,
          current_owner_name (str|null), expires_in_days,
          contestants: [{sect_id, name, bp, is_mine}],
          my_sect_score: int,
          leader: {sect_id, name, bp},
        }],
        last_results: [...],  // last finished SectWarLog batch (optional)
      }

    All values are READ-only — no mutation. Caller (webserver) wraps in a
    session.commit() to release the SELECT FOR UPDATE locks (none here).
    """
    now = datetime.now(timezone.utc)

    war = (await session.execute(
        select(SectWarState).where(SectWarState.is_active == True)
    )).scalar_one_or_none()

    # Check if "active" war is actually past its window — auto-coerce to inactive
    # so the UI doesn't show a stale war as still running.
    war_active = False
    seconds_remaining = 0
    if war and war.started_at:
        elapsed = (now - war.started_at).total_seconds()
        if elapsed < WAR_WINDOW_SECONDS:
            war_active = True
            seconds_remaining = int(WAR_WINDOW_SECONDS - elapsed)

    # Player's sect membership snapshot.
    member = (await session.execute(
        select(SectMember).where(SectMember.player_id == player_id)
    )).scalar_one_or_none()
    my_sect_id = str(member.sect_id) if member else None
    my_sect_name = None
    if member:
        sect_row = (await session.execute(
            select(Sect.name).where(Sect.id == member.sect_id)
        )).scalar_one_or_none()
        my_sect_name = sect_row or "???"

    out: dict = {
        "active": war_active,
        "seconds_remaining": seconds_remaining,
        "next_war_at": _next_war_start_utc(now).isoformat() if not war_active else None,
        "my_sect_id": my_sect_id,
        "my_sect_name": my_sect_name,
        "my_sect_in_war": False,
        "already_attacked": False,
        "my_sect_bp_total": 0,
        "participating_sects": [],
        "territories": [],
    }

    # Inactive war: still show territories (current owners + expiration).
    territories = (await session.execute(select(SectTerritory))).scalars().all()
    sect_by_id: dict[str, Sect] = {}
    if territories:
        owner_ids = {t.sect_id for t in territories if t.sect_id}
        if owner_ids:
            owners = (await session.execute(
                select(Sect).where(Sect.id.in_(owner_ids))
            )).scalars().all()
            sect_by_id = {str(s.id): s for s in owners}

    if not war_active:
        for terr in territories:
            owner_name = None
            expires_in_days = None
            if terr.sect_id:
                owner_name = (sect_by_id.get(str(terr.sect_id)) or _SectStub()).name
                if terr.expires_at:
                    delta_days = (terr.expires_at - now).total_seconds() / 86400.0
                    expires_in_days = max(0, int(round(delta_days)))
            out["territories"].append({
                "id": int(terr.id),
                "name": terr.name,
                "bonus_stones": int(terr.bonus_stones or 0),
                "bonus_cb": float(terr.bonus_cb or 0.0),
                "current_owner_name": owner_name,
                "expires_in_days": expires_in_days,
                "contestants": [],
                "my_sect_score": 0,
                "leader": None,
            })
        return out

    # Active war — enrich with attack state.
    participating = list(war.participating_sects or [])
    sect_names = dict(war.sect_names or {})
    attacks = dict(war.attacks or {})

    out["my_sect_in_war"] = (my_sect_id in participating) if my_sect_id else False
    out["already_attacked"] = (player_id in (war.attacked_players or []))

    # Aggregate BP per sect across all territories (for the "your sect / rivals
    # summary" card). Also surface participating sect list.
    sect_bp_totals: dict[str, int] = {}
    for sid in participating:
        sect_bp_totals[sid] = 0
    for terr_id, sect_map in attacks.items():
        for sid, bp in (sect_map or {}).items():
            sect_bp_totals[sid] = sect_bp_totals.get(sid, 0) + int(bp or 0)

    out["my_sect_bp_total"] = int(sect_bp_totals.get(my_sect_id, 0)) if my_sect_id else 0
    out["participating_sects"] = [
        {
            "id": sid,
            "name": sect_names.get(sid, "???"),
            "bp_total": int(sect_bp_totals.get(sid, 0)),
            "is_mine": (sid == my_sect_id),
        }
        for sid in participating
    ]

    for terr in territories:
        terr_attacks = attacks.get(str(terr.id), {}) or {}
        # Project per-contestant with defense bonus mult on the current owner.
        contestants: list[dict] = []
        leader: dict | None = None
        leader_score = -1
        for sid, raw_bp in terr_attacks.items():
            mult = 1.0
            if terr.sect_id and str(terr.sect_id) == sid:
                defending_sect = sect_by_id.get(str(terr.sect_id))
                if defending_sect:
                    mult = 1.0 + get_defense_bonus(int(defending_sect.defense_lvl or 0))
            adj = int(int(raw_bp or 0) * mult)
            entry = {
                "sect_id": sid,
                "name": sect_names.get(sid, "???"),
                "bp": adj,
                "is_mine": (sid == my_sect_id),
            }
            contestants.append(entry)
            if adj > leader_score:
                leader_score = adj
                leader = entry
        contestants.sort(key=lambda x: x["bp"], reverse=True)

        owner_name = None
        expires_in_days = None
        if terr.sect_id:
            owner_name = (sect_by_id.get(str(terr.sect_id)) or _SectStub()).name
            if terr.expires_at:
                delta_days = (terr.expires_at - now).total_seconds() / 86400.0
                expires_in_days = max(0, int(round(delta_days)))

        my_score = next((c["bp"] for c in contestants if c["is_mine"]), 0)

        out["territories"].append({
            "id": int(terr.id),
            "name": terr.name,
            "bonus_stones": int(terr.bonus_stones or 0),
            "bonus_cb": float(terr.bonus_cb or 0.0),
            "current_owner_name": owner_name,
            "expires_in_days": expires_in_days,
            "contestants": contestants,
            "my_sect_score": my_score,
            "leader": leader,
        })

    return out


class _SectStub:
    """Placeholder when a sect row is missing — prevents AttributeError on .name."""
    name = "???"
