# Nivrael — documentation

How the game is built, written from the code — for anyone who wants to run it,
study it or change it.

## Start here

- [Installing and running](installation.md) — Docker, without Docker, with your
  own Telegram bot; signing in; the variables; running the tests.
- [Architecture](architecture.md) — the shape of the process, worlds, the
  feature flags, the owners, the cultivator soul, the web server, the client, the
  scheduler, the chat surface.
- [The database](database.md) — the game model, the control plane, what happens
  at boot, the rules of migrations, the seeds.
- [Translations](translations.md) — the six catalogues, how a string is looked
  up, how to fix or add one.

## The systems

| page | what it covers |
|---|---|
| [Cultivation](systems/cultivation.md) | realms, Qi and the tick, meditation, the cave, birth, breakthroughs, lifespan |
| [The body](systems/body.md) | the mortal flesh and its four feeders, the transformations, the meridians |
| [Combat](systems/combat.md) | the damage model, duels, opponents, the arena, intent, the world boss |
| [Techniques](systems/techniques.md) | sect libraries, scrolls, legacy caves, the forbidden path |
| [Crafting](systems/crafting.md) | alchemy, the forge, formations, professions |
| [Items and beasts](systems/items-and-beasts.md) | the spatial ring, items, spirit beasts and expeditions |
| [Dungeons and exploration](systems/dungeons-and-exploration.md) | dungeon runs, regional portals, exploring by divine sense |
| [Sects, guilds and paths](systems/sects-and-paths.md) | karma and paths, the nine houses, guilds, factions |
| [The living world](systems/living-world.md) | continents, the world pulse, the heavens, cities, caravans, NPC cultivators, reputation, stories, the sky |
| [The Dao](systems/dao.md) | the supreme laws and the three thousand laws |
| [Quests, rewards and rebirth](systems/progression.md) | quests, achievements, the battle pass, prestige, Dao partners |
| [Economy](systems/economy.md) | currencies, the market, trades, and the real-money side that is off here |

## How these pages stay true

Every page here is checked against the code on every pull request by
`scripts/_verifica_documentacao.py`:

- every link opens, and every anchor names a heading;
- every path, module, function and constant written in `code style` exists — and
  where a page says a function lives in a file, it lives in that file;
- every web path is a route of the real application, and every chat command
  (`/cultivar`, …) is one the bot registers;
- **every number is measured.** It is written next to the fact that measures it,
  as an invisible marker — `40<!--#flags-->` — and the guard computes the fact
  from the code. A bare number fails;
- every engine of `core/`, every handler and every module of `community/` is
  named by some page, and every feature flag is in the
  [architecture](architecture.md#feature-flags) table — a new system without a
  page fails.

What the guard cannot check is whether a sentence is *right*. That is the
reviewer's job — and when you find a page that is wrong, an issue or a pull
request is the best gift.
