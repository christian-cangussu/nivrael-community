import random
import uuid
import logging
from datetime import datetime, timezone, date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Player, PlayerVIP, BattlePass, GachaBanner, GachaHistory, GachaPity, PlayerArtifact, PlayerCauldron, PlayerTechnique

logger = logging.getLogger(__name__)

from core.i18n import t
# 名 2026-09-14 — o Passe Celeste diz o nome do premio na lingua do pagante.
from core.i18n import catalog_name as _cname
from config import VIP_TIERS_EUR, GACHA_COST, CURRENT_SEASON, ALCHEMY_ENERGY_VIP_MAX_BONUS, ALCHEMY_ENERGY_VIP_REGEN
from core.activity_indicators import _invalidate_cache as _inv_cache

# Define what each VIP level gives
def get_vip_perks(vip_level: int) -> dict:
    perks = {
        "expedition_slots": 0,
        "auction_tax_discount": 0.0, # e.g. 0.05 for 5%
        "offline_cap_hours": 4, # Base is 4 hours (will be overridden by VIP/Pass)
        "exclusive_title": None,
        "priority_world_boss": False,
        "custom_announce": False,
        "exclusive_frame": False,
        "alchemy_energy_max_bonus": ALCHEMY_ENERGY_VIP_MAX_BONUS.get(vip_level, 0),
        "alchemy_energy_regen_minutes": ALCHEMY_ENERGY_VIP_REGEN.get(vip_level, 15),
    }

    if vip_level >= 1:
        perks["expedition_slots"] += 1
        perks["auction_tax_discount"] += 0.05
    if vip_level >= 2:
        perks["offline_cap_hours"] = max(perks["offline_cap_hours"], 18)
    if vip_level >= 3:
        perks["exclusive_title"] = "VIP3_Title"
    if vip_level >= 4:
        perks["priority_world_boss"] = True
    if vip_level >= 5:
        perks["custom_announce"] = True
        perks["exclusive_frame"] = True

    return perks

async def get_player_vip_level(session: AsyncSession, player_id: int) -> int:
    stmt = select(PlayerVIP).where(PlayerVIP.player_id == player_id)
    vip_record = (await session.execute(stmt)).scalar_one_or_none()
    
    if not vip_record:
        return 0
    return vip_record.vip_level

# VIP Milestone rewards — one-time bonuses at spending thresholds
VIP_MILESTONES = {
    1:   {"jade": 30,  "stones": 2000,  "label": "First Step"},
    3:   {"jade": 60,  "stones": 5000,  "label": "Outer Disciple"},
    5:   {"jade": 100, "stones": 8000,  "label": "Inner Disciple"},
    10:  {"jade": 200, "stones": 15000, "fragments": 20, "label": "Core Disciple"},
    20:  {"jade": 400, "stones": 30000, "fragments": 50, "label": "Elder"},
    50:  {"jade": 800, "stones": 60000, "fragments": 100, "title": "Dao Benefactor", "label": "Sect Patriarch"},
    100: {"jade": 1500, "stones": 100000, "fragments": 200, "title": "Heaven's Patron", "label": "Immortal Patron"},
}


