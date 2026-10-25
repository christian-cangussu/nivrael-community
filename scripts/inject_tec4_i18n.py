"""TEC-4 — Legacy Caves 传承洞 "Grutas do Legado" — injetor de i18n (chat + mini).

Roda:  python -X utf8 scripts/inject_tec4_i18n.py

Superfícies:
  · chat locales — TUDO server-resolved (padrão Chronicle/whisper): nome/desc
    da gruta e das 5 artes (tech_600..604), chronicle lgc_*, whisper
    wsp_cave_open_*, linhas/botão/erros do /viajar e o resultado do auto-play;
  · mini i18n — labels do card do mapa (lgc_mini_*) + painel self-doc da flag.

SO-ADICOES: `_apply` só escreve key que AINDA NÃO existe. Idempotente.
`newline="\n"` é load-bearing (Windows CRLF). Keys de ALERTA (lgc_err_*) e as
mensagens do /viajar são PLAIN TEXT (alerta/menu não renderizam Markdown).
Nomes de NPC são nomes próprios — idênticos nas 3 línguas (o {npc} chega do
engine). Verificador: scripts/_verify_tec4_i18n.py (anti-tuteamento + 14
idiomas EU-PT).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

CHAT = {
    "pt": {
        # ── A gruta (server-resolved nas views) ──
        "lgc_cave_name": "Gruta do Legado de {npc}",
        "lgc_house_tianlei": "Shen Tianlei enfrentou a tribulação de pé para salvar seus discípulos. O trovão que o matou ainda não terminou de cair.",
        "lgc_house_gushan": "Tiě Gǔshān temperou o corpo sob cachoeiras geladas por quinhentos anos, sem uma única pílula. A montanha ainda lembra do peso dele.",
        "lgc_house_wuchen": "Huā Wúchén refina o que o Dao Celestial não consegue tributar. O perfume desta gruta é uma receita que ninguém decifrou.",
        "lgc_house_wuming": "Yún Wúmíng pisou entre os planos e esqueceu de voltar. As grutas dele vagam pelo mundo como nuvens sem nome.",
        "lgc_house_xueye": "Lǐ Xuèyè escreveu seu sutra na única tinta que nunca seca. Esta gruta cheira a ferro — e observa quem entra.",
        # ── Chronicle + whisper ──
        "chron_lgc_open": "Os selos da tumba de {npc} quebraram — uma Gruta do Legado abriu em {continent}.",
        "chron_lgc_faded": "A Gruta do Legado de {npc} refez os próprios selos. A montanha esqueceu a entrada.",
        "chron_lgc_claim": "Um cultivador arrancou da gruta a arte perdida de {npc}. O mundo sentiu o legado trocar de mãos.",
        "wsp_cave_open_title": "🏮 A Tumba Abriu",
        "wsp_cave_open_body": "Os selos da tumba de {npc} quebraram em {place}. Por um breve tempo, a Gruta do Legado aceita visitantes.",
        # ── /viajar: vitrine honesta + botão ──
        "lgc_chat_line": "🏮 Gruta do Legado de {npc} em {emoji} {name} — {time} restantes",
        "lgc_chat_stakes": "A arte de legado se revela em {pct}% das vitórias e se garante na {pity}ª vitória na mesma gruta. Uma tentativa por abertura.",
        "lgc_chat_attempted": "Sua tentativa desta abertura já foi feita — aguarde a próxima.",
        "lgc_chat_has_art": "Você já guarda a arte desta gruta — o espólio vem em dobro.",
        "lgc_chat_enter_btn": "🏮 Entrar na Gruta do Legado",
        "lgc_chat_enter_toast": "🏮 Você entra na gruta...",
        # ── Recusas honestas (ALERTA: plain text) ──
        "lgc_err_wrong_continent": "A gruta fica em outro continente {emoji} — viaje até lá primeiro.",
        "lgc_err_attempted": "Sua tentativa desta abertura já foi consumida. A tumba reabrirá um dia.",
        "lgc_err_busy": "Você já está no meio de um duelo. Termine-o primeiro.",
        "lgc_err_hp": "Sua vitalidade está esgotada. Recupere-se antes de enfrentar o Eco.",
        "lgc_err_gone": "A gruta fechou os seus selos.",
        # ── Resultado do auto-play (menu: plain text) ──
        "lgc_chat_won": "🏮 Você venceu o Eco de {npc}! 🪨 +{stones} pedras espirituais.",
        "lgc_chat_won_mat": "📦 Materiais do continente foram somados ao seu anel.",
        "lgc_chat_won_bagfull": "⚠️ Seu anel espacial estava cheio — um material do espólio se perdeu.",
        "lgc_chat_won_frag": "💠 +{n} fragmento de Dao.",
        "lgc_chat_won_art": "⚡ A arte de legado {emoji} {name} é SUA. Cada uma pesa.",
        "lgc_chat_won_dupe": "Você já guardava esta arte — o espólio veio em dobro.",
        "lgc_chat_won_missed": "A arte não se revelou desta vez ({clears}/{pity} vitórias) — na última, ela se garante.",
        "lgc_chat_lost": "O Eco de {npc} repeliu você. A tentativa desta abertura foi consumida — a gruta aceitará você de novo na próxima.",
        # ── As 5 artes de legado (600-604, padrão tech_<id> do TEC-1) ──
        "tech_600_name": "Último Trovão",
        "tech_600_desc": "Shen Tianlei encarou sua tribulação de pé, e o raio que o matou nunca terminou de cair. A gruta o guarda; os dignos o emprestam. +66% de dano em todas as rodadas.",
        "tech_601_name": "Corpo das Nove Transformações",
        "tech_601_desc": "Tiě Gǔshān temperou o corpo sob cachoeiras geladas por quinhentos anos, sem uma única pílula. A nona transformação não é dureza — é paciência feita carne. Reduz em 55% o dano recebido.",
        "tech_602_name": "Pílula Além da Tribulação",
        "tech_602_desc": "Huā Wúchén refina o que o Dao Celestial não consegue tributar. Esmagada no punho, sua essência dissolve selos, armaduras e certezas. Ignora 55% da armadura do inimigo.",
        "tech_603_name": "Passo do Vazio",
        "tech_603_desc": "Yún Wúmíng pisou entre os planos e esqueceu de voltar. Aprenda o primeiro dos passos dele e o mundo vai perder você de vista. +42% de evasão em todas as rodadas.",
        "tech_604_name": "Sutra de Sangue",
        "tech_604_desc": "Lǐ Xuèyè o escreveu na única tinta que nunca seca. Cada verso recitado vira a vitalidade do inimigo contra ele mesmo. +68% de dano em todas as rodadas.",
    },
    "en": {
        "lgc_cave_name": "Legacy Cave of {npc}",
        "lgc_house_tianlei": "Shen Tianlei met his tribulation standing, to save his disciples. The thunder that killed him has not finished falling.",
        "lgc_house_gushan": "Tiě Gǔshān tempered his body under frozen waterfalls for five hundred years, without a single pill. The mountain still remembers his weight.",
        "lgc_house_wuchen": "Huā Wúchén refines what the Heavenly Dao cannot tax. The perfume of this cave is a recipe no one has deciphered.",
        "lgc_house_wuming": "Yún Wúmíng stepped between the planes and forgot to come back. His caves wander the world like nameless clouds.",
        "lgc_house_xueye": "Lǐ Xuèyè wrote her sutra in the only ink that never dries. This cave smells of iron — and watches whoever enters.",
        "chron_lgc_open": "The seals on the tomb of {npc} have broken — a Legacy Cave opened in {continent}.",
        "chron_lgc_faded": "The Legacy Cave of {npc} remade its own seals. The mountain forgot the entrance.",
        "chron_lgc_claim": "A cultivator tore the lost art of {npc} from the cave. The world felt the legacy change hands.",
        "wsp_cave_open_title": "🏮 The Tomb Has Opened",
        "wsp_cave_open_body": "The seals on the tomb of {npc} have broken in {place}. For a short while, the Legacy Cave accepts visitors.",
        "lgc_chat_line": "🏮 Legacy Cave of {npc} in {emoji} {name} — {time} left",
        "lgc_chat_stakes": "The legacy art reveals itself in {pct}% of victories and is guaranteed on your {pity}th victory in the same cave. One attempt per opening.",
        "lgc_chat_attempted": "Your attempt for this opening is spent — wait for the next one.",
        "lgc_chat_has_art": "You already hold this cave's art — the spoils come doubled.",
        "lgc_chat_enter_btn": "🏮 Enter the Legacy Cave",
        "lgc_chat_enter_toast": "🏮 You step into the cave...",
        "lgc_err_wrong_continent": "The cave lies on another continent {emoji} — travel there first.",
        "lgc_err_attempted": "Your attempt for this opening is already spent. The tomb will open again one day.",
        "lgc_err_busy": "You are already in the middle of a duel. Finish it first.",
        "lgc_err_hp": "Your vitality is drained. Recover before facing the Echo.",
        "lgc_err_gone": "The cave has closed its seals.",
        "lgc_chat_won": "🏮 You defeated the Echo of {npc}! 🪨 +{stones} spirit stones.",
        "lgc_chat_won_mat": "📦 Continental materials were added to your ring.",
        "lgc_chat_won_bagfull": "⚠️ Your spatial ring was full — one spoil material was lost.",
        "lgc_chat_won_frag": "💠 +{n} Dao fragment.",
        "lgc_chat_won_art": "⚡ The legacy art {emoji} {name} is YOURS. Each one carries weight.",
        "lgc_chat_won_dupe": "You already held this art — the spoils came doubled.",
        "lgc_chat_won_missed": "The art did not reveal itself this time ({clears}/{pity} victories) — on the last one, it is guaranteed.",
        "lgc_chat_lost": "The Echo of {npc} repelled you. This opening's attempt is spent — the cave will accept you again next time.",
        "tech_600_name": "Last Thunder",
        "tech_600_desc": "Shen Tianlei met his tribulation standing, and the bolt that killed him never finished falling. The cave keeps it; the worthy borrow it. +66% damage in all rounds.",
        "tech_601_name": "Nine Transformations Body",
        "tech_601_desc": "Tiě Gǔshān tempered his body under frozen waterfalls for five hundred years without a single pill. The ninth transformation is not hardness — it is patience made flesh. Reduces damage taken by 55%.",
        "tech_602_name": "Pill Beyond Tribulation",
        "tech_602_desc": "Huā Wúchén refines what the Heavenly Dao cannot tax. Crushed on the fist, her essence dissolves wards, armor and certainty alike. Ignores 55% of the enemy's armor.",
        "tech_603_name": "Void Walk",
        "tech_603_desc": "Yún Wúmíng stepped between the planes and forgot to come back. Learn the first of his steps and the world will keep losing track of where you are. +42% evasion in all rounds.",
        "tech_604_name": "Blood Sutra",
        "tech_604_desc": "Lǐ Xuèyè wrote it in the only ink that never dries. Every verse recited turns the enemy's vitality against them. +68% damage in all rounds.",
    },
    "es": {
        "lgc_cave_name": "Gruta del Legado de {npc}",
        "lgc_house_tianlei": "Shen Tianlei enfrentó su tribulación de pie para salvar a sus discípulos. El trueno que lo mató aún no ha terminado de caer.",
        "lgc_house_gushan": "Tiě Gǔshān templó su cuerpo bajo cascadas heladas durante quinientos años, sin una sola píldora. La montaña aún recuerda su peso.",
        "lgc_house_wuchen": "Huā Wúchén refina lo que el Dao Celestial no puede gravar. El perfume de esta gruta es una receta que nadie ha descifrado.",
        "lgc_house_wuming": "Yún Wúmíng pisó entre los planos y olvidó volver. Sus grutas vagan por el mundo como nubes sin nombre.",
        "lgc_house_xueye": "Lǐ Xuèyè escribió su sutra con la única tinta que nunca se seca. Esta gruta huele a hierro — y observa a quien entra.",
        "chron_lgc_open": "Los sellos de la tumba de {npc} se rompieron — una Gruta del Legado se abrió en {continent}.",
        "chron_lgc_faded": "La Gruta del Legado de {npc} rehízo sus propios sellos. La montaña olvidó la entrada.",
        "chron_lgc_claim": "Un cultivador arrancó de la gruta el arte perdido de {npc}. El mundo sintió el legado cambiar de manos.",
        "wsp_cave_open_title": "🏮 La Tumba Se Abrió",
        "wsp_cave_open_body": "Los sellos de la tumba de {npc} se rompieron en {place}. Por un breve tiempo, la Gruta del Legado acepta visitantes.",
        "lgc_chat_line": "🏮 Gruta del Legado de {npc} en {emoji} {name} — {time} restantes",
        "lgc_chat_stakes": "El arte del legado se revela en {pct}% de las victorias y se garantiza en tu {pity}ª victoria en la misma gruta. Un intento por apertura.",
        "lgc_chat_attempted": "Tu intento de esta apertura ya fue usado — espera la próxima.",
        "lgc_chat_has_art": "Ya guardas el arte de esta gruta — el botín llega doblado.",
        "lgc_chat_enter_btn": "🏮 Entrar en la Gruta del Legado",
        "lgc_chat_enter_toast": "🏮 Entras en la gruta...",
        "lgc_err_wrong_continent": "La gruta está en otro continente {emoji} — viaja allí primero.",
        "lgc_err_attempted": "Tu intento de esta apertura ya fue consumido. La tumba volverá a abrirse algún día.",
        "lgc_err_busy": "Ya estás en medio de un duelo. Termínalo primero.",
        "lgc_err_hp": "Tu vitalidad está agotada. Recupérate antes de enfrentar al Eco.",
        "lgc_err_gone": "La gruta cerró sus sellos.",
        "lgc_chat_won": "🏮 ¡Venciste al Eco de {npc}! 🪨 +{stones} piedras espirituales.",
        "lgc_chat_won_mat": "📦 Materiales del continente fueron añadidos a tu anillo.",
        "lgc_chat_won_bagfull": "⚠️ Tu anillo espacial estaba lleno — un material del botín se perdió.",
        "lgc_chat_won_frag": "💠 +{n} fragmento de Dao.",
        "lgc_chat_won_art": "⚡ El arte del legado {emoji} {name} es TUYO. Cada uno pesa.",
        "lgc_chat_won_dupe": "Ya guardabas este arte — el botín llegó doblado.",
        "lgc_chat_won_missed": "El arte no se reveló esta vez ({clears}/{pity} victorias) — en la última, se garantiza.",
        "lgc_chat_lost": "El Eco de {npc} te repelió. El intento de esta apertura fue consumido — la gruta te aceptará de nuevo la próxima vez.",
        "tech_600_name": "Último Trueno",
        "tech_600_desc": "Shen Tianlei enfrentó su tribulación de pie, y el rayo que lo mató nunca terminó de caer. La gruta lo guarda; los dignos lo toman prestado. +66% de daño en todas las rondas.",
        "tech_601_name": "Cuerpo de las Nueve Transformaciones",
        "tech_601_desc": "Tiě Gǔshān templó su cuerpo bajo cascadas heladas durante quinientos años sin una sola píldora. La novena transformación no es dureza — es paciencia hecha carne. Reduce en 55% el daño recibido.",
        "tech_602_name": "Píldora Más Allá de la Tribulación",
        "tech_602_desc": "Huā Wúchén refina lo que el Dao Celestial no puede gravar. Aplastada en el puño, su esencia disuelve sellos, armaduras y certezas. Ignora el 55% de la armadura del enemigo.",
        "tech_603_name": "Paso del Vacío",
        "tech_603_desc": "Yún Wúmíng pisó entre los planos y olvidó volver. Aprende el primero de sus pasos y el mundo te perderá de vista. +42% de evasión en todas las rondas.",
        "tech_604_name": "Sutra de Sangre",
        "tech_604_desc": "Lǐ Xuèyè lo escribió con la única tinta que nunca se seca. Cada verso recitado vuelve la vitalidad del enemigo en su contra. +68% de daño en todas las rondas.",
    },
}

MINIAPP = {
    "pt": {
        "lgc_mini_art_line": "{emoji} {name} — {pct}% por vitória · garantida na {pity}ª vitória",
        "lgc_mini_one_try": "Uma tentativa por abertura — a derrota também consome.",
        "lgc_mini_has_art": "Você já guarda esta arte — o espólio vem em dobro.",
        "lgc_mini_attempted": "Sua tentativa desta abertura já foi feita.",
        "lgc_mini_enter": "Entrar na Gruta",
        "lgc_mini_wrong": "A gruta fica em outro continente {emoji} — viaje até lá.",
        "lgc_mini_busy": "Você já está no meio de um duelo.",
        "lgc_mini_hp": "Recupere sua vitalidade antes de enfrentar o Eco.",
        "lgc_mini_gone": "A gruta fechou os seus selos.",
        "feature_legacy_caves": "🏮 Grutas do Legado 传承洞",
        "feature_legacy_caves_desc": "TEC-4 — quando uma casa busca herança no Pulso do Mundo (seek_inheritance), a tumba de um dos 5 NPCs lendários pode abrir VISITÁVEL no mapa por um prazo (knobs env: LGC_OPEN_CHANCE 0.20 · 1 ativa no mundo · LGC_GLOBAL_COOLDOWN_H 48 · LGC_TTL_H 72 · drift 70/30 · pity 7d). Entrar = 1 duelo vs o Eco do Legado (1 tentativa por abertura); vitória sempre paga (pedras + material + fragmento R5+); a arte única (ids 600-604) sai por LGC_ART_CHANCE 0.15 + garantia no LGC_PITY_CLEARS(3)º clear. INDEPENDENTE de tiandao_director (sweep próprio no pulso). LAUNCH-SERVER-BOUND: conteúdo novo — ligar primeiro em mundo de teste.",
    },
    "en": {
        "lgc_mini_art_line": "{emoji} {name} — {pct}% per victory · guaranteed on the {pity}th victory",
        "lgc_mini_one_try": "One attempt per opening — defeat also spends it.",
        "lgc_mini_has_art": "You already hold this art — the spoils come doubled.",
        "lgc_mini_attempted": "Your attempt for this opening is already spent.",
        "lgc_mini_enter": "Enter the Cave",
        "lgc_mini_wrong": "The cave lies on another continent {emoji} — travel there.",
        "lgc_mini_busy": "You are already in the middle of a duel.",
        "lgc_mini_hp": "Recover your vitality before facing the Echo.",
        "lgc_mini_gone": "The cave has closed its seals.",
        "feature_legacy_caves": "🏮 Legacy Caves 传承洞",
        "feature_legacy_caves_desc": "TEC-4 — when a house seeks inheritance in the World Pulse (seek_inheritance), the tomb of one of the 5 legendary NPCs may open VISITABLE on the map for a while (env knobs: LGC_OPEN_CHANCE 0.20 · 1 active worldwide · LGC_GLOBAL_COOLDOWN_H 48 · LGC_TTL_H 72 · 70/30 drift · 7d pity). Entering = 1 duel vs the Echo of the Legacy (1 attempt per opening); victory always pays (stones + material + R5+ fragment); the unique art (ids 600-604) drops at LGC_ART_CHANCE 0.15 + guarantee on the LGC_PITY_CLEARS(3)rd clear. INDEPENDENT of tiandao_director (own sweep in the pulse). LAUNCH-SERVER-BOUND: new content — enable on a test world first.",
    },
    "es": {
        "lgc_mini_art_line": "{emoji} {name} — {pct}% por victoria · garantizada en la {pity}ª victoria",
        "lgc_mini_one_try": "Un intento por apertura — la derrota también lo consume.",
        "lgc_mini_has_art": "Ya guardas este arte — el botín llega doblado.",
        "lgc_mini_attempted": "Tu intento de esta apertura ya fue usado.",
        "lgc_mini_enter": "Entrar en la Gruta",
        "lgc_mini_wrong": "La gruta está en otro continente {emoji} — viaja allí.",
        "lgc_mini_busy": "Ya estás en medio de un duelo.",
        "lgc_mini_hp": "Recupera tu vitalidad antes de enfrentar al Eco.",
        "lgc_mini_gone": "La gruta cerró sus sellos.",
        "feature_legacy_caves": "🏮 Grutas del Legado 传承洞",
        "feature_legacy_caves_desc": "TEC-4 — cuando una casa busca herencia en el Pulso del Mundo (seek_inheritance), la tumba de uno de los 5 PNJ legendarios puede abrirse VISITABLE en el mapa por un tiempo (knobs env: LGC_OPEN_CHANCE 0.20 · 1 activa en el mundo · LGC_GLOBAL_COOLDOWN_H 48 · LGC_TTL_H 72 · drift 70/30 · pity 7d). Entrar = 1 duelo vs el Eco del Legado (1 intento por apertura); la victoria siempre paga (piedras + material + fragmento R5+); el arte único (ids 600-604) sale con LGC_ART_CHANCE 0.15 + garantía en el LGC_PITY_CLEARS(3)º clear. INDEPENDIENTE de tiandao_director (sweep propio en el pulso). LAUNCH-SERVER-BOUND: contenido nuevo — activar primero en un mundo de prueba.",
    },
}

# ÚNICO override (documentado): a 1ª injeção desta MESMA leva saiu com {pity}
# repetido em lgc_chat_won_missed (o resolver do mini só troca a 1ª ocorrência;
# o verificador barrou). O override re-aplica a string corrigida por cima.
CHAT_OVERRIDES: dict = {
    lang: {"lgc_chat_won_missed": CHAT[lang]["lgc_chat_won_missed"]} for lang in LANGS
}
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
