# -*- coding: utf-8 -*-
"""画 O gerador de arte do Nivrael (2026-09-06).

Porque existe
-------------
O jogo precisa de ~307 pecas de arte e nenhuma existe. As 11 que ha' foram
geradas pelo owner a 2026-05-01 **para o site**, avulso — nao para o jogo (dito
por ele a 2026-09-06). Este script e' o caminho unico por onde arte nova entra.

O que ele NAO faz, de proposito
-------------------------------
- **Nao escreve em `miniapp/newapp/assets/`.** Grava em `tmp/art/` para revisao.
  Uma peca so' entra no jogo depois de o owner a ver (Lei §6) e de ganhar linha
  no registo de proveniencia.
- **Nao inventa estilo.** O `STYLE` abaixo e' copia literal do
  *Color Vibe of Imagery* de `miniapp/newapp/README.md`, que e' o seed unico.
  Errar la' nao custa uma imagem: custa 307.
- **Nao corre sem chave.** Sem `NV_IMAGE_API_KEY` no `.env`, sai com erro — nunca
  gera "por defeito" num tier que nao concede uso comercial.

Uso
---
    python scripts/gen_art.py --list
    python scripts/gen_art.py                  # o lote-piloto inteiro (10)
    python scripts/gen_art.py --only tech-thunder-step
    python scripts/gen_art.py --only beast-thunder-ox --seed 2   # outra tentativa

⚠️ CUSTO: ~$0.067 por imagem a 1K (tier standard, medido 2026-09-06:
1120 tokens de imagem por chamada). O piloto de 10 custa ~$0.67.
"""
import unicodedata
import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "tmp", "art")
MODEL = "gemini-3.1-flash-image"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"

# ── O SEED DE ESTILO ─────────────────────────────────────────────────────────
# ⚠️ Copia LITERAL do `Color Vibe of Imagery` (miniapp/newapp/README.md),
# reescrito a 2026-09-04 para a paleta quente. Nao editar aqui: editar la' e
# copiar. Duas fontes de estilo divergem no primeiro sprint.
STYLE = (
    "Dark, painterly, semi-realistic fantasy illustration with an ink-wash (shui-mo) "
    "sensibility rendered with depth. Never flat vector, never photography. "
    "Ground tones are WARM: near-black, charcoal, soot, bistre — the darkness of ink "
    "and lamp-smoke, not of night sky. Where the scene needs cold it comes from "
    "MATERIAL (jade, stone, mist, snow, ice), never from the ground itself. "
    "Light is aged gold and amber lantern-light, ember and hearth: light is the warm "
    "thing in the frame and what the eye is meant to find. "
    "Cinnabar red is used EXACTLY ONCE in the whole composition and never twice — a "
    "seal, a sash, a tassel, a talisman. It is a signature, not a colour scheme. "
    "Atmosphere: fog, smoke, incense, mountain haze, drifting ash; silhouetted "
    "ridgelines; depth built by layered atmosphere, not by drop shadow. "
    "NEVER: neon; aurora or borealis skies; cyan-teal rivers of energy; flat vectors; "
    "photography; Western high-fantasy armour; bright saturated mobile-game palettes."
)

# ── O ENQUADRAMENTO ──────────────────────────────────────────────────────────
# ⚠️ Ditado pela CARTA, nao pelo gosto: a chapa e' 4:3 e o pe dissolve-se no
# preto (gradiente ate' `--card`), o canto inferior esquerdo leva a etiqueta de
# estado e o direito leva o selo. Ver `Mecanicas/miniapp.md` §1.8.
FRAMING = (
    "Horizontal 4:3 composition. Subject centred with headroom above it. "
    "The lower third of the frame is intentionally quiet and fades into darkness — "
    "nothing essential below 70% of the height. Bottom-left and bottom-right corners "
    "stay calm and uncluttered. "
    # ⚠️ 2026-09-06, do piloto: a `abyss-wears-your-name` saiu linda e INUTIL —
    # a figura era um ponto ao fundo de um vale. A chapa da carta tem ~164px de
    # largura no telemovel; o que nao se le' a 164px nao existe.
    "The subject is LARGE in the frame and stays readable when the whole image is "
    "shown only 160 pixels wide: no tiny distant figures, no wide establishing shots. "
    # ⚠️ o modelo escreve garatujas sempre que ha' papel ou pergaminho na cena.
    "Absolutely no text, no lettering, no calligraphy, no scribbles or illegible "
    "written marks, no watermark, no border, no frame, no UI elements."
)

