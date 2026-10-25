# -*- coding: utf-8 -*-
"""文 THE DOCUMENTATION TELLS THE TRUTH — the guard of every public page.

Why it exists (community edition, F2 — 2026-10-22)
--------------------------------------------------
Documentation rots in silence: a function is renamed, a migration is added, a
route moves, and the page that explained it keeps explaining something that no
longer exists. Nobody notices until a newcomer follows it and gets lost. This
guard reads every public Markdown page and checks it against the code of THIS
checkout — never against a promise:

  1. LINKS     every relative link opens a file that exists; a `#anchor` into a
               Markdown page names a heading that exists.
  2. PATHS     every repository path written in code style (`core/cultivator_soul.py`,
               `migrations/`, `miniapp/i18n/{pt,en,es}.json`) exists.
  3. SYMBOLS   every `function()` written in code style is defined in the code;
               every `UPPER_CASE` name is defined in the code or documented in
               `.env.example`; every `Model.column` names a real ORM column.
  4. ROUTES    every web path written in code style (`/login`, `/api/...`) is a
               route of the real application (`create_app()`), not a guess.
  5. NUMBERS   every number in the prose is MEASURED: it carries a fact marker
               whose value this guard computes from the code, or it is one of the
               few declared CONVENTIONS (a licence version, the two screen sizes
               of the house). A bare number fails.
  6. COVERAGE  every module of `core/`, `handlers/` and `community/` is named by
               some page in `docs/`, and every per-world feature flag appears in
               `docs/architecture.md`. A new engine without a page fails.

How to write a number
---------------------
Put the marker right after it (after the closing `**` if it is bold):

    **40**<!--#flags--> flags      renders as "40 flags", and fails the day the code has 41
    140+<!--#migrations-->         "at least 140" — stays true when migrations are added
    eleven<!--#realms--> realms    number words work too (en / pt / es, up to one hundred)

A fact is either a name in FACTS below (a count measured from the code), or one
of three generic forms that read the code directly:

    4<!--#env:TRAVEL_COOLDOWN_HOURS-->           the default of an environment knob
    6<!--#env:ENV_COOLDOWN_SECONDS/3600-->       … converted (÷ 3600: seconds → hours; `*` multiplies, `*-1` turns a cost positive)
    15%<!--#env:LGC_ART_CHANCE-->                a percentage is compared with a fraction (0.15)
    1,000<!--#val:core/anel.py:RING_MAX_SLOTS[5]-->   a literal in a file (with a key)
    5<!--#len:core/continent_engine.py:CONTINENT_KEYS-->   the length of a literal

A count that no generic form can reach is added to FACTS, measured from the code
— never typed in. Numbers inside code (`inline` or fenced) are not prose and are
not checked; write a claim as prose. Number WORDS are checked only when marked.

Not checked for numbers, with the reason: `CHANGELOG.md` (a released version is
history — its numbers must NOT follow the code) and `NOTICE.md` (legal text:
section numbers and the copyright year). Their links and paths are checked.
`CODE_OF_CONDUCT.md` is the verbatim Contributor Covenant and is not read.

Before reading the real pages the guard runs its own SELF-TEST on a page it
writes in memory, with one defect of each kind: if it fails to see any of them,
it fails — a guard that stays green on everything guards nothing.

Usage:  python scripts/_verifica_documentacao.py
        python scripts/_verifica_documentacao.py --facts   # every fact and its value
"""
from __future__ import annotations

import ast
import glob
import io
import json
import os
import re
import subprocess
import sys
import textwrap
import warnings

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── what is read ─────────────────────────────────────────────────────────────
NOT_READ = {"CODE_OF_CONDUCT.md"}                 # the verbatim Covenant
NUMBERS_EXEMPT = {"CHANGELOG.md", "NOTICE.md"}    # history and legal text (see above)
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv", "venv", ".nivrael",
             ".pytest_cache"}
# Paths that only exist after a build or on one machine: never required to exist.
GENERATED = ("node_modules", "dist", ".nivrael", "__pycache__")
LOCAL_ONLY = {".env"}


def pages(root: str = ROOT) -> list[str]:
    """The public documentation: the Markdown at the root and everything in docs/."""
    out = [n for n in os.listdir(root) if n.endswith(".md") and n not in NOT_READ
           and os.path.isfile(os.path.join(root, n))]
    for p in glob.glob(os.path.join(root, "docs", "**", "*.md"), recursive=True):
        out.append(os.path.relpath(p, root).replace(os.sep, "/"))
    return sorted(out)


def _src(rel: str) -> str:
    return io.open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8").read()


# ═════════════════════════════════════════════════════════════════════════════
# FACTS — every number a page may state, measured from the code of this checkout
# ═════════════════════════════════════════════════════════════════════════════
_ARITH = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
          ast.Div: lambda a, b: a / b, ast.FloorDiv: lambda a, b: a // b, ast.Pow: lambda a, b: a ** b}


