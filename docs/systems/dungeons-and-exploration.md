# Dungeons and exploration

Two ways into danger: **dungeons**, portals with floors and a boss at the bottom,
and **exploration**, a walk into the wilds of a continent guided by the
cultivator's own senses.

## Dungeons

The catalogue has 23<!--#len:database/seeds/dungeon_seeds.py:DUNGEON_SEEDS--> dungeons
(`database/seeds/dungeon_seeds.py`), each open to a band of realms.

- **A run.** The cultivator enters at one of four<!--#len:core/dungeon_quest_engine.py:DIFF_ORDER-->
  difficulties — easy, normal, hard, nightmare — and descends floor by floor; each
  floor costs Qi and is fought automatically, and the last one holds a **boss**,
  fought by hand as a turn-based duel ([combat](combat.md#a-duel-round-by-round)),
  its archetype chosen by the dungeon (`get_dungeon_boss_archetype()` in
  `core/npc_loadouts.py`). A dungeon can also be **swept** once it is mastered.
- **One run at a time.** With `masmorra_unica`, a cultivator inside one dungeon
  cannot open another: `active_run()` in `core/dungeon_run_engine.py` is the one
  query all five ways in and out of a run read.
- **Anchored to the land.** With `dungeons_regionais`, each portal belongs to a
  continent (`DungeonCatalog.continent`; an empty value means everywhere): a
  cultivator sees and enters only the portals of the continent they stand on, and
  the screen says what lies beyond the horizon (`region_gate()`,
  `elsewhere_summary()` in `core/dungeon_regions.py`). A hard or nightmare run
  then has a 12%<!--#val:core/dungeon_regions.py:REGIONAL_BONUS_CHANCE--> chance of an extra material native to that
  continent.
- **Dungeon quests** — stories tied to one dungeon, with a minimum difficulty and,
  when repeatable, a cooldown (`core/dungeon_quest_engine.py`).

`core/masmorra.py` owns what the dungeon screen confirms: where the current
expedition is (`current_floor` of how many), which floors it has really cleared,
and the best reach in any difficulty — kept apart, never summed into one
made-up number.

## Exploration

`core/exploration_engine.py`. The cultivator enters the continent they are in
and reads it with their **divine sense** (`core/divine_sense_engine.py`): each
look offers 3<!--#env:DIVINE_BASE_DIRECTIONS--> directions, one more at a perception of
70<!--#env:DIVINE_PERCEPTION_T1--> and another at 160<!--#env:DIVINE_PERCEPTION_T2-->, and each direction is a
**clue** — a hint of what is there, never the full reveal:

| clue | what waits |
|---|---|
| a cache | materials, safely |
| danger | a quick fight |
| a choice | a moral fork — aid the wounded elder, open the sealed cache, guide the lost disciple… — that moves karma |
| ominous | a **hidden monster**: an NPC cultivator of the world, rare, more likely with luck (up to 16%<!--#env:DIVINE_HIDDEN_CAP--> of a clue) |
| mythic | a **mythic echo** — one of four<!--#len:core/exploration_engine.py:MYTHIC_ECHOES--> legendary creatures, rarer still (at most 5%<!--#env:DIVINE_MYTHIC_CAP-->), and only from depth 3<!--#env:DIVINE_MYTHIC_MIN_DEPTH--> |

Every step costs Qi and goes one level deeper, and what is found goes into an
expedition **bag**. Then the choice the loop is built on: **retreat** and keep
everything (`retreat()`), or **go deeper** for more — and risk dying there, which
loses most of the bag. A continent's state can make its roads more dangerous
([living world](living-world.md#continents-and-their-states)), and formations can
protect an expedition ([crafting](crafting.md#formations)).

## Where it lives

| | |
|---|---|
| engines | `core/dungeon_regions.py`, `core/dungeon_run_engine.py`, `core/dungeon_quest_engine.py`, `core/masmorra.py`, `core/exploration_engine.py`, `core/divine_sense_engine.py` |
| chat | `/dungeons`, `/explorar` |
| client API | `/api/miniapp/dungeons/`, `/api/miniapp/world/explore_scan`, `/api/miniapp/world/explore_advance`, `/api/miniapp/world/explore_retreat` |
| catalogues | `DungeonCatalog`, `DungeonQuestCatalog` (`database/seeds/dungeon_seeds.py`, `database/seeds/dungeon_quest_seeds.py`) |
| data | `PlayerDungeon`, `PlayerDungeonQuest`, `PlayerExploration` |
| flags | `dungeons_regionais`, `masmorra_unica` |
| tests | `scripts/_sabota_as_masmorras.py`, `scripts/_test_qol_relatos.py` |
