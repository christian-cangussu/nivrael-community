# -*- coding: utf-8 -*-
"""開 A EDIÇÃO COMUNITÁRIA — o que esta cópia promete, provado a correr.

Porque existe (Open Source F1, 2026-10-21)
------------------------------------------
A cópia pública é o jogo oficial com SEIS diferenças declaradas. Cada uma é uma
promessa a quem a corre, e cada promessa aqui é medida pela CHAMADA (o dono que
decide), nunca pelo texto que a configura — a 21/10 a flag da monetização estava
certa no registo do `main` e o dono da pergunta (`monetization_enabled_for`)
continuava a responder `True` fixo: o dado dizia uma coisa, a decisão outra.

  1. A monetização nasce DESLIGADA, e `NIVRAEL_MONETIZATION=1` liga-a (as Stars:
     2 cobranças no mini-app, 3 no chat — todas pelo mesmo dono).
  2. O gacha fecha no dono (`perform_gacha_pull`) e as telas dizem porquê.
  3. A identidade do jogo oficial não vem assada (Firebase, contacto legal).
  4. A porta local (`community/dev_login.py`) só abre quando deve, e recusa
     fora da rede local.
  5. O mundo local nasce com o jogo de hoje ligado (as 40 flags).
  6. O `.env.example` documenta TODA a variável que o código lê, e os ficheiros
     da comunidade existem e dizem a verdade.
  7. A CI corre o que a casa promete (o Python da produção, o comando inteiro,
     as guardas a morder, o DCO, o compose) sem segredos nem actions soltas, e os
     modelos de issue e de PR pedem o que a casa pede (F2).
  8. O `.env` que se lê é o DESTA pasta, nunca o de uma pasta-pai — guardada
     dentro de outro projecto, a cópia não arranca com a base nem o token dele.

Cada verificação que depende do ambiente corre num processo à parte, com o
ambiente limpo e o `.env` desligado — o resultado não muda com a máquina.

Uso:  python -X utf8 scripts/_test_edicao_comunitaria.py
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL: list[str] = []


def check(nome: str, cond, detalhe="") -> None:
    global PASS
    if cond:
        PASS += 1
        print(f"  ok  {nome}")
    else:
        FAIL.append(f"{nome} — {detalhe}" if detalhe else nome)
        print(f"  XX  {nome}" + (f"  ({str(detalhe)[:300]})" if detalhe else ""))


def rd(rel: str) -> str:
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


# O ambiente de cada sub-processo: sem nada que mude a resposta, e sem `.env`.
_LIMPAR = ("NIVRAEL_", "FIREBASE_", "LEGAL_CONTACT_EMAIL", "WEBHOOK_", "BOT_TOKEN",
           "SESSION_SECRET", "DATABASE_URL", "CONTROL_DATABASE_URL", "SIGNUP_WORLD")
_PRELUDIO = (
    "import sys, json, os\n"
    f"sys.path.insert(0, {ROOT!r})\n"
    "import dotenv\n"
    "dotenv.load_dotenv = lambda *a, **k: False\n"
)


def py(codigo: str, **env) -> dict:
    """Corre `codigo` num Python limpo; ele imprime `@@<json>` na última linha."""
    e = {k: v for k, v in os.environ.items() if not k.startswith(_LIMPAR)}
    e.update({k: str(v) for k, v in env.items()})
    e["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", _PRELUDIO + textwrap.dedent(codigo)],
                       cwd=ROOT, env=e, capture_output=True, text=True, encoding="utf-8")
    linhas = [l for l in r.stdout.splitlines() if l.startswith("@@")]
    if r.returncode != 0 or not linhas:
        return {"_erro": (r.stderr or r.stdout)[-900:]}
    return json.loads(linhas[-1][2:])


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 1. A monetização nasce desligada — e o interruptor liga-a ===")
FLAG = """
import config
from database.db import monetization_enabled_for, _main_world_row
print("@@" + json.dumps({"cfg": config.MONETIZATION_ENABLED,
                         "main": monetization_enabled_for("main"),
                         "desconhecido": monetization_enabled_for("mundo_que_nao_existe"),
                         "linha": _main_world_row()["monetization_enabled"]}))
"""
off, on = py(FLAG), py(FLAG, NIVRAEL_MONETIZATION="1")
check("sem nada no ambiente, a flag está DESLIGADA", off.get("cfg") is False, off)
check("o DONO da pergunta diz que o `main` não cobra", off.get("main") is False, off)
check("…e um mundo que não se resolve também não (lê-se como o `main`)",
      off.get("desconhecido") is False, off)
check("o registo do `main` em memória concorda", off.get("linha") is False, off)
check("`NIVRAEL_MONETIZATION=1` devolve o jogo oficial (dono, desconhecido e registo)",
      on.get("cfg") is True and on.get("main") is True and on.get("desconhecido") is True
      and on.get("linha") is True, on)

_cdb = rd("database/control_db.py")
_row = _cdb[_cdb.index("_BOOTSTRAP_MAIN_ROW = "):_cdb.index("async def bootstrap_control_db")]
check("a linha de controlo do `main` nasce com a flag (`:mon`), não com `true`",
      ":mon, true, 0)" in _row and "false, true, true, 0)" not in _row)
check("…e cada arranque volta a aplicá-la (EXCLUDED), em vez de forçar `true`",
      "monetization_enabled = EXCLUDED.monetization_enabled" in _row
      and "monetization_enabled = true" not in _row)
check("…com o valor da flag no parâmetro", '"mon": MONETIZATION_ENABLED' in _cdb)

STARS = """
import asyncio
from core import webserver as W
class R(dict):
    pass
async def go():
    out = {}
    for wk in ("main", "local", "mundo_que_nao_existe"):
        resp = await W.api_shop_buy_jade(R(user_id=1, payload={"pack": "pack_1"}, world_key=wk))
        out["jade_" + wk] = json.loads(resp.text).get("reason")
        resp = await W.api_shop_buy_monthly(R(user_id=1, payload={"card_type": "silver"}, world_key=wk))
        out["mensal_" + wk] = json.loads(resp.text).get("reason")
    return out
