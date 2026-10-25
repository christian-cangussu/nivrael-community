"""2026-06-01 weekend bug-fix sprint — i18n additions.

Idempotent upsert of the keys introduced by the weekend fixes. Currently just
the duel-result label that distinguishes an HP-advantage win from a true
luck/Dao tie (B1 duel tiebreaker fix). Mini-app only — duel_log_tiebreak lives
in miniapp/i18n, not the chat locales.

Run:  python scripts/inject_fixes_2026_06_01_i18n.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MINIAPP_ONLY = {
    "duel_log_tiebreak_hp": (
        "Decidido por vantagem de HP",
        "Decided by HP advantage",
        "Decidido por ventaja de HP",
    ),
}

LOCALES = ["pt", "en", "es"]


def _merge(path, keys):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    lang = os.path.splitext(os.path.basename(path))[0]
    idx = {"pt": 0, "en": 1, "es": 2}[lang]
    for key, vals in keys.items():
        data[key] = vals[idx]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return len(keys)


def main():
    for lang in LOCALES:
        n = _merge(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), MINIAPP_ONLY)
        print(f"  [{lang}] miniapp +{n} keys")
    print("INJECTION COMPLETE (2026-06-01 fixes)")


if __name__ == "__main__":
    main()