def _eval_literal(node, nomes: dict | None = None):
    """A literal, evaluated safely: constants, containers, signs, arithmetic
    between numbers (`5 * 60`), `float("inf")` / `int("3")`, and the names of
    literals assigned earlier in the same file (`(STATE_A, STATE_B)`). Nothing runs."""
    nomes = nomes or {}
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in nomes:
        return nomes[node.id]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        valores = [_eval_literal(e, nomes) for e in node.elts]
        return valores if isinstance(node, ast.List) else (
            tuple(valores) if isinstance(node, ast.Tuple) else set(valores))
    if isinstance(node, ast.Dict) and None not in node.keys:
        return {_eval_literal(k, nomes): _eval_literal(v, nomes) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval_literal(node.operand, nomes)
        if isinstance(v, (int, float)):
            return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and type(node.op) in _ARITH:
        a, b = _eval_literal(node.left, nomes), _eval_literal(node.right, nomes)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return _ARITH[type(node.op)](a, b)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("float", "int") \
            and len(node.args) == 1 and not node.keywords and isinstance(node.args[0], ast.Constant):
        return {"float": float, "int": int}[node.func.id](node.args[0].value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in ("frozenset", "set", "tuple", "list") and len(node.args) == 1 and not node.keywords:
        return {"frozenset": frozenset, "set": set, "tuple": tuple, "list": list}[node.func.id](
            _eval_literal(node.args[0], nomes))
    raise ValueError("not a literal")


def _literal(rel: str, name: str):
    """The literal assigned to `name` at the top level of a Python file."""
    vistos: dict = {}
    for node in ast.parse(_src(rel)).body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        alvos = [t.id for t in targets if isinstance(t, ast.Name)]
        if not alvos or node.value is None:
            continue
        if name in alvos:
            return _eval_literal(node.value, vistos)
        try:
            valor = _eval_literal(node.value, vistos)
        except (ValueError, TypeError, KeyError, ZeroDivisionError):
            continue
        for a in alvos:
            vistos[a] = valor
    raise KeyError(f"{name} is not assigned in {rel}")


def _env_default(rel: str, var: str) -> str:
    """The default of `os.getenv("VAR", "default")` in a Python file."""
    m = re.search(r"""os\.getenv\(\s*["']%s["']\s*,\s*["']([^"']*)["']""" % re.escape(var), _src(rel))
    if not m:
        raise KeyError(f"os.getenv({var!r}, …) with a default is not in {rel}")
    return m.group(1)


def _files(pattern: str) -> list[str]:
    return sorted(glob.glob(os.path.join(ROOT, *pattern.split("/"))))


def _json_keys(rel: str) -> int:
    return len(json.loads(_src(rel)))


def _models() -> dict[str, set[str]]:
    """ORM class name → the attribute names declared in its body (database/models.py)."""
    out = {}
    for node in ast.walk(ast.parse(_src("database/models.py"))):
        if not isinstance(node, ast.ClassDef):
            continue
        attrs = set()
        for s in node.body:
            for t in (s.targets if isinstance(s, ast.Assign) else
                      [s.target] if isinstance(s, ast.AnnAssign) else []):
                if isinstance(t, ast.Name):
                    attrs.add(t.id)
        if "__tablename__" in attrs:
            out[node.name] = attrs
    return out


_APP_ROUTES: list[str] | None = None
_APP = r"""
import json, os, sys
sys.path.insert(0, os.getcwd())
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
from core.webserver import create_app
from community import dev_login
app = create_app()
dev_login.install(app)
rotas = {r.resource.canonical for r in app.router.routes() if r.resource is not None}
rotas |= set(dev_login.LOGIN_PATHS) | {dev_login.POST_PATH}
print("@@" + json.dumps(sorted(rotas)))
"""


def _clean_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("NIVRAEL_", "FIREBASE_", "WEBHOOK_", "BOT_TOKEN", "DATABASE_URL"))}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_app(codigo: str, entrada: str = "") -> object:
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", codigo], cwd=ROOT, env=_clean_env(),
                       input=entrada, capture_output=True, text=True, encoding="utf-8", errors="replace")
    linhas = [l for l in r.stdout.splitlines() if l.startswith("@@")]
    if r.returncode != 0 or not linhas:
        raise RuntimeError("could not build the app to read its routes:\n" + (r.stderr or r.stdout)[-1500:])
    return json.loads(linhas[-1][2:])


def app_routes() -> list[str]:
    """The route table of the real application, built in a clean process."""
    global _APP_ROUTES
    if _APP_ROUTES is None:
        _APP_ROUTES = _run_app(_APP)
        # the Telegram webhook is mounted by main.py, outside create_app()
        _APP_ROUTES.append(_env_default("config.py", "WEBHOOK_PATH"))
    return _APP_ROUTES


# Whether a path is served is asked to the ROUTER's own resources
# (`resource.resolve`), never guessed from the route strings: the website's
# catch-all `/{name}` only takes files with an image/manifest extension, and a
# string comparison would let any one-segment path through. A path exists when a
# resource matches it for some method other than OPTIONS — the CORS preflight
# `OPTIONS /api/miniapp/{tail:.*}` matches every path under the API and proves
# nothing (it let `/api/miniapp/<anything>` through until the sabotage caught it).
_RESOLVE = r"""
import asyncio, json, os, sys
sys.path.insert(0, os.getcwd())
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
from aiohttp.test_utils import make_mocked_request
from core.webserver import create_app
from community import dev_login
app = create_app()
dev_login.install(app)
canon = sorted({r.resource.canonical for r in app.router.routes() if r.resource is not None})
pedido = json.loads(sys.stdin.read())
extra = set(dev_login.LOGIN_PATHS) | {dev_login.POST_PATH} | set(pedido["extra"])
async def go(paths):
    out = {}
    for p in paths:
        if p in extra:
            out[p] = True
        elif p.endswith("*") or (p.endswith("/") and p not in canon):
            pre = p.rstrip("*")
            out[p] = any(c.startswith(pre) and c != pre for c in canon)
        else:
            req = make_mocked_request("GET", p, app=app)
            out[p] = False
            for res in app.router.resources():
                casou, metodos = await res.resolve(req)
                metodos = set(metodos) | ({"GET"} if casou is not None else set())
                if (casou is not None or metodos) and metodos - {"OPTIONS"}:
                    out[p] = True
                    break
    return out
print("@@" + json.dumps(asyncio.run(go(pedido["paths"]))))
"""


def resolve_routes(paths: list[str]) -> dict[str, bool]:
    """{path: is it served?} for every path, in one clean process."""
    unicos = sorted(set(paths))
    if not unicos:
        return {}
    # the Telegram webhook is mounted by main.py, outside create_app()
    pedido = {"paths": unicos, "extra": [_env_default("config.py", "WEBHOOK_PATH")]}
    return _run_app(_RESOLVE, json.dumps(pedido))


def _scheduler_jobs() -> int:
    src = _src("core/scheduler.py")
    corpo = src[src.index("def init_scheduler("):]
    corpo = corpo[:re.search(r"\n(?:async )?def |\nclass ", corpo[1:]).start() + 1]
    return len(set(re.findall(r"""\bid\s*=\s*["']([\w-]+)["']""", corpo)))


def chat_commands() -> set[str]:
    """The command names main.py registers (`/start`, `/cultivar`, …)."""
    nomes = set()
    for m in re.finditer(r"CommandHandler\(\s*(\[[^\]]*\]|\([^)]*\)|[\"'][\w]+[\"'])", _src("main.py")):
        nomes.update(re.findall(r"[\"']([\w]+)[\"']", m.group(1)))
    return nomes


