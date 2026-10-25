"""Onda 3 — NPC Cultivators + Heaven's Whispers i18n injection.

Idempotent: adds ONLY missing keys, then re-dumps each locale file sorted +
indent=4 + ensure_ascii=False (mirrors scripts/inject_v164c_i18n.py).

Surfaces:
  * CHAT (locales/{pt,en,es}.json): karma disclosure, /conf toggle label, the
    server-rendered whisper title/body templates (used by both the bell and the
    feed), + the shared feed chrome.
  * MINIAPP (miniapp/i18n/{pt,en,es}.json): leaderboard NPC chip, the NPC
    profile/challenge/moral UI, + the shared feed chrome.

pt = PT-BR (você/seu, ativo/artefato). Placeholders {…} stay ASCII and appear at
most ONCE per string (t() replaces only the first occurrence).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Shared feed chrome — lives in BOTH surfaces (chat /sussurros + mini-app modal).
_FEED = {
    "pt": {"wsp_feed_title": "Sussurros do Céu", "wsp_feed_empty": "O céu está em silêncio... por enquanto."},
    "en": {"wsp_feed_title": "Heaven's Whispers", "wsp_feed_empty": "The heavens are silent... for now."},
    "es": {"wsp_feed_title": "Susurros del Cielo", "wsp_feed_empty": "Los cielos están en silencio... por ahora."},
}

CHAT = {
    "pt": {
        **_FEED["pt"],
        "karma_event_combat_spare": "Poupar um inimigo derrotado",
        "karma_event_combat_execute": "Executar um inimigo derrotado",
        "notif_pref_whisper": "🌌 Sussurros do Céu",
        "wsp_npc_ascension_title": "🌠 Ascensão",
        "wsp_npc_ascension_body": "O cultivador {name} rompeu as portas celestes e ascendeu — dizem que o céu estremeceu sobre {place}.",
        "wsp_beast_tide_title": "🐾 Maré de Bestas",
        "wsp_beast_tide_body": "Uma maré de bestas espirituais assola {place}. Os cultivadores erguem barreiras contra a horda.",
        "wsp_demonic_intrusion_title": "👹 Intrusão Demoníaca",
        "wsp_demonic_intrusion_body": "Energia demoníaca irrompe em {place} — o véu entre os mundos racha e as sombras avançam.",
        "wsp_sect_recruiting_title": "🏯 Recrutamento",
        "wsp_sect_recruiting_body": "A {sect} procura novos discípulos em {place}. As portas da casa estão abertas aos dignos.",
        "wsp_ruin_discovered_title": "🏚️ Ruína Descoberta",
        "wsp_ruin_discovered_body": "Uma ruína antiga emergiu nas profundezas de {place}. Tesouros e perigos aguardam os ousados.",
    },
    "en": {
        **_FEED["en"],
        "karma_event_combat_spare": "Spare a defeated foe",
        "karma_event_combat_execute": "Execute a defeated foe",
        "notif_pref_whisper": "🌌 Heaven's Whispers",
        "wsp_npc_ascension_title": "🌠 Ascension",
        "wsp_npc_ascension_body": "The cultivator {name} shattered the celestial gates and ascended — they say the heavens trembled over {place}.",
        "wsp_beast_tide_title": "🐾 Beast Tide",
        "wsp_beast_tide_body": "A tide of spirit beasts ravages {place}. Cultivators raise barriers against the horde.",
        "wsp_demonic_intrusion_title": "👹 Demonic Intrusion",
        "wsp_demonic_intrusion_body": "Demonic energy erupts in {place} — the veil between worlds cracks and shadows advance.",
        "wsp_sect_recruiting_title": "🏯 Recruitment",
        "wsp_sect_recruiting_body": "The {sect} seeks new disciples in {place}. The house's gates stand open to the worthy.",
        "wsp_ruin_discovered_title": "🏚️ Ruin Discovered",
        "wsp_ruin_discovered_body": "An ancient ruin surfaced deep within {place}. Treasures and perils await the bold.",
    },
    "es": {
        **_FEED["es"],
        "karma_event_combat_spare": "Perdonar a un enemigo derrotado",
        "karma_event_combat_execute": "Ejecutar a un enemigo derrotado",
        "notif_pref_whisper": "🌌 Susurros del Cielo",
        "wsp_npc_ascension_title": "🌠 Ascensión",
        "wsp_npc_ascension_body": "El cultivador {name} quebró las puertas celestiales y ascendió — dicen que los cielos temblaron sobre {place}.",
        "wsp_beast_tide_title": "🐾 Marea de Bestias",
        "wsp_beast_tide_body": "Una marea de bestias espirituales asola {place}. Los cultivadores alzan barreras contra la horda.",
        "wsp_demonic_intrusion_title": "👹 Intrusión Demoníaca",
        "wsp_demonic_intrusion_body": "La energía demoníaca irrumpe en {place} — el velo entre los mundos se resquebraja y las sombras avanzan.",
        "wsp_sect_recruiting_title": "🏯 Reclutamiento",
        "wsp_sect_recruiting_body": "La {sect} busca nuevos discípulos en {place}. Las puertas de la casa están abiertas a los dignos.",
        "wsp_ruin_discovered_title": "🏚️ Ruina Descubierta",
        "wsp_ruin_discovered_body": "Una ruina antigua emergió en las profundidades de {place}. Tesoros y peligros aguardan a los audaces.",
    },
}

MINIAPP = {
    "pt": {
        **_FEED["pt"],
        "lb_npc_chip": "NPC",
        "npc_cult_title": "Cultivador",
        "npc_cult_honest_banner": "Eco de um cultivador real — um instantâneo de combate, não um jogador.",
        "npc_cult_challenge": "Desafiar",
        "npc_cult_cooldown": "Aguarde {min} min antes de outro desafio.",
        "npc_cult_no_qi": "Qi insuficiente para o desafio.",
        "npc_cult_busy": "Você já está em um duelo.",
        "npc_cult_no_hp": "HP esgotado — recupere-se primeiro.",
        "npc_cult_unavailable": "Nenhum oponente disponível por perto.",
        "npc_cult_victory_title": "Vitória!",
        "npc_cult_moral_prompt": "{name} caiu diante de você. Poupar ou executar?",
        "npc_cult_spare": "Poupar",
        "npc_cult_spare_hint": "A misericórdia eleva seu karma rumo ao Santo.",
        "npc_cult_execute": "Executar",
        "npc_cult_execute_hint": "A execução mancha seu karma rumo ao Abismo.",
        "npc_cult_won": "Você venceu",
        "npc_cult_lost": "Você foi derrotado",
        "npc_cult_spared": "Você poupou o cultivador.",
        "npc_cult_executed": "Você executou o cultivador.",
        "npc_cult_karma_now": "Karma agora: {value}",
        "npc_cult_path_crystallized": "Seu Caminho cristalizou — seus atos definiram quem você é.",
    },
    "en": {
        **_FEED["en"],
        "lb_npc_chip": "NPC",
        "npc_cult_title": "Cultivator",
        "npc_cult_honest_banner": "Echo of a real cultivator — a combat snapshot, not a player.",
        "npc_cult_challenge": "Challenge",
        "npc_cult_cooldown": "Wait {min} min before another challenge.",
        "npc_cult_no_qi": "Not enough Qi for the challenge.",
        "npc_cult_busy": "You are already in a duel.",
        "npc_cult_no_hp": "HP depleted — recover first.",
        "npc_cult_unavailable": "No opponent available nearby.",
        "npc_cult_victory_title": "Victory!",
        "npc_cult_moral_prompt": "{name} has fallen before you. Spare or execute?",
        "npc_cult_spare": "Spare",
        "npc_cult_spare_hint": "Mercy raises your karma toward Saint.",
        "npc_cult_execute": "Execute",
        "npc_cult_execute_hint": "Execution stains your karma toward the Abyss.",
        "npc_cult_won": "You won",
        "npc_cult_lost": "You were defeated",
        "npc_cult_spared": "You spared the cultivator.",
        "npc_cult_executed": "You executed the cultivator.",
        "npc_cult_karma_now": "Karma now: {value}",
        "npc_cult_path_crystallized": "Your Path crystallized — your acts defined who you are.",
    },
    "es": {
        **_FEED["es"],
        "lb_npc_chip": "NPC",
        "npc_cult_title": "Cultivador",
        "npc_cult_honest_banner": "Eco de un cultivador real — una instantánea de combate, no un jugador.",
        "npc_cult_challenge": "Desafiar",
        "npc_cult_cooldown": "Espera {min} min antes de otro desafío.",
        "npc_cult_no_qi": "Qi insuficiente para el desafío.",
        "npc_cult_busy": "Ya estás en un duelo.",
        "npc_cult_no_hp": "HP agotado — recupérate primero.",
        "npc_cult_unavailable": "No hay oponente disponible cerca.",
        "npc_cult_victory_title": "¡Victoria!",
        "npc_cult_moral_prompt": "{name} ha caído ante ti. ¿Perdonar o ejecutar?",
        "npc_cult_spare": "Perdonar",
        "npc_cult_spare_hint": "La misericordia eleva tu karma hacia el Santo.",
        "npc_cult_execute": "Ejecutar",
        "npc_cult_execute_hint": "La ejecución mancha tu karma hacia el Abismo.",
        "npc_cult_won": "Has ganado",
        "npc_cult_lost": "Has sido derrotado",
        "npc_cult_spared": "Perdonaste al cultivador.",
        "npc_cult_executed": "Ejecutaste al cultivador.",
        "npc_cult_karma_now": "Karma ahora: {value}",
        "npc_cult_path_crystallized": "Tu Camino cristalizó — tus actos definieron quién eres.",
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
