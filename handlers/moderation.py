"""Filtro de moderação do grupo público — P0 LEGAL (hotfix "A Volta", 2026-07-07).

Contexto: um link CSAM foi postado no grupo Nivrael (incidente ~30/06; o user foi
banido manualmente) e o filtro prometido publicamente nunca tinha sido feito.
Este módulo fecha essa promessa.

Comportamento (SÓ em grupos — ``chat.type in (group, supergroup)``; ZERO impacto
nos comandos DM do jogo):
  • Mensagem (ou edição) de NÃO-admin contendo URL fora da whitelist — entities
    ``url``/``text_link`` em texto ou caption, mais um regex de segurança — ou
    encaminhada de um canal desconhecido → delete imediato + log persistente no
    ``admin_audit_log`` (control DB — sobrevive a wipe de mundo) + DM ao owner
    com o conteúdo removido + DM de aviso ao user (i18n ×3).
  • Reincidência: ao atingir ``MOD_STRIKE_LIMIT`` (default 3) o user é
    silenciado no grupo (``restrict``, sem permissões) e o owner é notificado.
  • Isentos: ``ADMIN_USERS``, admins do grupo (cache 10 min), admin anônimo
    (``sender_chat == chat``), auto-forward do canal vinculado e o próprio bot.
  • Whitelist: ``t.me/<username do bot>`` + ``MOD_WHITELIST_TME`` (nomes t.me
    aprovados, ex.: o grupo) + ``MOD_WHITELIST_DOMAINS`` (domínios aprovados).

Fail-closed de propósito: se a checagem "é admin do grupo?" falhar na API, a
mensagem É apagada — apagar por engano é recuperável (o owner recebe o conteúdo
na DM e pode repostar); deixar passar um link ilegal não é.

Requisito operacional (Passo 0 do hotfix): o bot precisa ser admin do grupo com
``can_delete_messages`` (+ ``can_restrict_members`` para o auto-mute). Se faltar
permissão, o owner recebe uma DM explicando exatamente o que ativar.

Persistência de strikes: linhas ``action='chat_link_delete'`` no
``admin_audit_log`` do control DB (nenhuma migration de mundo necessária; o
schema já existe via ``bootstrap_control_db``). Se o control DB estiver
indisponível, degrada para um contador em memória (reseta no deploy — aceitável
como fallback, nunca como caminho principal).
"""

import html
import json
import logging
import re
import time
from urllib.parse import urlparse, parse_qs

from sqlalchemy import text as sa_text
from telegram import ChatPermissions
from telegram.constants import MessageEntityType
from telegram.ext import ApplicationHandlerStop, ContextTypes, MessageHandler, filters

from config import ADMIN_USERS, MOD_STRIKE_LIMIT, MOD_WHITELIST_DOMAINS, MOD_WHITELIST_TME
from core.i18n import t
from database.db import current_world_key, get_session_factory
from database.control_db import get_control_session_factory

logger = logging.getLogger(__name__)

MOD_ACTION = "chat_link_delete"

# Regex de segurança para URLs sem entity (o Telegram gera entities para a
# maioria dos links, mas não custa cobrir texto colado de forma estranha).
_URL_RE = re.compile(r"(?:(?:https?|tg)://|www\.|t\.me/)[^\s<>\"']+", re.IGNORECASE)

_TG_HOSTS = {"t.me", "telegram.me", "telegram.dog"}

# Cache "é admin do grupo?" — evita um get_chat_member por mensagem.
_ADMIN_CACHE_TTL = 600.0  # 10 min
_admin_cache: dict[tuple[int, int], tuple[bool, float]] = {}

# Fallback em memória quando o control DB está fora (ver docstring).
_mem_strikes: dict[int, int] = {}


# ── Detecção de links ────────────────────────────────────────────────────────

def _extract_urls(message) -> list[str]:
    urls: list[str] = []
    for parse, ents in (
        (message.parse_entities, message.entities),
        (message.parse_caption_entities, message.caption_entities),
    ):
        if not ents:
            continue
        for entity, covered in parse([MessageEntityType.URL, MessageEntityType.TEXT_LINK]).items():
            urls.append(entity.url if entity.type == MessageEntityType.TEXT_LINK else covered)
    for raw in (message.text, message.caption):
        if raw:
            urls.extend(_URL_RE.findall(raw))
    return urls


def _tme_allowed(bot_username: str | None) -> set[str]:
    allowed = set(MOD_WHITELIST_TME)
    if bot_username:
        allowed.add(bot_username.lower())
    return allowed


