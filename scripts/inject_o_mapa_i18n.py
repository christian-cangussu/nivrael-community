# -*- coding: utf-8 -*-
"""圖 O MAPA — as 3 chaves novas, x3 linguas.

Porque existe um script em vez de tres edicoes a mao: o `pt.json` tem 3768
chaves e o `json.dump` por omissao reescreve o ficheiro inteiro com outra
indentacao — as chaves novas ficavam enterradas num diff de 22.590 linhas e
ninguem as revia. `indent=4` + `newline="\\n"` + `ensure_ascii=False` sao os
mesmos do `inject_item_vivo_i18n.py`, e mantem o diff em 4 linhas por ficheiro.

As TRES chaves:
  `feature_o_mapa`         — o rotulo no painel do owner
  `feature_o_mapa_desc`    — a descricao (ha guarda que falha sem as duas)
  `mapa_porta_apagada`     — o SUFIXO do `aria-label` de uma porta apagada

⚠️ A terceira nao e enfeite e nao se podia reaproveitar de nenhuma existente:
um leitor de ecra nao ve o cinzento. Sem ela, uma porta acesa e uma apagada
anunciam-se exactamente da mesma maneira, e a unica coisa que a cena diz sobre
o estado do lugar fica invisivel para quem mais precisa dela.

⚠️ A descricao cobre a flag INTEIRA, incluindo as duas coisas que o owner
precisa de saber ANTES de ligar o switch: que ela **exige a `ui_v2`** (sem isso
ligar esta nao muda um pixel e a flag parece avariada) e que **e 1 de 4 cenas**,
com as outras tres declaradas pendentes. O painel e a unica coisa que ele le
antes de ligar (Lei §6).

⚠️ `pt.json` e portugues BRASILEIRO (decisao do owner). Nada de "continua a
mostrar" nem de "artefacto".
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

KEYS = {
    "pt": {
        "feature_o_mapa": "圖 O Mapa (a tela de hub vira um lugar)",
        "mapa_porta_apagada": "apagado, à espera",
        "feature_o_mapa_desc": (
            "A tela de hub deixa de ser uma LISTA e passa a ser um LUGAR pintado com "
            "portas em que você toca. Isso não é \"colocar uma imagem de fundo no hub\": "
            "é trocar o mecanismo de navegação, que foi a ordem do owner (08/09: \"To "
            "pensando em um HUB completo com imagem e a pessoa clica no templo ou o que "
            "seja. E nao esses menus louco onde tem que buscar de um lado ao outro\"). "
            "O que existia antes: a antessala da Caverna desenhava cinco elipses de CSS, "
            "cada uma com um emoji de 28px no meio — nenhum pixel de ilustração — e tocar "
            "abria uma sanfona que revelava OUTRO botão (\"Entrar\"): dois toques para "
            "chegar onde um bastava. Agora é uma pintura da caverna com cinco construções "
            "desenhadas em cima dela, e um toque leva direto ao destino. "
            "COMO É FEITO: em camadas separadas. O fundo é só atmosfera (rocha, névoa, "
            "luz) e cada porta é a sua própria peça de arte. Isso importa porque regerar "
            "uma arte no Nivrael sempre cria um arquivo novo — se o desenho das portas "
            "morasse dentro da pintura e a posição delas morasse no código, no dia em que "
            "a arte mudasse o mapa passaria a apontar para o lugar errado sem nenhum teste "
            "reclamar. Separadas, o alinhamento é do código, uma porta nova não obriga a "
            "refazer a cena, e cada porta pode ACENDER ou APAGAR sem repintar nada. "
            "A HONESTIDADE: uma porta apagada continua sendo uma porta. O Salão de quem "
            "ainda não estabeleceu a caverna aparece escuro e diz \"à espera\" — mas o "
            "toque continua lá, levando à tela onde ele pode estabelecê-la. Um lugar vazio "
            "esperando, nunca um lugar que sumiu (a mesma resposta que os 11 reinos "
            "receberam). Nenhum destino fica órfão: os 5 destinos do grupo Caverna têm 5 "
            "portas, e existe um teste que fica vermelho no dia em que nascer um destino "
            "sem porta. Cada porta é um botão de verdade, com nome para leitor de tela, "
            "alcançável pelo Tab e com foco visível. "
            "⚠️ ESTA CHAVE EXIGE \"O Pergaminho Vivo\" (ui_v2) LIGADA — as telas de hub só "
            "existem lá. Ligar só esta não muda nada na tela. "
            "⚠️ É 1 DE 4 CENAS: só a Caverna foi desenhada. O Eu, o Mundo e o Pergaminho "
            "continuam com a tela de hoje e estão marcados como pendentes (a do Mundo "
            "ainda precisa decidir como nove destinos cabem numa pintura de 358px). O "
            "Combate não leva cena por decisão: ele tem um destino só, e uma cena com uma "
            "porta só é uma porta com moldura. "
            "Sem migration e sem estado no jogador: desligar devolve exatamente a tela de "
            "hoje, byte a byte."
        ),
    },
    "en": {
        "feature_o_mapa": "圖 The Map (a hub screen becomes a place)",
        "mapa_porta_apagada": "unlit, waiting",
        "feature_o_mapa_desc": (
            "A hub screen stops being a LIST and becomes a painted PLACE with doors you "
            "touch. This is not \"putting a background image on the hub\": it swaps the "
            "navigation mechanism, which is what the owner asked for (08/09: \"I'm "
            "thinking of a full HUB with an image where the person clicks the temple or "
            "whatever. Not these crazy menus where you have to hunt from one side to the "
            "other\"). "
            "What was there before: the Cavern antechamber drew five CSS ellipses, each "
            "with a 28px emoji in the middle — not one pixel of illustration — and tapping "
            "opened an accordion that revealed ANOTHER button (\"Enter\"): two taps to "
            "reach what one should reach. Now it is a painting of the cavern with five "
            "structures drawn on top of it, and one tap goes straight to the destination. "
            "HOW IT IS BUILT: in separate layers. The background is atmosphere only (rock, "
            "mist, light) and each door is its own art piece. That matters because "
            "regenerating art in Nivrael always writes a NEW file — if the doors were "
            "painted into the background while their positions lived in code, the day the "
            "art changed the map would start pointing at the wrong places with no test "
            "complaining. Separated, alignment belongs to the code, a new door does not "
            "force a repaint of the scene, and each door can be LIT or UNLIT without "
            "repainting anything. "
            "THE HONESTY: an unlit door is still a door. The Hall of someone who has not "
            "established a cavern yet shows dark and says \"waiting\" — but the tap is "
            "still there, leading to the screen where they can establish it. An empty "
            "place waiting, never a place that vanished (the same answer the 11 realms "
            "got). No destination is orphaned: the 5 destinations of the Cavern group have "
            "5 doors, and a test goes red the day a destination is born without one. Every "
            "door is a real button, named for screen readers, Tab-reachable, with a "
            "visible focus ring. "
            "⚠️ THIS FLAG REQUIRES \"The Living Scroll\" (ui_v2) TO BE ON — hub screens "
            "only exist there. Turning on only this one changes nothing on screen. "
            "⚠️ IT IS 1 OF 4 SCENES: only the Cavern is drawn. Self, World and Scroll keep "
            "today's screen and are declared pending (the World one still has to decide "
            "how nine destinations fit in a 358px painting). Combat gets no scene by "
            "decision: it has a single destination, and a scene with one door is a door "
            "with a frame. "
            "No migration and no player state: turning it off returns exactly today's "
            "screen, byte for byte."
        ),
    },
    "es": {
        "feature_o_mapa": "圖 El Mapa (la pantalla de hub se vuelve un lugar)",
        "mapa_porta_apagada": "apagado, esperando",
        "feature_o_mapa_desc": (
            "La pantalla de hub deja de ser una LISTA y pasa a ser un LUGAR pintado con "
            "puertas que se tocan. Esto no es \"poner una imagen de fondo en el hub\": "
            "cambia el mecanismo de navegación, que fue la orden del owner (08/09: "
            "\"Estoy pensando en un HUB completo con imagen donde la persona hace clic en "
            "el templo o lo que sea. Y no esos menús locos donde hay que buscar de un lado "
            "a otro\"). "
            "Lo que había antes: la antesala de la Caverna dibujaba cinco elipses de CSS, "
            "cada una con un emoji de 28px en el medio — ni un píxel de ilustración — y "
            "tocar abría un acordeón que revelaba OTRO botón (\"Entrar\"): dos toques para "
            "llegar donde bastaba uno. Ahora es una pintura de la caverna con cinco "
            "construcciones dibujadas encima, y un toque lleva directo al destino. "
            "CÓMO ESTÁ HECHO: en capas separadas. El fondo es solo atmósfera (roca, "
            "niebla, luz) y cada puerta es su propia pieza de arte. Importa porque "
            "regenerar arte en Nivrael siempre escribe un archivo NUEVO — si las puertas "
            "estuvieran pintadas dentro del fondo y su posición viviera en el código, el "
            "día que el arte cambiara el mapa apuntaría al lugar equivocado sin que ningún "
            "test se quejara. Separadas, la alineación es del código, una puerta nueva no "
            "obliga a rehacer la escena, y cada puerta puede ENCENDERSE o APAGARSE sin "
            "repintar nada. "
            "LA HONESTIDAD: una puerta apagada sigue siendo una puerta. El Salón de quien "
            "todavía no estableció su caverna aparece oscuro y dice \"esperando\" — pero el "
            "toque sigue ahí, llevando a la pantalla donde puede establecerla. Un lugar "
            "vacío esperando, nunca un lugar que desapareció (la misma respuesta que "
            "recibieron los 11 reinos). Ningún destino queda huérfano: los 5 destinos del "
            "grupo Caverna tienen 5 puertas, y hay un test que se pone rojo el día que "
            "nazca un destino sin puerta. Cada puerta es un botón de verdad, con nombre "
            "para lector de pantalla, alcanzable con Tab y con foco visible. "
            "⚠️ ESTA OPCIÓN EXIGE \"El Pergamino Vivo\" (ui_v2) ENCENDIDA — las pantallas "
            "de hub solo existen ahí. Encender solo esta no cambia nada en pantalla. "
            "⚠️ ES 1 DE 4 ESCENAS: solo la Caverna está dibujada. El Yo, el Mundo y el "
            "Pergamino siguen con la pantalla de hoy y están declarados pendientes (la del "
            "Mundo todavía tiene que decidir cómo caben nueve destinos en una pintura de "
            "358px). El Combate no lleva escena por decisión: tiene un solo destino, y una "
            "escena con una sola puerta es una puerta con marco. "
            "Sin migración y sin estado en el jugador: apagarla devuelve exactamente la "
            "pantalla de hoy, byte a byte."
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
