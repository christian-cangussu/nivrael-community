# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM das §26/§27 — uma guarda que nao morde nao guarda.

Mesmo contrato das outras (`_sabota_varredor`, `_sabota_o_mapa`,
`_sabota_a_forja`, `_sabota_o_golpe`, `_sabota_o_hp`, `_sabota_os_nomes`): cada
entrada estraga UMA coisa no codigo de producao, corre a suite, e exige que ela
fique VERMELHA **a dizer o que e'** — nunca a rebentar, e nunca por um motivo
diferente do esperado.

As duas feridas desta bateria sao as duas do dia 23/09:

  §26 至 A MACANETA — o owner: *"tenho que clicar 2 vezes no eu pra abrir o
      menuzinho pra ver o corpo"*. O selector existia e nada no ecra o
      anunciava. As sabotagens atacam os dois modos de falha que importam: a
      linha desaparecer, e a linha passar a ter uma SEGUNDA lista de nomes
      (que e' como ela deixaria de concordar com o que a sobreposicao abre —
      em silencio).

  §27 語 O NOME "W" DO [jogador] — o tradutor do browser a reescrever um nome proprio.
      As sabotagens atacam a raiz desmarcada e, sobretudo, o **dono unico da
      lingua**: basta um `LANG = ...` a' mao voltar e o `<html lang>` fica para
      tras outra vez, sem nada partir — que e' exactamente como isto sobreviveu
      ate' hoje.

Uso:  python scripts/_sabota_a_macaneta.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
APP = os.path.join(ROOT, "miniapp", "components", "app.js")
IDX = os.path.join(ROOT, "miniapp", "index.html")
PT = os.path.join(ROOT, "miniapp", "i18n", "pt.json")
SUITE = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── §26 至 A MACANETA ──────────────────────────────────────────────────
    ("a linha das portas desaparece da chegada", UI,
     '<span className="chegada-portas-rot">{t("chegada_portas_rotulo")}</span>',
     '<span className="chegada-portas-rot">{"\\u00a0"}</span>',
     "nomeia os destinos do Eu"),

    # 🔴 A QUE IMPORTA. Uma segunda lista de nomes a' mao nao parte nada, nao
    # da erro, e o ecra fica a anunciar destinos que o selector nao abre — o
    # modo de falha exacto da Lei 0 §2, e o mais dificil de ver a olhar.
    ("a linha ganha uma SEGUNDA lista de nomes, a' mao", TABS,
     "portas={pathsSeletor.map(pp => t(pp.key))}",
     'portas={["Cultivo", "Corpo", "Celestial"]}',
     "uma lista, um dono"),

    ("a linha volta a aparecer tambem no PC, por cima da lateral", UI,
     "{(!wide && portas && portas.length && onPortas) ? (",
     "{(portas && portas.length && onPortas) ? (",
     "composicao estreita"),

    # ⚠️ O fio cortado no MEIO: o botao continua a existir e deixa de abrir.
    ("o abridor deixa de nascer no App", APP,
     'onAbrirSeletor={() => { haptic("select"); setEuSeletor(true); }}',
     "onAbrirSeletor={undefined}",
     "nasce no App"),

    ("a `Chegada` deixa de encaminhar as portas para a cena", TABS,
     "portas={portas} onPortas={onPortas}",
     "portas={undefined} onPortas={undefined}",
     "o fio inteiro"),

    ("o `{n}` cai da palavra e o jogador le' so' \"mais\"", PT,
     '"chegada_portas_mais": "mais {n}"',
     '"chegada_portas_mais": "mais"',
     "nao sabe mais quantos"),

    # ── §27 語 O NOME "W" ─────────────────────────────────────────────────
    ("a raiz volta a ficar aberta ao tradutor do browser", IDX,
     '<html lang="pt-BR" translate="no" class="notranslate">',
     '<html lang="pt-BR">',
     "tradutor do browser"),

    # 🔴 A OUTRA QUE IMPORTA. Esta e' a avaria ORIGINAL a voltar: a lingua do
    # JOGO muda e a do DOCUMENTO fica para tras. Nada parte, nada fica lento, e
    # o browser volta a oferecer traduzir uma pagina que jura ser portuguesa.
    ("um escritor de `LANG` volta a saltar o dono", APP,
     "if (data?.language) definirLang(data.language);",
     "if (data?.language && STRINGS[data.language]) LANG = data.language;",
     "fora do dono"),

    ("o dono existe mas deixa de tocar no `<html lang>`", UI,
     '        document.documentElement.lang = v === "pt" ? "pt-BR" : v;',
     "        void v;",
     "actualiza o `<html lang>`"),

    ("a porta (`/login`) volta ao `lang` fixo", os.path.join(ROOT, "miniapp", "login.html"),
     '<html lang="{{LANG}}">',
     '<html lang="pt-BR">',
     "a lingua que serviu"),
]


def run():
    falhas = []
    print("=" * 78)
    print("  🩸 SABOTAGEM das §26/§27 — %d ataques" % len(SABOTAGENS))
    print("=" * 78)
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        # ⚠️ O alvo e' verificado ANTES: uma sabotagem que nunca encontra o que
        # estragar DA-SE POR BOA, e um "10/10 mordem" assim e' um falso verde
        # com mais passos (licao de 09/09).
        if orig.count(de) != 1:
            falhas.append("%-52s ALVO NAO ENCONTRADO (%d ocorrencias)"
                          % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(
            orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run(
                [sys.executable, SUITE],
                capture_output=True, text=True, env=env, cwd=ROOT, timeout=600,
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
                print("  ok  %-52s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-52s REBENTOU — uma guarda que rebenta nao e' "
                              "uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-52s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-52s ficou vermelha pelo motivo ERRADO "
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