async def add_vip_spending(session: AsyncSession, player_id: int, amount_eur: float) -> dict:
    stmt = select(PlayerVIP).where(PlayerVIP.player_id == player_id)
    vip_record = (await session.execute(stmt)).scalar_one_or_none()

    if not vip_record:
        vip_record = PlayerVIP(player_id=player_id, vip_level=0, total_spent_eur=0.0)
        session.add(vip_record)

    vip_record.total_spent_eur += amount_eur

    old_level = vip_record.vip_level
    new_level = 0
    for level, req_eur in sorted(VIP_TIERS_EUR.items(), reverse=True):
        if vip_record.total_spent_eur >= req_eur:
            new_level = level
            break

    level_up = new_level > old_level
    vip_record.vip_level = max(old_level, new_level)

    # Check VIP milestones
    claimed_ms = list(vip_record.vip_milestones_claimed or [])
    new_milestones = []
    for threshold_eur, rewards in sorted(VIP_MILESTONES.items()):
        if vip_record.total_spent_eur >= threshold_eur and threshold_eur not in claimed_ms:
            new_milestones.append((threshold_eur, rewards))
            claimed_ms.append(threshold_eur)

    milestone_grants = []
    if new_milestones:
        player = (await session.execute(select(Player).where(Player.telegram_id == player_id))).scalar_one_or_none()
        if player:
            for threshold_eur, rewards in new_milestones:
                if rewards.get("jade"):
                    await grant_jade(session, player, rewards["jade"])
                if rewards.get("stones"):
                    player.spirit_stones += rewards["stones"]
                if rewards.get("fragments"):
                    player.celestial_fragments = (player.celestial_fragments or 0) + rewards["fragments"]
                if rewards.get("title"):
                    titles = list(player.unlocked_titles or [])
                    if rewards["title"] not in titles:
                        titles.append(rewards["title"])
                        player.unlocked_titles = titles
                        from sqlalchemy.orm.attributes import flag_modified as fm_titles
                        fm_titles(player, "unlocked_titles")
                    player.active_title = rewards["title"]
                milestone_grants.append({
                    "threshold": threshold_eur,
                    "label": rewards["label"],
                    "jade": rewards.get("jade", 0),
                    "stones": rewards.get("stones", 0),
                    "fragments": rewards.get("fragments", 0),
                    "title": rewards.get("title"),
                })
        vip_record.vip_milestones_claimed = claimed_ms
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(vip_record, "vip_milestones_claimed")

    return {
        "level_up": level_up,
        "old_level": old_level,
        "new_level": vip_record.vip_level,
        "milestones": milestone_grants,
    }


# Battle Pass Config
# Celestial Pass costs e.g. €4.99/month
# Daily Jade: 10
async def get_active_battle_pass(session: AsyncSession, player_id: int) -> BattlePass | None:
    stmt = select(BattlePass).where(BattlePass.player_id == player_id, BattlePass.season == CURRENT_SEASON)
    return (await session.execute(stmt)).scalar_one_or_none()

async def activate_battle_pass(session: AsyncSession, player_id: int) -> bool:
    stmt = select(BattlePass).where(BattlePass.player_id == player_id, BattlePass.season == CURRENT_SEASON)
    bp = (await session.execute(stmt)).scalar_one_or_none()
    
    if bp:
        if bp.is_premium:
            return False # already active
        bp.is_premium = True
    else:
        bp = BattlePass(
            player_id=player_id,
            season=CURRENT_SEASON,
            tier=1,
            is_premium=True
        )
        session.add(bp)
    
    # Retroactively complete one-time missions for advanced players
    # Wrapped in try/except so pass activation succeeds even if retroactive progress fails
    try:
        from core.bp_engine import retroactive_bp_progress
        await retroactive_bp_progress(session, player_id)
    except Exception:
        logger.exception("retroactive_bp_progress failed for player %s (pass still activated)", player_id)
    
    return True

async def grant_jade(session: AsyncSession, player, amount: int) -> list:
    """THE canonical jade grant: credits the balance, bumps the monotonic
    ``lifetime_jade_earned`` counter (Migration 115) and fires Achievement #12
    Jade Collector with the LIFETIME value. Every earn path must route here —
    the old pattern (bare ``player.spirit_jade += X`` + passive balance
    snapshots on /status) made "Accumulate 10,000" unreachable for players who
    spend as they earn ([jogador], 2026-06-12). NEVER call this on refund paths
    (refunds are spend rollbacks, not income). Returns newly-unlocked
    achievements (callers may ignore). Defensive: the achievement fire must
    never break the grant."""
    amount = int(amount or 0)
    if amount <= 0:
        return []
    player.spirit_jade = int(player.spirit_jade or 0) + amount
    player.lifetime_jade_earned = int(getattr(player, "lifetime_jade_earned", 0) or 0) + amount
    try:
        from core.achievement_engine import check_achievements
        unlocked = await check_achievements(
            session, player.telegram_id, "jade_accumulated",
            int(player.lifetime_jade_earned),
        )
        if unlocked:
            # The unlock now happens at EARN time, where no caller forwards it
            # to notify_achievements (review finding: the congratulation would
            # vanish). Push the mini-app bell here — same keys + ref_id dedup
            # as notify_achievements, so no double-bell if a snapshot path
            # re-fires. The chat DM needs a bot handle earn sites don't have;
            # the bell + achievements tab carry the moment (mini-app canonical).
            try:
                from core.notification_engine import notify as _notify
                for ach in unlocked:
                    await _notify(
                        session, player.telegram_id, "achievement_unlock",
                        title_key="notif_achievement_title",
                        body_key="notif_achievement_body",
                        payload={"name": ach.name, "emoji": ach.emoji or "🏆"},
                        ref_id=f"ach:{ach.code}" if hasattr(ach, "code") else f"ach:{ach.id}",
                        icon=ach.emoji or "🏆",
                        target_tab="achievements",
                        priority=3,
                    )
            except Exception:
                logger.warning("achievement bell notify failed (player=%s)",
                               getattr(player, "telegram_id", "?"), exc_info=True)
        return unlocked
    except Exception:
        logger.warning("jade_accumulated fire failed (player=%s)",
                       getattr(player, "telegram_id", "?"), exc_info=True)
        return []


