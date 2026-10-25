# Techniques

Techniques are the arts a cultivator fights and cultivates with. They are
**scarce on purpose**: a cultivator ends up with a handful, and each one weighs.
The main way to learn them is to belong to a house; the rest come from the
world, rarely.

How techniques behave in a fight — mastery, grades, stances, slots, intent — is
in [combat](combat.md#techniques-in-a-fight). This page is about where they come
from and what they cost.

## The sect library

With `biblioteca_seitas`, each of the nine NPC sects opens a library in shelves
(`core/sect_library_engine.py`). A shelf opens with the member's **rank** in the
house, and an art on it costs **contribution** — earned by serving the house,
never bought ([sects and paths](sects-and-paths.md#the-nine-houses)):

| shelf | opens at | costs |
|---|---|---|
| outer | disciple | nothing — the house's lesson, and a new art when you join |
| inner | inner disciple | 750<!--#env:LIB_T2_CP--> contribution |
| core | core disciple, and one quest of the house done | 3,000<!--#env:LIB_T3_CP--> contribution |

With `estantes_seladas`, two **sealed shelves** sit above them:

- the **signature** shelf, for elders — 6,000<!--#env:SEL_T4_CP--> contribution;
- the **hidden** shelf, for the heir — no contribution, but karma that walks the
  house's own road (250<!--#env:SEL_KARMA_MIN--> or more, aligned) and a **rite**: a duel
  the house sets (`start_hidden_rite()`); a defeat waits
  24<!--#env:SEL_RITE_COOLDOWN_H--> hours before another try.

`library_tiers()` is the one truth of which shelves are visible, read by every
screen and by `learn_library_technique()` alike. Leaving the house locks the
arts of its core shelf and above again (`lock_core_arts_on_leave()`). Chat:
`/biblioteca`.

## Scrolls

A technique can also arrive as a **scroll** — from dungeons, NPC hunts, quests or
the arena. With `escassez_scrolls` (`core/scroll_economy_engine.py`):

- random scroll drops are cut to 15%<!--#env:SCR_DROP_MULT--> of what they were, and the
  arena gives one every 50<!--#env:SCR_ARENA_WIN_STEP--> wins;
- a scroll you cannot or do not want to learn is not dead weight: **donate** it
  to your house for contribution (25<!--#env:SCR_DONATE_CP_T1--> to 200<!--#env:SCR_DONATE_CP_T4-->
  by tier, up to 500<!--#env:SCR_DONATE_DAILY_CAP--> a day), or **burn** it for
  experience in the art's own intent (25<!--#env:SCR_BURN_XP_T1--> to
  200<!--#env:SCR_BURN_XP_T4-->; the rarest also give a Dao fragment).

`get_scroll_actions()` says, before you choose, what each action is worth.
Chat: `/pergaminhos`.

## Legacy caves

With `legacy_caves`, when a house seeks an inheritance in the
[world pulse](living-world.md#the-world-pulse), there is a
20%<!--#env:LGC_OPEN_CHANCE--> chance that an ancient tomb awakens in a continent for
72<!--#env:LGC_TTL_H--> hours (`maybe_open_cave()` in `core/legacy_cave_engine.py`). Inside
waits the echo of one of five<!--#len:core/legacy_cave_engine.py:CAVE_HOUSES--> legendary cultivators,
one per continent. Each player gets one attempt per opening — a duel against the
echo; a victory brings spirit stones and a 15%<!--#env:LGC_ART_CHANCE--> chance of the
echo's own art, the rarest source of the game, guaranteed by the
3<!--#env:LGC_PITY_CLEARS-->rd clear of the same house. Between openings the world rests
48<!--#env:LGC_GLOBAL_COOLDOWN_H--> hours.

## The forbidden path

With `forbidden_path` (`core/forbidden_path_engine.py`), the demonic house keeps
a **forbidden vault** above its sealed shelves. Its arts are not bought: they
are paid in karma and in **years**.

- To enter: the heir of the demonic house, on the demonic path, with aligned
  karma of 500<!--#env:FP_KARMA_MIN--> or more, and the rite registered.
- Each use costs 20<!--#val:core/karma_engine.py:KARMA_EVENTS['forbidden_tech_use']*-1--> karma and
  burns years of the cultivator's own lifespan ceiling — a fraction of it, at
  least 1<!--#env:FP_BURN_MIN_YEARS--> year. When the ceiling is spent, the art refuses.
  Rising a realm raises the ceiling: the way out is up, never "stop". Forbidden
  arts only count inside a duel.
- **The heart-demon rite** (`/coracao`): a duel against your own reflection.
  Win, and you cross over (your path crystallises anew) or reaffirm it; lose, and
  the heart bites your soul strength — and you may return after
  24<!--#env:FP_RITE_COOLDOWN_H--> hours.

## Comprehension

A technique's **mastery** is also its comprehension: it grows with use in
fights, and the passive arts — meditation and interior techniques — grow while
the cultivator meditates (`award_passive_mastery_xp()` in
`core/technique_engine.py`). The screen says how each art grows
(`technique_gain_key()`), and whether its element resonates with the
cultivator's root (`technique_root_resonance()`, flavour only).

## Where it lives

| | |
|---|---|
| engines | `core/sect_library_engine.py`, `core/scroll_economy_engine.py`, `core/legacy_cave_engine.py`, `core/forbidden_path_engine.py`, `core/technique_engine.py`, `learn_sect_technique()` in `core/world_sects_engine.py` |
| catalogue | `TechniqueCatalog`, seeded by `database/seeds/combat_seeds.py` |
| chat | `/tecnicas`, `/biblioteca`, `/pergaminhos`, `/coracao` |
| client API | `/api/miniapp/world/sect_library`, `/api/miniapp/combat/`, `/api/miniapp/heart_demon/` |
| data | `PlayerTechnique`, `PlayerSectTechnique`, `WorldEvent` (an open cave) |
| flags | `biblioteca_seitas`, `estantes_seladas`, `escassez_scrolls`, `legacy_caves`, `forbidden_path` |
| tests | `scripts/_test_tec1_library.py`, `scripts/_test_tec2_scrolls.py`, `scripts/_test_tec3_selado.py`, `scripts/_test_tec4_caves.py`, `scripts/_test_tec5_forbidden.py` |