def _modules(folder: str) -> list[str]:
    return [os.path.relpath(p, ROOT).replace(os.sep, "/") for p in _files(folder + "/*.py")
            if not p.endswith("__init__.py")]


def _dockerfile_from(image: str) -> str:
    m = re.search(r"^FROM\s+%s:([\d.]+)" % re.escape(image), _src("Dockerfile"), re.M)
    if not m:
        raise KeyError(f"no `FROM {image}:<version>` in the Dockerfile")
    return m.group(1)


def _compose(rx: str) -> str:
    m = re.search(rx, _src("docker-compose.yml"), re.M)
    if not m:
        raise KeyError(f"{rx!r} not in docker-compose.yml")
    return m.group(1)


FACTS: dict[str, tuple[str, object]] = {
    # the cultivator
    "realms": ("REALM_NAMES in config.py", lambda: len(_literal("config.py", "REALM_NAMES"))),
    "sub_layers": ("SUB_LAYERS_PER_REALM default in config.py",
                   lambda: int(_env_default("config.py", "SUB_LAYERS_PER_REALM"))),
    "spirit_roots": ("SPIRIT_ROOTS in config.py", lambda: len(_literal("config.py", "SPIRIT_ROOTS"))),
    "meditation_types": ("MEDITATION_TYPES in config.py",
                         lambda: len(_literal("config.py", "MEDITATION_TYPES"))),
    "guild_war_hour": ("the hour of the sect_war cron job in core/scheduler.py (the one that decides)",
                       lambda: int(re.search(r"sect_war_job,\s*\"cron\",\s*day_of_week=\"\w+\",\s*hour=(\d+)",
                                             _src("core/scheduler.py")).group(1))),
    "body_gate_level": ("the `bt_level < N` gate before Mahayana in core/game_logic.py",
                        lambda: int(re.search(r"if bt_level < (\d+):", _src("core/game_logic.py")).group(1))),
    "dao_laws": ("len(PATHS) × LAWS_PER_PATH in database/seeds/dao_3000_seeds.py",
                 lambda: len(_literal("database/seeds/dao_3000_seeds.py", "PATHS"))
                 * _literal("database/seeds/dao_3000_seeds.py", "LAWS_PER_PATH")),
    "heavenly_laws": ("len(HEAVENLY_PATHS) × LAWS_PER_HEAVENLY_PATH in database/seeds/heavenly_laws_seeds.py",
                      lambda: len(_literal("database/seeds/heavenly_laws_seeds.py", "HEAVENLY_PATHS"))
                      * _literal("database/seeds/heavenly_laws_seeds.py", "LAWS_PER_HEAVENLY_PATH")),
    # the worlds
    "flags": ("DEFAULT_WORLD_FEATURES in database/db.py",
              lambda: len(_literal("database/db.py", "DEFAULT_WORLD_FEATURES"))),
    "balance_knobs": ("DEFAULT_WORLD_BALANCE in database/db.py",
                      lambda: len(_literal("database/db.py", "DEFAULT_WORLD_BALANCE"))),
    "live_balance_knobs": ("LIVE_BALANCE_KEYS in database/db.py",
                           lambda: len(_literal("database/db.py", "LIVE_BALANCE_KEYS"))),
    # the data
    "migrations": ("SQL files in migrations/", lambda: len(_files("migrations/*.sql"))),
    "last_migration": ("the highest number prefix in migrations/",
                       lambda: max(int(re.match(r"(\d+)", os.path.basename(p)).group(1))
                                   for p in _files("migrations/*.sql"))),
    "orm_models": ("classes with __tablename__ in database/models.py", lambda: len(_models())),
    "seed_modules": ("database/seeds/*_seeds.py", lambda: len(_files("database/seeds/*_seeds.py"))),
    "control_tables": ("CREATE TABLE IF NOT EXISTS in database/control_db.py",
                       lambda: len(re.findall(r"CREATE TABLE IF NOT EXISTS", _src("database/control_db.py")))),
    "community_modules": ("community/*.py without __init__", lambda: len(_modules("community"))),
    # the languages
    "languages": ("locales/*.json", lambda: len(_files("locales/*.json"))),
    "catalogs": ("locales/*.json + miniapp/i18n/*.json",
                 lambda: len(_files("locales/*.json")) + len(_files("miniapp/i18n/*.json"))),
    "chat_keys": ("keys in locales/pt.json", lambda: _json_keys("locales/pt.json")),
    "client_keys": ("keys in miniapp/i18n/pt.json", lambda: _json_keys("miniapp/i18n/pt.json")),
    # the code
    "core_modules": ("core/*.py without __init__", lambda: len(_modules("core"))),
    "handler_modules": ("handlers/*.py without __init__", lambda: len(_modules("handlers"))),
    "chat_commands": ("command names registered with CommandHandler in main.py", lambda: len(chat_commands())),
    "api_routes": ("routes under /api/ of create_app()",
                   lambda: sum(1 for r in app_routes() if r.startswith("/api/"))),
    "scheduler_jobs": ("job ids in init_scheduler (core/scheduler.py)", _scheduler_jobs),
    "game_suites": ("scripts/_test_*.py without the community edition suite",
                    lambda: len([p for p in _files("scripts/_test_*.py")
                                 if not p.endswith("_test_edicao_comunitaria.py")])),
    # the machine
    "python": ("FROM python:<v>-slim in the Dockerfile", lambda: _dockerfile_from("python")),
    "node": ("FROM node:<v>-slim in the Dockerfile", lambda: _dockerfile_from("node")),
    "postgres": ("image: postgres:<v> in docker-compose.yml", lambda: _compose(r"image:\s*postgres:(\d+)")),
    "port": ("the published port in docker-compose.yml",
             lambda: int(_compose(r"""["']127\.0\.0\.1:(\d+):\d+["']"""))),
    "main_web_port": ("start_webserver(<port>) in main.py",
                      lambda: int(re.search(r"start_webserver\((\d+)\)", _src("main.py")).group(1))),
    "guard_max_mb": ("LIMITE_BYTES in scripts/_verifica_copia_publica.py",
                     lambda: int(re.search(r"LIMITE_BYTES\s*=\s*(\d+)\s*\*\s*1024\s*\*\s*1024",
                                           _src("scripts/_verifica_copia_publica.py")).group(1))),
}