print("@@" + json.dumps(asyncio.run(go())))
"""
st = py(STARS)
# F4b (23/10): sem nenhum mundo a cobrar, a razão é a sua — `purchases_official_only`
# (o mesmo dono do chat, `stars_refusal`); `sandbox_world` fica para quando o `main` cobra.
check("mini-app: o Jade por Stars recusa em TODO o mundo (main, local, desconhecido), porque nenhum cobra",
      all(st.get("jade_" + w) == "purchases_official_only" for w in ("main", "local", "mundo_que_nao_existe")), st)
check("mini-app: o Passe mensal por Stars recusa em todo o mundo, pela mesma razão",
      all(st.get("mensal_" + w) == "purchases_official_only" for w in ("main", "local", "mundo_que_nao_existe")), st)

CHAT = """
import asyncio, types
import handlers.shop as SH
chamadas = []
async def _resposta(q, *a, **k):
    chamadas.append(k)
SH.safe_answer = _resposta
q = types.SimpleNamespace(invoice_payload="jade_66_123", from_user=types.SimpleNamespace(id=123))
asyncio.run(SH.precheckout_callback(types.SimpleNamespace(pre_checkout_query=q), None))
print("@@" + json.dumps(chamadas[-1]))
"""
c_off, c_on = py(CHAT), py(CHAT, NIVRAEL_MONETIZATION="1")
check("chat: o pagamento por Stars é recusado ANTES da cobrança (pre-checkout)",
      c_off.get("ok") is False, c_off)
check("…com a frase que aponta o jogo oficial, não 'o Servidor Principal'",
      "oficial" in (c_off.get("error_message") or "")
      and "Servidor Principal" not in (c_off.get("error_message") or ""), c_off)
check("…e com a flag ligada o mesmo pre-checkout aprova (é a flag que decide)",
      c_on.get("ok") is True, c_on)

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 2. O gacha fecha no dono, e as telas dizem porquê ===")
GACHA = """
import asyncio
from core.monetization import gacha_enabled, perform_gacha_pull
out = {"aberto": gacha_enabled()}
try:
    out["tiragem"] = asyncio.run(perform_gacha_pull(None, 1, 1, "banner"))
except AttributeError:
    out["tiragem"] = "passou-o-portao"
from core import webserver as W
class R(dict):
    pass
try:
    out["banners"] = json.loads(asyncio.run(W.api_gacha_banners(R(user_id=1))).text)
except Exception:
    out["banners"] = "passou-o-portao"
print("@@" + json.dumps(out))
"""
g_off, g_on = py(GACHA), py(GACHA, NIVRAEL_MONETIZATION="1")
check("o gacha está fechado por defeito", g_off.get("aberto") is False, g_off)
check("a tiragem recusa NO DONO, antes de tocar na base",
      g_off.get("tiragem") == {"success": False, "error_key": "err_gacha_official_only"}, g_off)
check("a leitura dos banners diz que está fechado (a tela não fica vazia)",
      g_off.get("banners") == {"ok": False, "reason": "err_gacha_official_only"}, g_off)
check("com a flag ligada a tiragem e os banners passam o portão (vão à base)",
      g_on.get("aberto") is True and g_on.get("tiragem") == "passou-o-portao"
      and g_on.get("banners") == "passou-o-portao", g_on)

_gacha_chat = rd("handlers/gacha.py")
check("chat: /gacha e o botão da loja fecham os dois (2 portões)",
      _gacha_chat.count("if not gacha_enabled():") == 2)
_tabs = rd("miniapp/components/tabs.js")
check("mini-app: a aba Gacha mostra a frase do porquê",
      'gacha?.reason === "err_gacha_official_only"' in _tabs)

CATALOGOS = ("locales/pt.json", "locales/en.json", "locales/es.json",
             "miniapp/i18n/pt.json", "miniapp/i18n/en.json", "miniapp/i18n/es.json")
_cat = {f: json.loads(rd(f)) for f in CATALOGOS}
check("a frase do gacha fechado existe nas 3 línguas, nas 2 superfícies",
      all((_cat[f].get("err_gacha_official_only") or "").strip() for f in CATALOGOS))
check("…e cada língua tem a SUA frase (nenhuma ficou por traduzir)",
      len({_cat[f]["err_gacha_official_only"] for f in CATALOGOS[:3]}) == 3
      and len({_cat[f]["err_gacha_official_only"] for f in CATALOGOS[3:]}) == 3)
# F4b (23/10): as frases do jogo oficial ficam como são, e a edição tem as SUAS —
# a chamada escolhe (`stars_refusal`; `mainSells` no lobby). Nada se reescreve.
_sbx = {f: _cat[f].get("shop_purchases_official_only", "") for f in CATALOGOS}
check("a recusa das Stars sem nenhum mundo a cobrar aponta o jogo oficial, nas 3 línguas e 2 superfícies "
      "(nunca 'o Servidor Principal')",
      all(re.search(r"oficial|official", v, re.I) and not re.search(r"Servidor Principal|Main Server", v)
          for v in _sbx.values()), _sbx)
check("…e a do jogo oficial continua a dele (aponta o Servidor Principal) — a cópia já não a reescreve",
      all(re.search(r"Servidor Principal|Main Server", _cat[f].get("shop_sandbox_blocked", ""))
          for f in CATALOGOS), {f: _cat[f].get("shop_sandbox_blocked") for f in CATALOGOS})
_lob = {f: _cat[f].get("lobby_separate_world_note", "") for f in CATALOGOS[3:]}
check("o lobby da edição não chama 'de teste' ao mundo onde se joga",
      all(v and "test" not in v.lower() and "prueba" not in v for v in _lob.values()), _lob)
_mapa = re.search(r"const SHOP_STARS_REFUSAL = \{(.*?)\};", _tabs, re.S)
_mapa = dict(re.findall(r'(\w+):\s*"(\w+)"', _mapa.group(1))) if _mapa else {}
check("mini-app: cada razão de recusa das Stars tem a sua frase (o mapa do cliente)",
      _mapa == {"sandbox_world": "shop_sandbox_blocked",
                "purchases_official_only": "shop_purchases_official_only"}, _mapa)
check("mini-app: o lobby só aponta o Servidor Principal quando o `main` cobra",
      'const mainSells = servers.some(s => s.key === "main" && s.monetization_enabled);' in _tabs
      and 't(mainSells ? "lobby_sandbox_note" : "lobby_separate_world_note")' in _tabs)

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 3. A identidade do jogo oficial não vem assada ===")
IDENT = """
import asyncio
from core.webserver import firebase_web_config
from core import firebase_auth as FA, legal as LG
out = {"fb": firebase_web_config(), "pid": FA.project_id(), "contacto": LG.CONTACT_EMAIL}
try:
    asyncio.run(FA.verify_firebase_id_token("x.y.z"))
    out["verifica"] = "aceitou"
