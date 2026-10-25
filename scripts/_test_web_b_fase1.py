# -*- coding: utf-8 -*-
"""WEB-B Fase 1 (2026-08-21) — a identidade do jogador deixa de ser o Telegram.

Roda: python -X utf8 scripts/_test_web_b_fase1.py

O que este teste protege, por ordem de gravidade:

  1. **O ASSERT Nº 1: quem joga hoje pelo Telegram entra byte-idêntico.** O ramo
     do `init_data` não muda uma linha. Aqui isso é medido no código (o validador
     antigo intocado) E no comportamento (com `init_data` válido, o cookie nunca
     é sequer lido).
  2. **O COOKIE SOZINHO NÃO AUTENTICA.** É a primeira credencial persistente do
     projeto, com 248 pessoas e compras reais atrás. Sem o header
     `X-Nivrael-Session` a resposta é 401 — é isso que mata CSRF por construção.
  3. **REVOGAÇÃO REAL.** Uma sessão revogada morre no pedido SEGUINTE, sem cache
     e sem esperar pela expiração. Sem isto, um cookie roubado é eterno.
  4. **Os dois validadores HMAC** — e o facto de a CHAVE ser diferente. O do
     widget usa `SHA256(token)`; o do initData usa `HMAC(b"WebAppData", token)`.
     Um payload de widget assinado com a chave errada tem de ser recusado.
  5. **A allowlist do `/api/auth/` medida nos DOIS sentidos** (molde do WEB-A):
     uma rota sem declaração, ou uma declaração sem rota, partem o teste.
  6. **O backfill é idempotente** — e produz UMA identidade por PESSOA, não uma
     por personagem. Foi a medição (main∩s2 = 15) que decidiu a arquitectura.
  7. **A vitrine continua pública e o jogo continua fechado** (não-regressão do
     WEB-A e do middleware).
  8. **Lei §1 na porta**: a página de login tem sempre saída, mesmo quando o
     widget do Telegram não nasce, e um `next` de outro site não é seguido.
  9. **i18n**: paridade nas 3 línguas, PT-BR sem grafia europeia, e nenhuma key
     enviada que a página não leia (nem lida que não seja enviada).
 10. **§6 — o que fica INTERDITO dizer**: na Fase 1 não se promete jogar SEM
     Telegram (só sem o ABRIR), e não se promete data nenhuma.

⚠️ SOBRE O ARMAZÉM FALSO. Não há Postgres nesta máquina. Em vez de um mock que
diz "sim" a tudo (o anti-padrão que já deu verde a ramos mortos neste projeto),
o `_FakeControl` abaixo implementa as DEZ instruções SQL que o `web_session`
emite, com as restrições a sério (`UNIQUE (provider, provider_uid)`, `PK (sid)`).
**Uma instrução que ele não reconheça levanta.** Logo, mudar a SQL do módulo sem
mudar o teste dá VERMELHO em vez de um verde falso.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import os
import re
import sys
import time
import types
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Molde _test_web_a_vitrine: alguns engines re-exportam core.utils, que importa
# `telegram`. Stub mínimo — este teste não fala com a rede do bot.
if "telegram" not in sys.modules:
    _tg = types.ModuleType("telegram")
    _tg.Update = object
    _errmod = types.ModuleType("telegram.error")

    class _TgErr(Exception):
        retry_after = 0

    _errmod.RetryAfter = _errmod.TimedOut = _errmod.NetworkError = _errmod.BadRequest = _TgErr
    _tg.error = _errmod
    sys.modules["telegram"] = _tg
    sys.modules["telegram.error"] = _errmod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Token de teste. NUNCA o do bot: assinar payloads exige a metade secreta, e um
# teste que precise do token real não corre em máquina nenhuma sem produção.
TEST_TOKEN = "1234567:AAH-test-token-not-real-abcdefghijklmno"
os.environ["BOT_TOKEN"] = TEST_TOKEN
os.environ["SESSION_SECRET"] = "segredo-de-teste-web-b-fase-1"
os.environ["NIVRAEL_COOKIE_INSECURE"] = "1"  # o TestClient fala http

OK = 0
FAIL: list[str] = []


def chk(cond: bool, label: str) -> bool:
    global OK
    if cond:
        OK += 1
        print("  ok  " + label)
    else:
        FAIL.append(label)
        print("  XX  " + label)
    return bool(cond)


def rd(rel: str) -> str:
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


# ══════════════════════════════════════════════════════════════════════════
# O armazém falso do plano de controlo
# ══════════════════════════════════════════════════════════════════════════
def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", str(sql)).strip()


class _Rows:
    def __init__(self, rows): self._rows = list(rows)
    def first(self): return self._rows[0] if self._rows else None
    def all(self): return list(self._rows)
    def scalars(self): return _Scalars(self._rows)


class _Scalars:
    def __init__(self, rows): self._rows = list(rows)
    def all(self): return [r[0] if isinstance(r, (tuple, list)) else r for r in self._rows]


class _FakeControl:
    """O plano de controlo em memória. Fala as MESMAS instruções, com as MESMAS
    restrições. Uma instrução desconhecida levanta — de propósito."""

    def __init__(self):
        self.identities: list[dict] = []   # UNIQUE (provider, provider_uid)
        self.sessions: dict[str, dict] = {}  # PK (sid)
        self._next_identity_id = 1
        self.seen_sql: list[str] = []

    # ── sessionmaker protocol ────────────────────────────────────────────
    def __call__(self): return _FakeSession(self)


class _FakeSession:
    def __init__(self, store: _FakeControl): self.store = store
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def commit(self): return None
    async def rollback(self): return None

    async def execute(self, stmt, params=None):
        sql = _norm(getattr(stmt, "text", stmt))
        p = dict(params or {})
        st = self.store
        st.seen_sql.append(sql)
        now = datetime.now(timezone.utc)

        # 1. link_identity — upsert com RETURNING
        if sql.startswith("INSERT INTO auth_identities (player_id, provider, provider_uid, profile, last_login_at)"):
            hit = next((r for r in st.identities
                        if r["provider"] == p["prov"] and r["provider_uid"] == p["uid"]), None)
            if hit is None:
                hit = {"id": st._next_identity_id, "player_id": int(p["pid"]),
                       "provider": p["prov"], "provider_uid": p["uid"],
                       "profile": p["prof"], "created_at": now, "last_login_at": now}
                st._next_identity_id += 1
                st.identities.append(hit)
            else:
                # ⚠️ O `player_id` GUARDADO ganha — nunca o do argumento.
                hit["last_login_at"] = now
                hit["profile"] = p["prof"]
            return _Rows([(hit["id"], hit["player_id"])])

        # 2. backfill em lote
        if sql.startswith("INSERT INTO auth_identities (player_id, provider, provider_uid) VALUES"):
            # O backfill manda DOIS parametros por linha: `:pN` (BIGINT) e
            # `:uN` (TEXT). Reusar UM para as duas colunas era o bug que rebentou
            # em producao (`text versus bigint`) e que ESTE falso deixou passar.
            n = sum(1 for k in p if k.startswith("p"))
            out = []
            for i in range(n):
                pid_raw, uid_raw = p["p%d" % i], p["u%d" % i]
                # O falso passa a EXIGIR os tipos que o Postgres deduziria. Sem
                # isto ele volta a ser mais gentil que a base — que foi
                # exactamente como o bug chegou a producao com 188 asserts verdes.
                if not isinstance(pid_raw, int):
                    raise AssertionError(
                        "player_id tem de chegar como int (BIGINT), veio %r" % type(pid_raw))
                if not isinstance(uid_raw, str):
                    raise AssertionError(
                        "provider_uid tem de chegar como str (TEXT), veio %r" % type(uid_raw))
                pid = int(pid_raw)
                if any(r["provider"] == "telegram" and r["provider_uid"] == uid_raw
                       for r in st.identities):
                    continue  # ON CONFLICT DO NOTHING
                row = {"id": st._next_identity_id, "player_id": pid, "provider": "telegram",
                       "provider_uid": uid_raw, "profile": "{}", "created_at": now,
                       "last_login_at": None}
                st._next_identity_id += 1
                st.identities.append(row)
                out.append((row["id"],))
            return _Rows(out)

        # 3. find_identity
        if sql.startswith("SELECT id, player_id FROM auth_identities"):
            hit = next((r for r in st.identities
                        if r["provider"] == p["prov"] and r["provider_uid"] == p["uid"]), None)
            return _Rows([(hit["id"], hit["player_id"])] if hit else [])

        # 4. issue_session
        if sql.startswith("INSERT INTO auth_sessions"):
            assert p["sid"] not in st.sessions, "PK (sid) violada"
            st.sessions[p["sid"]] = {
                "sid": p["sid"], "player_id": int(p["pid"]), "identity_id": p["iid"],
                "provider": p["prov"], "csrf": p["csrf"], "tg_user": p["tgu"],
                "created_at": now, "last_seen_at": now, "expires_at": p["exp"],
                "revoked_at": None,
            }
            return _Rows([])

        # 5. limpeza oportunista
        if sql.startswith("DELETE FROM auth_sessions WHERE expires_at <"):
            cut = now - timedelta(days=7)
            for sid in [k for k, v in st.sessions.items() if v["expires_at"] < cut]:
                st.sessions.pop(sid, None)
            return _Rows([])

        # 6. verify_session
        if sql.startswith("SELECT sid, player_id, identity_id, provider, csrf, tg_user"):
            r = st.sessions.get(p["sid"])
            if r is None:
                return _Rows([])
            return _Rows([(r["sid"], r["player_id"], r["identity_id"], r["provider"],
                           r["csrf"], r["tg_user"], r["created_at"], r["last_seen_at"],
                           r["expires_at"], r["revoked_at"])])

        # 7/8. renovação deslizante
        if sql.startswith("UPDATE auth_sessions SET last_seen_at = :now, expires_at = :exp"):
            r = st.sessions.get(p["sid"])
            if r is not None and r["revoked_at"] is None:
                r["last_seen_at"] = p["now"]
                r["expires_at"] = p["exp"]
            return _Rows([])
        if sql.startswith("UPDATE auth_sessions SET last_seen_at = :now WHERE sid"):
            r = st.sessions.get(p["sid"])
            if r is not None:
                r["last_seen_at"] = p["now"]
            return _Rows([])

        # 9. revoke_session
        if sql.startswith("UPDATE auth_sessions SET revoked_at = now() WHERE sid"):
            r = st.sessions.get(p["sid"])
            if r is not None and r["revoked_at"] is None:
                r["revoked_at"] = now
            return _Rows([])

        # 10. revoke_all_for_player
        if sql.startswith("UPDATE auth_sessions SET revoked_at = now() WHERE player_id"):
            out = []
            for r in st.sessions.values():
                if r["player_id"] == int(p["pid"]) and r["revoked_at"] is None:
                    r["revoked_at"] = now
                    out.append((r["sid"],))
            return _Rows(out)

        raise AssertionError(
            "SQL não reconhecida pelo armazém falso — o teste NÃO pode dar verde "
            "a uma instrução que nunca correu:\n  " + sql)


STORE = _FakeControl()
import core.web_session as WS  # noqa: E402
WS._sm = lambda: STORE


# ══════════════════════════════════════════════════════════════════════════
print("\n=== 1. Os DOIS validadores HMAC (e as chaves são DIFERENTES) ===")
from core.telegram_auth import (  # noqa: E402
    InitDataError, LOGIN_WIDGET_MAX_AGE_SECONDS, validate_init_data,
    validate_login_widget,
)


def sign_widget(fields: dict, token: str = TEST_TOKEN) -> dict:
    data = {k: str(v) for k, v in fields.items()}
    dcs = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hashlib.sha256(token.encode()).digest()
    data["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return data


def sign_initdata(user: dict, auth_date: int, token: str = TEST_TOKEN) -> str:
    from urllib.parse import urlencode
    fields = {"user": json.dumps(user, separators=(",", ":")), "auth_date": str(auth_date)}
    dcs = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


now_ts = int(time.time())

# válido
got = validate_login_widget(sign_widget({"id": 4242, "first_name": "Lin", "auth_date": now_ts}), TEST_TOKEN)
chk(got["id"] == 4242 and got["first_name"] == "Lin", "widget válido passa e devolve o id como int")

# expirado
try:
    validate_login_widget(sign_widget({"id": 1, "auth_date": now_ts - (LOGIN_WIDGET_MAX_AGE_SECONDS + 60)}), TEST_TOKEN)
    chk(False, "widget expirado recusado")
except InitDataError:
    chk(True, "widget expirado recusado")

# forjado (hash mexido)
bad = sign_widget({"id": 1, "auth_date": now_ts})
bad["hash"] = ("0" * 64) if bad["hash"][0] != "0" else ("1" * 64)
try:
    validate_login_widget(bad, TEST_TOKEN)
    chk(False, "widget com hash forjado recusado")
except InitDataError:
    chk(True, "widget com hash forjado recusado")

# campo mexido depois de assinar
tampered = sign_widget({"id": 1, "auth_date": now_ts})
tampered["id"] = "999999"
try:
    validate_login_widget(tampered, TEST_TOKEN)
    chk(False, "widget com `id` trocado depois de assinar é recusado")
except InitDataError:
    chk(True, "widget com `id` trocado depois de assinar é recusado")

# sem hash
try:
    validate_login_widget({"id": 1, "auth_date": now_ts}, TEST_TOKEN)
    chk(False, "widget sem hash recusado")
except InitDataError:
    chk(True, "widget sem hash recusado")

# id negativo — é o espaço da Fase 2 (contas sem Telegram)
try:
    validate_login_widget(sign_widget({"id": -5, "auth_date": now_ts}), TEST_TOKEN)
    chk(False, "widget com id negativo recusado (é o espaço da F2)")
except InitDataError:
    chk(True, "widget com id negativo recusado (é o espaço da F2)")

# ⚠️ A PROVA de que a chave é outra: assinar com a chave do initData e falhar.
wrong_key = {k: str(v) for k, v in {"id": 7, "auth_date": now_ts}.items()}
dcs = "\n".join(f"{k}={wrong_key[k]}" for k in sorted(wrong_key))
wrong_key["hash"] = hmac.new(
    hmac.new(b"WebAppData", TEST_TOKEN.encode(), hashlib.sha256).digest(),
    dcs.encode(), hashlib.sha256).hexdigest()
try:
    validate_login_widget(wrong_key, TEST_TOKEN)
    chk(False, "payload assinado com a chave do WebApp NÃO passa no widget")
except InitDataError:
    chk(True, "payload assinado com a chave do WebApp NÃO passa no widget")

# ... e o simétrico: o validador ANTIGO continua exactamente como estava.
ok_init = sign_initdata({"id": 555, "first_name": "Wu"}, now_ts)
chk(validate_init_data(ok_init, TEST_TOKEN)["user"]["id"] == 555,
    "o validador do initData continua a aceitar o que sempre aceitou")
try:
    validate_init_data(sign_initdata({"id": 555}, now_ts - 7 * 3600), TEST_TOKEN)
    chk(False, "initData fora da janela de 6h continua recusado")
except InitDataError:
    chk(True, "initData fora da janela de 6h continua recusado")

chk(LOGIN_WIDGET_MAX_AGE_SECONDS <= 15 * 60,
    "a janela do widget é CURTA (%ds) — ele não é reemitido como o initData"
    % LOGIN_WIDGET_MAX_AGE_SECONDS)


# ══════════════════════════════════════════════════════════════════════════
print("\n=== 2. O cookie: assinado, opaco, e inútil sem o header ===")


async def _session_suite():
    res: list[tuple[bool, str]] = []
    cookie, csrf, exp = await WS.issue_session(4242, "telegram", 1, {"first_name": "Lin"})

    res.append((cookie.count(".") == 3, "o cookie tem forma `ver.sid.exp.mac` (%r)" % cookie[:24]))
    res.append((len(csrf) >= 20, "o csrf é longo (%d chars)" % len(csrf)))
    res.append((csrf not in cookie, "o csrf NÃO viaja dentro do cookie de sessão"))

    good = await WS.verify_session(cookie, csrf)
    res.append((good is not None and good.player_id == 4242, "cookie + header correcto → sessão"))
    res.append((good is not None and good.tg_user.get("first_name") == "Lin",
                "o snapshot do Telegram sobrevive (é o que o world/start lê)"))

    res.append((await WS.verify_session(cookie, "") is None,
                "⚠️ COOKIE SOZINHO (sem header) → recusado — é o anti-CSRF inteiro"))
    res.append((await WS.verify_session(cookie, "csrf-errado") is None,
                "header errado → recusado"))
    res.append((await WS.verify_session("", csrf) is None, "sem cookie → recusado"))

    # assinatura mexida
    parts = cookie.split(".")
    tampered = ".".join(parts[:3] + [("0" * 32) if parts[3][0] != "0" else ("1" * 32)])
    res.append((await WS.verify_session(tampered, csrf) is None, "mac mexido → recusado"))
    # sid trocado por outro sid válido de outra sessão? (mac deixa de bater)
    swapped = ".".join([parts[0], "sid-inventado", parts[2], parts[3]])
    res.append((await WS.verify_session(swapped, csrf) is None, "sid trocado → recusado"))
    # prolongar o exp à mão não funciona (entra no mac)
    longer = ".".join([parts[0], parts[1], str(int(parts[2]) + 999999), parts[3]])
    res.append((await WS.verify_session(longer, csrf) is None,
                "esticar o `exp` do cookie à mão → recusado"))

    # ── REVOGAÇÃO REAL ────────────────────────────────────────────────────
    res.append((await WS.revoke_session(cookie) is True, "revoke_session devolve True"))
    res.append((await WS.verify_session(cookie, csrf) is None,
                "⚠️ sessão REVOGADA → recusada no pedido seguinte (sem cache)"))

    # revogar todas
    c1, x1, _ = await WS.issue_session(777, "telegram", 2, {})
    c2, x2, _ = await WS.issue_session(777, "telegram", 2, {})
    c3, x3, _ = await WS.issue_session(888, "telegram", 3, {})
    n = await WS.revoke_all_for_player(777)
    res.append((n == 2, "revoke_all_for_player revogou as 2 sessões dele (veio %d)" % n))
    res.append((await WS.verify_session(c1, x1) is None and await WS.verify_session(c2, x2) is None,
                "as duas sessões do jogador morreram"))
    res.append((await WS.verify_session(c3, x3) is not None,
                "a sessão de OUTRO jogador não foi tocada"))

    # expiração do lado do servidor manda, mesmo com o cookie a dizer o contrário
    c4, x4, _ = await WS.issue_session(999, "telegram", 4, {})
    sid4 = c4.split(".")[1]
    STORE.sessions[sid4]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    res.append((await WS.verify_session(c4, x4) is None,
                "a BASE manda na expiração, não o cookie"))

    # tecto absoluto
    c5, x5, _ = await WS.issue_session(1000, "telegram", 5, {})
    sid5 = c5.split(".")[1]
    STORE.sessions[sid5]["created_at"] = datetime.now(timezone.utc) - timedelta(
        seconds=WS.SESSION_ABSOLUTE_MAX_SECONDS + 60)
    res.append((await WS.verify_session(c5, x5) is None,
                "o tecto absoluto mata a sessão por muito que ela deslize"))

    # renovação deslizante: só depois da trava, e nunca a cada pedido
    c6, x6, _ = await WS.issue_session(1001, "telegram", 6, {})
    s6 = await WS.verify_session(c6, x6)
    res.append((s6 is not None and s6.refreshed_cookie is None,
                "um pedido logo a seguir NÃO reescreve o cookie (trava de escrita)"))
    sid6 = c6.split(".")[1]
    STORE.sessions[sid6]["last_seen_at"] = datetime.now(timezone.utc) - timedelta(
        seconds=WS.SESSION_RENEW_AFTER_SECONDS + 60)
    STORE.sessions[sid6]["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=60)
    s6b = await WS.verify_session(c6, x6)
    res.append((s6b is not None and s6b.refreshed_cookie is not None,
                "passada a trava, a janela desliza e o cookie é reescrito"))
    res.append((s6b is not None and await WS.verify_session(s6b.refreshed_cookie, x6) is not None,
                "o cookie renovado continua a autenticar"))

    # ── identidades ──────────────────────────────────────────────────────
    a = await WS.link_identity("telegram", "4242", 4242, {"first_name": "Lin"})
    b = await WS.link_identity("telegram", "4242", 999999, {"first_name": "Lin"})
    res.append((a is not None and b is not None and a[1] == b[1] == 4242,
                "⚠️ um login NUNCA re-aponta a identidade para outro personagem"))
    res.append((a[0] == b[0], "a mesma identidade é a mesma linha (UNIQUE)"))
    found = await WS.find_identity("telegram", "4242")
    res.append((found == a, "find_identity encontra o que link_identity criou"))
    res.append((await WS.find_identity("email", "ninguem@exemplo.com") is None,
                "a Fase 2 já pode procurar por `email` — e hoje não encontra nada"))
    return res


for cond, label in asyncio.run(_session_suite()):
    chk(cond, label)


# ══════════════════════════════════════════════════════════════════════════
print("\n=== 3. O backfill: idempotente, e UMA identidade por PESSOA ===")
# A medição que decidiu a arquitectura: main=240, s2=23, INTERSECÇÃO=15 ⇒ 248
# pessoas. Aqui reproduz-se essa forma em miniatura: 3 ids no `main`, 3 no `s2`,
# 2 partilhados ⇒ 4 identidades, não 6.
import database.control_db as CDB  # noqa: E402
import database.db as DB  # noqa: E402

WORLD_PLAYERS = {"main": [11, 12, 13], "s2": [12, 13, 14]}


WORLDS_TOUCHED: list[str] = []


class _FakeGameSession:
    def __init__(self, key):
        self.key = key
        WORLDS_TOUCHED.append(key)
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def execute(self, stmt, params=None):
        sql = _norm(getattr(stmt, "text", stmt))
        assert sql.startswith("SELECT telegram_id FROM players WHERE telegram_id > 0"), sql
        return _Rows([(i,) for i in WORLD_PLAYERS[self.key]])


class _Ctx:
    def __init__(self, key): self.key = key
    def __enter__(self):
        global _CUR
        _CUR = self.key
        return self
    def __exit__(self, *a): return False


_CUR = "main"
# ⚠️ `backfill_telegram_identities` importa `database.db` POR DENTRO da função.
# Remendar `control_db.*` não teria efeito nenhum — e a primeira versão deste
# teste, por causa disso, foi buscar os 240 jogadores REAIS à produção. Os
# remendos têm de ser no módulo de onde o import vem.
DB.get_session_factory = lambda: (lambda: _FakeGameSession(_CUR))
DB.iter_world_keys = lambda: ["main", "s2"]
DB.use_world = _Ctx
CDB._ensure_control_engine = lambda: STORE

# limpar as identidades sintéticas dos testes acima para medir só o backfill
STORE.identities = [r for r in STORE.identities if int(r["player_id"]) not in (11, 12, 13, 14)]
_pre = len(STORE.identities)

n1 = asyncio.run(CDB.backfill_telegram_identities())
n2 = asyncio.run(CDB.backfill_telegram_identities())
chk(sorted(set(WORLDS_TOUCHED)) == ["main", "s2"],
    "o backfill varreu os DOIS mundos (veio %s) — e nenhum foi a produção"
    % sorted(set(WORLDS_TOUCHED)))
chk(n1 == 4, "1ª corrida ligou 4 identidades para 6 personagens em 2 mundos (veio %d)" % n1)
chk(n2 == 0, "⚠️ 2ª corrida = 0 — o backfill é idempotente (veio %d)" % n2)
created = [r for r in STORE.identities if int(r["player_id"]) in (11, 12, 13, 14)]
chk(len(created) == 4, "ficaram exactamente 4 linhas (uma por PESSOA)")
chk(sorted(int(r["player_id"]) for r in created) == [11, 12, 13, 14],
    "as 2 pessoas com personagem nos dois mundos têm UMA linha cada")
chk(all(r["provider"] == "telegram" and r["provider_uid"] == str(r["player_id"]) for r in created),
    "o provider é `telegram` e o uid é o id em TEXTO (o email não é número)")
chk(len(STORE.identities) == _pre + 4, "o backfill não tocou nas identidades que já existiam")


# ══════════════════════════════════════════════════════════════════════════
print("\n=== 4. A allowlist do /api/auth/, nos DOIS sentidos (molde do WEB-A) ===")
import core.webserver as W  # noqa: E402

app = W.create_app()
registered = sorted({
    r.resource.canonical for r in app.router.routes()
    if getattr(r, "resource", None) is not None
    and str(r.resource.canonical).startswith("/api/auth/")
})
chk(registered == sorted(W.AUTH_PUBLIC_PATHS),
    "rotas /api/auth/* == AUTH_PUBLIC_PATHS (%s)" % registered)
chk(all(p.startswith("/api/auth/") for p in W.AUTH_PUBLIC_PATHS),
    "nenhum caminho da porta fora do prefixo /api/auth/")
chk(not (set(W.AUTH_PUBLIC_PATHS) & set(W.VITRINE_PUBLIC_PATHS)),
    "as duas allowlists públicas não se cruzam")
chk(not any(p.startswith("/api/miniapp/") for p in W.AUTH_PUBLIC_PATHS),
    "NENHUM /api/miniapp/* na allowlist da porta")
# a vitrine não regride
registered_vit = sorted({
    r.resource.canonical for r in app.router.routes()
    if getattr(r, "resource", None) is not None
    and str(r.resource.canonical).startswith("/api/vitrine/")
})
chk(registered_vit == sorted(W.VITRINE_PUBLIC_PATHS),
    "WEB-A intacto: rotas /api/vitrine/* == VITRINE_PUBLIC_PATHS")


# ══════════════════════════════════════════════════════════════════════════
print("\n=== 5. O middleware: a ORDEM das credenciais é o contrato ===")
mw = rd("core/webserver.py")
seg = mw.split("async def auth_middleware", 1)[1].split("\ndef _refresh_session_cookies", 1)[0]
i_auth = seg.find('path.startswith("/api/auth/")')
i_vit = seg.find('path.startswith("/api/vitrine/")')
i_mini = seg.find('path.startswith("/api/miniapp/")')
i_init = seg.find("validate_init_data(init_data, bot_token)")
i_sess = seg.find("verify_request_session(request)")
i_401 = seg.find('return _err("unauthorized", 401)')
chk(0 < i_auth and 0 < i_vit and i_auth < i_mini and i_vit < i_mini,
    "as duas portas públicas são decididas ANTES do /api/miniapp/")
chk(0 < i_init < i_sess, "⚠️ o init_data é tentado ANTES do cookie (ramo 1 ganha sempre)")
chk(i_sess < i_401, "o 401 só acontece depois de as DUAS credenciais falharem")
chk("_rate_allow(user_id)" in seg and seg.find("_rate_allow(user_id)") > i_sess,
    "o limitador por user_id continua DEPOIS de resolvida a identidade")
chk("_auth_ip_buckets" in seg, "a porta tem balde de IP próprio (não gasta o da vitrine)")
chk("request[\"user_id\"] = None" in seg, "a porta declara user_id=None explicitamente")

# O validador antigo continua palavra por palavra onde estava.
ta = rd("core/telegram_auth.py")
chk('hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256)' in ta,
    "a chave do initData continua HMAC(b\"WebAppData\", token)")
chk("hashlib.sha256(bot_token.encode(\"utf-8\")).digest()" in ta,
    "a chave do widget é SHA256(token) — é OUTRA função, não um parâmetro")
chk(ta.count("def validate_init_data") == 1 and ta.count("def validate_login_widget") == 1,
    "são dois validadores distintos, não um com `if`")

ws_src = rd("core/web_session.py")
chk("compare_digest" in ws_src, "as comparações de segredo são compare_digest")
chk("httponly=True" in ws_src and 'samesite="Lax"' in ws_src,
    "o cookie de sessão é HttpOnly + SameSite=Lax")
chk("def cookie_secure" in ws_src and "NIVRAEL_COOKIE_INSECURE" in ws_src,
    "`Secure` é o default e desligá-lo exige dizê-lo em voz alta")
chk("init_data" not in ws_src.replace("`init_data`", ""),
    "a sessão NUNCA guarda o init_data")
for forbidden in ("hash", "password", "senha"):
    body = ws_src.split('"""', 2)[-1]  # sem o docstring do módulo
    chk(("%s=" % forbidden) not in body and ("'%s'" % forbidden) not in body,
        "a sessão não guarda `%s`" % forbidden)


