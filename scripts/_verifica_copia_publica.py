# -*- coding: utf-8 -*-
"""開 A GUARDA DA CÓPIA PÚBLICA — o que NUNCA pode chegar a um repositório público.

Porque existe (Open Source F1, 2026-10-21)
------------------------------------------
Este repositório nasceu como cópia LIMPA do jogo oficial: sem histórico, sem a
documentação interna, sem dados de jogadores, sem material de terceiros. "Limpa"
só é verdade enquanto alguém a medir — um PR, uma exportação nova ou um ficheiro
esquecido no disco bastam para a sujar. Esta guarda é essa medição, e corre antes
de cada push (e, na F3, em cada PR).

O que mede — cada achado é um motivo para NÃO publicar
------------------------------------------------------
  1. SEGREDOS     tokens do Telegram, URLs de base com senha, chaves privadas,
                  contas de serviço, chaves AWS/GitHub/OpenAI/Anthropic/Google/
                  Slack/Stripe, JWT, ficheiros `.env` (só o `.env.example` passa);
                  e código que vai buscar um `.env` FORA desta pasta
                  (`load_dotenv()`/`dotenv_values()` sem caminho, `find_dotenv()`).
  2. JOGADORES    IDs numéricos em contexto de identidade, e-mails reais,
                  caminhos de utilizador da máquina de quem exportou; e, com
                  `--lista-privada`, os apelidos dos relatos (a lista vive no
                  repositório privado e NUNCA aqui).
  3. IPs          nenhum IPv4 fora de loopback e dos blocos de documentação
                  (RFC 5737); privados (RFC 1918) só dentro dos testes.
  4. FICHEIROS    nada de `Reverse_*`, das pastas internas (Cérebro, prompts,
                  tmp, roblox…), de documentos .docx, de lugares do Roblox, de
                  chaves e bases; nada acima de 50 MB.
  5. LICENÇAS     `LICENSE` (AGPL-3.0) e `LICENSE-ASSETS` (CC BY-NC-SA 4.0) são
                  os textos canónicos, byte a byte.
  6. LORE         com `--lore-privado`, o rumo do jogo que o jogo oficial ainda
                  guarda (decisão do owner, 24/10: o que o jogo já mostra é
                  público; o fim não). A lista vive no repositório privado — aqui
                  ela diria o segredo que guarda.

Num repositório git mede o que o git publicaria (`ls-files` com os não-ignorados);
fora dele, a árvore inteira menos os artefactos de build.

Uso:  python scripts/_verifica_copia_publica.py
      python scripts/_verifica_copia_publica.py --lista-privada <ficheiro> --lore-privado <ficheiro>
      python scripts/_verifica_copia_publica.py --json
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
import warnings

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Fora da árvore pública por construção: artefactos de build e estado local.
# (Num repositório git, o `.gitignore` decide; esta lista é a da árvore solta.)
NUNCA_LIDO = {".git", "node_modules", "dist", "__pycache__", ".venv", "venv", ".pytest_cache"}

TEXTO = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".json", ".md", ".html", ".css",
    ".sql", ".txt", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".svg", ".xml", ".sh",
    ".conf", ".csv", ".env", ".example", ".webmanifest", ".cmd", ".ps1", ".bat",
}
TEXTO_NOMES = {"Dockerfile", ".dockerignore", ".gitattributes", ".gitignore", "LICENSE",
               "LICENSE-ASSETS", ".env.example", "Makefile"}

# ── 1. SEGREDOS ──────────────────────────────────────────────────────────────
SEGREDOS = (
    ("token do Telegram", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}\b")),
    ("URL de base com senha", re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)(?:\+\w+)?://([^:@\s/'\"]+):([^@\s'\"]+)@")),
    ("chave privada", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY")),
    ("conta de serviço", re.compile(r"\"type\"\s*:\s*\"service_account\"")),
    ("chave AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("token GitHub", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})")),
    ("chave OpenAI/Anthropic", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{24,}")),
    ("chave Google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("token Slack", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("chave Stripe", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{16,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
)
# Ir buscar o `.env` às pastas-PAI: sem caminho, `load_dotenv()` e `dotenv_values()`
# sobem pela árvore até achar um, e `find_dotenv()` existe para isso. Medido a 23/10:
# uma cópia desta árvore guardada dentro de outro projecto com `.env` arrancava com
# o `.env` DELE — outra base, outro token. Lido pela AST (a chamada, não o texto).
DOTENV_QUE_SOBE = ("load_dotenv", "dotenv_values", "find_dotenv")
# Credenciais de BRINQUEDO que os exemplos usam de propósito (compose, README).
CREDENCIAIS_DE_EXEMPLO = {("nivrael", "nivrael"), ("postgres", "postgres"), ("user", "password"),
                          ("usuario", "senha"), ("user", "pass"), ("u", "p")}

# ── 2. JOGADORES ─────────────────────────────────────────────────────────────
# O número tem de ser o VALOR da chave de identidade (`tid=…`, `"telegram_id": …`,
# `user_id == …`, `ADMIN_USERS=[…`, "tid 5638…") — um número qualquer mais à frente
# na mesma linha é dado do jogo, não de alguém.
ID_CONTEXTO = re.compile(
    r"(?i)\b(?:telegram_id|tg_id|tid|user_id|player_id|chat_id|owner_id|admin_users|admins?|uid)\b"
    r"[\"']?(?:\s*(?:==|=|:|\(|,|\[)\s*|\s+)\[?\s*[\"']?(-?\d{7,13})(?![\w.])")
# Números de FIXTURE e constantes que o contexto apanha e não são de ninguém.
IDS_PERMITIDOS = {
    "123456789", "1234567890", "987654321", "111111111", "999999999",
    "2654435761",  # constante multiplicativa de Knuth (hash por jogador)
}
SINTETICO = re.compile(r"^-10000000\d\d$")  # ids sintéticos de teste (contas web)

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
EMAIL_DOMINIOS_OK = ("example.com", "example.org", "example.net", "exemplo.com", "example",
                     "invalid", "gserviceaccount.com", "nivrael.com", "users.noreply.github.com",
                     "contributor-covenant.org")
EMAIL_LOCAIS_OK = {"fulano", "ninguem", "nobody", "exemplo", "example", "user", "voce", "you"}
CAMINHO_PESSOAL = re.compile(r"(?i)(?:[A-Z]:[\\/]+Users[\\/]+|/Users/|/home/)([A-Za-z0-9._-]+)")
CAMINHO_GENERICO = {"user", "users", "you", "voce", "runner", "<user>", "nome", "name", "username",
                    "default", "public", "shared", "app", "node"}

# ── 3. IPs ───────────────────────────────────────────────────────────────────
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
# Blocos que nunca são o endereço de um servidor: documentação (RFC 5737) e o
# espaço partilhado dos operadores (RFC 6598, 100.64/10 — não roteável na internet).
DOCUMENTACAO = [ipaddress.ip_network(n) for n in
                ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "100.64.0.0/10")]

# ── 4. FICHEIROS ─────────────────────────────────────────────────────────────
PASTAS_PROIBIDAS = ("Cerebro", "Prompts", "Publicacao", "tmp", "scratch", ".tmp_map", "plans",
                    "motor_mestres", ".agents", ".claude", "roblox", "tools/_db_audit", ".nivrael")
EXTENSOES_PROIBIDAS = (".docx", ".doc", ".rbxl", ".rbxlx", ".rbxm", ".rbxmx", ".apk", ".xapk",
                       ".ipa", ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".sqlite",
                       ".sqlite3", ".db", ".dump", ".bak")
LIMITE_BYTES = 50 * 1024 * 1024
MENCOES_PROIBIDAS = re.compile(r"Reverse_(?:Immortal|Shattered)\w*")

# ── 5. LICENÇAS (sha256 dos textos canónicos) ────────────────────────────────
LICENCAS = {
    "LICENSE": ("GNU AGPL-3.0", "8486a10c4393cee1c25392769ddd3b2d6c242d6ec7928e1414efff7dfb2f07ef"),
    "LICENSE-ASSETS": ("CC BY-NC-SA 4.0", "e66c269d4819aaab34b49ef5220c4ddab6756f21bb5180761a4eb8561f2b7bbd"),
}


def _e_texto(rel: str) -> bool:
    nome = os.path.basename(rel)
    return nome in TEXTO_NOMES or nome.startswith(".env") or os.path.splitext(rel)[1].lower() in TEXTO


def ficheiros(root: str) -> list[str]:
    """O que seria publicado. Num git: rastreados + não-ignorados."""
    if os.path.isdir(os.path.join(root, ".git")):
        r = subprocess.run(["git", "-C", root, "ls-files", "-co", "--exclude-standard", "-z"],
                           capture_output=True, check=True)
        return sorted(p for p in r.stdout.decode("utf-8").split("\0") if p)
    out = []
    for d, subs, nomes in os.walk(root):
        subs[:] = [s for s in subs if s not in NUNCA_LIDO]
        for n in nomes:
            out.append(os.path.relpath(os.path.join(d, n), root).replace(os.sep, "/"))
    return sorted(out)


def dotenv_que_sobe(txt: str) -> list[tuple[int, str]]:
    """(linha, função) de cada chamada que lê um `.env` fora da pasta do projecto."""
    try:
        with warnings.catch_warnings():  # um `\{` numa docstring alheia não é assunto desta guarda
            warnings.simplefilter("ignore")
            arvore = ast.parse(txt)
    except SyntaxError:
        return []
    nomes = {}  # `from dotenv import load_dotenv as ld` → ld() é load_dotenv()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and (no.module or "").split(".")[0] == "dotenv":
            for a in no.names:
                nomes[a.asname or a.name] = a.name
    out = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        f = no.func
        if isinstance(f, ast.Attribute):
            nome = f.attr
        elif isinstance(f, ast.Name):
            nome = nomes.get(f.id, "")
        else:
            continue
        if nome not in DOTENV_QUE_SOBE:
            continue
        caminho = no.args[0] if no.args else next(
            (k.value for k in no.keywords if k.arg in ("dotenv_path", "stream")), None)
        if nome == "find_dotenv" or caminho is None or (
                isinstance(caminho, ast.Constant) and caminho.value is None):
            out.append((no.lineno, nome))
    return out


def ler_lista_privada(caminho: str) -> tuple[list, list]:
    padroes, permitidos = [], []
    for linha in open(caminho, encoding="utf-8"):
        linha = linha.rstrip("\n")
        if not linha or linha.startswith("#"):
            continue
        if linha.startswith("!"):
            f, _, trecho = linha[1:].partition("\t")
            permitidos.append((f, trecho))
        else:
            padroes.append(re.compile(linha))
    return padroes, permitidos


def verificar(root: str, lista_privada: str | None = None, lore_privado: str | None = None) -> dict:
    achados: list[dict] = []
    contagem = {"ficheiros": 0, "texto": 0}

    def achar(cat, rel, n, motivo, trecho=""):
        achados.append({"categoria": cat, "ficheiro": rel, "linha": n, "motivo": motivo,
                        "trecho": trecho[:160]})

    privados, permitidos = ler_lista_privada(lista_privada) if lista_privada else ([], [])
    rumo, rumo_permitido = ler_lista_privada(lore_privado) if lore_privado else ([], [])
    todos = ficheiros(root)
    contagem["ficheiros"] = len(todos)

    for rel in todos:
        p = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(p):
            continue
        partes = rel.split("/")
        # 4. o caminho e o tamanho
        if any(x.startswith("Reverse_") for x in partes):
            achar("ficheiros", rel, 0, "material de engenharia reversa de terceiros")
        for proibida in PASTAS_PROIBIDAS:
            if rel == proibida or rel.startswith(proibida + "/"):
                achar("ficheiros", rel, 0, f"pasta interna `{proibida}/`")
        nome = partes[-1]
        if nome == ".env" or (nome.startswith(".env.") and nome != ".env.example"):
            achar("segredos", rel, 0, "ficheiro .env (só o .env.example é público)")
        if nome.lower().endswith(EXTENSOES_PROIBIDAS):
            achar("ficheiros", rel, 0, f"tipo proibido ({os.path.splitext(nome)[1]})")
        if os.path.getsize(p) > LIMITE_BYTES:
            achar("ficheiros", rel, 0, f"maior que 50 MB ({os.path.getsize(p) // (1024 * 1024)} MB)")
        if not _e_texto(rel):
            continue
        try:
            txt = open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        contagem["texto"] += 1
        e_teste = "/_test_" in f"/{rel}" or rel.startswith("scripts/_test_") or "/tests/" in f"/{rel}/"
        if rel.endswith(".py"):
            linhas = txt.splitlines()
            for n, func in dotenv_que_sobe(txt):
                achar("segredos", rel, n, f"`{func}()` sem caminho lê um .env FORA desta pasta "
                                          f"(sobe pelas pastas-pai)", linhas[n - 1].strip() if n <= len(linhas) else "")
        for n, linha in enumerate(txt.splitlines(), 1):
            # 1. segredos
            for motivo, rx in SEGREDOS:
                for m in rx.finditer(linha):
                    if motivo == "URL de base com senha" and (m.group(1), m.group(2)) in CREDENCIAIS_DE_EXEMPLO:
                        continue
                    achar("segredos", rel, n, motivo, linha.strip())
            # 2. jogadores
            for m in ID_CONTEXTO.finditer(linha):
                num = m.group(1)
                if num.lstrip("-") in IDS_PERMITIDOS or SINTETICO.match(num):
                    continue
                achar("jogadores", rel, n, f"ID numérico em contexto de identidade ({num})", linha.strip())
            for m in EMAIL.finditer(linha):
                if m.start() and linha[m.start() - 1] in "•*":
                    continue  # mascarado de propósito (`f•••o@…`): é o exemplo da máscara
                local, _, dom = m.group(0).partition("@")
                dom = dom.lower()
                if any(dom == d or dom.endswith("." + d) for d in EMAIL_DOMINIOS_OK):
                    continue
                if local.lower() in EMAIL_LOCAIS_OK:
                    continue
                achar("jogadores", rel, n, f"e-mail ({m.group(0)})", linha.strip())
            for m in CAMINHO_PESSOAL.finditer(linha):
                if m.group(1).lower() not in CAMINHO_GENERICO:
                    achar("jogadores", rel, n, f"caminho de utilizador ({m.group(0)})", linha.strip())
            for rx in privados:
                m = rx.search(linha)
                if m and not any(rel == f and trecho in linha for f, trecho in permitidos):
                    achar("jogadores", rel, n, f"apelido da lista privada ({m.group(0)!r})", linha.strip())
            # 6. o lore que o jogo oficial ainda guarda
            for rx in rumo:
                m = rx.search(linha)
                if m and not any(rel == f and trecho in linha for f, trecho in rumo_permitido):
                    achar("lore", rel, n, f"lore reservado da lista privada ({m.group(0)!r})", linha.strip())
            # 3. IPs
            for m in IPV4.finditer(linha):
                try:
                    ip = ipaddress.ip_address(m.group(0))
                except ValueError:
                    continue
                if ip.is_loopback or ip.is_unspecified or str(ip) == "255.255.255.255":
                    continue
                if any(ip in net for net in DOCUMENTACAO):
                    continue
                if (ip.is_private or ip.is_link_local) and e_teste:
                    continue
                achar("ips", rel, n, f"endereço IPv4 ({ip})", linha.strip())
            # 4. menções aos materiais privados
            for m in MENCOES_PROIBIDAS.finditer(linha):
                achar("ficheiros", rel, n, f"referência a material privado ({m.group(0)})", linha.strip())

    # 5. licenças
    for nome, (qual, sha) in LICENCAS.items():
        p = os.path.join(root, nome)
        if not os.path.isfile(p):
            achar("licencas", nome, 0, f"falta o {nome} ({qual})")
            continue
        got = hashlib.sha256(open(p, "rb").read()).hexdigest()
        if got != sha:
            achar("licencas", nome, 0, f"{nome} não é o texto canónico da {qual} (sha256 {got[:12]}…)")

    por_cat = {c: sum(1 for a in achados if a["categoria"] == c)
               for c in ("segredos", "jogadores", "ips", "ficheiros", "licencas", "lore")}
    return {"ok": not achados, "contagem": contagem, "por_categoria": por_cat,
            "lista_privada": bool(lista_privada), "lore_privado": bool(lore_privado), "achados": achados}


def main() -> int:
    ap = argparse.ArgumentParser(description="a guarda da cópia pública")
    ap.add_argument("--lista-privada", help="padrões privados (apelidos), um por linha")
    ap.add_argument("--lore-privado", help="padrões privados (o lore reservado), um por linha")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--raiz", default=ROOT)
    a = ap.parse_args()
    r = verificar(os.path.abspath(a.raiz), a.lista_privada, a.lore_privado)
    if a.json:
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 0 if r["ok"] else 1
    c = r["contagem"]
    print(f"開 a guarda da cópia pública — {c['ficheiros']} ficheiros, {c['texto']} de texto lidos")
    for cat, n in r["por_categoria"].items():
        print(f"  {'✅' if n == 0 else '❌'} {cat:<10} {n}")
    if not r["lista_privada"]:
        print("  ·  apelidos dos relatos: sem --lista-privada (a lista vive no repositório privado)")
    if not r["lore_privado"]:
        print("  ·  lore reservado: sem --lore-privado (a lista vive no repositório privado)")
    for x in r["achados"][:200]:
        onde = f"{x['ficheiro']}:{x['linha']}" if x["linha"] else x["ficheiro"]
        print(f"  ❌ [{x['categoria']}] {onde} — {x['motivo']}" + (f"\n       {x['trecho']}" if x["trecho"] else ""))
    if len(r["achados"]) > 200:
        print(f"  … e mais {len(r['achados']) - 200}")
    print("RESULTADO:", "LIMPA — pode publicar" if r["ok"] else f"{len(r['achados'])} achado(s) — NÃO publicar")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
