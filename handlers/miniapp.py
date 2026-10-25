import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from config import MINIAPP_URL
from core.i18n import t
from core.utils import _get_player, normalize_lang, rate_limit, safe_handler
from database.db import get_session_factory

logger = logging.getLogger(__name__)


@safe_handler
@rate_limit(1)
async def miniapp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open Telegram Mini App with a native web_app button."""
    user = update.effective_user
    if not user:
        return

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        lang = normalize_lang(player.language) if player else "pt"

    if not update.message:
        return

    if not MINIAPP_URL:
        await update.message.reply_text(t(lang, "miniapp_unavailable"))
        return

    text = t(lang, "miniapp_intro")
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(t(lang, "btn_open_miniapp"), web_app=WebAppInfo(url=MINIAPP_URL))]]
    )
    await update.message.reply_text(text, reply_markup=keyboard)
