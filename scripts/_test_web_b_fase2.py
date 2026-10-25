# -*- coding: utf-8 -*-
"""WEB-B **Fase 2** — a porta deixa de precisar do Telegram.

O que esta suite existe para impedir:

 1. **Confusão de algoritmo.** É o ataque clássico contra quem verifica JWT: o
    atacante troca o `alg` por `none` ou por HS256 (assinando com a chave
    PÚBLICA, que é pública) e uma verificação ingénua aceita. Aqui os tokens são
    MINTADOS de verdade, com uma chave RSA gerada no teste — não são fixtures.
 2. **Aceitar um token de outro projecto** (`aud`) ou de outro emissor (`iss`).
    Sem estas duas verificações, qualquer pessoa com um projecto Firebase seu
    entrava no nosso jogo com o token dela.
 3. **Enumeração de contas** — pela resposta e pela copy.
 4. **Colisão / reutilização do id sintético.**
 5. ⚠️ **O beco sem saída de quem não tem Telegram.** O `world/start` recusava
    `main` porque "o onboarding é o /start do chat". Para um jogador de
    Google/Apple/e-mail o chat NÃO EXISTE: conta criada, sessão válida, e
    nenhuma forma de ter personagem (Lei §1).
 6. **`_safe_send` a telefonar ao Telegram com um id negativo.**

Corre sem Postgres e sem rede: a JWKS é remendada em memória.
"""
import asyncio
import io
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("BOT_TOKEN", "1:fake-for-tests")

_ok, _bad = 0, []


def chk(cond, msg):
    global _ok
    if cond:
        _ok += 1
        print("  ok  " + msg)
    else:
        _bad.append(msg)
        print("  XX  " + msg)


def rd(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 1. O verificador do ID token: tokens REAIS, chave gerada aqui ===")
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# 開 A edição comunitária não traz projecto Firebase por defeito (o do jogo
# oficial ficava assado); a suite declara o SEU, como faz quem corre o jogo.
os.environ.setdefault("FIREBASE_PROJECT_ID", "projeto-de-teste")
import core.firebase_auth as FA

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIV = KEY.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8,
                         serialization.NoEncryption())
PUB = KEY.public_key()
PUB_PEM = PUB.public_bytes(serialization.Encoding.PEM,
                           serialization.PublicFormat.SubjectPublicKeyInfo)
KID = "test-kid-1"
PID = FA.project_id()

# Remendar a ida ao Google. A chave é a NOSSA — nada sai desta máquina.
async def _fake_jwks(force=False):
    return {KID: PUB}
FA._fetch_jwks = _fake_jwks


def mint(**over):
    now = int(time.time())
    claims = {
        "iss": f"https://securetoken.google.com/{PID}",
        "aud": PID,
        "sub": "uid-abc-123",
        "iat": now - 10,
        "exp": now + 3600,
        "auth_time": now - 10,
        "email": "Fulano@Example.COM",
        "email_verified": True,
        "name": "Fulano",
        "firebase": {"sign_in_provider": "google.com"},
    }
    claims.update(over)
    headers = over.pop("_headers", None) or {"kid": KID}
    return jwt.encode(claims, PRIV, algorithm="RS256", headers=headers)


def verify(tok):
    return asyncio.run(FA.verify_firebase_id_token(tok))


def refused(tok):
    """Devolve o `reason` da recusa, ou None se (mal) tiver passado."""
    try:
        verify(tok)
        return None
    except FA.FirebaseAuthError as e:
        return e.reason


prof = verify(mint())
chk(prof["uid"] == "uid-abc-123", "um token bem assinado passa e devolve o uid")
chk(prof["email"] == "fulano@example.com",
    "o e-mail é normalizado para minúsculas (%s)" % prof["email"])
chk(prof["sign_in_provider"] == "google.com", "o provider real vem na resposta")

