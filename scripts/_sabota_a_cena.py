# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM da §28 — uma guarda que nao morde nao guarda.

Mesmo contrato das outras (`_sabota_a_macaneta`, `_sabota_o_golpe`,
`_sabota_os_nomes`, ...): cada entrada estraga UMA coisa no codigo de producao,
corre a suite, e exige que ela fique VERMELHA **a dizer o que e'** — nunca a
rebentar, e nunca por um motivo diferente do esperado.

A razao de esta bateria existir e' mais velha do que o lote. A guarda de 14/09
contava que *toda chamada do cliente a `pieceArt` leva a chave* — e levava. O
`tech.art_key` e' que era `undefined`, porque o **servidor nunca o mandava**. A
guarda ficou verde nove dias sobre 129 artes por lingua invisiveis, e a unica
maneira de saber que uma guarda nova nao e' dessa familia e' **estraga-la a ver
se dói**.

Os tres grupos de ataque:

  §28.1-2 O PAYLOAD — a chave a nascer traduzida (a avaria ORIGINAL, na forma
      exacta), a chave a desaparecer, o custo a desaparecer, o endpoint a perder
      a lingua, e o mais perigoso de todos: a traducao a ser escrita DENTRO da
      coluna JSON que o outro lutador le'.

  §28.3-5 A CENA — a chapa a virar um segundo desenhador de arte, a paisagem de
      reino a entrar num duelo que nao tem lugar, o destaque a acender sem
      tecnica identificada, um emoji a nascer, e uma das quatro consequencias
      condicionais a cair no redesenho.

  §28.6-7 O PREPARO E A ENTRADA — a tira a virar um selector (a decisao que a
      v15.1.4 fechou), e a entrada a comecar uma luta ao toque.