# ══════════════════════════════════════════════════════════════════════════
print("\n=== 6. O servidor HTTP: as 4 portas, medidas ===")
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
from aiohttp import web as _web  # noqa: E402

import database.control_db as _CDB2  # noqa: E402


async def _fake_resolve(tid):
    return "main"


_CDB2.resolve_active_world = _fake_resolve


async def _probe(request):
    """Rota só do teste, para medir o MIDDLEWARE e não um handler qualquer.
    Devolve quem o middleware decidiu que somos."""
    return _web.json_response({"ok": True, "user_id": request["user_id"],
                               "tg_user": request.get("tg_user") or {},
                               "world": request.get("world_key")})


async def _http_suite():
    res: list[tuple[bool, str]] = []
    application = W.create_app()
    application.router.add_post("/api/miniapp/__probe", _probe)
    server = TestServer(application)
    client = TestClient(server)
    await client.start_server()
    try:
        XFF = {"X-Forwarded-For": "10.1.0.1"}

        # ── a porta serve HTML e diz o que fazer ──────────────────────────
        # ⚠️ MUDOU a 2026-08-26 (owner): *"as URLs têm que ser em inglês"*. O
        # sinónimo PT deixou de SERVIR a página e passou a 301 para a canónica.
        # O conteúdo do jogo continua nos 3 idiomas — mudou só o endereço.
        for alias in ("/login", "/login/", "/app"):
            r = await client.get(alias)
            res.append((r.status == 200, "%s serve a página (veio %d)" % (alias, r.status)))

        # As legadas NÃO servem: redirecionam. `allow_redirects=False` é
        # obrigatório — sem isso o cliente segue o salto e o teste vê 200,
        # dando verde a um 404 disfarçado.
        for old_url, want in (("/entrar", "/login"), ("/entrar/", "/login"),
                              ("/jogar", "/play"), ("/mundo", "/play"),
                              ("/privacidade", "/privacy"), ("/termos", "/terms")):
            r = await client.get(old_url, allow_redirects=False)
            res.append((r.status == 301,
                        "`%s` sai de circulação por 301, não por 404 (veio %d)"
                        % (old_url, r.status)))
            res.append((r.headers.get("Location") == want,
                        "`%s` aponta para a canónica `%s` (veio %r)"
                        % (old_url, want, r.headers.get("Location"))))

        # ⚠️ Um link que já circulou traz query. Se a redirecção a comesse,
        # "não parte links" seria falso: `/entrar?next=/app` perderia o destino.
        r = await client.get("/entrar?lang=pt&next=/app", allow_redirects=False)
        res.append((r.headers.get("Location") == "/login?lang=pt&next=/app",
                    "a 301 preserva a query do link antigo (veio %r)"
                    % r.headers.get("Location")))

        # E o salto tem de aterrar mesmo — não basta apontar.
        r = await client.get("/entrar?lang=pt")
        res.append((r.status == 200, "seguir a 301 aterra na porta (veio %d)" % r.status))
        a = await (await client.get("/login?lang=pt")).text()
        b = await r.text()
        res.append((a == b, "o link antigo acaba EXACTAMENTE na mesma porta"))
        r = await client.get("/login?lang=en")
        html = await r.text()
        res.append(("{{" not in html, "a porta não deixa placeholders por substituir"))
        res.append(("Enter Nivrael" in html, "`?lang=en` traduz a porta"))
        # ⚠️ 2026-08-26 — o widget do Telegram FOI APOSENTADO. O endpoint
        # `oauth.telegram.org/auth?...&embed=1` devolve literalmente
        # `deprecated`. Estes dois asserts pediam que a porta carregasse um
        # botão que só sabe falhar; agora medem o contrário.
        res.append(("telegram-widget.js" not in html,
                    "a porta NÃO carrega o widget aposentado do Telegram"))
        res.append(("firebasejs" in html,
                    "a porta carrega o SDK do Firebase (Google · Apple · e-mail)"))
        res.append(('"/api/auth/firebase"' in html,
                    "o ID token vai por POST para o nosso endpoint"))
        # O token nunca pode viajar na barra de endereço (fica em histórico,
        # em logs de acesso e no Referer).
        res.append(("id_token=" not in html,
                    "o ID token nunca vai na query string"))
        res.append(('JSON.stringify({ id_token: idToken })' in html,
                    "o ID token vai no CORPO do pedido"))
        # A config do Firebase é injectada pelo servidor — a página não a
        # inventa, e assim um projecto de testes é uma env var, não um edit.
        res.append(("{{FIREBASE}}" not in html and "apiKey" in html,
                    "a config do Firebase é injectada pelo servidor"))
        res.append(("signOut" in html,
                    "a sessão do Firebase é largada depois da troca (a nossa é que manda)"))
        res.append(("/play" in html, "Lei §1: a porta tem sempre uma saída (ver o mundo)"))
        res.append((r.headers.get("X-Frame-Options") == "DENY",
                    "a porta não pode ser posta num iframe de outro site"))
        res.append((r.headers.get("Cache-Control", "").startswith("no-cache"),
                    "a porta nunca é cacheada"))
        r = await client.get("/login?lang=pt")
        res.append(("Entrar em Nivrael" in (await r.text()), "`?lang=pt` traduz a porta"))

        # ── /api/auth/* ───────────────────────────────────────────────────
        r = await client.get("/api/auth/me", headers=XFF)
        j = await r.json()
        res.append((r.status == 200 and j.get("ok") is False,
                    "GET /api/auth/me sem sessão → 200 ok:false (é a resposta certa)"))
        r = await client.post("/api/auth/telegram", json={}, headers=XFF)
        res.append((r.status == 401, "POST /api/auth/telegram vazio → 401 (veio %d)" % r.status))
        forged = sign_widget({"id": 5, "auth_date": now_ts}, token="token-de-outro-bot")
        r = await client.post("/api/auth/telegram", json=forged, headers=XFF)
        res.append((r.status == 401 and (await r.json()).get("reason") == "login_invalid",
                    "payload assinado por OUTRO token → 401 login_invalid"))
        for probe in ("/api/auth/", "/api/auth/session", "/api/auth/admin"):
            r = await client.get(probe, headers=XFF)
            res.append((r.status == 404, "%s fora da lista → 404 (veio %d)" % (probe, r.status)))
        r = await client.request("PUT", "/api/auth/me", headers=XFF)
        res.append((r.status in (404, 405), "método estranho na porta → 405/404 (veio %d)" % r.status))
        r = await client.options("/api/auth/me", headers=XFF)
        res.append((r.status == 204, "OPTIONS na porta → 204 (veio %d)" % r.status))

        # ── LOGIN A SÉRIO, ponta a ponta ─────────────────────────────────
        payload = sign_widget({"id": 4242, "first_name": "Lin", "username": "lin_wx",
                               "auth_date": int(time.time())})
        r = await client.post("/api/auth/telegram", json=payload,
                              headers={"X-Forwarded-For": "10.1.0.2"})
        j = await r.json()
        res.append((r.status == 200 and j.get("ok") is True and j.get("player_id") == 4242,
                    "login com widget válido → sessão para o jogador 4242"))
        set_cookie = r.headers.getall("Set-Cookie", [])
        blob = " | ".join(set_cookie)
        res.append((("nv_session=" in blob) and ("nv_csrf=" in blob),
                    "o login escreve os dois cookies"))
        sess_line = next((c for c in set_cookie if c.startswith("nv_session=")), "")
        res.append(("HttpOnly" in sess_line, "nv_session é HttpOnly (%r)" % sess_line[:40]))
        res.append(("SameSite=Lax" in sess_line, "nv_session é SameSite=Lax"))
        csrf_line = next((c for c in set_cookie if c.startswith("nv_csrf=")), "")
        res.append(("HttpOnly" not in csrf_line,
                    "nv_csrf NÃO é HttpOnly — o JS tem de o ler para montar o header"))
        res.append((j.get("csrf") and j["csrf"] not in sess_line,
                    "o csrf do corpo não é o valor do cookie de sessão"))

        csrf = j["csrf"]
        cookie_val = sess_line.split("nv_session=", 1)[1].split(";", 1)[0]
        COOKIE = {"Cookie": "nv_session=%s; nv_csrf=%s" % (cookie_val, csrf)}

        # ⚠️ 2 — o cookie sozinho não autentica
        r = await client.post("/api/miniapp/__probe", json={}, headers={**COOKIE, **XFF})
        res.append((r.status == 401,
                    "⚠️ COOKIE SEM HEADER em /api/miniapp/* → 401 (veio %d)" % r.status))

        AUTHED = {**COOKIE, "X-Nivrael-Session": csrf, "X-Forwarded-For": "10.1.0.3"}
        r = await client.post("/api/miniapp/__probe", json={}, headers=AUTHED)
        jj = await r.json()
        res.append((r.status == 200 and jj.get("user_id") == 4242,
                    "cookie + header → o middleware resolve o jogador 4242"))
        res.append((jj.get("tg_user", {}).get("first_name") == "Lin",
                    "o `tg_user` chega ao handler (é o que o world/start lê)"))
        res.append((jj.get("world") == "main",
                    "o mundo continua a ser resolvido pelo plano de controlo"))

        # ⚠️ 1 — o Telegram de hoje entra byte-idêntico, e o cookie é irrelevante
        good_init = sign_initdata({"id": 555, "first_name": "Wu"}, int(time.time()))
        r = await client.post("/api/miniapp/__probe", json={"init_data": good_init},
                              headers={"X-Forwarded-For": "10.1.0.4"})
        jj = await r.json()
        res.append((r.status == 200 and jj.get("user_id") == 555,
                    "init_data válido SEM cookie nenhum → entra (byte-idêntico)"))
        # o mesmo pedido, agora com o cookie de OUTRO jogador colado: o initData manda
        r = await client.post("/api/miniapp/__probe", json={"init_data": good_init},
                              headers={**AUTHED, "X-Forwarded-For": "10.1.0.5"})
        jj = await r.json()
        res.append((jj.get("user_id") == 555,
                    "⚠️ com initData válido E cookie de outro, GANHA o initData (veio %s)"
                    % jj.get("user_id")))

        # ⚠️ 3 — revogação através do endpoint
        r = await client.post("/api/auth/logout", json={},
                              headers={**AUTHED, "X-Forwarded-For": "10.1.0.6"})
        res.append((r.status == 200 and (await r.json()).get("revoked") == 1,
                    "logout revoga a sessão"))
        r = await client.post("/api/miniapp/__probe", json={},
                              headers={**AUTHED, "X-Forwarded-For": "10.1.0.7"})
        res.append((r.status == 401,
                    "⚠️ depois do logout, o MESMO par cookie+header → 401 (veio %d)" % r.status))
        r = await client.get("/api/auth/me", headers={**AUTHED, "X-Forwarded-For": "10.1.0.8"})
        res.append(((await r.json()).get("ok") is False, "/api/auth/me confirma que já não há sessão"))

        # ── não-regressão: a vitrine e o jogo ────────────────────────────
        r = await client.get("/api/vitrine/world", headers={"X-Forwarded-For": "10.2.0.1"})
        res.append((r.status == 200, "WEB-A: /api/vitrine/world continua público (veio %d)" % r.status))
        for probe in ("/api/miniapp/player", "/api/miniapp/leaderboard",
                      "/api/miniapp/admin/servers"):
            r = await client.post(probe, json={"init_data": ""},
                                  headers={"X-Forwarded-For": "10.2.0.2"})
            res.append((r.status == 401, "%s sem nada → 401 (veio %d)" % (probe, r.status)))
        r = await client.post("/api/miniapp/player", json={"init_data": "lixo=1&hash=ff"},
                              headers={"X-Forwarded-For": "10.2.0.3"})
        res.append((r.status == 401, "initData forjado → 401 (veio %d)" % r.status))

        # limitação por IP na porta, e no balde PRÓPRIO
        ip = "203.0.113.90"
        codes = []
        for _ in range(14):
            rr = await client.get("/api/auth/me", headers={"X-Forwarded-For": ip})
            codes.append(rr.status)
        res.append((429 in codes, "IP a martelar a porta leva 429 (últimos %s)" % codes[-3:]))
        rr = await client.get("/api/vitrine/world", headers={"X-Forwarded-For": ip})
        res.append((rr.status == 200,
                    "⚠️ e a vitrine NÃO foi castigada pelo mesmo IP (veio %d)" % rr.status))

        # ── PERF 2026-08-25 — o servidor comprime o TEXTO (report do owner:
        # "o site demora MUITO no telefone"). Até aqui não comprimia NADA:
        # o cliente do jogo saía com 1.569 KB onde 314 KB chegam.
        async def _both(pth):
            a = await client.get(pth, headers={"Accept-Encoding": "identity"},
                                 auto_decompress=False)
            b = await client.get(pth, headers={"Accept-Encoding": "gzip"},
                                 auto_decompress=False)
            return (a.status, len(await a.read()), len(await b.read()),
                    b.headers.get("Content-Encoding"))

        for pth, label in (("/miniapp/components/tabs.js", "o cliente do jogo"),
                           ("/miniapp/i18n/pt.json", "as strings"),
                           ("/login", "a porta"),
                           ("/play", "a vitrine")):
            st, raw, gz, enc = await _both(pth)
            if st != 200:
                res.append((False, "%s serve 200 (veio %d)" % (label, st)))
                continue
            res.append((enc is not None and gz < raw,
                        "%s comprime: %.0f KB -> %.0f KB (%s)" % (label, raw/1024, gz/1024, enc)))

        # ⚠️ E o que JÁ vem comprimido não é comprimido outra vez: gastar CPU
        # num WebP para 0% de ganho é pior que não fazer nada.
        st, raw, gz, enc = await _both("/hero-bg.webp")
        if st == 200:
            res.append((enc is None and raw == gz,
                        "imagem NÃO é recomprimida (%.0f KB, enc=%r)" % (raw/1024, enc)))

        # o ContextVar não vaza
        from database.db import current_world_key
        res.append((current_world_key() == "main",
                    "o mundo não vaza depois do pedido (veio %r)" % current_world_key()))
    finally:
        await client.close()
    return res


