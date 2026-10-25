"""QoL-Feedback 2026-07-29 — injetor de i18n (chat + mini-app).

Roda:  python -X utf8 scripts/inject_qol_feedback_i18n.py

O lote dos 4 reports ([jogadores]):
  A. preview honesto da pilula de pureza (nota da fundacao) — inv_pill_detail_
     purity_note (chat) + pill_panel_purity_note (mini);
  B. grade-up com antes→depois (Lei §10) — tech_grade_upgraded_delta (chat) +
     combat_grade_upgrade_delta (mini); as keys ANTIGAS ficam intactas como
     fallback (so-adicoes);
  C. rep de FACCAO nomeada (🔱) + credito pulado dito — dng_quest_rep_* nas
     duas superficies;
  D. alimentar a Chama no mini (MA-48) — alch_sf_* no mini.

SO-ADICOES: `_apply` so escreve key que AINDA NAO existe (`if k not in data`).
Re-rodar e idempotente e nunca clobbera string viva. PT-BR estrito: voce/seu,
grafia BR (verificador: scripts/_verify_qol_feedback_i18n.py, com o bloco de
14 idiomas EU-PT do QoL-relatos). `newline="\n"` na escrita e load-bearing: sem
isso o Windows converte o ficheiro inteiro para CRLF e o diff explode.

Keys de ALERTA do Telegram (tech_grade_upgraded_delta, dng_quest_rep_gain/
_missed) sao PLAIN TEXT — alerta nao renderiza Markdown (licao Pedra 2:
"string dual-surface = plain text"). A unica key Markdown e a nota da
fundacao do card ℹ️ (inv_pill_detail_purity_note).

Lote 31/07 (mesmo prompt QoL-Feedback, sessao seguinte):
  B. dng_faction_quest_completed (chat, Markdown ok — mensagem de masmorra):
     a linha "Faction Quest completed" era EN hardcoded em 3 lugares do
     handler (advance/entrada/sweep);
  C. lgc_mini_* de espolio (mini): o loot da gruta do TEC-4 era MUDO no
     DuelArenaModal — textos espelham lgc_chat_won*/lgc_chat_lost do
     inject_tec4_i18n (o {npc} fica de fora: o banner ja mostra o Eco).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

CHAT = {
    "pt": {
        # Item A — nota da fundacao no card ℹ️ da pilula (Markdown ok aqui).
        "inv_pill_detail_purity_note": "🏯 Escala com sua fundação: *{foundation}*",
        # Item B — resultado do grade-up com antes→depois (ALERTA: plain text).
        "tech_grade_upgraded_delta": "✨ {emoji} {name} evoluiu: {old_grade_emoji} {old_grade} ×{old_mult} → {grade_emoji} {grade} ×{mult}!",
        # Item C — a rep das missões de masmorra é de FACÇÃO (🔱, o ícone do
        # sistema; ≠ rep de continente do MV-6). Preview + claim + crédito pulado.
        "dng_quest_rep_preview": "🔱 +{amount} Reputação de Facção",
        "dng_quest_rep_preview_nofaction": "🔱 +{amount} Reputação de Facção (requer facção — /faccao)",
        "dng_quest_rep_gain": "🔱 Reputação de Facção: +{amount}",
        "dng_quest_rep_missed": "🔱 Reputação de facção perdida (+{amount}) — junte-se a uma facção em /faccao para receber.",
        # Round 2 (report [jogador] 30/07): pílula no cap NÃO é mais consumida.
        "pill_stat_at_cap_kept": "⚠️ Seu {stat} já está no máximo ({cap}). A pílula não foi consumida.",
        "karma_event_path_crystallized": "Caminho cristalizado",
        # Lote 31/07 Item B — a linha de facção era EN hardcoded ×3 no handler.
        "dng_faction_quest_completed": "📜 *Missão de Facção:* {emoji} {name} completa!\n_Resgate no menu da facção (/faccao)._",
    },
    "en": {
        "inv_pill_detail_purity_note": "🏯 Scales with your foundation: *{foundation}*",
        "tech_grade_upgraded_delta": "✨ {emoji} {name} advanced: {old_grade_emoji} {old_grade} ×{old_mult} → {grade_emoji} {grade} ×{mult}!",
        "dng_quest_rep_preview": "🔱 +{amount} Faction Reputation",
        "dng_quest_rep_preview_nofaction": "🔱 +{amount} Faction Reputation (requires a faction — /faccao)",
        "dng_quest_rep_gain": "🔱 Faction Reputation: +{amount}",
        "dng_quest_rep_missed": "🔱 Faction reputation missed (+{amount}) — join a faction via /faccao to receive it.",
        "pill_stat_at_cap_kept": "⚠️ Your {stat} is already at its cap ({cap}). The pill was not consumed.",
        "karma_event_path_crystallized": "Path crystallized",
        "dng_faction_quest_completed": "📜 *Faction Quest:* {emoji} {name} completed!\n_Claim it in the Faction menu (/faccao)._",
    },
    "es": {
        "inv_pill_detail_purity_note": "🏯 Escala con tu fundación: *{foundation}*",
        "tech_grade_upgraded_delta": "✨ ¡{emoji} {name} evolucionó: {old_grade_emoji} {old_grade} ×{old_mult} → {grade_emoji} {grade} ×{mult}!",
        "dng_quest_rep_preview": "🔱 +{amount} Reputación de Facción",
        "dng_quest_rep_preview_nofaction": "🔱 +{amount} Reputación de Facción (requiere facción — /faccao)",
        "dng_quest_rep_gain": "🔱 Reputación de Facción: +{amount}",
        "dng_quest_rep_missed": "🔱 Reputación de facción perdida (+{amount}) — únete a una facción en /faccao para recibirla.",
        "pill_stat_at_cap_kept": "⚠️ Tu {stat} ya está al máximo ({cap}). La píldora no se consumió.",
        "karma_event_path_crystallized": "Camino cristalizado",
        "dng_faction_quest_completed": "📜 *Misión de Facción:* ¡{emoji} {name} completada!\n_Reclámala en el menú de facción (/faccao)._",
    },
}

MINIAPP = {
    "pt": {
        # Item A — nota da fundacao (vai atras do valor honesto, mesmo toast/linha).
        "pill_panel_purity_note": "escala com sua fundação ({fq})",
        # Item B — toast do grade-up com antes→depois.
        "combat_grade_upgrade_delta": "{emoji} {name}: {old_grade_emoji} {old_grade} ×{old_mult} → {grade_emoji} {grade} ×{mult}!",
        # Item C — moeda nomeada + aviso sem facção + crédito pulado no claim.
        "dng_quest_rep_faction_short": "Rep de Facção",
        "dng_quest_rep_needs_faction": "(requer facção)",
        "dng_quest_rep_missed_toast": "🔱 rep de facção perdida (+{n} — junte-se a uma facção)",
        # Item D — Alimentar a Chama (MA-48). Nomes espelham o chat:
        # "Núcleos de Monstro" (alch_sf_cores_owned) e "Chama da Alma".
        "alch_sf_cores_label": "Núcleos de Monstro: ×{n}",
        "alch_sf_feed_btn": "Alimentar Núcleo",
        "alch_sf_fed_toast": "🔥 +{xp} XP de Chama ({before} → {after})",
        "alch_sf_levelup_toast": "🔥 Chama da Alma evoluiu: {name}!",
        "alch_sf_no_cores_toast": "Sem Núcleos de Monstro no inventário — cace bestas para conseguir.",
        "alch_sf_locked_toast": "🔒 A Chama da Alma desperta no Reino {n}.",
        "alch_sf_feed_failed": "Não foi possível alimentar a Chama. Tente de novo.",
        # Round 2 (report [jogador] 30/07): pílula no cap NÃO é mais consumida.
        "pill_panel_at_cap_refused": "⚠️ Atributo no limite ({cap}) — a pílula não foi consumida.",
        "pill_panel_at_cap_kept": "⚠️ Limite atingido ({cap}) — as pílulas restantes não foram consumidas.",
        # Lote 31/07 Item C — espólio da gruta dito no DuelArenaModal (dívida
        # TEC-4); textos espelham lgc_chat_won*/lgc_chat_lost do TEC-4.
        "lgc_mini_loot_title": "🏮 Espólio do Legado",
        "lgc_mini_won_stones": "🪨 +{stones} pedras espirituais",
        "lgc_mini_won_mat": "📦 Materiais do continente foram somados ao seu anel.",
        "lgc_mini_won_bagfull": "⚠️ Seu anel espacial estava cheio — um material do espólio se perdeu.",
        "lgc_mini_won_frag": "💠 +{n} fragmento de Dao",
        "lgc_mini_won_art": "⚡ A arte de legado {emoji} {name} é SUA. Cada uma pesa.",
        "lgc_mini_won_dupe": "Você já guardava esta arte — o espólio veio em dobro.",
        "lgc_mini_won_missed": "A arte não se revelou desta vez ({clears}/{pity} vitórias) — na última, ela se garante.",
        "lgc_mini_lost_try": "A tentativa desta abertura foi consumida — a gruta aceitará você de novo na próxima.",
    },
    "en": {
        "pill_panel_purity_note": "scales with your foundation ({fq})",
        "combat_grade_upgrade_delta": "{emoji} {name}: {old_grade_emoji} {old_grade} ×{old_mult} → {grade_emoji} {grade} ×{mult}!",
        "dng_quest_rep_faction_short": "Faction Rep",
        "dng_quest_rep_needs_faction": "(requires a faction)",
        "dng_quest_rep_missed_toast": "🔱 faction rep missed (+{n} — join a faction)",
        "alch_sf_cores_label": "Beast Cores: ×{n}",
        "alch_sf_feed_btn": "Feed Core",
        "alch_sf_fed_toast": "🔥 +{xp} Flame XP ({before} → {after})",
        "alch_sf_levelup_toast": "🔥 The Soul Flame evolved: {name}!",
        "alch_sf_no_cores_toast": "No Beast Cores in your inventory — hunt beasts to get them.",
        "alch_sf_locked_toast": "🔒 The Soul Flame awakens at Realm {n}.",
        "alch_sf_feed_failed": "Could not feed the Flame. Try again.",
        "pill_panel_at_cap_refused": "⚠️ Attribute at its cap ({cap}) — the pill was not consumed.",
        "pill_panel_at_cap_kept": "⚠️ Cap reached ({cap}) — the remaining pills were not consumed.",
        "lgc_mini_loot_title": "🏮 Legacy Spoils",
        "lgc_mini_won_stones": "🪨 +{stones} spirit stones",
        "lgc_mini_won_mat": "📦 Continental materials were added to your ring.",
        "lgc_mini_won_bagfull": "⚠️ Your spatial ring was full — one spoil material was lost.",
        "lgc_mini_won_frag": "💠 +{n} Dao fragment",
        "lgc_mini_won_art": "⚡ The legacy art {emoji} {name} is YOURS. Each one carries weight.",
        "lgc_mini_won_dupe": "You already held this art — the spoils came doubled.",
        "lgc_mini_won_missed": "The art did not reveal itself this time ({clears}/{pity} victories) — on the last one, it is guaranteed.",
        "lgc_mini_lost_try": "This opening's attempt is spent — the cave will accept you again next time.",
    },
    "es": {
        "pill_panel_purity_note": "escala con tu fundación ({fq})",
        "combat_grade_upgrade_delta": "¡{emoji} {name}: {old_grade_emoji} {old_grade} ×{old_mult} → {grade_emoji} {grade} ×{mult}!",
        "dng_quest_rep_faction_short": "Rep de Facción",
        "dng_quest_rep_needs_faction": "(requiere facción)",
        "dng_quest_rep_missed_toast": "🔱 rep de facción perdida (+{n} — únete a una facción)",
        "alch_sf_cores_label": "Núcleos de Monstruo: ×{n}",
        "alch_sf_feed_btn": "Alimentar Núcleo",
        "alch_sf_fed_toast": "🔥 +{xp} XP de Llama ({before} → {after})",
        "alch_sf_levelup_toast": "🔥 ¡La Llama del Alma evolucionó: {name}!",
        "alch_sf_no_cores_toast": "Sin Núcleos de Monstruo en el inventario — caza bestias para conseguirlos.",
        "alch_sf_locked_toast": "🔒 La Llama del Alma despierta en el Reino {n}.",
        "alch_sf_feed_failed": "No se pudo alimentar la Llama. Inténtalo de nuevo.",
        "pill_panel_at_cap_refused": "⚠️ Atributo al máximo ({cap}) — la píldora no se consumió.",
        "pill_panel_at_cap_kept": "⚠️ Máximo alcanzado ({cap}) — las píldoras restantes no se consumieron.",
        "lgc_mini_loot_title": "🏮 Botín del Legado",
        "lgc_mini_won_stones": "🪨 +{stones} piedras espirituales",
        "lgc_mini_won_mat": "📦 Materiales del continente fueron añadidos a tu anillo.",
        "lgc_mini_won_bagfull": "⚠️ Tu anillo espacial estaba lleno — un material del botín se perdió.",
        "lgc_mini_won_frag": "💠 +{n} fragmento de Dao",
        "lgc_mini_won_art": "⚡ El arte del legado {emoji} {name} es TUYO. Cada uno pesa.",
        "lgc_mini_won_dupe": "Ya guardabas este arte — el botín llegó doblado.",
        "lgc_mini_won_missed": "El arte no se reveló esta vez ({clears}/{pity} victorias) — en la última, se garantiza.",
        "lgc_mini_lost_try": "El intento de esta apertura fue consumido — la gruta te aceptará de nuevo la próxima vez.",
    },
}

# Sem overrides neste lote — QoL-Feedback e 100% adicoes.
CHAT_OVERRIDES: dict = {}
MINI_OVERRIDES: dict = {}


def _apply(path: str, additions: dict, overrides: dict | None = None) -> tuple:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    before = len(data)
    for k, v in additions.items():
        if k not in data:
            data[k] = v
    for k, v in (overrides or {}).items():
        data[k] = v
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, sort_keys=True)
        f.write("\n")
    return before, len(data)


def main() -> None:
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "locales", lang + ".json"), CHAT[lang],
                      CHAT_OVERRIDES.get(lang))
        print("chat " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")
    for lang in LANGS:
        b, a = _apply(os.path.join(ROOT, "miniapp", "i18n", lang + ".json"), MINIAPP[lang],
                      MINI_OVERRIDES.get(lang))
        print("mini " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")


if __name__ == "__main__":
    main()