except FA.FirebaseAuthError as e:
    out["verifica"] = e.reason
print("@@" + json.dumps(out))
"""
i0 = py(IDENT)
i1 = py(IDENT, FIREBASE_PROJECT_ID="o-meu-projecto", FIREBASE_API_KEY="chave-publica-de-teste",
        LEGAL_CONTACT_EMAIL="operador@example.org")
check("sem `.env`, o Firebase do cliente vem VAZIO (nada do projecto oficial)",
      i0.get("fb") == {"apiKey": "", "authDomain": "", "projectId": "", "appId": ""}, i0)
check("…e o verificador do servidor não tem projecto", i0.get("pid") == "", i0)
check("…logo um token qualquer é recusado como configuração em falta, nunca aceite",
      i0.get("verifica") == "server_misconfigured", i0)
check("com o projecto do operador, é ESSE que vale (cliente e servidor)",
      i1.get("pid") == "o-meu-projecto" and i1.get("fb", {}).get("projectId") == "o-meu-projecto"
      and i1.get("fb", {}).get("authDomain") == "o-meu-projecto.firebaseapp.com", i1)
check("o contacto legal por defeito é um marcador que não recebe correio (.invalid)",
      str(i0.get("contacto", "")).endswith(".invalid"), i0)
check("…e o do operador substitui-o", i1.get("contacto") == "operador@example.org", i1)
_oficiais = re.compile(r"nivrael-f558f|AIzaSy|536992372740|suporte@nivrael\.com")
_assados = []
for pasta in ("core", "handlers", "database", "community"):
    for d, _s, ns in os.walk(os.path.join(ROOT, pasta)):
        for n in ns:
            if n.endswith(".py"):
                rel = os.path.relpath(os.path.join(d, n), ROOT).replace(os.sep, "/")
                if _oficiais.search(rd(rel)):
                    _assados.append(rel)
check("nenhum identificador do jogo oficial assado no código", not _assados, _assados)

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 4. A porta local abre só quando deve ===")
PORTA = r"""
import asyncio
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer, make_mocked_request
from unittest import mock
import core.web_session as WS
import database.control_db as CDB
from community import dev_login as DL

out = {}
os.environ.pop("NIVRAEL_DEV_LOGIN", None); os.environ.pop("WEBHOOK_URL", None)
out["fechada"] = DL.state()[0]
os.environ["NIVRAEL_DEV_LOGIN"] = "1"
out["aberta"] = DL.state()[0]
os.environ["WEBHOOK_URL"] = "https://exemplo.invalid/hook"
out["producao"] = DL.state()[0]
os.environ.pop("WEBHOOK_URL")
out["pares"] = {p: DL.peer_is_local(p) for p in
                ("127.0.0.1", "::1", "172.17.0.1", "192.168.1.5", "10.0.0.7", "100.64.0.7", "", "lixo")}
out["nomes"] = {n: DL.valid_name(n) for n in
                ("Lin Feng", "a", "Ãngela", "x" * 24, "x" * 25, " lin", "lin ", "<script>", "_lin", "Lin_Feng-2")}
out["mesma_conta"] = DL.account_key("Lin  Feng") == DL.account_key("lin feng")

registo = {}
async def _find(p, uid):
    registo["find"] = (p, uid); return None
async def _alloc():
    return -1000000077
async def _link(p, uid, pid, prof):
    registo["link"] = (p, uid, pid, prof); return (5, pid)
async def _issue(pid, p, iid, prof):
    import datetime as _d
    registo["issue"] = (pid, p, iid, prof)
    return ("v1.sid.0.mac", "csrf-de-teste", _d.datetime.now(_d.timezone.utc) + _d.timedelta(days=1))
WS.find_identity, WS.link_identity, WS.issue_session = _find, _link, _issue
CDB.allocate_synthetic_player_id = _alloc

async def go():
    app = web.Application()
    async def oficial(request):
        return web.Response(text="PORTA-OFICIAL")
    app.router.add_get("/login", oficial)
    DL.install(app)
    async with TestClient(TestServer(app)) as c:
        os.environ.pop("NIVRAEL_DEV_LOGIN", None)
        r = await c.get("/login"); out["fechada_login"] = await r.text()
        r = await c.post("/dev/login", data={"nome": "Lin"}); out["fechada_post"] = r.status
        os.environ["NIVRAEL_DEV_LOGIN"] = "1"
        r = await c.get("/login"); t = await r.text()
        out["aberta_login"] = [r.status, "本地之門" in t, 'name="nome"' in t, 'lang="pt"' in t]
        r = await c.get("/login?lang=en"); t = await r.text()
        out["aberta_en"] = ["Enter the local world" in t, "nv_lang" in r.headers.get("Set-Cookie", "")]
        r = await c.get("/login?lang=es"); t = await r.text()
        out["aberta_es"] = "Entrar al mundo local" in t
        r = await c.get("/login?porta=oficial"); out["porta_oficial"] = await r.text()
        r = await c.post("/dev/login", data={"nome": "x", "lang": "pt"}); t = await r.text()
        out["invalido"] = [r.status, "2 a 24" in t]
        r = await c.post("/dev/login", data={"nome": " Lin  Feng ", "lang": "en"}, allow_redirects=False)
        cookies = r.headers.getall("Set-Cookie", [])
        out["entrou"] = [r.status, r.headers.get("Location"),
                         any(x.startswith("nv_session=") and "HttpOnly" in x for x in cookies),
                         any(x.startswith("nv_csrf=") for x in cookies)]
    req = make_mocked_request("POST", "/dev/login", transport=mock.Mock(
        get_extra_info=lambda k, d=None: ("100.64.0.7", 4321) if k == "peername" else d))
    out["de_fora"] = (await DL.sign_in(req)).status

