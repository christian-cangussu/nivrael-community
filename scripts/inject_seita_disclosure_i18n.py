"""Seita — disclosure do bloqueio de caminho: injetor i18n (SO-ADICOES + 1 override).

Roda: python -X utf8 scripts/inject_seita_disclosure_i18n.py

Nasceu da pergunta do jogador **[jogador]** (28/07/2026): "como entro pra seita
demoniaca? aqui diz que um anciao vai aparecer pra mim". O jogo escondia a
resposta: o teaser do /seita so listava casas com afinidade > 0, e o hard-gate
de caminho ZERA a casa do outro lado — logo as Profundezas Abissais nunca
apareciam para quem nao era demoniaco. Nem o nome, nem o requisito.

Pior que um dead-end comum: a escolha de caminho e de UMA VEZ SO e abre no
Reino 3, entao dava para cristalizar Justo sem nunca saber que se fechou a
porta do Abismo para sempre.

CHAT (locales/*) = o cabecalho das casas barradas + os 2 motivos + o aviso da
escolha irreversivel. **OVERRIDE** do `wsect_menu_explain`: a string antiga
("Caminhe pelo mundo — e um dia um Anciao vai parar a sua frente") e passiva,
nao da agencia nenhuma e foi literalmente o que o jogador citou. A nova diz as
TRES alavancas que ele controla.

MINI (miniapp/i18n/*) = os mesmos 2 motivos (o card ja tinha "Caminho
incompativel", que dizia QUE mas nunca POR QUE).

PT-BR estrito (voce/seu, nunca tu/teu, nunca PT-europeu); ES usa tuteo;
placeholders {tok} un-accented e com o MESMO conjunto de tokens nas 3 linguas.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

CHAT = {
 "pt": {
  "wsect_menu_blocked_head": "*Fechadas para o seu caminho:*",
  "wsect_block_needs_demonic": "exige o Caminho Demoníaco 魔道",
  "wsect_block_barred_demonic": "nenhuma casa justa aceita um caminho caído",
  "wsect_menu_path_warning": "_O caminho se escolhe a partir do Reino 3 e cristaliza de uma vez só — depois de cristalizado não há troca. Escolha sabendo o que fecha._",
 },
 "en": {
  "wsect_menu_blocked_head": "*Closed to your path:*",
  "wsect_block_needs_demonic": "requires the Demonic Path 魔道",
  "wsect_block_barred_demonic": "no righteous house accepts a fallen path",
  "wsect_menu_path_warning": "_The path is chosen from Realm 3 and crystallizes once — after that there is no changing it. Choose knowing what it closes._",
 },
 "es": {
  "wsect_menu_blocked_head": "*Cerradas para tu camino:*",
  "wsect_block_needs_demonic": "exige el Camino Demoníaco 魔道",
  "wsect_block_barred_demonic": "ninguna casa justa acepta un camino caído",
  "wsect_menu_path_warning": "_El camino se elige a partir del Reino 3 y cristaliza de una sola vez — después no hay cambio. Elige sabiendo lo que cierra._",
 },
}

# A string antiga era passiva ("um Ancião vai parar à sua frente") e foi a que
# o jogador citou ao perguntar. A nova nomeia as 3 alavancas que ele controla.
CHAT_OVERRIDES = {
 "pt": {
  "wsect_menu_explain": "As Casas escolhem quem se alinha a elas — e três coisas movem esse alinhamento: seu *caminho*, o *continente* onde você pisa e seu *karma*. Suba a afinidade e um Ancião virá até você.",
 },
 "en": {
  "wsect_menu_explain": "The Houses choose those who align with them — and three things move that alignment: your *path*, the *continent* you stand on, and your *karma*. Raise the affinity and an Elder will come to you.",
 },
 "es": {
  "wsect_menu_explain": "Las Casas eligen a quien se alinea con ellas — y tres cosas mueven esa alineación: tu *camino*, el *continente* donde pisas y tu *karma*. Sube la afinidad y un Anciano vendrá a ti.",
 },
}

MINIAPP = {
 "pt": {
  "wsect_block_needs_demonic": "Exige o Caminho Demoníaco 魔道 — escolha do Reino 3, cristaliza de uma vez só.",
  "wsect_block_barred_demonic": "Nenhuma casa justa aceita um caminho caído.",
 },
 "en": {
  "wsect_block_needs_demonic": "Requires the Demonic Path 魔道 — chosen at Realm 3, crystallizes once.",
  "wsect_block_barred_demonic": "No righteous house accepts a fallen path.",
 },
 "es": {
  "wsect_block_needs_demonic": "Exige el Camino Demoníaco 魔道 — se elige en el Reino 3, cristaliza de una sola vez.",
  "wsect_block_barred_demonic": "Ninguna casa justa acepta un camino caído.",
 },
}


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
        b, a = _apply(os.path.join(ROOT, "miniapp", "i18n", lang + ".json"), MINIAPP[lang])
        print("mini " + lang + ": " + str(b) + " -> " + str(a) + " (+" + str(a - b) + ")")


if __name__ == "__main__":
    main()
