"""Track A (B4) — Mind Sea 识海 ("Mar da Consciência") i18n.

Re-runnable: OVERWRITES this wave's own (uniquely-namespaced) keys with the
current values, then re-dumps each locale indent=4 + ensure_ascii=False +
trailing newline. All keys are namespaced (status_mind_sea_* for the chat framing,
mind_sea_* for the mini framing, mind_sea_tier_* for the shared 4 depth tiers +
lore) and were verified not to collide with any pre-existing key (grep "mind_sea"
hit only docs before this wave).
  * CHAT    (locales/*.json)      — the /status "Mar da Consciência" block: title +
    the derived depth tier line + the "your Divine Sense flows from here" note +
    the honest future teaser (server-rendered in handlers/cultivation._mind_sea_lines).
  * MINIAPP (miniapp/i18n/*.json) — the CultivationTab Mind Sea Card (same copy) +
    the NpcCultivatorModal depth-tier chip (reuses the mind_sea_tier_* labels).
pt = PT-BR (você/seu). DISCLOSURE-ONLY (Lei §1, §3, §5): a REFRAME of the existing
soul_strength + perception stats (no new column). The teaser is explicit ("ainda
sem efeito") — NEVER a fake % nor an "immune to X" claim; the soul-defense /
alchemy-focus / Soul Lamp mechanics are wipe-bound. Nothing ticks or applies a
modifier this wave.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The 4 depth tiers + lore — SHARED across chat + mini (each locale file gets its
# own copy; the same keys are read by handlers/cultivation and miniapp/tabs.js).
TIERS = {
    "pt": {
        "mind_sea_tier_shallow": "Mar Raso",
        "mind_sea_tier_deep": "Mar Profundo",
        "mind_sea_tier_vast": "Mar Vasto",
        "mind_sea_tier_fathomless": "Mar Sem-Fundo",
        "mind_sea_tier_shallow_lore": "recém-formado — as águas da consciência ainda são rasas e turvas.",
        "mind_sea_tier_deep_lore": "as águas assentaram; o Sentido Divino alcança mais longe.",
        "mind_sea_tier_vast_lore": "uma vastidão serena onde a alma se move sem esforço.",
        "mind_sea_tier_fathomless_lore": "sem margem nem leito — o espírito toca o ilimitado.",
    },
    "en": {
        "mind_sea_tier_shallow": "Shallow Sea",
        "mind_sea_tier_deep": "Deep Sea",
        "mind_sea_tier_vast": "Vast Sea",
        "mind_sea_tier_fathomless": "Fathomless Sea",
        "mind_sea_tier_shallow_lore": "newly formed — the waters of consciousness are still shallow and murky.",
        "mind_sea_tier_deep_lore": "the waters have settled; your Divine Sense reaches farther.",
        "mind_sea_tier_vast_lore": "a serene vastness where the soul moves without effort.",
        "mind_sea_tier_fathomless_lore": "no shore, no floor — the spirit touches the boundless.",
    },
    "es": {
        "mind_sea_tier_shallow": "Mar Somero",
        "mind_sea_tier_deep": "Mar Profundo",
        "mind_sea_tier_vast": "Mar Vasto",
        "mind_sea_tier_fathomless": "Mar Sin Fondo",
        "mind_sea_tier_shallow_lore": "recién formado — las aguas de la consciencia aún son someras y turbias.",
        "mind_sea_tier_deep_lore": "las aguas se asentaron; el Sentido Divino alcanza más lejos.",
        "mind_sea_tier_vast_lore": "una vastedad serena donde el alma se mueve sin esfuerzo.",
        "mind_sea_tier_fathomless_lore": "sin orilla ni lecho — el espíritu toca lo ilimitado.",
    },
}

CHAT = {
    "pt": {
        "status_mind_sea_title": "🪷 Mar da Consciência 识海",
        "status_mind_sea_tier": "{emoji} {tier} — {lore}",
        "status_mind_sea_sense": "↳ daqui emana o seu Sentido Divino 神識 — já guia a sua Exploração",
        "status_mind_sea_future": "↳ a defesa de alma e o foco alquímico despertam no novo mundo — ainda sem efeito",
        **TIERS["pt"],
    },
    "en": {
        "status_mind_sea_title": "🪷 Sea of Consciousness 识海",
        "status_mind_sea_tier": "{emoji} {tier} — {lore}",
        "status_mind_sea_sense": "↳ from here flows your Divine Sense 神識 — it already guides your Exploration",
        "status_mind_sea_future": "↳ soul defense and alchemical focus awaken in the new world — no effect yet",
        **TIERS["en"],
    },
    "es": {
        "status_mind_sea_title": "🪷 Mar de la Consciencia 识海",
        "status_mind_sea_tier": "{emoji} {tier} — {lore}",
        "status_mind_sea_sense": "↳ de aquí emana tu Sentido Divino 神識 — ya guía tu Exploración",
        "status_mind_sea_future": "↳ la defensa del alma y el foco alquímico despiertan en el nuevo mundo — aún sin efecto",
        **TIERS["es"],
    },
}

MINIAPP = {
    "pt": {
        "mind_sea_title": "Mar da Consciência 识海",
        "mind_sea_sense": "Daqui emana o seu Sentido Divino 神識 — já guia a sua Exploração.",
        "mind_sea_future": "A defesa de alma e o foco alquímico despertam no novo mundo — ainda sem efeito.",
        **TIERS["pt"],
    },
    "en": {
        "mind_sea_title": "Sea of Consciousness 识海",
        "mind_sea_sense": "From here flows your Divine Sense 神識 — it already guides your Exploration.",
        "mind_sea_future": "Soul defense and alchemical focus awaken in the new world — no effect yet.",
        **TIERS["en"],
    },
    "es": {
        "mind_sea_title": "Mar de la Consciencia 识海",
        "mind_sea_sense": "De aquí emana tu Sentido Divino 神識 — ya guía tu Exploración.",
        "mind_sea_future": "La defensa del alma y el foco alquímico despiertan en el nuevo mundo — aún sin efecto.",
        **TIERS["es"],
    },
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