asyncio.run(go())
out["registo"] = {"find": registo.get("find"), "link_uid": (registo.get("link") or [None, None])[1],
                  "perfil": (registo.get("issue") or [None] * 4)[3], "provider": (registo.get("issue") or [None, None])[1]}
print("@@" + json.dumps(out, ensure_ascii=False))
"""
p = py(PORTA)
check("fechada sem a flag", p.get("fechada") is False, p)
check("aberta com NIVRAEL_DEV_LOGIN=1", p.get("aberta") is True, p)
check("…mas RECUSA abrir com WEBHOOK_URL definido (isso é produção)", p.get("producao") is False, p)
check("só aceita a própria máquina e a rede local (o par TCP)",
      p.get("pares") == {"127.0.0.1": True, "::1": True, "172.17.0.1": True, "192.168.1.5": True,
                         "10.0.0.7": True, "100.64.0.7": False, "": False, "lixo": False}, p.get("pares"))
check("nomes: 2 a 24, letras de qualquer língua, sem espaço nas pontas nem marcação",
      p.get("nomes") == {"Lin Feng": True, "a": False, "Ãngela": True, "x" * 24: True, "x" * 25: False,
                         " lin": False, "lin ": False, "<script>": False, "_lin": False, "Lin_Feng-2": True},
      p.get("nomes"))
check("o mesmo nome escrito de outra maneira é a MESMA conta", p.get("mesma_conta") is True, p)
check("fechada, /login é a porta oficial e /dev/login não existe (404)",
      p.get("fechada_login") == "PORTA-OFICIAL" and p.get("fechada_post") == 404, p)
check("aberta, /login é a porta local (o selo, o campo, a língua)",
      p.get("aberta_login") == [200, True, True, True], p.get("aberta_login"))
check("…nas três línguas, e a escolha viaja no cookie `nv_lang`",
      p.get("aberta_en") == [True, True] and p.get("aberta_es") is True, p)
check("…e a porta oficial continua alcançável (`?porta=oficial`)", p.get("porta_oficial") == "PORTA-OFICIAL", p)
check("um nome inválido volta à porta com o PORQUÊ (400)", p.get("invalido") == [400, True], p.get("invalido"))
check("entrar dá a sessão web do jogo (303 → /app, cookie HttpOnly + o do CSRF)",
      p.get("entrou") == [303, "/app", True, True], p.get("entrou"))
_r = p.get("registo") or {}
check("…pela identidade `dev`, com o nome normalizado como conta",
      _r.get("provider") == "dev" and _r.get("find") == ["dev", "lin feng"] and _r.get("link_uid") == "lin feng", _r)
check("…e o perfil leva o nome e a língua para o personagem nascer certo",
      (_r.get("perfil") or {}).get("first_name") == "Lin Feng"
      and (_r.get("perfil") or {}).get("language_code") == "en", _r)
check("um pedido de fora da rede local é recusado (403)", p.get("de_fora") == 403, p)
_ws = rd("core/webserver.py")
check("a porta local não existe no código do jogo — só em `community/`",
      "/dev/login" not in _ws and "NIVRAEL_DEV_LOGIN" not in _ws)

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 5. O mundo local nasce com o jogo de hoje ligado ===")
MUNDO = r"""
import asyncio
import database.db as DB
import core.world_provision as WP
import database.control_db as CDB
from community import local_world as LW

chamadas, sql = [], []
async def _prov(key, name, **kw):
    chamadas.append({"key": key, "name": name, **kw}); return {}
WP.provision_world = _prov
class _Res:
    def __init__(self, n): self.rowcount = n
class _S:
    def __init__(self, n): self.n = n
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def execute(self, q, p=None): sql.append((str(q), p)); return _Res(self.n)
    async def commit(self): pass