# ── Confusão de algoritmo ───────────────────────────────────────────────────
# ⚠️ A PyJWT RECUSA-SE a CRIAR estes tokens (protege quem assina). Um atacante
# não usa a PyJWT — monta os três segmentos à mão. É o que fazemos aqui, senão
# o teste mediria a educação da nossa biblioteca em vez da nossa defesa.
import base64
import hashlib
import hmac as _hmac


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def forge(alg: str, secret: bytes | None):
    """Monta um JWT à mão. `secret=None` => `alg: none`, sem assinatura."""
    hdr = _b64(json.dumps({"alg": alg, "typ": "JWT", "kid": KID}).encode())
    now = int(time.time())
    body = _b64(json.dumps({
        "iss": f"https://securetoken.google.com/{PID}", "aud": PID,
        "sub": "atacante", "iat": now - 10, "exp": now + 3600,
    }).encode())
    signing_input = f"{hdr}.{body}".encode()
    if secret is None:
        return f"{hdr}.{body}."
    sig = _hmac.new(secret, signing_input, hashlib.sha256).digest()
    return f"{hdr}.{body}.{_b64(sig)}"


# O atacante conhece a chave PÚBLICA (está publicada em JWKS) e assina um HS256
# com ela. Se aceitássemos o `alg` do token, isto entrava como qualquer pessoa.
chk(refused(forge("HS256", PUB_PEM)) == "login_invalid",
    "⚠️ HS256 assinado com a chave PÚBLICA é recusado (confusão de algoritmo)")
chk(refused(forge("none", None)) == "login_invalid", "⚠️ `alg: none` é recusado")
chk(refused(forge("HS256", b"secret")) == "login_invalid",
    "HS256 com qualquer outro segredo também é recusado")

# ── Outro projecto / outro emissor ──────────────────────────────────────────
chk(refused(mint(aud="outro-projecto")) == "login_invalid",
    "⚠️ token de OUTRO projecto Firebase é recusado (`aud`)")
chk(refused(mint(iss="https://securetoken.google.com/outro")) == "login_invalid",
    "⚠️ token de outro emissor é recusado (`iss`)")

# ── Tempo ───────────────────────────────────────────────────────────────────
# ⚠️ Tem de estar para lá do `CLOCK_SKEW_SECONDS` (60s), senão o teste mede a
# tolerância de relógio e não a expiração. Um `exp` de há 5s É aceite de
# propósito — relógios de browser andam torcidos, e recusar por causa disso
# trancava gente fora do jogo sem motivo.
chk(refused(mint(exp=int(time.time()) - 5)) is None,
    "um `exp` acabado de passar ainda entra (tolerância de relógio, %ds)"
    % FA.CLOCK_SKEW_SECONDS)
chk(refused(mint(exp=int(time.time()) - 3600)) == "token_expired",
    "expirado há uma hora é recusado, e DIZ que expirou (o cliente pede outro)")
chk(refused(mint(auth_time=int(time.time()) + 9999)) == "login_invalid",
    "`auth_time` no futuro é recusado")

# ── Assinatura e forma ──────────────────────────────────────────────────────
other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
other_pem = other.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
forged = jwt.encode({"iss": f"https://securetoken.google.com/{PID}", "aud": PID,
                     "sub": "x", "iat": int(time.time()) - 10,
                     "exp": int(time.time()) + 3600},
                    other_pem, algorithm="RS256", headers={"kid": KID})
chk(refused(forged) == "login_invalid", "assinado com outra chave RSA: recusado")
chk(refused(mint(_headers={"kid": "kid-que-nao-existe"})) == "login_invalid",
    "`kid` desconhecido é recusado")
chk(refused(mint(sub="")) == "login_invalid", "`sub` vazio é recusado (não há uid)")
for lixo in ("", "a.b", "não-é-um-jwt", "x" * 9000):
    chk(refused(lixo) == "login_invalid", "lixo recusado (%r...)" % lixo[:14])

src = rd("core/firebase_auth.py")
chk('algorithms=["RS256"]' in src,
    "⚠️ a lista de algoritmos é EXPLÍCITA, nunca lida do token")
chk('header.get("alg") != "RS256"' in src, "o `alg` do cabeçalho é conferido antes de tudo")
chk('"require": ["exp", "iat", "aud", "iss", "sub"]' in src,
    "as claims obrigatórias são exigidas, não assumidas")


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 2. O id sintético: negativo, único, nunca reutilizado ===")
import database.control_db as CDB

_seq = {"n": 0}


class _FakeRow:
    def __init__(self, v): self._v = v
    def scalar_one(self): return self._v


class _FakeSession:
    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        # ⚠️ Falso ESTRITO: uma instrução que ele não reconheça levanta. Foi a
        # gentileza do falso da F1 que deixou um bug chegar a produção.
        assert "nextval('web_player_id_seq')" in sql, "SQL inesperado: %s" % sql
        _seq["n"] += 1
        return _FakeRow(_seq["n"])
    async def commit(self): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


