"""
Achievement engine — tracks progress and unlocks achievements/titles.

check_achievements(session, player_id, event_type, value=1)
  - For cumulative events (wins, crafts, etc.): value = amount to increment
  - For set-based events (realm_reached, beasts_owned, jade_accumulated): value = absolute current value
  - Returns list of newly unlocked AchievementCatalog rows
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AchievementCatalog, PlayerAchievement, Player, PlayerBeast

logger = logging.getLogger(__name__)

# Events where we SET progress to value (not increment)
# v16.4c — sect_rank_reached carries the absolute rank ordinal (disciple=0 ..
# heir=4), so a later promotion re-fire must use max(), never increment.
# continents_visited (2026-06-12) carries the distinct-continent COUNT (home=1,
# any successful travel proves a 2nd) — increment semantics would double-count
# repeat trips and the travel-fire racing the snapshot sync.
_SET_EVENTS = {"realm_reached", "beasts_owned", "jade_accumulated", "prestige_count",
               "sect_rank_reached", "continents_visited"}


async def check_achievements(
    session: AsyncSession,
    player_id: int,
    event_type: str,
    value: int = 1,
) -> list[AchievementCatalog]:
    """
    Update progress for all achievements of the given event_type.
    Returns list of newly unlocked achievements.
    """
    catalog_stmt = select(AchievementCatalog).where(AchievementCatalog.event_type == event_type)
    catalog_rows = (await session.execute(catalog_stmt)).scalars().all()
    if not catalog_rows:
        return []

    newly_unlocked = []
    now = datetime.now(timezone.utc)

    for ach in catalog_rows:
        pa_stmt = select(PlayerAchievement).where(
            PlayerAchievement.player_id == player_id,
            PlayerAchievement.achievement_id == ach.id,
        )
        pa = (await session.execute(pa_stmt)).scalar_one_or_none()

        if pa is None:
            # Collision-safe first-insert (quick-wins 2026-06-10 review). This
            # runs on the CALLER's session, and a concurrent path can insert the
            # SAME (player_id, achievement_id) row at the same instant — e.g. an
            # event handler holding Player FOR UPDATE (api_dungeons_advance /
            # apply_karma) racing sync_player_snapshot via /conquistas, which
            # holds NO Player lock, so the two do NOT serialize. A plain
            # session.add then hits the composite PK and raises a UniqueViolation
            # at flush/commit, poisoning the caller's transaction and rolling back
            # its real work (the dungeon clear, the combat result that moved
            # karma, …). ON CONFLICT DO NOTHING makes the insert idempotent; we
            # then re-select the now-guaranteed row to update its progress.
            await session.execute(
                pg_insert(PlayerAchievement)
                .values(player_id=player_id, achievement_id=ach.id, progress=0)
                .on_conflict_do_nothing(index_elements=["player_id", "achievement_id"])
            )
            pa = (await session.execute(pa_stmt)).scalar_one()

        # Already fully unlocked — skip
        if pa.unlocked_at is not None:
            continue

        if event_type in _SET_EVENTS:
            pa.progress = max(pa.progress, value)
        else:
            pa.progress += value

        if pa.progress >= ach.target_value:
            pa.unlocked_at = now
            newly_unlocked.append(ach)
            logger.info("🏆 Player %d unlocked achievement '%s'", player_id, ach.name)

    return newly_unlocked


async def reset_achievement_progress(session: AsyncSession, player_id: int, event_type: str) -> None:
    """Reset progress for non-unlocked achievements of event_type (e.g. win_streak on loss)."""
    catalog_stmt = select(AchievementCatalog).where(AchievementCatalog.event_type == event_type)
    catalog_rows = (await session.execute(catalog_stmt)).scalars().all()
    for ach in catalog_rows:
        pa_stmt = select(PlayerAchievement).where(
            PlayerAchievement.player_id == player_id,
            PlayerAchievement.achievement_id == ach.id,
        )
        pa = (await session.execute(pa_stmt)).scalar_one_or_none()
        if pa and pa.unlocked_at is None:
            pa.progress = 0


async def get_achievement_stat_bonuses(session: AsyncSession, player_id: int) -> dict:
    """
    Aggregate all stat bonuses from unlocked achievements.
    These apply regardless of which title is equipped.
    """
    stmt = (
        select(AchievementCatalog)
        .join(PlayerAchievement, PlayerAchievement.achievement_id == AchievementCatalog.id)
        .where(
            PlayerAchievement.player_id == player_id,
            PlayerAchievement.unlocked_at.is_not(None),
            AchievementCatalog.stat_bonus.is_not(None),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()

    bonuses: dict = {}
    for ach in rows:
        if not ach.stat_bonus:
            continue
        for key, val in ach.stat_bonus.items():
            if key in bonuses:
                bonuses[key] = bonuses[key] + val
            else:
                bonuses[key] = val

    return bonuses


# Combate Unificado — keys whose stat_bonus value is a FULL multiplier (1.05 =
# +5%), so N stacking achievements must aggregate as 1+Σ(val-1), NOT the naive
# additive sum get_achievement_stat_bonuses does (two +5% → 1.05+1.05 = 2.10,
# which as a multiplier would DESTROY the stat). Anything not listed here
# (evasion, alchemy_quality…) is a plain delta and is intentionally excluded.
_ACHIEVEMENT_MULT_KEYS = frozenset({
    "cb_mult", "bp_mult", "soul_mult", "luck_mult", "hp_mult",
    "qi_recovery_mult", "perception_mult", "evasion_mult",
})


async def get_achievement_combat_multipliers(session: AsyncSession, player_id: int) -> dict:
    """Combate Unificado — unlocked-achievement ``*_mult`` bonuses as PROPER
    cumulative multipliers.

    ``stat_bonus`` stores each "+5%" as the FULL multiplier ``1.05`` (see
    database/seeds/achievement_seeds.py). The legacy ``get_achievement_stat_bonuses``
    sums those raw (``1.05 + 1.05 = 2.10``), which only happens to be correct
    while a single achievement carries a given key — a realm-10 player unlocking
    Core Master (1.05) + Nascent Awakening (1.10) + True Immortal (1.20) would
    otherwise get cb_mult ``3.35`` (a 235%/tick monster) instead of the honest
    ``1.35``. Here each achievement contributes its DELTA ``(val-1)`` and we
    return ``1 + Σdelta``, so the number the UI promises ("+5%", "+10%"…) is the
    number that actually bites cultivation speed (B) / strike + HP (C). Only
    reached on worlds with ``combate_unificado`` ON."""
    stmt = (
        select(AchievementCatalog)
        .join(PlayerAchievement, PlayerAchievement.achievement_id == AchievementCatalog.id)
        .where(
            PlayerAchievement.player_id == player_id,
            PlayerAchievement.unlocked_at.is_not(None),
            AchievementCatalog.stat_bonus.is_not(None),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: dict = {}
    for ach in rows:
        for key, val in (ach.stat_bonus or {}).items():
            if key in _ACHIEVEMENT_MULT_KEYS:
                try:
                    out[key] = out.get(key, 1.0) + (float(val) - 1.0)
                except (TypeError, ValueError):
                    continue
    return out


async def get_gated_achievement_multipliers(session: AsyncSession, player_id: int) -> dict:
    """``combate_unificado``-gated wrapper over get_achievement_combat_multipliers.

    Returns ``{}`` when the flag is OFF so ``main``/legacy paths pay ZERO query
    and stay byte-identical; else the corrected ``*_mult`` dict. Best-effort: a
    lookup failure degrades to ``{}`` (a neutral 1.0 everywhere), never crashes
    the cultivation tick or the display."""
    try:
        from database.db import feature_enabled_for_world
        if not feature_enabled_for_world("combate_unificado"):
            return {}
    except Exception:
        return {}
    try:
        return await get_achievement_combat_multipliers(session, player_id)
    except Exception:
        logger.exception("gated achievement multipliers fetch failed player=%s", player_id)
        return {}


# ── QoL 04/08 (report [jogador]) — o que a conquista REALMENTE dá NESTE mundo ──
#
# As keys de `stat_bonus` que têm CONSUMIDOR vivo. Só estas duas são lidas por
# algum engine (via get_gated_achievement_multipliers → build_fighter_data /
# tick de cultivo), e mesmo assim SÓ com `combate_unificado` ON.
#
# As outras 3 seedadas são ÓRFÃS — precificadas, exibidas e lidas por NINGUÉM:
#   · `evasion` 0.03 (#8 Undefeated) — não está na allow-list de multiplicadores
#     e `get_achievement_stat_bonuses` (que a devolveria) não tem call site;
#   · `alchemy_quality` 0.05/0.10 (#5/#6) — zero consumidores no jogo inteiro;
#   · `tribulation_severity_mult` 0.95 (#25) — a severidade real deriva só de
#     |karma| (karma_engine.get_tribulation_modifier).
# Ligá-las é decisão de BALANCE (Lei §5 — servidor de launch), não deste lote.
# O que este lote corrige é a MENTIRA: elas deixam de ser ANUNCIADAS como
# benefício enquanto não morderem (Lei §1: benefício invisível = benefício
# nenhum; e prometer o que não existe é pior que não prometer).
ACH_LIVE_BONUS_KEYS = frozenset({"cb_mult", "bp_mult"})


def bonus_display(stat_bonus: dict | None, world_key: str | None = None) -> list[dict]:
    """UMA verdade sobre o que ANUNCIAR de uma conquista — as 2 telas leem daqui.

    Antes deste lote cada superfície fazia a sua conta e ambas mentiam do MESMO
    jeito na `main`: com `combate_unificado` OFF o rótulo caía no ramo legado
    `v*100` sobre um multiplicador cheio (1.05) e prometia **"+105% cb mult"**
    aos 57 jogadores — de um bônus que, sem a flag, vale exatamente ZERO
    (`get_gated_achievement_multipliers` devolve {}).

    Regra: só entra na lista o bônus que ESTE mundo aplica de facto. Lista vazia
    ⇒ a tela mostra a linha honorífica em vez de um número que não existe."""
    if not stat_bonus:
        return []
    try:
        from database.db import feature_enabled_for_world
        live = bool(feature_enabled_for_world("combate_unificado", world_key))
    except Exception:
        live = False
    if not live:
        return []
    out: list[dict] = []
    for key, raw in stat_bonus.items():
        if key not in ACH_LIVE_BONUS_KEYS:
            continue          # seedado mas sem consumidor — não se anuncia
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        pct = (val - 1.0) * 100.0 if key.endswith("_mult") else val * 100.0
        if abs(pct) < 0.05:
            continue          # 0% não é benefício
        out.append({"key": key, "pct": round(pct, 1),
                    "label_key": f"ach_bonus_{key}"})
    return out


async def get_player_achievements(session: AsyncSession, player_id: int) -> list[tuple]:
    """
    Returns list of (AchievementCatalog, PlayerAchievement | None) tuples.
    """
    catalog = (await session.execute(select(AchievementCatalog).order_by(AchievementCatalog.id))).scalars().all()

    pa_stmt = select(PlayerAchievement).where(PlayerAchievement.player_id == player_id)
    pa_rows = {pa.achievement_id: pa for pa in (await session.execute(pa_stmt)).scalars().all()}

    return [(ach, pa_rows.get(ach.id)) for ach in catalog]


async def get_unlocked_titles(session: AsyncSession, player_id: int) -> list[str]:
    """Returns list of title strings the player has unlocked (achievements + VIP/BP extras)."""
    # Achievement titles
    stmt = (
        select(AchievementCatalog.title_granted)
        .join(PlayerAchievement, PlayerAchievement.achievement_id == AchievementCatalog.id)
        .where(
            PlayerAchievement.player_id == player_id,
            PlayerAchievement.unlocked_at.is_not(None),
            AchievementCatalog.title_granted.is_not(None),
        )
    )
    ach_titles = [r for r in (await session.execute(stmt)).scalars().all() if r]

    # Extra titles (VIP milestones, BP, etc.)
    player = (await session.execute(select(Player).where(Player.telegram_id == player_id))).scalar_one_or_none()
    extra = list(player.unlocked_titles or []) if player else []

    # Merge without duplicates, preserve order
    seen = set(ach_titles)
    merged = list(ach_titles)
    for t in extra:
        if t not in seen:
            merged.append(t)
            seen.add(t)
    return merged


# ─── Extra-title descriptions (TAPETE QoL §5 item 10 — [jogador] 25.05) ──────────
# Titles granted into Player.unlocked_titles (JSONB) have no catalog row and
# therefore no description anywhere ("esses 3 titulos não aparecem lá e não
# mostram o que fazem"). Map every known grant site to an i18n key; the
# prestige-shop titles reuse their existing shop desc keys. All are cosmetic
# (shown as [Title] before the dao name) — the descriptions say where each
# one comes from, honest-disclosure style (Lei §1).
EXTRA_TITLE_DESC_KEYS = {
    "Patron of the Dao": "title_desc_patron_of_the_dao",      # first jade top-up (handlers/shop.py)
    "Celestial Patron": "title_desc_celestial_patron",        # Celestial Pass milestone 30 (core/monetization.py)
    "Core Forger": "title_desc_core_forger",                  # Battle Pass reward (battle_pass_seeds)
    "Dao Benefactor": "title_desc_dao_benefactor",            # VIP €50 (core/monetization.py)
    "Heaven's Patron": "title_desc_heavens_patron",           # VIP €100 (core/monetization.py)
    "🔄 O Renascido": "prestige_shop_item_title_reborn_desc",
    "🌀 Caminhante das Mil Vidas": "prestige_shop_item_title_walker_desc",
    # # Pedra 2 wave 3 — Merit Pavilion cosmetic titles (bought in the Sect Hall; see world_sects_engine.MERIT_REWARDS).
    "☁️ Andarilho das Nuvens": "title_desc_azure_cloud_epithet",
    "☁️ Guardião do Céu Aberto": "title_desc_azure_cloud_legend",
    "🔥 Guardião da Brasa": "title_desc_eternal_flame_epithet",
    "🔥 Senhor das Mil Chamas Renascidas": "title_desc_eternal_flame_legend",
    "🪷 Mão que Não Ergue a Lâmina": "title_desc_jade_harmony_epithet",
    "🪷 O Dao que Cura Mais do que Fere": "title_desc_jade_harmony_legend",
    "🪨 Pele de Granito": "title_desc_iron_mountain_epithet",
    "🏔️ A Montanha que Caminha": "title_desc_iron_mountain_legend",
    "❄️ Discípulo do Coração Sereno": "title_desc_frozen_peak_epithet",
    "❄️ Soberano do Gelo Imóvel": "title_desc_frozen_peak_legend",
    "🌸 Botão de Mil Daos": "title_desc_thousand_bloom_epithet",
    "🌺 Jardineiro dos Mil Daos": "title_desc_thousand_bloom_legend",
    "🌬️ Passo que o Vento Engole": "title_desc_silent_wind_epithet",
    "🗡️ Lâmina que Ninguém Ouviu": "title_desc_silent_wind_legend",
    "🌅 Forjador do Primeiro Gume": "title_desc_blazing_sun_epithet",
    "☀️ Juiz Sem Sombra": "title_desc_blazing_sun_legend",
    "💀 Faminto do Abismo": "title_desc_abyssal_depths_epithet",
    "👁️ Soberano do Vazio Devorador": "title_desc_abyssal_depths_legend",
    # MV-5 §0 (dívida MV-4) — os 12 meridianos abertos (meridian_engine.MERIDIAN_TITLE_12).
    "🏮 Vaso Perfeito": "title_desc_vaso_perfeito",
    # MV-6 — o arco do rival fechado na 5ª derrota (reputation_engine.RIVAL_TITLE).
    "💢 Quebra-Rivais": "title_desc_quebra_rivais",
    # 印记 — 1000 ativações da MESMA formação no corpo (formation_engine.MARCA_TITLE).
    "🔯 Marca do Traçado": "title_desc_marca_do_tracado",
}


async def get_extra_titles_with_desc(session: AsyncSession, player_id: int, lang: str = "pt") -> list[dict]:
    """[{name, description}] for the player's JSONB extra titles (non-achievement).

    Best-effort: unknown titles (future grants without a mapping) still list,
    with an empty description — never hide an unlocked title (Lei §1).
    """
    from core.i18n import t as _t
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()
    extra = list(player.unlocked_titles or []) if player else []
    out = []
    for title in extra:
        key = EXTRA_TITLE_DESC_KEYS.get(title)
        out.append({
            "name": title,
            "description": _t(lang, key) if key else "",
        })
    return out


async def equip_title(session: AsyncSession, player_id: int, title: str) -> bool:
    """
    Equip a title. Returns True if successful, False if title not unlocked.
    Pass None to unequip.
    """
    if title is not None:
        unlocked = await get_unlocked_titles(session, player_id)
        if title not in unlocked:
            return False

    player = (await session.execute(select(Player).where(Player.telegram_id == player_id))).scalar_one_or_none()
    if not player:
        return False

    player.active_title = title
    return True


async def toggle_shadow_mode(session: AsyncSession, player_id: int, vip_level: int) -> tuple[bool, bool]:
    """
    Toggle shadow mode for VIP 3+ players.
    Returns (success, new_state).
    """
    if vip_level < 3:
        return False, False

    player = (await session.execute(select(Player).where(Player.telegram_id == player_id))).scalar_one_or_none()
    if not player:
        return False, False

    player.shadow_mode = not player.shadow_mode

    # Award the hidden achievement if activating for first time
    if player.shadow_mode:
        await check_achievements(session, player_id, "shadow_unlocked", 1)

    return True, player.shadow_mode


def format_display_name_with_title(player: Player) -> str:
    """Returns 'dao_name' or '[Title] dao_name' if a title is active."""
    name = player.dao_name or player.display_name or player.username or "Cultivador"
    if player.active_title:
        return f"[{player.active_title}] {name}"
    return name


async def sync_player_snapshot(session: AsyncSession, player: Player) -> list[AchievementCatalog]:
    """
    Retroactively sync set-based achievements from the player's current stats.
    Call this when the player first opens /conquistas so past progress is reflected.
    Returns list of newly unlocked achievements.
    """
    newly_unlocked = []

    if player.realm > 0:
        newly_unlocked += await check_achievements(session, player.telegram_id, "realm_reached", player.realm)

    # Migration 115 — jade_accumulated now tracks LIFETIME earnings via
    # grant_jade; the balance stays as a floor for grandfathered progress
    # (max() SET semantics: never regresses).
    _jade_val = max(int(player.spirit_jade or 0),
                    int(getattr(player, "lifetime_jade_earned", 0) or 0))
    if _jade_val > 0:
        newly_unlocked += await check_achievements(session, player.telegram_id, "jade_accumulated", _jade_val)

    if player.prestige_level > 0:
        newly_unlocked += await check_achievements(session, player.telegram_id, "prestige_count", player.prestige_level)

    beast_count = (await session.execute(
        select(func.count()).select_from(PlayerBeast).where(PlayerBeast.player_id == player.telegram_id)
    )).scalar_one()
    if beast_count > 0:
        newly_unlocked += await check_achievements(session, player.telegram_id, "beasts_owned", beast_count)

    # v16.3 — Retroactive grant for Achievement #24 Path Walker. The 57+
    # beta players whose `path` was backfilled by Migration 102 (or who
    # got their path crystallized via the karma engine before opening
    # /conquistas) deserve the catalog row to mark unlocked. Single-shot
    # (target=1): the first sync trip past this line locks it in.
    if getattr(player, "path", None):
        newly_unlocked += await check_achievements(session, player.telegram_id, "path_chosen", 1)

    # v16.3 — Retroactive grant for Achievement #25 Saint Walker. If a
    # cultivator already pushed past +1000 karma (unlikely at v16.3 launch
    # since the column just initialized to 0, but safe for the future),
    # mark them. karma column always exists (Migration 103 default 0).
    if int(getattr(player, "karma", 0) or 0) >= 1000:
        newly_unlocked += await check_achievements(session, player.telegram_id, "karma_reached_max", 1)

    # Quick-wins 2026-06-10 — retroactive grant for Achievement #31 Demon
    # Sovereign (the demonic mirror of Saint Walker). Two cultivators ([jogador] +
    # [jogador]) hit −1000 karma and reported getting no title; the catalog row +
    # event ship now, and this credits anyone already sitting at the floor the
    # first time they open /conquistas or the mini-app. Single-shot (target=1).
    if int(getattr(player, "karma", 0) or 0) <= -1000:
        newly_unlocked += await check_achievements(session, player.telegram_id, "karma_reached_min", 1)

    # v16.4c — retroactive sect rank achievements (#29 Sect Pillar / #30 Sect
    # Successor). Credits a member for their CURRENT rung the first time they
    # open /conquistas. The 57 live members are all 'disciple' (ordinal 0), so
    # nothing unlocks yet — but a member who later reaches elder/heir offline-
    # promoted is covered. SET event ⇒ max() keeps it monotonic.
    sect_rank = getattr(player, "sect_rank", None)
    if sect_rank:
        from core.world_sects_engine import rank_index as _sect_rank_index
        newly_unlocked += await check_achievements(
            session, player.telegram_id, "sect_rank_reached", _sect_rank_index(sect_rank)
        )

    # Quick-wins 2026-06-10 — retroactive grant for Achievement #16 Abyssal
    # Conqueror. The mini-app dungeon-completion path (api_dungeons_advance)
    # historically lacked the `dungeon_abyssal` achievement call (the same hole
    # the v16.7 fix patched for dungeon QUESTS), so mini-app players who cleared
    # the Abyssal Rift never got the title — [jogador] reported clearing it 3× with
    # nothing (25.05). Credit anyone who has EVER cleared dungeon #4 (completed
    # flag OR a non-zero best_difficulty — both are monotonic "cleared" signals)
    # the first time they open /conquistas or the mini-app. Single-shot.
    from sqlalchemy import or_ as _or
    from database.models import PlayerDungeon
    cleared_abyssal = (await session.execute(
        select(func.count()).select_from(PlayerDungeon).where(
            PlayerDungeon.player_id == player.telegram_id,
            PlayerDungeon.dungeon_id == 4,
            _or(PlayerDungeon.completed.is_(True), PlayerDungeon.best_difficulty >= 1),
        )
    )).scalar_one()
    if cleared_abyssal > 0:
        newly_unlocked += await check_achievements(session, player.telegram_id, "dungeon_abyssal", 1)

    # Onda 4b gap (2026-06-12) — retroactive grant for Achievement #22
    # Continent Explorer. Travel shipped 2026-06-07 without firing
    # `continents_visited` (the v16.0 seed was a disclosed placeholder), so
    # travellers ([jogador] among 16+) sat at 0/2 forever. Evidence of a 2nd
    # distinct continent: ever travelled (last_travel_at is stamped ONLY on a
    # successful move to a DIFFERENT continent) OR currently standing
    # off-home. SET event ⇒ max() keeps it idempotent.
    _home = getattr(player, "home_continent", None) or "linghe"
    _cur = getattr(player, "current_continent", None) or _home
    if getattr(player, "last_travel_at", None) is not None or _cur != _home:
        newly_unlocked += await check_achievements(session, player.telegram_id, "continents_visited", 2)

    return newly_unlocked
