# -*- coding: utf-8 -*-
"""🐍 O JOGO CORRE EM PYTHON 3.11 — e a máquina de desenvolvimento em 3.12.

Porque existe (冶 3.1, 2026-09-29)
---------------------------------
O `Dockerfile` de produção é `FROM python:3.11-slim`. A máquina onde se
escreve o código tem 3.12, e o 3.12 (PEP 701) aceita dentro de uma f-string
coisas que o 3.11 recusa como `SyntaxError`:

    f"{x.emoji} *{_cname(lang, "cauldron", x)}*"     ← aspa IGUAL dentro de {}
    f"{'\\n'.join(linhas)}"                            ← barra dentro de {}

No 3.12 compila, os testes passam, o `ast.parse` diz que está bem (o
`feature_version=(3, 11)` NÃO apanha isto — medido). Em produção o ficheiro
inteiro não importa e o bot não arranca. Aconteceu a meio do 3.1: onze sítios
de caldeirão no `handlers/alchemy.py`, apanhados por ler o `Dockerfile`, não
por nenhum teste.

Como mede
---------
O tokenizador do 3.12 separa a f-string em FSTRING_START / FSTRING_MIDDLE /
FSTRING_END; tudo o resto que aparece entre o início e o fim está DENTRO de um
`{}`. Aí, uma STRING (ou uma f-string aninhada) que abre com a MESMA aspa
simples de uma f-string que a envolve, ou que contém uma barra, é sintaxe só
do 3.12.

⚠️ Corre num Python >= 3.12 (é o tokenizador novo que marca as f-strings) OU
no próprio 3.11, onde o `compile` de cada ficheiro é a verificação — e a mais
fiel, porque é o que o contentor diria. A CI da edição comunitária corre as
suites no 3.11 (Open Source F2, 2026-10-22: até aí esta auditoria rebentava no
Python da produção, e a `_test_web_c_superficies` com ela).

Uso:  python scripts/_audit_py311.py            # o relatorio
      python scripts/_audit_py311.py --json     # para a guarda
"""
from __future__ import annotations

import io
import json
import os
import sys
import tokenize

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# O que o contentor de produção IMPORTA. `scripts/` não vai para lá como código
# do jogo, mas entra também: um script de manutenção que não corre no servidor
# é um script que falha no dia em que é preciso.
DIRS = ("core", "handlers", "database", "migrations", "scripts", "tools", "community")
FILES = ("main.py", "config.py")
SKIP = ("__pycache__", "node_modules", ".git")

_PREFIX = "rRbBuUfF"


def _abre(tok: str) -> str:
    """A aspa com que um literal abre: `"`, `'`, `\"\"\"` ou `'''`."""
    body = tok.lstrip(_PREFIX)
    return body[:3] if body[:3] in ('"""', "'''") else body[:1]


def problemas(src: str) -> list[tuple[int, str]]:
    if not hasattr(tokenize, "FSTRING_START"):
        # Sem o tokenizador do 3.12: no 3.11 o `compile` É a verificação — o que
        # só o 3.12 aceita (PEP 701) é SyntaxError aqui, como no contentor.
        if sys.version_info[:2] != (3, 11):
            raise RuntimeError("precisa do Python 3.11 (o da produção) ou >= 3.12 "
                               "(o tokenizador que marca f-strings)")
        try:
            compile(src, "<auditado>", "exec", dont_inherit=True)
        except SyntaxError as e:
            return [(e.lineno or 0, "nao compila no 3.11: %s" % e.msg)]
        return []
    out: list[tuple[int, str]] = []
    pilha: list[str] = []   # a aspa de cada f-string aberta
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, SyntaxError) as e:
        return [(0, "nao tokeniza: %s" % e)]
    for tk in toks:
        if tk.type == tokenize.FSTRING_START:
            q = _abre(tk.string)
            if pilha and len(q) == 1 and any(len(o) == 1 and o == q for o in pilha):
                out.append((tk.start[0], "f-string aninhada com a MESMA aspa (%s)" % q))
            pilha.append(q)
        elif tk.type == tokenize.FSTRING_END:
            if pilha:
                pilha.pop()
        elif pilha and tk.type == tokenize.STRING:
            q = _abre(tk.string)
            if len(q) == 1 and any(len(o) == 1 and o == q for o in pilha):
                out.append((tk.start[0], "aspa %s dentro de {} de uma f-string %s" % (q, q)))
            if "\\" in tk.string:
                out.append((tk.start[0], "barra dentro de {} de uma f-string"))
    return out


def scan() -> dict:
    alvos: list[str] = [os.path.join(ROOT, f) for f in FILES]
    for d in DIRS:
        for dp, dns, fns in os.walk(os.path.join(ROOT, d)):
            # relativo à RAIZ: o caminho de quem clonou não decide o que se lê
            if any(s in os.path.relpath(dp, ROOT) for s in SKIP):
                continue
            alvos += [os.path.join(dp, f) for f in fns if f.endswith(".py")]
    achados: dict[str, list[tuple[int, str]]] = {}
    lidos = 0
    for p in sorted(alvos):
        if not os.path.exists(p):
            continue
        lidos += 1
        src = io.open(p, encoding="utf-8").read()
        pr = problemas(src)
        if pr:
            achados[os.path.relpath(p, ROOT).replace(os.sep, "/")] = pr
    return {"ficheiros": lidos, "achados": achados,
            "total": sum(len(v) for v in achados.values())}


if __name__ == "__main__":
    r = scan()
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False))
        raise SystemExit(0)
    print("🐍 sintaxe so' do 3.12 em %d ficheiros: %d" % (r["ficheiros"], r["total"]))
    for f, pr in r["achados"].items():
        for ln, m in pr:
            print("   %s:%d  %s" % (f, ln, m))
    raise SystemExit(1 if r["total"] else 0)
