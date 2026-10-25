"""v16.4 — Sect-Guild Split i18n injector.

Idempotent upsert of the new keys into the chat locales (locales/{pt,en,es}.json)
and the mini-app bundle (miniapp/i18n/{pt,en,es}.json), preserving 3-locale
parity. Re-runnable (overwrites the keys it owns; never deletes others).

Names / philosophies / bonus labels of the 9 houses are NOT injected here —
they reuse the existing v16.1 `lineage_*` chat keys (server-resolved into the
payloads), so this only covers UI chrome, recruiter copy, ranks, and errors.

Run:  python scripts/inject_v164_i18n.py
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (pt, en, es) tuples. PT is the default fallback (Lei: fallback é Português).

# Keys needed in BOTH chat + mini-app (shared chrome / ranks / notif / errors).
SHARED = {
    "wsect_split_banner": (
        "As Seitas Anciãs (🏯) são as 9 Casas eternas do mundo — instituições NPC que te escolhem. As guildas (as antigas \"seitas\" de jogadores) continuam tuas. São coisas distintas.",
        "The Ancient Sects (🏯) are the world's 9 eternal Houses — NPC institutions that choose you. Guilds (the old player \"sects\") remain yours. They are distinct things.",
        "Las Sectas Ancestrales (🏯) son las 9 Casas eternas del mundo — instituciones NPC que te eligen. Los gremios (las antiguas \"sectas\" de jugadores) siguen siendo tuyos. Son cosas distintas.",
    ),
    "wsect_rank_disciple": ("Discípulo", "Disciple", "Discípulo"),
    "wsect_rank_inner": ("Discípulo Interior", "Inner Disciple", "Discípulo Interior"),
    "wsect_rank_core": ("Discípulo Nuclear", "Core Disciple", "Discípulo Nuclear"),
    "wsect_rank_heir": ("Herdeiro", "Heir", "Heredero"),
    "wsect_recruiter_notif_title": (
        "🏯 Uma Casa reparou em ti",
        "🏯 A House has taken notice of you",
        "🏯 Una Casa se ha fijado en ti",
    ),
    "wsect_recruiter_notif_body": (
        "Um Ancião espera-te numa encruzilhada. Abre o teu Perfil 🏯 para responder.",
        "An Elder awaits you at a crossroads. Open your Profile 🏯 to answer.",
        "Un Anciano te espera en una encrucijada. Abre tu Perfil 🏯 para responder.",
    ),
    "err_engine": (
        "Algo correu mal. Tenta novamente.",
        "Something went wrong. Try again.",
        "Algo salió mal. Inténtalo de nuevo.",
    ),
    "err_sect_path_mismatch": (
        "O teu caminho não se alinha com esta Casa.",
        "Your path does not align with this House.",
        "Tu camino no se alinea con esta Casa.",
    ),
    "err_sect_already_joined": (
        "Já pertences a uma Seita Anciã.",
        "You already belong to an Ancient Sect.",
        "Ya perteneces a una Secta Ancestral.",
    ),
    "err_recruiter_expired": (
        "O encontro com o Ancião expirou.",
        "The Elder's encounter has expired.",
        "El encuentro con el Anciano expiró.",
    ),
    "err_sect_invalid": ("Casa desconhecida.", "Unknown House.", "Casa desconocida."),
}

# Chat-only keys (rendered by handlers/sect.py, scheduler DM, /status).
CHAT_ONLY = {
    "wsect_recruiter_dm": (
        "{emoji} Um Ancião pára num pinheiro e fita-te.\n\n\"És tu o que procurávamos?\"\n\nA Casa *{sect}* reconhece a tua jornada — afinidade {score}/100. Aceitas o convite?",
        "{emoji} An Elder pauses upon a pine and gazes at you.\n\n\"Are you the one we sought?\"\n\nThe House of *{sect}* recognizes your journey — affinity {score}/100. Do you accept?",
        "{emoji} Un Anciano se detiene sobre un pino y te mira.\n\n\"¿Eres tú al que buscábamos?\"\n\nLa Casa de *{sect}* reconoce tu viaje — afinidad {score}/100. ¿Aceptas?",
    ),
    "wsect_recruiter_accept_btn": ("✅ Aceitar", "✅ Accept", "✅ Aceptar"),
    "wsect_recruiter_decline_btn": ("🚪 Recusar", "🚪 Decline", "🚪 Rechazar"),
    "wsect_menu_title": ("Seita Anciã", "Ancient Sect", "Secta Ancestral"),
    "wsect_menu_member": (
        "Pertences a {emoji} *{sect}* — {rank}.",
        "You belong to {emoji} *{sect}* — {rank}.",
        "Perteneces a {emoji} *{sect}* — {rank}.",
    ),
    "wsect_menu_pending": (
        "🏯 *Um Ancião espera a tua resposta:*",
        "🏯 *An Elder awaits your answer:*",
        "🏯 *Un Anciano espera tu respuesta:*",
    ),
    "wsect_menu_none": (
        "Ainda nenhuma das 9 Casas te chamou.",
        "None of the 9 Houses has called you yet.",
        "Ninguna de las 9 Casas te ha llamado aún.",
    ),
    "wsect_menu_explain": (
        "As Seitas Anciãs escolhem cultivadores cujo caminho, continente e karma se alinham com a Casa. Caminha o mundo — e um dia um Ancião há-de parar à tua frente.",
        "The Ancient Sects choose cultivators whose path, continent and karma align with the House. Walk the world — and one day an Elder will stop before you.",
        "Las Sectas Ancestrales eligen cultivadores cuyo camino, continente y karma se alinean con la Casa. Camina el mundo — y un día un Anciano se detendrá ante ti.",
    ),
    "wsect_menu_affinity_teaser": (
        "A tua afinidade actual (limiar {threshold}):",
        "Your current affinity (threshold {threshold}):",
        "Tu afinidad actual (umbral {threshold}):",
    ),
    "wsect_btn_accept": ("✅ Aceitar {sect}", "✅ Join {sect}", "✅ Unirse a {sect}"),
    "wsect_btn_decline": ("🚪 Recusar", "🚪 Decline", "🚪 Rechazar"),
    "wsect_accept_ok": (
        "{emoji} Entraste em *{sect}* como Discípulo. O Ancião acena: o teu nome ecoará nestas montanhas.",
        "{emoji} You entered *{sect}* as a Disciple. The Elder nods: your name will echo in these mountains.",
        "{emoji} Entraste en *{sect}* como Discípulo. El Anciano asiente: tu nombre resonará en estas montañas.",
    ),
    "wsect_declined": (
        "Recusaste o convite de {emoji} {sect}. O Ancião desaparece entre as nuvens — talvez outra Casa te chame.",
        "You declined {emoji} {sect}'s invitation. The Elder vanishes into the clouds — perhaps another House will call.",
        "Rechazaste la invitación de {emoji} {sect}. El Anciano desaparece entre las nubes — quizá otra Casa te llame.",
    ),
    "wsect_recruiter_expired": (
        "Este encontro já não está disponível.",
        "This encounter is no longer available.",
        "Este encuentro ya no está disponible.",
    ),
    "wsect_status_label": (
        "🏯 Seita: {emoji} {sect} ({rank})",
        "🏯 Sect: {emoji} {sect} ({rank})",
        "🏯 Secta: {emoji} {sect} ({rank})",
    ),
}

# Mini-app-only keys (rendered by WorldSectDirectoryModal / WorldSectJoinModal
# / repurposed lineage note).
MINIAPP_ONLY = {
    "wsect_dir_title": ("Seitas Anciãs", "Ancient Sects", "Sectas Ancestrales"),
    "wsect_dir_houses_title": ("As 9 Casas Eternas", "The 9 Eternal Houses", "Las 9 Casas Eternas"),
    "wsect_tier_demonic": ("Demoníaca", "Demonic", "Demoníaca"),
    "wsect_tier_righteous": ("Justa", "Righteous", "Justa"),
    "wsect_path_locked": ("Caminho incompatível", "Path incompatible", "Camino incompatible"),
    "wsect_affinity_label": (
        "Afinidade · limiar {threshold}",
        "Affinity · threshold {threshold}",
        "Afinidad · umbral {threshold}",
    ),
    "wsect_recruiter_pending_cta": (
        "🏯 Um Ancião espera — Aceitar",
        "🏯 An Elder awaits — Accept",
        "🏯 Un Anciano espera — Aceptar",
    ),
    "wsect_recruiter_awaiting": (
        "Afinidade suficiente — um Ancião virá ter contigo.",
        "Affinity met — an Elder will come for you.",
        "Afinidad suficiente — un Anciano vendrá a ti.",
    ),
    "wsect_join_trial_intro": (
        "Ao aceitar, és recebido como Discípulo. A Prova das Nove Casas — o teu juramento completo — desabrochará numa ascensão futura.",
        "On accepting, you are taken in as a Disciple. The Trial of the Nine Houses — your full oath — will unfold in a future ascension.",
        "Al aceptar, eres recibido como Discípulo. La Prueba de las Nueve Casas — tu juramento completo — florecerá en una ascensión futura.",
    ),
    "wsect_join_confirm_btn": ("Aceitar e entrar", "Accept and enter", "Aceptar y entrar"),
    "wsect_join_decline_btn": ("Agora não", "Not now", "Ahora no"),
    "wsect_join_success": ("Entraste em {sect}!", "You joined {sect}!", "¡Te uniste a {sect}!"),
    "wsect_lineage_migrated_note": (
        "As 9 Seitas Anciãs já são Casas vivas. Não se escolhe lineage — caminha o mundo e uma Casa há-de escolher-te. Vê a tua afinidade no Perfil 🏯.",
        "The 9 Ancient Sects are now living Houses. There is no lineage to pick — walk the world and a House will choose you. See your affinity in your Profile 🏯.",
        "Las 9 Sectas Ancestrales ya son Casas vivas. No se elige linaje — camina el mundo y una Casa te elegirá. Mira tu afinidad en tu Perfil 🏯.",
    ),
}

LOCALES = ["pt", "en", "es"]


def _merge(path: str, keys: dict) -> int:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key, (pt, en, es) in keys.items():
        val = {"pt": pt, "en": en, "es": es}
        # path encodes the locale as the last folder/file segment
        lang = os.path.splitext(os.path.basename(path))[0]
        data[key] = val[lang]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    return len(keys)


def main():
    for lang in LOCALES:
        chat_path = os.path.join(ROOT, "locales", f"{lang}.json")
        ma_path = os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json")
        n_chat = _merge(chat_path, {**SHARED, **CHAT_ONLY})
        n_ma = _merge(ma_path, {**SHARED, **MINIAPP_ONLY})
        print(f"  [{lang}] chat +{n_chat} keys · miniapp +{n_ma} keys")
    print("INJECTION COMPLETE (v16.4)")


if __name__ == "__main__":
    main()
