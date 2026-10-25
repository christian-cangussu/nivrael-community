# -*- coding: utf-8 -*-
"""鎖 A BATERIA DE SABOTAGEM do varredor PvE (2026-09-12).

Cada entrada desfaz UMA metade do conserto, corre `_test_relatos_0814.py`, e exige
que ele fique VERMELHO **a dizer o que e'** — nunca a rebentar, nunca verde.

As duas licoes de 11/09 estao assadas aqui e nao se repetem:
  · `text=True` num `subprocess` descodifica com o codec do LOCALE (cp1252 no
    Windows) e rebenta no primeiro 漢字 ⇒ `encoding="utf-8"` explicito.
  · "Traceback no stderr" nao detecta crash. O sinal honesto e' o RODAPE: se a
    suite chegou ao fim, ela imprime-o.

E a terceira, desta sessao: uma sabotagem cujo alvo nao existe **da-se por
boa**. Por isso cada alvo e' contado ANTES.

Uso:  python scripts/_sabota_varredor.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DE = os.path.join(ROOT, "core", "duel_engine.py")

SABOTAGENS = [
    # (rotulo, ficheiro, de, para, agulha que TEM de estar no vermelho)
    # ⚠️ O ALVO LEVA A LINHA DE CIMA. `DuelSession.state.in_(DUEL_OPEN_STATES),`
    # sozinho aparece DUAS vezes no ficheiro (aqui e no
    # `unlock_stuck_duels_for_player`) e a sabotagem recusava-se a correr,
    # dizendo-o. Uma sabotagem de alvo ambiguo nao e' uma sabotagem — e a
    # alternativa (baixar para `replace(...)` sem contar) seria pior: mudava o
    # sitio errado e o vermelho falaria de outra coisa.
    ("volta a UMA query para abertos+terminais", DE,
     "                DuelSession.pve_source.in_(PVE_SOURCES),\n"
     "                DuelSession.state.in_(DUEL_OPEN_STATES),",
     "                DuelSession.pve_source.in_(PVE_SOURCES),\n"
     "                DuelSession.state.in_(DUEL_OPEN_STATES + DUEL_TERMINAL_STATES),",
     "NAO partilham o mesmo orcamento"),

    ("a metade que paga deixa de filtrar o carimbo", DE,
     '                ~DuelSession.action_log.contains([{"type": "pve_settled"}]),\n',
     "",
     "filtra `pve_settled` em SQL"),

    ("o registo-de-excepcao fica vazio", DE,
     'PVE_SOURCES_SETTLED_ELSEWHERE = ("arena_npc_fallback",)',
     'PVE_SOURCES_SETTLED_ELSEWHERE = ()',
     "o `arena_npc_fallback` esta la'"),

    ("fonte mal escrita no registo-de-excepcao", DE,
     'PVE_SOURCES_SETTLED_ELSEWHERE = ("arena_npc_fallback",)',
     'PVE_SOURCES_SETTLED_ELSEWHERE = ("arena_npc_falback",)',
     "toda fonte do registo-de-excepcao existe"),

    # ⚠️ a sabotagem que prova que o conserto nao se desfaz pelo lado errado:
    # excluir a arena da metade que DESTRANCA seria voltar a prender gente.
    ("a arena sai tambem da metade que destranca", DE,
     """        abertos = (await session.execute(
            select(DuelSession.id).where(
                DuelSession.pve_source.in_(PVE_SOURCES),""",
     """        abertos = (await session.execute(
            select(DuelSession.id).where(
                DuelSession.pve_source.in_(
                    [f for f in PVE_SOURCES if f not in PVE_SOURCES_SETTLED_ELSEWHERE]
                ),""",
     "FICA na metade que DESTRANCA"),

    ("o despachante volta a atirar a arena para o settle PvE", DE,
     "    if not settled and duel.pve_source in PVE_SOURCES_SETTLED_ELSEWHERE:",
     "    if False:",
     "NAO atira uma fonte com settle proprio"),

    ("desaparece a varredura dos abertos", DE,
     "                DuelSession.pve_source.in_(PVE_SOURCES),\n"
     "                DuelSession.state.in_(DUEL_OPEN_STATES),\n",
     "",
     "varredura SO' dos abertos"),
]


def run():
    falhas = []
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8").read()
        if orig.count(de) != 1:
            falhas.append("%-48s ALVO NAO ENCONTRADO (%d ocorrencias)"
                          % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(
            orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run(
                [sys.executable, os.path.join(ROOT, "scripts", "_test_relatos_0814.py")],
                capture_output=True, text=True, env=env, cwd=ROOT, timeout=600,
                encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.stderr or "")
            vermelhos = [l for l in saida.split("\n") if "FAIL:" in l]
            chegou_ao_fim = "passed ·" in saida
            mordeu = bool(vermelhos) and chegou_ao_fim
            acertou = mordeu and any(agulha in l for l in vermelhos)
            if acertou:
                print("  ok  %-48s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif not chegou_ao_fim:
                falhas.append("%-48s REBENTOU (a suite nao chegou ao rodape)" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-48s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-48s vermelha pelo motivo ERRADO (esperava %r)"
                              % (rot, agulha))
                print("  XX  " + falhas[-1])
        finally:
            io.open(path, "w", encoding="utf-8", newline="").write(orig)
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas), len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
