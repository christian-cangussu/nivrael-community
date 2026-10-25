"""Track A item 4 — Karma Mecânico ("o mundo lê o teu karma") i18n.

Re-runnable: OVERWRITES this wave's own (uniquely-namespaced) keys with the
current values, then re-dumps each locale indent=4 + ensure_ascii=False +
trailing newline. All keys below are namespaced (npc_react_*, karma_chat_*,
karma_world_*, karma_band_blurb_*, karma_dist_*, karma_dir_*, karma_reacts_*)
and were verified not to collide with any pre-existing key, so overwriting only
ever touches this wave's strings.
  * CHAT    (locales/*.json)      — the per-band NPC reaction lines (SERVER-
    resolved via core.i18n into the mini-app NpcCultivatorModal, so PLAIN prose,
    no Telegram markdown) + the /conf -> karma sub-menu parity lines.
  * MINIAPP (miniapp/i18n/*.json) — the KarmaModal "O que o mundo vê" card.
pt = PT-BR (você/seu). No new KARMA_EVENTS labels needed (tribulation_survive/
_fail, rogue_kill_demonic already have karma_event_* keys).

Crystallization disclosure (item-4 review fix): the Path crystallizes AT Core
Formation (R3) and reads karma at that moment — the neutral band locks as ROGUE,
not righteous/demonic. The crystallize lines therefore name the R3 trigger + the
TRUE projected outcome (via derive_path_from_karma), never a karma "distance".
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHAT = {
    "pt": {
        "npc_react_ally": "Reconhece em você um espírito sombrio irmão — em vez de cruzar lâminas, propõe um treino.",
        "npc_react_hostile": "Sua aura reta o repugna; ele cerra os punhos com desprezo.",
        "npc_react_feared": "Ele recua um passo diante da sua aura demoníaca, a mão na espada.",
        "npc_react_revered": "Saúda você com respeito — reconhece um cultivador de coração puro.",
        "npc_react_wary": "Mede você com cautela, sem saber se é aliado ou ameaça.",
        "npc_react_neutral": "Cumprimenta você com cortesia indiferente.",
        "karma_chat_progress_crystallize_righteous": "Ao atingir o Núcleo (R3), seu Caminho cristaliza como Justo — com seu karma atual.",
        "karma_chat_progress_crystallize_demonic": "Ao atingir o Núcleo (R3), seu Caminho cristaliza como Demoníaco — com seu karma atual.",
        "karma_chat_progress_crystallize_rogue": "Ao atingir o Núcleo (R3), seu Caminho cristaliza como Andarilho — nem luz nem trevas, com seu karma atual.",
        "karma_chat_progress_diverge": "Faltam {n} de karma até o limiar do Demônio Interior.",
        "karma_chat_progress_settled": "Seu Caminho já está firmado.",
        "karma_chat_world_reacts": "O mundo sente o seu Dao: cultivadores reagem à sua aura, as seitas pesam o seu karma ao cortejá-lo, e o Céu o julga nas tribulações.",
    },
    "en": {
        "npc_react_ally": "He recognizes a kindred shadow in you — instead of crossing blades, he offers to spar.",
        "npc_react_hostile": "Your righteous aura disgusts him; he clenches his fists in contempt.",
        "npc_react_feared": "He steps back before your demonic aura, hand on his blade.",
        "npc_react_revered": "He greets you with respect — he sees a cultivator of pure heart.",
        "npc_react_wary": "He sizes you up warily, unsure whether you are ally or threat.",
        "npc_react_neutral": "He greets you with indifferent courtesy.",
        "karma_chat_progress_crystallize_righteous": "At Core Formation (R3) your Path crystallizes as Righteous — with your current karma.",
        "karma_chat_progress_crystallize_demonic": "At Core Formation (R3) your Path crystallizes as Demonic — with your current karma.",
        "karma_chat_progress_crystallize_rogue": "At Core Formation (R3) your Path crystallizes as Rogue — neither light nor dark, with your current karma.",
        "karma_chat_progress_diverge": "{n} more karma until the Heart Demon's threshold.",
        "karma_chat_progress_settled": "Your Path is already set.",
        "karma_chat_world_reacts": "The world feels your Dao: cultivators react to your aura, sects weigh your karma when courting you, and the Heavens judge you in tribulations.",
    },
    "es": {
        "npc_react_ally": "Reconoce en ti un espíritu sombrío hermano — en vez de cruzar espadas, te propone entrenar.",
        "npc_react_hostile": "Tu aura recta lo repugna; aprieta los puños con desprecio.",
        "npc_react_feared": "Retrocede un paso ante tu aura demoníaca, la mano en la espada.",
        "npc_react_revered": "Te saluda con respeto — reconoce a un cultivador de corazón puro.",
        "npc_react_wary": "Te mide con cautela, sin saber si eres aliado o amenaza.",
        "npc_react_neutral": "Te saluda con cortesía indiferente.",
        "karma_chat_progress_crystallize_righteous": "Al alcanzar el Núcleo (R3), tu Camino cristaliza como Justo — con tu karma actual.",
        "karma_chat_progress_crystallize_demonic": "Al alcanzar el Núcleo (R3), tu Camino cristaliza como Demoníaco — con tu karma actual.",
        "karma_chat_progress_crystallize_rogue": "Al alcanzar el Núcleo (R3), tu Camino cristaliza como Errante — ni luz ni oscuridad, con tu karma actual.",
        "karma_chat_progress_diverge": "Faltan {n} de karma hasta el umbral del Demonio Interior.",
        "karma_chat_progress_settled": "Tu Camino ya está firme.",
        "karma_chat_world_reacts": "El mundo siente tu Dao: los cultivadores reaccionan a tu aura, las sectas pesan tu karma al cortejarte, y el Cielo te juzga en las tribulaciones.",
    },
}

MINIAPP = {
    "pt": {
        "karma_world_sees_title": "O que o mundo vê",
        "karma_band_blurb_demonic": "O mundo treme: você é temido como um demônio.",
        "karma_band_blurb_tainted": "Sombras seguem seus passos — o mundo desconfia de você.",
        "karma_band_blurb_neutral": "Seu Dao ainda não se inclinou para luz nem trevas.",
        "karma_band_blurb_pure": "Cultivadores reconhecem em você um coração reto.",
        "karma_band_blurb_saint": "Sua virtude ressoa: o mundo o reverencia como um santo.",
        "karma_dist_crystallize": "Ao atingir o Núcleo (R3), seu Caminho cristaliza como {dir}.",
        "karma_dist_diverge": "A {n} de karma do limiar do Demônio Interior.",
        "karma_dist_settled": "Seu Caminho está firmado — sem desvio à vista.",
        "karma_dir_righteous": "Justo",
        "karma_dir_demonic": "Demoníaco",
        "karma_dir_rogue": "Andarilho",
        "karma_reacts_title": "Quem reage ao seu karma",
        "karma_reacts_npc": "Cultivadores reagem à sua aura ao encontrá-lo.",
        "karma_reacts_sect": "As seitas pesam o seu karma ao decidir cortejá-lo.",
        "karma_reacts_bounty": "Com karma sombrio (≤ −100), sua cabeça pode ir a prêmio.",
        "karma_reacts_tribulation": "O Céu o julga com tribulações mais severas (×{mod}).",
    },
    "en": {
        "karma_world_sees_title": "What the world sees",
        "karma_band_blurb_demonic": "The world trembles: you are feared as a demon.",
        "karma_band_blurb_tainted": "Shadows trail your steps — the world distrusts you.",
        "karma_band_blurb_neutral": "Your Dao has not yet leaned toward light or dark.",
        "karma_band_blurb_pure": "Cultivators recognize an upright heart in you.",
        "karma_band_blurb_saint": "Your virtue resounds: the world reveres you as a saint.",
        "karma_dist_crystallize": "At Core Formation (R3) your Path crystallizes as {dir}.",
        "karma_dist_diverge": "{n} karma from the Heart Demon's threshold.",
        "karma_dist_settled": "Your Path is set — no divergence in sight.",
        "karma_dir_righteous": "Righteous",
        "karma_dir_demonic": "Demonic",
        "karma_dir_rogue": "Rogue",
        "karma_reacts_title": "What reacts to your karma",
        "karma_reacts_npc": "Cultivators react to your aura when they meet you.",
        "karma_reacts_sect": "Sects weigh your karma when deciding to court you.",
        "karma_reacts_bounty": "With dark karma (≤ −100), your head can be put up for a bounty.",
        "karma_reacts_tribulation": "The Heavens judge you with harsher tribulations (×{mod}).",
    },
    "es": {
        "karma_world_sees_title": "Lo que el mundo ve",
        "karma_band_blurb_demonic": "El mundo tiembla: te temen como a un demonio.",
        "karma_band_blurb_tainted": "Las sombras siguen tus pasos — el mundo desconfía de ti.",
        "karma_band_blurb_neutral": "Tu Dao aún no se ha inclinado hacia la luz ni la oscuridad.",
        "karma_band_blurb_pure": "Los cultivadores reconocen en ti un corazón recto.",
        "karma_band_blurb_saint": "Tu virtud resuena: el mundo te venera como a un santo.",
        "karma_dist_crystallize": "Al alcanzar el Núcleo (R3), tu Camino cristaliza como {dir}.",
        "karma_dist_diverge": "A {n} de karma del umbral del Demonio Interior.",
        "karma_dist_settled": "Tu Camino está firme — sin desvío a la vista.",
        "karma_dir_righteous": "Justo",
        "karma_dir_demonic": "Demoníaco",
        "karma_dir_rogue": "Errante",
        "karma_reacts_title": "Qué reacciona a tu karma",
        "karma_reacts_npc": "Los cultivadores reaccionan a tu aura al encontrarte.",
        "karma_reacts_sect": "Las sectas pesan tu karma al decidir cortejarte.",
        "karma_reacts_bounty": "Con karma sombrío (≤ −100), tu cabeza puede ponerse a precio.",
        "karma_reacts_tribulation": "El Cielo te juzga con tribulaciones más severas (×{mod}).",
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
