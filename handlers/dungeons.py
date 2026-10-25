import random
import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, and_

from core.utils import safe_handler, rate_limit, _get_player, escape_markdown, safe_answer, safe_parse_callback_int, add_item_to_inventory, normalize_lang, build_pagination_keyboard
from core.game_logic import format_number
from core.combat_engine import simulate_combat, build_fighter_data, apply_hp_drain, apply_hp_drain_scaled, get_current_hp, get_max_hp, apply_stance_and_focus, STANCES
from core.i18n import t
# 名 2026-09-14 — o espolio da masmorra deixa de sair em ingles.
from core.i18n import catalog_name as _cname
from core.quest_engine import track_quest
from core.activity_indicators import _invalidate_cache as _inv_cache
from database.db import get_session_with_retry
from database.models import (
    Player, PlayerDungeon, DungeonCatalog,
    PlayerArtifact, PlayerTechnique, TechniqueCatalog,
    PlayerInventory, PlayerOre,
    HerbCatalog, OreCatalog,
)

logger = logging.getLogger(__name__)


# ─── Difficulty System ────────────────────────────────────────────────────────

DIFFICULTIES = ["easy", "normal", "hard", "nightmare"]
DIFF_ORDER = {"easy": 1, "normal": 2, "hard": 3, "nightmare": 4}

DIFF_CONFIG = {
    "easy":      {"bp_lo": 0.5, "bp_hi": 0.8,  "loot_mult": 0.5, "emoji": "🟢"},
    "normal":    {"bp_lo": 0.8, "bp_hi": 1.2,  "loot_mult": 1.0, "emoji": "🟡"},
    "hard":      {"bp_lo": 1.2, "bp_hi": 2.0,  "loot_mult": 2.0, "emoji": "🔴"},
    "nightmare": {"bp_lo": 2.0, "bp_hi": 3.5,  "loot_mult": 3.0, "emoji": "💀"},
}

HP_PER_BP = 4.0
DUNGEONS_PER_PAGE = 6

DUNGEON_HP_DRAIN = {
    "easy": 0.40,
    "normal": 0.55,
    "hard": 0.70,
    "nightmare": 0.90,
}


def _get_floor_count(dungeon: DungeonCatalog, difficulty: str) -> int:
    """Get floor count for a specific difficulty."""
    if dungeon.floor_counts and difficulty in dungeon.floor_counts:
        return dungeon.floor_counts[difficulty]
    return dungeon.floor_count


def _parse_diff_callback(data: str, prefix: str) -> tuple:
    """Parse 'prefix{id}_{difficulty}' → (id, difficulty)."""
    rest = data[len(prefix):]
    parts = rest.split("_", 1)
    if len(parts) != 2:
        return None, None
    try:
        did = int(parts[0])
    except ValueError:
        return None, None
    diff = parts[1]
    if diff not in DIFF_CONFIG:
        return None, None
    return did, diff


def _apply_difficulty_loot_mult(loot: dict, difficulty: str) -> dict:
    """Apply difficulty loot multiplier to a loot bag."""
    mult = DIFF_CONFIG[difficulty]["loot_mult"]
    if mult == 1.0:
        return loot
    result = {}
    for key, val in loot.items():
        if key in ("herbs", "ores", "healing_pills") and isinstance(val, dict):
            result[key] = {k: max(1, int(v * mult)) for k, v in val.items()}
        elif key == "qi_pill_id":
            result[key] = val  # D4: tier marker, never scale it
        elif isinstance(val, (int, float)):
            result[key] = max(1, int(val * mult))
        else:
            result[key] = val
    return result


def _effective_qi_cost(base_cost: int, player_realm: int) -> int:
    """Scale dungeon Qi cost by player realm: base * (1 + realm * 0.1)."""
    return max(1, int(base_cost * (1 + player_realm * 0.1)))


# ─── NPC Generation ────────────────────────────────────────────────────────────

_NPC_COUNT = 9


def _generate_dungeon_npc(base_bp: int, floor: int, floor_count: int, difficulty: str, dungeon_emoji: str, lang: str = "en") -> dict:
    """Generate NPC with fixed BP based on dungeon base_bp and difficulty."""
    npc_names = [t(lang, f"dng_npc_{i}") for i in range(1, _NPC_COUNT + 1)]

    cfg = DIFF_CONFIG[difficulty]
    lo, hi = cfg["bp_lo"], cfg["bp_hi"]
    progress = (floor - 1) / max(floor_count - 1, 1)
    scale = lo + progress * (hi - lo)
    npc_bp = max(10, int(base_bp * scale * random.uniform(0.95, 1.05)))
    npc_hp = max(1.0, npc_bp * HP_PER_BP * random.uniform(0.90, 1.10))

    # BUGFIX 2026-06-02 (v16.7) — the shared damage core (core/combat_model) reads
    # a fighter's 'combat_profile'. Without one, _profile_of() fell back to
    # realm=0 with no stats, so the dungeon NPC's STRIKE lost the realm_mult the
    # PLAYER's profile applies → trash floors became one-shots (matched players)
    # or instant death (under-levelled). dungeon base_bp is already on the
    # realm-scaled power scale (matches the player's realm-scaled STRIKE), so we
    # build the profile at realm=0 from npc_bp as the raw kinetic base and
    # PRESERVE the tuned dungeon HP (npc_hp) via the eff_hp override.
    from core import combat_model as _cm
    prof = _cm.make_profile(
        soul=npc_bp * 0.5, qi=npc_bp * 0.3, bp=float(npc_bp), realm=0,
        perception=npc_bp * 0.05,
    )
    prof["eff_hp"] = npc_hp

    return {
        "telegram_id": 0,
        "name": f"{dungeon_emoji} {random.choice(npc_names)}",
        "bp": npc_bp,
        "hp": npc_hp,
        "armor_bonus": 0.0,
        "realm": 0,
        "sub_layer": 1,
        "techniques": [],
        "pet_ability": None,
        "combat_profile": prof,
    }


# ─── Loot helpers ──────────────────────────────────────────────────────────────

def _filter_drops_by_difficulty(entries: list, difficulty: str) -> list:
    """Drop drop-table entries whose `min_difficulty` exceeds the run's
    difficulty. v14.4 D-1c: lets us gate Eternal Spring Petal (herb 13)
    to Nightmare runs only without splitting the herbs list per dungeon.
    Entries without `min_difficulty` always pass through."""
    cur = DIFF_ORDER.get(difficulty, 1)
    return [
        e for e in entries
        if DIFF_ORDER.get(e.get("min_difficulty", "easy"), 1) <= cur
    ]


def _qi_recovery_pill(min_realm: int) -> int:
    """D4 (v16.6): the Qi-recovery pill a dungeon of this grade drops.

    Mortal-grade dungeons (min_realm 0-1) drop Qi Amass (id 6, +30 Qi); Spirit-
    grade and above drop the Heavenly Qi Restoration pill (id 7, +80 Qi). This
    mirrors the already-tiered HEALING pills and offsets the realm-scaled Qi cost
    of clearing deeper dungeons (the recovery used to be a flat +30 everywhere).
    """
    return 7 if int(min_realm or 0) >= 2 else 6


def _roll_floor_loot(drops: dict, difficulty: str = "easy", min_realm: int = 0) -> dict:
    """Roll loot for a single floor victory.

    `difficulty` (default "easy") is used to filter drop-table entries
    that carry a `min_difficulty` field — see _filter_drops_by_difficulty.
    Defaulting to "easy" keeps existing callers backwards-compatible.

    `min_realm` (default 0) is the dungeon's grade gate — used to tier the
    Qi-recovery pill drop (D4) and to give higher-grade dungeons a small Qi-pill
    drop-chance bonus. Default 0 keeps any un-updated caller on the +30 pill.
    """
    bag: dict = {}

    # Spirit stones
    stones_cfg = drops.get("stones", {})
    stones = random.randint(stones_cfg.get("min", 10), stones_cfg.get("max", 50))
    bag["stones"] = bag.get("stones", 0) + stones

    # Herbs — pick 0-2
    herbs = _filter_drops_by_difficulty(drops.get("herbs", []), difficulty)
    if herbs:
        count = random.randint(0, 2)
        for _ in range(count):
            chosen = random.choices(herbs, weights=[h["weight"] for h in herbs], k=1)[0]
            herb_id = str(chosen["id"])
            bag.setdefault("herbs", {})
            bag["herbs"][herb_id] = bag["herbs"].get(herb_id, 0) + 1

    # Ores — pick 0-1
    ores = _filter_drops_by_difficulty(drops.get("ores", []), difficulty)
    if ores:
        count = random.randint(0, 1)
        for _ in range(count):
            chosen = random.choices(ores, weights=[o["weight"] for o in ores], k=1)[0]
            ore_id = str(chosen["id"])
            bag.setdefault("ores", {})
            bag["ores"][ore_id] = bag["ores"].get(ore_id, 0) + 1

    # Qi pill — D4 (v16.6): tier by dungeon grade; high grades drop it a touch
    # more often to offset their realm-scaled Qi cost. `qi_pill_id` is a tier
    # MARKER (not a quantity) — _merge_bag / _lose_90_percent special-case it.
    qi_chance = drops.get("qi_pill_chance", 0) + (0.04 if int(min_realm or 0) >= 5 else 0.0)
    if random.random() < qi_chance:
        bag["qi_pills"] = bag.get("qi_pills", 0) + 1
        bag["qi_pill_id"] = _qi_recovery_pill(min_realm)

    # Technique scroll — TEC-2: o corte mora AQUI, no único random() de
    # pergaminho de expedição. Este helper é o chokepoint de TODAS as
    # superfícies (masmorra do chat, varredura, sweep multi do mini-app e o
    # chefe em pve_duel_settle), portanto UM multiplicador corta o faucet
    # inteiro. Flag OFF ⇒ scroll_drop_mult() == 1.0 (identidade exata).
    from core.scroll_economy_engine import scroll_drop_mult
    if random.random() < drops.get("scroll_chance", 0) * scroll_drop_mult():
        bag["scrolls"] = bag.get("scrolls", 0) + 1

    # Dao fragment
    if random.random() < drops.get("dao_fragment_chance", 0):
        bag["dao_fragments"] = bag.get("dao_fragments", 0) + 1

    # Healing pills
    pills = drops.get("pills", [])
    if pills and random.random() < drops.get("pill_chance", 0):
        chosen = random.choices(pills, weights=[p["weight"] for p in pills], k=1)[0]
        pill_id = str(chosen["id"])
        bag.setdefault("healing_pills", {})
        bag["healing_pills"][pill_id] = bag["healing_pills"].get(pill_id, 0) + 1

    return bag


def _merge_bag(existing: dict, new_loot: dict) -> dict:
    """Merge new loot into the expedition bag."""
    result = dict(existing)
    for key, val in new_loot.items():
        if key in ("herbs", "ores", "healing_pills") and isinstance(val, dict):
            result.setdefault(key, {})
            for item_id, qty in val.items():
                result[key][item_id] = result[key].get(item_id, 0) + qty
        elif key == "qi_pill_id":
            # D4: tier marker, not a quantity — overwrite (same dungeon → same id).
            result[key] = val
        elif isinstance(val, (int, float)):
            result[key] = result.get(key, 0) + val
        else:
            # Non-numeric values (e.g. recipe_pill_name) — just overwrite
            result[key] = val
    return result