out = {"flags": LW.all_features_on(), "padrao": list(DB.DEFAULT_WORLD_FEATURES)}
DB.iter_active_world_keys = lambda: ["main", LW.WORLD_KEY]
out["existia"] = asyncio.run(LW.ensure()); out["prov_existia"] = len(chamadas)
DB.iter_active_world_keys = lambda: ["main"]
CDB.get_control_session_factory = lambda: (lambda: _S(0))
out["criado"] = asyncio.run(LW.ensure())
CDB.get_control_session_factory = lambda: (lambda: _S(1))
out["reparado"] = asyncio.run(LW.ensure())
out["chamada"] = chamadas[0] if chamadas else None
out["sql"] = sql[0][0] if sql else ""
out["key"] = LW.WORLD_KEY
print("@@" + json.dumps(out, ensure_ascii=False, default=str))
"""
m = py(MUNDO)
check("o mundo local liga TODAS as flags do jogo (uma por uma, nenhuma esquecida)",
      m.get("flags") and set(m["flags"]) == set(m.get("padrao", [])) and all(m["flags"].values())
      and len(m["flags"]) >= 40, (len(m.get("flags") or {}), m.get("_erro")))
check("se o mundo já existe, não se cria outra vez", m.get("existia") == "existia" and m.get("prov_existia") == 0, m)
_c = m.get("chamada") or {}
check("cria-se pelo MESMO caminho do jogo oficial, sandbox, público e sem código",
      _c.get("key") == m.get("key") and _c.get("requires_code") is False and _c.get("is_public") is True
      and _c.get("monetization_enabled") is False and _c.get("gen_code") is False, _c)
check("…com as 40 flags no `balance_config`",
      isinstance(_c.get("balance_config"), dict)
      and set((_c.get("balance_config") or {}).get("features", {})) == set(m.get("padrao", [])), _c)
check("as flags só se reescrevem se o mundo ficou a meio (features vazias), nunca por cima das do admin",
      "COALESCE(balance_config->'features', '{}'::jsonb) = '{}'::jsonb" in m.get("sql", ""), m.get("sql"))
check("criado vs reparado é dito", m.get("criado") == "criado" and m.get("reparado") == "reparado", m)

ARRANQUE = r"""
import community.local as L
L.load_dotenv = lambda *a, **k: False
L.STATE_DIR = os.environ["_DIR"]
n1 = L._prepare_env(); s1 = os.environ.get("SESSION_SECRET")
os.environ.pop("SESSION_SECRET")
n2 = L._prepare_env(); s2 = os.environ.get("SESSION_SECRET")
print("@@" + json.dumps({"signup": os.environ.get("SIGNUP_WORLD"), "s1": bool(s1) and len(s1) >= 40,
                         "igual": s1 == s2, "notas1": n1, "notas2": n2,
                         "inseguro": os.environ.get("NIVRAEL_COOKIE_INSECURE"),
                         "ficheiro": os.path.isfile(os.path.join(os.environ["_DIR"], "session_secret"))}))
