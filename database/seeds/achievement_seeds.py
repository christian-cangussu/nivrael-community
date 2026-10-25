import logging
from sqlalchemy import select, update
from database.models import AchievementCatalog

logger = logging.getLogger(__name__)

ACHIEVEMENT_SEEDS = [
    # ── Progression ──────────────────────────────────────────────────────────
    {
        "id": 1,
        "name": "Dao Seeker",
        "description": "Reach Foundation Establishment realm.",
        "event_type": "realm_reached",
        "target_value": 2,
        "title_granted": "Foundation Cultivator",
        "stat_bonus": None,
        "emoji": "🌱",
    },
    {
        "id": 2,
        "name": "Core Master",
        "description": "Reach Core Formation realm.",
        "event_type": "realm_reached",
        "target_value": 3,
        "title_granted": "Core Master",
        "stat_bonus": {"cb_mult": 1.05},
        "emoji": "💠",
    },
    {
        "id": 3,
        "name": "Nascent Awakening",
        "description": "Reach Nascent Soul realm.",
        "event_type": "realm_reached",
        "target_value": 4,
        "title_granted": "Nascent Sovereign",
        "stat_bonus": {"cb_mult": 1.10},
        "emoji": "👁️",
    },
    {
        "id": 4,
        "name": "True Immortal",
        "description": "Reach the pinnacle — realm 10.",
        "event_type": "realm_reached",
        "target_value": 10,
        "title_granted": "True Immortal",
        "stat_bonus": {"cb_mult": 1.20, "bp_mult": 1.10},
        "emoji": "✨",
    },
    # ── Alchemy ──────────────────────────────────────────────────────────────
    {
        "id": 5,
        "name": "Pill Adept",
        "description": "Craft 100 pills successfully.",
        "event_type": "pills_crafted",
        "target_value": 100,
        "title_granted": "Pill Adept",
        "stat_bonus": {"alchemy_quality": 0.05},
        "emoji": "⚗️",
    },
    {
        "id": 6,
        "name": "Pill Emperor",
        "description": "Craft 1000 pills successfully.",
        "event_type": "pills_crafted",
        "target_value": 1000,
        "title_granted": "Pill Emperor",
        "stat_bonus": {"alchemy_quality": 0.10},
        "emoji": "🔥",
    },
    # ── Combat ───────────────────────────────────────────────────────────────
    {
        "id": 7,
        "name": "Arena Champion",
        "description": "Win 50 arena battles.",
        "event_type": "arena_wins",
        "target_value": 50,
        "title_granted": "Arena Champion",
        "stat_bonus": {"bp_mult": 1.05},
        "emoji": "⚔️",
    },
    {
        "id": 8,
        "name": "Undefeated",
        "description": "Achieve a 10-win streak in the arena.",
        "event_type": "win_streak",
        "target_value": 10,
        "title_granted": "Undefeated",
        "stat_bonus": {"evasion": 0.03},
        "emoji": "🛡️",
    },
    # ── Social ───────────────────────────────────────────────────────────────
    {
        "id": 9,
        "name": "Sect Founder",
        "description": "Create your own sect.",
        "event_type": "sect_founded",
        "target_value": 1,
        "title_granted": "Sect Master",
        "stat_bonus": None,
        "emoji": "🏯",
    },
    {
        "id": 10,
        "name": "War Hero",
        "description": "Participate in 10 sect wars.",
        "event_type": "sect_wars",
        "target_value": 10,
        "title_granted": "War Hero",
        "stat_bonus": {"bp_mult": 1.03},
        "emoji": "⚡",
    },
    # ── Economy ──────────────────────────────────────────────────────────────
    {
        "id": 11,
        "name": "Merchant Prince",
        "description": "Complete 100 marketplace sales.",
        "event_type": "market_sales",
        "target_value": 100,
        "title_granted": "Merchant Prince",
        "stat_bonus": None,
        "emoji": "💰",
    },
    {
        "id": 12,
        "name": "Jade Collector",
        "description": "Accumulate 10,000 Spirit Jade.",
        "event_type": "jade_accumulated",
        "target_value": 10000,
        "title_granted": "Jade Lord",
        "stat_bonus": None,
        "emoji": "💎",
    },
    # ── Beasts ───────────────────────────────────────────────────────────────
    {
        "id": 13,
        "name": "Beast Tamer",
        "description": "Capture 5 spirit beasts.",
        "event_type": "beasts_captured",
        "target_value": 5,
        "title_granted": "Beast Tamer",
        "stat_bonus": None,
        "emoji": "🐾",
    },
    {
        "id": 14,
        "name": "Menagerie",
        "description": "Own 10 spirit beasts simultaneously.",
        "event_type": "beasts_owned",
        "target_value": 10,
        "title_granted": "Beast Sovereign",
        "stat_bonus": None,
        "emoji": "🐉",
    },
    # ── Dungeons ─────────────────────────────────────────────────────────────
    {
        "id": 15,
        "name": "Dungeon Crawler",
        "description": "Clear 50 dungeon floors in total.",
        "event_type": "dungeon_floors",
        "target_value": 50,
        "title_granted": "Dungeon Crawler",
        "stat_bonus": {"bp_mult": 1.03},
        "emoji": "🗺️",
    },
    {
        "id": 16,
        "name": "Abyssal Conqueror",
        "description": "Clear the Abyssal Rift dungeon completely.",
        "event_type": "dungeon_abyssal",
        "target_value": 1,
        "title_granted": "Abyssal Conqueror",
        "stat_bonus": {"bp_mult": 1.05},
        "emoji": "🕳️",
    },
    # ── Special ──────────────────────────────────────────────────────────────
    {
        "id": 17,
        "name": "Hungry Ghost",
        "description": "Consume 500 pills.",
        "event_type": "pills_consumed",
        "target_value": 500,
        "title_granted": "Pill Glutton",
        "stat_bonus": {"cb_mult": 1.05},
        "emoji": "👻",
    },
    {
        "id": 18,
        "name": "Prestige Master",
        "description": "Prestige 3 times.",
        "event_type": "prestige_count",
        "target_value": 3,
        "title_granted": "Eternal Cultivator",
        "stat_bonus": {"cb_mult": 1.15, "bp_mult": 1.10},
        "emoji": "👑",
    },
    # ── Hidden ───────────────────────────────────────────────────────────────
    {
        "id": 19,
        "name": "Shadow",
        "description": "Unlock Shadow Mode as a VIP 3+ cultivator.",
        "event_type": "shadow_unlocked",
        "target_value": 1,
        "title_granted": "Shadow",
        "stat_bonus": None,
        "emoji": "🌑",
    },
    {
        "id": 20,
        "name": "Eternal One",
        "description": "Complete the Eternal Dao law.",
        "event_type": "dao_completed",
        "target_value": 1,
        "title_granted": "Eternal One",
        "stat_bonus": {"cb_mult": 1.20, "bp_mult": 1.15},
        "emoji": "☯️",
    },
    # v14.3 D-6a — Apex achievement, fired by core.celestial_engine.try_grant_apex
    # when realm 10 + sub_layer 9 + 100/100 Heavenly Daos + Mahayana 3/3 trials.
    # 500 jade reward + Apex Cultivator title — gives endgame players a real
    # capstone instead of "encheu e nada veio" ([jogadores]).
    {
        "id": 21,
        "name": "Apex of Cultivation",
        "description": "Reach the absolute peak of mortal cultivation: Realm 10 IX, all 100 Heavenly Laws, all 3 Celestial Trials.",
        "event_type": "apex_reached",
        "target_value": 1,
        "title_granted": "Apex Cultivator",
        "stat_bonus": {"cb_mult": 1.25, "bp_mult": 1.20},
        "emoji": "🌌",
    },
    # v16.0 — Continent Explorer. Placeholder: fires when the travel
    # mechanic ships in v16.0b (event_type `continents_visited` will be
    # incremented by `set_player_continent` whenever current != home for
    # the first time). For v16.0 the row exists in the catalog so the
    # mini-app achievements panel surfaces the carrot, but no player can
    # progress yet (Lei §1: honest disclosure via the locked icon).
    {
        "id": 22,
        "name": "Continent Explorer",
        "description": "Visit a continent different from your birthplace — for the first time.",
        "event_type": "continents_visited",
        "target_value": 2,
        "title_granted": "Wanderer",
        "stat_bonus": None,
        "emoji": "🗺️",
    },
    # v16.1 — Lineage Master. Triggers when a player's sect lands 10 Sect
    # War attacks against the ancestral rival lineage. `register_war_attack`
    # already returns `rival_hit=True` whenever the rival multiplier fires;
    # the war resolution path will increment `rival_sect_wars` once the
    # rival-win tracking lands (deferred — placeholder catalog row for now
    # so the mini-app achievements panel surfaces the carrot).
    {
        "id": 23,
        "name": "Lineage Master",
        "description": "Win 10 Sect Wars against your ancestral rival lineage.",
        "event_type": "rival_sect_wars",
        "target_value": 10,
        "title_granted": "Ancestral Vanquisher",
        "stat_bonus": None,
        "emoji": "⚔️",
    },
    # v16.2 — Path Walker. Fires the first time a player commits to a path
    # at R3+. v16.3 activates the increment hook: when the karma engine
    # crystallizes the path (either via apply_karma at R3+ or via the
    # breakthrough handler at the R3 transition), it fires
    # `check_achievements(player_id, "path_chosen", 1)` from
    # `karma_engine.crystallize_path_for_player`. The catalog row is
    # unchanged from v16.2.
    {
        "id": 24,
        "name": "Path Walker",
        "description": "Define your path — Righteous, Demonic, or Rogue — upon reaching Core Formation.",
        "event_type": "path_chosen",
        "target_value": 1,
        "title_granted": "Path Walker",
        "stat_bonus": None,
        "emoji": "☯️",
    },
    # v16.3 — Saint Walker. Reach +1000 karma (the spiritual extreme).
    # event_type `karma_reached_max` is fired by the karma engine's clamp
    # path once new_value == KARMA_MAX. Catalog row exists in v16.3;
    # achievement bus hook activates immediately so retroactive grants
    # work for any player who somehow already pushed past +1000 in the
    # accumulated audit log (unlikely at launch but safe).
    {
        "id": 25,
        "name": "Saint Walker",
        "description": "Reach +1000 karma — the cultivator's soul becomes a beacon.",
        "event_type": "karma_reached_max",
        "target_value": 1,
        "title_granted": "Saint Walker",
        "stat_bonus": {"tribulation_severity_mult": 0.95},
        "emoji": "✨",
    },
    # v16.3 — Heart Demon Conquered. Survive a Heart Demon divergence
    # quest (the v16.7 Forbidden Path narrative quest). Wire is deferred
    # to v16.7 since the quest itself isn't shipped yet; v16.3 only
    # seeds the catalog row + locked icon so the carrot is visible.
    {
        "id": 26,
        "name": "Heart Demon Conquered",
        "description": "Survive a Heart Demon divergence quest — the soul refused to bend.",
        "event_type": "heart_demon_conquered",
        "target_value": 1,
        "title_granted": "Heart Demon Conqueror",
        "stat_bonus": None,
        "emoji": "👁️",
    },
    # v16.3 — Karmic Devotee. 1000 lifetime karma_log entries. The audit
    # row write itself increments this counter (event_type `karma_event_logged`
    # fired from inside `apply_karma`). Long-tail achievement — a player
    # actively interacting with every karma-mutating system (combat, sect,
    # tribulation, meditation, quests) accumulates this over weeks/months.
    {
        "id": 27,
        "name": "Karmic Devotee",
        "description": "Have 1000 karma events recorded in your audit log — the river never sleeps.",
        "event_type": "karma_event_logged",
        "target_value": 1000,
        "title_granted": "Karmic Devotee",
        "stat_bonus": None,
        "emoji": "⚖️",
    },
    # v16.4 — Sect Heir. Accept a World Sect recruiter encounter (the Elder on
    # the pine) and be taken in as a disciple of one of the 9 eternal houses.
    # event_type `world_sect_joined` fires from
    # core.world_sects_engine.join_player_to_sect on the first NPC sect join.
    # The narrative trial is deferred to v16.4b; the catalog row + carrot ship
    # now. Modest sect-disciple bonus (Lei §3 — depth, not power-creep).
    {
        "id": 28,
        "name": "Sect Heir",
        # QoL 04/08 — o nome "Sect Heir" é histórico e MENTE (dispara ao ENTRAR;
        # o posto Heir é a #30). O nome fica (a string vive no unlocked_titles de
        # 19 jogadores); a descrição passa a dizer a verdade. Rename = launch-bound.
        "description": "Awarded the moment a Cultivation Sect accepted you. It marks the day you were taken in — not the Heir rank (that one is #30).",
        "event_type": "world_sect_joined",
        "target_value": 1,
        "title_granted": "Sect Heir",
        "stat_bonus": {"cb_mult": 1.05},
        "emoji": "🏯",
    },
    # v16.4c — Sect rank ladder achievements. Fired from the promotion engine
    # (core.world_sects_engine via the `sect_rank_reached` SET event — the value
    # is the absolute rank ordinal in SECT_RANKS, so re-firing only raises
    # progress). `target_value` = the ordinal of the gated rank: elder=3, heir=4.
    # stat_bonus=None: the achievement-bonus pipeline is currently unwired (no
    # caller of get_achievement_stat_bonuses), and rank perks are disclosed-but-
    # deferred to the wipe (Lei §5) — so the reward here is the TITLE + prestige,
    # not power-creep on the freshly-balanced game (Lei §3). NOTE: #28's title
    # 'Sect Heir' fires on JOINING (mis-named historically); these use distinct
    # titles ('Sect Pillar' / 'Sect Successor') so title dedup never collides.
    {
        "id": 29,
        "name": "Sect Pillar",
        "description": "Ascend to Elder of your house — one of the pillars that hold up its sky.",
        "event_type": "sect_rank_reached",
        "target_value": 3,
        "title_granted": "Sect Pillar",
        "stat_bonus": None,
        "emoji": "🏛️",
    },
    {
        "id": 30,
        "name": "Sect Successor",
        "description": "Reached the rank of Heir 传人 inside your Cultivation Sect — the highest seat of the house.",
        "event_type": "sect_rank_reached",
        "target_value": 4,
        "title_granted": "Sect Successor",
        "stat_bonus": None,
        "emoji": "👑",
    },
    # Quick-wins 2026-06-10 — Demon Sovereign. The demonic mirror of #25 Saint
    # Walker: reach −1000 karma (the karmic floor). Asked for by [jogador] AND
    # [jogador] on the SAME day (09.06) — Saint Walker (+1000) had no negative
    # twin. event_type `karma_reached_min` is fired by the karma engine's clamp
    # path once new_value crosses −KARMA_MIN (mirrors `karma_reached_max`), with
    # a retroactive grant in sync_player_snapshot for the ≥2 cultivators already
    # at the floor (the engine fires it once new_value crosses KARMA_MIN, −1000).
    # stat_bonus=None on purpose: the achievement-bonus pipeline is
    # unwired (no caller of get_achievement_stat_bonuses) and wiring a passive
    # buff is wipe-bound (Lei §5) — the reward here is the TITLE + the conquest,
    # never a pre-wipe balance shift (Lei §4). Aditivo, wipe-safe.
    {
        "id": 31,
        "name": "Demon Sovereign",
        "description": "Reach −1000 karma — the cultivator's heart becomes a devouring abyss.",
        "event_type": "karma_reached_min",
        "target_value": 1,
        "title_granted": "Demon Sovereign",
        "stat_bonus": None,
        "emoji": "👹",
    },
    # ── Onda 5 Fase 3 — Ecos Míticos 六耳猕猴 (LW-05). Each legendary being grants a
    # permanent COSMETIC title on the first win in the Reinos Exploráveis (Lei §4/§5:
    # no jade, no technique, no balance — stat_bonus None, survives the wipe). The
    # event_type / title_granted MUST mirror core/exploration_engine.MYTHIC_ECHOES.
    # Fired idempotently from resolve_exploration_from_duel on the duel win.
    {
        "id": 32,
        "name": "Reflexo do Vazio",
        "description": "Derrote o Macaco de Seis Orelhas (六耳猕猴) — o teu próprio reflexo — nos Reinos Exploráveis.",
        "event_type": "mythic_liu_er",
        "target_value": 1,
        "title_granted": "Reflexo do Vazio",
        "stat_bonus": None,
        "emoji": "🪞",
    },
    {
        "id": 33,
        "name": "Voz do Bai Ze",
        "description": "Supere o Bai Ze (白泽), a fera onisciente, nos Reinos Exploráveis.",
        "event_type": "mythic_bai_ze",
        "target_value": 1,
        "title_granted": "Voz do Bai Ze",
        "stat_bonus": None,
        "emoji": "📖",
    },
    {
        "id": 34,
        "name": "Fome do Taotie",
        "description": "Vença o Taotie (饕餮), o devorador insaciável, nos Reinos Exploráveis.",
        "event_type": "mythic_taotie",
        "target_value": 1,
        "title_granted": "Fome do Taotie",
        "stat_bonus": None,
        "emoji": "👹",
    },
    {
        "id": 35,
        "name": "Jugo do Dragão",
        "description": "Dome o Dragão Celestial (辰龙) nos Reinos Exploráveis.",
        "event_type": "mythic_chen_long",
        "target_value": 1,
        "title_granted": "Jugo do Dragão",
        "stat_bonus": None,
        "emoji": "🐉",
    },
]


