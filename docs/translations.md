# Translations

The game speaks three<!--#languages--> languages — Brazilian Portuguese (`pt`), English
(`en`) and Spanish (`es`) — and every string exists in all of them. It lives in
six<!--#catalogs--> catalogues, three per surface:

| surface | files | keys today |
|---|---|---|
| the chat, and everything the **server** writes (notifications, the chronicle, lines the server resolves for the client) | `locales/pt.json`, `locales/en.json`, `locales/es.json` | 4,788<!--#chat_keys--> each |
| the **client** (`/app` and the Mini App) | `miniapp/i18n/pt.json`, `miniapp/i18n/en.json`, `miniapp/i18n/es.json` | 4,211<!--#client_keys--> each |

The three files of a surface always have **the same keys** — the suites fail
otherwise (for example the parity checks of `scripts/_test_qol_feedback.py`
and `scripts/_test_web_a_vitrine.py`).

## How a string is looked up

- **On the server:** `t(lang, key, **params)` in `core/i18n.py`. The language
  comes from the player's row; anything unknown becomes `pt`. A key missing in
  that language falls back to `pt`; a key missing everywhere is logged and shown
  as a readable version of the key — never as `[key]`. Placeholders are Python
  `format` fields: `"{name} reached {realm}"`.
- **On the client:** `t(key, params)` in `miniapp/components/ui.js`, over the
  files the client fetches when it starts. A missing key falls back to `pt`,
  then to the key itself. Placeholders look the same (`{name}`), but each one is
  replaced **once** — do not repeat a placeholder inside one client string.
- **Catalogue names** (techniques, pills, beasts, herbs, ores, quests, …) are
  keys built from the row: `<kind>_<id>_name` and `<kind>_<id>_desc`, read by
  `catalog_name()` and `catalog_desc()` in `core/i18n.py`. A row without a
  translation shows its catalogue name, so a missing translation never breaks a
  screen — it shows English.

**Which catalogue?** If the server composes the sentence and sends it ready, it
lives only in `locales/`, and the client prints it as it came. If the client
composes it, it lives only in `miniapp/i18n/`. One sentence never lives in both:
two copies of the same phrase drift.

The legal pages are the one exception: `/privacy` and `/terms` are long
documents edited as a whole, so their three languages live side by side in
`core/legal.py`.

## Rules of the text

- **Portuguese is Brazilian Portuguese** — *você*, Brazilian spelling.
- **Placeholders and commands never change:** `{name}` stays `{name}` in every
  language, and `/cultivar` is typed the same everywhere.
- **No Markdown in strings the server sends to both surfaces**: the chat would
  render it, the client would show the asterisks.
- **Keep the voice.** It is a cultivation world — "Qi", "realm", "sect",
  "breakthrough" — not a dashboard. Read the neighbouring keys before writing a
  new one.
- **Never hard-code text in the client.** Every visible word goes through `t()`.

## Fixing a translation

The best first contribution. Find the key (search the value you see on screen in
`locales/` or `miniapp/i18n/`), change it in the language that is wrong, and
open a pull request with a screenshot or the sentence before and after. Nothing
else to run besides `python scripts/run_tests.py`.

## Adding a string

A new key goes into the **three** files of its surface at once. The house way is
an **injector**: a small script, `scripts/inject_<what>_i18n.py`, that holds the
new keys of one change for the three languages and writes them into the
catalogues, idempotently (run it twice, nothing changes; it always writes with
`\n` line endings). The suite of that change imports the injector and checks
that every key it declares is present in all three files — so a key cannot be
added to one language and forgotten in the others. The existing injectors are
the examples (`scripts/inject_mv11_i18n.py` explains the rules above at the
top).

## A new language

A fourth language would be a large and welcome change — open an issue first.
It needs both catalogues complete, the language added to the supported set on
both sides (`core/i18n.py` and the client), the legal pages, and the suites that
compare the three languages taught about the fourth.