for cond, label in asyncio.run(_http_suite()):
    chk(cond, label)


# ══════════════════════════════════════════════════════════════════════════
print("\n=== 7. O cliente: o mesmo mini-app nas duas superfícies ===")
ui = rd("miniapp/components/ui.js")
tabs = rd("miniapp/components/tabs.js")

chk('headers[CSRF_HEADER] = csrf' in ui, "o api() põe o header CSRF fora do Telegram")
chk('opts.credentials = "include"' in ui, "o api() manda o cookie fora do Telegram")
seg_api = ui.split("async function api(", 1)[1].split("\n    function useApi", 1)[0]
chk("if (!initData) {" in seg_api,
    "⚠️ o caminho novo só existe quando NÃO há initData (inerte no Telegram)")
chk("res.status === 401 && !initData" in seg_api,
    "Lei §1: sem sessão o jogador vai para a porta, não para um ecrã de erro")
chk('var LOGIN_URL = "/login";' in ui,
    "a porta para onde o cliente manda um 401 é a CANÓNICA `/login`")
chk("openPaymentLink" in ui, "existe um único sítio que abre pagamentos")
chk(ui.count("tg.openInvoice(") == 1,
    "o `openInvoice` do SDK aparece UMA vez no projeto (dentro do helper)")
chk("shop_invoice_popup_blocked" in ui and "shop_invoice_external" in ui,
    "Lei §1: pop-up bloqueado e pagamento externo DIZEM o que fazer")
