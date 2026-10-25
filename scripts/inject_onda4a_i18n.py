"""Onda 4a — Continental Plaza (Wànshì) + Bounty Board i18n injection.

Idempotent: adds ONLY missing keys, then re-dumps each locale file sorted +
indent=4 + ensure_ascii=False (mirrors scripts/inject_onda3_i18n.py).

Surfaces:
  * CHAT (locales/{pt,en,es}.json): /praca — city name + intro + deep-link CTA +
    the bounty board chrome.
  * MINIAPP (miniapp/i18n/{pt,en,es}.json): the Plaza tab/home card + presence +
    service deep-links + the Bounty Board (cartaz tiers, challenge, claim).

Reuses existing Onda-3 keys (lb_npc_chip, npc_cult_title, wsp_feed_title/empty,
btn_close) — NOT re-added here.

pt = PT-BR (você/seu, ativo/artefato). Placeholders {…} stay ASCII and appear at
most ONCE per string (t() replaces only the first occurrence).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Cross-surface keys — live in BOTH the chat and the mini-app dicts.
_SHARED = {
    "pt": {
        "city_wanshi": "Praça de Wànshì",
        "bounty_board_title": "Quadro de Recompensas",
        "bounty_board_empty": "Nenhum cartaz de caça ativo agora.",
    },
    "en": {
        "city_wanshi": "Wànshì Plaza",
        "bounty_board_title": "Bounty Board",
        "bounty_board_empty": "No active bounty contracts right now.",
    },
    "es": {
        "city_wanshi": "Plaza de Wànshì",
        "bounty_board_title": "Tablón de Recompensas",
        "bounty_board_empty": "No hay contratos de caza activos ahora.",
    },
}

CHAT = {
    "pt": {
        **_SHARED["pt"],
        "plaza_chat_intro": "A grande cidade onde as almas se cruzam.",
        "plaza_open_miniapp": "🏙️ Abra a Praça no mini-app para ver quem está aqui e caçar recompensas.",
    },
    "en": {
        **_SHARED["en"],
        "plaza_chat_intro": "The great city where souls cross paths.",
        "plaza_open_miniapp": "🏙️ Open the Plaza in the mini-app to see who's here and hunt bounties.",
    },
    "es": {
        **_SHARED["es"],
        "plaza_chat_intro": "La gran ciudad donde las almas se cruzan.",
        "plaza_open_miniapp": "🏙️ Abre la Plaza en la mini-app para ver quién está aquí y cazar recompensas.",
    },
}

MINIAPP = {
    "pt": {
        **_SHARED["pt"],
        "tab_plaza": "Praça",
        "home_card_plaza": "Praça",
        "home_stat_plaza_hint": "Há outras almas aqui.",
        "plaza_subtitle": "Há outras almas aqui — cultivadores, recrutadores e caçadas.",
        "plaza_services": "Serviços da Praça",
        "plaza_service_recruiter": "Recrutador",
        "plaza_service_vendor": "Mercador",
        "plaza_service_questgiver": "Missões",
        "plaza_npcs_here": "Cultivadores da Região",
        "plaza_players_here": "Cultivadores Presentes",
        "plaza_empty_npcs": "Nenhum cultivador por perto.",
        "plaza_empty_presence": "A praça está tranquila.",
        "bounty_subtitle": "Caça a cultivadores de karma sombrio. Vença o alvo no duelo para reclamar.",
        "bounty_tier_tainted": "Manchado",
        "bounty_tier_demonic": "Demoníaco",
        "bounty_challenge": "Caçar",
        "bounty_claim_success": "Recompensa de caça: {stones} 🪨",
        "bounty_claimed_by_other": "Outro caçador já reclamou este cartaz — mas você derrotou o alvo.",
    },
    "en": {
        **_SHARED["en"],
        "tab_plaza": "Plaza",
        "home_card_plaza": "Plaza",
        "home_stat_plaza_hint": "Other souls are here.",
        "plaza_subtitle": "Other souls are here — cultivators, recruiters, and hunts.",
        "plaza_services": "Plaza Services",
        "plaza_service_recruiter": "Recruiter",
        "plaza_service_vendor": "Merchant",
        "plaza_service_questgiver": "Quests",
        "plaza_npcs_here": "Cultivators of the Region",
        "plaza_players_here": "Cultivators Present",
        "plaza_empty_npcs": "No cultivators nearby.",
        "plaza_empty_presence": "The plaza is quiet.",
        "bounty_subtitle": "Hunt cultivators of dark karma. Beat the target in a duel to claim.",
        "bounty_tier_tainted": "Tainted",
        "bounty_tier_demonic": "Demonic",
        "bounty_challenge": "Hunt",
        "bounty_claim_success": "Bounty reward: {stones} 🪨",
        "bounty_claimed_by_other": "Another hunter already claimed this contract — but you defeated the target.",
    },
    "es": {
        **_SHARED["es"],
        "tab_plaza": "Plaza",
        "home_card_plaza": "Plaza",
        "home_stat_plaza_hint": "Hay otras almas aquí.",
        "plaza_subtitle": "Hay otras almas aquí — cultivadores, reclutadores y cacerías.",
        "plaza_services": "Servicios de la Plaza",
        "plaza_service_recruiter": "Reclutador",
        "plaza_service_vendor": "Mercader",
        "plaza_service_questgiver": "Misiones",
        "plaza_npcs_here": "Cultivadores de la Región",
        "plaza_players_here": "Cultivadores Presentes",
        "plaza_empty_npcs": "Ningún cultivador cerca.",
        "plaza_empty_presence": "La plaza está tranquila.",
        "bounty_subtitle": "Caza a cultivadores de karma oscuro. Vence al objetivo en un duelo para reclamar.",
        "bounty_tier_tainted": "Manchado",
        "bounty_tier_demonic": "Demoníaco",
        "bounty_challenge": "Cazar",
        "bounty_claim_success": "Recompensa de caza: {stones} 🪨",
        "bounty_claimed_by_other": "Otro cazador ya reclamó este contrato — pero derrotaste al objetivo.",
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