# ── O QUE CADA FAMILIA E' ────────────────────────────────────────────────────
# ⚠️ 2026-09-06: as 3 reprovas do lote-piloto foram todas a MESMA falha — o
# modelo nao sabe o que a peca E' no nosso mundo. A `pill-qi-gathering` saiu um
# comprimido farmaceutico moderno (disco branco, com sulco), que e' o oposto
# exacto de um 丹. Isto nao se conserta prompt a prompt: conserta-se AQUI, uma
# vez, e vale para as 307.
KIND_HINT = {
    "technique": (
        "This is a martial/cultivation ART in the act of being used: the EFFECT must be "
        "unmistakably visible on or around the practitioner, not merely implied by mood. "
        "IGNORE any numeric game statistics in the description (percentages, round counts, "
        "multipliers) — illustrate only the imagery."),
    "pill": (
        "This is a cultivation pill (dan): a small LUSTROUS SPHERE or ovoid, like a dark "
        "pearl or a polished bead, with depth and inner glow. It is NEVER a modern "
        "pharmaceutical tablet, never a flat white disc, never scored or stamped."),
    "beast": (
        "This is a spirit beast: a real animal silhouette, anatomically believable, with "
        "one supernatural trait made visible. Not a monster, not a chimera."),
    "artifact": (
        "This is a cultivation TREASURE shown as an object at rest, not in use and not "
        "held by anyone: a weapon, robe, ring, talisman or pendant, resting on stone, "
        "silk or an altar, lit by lamplight, with its spiritual nature visible as a "
        "faint inner glow or drifting qi. No wielder, no hands, no character in frame."),
    # ── 2026-09-14, ORDEM DO OWNER ───────────────────────────────────────────
    # Ele mandou a captura do ecra do Chefe e perguntou: *"Olhar tambem se os
    # Boss tem imagens."* MEDIDO: **0 de 9**. O que estava la' era o emoji do
    # sistema (`boss.emoji`) desenhado a 24px em tres sitios do `tabs.js` — o
    # Void Beast, que e' uma coisa vinda da fresta entre os mundos, aparecia
    # como **☯️**.
    #
    # ⚠️ A FAMILIA E' PROPRIA, e nao `beast`, por duas razoes medidas:
    #   1. o hint da besta EXIGE "a real animal silhouette, not a monster, not
    #      a chimera" — e metade dos nove NAO sao animais (Demonic Emperor,
    #      Corrupted Immortal, Void Wraith). Pedir a um Imperador que seja um
    #      animal anatomicamente credivel e' pedir ao modelo que se contradiga,
    #      que e' a licao de 13/09 sobre as proibicoes impossiveis.
    #   2. a besta e' um COMPANHEIRO (calma, nao a atacar); o chefe e' a coisa
    #      que o servidor inteiro enfrenta durante 5 horas. A postura e o
    #      enquadramento sao opostos.
    #
    # A regra que fica: o chefe e' UMA PRESENCA, vista de BAIXO, e a escala
    # le'-se sem precisar de uma pessoa ao lado para comparar (uma pessoa no
    # quadro poria um segundo protagonista onde so' pode haver o jogador).
    "boss": (
        "This is a WORLD BOSS: a single overwhelming presence that an entire sect "
        "would gather to face, seen from BELOW so it towers over the viewer. "
        "It may be a beast, a fallen immortal, a demon sovereign or a formless thing — "
        "follow the subject, do not force it into an animal shape. "
        "Its scale must read from the environment alone (cliffs, ruins, clouds, storm "
        "at its own height), NEVER by putting a person in frame for comparison: "
        "ABSOLUTELY NO PEOPLE, no cultivator, no silhouette of a human onlooker. "
        "It is mid-presence, not mid-attack: menace comes from stillness and mass, "
        "not from a lunging pose. "
        "IGNORE any numeric game statistics in the description (HP, tiers, damage)."),
    # ── 2026-09-07, ordem do owner ────────────────────────────────────────────
    # "as imagens relacionada aos reinos mudar. eu fiz ela de teste mesmo, porem
    #  deveriam ser realmente relacionada a nivrael"
    #
    # ⚠️ E ha' um segundo motivo, MEDIDO a 2026-09-05 e escrito no
    # `newapp/README.md`: as 11 actuais tem PESSOAS la' dentro, cada uma a fazer
    # coisa diferente — `realm-mortal` tem um viajante DE PE', `realm-core` esta'
    # a LEVITAR, `void-refinement` e' COMBATE, `true-immortal` esta' a VOAR. Foi
    # por isso que a cena do Cultivo nunca pode legendar a imagem: 5 das 11
    # desmentiriam a frase "voce esta' sentado". A regra que ficou foi "a arte
    # diz ONDE, o orbe diz O QUE".
    #
    # ⇒ O reino passa a ser um LUGAR VAZIO. Nao e' gosto: e' o que permite a
    # camada de cima (o cultivador) ser o JOGADOR sem que a de baixo o
    # contradiga. Duas camadas, duas responsabilidades.
    "realm": (
        "This is a PLACE — the landscape or interior of one stage of the cultivation "
        "ladder, painted as a wide establishing view. "
        "ABSOLUTELY NO PEOPLE: no figure, no cultivator, no silhouette of a person, "
        "no monk, no traveller, no hands. The place is empty and waiting. "
        "It must read as somewhere a cultivator would SIT for a very long time. "
        "Composition weighted to the UPPER HALF: the lower third will be covered by "
        "interface and must stay dark and quiet."),
    # A figura que substitui o orbe. Vive num quadrado de ~200px POR CIMA do
    # fundo do reino, e por isso tem duas exigencias que nenhuma outra familia
    # tem: (1) fundo quase-preto para dissolver na cena, (2) luz de recorte forte
    # para o corpo se ler contra um fundo que tambem e' escuro.
    "cultivator": (
        "This is a SINGLE seated cultivator in deep meditation, cross-legged, spine "
        "straight, hands resting in the lap — the subject fills the frame and is the "
        "ONLY thing in it. "
        # ⚠️ 2026-09-07: "near-black, empty" nao chegou — sairam montanhas e
        # nevoeiro em duas das tres. A figura vai POR CIMA de uma pintura de
        # reino; qualquer paisagem aqui briga com a de baixo e faz duas
        # profundidades no mesmo sitio. Tem de ser dito como PROIBICAO, nao como
        # preferencia.
        "Background: FLAT NEAR-BLACK AND COMPLETELY EMPTY. There is NO scenery of "
        "any kind behind the figure: no mountains, no mist banks, no clouds, no "
        "room, no wall, no floor line, no horizon, no ground plane, no distant "
        "shapes. The figure floats on featureless darkness, because it will be "
        "composited over a separate painting. "
        # ⚠️ o modelo pendura talismas escritos em qualquer roupa Han
        "No text anywhere: no talisman, no paper charm, no tag, no inscription, "
        "no calligraphy, no illegible scribbles on any hanging ornament. "
        "Lighting: strong warm rim-light along the shoulders, crown and knees so the "
        "silhouette separates from black; the body itself stays mostly in shadow. "
        "The base of the figure dissolves into the darkness — no visible cushion, no "
        "ground, no cast shadow, no vignette ring, no circular frame, no aura disc. "
        "Robes are Han-style cultivation robes with long sleeves. Serene, still, "
        "eyes closed. NOT a portrait bust: the whole seated body is visible."),
    # 圖 O MAPA (2026-09-11) — as DUAS familias do hub ilustrado.
    #
    # ⚠️ Sao duas e nao uma, e e' a decisao central do lote (V5 §3.2,
    # hipotese (b) "camadas separadas"): o FUNDO e' atmosfera e a PORTA e' um
    # objecto proprio. A alternativa — uma unica pintura com os cinco sitios
    # la' dentro e as coordenadas escritas no codigo — mente em silencio no
    # dia em que a arte for regerada (`ARTE_PROVENIENCIA §2.5`: regenerar =
    # ficheiro NOVO, logo a composicao muda e nenhum teste da' por isso).
    #
    # A consequencia disto no PROMPT e' dura e tem de ser dita como PROIBICAO,
    # nao como preferencia — foi o que custou tres tentativas ao `cultivator`:
    # um fundo que traga UM edificio ja' desenhado passa a ter duas portas para
    # o mesmo sitio, uma pintada e outra tocavel.
    "place": (
        "This is an EMPTY PLACE. Separate painted structures will be composited "
        "ON TOP of it later, so it must contain NONE of them. "
        "ABSOLUTELY NO BUILDINGS and no built things of any kind: no house, no "
        "temple, no pagoda, no forge, no furnace, no stall, no shelves, no "
        "furniture, no altar, no dais, no platform, no stairs, no bridge, no "
        "gate, no doorway, no fence, no banner, no lantern, no cart. "
        "NO PEOPLE and NO ANIMALS: no figure, no silhouette of a person, no "
        "bird, no beast, no fish, no insect — nothing alive that has a body. "
        "Only terrain, air and light: rock, ground, water, mist, smoke, sky, "
        "distant silhouetted ridges. "
        # ⚠️ 2026-09-16 — ESTAS DUAS PROIBICOES GANHARAM CORPO porque DUAS das
        # cinco primeiras pecas de continente as violaram, e a licao e' a de
        # 07/09 (o `cultivator` que saiu com montanhas em 2 de 3): **uma
        # proibicao que o modelo ignora tem de ser ENUMERADA, nao nomeada uma
        # vez.** O Qianhe veio com duas lanternas de ferro e uma fogueira
        # acesa — exactamente no meio, que e' onde a porta assenta, e portanto
        # exactamente o defeito "dois Fenghuo" que esta familia existe para
        # impedir. E veio com uma FOCA.
        "ABSOLUTELY NO LIGHT SOURCE THAT SOMEONE PUT THERE: no lantern, no "
        "lamp, no torch, no brazier, no campfire, no candle, no glowing "
        "talisman, no rope, no stake, no marker, no cairn, no carved sign. If "
        "the scene needs light it comes from the SKY, from the material itself "
        "(ember, ice, water, mist) or from off-frame. "
        # ⚠️ E a moldura: o Yanshan veio com a pintura DENTRO de um rectangulo,
        # com banda escura a toda a volta. Servida com `objectFit: cover` numa
        # caixa mais alta do que larga, essa banda le'-se como a aresta de um
        # cartao — que e' o defeito que o `HubScene` passou 11/09 a tirar.
        "The painting must BLEED to all four edges of the image: no painted "
        "border, no inset panel, no framed-picture look, no dark band around "
        "the edge, no passe-partout, no vignette rectangle. The terrain runs "
        "off every side. "
        "The middle of the frame stays relatively calm and uncluttered, because "
        "the painted structures will sit there. "
        "It must read as somewhere a cultivator lives or passes through, and it "
        "is empty and waiting."),
    "door": (
        "This is a SINGLE structure seen from outside at a short distance — a "
        "building, an installation or an opening that a person could walk into. "
        "The whole of it is visible and it is the ONLY thing in the frame. "
        # ⚠️ copiado do `cultivator` de proposito, e a razao e' a mesma: esta
        # peca vai POR CIMA de outra pintura. Qualquer paisagem aqui faz duas
        # profundidades no mesmo sitio. La' "near-black, empty" nao chegou e
        # sairam montanhas em duas de tres — por isso vai enumerado.
        "Background: FLAT NEAR-BLACK AND COMPLETELY EMPTY. There is NO scenery "
        "of any kind behind or around it: no mountains, no mist banks, no "
        "clouds, no room, no wall, no floor line, no horizon, no ground plane "
        "beyond the structure's own footing, no distant shapes, no cast shadow, "
        "no vignette ring, no circular frame, no aura disc. The structure sits "
        "on featureless darkness, because it will be composited over a separate "
        "painting. "
        "NO PEOPLE and NO ANIMALS anywhere. "
        "No text anywhere: no sign, no plaque, no inscription, no calligraphy, "
        "no illegible scribbles. Any banner, tablet or plaque must be BLANK. "
        "Lighting: its own warm lamplight, ember-glow or hearth-glow, plus a "
        "strong warm rim-light along its upper edges so the silhouette "
        "separates from black; the base dissolves into the darkness. "
        # ⚠️ a licao da `abyss-wears-your-name` (06/09), medida outra vez: a
        # porta e' desenhada a ~110px de largura no telemovel. O que nao se le'
        # a 110px nao e' uma porta, e' uma mancha.
        "The silhouette must stay readable when shown only 110 pixels wide: one "
        "clear compact shape, no thin scattered detail, no tiny far-away "
        "elements."),
    # ── 圖 O MUNDO, 2026-09-13 — porque e' uma familia NOVA e nao uma `door` ──
    # A `door` e', pela sua propria definicao, *"a SINGLE structure — a building,
    # an installation or an opening that a person could walk into"*, e proibe
    # por nome **montanhas, nevoeiro, nuvens e horizonte**. Um continente e'
    # exactamente isso: uma montanha com nevoeiro. Pedir os cinco continentes a'
    # familia `door` seria pedir a uma familia que se contradissesse — e a licao
    # de 07/09 (o `cultivator` que saiu com montanhas em 2 de 3) diz que uma
    # proibicao que o assunto contraria NAO se cumpre.
    #
    # O que se mantem da `door`, palavra por palavra, e' o CONTRATO DE
    # COMPOSICAO — fundo preto liso, luz de recorte, base dissolvida, legivel a
    # 110px — porque o problema e' o mesmo: a peca vai POR CIMA de outra
    # pintura. So' o assunto e' que muda.
    "land": (
        "This is a WHOLE TERRITORY seen from very high above and far away, as "
        "one compact landmass floating in empty darkness — an aerial view of a "
        "region, like a single island on an old map, with its coast or its "
        "edges visible all the way around. The whole of it is in frame and it "
        "is the ONLY thing in frame. "
        "Background: FLAT NEAR-BLACK AND COMPLETELY EMPTY, on all sides and "
        "under it. There is NO sky, no horizon line, no sea around it, no cloud "
        "bank around it, no other land, no distant shapes, no cast shadow, no "
        "vignette ring, no circular frame, no aura disc. The territory sits on "
        "featureless darkness, because it will be composited over a separate "
        "painting of the cloud sea. "
        "NO BUILDINGS: no city, no temple, no pagoda, no tower, no wall, no "
        "bridge, no road. NO PEOPLE and NO ANIMALS. Only the land itself: rock, "
        "ridge, water, ice, forest, ash, and the weather that belongs to it. "
        "No text anywhere: no lettering, no calligraphy, no map labels, no "
        "compass rose, no illegible scribbles. "
        "Lighting: the territory lit from above by its OWN character (the "
        "colour of its element), with a strong rim-light along its upper edges "
        "so the silhouette separates from black; the underside dissolves into "
        "the darkness. "
        "The silhouette must stay readable when shown only 110 pixels wide: one "
        "clear compact shape, no thin scattered detail, no tiny far-away "
        "elements."),
}