def _lose_90_percent(bag: dict) -> dict:
    """Reduce all loot in bag by 90% (death penalty)."""
    result = {}
    for key, val in bag.items():
        if key in ("herbs", "ores", "healing_pills") and isinstance(val, dict):
            result[key] = {}
            for item_id, qty in val.items():
                kept = max(0, qty // 10)
                if kept:
                    result[key][item_id] = kept
        elif key == "qi_pill_id":
            # D4: tier marker — carry verbatim so any surviving qi_pills grant the
            # right tier (it is NOT a quantity; never reduce or drop it).
            result[key] = val
        elif isinstance(val, (int, float)):
            kept = max(0, int(val * 0.10))
            if kept:
                result[key] = kept
        # Non-numeric values (recipe_pill_name etc.) are lost on death
    return result


async def _load_item_names(session) -> tuple[dict, dict]:
    """Return (herb_names, ore_names) as {id: 'emoji name'} dicts."""
    herbs = (await session.execute(select(HerbCatalog))).scalars().all()
    ores = (await session.execute(select(OreCatalog))).scalars().all()
    herb_names = {str(h.id): f"{h.emoji} {h.name}" for h in herbs}
    ore_names = {str(o.id): f"{o.emoji} {o.name}" for o in ores}
    return herb_names, ore_names


def _format_loot(bag: dict, lang: str, herb_names: dict = None, ore_names: dict = None) -> str:
    lines = []
    if bag.get("stones"):
        lines.append(f"  {t(lang, 'dng_loot_stones', amount=format_number(bag['stones']))}")
    for herb_id, qty in bag.get("herbs", {}).items():
        label = herb_names.get(herb_id, f"Herb #{herb_id}") if herb_names else f"Herb #{herb_id}"
        lines.append(f"  🌿 {label}: *+{qty}*")
    for ore_id, qty in bag.get("ores", {}).items():
        label = ore_names.get(ore_id, f"Ore #{ore_id}") if ore_names else f"Ore #{ore_id}"
        lines.append(f"  {label}: *+{qty}*")
    if bag.get("qi_pills"):
        lines.append(f"  {t(lang, 'dng_loot_qi_pill', amount=bag['qi_pills'])}")
    if bag.get("scrolls"):
        lines.append(f"  {t(lang, 'dng_loot_scroll', amount=bag['scrolls'])}")
    if bag.get("dao_fragments"):
        lines.append(f"  {t(lang, 'dng_loot_dao_fragment', amount=bag['dao_fragments'])}")
    for pill_id, qty in bag.get("healing_pills", {}).items():
        lines.append(f"  ❤️ {t(lang, 'dng_loot_healing_pill', pill_id=pill_id, amount=qty)}")
    if bag.get("recipe_pill_id"):
        pill_name = bag.get("recipe_pill_name", f"Recipe #{bag['recipe_pill_id']}")
        lines.append(f"  📜 {t(lang, 'dng_loot_recipe', pill_name=pill_name)}")
    return "\n".join(lines) if lines else t(lang, "dng_bag_empty")


async def _transfer_bag_to_inventory(session, player: Player, bag: dict):
    """Move all items in the expedition bag into the player's permanent inventory."""
    if bag.get("stones"):
        player.spirit_stones += bag["stones"]

    if bag.get("qi_pills"):
        qty = bag["qi_pills"]
        # D4: grant the tiered Qi pill the dungeon dropped. int-fallback to id 6
        # (+30) for legacy bags rolled before the tier marker existed. Clamp to the
        # only valid tiers {6,7} — defense-in-depth so a marker that slipped past a
        # loot-multiplier loop (or a bag persisted mid-event) can never mint a
        # different, more valuable pill.
        qi_pill_id = int(bag.get("qi_pill_id", 6) or 6)
        if qi_pill_id not in (6, 7):
            qi_pill_id = 6
        await add_item_to_inventory(session, player.telegram_id, "pill", qi_pill_id, qty)

    for pill_id_str, qty in bag.get("healing_pills", {}).items():
        pill_id = int(pill_id_str)
        await add_item_to_inventory(session, player.telegram_id, "pill", pill_id, qty)

    total_herbs = 0
    for herb_id_str, qty in bag.get("herbs", {}).items():
        herb_id = int(herb_id_str)
        await add_item_to_inventory(session, player.telegram_id, "herb", herb_id, qty)
        total_herbs += qty
    if total_herbs > 0:
        from core.faction_engine import update_quest_progress as fac_quest_progress
        await fac_quest_progress(session, player.telegram_id, "gather_herb", total_herbs)

    total_ores = 0
    valid_ore_ids = set((await session.execute(select(OreCatalog.id))).scalars().all())
    for ore_id_str, qty in bag.get("ores", {}).items():
        ore_id = int(ore_id_str)
        if ore_id not in valid_ore_ids:
            logger.warning("Skipping invalid ore_id=%d from expedition bag", ore_id)
            continue
        stmt = select(PlayerOre).where(and_(
            PlayerOre.player_id == player.telegram_id,
            PlayerOre.ore_id == ore_id,
        ))
        ore_row = (await session.execute(stmt)).scalar_one_or_none()
        if ore_row:
            ore_row.quantity += qty
        else:
            session.add(PlayerOre(player_id=player.telegram_id, ore_id=ore_id, quantity=qty))
        total_ores += qty
    if total_ores > 0:
        from core.faction_engine import update_quest_progress as fac_quest_progress
        await fac_quest_progress(session, player.telegram_id, "gather_ore", total_ores)

    if bag.get("scrolls", 0) > 0:
        # Build realm-appropriate scroll pool: prefer techniques player doesn't know yet.
        # v16.4c — EXCLUDE house signature arts (sect_key set): they are Library-only
        # (learned via rank, no scroll) and must never enter the live drop economy
        # (Lei §5 — the "Library = primary source" switch is the wipe's job).
        all_techs = (await session.execute(
            select(TechniqueCatalog).where(
                TechniqueCatalog.req_realm <= player.realm,
                TechniqueCatalog.sect_key.is_(None),
            )
        )).scalars().all()
        known_ids = set((await session.execute(
            select(PlayerTechnique.technique_id).where(PlayerTechnique.player_id == player.telegram_id)
        )).scalars().all())
        owned_scroll_ids = set((await session.execute(
            select(PlayerInventory.item_id).where(
                PlayerInventory.player_id == player.telegram_id,
                PlayerInventory.item_type == "technique_scroll",
                PlayerInventory.quantity > 0,
            )
        )).scalars().all())
        # Priority 1: not known and no scroll yet; Priority 2: not known; Priority 3: any realm-valid
        p1 = [tech for tech in all_techs if tech.id not in known_ids and tech.id not in owned_scroll_ids]
        p2 = [tech for tech in all_techs if tech.id not in known_ids]
        scroll_pool = p1 or p2 or list(all_techs)

        for _ in range(bag["scrolls"]):
            chosen = random.choice(scroll_pool)
            await add_item_to_inventory(session, player.telegram_id, "technique_scroll", chosen.id)

    if bag.get("dao_fragments"):
        from database.models import DaoLawCatalog, PlayerDaoFragment
        dao_laws = (await session.execute(select(DaoLawCatalog))).scalars().all()
        if dao_laws:
            for _ in range(bag["dao_fragments"]):
                law = random.choice(dao_laws)
                stmt = select(PlayerDaoFragment).where(and_(
                    PlayerDaoFragment.player_id == player.telegram_id,
                    PlayerDaoFragment.dao_law_id == law.id,
                ))
                frag = (await session.execute(stmt)).scalar_one_or_none()
                if frag and not frag.is_completed:
                    frag.fragments_count = min(frag.fragments_count + 1, law.total_fragments)
                    if frag.fragments_count >= law.total_fragments:
                        frag.is_completed = True
                elif not frag:
                    session.add(PlayerDaoFragment(
                        player_id=player.telegram_id,
                        dao_law_id=law.id,
                        fragments_count=1,
                        is_completed=False,
                    ))


# ─── Keyboards ─────────────────────────────────────────────────────────────────

def _dungeon_list_keyboard(dungeons: list[DungeonCatalog], player_realm: int, lang: str, page: int = 1, total_pages: int = 1, cat_min: int = 0) -> InlineKeyboardMarkup:
    rows = []
    for d in dungeons:
        if d.min_realm <= player_realm <= d.max_realm:
            label = f"{d.emoji} {d.name}"
        else:
            label = f"🔒 {d.name} ({t(lang, 'realm', fallback='Realm')} {d.min_realm}+)"
        rows.append([InlineKeyboardButton(label, callback_data=f"dng_view_{d.id}")])
        
    if total_pages > 1:
        # Custom pagination since we need to pass cat_min
        pag_row = []
        if page > 1:
            pag_row.append(InlineKeyboardButton(f"⬅️ {t(lang, 'btn_previous', fallback='Prev')}", callback_data=f"dng_page_{page - 1}_{cat_min}"))
        else:
            pag_row.append(InlineKeyboardButton(" ", callback_data="noop"))
            
        pag_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        
        if page < total_pages:
            pag_row.append(InlineKeyboardButton(f"{t(lang, 'btn_next', fallback='Next')} ➡️", callback_data=f"dng_page_{page + 1}_{cat_min}"))
        else:
            pag_row.append(InlineKeyboardButton(" ", callback_data="noop"))
            
        rows.append(pag_row)
        
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="dng_list")])
    return InlineKeyboardMarkup(rows)


def _difficulty_picker_keyboard(dungeon: DungeonCatalog, best_diff: int, lang: str, prefix: str = "dng_diff") -> InlineKeyboardMarkup:
    """Build difficulty selection buttons. Locks difficulties not yet unlocked."""
    rows = []
    for diff in DIFFICULTIES:
        cfg = DIFF_CONFIG[diff]
        diff_level = DIFF_ORDER[diff]
        floors = _get_floor_count(dungeon, diff)
        loot_label = f"{cfg['loot_mult']}x"

        if diff_level == 1 or best_diff >= diff_level - 1:
            # Unlocked
            label = f"{cfg['emoji']} {t(lang, f'dng_diff_{diff}')} — {floors}F | {loot_label}"
            rows.append([InlineKeyboardButton(label, callback_data=f"{prefix}_{dungeon.id}_{diff}")])
        else:
            # Locked — need to complete previous difficulty
            prev_diff = DIFFICULTIES[diff_level - 2]
            label = f"🔒 {t(lang, f'dng_diff_{diff}')} — {t(lang, 'dng_diff_locked', req=t(lang, f'dng_diff_{prev_diff}'))}"
            rows.append([InlineKeyboardButton(label, callback_data="noop")])

    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_view_{dungeon.id}")])
    return InlineKeyboardMarkup(rows)


def _dungeon_view_keyboard(dungeon: DungeonCatalog, pd: PlayerDungeon | None, player_realm: int, lang: str) -> InlineKeyboardMarkup:
    rows = []
    accessible = dungeon.min_realm <= player_realm <= dungeon.max_realm
    if accessible:
        if pd and pd.current_floor > 0:
            rows.append([InlineKeyboardButton(t(lang, "dng_btn_advance"), callback_data=f"dng_advance_{dungeon.id}")])
            rows.append([InlineKeyboardButton(t(lang, "dng_btn_retreat"), callback_data=f"dng_retreat_{dungeon.id}")])
        else:
            rows.append([InlineKeyboardButton(t(lang, "dng_btn_enter"), callback_data=f"dng_enter_{dungeon.id}")])
        if pd and pd.completed:
            rows.append([InlineKeyboardButton(t(lang, "dng_sweep_button"), callback_data=f"dng_sweep_{dungeon.id}")])
        if pd and pd.expedition_bag:
            rows.append([InlineKeyboardButton(t(lang, "dng_btn_bag"), callback_data=f"dng_bag_{dungeon.id}")])
        rows.append([InlineKeyboardButton(t(lang, "dng_quest_btn"), callback_data=f"dng_qlist_{dungeon.id}")])
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="dng_list")])
    return InlineKeyboardMarkup(rows)


