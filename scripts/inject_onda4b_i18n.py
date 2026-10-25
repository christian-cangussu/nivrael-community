"""Onda 4b — Travel between continents i18n injection.

Idempotent: adds ONLY missing keys, then re-dumps each locale file sorted +
indent=4 + ensure_ascii=False (mirrors scripts/inject_onda4a_i18n.py).

Surfaces:
  * CHAT (locales/{pt,en,es}.json): the /viajar menu + destination detail
    (cost/cooldown disclosure, Lei §1) + arrival, AND the continent IDENTITY
    strings (continent_spec_* + native_tag_*) — these are resolved SERVER-SIDE
    by core.i18n (which reads locales/), so the mini-app receives them already
    localized inside the world/travel payload. They live in the CHAT files only.
  * MINIAPP (miniapp/i18n/{pt,en,es}.json): the TravelModal chrome (the "here"
    badge, the action/confirm buttons, the cancel) the client renders via t().

Reuses existing continent name/subtitle/lore keys (continent_linghe, ...) from
v16.0 — NOT re-added here.

pt = PT-BR (você/seu, custo, ativo). Placeholders {…} stay ASCII and appear at
most ONCE per string (t() replaces only the first occurrence).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cross-surface keys — live in BOTH the chat and the mini-app dicts.
_SHARED = {
    "pt": {
        "travel_title": "Viajar",
        "travel_intro": "A passagem entre continentes é longa e custa pedras espirituais — mas o mundo inteiro é seu.",
        "travel_changes_note": "Ao viajar, sua Praça, suas caçadas e quem o recruta mudam para o novo continente.",
        "travel_wipe_teaser": "Masmorras, ervas e minérios nativos de cada continente despertam por completo no novo mundo.",
        "travel_locked_demonic": "Trancado: só cultivadores do Caminho Demoníaco entram em Mòyǔ.",
        "travel_on_cooldown": "Você ainda se recupera da última viagem. Faltam {time}.",
        "travel_not_enough_stones": "Pedras espirituais insuficientes. Custo: {cost} 🪨",
        "travel_already_here": "Você já está neste continente.",
        "travel_failed": "A viagem falhou. Tente novamente.",
        "travel_confirm": "Confirmar viagem",
    },
    "en": {
        "travel_title": "Travel",
        "travel_intro": "The passage between continents is long and costs spirit stones — but the whole world is yours.",
        "travel_changes_note": "When you travel, your Plaza, your hunts and who recruits you change to the new continent.",
        "travel_wipe_teaser": "Each continent's native dungeons, herbs and ores fully awaken in the new world.",
        "travel_locked_demonic": "Locked: only Demonic Path cultivators may enter Mòyǔ.",
        "travel_on_cooldown": "You're still recovering from your last journey. {time} left.",
        "travel_not_enough_stones": "Not enough spirit stones. Cost: {cost} 🪨",
        "travel_already_here": "You're already in this continent.",
        "travel_failed": "The journey failed. Try again.",
        "travel_confirm": "Confirm travel",
    },
    "es": {
        "travel_title": "Viajar",
        "travel_intro": "El paso entre continentes es largo y cuesta piedras espirituales — pero el mundo entero es tuyo.",
        "travel_changes_note": "Al viajar, tu Plaza, tus cacerías y quién te recluta cambian al nuevo continente.",
        "travel_wipe_teaser": "Las mazmorras, hierbas y minerales nativos de cada continente despiertan por completo en el nuevo mundo.",
        "travel_locked_demonic": "Bloqueado: solo cultivadores de la Senda Demoníaca entran en Mòyǔ.",
        "travel_on_cooldown": "Aún te recuperas del último viaje. Faltan {time}.",
        "travel_not_enough_stones": "Piedras espirituales insuficientes. Costo: {cost} 🪨",
        "travel_already_here": "Ya estás en este continente.",
        "travel_failed": "El viaje falló. Inténtalo de nuevo.",
        "travel_confirm": "Confirmar viaje",
    },
}

# Continent IDENTITY (server-resolved via core.i18n → chat files only).
_IDENTITY = {
    "pt": {
        "continent_spec_linghe": "Centro Sagrado — Qi universal, lar das grandes seitas.",
        "continent_spec_qianhe": "Têmpera Corporal — água, gelo e resistência.",
        "continent_spec_yanshan": "Técnica & Alquimia — vento, madeira e luz.",
        "continent_spec_fenghuo": "Forja & Combate — fogo, relâmpago e caos.",
        "continent_spec_moyu": "O Proibido — artes sombrias, caminho demoníaco.",
        "native_tag_universal": "Qi Universal",
        "native_tag_sects": "Grandes Seitas",
        "native_tag_body": "Têmpera Corporal",
        "native_tag_ores": "Minérios Raros",
        "native_tag_herbs": "Ervas Raras",
        "native_tag_alchemy": "Alquimia",
        "native_tag_forge": "Forja",
        "native_tag_combat": "Combate",
        "native_tag_forbidden": "Técnicas Proibidas",
        "native_tag_demonic": "Cultivo Demoníaco",
    },
    "en": {
        "continent_spec_linghe": "Sacred Center — universal Qi, home of the great sects.",
        "continent_spec_qianhe": "Body Tempering — water, ice and endurance.",
        "continent_spec_yanshan": "Technique & Alchemy — wind, wood and light.",
        "continent_spec_fenghuo": "Forge & Combat — fire, lightning and chaos.",
        "continent_spec_moyu": "The Forbidden — dark arts, the demonic path.",
        "native_tag_universal": "Universal Qi",
        "native_tag_sects": "Great Sects",
        "native_tag_body": "Body Tempering",
        "native_tag_ores": "Rare Ores",
        "native_tag_herbs": "Rare Herbs",
        "native_tag_alchemy": "Alchemy",
        "native_tag_forge": "Forging",
        "native_tag_combat": "Combat",
        "native_tag_forbidden": "Forbidden Techniques",
        "native_tag_demonic": "Demonic Cultivation",
    },
    "es": {
        "continent_spec_linghe": "Centro Sagrado — Qi universal, hogar de las grandes sectas.",
        "continent_spec_qianhe": "Temple Corporal — agua, hielo y resistencia.",
        "continent_spec_yanshan": "Técnica y Alquimia — viento, madera y luz.",
        "continent_spec_fenghuo": "Forja y Combate — fuego, relámpago y caos.",
        "continent_spec_moyu": "Lo Prohibido — artes oscuras, senda demoníaca.",
        "native_tag_universal": "Qi Universal",
        "native_tag_sects": "Grandes Sectas",
        "native_tag_body": "Temple Corporal",
        "native_tag_ores": "Minerales Raros",
        "native_tag_herbs": "Hierbas Raras",
        "native_tag_alchemy": "Alquimia",
        "native_tag_forge": "Forja",
        "native_tag_combat": "Combate",
        "native_tag_forbidden": "Técnicas Prohibidas",
        "native_tag_demonic": "Cultivo Demoníaco",
    },
}

CHAT = {
    "pt": {
        **_SHARED["pt"],
        **_IDENTITY["pt"],
        "travel_cost_label": "Custo",
        "travel_cooldown_label": "Descanso",
        "travel_back": "‹ Voltar",
        "travel_arrived": "Você chegou a {continent}.",
    },
    "en": {
        **_SHARED["en"],
        **_IDENTITY["en"],
        "travel_cost_label": "Cost",
        "travel_cooldown_label": "Cooldown",
        "travel_back": "‹ Back",
        "travel_arrived": "You have arrived in {continent}.",
    },
    "es": {
        **_SHARED["es"],
        **_IDENTITY["es"],
        "travel_cost_label": "Costo",
        "travel_cooldown_label": "Descanso",
        "travel_back": "‹ Volver",
        "travel_arrived": "Has llegado a {continent}.",
    },
}

MINIAPP = {
    "pt": {
        **_SHARED["pt"],
        "travel_here": "Você está aqui",
        "travel_btn": "Viajar",
        "travel_confirm_q": "Viajar para {name} por {cost} 🪨?",
        "travel_cancel": "Cancelar",
    },
    "en": {
        **_SHARED["en"],
        "travel_here": "You are here",
        "travel_btn": "Travel",
        "travel_confirm_q": "Travel to {name} for {cost} 🪨?",
        "travel_cancel": "Cancel",
    },
    "es": {
        **_SHARED["es"],
        "travel_here": "Estás aquí",
        "travel_btn": "Viajar",
        "travel_confirm_q": "¿Viajar a {name} por {cost} 🪨?",
        "travel_cancel": "Cancelar",
    },
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
