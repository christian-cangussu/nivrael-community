# -*- coding: utf-8 -*-
"""名 A AUDITORIA DO NOME CRU — onde e' que o jogo AINDA imprime o nome em ingles.

Porque existe
-------------
O prompt de 2026-09-14 mandava CONTAR antes de traduzir a primeira linha, e a
contagem derrubou a premissa que ele trazia. O prompt dizia que
`core.i18n.catalog_text` "serve as 4 familias (artefactos, pilulas, ervas,
tecnicas)". MEDIDO: `_CATALOG_KINDS` ACEITA seis familias, mas **so' `tech` tem
chamadores** — 5, todos em `core/webserver.py`. As outras cinco tem ZERO.

E o achado que reorganizou o lote todo:

    o CONTEUDO das tecnicas esta' COMPLETO    — 129 x 2 campos x 3 linguas
    o ENCANAMENTO chegava a 9 de 41 sitios

...e 4 desses 9 eram uma SEGUNDA implementacao a' mao
(`t_optional(lang, f"tech_{id}_name", …)` em `sect_library_engine` e
`legacy_cave_engine`) — as "duas ligacoes a' mao" que a Lei F-7 §2 proibe.

Consequencia, na lingua de 125 dos 241 jogadores do main: **o chat imprime o
nome CRU** das 129 artes (12 leituras so' em `handlers/combat.py`) enquanto o
mini-app imprime o traduzido. O jogador pt-BR le' "Thunder Step" no chat e
"Passo do Trovao" na app. A Lei 0 e' explicita: a inconsistencia e' PIOR do que
a ausencia.

O que esta auditoria mede, e o que NAO mede
-------------------------------------------
Mede: leituras de `.name` / `.description` em ficheiros que importam um dos
catalogos, que NAO passam pelo resolvedor, fora da lista de atributos que
sabemos nao serem de catalogo (`dao_name`, `first_name`, `__name__`, ...).

⚠️ NAO mede dataflow. Uma leitura crua atraves de um nome de variavel novo conta
como leitura crua (bom: a catraca sobe e a guarda parte), mas uma leitura de
`.name` que nao e' de catalogo tambem conta (mau: inflaciona o numero). E' por
isso que o numero nao e' "nomes crus" mas sim **"leituras de .name/.description
sem resolvedor nos ficheiros que mexem em catalogos"**, e o que a guarda exige
dele e' uma coisa so': **que desca**. Mesmo contrato da catraca do emoji (§15).

⚠️ Filtra comentarios. A licao de 13/09 foi paga duas vezes: uma guarda que le'
a PROSA encontrou `orb-burst` no comentario que explicava que ele sobreviveu, e
a animacao inteira ficou sabotada com a guarda VERDE. O filtro de comentarios
tem anti-guarda nas duas direccoes no `_sabota_os_nomes.py`.

Uso
---
    python scripts/_audit_nomes_crus.py            # o relatorio
    python scripts/_audit_nomes_crus.py --json     # para a guarda
    python scripts/_audit_nomes_crus.py --lines    # cada linha, para corrigir

A GUARDA que impede isto de crescer vive em `scripts/_test_relatos_0814.py` (§N) e
importa este ficheiro.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# As seis familias que o `_CATALOG_KINDS` serve, pelo nome da classe do modelo.
CATALOG_MODELS = (
    "ArtifactCatalog",
    "PillCatalog",
    "HerbCatalog",
    "OreCatalog",
    "BeastCatalog",
    "TechniqueCatalog",
    # ── 2026-09-14, e estas DUAS entraram pela mao do owner ─────────────────
    # Ele mandou uma captura do ecra do Chefe, em espanhol, a dizer
    # "VOID BEAST" e "Attack World Boss — toca para reclamar la recompensa".
    # A minha contagem tinha as SEIS de cima e falhava exactamente as duas
    # superficies de nome MAIS VISTAS do jogo: o chefe do mundo e a missao
    # diaria. E' a Lei F-7 a funcionar ao contrario — quem contou fui eu, e
    # contei a menos; quem foi ver o ecra foi ele.
    "WorldBoss",
    "QuestCatalog",
    # ── 旅 2026-09-15 — a EXPEDICAO, e ela faltava aqui por omissao ────────
    # A tela das bestas ficou MEIA traduzida: "Boi do Trovao em Herb
    # Expedition" na mesma frase. A familia nunca esteve nesta tupla,
    # portanto a catraca dizia 0 crus com a expedicao inteira em ingles.
    # ⚠️ Esta e' a 3a familia a entrar DEPOIS de alguem ver o ecra (as duas
    # de cima vieram pela mao do owner). Contar sitios nao e' grep: e'
    # perguntar que familias EXISTEM antes de medir as que ja' estao na lista.
    "ExpeditionCatalog",
    # ── 冶 2026-09-29 — o CALDEIRAO, a 4.a familia a entrar depois de a
    # contagem a falhar. Os 7 nunca tiveram traducao: o corpo da Alquimia
    # dizia "Copper Cauldron" em pt e em es, em SEIS telas do chat e no
    # mini-app. Achado a medir o Atelie, nao por esta auditoria.
    "CauldronCatalog",
)

# Chamar QUALQUER uma destas na linha conta como "passa pelo resolvedor".
RESOLVERS = re.compile(
    r"\bcatalog_name\b|\bcatalog_desc\b|\bcatalog_text\b|\b_cat_t\b|\b_tname\b|\b_tdesc\b"
    # 獸 2026-09-15 — o dono unico da familia BESTA (e os dois alias com que
    # ele entra nos ficheiros que o importam). Ele proprio chama o
    # `catalog_name`; esta linha e' o que impede os sitios que o chamam de
    # continuarem a contar como crus.
    r"|\bbeast_display_name\b|\b_bdn_exp\b|\b_cat_t_b\b"
    # 旅 2026-09-15 — o dono unico da EXPEDICAO e os 3 alias com que ele entra
    # nos ficheiros. ⚠️ Isto NAO faz a familia passar a ser CONTADA: a
    # auditoria liga um MODELO a uma variavel e le' `.name` nela, e aqui o
    # nome cru vem de `PlayerBeast.expedition_type` (coluna de texto) e de um
    # `for e in lista` — segundo salto, que ela nao segue. A guarda desta
    # familia e' o §8.12 do `_test_relatos_0814.py`, e existe exactamente por isso.
    r"|expedition_display_name|expedition_display_desc"
    r"|_exp_name|_exp_name_ws|_exp_desc_ws"
)

# Atributos `.name` / `.description` que NAO sao de catalogo. Sem isto o numero
# e' ruido: `player.dao_name`, `path.name`, `func.__name__`, ...
# ⚠️ 2026-09-15 — `custom_name` SAIU desta lista, e a razao e' uma licao.
# Enquanto la' esteve, QUALQUER linha que a mencionasse saia da conta
# INTEIRA — e a forma de toda a familia BESTA era exactamente
# `b.custom_name or (c.name if c else "???")`. O varredor dizia ZERO com as
# 15 bestas cruas em SETE telas do chat: verde sobre o conjunto vazio (Lei 0
# passo 4), o mesmo modo de falha que a mochila teve a 14/09 por outra forma.
# ⚠️ Tirar daqui nao inventa leitura nenhuma: `b.custom_name` sozinho NUNCA
# contou, porque o `READ` exige um PONTO imediatamente antes de `name`. So'
# devolve a vista das leituras de catalogo que partilhavam a linha com ela.
NOT_CATALOG = re.compile(
    r"\b(?:"
    r"dao_name|first_name|last_name|user_name|username|full_name|"
    r"spirit_name|display_name|file_name|table_name|column_name|field_name|"
    r"grade_name|stage_name|tier_name|realm_name|mastery_name|slot_name|"
    r"sect_name|faction_name|city_name|npc_name|"
    r"region_name|continent_name|world_name|law_name|title_name|rank_name|"
    r"effect_name|item_name|pill_name|exp_name|lang_name|locale_name|"
    r"__name__|__description__"
    r")\b"
)

# O marcador da lista DECLARADA. Exige MOTIVO escrito depois dos dois pontos —
# um `# 名-CRU:` pelado nao declara nada (Lei 0 passo 5: "pendente" e' legitimo,
# "esquecido" nao e'; e um motivo em branco e' "esquecido" com enfeite).
_DECLARED = re.compile(r"#\s*名-CRU:\s*\S")

# A leitura: `<algo>.name` ou `<algo>.description`.
READ = re.compile(r"\.(?:name|description)\b")
READ_VAR = re.compile(r"\b([A-Za-z_]\w*)\.(?:name|description)\b")

# ── 🔴 O BURACO QUE ESTE VARREDOR TEVE, e que custou o ecra mais visto ──────
#
# A 2026-09-14 este ficheiro disse "0 leituras cruas" com a MOCHILA inteira a
# sair em ingles. O motivo: o `api_inventory` nao le' `cat.name` — faz
# `select(ArtifactCatalog.name, ...)` e DESEMPACOTA o tuplo, ficando com uma
# variavel chamada `name` que nao tem ponto nenhum. Um varredor que procura
# `<algo>.name` nao ve' nada ali, e a contagem fica verde sobre o conjunto
# vazio — o mesmo modo de falha que a Lei 0 passo 4 nomeia.
#
# Agora ha' uma segunda medicao, independente da primeira: toda `select(...)`
# que peca a COLUNA `name`/`description` de um catalogo tem de ter, na mesma
# funcao, uma chamada ao resolvedor. Nao diz QUAL linha esta' crua — diz que a
# funcao pede o nome ao SQL e nunca o traduz, que e' o que importa.
_COL_SELECT = re.compile(
    r"\b(?:" + "|".join(
        ["ArtifactCatalog", "PillCatalog", "HerbCatalog", "OreCatalog",
         "BeastCatalog", "TechniqueCatalog", "WorldBoss", "QuestCatalog",
         "CauldronCatalog"]
    ) + r")\.(?:name|description)\b"
)

# ── dataflow-lite: QUE variaveis e' que guardam uma linha de catalogo ────────
#
# Sem isto o numero e' ruido: `sect.name`, `quest.name` e `boss.name` contavam
# como nome cru de item. Com isto, conta-se a leitura SO' quando a variavel foi
# ligada, no mesmo ficheiro, a uma consulta que menciona um dos seis catalogos.
#
# ⚠️ Por ficheiro, nao por funcao — de proposito. Uma variavel chamada `cat` num
# ficheiro que consulta o `PillCatalog` e' uma linha de catalogo em qualquer
# funcao desse ficheiro, e preferimos contar a mais do que deixar passar.
_BIND = re.compile(
    r"^\s*(?:for\s+)?([\w,\s()]+?)\s*(?:=|\bin\b)\s*(.*)$"
)
# nomes que, nestes ficheiros, sao SEMPRE linha de catalogo (medido 14/09)
ALWAYS_CATALOG_VARS = {
    "tech", "tc", "tech_cat", "t_cat", "cat", "catalog", "pill_cat", "pc",
    "herb_cat", "hc", "ore_cat", "oc", "art_cat", "ac", "beast_cat", "bc",
    "pill", "herb", "ore", "arte",
    # 2026-09-14 — as duas que o owner apanhou na captura
    "boss", "wb", "world_boss", "quest", "q", "quest_cat", "qc",
    # 冶 2026-09-29 — o caldeirao chega quase sempre por `get_equipped_cauldron`
    # (2.o salto, que a ligacao modelo->variavel nao segue); o nome da
    # variavel e' estavel em todo o codigo.
    "cauldron", "next_cauldron",
}


def _catalog_vars(lines: list[str]) -> set[str]:
    """As variaveis que, neste ficheiro, guardam uma linha de um dos catalogos."""
    found: set[str] = set()
    alias: set[str] = set()
    for line in lines:
        # `from database.models import ArtifactCatalog as _AC`
        for m in re.finditer(r"\b(?:" + "|".join(CATALOG_MODELS) + r")\s+as\s+(\w+)", line):
            alias.add(m.group(1))
    models = set(CATALOG_MODELS) | alias
    mpat = re.compile(r"\b(?:" + "|".join(re.escape(x) for x in models) + r")\b")
    for line in lines:
        if not mpat.search(line):
            continue
        m = _BIND.match(line)
        if not m:
            continue
        lhs = m.group(1)
        for name in re.findall(r"\b([A-Za-z_]\w*)\b", lhs):
            if name in ("select", "await", "for", "in", "if", "return", "self"):
                continue
            found.add(name)
    return (found | ALWAYS_CATALOG_VARS)

# Ficheiros que nao sao produto (testes, sabotagens, seeds, ferramentas).
# `/nivrael-community` — a edição comunitária quando vive dentro desta árvore:
# outro projecto, com o seu próprio código (lê-la aqui duplicava cada achado).
SKIP_DIRS = (".git", "node_modules", "__pycache__", "/tmp", "dist", "scratch", "/seeds", "website",
             "/nivrael-community")
SKIP_FILE = re.compile(r"(?:^|/)(?:_test_|_sabota_|_audit_|_dev_|db_readonly_|db_write_)")


def _strip_comments_py(src: str) -> list[str]:
    """Devolve as linhas com os comentarios `#` e as docstrings apagados.

    ⚠️ Apaga o COMENTARIO, nunca o codigo: `x = y  # .name` perde o comentario e
    mantem `x = y`. Provado nas duas direccoes em `_sabota_os_nomes.py`.
    """
    out: list[str] = []
    in_doc = False
    doc_q = ""
    for line in src.splitlines():
        s = line
        if in_doc:
            if doc_q in s:
                s = s.split(doc_q, 1)[1]
                in_doc = False
            else:
                out.append("")
                continue
        # docstring/literal de bloco que ABRE e nao fecha nesta linha
        for q in ('"""', "'''"):
            if s.count(q) % 2 == 1:
                s = s.split(q, 1)[0]
                in_doc, doc_q = True, q
                break
        # comentario de fim de linha, respeitando strings simples
        cut = None
        in_str = ""
        i = 0
        while i < len(s):
            ch = s[i]
            if in_str:
                if ch == "\\":
                    i += 2
                    continue
                if ch == in_str:
                    in_str = ""
            elif ch in "\"'":
                in_str = ch
            elif ch == "#":
                cut = i
                break
            i += 1
        if cut is not None:
            s = s[:cut]
        out.append(s)
    return out