async def claim_daily_bp_jade(session: AsyncSession, player_id: int) -> dict:
    # Lock the BP row HERE so BOTH surfaces (chat button + mini-app endpoint)
    # serialize on it — review finding: the endpoint's own FOR UPDATE only
    # blocked other lockers, and the chat path read lock-free, leaving a
    # chat×mini-app double-claim window on the daily +10.
    bp = (await session.execute(
        select(BattlePass).where(
            BattlePass.player_id == player_id,
            BattlePass.season == CURRENT_SEASON,
        ).with_for_update()
    )).scalar_one_or_none()
    if not bp or not bp.is_premium:
        return {"success": False, "error_key": "err_bp_not_active"}

    now = datetime.now(timezone.utc)
    if bp.daily_jade_claimed_at and bp.daily_jade_claimed_at.date() == now.date():
        return {"success": False, "error_key": "err_bp_jade_already_claimed"}

    stmt = select(Player).where(Player.telegram_id == player_id)
    player = (await session.execute(stmt)).scalar_one_or_none()
    if not player:
        return {"success": False, "error_key": "err_player_not_found"}
        
    granted = 10
    await grant_jade(session, player, granted)
    bp.daily_jade_claimed_at = now
    _inv_cache(player_id)
    return {"success": True, "granted": granted}


# Gacha Engine (Ancient Chest)
# 160 jade = 1 pull, 1440 = 10 pulls
# Pity 90 = Guaranteed Legendary

def gacha_enabled() -> bool:
    """開 Edição comunitária — o gacha só abre com `NIVRAEL_MONETIZATION=1`.

    É aqui, no dono da tiragem, e não nas telas: o chat e o mini-app chamam os
    dois esta função, logo fechar aqui fecha em todo o lado de uma vez."""
    from config import MONETIZATION_ENABLED
    return bool(MONETIZATION_ENABLED)


