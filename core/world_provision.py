"""Provisioning of new game worlds (Sistema Multi-Servidor — Fase 2).

Creates a fresh world DB (best-effort ``CREATE DATABASE``), runs the FULL
migrations+seeds pipeline against it, registers it in the control DB, and
optionally mints an access code. Shared by the CLI
(``scripts/provision_world.py``) and the in-app Admin Panel endpoint, so both
paths build identical worlds.

Safety (57 real players + the locked design laws):
  • A fresh world is registered as ``status='maintenance'`` and only flipped to
    ``active`` AFTER init succeeds → a half-built world is never enterable.
  • Secondary worlds are born ``monetization_enabled=false`` (sandbox) and
    ``requires_code=true`` (code-gated). ``main`` can never be provisioned here.
  • ``init_world_db`` is run under ``use_world(key)`` so every query lands in the
    new world, never main.
  • ``CREATE DATABASE`` needs a role with CREATEDB. If that's not available the
    caller gets a clear error and can pre-create the DB / use ``--no-create-db``.
"""
import json
import logging
import re
import secrets
from urllib.parse import urlparse, urlunparse

from sqlalchemy import text

from config import DATABASE_URL, WORLD_DEFAULT_POOL_SIZE, WORLD_DEFAULT_MAX_OVERFLOW

logger = logging.getLogger(__name__)

# A world key is a short slug: lowercase, starts with a letter (so it's a valid
# DB-name suffix + a clean URL/callback token). 'main' is reserved.
WORLD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")

# No ambiguous chars (0/O, 1/I/l) so a code is easy to read/type off a phone.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_access_code(length: int = 10) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def _plain_dsn(url: str) -> str:
    """asyncpg.connect wants a plain ``postgresql://`` DSN (no ``+asyncpg``)."""
    return (
        (url or "")
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgres+asyncpg://", "postgresql://")
    )


def derive_world_db_url(key: str) -> str:
    """Derive a new world's DSN from ``DATABASE_URL`` by suffixing the DB name
    with ``_<key>`` (e.g. ``…/nivrael`` → ``…/nivrael_s2``). Host/user/password/
    port are inherited from the main DSN. The caller may override with an
    explicit ``db_url``."""
    p = urlparse(_plain_dsn(DATABASE_URL))
    base_db = (p.path or "/").lstrip("/") or "postgres"
    return urlunparse(p._replace(path="/" + f"{base_db}_{key}"))


def _maintenance_dsn(world_db_url: str) -> str:
    """A DSN to the ``postgres`` maintenance DB on the same server — you cannot
    ``CREATE DATABASE`` while connected to the target DB."""
    p = urlparse(_plain_dsn(world_db_url))
    return urlunparse(p._replace(path="/postgres"))


def _db_name(world_db_url: str) -> str:
    return (urlparse(_plain_dsn(world_db_url)).path or "/").lstrip("/")


async def create_database_if_missing(world_db_url: str) -> bool:
    """``CREATE DATABASE`` for the new world if it does not exist. Best-effort —
    requires the connecting role to have CREATEDB. Returns True if it created the
    DB, False if it already existed. Raises on a real connection/permission error
    so the caller can surface a clear message."""
    import asyncpg
    dbname = _db_name(world_db_url)
    conn = await asyncpg.connect(_maintenance_dsn(world_db_url))
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", dbname
        )
        if exists:
            return False
        # DB identifiers cannot be parameterized; dbname derives from a
        # WORLD_KEY_RE-validated key + the main DB name, so it is safe to quote.
        await conn.execute(f'CREATE DATABASE "{dbname}"')
        return True
    finally:
        await conn.close()


