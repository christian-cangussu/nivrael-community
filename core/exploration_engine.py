"""core/exploration_engine.py — Onda 5 (Fase 1): Reinos Exploráveis.

The ADDITIVE exploration loop. The player enters the continent they are in and
explores by Divine Sense (神識): picks a direction, resolves an encounter
(safe material cache · a quick trash fight · a Karmic-Crossroads moral fork · or
a rare luck-gated Hidden Monster = an Onda 3 NPC Cultivator), accumulates loot in
an expedition BAG, and decides "safe return" (bank 100%) or "go deeper" (more
risk — dying deep loses 90%, reusing the dungeon death penalty).

It COEXISTS with the 23 dungeons (/dungeons is untouched — this is a NEW tier)
and REUSES what is already alive:
  * the node map mirrors CONTINENT_META: ``EXPLORATION_NODES`` links each
    continent → a set of dungeon nodes whose loot POOL is the dungeon's own
    ``drops`` (Engine, NOT DB — wipe-safe; no column added to the dungeons).
  * the bag/loot/loss mechanic = ``handlers.dungeons`` helpers verbatim.
  * the Hidden Monster = ``npc_cultivator_engine.pick`` + ``rehydrate`` +
    ``start_duel_pve(source='exploration')`` settled in ``pve_duel_settle``;
    its spare/execute fork reuses ``apply_combat_moral_choice``.
  * the RPG forks reuse the Karmic-Crossroads pattern (karma via
    ``apply_karma(..., delta_override=...)``).

Production safety (Lei §5 + §1 + §4):
  * 🔴 ADDITIVE — /dungeons intact; NEVER locks farm/continent.
  * Loot = MATERIALS only (herbs/ores/stones/pills) — NEVER techniques
    (``_sanitize_pool`` strips scroll/dao-fragment faucets). No jade.
  * Its OWN cooldown stamp (``PlayerExploration.last_explore_at``), NEVER shared
    with ``last_cultivator_fight`` / farm.
  * Hidden Monsters are world encounters, NEVER on the ranking
    (``NPC_LEADERBOARD_ENABLED`` untouched, OFF).
  * Defensive: best-effort, never crash; invalid state → clear reason.

Concurrency: every WRITE (advance/retreat) runs with the CALLER holding the
``player`` row FOR UPDATE and owning the commit (the ``claim_bounty`` pattern);
this engine additionally locks the per-player ``player_exploration`` row.
"""

import logging
import os
import random
from datetime import datetime, timezone

from sqlalchemy import select

from core.continent_engine import CONTINENT_KEYS, DEFAULT_SPAWN_CONTINENT, is_valid_continent
from core.divine_sense_engine import scan_directions
from database.models import DungeonCatalog, NpcCultivator, PlayerExploration

logger = logging.getLogger(__name__)

# ── Node map (Engine, NOT DB — wipe-safe). Mirrors CONTINENT_META. ─────────────
# continent_key -> ordered list of DungeonCatalog ids. The node's name/emoji/
# min_realm/drops/qi_cost are read from DungeonCatalog at runtime (DRY — the loot
# pool stays in sync with the dungeon seeds; NO column is added to the dungeons,
# which keeps /dungeons 100% playable as the "fast instanced" tier). Mapping is
# the world_lore §3 continent→dungeon assignment (the 3 unassigned starters —
# Misty Cave/Forgotten Tomb/Spirit Mine — placed by theme: starters in Línghé,
# the ore mine in Qiānhé). 23 dungeons over 5 continents.
EXPLORATION_NODES = {
    "linghe":  [1, 6, 7, 10, 17],          # sacred centre / starter — universal + sects
    "qianhe":  [2, 9, 11, 18],             # north — body / ores / cold rivers
    "yanshan": [8, 12, 14],                # spring mountains — herbs / alchemy
    "fenghuo": [13, 16, 19],               # eternal fire — forge / combat
    "moyu":    [3, 4, 5, 15, 20, 21, 22, 23],  # ink rain — forbidden / demonic
}

# ── Tuning (env-overridable). ──────────────────────────────────────────────────
EXPLORE_QI_BASE = int(os.getenv("EXPLORE_QI_BASE", "10"))
# Its OWN cooldown (NEVER shared with farm). Default 0 = qi is the only gate;
# the field + knob exist so the owner can pace the loop without touching farm.
EXPLORE_COOLDOWN_SECONDS = int(os.getenv("EXPLORE_COOLDOWN_SECONDS", "0"))
EXPLORE_HIDDEN_QI_MULT = float(os.getenv("EXPLORE_HIDDEN_QI_MULT", "2.0"))
EXPLORE_HIDDEN_ROLLS_MIN = int(os.getenv("EXPLORE_HIDDEN_ROLLS_MIN", "5"))
EXPLORE_HIDDEN_ROLLS_MAX = int(os.getenv("EXPLORE_HIDDEN_ROLLS_MAX", "10"))
EXPLORE_NPC_WINDOW = int(os.getenv("EXPLORE_NPC_WINDOW", "1"))
# Fase 2 (item F — [jogador] 09.06: "uma rapaziada está apanhando… para os Bot"):
# players at or below this realm fight encounters ONE difficulty step easier
# (never below "easy"). CONSERVATIVE + additive: fight difficulty only — the
# LOOT difficulty is untouched, so nobody's drops are nerfed.
EXPLORE_LOW_REALM_PROTECT = int(os.getenv("EXPLORE_LOW_REALM_PROTECT", "2"))

# ── RPG fork templates (Karmic-Crossroads pattern). Deterministic per clue. ────
# Each choice: id (stable slug, <64B callback-safe), karma_delta (applied via
# apply_karma delta_override — like quest_moral_choice; NOT in KARMA_EVENTS), how
# many node-loot rolls it grants, and a stones multiplier. Righteous options pay
# modest + positive karma; greedy options pay more loot + negative karma.
EXPLORE_FORKS = {
    "wounded_elder": {
        "choices": [
            {"id": "aid",  "karma_delta": 12,  "rolls": 1, "stones_mult": 1.0},
            {"id": "rob",  "karma_delta": -12, "rolls": 2, "stones_mult": 1.4},
            {"id": "pass", "karma_delta": 0,   "rolls": 1, "stones_mult": 0.6},
        ],
    },
    "sealed_cache": {
        "choices": [
            {"id": "share", "karma_delta": 8,  "rolls": 1, "stones_mult": 1.0},
            {"id": "hoard", "karma_delta": -8, "rolls": 2, "stones_mult": 1.2},
        ],
    },
    "lost_disciple": {
        "choices": [
            {"id": "guide",   "karma_delta": 10,  "rolls": 1, "stones_mult": 1.0},
            {"id": "abandon", "karma_delta": 0,   "rolls": 1, "stones_mult": 0.8},
            {"id": "prey",    "karma_delta": -14, "rolls": 2, "stones_mult": 1.5},
        ],
    },
}

