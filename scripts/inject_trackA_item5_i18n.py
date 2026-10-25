"""Track A item 5 — Raízes (composição elemental) i18n.

Re-runnable: OVERWRITES this wave's own (uniquely-namespaced) keys with the
current values, then re-dumps each locale indent=4 + ensure_ascii=False +
trailing newline. All keys below are namespaced (root_el_*, root_archetype_*,
root_reson_*, status_root_resonance*, status_root_variant) and were verified not
to collide with any pre-existing key.
  * CHAT    (locales/*.json)      — the /status "a tua raíz ressoa…" block: the 12
    element names + 5 archetype labels + the 3 status lines (server-rendered).
  * MINIAPP (miniapp/i18n/*.json) — the CultivationTab resonance card: same element
    + archetype vocabulary + per-archetype lore + the card title/variant/future labels.
pt = PT-BR (você/seu). DISCLOSURE-ONLY: the future teaser is explicit ("ainda sem
efeito") — NO fake %; the elemental gating + Wuxing modifiers are wipe-bound (Lei §1/§5).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The 12 element names — shared vocabulary, injected into BOTH surfaces.
_ELEMENTS = {
    "pt": {
        "root_el_metal": "Metal", "root_el_wood": "Madeira", "root_el_water": "Água",
        "root_el_fire": "Fogo", "root_el_earth": "Terra", "root_el_lightning": "Relâmpago",
        "root_el_ice": "Gelo", "root_el_wind": "Vento", "root_el_dark": "Trevas",
        "root_el_chaos": "Caos", "root_el_space": "Espaço", "root_el_time": "Tempo",
    },
    "en": {
        "root_el_metal": "Metal", "root_el_wood": "Wood", "root_el_water": "Water",
        "root_el_fire": "Fire", "root_el_earth": "Earth", "root_el_lightning": "Lightning",
        "root_el_ice": "Ice", "root_el_wind": "Wind", "root_el_dark": "Darkness",
        "root_el_chaos": "Chaos", "root_el_space": "Space", "root_el_time": "Time",
    },
    "es": {
        "root_el_metal": "Metal", "root_el_wood": "Madera", "root_el_water": "Agua",
        "root_el_fire": "Fuego", "root_el_earth": "Tierra", "root_el_lightning": "Relámpago",
        "root_el_ice": "Hielo", "root_el_wind": "Viento", "root_el_dark": "Tinieblas",
        "root_el_chaos": "Caos", "root_el_space": "Espacio", "root_el_time": "Tiempo",
    },
}

# The 5 archetype labels — shared vocabulary, injected into BOTH surfaces.
_ARCHETYPES = {
    "pt": {
        "root_archetype_single": "Raiz Única", "root_archetype_dual": "Raiz Dupla",
        "root_archetype_tri": "Raiz Tríplice", "root_archetype_quad": "Raiz Quádrupla",
        "root_archetype_penta": "Raiz Penta",
    },
    "en": {
        "root_archetype_single": "Single Root", "root_archetype_dual": "Dual Root",
        "root_archetype_tri": "Triple Root", "root_archetype_quad": "Quad Root",
        "root_archetype_penta": "Penta Root",
    },
    "es": {
        "root_archetype_single": "Raíz Única", "root_archetype_dual": "Raíz Doble",
        "root_archetype_tri": "Raíz Triple", "root_archetype_quad": "Raíz Cuádruple",
        "root_archetype_penta": "Raíz Penta",
    },
}


def _merge(*dicts):
    out = {}
    for d in dicts:
        out.update(d)
    return out


CHAT = {
    "pt": _merge(_ELEMENTS["pt"], _ARCHETYPES["pt"], {
        "status_root_resonance": "🌌 {archetype}: {elements}",
        "status_root_variant": "✦ Variante adormecida — a Pedra de Teste comum não a lê.",
        "status_root_resonance_future": "↳ a afinidade elemental desperta no novo mundo (ainda sem efeito).",
    }),
    "en": _merge(_ELEMENTS["en"], _ARCHETYPES["en"], {
        "status_root_resonance": "🌌 {archetype}: {elements}",
        "status_root_variant": "✦ A dormant variant — the common Testing Stone cannot read it.",
        "status_root_resonance_future": "↳ the elemental affinity awakens in the new world (no effect yet).",
    }),
    "es": _merge(_ELEMENTS["es"], _ARCHETYPES["es"], {
        "status_root_resonance": "🌌 {archetype}: {elements}",
        "status_root_variant": "✦ Variante dormida — la Piedra de Prueba común no la lee.",
        "status_root_resonance_future": "↳ la afinidad elemental despierta en el nuevo mundo (aún sin efecto).",
    }),
}

MINIAPP = {
    "pt": _merge(_ELEMENTS["pt"], _ARCHETYPES["pt"], {
        "root_reson_title": "Sua raiz ressoa…",
        "root_reson_variant": "Variante adormecida — a Pedra de Teste comum não a lê.",
        "root_reson_future": "A afinidade elemental (compreensão e combate mais afins ao seu elemento) desperta no novo mundo — ainda sem efeito.",
        "root_archetype_single_lore": "Um só elemento — prodígio veloz e afiado, mas trancado fora de muitas artes.",
        "root_archetype_dual_lore": "Dois elementos — equilíbrio entre velocidade e versatilidade.",
        "root_archetype_tri_lore": "Três elementos — ampla afinidade, um caminho de muitas portas.",
        "root_archetype_quad_lore": "Quatro elementos — lenta a firmar-se, mas de horizonte vasto.",
        "root_archetype_penta_lore": "Os cinco elementos — lenta no início, mas a única raiz que pode fundi-los e alcançar as artes supremas.",
    }),
    "en": _merge(_ELEMENTS["en"], _ARCHETYPES["en"], {
        "root_reson_title": "Your root resonates…",
        "root_reson_variant": "A dormant variant — the common Testing Stone cannot read it.",
        "root_reson_future": "The elemental affinity (faster comprehension and combat in your element) awakens in the new world — no effect yet.",
        "root_archetype_single_lore": "A single element — a fast, sharp prodigy, but locked out of many arts.",
        "root_archetype_dual_lore": "Two elements — a balance of speed and versatility.",
        "root_archetype_tri_lore": "Three elements — broad affinity, a path of many doors.",
        "root_archetype_quad_lore": "Four elements — slow to settle, but vast in reach.",
        "root_archetype_penta_lore": "All five elements — slow at first, but the only root that can fuse them and reach the supreme arts.",
    }),
    "es": _merge(_ELEMENTS["es"], _ARCHETYPES["es"], {
        "root_reson_title": "Tu raíz resuena…",
        "root_reson_variant": "Una variante dormida — la Piedra de Prueba común no la lee.",
        "root_reson_future": "La afinidad elemental (comprensión y combate más afines a tu elemento) despierta en el nuevo mundo — aún sin efecto.",
        "root_archetype_single_lore": "Un solo elemento — prodigio veloz y afilado, pero excluido de muchas artes.",
        "root_archetype_dual_lore": "Dos elementos — equilibrio entre velocidad y versatilidad.",
        "root_archetype_tri_lore": "Tres elementos — amplia afinidad, un camino de muchas puertas.",
        "root_archetype_quad_lore": "Cuatro elementos — lenta en asentarse, pero de vasto alcance.",
        "root_archetype_penta_lore": "Los cinco elementos — lenta al inicio, pero la única raíz que puede fusionarlos y alcanzar las artes supremas.",
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
        data[k] = v  # overwrite — keys are uniquely namespaced to this wave
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
