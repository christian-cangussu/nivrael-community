# Cultivation

The spine of the game: a cultivator gathers Qi, deepens their **cultivation
base**, and breaks through realm after realm — Mortal to True Immortal — while
the world keeps moving when they are away.

## The realms

There are eleven<!--#realms--> realms (`REALM_NAMES` in `config.py`), each with
9<!--#sub_layers--> sub-layers: Mortal, Qi Condensation, Foundation Establishment, Core
Formation, Nascent Soul, Soul Transformation, Void Refinement, Body Integration,
Mahayana, Tribulation Transcendence and True Immortal. The client shows each
realm's name and colour from the same index.

The cultivation base needed for the next sub-layer is `get_threshold()` in
`config.py`: a base of 1,000<!--#env:BASE_THRESHOLD-->, multiplied by
4<!--#env:THRESHOLD_GROWTH_PER_REALM--> for every realm and by another
15%<!--#env:THRESHOLD_GROWTH_PER_SUBLAYER--> for every sub-layer. Each world can slow the
whole curve with its `cultivation_speed` knob ([per-world balance](../architecture.md#per-world-balance)).

## Gathering Qi

- **The tick.** Every 30<!--#env:TICK_INTERVAL_SECONDS--> seconds the scheduler runs
  `process_tick()` (`core/game_logic.py`) for every cultivator: cultivation base
  from `calculate_cb_per_tick()` — the spirit root, the realm's multiplier
  (`REALM_MULTIPLIERS`), buffs, equipment, the sect, the companion beast, the Dao,
  a Dao partner, achievements — and Qi regeneration.
- **Offline.** Progress keeps accruing while the player is away, up to
  4<!--#env:OFFLINE_CAP_SECONDS/3600--> hours (`OFFLINE_CAP_SECONDS`,
  `calculate_offline_progress()`).
- **Meditation** multiplies the gain for a while. Four<!--#meditation_types--> kinds, in
  `MEDITATION_TYPES` (`config.py`):

  | kind | multiplier | lasts | opens at |
  |---|---|---|---|
  | light | ×1.5<!--#val:config.py:MEDITATION_TYPES['light']['multiplier']--> | 30<!--#val:config.py:MEDITATION_TYPES['light']['duration_minutes']--> min | the start |
  | deep | ×2.5<!--#val:config.py:MEDITATION_TYPES['deep']['multiplier']--> | 60<!--#val:config.py:MEDITATION_TYPES['deep']['duration_minutes']--> min, costs Qi | the start |
  | void | ×6<!--#val:config.py:MEDITATION_TYPES['void']['multiplier']--> | 120<!--#val:config.py:MEDITATION_TYPES['void']['duration_minutes']--> min | Nascent Soul |
  | celestial | no cultivation — Dao comprehension ×20<!--#val:config.py:MEDITATION_TYPES['celestial_dao']['dao_fragment_mult']--> | 480<!--#val:config.py:MEDITATION_TYPES['celestial_dao']['duration_minutes']--> min | Mahayana |

  A finished session is credited even if nobody opens the game
  (`credit_meditation_if_earned()`, and the meditation sweep job).
- **The cave.** One per cultivator (`core/cavern_engine.py`): it gathers Qi on its
  own, capped at 10<!--#env:CAVERN_CAP_HOURS--> hours, and holds one formation that can
  boost it or bring Dao comprehension. Chat: `/caverna`.

## Birth

What a soul is born with is **fate**, not a menu:

- **Spirit root** — the grade that sets how fast you cultivate:
  five<!--#spirit_roots--> grades in `SPIRIT_ROOTS` (`config.py`), from Low
  (×1<!--#val:config.py:SPIRIT_ROOTS['Low']['multiplier']-->, the most common) to Heavenly
  (×5<!--#val:config.py:SPIRIT_ROOTS['Heavenly']['multiplier']-->, a weight of
  0.01<!--#val:config.py:SPIRIT_ROOTS['Heavenly']['weight']--> in a hundred). `roll_spirit_root()`.
- **Root composition** — which of the 12<!--#len:core/root_engine.py:ROOT_ELEMENTS--> elements the
  root carries (the five of the Wuxing, and rare variants). Derived from the
  player's id and a salt, shown to the player; it does not change a number yet
  (`core/root_engine.py`).
- **Race** — one of six<!--#len:core/race_engine.py:RACES--> peoples, humans being the common
  one by design; also derived and shown only, behind `racas`
  (`core/race_engine.py`).

The salts (`RACE_HASH_SALT`, `ROOT_ELEMENT_HASH_SALT`) must be chosen before
anyone is born in a world: changing them later rewrites destinies.

## Breakthroughs

`check_breakthrough()` (`core/game_logic.py`) moves a cultivator up when the base
reaches the threshold — except at the gates, where something else must happen
first. The player is never stuck without being told what:

| where | the gate | the engine |
|---|---|---|
| the first breakthroughs | with `breakthrough_trials`, a ceremony: **consolidate** (safe) or **force** (a gamble for a head start — 55%<!--#env:BT_FORCE_BASE_CHANCE--> before penalties, worse when the body lags the realm) | `core/breakthrough_trials_engine.py` |
| Qi Condensation → Foundation Establishment | the **foundation trial**: soul, perception and luck tested; the foundation comes out in one of five<!--#len:core/foundation_engine.py:FOUNDATION_QUALITIES--> qualities, from ×1<!--#val:core/foundation_engine.py:FOUNDATION_QUALITIES['low']['stat_mult']--> to ×2<!--#val:core/foundation_engine.py:FOUNDATION_QUALITIES['sacred']['stat_mult']--> on stats | `core/foundation_engine.py` |
| Foundation Establishment → Core Formation | the **golden core**: four<!--#len:core/golden_core_engine.py:CORE_QUALITIES--> qualities, and the foundation caps how good the core can be | `core/golden_core_engine.py` |
| from Nascent Soul on | **heavenly tribulations** — three<!--#len:core/tribulation_engine.py:STRATEGIES--> strategies (resist, dodge, absorb), thunder rounds, then a heart demon (three questions) and the Dao in the highest realms | `core/tribulation_engine.py` |
| Body Integration → Mahayana | the body must have reached transformation 3<!--#body_gate_level--> | `core/body_tempering_engine.py` ([body](body.md)) |
| inside Mahayana | **celestial trials** at three<!--#val:core/celestial_engine.py:MAX_TRIALS--> sub-layers; a failure costs 50%<!--#val:core/celestial_engine.py:FAILURE_CB_LOSS--> of the base within the realm and a 6<!--#val:core/celestial_engine.py:FAILURE_COOLDOWN_HOURS-->-hour wait | `core/celestial_engine.py` |
| the last sub-layer of True Immortal | the summit: the **apex** (`is_apex()`, `try_grant_apex()`), then [prestige](progression.md#prestige-and-rebirth) | `core/celestial_engine.py` |

The foundation can also be restarted (`/recomeco`, once, for new players) or
deliberately broken and rebuilt (`/quebrar_fundacao`) — `handlers/foundation.py`.

## The rest of the soul

Shown to the player as data — most of them read numbers the cultivator already
has, and none adds a hidden rule:

- **Lifespan** (`core/lifespan_engine.py`) — each realm raises the ceiling, from
  100<!--#val:core/lifespan_engine.py:REALM_LIFESPAN[0]--> years for a mortal to none for an
  immortal. Only the [forbidden path](techniques.md#the-forbidden-path) spends it.
- **Mind sea** (`core/mind_sea_engine.py`) — the depth of soul and perception,
  in four<!--#len:core/mind_sea_engine.py:MIND_SEA_TIERS--> tiers.
- **Dao heart** (`core/dao_heart_engine.py`) — how firm the will is, and how well
  the cultivator's acts match their path ([sects and paths](sects-and-paths.md#karma-and-paths)).

## The first hour

With `ftue_espinha`, `core/ftue_engine.py` guides a new cultivator through
meditating, the body, the garden and the first breakthrough. It stores nothing:
each step is read from the player's state, and steps that a world does not have
are skipped. Chat: `/guia`.

## Where it lives

| | |
|---|---|
| engines | `core/game_logic.py`, `core/cultivator_soul.py` ([architecture](../architecture.md#the-cultivator-soul)), `core/breakthrough_trials_engine.py`, `core/foundation_engine.py`, `core/golden_core_engine.py`, `core/tribulation_engine.py`, `core/celestial_engine.py`, `core/cavern_engine.py`, `core/ftue_engine.py`, `core/root_engine.py`, `core/race_engine.py`, `core/lifespan_engine.py`, `core/mind_sea_engine.py`, `core/dao_heart_engine.py` |
| chat | `/status`, `/cultivar`, `/meditar`, `/cerimonia`, `/tribulacao`, `/celestial`, `/recomeco`, `/caverna`, `/guia` |
| client API | `/api/miniapp/meditate/`, `/api/miniapp/breakthrough/`, `/api/miniapp/foundation/`, `/api/miniapp/core/attempt`, `/api/miniapp/tribulation/`, `/api/miniapp/celestial/`, `/api/miniapp/apex/` |
| data | `Player` (realm, sub-layer, base, Qi, foundation and core quality, …), `PlayerBuff`, `Tribulation`, `PlayerCavern` |
| flags | `breakthrough_trials`, `ftue_espinha`, `racas`; `progressao_visivel` for the before → after of every advance |
