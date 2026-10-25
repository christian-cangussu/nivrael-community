import logging
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import select, delete, or_
from core.activity_indicators import _invalidate_cache as _inv_cache
# 名 2026-09-14 — nome de quest pelo dono unico.
from core.i18n import catalog_name

from database.models import (
    QuestCatalog, PlayerQuest, LoginStreak,
    Player, SectMember,
)
# v16.3.5 Karmic Crossroads — moral choice engine. No import cycle:
# quest_choice_engine only pulls karma_engine/models/utils, never quest_engine.
from core.quest_choice_engine import (
    quest_has_choices, apply_quest_choice, get_quest_choices_raw,
)

logger = logging.getLogger(__name__)

STREAK_MILESTONES = {
    1: {"spirit_jade": 5},
    3: {"spirit_jade": 20},
    7: {"spirit_jade": 50, "item": "Rare Item Pack"},
    14: {"spirit_jade": 100},
    30: {"spirit_jade": 200, "title": "🔥 Devoted Cultivator"},
}


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _daily_reset_boundary() -> datetime:
    today = _today_utc()
    return datetime(today.year, today.month, today.day, tzinfo=timezone.utc)


def _weekly_reset_boundary() -> datetime:
    today = _today_utc()
    days_since_monday = today.weekday()
    monday = today - timedelta(days=days_since_monday)
    return datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)


# v16.4c — Sect Quests are NARRATIVE one-shots (no daily/weekly reset). reset_at
# is NOT NULL, so they take a far-future sentinel; the global daily/weekly reset
# jobs filter by type and never see them, so the sentinel is purely formal.
_SECT_QUEST_SENTINEL = datetime(2999, 1, 1, tzinfo=timezone.utc)


async def ensure_daily_quests(session, player_id: int):
    boundary = _daily_reset_boundary()

    stmt = select(QuestCatalog).where(
        QuestCatalog.type == "daily",
        QuestCatalog.is_active == True,
    )
    catalog = (await session.execute(stmt)).scalars().all()
    if not catalog:
        return

    quest_ids = [q.id for q in catalog]
    stmt_pq = select(PlayerQuest).where(
        PlayerQuest.player_id == player_id,
        PlayerQuest.quest_id.in_(quest_ids),
    )
    existing = (await session.execute(stmt_pq)).scalars().all()
    existing_map = {pq.quest_id: pq for pq in existing}

    for quest in catalog:
        pq = existing_map.get(quest.id)
        if pq and pq.reset_at >= boundary:
            continue

        if pq:
            pq.progress = 0
            pq.is_completed = False
            pq.claimed = False
            pq.reset_at = boundary
        else:
            session.add(PlayerQuest(
                player_id=player_id,
                quest_id=quest.id,
                progress=0,
                is_completed=False,
                claimed=False,
                reset_at=boundary,
            ))


async def ensure_weekly_quests(session, player_id: int):
    boundary = _weekly_reset_boundary()

    stmt = select(QuestCatalog).where(
        QuestCatalog.type == "weekly",
        QuestCatalog.is_active == True,
    )
    catalog = (await session.execute(stmt)).scalars().all()
    if not catalog:
        return

    quest_ids = [q.id for q in catalog]
    stmt_pq = select(PlayerQuest).where(
        PlayerQuest.player_id == player_id,
        PlayerQuest.quest_id.in_(quest_ids),
    )
    existing = (await session.execute(stmt_pq)).scalars().all()
    existing_map = {pq.quest_id: pq for pq in existing}

    for quest in catalog:
        pq = existing_map.get(quest.id)
        if pq and pq.reset_at >= boundary:
            continue

        if pq:
            pq.progress = 0
            pq.is_completed = False
            pq.claimed = False
            pq.reset_at = boundary
        else:
            session.add(PlayerQuest(
                player_id=player_id,
                quest_id=quest.id,
                progress=0,
                is_completed=False,
                claimed=False,
                reset_at=boundary,
            ))