# Numbers that are NOT facts of the code — each with the reason it may stand.
CONVENTIONS: list[tuple[str, str]] = [
    (r"\b390×844\b|\b1440×900\b", "the two screen sizes every screen is looked at (a house rule)"),
    (r"\bAGPL-3\.0(?:-only|-or-later)?\b", "the name of a licence"),
    (r"\bCC BY-NC-SA 4\.0\b", "the name of a licence"),
    (r"\bContributor Covenant(?: version)? 2\.1\b", "the name of a standard"),
    (r"\bDCO 1\.1\b|\bVersion 1\.1\b", "the name of a standard"),
    (r"\bwithin \*\*7 days\*\*|\bwithin 7 days\b", "a promise of the maintainers (SECURITY.md), not a fact of the code"),
    (r"\*\*30 days\*\* ahead|\*\*30 dias\*\* de antecedência|\*\*30 días\*\* de antelación",
     "a promise of the official game's owner to its players (README, Project status), not a fact of the code"),
]

NUMBER_WORDS = {}
for _lingua in (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty",
    "zero um dois três quatro cinco seis sete oito nove dez onze doze treze catorze quinze "
    "dezasseis dezassete dezoito dezanove vinte",
    "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince "
    "dieciséis diecisiete dieciocho diecinueve veinte",
):
    for _i, _w in enumerate(_lingua.split()):
        NUMBER_WORDS.setdefault(_w, _i)
NUMBER_WORDS.update({"uma": 1, "duas": 2, "una": 1, "catorze": 14, "quatorze": 14, "dezesseis": 16,
                     "dezessete": 17, "dezenove": 19, "thirty": 30, "forty": 40, "fifty": 50,
                     "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
                     "trinta": 30, "quarenta": 40, "cinquenta": 50, "treinta": 30, "cuarenta": 40,
                     "cincuenta": 50, "cem": 100, "cien": 100})


_CODE_FILES: list[str] | None = None


def _code_files() -> list[str]:
    """The Python files that hold game knobs (the same set .env.example documents)."""
    global _CODE_FILES
    if _CODE_FILES is None:
        out = ["config.py", "main.py", "resource_monitor.py"]
        for pasta in ("core", "handlers", "database", "community"):
            for p in glob.glob(os.path.join(ROOT, pasta, "**", "*.py"), recursive=True):
                out.append(os.path.relpath(p, ROOT).replace(os.sep, "/"))
        _CODE_FILES = [f for f in out if os.path.isfile(os.path.join(ROOT, f))]
    return _CODE_FILES


def _env_any(var: str):
    """The default of an environment knob, wherever the code reads it — one value."""
    v = re.escape(var)
    padroes = (
        r"""os\.(?:getenv|environ\.get)\(\s*["']%s["']\s*,\s*["']([^"']*)["']""" % v,
        r"""_env_(?:int|float|str)\(\s*["']%s["']\s*,\s*([-\d.]+)""" % v,
    )
    vistos = set()
    for rel in _code_files():
        src = _src(rel)
        if var not in src:
            continue
        for rx in padroes:
            vistos.update(m.group(1) for m in re.finditer(rx, src))
    if not vistos:
        raise KeyError(f"no literal default for the knob {var} in the code")
    if len(vistos) > 1:
        raise KeyError(f"the knob {var} has {len(vistos)} different defaults in the code: {sorted(vistos)}")
    bruto = vistos.pop()
    try:
        return int(bruto)
    except ValueError:
        return float(bruto)


def _literal_at(rel: str, alvo: str):
    """`NAME` or `NAME[key][key]` — a literal in a Python file, with optional keys."""
    m = re.fullmatch(r"([A-Za-z_]\w*)((?:\[[^\]]+\])*)", alvo)
    if not m:
        raise KeyError(f"`{alvo}` is not NAME or NAME[key]")
    valor = _literal(rel, m.group(1))
    for chave in re.findall(r"\[([^\]]+)\]", m.group(2)):
        valor = valor[ast.literal_eval(chave)]
    return valor


def _fact_value(spec: str):
    """The measured value behind a marker: a FACTS name or a generic form, with an
    optional unit conversion (`/3600`, `*100`)."""
    m = re.fullmatch(r"(?P<base>.+?)(?:(?P<op>[/*])(?P<k>-?\d+(?:\.\d+)?))?", spec)
    base, op, k = m.group("base"), m.group("op"), m.group("k")
    if base in FACTS:
        fn = FACTS[base][1]
        valor = fn() if callable(fn) else fn
    elif base.startswith("env:"):
        valor = _env_any(base[4:])
    elif base.startswith(("val:", "len:")):
        rel, _, alvo = base[4:].rpartition(":")
        if not rel or not os.path.isfile(os.path.join(ROOT, *rel.split("/"))):
            raise KeyError(f"`{rel}` is not a file")
        valor = _literal_at(rel, alvo)
        if base.startswith("len:"):
            valor = len(valor)
    else:
        raise KeyError(spec)
    if op:
        valor = valor / float(k) if op == "/" else valor * float(k)
    return valor


def _fact_where(spec: str) -> str:
    base = re.sub(r"[/*]-?\d+(?:\.\d+)?$", "", spec)
    if base in FACTS:
        return FACTS[base][0]
    if base.startswith("env:"):
        return f"the default of {base[4:]} in the code"
    if base.startswith("val:"):
        return f"{base[4:].rpartition(':')[2]} in {base[4:].rpartition(':')[0]}"
    if base.startswith("len:"):
        return f"len({base[4:].rpartition(':')[2]}) in {base[4:].rpartition(':')[0]}"
    return spec


def _as_number(texto: str):
    """'4,787' → 4787 · '0.15' → 0.15 · 'eleven' → 11 · anything else → None."""
    t = texto.strip().lower()
    if t in NUMBER_WORDS:
        return NUMBER_WORDS[t]
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", t):
        return int(t.replace(",", ""))
    if re.fullmatch(r"\d+", t):
        return int(t)
    if re.fullmatch(r"\d+\.\d+", t):
        return float(t)
    return None


def _version(texto) -> tuple | None:
    t = str(texto).strip()
    return tuple(int(x) for x in t.split(".")) if re.fullmatch(r"\d+(?:\.\d+)*", t) else None