"""
with tempfile.TemporaryDirectory() as tmp:
    a0 = py(ARRANQUE, _DIR=tmp)
with tempfile.TemporaryDirectory() as tmp:
    a1 = py(ARRANQUE, _DIR=tmp, NIVRAEL_DEV_LOGIN="1", SIGNUP_WORLD="outro")
check("quem entra nasce no mundo local por defeito", a0.get("signup") == "local", a0)
check("…mas o SIGNUP_WORLD do operador manda", a1.get("signup") == "outro", a1)
check("sem SESSION_SECRET nem BOT_TOKEN, gera um segredo forte e guarda-o",
      a0.get("s1") is True and a0.get("ficheiro") is True, a0)
check("…e o arranque seguinte REUSA o mesmo (as sessões sobrevivem ao reinício)", a0.get("igual") is True, a0)
check("o cookie só perde o `Secure` com a porta local ligada",
      a0.get("inseguro") is None and a1.get("inseguro") == "1", (a0.get("inseguro"), a1.get("inseguro")))

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 6. O .env.example está completo, e a comunidade tem a casa arrumada ===")
_lidas = set()
_rx_env = re.compile(r"os\.(?:getenv|environ\.get)\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']|os\.environ\[[\"']([A-Z][A-Z0-9_]+)[\"']\]")
for pasta in ("core", "handlers", "database", "community"):
    for d, _s, ns in os.walk(os.path.join(ROOT, pasta)):
        for n in ns:
            if n.endswith(".py"):
                for a_, b_ in _rx_env.findall(rd(os.path.relpath(os.path.join(d, n), ROOT))):
                    _lidas.add(a_ or b_)
for f in ("main.py", "config.py", "resource_monitor.py"):
    for a_, b_ in _rx_env.findall(rd(f)):
        _lidas.add(a_ or b_)

# ⚠️ (F2, 22/10) Não só `os.getenv("X")` directo. Três motores lêem os seus botões
# por um AJUDANTE (`_env_int("LIB_T2_CP", 750)`), e esta verificação não os via:
# dizia "TODAS" com 28 de fora. Segue-se a indirecção pela ESTRUTURA, não por
# nome: um ajudante é qualquer função cujo corpo passa o seu 1.º parâmetro a
# `os.getenv` / `os.environ.get` / `os.environ[...]`; cada chamada a ele com um
# nome literal é uma variável lida. Um ajudante novo, com outro nome, também conta.
import ast as _ast


def _e_leitura_env(no, param) -> bool:
    if isinstance(no, _ast.Call) and no.args and isinstance(no.args[0], _ast.Name) \
            and no.args[0].id == param and _ast.unparse(no.func) in ("os.getenv", "os.environ.get"):
        return True
    return isinstance(no, _ast.Subscript) and _ast.unparse(no.value) == "os.environ" \
        and isinstance(no.slice, _ast.Name) and no.slice.id == param


_fontes = [os.path.relpath(os.path.join(d, n), ROOT)
           for pasta in ("core", "handlers", "database", "community")
           for d, _s, ns in os.walk(os.path.join(ROOT, pasta)) for n in ns if n.endswith(".py")]
_fontes += ["main.py", "config.py", "resource_monitor.py"]
_arvores = {}
for f in _fontes:
    try:
        _arvores[f] = _ast.parse(rd(f))
    except SyntaxError:
        pass
_ajudantes = {fn.name for arv in _arvores.values() for fn in _ast.walk(arv)
              if isinstance(fn, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and fn.args.args
              and any(_e_leitura_env(x, fn.args.args[0].arg) for x in _ast.walk(fn))}
_por_ajudante = {c.args[0].value for arv in _arvores.values() for c in _ast.walk(arv)
                 if isinstance(c, _ast.Call) and isinstance(c.func, _ast.Name) and c.func.id in _ajudantes
                 and c.args and isinstance(c.args[0], _ast.Constant) and isinstance(c.args[0].value, str)
                 and re.fullmatch(r"[A-Z][A-Z0-9_]+", c.args[0].value)}
check("os ajudantes que lêem o ambiente são seguidos (e há chamadas por eles)",
      _ajudantes and _por_ajudante, (sorted(_ajudantes), len(_por_ajudante)))
_lidas |= _por_ajudante
_lidas -= {"PYTHONUNBUFFERED", "_DIR"}
_exemplo = rd(".env.example") if os.path.isfile(os.path.join(ROOT, ".env.example")) else ""
_doc = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", _exemplo, re.M))
_falta = sorted(_lidas - _doc)
check(f"as {len(_lidas)} variáveis que o código lê estão TODAS no .env.example "
      f"({len(_por_ajudante)} delas por um ajudante)", not _falta, _falta[:20])
check("o .env.example diz que a monetização vem desligada e como se liga",
      re.search(r"^#?\s*NIVRAEL_MONETIZATION=0\s*$", _exemplo, re.M) is not None)
check("…e que a porta local é só para desenvolvimento",
      "NIVRAEL_DEV_LOGIN=1" in _exemplo and re.search(r"nunca|never", _exemplo, re.I) is not None)

COMUNIDADE = ("README.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md", "LICENSE",
              "LICENSE-ASSETS", "NOTICE.md", "TRADEMARKS.md", "CHANGELOG.md", "ROADMAP.md",
              # F5 (24/10) — quem decide (o FUNDING.yml saiu: nenhum canal, decisão do owner)
              "MAINTAINERS.md", ".github/CODEOWNERS",
              "docker-compose.yml", ".env.example", ".gitignore",
              # F2 — a documentação, a CI e os modelos
              "docs/README.md", ".github/workflows/ci.yml", ".github/dependabot.yml",
              ".github/pull_request_template.md", ".github/ISSUE_TEMPLATE/bug.yml",
              ".github/ISSUE_TEMPLATE/idea.yml", ".github/ISSUE_TEMPLATE/translation.yml")
_faltam = [f for f in COMUNIDADE if not os.path.isfile(os.path.join(ROOT, f))
           or not rd(f).strip()]
check(f"os {len(COMUNIDADE)} ficheiros da comunidade existem e não estão vazios", not _faltam, _faltam)
if not _faltam:
    _gi = rd(".gitignore")
    check("o .gitignore nunca deixa sair o .env, o estado local nem os builds",
          all(re.search(r"^" + re.escape(x) + r"\s*$", _gi, re.M)
              for x in (".env", ".nivrael/", "node_modules/", "dist/", "__pycache__/"))
          and "!.env.example" in _gi)
    _dc = rd("docker-compose.yml")
    check("o docker-compose sobe Postgres 17 + o jogo pela porta local",
          "postgres:17" in _dc and "community.local" in _dc and "NIVRAEL_DEV_LOGIN" in _dc
          and "8080:8080" in _dc and "service_healthy" in _dc)
    _readme = rd("README.md")
    check("o README diz as licenças, o nome reservado e o que é só do jogo oficial",
          all(x in _readme for x in ("AGPL-3.0", "CC BY-NC-SA 4.0", "TRADEMARKS.md",
                                     "docker compose up", "NIVRAEL_MONETIZATION")))
    _contrib = rd("CONTRIBUTING.md")
    check("o CONTRIBUTING pede o DCO (Signed-off-by) e as guardas antes do PR",
          "Signed-off-by" in _contrib and "_verifica_copia_publica.py" in _contrib)
    # F5 (24/10) — as decisões 6, 8 e 12 do owner, ditas onde quem chega as lê
    check("o README diz o estado do projecto: o jogo vivo e os 30 dias de aviso, nas 3 línguas",
          "## Project status" in _readme and "**30 days** ahead" in _readme
          and "**30 dias** de antecedência" in _readme and "**30 días** de antelación" in _readme)
    _mant = rd("MAINTAINERS.md")
    _maos = set(re.findall(r"@([A-Za-z0-9-]+)", _mant))
    check("o MAINTAINERS nomeia quem decide, e nenhum mantenedor toca no servidor nem nos dados",
          bool(_maos) and "decided by its owner alone" in _mant
          and re.search(r"No maintainer[^.]*receives access[^.]*server, its\s+credentials or its\s+players'\s+data",
                        _mant) is not None, sorted(_maos))
    _donos = set(re.findall(r"@([A-Za-z0-9-]+)", "\n".join(
        l for l in rd(".github/CODEOWNERS").splitlines() if not l.lstrip().startswith("#"))))
    check("o CODEOWNERS pede a revisão de quem está no MAINTAINERS (e só deles)",
          bool(_donos) and _donos <= _maos, f"CODEOWNERS {sorted(_donos)} · MAINTAINERS {sorted(_maos)}")
    check("o CONTRIBUTING aponta o MAINTAINERS em 'Who decides'",
          "MAINTAINERS.md" in _contrib.split("## Who decides", 1)[-1])
    _fund = os.path.join(ROOT, ".github", "FUNDING.yml")
    _canais = ([l for l in open(_fund, encoding="utf-8").read().splitlines()
                if l.strip() and not l.lstrip().startswith("#")] if os.path.isfile(_fund) else None)
    check("sem canal de apoio por escolher: o FUNDING.yml ou não existe ou tem um canal a sério",
          _canais is None or bool(_canais), _canais)

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_guarda", os.path.join(ROOT, "scripts", "_verifica_copia_publica.py"))
_g = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_g)
_res = _g.verificar(ROOT)
check("a guarda da cópia pública está limpa (segredos, jogadores, IPs, ficheiros, licenças)",
      _res["ok"], _res["por_categoria"])

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 7. A CI corre o que a casa promete, e os modelos pedem o que a casa pede ===")
# (F2, 22/10) A CI é a guarda que corre sem ninguém se lembrar dela — e uma CI
# que deixou de correr o comando certo fica verde para sempre, calada. Sem
# PyYAML (não é dependência do jogo) o ficheiro lê-se por blocos de job: cada
# job vai do `  <nome>:` até ao job seguinte do mesmo nível.
_ci_p = ".github/workflows/ci.yml"
_ci = rd(_ci_p) if os.path.isfile(os.path.join(ROOT, _ci_p)) else ""
# o que o GitHub executa — os comentários explicam, não contam
_ci = "\n".join(l for l in _ci.splitlines() if not l.lstrip().startswith("#"))


def _job(nome: str) -> str:
    m = re.search(r"^  %s:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)" % re.escape(nome), _ci, re.M | re.S)
    return m.group(1) if m else ""


_jobs = {n: _job(n) for n in ("tests", "client", "guards", "dco", "compose")}
check("a CI tem os 5 jobs (testes, cliente, guardas, DCO, compose)", all(_jobs.values()),
      [n for n, v in _jobs.items() if not v])
_on = re.search(r"^on:\n(.*?)(?=^\S)", _ci, re.M | re.S)
_on = _on.group(1) if _on else ""
check("corre em cada pull request e em cada push para o main",
      re.search(r"^  pull_request:\s*$", _on, re.M) is not None
      and re.search(r"^  push:\n    branches: \[main\]\s*$", _on, re.M) is not None, _on)
check("…e nunca com `pull_request_target` (o gatilho que dá segredos ao código de um fork)",
      "pull_request_target" not in _ci)
check("o token é só de leitura (`permissions: contents: read` no topo)",
      re.search(r"^permissions:\n  contents: read\s*$", _ci, re.M) is not None)
check("nenhum job lê um segredo", "secrets." not in _ci)
_usos = re.findall(r"uses:\s*(\S+)", _ci)
_soltos = [u for u in _usos if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u)]
check(f"as {len(_usos)} actions estão presas a um commit (uma etiqueta pode mudar debaixo de nós)",
      _usos and not _soltos, _soltos)
_dockerfile = rd("Dockerfile")
_py_docker = (re.search(r"^FROM python:([\d.]+)", _dockerfile, re.M) or [None, "?"])[1]
_node_docker = (re.search(r"^FROM node:([\d.]+)", _dockerfile, re.M) or [None, "?"])[1]
check(f"os testes correm no Python do contentor de produção ({_py_docker})",
      re.search(r'python-version: "%s"' % re.escape(_py_docker), _jobs["tests"]) is not None, _py_docker)
check("…e correm o comando do CONTRIBUTING, inteiro (`python scripts/run_tests.py`, sem filtro)",
      re.search(r"run: python scripts/run_tests\.py\s*$", _jobs["tests"], re.M) is not None)
check("…com o esbuild do site e um Chrome (sem eles a `_test_cena_cabe` fica vermelha)",
      "npm ci" in _jobs["tests"] and "NV_CHROME=" in _jobs["tests"])
check(f"o cliente compila no Node do Dockerfile ({_node_docker}), como a imagem o compila",
      re.search(r'node-version: "%s"' % re.escape(_node_docker), _jobs["client"]) is not None
      and "npm run build" in _jobs["client"] and "node scripts/build_miniapp.mjs miniapp" in _jobs["client"])
check("as guardas são provadas a morder em cada PR (a bateria de sabotagem)",
      "python scripts/_sabota_a_copia_publica.py" in _jobs["guards"])
check("o DCO é verificado nos PRs, commit a commit, com o histórico inteiro",
      "scripts/_verifica_dco.py" in _jobs["dco"] and "github.event_name == 'pull_request'" in _jobs["dco"]
      and "fetch-depth: 0" in _jobs["dco"])
check("o compose sobe de verdade, o fumo entra como um jogador e as capturas ficam guardadas",
      "docker compose up --build" in _jobs["compose"] and "scripts/_fumo_da_edicao.py" in _jobs["compose"]
      and "--shots" in _jobs["compose"] and "upload-artifact" in _jobs["compose"]
      and "docker compose down" in _jobs["compose"])
_chamados = sorted(set(re.findall(r"(scripts/[\w./-]+\.(?:py|mjs))", _ci)))
check(f"os {len(_chamados)} scripts que a CI chama existem",
      _chamados and all(os.path.isfile(os.path.join(ROOT, c)) for c in _chamados), _chamados)
check("o Dependabot mantém as actions presas ao dia (e o DCO dispensa os bots)",
      "package-ecosystem: github-actions" in rd(".github/dependabot.yml")
      and "[bot]@users.noreply.github.com" in rd("scripts/_verifica_dco.py"))


def _caixas(texto: str) -> list[str]:
    return [l.strip() for l in texto.splitlines() if l.strip().startswith("- [ ]")]


_caixas_contrib = _caixas(rd("CONTRIBUTING.md"))
_caixas_pr = _caixas(rd(".github/pull_request_template.md"))
check(f"o modelo de PR traz a checklist do CONTRIBUTING ({len(_caixas_contrib)} itens), "
      "item a item e pela mesma ordem", _caixas_contrib and _caixas_pr == _caixas_contrib,
      sorted(set(_caixas_contrib) ^ set(_caixas_pr)))


def _campos(forma: str) -> dict[str, str]:
    """Os blocos de `body:` de um modelo de issue, por `id`."""
    out = {}
    for bloco in re.split(r"\n  - type:", forma)[1:]:
        m = re.search(r"^\s+id: ([\w-]+)", bloco, re.M)
        if m:
            out[m.group(1)] = bloco
    return out


_formas = {n: rd(f".github/ISSUE_TEMPLATE/{n}.yml") for n in ("bug", "idea", "translation")
           if os.path.isfile(os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", f"{n}.yml"))}
check("os 3 modelos de issue existem (bug, ideia, tradução)", len(_formas) == 3, sorted(_formas))
for _n, _txt in _formas.items():
    check(f"o modelo `{_n}` tem nome, descrição, uma etiqueta e um campo obrigatório",
          re.search(r"^name: \S", _txt, re.M) and re.search(r"^description: \S", _txt, re.M)
          and re.search(r'^labels: \["[\w ]+"\]', _txt, re.M) and "required: true" in _txt)
_bug = _campos(_formas.get("bug", ""))
check("o bug pede o que aconteceu e os passos para o reproduzir (obrigatórios)",
      "required: true" in _bug.get("what", "") and "required: true" in _bug.get("steps", ""), sorted(_bug))
check("…e manda um problema de segurança para o SECURITY.md, nunca para uma issue",
      "SECURITY.md" in _formas.get("bug", ""))
_trad = _campos(_formas.get("translation", ""))
check("a tradução pede a língua, o texto de agora e o certo (obrigatórios)",
      all("required: true" in _trad.get(k, "") for k in ("language", "now", "should")), sorted(_trad))

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 8. O .env que se lê é o DESTA pasta — nunca o de uma pasta-pai ===")
# Medido a 23/10: guardada dentro de outro projecto com `.env`, a cópia arrancava
# com o `.env` DELE — o `load_dotenv()` sem caminho sobe pelas pastas-pai até achar
# um. Prova-se a correr, com o dotenv VERDADEIRO (o resto da suite desliga-o): os
# dois sítios que o lêem — o `config.py` e o arranque local — numa pasta cujo PAI
# tem um `.env` com valores-canário; e, para a prova não ser verde sobre o vazio,
# o `.env` da própria pasta continua a ser lido.
_CANARIO = "postgresql://canario@pai.invalid/base_do_pai"
_PROPRIO = "postgresql://proprio@local.invalid/base_da_edicao"
_LER_ENV = (
    "import json, os\n"
    "import config\n"
    "from community.local import _prepare_env\n"
    "_prepare_env()\n"
    "print('@@' + json.dumps({'config': config.DATABASE_URL, 'token': config.BOT_TOKEN,\n"
    "                         'arranque': os.environ.get('DATABASE_URL', '')}))\n"
)


def _le_env(com_env_proprio: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="nv_dotenv_") as t:
        pai = os.path.join(t, "outro-projecto")
        ed = os.path.join(pai, "edicao")
        os.makedirs(os.path.join(ed, "community"))
        with open(os.path.join(pai, ".env"), "w", encoding="utf-8") as fh:
            fh.write(f"DATABASE_URL={_CANARIO}\nBOT_TOKEN=canario-do-pai\n")
        if com_env_proprio:
            with open(os.path.join(ed, ".env"), "w", encoding="utf-8") as fh:
                fh.write(f"DATABASE_URL={_PROPRIO}\n")
        for rel in ("config.py", "community/__init__.py", "community/local.py", "community/local_world.py"):
            with open(os.path.join(ROOT, *rel.split("/")), "rb") as fi, \
                    open(os.path.join(ed, *rel.split("/")), "wb") as fo:
                fo.write(fi.read())
        e = {k: v for k, v in os.environ.items() if not k.startswith(_LIMPAR)}
        e["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", _LER_ENV], cwd=ed, env=e,
                           capture_output=True, text=True, encoding="utf-8")
        linhas = [l for l in r.stdout.splitlines() if l.startswith("@@")]
        if r.returncode != 0 or not linhas:
            return {"_erro": (r.stderr or r.stdout)[-600:]}
        return json.loads(linhas[-1][2:])


_sem, _com = _le_env(False), _le_env(True)
check("o config.py NÃO lê o .env da pasta-pai (a base e o token do canário não chegam)",
      _sem.get("config") == "" and _sem.get("token") == "", _sem)
check("o arranque local (`community/local.py`) também não",
      _sem.get("arranque") == "", _sem)
check("…e o .env DESTA pasta continua a ser lido (nos dois sítios)",
      _com.get("config") == _PROPRIO and _com.get("arranque") == _PROPRIO, _com)

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 9. O fumo espera o jogo PRONTO, não só vivo ===")
# (F5, 25/10) O `/healthz` responde 200 desde o 1.º segundo — é a vida do processo,
# que o health check dos servidores oficiais lê — e diz a prontidão no CORPO. O fumo
# esperava pelo 200 e, num compose acabado de arrancar (o 1.º run da CI), entrava a
# meio do 1.º arranque: o recém-chegado nascia no `main`, ainda sem tabelas. Medido
# pela chamada: um /healthz de mentira que diz `ready: false` antes do `true`.
import http.server
import threading
import time
import types


class _Saude(http.server.BaseHTTPRequestHandler):
    pedidos, pronto_ao = 0, 3

    def do_GET(self):  # noqa: N802 — o nome é do http.server
        type(self).pedidos += 1
        pronto = type(self).pronto_ao is not None and type(self).pedidos >= type(self).pronto_ao
        corpo = json.dumps({"status": "ok" if pronto else "starting", "ready": pronto}).encode()
        self.send_response(200)  # SEMPRE 200, como o verdadeiro
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


_srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Saude)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
try:
    _spec_f = _ilu.spec_from_file_location("_fumo", os.path.join(ROOT, "scripts", "_fumo_da_edicao.py"))
    _fumo = _ilu.module_from_spec(_spec_f)
    _spec_f.loader.exec_module(_fumo)
    _fumo.time = types.SimpleNamespace(time=time.time, sleep=lambda s: time.sleep(0.05))
    _nav = _fumo.Browserless(f"http://127.0.0.1:{_srv.server_address[1]}")
    _ok = _fumo.esperar_pronto(_nav, 20)
    check("o fumo espera o `ready: true` do /healthz, não o primeiro 200",
          _ok and _Saude.pedidos >= 3, f"pronto={_ok} ao fim de {_Saude.pedidos} pedido(s)")
    _Saude.pedidos, _Saude.pronto_ao = 0, None
    _ok2 = _fumo.esperar_pronto(_nav, 1)
    check("…e um jogo que nunca fica pronto nunca passa (estar vivo não chega)",
          not _ok2 and _Saude.pedidos >= 1, f"pronto={_ok2} · {_Saude.pedidos} pedido(s)")
finally:
    _srv.shutdown()

# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)
print(f"OK — {PASS} asserts. A cópia não cobra ninguém, não fala em nome do jogo oficial, "
      "abre a porta local só onde deve e diz tudo o que lê.")
