# -*- coding: utf-8 -*-
"""印 OS ICONES — as strings do lote (2026-09-08).

Idempotente. Escreve **so'** em `miniapp/i18n/*`, e o motivo e' que este lote
nao acrescenta uma unica frase ao jogo: as marcas substituem emoji EM SITIOS QUE
JA' TEM O SEU ROTULO (a aba tem `tab_*`, o cartao da Home tem `home_card_*`, o
slot tem `inv_slot_*`). Uma marca nova nunca traz texto novo — traz, quando o
sitio nao tem rotulo visivel, um `aria-label` construido a partir do rotulo que
ja' existe. E' de proposito: inventar `icon_home`/`icon_sect` criaria uma segunda
verdade sobre o nome de cada destino, a divergir da primeira no primeiro sprint.

O que entra sao **duas** chaves: o rotulo e a descricao da flag `iconografia` no
painel do owner (ha' verificador que falha se uma flag do catalogo aparecer sem
rotulo OU sem descricao nas tres linguas — Lei §6: o painel auto-documenta-se).

⚠️ A descricao diz o que a flag NAO faz, porque e' isso que evita a ma' decisao:
ela nao toca nos emoji de CATALOGO (`beast.emoji`, `pill.emoji`, ...). Esses sao
conteudo, e na carta sao o glifo do verso honesto de uma peca sem arte.
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

MINI = {
    "pt": {
        "feature_iconografia": "印 Os Ícones (iconografia própria)",
        "feature_iconografia_desc": (
            "A navegação do jogo deixa de falar por emoji do sistema. Medido em "
            "08/09 no cliente: 194 emoji distintos, 1638 ocorrências. O defeito não "
            "é \"são feios\" — é que eles não são NOSSOS e mudam de forma: um emoji é "
            "desenhado pela fonte do aparelho, então o pagode da aba Seita são três "
            "ilustrações diferentes no iPhone, no Android e no Windows, com três "
            "paletas que ninguém aqui escolheu. Depois de a Pele Quente, a Carta e o "
            "Cultivador construírem uma linguagem de tinta quente e cinábrio, a barra "
            "de baixo continuava sendo um conjunto de pictogramas coloridos da Apple. "
            "O risco tem nome: o Amazing Cultivation Simulator — jogo chinês, de "
            "cultivo — foi lido como \"RimWorld chinês\" POR CAUSA DA UI. Entram 40 "
            "marcas SVG desenhadas, todas na mesma grade (24x24, traço 1.6, pontas "
            "redondas) e todas em currentColor: a cor vem sempre do lugar onde a marca "
            "vive, como o selo 朱砂 já fazia. Não é uma fonte chinesa, e isso é "
            "decisão: o mini-app não carrega nenhuma, e a 19px o caractere cai no "
            "fallback do sistema — seria trocar um conjunto de pictogramas alheios por "
            "outro. Alcance: os 25 destinos das abas (a barra de baixo E o trilho de "
            "desktop, que agrupa a MESMA lista), os 20 cartões da Home, os 6 slots de "
            "equipamento e 21 lugares de estado (cadeado, incenso para a espera, "
            "aviso, sim/não, presente). É aqui que morre também o ✦ que ainda marcava "
            "\"equipado\" na célula clássica do artefato — literalmente o glifo que a "
            "indústria usa desde 2023 para dizer \"gerado por IA\". Acessibilidade: a "
            "barra de baixo só escreve o nome do slot ATIVO, então com marcas os "
            "outros sete ficariam mudos para um leitor de tela — por isso a chave "
            "ligada traz aria-label no botão. NÃO toca nos emoji de CATÁLOGO (bestas, "
            "pílulas, artefatos): esses são conteúdo, e na carta são o glifo do verso "
            "honesto de uma peça que ainda não tem arte. Ortogonal a ui_v2, "
            "superficie_desktop, pele_quente, cena_cultivo e cartas. Re-render puro: "
            "desligar volta tudo ao emoji de hoje, byte a byte. Sem migration, sem "
            "estado no jogador."
        ),
    },
    "en": {
        "feature_iconografia": "印 The Icons (our own iconography)",
        "feature_iconografia_desc": (
            "The game's navigation stops speaking in system emoji. Measured 09/08 in "
            "the client: 194 distinct emoji, 1638 occurrences. The flaw is not that "
            "they are ugly — it is that they are not OURS and they change shape: an "
            "emoji is drawn by the device's font, so the pagoda on the Sect tab is "
            "three different illustrations on iPhone, Android and Windows, in three "
            "palettes nobody here chose. After the Warm Skin, the Card and the "
            "Cultivator built a language of warm ink and cinnabar, the bottom bar was "
            "still a set of colourful Apple pictograms. The risk has a name: Amazing "
            "Cultivation Simulator — a Chinese cultivation game — was read as "
            "\"Chinese RimWorld\" BECAUSE OF ITS UI. In come 40 drawn SVG marks, all "
            "on the same grid (24x24, stroke 1.6, round caps) and all in currentColor: "
            "the colour always comes from the place the mark lives in, exactly as the "
            "朱砂 seal already did. It is not a CJK font, and that is a decision: the "
            "mini-app loads none, and at 19px the glyph falls back to the system font "
            "— that would be trading one set of someone else's pictograms for another. "
            "Reach: the 25 tab destinations (the bottom bar AND the desktop rail, "
            "which groups the SAME list), the 20 Home cards, the 6 equipment slots and "
            "21 state sites (lock, incense for waiting, warning, yes/no, gift). This "
            "is also where the ✦ that still marked \"equipped\" on the classic "
            "artifact cell dies — literally the glyph the industry has used since 2023 "
            "to mean \"AI-generated\". Accessibility: the bottom bar only writes the "
            "ACTIVE slot's label, so with marks the other seven would be mute to a "
            "screen reader — which is why the flag ON adds aria-label to the button. "
            "It does NOT touch CATALOG emoji (beasts, pills, artifacts): those are "
            "content, and on the card they are the honest back of a piece with no art "
            "yet. Orthogonal to ui_v2, superficie_desktop, pele_quente, cena_cultivo "
            "and cartas. Pure re-render: turning it off returns every site to today's "
            "emoji, byte for byte. No migration, no player state."
        ),
    },
    "es": {
        "feature_iconografia": "印 Los Íconos (iconografía propia)",
        "feature_iconografia_desc": (
            "La navegación del juego deja de hablar con emoji del sistema. Medido el "
            "08/09 en el cliente: 194 emoji distintos, 1638 apariciones. El defecto no "
            "es que sean feos — es que no son NUESTROS y cambian de forma: un emoji lo "
            "dibuja la fuente del aparato, así que la pagoda de la pestaña Secta son "
            "tres ilustraciones distintas en iPhone, Android y Windows, con tres "
            "paletas que nadie aquí eligió. Después de que la Piel Cálida, la Carta y "
            "el Cultivador construyeran un lenguaje de tinta cálida y cinabrio, la "
            "barra inferior seguía siendo un conjunto de pictogramas de colores de "
            "Apple. El riesgo tiene nombre: Amazing Cultivation Simulator — juego "
            "chino, de cultivo — fue leído como \"RimWorld chino\" POR CULPA DE LA UI. "
            "Entran 40 marcas SVG dibujadas, todas en la misma retícula (24x24, trazo "
            "1.6, puntas redondas) y todas en currentColor: el color viene siempre del "
            "lugar donde vive la marca, como ya hacía el sello 朱砂. No es una fuente "
            "china, y eso es una decisión: el mini-app no carga ninguna, y a 19px el "
            "carácter cae en la fuente del sistema — sería cambiar un conjunto de "
            "pictogramas ajenos por otro. Alcance: los 25 destinos de las pestañas (la "
            "barra inferior Y el riel de escritorio, que agrupa la MISMA lista), las "
            "20 tarjetas del Inicio, las 6 ranuras de equipo y 21 lugares de estado "
            "(candado, incienso para la espera, aviso, sí/no, regalo). Aquí muere "
            "también el ✦ que aún marcaba \"equipado\" en la celda clásica del "
            "artefacto — literalmente el glifo que la industria usa desde 2023 para "
            "decir \"generado por IA\". Accesibilidad: la barra inferior solo escribe "
            "el nombre de la ranura ACTIVA, así que con marcas las otras siete "
            "quedarían mudas para un lector de pantalla — por eso la llave encendida "
            "añade aria-label al botón. NO toca los emoji de CATÁLOGO (bestias, "
            "píldoras, artefactos): esos son contenido, y en la carta son el reverso "
            "honesto de una pieza que aún no tiene arte. Ortogonal a ui_v2, "
            "superficie_desktop, pele_quente, cena_cultivo y cartas. Re-render puro: "
            "apagarla devuelve todo al emoji de hoy, byte a byte. Sin migration, sin "
            "estado en el jugador."
        ),
    },
}


def merge(path, add):
    """⚠️ `indent=4`, `newline="\\n"` e `sort_keys` sao o formato EXACTO dos
    ficheiros de hoje. Escrever com `indent=2` (ou deixar o Windows meter CRLF)
    reescreve as 3.766 linhas de cada lingua e enterra as 2 chaves novas num
    diff de 22.590 — que da' na mesma que nao as poder rever."""
    with io.open(path, encoding="utf-8") as f:
        d = json.load(f)
    new = [k for k in add if k not in d]
    d.update(add)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, ensure_ascii=False, indent=4, sort_keys=True)
        f.write("\n")
    return len(d), new


def main():
    counts = {}
    for lang in LANGS:
        p = os.path.join(ROOT, "miniapp", "i18n", "%s.json" % lang)
        n, new = merge(p, MINI[lang])
        counts[lang] = n
        print("miniapp/i18n/%s.json -> %d chaves (%d novas)" % (lang, n, len(new)))
    assert len(set(counts.values())) == 1, "PARIDADE QUEBRADA: %r" % counts


if __name__ == "__main__":
    main()