def _same(claim_text: str, pct: bool, measured, at_least: bool) -> bool:
    if isinstance(measured, str):                       # a version: "3.11", "20"
        a, b = _version(claim_text), _version(measured)
        if a is None or b is None:
            return False
        return b >= a if at_least else b == a
    claim = _as_number(claim_text)
    if claim is None or isinstance(measured, bool) or not isinstance(measured, (int, float)):
        return False
    if pct:
        claim = claim / 100.0
    if at_least:
        return measured >= claim - 1e-9
    return abs(measured - claim) <= 1e-9 * max(1.0, abs(claim))


# ═════════════════════════════════════════════════════════════════════════════
# READING A PAGE
# ═════════════════════════════════════════════════════════════════════════════
MARKER = re.compile(
    r"(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)*|[^\W\d_]+)(?P<pct>%?)(?P<plus>\+?)(?:\*\*|\*|_)?"
    r"<!--#(?P<fact>[^\s>]+?)-->")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s+\"[^\"]*\")?\s*$")
HTML_ATTR = re.compile(r"""<(?:img|a|source)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"']+)["']""", re.I)
NUMBER = re.compile(r"(?<![\w\-.#/])\d+(?:[.,]\d+)*")
# A name tied to a file in the prose: "`x()` in `core/a.py`", "`X` (`core/a.py`)".
SYMBOL_IN_FILE = re.compile(
    r"`(?P<sym>[A-Za-z_][\w.]*)(?P<call>\(\))?`\s+(?:(?:in|of|from)\s+|\(\s*)"
    r"`(?P<path>[\w./-]+\.(?:py|js|mjs))`")


def _strip_fences(texto: str) -> list[str]:
    """The page's lines with fenced code blocks blanked (line numbers survive)."""
    out, cerca = [], None
    for linha in texto.splitlines():
        m = re.match(r"^\s{0,3}(`{3,}|~{3,})", linha)
        if cerca:
            out.append("")
            if m and m.group(1)[0] == cerca[0] and len(m.group(1)) >= len(cerca):
                cerca = None
            continue
        if m:
            cerca = m.group(1)
            out.append("")
            continue
        out.append(linha)
    return out


