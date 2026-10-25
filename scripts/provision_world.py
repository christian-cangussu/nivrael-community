"""CLI — provision a new game world (Sistema Multi-Servidor — Fase 2).

Creates a fresh, isolated world (CREATE DATABASE + migrations + seeds), registers
it in the control DB, sets its balance, and mints an access code for the owner.
This is the RELIABLE first-provision path (synchronous, prints every step). The
in-app Admin Panel runs the SAME core (core.world_provision.provision_world).

Requires env: DATABASE_URL (main, to derive host/user) + CONTROL_DATABASE_URL.

Usage:
  python scripts/provision_world.py <key> "<name>" [options]

Options:
  --speed S          cultivation_speed (default 1.0; 0.3 ≈ 3x slower realms)
  --public           publicly listed + NO code (default: private + code-gated)
  --no-code          do not mint an access code
  --code CODE        use a specific code instead of a random one
  --uses N           code max uses (default 1)
  --expires-days N   code expiry in days (default: never)
  --db-url URL       explicit DSN (default: derive <main_db>_<key>)
  --no-create-db     assume the DB already exists (skip CREATE DATABASE)
  --monetization     enable real-money flows (DANGER — default OFF/sandbox)

Example (the first trial world):
  python scripts/provision_world.py s2 "Servidor de Provação" --speed 0.3
"""
import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


async def _main():
    p = argparse.ArgumentParser(description="Provision a new Nivrael game world.")
    p.add_argument("key", help="world key slug, e.g. s2")
    p.add_argument("name", help='display name, e.g. "Servidor de Provação"')
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--public", action="store_true")
    p.add_argument("--no-code", action="store_true")
    p.add_argument("--code", default=None)
    p.add_argument("--uses", type=int, default=1)
    p.add_argument("--expires-days", type=int, default=None)
    p.add_argument("--db-url", default=None)
    p.add_argument("--no-create-db", action="store_true")
    p.add_argument("--monetization", action="store_true")
    args = p.parse_args()

    from database.control_db import control_enabled, bootstrap_control_db
    if not control_enabled():
        print("✗ CONTROL_DATABASE_URL is not set — multi-world is disabled. Set it and retry.")
        sys.exit(2)

    # Make sure the control schema (servers/codes/access/active) exists.
    await bootstrap_control_db()

    balance = {}
    if args.speed != 1.0:
        balance["cultivation_speed"] = args.speed

    from core.world_provision import provision_world
    try:
        res = await provision_world(
            args.key, args.name,
            db_url=args.db_url,
            balance_config=balance,
            requires_code=not args.public,
            is_public=args.public,
            monetization_enabled=args.monetization,
            create_db=not args.no_create_db,
            gen_code=not args.no_code,
            code=args.code,
            code_max_uses=args.uses,
            code_expires_days=args.expires_days,
        )
    except Exception as e:
        print(f"\n✗ Provision FAILED: {e.__class__.__name__}: {e}")
        print("  (If it's a CREATE DATABASE permission error, pre-create the DB and")
        print("   re-run with --no-create-db, or grant CREATEDB to the bot's role.)")
        sys.exit(1)

    def _redact(url: str) -> str:
        import re
        return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", url or "")

    print("\n✅ World provisioned:")
    print(f"   key   : {res['key']}")
    print(f"   name  : {res['name']}")
    print(f"   db    : {_redact(res['db_url'])}")
    print(f"   status: {res['status']}")
    print(f"   speed : {balance.get('cultivation_speed', 1.0)} (cultivation_speed; <1 = slower)")
    print(f"   sandbox (monetization off): {not res['monetization_enabled']}")
    if res.get("code"):
        print(f"\n   🎟️  ACCESS CODE: {res['code']}")
        print("   Give this to the players you want to let into the world.")
    print("\n   The running bot picks up the world on its next restart; the in-app")
    print("   Admin Panel + the lobby route to it live immediately within this process.")


if __name__ == "__main__":
    asyncio.run(_main())
