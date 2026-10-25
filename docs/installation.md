# Installing and running

There are three ways to run Nivrael, from the least to the most work:

1. [With Docker](#with-docker) — one command, nothing else to install.
2. [Without Docker](#without-docker) — your own Python and PostgreSQL.
3. [With your own Telegram bot](#with-your-own-telegram-bot) — the chat game and
   the Mini App, on a bot you created.

The first two run the **browser game** (`python -m community.local`); the third
runs everything the official servers run (`python main.py`). All three use the
same code, the same database layout and the same variables
([the variables](#the-variables)).

> **None of this is meant for a public server as it is.** The local development
> login signs in with a name and no password. To expose an instance, read
> [Going public](#going-public) first.

## With Docker

```bash
docker compose up
```

Then open **http://localhost:8080/login**, choose a sign-in name and then your
cultivator's name.

What happens, read from `docker-compose.yml` and the `Dockerfile`:

- The image is built from the game's own `Dockerfile`: a Node 20<!--#node--> stage
  builds the website (`website/`) and compiles the client
  (`node scripts/build_miniapp.mjs`), and a Python 3.11<!--#python--> stage installs
  `requirements.txt` and copies both builds in.
- Two services start: `db` (PostgreSQL 17<!--#postgres-->) and `game`, whose command
  is `python -u -m community.local` instead of the image's default `main.py`.
- The game listens on port 8080<!--#port--> **of this machine only** (the compose file
  binds it to the loopback address). Inside the stack the database is always the
  `db` service, whatever your `.env` says.
- Two volumes keep your data between restarts: `pgdata` (the database) and
  `state` (the generated session secret, in `NIVRAEL_STATE_DIR`).

The first boot is the slow one: it creates the control plane, runs every
migration on each world, seeds the catalogues, and creates the **local world**
— a second world with all 40<!--#flags--> feature flags on, where new players are
born ([architecture](architecture.md#worlds)).

`docker compose down` stops the stack and keeps the data;
`docker compose down -v` also deletes the volumes (a fresh world next time).

## Without Docker

You need Python 3.11+<!--#python--> and PostgreSQL 17<!--#postgres--> (the version the
compose file runs). Node 20+<!--#node--> is optional: it builds the client and the
website.

```bash
pip install -r requirements.txt
cp .env.example .env            # then point DATABASE_URL at your PostgreSQL
NIVRAEL_DEV_LOGIN=1 python -m community.local
```

The database role needs `CREATEDB`: every world is its own database on the same
server, and the local world is created on first boot next to the one in
`DATABASE_URL`. On a public server, give the game a role of its own that **owns**
its databases and has `CREATEDB` — never a superuser, which can read files and
run commands on the database host — and keep the database port off the internet.

What `community/local.py` does, in order:

1. Reads the `.env` of the project folder — only that one: a `.env` in a parent
   folder is never read, so a copy kept inside another project does not start
   with that project's database — then fills in the defaults of this edition
   **without overwriting anything you set**: `SIGNUP_WORLD` points at the local world;
   `NIVRAEL_COOKIE_INSECURE` is set when the development login is on (plain
   http); and, when there is neither `SESSION_SECRET` nor `BOT_TOKEN`, a strong
   session secret is generated once and kept in `NIVRAEL_STATE_DIR`.
2. Starts the real web application (`core.webserver.create_app`) on
   `NIVRAEL_HTTP_HOST` and `NIVRAEL_HTTP_PORT`, with the local login installed
   on top (`community/dev_login.py`).
3. Brings every world online (`database.db.init_db` — see
   [database](database.md#what-happens-at-boot)) and creates the local world if
   it does not exist yet (`community/local_world.py`).
4. Starts the scheduler (`core.scheduler.init_scheduler`) with a bot that does not
   exist (`community/null_bot.py`): cultivation ticks, world events happen, and
   the messages that would have been Telegram DMs go nowhere.
5. Marks itself ready, so `/healthz` answers like it does on the official servers:
   it answers `200` from the very start (the process is alive) and says
   `"ready": true` in its body only from this point on — wait for that, not for
   the `200`, before you sign in (`scripts/_fumo_da_edicao.py` does).

### Building the client

The game works without this step: the client then compiles itself in the browser,
slowly (a fallback by design — a missing build is never a blank screen). To serve
what players get:

```bash
cd website && npm ci && npm run build && cd ..
node scripts/build_miniapp.mjs miniapp
```

`scripts/build_miniapp.mjs` finds `esbuild` inside `website/node_modules`, which
is why the website's `npm ci` comes first.

## With your own Telegram bot

```bash
BOT_TOKEN=<from @BotFather> python main.py
```

`main.py` runs the chat bot (the commands in `handlers/`) and starts the same web
server on port 8080<!--#main_web_port-->, which serves the Mini App at `/app` and the
API under `/api/miniapp/`. With `WEBHOOK_URL` set the bot receives updates by
webhook (on `PORT`, at `WEBHOOK_PATH`, checked with `WEBHOOK_SECRET`); without
it, it polls. Set `MINIAPP_URL` to the public address of `/app` so the bot's
buttons open it, and `ADMIN_USERS` to the Telegram ids allowed into the admin
panel.

`main.py` does **not** create the local world and does not open the development
login: it is the official game's entry point, unchanged.

## Signing in

| how | turn it on | notes |
|---|---|---|
| local development login | `NIVRAEL_DEV_LOGIN=1` | `/login` shows the local gate (a name, no password; three languages). It refuses to open when `WEBHOOK_URL` is set and answers only to this machine or the local network. `/login?porta=oficial` still shows the normal gate. |
| Google, Apple, e-mail | `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_APP_ID` | **your own** Firebase project. Empty = those buttons stay off; the server verifies every ID token against your project (`core/firebase_auth.py`). |
| Telegram | `BOT_TOKEN` (and `LOGIN_BOT_USERNAME` for the login widget on the web) | inside Telegram the Mini App signs every request (`core/telegram_auth.py`). |

Every way of signing in ends in the same web session (`core/web_session.py`): an
`HttpOnly` cookie plus a header the client sends back, both required. The
accounts, identities and sessions live in the control plane
([database](database.md#the-control-plane)).

## The variables

`.env.example` is the reference, and it is complete: the community edition suite
(`scripts/_test_edicao_comunitaria.py`) fails if the code reads a variable that
is not documented there — read directly or through a helper function. Copy it to
`.env` in the project folder (the game reads no other) and uncomment what you
change.

Its first half is what an operator sets:

| section | the variables that matter |
|---|---|
| Database | `DATABASE_URL`, `CONTROL_DATABASE_URL` (empty = the same server), the pool sizes |
| Community edition | `NIVRAEL_MONETIZATION` (off by default), `NIVRAEL_DEV_LOGIN`, `NIVRAEL_HTTP_HOST`, `NIVRAEL_HTTP_PORT`, `NIVRAEL_LOCAL_WORLD`, `SIGNUP_WORLD`, `NIVRAEL_STATE_DIR` |
| Web sessions and sign-in | `SESSION_SECRET`, `NIVRAEL_COOKIE_INSECURE`, the four `FIREBASE_*` |
| Telegram | `BOT_TOKEN`, `WEBHOOK_URL`, `WEBHOOK_SECRET`, `MINIAPP_URL`, `ADMIN_USERS` |
| Public pages | `LEGAL_CONTACT_EMAIL`, `VITRINE_WORLD`, `VITRINE_WEB_URL` |
| Game loop | `TICK_INTERVAL_SECONDS`, `OFFLINE_CAP_SECONDS` |
| Fate seeds | `RACE_HASH_SALT`, `ROOT_ELEMENT_HASH_SALT`, `NPC_CULTIVATOR_HASH_SALT`, `LIFESPAN_NPC_AGE_SALT` — change them **before** anyone is born in a world; later, they rewrite destinies |
| Tools | `NV_IMAGE_API_KEY` (`scripts/gen_art.py`), `NV_CHROME` (the browser the tests drive) |

The second half lists every balance knob the engines read, with its default,
grouped by the file that reads it. Leave them commented unless you are tuning a
world; most worlds are tuned per world instead, from the admin panel
([architecture](architecture.md#per-world-balance)).

## Running the tests

```bash
python scripts/run_tests.py           # everything — the command before a pull request
python scripts/run_tests.py mv9 tec   # only the suites whose name contains a word
```

What the full run needs besides `pip install -r requirements.txt`:

- **Node**, a recent one: some suites run the real client code under Node, and the
  browser driver (`scripts/_olhar_cdp.mjs`) uses Node's built-in `WebSocket`.
- **`cd website && npm ci`** — `scripts/_test_cena_cabe.py` compiles the current
  client with `esbuild`, which lives in `website/node_modules`.
- **A Chrome or Chromium** — the same suite opens the duel in a headless browser
  and measures it at several widths. Set `NV_CHROME` to its executable, or let
  it find the one `agent-browser` installs.

`scripts/run_tests.py` checks these before it starts and says what is missing.
The continuous integration runs exactly this command on every pull request
([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).

To look at a screen without a database, `python scripts/_dev_serve_miniapp.py`
serves the client with staged data — open it at 390×844 and 1440×900.

## Going public

Before anyone else can reach your instance:

- turn the development login **off** (`NIVRAEL_DEV_LOGIN` unset) and use
  Telegram or your own Firebase project;
- set a long random `SESSION_SECRET`, and serve over https (then remove
  `NIVRAEL_COOKIE_INSECURE`);
- set `LEGAL_CONTACT_EMAIL`, and rewrite `/privacy` and `/terms`
  (`core/legal.py`) — they describe the official game;
- give your instance its own name: "Nivrael" is reserved for the official game
  ([TRADEMARKS.md](../TRADEMARKS.md));
- decide about payments: `NIVRAEL_MONETIZATION=1` turns Telegram Stars and the
  gacha back on, and Stars only pay the owner of the bot that issues them.