async def perform_gacha_pull(session: AsyncSession, player_id: int, num_pulls: int, banner_id: str, use_tickets: bool = False) -> dict:
    if not gacha_enabled():
        return {"success": False, "error_key": "err_gacha_official_only"}
    stmt = select(Player).where(Player.telegram_id == player_id)
    player = (await session.execute(stmt)).scalar_one()

    if use_tickets:
        # Pay with gacha tickets from inventory
        from database.models import PlayerInventory
        ticket_inv = (await session.execute(
            select(PlayerInventory).where(
                PlayerInventory.player_id == player_id,
                PlayerInventory.item_type == "gacha_ticket",
                PlayerInventory.item_id == 0,
            )
        )).scalar_one_or_none()
        if not ticket_inv or ticket_inv.quantity < num_pulls:
            return {"success": False, "error_key": "err_tickets_insufficient"}
        ticket_inv.quantity -= num_pulls
        if ticket_inv.quantity <= 0:
            await session.delete(ticket_inv)
        total_cost = 0
    else:
        total_cost = GACHA_COST * 10 * 0.9 if num_pulls == 10 else GACHA_COST * num_pulls
        if player.spirit_jade < total_cost:
            return {"success": False, "error_key": "err_jade_insufficient"}
        player.spirit_jade -= int(total_cost)

    stmt_banner = select(GachaBanner).where(GachaBanner.id == banner_id)
    banner = (await session.execute(stmt_banner)).scalar_one_or_none()

    if not banner or not banner.is_active:
        return {"success": False, "error_key": "err_banner_not_found"}

    # ── Load pity from dedicated table (persistent, survives history truncation) ──
    stmt_pity = select(GachaPity).where(
        GachaPity.player_id == player_id,
        GachaPity.banner_id == banner_id
    ).with_for_update()
    pity_record = (await session.execute(stmt_pity)).scalar_one_or_none()
    current_pity = pity_record.current_pity if pity_record else 0

    results = []
    
    guarantee_rare = (num_pulls >= 10)
    has_rare_or_better = False

    for i in range(num_pulls):
        current_pity += 1
        is_pity = current_pity >= banner.pity_at

        # Determine rarity
        roll = random.random()
        rarity = "common"
        if is_pity:
            rarity = "legendary"
        elif roll < 0.02:  # 2% for legendary
            rarity = "legendary"
        elif roll < 0.10:  # 8% for epic
            rarity = "epic"
        elif roll < 0.30:  # 20% for rare
            rarity = "rare"
            
        # 10x guarantee: if we reach the last pull of a 10-pull and haven't hit rare+, force it.
        if guarantee_rare and i == num_pulls - 1 and not has_rare_or_better:
            rarity = "rare"
            if roll < 0.2: # let's give a small chance for epic anyway on the guaranteed rare
                rarity = "epic"
                
        if rarity in ("rare", "epic", "legendary"):
            has_rare_or_better = True

        if rarity == "legendary":
            current_pity = 0  # Reset pity only on legendary
            
        # Pick item from banner pool based on rarity.
        # Seeds use: {"weight": N, "items": [...]}
        # Legacy format uses a plain list directly.
        rarity_bucket = banner.items.get(rarity)
        if isinstance(rarity_bucket, dict):
            item_list = rarity_bucket.get("items", [])
        elif isinstance(rarity_bucket, list):
            item_list = rarity_bucket
        else:
            item_list = []

        result_item = "fallback"
        result_name = "1000 Spirit Stones"
        result_type = "spirit_stones"

        # ── Celestial Fragments: commons give fragments instead of junk ──
        if rarity == "common":
            frag_amount = random.randint(3, 8)
            player.celestial_fragments = (getattr(player, 'celestial_fragments', 0) or 0) + frag_amount
            result_item = str(frag_amount)
            result_name = f"{frag_amount} Celestial Fragments"
            result_type = "celestial_fragment"
            # Also give a small amount of stones so it doesn't feel completely different
            player.spirit_stones += 500

        elif not item_list:
            # Fallback: grant 1000 spirit stones
            player.spirit_stones += 1000
        else:
            chosen = random.choice(item_list)
            result_name = chosen.get("name", "Unknown Item")
            result_type = chosen.get("type", "item")

            # Normalise item ID: seeds use catalog_id / herb_id / pill_id / ore_id
            if result_type == "artifact":
                catalog_id_val = chosen.get("catalog_id") or chosen.get("id")
                result_item = str(catalog_id_val) if catalog_id_val else "unknown"

                # Fetch catalog for base_stats and grade (same approach as forge_engine)
                from database.models import ArtifactCatalog
                catalog_entry = (await session.execute(
                    select(ArtifactCatalog).where(ArtifactCatalog.id == int(catalog_id_val))
                )).scalar_one_or_none()

                art_grade = 0
                art_stats = {}
                if catalog_entry:
                    art_grade = catalog_entry.grade or 0
                    if catalog_entry.base_stats:
                        art_stats = catalog_entry.base_stats.copy()
                        # Scale stats by grade (same formula as forge)
                        multiplier = 1.0 + (art_grade * 0.5)
                        for stat_key in art_stats:
                            art_stats[stat_key] = int(art_stats[stat_key] * multiplier)

                new_art = PlayerArtifact(
                    player_id=player.telegram_id,
                    catalog_id=int(catalog_id_val),
                    grade=art_grade,
                    custom_stats=art_stats,
                )
                session.add(new_art)

            elif result_type in ("spirit_stones", "stones"):
                amount = chosen.get("amount", 1000)
                player.spirit_stones += amount
                result_item = str(amount)
                result_type = "spirit_stones"

            elif result_type == "herb":
                item_id = chosen.get("herb_id") or chosen.get("id")
                qty = chosen.get("qty", 1)
                result_item = str(item_id)
                from core.utils import add_item_to_inventory
                await add_item_to_inventory(session, player.telegram_id, "herb", int(item_id), qty)

            elif result_type == "pill":
                item_id = chosen.get("pill_id") or chosen.get("id")
                qty = chosen.get("qty", 1)
                result_item = str(item_id)
                from core.utils import add_item_to_inventory
                await add_item_to_inventory(session, player.telegram_id, "pill", int(item_id), qty)

            elif result_type == "ore":
                item_id = chosen.get("ore_id") or chosen.get("id")
                qty = chosen.get("qty", 1)
                result_item = str(item_id)
                from database.models import PlayerOre
                ore_stmt = select(PlayerOre).where(
                    PlayerOre.player_id == player.telegram_id,
                    PlayerOre.ore_id == int(item_id)
                )
                p_ore = (await session.execute(ore_stmt)).scalars().first()
                if p_ore:
                    p_ore.quantity += qty
                else:
                    session.add(PlayerOre(player_id=player.telegram_id, ore_id=int(item_id), quantity=qty))

            elif result_type == "beast_trap":
                qty = chosen.get("qty", 1)
                result_item = chosen.get("rarity", "common")
                trap_item_id = chosen.get("item_id", 0)
                from core.utils import add_item_to_inventory
                await add_item_to_inventory(session, player.telegram_id, "beast_trap", trap_item_id, qty, chosen.get("rarity", "common"))

            elif result_type == "technique_scroll":
                tech_id = chosen.get("technique_id") or chosen.get("id")
                qty = chosen.get("qty", 1)
                result_item = str(tech_id)
                from core.utils import add_item_to_inventory
                await add_item_to_inventory(session, player.telegram_id, "technique_scroll", int(tech_id), qty)

            elif result_type == "beast_egg":
                beast_id = chosen.get("beast_id") or chosen.get("id")
                qty = chosen.get("qty", 1)
                result_item = str(beast_id)
                from core.utils import add_item_to_inventory
                await add_item_to_inventory(session, player.telegram_id, "beast_egg", int(beast_id), qty)

            elif result_type == "core_essence":
                amount = chosen.get("amount", 10)
                from core.golden_core_engine import add_core_essence
                added = add_core_essence(player, amount)
                result_item = str(added) if added > 0 else "0"

            elif result_type == "alchemy_xp":
                amount = chosen.get("amount", 500)
                result_item = str(amount)
                from database.models import PlayerAlchemySkill
                alch_stmt = select(PlayerAlchemySkill).where(PlayerAlchemySkill.player_id == player.telegram_id)
                alch = (await session.execute(alch_stmt)).scalar_one_or_none()
                if alch:
                    alch.xp += amount
                else:
                    session.add(PlayerAlchemySkill(player_id=player.telegram_id, xp=amount))

            elif result_type == "forge_xp":
                amount = chosen.get("amount", 300)
                result_item = str(amount)
                from database.models import PlayerForgeSkill
                forge_stmt = select(PlayerForgeSkill).where(PlayerForgeSkill.player_id == player.telegram_id)
                forge = (await session.execute(forge_stmt)).scalar_one_or_none()
                if forge:
                    forge.xp += amount
                else:
                    session.add(PlayerForgeSkill(player_id=player.telegram_id, xp=amount))

            else:
                # Unknown type: grant spirit stones as fallback
                player.spirit_stones += 500
                result_item = "500"
                result_type = "spirit_stones"
                result_name = "500 Spirit Stones (fallback)"
                logger.warning(f"Gacha: unknown item type '{result_type}' in banner {banner_id}")

        # Save pull history (pity_count reflects current pull's counter value)
        hist = GachaHistory(
            player_id=player.telegram_id,
            banner_id=banner.id,
            result_item_id=result_item,
            result_rarity=rarity,
            pity_count=current_pity
        )
        session.add(hist)

        results.append({
            "name": result_name,
            "rarity": rarity,
            "type": result_type,
            "art_grade": art_grade if result_type == "artifact" else None,
            "is_pity": is_pity
        })

    # ── Persist pity counter (upsert to prevent race on first pull) ─────────────
    now = datetime.now(timezone.utc)
    upsert_stmt = pg_insert(GachaPity).values(
        player_id=player_id,
        banner_id=banner_id,
        current_pity=current_pity,
        updated_at=now,
    ).on_conflict_do_update(
        constraint="uq_gacha_pity",
        set_={"current_pity": current_pity, "updated_at": now},
    )
    await session.execute(upsert_stmt)

    return {
        "success": True,
        "results": results,
        "new_pity": current_pity,
        "cost": total_cost,
        "remaining_jade": player.spirit_jade
    }

