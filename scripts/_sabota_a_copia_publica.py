# -*- coding: utf-8 -*-
"""開 A SABOTAGEM DA CÓPIA PÚBLICA — prova que as guardas da edição MORDEM.

Porque existe
-------------
Uma guarda que nunca foi vista vermelha não guarda nada: a 09/09, três de nove
guardas do jogo estavam verdes sobre o conjunto vazio. Esta bateria estraga, de
propósito e uma de cada vez, cada coisa que as guardas da edição prometem
apanhar — e exige o vermelho CERTO (a verificação que nomeia o defeito, não um
vermelho qualquer). Depois devolve cada ficheiro byte a byte e confirma-o pelo
hash.

  • `scripts/_verifica_copia_publica.py` — segredos, jogadores, IPs, ficheiros,
    licenças e (com a lista privada) o lore reservado;
  • `scripts/_test_edicao_comunitaria.py` — as promessas da edição, a CI e os
    modelos de issue e de PR (F2);
  • `scripts/_verifica_documentacao.py` — a documentação diz a verdade: números
    medidos, ligações, caminhos, funções no ficheiro certo, rotas, comandos,
    colunas, e uma página para cada motor e cada flag (F2);
  • `scripts/_verifica_dco.py` — cada commit assinado, em repositórios git
    temporários feitos aqui (F2).

⚠️ Os "segredos" de mentira são montados a partir de pedaços: escritos inteiros
neste ficheiro, a própria guarda apanhá-lo-ia (e com razão).

⚠️ Num repositório git a guarda mede o que o git PUBLICARIA, e o `.gitignore`
esconde qualquer `.env.*` — o risco real aí é alguém forçar um `.env` para o
índice (`git add -f`). A sabotagem do `.env` faz exactamente isso quando há
`.git`, e tira-o do índice no fim. A árvore solta (a pasta antes do `git init`)
continua a ser medida ficheiro a ficheiro, como na F1.

Uso:  python -X utf8 scripts/_sabota_a_copia_publica.py
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARDA = os.path.join(ROOT, "scripts", "_verifica_copia_publica.py")
SUITE = os.path.join(ROOT, "scripts", "_test_edicao_comunitaria.py")
DOCS = os.path.join(ROOT, "scripts", "_verifica_documentacao.py")
DCO = os.path.join(ROOT, "scripts", "_verifica_dco.py")
NOVO = os.path.join(ROOT, "community", "__sabotagem__.py")
GIT = os.path.isdir(os.path.join(ROOT, ".git"))

# os pedaços (ver o ⚠️ acima)
_TOKEN = "123456" + "789:" + "AA" + "x" * 33
_URL = "postgres" + "ql://admin:" + "s3cr3t" + "@" + "db.exemplo" + ".invalid/jogo"
_ID = "56382" + "92910"
_MAIL = "alguem.real" + "@" + "gmail" + ".com"
_PASTA = "C:" + "\\" + "Users" + "\\" + "dono-da-maquina" + "\\" + "Desktop"
_IP = "9.9" + "." + "9.9"
_REVERSE = "Reverse_" + "Immortal" + "_Taoists"
_APELIDO = "Zhao" + "renwu"
_RUMO = "Segredo" + "DoFim"  # o lore reservado de mentira (a lista verdadeira é privada)
_SEGREDO_CI = "${{ " + "secrets" + ".X }}"


def sha(p: str) -> str | None:
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else None


def correr(alvo: str, *extra: str, cwd: str = ROOT) -> tuple[int, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-X", "utf8", alvo, *extra], cwd=cwd, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def trocar(rel: str, antigo: str, novo: str, todas: bool = False):
    def _f():
        p = os.path.join(ROOT, *rel.split("/"))
        s = open(p, encoding="utf-8", newline="").read()
        assert s.count(antigo) >= 1, f"âncora da sabotagem não está em {rel}: {antigo[:60]!r}"
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write(s.replace(antigo, novo) if todas else s.replace(antigo, novo, 1))
    return _f


def criar(rel: str, conteudo, binario: bool = False):
    def _f():
        p = os.path.join(ROOT, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if binario:
            with open(p, "wb") as fh:
                fh.write(conteudo)
        else:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(conteudo)
    return _f


def criar_e_forcar(rel: str, conteudo: str):
    """Cria o ficheiro e, num repositório git, força-o para o índice (`git add -f`)
    — devolve o que o tira de lá, para o `finally` da bateria."""
    def _f():
        criar(rel, conteudo)()
        if not GIT:
            return None
        subprocess.run(["git", "-C", ROOT, "add", "-f", "--", rel], check=True, capture_output=True)
        return lambda: subprocess.run(["git", "-C", ROOT, "rm", "--cached", "-q", "--ignore-unmatch", "--", rel],
                                      capture_output=True)
    return _f


# (nome, quem deve ficar vermelho, o que o vermelho tem de dizer, ficheiros tocados, acção, args extra)
GUARDA_SABOTAGENS = [
    ("um token do Telegram num ficheiro", GUARDA, "token do Telegram",
     ["community/__sabotagem__.py"], criar("community/__sabotagem__.py", f'T = "{_TOKEN}"\n'), ()),
    ("uma URL de base com senha", GUARDA, "URL de base com senha",
     ["community/__sabotagem__.py"], criar("community/__sabotagem__.py", f'U = "{_URL}"\n'), ()),
    ("um ficheiro .env de verdade" + (" (forçado para o índice do git)" if GIT else ""), GUARDA, "ficheiro .env",
     [".env.sabotagem"], criar_e_forcar(".env.sabotagem", "BOT_TOKEN=x\n"), ()),
    ("o id do Telegram de alguém", GUARDA, "ID numérico em contexto de identidade",
     ["community/__sabotagem__.py"], criar("community/__sabotagem__.py", f"ADMIN_USERS = [{_ID}]\n"), ()),
    ("um e-mail real", GUARDA, "e-mail",
     ["community/__sabotagem__.py"], criar("community/__sabotagem__.py", f'# contacto: {_MAIL}\n'), ()),
    ("o caminho da máquina de quem exportou", GUARDA, "caminho de utilizador",
     ["community/__sabotagem__.py"], criar("community/__sabotagem__.py", f'# {_PASTA}\n'), ()),
    ("o apelido de um jogador (com a lista privada)", GUARDA, "apelido da lista privada",
     ["community/__sabotagem__.py"], criar("community/__sabotagem__.py", f"# report do {_APELIDO}\n"),
     ("--lista-privada", "__LISTA__")),
    # F5 (24/10): o owner guardou o fim do jogo — a guarda recebe-o numa lista privada
    ("o rumo guardado do jogo (com a lista privada do lore)", GUARDA, "lore reservado da lista privada",
     ["community/__sabotagem__.py"], criar("community/__sabotagem__.py", f"# o fim: {_RUMO}\n"),
     ("--lore-privado", "__LORE__")),
    ("um IPv4 público", GUARDA, "endereço IPv4",
     ["community/__sabotagem__.py"], criar("community/__sabotagem__.py", f'HOST = "{_IP}"\n'), ()),
    ("uma pasta interna (o Cérebro)", GUARDA, "pasta interna",
     ["Cerebro/x.md"], criar("Cerebro/x.md", "nota\n"), ()),
    ("material de engenharia reversa", GUARDA, "engenharia reversa",
     ["Reverse_Teste/x.txt"], criar("Reverse_Teste/x.txt", "x\n"), ()),
    ("a referência a esse material, por escrito", GUARDA, "referência a material privado",
     ["community/__sabotagem__.py"], criar("community/__sabotagem__.py", f"# ver {_REVERSE}\n"), ()),
    ("um documento .docx", GUARDA, "tipo proibido",
     ["community/notas.docx"], criar("community/notas.docx", b"PK\x03\x04", binario=True), ()),
    ("um ficheiro acima de 50 MB", GUARDA, "maior que 50 MB",
     ["community/grande.png"], criar("community/grande.png", b"\0" * (51 * 1024 * 1024), binario=True), ()),
    ("o texto da AGPL alterado num byte", GUARDA, "não é o texto canónico",
     ["LICENSE"], trocar("LICENSE", "Version 3, 19 November 2007", "Version 3, 19 November 2008"), ()),
    # F4b (23/10): a cópia guardada dentro de outro projecto arrancava com o `.env` DELE
    ("o config.py volta a ir buscar o .env às pastas-pai", GUARDA, "`load_dotenv()` sem caminho",
     ["config.py"], trocar("config.py", 'load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))',
                           "load_dotenv()"), ()),
    ("um find_dotenv com outro nome (`as`)", GUARDA, "`find_dotenv()` sem caminho",
     ["community/__sabotagem__.py"],
     criar("community/__sabotagem__.py", "from dotenv import find_dotenv as achar\nachar()\n"), ()),
]

_CI = ".github/workflows/ci.yml"
SUITE_SABOTAGENS = [
    ("a flag nasce LIGADA", SUITE, "sem nada no ambiente, a flag está DESLIGADA",
     ["config.py"], trocar("config.py", 'in ("1", "true", "yes")\n', 'not in ("0", "false", "no")\n'), ()),
    ("o dono volta a responder `True` fixo para o `main` (o defeito de 21/10)", SUITE,
     "o DONO da pergunta diz que o `main` não cobra",
     ["database/db.py"], trocar("database/db.py", "    if key == MAIN_WORLD_KEY:\n        return MONETIZATION_ENABLED\n",
                                "    if key == MAIN_WORLD_KEY:\n        return True\n"), ()),
    ("o pre-checkout do chat deixa de perguntar ao dono", SUITE,
     "chat: o pagamento por Stars é recusado ANTES da cobrança",
     ["handlers/shop.py"], trocar("handlers/shop.py", "            if not monetization_enabled_for(_w):\n",
                                  "            if False:\n"), ()),
    ("o gacha perde o portão no dono", SUITE, "a tiragem recusa NO DONO",
     ["core/monetization.py"], trocar("core/monetization.py", "    if not gacha_enabled():\n        return {",
                                      "    if False:\n        return {"), ()),
    ("a frase do gacha some numa língua", SUITE, "a frase do gacha fechado existe nas 3 línguas",
     ["miniapp/i18n/es.json"], trocar("miniapp/i18n/es.json",
                                      '"err_gacha_official_only": "El gacha', '"err_gacha_official_onlyX": "El gacha'), ()),
    ("o projecto Firebase oficial volta assado", SUITE, "o Firebase do cliente vem VAZIO",
     ["core/webserver.py"], trocar("core/webserver.py",
                                   '    pid = (os.getenv("FIREBASE_PROJECT_ID") or "").strip()\n',
                                   '    pid = (os.getenv("FIREBASE_PROJECT_ID") or "").strip() or "nivrael-f558f"\n'), ()),
    ("a porta local esquece a recusa em produção", SUITE, "RECUSA abrir com WEBHOOK_URL",
     ["community/dev_login.py"], trocar("community/dev_login.py", '    if (os.getenv("WEBHOOK_URL") or "").strip():\n',
                                        '    if False:\n'), ()),
    ("a porta local aceita qualquer par", SUITE, "só aceita a própria máquina e a rede local",
     ["community/dev_login.py"], trocar("community/dev_login.py", "    return ip.is_loopback or ip.is_private\n",
                                        "    return True\n"), ()),
    ("o mundo local esquece UMA flag", SUITE, "o mundo local liga TODAS as flags",
     ["community/local_world.py"], trocar("community/local_world.py",
                                          "return {k: True for k in DEFAULT_WORLD_FEATURES}",
                                          'return {k: (k != "a_obra") for k in DEFAULT_WORLD_FEATURES}'), ()),
    ("uma variável do código some do .env.example", SUITE, "estão TODAS no .env.example",
     [".env.example"], trocar(".env.example", "# BOUNTY_TTL_HOURS=", "# BOUNTY_TTL_HORAS="), ()),
    ("o .gitignore deixa de esconder o .env", SUITE, "o .gitignore nunca deixa sair o .env",
     [".gitignore"], trocar(".gitignore", "\n.env\n", "\n"), ()),
    ("o README esquece o nome reservado", SUITE, "o README diz as licenças",
     ["README.md"], trocar("README.md", "TRADEMARKS.md", "MARCAS.md", todas=True), ()),
    # ── F5 (24/10): as decisões 6, 8 e 12 do owner ──────────────────────────
    ("o estado do projecto perde a promessa numa língua", SUITE, "o README diz o estado do projecto",
     ["README.md"], trocar("README.md", "**30 días** de antelación", "algunos días de antelación"), ()),
    ("o MAINTAINERS deixa um mantenedor tocar nos dados", SUITE, "nenhum mantenedor toca no servidor",
     ["MAINTAINERS.md"], trocar("MAINTAINERS.md", "receives access to the official",
                                "may ask for access to the official"), ()),
    ("o CODEOWNERS nomeia quem não é mantenedor", SUITE, "o CODEOWNERS pede a revisão",
     [".github/CODEOWNERS"], trocar(".github/CODEOWNERS", "*   @christian-cangussu", "*   @alguem-de-fora"), ()),
    ("volta um FUNDING.yml só com comentários", SUITE, "sem canal de apoio por escolher",
     [".github/FUNDING.yml"], criar(".github/FUNDING.yml", "# github: [o-teu-utilizador]\n"), ()),
    # 25/10: o compose emulado apanhou-o — o 1.º run da CI teria ficado vermelho
    ("o fumo volta a contentar-se com o 200 do /healthz", SUITE, "o fumo espera o `ready: true`",
     ["scripts/_fumo_da_edicao.py"], trocar("scripts/_fumo_da_edicao.py",
                                            "if status == 200 and pronto(corpo):", "if status == 200:"), ()),
    # ── F2 ───────────────────────────────────────────────────────────────────
    ("um botão lido por um AJUDANTE some do .env.example (o buraco da F1)", SUITE,
     "estão TODAS no .env.example",
     [".env.example"], trocar(".env.example", "# SCR_DROP_MULT=", "# SCR_DROP_MULTX="), ()),
    ("a CI deixa de correr nos pull requests", SUITE, "corre em cada pull request",
     [_CI], trocar(_CI, "on:\n  pull_request:\n", "on:\n  issues:\n"), ()),
    ("a CI passa a correr com `pull_request_target`", SUITE, "nunca com `pull_request_target`",
     [_CI], trocar(_CI, "on:\n  pull_request:\n", "on:\n  pull_request_target:\n"), ()),
    ("os testes passam a correr noutro Python", SUITE, "os testes correm no Python do contentor",
     [_CI], trocar(_CI, 'python-version: "3.11"', 'python-version: "3.12"'), ()),
    ("a CI corre só uma parte dos testes", SUITE, "correm o comando do CONTRIBUTING, inteiro",
     [_CI], trocar(_CI, "run: python scripts/run_tests.py\n", "run: python scripts/run_tests.py mv9\n"), ()),
    ("uma action deixa de estar presa a um commit", SUITE, "estão presas a um commit",
     [_CI], trocar(_CI, "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/checkout@v7"), ()),
    ("um job passa a ler um segredo", SUITE, "nenhum job lê um segredo",
     [_CI], trocar(_CI, "        run: pip install -r requirements.txt\n",
                   "        run: pip install -r requirements.txt\n        env:\n          X: " + _SEGREDO_CI + "\n"), ()),
    ("a bateria de sabotagem sai da CI", SUITE, "as guardas são provadas a morder",
     [_CI], trocar(_CI, "python scripts/_sabota_a_copia_publica.py", "python scripts/_sabota_o_mapa.py"), ()),
    ("a checklist do PR afasta-se da do CONTRIBUTING", SUITE, "o modelo de PR traz a checklist",
     [".github/pull_request_template.md"], trocar(".github/pull_request_template.md",
                                                  "- [ ] pt / en / es in parity\n", ""), ()),
    ("o bug deixa de exigir os passos para o reproduzir", SUITE, "o bug pede o que aconteceu e os passos",
     [".github/ISSUE_TEMPLATE/bug.yml"], trocar(".github/ISSUE_TEMPLATE/bug.yml",
                                                "        3. …\n    validations:\n      required: true\n",
                                                "        3. …\n"), ()),
    # ── F4b ──────────────────────────────────────────────────────────────────
    ("o config.py sobe às pastas-pai à procura do .env (a CHAMADA, com o dotenv verdadeiro)", SUITE,
     "o config.py NÃO lê o .env da pasta-pai",
     ["config.py"], trocar("config.py", 'load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))',
                           "load_dotenv()"), ()),
    ("o arranque local sobe às pastas-pai à procura do .env", SUITE, "o arranque local (`community/local.py`) também não",
     ["community/local.py"], trocar("community/local.py",
                                    'load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))',
                                    "load_dotenv()"), ()),
    ("o .env da própria pasta deixa de ser lido (a prova não pode ser verde sobre o vazio)", SUITE,
     "o .env DESTA pasta continua a ser lido",
     ["config.py"], trocar("config.py", 'load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))',
                           'load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.nenhum"))'), ()),
]

DOCS_SABOTAGENS = [
    ("um número medido fica velho (a página diz 41 flags)", DOCS, "says 41 for `#flags`",
     ["docs/architecture.md"], trocar("docs/architecture.md", "40<!--#flags--> today", "41<!--#flags--> today"), ()),
    ("o CÓDIGO muda debaixo da página (9 → 10 subcamadas)", DOCS, "says 9 for `#sub_layers`",
     ["config.py"], trocar("config.py", 'os.getenv("SUB_LAYERS_PER_REALM", "9")',
                           'os.getenv("SUB_LAYERS_PER_REALM", "10")'), ()),
    ("um número sem medida entra numa página", DOCS, "`12` is not measured",
     ["docs/systems/combat.md"], trocar("docs/systems/combat.md", "## The arena\n",
                                        "## The arena\n\nThe arena has 12 tiers.\n"), ()),
    ("uma ligação morre", DOCS, "`instalacao.md` does not exist",
     ["docs/README.md"], trocar("docs/README.md", "(installation.md)", "(instalacao.md)"), ()),
    ("um caminho que não existe", DOCS, "`core/horta_engine.py` does not exist",
     ["docs/systems/body.md"], trocar("docs/systems/body.md", "`core/garden_engine.py`", "`core/horta_engine.py`"), ()),
    ("uma função que não existe", DOCS, "`settle_pvp_duelo()` is not defined anywhere",
     ["docs/systems/combat.md"], trocar("docs/systems/combat.md", "`settle_pvp_duel()`", "`settle_pvp_duelo()`"), ()),
    ("uma função dita no ficheiro errado", DOCS, "`grant_jade()` is not defined in core/economy.py",
     ["docs/architecture.md"], trocar("docs/architecture.md", "`grant_jade()` in `core/monetization.py`",
                                      "`grant_jade()` in `core/economy.py`"), ()),
    ("uma rota que não existe", DOCS, "`/api/miniapp/shop_catalogue` is not a route",
     ["docs/systems/economy.md"], trocar("docs/systems/economy.md", "`/api/miniapp/shop_catalog`",
                                         "`/api/miniapp/shop_catalogue`"), ()),
    ("um comando de chat que não existe", DOCS, "`/daos` is neither a route of the application nor a chat command",
     ["docs/systems/dao.md"], trocar("docs/systems/dao.md", "| chat | `/dao` |", "| chat | `/daos` |"), ()),
    ("a coluna de um modelo que não existe", DOCS, "Player has no column `spirit_jades`",
     ["docs/systems/economy.md"], trocar("docs/systems/economy.md", "`Player.spirit_jade`", "`Player.spirit_jades`"), ()),
    ("um motor novo sem página", DOCS, "no page in docs/ names this module",
     ["core/sabotagem_engine.py"], criar("core/sabotagem_engine.py", "X = 1\n"), ()),
    ("uma flag nova sem documentação", DOCS, "the feature flag `flag_da_sabotagem` is not documented",
     ["database/db.py"], trocar("database/db.py", '    "a_obra":              False,',
                                '    "a_obra":              False,\n    "flag_da_sabotagem":   False,'), ()),
]


def _git(cwd: str, *args: str, env: dict | None = None) -> str:
    r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, encoding="utf-8",
                       env=env, check=True)
    return r.stdout.strip()


def sabotagens_dco() -> tuple[int, list[str]]:
    """O DCO em repositórios git feitos aqui, numa pasta temporária."""
    ok, falhas = 0, []
    autor = dict(os.environ, GIT_AUTHOR_NAME="Ana", GIT_AUTHOR_EMAIL="ana@example.org",
                 GIT_COMMITTER_NAME="Ana", GIT_COMMITTER_EMAIL="ana@example.org")
    bot = dict(autor, GIT_AUTHOR_NAME="dependabot[bot]",
               GIT_AUTHOR_EMAIL="49699333+dependabot[bot]@users.noreply.github.com")

    def caso(nome, commits, espera_codigo, espera_texto):
        nonlocal ok
        tmp = tempfile.mkdtemp(prefix="sabota_dco_")
        try:
            _git(tmp, "init", "-q")
            _git(tmp, "commit", "-q", "--allow-empty", "-m", "base\n\nSigned-off-by: Ana <ana@example.org>", env=autor)
            base = _git(tmp, "rev-parse", "HEAD")
            for msg, env in commits:
                _git(tmp, "commit", "-q", "--allow-empty", "-m", msg, env=env)
            codigo, saida = correr(DCO, base, "HEAD", cwd=tmp)
            mordeu = codigo == espera_codigo and espera_texto in saida
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if mordeu:
            ok += 1
            print(f"  ✅ {'morde' if espera_codigo else 'passa'}  [_verifica_dco.py] {nome}")
        else:
            falhas.append(nome)
            print(f"  ❌ NÃO {'MORDEU' if espera_codigo else 'PASSOU'}  [_verifica_dco.py] {nome}\n{saida[-400:]}")

    caso("um commit sem Signed-off-by", [("feat: x", autor)], 1, "no Signed-off-by line")
    caso("um Signed-off-by de outra pessoa", [("feat: x\n\nSigned-off-by: Rui <rui@example.org>", autor)],
         1, "signed off as")
    caso("ANTI-GUARDA: todos assinados passam", [("feat: x\n\nSigned-off-by: Ana <ana@example.org>", autor)],
         0, "every commit is signed off")
    caso("ANTI-GUARDA: o Dependabot não assina e passa", [("ci: bump", bot)], 0, "every commit is signed off")

    # F4b (23/10): uma cópia SEM `.git` próprio dentro de OUTRO repositório — o git sobe
    # e responde pelo de fora; o DCO tem de recusar em vez de culpar os commits dele.
    tmp = tempfile.mkdtemp(prefix="sabota_dco_")
    try:
        _git(tmp, "init", "-q")
        _git(tmp, "commit", "-q", "--allow-empty", "-m", "de fora, sem assinatura", env=autor)
        _git(tmp, "commit", "-q", "--allow-empty", "-m", "de fora, outra vez", env=autor)
        copia = os.path.join(tmp, "copia-sem-git", "scripts")
        os.makedirs(copia)
        shutil.copyfile(DCO, os.path.join(copia, "_verifica_dco.py"))
        codigo, saida = correr(os.path.join(copia, "_verifica_dco.py"), "HEAD~1", "HEAD",
                               cwd=os.path.dirname(copia))
        mordeu = codigo == 2 and "has no git repository of its own" in saida
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    nome = "uma cópia sem .git dentro de OUTRO repositório recusa (não culpa os commits dele)"
    if mordeu:
        ok += 1
        print(f"  ✅ morde  [_verifica_dco.py] {nome}")
    else:
        falhas.append(nome)
        print(f"  ❌ NÃO MORDEU  [_verifica_dco.py] {nome}\n{saida[-400:]}")
    return ok, falhas


def main() -> int:
    for p in (NOVO, os.path.join(ROOT, "core", "sabotagem_engine.py")):
        if os.path.exists(p):
            print(f"❌ {p} já existe — esta bateria não escreve por cima de nada")
            return 2
    ok = 0
    falhas = []
    tmp = tempfile.mkdtemp(prefix="sabota_")
    lista = os.path.join(tmp, "apelidos.txt")
    with open(lista, "w", encoding="utf-8") as fh:
        fh.write(_APELIDO + "\n")
    lore = os.path.join(tmp, "lore.txt")
    with open(lore, "w", encoding="utf-8") as fh:
        fh.write(_RUMO + "\n")
    privadas = {"__LISTA__": lista, "__LORE__": lore}
    todas = GUARDA_SABOTAGENS + SUITE_SABOTAGENS + DOCS_SABOTAGENS
    try:
        for nome, alvo, espera, tocados, accao, extra in todas:
            caminhos = [os.path.join(ROOT, *t.split("/")) for t in tocados]
            antes = {p: sha(p) for p in caminhos}
            existiam = {p: os.path.isfile(p) for p in caminhos}
            copias = {}
            for p in caminhos:
                if existiam[p]:
                    copias[p] = os.path.join(tmp, hashlib.sha1(p.encode()).hexdigest())
                    shutil.copyfile(p, copias[p])
            criadas = [os.path.dirname(p) for p in caminhos if not os.path.isdir(os.path.dirname(p))]
            desfazer = None
            mordeu = False
            saida = ""
            try:
                desfazer = accao()
                args = tuple(privadas.get(a, a) for a in extra)
                code, saida = correr(alvo, *args)
                # o vermelho CERTO: a linha da verificação que FALHOU nomeia o
                # defeito ("ok …" com o mesmo nome não conta)
                mordeu = code != 0 and any(
                    l.lstrip().startswith(("XX", "❌")) and espera in l for l in saida.splitlines())
            finally:
                if callable(desfazer):
                    desfazer()
                for p in caminhos:
                    if existiam[p]:
                        shutil.copyfile(copias[p], p)
                    elif os.path.exists(p):
                        os.remove(p)
                for d in sorted(set(criadas), key=len, reverse=True):
                    if os.path.isdir(d) and not os.listdir(d):
                        os.rmdir(d)
            voltou = all(sha(p) == antes[p] for p in caminhos)
            quem = os.path.basename(alvo)
            if mordeu and voltou:
                ok += 1
                print(f"  ✅ morde  [{quem}] {nome}")
            else:
                falhas.append(nome)
                motivo = "NÃO MORDEU" if not mordeu else "o ficheiro NÃO voltou byte a byte"
                print(f"  ❌ {motivo}  [{quem}] {nome}")
                if not mordeu:
                    print("     " + "\n     ".join(saida.strip().splitlines()[-6:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    dco_ok, dco_falhas = sabotagens_dco()
    ok += dco_ok
    falhas += dco_falhas

    # o estado de chegada: tudo verde outra vez
    g, _ = correr(GUARDA)
    s, _ = correr(SUITE)
    d, _ = correr(DOCS)
    total = len(todas) + dco_ok + len(dco_falhas)
    print(f"\n{ok}/{total} mordem (ou passam, nos ANTI-GUARDA) · os ficheiros voltaram byte a byte · "
          f"no fim: guarda {'verde' if g == 0 else 'VERMELHA'}, suite {'verde' if s == 0 else 'VERMELHA'}, "
          f"documentação {'verde' if d == 0 else 'VERMELHA'}")
    return 0 if (ok == total and g == 0 and s == 0 and d == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