async def ensure_sect_quests(session, player_id: int):
    """v16.4c — materialize Sect Quests for a HOUSE MEMBER (member-gated).

    Only players with a valid NPC sect get rows, and only for UNIVERSAL sect
    quests (sect_id NULL) plus their own house's quests. Narrative one-shots —
    they don't reset (sentinel reset_at), and the daily/weekly reset jobs filter
    by type so they're never touched. Progress auto-tracks via track_quest once
    the row exists (shared objective_types with daily/weekly).
    """
    row = (await session.execute(
        select(Player.sect_id).where(Player.telegram_id == player_id)
    )).first()
    sect_id = row[0] if row else None
    from core.world_sects_engine import is_valid_sect
    if not is_valid_sect(sect_id):
        return

    catalog = (await session.execute(
        select(QuestCatalog).where(
            QuestCatalog.type == "sect",
            QuestCatalog.is_active == True,
            or_(QuestCatalog.sect_id.is_(None), QuestCatalog.sect_id == sect_id),
        )
    )).scalars().all()
    if not catalog:
        return

    quest_ids = [q.id for q in catalog]
    existing = set((await session.execute(
        select(PlayerQuest.quest_id).where(
            PlayerQuest.player_id == player_id,
            PlayerQuest.quest_id.in_(quest_ids),
        )
    )).scalars().all())

    for quest in catalog:
        if quest.id in existing:
            continue
        session.add(PlayerQuest(
            player_id=player_id,
            quest_id=quest.id,
            progress=0,
            is_completed=False,
            claimed=False,
            reset_at=_SECT_QUEST_SENTINEL,
        ))


async def get_player_sect_quests(session, player_id: int):
    """v16.4c — list the member's Sect Quests (joined catalog). Empty if the
    player is not in a house. Member-gated by Player.sect_id (universal +
    house-specific)."""
    row = (await session.execute(
        select(Player.sect_id).where(Player.telegram_id == player_id)
    )).first()
    sect_id = row[0] if row else None
    from core.world_sects_engine import is_valid_sect
    if not is_valid_sect(sect_id):
        return []
    stmt = (
        select(PlayerQuest, QuestCatalog)
        .join(QuestCatalog, QuestCatalog.id == PlayerQuest.quest_id)
        .where(
            PlayerQuest.player_id == player_id,
            QuestCatalog.type == "sect",
            QuestCatalog.is_active == True,
            or_(QuestCatalog.sect_id.is_(None), QuestCatalog.sect_id == sect_id),
        )
        .order_by(QuestCatalog.id)
    )
    return (await session.execute(stmt)).all()


