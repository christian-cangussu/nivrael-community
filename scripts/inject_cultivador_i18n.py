# -*- coding: utf-8 -*-
"""坐 O CULTIVADOR — as strings novas do lote (2026-09-07).

Idempotente. Escreve nos DOIS lados, e cada um pelo seu motivo:

* `locales/*`      — o menu do genero vive no hub `/conf` do CHAT (regra da
                     casa: toda preferencia do jogador vive la', nunca num
                     comando avulso).
* `miniapp/i18n/*` — o rotulo e a descricao da flag `cultivador` no painel do
                     owner (ha' verificador que falha se uma flag do catalogo
                     aparecer sem rotulo OU sem descricao nas tres linguas).

⚠️ "Ainda nao escolhi" e' uma opcao de PRIMEIRA CLASSE, nao a ausencia de
resposta: os ~248 jogadores do beta nascem com `gender` NULL e o jogo desenha-os
com o 背影 (a figura de costas). Por isso ela tem nome proprio nas tres linguas,
em vez de ser um "-" ou um vazio.

⚠️ Nenhuma destas strings promete que o genero faz alguma coisa mecanica. Ele e'
COSMETICO (Lei §4): escolhe QUAL figura se senta na cena do Cultivo. Em
particular NAO toca no casamento (`dao_partners`), que existe desde antes e
continua gender-free por desenho — prometer o contrario aqui seria a tela a
mentir sobre o motor.
"""
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ("pt", "en", "es")

# ── 1. o menu do genero, no chat ─────────────────────────────────────────────
CHAT = {
    "pt": {
        "btn_settings_gender": "⚊ Forma do Cultivador",
        "gender_title": "*Forma do Cultivador*",
        "gender_current": "Agora: *{value}*",
        "gender_hint": ("Escolhe qual figura se senta na sua cena de Cultivo. "
                        "É apenas aparência — não muda nenhum número, nenhum "
                        "requisito e nenhum parceiro de Dao."),
        "gender_male": "Masculino",
        "gender_female": "Feminino",
        "gender_unset": "Não escolhido",
        "gender_saved": "Forma registrada.",
    },
    "en": {
        "btn_settings_gender": "⚊ Cultivator's Form",
        "gender_title": "*Cultivator's Form*",
        "gender_current": "Now: *{value}*",
        "gender_hint": ("Chooses which figure sits in your Cultivation scene. "
                        "Appearance only — it changes no number, no requirement "
                        "and no Dao partner."),
        "gender_male": "Male",
        "gender_female": "Female",
        "gender_unset": "Not chosen",
        "gender_saved": "Form recorded.",
    },
    "es": {
        "btn_settings_gender": "⚊ Forma del Cultivador",
        "gender_title": "*Forma del Cultivador*",
        "gender_current": "Ahora: *{value}*",
        "gender_hint": ("Elige qué figura se sienta en tu escena de Cultivo. "
                        "Solo apariencia — no cambia ningún número, ningún "
                        "requisito ni ninguna pareja de Dao."),
        "gender_male": "Masculino",
        "gender_female": "Femenino",
        "gender_unset": "Sin elegir",
        "gender_saved": "Forma registrada.",
    },
}