# ── O ENQUADRAMENTO POR FAMILIA ──────────────────────────────────────────────
# ⚠️ O `FRAMING` acima e' ditado pela CARTA (4:3, pe dissolvido, cantos calmos).
# Estas duas familias nao vivem numa carta, e herda-lo seria enquadrar para um
# sitio onde elas nunca aparecem: o reino e' um FUNDO largo de 340px que sangra
# de lado a lado (`RealmBackdrop`), e o cultivador e' um QUADRADO de ~200px no
# meio da cena (onde hoje esta' o orbe).
FRAMING_BY_KIND = {
    "realm": (
        "Wide cinematic 16:9 landscape composition. "
        # ⚠️ 2026-09-07 — a proibicao FRACA aqui deixou passar caligrafia falsa
        # por todo o ceu do `true-immortal`, DUAS vezes. A do `FRAMING` das
        # cartas (que nunca falhou em 236 pecas) e' mais dura porque nomeia o
        # que o modelo realmente faz: "garatujas / marcas escritas ilegiveis".
        # Nivelado por cima — correccao de FAMILIA, nao da peca.
        "ABSOLUTELY NO TEXT of any kind: no lettering, no calligraphy, no Chinese "
        "or Japanese characters, no inscriptions, no carved script on stone, no "
        "scribbles or illegible written marks anywhere in the frame, no signature, "
        "no watermark, no border, no frame, no UI elements. "
        "Any stone stele, tablet, banner or plaque in the scene must be BLANK. "
        "The image will be shown at 50% opacity behind interface, cropped to the "
        "centre and faded to black at the bottom and at both side edges — so keep "
        "the meaning in the upper-centre and let the edges fall into darkness."),
    "cultivator": (
        "Square 1:1 composition, the seated figure centred and LARGE, occupying "
        "roughly three quarters of the height. No text, no lettering, no watermark, "
        "no border, no frame, no UI elements, no decorative circle behind the figure."),
    # ⚠️ 4:3 e NAO 16:9: a cena do hub e' mais ALTA do que larga no telemovel
    # (~358x400) e mais larga do que alta no desktop. Serve-se com `cover` nos
    # dois, e por isso o que nao pode acontecer e' o assunto viver nas bordas.
    "place": (
        "Wide 4:3 composition. The image is shown behind interface, darkened, "
        "and cropped to the CENTRE — on a phone it is cropped to a taller shape "
        "and on a wide screen to a shorter one — and it fades to black at the "
        "bottom and at both side edges. Keep everything that matters in the "
        "middle of the frame and let all four edges fall into darkness. "
        "ABSOLUTELY NO TEXT of any kind: no lettering, no calligraphy, no "
        "Chinese or Japanese characters, no inscriptions, no carved script, no "
        "scribbles or illegible written marks anywhere, no signature, no "
        "watermark, no border, no frame, no UI elements."),
    "door": (
        "Square 1:1 composition, the structure centred and LARGE, occupying "
        "roughly three quarters of the frame. No text, no lettering, no "
        "watermark, no border, no frame, no UI elements, no decorative circle "
        "or halo behind the structure."),
    # 圖 O MUNDO (2026-09-13) — mesmo enquadramento da `door`, porque o problema
    # de composicao e' o MESMO: a peca vai por cima de outra pintura e e'
    # desenhada a ~110px. So' o ASSUNTO e' que muda (um territorio, nao um
    # edificio), e por isso a familia tem de ser outra — ver `KIND_HINT["land"]`.
    "land": (
        "Square 1:1 composition, the landmass centred and LARGE, occupying "
        "roughly three quarters of the frame. No text, no lettering, no "
        "watermark, no border, no frame, no UI elements, no decorative circle "
        "or halo behind the landmass."),
}
ASPECT_BY_KIND = {"realm": "16:9", "cultivator": "1:1",
                  "place": "4:3", "door": "1:1", "land": "1:1"}


def P(slug, kind, name, subject, note=""):
    return {"slug": slug, "kind": kind, "name": name, "subject": subject, "note": note}


# ── O LOTE-PILOTO (10) ───────────────────────────────────────────────────────
# Escolhido para FALHAR CEDO onde o estilo e' fragil, nao para ficar bonito:
# o frio que tem de vir do material, o cinabrio do Caminho Demoniaco, o quente
# no maximo, e o quase-sem-luz do fundo da escada.
#
# ⚠️ CORRECCAO ao que estava escrito em `ARTE_PROVENIENCIA.md §3.3`: a luz de
# uma tecnica segue o **ELEMENTO**, nao a cor do reino. O seed diz "o qi toma a
# cor do REINO" e isso e' verdade para o retrato de um CULTIVADOR num reino —
# mas uma tecnica identifica-se pelo elemento (o motor tem `element` em todas as
# 129 e constroi ressonancia e intencao por cima dele), e "Sunfire Body" com qi
# azul porque o reino 5 e' azul seria a imagem a contradizer o proprio nome. A
# cor do reino continua a mandar nas 11 ilustracoes de reino e na moldura da
# carta.
PILOT = [
    # ── 5 tecnicas, uma por familia de elemento, ao longo da escada ──────────
    P("tech-thunder-step", "technique", "Thunder Step",
      "A cultivator's after-image mid-stride on a rain-slick stone terrace, three "
      "translucent ghost-steps trailing behind the real body; sky-blue lightning "
      "crackling along the ankles and earthing into the wet flagstones; paper "
      "lanterns burning warm amber in the fog behind.",
      "elemento: relampago. O caso mais possuido do jogo."),
    P("tech-glacial-shell", "technique", "Glacial Shell",
      "Waist-up view of a cultivator, arms slightly spread, encased in THICK plates of "
      "translucent blue-white ice grown outward from the forearms, shoulders and chest "
      "— jagged, faceted, clearly solid, catching light on every edge. Frost rimes his "
      "brow and the air smokes with cold around him. The ice is the only cold thing in "
      "the frame and it is backlit by a warm ember brazier just behind him, so the cold "
      "reads as MATERIAL while the room stays warm.",
      "elemento: gelo. Prova que o frio vem do material, nunca do fundo."),
    P("tech-blood-frenzy", "technique", "Blood Frenzy",
      "A demonic cultivator seen against soot-black, demonic qi boiling off the "
      "shoulders as dark smoke that eats the lantern light around it; a single "
      "cinnabar seal-mark burns at the heart and is the ONLY red anywhere in the "
      "frame; the face is half-lost in shadow.",
      "elemento: caos. Onde o cinabrio corre mais risco de virar esquema de cor."),
    P("tech-sunfire-body", "technique", "Sunfire Body",
      "An elder wreathed in a small sun: dense gold and amber fire held tight to the "
      "body rather than thrown outward, the mountain behind him lost in warm haze, "
      "ash drifting upward through the light.",
      "elemento: fogo. O quente no maximo."),
    P("tech-abyss-wears-your-name", "technique", "The Abyss Wears Your Name",
      "Close view, waist-up, of a cultivator facing the viewer at the mouth of a "
      "lightless fissure: his own shadow has detached and risen behind and around him, "
      "reaching FORWARD past his shoulders toward the viewer, as if the deep were "
      "wearing him. His face is half-eaten by that darkness. Very little light — one "
      "dying lantern far behind him — and a single thread of cinnabar at his throat.",
      "elemento: caos, reino 8. O topo da escada e o quase-sem-luz."),
    # ── 3 pilulas: as duas pontas e o meio da escada de 5 ────────────────────
    P("pill-qi-gathering", "pill", "Qi Gathering Pill",
      "A single lustrous spherical pill — a dark amber bead with a deep inner glow, "
      "like polished resin — resting in the mouth of a tipped ceramic jar on a plain "
      "wooden board. Close, almost macro. Warm lamplight rakes from the left; faint qi "
      "vapour rises from the pill and curls. A few dried herb roots at the edge of the "
      "light. No paper, no scroll, no writing surface anywhere in the frame.",
      "grau 1 de 5. A que toda a gente fabrica."),
    P("pill-spirit-vein", "pill", "Spirit Vein Pill",
      "A deep blue-green pill held in bronze tweezers above a cooling cauldron, "
      "threads of pale qi still trailing from it like a cut vein; incense smoke, warm "
      "dark alchemist's workshop, one cinnabar cord on the cauldron handle.",
      "grau 3 de 5. O meio da escada."),
    P("pill-immortal-ascension", "pill", "Immortal Ascension Pill",
      "A pill resting on a cracked jade plate, gold light welling out from inside it "
      "like a forge glimpsed through a keyhole; the crack in the jade IS the "
      "composition, running under the pill; everything else in warm darkness.",
      "grau 5 de 5. O cume."),
    # ── 2 bestas: as duas pontas da escala de SETE ───────────────────────────
    P("beast-thunder-ox", "beast", "Thunder Ox",
      "A massive black ox standing in mountain fog, static electricity crackling "
      "sky-blue along the ridge of its back and horns; a single lantern behind it "
      "turning the mist warm amber; the animal is calm, not charging.",
      "posto 1 de 7. O companheiro do principiante."),
    P("beast-celestial-crane", "beast", "Celestial Crane",
      "A white crane rising through layered mountain haze, wings catching a low warm "
      "sun so the feathers glow gold at the edges; silhouetted ridgelines far below; "
      "one cinnabar band on its leg.",
      "posto 5 de 7. Carrega a sabedoria dos ceus."),
]


