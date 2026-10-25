# -*- coding: utf-8 -*-
"""印 A AUDITORIA DO EMOJI — onde e' que o jogo AINDA fala por emoji do sistema.

Porque existe
-------------
Ordem do owner, 2026-09-09 (textual): *"Usando minha conta normal ou antiga
ainda sai icones antigos etc. Precisamos remover isso. Tudo tem que ser novo,
NAO QUERO falhas."*

Ele tinha razao, e a flag `iconografia` **nao estava avariada** — estava a fazer
exactamente o que a descricao dela promete, que era pouco. MEDIDO a 2026-09-09,
com **todas** as flags visuais ligadas e o jogo servido a serio:

    160 emoji ainda visiveis em 8 abas · 57 distintos

⚠️ **Os quatro piores estavam no CABECALHO** — e o cabecalho aparece em TODAS as
telas, portanto multiplicavam-se por cada ecra que o jogador abria:

    🔮 avatar (REALM_AVATAR_EMOJIS, ui.js)   · nao gated
    🔮 chip do reino (player.realm_emoji)    · nao gated
    🔔 sino das notificacoes                 · nao gated
    🌐 emblema do mundo (so' em mundos != main — por isso o owner ve-o no s2)

Sozinhos valiam **47 das 160 ocorrencias vistas (29%)**. E eram a razao de o
sintoma aparecer *"na conta normal ou antiga"*, em qualquer ecra: nao dependia de
conta nenhuma, dependia de o cabecalho estar sempre la'.

⚠️ E ha' uma ironia registada: o lote que CRIOU a Lei F-7 (印 OS ICONES, 08/09)
converteu as **tres moedas** do cabecalho e deixou os **quatro** vizinhos. E' o
proprio defeito que a lei descreve, dentro do lote que a escreveu.

O QUE MUDOU no mesmo dia (lote 印 OS ICONES ANTIGOS)
---------------------------------------------------
O cabecalho esta' a **ZERO** e o jogo servido passou de **160 para 128** emoji
visiveis nas mesmas 8 abas — os 32 que sairam sao 4 x 8, o cabecalho exactamente.
A cobertura da flag subiu de 9,2% para **10,2%**, e o numero pequeno e' honesto:
o que saiu nao foi 1% de sitios quaisquer, foi o unico componente que aparece em
TODAS as telas. Contar ocorrencias no ficheiro e contar o que o jogador VE sao
duas medicoes diferentes, e e' a segunda que manda.

⚠️ E o achado que nenhuma contagem de ficheiro podia dar, porque so' aparece a
OLHAR: as marcas das duas barras de baixo estavam a ser desenhadas **PRETAS
sobre um fundo quase preto**. Um `<button>` nao herda a cor da pagina (a folha
do agente po~e-lhe `color: buttontext`) e a `Mark` desenha em `currentColor` de
proposito. Eram 8 por ecra, invisiveis, em todas as abas medidas — e a guarda
estava VERDE, porque perguntava se o `TAB_DEFS` tinha `mark:`, nunca se o traco
se via.

Uso
---
    python scripts/_audit_iconografia.py            # o relatorio
    python scripts/_audit_iconografia.py --json     # para outra ferramenta

A GUARDA que impede isto de crescer vive na §15 de
`scripts/_test_web_c_superficies.py` e importa este ficheiro. Aqui e' so' a
medicao; la' e' o dente.
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ⚠️ NAO inclui ️ (o seletor de variacao): ele e' um MODIFICADOR e contava
# duas vezes o mesmo simbolo. Tambem nao inclui os hanzi — 洞府 e' vocabulario
# da casa, escolhido, e nao um pictograma do sistema operativo.
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF"   # simbolos e pictogramas
    "☀-➿"            # misc + dingbats
    "⬀-⯿"            # setas e formas
    "←-⇿"            # setas
    "⭐〰〽]"
)

COMPONENTS = ("miniapp/components/ui.js",
              "miniapp/components/tabs.js",
              "miniapp/components/app.js")

# ── As formas que JA' passam pela flag ────────────────────────────────────────
# `ico("X","nome")` e `slotIco(slot, emoji, n)` trocam para a marca SVG quando
# `iconografia` esta' ON. Um campo `ico:` / `emoji:` numa tabela de definicao e'
# o FALLBACK legitimo do ramo desligado (ao lado dele ha' um `mark:`).
_GATED_CALL = re.compile(r'(?:slot)?[Ii]co\(\s*"$')
_DEF_FIELD = re.compile(r'(?:ico|emoji|glyph)\s*:\s*"$')
# ⚠️ A TERCEIRA forma, e a 1a versao desta auditoria nao a conhecia: o ternario
# escrito a mao `markOn("x") ? <Mark .../> : "emoji"`. A auditoria acusou as
# tres moedas do cabecalho de estarem cruas quando estao gated ha' um lote — ou
# seja, **sobre-reportou**, que e' a mesma familia de erro do sub-reportar: uma
# medicao errada manda o trabalho para o sitio errado. Encontrada a comparar o
# relatorio com o que o ecra mostrava (o ecra tinha razao).
_GATED_TERNARY = re.compile(
    r'(?:markOn\(\s*"[^"]+"\s*\)|iconografiaOn\(\))[\s\S]{0,400}:\s*"$')
# ⚠️ A QUARTA forma, 2026-09-09 (lote 印 OS ICONES ANTIGOS): `iconografiaOn()` e'
# o MESMO portao que o `markOn` — e' literalmente o que o `markOn` chama por
# dentro. Existe porque ha' dois sitios onde o ramo LIGADO **nao desenha marca
# nenhuma**: o chip do reino passa a TIPOGRAFIA e o emblema do mundo passa a
# 漢字. La', escrever `markOn("x")` seria uma mentira — nao ha' marca `x`. Sem
# esta forma a auditoria contava os dois como CRUS, e sub-reportar e
# sobre-reportar sao a mesma familia de erro: mandam o trabalho para o sitio
# errado com confianca.


def strip_comments(src):
    """Sem prosa, mas SEM PERDER A LINHA.

    ⚠️ A 1a versao apagava os comentarios e depois contava `\n` — e os numeros
    de linha que imprimia nao existiam no ficheiro (apontavam para um `<polygon>`
    a 200 linhas de distancia). Um relatorio que aponta para a linha errada e'
    pior do que um sem linha nenhuma: manda o proximo leitor ao sitio errado com
    confianca. Agora cada comentario e' substituido pelos MESMOS `\n` que
    ocupava, portanto o texto encolhe e a numeracao fica intacta.
    """
    def _blank(m):
        return "\n" * m.group(0).count("\n")
    src = re.sub(r"/\*.*?\*/", _blank, src, flags=re.S)
    # ⚠️ E a linha de `//` tambem fica — VAZIA, nao apagada.
    return re.sub(r"(?m)^\s*//.*$", "", src)


def scan_file(path):
    """[(linha, emoji, categoria)] para um ficheiro de componente."""
    src = strip_comments(io.open(os.path.join(ROOT, path), encoding="utf-8").read())
    out = []
    for m in EMOJI.finditer(src):
        # ⚠️ 420 e nao 40: o ternario do `markOn` pode ter o `<Mark/>` inteiro
        # pelo meio. Uma janela curta demais faz a auditoria acusar codigo que
        # ja' esta' certo.
        pre = src[max(0, m.start() - 420):m.start()]
        if _GATED_CALL.search(pre) or _GATED_TERNARY.search(pre):
            cat = "gated"          # troca para marca com a flag ON
        elif _DEF_FIELD.search(pre):
            cat = "fallback"       # o ramo OFF de uma tabela que tem `mark:`
        else:
            cat = "cru"            # NUNCA troca: o jogador ve isto sempre
        out.append((src[:m.start()].count("\n") + 1, m.group(0), cat))
    return out


def scan():
    res = {}
    for p in COMPONENTS:
        res[p] = scan_file(p)
    return res


# ── O CABECALHO: o multiplicador ─────────────────────────────────────────────
# Nao e' "mais um sitio": e' o unico componente que renderiza em TODAS as telas.
# Um emoji cru aqui custa 1x por ecra que o jogador abrir.
# ⚠️ **A MEDICAO SEGUE A INDIRECCAO.** O avatar deixou de viver dentro do
# `PlayerHeader`: passou a `RealmAvatar`, o dono unico dele **e** do gemeo que o
# `ProfileModal` tinha a' mao. Se esta funcao continuasse a olhar so' para o
# `PlayerHeader`, os 11 emoji do avatar **saiam do relatorio sem sair do jogo** e
# a medicao passava a dizer "resolvido" sobre codigo que apenas MUDOU DE SITIO.
# E' a licao de 09/09 ("a guarda afirma sobre o SITIO, nao sobre o ficheiro")
# virada do avesso: o sitio mudou, a medicao muda com ele.
_HEADER_REGIONS = ("function PlayerHeader(", "function RealmAvatar(",
                   "var REALM_AVATAR_DEFS")


def header_source():
    """[(ancora, offset_no_ficheiro, texto)] das regioes do cabecalho, sem prosa.

    O offset e' o que permite imprimir o numero de linha REAL — a licao dos
    numeros de linha inventados da 1a versao deste ficheiro.
    """
    src = strip_comments(io.open(os.path.join(ROOT, "miniapp/components/ui.js"),
                                 encoding="utf-8").read())
    out = []
    for anchor in _HEADER_REGIONS:
        i = src.find(anchor)
        if i < 0:
            # ⚠️ Uma ancora perdida NAO pode ser silencio: uma medicao cega fica
            # VERDE, que e' a pior forma de vermelho. Quem renomear le' isto.
            raise RuntimeError(
                "auditoria: a ancora %r desapareceu de ui.js. Se a funcao mudou "
                "de nome, ACTUALIZE _HEADER_REGIONS — nao apague a entrada, ou a "
                "medicao do cabecalho passa a olhar para menos codigo do que o "
                "jogador ve." % anchor)
        j = src.find("\n    function ", i + 20)
        k = src.find("\n    var ", i + 20)
        end = min([x for x in (j, k) if x > 0] or [len(src)])
        out.append((anchor, i, src[i:end]))
    return out


def header_offenders():
    src = strip_comments(io.open(os.path.join(ROOT, "miniapp/components/ui.js"),
                                 encoding="utf-8").read())
    out = []
    for _anchor, off, body in header_source():
        base = src[:off].count("\n")
        for m in EMOJI.finditer(body):
            pre = body[max(0, m.start() - 420):m.start()]
            if (_GATED_CALL.search(pre) or _DEF_FIELD.search(pre)
                    or _GATED_TERNARY.search(pre)):
                continue
            out.append((base + body[:m.start()].count("\n") + 1, m.group(0)))
        # o chip do reino nao tem literal — vem do payload (`player.realm_emoji`)
        p = body.find("player.realm_emoji")
        while p >= 0:
            # o mesmo portao dos literais, aplicado a uma expressao: so' conta
            # como ofensa se NAO estiver dentro de um ramo desligado pela flag.
            if not _GATED_TERNARY.search(body[max(0, p - 420):p] + ': "'):
                out.append((base + body[:p].count("\n") + 1,
                            "player.realm_emoji (vem do servidor, sem literal)"))
            p = body.find("player.realm_emoji", p + 1)
    return out


def main():
    res = scan()
    tot = {"gated": 0, "fallback": 0, "cru": 0}
    for hits in res.values():
        for _, _, c in hits:
            tot[c] += 1
    total = sum(tot.values())

    if "--json" in sys.argv:
        print(json.dumps({"total": total, "por_categoria": tot,
                          "cabecalho": [[l, e] for l, e in header_offenders()]},
                         ensure_ascii=False, indent=2))
        return 0

    print("=" * 72)
    print("  印 AUDITORIA DA ICONOGRAFIA — o que a flag alcanca, e o que nao")
    print("=" * 72)
    print()
    print("  %-46s %6s  %s" % ("categoria", "n", "o jogador ve..."))
    print("  " + "-" * 68)
    print("  %-46s %6d  %s" % ("gated — passa por ico()/slotIco()", tot["gated"],
                               "a MARCA (flag ON)"))
    print("  %-46s %6d  %s" % ("fallback — campo `ico:`/`emoji:` com `mark:`",
                               tot["fallback"], "a MARCA (flag ON)"))
    print("  %-46s %6d  %s" % ("CRU — literal no JSX, sem porta nenhuma",
                               tot["cru"], "SEMPRE o emoji"))
    print("  " + "-" * 68)
    print("  %-46s %6d" % ("TOTAL", total))
    cobre = tot["gated"] + tot["fallback"]
    print()
    print("  A flag `iconografia` alcanca %d de %d = %.1f%%."
          % (cobre, total, 100.0 * cobre / max(1, total)))
    print()
    print("  Por ficheiro (so' os CRUS):")
    for p, hits in res.items():
        n = sum(1 for _, _, c in hits if c == "cru")
        print("    %-34s %5d" % (p.split("/")[-1], n))

    print()
    print("=" * 72)
    print("  O CABECALHO — o multiplicador (renderiza em TODAS as telas)")
    print("=" * 72)
    _off = header_offenders()
    for line, e in _off:
        print("    ui.js:%-6s %s" % (line if line > 0 else "?", e))
    if not _off:
        print("    (nenhum — as tres regioes do multiplicador falam por marca)")
    print()
    print("  MEDIDO a 2026-09-09 no jogo servido, com TODAS as flags visuais ON,")
    print("  navegando as 8 abas por POSICAO do slot (nem por emoji nem por")
    print("  aria-label: sao os dois metodos que so' funcionam de UM lado):")
    print("    antes  ..... 160 emoji visiveis · 57 distintos · cabecalho 4/ecra")
    print("    depois ..... 128 emoji visiveis · 57 distintos · cabecalho ZERO")
    print("  Os 32 que sairam sao 4 x 8 abas: o cabecalho, exactamente.")
    print("  Os distintos NAO desceram, e isso e' honesto: o sino e o emblema")
    print("  continuam a existir noutros sitios (as linhas das Configuracoes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
