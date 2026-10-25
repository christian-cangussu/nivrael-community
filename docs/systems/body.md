# The body

Qi is half of a cultivator. The other half is the **body**, tempered from the
mortal flesh up to a celestial physique — and in the worlds that turn it on, a
body that lags the realm holds the cultivator back in combat.

## The mortal flesh

With `cultivo_corpo_r0`, the body path starts in the first realm. The flesh is
tempered through seven<!--#len:core/body_tempering_engine.py:MORTAL_TIERS--> tiers — skin, flesh,
blood, tendons, bones, marrow, viscera — each costing spirit stones and a share
of the Qi capacity (`mortal_temper_cost()`, `perform_mortal_temper()` in
`core/body_tempering_engine.py`). The body may run at most
1<!--#env:BODY_REALM_LEAD--> tier ahead of the realm (`mortal_realm_cap()`).

**Temper progress** is the patient currency of the flesh: banked progress
discounts the Qi cost of the next tier by 35%<!--#val:core/body_tempering_engine.py:HORTA_QI_DISCOUNT-->.
Four feeders fill it, each paced differently:

| feeder | how | engine |
|---|---|---|
| the **garden** | plant herbs in 4<!--#env:GARDEN_PLOTS--> plots; they mature on their own, from 30<!--#val:core/garden_engine.py:GARDEN_HERBS['erva_serena']['grow_seconds']/60--> minutes to 12<!--#val:core/garden_engine.py:GARDEN_HERBS['flor_sangue']['grow_seconds']/3600--> hours, and the harvest is progress | `core/garden_engine.py` |
| the **hunt** | beast expeditions bring back hunt essence; refining 10<!--#env:HUNT_REFINE_COST--> essence gives 50<!--#env:HUNT_REFINE_YIELD--> progress | `core/hunt_engine.py` |
| the **temper sites** | four<!--#len:core/environment_engine.py:TEMPER_SITES--> extreme places, one in each continent but Mòyǔ — the ice cavern, the volcano peak…; once every 6<!--#env:ENV_COOLDOWN_SECONDS/3600--> hours, where you stand | `core/environment_engine.py` |
| **combat insight** | winning a worthy fight (the opponent at 70%<!--#env:INSIGHT_MIN_OPP_BP_RATIO--> of your power or more) gives 25<!--#env:INSIGHT_PROGRESS--> progress, once every 30<!--#env:INSIGHT_COOLDOWN_SECONDS/60--> minutes; surviving one at 30%<!--#env:INSIGHT_NEARDEATH_FRAC--> HP or less grants an **insight charge** for 24<!--#env:INSIGHT_CHARGE_HOURS--> hours, which lets the breakthrough ceremony force without risk | `core/insight_engine.py` |

Chat: `/corpo`, `/horta` (the garden and the hunt).

## The transformations

From Body Integration on (realm 7<!--#val:core/body_tempering_engine.py:MIN_REALM_REQUIRED--> in the
code's count), the body climbs the **nine transformations** — Iron Skin, Copper
Bones, Silver Meridians, … up to the Perfect Body — and three celestial ones
beyond them, 12<!--#val:core/body_tempering_engine.py:MAX_TEMPERING_LEVEL--> levels in all
(`TEMPERING_LEVELS`). Each raises HP and defence (×2.5<!--#val:core/body_tempering_engine.py:TEMPERING_LEVELS[12]['hp_def_mult']--> at the
top) and the Qi capacity; the celestial levels add their own bonuses
(`get_celestial_body_bonuses()`). Reaching Mahayana requires the third
transformation ([cultivation](cultivation.md#breakthroughs)).

`project_tempering_status()` is the one owner of what the transformation screen
shows; `can_temper()` and `perform_tempering()` decide and apply.

## The meridians

With `corpo_profundo`, the twelve<!--#len:core/meridian_engine.py:MERIDIAN_CHANNELS--> classical channels open
one by one, in their classical order (`core/meridian_engine.py`). The realm sets
how many the body can hold — from Foundation Establishment, 2<!--#env:MERIDIAN_CHANNELS_PER_REALM-->
more per realm — and opening each is a hard ritual in three steps:

1. **prepare** — spirit stones, temper progress and hunt essence, paid together
   (`start_ritual()`);
2. **circulate** — the Qi has to run the channel for hours
   (6<!--#env:MERIDIAN_CIRCULATE_HOURS_BASE--> for the first, more for each next);
3. **break through** (`attempt_break()`) — an honest chance, shown before:
   55%<!--#env:MERIDIAN_BREAK_CHANCE_BASE--> for the first channel, lower for each next (never
   under 30%<!--#env:MERIDIAN_BREAK_CHANCE_FLOOR-->), plus 10%<!--#env:MERIDIAN_BREAK_RETRY_BONUS--> after each failure
   (up to 90%<!--#env:MERIDIAN_BREAK_CHANCE_CAP-->). A failure loses nothing that was paid: the
   channel only has to circulate again, for 50%<!--#env:MERIDIAN_RETRY_FRACTION--> of the time.

After a channel opens, the next ritual waits 48<!--#env:MERIDIAN_RITUAL_COOLDOWN_HOURS--> hours.

Each open channel makes the body 2%<!--#env:MERIDIAN_DURABILITY_PER_CHANNEL--> more durable in combat
(`meridian_durability_bonus()`). **Where** you refine also matters
(`refine_place_mult()`): the cave with a living formation is the best place
(×1.25<!--#env:REFINE_MULT_CAVERN-->), the continent's temper site the baseline, and the road
the worst (×0.75<!--#env:REFINE_MULT_ANYWHERE-->) — and the screen says which one you are in.

## The body in combat

Every layer of the body folds into one multiplier of HP and defence,
`body_durability_mult()`, which the cultivator soul and the fight both read.

A world can also make a lagging body **cost** power: with the balance knob
`body_throttle_enabled`, a cultivator whose body stage (`body_stage_for_gap()`)
falls behind the realm strikes weaker, by `body_throttle()` in
`core/combat_model.py` — tuned by `body_throttle_base` and `body_throttle_cap`
([per-world balance](../architecture.md#per-world-balance)). It is off by default.

## Where it lives

| | |
|---|---|
| engines | `core/body_tempering_engine.py`, `core/garden_engine.py`, `core/hunt_engine.py`, `core/environment_engine.py`, `core/insight_engine.py`, `core/meridian_engine.py` |
| chat | `/corpo`, `/horta` |
| client API | `/api/miniapp/body_tempering/status`, `/api/miniapp/body_tempering/ascend`, `/api/miniapp/world/body_temper`, `/api/miniapp/world/garden`, `/api/miniapp/world/garden_plant`, `/api/miniapp/world/garden_harvest`, `/api/miniapp/world/hunt_refine`, `/api/miniapp/world/env_temper`, `/api/miniapp/world/meridians`, `/api/miniapp/world/meridian_start`, `/api/miniapp/world/meridian_break` |
| data | `Player` (the body levels, temper progress, hunt essence, meridians), `PlayerGardenPlot` |
| flags | `cultivo_corpo_r0`, `corpo_profundo` |
| tests | `scripts/_test_mv4_meridians.py`, `scripts/_sabota_o_corpo.py` |
