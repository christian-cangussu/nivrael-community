"""Control plane for the multi-server system (Sistema Multi-Servidor — Fase 1).

The control DB is a SEPARATE, isolated Postgres database (NOT a game world).
It maps ``telegram_id -> unlocked worlds + active world`` and holds the server
registry that ``database/db.py`` reads to build per-world engines.

Design laws (Cerebro/Nivrael/GameDesign/multi_server_architecture.md):
  • Aditivo (§1/§5): this module is a NO-OP when ``CONTROL_DATABASE_URL`` is
    empty — the bot then runs exactly as a single-world ("main") deployment.
  • Degrade-to-main: ANY control-plane error must be swallowed by the caller so
    the bot never crashes; resolution then falls back to "main".
  • The control DB SURVIVES the wipe of any game world (separate DSN/DB).

This module owns ONLY the control-plane engine + schema bootstrap + registry
reads. The per-world game engines + the ``current_world`` contextvar router live
in ``database/db.py``.
"""

import logging
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config import CONTROL_DATABASE_URL, DATABASE_URL, MONETIZATION_ENABLED

logger = logging.getLogger(__name__)

# The canonical default world. Mirrors database.db.MAIN_WORLD_KEY (kept as a
# literal here to avoid an import cycle; db.py imports control_db, not vice-versa).
MAIN_WORLD_KEY = "main"
MAIN_WORLD_NAME = "Servidor Principal"

_control_engine = None
_control_session = None


def control_enabled() -> bool:
    """True when the control plane is available.

    The control plane lives in its own ``CONTROL_DATABASE_URL`` when set;
    otherwise it FALLS BACK to the MAIN game DB (``DATABASE_URL``) so the lobby +
    Admin Panel work out-of-the-box with ZERO extra setup — the 4 small control
    tables (servers/codes/access/active) just sit alongside the game tables. This
    only requires the owner to set ``ADMIN_USERS`` to their Telegram id.

    (Set a dedicated ``CONTROL_DATABASE_URL`` before the launch wipe so the
    control data survives a rebuild of the main DB — §11/§12 of the design doc.)

    Returns False only if NEITHER url is configured (no DB at all → the bot can't
    run anyway), in which case the multi-world layer stays fully dormant."""
    return bool(_control_url())


def _control_url() -> str:
    # Prefer the dedicated control DB; fall back to the main game DB so the
    # control plane is available without a second database to provision.
    url = (CONTROL_DATABASE_URL or "").strip() or (DATABASE_URL or "").strip()
    url = url.replace("postgresql://", "postgresql+asyncpg://")
    url = url.replace("postgres://", "postgresql+asyncpg://")
    return url


# ── 一 A senha dos mundos tem UM dono: o env (2026-10-24) ─────────────────────
# MEDIDO na produção (só leitura): as duas linhas do registo, `main` e `s2`,
# guardavam o `DATABASE_URL` INTEIRO — utilizador e senha do superuser — numa
# tabela que qualquer leitura da base lê. Dois donos da mesma senha: trocar a do
# env (o papel sem superuser) deixava o s2 a entrar com a antiga. O registo passa
# a guardar só o ENDEREÇO, e quem liga pede o login ao env.

def strip_credentials(url: str) -> str:
    """``url`` without its ``user[:password]@`` — what the registry stores."""
    parts = urlsplit(url or "")
    if "@" not in parts.netloc:
        return url or ""
    return urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[1]))


def with_env_credentials(url: str) -> str:
    """A world DSN without ``user[:password]@`` borrows them from ``DATABASE_URL`` —
    only on the env's OWN server (same host and port): the env's password never
    goes to another host, whatever a registry row says.

    A DSN that names its own user is returned exactly as written: the rows written
    before 2026-10-24 keep connecting byte for byte, and a world on another server
    keeps its own login."""
    parts = urlsplit(url or "")
    env = urlsplit(DATABASE_URL or "")
    if not parts.netloc or "@" in parts.netloc or "@" not in env.netloc:
        return url or ""
    if (parts.hostname, parts.port or 5432) != (env.hostname, env.port or 5432):
        return url
    return urlunsplit(parts._replace(netloc=env.netloc.rsplit("@", 1)[0] + "@" + parts.netloc))


