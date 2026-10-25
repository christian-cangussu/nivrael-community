"""MV-2 Mundo Vivo v2 — Tiandao Director i18n (chat + mini-app, pt/en/es).

Idempotente (só insere keys que faltam), convenção de inject_mv1_i18n.py.
Regras: pt = PT-BR (você/seu, nunca EU-PT); cada {token} aparece no máximo
UMA vez por string (t() só substitui a primeira); placeholders ASCII.
Verificação de paridade/contagem: scripts/_verify_mv2_i18n.py.
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CHAT = {
    "pt": {
        "wev_tide_name": "Maré de Bestas",
        "wev_meteor_name": "Meteoro Celestial",
        "wev_tide_desc": "Bestas ferozes assolam a região. Vença combates neste continente para conter a maré antes do prazo — a cidade recompensa quem lutar.",
        "wev_meteor_desc": "Um fragmento do céu caiu aqui. Minere o metal celestial antes que a energia se dissipe.",
        "wev_chron_tide_born": "🌊 Uma Maré de Bestas irrompeu em {continent}! Os cultivadores têm {hours}h para contê-la.",
        "wev_chron_tide_contained": "🌊 A Maré de Bestas em {continent} foi contida — a cidade agradece aos cultivadores.",
        "wev_chron_tide_ignored": "🌊 A Maré de Bestas engoliu as estradas de {continent}. Viajar de lá (ou para lá) ficou mais caro por um tempo.",
        "wev_chron_meteor_born": "☄️ Um Meteoro Celestial caiu em {continent} — o minério do céu espera quem chegar primeiro.",
        "wev_chron_meteor_faded": "☄️ A energia do Meteoro Celestial em {continent} se dissipou.",
        "wev_chat_line": "{event} em {emoji} {name} — ⏳ {time} restantes",
        "wev_chat_progress": " · ⚔️ {progress}/{goal}",
        "wev_rumor": "Dizem na praça que {event} surgiu em {emoji} {name} — {time} restantes...",
        "wev_travel_penalty_note": "🌊 Estradas sitiadas pela Maré ignorada — o preço da travessia subiu.",
        "wev_tide_progress": "🌊 Maré de Bestas: {before}→{progress}/{goal}",
        "wev_local_tide": "🌊 A Maré de Bestas assola ESTE continente — cada vitória em combate conta! ⏳ {time} restantes",
        "wev_local_meteor": "☄️ Um Meteoro Celestial pousou aqui — minere o céu pelo mapa ou pelo /viajar. ⏳ {time} restantes",
        "wev_chat_mine_btn": "⛏️ Minerar o céu · ⚡{cost}",
        "wev_chat_mine_ok": "☄️ Você extraiu {n}x material nativo do céu!",
        "wev_chat_mine_cooldown": "☄️ O céu ainda arde — volte em {time}.",
        "wev_chat_mine_no_qi": "⚡ Qi insuficiente — a mineração exige {cost} de qi.",
        "wev_chat_gone": "O evento já se dissipou.",
        # notif_* são resolvidas SERVER-side (notification_engine → core.i18n.t
        # → locales/) — review MV-2: no mini-app estas keys eram peso morto.
        "notif_wev_reward_title": "🌊 A maré foi contida!",
        "notif_wev_reward_body": "Sua coragem foi recompensada — pedras espirituais e um material nativo chegaram ao seu anel.",
    },
    "en": {
        "wev_tide_name": "Beast Tide",
        "wev_meteor_name": "Celestial Meteor",
        "wev_tide_desc": "Savage beasts ravage the region. Win battles on this continent to contain the tide before time runs out — the city rewards those who fight.",
        "wev_meteor_desc": "A shard of the heavens has fallen here. Mine the celestial ore before its energy fades.",
        "wev_chron_tide_born": "🌊 A Beast Tide has erupted in {continent}! Cultivators have {hours}h to contain it.",
        "wev_chron_tide_contained": "🌊 The Beast Tide in {continent} was contained — the city thanks its cultivators.",
        "wev_chron_tide_ignored": "🌊 The Beast Tide swallowed the roads of {continent}. Travel to and from there is costlier for a while.",
        "wev_chron_meteor_born": "☄️ A Celestial Meteor fell in {continent} — sky ore awaits those who arrive first.",
        "wev_chron_meteor_faded": "☄️ The Celestial Meteor's energy in {continent} has faded.",
        "wev_chat_line": "{event} in {emoji} {name} — ⏳ {time} left",
        "wev_chat_progress": " · ⚔️ {progress}/{goal}",
        "wev_rumor": "Word in the plaza: {event} appeared in {emoji} {name} — {time} left...",
        "wev_travel_penalty_note": "🌊 Roads besieged by the ignored Tide — the crossing costs more.",
        "wev_tide_progress": "🌊 Beast Tide: {before}→{progress}/{goal}",
        "wev_local_tide": "🌊 The Beast Tide ravages THIS continent — every combat victory counts! ⏳ {time} left",
        "wev_local_meteor": "☄️ A Celestial Meteor landed here — mine the sky via the map or /viajar. ⏳ {time} left",
        "wev_chat_mine_btn": "⛏️ Mine the sky · ⚡{cost}",
        "wev_chat_mine_ok": "☄️ You extracted {n}x native sky material!",
        "wev_chat_mine_cooldown": "☄️ The sky still burns — come back in {time}.",
        "wev_chat_mine_no_qi": "⚡ Not enough Qi — mining requires {cost} qi.",
        "wev_chat_gone": "The event has already faded.",
        "notif_wev_reward_title": "🌊 The tide was contained!",
        "notif_wev_reward_body": "Your courage was rewarded — spirit stones and a native material arrived in your ring.",
    },
    "es": {
        "wev_tide_name": "Marea de Bestias",
        "wev_meteor_name": "Meteoro Celestial",
        "wev_tide_desc": "Bestias feroces asolan la región. Gana combates en este continente para contener la marea antes del plazo — la ciudad recompensa a quienes luchen.",
        "wev_meteor_desc": "Un fragmento del cielo cayó aquí. Extrae el mineral celestial antes de que su energía se disipe.",
        "wev_chron_tide_born": "🌊 ¡Una Marea de Bestias irrumpió en {continent}! Los cultivadores tienen {hours}h para contenerla.",
        "wev_chron_tide_contained": "🌊 La Marea de Bestias en {continent} fue contenida — la ciudad agradece a los cultivadores.",
        "wev_chron_tide_ignored": "🌊 La Marea de Bestias devoró los caminos de {continent}. Viajar desde allí (o hacia allí) cuesta más por un tiempo.",
        "wev_chron_meteor_born": "☄️ Un Meteoro Celestial cayó en {continent} — el mineral del cielo espera a quien llegue primero.",
        "wev_chron_meteor_faded": "☄️ La energía del Meteoro Celestial en {continent} se disipó.",
        "wev_chat_line": "{event} en {emoji} {name} — ⏳ {time} restantes",
        "wev_chat_progress": " · ⚔️ {progress}/{goal}",
        "wev_rumor": "Dicen en la plaza que {event} apareció en {emoji} {name} — {time} restantes...",
        "wev_travel_penalty_note": "🌊 Caminos sitiados por la Marea ignorada — el precio del viaje subió.",
        "wev_tide_progress": "🌊 Marea de Bestias: {before}→{progress}/{goal}",
        "wev_local_tide": "🌊 ¡La Marea de Bestias asola ESTE continente — cada victoria en combate cuenta! ⏳ {time} restantes",
        "wev_local_meteor": "☄️ Un Meteoro Celestial aterrizó aquí — extrae el cielo desde el mapa o con /viajar. ⏳ {time} restantes",
        "wev_chat_mine_btn": "⛏️ Minar el cielo · ⚡{cost}",
        "wev_chat_mine_ok": "☄️ ¡Extrajiste {n}x material nativo del cielo!",
        "wev_chat_mine_cooldown": "☄️ El cielo aún arde — vuelve en {time}.",
        "wev_chat_mine_no_qi": "⚡ Qi insuficiente — la minería exige {cost} de qi.",
        "wev_chat_gone": "El evento ya se disipó.",
        "notif_wev_reward_title": "🌊 ¡La marea fue contenida!",
        "notif_wev_reward_body": "Tu coraje fue recompensado — piedras espirituales y un material nativo llegaron a tu anillo.",
    },
}

_MINI = {
    "pt": {
        "feature_tiandao_director": "Eventos Celestiais (Tiandao)",
        "feature_tiandao_director_desc": "O Céu gera eventos com lugar, prazo e consequência — Marés de Bestas e Meteoros no mapa. Ligado = mundo que se move.",
        "wev_time_left": "{time} restantes",
        "wev_progress_label": "Vitórias na região",
        "wev_action_mine": "Minerar o céu",
        "wev_mine_cooldown": "O céu ainda arde — volte em {time}",
        "wev_mine_reward": "Você extraiu: {loot}",
        "wev_mine_no_qi": "Qi insuficiente (precisa de {cost})",
        "wev_travel_hint": "Viaje até lá para agir",
        "wev_gone": "O evento já se dissipou",
        "wev_mine_wrong_continent": "{emoji} O meteoro está em {name} — viaje até lá para minerar",
        "wev_mine_fail": "Não foi possível minerar agora — tente novamente",
        # Fix 2026-07-14 (report [jogador]): upgrade do Anel Espacial no mini-app
        "inv_ring_expand_btn": "Expandir para T{tier} · 🪨 {cost}",
        "inv_ring_expand_ok": "💍 Anel expandido: {max} slots!",
        "inv_ring_expand_max": "O anel já está no tier máximo",
        "inv_ring_expand_no_stones": "Pedras insuficientes — precisa de {cost}",
        "inv_ring_expand_fail": "Não foi possível expandir agora — tente novamente",
        "notif_wev_reward_title": "🌊 A maré foi contida!",
        "notif_wev_reward_body": "Sua coragem foi recompensada — pedras espirituais e um material nativo chegaram ao seu anel.",
    },
    "en": {
        "feature_tiandao_director": "Celestial Events (Tiandao)",
        "feature_tiandao_director_desc": "The Heavens spawn events with a place, a deadline and a consequence — Beast Tides and Meteors on the map. On = a world that moves.",
        "wev_time_left": "{time} left",
        "wev_progress_label": "Victories in the region",
        "wev_action_mine": "Mine the sky",
        "wev_mine_cooldown": "The sky still burns — come back in {time}",
        "wev_mine_reward": "You extracted: {loot}",
        "wev_mine_no_qi": "Not enough Qi (needs {cost})",
        "wev_travel_hint": "Travel there to act",
        "wev_gone": "The event has already faded",
        "wev_mine_wrong_continent": "{emoji} The meteor is in {name} — travel there to mine",
        "wev_mine_fail": "Mining failed just now — try again",
        "inv_ring_expand_btn": "Expand to T{tier} · 🪨 {cost}",
        "inv_ring_expand_ok": "💍 Ring expanded: {max} slots!",
        "inv_ring_expand_max": "The ring is already at max tier",
        "inv_ring_expand_no_stones": "Not enough stones — needs {cost}",
        "inv_ring_expand_fail": "Could not expand right now — try again",
        "notif_wev_reward_title": "🌊 The tide was contained!",
        "notif_wev_reward_body": "Your courage was rewarded — spirit stones and a native material arrived in your ring.",
    },
    "es": {
        "feature_tiandao_director": "Eventos Celestiales (Tiandao)",
        "feature_tiandao_director_desc": "El Cielo genera eventos con lugar, plazo y consecuencia — Mareas de Bestias y Meteoros en el mapa. Activado = mundo que se mueve.",
        "wev_time_left": "{time} restantes",
        "wev_progress_label": "Victorias en la región",
        "wev_action_mine": "Minar el cielo",
        "wev_mine_cooldown": "El cielo aún arde — vuelve en {time}",
        "wev_mine_reward": "Extrajiste: {loot}",
        "wev_mine_no_qi": "Qi insuficiente (necesitas {cost})",
        "wev_travel_hint": "Viaja hasta allí para actuar",
        "wev_gone": "El evento ya se disipó",
        "wev_mine_wrong_continent": "{emoji} El meteoro está en {name} — viaja hasta allí para minar",
        "wev_mine_fail": "No se pudo minar ahora — inténtalo de nuevo",
        "inv_ring_expand_btn": "Expandir a T{tier} · 🪨 {cost}",
        "inv_ring_expand_ok": "💍 ¡Anillo expandido: {max} slots!",
        "inv_ring_expand_max": "El anillo ya está en el tier máximo",
        "inv_ring_expand_no_stones": "Piedras insuficientes — necesitas {cost}",
        "inv_ring_expand_fail": "No se pudo expandir ahora — inténtalo de nuevo",
        "notif_wev_reward_title": "🌊 ¡La marea fue contenida!",
        "notif_wev_reward_body": "Tu coraje fue recompensado — piedras espirituales y un material nativo llegaron a tu anillo.",
    },
}

LANGS = ("pt", "en", "es")
CHAT = {lang: dict(_CHAT[lang]) for lang in LANGS}
MINIAPP = {lang: dict(_MINI[lang]) for lang in LANGS}


def _apply(path: str, additions: dict) -> tuple[int, int]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    before = len(data)
    added = 0
    for k, v in additions.items():
        if k not in data:
            data[k] = v
            added += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)
        f.write("\n")
    return before, added


def main() -> None:
    for lang in LANGS:
        before, added = _apply(os.path.join(ROOT, "locales", f"{lang}.json"), CHAT[lang])
        print(f"chat    {lang}: {before} -> {before + added} (+{added})")
    for lang in LANGS:
        before, added = _apply(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), MINIAPP[lang])
        print(f"miniapp {lang}: {before} -> {before + added} (+{added})")


if __name__ == "__main__":
    main()