# ── O MODO CATALOGO: como as 307 se fazem ───────────────────────────────────
#
# ⚠️ O lote-piloto tem 10 assuntos escritos a' mao. **307 nao se escrevem a'
# mao** — nem se deve: o catalogo JA' descreve cada peca, e essa descricao e' a
# unica que o jogo mostra ao jogador. Se a imagem for gerada a partir de outro
# texto, a imagem e a legenda passam a contar historias diferentes, que e'
# exactamente o defeito que a tabela de posturas dos reinos apanhou.
#
# Entao o assunto DERIVA da linha do catalogo: nome + elemento/posto +
# descricao. O `STYLE`, o `KIND_HINT` e o `FRAMING` fazem o resto.
#
# ⚠️ A descricao de uma tecnica mistura imagem com estatistica ("The sword rides
# the wind. +18% damage in all rounds."). Nao se corta o numero por parsing —
# frageis demais e ha' 129 formas de o escrever. Diz-se ao modelo para o
# ignorar, no `KIND_HINT`.
def catalog_pieces(kind):
    sys.path.insert(0, ROOT)
    if kind == "beast":
        from database.seeds.beasts_seeds import BEASTS as rows
        return [P("beast-" + slugify(b["name"]), "beast", b["name"],
                  "A %s spirit beast of the %s element. %s"
                  % (b["rank"].lower(), b["element"].lower(), b["description"]),
                  "posto %s" % b["rank"]) for b in rows]
    if kind == "pill":
        from database.seeds.alchemy_seeds import PILLS as rows
        return [P("pill-" + slugify(p["name"]), "pill", p["name"],
                  "A cultivation pill named %s. %s" % (p["name"], p["description"]),
                  "grau %s de 5" % p["required_alchemy_tier"]) for p in rows]
    if kind == "artifact":
        from database.seeds.artifacts_seeds import ARTIFACTS as rows
        return [P("art-" + slugify(a["name"]), "artifact", a["name"],
                  "A cultivation artifact named %s — a %s. %s"
                  % (a["name"], a.get("type", "treasure"), a["description"]),
                  "grau %s / %s" % (a.get("grade", 0), a.get("type", "?")))
                for a in rows]
    # ── 2026-09-14 — OS NOVE CHEFES, pela ordem do owner ────────────────────
    # ⚠️ O slug vem do NOME e nao do id: `world_bosses.id` e' autoincremento por
    # APARICAO (o mesmo Void Beast nasce com id novo cada vez que o ceu o
    # larga), exactamente como no `catalog_slug` de `core/i18n.py`. Uma peca
    # por id significaria uma peca por aparicao.
    # ⚠️ O `WORLD_BOSS_POOL` nao traz descricao — traz nome, tier e emoji. O
    # sujeito escreve-se A' MAO, aqui, porque nove frases boas valem mais do
    # que nove geradas de um `loot_table`.
    if kind == "boss":
        return [P("boss-" + slugify(name), "boss", name, subject, nota)
                for name, subject, nota in BOSSES]
    if kind == "technique":
        from database.seeds.combat_seeds import TECHNIQUES as rows
        return [P("tech-" + slugify(t["name"]), "technique", t["name"],
                  "A cultivation art named %s, of the %s element. %s"
                  % (t["name"], t.get("element", "universal"), t["description"]),
                  "reino %s" % t.get("req_realm", 0)) for t in rows]
    # ── 界 OS ONZE REINOS, como LUGARES (2026-09-07) ─────────────────────────
    # ⚠️ Os nomes de ficheiro sao os MESMOS que existem hoje
    # (`realm-mortal.webp`, …) e isso e' deliberado: o `REALM_ART_FILES` do
    # `ui.js` ja' aponta para eles e a ordem dos 11 e' a ordem da escada. Trocar
    # o nome obrigaria a mexer no cliente sem ganhar nada.
    # ⚠️⚠️ MAS a rota `assets` serve com cache de UM ANO IMUTAVEL
    # (`ARTE_PROVENIENCIA.md §2.5`): substituir o corpo por baixo de um nome ja'
    # servido deixaria os 248 com a imagem velha em cache para sempre. Por isso
    # o `--approve` destas TEM de gravar com nome novo (sufixo `-v2`) e o
    # `REALM_ART_FILES` acompanha. Ver o aviso impresso no fim do `--list`.
    if kind == "realm":
        return [P("realm-" + slug, "realm", name, subject)
                for slug, name, subject in REALMS]
    # ── 坐 O CULTIVADOR que substitui o orbe ─────────────────────────────────
    if kind == "cultivator":
        return [P("cultivator-" + slug, "cultivator", name, subject)
                for slug, name, subject in CULTIVATORS]
    # 圖 O MAPA — a cena de cada hub, e as portas que vivem nela.
    if kind == "place":
        return [P(slug, "place", name, subject) for slug, name, subject in HUB_PLACES]
    if kind == "door":
        return [P(slug, "door", name, subject) for slug, name, subject in HUB_DOORS]
    # 州 Os cinco continentes — familia propria porque a `door` proibe por nome
    # montanhas e nevoeiro, e um continente e' as duas coisas (ver KIND_HINT).
    if kind == "land":
        return [P(slug, "land", name, subject) for slug, name, subject in HUB_LANDS]
    sys.exit("familia desconhecida: %s "
             "(beast|pill|technique|artifact|realm|cultivator|place|door|land)" % kind)


# ── 凶 OS NOVE CHEFES DO MUNDO (2026-09-14, ordem do owner) ─────────────────
# A pergunta que cada assunto responde: *o que e' que o servidor inteiro
# encontra quando chega?* — e a resposta nunca e' uma pose de ataque. Os tres
# tiers do `WORLD_BOSS_POOL` (mortal · spirit · immortal) dao a ESCALA: o
# mortal cabe num vale, o imortal nao cabe no quadro.
#
# ⚠️ Sem gente em nenhuma. Por um motivo de desenho e nao de regra: uma figura
# humana no quadro poe um segundo protagonista onde so' pode haver o jogador —
# a mesma razao pela qual os 11 reinos sao lugares VAZIOS desde 07/09.
BOSSES = [
    ("Demonic Emperor",
     "A colossal enthroned sovereign of the demonic path seen from below, armoured in "
     "black lacquer and bone, a crown of nine crooked horns; cinnabar-red qi bleeding "
     "from the throne down cracked palace steps; banners rotting in still air. "
     "He is seated and motionless — the menace is that he has not bothered to stand.",
     "tier mortal · o unico dos nove que esta' SENTADO"),

    ("Void Beast",
     "A vast formless thing filling a tear in the night sky above a dead salt flat: "
     "it has no stable silhouette, edges dissolving into starless black, faint violet "
     "light bending WRONG around where its body should be; the ground beneath it is "
     "bleached white and cracked. Nothing about it resolves into an animal.",
     "tier mortal · o que o owner fotografou a aparecer como ☯️"),

    ("Shadow Wolf Alpha",
     "An enormous black wolf standing on a ridge in moonlit pine forest, seen from "
     "below; its shadow on the ground is far larger than the animal and reaches "
     "toward the viewer; pale blue moonlight, breath steaming, eyes like two cold "
     "coals. Standing still, head lowered, not lunging.",
     "tier mortal · a sombra chega antes dos dentes"),

    ("Ancient Dragon",
     "A titanic eastern dragon coiled around a shattered mountain peak, scales like "
     "weathered jade and bronze, seen from the valley floor far below; storm clouds "
     "at its own height; one eye open, the rest of it still asleep. "
     "Gold-amber qi drifting from its whiskers.",
     "tier spirit · dormiu uma era"),

    ("Celestial Demon",
     "A winged figure of blinding white and rot descending through a broken heavenly "
     "gate, seen from below: half of it still radiant celestial gold, half blackened "
     "and fissured with crimson; feathers falling and burning as they fall. "
     "Faceless — the head is lost in its own light.",
     "tier spirit · subiu e o que desceu nao era o mesmo"),

    ("Void Wraith",
     "A tall hollow apparition of a cultivator's robes with nothing inside, drifting "
     "over a frozen lake under a starless sky; the fabric streams upward as if falling "
     "into somewhere above; faint violet witch-light where the face would be; the ice "
     "below reflects nothing.",
     "tier spirit · o que sobra de quem cruzou o vazio sem corpo"),

    ("Corrupted Immortal",
     "An immense seated figure in imperial immortal vestments atop a ruined jade "
     "platform, seen from below; the robes are pristine but the body beneath has gone "
     "to black crystalline rot spreading up the throat; a broken halo still turning "
     "above the head. Sickly gold light, absolute stillness.",
     "tier immortal · descobriu tarde o que trocou"),

    ("Primordial Chaos Beast",
     "An incomprehensible mass older than order filling the entire upper frame above a "
     "primordial sea: overlapping impossible geometries, shifting grey-gold light, "
     "nothing that resolves into a head or limbs; the water below is perfectly flat "
     "and reflects a DIFFERENT shape than the one above it.",
     "tier immortal · nao ataca, so' deixa de concordar que voce existe"),

    ("Heaven-Devouring Serpent",
     "A world-serpent whose body wraps the horizon, jaws open at the top of the frame "
     "swallowing a section of the night sky — stars visibly draining into its throat; "
     "scales like dark iron, seen from a cliff far below; the swallowed region of sky "
     "is pure absence, not black.",
     "tier immortal · engole o ceu uma bocada por vez"),
]


