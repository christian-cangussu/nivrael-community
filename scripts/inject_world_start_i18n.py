"""Multi-Servidor — "começar neste servidor" (world-start) i18n.

MINI-APP ONLY (miniapp/i18n/{pt,en,es}.json). The world-start welcome screen lives
entirely in the mini-app (App root render on needs_world_start). Re-runnable:
upserts this wave's uniquely-namespaced keys (world_start_*) and re-dumps each
locale indent=4 + ensure_ascii=False + trailing newline.

pt = PT-BR (você/seu). No placeholders in these strings.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MINIAPP = {
    "pt": {
        "world_start_title": "Novo servidor, novo começo",
        "world_start_desc": "Você ainda não tem personagem neste servidor. Comece do zero aqui — a conta é a mesma, mas o progresso deste mundo é totalmente separado.",
        "world_start_btn": "Começar neste servidor",
        "world_start_loading": "Forjando seu destino…",
        "world_start_error": "Não foi possível começar aqui. Tente de novo.",
    },
    "en": {
        "world_start_title": "A new server, a fresh start",
        "world_start_desc": "You don't have a character on this server yet. Start from zero here — same account, but this world's progress is fully separate.",
        "world_start_btn": "Start on this server",
        "world_start_loading": "Forging your destiny…",
        "world_start_error": "Couldn't start here. Try again.",
    },
    "es": {
        "world_start_title": "Servidor nuevo, comienzo nuevo",
        "world_start_desc": "Aún no tienes personaje en este servidor. Empieza desde cero aquí — la misma cuenta, pero el progreso de este mundo es totalmente separado.",
        "world_start_btn": "Empezar en este servidor",
        "world_start_loading": "Forjando tu destino…",
        "world_start_error": "No se pudo empezar aquí. Inténtalo de nuevo.",
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
        data[k] = v  # overwrite — keys are uniquely namespaced to this wave
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