def scan() -> dict:
    per_file: dict[str, int] = {}
    lines_out: dict[str, list[tuple[int, str]]] = {}
    declared: list[tuple[str, int, str]] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # ⚠️ RELATIVO à raiz (Open Source F2, 22/10): com o caminho absoluto, um
        # clone em `/tmp/…` ou numa pasta `scratch`/`dist`/`website` saltava a
        # árvore INTEIRA — o varredor via zero e a anti-guarda ficava vermelha.
        rel_dir = "/" + os.path.relpath(dirpath, ROOT).replace(os.sep, "/")
        if any(s in rel_dir for s in SKIP_DIRS):
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT).replace(os.sep, "/")
            if SKIP_FILE.search("/" + rel):
                continue
            try:
                src = open(full, encoding="utf-8").read()
            except Exception:
                continue
            # so' ficheiros que mexem em catalogos
            if not any(m in src for m in CATALOG_MODELS):
                continue
            clean = _strip_comments_py(src)
            raw_lines = src.splitlines()
            cat_vars = _catalog_vars(clean)
            hits: list[tuple[int, str]] = []
            for n, line in enumerate(clean, 1):
                if not READ.search(line):
                    continue
                if RESOLVERS.search(line):
                    continue
                # 冶 2026-09-29 — o `NOT_CATALOG` deixou de tirar a LINHA da conta.
                # Era o defeito do `custom_name` de 15/09 na forma geral: qualquer
                # linha que MENCIONASSE `pill_name`/`grade_name`/`stage_name` saia
                # inteira, com a leitura crua dentro. Medido no dia: 15 leituras
                # escondidas (`"pill_name": pill.name` x3 no webserver, 12 no chat).
                # ⚠️ Nao se perde precisao: o `READ` exige um PONTO colado a `name`,
                # logo `x.dao_name`/`f.__name__` nunca foram leituras; e a leitura so'
                # conta se o DONO for uma variavel de catalogo (linha abaixo).
                # A regex fica como a lista do que NAO e' catalogo, consultada por
                # quem quiser saber porque um atributo nao conta.
                # a leitura SO' conta se o dono dela for uma linha de catalogo,
                # ou se for a coluna crua (`PillCatalog.name`) — que tambem e'.
                owners = set(READ_VAR.findall(line))
                if not (owners & cat_vars):
                    continue
                # ── a lista DECLARADA: sitios que TEM de ficar crus ──────────
                # ⚠️ Lida da linha ORIGINAL (com comentarios), nao da limpa — e' o
                # unico sitio onde o comentario e' o assunto e nao ruido. Um
                # `# 名-CRU: <motivo>` na linha ou na linha de cima tira-a da
                # conta; sem motivo escrito NAO conta como declarada.
                window = "\n".join(raw_lines[max(0, n - 3):n])
                if _DECLARED.search(window):
                    declared.append((rel, n, line.strip()[:100]))
                    continue
                hits.append((n, line.strip()[:120]))
            if hits:
                per_file[rel] = len(hits)
                lines_out[rel] = hits
    return {
        "per_file": dict(sorted(per_file.items(), key=lambda kv: -kv[1])),
        "total": sum(per_file.values()),
        "lines": lines_out,
        "declared": declared,
        "col_muda": _scan_colunas_mudas(),
    }


