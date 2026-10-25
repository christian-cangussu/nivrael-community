# -*- coding: utf-8 -*-
"""WEB-B Fase 1 — A SESSÃO WEB: "o teu JOGADOR", não "o teu Telegram".

⚠️ **Este é o único módulo perigoso do lote.** Até 2026-08-21 o Nivrael não tinha
uma única credencial persistente: o HMAC do Telegram é reemitido a cada abertura
e não há senha guardada em lado nenhum — literalmente **não havia nada para
roubar**. Este ficheiro introduz a primeira, com **248 pessoas e compras reais**
atrás dela. Tudo aqui existe por causa disso.

As cinco promessas (e onde cada uma vive):

1. **O cookie sozinho NÃO autentica.** Autenticar exige o par
   `cookie nv_session` + header ``X-Nivrael-Session``, e o header tem de bater
   com a coluna `csrf` da row — não com um segundo cookie. Um `<form>` de outro
   site consegue mandar o cookie; **não** consegue pôr um header. CSRF morre por
   construção, e morre no chokepoint (`verify_request_session`), não em cada
   handler. Isto é mais forte que o double-submit clássico: quem escreva cookies
   (um subdomínio comprometido) continua sem saber o valor guardado no servidor.
2. **Revogação real.** A row em `auth_sessions` É a verdade. `revoked_at` mata a
   sessão no pedido SEGUINTE — sem cache, sem esperar pela expiração. Um cookie
   assinado-e-sem-estado seria eterno; isso é inaceitável com compras atrás.
3. **O segredo do cookie nunca é só o `sid`.** O cookie leva `sid.exp.mac`: o
   `mac` deixa recusar lixo (scanners, cookies velhos) **sem tocar na base**, e o
   `sid` é 256 bits de `secrets.token_urlsafe`. Assinado E com estado — as duas
   coisas, porque resolvem problemas diferentes.
4. **Nada do Telegram é persistido além do necessário.** Nunca o `init_data`,
   nunca o `hash` do widget. `tg_user` guarda só `{first_name, username}` porque
   é o que `world/start` usa para nomear o personagem novo — o mesmo que o
   Telegram já dá hoje pelo `init_data`.
5. **Nunca decide o mundo.** A sessão diz QUEM; `player_active_server` continua
   a dizer ONDE, exactamente como no ramo do `init_data`. Se este módulo
   escrevesse o mundo, o chat sentiria (LEI DUAL-SURFACE) — por isso não escreve.

TTL: janela deslizante curta (`SESSION_TTL_SECONDS`), com um tecto absoluto
(`SESSION_ABSOLUTE_MAX_SECONDS`) que nem o uso diário ultrapassa. Quem joga todos
os dias nunca volta a fazer login; um cookie roubado e parado morre sozinho.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Constantes (knobs do owner — Lei §6: defaults assados, sem quiz) ──────────
COOKIE_NAME = "nv_session"          # HttpOnly — a credencial
CSRF_COOKIE_NAME = "nv_csrf"        # legível por JS — só para o cliente montar o header
CSRF_HEADER = "X-Nivrael-Session"   # o header que um <form> de outro site não consegue pôr

#: Janela deslizante. Curta de propósito: um cookie roubado e PARADO morre aqui.
SESSION_TTL_SECONDS = 72 * 3600
#: Tecto absoluto desde a criação — o deslizar não é eterno.
SESSION_ABSOLUTE_MAX_SECONDS = 30 * 86400
#: Só escrevemos na base para renovar depois deste tempo desde o último toque.
#: Sem isto, cada pedido do jogo (a cultivação sonda de 5 em 5s) seria um UPDATE.
SESSION_RENEW_AFTER_SECONDS = 3600

COOKIE_VERSION = "1"
_MAC_LEN = 32  # 128 bits de HMAC truncado — de sobra para um identificador opaco


class WebSessionError(Exception):
    """Falha ao emitir uma sessão (só o LOGIN levanta; verificar nunca levanta)."""


@dataclass
class WebSession:
    """Uma sessão VÁLIDA. Nunca é construída para uma sessão recusada."""
    sid: str
    player_id: int
    provider: str
    identity_id: int | None
    tg_user: dict
    expires_at: datetime
    #: Cookie novo a escrever na resposta (só quando a janela deslizou).
    refreshed_cookie: str | None = None
    refreshed_csrf: str | None = None


# ── Segredo ───────────────────────────────────────────────────────────────────
def _session_secret() -> bytes:
    """O segredo que assina o cookie.

    `SESSION_SECRET` manda. Sem ele, DERIVA-SE do `BOT_TOKEN` — zero configuração
    de ops (o Coolify já tem o token) e uma propriedade útil de graça: rodar o
    token do bot invalida todas as sessões web de uma vez. A derivação é
    unidireccional, portanto o cookie nunca é um oráculo sobre o token.
    """
    raw = (os.getenv("SESSION_SECRET") or "").strip()
    if raw:
        return raw.encode("utf-8")
    token = os.getenv("BOT_TOKEN", "").strip().strip('"').strip("'")
    if not token:
        raise WebSessionError("server misconfigured: no SESSION_SECRET / BOT_TOKEN")
    return hmac.new(b"nivrael-web-session-v1", token.encode("utf-8"), hashlib.sha256).digest()


def cookie_secure() -> bool:
    """`Secure` ligado por defeito. Só o dev local o desliga, e tem de o dizer em
    voz alta (`NIVRAEL_COOKIE_INSECURE=1`) — nenhum default silencioso consegue
    transformar produção em http."""
    return (os.getenv("NIVRAEL_COOKIE_INSECURE") or "").strip().lower() not in ("1", "true", "yes")


def _sign(sid: str, exp: int) -> str:
    msg = f"{COOKIE_VERSION}.{sid}.{exp}".encode("utf-8")
    return hmac.new(_session_secret(), msg, hashlib.sha256).hexdigest()[:_MAC_LEN]


def _pack(sid: str, exp: int) -> str:
    return f"{COOKIE_VERSION}.{sid}.{exp}.{_sign(sid, exp)}"


def _unpack(cookie_value: str) -> tuple[str, int] | None:
    """Verificação OFFLINE: formato, assinatura e expiração. `None` = lixo.

    Corre antes de qualquer ida à base — um scanner a atirar cookies aleatórios
    nunca gera uma query."""
    if not cookie_value or len(cookie_value) > 512:
        return None
    parts = cookie_value.split(".")
    if len(parts) != 4:
        return None
    ver, sid, exp_raw, mac = parts
    if ver != COOKIE_VERSION or not sid or len(sid) > 128:
        return None
    # `compare_digest` LEVANTA com str não-ASCII, e um cookie cru pode trazer
    # bytes >127. Esta função promete devolver None para lixo — a promessa não
    # pode depender de um try/except do chamador.
    if not (sid.isascii() and mac.isascii() and exp_raw.isascii()):
        return None
    try:
        exp = int(exp_raw)
    except (TypeError, ValueError):
        return None
    try:
        expected = _sign(sid, exp)
    except WebSessionError:
        return None
    if not hmac.compare_digest(expected, mac):
        return None
    if exp <= int(datetime.now(timezone.utc).timestamp()):
        return None
    return sid, exp


def _sm():
    from database.control_db import get_control_session_factory
    return get_control_session_factory()


def _as_dict(raw) -> dict:
    """`tg_user` pode chegar como dict (JSONB) ou como str (conforme o driver e o
    tipo real da coluna). Nunca deixar o tipo do driver chegar aos handlers."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (str, bytes)):
        try:
            out = json.loads(raw)
            return out if isinstance(out, dict) else {}
        except Exception:
            return {}
    return {}


