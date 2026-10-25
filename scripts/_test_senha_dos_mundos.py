# -*- coding: utf-8 -*-
"""一 A SENHA DOS MUNDOS TEM UM DONO — o env (2026-10-24) — suite COMMITTED.

    python -X utf8 scripts/_test_senha_dos_mundos.py

Medido na produção (só leitura, Open Source F5): as duas linhas do registo de
mundos (`servers.db_url`, `main` e `s2`) guardavam o `DATABASE_URL` inteiro — o
utilizador e a senha do superuser — numa tabela que qualquer leitura da base lê.
Dois donos da mesma senha: trocar a do env deixava o s2 a entrar com a antiga.

Cobre, pela CHAMADA (nunca pelo texto do código):
  1. `strip_credentials` / `with_env_credentials` — o endereço sem login, e o
     login que volta do env; uma linha com OUTRO login fica como estava
  2. o motor de um mundo: a linha sem login liga com o login do env
  3. o arranque escreve a linha do `main` SEM senha
  4. `strip_registry_credentials` limpa só o que o env devolve igual, e o
     `init_db` corre-o num passo próprio (a falha dele não leva o registo)
  5. o aprovisionamento guarda o endereço; o `CREATE DATABASE` liga com o login

Sem base de dados: as ligações são falsas e os motores nunca ligam.
"""
from __future__ import annotations

import asyncio
import os
import sys
import types
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── stub do telegram ANTES de qualquer core.* (convenção da casa) ────────────
if "telegram" not in sys.modules:
    _tg = types.ModuleType("telegram")
    _tg.Update = object
    _err = types.ModuleType("telegram.error")

    class _TgErr(Exception):
        retry_after = 0

    _err.RetryAfter = _err.TimedOut = _err.NetworkError = _err.BadRequest = _TgErr
    _tg.error = _err
    sys.modules["telegram"] = _tg
    sys.modules["telegram.error"] = _err
# o aprovisionamento avisa o agendador no fim; o verdadeiro puxa o telegram inteiro
if "core.scheduler" not in sys.modules:
    _agenda = types.ModuleType("core.scheduler")
    _agenda.reset_world_degraded_state = lambda key: None
    sys.modules["core.scheduler"] = _agenda

import database.control_db as CDB  # noqa: E402
import database.db as DB  # noqa: E402
import core.world_provision as WP  # noqa: E402

PASS = 0
FAIL: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {detail}")
        print(f"  FAIL: {name} {detail}")


# ⚠️ Os logins de mentira montam-se aos pedaços: escritos inteiros, a guarda da
# cópia pública apanhá-los-ia como segredo (e com razão).
def _dsn(esquema: str, login: str, endereco: str) -> str:
    return f"{esquema}://{login}@{endereco}"


# O env de mentira — uma senha com `@` codificado, como as reais podem ter.
ENV = _dsn("postgresql+asyncpg", "jogo:s3nh%40forte", "db.exemplo.invalid:5432/nivrael")
OUTRO = _dsn("postgresql", "outro:x", "noutro.exemplo.invalid:6543/mundo_longe")
VELHA = _dsn("postgresql+asyncpg", "postgres:velha", "db.exemplo.invalid:5432/nivrael_s2")
CDB.DATABASE_URL = ENV
WP.DATABASE_URL = ENV

# ── 1. as duas funções ───────────────────────────────────────────────────────
s, w = CDB.strip_credentials, CDB.with_env_credentials
check("1/tira o login", s(ENV) == "postgresql+asyncpg://db.exemplo.invalid:5432/nivrael", s(ENV))
check("1/tira o login de um DSN simples", s("postgresql://u:p@h/db") == "postgresql://h/db")
check("1/sem login fica igual", s("postgresql://h:5432/db") == "postgresql://h:5432/db")
check("1/vazio fica vazio", s("") == "" and s(None) == "")
check("1/idempotente", s(s(ENV)) == s(ENV))
check("1/a query sobrevive", s("postgresql://u:p@h/db?sslmode=require") == "postgresql://h/db?sslmode=require")
check("1/o login volta do env", w(s(ENV)) == ENV, w(s(ENV)))
check("1/o login do env vai para OUTRA base do mesmo servidor",
      w("postgresql://db.exemplo.invalid:5432/nivrael_s2")
      == _dsn("postgresql", "jogo:s3nh%40forte", "db.exemplo.invalid:5432/nivrael_s2"))
