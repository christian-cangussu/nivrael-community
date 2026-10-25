# Changelog

All notable changes to the community edition are written here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `MAINTAINERS.md` and `.github/CODEOWNERS` — who reviews and merges, who
  decides what reaches the official game (its owner alone), how one becomes a
  maintainer, and that no maintainer ever gets access to the official servers,
  their credentials or their players' data.
- **Project status** in the README (and in its Portuguese and Spanish
  summaries): the official game is live; if it ever has to close, its players
  are told at least 30 days ahead, and this repository stays.
- The publication guard reads a second private list (`--lore-privado`): the part
  of the story the official game keeps for later. Like the nicknames, the list
  lives only in the official game's private repository.
- `scripts/_test_senha_dos_mundos.py` and `scripts/_sabota_a_senha_dos_mundos.py`:
  the database password of every world has one owner — the environment.

- **`docs/`** — installing and running, the architecture, the database, the
  translations, and one page per system (cultivation, the body, combat,
  techniques, crafting, items and beasts, dungeons and exploration, sects and
  paths, the living world, the Dao, quests and rebirth, the economy), written
  from the code.
- `scripts/_verifica_documentacao.py` — the documentation guard: every link,
  path, function (in the file the page names), route, chat command and model
  column is checked against the code; every number in the prose carries the fact
  that measures it; every engine, handler and flag has a page. It tests itself
  before it reads the pages.
- **Continuous integration** (`.github/workflows/ci.yml`) on every pull request
  and push to `main`: the full `scripts/run_tests.py` on Python 3.11, the
  website and client build, the sabotage battery, the DCO sign-off of every
  commit, and `docker compose up` walked by a smoke test that keeps screenshots
  at 390×844 and 1440×900. Read-only token, no secrets, actions pinned to
  commits; `.github/dependabot.yml` keeps them current.
- Issue forms (bug, idea, translation) and a pull request template with the
  checklist of `CONTRIBUTING.md`.
- `scripts/_verifica_dco.py` (the sign-off check) and `scripts/_fumo_da_edicao.py`
  (the smoke test of a running instance).
- `scripts/run_tests.py` says, before it starts, what the full run is missing
  (Node, `esbuild`, a Chrome) and how to get it.

### Changed

- The registry of worlds (`servers.db_url`) keeps each world's address without
  a user or a password; connecting to a world borrows the login of
  `DATABASE_URL` — only on that same server: the environment's password never
  goes to another host. On boot, the rows that only repeated the environment's
  login are rewritten without it — the connection stays byte for byte the same —
  and a row with a login of its own is left alone. A provisioned world is stored
  the same way.
- A few code comments and one design preview no longer carry notes on the part
  of the story the official game has not told yet; the publication guard keeps
  it that way. Nothing a player sees changes.
- The Stars refusal and the lobby note are no longer rewritten for this edition:
  both phrases live in the code (`shop_purchases_official_only`,
  `lobby_separate_world_note`, in the three languages) and the call chooses.
  When a world sells (the official game's main server), the refusal points to
  it; when none does — this edition, out of the box — it says that real
  purchases exist only in the official game.

### Fixed

- The game read the first `.env` it found walking up the folders:
  `config.py` and `community/local.py` called python-dotenv's `load_dotenv`
  without a path, so a copy kept inside another project started with that
  project's database and bot token. Both now read only the `.env` of the project
  folder; the publication guard refuses `load_dotenv` or `dotenv_values` without
  a path and any call to `find_dotenv`, and the edition suite proves it with a
  canary `.env` in a parent folder.
- `scripts/_verifica_dco.py`, run in a copy with no git repository of its own,
  checked the commits of the repository around it; it now says so and stops.
- `.env.example` was missing 28 balance knobs that three engines read through a
  helper function (the forbidden path, the scroll economy, the sect library);
  the edition suite now follows such helpers, so it cannot miss one again.
- The sabotage battery's `.env` case also bites inside a git repository (it
  forces the file into the index, the real risk there).

### Removed

- The GitHub funding file (FUNDING.yml, under .github): every line in it was
  commented out. The project has no support channel for now; adding one is a
  single line in a new FUNDING.yml.

## [0.1.0] — the first community edition

The game of the official servers, opened, with what is private taken out.

### Included

- The whole game: cultivation and meditation across eleven realms, the body
  path and meridians, techniques with mastery and scarcity, alchemy, forging,
  refining and enchanting, the spatial ring, spirit beasts and expeditions,
  sects and player guilds, dungeons with difficulties and floor bosses, the
  world boss, duels and the ranked arena, the living world (houses with
  memory, regional states, cities, caravans, the sky's own temperament), quests
  and achievements, prestige and rebirth.
- The browser client (phone and desktop layouts) and the Telegram Mini App, in
  Brazilian Portuguese, English and Spanish.
- 140 additive SQL migrations, applied to every world at boot, and the content
  seeds.
- 29 standalone game suites, the audits and the sabotage batteries.

### Added for this edition

- `python -m community.local` — the web game without Telegram: one command,
  migrations and seeds on boot, a **local world** with all 40 feature flags on.
- The **local development login** (`NIVRAEL_DEV_LOGIN=1`) — a name, no
  password; refuses to open on a production configuration or for requests from
  outside the local network.
- `docker-compose.yml` (PostgreSQL 17 + the game) and a complete `.env.example`
  documenting every variable the code reads.
- `scripts/_test_edicao_comunitaria.py` — proves each difference below by
  calling the code that decides it.
- `scripts/_verifica_copia_publica.py` — the publication guard: no secrets, no
  player data, no IP addresses, no private folders, canonical licence texts.
- `scripts/run_tests.py`, the community files, the licences.

### Different from the official game

- Real-money purchases (Telegram Stars) and the gacha are **off by default**
  (`NIVRAEL_MONETIZATION=0`); the shop says so in all three languages.
- No Firebase project and no legal contact are built in; each instance brings
  its own.
- Names of players quoted in code comments, tests and old release notes are
  replaced by `[jogador]`; three test files that carried a player's initials
  were renamed.