# ── 界 Os onze lugares ───────────────────────────────────────────────────────
# A escada e' `config.REALM_NAMES`; a cor de cada reino e' `--realm-N` do
# `newapp/README.md` e e' ela que manda no qi/luz de cada cena. O assunto de
# cada uma responde a UMA pergunta: *onde e' que alguem deste degrau se senta?*
# Nao ha' pessoas em nenhuma (`KIND_HINT["realm"]`).
REALMS = [
    ("mortal", "Mortal",
     "An empty terraced valley at dusk seen from a cliff path: rice terraces, a "
     "sleeping village of lantern-lit roofs far below, cold blue-grey mist between "
     "the ridges. The stone path is empty. This is the world before cultivation."),
    ("qi", "Qi Condensation",
     "The empty mouth of a mossy cave open to a night sky, a flat meditation ledge "
     "worn smooth by use, thin threads of sky-blue qi drifting in from the dark like "
     "water finding a channel. Nobody sits there yet."),
    # ⚠️ canon (`novel_reinos_canon.md`): R1→R2 exige a **Provacao da Fundacao**, e
    # a fundacao tem QUALIDADE — apressar sai caro. O lugar tem de ser um RITO a
    # espera, nao so' um patio bonito.
    ("foundation", "Foundation Establishment",
     "An empty rite-courtyard of a mountain sect at first light: a circular platform "
     "of fitted flagstones with a shallow carved basin at its centre, four unlit "
     "braziers at the cardinal points, amber lanterns still burning on the pillars, "
     "pine and drifting fog beyond. A trial is prepared here and has not begun. "
     "No people."),
    # ⚠️ canon: o rito R2→R3 e' formar o **Nucleo Dourado**, e ele e' OURO — a cor
    # violeta e' a do reino na interface, nao a do nucleo. A cena carrega as duas:
    # ambiente violeta, luz de ouro. Pintar o nucleo de violeta seria a imagem a
    # contradizer o nome que o jogo lhe da'.
    ("core", "Core Formation",
     "An empty vaulted hall of dark rock veined with violet crystal, a single bare "
     "meditation dais at the centre. From a fissure far above, one shaft of pure "
     "GOLDEN light falls exactly onto the dais and pools there like molten metal; "
     "the violet of the stone is only the ambience around it. Nobody on the dais."),
    ("nascent-soul", "Nascent Soul",
     "An empty grotto behind a waterfall of pale mist rather than water, a still "
     "black pool reflecting a second, ghostly cavern beneath it — the world doubled. "
     "Teal light from below the surface. No figure."),
    ("soul-transformation", "Soul Transformation",
     "An empty pavilion on a spur of rock above a sea of cloud at night, deep blue "
     "starlight, the pillars half dissolved into mist as if the building itself were "
     "losing its edges. Nobody there."),
    ("void-refinement", "Void Refinement",
     "An empty rift in the air over a shattered plateau: reality cracked open in a "
     "seam of violet dark, stones hanging motionless where they fell. Silent, "
     "abandoned, no combat, no people."),
    ("body-integration", "Body Integration",
     "The empty interior of a colossal forge carved into a mountain heart, molten "
     "amber light from a channel of fire below, hammer-scarred anvil-stone, warm "
     "orange haze. The body as a furnace. No smith, no figure."),
    ("mahayana", "Mahayana",
     "An empty summit above every cloud at the blue hour, a ring of ancient weathered "
     "steles half-buried in snow, the sky enormous and pale. The last mortal ground. "
     "Nobody is standing there."),
    # ⚠️ canon: as tribulacoes pontuam a escada inteira, mas o R9 E' a tribulacao.
    # O chao tem de contar quantas ja' cairam ali.
    ("tribulation", "Tribulation Transcendence",
     "An empty scorched plateau under a low black thunderhead. The ground is fused "
     "to glass in overlapping scars where lightning has struck the same spot many "
     "times over centuries, each ring older than the last. One bolt hangs frozen "
     "mid-fall, white and gold against the dark. Nothing stands beneath it."),
    # ⚠️ canon: o R10 e' o topo do MUNDO. O lugar tem de ser uma PORTA, nao um
    # trono: a composicao aponta para fora.
    ("true-immortal", "True Immortal",
     "An empty threshold at the very top of the world: a broken jade stair rising "
     "out of a rose-gold cloud sea and ending in open, formless light — the stair "
     "goes somewhere the frame cannot show. Gold cloud-curls and drifting motes of "
     "light in the air. No ceiling, no floor, nothing human. A door, not a throne."),
    # ⚠️ A 1a versao pedia "gold cloud-SCRIPT" e o modelo escreveu garatujas
    # ilegiveis por todo o ceu — e estava a obedecer: o `FRAMING` proibia texto e
    # o ASSUNTO pedia-o. A culpa era do briefing, nao do modelo. Se uma peca sair
    # com letras, procurar primeiro a palavra que as encomendou.
]

# ── 坐 O cultivador ──────────────────────────────────────────────────────────
# ⚠️ TRES pecas, nao 22. A alternativa era assar a figura dentro de cada uma das
# 11 imagens de reino (11 x 2 gene..s = 22) — e alem do custo, isso trancava:
# uma terceira opcao de figura passaria a custar +11 em vez de +1. Com duas
# camadas, o reino e' o LUGAR e o cultivador e' QUEM — e cada um muda sozinho.
#
# ⚠️ A terceira peca (`back`) nao e' um extra: e' o estado HONESTO de quem ainda
# nao escolheu genero — e sao **248 jogadores**, porque a coluna nasce NULL.
# 背影, a figura de costas, e' como a pintura chinesa classica retrata quem
# medita; nao e' uma evasiva, e' o idioma do genero.
CULTIVATORS = [
    ("male", "Cultivator (male)",
     "A young man in dark Han cultivation robes, seated cross-legged in deep "
     "meditation, seen from the front, face calm with eyes closed, long hair bound "
     "up in a simple topknot."),
    ("female", "Cultivator (female)",
     "A young woman in dark Han cultivation robes, seated cross-legged in deep "
     "meditation, seen from the front, face calm with eyes closed, long hair bound "
     "with a plain pin, sleeves pooling over the knees."),
    # ⚠️ 2026-09-07, apanhado pelo OWNER: a 1a versao saiu um HIBRIDO — cabeca,
    # nuca e ombros de costas, mas as MAOS em concha no colo, o NO do cinto e o
    # LACO vermelho todos vistos de FRENTE. Um tronco torcido 180 graus. E' a
    # falha classica do modelo com 背影: ele conhece "meditacao sentada" como uma
    # pose FRONTAL e so' roda a cabeca.
    # O conserto nao e' pedir "de costas" com mais forca — e' NOMEAR o que NAO
    # pode aparecer, porque e' isso que denuncia a frente.
    ("back", "Cultivator (unnamed)",
     "A cultivator seen strictly FROM BEHIND (the classical 背影) — the viewer "
     "stands behind the figure and sees only its BACK. Seated cross-legged in "
     "deep meditation: the back of the head, the nape of the neck, bound hair, "
     "and the shoulder blades and spine under the robe. "
     "CRITICAL, the whole pose must be consistent from one single viewpoint: the "
     "HANDS ARE NOT VISIBLE (they rest in the lap, completely hidden by the "
     "torso), the SOLES OF THE FEET ARE NOT VISIBLE, and no front-of-garment "
     "detail may appear — no sash knot, no hanging tassel, no lapel, no collar "
     "crossing, no belt buckle, nothing that only exists on the front of a robe. "
     "Do NOT rotate only the head: the entire body faces away from the viewer. "
     "The face is not visible and must not be guessable — this figure belongs to "
     "whoever is looking at it."),
]


