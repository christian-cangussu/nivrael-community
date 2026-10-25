# Quests, rewards and rebirth

The goals the game hands a cultivator, the marks it leaves when they are met, and
what happens at the very end of the road.

## Quests

`core/quest_engine.py` keeps the quest log (`QuestCatalog`, `PlayerQuest`; the
catalogue has 48<!--#len:database/seeds/quests_seeds.py:QUEST_SEEDS--> quests in `database/seeds/quests_seeds.py`):

- **daily** and **weekly** quests, renewed by the scheduler at midnight UTC and on
  Mondays (`ensure_daily_quests()`, `reset_daily_quests_global()`);
- **sect quests**, only for members of a house (`ensure_sect_quests()`), which are
  how contribution and the core shelf of the library are earned
  ([sects and paths](sects-and-paths.md#the-nine-houses));
- progress is counted by `track_quest()`, called by every engine with the kind of
  deed — "craft pills", "win a duel", "clear a floor"… — so a new system makes
  its deeds count by calling it;
- a quest may carry a **choice** on claim — mercy, power or greed — that moves
  karma ([karma and paths](sects-and-paths.md#karma-and-paths));
- the **login streak** rewards coming back on consecutive days, at the milestones
  of `STREAK_MILESTONES` (`update_login_streak()`).

The stories the world offers on its own are [storylets](living-world.md#stories-and-bounties);
the dungeon quests live with the [dungeons](dungeons-and-exploration.md#dungeons).

## Achievements and titles

`core/achievement_engine.py`: 35<!--#len:database/seeds/achievement_seeds.py:ACHIEVEMENT_SEEDS--> achievements
(`database/seeds/achievement_seeds.py`). Engines report events with
`check_achievements()` — counted ones (wins, crafts) add up, state ones (realm
reached, beasts owned) compare the current value. An achievement can give a
**title**, which the cultivator wears before their name (`equip_title()`), and
some give a lasting bonus; `bonus_display()` is the one truth of what an
achievement announces, read by both screens.

## The battle pass

`core/bp_engine.py`: a season of 22<!--#len:database/seeds/battle_pass_seeds.py:BP_MISSIONS--> missions
(`database/seeds/battle_pass_seeds.py`) fed by the same deeds
(`update_bp_mission()`) — one-time missions are worth more points than daily or
weekly ones — and the points set the pass tier (`recalculate_bp_tier()`). The
premium side of the pass is a purchase, off in this edition
([economy](economy.md#real-money)).

## Prestige and rebirth

At the last sub-layer of True Immortal (`can_prestige()` in
`core/prestige_engine.py`), a cultivator may be **reborn** (`process_prestige()`):

- **reset** — realm and sub-layer, cultivation base, foundation, golden core, Qi
  and its capacity, every technique but one the player keeps, and unfinished Dao
  fragments;
- **kept** — spirit stones and jade, artifacts, the ring, cauldrons, beasts,
  completed Dao laws, titles;
- **gained** — a prestige level, which makes all later cultivation faster
  (`get_prestige_multiplier()`), and prestige points.

The path is derived again from the karma that crosses the lives, and the screen
warns, before the rebirth, what will change — including the dungeons a regional
world will no longer show (`rebirth_portal_warning()` in `core/dungeon_regions.py`).

Prestige points are spent in the **prestige pavilion**
(`core/prestige_shop_engine.py`): 7<!--#len:core/prestige_shop_engine.py:PRESTIGE_SHOP_CATALOG--> items in three
kinds — permanent "soul echoes" that survive every rebirth, one-shot gifts, and
titles inscribed in the heavens. `re_apply_persistent_perks()` restores the
permanent ones after each rebirth.

## Dao partners

Two cultivators may become **Dao partners** (`core/partner_engine.py`): one
proposes with a jade ring, the other answers. While both have been online
recently they cultivate faster together (`get_partner_cb_mult()`), and their
intimacy grows. Cutting the bond leaves a heartbreak — a cultivation penalty and a
wait before another proposal (`apply_heartbreak()`).

## Where it lives

| | |
|---|---|
| engines | `core/quest_engine.py`, `core/achievement_engine.py`, `core/bp_engine.py`, `core/prestige_engine.py`, `core/prestige_shop_engine.py`, `core/partner_engine.py` |
| chat | `/missoes`, `/conquistas`, `/renascer`, `/prestige`, `/loja_prestige` |
| client API | `/api/miniapp/quests`, `/api/miniapp/achievements/list`, `/api/miniapp/battle_pass`, `/api/miniapp/rebirth/preview`, `/api/miniapp/rebirth/attempt`, `/api/miniapp/prestige/shop`, `/api/miniapp/partner/` |
| data | `QuestCatalog`, `PlayerQuest`, `LoginStreak`, `AchievementCatalog`, `PlayerAchievement`, `BattlePassMission`, `PlayerBPMission`, `PrestigeLog`, `PlayerPrestigePurchase`, `DaoPartner`, `DaoPartnerProposal` |
| tests | `scripts/_test_qol0809.py` (the rebirth warning) |