def _is_whitelisted(url: str, bot_username: str | None) -> bool:
    u = url.strip().rstrip(").,;>]'\"")
    if "://" not in u:
        u = "http://" + u
    try:
        parsed = urlparse(u)
    except ValueError:
        return False

    if parsed.scheme == "tg":
        # tg://resolve?domain=<nome> é o equivalente deep-link de t.me/<nome>
        domain = (parse_qs(parsed.query).get("domain") or [""])[0].lower()
        return domain in _tme_allowed(bot_username)

    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host:
        return False
    if host in _TG_HOSTS:
        first_seg = parsed.path.lstrip("/").split("/")[0].lower()
        # t.me/+<invite> e t.me/joinchat/<hash> nunca batem num nome aprovado
        return first_seg in _tme_allowed(bot_username)
    return host in MOD_WHITELIST_DOMAINS or any(
        host.endswith("." + d) for d in MOD_WHITELIST_DOMAINS
    )


def _violating_urls(message, bot_username: str | None) -> list[str]:
    return [u for u in _extract_urls(message) if not _is_whitelisted(u, bot_username)]


def _unknown_channel_forward(message, bot_username: str | None) -> bool:
    origin = getattr(message, "forward_origin", None)
    if origin is None or getattr(message, "is_automatic_forward", False):
        return False
    chat_ = getattr(origin, "chat", None)  # só MessageOriginChannel tem .chat
    if chat_ is None or chat_.type != "channel":
        return False
    uname = (chat_.username or "").lower()
    return not (uname and uname in _tme_allowed(bot_username))


# ── Isenções ─────────────────────────────────────────────────────────────────

async def _is_group_admin(chat, user_id: int, context) -> bool:
    key = (chat.id, user_id)
    now = time.monotonic()
    hit = _admin_cache.get(key)
    if hit and hit[1] > now:
        return hit[0]
    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
        is_admin = member.status in ("administrator", "creator")
    except Exception:
        # Fail-closed (ver docstring): sem cache do erro — tenta de novo na próxima.
        logger.warning("moderation: get_chat_member falhou p/ %s em %s — fail-closed", user_id, chat.id)
        return False
    _admin_cache[key] = (is_admin, now + _ADMIN_CACHE_TTL)
    return is_admin


async def _is_exempt(chat, user, message, context) -> bool:
    if getattr(message, "is_automatic_forward", False):
        return True  # post do canal vinculado ao grupo
    if message.sender_chat is not None and message.sender_chat.id == chat.id:
        return True  # admin anônimo (fala como o grupo)
    if user is None:
        return False
    if user.id in ADMIN_USERS or user.id == context.bot.id:
        return True
    return await _is_group_admin(chat, user.id, context)


# ── Persistência / notificações ──────────────────────────────────────────────

async def _record_strike(bot_id: int, user_id: int, detail: dict) -> int:
    """Grava o strike no admin_audit_log (control DB) e devolve o total do user
    (incluindo este). Fallback em memória se o control DB falhar."""
    sm = get_control_session_factory()
    if sm is not None:
        try:
            async with sm() as session:
                await session.execute(
                    sa_text(
                        "INSERT INTO admin_audit_log (admin_id, world_key, target_id, action, detail) "
                        "VALUES (:a, :w, :t, :ac, CAST(:d AS JSONB))"
                    ),
                    {
                        "a": bot_id,
                        "w": current_world_key(),
                        "t": user_id,
                        "ac": MOD_ACTION,
                        "d": json.dumps(detail, ensure_ascii=False, default=str),
                    },
                )
                count = (
                    await session.execute(
                        sa_text(
                            "SELECT COUNT(*) FROM admin_audit_log "
                            "WHERE action = :ac AND target_id = :t"
                        ),
                        {"ac": MOD_ACTION, "t": user_id},
                    )
                ).scalar_one()
                await session.commit()
                return int(count)
        except Exception:
            logger.warning("moderation: log de strike no control DB falhou — fallback em memória", exc_info=True)
    _mem_strikes[user_id] = _mem_strikes.get(user_id, 0) + 1
    return _mem_strikes[user_id]


async def _player_lang(user_id: int) -> str:
    try:
        async with get_session_factory()() as session:
            lang = (
                await session.execute(
                    sa_text("SELECT language FROM players WHERE telegram_id = :tid"),
                    {"tid": user_id},
                )
            ).scalar_one_or_none()
            return lang or "pt"
    except Exception:
        return "pt"


def _user_label(user) -> str:
    if user is None:
        return "?"
    uname = f" @{user.username}" if user.username else ""
    return f"{html.escape(user.full_name or '')}{uname} (id <code>{user.id}</code>)"


async def _notify_owner(context, html_text: str) -> None:
    for admin_id in ADMIN_USERS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=html_text, parse_mode="HTML")
        except Exception:
            logger.warning("moderation: DM ao owner %s falhou", admin_id)


# ── Handler principal ────────────────────────────────────────────────────────