# ── Ecos Míticos 六耳猕猴 (Onda 5 Fase 3 / LW-05). Engine, NOT DB — wipe-safe. ───
# A raríssimo layer on the Hidden-Monster slot: legendary beings of Chinese myth.
# The jewel is the doppelgänger (Liu Er Mi Hou) — a Hidden Monster whose fighter
# is built from the PLAYER'S OWN snapshot (reuse of the Onda 3 echo path), so the
# player "fights himself". REUSE-ONLY (Lei §3): same duel motor, same settle, same
# spare/execute fork. The permanent reward is a COSMETIC TITLE (Lei §4/§5 — no
# jade, no technique, no balance drift; survives the wipe). NPCs stay OFF the
# ranking and the doppelgänger creates no PII (it is the player's own data, shown
# only to the player, with the telegram_id=0 / is_npc=True sentinels).
#
# Each eco:
#   body       : "doppelganger" (mirror the player) | "npc_echo" (a real
#                continent NPC Cultivator wrapped in mythic flavour; falls back to
#                the mirror if no NPC is present — honest, never a void).
#   alignment  : "righteous" | "demonic" | "neutral" — compared against the
#                player's karma-derived path to compute the karma_stance.
#   power_scale: STRIKE-ONLY base multiplier (faction_dmg), NEVER touches HP/bp.
#   display    : language-neutral arena name (Chinese + pinyin); None → the
#                doppelgänger shows the player's OWN dao_name (the "estás TU" punch).
#   title      : the permanent cosmetic title granted on the first win (must match
#                the achievement seed's title_granted, ids 32-35).
#   event      : the achievement event_type fired on the win (idempotent grant).
MYTHIC_ECHOES = {
    "liu_er": {  # 六耳猕猴 — Six-Eared Macaque, the perfect doppelgänger (the jewel)
        "body": "doppelganger", "alignment": "neutral", "power_scale": 1.0,
        "emoji": "🪞", "display": None,
        "title": "Reflexo do Vazio", "event": "mythic_liu_er",
    },
    "bai_ze": {  # 白泽 — Bái Zé, the auspicious all-knowing beast (righteous)
        "body": "npc_echo", "alignment": "righteous", "power_scale": 1.04,
        "emoji": "📖", "display": "白泽 Bái Zé",
        "title": "Voz do Bai Ze", "event": "mythic_bai_ze",
    },
    "taotie": {  # 饕餮 — Tāo Tiè, the gluttonous devourer (demonic)
        "body": "npc_echo", "alignment": "demonic", "power_scale": 1.06,
        "emoji": "👹", "display": "饕餮 Tāo Tiè",
        "title": "Fome do Taotie", "event": "mythic_taotie",
    },
    "chen_long": {  # 辰龙 — Chén Lóng, the celestial dragon (neutral, the tough one)
        "body": "npc_echo", "alignment": "neutral", "power_scale": 1.12,
        "emoji": "🐉", "display": "辰龙 Chén Lóng",
        "title": "Jugo do Dragão", "event": "mythic_chen_long",
    },
}

# Strike-only stance modifier (applied to faction_dmg, NEVER HP — wipe-safe):
#   aligned → a friendly spar (lower risk); opposed → loathing (harder);
#   neutral → the pure mirror. The eco recognizes (or rejects) your karma.
_MYTHIC_STANCE_SCALE = {"aligned": 0.90, "neutral": 1.0, "opposed": 1.10}
# Global doppelgänger/mythic strike knob (env-tunable for "difícil mas justo").
MYTHIC_DOPPEL_SCALE = float(os.getenv("MYTHIC_DOPPEL_SCALE", "1.0"))


def _mythic_stance(player_karma, alignment: str) -> str:
    """How a Mythic Echo regards the player: aligned (same karmic path), opposed
    (the opposite path), or neutral (a neutral eco, or a rogue/middling player)."""
    if alignment == "neutral":
        return "neutral"
    try:
        from core.karma_engine import derive_path_from_karma
        path = derive_path_from_karma(int(player_karma or 0))  # righteous | demonic | rogue
    except Exception:
        return "neutral"
    if path == alignment:
        return "aligned"
    opposite = {"righteous": "demonic", "demonic": "righteous"}.get(alignment)
    if path == opposite:
        return "opposed"
    return "neutral"