def _after_fight_keyboard(dungeon_id: int, won: bool, lang: str, auto_progress: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if won:
        rows.append([
            InlineKeyboardButton(t(lang, "dng_btn_advance"), callback_data=f"dng_advance_{dungeon_id}"),
            InlineKeyboardButton(t(lang, "dng_btn_retreat"), callback_data=f"dng_retreat_{dungeon_id}"),
        ])
        # v14.5 Q-1: opt-in auto-progress button. Only rendered when the
        # player flipped the /conf toggle on, to keep the UI uncluttered for
        # the manual majority.
        if auto_progress:
            rows.append([InlineKeyboardButton(t(lang, "dng_btn_auto_advance"), callback_data=f"dng_auto_advance_{dungeon_id}")])
        rows.append([InlineKeyboardButton(t(lang, "dng_btn_bag"), callback_data=f"dng_bag_{dungeon_id}")])
    else:
        rows.append([InlineKeyboardButton(t(lang, "dng_btn_list"), callback_data="dng_list")])
    return InlineKeyboardMarkup(rows)


# ─── Core Fight Logic ──────────────────────────────────────────────────────────

async def _do_dungeon_floor(session, player: Player, dungeon: DungeonCatalog, target_floor: int, difficulty: str, lang: str, stance: str = "balanced", focus_tech_id: int = 0) -> tuple[bool, str, dict]:
    """
    Attempt a floor fight. Returns (won, narration_text, loot).
    Handles Qi cost, combat simulation, and bag updates.

    v15.1.4 — BOSS FLOOR HINT: the last floor of any dungeon is now a
    turn-based boss duel only available in the mini-app. Chat-side
    callers get a non-fatal "won=False, hint narration" return so the
    keyboard surfaces "abre o mini-app". The chat boss floor never
    resolves via simulate_combat (lei §1 — player not stuck: they have
    a path, just not in chat). Trash floors (1..floor_count-1) remain
    100% legacy auto-resolve.
    """
    floor_count = _get_floor_count(dungeon, difficulty)

    # Boss floor (last floor) — chat-side cannot run turn-based; defer.
    if target_floor == floor_count:
        return False, t(lang, "dng_boss_floor_chat_hint"), {"boss_floor": True}

    # Qi check — scale cost by player realm
    qi_cost = _effective_qi_cost(dungeon.qi_cost_per_floor, player.realm)
    if player.qi < qi_cost:
        return False, t(lang, "dng_no_qi", current=int(player.qi), cost=qi_cost), {}

    # Deduct Qi
    player.qi = max(0.0, player.qi - qi_cost)

    # Build player fighter
    equipped_stmt = select(PlayerArtifact).where(
        PlayerArtifact.player_id == player.telegram_id,
        PlayerArtifact.is_equipped == True,
    )
    equipped = (await session.execute(equipped_stmt)).scalars().all()

    active_tech_stmt = (
        select(PlayerTechnique, TechniqueCatalog)
        .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
        .where(
            PlayerTechnique.player_id == player.telegram_id,
            PlayerTechnique.is_active_combat == True,
        )
    )
    active_tech_rows = (await session.execute(active_tech_stmt)).all()

    class _Tech:
        pass

    active_techs = []
    for pt, tc in active_tech_rows:
        obj = _Tech()
        obj.technique_id = tc.id
        obj.effect_type = tc.effect_type
        obj.effect_value = tc.effect_value
        obj.effect_round = tc.effect_round
        # 名-CRU: mesmo motivo do `core/combat_engine.py` — o nome entra no
        # `combat_log.rounds_data` persistido, como string ja' composta e sem id.
        obj.name = tc.name
        obj.emoji = tc.emoji
        obj.mastery_level = pt.mastery_level
        obj.intent_affinity = getattr(tc, "intent_affinity", None)  # D3 (v16.6)
        active_techs.append(obj)

    from core.combat_engine import get_combat_buff_mults
    buff_mults = await get_combat_buff_mults(session, player.telegram_id)
    from core.faction_engine import get_faction_bonuses
    fac_bonuses = await get_faction_bonuses(session, player.telegram_id)
    # v16.7 follow-up (combat audit 2026-06-09) — this floor was the LAST player
    # combat path still building the fighter WITHOUT dao_bonuses/companion_bonus,
    # so a player's Dao Laws (the v16.7 apex multiplier) and companion contributed
    # ZERO on dungeon trash floors — chat AND mini-app (webserver api_dungeons_
    # enter/advance call this same builder). The v16.7 model routes 100% of the Dao
    # through dao_index, so omitting dao_bonuses dropped the laws entirely here.
    # Mirror handlers/combat.py:_build_fighter. Best-effort: a lookup failure must
    # never break the floor for the 57 live players (Lei §1).
    dao_bonuses = None
    try:
        from core.dao_engine import get_player_dao_bonuses
        dao_bonuses = await get_player_dao_bonuses(session, player.telegram_id, int(player.realm or 0))
    except Exception:
        logger.exception("dungeon floor dao_bonuses fetch failed player=%s", player.telegram_id)
    comp_bonus = None
    pet_ability = None
    try:
        from core.beast_engine import get_companion_beast, get_companion_bonuses, get_pet_combat_ability
        comp_beast, comp_catalog = await get_companion_beast(session, player.telegram_id)
        comp_bonus = get_companion_bonuses(comp_beast, comp_catalog)
        # [jogador] 2026-06-11: pet special ability was never wired anywhere.
        pet_ability = get_pet_combat_ability(comp_catalog, comp_beast,
                                             player.language or "pt")
    except Exception:
        logger.exception("dungeon floor companion fetch failed player=%s", player.telegram_id)
    interior_b = ach_b = None
    try:
        from core.combat_engine import get_unified_combat_bonuses
        interior_b, ach_b = await get_unified_combat_bonuses(session, player.telegram_id)
    except Exception:
        logger.exception("dungeon floor unified bonuses fetch failed player=%s", player.telegram_id)
    fighter = build_fighter_data(player, equipped, active_techs, pet_ability=pet_ability,
                                 buff_mults=buff_mults,
                                 companion_bonus=comp_bonus, dao_bonuses=dao_bonuses,
                                 faction_bonuses=fac_bonuses,
                                 interior_bonuses=interior_b, achievement_bonuses=ach_b)
    # D3 (v16.6): inject Intent ranks so the soul-mastery aura helps clear trash floors too.
    from core.intent_engine import snapshot_intent_ranks
    fighter["intent_ranks"] = await snapshot_intent_ranks(session, player)
    apply_stance_and_focus(fighter, stance, focus_tech_id)

    # Generate NPC with fixed base_bp
    npc = _generate_dungeon_npc(dungeon.base_bp, target_floor, floor_count, difficulty, dungeon.emoji, lang)

    result = simulate_combat(fighter, npc, mode="dungeon")
    won = result["winner"] == "attacker"

    herb_names, ore_names = await _load_item_names(session)

    diff_emoji = DIFF_CONFIG[difficulty]["emoji"]
    # Build narration (compact)
    raw_player_name = player.dao_name or player.display_name or t(lang, "dng_default_name")
    player_name = escape_markdown(raw_player_name)
    npc_name = escape_markdown(npc['name'])
    lines = [
        t(lang, "dng_floor_header", floor=target_floor, total=floor_count, emoji=dungeon.emoji),
        f"{diff_emoji} {t(lang, f'dng_diff_{difficulty}')}",
        f"⚔️ *{player_name}* vs *{npc_name}*",
        t(lang, "dng_bp_display", player_bp=format_number(fighter['bp']), enemy_bp=format_number(npc['bp'])),
        f"——————————————",
    ]

    # Pet strike happens in round 1, which the last-2-rounds window below
    # almost always drops — surface it explicitly ([jogador] 2026-06-11: the
    # ability finally fires; it must be SEEN to be believed). Reuses the
    # existing chat key combat_pet_attack. Defensive: never break the floor.
    try:
        for ev in (result["rounds"][0].get("events") or []):
            if ev.get("type") == "pet_attack" and ev.get("who") == "attacker":
                lines.append(t(lang, "combat_pet_attack", actor=player_name,
                               pet_name=ev["pet_name"],
                               damage=format_number(ev["damage"]),
                               ability=ev["ability"]))
                break
    except Exception:
        pass

    # Show last 2 rounds only to keep message short
    for rnd in result["rounds"][-2:]:
        for ev in rnd["events"]:
            if ev["type"] == "attack":
                actor = player_name if ev["who"] == "attacker" else npc_name
                lines.append(f"  ⚔️ *{actor}*: -{format_number(ev['damage'])} HP")
            elif ev["type"] in ("evasion", "dodge"):
                actor = player_name if ev["who"] == "attacker" else npc_name
                lines.append(f"  💨 *{actor}* evaded!")

    lines.append(f"——————————————")
    lines.append(t(lang, "dng_qi_remaining",
        current=int(player.qi),
        max=int(player.qi_capacity),
        cost=qi_cost))

    loot = {}
    if won:
        loot = _roll_floor_loot(dungeon.drops, difficulty, min_realm=int(dungeon.min_realm or 0))

        # Apply difficulty loot multiplier
        loot = _apply_difficulty_loot_mult(loot, difficulty)

        # Meteor Shower event: double all loot quantities
        from handlers.events import get_event_multipliers
        event_mults = await get_event_multipliers(session)
        loot_mult = event_mults.get("loot_mult", 1.0)
        if loot_mult > 1.0:
            loot_multiplied: dict = {}
            for key, val in loot.items():
                if key in ("herbs", "ores", "healing_pills") and isinstance(val, dict):
                    loot_multiplied[key] = {k: max(1, int(v * loot_mult)) for k, v in val.items()}
                elif key == "qi_pill_id":
                    loot_multiplied[key] = val  # D4: tier marker, never scale it
                elif isinstance(val, (int, float)):
                    loot_multiplied[key] = max(1, int(val * loot_mult))
                else:
                    loot_multiplied[key] = val
            loot = loot_multiplied

        # Fortune Incense buff: +5% extra drop chance (bonus loot)
        from database.models import PlayerBuff
        from datetime import datetime as _dt, timezone as _tz
        _now_fi = _dt.now(_tz.utc)
        _incense = (await session.execute(
            select(PlayerBuff).where(
                PlayerBuff.player_id == player.telegram_id,
                PlayerBuff.buff_type == "fortune_incense",
                PlayerBuff.expires_at > _now_fi
            )
        )).scalar_one_or_none()
        if _incense:
            # Apply bonus: boost stones by 5% and add extra herb/ore roll chance
            loot["stones"] = int(loot.get("stones", 0) * 1.05)
            if random.random() < 0.20:  # 20% extra herb drop per floor
                herbs_cfg = dungeon.drops.get("herbs", [])
                if herbs_cfg:
                    chosen_h = random.choices(herbs_cfg, weights=[h["weight"] for h in herbs_cfg], k=1)[0]
                    loot.setdefault("herbs", {})[str(chosen_h["id"])] = loot.get("herbs", {}).get(str(chosen_h["id"]), 0) + 1

        # Recipe drop chance (8% per floor, T2-T3; hard/nightmare → T4).
        # 2026-07-10 (owner: "ativar as pills de tier 4"): classe N-34 — as 10
        # receitas T4 não caíam em NENHUMA fonte (todo roll era (2,3)). O gate
        # real das T4 são os ingredientes T5 + Grandmaster; a receita visível é
        # o signpost, dificuldade hard+ é a fonte.
        from core.alchemy_engine import roll_recipe_drop
        _rt_max = 4 if difficulty in ("hard", "nightmare") else 3
        recipe_pill_id = await roll_recipe_drop(session, player.telegram_id, (2, _rt_max), 0.08)
        if recipe_pill_id:
            loot["recipe_pill_id"] = recipe_pill_id
            from database.models import PillCatalog
            _pill = await session.get(PillCatalog, recipe_pill_id)
            loot["recipe_pill_name"] = _cname(lang, "pill", _pill) if _pill else f"Recipe #{recipe_pill_id}"

        lines.append(t(lang, "dng_floor_win", floor=target_floor))

        # MV-2 — Tiandao: cada trash floor vencida conta para a Maré de Bestas
        # do continente (gated + fail-safe). UM hook cobre chat E mini-app —
        # api_dungeons_enter/advance chamam este MESMO helper. Progresso
        # antes→depois na narração (Lei da progressão visível).
        try:
            from core.tiandao_engine import record_pve_victory
            _wev = await record_pve_victory(session, player)
            if _wev:
                lines.append(t(lang, "wev_tide_progress", before=_wev["before"],
                               progress=_wev["progress"], goal=_wev["goal"]))
        except Exception:
            logger.debug("tiandao dungeon hook failed", exc_info=True)

        loot_text = _format_loot(loot, lang, herb_names, ore_names)
        if loot_text:
            lines.append(t(lang, "dng_loot_this_floor"))
            lines.append(loot_text)
        if loot_mult > 1.0:
            lines.append(f"☄️ _{t(lang, 'event_meteor_shower_bonus')}_")
    else:
        lines.append(t(lang, "dng_floor_lose", floor=target_floor))

    # Apply persistent HP drain (scaled by dungeon difficulty)
    atk_dmg_taken = result.get("attacker_damage_taken", 0)
    drain = DUNGEON_HP_DRAIN.get(difficulty, 0.50)
    # BUGFIX 2026-07-26: reconcile effective combat-pool damage → raw current_hp.
    hp_lost = apply_hp_drain_scaled(player, atk_dmg_taken, result.get("attacker_max_hp"), drain_pct=drain)
    # Onda B — floor-result HP shown == the arena/profile (Alma-routed).
    from core.cultivator_soul import soul_max_hp, soul_current_hp
    max_hp_val = await soul_max_hp(session, player)
    cur_hp = soul_current_hp(player, max_hp_val)
    hp_pct = int(cur_hp / max_hp_val * 100) if max_hp_val > 0 else 0
    lines.append(f"\n❤️ HP: {format_number(cur_hp)} / {format_number(max_hp_val)} ({hp_pct}%)")
    if hp_lost > 0:
        lines.append(f"  (-{format_number(hp_lost)})")
    if cur_hp <= 0:
        lines.append(f"⚠️ {t(lang, 'hp_depleted_warning')}")

    narration = "\n".join(lines)
    return won, narration, loot


# ─── Handler Functions ─────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def dungeons_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point — show dungeon categories (Realms) or paginated dungeons within a category."""
    query = update.callback_query
    user = update.effective_user

    page = 1
    cat_min = None
    if query and query.data:
        if query.data.startswith("dng_page_"):
            parts = query.data.split("_")
            page = int(parts[2])
            if len(parts) > 3:
                cat_min = int(parts[3])
        elif query.data.startswith("dng_cat_"):
            cat_min = int(query.data.split("_")[2])

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            if query:
                await safe_answer(query, t(normalize_lang(update.effective_user.language_code), "not_registered"), show_alert=True)
            return

        lang = player.language or "en"
        
        # CATEGORY SELECTION MODE
        if cat_min is None:
            text = t(lang, "dng_list_title", fallback="🏔️ *Dungeons List*\n")
            text += "\n_" + t(lang, "dng_select_category_desc", fallback="Select a realm category to view available dungeons.") + "_\n"
            
            kb_rows = [
                # Realm 0-2
                [InlineKeyboardButton("🪨 Mortal Realms (0-2)", callback_data="dng_cat_0")],
                # Realm 3-5
                [InlineKeyboardButton("☁️ Spirit Realms (3-5)", callback_data="dng_cat_3")],
                # Realm 6-8
                [InlineKeyboardButton("🌌 Celestial Realms (6-8)", callback_data="dng_cat_6")],
                # Realm 9-10
                [InlineKeyboardButton("⚡ Immortal Realms (9-10)", callback_data="dng_cat_9")],
                [InlineKeyboardButton(t(lang, "nav_main", fallback="🔙 Back to Main"), callback_data="nav_combate")]
            ]
            kb = InlineKeyboardMarkup(kb_rows)
            
            if query:
                await safe_answer(query)
                import logging
                logger = logging.getLogger(__name__)
                try:
                    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"[DEBUG DUNGEONS] editMessageText failed on Selection Category: {repr(e)}\nTEXT WAS: {repr(text)}")
                    raise
            else:
                await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")
            return

        # CATEGORY CONTENT MODE
        # Define ranges
        if cat_min == 0: cat_max = 2
        elif cat_min == 3: cat_max = 5
        elif cat_min == 6: cat_max = 8
        else: cat_max = 10

        stmt = select(DungeonCatalog).where(
            and_(
                DungeonCatalog.min_realm >= cat_min,
                DungeonCatalog.min_realm <= cat_max
            )
        ).order_by(DungeonCatalog.id)
        cat_dungeons = (await session.execute(stmt)).scalars().all()

        # MV-1: com `dungeons_regionais` ON, Portais mostra só os portais do
        # continente atual (+ os não-ancorados). OFF → lista global de hoje.
        from core.dungeon_regions import dungeon_visible_here, elsewhere_summary
        _dng_elsewhere = elsewhere_summary(cat_dungeons, player)
        cat_dungeons = [d for d in cat_dungeons if dungeon_visible_here(d, player)]

        total_pages = max(1, (len(cat_dungeons) + DUNGEONS_PER_PAGE - 1) // DUNGEONS_PER_PAGE)
        page = max(1, min(page, total_pages))
        start = (page - 1) * DUNGEONS_PER_PAGE
        page_dungeons = cat_dungeons[start:start + DUNGEONS_PER_PAGE]

        from config import REALM_NAMES
        min_name = REALM_NAMES[cat_min] if cat_min < len(REALM_NAMES) else f"R{cat_min}"
        max_name = REALM_NAMES[cat_max] if cat_max < len(REALM_NAMES) else f"R{cat_max}"
        
        text = f"🏔️ *{min_name} — {max_name}*\n\n"
        
        if not page_dungeons:
            # QoL 09/08 Item D (report [jogador]) — "nenhum portal descoberto" MENTIA
            # quando a lista local está vazia só por geografia: os portais
            # existem, são desta faixa de reinos, e estão do outro lado do mar —
            # o bloco "Além do horizonte" logo abaixo prova-o. A frase culpava o
            # reino quando a culpa é do lugar (Lei §1).
            if _dng_elsewhere:
                _empty = t(lang, "dng_empty_here_elsewhere",
                           fallback="No portal of this realm range opens on this continent.")
            else:
                _empty = t(lang, "dng_empty_category",
                           fallback="No dungeons discovered in this realm yet.")
            text += "_" + _empty + "_"
        else:
            for d in page_dungeons:
                accessible = d.min_realm <= player.realm <= d.max_realm
                status = "✅" if accessible else "🔒"
                qi_shown = _effective_qi_cost(d.qi_cost_per_floor, player.realm) if accessible else d.qi_cost_per_floor
                text += f"{d.emoji} *{escape_markdown(d.name)}* {status}"
                text += f"\n   ⚔️ BP {format_number(d.base_bp)} | 🏰 {d.floor_count}F | ⚡ {qi_shown} Qi\n\n"

        kb = _dungeon_list_keyboard(page_dungeons, player.realm, lang, page, total_pages, cat_min)

        # MV-1 Lei §1 — disclosure, não void: o que existe além do horizonte.
        if _dng_elsewhere:
            text += "\n" + t(lang, "dng_elsewhere_header") + "\n"
            for ew in _dng_elsewhere:
                cname = t(lang, f"continent_{ew['continent']}")
                text += t(lang, "dng_elsewhere_line", emoji=ew["emoji"], name=cname, n=ew["count"]) + "\n"
                # MV-9 §P6 — os portais por NOME (o apagador do MV-1). A
                # contagem sozinha não deixa ninguém decidir se vale a estrada.
                for _p in (ew.get("portals") or []):
                    text += f"   {_p['emoji']} {_p['name']}\n"
            rows = [list(r) for r in kb.inline_keyboard]
            rows.insert(len(rows) - 1, [InlineKeyboardButton(t(lang, "dng_btn_travel"), callback_data="cmd_viajar")])
            kb = InlineKeyboardMarkup(rows)

        if query:
            await safe_answer(query)
            import logging
            logger = logging.getLogger(__name__)
            try:
                await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"[DEBUG DUNGEONS] editMessageText failed on Content Mode: {repr(e)}\nTEXT WAS: {repr(text)}")
                raise
        else:
            await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


