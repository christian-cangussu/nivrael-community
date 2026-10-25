# -*- coding: utf-8 -*-
"""MV-4 Mundo Vivo v2 — Corpo Profundo: i18n injector (padrão inject_mv3_i18n).

CHAT (locales/): nomes dos 12 canais + ritual + refino/lugar + notif_* (lição
MV-2: o server resolve via core.i18n.t — as keys TÊM de viver no chat) + as
keys do fix §0 do bounty. MINI (miniapp/i18n/): chrome do MeridiansCard +
self-doc do painel admin (feature_corpo_profundo) + fix §0 do bounty.

Idempotente — só insere keys ausentes. Correr: python -X utf8 scripts/inject_mv4_i18n.py
Verificar: python -X utf8 scripts/_verify_mv4_i18n.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

CHAT = {
    "pt": {
        # ── Os 12 canais (十二正经 — ordem clássica da circulação) ──
        "mer_ch_pulmao": "Meridiano do Pulmão",
        "mer_ch_intestino_grosso": "Meridiano do Intestino Grosso",
        "mer_ch_estomago": "Meridiano do Estômago",
        "mer_ch_baco": "Meridiano do Baço",
        "mer_ch_coracao": "Meridiano do Coração",
        "mer_ch_intestino_delgado": "Meridiano do Intestino Delgado",
        "mer_ch_bexiga": "Meridiano da Bexiga",
        "mer_ch_rim": "Meridiano do Rim",
        "mer_ch_pericardio": "Meridiano do Pericárdio",
        "mer_ch_triplo_aquecedor": "Meridiano do Triplo Aquecedor",
        "mer_ch_vesicula": "Meridiano da Vesícula",
        "mer_ch_figado": "Meridiano do Fígado",
        # ── O bloco no /corpo + o ritual ──
        "mer_block_title": "⛩️ Meridianos 经脉 · {n}/{total} canais abertos",
        "mer_block_bonus": "🛡️ +{pct}% de HP e defesa pelos canais abertos",
        "mer_next_line": "Próximo: {emoji} {name} · 🪨 {stones} · 🧵 {progress} progresso · 🦴 {essence} essência",
        "mer_next_detail": "Circulação: {hours}h · chance de rompimento: {chance}%",
        "mer_start_btn": "⛩️ Iniciar ritual",
        "mer_break_btn": "⚡ Romper o canal",
        "mer_started": "{emoji} O ritual começou: {name}.\nCircule qi por {hours}h — depois tente o rompimento ({chance}% de chance).",
        "mer_ritual_circulating": "⏳ Circulando qi: {name} — pronto em {time}.",
        "mer_ritual_ready": "⚡ O qi pressiona a barreira: {name} pronto para o rompimento ({chance}% de chance).",
        "mer_break_success": "🌟 {emoji} {name} ABERTO! Canais: {n}/{total}.",
        "mer_break_delta": "❤️ HP máx {hp_before} → {hp_after} · 🛡️ resistência +{pct}%",
        "mer_break_fail": "💢 O canal resistiu ({chance}%). Nada se perdeu: circule qi por {time} e tente de novo com {next_chance}%.",
        "mer_all_open": "🏮 Os Doze Canais fluem como um rio — seu corpo é um vaso perfeito.",
        "mer_teaser": "Dizem que além dos doze existem oito vasos extraordinários…",
        # ── Recusas honestas (Lei §1) ──
        "mer_locked": "Os meridianos ainda dormem neste mundo.",
        "mer_ritual_active": "Um ritual já está em curso — termine-o primeiro.",
        "mer_no_ritual": "Nenhum ritual em curso — prepare o próximo canal primeiro.",
        "mer_still_circulating": "O qi ainda circula — pronto em {time}.",
        "mer_cooldown": "O corpo ainda assenta o último canal — aguarde {time}.",
        "mer_need_realm": "Seus canais ainda não suportam tanto qi — alcance o Reino {realm} para abrir o primeiro meridiano.",
        "mer_realm_capped": "O corpo precisa acompanhar o reino — avance de reino para abrir mais canais.",
        "mer_need_stones": "Pedras espirituais insuficientes para preparar o canal.",
        "mer_need_progress": "Progresso de têmpera insuficiente — a Horta, a Caça, os sítios e o combate alimentam o corpo.",
        "mer_need_essence": "Essência de caça insuficiente — as expedições de bestas trazem essência.",
        # ── Notificação pessoal + Chronicle (server-resolved) ──
        "notif_meridian_open_title": "⛩️ Meridiano aberto",
        "notif_meridian_open_body": "{name} aberto — {n}/{total} canais. Seu corpo canaliza mais qi.",
        "mer_chron_first": "⛩️ Em {continent}, um cultivador rompeu um dos Doze Meridianos pela primeira vez nesta era.",
        # ── Refino ancorado em LUGAR (server-resolved ×2 superfícies) ──
        "refino_place_cavern": "Sua caverna canaliza o qi — refino +{pct}%.",
        "refino_place_site": "O sítio de têmpera deste continente sustenta seu refino.",
        "refino_place_road": "Refinar na estrada é amador — refino −{pct}%. Vá a um sítio de têmpera ou à sua caverna com Formação ativa.",
        "refino_place_festival": "🏮 O festival adensa o qi (+{pct}%).",
        # ── §0 — fix do bounty (report do owner 2026-07-15) ──
        "wbounty_yours_chip": "🎁 seu contrato",
        "bounty_board_empty_hint": "🧭 Cada continente tem seu próprio quadro — viaje para caçar outros contratos.",
    },
    "en": {
        "mer_ch_pulmao": "Lung Meridian",
        "mer_ch_intestino_grosso": "Large Intestine Meridian",
        "mer_ch_estomago": "Stomach Meridian",
        "mer_ch_baco": "Spleen Meridian",
        "mer_ch_coracao": "Heart Meridian",
        "mer_ch_intestino_delgado": "Small Intestine Meridian",
        "mer_ch_bexiga": "Bladder Meridian",
        "mer_ch_rim": "Kidney Meridian",
        "mer_ch_pericardio": "Pericardium Meridian",
        "mer_ch_triplo_aquecedor": "Triple Burner Meridian",
        "mer_ch_vesicula": "Gallbladder Meridian",
        "mer_ch_figado": "Liver Meridian",
        "mer_block_title": "⛩️ Meridians 经脉 · {n}/{total} channels open",
        "mer_block_bonus": "🛡️ +{pct}% HP and defense from open channels",
        "mer_next_line": "Next: {emoji} {name} · 🪨 {stones} · 🧵 {progress} progress · 🦴 {essence} essence",
        "mer_next_detail": "Circulation: {hours}h · breakthrough chance: {chance}%",
        "mer_start_btn": "⛩️ Begin ritual",
        "mer_break_btn": "⚡ Break the channel",
        "mer_started": "{emoji} The ritual has begun: {name}.\nCirculate qi for {hours}h — then attempt the breakthrough ({chance}% chance).",
        "mer_ritual_circulating": "⏳ Circulating qi: {name} — ready in {time}.",
        "mer_ritual_ready": "⚡ The qi presses the barrier: {name} is ready for the breakthrough ({chance}% chance).",
        "mer_break_success": "🌟 {emoji} {name} OPENED! Channels: {n}/{total}.",
        "mer_break_delta": "❤️ Max HP {hp_before} → {hp_after} · 🛡️ resilience +{pct}%",
        "mer_break_fail": "💢 The channel resisted ({chance}%). Nothing was lost: circulate qi for {time} and try again at {next_chance}%.",
        "mer_all_open": "🏮 The Twelve Channels flow like a river — your body is a perfect vessel.",
        "mer_teaser": "They say beyond the twelve lie eight extraordinary vessels…",
        "mer_locked": "The meridians still sleep in this world.",
        "mer_ritual_active": "A ritual is already underway — finish it first.",
        "mer_no_ritual": "No ritual underway — prepare the next channel first.",
        "mer_still_circulating": "The qi still circulates — ready in {time}.",
        "mer_cooldown": "Your body is still settling the last channel — wait {time}.",
        "mer_need_realm": "Your channels cannot hold this much qi yet — reach Realm {realm} to open the first meridian.",
        "mer_realm_capped": "The body must keep pace with the realm — break through to open more channels.",
        "mer_need_stones": "Not enough spirit stones to prepare the channel.",
        "mer_need_progress": "Not enough temper progress — the Garden, the Hunt, the sites and combat feed the body.",
        "mer_need_essence": "Not enough hunt essence — beast expeditions bring essence.",
        "notif_meridian_open_title": "⛩️ Meridian opened",
        "notif_meridian_open_body": "{name} opened — {n}/{total} channels. Your body channels more qi.",
        "mer_chron_first": "⛩️ In {continent}, a cultivator broke open one of the Twelve Meridians for the first time this era.",
        "refino_place_cavern": "Your cavern channels the qi — refining +{pct}%.",
        "refino_place_site": "This continent's tempering site sustains your refining.",
        "refino_place_road": "Refining on the road is amateurish — refining −{pct}%. Go to a tempering site or to your cavern with an active Formation.",
        "refino_place_festival": "🏮 The festival thickens the qi (+{pct}%).",
        "wbounty_yours_chip": "🎁 your contract",
        "bounty_board_empty_hint": "🧭 Each continent hangs its own board — travel to hunt other contracts.",
    },
    "es": {
        "mer_ch_pulmao": "Meridiano del Pulmón",
        "mer_ch_intestino_grosso": "Meridiano del Intestino Grueso",
        "mer_ch_estomago": "Meridiano del Estómago",
        "mer_ch_baco": "Meridiano del Bazo",
        "mer_ch_coracao": "Meridiano del Corazón",
        "mer_ch_intestino_delgado": "Meridiano del Intestino Delgado",
        "mer_ch_bexiga": "Meridiano de la Vejiga",
        "mer_ch_rim": "Meridiano del Riñón",
        "mer_ch_pericardio": "Meridiano del Pericardio",
        "mer_ch_triplo_aquecedor": "Meridiano del Triple Calentador",
        "mer_ch_vesicula": "Meridiano de la Vesícula",
        "mer_ch_figado": "Meridiano del Hígado",
        "mer_block_title": "⛩️ Meridianos 经脉 · {n}/{total} canales abiertos",
        "mer_block_bonus": "🛡️ +{pct}% de HP y defensa por los canales abiertos",
        "mer_next_line": "Siguiente: {emoji} {name} · 🪨 {stones} · 🧵 {progress} progreso · 🦴 {essence} esencia",
        "mer_next_detail": "Circulación: {hours}h · probabilidad de ruptura: {chance}%",
        "mer_start_btn": "⛩️ Iniciar ritual",
        "mer_break_btn": "⚡ Romper el canal",
        "mer_started": "{emoji} El ritual ha comenzado: {name}.\nCircula qi durante {hours}h — luego intenta la ruptura ({chance}% de probabilidad).",
        "mer_ritual_circulating": "⏳ Circulando qi: {name} — listo en {time}.",
        "mer_ritual_ready": "⚡ El qi presiona la barrera: {name} listo para la ruptura ({chance}% de probabilidad).",
        "mer_break_success": "🌟 {emoji} ¡{name} ABIERTO! Canales: {n}/{total}.",
        "mer_break_delta": "❤️ HP máx {hp_before} → {hp_after} · 🛡️ resistencia +{pct}%",
        "mer_break_fail": "💢 El canal resistió ({chance}%). Nada se perdió: circula qi durante {time} e inténtalo de nuevo con {next_chance}%.",
        "mer_all_open": "🏮 Los Doce Canales fluyen como un río — tu cuerpo es un recipiente perfecto.",
        "mer_teaser": "Dicen que más allá de los doce existen ocho vasos extraordinarios…",
        "mer_locked": "Los meridianos aún duermen en este mundo.",
        "mer_ritual_active": "Ya hay un ritual en curso — termínalo primero.",
        "mer_no_ritual": "Ningún ritual en curso — prepara el siguiente canal primero.",
        "mer_still_circulating": "El qi aún circula — listo en {time}.",
        "mer_cooldown": "El cuerpo aún asienta el último canal — espera {time}.",
        "mer_need_realm": "Tus canales aún no soportan tanto qi — alcanza el Reino {realm} para abrir el primer meridiano.",
        "mer_realm_capped": "El cuerpo debe acompañar al reino — avanza de reino para abrir más canales.",
        "mer_need_stones": "Piedras espirituales insuficientes para preparar el canal.",
        "mer_need_progress": "Progreso de temple insuficiente — el Huerto, la Caza, los sitios y el combate alimentan el cuerpo.",
        "mer_need_essence": "Esencia de caza insuficiente — las expediciones de bestias traen esencia.",
        "notif_meridian_open_title": "⛩️ Meridiano abierto",
        "notif_meridian_open_body": "{name} abierto — {n}/{total} canales. Tu cuerpo canaliza más qi.",
        "mer_chron_first": "⛩️ En {continent}, un cultivador rompió uno de los Doce Meridianos por primera vez en esta era.",
        "refino_place_cavern": "Tu caverna canaliza el qi — refinado +{pct}%.",
        "refino_place_site": "El sitio de temple de este continente sostiene tu refinado.",
        "refino_place_road": "Refinar en el camino es de aficionados — refinado −{pct}%. Ve a un sitio de temple o a tu caverna con Formación activa.",
        "refino_place_festival": "🏮 El festival espesa el qi (+{pct}%).",
        "wbounty_yours_chip": "🎁 tu contrato",
        "bounty_board_empty_hint": "🧭 Cada continente tiene su propio tablón — viaja para cazar otros contratos.",
    },
}

MINIAPP = {
    "pt": {
        # Painel admin self-doc (lição R6/MV-1)
        "feature_corpo_profundo": "Corpo Profundo (Meridianos)",
        "feature_corpo_profundo_desc": "Meridianos (12 canais, ritual difícil) + refino ancorado em lugar (caverna com formação > sítio do continente > qualquer lugar). Ligado = o corpo tem profundidade e a caverna importa. Funciona em conjunto com 'Cultivo do Corpo' (os custos do ritual e as telas do corpo vivem nesse eixo).",
        # Chrome do MeridiansCard
        "mer_section_title": "Meridianos 经脉",
        "mer_bonus_line": "+{pct}% HP/DEF pelos canais abertos",
        "mer_started_toast": "Ritual iniciado — circule qi por {hours}h.",
        "mer_open_toast": "Canal aberto ({n}/{total})! HP {hp_before} → {hp_after}.",
        "mer_fail_toast": "O canal resistiu ({chance}%). Próxima: {next}% após {time}.",
        "mer_ready_line": "{name} pronto para o rompimento — {chance}% de chance.",
        "mer_circulating_line": "Circulando {name} — pronto em {time}.",
        "mer_start_btn": "Iniciar ritual",
        "mer_start_confirm": "Confirmar ritual",
        "mer_break_btn": "Romper o canal",
        "mer_cooldown_mini": "O corpo assenta o último canal — {time}.",
        "mer_all_open_mini": "Os Doze Canais fluem como um rio — seu corpo é um vaso perfeito.",
        "mer_teaser_mini": "Dizem que além dos doze existem oito vasos extraordinários…",
        # Recusas (safeT dos reasons — versões SEM placeholder)
        "mer_locked": "Os meridianos ainda dormem neste mundo.",
        "mer_ritual_active": "Um ritual já está em curso.",
        "mer_no_ritual": "Nenhum ritual em curso.",
        "mer_still_circulating": "O qi ainda circula — aguarde.",
        "mer_cooldown": "O corpo ainda assenta o último canal.",
        "mer_need_realm": "Alcance um reino superior para abrir o primeiro meridiano.",
        "mer_realm_capped": "Avance de reino para abrir mais canais.",
        "mer_need_stones": "Pedras espirituais insuficientes.",
        "mer_need_progress": "Progresso de têmpera insuficiente — Horta, Caça, sítios e combate alimentam o corpo.",
        "mer_need_essence": "Essência de caça insuficiente — expedições de bestas trazem essência.",
        "mer_all_open": "Os doze canais já estão abertos.",
        # §0 — fix do bounty
        "wbounty_post_ok_where": "Contrato listado no quadro de {continent}.",
        "bounty_board_empty_hint": "Cada continente tem seu próprio quadro — viaje para caçar outros contratos.",
    },
    "en": {
        "feature_corpo_profundo": "Deep Body (Meridians)",
        "feature_corpo_profundo_desc": "Meridians (12 channels, hard ritual) + place-anchored refining (cavern with formation > continent site > anywhere). On = the body has depth and the cavern matters. Works together with 'Deep Body Cultivation' (ritual costs and the body screens live on that axis).",
        "mer_section_title": "Meridians 经脉",
        "mer_bonus_line": "+{pct}% HP/DEF from open channels",
        "mer_started_toast": "Ritual begun — circulate qi for {hours}h.",
        "mer_open_toast": "Channel opened ({n}/{total})! HP {hp_before} → {hp_after}.",
        "mer_fail_toast": "The channel resisted ({chance}%). Next: {next}% after {time}.",
        "mer_ready_line": "{name} ready for the breakthrough — {chance}% chance.",
        "mer_circulating_line": "Circulating {name} — ready in {time}.",
        "mer_start_btn": "Begin ritual",
        "mer_start_confirm": "Confirm ritual",
        "mer_break_btn": "Break the channel",
        "mer_cooldown_mini": "The body settles the last channel — {time}.",
        "mer_all_open_mini": "The Twelve Channels flow like a river — your body is a perfect vessel.",
        "mer_teaser_mini": "They say beyond the twelve lie eight extraordinary vessels…",
        "mer_locked": "The meridians still sleep in this world.",
        "mer_ritual_active": "A ritual is already underway.",
        "mer_no_ritual": "No ritual underway.",
        "mer_still_circulating": "The qi still circulates — wait.",
        "mer_cooldown": "The body is still settling the last channel.",
        "mer_need_realm": "Reach a higher realm to open the first meridian.",
        "mer_realm_capped": "Break through to open more channels.",
        "mer_need_stones": "Not enough spirit stones.",
        "mer_need_progress": "Not enough temper progress — Garden, Hunt, sites and combat feed the body.",
        "mer_need_essence": "Not enough hunt essence — beast expeditions bring essence.",
        "mer_all_open": "All twelve channels are already open.",
        "wbounty_post_ok_where": "Contract listed on the {continent} board.",
        "bounty_board_empty_hint": "Each continent hangs its own board — travel to hunt other contracts.",
    },
    "es": {
        "feature_corpo_profundo": "Cuerpo Profundo (Meridianos)",
        "feature_corpo_profundo_desc": "Meridianos (12 canales, ritual difícil) + refinado anclado al lugar (caverna con formación > sitio del continente > cualquier lugar). Activado = el cuerpo tiene profundidad y la caverna importa. Funciona junto con 'Cultivo del Cuerpo' (los costes del ritual y las pantallas del cuerpo viven en ese eje).",
        "mer_section_title": "Meridianos 经脉",
        "mer_bonus_line": "+{pct}% HP/DEF por los canales abiertos",
        "mer_started_toast": "Ritual iniciado — circula qi durante {hours}h.",
        "mer_open_toast": "¡Canal abierto ({n}/{total})! HP {hp_before} → {hp_after}.",
        "mer_fail_toast": "El canal resistió ({chance}%). Siguiente: {next}% tras {time}.",
        "mer_ready_line": "{name} listo para la ruptura — {chance}% de probabilidad.",
        "mer_circulating_line": "Circulando {name} — listo en {time}.",
        "mer_start_btn": "Iniciar ritual",
        "mer_start_confirm": "Confirmar ritual",
        "mer_break_btn": "Romper el canal",
        "mer_cooldown_mini": "El cuerpo asienta el último canal — {time}.",
        "mer_all_open_mini": "Los Doce Canales fluyen como un río — tu cuerpo es un recipiente perfecto.",
        "mer_teaser_mini": "Dicen que más allá de los doce existen ocho vasos extraordinarios…",
        "mer_locked": "Los meridianos aún duermen en este mundo.",
        "mer_ritual_active": "Ya hay un ritual en curso.",
        "mer_no_ritual": "Ningún ritual en curso.",
        "mer_still_circulating": "El qi aún circula — espera.",
        "mer_cooldown": "El cuerpo aún asienta el último canal.",
        "mer_need_realm": "Alcanza un reino superior para abrir el primer meridiano.",
        "mer_realm_capped": "Avanza de reino para abrir más canales.",
        "mer_need_stones": "Piedras espirituales insuficientes.",
        "mer_need_progress": "Progreso de temple insuficiente — Huerto, Caza, sitios y combate alimentan el cuerpo.",
        "mer_need_essence": "Esencia de caza insuficiente — las expediciones de bestias traen esencia.",
        "mer_all_open": "Los doce canales ya están abiertos.",
        "wbounty_post_ok_where": "Contrato listado en el tablón de {continent}.",
        "bounty_board_empty_hint": "Cada continente tiene su propio tablón — viaja para cazar otros contratos.",
    },
}


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