chk("window.open(link" in ui, "fora do Telegram o invoice_link abre em janela nova")
tabs_code = "\n".join(ln for ln in tabs.splitlines() if not ln.strip().startswith("//"))
chk("tg.openInvoice" not in tabs_code,
    "nenhum call site de pagamento ficou preso ao SDK")
chk(tabs.count("openPaymentLink(res.invoice_link") == 2,
    "os DOIS call sites do pagamento passaram pelo helper")

# Haptics/BackButton/fullscreen degradam sozinhos — medido no RECON, não tocar.
chk("tg?.HapticFeedback" in ui, "os haptics continuam guardados por `tg?.` (não tocados)")
chk("if (!tg) return;" in ui, "o BackButton continua guardado (não tocado)")


# ⚠️ 2026-08-26 — o owner tornou as URLs INGLESAS a regra única: *"quero
# global, quero inglês; se tiver alguma coisa em português ou espanhol, fora —
# digo as URLs"*. O sinónimo deixou de ser uma rota e passou a ser uma 301.
# Isto é um override explícito da regra de 2026-08-21 (Lei §6), e o teste segue
# a decisão nova — não a antiga.
_login_routes = sorted({
    r.resource.canonical for r in app.router.routes()
    if getattr(r, "resource", None) is not None
    and str(r.resource.canonical).rstrip("/") in ("/login", "/entrar")
})
chk(_login_routes == ["/entrar", "/entrar/", "/login", "/login/"],
    "a porta responde na canónica E na legada (%s)" % _login_routes)