# ── 圖 AS CENAS DOS HUBS ─────────────────────────────────────────────────────
# UMA por hub — e QUATRO e nao cinco: o `hub_combate` tem um unico destino e o
# proprio combate JA' e' o landing. Uma cena com uma porta so' e' uma porta com
# moldura (V5 §3.1).
#
# ⚠️ O que NAO esta' aqui e' tao decisivo como o que esta': a cena nao tem
# edificios. Todos eles sao `door`s, pintadas a' parte e postas por CSS. E' a
# hipotese (b) inteira numa frase.
HUB_PLACES = [
    # 圖 O MUNDO (2026-09-13) — e repare no que este assunto NAO tem: terra.
    # A cena do Mundo e' o **espaco ENTRE** os continentes, porque os cinco
    # continentes sao pecas `land` postas por cima. E' a hipotese (b) levada ao
    # fim: se a terra viesse no fundo, o mapa passava a ter dois Fenghuo — um
    # pintado e outro tocavel — que e' exactamente o defeito que a proibicao de
    # edificios da `place` existe para impedir.
    # ⚠️ A 1ª tentativa (`hub-mundo`, gerada e OLHADA a 2026-09-13) saiu bonita
    # e ERRADA PARA O TRABALHO DELA, e o defeito so' se viu montado: um mar de
    # nuvens "a hora antes da madrugada" e' PALIDO, e as cinco pecas `land` sao
    # massas de terra ESCURAS. O fundo ficou a coisa mais clara do ecra e os
    # continentes leram-se como cinco buracos — contraste invertido. Pior: a
    # mascara radial que dissolve o bordo de cada peca corta um quadrado de
    # quase-preto num CIRCULO, e contra um ceu claro esse circulo VE-SE. Eram
    # cinco discos cinzentos a emoldurar os continentes — a mesma avaria que a
    # chapa de recurso produziu a 11/09, renascida, porque o fundo mudou de
    # escuro para claro.
    #
    # A licao que fica, e vale para toda a familia: **um fundo `place` e' o
    # CHAO, e um chao mais claro do que as suas figuras nao e' uma questao de
    # afinacao — e' um erro de composicao.** As pecas `door`/`land` nascem sobre
    # quase-preto por contrato; logo a cena por baixo TEM de ser escura.
    #
    # `ARTE_PROVENIENCIA §2.5`: regerar = ficheiro NOVO. A 1ª fica no historico.
    ("hub-mundo", "O Mundo 天下 (1ª — clara demais, substituida)",
     "An immense sea of cloud seen from very high above, at the hour before "
     "dawn: layer upon layer of slow grey-blue cloud stretching to a pale "
     "distant horizon, with a broad river of brighter mist winding through the "
     "middle of it and a scatter of faint stars still burning in the deep sky "
     "overhead. NO LAND ANYWHERE: no island, no mountain, no peak, no ridge, "
     "no shore, no rock breaking the cloud — nothing but cloud, air and light. "
     "The centre of the frame is the calmest and most open part of the sky."),
    ("hub-mundo-noite", "O Mundo 天下 — o vazio entre os continentes",
     "An immense sea of cloud seen from very high above in the DEAD OF NIGHT, "
     "painted almost entirely in near-black and the deepest blue-black. It is "
     "a DARK image: the cloud is barely visible, reading as slow charcoal "
     "shapes that only just separate from the blackness, with a few thin "
     "edges catching cold starlight. Above it, a deep black sky with a quiet "
     "scatter of small stars. NO LAND ANYWHERE: no island, no mountain, no "
     "peak, no ridge, no shore, no rock breaking the cloud — nothing but "
     "night cloud, air and darkness. NO MOON, no bright glow, no dawn light, "
     "no pale horizon band, no light source of any kind in the frame. The "
     "centre of the frame is the darkest, calmest and emptiest part, because "
     "bright painted landmasses will be composited on top of it and it must "
     "sit BEHIND them."),
    ("hub-caverna", "A Caverna 洞府",
     "The empty interior of a cultivator's mountain cave-dwelling, seen from "
     "within: a wide chamber of dark veined rock, a vaulted ceiling lost in "
     "blackness far above, a floor of worn uneven stone, and a slow drift of "
     "incense smoke and mineral haze catching a single source of warm amber "
     "lamplight that comes from off-frame. A thin seam of pale jade runs "
     "through the rock on one side. The chamber is bare and lived-in only by "
     "the light: nothing has been built in it."),

    # ── 州 O CHAO DOS CINCO CONTINENTES (2026-09-16, correccao do owner) ─────
    #
    # 🔴 O OWNER CORRIGIU O QUE EU ENTREGUEI A 15/09, e a correccao e' de
    # CATEGORIA. Textual: *"quando estou no continente eu abro ele tipo um mapa
    # mundial, e dentro tem a imagem da praza aventura, as dungeons"*.
    #
    # Eu tinha feito uma GRELHA de azulejos pintados por baixo do mapa. Ele quer
    # que o continente ABRA COMO UM LUGAR, com os sitios POSTOS DENTRO dele —
    # exactamente o que a Caverna e o Mundo ja' fazem uma camada acima.
    #
    # ⚠️ Isto NAO contradiz a proibicao da V5 §2 / V7. O que la' esta' proibido
    # e' *"uma pintura unica do continente com os seis sitios LA' DENTRO e as
    # coordenadas no codigo"* — ou seja, os edificios PINTADOS no fundo. Estas
    # cinco sao `place`: **chao vazio**, e as seis `door-mundo-*` continuam a ser
    # pecas separadas postas por CSS. E' a hipotese (b) outra vez, um nivel
    # abaixo: regerar o chao nao move uma porta.
    #
    # ⚠️ E a licao do `hub-mundo` (13/09) manda aqui com mais forca do que em
    # qualquer outro sitio: **um chao mais claro do que as suas figuras nao e'
    # uma questao de afinacao, e' um erro de composicao.** As `door` nascem
    # sobre quase-preto por contrato; estas cinco tem de ser ESCURAS, com a cor
    # do continente a vir da LUZ e nao do fundo.
    #
    # A identidade de cor de cada um vem do seu `land-mundo-*` (a vista aerea do
    # mapa): quem desce de um vale de terracos tem de aterrar num vale de
    # terracos, ou o mapa mente na transicao.
    ("isle-linghe", "Línghé 灵河 — o chao do vale",
     "A wide temperate river valley at night, seen from the ground: terraced "
     "fields stepping down both flanks in long curved shelves, a broad slow "
     "river of pale mist winding through the middle distance, and soft rounded "
     "green-grey hills rising on either side into a dark sky. Fireflies of pale "
     "jade light drift low over the terraces. NOTHING IS BUILT: no house, no "
     "pagoda, no bridge, no wall, no gate, no lantern, no stall, no path "
     "paving. NO PEOPLE and NO ANIMALS. The middle of the frame is the calmest "
     "and most open part of the valley floor. It is a DARK image overall — the "
     "green is deep and desaturated, the light is a thin warm glow low on the "
     "horizon — because bright painted structures will be composited on top."),
    ("isle-qianhe", "Qiānhé 千河 — o chao do gelo",
     "A high frozen mountain basin at night, seen from the ground: sheer "
     "blue-black ice walls on both sides, a floor of cracked glacier and "
     "wind-scoured rock, frozen waterfalls hanging still against the cliffs, "
     "and a thin freezing mist crawling across the ground. Cold starlight "
     "catches the ice edges. NOTHING IS BUILT: no house, no tower, no bridge, "
     "no wall, no gate, no lantern, no stairs. NO PEOPLE and NO ANIMALS. The "
     "middle of the frame is the calmest and most open part of the basin. It is "
     "a DARK image — the cold comes from the MATERIAL (ice, stone, snow) and "
     "the ground itself stays near-black."),
    ("isle-yanshan", "Yǎnshān 燕山 — o chao das flores",
     "A range of rounded flowering hills at night, seen from the ground: "
     "ancient cherry trees in heavy bloom standing in loose groves, a carpet of "
     "fallen petals over dark grass, a shallow stream threading between the "
     "hills, and slow drifting petal-fall through the air. The blossom is deep "
     "dusty rose, not pink neon, lit only by a low warm glow. NOTHING IS BUILT: "
     "no house, no shrine, no pavilion, no bridge, no wall, no gate, no "
     "lantern, no fence. NO PEOPLE and NO ANIMALS. The middle of the frame is "
     "the calmest and most open part of the ground. It is a DARK image."),
    ("isle-fenghuo", "Fēnghuǒ 烽火 — o chao da lava",
     "A volcanic plain at night, seen from the ground: cracked black basalt "
     "underfoot with thin seams of ember-orange glowing along the fractures, "
     "jagged cinder ridges in the middle distance, a great smoking cone far "
     "behind them, and columns of ash and heat-haze rising through the frame. "
     "NOTHING IS BUILT: no forge, no furnace, no house, no bridge, no wall, no "
     "gate, no lantern, no anvil. NO PEOPLE and NO ANIMALS. The middle of the "
     "frame is the calmest and most open part of the plain. It is a DARK image "
     "— the fire lives in thin cracks, never in broad bright areas."),
    ("isle-moyu", "Mòyǔ 墨雨 — o chao da tinta",
     "A blighted shattered land at night, seen from the ground: broken black "
     "rock split into leaning slabs, a fine dark rain falling like spilled ink, "
     "pools of still black water between the slabs, and a low corrupt haze "
     "clinging to everything. A very few deep cinnabar-red points glow far off "
     "in the murk. NOTHING IS BUILT: no ruin with walls, no house, no tower, no "
     "bridge, no gate, no lantern, no stairs. NO PEOPLE and NO ANIMALS. The "
     "middle of the frame is the calmest and most open part of the ground. It "
     "is the DARKEST of the five — almost monochrome black and ink-grey."),
]

# ── 門 AS PORTAS DA CAVERNA (5) ──────────────────────────────────────────────
# Uma por destino do grupo `hub_caverna` do `HUB_DEFS` — cinco destinos, cinco
# portas, zero orfaos (V5 §3.4). O nome do ficheiro carrega o HUB no meio
# (`door-caverna-forja`) porque a mesma palavra vai repetir-se noutros hubs e um
# `door-forja` global colidiria no dia em que a Praca tivesse uma.
#
# ⚠️ A do MERCADO e' uma PASSAGEM, nao uma banca — e isso e' desenho, nao
# preguica: o mercado nao vive na sua caverna. A porta e' a SAIDA para onde a
# coisa vive, e uma banca de feira dentro de uma gruta seria a cena a mentir
# (regua #4 da linguagem visual).
HUB_DOORS = [
    ("door-caverna-salao", "O Salao 洞府",
     "A single raised circular meditation dais of fitted dark stone, three "
     "shallow steps leading up to its front, a low carved stone rail curving "
     "around its far edge, and a shallow round basin cut into its centre with a "
     "faint blue-white glimmer of qi resting in it. Two small stone lamps burn "
     "low at the front corners. The dais is EMPTY — nobody sits on it."),
    ("door-caverna-forja", "A Forja",
     "A small cultivator's forge built of blackened fieldstone: a squat domed "
     "furnace whose open mouth glows deep ember-orange, a leather bellows "
     "lashed to its flank, and a scarred anvil-stone standing in front of it "
     "with a hammer left resting on top. A few tongs hang from an iron bar. No "
     "smith and nobody in the frame."),
    ("door-caverna-anel", "O Anel Espacial",
     "A storage alcove hewn into rock: heavy stone shelves holding sealed "
     "ceramic jars, bound wooden chests, rolled bundles of cloth and a stack of "
     "folded robes, with one small oil lamp burning on the middle shelf and "
     "warming everything around it. Orderly, full, and unattended."),
    ("door-caverna-estabulo", "O Estabulo",
     "A small stone pen for a spirit beast: a low wall of stacked rough rock, a "
     "gate of lashed bamboo standing open, a thick bed of dry straw inside, a "
     "woven feed basket hanging from a hook and a shallow water trough cut from "
     "stone. It is EMPTY — no animal and no people."),
    ("door-caverna-mercado", "O Mercado",
     "An archway cut clean through a rock wall and framed with dressed stone "
     "blocks, opening on warm distant lamplight and a suggestion of a street "
     "beyond — the way OUT, toward a town. One red paper lantern hangs from an "
     "iron hook above the keystone. The archway is empty: nobody standing in "
     "it, and no stall, no goods and no counter anywhere."),

    # ── 門 AS SEIS PORTAS DO CONTINENTE (2026-09-15, ordem do owner) ─────────
    # Owner, 14/09: *"quando abrir tem la' os icones das coisas do que fazer
    # como dungeons etc explorer nao em menu e sim naquele estilo"*.
    #
    # ⚠️ SEIS pecas e nao trinta, e a razao esta' escrita na V7 antes de se
    # desenhar um pixel: as seis portas sao as MESMAS nos cinco continentes — o
    # que muda entre eles e' o TERRITORIO, nao a lista de coisas a fazer. Trinta
    # pecas seriam cinco vezes a mesma decisao, cinco vezes o custo, e cinco
    # oportunidades de divergirem.
    #
    # ⚠️ O slug leva a CHAVE DO DESTINO (`explore`, `plaza`, `sect`,
    # `dungeons`, `caravan`, `chronicle`) e nao uma palavra portuguesa: e' assim
    # que o cliente a deriva mecanicamente (`door-mundo-<key>.webp`) e a guarda
    # da §16h consegue exigir ficheiro para CADA sitio. Um mapa a' mao aqui
    # divergia no primeiro rename.
    #
    # ⚠️ Nenhuma delas pode ser a `door-caverna-mercado` outra vez: essa ja' e'
    # um arco de pedra com lanterna vermelha a abrir para uma rua. A Praca tem
    # de ser outra coisa (um paifang), senao o jogador ve' a mesma porta em dois
    # sitios que nao sao o mesmo sitio.
    ("door-mundo-explore", "Explorar 探",
     "A wayfarer's trailhead at the mouth of a wilderness path: two leaning "
     "weathered stone pillars, a frayed rope strung between their tops with a "
     "few narrow cloth prayer-strips hanging from it, and a single small "
     "storm-lantern hooked on the left pillar. Between the pillars a worn "
     "footpath of loose stone climbs two or three steps and is swallowed by "
     "darkness. Nobody on the path."),
    ("door-mundo-plaza", "A Praca 坊",
     "A free-standing ceremonial town archway (a paifang) of dark timber and "
     "stone: four posts, a tiled upturned roof over the central span, and two "
     "red paper lanterns hanging under it, burning. The central plaque and "
     "every panel are BLANK. Through the span there is only warm distant "
     "lamplight. No stalls, no goods, no cart, no street furniture."),
    ("door-mundo-sect", "A Seita 山門",
     "The mountain gate of a cultivation sect: a tall gatehouse of grey stone "
     "and dark timber with a steep upturned tiled roof, its double doors "
     "standing open on blackness, a blank stone plaque above the lintel, and a "
     "carved stone guardian lion crouched on a low plinth at each side. Behind "
     "the opening, a flight of worn steps rises and vanishes. Empty."),
    ("door-mundo-dungeons", "Os Portais 秘境",
     "A free-standing doorway of cracked black stone with nothing built around "
     "it — a rectangular portal frame standing alone, its jambs carved with a "
     "continuous ring of worn talismanic notches, one corner of the lintel "
     "broken away. The opening is not empty air: it holds a churning depth of "
     "darkness with a few deep ember-red points burning far inside it. Cold "
     "mineral haze spills over the threshold."),
    ("door-mundo-caravan", "A Caravana 商隊",
     "A merchant's covered wagon at rest: a two-wheeled cart with a ribbed "
     "canopy of oiled cloth, roped crates and bound bales stacked under it, the "
     "shafts lowered to the ground, and an oil lantern hanging from the front "
     "hoop and lit. The canopy and every crate face are BLANK. No animal, no "
     "driver, nobody."),
    ("door-mundo-chronicle", "A Cronica 碑",
     "A single memorial stele of dark polished stone standing upright on a "
     "carved plinth under its own small tiled canopy on four short posts. The "
     "face of the stele is completely BLANK and unmarked — smooth stone, no "
     "carving, no lettering of any kind. A low bronze brazier burns at its foot "
     "and lights it from below; a thread of incense smoke rises past it."),
]

