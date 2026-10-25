# -*- coding: utf-8 -*-
"""牌 A CARTA — as strings novas do lote (2026-09-05).

Idempotente: correr duas vezes nao duplica nada. Escreve so' em
`miniapp/i18n/{pt,en,es}.json` — o chat nao ganha uma unica key (a carta e' do
mini-app, e `technique_grade_*` JA' existe nos `locales/`, que e' de onde estas
copias vem, verbatim, para os dois lados nunca discordarem).

Tres familias:

1. `technique_grade_*` (5) — copiadas de `locales/*.json` sem tocar numa letra.
   O mini-app nao as tinha; a carta precisa da PALAVRA do grau ao lado do lombo
   contado (o lombo diz "3 de 5", a palavra diz *qual*).

2. `beast_rank_*` (7) — NOVAS. Ate' hoje o mini-app imprimia `b.rank` CRU, ou
   seja "Legendary" em ingles a um jogador pt-BR, no `BeastsListPanel`, no
   `BeastsCapturePanel` e no `BeastsCompanionPanel`. E' a mesma familia de
   defeito que a WEB-E encontrou no Mar de Longevidade ("Core Formation: 500
   anos" a 300px do cartao que dizia "Nucleo") e sobram 7 sitios desses.
   ⚠️ Os valores na base sao Capitalizados (`config.BEAST_RANKS`); as keys sao
   minusculas porque `nivRank` faz `String(v).toLowerCase()` antes de procurar.

3. `feature_cartas` + `_desc` — o painel do owner auto-documenta-se (Lei §6).
   Ha' verificador: `_verify_mv11_i18n.py` falha se uma flag do catalogo
   aparecer sem rotulo OU sem descricao nas tres linguas.
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

# ── 1. os graus da tecnica, copiados do chat ─────────────────────────────────
GRADE_KEYS = ["technique_grade_common", "technique_grade_refined",
              "technique_grade_perfected", "technique_grade_transcendent",
              "technique_grade_celestial"]

# ── 2. os postos da besta ────────────────────────────────────────────────────
# pt-BR: "Comum/Incomum/Raro/Epico/Lendario/Mitico/Divino" — masculino porque o
# substantivo que eles qualificam e' "posto"/"rank" e porque o UI ja' escreve
# "Rank maximo atingido" (`beasts_err_max_rank`).
BEAST = {
    "pt": {
        "beast_rank_common": "Comum",
        "beast_rank_uncommon": "Incomum",
        "beast_rank_rare": "Raro",
        "beast_rank_epic": "Épico",
        "beast_rank_legendary": "Lendário",
        "beast_rank_mythic": "Mítico",
        "beast_rank_divine": "Divino",
    },
    "en": {
        "beast_rank_common": "Common",
        "beast_rank_uncommon": "Uncommon",
        "beast_rank_rare": "Rare",
        "beast_rank_epic": "Epic",
        "beast_rank_legendary": "Legendary",
        "beast_rank_mythic": "Mythic",
        "beast_rank_divine": "Divine",
    },
    "es": {
        "beast_rank_common": "Común",
        "beast_rank_uncommon": "Poco común",
        "beast_rank_rare": "Raro",
        "beast_rank_epic": "Épico",
        "beast_rank_legendary": "Legendario",
        "beast_rank_mythic": "Mítico",
        "beast_rank_divine": "Divino",
    },
}

# ── 3. a flag no painel do owner ─────────────────────────────────────────────
_DESC_PT = (
    "A carta-padrão do jogo. Hoje há 413 usos de <Card> e todos desenham a "
    "mesma moldura de painel — gradiente, borda dourada de 1px, raio 10, um fio "
    "no topo, cantos ornamentados: a mesma caixa para o Qi, para uma pílula e "
    "para um aviso. A carta nova SUBTRAI (um contorno, um fio, zero gradientes, "
    "raio 4, canto inferior direito chanfrado) e põe três marcas que carregam "
    "sentido. (1) 品 O LOMBO CONTADO: a raridade deixa de ser cor e vira MEDIDA "
    "— uma faixa no bordo esquerdo cortada em tantos entalhes quantos a escala "
    "daquele conteúdo tem. O motivo foi medido no motor: o jogo tem OITO "
    "vocabulários de raridade com tamanhos diferentes (técnica 5, besta 7, "
    "artefato 4, pílula 5, núcleo 4, armadilha 6, gacha 4, lei do Dao 5) — um "
    "código de cores obrigaria o jogador a decorar oito escalas e a acreditar "
    "que o \"Rare\" de uma besta é o mesmo que o \"perfected\" de uma arte, "
    "quando um é 3 de 7 e o outro é 3 de 5. Contar é o que o próprio gênero faz "
    "(三品丹 = pílula de terceiro grau). (2) O VERSO HONESTO: anéis de tinta "
    "mais o ícone da própria peça ficam pintados SEMPRE por baixo, então nunca "
    "há buraco enquanto a arte carrega, se ela falhar, ou enquanto a peça ainda "
    "não tem arte nenhuma — 307 peças não nascem no mesmo dia. (3) O SELO 朱砂, "
    "que marca só o estado ATIVO (arte equipada, besta companheira): o jogo "
    "torna verdadeira sozinho a regra de \"um selo por tela\", porque se equipam "
    "poucas artes e existe UM companheiro. Provada em três conteúdos — técnica, "
    "pílula e besta — nas duas telas (celular e larga) e nas duas peles. NÃO "
    "converte as outras cartas do jogo: com esta chave desligada, cada um dos "
    "três lugares desenha exatamente o que desenha hoje. Ortogonal a ui_v2, "
    "superficie_desktop, pele_quente e cena_cultivo. Sem migration, sem estado "
    "no jogador."
)
_DESC_EN = (
    "The game's standard card. Today there are 413 uses of <Card> and every one "
    "draws the same dashboard frame — gradient, 1px gold border, radius 10, a "
    "hairline on top, ornate corners: the same box for Qi, for a pill and for a "
    "notice. The new card SUBTRACTS (one outline, one rule, zero gradients, "
    "radius 4, a chamfered bottom-right corner) and adds three marks that carry "
    "meaning. (1) 品 THE COUNTED SPINE: rarity stops being a colour and becomes "
    "a MEASURE — a band on the left edge cut into exactly as many notches as "
    "that content's own scale has. The reason was measured in the engine: the "
    "game has EIGHT rarity vocabularies of different lengths (technique 5, beast "
    "7, artifact 4, pill 5, core 4, trap 6, gacha 4, dao law 5) — a colour code "
    "would force the player to learn eight scales and to believe a beast's "
    "\"Rare\" is the same as an art's \"perfected\", when one is 3 of 7 and the "
    "other is 3 of 5. Counting is what the genre itself does (三品丹 = a "
    "third-grade pill). (2) THE HONEST BACK: ink rings plus the piece's own icon "
    "are ALWAYS painted underneath, so there is never a hole while the art "
    "loads, if it fails, or while a piece has no art at all — 307 pieces are not "
    "born on the same day. (3) THE 朱砂 SEAL, which marks only the ACTIVE state "
    "(equipped art, companion beast): the game makes \"one seal per screen\" "
    "true by itself, because few arts are equipped and there is ONE companion. "
    "Proven on three contents — technique, pill and beast — on both surfaces "
    "(phone and wide) and in both skins. It does NOT convert the game's other "
    "cards: with this switch off, each of the three places draws exactly what it "
    "draws today. Orthogonal to ui_v2, superficie_desktop, pele_quente and "
    "cena_cultivo. No migration, no player state."
)
_DESC_ES = (
    "La carta estándar del juego. Hoy hay 413 usos de <Card> y todos dibujan el "
    "mismo marco de panel — degradado, borde dorado de 1px, radio 10, un hilo "
    "arriba, esquinas ornamentadas: la misma caja para el Qi, para una píldora y "
    "para un aviso. La carta nueva RESTA (un contorno, un hilo, cero degradados, "
    "radio 4, esquina inferior derecha achaflanada) y pone tres marcas que "
    "cargan sentido. (1) 品 EL LOMO CONTADO: la rareza deja de ser color y pasa "
    "a ser MEDIDA — una franja en el borde izquierdo cortada en tantas muescas "
    "como tenga la escala de ese contenido. El motivo se midió en el motor: el "
    "juego tiene OCHO vocabularios de rareza de largos distintos (técnica 5, "
    "bestia 7, artefacto 4, píldora 5, núcleo 4, trampa 6, gacha 4, ley del Dao "
    "5) — un código de colores obligaría al jugador a aprender ocho escalas y a "
    "creer que el \"Rare\" de una bestia es lo mismo que el \"perfected\" de un "
    "arte, cuando uno es 3 de 7 y el otro 3 de 5. Contar es lo que hace el "
    "propio género (三品丹 = píldora de tercer grado). (2) EL REVERSO HONESTO: "
    "anillos de tinta más el icono de la propia pieza quedan pintados SIEMPRE "
    "debajo, así que nunca hay hueco mientras el arte carga, si falla, o "
    "mientras la pieza aún no tiene arte — 307 piezas no nacen el mismo día. (3) "
    "EL SELLO 朱砂, que marca solo el estado ACTIVO (arte equipada, bestia "
    "compañera): el juego vuelve verdadera por sí sola la regla de \"un sello "
    "por pantalla\", porque se equipan pocas artes y hay UN compañero. Probada "
    "en tres contenidos — técnica, píldora y bestia — en las dos superficies "
    "(móvil y ancha) y en las dos pieles. NO convierte las demás cartas del "
    "juego: con esta llave apagada, cada uno de los tres lugares dibuja "
    "exactamente lo que dibuja hoy. Ortogonal a ui_v2, superficie_desktop, "
    "pele_quente y cena_cultivo. Sin migration, sin estado en el jugador."
)
FLAG = {
    "pt": {"feature_cartas": "牌 A Carta-Padrão", "feature_cartas_desc": _DESC_PT},
    "en": {"feature_cartas": "牌 The Standard Card", "feature_cartas_desc": _DESC_EN},
    "es": {"feature_cartas": "牌 La Carta Estándar", "feature_cartas_desc": _DESC_ES},
}


def main() -> int:
    chat = {lg: json.load(io.open(os.path.join(ROOT, "locales", f"{lg}.json"),
                                  encoding="utf-8")) for lg in LANGS}
    added_total = 0
    for lg in LANGS:
        path = os.path.join(ROOT, "miniapp", "i18n", f"{lg}.json")
        d = json.load(io.open(path, encoding="utf-8"))
        new: dict = {}
        # 1 — copia VERBATIM do chat: se divergirem, o mesmo grau teria dois
        #     nomes no mesmo jogo (o defeito do "Core Formation"/"Núcleo").
        for k in GRADE_KEYS:
            src = chat[lg].get(k)
            if src is None:
                print(f"  !! {lg}: `{k}` nao existe em locales/ — abortado")
                return 1
            new[k] = src
        new.update(BEAST[lg])
        new.update(FLAG[lg])

        added = 0
        for k, v in new.items():
            if k not in d:
                d[k] = v
                added += 1
        d = dict(sorted(d.items()))
        io.open(path, "w", encoding="utf-8", newline="\n").write(
            json.dumps(d, ensure_ascii=False, indent=4) + "\n")
        added_total += added
        print(f"  {lg}: +{added} keys -> {len(d)} total")
    print(f"total adicionadas: {added_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