srv_src = rd("core/webserver.py")
chk(srv_src.index('for _alias in ("/login"') < srv_src.index('_LEGACY_ROUTE_REDIRECTS.items()'),
    "a canónica está declarada PRIMEIRO (é ela que se publica)")

# A lista de legadas é a ÚNICA fonte — uma rota PT declarada à mão fora dela
# escapava à regra em silêncio.
from core.webserver import _LEGACY_ROUTE_REDIRECTS as _LEG
chk(all(v.isascii() and v.islower() and " " not in v for v in _LEG.values()),
    "todas as canónicas de destino são caminhos simples")
chk(set(_LEG.values()) <= {"/play", "/login", "/privacy", "/terms"},
    "as legadas só apontam para canónicas INGLESAS (%s)" % sorted(set(_LEG.values())))
_served = {str(r.resource.canonical) for r in app.router.routes()
           if getattr(r, "resource", None) is not None}
chk(not ({"/jogar", "/mundo", "/entrar"} - set(_LEG)),
    "nenhuma rota PT ficou a SERVIR página — todas passaram para a lista de 301")
chk('MINIAPP_DIR / "login.html"' in srv_src,
    "o ficheiro da página tem o nome da rota canónica")
chk(not os.path.exists(os.path.join(ROOT, "miniapp", "entrar.html")),
    "não sobrou um `entrar.html` órfão a divergir do `login.html`")


