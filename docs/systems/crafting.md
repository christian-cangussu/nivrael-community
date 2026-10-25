# Crafting

Alchemy refines herbs into pills, the forge turns ores into artifacts, and
formations turn the spoils of exploration into timed power. Each craft has its
own rank, its own per-recipe mastery, and — where a world turns professions on —
a cultivator who lives by one of them.

## Alchemy

`core/alchemy_engine.py`, from Qi Condensation on (`ALCHEMY_MIN_REALM`).

- **A craft** (`craft_pill()`) spends the recipe's herbs and alchemy energy, and
  rolls one of six<!--#len:core/alchemy_engine.py:CRAFT_RESULTS--> results: heavenly, divine, perfect,
  success, failure or explosion. Better results make stronger pills
  (`CRAFT_RESULTS`). The success chance (`calculate_success_chance()`) comes from
  the cauldron, the pill, the alchemy rank, the recipe's mastery, the soul fire
  and the profession — and the screen shows it before the craft. Batches exist
  (`/api/miniapp/alchemy/craft_bulk`).
- **Rank** — five<!--#val:core/alchemy_engine.py:MAX_ALCHEMY_TIER--> alchemy tiers, from Apprentice up
  (`ALCHEMY_TIERS`), raised by crafting.
- **Mastery** — every pill recipe has its own five<!--#val:core/alchemy_engine.py:MAX_MASTERY_LEVEL--> levels,
  which reduce failures.
- **The soul fire** — from Core Formation (`SOUL_FIRE_MIN_REALM`), a flame of
  six<!--#val:core/alchemy_engine.py:MAX_SOUL_FIRE_TIER--> tiers, fed by crafting and by beast cores
  (`feed_beast_core_to_soul_fire()`); it raises the success chance, and the
  alchemy rank raises the flame's ceiling and how fast the energy returns
  (`get_flame_mastery()`).
- **Cauldrons** carry a grade and durability: upgrade them with ores and stones
  (`upgrade_cauldron()`), repair them (`repair_cauldron()`). A pill tribulation can
  strike a craft: three<!--#val:core/alchemy_engine.py:PILL_TRIBULATION_ROUNDS--> rounds, each one a choice — protect,
  reinforce or sacrifice — of which 2<!--#val:core/alchemy_engine.py:PILL_TRIBULATION_PASS_THRESHOLD--> must succeed;
  failing costs cauldron durability and Qi (`apply_tribulation_failure()`).
- **Recipes** — every cultivator starts with the
  10<!--#len:core/alchemy_engine.py:T1_PILL_IDS--> first-tier recipes; the rest drop, or come from recipe
  scrolls.

**Medicine resistance.** Only the pills that raise the **Qi capacity** — the one
gain with no ceiling — build resistance (`_pill_has_resistance()`): full strength
for the first 3<!--#val:core/alchemy_engine.py:_RESISTANCE_TABLE[0][0]--> doses in a realm, then less, down to
25%<!--#val:core/alchemy_engine.py:_RESISTANCE_TABLE[3][1]--> of the effect (`get_pill_effectiveness()`); the next realm resets it
(`reset_medicine_resistance()`). Every other pill is exempt. Stat pills stop at a
ceiling instead, and the pill says so before it is used (`stat_boost_cap_state()`).

## The forge

`core/forge_engine.py` forges **artifacts** — weapons, armour, accessories — that
cultivators equip.

- **From a blueprint** (`forge_artifact()`) or **from a recipe** (`forge_recipe_item()`):
  ores and stones in, an artifact out, sometimes with a spirit of its own.
  Recipes come in six<!--#len:core/forge_engine.py:FORGE_RECIPE_TIER_INFO--> tiers; each recipe has
  five<!--#val:core/forge_engine.py:MAX_FORGE_MASTERY--> mastery levels that raise its success.
- **Rank** — five<!--#val:core/forge_engine.py:MAX_FORGE_TIER--> forge tiers, from Novice up (`FORGE_TIERS`),
  each improving quality and discounting ores.
