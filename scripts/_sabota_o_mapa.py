# -*- coding: utf-8 -*-
"""圖 A BATERIA DE SABOTAGEM da §16 — uma guarda que nao morde nao guarda.

Cada entrada estraga UMA coisa no codigo de producao, corre
`_test_web_c_superficies.py`, e exige que ele fique VERMELHO — e que fique
vermelho A DIZER O QUE E' (a mensagem tem de conter a agulha), nunca a rebentar.

Duas licoes desta casa estao assadas aqui:

  · **Uma guarda que REBENTA nao e' uma guarda vermelha** (09/09). Se a suite
    morrer com `IndexError`, ela esta' a dizer que o FICHEIRO DE TESTE esta'
    errado, nao que o codigo esta'. Por isso se exige codigo de saida 1 (asserts
    vermelhos) e nao um traceback.
  · **Uma sabotagem que nunca encontra o alvo da-se por boa** (09/09). Por isso
    cada alvo e' verificado ANTES: se a string nao existir no ficheiro, a
    sabotagem falha aqui, ruidosamente.

Uso:  python scripts/_sabota_o_mapa.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
DB = os.path.join(ROOT, "database", "db.py")
HTML = os.path.join(ROOT, "miniapp", "index.html")

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    ("porta apagada do manifesto (orfao)", UI,
     '''          { key:"mercado",  tab:"market",    label_key:"tab_market",
            art:"door-caverna-mercado.webp",  x:62, y:70, w:34 },
''', "", "ZERO ORFAOS"),

    ("destino NOVO no grupo do hub, sem porta", UI,
     'group:["hub_caverna_screen","cavern","crafting","inventory","beasts","market"]',
     'group:["hub_caverna_screen","cavern","crafting","inventory","beasts","market","horta"]',
     "ZERO ORFAOS"),

    ("porta a apontar para fora do grupo", UI,
     '{ key:"forja",    tab:"crafting",',
     '{ key:"forja",    tab:"explore",',
     "aponta para fora"),

    ("duas portas uma por cima da outra", UI,
     'art:"door-caverna-anel.webp",     x:65, y:37, w:32 }',
     'art:"door-caverna-anel.webp",     x:33, y:6,  w:32 }',
     "nao se sobrepoem"),

    ("nome de arte mal escrito", UI,
     'art:"door-caverna-estabulo.webp"',
     'art:"door-caverna-estabolo.webp"',
     "existe em disco"),

    # ⚠️ RE-APONTADA a 2026-09-13: o `onClick` ganhou o ramo do `onSelect`
    # (uma porta pode ABRIR em vez de IR) e o alvo antigo deixou de existir. A
    # bateria disse "ALVO NAO ENCONTRADO" em vez de se dar por boa — foi assim
    # que se soube.
    # ⚠️ RE-APONTADA a 2026-09-15: o `onClick` mudou de dono (`HubScene` ->
    # `SceneDoor`) quando a porta saiu para poder ser usada tambem dentro do
    # continente. As tres sabotagens abaixo diziam "ALVO NAO ENCONTRADO" e
    # davam-se por boas — falso verde com mais passos, pela 2a vez em dois dias.
    ("o tap morre junto com a luz (Lei §1)", UI,
     '          onClick={() => { haptic("select"); onActivate && onActivate(); }}',
     '          onClick={aceso ? () => { haptic("select"); onActivate && onActivate(); } : undefined}',
     # ⚠️ A agulha deixou de citar o nome da variavel: a guarda cegou-se uma vez
     # com um rename (`lit` -> `aceso`) e passou a afirmar sobre os DOIS nomes.
     "NAO depende do estado aceso/apagado"),

    # 州 A porta que so' sabe IR — e o Mundo fica mudo (o continente deixava de
    # revelar os seus locais, e um tap passava a saltar para `explore`).
    ("a porta perde o ramo do `onSelect`", UI,
     '                  if (typeof ds.onSelect === "function") { ds.onSelect(d.key); return; }\n',
     "",
     "sabe ABRIR"),

    # 州 …e o inverso: a porta que so' sabe ABRIR parte a Caverna inteira.
    ("a porta perde o caminho por omissao (`setTab`)", UI,
     '                  if (typeof ds.onSelect === "function") { ds.onSelect(d.key); return; }\n                  setTab(d.tab);',
     '                  if (typeof ds.onSelect === "function") { ds.onSelect(d.key); return; }',
     "sabe ABRIR"),

    # 州 Um `dim` que nao apaga: o estado desaparece sem nada ficar vermelho.
    ("o apagado declarado deixa de apagar", UI,
     'dim: "grayscale(.34) brightness(.72)",',
     'dim: "none",',
     "continua a DESSATURAR"),

    # 州 Um `dim_key` declarado e nao traduzido anuncia o TOKEN CRU.
    ("o `dim_key` do Mundo nao existe na i18n", UI,
     'dim_key: "mapa_porta_longe",',
     'dim_key: "mapa_porta_longe_XX",',
     "existe em"),

    ("o botao perde a cor (preto sobre preto)", UI,
     '            color:"var(--gold2)",\n',
     "",
     "declara `color`"),

    # ⚠️ RE-APONTADA a 2026-09-13: o sufixo passou a vir do `def.dim_key`,
    # porque o que "apagado" quer dizer muda com o hub (na Caverna e' "a'
    # espera"; no Mundo seria mentira — o continente existe, voce e' que esta'
    # noutro sitio).
    ("o apagado deixa de se anunciar", UI,
     'name + " — " + safeT(dimKey || "mapa_porta_apagada")',
     'name',
     "DIZ que esta' apagada"),

    ("a flag deixa de exigir a ui_v2", UI,
     '&& featureEnabled("o_mapa") && featureEnabled("ui_v2");',
     '&& featureEnabled("o_mapa");',
     "exige as DUAS flags"),

    # ⚠️ RE-APONTADA a 2026-09-13: as entradas do Eu e do Pergaminho deixaram
    # de comecar por "pendente" — passaram a ser DECISOES escritas (nenhum dos
    # dois e' um lugar). A guarda que elas alimentam nao mudou.
    ("um hub sem cena e sem pendente (o esquecido)", UI,
     '      hub_pergaminho: "decisao,',
     '      hub_pergamiXXo: "decisao,',
     "tem resposta"),

    # ⚠️ RE-APONTADA a 2026-09-13 (ver acima). O corte e' pelo PREFIXO da
    # linha, para nao voltar a partir de cada vez que o motivo for reescrito.
    ("pendente sem motivo", UI,
     '      hub_eu:         "decisao, nao pendente:',
     '      hub_eu:         "pendente", //',
     "MOTIVO escrito"),

    ("volta o segundo tap (o acordeao)", TABS,
     '            <HubScene hub="hub_caverna" setTab={setTab} doors={mapaDoors} />',
     '            <HubScene hub="hub_caverna" setTab={setTab} doors={mapaDoors} />\n'
     '            <button>{safeT("hub_caverna_entrar")}</button>',
     "nao tem o botao 'Entrar'"),

    ("a flag nasce LIGADA", DB,
     '"o_mapa":              False,',
     '"o_mapa":              True, ',
     "nasce OFF"),

    ("a porta perde o foco visivel", HTML,
     ".nv-door:focus-visible",
     ".nv-doorXX:focus-visible",
     "foco VISIVEL"),

    ("a caixa perde a razao declarada", UI,
     'aspectRatio:"1 / 1.70", borderRadius:14',
     'borderRadius:14',
     "declara a sua razao"),

    # ⚠️ 2026-09-15 — a ancora MUDOU DE SITIO porque a porta saiu do `HubScene`
    # para o `SceneDoor`, e sao agora DUAS imagens em dois donos. Uma bateria
    # que nao segue a mudanca diz "ALVO NAO ENCONTRADO" e da-se por boa: falso
    # verde com mais passos (6 das 17 sabotagens de 14/09 morreram assim).
    ("a PORTA perde o onError", UI,
     '                   onError={() => setFailed(true)}\n',
     "",
     "PORTA tem `onError`"),

    ("o FUNDO da cena perde o onError", UI,
     '                 onError={() => setBgFailed(true)}\n',
     "",
     "FUNDO da cena tem `onError`"),

    # ══ 圖 V7 — O DENTRO DO CONTINENTE (2026-09-15) ═══════════════════════
    # A 1ª destas e' a que importa: sem peca para UM local, a gaveta desenha
    # cinco portas pintadas e um emoji — a tela nao fica por fazer, fica
    # PARTIDA, que a Lei 0 diz ser pior.
    ("um local do continente fica sem peca", UI,
     '      sect:      "door-mundo-sect.webp",\n',
     "",
     "sem peca"),

    ("uma peca de porta fica sem local que a peca", TABS,
     '{ id:"chronicle", ico:"📖", key:"hub_mundo_cronica"',
     '{ ico:"📖", key:"hub_mundo_cronica"',
     "sem local"),

    ("a peca aponta para um ficheiro que nao existe", UI,
     '      plaza:     "door-mundo-plaza.webp",',
     '      plaza:     "door-mundo-praca.webp",',
     "existe em disco"),

    # 🔴 A arte NAO pode apagar a frase da porta apagada (V7 §3 / MV-9): sao 20
    # portas que voltariam a ficar mudas, e o jogador batia sem resposta.
    # ⚠️ 2026-09-16 — RE-APONTADAS. O owner corrigiu a forma do dentro do
    # continente: deixou de ser uma grelha de azulejos e passou a ser uma CENA.
    # O estado vivo de cada porta mudou de sitio (do JSX do azulejo para o mapa
    # `doors` que a tela entrega ao `HubScene`). Uma bateria que nao segue diz
    # "ALVO NAO ENCONTRADO" e da-se por boa — falso verde com mais passos.
    ("a porta pintada perde a linha `⛵ <cidade>`", TABS,
     '                              line: !isCurrent ? seloViagem(isle) : null,\n',
     "",
     "veste a frase"),

    ("a porta APAGADA deixa de levar a' viagem", TABS,
     '                                : () => onOpenTravel && onOpenTravel(),',
     '                                : undefined,',
     "beco"),

    # 🔴 O CHAO TEM DE SER MAIS ESCURO DO QUE AS PECAS. Sem veu proprio, cada
    # porta sai com um HALO no vale de Linghe — so' se ve' a OLHAR.
    ("a cena do continente perde o seu veu", TABS,
     '                            veil: "radial-gradient(ellipse at 50% 46%,"',
     '                            _veil_off: "radial-gradient(ellipse at 50% 46%,"',
     "declara o seu proprio veu"),

    ("a lista de emoji volta a existir COM a flag", TABS,
     '                      {!sceneOn && (\n                      <div style={{\n'
     '                        display:"grid",',
     '                      {true && (\n                      <div style={{\n'
     '                        display:"grid",',
     "atras de `!sceneOn`"),

    ("o hub deixa de passar o seu apagado a' porta", UI,
     '                dim={def.dim}\n',
     "",
     "passa o `dim`"),

    # ⚠️ UM DONO: uma segunda definicao da porta e' a Lei F-7 §2 a quebrar-se.
    ("nasce uma SEGUNDA definicao de `SceneDoor`", UI,
     # ⚠️ RE-APONTADA a 2026-09-16: a assinatura ganhou `sceneDef` quando o
     # continente passou a abrir como cena. Uma ancora que nao segue diz
     # "ALVO NAO ENCONTRADO" e da-se por boa.
     '    function HubScene({ hub, setTab, doors, sceneDef }) {',
     '    function SceneDoor(p) { return null; }\n'
     '    function HubScene({ hub, setTab, doors, sceneDef }) {',
     "UMA definicao de `SceneDoor`"),

    # ⚠️ Esta sabotagem deixa o JSX inteiro no ficheiro e so' apaga a CONDICAO —
    # foi ela que derrubou a 1a versao da guarda (`"<SceneDoor" in tabs.js`),
    # que ficava verde com a gaveta outra vez em emoji. A agulha e' a da guarda
    # NOVA, que le' a condicao do codigo.
    ("a gaveta do continente deixa de abrir como cena", TABS,
     '                      {sceneOn && typeof HubScene === "function"',
     '                      {false && typeof HubScene === "function"',
     "sob a flag do mapa"),

    # ⚠️ A pintura do continente e' pedida por tabela propria. Um continente sem
    # chao cai no recurso do `HubScene` e o jogador ve' uma caixa vazia com
    # portas a flutuar — sem erro nenhum.
    # ⚠️ A agulha e' "tem chao declarado" e NAO "existe em disco": sao dois
    # modos de falha diferentes e a guarda tem os dois. Tirar o continente da
    # tabela e' o primeiro; escrever mal o nome do ficheiro e' o segundo.
    ("um continente fica sem o seu chao", UI,
     '      linghe:  "isle-linghe-scene.webp",\n',
     "",
     "tem chao declarado"),

    ("o chao de um continente aponta para ficheiro que nao existe", UI,
     '      moyu:    "isle-moyu-scene.webp",',
     '      moyu:    "isle-mo-yu-scene.webp",',
     "existe em disco"),

    # ══ 卷 A PELE DO PERGAMINHO (2026-09-15) ══════════════════════════════
    ("o rolo deixa de MEDIR a caixa que o hospeda", TABS,
     '          const host = el.closest(".scroll-area");',
     '          const host = null;',
     "MEDIDA na caixa"),

    ("a altura do rolo passa a ser assada em `vh`", TABS,
     '          setFill(dentro > 160 ? Math.round(dentro) : 0);',
     '          setFill(Math.round(window.innerHeight * 0.72));\n'
     '          if (false) { const _x = "100vh"; }',
     "unidades de ecra"),

    # 🔴 A textura que o OLHAR reprovou: dois repetidores cruzados dao uma
    # GRELHA (papel milimetrico), nao fibra.
    ("o papel volta a ter trama com periodo", TABS,
     '          "radial-gradient(130% 46% at 50% -4%,',
     '          "repeating-linear-gradient(90deg, rgba(0,0,0,.1) 0 1px, transparent 1px 3px),"\n'
     '          + "radial-gradient(130% 46% at 50% -4%,',
     "trama com PERIODO"),

    ("a altura do rolo sai de dentro do ternario", TABS,
     '               minHeight: fill ? (fill - 6) : undefined,',
     '               minHeight: 601,',
     "DENTRO do ternario"),

    # ⚠️ A ANTI-GUARDA: se o localizador deixar de encontrar a tabela, TUDO o que
    # vem depois compara conjuntos vazios. Isto tem de ficar vermelho a dizer
    # isso — e nao a rebentar com um ValueError.
    ("o localizador perde a tabela das cenas", UI,
     # ⚠️ `HUB_SCENE_DEFS_X` NAO servia: o localizador procura o PREFIXO
     # `var HUB_SCENE_DEFS` e continuava a encontra-lo dentro do nome novo — a
     # sabotagem dava-se por boa sem nunca ter mudado nada. O nome tem de nao
     # partilhar prefixo nenhum.
     "var HUB_SCENE_DEFS = {",
     "var HUB_CENA_TABELA = {",
     "as tres pecas do mapa existem"),
]


def run():
    falhas = []
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8").read()
        if orig.count(de) != 1:
            falhas.append("%-46s ALVO NAO ENCONTRADO (%d ocorrencias) — a "
                          "sabotagem dava-se por boa sem nunca ter corrido"
                          % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(
            orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run(
                [sys.executable,
                 os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")],
                capture_output=True, text=True, env=env, cwd=ROOT, timeout=600,
                # ⚠️ `text=True` sozinho descodifica com o codec do LOCALE
                # (cp1252 no Windows) e REBENTA no primeiro 漢字 da suite. A 1a
                # versao deste ficheiro reportou "0/17 mordem" — dezassete
                # falsos negativos, todos porque o RUNNER e nao o codigo e que
                # estava partido. Uma bateria de sabotagem que mente na
                # direccao do alarme e menos perigosa do que a que mente ao
                # contrario, mas continua a nao valer nada.
                encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n") if l.strip().startswith("x ")]
            # ⚠️ NAO se detecta um crash por "Traceback" no stderr: a propria
            # suite acende um de proposito no §1 (o cenario "control plane em
            # chamas") e as 17 sabotagens sairam todas como REBENTOU, que e'
            # um falso alarme tao inutil como um falso verde. O sinal honesto
            # e' o RODAPE: se a suite chegou ao fim, ela imprime-o; se morreu
            # a meio, nao.
            rebentou = "asserts verdes" not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and (not agulha
                                  or any(agulha in l for l in vermelhos))
            if acertou:
                print("  ok  %-46s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-46s REBENTOU — uma guarda que rebenta nao e' "
                              "uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-46s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-46s ficou vermelha pelo motivo ERRADO "
                              "(esperava %r)" % (rot, agulha))
                print("  XX  " + falhas[-1])
        finally:
            io.open(path, "w", encoding="utf-8", newline="").write(orig)
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas),
                                       len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
