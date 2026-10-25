# Sects, guilds and paths

Who a cultivator belongs to, and what road they walk. Three different things
share the word "sect" in the code, and keeping them apart is the first thing to
know:

| | what it is | where |
|---|---|---|
| **the nine houses** | the NPC cultivation sects of the world — they choose you | `core/world_sects_engine.py`, table `world_sects` |
| **guilds** | groups players create and run (the `sects` table, called "guild" on screen) | `core/sect_engine.py` |
| **factions** | the old Celestial-or-Demonic choice, kept for the players who joined one | `core/faction_engine.py` |

## Karma and paths

Every cultivator carries **karma**, from −1,000<!--#val:core/karma_engine.py:KARMA_MIN*-1--> to
+1,000<!--#val:core/karma_engine.py:KARMA_MAX--> (`core/karma_engine.py`). Acts move it by fixed amounts
(`KARMA_EVENTS`, applied through `apply_karma()`): passing a tribulation, rescuing
someone, an honest market sale raise it; using a forbidden art, killing the
righteous, betraying a sect oath lower it. The screen shows its band — saint,
pure, neutral, tainted, demonic — and how the world reads it
(`project_world_reactions()`).

There is no path to pick. At Core Formation the karma **crystallises** into one
of three<!--#len:core/path_engine.py:PATH_KEYS--> paths (`crystallize_path_for_player()`,
`core/path_engine.py`): **righteous** at +250<!--#val:core/karma_engine.py:KARMA_PATH_THRESHOLDS['righteous']-->
or more, **demonic** at −250<!--#val:core/karma_engine.py:KARMA_PATH_THRESHOLDS['demonic']*-1--> or less, **rogue** in between. The
old endpoint that let a player choose answers `410 Gone`.