async def track_quest(session, player_id: int, objective_type: str, amount: int = 1,
                      *, prof_weight_tier=None):
    # QoL-relatos (report [jogador], 28/07) — `prof_weight_tier` é um canal PARALELO que
    # SÓ o gancho de profissão lê (o tier 1..5 do que foi criado/usado). É
    # keyword-only de propósito: nenhum dos ~200 call sites posicionais pode
    # empurrá-lo por engano para dentro de `amount`. NUNCA é passado aos
    # storylets nem entra no contador de objetivo abaixo — se entrasse, uma
    # quest "forje 5 artefatos" fecharia em 1 forja (armadilha §0.3 do prompt).
    # MV-5 — storylets REUSAM este chokepoint: todo objective_type que alimenta
    # as quests alimenta os storylets aceitos (zero hooks novos, zero objetivos
    # órfãos — lição MV-1). Aditivo + flag-gated: quests_vivas OFF → return sem
    # UMA query; um erro aqui NUNCA derruba o tracking das quests.
    try:
        from core.storylet_engine import track_storylets
        await track_storylets(session, player_id, objective_type, amount)
    except Exception:
        logger.exception("storylet track hook failed (player=%s, type=%s)",
                         player_id, objective_type)

    # MV-7 — profissões REUSAM o mesmo chokepoint (craft_pill/forge_artifact/
    # use_pill → XP de ofício). Prefiltro estático PRÓPRIO dentro do gancho
    # (frozenset — login/cultivate não pagam nada) + flag profissoes OFF →
    # return sem UMA query; um erro NUNCA derruba o tracking das quests.
    try:
        from core.profession_engine import track_profession
        await track_profession(session, player_id, objective_type, amount,
                               weight_tier=prof_weight_tier)
    except Exception:
        logger.exception("profession track hook failed (player=%s, type=%s)",
                         player_id, objective_type)

    stmt = (
        select(PlayerQuest, QuestCatalog)
        .join(QuestCatalog, QuestCatalog.id == PlayerQuest.quest_id)
        .where(
            PlayerQuest.player_id == player_id,
            QuestCatalog.objective_type == objective_type,
            QuestCatalog.is_active == True,
            PlayerQuest.is_completed == False,
        )
    )
    rows = (await session.execute(stmt)).all()

    completed = False
    # v15.1.5 hotfix — collect freshly-completed quests so we can fire the
    # bell notification once per transition. Without this the player only
    # saw a quest finished by manually opening /quests, which was easy to
    # miss after long combat/dungeon sessions.
    completed_quests: list = []
    for pq, quest in rows:
        pq.progress = min(pq.progress + amount, quest.objective_value)
        if pq.progress >= quest.objective_value:
            pq.is_completed = True
            completed = True
            completed_quests.append(quest)
    if completed:
        _inv_cache(player_id)
        # v15.1.5-hf3 — ref_id MUST include a cycle marker because daily /
        # weekly quests reset and re-complete every cycle. A stable ref_id
        # like "quest:{id}" collides with the previous cycle's row in the
        # idx_pn_dedup unique index (which ignores dismissed_at), tripping
        # an IntegrityError that previously poisoned the parent transaction.
        # The savepoint in notify() now contains that blast — this cycle
        # marker is the proper fix that avoids the redundant churn.
        from datetime import datetime as _dt, timezone as _tz
        cycle = _dt.now(_tz.utc).strftime("%Y%m%d")
        # 名 2026-09-14 — o payload da notificacao leva o nome JA' traduzido.
        # ⚠️ Nao e' um placeholder novo (a licao de "notificacao NUNCA ganha
        # placeholder novo" continua de pe'): a chave `name` ja' la' estava, so'
        # muda o VALOR. E' seguro gravar traduzido porque esta notificacao tem
        # UM destinatario — o dono da quest — ao contrario do `combat_log`, que
        # tem dois. As rows ja' gravadas continuam a render o ingles que tem.
        from database.models import Player as _QPlayer
        _q_lang = ((await session.execute(
            select(_QPlayer.language).where(_QPlayer.telegram_id == player_id)
        )).scalar_one_or_none() or "pt").lower()
        for quest in completed_quests:
            try:
                from core.notification_engine import notify as _notify
                await _notify(
                    session, player_id, "quest_ready",
                    title_key="notif_inbox_quest_title",
                    body_key="notif_inbox_quest_body",
                    payload={"name": catalog_name(_q_lang, "q", quest) or ""},
                    ref_id=f"quest:{quest.id}:{cycle}",
                    icon=quest.emoji or "🎯",
                    target_tab="quests",
                    priority=2,
                )
            except Exception:
                # Belt-and-suspenders: notify() already has a savepoint and
                # never raises, but if some future refactor regresses that
                # contract this catch stops the regression from poisoning
                # the parent transaction (boss_attack, alchemy_craft, etc).
                logger.exception("quest_ready notify failed player=%s quest=%s",
                                 player_id, quest.id)


async def get_player_quests(session, player_id: int, quest_type: str):
    stmt = (
        select(PlayerQuest, QuestCatalog)
        .join(QuestCatalog, QuestCatalog.id == PlayerQuest.quest_id)
        .where(
            PlayerQuest.player_id == player_id,
            QuestCatalog.type == quest_type,
            QuestCatalog.is_active == True,
        )
        .order_by(QuestCatalog.id)
    )
    return (await session.execute(stmt)).all()