def slug(titulo: str) -> str:
    """GitHub's anchor for a heading."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", titulo)
    t = re.sub(r"<[^>]+>", "", t).replace("`", "").replace("*", "").strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def anchors(texto: str) -> set[str]:
    vistos: dict[str, int] = {}
    out = set()
    for linha in _strip_fences(texto):
        m = re.match(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", linha)
        if not m:
            continue
        s = slug(m.group(1))
        n = vistos.get(s, 0)
        vistos[s] = n + 1
        out.add(s if n == 0 else f"{s}-{n}")
    for m in re.finditer(r"""<a\s+(?:name|id)=["']([^"']+)["']""", texto):
        out.add(m.group(1))
    return out


def code_spans(linhas: list[str]):
    for n, linha in enumerate(linhas, 1):
        for m in CODE_SPAN.finditer(linha):
            yield n, m.group(2).strip()


def _expand(token: str) -> list[str]:
    m = re.search(r"\{([^{}]*,[^{}]*)\}", token)
    if not m:
        return [token]
    return [x for alt in m.group(1).split(",")
            for x in _expand(token[:m.start()] + alt + token[m.end():])]


# ═════════════════════════════════════════════════════════════════════════════
# WHAT THE CODE DEFINES (read once)
# ═════════════════════════════════════════════════════════════════════════════
class Code:
    def __init__(self, root: str):
        self.root = root
        self.top = set(os.listdir(root))
        self.functions: set[str] = set()
        self.names: set[str] = set()
        warnings.simplefilter("ignore", SyntaxWarning)   # old escapes in some scripts — not ours to judge here
        for d, subs, nomes in os.walk(root):
            subs[:] = [s for s in subs if s not in SKIP_DIRS]
            for n in nomes:
                p = os.path.join(d, n)
                if n.endswith(".py"):
                    try:
                        tree = ast.parse(io.open(p, encoding="utf-8").read())
                    except (SyntaxError, UnicodeDecodeError):
                        continue
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            self.functions.add(node.name)
                        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                            ts = node.targets if isinstance(node, ast.Assign) else [node.target]
                            for t in ts:
                                if isinstance(t, ast.Name):
                                    self.names.add(t.id)
                elif n.endswith((".js", ".mjs")) and "/miniapp/" in "/" + os.path.relpath(p, root).replace(os.sep, "/") \
                        or n.endswith(".mjs"):
                    try:
                        js = io.open(p, encoding="utf-8").read()
                    except UnicodeDecodeError:
                        continue
                    self.functions.update(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", js))
                    for nome in re.findall(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=", js):
                        self.names.add(nome)
                        self.functions.add(nome)
        exemplo = os.path.join(root, ".env.example")
        self.env = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", io.open(exemplo, encoding="utf-8").read(), re.M)) \
            if os.path.isfile(exemplo) else set()
        try:
            self.models = _models()
        except Exception:
            self.models = {}

    def exists(self, rel: str) -> bool:
        rel = rel.rstrip("/")
        if any(ch in rel for ch in "*?["):
            return bool(glob.glob(os.path.join(self.root, *rel.split("/"))))
        return os.path.exists(os.path.join(self.root, *rel.split("/")))

    def defined_in(self, rel: str) -> set[str]:
        """Every name a file defines (functions, classes, assignments at any depth)."""
        cache = self.__dict__.setdefault("_por_ficheiro", {})
        if rel not in cache:
            nomes: set[str] = set()
            p = os.path.join(self.root, *rel.split("/"))
            try:
                src = io.open(p, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                src = ""
            if rel.endswith(".py") and src:
                try:
                    for node in ast.walk(ast.parse(src)):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            nomes.add(node.name)
                        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                            for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                                if isinstance(t, ast.Name):
                                    nomes.add(t.id)
                except SyntaxError:
                    pass
            elif src:
                nomes.update(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", src))
                nomes.update(re.findall(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=", src))
            cache[rel] = nomes
        return cache[rel]

    def is_path(self, token: str) -> bool:
        primeiro = token.split("/", 1)[0]
        return (("/" in token and primeiro in self.top) or token in self.top) \
            and not re.search(r"[<>]|://", token)

    def module_error(self, token: str) -> str | None:
        """`community.local`, `core.webserver.create_app`: the module exists, and
        what follows it is a name defined in the code. None = fine."""
        partes = token.split(".")
        for i in range(len(partes), 0, -1):
            base = os.path.join(self.root, *partes[:i])
            resto = partes[i:]
            if os.path.isfile(base + ".py"):
                if resto and resto[-1] not in self.functions | self.names:
                    return f"`{token}`: `{resto[-1]}` is not defined in {'/'.join(partes[:i])}.py"
                return None
            if os.path.isdir(base):
                # after a package comes a module (or nothing)
                return f"`{token}` is not a module of this repository" if resto else None
        return f"`{token}` is not a module of this repository"

    def is_module(self, token: str) -> bool:
        return bool(re.fullmatch(r"[a-z_]+(?:\.[A-Za-z_]\w*)+", token)) \
            and token.split(".", 1)[0] in {"core", "handlers", "database", "community", "scripts"}


# Code-style words that are not names of this code base, each with its reason.
KNOWN_WORDS = {
    "CREATEDB": "a PostgreSQL role attribute", "DROP": "SQL", "NULL": "SQL", "JSONB": "SQL",
    "DEFAULT": "SQL", "UTF-8": "an encoding", "GET": "HTTP", "POST": "HTTP",
}


# ═════════════════════════════════════════════════════════════════════════════
# THE CHECKS
# ═════════════════════════════════════════════════════════════════════════════
def check_page(rel: str, texto: str, code: Code, rotas: list, achar) -> dict:
    """Checks one page; the web paths it names are appended to `rotas` as
    (page, line, path) for `check_routes`."""
    stats = {"links": 0, "paths": 0, "symbols": 0, "routes": 0, "facts": 0}
    linhas = _strip_fences(texto)
    base = os.path.dirname(rel)

    # 1. links (inline, reference-style and HTML)
    for n, linha in enumerate(linhas, 1):
        sem_codigo = CODE_SPAN.sub("", linha)
        alvos = [m.group(1) for m in LINK.finditer(sem_codigo)]
        alvos += [m.group(1) for m in HTML_ATTR.finditer(sem_codigo)]
        m = REF_DEF.match(sem_codigo)
        if m:
            alvos.append(m.group(1))
        for alvo in alvos:
            if re.match(r"^[a-z][a-z0-9+.-]*:", alvo, re.I):   # http:, mailto:, …
                continue
            stats["links"] += 1
            caminho, _, ancora = alvo.partition("#")
            if not caminho:
                if ancora and ancora not in anchors(texto):
                    achar("links", rel, n, f"`#{ancora}` is not a heading of this page")
                continue
            destino = os.path.normpath(os.path.join(base, caminho)).replace(os.sep, "/")
            if destino.startswith(".."):
                achar("links", rel, n, f"`{alvo}` leaves the repository")
                continue
            if not code.exists(destino):
                achar("links", rel, n, f"`{alvo}` does not exist")
                continue
            if ancora and destino.endswith(".md"):
                if ancora not in anchors(io.open(os.path.join(code.root, *destino.split("/")),
                                                  encoding="utf-8").read()):
                    achar("links", rel, n, f"`{alvo}`: no heading `#{ancora}` in {destino}")

    # 3b. "`x()` in `file`" / "`X` (`file`)": the name is defined in THAT file.
    # Read over the whole text (a sentence wraps lines), each match mapped back to its line.
    # Only owner-shaped names are claims: a call (`x()`) must be DEFINED in the file;
    # an UPPER_CASE name must be defined there or read there (an environment knob).
    corrido = "\n".join(linhas)
    for m in SYMBOL_IN_FILE.finditer(corrido):
        n = corrido.count("\n", 0, m.start()) + 1
        nome = m.group("sym").split(".")[-1]
        rel_f = m.group("path")
        maiusculo = bool(re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", nome))
        if not (m.group("call") or maiusculo) or not code.exists(rel_f):
            continue  # not a claim about the file / the path check reports it
        stats["symbols"] += 1
        ok = nome in code.defined_in(rel_f)
        if not ok and maiusculo:
            ok = re.search(r"\b%s\b" % re.escape(nome),
                           io.open(os.path.join(code.root, *rel_f.split("/")), encoding="utf-8").read()) is not None
        if not ok:
            achar("symbols", rel, n, f"`{m.group('sym')}{m.group('call') or ''}` is not defined in {rel_f}")

    # 2–4. what is written in code style
    for n, token in code_spans(linhas):
        token = token.strip()
        if not token:
            continue
        if " " in token and not re.match(r"^(GET|POST|PUT|DELETE) /", token):
            # a command: each word that is a path or a module must exist
            for w in token.split():
                w = w.strip("\"'`,;()")
                if code.is_path(w) and not any(g in w.split("/") for g in GENERATED):
                    for alt in _expand(re.sub(r":\d+(-\d+)?$", "", w)):
                        stats["paths"] += 1
                        if not code.exists(alt):
                            achar("paths", rel, n, f"`{alt}` (in `{token}`) does not exist")
                elif code.is_module(w):
                    stats["paths"] += 1
                    erro = code.module_error(w)
                    if erro:
                        achar("paths", rel, n, erro)
            continue
        if code.is_module(token):
            stats["paths"] += 1
            erro = code.module_error(token)
            if erro:
                achar("paths", rel, n, erro)
            continue
        # 4. routes — collected here, resolved by the real router afterwards
        rota = re.sub(r"^(GET|POST|PUT|DELETE) ", "", token)
        if rota.startswith("/") and re.fullmatch(r"/[\w\-./{}:*]*(\?\S*)?", rota):
            stats["routes"] += 1
            rotas.append((rel, n, rota.split("?", 1)[0]))
            continue
        # 2. paths
        if code.is_path(token):
            limpo = re.sub(r":\d+(-\d+)?$", "", token)
            for alt in _expand(limpo):
                if any(g in alt.split("/") for g in GENERATED) or alt in LOCAL_ONLY:
                    continue
                stats["paths"] += 1
                if not code.exists(alt):
                    achar("paths", rel, n, f"`{alt}` does not exist")
            continue
        # 3. symbols
        m = re.fullmatch(r"(?:[A-Za-z_][\w]*\.)*([A-Za-z_]\w*)\(\)", token)
        if m:
            stats["symbols"] += 1
            if m.group(1) not in code.functions:
                achar("symbols", rel, n, f"`{token}` is not defined anywhere in the code")
            continue
        m = re.fullmatch(r"([A-Z][A-Za-z0-9]*)\.([a-z_][a-z0-9_]*)", token)
        if m and m.group(1) in code.models:
            stats["symbols"] += 1
            if m.group(2) not in code.models[m.group(1)]:
                achar("symbols", rel, n, f"`{token}`: {m.group(1)} has no column `{m.group(2)}`")
            continue
        m = re.fullmatch(r"(?:[a-z_][\w]*\.)*([A-Z][A-Z0-9_]{2,})(=\S*)?", token)
        if m and (("_" in m.group(1)) or len(m.group(1)) >= 4):
            nome = m.group(1)
            stats["symbols"] += 1
            if nome not in code.names and nome not in code.env and nome not in KNOWN_WORDS \
                    and nome not in code.functions:
                achar("symbols", rel, n, f"`{nome}` is neither a name in the code nor a variable in .env.example")

    # 5. numbers
    if os.path.basename(rel) not in NUMBERS_EXEMPT or "/" in rel:
        for n, linha in enumerate(linhas, 1):
            sem = CODE_SPAN.sub(" ", linha)
            for m in MARKER.finditer(sem):
                stats["facts"] += 1
                nome = m.group("fact")
                try:
                    medido = _fact_value(nome)
                except Exception as e:
                    base = re.sub(r"[/*]-?\d+(?:\.\d+)?$", "", nome)
                    if base not in FACTS and not base.startswith(("env:", "val:", "len:")):
                        achar("numbers", rel, n, f"`#{nome}` is not a fact (add it to FACTS, or use "
                                                 f"#env:VAR, #val:file:NAME or #len:file:NAME)")
                    else:
                        achar("numbers", rel, n, f"`#{nome}` could not be measured: {e}")
                    continue
                texto = m.group("num")
                if _as_number(texto) is None and _version(texto) is None:
                    achar("numbers", rel, n, f"`{texto}` before `#{nome}` is not a number")
                elif not _same(texto, bool(m.group("pct")), medido, bool(m.group("plus"))):
                    diz = texto + m.group("pct") + m.group("plus")
                    achar("numbers", rel, n, f"says {diz} for `#{nome}`, the code has {medido} "
                                             f"({_fact_where(nome)})")
            sem = MARKER.sub(" ", sem)
            sem = re.sub(r"<!--.*?-->", " ", sem)
            sem = LINK.sub(lambda mm: " " + re.sub(r"\]\(.*$", "", mm.group(0)).lstrip("!["), sem)
            sem = re.sub(r"<[^>]+>", " ", sem)
            sem = re.sub(r"https?://\S+", " ", sem)
            for rx, _motivo in CONVENTIONS:
                sem = re.sub(rx, " ", sem)
            sem = re.sub(r"^\s{0,3}#{1,6}\s+\d+(?:\.\d+)*\.?\s", " ", sem)   # "## 1. Code"
            sem = re.sub(r"^\s*\d+[.)]\s", " ", sem)                         # "1. a list item"
            sem = re.sub(r"^\s*\|?\s*-{3,}.*$", " ", sem)                   # table rule
            for m in NUMBER.finditer(sem):
                achar("numbers", rel, n,
                      f"`{m.group(0)}` is not measured — mark it with a fact "
                      f"(`{m.group(0)}<!--#name-->`) or write the sentence without it")
    return stats


def check_routes(rotas: list, achar) -> None:
    """Asks the real router about every collected path (one process for all).
    A family written with its slash (`/api/miniapp/`) or a star must have routes under it.
    A one-word path that main.py registers as a chat command (`/cultivar`) is a command."""
    comandos = {"/" + c for c in chat_commands()}
    web = [r for _rel, _n, r in rotas if r not in comandos]
    try:
        servido = resolve_routes(web)
    except Exception as e:
        achar("routes", "core/webserver.py", 0, str(e))
        return
    for rel, n, rota in rotas:
        if rota in comandos or servido.get(rota):
            continue
        if re.fullmatch(r"/[a-z0-9_]+", rota):
            achar("routes", rel, n, f"`{rota}` is neither a route of the application nor a chat command")
        else:
            achar("routes", rel, n, f"`{rota}` is not a route of the application")


def check_coverage(code: Code, textos: dict[str, str], achar) -> dict:
    """Every engine, handler and community module named in docs/; every flag in architecture."""
    nos_docs = set()
    for rel, texto in textos.items():
        if rel.startswith("docs/"):
            for _n, token in code_spans(_strip_fences(texto)):
                nos_docs.update(_expand(token.strip()))
    modulos = _modules("core") + _modules("handlers") + _modules("community")
    for mod in modulos:
        if mod not in nos_docs:
            achar("coverage", mod, 0, "no page in docs/ names this module — say what it does, and where")
    arq = textos.get("docs/architecture.md", "")
    nomes_arq = {t.strip() for _n, t in code_spans(_strip_fences(arq))}
    try:
        flags = list(_literal("database/db.py", "DEFAULT_WORLD_FEATURES"))
    except Exception as e:
        achar("coverage", "database/db.py", 0, f"could not read DEFAULT_WORLD_FEATURES: {e}")
        flags = []
    for f in flags:
        if f not in nomes_arq:
            achar("coverage", "docs/architecture.md", 0, f"the feature flag `{f}` is not documented")
    return {"modules": len(modulos), "flags": len(flags)}


# ═════════════════════════════════════════════════════════════════════════════
# THE SELF-TEST — one defect of each kind, all of which MUST be seen
# ═════════════════════════════════════════════════════════════════════════════
SELF_TEST = textwrap.dedent("""\
    # Self test

    The game has 999 realms and **12**<!--#realms--> realm names.
    It has 140+<!--#migrations--> migrations, eleven<!--#realms--> realms and <!--#x-->.
    A broken [link](no/such/file.md), a [dead anchor](#nowhere) and a [good one](#self-test).
    The path `core/no_such_engine.py`, the function `no_such_function()` and `NO_SUCH_KNOB`.
    The route `/no/such/route`, the page `/player` (the site's catch-all takes only files),
    the family `/api/miniapp/` and the route `/api/miniapp/player`, and the column `Player.no_such_column`.
    The chat command `/cultivar`, and one that does not exist: `/no_such_command`; an API path only the
    CORS preflight matches: `/api/miniapp/no_such_endpoint`.
    The owner `compute_cultivator_soul()` in `core/cultivator_soul.py`, but not `compute_cultivator_soul()` in
    `core/game_logic.py`; and `DEFAULT_WORLD_FEATURES` (`database/db.py`).
    Run `python scripts/no_such_script.py`, or `python -m community.no_such_module`.
    ```
    numbers in code are fine: 12345
    ```
    The fact `#unknown`: 7<!--#no_such_fact-->.
    Knobs: 4<!--#env:TRAVEL_COOLDOWN_HOURS--> hours, 20%<!--#env:LGC_OPEN_CHANCE-->, six<!--#env:ENV_COOLDOWN_SECONDS/3600-->
    hours, 1,000<!--#val:core/anel.py:RING_MAX_SLOTS[5]--> slots, 5<!--#len:core/continent_engine.py:CONTINENT_KEYS-->
    continents — and a stale one: 5<!--#env:TRAVEL_COOLDOWN_HOURS--> hours.
""")
SELF_TEST_EXPECTS = [
    ("numbers", "`999` is not measured"),
    ("numbers", "says 12 for `#realms`"),
    ("links", "`no/such/file.md` does not exist"),
    ("links", "`#nowhere` is not a heading"),
    ("paths", "`core/no_such_engine.py` does not exist"),
    ("symbols", "`no_such_function()` is not defined"),
    ("symbols", "`NO_SUCH_KNOB` is neither"),
    ("routes", "`/no/such/route` is not a route"),
    ("routes", "`/player` is neither a route"),
    ("routes", "`/no_such_command` is neither a route of the application nor a chat command"),
    ("symbols", "`compute_cultivator_soul()` is not defined in core/game_logic.py"),
    ("routes", "`/api/miniapp/no_such_endpoint` is not a route"),
    ("symbols", "Player has no column `no_such_column`"),
    ("paths", "`scripts/no_such_script.py` (in `python scripts/no_such_script.py`) does not exist"),
    ("paths", "`community.no_such_module` is not a module"),
    ("numbers", "`#no_such_fact` is not a fact"),
    ("numbers", "says 5 for `#env:TRAVEL_COOLDOWN_HOURS`"),
]
SELF_TEST_MUST_NOT = ["`140", "`11", "eleven", "12345", "#self-test", "says 4 ", "LGC_OPEN_CHANCE",
                      "ENV_COOLDOWN_SECONDS", "RING_MAX_SLOTS", "CONTINENT_KEYS", "`/api/miniapp/` is",
                      "`/api/miniapp/player`",
                      "`/cultivar`", "in core/cultivator_soul.py", "DEFAULT_WORLD_FEATURES"]


def self_test(code: Code) -> list[str]:
    vistos, rotas = [], []
    anotar = lambda cat, rel, n, motivo: vistos.append((cat, motivo))  # noqa: E731
    check_page("docs/_self_test.md", SELF_TEST, code, rotas, anotar)
    check_routes(rotas, anotar)
    falhas = [f"did not see: [{c}] {s}" for c, s in SELF_TEST_EXPECTS
              if not any(cat == c and s in m for cat, m in vistos)]
    falhas += [f"saw a defect that is not one: {m}" for _c, m in vistos
               if any(x in m for x in SELF_TEST_MUST_NOT)]
    return falhas


# ═════════════════════════════════════════════════════════════════════════════
def verify(root: str = ROOT) -> dict:
    achados: list[dict] = []

    def achar(cat, rel, n, motivo):
        achados.append({"category": cat, "file": rel, "line": n, "reason": motivo})

    code = Code(root)
    for f in self_test(code):
        achar("self-test", "scripts/_verifica_documentacao.py", 0, f)

    lista = pages(root)
    textos = {rel: io.open(os.path.join(root, *rel.split("/")), encoding="utf-8").read() for rel in lista}
    stats = {"pages": len(lista), "links": 0, "paths": 0, "symbols": 0, "routes": 0, "facts": 0}
    rotas: list = []
    for rel, texto in textos.items():
        for k, v in check_page(rel, texto, code, rotas, achar).items():
            stats[k] += v
    check_routes(rotas, achar)
    stats.update(check_coverage(code, textos, achar))
    # never green on an empty set
    if not any(r.startswith("docs/") for r in lista):
        achar("coverage", "docs/", 0, "there is no page in docs/")
    if stats["facts"] == 0:
        achar("numbers", "docs/", 0, "no number carries a fact marker — the number check saw nothing")
    cats = ("links", "paths", "symbols", "routes", "numbers", "coverage", "self-test")
    return {"ok": not achados, "stats": stats,
            "by_category": {c: sum(1 for a in achados if a["category"] == c) for c in cats},
            "findings": achados}


def main() -> int:
    if "--facts" in sys.argv:
        for nome, (onde, _fn) in FACTS.items():
            try:
                valor = _fact_value(nome)
            except Exception as e:
                valor = f"ERROR {e}"
            print(f"  {nome:<20} {str(valor):<10} {onde}")
        return 0
    r = verify()
    s = r["stats"]
    print(f"文 the documentation tells the truth — {s['pages']} pages · {s['links']} links · "
          f"{s['paths']} paths · {s['symbols']} names · {s['routes']} routes · {s['facts']} measured numbers · "
          f"{s['modules']} modules and {s['flags']} flags covered")
    for cat, n in r["by_category"].items():
        print(f"  {'✅' if n == 0 else '❌'} {cat:<10} {n}")
    for x in r["findings"][:200]:
        onde = f"{x['file']}:{x['line']}" if x["line"] else x["file"]
        print(f"  ❌ [{x['category']}] {onde} — {x['reason']}")
    if len(r["findings"]) > 200:
        print(f"  … and {len(r['findings']) - 200} more")
    print("RESULT:", "the pages match the code" if r["ok"]
          else f"{len(r['findings'])} finding(s) — fix the page or the code")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
