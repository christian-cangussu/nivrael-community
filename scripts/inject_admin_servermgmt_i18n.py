"""Admin server-management — rename + flag toggles i18n (mini-app only).

Adds the keys for the AdminServerCard rename input + monetization/public/code
toggles. Re-runnable; upserts uniquely-namespaced admin_* keys and re-dumps each
locale indent=4 + ensure_ascii=False + trailing newline. pt = PT-BR.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MINIAPP = {
    "pt": {
        "admin_rename_ph": "Nome do mundo",
        "admin_rename_btn": "Renomear",
        "admin_renamed": "Nome atualizado",
        "admin_flags_title": "Acesso & monetização",
        "admin_flag_monetized": "Monetizado",
        "admin_flag_sandbox": "Sandbox",
        "admin_flag_public": "Público",
        "admin_flag_private": "Privado",
        "admin_flag_code": "Com código",
        "admin_flag_nocode": "Sem código",
        "admin_flags_saved": "Acesso atualizado",
    },
    "en": {
        "admin_rename_ph": "World name",
        "admin_rename_btn": "Rename",
        "admin_renamed": "Name updated",
        "admin_flags_title": "Access & monetization",
        "admin_flag_monetized": "Monetized",
        "admin_flag_sandbox": "Sandbox",
        "admin_flag_public": "Public",
        "admin_flag_private": "Private",
        "admin_flag_code": "Code-gated",
        "admin_flag_nocode": "No code",
        "admin_flags_saved": "Access updated",
    },
    "es": {
        "admin_rename_ph": "Nombre del mundo",
        "admin_rename_btn": "Renombrar",
        "admin_renamed": "Nombre actualizado",
        "admin_flags_title": "Acceso y monetización",
        "admin_flag_monetized": "Monetizado",
        "admin_flag_sandbox": "Sandbox",
        "admin_flag_public": "Público",
        "admin_flag_private": "Privado",
        "admin_flag_code": "Con código",
        "admin_flag_nocode": "Sin código",
        "admin_flags_saved": "Acceso actualizado",
    },
}


def _apply(path, additions):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    before = len(data)
    added = 0
    for k, v in additions.items():
        if k not in data:
            added += 1
        data[k] = v
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write("\n")
    return before, len(data), added


def main():
    for lang, adds in MINIAPP.items():
        before, after, added = _apply(
            os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), adds)
        print(f"miniapp {lang}: {before} -> {after} (+{added})")


if __name__ == "__main__":
    main()