async def claim_quest_reward(session, player_id: int, quest_id: int, choice_id: str | None = None) -> dict | None:
    # SEC (2026-06-01): lock the player_quest row so concurrent claim requests
    # serialize — the second txn blocks, then re-reads claimed=True (the WHERE is
    # re-evaluated under the lock) and returns no row → no double-grant.
    stmt = (
        select(PlayerQuest, QuestCatalog)
        .join(QuestCatalog, QuestCatalog.id == PlayerQuest.quest_id)
        .where(
            PlayerQuest.player_id == player_id,
            PlayerQuest.quest_id == quest_id,
            PlayerQuest.is_completed == True,
            PlayerQuest.claimed == False,
        )
        .with_for_update(of=PlayerQuest)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None

    pq, quest = row

    # v16.3.5 Karmic Crossroads — quests with a `choices` fork apply a moral
    # choice instead of the fixed reward. The whole choice apply runs under the
    # same row lock as `claimed=True`, so the idempotency proof is identical to
    # the legacy path: a second click blocks, re-reads claimed=True, gets nothing.
    if quest_has_choices(quest):
        if choice_id is None:
            # Defer — the player must pick. Do NOT set claimed; return the menu.
            return {"needs_choice": True, "quest_id": quest_id, "choices": get_quest_choices_raw(quest)}
        player = (await session.execute(
            select(Player).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()
        if player is None:
            return None
        result = await apply_quest_choice(session, player, quest, pq, choice_id)
        if not result.get("ok"):
            return {"needs_choice": False, "error": result.get("reason")}
        pq.claimed = True
        _inv_cache(player_id)
        return {"choice_result": result}

    rewards = dict(quest.rewards)
    await _apply_rewards(session, player_id, rewards)
    pq.claimed = True
    _inv_cache(player_id)
    return rewards


async def claim_all_completed(session, player_id: int) -> dict:
    # SEC (2026-06-01): lock matched player_quest rows so concurrent claim_all
    # requests can't double-grant (FOR UPDATE re-evaluates claimed under the lock).
    stmt = (
        select(PlayerQuest, QuestCatalog)
        .join(QuestCatalog, QuestCatalog.id == PlayerQuest.quest_id)
        .where(
            PlayerQuest.player_id == player_id,
            PlayerQuest.is_completed == True,
            PlayerQuest.claimed == False,
        )
        .with_for_update(of=PlayerQuest)
    )
    rows = (await session.execute(stmt)).all()

    total_rewards: dict = {}
    claimed_count = 0
    for pq, quest in rows:
        # v16.3.5 — choice quests need an explicit moral pick; "claim all" must
        # NOT auto-grant them (that would set claimed=True with no karma applied).
        # Leave them completed+unclaimed so they surface for individual claiming.
        if quest_has_choices(quest):
            continue
        # v16.4c — Sect Quests are claimed in the Sect Hall (not swept by the
        # generic /quests claim-all), so members always see them in context.
        if quest.type == "sect":
            continue
        for key, val in quest.rewards.items():
            total_rewards[key] = total_rewards.get(key, 0) + val
        pq.claimed = True
        claimed_count += 1

    if total_rewards:
        await _apply_rewards(session, player_id, total_rewards)
        _inv_cache(player_id)

    return total_rewards, claimed_count


async def _apply_rewards(session, player_id: int, rewards: dict):
    player_stmt = select(Player).where(Player.telegram_id == player_id)
    player = (await session.execute(player_stmt)).scalar_one_or_none()
    if not player:
        return

    if "spirit_stones" in rewards:
        player.spirit_stones += rewards["spirit_stones"]

    if "spirit_jade" in rewards:
        from core.monetization import grant_jade
        await grant_jade(session, player, rewards["spirit_jade"])

    if "contribution_points" in rewards:
        member_stmt = select(SectMember).where(SectMember.player_id == player_id)
        member = (await session.execute(member_stmt)).scalar_one_or_none()
        if member:
            member.contribution_points += rewards["contribution_points"]
            from core.sect_engine import log_sect_contribution
            await log_sect_contribution(session, player_id, member.sect_id, "quest", rewards["contribution_points"])

    if "herb_pack" in rewards:
        count = rewards["herb_pack"]
        import random
        from core.utils import add_item_to_inventory
        # Weighted towards crafting-essential herbs
        herb_ids =     [1,  2,  3,  12, 9]
        herb_weights = [35, 25, 15, 15, 10]  # Qi Root > Spirit Grass > others > Moonlight Moss
        for _ in range(count):
            herb_id = random.choices(herb_ids, weights=herb_weights, k=1)[0]
            await add_item_to_inventory(session, player_id, "herb", herb_id, 3)

    if "technique_scroll" in rewards:
        import random
        from core.utils import add_item_to_inventory
        scroll_id = random.randint(1, 5)
        # TEC-2 — mesma régua das quests de masmorra (UMA regra para toda
        # recompensa GARANTIDA de pergaminho). Os seeds vivos já dão qty 1,
        # portanto isto é no-op hoje — existe para que um seed futuro de qty 3
        # não reabra o faucet sem ninguém notar. Flag OFF ⇒ idêntico.
        from core.scroll_economy_engine import quest_scroll_qty
        await add_item_to_inventory(session, player_id, "technique_scroll", scroll_id,
                                    quest_scroll_qty(rewards["technique_scroll"]))

    # v16.4c — NPC-sect rank currency (Sect Quests). SEPARATE from the GUILD's
    # `contribution_points` above (which credits SectMember). Routes through the
    # single mutator, which auto-promotes if a rank threshold is crossed.
    if "sect_contribution" in rewards:
        try:
            from core.world_sects_engine import award_sect_contribution
            await award_sect_contribution(
                session, player_id, int(rewards["sect_contribution"]), source="sect_quest"
            )
        except Exception:
            logger.exception("sect_contribution reward failed (player=%s)", player_id)

    if player.realm == 2 and player.core_quality is None:
        from core.golden_core_engine import add_core_essence
        ce_added = add_core_essence(player, 5)
        if ce_added > 0:
            rewards["core_essence"] = ce_added


async def update_login_streak(session, player_id: int) -> dict | None:
    stmt = select(LoginStreak).where(LoginStreak.player_id == player_id).with_for_update()
    streak = (await session.execute(stmt)).scalar_one_or_none()

    today = _today_utc()

    if not streak:
        streak = LoginStreak(
            player_id=player_id,
            current_streak=1,
            longest_streak=1,
            last_login_date=datetime(today.year, today.month, today.day, tzinfo=timezone.utc),
            total_logins=1,
        )
        session.add(streak)
        milestone = STREAK_MILESTONES.get(1)
        if milestone:
            await _apply_streak_reward(session, player_id, milestone)
        return milestone

    last_date = streak.last_login_date.date() if streak.last_login_date else None

    if last_date == today:
        return None

    if last_date and (today - last_date).days == 1:
        streak.current_streak += 1
    elif last_date and (today - last_date).days > 1:
        streak.current_streak = 1
    else:
        streak.current_streak = 1

    streak.last_login_date = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    streak.total_logins += 1
    if streak.current_streak > streak.longest_streak:
        streak.longest_streak = streak.current_streak

    milestone = STREAK_MILESTONES.get(streak.current_streak)
    if milestone:
        await _apply_streak_reward(session, player_id, milestone)
    return milestone


async def _apply_streak_reward(session, player_id: int, milestone: dict):
    player_stmt = select(Player).where(Player.telegram_id == player_id)
    player = (await session.execute(player_stmt)).scalar_one_or_none()
    if not player:
        return

    if "spirit_jade" in milestone:
        from core.monetization import grant_jade
        await grant_jade(session, player, milestone["spirit_jade"])

    # The "item" key (e.g. day-7 "Rare Item Pack") was being silently dropped:
    # the function only granted spirit_jade. Player report 2026-04-30: "tem
    # aquilo de rare pack em 7 dias… Não notei receber nada no dia 7", Saint
    # confirmed "possible bug". Resolve by materialising the pack as concrete
    # items so the reward actually reaches the inventory.
    if milestone.get("item") == "Rare Item Pack":
        from core.utils import add_item_to_inventory
        # 3 perfect-grade T2 utility pills + 1 high-tier herb. Picked to be
        # immediately useful at any realm without warping economy: pills are
        # consumables, herb feeds T2/T3 alchemy.
        for pill_id in (2, 3, 4):  # Foundation Pill, Soul Strength Pill, Body Refining Pill
            await add_item_to_inventory(session, player_id, "pill", pill_id, 1, "perfect")
        await add_item_to_inventory(session, player_id, "herb", 5, 1)  # Breakthrough Flower


async def get_login_streak(session, player_id: int) -> LoginStreak | None:
    stmt = select(LoginStreak).where(LoginStreak.player_id == player_id)
    return (await session.execute(stmt)).scalar_one_or_none()


def get_streak_rewards_table() -> dict:
    return STREAK_MILESTONES


async def reset_daily_quests_global(session):
    boundary = _daily_reset_boundary()
    stmt = (
        select(PlayerQuest)
        .join(QuestCatalog, QuestCatalog.id == PlayerQuest.quest_id)
        .where(
            QuestCatalog.type == "daily",
            PlayerQuest.reset_at < boundary,
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    for pq in rows:
        pq.progress = 0
        pq.is_completed = False
        pq.claimed = False
        pq.reset_at = boundary

    logger.info("🎯 Reset %d daily quests", len(rows))


async def reset_weekly_quests_global(session):
    boundary = _weekly_reset_boundary()
    stmt = (
        select(PlayerQuest)
        .join(QuestCatalog, QuestCatalog.id == PlayerQuest.quest_id)
        .where(
            QuestCatalog.type == "weekly",
            PlayerQuest.reset_at < boundary,
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    for pq in rows:
        pq.progress = 0
        pq.is_completed = False
        pq.claimed = False
        pq.reset_at = boundary

    logger.info("📅 Reset %d weekly quests", len(rows))