CDB._ensure_control_engine = lambda: (lambda: _FakeSession())
ids = [asyncio.run(CDB.allocate_synthetic_player_id()) for _ in range(200)]
chk(all(i is not None for i in ids), "aloca sempre que o plano de controlo responde")
chk(all(i < 0 for i in ids), "todos os ids são NEGATIVOS")
chk(len(set(ids)) == len(ids), "200 alocações, 200 valores distintos (zero colisões)")
chk(ids[0] == -(CDB.SYNTHETIC_ID_BASE + 1),
    "o 1º jogador web é %d" % -(CDB.SYNTHETIC_ID_BASE + 1))
chk(all(ids[i] > ids[i + 1] for i in range(len(ids) - 1)),
    "a sequência só desce — um valor devolvido nunca volta")
chk(min(ids) > -(2 ** 62), "cabe folgadamente num BIGINT")

cdb_src = rd("database/control_db.py")
chk("CREATE SEQUENCE IF NOT EXISTS web_player_id_seq" in cdb_src,
    "a sequência vive no PLANO DE CONTROLO (única ENTRE mundos, não dentro de um)")
chk("IF NOT EXISTS" in cdb_src.split("web_player_id_seq")[0][-80:],
    "o bootstrap é idempotente (corre em todo o boot)")

# Plano de controlo em baixo → None, e NUNCA um id inventado.
CDB._ensure_control_engine = lambda: None
chk(asyncio.run(CDB.allocate_synthetic_player_id()) is None,
    "⚠️ sem plano de controlo devolve None — nunca inventa um id")
ws_src = rd("core/webserver.py")
seg = ws_src.split("async def api_auth_firebase", 1)[1].split("async def ", 1)[0]
chk("if synthetic is None" in seg and "server_misconfigured" in seg,
    "o handler recusa o login em vez de inventar um id")


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 3. _safe_send recusa chat_id <= 0 SEM telefonar ao Telegram ===")
# ⚠️ O `python-telegram-bot` não está instalado nesta máquina (só no
# contentor). Stub MÍNIMO: o suficiente para os dois módulos importarem.
# ⚠️ Repare que o stub NÃO implementa `send_message` — quem envia é o espião
# abaixo, e é ele que conta. Um stub que 'enviasse' daria verde a um guarda
# partido, que é exactamente como o bug do backfill chegou a produção.
import types as _types
if "telegram" not in sys.modules:
    # O `python-telegram-bot` só existe no contentor. Este stub responde a
    # QUALQUER nome que a cadeia de imports peça (`TimedOut`, `NetworkError`,
    # ...), porque enumerá-los à mão dava um teste que parte sempre que uma
    # linha de import muda noutro ficheiro.
    #
    # ⚠️ O que ele NÃO faz é `send_message`. Quem envia é o espião abaixo, e é
    # ele que conta. Um stub que 'enviasse' daria verde a um guarda partido —
    # foi assim que o bug do backfill passou por 188 asserts.
    def _mk_module(name, base):
        mod = _types.ModuleType(name)
        made = {}

        def _auto(attr):
            if attr.startswith("__"):
                raise AttributeError(attr)
            if attr not in made:
                made[attr] = type(attr, (base,), {})
            return made[attr]
        mod.__getattr__ = _auto
        return mod

    _tg = _mk_module("telegram", object)
    _tgerr = _mk_module("telegram.error", Exception)
    # O único que precisa de forma própria: o handler lê `e.retry_after`.
    class _RetryAfter(Exception):
        retry_after = 0
    _tgerr.RetryAfter = _RetryAfter
    _tg.error = _tgerr
    sys.modules["telegram"] = _tg
    sys.modules["telegram.error"] = _tgerr
    sys.modules["telegram.constants"] = _mk_module("telegram.constants", object)
    sys.modules["telegram.ext"] = _mk_module("telegram.ext", object)


class _SpyBot:
    def __init__(self): self.calls = 0
    async def send_message(self, **kw):
        self.calls += 1
        return True