print("\n=== 8. A porta: Lei §1 e nenhum open redirect ===")
page = rd("miniapp/login.html")
chk('raw.charAt(0) === "/" && raw.charAt(1) !== "/"' in page,
    "⚠️ o `next` só aceita caminhos DESTE site (sem open redirect)")
BS = chr(92)
# /security-review 2026-08-21 apanhou isto: os browsers RETIRAM tab/chr(13)/chr(10) ao
# interpretar um URL, portanto `?next=/%09//evil.com` passava no teste dos dois
# primeiros caracteres e navegava para `///evil.com` (protocol-relative).
CTRL_CLASS = "[" + BS + "u0000-" + BS + "u001F" + BS + "u007F" + BS + "s]"
seg_next = page.split("function safeNext", 1)[1][:500]
chk(CTRL_CLASS in seg_next,
    "o `next` e LIMPO de caracteres de controlo ANTES de ser validado")
chk('raw.indexOf(":") < 0' in page, "o `next` nao pode trazer esquema nenhum")


def _safe_next(raw_next: str) -> str:
    """A MESMA regra, em Python, para a poder medir com casos reais."""
    cleaned = re.sub(CTRL_CLASS, "", raw_next or "")
    if (cleaned[:1] == "/" and cleaned[1:2] != "/"
            and BS not in cleaned and ":" not in cleaned):
        return cleaned
    return "/app"