check("1/uma linha com o seu login fica como foi escrita (beta)", w(OUTRO) == OUTRO)
check("1/uma linha com a senha antiga fica como foi escrita", w(VELHA) == VELHA)
check("1/vazio não inventa nada", w("") == "")
check("1/o login do env NUNCA vai para outro servidor",
      w("postgresql://outro-servidor.exemplo.invalid:5432/nivrael_s2")
      == "postgresql://outro-servidor.exemplo.invalid:5432/nivrael_s2")
check("1/…nem para outra porta do mesmo host",
      w("postgresql://db.exemplo.invalid:6543/nivrael_s2") == "postgresql://db.exemplo.invalid:6543/nivrael_s2")
check("1/a porta por omissão (5432) é a mesma porta",
      w("postgresql://db.exemplo.invalid/nivrael_s2")
      == _dsn("postgresql", "jogo:s3nh%40forte", "db.exemplo.invalid/nivrael_s2"))
_env_antigo = CDB.DATABASE_URL
CDB.DATABASE_URL = "postgresql://db.exemplo.invalid/nivrael"   # um env sem login
check("1/env sem login: a linha fica sem login (não inventa)",
      w("postgresql://h/db") == "postgresql://h/db")
CDB.DATABASE_URL = _env_antigo

# ── 2. o motor de um mundo ───────────────────────────────────────────────────
def _motor(row):
    """O motor, ou a razão de não haver motor — um DSN partido é vermelho, nunca rebentar."""
    try:
        return DB._build_world_engine(row), ""
    except Exception as exc:
        return None, f"rebentou: {type(exc).__name__}: {str(exc)[:80]}"


eng, porque = _motor({"key": "s2", "db_url": "postgresql://db.exemplo.invalid:5432/nivrael_s2"})
check("2/a linha sem login liga com o utilizador do env", eng and eng.url.username == "jogo",
      porque or str(eng.url.username))
check("2/…e com a senha do env", eng and eng.url.password == "s3nh@forte")
check("2/…na base da linha", eng and eng.url.database == "nivrael_s2")
check("2/…pelo driver do jogo", eng and eng.url.drivername == "postgresql+asyncpg")
eng2, porque = _motor({"key": "longe", "db_url": OUTRO})
check("2/a linha com outro login liga com ELE", eng2 and eng2.url.username == "outro" and eng2.url.port == 6543,
      porque)
try:
    DB._build_world_engine({"key": "x", "db_url": ""})
    check("2/linha vazia continua a recusar", False, "não levantou")
except RuntimeError:
    check("2/linha vazia continua a recusar", True)


# ── uma ligação falsa: guarda o SQL e devolve as linhas que lhe dermos ───────
class _Res:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)


class _Conn:
    def __init__(self, linhas):
        self.linhas = linhas
        self.sql: list[tuple[str, dict]] = []

    async def execute(self, q, p=None):
        q = str(q)
        self.sql.append((q, dict(p or {})))
        if q.strip().upper().startswith("SELECT KEY, DB_URL FROM SERVERS"):
            return _Res(self.linhas)
        return _Res([])


class _Begin:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *a):
        return False


class _Eng:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return _Begin(self.conn)


def _com_engine(conn):
    CDB._ensure_control_engine = lambda: object()
    CDB._control_engine = _Eng(conn)


# ── 3. a linha do main ───────────────────────────────────────────────────────
c3 = _Conn([])
_com_engine(c3)
asyncio.run(CDB.bootstrap_control_db())
_ins = [p for q, p in c3.sql if "INSERT INTO servers" in q]
check("3/o arranque escreve a linha do main", len(_ins) == 1, str(len(_ins)))
check("3/…sem utilizador nem senha", _ins and "@" not in _ins[0]["db_url"], _ins and _ins[0]["db_url"])
check("3/…mas com o endereço do env", _ins and _ins[0]["db_url"] == s(ENV))

# ── 4. a limpeza do registo ──────────────────────────────────────────────────
linhas = [
    ("main", ENV),                                                                  # ainda com senha
    ("s2", _dsn("postgresql", "jogo:s3nh%40forte", "db.exemplo.invalid:5432/nivrael_s2")),  # a cópia do env
    ("longe", OUTRO),                                                               # outro login
    ("limpo", "postgresql://db.exemplo.invalid:5432/nivrael_limpo"),               # já limpo
    ("velha", _dsn("postgresql", "postgres:velha", "db.exemplo.invalid:5432/nivrael_v")),  # senha que o env já não tem
]
c4 = _Conn(linhas)
_com_engine(c4)
n = asyncio.run(CDB.strip_registry_credentials())
upd = {p["k"]: p["u"] for q, p in c4.sql if q.startswith("UPDATE servers")}
check("4/limpa as duas linhas que copiavam o env", n == 2 and set(upd) == {"main", "s2"}, f"{n} {sorted(upd)}")
check("4/…e cada uma volta a ligar ao MESMO DSN", all(w(u) == dict(linhas)[k] for k, u in upd.items()))
check("4/…sem senha nenhuma na tabela", all("@" not in u for u in upd.values()))
check("4/uma linha com outro login não é tocada", "longe" not in upd)
check("4/uma linha com uma senha que o env já não tem não é tocada", "velha" not in upd)
c4b = _Conn([(k, upd.get(k, u)) for k, u in linhas])
_com_engine(c4b)
check("4/a segunda passagem não muda nada", asyncio.run(CDB.strip_registry_credentials()) == 0)

