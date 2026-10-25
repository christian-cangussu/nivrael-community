"""Telegram WebApp initData HMAC validation.

Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Without this, anyone can POST a forged init_data with any user_id and read
arbitrary players' data from /api/miniapp/* endpoints.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)

# Reject initData older than this many seconds. SEC (2026-06-01): lowered from
# 24h to 6h to shrink the capture-and-replay window (a captured initData visible
# in devtools was reusable for a full day, enabling all-day headless automation)
# while still covering open-and-leave sittings. NOTE: Telegram only refreshes
# init_data on RELAUNCH, not while the WebApp stays open — so a session left open
# past this window 401s until reopened (self-healing). 6h cuts the replay budget
# 4x vs the old 24h without forcing reopens during a normal multi-hour session.
MAX_AGE_SECONDS = 6 * 60 * 60


class InitDataError(Exception):
    """Raised when initData fails HMAC, parsing, or age check."""


def _build_secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()


def validate_init_data(init_data: str, bot_token: str, max_age: int = MAX_AGE_SECONDS) -> dict:
    """Validate a Telegram WebApp initData query string.

    Returns the parsed payload (with ``user`` already JSON-decoded) on success.
    Raises ``InitDataError`` on any failure.
    """
    if not init_data:
        raise InitDataError("empty init_data")
    if not bot_token:
        raise InitDataError("server misconfigured: BOT_TOKEN not set")

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    except Exception as exc:
        raise InitDataError(f"malformed init_data: {exc}") from exc

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InitDataError("missing hash")

    # Per the Telegram spec, the data_check_string includes ALL received
    # fields except `hash`. The newer `signature` field (Ed25519 for third-
    # party validation) IS included in the HMAC data_check_string — official
    # implementations (@telegram-apps/init-data-python, pyTelegramBotAPI)
    # confirm this. Removing it caused every HMAC check to mismatch.
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = _build_secret_key(bot_token)
    expected = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("hash mismatch")

    auth_date_raw = parsed.get("auth_date", "")
    try:
        auth_date = int(auth_date_raw)
    except (TypeError, ValueError) as exc:
        raise InitDataError("missing or invalid auth_date") from exc

    age = int(time.time()) - auth_date
    if age < 0:
        # Clock skew tolerance: allow up to 5min of "future" auth_date.
        if age < -300:
            raise InitDataError("auth_date in the future")
    elif age > max_age:
        raise InitDataError(f"init_data expired (age={age}s)")

    user_raw = parsed.get("user")
    if user_raw:
        try:
            parsed["user"] = json.loads(user_raw)
        except json.JSONDecodeError as exc:
            raise InitDataError(f"malformed user payload: {exc}") from exc

    return parsed


def extract_user_id(init_data: str, bot_token: str) -> int:
    """Validate and return the Telegram user id, or raise InitDataError."""
    payload = validate_init_data(init_data, bot_token)
    user = payload.get("user") or {}
    user_id = user.get("id")
    if not isinstance(user_id, int) or user_id <= 0:
        raise InitDataError("user.id missing or invalid")
    return user_id


# ── Login Widget (WEB-B Fase 1, 2026-08-21) ───────────────────────────────────
# O SEGUNDO validador. ⚠️ NÃO é um parâmetro do primeiro: a chave é DIFERENTE.
#
#   WebApp initData   → secret = HMAC(key=b"WebAppData", msg=bot_token)
#   Login Widget      → secret = SHA256(bot_token)
#
# Em ambos o `hash` é HMAC-SHA256(secret, data_check_string), e o
# data_check_string é `k=v` ordenado por chave e junto por "\n", sobre TODOS os
# campos menos o `hash`. Escrever isto como uma função à parte (e não como um
# `if` dentro de `validate_init_data`) é deliberado: o ramo do initData é o que
# 263 jogadores usam hoje e não pode ganhar um caminho novo por dentro.
#
# Spec: https://core.telegram.org/widgets/login#checking-authorization
#
# Janela: o widget assina UMA vez, no clique. Ao contrário do initData (que o
# Telegram reemite a cada relaunch), aqui não há reemissão automática — o payload
# é trocado por uma sessão em segundos. Daí a janela ser MUITO mais curta que os
# 6h do initData: é o tempo entre o clique e o POST, não o tempo de uma sessão.
LOGIN_WIDGET_MAX_AGE_SECONDS = 5 * 60

# Os campos que o widget pode mandar. Um campo fora desta lista entra na conta do
# HMAC na mesma (a spec manda incluir TUDO menos o `hash`) — a lista existe só
# para o que guardamos, nunca para filtrar o que se verifica.
LOGIN_WIDGET_FIELDS = ("id", "first_name", "last_name", "username", "photo_url", "auth_date")


def _login_widget_secret(bot_token: str) -> bytes:
    return hashlib.sha256(bot_token.encode("utf-8")).digest()


def validate_login_widget(
    payload: dict,
    bot_token: str,
    max_age: int = LOGIN_WIDGET_MAX_AGE_SECONDS,
) -> dict:
    """Valida o payload do *Telegram Login Widget*.

    Devolve o dict validado (com `id` e `auth_date` já como ``int``).
    Levanta ``InitDataError`` em qualquer falha — a MESMA excepção do initData,
    para o middleware ter um só `except`.
    """
    if not isinstance(payload, dict) or not payload:
        raise InitDataError("empty login payload")
    if not bot_token:
        raise InitDataError("server misconfigured: BOT_TOKEN not set")

    # Só valores escalares entram no data_check_string. Um `dict`/`list` vindo do
    # JSON do cliente não existe no widget e nunca teria representação estável —
    # recusar é mais seguro que serializar à sorte.
    data: dict[str, str] = {}
    for key, value in payload.items():
        if key == "hash":
            continue
        if isinstance(value, bool) or value is None:
            raise InitDataError(f"invalid field type: {key}")
        if isinstance(value, (dict, list, tuple, set)):
            raise InitDataError(f"invalid field type: {key}")
        data[str(key)] = str(value)

    received_hash = payload.get("hash")
    if not received_hash or not isinstance(received_hash, str):
        raise InitDataError("missing hash")

    data_check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = _login_widget_secret(bot_token)
    expected = hmac.new(secret, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash.lower()):
        raise InitDataError("hash mismatch")

    try:
        auth_date = int(data.get("auth_date", ""))
    except (TypeError, ValueError) as exc:
        raise InitDataError("missing or invalid auth_date") from exc

    age = int(time.time()) - auth_date
    if age < 0:
        # Mesma tolerância de relógio do initData (5min de "futuro").
        if age < -300:
            raise InitDataError("auth_date in the future")
    elif age > max_age:
        raise InitDataError(f"login payload expired (age={age}s)")

    try:
        user_id = int(data.get("id", ""))
    except (TypeError, ValueError) as exc:
        raise InitDataError("missing or invalid id") from exc
    if user_id <= 0:
        # ⚠️ O espaço NEGATIVO é o da Fase 2 (contas sem Telegram). Um payload de
        # widget que o reclamasse colidiria com um jogador de email.
        raise InitDataError("id must be positive")

    out = dict(data)
    out["id"] = user_id
    out["auth_date"] = auth_date
    return out


def extract_login_widget_user_id(payload: dict, bot_token: str) -> int:
    """Valida e devolve o id do Telegram, ou levanta ``InitDataError``."""
    return int(validate_login_widget(payload, bot_token)["id"])