@safe_handler
@rate_limit(1)
async def dungeon_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    dungeon_id = safe_parse_callback_int(query.data, "dng_view_")
    if dungeon_id is None:
        await safe_answer(query)
        return

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"
        dungeon = (await session.execute(select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id))).scalar_one_or_none()
        if not dungeon:
            await safe_answer(query, t(lang, "dng_not_found"), show_alert=True)
            return

        pd = (await session.execute(
            select(PlayerDungeon).where(and_(
                PlayerDungeon.player_id == player.telegram_id,
                PlayerDungeon.dungeon_id == dungeon_id,
            ))
        )).scalar_one_or_none()

        accessible = dungeon.min_realm <= player.realm <= dungeon.max_realm
        eff_qi_cost = _effective_qi_cost(dungeon.qi_cost_per_floor, player.realm)

        lines = [
            f"{dungeon.emoji} *{escape_markdown(dungeon.name)}*",
            f"_{escape_markdown(dungeon.description)}_",
            "",
            t(lang, "dng_required_realm", min=dungeon.min_realm, max=dungeon.max_realm),
            f"⚔️ Base BP: *{format_number(dungeon.base_bp)}*",
            t(lang, "dng_qi_cost", cost=eff_qi_cost),
            t(lang, "dng_your_qi", current=int(player.qi), max=int(player.qi_capacity)),
        ]
        if eff_qi_cost != dungeon.qi_cost_per_floor:
            lines.append(t(lang, "dng_qi_cost_note", base=dungeon.qi_cost_per_floor))

        # Espólio possível — the chat detail screen had ZERO loot disclosure
        # (the "Espólio possível" surface was mini-app-only, and even there it
        # truncated entries — [jogador] burned 600k qi on the wrong dungeon,
        # 2026-06-12). Iterate the WHOLE drops dict generically so any future
        # drop type is auto-disclosed (Lei §1). Best-effort: a lookup failure
        # must never break the detail screen.
        try:
            drops = dungeon.drops or {}
            d_lines = []
            stones = drops.get("stones") or {}
            if stones.get("max"):
                d_lines.append(f"  🪙 {format_number(int(stones.get('min', 0)))}–{format_number(int(stones.get('max', 0)))} {t(lang, 'dng_drops_per_floor')}")
            herb_ids = [int(m.get("id", 0)) for m in (drops.get("herbs") or [])]
            ore_ids = [int(m.get("id", 0)) for m in (drops.get("ores") or [])]
            pill_ids = [int(m.get("id", 0)) for m in (drops.get("pills") or [])]
            from database.models import HerbCatalog, OreCatalog, PillCatalog
            luts = {}
            for kind, model, ids in (("herbs", HerbCatalog, herb_ids),
                                     ("ores", OreCatalog, ore_ids),
                                     ("pills", PillCatalog, pill_ids)):
                lut = {}
                if ids:
                    for row in (await session.execute(select(model).where(model.id.in_(ids)))).scalars().all():
                        lut[row.id] = f"{getattr(row, 'emoji', '') or ''} {row.name}".strip()
                luts[kind] = lut
            for kind in ("herbs", "ores", "pills"):
                for m in (drops.get(kind) or []):
                    name = luts[kind].get(int(m.get("id", 0)), f"#{m.get('id')}")
                    gate = " 💀" if m.get("min_difficulty") == "nightmare" else ""
                    d_lines.append(f"  {escape_markdown(name)}{gate}")
            qi_pill = float(drops.get("qi_pill_chance", 0) or 0)
            if qi_pill > 0 and int(dungeon.min_realm or 0) >= 5:
                qi_pill = min(1.0, qi_pill + 0.04)  # mirror _roll_floor_loot D4 bonus
            if qi_pill > 0:
                d_lines.append(f"  ⚗️ {t(lang, 'dng_drop_qi_pill')}: {round(qi_pill * 100)}%")
            if float(drops.get("pill_chance", 0) or 0) > 0:
                d_lines.append(f"  💊 {t(lang, 'dng_drop_heal_pill')}: {round(float(drops['pill_chance']) * 100)}%")
            # TEC-2 — a vitrine mostra o número CORTADO (display = roll, lição
            # MV-6). Flag OFF ⇒ mult 1.0 ⇒ o mesmo número de sempre.
            from core.scroll_economy_engine import escassez_on as _scr_on
            from core.scroll_economy_engine import scroll_drop_mult as _scr_mult
            scroll_ch = float(drops.get("scroll_chance", 0) or 0) * _scr_mult()
            if scroll_ch > 0:
                # Sob escassez a taxa fica sub-1%: 1 casa decimal para não virar
                # "0%" (mentira) nem "1%" (arredondamento generoso).
                _pct = scroll_ch * 100
                _shown = f"{_pct:.1f}" if _pct < 1 else f"{round(_pct)}"
                d_lines.append(f"  📜 {t(lang, 'dng_drop_scroll')}: {_shown}%")
                if _scr_on():
                    # Lei §1: só aponta a estrada que EXISTE. Sem a Biblioteca
                    # ligada nesse mundo, a linha diz a escassez sem prometer
                    # uma porta que o jogador não vai encontrar.
                    from core.sect_library_engine import biblioteca_on as _lib_on
                    d_lines.append(
                        f"  _{t(lang, 'scr_dng_scarcity_hint' if _lib_on() else 'scr_dng_scarcity_bare')}_")
            if float(drops.get("dao_fragment_chance", 0) or 0) > 0:
                d_lines.append(f"  💠 {t(lang, 'dng_drop_dao_frag')}: {round(float(drops['dao_fragment_chance']) * 100)}%")
            if d_lines:
                lines.append(f"\n📦 *{t(lang, 'dng_possible_drops_header')}*")
                lines.extend(d_lines)
        except Exception:
            logger.exception("dungeon_view drops disclosure failed (dungeon=%s)", dungeon_id)

        best_diff = pd.best_difficulty if pd else 0
        if best_diff > 0:
            best_name = DIFFICULTIES[best_diff - 1]
            best_emoji = DIFF_CONFIG[best_name]["emoji"]
            lines.append(f"\n🏆 {t(lang, 'dng_best_difficulty', emoji=best_emoji, diff=t(lang, f'dng_diff_{best_name}'))}")

        if pd and pd.current_floor > 0:
            diff_name = pd.difficulty or "normal"
            diff_emoji = DIFF_CONFIG[diff_name]["emoji"]
            fc = _get_floor_count(dungeon, diff_name)
            lines.append(f"\n{diff_emoji} {t(lang, 'dng_in_progress', floor=pd.current_floor)} / {fc}")
            lines.append(t(lang, "dng_can_advance_or_retreat"))

        if not accessible:
            lines.append(f"\n🔒 {t(lang, 'dng_realm_locked', min_realm=dungeon.min_realm)}")

        text = "\n".join(lines)
        kb = _dungeon_view_keyboard(dungeon, pd, player.realm, lang)
        await safe_answer(query)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


def _run_elsewhere_refusal(lang: str, run: dict, *, same: bool = False):
    """QoL-relatos — a recusa de "uma masmorra de cada vez", NUNCA muda (Lei §1).

    Diz o NOME e o ANDAR e oferece a saída (Retirar-se) ali mesmo. Um alerta
    de callback do Telegram não aceita botões, por isso isto devolve
    (texto, teclado) para `edit_message_text` — a mesma forma que o
    `dng_sweep_no_qi` já usa. UM renderizador para os 3 caminhos do chat.
    """
    key = "dng_run_here" if same else "dng_run_elsewhere"
    text = t(lang, key, emoji=run["emoji"], name=escape_markdown(run["name"]),
             floor=run["current_floor"])
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "dng_btn_retreat"),
                              callback_data=f"dng_retreat_{run['dungeon_id']}")],
        [InlineKeyboardButton(t(lang, "dng_btn_go_to_run"),
                              callback_data=f"dng_view_{run['dungeon_id']}")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="dng_list")],
    ])
    return text, kb


@safe_handler
@rate_limit(1)
async def dungeon_enter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show difficulty selection screen before entering dungeon."""
    query = update.callback_query
    user = update.effective_user

    dungeon_id = safe_parse_callback_int(query.data, "dng_enter_")
    if dungeon_id is None:
        await safe_answer(query)
        return

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"
        dungeon = (await session.execute(select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id))).scalar_one_or_none()
        if not dungeon:
            await safe_answer(query)
            return

        if not (dungeon.min_realm <= player.realm <= dungeon.max_realm):
            await safe_answer(query, t(lang, "dng_realm_locked", min_realm=dungeon.min_realm), show_alert=True)
            return

        # MV-1: recusa honesta — o portal fica noutro continente (server-side).
        from core.dungeon_regions import region_gate
        _rg = region_gate(dungeon, player)
        if _rg:
            cname = t(lang, f"continent_{_rg['continent']}")
            await safe_answer(query, t(lang, "dng_wrong_continent", emoji=_rg["continent_emoji"], name=cname), show_alert=True)
            return

        pd = (await session.execute(
            select(PlayerDungeon).where(and_(
                PlayerDungeon.player_id == player.telegram_id,
                PlayerDungeon.dungeon_id == dungeon_id,
            ))
        )).scalar_one_or_none()

        best_diff = pd.best_difficulty if pd else 0

        lines = [
            f"{dungeon.emoji} *{escape_markdown(dungeon.name)}*",
            "",
            t(lang, "dng_pick_difficulty"),
            "",
        ]
        for diff in DIFFICULTIES:
            cfg = DIFF_CONFIG[diff]
            diff_level = DIFF_ORDER[diff]
            floors = _get_floor_count(dungeon, diff)
            bp_lo = int(dungeon.base_bp * cfg["bp_lo"])
            bp_hi = int(dungeon.base_bp * cfg["bp_hi"])
            unlocked = diff_level == 1 or best_diff >= diff_level - 1
            lock = "" if unlocked else "🔒 "
            lines.append(f"{lock}{cfg['emoji']} *{t(lang, f'dng_diff_{diff}')}*")
            lines.append(f"   {t(lang, 'dng_diff_info', floors=floors, bp_lo=format_number(bp_lo), bp_hi=format_number(bp_hi), loot=cfg['loot_mult'])}")

        text = "\n".join(lines)
        kb = _difficulty_picker_keyboard(dungeon, best_diff, lang, prefix="dng_diff")
        await safe_answer(query)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


STANCE_CODE_MAP = {"o": "offensive", "b": "balanced", "d": "defensive"}


@safe_handler
@rate_limit(2)
async def dungeon_start_difficulty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show stance menu after choosing dungeon difficulty."""
    query = update.callback_query

    dungeon_id, difficulty = _parse_diff_callback(query.data, "dng_diff_")
    if dungeon_id is None or difficulty is None:
        await safe_answer(query)
        return

    async with get_session_with_retry() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"
        dungeon = (await session.execute(select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id))).scalar_one_or_none()
        if not dungeon:
            await safe_answer(query)
            return

        # QoL-relatos — recusa CEDO (boa UX): não deixa escolher postura/técnica
        # para só depois levar um "não". O guard duro está no dng_go_ (o
        # botão desta mensagem pode ser tocado dias depois — Telegram guarda
        # teclados para sempre), mas o jogador merece saber já aqui.
        from core.dungeon_run_engine import active_run
        _run = await active_run(session, player.telegram_id, exclude=dungeon_id)
        if _run:
            _txt, _kb = _run_elsewhere_refusal(lang, _run)
            await safe_answer(query)
            await query.edit_message_text(_txt, reply_markup=_kb, parse_mode="Markdown")
            return

    cfg = DIFF_CONFIG[difficulty]
    text = (
        f"{dungeon.emoji} *{dungeon.name}*\n"
        f"{cfg['emoji']} *{t(lang, f'dng_diff_{difficulty}')}*\n\n"
        + t(lang, "stance_choose_title") + "\n\n"
        + t(lang, "stance_offensive_desc") + "\n"
        + t(lang, "stance_balanced_desc") + "\n"
        + t(lang, "stance_defensive_desc")
    )

    buttons = []
    for stance_key, st_data in STANCES.items():
        btn_text = f"{st_data['emoji']} {t(lang, f'stance_{stance_key}')}"
        stance_code = stance_key[0]  # o, b, d
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"dng_st_{dungeon_id}_{difficulty}_{stance_code}")])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_enter_{dungeon_id}")])
    kb = InlineKeyboardMarkup(buttons)
    await safe_answer(query)
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


