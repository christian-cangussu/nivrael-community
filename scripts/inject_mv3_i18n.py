"""MV-3 Mundo Vivo v2 — Estados Regionais i18n (chat + mini-app, pt/en/es).

Idempotente (só insere keys que faltam), convenção de inject_mv2_i18n.py.
Regras: pt = PT-BR (você/seu, nunca EU-PT); cada {token} aparece no máximo
UMA vez por string; placeholders ASCII. name/desc dos estados são
server-resolved (locales de CHAT, padrão Chronicle) — o mini só guarda chrome.
Verificação de paridade/contagem: scripts/_verify_mv3_i18n.py.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CHAT = {
    "pt": {
        # Os 4 estados (name + desc curta — a "linha" é "{emoji} {name} — {desc}")
        "rst_prospera_name": "Próspera",
        "rst_prospera_desc": "mercados generosos, estradas seguras",
        "rst_tensa_name": "Tensa",
        "rst_tensa_desc": "as estradas sussurram; explorar ficou mais arriscado",
        "rst_sitiada_name": "Sitiada",
        "rst_sitiada_desc": "estradas caras, mercados nervosos",
        "rst_festival_name": "Festival",
        "rst_festival_desc": "o qi dança; cultivar aqui rende mais",
        # Chronicle de cada transição ({continent} resolve no render)
        "rst_chron_tensa": "⚡ Tempos tensos em {continent} — bestas rondam e as estradas sussurram.",
        "rst_chron_sitiada": "🏚️ {continent} está sob cerco — a maré ignorada cobrou seu preço: estradas caras, mercados nervosos.",
        "rst_chron_festival": "🏮 Festival em {continent} — o qi dança e os mercados abrem as portas.",
        "rst_chron_prospera": "🌾 A paz retorna a {continent} — as estradas se abrem e os mercados respiram.",
        # Nota do mercado local (Lei §1 — o preço nunca muda mudo)
        "rst_market_note_up": "{emoji} Mercados nervosos — preços locais +{pct}% para quem compra aqui.",
        "rst_market_note_down": "{emoji} Mercados em bom momento — preços locais -{pct}% para quem compra aqui.",
    },
    "en": {
        "rst_prospera_name": "Prosperous",
        "rst_prospera_desc": "generous markets, safe roads",
        "rst_tensa_name": "Tense",
        "rst_tensa_desc": "the roads whisper; exploring got riskier",
        "rst_sitiada_name": "Besieged",
        "rst_sitiada_desc": "costly roads, nervous markets",
        "rst_festival_name": "Festival",
        "rst_festival_desc": "the qi dances; cultivating here yields more",
        "rst_chron_tensa": "⚡ Tense times in {continent} — beasts prowl and the roads whisper.",
        "rst_chron_sitiada": "🏚️ {continent} is under siege — the ignored tide took its toll: costly roads, nervous markets.",
        "rst_chron_festival": "🏮 Festival in {continent} — the qi dances and the markets open their doors.",
        "rst_chron_prospera": "🌾 Peace returns to {continent} — the roads open and the markets breathe.",
        "rst_market_note_up": "{emoji} Nervous markets — local prices +{pct}% for buyers here.",
        "rst_market_note_down": "{emoji} Thriving markets — local prices -{pct}% for buyers here.",
    },
    "es": {
        "rst_prospera_name": "Próspera",
        "rst_prospera_desc": "mercados generosos, caminos seguros",
        "rst_tensa_name": "Tensa",
        "rst_tensa_desc": "los caminos susurran; explorar es más arriesgado",
        "rst_sitiada_name": "Sitiada",
        "rst_sitiada_desc": "caminos caros, mercados nerviosos",
        "rst_festival_name": "Festival",
        "rst_festival_desc": "el qi danza; cultivar aquí rinde más",
        "rst_chron_tensa": "⚡ Tiempos tensos en {continent} — las bestias acechan y los caminos susurran.",
        "rst_chron_sitiada": "🏚️ {continent} está bajo asedio — la marea ignorada cobró su precio: caminos caros, mercados nerviosos.",
        "rst_chron_festival": "🏮 Festival en {continent} — el qi danza y los mercados abren sus puertas.",
        "rst_chron_prospera": "🌾 La paz regresa a {continent} — los caminos se abren y los mercados respiran.",
        "rst_market_note_up": "{emoji} Mercados nerviosos — precios locales +{pct}% para quien compra aquí.",
        "rst_market_note_down": "{emoji} Mercados en buen momento — precios locales -{pct}% para quien compra aquí.",
    },
}

_MINI = {
    "pt": {
        # Painel admin self-doc (lição R6/MV-1)
        "feature_estados_regionais": "Estados Regionais",
        "feature_estados_regionais_desc": "Cada continente tem um estado vivo (próspera/tensa/sitiada/festival) com efeitos reais — preços, risco, densidade de qi. Ligado = mundo com consequência.",
        # Chrome do chip Chronicle→mapa (ui_v2)
        "rst_see_on_map": "Ver no mapa",
    },
    "en": {
        "feature_estados_regionais": "Regional States",
        "feature_estados_regionais_desc": "Each continent has a living state (prosperous/tense/besieged/festival) with real effects — prices, risk, qi density. On = a world with consequence.",
        "rst_see_on_map": "See on map",
    },
    "es": {
        "feature_estados_regionais": "Estados Regionales",
        "feature_estados_regionais_desc": "Cada continente tiene un estado vivo (próspera/tensa/sitiada/festival) con efectos reales — precios, riesgo, densidad de qi. Activado = un mundo con consecuencia.",
        "rst_see_on_map": "Ver en el mapa",
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
