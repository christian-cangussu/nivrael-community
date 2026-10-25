"""scripts/inject_mv1_i18n.py — MV-1 Mundo Vivo v2: dungeons ancoradas i18n.

Idempotent injector (convenção inject_onda5_i18n.py). Adds ONLY missing keys
to both surfaces, keeping pt/en/es in parity:
  * _CHAT — chat-only keys (locales/) — lista /dungeons, recusa, horizonte
  * _MINI — mini-app-only keys (miniapp/i18n/) — admin flag labels, DungeonsTab

Rules: pt = PT-BR (você/seu); every {token} placeholder appears at most ONCE
per string (t() replaces only the first); placeholders stay ASCII.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CHAT = {
    "pt": {
        "dng_elsewhere_header": "🧭 *Além do horizonte*",
        "dng_elsewhere_line": "{emoji} {name} guarda {n} portais",
        "dng_btn_travel": "⛵ Viajar",
        "dng_wrong_continent": "🧭 Este portal fica em {emoji} {name}. Viaje até lá para cruzá-lo.",
        "dng_regional_bonus": "🧭 Tributo da terra: {emoji} {name} cedeu um material nativo!",
    },
    "en": {
        "dng_elsewhere_header": "🧭 *Beyond the horizon*",
        "dng_elsewhere_line": "{emoji} {name} holds {n} portals",
        "dng_btn_travel": "⛵ Travel",
        "dng_wrong_continent": "🧭 This portal lies in {emoji} {name}. Travel there to cross it.",
        "dng_regional_bonus": "🧭 Tribute of the land: {emoji} {name} yielded a native material!",
    },
    "es": {
        "dng_elsewhere_header": "🧭 *Más allá del horizonte*",
        "dng_elsewhere_line": "{emoji} {name} guarda {n} portales",
        "dng_btn_travel": "⛵ Viajar",
        "dng_wrong_continent": "🧭 Este portal está en {emoji} {name}. Viaja hasta allí para cruzarlo.",
        "dng_regional_bonus": "🧭 Tributo de la tierra: ¡{emoji} {name} cedió un material nativo!",
    },
}

_MINI = {
    "pt": {
        "feature_dungeons_regionais": "Dungeons Regionais",
        "feature_dungeons_regionais_desc": "Dungeons ancoradas por continente — só se veem os portais de onde você está. Ligado = mundo com geografia.",
        "dungeon_elsewhere_title": "🧭 Além do horizonte",
        "dungeon_elsewhere_line": "{emoji} {name} guarda {n} portais",
        "dungeon_wrong_continent": "Este portal fica em {emoji} {name}. Viaje até lá para cruzá-lo.",
        "dungeon_regional_bonus": "🧭 Tributo da terra: {emoji} {name} cedeu um material nativo!",
    },
    "en": {
        "feature_dungeons_regionais": "Regional Dungeons",
        "feature_dungeons_regionais_desc": "Dungeons anchored per continent — you only see the portals where you stand. On = a world with geography.",
        "dungeon_elsewhere_title": "🧭 Beyond the horizon",
        "dungeon_elsewhere_line": "{emoji} {name} holds {n} portals",
        "dungeon_wrong_continent": "This portal lies in {emoji} {name}. Travel there to cross it.",
        "dungeon_regional_bonus": "🧭 Tribute of the land: {emoji} {name} yielded a native material!",
    },
    "es": {
        "feature_dungeons_regionais": "Mazmorras Regionales",
        "feature_dungeons_regionais_desc": "Mazmorras ancladas por continente — solo se ven los portales de donde estás. Activado = mundo con geografía.",
        "dungeon_elsewhere_title": "🧭 Más allá del horizonte",
        "dungeon_elsewhere_line": "{emoji} {name} guarda {n} portales",
        "dungeon_wrong_continent": "Este portal está en {emoji} {name}. Viaja hasta allí para cruzarlo.",
        "dungeon_regional_bonus": "🧭 Tributo de la tierra: ¡{emoji} {name} cedió un material nativo!",
    },
}

LANGS = ("pt", "en", "es")
CHAT = {lc: dict(_CHAT[lc]) for lc in LANGS}
MINIAPP = {lc: dict(_MINI[lc]) for lc in LANGS}


def _apply(path, additions):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    before = len(data)
    added = 0
    for k, v in additions.items():
        if k not in data:
            data[k] = v
            added += 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4, sort_keys=True)
        fh.write("\n")
    return before, added


def main():
    for lang, adds in CHAT.items():
        p = os.path.join(ROOT, "locales", f"{lang}.json")
        before, added = _apply(p, adds)
        print(f"chat    {lang}: {before} -> {before + added} (+{added})")
    for lang, adds in MINIAPP.items():
        p = os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json")
        before, added = _apply(p, adds)
        print(f"miniapp {lang}: {before} -> {before + added} (+{added})")


if __name__ == "__main__":
    main()
