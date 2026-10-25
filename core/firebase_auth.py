# -*- coding: utf-8 -*-
"""WEB-B Fase 2 — VERIFICAR O ID TOKEN DO FIREBASE (Google · Apple · e-mail/senha).

⚠️ **Este ficheiro é a fronteira de confiança inteira do login novo.** Do outro
lado dele está `link_identity()`, que entrega um `player_id` — ou seja, um
personagem com compras reais. Tudo o que este módulo deixa passar entra no jogo
como se fosse a pessoa. Não há segunda verificação a jusante.

**Porquê o Firebase e não senhas nossas** (decisão do owner 2026-08-26): as
senhas passam a ser problema do Google. Nunca guardamos uma, nunca enviamos um
e-mail de recuperação, nunca escrevemos uma defesa anti-enumeração. O que
guardamos é o **`uid`** — um identificador opaco — e é isso que vira
`auth_identities.provider_uid`.

**Porquê o Telegram NÃO vive aqui:** um provider OIDC personalizado no Firebase
custa $0,015/MAU depois dos primeiros 50 e obriga a subir para o Identity
Platform. O Telegram fica cliente OIDC nosso (`core/oidc.py`), grátis. Os dois
caminhos aterram na MESMA `auth_identities` — que era o objectivo da F1.

**Como se verifica um ID token do Firebase** (é um JWT RS256 assinado pelo
Google, e a receita é a da documentação oficial — nada aqui é inventado):

  1. `alg` tem de ser **RS256**, e a lista de algoritmos aceites é EXPLÍCITA.
     Sem isso existe o ataque clássico de confusão de algoritmo: um atacante
     manda `alg: none` (ou HS256 assinado com a chave pública, que é pública) e
     uma verificação ingénua aceita. A `PyJWT` só fecha isto quando lhe damos a
     lista — por isso ela está escrita à mão e nunca sai do token.
  2. `kid` do cabeçalho tem de existir nas chaves públicas do Google.
  3. `aud` == o nosso `projectId`.
  4. `iss` == `https://securetoken.google.com/<projectId>`.
  5. `exp` no futuro, `iat` e `auth_time` no passado.
  6. `sub` não vazio — é o `uid`, e é a única coisa que persistimos.

Nada é levantado para o chamador em texto útil a um atacante: ou devolve as
claims, ou levanta `FirebaseAuthError` com uma razão estável que a página
traduz.
"""
from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger(__name__)

#: As chaves públicas do Google para os ID tokens do Firebase, em formato JWK.
#: (Há também um endpoint em x509; o JWK é o que a `PyJWT` consome directamente.)
JWKS_URL = ("https://www.googleapis.com/service_accounts/v1/jwk/"
            "securetoken@system.gserviceaccount.com")

#: O `projectId` **não é secreto** — vai no HTML do cliente, como manda o
#: Firebase. Fica com default assado (Lei §6: sem quiz ao owner) e com env por
#: cima para o dia em que houver um projecto de testes.
DEFAULT_PROJECT_ID = ""  # 開 edição comunitária: cada instância traz o seu (FIREBASE_PROJECT_ID)

#: Margem para relógios dessincronizados. 60s é o que a própria documentação do
#: Firebase tolera; mais do que isso alarga a janela de um token roubado.
CLOCK_SKEW_SECONDS = 60

#: Rede de segurança do cache das chaves. O Google manda um `max-age` (~6h) e é
#: esse que mandamos respeitar; isto é só o tecto para o caso de vir sem ele.
_JWKS_MAX_TTL = 6 * 3600
_JWKS_MIN_TTL = 300


class FirebaseAuthError(Exception):
    """Recusa de login. O `reason` é uma key estável, nunca o motivo exacto.

    ⚠️ Dizer *porquê* um token falhou é um oráculo para quem forja. A página só
    precisa de saber se vale a pena tentar outra vez."""

    def __init__(self, reason: str = "login_invalid"):
        super().__init__(reason)
        self.reason = reason


def project_id() -> str:
    return (os.getenv("FIREBASE_PROJECT_ID") or "").strip() or DEFAULT_PROJECT_ID


def is_configured() -> bool:
    """Há projecto para verificar contra? (Nunca levanta — a porta tem de
    conseguir desenhar mesmo mal configurada, Lei §1.)"""
    return bool(project_id())


# ── As chaves públicas do Google ─────────────────────────────────────────────
#: `{kid: chave}` + o instante em que expira. Em processo, sem Redis: são 2 ou 3
#: chaves e o Google roda-as de horas a horas.
_jwks_cache: dict = {}
_jwks_expires_at: float = 0.0


def _parse_max_age(cache_control: str | None) -> int:
    """O `max-age=N` do header, limitado pelo nosso mínimo/máximo."""
    ttl = _JWKS_MAX_TTL
    for part in str(cache_control or "").split(","):
        k, _, v = part.strip().partition("=")
        if k.strip().lower() == "max-age":
            try:
                ttl = int(v)
            except (TypeError, ValueError):
                ttl = _JWKS_MAX_TTL
            break
    return max(_JWKS_MIN_TTL, min(_JWKS_MAX_TTL, ttl))