async def run_achievement_seeds(session):
    existing_ids = set((await session.execute(select(AchievementCatalog.id))).scalars().all())

    added = 0
    for seed in ACHIEVEMENT_SEEDS:
        if seed["id"] in existing_ids:
            continue
        session.add(AchievementCatalog(**seed))
        added += 1

    if added:
        logger.info("🏆 Seeded %d achievements", added)

    # ── QoL 04/08 (report [jogador]) — FORCE-SYNC de texto ─────────────────────
    # O runner acima é insert-only: mudar `description` no seed NUNCA chega a uma
    # linha que já existe em prod. Este bloco re-aplica o texto a cada boot
    # (padrão QI_COSTS/INTENT_AFFINITIES do combat_seeds).
    #
    # O problema que ele paga: a #28 chama-se "Sect Heir" mas dispara ao ENTRAR
    # numa seita — enquanto o posto REAL `heir` é medido pela #30. Em produção as
    # populações provam a confusão: main tem 19 com a #28 e 13 com sect_rank='heir'
    # (e 2 portadores da #28 nem estão em seita nenhuma). O `title_granted` NÃO se
    # toca — a string vive no `unlocked_titles` de 19 jogadores e renomeá-la
    # órfãozaria os registros; o rename player-facing é launch-server-bound.
    # O que muda é a DESCRIÇÃO, que passa a dizer exatamente o que a conquista é.
    TEXT_SYNC = {
        28: "Awarded the moment a Cultivation Sect accepted you. It marks the "
            "day you were taken in — not the Heir rank (that one is #30).",
        30: "Reached the rank of Heir 传人 inside your Cultivation Sect — the "
            "highest seat of the house.",
    }
    for ach_id, desc in TEXT_SYNC.items():
        if ach_id in existing_ids:
            await session.execute(
                update(AchievementCatalog)
                .where(AchievementCatalog.id == ach_id)
                .values(description=desc)
            )

    await session.commit()