def _ensure_control_engine():
    """Lazily build the control-plane engine/sessionmaker. Returns the
    sessionmaker, or ``None`` when the control DB is disabled."""
    global _control_engine, _control_session
    if not control_enabled():
        return None
    if _control_engine is None:
        url = _control_url()
        if "asyncpg://" not in url:
            logger.warning("CONTROL_DATABASE_URL malformed — running main-only")
            return None
        # Small pool: the control DB only serves lobby lookups (resolve active
        # world, list/redeem/switch), never the hot game path.
        _control_engine = create_async_engine(
            url,
            echo=False,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_timeout=10,
            pool_reset_on_return="rollback",
            connect_args={
                "command_timeout": 15,
                "server_settings": {
                    "idle_in_transaction_session_timeout": "30000",
                    "statement_timeout": "15000",
                },
            },
        )
        _control_session = async_sessionmaker(
            _control_engine, class_=AsyncSession, expire_on_commit=False
        )
    return _control_session


def get_control_session_factory():
    """Return the control-plane sessionmaker (or ``None`` if disabled).

    Lobby/control endpoints (Fase 2) open sessions via this factory — NEVER via
    ``database.db.get_session_factory()`` (that is the active GAME world)."""
    return _ensure_control_engine()


# ── Schema bootstrap (idempotent; script à parte do migrations/ dos mundos) ──
_BOOTSTRAP_DDL = [
    """
    CREATE TABLE IF NOT EXISTS servers (
        key                  TEXT PRIMARY KEY,
        name                 TEXT NOT NULL,
        db_url               TEXT NOT NULL,
        status               TEXT NOT NULL DEFAULT 'active',
        is_default           BOOLEAN NOT NULL DEFAULT false,
        requires_code        BOOLEAN NOT NULL DEFAULT true,
        monetization_enabled BOOLEAN NOT NULL DEFAULT false,
        is_public            BOOLEAN NOT NULL DEFAULT false,
        pool_size            INTEGER,
        max_overflow         INTEGER,
        sort_order           INTEGER NOT NULL DEFAULT 100,
        balance_config       JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # Idempotent add for a control DB created before Fase 2 (the Fase 1 schema
    # had no per-server balance). NOT NULL DEFAULT '{}' so existing rows (= main)
    # get an empty config; main's config is IGNORED by the engine regardless.
    "ALTER TABLE servers ADD COLUMN IF NOT EXISTS balance_config JSONB NOT NULL DEFAULT '{}'::jsonb",
    """
    CREATE TABLE IF NOT EXISTS server_access_codes (
        code        TEXT PRIMARY KEY,
        server_key  TEXT NOT NULL REFERENCES servers(key),
        max_uses    INTEGER NOT NULL DEFAULT 1,
        uses        INTEGER NOT NULL DEFAULT 0,
        expires_at  TIMESTAMPTZ,
        note        TEXT,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_server_access (
        telegram_id BIGINT NOT NULL,
        server_key  TEXT NOT NULL REFERENCES servers(key),
        granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (telegram_id, server_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_active_server (
        telegram_id BIGINT PRIMARY KEY,
        server_key  TEXT NOT NULL REFERENCES servers(key),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # Admin Console v2 — audit trail of every admin WRITE (grant / set-realm /…).
    # Lives in the control plane so it survives a game-world wipe.
    """
    CREATE TABLE IF NOT EXISTS admin_audit_log (
        id          BIGSERIAL PRIMARY KEY,
        admin_id    BIGINT NOT NULL,
        world_key   TEXT NOT NULL,
        target_id   BIGINT,
        action      TEXT NOT NULL,
        detail      JSONB,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_admin_audit_created ON admin_audit_log (created_at DESC)",
    # ── WEB-B Fase 1 (2026-08-21) — A IDENTIDADE DEIXA DE SER O TELEGRAM ──────
    #
    # `auth_identities` responde a UMA pergunta: *quem é esta pessoa?* — e a
    # resposta é um `player_id`, nunca uma credencial. O `telegram_id` continua
    # a ser a chave primária do jogo (74 FK, zero migration nelas) mas deixa de
    # ser a prova de identidade: o Telegram passa a ser **um provider entre
    # vários**, e a Fase 2 (email) é inserir uma linha aqui, não um rewrite.
    #
    # ⚠️ POR QUE VIVE NO PLANO DE CONTROLO E NÃO EM `migrations/` (correcção
    # MEDIDA ao spec, 2026-08-21). O spec pedia `migrations/140_auth_identities.sql`
    # com `REFERENCES players(telegram_id)`. Medir a produção derrubou isso:
    #
    #   main = 240 personagens · s2 = 23 personagens · soma = 263
    #   INTERSECÇÃO = 15  ⇒  **248 PESSOAS**, não 263.
    #   (e `player_active_server` tem exactamente 248 rows — a mesma verdade)
    #
    # Ou seja: 15 pessoas têm DOIS personagens, um por mundo. Uma tabela por
    # mundo daria a essas 15 duas identidades (o `UNIQUE` é por base de dados),
    # e "a sessão é o teu JOGADOR" viraria "a sessão é o teu jogador NESTE
    # mundo" — exactamente o que a decisão de 20/08 existe para evitar. Pior: na
    # Fase 2, procurar um email teria de varrer todos os mundos.
    #
    # A identidade é da PESSOA; o mundo continua a ser decidido por
    # `player_active_server` (o mecanismo que o Telegram já usa hoje). Logo isto
    # é irmão de `player_active_server`/`player_server_access` e vive ao lado
    # deles — com o mesmo padrão da casa: `telegram_id BIGINT` **sem FK** para
    # `players`, porque o control DB pode ser (e será, antes do launch) uma base
    # separada onde `players` não existe.
    """
    CREATE TABLE IF NOT EXISTS auth_identities (
        id            BIGSERIAL PRIMARY KEY,
        player_id     BIGINT NOT NULL,
        provider      TEXT   NOT NULL,
        provider_uid  TEXT   NOT NULL,
        profile       JSONB  NOT NULL DEFAULT '{}'::jsonb,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_login_at TIMESTAMPTZ,
        UNIQUE (provider, provider_uid)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_auth_identities_player ON auth_identities (player_id)",
    # A SESSÃO — o único item perigoso do lote. 248 pessoas com compras reais
    # atrás, e até hoje não havia NADA para roubar (o HMAC do Telegram não é uma
    # credencial persistente). Requisitos que esta tabela existe para cumprir:
    #
    #  • REVOGAÇÃO REAL. Um cookie assinado sem estado no servidor é eterno até
    #    expirar — inaceitável. A row É a verdade: `revoked_at` mata a sessão no
    #    pedido seguinte, sem esperar por expiração.
    #  • CSRF POR CONSTRUÇÃO. `csrf` é gerado por sessão e guardado AQUI. O
    #    header tem de bater com esta coluna — não com um segundo cookie. Isso é
    #    mais forte que o double-submit clássico: quem consiga escrever cookies
    #    (um subdomínio comprometido) ainda não consegue forjar o par.
    #  • Nunca guardamos o `init_data` nem o `hash` do widget. `tg_user` guarda
    #    só {first_name, username} — o que o `world/start` precisa para criar o
    #    personagem com o mesmo nome que o Telegram daria.
    """
    CREATE TABLE IF NOT EXISTS auth_sessions (
        sid          TEXT PRIMARY KEY,
        player_id    BIGINT NOT NULL,
        identity_id  BIGINT,
        provider     TEXT   NOT NULL DEFAULT 'telegram',
        csrf         TEXT   NOT NULL,
        tg_user      JSONB  NOT NULL DEFAULT '{}'::jsonb,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at   TIMESTAMPTZ NOT NULL,
        revoked_at   TIMESTAMPTZ
    )
    """,
    # ── WEB-B Fase 2 — O ID SINTÉTICO ────────────────────────────────────────
    #
    # `players.telegram_id` é a chave primária do jogo (74 FK). Quem entra pelo
    # Google/Apple/e-mail não tem um, e inventar um positivo colidiria com uma
    # conta real do Telegram amanhã. Por isso nasce **negativo**.
    #
    # ⚠️ POR QUE UMA SEQUÊNCIA, E POR QUE AQUI:
    #  • `MAX(telegram_id)+1` seria uma condição de corrida e obrigaria a ler a
    #    tabela `players` — que é POR MUNDO. Duas pessoas a registar-se em
    #    mundos diferentes no mesmo segundo receberiam o mesmo id.
    #  • A sequência vive no PLANO DE CONTROLO porque é aí que a identidade
    #    vive (a mesma razão de `auth_identities`): o id tem de ser único ENTRE
    #    MUNDOS, não dentro de um. Um jogador de e-mail pode vir a ter
    #    personagem em dois mundos, como as 15 pessoas de hoje.
    #  • Sequências do Postgres **nunca reutilizam** um valor, nem com
    #    ROLLBACK. Gaps sim; repetição nunca. É exactamente a garantia pedida.
    #
    # O espaço negativo foi medido a 2026-08-21 e está livre: `main` 0
    # negativos (menor id 175.746.696), `s2` 0 negativos (menor 337.746.273).
    #
    # ⚠️ O id NÃO é um segredo e nunca é uma credencial — provar quem se é
    # continua a ser uma pergunta a `auth_identities`. Ser sequencial é
    # irrelevante: os ids do Telegram também são enumeráveis.
    "CREATE SEQUENCE IF NOT EXISTS web_player_id_seq AS BIGINT START WITH 1 INCREMENT BY 1",
    # ── UMA CONTA, QUALQUER PLATAFORMA (2026-08-26) ──────────────────────────
    #
    # O código que junta duas credenciais no mesmo jogador. Vive no plano de
    # controlo pela mesma razão de `auth_identities`: o vínculo é da PESSOA e
    # atravessa mundos. Uma tabela por mundo daria códigos que só funcionam
    # onde foram criados — e a pessoa não sabe (nem devia saber) em que mundo
    # está quando liga a conta.
    #
    # ⚠️ `used_at` em vez de DELETE: um código gasto tem de continuar a
    # existir para o segundo resgate falhar com "já usado" em vez de com
    # "não existe". A limpeza é oportunista, na emissão seguinte.
    """
    CREATE TABLE IF NOT EXISTS account_link_codes (
        code       TEXT PRIMARY KEY,
        player_id  BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at TIMESTAMPTZ NOT NULL,
        used_at    TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_link_codes_player ON account_link_codes (player_id)",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_player ON auth_sessions (player_id)",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at)",
]

# Idempotent main row. ON CONFLICT re-syncs db_url + the locked invariants every
# boot WITHOUT clobbering a custom name. NOTE: db.py still derives main's ENGINE
# from config.DATABASE_URL, not from this row — this row exists for the lobby UI
# and as the registry anchor.
#
# ⚠️ PIVOT 2026-08-11 — `is_default` DEIXOU de ser forçado aqui. Ele passou a
# significar *é aqui que se nasce* (ver `database.db.signup_world_key`), e o
# `main` é agora o Mundo Legado: reafirmá-lo a cada boot desfazia, em silêncio e
# a cada deploy, a escolha do owner. Continua a nascer `true` num control DB
# vazio (o VALUES), o que mantém a instalação de raiz a nascer em `main`.
# O que CONTINUA forçado é o que é mesmo invariante do `main`: ele nunca fecha,
# nunca pede código — e, na edição comunitária, a monetização dele segue a
# flag `NIVRAEL_MONETIZATION` (desligada por defeito) em vez de nascer forçada.
_BOOTSTRAP_MAIN_ROW = """
    INSERT INTO servers (key, name, db_url, status, is_default, requires_code,
                         monetization_enabled, is_public, sort_order)
    VALUES (:key, :name, :db_url, 'active', true, false, :mon, true, 0)
    ON CONFLICT (key) DO UPDATE SET
        db_url               = EXCLUDED.db_url,
        status               = 'active',
        requires_code        = false,
        monetization_enabled = EXCLUDED.monetization_enabled
"""


async def bootstrap_control_db() -> bool:
    """Create the control schema + seed the ``main`` row, idempotently.

    Returns True if the control DB was bootstrapped, False if disabled. Raises
    on a real DB error — the caller (init_db) wraps this in try/except so a
    control-plane outage degrades to main-only instead of crashing the bot."""
    sm = _ensure_control_engine()
    if sm is None:
        return False
    async with _control_engine.begin() as conn:
        for ddl in _BOOTSTRAP_DDL:
            await conn.execute(text(ddl))
        await conn.execute(
            text(_BOOTSTRAP_MAIN_ROW),
            {"key": MAIN_WORLD_KEY, "name": MAIN_WORLD_NAME, "db_url": strip_credentials(DATABASE_URL),
             "mon": MONETIZATION_ENABLED},
        )
    logger.info("✅ Control DB bootstrapped (servers/codes/access/active)")
    return True


async def strip_registry_credentials() -> int:
    """Rewrite each world row whose ``db_url`` carries EXACTLY the env's login as
    the same address without it. Returns how many rows changed (0 once clean).

    Changes no connection: the rewritten row gets the very same DSN back from
    ``with_env_credentials``. A row with ANOTHER login is left alone. Its own step
    in ``init_db`` (never inside the bootstrap): a failure here must leave the
    lobby and the registry running, with the rows as they were."""
    if _ensure_control_engine() is None:
        return 0
    mudadas = 0
    async with _control_engine.begin() as conn:
        rows = (await conn.execute(text("SELECT key, db_url FROM servers"))).all()
        for key, url in rows:
            sem = strip_credentials(url)
            if sem != url and with_env_credentials(sem) == url:
                await conn.execute(text("UPDATE servers SET db_url = :u WHERE key = :k"),
                                   {"u": sem, "k": key})
                mudadas += 1
    if mudadas:
        logger.info("🔐 registry: %d world row(s) no longer store the env's password", mudadas)
    return mudadas


async def fetch_world_registry() -> list[dict]:
    """Return the active server rows from the control DB (empty list if disabled).

    Used by ``database.db.load_world_registry()`` to merge secondary worlds into
    the per-world engine registry at startup."""
    sm = _ensure_control_engine()
    if sm is None:
        return []
    async with sm() as session:
        rows = (await session.execute(text(
            "SELECT key, name, db_url, status, is_default, requires_code, "
            "monetization_enabled, is_public, pool_size, max_overflow, sort_order, "
            "balance_config "
            "FROM servers WHERE status = 'active'"
        ))).mappings().all()
        return [dict(r) for r in rows]


# Cache curto de resolução (pivot 2026-08-11). O CHAT passou a resolver o mundo
# a cada update; sem isto seria uma query ao plano de controlo por mensagem. TTL
# curto + invalidação explícita no switch — um mundo trocado no lobby vale de
# imediato, e no pior caso a troca demora `_RESOLVE_TTL` a chegar ao chat.
_resolve_cache: dict[int, tuple[str, float]] = {}
_RESOLVE_TTL = 60.0


def invalidate_world_cache(telegram_id: int | None = None) -> None:
    if telegram_id is None:
        _resolve_cache.clear()
    else:
        _resolve_cache.pop(int(telegram_id), None)


async def set_active_world(telegram_id: int, server_key: str) -> bool:
    """Bind a player to a world (upsert em ``player_active_server``) + declarar o
    acesso. Idempotente. Best-effort: devolve False em qualquer erro e NUNCA
    levanta — quem chama está no meio de criar um personagem.

    Espelha exatamente o que o lobby já faz (``api_lobby_switch``); existe para o
    /start do CHAT poder registar o mundo de nascimento sem duplicar SQL."""
    sm = _ensure_control_engine()
    if sm is None or not telegram_id or not server_key:
        return False
    try:
        async with sm() as session:
            await session.execute(text(
                "INSERT INTO player_server_access (telegram_id, server_key) "
                "VALUES (:tid, :k) ON CONFLICT DO NOTHING"),
                {"tid": telegram_id, "k": server_key})
            await session.execute(text(
                "INSERT INTO player_active_server (telegram_id, server_key) "
                "VALUES (:tid, :k) ON CONFLICT (telegram_id) DO UPDATE "
                "SET server_key = EXCLUDED.server_key, updated_at = now()"),
                {"tid": telegram_id, "k": server_key})
            await session.commit()
        invalidate_world_cache(telegram_id)
        return True
    except Exception:
        logger.warning("set_active_world failed tid=%s key=%s", telegram_id, server_key,
                       exc_info=True)
        return False


async def resolve_active_world_cached(telegram_id: int) -> str:
    """`resolve_active_world` com cache de `_RESOLVE_TTL` segundos.

    Para o CHAT, que resolve a cada update. O mini-app continua a usar a versão
    crua (uma resolução por request já era o contrato, e o middleware dela
    depende para ver um switch imediatamente)."""
    import time as _t
    now = _t.monotonic()
    hit = _resolve_cache.get(int(telegram_id))
    if hit is not None and (now - hit[1]) < _RESOLVE_TTL:
        return hit[0]
    key = await resolve_active_world(telegram_id)
    _resolve_cache[int(telegram_id)] = (key, now)
    return key


async def resolve_active_world(telegram_id: int) -> str:
    """Resolve a player's active world key from the control DB.

    Sem row → o **mundo de nascimento** (``database.db.signup_world_key()``), não
    `main`.

    ⚠️ ISTO MUDOU NO PIVOT DE 2026-08-11 e a pré-condição é load-bearing: até
    aqui "sem row" descrevia TAMBÉM os 240 personagens do `main` (esta docstring
    dizia-o: *"the 57 beta players have none → main"*), portanto mudar o fallback
    tê-los-ia mudado de mundo a todos. Antes de esta linha existir, correu-se
    ``tools/db_write_s2_abertura.py``, que escreveu ``player_active_server='main'``
    para os 240 — logo "sem row" passou a significar, de facto, **jogador novo**.
    Se alguma vez se restaurar o control DB de um backup anterior a esse
    backfill, ESTA função manda os legados para o mundo novo. Não mexer sem
    reexecutar o backfill.

    Degrada para ``main`` com o control DB em baixo/desligado (Lei §1)."""
    sm = _ensure_control_engine()
    if sm is None:
        return MAIN_WORLD_KEY
    try:
        from database.db import signup_world_key
    except Exception:
        signup_world_key = lambda: MAIN_WORLD_KEY  # noqa: E731
    try:
        async with sm() as session:
            # Only route into the active world if that world is STILL 'active'.
            # If the owner closes/maintenances a test world (or the row is gone),
            # the player degrades to main (Lei §1) instead of being stuck on a
            # paused/closed world. main itself is always an 'active' row.
            key = (await session.execute(
                text("SELECT pas.server_key FROM player_active_server pas "
                     "JOIN servers s ON s.key = pas.server_key "
                     "WHERE pas.telegram_id = :tid AND s.status = 'active'"),
                {"tid": telegram_id},
            )).scalar_one_or_none()
            return key or signup_world_key()
    except Exception:
        logger.warning("resolve_active_world failed for %s — defaulting to main",
                       telegram_id, exc_info=True)
        return MAIN_WORLD_KEY


# ── UMA CONTA, QUALQUER PLATAFORMA — resolver a IDENTIDADE ──────────────────
#
# Depois do vínculo, o `telegram_id` que chega no `init_data` pode pertencer a
# uma pessoa cujo personagem vive noutro `player_id` (o sintético que ela criou
# pelo Google). Sem esta resolução, ela abria o jogo no Telegram e via um
# personagem VAZIO ao lado do dela — que é exactamente o que o vínculo existe
# para impedir.
#
# ⚠️ RAIO DE EXPLOSÃO, e por que isto é seguro para os 248: depois do backfill
# cada identidade `telegram:<id>` aponta para o PRÓPRIO `<id>`, portanto a
# resolução devolve o mesmo número que entrou — byte-idêntico. E se a linha
# não existir (backfill por correr, plano de controlo em baixo, qualquer erro)
# devolve-se o id cru. Só um vínculo EXPLÍCITO muda alguma coisa.
_identity_cache: dict[tuple[str, str], tuple[int, float]] = {}
_IDENTITY_TTL = 60.0


def invalidate_identity_cache(provider: str | None = None,
                              provider_uid: str | None = None) -> None:
    """Esquecer o que foi resolvido. O resgate de um código TEM de chamar
    isto, senão a pessoa continua a ver o personagem antigo até o TTL passar."""
    if provider is None:
        _identity_cache.clear()
    else:
        _identity_cache.pop((provider, str(provider_uid)), None)


async def resolve_identity_player_id(provider: str, provider_uid: str,
                                     default: int) -> int:
    """O `player_id` desta credencial. `default` sempre que houver dúvida.

    Cache curto porque isto entra no caminho QUENTE (uma resolução por
    pedido do mini-app). Nunca levanta: um erro aqui viraria 401 em massa
    ou, pior, um jogador a ver o personagem de outra pessoa."""
    import time as _t
    key = (provider, str(provider_uid))
    now = _t.monotonic()
    hit = _identity_cache.get(key)
    if hit is not None and (now - hit[1]) < _IDENTITY_TTL:
        return hit[0]
    sm = _ensure_control_engine()
    if sm is None:
        return default
    try:
        async with sm() as session:
            row = (await session.execute(text(
                "SELECT player_id FROM auth_identities "
                "WHERE provider = :p AND provider_uid = :u"
            ), {"p": provider, "u": str(provider_uid)})).first()
        resolved = int(row[0]) if row else int(default)
    except Exception:
        logger.warning("resolve_identity_player_id falhou %s:%s — a usar o id cru",
                       provider, provider_uid, exc_info=True)
        return default
    if len(_identity_cache) > 5000:
        _identity_cache.clear()
    _identity_cache[key] = (resolved, now)
    return resolved


# ── WEB-B Fase 2 — o id sintético ────────────────────────────────────────────
#: A base do espaço negativo. O 1º jogador web é `-1.000.000.001`: legível à
#: vista (negativo, ordem de 1e9) e longe do intervalo dos ids de grupo do
#: Telegram, que também são negativos — embora o guarda do `_safe_send` já
#: torne essa colisão inofensiva.
SYNTHETIC_ID_BASE = 1_000_000_000


async def allocate_synthetic_player_id() -> int | None:
    """Um `telegram_id` NEGATIVO, único entre mundos e nunca reutilizado.

    Devolve `None` se o plano de controlo estiver em baixo — e quem chama TEM
    de tratar isso como "não dá para criar conta agora", nunca inventar um id
    por sua conta. Um id inventado é um personagem que colide com outro daqui a
    seis meses, e nessa altura já não há como desfazer.
    """
    sm = _ensure_control_engine()
    if sm is None:
        return None
    try:
        async with sm() as session:
            n = (await session.execute(
                text("SELECT nextval('web_player_id_seq')"))).scalar_one()
            await session.commit()
        return -(SYNTHETIC_ID_BASE + int(n))
    except Exception:
        logger.warning("allocate_synthetic_player_id falhou", exc_info=True)
        return None


# ── WEB-B Fase 1 — o backfill das identidades ────────────────────────────────
async def backfill_telegram_identities() -> int:
    """Liga cada personagem existente à sua identidade `telegram`. Idempotente.

    Corre em TODO o boot (o `ON CONFLICT DO NOTHING` faz da segunda corrida um
    no-op) e varre TODOS os mundos registados — porque a identidade é da PESSOA
    e os personagens são por mundo. As 15 pessoas que têm personagem em `main` e
    em `s2` produzem UMA linha só: o `UNIQUE (provider, provider_uid)` é o que
    torna "duas caras, uma pessoa" verdade no esquema, e não só na prosa.

    Devolve o nº de linhas inseridas nesta corrida (0 no estado estável).

    Best-effort: um mundo inalcançável é registado e saltado — nunca impede o
    boot (Lei §1). Sem isto, os 248 teriam de "criar conta" para entrar na web;
    com isto, entram sem fazer nada.
    """
    sm = _ensure_control_engine()
    if sm is None:
        return 0

    from database.db import get_session_factory, iter_world_keys, use_world

    ids: set[int] = set()
    for key in iter_world_keys():
        try:
            with use_world(key):
                async with get_session_factory()() as gs:
                    rows = (await gs.execute(text(
                        "SELECT telegram_id FROM players WHERE telegram_id > 0"
                    ))).scalars().all()
            ids.update(int(r) for r in rows if r)
        except Exception:
            logger.warning("backfill de identidades: mundo %r inalcançável — saltado",
                           key, exc_info=True)

    if not ids:
        return 0

    inserted = 0
    try:
        async with sm() as session:
            # Um INSERT com VALUES em lote: 248 linhas cabem folgadamente numa
            # ida, e o `RETURNING` diz exactamente quantas eram novas — que é o
            # número que o teste da idempotência mede (2ª corrida ⇒ 0).
            ordered = sorted(ids)
            # ⚠️ BUG DE PRODUCAO (medido nos logs 2026-08-26, falhava desde a F1):
            # a versao anterior reusava O MESMO parametro nas duas colunas —
            # `(:p0, 'telegram', (:p0)::text)`. O Postgres tem de deduzir UM tipo
            # por parametro e via `$1` usado como BIGINT e como TEXT ao mesmo
            # tempo: `AmbiguousParameterError: inconsistent types deduced for
            # parameter $1 — text versus bigint`. O INSERT inteiro rebentava, o
            # try/except engolia, e as 248 identidades NUNCA foram criadas.
            # Dois parametros distintos por linha tornam a deducao trivial.
            params = {}
            for i, v in enumerate(ordered):
                params[f"p{i}"] = int(v)     # BIGINT — player_id
                params[f"u{i}"] = str(v)     # TEXT   — provider_uid
            values = ", ".join(f"(:p{i}, 'telegram', :u{i})" for i in range(len(ordered)))
            res = await session.execute(text(
                "INSERT INTO auth_identities (player_id, provider, provider_uid) "
                f"VALUES {values} "
                "ON CONFLICT (provider, provider_uid) DO NOTHING RETURNING id"
            ), params)
            inserted = len(res.scalars().all())
            await session.commit()
    except Exception:
        logger.warning("backfill de identidades falhou — a web fica sem os legados "
                       "até ao próximo boot (o login liga a identidade na mesma)",
                       exc_info=True)
        return 0

    if inserted:
        logger.info("✅ auth_identities: %d identidade(s) `telegram` ligada(s) "
                    "(%d personagens em %d mundos)", inserted, len(ids), len(list(iter_world_keys())))
    return inserted