for mod_name in ("core.notifications_engine", "core.scheduler"):
    mod = __import__(mod_name, fromlist=["_safe_send"])
    bot = _SpyBot()
    for bad_id in (0, -1, -1_000_000_001, -999):
        asyncio.run(mod._safe_send(bot, bad_id, "olá"))
    chk(bot.calls == 0,
        "%s: 4 ids inválidos, %d chamadas à API (esperado 0)" % (mod_name, bot.calls))
    asyncio.run(mod._safe_send(bot, 175746696, "olá"))
    chk(bot.calls == 1, "%s: um id REAL continua a ser enviado" % mod_name)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 4. O beco sem saída de quem não tem Telegram ===")
# ⚠️ Sem isto: conta criada, sessão válida, e nenhuma forma de ter personagem.
# O 404 do `main` significava "vai fazer /start no chat" — e quem entra pelo
# Google não tem chat nenhum.
seg_player = ws_src.split("async def api_player", 1)[1][:6000]
chk('int(user_id) < 0' in seg_player and "needs_world_start" in seg_player,
    "api_player oferece `needs_world_start` a um id negativo (não 404)")
seg_start = ws_src.split("async def api_world_start", 1)[1][:2500]
chk('world_key == "main" and int(user_id) >= 0' in seg_start,
    "world/start só recusa `main` a quem TEM Telegram")
chk("main_no_autostart" in seg_start,
    "e continua a recusar a quem tem (os 248 e o /start do chat, intactos)")


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 5. Anti-enumeração, na resposta E na copy ===")
page = rd("miniapp/login.html")
chk('case "auth/user-not-found":' in page and 'case "auth/wrong-password":' in page,
    "os dois códigos caem no MESMO ramo (o Firebase distingue; nós não)")
seg_map = page.split("function mapErr", 1)[1].split("}", 1)[0]
chk(seg_map.count("web_login_err_email") == 1,
    "e esse ramo devolve uma só frase para os dois")
chk('catch (e) {}' in page.split("btn-forgot", 1)[-1] or "sendPasswordResetEmail" in page,
    "o `esqueci a senha` engole o erro de propósito — a resposta é sempre igual")

chat = {lg: json.loads(rd("locales/%s.json" % lg)) for lg in ("pt", "en", "es")}
chk(len(set(len(v) for v in chat.values())) == 1,
    "as 3 locales continuam em paridade (%s)" % {k: len(v) for k, v in chat.items()})
for lg in ("pt", "en", "es"):
    t = (chat[lg].get("web_login_reset_sent") or "").lower()
    chk(any(w in t for w in ("se esse", "if that", "si ese")),
        "a resposta do reset em %s é CONDICIONAL ('se esse e-mail tiver conta')" % lg)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 6. A allowlist da porta, medida nos dois sentidos ===")
import core.webserver as W
declared = set(W.AUTH_PUBLIC_PATHS)
chk("/api/auth/firebase" in declared, "o caminho novo está declarado")
routed = set(re.findall(r'add_(?:post|get)\("(/api/auth/[^"]+)"', ws_src))
chk(declared == routed,
    "declaradas == roteadas (declaradas-roteadas=%s, roteadas-declaradas=%s)"
    % (sorted(declared - routed), sorted(routed - declared)))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 7. As páginas legais (o Google EXIGE a de privacidade) ===")
from core.legal import get_document, SUPPORTED
for kind in ("privacy", "terms"):
    for lg in SUPPORTED:
        d = get_document(kind, lg)
        chk(d["title"] and d["intro"] and len(d["sections"]) >= 6,
            "%s/%s tem título, intro e %d secções" % (kind, lg, len(d["sections"])))
        blob = " ".join(p for _, ps in d["sections"] for p in ps)
        chk("{email}" not in blob, "%s/%s sem marcador `{email}` por resolver" % (kind, lg))
chk(get_document("privacy", "xx")["lang"] == "en",
    "uma língua desconhecida degrada para inglês (o default público)")
chk(get_document("terms", "pt")["other_href"] == "/privacy",
    "os termos ligam para a privacidade")

for lg in SUPPORTED:
    blob = " ".join(p for _, ps in get_document("privacy", lg)["sections"] for p in ps).lower()
    chk("firebase" in blob, "a privacidade %s DIZ quem guarda a senha (não somos nós)" % lg)
    chk(any(w in blob for w in ("apagamento", "deletion", "borrado")),
        "a privacidade %s diz como pedir o apagamento" % lg)

