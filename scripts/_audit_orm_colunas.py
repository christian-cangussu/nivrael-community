# -*- coding: utf-8 -*-
"""🗄️ TODA A `Modelo.coluna` DO CÓDIGO EXISTE NO MODELO.

Porque existe (report de 2026-09-30)
------------------------------------
*"@saint, bug: error 500 on selecting default arts for duels, in Loadout
screen"*. A rota `combat/default_strike` filtrava `PlayerTechnique.is_active`;
a coluna chama-se `is_active_combat`. Um atributo que não existe numa classe do
SQLAlchemy só rebenta QUANDO a linha corre: o `import` passa, o `ast.parse`
passa, as guardas de texto passam — e o arnês devolvia `ok: true` sem chamar a
rota. No Nivrael Beta, desde que a flag `golpe_padrao` ligou: **0 escolhas
gravadas**, com os 38 jogadores de arte equipada.

A primeira passagem deste varredor achou um SEGUNDO igual, que nenhum jogador
tinha ainda pisado: o chat filtrava `Tribulation.result` (a coluna é `outcome`)
ao subir uma técnica ao grau celestial. 4002 referências lidas, 2 partidas.

Como mede
---------
Importa `database.models` e colhe as classes mapeadas (as subclasses de `Base`).
Em cada ficheiro segue os nomes importados de `database.models` (com o `as`, em
qualquer escopo) e, para cada `Nome.atributo` da AST cujo `Nome` é um modelo,
pergunta à CLASSE se o atributo existe (`hasattr` — cobre colunas, relações,
`__table__`, métodos). Pergunta ao modelo, nunca a uma lista escrita à mão.

Pontos cegos (medidos a 2026-09-30, declarados)
-----------------------------------------------
- SQL cru em `text(...)`: 26 em `core/` + `handlers/` — são strings; só a base
  os verifica (as sondas `tools/db_readonly_*` correm-nos só-leitura).
- atributos de INSTÂNCIA (`player.foo`): o tipo não se sabe sem correr. Ler um
  atributo inexistente rebenta igual; ESCREVER um cria um atributo Python solto
  e não grava nada — calado.
- `aliased(...)`, `getattr(Modelo, "...")`, `import database.models as m`,
  `from database import models`: 0 usos hoje. Se nascerem, ficam fora do
  varredor — a guarda conta as referências vistas para dar por um recuo.

Uso:  python scripts/_audit_orm_colunas.py            # o relatorio
      python scripts/_audit_orm_colunas.py --json     # para a guarda
"""
from __future__ import annotations

import ast
import io
import json
import os
import sys
import warnings

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

MODULO = "database.models"
# Tudo o que tem `.py` no repositório — o jogo, os seeds, as migrations em
# Python, os scripts e as ferramentas. Um script de manutenção com uma coluna
# que não existe é um script que falha no dia em que é preciso.
# `rea-runtime` — ferramentas de TERCEIROS que podem viver numa árvore de
# trabalho local (scripts Jython, Python 2): não são código do jogo e só
# dariam falsos alarmes.
# `nivrael-community` — a edição comunitária quando vive dentro desta árvore:
# outro projecto, com o seu próprio código (lê-la aqui duplicava cada achado).
SKIP = ("__pycache__", "node_modules", ".git", "dist", "rea-runtime", "nivrael-community")


def modelos() -> dict[str, type]:
    """As classes mapeadas, pelo nome — lidas do módulo, não de uma lista."""
    import database.models as M
    from database.db import Base
    return {n: c for n, c in vars(M).items()
            if isinstance(c, type) and issubclass(c, Base) and c is not Base}


def problemas(src: str, mods: dict[str, type]) -> tuple[int, list[tuple[int, str]]]:
    """Para UM ficheiro: (referências a modelos vistas, [(linha, "Modelo.attr")])."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(src)
    except SyntaxError as e:
        return 0, [(e.lineno or 0, "nao analisa: %s" % e.msg)]
    nomes: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == MODULO:
            for a in node.names:
                if a.name in mods:
                    nomes[a.asname or a.name] = a.name
    if not nomes:
        return 0, []
    vistas, out = 0, []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in nomes):
            vistas += 1
            cls = nomes[node.value.id]
            if not hasattr(mods[cls], node.attr):
                out.append((node.lineno, "%s.%s" % (cls, node.attr)))
    return vistas, sorted(out)


def scan() -> dict:
    mods = modelos()
    alvos: list[str] = []
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP and not d.startswith(".")]
        alvos += [os.path.join(dp, f) for f in fns if f.endswith(".py")]
    achados: dict[str, list[tuple[int, str]]] = {}
    lidos = vistas = 0
    for p in sorted(alvos):
        lidos += 1
        src = io.open(p, encoding="utf-8").read()
        v, pr = problemas(src, mods)
        vistas += v
        if pr:
            achados[os.path.relpath(p, ROOT).replace(os.sep, "/")] = pr
    return {"modelos": len(mods), "ficheiros": lidos, "referencias": vistas,
            "achados": achados, "total": sum(len(v) for v in achados.values())}


if __name__ == "__main__":
    r = scan()
    if "--json" in sys.argv:
        print(json.dumps(r, ensure_ascii=False))
        raise SystemExit(0)
    print("🗄️ %d modelos · %d ficheiros · %d referencias `Modelo.coluna` · %d partidas"
          % (r["modelos"], r["ficheiros"], r["referencias"], r["total"]))
    for f, pr in r["achados"].items():
        for ln, m in pr:
            print("   %s:%d  %s" % (f, ln, m))
    raise SystemExit(1 if r["total"] else 0)
