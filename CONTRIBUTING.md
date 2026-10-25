# Contributing to Nivrael

Thank you for wanting to walk this path with us. Issues, translations, tests,
fixes and new systems are all welcome. This page is the house rules — they are
short because each one exists for a mistake that was already paid for once.

## Before you start

- **Small and focused.** One pull request, one change, with the test that
  proves it. A big redesign starts as an issue so we can talk first.
- **Look for `good first issue`.** Translations, wording, tests and small
  disclosures are the best way in.
- **Security problems are never public.** See [SECURITY.md](SECURITY.md).

## The house rules

1. **Nothing reaches the player half done.** A new item, screen, tab or
   function is finished when it works *in every place it appears*. Count those
   places before you start; if you leave one out, write down which and why in
   the pull request.
2. **One owner in the code.** A capability has one function that decides it;
   every surface asks that function. Two hand-wired copies always drift.
3. **Serve it and look.** `python scripts/_dev_serve_miniapp.py` (or the real
   game with `python -m community.local`) at **390×844 and 1440×900** before
   saying a screen is done. A green test can be right about the wrong thing.
4. **A guard that bites.** A new rule gets a check in a suite — and you prove
   the check turns red when the rule is broken (that is what the
   `scripts/_sabota_*.py` batteries do). A check that is green on an empty set
   guards nothing.
5. **The player is never stuck without a path.** A locked option says why and
   what opens it; an error says what to do next. Never a silent void.
6. **Three languages, always.** Every string in `pt` (Brazilian Portuguese),
   `en` and `es`, in `locales/` (chat) and `miniapp/i18n/` (client). No
   hard-coded text in the client.
7. **Migrations only add.** `ADD COLUMN IF NOT EXISTS`, neutral defaults, never
   `DROP`. Every world runs every migration at boot; the official game has
   players with history behind each row.
8. **New features start behind a per-world flag, OFF by default.** See
   `DEFAULT_WORLD_FEATURES` in `database/db.py`.
9. **Production runs Python 3.11<!--#python-->.** `scripts/_audit_py311.py` catches the
   f-string syntax that only newer Pythons accept.
10. **Does it sound like Wuxia?** Before building, ask whether it reads like
    *Reverend Insanity* or like *World of Warcraft* — and whether the screen
    reads as a cultivation game or as a dashboard.

## Setting up

Follow [docs/installation.md](docs/installation.md) — with Docker it is
`docker compose up`, then http://localhost:8080/login. The rest of
[`docs/`](docs/README.md) explains the architecture, the database, the
translations and each system, from the code.

## Before you open a pull request

```bash
python scripts/run_tests.py
```

It runs the 30<!--#game_suites--> game suites, the community edition suite
(`scripts/_test_edicao_comunitaria.py`), the audits, the documentation guard
(`scripts/_verifica_documentacao.py`) and the publication guard
(`scripts/_verifica_copia_publica.py`). All of them must be green — the
continuous integration runs the same command on your pull request, and checks
that every commit is signed off. If you touched the client, rebuild it
(`node scripts/build_miniapp.mjs miniapp`) and look at the screen.

**Documentation is code.** If your change alters what a page in `docs/` says,
change the page in the same pull request. The documentation guard checks every
link, path, function, route and number against the code: a number is written
with the fact that measures it — `40<!--#flags-->` in the source renders as just the number,
and turns the check red the day the code has another count — so a page can go
stale only loudly. The guard's docstring explains how to add a fact.

Checklist:

- [ ] the change works in every place it appears (and the PR lists them)
- [ ] a test proves it — and you saw that test fail without the change
- [ ] pt / en / es in parity
- [ ] the pages in `docs/` that describe it are updated
- [ ] migrations (if any) are additive and numbered after the last one
- [ ] looked at it at 390×844 and 1440×900 (screens only)
- [ ] every commit is signed off

## Sign your commits (DCO)

We use the [Developer Certificate of Origin](https://developercertificate.org/)
instead of a contributor licence agreement. Add a sign-off line to every
commit — `git commit -s` does it for you:

```
Signed-off-by: Your Name <you@example.com>
```

By signing off you certify the DCO 1.1, reproduced here:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## Licence of your contribution

Inbound equals outbound: code you contribute is licensed under the
[AGPL-3.0-only](LICENSE); art and game text under
[CC BY-NC-SA 4.0](LICENSE-ASSETS) (see [NOTICE.md](NOTICE.md) for which is
which). Do not submit material you do not have the right to license that way —
including text or images taken from other games.

## Who decides

The maintainers are listed in [MAINTAINERS.md](MAINTAINERS.md) — today, the
game's creator alone. A maintainer reviews every pull request and merges it once
the continuous integration is green. What goes to the official game's servers,
and when, is decided by its owner only: a merge here never deploys anything by
itself.