async def get_gacha_pity(session: AsyncSession, player_id: int, banner_id: str) -> int:
    stmt = select(GachaPity).where(GachaPity.player_id == player_id, GachaPity.banner_id == banner_id)
    pity_record = (await session.execute(stmt)).scalar_one_or_none()
    return pity_record.current_pity if pity_record else 0

async def ensure_default_banner(session: AsyncSession):
    from database.seeds.gacha_seeds import GACHA_BANNERS
    
    chest_seed = next((b for b in GACHA_BANNERS if b["id"] == "ancient_chest_01"), None)
    if not chest_seed:
        return
        
    stmt = select(GachaBanner).where(GachaBanner.id == "ancient_chest_01")
    banner = (await session.execute(stmt)).scalar_one_or_none()
    
    if banner:
        # Overwrite with latest seed items
        banner.items = chest_seed["items"]
        banner.name = chest_seed["name"]
        banner.description = chest_seed["description"]
        banner.pity_at = chest_seed["pity_at"]
    else:
        b = GachaBanner(
            id=chest_seed["id"],
            name=chest_seed["name"],
            description=chest_seed["description"],
            items=chest_seed["items"],
            pity_at=chest_seed["pity_at"],
            is_active=chest_seed["is_active"]
        )
        session.add(b)
    await session.commit()


