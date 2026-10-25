# -*- coding: utf-8 -*-
"""⚔️ A BATERIA DE SABOTAGEM do report do [jogador] (03/10/2026) — a cena cabe no ecrã.

*"@saint_nivrael, bug: in PvE arena, popup of combat shows opponent's hp out of
bound on screen."* As guardas são duas: a de GEOMETRIA
(`scripts/_test_cena_cabe.py`, mede num Chrome a 320–1440) e a §10 do
`scripts/_test_relatos_0814.py` (o nome da origem no vão, contra o tuplo do servidor).
Uma guarda que não morde não guarda — e esta tela já transbordou DUAS vezes com
mil guardas verdes por cima. Cada entrada estraga UMA coisa, corre a suite que
a deve apanhar, e exige que ela fique VERMELHA a dizer o quê.

As regras são as das baterias anteriores:
  · uma suite que REBENTA não é uma guarda vermelha (exige-se o rodapé);
  · uma sabotagem que não encontra o alvo dá-se por boa — cada alvo tem de
    aparecer EXACTAMENTE uma vez, verificado antes, ruidosamente;
  · os BYTES voltam iguais (lê com `newline=""`; o alvo ganha o fim de linha
    do ficheiro) — e cada ficheiro é conferido no fim.

⚠️ A suite de geometria compila o cliente sabotado numa pasta TEMPORÁRIA
(`NV_BUNDLE`): o `miniapp/dist` da árvore nunca fica com código estragado.

Uso:  python -X utf8 scripts/_sabota_a_cena_cabe.py      (~10 min: 11 × a geometria)
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CABE = os.path.join(ROOT, "scripts", "_test_cena_cabe.py")
RELATOS = os.path.join(ROOT, "scripts", "_test_relatos_0814.py")
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
ARNES = os.path.join(ROOT, "scripts", "_dev_serve_miniapp.py")
MOTOR = os.path.join(ROOT, "core", "duel_engine.py")
MI_ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")

# (rótulo, ficheiro, de, para, pedaço que TEM de aparecer no vermelho, suite)
SABOTAGENS = [
    # ── a geometria (o report) ──────────────────────────────────────────────
    ("o par valor+maximo volta a ser nowrap (o bug de 03/10)", UI,
     "            .cena-duelo .cena-faixa-num { font-size:12px; line-height:16px;\n"
     "              color:var(--cena-paper); letter-spacing:-.1px; }",
     "            .cena-duelo .cena-faixa-num { font-size:12px; line-height:16px;\n"
     "              color:var(--cena-paper); letter-spacing:-.1px; white-space:nowrap; }",
     "nada sai da coluna", CABE),
    ("o vao volta a ser AUTO (cresce antes dos lados)", UI,
     "grid-template-columns:minmax(0,1fr) fit-content(64px) minmax(0,1fr);",
     "grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);",
     "tamanho inteiro", CABE),
    ("o vao herda o anywhere da janela (EXPLORATI / ON)", UI,
     "              align-content:start; max-width:112px; padding-top:6px;\n"
     "              overflow-wrap:normal; }",
     "              align-content:start; max-width:112px; padding-top:6px; }",
     "partido a meio", CABE),
    ("o numero perde os wbr (sem container queries parte a meio)", UI,
     '        if ((c < "0" || c > "9") && i < s.length - 1) {',
     "        if (false) {",
     "nunca a meio de um", CABE),
    ("as metades deixam de ser unidades (inline-block)", UI,
     "            .cena-duelo .cena-faixa-val,\n"
     "            .cena-duelo .cena-faixa-max,\n"
     "            .cena-duelo .cena-faixa-maxn { display:inline-block; }\n",
     "",
     "inteiro numa linha", CABE),
    ("o numero do maximo deixa de ser a sua unidade", UI,
     "            .cena-duelo .cena-faixa-max,\n"
     "            .cena-duelo .cena-faixa-maxn { display:inline-block; }\n",
     "            .cena-duelo .cena-faixa-max { display:inline-block; }\n",
     "número de cada máximo", CABE),
    ("o numero deixa de encolher (parte a 360/320)", UI,
     "                font-size:max(8px, min(12px, calc(98cqi / var(--cena-em, 1)))); }",
     "                font-size:12px; }",
     "cada vida fica inteira", CABE),
    ("o numero encolhe ate' onde cabia inteiro", UI,
     "                font-size:max(8px, min(12px, calc(98cqi / var(--cena-em, 1)))); }",
     "                font-size:max(8px, min(12px, calc(80cqi / var(--cena-em, 1)))); }",
     "tamanho inteiro", CABE),
    ("a cena perde o nome da arena (volta a dizer Duelo)", UI,
     '      arena_npc_fallback: "cena_fonte_arena",\n',
     "",
     "o vão diz a origem", CABE),
    # ── as anti-guardas (a suite tem de ver que mede a coisa certa) ──────────
    ("o arnes ignora o NV_DUELO_HP (numeros de mentira)", ARNES,
     '        _hp_raw = (os.environ.get("NV_DUELO_HP") or "").strip().lower()',
     '        _hp_raw = ""',
     "os números de produção", CABE),
    ("o arnes serve o dist da arvore e nao o compilado agora", ARNES,
     '        elif path == "/miniapp/dist/bundle.js" and os.environ.get("NV_BUNDLE"):',
     "        elif False:",
     "serve o bundle compilado agora", CABE),
    # ── a §10: o nome da origem contra o servidor ───────────────────────────
    ("uma chave morta volta a' tabela", UI,
     '      arena_npc_fallback: "cena_fonte_arena",\n',
     '      arena_npc_fallback: "cena_fonte_arena",\n      arena:              "cena_fonte_arena",\n',
     "nenhuma chave morta", RELATOS),
    ("uma origem do servidor fica sem nome na cena", UI,
     '      jianghu_ambush:     "cena_fonte_emboscada",\n',
     "",
     "toda origem PvE do servidor tem nome", RELATOS),
    ("o servidor ganha uma origem nova e a cena nao", MOTOR,
     '    "jianghu_ambush",       # core/jianghu_engine.py         (JH_AMBUSH_SOURCE)\n',
     '    "jianghu_ambush",       # core/jianghu_engine.py         (JH_AMBUSH_SOURCE)\n'
     '    "torneio_celeste",\n',
     "toda origem PvE do servidor tem nome", RELATOS),
    ("um nome falta numa lingua", MI_ES,
     '  "cena_fonte_desafio": "Desafío",\n',
     "",
     "nas tres linguas", RELATOS),
]


def _ler(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _gravar(path, texto):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(texto)


def run():
    falhas = []
    originais = {}
    for _r, path, _d, _p, _a, _s in SABOTAGENS:
        originais.setdefault(path, _ler(path))
    for rot, path, de, para, agulha, suite in SABOTAGENS:
        orig = _ler(path)
        if "\r\n" in orig:
            de, para = de.replace("\n", "\r\n"), para.replace("\n", "\r\n")
        if orig.count(de) != 1:
            falhas.append("%-58s ALVO NAO ENCONTRADO (%d ocorrencias) — a sabotagem "
                          "dava-se por boa sem nunca ter corrido" % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        _gravar(path, orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, "-X", "utf8", suite], capture_output=True,
                               text=True, env=env, cwd=ROOT, timeout=900,
                               encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n") if l.startswith("  FAIL: ")]
            rebentou = " passed · " not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and any(agulha in l for l in vermelhos)
            if acertou:
                print("  ok  %-58s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-58s REBENTOU — uma suite que rebenta nao e' uma guarda "
                              "vermelha" % rot)
                print("  XX  " + falhas[-1])
                print("      " + (saida.strip().split("\n") or [""])[-1][:200])
            elif not mordeu:
                falhas.append("%-58s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-58s ficou vermelha pelo motivo ERRADO (esperava %r)"
                              % (rot, agulha))
                print("  XX  " + falhas[-1])
                for l in vermelhos[:3]:
                    print("      " + l.strip()[:200])
        finally:
            _gravar(path, orig)
            if _ler(path) != orig:
                print("  !!  %s NAO VOLTOU IGUAL — parar e ver a mao" % path)
                return 2
    for path, orig in originais.items():
        if _ler(path) != orig:
            print("  !!  %s NAO VOLTOU IGUAL no fim" % path)
            return 2
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas), len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