# o init_db corre a limpeza num passo PRÓPRIO: a falha dela não leva o registo
_ordem: list[str] = []
_orig = (CDB.bootstrap_control_db, CDB.strip_registry_credentials, DB.load_world_registry, DB.init_world_db)


async def _boot():
    _ordem.append("bootstrap")


async def _limpa_que_falha():
    _ordem.append("limpeza")
    raise RuntimeError("a limpeza rebentou")


async def _registo():
    _ordem.append("registo")


class _Para(Exception):
    pass


async def _main(key):
    _ordem.append("main")
    raise _Para()


CDB.bootstrap_control_db, CDB.strip_registry_credentials = _boot, _limpa_que_falha
DB.load_world_registry, DB.init_world_db = _registo, _main
try:
    asyncio.run(DB.init_db())
except _Para:
    pass
except Exception as exc:  # a falha da limpeza escapou do init_db: vermelho, nunca rebentar
    _ordem.append("rebentou: " + type(exc).__name__)
finally:
    CDB.bootstrap_control_db, CDB.strip_registry_credentials, DB.load_world_registry, DB.init_world_db = _orig
check("4/o init_db limpa DEPOIS do arranque e ANTES de ler o registo",
      _ordem[:3] == ["bootstrap", "limpeza", "registo"], str(_ordem))
check("4/…e a falha da limpeza não impede o registo nem o main", _ordem == ["bootstrap", "limpeza", "registo", "main"],
      str(_ordem))

# ── 5. o aprovisionamento ────────────────────────────────────────────────────
_insert: list[dict] = []
_criada: list[str] = []
_registo_row: list[dict] = []


class _Sessao:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, q, p=None):
        if "INSERT INTO servers" in str(q):
            _insert.append(dict(p or {}))

        class _R:
            def first(self_inner):
                return ("CODIGO",)
        return _R()

    async def commit(self):
        return None


async def _cria(url):
    _criada.append(url)
    return True


async def _init(key):
    return None


@contextmanager
def _no_mundo(key):
    yield


def _registar(row):
    _registo_row.append(dict(row))


_prov_orig = (CDB.get_control_session_factory, CDB.control_enabled, WP.create_database_if_missing,
              DB.init_world_db, DB.register_world, DB.use_world, DB.get_session_factory)
CDB.get_control_session_factory = lambda: (lambda: _Sessao())
CDB.control_enabled = lambda: True
WP.create_database_if_missing = _cria
DB.init_world_db, DB.register_world, DB.use_world = _init, _registar, _no_mundo
DB.get_session_factory = lambda: (lambda: _Sessao())
try:
    res = asyncio.run(WP.provision_world("novo", "Mundo Novo", gen_code=False))
    check("5/o registo guarda o endereço SEM login", _insert and "@" not in _insert[-1]["db_url"],
          _insert and _insert[-1]["db_url"])
    check("5/…da base certa", _insert and _insert[-1]["db_url"].endswith("/nivrael_novo"))
    check("5/o CREATE DATABASE liga COM o login do env",
          _criada and "jogo:s3nh%40forte@" in _criada[-1], _criada and s(_criada[-1]))
    check("5/a linha em memória volta a ligar pelo env",
          _registo_row and w(_registo_row[-1]["db_url"]) == _criada[-1])
    check("5/o resumo não leva a senha", "@" not in res["db_url"])
    _insert.clear()
    asyncio.run(WP.provision_world("longe", "Mundo Longe", db_url=OUTRO, gen_code=False, create_db=False))
    check("5/um db_url com OUTRO login fica guardado como foi dado", _insert and _insert[-1]["db_url"] == OUTRO)
finally:
    (CDB.get_control_session_factory, CDB.control_enabled, WP.create_database_if_missing,
     DB.init_world_db, DB.register_world, DB.use_world, DB.get_session_factory) = _prov_orig

print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)
print(f"OK — {PASS} asserts. A senha dos mundos vive só no env: o registo guarda o endereço, "
      "e quem liga pede o login a um dono só.")