# ── 州 OS CINCO CONTINENTES (5) ──────────────────────────────────────────────
# 🔴 E AQUI ESTA' A CORRECCAO QUE DESTRANCOU ESTE LOTE (2026-09-13).
#
# O pendente escrito a 11/09 dizia: *"o hub do Mundo tem NOVE destinos, e nove
# portas numa pintura de 358px e' uma sopa"*. Servido e OLHADO a 390x844, o
# `HubMundoScreen` desenha **CINCO** elipses, nao nove. O nove era o
# `HUB_DEFS.group` — um array de 9 entradas que inclui o proprio landing e as
# abas que se alcancam de DENTRO da tela:
#
#     O CEU (faixa de chips, 4 destinos)  world_boss · leaderboard · faction · guild
#     A ILHA (gaveta, 4 destinos)         explore · plaza · sect · dungeons
#     o landing                           hub_mundo_screen
#     ------------------------------------------------------------------
#     9 entradas no `group`   ·   MAS 5 continentes desenhados
#
# E' a armadilha #4 do lote anterior — *"um assert sobre o repositorio em vez do
# assunto"* — feita em prosa: contou-se o array e nao o ecra. Os quatro do CEU
# **nao pertencem a lugar nenhum** (e' isso que "Ceu" quer dizer) e os quatro da
# ILHA sao **locais de onde voce esta'**, que e' informacao VIVA que uma pintura
# nao pode substituir. Portanto a cena do Mundo tem **cinco portas**, que e'
# exactamente o numero que a Caverna ja' provou caber.
#
# Cada assunto sai do canon que ja' existe: `core/continent_engine.CONTINENT_META`
# (elementos) + as chaves `continent_*_subtitle` / `continent_lore_*` dos
# `locales/`. Nada inventado aqui.
HUB_LANDS = [
    ("land-mundo-linghe", "Línghé 灵河 — o coracao do mundo",
     "A broad temperate highland seen from far above: green terraced ridges "
     "folding around a wide calm river that loops through the middle of it, "
     "standing pools catching a soft even daylight, and a gentle unbroken "
     "drift of pale spirit-mist lying along the valleys. The light on it is "
     "balanced and golden-white, the most harmonious of the five."),
    ("land-mundo-qianhe", "Qiānhé 千河 — a terra dos mil rios",
     "A cold mountain territory seen from far above: sheer grey-blue peaks "
     "capped with ice and snow, a fan of a thousand narrow frozen rivers "
     "cutting down from them and braiding across a dark stone plain, with "
     "sheets of hard pale ice catching a low cold light. Steel-blue and white, "
     "and nothing soft anywhere on it."),
    ("land-mundo-yanshan", "Yǎnshān 燕山 — o jardim das mil flores",
     "A range of gentle rounded mountains seen from far above, entirely "
     "covered in eternal cherry blossom: drifts of pale pink and white over "
     "green slopes, narrow herb terraces stepping down the southern faces, and "
     "petals lifting off the ridges on a visible current of wind. Warm rose "
     "and green, lit as if in late spring afternoon."),
    ("land-mundo-fenghuo", "Fēnghuǒ 烽火 — onde o chao sangra lava",
     "A volcanic territory seen from far above: one great caldera open at its "
     "centre with molten orange rivers running out of it in branching veins "
     "across black basalt, ash plains fading to charcoal at the edges, and a "
     "heavy column of smoke leaning off one side. Ember-orange and near-black, "
     "the only heat among the five."),
    ("land-mundo-moyu", "Mòyǔ 墨雨 — a chuva de tinta",
     "A forbidden territory seen from far above, drowned in perpetual black "
     "rain: jagged dark rock rising out of a stained plain, rivers running the "
     "colour of spilled ink, a sunken crater at its heart where the rain falls "
     "hardest, and a dull cinnabar-red glow bleeding up through the cracks. "
     "Nearly monochrome, wet, and hostile."),
]


ASSETS = os.path.join(ROOT, "miniapp", "newapp", "assets")
# ⚠️ 2026-09-14 — `boss` FALTAVA AQUI e o sintoma foi EXACTAMENTE o que o
# `ARTE_PROVENIENCIA §1.4` ja' registara para os 51 artefactos: as 9 pecas
# copiaram-se para `assets/` e o `sync_index` disse *"indice ja' em dia: 236"*,
# porque filtra por `f.split("-")[0] in KIND_PREFIX.values()` — sem `boss` aqui,
# os nove ficheiros `boss-*.webp` nao eram sequer candidatos. Arte paga, em
# disco, invisivel, e SEM ERRO NENHUM: a carta cai no verso, que e' um estado
# legitimo. Segunda vez que esta lista come um lote inteiro.
KIND_PREFIX = {"technique": "tech", "pill": "pill", "beast": "beast",
               "artifact": "art", "herb": "herb", "formation": "form",
               "boss": "boss"}


def slugify(name):
    """O nome do ficheiro DERIVA do nome do catalogo, mecanicamente.

    ⚠️ Nao ha' tabela de mapeamento a mao, e isso e' desenho: com 307 pecas,
    uma tabela de 307 linhas escrita a' mao diverge do catalogo no primeiro
    rename. O cliente (`ui.js`) faz exactamente a mesma transformacao — se as
    duas discordarem, a carta cai no verso honesto em vez de partir.
    """
    # ⚠️ 2026-09-15 — A DOBRA PARA ASCII, e porque ela custou uma peca.
    # `ch.isalnum()` em Python e' UNICODE: `"ú".isalnum()` e' True. O cliente
    # faz `/[^a-z0-9]+/`, onde `ú` NAO casa e vira traco. As duas metades desta
    # regra discordavam exactamente num caracter, e o comentario acima jurava
    # que concordavam. Medido: `tech-yún-step-reborn.webp` estava em disco e no
    # indice, o cliente pedia `tech-y-n-step-reborn`, e a peca — paga, gerada,
    # aprovada — nunca chegou a um jogador. A 3a vez que esta casa perde arte
    # por UMA ligacao (51 artefactos a 08/09, 229 nomes a 14/09, esta).
    # Dobrar primeiro para ASCII faz `ú`→`u` (legivel) e deixa o 漢字 virar
    # traco nos DOIS lados, que e' o que o cliente ja' fazia.
    folded = unicodedata.normalize("NFKD", name)
    out, prev_dash = [], False
    for ch in folded.lower():
        if ch.isalnum() and ch.isascii():
            out.append(ch)
            prev_dash = False
        elif unicodedata.combining(ch):
            continue                      # o acento solto do NFKD desaparece
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-")


# ⚠️ Duas familias nomeiam pelo SLUG, nao pelo nome do catalogo, e cada uma por
# uma razao propria:
#
#  `realm`      — o nome ("Qi Condensation") daria `realm-qi-condensation.webp`,
#                 mas o `REALM_ART_FILES` do `ui.js` ja' aponta para
#                 `realm-qi.webp`. O slug e' que carrega a correspondencia.
#                 ⚠️⚠️ E leva SUFIXO `-v2`: a rota `assets` serve com
#                 `max-age=31536000, immutable`, logo trocar o corpo por baixo de
#                 um nome ja' servido deixaria os 248 com a imagem VELHA em cache
#                 para sempre (ARTE_PROVENIENCIA §2.5 — "regenerar = ficheiro
#                 NOVO"). O ficheiro velho fica no disco; o indice e' que muda.
#  `cultivator` — o nome ja' comeca por "Cultivator", e o prefixo da familia
#                 duplicava-o (`cultivator-cultivator-male.webp`).
# ⚠️ O sufixo do reino NAO pode ser "-v2": o `--seed N` ja' grava as tentativas
# como `<slug>-v2.webp`, `<slug>-v3.webp` em `tmp/art/`, e o `approve` escolhe a
# tentativa mais recente por ordem alfabetica. Com "-v2" nos dois lados, o nome
# APROVADO e o nome de uma TENTATIVA passavam a ser a mesma string — e uma
# segunda tentativa de um reino ja' aprovado sobrescrevia-o em silencio.
# `-place` nao colide com nada e ainda diz o que mudou: o reino virou LUGAR.
#  `place`/`door` — o slug JA' e' o nome (`hub-caverna`, `door-caverna-forja`).
#                 A cena leva `-scene` para nunca colidir com o `-v2`/`-v3` das
#                 tentativas em `tmp/art/` (a mesma armadilha que deu o `-place`
#                 aos reinos); a porta ja' tem prefixo proprio e nao precisa.
_SLUG_NAMED = {"realm": "-place", "cultivator": "",
               "place": "-scene", "door": "", "land": ""}


