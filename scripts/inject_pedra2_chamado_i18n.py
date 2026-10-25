"""Track A, Pedra 2 — "O Chamado da Seita" 宗门征召 i18n injection.

Idempotent: adds ONLY missing keys (preserving existing insertion order, new
keys appended at the end → clean diff), then re-dumps each locale indent=4 +
ensure_ascii=False + trailing newline.

Surfaces:
  * CHAT    (locales/{pt,en,es}.json)        — the Chamado DM (soul tones) +
    breakdown disclosure + the named-shifu line + the Guild disambiguation header.
  * MINIAPP (miniapp/i18n/{pt,en,es}.json)   — the Hall master line + live
    strength label + blessing-awaits note + the ProfileModal master line.

pt = PT-BR (você/seu). Command literals (/seita_ancia) stay un-accented.
Chat tone templates are PLAIN text (no markdown) — they are ALSO server-resolved
into the mini-app (project_sect_call), where markdown would render literally.
Placeholders {…} stay ASCII and appear at most once per string.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHAT = {
    "pt": {
        # ── O Chamado — 3 soul-derived tone templates (plain text; dual-surface)
        "wsect_call_urgent": "{emoji} Um Ancião de {sect} corta seu caminho, o olhar de aço.\n\n\"O mundo não espera os hesitantes. Nossa Casa se ergue — e vê em você o aço que procura. Afinidade {score}/100. Vai ficar aí parado, ou vem conosco tomar o que é nosso?\"",
        "wsect_call_honor": "{emoji} Um Ancião de {sect} inclina a cabeça, sereno.\n\n\"Observamos sua jornada de longe, e ela honra os céus. Afinidade {score}/100. Se aceitar, será recebido com cerimônia — e o Dao de nossa Casa será seu.\"",
        "wsect_call_greed": "{emoji} Um Ancião de {sect} sorri, e o ar cheira a tesouro.\n\n\"Poucos têm o que vejo em você. Afinidade {score}/100. Junte-se a nós e nenhuma relíquia, nenhum segredo dos abismos ficará fora de seu alcance.\"",
        "wsect_call_courts": "📜 Ela chama você por: {parts}",
        # ── compact breakdown labels (chat versions of the mini-app wsect_bd_*)
        "wsect_bd_path": "Caminho",
        "wsect_bd_continent": "Continente",
        "wsect_bd_karma": "Karma",
        "wsect_bd_lineage": "Linhagem",
        "wsect_bd_actions": "Atos",
        # ── Master-Disciple bond line (chat; markdown bold ok)
        "wsect_master_line": "🧧 Discípulo de *{master}* da {sect}.",
        # ── Guild disambiguation header (fim do "lio")
        "sect_guild_disambig": "🏯 Esta é a sua *Guilda* (seu clã). As 9 *Seitas Anciãs* — as Casas eternas que chamam você — vivem em `/seita_ancia`.",
    },
    "en": {
        "wsect_call_urgent": "{emoji} An Elder of {sect} cuts across your path, eyes like steel.\n\n\"The world does not wait for the hesitant. Our House rises — and sees in you the steel it seeks. Affinity {score}/100. Will you stand there, or come take what is ours?\"",
        "wsect_call_honor": "{emoji} An Elder of {sect} bows their head, serene.\n\n\"We have watched your journey from afar, and it honors the heavens. Affinity {score}/100. Accept, and you will be received with ceremony — and the Dao of our House will be yours.\"",
        "wsect_call_greed": "{emoji} An Elder of {sect} smiles, and the air smells of treasure.\n\n\"Few possess what I see in you. Affinity {score}/100. Join us, and no relic, no secret of the abyss will lie beyond your reach.\"",
        "wsect_call_courts": "📜 It calls you for: {parts}",
        "wsect_bd_path": "Path",
        "wsect_bd_continent": "Continent",
        "wsect_bd_karma": "Karma",
        "wsect_bd_lineage": "Lineage",
        "wsect_bd_actions": "Deeds",
        "wsect_master_line": "🧧 Disciple of *{master}* of {sect}.",
        "sect_guild_disambig": "🏯 This is your *Guild* (your clan). The 9 *Ancient Sects* — the eternal Houses that call you — live in `/seita_ancia`.",
    },
    "es": {
        "wsect_call_urgent": "{emoji} Un Anciano de {sect} te corta el paso, mirada de acero.\n\n\"El mundo no espera a los indecisos. Nuestra Casa se alza — y ve en ti el acero que busca. Afinidad {score}/100. ¿Te quedarás ahí, o vienes a tomar lo que es nuestro?\"",
        "wsect_call_honor": "{emoji} Un Anciano de {sect} inclina la cabeza, sereno.\n\n\"Hemos observado tu viaje desde lejos, y honra a los cielos. Afinidad {score}/100. Acepta, y serás recibido con ceremonia — y el Dao de nuestra Casa será tuyo.\"",
        "wsect_call_greed": "{emoji} Un Anciano de {sect} sonríe, y el aire huele a tesoro.\n\n\"Pocos tienen lo que veo en ti. Afinidad {score}/100. Únete a nosotros y ninguna reliquia, ningún secreto de los abismos quedará fuera de tu alcance.\"",
        "wsect_call_courts": "📜 Te llama por: {parts}",
        "wsect_bd_path": "Camino",
        "wsect_bd_continent": "Continente",
        "wsect_bd_karma": "Karma",
        "wsect_bd_lineage": "Linaje",
        "wsect_bd_actions": "Actos",
        "wsect_master_line": "🧧 Discípulo de *{master}* de {sect}.",
        "sect_guild_disambig": "🏯 Esta es tu *Guilda* (tu clan). Las 9 *Sectas Ancianas* — las Casas eternas que te llaman — viven en `/seita_ancia`.",
    },
}

MINIAPP = {
    "pt": {
        "sect_hall_master_line": "Discípulo de {master}",
        "sect_hall_strength_label": "Força viva da Casa",
        "sect_hall_blessing_note": "A bênção plena desperta no novo mundo — e crescerá com a força da Casa.",
        "profile_sect_master_line": "🧧 Discípulo de {master} da {sect}",
    },
    "en": {
        "sect_hall_master_line": "Disciple of {master}",
        "sect_hall_strength_label": "House's living strength",
        "sect_hall_blessing_note": "The full blessing awakens in the new world — and will grow with the House's strength.",
        "profile_sect_master_line": "🧧 Disciple of {master} of {sect}",
    },
    "es": {
        "sect_hall_master_line": "Discípulo de {master}",
        "sect_hall_strength_label": "Fuerza viva de la Casa",
        "sect_hall_blessing_note": "La bendición plena despierta en el nuevo mundo — y crecerá con la fuerza de la Casa.",
        "profile_sect_master_line": "🧧 Discípulo de {master} de {sect}",
    },
}


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
        json.dump(data, fh, ensure_ascii=False, indent=4)
        fh.write("\n")
    return before, before + added, added


def main():
    for lang, adds in CHAT.items():
        p = os.path.join(ROOT, "locales", f"{lang}.json")
        before, after, added = _apply(p, adds)
        print(f"chat    {lang}: {before} -> {after} (+{added})")
    for lang, adds in MINIAPP.items():
        p = os.path.join(ROOT, "miniapp", "i18n", f"{lang}.json")
        before, after, added = _apply(p, adds)
        print(f"miniapp {lang}: {before} -> {after} (+{added})")


if __name__ == "__main__":
    main()
