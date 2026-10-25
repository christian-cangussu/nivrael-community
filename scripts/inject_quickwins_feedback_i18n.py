"""scripts/inject_quickwins_feedback_i18n.py — Quick-wins do feedback 2026-06-10.

Idempotent injector (clone of inject_onda5_i18n.py). Adds ONLY missing keys,
keeping pt/en/es in parity. Two new strings, each surface-specific:
  * _CHAT — `inv_use_pill_max`     — the chat bulk "use all up to N" button
  * _MINI — `pill_panel_custom_ph` — the mini-app custom-quantity input placeholder

Items A (karma −1000 achievement) and D (Abyssal Conqueror) need NO i18n keys:
achievement name/description render straight from the seed (English-in-DB, like
all 30 others) and disclosure already works. Item C reuses `dungeon_hp_label`.

Rules: pt = PT-BR (você/seu, ativo); every {token} placeholder appears at most
ONCE per string; placeholders stay ASCII.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LANGS = ("pt", "en", "es")

# ── _CHAT — backend/chat-only (handlers/inventory._pills_tab) ──────────────────
_CHAT = {
    "pt": {"inv_use_pill_max": "💊 Tudo ×{n}"},
    "en": {"inv_use_pill_max": "💊 All ×{n}"},
    "es": {"inv_use_pill_max": "💊 Todo ×{n}"},
}

# ── _MINI — mini-app-only (PillUsePanel custom-quantity input) ─────────────────
_MINI = {
    "pt": {"pill_panel_custom_ph": "Quantidade (máx {max})"},
    "en": {"pill_panel_custom_ph": "Quantity (max {max})"},
    "es": {"pill_panel_custom_ph": "Cantidad (máx {max})"},
}


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
    for lang, adds in _CHAT.items():
        p = os.path.join(ROOT, "locales", f"{lang}.json")
        before, added = _apply(p, adds)
        print(f"chat    {lang}: {before} -> {before + added} (+{added})")
    for lang, adds in _MINI.items():
        p = os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json")
        before, added = _apply(p, adds)
        print(f"miniapp {lang}: {before} -> {before + added} (+{added})")


if __name__ == "__main__":
    main()