def asset_name(piece):
    if piece["kind"] in _SLUG_NAMED:
        return "%s%s.webp" % (piece["slug"], _SLUG_NAMED[piece["kind"]])
    return "%s-%s.webp" % (KIND_PREFIX.get(piece["kind"], piece["kind"]),
                           slugify(piece["name"]))


def approve(slugs, catalogo=None):
    """Move uma peca revista de `tmp/art/` para o jogo.

    ⚠️ Passo SEPARADO da geracao, de proposito. Gerar e' barato e automatico;
    entrar no jogo exige que alguem tenha OLHADO. E cada peca aprovada imprime a
    linha de proveniencia para colar em `GameDesign/ARTE_PROVENIENCIA.md §1.2` —
    peca sem linha nao entra.
    """
    import shutil
    from datetime import date
    by_slug = {p["slug"]: p for p in (catalogo or PILOT)}
    linhas = []
    for slug in slugs:
        p = by_slug.get(slug)
        if not p:
            print("  ?? slug desconhecido: %s" % slug)
            continue
        # A tentativa mais recente ganha (`-v2`, `-v3`, ...).
        # ⚠️ Por MTIME, nao por ordem alfabetica: alfabeticamente `-v10` vem
        # antes de `-v2`, e a partir da 10a tentativa a peca aprovada seria a
        # errada, sem erro nenhum. E `startswith(slug)` apanharia
        # `realm-core-formation` ao pedir `realm-core` — exige-se o slug exacto
        # ou o slug seguido de `-v<numero>`.
        import re as _re
        _pat = _re.compile(r"^" + _re.escape(slug) + r"(-v\d+)?\.webp$")
        cands = [f for f in os.listdir(OUT_DIR) if _pat.match(f)]
        cands.sort(key=lambda f: os.path.getmtime(os.path.join(OUT_DIR, f)))
        if not cands:
            print("  !! sem .webp gerado para %s" % slug)
            continue
        src = os.path.join(OUT_DIR, cands[-1])
        dest = os.path.join(ASSETS, asset_name(p))
        shutil.copyfile(src, dest)
        kb = os.path.getsize(dest) / 1024
        print("  ok %-34s <- %-32s %.0f KB" % (asset_name(p), cands[-1], kb))
        linhas.append("| `%s` | %s | Google | %s | %s | tier pago (standard) | §3.3 %s |"
                      % (asset_name(p), p["name"], MODEL, date.today().isoformat(), slug))
    sync_index()
    if linhas:
        print("\n  --- colar em ARTE_PROVENIENCIA.md §1.2 ---")
        for l in linhas:
            print("  " + l)
    return 0


def sync_index():
    """Reescreve o `NIV_ART_INDEX` do `ui.js` a partir do que esta' EM DISCO.

    ⚠️ Passo automatico de proposito. O indice existe para uma peca sem arte nao
    pedir um URL que da' 404 — mas se ele ficar por actualizar a' mao, a arte
    PAGA fica invisivel e a carta cai no verso **em silencio**: ninguem ve um
    erro, so' se ve uma carta virada para baixo, que e' um estado legitimo. Um
    passo manual que falha em silencio nao sobrevive a 307 pecas.
    (Ha' guarda na suite que compara o indice com o disco nos dois sentidos.)
    """
    ui = os.path.join(ROOT, "miniapp", "components", "ui.js")
    slugs = sorted(f[:-5] for f in os.listdir(ASSETS)
                   if f.endswith(".webp")
                   and f.split("-")[0] in set(KIND_PREFIX.values()))
    linhas, cur = [], []
    for s in slugs:                       # ~4 por linha, para o diff ficar legivel
        cur.append('"%s"' % s)
        if len(cur) == 3:
            linhas.append("      " + ", ".join(cur) + ",")
            cur = []
    if cur:
        linhas.append("      " + ", ".join(cur) + ",")
    novo = "var NIV_ART_INDEX = new Set([\n" + "\n".join(linhas) + "\n    ]);"
    src = io.open(ui, encoding="utf-8").read()
    ini = src.index("var NIV_ART_INDEX = new Set([")
    fim = src.index("]);", ini) + 3
    if src[ini:fim] == novo:
        print("  (indice ja' em dia: %d peças)" % len(slugs))
        return
    io.open(ui, "w", encoding="utf-8", newline="").write(src[:ini] + novo + src[fim:])
    print("  indice do ui.js actualizado: %d peças" % len(slugs))


def api_key():
    env = os.path.join(ROOT, ".env")
    key = os.environ.get("NV_IMAGE_API_KEY")
    if not key and os.path.isfile(env):
        for ln in io.open(env, encoding="utf-8"):
            if ln.startswith("NV_IMAGE_API_KEY="):
                key = ln.split("=", 1)[1].strip()
                break
    if not key:
        sys.exit("NV_IMAGE_API_KEY ausente (.env ou ambiente). "
                 "⚠️ Nao gerar sem chave: o tier gratis nao concede uso comercial.")
    return key


def build_prompt(piece, seed=1):
    extra = "" if seed == 1 else (" Vary the staging and camera angle from previous "
                                  "attempts while keeping the same subject and mood.")
    hint = KIND_HINT.get(piece["kind"], "")
    framing = FRAMING_BY_KIND.get(piece["kind"], FRAMING)
    return "%s\n\n%s %s\n\n%s%s" % (STYLE, piece["subject"], hint, framing, extra)


def generate(piece, key, seed=1):
    body = {
        "contents": [{"parts": [{"text": build_prompt(piece, seed)}]}],
        "generationConfig": {"responseModalities": ["IMAGE"],
                             "imageConfig": {"aspectRatio":
                                             ASPECT_BY_KIND.get(piece["kind"], "4:3")}},
    }
    req = urllib.request.Request(
        ENDPOINT % MODEL, data=json.dumps(body).encode(),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    raw, mime, refusal = None, None, None
    for p in d.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in p:
            raw = base64.b64decode(p["inlineData"]["data"])
            mime = p["inlineData"]["mimeType"]
        elif "text" in p:
            refusal = p["text"]
    tokens = d.get("usageMetadata", {}).get("totalTokenCount", 0)
    return raw, mime, refusal, time.time() - t0, tokens


def to_webp(raw, dest, quality=88):
    """WebP porque a rota `assets` serve `.webp` e porque a carta o quer leve.
    ⚠️ Guarda-se TAMBEM o original: reconverter de um webp ja' comprimido perde
    duas vezes, e a peca aprovada pode precisar de outro corte amanha."""
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.save(dest, "WEBP", quality=quality, method=6)
    return os.path.getsize(dest), im.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="gerar so' esta peca (slug)")
    ap.add_argument("--seed", type=int, default=1, help="numero da tentativa")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--family", help="beast|pill|technique — deriva os assuntos do CATALOGO")
    ap.add_argument("--limit", type=int, help="so as N primeiras (para provar antes de escalar)")
    ap.add_argument("--redo", action="store_true",
                    help="refazer mesmo o que ja tem .webp no jogo (por defeito salta)")
    ap.add_argument("--approve", help="slugs separados por virgula: copia de "
                                      "tmp/art/ para o jogo e imprime a proveniencia")
    a = ap.parse_args()

    if a.list:
        for p in (catalog_pieces(a.family) if a.family else PILOT):
            print("%-30s %-10s %-34s %s"
                  % (p["slug"], p["kind"], asset_name(p), p["note"]))
        return 0

    if a.approve:
        return approve([x.strip() for x in a.approve.split(",") if x.strip()],
                       catalog_pieces(a.family) if a.family else PILOT)

    catalogo = catalog_pieces(a.family) if a.family else PILOT
    pieces = [p for p in catalogo if not a.only or p["slug"] == a.only]
    if not pieces:
        sys.exit("slug desconhecido: %s (use --list)" % a.only)
    # ⚠️ Por defeito NAO se refaz o que ja' esta' no jogo: a arte aprovada e' um
    # facto revisto por uma pessoa, e regerar por cima apagava a revisao. `--redo`
    # e' explicito de proposito.
    if not a.redo:
        antes = len(pieces)
        pieces = [p for p in pieces
                  if not os.path.isfile(os.path.join(ASSETS, asset_name(p)))]
        if antes != len(pieces):
            print("(saltadas %d ja' no jogo; --redo para refazer)" % (antes - len(pieces)))
    if a.limit:
        pieces = pieces[:a.limit]
    if not pieces:
        print("nada a fazer — tudo ja' tem arte.")
        return 0

    key = api_key()
    os.makedirs(OUT_DIR, exist_ok=True)
    total_tokens, feitas, falhas = 0, [], []

    for i, p in enumerate(pieces, 1):
        print("[%d/%d] %s ..." % (i, len(pieces), p["slug"]), end=" ", flush=True)
        try:
            raw, mime, refusal, secs, tokens = generate(p, key, a.seed)
        except urllib.error.HTTPError as e:
            print("HTTP %s\n   %s" % (e.code, e.read().decode()[:300]))
            falhas.append(p["slug"])
            continue
        except Exception as e:
            print("ERRO %s: %s" % (type(e).__name__, e))
            falhas.append(p["slug"])
            continue
        total_tokens += tokens
        if not raw:
            print("SEM IMAGEM — %s" % (refusal or "resposta vazia")[:160])
            falhas.append(p["slug"])
            continue
        suf = "" if a.seed == 1 else "-v%d" % a.seed
        base = os.path.join(OUT_DIR, p["slug"] + suf)
        ext = ".jpg" if "jpeg" in (mime or "") else ".png"
        io.open(base + ext, "wb").write(raw)
        size, dim = to_webp(raw, base + ".webp")
        print("ok %.1fs · %dx%d · webp %.0f KB" % (secs, dim[0], dim[1], size / 1024))
        feitas.append(p["slug"])

    print("\n%d feitas · %d falhas · ~%d tokens · custo estimado ~$%.2f"
          % (len(feitas), len(falhas), total_tokens, len(feitas) * 0.067))
    print("gravado em tmp/art/ — ⚠️ NADA entra no jogo antes de o owner ver "
          "e de a peca ganhar linha em GameDesign/ARTE_PROVENIENCIA.md §1.2")
    if falhas:
        print("falharam: " + ", ".join(falhas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
