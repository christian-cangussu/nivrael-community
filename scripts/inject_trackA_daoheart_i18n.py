"""Track A (B4) — Dao Heart 道心 ("Coração Dao") i18n.

Re-runnable: OVERWRITES this wave's own (uniquely-namespaced) keys with the current
values, then re-dumps each locale indent=4 + ensure_ascii=False + trailing newline.
All keys are namespaced (status_dao_heart_* for the chat framing, dao_heart_* for the
mini framing, dao_heart_tier_* for the shared 5 firmeza tiers + lore, and
dao_heart_tendency_* for the shared 3 self-contained Path-tendency labels) and were
verified not to collide with any pre-existing key (grep "dao_heart" hit only docs
before this wave). The tendency labels are SELF-CONTAINED (the Path name + emoji baked
in) on purpose — the chat ``path_*`` name keys do NOT exist in the mini i18n, so this
avoids a cross-surface dependency and guarantees chat↔mini parity.
  * CHAT    (locales/*.json)      — the /status "Coração Dao" block: title + the
    derived firmeza tier line + the Will's tendency + the 心魔 link (variant by path
    state) + the honest future teaser (handlers/cultivation._dao_heart_lines).
  * MINIAPP (miniapp/i18n/*.json) — the CultivationTab Dao Heart Card (same copy).
pt = PT-BR (você/seu). DISCLOSURE-ONLY (Lei §1, §3, §5): a REFRAME of the existing
path + karma + divergence (no new column). The teaser is explicit ("ainda sem
efeito") — NEVER a fake % nor an "immune to X" claim; the intention-weighted karma /
choice verbs / 心魔劫 Heart-Demon Judgment are wipe-bound (v16.7 Forbidden Path).
Nothing ticks or applies a modifier this wave. Origin: player feedback ([jogador],
2026-06-23) — "karma bom/mau é raso; deveria passar pelo Coração Dao / pela Vontade".
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The 5 firmeza tiers + lore — SHARED across chat + mini (each locale file gets its
# own copy; the same keys are read by handlers/cultivation and miniapp/tabs.js).
TIERS = {
    "pt": {
        "dao_heart_tier_unshaken": "Coração Inabalável 不动心",
        "dao_heart_tier_firm": "Coração Firme",
        "dao_heart_tier_wavering": "Coração Vacilante",
        "dao_heart_tier_trembling": "Coração Trêmulo",
        "dao_heart_tier_forming": "Coração em Formação",
        "dao_heart_tier_unshaken_lore": "fundo no seu Caminho, distante de toda divergência — nada o move.",
        "dao_heart_tier_firm_lore": "firme no Caminho que escolheu; a Vontade não vacila.",
        "dao_heart_tier_wavering_lore": "a Vontade se afasta do Caminho — o coração começa a vacilar.",
        "dao_heart_tier_trembling_lore": "o karma roça (ou rompeu) o limite do Caminho; o 心魔 se agita.",
        "dao_heart_tier_forming_lore": "a Vontade ainda não cristalizou — o coração se forma a cada escolha.",
    },
    "en": {
        "dao_heart_tier_unshaken": "Unshaken Heart 不动心",
        "dao_heart_tier_firm": "Firm Heart",
        "dao_heart_tier_wavering": "Wavering Heart",
        "dao_heart_tier_trembling": "Trembling Heart",
        "dao_heart_tier_forming": "Forming Heart",
        "dao_heart_tier_unshaken_lore": "deep in your Path, far from any divergence — nothing moves it.",
        "dao_heart_tier_firm_lore": "steady on the Path you chose; the Will does not waver.",
        "dao_heart_tier_wavering_lore": "the Will drifts from the Path — the heart begins to waver.",
        "dao_heart_tier_trembling_lore": "your karma grazes (or has crossed) the Path's edge; the 心魔 stirs.",
        "dao_heart_tier_forming_lore": "the Will has not yet crystallized — the heart forms with each choice.",
    },
    "es": {
        "dao_heart_tier_unshaken": "Corazón Inquebrantable 不动心",
        "dao_heart_tier_firm": "Corazón Firme",
        "dao_heart_tier_wavering": "Corazón Vacilante",
        "dao_heart_tier_trembling": "Corazón Tembloroso",
        "dao_heart_tier_forming": "Corazón en Formación",
        "dao_heart_tier_unshaken_lore": "hondo en tu Camino, lejos de toda divergencia — nada lo mueve.",
        "dao_heart_tier_firm_lore": "firme en el Camino que elegiste; la Voluntad no vacila.",
        "dao_heart_tier_wavering_lore": "la Voluntad se aleja del Camino — el corazón empieza a vacilar.",
        "dao_heart_tier_trembling_lore": "tu karma roza (o ha cruzado) el límite del Camino; el 心魔 se agita.",
        "dao_heart_tier_forming_lore": "la Voluntad aún no ha cristalizado — el corazón se forma con cada elección.",
    },
}

# The 3 Path-tendency labels — SHARED, self-contained (name + emoji baked in) so no
# surface depends on the chat-only path_* keys. Substituted into the {tendency}
# placeholder of the (status_)dao_heart_tendency[_forming] sentence templates.
#
# NB key family: the labels live under `dao_heart_tend_label_*`, DISJOINT from the
# sentence templates (`dao_heart_tendency` / `_forming` on mini, `status_dao_heart_*`
# on chat). Earlier these were `dao_heart_tendency_*`, which shared a prefix with the
# mini template `dao_heart_tendency` — harmless today (engine tendency is only
# righteous/demonic/rogue, never 'forming') but a latent footgun. Disjoint now; the
# old keys are dropped via OBSOLETE below (review finding 2026-06-23, low/hardening).
TENDENCY = {
    "pt": {
        "dao_heart_tend_label_righteous": "Caminho Justo ☀️",
        "dao_heart_tend_label_demonic": "Caminho Demoníaco 👹",
        "dao_heart_tend_label_rogue": "Caminho Errante 🐺",
    },
    "en": {
        "dao_heart_tend_label_righteous": "Righteous Path ☀️",
        "dao_heart_tend_label_demonic": "Demonic Path 👹",
        "dao_heart_tend_label_rogue": "Rogue Path 🐺",
    },
    "es": {
        "dao_heart_tend_label_righteous": "Camino Justo ☀️",
        "dao_heart_tend_label_demonic": "Camino Demoníaco 👹",
        "dao_heart_tend_label_rogue": "Camino Errante 🐺",
    },
}

# Keys this wave once injected but has since renamed — popped from every locale file on
# each run so the rename leaves no orphans (keeps parity + re-runnability clean).
OBSOLETE = (
    "dao_heart_tendency_righteous",
    "dao_heart_tendency_demonic",
    "dao_heart_tendency_rogue",
)

CHAT = {
    "pt": {
        "status_dao_heart_title": "❤️‍🔥 Coração Dao 道心",
        "status_dao_heart_firmeza": "{emoji} {tier} — {lore}",
        "status_dao_heart_tendency": "↳ a sua Vontade segue o {tendency}",
        "status_dao_heart_tendency_forming": "↳ a sua Vontade ainda se forma — o karma se inclina para o {tendency}",
        "status_dao_heart_demon": "↳ o Coração Dao segura a alma contra o 心魔 Demônio Interior — se o seu karma divergir do Caminho, ele já o avisa",
        "status_dao_heart_demon_near": "↳ ⚠️ o seu karma se aproxima do limite onde o 心魔 Demônio Interior se agita — é o Coração Dao que segura a alma",
        "status_dao_heart_demon_rogue": "↳ o Caminho Errante não conhece divergência — a sua firmeza é a sua própria independência",
        "status_dao_heart_demon_forming": "↳ assim que a sua Vontade cristalizar, o Coração Dao segurará a alma contra o 心魔 Demônio Interior",
        "status_dao_heart_future": "↳ o karma pesado pela sua intenção, as escolhas além de bom/mau e o Julgamento do 心魔劫 despertam no novo mundo — ainda sem efeito",
        **TIERS["pt"],
        **TENDENCY["pt"],
    },
    "en": {
        "status_dao_heart_title": "❤️‍🔥 Dao Heart 道心",
        "status_dao_heart_firmeza": "{emoji} {tier} — {lore}",
        "status_dao_heart_tendency": "↳ your Will follows the {tendency}",
        "status_dao_heart_tendency_forming": "↳ your Will is still forming — your karma leans toward the {tendency}",
        "status_dao_heart_demon": "↳ the Dao Heart holds the soul against the 心魔 Heart Demon — should your karma diverge from the Path, it already warns you",
        "status_dao_heart_demon_near": "↳ ⚠️ your karma nears the edge where the 心魔 Heart Demon stirs — it is the Dao Heart that holds the soul",
        "status_dao_heart_demon_rogue": "↳ the Rogue Path knows no divergence — your firmness is your own independence",
        "status_dao_heart_demon_forming": "↳ once your Will crystallizes, the Dao Heart will hold the soul against the 心魔 Heart Demon",
        "status_dao_heart_future": "↳ karma weighed by your intent, the choices beyond good/evil, and the 心魔劫 Heart-Demon Judgment awaken in the new world — no effect yet",
        **TIERS["en"],
        **TENDENCY["en"],
    },
    "es": {
        "status_dao_heart_title": "❤️‍🔥 Corazón Dao 道心",
        "status_dao_heart_firmeza": "{emoji} {tier} — {lore}",
        "status_dao_heart_tendency": "↳ tu Voluntad sigue el {tendency}",
        "status_dao_heart_tendency_forming": "↳ tu Voluntad aún se forma — tu karma se inclina hacia el {tendency}",
        "status_dao_heart_demon": "↳ el Corazón Dao sostiene el alma contra el 心魔 Demonio Interior — si tu karma diverge del Camino, ya te avisa",
        "status_dao_heart_demon_near": "↳ ⚠️ tu karma se acerca al límite donde el 心魔 Demonio Interior se agita — es el Corazón Dao el que sostiene el alma",
        "status_dao_heart_demon_rogue": "↳ el Camino Errante no conoce divergencia — tu firmeza es tu propia independencia",
        "status_dao_heart_demon_forming": "↳ en cuanto tu Voluntad cristalice, el Corazón Dao sostendrá el alma contra el 心魔 Demonio Interior",
        "status_dao_heart_future": "↳ el karma pesado por tu intención, las decisiones más allá de bien/mal y el Juicio del 心魔劫 despiertan en el nuevo mundo — aún sin efecto",
        **TIERS["es"],
        **TENDENCY["es"],
    },
}

MINIAPP = {
    "pt": {
        "dao_heart_title": "Coração Dao 道心",
        "dao_heart_tendency": "A sua Vontade segue o {tendency}",
        "dao_heart_tendency_forming": "A sua Vontade ainda se forma — o karma se inclina para o {tendency}",
        "dao_heart_demon": "O Coração Dao segura a alma contra o 心魔 Demônio Interior — se o seu karma divergir do Caminho, ele já o avisa.",
        "dao_heart_demon_near": "⚠️ O seu karma se aproxima do limite onde o 心魔 Demônio Interior se agita — é o Coração Dao que segura a alma.",
        "dao_heart_demon_rogue": "O Caminho Errante não conhece divergência — a sua firmeza é a sua própria independência.",
        "dao_heart_demon_forming": "Assim que a sua Vontade cristalizar, o Coração Dao segurará a alma contra o 心魔 Demônio Interior.",
        "dao_heart_future": "O karma pesado pela sua intenção, as escolhas além de bom/mau e o Julgamento do 心魔劫 despertam no novo mundo — ainda sem efeito.",
        **TIERS["pt"],
        **TENDENCY["pt"],
    },
    "en": {
        "dao_heart_title": "Dao Heart 道心",
        "dao_heart_tendency": "Your Will follows the {tendency}",
        "dao_heart_tendency_forming": "Your Will is still forming — your karma leans toward the {tendency}",
        "dao_heart_demon": "The Dao Heart holds the soul against the 心魔 Heart Demon — should your karma diverge from the Path, it already warns you.",
        "dao_heart_demon_near": "⚠️ Your karma nears the edge where the 心魔 Heart Demon stirs — it is the Dao Heart that holds the soul.",
        "dao_heart_demon_rogue": "The Rogue Path knows no divergence — your firmness is your own independence.",
        "dao_heart_demon_forming": "Once your Will crystallizes, the Dao Heart will hold the soul against the 心魔 Heart Demon.",
        "dao_heart_future": "Karma weighed by your intent, the choices beyond good/evil, and the 心魔劫 Heart-Demon Judgment awaken in the new world — no effect yet.",
        **TIERS["en"],
        **TENDENCY["en"],
    },
    "es": {
        "dao_heart_title": "Corazón Dao 道心",
        "dao_heart_tendency": "Tu Voluntad sigue el {tendency}",
        "dao_heart_tendency_forming": "Tu Voluntad aún se forma — tu karma se inclina hacia el {tendency}",
        "dao_heart_demon": "El Corazón Dao sostiene el alma contra el 心魔 Demonio Interior — si tu karma diverge del Camino, ya te avisa.",
        "dao_heart_demon_near": "⚠️ Tu karma se acerca al límite donde el 心魔 Demonio Interior se agita — es el Corazón Dao el que sostiene el alma.",
        "dao_heart_demon_rogue": "El Camino Errante no conoce divergencia — tu firmeza es tu propia independencia.",
        "dao_heart_demon_forming": "En cuanto tu Voluntad cristalice, el Corazón Dao sostendrá el alma contra el 心魔 Demonio Interior.",
        "dao_heart_future": "El karma pesado por tu intención, las decisiones más allá de bien/mal y el Juicio del 心魔劫 despiertan en el nuevo mundo — aún sin efecto.",
        **TIERS["es"],
        **TENDENCY["es"],
    },
}


def _apply(path, additions):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    before = len(data)
    added = changed = removed = 0
    for k in OBSOLETE:
        if data.pop(k, None) is not None:
            removed += 1
    for k, v in additions.items():
        if k not in data:
            added += 1
        elif data[k] != v:
            changed += 1
        data[k] = v  # overwrite — keys are uniquely namespaced to this wave
    if removed:
        print(f"  (dropped {removed} obsolete key(s) in {os.path.basename(path)})")
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