- **After the forge** — refine an artifact (`refine_artifact()`), engrave runes
  (`enchant_artifact()`), or dismantle it for part of its materials back
  (`refund_recipe_materials()`). The celestial artifacts are forged only in
  Mahayana ([cultivation](cultivation.md#breakthroughs)).

Equipping, locking and the artifact's stats: `/api/miniapp/artifact/equip`,
`get_artifact_total_stats()`.

## Formations

`core/formation_engine.py`. A formation is a **craftable, timed consumable**:
herbs, ores and stones in (`craft_formation()`), a formation in the pouch. It
is then activated **on the body** — a timed buff (`activate_on_body()`), the same
buff rows pills use — or placed in the cave, where it works on the cave's own
gathering ([cultivation](cultivation.md#gathering-qi)). Some protect an
exploration (up to 75%<!--#env:EXPLORE_PROTECTION_CAP--> of the danger).

With `marca_do_tracado`, each formation keeps its own mastery, counted in
activations on the body: at 50<!--#val:core/formation_engine.py:MARCA_TIERS[0][1]--> it lasts longer
(+15%<!--#val:core/formation_engine.py:MARCA_DURATION_BONUS-->), at 200<!--#val:core/formation_engine.py:MARCA_TIERS[1][1]--> it costs less
(−20%<!--#val:core/formation_engine.py:MARCA_STONE_DISCOUNT--> stones, one material fewer), and at
1,000<!--#val:core/formation_engine.py:MARCA_TIERS[2][1]--> it gives a title.

Chat: `/formacoes`.

## Professions

With `profissoes`, each cultivator may live by **one** profession
(`core/profession_engine.py`) — three<!--#len:core/profession_engine.py:PROFESSIONS--> today, each fed by
an act the game already has, and each felt in an engine:

| profession | grows by | what it changes |
|---|---|---|
| alchemist | crafting pills | a higher success chance, up to +10%<!--#env:PROF_ALCH_SUCCESS_CAP/100--> (inside the same chance the screen shows), and a chance of an extra low-tier pill |
| blacksmith | forging | cheaper forging, and a chance of a free refine |
| physician | taking pills | stronger healing pills — also on an ally (`/api/miniapp/world/profession_heal`) — and faster meridian circulation |

A profession has 4<!--#val:core/profession_engine.py:PROF_TIER_COUNT--> tiers, reached at
100<!--#env:PROF_TIER_T2-->, 400<!--#env:PROF_TIER_T3--> and 1,200<!--#env:PROF_TIER_T4--> experience. Practising it
in its native continent counts ×1.5<!--#env:PROF_NATIVE_XP_MULT-->. Changing profession costs
10,000<!--#env:PROF_SWITCH_COST--> spirit stones. A world tunes the pace with its
`profession_speed` knob. Six<!--#len:core/profession_engine.py:FUTURE_PROFESSIONS--> more are named and not built
(`FUTURE_PROFESSIONS`). Chat: `/oficio`.

## What the screen confirms

`core/oficios.py` owns what a craft **confirmed**: the craft rank, the recipe's
mastery and the soul fire, read before and after the engine ran
(`ganho_alquimia()`, `ganho_forja()`), so the client lights up only what really
changed — never a number the client guessed.

## Where it lives

| | |
|---|---|
| engines | `core/alchemy_engine.py`, `core/forge_engine.py`, `core/formation_engine.py`, `core/profession_engine.py`, `core/oficios.py` |
| chat | `/alquimia`, `/craftar`, `/ervas`, `/pilulas`, `/artefactos`, `/forjar`, `/formacoes`, `/oficio` |
| client API | `/api/miniapp/alchemy/`, `/api/miniapp/alchemy_recipes`, `/api/miniapp/pill/`, `/api/miniapp/forge/`, `/api/miniapp/forge_recipes`, `/api/miniapp/artifact/`, `/api/miniapp/world/formations`, `/api/miniapp/world/profession` |
| catalogues | `HerbCatalog`, `PillCatalog`, `CauldronCatalog`, `OreCatalog`, `ArtifactCatalog`, `ForgeRecipe`, `FormationCatalog` — seeded by `database/seeds/alchemy_seeds.py`, `database/seeds/artifacts_seeds.py`, `database/seeds/forge_seeds.py`, `database/seeds/formation_seeds.py` |
| data | `PlayerAlchemySkill`, `PlayerPillMastery`, `PlayerSoulFire`, `PlayerCauldron`, `PlayerRecipe`, `PlayerMedicineResistance`, `PlayerForgeSkill`, `PlayerForgeMastery`, `PlayerArtifact`, `PlayerOre`, `PlayerFormation` |
| flags | `profissoes`, `marca_do_tracado` |
| tests | `scripts/_test_mv7_professions.py`, `scripts/_test_marca_tracado.py`, `scripts/_sabota_os_oficios.py`, `scripts/_sabota_a_forja.py` |