async def _dng_focus_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show technique focus selection after choosing dungeon stance."""
    query = update.callback_query
    await safe_answer(query)
    # callback: dng_st_{dungeon_id}_{difficulty}_{stance_code}
    raw = query.data.replace("dng_st_", "")
    parts = raw.rsplit("_", 2)
    if len(parts) != 3:
        return
    dungeon_id_str, difficulty, stance_code = parts
    if not dungeon_id_str.isdigit() or stance_code not in STANCE_CODE_MAP:
        return
    dungeon_id = int(dungeon_id_str)
    stance = STANCE_CODE_MAP[stance_code]

    async with get_session_with_retry() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"

        active_tech_stmt = (
            select(PlayerTechnique, TechniqueCatalog)
            .join(TechniqueCatalog, TechniqueCatalog.id == PlayerTechnique.technique_id)
            .where(
                PlayerTechnique.player_id == player.telegram_id,
                PlayerTechnique.is_active_combat == True,
            )
        )
        tech_rows = (await session.execute(active_tech_stmt)).all()

    st_data = STANCES[stance]
    text = (
        f"{st_data['emoji']} *{t(lang, f'stance_{stance}')}*\n\n"
        + t(lang, "focus_choose_title")
    )

    buttons = []
    buttons.append([InlineKeyboardButton(
        f"⚖️ {t(lang, 'focus_none')}",
        callback_data=f"dng_go_{dungeon_id}_{difficulty}_{stance_code}_0"
    )])

    for pt, tc in tech_rows:
        buttons.append([InlineKeyboardButton(
            f"{tc.emoji} {_cname(lang, 'tech', tc)}",
            callback_data=f"dng_go_{dungeon_id}_{difficulty}_{stance_code}_{tc.id}"
        )])

    buttons.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_diff_{dungeon_id}_{difficulty}")])
    kb = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


@safe_handler
@rate_limit(2)
async def _dungeon_start_with_stance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enter dungeon at chosen difficulty with stance/focus — fight floor 1."""
    query = update.callback_query
    user = update.effective_user

    # callback: dng_go_{dungeon_id}_{difficulty}_{stance_code}_{focus_tech_id}
    raw = query.data.replace("dng_go_", "")
    parts = raw.rsplit("_", 3)
    if len(parts) != 4:
        await safe_answer(query)
        return
    dungeon_id_str, difficulty, stance_code, focus_str = parts
    if not dungeon_id_str.isdigit() or stance_code not in STANCE_CODE_MAP:
        await safe_answer(query)
        return
    dungeon_id = int(dungeon_id_str)
    stance = STANCE_CODE_MAP[stance_code]
    focus_tech_id = int(focus_str) if focus_str.isdigit() else 0

    # Store stance/focus in user_data for advance floors
    context.user_data["dng_stance"] = stance
    context.user_data["dng_focus"] = focus_tech_id

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"
        dungeon = (await session.execute(select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id))).scalar_one_or_none()
        if not dungeon:
            await safe_answer(query)
            return

        if get_current_hp(player) <= 0:
            await safe_answer(query, t(lang, "hp_too_low_combat"), show_alert=True)
            return

        if not (dungeon.min_realm <= player.realm <= dungeon.max_realm):
            await safe_answer(query, t(lang, "dng_realm_locked", min_realm=dungeon.min_realm), show_alert=True)
            return

        # MV-1: re-valida o continente no executor real (o picker esconde,
        # o servidor garante).
        from core.dungeon_regions import region_gate
        _rg = region_gate(dungeon, player)
        if _rg:
            cname = t(lang, f"continent_{_rg['continent']}")
            await safe_answer(query, t(lang, "dng_wrong_continent", emoji=_rg["continent_emoji"], name=cname), show_alert=True)
            return

        # QoL-relatos — o guard DURO: este é o executor que cria/mexe a run. O
        # ecrã de dificuldade já recusa, mas um teclado antigo (`dng_go_`)
        # pode ser tocado dias depois e saltar o picker inteiro — a verdade
        # é do servidor. Excluir a própria masmorra mantém intacto o fluxo
        # de retomar a run em curso.
        from core.dungeon_run_engine import active_run
        _run = await active_run(session, player.telegram_id, exclude=dungeon_id)
        if _run:
            _txt, _kb = _run_elsewhere_refusal(lang, _run)
            await safe_answer(query)
            await query.edit_message_text(_txt, reply_markup=_kb, parse_mode="Markdown")
            return

        # Get or create PlayerDungeon row
        pd = (await session.execute(
            select(PlayerDungeon).where(and_(
                PlayerDungeon.player_id == player.telegram_id,
                PlayerDungeon.dungeon_id == dungeon_id,
            ))
        )).scalar_one_or_none()

        if not pd:
            pd = PlayerDungeon(
                player_id=player.telegram_id,
                dungeon_id=dungeon_id,
                current_floor=0,
                max_floor_reached=0,
                expedition_bag={},
                best_difficulty=0,
            )
            session.add(pd)
            await session.flush()

        # Check progression gate
        diff_level = DIFF_ORDER[difficulty]
        if diff_level > 1 and pd.best_difficulty < diff_level - 1:
            prev_diff = DIFFICULTIES[diff_level - 2]
            await safe_answer(query, t(lang, "dng_diff_gate", req=t(lang, f"dng_diff_{prev_diff}")), show_alert=True)
            return

        # Set difficulty for this run
        pd.difficulty = difficulty

        target_floor = 1
        won, narration, loot = await _do_dungeon_floor(session, player, dungeon, target_floor, difficulty, lang, stance, focus_tech_id)

        if "dng_no_qi" in narration:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_view_{dungeon_id}")]])
            await safe_answer(query)
            await query.edit_message_text(narration, reply_markup=kb, parse_mode="Markdown")
            await session.commit()
            return

        dng_ach = []
        if won:
            pd.current_floor = target_floor
            pd.max_floor_reached = max(pd.max_floor_reached, target_floor)
            pd.expedition_bag = _merge_bag(pd.expedition_bag or {}, loot)
            pd.last_attempt_at = datetime.now(timezone.utc)
            await track_quest(session, player.telegram_id, "dungeon_floor", 1)
            
            from core.dungeon_quest_engine import track_dungeon_quest_progress
            completed_quests = await track_dungeon_quest_progress(
                session, player.telegram_id, dungeon_id,
                "floor_win", 1, difficulty, False
            )
            for pq, qcat in completed_quests:
                narration += f"\n\n{t(lang, 'dqst_' + str(qcat.id) + '_complete')}"
                narration += f"\n{t(lang, 'dng_quest_completed_inline')}"
                
            from core.faction_engine import update_quest_progress as fac_quest_progress
            completed_f_quests = await fac_quest_progress(
                session, player.telegram_id, "dungeon",
                target_filter={"dungeon_id": dungeon_id, "floor": target_floor, "difficulty": difficulty}
            )
            for q in completed_f_quests:
                narration += "\n\n" + t(lang, "dng_faction_quest_completed", emoji=q.emoji, name=_cname(lang, "q", q))

            from core.achievement_engine import check_achievements
            dng_ach += await check_achievements(session, player.telegram_id, "dungeon_floors", 1)
            if player.realm == 2:
                from core.golden_core_engine import add_core_essence
                _ce = add_core_essence(player, 3)
                if _ce > 0:
                    narration += "\n" + t(lang, "core_essence_gain", amount=_ce, total=player.core_essence or 0)
        else:
            lost_bag = pd.expedition_bag or {}
            survivors = _lose_90_percent(lost_bag)
            if survivors:
                await _transfer_bag_to_inventory(session, player, survivors)
            pd.current_floor = 0
            pd.expedition_bag = {}
            pd.difficulty = None
            pd.last_attempt_at = datetime.now(timezone.utc)
            if lost_bag:
                narration += f"\n\n{t(lang, 'dng_lost_90_loot')}"

        await session.commit()
        if dng_ach:
            from handlers.achievements import notify_achievements
            await notify_achievements(context, player.telegram_id, dng_ach)

        kb = _after_fight_keyboard(dungeon_id, won, lang, auto_progress=bool(getattr(player, "auto_progress_dungeon", False)))
        await safe_answer(query)
        await query.edit_message_text(narration, reply_markup=kb, parse_mode="Markdown")