async def moderation_filter(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if message is None or chat is None or chat.type not in ("group", "supergroup"):
        return

    bot_username = context.bot.username
    bad_urls = _violating_urls(message, bot_username)
    channel_fwd = _unknown_channel_forward(message, bot_username)
    if not bad_urls and not channel_fwd:
        return
    if await _is_exempt(chat, user, message, context):
        return

    chat_label = chat.title or "Nivrael"
    excerpt = (message.text or message.caption or "")[:800]
    reason = "forward de canal desconhecido" if channel_fwd and not bad_urls else "link fora da whitelist"

    try:
        await message.delete()
    except Exception as e:
        logger.error("moderation: delete falhou no chat %s: %s", chat.id, e)
        await _notify_owner(
            context,
            "⚠️ <b>Moderação:</b> detectei uma mensagem com link no grupo "
            f"<b>{html.escape(chat_label)}</b> mas <b>não consegui apagá-la</b>.\n"
            "Verifique se o bot é <b>admin do grupo com can_delete_messages</b> (Passo 0 do hotfix).\n\n"
            f"De: {_user_label(user)}\nMotivo: {reason}\n"
            f"Conteúdo:\n<pre>{html.escape(excerpt)}</pre>",
        )
        raise ApplicationHandlerStop

    strikes = await _record_strike(
        context.bot.id,
        user.id if user else 0,
        {
            "chat_id": chat.id,
            "chat_title": chat_label,
            "reason": reason,
            "urls": bad_urls[:10],
            "excerpt": excerpt[:400],
            "username": getattr(user, "username", None),
        },
    )

    muted = False
    if user is not None and strikes >= MOD_STRIKE_LIMIT:
        try:
            await context.bot.restrict_chat_member(
                chat.id, user.id, permissions=ChatPermissions.no_permissions()
            )
            muted = True
        except Exception:
            logger.warning("moderation: restrict falhou p/ %s em %s (falta can_restrict_members?)",
                           user.id, chat.id, exc_info=True)

    if user is not None:
        lang = await _player_lang(user.id)
        try:
            if muted:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=t(lang, "mod_muted_dm", chat=chat_label, limit=MOD_STRIKE_LIMIT),
                )
            else:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=t(lang, "mod_warn_dm", chat=chat_label, strikes=strikes, limit=MOD_STRIKE_LIMIT),
                )
        except Exception:
            pass  # user nunca abriu DM com o bot — nada a fazer

    status_line = (
        f"🔇 <b>SILENCIADO</b> ({strikes}/{MOD_STRIKE_LIMIT} strikes)"
        if muted
        else f"strike <b>{strikes}/{MOD_STRIKE_LIMIT}</b>"
    )
    if user is not None and strikes >= MOD_STRIKE_LIMIT and not muted:
        status_line += " — ⚠️ auto-mute FALHOU (dar can_restrict_members ao bot ou agir manualmente)"
    urls_line = ("\nLinks: " + html.escape(", ".join(bad_urls[:5]))) if bad_urls else ""
    await _notify_owner(
        context,
        f"🛡️ <b>Moderação</b> — mensagem apagada em <b>{html.escape(chat_label)}</b>\n"
        f"De: {_user_label(user)}\nMotivo: {reason} — {status_line}{urls_line}\n"
        f"Conteúdo removido:\n<pre>{html.escape(excerpt)}</pre>",
    )

    # Mensagem tratada (e apagada): nenhum outro handler deve processá-la.
    raise ApplicationHandlerStop


async def group_game_command_guard(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """O jogo é DM-only. Sem este guard, um /start ou /status digitado DENTRO
    do grupo faria o bot responder ALI (handlers respondem no chat de origem),
    expondo os dados do próprio jogador para o grupo inteiro e poluindo o chat.
    Engole silenciosamente TODO comando vindo de grupo (o jogador usa o privado,
    como sempre). ADMIN_USERS ficam isentos — comandos admin (/startwar,
    /admin_announce, …) continuam utilizáveis onde o owner quiser."""
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if message is None or chat is None or chat.type not in ("group", "supergroup"):
        return
    if user is not None and user.id in ADMIN_USERS:
        return
    raise ApplicationHandlerStop


def setup_moderation_handlers(app) -> None:
    """Regista o filtro num group NEGATIVO (-100): roda antes de qualquer handler
    de jogo, e ApplicationHandlerStop impede o resto quando a mensagem é tratada.
    O filtro só olha updates de grupo — DMs (o jogo inteiro) passam direto.
    Em -99, o guard DM-only engole comandos de jogo digitados em grupos (depois
    do filtro de links, antes de qualquer CommandHandler do jogo)."""
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, moderation_filter), group=-100)
    app.add_handler(
        MessageHandler(filters.ChatType.GROUPS & filters.COMMAND, group_game_command_guard),
        group=-99,
    )
