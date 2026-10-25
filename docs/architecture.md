# Architecture

One Python process serves the whole game: the web server, the scheduler and,
on the official servers, the Telegram bot. Every surface asks the same engines,
and every engine reads and writes the database of the **world** the request
belongs to.

```
   browser (/login → /app, /play)            Telegram (chat + Mini App)
            │                                          │
            ▼                                          ▼
   core/webserver.py  (aiohttp)  ◄─── same process ───  main.py  (python-telegram-bot)
   the client · the API · pages                         handlers/  (the chat surface)
            │                                          │
            └──────────────►  core/  (the engines)  ◄──┘
                                   │
                core/scheduler.py ─┤  jobs, run once per active world
                                   ▼
                database/db.py — the world router (a ContextVar picks the world)
                   │                     │                      │
             control plane           world "main"          world "local" …
           (accounts, sessions,      (its own database,    (its own database,
            the world registry)       every game table)     every game table)
```

- [The entry points](#the-entry-points)
- [Worlds](#worlds) · [Feature flags](#feature-flags) · [Per-world balance](#per-world-balance)
- [The owners](#the-owners) · [The cultivator soul](#the-cultivator-soul)
- [The web server](#the-web-server) · [The client](#the-client) · [The scheduler](#the-scheduler)
- [The chat surface](#the-chat-surface) · [Platform modules](#platform-modules) · [This edition](#this-edition)

## The entry points

| command | what runs |
|---|---|
| `python -m community.local` | the web game without Telegram: web server, scheduler, the local world, the local login ([installation](installation.md#without-docker)) |
| `python main.py` | the official game: the chat bot, the same web server on port 8080<!--#main_web_port-->, the scheduler |
| `python scripts/provision_world.py` | creates a world from the command line — the same `provision_world()` the admin panel calls |
| `python scripts/_dev_serve_miniapp.py` | the client alone, with staged data and no database — for looking at screens |

## Worlds

The game runs several **isolated worlds** in one process. A world is a row in
the control plane (the `servers` table) plus its own PostgreSQL database with
every game table. Two worlds never share a player row, a market or a sect.

- **Choosing the world.** `database/db.py` keeps a `ContextVar`
  (`set_current_world()`, `use_world()`); `get_session_factory()` returns the
  sessions of the world bound to the current request or job. Unbound code
  resolves to `main`. A request is bound by the web server from the player's
  active world (`resolve_active_world()` in `database/control_db.py`).
- **`main` is special.** It is always resolvable from `DATABASE_URL` alone, even
  with the control plane down, and it **always reads the default flags and the
  default balance** (`get_world_features()`, `get_world_balance()` ignore what is
  stored for it). On the official servers that is how the legacy world is kept
  exactly as its players know it.
- **Where players are born.** `signup_world_key()` reads `SIGNUP_WORLD`. In this
  edition `community.local` points it at the local world.
- **Making a world.** `provision_world()` in `core/world_provision.py` creates
  the database (best effort), runs the full migrations and seeds against it,
  registers it as `maintenance`, and flips it to `active` only when everything
  succeeded — a half-built world is never enterable.
- **A broken world never breaks `main`.** At boot every secondary world is
  initialised inside its own `try`; one that fails, or has no `players` table
  afterwards, is demoted to `maintenance` (`demote_world()`), its players fall
  back to `main`, and the scheduler stops ticking it.

## Feature flags

New systems are built **behind a per-world flag, off by default**. There are
40<!--#flags--> today, in `DEFAULT_WORLD_FEATURES` (`database/db.py`); the local world
of this edition turns all of them on. The rules:

- read a flag only through `feature_enabled_for_world()` — it fails safe to
  `False` on any error, so a bug can never expose a gated system. Most engines
  wrap it in a one-line gate of their own (`director_on()`, `estados_on()`, …);
- the admin panel changes a world's flags live (`set_world_features()`); the
  control plane keeps them in `servers.balance_config`, under `features`;
- unknown keys are ignored, and `main` never reads its stored flags.

| flag | what turns on | read by |
|---|---|---|
| `cultivo_corpo_r0` | the body path from the first realm (Mortal) — tempering the mortal flesh, the garden, the hunt, the temper sites, combat insight | `core/body_tempering_engine.py` and its feeders |
| `horta` | **nothing today** — declared, read by no code; the garden shipped under `cultivo_corpo_r0` | — |
| `formacoes` | **nothing today** — declared, read by no code; formations open by realm | — |
| `breakthrough_trials` | the breakthrough ceremony: consolidate or force the first breakthroughs | `core/breakthrough_trials_engine.py` |
| `ftue_espinha` | the guided first hour | `core/ftue_engine.py` |
| `racas` | the people a soul is born into, shown (disclosure only) | `core/race_engine.py` |
| `progressao_visivel` | one aggregated combat power, and before → after on every advance | `core/cultivator_soul.py` |
| `combate_unificado` | every source of power counts in combat — equipment, foundation, Dao, techniques, achievements | `core/cultivator_soul.py`, `core/combat_engine.py` |
| `manifest_canary` | a hidden tab that proves surface gating works | the client |
| `ui_v2` | the "living scroll" shell of the client | the client |
| `dungeons_regionais` | dungeons anchored to continents | `core/dungeon_regions.py` |
| `tiandao_director` | the heavens make events happen in places: beast tides, meteors | `core/tiandao_engine.py` |
| `estados_regionais` | each continent has a living state with real effects | `core/region_state_engine.py` |
| `corpo_profundo` | the twelve meridians and refining that depends on where you are | `core/meridian_engine.py` |
| `quests_vivas` | storylets — quests that exist only when the world makes them true | `core/storylet_engine.py` |
| `reputacao_rival` | regional reputation, and a rival who remembers you | `core/reputation_engine.py` |
| `profissoes` | one profession per cultivator, felt in the engines | `core/profession_engine.py` |
| `biblioteca_seitas` | sect libraries in shelves, opened by rank | `core/sect_library_engine.py` |
| `escassez_scrolls` | the scroll economy: random drops cut, scrolls donated or burned | `core/scroll_economy_engine.py` |
| `estantes_seladas` | the two sealed shelves of a sect library | `core/sect_library_engine.py` |
| `legacy_caves` | legacy caves that awaken from the world pulse | `core/legacy_cave_engine.py` |
| `forbidden_path` | the forbidden path: power paid in karma and in years | `core/forbidden_path_engine.py` |
| `jianghu` | NPC cultivators with goals — they march, hunt, take contracts, hold vendettas | `core/jianghu_engine.py` |
| `cidades` | one named city per continent, with requests and a voice | `core/city_engine.py` |
| `marca_do_tracado` | mastery per formation, counted in activations | `core/formation_engine.py` |
| `caravana` | where each material is born, and caravans that bring it by barter | `core/caravan_engine.py` |
| `tempo_do_ceu` | the sky's temperament, on a clock | `core/tianshi_engine.py` |
| `masmorra_unica` | one dungeon run at a time | `core/dungeon_run_engine.py` |
| `superficie_desktop` | the desktop layout (wide screens get their own surface) | the client |
| `pele_quente` | the warm, hand-made skin | the client |
| `cena_cultivo` | the cultivation scene | the client |
| `cultivador` | the cultivator figure instead of the orb | the client |
| `cartas` | cards for items and characters | the client |
| `iconografia` | the drawn marks that replace emoji | the client |
| `item_vivo` | items that show their tier | the client |
| `o_mapa` | the world map | the client |
| `golpe_padrao` | a chosen default technique for the round clock | `core/duel_engine.py` |
| `arena_encontro_rapido` | the arena's quick encounter when nobody else is queued | `core/arena_engine.py` |
| `cultivador_jogavel` | the playable cultivator — the arrival, the side panel, the locked doors | `core/portas.py`, the client |
| `a_obra` | one switch that turns the new shell on with everything built for it | `core/portas.py`, the client |

The client reads the flags from the `/api/miniapp/player` payload through one function
(`featureEnabled()` in `miniapp/components/app.js`).

## Per-world balance

A world can also run a different balance without touching `main`:
`DEFAULT_WORLD_BALANCE` (`database/db.py`) has 9<!--#balance_knobs--> knobs, of which
6<!--#live_balance_knobs--> are wired into the engines today (`LIVE_BALANCE_KEYS`) — the
cultivation speed, the profession speed, the Qi band of combat and the three knobs
of the body throttle. The rest are stored for the systems that will read them,
and the admin panel says which is which (`BALANCE_KNOB_DOCS`). Engines read them
with `get_world_balance()`.

## The owners

The rule of the house: **one function decides a capability, and every surface
asks it.** Two hand-wired copies always drift. The main owners:

| capability | the owner |
|---|---|
| power, stats and HP | `compute_cultivator_soul()` — [below](#the-cultivator-soul) |
| the damage, HP and mitigation math of every fight | `core/combat_model.py` (`compute_attack()`, `combat_hp()`) |
| a feature flag | `feature_enabled_for_world()` |
| whether a world charges real money · whether the gacha opens | `monetization_enabled_for()` · `gacha_enabled()` |
| granting Spirit Jade | `grant_jade()` in `core/monetization.py` |
| a string in the player's language | `t()` in `core/i18n.py`, and `t()` in the client |
| whether a tab opens for this player, and why not | `portas_do_jogador()` in `core/portas.py` |
| whether an introduction is still shown | `core/explicacoes.py` |
| the spatial ring's size and price | `core/anel.py` |
| the name of every item outside the catalogues | `core/itens.py` |
| the open dungeon run | `active_run()` in `core/dungeon_run_engine.py` |
| what a continent's state changes | `region_overrides()` in `core/region_state_engine.py` |
| a notification to a player | `notify()` in `core/notification_engine.py` |

The "lights up" owners — `core/oficios.py`, `core/bestas.py`, `core/seita.py`,
`core/guilda.py`, `core/masmorra.py` — each own what a screen shows as
*confirmed progress* for one system (a craft tier, a beast's level, a sect rank,
a guild building, a dungeon floor), computed from the engine's state before and
after an action, never guessed by the client.

## The cultivator soul

`core/cultivator_soul.py` is the single source of the player's effective power,
attributes and HP. Whatever raises power — equipment, the companion beast, Dao
laws, interior techniques, achievements, the foundation — is folded **once**,
there, and every surface reads the result: the profile, the arena, the duel,
the combat preview. The same cultivator never shows two numbers.

- `load_cultivator_modifiers()` fetches the modifier stack once;
  `build_soul_snapshot()` is the pure core (no I/O, so chat handlers that
  already loaded the modifiers share it); `compute_cultivator_soul()` is what
  surfaces call. `soul_max_hp()` and `soul_current_hp()` are the accessors for
  HP screens.
- Two flags shape it: with `combate_unificado` the HP and attributes are the
  effective ones (the same numbers combat uses); with `progressao_visivel` the
  displayed power is the aggregated one (`display_combat_power()`). The Qi
  capacity is always the effective cap (`get_effective_qi_capacity()`).

## The web server

`core/webserver.py` builds the application (`create_app()`): the pages, the
website, the client and the JSON API — 279<!--#api_routes--> routes under `/api/`.

- **Pages:** `/login` (the gate), `/app` (the client in a browser tab — the same
  file as `/miniapp` inside Telegram), `/play` (the world seen from outside, no
  account — `core/vitrine.py`, data from `/api/vitrine/world`), `/privacy` and
  `/terms` (`core/legal.py`), `/healthz`. The old Portuguese paths answer with a
  permanent redirect.
- **The API** lives under `/api/miniapp/`, grouped by system:
  `/api/miniapp/world/` (the living world, the sects, travel), `/api/miniapp/combat/`,
  `/api/miniapp/dungeons/`, `/api/miniapp/beasts/`, `/api/miniapp/alchemy/`,
  `/api/miniapp/forge/`, `/api/miniapp/market/`, `/api/miniapp/trade/`, and so on;
  `/api/miniapp/admin/` is the admin panel. Sign-in lives under `/api/auth/`.
- **Who is asking.** Inside Telegram every request carries the Mini App's signed
  `initData` (`core/telegram_auth.py`); in a browser it carries the web session
  (`core/web_session.py`: an `HttpOnly` cookie plus the `X-Nivrael-Session`
  header, both required). Either way the request is bound to the player's world
  before any engine runs.
- **Honeypots.** `core/anti_bot.py` registers decoy routes and a decoy block in
  the `/api/miniapp/player` payload for automation that scrapes the API — real clients never
  touch them.

## The client

The client is three plain script files, `miniapp/components/ui.js`, `tabs.js` and
`app.js` (React, written as JSX), loaded by `miniapp/index.html` in that order.
They share one global script scope — which is why their top-level shared state
uses `var`, and why `scripts/build_miniapp.mjs` **transforms and concatenates**
them into `miniapp/dist/bundle.js` instead of bundling modules. If the bundle is
missing, `index.html` falls back to compiling the files in the browser: slower,
never blank.

The client's text lives in `miniapp/i18n/` ([translations](translations.md)); its
art in `miniapp/newapp/assets/`. One client serves the phone and, with
`superficie_desktop`, a desktop layout.

The website at `/` is a separate Vite + React + Tailwind project in `website/`,
built into `website/dist/`.

## The scheduler

`init_scheduler()` in `core/scheduler.py` registers 24<!--#scheduler_jobs--> APScheduler
jobs. Most run **once per active world** (`iter_active_world_keys()`), each pass
bound to its world with `use_world()`; a failing world is reported and skipped,
never allowed to stop the others. Among them:

- the **cultivation tick**, every 30<!--#env:TICK_INTERVAL_SECONDS--> seconds — passive
  Qi and cultivation for everyone, offline progress capped by `OFFLINE_CAP_SECONDS`;
- the **world pulse**, every 6<!--#env:WORLD_PULSE_INTERVAL_HOURS--> hours — the NPC sects act,
  and the systems of the living world take their step after it
  ([living world](systems/living-world.md));
- daily and weekly quest resets, the battle pass reset, the world boss (spawn,
  check, expiry), sect wars, the arena queue sweep, the meditation sweep, the
  expedition check and the notifications pack.

## The chat surface

`main.py` registers 102<!--#chat_commands--> command names (many are the same command in
three languages) in 30<!--#handler_modules--> handler modules. The chat is the original
surface; the client is now the canonical one, and new systems ship there first.

| module | commands / what it does |
|---|---|
| `handlers/start.py` | `/start`, `/ajuda` — birth, the main menu, help |
| `handlers/cultivation.py` | `/status`, `/cultivar`, `/meditar`, `/corpo`, `/horta`, `/cerimonia`, `/guia`, `/ranking`, and the settings hub `/conf` with `/idioma` and `/notif` |
| `handlers/foundation.py` | `/recomeco`, `/quebrar_fundacao` — restarting and breaking the foundation |
| `handlers/tribulation.py` | `/tribulacao` — heavenly tribulations and their history |
| `handlers/celestial.py` | `/celestial`, `/camara_reflexao` — the Mahayana gates |
| `handlers/dao.py` | `/dao` — the Dao laws |
| `handlers/alchemy.py` | `/alquimia`, `/craftar`, `/ervas`, `/pilulas` |
| `handlers/artifacts.py` | `/artefactos`, `/forjar` |
| `handlers/inventory.py` | `/inventario` — the spatial ring |
| `handlers/beasts.py` | `/bestiario` — spirit beasts and expeditions |
| `handlers/combat.py` | `/combate`, `/desafiar`, `/arena`, `/tecnicas` |
| `handlers/dungeons.py` | `/dungeons` |
| `handlers/world_boss.py` | `/boss` |
| `handlers/sect.py` | `/seita`, `/seita_ancia`, `/praca`, `/viajar`, `/explorar`, `/caverna`, `/formacoes`, `/cronica`, `/sussurros`, guild management and wars |
| `handlers/library.py` | `/biblioteca` — the sect library |
| `handlers/scrolls.py` | `/pergaminhos` — what a scroll is worth |
| `handlers/forbidden.py` | `/coracao` — the heart-demon rite |
| `handlers/faction.py` | `/faccao` — the old factions, kept for their members |
| `handlers/profession.py` | `/oficio` — the profession guild |
| `handlers/quests.py` | `/missoes` |
| `handlers/achievements.py` | `/conquistas` |
| `handlers/events.py` | `/eventos` — celestial events |
| `handlers/prestige.py` | `/renascer`, `/prestige`, `/loja_prestige` |
| `handlers/market.py` | `/mercado`, `/vender`, `/trocar` |
| `handlers/shop.py` | the shop, and the Telegram Stars checkout (off in this edition) |
| `handlers/gacha.py` | the gacha (off in this edition) |
| `handlers/admin_monetization.py` | the admin's own commands — grant jade, VIP or a pass, start a celestial event, spawn a world boss, review suspicious trades (`setup_admin_monetization_handlers()`) |
| `handlers/partner.py` | Dao partners — buttons, no command |
| `handlers/moderation.py` | the link filter of the public group |
| `handlers/miniapp.py` | `/app` — opens the Mini App |

## Platform modules

The parts of `core/` that are not a game system:

| module | what it does |
|---|---|
| `core/webserver.py` | the web application and the whole API |
| `core/scheduler.py` | the jobs |
| `core/web_session.py` | browser sessions: cookie + header, renewal, revocation |
| `core/telegram_auth.py` | checks the Mini App's `initData` and the Telegram login widget |
| `core/firebase_auth.py` | verifies Firebase ID tokens against **your** project |
| `core/account_link.py` | the code that links a Telegram account and a web account into one player |
| `core/world_provision.py` | creates a world end to end |
| `core/i18n.py` | `t()`, catalogue names, language detection |
| `core/vitrine.py` | `/play` — the world from outside, cached, in three languages |
| `core/legal.py` | `/privacy` and `/terms`, the three languages side by side |
| `core/anti_bot.py` | the honeypots |
| `core/notification_engine.py` · `core/notification_prefs.py` · `core/notifications_engine.py` | the inbox and its bell · the per-player opt-outs · the job that sends the four timed reminders |
| `core/announcement_engine.py` | announcements to every player, in their language |
| `core/activity_indicators.py` | the dots on the main menu that say something is waiting |
| `core/portas.py` | which tab opens for this player, and what opens it |
| `core/explicacoes.py` | introductions that collapse once understood ("got it" / "show again") |
| `core/visual_engine.py` | the text banners of big moments in the chat |
| `core/log_buffer.py` | the recent logs the admin console reads, with secrets redacted |
| `core/utils.py` | shared helpers of the chat surface: safe sends, pagination, rate limits, adding to the ring |

## This edition

`community/` holds the 4<!--#community_modules--> modules that only the community edition has —
doors and scaffolding around the game, never a rule of it:

| module | what it does |
|---|---|
| `community/local.py` | `python -m community.local` — the web game without Telegram |
| `community/local_world.py` | the local world, with every flag on, made by the same `provision_world()` |
| `community/dev_login.py` | the local development login — a name, no password, only on this machine or network |
| `community/null_bot.py` | the bot that does not exist, so the scheduler's messages go nowhere |