@safe_handler
@rate_limit(2)
async def dungeon_advance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Advance to next floor."""
    query = update.callback_query
    user = update.effective_user

    dungeon_id = safe_parse_callback_int(query.data, "dng_advance_")
    if dungeon_id is None:
        await safe_answer(query)
        return

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"

        if get_current_hp(player) <= 0:
            await safe_answer(query, t(lang, "hp_too_low_combat"), show_alert=True)
            return

        dungeon = (await session.execute(select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id))).scalar_one_or_none()
        if not dungeon:
            await safe_answer(query)
            return

        pd = (await session.execute(
            select(PlayerDungeon).where(and_(
                PlayerDungeon.player_id == player.telegram_id,
                PlayerDungeon.dungeon_id == dungeon_id,
            ))
        )).scalar_one_or_none()

        if not pd or pd.current_floor == 0:
            await safe_answer(query, t(lang, "dng_not_in_dungeon"), show_alert=True)
            return

        difficulty = pd.difficulty or "normal"
        floor_count = _get_floor_count(dungeon, difficulty)

        next_floor = pd.current_floor + 1
        if next_floor > floor_count:
            # Dungeon completed at this difficulty!
            # MV-1 §5: roll extra de material nativo (hard/nightmare, gated).
            from core.dungeon_regions import regional_bonus_line, roll_regional_bonus
            _regional = roll_regional_bonus(dungeon, difficulty)
            if _regional:
                pd.expedition_bag = _merge_bag(pd.expedition_bag or {}, _regional["loot"])
            herb_names, ore_names = await _load_item_names(session)
            diff_emoji = DIFF_CONFIG[difficulty]["emoji"]
            text = t(lang, "dng_completed", name=dungeon.name, emoji=dungeon.emoji)
            text += f"\n{diff_emoji} {t(lang, f'dng_diff_{difficulty}')}"
            bag_text = _format_loot(pd.expedition_bag or {}, lang, herb_names, ore_names)
            if bag_text:
                text += f"\n\n{t(lang, 'dng_final_loot')}\n{bag_text}"
            if _regional:
                # QoL 04/08 (report [jogador]) — a linha DIZ o item e a quantidade
                # (o servidor já os tinha; a tela deitava-os fora).
                _trib = await regional_bonus_line(session, _regional, lang)
                if _trib:
                    text += f"\n{_trib}"
            await _transfer_bag_to_inventory(session, player, pd.expedition_bag or {})
            pd.current_floor = 0
            pd.expedition_bag = {}
            # Fix 2026-07-23 (report [jogador]): completar = alcançou o último andar.
            pd.max_floor_reached = max(int(pd.max_floor_reached or 0), int(floor_count))
            pd.completed = True
            diff_level = DIFF_ORDER[difficulty]
            pd.best_difficulty = max(pd.best_difficulty, diff_level)
            pd.difficulty = None
            pd.last_attempt_at = datetime.now(timezone.utc)
            _inv_cache(player.telegram_id)
            # Check abyssal achievement (dungeon id 4 = Abyssal Rift)
            if dungeon_id == 4:
                from core.achievement_engine import check_achievements
                abyssal_ach = await check_achievements(session, player.telegram_id, "dungeon_abyssal", 1)
            else:
                abyssal_ach = []
            from core.bp_engine import update_bp_mission
            await update_bp_mission(session, player.telegram_id, "complete_dungeon")
            from core.body_tempering_engine import add_tempering_progress
            tempering_base = max(10, floor_count * 3)
            tempering_diff_mult = DIFF_CONFIG[difficulty]["loot_mult"]
            add_tempering_progress(player, int(tempering_base * tempering_diff_mult))
            from core.faction_engine import update_quest_progress as fac_quest_progress
            await fac_quest_progress(session, player.telegram_id, "dungeon_any")
            await fac_quest_progress(session, player.telegram_id, "dungeon", target_filter={"dungeon_id": dungeon_id, "floor": floor_count, "difficulty": difficulty})
            
            from core.dungeon_quest_engine import track_dungeon_quest_progress
            completed_quests = await track_dungeon_quest_progress(
                session, player.telegram_id, dungeon_id,
                "dungeon_complete", floor_count, difficulty, True
            )
            for pq, qcat in completed_quests:
                text += f"\n\n{t(lang, 'dqst_' + str(qcat.id) + '_complete')}"
                text += f"\n{t(lang, 'dng_quest_completed_inline')}"

            await session.commit()
            if abyssal_ach:
                from handlers.achievements import notify_achievements
                await notify_achievements(context, player.telegram_id, abyssal_ach)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "dng_btn_list"), callback_data="dng_list")]])
            await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
            return

        adv_stance = context.user_data.get("dng_stance", "balanced")
        adv_focus = context.user_data.get("dng_focus", 0)
        won, narration, loot = await _do_dungeon_floor(session, player, dungeon, next_floor, difficulty, lang, adv_stance, adv_focus)

        # v15.1.4 — Boss floor short-circuit. Chat advance can't run the
        # turn-based duel; surface the redirect hint + retreat option so
        # the player isn't stuck (lei §1). NO bag loss, NO floor reset —
        # the run stays intact at floor (floor_count-1) waiting for the
        # boss attempt via the mini-app.
        if isinstance(loot, dict) and loot.get("boss_floor"):
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(t(lang, "dng_btn_retreat"), callback_data=f"dng_retreat_{dungeon_id}"),
                InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_view_{dungeon_id}"),
            ]])
            await query.edit_message_text(narration, reply_markup=kb, parse_mode="Markdown")
            await session.commit()
            return

        if "dng_no_qi" in narration:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(t(lang, "dng_btn_retreat"), callback_data=f"dng_retreat_{dungeon_id}"),
                InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_view_{dungeon_id}"),
            ]])
            await query.edit_message_text(narration, reply_markup=kb, parse_mode="Markdown")
            await session.commit()
            return

        adv_ach = []
        if won:
            pd.current_floor = next_floor
            pd.max_floor_reached = max(pd.max_floor_reached, next_floor)
            pd.expedition_bag = _merge_bag(pd.expedition_bag or {}, loot)
            pd.last_attempt_at = datetime.now(timezone.utc)
            await track_quest(session, player.telegram_id, "dungeon_floor", 1)
            
            from core.dungeon_quest_engine import track_dungeon_quest_progress
            completed_quests = await track_dungeon_quest_progress(
                session, player.telegram_id, dungeon_id, 
                "floor_win", next_floor, difficulty, False
            )
            for pq, qcat in completed_quests:
                narration += f"\n\n{t(lang, 'dqst_' + str(qcat.id) + '_complete')}"
                narration += f"\n{t(lang, 'dng_quest_completed_inline')}"
                
            from core.faction_engine import update_quest_progress as fac_quest_progress
            completed_f_quests = await fac_quest_progress(
                session, player.telegram_id, "dungeon",
                target_filter={"dungeon_id": dungeon_id, "floor": next_floor, "difficulty": difficulty}
            )
            for q in completed_f_quests:
                narration += "\n\n" + t(lang, "dng_faction_quest_completed", emoji=q.emoji, name=_cname(lang, "q", q))

            from core.achievement_engine import check_achievements
            adv_ach += await check_achievements(session, player.telegram_id, "dungeon_floors", 1)
            if player.realm == 2:
                from core.golden_core_engine import add_core_essence
                _ce = add_core_essence(player, 3)
                if _ce > 0:
                    narration += "\n" + t(lang, "core_essence_gain", amount=_ce, total=player.core_essence or 0)
            from core.body_tempering_engine import add_tempering_progress
            floor_diff_mult = DIFF_CONFIG[difficulty]["loot_mult"]
            add_tempering_progress(player, max(2, int(5 * floor_diff_mult)))
        else:
            lost_bag = pd.expedition_bag or {}
            survivors = _lose_90_percent(lost_bag)
            if survivors:
                await _transfer_bag_to_inventory(session, player, survivors)
            pd.current_floor = 0
            pd.expedition_bag = {}
            pd.difficulty = None
            pd.last_attempt_at = datetime.now(timezone.utc)
            if lost_bag:
                narration += f"\n\n{t(lang, 'dng_lost_90_loot')}"

        await session.commit()
        if adv_ach:
            from handlers.achievements import notify_achievements
            await notify_achievements(context, player.telegram_id, adv_ach)

        kb = _after_fight_keyboard(dungeon_id, won, lang, auto_progress=bool(getattr(player, "auto_progress_dungeon", False)))
        await safe_answer(query)
        await query.edit_message_text(narration, reply_markup=kb, parse_mode="Markdown")


# v14.5 Q-1 — Auto-progress dungeon. Opt-in via /conf → Notificações
# (`auto_progress_dungeon` toggle). Loops floors until HP <30% or Qi <20%,
# the player loses a fight, the dungeon completes, or a 10-second time
# budget is exhausted. One summary message at the end — no per-floor spam.
AUTO_PROGRESS_HP_STOP = 0.30
AUTO_PROGRESS_QI_STOP = 0.20
AUTO_PROGRESS_MAX_ITERS = 50
AUTO_PROGRESS_TIME_BUDGET = 10.0  # seconds


@safe_handler
@rate_limit(2)
async def dungeon_auto_advance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Loop floor advances until a stop condition fires, then render a summary."""
    query = update.callback_query
    user = update.effective_user

    dungeon_id = safe_parse_callback_int(query.data, "dng_auto_advance_")
    if dungeon_id is None:
        await safe_answer(query)
        return

    started_at = datetime.now(timezone.utc)

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"

        if not player.auto_progress_dungeon:
            # Toggle was flipped off mid-run — surface a hint and bail back.
            await safe_answer(query, t(lang, "auto_progress_off"), show_alert=True)
            return

        if get_current_hp(player) <= 0:
            await safe_answer(query, t(lang, "hp_too_low_combat"), show_alert=True)
            return

        dungeon = (await session.execute(
            select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id)
        )).scalar_one_or_none()
        if not dungeon:
            await safe_answer(query)
            return

        pd = (await session.execute(
            select(PlayerDungeon).where(and_(
                PlayerDungeon.player_id == player.telegram_id,
                PlayerDungeon.dungeon_id == dungeon_id,
            ))
        )).scalar_one_or_none()

        if not pd or pd.current_floor == 0:
            await safe_answer(query, t(lang, "dng_not_in_dungeon"), show_alert=True)
            return

        difficulty = pd.difficulty or "normal"
        floor_count = _get_floor_count(dungeon, difficulty)
        adv_stance = context.user_data.get("dng_stance", "balanced")
        adv_focus = context.user_data.get("dng_focus", 0)

        floors_won: list[int] = []
        loot_total: dict = {}
        stop_reason: str = "hp"  # default; overwritten below
        adv_ach: list = []
        completed_dungeon = False

        for _ in range(AUTO_PROGRESS_MAX_ITERS):
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            if elapsed > AUTO_PROGRESS_TIME_BUDGET:
                stop_reason = "budget"
                break

            cur_hp = get_current_hp(player)
            max_hp_v = get_max_hp(player)
            hp_pct = (cur_hp / max_hp_v) if max_hp_v > 0 else 0
            qi_pct = (player.qi / player.qi_capacity) if player.qi_capacity > 0 else 0
            if hp_pct < AUTO_PROGRESS_HP_STOP:
                stop_reason = "hp"
                break
            if qi_pct < AUTO_PROGRESS_QI_STOP:
                stop_reason = "qi"
                break

            next_floor = pd.current_floor + 1
            if next_floor > floor_count:
                # Same finalisation path as dungeon_advance "completed" branch.
                await _transfer_bag_to_inventory(session, player, pd.expedition_bag or {})
                pd.current_floor = 0
                pd.expedition_bag = {}
                # Fix 2026-07-23 (report [jogador]): completar = alcançou o último andar.
                pd.max_floor_reached = max(int(pd.max_floor_reached or 0), int(floor_count))
                pd.completed = True
                pd.best_difficulty = max(pd.best_difficulty, DIFF_ORDER[difficulty])
                pd.difficulty = None
                pd.last_attempt_at = datetime.now(timezone.utc)
                _inv_cache(player.telegram_id)
                if dungeon_id == 4:
                    from core.achievement_engine import check_achievements
                    adv_ach += await check_achievements(session, player.telegram_id, "dungeon_abyssal", 1)
                from core.bp_engine import update_bp_mission
                await update_bp_mission(session, player.telegram_id, "complete_dungeon")
                from core.body_tempering_engine import add_tempering_progress
                tempering_base = max(10, floor_count * 3)
                tempering_diff_mult = DIFF_CONFIG[difficulty]["loot_mult"]
                add_tempering_progress(player, int(tempering_base * tempering_diff_mult))
                from core.faction_engine import update_quest_progress as fac_quest_progress
                await fac_quest_progress(session, player.telegram_id, "dungeon_any")
                await fac_quest_progress(
                    session, player.telegram_id, "dungeon",
                    target_filter={"dungeon_id": dungeon_id, "floor": floor_count, "difficulty": difficulty},
                )
                from core.dungeon_quest_engine import track_dungeon_quest_progress
                await track_dungeon_quest_progress(
                    session, player.telegram_id, dungeon_id,
                    "dungeon_complete", floor_count, difficulty, True,
                )
                completed_dungeon = True
                stop_reason = "completed"
                break

            won, narration, loot = await _do_dungeon_floor(
                session, player, dungeon, next_floor, difficulty, lang, adv_stance, adv_focus
            )

            # v15.1.4 — Boss floor: auto-advance halts here. Boss duels
            # are turn-based mini-app only; never auto-resolve. Player
            # gets a "boss waiting" stop reason and a manual handoff.
            if isinstance(loot, dict) and loot.get("boss_floor"):
                stop_reason = "boss"
                break

            # `_do_dungeon_floor` returns False with a "dng_no_qi" key when Qi
            # was insufficient for the cost — same sentinel as dungeon_advance.
            if "dng_no_qi" in narration:
                stop_reason = "qi"
                break

            if won:
                pd.current_floor = next_floor
                pd.max_floor_reached = max(pd.max_floor_reached, next_floor)
                pd.expedition_bag = _merge_bag(pd.expedition_bag or {}, loot)
                pd.last_attempt_at = datetime.now(timezone.utc)
                floors_won.append(next_floor)
                loot_total = _merge_bag(loot_total, loot)
                await track_quest(session, player.telegram_id, "dungeon_floor", 1)
                from core.achievement_engine import check_achievements
                adv_ach += await check_achievements(session, player.telegram_id, "dungeon_floors", 1)
                if player.realm == 2:
                    from core.golden_core_engine import add_core_essence
                    add_core_essence(player, 3)
                from core.body_tempering_engine import add_tempering_progress
                floor_diff_mult = DIFF_CONFIG[difficulty]["loot_mult"]
                add_tempering_progress(player, max(2, int(5 * floor_diff_mult)))
                from core.dungeon_quest_engine import track_dungeon_quest_progress
                await track_dungeon_quest_progress(
                    session, player.telegram_id, dungeon_id,
                    "floor_win", next_floor, difficulty, False,
                )
                from core.faction_engine import update_quest_progress as fac_quest_progress
                await fac_quest_progress(
                    session, player.telegram_id, "dungeon",
                    target_filter={"dungeon_id": dungeon_id, "floor": next_floor, "difficulty": difficulty},
                )
            else:
                # Lost — same death penalty as dungeon_advance.
                lost_bag = pd.expedition_bag or {}
                survivors = _lose_90_percent(lost_bag)
                if survivors:
                    await _transfer_bag_to_inventory(session, player, survivors)
                pd.current_floor = 0
                pd.expedition_bag = {}
                pd.difficulty = None
                pd.last_attempt_at = datetime.now(timezone.utc)
                stop_reason = "lost"
                break
        else:
            # Hit AUTO_PROGRESS_MAX_ITERS without any other stop — extremely
            # unlikely (dungeons cap at ~20 floors). Treat as time-out.
            stop_reason = "budget"

        await session.commit()

        if adv_ach:
            from handlers.achievements import notify_achievements
            await notify_achievements(context, player.telegram_id, adv_ach)

        # ── Render single summary message ────────────────────────────────────
        herb_names, ore_names = await _load_item_names(session)
        diff_emoji = DIFF_CONFIG[difficulty]["emoji"]
        lines = [
            t(lang, "auto_advance_summary_header",
              emoji=dungeon.emoji, name=dungeon.name,
              diff_emoji=diff_emoji, diff=t(lang, f"dng_diff_{difficulty}")),
        ]
        if floors_won:
            lines.append(t(lang, "auto_advance_floors_won",
                           count=len(floors_won),
                           first=floors_won[0], last=floors_won[-1]))
        else:
            lines.append(t(lang, "auto_advance_no_floors_won"))

        loot_text = _format_loot(loot_total, lang, herb_names, ore_names)
        if loot_text:
            lines.append("")
            lines.append(t(lang, "auto_advance_loot_collected"))
            lines.append(loot_text)

        # Onda B — auto-advance summary HP shown == the arena/profile (Alma-routed).
        from core.cultivator_soul import soul_max_hp, soul_current_hp
        max_hp_v = await soul_max_hp(session, player)
        cur_hp = soul_current_hp(player, max_hp_v)
        hp_pct = int(cur_hp / max_hp_v * 100) if max_hp_v > 0 else 0
        qi_pct = int(player.qi / player.qi_capacity * 100) if player.qi_capacity > 0 else 0
        lines.append("")
        lines.append(t(lang, "auto_advance_state",
                       hp=format_number(cur_hp), max_hp=format_number(max_hp_v), hp_pct=hp_pct,
                       qi=int(player.qi), qi_max=int(player.qi_capacity), qi_pct=qi_pct))

        stop_key = {
            "hp": "auto_advance_stop_hp",
            "qi": "auto_advance_stop_qi",
            "lost": "auto_advance_stop_lost",
            "completed": "auto_advance_stop_completed",
            "budget": "auto_advance_stop_budget",
            "boss": "auto_advance_stop_boss",
        }.get(stop_reason, "auto_advance_stop_hp")
        lines.append("")
        lines.append(t(lang, stop_key))

        text = "\n".join(lines)
        if completed_dungeon or stop_reason == "lost":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "dng_btn_list"), callback_data="dng_list")]])
        else:
            # Still inside the dungeon — give the player both buttons so they
            # can retreat (claim) or push manually. Auto button always re-shows
            # here because we already proved the toggle is on.
            kb = _after_fight_keyboard(dungeon_id, True, lang, auto_progress=True)
        await safe_answer(query)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


