# The database

Everything lives in PostgreSQL, through SQLAlchemy's async engine (`asyncpg`).
There are two kinds of database:

- **one control plane** — accounts, sign-in identities, sessions and the
  registry of worlds;
- **one database per world** — every game table, from `players` down. Two
  worlds never share a row.

On a single machine they are all databases of the same PostgreSQL server: the
control plane uses `CONTROL_DATABASE_URL` (empty = the server of
`DATABASE_URL`), `main` uses `DATABASE_URL`, and each new world gets a database
of its own, derived from it (`derive_world_db_url()` in `core/world_provision.py`).
How a request reaches the right one is in [architecture](architecture.md#worlds).

The registry keeps each world's address **without** a user or a password: whoever
connects to a world borrows the login of `DATABASE_URL`
(`with_env_credentials()` in `database/control_db.py`) — only on that same server,
so the password never goes to another host. It lives in one place — the
environment — so changing it never leaves a world behind. On boot,
`strip_registry_credentials()` rewrites the rows that only repeated the
environment's login (the connection stays exactly the same); a row with a login
of its own — a world on another server — is left as written.

## The game model

`database/models.py` declares the game schema: 101<!--#orm_models--> ORM models, one per
table, on one declarative `Base`. The player row (`Player`, table `players`) is
the centre; most other tables hang from `player_id`. By system:

| system | tables (models) |
|---|---|
| the cultivator | `Player`, `PlayerBuff`, `PlayerMedicineResistance`, `Tribulation`, `PrestigeLog`, `KarmaLog`, `LoginStreak` |
| techniques and intent | `TechniqueCatalog`, `PlayerTechnique`, `PlayerSectTechnique`, `PlayerIntent` |
| combat | `DuelSession`, `CombatLog`, `ArenaRanking`, `ArenaQueue`, `PVPChallenge`, `PlayerNPCCooldown` |
| alchemy and forging | `HerbCatalog`, `PillCatalog`, `CauldronCatalog`, `PlayerCauldron`, `PlayerAlchemySkill`, `PlayerPillMastery`, `PlayerSoulFire`, `PlayerRecipe`, `OreCatalog`, `PlayerOre`, `ArtifactCatalog`, `PlayerArtifact`, `ForgeRecipe`, `PlayerForgeSkill`, `PlayerForgeMastery` |
| the ring and the market | `PlayerInventory`, `PlayerSpatialRing`, `MarketplaceListing`, `P2PTrade`, `Transaction` |
| beasts | `BeastCatalog`, `PlayerBeast`, `ExpeditionCatalog` |
| dungeons and exploration | `DungeonCatalog`, `PlayerDungeon`, `DungeonQuestCatalog`, `PlayerDungeonQuest`, `PlayerExploration` |
| the Dao | `DaoLawCatalog`, `PlayerDaoFragment`, `DaoCategory`, `DaoPath`, `DaoPathLaw`, `PlayerDaoDiscovery` |
| sects, guilds, factions | `WorldSect`, `WorldSectRecruiterPending`, `WorldSectTrial`, `Sect`, `SectMember`, `SectBuildingLog`, `SectContributionLog`, `SectTerritory`, `SectWarLog`, `SectWarState`, `FactionCatalog`, `PlayerFaction`, `FactionQuestCatalog`, `PlayerFactionQuest`, `FactionShopItem` |
| the living world | `WorldChronicle`, `WorldEvent`, `RegionState`, `NpcCultivator`, `HeavensWhisperLog`, `Bounty`, `StoryletCatalog`, `PlayerStorylet`, `PlayerRegionRep`, `CelestialEvent`, `WorldBoss`, `WorldBossDamage` |
| the cave | `PlayerCavern`, `FormationCatalog`, `PlayerFormation`, `PlayerGardenPlot` |
| quests and rewards | `QuestCatalog`, `PlayerQuest`, `QuestChoiceLog`, `AchievementCatalog`, `PlayerAchievement`, `BattlePassMission`, `PlayerBPMission`, `PlayerPrestigePurchase` |
| purchases | `Purchase`, `PlayerVIP`, `BattlePass`, `GachaBanner`, `GachaHistory`, `GachaPity` |
| people and messages | `DaoPartner`, `DaoPartnerProposal`, `PlayerNotification`, `PlayerNotificationPref`, `GlobalAnnouncement` |

`*Catalog` tables are **content** — filled by the seeds below, the same in
every world. The `Player*` tables are **state**.

`scripts/_audit_orm_colunas.py` reads every `Model.column` the code uses and
fails on one the models do not declare — a missing column only explodes when
the line runs, so it is caught before.

## The control plane

`database/control_db.py` creates its own 8<!--#control_tables--> tables with plain SQL
(`bootstrap_control_db()`, idempotent, at every boot):

| table | holds |
|---|---|
| `servers` | the registry of worlds: key, database, status, public / sandbox flags, and `balance_config` (the per-world balance and feature flags) |
| `server_access_codes` · `player_server_access` | invitation codes for closed worlds, and who used them |
| `player_active_server` | the world each player is in now |
| `auth_identities` | each way of signing in (`telegram`, `firebase`, `dev`, …) pointing at a player |
| `auth_sessions` | the browser sessions |
| `account_link_codes` | the short codes that join a Telegram account and a web account |
| `admin_audit_log` | what the admin panel changed |

A browser account has no Telegram id: `allocate_synthetic_player_id()` gives it
a negative one, unique across worlds and never reused.

## What happens at boot

`init_db()` in `database/db.py`, every time the game starts:

1. `bootstrap_control_db()`, then `load_world_registry()` — the worlds.
2. For `main`, and then for each other world, `init_world_db()`:
   1. `create_all` — the ORM builds every table the models declare that does
      not exist yet, and **commits**. A fresh world has the whole current schema
      at this point.
   2. `run_migrations()` — in a separate transaction, every file of
      `migrations/` not yet recorded in `applied_migrations`, in name order.
      A failure is **fatal for `main`** and logged and skipped for a secondary
      world (its schema already came from `create_all`).
   3. The seeds — every catalogue, idempotent (below).
3. A secondary world that failed, or has no `players` table afterwards, is
   demoted to `maintenance` — `main` is never affected.
4. Every existing character is linked to its `telegram` identity (idempotent).

## Migrations

`migrations/` holds 140<!--#migrations--> SQL files today, numbered up to
142<!--#last_migration-->. `run_migrations()` applies them in name order and records each
**file name** in `applied_migrations` — the name, not the number, is the
identity (two old files share their number: `migrations/001_add_language.sql`
and `migrations/001_performance_indexes.sql`). Statements are split by a
tokenizer that understands comments, strings and `DO $$ … $$` blocks
(`_split_sql_statements()`), and a statement waiting on a lock is retried.

The rules — every world runs every migration at boot, and the official game has
players with years of history behind each row:

- **Only add.** `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT
  EXISTS`, `CREATE INDEX IF NOT EXISTS`. Never `DROP`, never a rename, never a
  type change that loses data.
- **Neutral defaults.** A new column is `DEFAULT NULL` or a value that means
  "nothing changed" — and the code treats `NULL` as that value. A row written
  before the column existed must behave exactly as before.
- **Idempotent.** Applying a file twice must change nothing (a world can be
  re-provisioned).
- **Numbered after the last one** (142<!--#last_migration--> today), with a name that says
  what it adds: `<next number>_<what>.sql`.
- **The model too.** Add the column to `database/models.py` as well: fresh
  worlds get it from `create_all`, existing ones from the migration.
- Start the file with a comment that says **why** — the existing files are the
  examples.

## Seeds

The catalogues (techniques, pills, herbs, ores, artifacts and recipes, beasts and
expeditions, dungeons and their quests, quests, achievements, the Dao laws and
paths, the NPC sects, formations, storylets, the world boss, events, factions,
the battle pass, the gacha banners) are code, in
21<!--#seed_modules--> modules under `database/seeds/`, and run on every boot after the
migrations — no migration is needed to add content. Every seed inserts the rows
that are missing. Whether it also **updates** a row that already exists, and
which fields, is decided seed by seed: read its `run_*` function before relying
on an edit reaching the worlds that already have the row (the dungeon seed, for
one, re-syncs the power, the floor counts, the drops and the continent of every
dungeon; others leave an existing row untouched). Content that players own (a
learned technique, a beast) points at the catalogue row by id: never reuse or
renumber an id.

## Adding a column, step by step

1. The model: the attribute in `database/models.py`, nullable or with a neutral
   default.
2. The migration: `migrations/<next number>_<what>.sql` with
   `ALTER TABLE <table> ADD COLUMN IF NOT EXISTS …`, and the comment that says why.
3. The code reads it defensively (a `NULL` is the old behaviour).
4. `python scripts/run_tests.py` — the ORM audit and the suites.
5. Boot it twice on a fresh database and on an existing one: both must start.
