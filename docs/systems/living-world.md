# The living world

The world does not wait for the player. Houses act, the heavens send tides and
meteors, continents prosper and fall under siege, NPC cultivators march and
hunt, and the chronicle writes it all down — on a clock, in every world, even
when nobody is online.

Most of this is built in steps that ride the same heartbeat, each behind its
own flag. The world's geography comes first.

## Continents and travel

Five<!--#len:core/continent_engine.py:CONTINENT_KEYS--> continents (`core/continent_engine.py`): **Línghé**, the sacred
centre where everyone is born; **Qiānhé**, the north of the body and of ores;
**Yǎnshān**, the land of herbs; **Fēnghuǒ**, of forges and fighting; and
**Mòyǔ**, open only to the demonic path. Each player has a home continent (where
they were born) and a current one (where they are).

**Travel** (`core/travel_engine.py`) moves the cultivator: it costs spirit stones
— 200<!--#env:TRAVEL_COST_BASE--> plus 50<!--#env:TRAVEL_COST_PER_REALM--> per realm — and then waits
4<!--#env:TRAVEL_COOLDOWN_HOURS--> hours before the next trip (`can_travel()`, `do_travel()`).
Changing continent changes everything local at once: the plaza, the bounty
board, the dungeons a regional world shows, the market's prices, the people met.

**The plaza** (`/praca`) is the local square of the continent you stand on: the
people you can meet and fight, the bounty board, the local events, a story
offered by a stranger, the caravan, your rival.

## The world pulse

Every 6<!--#env:WORLD_PULSE_INTERVAL_HOURS--> hours, `run_world_pulse()` in
`core/world_pulse_engine.py` gives each of the nine houses one **beat**. A house
chooses among six<!--#len:core/world_pulse_engine.py:PULSE_ACTIONS--> actions — recruit, fortify, claim a
node, raid its rival, seek an inheritance, or suffer internal strife — weighed by
its soul and its situation (`score_actions()`), with a little noise. Only
2<!--#env:WORLD_PULSE_MAX_MAJOR_PER_TICK--> major beats happen per pulse.

Houses **remember**: a raid leaves a grudge (`bump_grudge()`), grudges fade a
little every beat, and a grudge strong enough sends the house against its
offender instead of its ancestral rival (`grudge_target()`).

Everything that happens is written to the **chronicle** (`WorldChronicle`,
`/cronica`), one line per event, in every language — the same chronicle the
public page `/play` shows.

After the houses, the other systems of the world take their step **on the same
pulse**, in this order, each in its own transaction so one failing never stops
the rest: the heavens (`director_pulse()`), the continents' states
(`sync_region_states()`), reputation and the rival (`decay_region_rep()`,
`rival_pulse()`), the market report of the professions, the people of the jianghu
(`jianghu_pulse()`) and the cities.

## Events of the heavens

With `tiandao_director` (`core/tiandao_engine.py`), each pulse has a
35%<!--#env:TIANDAO_SPAWN_CHANCE--> chance of an event with a **place, a timer and a
consequence** — never two at once:

- a **beast tide** in a continent: for 48<!--#env:TIANDAO_TIDE_HOURS--> hours, every PvE victory
  there counts towards holding it back (40<!--#env:TIANDAO_TIDE_GOAL--> of them); held, it pays;
  ignored, the roads close — travel costs ×1.5<!--#env:TIANDAO_TRAVEL_PENALTY_MULT--> — and the
  continent is besieged;
- a **celestial meteor** that can be mined for 72<!--#env:TIANDAO_METEOR_HOURS--> hours
  (`mine_meteor()`), once every 6<!--#env:TIANDAO_METEOR_COOLDOWN/3600--> hours per cultivator.

Separately, an admin can start a **celestial event** for the whole world — a
meteor shower, a convergence of the Dao, a spirit tide, an immortal auction or a
demonic invasion, the 5<!--#len:database/seeds/events_seeds.py:CELESTIAL_EVENTS--> kinds of `database/seeds/events_seeds.py` —
each a multiplier for some hours (`CelestialEvent`, `/eventos`). Nothing starts
one on its own; the scheduler only ends them when their time is up and announces
it.

## Continents and their states

With `estados_regionais` (`core/region_state_engine.py`), each continent lives in
one of five<!--#len:core/region_state_engine.py:VALID_STATES--> states — prosperous, tense, besieged, in festival, or
occupied by a house — and the state **changes numbers the player feels**: the
local market's prices, the danger of exploring, the gathering of Qi.
`region_overrides()` is the one helper all of them read, and every screen that a
state changes says so. The heavens' events are the cause; the state is the
lasting effect. News of a distant continent reaches you later, the farther it is.

## The cities

With `cidades` (`core/city_engine.py`), each continent has one named city — five
in all — with a face, a voice in the chronicle, and a **request** of the day
(an *encargo*) that changes on its own clock.

## Caravans and the origin of things

With `caravana` (`core/caravan_engine.py` — it also needs `cidades` and
`dungeons_regionais`), the game says **where each material is born**
(`material_origin()`, `origin_line()`): a material that drops only in some
continents is a geographical wall. A city's caravan can bring one from another
continent by **barter** — paid in materials, never in spirit stones:
3<!--#env:CRV_LOAD_UNITS--> units per load, arriving after 6<!--#env:CRV_ETA_HOURS--> hours, one load
open at a time (`send_load()`). The load is credited when it arrives, by whoever
looks first (`credit_arrived()`).

## NPC cultivators

The world has a **persistent population** (`core/npc_cultivator_engine.py`):
cultivators with a continent, a sect, a path, a realm and karma. Each continent is
kept at 6<!--#env:NPC_CULTIVATOR_BOOTSTRAP_PER_CONTINENT--> at least, and the rest are anonymised **echoes** of
real players' public combat state — never a name, never an id. A cultivator meets
a fair opponent within one realm of their own (`pick_encounter_npc()`); after a
victory comes the choice to spare or to execute, which moves karma.

With `jianghu` (`core/jianghu_engine.py`), they stop being statues and **want**
things: each pulse, a few in every continent pick a goal from their own soul and
what the world offers — **march** to a contested land, **hunt** in a besieged
one, take a **contract**, pursue a **vendetta** — and the chronicle announces it.
Houses whose cultivators gather in a continent occupy it. They can also
**ambush** a player — while exploring, in the plaza or on the road — and the
player chooses to pay, to flee or to fight. A cultivator who executes the
defeated becomes **marked**, and hunted for a while.

`core/heavens_whispers_engine.py` turns the life of the world into rumours — a
cultivator ascending, a beast tide, a ruin found — in a feed (`/sussurros`), and
now and then in a player's inbox, for those who keep that notification on.

## Reputation and the rival

With `reputacao_rival` (`core/reputation_engine.py`), every cultivator has a
**reputation in each continent**, from −100<!--#val:core/reputation_engine.py:REP_MIN*-1--> to
+100<!--#val:core/reputation_engine.py:REP_MAX-->, raised by what they do there — finishing a story
(+3<!--#env:REP_STORYLET_DONE-->), a bounty (+2<!--#env:REP_BOUNTY_CLAIM-->), holding back a tide
(+2<!--#env:REP_TIDE_CONTAINED-->), beating a local cultivator (+1<!--#env:REP_NPC_WIN-->, at most
3<!--#env:REP_NPC_WIN_DAILY_CAP--> a day) — and fading back towards zero, one point a week, where
they are absent. At +25<!--#env:REP_DISCOUNT_THRESHOLD--> the local market gives a discount; at
+50<!--#env:REP_REVERENCE_THRESHOLD--> the place reveres you; at −25<!--#env:REP_CONTEMPT_THRESHOLD*-1--> it charges more.

And the **rival**: an NPC cultivator you defeat may, with an
8%<!--#env:RIVAL_BIRTH_CHANCE--> chance, swear to come back — after
48<!--#env:RIVAL_RETURN_HOURS--> hours, a little stronger each time (+12%<!--#env:RIVAL_POWER_PER_DEFEAT-->
per defeat, up to +60%<!--#env:RIVAL_POWER_CAP-->), until you have beaten them
5<!--#env:RIVAL_MAX_DEFEATS--> times.

## Stories and bounties

With `quests_vivas` (`core/storylet_engine.py`), quests become **storylets**:
pieces of story with declarative requirements — a place, a continent's state,
an active event, karma, path, realm, meridians — that exist only when the world
makes them true (`storylet_available()`), offered by a stranger in the plaza, on
arrival from a journey or while exploring. Refusing costs nothing; an accepted
story counts the player's own deeds towards it (`track_storylets()`).

The **bounty board** (`core/bounty_engine.py`) posts contracts on NPC cultivators
whose karma has gone dark — 4<!--#env:BOUNTY_POOL_PER_CONTINENT--> per continent, each for
48<!--#env:BOUNTY_TTL_HOURS--> hours — fulfilled by the same duel the plaza already offers.
A house's raid can post one; and a player can put a price on a dark cultivator's
head with their own spirit stones (at least 500<!--#env:MIN_PLAYER_BOUNTY-->).

## The sky's temperament

With `tempo_do_ceu` (`core/tianshi_engine.py`), the sky of each world turns every
12<!--#env:TIANSHI_TICK_HOURS--> hours to one of three<!--#len:core/tianshi_engine.py:SKIES--> temperaments — serene,
wrathful, or veiled — the same for everyone in that world, computed from the
clock and the world's key, with no job and no table. It changes how severe a
tribulation is, and the tribulation screen shows the before and after
(`sky_view()`), and when the sky will turn next.

## Where it lives

| | |
|---|---|
| engines | `core/world_pulse_engine.py`, `core/continent_engine.py`, `core/travel_engine.py`, `core/tiandao_engine.py`, `core/region_state_engine.py`, `core/city_engine.py`, `core/caravan_engine.py`, `core/npc_cultivator_engine.py`, `core/jianghu_engine.py`, `core/heavens_whispers_engine.py`, `core/reputation_engine.py`, `core/storylet_engine.py`, `core/bounty_engine.py`, `core/tianshi_engine.py` |
| chat | `/praca`, `/viajar`, `/cronica`, `/sussurros`, `/eventos` |
| client API | `/api/miniapp/world/plaza`, `/api/miniapp/world/travel`, `/api/miniapp/world/chronicle`, `/api/miniapp/world/events`, `/api/miniapp/world/caravan`, `/api/miniapp/world/storylets`, `/api/miniapp/world/bounties`, `/api/miniapp/world/whispers`, `/api/miniapp/world/npc_list`, `/api/miniapp/events/active` |
| data | `WorldSect`, `WorldChronicle`, `WorldEvent`, `RegionState`, `NpcCultivator`, `HeavensWhisperLog`, `PlayerRegionRep`, `StoryletCatalog`, `PlayerStorylet`, `Bounty`, `CelestialEvent` |
| flags | `tiandao_director`, `estados_regionais`, `cidades`, `caravana`, `jianghu`, `reputacao_rival`, `quests_vivas`, `tempo_do_ceu` |
| tests | `scripts/_test_mv5_storylets.py`, `scripts/_test_mv6_reputation.py`, `scripts/_test_mv8_jianghu.py`, `scripts/_test_mv9_cidades.py`, `scripts/_test_mv95_caravana.py`, `scripts/_test_mv11_tianshi.py` |