@safe_handler
@rate_limit(1)
async def dungeon_retreat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retreat safely — claim 100% of loot."""
    query = update.callback_query
    user = update.effective_user

    dungeon_id = safe_parse_callback_int(query.data, "dng_retreat_")
    if dungeon_id is None:
        await safe_answer(query)
        return

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"
        dungeon = (await session.execute(select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id))).scalar_one_or_none()
        pd = (await session.execute(
            select(PlayerDungeon).where(and_(
                PlayerDungeon.player_id == player.telegram_id,
                PlayerDungeon.dungeon_id == dungeon_id,
            ))
        )).scalar_one_or_none()

        if not pd:
            await safe_answer(query, t(lang, "dng_not_in_dungeon"), show_alert=True)
            return

        bag = pd.expedition_bag or {}
        herb_names, ore_names = await _load_item_names(session)
        bag_text = _format_loot(bag, lang, herb_names, ore_names)
        floor_reached = pd.current_floor

        await _transfer_bag_to_inventory(session, player, bag)
        pd.current_floor = 0
        pd.expedition_bag = {}
        pd.difficulty = None
        pd.last_attempt_at = datetime.now(timezone.utc)
        _inv_cache(player.telegram_id)
        await session.commit()

        name = dungeon.name if dungeon else f"Dungeon #{dungeon_id}"
        emoji = dungeon.emoji if dungeon else "🗺️"
        lines = [
            t(lang, "dng_retreat_title", emoji=emoji, name=name),
            t(lang, "dng_retreat_floor", floor=floor_reached),
        ]
        if bag_text:
            lines.append(t(lang, "dng_retreat_loot"))
            lines.append(bag_text)
        else:
            lines.append(t(lang, "dng_bag_empty"))

        text = "\n".join(lines)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "dng_btn_list"), callback_data="dng_list")]])
        await safe_answer(query)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


@safe_handler
@rate_limit(1)
async def dungeon_bag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View expedition bag contents."""
    query = update.callback_query
    user = update.effective_user

    dungeon_id = safe_parse_callback_int(query.data, "dng_bag_")
    if dungeon_id is None:
        await safe_answer(query)
        return

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            await safe_answer(query)
            return

        lang = player.language or "en"
        pd = (await session.execute(
            select(PlayerDungeon).where(and_(
                PlayerDungeon.player_id == player.telegram_id,
                PlayerDungeon.dungeon_id == dungeon_id,
            ))
        )).scalar_one_or_none()

        bag = pd.expedition_bag if pd else {}
        herb_names, ore_names = await _load_item_names(session)
        bag_text = _format_loot(bag or {}, lang, herb_names, ore_names)

        lines = [
            t(lang, "dng_bag_title"),
            t(lang, "dng_bag_note"),
            "",
            bag_text,
        ]
        text = "\n".join(lines)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_view_{dungeon_id}")]])
        await safe_answer(query)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