- A path that drifts too far from its karma — righteous down to
  −500<!--#val:core/karma_engine.py:KARMA_DIVERGENCE_THRESHOLDS['righteous']*-1-->, demonic up to
  +500<!--#val:core/karma_engine.py:KARMA_DIVERGENCE_THRESHOLDS['demonic']--> — awakens a **heart demon** after
  72<!--#val:core/karma_engine.py:KARMA_DIVERGENCE_GRACE_HOURS--> hours of grace; the rite that answers it is in
  [techniques](techniques.md#the-forbidden-path).
- Karma also hardens the heavens: the further from zero, the harsher the
  tribulations (`get_tribulation_modifier()`).
- **Moral choices** come from the world, not from a menu: quests with a choice —
  mercy, power or greed — move karma, reputation and rewards
  (`apply_quest_choice()` in `core/quest_choice_engine.py`); so do the forks met
  while exploring, and sparing or executing a defeated NPC cultivator
  (`apply_combat_moral_choice()`).

The continent of Mòyǔ admits only the demonic path (`is_demonic_only()`).

## The nine houses

Nine<!--#len:core/world_sects_engine.py:WORLD_SECT_KEYS--> NPC sects — eight righteous houses and the demonic Abyssal
Depths — each with a home continent, a rival and a **soul**: five scalars
(ambition, honor, greed, zeal, aggression) that drive what the house does on the
[world pulse](living-world.md#the-world-pulse).

**Being chosen.** A house is never joined from a list. For every house the game
computes an **affinity** score, up to 100<!--#val:core/affinity_engine.py:AFFINITY_MAX--> (`core/affinity_engine.py`):
the path (a righteous house will not court a demonic soul, nor the other way —
`path_block_reason()` says why), the continent, the karma, the guild's lineage
and the moral choices made. When it reaches
75<!--#val:core/affinity_engine.py:AFFINITY_THRESHOLD-->, the hourly recruiter sends an elder to invite the
cultivator. Accepting starts a **trial** (`core/sect_trial_engine.py`): a duel
against an elder of the cultivator's own realm. Victory joins the house
(`join_player_to_sect()`); a defeat may be retried after
24<!--#val:core/sect_trial_engine.py:TRIAL_LOSS_COOLDOWN_HOURS--> hours.

**Rising.** A member climbs five<!--#len:core/world_sects_engine.py:SECT_RANKS--> ranks — disciple, inner, core,
elder, heir — each needing **contribution** and a realm
(`SECT_RANK_THRESHOLDS`, `SECT_RANK_REALM_GATES`, `eligible_rank()`); the house's
bonuses grow with the rank (`compute_rank_perks()`). Contribution comes from the
house's quests, from tribute in spirit stones
(25<!--#val:core/world_sects_engine.py:TRIBUTE_STONES_PER_POINT--> stones a point, `tribute_stones()`) and from donated
scrolls. What was earned sets the rank; what is left can be spent in the house's
**merit pavilion**, on titles (`buy_merit_reward()`). Each house teaches its arts
in its library ([techniques](techniques.md#the-sect-library)), and gives the new
disciple a named master.

`core/seita.py` owns what the hall confirms after an action — the rank recorded
and the contribution towards the next — read before and after the engine.

## Guilds

Players found guilds (`create_sect_for_player()`), and each inherits the lineage
of one of the nine houses (`core/sect_lineage_engine.py`): its philosophy, its
home continent and its ancestral rival.

- **Buildings** — six<!--#len:core/sect_engine.py:BUILDINGS--> of them (training ground, herb garden,
  forge, library, defence, spirit vein), raised with the guild's treasury
  (`upgrade_building()`); each level's effect is one number, the same on every
  screen (`building_effect_value()`).
- **Running it** — the master promotes and expels (`promote_member()`,
  `kick_member()`), issues a decree that lasts
  24<!--#val:core/sect_engine.py:DECREE_DURATION_HOURS--> hours, and may pass the torch to an elder, once every
  30<!--#val:core/sect_engine.py:TORCH_COOLDOWN_DAYS--> days. Members donate, and buy in the guild shop.
- **Wars** — every Friday, from hour 20<!--#guild_war_hour--> UTC, guilds fight for the territories
  for one<!--#val:core/sect_engine.py:WAR_WINDOW_SECONDS/3600--> hour; holding a territory pays a daily bonus. Fighting
  the guild of your ancestral rival hits ×1.5<!--#val:core/sect_lineage_engine.py:RIVAL_BP_MULTIPLIER--> harder.

`core/guilda.py` owns what the guild screen confirms after an upgrade: the
building's recorded level and the treasury before and after.

## Factions

The first version of the game split cultivators into two factions from Core
Formation on (`FACTION_MIN_REALM`), with reputation ranks, quests and a shop.
The paths replaced them; `core/faction_engine.py` keeps everything a faction
member earned working. New code reads the path, never the faction.

## Where it lives

| | |
|---|---|
| engines | `core/karma_engine.py`, `core/path_engine.py`, `core/quest_choice_engine.py`, `core/world_sects_engine.py`, `core/affinity_engine.py`, `core/sect_trial_engine.py`, `core/seita.py`, `core/sect_engine.py`, `core/sect_lineage_engine.py`, `core/guilda.py`, `core/faction_engine.py` |
| chat | `/seita`, `/seita_ancia`, `/criarseita`, `/entrarseita`, `/doarseita`, `/sairseita`, `/loja_seita`, `/ranking_sects`, `/decreto`, `/passar_tocha`, `/faccao` |
| client API | `/api/miniapp/world/sect_hall`, `/api/miniapp/world/sect_directory`, `/api/miniapp/world/sect_trial_start`, `/api/miniapp/world/sect_tribute`, `/api/miniapp/world/merit_list`, `/api/miniapp/world/karma_info`, `/api/miniapp/path/status`, `/api/miniapp/sect/`, `/api/miniapp/faction/` |
| data | `KarmaLog`, `QuestChoiceLog`, `WorldSect`, `WorldSectRecruiterPending`, `WorldSectTrial`, `Sect`, `SectMember`, `SectBuildingLog`, `SectContributionLog`, `SectTerritory`, `SectWarLog`, `SectWarState`, the faction tables |
| tests | `scripts/_test_seita_disclosure.py`, `scripts/_sabota_a_seita.py`, `scripts/_sabota_a_guilda.py` |