EVIL = [
    "//evil.com",
    "/" + chr(9) + "//evil.com",
    "/" + chr(10) + "//evil.com",
    "/" + chr(13) + "//evil.com",
    "https://evil.com",
    "javascript:alert(1)",
    "/" + BS + "evil.com",
    BS + "/evil.com",
]
for evil in EVIL:
    chk(_safe_next(evil) == "/app", "`next=%r` e recusado -> /app" % evil)
for good in ("/app", "/app?tab=home", "/play"):
    chk(_safe_next(good) == good, "`next=%r` e aceite" % good)

chk("credentials: \"include\"" in page, "a porta manda o cookie que acabou de receber")
srv = rd("core/webserver.py")
chk((BS + "u003c") in srv,
    "o JSON injectado no <script> escapa `<` (nunca fecha a tag)")
chk('"&lt;"' in srv, "o título injectado no <head> é escapado")
ws2 = rd("core/web_session.py")
chk("isascii()" in ws2,
    "⚠️ um cookie com bytes não-ASCII devolve None em vez de levantar")

# zero copy: toda a string visível vem do servidor
used = set(re.findall(r'"(web_login_\w+)"', page))
declared = set(W.WEB_LOGIN_KEYS)
chk(used == declared,
    "as keys usadas pela página == WEB_LOGIN_KEYS (a mais: %s | a menos: %s)"
    % (sorted(used - declared), sorted(declared - used)))


print("\n=== 9. i18n: paridade, PT-BR, e nada prometido a mais ===")
chat = {lg: json.loads(rd("locales/%s.json" % lg)) for lg in ("pt", "en", "es")}
mini = {lg: json.loads(rd("miniapp/i18n/%s.json" % lg)) for lg in ("pt", "en", "es")}
chk(len(set(len(v) for v in chat.values())) == 1,
    "as 3 locales do chat estão em paridade (%s)" % {k: len(v) for k, v in chat.items()})
chk(len(set(len(v) for v in mini.values())) == 1,
    "as 3 locales do mini-app estão em paridade (%s)" % {k: len(v) for k, v in mini.items()})
for key in W.WEB_LOGIN_KEYS:
    chk(all(chat[lg].get(key) for lg in ("pt", "en", "es")),
        "`%s` existe e não está vazia nas 3 línguas" % key)
for key in ("shop_invoice_external", "shop_invoice_popup_blocked"):
    chk(all(mini[lg].get(key) for lg in ("pt", "en", "es")),
        "`%s` existe nas 3 línguas do mini-app" % key)

# PT-BR, nunca EU-PT (lição que já custou uma reclamação do owner)
EUPT = ("utilizador", "ecrã", "telemóvel", "a fazer", "estás", "clica ", "carrega em",
        "ficheiro", "actualiz", "definições", "pretende")