# A porta liga para as duas — e as rotas TÊM de existir.
chk('href="/privacy"' in page and 'href="/terms"' in page, "a porta liga para as duas")
for rota in ("/privacy", "/privacy/", "/terms", "/terms/"):
    chk(('"%s"' % rota) in ws_src, "a rota %s está registada (sem isto: link morto)" % rota)


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 8. O widget aposentado não voltou ===")
# ⚠️ Medir o CÓDIGO, não a prosa: o comentário no topo da página cita o
# endpoint aposentado de propósito, para explicar por que ele saiu. Um
# assert sobre o ficheiro inteiro dava vermelho à documentação — é o mesmo
# erro que o guarda do backfill já tinha apanhado uma vez.
import re as _re
_code = _re.sub(r"<!--.*?-->", "", page, flags=_re.S)
chk("telegram-widget.js" not in _code,
    "⚠️ o widget que devolve `deprecated` não está na porta")
chk("oauth.telegram.org" not in _code, "nem o endpoint aposentado")
chk("oauth.telegram.org" in page,
    "…mas o comentário EXPLICA por que ele saiu (quem ler daqui a um ano percebe)")
chk("firebasejs" in page, "o SDK do Firebase é o que a porta carrega")
chk('href="https://t.me/"' not in page and "s-open-bot" in page,
    "e a saída pelo bot continua lá para os 248 (Lei §1)")



# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 9. UMA CONTA, QUALQUER PLATAFORMA — o codigo de vinculo ===")
import core.account_link as AL


class _LinkStore:
    """Falso ESTRITO do plano de controlo para o vinculo.

    Implementa as instrucoes que o modulo emite e LEVANTA perante uma que nao
    reconheca — a licao do backfill: um falso gentil da verde a SQL partida."""

    def __init__(self):
        self.codes = {}       # code -> {player_id, expires_at, used_at}
        self.identities = {}  # (provider, uid) -> player_id

    def __call__(self):
        return _LinkSession(self)


class _Row:
    def __init__(self, t): self._t = t
    def first(self): return self._t


class _LinkSession:
    def __init__(self, st): self.st = st
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def commit(self): pass
    async def rollback(self): pass

    async def execute(self, stmt, params=None):
        import datetime as _dt
        sql = " ".join(str(stmt).split())
        p = params or {}
        now = _dt.datetime.now(_dt.timezone.utc)
        st = self.st

        if sql.startswith("DELETE FROM account_link_codes WHERE player_id"):
            for c in [c for c, v in st.codes.items() if v["player_id"] == p["pid"]]:
                st.codes.pop(c)
            return _Row(None)

        if sql.startswith("INSERT INTO account_link_codes"):
            if p["c"] in st.codes:
                raise AssertionError("PK duplicada")
            st.codes[p["c"]] = {"player_id": p["pid"], "expires_at": p["exp"], "used_at": None}
            return _Row(None)

        if sql.startswith("SELECT player_id FROM account_link_codes"):
            v = st.codes.get(p["c"])
            if v is None or v["used_at"] is not None or v["expires_at"] <= now:
                return _Row(None)
            return _Row((v["player_id"],))

        if sql.startswith("UPDATE account_link_codes SET used_at"):
            if p["c"] in st.codes:
                st.codes[p["c"]]["used_at"] = now
            return _Row(None)

        if sql.startswith("SELECT player_id FROM auth_identities"):
            v = st.identities.get((p["p"], p["u"]))
            return _Row((v,) if v is not None else None)

        if sql.startswith("UPDATE auth_identities SET player_id"):
            k = (p["p"], p["u"])
            if k in st.identities:
                st.identities[k] = p["target"]
            return _Row(None)

        if sql.startswith("INSERT INTO auth_identities"):
            st.identities.setdefault((p["p"], p["u"]), p["target"])
            return _Row(None)

        if sql.startswith("SELECT provider, provider_uid, profile"):
            return _MappingRows([])

        raise AssertionError("SQL nao reconhecida pelo falso: " + sql[:120])


class _MappingRows:
    def __init__(self, rows): self._r = rows
    def mappings(self): return self
    def all(self): return self._r


STORE = _LinkStore()
AL._sm = lambda: STORE

# Quem TEM personagem. O `_has_character` real varre os mundos; aqui e um
# conjunto, porque o que interessa medir e a DECISAO, nao a varredura.
WITH_CHAR = {7001}
async def _fake_has_char(pid):
    return int(pid) in WITH_CHAR
