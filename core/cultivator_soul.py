"""A Alma do Cultivador — the SINGLE canonical source of truth for the player's
effective power / stats / HP.

Owner mandate (2026-07-01, foundational/eternal): there must be ONE truth — the
calculation of everything — where whatever raises power (a Dao Law, an equipment,
an achievement) SUMS into this one source, and the WHOLE game reads from it. No
surface may recompute its own version, so the same cultivator never shows two
different numbers (the bug: HP in the arena != HP in the profile).

Design + rollout: Cerebro/Nivrael/ALMA_DO_CULTIVADOR.md
Generalizes: Combate Unificado (combat reads effective) + Progressão Visível
(the one aggregated Poder de Combate) — extends that SAME truth to HP + every
attribute + every surface.

Contract:
  - ``build_soul_snapshot`` — the pure (sync) core. Given the player + already
    fetched modifiers + the two feature flags, returns the canonical snapshot.
    Computes each field to MATCH the canonical/combat path (so the profile HP ==
    the arena HP, the /combate preview == the actual strike). Folds every
    modifier EXACTLY ONCE (the tempering² trap is defended by unified_combat_hp).
  - ``load_cultivator_modifiers`` — async; fetches the modifier stack once.
  - ``compute_cultivator_soul`` — async wrapper (fetch + build). What surfaces call.

Gating (so ``main`` / the 57 stay byte-identical until a world flips the flags):
  - combate_unificado OFF  → max_hp = calculate_hp (RAW), attributes RAW, integer realm.
  - combate_unificado ON   → max_hp = unified_combat_hp (EFFECTIVE), attributes effective, fractional realm.
  - progressao_visivel OFF → display_power = RAW battle_power.
  - progressao_visivel ON  → display_power = display_combat_power (aggregated).
  - qi_capacity is ALWAYS the effective cap (get_effective_qi_capacity) — matches
    what api_player already emits on main (honest since the 2026-05-10 hotfix).

No migration (everything computed). Wipe-safe (Lei §5).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_soul_snapshot(
    player, *,
    equip_stats: dict | None = None,
    companion_bonus: dict | None = None,
    dao_bonuses: dict | None = None,
    interior_bonuses: dict | None = None,
    achievement_mults: dict | None = None,
    faction_bonuses: dict | None = None,
    qi_capacity_eff: float | None = None,
    unified: bool = False,
    visible: bool = False,
) -> dict:
    """The pure core — compute the canonical snapshot from PRE-FETCHED modifiers.

    Sync + no I/O so chat handlers (which pre-load the modifiers) and the async
    wrapper share ONE computation. Every field is computed to match the surface
    that already "owns" that number:
      - ``max_hp``          → matches the arena (build_fighter_data: unified_combat_hp
                              on the CLEAN stats + companion hp_mult + faction foundation).
      - ``display_power``   → matches the header (display_combat_power).
      - ``battle_power_strike`` → the CLEAN bp that feeds the actual strike (for the
                              honest /combate preview — no Dao bp_mult here; that rides
                              the dao_index apex separately, exactly like combat).
      - ``soul_strength/perception/luck`` → the EFFECTIVE attributes (full Dao).
      - ``qi_capacity``     → the effective cap.
    """
    from core.game_logic import calculate_total_stats, display_combat_power
    from core.combat_engine import calculate_hp, unified_combat_hp

    realm = int(player.realm or 0)
    sub = int(getattr(player, "sub_layer", 1) or 1)
    _ach_bp = float((achievement_mults or {}).get("bp_mult", 1.0) or 1.0)

    # ── effective stat block (full Dao) — the player's real attributes ──
    total = None
    if unified or visible:
        total = calculate_total_stats(
            player, equip_stats, companion_bonus, dao_bonuses,
            interior_bonuses=interior_bonuses, achievement_bp_mult=_ach_bp,
        )

    if unified:
        from config import SUB_LAYERS_PER_REALM as _SLPR
        _sl = min(max(sub, 1), _SLPR)
        realm_eff = realm + (_sl - 1) / _SLPR
        # CLEAN stats (Dao bp_mult stripped → it rides the dao_index apex for the
        # strike, never the HP pool) — this is EXACTLY the bp/soul/qi build_fighter_data
        # feeds unified_combat_hp, so the Alma's HP == the arena's HP by construction.
        _combat_dao = dict(dao_bonuses) if dao_bonuses else None
        if _combat_dao is not None:
            _combat_dao["bp_mult"] = 1.0
        clean = calculate_total_stats(
            player, equip_stats, companion_bonus, dao_bonuses=_combat_dao,
            interior_bonuses=interior_bonuses,
        )
        # Achievement bp_mult is folded onto the ALREADY int-truncated clean bp as a
        # FLOAT (int(P)·m), EXACTLY like build_fighter_data — NOT inside calculate_total_
        # stats (int(P·m)) — so the Alma's max_hp matches the arena to the sub-unit even
        # when an achievement bp_mult is active (keeps "profile HP == arena HP" exact).
        _clean_bp = float(clean.get("battle_power", 0) or 0)
        if _ach_bp and _ach_bp != 1.0:
            _clean_bp = _clean_bp * _ach_bp
        max_hp = unified_combat_hp(
            player, clean["soul_strength"], clean["qi_capacity"], _clean_bp,
            realm_eff=realm_eff,
        )
        # Companion hp_mult + faction foundation scale the POOL (never inside
        # calculate_total_stats → no double-count), mirroring build_fighter_data.
        if companion_bonus:
            max_hp = max_hp * float(companion_bonus.get("hp_mult", 1.0) or 1.0)
        _foundation = float((faction_bonuses or {}).get("foundation_bonus", 0) or 0)
        if _foundation > 0:
            max_hp = max_hp * (1.0 + _foundation)
        soul_v = total["soul_strength"]
        percep_v = total["perception"]
        luck_v = total["luck"]
        qi_v = qi_capacity_eff if qi_capacity_eff is not None else total["qi_capacity"]
        bp_strike = int(_clean_bp)
    else:
        realm_eff = float(realm)
        max_hp = calculate_hp(player)
        soul_v = int(player.soul_strength or 0)
        percep_v = int(player.perception or 0)
        luck_v = int(player.luck or 0)
        qi_v = qi_capacity_eff if qi_capacity_eff is not None else float(player.qi_capacity or 0)
        bp_strike = int(player.battle_power or 0)

    # ── headline Poder de Combate (gated progressao_visivel; else raw) ──
    if visible:
        display_power = int(display_combat_power(total["total_battle_power"], player))
    else:
        display_power = int(player.battle_power or 0)

    return {
        "max_hp": float(max_hp),
        "display_power": display_power,
        "battle_power_strike": int(bp_strike),
        "soul_strength": int(soul_v),
        "perception": int(percep_v),
        "luck": int(luck_v),
        "qi_capacity": float(qi_v),
        "realm": realm,
        "sub_layer": sub,
        "realm_eff": float(realm_eff),
        "mode": "effective" if unified else "raw",
    }


async def load_cultivator_modifiers(session, player) -> dict:
    """Fetch the full modifier stack once (equip · companion · Dao · interior ·
    achievements · faction · effective qi cap). Best-effort — each source is
    guarded so a single lookup failure degrades to a neutral default, never
    crashes the snapshot. Achievements are gated (combate_unificado) via the
    corrected delta helper → {} + zero query on main."""
    pid = player.telegram_id
    equip_stats = companion_bonus = dao_bonuses = interior_bonuses = None
    achievement_mults = faction_bonuses = None
    qi_capacity_eff = None

    try:
        from sqlalchemy import select as _select
        from database.models import PlayerArtifact
        from core.game_logic import get_player_equipment_stats
        arts = (await session.execute(_select(PlayerArtifact).where(
            PlayerArtifact.player_id == pid,
            PlayerArtifact.is_equipped == True,  # noqa: E712
        ))).scalars().all()
        equip_stats = get_player_equipment_stats(arts) if arts else None
    except Exception:
        logger.exception("soul: equip fetch failed player=%s", pid)

    try:
        from core.beast_engine import get_companion_beast, get_companion_bonuses
        cb, cc = await get_companion_beast(session, pid)
        companion_bonus = get_companion_bonuses(cb, cc) if (cb and cc) else None
    except Exception:
        logger.exception("soul: companion fetch failed player=%s", pid)

    try:
        from core.dao_engine import get_player_dao_bonuses
        dao_bonuses = await get_player_dao_bonuses(session, pid, int(player.realm or 0))
    except Exception:
        logger.exception("soul: dao fetch failed player=%s", pid)

    try:
        from core.game_logic import get_active_technique_bonuses
        interior_bonuses = await get_active_technique_bonuses(session, pid)
    except Exception:
        logger.exception("soul: interior fetch failed player=%s", pid)

    try:
        from core.achievement_engine import get_gated_achievement_multipliers
        achievement_mults = await get_gated_achievement_multipliers(session, pid)
    except Exception:
        logger.exception("soul: achievement fetch failed player=%s", pid)

    try:
        from core.faction_engine import get_faction_bonuses
        faction_bonuses = await get_faction_bonuses(session, pid)
    except Exception:
        logger.exception("soul: faction fetch failed player=%s", pid)

    try:
        # HOTFIX 2026-07-26: a função SEMPRE viveu em game_logic — o import de
        # combat_engine (afa0872, 2026-07-01) nunca resolveu, então desde que
        # `combate_unificado` ligou no s2 TODO snapshot da Alma caía aqui
        # (ImportError a cada tick, qi_capacity_eff nunca preenchido → o qi
        # efetivo de têmpera/pílulas ficava FORA do HP unificado no s2, e o
        # log inundava com "qi_cap fetch failed"). Regra da memória: gates de
        # qi usam capacidade EFETIVA — agora a Alma volta a usar.
        from core.game_logic import get_effective_qi_capacity
        qi_capacity_eff = await get_effective_qi_capacity(session, player, equip_stats=equip_stats)
    except Exception:
        logger.exception("soul: qi_cap fetch failed player=%s", pid)

    return {
        "equip_stats": equip_stats,
        "companion_bonus": companion_bonus,
        "dao_bonuses": dao_bonuses,
        "interior_bonuses": interior_bonuses,
        "achievement_mults": achievement_mults,
        "faction_bonuses": faction_bonuses,
        "qi_capacity_eff": qi_capacity_eff,
    }


async def compute_cultivator_soul(session, player, *, preloaded: dict | None = None) -> dict:
    """A ALMA DO CULTIVADOR — the one snapshot every surface reads.

    ``preloaded`` lets a caller that already fetched the modifier stack (e.g. the
    combat fighter builder, or a chat handler batching its queries) skip the
    re-fetch. Best-effort: any failure degrades to the RAW snapshot so a display
    can never blank. Gated by combate_unificado (HP/attributes/realm) +
    progressao_visivel (headline power); OFF → byte-identical to legacy `main`."""
    try:
        from database.db import feature_enabled_for_world as _ffe
        unified = bool(_ffe("combate_unificado"))
        visible = bool(_ffe("progressao_visivel"))
    except Exception:
        unified = visible = False

    try:
        mods = preloaded if preloaded is not None else await load_cultivator_modifiers(session, player)
    except Exception:
        logger.exception("soul: modifier load failed player=%s", getattr(player, "telegram_id", None))
        mods = {}

    try:
        return build_soul_snapshot(
            player,
            equip_stats=mods.get("equip_stats"),
            companion_bonus=mods.get("companion_bonus"),
            dao_bonuses=mods.get("dao_bonuses"),
            interior_bonuses=mods.get("interior_bonuses"),
            achievement_mults=mods.get("achievement_mults"),
            faction_bonuses=mods.get("faction_bonuses"),
            qi_capacity_eff=mods.get("qi_capacity_eff"),
            unified=unified,
            visible=visible,
        )
    except Exception:
        logger.exception("soul: snapshot build failed player=%s", getattr(player, "telegram_id", None))
        # Absolute fail-safe — the RAW snapshot (never raises, never blanks a UI).
        return build_soul_snapshot(player, unified=False, visible=False)


async def soul_max_hp(session, player, *, preloaded: dict | None = None) -> float:
    """Onda B accessor — the ONE max HP every DISPLAY surface must show.

    This is what closes the owner's anchor bug (*"HP na arena mostra uma coisa, no
    perfil outra"*) in production: every HP screen calls this, so the profile HP,
    the /status HP, the exploration HP and the arena HP are the SAME number.

      - combate_unificado ON  → the Alma's EFFECTIVE max HP (equip/Dao/companion/
        faction/tempering) — identical to ``build_fighter_data`` by construction.
      - combate_unificado OFF → the RAW legacy ``calculate_hp`` WITHOUT fetching a
        single modifier: ``main``/the 57 stay byte-identical AND the 30s ``api_player``
        poll pays ZERO extra queries (the raw HP needs only the player row). This
        short-circuit is why callers can use this everywhere, hot path included.

    Fail-safe: any error (flag lookup, snapshot) degrades to the raw HP so a bar
    never blanks. ``preloaded`` reuses an already-fetched modifier stack when ON.
    """
    from core.combat_engine import get_max_hp
    try:
        from database.db import feature_enabled_for_world as _ffe
        if not bool(_ffe("combate_unificado")):
            return float(get_max_hp(player))
    except Exception:
        return float(get_max_hp(player))
    try:
        soul = await compute_cultivator_soul(session, player, preloaded=preloaded)
        return float(soul["max_hp"])
    except Exception:
        logger.exception("soul_max_hp failed → raw HP fallback (player=%s)",
                         getattr(player, "telegram_id", None))
        return float(get_max_hp(player))


def soul_current_hp(player, max_hp) -> float:
    """Onda B/C — the current HP to DISPLAY against ``max_hp`` (from :func:`soul_max_hp`).

    Returns the SAME FRACTION of the (possibly effective) display pool that the
    cultivator holds of their RAW persisted pool. This matters on combate_unificado
    worlds: ``player.current_hp`` is persisted/clamped against the RAW ``calculate_hp``
    pool (apply_hp_drain, healing and regen all baseline off it), so reading it
    directly against the larger EFFECTIVE pool would deflate the % — and snap a
    full fighter down to raw/eff after a single scratch. Scaling by the fraction
    keeps the bar honest (100% when full, N% at N% of the raw pool) while showing
    effective absolute numbers, and is DISPLAY-ONLY (no change to the HP persistence
    model). It also makes the displayed % equal the raw gameplay % (e.g. the dungeon
    auto-advance stop threshold). On OFF (``max_hp`` == raw) it is byte-identical to
    ``get_current_hp``. Never raises."""
    from core.combat_engine import get_current_hp, get_max_hp
    try:
        cur = float(get_current_hp(player))     # raw-clamped; None persisted == full raw pool
        max_hp = float(max_hp)
        raw_max = float(get_max_hp(player))
        if raw_max <= 0 or abs(max_hp - raw_max) < 1e-9:
            # OFF (or no effective headroom) → the exact legacy value.
            return min(cur, max_hp)
        return (cur / raw_max) * max_hp          # same fraction of the effective pool
    except Exception:
        try:
            return float(max_hp)
        except Exception:
            return 0.0
