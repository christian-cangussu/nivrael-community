"""v16.4c — inject Sect Library + Ranks + Quests + Hall i18n keys (chat + mini-app, ×3).

Idempotent: only adds missing keys, preserves the canonical format
(indent=4, sort_keys, ensure_ascii=False, trailing newline). pt = PT-BR
(você/seu, ativo/artefato; {placeholders} kept ASCII). Re-runnable.

Run once:  python scripts/inject_v164c_i18n.py
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Chat (locales/) ────────────────────────────────────────────────────────
CHAT = {
    "pt": {
        "wsect_rank_elder": "Ancião",
        "wsect_hall_contrib": "📊 Contribuição: {have}/{need} {bar} → {next}",
        "wsect_hall_realm_gate": "🔒 Requer Reino {realm}",
        "wsect_hall_maxed": "👑 Rank máximo — você é o Herdeiro da Casa ({contrib} de contribuição).",
        "wsect_btn_library": "📜 Biblioteca",
        "wsect_btn_quests": "⚔️ Missões da Seita",
        "wsect_btn_tribute": "💰 Tributo",
        "wsect_promoted_title": "🏯 Promoção na Seita",
        "wsect_promoted_body": "A Casa reconhece o seu progresso. Abra o Salão da Seita para ver o seu novo rank.",
        "wsect_lib_title": "Biblioteca de {sect}",
        "wsect_lib_intro": "As artes que esta Casa guarda. Suba de rank para desbloquear as mais profundas.",
        "wsect_lib_empty": "A biblioteca ainda está vazia.",
        "wsect_lib_learned": "✅ Aprendida",
        "wsect_lib_unlockable": "🔓 Disponível",
        "wsect_lib_locked": "🔒 {rank}",
        "wsect_lib_learn_btn": "Aprender {name}",
        "wsect_learn_ok": "✨ Você aprendeu {name}!",
        "wsect_learn_rank_low": "🔒 Seu rank ainda é baixo para esta arte.",
        "wsect_learn_already": "Você já domina esta arte.",
        "wsect_learn_realm_low": "🔒 Requer Reino {realm}.",
        "wsect_learn_fail": "Não foi possível aprender esta arte.",
        "wsect_quests_title": "Missões da Seita",
        "wsect_quests_empty": "Nenhuma missão da Casa disponível agora.",
        "wsect_quests_claim_btn": "🎁 Reivindicar: {name}",
        "wsect_quest_status_claimed": "{emoji} {name} — ✓ concluída",
        "wsect_quest_status_done": "{emoji} {name} — ✨ pronta para reivindicar",
        "wsect_quest_status_progress": "{emoji} {name} — {progress}/{target}",
        "wsect_quest_claimed_toast": "🎁 Recompensa da Seita recebida!",
        "wsect_tribute_title": "Tributo à Seita",
        "wsect_tribute_intro": "Doe Spirit Stones à Casa para ganhar contribuição ({rate} pedras = 1 ponto).",
        "wsect_tribute_balance": "Você tem {stones} Spirit Stones.",
        "wsect_tribute_btn": "Doar {stones} (+{points})",
        "wsect_tribute_too_small": "Pedras insuficientes para um tributo.",
        "wsect_tribute_ok": "🙏 Você doou {stones} pedras — +{points} de contribuição.",
        "wsect_tribute_promoted": "🏯 A Casa te promove a {rank}!",
        "qc_602_mercy": "Perdoe o discípulo e ensine-o",
        "qc_602_mercy_result": "Você intercede pelo jovem. O Ancião assente, lento. A misericórdia também é um Dao.",
        "qc_602_honor": "Aplique a lei da Seita, sem ódio",
        "qc_602_honor_result": "Punição justa, medida. A Casa vê em você um futuro Ancião.",
        "qc_602_cruelty": "Faça dele um exemplo",
        "qc_602_cruelty_result": "Seu castigo ecoa pelos corredores. A Casa teme você — e a sua alma esfria um pouco.",
    },
    "en": {
        "wsect_rank_elder": "Elder",
        "wsect_hall_contrib": "📊 Contribution: {have}/{need} {bar} → {next}",
        "wsect_hall_realm_gate": "🔒 Requires Realm {realm}",
        "wsect_hall_maxed": "👑 Highest rank — you are the House's Heir ({contrib} contribution).",
        "wsect_btn_library": "📜 Library",
        "wsect_btn_quests": "⚔️ Sect Quests",
        "wsect_btn_tribute": "💰 Tribute",
        "wsect_promoted_title": "🏯 Sect Promotion",
        "wsect_promoted_body": "The House recognizes your progress. Open the Sect Hall to see your new rank.",
        "wsect_lib_title": "Library of {sect}",
        "wsect_lib_intro": "The arts this House guards. Climb in rank to unlock the deeper ones.",
        "wsect_lib_empty": "The library is still empty.",
        "wsect_lib_learned": "✅ Learned",
        "wsect_lib_unlockable": "🔓 Available",
        "wsect_lib_locked": "🔒 {rank}",
        "wsect_lib_learn_btn": "Learn {name}",
        "wsect_learn_ok": "✨ You learned {name}!",
        "wsect_learn_rank_low": "🔒 Your rank is too low for this art.",
        "wsect_learn_already": "You already master this art.",
        "wsect_learn_realm_low": "🔒 Requires Realm {realm}.",
        "wsect_learn_fail": "Could not learn this art.",
        "wsect_quests_title": "Sect Quests",
        "wsect_quests_empty": "No House quests available right now.",
        "wsect_quests_claim_btn": "🎁 Claim: {name}",
        "wsect_quest_status_claimed": "{emoji} {name} — ✓ done",
        "wsect_quest_status_done": "{emoji} {name} — ✨ ready to claim",
        "wsect_quest_status_progress": "{emoji} {name} — {progress}/{target}",
        "wsect_quest_claimed_toast": "🎁 Sect reward received!",
        "wsect_tribute_title": "Tribute to the Sect",
        "wsect_tribute_intro": "Donate Spirit Stones to the House for contribution ({rate} stones = 1 point).",
        "wsect_tribute_balance": "You have {stones} Spirit Stones.",
        "wsect_tribute_btn": "Donate {stones} (+{points})",
        "wsect_tribute_too_small": "Not enough stones for a tribute.",
        "wsect_tribute_ok": "🙏 You donated {stones} stones — +{points} contribution.",
        "wsect_tribute_promoted": "🏯 The House promotes you to {rank}!",
        "qc_602_mercy": "Forgive the disciple and teach him",
        "qc_602_mercy_result": "You plead for the youth. The Elder nods, slowly. Mercy, too, is a Dao.",
        "qc_602_honor": "Apply the Sect's law, without hatred",
        "qc_602_honor_result": "Just punishment, measured. The House sees a future Elder in you.",
        "qc_602_cruelty": "Make an example of him",
        "qc_602_cruelty_result": "Your punishment echoes down the halls. The House fears you — and your soul cools a little.",
    },
    "es": {
        "wsect_rank_elder": "Anciano",
        "wsect_hall_contrib": "📊 Contribución: {have}/{need} {bar} → {next}",
        "wsect_hall_realm_gate": "🔒 Requiere Reino {realm}",
        "wsect_hall_maxed": "👑 Rango máximo — eres el Heredero de la Casa ({contrib} de contribución).",
        "wsect_btn_library": "📜 Biblioteca",
        "wsect_btn_quests": "⚔️ Misiones de la Secta",
        "wsect_btn_tribute": "💰 Tributo",
        "wsect_promoted_title": "🏯 Ascenso en la Secta",
        "wsect_promoted_body": "La Casa reconoce tu progreso. Abre el Salón de la Secta para ver tu nuevo rango.",
        "wsect_lib_title": "Biblioteca de {sect}",
        "wsect_lib_intro": "Las artes que esta Casa guarda. Asciende de rango para desbloquear las más profundas.",
        "wsect_lib_empty": "La biblioteca aún está vacía.",
        "wsect_lib_learned": "✅ Aprendida",
        "wsect_lib_unlockable": "🔓 Disponible",
        "wsect_lib_locked": "🔒 {rank}",
        "wsect_lib_learn_btn": "Aprender {name}",
        "wsect_learn_ok": "✨ ¡Aprendiste {name}!",
        "wsect_learn_rank_low": "🔒 Tu rango aún es bajo para este arte.",
        "wsect_learn_already": "Ya dominas este arte.",
        "wsect_learn_realm_low": "🔒 Requiere Reino {realm}.",
        "wsect_learn_fail": "No se pudo aprender este arte.",
        "wsect_quests_title": "Misiones de la Secta",
        "wsect_quests_empty": "No hay misiones de la Casa disponibles ahora.",
        "wsect_quests_claim_btn": "🎁 Reclamar: {name}",
        "wsect_quest_status_claimed": "{emoji} {name} — ✓ completada",
        "wsect_quest_status_done": "{emoji} {name} — ✨ lista para reclamar",
        "wsect_quest_status_progress": "{emoji} {name} — {progress}/{target}",
        "wsect_quest_claimed_toast": "🎁 ¡Recompensa de la Secta recibida!",
        "wsect_tribute_title": "Tributo a la Secta",
        "wsect_tribute_intro": "Dona Spirit Stones a la Casa para ganar contribución ({rate} piedras = 1 punto).",
        "wsect_tribute_balance": "Tienes {stones} Spirit Stones.",
        "wsect_tribute_btn": "Donar {stones} (+{points})",
        "wsect_tribute_too_small": "Piedras insuficientes para un tributo.",
        "wsect_tribute_ok": "🙏 Donaste {stones} piedras — +{points} de contribución.",
        "wsect_tribute_promoted": "🏯 ¡La Casa te asciende a {rank}!",
        "qc_602_mercy": "Perdona al discípulo y enséñale",
        "qc_602_mercy_result": "Intercedes por el joven. El Anciano asiente, lento. La misericordia también es un Dao.",
        "qc_602_honor": "Aplica la ley de la Secta, sin odio",
        "qc_602_honor_result": "Castigo justo, medido. La Casa ve en ti a un futuro Anciano.",
        "qc_602_cruelty": "Haz de él un ejemplo",
        "qc_602_cruelty_result": "Tu castigo resuena por los pasillos. La Casa te teme — y tu alma se enfría un poco.",
    },
}

# ── Mini-app (miniapp/i18n/) ───────────────────────────────────────────────
MINIAPP = {
    "pt": {
        "wsect_rank_elder": "Ancião",
        "sect_hall_title": "Salão da Seita",
        "sect_hall_not_member": "Você ainda não pertence a uma Casa.",
        "sect_hall_contrib_label": "Contribuição",
        "sect_hall_next": "Próximo: {rank} ({need})",
        "sect_hall_maxed": "Rank máximo — Herdeiro da Casa.",
        "sect_hall_realm_gate": "Requer Reino {realm}",
        "sect_hall_perks_title": "Favor da Casa",
        "sect_hall_perks_note": "O favor pleno da Casa desperta no novo mundo.",
        "sect_hall_library_title": "Biblioteca",
        "sect_hall_learned": "Aprendida",
        "sect_hall_learn_btn": "Aprender",
        "sect_hall_tribute_title": "Tributo",
        "sect_hall_tribute_intro": "Doe pedras por contribuição ({rate} = 1 ponto).",
        "sect_hall_tribute_too_small": "Pedras insuficientes.",
        "sect_hall_quests_title": "Missões da Seita",
        "sect_hall_quests_empty": "Nenhuma missão da Casa agora.",
        "wsect_learn_ok": "✨ Você aprendeu {name}!",
        "wsect_learn_rank_low": "🔒 Rank insuficiente para esta arte.",
        "wsect_learn_already": "Você já domina esta arte.",
        "wsect_learn_realm_low": "🔒 Requer Reino {realm}.",
        "wsect_learn_fail": "Não foi possível aprender.",
        "wsect_tribute_ok": "🙏 +{points} de contribuição ({stones} pedras).",
        "wsect_tribute_promoted": "🏯 Promovido a {rank}!",
        "wsect_tribute_too_small": "Pedras insuficientes.",
        "qc_602_mercy": "Perdoe o discípulo e ensine-o",
        "qc_602_mercy_result": "Você intercede pelo jovem. O Ancião assente, lento. A misericórdia também é um Dao.",
        "qc_602_honor": "Aplique a lei da Seita, sem ódio",
        "qc_602_honor_result": "Punição justa, medida. A Casa vê em você um futuro Ancião.",
        "qc_602_cruelty": "Faça dele um exemplo",
        "qc_602_cruelty_result": "Seu castigo ecoa pelos corredores. A Casa teme você — e a sua alma esfria um pouco.",
    },
    "en": {
        "wsect_rank_elder": "Elder",
        "sect_hall_title": "Sect Hall",
        "sect_hall_not_member": "You do not belong to a House yet.",
        "sect_hall_contrib_label": "Contribution",
        "sect_hall_next": "Next: {rank} ({need})",
        "sect_hall_maxed": "Highest rank — House Heir.",
        "sect_hall_realm_gate": "Requires Realm {realm}",
        "sect_hall_perks_title": "House Favour",
        "sect_hall_perks_note": "The House's full favour awakens in the new world.",
        "sect_hall_library_title": "Library",
        "sect_hall_learned": "Learned",
        "sect_hall_learn_btn": "Learn",
        "sect_hall_tribute_title": "Tribute",
        "sect_hall_tribute_intro": "Donate stones for contribution ({rate} = 1 point).",
        "sect_hall_tribute_too_small": "Not enough stones.",
        "sect_hall_quests_title": "Sect Quests",
        "sect_hall_quests_empty": "No House quests right now.",
        "wsect_learn_ok": "✨ You learned {name}!",
        "wsect_learn_rank_low": "🔒 Rank too low for this art.",
        "wsect_learn_already": "You already master this art.",
        "wsect_learn_realm_low": "🔒 Requires Realm {realm}.",
        "wsect_learn_fail": "Could not learn.",
        "wsect_tribute_ok": "🙏 +{points} contribution ({stones} stones).",
        "wsect_tribute_promoted": "🏯 Promoted to {rank}!",
        "wsect_tribute_too_small": "Not enough stones.",
        "qc_602_mercy": "Forgive the disciple and teach him",
        "qc_602_mercy_result": "You plead for the youth. The Elder nods, slowly. Mercy, too, is a Dao.",
        "qc_602_honor": "Apply the Sect's law, without hatred",
        "qc_602_honor_result": "Just punishment, measured. The House sees a future Elder in you.",
        "qc_602_cruelty": "Make an example of him",
        "qc_602_cruelty_result": "Your punishment echoes down the halls. The House fears you — and your soul cools a little.",
    },
    "es": {
        "wsect_rank_elder": "Anciano",
        "sect_hall_title": "Salón de la Secta",
        "sect_hall_not_member": "Aún no perteneces a una Casa.",
        "sect_hall_contrib_label": "Contribución",
        "sect_hall_next": "Siguiente: {rank} ({need})",
        "sect_hall_maxed": "Rango máximo — Heredero de la Casa.",
        "sect_hall_realm_gate": "Requiere Reino {realm}",
        "sect_hall_perks_title": "Favor de la Casa",
        "sect_hall_perks_note": "El favor pleno de la Casa despierta en el nuevo mundo.",
        "sect_hall_library_title": "Biblioteca",
        "sect_hall_learned": "Aprendida",
        "sect_hall_learn_btn": "Aprender",
        "sect_hall_tribute_title": "Tributo",
        "sect_hall_tribute_intro": "Dona piedras por contribución ({rate} = 1 punto).",
        "sect_hall_tribute_too_small": "Piedras insuficientes.",
        "sect_hall_quests_title": "Misiones de la Secta",
        "sect_hall_quests_empty": "No hay misiones de la Casa ahora.",
        "wsect_learn_ok": "✨ ¡Aprendiste {name}!",
        "wsect_learn_rank_low": "🔒 Rango insuficiente para este arte.",
        "wsect_learn_already": "Ya dominas este arte.",
        "wsect_learn_realm_low": "🔒 Requiere Reino {realm}.",
        "wsect_learn_fail": "No se pudo aprender.",
        "wsect_tribute_ok": "🙏 +{points} de contribución ({stones} piedras).",
        "wsect_tribute_promoted": "🏯 ¡Ascendido a {rank}!",
        "wsect_tribute_too_small": "Piedras insuficientes.",
        "qc_602_mercy": "Perdona al discípulo y enséñale",
        "qc_602_mercy_result": "Intercedes por el joven. El Anciano asiente, lento. La misericordia también es un Dao.",
        "qc_602_honor": "Aplica la ley de la Secta, sin odio",
        "qc_602_honor_result": "Castigo justo, medido. La Casa ve en ti a un futuro Anciano.",
        "qc_602_cruelty": "Haz de él un ejemplo",
        "qc_602_cruelty_result": "Tu castigo resuena por los pasillos. La Casa te teme — y tu alma se enfría un poco.",
    },
}


def _apply(path: str, additions: dict[str, str]) -> tuple[int, int]:
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


def main() -> None:
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