def _scan_colunas_mudas() -> list[tuple[str, str, int]]:
    """Funcoes que pedem a COLUNA `name`/`description` ao SQL e NUNCA resolvem.

    A segunda medicao, independente da primeira — ver a nota longa acima.
    Devolve (ficheiro, funcao, nº de colunas pedidas).
    """
    out: list[tuple[str, str, int]] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        # ⚠️ RELATIVO à raiz (Open Source F2, 22/10): com o caminho absoluto, um
        # clone em `/tmp/…` ou numa pasta `scratch`/`dist`/`website` saltava a
        # árvore INTEIRA — o varredor via zero e a anti-guarda ficava vermelha.
        rel_dir = "/" + os.path.relpath(dirpath, ROOT).replace(os.sep, "/")
        if any(x in rel_dir for x in SKIP_DIRS):
            continue
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/")
            if SKIP_FILE.search("/" + rel):
                continue
            try:
                src = open(os.path.join(dirpath, fn), encoding="utf-8").read()
            except Exception:
                continue
            if not _COL_SELECT.search(src):
                continue
            clean = "\n".join(_strip_comments_py(src))
            try:
                tree = ast.parse(clean)
            except SyntaxError:
                continue
            lines = clean.splitlines()
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                seg = "\n".join(lines[node.lineno - 1:(node.end_lineno or node.lineno)])
                n = len(_COL_SELECT.findall(seg))
                if not n or RESOLVERS.search(seg):
                    continue
                # a mesma lista DECLARADA da 1a medicao: uma coluna crua com
                # motivo escrito nao conta. Le-se do ORIGINAL (com comentarios),
                # que e' o unico sitio onde o comentario e' o assunto.
                raw_seg = "\n".join(
                    src.splitlines()[node.lineno - 1:(node.end_lineno or node.lineno)])
                if _DECLARED.search(raw_seg):
                    continue
                out.append((rel, node.name, n))
    return out


def main() -> int:
    res = scan()
    if "--json" in sys.argv:
        print(json.dumps({"per_file": res["per_file"], "total": res["total"],
                          "declared": len(res["declared"]),
                          "col_muda": len(res["col_muda"])},
                         ensure_ascii=False, indent=2))
        return 0
    print("=" * 74)
    print("  名 NOMES CRUS — leituras de .name/.description SEM resolvedor")
    print("=" * 74)
    for f, n in res["per_file"].items():
        print(f"   {n:4d}  {f}")
        if "--lines" in sys.argv:
            for ln, txt in res["lines"][f]:
                print(f"          {ln:6d}: {txt}")
    print("-" * 74)
    print(f"   TOTAL A CORRIGIR: {res['total']} leituras em {len(res['per_file'])} ficheiros")
    print(f"   DECLARADAS (tem de ficar cruas, com motivo): {len(res['declared'])}")
    print(f"   COLUNAS MUDAS (pede o nome ao SQL e nunca resolve): {len(res['col_muda'])}")
    for f, fnn, n in res["col_muda"]:
        print(f"          {f}::{fnn}()  ({n} coluna(s))")
    for f, ln, txt in res["declared"]:
        print(f"          {f}:{ln}: {txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
