# -*- coding: utf-8 -*-
"""器 O ITEM VIVO — as 2 chaves do painel de admin, x3 linguas.

Porque existe um script em vez de tres edicoes a mao: o `pt.json` tem 3768
chaves e o `json.dump` por omissao reescreve o ficheiro inteiro com outra
indentacao — as 2 chaves novas ficavam enterradas num diff de 22.590 linhas e
ninguem as revia. `indent=4` + `newline="\\n"` + `ensure_ascii=False` sao os
mesmos do `inject_icones_i18n.py`, e mantem o diff em 3 linhas por ficheiro.

⚠️ AS DUAS chaves sao obrigatorias: `feature_<flag>` (o rotulo) E
`feature_<flag>_desc` (a descricao). O painel de admin auto-documenta-se a
partir delas (Lei §6 — "o painel se auto-documenta; nao fazer quiz ao owner"),
e ha guarda que falha se faltar qualquer uma das duas.

⚠️ A descricao cobre as TRES metades da flag. A 1a versao deste ficheiro so'
descrevia duas, porque a terceira (a face da peca em TODA parte, Lei F-7) nasceu
do report do owner a meio do lote. Uma descricao que descreve metade do que a
flag faz e' uma armadilha para quem a ligar — e o painel e' a unica coisa que o
owner le' antes de ligar um switch.

⚠️ `pt.json` e' portugues BRASILEIRO (decisao do owner). Nada de "continua a
mostrar" nem de "artefacto".
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYS = {
    "pt": {
        "feature_item_vivo": "器 O Item Vivo (a foto + o posto que se vê)",
        "feature_item_vivo_desc": (
            "A peça deixa de ser intercambiável. São três partes da mesma ordem do owner "
            "(08/09: \"as espadas cards diferenciados nos Tieres… se eu abrir o item na "
            "mochila mostrar a foto dele\" e, depois de olhar o resultado: \"imagens nao "
            "aparecem de espadas algumas vezes sim e outras nao\"). "
            "(1) A FOTO NO DETALHE: a arte de 51/51 artefatos já existia e já era servida "
            "na célula da mochila — quem não pedia ela era o modal de detalhe, que "
            "desenhava um ícone de 30px. Agora o artefato e a pílula usam o mesmo "
            "PieceHero que as feras já usavam. "
            "(2) A FOTO EM TODA PARTE (Lei F-7): só 12 pontos do cliente pediam a arte; a "
            "Forja, a Oficina de Artefatos, o refino, o encantamento, o perfil, a receita "
            "da pílula e a evolução da fera desenhavam um emoji à mão. Agora são 21 telas, "
            "todas pelo mesmo componente. Um item sem arte (ervas, minérios) continua "
            "mostrando o verso honesto — nada piora em lugar nenhum. "
            "(3) OS TRÊS PATAMARES: a carta era igual para um item de grau 0 e para um de "
            "grau 8. Agora existe comum (a carta de hoje), notável (o contorno esquenta e "
            "a lombada acende) e celeste (esquadro nos cantos, brilho, e a arte transborda "
            "a moldura). Isso NÃO reabre a decisão de 05/09: a lombada continua dizendo "
            "QUANTO (medido), e o ornamento só diz \"isso é raro\" — o primeiro você lê, o "
            "segundo você só sente. Três patamares e não nove, tirados da posição do "
            "degrau dentro da própria escala (p = i/(n-1); celeste ≥ .90, notável ≥ .60), "
            "nunca de uma lista fixa de nomes. "
            "A parte (3) só aparece se A Carta-Padrão também estiver ligada. Sem migration "
            "e sem estado no jogador: desligar devolve exatamente o que existe hoje."
        ),
    },
    "en": {
        "feature_item_vivo": "器 The Living Item (its photo, and rank you can see)",
        "feature_item_vivo_desc": (
            "A piece stops being interchangeable. Three parts of one owner order (09/08: "
            "\"swords, cards differentiated by tier… if I open the item in the bag, show "
            "its photo\", and then, after looking: \"sword images sometimes show and "
            "sometimes don't\"). "
            "(1) THE PHOTO IN THE DETAIL: art for 51/51 artifacts already existed and was "
            "already served in the bag cell — it was the detail modal that never asked for "
            "it, drawing a 30px icon instead. Artifacts and pills now use the same "
            "PieceHero the beasts already had. "
            "(2) THE PHOTO EVERYWHERE (Law F-7): only 12 points of the client asked for "
            "art; the forge, the artifact workshop, refining, enchanting, the profile, the "
            "pill recipe and beast evolution each hand-drew an emoji. Now 21 screens show "
            "the piece, all through one component. A piece with no art (herbs, ores) still "
            "shows the honest card back — nothing gets worse anywhere. "
            "(3) THE THREE TIERS: the card looked identical for a grade-0 and a grade-8 "
            "piece. Now there is common (today's card), notable (the outline warms, the "
            "spine lights up) and celestial (corner brackets, a glow, and the art bleeds "
            "past its plate). This does NOT reopen the 09/05 decision: the spine still "
            "says HOW MUCH (measured), the ornament only says \"this is rare\" — the first "
            "is read, the second is merely felt. Three tiers, not nine, derived from the "
            "step's position on its own scale (p = i/(n-1); celestial ≥ .90, notable ≥ "
            ".60), never from a fixed list of names. "
            "Part (3) only shows with The Standard Card also on. No migration, no player "
            "state: turning it off restores exactly what ships today."
        ),
    },
    "es": {
        "feature_item_vivo": "器 El Ítem Vivo (la foto + el rango que se ve)",
        "feature_item_vivo_desc": (
            "La pieza deja de ser intercambiable. Son tres partes de una misma orden del "
            "owner (08/09: \"las espadas, cards diferenciados en los tiers… si abro el "
            "ítem en la mochila, mostrar su foto\" y, tras mirar el resultado: \"las "
            "imágenes de espadas a veces salen y a veces no\"). "
            "(1) LA FOTO EN EL DETALLE: el arte de 51/51 artefactos ya existía y ya se "
            "servía en la celda de la mochila — era el modal de detalle el que no lo "
            "pedía: dibujaba un ícono de 30px. Ahora el artefacto y la píldora usan el "
            "mismo PieceHero que ya tenían las bestias. "
            "(2) LA FOTO EN TODAS PARTES (Ley F-7): solo 12 puntos del cliente pedían el "
            "arte; la forja, el taller de artefactos, el refinado, el encantamiento, el "
            "perfil, la receta de la píldora y la evolución de la bestia dibujaban un "
            "emoji a mano. Ahora son 21 pantallas, todas por el mismo componente. Una "
            "pieza sin arte (hierbas, minerales) sigue mostrando el reverso honesto. "
            "(3) LOS TRES PELDAÑOS: la carta era igual para una pieza de grado 0 y una de "
            "grado 8. Ahora hay común (la carta de hoy), notable (el contorno gana "
            "temperatura, el lomo se enciende) y celeste (escuadras en las esquinas, "
            "brillo, y el arte se derrama fuera de la placa). Esto NO reabre la decisión "
            "del 05/09: el lomo sigue diciendo CUÁNTO (medido) y el ornamento solo dice "
            "\"esto es raro\" — el primero se lee, el segundo solo se siente. Tres "
            "peldaños y no nueve, derivados de la posición del escalón en su propia escala "
            "(p = i/(n-1); celeste ≥ .90, notable ≥ .60), nunca de una lista fija de "
            "nombres. "
            "La parte (3) solo aparece con La Carta Estándar también encendida. Sin "
            "migración y sin estado en el jugador: apagarla devuelve exactamente lo de hoy."
        ),
    },
}


def main():
    for lang, pairs in KEYS.items():
        path = os.path.join(ROOT, "miniapp", "i18n", "%s.json" % lang)
        with io.open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        before = len(data)
        for k, v in pairs.items():
            data[k] = v
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=4)
            fh.write("\n")
        print("%s: %d -> %d chaves" % (lang, before, len(data)))


if __name__ == "__main__":
    main()