for key in W.WEB_LOGIN_KEYS:
    txt = (chat["pt"].get(key) or "").lower()
    bad = [w for w in EUPT if w in txt]
    chk(not bad, "PT-BR em `%s` (grafia europeia: %s)" % (key, bad))

# §6 — o que fica INTERDITO dizer.
#
# ⚠️ MUDOU a 2026-08-26. "sem Telegram" saiu desta lista, e a razão é a única
# que vale: **deixou de ser mentira**. Em 21/08 a porta só sabia autenticar
# Telegram, e prometer o contrário era enganar. Hoje há Google, Apple e
# e-mail/senha, e a frase passou a descrever o que a página faz.
#
# O que CONTINUA proibido é o que continua a não estar nas nossas mãos: uma
# DATA, e qualquer forma de "em breve" — a promessa que nunca se cumpre no
# calendário de quem a leu.
FORBIDDEN = {
    "pt": ("em breve", "em algumas semanas", "nos próximos dias"),
    "en": ("coming soon", "in a few weeks", "in the next few days"),
    "es": ("próximamente", "en unas semanas", "en los próximos días"),
}
for lg, words in FORBIDDEN.items():
    blob = " ".join((chat[lg].get(k) or "") for k in W.WEB_LOGIN_KEYS).lower()
    bad = [w for w in words if w in blob]
    chk(not bad, "porta %s sem promessa proibida %s (§6)" % (lg, bad))
    chk(not re.search(r"\b20\d\d\b", blob), "porta %s sem data nenhuma (§6)" % lg)

# Lei §1 — honest disclosure, na versão de HOJE. A porta tem de continuar a
# dizer aos 248 que o personagem deles não se perdeu: enquanto o login do
# Telegram não voltar, eles entram pelo bot, e a página TEM de o dizer.
for lg in ("pt", "en", "es"):
    fb = ((chat[lg].get("web_login_fallback_title") or "") + " " +
          (chat[lg].get("web_login_fallback_body") or ""))
    chk("Telegram" in fb,
        "a porta %s diz a quem já jogava por onde entrar (Lei §1)" % lg)
chk(any(w in chat["pt"]["web_login_fallback_body"].lower()
        for w in ("continuam", "onde estavam")),
    "a porta diz que o personagem continua onde estava (ninguém teme perdê-lo)")

# Os três caminhos novos existem, e cada erro DIZ o que fazer.
for key in ("web_login_google", "web_login_apple", "web_login_submit_up"):
    chk(all(chat[lg].get(key) for lg in ("pt", "en", "es")),
        "`%s` existe nas 3 línguas" % key)
# ⚠️ ANTI-ENUMERAÇÃO na copy: a frase de "e-mail ou senha" não pode dizer qual
# dos dois falhou — senão a página vira um verificador de e-mails.
for lg in ("pt", "en", "es"):
    t_err = (chat[lg].get("web_login_err_email") or "").lower()
    chk(not any(w in t_err for w in ("não existe", "not found", "no existe",
                                     "não cadastrado", "unregistered")),
        "porta %s não revela SE o e-mail existe (anti-enumeração)" % lg)


print("\n=== 9.5 O SQL do backfill: um parametro, um tipo ===")
# ⚠️ ESTE BLOCO NASCEU DE UM BUG DE PRODUCAO (logs do owner, 2026-08-26).
# O backfill falhava em TODO boot desde a F1 e as 248 identidades nunca foram
# criadas — o try/except engolia e ninguem via:
#
#   AmbiguousParameterError: inconsistent types deduced for parameter $1
#   DETAIL: text versus bigint
#
# Causa: `VALUES (:p0, 'telegram', (:p0)::text)` reusava O MESMO parametro como
# BIGINT e como TEXT. O Postgres deduz UM tipo por parametro e recusa.
#
# ⚠️ E A LICAO DURA: o `_FakeControl` desta suite deu VERDE a isto. Um armazem
# falso implementa o que a instrucao FAZ, nunca o que o Postgres RECUSA. Por
# isso o guarda aqui e ESTATICO — le o codigo, nao o comportamento do falso.
import ast as _ast
_cdb_src = rd("database/control_db.py")
_fn = next(n for n in _ast.walk(_ast.parse(_cdb_src))
           if isinstance(n, (_ast.AsyncFunctionDef, _ast.FunctionDef))
           and n.name == "backfill_telegram_identities")
_code = _ast.unparse(_fn)   # sem comentarios: mede o codigo, nao a prosa
chk("::text" not in _code,
    "o backfill nao volta a castar um parametro (era o `text versus bigint`)")
_tpl = [ln for ln in _code.splitlines() if "VALUES" in ln or "telegram'," in ln]
chk(any(":u{i}" in ln or ":u' + str(i)" in ln for ln in _code.splitlines()),
    "provider_uid recebe um parametro PROPRIO, ja em texto")
_names = re.findall(r":(\w+)\{?i?\}?", _code)
chk(_code.count(":p{i}") == 1 and _code.count(":u{i}") == 1,
    "cada parametro aparece uma unica vez no template da linha")


print("\n=== 10. Migrations: nada partido, e a tabela nasce no sítio certo ===")
mig = sorted(f for f in os.listdir(os.path.join(ROOT, "migrations")) if f.endswith(".sql"))
# ⚠️ 2026-09-07 — dizia "não há migration 140" e a Mig 140 (género) nasceu,
# vermelha sem nada a ver com a identidade. O que a WEB-B tem de provar é que
# `auth_identities` vive no PLANO DE CONTROLO e NÃO numa migration de mundo —
# e isso prova-se pelo assunto, não pelo número seguinte da fila.
chk(not [f for f in mig if "auth_identit" in (f + rd("migrations/" + f)).lower()],
    "nenhuma migration de MUNDO cria auth_identities — a identidade é do "
    "PLANO DE CONTROLO")
cdb = rd("database/control_db.py")
chk("CREATE TABLE IF NOT EXISTS auth_identities" in cdb,
    "auth_identities nasce no bootstrap do plano de controlo")
chk("CREATE TABLE IF NOT EXISTS auth_sessions" in cdb, "auth_sessions idem")
chk("UNIQUE (provider, provider_uid)" in cdb,
    "⚠️ o UNIQUE é o que torna `uma pessoa, uma identidade` verdade no esquema")
chk("provider_uid  TEXT" in cdb, "provider_uid é TEXT (o email não é número)")
chk("REFERENCES players" not in cdb.split("auth_identities", 1)[1].split(")", 1)[0],
    "sem FK para players — o control DB pode não ter essa tabela")
chk("DROP TABLE" not in cdb and "DROP COLUMN" not in cdb,
    "regra da casa: só ADD/CREATE IF NOT EXISTS, nunca DROP")
chk("ON CONFLICT (provider, provider_uid) DO NOTHING" in cdb,
    "o backfill é idempotente por construção")
db_src = rd("database/db.py")
chk("backfill_telegram_identities" in db_src, "o backfill corre no init_db")
i_worlds = db_src.find("DEMOTING to 'maintenance'")
i_backfill = db_src.find("backfill_telegram_identities")
chk(0 < i_worlds < i_backfill,
    "o backfill corre DEPOIS dos mundos (lê a tabela players de cada um)")


print("\n" + "=" * 62)
print("  %d asserts verdes, %d vermelhos" % (OK, len(FAIL)))
if FAIL:
    print("\n  VERMELHOS:")
    for f in FAIL:
        print("   x " + f)
print("=" * 62)
sys.exit(1 if FAIL else 0)
