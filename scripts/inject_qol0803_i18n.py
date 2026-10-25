"""QoL-Feedback 2026-08-03 — injetor de i18n (chat + mini) do lote dos 3 reports.

Roda:  python -X utf8 scripts/inject_qol0803_i18n.py

Superfícies:
  · chat locales — os 6 `pill_effect_label_*` que FALTAVAM (o card ℹ️ imprimia
    o token cru do effect_type) + o preview honesto do reroll da Fundação
    (`inv_pill_detail_found_*`): fundação atual com o ×mult, a tabela de odds
    real da qualidade do craft, o caminho da Sagrada e o risco de PIORAR;
  · mini i18n — o mesmo preview (`pill_found_*`), o resultado old→new que o
    painel deitava fora, a linha "🏯 Fundação" do ProfileModal, e as strings
    do teto do refino (`refine_at_max_next`, `inv_detail_refine_*`).

SÓ-ADIÇÕES: `_apply` só escreve key que AINDA NÃO existe. Idempotente.
`newline="\n"` é load-bearing (Windows CRLF). OVERRIDES re-aplicam as 3
strings ENRIQUECIDAS (o teto do refino passou a dizer o caminho seguinte; os
dois `pill_eff_*` do mini ganharam nomes claros em PT-BR).

Verificador: scripts/_verify_qol0803_i18n.py.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

CHAT = {
    "pt": {
        "pill_effect_label_eternal_foundation_reroll": "Refaz sua Fundação (aposta)",
        "pill_effect_label_foundation_reroll": "Refaz sua Fundação (ritual)",
        "pill_effect_label_core_essence": "Acumula Essência de Núcleo",
        "pill_effect_label_body_tempering_progress": "Progresso de Cultivo do Corpo",
        "pill_effect_label_qi_regen_boost": "Buff de regeneração de Qi (temporário)",
        "pill_effect_label_special": "Efeito especial",
        "inv_pill_detail_found_current": "🏯 Fundação atual: {quality} (×{mult} nos stats)",
        "inv_pill_detail_found_current_none": "🏯 Fundação atual: ainda não estabelecida",
        "inv_pill_detail_found_locked": "🌌 Sua Fundação é Sagrada — o pináculo. Esta pílula não muda nada.",
        "inv_pill_detail_found_odds": "🎲 Resultado possível: {odds}",
        "inv_pill_detail_found_odds_row": "{pct}% {quality} (×{mult})",
        "inv_pill_detail_found_sacred": "🌌 Nesta qualidade e com Fundação Perfeita, o resultado é a *Fundação Sagrada* (×2.00) — garantido.",
        "inv_pill_detail_found_sacred_hint": "🌌 A Fundação Sagrada (×2.00) só nasce de uma pílula Celestial usada sobre Fundação Perfeita.",
        "inv_pill_detail_found_risk": "⚠️ *É uma aposta:* a Fundação pode PIORAR. Não há como desfazer.",
        "inv_pill_detail_found_trial": "🎲 Refaz a *prova da Fundação*: 3 desafios (Alma · Percepção · Sorte) contra limiares que sobem com seu prestígio. O melhor resultado possível é *Perfeita* — a Sagrada só vem da Pílula da Fundação Eterna.",
        "pill_effect_eternal_same": "🏯 A Fundação resistiu: continua *{quality}* (×{mult}). Nada mudou.",
        "pill_effect_eternal_down": "💔 *A Fundação rachou.* {old} → *{new}*  (×{old_mult} → ×{new_mult})",
        "pill_effect_eternal_mult": "📈 Multiplicador de stats: ×{old_mult} → *×{new_mult}*",
        "pill_foundation_sacred_locked": "🌌 Sua Fundação é Sagrada — o pináculo. Esta pílula não teria efeito, então NADA foi consumido.",
        "pill_foundation_not_established": "🏯 Você ainda não estabeleceu uma Fundação para reparar. NADA foi consumido.",
    },
    "en": {
        "pill_effect_label_eternal_foundation_reroll": "Rerolls your Foundation (gamble)",
        "pill_effect_label_foundation_reroll": "Rerolls your Foundation (ritual)",
        "pill_effect_label_core_essence": "Accumulates Core Essence",
        "pill_effect_label_body_tempering_progress": "Body Cultivation progress",
        "pill_effect_label_qi_regen_boost": "Qi regeneration buff (timed)",
        "pill_effect_label_special": "Special effect",
        "inv_pill_detail_found_current": "🏯 Current Foundation: {quality} (×{mult} to stats)",
        "inv_pill_detail_found_current_none": "🏯 Current Foundation: not established yet",
        "inv_pill_detail_found_locked": "🌌 Your Foundation is Sacred — the pinnacle. This pill changes nothing.",
        "inv_pill_detail_found_odds": "🎲 Possible outcome: {odds}",
        "inv_pill_detail_found_odds_row": "{pct}% {quality} (×{mult})",
        "inv_pill_detail_found_sacred": "🌌 At this quality, on a Perfect Foundation, the outcome is the *Sacred Foundation* (×2.00) — guaranteed.",
        "inv_pill_detail_found_sacred_hint": "🌌 The Sacred Foundation (×2.00) is born only from a Heavenly pill used on a Perfect Foundation.",
        "inv_pill_detail_found_risk": "⚠️ *This is a gamble:* the Foundation can get WORSE. There is no undo.",
        "inv_pill_detail_found_trial": "🎲 Retakes the *Foundation trial*: 3 challenges (Soul · Perception · Luck) against thresholds that scale with your prestige. The best possible outcome is *Perfect* — Sacred only comes from the Eternal Foundation Pill.",
        "pill_effect_eternal_same": "🏯 The Foundation held: still *{quality}* (×{mult}). Nothing changed.",
        "pill_effect_eternal_down": "💔 *The Foundation cracked.* {old} → *{new}*  (×{old_mult} → ×{new_mult})",
        "pill_effect_eternal_mult": "📈 Stat multiplier: ×{old_mult} → *×{new_mult}*",
        "pill_foundation_sacred_locked": "🌌 Your Foundation is Sacred — the pinnacle. This pill would do nothing, so NOTHING was consumed.",
        "pill_foundation_not_established": "🏯 You have no Foundation to repair yet. NOTHING was consumed.",
    },
    "es": {
        "pill_effect_label_eternal_foundation_reroll": "Rehace tu Cimiento (apuesta)",
        "pill_effect_label_foundation_reroll": "Rehace tu Cimiento (ritual)",
        "pill_effect_label_core_essence": "Acumula Esencia de Núcleo",
        "pill_effect_label_body_tempering_progress": "Progreso de Cultivo del Cuerpo",
        "pill_effect_label_qi_regen_boost": "Buff de regeneración de Qi (temporal)",
        "pill_effect_label_special": "Efecto especial",
        "inv_pill_detail_found_current": "🏯 Cimiento actual: {quality} (×{mult} a los stats)",
        "inv_pill_detail_found_current_none": "🏯 Cimiento actual: aún no establecido",
        "inv_pill_detail_found_locked": "🌌 Tu Cimiento es Sagrado — la cima. Esta píldora no cambia nada.",
        "inv_pill_detail_found_odds": "🎲 Resultado posible: {odds}",
        "inv_pill_detail_found_odds_row": "{pct}% {quality} (×{mult})",
        "inv_pill_detail_found_sacred": "🌌 En esta calidad y con Cimiento Perfecto, el resultado es el *Cimiento Sagrado* (×2.00) — garantizado.",
        "inv_pill_detail_found_sacred_hint": "🌌 El Cimiento Sagrado (×2.00) sólo nace de una píldora Celestial usada sobre un Cimiento Perfecto.",
        "inv_pill_detail_found_risk": "⚠️ *Es una apuesta:* el Cimiento puede EMPEORAR. No hay vuelta atrás.",
        "inv_pill_detail_found_trial": "🎲 Repite la *prueba del Cimiento*: 3 desafíos (Alma · Percepción · Suerte) contra umbrales que suben con tu prestigio. El mejor resultado posible es *Perfecto* — el Sagrado sólo viene de la Píldora del Cimiento Eterno.",
        "pill_effect_eternal_same": "🏯 El Cimiento resistió: sigue *{quality}* (×{mult}). Nada cambió.",
        "pill_effect_eternal_down": "💔 *El Cimiento se agrietó.* {old} → *{new}*  (×{old_mult} → ×{new_mult})",
        "pill_effect_eternal_mult": "📈 Multiplicador de stats: ×{old_mult} → *×{new_mult}*",
        "pill_foundation_sacred_locked": "🌌 Tu Cimiento es Sagrado — la cima. Esta píldora no haría nada, así que NADA fue consumido.",
        "pill_foundation_not_established": "🏯 Aún no tienes un Cimiento que reparar. NADA fue consumido.",
    },
}

MINIAPP = {
    "pt": {
        "pill_found_current": "Fundação atual: {quality} (×{mult} nos stats)",
        "pill_found_current_none": "Fundação ainda não estabelecida",
        "pill_found_locked": "Sua Fundação é Sagrada — o pináculo. Esta pílula não muda nada.",
        "pill_found_odds_title": "Resultado possível:",
        "pill_found_sacred_now": "Com Fundação Perfeita e esta qualidade, o resultado é a Fundação Sagrada (×2.00) — garantido.",
        "pill_found_sacred_hint": "A Fundação Sagrada (×2.00) só nasce de uma pílula Celestial usada sobre Fundação Perfeita.",
        "pill_found_risk": "É uma aposta: a Fundação pode PIORAR. Não há como desfazer.",
        "pill_found_trial": "Refaz a prova da Fundação: 3 desafios (Alma · Percepção · Sorte) contra limiares que sobem com seu prestígio. O melhor resultado possível é Perfeita.",
        "pill_found_result": "🌌 Fundação Reforjada! {old} → {new}",
        "pill_found_result_sacred": "🌌✨ FUNDAÇÃO SAGRADA DESPERTADA! {old} → {new}",
        "pill_found_result_mult": "🏯 Multiplicador de stats agora: ×{mult}",
        "pill_found_result_same": "🏯 A Fundação resistiu: continua {quality} (×{mult}). Nada mudou.",
        "pill_found_result_down": "💔 A Fundação rachou: {old} → {new}  (×{old_mult} → ×{new_mult})",
        "pill_found_result_mult_delta": "📈 Multiplicador de stats: ×{old_mult} → ×{new_mult}",
        "pill_found_locked_btn": "Nada a reforjar",
        "pill_foundation_sacred_locked": "Sua Fundação é Sagrada — o pináculo. Esta pílula não teria efeito, então NADA foi consumido.",
        "pill_foundation_not_established": "Você ainda não estabeleceu uma Fundação para reparar. NADA foi consumido.",
        "profile_foundation_label": "Fundação",
        "refine_at_max_next": "Acima de G7 Dao não se refina: o equipamento G8 Celestial é forjado inteiro, com receitas Celestiais (Mahayana).",
        "refine_at_absolute_max": "Celestial — o grau mais alto do mundo",
        "inv_detail_refine_hint": "Refine este item no 🛡️ {workshop} (aba Forja › segmento ⚒️ Forja), consumindo uma duplicata idêntica.",
        "inv_detail_refine_at_max": "Grau máximo (G7 Dao) — não há refino acima daqui. O G8 Celestial é forjado inteiro, com receitas Celestiais (Mahayana).",
        "inv_detail_refine_absolute_max": "G8 Celestial — o grau mais alto do mundo. Não há refino nem forja acima daqui.",
    },
    "en": {
        "pill_found_current": "Current Foundation: {quality} (×{mult} to stats)",
        "pill_found_current_none": "Foundation not established yet",
        "pill_found_locked": "Your Foundation is Sacred — the pinnacle. This pill changes nothing.",
        "pill_found_odds_title": "Possible outcome:",
        "pill_found_sacred_now": "On a Perfect Foundation at this quality, the outcome is the Sacred Foundation (×2.00) — guaranteed.",
        "pill_found_sacred_hint": "The Sacred Foundation (×2.00) is born only from a Heavenly pill used on a Perfect Foundation.",
        "pill_found_risk": "This is a gamble: the Foundation can get WORSE. There is no undo.",
        "pill_found_trial": "Retakes the Foundation trial: 3 challenges (Soul · Perception · Luck) against thresholds that scale with your prestige. The best possible outcome is Perfect.",
        "pill_found_result": "🌌 Foundation Reforged! {old} → {new}",
        "pill_found_result_sacred": "🌌✨ SACRED FOUNDATION AWAKENED! {old} → {new}",
        "pill_found_result_mult": "🏯 Stat multiplier is now ×{mult}",
        "pill_found_result_same": "🏯 The Foundation held: still {quality} (×{mult}). Nothing changed.",
        "pill_found_result_down": "💔 The Foundation cracked: {old} → {new}  (×{old_mult} → ×{new_mult})",
        "pill_found_result_mult_delta": "📈 Stat multiplier: ×{old_mult} → ×{new_mult}",
        "pill_found_locked_btn": "Nothing to reforge",
        "pill_foundation_sacred_locked": "Your Foundation is Sacred — the pinnacle. This pill would do nothing, so NOTHING was consumed.",
        "pill_foundation_not_established": "You have no Foundation to repair yet. NOTHING was consumed.",
        "profile_foundation_label": "Foundation",
        "refine_at_max_next": "Above G7 Dao there is no refining: G8 Celestial gear is forged whole, with Celestial recipes (Mahayana).",
        "refine_at_absolute_max": "Celestial — the highest grade in the world",
        "inv_detail_refine_hint": "Refine this item at the 🛡️ {workshop} (Crafting tab › ⚒️ Forge segment) by consuming an identical duplicate.",
        "inv_detail_refine_at_max": "Max grade (G7 Dao) — there is no refining above this. G8 Celestial gear is forged whole, with Celestial recipes (Mahayana).",
        "inv_detail_refine_absolute_max": "G8 Celestial — the highest grade in the world. There is no refining and no forging above this.",
    },
    "es": {
        "pill_found_current": "Cimiento actual: {quality} (×{mult} a los stats)",
        "pill_found_current_none": "Cimiento aún no establecido",
        "pill_found_locked": "Tu Cimiento es Sagrado — la cima. Esta píldora no cambia nada.",
        "pill_found_odds_title": "Resultado posible:",
        "pill_found_sacred_now": "Con Cimiento Perfecto y esta calidad, el resultado es el Cimiento Sagrado (×2.00) — garantizado.",
        "pill_found_sacred_hint": "El Cimiento Sagrado (×2.00) sólo nace de una píldora Celestial usada sobre un Cimiento Perfecto.",
        "pill_found_risk": "Es una apuesta: el Cimiento puede EMPEORAR. No hay vuelta atrás.",
        "pill_found_trial": "Repite la prueba del Cimiento: 3 desafíos (Alma · Percepción · Suerte) contra umbrales que suben con tu prestigio. El mejor resultado posible es Perfecto.",
        "pill_found_result": "🌌 ¡Cimiento Reforjado! {old} → {new}",
        "pill_found_result_sacred": "🌌✨ ¡CIMIENTO SAGRADO DESPERTADO! {old} → {new}",
        "pill_found_result_mult": "🏯 Multiplicador de stats ahora: ×{mult}",
        "pill_found_result_same": "🏯 El Cimiento resistió: sigue {quality} (×{mult}). Nada cambió.",
        "pill_found_result_down": "💔 El Cimiento se agrietó: {old} → {new}  (×{old_mult} → ×{new_mult})",
        "pill_found_result_mult_delta": "📈 Multiplicador de stats: ×{old_mult} → ×{new_mult}",
        "pill_found_locked_btn": "Nada que reforjar",
        "pill_foundation_sacred_locked": "Tu Cimiento es Sagrado — la cima. Esta píldora no haría nada, así que NADA fue consumido.",
        "pill_foundation_not_established": "Aún no tienes un Cimiento que reparar. NADA fue consumido.",
        "profile_foundation_label": "Cimiento",
        "refine_at_max_next": "Por encima de G7 Dao no hay refinado: el equipo G8 Celestial se forja entero, con recetas Celestiales (Mahayana).",
        "refine_at_absolute_max": "Celestial — el grado más alto del mundo",
        "inv_detail_refine_hint": "Refina este objeto en el 🛡️ {workshop} (pestaña Forja › segmento ⚒️ Forja) consumiendo un duplicado idéntico.",
        "inv_detail_refine_at_max": "Grado máximo (G7 Dao) — no hay refinado por encima. El equipo G8 Celestial se forja entero, con recetas Celestiales (Mahayana).",
        "inv_detail_refine_absolute_max": "G8 Celestial — el grado más alto del mundo. No hay refinado ni forja por encima.",
    },
}

# Strings que ja EXISTIAM e foram ENRIQUECIDAS por este lote (nao sao adicoes):
#  · workshop_err_max_grade — dizia so "grau maximo"; agora aponta o caminho
#    seguinte (Lei §1: a recusa diz o porque E para onde ir);
#  · pill_eff_* — "Rerolla Fundacao Eterna" nao e portugues de jogador.
CHAT_OVERRIDES: dict = {}
MINI_OVERRIDES = {
    "pt": {
        "workshop_err_max_grade": "Artefato já no grau máximo (G7 Dao). Acima disto, o equipamento G8 Celestial é forjado inteiro, com receitas Celestiais (Mahayana).",
        "pill_eff_eternal_foundation_reroll": "Refaz sua Fundação (aposta)",
        "pill_eff_foundation_reroll": "Refaz sua Fundação (ritual)",
    },
    "en": {
        "workshop_err_max_grade": "Artifact already at max grade (G7 Dao). Above this, G8 Celestial gear is forged whole, with Celestial recipes (Mahayana).",
        "pill_eff_eternal_foundation_reroll": "Rerolls your Foundation (gamble)",
        "pill_eff_foundation_reroll": "Rerolls your Foundation (ritual)",
    },
    "es": {
        "workshop_err_max_grade": "Artefacto ya en el grado máximo (G7 Dao). Por encima, el equipo G8 Celestial se forja entero, con recetas Celestiales (Mahayana).",
        "pill_eff_eternal_foundation_reroll": "Rehace tu Cimiento (apuesta)",
        "pill_eff_foundation_reroll": "Rehace tu Cimiento (ritual)",
    },
}


def _apply(path: str, additions: dict, overrides: dict | None = None) -> tuple:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    before = len(data)
    for k, v in additions.items():
        if k not in data:
            data[k] = v
    for k, v in (overrides or {}).items():
        data[k] = v
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)
        f.write("\n")
    return before, len(data)


def main() -> None:
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "locales", lang + ".json"), CHAT[lang],
                      CHAT_OVERRIDES.get(lang))
        print("chat " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "miniapp", "i18n", lang + ".json"), MINIAPP[lang],
                      MINI_OVERRIDES.get(lang))
        print("mini " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")


if __name__ == "__main__":
    main()