async def _fetch_jwks(force: bool = False) -> dict:
    """As chaves públicas, com cache. `force` ignora o cache (rotação de chave).

    Levanta `FirebaseAuthError("server_unreachable")` se não conseguir — e isso
    vira 503, nunca "passa". Uma falha de rede não pode autenticar ninguém.
    """
    global _jwks_cache, _jwks_expires_at
    now = time.monotonic()
    if not force and _jwks_cache and now < _jwks_expires_at:
        return _jwks_cache

    import aiohttp
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as sess:
            async with sess.get(JWKS_URL) as resp:
                if resp.status != 200:
                    raise FirebaseAuthError("server_unreachable")
                payload = await resp.json(content_type=None)
                ttl = _parse_max_age(resp.headers.get("Cache-Control"))
    except FirebaseAuthError:
        raise
    except Exception as exc:
        logger.warning("firebase: JWKS inalcançável (%s)", type(exc).__name__)
        raise FirebaseAuthError("server_unreachable") from exc

    keys = {}
    for jwk in (payload or {}).get("keys") or []:
        kid = jwk.get("kid")
        if not kid:
            continue
        try:
            from jwt.algorithms import RSAAlgorithm
            keys[kid] = RSAAlgorithm.from_jwk(jwk)
        except Exception:
            logger.warning("firebase: JWK ignorada (kid=%s)", kid)

    if not keys:
        raise FirebaseAuthError("server_unreachable")

    _jwks_cache = keys
    _jwks_expires_at = now + ttl
    return keys


async def _key_for(kid: str):
    """A chave deste `kid`, com UMA re-leitura forçada se ele não estiver no
    cache — é assim que uma rotação de chaves do Google não deita o login abaixo
    até o TTL expirar. Uma só, e não por pedido: senão um atacante a mandar
    `kid` inventados fazia-nos martelar o Google por ele."""
    keys = await _fetch_jwks()
    if kid in keys:
        return keys[kid]
    keys = await _fetch_jwks(force=True)
    if kid in keys:
        return keys[kid]
    raise FirebaseAuthError("login_invalid")


# ── A verificação ────────────────────────────────────────────────────────────
async def verify_firebase_id_token(id_token: str) -> dict:
    """Verifica o token e devolve o perfil. Levanta `FirebaseAuthError`.

    O que sai daqui é o MÍNIMO que o jogo precisa — nunca o token, nunca as
    claims cruas, nunca nada que sirva para reconstruir a sessão do Firebase.
    """
    if not id_token or not isinstance(id_token, str) or len(id_token) > 8192:
        raise FirebaseAuthError("login_invalid")
    if not is_configured():
        raise FirebaseAuthError("server_misconfigured")

    import jwt

    try:
        header = jwt.get_unverified_header(id_token)
    except Exception:
        raise FirebaseAuthError("login_invalid")

    # ⚠️ A lista de algoritmos NUNCA sai do token. Ler `header["alg"]` e passá-lo
    # a `jwt.decode` é literalmente o ataque de confusão de algoritmo.
    if header.get("alg") != "RS256":
        raise FirebaseAuthError("login_invalid")
    kid = header.get("kid")
    if not kid or not isinstance(kid, str):
        raise FirebaseAuthError("login_invalid")

    key = await _key_for(kid)
    pid = project_id()

    try:
        claims = jwt.decode(
            id_token,
            key=key,
            algorithms=["RS256"],          # explícito, sempre
            audience=pid,
            issuer=f"https://securetoken.google.com/{pid}",
            leeway=CLOCK_SKEW_SECONDS,
            options={
                "require": ["exp", "iat", "aud", "iss", "sub"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
    except jwt.ExpiredSignatureError:
        # A ÚNICA recusa que vale a pena distinguir: dizer "expirou" não ajuda
        # quem forja (não consegue assinar de novo) e ajuda muito quem deixou o
        # separador aberto — o cliente pede um token novo e reentra sozinho.
        raise FirebaseAuthError("token_expired")
    except Exception:
        raise FirebaseAuthError("login_invalid")

    uid = str(claims.get("sub") or "").strip()
    if not uid or len(uid) > 128:
        raise FirebaseAuthError("login_invalid")

    # `auth_time` é quando a pessoa se autenticou de facto. Um valor no futuro
    # não acontece num token honesto.
    auth_time = claims.get("auth_time")
    if isinstance(auth_time, (int, float)):
        if auth_time > time.time() + CLOCK_SKEW_SECONDS:
            raise FirebaseAuthError("login_invalid")

    firebase = claims.get("firebase") or {}
    sign_in = str(firebase.get("sign_in_provider") or "").strip()[:32]

    return {
        "uid": uid,
        "email": (str(claims.get("email") or "").strip().lower())[:254],
        # ⚠️ Só o Google diz se o e-mail está verificado. Nunca inferir de
        # "veio um e-mail no token" — o provider `password` devolve o e-mail
        # antes de a pessoa clicar no link.
        "email_verified": bool(claims.get("email_verified")),
        "name": (str(claims.get("name") or "").strip())[:64],
        "picture": (str(claims.get("picture") or "").strip())[:512],
        #: `google.com` · `apple.com` · `password` — o que o owner ligou.
        "sign_in_provider": sign_in,
    }