Uso:  python scripts/_sabota_a_cena.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
WS = os.path.join(ROOT, "core", "webserver.py")
DUEL = os.path.join(ROOT, "core", "duel_engine.py")
SUITE = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── §28.1 O PAYLOAD ───────────────────────────────────────────────────
    # 🔴 A AVARIA ORIGINAL, NA FORMA EXACTA. Nao e' a chave a faltar — e' a
    # chave a existir e a estar ERRADA. `"art_key": _tname(...)` compila, tem o
    # nome certo, passa qualquer revisao a olho, e a arte cai no verso em `pt` e
    # em `es` sem um erro. Se a guarda nao apanhar ISTO, nao apanha nada.
    ("a chave nasce TRADUZIDA (a avaria de 14/09, na forma exacta)", WS,
     '                "art_key": name,\n                "emoji": emoji or "⚔️",',
     '                "art_key": _tname(int(tid), name),\n                "emoji": emoji or "⚔️",',
     "esta e' a MEDICAO"),

    ("a chave desaparece do `learned[]`", WS,
     '                "art_key": name,\n                "emoji": emoji or "⚔️",',
     '                "emoji": emoji or "⚔️",',
     "leva `art_key`"),

    ("o custo desaparece e a arte passa a parecer de graca", WS,
     '                "qi_cost": int(qi_cost or 10),\n',
     "",
     "de graca"),

    # ── §28.2 A LEITURA DO DUELO ──────────────────────────────────────────
    # 🔴 A PIOR DE TODAS, e a que nenhum teste de ecra apanharia. Um caractere:
    # `dict(tech)` -> `tech`. A tela do jogador `pt` fica IGUAL — certa, até. O
    # que muda e' que a traducao passa a ser escrita na coluna JSON da sessao, e
    # o adversario `es` abre o log dele e le' portugues. Para sempre.
    ("a traducao passa a ser escrita DENTRO do log gravado", DUEL,
     "    out = dict(tech)\n    tid = tech.get(\"id\")",
     "    out = tech\n    tid = tech.get(\"id\")",
     "INTACTAS"),

    ("o lado do log deixa de ser copiado antes de ser lido", DUEL,
     '    out = dict(lado)\n    out["tech"] = _tech_lido(lado.get("tech"), lang)',
     '    out = lado\n    out["tech"] = _tech_lido(lado.get("tech"), lang)',
     "INTACTAS"),

    # o fio cortado no MEIO: a funcao sabe traduzir e ninguem lhe diz a lingua.
    ("o endpoint perde a lingua de quem olha", WS,
     "get_duel_state(duel, user_id, _duel_lang)",
     "get_duel_state(duel, user_id)",
     "le' a lingua do espectador"),

    # a esquiva e' um estado HONESTO: sem tecnica, sem nome. Inventar um nome
    # para o `null` poria "Golpe basico" onde ninguem golpeou.
    ("o `null` da esquiva passa a devolver um dicionario", DUEL,
     "    if not isinstance(tech, dict):\n        return tech",
     '    if not isinstance(tech, dict):\n        return {"name": "?", "art_key": "?"}',
     "mantem `tech = null`"),

    # ── §28.3 A CENA ──────────────────────────────────────────────────────
    # A sexta chapa a nascer. Foi isto que a F-7 (B) me apanhou a fazer neste
    # lote, e e' como o verso honesto se duplicou tres vezes nesta casa.
    ("a chapa da cena volta a desenhar o seu proprio `<img>`", UI,
     '          <CardArt fill src={src || null} accent={acento || NIV_ONDA.muted}',
     '          <img src={src || undefined} alt="" /><CardArt fill src={src || null} accent={acento || NIV_ONDA.muted}',
     "involucro do `CardArt`"),

    # 🔴 O LUGAR INVENTADO. `duel_state` nao tem campo de lugar (medido, §7.4).
    # Pintar um reino por tras da luta e' dado fabricado com cara de dado real —
    # e ninguem daria por isso, porque fica bonito.
    ("a cena pinta uma paisagem de reino que o contrato nao diz", UI,
     '          <div className="cena-confronto">',
     '          <div className="cena-confronto">{realmArtUrl ? null : null}',
     "tinta neutra"),

    ("o destaque acende mesmo quando o evento nao identifica a tecnica", UI,
     "        const a = actVoce && actVoce.tech ? actVoce.tech : null;",
     '        const a = actVoce ? (actVoce.tech || {name:"?"}) : null;',
     "IDENTIFICA a tecnica"),

    ("um emoji nasce na cena (a catraca esta' a 1300/1300, sem folga)", UI,
     '              <span className="cena-vao-fio" aria-hidden="true" />',
     '              <span className="cena-vao-fio" aria-hidden="true" />⚔️',
     "nao tem UM emoji literal"),

    # ── §28.5 O RESULTADO ─────────────────────────────────────────────────
    # Uma das quatro consequencias a cair. Cada uma custou um lote a descobrir:
    # o espolio da gruta era MUDO no mini (QoL 31/07), o Tributo da Terra rolava
    # no settle e ninguem o dizia (QoL 04/08).
    ("o Tributo da Terra do chefe cai no redesenho", TABS,
     "{state.tribute_line && (",
     "{false && state.tribute_line && (",
     "sobreviveu ao redesenho"),

    ("a cena deixa de receber o resultado e o fim fica MUDO", TABS,
     "              resultado={blocoResultado}",
     "              resultado={null}",
     "usada no ramo antigo E na cena"),

    # ── §28.6 O PREPARO ───────────────────────────────────────────────────
    # Ressuscitar um "foco" aqui reabre uma decisao fechada na v15.1.4 (a arte
    # escolhe-se por RODADA, dentro do duelo).
    ("a tira de preparo volta a ser um selector de foco", UI,
     '                <div className="cena-prep-peca" key={tt.id}>',
     '                <div className="cena-prep-peca" key={tt.id} onClick={() => 0}>',
     "nao tem um unico botao"),

    ("nasce uma TERCEIRA tira parecida", TABS,
     '          {_cenaOn ? (\n            <CenaPreparo techs={combatTechs}',
     '          {_cenaOn ? (\n            <CenaPreparo techs={[]} />\n          ) : null}\n          {_cenaOn ? (\n            <CenaPreparo techs={combatTechs}',
     "exactamente duas chamadas"),

    # ── §28.9 OS TRES QUE SO' A OLHAR APARECERAM ─────────────────────────
    # 🔴 O hook a cair para depois do `return` antecipado. E' a avaria EXACTA
    # deste lote: React #310, e o jogador ve' "⚠️ Erro nesta secao" no lugar do
    # duelo inteiro. Nao se ve' a ler o ficheiro, nao aparece numa contagem, e
    # 1070 guardas estavam verdes por cima.
    # ⚠️ O alvo tem de ficar DEPOIS do `if (!state) return (<Modal>…)`, que e'
    # onde a avaria real esteve. Por o hook logo acima do `useState` nao sabota
    # nada — continua antes do primeiro return, e a guarda tem razao em ficar
    # verde (a 1a versao desta sabotagem e' que estava errada, nao a guarda).
    ("um hook cai para depois do `return` antecipado (React #310)", TABS,
     "      const you = state.you || {};",
     '      const _tarde = typeof useWideShell === "function" ? useWideShell() : false;\n'
     "      void _tarde;\n"
     "      const you = state.you || {};",
     "todo hook nasce ANTES"),

    # Uma crase dentro do CSS fecha o template literal e o BUILD morre. Tres
    # vezes seguidas neste lote, sempre a citar o nome de uma propriedade.
    ("uma crase entra num comentario do CSS da cena", UI,
     "            /* ── a faixa do CONFRONTO. O fundo e' TINTA NEUTRA",
     "            /* ── a faixa do " + chr(96) + "CONFRONTO" + chr(96) + ". O fundo e' TINTA NEUTRA",
     "ZERO crases"),

    # Um numero partido em duas linhas nao e' feio — e' FALSO. Visto a olho a
    # 390px: `158.977.287.8` / `26`.
    ("o numero das barras volta a poder partir-se ao meio", UI,
     "color:var(--cena-paper); white-space:nowrap;",
     "color:var(--cena-paper); overflow-wrap:anywhere;",
     "nunca os digitos"),

    # ── §28.7 A ENTRADA ───────────────────────────────────────────────────
    ("os numeros recolhem junto com o cabecalho de emoji", TABS,
     "            <CombatHeaderStats data={data} loading={loading && !data} />\n            <div style={{ marginTop:9 }}>",
     "            <div style={{ marginTop:9 }}>",
     "FICA"),
]