AL._has_character = _fake_has_char

# Cenario: 7001 = jogador de Telegram, com personagem. -1000000009 = acabou
# de entrar com o Google e ainda NAO criou personagem.
TG, WEB = 7001, -1000000009
STORE.identities[("telegram", "7001")] = TG
STORE.identities[("firebase", "uid-web")] = WEB

code, exp = asyncio.run(AL.issue_link_code(TG))
chk(len(code) == AL.CODE_LENGTH, "o codigo tem %d caracteres" % AL.CODE_LENGTH)
chk(all(ch in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" for ch in code),
    "sem I/O/0/1 — os quatro que uma pessoa confunde ao copiar (%s)" % code)
chk(asyncio.run(AL.peek_link_code(code)) == TG, "espreitar o codigo nao o gasta")

# A normalizacao: as pessoas escrevem com espacos, hifens e minusculas.
chk(AL.normalize_code(code.lower()) == code, "minusculas sao aceites")
chk(AL.normalize_code(code[:4] + "-" + code[4:]) == code, "hifen no meio e aceite")
chk(AL.normalize_code(" " + code + " ") == code, "espacos a volta sao aceites")

# ── O caminho feliz: o Google passa a abrir a conta do Telegram ──────────
target = asyncio.run(AL.redeem_link_code(code, "firebase", "uid-web", WEB))
chk(target == TG, "a identidade do Google passou a apontar ao jogador do Telegram")
chk(STORE.identities[("firebase", "uid-web")] == TG,
    "⚠️ e e a LINHA da identidade que muda — `players` nao foi tocada")
chk(STORE.identities[("telegram", "7001")] == TG, "a identidade do Telegram fica intacta")

# ── Uso unico ────────────────────────────────────────────────────────────
try:
    asyncio.run(AL.redeem_link_code(code, "firebase", "outro-uid", -1000000010))
    chk(False, "um codigo gasto tem de ser recusado")
except AL.LinkError as e:
    chk(e.reason == "link_code_invalid", "codigo gasto -> link_code_invalid")

# ── Expirado ─────────────────────────────────────────────────────────────
import datetime as _dt
code2, _ = asyncio.run(AL.issue_link_code(TG))
STORE.codes[code2]["expires_at"] = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=1)
chk(asyncio.run(AL.peek_link_code(code2)) is None, "um codigo expirado nao se espreita")
try:
    asyncio.run(AL.redeem_link_code(code2, "firebase", "x", -1000000011))
    chk(False, "um codigo expirado tem de ser recusado")
except AL.LinkError as e:
    chk(e.reason == "link_code_invalid",
        "⚠️ expirado e inexistente dao a MESMA razao (nao dizer a quem adivinha que acertou)")

# ── ⚠️ A recusa que impede um personagem orfao ───────────────────────────
WITH_CHAR.add(-1000000012)
STORE.identities[("firebase", "uid-com-char")] = -1000000012
code3, _ = asyncio.run(AL.issue_link_code(TG))
try:
    asyncio.run(AL.redeem_link_code(code3, "firebase", "uid-com-char", -1000000012))
    chk(False, "ligar uma conta que JA tem personagem tem de ser recusado")
except AL.LinkError as e:
    chk(e.reason == "link_has_character",
        "⚠️ com personagem dos DOIS lados recusa-se: juntar seria escolher qual apagar")
chk(STORE.identities[("firebase", "uid-com-char")] == -1000000012,
    "e nada foi re-apontado na recusa")

# ── A propria conta ──────────────────────────────────────────────────────
code4, _ = asyncio.run(AL.issue_link_code(TG))
try:
    asyncio.run(AL.redeem_link_code(code4, "telegram", "7001", TG))
    chk(False, "resgatar o proprio codigo tem de ser recusado")
except AL.LinkError as e:
    chk(e.reason == "link_same_account", "o proprio codigo -> link_same_account")

# ── Gerar outro invalida o anterior ──────────────────────────────────────
code5, _ = asyncio.run(AL.issue_link_code(TG))
code6, _ = asyncio.run(AL.issue_link_code(TG))
chk(code5 != code6, "um codigo novo e mesmo novo")
chk(asyncio.run(AL.peek_link_code(code5)) is None,
    "gerar outro MATA o anterior (dois codigos vivos = a pessoa nao sabe qual usar)")