# ── 2. a flag no painel do owner ─────────────────────────────────────────────
_D_PT = (
    "坐 O CULTIVADOR. Ordem do owner (2026-09-07, textual): \"esse orb nao "
    "gostei nada, muito AI. etc. usamos uma imagem e criamos efeito nela tipo de "
    "um cultivador\" · \"as imagens relacionada aos reinos mudar. eu fiz ela de "
    "teste mesmo, porem deveriam ser realmente relacionada a nivrael\". "
    "TRÊS coisas, uma chave. (1) O ORBE MORRE. A cena do Cultivo mostrava uma "
    "esfera de gradiente puro com um ✦ no centro — e o ✦ é literalmente o glifo "
    "que virou o ícone universal de \"gerado por IA\" desde 2023; fora da "
    "meditação o centro era pior, um EMOJI DO SISTEMA (🔮), que muda de forma "
    "de aparelho para aparelho. Era a única peça do jogo feita inteiramente de "
    "gradiente, depois de dois lotes a tirá-los. No lugar entra um CULTIVADOR "
    "ILUSTRADO sentado, e o efeito (respiração, anéis, partículas de qi) passa a "
    "ser aplicado NELE — que é literalmente o que o owner pediu. (2) OS ONZE "
    "REINOS VIRAM LUGARES VAZIOS. As antigas eram enfeite de landing "
    "reaproveitado (palavras do próprio owner) e tinham PESSOAS lá dentro a "
    "fazer coisas diferentes: um viajante DE PÉ, um cultivador a LEVITAR, um "
    "COMBATE, um homem a VOAR. Foi por isso que a cena nunca pôde legendar a "
    "imagem — cinco das onze desmentiriam a frase \"você está sentado\". Com o "
    "lugar vazio, a camada de cima pode ser o JOGADOR sem que a de baixo o "
    "contradiga: o reino diz ONDE, a figura diz QUEM, o efeito diz O QUÊ. "
    "(3) A FIGURA SÓ APARECE SENTADA. De pé, o círculo mostra o assento vazio e "
    "o lugar à espera — porque a legenda diz \"você não está sentado\" e a tela "
    "não pode contradizer-se. Sentar-se passa a ser o momento em que você "
    "APARECE no mundo. O género (Migration 140) escolhe qual figura; NULL é "
    "estado legítimo (os jogadores do beta) e tem figura própria, 背影, de "
    "costas. NADA é bloqueado por género — em particular o casamento, que "
    "continua gender-free. Ortogonal a `cartas` e a `cena_cultivo`; com esta "
    "chave desligada a cena rende exactamente o orbe de hoje."
)
_D_EN = (
    "坐 THE CULTIVATOR. Owner's order (2026-09-07): the orb had to go — the ✦ at "
    "its centre is literally the glyph the whole industry uses to mean \"AI "
    "generated\", and outside meditation the centre was a SYSTEM EMOJI that "
    "changes shape from device to device. It was the only piece of the game made "
    "entirely of gradient, after two batches spent removing them. In its place "
    "sits an ILLUSTRATED CULTIVATOR, and the effect (breathing, rings, rising qi) "
    "is applied to the FIGURE. The eleven realm images become EMPTY PLACES: the "
    "old ones were repurposed landing-page decoration with PEOPLE inside doing "
    "different things (one standing, one levitating, one fighting, one flying) — "
    "which is why the scene could never caption the image, since five of eleven "
    "would contradict the line \"you are seated\". With the place empty, the "
    "upper layer can be the PLAYER without the lower one contradicting it: the "
    "realm says WHERE, the figure says WHO, the effect says WHAT. The figure only "
    "appears while SEATED — standing, the circle shows the empty seat and the "
    "place waiting, because the caption says \"you are not seated\" and the "
    "screen may not contradict itself. Gender (Migration 140) picks which figure; "
    "NULL is a legitimate state (the beta players) with its own figure, 背影, seen "
    "from behind. NOTHING is gated on gender — marriage in particular stays "
    "gender-free. Orthogonal to `cartas` and `cena_cultivo`; with this switch off "
    "the scene renders exactly today's orb."
)
_D_ES = (
    "坐 EL CULTIVADOR. Orden del owner (2026-09-07): el orbe tenía que irse — el "
    "✦ de su centro es literalmente el glifo que toda la industria usa para decir "
    "\"generado por IA\", y fuera de la meditación el centro era un EMOJI DEL "
    "SISTEMA que cambia de forma según el aparato. Era la única pieza del juego "
    "hecha enteramente de degradado, tras dos lotes quitándolos. En su lugar se "
    "sienta un CULTIVADOR ILUSTRADO, y el efecto (respiración, anillos, qi "
    "ascendente) se aplica a la FIGURA. Las once imágenes de reino pasan a ser "
    "LUGARES VACÍOS: las antiguas eran decoración de landing reaprovechada con "
    "PERSONAS dentro haciendo cosas distintas (uno de pie, uno levitando, uno "
    "combatiendo, uno volando) — por eso la escena nunca pudo poner leyenda a la "
    "imagen, ya que cinco de once contradirían la frase \"estás sentado\". Con el "
    "lugar vacío, la capa de arriba puede ser el JUGADOR sin que la de abajo la "
    "contradiga: el reino dice DÓNDE, la figura dice QUIÉN, el efecto dice QUÉ. "
    "La figura solo aparece SENTADA — de pie, el círculo muestra el asiento vacío "
    "y el lugar esperando, porque la leyenda dice \"no estás sentado\" y la "
    "pantalla no puede contradecirse. El género (Migración 140) elige qué figura; "
    "NULL es un estado legítimo (los jugadores del beta) con figura propia, 背影, "
    "de espaldas. NADA está bloqueado por género — el matrimonio en particular "
    "sigue siendo gender-free. Ortogonal a `cartas` y `cena_cultivo`; con esta "
    "llave apagada la escena renderiza exactamente el orbe de hoy."
)
MINI = {
    "pt": {"feature_cultivador": "坐 O Cultivador", "feature_cultivador_desc": _D_PT},
    "en": {"feature_cultivador": "坐 The Cultivator", "feature_cultivador_desc": _D_EN},
    "es": {"feature_cultivador": "坐 El Cultivador", "feature_cultivador_desc": _D_ES},
}


def _merge(path, new):
    d = json.load(io.open(path, encoding="utf-8"))
    added = 0
    for k, v in new.items():
        if k not in d:
            d[k] = v
            added += 1
    d = dict(sorted(d.items()))
    io.open(path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=4) + "\n")
    return added, len(d)


def main() -> int:
    for lg in LANGS:
        a, n = _merge(os.path.join(ROOT, "locales", f"{lg}.json"), CHAT[lg])
        b, m = _merge(os.path.join(ROOT, "miniapp", "i18n", f"{lg}.json"), MINI[lg])
        print(f"  {lg}: chat +{a} -> {n} · mini +{b} -> {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
