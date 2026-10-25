"""v16.4b — inject Sect Recruitment trial i18n keys (chat + mini-app, ×3).

Idempotent: only adds missing keys, preserves the canonical format
(indent=4, sort_keys, ensure_ascii=False, trailing newline). pt = PT-BR.

Run once:  python scripts/inject_v164b_i18n.py
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Chat (locales/) ────────────────────────────────────────────────────────
CHAT = {
    "pt": {
        "npc_archetype_elder": "🧙 Ancião",
        "wsect_trial_intro": "{emoji} Um Ancião de *{sect}* ergue-se diante de você.\n\n\"Afinidade {score}/100. Números não bastam — mostre-me seu Dao.\"\n\nEnfrente o Ancião para provar seu valor. Uma derrota não fecha portas: apenas adia.",
        "wsect_trial_face_btn": "⚔️ Enfrentar o Ancião",
        "wsect_trial_win": "{emoji} Após {rounds} trocas, o Ancião baixa a guarda e sorri.\n\n\"A Casa *{sect}* te acolhe como Discípulo. Seu nome ecoará nestas montanhas.\"",
        "wsect_trial_loss": "{emoji} O Ancião de *{sect}* te supera em {rounds} trocas.\n\n\"Seu Dao ainda é verde. Volte quando amadurecer.\"\n\n_Nova tentativa em {hours}h._",
        "wsect_trial_cooldown": "{emoji} O Ancião de *{sect}* ainda medita sobre sua última derrota. Volte em até {hours}h.",
        "wsect_trial_busy": "Você já está em combate. Conclua antes de enfrentar o Ancião.",
    },
    "en": {
        "npc_archetype_elder": "🧙 Elder",
        "wsect_trial_intro": "{emoji} An Elder of *{sect}* rises before you.\n\n\"Affinity {score}/100. Numbers are not enough — show me your Dao.\"\n\nFace the Elder to prove your worth. A defeat closes no doors: it only delays.",
        "wsect_trial_face_btn": "⚔️ Face the Elder",
        "wsect_trial_win": "{emoji} After {rounds} exchanges, the Elder lowers their guard and smiles.\n\n\"The House of *{sect}* receives you as a Disciple. Your name will echo through these mountains.\"",
        "wsect_trial_loss": "{emoji} The Elder of *{sect}* bests you in {rounds} exchanges.\n\n\"Your Dao is still green. Return when it ripens.\"\n\n_Try again in {hours}h._",
        "wsect_trial_cooldown": "{emoji} The Elder of *{sect}* still broods over your last defeat. Return within {hours}h.",
        "wsect_trial_busy": "You are already in combat. Finish it before facing the Elder.",
    },
    "es": {
        "npc_archetype_elder": "🧙 Anciano",
        "wsect_trial_intro": "{emoji} Un Anciano de *{sect}* se alza ante ti.\n\n\"Afinidad {score}/100. Los números no bastan — muéstrame tu Dao.\"\n\nEnfrenta al Anciano para probar tu valía. Una derrota no cierra puertas: solo las retrasa.",
        "wsect_trial_face_btn": "⚔️ Enfrentar al Anciano",
        "wsect_trial_win": "{emoji} Tras {rounds} intercambios, el Anciano baja la guardia y sonríe.\n\n\"La Casa *{sect}* te acoge como Discípulo. Tu nombre resonará en estas montañas.\"",
        "wsect_trial_loss": "{emoji} El Anciano de *{sect}* te supera en {rounds} intercambios.\n\n\"Tu Dao aún es verde. Vuelve cuando madure.\"\n\n_Nuevo intento en {hours}h._",
        "wsect_trial_cooldown": "{emoji} El Anciano de *{sect}* aún medita sobre tu última derrota. Vuelve en {hours}h.",
        "wsect_trial_busy": "Ya estás en combate. Termínalo antes de enfrentar al Anciano.",
    },
}

# ── Mini-app (miniapp/i18n/) ───────────────────────────────────────────────
MINIAPP = {
    "pt": {
        "wsect_bd_title": "Por que esta Casa te observa",
        "wsect_bd_path": "Caminho",
        "wsect_bd_continent": "Continente",
        "wsect_bd_karma": "Karma",
        "wsect_bd_lineage": "Linhagem",
        "wsect_bd_actions": "Seus atos",
        "wsect_bd_total": "Afinidade",
        "wsect_trial_intro_miniapp": "Aceitar não basta: prove seu Dao contra o Ancião da Casa. Vença, e você entra como Discípulo. Perca, e o Ancião pede que volte mais tarde — nunca um beco sem saída.",
        "wsect_trial_face_btn": "⚔️ Enfrentar o Ancião",
        "wsect_trial_busy": "Você já está em um duelo. Conclua-o primeiro.",
        "wsect_trial_result_win_title": "A Casa te acolhe",
        "wsect_trial_result_win_body": "Você provou seu Dao. *{sect}* te recebe como Discípulo.",
        "wsect_trial_result_loss_title": "O Ancião te supera",
        "wsect_trial_result_loss_body": "{sect} ainda não te abre as portas. Recupere as forças e retorne em {hours}h.",
        "wsect_trial_result_close_btn": "Entendido",
        "err_hp_depleted": "Seus PV estão esgotados — recupere-se antes do duelo.",
        "err_recruiter_expired": "Este encontro já não está disponível.",
        "err_internal_error": "Algo deu errado. Tente novamente.",
    },
    "en": {
        "wsect_bd_title": "Why this House watches you",
        "wsect_bd_path": "Path",
        "wsect_bd_continent": "Continent",
        "wsect_bd_karma": "Karma",
        "wsect_bd_lineage": "Lineage",
        "wsect_bd_actions": "Your deeds",
        "wsect_bd_total": "Affinity",
        "wsect_trial_intro_miniapp": "Accepting is not enough: prove your Dao against the House Elder. Win, and you enter as a Disciple. Lose, and the Elder asks you to return later — never a dead-end.",
        "wsect_trial_face_btn": "⚔️ Face the Elder",
        "wsect_trial_busy": "You're already in a duel. Finish it first.",
        "wsect_trial_result_win_title": "The House receives you",
        "wsect_trial_result_win_body": "You proved your Dao. *{sect}* welcomes you as a Disciple.",
        "wsect_trial_result_loss_title": "The Elder bests you",
        "wsect_trial_result_loss_body": "{sect} does not open its gates yet. Recover your strength and return in {hours}h.",
        "wsect_trial_result_close_btn": "Understood",
        "err_hp_depleted": "Your HP is depleted — recover before the duel.",
        "err_recruiter_expired": "This encounter is no longer available.",
        "err_internal_error": "Something went wrong. Try again.",
    },
    "es": {
        "wsect_bd_title": "Por qué esta Casa te observa",
        "wsect_bd_path": "Camino",
        "wsect_bd_continent": "Continente",
        "wsect_bd_karma": "Karma",
        "wsect_bd_lineage": "Linaje",
        "wsect_bd_actions": "Tus actos",
        "wsect_bd_total": "Afinidad",
        "wsect_trial_intro_miniapp": "Aceptar no basta: prueba tu Dao contra el Anciano de la Casa. Vence, y entrarás como Discípulo. Pierde, y el Anciano te pedirá que vuelvas más tarde — nunca un callejón sin salida.",
        "wsect_trial_face_btn": "⚔️ Enfrentar al Anciano",
        "wsect_trial_busy": "Ya estás en un duelo. Termínalo primero.",
        "wsect_trial_result_win_title": "La Casa te acoge",
        "wsect_trial_result_win_body": "Probaste tu Dao. *{sect}* te recibe como Discípulo.",
        "wsect_trial_result_loss_title": "El Anciano te supera",
        "wsect_trial_result_loss_body": "{sect} aún no te abre sus puertas. Recupera fuerzas y vuelve en {hours}h.",
        "wsect_trial_result_close_btn": "Entendido",
        "err_hp_depleted": "Tus PV están agotados — recupérate antes del duelo.",
        "err_recruiter_expired": "Este encuentro ya no está disponible.",
        "err_internal_error": "Algo salió mal. Inténtalo de nuevo.",
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
        print(f"chat   {lang}: {before} -> {before + added} (+{added})")
    for lang, adds in MINIAPP.items():
        p = os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json")
        before, added = _apply(p, adds)
        print(f"miniapp {lang}: {before} -> {before + added} (+{added})")


if __name__ == "__main__":
    main()