# ─── Battle Pass Tier Rewards ─────────────────────────────────────────────────
# Tiers 1-10:  basic resources (stones, herbs, basic pills)
# Tiers 11-20: scrolls, ores, beast traps
# Tiers 21-29: rare pills, artifact chests, gacha tickets
# Tier 30:     exclusive title "Celestial Patron" + premium loot

BATTLE_PASS_REWARDS = {
    1:  [{"type": "spirit_stones", "amount": 500}],
    2:  [{"type": "herb", "herb_id": 1, "qty": 10}],
    3:  [{"type": "pill", "pill_id": 1, "qty": 3}],
    4:  [{"type": "spirit_stones", "amount": 1000}],
    5:  [{"type": "herb", "herb_id": 2, "qty": 8}, {"type": "pill", "pill_id": 2, "qty": 2}],
    6:  [{"type": "spirit_stones", "amount": 1500}],
    7:  [{"type": "pill", "pill_id": 3, "qty": 3}],
    8:  [{"type": "herb", "herb_id": 3, "qty": 5}, {"type": "spirit_stones", "amount": 1000}],
    9:  [{"type": "pill", "pill_id": 6, "qty": 5}],
    10: [{"type": "spirit_stones", "amount": 3000}, {"type": "herb", "herb_id": 4, "qty": 5}],
    # Tiers 11-20: mid-tier rewards
    11: [{"type": "technique_scroll", "technique_id": 1, "qty": 1}],
    12: [{"type": "ore", "ore_id": 2, "qty": 5}],
    13: [{"type": "beast_trap", "rarity": "common", "qty": 3}],
    14: [{"type": "spirit_stones", "amount": 5000}],
    15: [{"type": "ore", "ore_id": 3, "qty": 5}, {"type": "technique_scroll", "technique_id": 3, "qty": 1}],
    16: [{"type": "beast_trap", "rarity": "rare", "qty": 2}],
    17: [{"type": "ore", "ore_id": 4, "qty": 3}, {"type": "spirit_stones", "amount": 3000}],
    18: [{"type": "technique_scroll", "technique_id": 5, "qty": 1}],
    19: [{"type": "beast_trap", "rarity": "epic", "qty": 1}, {"type": "ore", "ore_id": 3, "qty": 5}],
    20: [{"type": "spirit_stones", "amount": 8000}, {"type": "technique_scroll", "technique_id": 7, "qty": 1}],
    # Tiers 21-29: premium rewards
    21: [{"type": "pill", "pill_id": 8, "qty": 3}],
    22: [{"type": "gacha_ticket", "qty": 1}],
    23: [{"type": "pill", "pill_id": 10, "qty": 2}],
    24: [{"type": "spirit_stones", "amount": 10000}],
    25: [{"type": "gacha_ticket", "qty": 2}, {"type": "pill", "pill_id": 8, "qty": 5}],
    26: [{"type": "beast_trap", "rarity": "mythic", "qty": 1}],
    27: [{"type": "pill", "pill_id": 13, "qty": 1}, {"type": "spirit_stones", "amount": 10000}],
    28: [{"type": "gacha_ticket", "qty": 3}],
    29: [{"type": "spirit_stones", "amount": 20000}, {"type": "pill", "pill_id": 10, "qty": 3}],
    # Tier 30: exclusive title + loot
    30: [{"type": "title", "value": "Celestial Patron"}, {"type": "gacha_ticket", "qty": 5}, {"type": "spirit_stones", "amount": 30000}],
}

