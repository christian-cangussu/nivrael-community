"""Track A item 6 — Técnicas (eixo de Compreensão) i18n.

Re-runnable: OVERWRITES the keys below (reframe + new) with the current values, then
re-dumps each locale indent=4 + ensure_ascii=False + trailing newline.

This wave is a REFRAME, not a new mechanic (owner decision 2026-06-21, §6): the live
``mastery_level`` axis IS the Compreensão the Grand Design §9 asks for, so we relabel it
"Compreensão" (Vislumbre→Consumação) across both surfaces — PURE i18n, ZERO mechanic
change — and add three disclosure strings (loadout-cap hint + Art↔Root resonance + its
honest future teaser). Element names reuse item-5's shared ``root_el_*`` keys.

  * CHAT    (locales/*.json)      — /tecnicas list + per-tech detail + absorb/levelup msgs.
  * MINIAPP (miniapp/i18n/*.json) — CombatTab loadout panel + TechDetailModal.

pt = PT-BR (você/sua). DISCLOSURE-ONLY: the resonance future teaser is explicit ("ainda
sem efeito") — NO fake %; the elemental gating + the uncapped non-qi Comprehension lever
are wipe-bound (Lei §1/§5). NOTE: only TECHNIQUE mastery labels are reframed — alchemy
(alch_*), forge (frg_*/forge_*), sect ("Maestro"), and intent keys are deliberately
LEFT untouched.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The 5-stage Comprehension ladder (reframe of the existing mastery stage names),
# shared by BOTH surfaces (same keys exist in chat + mini).
_STAGES = {
    "pt": {
        "technique_mastery_stage_1": "Vislumbre",
        "technique_mastery_stage_2": "Pequeno Sucesso",
        "technique_mastery_stage_3": "Grande Sucesso",
        "technique_mastery_stage_4": "Perfeição",
        "technique_mastery_stage_5": "Consumação",
    },
    "en": {
        "technique_mastery_stage_1": "Glimpse",
        "technique_mastery_stage_2": "Small Success",
        "technique_mastery_stage_3": "Great Success",
        "technique_mastery_stage_4": "Perfection",
        "technique_mastery_stage_5": "Consummation",
    },
    "es": {
        "technique_mastery_stage_1": "Vislumbre",
        "technique_mastery_stage_2": "Pequeño Éxito",
        "technique_mastery_stage_3": "Gran Éxito",
        "technique_mastery_stage_4": "Perfección",
        "technique_mastery_stage_5": "Consumación",
    },
}

# The three NEW disclosure strings — shared by BOTH surfaces.
_NEW = {
    "pt": {
        "tech_loadout_cap_hint": "☯️ O Mar de Qi suporta {max} artes de combate ativas — cresce com o reino.",
        "tech_root_resonance": "Ressoa com sua raiz de {element}",
        "tech_root_resonance_future": "↳ a harmonia elemento↔arte desperta no novo mundo (ainda sem efeito).",
    },
    "en": {
        "tech_loadout_cap_hint": "☯️ Your Sea of Qi sustains {max} active combat arts — it grows with your realm.",
        "tech_root_resonance": "Resonates with your {element} root",
        "tech_root_resonance_future": "↳ the element↔art harmony awakens in the new world (no effect yet).",
    },
    "es": {
        "tech_loadout_cap_hint": "☯️ Tu Mar de Qi sostiene {max} artes de combate activas — crece con tu reino.",
        "tech_root_resonance": "Resuena con tu raíz de {element}",
        "tech_root_resonance_future": "↳ la armonía elemento↔arte despierta en el nuevo mundo (aún sin efecto).",
    },
}


def _merge(*dicts):
    out = {}
    for d in dicts:
        out.update(d)
    return out


# ── CHAT (locales/*.json) — stages + new + chat-only label reframes ──────────
CHAT = {
    "pt": _merge(_STAGES["pt"], _NEW["pt"], {
        "tech_detail_mastery": "{emoji} Compreensão: *{stage}* ({xp}/{next_xp} XP) ×{mult}",
        "tech_grade_mastery_low": "⚠️ Você precisa de Compreensão nível {required} para esta evolução.",
        "tech_upgrade_locked": "  🔒 Evoluir {grade}: Req Compreensão {mastery}{extras}",
        "technique_mastery_xp_gain": "+{xp} XP de Compreensão",
        "combat_tech_absorbed_all": "📖 Absorvidos ×{qty} scrolls de *{name}*! +{xp} XP de Compreensão",
        "inv_tech_absorb": "📖 *{name}* absorvida! +{xp} XP de Compreensão",
        "inv_tech_absorb_levelup": "⬆️ Compreensão de *{name}* alcançou *{stage}*! (×{mult})",
    }),
    "en": _merge(_STAGES["en"], _NEW["en"], {
        "tech_detail_mastery": "{emoji} Comprehension: *{stage}* ({xp}/{next_xp} XP) ×{mult}",
        "tech_grade_mastery_low": "⚠️ Comprehension level {required} required for this upgrade.",
        "tech_upgrade_locked": "  🔒 Upgrade {grade}: Req Comprehension {mastery}{extras}",
        "technique_mastery_xp_gain": "+{xp} Comprehension XP",
        "combat_tech_absorbed_all": "📖 Absorbed ×{qty} scrolls of *{name}*! +{xp} Comprehension XP",
        "inv_tech_absorb": "📖 *{name}* absorbed! +{xp} Comprehension XP",
        "inv_tech_absorb_levelup": "⬆️ *{name}* comprehension reached *{stage}*! (×{mult})",
    }),
    "es": _merge(_STAGES["es"], _NEW["es"], {
        "tech_detail_mastery": "{emoji} Comprensión: *{stage}* ({xp}/{next_xp} XP) ×{mult}",
        "tech_grade_mastery_low": "⚠️ Se requiere Comprensión nivel {required} para esta evolución.",
        "tech_upgrade_locked": "  🔒 Evolucionar {grade}: Req Comprensión {mastery}{extras}",
        "technique_mastery_xp_gain": "+{xp} XP de Comprensión",
        "combat_tech_absorbed_all": "📖 ¡Absorbidos ×{qty} pergaminos de *{name}*! +{xp} XP de Comprensión",
        "inv_tech_absorb": "📖 ¡*{name}* absorbida! +{xp} XP de Comprensión",
        "inv_tech_absorb_levelup": "⬆️ ¡Comprensión de *{name}* alcanzó *{stage}*! (×{mult})",
    }),
}

# ── MINIAPP (miniapp/i18n/*.json) — stages + new + mini-only label reframes ──
MINIAPP = {
    "pt": _merge(_STAGES["pt"], _NEW["pt"], {
        "combat_detail_grade_req_mastery": "Compreensão mínima: nível {n}",
        "combat_detail_mastery_max": "Compreensão máxima — {emoji} ×{mult}",
        "combat_detail_mastery_progress": "Progresso de Compreensão",
        "combat_grade_upgrade_mastery": "Precisa de compreensão nível {n}.",
        "combat_result_mastery_up": "Compreensão de {emoji} {name} → nível {lvl} (×{mult})",
        "combat_tech_detail_mastery": "Compreensão: {emoji} {stage} ×{mult}",
        "combat_tech_mastery_label": "Compreensão",
        "combat_tech_xp_maxed": "Compreensão máxima",
    }),
    "en": _merge(_STAGES["en"], _NEW["en"], {
        "combat_detail_grade_req_mastery": "Min comprehension: level {n}",
        "combat_detail_mastery_max": "Comprehension maxed — {emoji} ×{mult}",
        "combat_detail_mastery_progress": "Comprehension Progress",
        "combat_grade_upgrade_mastery": "Needs comprehension level {n}.",
        "combat_result_mastery_up": "{emoji} {name} comprehension → level {lvl} (×{mult})",
        "combat_tech_detail_mastery": "Comprehension: {emoji} {stage} ×{mult}",
        "combat_tech_mastery_label": "Comprehension",
        "combat_tech_xp_maxed": "Comprehension maxed",
    }),
    "es": _merge(_STAGES["es"], _NEW["es"], {
        "combat_detail_grade_req_mastery": "Comprensión mínima: nivel {n}",
        "combat_detail_mastery_max": "Comprensión máxima — {emoji} ×{mult}",
        "combat_detail_mastery_progress": "Progreso de Comprensión",
        "combat_grade_upgrade_mastery": "Necesita comprensión nivel {n}.",
        "combat_result_mastery_up": "Comprensión de {emoji} {name} → nivel {lvl} (×{mult})",
        "combat_tech_detail_mastery": "Comprensión: {emoji} {stage} ×{mult}",
        "combat_tech_mastery_label": "Comprensión",
        "combat_tech_xp_maxed": "Comprensión máxima",
    }),
}


def _apply(path, additions):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    before = len(data)
    added = changed = 0
    for k, v in additions.items():
        if k not in data:
            added += 1
        elif data[k] != v:
            changed += 1
        data[k] = v  # overwrite — reframe of existing keys + this wave's new keys
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write("\n")
    return before, len(data), added, changed


def main():
    for lang, adds in CHAT.items():
        before, after, added, changed = _apply(os.path.join(ROOT, "locales", f"{lang}.json"), adds)
        print(f"chat    {lang}: {before} -> {after} (+{added}, ~{changed} updated)")
    for lang, adds in MINIAPP.items():
        before, after, added, changed = _apply(os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json"), adds)
        print(f"miniapp {lang}: {before} -> {after} (+{added}, ~{changed} updated)")


if __name__ == "__main__":
    main()
