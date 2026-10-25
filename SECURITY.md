# Security policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Report it
privately in one of two ways:

1. **GitHub** — the *Security* tab of this repository → *Report a
   vulnerability* (a private advisory only the maintainers can see); or
2. **E-mail** — suporte@nivrael.com, with "SECURITY" in the subject.

Include what you found, how to reproduce it (the smallest steps you can), what
an attacker could do with it, and the commit or version you looked at. If you
have a fix in mind, describe it in the report rather than in a public pull
request.

We answer within **7 days**, keep you informed while we fix it, and credit you
in the advisory unless you prefer otherwise. This is a volunteer project: there
is no bug bounty.

## Scope

- **In scope:** the code in this repository — the web server and its API, the
  session and sign-in flows, the Telegram integration, the client, the
  migrations and the local runner (`community/`).
- **The official game's servers are not a test target.** Do not scan, load-test
  or attack the official game or its players' accounts; reproduce against your
  own instance (`docker compose up`). Proof that needs real players' data is
  never necessary — and never acceptable.
- **Known by design, not a vulnerability:** the local development login
  (`NIVRAEL_DEV_LOGIN=1`) signs in with a name and no password. It refuses to
  open when `WEBHOOK_URL` is set and only accepts requests from the local
  machine or network — but it must never run on a public server. A Firebase
  *web* API key is public by design; what protects accounts is the server-side
  verification of the ID token (`core/firebase_auth.py`).

## Supported versions

Only the latest state of the `main` branch receives fixes.

## Secrets

This repository must never contain a secret. `scripts/_verifica_copia_publica.py`
checks every file for tokens, keys, passwords in URLs, `.env` files, private
folders and personal data, and is part of `scripts/run_tests.py`. If you ever see
a credential here, report it as above — do not use it.
