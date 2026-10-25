"""
Visual Engine — Epic emoji art templates for key game moments.

All art uses t() for translated text, so the same function works across
EN, PT, and ES without hardcoded strings inside the art frames.
"""
from core.i18n import t
from core.utils import escape_markdown


# One art emoji per realm index (0–10)
_REALM_EMOJIS = ["🪨", "☯️", "🏯", "🔮", "👻", "⚡", "🐉", "🌟", "💎", "👑", "🌸"]

# Foundation quality emoji mapping
_FOUNDATION_EMOJIS = {
    "low": "🪨",
    "medium": "🏯",
    "high": "🔮",
    "perfect": "💎",
}

# Core quality emoji mapping
_CORE_EMOJIS = {
    "flawed": "🌑",
    "normal": "💠",
    "superior": "🔮",
    "perfect": "💎",
}

_SEP = "—" * 20


def realm_up_art(realm: int, realm_name: str, lang: str = "en") -> str:
    """
    Render a full-width breakthrough banner for a realm advancement.

    Args:
        realm:      New realm index (used for emoji selection).
        realm_name: Localised realm name string (from REALM_NAMES).
        lang:       Player language code.

    Returns:
        Multi-line string safe for Telegram Markdown parse mode.
    """
    e = _REALM_EMOJIS[min(realm, len(_REALM_EMOJIS) - 1)]
    header = t(lang, "art_bt_header", emoji=e)
    heavens = t(lang, "art_bt_heavens")
    safe_realm = escape_markdown(realm_name)
    return (
        f"{_SEP}\n"
        f"{header}\n"
        f"{_SEP}\n\n"
        f"✨ *{safe_realm}* ✨\n\n"
        f"{heavens}\n\n"
        f"{_SEP}"
    )


def sublayer_up_art(realm_display: str, lang: str = "en") -> str:
    """
    Smaller breakthrough banner for a sub-layer advancement (no realm change).

    Args:
        realm_display: Full realm+sub-layer display string.
        lang:          Player language code.

    Returns:
        Multi-line string safe for Telegram Markdown parse mode.
    """
    safe_display = escape_markdown(realm_display)
    header = t(lang, "art_sublayer_header")
    return (
        f"⚡ {header} ⚡\n\n"
        f"☯️ *{safe_display}*\n\n"
        f"{t(lang, 'art_sublayer_msg')}"
    )


def gacha_legendary_art(item_name: str, lang: str = "en") -> str:
    """
    Golden shimmer banner shown when the player pulls a legendary item.

    Args:
        item_name: Localised item name.
        lang:      Player language code.

    Returns:
        Multi-line string safe for Telegram Markdown parse mode.
    """
    safe_name = escape_markdown(item_name)
    header = t(lang, "art_legendary_header")
    return (
        f"✨🌟✨🌟✨🌟✨🌟✨\n\n"
        f"  {header}\n\n"
        f"  *{safe_name}*\n\n"
        f"✨🌟✨🌟✨🌟✨🌟✨"
    )


def tribulation_thunder_art(lang: str = "en") -> str:
    """
    Stormy announcement banner shown at the start of a tribulation.

    Args:
        lang: Player language code.

    Returns:
        Multi-line string safe for Telegram Markdown parse mode.
    """
    sky = t(lang, "art_trib_sky")
    echo = t(lang, "art_trib_echo")
    header = t(lang, "art_trib_header")
    return (
        f"⛈️⚡⛈️⚡⛈️⚡⛈️\n\n"
        f"{sky}\n"
        f"{echo}\n\n"
        f"⚡ *{header}* ⚡\n\n"
        f"⛈️⚡⛈️⚡⛈️⚡⛈️"
    )


def foundation_art(quality: str, quality_label: str, lang: str = "en") -> str:
    """
    Reveal banner shown when the Foundation Trial result is announced.

    Args:
        quality:       Foundation quality key ("low", "medium", "high", "perfect").
        quality_label: Translated quality label (e.g. "Sólida", "Perfeita").
        lang:          Player language code.

    Returns:
        Multi-line string safe for Telegram Markdown parse mode.
    """
    e = _FOUNDATION_EMOJIS.get(quality, "🏯")
    safe_label = escape_markdown(quality_label)
    header = t(lang, "art_foundation_header", emoji=e)
    msg = t(lang, "art_foundation_msg")
    return (
        f"{_SEP}\n"
        f"{header}\n"
        f"{_SEP}\n\n"
        f"  *{safe_label}*\n\n"
        f"  {msg}\n\n"
        f"{_SEP}"
    )


def core_formation_art(quality: str, quality_label: str, lang: str = "en") -> str:
    """
    Crystallisation banner shown when Golden Core formation completes.

    Args:
        quality:       Core quality key ("flawed", "normal", "hollow", "perfect").
        quality_label: Translated quality label.
        lang:          Player language code.

    Returns:
        Multi-line string safe for Telegram Markdown parse mode.
    """
    e = _CORE_EMOJIS.get(quality, "💠")
    safe_label = escape_markdown(quality_label)
    header = t(lang, "art_core_header", emoji=e)
    msg = t(lang, "art_core_msg")
    return (
        f"{_SEP}\n"
        f"{header}\n"
        f"{_SEP}\n\n"
        f"  *{safe_label}*\n\n"
        f"  {msg}\n\n"
        f"{_SEP}"
    )