def _aware(dt: datetime) -> datetime:
    """Postgres pode devolver naive conforme o driver/coluna. Comparar naive com
    aware levanta `TypeError` — e um `TypeError` aqui dentro viraria 401 em massa."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ── Identidades ───────────────────────────────────────────────────────────────
async def link_identity(provider: str, provider_uid: str, player_id: int,
                        profile: dict | None = None) -> tuple[int, int] | None:
    """Resolve (ou cria) a identidade. Devolve ``(identity_id, player_id)``.

    ⚠️ O `player_id` passado só vale para uma identidade NOVA. Num conflito, o
    `player_id` **guardado** ganha e o do argumento é ignorado — é isso que
    impede que um login re-aponte uma identidade para outro personagem, e é a
    linha que a Fase 2 (email) herda sem alterar nada.
    """
    sm = _sm()
    if sm is None:
        return None
    payload = json.dumps(profile or {}, ensure_ascii=False)
    async with sm() as session:
        row = (await session.execute(text(
            "INSERT INTO auth_identities (player_id, provider, provider_uid, profile, last_login_at) "
            "VALUES (:pid, :prov, :uid, CAST(:prof AS JSONB), now()) "
            "ON CONFLICT (provider, provider_uid) DO UPDATE SET "
            "  last_login_at = now(), "
            "  profile = CAST(:prof AS JSONB) "
            "RETURNING id, player_id"
        ), {"pid": int(player_id), "prov": provider, "uid": str(provider_uid), "prof": payload})).first()
        await session.commit()
    if row is None:
        return None
    return int(row[0]), int(row[1])


async def find_identity(provider: str, provider_uid: str) -> tuple[int, int] | None:
    """``(identity_id, player_id)`` ou ``None``. É a leitura que a Fase 2 usa."""
    sm = _sm()
    if sm is None:
        return None
    async with sm() as session:
        row = (await session.execute(text(
            "SELECT id, player_id FROM auth_identities "
            "WHERE provider = :prov AND provider_uid = :uid"
        ), {"prov": provider, "uid": str(provider_uid)})).first()
    return (int(row[0]), int(row[1])) if row else None


# ── Sessões ───────────────────────────────────────────────────────────────────
async def issue_session(player_id: int, provider: str, identity_id: int | None,
                        tg_user: dict | None = None) -> tuple[str, str, datetime]:
    """Emite uma sessão. Devolve ``(cookie_value, csrf, expires_at)``."""
    sm = _sm()
    if sm is None:
        raise WebSessionError("control plane unavailable")
    sid = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=SESSION_TTL_SECONDS)
    async with sm() as session:
        await session.execute(text(
            "INSERT INTO auth_sessions (sid, player_id, identity_id, provider, csrf, tg_user, expires_at) "
            "VALUES (:sid, :pid, :iid, :prov, :csrf, CAST(:tgu AS JSONB), :exp)"
        ), {"sid": sid, "pid": int(player_id), "iid": identity_id, "prov": provider,
            "csrf": csrf, "tgu": json.dumps(tg_user or {}, ensure_ascii=False), "exp": expires})
        # Limpeza oportunista: rows mortas há mais de uma semana não servem nem
        # para auditoria. Sem job novo, sem scheduler novo.
        await session.execute(text(
            "DELETE FROM auth_sessions WHERE expires_at < now() - INTERVAL '7 days'"
        ))
        await session.commit()
    return _pack(sid, int(expires.timestamp())), csrf, expires


async def verify_session(cookie_value: str, csrf_header: str) -> WebSession | None:
    """A porta. `None` para QUALQUER falha — nunca levanta, nunca diz porquê.

    Ordem deliberada: offline primeiro (formato/assinatura/expiração), só depois
    a base. E a comparação do CSRF é `compare_digest` — um `==` daria um oráculo
    de tempo sobre um valor que vive num cookie legível por JS.
    """
    unpacked = _unpack(cookie_value or "")
    if unpacked is None:
        return None
    sid, _exp = unpacked
    if not csrf_header:
        # O cookie SOZINHO não autentica. Esta linha é o anti-CSRF inteiro.
        return None

    sm = _sm()
    if sm is None:
        return None
    now = datetime.now(timezone.utc)
    try:
        async with sm() as session:
            row = (await session.execute(text(
                "SELECT sid, player_id, identity_id, provider, csrf, tg_user, "
                "       created_at, last_seen_at, expires_at, revoked_at "
                "FROM auth_sessions WHERE sid = :sid"
            ), {"sid": sid})).first()
            if row is None:
                return None
            (_sid, player_id, identity_id, provider, csrf, tg_user_raw,
             created_at, last_seen_at, expires_at, revoked_at) = row

            if revoked_at is not None:
                return None
            if not hmac.compare_digest(str(csrf), str(csrf_header)):
                return None
            # A base é a verdade sobre a expiração — o `exp` do cookie é só uma
            # optimização. Uma sessão encurtada do lado do servidor tem de morrer
            # mesmo que o cookie ainda diga que está viva.
            if expires_at is None or _aware(expires_at) <= now:
                return None
            if created_at is not None and \
                    (now - _aware(created_at)).total_seconds() > SESSION_ABSOLUTE_MAX_SECONDS:
                return None
            if int(player_id) == 0:
                return None

            out = WebSession(
                sid=sid, player_id=int(player_id), provider=str(provider or "telegram"),
                identity_id=int(identity_id) if identity_id is not None else None,
                tg_user=_as_dict(tg_user_raw), expires_at=_aware(expires_at),
            )

            # Renovação deslizante, com trava de escrita: só toca na base uma vez
            # por hora, por muito que o jogo sonde.
            stale = last_seen_at is None or \
                (now - _aware(last_seen_at)).total_seconds() > SESSION_RENEW_AFTER_SECONDS
            if stale:
                hard_cap = (_aware(created_at) if created_at is not None else now) + \
                    timedelta(seconds=SESSION_ABSOLUTE_MAX_SECONDS)
                new_exp = min(now + timedelta(seconds=SESSION_TTL_SECONDS), hard_cap)
                if new_exp > _aware(expires_at):
                    await session.execute(text(
                        "UPDATE auth_sessions SET last_seen_at = :now, expires_at = :exp "
                        "WHERE sid = :sid AND revoked_at IS NULL"
                    ), {"now": now, "exp": new_exp, "sid": sid})
                    await session.commit()
                    out.expires_at = new_exp
                    out.refreshed_cookie = _pack(sid, int(new_exp.timestamp()))
                    out.refreshed_csrf = str(csrf)
                else:
                    await session.execute(text(
                        "UPDATE auth_sessions SET last_seen_at = :now WHERE sid = :sid"
                    ), {"now": now, "sid": sid})
                    await session.commit()
            return out
    except Exception:
        # Base em baixo ⇒ 401, nunca 500 e nunca "passa". Um erro de
        # infra-estrutura não pode virar uma autenticação.
        logger.warning("verify_session falhou — a tratar como não autenticado", exc_info=True)
        return None


async def revoke_session(cookie_value: str) -> bool:
    """Revoga UMA sessão a partir do cookie. Idempotente."""
    unpacked = _unpack(cookie_value or "")
    if unpacked is None:
        return False
    sm = _sm()
    if sm is None:
        return False
    try:
        async with sm() as session:
            await session.execute(text(
                "UPDATE auth_sessions SET revoked_at = now() "
                "WHERE sid = :sid AND revoked_at IS NULL"
            ), {"sid": unpacked[0]})
            await session.commit()
        return True
    except Exception:
        logger.warning("revoke_session falhou", exc_info=True)
        return False


async def revoke_all_for_player(player_id: int) -> int:
    """Mata TODAS as sessões de um jogador. É a resposta a "perdi o telemóvel" e
    a válvula do owner para um cookie roubado."""
    sm = _sm()
    if sm is None:
        return 0
    try:
        async with sm() as session:
            res = await session.execute(text(
                "UPDATE auth_sessions SET revoked_at = now() "
                "WHERE player_id = :pid AND revoked_at IS NULL RETURNING sid"
            ), {"pid": int(player_id)})
            n = len(res.scalars().all())
            await session.commit()
        return n
    except Exception:
        logger.warning("revoke_all_for_player falhou pid=%s", player_id, exc_info=True)
        return 0


# ── Ponte com o aiohttp ───────────────────────────────────────────────────────
async def verify_request_session(request) -> WebSession | None:
    """Lê o par cookie+header de um `web.Request` e valida-o."""
    return await verify_session(
        request.cookies.get(COOKIE_NAME) or "",
        request.headers.get(CSRF_HEADER) or "",
    )


def set_session_cookies(response, cookie_value: str, csrf: str, expires: datetime) -> None:
    """Escreve o par. `SameSite=Lax` + `Secure` + `HttpOnly` no que autentica; o
    `nv_csrf` é legível de propósito (o JS tem de o pôr no header) e por isso
    **não** é uma credencial — sozinho não abre nada."""
    max_age = max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))
    secure = cookie_secure()
    response.set_cookie(COOKIE_NAME, cookie_value, max_age=max_age, httponly=True,
                        secure=secure, samesite="Lax", path="/")
    response.set_cookie(CSRF_COOKIE_NAME, csrf, max_age=max_age, httponly=False,
                        secure=secure, samesite="Lax", path="/")


def clear_session_cookies(response) -> None:
    secure = cookie_secure()
    for name in (COOKIE_NAME, CSRF_COOKIE_NAME):
        response.set_cookie(name, "", max_age=0, httponly=(name == COOKIE_NAME),
                            secure=secure, samesite="Lax", path="/")