# Overflow rewards cycle every 5 tiers after tier 30
BATTLE_PASS_OVERFLOW_CYCLE = [
    [{"type": "spirit_stones", "amount": 500}],
    [{"type": "spirit_jade", "amount": 15}],
    [{"type": "spirit_stones", "amount": 1000}],
    [{"type": "gacha_ticket", "qty": 1}],
    [{"type": "spirit_jade", "amount": 25}, {"type": "celestial_fragments", "amount": 10}],
]


def get_bp_rewards_for_tier(tier: int) -> list:
    """Get rewards for any tier, including overflow tiers beyond 30."""
    if tier <= 30:
        return BATTLE_PASS_REWARDS.get(tier, [])
    # Overflow: cycle every 5 tiers
    idx = (tier - 31) % len(BATTLE_PASS_OVERFLOW_CYCLE)
    return BATTLE_PASS_OVERFLOW_CYCLE[idx]


async def claim_battle_pass_tier(session: AsyncSession, player_id: int, tier: int, lang: str = "en") -> dict:
    """Claim rewards for a specific BP tier. Returns success/failure + reward details."""
    bp = await get_active_battle_pass(session, player_id)
    if not bp or not bp.is_premium:
        return {"success": False, "error": "no_active_pass"}

    if tier < 1:
        return {"success": False, "error": "invalid_tier"}

    if tier > bp.tier:
        return {"success": False, "error": "tier_not_reached"}

    # Track claimed tiers in bp.claimed_tiers (JSON list)
    claimed = list(bp.claimed_tiers or [])  # COPY — new object so SQLAlchemy detects JSONB change
    if tier in claimed:
        return {"success": False, "error": "already_claimed"}

    rewards = get_bp_rewards_for_tier(tier)
    if not rewards:
        return {"success": False, "error": "no_rewards"}

    stmt = select(Player).where(Player.telegram_id == player_id)
    player = (await session.execute(stmt)).scalar_one_or_none()
    if not player:
        return {"success": False, "error": "player_not_found"}

    granted = []
    for reward in rewards:
        r_type = reward["type"]
        if r_type == "spirit_stones":
            player.spirit_stones += reward["amount"]
            granted.append(f"🪨 {reward['amount']} {t(lang, 'currency_spirit_stones')}")

        elif r_type == "herb":
            herb_id = reward["herb_id"]
            qty = reward.get("qty", 1)
            from core.utils import add_item_to_inventory
            await add_item_to_inventory(session, player_id, "herb", herb_id, qty)
            from database.models import HerbCatalog
            _bp_herb = await session.get(HerbCatalog, herb_id)
            _bp_herb_name = _cname(lang, "herb", _bp_herb) if _bp_herb else f"Herb #{herb_id}"
            granted.append(f"🌿 {_bp_herb_name} ×{qty}")

        elif r_type == "pill":
            pill_id = reward["pill_id"]
            qty = reward.get("qty", 1)
            from core.utils import add_item_to_inventory
            await add_item_to_inventory(session, player_id, "pill", pill_id, qty)
            from database.models import PillCatalog
            _pill = await session.get(PillCatalog, pill_id)
            _pill_name = _cname(lang, "pill", _pill) if _pill else f"Pill #{pill_id}"
            granted.append(f"💊 {_pill_name} ×{qty}")

        elif r_type == "ore":
            ore_id = reward["ore_id"]
            qty = reward.get("qty", 1)
            from database.models import PlayerOre, OreCatalog
            ore_stmt = select(PlayerOre).where(
                PlayerOre.player_id == player_id,
                PlayerOre.ore_id == ore_id
            )
            p_ore = (await session.execute(ore_stmt)).scalars().first()
            if p_ore:
                p_ore.quantity += qty
            else:
                session.add(PlayerOre(player_id=player_id, ore_id=ore_id, quantity=qty))
            _bp_ore = await session.get(OreCatalog, ore_id)
            _bp_ore_name = _cname(lang, "ore", _bp_ore) if _bp_ore else f"Ore #{ore_id}"
            granted.append(f"⛏️ {_bp_ore_name} ×{qty}")

        elif r_type == "technique_scroll":
            tech_id = reward["technique_id"]
            qty = reward.get("qty", 1)
            from core.utils import add_item_to_inventory
            await add_item_to_inventory(session, player_id, "technique_scroll", tech_id, qty)
            granted.append(f"📜 Technique Scroll #{tech_id} ×{qty}")

        elif r_type == "beast_trap":
            qty = reward.get("qty", 1)
            rarity = reward.get("rarity", "common")
            trap_item_id = reward.get("item_id", 0)
            from core.utils import add_item_to_inventory
            await add_item_to_inventory(session, player_id, "beast_trap", trap_item_id, qty, rarity)
            granted.append(f"🪤 {rarity.title()} Beast Trap ×{qty}")

        elif r_type == "gacha_ticket":
            qty = reward.get("qty", 1)
            from core.utils import add_item_to_inventory
            await add_item_to_inventory(session, player_id, "gacha_ticket", 0, qty)
            granted.append(f"🎟️ Gacha Ticket ×{qty}")

        elif r_type == "title":
            title_val = reward["value"]
            titles = list(player.unlocked_titles or [])
            if title_val and title_val not in titles:
                titles.append(title_val)
                player.unlocked_titles = titles
                from sqlalchemy.orm.attributes import flag_modified as fm_t2
                fm_t2(player, "unlocked_titles")
            player.active_title = title_val
            granted.append(f"🏅 Title: {title_val}")

        elif r_type == "spirit_jade":
            amount = reward["amount"]
            await grant_jade(session, player, amount)
            granted.append(f"💎 {amount} Spirit Jade")

        elif r_type == "celestial_fragments":
            amount = reward["amount"]
            player.celestial_fragments = (player.celestial_fragments or 0) + amount
            granted.append(f"🔮 {amount} Celestial Fragments")

    # Mark tier as claimed
    claimed.append(tier)
    bp.claimed_tiers = claimed
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(bp, "claimed_tiers")
    _inv_cache(player_id)

    return {"success": True, "granted": granted, "tier": tier}


async def set_battle_pass_tier(session: AsyncSession, player_id: int, tier: int) -> bool:
    """Admin: manually set a player's BP tier."""
    bp = await get_active_battle_pass(session, player_id)
    if not bp:
        return False
    bp.tier = max(1, tier)
    return True
