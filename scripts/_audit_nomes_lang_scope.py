# -*- coding: utf-8 -*-
"""名 A GUARDA DO `lang` — uma chamada ao resolvedor com `lang` nao ligado.

Porque existe
-------------
O resolvedor (`catalog_name` / `catalog_desc`) precisa da lingua. Trocar
`tech.name` por `_cname(lang, "tech", tech)` num sitio onde `lang` nao existe
**compila** e so' rebenta em producao, na mao do jogador, com `NameError`.
A Lei §1 diz que um erro nunca tira o tap — portanto isto nao pode chegar la'.

Percorre a AST: para cada chamada ao resolvedor, confirma que o 1o argumento e'
um nome LIGADO na funcao que a contem (parametro, atribuicao, `for`, `with`,
walrus) ou um atributo/expressao (ex. `player.language`), que e' sempre valido.

Uso
---
    python scripts/_audit_nomes_lang_scope.py      # vazio = verde
"""
from __future__ import annotations

import ast
import builtins
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOLVERS = {"catalog_name", "catalog_desc", "catalog_text", "_cname", "_cdesc", "_cat_t"}
# `/nivrael-community` — a edição comunitária quando vive dentro desta árvore
# (outro projecto, com o seu próprio código: lê-la aqui duplicava cada achado)
SKIP = (".git", "node_modules", "__pycache__", "/tmp", "dist", "scratch", "website", "/nivrael-community")


def _module_names(tree: ast.Module) -> set[str]:
    """So' os nomes ligados no ESCOPO DO MODULO.

    ⚠️ 2026-09-15 — esta funcao existe porque a guarda nasceu CEGA. A versao
    anterior fazia `ast.walk(tree)` e apanhava **todo** o `Store` do ficheiro,
    incluindo os de dentro das funcoes: um `lang = player.language` na linha 65
    de `handlers/quests.py` marcava `lang` como ligado nas outras 20 funcoes do
    mesmo ficheiro. Resultado medido: a guarda dizia VERDE enquanto o
    `_claim_quest` rebentava com `NameError: name 'lang' is not defined` na mao
    de 3 jogadores, 7 vezes em 2 dias. Nao descer aos corpos e' o ponto todo.
    """
    names: set[str] = set(dir(builtins))
    def visit(body) -> None:
        for st in body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(st.name)          # o nome liga; o CORPO nao se visita
                continue
            if isinstance(st, (ast.Import, ast.ImportFrom)):
                for al in st.names:
                    names.add((al.asname or al.name).split(".")[0])
                continue
            for node in ast.walk(st):
                if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                    names.add(node.id)
                elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
                    names.add(node.target.id)
            # ramos de topo (if/try/for/while) ainda sao escopo do modulo
            for attr in ("body", "orelse", "finalbody"):
                inner = getattr(st, attr, None)
                if inner and not isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                 ast.ClassDef)):
                    visit([s for s in inner
                           if isinstance(s, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                                             ast.AsyncFunctionDef, ast.ClassDef))])
            for h in getattr(st, "handlers", []) or []:
                visit([s for s in h.body
                       if isinstance(s, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                                         ast.AsyncFunctionDef, ast.ClassDef))])
    visit(tree.body)
    return names


def _enclosing(tree: ast.Module) -> dict:
    """Cada funcao -> a funcao que a contem (para as closures nao darem falso)."""
    parent: dict = {}
    def walk(node, cur):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parent[child] = cur
                walk(child, child)
            else:
                walk(child, cur)
    walk(tree, None)
    return parent


def _bound_names(fn: ast.AST) -> set[str]:
    """Todos os nomes que a funcao LIGA (args, atribuicoes, for, with, walrus)."""
    names: set[str] = set()
    a = getattr(fn, "args", None)
    if a is not None:
        for grp in (a.posonlyargs, a.args, a.kwonlyargs):
            for arg in grp:
                names.add(arg.arg)
        if a.vararg:
            names.add(a.vararg.arg)
        if a.kwarg:
            names.add(a.kwarg.arg)
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Global):
            names.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            names.update(node.names)
    return names


def main() -> int:
    bad: list[str] = []
    checked = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # relativo à RAIZ (Open Source F2, 22/10) — um clone em `/tmp/…` não pode
        # esconder a árvore inteira deste varredor
        if any(s in "/" + os.path.relpath(dirpath, ROOT).replace(os.sep, "/") for s in SKIP):
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
            try:
                tree = ast.parse(open(full, encoding="utf-8").read())
            except Exception:
                continue
            module_names = _module_names(tree)
            parent = _enclosing(tree)
            funcs = [n for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            for f in funcs:
                bound = _bound_names(f) | module_names
                up = parent.get(f)          # closures: o escopo de cima conta
                while up is not None:
                    bound |= _bound_names(up)
                    up = parent.get(up)
                for node in ast.walk(f):
                    if not isinstance(node, ast.Call):
                        continue
                    name = (node.func.id if isinstance(node.func, ast.Name)
                            else getattr(node.func, "attr", None))
                    if name not in RESOLVERS or not node.args:
                        continue
                    checked += 1
                    first = node.args[0]
                    if isinstance(first, ast.Name) and first.id not in bound:
                        bad.append(f"{rel}:{node.lineno}: {f.name}() chama "
                                   f"{name}({first.id}, …) e `{first.id}` nao esta ligado")
    print(f"名 GUARDA DO lang — {checked} chamadas ao resolvedor verificadas")
    for b in bad:
        print("   !! " + b)
    if bad:
        print(f"   VERMELHO: {len(bad)} chamada(s) com a lingua nao ligada")
        return 1
    print("   VERDE: todas as chamadas tem a lingua ligada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
