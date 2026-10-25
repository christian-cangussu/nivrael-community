# -*- coding: utf-8 -*-
"""TAPETE QoL §5 (feedback 2026-06-09) — i18n keys, chat + mini-app.

Itens: 1 desmonte em massa por qualidade · 2 qty na forja · 4/5 disclosure do
mercado (refino/encantamento + cor) · 6 ⏱️ pílulas · 7 teaser T4/T5 ·
8 erro de realm com número · 10 descrições de títulos extra · 11 disclosure
percepção→Leis.

Regras (iguais ao inject_onda5fase2_i18n.py): idempotente (só adiciona keys
novas; correr 1×, commitar os JSONs); pt = PT-BR (você/seu, ativo); cada
{token} aparece NO MÁXIMO 1× por string; placeholders em ASCII.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Keys em AMBAS as superfícies ─────────────────────────────────────────────
_SHARED = {
    "pt": {
        # Qualidade de forja ("refino" no vocabulário do [jogador]) — itens 1/3/4/5
        "art_quality_normal": "Normal",
        "art_quality_perfect": "Perfeito",
        "art_quality_divine": "Divino",
        "art_quality_spirit": "Espírito",
        # review 2026-06-12: grade acima do catálogo (refine_artifact) = chip
        # próprio, SEMPRE acima de qualquer corte de qualidade no desmonte
        "art_quality_refined": "Refinado",
    },
    "en": {
        "art_quality_normal": "Normal",
        "art_quality_perfect": "Perfect",
        "art_quality_divine": "Divine",
        "art_quality_spirit": "Spirit",
        "art_quality_refined": "Refined",
    },
    "es": {
        "art_quality_normal": "Normal",
        "art_quality_perfect": "Perfecto",
        "art_quality_divine": "Divino",
        "art_quality_spirit": "Espíritu",
        "art_quality_refined": "Refinado",
    },
}

# ── Chat-only ────────────────────────────────────────────────────────────────
_CHAT = {
    "pt": {
        # Item 10 — títulos extra (JSONB) finalmente descritos (cosméticos)
        "title_desc_patron_of_the_dao": "Concedido no seu primeiro aporte de Jade Espiritual. Título cosmético — aparece antes do seu nome.",
        "title_desc_celestial_patron": "Recompensa do marco 30 do Passe Celestial. Título cosmético — aparece antes do seu nome.",
        "title_desc_core_forger": "Recompensa do Passe de Batalha. Título cosmético — aparece antes do seu nome.",
        "title_desc_dao_benefactor": "Honra de Benfeitor do Dao (apoio VIP). Título cosmético — aparece antes do seu nome.",
        "title_desc_heavens_patron": "Honra suprema dos Céus (apoio VIP máximo). Título cosmético — aparece antes do seu nome.",
        # Item 11 — disclosure de velocidade de compreensão no /dao
        "dao_comp_header": "📖 *Velocidade de Compreensão*",
        "dao_comp_fragments": "🧩 Fragmentos Supremos: {pct}% por ciclo de 30s — sua percepção ({perception}) acelera linearmente.",
        "dao_comp_frag_capped": "   ✅ _No teto: cada ciclo de meditação já concede fragmento._",
        "dao_comp_discovery": "🧭 Descoberta de Leis: {pct}% por ciclo — restam {remaining} de {total} Leis acessíveis. _Quanto mais você aprende, mais difícil fica._",
        "dao_comp_rarity": "✨ Raridade: percepção desloca os achados para Leis raras (×{factor}).",
        "dao_comp_rarity_capped": "   ✅ _No teto: ×2 a partir de 10000 de percepção._",
        "dao_comp_chat_note": "_Valores na base ×1 — o tipo de meditação e os buffs multiplicam tudo._",
    },
    "en": {
        "title_desc_patron_of_the_dao": "Granted on your first Spirit Jade top-up. Cosmetic title — shown before your name.",
        "title_desc_celestial_patron": "Celestial Pass milestone 30 reward. Cosmetic title — shown before your name.",
        "title_desc_core_forger": "Battle Pass reward. Cosmetic title — shown before your name.",
        "title_desc_dao_benefactor": "Dao Benefactor honor (VIP support). Cosmetic title — shown before your name.",
        "title_desc_heavens_patron": "Supreme honor of the Heavens (top VIP support). Cosmetic title — shown before your name.",
        "dao_comp_header": "📖 *Comprehension Speed*",
        "dao_comp_fragments": "🧩 Supreme Fragments: {pct}% per 30s tick — your perception ({perception}) scales it linearly.",
        "dao_comp_frag_capped": "   ✅ _Capped: every meditation tick already grants a fragment._",
        "dao_comp_discovery": "🧭 Law discovery: {pct}% per tick — {remaining} of {total} accessible Laws remain. _The more you learn, the harder it gets._",
        "dao_comp_rarity": "✨ Rarity: perception shifts finds toward rarer Laws (×{factor}).",
        "dao_comp_rarity_capped": "   ✅ _Capped: ×2 from 10000 perception onward._",
        "dao_comp_chat_note": "_Base ×1 values — the meditation type and buffs multiply everything._",
    },
    "es": {
        "title_desc_patron_of_the_dao": "Otorgado en tu primera recarga de Jade Espiritual. Título cosmético — aparece antes de tu nombre.",
        "title_desc_celestial_patron": "Recompensa del hito 30 del Pase Celestial. Título cosmético — aparece antes de tu nombre.",
        "title_desc_core_forger": "Recompensa del Pase de Batalla. Título cosmético — aparece antes de tu nombre.",
        "title_desc_dao_benefactor": "Honor de Benefactor del Dao (apoyo VIP). Título cosmético — aparece antes de tu nombre.",
        "title_desc_heavens_patron": "Honor supremo de los Cielos (apoyo VIP máximo). Título cosmético — aparece antes de tu nombre.",
        "dao_comp_header": "📖 *Velocidad de Comprensión*",
        "dao_comp_fragments": "🧩 Fragmentos Supremos: {pct}% por ciclo de 30s — tu percepción ({perception}) la acelera linealmente.",
        "dao_comp_frag_capped": "   ✅ _Al tope: cada ciclo de meditación ya concede fragmento._",
        "dao_comp_discovery": "🧭 Descubrimiento de Leyes: {pct}% por ciclo — quedan {remaining} de {total} Leyes accesibles. _Cuanto más aprendes, más difícil se vuelve._",
        "dao_comp_rarity": "✨ Rareza: la percepción desplaza los hallazgos hacia Leyes raras (×{factor}).",
        "dao_comp_rarity_capped": "   ✅ _Al tope: ×2 a partir de 10000 de percepción._",
        "dao_comp_chat_note": "_Valores en base ×1 — el tipo de meditación y los buffs lo multiplican todo._",
    },
}

# ── Mini-app-only ────────────────────────────────────────────────────────────
_MINI = {
    "pt": {
        # Item 1 — desmonte em massa por qualidade + preview/confirmação
        "forge_bulk_quality_label": "Refino máximo a desmontar",
        "forge_bulk_quality_all": "Todas",
        "forge_bulk_confirm_title": "Confirmar desmonte",
        "forge_bulk_confirm_body": "Você vai desmontar {n} itens e receber ~{ss} Pedras Espirituais + ~25% dos materiais de forja de volta.",
        "forge_bulk_confirm_note": "Itens equipados, trancados e acima do filtro de refino ficam SEMPRE de fora.",
        "forge_bulk_confirm_btn": "Desmontar {n}",
        "forge_bulk_cancel_btn": "Cancelar",
        # Item 2 — caixa de quantidade no craft da forja
        "forge_bulk_custom_label": "Quantidade:",
        # Item 4 — disclosure do mercado
        "market_art_spirit": "Espírito desperto",
        # Item 7 — teaser honesto das receitas T4/T5 (Lei §1)
        "alch_locked_tier_teaser": "Estas receitas dormem… e despertam no novo mundo.",
        # Item 8 — erro de realm com o número
        "alch_err_realm_too_low_n": "⛔ Reino insuficiente — requer Reino {n}+",
        # Item 10 — secção Honras
        "ach_honors_section": "Honras",
        # Item 11 — card de velocidade de compreensão
        "dao_comp_header_mini": "Velocidade de Compreensão",
        "dao_comp_perception_chip": "Sua percepção",
        "dao_comp_fragments_chip": "Fragmentos por ciclo",
        "dao_comp_discovery_chip": "Descoberta ({remaining}/{total} restantes)",
        "dao_comp_rarity_chip": "Raridade (percepção)",
        "dao_comp_note": "A dificuldade cresce a cada Lei aprendida; o tipo de meditação multiplica tudo.",
    },
    "en": {
        "forge_bulk_quality_label": "Max refine quality to dismantle",
        "forge_bulk_quality_all": "All",
        "forge_bulk_confirm_title": "Confirm dismantle",
        "forge_bulk_confirm_body": "You will dismantle {n} items and receive ~{ss} Spirit Stones + ~25% of the forging materials back.",
        "forge_bulk_confirm_note": "Equipped, locked and above-the-filter items are ALWAYS excluded.",
        "forge_bulk_confirm_btn": "Dismantle {n}",
        "forge_bulk_cancel_btn": "Cancel",
        "forge_bulk_custom_label": "Amount:",
        "market_art_spirit": "Awakened spirit",
        "alch_locked_tier_teaser": "These recipes slumber… they awaken in the new world.",
        "alch_err_realm_too_low_n": "⛔ Realm too low — requires Realm {n}+",
        "ach_honors_section": "Honors",
        "dao_comp_header_mini": "Comprehension Speed",
        "dao_comp_perception_chip": "Your perception",
        "dao_comp_fragments_chip": "Fragments per tick",
        "dao_comp_discovery_chip": "Discovery ({remaining}/{total} left)",
        "dao_comp_rarity_chip": "Rarity (perception)",
        "dao_comp_note": "Difficulty grows with every Law learned; the meditation type multiplies everything.",
    },
    "es": {
        "forge_bulk_quality_label": "Refinado máximo a desmontar",
        "forge_bulk_quality_all": "Todas",
        "forge_bulk_confirm_title": "Confirmar desmontaje",
        "forge_bulk_confirm_body": "Vas a desmontar {n} objetos y recibirás ~{ss} Piedras Espirituales + ~25% de los materiales de forja.",
        "forge_bulk_confirm_note": "Los objetos equipados, bloqueados y por encima del filtro quedan SIEMPRE fuera.",
        "forge_bulk_confirm_btn": "Desmontar {n}",
        "forge_bulk_cancel_btn": "Cancelar",
        "forge_bulk_custom_label": "Cantidad:",
        "market_art_spirit": "Espíritu despierto",
        "alch_locked_tier_teaser": "Estas recetas duermen… despiertan en el nuevo mundo.",
        "alch_err_realm_too_low_n": "⛔ Reino insuficiente — requiere Reino {n}+",
        "ach_honors_section": "Honores",
        "dao_comp_header_mini": "Velocidad de Comprensión",
        "dao_comp_perception_chip": "Tu percepción",
        "dao_comp_fragments_chip": "Fragmentos por ciclo",
        "dao_comp_discovery_chip": "Descubrimiento ({remaining}/{total} restantes)",
        "dao_comp_rarity_chip": "Rareza (percepción)",
        "dao_comp_note": "La dificultad crece con cada Ley aprendida; el tipo de meditación lo multiplica todo.",
    },
}

LANGS = ("pt", "en", "es")
CHAT = {lc: {**_SHARED[lc], **_CHAT[lc]} for lc in LANGS}
MINIAPP = {lc: {**_SHARED[lc], **_MINI[lc]} for lc in LANGS}


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