# ── DISCLOSURE (Lei §1): what awakens in the new world (teaser only, no mechanic). ──
# Fase 2 note: the caverns/matrices teasers GRADUATED to live features
# (/caverna + /formacoes, 🏯 mini-app) — replaced by the next wave's teasers:
# World Boss per continent + Demon Tide, Rivalry Events (sect feuds), the
# per-continent content hard-gate, and [jogador]' CULTIVABLE realms (vision §6.5:
# nodes like Tribulation Ground / Dao Origin with their own cultivation
# risk/reward triggers). PvP/dungeons→nodes/techniques stay (still wipe-bound).
NEW_WORLD_TEASERS = [
    {"key": "pvp",        "emoji": "⚔️", "title_key": "explore_teaser_pvp_title",        "body_key": "explore_teaser_pvp_body"},
    {"key": "worldboss",  "emoji": "🐉", "title_key": "explore_teaser_worldboss_title",  "body_key": "explore_teaser_worldboss_body"},
    {"key": "rivalry",    "emoji": "🔥", "title_key": "explore_teaser_rivalry_title",    "body_key": "explore_teaser_rivalry_body"},
    {"key": "cultivable", "emoji": "⛩️", "title_key": "explore_teaser_cultivable_title", "body_key": "explore_teaser_cultivable_body"},
    {"key": "hardgate",   "emoji": "🌍", "title_key": "explore_teaser_hardgate_title",   "body_key": "explore_teaser_hardgate_body"},
    {"key": "dungeons",   "emoji": "🗺️", "title_key": "explore_teaser_dungeons_title",   "body_key": "explore_teaser_dungeons_body"},
    {"key": "techniques", "emoji": "📜", "title_key": "explore_teaser_techniques_title", "body_key": "explore_teaser_techniques_body"},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _player_continent(player) -> str:
    c = getattr(player, "current_continent", None)
    return c if is_valid_continent(c) else DEFAULT_SPAWN_CONTINENT


def get_continent_node_ids(continent: str) -> list:
    return list(EXPLORATION_NODES.get(continent) or [])


def _difficulty_for_depth(depth: int) -> str:
    d = int(depth or 0)
    if d < 3:
        return "easy"
    if d < 6:
        return "normal"
    if d < 10:
        return "hard"
    return "nightmare"


_DIFF_ORDER = ["easy", "normal", "hard", "nightmare"]


def _bump_diff(diff: str) -> str:
    i = _DIFF_ORDER.index(diff) if diff in _DIFF_ORDER else 1
    return _DIFF_ORDER[min(i + 1, len(_DIFF_ORDER) - 1)]


def _fight_diff(diff: str, realm) -> str:
    """Fase 2 item F — newbie protection: realm ≤ EXPLORE_LOW_REALM_PROTECT
    fights ONE step easier (never below easy). Applies to the FIGHT only —
    loot difficulty is untouched (nobody's drops get nerfed)."""
    if int(realm or 0) > EXPLORE_LOW_REALM_PROTECT:
        return diff
    i = _DIFF_ORDER.index(diff) if diff in _DIFF_ORDER else 1
    return _DIFF_ORDER[max(0, i - 1)]


async def _explore_mods(session, player) -> dict:
    """Fase 2 — the Formação effects exploration consumes (defensive, never
    raises): ``protection`` (fraction of the death-loss prevented) and
    ``perception_mult`` (Divine Sense clarity). See formation_engine."""
    try:
        from core.formation_engine import get_exploration_mods
        return await get_exploration_mods(session, player.telegram_id)
    except Exception:
        logger.exception("explore mods failed (player=%s)", getattr(player, "telegram_id", "?"))
        return {"protection": 0.0, "perception_mult": 1.0}


def _eff_perception(player, mods: dict) -> int:
    return int(int(player.perception or 0) * float(mods.get("perception_mult", 1.0) or 1.0))


def _death_survivors(bag: dict, protection: float) -> dict:
    """Protection-aware death penalty. Base keeps 10% (the dungeon
    ``_lose_90_percent`` contract); an active Véu (explore_protection buff)
    PREVENTS that fraction of the loss: keep = 10% + 90%·protection.
    Mirrors ``_lose_90_percent``'s shape rules exactly (qi_pill_id is a tier
    marker carried verbatim; non-numeric extras are lost on death)."""
    p = max(0.0, min(1.0, float(protection or 0.0)))
    if p <= 0.0:
        from handlers.dungeons import _lose_90_percent
        return _lose_90_percent(bag or {})
    keep = 0.10 + 0.90 * p
    result = {}
    for key, val in (bag or {}).items():
        if key in ("herbs", "ores", "healing_pills") and isinstance(val, dict):
            result[key] = {}
            for item_id, qty in val.items():
                kept = max(0, int(qty * keep))
                if kept:
                    result[key][item_id] = kept
        elif key == "qi_pill_id":
            result[key] = val
        elif isinstance(val, (int, float)):
            kept = max(0, int(val * keep))
            if kept:
                result[key] = kept
    return result


def _qi_cost(node_min_realm: int, depth: int, realm: int) -> int:
    base = EXPLORE_QI_BASE + int(node_min_realm or 0) * 3 + int(depth or 0) * 2
    return max(1, int(base * (1 + max(0, int(realm or 0)) * 0.05)))


def _sanitize_pool(drops: dict) -> dict:
    """Copy a dungeon drop pool but STRIP the technique-scroll and dao-fragment
    faucets — exploration loot is MATERIALS only (Lei §5: never thicken the
    scroll economy; technique reorg is the wipe)."""
    pool = dict(drops or {})
    pool.pop("scroll_chance", None)
    pool.pop("dao_fragment_chance", None)
    return pool


def _bag_nonempty(bag: dict) -> bool:
    bag = bag or {}
    if int(bag.get("stones", 0) or 0) > 0:
        return True
    for k in ("herbs", "ores", "healing_pills"):
        if bag.get(k):
            return True
    if int(bag.get("qi_pills", 0) or 0) > 0:
        return True
    return False


def _qi_gate(player, cost: int):
    if float(player.qi or 0) < cost:
        return {"ok": False, "reason": "qi_insufficient", "qi_cost": int(cost), "qi": float(player.qi or 0)}
    return None


def _charge_qi(player, cost: int) -> None:
    player.qi = max(0.0, float(player.qi or 0) - int(cost))


def _cooldown_remaining_ms(exp) -> int:
    if EXPLORE_COOLDOWN_SECONDS <= 0 or exp is None or exp.last_explore_at is None:
        return 0
    elapsed = (_now() - exp.last_explore_at).total_seconds()
    return max(0, int((EXPLORE_COOLDOWN_SECONDS - elapsed) * 1000))


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def _get_state(session, player_id: int):
    return (await session.execute(
        select(PlayerExploration).where(PlayerExploration.player_id == int(player_id))
    )).scalar_one_or_none()


async def _load_continent_nodes(session, continent: str) -> list:
    # MV-3 §0.1 — harmonização gated com a geografia canónica do MV-1: com
    # `dungeons_regionais` ON, os nós de explore leem a MESMA âncora
    # `DungeonCatalog.continent` (dungeons não-ancoradas NULL aparecem em todo
    # lado, semântica MV-1); OFF → EXPLORATION_NODES de hoje, byte-idêntico
    # (a tabela hardcoded diverge em ~8 ids mas está LIVE em main). Fail-safe:
    # qualquer erro cai no caminho legado. Ordem por id = determinística
    # (scan_directions é seeded por (player, continente, depth)).
    try:
        from core.dungeon_regions import regionais_on
        if regionais_on():
            rows = (await session.execute(
                select(DungeonCatalog).where(
                    (DungeonCatalog.continent == continent)
                    | (DungeonCatalog.continent.is_(None))
                ).order_by(DungeonCatalog.id)
            )).scalars().all()
            return [{
                "id": int(r.id), "name": r.name, "emoji": r.emoji,
                "min_realm": int(r.min_realm or 0), "drops": r.drops or {},
                "qi_cost": int(r.qi_cost_per_floor or 5),
            } for r in rows]
    except Exception:
        logger.exception("regional node override failed — falling back to legacy map")
    ids = get_continent_node_ids(continent)
    if not ids:
        return []
    rows = (await session.execute(
        select(DungeonCatalog).where(DungeonCatalog.id.in_(ids))
    )).scalars().all()
    by_id = {r.id: r for r in rows}
    nodes = []
    for nid in ids:  # preserve EXPLORATION_NODES order
        r = by_id.get(nid)
        if not r:
            continue
        nodes.append({
            "id": int(r.id), "name": r.name, "emoji": r.emoji,
            "min_realm": int(r.min_realm or 0), "drops": r.drops or {},
            "qi_cost": int(r.qi_cost_per_floor or 5),
        })
    return nodes


async def _load_node(session, node_id: int):
    r = (await session.execute(
        select(DungeonCatalog).where(DungeonCatalog.id == int(node_id))
    )).scalar_one_or_none()
    if not r:
        return None
    return {"id": int(r.id), "name": r.name, "emoji": r.emoji,
            "min_realm": int(r.min_realm or 0), "drops": r.drops or {}}


async def _project_bag(session, bag: dict, lang: str = "pt") -> dict:
    """Resolve a bag's item ids to display names (materials only)."""
    bag = bag or {}
    items = []
    if bag.get("herbs") or bag.get("ores"):
        from handlers.dungeons import _load_item_names
        herb_names, ore_names = await _load_item_names(session)
    else:
        herb_names, ore_names = {}, {}
    for hid, qty in (bag.get("herbs") or {}).items():
        items.append({"name": herb_names.get(str(hid), f"Herb #{hid}"), "qty": int(qty)})
    for oid, qty in (bag.get("ores") or {}).items():
        items.append({"name": ore_names.get(str(oid), f"Ore #{oid}"), "qty": int(qty)})

    pill_ids = [int(x) for x in (bag.get("healing_pills") or {}).keys()]
    if int(bag.get("qi_pills", 0) or 0) > 0:
        pill_ids.append(int(bag.get("qi_pill_id", 6) or 6))
    if pill_ids:
        from database.models import PillCatalog
        rows = (await session.execute(
            select(PillCatalog).where(PillCatalog.id.in_(pill_ids))
        )).scalars().all()
        pname = {p.id: f"{getattr(p, 'emoji', '') or ''} {p.name}".strip() for p in rows}
        for pid, qty in (bag.get("healing_pills") or {}).items():
            items.append({"name": pname.get(int(pid), f"Pill #{pid}"), "qty": int(qty)})
        if int(bag.get("qi_pills", 0) or 0) > 0:
            qpid = int(bag.get("qi_pill_id", 6) or 6)
            items.append({"name": pname.get(qpid, f"Pill #{qpid}"), "qty": int(bag.get("qi_pills"))})

    return {"stones": int(bag.get("stones", 0) or 0), "items": items,
            "total_items": sum(int(i["qty"]) for i in items)}


async def _transfer_bag(session, player, bag: dict) -> None:
    from handlers.dungeons import _transfer_bag_to_inventory
    await _transfer_bag_to_inventory(session, player, bag or {})


def _roll_node_loot(node: dict, depth: int) -> dict:
    from handlers.dungeons import _roll_floor_loot
    diff = _difficulty_for_depth(depth)
    return _roll_floor_loot(_sanitize_pool(node.get("drops") or {}), diff, int(node.get("min_realm", 0)))


def _merge(existing: dict, new_loot: dict) -> dict:
    from handlers.dungeons import _merge_bag
    return _merge_bag(existing or {}, new_loot or {})


# ── Projection ─────────────────────────────────────────────────────────────────

def _hp_pair(player, max_hp=None) -> tuple[float, float]:
    """Current/max HP for the explore HUD. [jogador] (09.06) asked for "a tela com
    a vida do personagem… pra ter noção do quanto podemos explorar" — exposing
    HP lets the player judge when to take Safe Return before a Hidden Monster /
    trash floor kills them (the Fase 1 risk loop). Reuses the SAME combat-model
    HP the duels/dungeons use (`get_current_hp` already gates _resolve_trash /
    _resolve_hidden). Onda B (A Alma do Cultivador): the async caller passes the
    Alma's ``max_hp`` (== the arena when combate_unificado ON; raw on OFF) so the
    explore HUD shows the SAME HP as everywhere else; current is clamped to it.
    Defensive: never raises — falls back to (0,0) so the bar renders empty rather
    than breaking scan/advance."""
    try:
        from core.combat_engine import get_max_hp
        from core.cultivator_soul import soul_current_hp
        if max_hp is None:
            max_hp = get_max_hp(player)
        max_hp = float(max_hp)
        return soul_current_hp(player, max_hp), max_hp
    except Exception:
        logger.exception("explore _hp_pair failed (player=%s)", getattr(player, "telegram_id", "?"))
        return 0.0, 0.0


async def project_state(session, exp, player, lang: str = "pt") -> dict:
    continent = _player_continent(player)
    on_continent = bool(exp and exp.continent_key == continent)
    bag = (exp.bag if on_continent else {}) or {}
    from core.cultivator_soul import soul_max_hp
    cur_hp, max_hp = _hp_pair(player, await soul_max_hp(session, player))
    return {
        "continent": continent,
        "depth": int(exp.depth) if on_continent else 0,
        "bag": await _project_bag(session, bag, lang),
        "has_bag": _bag_nonempty(bag),
        "qi": float(player.qi or 0),
        "current_hp": cur_hp,
        "hp_max": max_hp,
        "cooldown_remaining_ms": _cooldown_remaining_ms(exp if on_continent else None),
    }


def _project_direction(d: dict, node_by_id: dict, player, depth: int) -> dict:
    node = node_by_id.get(d["node_id"]) or {}
    mult = EXPLORE_HIDDEN_QI_MULT if d["type"] in ("hidden", "mythic") else 1.0
    qi_cost = int(_qi_cost(node.get("min_realm", 0), depth, player.realm) * mult)
    out = {
        "idx": d["idx"],
        "node_id": d["node_id"],
        "node_name": node.get("name"),
        "node_emoji": node.get("emoji"),
        "node_min_realm": int(node.get("min_realm", 0)),
        "type": d["type"],
        "risk": d["risk"],
        "risk_key": f"explore_risk_{d['risk']}",
        "emoji": d["emoji"],
        "clue_key": f"explore_clue_{d['type']}_{d['clue_variant']}",
        "qi_cost": qi_cost,
        "is_fork": d["type"] == "fork",
        "is_hidden": d["type"] == "hidden",
        "is_mythic": d["type"] == "mythic",
    }
    if d.get("fork_key"):
        out["fork_key"] = d["fork_key"]
    if d.get("mythic_key"):
        out["mythic_key"] = d["mythic_key"]
        out["mythic_emoji"] = MYTHIC_ECHOES.get(d["mythic_key"], {}).get("emoji", "👁️‍🗨️")
    return out


# ── READ — scan (Divine Sense) ─────────────────────────────────────────────────

async def scan(session, player, *, lang: str = "pt") -> dict:
    """READ — the Divine Sense reading: 3..5 directional clues + the bag + the
    new-world disclosure. No state change."""
    continent = _player_continent(player)
    exp = await _get_state(session, player.telegram_id)
    on_continent = bool(exp and exp.continent_key == continent)
    depth = int(exp.depth) if on_continent else 0
    nodes = await _load_continent_nodes(session, continent)
    node_by_id = {n["id"]: n for n in nodes}
    # Fase 2 — active Formação mods: clarity raises the EFFECTIVE perception
    # (more clues), protection is surfaced for the HUD (Lei §1 — the player
    # SEES the Véu working). advance() recomputes the same mods so the clue
    # picked resolves to the clue shown.
    mods = await _explore_mods(session, player)
    eff_perception = _eff_perception(player, mods)
    raw = scan_directions(
        player_id=player.telegram_id, perception=eff_perception, luck=player.luck,
        realm=player.realm, continent=continent, depth=depth,
        nodes=[{"id": n["id"], "min_realm": n["min_realm"]} for n in nodes],
        fork_keys=list(EXPLORE_FORKS.keys()),
        mythic_keys=list(MYTHIC_ECHOES.keys()),
    )
    directions = [_project_direction(d, node_by_id, player, depth) for d in raw]
    bag = (exp.bag if on_continent else {}) or {}
    # Onda E — the HUD's own-stat badges (👁️ perception / 🍀 luck) read the Alma-effective
    # values (== the profile) when combate_unificado ON; OFF → raw (byte-identical). ONE
    # snapshot, reused for HP. The scan mechanic above still uses the situational
    # eff_perception (formation clarity) — a temporary explore buff, not the base stat.
    from database.db import feature_enabled_for_world as _ffe_ex
    _cu_ex = bool(_ffe_ex("combate_unificado"))
    if _cu_ex:
        from core.cultivator_soul import compute_cultivator_soul
        _exs = await compute_cultivator_soul(session, player)
        _ex_max_hp = float(_exs["max_hp"])
        _disp_perc = int(_exs["perception"])
        _disp_luck = int(_exs["luck"])
    else:
        from core.cultivator_soul import soul_max_hp
        _ex_max_hp = await soul_max_hp(session, player)
        _disp_perc = int(player.perception or 0)
        _disp_luck = int(player.luck or 0)
    cur_hp, max_hp = _hp_pair(player, _ex_max_hp)
    return {
        "ok": True,
        "continent": continent,
        "depth": depth,
        "directions": directions,
        "bag": await _project_bag(session, bag, lang),
        "has_bag": _bag_nonempty(bag),
        "qi": float(player.qi or 0),
        "current_hp": cur_hp,
        "hp_max": max_hp,
        "perception": _disp_perc,
        "effective_perception": (_disp_perc if _cu_ex else eff_perception),
        "luck": _disp_luck,
        "protection": float(mods.get("protection", 0.0) or 0.0),
        "cooldown_remaining_ms": _cooldown_remaining_ms(exp if on_continent else None),
        "teasers": NEW_WORLD_TEASERS,
    }


# ── WRITE — advance (resolve a direction) ──────────────────────────────────────

async def _ensure_expedition(session, player, continent):
    """Lock-or-create the per-player expedition row, normalised to the player's
    CURRENT continent. If the player travelled mid-expedition the old bag is
    BANKED (never silently lost — Lei §1/§4) and the expedition resets."""
    exp = (await session.execute(
        select(PlayerExploration).where(PlayerExploration.player_id == player.telegram_id).with_for_update()
    )).scalar_one_or_none()
    banked = None
    if exp is None:
        exp = PlayerExploration(player_id=player.telegram_id, continent_key=continent,
                                depth=0, bag={}, started_at=_now())
        session.add(exp)
        await session.flush()
    elif exp.continent_key != continent:
        if _bag_nonempty(exp.bag or {}):
            banked = await _project_bag(session, exp.bag or {}, getattr(player, "language", "pt") or "pt")
            await _transfer_bag(session, player, exp.bag or {})
        exp.continent_key = continent
        exp.depth = 0
        exp.bag = {}
        exp.started_at = _now()
    return exp, banked


async def advance(session, player, *, direction_idx, expected_depth=None,
                  choice_id=None, lang: str = "pt", realm_label=None,
                  allow_duel=True) -> dict:
    """WRITE — resolve the chosen direction at the current depth. The caller
    row-locks ``player`` FOR UPDATE and owns the commit. Idempotent via the
    optimistic ``expected_depth`` check + the duel/marker discipline.

    ``allow_duel`` — when True (mini-app, canonical) a Hidden Monster starts an
    interactive duel (DuelArenaModal). When False (chat, the simplified legacy
    door) it auto-resolves as a tougher fight, since chat has no live arena."""
    continent = _player_continent(player)
    exp, banked = await _ensure_expedition(session, player, continent)

    # Own cooldown (never shared with farm).
    cd_ms = _cooldown_remaining_ms(exp)
    if cd_ms > 0:
        return {"ok": False, "reason": "cooldown", "cooldown_remaining_ms": cd_ms,
                "state": await project_state(session, exp, player, lang)}

    # If a Hidden-Monster duel is still unsettled, you can't advance ANY
    # direction (else depth/bag would double-move when it settles). Redirect to
    # the in-flight duel instead — idempotent (covers every encounter type, not
    # just a re-tapped hidden one).
    open_duel = await _open_exploration_duel(session, player.telegram_id)
    if open_duel is not None:
        out = {"ok": True, "redirect_to_duel": True, "duel_id": str(open_duel.id),
               "state": await project_state(session, exp, player, lang)}
        if banked is not None:
            out["banked"] = banked
        return out

    # Idempotency — a stale/retried request (depth already moved) is a no-op.
    if expected_depth is not None and int(exp.depth) != int(expected_depth):
        return {"ok": False, "reason": "stale", "banked": banked,
                "state": await project_state(session, exp, player, lang)}

    nodes = await _load_continent_nodes(session, continent)
    if not nodes:
        return {"ok": False, "reason": "no_nodes", "state": await project_state(session, exp, player, lang)}
    node_by_id = {n["id"]: n for n in nodes}
    # Same effective perception as scan() — the clue picked resolves to the
    # clue shown. (If a clarity buff expired in between, the direction count
    # can shrink and a tail idx returns invalid_direction — honest, rescan.)
    mods = await _explore_mods(session, player)
    raw = scan_directions(
        player_id=player.telegram_id, perception=_eff_perception(player, mods), luck=player.luck,
        realm=player.realm, continent=continent, depth=int(exp.depth),
        nodes=[{"id": n["id"], "min_realm": n["min_realm"]} for n in nodes],
        fork_keys=list(EXPLORE_FORKS.keys()),
        mythic_keys=list(MYTHIC_ECHOES.keys()),
    )
    try:
        idx = int(direction_idx)
    except (TypeError, ValueError):
        idx = -1
    if idx < 0 or idx >= len(raw):
        return {"ok": False, "reason": "invalid_direction",
                "state": await project_state(session, exp, player, lang)}
    d = raw[idx]
    node = node_by_id.get(d["node_id"]) or {}
    etype = d["type"]

    if etype == "cache":
        out = await _resolve_cache(session, player, exp, node, lang)
    elif etype == "fork":
        out = await _resolve_fork(session, player, exp, node, d, choice_id, lang)
    elif etype == "mythic":
        if allow_duel:
            out = await _resolve_mythic(session, player, exp, node, d, continent, lang, realm_label)
        else:
            # Chat (no live arena) — auto-resolve the Mythic Echo as a tough fight.
            out = await _resolve_mythic_chat(session, player, exp, node, d, continent, lang)
    elif etype == "hidden":
        if allow_duel:
            out = await _resolve_hidden(session, player, exp, node, d, continent, lang, realm_label)
        else:
            # Chat (no live arena) — auto-resolve the Hidden Monster as a tough fight.
            out = await _resolve_trash(session, player, exp, node, lang, tougher=True)
    else:  # trash (default)
        out = await _resolve_trash(session, player, exp, node, lang)

    if banked is not None and isinstance(out, dict):
        out["banked"] = banked

    # MV-5 — o encontro raro do EXPLORE: depois de um avanço RESOLVIDO (não um
    # redirect de duelo nem uma recusa), alguém pode te achar na mata — chance
    # pequena, e o pacer do engine (1 oferta + cooldown 12h) morde em cima.
    # Deliberadamente um gancho pós-resolve, NÃO um etype novo no
    # scan_directions: o stream de rng do scan é type-independent por contrato
    # (scan e advance nunca podem divergir) e um slot novo lá arriscaria isso.
    # Aditivo + flag-gated (OFF → zero rolls, zero queries); nunca levanta.
    try:
        if isinstance(out, dict) and out.get("resolved"):
            from core.storylet_engine import quests_vivas_on, maybe_offer, STORYLET_EXPLORE_CHANCE
            if quests_vivas_on() and random.random() < STORYLET_EXPLORE_CHANCE:
                offer = await maybe_offer(session, player, source="explore")
                if offer:
                    out["storylet_offer"] = offer
    except Exception:
        logger.debug("storylet explore offer failed", exc_info=True)

    # MV-8 — a EMBOSCADA. MESMO ponto pós-resolve e MESMO gate `resolved`: isso
    # garante POR CONSTRUÇÃO que o encontro nunca cai em cima de um duelo
    # hidden/mythic já aberto (os dois ramos de redirect não trazem "resolved").
    # E é um ENCONTRO, nunca um duelo: `ambush_offer` só devolve payload — quem
    # cria duelo é o tap do jogador em ⚔️ (Lei §1: no forced losses).
    # Flag OFF → None sem UMA query → key ausente → payload byte-idêntico.
    try:
        if isinstance(out, dict) and out.get("resolved"):
            from core.jianghu_engine import ambush_offer
            ambush = await ambush_offer(session, player, source="explore", lang=lang)
            if ambush:
                out["jianghu_ambush"] = ambush
    except Exception:
        logger.debug("jianghu ambush explore offer failed", exc_info=True)
    return out


async def _resolve_cache(session, player, exp, node, lang) -> dict:
    cost = _qi_cost(node.get("min_realm", 0), exp.depth, player.realm)
    gate = _qi_gate(player, cost)
    if gate:
        return gate
    _charge_qi(player, cost)
    gained = _roll_node_loot(node, exp.depth)
    exp.bag = _merge(exp.bag or {}, gained)
    _flag_bag(exp)
    exp.depth = int(exp.depth) + 1
    exp.last_explore_at = _now()
    return {"ok": True, "resolved": True, "type": "cache", "qi_cost": int(cost),
            "gained": await _project_bag(session, gained, lang),
            "state": await project_state(session, exp, player, lang)}


async def _resolve_trash(session, player, exp, node, lang, tougher=False) -> dict:
    from core.combat_engine import build_player_combat_fighter, generate_npc_fighter, simulate_combat, get_current_hp

    if get_current_hp(player) <= 0:
        return {"ok": False, "reason": "hp_depleted", "state": await project_state(session, exp, player, lang)}

    cost = _qi_cost(node.get("min_realm", 0), exp.depth, player.realm)
    gate = _qi_gate(player, cost)
    if gate:
        return gate
    _charge_qi(player, cost)
    exp.last_explore_at = _now()

    diff = _difficulty_for_depth(exp.depth)
    if tougher:
        diff = _bump_diff(diff)
    # MV-3 — Estados Regionais: continente tenso/sitiado = explore +1 degrau
    # de dificuldade NA LUTA (loot intocado — risco sobe, recompensa não;
    # Lei §13). Gated `estados_regionais` + fail-safe 0; a proteção de
    # novato (_fight_diff) continua a aplicar-se DEPOIS do bump.
    try:
        from core.region_state_engine import explore_risk_bump
        for _ in range(await explore_risk_bump(session, player)):
            diff = _bump_diff(diff)
    except Exception:
        logger.debug("region risk bump failed", exc_info=True)
    fighter = await build_player_combat_fighter(session, player, lang=lang)
    # Item F: low realms fight one step easier (loot difficulty untouched).
    npc = generate_npc_fighter(difficulty=_fight_diff(diff, player.realm),
                               player_realm=int(player.realm or 0), lang=lang)
    result = simulate_combat(fighter, npc, mode="dungeon")
    won = result.get("winner") == "attacker"

    if won:
        gained = _roll_node_loot(node, exp.depth)
        exp.bag = _merge(exp.bag or {}, gained)
        _flag_bag(exp)
        exp.depth = int(exp.depth) + 1
        # MV-2 — Tiandao: a vitória de superfície conta para a Maré de Bestas
        # (gated + fail-safe; o explore nunca quebra por causa do evento).
        _wev = None
        try:
            from core.tiandao_engine import record_pve_victory
            _wev = await record_pve_victory(session, player)
        except Exception:
            logger.debug("tiandao explore hook failed", exc_info=True)
        return {"ok": True, "resolved": True, "type": "trash", "won": True, "qi_cost": int(cost),
                "gained": await _project_bag(session, gained, lang),
                **({"world_event": _wev} if _wev else {}),
                "state": await project_state(session, exp, player, lang)}
    # Died deep — lose 90% (less if a Véu / explore_protection Formação is
    # active — Fase 2), bank the survivors, reset the expedition.
    mods = await _explore_mods(session, player)
    survivors = _death_survivors(exp.bag or {}, mods.get("protection", 0.0))
    await _transfer_bag(session, player, survivors)
    exp.bag = {}
    _flag_bag(exp)
    exp.depth = 0
    return {"ok": True, "resolved": True, "type": "trash", "won": False, "died": True, "qi_cost": int(cost),
            "protection": float(mods.get("protection", 0.0) or 0.0),
            "survivors": await _project_bag(session, survivors, lang),
            "state": await project_state(session, exp, player, lang)}


async def _resolve_fork(session, player, exp, node, d, choice_id, lang) -> dict:
    fork_key = d.get("fork_key")
    fork = EXPLORE_FORKS.get(fork_key)
    if not fork:
        # No template resolved — degrade to a safe cache (never crash — Lei §1).
        return await _resolve_cache(session, player, exp, node, lang)
    choices = fork["choices"]
    if not choice_id:
        return {
            "ok": True, "needs_choice": True, "type": "fork", "fork_key": fork_key,
            "prompt_key": f"explore_fork_{fork_key}_prompt",
            "node_name": node.get("name"), "node_emoji": node.get("emoji"),
            "choices": [{
                "id": c["id"],
                "label_key": f"explore_fork_{fork_key}_{c['id']}",
                "result_key": f"explore_fork_{fork_key}_{c['id']}_result",
                "karma_delta": int(c["karma_delta"]),
            } for c in choices],
        }
    chosen = next((c for c in choices if c["id"] == choice_id), None)
    if chosen is None:
        return {"ok": False, "reason": "invalid_choice",
                "state": await project_state(session, exp, player, lang)}

    cost = _qi_cost(node.get("min_realm", 0), exp.depth, player.realm)
    gate = _qi_gate(player, cost)
    if gate:
        return gate
    _charge_qi(player, cost)

    gained = {}
    for _ in range(max(1, int(chosen.get("rolls", 1)))):
        gained = _merge(gained, _roll_node_loot(node, exp.depth))
    if gained.get("stones"):
        gained["stones"] = int(gained["stones"] * float(chosen.get("stones_mult", 1.0)))
    exp.bag = _merge(exp.bag or {}, gained)
    _flag_bag(exp)
    exp.depth = int(exp.depth) + 1
    exp.last_explore_at = _now()

    karma_result = {}
    kd = int(chosen.get("karma_delta", 0))
    if kd != 0:
        try:
            from core.karma_engine import apply_karma
            karma_result = await apply_karma(
                session, player.telegram_id, "exploration_fork",
                metadata={"fork": fork_key, "choice": choice_id, "node_id": int(node.get("id", 0))},
                delta_override=kd,
            )
        except Exception:
            logger.exception("exploration fork karma failed (player=%s)", player.telegram_id)

    return {"ok": True, "resolved": True, "type": "fork", "fork_key": fork_key,
            "choice_id": choice_id, "qi_cost": int(cost),
            "result_key": f"explore_fork_{fork_key}_{choice_id}_result",
            "gained": await _project_bag(session, gained, lang), "karma": karma_result,
            "state": await project_state(session, exp, player, lang)}


async def _open_exploration_duel(session, player_id):
    """Return the player's UNSETTLED exploration duel (live OR terminal-but-not-
    yet-settled), or None.

    Settlement runs LAZILY on the duel_state poll, so a duel that a round/accept
    timeout already drove to 'finished'/'forfeited' is STILL blocking until the
    pve_settled marker lands — otherwise advancing/retreating here would
    double-move depth/bag when that orphan finally settles (the original
    blocker). We deliberately do NOT settle inline: advance/retreat already hold
    the player row FOR UPDATE while the settle path locks duel -> player ->
    exploration, so settling here would invert the order and deadlock. Instead
    the caller redirects the client to the duel (which settles it on the
    duel-locked poll path), and the scheduler safety-net
    (sweep_orphan_exploration_duels) settles ones the client never polls."""
    from database.models import DuelSession
    from core.pve_duel_settle import _already_settled
    rows = (await session.execute(
        select(DuelSession).where(
            DuelSession.attacker_id == int(player_id),
            DuelSession.pve_source == "exploration",
            DuelSession.state.in_(["waiting_actions", "pending_acceptance", "finished", "forfeited"]),
        ).order_by(DuelSession.id.desc()).limit(8)
    )).scalars().all()
    for d in rows:
        if not _already_settled(d):
            return d
    return None


async def sweep_orphan_exploration_duels(session) -> int:
    """DEPRECADO desde 2026-09-04 — delega em `sweep_orphan_pve_duels`.

    ⚠️ Este varredor era um de TRES, cada um a nomear a SUA fonte, enquanto o
    codigo cria DEZ. Sete familias ficaram anos sem rede — entre elas a maior do
    jogo (`arena_npc_fallback`) e o proprio default de `start_duel_pve`
    (`npc_hunt`). Resultado medido a 2026-09-03: 27 duelos expirados a prender
    13 jogadores, o mais antigo ha' 103 dias.

    Fica como nome, nao como segunda implementacao: duas copias da mesma
    varredura divergem no primeiro fix que so' uma delas recebe. O scheduler
    chama a familia inteira, uma vez.
    """
    from core.duel_engine import sweep_orphan_pve_duels
    return await sweep_orphan_pve_duels(session)
async def _pick_hidden_npc(session, player, continent):
    """Continent-STRICT pick of an active NPC Cultivator within ±window realms
    (the Hidden Monster belongs to THIS realm; no global fallback). Returns the
    ORM row or None (None → honest: no hidden presence here → tough trash)."""
    realm = int(player.realm or 0)
    cand = (await session.execute(
        select(NpcCultivator).where(
            NpcCultivator.status == "active",
            NpcCultivator.continent_key == continent,
            NpcCultivator.realm >= max(0, realm - EXPLORE_NPC_WINDOW),
            NpcCultivator.realm <= realm + EXPLORE_NPC_WINDOW,
        ).limit(40)
    )).scalars().all()
    if not cand:
        return None
    rng = random.Random()
    rng.shuffle(cand)
    cand.sort(key=lambda n: (1 if int(n.realm or 0) > realm else 0, abs(int(n.realm or 0) - realm)))
    return cand[0]


async def _resolve_hidden(session, player, exp, node, d, continent, lang, realm_label) -> dict:
    # The open-duel guard at the top of advance() already guarantees there is no
    # unsettled exploration duel here (it redirects to one if it exists), so we
    # only gate on the combat preconditions and then start the encounter.
    from core.combat_engine import get_current_hp
    from core.npc_cultivator_engine import rehydrate_npc_fighter, project_npc_for_profile
    from core.duel_engine import start_duel_pve

    if get_current_hp(player) <= 0:
        return {"ok": False, "reason": "hp_depleted", "state": await project_state(session, exp, player, lang)}

    npc = await _pick_hidden_npc(session, player, continent)
    if npc is None:
        # No hidden presence in this realm — honest fallback: a tougher trash fight.
        return await _resolve_trash(session, player, exp, node, lang, tougher=True)

    cost = int(_qi_cost(node.get("min_realm", 0), exp.depth, player.realm) * EXPLORE_HIDDEN_QI_MULT)
    gate = _qi_gate(player, cost)
    if gate:
        return gate
    _charge_qi(player, cost)
    exp.last_explore_at = _now()

    fb = rehydrate_npc_fighter(npc)
    duel = await start_duel_pve(
        session, player,
        archetype="npc_cultivator", difficulty="normal",
        source="exploration",
        context={"npc_id": int(npc.id), "continent_key": continent,
                 "node_id": int(node.get("id", 0)), "depth": int(exp.depth)},
        fighter_b_override=fb,
    )
    return {
        "ok": True, "redirect_to_duel": True, "duel_id": str(duel.id), "qi_cost": int(cost),
        "npc": project_npc_for_profile(npc, lang, realm_label=realm_label),
        "state": await project_state(session, exp, player, lang),
    }


# ── Ecos Míticos (Onda 5 Fase 3) — sibling of the Hidden-Monster resolver. ─────

async def _build_mythic_fighter(session, player, eco, stance, continent):
    """Build the mythic fighter_b dict + (optional) the source NPC row.

    REUSE (Lei §3): a doppelgänger mirrors the player via the EXACT Onda 3 echo
    path (``_build_public_fighter`` → ``_anonymize_fighter``) — telegram_id=0 /
    is_npc=True sentinels, intent aura dropped (so the player keeps a real edge →
    winnable-but-hard, no mirror stall). An npc_echo prefers a real continent NPC
    (``rehydrate_npc_fighter``) and falls back to the mirror if none is present
    (honest — never a void). The stance × eco strike scale is applied STRIKE-ONLY
    on combat_profile['faction_dmg'] (NEVER eff_hp/bp — wipe-safe, no balance drift).
    Returns ``(fighter_b, npc_row_or_None)`` or ``(None, None)`` on failure.
    """
    from core.npc_cultivator_engine import (
        _build_public_fighter, _anonymize_fighter, rehydrate_npc_fighter,
    )
    scale = (float(eco.get("power_scale", 1.0))
             * _MYTHIC_STANCE_SCALE.get(stance, 1.0)
             * MYTHIC_DOPPEL_SCALE)
    display = eco.get("display") or (player.dao_name or player.display_name
                                     or getattr(player, "username", None) or "???")

    fb = None
    npc_row = None
    if eco.get("body") == "npc_echo":
        npc_row = await _pick_hidden_npc(session, player, continent)
        if npc_row is not None:
            fb = rehydrate_npc_fighter(npc_row)
    if fb is None:
        # Doppelgänger (the jewel) OR npc_echo with no NPC present → mirror the player.
        pub = await _build_public_fighter(session, player)
        if pub is None:
            return None, None
        fb = _anonymize_fighter(pub, name=display, realm=int(player.realm or 0), sect_id=None)

    fb["name"] = display
    fb["dao_name"] = display
    prof = dict(fb.get("combat_profile") or {})
    if prof and scale != 1.0:
        prof["faction_dmg"] = float(prof.get("faction_dmg", 1.0)) * scale
    fb["combat_profile"] = prof
    return fb, npc_row


def _project_mythic_npc(eco, key, stance, player, npc_row, lang, realm_label) -> dict:
    """The npc payload the mini-app modal reads — anonymized + mythic flavour
    flags. No PII: the doppelgänger shows the player's OWN dao_name back to them
    (telegram_id never leaves; npc_echo rides the PII-safe project_npc_for_profile)."""
    base = {}
    if npc_row is not None:
        try:
            from core.npc_cultivator_engine import project_npc_for_profile
            base = project_npc_for_profile(npc_row, lang, realm_label=realm_label)
        except Exception:
            base = {}
    base["is_mythic"] = True
    base["mythic_key"] = key
    base["is_doppelganger"] = (eco.get("body") == "doppelganger")
    base["karma_stance"] = stance
    base["mythic_emoji"] = eco.get("emoji", "👁️‍🗨️")
    base["mythic_title"] = eco.get("title")
    base["mythic_name_key"] = f"explore_mythic_name_{key}"
    base["mythic_reveal_key"] = f"explore_mythic_reveal_{key}"
    # Arena/display name: the doppelgänger shows YOUR name (the "estás TU" moment).
    base["name"] = (player.dao_name or player.display_name or "???") if eco.get("display") is None else eco["display"]
    return base


async def _resolve_mythic(session, player, exp, node, d, continent, lang, realm_label) -> dict:
    """Mini-app (allow_duel) resolver for a Mythic Echo — sibling of
    ``_resolve_hidden``. Reuses ``start_duel_pve(source='exploration')`` verbatim,
    stamping ``mythic_key`` + ``mythic_stance`` into pve_context so the existing
    open-duel guard / sweep / settle cover it unchanged (no new settle path)."""
    from core.combat_engine import get_current_hp
    from core.duel_engine import start_duel_pve

    if get_current_hp(player) <= 0:
        return {"ok": False, "reason": "hp_depleted", "state": await project_state(session, exp, player, lang)}

    key = d.get("mythic_key")
    eco = MYTHIC_ECHOES.get(key)
    if not eco:
        # Unknown mythic key — degrade to a tougher fight (never crash — Lei §1).
        return await _resolve_trash(session, player, exp, node, lang, tougher=True)

    stance = _mythic_stance(getattr(player, "karma", 0), eco["alignment"])
    # Best-effort (Lei §1 — never crash): if the mirror/echo fighter can't be
    # assembled (e.g. a DB hiccup in the NPC pick), degrade to a tougher fight
    # instead of bubbling a 500 to the player.
    try:
        fb, npc_row = await _build_mythic_fighter(session, player, eco, stance, continent)
    except Exception:
        logger.exception("mythic fighter build failed (player=%s, eco=%s)", player.telegram_id, key)
        fb, npc_row = None, None
    if fb is None:
        return await _resolve_trash(session, player, exp, node, lang, tougher=True)

    cost = int(_qi_cost(node.get("min_realm", 0), exp.depth, player.realm) * EXPLORE_HIDDEN_QI_MULT)
    gate = _qi_gate(player, cost)
    if gate:
        return gate
    _charge_qi(player, cost)
    exp.last_explore_at = _now()

    ctx = {"continent_key": continent, "node_id": int(node.get("id", 0)), "depth": int(exp.depth),
           "mythic_key": key, "mythic_stance": stance}
    if npc_row is not None:
        ctx["npc_id"] = int(npc_row.id)
    duel = await start_duel_pve(
        session, player,
        archetype="npc_cultivator", difficulty="normal",
        source="exploration",
        context=ctx,
        fighter_b_override=fb,
    )
    return {
        "ok": True, "redirect_to_duel": True, "duel_id": str(duel.id), "qi_cost": int(cost),
        "npc": _project_mythic_npc(eco, key, stance, player, npc_row, lang, realm_label),
        "state": await project_state(session, exp, player, lang),
    }


async def _resolve_mythic_chat(session, player, exp, node, d, continent, lang) -> dict:
    """Chat (no live arena) resolver — auto-resolves the Mythic Echo as a tough
    fight (mirrors the Hidden-Monster chat degradation), narrates the reveal, and
    fires the permanent title on a win (idempotent). The cinematic mirror duel
    lives in the mini-app (Lei: mini-app canonical; chat keeps parity, not parity++)."""
    key = d.get("mythic_key")
    eco = MYTHIC_ECHOES.get(key)
    out = await _resolve_trash(session, player, exp, node, lang, tougher=True)
    if eco and isinstance(out, dict) and out.get("ok"):
        out["mythic_key"] = key
        out["mythic_name_key"] = f"explore_mythic_name_{key}"
        out["mythic_reveal_key"] = f"explore_mythic_reveal_{key}"
        out["mythic_title"] = eco.get("title")
        out["is_doppelganger"] = (eco.get("body") == "doppelganger")
        if out.get("won"):
            try:
                from core.achievement_engine import check_achievements
                await check_achievements(session, player.telegram_id, eco["event"], 1)
            except Exception:
                logger.exception("mythic chat title grant failed (player=%s)", player.telegram_id)
    return out


def _flag_bag(exp) -> None:
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(exp, "bag")


# ── WRITE — retreat (safe return: bank 100%) ───────────────────────────────────

async def retreat(session, player, *, lang: str = "pt") -> dict:
    """WRITE — safe return: bank 100% of the expedition bag into the permanent
    inventory and reset depth/bag. Idempotent (empty bag → no-op). Caller
    row-locks ``player`` FOR UPDATE and owns the commit."""
    exp = (await session.execute(
        select(PlayerExploration).where(PlayerExploration.player_id == player.telegram_id).with_for_update()
    )).scalar_one_or_none()
    # Can't bank while a Hidden-Monster duel is unsettled — else the player would
    # de-risk the deep bag (bank 100% now) AND still claim the duel's win loot /
    # dodge the death penalty when it settles. Refuse with a disclosed reason
    # until the duel resolves (the bag stays exposed to the deep-death risk).
    open_duel = await _open_exploration_duel(session, player.telegram_id)
    if open_duel is not None:
        return {"ok": False, "reason": "duel_in_progress", "duel_id": str(open_duel.id),
                "state": await project_state(session, exp, player, lang)}
    if exp is None or not _bag_nonempty(exp.bag or {}):
        return {"ok": True, "retreated": True, "banked": {"stones": 0, "items": [], "total_items": 0},
                "empty": True, "state": await project_state(session, exp, player, lang)}
    banked = exp.bag or {}
    summary = await _project_bag(session, banked, lang)
    await _transfer_bag(session, player, banked)
    exp.bag = {}
    _flag_bag(exp)
    exp.depth = 0
    exp.last_explore_at = _now()
    return {"ok": True, "retreated": True, "banked": summary,
            "state": await project_state(session, exp, player, lang)}


# ── Settle hook — called from pve_duel_settle for pve_source='exploration' ─────

async def resolve_exploration_from_duel(session, duel, player, won: bool) -> dict:
    """Settle-hook resolver for an exploration Hidden-Monster duel. On a WIN,
    grants 5-10× the node loot into the expedition bag and advances depth + flags
    the spare/execute moral fork. On a LOSS (died deep), loses 90% of the bag,
    banks the survivors, and resets the expedition. Idempotency rides on the
    engine-level pve_settled marker (this only mutates on the terminal settle)."""
    ctx = duel.pve_context or {}
    node_id = int(ctx.get("node_id") or 0)
    mythic_key = ctx.get("mythic_key")
    payload = {"exploration": True, "won": bool(won), "offer_moral_choice": bool(won)}

    exp = (await session.execute(
        select(PlayerExploration).where(PlayerExploration.player_id == player.telegram_id).with_for_update()
    )).scalar_one_or_none()
    if exp is None:
        return payload  # expedition vanished (retreat raced) — nothing to settle

    node = await _load_node(session, node_id)
    if won:
        if node:
            rng = random.Random()
            rolls = rng.randint(EXPLORE_HIDDEN_ROLLS_MIN, EXPLORE_HIDDEN_ROLLS_MAX)
            gained = {}
            for _ in range(rolls):
                gained = _merge(gained, _roll_node_loot(node, exp.depth))
            exp.bag = _merge(exp.bag or {}, gained)
            _flag_bag(exp)
            payload["gained"] = await _project_bag(session, gained, getattr(player, "language", "pt") or "pt")
            payload["loot_rolls"] = rolls
        # Ecos Míticos (Onda 5 Fase 3) — the unique, permanent, wipe-safe reward is
        # the COSMETIC TITLE (Lei §4/§5). Fired via the seed-driven achievement bus;
        # idempotent (unlocked_at short-circuit) so a re-poll / sweep double-settle
        # never double-grants. Defensive (mirrors apply_karma): a grant crash never
        # aborts the loot settle.
        eco = MYTHIC_ECHOES.get(mythic_key) if mythic_key else None
        if eco:
            payload["mythic_key"] = mythic_key
            payload["mythic_title"] = eco.get("title")
            try:
                from core.achievement_engine import check_achievements
                await check_achievements(session, player.telegram_id, eco["event"], 1)
            except Exception:
                logger.exception("mythic title grant failed (player=%s, eco=%s)", player.telegram_id, mythic_key)
        exp.depth = int(exp.depth) + 1
        exp.last_explore_at = _now()
    else:
        # Lose 90% — less if a Véu (explore_protection) hums (Fase 2).
        mods = await _explore_mods(session, player)
        survivors = _death_survivors(exp.bag or {}, mods.get("protection", 0.0))
        await _transfer_bag(session, player, survivors)
        exp.bag = {}
        _flag_bag(exp)
        exp.depth = 0
        exp.last_explore_at = _now()
        payload["died"] = True
        payload["protection"] = float(mods.get("protection", 0.0) or 0.0)
        payload["survivors"] = await _project_bag(session, survivors, getattr(player, "language", "pt") or "pt")

    # MV-8 P0 — o gancho do MV-6 que FALTAVA aqui. O Monstro Escondido É um
    # NpcCultivator (`_pick_hidden_npc` seleciona da MESMA tabela), mas só o
    # settle de pve_source='npc_cultivator' alimentava a reputação/o RIVAL —
    # esta era a MAIOR superfície de contato com NPC do jogo e não contava para
    # nada. Prod 2026-08-04 provou o custo: `rival_npc_id IS NOT NULL` = 0 nas
    # DUAS DBs (inclusive no s2 com `reputacao_rival` ON desde 20/07), contra
    # 814 lutas/30d em main e 55/30d em s2 jogadas fora.
    # Aditivo + fail-safe: `on_npc_duel_settled` no-opa (None, sem query) com a
    # flag do MV-6 OFF ⇒ main fica byte-idêntico por construção. O `player` já
    # está FOR UPDATE na sessão do settle. Nunca altera o duelo nem o loot.
    npc_id = ctx.get("npc_id")
    if npc_id is not None:
        try:
            from core.reputation_engine import on_npc_duel_settled
            _mv6 = await on_npc_duel_settled(session, player, npc_id, bool(won))
            if _mv6:
                payload["mv6"] = _mv6
        except Exception:
            logger.exception("resolve_exploration_from_duel: mv6 hook failed (duel=%s)", duel.id)
    return payload