# ── Lixo ─────────────────────────────────────────────────────────────────
for lixo in ("", "abc", None, "!!!!!!!!", "A" * 40):
    chk(asyncio.run(AL.peek_link_code(lixo)) is None, "lixo recusado (%r)" % lixo)

# ── O mascaramento: reconhecivel, nunca copiavel ─────────────────────────
chk(AL._mask_email("fulano@gmail.com").endswith("@gmail.com"),
    "o dominio fica visivel (e por ele que a pessoa reconhece a conta)")
chk("fulano" not in AL._mask_email("fulano@gmail.com"),
    "⚠️ mas o utilizador do e-mail NAO fica legivel")
chk(AL._mask_uid("1234567890") == "\u20267890", "o uid so mostra os ultimos 4")

# ── O contrato dos endpoints ─────────────────────────────────────────────
for rota in ("account/status", "account/link_code", "account/redeem"):
    chk('"/api/miniapp/%s"' % rota in ws_src, "a rota %s esta registada" % rota)
chk("revoke_all_for_player" in ws_src.split("async def api_account_redeem", 1)[1][:2200],
    "⚠️ o resgate REVOGA as sessoes — a identidade mudou de dono, o login tem de refazer")

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 10. 門 As portas: quais estao abertas, e num sitio so' ===")
#
# O owner desligou o Apple no Firebase a 2026-09-15 ("SO GOOGLE MSM"). Um
# botao que o provider recusa nao e' um botao — e' um beco (Lei §1).
#
# ⚠️ MEDIDO ANTES de fechar (`tools/db_readonly_apple_0915.py`, control db):
#     Telegram 254 pessoas · Google 4 · e-mail 1 · **Apple 0**.
# Zero pessoas trancadas. Esta guarda existe para que a PROXIMA porta a
# fechar-se passe pela mesma pergunta antes, e nao depois.
_portas = re.search(r"var PORTAS = \{([^}]*)\}", page)
chk(_portas is not None, "existe UMA tabela de portas (`var PORTAS`)")
_pt_txt = _portas.group(1) if _portas else ""
chk("apple: false" in _pt_txt, "a porta APPLE esta' fechada (ordem do owner)")
chk("google: true" in _pt_txt, "a porta GOOGLE continua aberta (os 4 entram)")
chk("email: true" in _pt_txt, "a porta E-MAIL continua aberta (o 1 entra)")

# ⚠️ A tabela tem de ser declarada ANTES do primeiro uso. `var` sobe, a
# ATRIBUICAO nao: com o bloco mais abaixo (foi onde nasceu), o
# `if (PORTAS.apple)` da linha do i18n corria com `undefined` e a porta
# inteira rebentava com TypeError — a pagina de entrada em branco.
_decl = page.find("var PORTAS =")
_usos = [m.start() for m in re.finditer(r"PORTAS\.", page)]
chk(bool(_usos), "ANTI-GUARDA: ha' usos de `PORTAS.` para ordenar")
chk(_decl > 0 and all(u > _decl for u in _usos),
    "a tabela e' declarada ANTES de todo uso (var sobe, a atribuicao nao)")

# A porta fechada SAI do ecra. Um botao cinzento ainda promete o que nao ha'.
chk("el.remove()" in page,
    "a porta fechada e' REMOVIDA do DOM, nao apenas desactivada")
# e nenhum caminho da Apple corre sem passar pela tabela
_seg_ap = page.split('OAuthProvider("apple.com")')
chk(len(_seg_ap) == 2, "ANTI-GUARDA: o caminho da Apple ainda existe no ficheiro")
chk("if (PORTAS.apple) {" in _seg_ap[0][-400:],
    "o listener da Apple so' se liga com a porta ABERTA")
chk("if (PORTAS.apple) put(\"s-apple\"" in page,
    "a string da Apple so' se escreve com a porta ABERTA")
# e o `setBusy` deixou de assumir que os tres botoes existem
_seg_busy = page.split("function setBusy", 1)[1][:400]
chk("if (el)" in _seg_busy,
    "o `setBusy` tolera um botao que ja' nao esta' no DOM")


print("\n" + "=" * 62)
print("  %d asserts verdes, %d vermelhos" % (_ok, len(_bad)))
if _bad:
    print("\n  VERMELHOS:")
    for m in _bad:
        print("   x " + m)
print("=" * 62)
sys.exit(1 if _bad else 0)