def run():
    falhas = []
    print("=" * 78)
    print("  \U0001fa78 SABOTAGEM da §28 — %d ataques" % len(SABOTAGENS))
    print("=" * 78)
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        # ⚠️ O alvo e' verificado ANTES: uma sabotagem que nunca encontra o que
        # estragar DA-SE POR BOA, e um "17/17 mordem" assim e' um falso verde
        # com mais passos (licao de 09/09).
        if orig.count(de) != 1:
            falhas.append("%-56s ALVO NAO ENCONTRADO (%d ocorrencias)"
                          % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(
            orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run(
                [sys.executable, SUITE],
                capture_output=True, text=True, env=env, cwd=ROOT, timeout=900,
                # ⚠️ `text=True` sozinho descodifica com o codec do LOCALE
                # (cp1252 no Windows) e rebenta no primeiro 漢字 da suite.
                encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n") if l.strip().startswith("x ")]
            # ⚠️ O sinal honesto de crash e' o RODAPE, nunca "Traceback" no
            # stderr: a propria suite acende um de proposito no §1.
            rebentou = "asserts verdes" not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and (not agulha
                                  or any(agulha in l for l in vermelhos))
            if acertou:
                print("  ok  %-56s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-56s REBENTOU — uma guarda que rebenta nao e' "
                              "uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-56s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-56s ficou vermelha pelo motivo ERRADO "
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