@safe_handler
@rate_limit(1)
async def dungeon_sweep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show difficulty picker for sweep."""
    query = update.callback_query
    user = update.effective_user

    dungeon_id = safe_parse_callback_int(query.data, "dng_sweep_")
    if dungeon_id is None:
        await safe_answer(query)
        return

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"
        dungeon = (await session.execute(select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id))).scalar_one_or_none()
        if not dungeon:
            await safe_answer(query, t(lang, "dng_not_found"), show_alert=True)
            return

        pd = (await session.execute(
            select(PlayerDungeon).where(and_(
                PlayerDungeon.player_id == player.telegram_id,
                PlayerDungeon.dungeon_id == dungeon_id,
            ))
        )).scalar_one_or_none()

        if not pd or not pd.completed:
            await safe_answer(query, t(lang, "dng_not_in_dungeon"), show_alert=True)
            return

        # MV-1: o picker do sweep também respeita a geografia.
        from core.dungeon_regions import region_gate
        _rg = region_gate(dungeon, player)
        if _rg:
            cname = t(lang, f"continent_{_rg['continent']}")
            await safe_answer(query, t(lang, "dng_wrong_continent", emoji=_rg["continent_emoji"], name=cname), show_alert=True)
            return

        best_diff = pd.best_difficulty

        lines = [
            f"⚡ *{escape_markdown(dungeon.name)}* — {t(lang, 'dng_sweep_pick')}",
            "",
        ]
        for diff in DIFFICULTIES:
            cfg = DIFF_CONFIG[diff]
            diff_level = DIFF_ORDER[diff]
            if diff_level <= best_diff:
                floors = _get_floor_count(dungeon, diff)
                qi_cost = _effective_qi_cost(dungeon.qi_cost_per_floor, player.realm) * floors
                lines.append(f"{cfg['emoji']} *{t(lang, f'dng_diff_{diff}')}* — {floors}F | {cfg['loot_mult']}x | {qi_cost} Qi")

        text = "\n".join(lines)

        # Build sweep difficulty buttons (only completed difficulties)
        rows = []
        for diff in DIFFICULTIES:
            cfg = DIFF_CONFIG[diff]
            diff_level = DIFF_ORDER[diff]
            if diff_level <= best_diff:
                floors = _get_floor_count(dungeon, diff)
                label = f"{cfg['emoji']} {t(lang, f'dng_diff_{diff}')} — {floors}F | {cfg['loot_mult']}x"
                rows.append([InlineKeyboardButton(label, callback_data=f"dng_sdiff_{dungeon.id}_{diff}")])
        rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_view_{dungeon.id}")])
        kb = InlineKeyboardMarkup(rows)

        await safe_answer(query)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")


@safe_handler
@rate_limit(2)
async def dungeon_sweep_exec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Execute sweep at chosen difficulty."""
    query = update.callback_query
    user = update.effective_user

    dungeon_id, difficulty = _parse_diff_callback(query.data, "dng_sdiff_")
    if dungeon_id is None or difficulty is None:
        await safe_answer(query)
        return

    async with get_session_with_retry() as session:
        player = await _get_player(user.id, session)
        if not player:
            return

        lang = player.language or "en"

        dungeon = (await session.execute(select(DungeonCatalog).where(DungeonCatalog.id == dungeon_id))).scalar_one_or_none()
        if not dungeon:
            await safe_answer(query, t(lang, "dng_not_found"), show_alert=True)
            return

        pd = (await session.execute(
            select(PlayerDungeon).where(and_(
                PlayerDungeon.player_id == player.telegram_id,
                PlayerDungeon.dungeon_id == dungeon_id,
            ))
        )).scalar_one_or_none()

        if not pd or not pd.completed:
            await safe_answer(query, t(lang, "dng_not_in_dungeon"), show_alert=True)
            return

        # Check player has completed this difficulty
        diff_level = DIFF_ORDER[difficulty]
        if pd.best_difficulty < diff_level:
            await safe_answer(query, t(lang, "dng_diff_gate", req=t(lang, f"dng_diff_{difficulty}")), show_alert=True)
            return

        # MV-1: sweep também respeita a geografia (recusa honesta, server-side).
        from core.dungeon_regions import region_gate, regional_bonus_line, roll_regional_bonus
        _rg = region_gate(dungeon, player)
        if _rg:
            cname = t(lang, f"continent_{_rg['continent']}")
            await safe_answer(query, t(lang, "dng_wrong_continent", emoji=_rg["continent_emoji"], name=cname), show_alert=True)
            return

        # QoL-relatos — varrer OUTRA masmorra já concluída continua LIVRE mesmo com
        # uma run aberta (varredura é revisitar o que se dominou, não uma
        # expedição). O que se recusa é varrer a masmorra onde você ESTÁ:
        # `completed` e `current_floor` são independentes, então dá para
        # varrer e correr a mesma masmorra ao mesmo tempo — e isso paga duas
        # vezes. Daí `only=` em vez de `exclude=`.
        from core.dungeon_run_engine import active_run
        _run = await active_run(session, player.telegram_id, only=dungeon_id)
        if _run:
            _txt, _kb = _run_elsewhere_refusal(lang, _run, same=True)
            await safe_answer(query)
            await query.edit_message_text(_txt, reply_markup=_kb, parse_mode="Markdown")
            return

        floor_count = _get_floor_count(dungeon, difficulty)

        # Qi cost = effective cost per floor × total floors (scales with realm)
        total_qi_cost = _effective_qi_cost(dungeon.qi_cost_per_floor, player.realm) * floor_count
        if player.qi < total_qi_cost:
            text = t(lang, "dng_sweep_no_qi", current=int(player.qi), cost=total_qi_cost)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_view_{dungeon_id}")]])
            await safe_answer(query)
            await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
            return

        player.qi = max(0.0, player.qi - total_qi_cost)

        # Roll drops for every floor and merge them
        from core.alchemy_engine import roll_recipe_drop
        from database.models import PillCatalog
        bag: dict = {}
        for _ in range(floor_count):
            floor_loot = _roll_floor_loot(dungeon.drops, difficulty, min_realm=int(dungeon.min_realm or 0))
            floor_loot = _apply_difficulty_loot_mult(floor_loot, difficulty)
            bag = _merge_bag(bag, floor_loot)
            # Recipe drop chance per floor (same 8%; hard/nightmare → T4, ver
            # nota N-34 no _do_dungeon_floor)
            if not bag.get("recipe_pill_id"):
                _rt_max = 4 if difficulty in ("hard", "nightmare") else 3
                recipe_pill_id = await roll_recipe_drop(session, player.telegram_id, (2, _rt_max), 0.08)
                if recipe_pill_id:
                    bag["recipe_pill_id"] = recipe_pill_id
                    _pill = await session.get(PillCatalog, recipe_pill_id)
                    bag["recipe_pill_name"] = _cname(lang, "pill", _pill) if _pill else f"Recipe #{recipe_pill_id}"

        # Apply event loot multiplier
        from handlers.events import get_event_multipliers
        event_mults = await get_event_multipliers(session)
        loot_mult = event_mults.get("loot_mult", 1.0)
        if loot_mult > 1.0:
            bag_multiplied: dict = {}
            for key, val in bag.items():
                if key in ("herbs", "ores", "healing_pills") and isinstance(val, dict):
                    bag_multiplied[key] = {k: max(1, int(v * loot_mult)) for k, v in val.items()}
                elif key == "qi_pill_id":
                    bag_multiplied[key] = val  # D4: tier marker, never scale it
                elif isinstance(val, (int, float)):
                    bag_multiplied[key] = max(1, int(val * loot_mult))
                else:
                    bag_multiplied[key] = val
            bag = bag_multiplied

        # Fortune Incense buff: +5% stones bonus on sweep
        from database.models import PlayerBuff
        _now_fi = datetime.now(timezone.utc)
        _incense_sweep = (await session.execute(
            select(PlayerBuff).where(
                PlayerBuff.player_id == player.telegram_id,
                PlayerBuff.buff_type == "fortune_incense",
                PlayerBuff.expires_at > _now_fi
            )
        )).scalar_one_or_none()
        if _incense_sweep:
            bag["stones"] = int(bag.get("stones", 0) * 1.05)

        # MV-1 §5: roll extra de material nativo do continente (hard/nightmare,
        # flag ON) — ADITIVO, antes do transfer para aparecer no loot.
        _regional = roll_regional_bonus(dungeon, difficulty)
        if _regional:
            bag = _merge_bag(bag, _regional["loot"])

        await _transfer_bag_to_inventory(session, player, bag)
        pd.last_attempt_at = datetime.now(timezone.utc)
        from core.body_tempering_engine import add_tempering_progress
        sweep_tempering_base = max(10, floor_count * 3)
        sweep_diff_mult = DIFF_CONFIG[difficulty]["loot_mult"]
        tempering_gained = add_tempering_progress(player, int(sweep_tempering_base * sweep_diff_mult))

        # Core Essence for sweep (same 3 per floor as normal dungeon)
        ce_gained = 0
        if player.realm == 2:
            from core.golden_core_engine import add_core_essence
            ce_gained = add_core_essence(player, 3 * floor_count)

        from core.bp_engine import update_bp_mission
        await update_bp_mission(session, player.telegram_id, "complete_dungeon")

        from core.faction_engine import update_quest_progress as fac_quest_progress
        await fac_quest_progress(session, player.telegram_id, "dungeon_any")
        for f in range(1, floor_count + 1):
            await fac_quest_progress(
                session, player.telegram_id, "dungeon",
                target_filter={"dungeon_id": dungeon_id, "floor": f, "difficulty": difficulty},
            )
        completed_f_quests_final = await fac_quest_progress(
            session, player.telegram_id, "dungeon",
            target_filter={"dungeon_id": dungeon_id, "floor": floor_count, "difficulty": difficulty},
        )

        from core.dungeon_quest_engine import track_dungeon_quest_progress
        for f in range(1, floor_count + 1):
            await track_dungeon_quest_progress(session, player.telegram_id, dungeon_id, "floor_win", f, difficulty, False)
        completed_quests = await track_dungeon_quest_progress(session, player.telegram_id, dungeon_id, "dungeon_complete", floor_count, difficulty, True)

        # QoL 31/07 Item B (decisão [jogador], Lei §6): o sweep credita os MESMOS
        # hooks do advance. O gate lá em cima (pd.completed + best_difficulty
        # >= diff_level) JÁ prova que a dificuldade varrida foi 100% completada
        # — a ida aconteceu; o sweep é colheita legítima. Faction + floor_win +
        # dungeon_complete + essência creditam aqui desde 2026-04 (54ad520b);
        # estes eram os 2 que faltavam para a paridade total por andar.
        from core.achievement_engine import check_achievements
        sweep_ach = await check_achievements(session, player.telegram_id, "dungeon_floors", floor_count)
        await track_quest(session, player.telegram_id, "dungeon_floor", floor_count)

        await session.commit()
        if sweep_ach:
            from handlers.achievements import notify_achievements
            await notify_achievements(context, player.telegram_id, sweep_ach)

        diff_emoji = DIFF_CONFIG[difficulty]["emoji"]
        herb_names, ore_names = await _load_item_names(session)
        drops_text = _format_loot(bag, lang, herb_names, ore_names)
        text = t(lang, "dng_sweep_result",
                 emoji=dungeon.emoji, name=dungeon.name,
                 floors=floor_count, qi_cost=total_qi_cost)
        text += f"\n{diff_emoji} {t(lang, f'dng_diff_{difficulty}')}"
        text += f"\n\n{t(lang, 'dng_sweep_drops')}\n{drops_text}"
        if tempering_gained > 0:
            text += f"\n{t(lang, 'dng_sweep_tempering', amount=tempering_gained)}"
        if ce_gained > 0:
            text += f"\n{t(lang, 'core_essence_gain', amount=ce_gained, total=player.core_essence or 0)}"
        if loot_mult > 1.0:
            text += f"\n☄️ _{t(lang, 'event_meteor_shower_bonus')}_"
        if _regional:
            # QoL 04/08 (report [jogador]) — a linha DIZ o item e a quantidade
            # (o servidor já os tinha; a tela deitava-os fora).
            _trib = await regional_bonus_line(session, _regional, lang)
            if _trib:
                text += f"\n{_trib}"

        for pq, qcat in completed_quests:
            text += f"\n\n{t(lang, 'dqst_' + str(qcat.id) + '_complete')}"
            text += f"\n{t(lang, 'dng_quest_completed_inline')}"

        for q in completed_f_quests_final or []:
            text += "\n\n" + t(lang, "dng_faction_quest_completed", emoji=q.emoji, name=_cname(lang, "q", q))

        # H-10: "Sweep again" button keeps the dungeon + difficulty in scope.
        # Uses the existing `dng_sdiff_` callback so the executor parses it correctly.
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                t(lang, "dng_sweep_again"),
                callback_data=f"dng_sdiff_{dungeon_id}_{difficulty}",
            )],
            [InlineKeyboardButton(t(lang, "dng_btn_list"), callback_data="dng_list")],
        ])
        await safe_answer(query)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def _dungeon_quest_list(update: Update, context: ContextTypes.DEFAULT_TYPE, force_dungeon_id: int = None):
    query = update.callback_query
    dungeon_id = force_dungeon_id or safe_parse_callback_int(query.data, "dng_qlist_")
    if not dungeon_id:
        return

    async with get_session_with_retry() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"
        
        from core.dungeon_quest_engine import get_player_dungeon_quests
        quests_info = await get_player_dungeon_quests(session, player.telegram_id, dungeon_id)
        
        if not quests_info:
            await safe_answer(query, t(lang, "dqst_no_quests_avail", fallback="No quests available."), show_alert=True)
            return
            
        text = t(lang, "dng_quest_menu_title", fallback="📜 Dungeon Quests") + "\n\n"
        from core.dungeon_quest_engine import is_quest_on_cooldown

        # QoL-Feedback 2026-07-29 Item C (report [jogador]): a rep prometida é de
        # FACÇÃO — sem facção o claim pula o crédito, então o preview tem de
        # dizer isso ANTES (Lei §1) e nomear a moeda (lição naming MV-6).
        from database.models import PlayerFaction
        has_faction = (await session.execute(
            select(PlayerFaction).where(PlayerFaction.player_id == player.telegram_id)
        )).scalar_one_or_none() is not None

        kb_rows = []
        for qcat, pdq in quests_info:
            text += f"{qcat.emoji} *{qcat.name}*"
            desc = t(lang, qcat.description_key) if qcat.description_key else ""

            rew_str = []
            if qcat.reward_rep:
                rep_key = "dng_quest_rep_preview" if has_faction else "dng_quest_rep_preview_nofaction"
                rew_str.append(t(lang, rep_key, amount=qcat.reward_rep))
            if qcat.reward_stones: rew_str.append(f"🪨 +{qcat.reward_stones} Spirit Stones")
            if qcat.reward_items:
                if "technique_scroll" in qcat.reward_items: 
                    rew_str.append(f"📜 +{qcat.reward_items['technique_scroll']}x Random Technique")
                if "herb_pack" in qcat.reward_items: 
                    rew_str.append(f"🌿 +{qcat.reward_items['herb_pack']}x Herb Packs")
                if "dao_fragment" in qcat.reward_items: 
                    rew_str.append(f"💠 +{qcat.reward_items['dao_fragment']}x Dao Fragments")
                if "ore" in qcat.reward_items: 
                    ore_data = qcat.reward_items["ore"]
                    ore_id = ore_data.get("id")
                    ore_qty = ore_data.get("qty", 1)
                    from database.models import OreCatalog
                    ore_obj = await session.get(OreCatalog, ore_id)
                    ore_name = _cname(lang, "ore", ore_obj) if ore_obj else f"Ore #{ore_id}"
                    rew_str.append(f"⛏️ +{ore_qty}x {ore_name}")
            
            rew_txt = "\n".join([f"  {r}" for r in rew_str])

            if desc:
                text += f"\n_{desc}_\n🎁 *Rewards*:\n{rew_txt}"
            else:
                text += f"\n🎁 *Rewards*:\n{rew_txt}"
                
            req_diff = t(lang, f"dng_diff_{qcat.min_difficulty}")
            
            status_text = ""
            btn = None
            if not pdq:
                status_text = t(lang, "dng_quest_status_pending", fallback="Pending")
                text += f"\n🏆 *Req*: {req_diff} | {status_text}"
                btn = InlineKeyboardButton(f"📜 {qcat.name}", callback_data=f"dng_qacc_{qcat.id}")
            else:
                on_cd, remaining = is_quest_on_cooldown(pdq, qcat.cooldown_hours)
                if pdq.progress >= qcat.objective_count and pdq.is_active:
                    status_text = t(lang, "dng_quest_status_claimable", fallback="Ready to Claim")
                    text += f"\n✅ {status_text}"
                    btn = InlineKeyboardButton(f"🎁 {t(lang, 'dng_btn_claim', fallback='Claim')}", callback_data=f"dng_qclm_{qcat.id}")
                elif pdq.is_active:
                    status_text = t(lang, "dng_quest_status_active", fallback="Active")
                    if qcat.objective_target:
                        text += f"\n🎯 *Prog*: {pdq.progress}/{qcat.objective_count} | {status_text}"
                    else:
                        text += f"\n🎯 *Req*: {req_diff} | {status_text}"
                elif on_cd:
                    status_text = t(lang, "dng_quest_status_cooldown", fallback="Cooldown ({hours}h)", hours=remaining)
                    text += f"\n⏳ {status_text}"
                else:
                    status_text = t(lang, "dng_quest_status_ready", fallback="Ready")
                    text += f"\n🔄 {status_text}"
                    btn = InlineKeyboardButton(f"📜 {qcat.name}", callback_data=f"dng_qacc_{qcat.id}")
                    
            if btn:
                kb_rows.append([btn])
            text += "\n" + "—" * 15 + "\n"
            
        kb_rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"dng_view_{dungeon_id}")])
        kb = InlineKeyboardMarkup(kb_rows)
        await safe_answer(query)
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def _dungeon_quest_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    query = update.callback_query
    prefix = "dng_qacc_" if action == "accept" else "dng_qclm_"
    quest_id = safe_parse_callback_int(query.data, prefix)
    if not quest_id:
        return
        
    async with get_session_with_retry() as session:
        player = await _get_player(update.effective_user.id, session)
        if not player:
            return
        lang = player.language or "en"
        
        from database.models import DungeonQuestCatalog
        qcat = await session.get(DungeonQuestCatalog, quest_id)
        if not qcat:
            await safe_answer(query, t(lang, "dng_quest_not_found"), show_alert=True)
            return
            
        if action == "accept":
            from core.dungeon_quest_engine import accept_dungeon_quest
            success, err = await accept_dungeon_quest(session, player.telegram_id, quest_id)
            if not success:
                err_num = err.split(":")[1] if ":" in err else ""
                err_k = err.split(":")[0] if ":" in err else err
                await safe_answer(query, t(lang, err_k, hours=err_num), show_alert=True)
                return
            await session.commit()
            
            # Send intro narrative
            intro = t(lang, qcat.story_intro_key) if qcat.story_intro_key else ""
            if intro:
                await context.bot.send_message(
                    chat_id=player.telegram_id, 
                    text=f"📜 *{qcat.name}*\n\n_{intro}_", 
                    parse_mode="Markdown"
                )
            await safe_answer(query, t(lang, "dng_quest_accepted"), show_alert=True)
            
        elif action == "claim":
            from core.dungeon_quest_engine import claim_dungeon_quest_reward
            rewards, item_name = await claim_dungeon_quest_reward(session, player.telegram_id, quest_id)
            if rewards is None:
                await safe_answer(query, t(lang, item_name), show_alert=True)
                return
            await session.commit()
            
            rep = rewards.get("reputation", 0)
            rep_missed = rewards.get("reputation_missed", 0)
            st = rewards.get("spirit_stones", 0)
            txt = t(lang, "dng_quest_claimed", name=qcat.name, fallback="Quest Completed!")
            if st > 0: txt += f"\n- {t(lang, 'currency_spirit_stones')}: {st}"
            # QoL-Feedback 2026-07-29 Item C: rotular a moeda (🔱 facção, não a
            # rep de continente) e DIZER quando o crédito foi pulado (Lei §1).
            if rep > 0: txt += "\n- " + t(lang, "dng_quest_rep_gain", amount=rep)
            if rep_missed > 0: txt += "\n" + t(lang, "dng_quest_rep_missed", amount=rep_missed)
            await safe_answer(query, txt, show_alert=True)
            
        await _dungeon_quest_list(update, context, force_dungeon_id=qcat.dungeon_id)

# ─── Button Router ─────────────────────────────────────────────────────────────

async def dungeon_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    data = query.data

    if data == "dng_list" or data == "cmd_dungeons":
        await dungeons_command(update, context)
        return True
    if data.startswith("dng_page_") or data.startswith("dng_cat_"):
        await dungeons_command(update, context)
        return True
    if data.startswith("dng_view_"):
        await dungeon_view(update, context)
        return True
    if data.startswith("dng_enter_"):
        await dungeon_enter(update, context)
        return True
    if data.startswith("dng_go_"):
        await _dungeon_start_with_stance(update, context)
        return True
    if data.startswith("dng_st_"):
        await _dng_focus_menu(update, context)
        return True
    if data.startswith("dng_diff_"):
        await dungeon_start_difficulty(update, context)
        return True
    if data.startswith("dng_sdiff_"):
        await dungeon_sweep_exec(update, context)
        return True
    if data.startswith("dng_auto_advance_"):
        await dungeon_auto_advance(update, context)
        return True
    if data.startswith("dng_advance_"):
        await dungeon_advance(update, context)
        return True
    if data.startswith("dng_retreat_"):
        await dungeon_retreat(update, context)
        return True
    if data.startswith("dng_bag_"):
        await dungeon_bag(update, context)
        return True
    if data.startswith("dng_sweep_"):
        await dungeon_sweep(update, context)
        return True
    if data.startswith("dng_qlist_"):
        await _dungeon_quest_list(update, context)
        return True
    if data.startswith("dng_qacc_"):
        await _dungeon_quest_action(update, context, action="accept")
        return True
    if data.startswith("dng_qclm_"):
        await _dungeon_quest_action(update, context, action="claim")
        return True

    return False