async def provision_world(
    key: str,
    name: str,
    *,
    db_url: str | None = None,
    balance_config: dict | None = None,
    requires_code: bool = True,
    is_public: bool = False,
    monetization_enabled: bool = False,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    status: str = "active",
    create_db: bool = True,
    gen_code: bool = True,
    code: str | None = None,
    code_max_uses: int = 1,
    code_expires_days: int | None = None,
) -> dict:
    """Provision a complete, isolated game world end-to-end.

    Steps: validate → (CREATE DATABASE) → register row as 'maintenance' →
    make routable in-process → run migrations+seeds → flip to ``status`` →
    (mint access code). Idempotent: re-running upserts the row and re-runs the
    idempotent seed pipeline. Returns a summary dict (includes ``code``)."""
    from database.control_db import get_control_session_factory, control_enabled
    from database.db import (
        init_world_db, register_world, demote_world, use_world, get_session_factory,
    )

    key = (key or "").strip().lower()
    name = (name or "").strip()
    if not WORLD_KEY_RE.match(key):
        raise ValueError(f"invalid world key {key!r} — must match ^[a-z][a-z0-9_]{{1,30}}$")
    if key == "main":
        raise ValueError("'main' is the live world and cannot be provisioned")
    if not name:
        raise ValueError("a world name is required")
    if not control_enabled():
        raise RuntimeError("CONTROL_DATABASE_URL is not set — multi-world is disabled")
    sm = get_control_session_factory()
    if sm is None:
        raise RuntimeError("control DB session factory unavailable")

    db_url = (db_url or derive_world_db_url(key)).strip()
    # O registo guarda o ENDEREÇO; o login fica no env, e `with_env_credentials`
    # devolve-o a quem liga (2026-10-24). Um `db_url` com OUTRO login — um mundo
    # noutro servidor — fica guardado como foi dado.
    from database.control_db import strip_credentials, with_env_credentials
    stored_url = strip_credentials(db_url)
    if with_env_credentials(stored_url) != db_url:
        stored_url = db_url
    pool_size = pool_size or WORLD_DEFAULT_POOL_SIZE
    max_overflow = WORLD_DEFAULT_MAX_OVERFLOW if max_overflow is None else max_overflow
    balance_config = balance_config or {}

    created = False
    if create_db:
        created = await create_database_if_missing(db_url)
        logger.info("provision %s: database %s", key, "created" if created else "already existed")

    row = {
        "key": key, "name": name, "db_url": stored_url, "status": "maintenance",
        "is_default": False, "requires_code": requires_code,
        "monetization_enabled": monetization_enabled, "is_public": is_public,
        "pool_size": pool_size, "max_overflow": max_overflow,
        "balance_config": balance_config,
    }

    # 1) Upsert the control-DB row as MAINTENANCE (not enterable yet).
    #    RMW on balance_config: the incoming config carries only the balance KNOBS,
    #    so on a re-provision of a LIVE world we fold the existing per-world "features"
    #    sub-block back in — otherwise re-provisioning would silently wipe the admin's
    #    toggled feature flags (mirrors api_admin_set_balance's guard; FF-2 / Lei §1).
    async with sm() as session:
        await session.execute(text(
            "INSERT INTO servers (key, name, db_url, status, is_default, requires_code, "
            "  monetization_enabled, is_public, pool_size, max_overflow, balance_config) "
            "VALUES (:key,:name,:db_url,'maintenance',false,:rc,:mon,:pub,:ps,:mo, CAST(:bc AS JSONB)) "
            "ON CONFLICT (key) DO UPDATE SET "
            "  name=EXCLUDED.name, db_url=EXCLUDED.db_url, requires_code=EXCLUDED.requires_code, "
            "  monetization_enabled=EXCLUDED.monetization_enabled, is_public=EXCLUDED.is_public, "
            "  pool_size=EXCLUDED.pool_size, max_overflow=EXCLUDED.max_overflow, "
            "  balance_config = EXCLUDED.balance_config "
            "    || jsonb_build_object('features', COALESCE(servers.balance_config->'features', '{}'::jsonb)) "
            "    || (CASE WHEN jsonb_exists(servers.balance_config, 'realm') "
            "             THEN jsonb_build_object('realm', servers.balance_config->'realm') "
            "             ELSE '{}'::jsonb END), "
            "  status='maintenance'"),
            {"key": key, "name": name, "db_url": stored_url, "rc": requires_code,
             "mon": monetization_enabled, "pub": is_public, "ps": pool_size,
             "mo": max_overflow, "bc": json.dumps(balance_config)})
        await session.commit()

    # 2) Make the world routable in THIS process, then run the full pipeline
    #    against it (bound to the world so stray get_session_factory()s land here).
    #    If init/verify FAILS, the world must NOT survive as a tickable/'active'
    #    world: a half-built world (no `players` table) makes the scheduler spin
    #    and spam (2026-06-24 incident). So on failure we de-register it in-process
    #    AND leave its control row at 'maintenance' (never enterable, never ticked),
    #    then re-raise so the caller surfaces the error.
    register_world(row)
    try:
        with use_world(key):
            await init_world_db(key)
            # init MUST have created the core schema. Verify the cornerstone table
            # exists before we ever flip the world to 'active'.
            async with get_session_factory()() as vsession:
                await vsession.execute(text("SELECT 1 FROM players LIMIT 1"))
    except Exception:
        # Take the half-built world OUT of service: de-register in-process +
        # revert the control row to 'maintenance' (never tickable, never routed-to),
        # then re-raise so the caller surfaces the error.
        await demote_world(key)
        logger.exception("provision %s: world init/verify FAILED — left at 'maintenance'", key)
        raise

    # 3) Schema+seeds are in place — flip to the requested status.
    register_world({**row, "status": status})
    # A previously-degraded world (re-provision after a failure) reports afresh.
    try:
        from core.scheduler import reset_world_degraded_state
        reset_world_degraded_state(key)
    except Exception:
        logger.warning(
            "provision %s: could not reset scheduler degraded-state "
            "(world will not re-report failures afresh)", key, exc_info=True)
    async with sm() as session:
        await session.execute(text("UPDATE servers SET status=:s WHERE key=:k"),
                              {"s": status, "k": key})
        await session.commit()

    # 4) Optional access code (code-gated worlds need at least one). Compute the
    # expiry in Python — a bare `:d IS NULL` parameter is an untyped NULL that
    # asyncpg/Postgres can't infer, which silently failed the auto-code on
    # provisioning (and the manual gen-code endpoint).
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    out_code = None
    if gen_code:
        expires_at_val = (
            _dt.now(_tz.utc) + _td(days=code_expires_days)
            if code_expires_days is not None else None
        )
        async with sm() as session:
            for _ in range(5):  # retry the astronomically-unlikely PK collision
                cand = code or generate_access_code()
                ins = await session.execute(text(
                    "INSERT INTO server_access_codes (code, server_key, max_uses, expires_at, note) "
                    "VALUES (:c, :k, :mu, :exp, :note) "
                    "ON CONFLICT (code) DO NOTHING RETURNING code"),
                    {"c": cand, "k": key, "mu": code_max_uses, "exp": expires_at_val,
                     "note": f"provisioned {key}"})
                if ins.first() is not None:
                    out_code = cand
                    break
                if code:  # an explicit code that already exists → stop, report it
                    out_code = code
                    break
            await session.commit()

    logger.info("✅ provisioned world %r (%s) status=%s code=%s", key, name, status, out_code)
    return {
        "key": key, "name": name, "db_url": stored_url, "status": status,
        "created_db": created, "code": out_code,
        "requires_code": requires_code, "is_public": is_public,
        "monetization_enabled": monetization_enabled, "balance_config": balance_config,
    }
