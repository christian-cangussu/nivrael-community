# -*- coding: utf-8 -*-
"""WEB-C 兩面 — duas superficies, um jogo.

O que esta suite existe para impedir:

 1. **O chat a servir o personagem errado.** Desde a WEB-B F2 o `telegram_id`
    deixou de ser o `player_id` por definicao. O mini-app ja resolvia; o chat
    nao. Aqui medem-se as tres respostas: sem vinculo -> o proprio id; com
    vinculo -> o id ligado; plano de controlo em baixo -> id cru (fail-safe).
 2. ⚠️ **O FIX PARCIAL.** Consertar so o `_ensure_player` deixava 101 chamadas
    diretas a `_get_player` e 25 `select(Player)` inline com o id CRU: o
    `/status` certo e o `/meditar` a falhar em silencio e PIOR que nao
    consertar. Ha um teste ESTRUTURAL que varre `handlers/` e falha se nascer
    um sitio novo com o id cru.
 3. **O ponto de corte das duas superficies a disparar dentro do Telegram** —
    onde e sempre telemovel, mesmo no Telegram Desktop.
 4. **O site a voltar a carregar o que foi morto** (LoadingScreen, CustomCursor,
    ScrollProgress, MagneticButton, Lenis).
 5. **`/privacy` e `/terms` a deixarem de responder** nas 3 linguas — o Google
    exige-as alcancaveis para o consentimento OAuth.

Corre sem Postgres e sem rede.
"""
import asyncio
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("BOT_TOKEN", "1:fake-for-tests")

_ok, _bad = 0, []


def chk(cond, msg):
    global _ok
    if cond:
        _ok += 1
        print("  ok  " + msg)
    else:
        _bad.append(msg)
        print("  XX  " + msg)


def rd(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 1. A divida da F2: o chat resolve a identidade ===")

import database.control_db as CDB
from core.utils import resolve_chat_player_id


class _Row:
    def __init__(self, t): self._t = t
    def first(self): return self._t


class _IdentitySession:
    """Falso ESTRITO: levanta perante SQL que nao reconheca.

    A licao do backfill de 26/08 — um falso gentil deu verde a um INSERT que a
    producao recusava (`text versus bigint`), e as 248 identidades nunca foram
    criadas. Um falso que so aceita o que sabe ler nao consegue mentir assim."""

    def __init__(self, store): self.store = store
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        p = params or {}
        if sql.startswith("SELECT player_id FROM auth_identities"):
            v = self.store.get((p["p"], p["u"]))
            return _Row((v,) if v is not None else None)
        raise AssertionError("SQL nao reconhecida pelo falso: " + sql[:120])


def _install(store):
    """Liga o falso e limpa a cache (60s de TTL mentiriam entre casos)."""
    CDB._identity_cache.clear()
    CDB._ensure_control_engine = lambda: (lambda: _IdentitySession(store))


def _control_down():
    CDB._identity_cache.clear()
    CDB._ensure_control_engine = lambda: None


R = lambda tid: asyncio.run(resolve_chat_player_id(tid))

# (1) sem vinculo -> o PROPRIO id. E o estado dos 252 hoje: medido em producao
#     a 2026-08-31, `player_id <> provider_uid::text` = 0 linhas.
_install({})
chk(R(1398335944) == 1398335944,
    "sem vinculo, o chat devolve o PROPRIO telegram_id (no-op medido p/ os 252)")

# (2) com vinculo -> o player_id ligado.
_install({("telegram", "1398335944"): -1000000001})
chk(R(1398335944) == -1000000001,
    "com vinculo, o chat devolve o player_id LIGADO (era este o bug do /status)")

# (3) plano de controlo em baixo -> id cru. Fail-safe absoluto.
_control_down()
chk(R(1398335944) == 1398335944,
    "⚠️ control plane em baixo -> id CRU (nunca 'nao existe', nunca 401)")

# (3b) o resolvedor a levantar -> id cru na mesma.
CDB._identity_cache.clear()
def _boom(): raise RuntimeError("control plane em chamas")
CDB._ensure_control_engine = _boom
chk(R(1398335944) == 1398335944, "erro a levantar -> id cru (Lei §1: nunca tira o comando)")

# (4) id sintetico (nasceu na web) nunca consulta: nao existe `telegram:<neg>`.
CDB._identity_cache.clear()
CDB._ensure_control_engine = lambda: (_ for _ in ()).throw(
    AssertionError("id negativo NAO pode ir ao plano de controlo"))
chk(R(-1000000001) == -1000000001,
    "id sintetico salta a consulta (o mesmo `> 0` do ramo do init_data)")

# (5) lixo nunca rebenta um handler.
for lixo in (None, "abc", ""):
    chk(R(lixo) == lixo, "lixo devolvido intacto, sem levantar (%r)" % lixo)

# (6) idempotencia: resolver um id JA resolvido devolve-o.
_install({("telegram", "1398335944"): -1000000001})
chk(R(-1000000001) == -1000000001,
    "resolver duas vezes e igual a resolver uma (o vinculo e idempotente)")


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 2. ⚠️ O fix PARCIAL: nenhum sitio do chat le o id cru ===")

utils_src = rd("core/utils.py")
chk("resolve_chat_player_id" in utils_src.split("async def _get_player", 1)[1][:400],
    "`_get_player` — o chokepoint dos 101 chamadores — resolve a identidade")
ens = utils_src.split("async def _ensure_player", 1)[1]
ens = ens[:ens.find("\ndef ")]
chk("PlayerArtifact.player_id == player.telegram_id" in ens,
    "`_ensure_player` le os artefactos por `player.telegram_id`, nao por `user.id`")
chk("PlayerArtifact.player_id == user.id" not in ens,
    "⚠️ o id cru saiu do calculo de progresso offline")

# O varredor estrutural. Um `select(Player).where(Player.telegram_id == <id cru>)`
# novo em `handlers/` volta a partir o vinculo em silencio — e isso ja aconteceu
# 4 vezes com "quem finaliza credita". Aqui falha o teste, nao o jogador.
CRU = re.compile(
    r"Player\.telegram_id\s*==\s*(?:update\.effective_user|user|query\.from_user)\.id\b")
ofensas = []
hdir = os.path.join(ROOT, "handlers")
for fn in sorted(os.listdir(hdir)):
    if not fn.endswith(".py"):
        continue
    for i, line in enumerate(rd("handlers/" + fn).split("\n"), 1):
        if CRU.search(line):
            ofensas.append("handlers/%s:%d" % (fn, i))
chk(not ofensas,
    "⚠️ ZERO lookups de Player por id cru em handlers/ (achados: %s)"
    % (", ".join(ofensas) or "nenhum"))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 3. 兩面 O ponto de corte NAO dispara dentro do Telegram ===")

import shutil
import subprocess

ui_src = rd("miniapp/components/ui.js")
chk("function isDesktopSurface()" in ui_src, "`isDesktopSurface` existe em ui.js")
corte = ui_src.split("function isDesktopSurface()", 1)[1][:700]
chk("if (!isWebSurface()) return false;" in corte,
    "⚠️ a 1a condicao e a superficie DECLARADA — dentro do Telegram e sempre telemovel")
chk("DESKTOP_MIN_WIDTH" in corte, "a 2a condicao e a largura")
chk("pointer: fine" in corte, "a 3a e o ponteiro (um tablet deitado passa os 1024px e e dedo)")

# O comportamento, a serio: o ui.js REAL corrido sob node contra 8 superficies.
node = shutil.which("node")
if node:
    r = subprocess.run([node, os.path.join(ROOT, "scripts", "_test_web_c_cutpoint.js")],
                       capture_output=True, text=True)
    for ln in (r.stdout or "").rstrip().split("\n"):
        if ln.strip():
            print("   " + ln.strip())
    chk(r.returncode == 0,
        "⚠️ TELEGRAM DESKTOP a 1600px continua TELEMOVEL (+7 superficies, ui.js real sob node)")
else:
    print("   (node ausente — so o contrato de fonte acima)")
    chk(True, "node ausente: o contrato de fonte fica como unica garantia")

app_src = rd("miniapp/components/app.js")
# WEB-D: o gate MUDOU DE CASA, nao desapareceu. Estava inline no app.js; passou
# para `useWideShell` (ui.js) quando as ABAS precisaram da mesma resposta — e
# esta assercao apanhou a mudanca, que e' exactamente o que ela existe para
# fazer. O invariante continua a ser o mesmo: a superficie larga NAO desenha
# sem a flag per-world (kill-switch do owner).
ui_src_flag = rd("miniapp/components/ui.js")
chk('featureEnabled("superficie_desktop")' in ui_src_flag,
    "a superficie larga esta atras da flag per-world (kill-switch do owner)")
chk("useWideShell" in app_src,
    "e o app.js le esse gate pela casa unica (useWideShell), sem o repetir")
chk('typeof SideRail === "function"' in app_src,
    "typeof-guard: um cliente cacheado fica no telemovel em vez de rebentar")

from database.db import DEFAULT_WORLD_FEATURES, feature_enabled_for_world
chk(DEFAULT_WORLD_FEATURES.get("superficie_desktop") is False,
    "a flag nasce OFF (FF-1: novo = opt-in por mundo)")
chk(feature_enabled_for_world("superficie_desktop", "main") is False,
    "⚠️ `main` le os defaults — OFF eterno para os 248")

# Um so cliente: o telemovel tem de sair BYTE-IDENTICO.
chk("if (!on) return <React.Fragment>{children}</React.Fragment>;" in ui_src,
    "⚠️ `SurfaceColumn` e um Fragment no telemovel — zero DOM novo na superficie dos 248")
chk("{!desktop && (" in app_src,
    "a barra inferior de telemovel nao renderiza no desktop")
# ⚠️ 2026-09-21 — a guarda SEGUE A FORMA NOVA em vez de se baixar. Desde a P5
# ([017] §1) ha' DUAS laterais — a de hubs com a onda ON, a de sempre com ela
# OFF — e as duas continuam DENTRO do mesmo `{desktop && (`. O texto literal
# antigo deixou de existir; a intencao (trilho so' no desktop) nao mudou.
_rail_bloco = app_src[app_src.find("{desktop && ("):] if "{desktop && (" in app_src else ""
_rail_bloco = _rail_bloco[:_rail_bloco.find(")}") + 2]
chk("<SideRail tab={tab}" in _rail_bloco and "<SideRailHubs tab={tab}" in _rail_bloco,
    "o trilho so renderiza no desktop — as DUAS laterais vivem dentro do "
    "mesmo `{desktop && (`")

# Lei de Ferro da UI (a): zero orfaos. O trilho agrupa TAB_DEFS, nao uma lista
# propria — e uma aba sem grupo cai no ultimo em vez de desaparecer.
chk("const orfas = TAB_DEFS.filter" in ui_src,
    "⚠️ uma aba nova sem grupo aparece na mesma (zero orfaos, Lei de Ferro (a))")

import re as _re
grupos = _re.search(r"var RAIL_GROUPS = \[(.*?)\n    \];", ui_src, _re.S)
chk(grupos is not None, "RAIL_GROUPS declarado")
if grupos:
    no_trilho = set(_re.findall(r'"([a-z_0-9]+)"', grupos.group(1)))
    defs = _re.search(r"var TAB_DEFS = \[(.*?)\n    \];", ui_src, _re.S)
    # ⚠️ `(?<!label_)`: sem isto o padrao apanha tambem os `label_key:"tab_*"`
    # e o teste acusa 25 orfas que nao existem (falso vermelho, medido).
    todas = set(_re.findall(r'(?<!label_)key:"([a-z_0-9]+)"', defs.group(1)))
    faltam = todas - no_trilho - {"__manifest_canary"}
    chk(not faltam,
        "todas as abas de TAB_DEFS teem grupo no trilho (sem grupo: %s)"
        % (", ".join(sorted(faltam)) or "nenhuma"))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 4. O site: o que foi morto ficou morto ===")

idx = rd("website/src/pages/Index.tsx")
hero = rd("website/src/components/HeroSection.tsx")

# ⚠️ Procurar o NOME em bruto daria falso vermelho: o comentario do ficheiro
# explica porque cada um saiu, e essa explicacao e para ficar. O que nao pode
# voltar e o IMPORT e o USO.
MORTOS = ["LoadingScreen", "CustomCursor", "ScrollProgress", "MagneticButton"]
for nome in MORTOS:
    usado = ('from "@/components/%s"' % nome) in idx or ("<%s" % nome) in idx \
        or ('from "@/components/%s"' % nome) in hero or ("<%s" % nome) in hero
    chk(not usado, "o site nao importa nem monta `%s`" % nome)
chk("lenis" not in idx.lower().replace("//", "").split("const Index")[0].replace("lenis (smooth scroll)", "")
    or 'from "lenis"' not in idx,
    "o smooth-scroll (Lenis) nao e importado")
chk('from "lenis"' not in idx, "⚠️ `import Lenis from \"lenis\"` saiu — a roda do rato volta a obedecer")
chk('"lenis"' not in rd("website/package.json"),
    "e a dependencia saiu do package.json (nao fica a pesar no lockfile)")

for morto in ("LoadingScreen", "CustomCursor", "MagneticButton"):
    chk(not os.path.exists(os.path.join(ROOT, "website/src/components/%s.tsx" % morto)),
        "o ficheiro %s.tsx foi apagado (Lei §5: nada descartavel fica no chao)" % morto)

# O acto primario: JOGAR. Ate 2026-08-27 o botao de ouro levava a vitrine
# (leitura) e o de jogar levava ao Telegram — e a porta, viva desde 21/08,
# nao era apontada por lado nenhum do site (divida em identidade.md §7).
chk('href="/login"' in hero, "⚠️ o botao primario do hero leva a `/login` — a PORTA")
chk("t.hero.playCta" in hero, "e diz JOGAR (key propria, nas 3 linguas)")
chk('href="/play"' in hero, "a vitrine continua la, em secundario (Lei §1: nada fecha)")
nav = rd("website/src/components/Navbar.tsx")
chk('href="/login"' in nav, "a barra tem a porta")
chk("t.me/Nivrael_bot" in nav, "e o bot continua alcancavel da barra (Lei §1)")
tr = rd("website/src/lib/translations.ts")
chk(tr.count("playCta:") == 4, "playCta declarada no tipo + 3 linguas (achei %d)" % tr.count("playCta:"))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 5. /privacy e /terms — 200 nas 3 linguas, e parecem o site ===")

from aiohttp import web as _web
from aiohttp.test_utils import TestClient, TestServer
import core.webserver as WS

async def _legal_probe():
    app = _web.Application()
    for rota in ("/privacy", "/terms"):
        app.router.add_get(rota, WS.serve_legal_page)
    async with TestClient(TestServer(app)) as cli:
        out = {}
        for rota in ("/privacy", "/terms"):
            for lang in ("pt", "en", "es"):
                r = await cli.get(rota, params={"lang": lang})
                out[(rota, lang)] = (r.status, await r.text())
        return out

paginas = asyncio.run(_legal_probe())
for (rota, lang), (status, html) in sorted(paginas.items()):
    chk(status == 200, "%s?lang=%s -> 200" % (rota, lang))
    chk('lang="%s"' % lang in html, "%s?lang=%s declara a lingua no <html>" % (rota, lang))
    chk("<h2>" in html, "%s?lang=%s tem seccoes (o documento nao veio vazio)" % (rota, lang))

pt = paginas[("/privacy", "pt")][1]
# A linguagem da PORTA, nao a do mini-app. Antes destas paginas herdavam o
# azul-escuro (#06080f) do dashboard e nao se pareciam com nada.
chk("--ink:#0b0a0c" in pt, "⚠️ preto QUENTE (o da porta), nao o azul do mini-app")
chk("#06080f" not in pt, "o azul-escuro do mini-app saiu da pagina legal")
chk("Cormorant+Garamond" in pt, "a mesma tipografia de display da porta")
chk("--seal:#c8442f" in pt, "o cinabrio 朱砂 do selo")
chk('class="seal"' in pt, "e o selo vertical carimbado esta la")
chk('href="/terms"' in pt and 'href="/play"' in pt, "o rodape liga ao outro documento e ao mundo")
chk("{title}" not in pt and "{lang}" not in pt,
    "⚠️ zero chavetas orfas do .format (o CSS tem `{{` duplicadas — uma falha aqui e a pagina crua)")

en = paginas[("/privacy", "en")][1]
chk("Official document" in en, "a sobrancelha nova esta traduzida (en)")
chk("Documento oficial" in paginas[("/privacy", "es")][1], "e em es")


# ══════════════════════════════════════════════════════════════════════════
#  WEB-D 皮 — A PELE (e os olhos para a ver)
# ══════════════════════════════════════════════════════════════════════════
#  Nao e' uma suite nova de proposito (§4 do prompt): o que se guarda aqui e'
#  a MESMA superficie que a WEB-C construiu. O que a WEB-D acrescenta e' que
#  ela finalmente foi VISTA — e o que se viu tem de ficar visto.
print("\n-- WEB-D 皮 · a paleta e o trilho ------------------------------")

_UI   = io.open(os.path.join(ROOT, "miniapp", "components", "ui.js"),   encoding="utf-8").read()
_TABS = io.open(os.path.join(ROOT, "miniapp", "components", "tabs.js"), encoding="utf-8").read()
_APP  = io.open(os.path.join(ROOT, "miniapp", "components", "app.js"),  encoding="utf-8").read()
_HTML = io.open(os.path.join(ROOT, "miniapp", "index.html"),            encoding="utf-8").read()

_HEX_RE  = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_RGBA_RE = re.compile(r"\brgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}")

# -- 1. A CONTAGEM. O criterio do §2.1 e' um NUMERO, nao uma impressao. -----
# Antes da varredura (medido 2026-08-31, e escrito no doc da linguagem visual):
#   tabs.js = 412 literais hex + 1459 chamadas rgba() = 1871 sitios que uma
#   troca de `:root` NAO alcancava. Um `background:"#0d1422"` escrito a mao
#   dentro de um componente ignora a variavel — logo trocar o token mudava o
#   fundo e mais NADA.
# Estes tectos sao o clique da roquete: podem descer, nunca subir.
_TABS_HEX_ANTES, _TABS_RGBA_ANTES = 412, 1459
_tabs_hex  = len(_HEX_RE.findall(_TABS))
_tabs_rgba = len(_RGBA_RE.findall(_TABS))
chk(_tabs_hex < _TABS_HEX_ANTES,
    "tabs.js: literais hex %d < %d (antes da varredura)" % (_tabs_hex, _TABS_HEX_ANTES))
chk(_tabs_rgba < _TABS_RGBA_ANTES,
    "tabs.js: rgba() literais %d < %d (antes da varredura)" % (_tabs_rgba, _TABS_RGBA_ANTES))
# Tecto absoluto: se alguem colar 200 cores novas a mao, isto acende.
chk(_tabs_hex <= 170, "tabs.js: hex a mao <= 170 (esta em %d)" % _tabs_hex)
chk(_tabs_rgba <= 600, "tabs.js: rgba() a mao <= 600 (esta em %d)" % _tabs_rgba)
chk(_TABS.count("var(--") >= 3000,
    "tabs.js le a paleta por token em >=3000 sitios (%d)" % _TABS.count("var(--"))

# -- 2. A ARMADILHA R3/R5, agora como invariante do ficheiro ----------------
# `${cor}88` concatena alpha. Se `cor` for um `var(--x)` o resultado
# (`var(--gold2)88`) e' invalido *at-computed-value-time* e derruba a
# declaracao INTEIRA em silencio — ja custou dois sprints (R3 e R5). Depois da
# varredura QUALQUER tabela de cores pode virar token a qualquer momento; a
# unica defesa estavel e' exigir que o alpha-concat passe sempre por
# `cssHex()`, que resolve o var() de volta a hex.
_ALPHA_CONCAT = re.compile(r"\$\{([^{}]{1,80}?)\}([0-9a-fA-F]{2})(?![0-9a-fA-F])")
for _nome, _src in (("ui.js", _UI), ("tabs.js", _TABS), ("app.js", _APP)):
    def _em_comentario(_s, _pos):
        # Um `//` antes do match, na mesma linha, faz disto prosa e nao codigo.
        # A nota historica da R5 CITA o padrao antigo de proposito.
        _ini = _s.rfind("\n", 0, _pos) + 1
        return "//" in _s[_ini:_pos]
    _nus = [m.group(0) for m in _ALPHA_CONCAT.finditer(_src)
            if not m.group(1).strip().startswith("cssHex(")
            and not _em_comentario(_src, m.start())]
    chk(not _nus,
        "%s: zero alpha-concat sem cssHex() (a licao R3/R5) — %d encontrados: %s"
        % (_nome, len(_nus), _nus[:3]))
# E o caso NOMEADO pelo prompt: realmColor() devolve `var(--realm-N)` e nunca
# pode receber sufixo alpha. O irmao hex e' realmHex().
chk(not re.search(r"realmColor\([^)]*\)\s*\}?[0-9a-fA-F]{2}\b", _UI + _TABS),
    "nenhum realmColor(...) recebe sufixo alpha (usa-se realmHex/cssHex)")

# -- 3. O ESPELHO. Duas paletas a divergir e' o bug seguinte. ---------------
# `CSS_VAR_HEX` existe porque tres sitios exigem hex literal e nao sabem ler
# var(): o alpha-concat, `tg.setHeaderColor()` e os atributos de SVG. Se o
# :root mudar e o espelho nao, metade do jogo pinta com a paleta velha.
_root_m = re.search(r":root \{(.*?)\n    \}", _HTML, re.S)
chk(_root_m is not None, ":root encontrado em index.html")
_root_rgb = {}
for _m in re.finditer(r"--([a-z0-9-]+)-rgb:\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", _root_m.group(1)):
    _root_rgb[_m.group(1)] = "#%02x%02x%02x" % (int(_m.group(2)), int(_m.group(3)), int(_m.group(4)))
chk(len(_root_rgb) >= 27, ":root define >=27 tripletos -rgb (%d)" % len(_root_rgb))

_mirror_m = re.search(r"var CSS_VAR_HEX = \{(.*?)\n    \};", _UI, re.S)
chk(_mirror_m is not None, "CSS_VAR_HEX encontrado em ui.js")
_mirror = dict(re.findall(r'"(--[a-z0-9-]+)"\s*:\s*"(#[0-9a-fA-F]{6})"', _mirror_m.group(1)))
_drift = [(k, v, _root_rgb[k[2:]]) for k, v in _mirror.items()
          if k[2:] in _root_rgb and _root_rgb[k[2:]].lower() != v.lower()]
chk(not _drift, "CSS_VAR_HEX == :root (zero deriva): %s" % (_drift[:3],))
# Toda a paleta NAO-realm/NAO-ambiente tem de estar no espelho: uma que falte
# cai no fallback dourado e o dano fica cor de ouro.
_faltam = [k for k in _root_rgb
           if not k.startswith(("realm-", "amb-")) and ("--" + k) not in _mirror]
chk(not _faltam, "nenhum token fora do espelho CSS_VAR_HEX: %s" % (_faltam,))

# -- 4. Todo `var(--x-rgb)` usado EXISTE no :root ---------------------------
# Um tripleto inexistente nao da erro: a declaracao morre calada.
_usados = set(re.findall(r"var\(--([a-z0-9-]+)-rgb\)", _UI + _TABS + _APP + _HTML))
_orfaos = sorted(u for u in _usados if u not in _root_rgb)
chk(not _orfaos, "zero var(--X-rgb) sem definicao no :root: %s" % (_orfaos,))
# E o inverso: `rgba(var(--token))` sem o sufixo -rgb seria `rgba(rgb(...))`.
_sem_sufixo = [n for n in re.findall(r"rgba?\(var\(--([a-z0-9-]+)\)", _UI + _TABS + _APP)
               if not n.endswith("-rgb")]
chk(not _sem_sufixo,
    "nenhum rgba(var(--token)) sem o sufixo -rgb: %s" % (_sem_sufixo[:3],))

# -- 5. cssHex() devolve HEX. E' a unica funcao onde var() seria o bug. -----
# A varredura converteu os fallbacks desta funcao por engano (apanhado no
# diff): quem a chama cola-lhe um alpha logo a seguir.
_css_hex = re.search(r"var cssHex = \(c, fb\) => \{(.*?)\n    \};", _UI, re.S)
chk(_css_hex is not None, "cssHex encontrado")
chk(_css_hex is not None and "var(--" not in _css_hex.group(1),
    "cssHex nao devolve var() em ramo nenhum (os fallbacks sao hex literal)")

# -- 6. A FLAG da pele nasce OFF e `main` le os defaults --------------------
_DB = io.open(os.path.join(ROOT, "database", "db.py"), encoding="utf-8").read()
chk(re.search(r'"pele_quente":\s*False', _DB) is not None,
    "a flag `pele_quente` existe e nasce OFF (main le os defaults)")
chk('featureEnabled("pele_quente")' in _APP, "a pele so' e' aplicada atras da flag")
chk("applyWarmSkin" in _UI, "applyWarmSkin existe em ui.js")
# Flag PROPRIA: a pele nao pode ficar refem do shell do Pergaminho Vivo
# (ui_v2, OFF eterno no main) nem do layout largo (superficie_desktop).
_linhas_pele = [l for l in _APP.splitlines() if 'featureEnabled("pele_quente")' in l]
chk(bool(_linhas_pele) and "ui_v2" not in _linhas_pele[0]
    and "superficie_desktop" not in _linhas_pele[0],
    "a pele e' ortogonal: nao depende de ui_v2 nem de superficie_desktop")
# A pele tem de repintar TAMBEM o espelho — senao o alpha-concat e o SVG
# continuam frios ("meio quente e meio azul", o que o doc proibe).
_warm_hex_m = re.search(r"var WARM_SKIN_HEX = \{(.*?)\n    \};", _UI, re.S)
chk(_warm_hex_m is not None, "WARM_SKIN_HEX existe")
chk("CSS_VAR_HEX[k] = WARM_SKIN_HEX[k]" in _UI,
    "a pele repinta o espelho CSS_VAR_HEX (senao o alpha-concat fica azul)")
chk("setHeaderColor" in _UI.split("var applyWarmSkin")[1].split("};")[0],
    "a pele repinta tambem a moldura do Telegram")
_warm_rgb_m = re.search(r"var WARM_SKIN_RGB = \{(.*?)\n    \};", _UI, re.S)
chk(_warm_rgb_m is not None, "WARM_SKIN_RGB existe")
_warm_rgb = set(re.findall(r'"([a-z0-9-]+)":\s*"\d+,\d+,\d+"', _warm_rgb_m.group(1)))
chk("bg" in _warm_rgb and "text" in _warm_rgb,
    "a pele troca o fundo e o texto (as duas decisoes do doc §1)")
chk(set(["amb-sky", "amb-ridge1", "amb-ridge2", "amb-ridge3",
         "amb-pagoda", "amb-aura"]).issubset(_warm_rgb),
    "a pele alcanca o AMBIENTE (o fundo de constelacao — a maior superficie do "
    "jogo; sem isto ficava uma montanha AZUL sobre preto quente)")
chk(not [k for k in _warm_rgb if k.startswith("realm-")],
    "a pele NAO toca nas cores dos reinos (identidade do jogo, nao moldura)")
# Todo token que a pele escreve tem de existir no :root.
_warm_orfaos = sorted(k for k in _warm_rgb if k not in _root_rgb)
chk(not _warm_orfaos, "a pele nao escreve tokens inexistentes: %s" % (_warm_orfaos,))

# -- 7. O TRILHO, o que o §1 viu com os olhos ------------------------------
# MEDIDO 2026-09-01 a servir o jogo a serio: a 1280x720 o trilho tinha 1131px
# de conteudo em 720px e OITO destinos ficavam por baixo da dobra — Mercado,
# Forja, Combate, Bestas, Passe, Loja, Noticias e Configuracoes — sem UM pixel
# a dizer que aquilo deslizava, porque `*::-webkit-scrollbar{width:0}` e'
# global. Lei No 1 partida por uma regra de CSS escrita para o telemovel.
chk('className="scroll-area nv-rail"' in _UI,
    "o trilho tem a classe .nv-rail (a que devolve a barra de deslocacao)")
chk(".nv-rail::-webkit-scrollbar" in _HTML and "scrollbar-width: thin" in _HTML,
    "index.html devolve a barra ao trilho")
chk(re.search(r"@media \(min-width: 1024px\) and \(pointer: fine\) \{[^@]*?\.nv-rail\b",
              _HTML, re.S) is not None,
    "a barra so' volta no ponteiro FINO — no telemovel o esconderijo global fica")
chk(_HTML.index("*::-webkit-scrollbar") < _HTML.index(".nv-rail::-webkit-scrollbar"),
    "a regra do trilho vem DEPOIS da global (a especificidade empata: manda a ordem)")
chk('el.scrollIntoView({ block: "nearest" })' in _UI,
    "o destino ACTIVO e' trazido a vista (senao o jogador esta numa aba que o "
    "trilho jura nao existir)")

# -- 8. Um cartao de telemovel esticado a 514px continua vazio -------------
# MEDIDO: `1fr 1fr` + `aspectRatio:"1/1"` dava cartoes de 177x177 no telemovel
# (o desenho) e de 514x514 no desktop, com 440px de vazio entre o medalhao e o
# titulo — e a Home passava de ~2600px para 5436px de altura. O ecra LARGO
# ficava com MAIS scroll do que o telemovel para o mesmo conteudo.
chk("function useWideShell" in _UI, "useWideShell existe (a conjuncao numa so' casa)")
chk("typeof useWideShell" in _TABS, "as abas sabem perguntar pela superficie larga")
chk("repeat(auto-fill, minmax(168px, 1fr))" in _TABS,
    "a grelha da Home poe MAIS cartoes por linha em vez de os inchar")
chk('"1fr 1fr"' in _TABS, "e o ramo de telemovel continua la (byte-identico)")
# A conjuncao mora numa so' casa: duas copias divergiriam no primeiro sprint.
chk(_APP.count('featureEnabled("superficie_desktop")') == 0,
    "app.js ja nao repete a conjuncao (le useWideShell)")


# ══════════════════════════════════════════════════════════════════════════
#  WEB-E 坐 — A CENA DO CULTIVO
# ══════════════════════════════════════════════════════════════════════════
#  Continua a NAO ser uma suite nova (§4 do prompt): e' a mesma superficie.
#  O que se guarda aqui e' a promessa da cena — que ela nao remove nada, que
#  nasce OFF, e que a tela deixa de mentir a 57% de quem a abre.
print("\n-- WEB-E 坐 · a cena do cultivo --------------------------------")

# -- 1. A FLAG nasce OFF e e' ORTOGONAL as outras tres de superficie -------
chk(re.search(r'"cena_cultivo":\s*False', _DB) is not None,
    "a flag `cena_cultivo` existe e nasce OFF (main le os defaults)")
_linha_cena = [l for l in _TABS.splitlines() if 'featureEnabled("cena_cultivo")' in l]
chk(len(_linha_cena) == 1,
    "a cena tem UM so' gate (%d encontrados)" % len(_linha_cena))
chk(bool(_linha_cena) and not any(f in _linha_cena[0]
        for f in ("ui_v2", "superficie_desktop", "pele_quente")),
    "a cena e' ortogonal: nao depende de ui_v2, superficie_desktop nem pele_quente")

# -- 2. NADA FOI REMOVIDO (Lei de Ferro (a): 100% das features alcancaveis) -
# A cena funde quatro caixas numa composicao. Se alguma peca tivesse ficado
# pelo caminho, o jogador com a flag ON perdia jogo — e um teste que so olhe
# para o ramo OFF nunca daria por isso.
_cena_m = re.search(r"function CultivationScene\(\{(.*?)\n    \}\n", _UI, re.S)
chk(_cena_m is not None, "CultivationScene existe em ui.js")
_cena = _cena_m.group(1) if _cena_m else ""
for _peca, _msg in (
        ("CultivationOrb",        "o orbe"),
        ('t("cultivation")',      "o rotulo do Cultivo"),
        ('t("qi")',               "o rotulo do Qi"),
        ("cbNow", "os numeros crus da base"), ("cbMax", "o limiar da base"),
        ("qiNow", "o qi actual"),             ("qiMax", "a capacidade de qi"),
        ("realmLabel",            "o nome do reino"),
        ("qiRegenMult",           "o chip de regeneracao de qi"),
        ("medLabel",              "o tipo de meditacao"),
        ("medMult",               "o multiplicador"),
        ("remainMs",              "o tempo que falta"),
        ('t("meditate_stop")',    "o botao de interromper"),
        ("medTypes",              "os quatro assentos"),
        ("m.min_realm",           "os cadeados de reino dos assentos"),
        ("{cta}",                 "os CTAs de Avancar/Renascer"),
):
    chk(_peca in _cena, "a cena mantem %s (`%s`)" % (_msg, _peca))

# -- 3. Os CTAs sao o MESMO JSX nos dois ramos -----------------------------
# Um botao de Avancar que so existisse num dos ramos seria a Lei No 1 partida
# pela flag — e seria invisivel para quem so testasse o ramo OFF.
chk(_TABS.count("const advanceCta = (") == 1,
    "os CTAs vivem numa constante unica")
# ⚠️ 2026-09-16 (坐 ONDA 1): passaram a ser TRES ramos (onda / cena / o
# classico). O numero fica EXACTO de proposito — um `>= 2` deixaria nascer
# um quarto ramo sem CTA nenhum, que e' exactamente o que esta guarda
# existe para apanhar. Quem acrescentar um ramo muda este numero A OLHAR.
chk(_TABS.count("{advanceCta}") == 3,
    "a MESMA constante e' renderizada nos TRES ramos (%d usos)"
    % _TABS.count("{advanceCta}"))
chk(_TABS.count("const trialCard = ") == 1 and _TABS.count("{trialCard}") == 3,
    "o cartao de Ritual Pendente tambem e' o mesmo JSX nos TRES ramos (%d)"
    % _TABS.count("{trialCard}"))

# -- 4. A tela deixa de MENTIR no cume -------------------------------------
# MEDIDO 2026-09-02 nas duas DBs de producao: 21 dos 37 activos-30d do `main`
# (57%) estao em reino 10 camada 9. La `check_breakthrough` FIXA a base no
# limiar e devolve None ⇒ encher a barra nao produz evento nenhum, e
# `breakthroughReady` e' falso por construcao (o `prestigeReady` tem
# precedencia). Sem uma palavra, a barra finge uma contagem decrescente para a
# maioria de quem abre a tela. Lei No 1: honest disclosure, nunca silent void.
chk("atCeiling" in _cena, "a cena recebe o estado de cume")
chk('t("cena_ceiling_title")' in _cena and 't("cena_ceiling_body")' in _cena,
    "e DIZ o cume por palavras (nao so' por ausencia de botao)")
chk("atCeiling={prestigeReady}" in _TABS,
    "o cume da cena e' o MESMO predicado que troca o CTA para Renascer")
_gl = re.search(r"const prestigeReady = (.*?);", _TABS, re.S)
chk(_gl is not None and ">= 10" in _gl.group(1) and ">= 9" in _gl.group(1),
    "prestigeReady continua a ser reino 10 + camada 9 (o topo canonico)")

# -- 5. Uma so' barra no jogo (a paleta nao pode aquecer metade) -----------
# O fio da cena e' o `ProgressBar` com `bare`, nao uma segunda barra: as tres
# cores vivem numa casa. Uma copia divergia na primeira troca de paleta.
chk("function ProgressBar({ pct, variant=\"cult\", height=8, bare=false, over=false })" in _UI,
    "ProgressBar ganhou `bare` e `over` (em vez de uma segunda barra) — os "
    "dois sao ADITIVOS, e e' por isso que os 14 usos de hoje nao mudam")
chk("<ProgressBar pct={pct} variant={variant} height={3} bare />" in _UI,
    "o fio da cena REUSA o ProgressBar (mesmo gradiente do resto do jogo)")

# -- 6. Um botao de 1070px e' o erro dos cartoes de 514x514 ----------------
chk("maxWidth: wide ? 460 : undefined" in _UI,
    "a accao da cena tem tecto de largura no ecra largo (a MEDIDA fica inteira)")

# -- 7. i18n: as 6 chaves novas existem nas TRES linguas -------------------
import json as _json
_CENA_KEYS = ["cena_remaining", "cena_idle_title", "cena_idle_body",
              "cena_idle_choose", "cena_ceiling_title", "cena_ceiling_body"]
_counts = {}
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    _counts[_lang] = len(_d)
    _falta = [k for k in _CENA_KEYS if not _d.get(k)]
    chk(not _falta, "miniapp/i18n/%s.json tem as chaves da cena: falta %s"
        % (_lang, _falta))
chk(len(set(_counts.values())) == 1,
    "paridade i18n do mini-app nas 3 linguas: %s" % _counts)

# -- 8. O nome do reino nao pode aparecer em INGLES numa tela em PT --------
# VISTO (nao apanhado por teste nenhum): o `lifespan_engine` devolve o nome
# canonico em INGLES por decisao declarada, e o cartao do Mar de Longevidade
# imprimia-o cru. Resultado: "Core Formation: 500 anos" a 300px do cartao que
# diz "Nucleo" — o MESMO reino com dois nomes na mesma tela. O payload ja traz
# o inteiro e o cliente ja sabe traduzi-lo.
chk("player.lifespan.realm_name" not in _TABS,
    "o cartao do Lifespan nao imprime o realm_name do servidor (ingles)")
chk("player.lifespan.next_realm_name" not in _TABS,
    "nem o next_realm_name")
chk("realmName(player.lifespan.realm)" in _TABS
    and "realmName(player.lifespan.next_realm)" in _TABS,
    "usa realmName(<inteiro>) — a chave realm_N, traduzida nas 3 linguas")
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    chk(all(_d.get("realm_%d" % _i) for _i in range(11)),
        "miniapp/i18n/%s.json define realm_0..realm_10" % _lang)



# ══════════════════════════════════════════════════════════════════════════
#  牌 A CARTA (2026-09-05) — a arte servida + a carta-padrao
# ══════════════════════════════════════════════════════════════════════════
print("\n-- 牌 A CARTA --------------------------------------------------")

_WS = rd("core/webserver.py")

# ── 1. A ARTE. Existia desde 2026-05-01 e o servidor nunca serviu um byte. ──
_rules_m = re.search(r"_MINIAPP_SUBDIR_RULES = \{(.*?)\n\}", _WS, re.S)
chk(_rules_m is not None, "assets: _MINIAPP_SUBDIR_RULES encontrado")
_rules_src = _rules_m.group(1) if _rules_m else ""
chk('"assets": {' in _rules_src, "assets: existe uma regra `assets`")
_assets_m = re.search(r'"assets": \{(.*?)\n    \}', _rules_src, re.S)
_assets = _assets_m.group(1) if _assets_m else ""
chk('"dir": "newapp/assets"' in _assets,
    "assets: a rota /miniapp/assets/ aponta para a pasta newapp/assets")
chk('".webp"' in _assets, "assets: .webp e' servivel")
chk("immutable" in _assets and "31536000" in _assets,
    "assets: cache LONGA e imutavel (o oposto do bundle, que revalida)")

# ⚠️ `.webp` ja vem comprimido: gzipa-lo gasta CPU por ~0% (as vezes cresce).
_comp_m = re.search(r"_COMPRESSIBLE_SUFFIXES = frozenset\(\{(.*?)\}\)", _WS, re.S)
_comp = _comp_m.group(1) if _comp_m else ""
for _ext in (".webp", ".png", ".jpg", ".avif"):
    chk(_ext not in _comp,
        "assets: %s FORA de _COMPRESSIBLE_SUFFIXES (ja vem comprimido)" % _ext)

# ⚠️ GUARDA QUE SEGUE A INDIRECCAO (licao 2026-09-04): a regra `assets` e' a
# unica onde a ROTA e a PASTA divergem. Se o handler voltar a colar
# `MINIAPP_DIR / subdir / name`, a arte da 404 e a cena fica sem fundo — em
# silencio, porque o fallback e' honesto de proposito.
chk('rule.get("dir", subdir)' in _WS,
    "⚠️ assets: o handler resolve a pasta por `rule.get(\"dir\", subdir)`")

# ── 2. As 11 ilustracoes EXISTEM, e na ordem dos reinos ────────────────────
_UI2 = rd("miniapp/components/ui.js")
_art_m = re.search(r"var REALM_ART_FILES = \[(.*?)\];", _UI2, re.S)
chk(_art_m is not None, "assets: REALM_ART_FILES declarado no ui.js")
_art = re.findall(r'"([^"]+\.webp)"', _art_m.group(1) if _art_m else "")
chk(len(_art) == 11, "assets: 11 ficheiros de reino listados (%d)" % len(_art))
_falta = [f for f in _art if not os.path.isfile(os.path.join(ROOT, "miniapp", "newapp", "assets", f))]
chk(not _falta, "⚠️ assets: TODOS os ficheiros listados existem em disco: %s" % (_falta,))
# a ordem e' o indice do reino: trocar duas linhas poe a tempestade da
# Tribulacao por tras de um Mortal, e nada falha — so' mente.
chk(_art[0] == "realm-mortal.webp" and _art[10] == "realm-true-immortal.webp",
    "assets: a ordem e' o indice do reino (0 mortal .. 10 true-immortal)")

# ⚠️ O `hero-bg` e o `clouds-divider` sao MOLDURA fria e nao entram sem serem
# regenerados quentes (veredicto escrito em newapp/README.md, 2026-09-04).
chk("hero-bg" not in _UI2 and "clouds-divider" not in _UI2,
    "⚠️ assets: hero-bg/clouds-divider NAO sao referidos pelo jogo (moldura azul)")

# ── 2b. O INDICE da arte das pecas (2026-09-06) ───────────────────────────
# ⚠️ O nome do ficheiro DERIVA do nome do catalogo, nos dois lados: `gen_art.py`
# ao gravar e `_artSlug` no `ui.js` ao pedir. Se as duas transformacoes
# divergirem, a carta cai no verso honesto — nao parte, mas a arte paga fica
# invisivel e ninguem da' por isso. Estas duas guardas apanham as duas metades.
_idx_m = re.search(r"var NIV_ART_INDEX = new Set\(\[(.*?)\]\);", _UI2, re.S)
chk(_idx_m is not None, "arte: NIV_ART_INDEX declarado no ui.js")
_idx = re.findall(r'"([^"]+)"', _idx_m.group(1) if _idx_m else "")
_semficheiro = [g for g in _idx
                if not os.path.isfile(os.path.join(ROOT, "miniapp", "newapp",
                                                   "assets", g + ".webp"))]
chk(not _semficheiro,
    "⚠️ arte: todo slug do indice tem .webp em disco: %s" % (_semficheiro,))
# e o inverso: arte paga que ficou de fora do indice nunca chega ao jogador.
try:
    # ⚠️ O indice cobre as PECAS (o que passa por `pieceArt`). Duas familias
    # NAO sao pecas e por isso nao entram nele:
    #   `realm-*`      — o retrato/lugar do reino, pedido por `realmArtUrl`
    #   `cultivator-*` — a figura da cena, pedida por `cultivatorArtUrl`
    # Nenhuma das duas cai no verso de uma carta, logo o modo de falha que este
    # indice existe para impedir (arte paga invisivel em silencio) nao se lhes
    # aplica: se faltarem, ha' `onError` proprio na cena.
    #   `hub-*` / `door-*` — 圖 O MAPA (2026-09-11): a cena de um hub e as
    #                  portas que vivem nela. Pedidas por `HUB_SCENE_DEFS` e
    #                  com `onError` proprio no `HubScene` (a chapa de recurso),
    #                  exactamente como as duas acima.
    #   `land-*`     — 州 O MUNDO (2026-09-13): os cinco continentes. Familia
    #                  propria e nao `door-` porque a `door` PROIBE por nome
    #                  montanhas e nevoeiro (um continente e' as duas coisas),
    #                  mas o papel no ecra e' identico: pedida pelo mesmo
    #                  `HUB_SCENE_DEFS`, desenhada pelo mesmo `HubScene`, com a
    #                  mesma chapa de recurso no mesmo `onError`. Esta guarda
    #                  MORDEU outra vez quando as 5 entraram — o que prova que
    #                  ela continua a olhar para o disco — e alarga-se pelo
    #                  MESMO motivo de sempre: nenhuma delas cai no verso de uma
    #                  carta, que e' o unico modo de falha que o indice existe
    #                  para impedir.
    # ⚠️ Esta guarda MORDEU quando as 6 pecas entraram, e foi assim que se
    # confirmou que ela olha mesmo para o disco. Alargar a lista e' a correccao
    # certa SO' porque o modo de falha nao se aplica: nada disto cai no verso de
    # uma carta. Uma peca de verdade que ficasse de fora do indice continua a
    # por isto vermelho.
    #   `isle-*`     — 州 O CHAO DOS CINCO CONTINENTES (2026-09-16): a pintura
    #                  `place` de cada continente, sobre a qual as seis
    #                  `door-mundo-*` assentam. Mesmo papel no ecra que as
    #                  `hub-*`: pedida por tabela propria (`ISLE_SCENE_ART`),
    #                  desenhada pelo mesmo `HubScene`, com o mesmo `onError`.
    #                  Esta guarda MORDEU quando as 5 entraram — 3a vez que o faz
    #                  numa familia nova, e 3a vez que o disco confirma que ela
    #                  olha mesmo para la'.
    _NAO_PECA = ("realm-", "cultivator-", "hub-", "door-", "land-", "isle-")
    _todos = [f[:-5] for f in os.listdir(os.path.join(ROOT, "miniapp", "newapp", "assets"))
              if f.endswith(".webp") and not f.startswith(_NAO_PECA)
              and f not in ("hero-bg.webp", "clouds-divider.webp", "alchemy-art.webp")]
    _forade = sorted(set(_todos) - set(_idx))
    chk(not _forade,
        "⚠️ arte: nenhuma peca gerada ficou FORA do indice (invisivel): %s" % (_forade,))
except FileNotFoundError:
    chk(False, "pasta de assets legivel")
# as duas transformacoes de slug tem de concordar — provado num nome com "The"
# e outro com sufixo, que sao os dois casos que ja' mordiam.
try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("gen_art", os.path.join(ROOT, "scripts", "gen_art.py"))
    _ga = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_ga)
    # 🔴 2026-09-15 — OS TRES CASOS DE CIMA ERAM TODOS ASCII PURO, e por isso
    # esta guarda esteve verde enquanto as duas metades DIVERGIAM: em Python
    # `"ú".isalnum()` e' True e o ficheiro nascia `tech-yún-step-reborn.webp`;
    # no cliente `ú` nao casa `[a-z0-9]` e pedia-se `tech-y-n-step-reborn`. A
    # peca — paga, gerada, aprovada, em disco, NO INDICE — nunca chegou a um
    # jogador. Os dois primeiros casos abaixo sao os que faltavam.
    _casos = [("technique", "Yún Step Reborn", "tech-yun-step-reborn"),
              ("beast", "Bestia del Vacío", "beast-bestia-del-vacio"),
              ("technique", "The Abyss Wears Your Name", "tech-the-abyss-wears-your-name"),
              ("pill", "Qi Gathering Pill", "pill-qi-gathering-pill"),
              ("beast", "Celestial Crane", "beast-celestial-crane")]
    _mau = [n for k, n, esperado in _casos
            if _ga.asset_name({"kind": k, "name": n}) != esperado + ".webp"]
    chk(not _mau, "⚠️ arte: gen_art.py e o ui.js derivam o MESMO slug: %s" % (_mau,))
    # 🔴 A TERCEIRA PERNA — E ELA CORRE O CLIENTE, NAO LE' O CLIENTE.
    #
    # As duas guardas de cima comparam o INDICE com o DISCO, e a 15/09 os dois
    # estavam de acordo *no erro*: o ficheiro chamava-se
    # `tech-yún-step-reborn.webp` e a chave do indice era `tech-yún-step-reborn`
    # — identicas uma a' outra e ambas inalcancaveis, porque a cadeia real e'
    # CLIENTE -> indice -> disco e o cliente nunca estava na comparacao.
    #
    # ⚠️ A primeira versao DESTA guarda afirmava `'.normalize("NFD")' in _UI2` e
    # ficou VERDE com o cliente sabotado: encontrava o seu alvo no COMENTARIO
    # que explicava a correccao. 5a vez que esta casa paga a mesma licao. A
    # outra metade usava `_ga.slugify` — o slug do PYTHON — para afirmar sobre o
    # slug do CLIENTE, que e' o proprio bug com mais passos.
    # Por isso esta arranca o `_artSlug` do `ui.js` REAL e corre-o sob node,
    # como a guarda do ponto de corte la' em cima (§1). Comentario nenhum pode
    # satisfaze-la.
    _sl_m = re.search(r"var _artSlug = (.*?);\s*$", _UI2, re.S | re.M)
    chk(_sl_m is not None, "arte: `_artSlug` declarado no ui.js")
    if _sl_m and node:
        _corpus = ["Yún Step Reborn", "Yún Wúmíng", "Bestia del Vacío",
                   "Café Palm", "Heaven's Edge", "The Abyss Wears Your Name",
                   "Void Beast", "Celestial Crane", "Qi Gathering Pill"] + _idx
        _js = ("var _artSlug = %s; "
               "console.log(JSON.stringify(JSON.parse(process.argv[1])"
               ".map(function (s) { return _artSlug(s); })));" % _sl_m.group(1))
        _r = subprocess.run([node, "-e", _js, _json.dumps(_corpus)],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=60)
        _cli = _json.loads(_r.stdout or "[]")
        chk(len(_cli) == len(_corpus),
            "arte: o `_artSlug` real corre sob node (%s)" % (_r.stderr or "")[:120])
        # (a) as DUAS metades da mesma regra dao o mesmo slug, em nomes com acento
        _diverge = [(n, _ga.slugify(n), c)
                    for n, c in zip(_corpus, _cli) if _ga.slugify(n) != c]
        chk(not _diverge,
            "⚠️ arte: `gen_art.slugify` e o `_artSlug` do ui.js CORRIDO dao o "
            "mesmo slug: %s" % (_diverge[:4],))
        # (b) toda chave do indice e' PRODUZIVEL pelo cliente. Uma chave que o
        #     `_artSlug` nao consegue gerar e' uma chave que ninguem pede:
        #     arte paga, indexada, e invisivel em silencio.
        _instavel = [g for g, c in zip(_corpus[-len(_idx):], _cli[-len(_idx):])
                     if g != c]
        chk(not _instavel,
            "⚠️ arte: toda chave do indice e' PRODUZIVEL pelo `_artSlug` do "
            "cliente: %s" % (_instavel[:4],))
    _nao_ascii = sorted(f for f in os.listdir(
        os.path.join(ROOT, "miniapp", "newapp", "assets")) if not f.isascii())
    chk(not _nao_ascii,
        "⚠️ arte: nenhum ficheiro em disco tem caracter nao-ASCII no nome "
        "(o cliente nunca o pediria): %s" % (_nao_ascii,))
except Exception as _e:  # pragma: no cover
    chk(False, "gen_art.py importavel para comparar slugs (%s)" % _e)

# ── 3. A carta so' desenha com a flag, e a flag nasce OFF ──────────────────
from database.db import DEFAULT_WORLD_FEATURES as _DWF, feature_enabled_for_world as _few
chk(_DWF.get("cartas") is False, "cartas: a flag nasce OFF no catalogo (Lei §5)")
chk(_few("cartas", "main") is False, "cartas: OFF no `main` (os 248 nao veem nada)")

_TABS2 = rd("miniapp/components/tabs.js")
# ⚠️ NAO-REGRESSAO POR CONSTRUCAO: cada sitio convertido guarda o markup de
# hoje num `*Classic` e chama-o quando a flag esta OFF. Se um destes
# desaparecer, o caminho velho deixou de existir e `main` mudou de cara.
# ⚠️ 2026-09-08 — os dois novos (`ArtifactCellClassic`/`ItemCellClassic`) TEM de
# estar nesta lista. Provado a apagar a chamada do primeiro com a lista antiga:
# a suite ficou VERDE. Uma guarda que cobre 3 de 5 caminhos e' uma guarda que
# nao morde nos outros 2 — e a mochila e' o sitio que os 248 mais abrem.
for _fn in ("LearnedRowClassic", "RecipeCardClassic", "EquippedRowClassic",
            "ArtifactCellClassic", "ItemCellClassic"):
    _declarado = ("function %s(" % _fn) in _TABS2
    # ⚠️ A 1a versao desta guarda procurava `Nome({` como prova de CHAMADA e
    # nunca podia falhar: a propria declaracao e' `function Nome({ tech, ...`.
    # Provado a apagar a chamada — verde na mesma. Contar as ocorrencias e' a
    # unica forma de distinguir "declarado" de "declarado E usado".
    _usos = _TABS2.count(_fn)
    chk(_declarado and _usos >= 2,
        "cartas: `%s` declarado E chamado (%d usos; o caminho OFF continua vivo)"
        % (_fn, _usos))
chk(_TABS2.count('featureEnabled("cartas")') >= 6,
    "cartas: os sitios convertidos leem a flag (%d)" % _TABS2.count('featureEnabled("cartas")'))

# ⚠️ §2.1 — os invólucros que trocam a MOLDURA por espaço. Com a flag OFF eles
# tem de devolver o `<Card>`/`<CardTitle>` de hoje; se alguem simplificar o
# `CardHost`/`CardShell` para devolver sempre o `<div>`, os 248 perdem a moldura
# do jogo inteiro sem um unico teste vermelho.
for _fn in ("CardHost", "CardShell"):
    chk(("function %s(" % _fn) in _UI2 and _UI2.count(_fn) >= 1,
        "moldura: `%s` existe em ui.js" % _fn)
_host_m = re.search(r"function CardHost\(\{ cards.*?\n    \}", _UI2, re.S)
chk(_host_m is not None and "<Card style={style}>" in _host_m.group(0)
    and "<CardTitle left={title} right={right} />" in _host_m.group(0),
    "⚠️ moldura: com a flag OFF o CardHost devolve o <Card>+<CardTitle> de hoje")
_shell_m = re.search(r"function CardShell\(\{ cards.*?\n    \}", _UI2, re.S)
chk(_shell_m is not None and "<Card style={style} ornate={ornate}>" in _shell_m.group(0),
    "⚠️ moldura: com a flag OFF o CardShell devolve o <Card> com as MESMAS props")
chk(_TABS2.count("<InvGrid cards={invCards}>") >= 3,
    "moldura: as tres grelhas da mochila passam pelo InvGrid (%d)"
    % _TABS2.count("<InvGrid cards={invCards}>"))
# ⚠️ O `InvGrid` TEM de viver no topo do ficheiro, nunca dentro do
# `InventoryTab`: uma seta declarada no corpo do componente re-cria o TIPO a
# cada render e o React desmonta/remonta a grelha inteira — visto a olho, a
# arte da mochila apagava-se sozinha ao mexer em qualquer filtro. Nenhum teste
# de DOM apanha isto (os dois caminhos rendem o mesmo markup).
chk("\n    function InvGrid({ cards, children }) {" in _TABS2,
    "⚠️ moldura: `InvGrid` e' declarado no TOPO (nao dentro do InventoryTab)")
_inv_m = re.search(r"function InventoryTab\(.*?\n    \}\n", _TABS2, re.S)
chk(_inv_m is not None and "const InvGrid" not in _inv_m.group(0),
    "⚠️ moldura: nenhum `const InvGrid` dentro do InventoryTab (remonta tudo)")

# ── 3b. 朱砂 O SELO marca uma ESCOLHA, e por isso tem prop propria ─────────
# Visto a olho a 2026-09-08: os 4 artefactos equipados punham QUATRO carimbos de
# cinabrio na primeira tela da mochila. Quatro deixam de ser um acento.
chk("const showSeal = seal === undefined ? isActive : !!seal;" in _UI2,
    "⚠️ selo: `seal` e' uma prop com omissao = o estado activo")
chk("{showSeal && <SealMark" in _UI2 and "{isActive && <SealMark" not in _UI2,
    "⚠️ selo: quem desenha o carimbo e' `showSeal`, nao `isActive`")
chk("seal={false}" in _TABS2,
    "⚠️ selo: a mochila desliga-o (um slot cheio nao e' uma escolha)")
chk('stateLabel={t("combat_tech_status_equipped")}' in _TABS2
    and "seal={false}" not in _TABS2.split('stateLabel={t("combat_tech_status_equipped")}')[1][:400],
    "⚠️ selo: a arte EQUIPADA no Combate MANTEM o carimbo (la ha escolha)")

# ── 4. 品 O LOMBO: as escalas do cliente == as escalas do MOTOR ────────────
# ⚠️ Esta e' a guarda cara. Se alguem acrescentar um 6º grau de tecnica em
# Python, o lombo continua a desenhar CINCO entalhes e passa a mentir sobre a
# posicao de todas as artes — sem erro nenhum.
_sc_m = re.search(r"var NIV_RANK_SCALES = \{(.*?)\n    \};", _UI2, re.S)
chk(_sc_m is not None, "lombo: NIV_RANK_SCALES declarado")
_sc = _sc_m.group(1) if _sc_m else ""


def _order(kind):
    m = re.search(kind + r":\s*\{ order: \[(.*?)\]", _sc, re.S)
    return [x.lower() for x in re.findall(r'"([^"]+)"', m.group(1))] if m else []


from core.combat_engine import GRADE_ORDER as _GO
from config import BEAST_RANKS as _BR
chk(_order("technique") == [g.lower() for g in _GO],
    "⚠️ lombo: a escala da tecnica == core.combat_engine.GRADE_ORDER (%d)" % len(_GO))
chk(_order("beast") == [r.lower() for r in _BR],
    "⚠️ lombo: a escala da besta == config.BEAST_RANKS (%d)" % len(_BR))
from core.alchemy_engine import MAX_ALCHEMY_TIER as _MAT
_pill_m = re.search(r"pill:\s+\{ steps: (\d+), numeric: true", _sc)
chk(_pill_m is not None and int(_pill_m.group(1)) == _MAT,
    "⚠️ lombo: a escala da pilula == core.alchemy_engine.MAX_ALCHEMY_TIER (%d)" % _MAT)
chk("recipe.required_alchemy_tier" in _TABS2 and "kind=\"pill\" rank={recipe.difficulty}" not in _TABS2,
    "⚠️ lombo: a pilula pontua por `required_alchemy_tier`, NUNCA por `difficulty`")

# ⚠️ A GUARDA QUE FALTAVA, e que teria apanhado o meu proprio erro. A 1a versao
# desta carta pontuava a pilula por `difficulty` "1..5" — e `difficulty` vai a
# **7** nos seeds. As pilulas de grau 6 e 7 saturavam em 5 de 5 e ficavam
# indistinguiveis das de 5: o lombo a mentir exactamente como uma cor mentiria.
# Comparar o cliente com o MOTOR nao chegou; e preciso comparar com os DADOS.
try:
    from database.seeds.combat_seeds import TECHNIQUES as _SEED_T
    from database.seeds.alchemy_seeds import PILLS as _SEED_P
    from database.seeds.beasts_seeds import BEASTS as _SEED_B
    _fora = sorted({int(p["required_alchemy_tier"]) for p in _SEED_P} - set(range(1, _MAT + 1)))
    chk(not _fora, "⚠️ dados: nenhuma pilula seedada acima da escala do lombo: %s" % _fora)
    _fora = sorted({b["rank"] for b in _SEED_B} - set(_BR))
    chk(not _fora, "⚠️ dados: nenhuma besta seedada fora de BEAST_RANKS: %s" % _fora)
    # as tecnicas nascem sempre "common" (o grau sobe por upgrade, nao por seed)
    chk(all("grade" not in _t for _t in _SEED_T),
        "dados: nenhuma tecnica seedada traz grau proprio (o grau e' ganho)")

    # ── 全 2026-09-08 — o ARTEFACTO, e o erro que os dados derrubaram ──────
    # ⚠️ O prompt deste lote mandava dar ao artefacto uma escala de QUATRO
    # (`normal|perfect|divine|spirit`). Esses quatro sao a QUALIDADE DE FORJA,
    # nao um posto: o motor infere-a post-hoc (`infer_artifact_quality`), nunca
    # a persiste, o refino APAGA-a, e `refined` esta "OUTSIDE the order on
    # purpose". E' a mesma familia de campo que o `difficulty` da pilula.
    # O posto e' o `grade` — e sao os SEEDS que o provam: os 51 artefactos
    # ocupam os NOVE degraus. Com uma escala de 4, dois tercos do catalogo
    # saturavam no topo e o lombo mentia como uma cor mentiria.
    from config import ARTIFACT_GRADES as _AG
    from database.seeds.artifacts_seeds import ARTIFACTS as _SEED_A
    _art_m = _re.search(r"artifact:\s+\{ steps: (\d+), numeric: true, base: (\d+)", _sc)
    chk(_art_m is not None and int(_art_m.group(1)) == len(_AG),
        "⚠️ lombo: a escala do artefacto == config.ARTIFACT_GRADES (%d)" % len(_AG))
    chk(_art_m is not None and int(_art_m.group(2)) == min(_AG),
        "⚠️ lombo: o artefacto comeca no grau %d (a UNICA escala base-0)" % min(_AG))
    _fora = sorted({int(a["grade"]) for a in _SEED_A} - set(_AG))
    chk(not _fora, "⚠️ dados: nenhum artefacto seedado fora de ARTIFACT_GRADES: %s" % _fora)
    # ⚠️ E o inverso, que e' o que apanha uma escala CURTA DEMAIS: se os seeds
    # so usassem 4 dos 9 degraus, uma escala de 4 passaria a checagem acima.
    _usados = sorted({int(a["grade"]) for a in _SEED_A})
    chk(len(_usados) == len(_AG),
        "⚠️ dados: os seeds ocupam TODOS os %d degraus do artefacto (usados: %d)"
        % (len(_AG), len(_usados)))
    # a qualidade de forja NAO e' o lombo, e `refined` fica FORA da ordem
    from core.forge_engine import ARTIFACT_QUALITY_ORDER as _AQO
    chk("refined" not in _AQO,
        "⚠️ motor: `refined` esta FORA de ARTIFACT_QUALITY_ORDER (eixo a parte)")
    chk('kind="artifact" rank={a.grade}' in _TABS2,
        "⚠️ lombo: o artefacto pontua por `grade`, NUNCA pela qualidade de forja")

    # ── as outras tres escalas do lote, contra os seus motores ────────────
    from core.dao_laws_engine import RARITY_WEIGHTS as _DRW
    chk(_order("dao_law") == sorted([r.lower() for r in _DRW],
                                    key=lambda r: -_DRW[r]),
        "⚠️ lombo: a escala da lei do Dao == RARITY_WEIGHTS (%d, do mais comum ao mais raro)"
        % len(_DRW))
    _tq = _re.search(r"TRAP_QUALITY_ORDER = \{([^}]*)\}",
                     rd("core/beast_engine.py"))
    _tq_pairs = _re.findall(r'"(\w+)":\s*(\d+)', _tq.group(1)) if _tq else []
    _tq_order = [k for k, _ in sorted(_tq_pairs, key=lambda kv: int(kv[1]))]
    chk(_order("trap") == _tq_order,
        "⚠️ lombo: a escala da armadilha == core/beast_engine TRAP_QUALITY_ORDER (%s)"
        % _tq_order)
    # ⚠️ o caso contra-intuitivo, fixado de proposito: na armadilha `mythic`
    # esta ABAIXO de `legendary`; na besta esta ACIMA. As duas estao certas e a
    # carta segue o motor de CADA conteudo — e' por isso que ha oito
    # vocabularios em vez de um codigo de cores.
    chk(_tq_order.index("mythic") < _tq_order.index("legendary")
        and [r.lower() for r in _BR].index("mythic") > [r.lower() for r in _BR].index("legendary"),
        "⚠️ dados: armadilha e besta DISCORDAM em mythic/legendary — e ambas estao certas")
    from database.seeds.gacha_seeds import GACHA_BANNERS as _GB
    _buckets = set()
    for _b in _GB:
        _buckets |= {k for k in (_b.get("items") or {})}
    chk(set(_order("gacha")) == {b.lower() for b in _buckets},
        "⚠️ lombo: a escala do gacha == os baldes seedados do banner (%s)"
        % sorted(_buckets))
except Exception as _e:  # pragma: no cover
    chk(False, "dados: seeds legiveis (%s)" % _e)

# ── 5. Cada valor de cada escala tem PALAVRA nas 3 linguas ────────────────
# Sem a palavra, o lombo diz "3 de 5" e o jogador nunca sabe de QUE.
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    _sem = [g for g in _GO if not _d.get("technique_grade_%s" % g.lower())]
    chk(not _sem, "lombo/%s: todo grau de tecnica tem nome: %s" % (_lang, _sem))
    _sem = [r for r in _BR if not _d.get("beast_rank_%s" % r.lower())]
    chk(not _sem, "lombo/%s: todo posto de besta tem nome: %s" % (_lang, _sem))
    chk(bool(_d.get("alch_grade")), "lombo/%s: a pilula usa alch_grade" % _lang)

# ── 5b. 坐 O CULTIVADOR (2026-09-07) ──────────────────────────────────────
# Ordem do owner: o orbe morre. Tres coisas a proteger.

# (a) O ORBE NAO PODE VOLTAR PELA PORTA DAS TRASEIRAS.
# ⚠️ O ✦ e' o glifo que a industria inteira usa para dizer "gerado por IA", e
# estava no centro da tela mais aberta do jogo. O emoji do reino era pior: muda
# de forma de aparelho para aparelho. Os dois vivem em `orbCenterIcon`, que so'
# pode ser chamado pelo caminho CLASSICO.
_fig = _UI2[_UI2.index("function CultivatorFigure("):_UI2.index("function CultivationOrbClassic(")]
chk("orbCenterIcon" not in _fig,
    "⚠️ cultivador: a figura NAO usa `orbCenterIcon` (nem o ✦ nem o emoji do reino)")
chk("✦" not in _fig and "REALM_EMOJIS" not in _fig,
    "⚠️ cultivador: nenhum ✦ e nenhum emoji de sistema na figura")
# ⚠️ A 1a versao desta guarda contava `radial-gradient` e estava errada: a
# aureola e o assento vazio SAO gradientes, e legitimamente. O que distingue a
# figura do orbe nao e' a ausencia de gradiente — e' a presenca de uma IMAGEM e
# a ausencia da tabela de onze esferas.
chk("<img src={src}" in _fig and "cultivatorArtUrl" in _UI2,
    "cultivador: a figura e' uma IMAGEM servida, nao uma esfera desenhada")
chk("orbGradients" not in _fig,
    "cultivador: a tabela das 11 esferas de gradiente ficou no caminho CLASSICO")

# (b) A FIGURA SO' EXISTE SENTADA — a tela nao se pode contradizer.
# ⚠️ Isto foi apanhado a OLHAR: a 1a versao desenhava o cultivador sempre, e a
# cena ficou a dizer "VOCE NAO ESTA SENTADO" por baixo de uma figura sentada.
# E' a mesma familia do defeito que a WEB-E achou no cume.
chk(_re.search(r"\{meditating && !failed && \(\s*<img", _fig) is not None,
    "⚠️ cultivador: a figura so' e' desenhada com `meditating` (senao a tela mente)")
chk("{!meditating && (" in _fig,
    "cultivador: de pe' desenha o ASSENTO VAZIO, nao um buraco (Lei §1)")

# (c) O CAMINHO OFF continua vivo, e a arte nova nao vaza para ele.
chk("function CultivationOrbClassic(" in _UI2 and _UI2.count("CultivationOrbClassic") >= 2,
    "cultivador: `CultivationOrbClassic` declarado E chamado (o caminho OFF vive)")
chk('featureEnabled("cultivador")' in _UI2,
    "cultivador: a cena le' a flag")
chk("REALM_PLACE_FILES" in _UI2 and "-place.webp" in _UI2,
    "cultivador: os reinos-LUGAR tem nome proprio (cache imutavel: regenerar = ficheiro NOVO)")

# (d) as 14 pecas EXISTEM em disco, e as tres figuras cobrem os TRES estados
# (o terceiro, `null`, e' o dos ~248 do beta — nao e' um caso de canto).
_ASSETS = os.path.join(ROOT, "miniapp", "newapp", "assets")
_falta = [f for f in
          [n.replace(".webp", "-place.webp") for n in
           _re.findall(r'"(realm-[a-z-]+\.webp)"', _UI2)]
          if not os.path.exists(os.path.join(_ASSETS, f))]
chk(not _falta, "⚠️ cultivador: os 11 reinos-LUGAR estao em disco: %s" % (_falta,))
_figs = ["cultivator-male.webp", "cultivator-female.webp", "cultivator-back.webp"]
_faltaf = [f for f in _figs if not os.path.exists(os.path.join(_ASSETS, f))]
chk(not _faltaf, "⚠️ cultivador: as TRES figuras estao em disco: %s" % (_faltaf,))
chk('CULTIVATOR_ART[g] || "cultivator-back.webp"' in _UI2,
    "⚠️ cultivador: genero desconhecido/NULL cai no 背影, nunca num buraco")

# (e) o genero e' COSMETICO — nada fica bloqueado por ele.
# ⚠️ O casamento (`dao_partners`) existe desde antes desta coluna e continua
# gender-free: exigir par masculino/feminino REMOVERIA algo que jogadores reais
# fazem hoje. Esta guarda existe para impedir isso por distraccao.
_partner = rd("core/partner_engine.py") + rd("handlers/partner.py")
chk("gender" not in _partner.lower(),
    "⚠️ genero: o casamento NAO le' genero (gender-free por desenho)")
# ⚠️ Ler o SQL SEM os comentarios: a 1a versao deu vermelho porque o proprio
# cabecalho do ficheiro diz "sem DROP" — a guarda estava a apanhar a promessa em
# vez do codigo. Uma guarda que le' comentarios nao le' o que executa.
_mig140 = " ".join(l for l in rd("migrations/140_gender.sql").splitlines()
                   if not l.strip().startswith("--"))
chk("DROP" not in _mig140.upper(), "genero: Mig 140 nao tem DROP")
chk("IF NOT EXISTS" in _mig140.upper() and "DEFAULT NULL" in _mig140.upper(),
    "genero: Mig 140 e' idempotente e nasce NULL (compativel para tras)")

# ── 6. 朱砂 — o selo e' ASSINATURA, nao moldura ────────────────────────────
# ⚠️ Se `seal` entrar no WARM_SKIN_RGB, o carimbo passa a mudar com a pele e
# deixa de ser uma assinatura. E' o mesmo argumento que ja protege as 11
# cores de reino (`Mecanicas/miniapp.md` §1.6).
_warm_m = re.search(r"var WARM_SKIN_RGB = \{(.*?)\n    \};", _UI2, re.S)
_warm = _warm_m.group(1) if _warm_m else ""
chk('"seal"' not in _warm,
    "⚠️ selo: `seal` FORA do WARM_SKIN_RGB — cinabrio nas duas peles")
chk("--seal-rgb: 200,68,47" in _HTML, "selo: --seal-rgb definido no :root (朱砂 #c8442f)")
chk('"--seal":"#c8442f"' in _UI2, "selo: espelhado no CSS_VAR_HEX (alpha-concat)")
# o selo e' SVG e nao um caractere: o mini-app nao carrega fonte CJK e a 19px
# o fallback do sistema muda de aparelho para aparelho.
chk("function SealMark(" in _UI2 and "<svg" in _UI2[_UI2.index("function SealMark("):_UI2.index("function SealMark(") + 900],
    "selo: e' um SVG, nao um caractere CJK")

# ── 7. O VERSO HONESTO (Lei §1) — nunca um buraco ─────────────────────────
_ca = _UI2[_UI2.index("function CardArt("):_UI2.index("var NIV_CARD_STATES")]
chk("onError" in _ca, "verso: a arte que falha cai no verso (onError)")
chk('loading="lazy"' in _ca, "verso: a arte e' lazy")
chk(_ca.index("placeItems") < _ca.index("<img"),
    "⚠️ verso: o verso e' pintado ANTES da <img> — nunca ha buraco enquanto carrega")

# ── 8. A CENA: a arte e' o LUGAR, o orbe continua a ser o ESTADO ──────────
# ⚠️ 6 das 11 ilustracoes mostram alguem sentado e 5 NAO (mortal=paisagem,
# foundation=de pe, void=combate, tribulation=de pe, true-immortal=a voar).
# Legendar qualquer uma como "voce esta sentado" seria imprimir uma mentira
# por cima da imagem — e o reino 10 e' 57% dos activos-30d do `main`.
_scene = _UI2[_UI2.index("function RealmBackdrop("):_UI2.index("function CultivationScene(")]
# ⚠️ A assinatura ganhou um 2o argumento a 2026-09-07 (`places`, que escolhe o
# LUGAR VAZIO em vez do retrato antigo). O que esta guarda protege nao e' a
# forma da chamada — e' que a cena peca UMA imagem, a do reino do JOGADOR, e
# nunca as onze. Por isso passa a exigir o argumento `realm` e a proibir
# qualquer varredura do array inteiro.
chk(_re.search(r"realmArtUrl\(realm[,)]", _scene) is not None,
    "cena: carrega SO' o reino do jogador")
chk("REALM_ART_FILES.map" not in _scene and "REALM_PLACE_FILES.map" not in _scene,
    "⚠️ cena: nunca pede as ONZE imagens de uma vez (o arranque paga zero)")
chk("onError" in _scene and "setFailed" in _scene,
    "cena: a arte que falha some e a cena volta a ser a de 02/09 (Lei §1)")
chk('loading="lazy"' in _scene, "cena: a arte de fundo e' lazy")
chk("<CultivationOrb" in _UI2,
    "⚠️ cena: o ORBE continua la — e' a unica peca que carrega o ESTADO")
chk('zIndex:1' in _UI2[_UI2.index("<RealmBackdrop"):_UI2.index("<RealmBackdrop") + 900],
    "⚠️ cena: o conteudo sobe uma camada (senao os fios pintam POR BAIXO do fundo)")

# ═══════════════════════════════════════════════════════════════════════════
# 印 OS ICONES (2026-09-08) — a iconografia propria
#
# O que estas guardas existem para impedir, e cada uma nasceu de um defeito
# REAL desta casa:
#
#  a) **Uma marca que nao existe desenha NADA.** `ico()` cai para o emoji
#     quando o nome nao esta no registo — mas um `mark:"pagoda2"` escrito a
#     mao passaria despercebido para sempre, porque a tela continua a mostrar
#     um icone. A guarda SEGUE A INDIRECCAO (a licao de 2026-09-05: um guarda
#     estrutural nunca se baixa a procurar o literal).
#  b) **Uma marca sem casa e' codigo descartavel** (Lei §5). O `crate` foi
#     desenhado neste mesmo lote e apagado a meio, quando se mediu que a
#     seccao "outros" da mochila nunca desenhou icone nenhum.
#  c) **A OFF-identidade.** Com a flag desligada cada sitio tem de devolver o
#     emoji de hoje — e' a promessa aos 248. Por isso todo `ico(` tem de levar
#     um emoji como PRIMEIRO argumento.
#  d) **A regressao de acessibilidade.** A barra de baixo so' escreve o rotulo
#     do slot ACTIVO; trocar sete emoji por SVG mudos deixaria sete botoes sem
#     nome nenhum para um leitor de ecra.
#  e) **O sparkle de quatro pontas.** E' o glifo que a industria usa desde 2023
#     para dizer "gerado por IA", e foi por causa dele que o owner mandou matar
#     o orbe a 07/09. Nao pode voltar a nascer dentro do registo de marcas.
print("\n=== 10. 印 As marcas: o registo, a cobertura e a OFF-identidade ===")

_UIM = rd("miniapp/components/ui.js")
_TBM = rd("miniapp/components/tabs.js")
_AI_GLYPH = u"✦"
_AI_GLYPH2 = u"✧"


def _obj_after(src, needle):
    """O texto do objecto/array literal que comeca depois de `needle`."""
    i = src.index(needle)
    cands = [k for k in (src.find("{", i), src.find("[", i)) if k >= 0]
    j = min(cands)
    close = {"{": "}", "[": "]"}[src[j]]
    depth, k = 0, j
    while k < len(src):
        if src[k] == src[j]:
            depth += 1
        elif src[k] == close:
            depth -= 1
            if depth == 0:
                return src[j:k + 1]
        k += 1
    raise AssertionError("literal nao fechado: " + needle)


def _strip_js_comments(src):
    """O mesmo texto sem `//...`, sem `/*...*/` e sem `{/*...*/}` de JSX.

    Existe porque uma guarda sobre um GLIFO nao pode confundir markup com a
    prosa que explica porque e' que aquele glifo foi morto.
    """
    out = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"//[^\n]*", " ", out)


def _fn_src(src, needle):
    """A fonte de uma funcao inteira, do `function X(` ate' a' seguinte.

    ⚠️ NAO usar `_obj_after` para isto: em `function DetailModal({ entry, ... })`
    o primeiro `{` e' o DESTRUCTURING dos parametros, e uma guarda sobre ele
    fica verde a afirmar coisas sobre sete nomes de props em vez do corpo.
    Descoberto a correr, nao a ler.
    """
    i = src.index(needle)
    j = src.find("\n    function ", i + len(needle))
    if j < 0:
        j = len(src)
    return src[i:j]


_MARKS_SRC = _obj_after(_UIM, "var NIV_MARKS = ")
_MARK_NAMES = set(re.findall(r"^      ([a-z_]+):\s*\{", _MARKS_SRC, re.M))
chk(len(_MARK_NAMES) >= 35,
    "marcas: o registo tem %d marcas (>=35)" % len(_MARK_NAMES))

# (a) TODA marca pedida existe — seguindo a indireccao, nunca o literal.
_REQ = {}
for _label, _src, _pat in (
    # ⚠️ O nome da marca le'-se como `[^"]*`, NUNCA como `[a-z_]+`. A 1a versao
    # usava `[a-z_]+` e a sabotagem `mark:"pagoda2"` ficou VERDE: com um digito
    # no nome, o PAR inteiro deixava de casar e a orfa tornava-se invisivel.
    # Uma guarda que so' ve' os nomes bem escritos nao guarda nada.
    ("TAB_DEFS", _obj_after(_UIM, "var TAB_DEFS = "), r'key:"([a-z_]+)",[^\n]*?mark:"([^"]*)"'),
    ("HOME_CARDS", _obj_after(_TBM, "var HOME_CARDS = "), r'key:"([a-z_]+)",[^\n]*?mark:"([^"]*)"'),
    ("SLOT_MARKS", _obj_after(_TBM, "var SLOT_MARKS = "), r'([a-z0-9_]+):"([^"]*)"'),
):
    _pairs = re.findall(_pat, _src)
    chk(len(_pairs) >= 6, "%s: %d entradas com marca" % (_label, len(_pairs)))
    for _k, _m in _pairs:
        _REQ.setdefault(_m, []).append("%s.%s" % (_label, _k))

for _src in (_UIM, _TBM):
    for _m in re.findall(r'ico\(\s*"[^"]+"\s*,\s*"([^"]*)"', _src):
        _REQ.setdefault(_m, []).append("ico() inline")
    for _m in re.findall(r'markOn\("([^"]*)"\)', _src):
        _REQ.setdefault(_m, []).append("markOn() inline")

_orfas = sorted(m for m in _REQ if m not in _MARK_NAMES)
chk(not _orfas,
    "marcas: TODA marca pedida existe no registo (orfas: %r)" % (_orfas,))

# (b) e ao contrario: nenhuma marca desenhada sem casa (Lei §5).
_mortas = sorted(_MARK_NAMES - set(_REQ))
chk(not _mortas,
    "marcas: nenhuma marca sem casa — zero codigo descartavel (mortas: %r)" % (_mortas,))

# TAB_DEFS e' a lista MAE: o trilho de desktop agrupa-a, nao tem lista propria.
# Uma aba sem marca e' um buraco nas DUAS superficies de uma vez.
_tabs_src = _obj_after(_UIM, "var TAB_DEFS = ")
_all_tabs = re.findall(r'\{ key:"([a-z_]+)"', _tabs_src)
_tabs_sem = [k for k in _all_tabs
             if not re.search(r'key:"%s",[^\n]*?mark:"' % re.escape(k), _tabs_src)]
chk(not _tabs_sem,
    "marcas: as %d abas TODAS tem marca (sem: %r)" % (len(_all_tabs), _tabs_sem))

_home_src = _obj_after(_TBM, "var HOME_CARDS = ")
_all_cards = re.findall(r'\{ key:"([a-z_]+)"', _home_src)
_cards_sem = [k for k in _all_cards
              if not re.search(r'key:"%s",[^\n]*?mark:"' % re.escape(k), _home_src)]
chk(not _cards_sem,
    "marcas: os %d cartoes da Home TODOS tem marca (sem: %r)" % (len(_all_cards), _cards_sem))

# (c) a OFF-identidade: `ico(` sem emoji devolveria `undefined` com a flag OFF.
# ⚠️ Duas fontes NAO-literais sao aceites, e so' porque as duas linhas abaixo
# provam que elas nunca sao vazias: `td.ico` (toda entrada de TAB_DEFS tem
# `ico:"..."`) e `icon` (todo cartao da Home tem `icon:"..."`). Sem essas duas
# provas isto seria uma porta aberta, nao uma lista de excepcoes.
# 2026-09-09: `h.ico` entra na lista — e SO' entra porque a prova ao lado
# existe: a guarda dos hubs (§15) exige `ico:` em TODA entrada de
# `HUB_DEFS`. Sem essa prova isto era uma porta aberta.
_ICO_FONTES_OK = ("td.ico", "icon", "h.ico")
chk(len([k for k in _all_tabs
         if re.search(r'key:"%s",[^\n]*?ico:"' % re.escape(k), _tabs_src)]) == len(_all_tabs),
    "OFF-identidade: TODA aba tem `ico:` (a fonte de `td.ico` nunca e' vazia)")
chk(len([k for k in _all_cards
         if re.search(r'key:"%s",[^\n]*?icon:"' % re.escape(k), _home_src)]) == len(_all_cards),
    "OFF-identidade: TODO cartao da Home tem `icon:` (a fonte de `icon` nunca e' vazia)")
_bad_ico = []
for _f, _src in (("ui.js", _UIM), ("tabs.js", _TBM)):
    for _m in re.finditer(r"(?<![a-zA-Z_.])ico\(([^,]{0,40}),", _src):
        if _src[max(0, _m.start() - 9):_m.start()].endswith("function "):
            continue                      # a propria declaracao `function ico(emoji, ...)`
        _first = _m.group(1).strip()
        if _first.startswith('"') and len(_first) > 2:
            continue
        if _first in _ICO_FONTES_OK:
            continue
        _bad_ico.append("%s: ico(%s" % (_f, _first[:24]))
chk(not _bad_ico,
    "OFF-identidade: todo `ico()` leva um emoji (literal ou fonte provada) (%r)" % (_bad_ico[:3],))
chk("if (!name || !NIV_MARKS[name] || !iconografiaOn()) return emoji;" in _UIM,
    "OFF-identidade: `ico()` devolve o emoji quando a flag esta' OFF")
chk(re.search(r'function iconografiaOn\(\)\s*\{\s*return typeof featureEnabled === "function"'
              r'\s*&& featureEnabled\("iconografia"\);', _UIM) is not None,
    "OFF-identidade: a flag le'-se do Manifesto (fail-safe se o helper faltar)")

# (d) a acessibilidade da barra de baixo
_bn = _UIM[_UIM.index("function BottomNav("):_UIM.index("function BottomNav(") + 4600]
chk("aria-label={markOn(td.mark) ? t(td.label_key) : undefined}" in _bn,
    "acessibilidade: com marcas, o botao da barra ganha `aria-label` (Lei §1)")

# (e) o sparkle nao volta a nascer no registo, nem no mini-orbe da Home
chk(_AI_GLYPH not in _MARKS_SRC and _AI_GLYPH2 not in _MARKS_SRC,
    "o glifo de 'AI' nao existe dentro de NIV_MARKS")
_orb = _TBM[_TBM.index("function HomeCultivationCard("):
            _TBM.index("function HomeCultivationCard(") + 3600]
chk(('ico("' + _AI_GLYPH + '", "seated"') in _orb,
    "o sparkle do mini-orbe da Home passa a ser a figura sentada")

# o contrato do desenho: cor SO' do sitio onde a marca vive
chk('stroke="currentColor"' in _UIM and 'fill="currentColor"' in _UIM,
    "marcas: o traco e os pontos usam `currentColor` (a cor vem do sitio)")
chk(not re.search(r"(#[0-9a-fA-F]{3,8}|rgba?\()", _MARKS_SRC),
    "marcas: ZERO cor propria dentro do registo (senao a pele nao lhes chega)")
chk("var NIV_MARK_GRID = { view: 24, stroke: 1.6 }" in _UIM,
    "marcas: uma grelha so' — 24x24, traco 1.6")
chk('viewBox="0 0 24 24"' in _UIM[_UIM.index("function Mark("):
                                  _UIM.index("function Mark(") + 1600],
    "marcas: todas desenham na MESMA caixa de 24")

# a regra dos 20px, medida: nenhuma marca passa de 8 pecas de desenho.
# (Nao prova beleza — prova que nenhuma virou nodoa por acumulacao.)
_pesadas = []
for _nm in sorted(_MARK_NAMES):
    _body = _obj_after(_MARKS_SRC, "\n      %s:" % _nm)
    _n = len(re.findall(r'"M[^"]+"', _body)) + len(re.findall(r"\[[\d.]+,[\d.]+,[\d.]+\]", _body))
    if _n == 0:
        _pesadas.append(_nm + " (VAZIA)")
    elif _n > 8:
        _pesadas.append("%s (%d)" % (_nm, _n))
chk(not _pesadas,
    "20px: nenhuma marca vazia nem com mais de 8 pecas (%r)" % (_pesadas[:4],))

print("\n=== 11. 印 A flag: nasce OFF e auto-documenta-se ===")
_DB = rd("database/db.py")
_feat = _obj_after(_DB, "DEFAULT_WORLD_FEATURES")
chk(re.search(r'"iconografia":\s*False', _feat) is not None,
    "flag: `iconografia` nasce OFF em DEFAULT_WORLD_FEATURES (o `main` le' defaults)")
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    chk("feature_iconografia" in _d and len(_d["feature_iconografia"]) > 6,
        "flag: rotulo no painel do owner em %s" % _lang)
    chk("feature_iconografia_desc" in _d and len(_d["feature_iconografia_desc"]) > 400,
        "flag: descricao auto-documentada em %s" % _lang)

# ⚠️ Escrito pelo ASSUNTO, nunca sobre "a migration mais alta do repositorio".
# A Mig 140 pos SETE suites vermelhas de uma vez a 2026-09-07 porque afirmavam
# um TECTO GLOBAL. Isto continua verdade daqui a cem migrations.
# ⚠️ `mark` como sub-cadeia apanha `044_market_unit_price.sql` — a 1a versao
# desta guarda ficou vermelha por causa do MERCADO. O assunto tem de ser um
# SEGMENTO do nome, nao um pedaco de palavra.
_meu = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
        if re.search(r"(?:^|_)(icon|icone|icons|icones|iconografia|marca|marcas)(?:_|\.)", m, re.I)]
chk(not _meu,
    "nenhuma migration fala de icones — o lote e' re-render puro (%r)" % (_meu,))

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 12. 器 O ITEM: a foto no detalhe + os tres patamares ===")

# ── 12a. A FOTO. A arte estava paga, indexada e servida — e escondida ─────
#
# ⚠️ O defeito e' de OMISSAO, e por isso nenhuma guarda antiga podia apanha-lo:
# `pieceArt("artifact", ...)` ja' servia 51/51 na CELULA e o modal simplesmente
# nao chamava. Codigo que nao existe nao da erro. A guarda tem de afirmar a
# CHAMADA, dentro do modal, nao a existencia da funcao.
_DETAIL = _fn_src(_TBM, "function DetailModal(")
# ⚠️ 2026-09-14 — a guarda SOBE, nao desce. A chamada passou a levar um 3º
# argumento (`entry.art_key`) porque o nome do payload passou a ir TRADUZIDO e o
# slug da arte tem de vir do canonico — sem ele eram 229 pecas invisiveis em pt
# e es. Aceitar `pieceArt("artifact", entry.name` truncado deixaria passar a
# versao SEM chave, que e' exactamente o defeito novo. Por isso exige-se a
# chamada COM a chave: afirma a foto E a lingua no mesmo assert.
chk('pieceArt("artifact", entry.name, entry.art_key)' in _DETAIL,
    "foto: o modal de detalhe PEDE a arte do artefacto, COM a chave canonica "
    "(sem ela a foto existe so' em ingles)")
chk('pieceArt("pill", entry.name, entry.art_key)' in _DETAIL,
    "foto: o modal de detalhe pede a arte da PILULA, COM a chave canonica "
    "(o artefacto e a pilula ficaram os dois para tras a 07/09, nao so' um)")
chk("<PieceHero" in _DETAIL,
    "foto: usa o PieceHero — a MESMA chapa da besta")

# ⚠️ UM SO' componente de chapa em todo o cliente. Bifurcar duplicaria o verso
# honesto, o `onError` e o `lazy`, e um dos dois ficaria para tras — que e'
# exactamente como este defeito nasceu (a correccao de 07/09 cobriu 1 de 3).
_HERO_DEFS = re.findall(r"function\s+(\w*PieceHero\w*)\s*\(", _UIM + _TBM)
chk(_HERO_DEFS == ["PieceHero"],
    "foto: existe UMA definicao de chapa-heroi em todo o cliente (%r)" % (_HERO_DEFS,))

# ⚠️ A guarda que apanha o valor ASSADO. O `PieceHero` sangra `-bleed` para
# comer a goteira do corpo do modal; o `Modal` da casa tem `padding:14` e este
# modal e' feito a mao com **18**. Assar 14 aqui deixaria uma tira de 4px do
# fundo a' volta da arte — a moldura que a chapa existe para nao ter. Se alguem
# mexer no padding do painel sem mexer no bleed, isto fica vermelho.
# ⚠️ 2026-09-09 — A GUARDA SEGUIU A INDIRECCAO, NAO SE BAIXOU. O padding deixou
# de estar no `style` do painel e passou a ser o `bodyStyle` do `Overlay` (o
# modal deixou de ser escrito a mao — ver §14). O que a guarda mede e' o MESMO:
# a goteira que a arte tem de comer. Procura-se onde ela vive AGORA.
_m_pad = (re.search(r'bodyStyle=\{\{\s*padding:"(\d+)px (\d+)px (\d+)px"', _DETAIL)
          or re.search(r'borderRadius:14,\s*padding:"(\d+)px (\d+)px (\d+)px"', _DETAIL))
chk(_m_pad is not None, "foto: o painel do modal declara o seu padding (ancora da guarda)")
if _m_pad:
    _m_bleed = re.search(r"bleed=\{(\d+)\}", _DETAIL)
    chk(_m_bleed is not None and _m_bleed.group(1) == _m_pad.group(2),
        "foto: o `bleed` (%s) == o padding lateral do painel (%s) — a arte encosta "
        "ao vidro, sem tira de fundo a' volta"
        % (_m_bleed and _m_bleed.group(1), _m_pad.group(2)))

# O ✦ ("gerado por IA", proibido na casa desde 07/09) sai do ramo NOVO. No ramo
# desligado fica onde sempre esteve — mexer nele seria mexer no que os 248 veem.
# ⚠️ Sem os comentarios. A 1a versao desta guarda ficou vermelha por causa do
# comentario que EXPLICA a morte do ✦ — e tinha razao em nao saber ler prosa.
# Tirar os comentarios torna-a mais afiada (passa a falar de markup), nao mais
# mole: sabotar o JSX continua a po-la vermelha, e foi provado.
_ON_BRANCH = _strip_js_comments(
    _DETAIL[_DETAIL.index("{itemOn ? ("):_DETAIL.index("            ) : (")])
chk(_AI_GLYPH not in _ON_BRANCH,
    "foto: o ✦ de \"equipado\" nao sobrevive no ramo novo — quem o diz e' o selo")
chk(_AI_GLYPH in _DETAIL,
    "foto: ...e CONTINUA no ramo desligado (a OFF-identidade nao se \"melhora\")")

# ── 12b. OS TRES PATAMARES: tres, e derivados da ESCALA ───────────────────
_ORN = _obj_after(_UIM, "var NIV_TIER_ORN = ")
_TIERS = re.findall(r"^      ([a-z]+):", _ORN, re.M)
chk(_TIERS == ["common", "notable", "celestial"],
    "patamar: TRES patamares, nesta ordem (%r) — nove nunca parecem um conjunto "
    "(Lei §3)" % (_TIERS,))
chk(re.search(r"common:\s*null", _ORN) is not None,
    "patamar: `common` e' `null` — o patamar de baixo NAO tem ramo proprio, "
    "logo desenha os literais de 05/09 e nao uma copia deles")

# ⚠️ A GUARDA QUE IMPEDE O CODIGO DE CORES DE VOLTAR PELA PORTA LATERAL.
# A decisao de 05/09 ("a raridade e' MEDIDA, nao cor") morre em silencio se o
# ornamento passar a pintar por GRAU: seriam nove aparencias outra vez, e
# ninguem teria reaberto nada. O ornamento so' pode falar em ouro — a cor do
# grau ja' entra na carta pelo `accent` (a tinta do verso) e para' aí.
chk("GRADE_VISUALS" not in _ORN,
    "patamar: o ornamento NAO le a paleta por grau (o codigo de cores nao volta)")
chk(re.search(r"--realm-", _ORN) is None,
    "patamar: o ornamento nao usa cor de reino — so' a escada de ouro")
_ORN_VARS = set(re.findall(r"var\(--([a-z0-9-]+)\)", _ORN))
chk(_ORN_VARS <= {"gold-rgb", "gold2-rgb", "gold3-rgb"},
    "patamar: as unicas cores do ornamento sao os tres ouros (%r)" % (sorted(_ORN_VARS),))

# O patamar sai da POSICAO na escala, nunca de uma lista de nomes. Uma lista
# fixa envelhece em silencio: a licao de 07/09 (a guarda dos `*Classic` cobria
# 3 de 5 e ficou verde) e a de 06/09 (a escala do artefacto tinha NOVE degraus
# e o prompt dizia quatro). Se alguem trocar a conta por um `indexOf`, vermelho.
_TIERFN = _UIM[_UIM.index("function nivTier("):_UIM.index("// A arte servida pelo jogo.")]
chk("rank.i / (rank.n - 1)" in _TIERFN,
    "patamar: o patamar DERIVA de i/(n-1) — a posicao na escala daquele conteudo")
# ⚠️ `celestial` NAO entra nesta lista: e' o nome do PATAMAR (o valor que
# `nivTier` devolve), nao o de uma raridade. A 1a versao desta guarda proibia-o
# e ficou vermelha contra o codigo certo — proibir a palavra errada e' tao mau
# como nao proibir nenhuma.
for _bad_name in ("divine", "legendary", "transcendent", "perfected", "mythic",
                  "GRADE_ORDER", "indexOf"):
    chk(_bad_name not in _TIERFN,
        "patamar: `nivTier` nao conhece %r — deriva, nunca consulta uma lista"
        % _bad_name)

# ⚠️ E TEM DE VIVER DENTRO DA FATIA QUE O HARNESS DE NODE LE. O
# `_test_carta_rank.js` corta o `ui.js` entre `var NIV_RANK_SCALES = {` e
# `// A arte servida pelo jogo.`; fora dessa fatia o `nivTier` continuava a
# existir e deixava de ser EXECUTADO por ninguem — uma guarda verde a cobrir
# codigo que ela nao corre.
_SLICE = _UIM[_UIM.index("var NIV_RANK_SCALES = {"):_UIM.index("// A arte servida pelo jogo.")]
chk("function nivTier(" in _SLICE and "var NIV_TIER_CUTS" in _SLICE,
    "patamar: `nivTier` e os cortes vivem na fatia que o harness de node CORRE")

# ── 12c. A REGUA NOVA DESTE LOTE, contra os DADOS SEEDADOS ────────────────
#
# *"Se tudo ficar bonito, o topo deixou de ser topo?"* — e a resposta so' se
# obtem contando os SEEDS, nunca lendo o motor. Foi a comparacao com os dados
# (e nao com o motor, que concordava) que matou a escala de 4 do artefacto a
# 06/09 e o `difficulty` da pilula a 05/09. Os cortes sao lidos do proprio
# `ui.js`: baixa-los para inundar a mochila de celestes poe isto vermelho.
_cuts = dict((k, float(v)) for k, v in re.findall(
    r"(celestial|notable):\s*(\.\d+)", _obj_after(_UIM, "var NIV_TIER_CUTS = ")))
chk(set(_cuts) == {"celestial", "notable"} and _cuts["celestial"] > _cuts["notable"],
    "regua: os dois cortes existem e estao pela ordem certa (%r)" % (_cuts,))


def _tier_of(i, n):
    if n <= 1:
        return "common"
    p = float(i) / (n - 1)
    if p >= _cuts["celestial"]:
        return "celestial"
    if p >= _cuts["notable"]:
        return "notable"
    return "common"


_SEED_FAMILIES = (
    # (nome, ficheiro, regex do posto, n de degraus, indice a partir do valor)
    ("artefacto", "database/seeds/artifacts_seeds.py",
     r'"grade"\s*:\s*(\d+)', 9, lambda v: int(v)),
    ("pilula", "database/seeds/alchemy_seeds.py",
     r'"required_alchemy_tier"\s*:\s*(\d+)', 5, lambda v: int(v) - 1),
    ("besta", "database/seeds/beasts_seeds.py",
     r'"rank"\s*:\s*"([A-Za-z]+)"', 7,
     lambda v: ["common", "uncommon", "rare", "epic",
                "legendary", "mythic", "divine"].index(v.lower())),
)
for _fam, _path, _pat, _n, _idx in _SEED_FAMILIES:
    _vals = re.findall(_pat, rd(_path))
    _tot = len(_vals)
    _cnt = {"common": 0, "notable": 0, "celestial": 0}
    for _v in _vals:
        _cnt[_tier_of(_idx(_v), _n)] += 1
    chk(_tot >= 15, "regua: %s tem %d pecas seedadas para contar" % (_fam, _tot))
    if _tot:
        _pc = 100.0 * _cnt["celestial"] / _tot
        _pm = 100.0 * _cnt["common"] / _tot
        chk(_pc <= 20.0,
            "regua: %s — celeste em %.0f%% das pecas (<=20%%): o topo continua "
            "a ser topo" % (_fam, _pc))
        chk(_pm >= 50.0,
            "regua: %s — comum em %.0f%% das pecas (>=50%%): se tudo brilha, "
            "nada brilha" % (_fam, _pm))

# ── 12d. A flag: nasce OFF, auto-documenta-se, e nao traz migration ───────
chk(re.search(r'"item_vivo":\s*False', _feat) is not None,
    "flag: `item_vivo` nasce OFF em DEFAULT_WORLD_FEATURES (o `main` le' defaults)")
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    chk("feature_item_vivo" in _d and len(_d["feature_item_vivo"]) > 6,
        "flag: rotulo no painel do owner em %s" % _lang)
    chk("feature_item_vivo_desc" in _d and len(_d["feature_item_vivo_desc"]) > 400,
        "flag: descricao auto-documentada em %s" % _lang)

# ⚠️ Pelo ASSUNTO e por SEGMENTO do nome — a lição dupla de 07-08/09 (um assert
# sobre "a migration mais recente" pos 7 suites vermelhas; e `mark` como
# sub-cadeia apanhou `044_market_unit_price.sql`).
_meu2 = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
         if re.search(r"(?:^|_)(item_vivo|patamar|patamares|ornamento|posto_visivel)(?:_|\.)",
                      m, re.I)]
chk(not _meu2,
    "nenhuma migration fala do item vivo — o lote e' re-render puro (%r)" % (_meu2,))

# ── 12e. A OFF-identidade, no unico sitio onde ela se pode afirmar em fonte ─
#
# ⚠️ Toda propriedade de estilo NOVA tem de estar DENTRO do ternario. A 08/09
# custou tres consertos: `display: on ? "grid" : undefined, placeItems:"center"`
# deixa o `placeItems` nos DOIS ramos e ja' e' um DOM diferente. As tres chaves
# novas da carta sao `boxShadow` (a moldura), `dissolve` e `tier` (props).
_CARD = _fn_src(_UIM, "function NivraelCard(")
for _prop in ("boxShadow", "dissolve", "tier"):
    _hits = re.findall(r"[^\n]*\b%s\b[^\n]*" % _prop, _CARD)
    chk(_hits and all(("orn ?" in h) or ("orn &&" in h) or ("(orn" in h) for h in _hits),
        "OFF-identidade: `%s` so' aparece dentro do ternario do ornamento (%d usos)"
        % (_prop, len(_hits)))
chk("const orn = (!isGhost && itemVivoOn())" in _CARD,
    "OFF-identidade: o ornamento e' `null` com a flag desligada, num sitio SO'")

# ⚠️ E a rampa por omissao do `CardArt` tem de ser uma STRING LITERAL, nunca uma
# conta: `42 + (100-42)*.55` da' **73.9**, nao 74, e uma casa decimal a mais no
# atributo `style` ja' e' um DOM diferente.
_ARTFN = _fn_src(_UIM, "function CardArt(")
chk("transparent 42%," in _ARTFN and 'rgba(var(--card-rgb),.5) 74%' in _ARTFN,
    "OFF-identidade: a rampa por omissao do verso e' a string literal de 05/09")
chk("dissolve == null" in _ARTFN,
    "OFF-identidade: e' `dissolve == null` que escolhe o ramo literal")

# `PieceHero` sem `bleed`/`radius` tem de dar o markup de 08/09 (o modal da
# BESTA nao pode mexer-se por causa deste lote).
_PH = _fn_src(_UIM, "function PieceHero(")
chk("bleed == null ? 14 : bleed" in _PH,
    "OFF-identidade: sem `bleed` o PieceHero mantem os -14px da besta")
chk("...(radius ? { borderRadius: radius } : {})" in _PH,
    "OFF-identidade: sem `radius` nao nasce chave `borderRadius` nenhuma")

# ── 12f. O comentario que MENTIA por antiguidade ──────────────────────────
# Dizia que o jogador lia tipo e raridade "sem art assets" — verdade com ZERO
# pecas, falso com 235. Um comentario desactualizado e' uma decisao velha a
# continuar a mandar.
_SLOTC = _TBM[_TBM.index("var SLOT_ICONS =") - 1400:_TBM.index("var SLOT_ICONS =")]
chk("without art assets" not in _SLOTC,
    "comentario: o `SLOT_ICONS` deixou de dizer \"sem art assets\" (ha' 235 pecas)")
chk("235" in _SLOTC and "verso honesto" in _SLOTC,
    "comentario: ...e diz o que o icone do slot passou a ser — o verso honesto")

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 13. F-7 O MANIFESTO: toda tela que mostra uma PECA pede a arte ===")
#
# ⚠️ ISTO E' O DENTE DA LEI F-7 (`DESIGN_DECISIONS_v14.md §5`), escrita por
# ordem do owner a 2026-09-08:
#   *"Anotar isso como lei que sempre funcione em tudo. sempre ter isso pendente
#    e qualquer alteracao checar e fazer funcional. Atencao nisso pra nao ter
#    trabalho dobrado."*
#
# O report que a originou: *"imagens nao aparecem de espadas algumas vezes sim e
# outras nao ainda usam icones do propio emoji"*. E ele tinha razao: as quatro
# familias estao COMPLETAS no indice (artefacto 51/51 · pilula 41/41 · besta
# 15/15 · tecnica 128) e mesmo assim so' **12 pontos** do cliente pediam
# `pieceArt(...)`. O resto desenhava `<div style={{fontSize:38}}>{a.emoji}</div>`
# a' mao — porque nunca existiu um componente que respondesse "mostra-me esta
# peca". A inconsistencia e' pior do que a ausencia.
#
# COMO A GUARDA FUNCIONA (e porque nao e' uma lista que envelhece em silencio):
#   (a) varre o cliente a' procura de RETRATOS — um emoji a >=18px que e' a cara
#       de alguma coisa (`{x.emoji}` ou `slotIco(...)` logo a seguir);
#   (b) exige que CADA UM esteja no manifesto abaixo, com estado;
#   (c) exige que os marcados `arte` REALMENTE peçam a arte na sua funcao.
# ⇒ Uma tela NOVA que desenhe o retrato de uma peca parte a suite ate' alguem
#   decidir, de propósito, em que estado ela fica. E' o "sempre ter isso
#   pendente" do owner, feito mecanica.
#
# "pendente" e' um estado LEGITIMO — a familia ainda nao tem arte gerada
# (ARTE_PROVENIENCIA §2.5: faltam 14 ervas · 6 minerios · 10 formacoes ·
# 23 masmorras · 9 chefes · 9 brasoes · 35 conquistas). O que a lei proibe e' a
# tela que PODIA mostrar e nao mostra.
_FACE_MANIFEST = {
    # ── as quatro familias COM arte: tem de pedir ────────────────────────
    "ArtifactCell":            "arte",
    "DetailModal":             "arte",
    "ProfileCardBody":         "arte",
    "EquipSlotPickerModal":    "arte",
    "ArtifactWorkshopModal":   "arte",
    "RefineConfirmModal":      "arte",
    "EnchantPickerModal":      "arte",
    "ForgeResultModal":        "arte",
    "ItemCell":                "arte",
    "RecipeCard":              "arte",
    "RecipeDetailModal":       "arte",
    "AlchemyPanel":            "arte",
    "HeavenlyTribulationModal": "arte",
    "BeastsListPanel":         "arte",
    "BeastsCapturePanel":      "arte",
    "BeastsCompanionPanel":    "arte",
    "BeastDetailModal":        "arte",
    "BeastEvolveModal":        "arte",
    "EquippedRow":             "arte",
    "LearnedRow":              "arte",
    "LearnableRow":            "arte",
    # ── os ramos *Classic: sao a OFF-identidade, e nao se tocam ──────────
    "ArtifactCellClassic":     "off-identity: o markup dos 248, byte a byte",
    "ItemCellClassic":         "off-identity",
    "RecipeCardClassic":       "off-identity",
    "EquippedRowClassic":      "off-identity",
    "LearnedRowClassic":       "off-identity",
    # ── familias SEM arte gerada (ARTE_PROVENIENCIA §2.5) ────────────────
    "ForgeRecipeDetailModal":  "pendente: minerios (6) sem arte",
    "ForgeOreStrip":           "pendente: minerios (6) sem arte",
    "ForgeRecipeCard":         "pendente: minerios (6) sem arte",
    "CauldronPickerModal":     "pendente: caldeiroes sem arte",
    "CauldronRepairModal":     "pendente: caldeiroes sem arte",
    "CauldronUpgradeModal":    "pendente: caldeiroes sem arte",
    "DungeonCard":             "pendente: 23 masmorras sem arte",
    "DungeonEntryModal":       "pendente: 23 masmorras sem arte",
    "DungeonRunCard":          "pendente: 23 masmorras sem arte",
    "DungeonQuestsModal":      "pendente: 23 masmorras sem arte",
    "ExploreTab":              "pendente: 23 masmorras sem arte",
    "DropsPreview":            "pendente: espolio misto",
    "WorldBossTab":            "pendente: 9 chefes sem arte",
    "BossRankingsModal":       "pendente: 9 chefes sem arte",
    "AchievementsModal":       "pendente: 35 conquistas sem arte",
    "WorldSectDirectoryModal": "pendente: 9 brasoes de seita sem arte",
    "BeastExpeditionModal":    "pendente: expedicoes nao sao pecas",
    "BeastCaptureOutcomeModal": "pendente: espolio misto",
    "FactionShopPanel":        "pendente: catalogo misto",
    "FactionPickPanel":        "nao-peca: faccao e' um lugar, nao um objecto",
    "FactionAvailableQuestCard": "nao-peca: quest",
    "FactionDashboardPanel":   "nao-peca: quest",
    "PrestigeShopModal":       "pendente: catalogo misto",
    "ShopFragmentsSection":    "pendente: catalogo misto",
    "SectShopPanel":           "pendente: catalogo misto",
    # ── nao sao pecas: sao lugares, estados, caminhos, pessoas ───────────
    "FoundationTrialModal":    "nao-peca: rito",
    "CoreFormationModal":      "nao-peca: rito",
    "BodyTemperingTab":        "nao-peca: estado do corpo",
    # 星 2.1 — o ramo de sempre do Corpo passou a ter nome proprio quando a
    # figura que acende nasceu; e' a OFF-identidade, como os outros *Classic.
    "BodyTemperingClassic":    "off-identity: o Corpo de sempre, byte a byte",
    "RebirthModal":            "nao-peca: rito",
    "ContinentModal":          "nao-peca: lugar",
    "LineageChooserModal":     "nao-peca: linhagem",
    "LineageInfoModal":        "nao-peca: linhagem",
    "_PathCardBody":           "nao-peca: caminho",
    "PathModal":               "nao-peca: caminho",
    "KarmaModal":              "nao-peca: estado",
    "QuestRow":                "nao-peca: quest",
    "StoryletSection":         "nao-peca: quest",
    "IntentModal":             "nao-peca: intencao de combate",
    "TechIntentBlock":         "nao-peca: intencao de combate",
    "ScrollEconomyCard":       "nao-peca: estado da economia",
    "CelTrialRow":             "nao-peca: rito",
    "EventsModal":             "nao-peca: evento",
    "TravelModal":             "nao-peca: lugar",
    "CavernTab":               "nao-peca: lugar",
    "TutorialModal":           "nao-peca: ensino",
    "HubMundoScreen":          "nao-peca: lugar",
    "HubCavernaScreen":        "nao-peca: lugar",
    "HubPergaminhoScreen":     "nao-peca: seccao",
    "DaoSupremeView":          "nao-peca: lei do Dao",
    "DaoDiscoveriesView":      "nao-peca: lei do Dao",
    "InventoryTab":            "nao-peca: silhueta do slot VAZIO",
}

_tlines = _TBM.split("\n")
_tfns = [(i, m.group(1)) for i, l in enumerate(_tlines)
         for m in [re.match(r"    function (\w+)", l)] if m]


def _owner_fn(n):
    prev = None
    for i, nm in _tfns:
        if i > n:
            break
        prev = nm
    return prev


# (a) achar todos os RETRATOS
_portraits = {}
for _i, _l in enumerate(_tlines):
    _m = re.search(r"fontSize:\s*(\d{2,})", _l)
    if not _m or int(_m.group(1)) < 18:
        continue
    if not re.search(r"\{\s*(?:\w+\.emoji|slotIco\()", "\n".join(_tlines[_i:_i + 3])):
        continue
    _portraits.setdefault(_owner_fn(_i), []).append(_i + 1)

# (b) todo retrato TEM de estar no manifesto
_orfas = sorted(f for f in _portraits if f not in _FACE_MANIFEST)
chk(not _orfas,
    "F-7: nenhuma tela desenha o retrato de uma peca fora do manifesto (%r)"
    % (_orfas,))

# ⚠️ e o inverso: uma entrada de manifesto sem tela e' lixo que engana o
# planeamento (a licao do `crate`, a marca desenhada e apagada no mesmo lote).
# ⚠️ ...e o inverso: uma entrada do manifesto que nao existe no cliente e' lixo
# que engana o planeamento (a licao do `crate`, a marca desenhada e apagada no
# mesmo lote). Aqui o criterio e' duro: a FUNCAO tem de existir.
_inexistentes = sorted(f for f in _FACE_MANIFEST
                       if ("    function %s(" % f) not in _TBM)
chk(not _inexistentes,
    "F-7: o manifesto nao nomeia telas que nao existem (%r)" % (_inexistentes,))

# (c) o que esta' marcado `arte` TEM de pedir a arte
_sem_arte = []
for _fn, _estado in sorted(_FACE_MANIFEST.items()):
    if _estado != "arte":
        continue
    _needle = "    function %s(" % _fn
    if _needle not in _TBM:
        _sem_arte.append(_fn + " (funcao inexistente)")
        continue
    _body = _fn_src(_TBM, _needle)
    if "pieceArt(" not in _body and "<PieceIcon" not in _body and "<PieceHero" not in _body:
        _sem_arte.append(_fn)
chk(not _sem_arte,
    "F-7: TODA tela marcada `arte` pede mesmo a arte (%d telas; falham: %r)"
    % (sum(1 for v in _FACE_MANIFEST.values() if v == "arte"), _sem_arte))

# ⚠️ UM dono para a face de uma peca — a causa-raiz das tres recorrencias foi
# nunca ter havido nenhum. Se nascer um segundo, a divergencia volta.
# ⚠️ A 1a versao desta guarda procurava `(PieceIcon|PieceHero|CardArt)` — isto
# e', so' reconhecia os nomes CERTOS, e ficou VERDE quando lhe meti um
# `PieceThumb` ao lado. E' letra por letra a licao de 08/09 ("uma guarda que so'
# reconhece os nomes bem escritos nao guarda nada"). Agora sao duas regras
# ESTRUTURAIS, e a segunda nao depende de nome nenhum:
#   (A) por convencao: uma funcao chamada `Piece*` so' pode ser uma das duas;
#   (B) por estrutura: so' o `CardArt` pode desenhar a arte de uma peca — quem
#       quer que renderize `<img` a partir de `pieceArt(...)` esta' a fazer uma
#       segunda chapa, e e' assim que o verso honesto/`onError`/`lazy` divergem.
_PIECE_NAMED = sorted(set(re.findall(r"function\s+(Piece\w*)\s*\(", _UIM + _TBM)))
chk(_PIECE_NAMED == ["PieceHero", "PieceIcon"],
    "F-7 (A): so' existem duas funcoes `Piece*` — a chapa grande e a pequena (%r)"
    % (_PIECE_NAMED,))

_FACE_DEFS = re.findall(r"function\s+(CardArt)\s*\(", _UIM + _TBM)
chk(_FACE_DEFS == ["CardArt"],
    "F-7: ha' UMA chapa honesta em todo o cliente (%r)" % (_FACE_DEFS,))

# (B) — quem desenha `<img` de arte de peca? So' o `CardArt`.
_ulines = (_UIM + chr(10) + _TBM).split(chr(10))
_ufns = [(i, m.group(1)) for i, l in enumerate(_ulines)
         for m in [re.match(r"    function (\w+)", l)] if m]


def _owner_any(n):
    prev = None
    for i, nm in _ufns:
        if i > n:
            break
        prev = nm
    return prev


# ⚠️ SEM filtro nenhum: o cliente inteiro tem TRES `<img`, portanto nao ha' o
# que filtrar. A 1a versao desta guarda peneirava o atributo `src` com um regex
# — e o regex tinha um `\b` escrito atraves de uma string NAO-raw, que em
# Python e' o caractere de BACKSPACE (0x08), nao uma fronteira de palavra. O
# padrao nunca casava, o conjunto ficava VAZIO, e `set() <= {"CardArt"}` e'
# verdade — a guarda passava sem nunca ter olhado para nada. E' a mesma familia
# da licao de 06/09 (comparar com o motor e nao com os dados): uma guarda que
# pode ficar verde sobre o conjunto vazio nao guarda.
_img_owners = set(_owner_any(_i) for _i, _l in enumerate(_ulines) if "<img" in _l)
chk(len(_img_owners) == 5,
    "F-7 (B): o cliente inteiro tem 5 renderizadores de imagem — o conjunto "
    "NAO e' vazio (%d)" % len(_img_owners))
# Os TRES renderizadores de imagem do cliente, cada um com o seu papel:
#   CardArt          — a face de uma PECA (com verso honesto, onError, lazy)
#   CultivatorFigure — a figura sentada da cena do Cultivo (07/09)
#   RealmBackdrop    — o reino por tras dela (07/09)
# Os dois ultimos NAO sao pecas: nao tem posto, nao tem lombo, nao passam por
# `pieceArt`. O valor desta guarda esta' em ficar vermelha quando nascer um
# QUARTO — foi assim que o verso honesto se duplicou tres vezes nesta casa.
#   HubScene         — 圖 a cena de um hub e as suas portas (2026-09-11). E' o
#                      QUARTO, e entrou por decisao escrita: tambem nao e' uma
#                      peca (nao tem posto, nao tem lombo, nao passa por
#                      `pieceArt`) e tem o seu proprio recurso — a chapa de
#                      pedra por baixo de cada porta, que mantem o botao
#                      tocavel quando a arte falha (Lei §1).
# ⚠️ Esta guarda ficou VERMELHA quando o `HubScene` nasceu, que e' exactamente o
# que ela existe para fazer. Alargar a lista e' legitimo; baixa-la para
# `>= 3` nao seria — era transformar uma guarda que conta numa que nao conta.
#   SceneDoor        — 門 a porta pintada (2026-09-15). E' o QUINTO, e entrou
#                      por uma razao de DONO UNICO e nao por gosto: a V7 poe as
#                      mesmas portas DENTRO do continente, e desenha-las la' com
#                      codigo proprio era a segunda ligacao a' mao que a Lei F-7
#                      §2 proibe. Saiu de dentro do `HubScene` — o numero subiu,
#                      mas o numero de IMPLEMENTACOES da porta desceu de duas
#                      (uma escrita, uma por escrever) para UMA.
_IMG_OWNERS_OK = {"CardArt", "CultivatorFigure", "RealmBackdrop", "HubScene",
                  "SceneDoor"}
chk(_img_owners == _IMG_OWNERS_OK,
    "F-7 (B): os renderizadores de imagem sao os cinco conhecidos — a peca so' "
    "pelo `CardArt` (%r)" % (sorted(_img_owners),))
chk("<CardArt" in _fn_src(_UIM, "function PieceIcon("),
    "F-7: o `PieceIcon` reusa a chapa honesta, nao faz uma segunda")
chk("<CardArt" in _fn_src(_UIM, "function PieceHero("),
    "F-7: o `PieceHero` reusa a chapa honesta, nao faz uma segunda")

# ⚠️ A cobertura MEDIDA — e' o numero que o owner leu na tela. Se alguem
# desligar telas, isto desce e a suite diz.
_n_arte = sum(1 for v in _FACE_MANIFEST.values() if v == "arte")
chk(_n_arte >= 21,
    "F-7: %d telas de peca servem a arte (eram 6 antes deste lote)" % _n_arte)

# ⚠️ E as quatro familias com arte estao COMPLETAS — a guarda contra os DADOS,
# nao contra o motor. Se alguem semear uma peca nova sem gerar a arte dela, a
# familia deixa de estar completa e isto fica vermelho no mesmo commit.
_ART_IDX = set(re.findall(r'"([a-z0-9-]+)"',
                          _obj_after(_UIM, "var NIV_ART_INDEX = new Set(")))


def _slug(n):
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", n.lower()))


def _dict_blocks(src):
    r"""Cada literal `{...}` de topo do seed, com as chaves ANINHADAS incluidas.

    ⚠️ Um `re.findall(r"\{[^{}]*\}")` nao serve e ficou VERMELHO a' primeira:
    toda entrada de artefacto tem um `base_stats: {...}` la' dentro, portanto o
    regex nao-aninhado casava so' o interior e a contagem dava **0 de 0** — uma
    guarda a dizer "verde" sobre um conjunto vazio. Contar exige contar a serio.
    """
    out, i = [], 0
    while True:
        j = src.find("{", i)
        if j < 0:
            return out
        d, k = 0, j
        while k < len(src):
            if src[k] == "{":
                d += 1
            elif src[k] == "}":
                d -= 1
                if d == 0:
                    out.append(src[j:k + 1])
                    break
            k += 1
        else:
            return out
        i = k + 1


for _fam, _pre, _seed, _key in (
        ("artefacto", "art", "database/seeds/artifacts_seeds.py", r'"grade"'),
        ("besta", "beast", "database/seeds/beasts_seeds.py", r'"rank"')):
    # so' as entradas que TEM o campo que as torna aquela familia
    _blocks = [b for b in _dict_blocks(rd(_seed)) if re.search(_key, b)]
    _nomes = [m.group(1) for b in _blocks
              for m in [re.search(r'"name"\s*:\s*"([^"]+)"', b)] if m]
    _falta = [n for n in _nomes if _pre + "-" + _slug(n) not in _ART_IDX]
    chk(_nomes and not _falta,
        "F-7: %s — %d/%d com arte no indice (sem: %r)"
        % (_fam, len(_nomes) - len(_falta), len(_nomes), _falta[:4]))

# ── 9. 品 o comportamento, a serio: nivRank corrido sob node ──────────────
if node:
    _r = subprocess.run([node, os.path.join(ROOT, "scripts", "_test_carta_rank.js")],
                        capture_output=True, text=True)
    _lines = [l for l in (_r.stdout or "").rstrip().split("\n") if l.strip()]
    print("   (%d asserts do lombo sob node)" % len(_lines))
    for _l in _lines:
        if _l.startswith("FAIL"):
            print("   " + _l)
    chk(_r.returncode == 0,
        "⚠️ lombo: nivRank REAL conta bem 5/7/5 e devolve null no desconhecido")
else:
    chk(True, "node ausente: fica o contrato de fonte acima")


# ══════════════════════════════════════════════════════════════════════════
# 14. 窗 A JANELA — o dono unico de "sobrepor uma coisa ao jogo"
# ══════════════════════════════════════════════════════════════════════════
#
# Nasceu de um relato do owner (2026-09-08, do telemovel dele): *"quando abro o
# item no telefone nao posso fechar a janela. cobre tudo e nao deixa o X."*
#
# A causa estava escrita no proprio repo desde **2026-05-10**, no comentario do
# `Modal`: no WebView do iOS um `position:fixed` DENTRO da `.scroll-area` ancora
# ao contentor que rola e nao ao ecra, e o topo (com o X) esconde-se atras do
# PlayerHeader. O `Modal` foi consertado com um PORTAL nessa altura. Os modais
# escritos a mao nunca foram. Lei F-7 na letra: a correccao teve UM dono e o
# problema tinha TRES.
print("\n=== 14. A JANELA: portal, rolagem e o X que nao foge ===")

_OVL = _fn_src(_UIM, "function Overlay(")

_OVL_DEFS = re.findall(r"function\s+(Overlay)\s*\(", _UIM + _TBM)
chk(_OVL_DEFS == ["Overlay"],
    "janela: existe UMA definicao de `Overlay` em todo o cliente (%r)" % (_OVL_DEFS,))

chk("ReactDOM.createPortal" in _OVL,
    "janela: o `Overlay` faz PORTAL para o body — sem isto volta o bug do iOS "
    "que escondia o X atras do PlayerHeader")
chk("useBodyScrollLock" in _OVL,
    "janela: o `Overlay` trava a rolagem do fundo (o mesmo que o `Modal` faz)")
# ⚠️ SOBRE O FUNDO, e nao "algures no ficheiro". A 1a versao dizia so'
# `'overflowY:"auto"' in _OVL` e ficou VERDE quando lho tirei do fundo — porque
# o CORPO tambem o tem. Uma guarda que aceita a ocorrencia errada nao guarda o
# que diz guardar. O fundo e' o texto ate' ao cartao.
_OVL_BACKDROP = _OVL[_OVL.index('position:"fixed"'):_OVL.index("onClick={(e) => e.stopPropagation()}")]
chk('overflowY:"auto"' in _OVL_BACKDROP,
    "janela: o FUNDO do `Overlay` rola — sem isto o que sai do ecra fica "
    "inalcancavel (medido: `scrollHeight === clientHeight` no modal antigo)")

# ⚠️ A guarda do CENTRAMENTO. `place-items:center` numa peca mais alta que o pai
# corta as DUAS pontas e leva o X para fora do ecra sem deixar maneira de la
# chegar — foi metade do defeito de 08/09. `margin:auto` centra e NUNCA corta.
chk('margin:"auto"' in _OVL,
    "janela: o cartao centra-se com `margin:auto` — o unico centramento que nao "
    "corta o topo quando o conteudo e' mais alto que o ecra")
chk("placeItems" not in _OVL,
    "janela: ...e NAO com `placeItems`, que e' precisamente o que cortava")

# ⚠️ A guarda do COLAPSO, e esta so' se descobriu a OLHAR. `flex:"1 1 0"` (o que
# o `Modal` usa) exige que o pai tenha altura DEFINIDA; aqui o cartao tem so'
# `maxHeight`, e com base 0 o corpo colapsa para 0px: o modal abriu com 36px e
# NADA dentro, so' o X. Um teste de alcance teria dito "o X esta' alcancavel" e
# estaria certo — sobre uma janela vazia.
chk('flex:"0 1 auto"' in _OVL,
    "janela: o corpo limitado usa `flex:0 1 auto` — com `1 1 0` colapsa a 0px "
    "(visto a olho: 36px de modal, so' o X)")
# ⚠️ Sobre o MARKUP, nao sobre a prosa: o comentario acima EXPLICA o `1 1 0`
# e por isso a 1a versao desta guarda ficou vermelha a ler a sua propria
# explicacao. (2a vez neste ficheiro — a mesma correccao do ✦ em §12.)
chk('flex:"1 1 0"' not in _strip_js_comments(_OVL),
    "janela: ...e nunca `1 1 0`, que so' funciona com altura definida no pai")

# O X vai em `pinned`, FORA do corpo que rola — senao desaparece com a rolagem.
# ⚠️ Nao usar `.index` cru: apagar o `{pinned}` fazia a suite REBENTAR com um
# ValueError em vez de ficar vermelha. Uma guarda que estoira nao diz o que
# esta' errado — diz que o ficheiro do teste esta' errado.
_i_pin = _OVL.find("{pinned}")
_i_body = _OVL.find('className={"scroll-area"')
chk(_i_pin >= 0 and _i_body >= 0 and _i_pin < _i_body,
    "janela: o que e' `pinned` (o X) e' irmao do corpo que rola e vem ANTES "
    "dele — nunca la' dentro, senao rola para fora de vista")

# ── A GUARDA QUE CONTA (F-7) ──────────────────────────────────────────────
# Uma 9a janela escrita a mao parte esta suite. Legitimo: `Modal`, `Overlay`,
# `ErrBanner`, e as CINEMATICAS (`pointerEvents:"none"` — nao sao janelas: nao
# tem X, nao tem conteudo para rolar, duram um segundo). Tudo o resto e' uma
# janela sem dono.
_OVERLAY_RE = re.compile(r'position:\s*"fixed"[^}]*?inset:\s*0', re.S)


def _hand_rolled_windows(src):
    out = []
    for m in _OVERLAY_RE.finditer(src):
        seg = src[m.start():m.start() + 900]
        if 'pointerEvents:"none"' in seg[:400]:
            continue  # cinematica: nao e' uma janela
        out.append(src[:m.start()].count("\n") + 1)
    return out


_HAND = _hand_rolled_windows(_TBM)
chk(_HAND == [],
    "janela F-7: ZERO janelas interactivas escritas a mao em tabs.js — todas "
    "passam pelo `Modal` ou pelo `Overlay` (linhas encontradas: %r)" % (_HAND,))

# ⚠️ Prova de que a guarda MORDE: as cinematicas TEM de continuar visiveis ao
# regex, senao a guarda acima esta' verde por nao encontrar NADA — que e' a
# licao de 08/09 (`set() <= {...}` e' verdade).
_ALL_FIXED = len(_OVERLAY_RE.findall(_TBM))
chk(_ALL_FIXED >= 6,
    "janela: o regex ainda ve os %d `position:fixed;inset:0` de tabs.js — uma "
    "guarda verde sobre o conjunto VAZIO nao guarda" % _ALL_FIXED)

# As duas que foram convertidas, nomeadas.
chk("<Overlay" in _DETAIL and 'position:"fixed"' not in _DETAIL,
    "janela: o `DetailModal` (o que o owner nao conseguia fechar) passa pelo "
    "`Overlay` e ja' nao declara `position:fixed`")
_PICKER = _fn_src(_TBM, "function EquipSlotPickerModal(")
chk("<Overlay" in _PICKER and 'position:"fixed"' not in _PICKER,
    "janela: o `EquipSlotPickerModal` — a segunda janela sem dono — tambem")
# ⚠️ Sem comentarios: a explicacao aqui em cima diz "bounded" e deixava a
# guarda verde depois de eu APAGAR a prop. (3a vez neste ficheiro.)
chk("bounded" in _strip_js_comments(_DETAIL),
    "janela: o `DetailModal` e' `bounded` (altura limitada + corpo que rola) — "
    "era o que tinha conteudo a mais para o ecra")

# ── O NUMERO PARTIDO (fotografado pelo owner na MESMA tela) ───────────────
# "Poder de Combate +12000" imprimia-se `+1200` / `0` em duas linhas. Um numero
# partido nao e' feio: e' FALSO — le-se mil e duzentos.
# ⚠️ Sobre a CELULA DO VALOR. A 1a versao perguntava se `nowrap` aparecia
# algures na funcao — e ficou verde depois de eu o tirar do numero, porque o
# ROTULO ao lado tambem o tem. O que se mede e' o elemento que imprime o valor:
# o `+{...}` e o que o embrulha.
def _value_cell(src):
    """O markup desde o rotulo `humanizeStat(k)` ate' ao fim da linha do valor."""
    i = src.index("humanizeStat(k)}</span>")
    return _strip_js_comments(src[i:i + 700])


for _lbl, _src in (("modal de detalhe", _DETAIL),
                   ("receita da forja",
                    _fn_src(_TBM, "function ForgeRecipeDetailModal("))):
    _cell = _value_cell(_src)
    chk('whiteSpace:"nowrap"' in _cell,
        "numero: no %s o VALOR e' `nowrap` — um numero partido em duas linhas "
        "nao e' feio, e' FALSO (`+12000` lia-se `+1200`)" % _lbl)
    # ⚠️ o estilo DO ROTULO, e nao "ha' um minWidth:0 algures na funcao" — que
    # e' o que a 1a versao perguntava, e ficava verde depois de eu o apagar
    # (o `DetailModal` tem outros `minWidth:0` sem relacao nenhuma com isto).
    _m_lbl = re.search(r"<span style=\{\{([^}]*)\}\}>\{humanizeStat\(k\)\}</span>",
                       _strip_js_comments(_src), re.S)
    chk(_m_lbl is not None and "minWidth:0" in _m_lbl.group(1),
        "numero: ...e o ROTULO do %s tem `minWidth:0`, senao e' ele que estica "
        "a coluna e o valor continua a quebrar" % _lbl)


# ══════════════════════════════════════════════════════════════════════════
# 15. 印 A CATRACA DO EMOJI — o numero so' pode DESCER
# ══════════════════════════════════════════════════════════════════════════
#
# Ordem do owner, 2026-09-09 (textual): *"Usando minha conta normal ou antiga
# ainda sai icones antigos etc. Precisamos remover isso. Tudo tem que ser novo,
# NAO QUERO falhas. (…) Cada nova imagem cada novo item cada nova funcao cada
# nova aba. sempre garantizar o funcionamento perfeito de cada sistema pros
# jogadores."*
#
# ⚠️ Ele tinha razao, e a flag NAO estava avariada. MEDIDO a 2026-09-09 com o
# jogo SERVIDO e **todas** as flags visuais ligadas: **160 emoji visiveis em 8
# abas, 57 distintos**. A `iconografia` alcanca **9,2%** das ocorrencias; o
# resto sao literais crus que nunca tiveram porta nenhuma.
#
# Esta seccao nao conserta isso — conserta-lo e' um lote. O que ela faz e'
# impedir que PIORE, que e' a metade que se perde sempre: cada aba nova, cada
# item novo, cada funcao nova traz emoji com ela se ninguem contar.
#
# **A catraca:** o numero medido tem de ser <= ao TECTO declarado. Baixa-se o
# tecto quando se corrige; um emoji novo sem porta empurra-o para cima e a
# suite fica VERMELHA, com o ficheiro e a linha.
print("\n=== 15. A CATRACA DO EMOJI: o numero so' desce ===")

import importlib.util as _ilu
_aud_spec = _ilu.spec_from_file_location(
    "_audit_iconografia", os.path.join(ROOT, "scripts", "_audit_iconografia.py"))
_AUD = _ilu.module_from_spec(_aud_spec)
_aud_spec.loader.exec_module(_AUD)

# ── O TECTO, medido a 2026-09-09. BAIXAR ao corrigir; nunca subir. ──────────
# 2026-09-09, lote 印 OS ICONES ANTIGOS: 36 -> 23 (ui.js) e 1311 -> 1300
# (tabs.js). O que desceu: os 11 emoji do avatar deixaram de estar CRUS (viraram
# a tabela `REALM_AVATAR_DEFS`, com `mark:` ao lado, como o `TAB_DEFS`); o sino,
# o emblema do mundo e o chip do reino passaram a ter portao; e os 11 emoji que
# o `ProfileModal` tinha COPIADOS a' mao desapareceram com o gemeo.
_TECTO_CRU = {
    "miniapp/components/ui.js": 23,
    # ⚠️ 2026-09-23, 武 2.2: 1300 -> 1289, e a descida NAO e' deste lote — e'
    # a FOLGA que ninguem baixou. Medido dos dois lados (HEAD e agora):
    # 1289 crus, 32 gated, 72 fallback, identico. A cena nova nasceu com
    # ZERO emoji literais (cada glifo e' uma `<Mark>` ou a arte da peca),
    # portanto o numero nao se mexeu. Baixar o tecto e' a metade da
    # catraca que se esquece: 11 de folga sao 11 emoji que podiam entrar
    # em silencio.
    "miniapp/components/tabs.js": 1289,
    # 2026-09-16, 坐 ONDA 1: 3 -> 2. O ☯️ de 36px do ecra de chegada-que-falha
    # saiu junto com o beco (era a unica coisa no ecra alem da palavra crua
    # "unauthorized"); no lugar dele ha' um cartao que diz o que aconteceu e
    # tem um botao. Baixar o tecto e' a metade da catraca que se esquece.
    "miniapp/components/app.js": 2,
}

_scan = _AUD.scan()
for _p, _tecto in _TECTO_CRU.items():
    _n = sum(1 for _, _, c in _scan[_p] if c == "cru")
    _piores = [("%s:%d %s" % (_p.split("/")[-1], l, e))
               for l, e, c in _scan[_p] if c == "cru"][:3]
    chk(_n <= _tecto,
        "catraca: %s tem %d emoji CRUS (tecto %d). Se subiu, nasceu um emoji "
        "sem porta — baixe-o, nao suba o tecto. Primeiros: %s"
        % (_p.split("/")[-1], _n, _tecto, _piores))

# ⚠️ A guarda que prova que a CATRACA olha para alguma coisa. Um tecto sobre um
# conjunto vazio e' verde para sempre (licao de 08/09: `set() <= {...}`).
_total_cru = sum(1 for hits in _scan.values() for _, _, c in hits if c == "cru")
chk(_total_cru > 1000,
    "catraca: a auditoria ainda ve %d emoji crus — se este numero desabasse "
    "para ~0 de repente, seria o regex partido e nao o problema resolvido"
    % _total_cru)

# ── O CABECALHO: o multiplicador ───────────────────────────────────────────
# Nao e' "mais um sitio". E' o unico componente que renderiza em TODAS as telas,
# portanto um emoji cru aqui paga-se uma vez por cada ecra que o jogador abre —
# 47 das 160 ocorrencias vistas (29%) sao estes.
# ⚠️ A guarda MUDOU DE PERGUNTA a 2026-09-09 (lote 印 OS ICONES ANTIGOS). Ate'
# aqui ela perguntava *"nasceu algum emoji NOVO no cabecalho?"* e tolerava os 13
# conhecidos. Os 13 acabaram — o avatar, o sino, o chip do reino e o emblema do
# mundo passaram todos por portao — portanto a pergunta certa passa a ser a
# absoluta: **ZERO**. Uma guarda que continuasse a tolerar 13 deixaria voltar
# exactamente aquilo que este lote foi tirar.
_HDR = [e for _, e in _AUD.header_offenders()]
chk(_HDR == [],
    "cabecalho: ZERO emoji sem porta nas regioes que renderizam em TODAS as "
    "telas (`PlayerHeader` + `RealmAvatar` + `REALM_AVATAR_DEFS`). Um emoji cru "
    "aqui paga-se 1x por cada ecra que o jogador abre — foram 47 das 160 "
    "ocorrencias vistas (29%%) antes de 09/09. Encontrados: %r" % (_HDR,))

# ⚠️ **A ANTI-GUARDA, e ela e' obrigatoria aqui.** Zero e' tambem o que uma
# medicao CEGA devolve: basta o localizador deixar de encontrar a funcao (uma
# renomeacao, um `var` a mais pelo meio) para o assert acima ficar verde para
# sempre sobre o conjunto vazio — a licao de 08/09 (`set() <= {...}`) e a de
# 09/09 (o ✕ alcancavel numa janela de 36px sem nada dentro). Portanto: provar
# que ele AINDA le' as tres regioes, e que cada uma tem codigo la' dentro.
_REG = _AUD.header_source()
chk(len(_REG) == 3,
    "cabecalho: a medicao le' as 3 regioes do multiplicador (leu %d)" % len(_REG))
for _anchor, _off, _body in _REG:
    chk(len(_body) > 400,
        "cabecalho: a regiao %r tem %d chars — se encolheu para quase nada, o "
        "localizador partiu-se e o 'ZERO' acima nao vale nada"
        % (_anchor, len(_body)))
# e que o texto lido e' MESMO o do cabecalho, nao um pedaco qualquer do ficheiro
_SENT = {"function PlayerHeader(": "onBellClick",
         "function RealmAvatar(": "REALM_AVATAR_TONES",
         "var REALM_AVATAR_DEFS": "mark:"}
for _anchor, _sent in _SENT.items():
    # ⚠️ `.get`-style, NUNCA `[0]` — a licao de 09/09: uma guarda que REBENTA nao
    # e' uma guarda vermelha. Ao tirar uma regiao do localizador, a versao com
    # `[...][0]` levantava IndexError e a suite falhava a dizer que o FICHEIRO DE
    # TESTE estava errado, em vez de dizer que o codigo estava. Sabotagem 11.
    _bs = [b for a, _o, b in _REG if a == _anchor]
    chk(bool(_bs) and _sent in _bs[0],
        "cabecalho: a regiao %r existe e contem %r — sem isto a medicao pode "
        "estar a ler menos codigo do que o jogador ve, e a dizer zero com "
        "confianca" % (_anchor, _sent))

# ── UM DONO PARA O AVATAR (Lei 0 passo 2 / Lei F-7) ────────────────────────
# ⚠️ Esta e' a guarda que teria evitado o lote. A escada de 11 emoji de reino
# existia DUAS vezes — no `PlayerHeader` e, copiada a' mao, no `ProfileModal`,
# com o comentario *"Mirrors the `REALM_EMOJIS` from ui.js"* escrito por cima.
# Duas copias divergiram em seis valores sem ninguem dar por isso, e o orbe
# sobreviveu a' sua propria morte (07/09) por viver no sitio que ninguem contou.
# A guarda nao pergunta "existe um `RealmAvatar`?" — pergunta se a ESCADA aparece
# mais do que uma vez, que e' o sintoma real.
_UI_NC = _strip_js_comments(_UIM)
_TABS_NC = _strip_js_comments(_TBM)
_ESCADA = re.compile(r'"\U0001FAA8"[\s\S]{0,240}?"\U0001F338"')
_n_escadas = (len(_ESCADA.findall(_UI_NC)) + len(_ESCADA.findall(_TABS_NC)))
chk(_n_escadas == 1,
    "avatar: a escada dos 11 emoji de reino existe UMA vez nos componentes "
    "(encontrada %d). Duas copias e' a Lei F-7 outra vez — foi assim que o orbe "
    "sobreviveu a' propria morte de 07/09." % _n_escadas)
chk(_UI_NC.count("<RealmAvatar") + _TABS_NC.count("<RealmAvatar") >= 2,
    "avatar: os DOIS sitios (cabecalho e `ProfileModal`) desenham o MESMO "
    "componente — um conserto, dois sitios")
# e o `title` da marca: uma marca muda e' pior do que o emoji que substituiu
_RA = _obj_after(_UIM, "function RealmAvatar") if False else _UI_NC[
    _UI_NC.index("function RealmAvatar("):]
_RA = _RA[:_RA.index("\n    var ")] if "\n    var " in _RA else _RA[:4000]
chk("title={realmName(" in _RA,
    "avatar: a marca do avatar leva `title` (=> role=img + aria-label). Sem ele "
    "a iconografia seria uma REGRESSAO: o emoji ainda era anunciado, um SVG e' "
    "mudo")

# ── A NAVEGACAO DESENHA A MARCA COM COR (o preto sobre preto) ──────────────
# 🔴 MEDIDO a 2026-09-09 no jogo servido: as marcas das DUAS barras de baixo
# sairam com `stroke: rgb(0,0,0)` sobre um fundo quase preto — 8 por ecra, em
# todas as abas olhadas. A causa: um `<button>` nao herda a cor da pagina (a
# folha do agente po~e-lhe `color: buttontext`, preto) e a `Mark` desenha em
# `currentColor` de proposito. Um emoji nao quer saber da cor — por isso a
# omissao ficou invisivel um lote inteiro, com a guarda das marcas VERDE: ela
# perguntava se o `TAB_DEFS` tinha `mark:`, nunca se o traco se via.
for _fn, _rot in (("function BottomNav(", "BottomNav"),
                  ("function V2BottomNav(", "V2BottomNav")):
    _i = _UI_NC.index(_fn)
    _j = _UI_NC.find("\n    function ", _i + 20)
    _body = _UI_NC[_i:_j if _j > 0 else len(_UI_NC)]
    chk(re.search(r'color:\s*markOn\([^)]*\)\s*\?\s*"var\(--gold2\)"\s*:\s*undefined',
                  _body) is not None,
        "nav: o botao do %s declara `color` quando desenha marca — sem isto a "
        "`Mark` herda `buttontext` (PRETO) e desaparece na barra escura" % _rot)

# ── CADA ABA NOVA NASCE COM MARCA (a clausula "cada nova aba" da lei) ──────
_TABDEF = _obj_after(_UIM, "var TAB_DEFS")
_tabs_sem_marca = [m.group(1) for m in re.finditer(r'key:"(\w+)"([^}]*)', _TABDEF)
                   if "mark:" not in m.group(2)]
# ⚠️ HONESTIDADE: esta clausula JA' estava coberta pela guarda das marcas (§10,
# "as 25 abas TODAS tem marca"), e foi verificado em isolamento. Fica na mesma,
# com a mensagem presa a' LEI e nao a' feature — quem partir isto le' o porque',
# nao so' o que. O que e' NOVO nesta seccao e' a catraca e o cabecalho.
chk(_tabs_sem_marca == [],
    "aba: TODA entrada de `TAB_DEFS` traz `mark:` — uma aba nova sem marca "
    "nasce a falar emoji do sistema (sem marca: %r)" % (_tabs_sem_marca,))
chk(len(re.findall(r'mark:', _TABDEF)) >= 25,
    "aba: e sao %d marcas declaradas — o conjunto nao e' vazio"
    % len(re.findall(r'mark:', _TABDEF)))

# ── E OS 5 HUBS DA `ui_v2` DEIXARAM DE SER PENDENTES (2026-09-09) ──────────
# Ate' aqui esta guarda **contava** os 5 hubs sem marca e dizia o numero, que era
# a forma honesta de declarar um pendente. O pendente fechou: `HUB_DEFS` tem 5/5.
#
# ⚠️ E a guarda antiga estava PARTIDA, do jeito exacto que a licao de 09/09
# descreve — afirmava sobre o FICHEIRO em vez de sobre o SITIO:
#     [... for m in ... if "mark:" not in _HUBDEF]
# o `if` nao olhava para a entrada `m`, olhava para o objecto INTEIRO. Bastava
# UMA marca em qualquer hub para a lista esvaziar de repente e a guarda ir a
# vermelho por um numero, nao por um facto. Agora o filtro le' a ENTRADA.
_HUBDEF = _obj_after(_UIM, "var HUB_DEFS")
_hub_entries = re.findall(
    # ⚠️ o `(?<![a-z_])` nao e' paranoia: sem ele o `label_key:"..."` de cada
    # entrada tambem casa, e o localizador ve 10 entradas onde ha' 5.
    r'(?<![a-z_])key:"(\w+)",([\s\S]*?)(?=(?<![a-z_])key:"|\Z)', _HUBDEF)
chk(len(_hub_entries) == 5,
    "hub: o localizador ainda ve as 5 entradas de `HUB_DEFS` (viu %d) — se caisse "
    "a zero, tudo o que vem a seguir ficava verde sobre o conjunto vazio"
    % len(_hub_entries))
_hubs_sem_marca = [k for k, body in _hub_entries if "mark:" not in body]
_hubs_sem_ico = [k for k, body in _hub_entries if "ico:" not in body]
chk(_hubs_sem_ico == [],
    "OFF-identidade: TODA entrada de `HUB_DEFS` tem `ico:` — e' esta a prova que autoriza `ico(h.ico, ...)`; sem ela o ramo DESLIGADO da barra da `ui_v2` desenhava vazio (sem ico: %r)" % (_hubs_sem_ico,))
chk(_hubs_sem_marca == [],
    "hub: TODA entrada de `HUB_DEFS` traz `mark:` — e' a barra que o owner tem "
    "debaixo do polegar na `ui_v2`, e durante um lote inteiro teve 0 de 5 "
    "enquanto o `TAB_DEFS` tinha 25 de 25 (sem marca: %r)" % (_hubs_sem_marca,))

# ══════════════════════════════════════════════════════════════════════════
# 16. 圖 O MAPA — a matriz de destinos, os dois estados, e zero orfaos
# ══════════════════════════════════════════════════════════════════════════
#
# ⚠️ Seccao NOVA na suite EXISTENTE (nao a 29a suite). Nao entrou na §15 porque
# a §15 e' a catraca do EMOJI e o mapa nao e' um assunto de emoji — e' de
# NAVEGACAO. Misturar os dois dava uma seccao que ninguem sabe porque' e' que
# fica vermelha.
#
# A Lei de Ferro (a) — *100% das features alcancaveis, ZERO orfaos* — e a regra
# MA-32b — *entradas mudam, destinos NUNCA* — sao o que este lote arrisca: uma
# tela que substitui uma lista por uma pintura pode APAGAR um destino sem que
# ninguem de' por isso, porque o destino continua a existir no codigo e so'
# deixa de ter porta. Nao ha' erro, nao ha' 404: ha' uma coisa que deixou de ser
# alcancavel.
print("\n=== 16. 圖 O MAPA: a matriz de destinos e os dois estados ===")

# ⚠️ `_obj_after` LEVANTA `ValueError` quando nao encontra o nome, e a suite
# morreria a dizer que o FICHEIRO DE TESTE esta' errado em vez de dizer que o
# codigo esta' (a licao de 09/09: *uma guarda que rebenta nao e' uma guarda
# vermelha*). Aqui o alvo pode mesmo desaparecer — e' isso que a §16 existe para
# apanhar — portanto a falta tem de virar ASSERT, nao traceback.
def _obj_ou_vazio(src, needle):
    try:
        return _obj_after(src, needle)
    except (ValueError, AssertionError):
        return ""


_SCENES = _obj_ou_vazio(_UIM, "var HUB_SCENE_DEFS")
_PENDING = _obj_ou_vazio(_UIM, "var HUB_SCENE_PENDING")
_HUBDEF2 = _obj_ou_vazio(_UIM, "var HUB_DEFS")
_HUBSCENE = _fn_src(_UIM, "function HubScene(") if "function HubScene(" in _UIM else ""
chk(bool(_SCENES) and bool(_PENDING) and bool(_HUBSCENE),
    "mapa: as tres pecas do mapa existem com o nome que o resto desta seccao "
    "procura (`HUB_SCENE_DEFS` %s · `HUB_SCENE_PENDING` %s · `HubScene` %s). "
    "Se uma for renomeada, TUDO o que vem a seguir passa a comparar conjuntos "
    "vazios — e um conjunto vazio satisfaz quase toda a guarda que existe"
    % (bool(_SCENES), bool(_PENDING), bool(_HUBSCENE)))

# ── 16a. O LOCALIZADOR VE' ALGUMA COISA (a licao do conjunto vazio) ────────
# ⚠️ Tudo o que vem a seguir e' uma comparacao de conjuntos, e um conjunto vazio
# satisfaz quase todas: `set() <= {...}` e' verdade, e `[x for x in [] ...]` e'
# sempre `[]`. Se o `_obj_after` deixar de encontrar a tabela (um rename, um
# `var` a mais pelo meio), a seccao inteira fica verde sem nunca ter olhado.
_scene_hubs = re.findall(r'^      (\w+):\s*\{', _SCENES, re.M)
chk(len(_scene_hubs) >= 1,
    "mapa: o localizador ve' %d hub(s) com cena em `HUB_SCENE_DEFS` — se caisse "
    "a zero, TUDO o que vem a seguir ficava verde sobre o conjunto vazio"
    % len(_scene_hubs))
_hub_entries2 = re.findall(
    r'(?<![a-z_])key:"(\w+)",([\s\S]*?)(?=(?<![a-z_])key:"|\Z)', _HUBDEF2)
chk(len(_hub_entries2) == 5,
    "mapa: o localizador ainda ve' as 5 entradas de `HUB_DEFS` (viu %d)"
    % len(_hub_entries2))

# ── 16b. TODO HUB TEM RESPOSTA: ou cena, ou pendente DECLARADO ─────────────
# "Pendente" e' um estado legitimo; "esquecido" nao e' (Lei 0 passo 5). Um hub
# que nao esteja em nenhuma das duas tabelas e' exactamente o esquecido.
_pending_hubs = set(re.findall(r'^      (\w+):\s*"', _PENDING, re.M))
_all_hubs = [k for k, _ in _hub_entries2]
_sem_resposta = [h for h in _all_hubs
                 if h not in _scene_hubs and h not in _pending_hubs]
chk(_sem_resposta == [],
    "mapa: TODO hub do `HUB_DEFS` tem resposta — cena desenhada ou pendente "
    "DECLARADO com motivo. Sem resposta: %r" % (_sem_resposta,))
# e o motivo tem de ser um motivo, nao uma palavra
_motivos_curtos = [m.group(1) for m in re.finditer(r'^      \w+:\s*"([^"]*)"', _PENDING, re.M)
                   if len(m.group(1)) < 40]
chk(_motivos_curtos == [],
    "mapa: todo pendente traz o MOTIVO escrito e nao so' a palavra 'pendente' "
    "— um pendente sem porque' e' um esquecido com melhor caligrafia (%r)"
    % (_motivos_curtos,))

# ── 16c. A MATRIZ: zero orfaos, zero portas para lado nenhum ──────────────
# ⚠️ E' ESTE o assert que a Lei de Ferro (a) pede pelo nome. Quando alguem
# acrescentar um destino ao `group` de um hub que ja' tem cena, isto fica
# vermelho COM O NOME do destino — e nao ha' como o esquecer.
_hub_group = {}
_hub_group_landing = {}
for _k, _body in _hub_entries2:
    _g = re.search(r'group:\s*\[([^\]]*)\]', _body)
    _hub_group[_k] = set(re.findall(r'"([^"]+)"', _g.group(1) if _g else ""))
    # o `landing` e' o que da' o NOME da funcao da tela (hub_mundo_screen ->
    # HubMundoScreen); e' assim que a prova de alcancabilidade acha o codigo.
    _l = re.search(r'landing:"([^"]+)"', _body)
    _hub_group_landing[_k] = _l.group(1) if _l else ""

_doors_by_hub = {}
for _h in _scene_hubs:
    # ⚠️ `_obj_after` e NAO um `find("\n      ")`: a 1a versao cortava o bloco no
    # primeiro `\n` + 6 espacos, e as linhas DE DENTRO da cena tem 8 — o corte
    # caia na 2a linha e o localizador lia ZERO portas. Ficou vermelho a dizer
    # exactamente isso, que e' o que a anti-guarda existe para fazer.
    _blk = _obj_after(_SCENES, "      %s:" % _h)
    _doors_by_hub[_h] = re.findall(
        r'\{\s*key:"(\w+)",\s*tab:"(\w+)",\s*label_key:"([^"]+)",'
        r'\s*art:"([^"]+)",\s*x:(-?\d+),\s*y:(-?\d+),\s*w:(\d+)\s*\}', _blk)

for _h in _scene_hubs:
    _dd = _doors_by_hub[_h]
    chk(len(_dd) >= 1,
        "mapa: a cena de %s tem %d portas lidas pelo localizador — zero seria a "
        "guarda a afirmar sobre o vazio" % (_h, len(_dd)))
    # o `group` menos os landings-tela (o `*_screen` e' a PROPRIA tela, nao um
    # destino que precise de porta)
    _dest = {d for d in _hub_group.get(_h, set()) if not d.endswith("_screen")}
    _tabs = {t for _k, t, _lk, _a, _x, _y, _w in _dd}
    _orfaos = sorted(_dest - _tabs)
    _fantasmas = sorted(_tabs - _dest)
    # ── 🔴 2026-09-13 — A GUARDA APERTA, E ISTO E' UMA CORRECCAO DA PERGUNTA ──
    #
    # Ate' aqui ela perguntava *"todo destino tem PORTA?"*, porque a unica cena
    # que existia era a Caverna, onde porta e destino sao 1 para 1. O Mundo
    # partiu essa premissa: dos seus 8 destinos, **nenhum** e' um continente —
    # quatro pairam no CEU (nao pertencem a lugar nenhum, e' isso que a palavra
    # quer dizer) e quatro sao LOCAIS da ilha onde voce esta', que mudam com o
    # sitio. As portas da cena sao os cinco continentes.
    #
    # A pergunta certa nunca foi a porta — e' a **Lei de Ferro (a)**: *todo
    # destino continua ALCANCAVEL a partir desta tela?* Um destino sem porta so'
    # e' um orfao se a tela tambem nao o chamar.
    #
    # ⚠️ E a prova nao pode ser uma DECLARACAO ("este hub e' especial"), senao
    # qualquer futuro apagador de destinos escreve a declaracao e passa. Le'-se
    # o CODIGO DA TELA daquele hub e exige-se um `setTab("<destino>")` la'
    # dentro. Apagar um chip do Ceu poe isto vermelho COM O NOME do destino,
    # exactamente como antes.
    _scr_fn = "".join(w.capitalize() for w in
                      _hub_group_landing.get(_h, "").replace("_screen", "").split("_"))
    _scr_src = _fn_src(_TBM, "function %sScreen(" % _scr_fn) \
        if ("function %sScreen(" % _scr_fn) in _TBM else ""
    chk(bool(_scr_src) or not _orfaos,
        "mapa: a tela de %s foi encontrada pelo nome (`%sScreen`) — sem ela a "
        "prova de alcancabilidade compara o conjunto vazio e fica verde sobre "
        "nada" % (_h, _scr_fn))
    _inalcancaveis = sorted(d for d in _orfaos
                            if ('setTab("%s")' % d) not in _scr_src)
    chk(_inalcancaveis == [],
        "mapa: ZERO ORFAOS em %s — todo destino do `group` ou tem porta na cena, "
        "ou continua a ser chamado por `setTab()` de dentro da PROPRIA tela (o "
        "Ceu, a gaveta da ilha). Um destino que so' existia na lista que o mapa "
        "substituiu deixa de ser alcancavel sem dar erro nenhum (Lei de Ferro "
        "(a) / MA-32b). Inalcancaveis: %r" % (_h, _inalcancaveis))
    chk(not _orfaos or len(_orfaos) < len(_dest) or _h != "hub_caverna",
        "mapa: a Caverna continua a ser 1-para-1 (porta por destino) — se ela "
        "passasse a depender do `setTab` da tela, a cena tinha deixado de ser a "
        "navegacao e voltado a ser decoracao")
    chk(_fantasmas == [],
        "mapa: nenhuma porta de %s aponta para fora do `group` do hub — uma "
        "porta assim leva o jogador para uma aba que o hub nao reclama, e o "
        "botao Voltar passa a mentir (%r)" % (_h, _fantasmas))

# ── 16d. GEOMETRIA: dentro da caixa, e nenhuma porta por cima de outra ────
# ⚠️ ANCORADA NA CAIXA, e isto foi a sabotagem 15 a ensinar. A 1a versao
# procurava `aspectRatio:"1 / N"` no `HubScene` inteiro — e a PORTA tambem tem
# um (`1 / 1`). Ao apagar o da caixa a guarda continuava VERDE, a ler a razao da
# porta e a medir sobreposicoes com rectangulos que nao existem. E' a licao de
# 09/09 pela enesima vez: *afirmar sobre o FICHEIRO em vez do SITIO fica verde
# pela ocorrencia errada.* Agora le'-se a razao que vem a seguir ao `maxWidth`
# da caixa, que e' o unico sitio onde ela pode viver.
_m_asp = re.search(r'maxWidth:520,[\s\S]{0,120}?aspectRatio:"1 / ([\d.]+)"',
                   _HUBSCENE)
chk(_m_asp is not None,
    "mapa: a CAIXA da cena declara a sua razao (`aspectRatio` a seguir ao "
    "`maxWidth`) — sem a ler, a guarda da sobreposicao mede rectangulos "
    "imaginarios, e a razao da PORTA (1/1) daria um verde falso")
_ASPECT = float(_m_asp.group(1)) if _m_asp else 1.0
chk(1.0 <= _ASPECT <= 2.2,
    "mapa: a razao da caixa e' %.2f — fora de [1.0, 2.2] a cena ou vira uma "
    "faixa ou nao cabe no ecra" % _ASPECT)
# ⚠️ Duas portas sobrepostas nao dao erro: dao UMA porta e outra inalcancavel
# por baixo dela. E' o orfao outra vez, so' que em pixels em vez de em codigo.
for _h in _scene_hubs:
    _boxes = []
    for _k, _t, _lk, _art, _x, _y, _w in _doors_by_hub[_h]:
        _x, _y, _w = int(_x), int(_y), int(_w)
        chk(0 <= _x and _x + _w <= 100,
            "mapa: a porta %s/%s cabe na largura da caixa (x=%d w=%d)"
            % (_h, _k, _x, _w))
        chk(0 <= _y <= 100,
            "mapa: a porta %s/%s comeca dentro da caixa (y=%d)" % (_h, _k, _y))
        _boxes.append((_k, _x, _y, _w))
    for _i in range(len(_boxes)):
        for _j in range(_i + 1, len(_boxes)):
            _ka, _xa, _ya, _wa = _boxes[_i]
            _kb, _xb, _yb, _wb = _boxes[_j]
            # ⚠️ A porta e' QUADRADA, mas `x`/`w` sao % da largura e `y` e' % da
            # ALTURA — logo a altura de uma porta em % da caixa e' `w / razao`.
            # A razao LE'-SE do proprio `HubScene` e nunca se assa aqui: ela
            # mudou de 1.02 para 1.45 depois de se olhar para a tela, e uma
            # constante escrita nesta linha teria continuado verde a comparar
            # rectangulos que ja' nao existem.
            _ha, _hb = _wa / _ASPECT, _wb / _ASPECT
            _ovx = min(_xa + _wa, _xb + _wb) - max(_xa, _xb)
            _ovy = min(_ya + _ha, _yb + _hb) - max(_ya, _yb)
            chk(not (_ovx > 2 and _ovy > 2),
                "mapa: as portas %s e %s de %s nao se sobrepoem (%.0f%% x "
                "%.0f%%) — uma porta por baixo de outra e' um destino "
                "inalcancavel sem erro nenhum"
                % (_ka, _kb, _h, max(_ovx, 0), max(_ovy, 0)))

# ── 16e. A ARTE PEDIDA EXISTE EM DISCO ────────────────────────────────────
# ⚠️ A licao do §13: arte que nao existe cai num estado LEGITIMO (aqui, a chapa
# de pedra) — ninguem ve' um erro, so' ve' uma porta feia. Um nome mal escrito
# sobreviveria para sempre.
_ASSETS = os.path.join(ROOT, "miniapp", "newapp", "assets")
_arte_pedida = set(re.findall(r'art:\s*"([^"]+\.webp)"', _SCENES))
chk(len(_arte_pedida) >= 6,
    "mapa: a cena pede %d ficheiros de arte — o conjunto nao e' vazio"
    % len(_arte_pedida))
_sem_ficheiro = sorted(f for f in _arte_pedida
                       if not os.path.isfile(os.path.join(_ASSETS, f)))
chk(_sem_ficheiro == [],
    "mapa: toda a arte pedida pelo `HUB_SCENE_DEFS` existe em disco (sem "
    "ficheiro: %r)" % (_sem_ficheiro,))

# ── 16f. UM DONO, e as duas flags ─────────────────────────────────────────
_n_scene_defs = len(re.findall(r"function\s+HubScene\s*\(", _UIM + _TBM))
chk(_n_scene_defs == 1,
    "mapa: existe UMA definicao de `HubScene` em todo o cliente (%d) — duas "
    "ligacoes a' mao divergem sempre (Lei 0 passo 2)" % _n_scene_defs)
# ⚠️ 2026-09-16 — A CONTA MUDOU DE FORMA, e a correccao NAO e' relaxar o numero.
# Ate' aqui todo `<HubScene` era um HUB, e portanto bastava compara-lo com o
# numero de cenas declaradas. Deixou de ser verdade: o continente abre como um
# LUGAR e reusa o mesmo componente com `sceneDef`, sem ser um hub (nao tem
# `group` no `HUB_DEFS`). Trocar isto por um `>=` teria transformado a guarda
# numa que nao conta — passa a separar-se o que e' de hub do que nao e'.
_hs_hub = len(re.findall(r'<HubScene\s+hub="', _TBM))
_hs_def = len(re.findall(r"<HubScene(?![\w])(?:(?!/>|>)[\s\S]){0,400}?sceneDef=", _TBM))
chk(_hs_hub == len(_scene_hubs),
    "mapa: exactamente as telas COM cena de HUB desenham o `HubScene hub=` (%d "
    "desenham, %d cenas declaradas) — uma a mais e' um hub a mostrar a caverna "
    "de outro; uma a menos e' arte paga que nunca chega ao ecra"
    % (_hs_hub, len(_scene_hubs)))
chk(_hs_hub + _hs_def == len(re.findall(r"<HubScene", _TBM)),
    "mapa: TODO `<HubScene` e' ou de hub (`hub=`) ou de cena declarada "
    "(`sceneDef=`) — um terceiro modo de o chamar e' uma cena sem dono, que "
    "ninguem conta e ninguem guarda (%d hub + %d sceneDef de %d)"
    % (_hs_hub, _hs_def, len(re.findall(r"<HubScene", _TBM))))
_MAPAON = _fn_src(_UIM, "function mapaOn(")
chk('featureEnabled("o_mapa")' in _MAPAON and 'featureEnabled("ui_v2")' in _MAPAON,
    "mapa: `mapaOn()` exige as DUAS flags. As telas de hub so' existem com a "
    "`ui_v2`; sem esta conjuncao, ligar so' a `o_mapa` nao mudava um pixel e o "
    "owner concluia que a flag estava avariada (Lei §6)")

# ── 16g. OS DOIS ESTADOS — e o apagado CONTINUA a ser uma porta ───────────
# ⚠️ Este e' o assert que o exemplo do owner pede ("um templo com nome guilda —
# e se ele nao tiver guilda?"). O erro facil nao e' esquecer o cinzento: e'
# desligar o `onClick` junto com a luz, e ai' a Lei §1 parte-se em silencio.
# ⚠️ O `onClick` da porta deixou de caber num regex de chavetas quando ganhou o
# ramo do `onSelect` (2026-09-13). Um regex que deixa de casar devolve `None` e
# a guarda fica vermelha — foi o que aconteceu, e e' o comportamento certo. Mas
# a correccao NAO pode ser afrouxar: le'-se o bloco com um contador de chavetas,
# que segue o handler ate' onde ele acabar, tenha o tamanho que tiver.
def _bloco_apos(src, needle):
    i = src.find(needle)
    if i < 0:
        return ""
    i = src.find("{", i + len(needle) - 1)
    if i < 0:
        return ""
    d = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            d += 1
        elif src[j] == "}":
            d -= 1
            if d == 0:
                return src[i:j + 1]
    return ""


# ── 🔴 2026-09-15 — A GUARDA SEGUE A PORTA, E NUNCA SE BAIXA ───────────────
#
# A porta saiu de dentro do `HubScene` e passou a ser o `SceneDoor`, porque a V7
# poe as MESMAS portas dentro do continente e escreve-las la' outra vez era a
# segunda ligacao a' mao que a Lei F-7 §2 proibe. Treze asserts desta seccao
# liam `_HUBSCENE` e ficaram vermelhos no mesmo segundo — que e' o comportamento
# CERTO de uma guarda estrutural.
#
# ⚠️ A correccao e' seguir a indireccao, jamais afrouxar: cada assert passa a
# afirmar sobre o ficheiro de quem agora desenha a porta. Baixar qualquer um
# deles para "existe algures no ui.js" teria transformado treze guardas que
# apontam num sitio em treze que apontam no repositorio.
_SCENEDOOR = _fn_src(_UIM, "function SceneDoor(") if "function SceneDoor(" in _UIM else ""
chk(len(_SCENEDOOR) > 400,
    "mapa: o localizador achou o `SceneDoor` pelo nome (%d chars) — a zero, os "
    "treze asserts abaixo comparam a string vazia e ficam verdes sobre nada"
    % len(_SCENEDOOR))
# UM DONO: uma definicao, e o `HubScene` USA-A em vez de desenhar a sua.
_n_door_defs = len(re.findall(r"function\s+SceneDoor\s*\(", _UIM + _TBM))
chk(_n_door_defs == 1,
    "mapa: existe UMA definicao de `SceneDoor` em todo o cliente (%d) — duas "
    "ligacoes a' mao divergem sempre (Lei 0 passo 2)" % _n_door_defs)
chk("<SceneDoor" in _HUBSCENE and "<img" not in _HUBSCENE.split("def.doors.map")[-1],
    "mapa: o `HubScene` DELEGA a porta no `SceneDoor` e nao voltou a desenhar "
    "uma — se ele reimplementasse a sua, as duas divergiam no primeiro estado "
    "novo e a gaveta do continente ficava com a versao velha")
# 🔴 E O ASSERT TEM DE SER SOBRE A CONDICAO, NAO SOBRE O JSX. A 1a versao dizia
# so' `"<SceneDoor" in _TBM` e a bateria derrubou-a: trocar o `sceneOn &&` por
# `false &&` deixa o JSX inteiro no ficheiro e a guarda FICOU VERDE com a gaveta
# outra vez em emoji. Afirmar que um elemento EXISTE nao e' afirmar que ele
# CHEGA ao ecra — e' a mesma familia do "verde sobre o conjunto vazio".
#
# ⚠️ 2026-09-16 — RE-APONTADO. O owner corrigiu a forma: o continente deixou de
# ser uma GRELHA de azulejos (que desenhava `<SceneDoor>` a' mao na tela) e passou
# a ABRIR COMO UM LUGAR — uma cena, com as portas la' dentro. O `SceneDoor`
# continua a ser o dono unico da porta, mas quem o desenha e' o `HubScene`, e a
# tela so' declara a cena. Portanto a condicao que importa passou a ser a da
# CENA do continente. A guarda segue; nao se baixa.
_m_v7 = re.search(r'(\w+)\s*&&\s*typeof HubScene === "function"\s*'
                  r'&&\s*typeof ISLE_SCENE_ART === "object"', _TBM)
chk(_m_v7 is not None and _m_v7.group(1) == "sceneOn",
    "mapa: a gaveta abre o continente como CENA sob a flag do mapa (`sceneOn`), "
    "e a condicao le'-se do CODIGO (lido %r) — um `false &&` deixa o JSX no "
    "ficheiro e a arte nunca chega ao ecra"
    % (_m_v7.group(1) if _m_v7 else None,))
chk("sceneDef={{" in _TBM and "ISLE_SCENE_ART[isle.key]" in _TBM,
    "mapa: a cena do continente e' declarada pela tela e a pintura vem do "
    "`ISLE_SCENE_ART` — sem isto a V7 existe no `ui.js` e nunca chega ao ecra "
    "(arte paga invisivel, 3a vez)")
# ⚠️ E a LISTA de emoji so' pode existir SEM a flag. Duas formas de desenhar o
# mesmo dentro-do-continente foi exactamente o que o owner mandou corrigir: a
# grelha de azulejos sobreviveu um dia ao lado da cena e ja' era a Lei F-7 §2 a
# nascer. Aqui exige-se que o ramo da lista esteja atras de `!sceneOn`.
chk(re.search(r"\{!sceneOn && \(\s*<div style=\{\{\s*display:\"grid\"", _TBM)
    is not None,
    "mapa: a grelha de emoji do continente vive atras de `!sceneOn` — se as duas "
    "formas coexistirem, uma delas fica para tras no primeiro estado novo")

_ONCLICK = _bloco_apos(_SCENEDOOR, "onClick=")
chk(len(_ONCLICK) > 20,
    "mapa: o localizador leu o corpo do `onClick` da porta (%d chars) — a zero, "
    "a guarda de baixo ficava verde sobre a string vazia" % len(_ONCLICK))
# 🔴 2026-09-15 — ESTA GUARDA CEGOU-SE COM UM RENAME, e a bateria apanhou-o.
# Ela procurava a palavra `lit`. Ao sair para o `SceneDoor`, a variavel do estado
# passou a chamar-se `aceso` — e a sabotagem "o tap morre junto com a luz" ficou
# VERDE com o `onClick` a depender do estado. Uma guarda que afirma sobre UM
# nome de variavel morre no primeiro rename, em silencio. Agora afirma sobre os
# DOIS nomes, e o que ela mede continua a ser a Lei §1 e nao a ortografia.
_DEPENDE_DA_LUZ = ("lit", "aceso")
_dep = [w for w in _DEPENDE_DA_LUZ if w in _ONCLICK]
chk(_ONCLICK and not _dep,
    "mapa: o `onClick` da porta NAO depende do estado aceso/apagado (%r) — uma "
    "porta apagada e' um lugar a' espera, nunca um beco (Lei §1). Lido: %r"
    % (_dep, _ONCLICK))
# 州 O contrato novo: uma porta pode ABRIR em vez de IR, e o caminho por omissao
# (`setTab`) tem de continuar la' — se um deles sumisse, metade das cenas ficava
# muda sem partir mais nada.
# ⚠️ Agora a escolha vive no CHAMADOR (`onActivate`), portanto e' no `HubScene`
# que ela se afirma — segue-se a indireccao, nao se afrouxa o assert.
_ACT = _bloco_apos(_HUBSCENE, "onActivate=")
chk(len(_ACT) > 20,
    "mapa: o localizador leu o `onActivate` que o `HubScene` passa a' porta "
    "(%d chars)" % len(_ACT))
chk("onSelect" in _ACT and "setTab(d.tab)" in _ACT,
    "mapa: a porta sabe ABRIR (`onSelect`) E IR (`setTab(d.tab)`) — o Mundo "
    "precisa da 1a (um continente revela os seus locais, nao e' um destino) e a "
    "Caverna da 2a; perder qualquer uma parte um hub inteiro em silencio")

_m_dim = re.search(r'aceso\s*\n?\s*\?\s*"drop-shadow[^"]*"\s*\n?\s*:\s*\(?\s*'
                   r'(?:dim\s*\|\|\s*)?"grayscale', _SCENEDOOR)
chk(_m_dim is not None,
    "mapa: os DOIS estados saem da MESMA arte por CSS (aceso = halo, apagado = "
    "dessaturado) — dois ficheiros por porta duplicavam o custo e divergiam")
# ⚠️ E um hub que DECLARE o seu proprio apagado nao pode declarar um apagado que
# nao apaga: sem isto, `dim:"none"` passava e a cena perdia o estado em silencio.
for _m in re.finditer(r'dim:\s*"([^"]*)"', _SCENES):
    _v = _m.group(1)
    chk("grayscale" in _v and "brightness" in _v,
        "mapa: o `dim` declarado por um hub continua a DESSATURAR e a ESCURECER "
        "(lido %r) — um `dim` que nao apaga e' o estado a desaparecer sem que "
        "nada fique vermelho" % _v)

chk('safeT(dimKey || "mapa_porta_apagada")' in _SCENEDOOR,
    "mapa: o `aria-label` de uma porta apagada DIZ que esta' apagada — um "
    "leitor de ecra nao ve' o cinzento, e sem isto a unica informacao de estado "
    "da cena fica invisivel para quem mais precisa dela")
# ⚠️ E o hub tem de CONTINUAR a passar o seu `dim`/`dim_key` a' porta: o
# componente aceita-os, mas um `HubScene` que os deixasse cair fazia o Mundo
# voltar ao apagado DURO da Caverna — quatro continentes mortos, sem um unico
# assert vermelho, porque o valor por omissao existe.
chk("dim={def.dim}" in _HUBSCENE and "dimKey={def.dim_key}" in _HUBSCENE,
    "mapa: o `HubScene` passa o `dim` e o `dim_key` do hub a' porta — sem isso "
    "o Mundo herda o apagado da Caverna e sai morto, em silencio")
# 🔴 E o que "apagado" QUER DIZER muda com o hub. Na Caverna e' "ainda nao
# estabelecida"; no Mundo seria MENTIRA (um continente onde voce nao esta' nao
# esta' a' espera de ser construido — voce e' que esta' noutro sitio). Um
# `dim_key` que nao exista nas 3 linguas renderiza o TOKEN CRU no leitor de
# ecra, que e' pior do que a frase errada.
_dim_keys = set(re.findall(r'dim_key:\s*"([^"]+)"', _SCENES)) | {"mapa_porta_apagada"}
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    for _dk in sorted(_dim_keys):
        chk(_dk in _d and len(_d[_dk]) > 3,
            "mapa: a chave do estado apagado `%s` existe em %s — um `dim_key` "
            "declarado e nao traduzido anuncia o token cru" % (_dk, _lang))

# ── 16h. A PORTA E' UM BOTAO, com nome e com cor ──────────────────────────
# ⚠️ "Uma imagem com `onClick` nao e' um botao" (V5 §3.6). E a clausula de
# 09/09: um `<button>` nao herda a cor da pagina — a folha do agente po~e-lhe
# `color: buttontext` (PRETO). Foi assim que 8 marcas por ecra sairam pretas
# sobre preto durante um lote inteiro, com a guarda verde.
chk("<button" in _SCENEDOOR and "aria-label=" in _SCENEDOOR,
    "mapa: a porta e' um `<button>` com `aria-label` — alcancavel por Tab e "
    "anunciada; uma imagem com onClick nao e' um botao")
chk(re.search(r'color:\s*"var\(--gold2\)"', _SCENEDOOR) is not None,
    "mapa: o botao da porta declara `color` — sem isto tudo o que la' dentro "
    "herda `buttontext` (PRETO) sobre uma cena escura")
chk('alt=""' in _SCENEDOOR,
    "mapa: a arte da porta e' `alt=\"\"` (decoracao do botao) — o nome vive no "
    "`aria-label`, senao o leitor de ecra anuncia a mesma coisa duas vezes")
_CSS = rd("miniapp/index.html")
chk(".nv-door:focus-visible" in _CSS and 'className="nv-door"' in _SCENEDOOR,
    "mapa: a porta tem foco VISIVEL e a classe esta' mesmo no botao — o anel do "
    "agente nasce quadrado por cima de uma peca redonda e some contra o ouro")

# ── 16i. LEI §1 — a cena nunca deixa um buraco ───────────────────────────
# ⚠️ As duas imagens vivem agora em DOIS ficheiros (o fundo no `HubScene`, a
# porta no `SceneDoor`) — cada uma responde pelo seu `onError`. Contar "2 no
# HubScene" teria ficado verde com a porta sem recurso nenhum.
chk(_HUBSCENE.count("onError=") == 1,
    "mapa: o FUNDO da cena tem `onError` — a pintura pode falhar e o lugar "
    "continua a ser um lugar tocavel (%d)" % _HUBSCENE.count("onError="))
chk(_SCENEDOOR.count("onError=") == 1,
    "mapa: a PORTA tem `onError` — sem ele uma peca em falta deixa um botao "
    "invisivel, que e' um beco (Lei §1) (%d)" % _SCENEDOOR.count("onError="))
chk("setBgFailed" in _HUBSCENE and "aria-hidden" in _SCENEDOOR
    and "setFailed" in _SCENEDOOR,
    "mapa: ha' chapa de recurso por baixo de cada porta e fundo de recurso na "
    "caixa — nenhum dos dois e' um `null`")

# ══ 16k. 圖 V7 — O DENTRO DO CONTINENTE: zero orfaos, dos dois lados ═══════
#
# A V7 §4 pede isto pelo nome: *"a guarda passa a exigir peca para cada porta do
# continente, e fica vermelha COM O NOME da que nascer sem ela"*. Sao DUAS
# direccoes, e faltar qualquer uma delas e' um modo de falha diferente:
#
#   sitio sem peca  -> a gaveta desenha o ramo antigo (emoji) para UM local e a
#                      pintura para os outros cinco: a tela parece PARTIDA, que
#                      a Lei 0 diz ser pior do que estar por fazer.
#   peca sem sitio  -> arte paga que nunca chega a um ecra. Ja' aconteceu com 51
#                      artefactos durante meses e com os 9 chefes a 14/09.
_ISLE_ART = _obj_ou_vazio(_UIM, "var ISLE_DOOR_ART")
chk(len(_ISLE_ART) > 40,
    "mapa/V7: o localizador achou o `ISLE_DOOR_ART` (%d chars) — a zero, os "
    "asserts abaixo comparam conjuntos vazios e ficam verdes sobre nada"
    % len(_ISLE_ART))
_isle_art_keys = dict(re.findall(r'(\w+):\s*"([^"]+\.webp)"', _ISLE_ART))
chk(len(_isle_art_keys) >= 6,
    "mapa/V7: o localizador le' %d pecas de porta de continente (>=6)"
    % len(_isle_art_keys))

# os `id` que a gaveta pede, lidos do CODIGO da tela e nao de uma lista escrita
# aqui — uma lista a mao aqui divergia no primeiro local novo
# ⚠️ `_bloco_apos` conta CHAVETAS, e o `isleSites` devolve um ARRAY: ele parava
# no primeiro objecto e a guarda lia UM local dos seis. Ficou vermelha a dizer
# exactamente isso — que e' o trabalho da anti-guarda, e por isso ela vem
# ANTES dos asserts que dependem dela. Aqui contam-se PARENTESES RECTOS.
def _lista_apos(src, needle):
    i = src.find(needle)
    if i < 0:
        return ""
    i = src.find("[", i + len(needle) - 1)
    if i < 0:
        return ""
    d = 0
    for j in range(i, len(src)):
        if src[j] == "[":
            d += 1
        elif src[j] == "]":
            d -= 1
            if d == 0:
                return src[i:j + 1]
    return ""


_ISLESITES = _lista_apos(_TBM, "const isleSites = (isle) =>")
chk(len(_ISLESITES) > 300,
    "mapa/V7: o localizador leu a lista do `isleSites` (%d chars)"
    % len(_ISLESITES))
_isle_ids = re.findall(r'\{\s*id:"(\w+)"', _ISLESITES)
chk(len(_isle_ids) >= 6,
    "mapa/V7: a gaveta declara %d locais com `id` — todo local TEM de ter o id "
    "do destino, que e' por onde a peca se deriva (`ISLE_DOOR_ART[s.id]`). Um "
    "local sem `id` cai no ramo do emoji e a tela fica meio pintada"
    % len(_isle_ids))
_sem_peca = sorted(set(_isle_ids) - set(_isle_art_keys))
chk(_sem_peca == [],
    "mapa/V7: TODO local do continente tem peca declarada — sem peca: %r"
    % (_sem_peca,))
_peca_orfa = sorted(set(_isle_art_keys) - set(_isle_ids))
chk(_peca_orfa == [],
    "mapa/V7: nenhuma peca de porta ficou sem local que a peca — arte paga que "
    "nunca chega a um ecra: %r" % (_peca_orfa,))
# e o FICHEIRO existe mesmo em disco (a licao do §13: a arte que falta cai num
# estado LEGITIMO — a chapa de pedra — e um nome mal escrito viveria para sempre)
_isle_sem_ficheiro = sorted(f for f in _isle_art_keys.values()
                            if not os.path.isfile(os.path.join(_ASSETS, f)))
chk(_isle_sem_ficheiro == [],
    "mapa/V7: toda a peca pedida pelo `ISLE_DOOR_ART` existe em disco (sem "
    "ficheiro: %r)" % (_isle_sem_ficheiro,))

# ══ O CHAO DE CADA CONTINENTE — zero orfaos, nos dois sentidos ═════════════
# Um continente sem chao cai no recurso do `HubScene` e o jogador ve' uma caixa
# vazia com portas a flutuar, sem erro nenhum. Uma pintura sem continente e'
# arte paga que nunca chega a um ecra (ja' aconteceu com 51 artefactos).
_ISLE_CHAO = _obj_ou_vazio(_UIM, "var ISLE_SCENE_ART")
_chao = dict(re.findall(r'(\w+):\s*"([^"]+\.webp)"', _ISLE_CHAO))
chk(len(_chao) == 5,
    "mapa/V7: o localizador le' %d chaos de continente (sao 5) — a zero, tudo "
    "o que vem a seguir compara conjuntos vazios" % len(_chao))
# os continentes lem-se do CODIGO da tela, nunca de uma lista escrita aqui
_ISLES_ARR = _lista_apos(_TBM, "const isles = [")
_isle_keys = re.findall(r'\{\s*key:"(\w+)"', _ISLES_ARR)
chk(len(_isle_keys) == 5,
    "mapa/V7: o localizador le' os %d continentes do `isles` (sao 5)"
    % len(_isle_keys))
_sem_chao = sorted(set(_isle_keys) - set(_chao))
chk(_sem_chao == [],
    "mapa/V7: TODO continente tem chao declarado — sem chao ele abre como uma "
    "caixa vazia com portas a flutuar: %r" % (_sem_chao,))
_chao_orfao = sorted(set(_chao) - set(_isle_keys))
chk(_chao_orfao == [],
    "mapa/V7: nenhuma pintura de chao ficou sem continente que a peca: %r"
    % (_chao_orfao,))
_chao_sem_ficheiro = sorted(f for f in _chao.values()
                            if not os.path.isfile(os.path.join(_ASSETS, f)))
chk(_chao_sem_ficheiro == [],
    "mapa/V7: todo o chao pedido pelo `ISLE_SCENE_ART` existe em disco (sem "
    "ficheiro: %r)" % (_chao_sem_ficheiro,))

# ⚠️ E A FRASE DA PORTA APAGADA NAO PODE SER APAGADA PELA ARTE. As 20 portas
# das 4 ilhas remotas dizem "⛵ <cidade>" desde o MV-9, e a V7 §3 e' explicita:
# *a arte nao pode apagar essa frase, so' veste-la*. Sem isto o jogador tocava
# numa porta bonita e nada acontecia, sem uma palavra (Lei §1) — o beco que o
# MV-9 ja' tinha fechado uma vez.
# ⚠️ 2026-09-16 — a janela MUDOU DE SITIO. Com a cena, o estado vivo de cada
# porta deixou de ser escrito no JSX de um azulejo e passou a ser o mapa `doors`
# que a tela monta e entrega ao `HubScene`. A guarda le' ESSE mapa. Uma janela
# de caracteres fixa (`[:4200]`) a partir do `isleSites` continuaria a apanhar
# codigo — mas o codigo ERRADO, e ficaria verde sobre o ramo da lista de emoji.
_CENA_ILHA = _TBM[_TBM.find("sceneDef={{"):][:2600]
chk(len(_CENA_ILHA) > 800 and "ISLE_DOOR_LAYOUT" in _CENA_ILHA,
    "mapa/V7: o localizador leu a declaracao da cena do continente (%d chars) — "
    "a zero, os dois asserts abaixo ficam verdes sobre a string vazia"
    % len(_CENA_ILHA))
chk("seloViagem(isle)" in _CENA_ILHA and "line:" in _CENA_ILHA,
    "mapa/V7: a porta pintada do continente leva a linha `⛵ <cidade>` — a arte "
    "veste a frase, nunca a apaga (V7 §3 / MV-9)")
chk("onOpenTravel" in _CENA_ILHA,
    "mapa/V7: a porta APAGADA continua tocavel e leva a' viagem — um lugar "
    "pintado que nao faz nada e' um beco com mais passos (Lei §1)")
# ⚠️ E o CHAO tem de ser mais escuro do que as pecas que assentam nele. Sem veu
# proprio, cada porta saiu com um HALO no vale de Linghe — a mesma avaria de
# 13/09 ao contrario (la' o fundo claro fez buracos; aqui fez auroreolas).
chk("veil:" in _CENA_ILHA,
    "mapa/V7: a cena do continente declara o seu proprio veu — o dos hubs foi "
    "afinado para rocha quase-preta, e os cinco continentes sao chao com luz; "
    "sem isto as portas voltam a sair com halo")
# UM DONO tambem para o ⛵: a catraca do emoji apanhou-o quando ele se escreveu
# duas vezes (5 -> 7) e a regra e' baixar, nunca subir o tecto.
chk(_TBM.count('const seloViagem') == 1 and _TBM.count('const botaoViajar') == 1,
    "mapa/V7: o selo `⛵ <cidade>` e o botao de viajar tem UM dono cada — "
    "escritos duas vezes, a catraca do emoji sobe e a Lei F-7 §2 quebra-se")

# ══ 16l. 卷 A PELE DO PERGAMINHO — o rolo OCUPA o ecra ═════════════════════
#
# MEDIDO a 390x844, servido e olhado: o rolo ocupava **253 dos 601px** da caixa
# de conteudo (42%) e deixava **348px de PAGINA vazia** por baixo. Depois:
# **589 de 601 (98%)**. E' o mesmo defeito e a mesma correccao da Caverna a
# 11/09 (`1 / 1.02` -> `1 / 1.70`) — *um objecto que acaba a um terco do ecra
# le'-se como um CARTAO a flutuar*.
#
# ⚠️ E a razao de ser MEDIDO e nao assado: o cabecalho muda de altura com o
# estado do jogador (raiz, reino, passe). Uma conta escrita a mao ficava certa
# hoje e errada na primeira linha nova, e ninguem daria por isso — porque o
# resultado continua a ser "um rolo", so' que do tamanho errado.
_PERG = _fn_src(_TBM, "function HubPergaminhoScreen(") \
    if "function HubPergaminhoScreen(" in _TBM else ""
chk(len(_PERG) > 1000,
    "pele: o localizador achou o `HubPergaminhoScreen` (%d chars) — a zero, os "
    "asserts abaixo ficam verdes sobre a string vazia" % len(_PERG))
chk('closest(".scroll-area")' in _PERG and "clientHeight" in _PERG,
    "pele: a altura do rolo e' MEDIDA na caixa que o hospeda — sem isso ele "
    "volta a ter a altura do seu conteudo e o buraco de 348px reabre")
chk("paddingTop" in _PERG and "paddingBottom" in _PERG,
    "pele: a medida DESCONTA o padding da caixa — sem isso o rolo passa por "
    "baixo da barra de navegacao e o fim dele fica inalcancavel")
chk(re.search(r'minHeight:\s*fill\s*\?', _PERG) is not None
    and re.search(r'flex:\s*fill\s*\?', _PERG) is not None,
    "pele: a altura e o esticar vivem DENTRO do ternario — a identidade de quem "
    "nao tem medida quebra-se pela ORDEM, nao so' pelo valor (licao 09/09)")
# 🔴 SOBRE O CODIGO, NAO SOBRE A PROSA — e esta guarda cometeu o erro que ela
# propria vigia. A 1a versao procurava "100vh" no `_PERG` inteiro e ficou
# VERMELHA por causa do comentario que explica *"porque e' MEDIDO e nao
# `100vh`"*. E' a licao de 13/09 ao vivo (4x num lote): quem le' a prosa afirma
# sobre o texto que EXPLICA a correccao, nao sobre a correccao.
_PERG_CODE = _strip_js_comments(_PERG)
chk(len(_PERG_CODE) > 800,
    "pele: o filtro de comentarios deixou codigo de pe' (%d chars) — se apagasse "
    "tudo, o assert de baixo ficava verde sobre o vazio" % len(_PERG_CODE))
chk("100vh" not in _PERG_CODE and "100dvh" not in _PERG_CODE,
    "pele: a altura NAO e' assada em unidades de ecra — o cabecalho muda de "
    "altura com o estado do jogador e uma conta fixa mente em silencio")
# 🔴 O defeito que so' o OLHAR apanhou, e que nenhum teste de propriedade
# apanharia: a 1a textura tinha DOIS `repeating-linear-gradient` cruzados. Dois
# repetidores cruzados nao dao fibra — dao uma GRELHA, e o que apareceu no ecra
# foi papel milimetrico. Papel envelhecido e' TONAL, nunca linear.
_PAPEL = _bloco_apos(_PERG, "const papel =")
chk(len(_PAPEL) > 200,
    "pele: o localizador leu o objecto `papel` (%d chars)" % len(_PAPEL))
chk("repeating-linear-gradient" not in _PAPEL,
    "pele: o papel nao tem trama com PERIODO — dois repetidores cruzados dao "
    "uma grelha (papel milimetrico), e isso e' a regua #1 a falhar; o "
    "envelhecimento e' tonal (manchas + luz), nunca linear")
chk(_PAPEL.count("radial-gradient") >= 5,
    "pele: o papel tem manchas suficientes para nao ler como chapa (%d) — com "
    "menos de cinco a metade de baixo volta a ser um rectangulo liso"
    % _PAPEL.count("radial-gradient"))
# e o pendente que aqui estava FECHOU — nao pode voltar a dizer que ha' buraco
chk("440px" not in _PENDING,
    "pele: o pendente dos 440px de pagina vazia esta' FECHADO no "
    "`HUB_SCENE_PENDING` — um pendente resolvido que continua escrito manda a "
    "proxima sessao arranjar o que ja' esta' arranjado")

# ── 16j. UM TAP, NAO DOIS — o acordeao morreu no ramo LIGADO ──────────────
# ⚠️ Era metade da queixa do owner ("menus louco onde tem que buscar de um lado
# ao outro"): tocar a sala abria uma sanfona que revelava OUTRO botao. A guarda
# afirma sobre o SITIO (o ramo do mapa), nunca sobre o ficheiro — o "Entrar" do
# ramo DESLIGADO tem de continuar la', e por isso um `not in _TBM` estaria
# errado nos dois sentidos.
_i = _TBM.index("if (typeof mapaOn === \"function\"")
_RAMO = _TBM[_i:_TBM.index("Veios de pedra", _i)]
chk("hub_caverna_entrar" not in _RAMO,
    "mapa: o ramo LIGADO nao tem o botao 'Entrar' — tocar a porta VAI ao "
    "destino. Eram dois taps; passa a ser um")
chk("hub_caverna_entrar" in _TBM,
    "mapa: e o ramo DESLIGADO continua a ter o 'Entrar' — se isto ficasse "
    "vermelho, a guarda de cima estaria verde por o acordeao ter desaparecido "
    "dos DOIS lados, que e' uma regressao para quem tem a flag OFF")

# ── 16k. A FLAG: nasce OFF e auto-documenta-se ────────────────────────────
_DB2 = rd("database/db.py")
chk(re.search(r'"o_mapa":\s*False', _obj_after(_DB2, "DEFAULT_WORLD_FEATURES")) is not None,
    "mapa: a flag `o_mapa` nasce OFF em DEFAULT_WORLD_FEATURES (o `main` le' "
    "defaults — a lente dos 57)")
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    chk("feature_o_mapa" in _d and len(_d["feature_o_mapa"]) > 6,
        "mapa: rotulo no painel do owner em %s" % _lang)
    chk("feature_o_mapa_desc" in _d and len(_d["feature_o_mapa_desc"]) > 400,
        "mapa: descricao auto-documentada em %s" % _lang)
    # ⚠️ as DUAS coisas que ele precisa de saber ANTES de ligar o switch
    chk("ui_v2" in _d["feature_o_mapa_desc"],
        "mapa: a descricao DIZ que a flag exige a `ui_v2` em %s — sem isso ele "
        "liga, nao ve' nada, e conclui que esta' avariada" % _lang)
    chk("mapa_porta_apagada" in _d and len(_d["mapa_porta_apagada"]) > 3,
        "mapa: a chave do estado apagado existe em %s" % _lang)

# ⚠️ Escrito pelo ASSUNTO, nunca sobre "a migration mais alta do repositorio"
# (a Mig 140 pos SETE suites vermelhas de uma vez a 2026-09-07).
_meu3 = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
         if re.search(r"(?:^|_)(mapa|map|hub|hubs|cena|cenas|porta|portas)(?:_|\.)",
                      m, re.I)]
chk(not _meu3,
    "mapa: nenhuma migration fala do mapa — o lote e' re-render puro (%r)"
    % (_meu3,))

# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 17. A FORJA EM LOTE: a parede de 50 cartas (report [jogador] 10/09) ===")
#
# O QUE ESTA SECCAO GUARDA, e porque' ela existe:
#
# A 2026-09-12, a SERVIR E OLHAR, um lote de 50 na forja desenhava a grelha com
# `minmax(54px, 1fr)` — uma medida escrita para o QUADRADO de 54px do
# `ArtifactCellClassic`. Desde o 牌 A CARTA a mesma celula e' uma `NivraelCard`
# em RETRATO: a grelha dava-lhe 63px e a carta saia **63 x 312**, com o nome a
# UMA LETRA POR LINHA. Medido: **3003px de lista dentro de uma janela de 553px**
# (5,4 ecras), e os botoes de reciclar — a UNICA coisa que se faz com esta lista
# — por baixo dos 3003.
#
# ⚠️ A avaria comecava na 5a peca, nao na 50a (4 = 80x218 e CABE no ecra; 8 =
# 63x304). Uma guarda que so' falasse de "lotes grandes" nao apanhava a causa.
#
# ⚠️ E a causa de fundo e' de Lei F-7: toda grelha de cartas do jogo passa pelo
# `CardGrid`/`InvGrid` (min 152px); **esta era a UNICA escrita a mao**, e por
# isso foi a unica que nao soube da carta nova.
#
# ⚠️ A guarda afirma sobre o SITIO (a funcao), nunca sobre o ficheiro nem sobre
# uma janela de caracteres — a licao das duas janelas que ficaram vermelhas a
# 12/09 so' por o codigo ter ganho comentarios.
_HAS_FRM = "function ForgeResultModal(" in _TBM
chk(_HAS_FRM,
    "forja: a funcao `ForgeResultModal` existe — se ela mudar de nome, TUDO o "
    "que vem a seguir passa a comparar o vazio, e um tecto sobre o vazio e' "
    "verde para sempre")
_FRM = _fn_src(_TBM, "function ForgeResultModal(") if _HAS_FRM else ""
chk(len(_FRM) > 4000,
    "forja: a fatia e' a FUNCAO `ForgeResultModal` (%d chars), nao uma janela "
    "de caracteres que a prosa faz mentir" % len(_FRM))

# (a) a grelha pintada deixou de herdar a medida do quadrado
chk("FORGE_RESULT_CARD_MIN" in _FRM,
    "forja: a grelha usa a medida NOVA (`FORGE_RESULT_CARD_MIN`), e nao mais um "
    "54 cravado no ramo das cartas")
_CARD_MIN = re.search(r"var FORGE_RESULT_CARD_MIN = (\d+)", _TBM)
chk(_CARD_MIN is not None and int(_CARD_MIN.group(1)) >= 96,
    "forja: a coluna minima da grelha pintada e' >=96px — a 63px o nome parte-se "
    "a uma letra por linha (medido a 390x844)")

# (b) ⚠️ A ANTI-GUARDA DO RAMO OFF. Se a medida nova escapar do ternario, os 57
#     do `main` (que leem defaults, tudo OFF) recebem uma tela diferente sem que
#     ninguem tenha ligado nada. A OFF-identidade quebra-se pela ORDEM.
chk('"repeat(auto-fit, minmax(54px, 1fr))"' in _FRM,
    "forja: o ramo `cartas` OFF continua com a grelha de hoje, byte a byte")
_gi = _FRM.find("gridTemplateColumns: cardsOn")
_grid_expr = _FRM[_gi:_gi + 400] if _gi >= 0 else ""
chk("minmax(54px, 1fr)" in _grid_expr and "FORGE_RESULT_CARD_MIN" in _grid_expr,
    "forja: as DUAS medidas vivem dentro do MESMO ternario — a nova nunca chega "
    "a quem tem a flag desligada (byte a byte no ramo OFF)")

# (c) acima de N o LOTE e' o assunto: lista densa, nao 50 torres
_LIST_FROM = re.search(r"var FORGE_RESULT_LIST_FROM = (\d+)", _TBM)
chk(_LIST_FROM is not None and 4 <= int(_LIST_FROM.group(1)) <= 16,
    "forja: ha' um limiar declarado a partir do qual o lote deixa de ser cartas "
    "(4..16; e' %s)" % (_LIST_FROM.group(1) if _LIST_FROM else None))
chk("cardsOn && sortedArts.length >= FORGE_RESULT_LIST_FROM" in _FRM,
    "forja: o limiar decide de facto qual a forma que se desenha — e a lista "
    "densa so' existe no ramo onde a avaria nasceu (`cartas` ON)")

# (d) ⚠️ A LISTA NAO PODE PERDER FUNCAO. Uma 'correccao' que mostre 50 nomes mas
#     tire o cadeado e a caixa de seleccao troca uma parede por um beco: o unico
#     motivo para olhar esta lista e' reciclar o lixo (Lei §1).
_di = _FRM.find("cardsOn && sortedArts.length >= FORGE_RESULT_LIST_FROM")
_DENSE = _FRM[_di:] if _di >= 0 else ""
_dj = _DENSE.find("                ) : (")
_DENSE = _DENSE[:_dj] if _dj >= 0 else _DENSE
# ⚠️ ANTI-GUARDA DA FATIA: se o fim do ramo deixar de se encontrar, `_DENSE`
# passa a ser a funcao TODA — e as guardas de "a lista nao perdeu funcao" ficam
# verdes por estarem a ler a GRELHA, que sempre teve o cadeado e a seleccao.
chk(len(_DENSE) > 0 and "<ArtifactCell a={a}" not in _DENSE,
    "forja: a fatia da lista densa e' uma PARTE do modal e NAO engoliu a grelha "
    "(%d de %d chars) — se engolisse, as guardas seguintes ficavam verdes por "
    "estarem a aprovar a GRELHA, que sempre teve cadeado e seleccao"
    % (len(_DENSE), len(_FRM)))
for _needle, _what in (
    ("setPickedArt(a)", "abrir o detalhe da peca"),
    ("toggleLock(a)", "trancar/destrancar"),
    ("toggleSelect(a.id)", "escolher para reciclar"),
    ("{a.name}", "o NOME inteiro da peca"),
    ("a.has_spirit", "dizer qual tem espirito desperto"),
):
    chk(_needle in _DENSE,
        "forja: a lista densa mantem %s — a grelha fazia-o, a lista tem de fazer "
        "tambem" % _what)

# (e) a lista pagina, e pagina com o idioma que a casa ja' tem
chk("sortedArts.slice(0, listLimit).map" in _DENSE,
    "forja: a lista densa PAGINA de facto (corta em `listLimit`) — sem isto um "
    "lote de 50 volta a desenhar 50 de uma vez, que era a avaria")
chk("FORGE_RESULT_PAGE" in _DENSE and "inv_load_more" in _DENSE,
    "forja: e pagina com o idioma que a casa ja' tem (`inv_load_more` do Anel "
    "Espacial) — zero chave nova, zero 2a maneira de dizer a mesma coisa")

# (f) ⚠️ NENHUM EMOJI NOVO SEM PORTA. A §15 e' a catraca; isto e' o dente local,
#     porque uma lista nova e' exactamente o sitio onde eles nascem. O cadeado e
#     a marca de escolha passam pelo `ico(...)`, e o espirito diz-se em PALAVRA
#     (o ✧ e' da familia do ✦ que o jogo esta' a apagar).
chk('ico("🔒", "lock"' in _DENSE and 'ico("🔓", "lock"' in _DENSE,
    "forja: o cadeado da lista densa passa pela porta `ico(...)`")
chk('ico("✓", "check"' in _DENSE,
    "forja: a marca de escolha da lista densa passa pela porta `ico(...)`")
_DENSE_CODE = _strip_js_comments(_DENSE)
chk(u"✧" not in _DENSE_CODE and u"✦" not in _DENSE_CODE,
    "forja: a lista densa nao trouxe um ✦/✧ novo — o espirito desperto diz-se "
    "por palavra, que alem de tudo se le'")
# ⚠️ e a anti-guarda: se o `_strip_js_comments` deixasse de tirar seja o que
# for, a de cima ficava verde sobre o texto inteiro e nao guardava nada.
chk(len(_DENSE_CODE) < len(_DENSE),
    "forja: o filtro de comentarios TIROU alguma coisa da fatia densa (%d -> %d) "
    "— sem isto a guarda do glifo estaria a afirmar sobre a prosa"
    % (len(_DENSE), len(_DENSE_CODE)))

# (g) ⚠️ NAO DESFAZER O 器 O ITEM VIVO. A carta pintada fica onde a peca E' o
#     assunto. Se isto ficar vermelho, alguem 'arrumou' a grelha inteira.
chk("<ArtifactCell a={a}" in _FRM,
    "forja: a carta pintada CONTINUA a ser desenhada nos lotes pequenos — o que "
    "estava errado eram cinquenta de uma vez, nao a carta")

# (h) ⚠️ A ALQUIMIA — o report disse "i think also alchemy". MEDIDO a olhar, a
#     2026-09-12: 30 pilulas rendem **536px numa janela de 536px (zero
#     rolagem)**, porque o modal de lote da alquimia NUNCA teve lista por item.
#     Ele estava enganado, e e' bom que estivesse. A guarda fixa isso, para que
#     o dia em que alguem la' meta uma grelha de cartas fique VERMELHO.
_CRB = _fn_src(_TBM, "function CraftResultBulkModal(")
chk(len(_CRB) > 1500,
    "alquimia: a fatia e' a FUNCAO `CraftResultBulkModal` (%d chars)" % len(_CRB))
chk("ArtifactCell" not in _CRB and "NivraelCard" not in _CRB
    and "PieceIcon" not in _CRB and "pieceArt(" not in _CRB,
    "alquimia: o resultado em lote continua a ser SO' o resumo — nenhuma carta "
    "por item (medido 12/09: 30 pilulas = 536px numa janela de 536px)")
chk("bulk_pills_added" in _CRB,
    "alquimia: e o resumo diz quantas entraram, que e' a unica coisa que a tela "
    "tem de responder")

# (i) ⚠️ ZERO migration e ZERO flag nova: e' correccao de forma, como a 窗 A
#     JANELA. Escrito pelo ASSUNTO, nunca sobre "a migration mais alta do
#     repositorio" (a Mig 140 pos SETE suites vermelhas de uma vez a 07/09).
_meu4 = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
         if re.search(r"(?:^|_)(lote|bulk|resultado|result)(?:_|\.)", m, re.I)]
chk(not _meu4,
    "forja: nenhuma migration fala do lote — e' re-render puro (%r)" % (_meu4,))
_DB4 = _obj_after(rd("database/db.py"), "DEFAULT_WORLD_FEATURES")
chk("forja_em_lote" not in _DB4 and "forge_bulk" not in _DB4,
    "forja: nenhuma flag nova nasceu — a correccao vive no ramo da flag que "
    "criou a avaria (`cartas`), que e' onde ela pertence")


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 18. O GOLPE PADRAO: a tela nao pode prometer o que o motor nao faz ===")
#
# O painel onde o jogador escolhe a arte que sai sozinha quando o relogio
# dispara por ele (report do [jogador], 10/09 09:59). As guardas aqui sao TODAS sobre
# honestidade, porque e' a unica coisa que uma tela de preferencia pode errar:
# guardar uma escolha que o motor nao vai cumprir.
_HAS_DSP = "function DefaultStrikePicker(" in _TBM
chk(_HAS_DSP,
    "golpe: a funcao `DefaultStrikePicker` existe — se mudar de nome, tudo o "
    "que vem a seguir compara o vazio (e uma guarda que REBENTA diz que o "
    "teste esta' errado, nao o codigo)")
_DSP = _fn_src(_TBM, "function DefaultStrikePicker(") if _HAS_DSP else ""
chk(len(_DSP) > 1500,
    "golpe: a fatia e' a FUNCAO `DefaultStrikePicker` (%d chars)" % len(_DSP))

# ⚠️ O BLOCO SO' EXISTE QUANDO O SERVIDOR O MANDA. A tela nao decide se a
# feature existe — a AUSENCIA do bloco e' a resposta. Se isto ficar vermelho, o
# painel nasce em todo mundo, incluindo nos 57 do `main`.
chk("{data.default_strike && (" in _TBM,
    "golpe: o painel so' nasce quando o servidor manda o bloco (flag ON) — com "
    "ela OFF a seccao das Equipadas e' a de hoje, byte a byte")

# ⚠️ A ESCOLHA MORTA. Se o id gravado ja' nao esta' equipado, o motor dispara o
# golpe basico — e a tela TEM de mostrar o golpe basico, nunca a escolha morta.
# Mostrar a escolha morta seria a tela a prometer o que o motor nao cumpre, que
# e' a unica forma de uma tela de preferencia mentir.
chk("{!!ds.stored && ds.stored !== cur && (" in _DSP and "gp_stale" in _DSP,
    "golpe: quando a arte escolhida deixou de estar equipada, a tela DIZ que "
    "por agora sai o basico — em vez de mostrar uma escolha que o motor ignora")

# ⚠️ A PROIBIDA FICA DE FORA **E DIZ-SE**. Escondida em silencio, o jogador
# procurava a arte mais forte que tem, nao a encontrava, e concluia que a tela
# esta' avariada (Lei §1: nunca um beco mudo).
chk("{ds.forbidden_hidden > 0 && (" in _DSP and "gp_forbidden_hidden" in _DSP,
    "golpe: a arte do Caminho Proibido fica de fora E a tela diz que ficou, e "
    "porque' — esconder em silencio e' que seria o beco")

# O golpe basico continua a ser uma ESCOLHA, e vem primeiro: e' o que o jogo faz
# hoje, e quem estiver bem assim tem de o poder reencontrar.
chk('{ id: 0, name: t("gp_basic")' in _DSP,
    "golpe: o golpe basico e' a primeira opcao — voltar atras tem de ser tao "
    "facil como avancar")

# O erro do servidor chega ao jogador NOMEADO, nunca como "erro".
chk("gp_err_forbidden" in _DSP and "gp_err_not_equipped" in _DSP,
    "golpe: as duas recusas do servidor tem mensagem PROPRIA — 'nao deu' nao "
    "diz ao jogador o que fazer a seguir")

# ⚠️ A FILA QUE CULPAVA O ELO. `pool_empty` so' chega com a flag ligada; sem
# ela, a linha de sempre. E o ramo novo tem de existir mesmo.
_AQW = _fn_src(_TBM, "function ArenaQueueWidget(")
chk("status.pool_empty" in _AQW and "combat_arena_q_waiting_solo" in _AQW,
    "arena: a fila diz POR QUEM se espera quando nao ha' mais ninguem nela")
chk("combat_arena_q_waiting_meta" in _AQW,
    "arena: e o ramo de sempre continua la' — se ele sumisse, a guarda de cima "
    "estaria verde sobre uma tela que perdeu o caso normal")

# As chaves, nas tres linguas (o verificador da casa).
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    for _k in ("gp_title", "gp_hint", "gp_basic", "gp_stale",
               "gp_forbidden_hidden", "combat_arena_q_waiting_solo"):
        chk(_k in _d and len(_d[_k]) > 3,
            "golpe: a chave `%s` existe em %s" % (_k, _lang))


# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 18. 🩸 O HP A ZERO: a recusa que diz o caminho, e a barra que tem nome ===")
#
# PORQUE' ESTA SECCAO EXISTE, e o que ela guarda:
#
# O prompt de 14/09 trazia um numero herdado — *"activos-7d com HP<=0: 9 de 13
# no s2 (69%), 5 de 16 no main (31%)"* — e mandava responder se era problema de
# RECUPERACAO ou de DANO. Medido em producao a 2026-09-13
# (`tools/db_readonly_hp_0913*.py`): **nem um nem outro.** O numero era FALSO.
#
# O probe de 12/09 escreveu `COALESCE(current_hp, 0) <= 0` — e `current_hp`
# NULL significa **CHEIO**, nao morto (`combat_engine.get_current_hp`: *"NULL in
# DB means full HP"*). Os "69%" eram os NOVE jogadores com a barra INTEIRA.
# Re-medido: **ZERO** activos-7d a zero nos dois mundos; 3 de 241 no main em
# toda a historia, o mais recente visto ha' 10 dias.
#
# ⚠️ E' a familia *"uma medicao certa sobre a coisa errada"*. Por isso a 1a
# guarda desta seccao afirma sobre o CODIGO DE PRODUCAO: ninguem pode voltar a
# tratar NULL como zero num gate.
#
# O que SOBREVIVEU da investigacao foi outra coisa, e essa era real: a
# superficie CANONICA mandava o jogador ESPERAR.

# ── 18a. 🔴 NULL NAO E' ZERO — em codigo de producao ──────────────────────
# 🔴 A GUARDA LE' O CODIGO, NUNCA A PROSA — e esta funcao existe porque ela
# JA' falhou assim, aqui, hoje. A 1a versao varria o ficheiro inteiro e acusou
# `core/webserver.py:5985`… que era **o comentario que eu tinha acabado de
# escrever a explicar o bug**, com a forma do bug citada la' dentro. E' a 5a
# recorrencia medida desta familia (quatro delas num so' lote a 13/09) e a mais
# ironica de todas: a prosa que documenta a correccao fez a guarda acusar a
# correccao.
def _sem_prosa_py(src):
    """Apaga comentarios `#`, PRESERVANDO os \\n (os numeros de linha tem de bater)."""
    out = []
    for _ln in src.split("\n"):
        _q = None
        _cut = None
        _i = 0
        while _i < len(_ln):
            _c = _ln[_i]
            if _q:
                if _c == "\\":
                    _i += 2
                    continue
                if _c == _q:
                    _q = None
            elif _c in "\"'":
                _q = _c
            elif _c == "#":
                _cut = _i
                break
            _i += 1
        out.append(_ln if _cut is None else _ln[:_cut])
    return "\n".join(out)


# ⚠️ ANTI-GUARDA: o filtro TEM de filtrar, e TEM de nao filtrar a mais. Se ele
# deixasse de apagar comentarios, a guarda voltava a acusar prosa; se apagasse
# codigo, ficava verde sobre o ficheiro vazio. As duas avarias sao a mesma, ao
# contrario uma da outra — e foi o modo de falha de 13/09 ("sabotei a trava
# inteira e ela ficou VERDE").
chk("current_hp" not in _sem_prosa_py("# nota: player.current_hp or 0 era o erro"),
    "hp: o filtro de comentarios APAGA mesmo a prosa — sem ele a guarda do NULL "
    "acusa o comentario que explica o bug (aconteceu hoje)")
chk("current_hp" in _sem_prosa_py("cur = float(player.current_hp or 0)"),
    "hp: e o filtro NAO apaga codigo — um filtro que apagasse tudo deixava a "
    "guarda verde sobre o vazio, que e' a mesma avaria ao contrario")
chk(_sem_prosa_py("a = 1\n# x\nb = 2").count("\n") == 2,
    "hp: o filtro preserva as LINHAS — sem isso o numero que a guarda imprime "
    "manda o proximo leitor ao sitio errado com confianca")

_hp_null_zero = []
_hp_lidos = 0
for _dirp, _dirs, _files in os.walk(ROOT):
    # relativo a' RAIZ (a licao da F2): com o caminho absoluto, um clone numa pasta
    # `tmp`/`tools`/`dist` saltava a arvore inteira. E `nivrael-community/` e' a
    # edicao comunitaria quando vive dentro desta arvore: outro projecto, com o
    # seu proprio codigo — le-la aqui duplicava cada achado.
    _rel = os.path.relpath(_dirp, ROOT).replace(os.sep, "/")
    if _rel.split("/")[0] == "nivrael-community" or any(
            _x in _rel for _x in ("__pycache__", "node_modules", ".git", "tmp",
                                  "tools", "scripts", "dist", "Cerebro", "Prompts")):
        continue
    for _f in _files:
        if not _f.endswith((".py", ".sql")):
            continue
        _fp = os.path.join(_dirp, _f)
        try:
            _src = io.open(_fp, encoding="utf-8").read()
        except Exception:
            continue
        _hp_lidos += 1
        _src = _sem_prosa_py(_src)
        # ⚠️ O padrao aponta ao `current_hp` DO JOGADOR. O `world_bosses`
        # tem uma coluna com o MESMO nome cuja semantica e' outra (NOT NULL, e
        # zero quer mesmo dizer morto), e a 1a versao desta guarda acusou-a: um
        # falso positivo e' tao corrosivo como um falso verde, porque ensina a
        # proxima pessoa a ignorar a guarda.
        for _m in re.finditer(
                r"COALESCE\(\s*(?:p|player|target)?\.?\s*current_hp\s*,\s*0"
                r"|(?<!boss\.)(?<!_boss\.)current_hp\s+or\s+0", _src, re.I):
            _hp_null_zero.append("%s:%s" % (os.path.relpath(_fp, ROOT),
                                            _src[:_m.start()].count("\n") + 1))
chk(_hp_null_zero == [],
    "hp: nenhum codigo de PRODUCAO trata `current_hp` NULL como zero. NULL "
    "significa CHEIO (`get_current_hp`), e confundir os dois transforma quem "
    "esta' de barra inteira em quem esta' morto — foi exactamente isso que "
    "produziu o falso '69%% dos activos do s2 sem poder lutar' de 12/09. "
    "Encontrado em: %r" % (_hp_null_zero,))
# anti-guarda: o padrao continua a APANHAR a forma que causou o bug de 12/09 —
# sem isto, o estreitamento acima podia ter matado a guarda inteira em silencio.
_iscas = ["COALESCE(current_hp, 0) <= 0", "cur = float(player.current_hp or 0)"]
for _isca in _iscas:
    chk(len(re.findall(
            r"COALESCE\(\s*(?:p|player|target)?\.?\s*current_hp\s*,\s*0"
            r"|(?<!boss\.)(?<!_boss\.)current_hp\s+or\s+0", _isca, re.I)) == 1,
        "hp: o padrao do NULL ainda apanha a forma real do bug (%r) — um regex "
        "estreitado a mais e' um verde permanente" % _isca)
chk(len(re.findall(
        r"COALESCE\(\s*(?:p|player|target)?\.?\s*current_hp\s*,\s*0"
        r"|(?<!boss\.)(?<!_boss\.)current_hp\s+or\s+0",
        "hp_pct = round(100 * (boss.current_hp or 0) / boss.hp)", re.I)) == 0,
    "hp: e NAO apanha o `current_hp` do CHEFE MUNDIAL, que e' outra coluna com "
    "outra semantica — um falso positivo ensina a ignorar a guarda")

chk(_hp_lidos > 40,
    "hp: a varredura do NULL leu %d ficheiros — a zero, a guarda de cima "
    "ficava verde sobre o conjunto vazio" % _hp_lidos)

# ── 18b. A RECUSA DIZ O CAMINHO, e tem UM DONO ────────────────────────────
_HPMSG = _fn_src(_UIM, "function hpDepletedMsg(")
chk(bool(_HPMSG) and 'safeT("combat_hp_way_out")' in _HPMSG,
    "hp: `hpDepletedMsg()` existe e junta a frase do CAMINHO DE SAIDA — o "
    "contexto muda (npc/fila/pvp/Eco), o caminho nao")
chk(len(re.findall(r"function\s+hpDepletedMsg\s*\(", _UIM + _TBM)) == 1,
    "hp: existe UMA definicao de `hpDepletedMsg` em todo o cliente — duas "
    "ligacoes a' mao divergem sempre (Lei 0 passo 2)")
_RECUSAS = ("combat_npc_hp_depleted", "combat_arena_q_err_hp",
            "combat_pvp_hp_depleted", "lgc_mini_hp")
for _k in _RECUSAS:
    chk(('hpDepletedMsg("%s")' % _k) in _TBM,
        "hp: a recusa `%s` passa pelo dono unico (e nao por um `t()` cru que "
        "diria o facto sem dizer o que fazer)" % _k)
    chk(('t("%s")' % _k) not in _TBM,
        "hp: a recusa `%s` NAO tem nenhuma chamada crua sobrevivente — uma "
        "so' basta para o beco voltar num dos quatro sitios" % _k)
chk('hpDepletedMsg("combat_pvp_challenger_hp_depleted")' not in _TBM
    and 't("combat_pvp_challenger_hp_depleted")' in _TBM,
    "hp: a recusa do DESAFIANTE nao manda VOCE meditar — a vitalidade que esta' "
    "a zero e' a dele, e mandar-lhe um conselho seria a tela a mentir")

# ── 18c. O CAMINHO NOMEIA ACCOES QUE EXISTEM, nas 3 linguas ───────────────
_ACCOES = {"pt": ("medit", "ílula"), "en": ("medit", "pill"), "es": ("medit", "íldora")}
_ESPERAR = {"pt": "espere", "en": "wait to regenerate", "es": "espera a regenerar"}
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    chk("combat_hp_way_out" in _d,
        "hp: a frase do caminho existe em %s" % _lang)
    _txt = _d.get("combat_hp_way_out", "").lower()
    for _needle in _ACCOES[_lang]:
        chk(_needle in _txt,
            "hp: o caminho de saida em %s nomeia `%s` — uma recusa que nao "
            "nomeia uma accao REAL do motor e' um beco com boas maneiras "
            "(Lei §1). Lido: %r" % (_lang, _needle, _txt))
    for _k in _RECUSAS:
        chk(_ESPERAR[_lang] not in _d.get(_k, "").lower(),
            "hp: a recusa `%s` em %s nao manda ESPERAR — esperar e' o caminho "
            "mais lento que o motor oferece (0,1%%/min, tecto ~24%% por visita), "
            "enquanto a meditacao profunda enche a barra em 20 minutos e o chat "
            "ja' dizia o certo desde sempre" % (_k, _lang))

# ── 18d. A BARRA DIZ O QUE E' ─────────────────────────────────────────────
# 🔴 E O MESMO ERRO OUTRA VEZ, NO MESMO LOTE — a bateria apanhou-o.
# A guarda "o efeito sobreviveu" procurava `orb-burst` no corpo da `HubEuScreen`
# e ENCONTRAVA-O **no comentario que eu escrevi a explicar que o efeito
# sobreviveu**. Sabotei a animacao inteira (`orb-burst` -> `"none"`) e ela ficou
# VERDE. E' a 3a recorrencia desta familia hoje, e a 2a de forma identica a' de
# 13/09 (*"procurava `is_forbidden` e encontrava-o no comentario que explica
# porque a arte proibida nao dispara"*).
#
# ⇒ Toda afirmacao sobre CODIGO JS nesta seccao le' a fonte SEM PROSA.
def _sem_prosa_js(src):
    """Apaga `//` e `/* */`, PRESERVANDO os \\n (as contagens tem de bater)."""
    out, i, n, q = [], 0, len(src), None
    while i < n:
        c = src[i]
        if q:
            out.append(c)
            if c == "\\":
                if i + 1 < n:
                    out.append(src[i + 1])
                i += 2
                continue
            if c == q:
                q = None
            i += 1
            continue
        if c in "\"'`":
            q = c
            out.append(c)
            i += 1
            continue
        if src[i:i + 2] == "//":
            j = src.find("\n", i)
            j = n if j < 0 else j
            i = j
            continue
        if src[i:i + 2] == "/*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * src[i:j].count("\n"))
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


# ⚠️ ANTI-GUARDA do filtro JS — as duas direccoes, como a do Python.
chk("orb-burst" not in _sem_prosa_js("// o orb-burst sobrevive\nx = 1;"),
    "hp: o filtro de prosa JS apaga `//` — sem ele a guarda do efeito ficou "
    "VERDE com a animacao sabotada (aconteceu hoje, apanhado pela bateria)")
chk("orb-burst" not in _sem_prosa_js("/* nota:\n   orb-burst */\nx = 1;"),
    "hp: o filtro de prosa JS apaga `/* */` — e' onde vivem os comentarios JSX")
chk('animation:"orb-burst"' in _sem_prosa_js('animation:"orb-burst" // nota'),
    "hp: e o filtro NAO apaga codigo nem o conteudo das strings — apagar tudo "
    "deixava a guarda verde sobre o vazio, a mesma avaria ao contrario")

_LBAR = _fn_src(_UIM, "function LabeledBar(")
chk(bool(_LBAR) and "ProgressBar" in _LBAR,
    "hp: `LabeledBar` existe e desenha por cima do `ProgressBar` — o dono unico "
    "de 'uma barra com significado'")
_HUBEU_RAW = _fn_src(_TBM, "function HubEuScreen(")
_HUBEU = _sem_prosa_js(_HUBEU_RAW)
chk(bool(_HUBEU), "hp: a tela do hub EU foi encontrada pelo nome")
chk(len(_HUBEU) > 0.25 * max(1, len(_HUBEU_RAW)),
    "hp: o filtro deixou %d de %d chars da tela do hub EU — se ele comesse "
    "quase tudo, todas as guardas abaixo ficavam verdes sobre o vazio"
    % (len(_HUBEU), len(_HUBEU_RAW)))
chk(_HUBEU.count("<LabeledBar") == 3,
    "hp: as TRES barras do hub EU tem rotulo (lidas %d) — uma barra sem nome "
    "nao e' uma barra, e a que faltava era justamente a Vitalidade"
    % _HUBEU.count("<LabeledBar"))
chk("<ProgressBar" not in _HUBEU,
    "hp: nenhuma barra NUA sobreviveu no hub EU — bastava uma para o defeito "
    "voltar no sitio de onde veio")
chk('safeT("hub_eu_bar_vitality")' in _HUBEU,
    "hp: a barra da Vitalidade e' nomeada pela chave propria (e nao por um "
    "literal, que nao teria as tres linguas)")
for _lang in ("pt", "en", "es"):
    _d = _json.loads(rd("miniapp/i18n/%s.json" % _lang))
    chk("hub_eu_bar_vitality" in _d and len(_d["hub_eu_bar_vitality"]) > 3,
        "hp: o rotulo da Vitalidade existe em %s" % _lang)

# ── 18e. 坐 O ORBE: nenhuma esfera escrita a' mao sobreviveu ───────────────
# A ordem do owner (07/09, textual): *"esse orb nao gostei nada, muito AI"*. A
# 07/09 morreu no Cultivo; a 09/09 no cabecalho. Ficaram DOIS escritos a' mao —
# o heroi do hub EU (150px, com um EMOJI DO SISTEMA ao centro) e a bolinha do
# ProfileModal que ele abria. A familia F-7 inteira numa so' interaccao.
_RX_ESFERA = (r'borderRadius:\s*"50%"[\s\S]{0,340}?radial-gradient\(circle'
              r'[\s\S]{0,460}?realm_emoji')
_esferas = re.findall(_RX_ESFERA, _TBM)
chk(_esferas == [],
    "hp/orbe: nenhuma esfera de `radial-gradient` com `realm_emoji` ao centro "
    "sobreviveu no `tabs.js` (%d) — `RealmAvatar` e' o dono unico da bolinha do "
    "reino desde 09/09, e uma copia a' mao diverge sempre" % len(_esferas))
_falso = ('borderRadius:"50%", background:`radial-gradient(circle at 30% 30%, '
          '${rc}, transparent 70%)`}}><span>{data.realm_emoji}</span>')
chk(len(re.findall(_RX_ESFERA, _falso)) == 1,
    "hp/orbe: o localizador de esferas ENCONTRA uma esfera quando ela existe — "
    "sem esta anti-guarda, um regex partido dava verde para sempre")
_n_ra = len(re.findall(r"<RealmAvatar\b", _HUBEU))
chk(_n_ra == 1 and "realm_emoji" not in _HUBEU,
    "hp/orbe: o heroi do hub EU e' o `RealmAvatar` (o 坐 com o anel do reino), "
    "que e' o que o cabecalho ja' decidiu a 09/09 pelo mesmo motivo — e NAO "
    "pode ser o `CultivatorFigure`, cuja lei e' que a figura so' existe SENTADA "
    "(lidos %d `<RealmAvatar` e emoji-do-sistema=%s). ⚠️ A fronteira `\b` no "
    "padrao nao e' cosmetica: `<RealmAvatarX` COMECA por `<RealmAvatar`, e foi "
    "assim que a sabotagem do rename passou verde a' primeira"
    % (_n_ra, "realm_emoji" in _HUBEU))
chk("orb-breathe" in _HUBEU and "orb-burst" in _HUBEU,
    "hp/orbe: a respiracao e o pulso da subida de Poder SOBREVIVERAM a troca — "
    "o orbe morreu, o que ele fazia nao")
chk("function _realmAvatarTone(" in _UIM,
    "hp/orbe: `RealmAvatar` deriva o tom para tamanhos fora da tabela — sem "
    "isso o heroi de 150px desenhava a marca no tamanho de um avatar de 34")

# ── 18f. O ARRANQUE NAO PODE PENDURAR (achado da auditoria externa) ───────
# ⚠️ O `catch` por lingua ja' salvava o 404 e o erro de rede; o que nao salvava
# era o pedido PENDURADO — `Promise.all` nunca resolve, o `.finally()` nunca
# dispara, e o `createRoot().render()` nunca corre: ecra em BRANCO, sem erro,
# para sempre. E' o pior beco que existe, porque nem ha' tela onde escrever.
_APPM = rd("miniapp/components/app.js")
_LOADI = _fn_src(_APPM, "async function _loadI18n(")
chk(bool(_LOADI), "hp/arranque: `_loadI18n` foi encontrada pelo nome")
chk("AbortController" in _LOADI and "setTimeout" in _LOADI,
    "hp/arranque: cada lingua tem RELOGIO e aborta — um `fetch` que nunca "
    "resolve deixava o mini-app em branco para sempre (Lei §1)")
chk("clearTimeout" in _LOADI,
    "hp/arranque: o relogio e' limpo no `finally` — sem isso ficava um abort "
    "agendado por cima de um pedido que ja' chegou")
chk(re.search(r"_loadI18n\(\)\s*\n?\s*\.finally", _APPM) is not None
    or re.search(r"_loadI18n\(\)\.finally", _APPM) is not None,
    "hp/arranque: o `render()` corre no `finally` — mesmo com as tres linguas "
    "em falha o jogo ABRE (o `t()` degrada por token)")

# ⚠️ Escrito pelo ASSUNTO. "hp" e' palavra velha do dominio (ha' migrations de
# combate desde 2024): a pergunta e' se ESTE lote mexeu na base de dados.
_meu4 = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
         if re.search(r"(?:^|_)(vitalidade|hp_zero|hp_caminho|recusa)(?:_|\.)", m, re.I)]
chk(not _meu4,
    "hp: nenhuma migration — o lote e' texto, render e uma varredura de leitura "
    "(%r)" % (_meu4,))



# ═══════════════════════════════════════════════════════════════════════════
# 19. 坐 O CULTIVADOR JOGAVEL — a onda 1 (desenho do Astra, MESA [011])
# ═══════════════════════════════════════════════════════════════════════════
# O lote tem tres metades e cada uma tinha um defeito MEDIDO, nao suposto:
#
#   S3  o cliente desenhava **4** modalidades e o servidor aceita **7**. As
#       tres em falta (`dao_basic` R5, `dao_deep` R6, `dao_transcend` R8) sao
#       conteudo que o jogador destranca ao subir de reino e que a superficie
#       canonica NUNCA lhe mostrou. Duas listas, dois donos, e divergiram em
#       3 de 7 (Lei 0 §2).
#   S2  os numeros passavam pelo `fmtNum`, que ABREVIA. O `current_hp` de
#       producao tem **12 digitos** e o jogador lia `158.98B`.
#   S1  o erro escrevia a palavra crua do servidor. Um 401 no mini-app e'
#       `_err("unauthorized", 401)`, portanto quem perdia a sessao lia
#       literalmente **"unauthorized"**, num ecra sem um unico botao.
#
# ⚠️ Estas guardas perguntam pelo SITIO, nunca pelo ficheiro (licao de 09/09: 3
# de 9 guardas ficaram verdes por afirmarem sobre o ficheiro). E leem o CODIGO,
# nunca a prosa (`_sem_prosa_*`) — a familia de erro que ja' custou 5
# recorrencias medidas.
print("\n=== 19. 坐 O CULTIVADOR JOGAVEL: a onda 1 ===")

_UIC = _sem_prosa_js(_UI)
_TBC = _sem_prosa_js(_TABS)
_APC = _sem_prosa_js(_APPM)
_WEBC = _sem_prosa_py(rd("core/webserver.py"))
# ⚠️ O cru, com as STRINGS: o dono das travas atribui os codigos como
# literais, e o `_sem_prosa_py` apaga-os.
_WEB_CRU = rd("core/webserver.py")

# ── 19a — O CATALOGO TEM UM DONO, e o dono e' o `config.py` ────────────────
# A prova nao e' "existe um catalogo" — e' que ele diz o MESMO que o validador
# do `start`. Comparar com o `config.py` importado (nao com uma copia escrita
# aqui) e' o que impede esta guarda de virar o terceiro dono.
sys.path.insert(0, ROOT)
from config import MEDITATION_TYPES as _MT, DAO_MEDITATION_TYPES as _DMT  # noqa: E402

_esperadas = set(_MT) | set(_DMT)
chk(len(_esperadas) == 7,
    "onda1/S3: o `config.py` tem %d modalidades (esperava 7 — se subiu, o "
    "catalogo do servidor tem de as levar todas)" % len(_esperadas))

chk("def _meditation_catalog" in _WEBC,
    "onda1/S3: `_meditation_catalog` existe em `core/webserver.py` — o catalogo "
    "sai do `config.py`, nunca de uma lista escrita a mao no cliente")

# ⚠️ A guarda MEDE: importa e compara campo a campo. Um catalogo que perdesse
# uma modalidade, ou que mentisse num custo, fica vermelho AQUI.
try:
    import importlib as _il
    _wsmod = _il.import_module("core.webserver")
    _cat = _wsmod._meditation_catalog()
except Exception as _e:          # pragma: no cover — o import e' a prova
    _cat = []
    chk(False, "onda1/S3: `_meditation_catalog()` nao correu (%s)" % _e)

chk(len(_cat) == 7,
    "onda1/S3: o catalogo devolve %d linhas, nao 7 — o cliente desenhava 4 e "
    "por isso 3 praticas destrancadas nunca chegavam a tela" % len(_cat))
chk(set(r["key"] for r in _cat) == _esperadas,
    "onda1/S3: as chaves do catalogo sao EXACTAMENTE as do `config.py` "
    "(falta/sobra: %r)" % (set(r["key"] for r in _cat) ^ _esperadas,))
for _r in _cat:
    _src = _MT.get(_r["key"]) or _DMT.get(_r["key"]) or {}
    chk(_r["qi_cost"] == int(_src.get("qi_cost", 0))
        and _r["min_realm"] == int(_src.get("min_realm", 0))
        and _r["duration_minutes"] == int(_src.get("duration_minutes", 0)),
        "onda1/S3: `%s` no catalogo NAO bate com o `config.py` — duas verdades "
        "para o mesmo custo e' a Lei 0 §2 a repetir-se" % _r["key"])
# ⚠️ Ausente e' AUSENTE: `dao_fragment_mult` nao existe nas tres primeiras e a
# linha nao inventa um x1 que ninguem mediu.
chk(all((r["dao_fragment_mult"] is None)
        == (( _MT.get(r["key"]) or _DMT.get(r["key"]) or {}).get("dao_fragment_mult") is None)
        for r in _cat),
    "onda1/S3: `dao_fragment_mult` ausente continua ausente no catalogo")

# ── 19b — O CLIENTE LE O CATALOGO, nao uma lista sua ──────────────────────
chk("catalog={data.meditation_catalog}" in _TBC,
    "onda1/S3: o `MeditationCard` recebe o catalogo DO SERVIDOR "
    "(`data.meditation_catalog`) — nunca uma lista literal")
_mc = _UIC[_UIC.find("function MeditationCard"):]
_mc = _mc[:_mc.find("\n    }\n")] if "\n    }\n" in _mc else _mc
chk(bool(_mc), "onda1/S3: `MeditationCard` foi encontrada em `ui.js`")
chk("medTypes" not in _mc,
    "onda1/S3: o cartao novo NAO toca na lista velha `medTypes` — foi ela que "
    "escondeu 3 das 7 praticas")
chk(_mc.count("min_realm") >= 2 and "qi_cost" in _mc,
    "onda1/S3: o cadeado de cada linha le `min_realm`/`qi_cost` do catalogo "
    "servido, nao um numero escrito no cliente")

# ── 19c — OS CINCO ERROS DO `start` tem CADA UM a sua frase ────────────────
# ⚠️ MEDIDO no endpoint: sao estes cinco e nao outros. A guarda le os `_err(...)`
# do proprio `api_meditate_start` — assim, um erro NOVO no servidor sem frase no
# cliente fica vermelho, em vez de sair como uma string crua ao jogador.
_ms = _WEBC[_WEBC.find("async def api_meditate_start"):]
_ms = _ms[:_ms.find("async def api_meditate_stop")]
# 🔴 2026-09-21 — A GUARDA SEGUE AS DUAS FORMAS DE RECUSAR, e e' o bug do [jogador]
# um nivel acima. O servidor recusa por DOIS caminhos: `_err("x")` e
# `_json({"ok": False, "reason": "x"})`. Esta guarda so' lia o primeiro —
# e as duas recusas da Celestial (`heavenly_laws_complete`,
# `needs_first_trial`) saem pelo SEGUNDO. Ficou verde enquanto elas chegavam
# CRUAS ao jogador. Uma guarda que so' olha para metade da superficie nao
# guarda a outra metade (licao `a guarda estrutural segue a indireccao`).
# ⚠️ E segue a INDIRECCAO: desde 21/09 o `start` delega duas recusas no dono
# `_travas_da_meditacao` (a mesma que o `dao/meditate_start` e o catalogo
# usam). Um regex que so' lesse o corpo do `start` deixava de as ver e a
# guarda voltava a ficar verde com elas cruas — que foi exactamente o que
# aconteceu antes, por outro caminho.
_tv = _WEB_CRU[_WEB_CRU.find("async def _travas_da_meditacao"):]
_tv = _tv[:_tv.find("async def api_cultivation")]
_codigos = (set(re.findall(r'_err\("([a-z_]+)"', _ms))
            | set(re.findall(r'= "([a-z_]+)"', _tv)))
chk("_travas_da_meditacao(session, player, user_id)).get(med_key)" in _ms,
    "onda1/S3: o `start` pergunta ao MESMO dono das travas que o "
    "`dao/meditate_start` — dois endpoints, uma regra")
chk(_codigos == {"invalid_meditation_type", "player_not_found",
                 "realm_too_low", "already_meditating", "not_enough_qi",
                 "heavenly_laws_complete", "needs_first_trial"},
    "onda1/S3: os codigos de recusa do `start` mudaram (%r) — a tabela do "
    "cliente tem de mudar com eles" % sorted(_codigos))
for _c in sorted(_codigos):
    chk(("%s: \"onda_med_err_" % _c) in _UIC or ("%s:" % _c) in _UIC,
        "onda1/S3: a recusa `%s` nao tem frase propria no cartao — sem ela o "
        "jogador le a palavra crua do servidor" % _c)
_tab_err = _UIC[_UIC.find("var _MED_ERR_KEY"):]
_tab_err = _tab_err[:_tab_err.find("};") + 2]
chk(set(re.findall(r"(\w+): \"onda_med_err", _tab_err)) == _codigos,
    "onda1/S3: a tabela `_MED_ERR_KEY` cobre EXACTAMENTE os codigos do "
    "servidor (tem %r)" % sorted(re.findall(r"(\w+): \"onda_med_err", _tab_err)))

# ── 19d — S2: o numero INTEIRO, nunca abreviado ───────────────────────────
_syn = _UIC[_UIC.find("function CultivationSynthesis"):]
_syn = _syn[:_syn.find("\n    // ─── S3")] if "\n    // ─── S3" in _syn else _syn[:20000]
chk(bool(_syn), "onda1/S2: `CultivationSynthesis` foi encontrada")
chk("fmtNum(" not in _syn,
    "onda1/S2: a cena NAO usa `fmtNum` — ele abrevia (`20.67B`), e o HP de "
    "producao tem 12 digitos: o jogador ficava sem saber quanto tem")
chk(_syn.count("fmtFull(") >= 6,
    "onda1/S2: os seis numeros (HP/Qi/CB, atual+maximo) passam pelo `fmtFull`")
chk("toLocaleString" in _UIC and "useGrouping" in _UIC,
    "onda1/S2: `fmtFull` agrupa pela LINGUA (`Intl`), nunca por concatenacao")

# ⚠️ NULL e' CHEIO. Um `COALESCE(current_hp, 0)` ja' inventou "69% dos activos
# sem poder lutar"; re-medido, eram zero. A resolucao vive num sitio so'.
chk(re.search(r"hpNow === null \|\| hpNow === undefined\) \? maxHp", _syn) is not None,
    "onda1/S2: `current_hp` NULL resolve para o MAXIMO (cheio), nunca para 0")
chk("Number(hpNow) || 0" not in _syn,
    "onda1/S2: ninguem faz `Number(hpNow) || 0` — isso transformaria o NULL "
    "'cheio' num zero 'morto'")

# ── 19e — as DUAS barras aguentam mais de 100% ────────────────────────────
chk("qiOver = qiM > 0 && qiN > qiM" in _syn,
    "onda1/S2: o transbordo do Qi e' DETECTADO (medido: 2,08x acima da "
    "capacidade num jogador real)")
chk("onda_qi_over" in _syn,
    "onda1/S2: o transbordo e' DITO em palavras, com o multiplicador — uma "
    "barra a 100% apagaria o unico facto interessante da linha")
chk("cbOver = cbM > 0 && cbN > cbM" in _syn,
    "onda1/S2: o transbordo da Base de Cultivo tambem e' detectado (10 digitos "
    "contra um limiar de 9 no apice)")
_pb = _UIC[_UIC.find("function ProgressBar"):]
_pb = _pb[:_pb.find("\n    function ", 10)]
chk("over=false" in _pb,
    "onda1/S2: o `over` do `ProgressBar` e' ADITIVO (default `false`) — os 14 "
    "usos de hoje desenham o mesmo markup")

# ── 19f — CB NAO E' PODER DE COMBATE (a correccao da MESA [012]) ──────────
# ⚠️ `get_threshold` nao ve combate nenhum e o servidor compara a
# `cultivation_base`. Por o `display_combat_power` ao lado do limiar faria a
# barra mentir — sao grandezas diferentes.
# 🔴 A fatia é a CHAMADA DA ONDA, não o ficheiro. A 1a versao perguntava
# `"cbNow={data.cultivation_base}" in _TBC` -- e essa string existe DUAS vezes
# no `tabs.js` (o ramo da onda e o da `cena_cultivo`). A sabotagem trocou a da
# ONDA pelo Poder de Combate e a guarda ficou VERDE, por ter encontrado a do
# outro ramo. E' a familia "conta o que EXISTE, nao o que CHEGA".
_syncall = _TBC[_TBC.find("<CultivationSynthesis"):]
_syncall = _syncall[:_syncall.find("/>") + 2]
chk(200 < len(_syncall) < 2000,
    "onda1/S2: a chamada da cena foi delimitada (%d chars)" % len(_syncall))
chk("cbNow={data.cultivation_base}" in _syncall
    and "cbMax={data.cb_threshold}" in _syncall,
    "onda1/S2: a barra do avanco compara `cultivation_base` com `cb_threshold` "
    "— NUNCA o Poder de Combate (MESA [012])")
chk(re.search(r"combatPower[^\n]*\n[^\n]*progressao_visivel", _TBC) is not None,
    "onda1/S2: o Poder de Combate so' e' passado quando o mundo o calcula "
    "(`progressao_visivel`); com a flag OFF vem `null`")
# ⚠️ 2026-09-16 ([013] §B.3): o Poder MUDOU DE CASA — saiu da coluna dos
# recursos e passou a leitura secundaria junto a' IDENTIDADE, de proposito
# LONGE do limiar. A guarda segue-o; ficar a apontar para a cena seria uma
# guarda a olhar para o sitio de onde a coisa saiu.
_idt = _UIC[_UIC.find("function CultIdentity"):]
_idt = _idt[:_idt.find("function CultAnchors")]
chk(len(_idt) > 500, "onda1/S2: `CultIdentity` foi delimitada (%d chars)" % len(_idt))
chk("combatPower != null ?" in _idt,
    "onda1/S2: sem Poder de Combate a linha NAO EXISTE — nao fica um buraco "
    "nem um zero inventado")
# ⚠️ 2026-09-16 ([013] §B.3): a Base de Cultivo deixou de ser um `CultBlock`
# igual aos outros e virou o FECHO da progressao — logo ja' nao ha' `minH={88}`
# onde a fatia acabava. Acaba agora no CTA, que e' o fim real do conjunto.
# A fatia continua delimitada pela ESTRUTURA, nunca a um numero
# de caracteres a olho: uma janela fixa engolia o bloco SEGUINTE e a guarda
# ficava vermelha por ler codigo que nao e' o dela.
_cb_i = _syn.find("onda_cb_label")
_cb_j = _syn.find("{cta}", _cb_i)
# ⚠️ `> 400` e nao `> _cb_i`: uma fatia de 10 caracteres tambem satisfaz a
# ordem, e todas as perguntas abaixo ficariam verdes sobre um pedaco VAZIO
# (a licao de 08/09, `set() <= {...}`). O tamanho e' a anti-guarda.
chk(_cb_i > 0 and _cb_j - _cb_i > 400,
    "onda1/S2: o bloco do limiar foi delimitado e tem conteudo (%d..%d)"
    % (_cb_i, _cb_j))
_cbblock = _syn[_cb_i:_cb_j]
chk("combatPower" not in _cbblock,
    "onda1/S2: o Poder de Combate NAO entra no bloco do limiar — e' outra "
    "grandeza, e ao lado dele a barra mentiria")

# ── 19g — S1: o erro deixa de ser a palavra crua do servidor ──────────────
chk("<CultRecovery" in _APC,
    "onda1/S1: a chegada que falha desenha o cartao de recuperacao")
chk("<ErrBanner msg={error} />" not in _APC,
    "onda1/S1: a faixa com a palavra crua saiu do ecra de chegada — era um "
    "beco: 'unauthorized' em ingles, sem um unico botao")
chk("onRetry" in _APC and "loadPlayer()" in _APC,
    "onda1/S1: ha' um 'Tentar de novo' que REPETE a chamada")
_rec = _UIC[_UIC.find("function CultRecovery"):]
_rec = _rec[:_rec.find("\n    // ─── S3")] if "\n    // ─── S3" in _rec else _rec[:6000]
for _s in ("unauthorized", "session_expired"):
    chk(_s in _UIC[_UIC.find("var _SESSION_ERRS"):_UIC.find("var _SESSION_ERRS") + 300],
        "onda1/S1: `%s` e' reconhecido como sessao expirada — e' o que o "
        "middleware devolve" % _s)
chk("onda_rec_session_telegram" in _rec and "onda_rec_session_browser" in _rec,
    "onda1/S1: a saida e' POR PLATAFORMA — no Telegram nao ha' `/login` para "
    "onde mandar, e um botao que nao faz nada e' pior que nenhum")
chk("tg.initData" in _rec or "tg && tg.initData" in _rec,
    "onda1/S1: a plataforma e' DETECTADA (o `initData` do Telegram), nao "
    "assumida")

# ── 19h — as ANCORAS nunca apontam para o vazio ───────────────────────────
_anc = _UIC[_UIC.find("function CultAnchors"):]
_anc = _anc[:_anc.find("\n    // ─── S1 — o CARTÃO")] if "\n    // ─── S1 — o CARTÃO" in _anc else _anc[:4000]
chk("filter(function (a) { return a && a.present; })" in _anc,
    "onda1/S1: as ancoras FILTRAM por `present` — uma ancora para uma seccao "
    "que nao existe e' a Lei §1 partida pela decoracao")
chk("live.length < 2" in _anc,
    "onda1/S1: a faixa toda desaparece abaixo de duas ancoras — uma ancora "
    "sozinha nao e' navegacao, e' ruido")
# ⚠️ 2026-09-16: QUATRO alvos, nao tres. As tres reguas de seccao mais a
# propria OPERACAO (`cult-sec-meditar`), que a [013] §B.1 mandou alcancar por
# um salto textual quando a identidade passou a ocupar a largura toda e S3
# caiu abaixo da primeira dobra no telemovel.
chk(_TBC.count('anchorId="cult-sec-') == 4,
    "onda1/S1: as tres reguas + a operacao tem `anchorId` (%d encontradas) — "
    "sem ele o salto nao tem alvo" % _TBC.count('anchorId="cult-sec-'))
chk('anchorId="cult-sec-meditar"' in _TBC and "cult-sec-meditar" in _TBC,
    "onda1/S1: o salto para a operacao tem destino REAL na pagina")
# 🔴 E a pergunta que FALTAVA, apanhada pela sabotagem 25/33: as guardas
# acima verificam que o `anchorId` e' PASSADO. Nenhuma verificava que ele
# CHEGA a um atributo `id` no elemento -- tirei o `id={anchorId}` do
# `SectionRule` e as 786 ficaram VERDES, com as quatro ancoras da tela a
# saltar para lado nenhum. "Existe" nao e' "chega" (licao ja' registada).
_sr = _UIC[_UIC.find("function SectionRule"):]
_sr = _sr[:_sr.find("\n    function ", 10)]
chk(len(_sr) > 400, "onda1/S1: `SectionRule` foi delimitada (%d chars)" % len(_sr))
chk("<div id={anchorId}" in _sr,
    "onda1/S1: o `anchorId` CHEGA ao DOM na regua de seccao -- sem o "
    "atributo `id` o salto nao tem alvo e NADA o denuncia")
# ** O mesmo para a operacao, que e' uma `<section>` e nao uma regua.
_ms = _UIC[_UIC.find("function MeditationCard"):]
chk("<section id={anchorId}" in _ms,
    "onda1/S1: o `anchorId` CHEGA ao DOM na seccao da meditacao")
# ** E o `scrollMarginTop`, que so' existe quando ha' ancora: sem ele o
# titulo da seccao encostava ao cabecalho fixo depois do salto.
chk("scrollMarginTop: anchorId ? 12 : undefined" in _sr,
    "onda1/S1: a regua reserva o topo SO' quando e' alvo -- os sitios sem "
    "ancora desenham o mesmo markup de hoje")
_ids_alvo = set(re.findall(r'anchorId="(cult-sec-[a-z]+)"', _TBC))
_ids_orig = set(re.findall(r'id:"(cult-sec-[a-z]+)"', _TBC))
# ⚠️ A pergunta certa e' SUBCONJUNTO, nao igualdade: `cult-sec-meditar` e' um
# ALVO sem ser uma ancora da faixa (tem o salto proprio, junto ao estado). Uma
# guarda de igualdade obrigaria a por a operacao na faixa so' para ficar verde.
chk(_ids_orig and _ids_orig <= _ids_alvo and len(_ids_orig) == 3,
    "onda1/S1: cada ancora aponta para um `anchorId` que EXISTE (ancoras %r "
    "vs alvos %r)" % (sorted(_ids_orig), sorted(_ids_alvo)))
chk("present:_hasPractice" in _TBC and "present:_hasPaths" in _TBC,
    "onda1/S1: a Pratica e os Caminhos so' ganham ancora quando a condicao "
    "deles e' verdadeira — nunca `present:true` fixo")

# ── 19i — a ORDEM muda sem o JSX ser escrito duas vezes ───────────────────
chk("const secPractice = (" in _TBC and "const secSelf = (" in _TBC,
    "onda1: as duas seccoes vivem em constantes")
chk(_TBC.count("<SectionRule glyph=\"修\"") == 1
    and _TBC.count("<SectionRule glyph=\"己\"") == 1,
    "onda1: cada regua e' escrita UMA vez — duplicar 240 linhas de JSX para "
    "trocar duas posicoes seria a Lei 0 §2 dentro do lote que a cumpre")
chk("{secSelf}{secPractice}" in _TBC and "{secPractice}{secSelf}" in _TBC,
    "onda1: a ordem ON e' 己 -> 修 (a do desenho) e a OFF e' a de hoje")

# ── 19j — A FLAG: OFF em todo o lado, e `main` le' os defaults ────────────
_DBJS = rd("database/db.py")
chk('"cultivador_jogavel":  False,' in _DBJS,
    "onda1: a flag nasce OFF no `DEFAULT_WORLD_FEATURES` — e o `main` le' "
    "SEMPRE os defaults")
chk("ondaCultOn" in _UIC and 'featureEnabled("cultivador_jogavel")' in _UIC,
    "onda1: o portao unico e' `ondaCultOn()` — nao ha' um segundo sitio a ler "
    "a chave a mao")
chk(_UIC.count('featureEnabled("cultivador_jogavel")') == 1,
    "onda1: a chave e' lida UMA vez em `ui.js` (%d) — dois leitores divergem"
    % _UIC.count('featureEnabled("cultivador_jogavel")'))
chk(_TBC.count("ondaCultOn()") == 1,
    "onda1: `tabs.js` chama o portao UMA vez e passa o booleano (%d)"
    % _TBC.count("ondaCultOn()"))
# ⚠️ O ramo OFF nao pode perder NADA. Os dez modais da aba continuam la',
# porque o desenho diz que "Meditar" nao substitui nenhum desses acessos.
for _m in ("BreakthroughModal", "CoreFormationModal", "DaoLawsModal",
           "FoundationTrialModal", "PrestigeShopModal", "QuebrarFundacaoModal",
           "RebirthModal", "RecomecoModal", "SpiritRootRerollModal",
           "TribulationModal"):
    chk(("<" + _m) in _TBC,
        "onda1: o acesso a `%s` sobreviveu a onda — nenhuma accao da aba pode "
        "sumir atras de um CTA novo" % _m)

# ── 19k — as 3 linguas, em PARIDADE ───────────────────────────────────────
import json
_locs = {}
for _lg in ("pt", "en", "es"):
    _locs[_lg] = json.loads(rd("miniapp/i18n/%s.json" % _lg))
chk(len(set(len(v) for v in _locs.values())) == 1,
    "onda1/i18n: os tres ficheiros do mini-app tem o MESMO numero de chaves "
    "(%r)" % {k: len(v) for k, v in _locs.items()})
_usadas = set(re.findall(r't\("(onda_[a-z0-9_]+)"', _UI + _TABS + _APPM))
chk(len(_usadas) >= 30,
    "onda1/i18n: a onda usa %d chaves `onda_*` — se desabasse, o regex "
    "partiu-se e nao o problema" % len(_usadas))
for _lg, _d in _locs.items():
    _falta = sorted(k for k in _usadas if k not in _d)
    chk(not _falta,
        "onda1/i18n: `%s.json` tem todas as chaves da onda (falta %r)"
        % (_lg, _falta[:5]))
# ⚠️ E o PAINEL DE ADMIN. Sem estas duas ele escrevia a chave crua ao lado de
# um interruptor que muda a tela mais aberta do jogo (Lei 0 §1: contar os
# sitios — o sitio nao e' so' onde me pediram).
for _lg, _d in _locs.items():
    chk("feature_cultivador_jogavel" in _d
        and "feature_cultivador_jogavel_desc" in _d,
        "onda1/i18n: `%s.json` nomeia e descreve a flag para o painel de "
        "admin" % _lg)
# ⚠️ Nenhum `{param}` orfao: um placeholder que a traducao esqueceu sai LITERAL
# na cara do jogador.
for _k in sorted(_usadas):
    _ps = [set(re.findall(r"\{(\w+)\}", _locs[_l].get(_k, ""))) for _l in ("pt", "en", "es")]
    chk(_ps[0] == _ps[1] == _ps[2],
        "onda1/i18n: `%s` tem os MESMOS placeholders nas tres linguas (%r) — um `{param}` esquecido numa traducao sai LITERAL na cara do jogador"
        % (_k, [sorted(p) for p in _ps]))

# -- 19m -- A PELE DA [013] EXISTE, e nao e' a velha --------------------------
# ** Esta familia existe porque a AUSENCIA dela custou um lote inteiro: a [011]
# foi implementada a' letra, as guardas ficaram todas VERDES, e o owner recusou
# a tela A OLHAR ("nao foi isso que eu vi antes na previa"). Elas mediam a
# GEOMETRIA e a VERDADE dos numeros; nenhuma perguntava se a tela tinha a PELE
# decidida. Um teste verde pode estar certo sobre a coisa errada.
_ONDA_CORES = {"tinta": "#0b0a0c", "papel": "#ece5d8", "ouro": "#c9903a",
               "cinabrio": "#c8442f", "secundario": "#baad97"}
_paleta = _UIC[_UIC.find("var NIV_ONDA = {"):]
_paleta = _paleta[:_paleta.find("};") + 2]
chk(len(_paleta) > 200, "onda1/pele: `NIV_ONDA` existe (%d chars) -- a paleta "
    "local da [013]" % len(_paleta))
for _nome in sorted(_ONDA_CORES):
    chk(_ONDA_CORES[_nome] in _paleta,
        "onda1/pele: a cor `%s` (%s) da previa esta' na paleta local"
        % (_nome, _ONDA_CORES[_nome]))
chk("Cormorant Garamond" in _paleta and "Noto Sans" in _paleta
    and "Cinzel" in _paleta,
    "onda1/pele: as tres familias da previa estao declaradas")
# ** Cinzel FORA do fallback do Cormorant: as duas sao serifadas mas de caracter
# OPOSTO, e enquanto a primeira nao carrega o titulo fica com a personalidade
# errada -- nao com uma parecida ([013] A.2).
chk("'Cormorant Garamond', Georgia, serif" in _paleta,
    "onda1/pele: o fallback do Cormorant e' Georgia, nunca Cinzel")
# ** A pele e' LOCAL ([013] C.4): esta tela nao escreve no `:root` nem depende
# da `pele_quente`. Um `applyWarmSkin()` aqui repintava o jogo INTEIRO a partir
# de uma flag que so' decidiu UMA tela.
_onda_bloco = _UIC[_UIC.find("var NIV_ONDA = {"):_UIC.find("function LeaderRow")]
chk(len(_onda_bloco) > 5000,
    "onda1/pele: o bloco da onda foi delimitado (%d chars)" % len(_onda_bloco))
chk("applyWarmSkin" not in _onda_bloco and "CSS_VAR_HEX" not in _onda_bloco,
    "onda1/pele: a onda nao chama a pele global nem le a tabela dela")
chk("pele_quente" not in _onda_bloco,
    "onda1/pele: a onda nao depende da `pele_quente` -- a fronteira da [013] C")
# ** O FIO de 2px substituiu a barra de 6px, e a marca de transbordo vive FORA
# da camada que recorta o preenchimento -- dentro de um `overflow:hidden` ela
# era cortada exactamente onde precisa de se ver ([013] A.4).
_fio = _UIC[_UIC.find("function CultFio"):_UIC.find("function CultBlock")]
chk(len(_fio) > 300, "onda1/pele: `CultFio` existe -- o fio de 2px da [013]")
chk("height:2" in _fio, "onda1/pele: o trilho tem 2px, nao os 6 da [011]")
chk("linear-gradient" not in _fio,
    "onda1/pele: o fio e' cor SOLIDA -- a [013] cortou os gradientes das barras")
_ov_i, _rec_i = _fio.find("height:10"), _fio.find('overflow:"hidden"')
chk(_ov_i > 0 and _rec_i > 0 and _ov_i < _rec_i,
    "onda1/pele: a marca de transbordo abre FORA da camada que recorta "
    "(caixa em %d, recorte em %d)" % (_ov_i, _rec_i))
# ** S3 perdeu a moldura: e' uma `<section>`, nao um `<Card>`. E nao bastava
# passar `ornate={false}` ao Card -- ele continua a desenhar fundo, borda,
# brilho superior e textura ([013] B.5).
_s3 = _UIC[_UIC.find("function MeditationCard"):]
chk("<section" in _s3, "onda1/pele: S3 e' uma seccao ABERTA, nao um cartao")
chk("<Card>" not in _s3 and "<CardTitle" not in _s3,
    "onda1/pele: S3 nao reabre o `Card` -- a moldura era o defeito")
# ** O botao da onda e' papel/tinta com raio ZERO. O `ActionBtn` e' usado em 345
# sitios e carrega o gradiente e o raio que esta tela foi cortar; dar-lhe uma
# variante nova era por 344 ecras a carregar uma pele que nao e' deles.
_btn = _UIC[_UIC.find("function OndaBtn"):_UIC.find("var _SESSION_ERRS")]
chk(len(_btn) > 400, "onda1/pele: `OndaBtn` existe")
chk("borderRadius:0" in _btn, "onda1/pele: o botao da onda tem raio ZERO")
chk('backgroundImage:"none"' in _btn and 'boxShadow:"none"' in _btn,
    "onda1/pele: o botao da onda nao tem gradiente nem sombra")
# ** E o EMOJI sai do nome EXIBIDO das modalidades -- so' do exibido. Numa tela
# de tinta, papel e Cormorant, sete pictogramas coloridos do sistema operativo
# em lista sao o unico sitio onde a pele se parte ([013] A.3).
chk("function ondaNomeLimpo" in _UIC,
    "onda1/pele: ha' um dono unico para limpar o nome exibido")
chk(_UIC.count("ondaNomeLimpo(") >= 4,
    "onda1/pele: os sitios que escrevem o nome de uma modalidade passam pelo "
    "dono (%d)" % _UIC.count("ondaNomeLimpo("))
# ** A CHAVE e a traducao ficam INTACTAS -- muda o que se PINTA. Traduzir ou
# reescrever a chave partia o `start` (licao medida: "traduzir o nome APAGA a
# arte, em silencio").
# ** A chave crua vive na LINHA (`MeditationRow`), nao no cartao -- e a fatia
# tem de ser a dela. A 1a versao olhou para `MeditationCard`, que so' tem
# `r.key`: guarda vermelha por ler o sitio errado, nao por defeito no codigo.
_s3row = _UIC[_UIC.find("function MeditationRow"):_UIC.find("var _MED_ERR_KEY")]
chk(len(_s3row) > 1000,
    "onda1/pele: `MeditationRow` foi delimitada (%d chars)" % len(_s3row))
chk("row.key" in _s3row and "onSelect(row.key)" in _s3row,
    "onda1/pele: a CHAVE da modalidade continua crua -- so' o nome e' limpo")

# -- 19n -- A REDUCAO DE MOVIMENTO, que NAO EXISTIA ---------------------------
# ** MEDIDO a 2026-09-16: `miniapp/index.html` tinha ZERO ocorrencias de
# `prefers-reduced-motion` e 20+ `@keyframes` a correr sempre -- incluindo
# pulsos de brilho e uma tempestade. Para quem pediu ao sistema operativo para
# NAO ter movimento, o jogo ignorava o pedido em TODAS as telas.
_IDX = rd("miniapp/index.html")
chk("prefers-reduced-motion" in _IDX,
    "onda1/a11y: o mini-app RESPEITA a reducao de movimento (nao respeitava)")
# ** `.01ms` e nao `none`: uma animacao com `animation: none` NUNCA dispara
# `animationend`, e ha' codigo que espera por esse evento para continuar --
# mata-la a seco PENDURAVA o fluxo em vez de o acelerar.
_rm = _IDX[_IDX.find("@media (prefers-reduced-motion"):]
_rm = _rm[:_rm.find("@keyframes")]
chk("animation-duration: .01ms" in _rm and "animation: none" not in _rm,
    "onda1/a11y: a regra usa .01ms e nao `none` -- `none` nunca dispara "
    "`animationend` e pendura quem espera por ele")
chk("!important" in _rm,
    "onda1/a11y: a regra vence os estilos em linha do jogo (sao centenas)")

# -- 19o -- A CHAVE-MESTRA do owner -------------------------------------------
# ** Ordem dele: "amanha eu so ativo uma feature nova onde tudo que criaram
# juntos eu ativo e vejo". UMA linha no painel, nao cinco.
chk('"a_obra":' in _DBJS, "onda1/obra: a chave-mestra `a_obra` existe")
chk('"a_obra":              False,' in _DBJS,
    "onda1/obra: ela nasce OFF -- o `main` le' sempre os defaults")
# ** A implicacao vive num sitio SO'. Escrever a condicao dupla em cada
# componente seria a mesma decisao com dois donos (Lei 0 2) -- e foi assim que
# uma lista de 4 modalidades sobreviveu meses ao lado de um servidor que
# aceita 7.
_gate = _UIC[_UIC.find("function ondaCultOn"):]
_gate = _gate[:_gate.find("\n    }") + 6]
chk('featureEnabled("a_obra")' in _gate
    and 'featureEnabled("cultivador_jogavel")' in _gate,
    "onda1/obra: a chave-mestra IMPLICA a da tela, no portao unico")
chk(_UIC.count('featureEnabled("a_obra")') == 1
    and _TBC.count('featureEnabled("a_obra")') == 0,
    "onda1/obra: a chave-mestra e' lida UMA vez, no portao (ui %d / tabs %d)"
    % (_UIC.count('featureEnabled("a_obra")'),
       _TBC.count('featureEnabled("a_obra")')))
# ** IMPLICA, nunca SUBSTITUI: o `s2` tem `cultivador_jogavel` ligada desde
# 15/09 e nao pode perder a tela por a chave-mestra ter nascido.
chk(" || " in _gate,
    "onda1/obra: e' um OU -- quem ja' tinha a chave da tela NAO a perde")
for _lg in ("pt", "en", "es"):
    chk("feature_a_obra" in _locs[_lg] and "feature_a_obra_desc" in _locs[_lg],
        "onda1/obra: `%s.json` nomeia e descreve a chave-mestra para o painel "
        "(sem isto o owner lia a chave crua ao lado do interruptor)" % _lg)

# -- 19p -- A TELA NAO SE DESMENTE NO CUME ------------------------------------
# ** Apanhado A OLHAR a 1440x900 (Lei 0 passo 3), com as 783 guardas VERDES. No
# estado `ceiling` a tela dizia, com quatro pixels entre as duas linhas:
#     "Faltam 136.000 para o limiar"
#     "O cume da escada -- encher esta barra ja' nao abre avanco nenhum"
# A primeira convida a encher; a segunda diz que encher nao faz nada. E' a MESMA
# familia de defeito que a WEB-E foi corrigir NESTA tela (a barra a fingir uma
# contagem decrescente no cume) a voltar pela porta do lado, num lote que trouxe
# o aviso e deixou a distancia.
# ** E nao e' um caso raro: reino 10 camada 9 sao **21 dos 37 activos-30d do
# `main` (57%)** -- a MAIORIA de quem abre esta tela.
chk("{cbM > 0 && !atCeiling ?" in _syn,
    "onda1/cume: a linha da distancia ao limiar CALA-SE no cume -- 'faltam X' "
    "ao lado de 'X nao serve para nada' e' a tela a desmentir-se")
# ** A anti-guarda: o aviso do cume TEM de continuar la'. Uma 'correccao' que
# apagasse os dois deixava o jogador do cume sem explicacao nenhuma, que e' o
# silent void que a Lei 1 proibe -- pior do que a contradicao.
chk('t("cena_ceiling_title")' in _syn and 't("cena_ceiling_body")' in _syn,
    "onda1/cume: o aviso do cume CONTINUA dito por palavras -- calar os dois "
    "seria trocar uma contradicao por um vazio")
chk("{atCeiling && (" in _syn,
    "onda1/cume: o aviso e' condicional ao cume (nao aparece a quem ainda sobe)")

# -- 19q -- TRES DEFEITOS QUE CUSTAM RECURSOS AO JOGADOR ----------------------
# ** Achados pelo Astra na auditoria de 16/09 e MEDIDOS por mim antes de tocar
# em nada (`Olho/Astra/2026-09-16-onde-melhorar.md`). Nenhum e' desenho, e por
# isso nenhum esta' atras de flag: sao a Lei 1 (a tela nunca engana) em tres
# sitios onde enganar custa pedras, um artefacto ou uma luta.

# (a) O COMPARADOR ESCONDIA AS PERDAS.
# Medido: `stats` saia de `Object.entries(_shownStats)` -- SO' os atributos da
# peca NOVA. Trocar `{defesa:100}` por `{ataque:20}` mostrava o +20 e NUNCA
# dizia que se perdiam 100 de defesa. A interface ajudava a escolher pior.
chk("Object.entries(_shownStats).concat(" in _TBC,
    "mercado/inv: o comparador percorre a UNIAO dos atributos das duas pecas")
chk(".filter(k => !(k in _shownStats))" in _TBC,
    "mercado/inv: os atributos que SO' a peca equipada tem entram na lista -- "
    "um atributo que DESAPARECE e' a informacao que decide a troca")
# ** A anti-guarda: a peca nova continua a vir PRIMEIRO. Uma 'correccao' que
# ordenasse tudo por nome mudava de sitio a leitura de sempre.
_cmp_i = _TBC.find("const stats = isArtifact")
chk(_cmp_i > 0 and _TBC.find("Object.entries(_shownStats)", _cmp_i) <
    _TBC.find(".filter(k => !(k in _shownStats))", _cmp_i),
    "mercado/inv: os atributos da peca NOVA vem primeiro; as perdas a seguir")

# (b) O HP DO COMBATE DIZIA "0 / X (100%)".
# Medido: `hp_pct ?? 100` (NULL -> 100) ao lado de `current_hp || 0` (NULL -> 0).
# Com o HP nulo -- que no contrato significa CHEIO -- a MESMA linha escrevia
# zero de vida e cem por cento, com 40 pixels entre os dois.
chk("stats.current_hp === null || stats.current_hp === undefined" in _TBC,
    "combate: o HP nulo do cabecalho e' resolvido como CHEIO, nunca como zero")
chk("{fmtNum(stats.current_hp || 0)}" not in _TBC,
    "combate: o `current_hp || 0` do cabecalho MORREU -- era ele que escrevia "
    "o zero ao lado dos 100%")
chk("{fmtFull(_curHp)} / {fmtFull(_maxHp)}" in _TBC,
    "combate: o HP do cabecalho e' INTEIRO (o do Cultivo tem 12 digitos; este "
    "le a mesma coluna)")

# (c) O MERCADO ABRIA COM O ESTOQUE INTEIRO SELECCIONADO.
# Medido: `useState(listing.quantity)`. Um toque em confirmar levava a oferta
# completa -- e o botao "comprar tudo" existe a 30 pixels dali, o que prova que
# "tudo" JA' era para ser uma escolha explicita.
_mb = _TBC[_TBC.find("function MarketBuyModal"):]
_mb = _mb[:_mb.find("\n    function ", 10)]
chk(len(_mb) > 2000, "mercado: `MarketBuyModal` foi delimitada (%d chars)" % len(_mb))
chk("const [qty, setQty] = useState(1);" in _mb,
    "mercado: a janela abre com UMA unidade, nao com o estoque inteiro")
chk("useState(listing.quantity)" not in _mb,
    "mercado: o `useState(listing.quantity)` MORREU -- era ele que punha o "
    "estoque todo a um toque de distancia")
chk('t("market_buy_all")' in _mb,
    "mercado: o botao 'comprar tudo' CONTINUA la' -- tirar a armadilha nao "
    "pode tirar a conveniencia")
# ** E o numero que sai da carteira nunca e' abreviado.
chk("{fmtFull(total)}" in _mb and "{fmtNum(total)}" not in _mb,
    "mercado: o TOTAL e' inteiro -- `fmtNum` mostrava `184.3K` onde saem "
    "184.312 pedras")
chk("{fmtFull(unit)}" in _mb,
    "mercado: o preco unitario tambem e' inteiro (e' o que multiplica)")

# -- 19r -- O TRANSPORTE NAO PENDURA, E O DUELO NAO MENTE --------------------
# ** Itens 6 e 8 da auditoria do Astra (16/09), medidos por mim antes de tocar.

# (a) O RELOGIO. O `fetch` do transporte comum nao tinha prazo: um pedido que
# nunca resolve deixava o botao em `busy` e o jogador PENDURADO para sempre --
# sem erro, sem caminho, e sem saber se a coisa aconteceu (Lei 1 na forma mais
# pura). Corre no caminho de TODAS as 25 abas.
_apib = _UIC[_UIC.find("async function api(endpoint"):]
_apib = _apib[:_apib.find("function openPaymentLink")]
chk(len(_apib) > 800, "transporte: o `api()` foi delimitado (%d chars)" % len(_apib))
# 🔴 A 1a versao desta guarda FICOU VERDE na sabotagem: ela perguntava se a
# CONSTANTE existia, nunca se o relogio estava ARMADO. Trocar o `setTimeout`
# por `_tm = null` deixava `API_TIMEOUT_MS` e `AbortController` no ficheiro e
# o jogo voltava a pendurar. Familia "existe nao e chega", 5a recorrencia.
chk("API_TIMEOUT_MS" in _UIC and "AbortController" in _apib,
    "transporte: o `fetch` conhece o prazo")
chk(re.search(r"_tm\s*=\s*setTimeout\([\s\S]{0,120}?abort\(\)[\s\S]{0,60}?API_TIMEOUT_MS\)", _apib)
    is not None,
    "transporte: o relogio esta ARMADO (o `setTimeout` chama mesmo o `abort` com o prazo) -- sem isto um pedido pendurado nao tem fim")
chk("clearTimeout(_tm)" in _apib,
    "transporte: o relogio e' limpo -- senao fica um abort agendado por cima "
    "de um pedido que ja' chegou")
# ** 🔴 A ARMADILHA, e e' do Astra: "uma resposta perdida pode corresponder a
# uma accao CONCLUIDA no servidor". Um relogio que repetisse sozinho um
# `market/buy` cobraria duas vezes. Ele devolve o CONTROLO, nunca repete.
chk("retry" not in _apib.lower() and "setTimeout(() => api(" not in _apib,
    "transporte: o relogio NAO repete o pedido -- repetir uma mutacao perdida "
    "cobra duas vezes (a resposta e' que se perdeu, nao a accao)")
chk('"request_timeout"' in _apib and '"network_error"' in _apib,
    "transporte: o PRAZO e a falha de rede sao codigos DIFERENTES -- um diz "
    "'nao sei', o outro diz 'nao saiu', e o conselho ao jogador nao e' o mesmo")
# ** E a frase do prazo nunca pode dizer "falhou".
for _lg in ("pt", "en", "es"):
    _tt = _locs[_lg].get("err_request_timeout", "")
    chk(bool(_tt), "transporte/i18n: `%s.json` tem a frase do prazo" % _lg)
_pt_to = _locs["pt"].get("err_request_timeout", "")
chk("nao sabemos" in _pt_to.lower() or "n\u00e3o sabemos" in _pt_to.lower()
    or "sabemos" in _pt_to.lower(),
    "transporte/i18n: a frase do prazo diz que NAO SE SABE, nunca que falhou "
    "(%r)" % _pt_to[:60])

# (b) UM DONO para traduzir o codigo de erro. O `ErrBanner` e' usado em ~99
# sitios e tinha uma tabela de DUAS entradas escrita a mao la' dentro; o
# `core/webserver.py` tem 85 codigos distintos.
chk("var API_ERR_KEY = {" in _UIC and "function apiErroTexto" in _UIC,
    "erros: ha' UM dono para traduzir o codigo (`apiErroTexto`)")
_eb = _UIC[_UIC.find("function ErrBanner"):]
_eb = _eb[:_eb.find("\n    //", 10)]
chk("apiErroTexto(msg)" in _eb,
    "erros: o `ErrBanner` passa pelo dono -- e assim os ~99 sitios dele "
    "melhoram com uma escrita so'")
chk('msg === "unauthorized" ?' not in _eb,
    "erros: a tabela de duas entradas escrita a mao dentro do banner MORREU")
chk("apiErroTexto" in _UIC[_UIC.find("function CultRecovery"):][:3000],
    "erros: o cartao de recuperacao usa o MESMO dono -- duas tabelas dariam "
    "duas frases para a mesma falha")
# ** O DESCONHECIDO cai para o codigo cru: esconder o que nao sei traduzir tira
# ao jogador a unica coisa que ele podia colar num report.
chk("return k ? t(k) : msg;" in _UIC,
    "erros: um codigo sem frase sai CRU, nunca escondido")

# (c) O DUELO enviava a tecnica que a propria tela tinha desactivado.
# Medido: `pickTech` persiste entre rondas (so' muda nos dois onClick), a carta
# e' desactivada por `you.combat_qi >= tt.qi_cost` recalculado a cada render, e
# o `submit()` mandava `pickTech` SEM reverificar. Escolher X na ronda 1 e
# entrar na 2 sem qi mandava X na mesma, com a carta vermelha no ecra.
chk("const _pickCaiu = pickTech !== 0" in _TBC,
    "duelo: a queda da escolha e' DETECTADA")
chk("const pickEfetivo = _pickCaiu ? 0 : pickTech;" in _TBC,
    "duelo: o que se VE e' derivado no render -- um `setPickTech(0)` num efeito "
    "daria um frame com a escolha velha acesa, que e' o instante do toque")
chk("pickEfetivo === 0" in _TBC and "const selected = pickEfetivo === tt.id;" in _TBC,
    "duelo: as cartas acendem o que vai SER ENVIADO, nao o que foi escolhido")
chk("duel_id: duelId, technique_id: _envio," in _TBC,
    "duelo: o envio manda a escolha VALIDADA, nunca o `pickTech` cru")
chk('t("duel_tech_dropped")' in _TBC,
    "duelo: a tela DIZ porque e' que a escolha caiu -- 'mudou sozinho' e' pior "
    "do que 'mudou e disse'")
for _lg in ("pt", "en", "es"):
    chk("duel_tech_dropped" in _locs[_lg],
        "duelo/i18n: `%s.json` tem a frase da escolha que caiu" % _lg)

# ── 19l — ZERO migration ──────────────────────────────────────────────────
_meu5 = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
         if re.search(r"(?:^|_)(cultivador_jogavel|onda1|onda_1|meditacao_catalogo)(?:_|\.)",
                      m, re.I)]
chk(not _meu5,
    "onda1: nenhuma migration — a onda e' render, i18n e uma chave nova no "
    "payload (%r)" % (_meu5,))



# ═══════════════════════════════════════════════════════════════════════════
print("\n=== 20. 決 A DECISAO QUE NAO SE PERDE (item 5 da auditoria) ===")
#
# 🔴 O DEFEITO, medido nos DOIS lados a 2026-09-16:
#
#   `ExploreDuelModal` lia o desfecho do duelo com
#       const w = !!(st && st.state === "finished" && st.winner_id === youId);
#   e mandava tudo o que nao fosse isso para `won=false` — que a tela escreve
#   como 🥀 *"O Monstro Escondido foi forte demais"*.
#
#   So' que o servidor tem TRES caminhos que chegam ali sem ser uma derrota:
#     · `combat/duel_state` devolve **HTTP 200 com `ok:false`**
#       (`not_a_participant`) e 200 com `duel_id:null` — o `catch` nao dispara;
#     · `combat/npc_cultivator_resolve` devolve **HTTP 200 com
#       `{ok:false, reason:"internal_error"}` em QUALQUER excepcao do servidor**;
#     · o prazo de 30s do transporte (`request_timeout`), que e' "nao sei".
#
#   Ou seja: uma falha de rede de 200ms AFIRMAVA uma derrota que podia nao ter
#   acontecido, e comia a escolha moral inteira — o karma nunca era oferecido.
#
# ⚠️ E o contrato JA' SALVAVA o jogador: `apply_combat_moral_choice` e'
#   idempotente por duelo e a recusa `already_resolved` **traz o desfecho dentro
#   dela**. O cliente deitava fora exactamente a informacao que o desprendia.
_UIC = _sem_prosa_js(_UI)

# (a) 🔴 UM DONO, TRES BEBEDORES. Esta e' a guarda que a Lei 0 §2 pede, e e' a
#     que me apanhou a mim: eu tinha corrigido o sitio que o Astra apontou e
#     havia TRES modais com a mesma decisao moral copiada a' mao —
#     `NpcCultivatorModal`, `JianghuAmbushModal` e `ExploreDuelModal`. As tres
#     tinham o mesmo defeito, e a terceira ja' tinha perdido a linha do Caminho
#     cristalizado que as outras duas mostram.
chk(_TBC.count("function useDecisaoMoral(") == 1,
    "decisao: o dono e' UM (%d definicoes de `useDecisaoMoral`)"
    % _TBC.count("function useDecisaoMoral("))
_CHAMADAS_DONO = (_TBC.count("useDecisaoMoral({")
                  - _TBC.count("function useDecisaoMoral({"))
chk(_CHAMADAS_DONO == 3,
    "decisao: os TRES modais bebem do mesmo dono (%d chamadas) — perfil, "
    "emboscada e Monstro Escondido" % _CHAMADAS_DONO)
chk('const [desfecho, setDesfecho] = useState("desconhecido");' in _TBC,
    "decisao: o desfecho tem TRES estados (vitoria/derrota/desconhecido)")
chk("setWon(" not in _TBC,
    "decisao: o booleano `setWon` MORREU nos tres — enquanto ele existir ha' "
    "um sitio onde 'nao sei' e' gravado como 'perdi'")
# Os TRES leitores legitimos de `duel_state`, medidos: o painel da arena
# (`DuelArenaPanel`, sem duel_id — procura o duelo aberto), o proprio modal da
# arena (`DuelArenaModal`, o polling de 2s) e o dono da decisao moral. Um
# quarto seria um modal novo a reimplementar a leitura do desfecho a' mao — que
# e' exactamente como nasceram as tres copias que este lote juntou.
chk(_TBC.count('api("combat/duel_state"') == 3,
    "decisao: o desfecho do duelo le-se em 3 sitios (painel, arena, dono) e "
    "nao mais (%d)" % _TBC.count('api("combat/duel_state"'))

# (b) o `ok:false` a HTTP 200 e' LIDO. O `catch` nunca o apanha.
chk('if (!st || st.ok === false || st.state !== "finished" || youId == null) '
    'return "desconhecido";' in _TBC,
    "decisao: `ok:false` a 200 e a ausencia de `youId` sao 'nao sei', nunca derrota")

# (c) a saida do 'nao sei' e' uma LEITURA repetivel — nunca um reenvio da mutacao.
#     E' a regra do item 8 do Astra: *uma resposta perdida pode corresponder a
#     uma accao concluida no servidor*.
chk("async function lerDesfecho()" in _TBC and "async function reverDesfecho()" in _TBC,
    "decisao: a saida do 'nao sei' e' uma LEITURA repetivel")
chk(_TBC.count('api("combat/npc_cultivator_resolve"') == 1,
    "decisao: a mutacao moral sai de UM sitio so' (%d) — dois seriam duas "
    "hipoteses de ela se repetir sozinha"
    % _TBC.count('api("combat/npc_cultivator_resolve"'))

# (d) o contrato que ja' salvava o jogador, e que o cliente deitava fora.
chk('res.reason === "already_resolved" && res.outcome' in _TBC,
    "decisao: a recusa `already_resolved` TRAZ o desfecho — le-se, nao se deita fora")

# (e) 🔴 o defeito EXACTO: o `finally` mandava para o resultado mesmo tendo
#     falhado, e a escolha desaparecia sem a tela alguma vez o admitir.
# ⚠️ Esta assert e' POSITIVA de proposito. A 1a versao dizia apenas *"o texto
#    antigo ja' nao esta' ca'"* — e uma guarda que so' sabe recusar uma frase
#    exacta nao guarda o comportamento: bastava escrever o mesmo defeito com
#    outras palavras para ela ficar verde. Agora ela afirma o que o `finally`
#    TEM de fazer: soltar o botao e avisar quem chamou, e mais nada.
chk("} finally { setMoralBusy(false); if (aoResolver) aoResolver(); }" in _TBC,
    "decisao: o `finally` da escolha solta o botao e avisa quem chamou — e NAO "
    "muda de fase. Empurrar para o resultado era o que apagava a escolha")
# ⚠️ E a assert segue a INDIRECCAO em vez de se baixar: recorta o corpo de
#    `escolher` e conta onde e' que a fase muda. Duas vezes, e as duas sao
#    caminhos CONFIRMADOS pelo servidor (`ok:true` e `already_resolved`, que
#    traz o desfecho dentro dela). O `catch` — a rede que caiu — nao muda nada.
_ESCOLHER = (_TBC.split("async function escolher")[1].split("\n      }\n")[0]
             if "async function escolher" in _TBC else "")
_ESC_CATCH = _ESCOLHER.split("} catch (e) {")[1] if "} catch (e) {" in _ESCOLHER else "SEM-CATCH"
chk(_ESCOLHER.count('setFase("result");') == 2,
    "decisao: a fase so' avanca nos DOIS caminhos confirmados pelo servidor "
    "(%d mudancas de fase em `escolher`)" % _ESCOLHER.count('setFase("result");'))
chk("setFase(" not in _ESC_CATCH,
    "decisao: o `catch` da escolha NAO muda de fase — avancar com a rede caida "
    "era o que apagava a decisao sem a tela o admitir")
chk("setMoralErro({ tipo: \"silencio\"" in _TBC
    and "setMoralErro({ tipo: \"recusa\"" in _TBC,
    "decisao: recusa e silencio sao estados DISTINTOS — 'o servidor disse nao' "
    "e 'nao chegou resposta' pedem coisas diferentes ao jogador")

# (f) a tela tem TRES faces e diz a que nao sabe.
chk('t("explore_desfecho_incerto")' in _TBC and 't("explore_desfecho_rever")' in _TBC,
    "decisao: a tela DIZ 'nao sei' e oferece o caminho de volta (Lei §1)")
chk('{won ? textoVitoria : naoSei ? t("explore_desfecho_incerto") : textoDerrota}' in _TBC,
    "decisao: a derrota so' se escreve quando o servidor a CONFIRMOU — o 'nao "
    "sei' tem rosto proprio")
chk(_TBC.count("<DesfechoRosto ") == 3 and _TBC.count("<MoralErroAviso ") == 3
    and _TBC.count("<MoralResultado ") == 3,
    "decisao: as tres telas usam os MESMOS tres componentes (rosto %d, aviso "
    "%d, resultado %d) — foi a copia a' mao que perdeu o Caminho cristalizado "
    "num deles" % (_TBC.count("<DesfechoRosto "), _TBC.count("<MoralErroAviso "),
                   _TBC.count("<MoralResultado ")))
chk('if (d === "vitoria" && !moral) {' in _TBC and 'setFase("moral");' in _TBC,
    "decisao: se a 2a leitura disser VITORIA a escolha moral volta a ser "
    "oferecida — a consequencia nao se perde por uma resposta que nao chegou")
chk("moral.karma && moral.karma.crystallized" in _TBC
    and _TBC.count("moral.karma && moral.karma.crystallized") == 1,
    "decisao: o Caminho cristalizado e' dito a partir de UM sitio, portanto "
    "nas tres telas — antes estava em duas de tres")

# (g) o rosto do 'nao sei' e' um CARACTERE e nao um emoji. O `tabs.js` esta' no
#     tecto da catraca (§15, 1300/1300): um emoji novo sem porta fa-la subir.
chk('"\u7591"' in _TBC,
    "decisao: o rosto do 'nao sei' e' 疑 (caractere), nao um emoji — o tecto "
    "da catraca nao tem folga nenhuma")

# (h) o dono UNICO do texto de erro ganhou os codigos que chegam a HTTP 200.
_MAPA = _UIC.split("var API_ERR_KEY")[1].split("};")[0] if "var API_ERR_KEY" in _UIC else ""
for _c in ("internal_error", "not_won", "not_your_duel"):
    chk(_c in _MAPA,
        "decisao: `%s` tem frase no dono unico (`API_ERR_KEY`) — um codigo a "
        "200 sem frase sai cru no meio de uma decisao moral" % _c)

# (i) as tres linguas, em paridade.
for _lg in ("pt", "en", "es"):
    for _k in ("explore_desfecho_incerto", "explore_desfecho_rever",
               "npc_cult_moral_silencio", "npc_cult_erro_nao_venceu",
               "npc_cult_erro_nao_e_seu"):
        chk(_k in _locs[_lg], "decisao/i18n: `%s.json` tem `%s`" % (_lg, _k))

# (j) ⚠️ A GUARDA QUE PROVA QUE AS DE CIMA OLHAM PARA O CODIGO. Quatro guardas
#     desta casa ja' ficaram verdes por lerem a PROSA do comentario em vez do
#     codigo. Se o titulo do bloco aparecesse em `_TBC`, tudo acima era suspeito.
chk("A DECISAO QUE NAO SE PERDE" not in _TBC,
    "decisao: `_TBC` esta' mesmo sem comentarios — se nao estivesse, as asserts "
    "de cima podiam estar a ler a prosa que eu proprio escrevi")

# (k) ZERO migration — isto e' render, contrato lido e i18n.
_meu20 = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
          if re.search(r"(?:^|_)(decisao|moral_resolve|desfecho)(?:_|\.)", m, re.I)]
chk(not _meu20, "decisao: nenhuma migration — o servidor ja' dizia tudo (%r)" % (_meu20,))



# ===========================================================================
print("\n=== 21. O FACTO QUE DECIDE A MEDITACAO (owner, 16/09 06:12) ===")
#
# 🔴 O owner fotografou a lista de meditacao a correr e escreveu: *"quero
# algo melhor, algo jogavel, algo que ate' um idiota entra e entenda"*. A tela
# mostrava sete linhas com tres numeros cada (duracao, Qi, multiplicador) e
# NADA que dissesse qual escolher.
#
# ⚠️ Medido no `config.py`: somando `multiplier` x `duration`, a Void rende
# 12,0 **de graca** e a Deep rende 2,5 **por 50 Qi** — a Deep e' dominada em
# todas as dimensoes a partir do reino 4. Logo a UNICA escolha real na tela e'
# *"quero continuar a lutar?"*, e essa e' decidida por `RESTRICTED_MEDITATION`
# (config.py:157), que existe desde sempre e **nunca saiu do `config.py`**.
#
# ⚠️ E' DISCLOSURE, nao balance: nenhum numero muda. O defeito Deep-vs-Void
# fica escrito para o servidor de launch — mexer-lhe em `main` mudava o jogo
# debaixo dos 57.
import config as _CFG
try:
    from core.webserver import _meditation_catalog as _mc
    _CAT = _mc()
except Exception:
    _CAT = None
chk(_CAT is not None and len(_CAT) == 7,
    "trava: o catalogo devolve as 7 modalidades (%s)"
    % (len(_CAT) if _CAT else "FALHOU"))
# 🐛 2026-09-22 — A RESPOSTA MUDOU, e a guarda muda com ela. A sugestao
# do [jogador] mediu que a trava vivia em 6 portas e faltava em 15+: unificou-se pelo
# lado permissivo (ver §25 f2). Logo o catalogo NAO promete uma trava — o que
# esta guarda passa a exigir e' que ele nao volte a prometer sozinho, sem as
# portas voltarem todas ao mesmo tempo.
chk(_CAT is not None and all("restricts_combat" not in r for r in _CAT),
    "trava: o catalogo NAO promete uma trava de combate que ja nao existe "
    "(a promessa e' do `config.py` + as portas, nunca de uma coluna solta)")
chk(_CAT is not None and all(set(r) >= {"key", "duration_minutes", "qi_cost",
                                        "min_realm", "multiplier"} for r in _CAT),
    "trava: as sete linhas continuam com duracao, custo, reino e multiplicador")
# ⚠️ pelo CODIGO, nunca pela prosa: o comentario que explica a remocao
# cita o nome do campo, e a 1a versao desta assert ficou vermelha por causa
# dele (a armadilha registada nesta casa: "a guarda le' a prosa").
chk("row.restricts_combat" not in _UIC,
    "trava: o cliente deixou de LER a coluna que nunca mais recebe dado — "
    "codigo que existe e nunca chega e' a doenca desta casa")

# 🐛 2026-09-22 — as asserts da COLUNA sairam com a coluna (sugestao do
# [jogador], §25 f2). O que ficou de pe' e' o que continua verdade: as sete linhas,
# os seus numeros, e o `config.py` como dono da constante caso ela volte a
# ligar-se em TODAS as portas de uma vez. As frases `onda_med_trava`/
# `onda_med_livre` ficam na i18n — a paridade das tres linguas nao se mexe
# por um texto deixar de ser desenhado.

# ZERO migration: uma chave nova num payload de LEITURA.
_meu21 = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
          if re.search(r"(?:^|_)(restricts_combat|trava|meditation_lock)(?:_|[.])", m, re.I)]
chk(not _meu21, "trava: nenhuma migration — e' uma chave nova num READ (%r)" % (_meu21,))



# ===========================================================================
print("\n=== 22. 至 A CHEGADA — e os erros tontos deste lote ===")
#
# 🔴 MEDIDO a 2026-09-16, no jogo servido a 390x844 com a flag ON:
#
#     rolagem da chegada .... 2.397 px  ->  834 px   (2,8 ecras -> 0,99)
#     portas empilhadas .....      21   ->      0
#     <img> na tela .........       0   ->      1
#
# ⚠️ Esta seccao existe tanto para guardar a chegada como para guardar
# CONTRA MIM. Cada bloco abaixo corresponde a um erro que este lote cometeu e
# que **nenhuma das 880 guardas existentes apanhou** — tres deles so'
# apareceram A OLHAR.

# ── (a) 🔴 O NOME DO JOGADOR E' `dao_name`. O `/player` TEM um campo `name`
#     e ele vale **None** — `name` pertence aos objectos aninhados
#     (`sect.name`, `boss.name`). A tarefa que escrevi para o Astra listou o
#     campo errado, ele implementou-a a' letra, e **a chegada saiu SEM NOME
#     NENHUM com 880 asserts verdes**. O `tabs.js:4192` ja' fazia
#     `player.dao_name || player.name` desde sempre: o codigo sabia, a minha
#     lista e' que nao.
_NOME_NU = []
for _f, _s in (("ui.js", _UIC), ("tabs.js", _TBC)):
    _i = 0
    while True:
        _i = _s.find("player.name", _i)
        if _i < 0:
            break
        # a expressao TEM de trazer o `dao_name` antes, na mesma linha logica
        if "dao_name" not in _s[max(0, _i - 60):_i]:
            _NOME_NU.append("%s@%d" % (_f, _s.count(chr(10), 0, _i) + 1))
        _i += 11
chk(not _NOME_NU,
    "chegada: o nome do jogador NUNCA se le' de `player.name` sozinho (%r) — "
    "esse campo vale `None` no `/player` e a chegada ja' saiu sem nome com 880 "
    "guardas verdes" % (_NOME_NU[:3],))
chk("player.dao_name || player.name" in _UIC,
    "chegada: a cena le' `dao_name` PRIMEIRO, com o `name` so' como recurso")

# ── (b) ⚠️ AS PALAVRAS VIVEM NO i18n. A 1a versao da cena trazia 13 strings
#     inlineadas em pt/en/es dentro do proprio componente — e a culpa era da
#     FRONTEIRA que eu dei ("nao toques em ficheiros partilhados"). Texto fora
#     do `i18n/` nao passa pela guarda de paridade das tres linguas.
_CENA = (_UIC.split("function ChegadaCena(")[1].split(chr(10) + "    function ")[0]
         if "function ChegadaCena(" in _UIC else "")
chk(len(_CENA) > 2000,
    "chegada: `ChegadaCena` foi delimitada (%d chars)" % len(_CENA))
chk("words[LANG]" not in _CENA and 'pt: {' not in _CENA and 'es: {' not in _CENA,
    "chegada: a cena NAO traz uma tabela de linguas a mao — as palavras vivem "
    "em `miniapp/i18n/*.json` como as das outras 24 telas")
chk(_CENA.count('t("chegada_') >= 10,
    "chegada: a cena le' as palavras pelo `t()` (%d chaves) — se isto desabasse "
    "para ~0 a tabela a mao teria voltado" % _CENA.count('t("chegada_'))

# ── (c) A CENA E' MESMO ALCANCADA, e o agregado sai pela MESMA condicao.
#     "Existe no ficheiro" nao e' "chega ao ecra" — 5 recorrencias nesta casa.
chk("<ChegadaCena " in _TBC,
    "chegada: o `HomeTab` RENDERIZA a cena — um componente que existe e nao e' "
    "chamado e' o defeito classico desta casa")
chk("{chegadaOn && (" in _TBC and "{!chegadaOn && (<>" in _TBC,
    "chegada: a cena entra e o agregado das 21 portas sai pela MESMA condicao "
    "— duas condicoes separadas deixariam nascer o estado em que nenhum dos "
    "dois aparece")
chk(_TBC.count("obraOn()") >= 2 and _TBC.count("ondaCultOn()") == 1,
    "chegada: `tabs.js` tem UM leitor da chave-mestra (`obraOn`) e distribui o "
    "booleano — a guarda do §19 apanhou-me a acrescentar um segundo")

# ── (d) 🔴 A ACCAO NAO INVENTA. A regra e' do Astra: *"ausencia de um campo
#     nao e' estado confirmado"*. Um ramo que nao sabe **nao decide**.
_ACAO = (_TBC.split("function acaoDaChegada(")[1].split(chr(10) + "    function ")[0]
         if "function acaoDaChegada(" in _TBC else "")
chk(len(_ACAO) > 800, "chegada: `acaoDaChegada` foi delimitada (%d)" % len(_ACAO))
for _ramo in ("duelo", "meditacao", "recompensa", "avanco", "meditar"):
    chk(('chave:"%s"' % _ramo) in _ACAO,
        "chegada/accao: o ramo `%s` existe — sao os CINCO da [016]" % _ramo)
chk("acao.duelo && acao.duelo.duel_id" in _ACAO,
    "chegada/accao: o duelo confirma-se pela PRESENCA do `duel_id`, nunca pela "
    "ausencia do contrario")
chk("acao.avanco && acao.avanco.eligible === true" in _ACAO,
    "chegada/accao: o avanco exige `eligible === true` — `undefined` e' 'nao "
    "sei' e nao passa num teste de igualdade estrita")
chk("cult && cult.is_meditating === false" in _ACAO,
    "chegada/accao: 'meditar' so' se oferece quando o cliente SABE que nao esta' "
    "a meditar — um `cult` ausente nao promete nada")
chk("return null;" in _ACAO,
    "chegada/accao: quando nenhum ramo confirma ela devolve `null`, e a tela "
    "escreve o motivo SEM botao — um botao que promete o que o servidor vai "
    "recusar e' pior do que nenhum (Lei §1)")

# ── (e) A VIDA. `current_hp` NULL significa CHEIO, e ja' custou um lote.
chk("function vidaDe(p)" in _TBC and "(cur === null || cur === undefined) ? max" in _TBC,
    "chegada: `current_hp` a NULL e' VIDA CHEIA, nunca zero — o `COALESCE(.., 0)` "
    "ja' inventou '69% dos activos sem poder lutar' nesta casa")

# ── (f) as tres linguas, em paridade.
for _lg in ("pt", "en", "es"):
    _faltam = [k for k in ("chegada_acao_duelo", "chegada_acao_meditar",
                           "chegada_sem_acao", "chegada_pedras", "chegada_vida",
                           "chegada_proximo_avanco")
               if k not in _locs[_lg]]
    chk(not _faltam, "chegada/i18n: `%s.json` tem as chaves da chegada (falta %r)"
        % (_lg, _faltam))

# ── (h) 🔴 A CHEGADA E' ALCANCADA PELA NAVEGACAO QUE O OWNER CORRE.
#     O defeito: ela foi construida so' em `home`, e com a `ui_v2` ON — o que
#     ele corre — o hub Eu abre em `hub_eu_screen`. Ela existia, estava certa, e
#     a navegacao dele nunca lhe passava. 6a vez nesta casa que "existe" nao foi
#     "chega", e a 1a em que o sitio errado tinha 415px de tela bonita.
chk('return (tab === "home" || tab === "hub_eu_screen")' in _UIC,
    "chegada: o portao cobre as DUAS portas de entrada — a `home` da barra "
    "antiga E o `hub_eu_screen`, que e' o landing que a `ui_v2` abre")
chk(_TBC.count("<Chegada ") == 2,
    "chegada: as duas entradas chamam o MESMO componente (%d) — escrever a "
    "composicao duas vezes era a Lei 0 §2 dentro do lote que a cumpre"
    % _TBC.count("<Chegada "))
chk("function Chegada({ player, setTab" in _TBC,
    "chegada: ha' um dono unico que busca os dados e monta a accao")

# ── (i) ⚠️ O RETOQUE e' "ja' estou NESTA TELA", nao "ja' estou neste hub".
#     Medido a olhar: o `active` da barra e' verdadeiro para qualquer aba do
#     GRUPO, e a `home` esta' no grupo do Eu — com ele, tocar em "Eu" estando na
#     `home` abria um selector invisivel em vez de LEVAR ao landing.
chk('if (tab === h.landing && typeof onRetoque === "function")' in _UIC,
    "chegada/nav: o retoque compara com o LANDING, nunca com o hub activo")
chk("seletorAberto && (" in _TBC and "onFecharSeletor" in _TBC,
    "chegada/nav: o selector do hub Eu existe e fecha-se ([017] §3)")

# ── (j) 🔴 OS DOIS ATALHOS, e a chave que ENCONTRA a arte.
#     [016] §1: *"Dois, Tecnicas e Equipamento: imagem do item equipado e
#     nome. Sem equipamento, marca propria e 'Nenhum equipado'."*
_WEBPY = rd("core/webserver.py")
chk('"atalhos": atalhos,' in _WEBPY,
    "atalhos: o `home_summary` manda os dois equipados — no MESMO read que a "
    "chegada ja' pede, sem round-trip novo")
chk('"art_key": _t[1],' in _WEBPY and '"art_key": _a[1],' in _WEBPY,
    "atalhos: os dois mandam o `art_key` CANONICO ao lado do nome traduzido — "
    "sem ele o slug sai do nome traduzido e 229 pecas por lingua desaparecem")
chk('_atalho("tecnica", t("chegada_atalho_tecnica"), "sword", "technique"' in _TBC
    and '_atalho("arma", t("chegada_atalho_arma"), "stone", "artifact"' in _TBC,
    "atalhos: o `pieceArt` recebe as chaves LONGAS (`technique`/`artifact`) — "
    "as curtas nao existem no `ART_KIND_PREFIX` e devolvem `null` em silencio")
chk("<CardArt src={arte}" in _TBC,
    "atalhos: a peca desenha-se pelo `CardArt`, o dono unico (Lei F-7 B) — "
    "ele ja' traz o VERSO honesto quando a arte falta, e a guarda dos "
    "renderizadores apanhou-me a escrever uma etiqueta de imagem crua")
# 🔴 TRES estados, e o do meio custou um defeito em producao: uma consulta
# que REBENTA nao pode virar "nenhum equipado". O owner tinha a "Divine Cosmic
# Blade" equipada e a chegada negava-a — porque eu pedi `PlayerArtifact.name`,
# uma coluna que NAO EXISTE (12 colunas na tabela, medido, e `name` nao e' uma).
chk('sabido ? t("chegada_atalho_vazio")' in _TBC
    and 't("chegada_atalho_incerto")' in _TBC,
    "atalhos: `undefined` (nao sei) e `null` (confirmei que nao ha') sao "
    "estados DIFERENTES — dizer 'nenhum equipado' quando a consulta rebentou e' "
    "afirmar o que ninguem mediu")
chk('Object.prototype.hasOwnProperty.call(_at, "arma")' in _TBC,
    "atalhos: o cliente distingue a chave AUSENTE da chave a `null`")
chk("select(PlayerArtifact.name" not in _WEBPY,
    "atalhos: nada pede `PlayerArtifact.name` — essa coluna nao existe, e "
    "pedi-la fazia a consulta rebentar em silencio")
chk('ArtifactCatalog.type == "weapon"' in _WEBPY,
    "atalhos: a arma acha-se pelo `type` do catalogo OU pelo `slot` — o `slot` "
    "e' nullable e o tipo diz o que a peca E'")
chk('atalhos = {}' in _WEBPY,
    "atalhos: o dicionario nasce VAZIO e a chave so' existe quando se sabe")
for _lg in ("pt", "en", "es"):
    chk(all(k in _locs[_lg] for k in ("chegada_atalho_tecnica",
                                      "chegada_atalho_arma",
                                      "chegada_atalho_vazio")),
        "atalhos/i18n: `%s.json` tem as tres frases" % _lg)
# ── (k) 🔴 O SELECTOR DO HUB EU — os tres acabamentos do Astra (§0 do
#     `2026-09-16-e-o-corpo-que-acende.md`), verificados A OLHAR:
#       altura da chegada COM e SEM o selector: 415 px nos dois.
_APPJ2 = rd("miniapp/components/app.js")
chk("<Modal open onClose={onFecharSeletor}" in _TBC,
    "seletor: e' uma SOBREPOSICAO e nao uma seccao em fluxo — *'nao aumenta a "
    "altura da chegada'*. Em fluxo era a pilha 'cena + lista de portas' que o "
    "owner mandou matar, so' que escondida atras de um gesto")
chk('p.key !== "tab_home"' in _TBC,
    "seletor: SETE destinos e nao oito — o 'Inicio' sai, porque a chegada E' "
    "este ecra e a porta levaria o jogador a um sitio identico ao que ja' ve'")
chk("const pathsSeletor = paths.filter" in _TBC,
    "seletor: a lista filtrada e' a que se DESENHA — o `paths` original fica "
    "intacto para o ramo OFF")
# 門 P6 (27/09) — a expressao deixou de acabar no `euSeletor` (a consulta das
# portas entrou depois dele); a guarda passa a ler a EXPRESSAO, nao a linha.
chk(re.search(r"const _anyModalOpen = [^;]*[|][|] euSeletor[^;]*;", _APPJ2),
    "seletor: conta como janela aberta (`_anyModalOpen`) — sem isto o VOLTAR "
    "nativo fechava o webapp INTEIRO em vez do selector")
chk("if (euSeletor) { setEuSeletor(false); return; }" in _APPJ2,
    "seletor: o `_handleBack` descasca-o PRIMEIRO — nada stacka nele")
chk("else setEuSeletor(false);" in _APPJ2,
    "seletor: mudar de hub LIMPA o estado, em vez de o deixar pendurado")

_meu22 = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
          if re.search(r"(?:^|_)(chegada|home_acao|arrival)(?:_|[.])", m, re.I)]
chk(not _meu22, "chegada: nenhuma migration (%r)" % (_meu22,))



# ===========================================================================
print("\n=== 23. A CELESTIAL — o bug do [jogador] (21/09) ===")
#
# 🔴 Report textual: *"Meditating from main UI -> can select Celestial. When
# opening menu meditation (further down the main page), celestial meditation is
# blocked (getting error as I have already fully unlocked celestial laws)"*.
#
# MEDIDO: o `api_meditate_start` recusa a `celestial_dao` com
# `heavenly_laws_complete` (as 100 Leis Celestiais dominadas: a meditacao ja'
# nao tem nada a revelar, e gastava 800 Qi e 8h) e com `needs_first_trial`. A
# aba Celestial sabia. A lista de meditacao do Cultivo NAO: mostrava a
# Celestial escolhivel, o jogador tocava, e o erro chegava CRU — nenhuma das
# duas razoes tinha frase. Duas superficies, duas regras, e o jogador a
# descobrir a certa pelo erro.
_WEB23 = rd("core/webserver.py")
chk("async def _travas_da_meditacao(" in _WEB23,
    "celestial: ha' UM dono das travas por jogador que o catalogo tem de "
    "conhecer")
chk('travas["celestial_dao"] = "heavenly_laws_complete"' in _WEB23
    and 'travas["celestial_dao"] = "needs_first_trial"' in _WEB23,
    "celestial: o dono aplica as DUAS regras que o `start` aplica")
chk("dict(_r, lock_reason=_travas.get(_r[\"key\"]))" in _WEB23,
    "celestial: o catalogo leva `lock_reason` ao lado de cada modalidade")
chk("_travas = await _travas_da_meditacao(session, player, user_id)" in _WEB23,
    "celestial: as travas calculam-se com a sessao ABERTA, antes do retorno")

_MEDMAP = (_UIC.split("var _MED_ERR_KEY")[1].split("};")[0]
           if "var _MED_ERR_KEY" in _UIC else "")
for _c in ("heavenly_laws_complete", "needs_first_trial"):
    chk(_c in _MEDMAP,
        "celestial: `%s` tem frase no mapa de erros da meditacao — antes o "
        "jogador lia o CODIGO" % _c)
chk("if (r.lock_reason && _MED_ERR_KEY[r.lock_reason])" in _UIC,
    "celestial: o motivo da trava que o SERVIDOR conhece vem primeiro")
chk("var locked = !!r.lock_reason" in _UIC,
    "celestial: a linha fica TRANCADA quando o servidor diz que esta' — "
    "nunca escolhivel para depois falhar")
chk("selRow.lock_reason ||" in _UIC,
    "celestial: a seleccao respeita a trava do servidor")
for _lg in ("pt", "en", "es"):
    chk("onda_med_err_leis_completas" in _locs[_lg]
        and "onda_med_err_primeiro_julgamento" in _locs[_lg],
        "celestial/i18n: `%s.json` tem as duas frases" % _lg)



# ===========================================================================
print("\n=== 24. A LATERAL DO PC (P5, [017] \u00a71) ===")
#
# \U0001f534 O QUE ESTAVA AQUI, medido: 24 destinos = 1.131 px de trilho, TODOS
# abertos ao mesmo tempo, num ecra de 720 px — oito por baixo da dobra. A mesma
# doenca da chegada, do lado do PC. MEDIDO a 1440x900 depois: 216 px e 12
# botoes (so' o Eu aberto); recolhida, 64 px e 6 botoes com nome acessivel.
# 門 P6 (27/09) — a lateral recebe o jogador (as portas) e o gesto da consulta.
chk("function SideRailHubs({ tab, setTab, player, onPorta })" in _UIC,
    "lateral: existe a lateral de HUBS da [017]")
chk("const largura = recolhida ? 64 : 216;" in _UIC,
    "lateral: 216 px aberta e 64 px recolhida — os numeros da decisao, nao os "
    "236 que o trilho antigo tinha")
chk("const aberto = hubActivo === h.key;" in _UIC
    and "{aberto && !recolhida && itens.map(" in _UIC,
    "lateral: SO' o hub activo expoe os destinos — e' isto que impede o trilho "
    "de voltar a 24 portas abertas ao mesmo tempo")
chk("aria-label={recolhida ? t(h.label_key) : undefined}" in _UIC,
    "lateral: recolhida, o nome sai do ECRA mas fica na ARVORE — cinco "
    "pictogramas mudos seriam uma regressao de acessibilidade")
chk('window.localStorage.getItem(_RAIL_PREF) === "1"' in _UIC
    and "catch (e) { return false; }" in _UIC,
    "lateral: a preferencia guarda-se, e uma leitura que rebenta abre expandida "
    "em vez de partir o jogo")
_APP24 = rd("miniapp/components/app.js")
chk("? <SideRailHubs tab={tab} setTab={setTab} player={player} onPorta={abrirPorta} />" in _APP24
    and ": <SideRail tab={tab} setTab={setTab} />" in _APP24,
    "lateral: UMA unica navegacao global por composicao — a nova com a onda ON, "
    "a de sempre com ela OFF, nunca as duas")
for _lg in ("pt", "en", "es"):
    chk("rail_recolher" in _locs[_lg] and "rail_expandir" in _locs[_lg],
        "lateral/i18n: `%s.json` tem os dois rotulos do interruptor" % _lg)


# ===========================================================================
print("\n=== 25. 星 O CORPO QUE ACENDE (2.1) e A JANELA DA PREVIA ===")
#
# A primeira prova do idioma que o owner pediu para o jogo inteiro (16/09):
# *"refina o corpo, la tem o desenho do cultivador, e cada vez que melhoras
# abre algo ou ilumina, como estrelas"*. Desenho do Astra
# (`Olho/Astra/2026-09-16-e-o-corpo-que-acende.md` §2); gramatica da previa
# aprovada (`newapp/preview/portal-v1.html`).
#
# MEDIDO a 21/09, servido a 390x844 e 1440x900 pelos MOTORES reais:
#   forjar  -> "Nivel 2 -> 3 (+1) · Defesa +13% -> +21% · Poder 54.466 -> 58.322"
#   romper com sorte a falhar -> "Nao abriu · 51% -> 61%", ZERO pontos novos
#   arte bloqueada -> silhueta + 12 pontos + numeros + accao, 0 imagens
#   a janela dos Avisos: 912x720 -> 640x279 (PC) · 366x660 -> 366x259 (telemovel)
#   o selector do Eu (entregue a 21/09): cartao 80px/corpo 28px -> 332/262
_TB25 = rd("miniapp/components/tabs.js")
_UI25 = rd("miniapp/components/ui.js")


def _fn25(src, assinatura):
    """O corpo de uma funcao (ate' a' proxima do mesmo nivel), SEM comentarios
    de linha — a guarda le' o CODIGO, nunca a prosa que o explica (a licao de
    13/09: uma trava proibida escondida num comentario deixava a guarda verde)."""
    if assinatura not in src:
        return ""
    corpo = src.split(assinatura, 1)[1]
    # ⚠️ Uma funcao de TOPO (4 espacos) termina na proxima de topo — as suas
    # funcoes internas (6 espacos) fazem parte dela. A 1a versao cortava o
    # `CorpoFigura` no `tracado()` interno, antes do `return`, e a guarda ficou
    # vermelha a dizer que a figura nao usava o dono — sobre metade da funcao.
    _topo = not assinatura.startswith("      ")
    _fins = ((chr(10) + "    function ", chr(10) + "    var ") if _topo else
             (chr(10) + "      async function ", chr(10) + "      function ",
              chr(10) + "    function ", chr(10) + "    var "))
    for fim in _fins:
        corpo = corpo.split(fim, 1)[0]
    return chr(10).join(l for l in corpo.split(chr(10)) if not l.strip().startswith("//"))


# ── (a) o comportamento, a serio: as TRES leituras sob node, alimentadas pelos
#     MOTORES do servidor (nunca por numeros meus).
import types as _types25
import asyncio as _aio25
import core.body_tempering_engine as _bte25
import core.meridian_engine as _mer25

_orig25 = (_bte25._cultivo_corpo_on, _mer25.corpo_profundo_on, _mer25.refine_place_view)
_bte25._cultivo_corpo_on = lambda *a, **k: True
_mer25.corpo_profundo_on = lambda *a, **k: True


async def _sem_lugar25(*a, **k):
    return None
_mer25.refine_place_view = _sem_lugar25


def _jog25(**kw):
    base = dict(realm=3, mortal_body_level=0, mortal_temper_progress=0,
                spirit_stones=10 ** 9, qi=10.0 ** 6, qi_capacity=10.0 ** 6,
                battle_power=10 ** 8, body_tempering_level=0,
                body_tempering_progress=0, celestial_essence=0,
                meridians_opened={}, meridian_ritual=None, hunt_essence=0,
                language="pt", telegram_id=1)
    base.update(kw)
    return _types25.SimpleNamespace(**base)


try:
    _dados25 = {"canais_do_motor": [c["key"] for c in _mer25.MERIDIAN_CHANNELS],
                "mortal": [], "transf": [], "mer": []}
    for _lv in range(0, 8):
        _dados25["mortal"].append({"rotulo": "R6 nivel %d" % _lv,
                                   "bc": _bte25.project_body_for_display(_jog25(realm=6, mortal_body_level=_lv))})
    _dados25["mortal"].append({"rotulo": "limite do reino (R3, 4/7)",
                               "bc": _bte25.project_body_for_display(_jog25(realm=3, mortal_body_level=4))})
    _dados25["mortal"].append({"rotulo": "apice (R8, 5/7)",
                               "bc": _bte25.project_body_for_display(_jog25(realm=8, mortal_body_level=5))})
    for _rot, _kw in (("R3 trancado", dict(realm=3)),
                      ("R7 0/12", dict(realm=7)),
                      ("R8 5/12", dict(realm=8, body_tempering_level=5)),
                      ("R7 9/12, celeste pede R8", dict(realm=7, body_tempering_level=9)),
                      ("R8 12/12", dict(realm=8, body_tempering_level=12))):
        _p = _jog25(**_kw)
        _dados25["transf"].append({"rotulo": _rot,
                                   "d": _bte25.project_tempering_status(_p, total_battle_power=_p.battle_power)})
    _chaves = [c["key"] for c in _mer25.MERIDIAN_CHANNELS]
    for _rot, _n, _rit in (("0 abertos", 0, False), ("7 abertos + ritual", 7, True), ("12 abertos", 12, False)):
        _op = {k: {"opened_at": "2026-09-01T00:00:00+00:00"} for k in _chaves[:_n]}
        _ri = ({"channel": _chaves[_n], "stage": "circulate", "started_at": "2026-09-21T00:00:00+00:00",
                "ends_at": "2026-09-21T01:00:00+00:00", "attempts": 1} if _rit else None)
        _dados25["mer"].append({"rotulo": _rot, "d": _aio25.run(_mer25.project_meridians(
            None, _jog25(realm=8, meridians_opened=_op, meridian_ritual=_ri), lang="pt"))})
    _gerou25 = True
except Exception as _e25:
    print("   geracao das cargas falhou: %r" % (_e25,))
    _dados25, _gerou25 = {}, False
finally:
    _bte25._cultivo_corpo_on, _mer25.corpo_profundo_on, _mer25.refine_place_view = _orig25

chk(_gerou25 and len(_dados25.get("mortal", [])) == 10,
    "corpo: as cargas vem dos MOTORES (`project_body_for_display`, "
    "`project_tempering_status`, `project_meridians`) — 10 mortais, 5 "
    "transformacoes, 3 mapas de canais")
chk(_gerou25 and all(c["bc"].get("tier_keys") == [k for k, _e in _bte25.MORTAL_TIERS]
                     for c in _dados25["mortal"]),
    "corpo/servidor: `tier_keys` e' a ORDEM do dono (`MORTAL_TIERS`) — a ordem "
    "alfabetica do i18n nao prova a sequencia do jogo")
chk(_gerou25 and all(len(c["d"]["levels"]) == _bte25.MAX_TEMPERING_LEVEL
                     for c in _dados25["transf"]),
    "corpo/servidor: `levels` traz os %d niveis das Transformacoes"
    % _bte25.MAX_TEMPERING_LEVEL)
if node:
    _r25 = subprocess.run([node, os.path.join(ROOT, "scripts", "_test_corpo.js")],
                          input=_json.dumps(_dados25), capture_output=True,
                          text=True, encoding="utf-8")
    _l25 = [l for l in (_r25.stdout or "").rstrip().split(chr(10)) if l.strip()]
    print("   (%d asserts das leituras do Corpo sob node)" % len(_l25))
    for _l in _l25:
        if _l.startswith("FAIL"):
            print("   " + _l)
    chk(_r25.returncode == 0 and len(_l25) > 60,
        "corpo: as TRES leituras REAIS, sob node, contra os motores — sem dados "
        "nunca e' zero, o maximo do payload manda, a ordem dos canais nao "
        "desloca conquistas (%d asserts)" % len(_l25))
else:
    chk(True, "node ausente: fica o contrato de fonte abaixo")

# ── (b) o Corpo e' ALCANCADO pela chave-mestra, e o ramo de sempre fica.
_DESP = _fn25(_TB25, "    function BodyTemperingTab({ player, onPlayerRefresh }) {")
chk("if (obraOn()) return <CorpoQueAcende" in _DESP
    and "return <BodyTemperingClassic" in _DESP and "useState" not in _DESP,
    "corpo: a aba despacha pela chave-mestra, SEM hooks (a condicao pode mudar "
    "quando o manifesto chega) — a figura com a obra ON, o Corpo de sempre OFF")
chk("    function BodyTemperingClassic({ player, onPlayerRefresh }) {" in _TB25,
    "corpo: o ramo OFF continua inteiro (OFF-identidade provada byte a byte a 21/09)")

# ── (c) SO' A CONFIRMACAO ACENDE. A regra que o Astra escreveu contra os
#     dois: *"uma tentativa falhada, um ritual iniciado, um timeout e uma
#     simples reentrada nao conquistam um ponto"*.
_ROMPER = _fn25(_TB25, "      async function romperCanal() {")
_INICIAR = _fn25(_TB25, "      async function iniciarRitual() {")
_TEMPERAR = _fn25(_TB25, "      async function temperar() {")
_ASCENDER = _fn25(_TB25, "      async function ascender() {")
chk(len(_ROMPER) > 400 and len(_INICIAR) > 300 and len(_TEMPERAR) > 400 and len(_ASCENDER) > 400,
    "corpo/luz: as quatro accoes foram delimitadas (%d/%d/%d/%d)"
    % (len(_ROMPER), len(_INICIAR), len(_TEMPERAR), len(_ASCENDER)))
_cond = "if (res && res.ok === true && res.opened === true) {"
chk(_cond in _ROMPER and _ROMPER.index("setAcende(") > _ROMPER.index(_cond)
    and _ROMPER.index("setAcende(") < _ROMPER.index("} else if (res && res.ok === true) {"),
    "corpo/luz: o canal so' acende com `ok:true` E `opened:true` — o `ok:true` "
    "com `opened:false` e' a FALHA honesta e cai no ramo que nao acende")
chk("setAcende(" not in _INICIAR,
    "corpo/luz: iniciar o ritual NAO acende nada — e' uma espera, nao um canal")
for _nm, _fsrc in (("temperar", _TEMPERAR), ("ascender", _ASCENDER), ("romperCanal", _ROMPER)):
    chk("catch (e)" in _fsrc and "setAcende(" not in _fsrc.split("catch (e)", 1)[1],
        "corpo/luz: `%s` — um erro de rede/timeout NAO acende (reconcilia antes "
        "de deixar gastar de novo)" % _nm)
chk(all("res.ok === true" in _f.split("setAcende(")[0] for _f in (_TEMPERAR, _ASCENDER)),
    "corpo/luz: forjar e ascender so' acendem depois de `res.ok === true` — "
    "nunca por ausencia de erro")
chk("await reconciliar(" in _TEMPERAR and "await reconciliar(" in _ASCENDER
    and "await reconciliar(" in _ROMPER and "await reconciliar(" in _INICIAR,
    "corpo: uma resposta que nao chegou reconcilia com o servidor ANTES de "
    "deixar repetir uma accao que consome recursos")

# ── (d) UMA figura, UM dono da pintura: o modo `diagrama` do CultivatorFigure.
_FIG = _fn25(_TB25, "    function CorpoFigura(")
chk("<CultivatorFigure diagrama" in _FIG and "<img" not in _FIG,
    "corpo: a figura e' o `CultivatorFigure` em modo DIAGRAMA — a 1a versao "
    "pintou a imagem por conta propria e a F-7 (B) contou o segundo dono")
_CF = _fn25(_UI25, "    function CultivatorFigure(")
chk("if (diagrama) {" in _CF and "meditating &&" not in _CF.split("if (diagrama) {")[1].split("return (")[0],
    "corpo: o modo diagrama NAO depende de `meditating` — a figura em repouso "
    "nao finge meditacao")

# ── (e) A JANELA DA PREVIA (owner, 21/09): *"Todos modals etc. Bom a previa
#     que eu VI. quero aquilo."*
_MOD = _fn25(_UI25, "    function Modal({")
chk('const bodyFlex = _conteudo ? "0 1 auto" : "1 1 0";' in _MOD and "flex: bodyFlex," in _MOD,
    "janela: com altura automatica o corpo NAO tem base zero — o selector do "
    "Eu abria com 80px e os sete destinos escondidos numa faixa de 28px")
chk("const _conteudo = !fs && (compact || (_onda && _cabe));" in _MOD,
    "janela: a altura automatica so' quando o conteudo CABE (medido); quando "
    "nao cabe, a altura fixa — o caminho que rola no WebKit do iPhone")
chk("c.offsetTop - base + c.offsetHeight" in _MOD and "getBoundingClientRect" not in _MOD,
    "janela: a medida e' de LAYOUT — o rectangulo transformado da animacao de "
    "entrada mentia (741px pareciam 710 e a janela ficava presa em 'cabe')")
chk("if (onda) return `min(${Math.round(d * 1.6)}px, 1120px, 88vw)`;" in _UI25,
    "janela: no PC a escala da previa (380 -> 608, os 610 dela), mantendo a "
    "proporcao entre janelas")
chk("...(_onda && !fs ? semMoldura(cardStyle) : cardStyle)," in _MOD,
    "janela: a MOLDURA e' do dono — com a onda, o gradiente de cada sitio (a "
    "Fundacao pintava-se de azul) deixa de repintar 84 janelas")
chk("if (!_onda || fullScreen || open === false) return undefined;" in _MOD,
    "janela: com a onda OFF a medida nem corre — OFF-identidade (provada byte "
    "a byte a 21/09: HOME, Corpo e a janela IGUAIS ao HEAD)")

# ── (f) as palavras vivem no i18n, nas tres linguas — contadas no CODIGO.
# (um prefixo DINAMICO — `"corpo_explica_" + cam` — nao e' uma chave: as tres
#  que ele forma entram pelo nome)
_usadas25 = sorted((set(k for k in re.findall(r'"(corpo_[a-z0-9_]+)"', _TB25) if not k.endswith("_"))
                    - {"corpo_profundo"}) | {"corpo_explica_mortal", "corpo_explica_transf",
                                             "corpo_explica_mer"})
chk(len(_usadas25) >= 60,
    "corpo/i18n: o codigo pede %d chaves `corpo_*` — se isto desabasse, o "
    "regex partiu-se e a guarda de baixo ficava verde sobre o vazio" % len(_usadas25))
for _lg in ("pt", "en", "es"):
    _falta25 = [k for k in _usadas25 if k not in _locs[_lg]]
    chk(not _falta25, "corpo/i18n: `%s.json` tem as %d chaves do Corpo (falta %r)"
        % (_lg, len(_usadas25), _falta25[:4]))

# ── (f2) 🐛 A SUGESTAO DO [jogador] (22/09 21:50): *"when meditating, I can do Arena
#     battle but not NPC battle. Why? Arena eventually takes me to NPC battle"*.
#     CONTADO antes de mexer: a trava `RESTRICTED_MEDITATION` vivia em **6**
#     portas (duelo NPC, cultivador NPC, duelo NPC do chat, masmorras entrar/
#     avancar/varrer, exploracao) e faltava em mais de **15** — Arena, duelo
#     PvP, chefe mundial, guerra de seita, julgamento celestial, bestas. A
#     mesma accao com duas regras, que e' o MESMO defeito do bug da Celestial
#     que ele apanhou a 21/09. Unificou-se pelo lado que nao tira nada a
#     ninguem, e o `main` ja' tinha perdido duas destas travas em 2026-05-17.
_RM = []
for _dir in ("core", "handlers"):
    for _f in sorted(os.listdir(os.path.join(ROOT, _dir))):
        if not _f.endswith(".py"):
            continue
        for _i, _l in enumerate(rd(_dir + "/" + _f).split(chr(10)), 1):
            if "RESTRICTED_MEDITATION" in _l and not _l.strip().startswith("#"):
                _RM.append("%s/%s:%d" % (_dir, _f, _i))
chk(not _RM,
    "meditacao/combate: ZERO portas travam por meditar — uma regra que vive em "
    "6 sitios e falta em 15 e' a mesma accao com duas regras (%r)" % (_RM[:4],))
chk('"restricts_combat"' not in rd("core/webserver.py"),
    "meditacao/combate: o catalogo deixou de prometer que cinco praticas "
    "trancam o combate — a promessa deixou de ser verdade")
chk("RESTRICTED_MEDITATION" in rd("config.py"),
    "meditacao/combate: a constante fica no `config.py` (o dono unico) para "
    "quem a quiser voltar a ligar em TODAS as portas de uma vez")

# ── (g) 🐛 O REPORT DO [jogador] (22/09): a Vida do web "atras" da do Telegram.
#     MEDIDO em producao (so' leitura): o vinculo estava CERTO — a conta Google
#     abre o mesmo `490009047`, no mesmo mundo (s2). O que ficava para tras era
#     o SEPARADOR: ao voltar a ficar visivel o poll recomecava do zero (30s de
#     valor velho a' vista), e mudar de ecra nao voltava a pedir o jogador.
#     Provado no browser: regresso 0 -> 1 pedido; navegar 1 -> 2; navegar de
#     novo em <10s continua 2.
_UVI = _fn25(_UI25, "    function useVisibleInterval(fn, ms) {")
chk('window.addEventListener("focus", onFocus);' in _UVI
    and "regresso(); start();" in _UVI
    and "if (Date.now() - ultimo > 2000) tick();" in _UVI,
    "frescor: voltar ao separador (ou a' janela) pede JA' — o intervalo nao "
    "espera mais `ms` com o valor velho a' vista; trava de 2s contra o par "
    "visibilitychange+focus")
_APP25 = rd("miniapp/components/app.js")
chk("if (Date.now() - _ultimoPlayerRef.current > 10000) loadPlayer();" in _APP25
    and "}, [tab]);" in _APP25.split("_ultimoPlayerRef.current > 10000")[1][:200]
    and "_ultimoPlayerRef.current = Date.now();" in _APP25,
    "frescor: mudar de ecra refresca o jogador (trava de 10s) — antes a Vida "
    "ficava com a idade do ultimo poll")

_meu25 = [m for m in os.listdir(os.path.join(ROOT, "migrations"))
          if re.search(r"(?:^|_)(corpo|body_map|janela)(?:_|[.])", m, re.I)]
chk(not _meu25, "corpo: nenhuma migration (%r)" % (_meu25,))

# ═══ §26 — 至 A MACANETA: a chegada passa a DIZER que ha' sete destinos ═══════
#
# ORDEM DO OWNER, 2026-09-23, textual: *"como vou encontrar corpo etc. (...)
# tenho que clicar 2 vezes no eu pra abrir o menuzinho pra ver o corpo"*.
#
# 🔴 MEDIDO antes de escrever uma linha: o selector dos sete destinos do Eu so'
# abre ao RETOCAR `SELF` **ja' estando na chegada** (`tab === h.landing`), e a
# chegada nao tinha **uma unica palavra** a dizer que ele existe. O ecra mostrava
# cena + Vida/Qi + Proximo avanco + um botao + dois atalhos (Tecnica, Arma).
# Corpo, Celestial, Parceiro e Conquistas — quatro destinos — sem nome em lado
# nenhum. Uma porta que existe e nao se anuncia e' a Lei §1 partida, e falha o
# criterio do owner (*"que ate' um idiota entra e entende"*) por um gesto que
# ninguem lhe ensinou.
#
# A correccao e' UMA linha de 44px que NOMEIA o que ha' — nao a pilha de 21
# portas de volta (a [016] §1 matou-a, 2.397px -> 415px). Quem abre continua a
# ser a sobreposicao.
_MAC26 = _fn25(_UI25, "    function ChegadaCena({ p, cult, onAgir, atalhos, wide, notifCount, onSino, onLoja, onPerfil,")
_APP26 = rd("miniapp/components/app.js")

chk('className="chegada-portas-btn"' in _MAC26
    and 't("chegada_portas_rotulo")' in _MAC26,
    "macaneta: a chegada tem a linha que nomeia os destinos do Eu — sem ela o "
    "Corpo so' se alcanca por um duplo toque que nada no ecra ensina")

# ⚠️ A guarda que IMPORTA: os nomes tem de sair do MESMO array que a
# sobreposicao abre. Dois donos da lista divergem sempre (Lei 0 §2) e o modo de
# falha e' silencioso — a linha anuncia seis destinos e o selector abre sete.
# 門 P6 (27/09) — a lista continua a ser UMA, mas passou por um dono que aplica
# a regra do marco (`euPortasVisiveis`): a linha e a sobreposicao leem os dois
# o MESMO resultado dele. A guarda segue a indireccao em vez de a baixar — e o
# `_test_portas.js` prova, a correr, que os nomes sao exactamente as portas do
# selector (`nomes.length === visiveis.length`).
_EU25 = _fn25(_TB25, "    function HubEuScreen(")
chk("const eu = euPortasVisiveis(player, pathsSeletor);" in _EU25
    and "const pathsVisiveis = eu.visiveis;" in _EU25
    and "const nomesMacaneta = eu.nomes;" in _EU25
    and "portas={nomesMacaneta}" in _EU25
    and "{pathsVisiveis.map(p => {" in _EU25,
    "macaneta: os nomes da linha saem do MESMO `pathsSeletor` que a "
    "sobreposicao abre — uma lista, um dono")

# ⚠️ E so' na composicao ESTREITA. Medido a 1440x900 a OLHAR: no PC a lateral
# (P5) ja' nomeia os sete, e a linha punha-os uma SEGUNDA vez no mesmo ecra —
# a duplicacao de identidade que o Astra mandou matar.
chk("{(!wide && portas && portas.length && onPortas) ? (" in _MAC26,
    "macaneta: a linha so' aparece na composicao estreita — no PC a lateral ja' "
    "nomeia os sete e duas declaracoes no mesmo ecra e' a duplicacao proibida")

# ⚠️ E o fio TEM de chegar do principio ao fim. Ligar so' o `HubEuScreen`
# deixava o botao a existir no codigo e a nao abrir nada.
chk('onAbrirSeletor={() => { haptic("select"); setEuSeletor(true); }}' in _APP26,
    "macaneta: o `onAbrirSeletor` nasce no App (o dono do estado do selector)")
chk("seletorAberto, onAbrirSeletor," in _TB25,
    "macaneta: o `HubEuScreen` recebe o abridor")
# ⚠️ 2026-09-27 (P7) — a assinatura le-se pelo que EXIGE, nao pela virgula
# final: o P7 acrescentou `onPlayerRefresh` a' `Chegada` e o texto exacto
# `portas, onPortas }) {` ficou vermelho sem nada estar partido.
chk(re.search(r"function Chegada\(\{[^}]*\bportas, onPortas\b[^}]*\}\) \{", _TB25)
    and "portas={portas} onPortas={onPortas}" in _TB25,
    "macaneta: a `Chegada` encaminha as portas para a cena — o fio inteiro, "
    "App -> HubEuScreen -> Chegada -> ChegadaCena")

# ⚠️ As palavras vivem no i18n, nas TRES linguas (a licao da chegada: texto
# inlineado no componente nao passa pela guarda de paridade).
_locs26 = {}
for _lg26 in ("pt", "en", "es"):
    with io.open(os.path.join(ROOT, "miniapp", "i18n", _lg26 + ".json"), encoding="utf-8") as _f26:
        _locs26[_lg26] = json.load(_f26)
chk(all("chegada_portas_rotulo" in _locs26[_l26] and "chegada_portas_mais" in _locs26[_l26]
        for _l26 in ("pt", "en", "es")),
    "macaneta: as duas palavras existem nas tres linguas")
chk("{n}" in _locs26["pt"]["chegada_portas_mais"],
    "macaneta: `chegada_portas_mais` leva o `{n}` — sem ele o jogador le' "
    "'mais' e nao sabe mais quantos")


# ═══ §27 — 語 O NOME "W" DO [jogador]: quem o escreveu foi o GOOGLE ════════════════
#
# O report: o MESMO jogador, ao mesmo tempo, com o nome "C" no Telegram e "W" no
# browser. A busca em producao (so' leitura) nao achou nenhum "W" em lado nenhum
# — mesmo `player_id`, mesmo mundo, sem personagem "W". **Porque nos nunca
# escrevemos um.**
#
# A captura que ele mandou a 23/09 fechou o caso: ao lado do cadeado, a barra do
# Chrome com "PORTUGUESE" — o tradutor automatico LIGADO. E o jogo dava-lhe dois
# motivos para isso:
#
#   1. `<html lang="pt-BR">` FIXO no `/app` e nunca actualizado, enquanto o
#      `/login` (`lang="{{LANG}}"`) e a vitrine (`documentElement.lang = ...`)
#      ja' diziam a verdade. Um jogador em ingles abria uma pagina que JURAVA
#      ser portuguesa ⇒ o browser oferece traduzir.
#   2. ZERO `translate="no"` no cliente inteiro ⇒ ao aceitar, o tradutor
#      reescreve todos os nos de texto. Um nome proprio nao se traduz: corrompe.
#
# PROVADO a olhar, nas duas linguas: jogador `en` ⇒ `<html lang="en">`;
# jogador `pt` ⇒ `pt-BR` (sem regressao) e o nome intacto.
_IDX27 = rd("miniapp/index.html")
_TBS27 = rd("miniapp/components/tabs.js")

chk('translate="no"' in _IDX27 and 'class="notranslate"' in _IDX27,
    "nome/W: a raiz do jogo esta' marcada contra o tradutor do browser — sao "
    "**73 sitios** so' com `dao_name` (mais tecnicas, itens e bestas, cujos "
    "nomes a arte ainda usa); marcar um a um e' a ligacao a' mao que a Lei 0 §2 "
    "proibe, e bastava esquecer um")

# 🔴 A GUARDA QUE MORDE: o dono unico. `LANG` tinha TRES escritores e nenhum
# dizia ao browser qual era a lingua. Se um deles voltar a escrever `LANG = ...`
# a' mao, o `<html lang>` fica para tras e o convite do tradutor volta —
# silenciosamente, porque o jogo continua na lingua certa.
chk("function definirLang(v) {" in _UI25
    and "document.documentElement.lang = v === \"pt\" ? \"pt-BR\" : v;" in _UI25,
    "nome/W: existe UM dono da lingua, e ele actualiza o `<html lang>`")

_escritores27 = []
for _f27, _src27 in (("ui.js", _UI25), ("tabs.js", _TBS27), ("app.js", _APP26)):
    for _m27 in re.finditer(r"^\s*(?!//).*\bLANG\s*=\s*(?!=)", _src27, re.M):
        _ln27 = _src27[:_m27.start()].count(chr(10)) + 1
        _txt27 = _m27.group(0).strip()
        # a declaracao inicial e a atribuicao DENTRO do dono sao as unicas legitimas
        if _txt27.startswith("var LANG =") or "LANG = v;" in _src27[_m27.start():_m27.start() + 40]:
            continue
        _escritores27.append("%s:%d" % (_f27, _ln27))
chk(not _escritores27,
    "nome/W: ninguem escreve `LANG` fora do dono (`definirLang`) — %r escreve "
    "a lingua do JOGO sem dizer a do DOCUMENTO, que e' exactamente o buraco "
    "por onde o tradutor entrou" % (_escritores27,))

chk("definirLang(data.language)" in _APP26 and "definirLang(res.language)" in _TBS27,
    "nome/W: os dois escritores que restavam (`/player` e o `world_start`) "
    "passam pelo dono")

# ⚠️ E as outras duas superficies nao podem regredir para o `lang` fixo.
chk('<html lang="{{LANG}}">' in rd("miniapp/login.html"),
    "nome/W: a porta continua a declarar a lingua que serviu")
chk("document.documentElement.lang" in rd("miniapp/vitrine.html"),
    "nome/W: a vitrine continua a corrigir a lingua em runtime")




# ══════════════════════════════════════════════════════════════════════════
# §28 — 武 O COMBATE É UMA CENA (2026-09-23)
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 A GUARDA DESTE LOTE TEM DE MORDER NO **PAYLOAD**, E NÃO NA CHAMADA, e isso
# não é uma preferência de estilo — é a correcção de um erro medido.
#
# A guarda de 14/09 (`_test_relatos_0814.py §8`) conta que *toda chamada do cliente a
# `pieceArt` leva a chave*. E leva: `pieceArt("technique", tech.name,
# tech.art_key)` está escrito nos três sítios. Só que `tech.art_key` era
# `undefined` — porque o **servidor nunca o mandava**. A guarda ficou VERDE por
# cima de 129 artes por língua invisíveis, durante 9 dias.
#
# Afirmar sobre a chamada não é afirmar sobre o payload. Por isso o §28.1
# EXTRAI o serializador real do `webserver.py` e EXECUTA-O, e o §28.2 chama o
# `get_duel_state` real. O que se mede é o dicionário que sai, não o texto que
# o produz.
print("\n=== 28. 武 O COMBATE É UMA CENA ===")

import ast as _ast28

_WS28 = rd("core/webserver.py")
_DUEL28 = rd("core/duel_engine.py")
_UI28 = _sem_prosa_js(_UIM)
_TB28 = _sem_prosa_js(_TBM)

# ── 28.1 — A CHAVE CHEGA AO PAYLOAD, e a arte encontra-se nas TRÊS línguas ──
#
# Extrai `_serialize_learned` do `_build_combat_loadout_payload` e corre-o
# contra os 129 seeds, com o i18n REAL e com o `slugify` do `gen_art.py` (o
# dono Python do slug — a lição de 15/09: `"ú".isalnum()` é True em Python e
# falso em JS, e uma réplica à mão do slug do cliente mentiria numa peça).
_alvo28 = [n for n in _ast28.walk(_ast28.parse(_WS28))
           if isinstance(n, (_ast28.FunctionDef, _ast28.AsyncFunctionDef))
           and n.name == "_serialize_learned"]
chk(len(_alvo28) == 1,
    "cena/payload: existe UM `_serialize_learned` no webserver (%d)" % len(_alvo28))

_src28 = _ast28.get_source_segment(_WS28, _alvo28[0])
from core.i18n import catalog_text as _ct28
from core.combat_engine import (MASTERY_STAGES as _MS28, TECHNIQUE_GRADES as _TG28,
                                GRADE_UPGRADE_REQS as _GR28, get_next_grade as _gn28)
from scripts.gen_art import slugify as _slug28
from database.seeds.combat_seeds import TECHNIQUES as _TECS28

_m28 = re.search(r"var NIV_ART_INDEX = new Set\(\[(.*?)\]\);", _UIM, re.S)
_IDX28 = set(re.findall(r'"([^"]+)"', _m28.group(1))) if _m28 else set()
chk(len(_IDX28) > 200,
    "cena/payload: o indice de arte do cliente tem %d pecas — se isto desabasse "
    "para ~0 seria o regex partido e nao o problema resolvido" % len(_IDX28))


def _paga28(lang):
    """O `_serialize_learned` REAL, corrido com a lingua `lang`."""
    ns = {"MASTERY_STAGES": _MS28, "TECHNIQUE_GRADES": _TG28,
          "GRADE_UPGRADE_REQS": _GR28, "get_next_grade": _gn28,
          "_scr_grade_cost": lambda n: n,
          "_tname": lambda tid, raw: _ct28(lang, "tech", tid, "name", raw),
          "_tdesc": lambda tid, raw: _ct28(lang, "tech", tid, "desc", raw),
          "_gain_hint": lambda tt: "",
          "technique_root_resonance": lambda e, s: None, "root_set": set()}
    exec(_src28, ns)
    fn = ns["_serialize_learned"]
    saida = []
    for t in _TECS28:
        saida.append(fn((t["id"], 3, 0, True, "common", t["name"], t.get("emoji"),
                         t.get("effect_type"), t.get("effect_value"),
                         t.get("effect_round"), t.get("qi_cost"), t.get("tech_type"),
                         t.get("req_realm"), t.get("description"), None, None, None,
                         t.get("element"))))
    return saida


_ACHA28 = {}
for _lang28 in ("pt", "en", "es"):
    _linhas28 = _paga28(_lang28)
    _sem_chave28 = [d["id"] for d in _linhas28 if not d.get("art_key")]
    chk(not _sem_chave28,
        "cena/payload: `learned[]` em `%s` leva `art_key` nas %d linhas — a "
        "guarda de 14/09 afirmava sobre a CHAMADA do cliente e ficou verde 9 "
        "dias sobre este buraco (faltam: %r)"
        % (_lang28, len(_linhas28), _sem_chave28[:5]))
    _por_chave28 = sum(1 for d in _linhas28
                       if ("tech-" + _slug28(d.get("art_key") or "")) in _IDX28)
    _por_nome28 = sum(1 for d in _linhas28
                      if ("tech-" + _slug28(d["name"])) in _IDX28)
    _ACHA28[_lang28] = (_por_nome28, _por_chave28)
    chk(_por_chave28 == 129,
        "cena/payload: em `%s` a arte encontra-se por `art_key` em %d/129 — "
        "esta e' a MEDICAO, nao a leitura do ficheiro" % (_lang28, _por_chave28))
    # o custo: sem ele a tira de preparo imprimia "0 de Qi", e de graca e' pior
    # do que calado.
    _sem_custo28 = [d["id"] for d in _linhas28 if not d.get("qi_cost")]
    chk(not _sem_custo28,
        "cena/payload: `learned[]` em `%s` leva `qi_cost` — sem ele a tira de "
        "preparo dizia que a arte e' de graca (faltam: %r)"
        % (_lang28, _sem_custo28[:5]))

# ⚠️ A PROVA DE QUE A CHAVE É NECESSÁRIA — e a defesa contra o conjunto vazio.
# Se o nome TRADUZIDO passasse a encontrar a arte em `pt`, ou a medição está
# partida ou alguém renomeou 129 ficheiros; nos dois casos isto tem de parar o
# lote. E em `en` o nome É o canónico, logo os dois números batem — se não
# batessem, o `slugify` deixou de concordar com o cliente.
chk(_ACHA28["pt"][0] == 0 and _ACHA28["es"][0] == 0,
    "cena/payload: pelo NOME TRADUZIDO a arte continua a nao ser encontrada "
    "(pt %d · es %d de 129) — e' por isso que a chave existe"
    % (_ACHA28["pt"][0], _ACHA28["es"][0]))
chk(_ACHA28["en"][0] == 129 and _ACHA28["en"][1] == 129,
    "cena/payload: em `en` nome e chave dao o MESMO resultado (%d/%d) — se nao "
    "dessem, o `slugify` do Python deixou de concordar com o `_artSlug` do JS "
    "(a licao de 15/09, uma peca paga perdida por um acento)"
    % _ACHA28["en"])

# ── 28.2 — O DUELO INTERPRETA NA LEITURA, e não muta o que está GRAVADO ────
#
# O `action_log` e o `fighter_a/b` que chegam ao `get_duel_state` SÃO as colunas
# JSON da sessão. Traduzir no sítio gravaria a tradução no log — e o log é lido
# pelo OUTRO lutador, na outra língua, para sempre. Esta guarda chama a função
# real e compara o objecto de entrada ANTES e DEPOIS.
import copy as _copy28
from core.duel_engine import get_duel_state as _gds28


class _Duelo28:
    id = "x"; state = "waiting_actions"; round_idx = 2; max_rounds = 10
    sudden_death = False; winner_id = None; attacker_id = 1; defender_id = 2
    npc_archetype = None; npc_difficulty = None; pve_source = None
    hp_a = 90; hp_b = 80; hp_a_max = 100; hp_b_max = 100
    combat_qi_a = 50; combat_qi_b = 40; combat_qi_a_max = 100; combat_qi_b_max = 100
    pending_action_a = None; pending_action_b = None; expires_at = None

    def __init__(self):
        self.fighter_a = {"telegram_id": 1, "dao_name": "Kuu", "techniques": [
            {"id": 1, "name": "Thunder Step", "emoji": "x", "qi_cost": 10}]}
        self.fighter_b = {"telegram_id": 2, "dao_name": "Rival", "techniques": []}
        self.action_log = [{"round": 1,
                            "a": {"tech": {"id": 1, "name": "Thunder Step"}, "damage": 5},
                            "b": {"tech": None, "evaded": True}}]


_d28 = _Duelo28()
_antes28 = (_copy28.deepcopy(_d28.action_log), _copy28.deepcopy(_d28.fighter_a))

# (a) sem lingua ⇒ o payload de HOJE, chave a chave (OFF-identidade do contrato)
_hoje28 = _gds28(_d28, 1)
chk(_hoje28["you"]["techniques"][0].get("name") == "Thunder Step"
    and "art_key" not in _hoje28["you"]["techniques"][0],
    "cena/duelo: `get_duel_state(duel, id)` SEM lingua devolve o payload de "
    "hoje — nome cru, zero `art_key` (o default nao muda nada para ninguem)")

# (b) com lingua ⇒ nome LIDO + a chave ao lado, nas duas listas
for _lg28, _esperado28 in (("pt", "Passo do Trovão"), ("en", "Thunder Step"),
                           ("es", "Paso del Trueno")):
    _o28 = _gds28(_d28, 1, _lg28)
    _tt28 = _o28["you"]["techniques"][0]
    _lg_tec28 = _o28["action_log"][0]["a"]["tech"]
    chk(_tt28.get("name") == _esperado28 and _tt28.get("art_key") == "Thunder Step",
        "cena/duelo: `you.techniques[]` em `%s` le' %r e leva `art_key` canonica "
        "(%r / %r)" % (_lg28, _esperado28, _tt28.get("name"), _tt28.get("art_key")))
    chk(_lg_tec28.get("name") == _esperado28
        and _lg_tec28.get("art_key") == "Thunder Step",
        "cena/duelo: cada lado do `action_log` em `%s` tambem — o log GRAVA cru "
        "e e' a LEITURA que interpreta (a licao de 卷獸圖)" % _lg28)
    chk(_o28["action_log"][0]["b"]["tech"] is None,
        "cena/duelo: a esquiva mantem `tech = null` em `%s` — sem tecnica, sem "
        "nome e sem destaque na resolucao (estado honesto)" % _lg28)

# (c) 🔴 O GRAVADO NÃO FOI TOCADO. Se isto ficar vermelho, a tradução está a
#     entrar na coluna JSON e o outro lutador vai ler a língua deste.
chk(_d28.action_log == _antes28[0] and _d28.fighter_a == _antes28[1],
    "cena/duelo: as colunas JSON da sessao ficam INTACTAS depois de tres "
    "leituras em tres linguas — traduzir no sitio gravaria no log que o OUTRO "
    "lutador le'")

# (d) o endpoint passa a lingua de QUEM OLHA (o fio, que um payload nao alcanca
#     sem Postgres).
chk("_duel_lang = await _lang_of(session, user_id)" in _WS28
    and "get_duel_state(duel, user_id, _duel_lang)" in _WS28,
    "cena/duelo: o endpoint `combat/duel_state` le' a lingua do espectador e "
    "passa-a — sem isto o `lang` fica None e nada disto chega ao ecra")
chk(_DUEL28.count("def get_duel_state(") == 1
    and _DUEL28.count("def _tech_lido(") == 1,
    "cena/duelo: UM dono da projeccao e UM dono da leitura da tecnica")

# ── 28.3 — A CENA: as faixas que o Astra desenhou, e o que ela NÃO inventa ──
_CENA28 = _fn_src(_UI28, "function CenaDuelo(")
chk(_UI28.count("function CenaDuelo(") == 1
    and _UI28.count("function CenaEntradaCombate(") == 1
    and _UI28.count("function CenaPreparo(") == 1,
    "cena: as tres pecas existem uma vez cada (cena do duelo, entrada da aba, "
    "tira de preparo)")

# as quatro faixas, pelas classes que as desenham
for _faixa28, _cls28 in (("confronto", "cena-confronto"),
                         ("ultima rodada", "cena-ultima"),
                         ("decisao", "cena-decisao")):
    chk(('className="' + _cls28 + '"') in _CENA28 or ("." + _cls28 + " ") in _CENA28,
        "cena: a faixa `%s` existe na cena" % _faixa28)
# 🔴 A 4a FAIXA — a CONFIRMACAO — vive no RODAPE da janela, e nao no corpo.
# Corrigido a OLHAR, a 390px: no corpo (que rola) o que ficava fixo no pe' era
# **Render**, e a accao principal caia abaixo da dobra. Esta guarda mede-a onde
# ela esta' AGORA, e exige que ela leve o resumo E o alvo de 52px.
_CONF28 = _fn_src(_UI28, "function CenaConfirmacao(")
_MODAL28 = _fn_src(_TB28, "function DuelArenaModal(")
chk("minHeight: 52" in _CONF28 and "minHeight: 80" in _CONF28,
    "cena: a faixa de confirmacao tem os 80px de faixa e o alvo de 52px que o "
    "Astra pediu")
chk('t("duel_btn_submit")' in _CONF28 and 't("duel_btn_forfeit")' in _CONF28
    and 'resumo' in _CONF28,
    "cena: a confirmacao leva o resumo (arte . custo), o ENVIAR e a rendicao "
    "ao lado — uma saida, nunca uma jogada")
chk("<CenaConfirmacao" in _MODAL28 and "cenaEscolha(state, pickEfetivo)" in _MODAL28,
    "cena: o rodape da janela monta a confirmacao e le' a escolha pelo DONO "
    "UNICO (`cenaEscolha`) — o corpo e o rodape nunca escrevem custos "
    "diferentes")
# ⚠️ contar a CHAMADA, nao a assinatura: `"cenaEscolha(state, pick)"` casa
# tambem a linha do `function`, e a 1a versao desta guarda ficou vermelha sobre
# codigo correcto por contar 2 onde ha' 1 definicao + 1 chamada.
chk(_UI28.count("function cenaEscolha(") == 1
    and _CENA28.count("cenaEscolha(state, pick)") == 1,
    "cena: `cenaEscolha` tem UM dono e a cena le' por ele")
chk("cena-confirma" not in _CENA28,
    "cena: e o corpo da cena ja' NAO desenha faixa de confirmacao nenhuma — "
    "duas seriam dois botoes de enviar no mesmo ecra")

# a Vida dos DOIS lados e o Qi do jogador — *"Vida identificada dos dois lados;
# Qi do jogador"*. O `ladoCena` desenha a Vida e e' chamado duas vezes.
chk(_CENA28.count('ladoCena("voce"') == 1 and _CENA28.count('ladoCena("opp"') == 1,
    "cena: os DOIS lados sao desenhados pelo mesmo `ladoCena` — um dono, duas "
    "chamadas (nunca dois blocos parecidos)")
chk('faixa(t("cena_vida")' in _CENA28 and 'faixa(t("cena_qi")' in _CENA28,
    "cena: a Vida (nos dois lados) e o Qi de combate (so' do jogador) tem NOME "
    "e valor inteiro")
# ⚠️ o Qi do ADVERSARIO nao se le': seria informacao de uma regra que este
# contrato nao tem (nao ha' escolha de alvo nem leitura da bolsa do outro).
chk("opp.combat_qi" not in _CENA28,
    "cena: a cena NAO le' o Qi do adversario — chega no payload, mas ler o que "
    "o outro pode pagar seria uma regra que este duelo nao tem")

# 🔴 O LUGAR É TINTA NEUTRA, porque o contrato não diz o lugar (§7.4 medido).
# Nenhuma paisagem de reino entra aqui: seria invencao pintada como se fosse
# dado.
for _proibido28 in ("realmArtUrl", "RealmBackdrop", "HubScene", "hubArtUrl"):
    chk(_proibido28 not in _CENA28,
        "cena: a cena nao usa `%s` — `duel_state` nao tem campo de lugar nem de "
        "reino, logo tinta neutra (ordem do Astra: *o lugar so' e' ilustrado "
        "quando conhecido*)" % _proibido28)

# o destaque da resolucao SO' quando o evento identifica a tecnica
chk("actVoce && actVoce.tech ? actVoce.tech : null" in _CENA28
    and "actOpp && actOpp.tech ? actOpp.tech : null" in _CENA28,
    "cena: o destaque da resolucao so' nasce quando o evento IDENTIFICA a "
    "tecnica — `tech` e' `null` na esquiva, e ai nao ha' destaque nenhum")
chk("if (!a && !b) return undefined;" in _CENA28,
    "cena: esquiva dos DOIS lados ⇒ zero destaques (nunca um lampo sobre o "
    "vazio)")

# ate' quatro mosaicos: o basico + tres. Nem inventa quatro nem elimina as
# excedentes — elas vao para a seleccao VERTICAL.
chk("const VISIVEIS = 3;" in _CENA28,
    "cena: a grelha mostra o basico + 3 artes = quatro opcoes, a medida do "
    "Astra")
chk("cena-grelha--vertical" in _CENA28 and "setTudo(!tudo)" in _CENA28,
    "cena: as excedentes abrem em seleccao VERTICAL, na mesma janela — nunca um "
    "trilho horizontal sem indicacao")
# ⚠️ a ESCOLHA preservada: se a arte escolhida estiver fora das tres primeiras,
# ela passa a' frente. Sem isto o jogador escolhia e a carta dele desaparecia.
chk("if (pick !== 0 && !visiveis.some(tt => tt.id === pick))" in _CENA28,
    "cena: a arte ESCOLHIDA fica sempre a' vista, mesmo que esteja fora das "
    "tres primeiras")

# 🔴 A ARTE PELA CHAVE, nos tres sitios novos. `pieceArt(kind, name, artKey)`
# prefere a chave; passar so' o nome e' o bug de 14/09 outra vez.
_chamadas28 = re.findall(r"pieceArt\(\"technique\",[^)]*\)", _UI28)
_sem_chave_js28 = [c for c in _chamadas28 if "art_key" not in c]
chk(len(_chamadas28) >= 4 and not _sem_chave_js28,
    "cena: as %d chamadas novas a `pieceArt(\"technique\", ...)` no `ui.js` "
    "levam a CHAVE (sem chave: %r)" % (len(_chamadas28), _sem_chave_js28))

# ⚠️ UM desenhador de arte de peca. A guarda F-7 (B) ja' conta os cinco donos;
# aqui garante-se que a chapa da cena e' um INVOLUCRO e nao a sexta.
_CHAPA28 = _fn_src(_UI28, "function CenaChapa(")
chk("<CardArt" in _CHAPA28 and "<img" not in _CHAPA28,
    "cena: a `CenaChapa` e' um involucro do `CardArt` — o verso honesto, o "
    "`onError` e o `lazy` vem do dono, nao de uma segunda chapa (esta guarda "
    "apanhou-me a escrever a sexta)")

# ── 28.4 — ZERO EMOJI NA CENA (a catraca esta' em 1300/1300, sem folga) ────
# O unico emoji legitimo vem do PAYLOAD (`tech.emoji`, uma variavel).
_EMOJI28 = re.compile(
    "[\U0001F300-\U0001FAFF☀-➿⬀-⯿️←-⇿]")
# ⚠️ `_sem_prosa_js` NAO chega aqui: ele segue aspas ANTES de comentarios,
# e um comentario que cite o Astra (com aspas la' dentro) abre uma string falsa
# e deixa passar tudo o que vem depois. Foi assim que esta guarda ficou vermelha
# sobre um "⚠️" que vivia dentro de um comentario JSX. `_strip_js_comments` e'
# o varredor por regex, e nao se engana com aspas.
def _sem_coment28(src):
    return _strip_js_comments(src)


for _nome28, _fonte28 in (("CenaDuelo", _sem_coment28(_CENA28)),
                          ("CenaEntradaCombate", _sem_coment28(_fn_src(_UI28, "function CenaEntradaCombate("))),
                          ("CenaPreparo", _sem_coment28(_fn_src(_UI28, "function CenaPreparo("))),
                          ("CenaChapa", _sem_coment28(_CHAPA28)),
                          ("CenaOpcao", _sem_coment28(_fn_src(_UI28, "function CenaOpcao("))),
                          ("CenaConfirmacao", _sem_coment28(_CONF28))):
    _achados28 = sorted(set(_EMOJI28.findall(_fonte28)))
    chk(not _achados28,
        "cena: `%s` nao tem UM emoji literal — cada glifo e' uma `<Mark>` ou a "
        "arte da peca (achados: %r)" % (_nome28, _achados28))
# ⚠️ e a prova de que o regex ve' alguma coisa: o `tabs.js` esta' cheio deles.
chk(len(_EMOJI28.findall(_TB28)) > 1000,
    "cena: o regex de emoji ainda ve' os %d do `tabs.js` — uma guarda verde "
    "sobre o conjunto vazio nao guarda" % len(_EMOJI28.findall(_TB28)))

# ── 28.5 — O RESULTADO FOI EXTRAÍDO, NÃO REESCRITO ────────────────────────
#
# 🔴 São QUATRO consequências condicionais que lotes anteriores pagaram a
# descobrir, e redesenhar a cena de zero é exactamente como se perdem. O bloco
# saiu para uma variável byte a byte e entra na cena por `prop`.
chk("const blocoResultado = (" in _MODAL28 and "{blocoResultado}" in _MODAL28
    and "resultado={blocoResultado}" in _MODAL28,
    "cena: o resultado e' UMA variavel, usada no ramo antigo E na cena — nunca "
    "dois blocos de resultado a divergir")
# 🔴 CONTAR QUE A STRING EXISTE NAO GUARDA NADA — a bateria de sabotagem
#    apanhou-me: `{false && state.tribute_line && (` deixava esta guarda VERDE
#    com a consequencia morta. E' a mesma familia de 3 guardas minhas de
#    2026-09-12 ("existe" nao e' "chega"). O que se mede e' a FORMA ALCANCAVEL
#    da condicao, e a ausencia de codigo morto por cima dela.
_i_res28 = _MODAL28.index("const blocoResultado = (")
# ⚠️ O corte e' no `return (` DO MODAL, nunca no primeiro `return (` que
#    aparecer: tres das quatro consequencias sao `(() => { ... return (...) })`,
#    e cortar no primeiro truncava o bloco logo depois da PRIMEIRA — foi
#    exactamente o que fez 3 destas guardas ficarem vermelhas sobre codigo
#    correcto. Uma guarda que aponta para o sitio errado com confianca.
_BLOCO28 = _MODAL28[_i_res28:_MODAL28.index("\n      return (", _i_res28)]
for _cons28, _forma28 in (("legacy_cave_result", "{state.legacy_cave_result && (() =>"),
                          ("tribute_line", "{state.tribute_line && ("),
                          ("heart_demon_result", "{state.heart_demon_result && (() =>"),
                          ("forbidden_cost", "{state.forbidden_cost && (() =>")):
    chk(_forma28 in _BLOCO28,
        "cena: a consequencia condicional `%s` sobreviveu ao redesenho E "
        "continua ALCANCAVEL (a forma `%s`)" % (_cons28, _forma28))
# ⚠️ `"0 &&"` saiu daqui e o motivo importa: ele casava
#    `fc.years_burned > 0 &&`, que e' codigo VIVO e correcto. Um padrao
#    que acusa codigo certo manda o proximo leitor ao sitio errado com
#    confianca, e e' pior do que nao ter padrao nenhum.
for _morto28 in ("false &&", "&& false", "&& null &&"):
    chk(_morto28 not in _BLOCO28,
        "cena: o bloco do resultado nao tem codigo morto (`%s`) a desligar uma "
        "consequencia em silencio" % _morto28)

# OFF-identidade: o ramo antigo continua inteiro, e o gate e' o `obraOn()`.
chk("{_cenaOn ? (" in _MODAL28 and "<CenaDuelo" in _MODAL28,
    "cena: o duelo escolhe entre a CENA e o markup de hoje")
# ⚠️ `_MODAL28` vem SEM PROSA (`_sem_prosa_js`), logo o comentario JSX
#    `{/* Opponent header */}` nao esta' la' — a 1a versao desta guarda
#    procurava-o e ficava vermelha a afirmar sobre a explicacao em vez do
#    markup. E' a 5a vez que isto acontece neste ficheiro: mede-se o MARKUP.
chk("duel_opp_choosing" in _MODAL28
    and 'gridTemplateColumns:"minmax(0, 1fr)", gap:14' in _MODAL28,
    "cena: com a flag OFF o markup de hoje continua la' inteiro (OFF-identidade)")
chk(_TBC.count("ondaCultOn()") == 1,
    "cena: `tabs.js` continua com UM leitor da chave-mestra (%d)"
    % _TBC.count("ondaCultOn()"))

# o *enviar* muda de casa e NAO fica em dois sitios
chk("} ) : _cenaOn ? (".replace(" ", "") in _MODAL28.replace(" ", "")
    or ") : _cenaOn ? (" in _MODAL28,
    "cena: com a cena ligada o pe do modal fica so' com a rendicao — o enviar e' "
    "a faixa de confirmacao, e dois botoes de enviar no mesmo ecra e' a "
    "duplicacao que a chegada matou")

# ── 28.6 — A TIRA DE PREPARO: código morto que passou a responder ──────────
_NPC28 = _fn_src(_TB28, "function CombatNPCPanel(")
_ARENA28 = _fn_src(_TB28, "function CombatArenaPanel(")
chk("combatTechs" in _NPC28 and "<CenaPreparo" in _NPC28,
    "preparo: o `combatTechs` do painel NPC era calculado e NUNCA desenhado "
    "desde a v15.1.4 — passa a alimentar a tira")
chk("<CenaPreparo" in _ARENA28,
    "preparo: a arena usa a MESMA tira (um dono, dois sitios) — ela tambem "
    "cobra Qi e Elo por entrar")
chk(_TB28.count("<CenaPreparo") == 2,
    "preparo: exactamente duas chamadas (%d) — uma terceira tira parecida seria "
    "a Lei 0 §2 outra vez" % _TB28.count("<CenaPreparo"))
# a tira NAO e' um selector: a escolha e' por rodada, dentro do duelo (v15.1.4).
_PREP28 = _fn_src(_UI28, "function CenaPreparo(")
chk("<button" not in _PREP28 and "onClick" not in _PREP28,
    "preparo: a tira nao tem um unico botao — ressuscitar um *foco* aqui "
    "reabriria a decisao que a v15.1.4 fechou")

# ── 28.7 — A ENTRADA da aba convida, e não luta ────────────────────────────
_ENT28 = _fn_src(_TB28, "function CombatTab(")
chk("<CenaEntradaCombate" in _ENT28 and 'setSeg("npc")' in _ENT28
    and 'setSeg("loadout")' in _ENT28,
    "entrada: o botao da entrada ABRE o segmento (NPC quando ha' arte, Tecnicas "
    "quando nao ha') — nenhum modo com custo ou PvP comeca ao toque")
chk("npc_duel_create" not in _fn_src(_UI28, "function CenaEntradaCombate("),
    "entrada: a cena da entrada nao chama nenhum endpoint de luta")
# a arte e' da arte REALMENTE equipada, escolhida pela maior Compreensao.
chk("tt.tech_type === \"combat\" && tt.is_active" in _ENT28
    and "mastery_level" in _ENT28,
    "entrada: a arte e' a EQUIPADA de maior Compreensao — nunca uma imagem "
    "qualquer a fingir que ha' uma arte pronta")
# e os NUMEROS nao recolhem com o cabecalho de emoji (Lei §1: recolhe-se
# explicacao, nunca evidencia).
chk("{!_cenaOn ? (" in _ENT28 and "<CombatHeaderStats" in _ENT28,
    "entrada: o cabecalho de emoji recolhe mas o `CombatHeaderStats` (Poder, "
    "Elo, lugares, cartel, Vida) FICA — recolher evidencia e' o que a Lei §1 "
    "proibe")

# ── 28.9 — OS DOIS ERROS QUE SÓ A OLHAR APARECERAM ────────────────────────
#
# 🔴 Estes dois nasceram NESTE lote, com 1070 guardas verdes por cima. Nenhum se
# vê a ler o ficheiro, nenhum aparece numa contagem, e os dois partiam a tela.
# Por isso cada um vira guarda.
#
# (a) HOOK DEPOIS DE UM RETURN. O `useWideShell()` ficou ~200 linhas abaixo, a
#     seguir ao `if (!state) return (<Modal>…a carregar…</Modal>)`. No 1º render
#     o hook NÃO corria; no 2º corria. React #310 — *"Rendered more hooks than
#     during the previous render"* — e o jogador via a faixa "⚠️ Erro nesta
#     seção" no lugar do duelo INTEIRO.
#
#     ⚠️ `return` de NÍVEL 1 do corpo = exactamente 6 espaços. Um
#     `return () => clearInterval(i)` dentro de um `useEffect` está a 8 e NÃO
#     conta — a 1ª versão desta medição acusou código correcto por causa disso,
#     e uma guarda que aponta para o sítio errado com confiança é pior do que
#     nenhuma.
def _saida_antecipada28(src):
    """A posicao do 1o `return` que SAI do componente, ou None.

    ⚠️ E' isto que a 1a versao errou, e a bateria de sabotagem apanhou-a: eu
    media `^      return` (nivel 1), e o `return` que causou o React #310 vive
    DENTRO de um `if (!state) { … }` — a 8 espacos, invisivel para esse regex.
    A guarda ficava verde a afirmar sobre o `return` FINAL do componente, que
    todo hook precede por construcao. Uma guarda que mede o return errado nao
    guarda nada.

    ⚠️ E tambem nao serve contar QUALQUER `return` indentado: um
    `return () => clearInterval(i)` dentro de um `useEffect` e' limpeza, nao
    saida. A diferenca e' o que ABRIU o bloco — por isso segue-se a pilha:
    um `return` so' sai do componente quando NENHUM bloco aberto por cima dele
    e' uma funcao (`=>` ou `function`).
    """
    corpo = src[src.index("{"):]
    pilha, i, n = [], 0, len(corpo)
    linha_ini = 0
    while i < n:
        c = corpo[i]
        if c == "\n":
            linha_ini = i + 1
        elif c == "{":
            cab = corpo[linha_ini:i]
            pilha.append("fn" if ("=>" in cab or "function" in cab) else "blk")
        elif c == "}":
            if pilha:
                pilha.pop()
        elif corpo.startswith("return", i) and (i == 0 or not corpo[i - 1].isalnum()):
            # dentro da funcao-componente (pilha[0]) e de mais nenhuma funcao
            if len(pilha) >= 1 and "fn" not in pilha[1:]:
                return i
        i += 1
    return None


_HOOKS28 = re.compile("^ {6,}(?:const|let|var)[^\n]*\\buse[A-Z]\\w*\\(", re.M)
for _fn28 in ("DuelArenaModal", "CombatTab", "CombatNPCPanel", "CombatArenaPanel",
              "CenaDuelo", "CenaPreparo", "CenaEntradaCombate", "CenaChapa"):
    _eh_tab28 = _fn28 in ("DuelArenaModal", "CombatTab", "CombatNPCPanel",
                          "CombatArenaPanel")
    _src28 = _fn_src(_TB28 if _eh_tab28 else _UI28, "function %s(" % _fn28)
    _corpo28 = _src28[_src28.index("{"):]
    _hooks28 = [m.start() for m in _HOOKS28.finditer(_corpo28)]
    _saida28 = _saida_antecipada28(_src28)
    chk(not _hooks28 or _saida28 is None or max(_hooks28) < _saida28,
        "hooks: em `%s` todo hook nasce ANTES da primeira SAIDA do componente — "
        "um hook depois de um `return` antecipado da' React #310, e o jogador "
        "ve' uma faixa de ERRO no lugar da tela (aconteceu neste lote, com 1070 "
        "guardas verdes por cima)" % _fn28)
# ⚠️ e a prova de que o detector VE' as duas coisas: sem isto, um regex partido
# deixava tudo verde para sempre (a licao de 08/09).
_dm28 = _fn_src(_TB28, "function DuelArenaModal(")
chk(len(_HOOKS28.findall(_dm28)) >= 4 and _saida_antecipada28(_dm28) is not None,
    "hooks: o detector ainda ve' os %d hooks do `DuelArenaModal` E a saida "
    "antecipada dele — uma guarda verde sobre o conjunto vazio nao guarda"
    % len(_HOOKS28.findall(_dm28)))

# (b) UMA CRASE DENTRO DO CSS FECHA A STRING. O `<style>{...}</style>` da cena é
#     um template literal: uma crase num COMENTÁRIO de CSS lá dentro termina a
#     string e o build morre com "Expected } but found min". Aconteceu TRÊS
#     vezes seguidas neste lote, sempre a citar o nome de uma propriedade.
_BT28 = chr(96)


def _css_da_cena28(src):
    """O texto de cada folha `<style>` de uma cena."""
    out, i = [], 0
    while True:
        i = src.find("<style>{" + _BT28, i)
        if i < 0:
            return out
        j = src.find(_BT28 + "}</style>", i)
        if j < 0:
            return out
        out.append(src[i + 9:j])
        i = j + 1


_css28 = []
for _f28 in ("CenaDuelo", "CenaPreparo", "CenaEntradaCombate"):
    _css28 += _css_da_cena28(_fn_src(_UI28, "function %s(" % _f28))
chk(len(_css28) == 3,
    "cena/css: as tres cenas declaram a sua folha (%d encontradas)" % len(_css28))
_crases28 = [c[:70] for c in _css28 if _BT28 in c]
chk(not _crases28,
    "cena/css: ZERO crases dentro do `<style>` — uma crase la' dentro FECHA o "
    "template literal e o build morre (3x neste lote): %r" % _crases28)

# (c) E O NÚMERO NÃO PARTE. Visto a olho, a 390px: `158.977.287.8` numa linha e
#     `26` na seguinte lê-se como OUTRO número. É a mesma lei da §14 (`+12000`
#     lido como `+1200`): um número partido não é feio, é FALSO.
#
#     🔴 05/10 — e a 1.ª forma desta regra CAUSOU o report do [jogador] (*"in PvE
#     arena, popup of combat shows opponent's hp out of bound on screen"*): o
#     `nowrap` estava no PAR inteiro (valor + "de máx"), e um par que não pode
#     quebrar, numa coluna de 88px, só pode transbordar — o adversário de 10
#     dígitos saía 20px pelo lado direito do telemóvel. A lei continua (o número
#     não parte); o meio mudou: o par FLUI e o número ENCOLHE para caber (a
#     coluna é um container query). Quem MEDE a lei, num browser, a 320–1440, é
#     `scripts/_test_cena_cabe.py`. Aqui fica o que se lê no CSS.
_regra_num28 = ""
if _css28 and ".cena-duelo .cena-faixa-num" in _css28[0]:
    _regra_num28 = _css28[0].split(".cena-duelo .cena-faixa-num")[1].split("}")[0]
chk(bool(_regra_num28) and "nowrap" not in _regra_num28,
    "cena: o PAR valor+'de <maximo>' NAO e' `nowrap` — o espaco entre eles e' o "
    "ponto de quebra (o report de 03/10) (regra: %r)" % _regra_num28.strip()[:60])
_sup28 = ""
if _css28 and "@supports (container-type:inline-size)" in _css28[0]:
    _sup28 = _css28[0].split("@supports (container-type:inline-size)")[1]
_val28 = (_sup28.split(".cena-duelo .cena-faixa-val")[1].split("}")[0]
          if ".cena-duelo .cena-faixa-val" in _sup28 else "")
chk(".cena-duelo .cena-faixa { container-type:inline-size; }" in _sup28
    and "cqi" in _val28 and "var(--cena-em" in _val28,
    "cena: o NUMERO encolhe para caber (a coluna e' container; o tamanho sai de "
    "cqi / --cena-em), dentro de @supports (regra: %r)" % _val28.strip()[:70])
_fx28 = _fn_src(_UI28, "function CenaDuelo(")
chk('"--cena-em"' in _fx28 and "fmtFullQuebra(vv)" in _fx28
    and "fmtFullQuebra(mm)" in _fx28,
    "cena: o valor e o maximo levam a largura (--cena-em) e passam pelo "
    "fmtFullQuebra (a quebra entre grupos so' sem container queries)")

# ── 28.8 — as palavras, nas TRÊS línguas, e nenhuma chave morta ────────────
_I28 = {l: __import__("json").load(io.open(
    os.path.join(ROOT, "miniapp", "i18n", "%s.json" % l), encoding="utf-8"))
    for l in ("pt", "en", "es")}
_usadas28 = set(re.findall(r'[ts]\("(cena_[a-z0-9_]+)"', _UI28))
chk(len(_usadas28) >= 30,
    "cena/i18n: a cena usa %d chaves `cena_*`" % len(_usadas28))
for _l28 in ("pt", "en", "es"):
    _falta28 = sorted(k for k in _usadas28 if k not in _I28[_l28])
    chk(not _falta28,
        "cena/i18n: `%s.json` tem todas as chaves que a cena pede (falta %r)"
        % (_l28, _falta28))
chk(len(_I28["pt"]) == len(_I28["en"]) == len(_I28["es"]),
    "cena/i18n: as tres linguas continuam em paridade (%d/%d/%d)"
    % (len(_I28["pt"]), len(_I28["en"]), len(_I28["es"])))
# ⚠️ Cada arquetipo da tabela de emblemas tem palavra nas tres linguas. Um
# emblema sem nome e' pior do que um emoji (a marca nunca vai sozinha).
for _arq28 in ("bandit", "sect_disciple", "beast", "demon", "boss", "elder"):
    chk(('"cena_arq_%s"' % _arq28) in _UI28
        and all(("cena_arq_" + _arq28) in _I28[l] for l in ("pt", "en", "es")),
        "cena: o arquetipo `%s` tem emblema E palavra nas tres linguas" % _arq28)
# ⚠️ E a tabela cobre os arquetipos que o SERVIDOR pode mandar — nao uma lista
# escolhida a' mao. Um `npc_archetype` novo no `npc_loadouts.py` sem emblema
# cairia no combatente generico em silencio.
from core.npc_loadouts import NPC_ARCHETYPES as _ARQS28
_sem_emblema28 = sorted(a for a in _ARQS28 if ('"cena_arq_%s"' % a) not in _UI28)
chk(not _sem_emblema28,
    "cena: os %d arquetipos que o servidor pode mandar tem todos emblema "
    "(sem: %r)" % (len(_ARQS28), _sem_emblema28))
# os 11 `effect_type` dos seeds tem frase, ou a tela cala-se em vez de prometer.
_tipos28 = sorted({t.get("effect_type") for t in _TECS28 if t.get("effect_type")})
_sem_frase28 = [x for x in _tipos28 if ("cena_efeito_" + x) not in _I28["pt"]]
chk(not _sem_frase28,
    "cena: os %d `effect_type` do catalogo tem frase em palavras (sem: %r) — "
    "um tipo sem frase mostra so' o custo, que e' verdade, mas um tipo dos "
    "seeds sem frase e' trabalho esquecido" % (len(_tipos28), _sem_frase28))

# ══════════════════════════════════════════════════════════════════════════
# §29 — 門 A NAVEGAÇÃO ACOMPANHA A PROGRESSÃO (P6, 2026-09-27)
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 O QUE SE MEDIU ANTES DE ESCREVER: das 24 abas, TRÊS recusam por reino
# (Facção R3 · Celestial R8 · Corpo R7 sem o Refino Mortal). A navegação não
# sabia nenhuma — não havia campo no payload — e a Facção tinha DOIS donos do
# mesmo 3 (o `webserver` e o chat). O "11 trancam por dentro" de 16/09 não
# tinha lista escrita e não se reproduz: misturava gates de progressão com
# estados vazios que já oferecem caminho (guilda, parceiro, chefe).
#
# ⚠️ A GUARDA MORDE NO SÍTIO, NÃO NO FICHEIRO. Três formas, e cada uma fecha
# uma porta por onde este defeito já passou nesta casa:
#   29.1 o SERVIDOR — o dono é chamado pelos endpoints (seguindo a chamada) e
#        a porta bate com os motores de cada camada, reino a reino;
#   29.2 o CLIENTE sob node — as funções REAIS contra os `nav_gates` que o
#        `core/portas.py` REAL produz (nunca números meus);
#   29.3 os SÍTIOS — a lista de gates vem do SERVIDOR (`PORTAS`), e todo bloco
#        do cliente que apresenta uma dessas abas como porta tem de consultar o
#        dono. Um gate novo amanhã (o Mercado, digamos) acusa, sozinho, a cena
#        da Caverna que o mostra como aberto.
print("\n=== 29. 門 A NAVEGAÇÃO ACOMPANHA A PROGRESSÃO ===")

import ast as _ast29
from types import SimpleNamespace as _NS29
import core.portas as _P29
from core.faction_engine import FACTION_MIN_REALM as _FMR29
from core.celestial_engine import MAHAYANA_REALM as _MAH29
from core.body_tempering_engine import (MIN_REALM_REQUIRED as _BMR29,
                                        project_tempering_status as _pts29)
from core.meridian_engine import (MERIDIAN_MIN_REALM as _MMR29,
                                  channels_allowed as _chan29)

_WS29 = rd("core/webserver.py")
_APM29 = rd("miniapp/components/app.js")
_UI29 = _sem_prosa_js(_UIM)
_TB29 = _sem_prosa_js(_TBM)
_AP29 = _sem_prosa_js(_APM29)
_TAB_KEYS29 = set(re.findall(r'\{ key:"(\w+)"', _obj_after(_UIM, "var TAB_DEFS = ")))


def _jog29(realm):
    return _NS29(realm=realm, body_tempering_level=0, mortal_body_level=0,
                 mortal_temper_progress=0, qi=0, qi_capacity=100, spirit_stones=0,
                 hunt_essence=0, sub_layer=1, telegram_id=1)


def _flag29(on):
    return lambda k: k in on


_MUNDOS29 = {"-": set(), "cultivo_corpo_r0": {"cultivo_corpo_r0"},
             "corpo_profundo": {"corpo_profundo"},
             "cultivo_corpo_r0+corpo_profundo": {"cultivo_corpo_r0", "corpo_profundo"}}

# ── 29.1 O SERVIDOR ─────────────────────────────────────────────────────────
_chaves29 = [k for k, _f in _P29.PORTAS]
chk(_chaves29 == ["faction", "celestial", "body_tempering"],
    "portas/servidor: o registo tem as TRES abas medidas com gate (%r)" % (_chaves29,))
chk(set(_chaves29) <= _TAB_KEYS29,
    "portas/servidor: cada gate e' uma aba do `TAB_DEFS` — a chave e' por onde "
    "o cliente a encontra (fora: %r)" % sorted(set(_chaves29) - _TAB_KEYS29))

# (a) reino a reino, mundo a mundo, contra os MOTORES de cada camada
_div29 = []
for _mk, _on in _MUNDOS29.items():
    for _r in range(0, 11):
        _g = _P29.portas_do_jogador(_jog29(_r), _flag29(_on))
        _esp = {
            "faction": _r >= _FMR29,
            "celestial": _r >= _MAH29,
            # o Corpo abre quando UMA camada abre — cada uma pelo seu dono
            "body_tempering": ("cultivo_corpo_r0" in _on
                               or ("corpo_profundo" in _on and _chan29(_r) > 0)
                               or bool(_pts29(_jog29(_r))["unlocked"])),
        }
        for _k, _v in _esp.items():
            if _g[_k]["open"] is not _v:
                _div29.append("%s R%d %s" % (_mk, _r, _k))
            if _g[_k]["open"] is False and (_g[_k].get("have") != _r or _g[_k].get("kind") != "realm"):
                _div29.append("%s R%d %s sem have/kind" % (_mk, _r, _k))
chk(not _div29,
    "portas/servidor: 44 jogadores (R0-R10 x 4 mundos) — a porta bate com o "
    "motor de cada camada (divergem: %r)" % _div29[:4])
_g0 = _P29.portas_do_jogador(_jog29(0), _flag29(set()))
chk(_g0["faction"].get("need") == _FMR29 and _g0["celestial"].get("need") == _MAH29
    and _g0["body_tempering"].get("need") == _BMR29
    and _P29.portas_do_jogador(_jog29(0), _flag29({"corpo_profundo"}))["body_tempering"].get("need") == _MMR29,
    "portas/servidor: o requisito e' a CONSTANTE do motor (R%d/R%d/R%d; R%d com os "
    "meridianos) — nao um numero escrito aqui" % (_FMR29, _MAH29, _BMR29, _MMR29))

# (b) um gate que rebenta e' DESCONHECIDO, nunca aberto
_orig29 = _P29.PORTAS


def _rebenta29(p, f):
    raise RuntimeError("porta em chamas")


_P29.PORTAS = (("faction", _rebenta29),) + tuple(_orig29[1:])
try:
    _gr29 = _P29.portas_do_jogador(_jog29(9), _flag29(set()))
finally:
    _P29.PORTAS = _orig29
chk(_gr29.get("faction") == {"open": None} and _gr29.get("celestial") == {"open": True},
    "portas/servidor: um gate que rebenta sai `open:null` (o cliente diz 'verificando') "
    "e NAO leva os outros consigo")


# (c) os ENDPOINTS decidem pelo dono — seguindo a chamada, nunca uma copia
def _fn29(src, nome):
    for _n in _ast29.walk(_ast29.parse(src)):
        if isinstance(_n, (_ast29.FunctionDef, _ast29.AsyncFunctionDef)) and _n.name == nome:
            return _n
    return None


def _chama29(fn, alvo):
    return any(isinstance(_c, _ast29.Call) and isinstance(_c.func, _ast29.Name)
               and _c.func.id == alvo for _c in _ast29.walk(fn))


def _compara_reino29(fn, const):
    """Uma comparacao `... < CONST` / `... >= CONST` escrita a' mao dentro da
    funcao — a copia do predicado que o dono veio substituir."""
    for _c in _ast29.walk(fn):
        if isinstance(_c, _ast29.Compare):
            for _o in [_c.left] + list(_c.comparators):
                if isinstance(_o, _ast29.Name) and _o.id == const:
                    return True
    return False


for _nome29, _dono29, _const29 in (("_build_faction_payload", "porta_faccao", "FACTION_MIN_REALM"),
                                   ("api_faction_pick", "porta_faccao", "FACTION_MIN_REALM"),
                                   ("api_celestial_status", "porta_celestial", "MAHAYANA_REALM")):
    _f29 = _fn29(_WS29, _nome29)
    chk(_f29 is not None and _chama29(_f29, _dono29) and not _compara_reino29(_f29, _const29),
        "portas/endpoint: `%s` decide o seu `locked` chamando `%s` — e sem uma "
        "comparacao propria contra `%s`" % (_nome29, _dono29, _const29))

# (d) UM limiar da Faccao em todo o servidor e no chat
_atribs29 = []
for _dir29 in ("core", "handlers"):
    for _fn in sorted(os.listdir(os.path.join(ROOT, _dir29))):
        if not _fn.endswith(".py"):
            continue
        _t = rd(_dir29 + "/" + _fn)
        if "MIN_REALM_FACTION" not in _t and "FACTION_MIN_REALM" not in _t:
            continue
        for _n in _ast29.walk(_ast29.parse(_t)):
            if isinstance(_n, _ast29.Assign) and isinstance(_n.value, _ast29.Constant):
                for _tg in _n.targets:
                    if isinstance(_tg, _ast29.Name) and _tg.id in ("MIN_REALM_FACTION", "FACTION_MIN_REALM"):
                        _atribs29.append("%s/%s" % (_dir29, _fn))
chk(_atribs29 == ["core/faction_engine.py"],
    "portas/limiar: a Faccao abre num numero escrito UMA vez (atribuicoes: %r) — "
    "eram dois 3 a' mao, o do mini-app e o do chat" % _atribs29)
import handlers.faction as _hf29
chk(_hf29.MIN_REALM_FACTION == _FMR29,
    "portas/limiar: o chat le' o MESMO limiar (%d)" % _hf29.MIN_REALM_FACTION)

# (e) o `/player` manda as portas SO' com a onda, e sem a onda a chave nem existe
_pl29 = _fn29(_WS29, "api_player")
_pls29 = _ast29.get_source_segment(_WS29, _pl29) if _pl29 else ""
chk('**({"nav_gates": _nav_gates} if _nav_gates is not None else {})' in _pls29
    and "if _onda_on():" in _pls29 and "portas_do_jogador(player)" in _pls29,
    "portas/payload: `nav_gates` sai de `portas_do_jogador` so' com a onda ON, e "
    "por chave CONDICIONAL — em `main` o payload fica byte-identico")
_cli_onda29 = re.findall(r'featureEnabled\("(\w+)"\)', _fn_src(_UIM, "    function ondaCultOn("))
chk(sorted(_cli_onda29) == sorted(_P29.ONDA_FLAGS) and len(_cli_onda29) >= 2,
    "portas/onda: o servidor liga as portas com as MESMAS chaves do `ondaCultOn()` "
    "(servidor %r, cliente %r)" % (list(_P29.ONDA_FLAGS), _cli_onda29))
chk(_P29.onda_on(_flag29({"cultivador_jogavel"})) and not _P29.onda_on(_flag29({"ui_v2"})),
    "portas/onda: `cultivador_jogavel` sozinha liga (o s2 desde 15/09); `ui_v2` sozinha nao")

# ── 29.2 O CLIENTE, SOB NODE, CONTRA O SERVIDOR ─────────────────────────────
_casos29 = {}
for _mk, _on in _MUNDOS29.items():
    for _r in range(0, 11):
        _casos29["r%d|%s" % (_r, _mk)] = {"gates": _P29.portas_do_jogador(_jog29(_r), _flag29(_on))}
_carga29 = {"casos": _casos29, "min": {"faction": _FMR29, "celestial": _MAH29, "body": _BMR29}}
if node:
    _r29 = subprocess.run([node, os.path.join(ROOT, "scripts", "_test_portas.js")],
                          input=_json.dumps(_carga29), capture_output=True,
                          text=True, encoding="utf-8")
    _l29 = [l for l in (_r29.stdout or "").rstrip().split(chr(10)) if l.strip()]
    print("   (%d asserts das portas sob node)" % len(_l29))
    for _l in _l29:
        if _l.startswith("FAIL"):
            print("   " + _l)
    chk(_r29.returncode == 0 and len(_l29) > 300,
        "portas/cliente: o `portaDe`/`portasDoHub`/`euPortasVisiveis` REAIS, sob "
        "node, contra 44 cargas do `core/portas.py` — so' o marco a' vista, nunca "
        "a opcao (c), incerta nunca aberta, OFF = hoje (%d asserts)" % len(_l29))
else:
    chk(True, "node ausente: ficam os contratos de fonte abaixo")

# (a) o cliente nao tem limiar: nenhum sitio compara o reino a um numero
_donos29 = ["portasOn", "portaDe", "portasDoHub", "PortaSelo", "PortaConsulta",
            "SideRailHubs", "V2HubStrip"]
_comp29 = [n for n in _donos29
           if re.search(r"realm\w*\s*(<|>|<=|>=)\s*\d", _fn_src(_UI29, "    function %s(" % n))]
chk(not _comp29,
    "portas/cliente: nenhum limiar de reino escrito no cliente (em %r) — o "
    "numero vem do servidor, sempre" % _comp29)
# (b) todo `kind` que o servidor pode mandar tem CAMINHO no cliente
_kinds29 = sorted({getattr(_P29, _k) for _k in dir(_P29) if _k.startswith("KIND_")})
_cam29 = set(re.findall(r"^      (\w+):\s*\{", _obj_after(_UIM, "var PORTA_CAMINHOS = "), re.M))
chk(_kinds29 and set(_kinds29) <= _cam29,
    "portas/caminho: todo `kind` do servidor (%r) tem caminho no cliente (%r) — "
    "uma porta que diz O QUE falta e nao COMO e' metade" % (_kinds29, sorted(_cam29)))
for _k29 in _cam29:
    _c = _obj_after(_UIM, "var PORTA_CAMINHOS = ")
    _tb = re.search(r'%s:\s*\{[^}]*tab:\s*"(\w+)"' % _k29, _c)
    chk(_tb and _tb.group(1) in _TAB_KEYS29,
        "portas/caminho: o caminho `%s` leva a uma aba que existe" % _k29)

# ── 29.3 OS SÍTIOS — a lista de gates vem do SERVIDOR ──────────────────────


def _blocos29(src):
    out, cur, nome = [], [], "(topo)"
    for _l in src.split(chr(10)):
        _m = re.match(r"^    (?:async )?function (\w+)\(|^    var (\w+)\s*=", _l)
        if _m:
            out.append((nome, chr(10).join(cur)))
            nome, cur = (_m.group(1) or _m.group(2)), []
        cur.append(_l)
    out.append((nome, chr(10).join(cur)))
    return out


def _sitios29(chaves):
    """Todo bloco de topo do cliente que APRESENTA uma destas abas como porta:
    navega para ela por literal, ou percorre o grupo de um hub."""
    achados = []
    for _f, _s in (("ui.js", _UI29), ("tabs.js", _TB29), ("app.js", _AP29)):
        for _nome, _b in _blocos29(_s):
            _pats = []
            for _k in chaves:
                _pats += [r'setTab\(\s*"%s"\s*\)' % _k, r'\btab\s*:\s*"%s"' % _k]
                if "setTab(" in _b:
                    _pats.append(r':\s*"%s"\s*[,}]' % _k)
            _porta = any(re.search(_p, _b) for _p in _pats)
            _grupo = bool(re.search(r"\.group\s*\.\s*(filter|map)\(", _b))
            if _porta or _grupo:
                achados.append((_f, _nome, ("portasDoHub(" in _b) or ("euPortasVisiveis(" in _b)))
    return achados


# ⚠️ As excepcoes vivem AQUI, com o motivo, e cada motivo e' VERIFICADO abaixo
# — uma excepcao que deixa de ser verdade fica vermelha, nao fica esquecida.
_EXCEPCOES29 = {
    "HOME_CARDS": "a grelha antiga da Home so' renderiza com a onda OFF — com ela ON a Home e' a chegada",
    "EU_PORTAS": "e' DADO: so' se le' pelo dono (`euPortasVisiveis`) — verificado abaixo",
    "FtueCard": "o passo `corpo` so' existe com `cultivo_corpo_r0`, e ai' o Corpo ja' abriu",
    "CultivationTab": "`onGateCelestial` so' dispara com `celestial_trial_required`, que so' existe no reino da Celestial",
}
_s29 = _sitios29(_chaves29)
_fora29 = [(f, n) for f, n, dono in _s29 if not dono and n not in _EXCEPCOES29]
chk(not _fora29,
    "portas/sitios: todo bloco que apresenta Faccao/Celestial/Corpo como porta "
    "consulta o dono (sem dono: %r)" % _fora29)
chk(len(_s29) >= 8,
    "portas/sitios: a varredura ve' %d blocos — se desabasse para ~0 era o regex "
    "partido e nao o problema resolvido" % len(_s29))
_nomes29 = {n for _f, n, _d in _s29}
chk(set(_EXCEPCOES29) <= _nomes29,
    "portas/sitios: cada excepcao declarada ainda existe (orfas: %r)"
    % sorted(set(_EXCEPCOES29) - _nomes29))
# — e cada motivo continua VERDADE
chk("chegadaOn" in _fn_src(_TB29, "    function HomeTab(")
    and "HOME_CARDS" in _fn_src(_TB29, "    function HomeTab(")
    and "{!chegadaOn && (<>" in _fn_src(_TB29, "    function HomeTab("),
    "portas/excepcao: a grelha HOME_CARDS continua so' no ramo `!chegadaOn`")
_consumidores29 = [(f, n, ("euPortasVisiveis(" in b) or ("portasDoHub(" in b))
                   for f, s in (("ui.js", _UI29), ("tabs.js", _TB29), ("app.js", _AP29))
                   for n, b in _blocos29(s) if n != "EU_PORTAS" and "EU_PORTAS" in b]
chk(len(_consumidores29) >= 2 and all(d for _f, _n, d in _consumidores29),
    "portas/excepcao: todo leitor do `EU_PORTAS` passa pelo dono (%r)"
    % [(f, n) for f, n, d in _consumidores29 if not d])
chk(all(_P29.porta_corpo(_jog29(_r), _flag29({"cultivo_corpo_r0"}))["open"] is True for _r in range(11))
    and re.search(r"if _body_axis_on\(\):\s*\n\s*steps\.append\(\(\"corpo\"", rd("core/ftue_engine.py")),
    "portas/excepcao: o passo `corpo` do FTUE so' nasce com o eixo do corpo — e com ele "
    "o Corpo esta' aberto em TODO reino")
chk(_MAH29 == 8 and "if player.realm == 8:" in rd("core/game_logic.py")
    and "celestial_trial_required" in rd("core/game_logic.py").split("if player.realm == 8:", 1)[1][:900],
    "portas/excepcao: o `celestial_trial_required` so' existe no reino %d = o da Celestial" % _MAH29)

# (b) os QUATRO sitios que desenham portas: consultam, dizem porque e abrem a consulta
for _f29s, _src29s, _fn29s in (("ui.js", _UI29, "SideRailHubs"), ("ui.js", _UI29, "V2HubStrip"),
                               ("tabs.js", _TB29, "HubEuScreen"), ("tabs.js", _TB29, "HubMundoScreen")):
    _b29 = _fn_src(_src29s, "    function %s(" % _fn29s)
    chk(("portasDoHub(" in _b29 or "euPortasVisiveis(" in _b29)
        and ("portaDe(" in _b29 or "portaDoPath(" in _b29)
        and "<PortaSelo" in _b29 and "portaAria(" in _b29 and "onPorta(" in _b29,
        "portas/sitio `%s`: o marco pelo dono, a porta pelo `portaDe`, o selo, o "
        "nome acessivel com o motivo, e o toque abre a CONSULTA" % _fn29s)
    _el29 = re.search(r"<%s\b(.*?)/>" % _fn29s, _AP29, re.S)
    chk(bool(_el29) and "onPorta={abrirPorta}" in _el29.group(1),
        "portas/sitio `%s`: o `app.js` entrega-lhe `onPorta` — sem isto o toque "
        "caia na aba que recusa" % _fn29s)

# (c) a MAÇANETA: nos DOIS sitios onde a chegada se desenha
_cheg29 = re.findall(r"<Chegada\b(.*?)/>", _TB29, re.S)
chk(len(_cheg29) >= 2 and all("portas={" in c and "onPortas={" in c and "euPortasVisiveis(" in _TB29
                              for c in _cheg29),
    "portas/maçaneta: as %d chegadas (`home` e `hub_eu_screen`) nomeiam as portas — a "
    "app ARRANCA em `home`, que era a que nao tinha" % len(_cheg29))
chk("euPortasVisiveis(player, EU_PORTAS).nomes" in _fn_src(_TB29, "    function HomeTab(")
    and "nomesMacaneta" in _fn_src(_TB29, "    function HubEuScreen(")
    and "eu.nomes" in _fn_src(_TB29, "    function HubEuScreen("),
    "portas/maçaneta: as duas leem os nomes do MESMO dono")
chk(re.search(r"onAbrirSeletor=\{featureEnabled\(\"ui_v2\"\)[^}]*\?\s*\(\)\s*=>\s*\{[^}]*"
              r"setTab\(\"hub_eu_screen\"\);\s*setEuSeletor\(true\);", _AP29, re.S),
    "portas/maçaneta: a do `home` leva ao Eu com o selector JA' aberto (um toque)")

# (d) a CONSULTA: janela da raiz, dentro da fronteira, e o VOLTAR fecha-a
_hb29 = _AP29.split("const _handleBack = useCallback(", 1)[1].split("useTelegramBackButton", 1)[0]
chk("|| !!portaConsulta" in _AP29 and "if (portaConsulta) { setPortaConsulta(null); return; }" in _hb29
    and "portaConsulta," in _hb29.split("}, [", 1)[1],
    "portas/consulta: conta como janela aberta, e o VOLTAR nativo fecha-a antes "
    "de fechar o webapp (com a dependencia declarada)")
_mb29 = _AP29.split('<ModalErrorBoundary label="root-modal"', 1)[1].split("</ModalErrorBoundary>", 1)[0]
chk("<PortaConsulta " in _mb29,
    "portas/consulta: vive DENTRO da fronteira dos modais da raiz (a tela preta de 17/06)")
_pc29 = _fn_src(_UI29, "    function PortaConsulta(")
chk("<Modal " in _pc29 and "portaDe(" in _pc29 and "portasDoHub(" in _pc29
    and "PORTA_CAMINHOS[" in _pc29 and "realmName(" in _pc29,
    "portas/consulta: pela moldura da casa, com o requisito pelo nome do reino e o "
    "caminho do `kind`")

# (e) o SELO: uma marca que existe, nunca sozinha, com cor declarada
_ps29 = _fn_src(_UI29, "    function PortaSelo(")
chk('<Mark name="lock" size={12} />' in _ps29 and "lock" in _MARK_NAMES and "portaRotulo(" in _ps29
    and "color:" in _ps29 and "fontSize:12," in _ps29 and "gap:4," in _ps29,
    "portas/selo: o cadeado e' a marca `lock` a 12px com o numero a 12px e 4px entre eles "
    "(o Astra, MESA [020]), SEMPRE com o numero, e com `color` declarada")

# (f) o texto: tres linguas, e so' chaves que existem
_I29 = {_l: _json.load(io.open(os.path.join(ROOT, "miniapp", "i18n", _l + ".json"),
                               encoding="utf-8")) for _l in ("pt", "en", "es")}
_usadas29 = sorted(set(re.findall(r'"(porta_\w+)"', _UIM + _TBM)))
chk(len(_usadas29) >= 15, "portas/i18n: o cliente usa %d chaves `porta_*`" % len(_usadas29))
for _l29 in ("pt", "en", "es"):
    _falta29 = [k for k in _usadas29 if k not in _I29[_l29]]
    chk(not _falta29, "portas/i18n: `%s.json` tem todas (falta %r)" % (_l29, _falta29))
chk(len(_I29["pt"]) == len(_I29["en"]) == len(_I29["es"]),
    "portas/i18n: paridade (%d/%d/%d)" % (len(_I29["pt"]), len(_I29["en"]), len(_I29["es"])))
# (g) A FORMA, decidida pelo Astra (MESA [020]) — um dono, e a regra MEDIDA da cor
_pt29 = _fn_src(_UI29, "    function portaTom(")
chk('trancada: "1px dashed " + NIV_ONDA.line' in _pt29 and 'consulta: "1px solid " + NIV_ONDA.line' in _pt29,
    "portas/forma: o tracejado so' na TRANCADA e o contorno CONTINUO na consulta "
    "«Desbloqueios» — um dono (`portaTom`), nunca um `dashed` escrito por sitio")
chk('{"+" + n}' in _fn_src(_UI29, "    function PortaConta("),
    "portas/forma: o contador de «Desbloqueios» diz +N (destinos ADICIONAIS), nunca so' N")


def _cor29(txt):
    _m = re.search(r"\bcolor:\s*([^,\n]+?)\s*,", txt)
    return _m.group(1).strip() if _m else None


for _f29c, _src29c, _fn29c, _caixa29c in (("ui.js", _UI29, "SideRailHubs", False),
                                           ("ui.js", _UI29, "V2HubStrip", True),
                                           ("tabs.js", _TB29, "HubEuScreen", True),
                                           ("tabs.js", _TB29, "HubMundoScreen", True)):
    _b29c = _fn_src(_src29c, "    function %s(" % _fn29c)
    chk("dashed" not in _b29c,
        "portas/forma `%s`: nenhum `dashed` escrito a' mao — o tracejado vem do dono" % _fn29c)
    chk("<PortaConta n=" in _b29c,
        "portas/forma `%s`: «Desbloqueios» conta pelo dono (+N)" % _fn29c)
    if _caixa29c:
        chk("border: portaTom().trancada" in _b29c and "border: portaTom().consulta" in _b29c,
            "portas/forma `%s`: a trancada tracejada e «Desbloqueios» com contorno CONTINUO" % _fn29c)
    else:
        chk("portaTom().trancada" not in _b29c,
            "portas/forma `%s`: na lateral do PC a porta fica a FILA com o selo, sem caixa "
            "(*'a geometria pertence ao sitio'*)" % _fn29c)
    # 🔴 A MESMA COR das abertas do mesmo sitio. Medido a servir: com o nome em
    # papel a' letra, o Corpo trancado saia rgb(236,229,216) numa faixa de chips
    # abertos a rgb(110,137,191) — a porta que NAO abre a gritar mais alto.
    _i29c = _b29c.find('.estado !== "aberta") {')
    _fim29c = _b29c.find("</button>", _i29c)
    _ab29c = _b29c[_fim29c:_b29c.find("</button>", _fim29c + 9)]
    _ct29c, _ca29c = _cor29(_b29c[_i29c:_fim29c]), _cor29(_ab29c)
    # o Astra afinou (MESA [020]): a cor das abertas NAO SELECCIONADAS — um
    # `sel ? X : Y` na aberta conta pelo `Y`, e a trancada nao tem ramo `sel`.
    if _ca29c and "?" in _ca29c and ":" in _ca29c:
        _ca29c = _ca29c.rsplit(":", 1)[1].strip()
    chk(_i29c > 0 and _ct29c and _ct29c == _ca29c,
        "portas/forma `%s`: a porta trancada tem a MESMA cor das abertas NAO "
        "seleccionadas do sitio (trancada %r, aberta %r) — o significado e' do SELO"
        % (_fn29c, _ct29c, _ca29c))
chk(" você " in " " + _I29["pt"]["porta_caminho_reino"] + " " and "verificar" in _I29["pt"]["porta_incerta_nota"]
    and _I29["pt"]["porta_incerta"] == "Verificando",
    "portas/i18n: pt e' do BRASIL (voce; 'Verificando', nunca 'A verificar')")

# ══════════════════════════════════════════════════════════════════════════
# §30 — 減 A REDUÇÃO PROGRESSIVA (P7, 2026-09-27)
# ══════════════════════════════════════════════════════════════════════════
#
# A decisão é do Astra (MESA [017] §4): *"Depois de uma acção bem-sucedida
# nesse sistema, oferecer «Já percebi»: a frase introdutória recolhe; «Ajuda»
# permite recuperá-la. Sem presumir domínio pelo tempo de conta e SEM MUDAR A
# POSIÇÃO DOS COMANDOS."* E ficam SEMPRE: rótulo, valor, limiar, custo,
# duração, bloqueio e consequência confirmada.
#
# 🔴 O QUE SE CONTOU ANTES: 242 chaves nas telas da onda, e só SEIS explicam
# sem carregar número nem motivo. Vida/Qi não tem UMA dica escrita (é tudo
# prova); `cena_idle_body` só se desenha com a onda OFF.
#
# ⚠️ A GUARDA MORDE NO SÍTIO, NÃO NO FICHEIRO:
#   30.1 o SERVIDOR — o dono e os seus estados; cada endpoint que o registo
#        nomeia marca o seu sistema ANTES do commit, e só no caminho do êxito;
#   30.2 o CLIENTE sob node — `explicaEstado` real: sem preferência lida nunca
#        é "recolhido";
#   30.3 os SÍTIOS — a lista de frases vem do REGISTO (`EXPLICA`), e todo sítio
#        do cliente que desenha uma delas tem de a pôr dentro do `Explica` do
#        SEU sistema. Uma frase nova no registo acusa, sozinha, quem a mostra;
#   30.4 nenhum NÚMERO recolhe — e nenhuma frase de prova entra no registo;
#   30.5 a GEOMETRIA que impede o comando de mexer, e o "só o confirmado";
#   30.6 as Configurações, o fio do refresh e as três línguas.
print("\n=== 30. 減 A REDUÇÃO PROGRESSIVA ===")

import subprocess as _sp30
from types import SimpleNamespace as _NS30
import core.explicacoes as _E30

_WS30 = rd("core/webserver.py")
_UI30 = _sem_prosa_js(_UIM)
_TB30 = _sem_prosa_js(_TBM)
_AP30 = _sem_prosa_js(rd("miniapp/components/app.js"))
_FONTES30 = (("ui.js", _UI30), ("tabs.js", _TB30), ("app.js", _AP30))
_REG30_SRC = _obj_after(_UIM, "var EXPLICA = ")
_REG30 = {k: re.findall(r'"(\w+)"', v)
          for k, v in re.findall(r"^\s*(\w+):\s*\[([^\]]*)\]", _REG30_SRC, re.M)}
_I30 = {_l: _json.load(io.open(os.path.join(ROOT, "miniapp", "i18n", _l + ".json"),
                               encoding="utf-8")) for _l in ("pt", "en", "es")}

# ── 30.1 O SERVIDOR ─────────────────────────────────────────────────────────
chk(set(_REG30) == set(_E30.SISTEMAS) and len(_REG30) >= 5,
    "explica/servidor: os SISTEMAS do cliente (`EXPLICA`) sao os do servidor "
    "(`core/explicacoes.SISTEMAS`) — cliente %r, servidor %r"
    % (sorted(_REG30), sorted(_E30.SISTEMAS)))
chk(all(_REG30[s] for s in _REG30) and all(k in _I30["pt"] for s in _REG30 for k in _REG30[s]),
    "explica/servidor: cada sistema tem frase, e cada frase existe no i18n")

_on30 = lambda k: k == "a_obra"
_off30 = lambda k: False
_j30 = _NS30(explicacoes=None)
chk(_E30.para_payload(_j30, _off30) is None and _E30.para_payload(_j30, _on30) == {},
    "explica/servidor: onda OFF => nenhuma chave (o `main` byte-identico); ON => {} (nada gravado)")
chk(_E30.marcar_apto(_j30, "meditar", _off30) is False and _j30.explicacoes is None,
    "explica/servidor: com a onda OFF a accao NAO escreve — os 57 ficam NULL")
chk(_E30.recolher(_j30, "meditar", _on30) == (False, "nao_apto"),
    "explica/servidor: recolher o que nunca foi oferecido e' recusado (`nao_apto`) — o toque nao e' gatilho")
_E30.marcar_apto(_j30, "meditar", _on30)
chk(_j30.explicacoes == {"meditar": "apto"},
    "explica/servidor: a accao confirmada torna o sistema APTO (e so' esse)")
chk(_E30.recolher(_j30, "meditar", _on30) == (True, None)
    and _j30.explicacoes == {"meditar": "recolhido"}
    and _E30.recolher(_j30, "meditar", _on30) == (True, None),
    "explica/servidor: «Ja' percebi» recolhe — e dois toques dao UM estado")
chk(_E30.marcar_apto(_j30, "meditar", _on30) is False and _j30.explicacoes["meditar"] == "recolhido",
    "explica/servidor: agir outra vez NUNCA desfaz o recolhido")
chk(_E30.recolher(_j30, "nao_existe", _on30) == (False, "sistema_invalido"),
    "explica/servidor: um sistema fora do registo e' recusado")
_j30.explicacoes = dict(_j30.explicacoes, lixo="x", equipar="talvez")
chk(_E30.estados(_j30) == {"meditar": "recolhido"},
    "explica/servidor: a leitura so' conhece sistemas e valores do registo (lixo some, nao rebenta)")
chk(_E30.repor(_j30, _on30) == (True, None) and _j30.explicacoes == {"meditar": "apto"},
    "explica/servidor: Configuracoes -> o recolhido volta a APTO (a frase volta; a oferta fica)")
chk(_E30.repor(_NS30(explicacoes=None), _off30) == (False, "onda_off"),
    "explica/servidor: sem a onda, repor e' recusado")


def _fn_py30(nome):
    _m = re.search(r"^async def %s\(.*?(?=^async def |^def |\Z)" % re.escape(nome), _WS30, re.S | re.M)
    return _m.group(0) if _m else ""


# (a) cada endpoint que o REGISTO nomeia marca o SEU sistema, antes do commit
_mal30 = []
for _s30, _eps30 in _E30.SISTEMAS.items():
    for _ep30 in _eps30:
        _b30 = _fn_py30(_ep30)
        _call30 = re.search(r'_explica_apto\(player, "%s"\)' % _s30, _b30)
        _commits30 = [m.start() for m in re.finditer(r"await session\.commit\(\)", _b30)]
        if not _b30:
            _mal30.append("%s: endpoint nao existe" % _ep30)
        elif not _call30:
            _mal30.append("%s: nao marca %r" % (_ep30, _s30))
        elif not any(c > _call30.start() for c in _commits30):
            _mal30.append("%s: marca DEPOIS do commit" % _ep30)
        elif "from core.explicacoes import marcar_apto as _explica_apto" not in _b30:
            _mal30.append("%s: nao chama o DONO" % _ep30)
chk(not _mal30 and sum(len(v) for v in _E30.SISTEMAS.values()) >= 7,
    "explica/gatilho: os %d endpoints do registo marcam o SEU sistema, pelo dono, "
    "ANTES do commit (falham: %r)" % (sum(len(v) for v in _E30.SISTEMAS.values()), _mal30))
# (b) e so' no caminho do EXITO — os meridianos commitam SEMPRE (ate' na recusa)
for _ep30 in ("api_world_meridian_start", "api_world_meridian_break"):
    _b30 = _fn_py30(_ep30)
    chk(re.search(r'if isinstance\(result, dict\) and result\.get\("ok"\):\s*\n\s*from core\.explicacoes '
                  r'import marcar_apto as _explica_apto\s*\n\s*_explica_apto\(player, "corpo_mer"\)', _b30),
        "explica/gatilho `%s`: so' marca com o ritual ACEITE (`ok`) — este endpoint "
        "commita tambem a recusa" % _ep30)
_beq30 = _fn_py30("api_combat_equip_technique")
chk(re.search(r'if equip and tech\.tech_type == "combat":\s*\n\s*from core\.explicacoes import marcar_apto '
              r'as _explica_apto\s*\n\s*_explica_apto\(player, "equipar"\)', _beq30),
    "explica/gatilho: equipar so' conta com equip=TRUE de uma arte de COMBATE (desequipar nao ensina)")
_n_marcas30 = len(re.findall(r"_explica_apto\(player, \"", _WS30))
chk(_n_marcas30 == sum(len(v) for v in _E30.SISTEMAS.values()),
    "explica/gatilho: %d marcas no webserver = os endpoints do registo — uma marca "
    "fora do registo e' um gatilho sem documentacao" % _n_marcas30)
# (c) o payload: condicional no /player e na resposta do settings/update
chk('**({"explicacoes": _explicacoes} if _explicacoes is not None else {}),' in _WS30
    and "_explicacoes = _explica_payload(player)" in _WS30,
    "explica/payload: o `/player` manda o estado pelo dono, com a chave CONDICIONAL")
_bset30 = _fn_py30("api_settings_update")
chk('elif "explicacao_recolher" in payload:' in _bset30 and "_recolher(player," in _bset30
    and 'elif "explicacoes_repor" in payload:' in _bset30 and "_repor(player)" in _bset30
    and '**({"explicacoes": _expl_after} if _expl_after is not None else {}),' in _bset30,
    "explica/payload: `settings/update` recolhe e repoe PELO DONO e devolve o estado gravado")
# (d) a migration e o modelo
_mig30 = rd("migrations/142_explicacoes.sql")
chk("ADD COLUMN IF NOT EXISTS explicacoes JSONB DEFAULT NULL" in _mig30
    and "DROP" not in re.sub(r"--[^\n]*", "", _mig30).upper(),
    "explica/migration: 142 acrescenta a coluna NULL, sem DROP, sem backfill")
chk(re.search(r"explicacoes: Mapped\[dict \| None\] = mapped_column\(JSONB, nullable=True, default=None\)",
              rd("database/models.py")),
    "explica/modelo: `Player.explicacoes` nullable, NULL por defeito")

# ── 30.2 O CLIENTE sob node — a funcao REAL ─────────────────────────────────
_fe30 = _fn_src(_UIM, "    function explicaEstado(")
# so' a funcao: o `_fn_src` vai ate' a' seguinte e levava o `var _EXPLICA_BTN`
# (que le' o `NIV_ONDA`, inexistente sob node)
_fe30 = _fe30[:_fe30.index(chr(10) + "    }" + chr(10)) + 6]
_js30 = (_fe30 + "\nconst r = [explicaEstado(undefined,'meditar'), explicaEstado(null,'meditar'),"
         " explicaEstado({},'meditar'), explicaEstado({meditar:'talvez'},'meditar'),"
         " explicaEstado({meditar:'apto'},'meditar'), explicaEstado({meditar:'recolhido'},'meditar'),"
         " explicaEstado({meditar:'recolhido'},'equipar'), explicaEstado('recolhido','meditar')];"
         "\nprocess.stdout.write(JSON.stringify(r));")
try:
    _node30 = _sp30.run(["node", "-e", _js30], capture_output=True, text=True,
                        encoding="utf-8", timeout=60).stdout
    _res30 = _json.loads(_node30)
except Exception as _e:
    _res30 = repr(_e)
chk(_res30 == [None, None, None, None, "apto", "recolhido", None, None],
    "explica/cliente (node): sem preferencia LIDA nunca e' recolhido — so' o "
    "\"recolhido\" que o servidor disse recolhe (%r)" % (_res30,))

# ── 30.3 OS SITIOS — descobertos pelo REGISTO ───────────────────────────────


def _dentro_explica30(src, i):
    """O `<Explica ...>` aberto que contem a posicao i, ou None."""
    a = src.rfind("<Explica ", 0, i)
    if a < 0 or src.find("</Explica>", a, i) >= 0:
        return None
    return src[a:src.find(">", a) + 1]


_sitios30, _fora30 = [], []
for _s30, _ks30 in _REG30.items():
    for _k30 in _ks30:
        for _f30, _src30 in _FONTES30:
            for _m30 in re.finditer(r'"%s"' % re.escape(_k30), _src30):
                if _src30 is _UI30 and _UI30.find("var EXPLICA = ") <= _m30.start() <= \
                        _UI30.find("var EXPLICA = ") + len(_REG30_SRC) + 20:
                    continue   # o proprio registo
                _tag30 = _dentro_explica30(_src30, _m30.start())
                _obj30 = _src30[_m30.start():_m30.start() + 260]
                _ok30 = bool(_tag30 and ('sistema="%s"' % _s30) in _tag30) or \
                    ('explica:"%s"' % _s30) in _obj30.split("}")[0] + "}"
                _sitios30.append((_f30, _k30))
                if not _ok30:
                    _fora30.append("%s:%s" % (_f30, _k30))
# a frase DINAMICA do Corpo (`"corpo_explica_" + cam`) — pelo prefixo do registo
_pref30 = sorted({k.rsplit("_", 1)[0] + "_" for ks in _REG30.values() for k in ks
                  if k.startswith("corpo_explica_")})
for _p30 in _pref30:
    for _f30, _src30 in _FONTES30:
        for _m30 in re.finditer(r'"%s"\s*\+' % re.escape(_p30), _src30):
            _tag30 = _dentro_explica30(_src30, _m30.start())
            _sitios30.append((_f30, _p30 + "*"))
            if not (_tag30 and 'sistema={"corpo_" + cam}' in _tag30):
                _fora30.append("%s:%s*" % (_f30, _p30))
chk(all(("corpo_" + k.rsplit("_", 1)[1]) == s for s, ks in _REG30.items()
        for k in ks if k.startswith("corpo_explica_")),
    "explica/sitios: a frase `corpo_explica_<camada>` pertence ao sistema `corpo_<camada>` "
    "— e' isso que torna o `sistema={\"corpo_\" + cam}` honesto")
chk(not _fora30,
    "explica/sitios: toda frase do registo e' desenhada DENTRO do `Explica` do SEU "
    "sistema (fora: %r)" % _fora30)
chk(len(_sitios30) >= 4,
    "explica/sitios: a varredura ve' %d sitios — se desabasse para ~0 era o regex "
    "partido, nao o problema resolvido" % len(_sitios30))
_ch30 = _fn_src(_TB30, "    function Chegada(")
chk("acao && acao.explica ? (" in _ch30 and "<Explica sistema={acao.explica}" in _ch30
    and "estados={player && player.explicacoes}" in _ch30,
    "explica/sitios: a chegada desenha o `porque` pelo `Explica` quando o ramo o declara")

# ── 30.4 NENHUM NUMERO RECOLHE ─────────────────────────────────────────────
_num30 = [(l, k) for l in ("pt", "en", "es") for ks in _REG30.values() for k in ks
          if re.search(r"[0-9{}]", _I30[l].get(k, ""))]
chk(not _num30,
    "explica/prova: nenhuma frase registada carrega NUMERO ou placeholder — "
    "recolher evidencia e' o que a [017] proibe (%r)" % _num30)
_PROVA30 = ("cena_entrada_sem", "chegada_porque_recuperar", "chegada_porque_duelo",
            "chegada_porque_recompensa", "chegada_porque_avanco", "chegada_sem_acao",
            "combat_hp_way_out", "cena_ceiling_body", "cena_entrada_lugares",
            "tech_loadout_cap_hint", "combat_equipped_empty", "corpo_limite_reino",
            "onda_cb_left", "onda_med_need_qi", "onda_med_need_realm")
_mistura30 = [k for k in _PROVA30 if any(k in ks for ks in _REG30.values())]
chk(not _mistura30,
    "explica/prova: estado, bloqueio, limiar e caminho NUNCA entram no registo (%r)" % _mistura30)
_dentro30 = []
for _f30, _src30 in _FONTES30:
    for _m30 in re.finditer(r"<Explica\b", _src30):
        _fim30 = _src30.find("</Explica>", _m30.start())
        _corpo30 = _src30[_src30.find(">", _m30.start()) + 1:_fim30]
        if re.search(r"fmtFull\(|fmtNum\(|fmtDuration\(", _corpo30) or \
                any('"%s"' % k in _corpo30 for k in _PROVA30):
            _dentro30.append(_f30)
chk(not _dentro30 and len(re.findall(r"<Explica\b", _UI30 + _TB30)) >= 3,
    "explica/prova: dentro de um `Explica` so' mora a frase — nenhum numero, "
    "nenhuma chave de prova (%r)" % _dentro30)
chk('t("cena_entrada_sem")' in _fn_src(_UI30, "    function CenaEntradaCombate(")
    and _dentro_explica30(_fn_src(_UI30, "    function CenaEntradaCombate("),
                          _fn_src(_UI30, "    function CenaEntradaCombate(").find('t("cena_entrada_sem")')) is None,
    "explica/prova: \"Voce ainda nao equipou nenhuma arte\" e' ESTADO e fica sempre a' vista")

# ── 30.5 A GEOMETRIA e o "so' o confirmado" ─────────────────────────────────
_ex30 = _fn_src(_UI30, "    function Explica(")
chk(_ex30.count('gridArea:"1 / 1"') == 2 and "display:\"grid\"" in _ex30,
    "explica/geometria: frase e «Ajuda» na MESMA celula — a caixa tem sempre a "
    "altura da maior, e o comando de baixo nao mexe (medido: 601/601/601)")
chk("visibility: recolhida ? \"hidden\" : \"visible\"" in _ex30
    and "visibility: recolhida ? \"visible\" : \"hidden\"" in _ex30
    and not re.search(r"display\s*:\s*(recolhida|oferece|\"none\")", _ex30),
    "explica/geometria: esconde-se por `visibility` (continua a medir), nunca por `display`")
chk("{ visibility: oferece ? \"visible\" : \"hidden\" }" in _ex30
    and not re.search(r"\{\s*oferece\s*&&\s*<button", _ex30),
    "explica/geometria: «Ja' percebi» existe SEMPRE na linha, so' invisivel antes da "
    "accao — aparecer depois do clique nao pode empurrar o botao que se acabou de tocar")
_btn30 = _obj_after(_UIM, "var _EXPLICA_BTN = ")
chk('padding:"13px 6px", margin:"-13px -6px"' in _btn30 and "fontSize:12, lineHeight:(18/12)" in _btn30,
    "explica/geometria: alvo de 18+13+13 = 44px, com o padding compensado pela margem "
    "(a caixa de toque cresce, a linha nao)")
chk(re.search(r'const novo = \(r && r\.ok && r\.explicacoes\) \? r\.explicacoes\[sistema\] : null;\s*'
              r'if \(novo === "recolhido"\) \{\s*haptic\("select"\);\s*setConf\(', _ex30)
    and _ex30.count("setConf(") == 1,
    "explica/confirmado: a frase recolhe perante a RESPOSTA do servidor, nunca "
    "perante o toque (um `setConf` so', dentro do ramo confirmado)")
chk(_ex30.count('showToast(t("settings_explica_erro"), "err")') == 2,
    "explica/confirmado: sem confirmacao, a frase fica — e o toque DIZ que nada "
    "mudou (Lei §1; visto a servir com o pedido a falhar)")
chk("conf && conf.base === estados" in _ex30,
    "explica/confirmado: a copia confirmada morre quando o `/player` novo chega — "
    "nunca ha' dois donos do estado")

# ── 30.6 CONFIGURACOES · o fio do refresh · as linguas · a onda OFF ──────────
chk("{obraOn() && <SettingsExplicacoesSection onPlayerRefresh={onPlayerRefresh} />}"
    in _fn_src(_TB30, "    function SettingsTab("),
    "explica/config: «Mostrar as explicacoes de novo» vive no hub de Configuracoes, "
    "SO' com a onda (OFF = a tela de hoje)")
_sc30 = _fn_src(_TB30, "    function SettingsExplicacoesSection(")
chk('api("settings/update", { explicacoes_repor: true })' in _sc30
    and re.search(r"if \(r && r\.ok\) \{\s*haptic\(\"success\"\);\s*showToast\(t\(\"settings_explica_ok\"\)\)", _sc30),
    "explica/config: o aviso de sucesso so' sai com `ok` da resposta")
_cheg30 = re.findall(r"<Chegada\b(.*?)/>", _TB30, re.S)
chk(len(_cheg30) >= 2 and all("onPlayerRefresh={onPlayerRefresh}" in c for c in _cheg30)
    and "onPlayerRefresh={loadPlayer}" in re.search(r"<HubEuScreen\b(.*?)/>", _AP30, re.S).group(1),
    "explica/fio: as %d chegadas pedem o `/player` depois de recolher — a do Eu "
    "recebe-o do App" % len(_cheg30))
chk("explicacoes={player && player.explicacoes}" in _fn_src(_TB30, "    function CombatTab(")
    and "onRefresh={onPlayerRefresh}" in _fn_src(_TB30, "    function CombatTab("),
    "explica/fio: a entrada do Combate le' o estado do `/player`")
chk(re.search(r"if \(obraOn\(\)\) return <CorpoQueAcende", _TB30)
    and re.search(r"_cenaOn = obraOn\(\) && typeof CenaEntradaCombate", _TB30),
    "explica/OFF: os sitios so' existem com a onda — com ela OFF o DOM e' o de hoje "
    "(medido: hash das 3 telas igual antes/depois)")
_novas30 = ["explica_ja_percebi", "explica_ja_percebi_aria", "explica_ajuda", "explica_ajuda_aria",
            "settings_explica_titulo", "settings_explica_hint", "settings_explica_btn",
            "settings_explica_ok", "settings_explica_erro"]
for _l30 in ("pt", "en", "es"):
    _f30 = [k for k in _novas30 if not _I30[_l30].get(k)]
    chk(not _f30, "explica/i18n: `%s.json` tem as %d chaves (falta %r)" % (_l30, len(_novas30), _f30))
chk(len(_I30["pt"]) == len(_I30["en"]) == len(_I30["es"]),
    "explica/i18n: paridade (%d/%d/%d)" % (len(_I30["pt"]), len(_I30["en"]), len(_I30["es"])))
chk(_I30["pt"]["explica_ja_percebi"] == "Já entendi"
    and not any("percebi" in _I30["pt"][k].lower() for k in _novas30),
    "explica/i18n: pt e' do BRASIL — \"Ja' entendi\", nunca \"Ja' percebi\" (Portugal)")


# ══════════════════════════════════════════════════════════════════════════
# §31 — 冶 OS OFÍCIOS: o gate, o retrato, o ganho e os nomes (3.1, 2026-09-29)
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 O QUE SE MEDIU ANTES DE ESCREVER (Lei 0 passo 1):
#   · o limiar da Alquimia estava escrito À MÃO em 5 sítios (3 comparações
#     `< 1` e um `"min_realm_required": 1` no servidor, `realm < 1` no chat) e
#     o número vivia DENTRO do texto `alch_locked_msg`, com o reino em inglês
#     no pt-BR ("Qi Condensation (Reino 1)");
#   · o "quanto falta" (`TIERS[t + 1]["xp_req"]`) estava copiado 8 vezes no
#     servidor, e o resultado de uma feitura só dizia o GANHO ("+20 XP") — o
#     antes→depois que o Astra pede não existia em lado nenhum;
#   · a Forja mandava o artefacto com o nome CRU e sem chave de arte, as ervas
#     e os minérios crus, os 7 caldeirões nunca tiveram tradução, e o varredor
#     do nome não via nada disto (tirava da conta a LINHA inteira que
#     mencionasse `pill_name`).
#
# ⚠️ A FORMA do Ateliê é do Astra e NÃO está construída (limite semanal até
# 04/10 00:17). Esta secção guarda o que é MEU e já está no ar:
#   31.1 o DONO do gate — as rotas que recusam por reino vêm da TABELA DE
#        ROTAS do servidor, não de uma lista minha
#   31.2 o RETRATO — um só "quanto falta", contra as TABELAS dos motores
#   31.3 o GANHO — o que DÁ progresso a um ofício é descoberto nos MOTORES; toda
#        função do servidor que o chama tem de ler o "antes" e devolver o ganho
#   31.4 os NOMES — as funções dos ofícios vêm das ROTAS (e dos ajudantes que
#        elas chamam)
#   31.5 o TEXTO e o PYTHON 3.11 do contentor
print("\n=== 31. 冶 OS OFÍCIOS: o gate, o retrato, o ganho e os nomes ===")

import ast as _ast31
import json as _json31
from types import SimpleNamespace as _NS31
import core.oficios as _OF31
import core.alchemy_engine as _AE31
import core.forge_engine as _FE31
import core.i18n as _I31

_WS31 = rd("core/webserver.py")
_T31 = _ast31.parse(_WS31)
_FN31 = {}
for _n31 in _ast31.walk(_T31):
    if isinstance(_n31, (_ast31.FunctionDef, _ast31.AsyncFunctionDef)):
        _FN31.setdefault(_n31.name, _n31)


def _src31(fn):
    return _ast31.get_source_segment(_WS31, fn) or ""


def _chamadas31(fn):
    """(nome, no) de cada chamada dentro da funcao — `f(...)` ou `x.f(...)`."""
    out = []
    for _c in _ast31.walk(fn):
        if isinstance(_c, _ast31.Call):
            if isinstance(_c.func, _ast31.Name):
                out.append((_c.func.id, _c))
            elif isinstance(_c.func, _ast31.Attribute):
                out.append((_c.func.attr, _c))
    return out


def _chama31(fn, alvo):
    return any(_nm == alvo for _nm, _ in _chamadas31(fn))


# As ROTAS dos ofícios — lidas da tabela de rotas do servidor.
_ROTAS31 = dict(re.findall(r'add_post\("/api/miniapp/((?:alchemy|forge)[\w/]*)",\s*(\w+)\)', _WS31))
chk(len(_ROTAS31) >= 12
    and {"alchemy_recipes", "alchemy/craft", "alchemy/craft_bulk", "forge_recipes", "forge/craft"} <= set(_ROTAS31),
    "oficios/rotas: a tabela de rotas do servidor da' as %d rotas dos oficios" % len(_ROTAS31))

_MI31 = {_lg: _json31.loads(rd("miniapp/i18n/%s.json" % _lg)) for _lg in ("pt", "en", "es")}
_LO31 = {_lg: _json31.loads(rd("locales/%s.json" % _lg)) for _lg in ("pt", "en", "es")}

# ── 31.1 O DONO DO GATE DA ALQUIMIA ─────────────────────────────────────────
_MR31 = _AE31.ALCHEMY_MIN_REALM
chk(all(_AE31.alchemy_realm_locked(_NS31(realm=_r)) is (_r < _MR31) for _r in range(0, 11))
    and _AE31.alchemy_realm_locked(_NS31(realm=None)) is (0 < _MR31),
    "oficios/gate: `alchemy_realm_locked` fecha abaixo de `ALCHEMY_MIN_REALM` (R%d) — "
    "R0..R10 e reino nulo" % _MR31)

_atr31 = []
for _d31 in ("core", "handlers"):
    for _f31 in sorted(os.listdir(os.path.join(ROOT, _d31))):
        if not _f31.endswith(".py"):
            continue
        _t31 = rd(_d31 + "/" + _f31)
        if "ALCHEMY_MIN_REALM" not in _t31:
            continue
        for _n in _ast31.walk(_ast31.parse(_t31)):
            if isinstance(_n, _ast31.Assign) and any(
                    isinstance(_g, _ast31.Name) and _g.id == "ALCHEMY_MIN_REALM" for _g in _n.targets):
                _atr31.append(_d31 + "/" + _f31)
chk(_atr31 == ["core/alchemy_engine.py"],
    "oficios/gate: o limiar da Alquimia e' escrito UMA vez (atribuicoes: %r)" % _atr31)


def _literal_de_reino31(fn):
    """Uma comparacao de ORDEM do reino contra um numero escrito a' mao, ou um
    `min_realm`/`min_realm_required` com um numero literal no payload."""
    for _c in _ast31.walk(fn):
        if isinstance(_c, _ast31.Compare) and any(
                isinstance(_o, (_ast31.Lt, _ast31.LtE, _ast31.Gt, _ast31.GtE)) for _o in _c.ops):
            _lados = [_c.left] + list(_c.comparators)
            _segs = [(_ast31.get_source_segment(_WS31, _x) or "") for _x in _lados]
            if any("realm" in _s and "min_realm" not in _s for _s in _segs) and any(
                    isinstance(_x, _ast31.Constant) and type(_x.value) is int for _x in _lados):
                return _ast31.get_source_segment(_WS31, _c)
        if isinstance(_c, _ast31.Dict):
            for _k, _v in zip(_c.keys, _c.values):
                if (isinstance(_k, _ast31.Constant) and _k.value in ("min_realm", "min_realm_required")
                        and isinstance(_v, _ast31.Constant)):
                    return '"%s": %r' % (_k.value, _v.value)
    return None


_gate31 = [(_r, _nm) for _r, _nm in sorted(_ROTAS31.items())
           if _nm in _FN31 and '"realm_locked"' in _src31(_FN31[_nm])]
chk(len(_gate31) >= 3,
    "oficios/gate: as rotas que recusam por reino foram DESCOBERTAS na tabela de rotas "
    "(%d: %r)" % (len(_gate31), [_r for _r, _ in _gate31]))
for _r, _nm in _gate31:
    _lit31 = _literal_de_reino31(_FN31[_nm])
    chk(_chama31(_FN31[_nm], "alchemy_realm_locked") and not _lit31,
        "oficios/gate: `%s` (/%s) decide pelo dono `alchemy_realm_locked`, sem numero "
        "a' mao (%s)" % (_nm, _r, _lit31))
_rec31 = _src31(_FN31["api_alchemy_recipes"])
chk('"min_realm_required": ALCHEMY_MIN_REALM' in _rec31,
    "oficios/gate: a leitura manda ao cliente o limiar do MOTOR (`min_realm_required`)")

_CH31 = rd("handlers/alchemy.py")
_cmd31 = _CH31[_CH31.index("async def alquimia_command("):]
_cmd31 = _cmd31[:_cmd31.index("\nasync def ", 10)]
chk("alchemy_realm_locked(player)" in _cmd31 and not re.search(r"realm\s*<\s*\d", _cmd31),
    "oficios/gate: o chat (`/alquimia`) le' o MESMO dono, sem `realm < 1` a' mao")
for _lg, _pal in (("pt", "Reino"), ("en", "Realm"), ("es", "Reino")):
    _tx31 = _LO31[_lg]["milestone_locked_alchemy"]
    _nome31 = _MI31[_lg]["realm_%d" % _MR31]
    chk("(%s %d)" % (_pal, _MR31) in _tx31 and _nome31 in _tx31,
        "oficios/gate: o texto do chat (%s) diz o reino do MOTOR — \"%s\" (%s %d). O chat nao "
        "tem nome de reino localizado; esta guarda amarra o texto ao limiar" % (_lg, _nome31, _pal, _MR31))
for _lg in ("pt", "en", "es"):
    _v31 = _MI31[_lg]["alch_locked_msg"]
    chk("{realm}" in _v31 and "{n}" in _v31 and not re.search(r"\d", _v31),
        "oficios/gate: `alch_locked_msg` (%s) recebe o reino por parametro — nenhum numero "
        "nem nome de reino dentro do texto (%r)" % (_lg, _v31))
_AP31 = _fn_src(_TBM, "    function AlchemyPanel(")
chk('t("alch_locked_msg", { realm: realmName(data.min_realm_required), n: data.min_realm_required })' in _AP31
    and "Number.isInteger(data.min_realm_required)" in _AP31 and 't("alch_err_realm_locked")' in _AP31,
    "oficios/gate: o cliente escreve o reino do SERVIDOR pelo `realmName` — e sem o numero diz "
    "a frase generica, nunca \"Mortal\" por um `undefined`")

# ── 31.2 O RETRATO — um só "quanto falta" ──────────────────────────────────
_div31 = []
for _t in range(1, _AE31.MAX_ALCHEMY_TIER + 1):
    _rr = _OF31.retrato_alquimia(_NS31(tier=_t, xp=123))
    _es = _AE31.ALCHEMY_TIERS[_t + 1]["xp_req"] if _t < _AE31.MAX_ALCHEMY_TIER else None
    if (_rr["xp_to_next"], _rr["at_max"], _rr["xp"]) != (_es, _t == _AE31.MAX_ALCHEMY_TIER, 123):
        _div31.append("alquimia T%d" % _t)
for _t in range(1, _FE31.MAX_FORGE_TIER + 1):
    _rr = _OF31.retrato_forja(_NS31(tier=_t, xp=7))
    _es = _FE31.FORGE_TIERS[_t + 1]["xp_req"] if _t < _FE31.MAX_FORGE_TIER else None
    if (_rr["xp_to_next"], _rr["at_max"]) != (_es, _t == _FE31.MAX_FORGE_TIER):
        _div31.append("forja T%d" % _t)
for _t in range(0, _AE31.MAX_SOUL_FIRE_TIER + 1):
    _rr = _OF31.retrato_fogo(_NS31(fire_tier=_t, fire_exp=9))
    _es = _AE31.SOUL_FIRE_TIERS[_t + 1]["xp_req"] if _t < _AE31.MAX_SOUL_FIRE_TIER else None
    if (_rr["xp_to_next"], _rr["xp"]) != (_es, 9):
        _div31.append("fogo T%d" % _t)
for _L in range(1, _AE31.MAX_MASTERY_LEVEL + 1):
    _m = _NS31(mastery_level=_L, crafts_count=_L * 7)
    _rr, _e = _OF31.retrato_receita_pilula(_m), _AE31.get_mastery_next_info(_m)
    if (_rr["next_crafts"], _rr["next_level"], _rr["at_max"], _rr["crafts_count"]) != (
            _e.get("next_crafts"), _e.get("next_level"), _e["at_max"], _e["crafts"]):
        _div31.append("pilula L%d" % _L)
for _L in range(1, _FE31.MAX_FORGE_MASTERY + 1):
    _m = _NS31(mastery_level=_L, forges_count=_L * 7)
    _rr, _e = _OF31.retrato_receita_forja(_m), _FE31.get_forge_mastery_next_info(_m)
    if (_rr["next_forges"], _rr["next_level"], _rr["at_max"], _rr["forges_count"]) != (
            _e.get("next_forges"), _e.get("next_level"), _e["at_max"], _e["forges"]):
        _div31.append("receita forja L%d" % _L)
chk(not _div31,
    "oficios/retrato: o retrato bate com as TABELAS e com o `*_next_info` dos motores "
    "(a formula que a lista usava) — divergem: %r" % _div31)
_r0p31, _r0f31 = _OF31.retrato_receita_pilula(None), _OF31.retrato_receita_forja(None)
chk((_r0p31["level"], _r0p31["crafts_count"], _r0p31["next_crafts"]) == (1, 0, _AE31.MASTERY_LEVELS[2]["crafts_req"])
    and (_r0f31["level"], _r0f31["forges_count"], _r0f31["next_forges"]) == (1, 0, _FE31.FORGE_MASTERY_LEVELS[2]["forges_req"]),
    "oficios/retrato: receita sem linha = o estado com que o MOTOR a cria (nivel 1, 0 feitos, o "
    "limiar da TABELA — nao o `10` escrito a' mao que la' estava)")
chk(_OF31.retrato_alquimia(_NS31(tier=0, xp=0))["tier"] == 0
    and _OF31.retrato_fogo(_NS31(fire_tier=0, fire_exp=0))["tier"] == 0,
    "oficios/retrato: um 0 real continua 0 — so' o `None` vira o valor de criacao")
for _nm, _donos in (("api_alchemy_recipes", ("retrato_alquimia", "retrato_fogo", "retrato_receita_pilula")),
                    ("api_forge_recipes", ("retrato_forja", "retrato_receita_forja"))):
    chk(all(_chama31(_FN31[_nm], _d) for _d in _donos),
        "oficios/retrato: `%s` monta o oficio e a maestria pelo dono (%s)" % (_nm, ", ".join(_donos)))
_WSC31 = _sem_prosa_py(_WS31)
_copias31 = re.findall(r'(?:ALCHEMY|FORGE|SOUL_FIRE)_TIERS\[[^\]]*\+\s*1\]\s*\[\s*"xp_req"\s*\]', _WSC31)
_copias31 += re.findall(r'"next_(?:crafts|forges)":\s*\d', _WSC31)
chk(not _copias31,
    "oficios/retrato: nenhuma copia do \"quanto falta\" no servidor (eram 8) — %d: %r"
    % (len(_copias31), _copias31[:3]))

# ── 31.3 O GANHO — o que DÁ progresso vem dos MOTORES ───────────────────────
_COLS31 = {"xp", "fire_exp", "crafts_count", "forges_count", "mastery_level"}


def _progresso31(caminhos):
    """As funcoes dos motores que SOBEM uma coluna de progresso de um oficio,
    e (em fecho) as que chamam uma delas."""
    _fns = {}
    for _p in caminhos:
        for _n in _ast31.walk(_ast31.parse(rd(_p))):
            if isinstance(_n, (_ast31.FunctionDef, _ast31.AsyncFunctionDef)):
                _fns[_n.name] = _n
    _base = set()
    for _nm, _fn in _fns.items():
        for _x in _ast31.walk(_fn):
            if (isinstance(_x, _ast31.AugAssign) and isinstance(_x.op, _ast31.Add)
                    and isinstance(_x.target, _ast31.Attribute) and _x.target.attr in _COLS31):
                _base.add(_nm)
    _mudou = True
    while _mudou:
        _mudou = False
        for _nm, _fn in _fns.items():
            if _nm not in _base and any(_c in _base for _c, _ in _chamadas31(_fn)):
                _base.add(_nm)
                _mudou = True
    return _base


_PROG31 = _progresso31(["core/alchemy_engine.py", "core/forge_engine.py", "core/inventory_actions.py"])
chk({"grant_alchemy_xp", "grant_forge_xp", "increment_pill_mastery", "increment_forge_mastery",
     "grant_soul_fire_xp", "craft_pill", "forge_recipe_item", "feed_beast_core_to_soul_fire"} <= _PROG31,
    "oficios/ganho: o que DA' progresso a um oficio vem dos MOTORES (%d funcoes: %s)"
    % (len(_PROG31), ", ".join(sorted(_PROG31))))

# Os SITIOS: todo `def` do servidor (rota ou ajudante) que chama o motor de
# progresso. Sem lista de excepcoes: um ajudante novo que suba a maestria sem
# ler o "antes" fica vermelho ate' alguem decidir o seu ganho.
_sitios31 = sorted(_nm for _nm, _fn in _FN31.items()
                   if any(_c in _PROG31 for _c, _ in _chamadas31(_fn)))
chk({"api_alchemy_craft", "api_alchemy_craft_bulk", "api_forge_craft", "api_alchemy_feed_core"} <= set(_sitios31),
    "oficios/ganho: os sitios que confirmam progresso foram DESCOBERTOS pelos motores (%r)" % _sitios31)
for _nm in _sitios31:
    _fn = _FN31[_nm]
    _le = [(_c, _no) for _c, _no in _chamadas31(_fn) if _c.startswith("ler_antes_")]
    _mo = [_no.lineno for _c, _no in _chamadas31(_fn) if _c in _PROG31]
    chk(bool(_le) and _chama31(_fn, "no_payload") and min(_no.lineno for _, _no in _le) < min(_mo),
        "oficios/ganho: `%s` confirma progresso — le' o \"antes\" (%s) ANTES do motor e devolve o "
        "ganho pelo dono" % (_nm, sorted({_c for _c, _ in _le}) or "NENHUM"))

_ga31 = _OF31.ganho(
    oficio=(_OF31.retrato_alquimia(_NS31(tier=2, xp=1990)), _OF31.retrato_alquimia(_NS31(tier=3, xp=2010))),
    receita=(_OF31.retrato_receita_pilula(_NS31(mastery_level=2, crafts_count=20)),
             _OF31.retrato_receita_pilula(_NS31(mastery_level=2, crafts_count=21))),
    fogo=(None, None))
chk(_ga31["acende"] == ["oficio"] and "fogo" not in _ga31 and _ga31["receita"]["depois"]["crafts_count"] == 21,
    "oficios/ganho: acende SO' o eixo cuja CONQUISTA subiu — o traco da receita subiu e nao "
    "acende; um eixo sem dados nao entra como \"0 -> 0\"")
try:
    _OF31.ganho(energia=({"tier": 1}, {"tier": 2}))
    _rb31 = False
except ValueError:
    _rb31 = True
except Exception:
    _rb31 = False  # rebentar por OUTRO motivo (KeyError...) e' vermelho, nao crash
chk(_rb31 and tuple(_OF31.EIXOS) == ("oficio", "receita", "fogo"),
    "oficios/ganho: um eixo fora dos tres que acendem (energia, chama, preco...) REBENTA no "
    "servidor em vez de chegar ao ecra")
_gx31 = _OF31.ganho(oficio=(_OF31.retrato_forja(_NS31(tier=5, xp=20000)),
                            _OF31.retrato_forja(_NS31(tier=5, xp=20025))))
chk(_gx31["acende"] == [] and _gx31["oficio"]["depois"]["xp_to_next"] is None,
    "oficios/ganho: no maximo o XP sobe e nada acende; o \"quanto falta\" e' `None`, nunca um "
    "denominador inventado")
chk(_OF31.no_payload({"acende": []}, lambda k: False) == {}
    and _OF31.no_payload(None, lambda k: True) == {}
    and _OF31.no_payload({"acende": []}, lambda k: k == "a_obra") == {"oficio_ganho": {"acende": []}},
    "oficios/ganho: a chave so' viaja com a onda (o `main` recebe o payload de hoje) e nunca como `null`")
_OFS31 = rd("core/oficios.py")
for _n in _ast31.walk(_ast31.parse(_OFS31)):
    if isinstance(_n, _ast31.AsyncFunctionDef) and _n.name.startswith("ler_antes_"):
        _seg = _ast31.get_source_segment(_OFS31, _n)
        chk(not re.search(r"\.add\(|\.flush\(|get_or_create|\.commit\(", _seg),
            "oficios/ganho: `%s` so' LE — nada de add/flush/get_or_create (uma receita inexistente "
            "tem de dizer `recipe_not_found`, nao rebentar numa FK)" % _n.name)
chk('"oficio_ganho"' not in _WSC31,
    "oficios/ganho: o servidor nunca escreve `oficio_ganho` a' mao — so' pelo `no_payload`")

# ── 31.4 OS NOMES — as funções dos ofícios vêm das ROTAS ────────────────────
_RESOLVE31 = {"catalog_name", "catalog_desc", "catalog_text", "catalog_art_key"}


def _crus31(fn):
    """Leituras `.name`/`.description` que nao passam por um resolvedor."""
    _dentro = set()
    for _c in _ast31.walk(fn):
        if isinstance(_c, _ast31.Call) and isinstance(_c.func, _ast31.Name) and _c.func.id in _RESOLVE31:
            _dentro.update(id(_x) for _x in _ast31.walk(_c))
    return [_ast31.get_source_segment(_WS31, _x) for _x in _ast31.walk(fn)
            if isinstance(_x, _ast31.Attribute) and _x.attr in ("name", "description")
            and isinstance(_x.ctx, _ast31.Load) and id(_x) not in _dentro]


_ofn31 = {_nm for _nm in _ROTAS31.values() if _nm in _FN31}
for _nm in list(_ofn31):
    for _c, _ in _chamadas31(_FN31[_nm]):
        if _c in _FN31 and _c.startswith("_") and _c not in ("_json", "_err"):
            _ofn31.add(_c)
_cru31 = {_nm: _crus31(_FN31[_nm]) for _nm in sorted(_ofn31)}
_cru31 = {_k: _v for _k, _v in _cru31.items() if _v}
chk(len(_ofn31) >= 16 and not _cru31,
    "oficios/nomes: nenhuma leitura crua de nome/descricao nas %d funcoes dos oficios "
    "(rotas + ajudantes) — %r" % (len(_ofn31), _cru31))
chk('"artifact_art_key": catalog_art_key(blueprint)' in _src31(_FN31["api_forge_recipes"]),
    "oficios/nomes: a receita da Forja manda a CHAVE da arte ao lado do nome traduzido "
    "(traduzir sem a chave apaga a peca — 14/09)")
chk(_src31(_FN31["api_alchemy_craft_bulk"]).count('"pill_art_key": catalog_art_key(pill)') == 2,
    "oficios/nomes: a tribulacao nascida de um LOTE leva o nome e a chave de arte do craft "
    "simples (no estado e na resposta)")
from database.seeds.alchemy_seeds import CAULDRONS as _CS31
_cald31 = {_k for _k in _LO31["pt"] if re.match(r"^cauldron_\d+_(name|desc)$", _k)}
chk(len(_cald31) == 2 * len(_CS31)
    and all({_k for _k in _LO31[_lg] if re.match(r"^cauldron_\d+_(name|desc)$", _k)} == _cald31 for _lg in ("en", "es"))
    and {"cauldron_%d_name" % _c["id"] for _c in _CS31} <= _cald31,
    "oficios/nomes: os %d caldeiroes dos SEEDS tem nome e descricao nas 3 linguas" % len(_CS31))
chk("cauldron" in _I31._CATALOG_KINDS
    and _I31.catalog_name("pt", "cauldron", _NS31(id=1, name="Copper Cauldron")) == _LO31["pt"]["cauldron_1_name"] != "Copper Cauldron",
    "oficios/nomes: o dono do catalogo serve a familia `cauldron` (pt: %s)" % _LO31["pt"].get("cauldron_1_name"))

# ── 31.5 O TEXTO DO OFÍCIO e o PYTHON DO CONTENTOR ──────────────────────────
_ruins31 = ["%s:%s" % (_lg, _k) for _lg in ("pt", "es") for _k, _v in _MI31[_lg].items()
            if (_k.startswith("alch_") or _k.startswith("forge_")) and re.search(r"craft|heavenly", _v, re.I)]
chk(not _ruins31,
    "oficios/texto: nenhum `alch_*`/`forge_*` em pt/es diz \"craft\"/\"heavenly\" (%r)" % _ruins31[:4])
_verbo31 = [_k for _k in _MI31["pt"] if _k.startswith("alch_craft")]
chk(_verbo31 and all("Refin" in _MI31["pt"][_k] and "Refin" in _MI31["es"][_k] for _k in _verbo31),
    "oficios/texto: o botao da Alquimia REFINA (pt/es) — dizia \"Forjar\", o verbo da Forja (%r)" % _verbo31)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import _audit_py311 as _P31
_p311 = _P31.scan()
# 開 Na cópia comunitária o chão é 250: ela não leva `tools/` (~100 scripts de
# operação do jogo oficial). Medido a 21/10: 294 ficheiros. O chão continua a
# existir pela mesma razão — uma auditoria que lê ZERO ficheiros fica verde.
chk(_p311["total"] == 0 and _p311["ficheiros"] >= 250,
    "py311: o contentor e' `python:3.11` — nenhuma f-string com sintaxe so' do 3.12 nos %d "
    "ficheiros (%r)" % (_p311["ficheiros"], list(_p311["achados"].items())[:2]))
_DF31 = rd("Dockerfile")
chk(re.search(r"^FROM python:3\.11", _DF31, re.M) is not None or "3.11" not in _DF31,
    "py311: o `Dockerfile` ainda diz `python:3.11` (se mudar, esta guarda e o varredor mudam com ele)")


# ══════════════════════════════════════════════════════════════════════════
# §32 — 🎒 O INVENTÁRIO: o anel com dono, a tabela e os nomes (3.2, 2026-09-30)
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 O QUE SE MEDIU ANTES (Lei 0 passo 1 — `tools/db_readonly_anel_0930.py`):
#   · a conta do anel vivia em TRES sitios (a expansao do chat, a do mini-app e
#     o botao do chat, que JA' mentia: anunciava o maximo ABSOLUTO do tier a
#     quem comprou lugares no Pavilhao — 1 anel no `main`);
#   · a mochila era uma parede de cartas de ~270 px, duas por fila (4.212 px
#     para 26 linhas; p90 = 91 artefactos guardados, max. 732);
#   · o que nao era pilula/erva/minerio chegava ao ecra como
#     "technique_scroll #12" (229 jogadores no `main`) e o chat nomeava-o em
#     INGLES fixo; o detalhe escrevia qualidade, tipo e grau crus em ingles.
#
#   32.1 o DONO do anel — a conta, o retrato (OFF-identidade) e o ganho; a
#        rota CORRE numa sessao que compila no dialecto do Postgres (a licao
#        do 500 do golpe padrao, no mesmo dia)
#   32.2 os NOMES — os tipos que tocam a mochila sao descobertos nos
#        ESCRITORES e nas CONSULTAS do codigo, nunca numa lista minha
#   32.3 a TABELA — "tabela para gerir, carta para ver" (Astra, [018] §1)
#   32.4 o ANEL no ecra — a luz com o numero, so' o confirmado acende
print("\n=== 32. 🎒 O INVENTÁRIO: o anel com dono, a tabela e os nomes ===")

import ast as _ast32
import asyncio as _aio32
import json as _json32
from types import SimpleNamespace as _NS32
from sqlalchemy.dialects import postgresql as _pg32
import core.anel as _AN32
import core.itens as _IT32
import core.portas as _PO32
import core.utils as _UT32
import core.webserver as _W32

# ── 32.1 O DONO DO ANEL ─────────────────────────────────────────────────────
chk(_AN32.proximo_max(4, 510) == 1010 and _AN32.proximo_max(4, 500) == 1000,
    "anel/conta: a expansao e' ADITIVA — um T4 com 510 (10 comprados no Pavilhao) "
    "vai a 1010, nunca a 1000 (o botao do chat anunciava 1000)")
chk(_AN32.proximo_max(5, 1000) is None and _AN32.custo_proximo(5) is None,
    "anel/conta: no topo nao ha' proxima expansao nem preco (None, nunca 0)")
chk([_AN32.custo_proximo(_t) for _t in (1, 2, 3, 4)] == [1000, 5000, 25000, 100000],
    "anel/conta: o preco de cada expansao e' o da tabela do dono")
_r32 = _NS32(tier=3, max_slots=210)
_ad32 = _AN32.expandir(_r32)
chk(_ad32 == {"tier": {"antes": 3, "depois": 4}, "max_slots": {"antes": 210, "depois": 510}}
    and (_r32.tier, _r32.max_slots) == (4, 510),
    "anel/conta: `expandir` muda a linha e devolve o antes->depois DA MESMA linha")
try:
    _AN32.expandir(_NS32(tier=5, max_slots=1000))
    _topo32 = False
except ValueError:
    _topo32 = True
chk(_topo32, "anel/conta: expandir no topo REBENTA — um defeito nao pode dar um tier 6")

chk(list(_AN32.retrato(3, 200, 20, False)) == ["tier", "max_slots", "used_slots", "can_upgrade", "next_cost"],
    "anel/retrato: com a onda OFF o bloco `ring` tem as chaves de HOJE, pela mesma ordem")
chk(list(_AN32.retrato(5, 1000, 20, False)) == ["tier", "max_slots", "used_slots", "can_upgrade"]
    and _AN32.retrato(5, 1000, 20, False)["can_upgrade"] is False,
    "anel/retrato: OFF no topo — sem `next_cost`, como hoje")
_on32 = _AN32.retrato(3, 200, 20, True)
chk(_on32.get("max_tier") == _AN32.MAX_RING_TIER and _on32.get("next_max_slots") == 500,
    "anel/retrato: com a onda, o denominador (`max_tier`) e a meta real (`next_max_slots`) "
    "vem do SERVIDOR — o cliente nunca inventa \"nivel 3 de ?\"")
chk("next_max_slots" not in _AN32.retrato(5, 1000, 20, True),
    "anel/retrato: no topo nao ha' meta (a chave nao nasce, nunca `null`)")
_g32 = _AN32.ganho(_ad32)
chk(_g32["acende"] == ["tier"] and _g32["tier"] == {"antes": 3, "depois": 4}
    and _g32["max_slots"] == {"antes": 210, "depois": 510},
    "anel/ganho: acende SO' o nivel (a conquista); os lugares sao numero antes->depois")
chk(tuple(_AN32.EIXOS_QUE_ACENDEM) == ("tier",),
    "anel/ganho: a ocupacao e os lugares NUNCA acendem — o unico eixo e' o nivel")


class _Res32:
    def __init__(self, o):
        self._o = o

    def scalar_one_or_none(self):
        return self._o


class _Sess32:
    """Compila cada query no dialecto do Postgres antes de responder — uma
    coluna que nao existe rebenta AQUI como rebentaria em producao."""

    def __init__(self, jogador):
        self.j, self.sql, self.commits = jogador, [], 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt):
        self.sql.append(str(stmt.compile(dialect=_pg32.dialect())))
        return _Res32(self.j)

    async def commit(self):
        self.commits += 1


def _expande32(tier, max_slots, pedras, onda):
    """Corre `api_inventory_ring_upgrade` de ponta a ponta."""
    _j = _NS32(telegram_id=77, spirit_stones=pedras)
    _anel = _NS32(tier=tier, max_slots=max_slots)
    _s = _Sess32(_j)
    _orig = (_W32.get_session_factory, _UT32._get_or_create_ring, _PO32.onda_on)

    async def _ring(_sess, _pid):
        return _anel
    _W32.get_session_factory = lambda: (lambda: _s)
    _UT32._get_or_create_ring = _ring
    _PO32.onda_on = lambda *a, **k: onda
    try:
        _resp = _aio32.run(_W32.api_inventory_ring_upgrade({"user_id": 77, "payload": {}}))
        return _json32.loads(_resp.text), _anel, _j, _s
    except Exception as _ex:
        return "%s: %s" % (type(_ex).__name__, str(_ex)[:100]), _anel, _j, _s
    finally:
        _W32.get_session_factory, _UT32._get_or_create_ring, _PO32.onda_on = _orig


_c32, _a32, _j32, _s32 = _expande32(3, 210, 50000, True)
chk(isinstance(_c32, dict) and _c32.get("ok") is True
    and _c32.get("anel_ganho") == {"tier": {"antes": 3, "depois": 4},
                                   "max_slots": {"antes": 210, "depois": 510}, "acende": ["tier"]},
    "anel/rota: a expansao CORRE e devolve `anel_ganho` com o antes da linha TRANCADA (%r)" % (_c32,))
chk(isinstance(_c32, dict) and (_a32.tier, _a32.max_slots, _j32.spirit_stones, _s32.commits) == (4, 510, 25000, 1)
    and _c32.get("spent") == 25000,
    "anel/rota: cobra 25.000, grava tier 4 / 510 lugares, um commit")
chk(len(_s32.sql) == 1 and "FOR UPDATE" in _s32.sql[0],
    "anel/rota: o jogador e' lido TRANCADO (as pedras nao se gastam duas vezes)")
_c32, _a32, _j32, _s32 = _expande32(3, 200, 50000, False)
chk(isinstance(_c32, dict) and list(_c32) == ["ok", "tier", "max_slots", "spent", "spirit_stones"],
    "anel/rota: com a onda OFF a resposta e' a de HOJE, chave a chave (%r)" % (_c32,))
_c32, _a32, _j32, _s32 = _expande32(3, 200, 1000, True)
chk(_c32 == {"ok": False, "reason": "not_enough_stones", "cost": 25000, "have": 1000}
    and (_a32.tier, _s32.commits) == (3, 0),
    "anel/rota: sem pedras recusa a DIZER o preco e o que tem, e nao grava nada")
_c32, _a32, _j32, _s32 = _expande32(5, 1000, 999999, True)
chk(_c32 == {"ok": False, "reason": "ring_max"} and (_a32.tier, _s32.commits) == (5, 0),
    "anel/rota: no topo recusa com `ring_max` e nao grava nada")

# As COPIAS da conta, descobertas na AST: uma atribuicao a `.max_slots` (ou ao
# `.tier` de um anel) fora do dono. O Pavilhao de Prestigio SOMA lugares
# comprados — essa e' outra operacao, e e' a unica excepcao.
_copias32, _expansoes32 = [], []
for _d32 in ("core", "handlers"):
    for _f32 in sorted(os.listdir(os.path.join(ROOT, _d32))):
        if not _f32.endswith(".py"):
            continue
        _rel32 = _d32 + "/" + _f32
        _t32 = _ast32.parse(rd(_rel32))
        for _n32 in _ast32.walk(_t32):
            if isinstance(_n32, (_ast32.Assign, _ast32.AugAssign)):
                _alvos32 = _n32.targets if isinstance(_n32, _ast32.Assign) else [_n32.target]
                for _al32 in _alvos32:
                    if (isinstance(_al32, _ast32.Attribute)
                            and (_al32.attr == "max_slots"
                                 or (_al32.attr == "tier" and isinstance(_al32.value, _ast32.Name)
                                     and "ring" in _al32.value.id.lower()))):
                        if _rel32 not in ("core/anel.py", "core/prestige_shop_engine.py"):
                            _copias32.append("%s:%d" % (_rel32, _n32.lineno))
            if (isinstance(_n32, _ast32.Call) and isinstance(_n32.func, _ast32.Attribute)
                    and _n32.func.attr == "expandir" and _rel32 != "core/anel.py"):
                _expansoes32.append(_rel32)
chk(not _copias32,
    "anel/dono: nenhuma conta do anel fora de `core/anel.py` (e do Pavilhao, que SOMA "
    "lugares comprados) — %r" % _copias32)
chk(sorted(set(_expansoes32)) == ["core/webserver.py", "handlers/inventory.py"],
    "anel/dono: ANTI-GUARDA — as duas portas que expandem (mini-app e chat) chamam o dono "
    "(%r)" % sorted(set(_expansoes32)))
_HI32 = rd("handlers/inventory.py")
# ⚠️ SEM os comentarios: o comentario que explica a correccao CITA o texto
# antigo (`RING_MAX_SLOTS[next_tier]`), e a guarda leria a prosa.
_hic32 = "\n".join(_l.split("#")[0] for _l in _HI32.split("\n"))
_ri32 = _hic32.split("async def _ring_info(")[1].split("\nasync def ")[0]
chk("_anel.proximo_max(ring.tier, ring.max_slots)" in _ri32 and "RING_MAX_SLOTS[next_tier]" not in _ri32,
    "anel/dono: o botao do chat anuncia a conta que a expansao FAZ (era o maximo absoluto)")
_WS32 = rd("core/webserver.py")
_inv32 = _WS32.split("async def api_inventory(")[1].split("\nasync def ")[0]
chk("_anel.retrato(ring.tier, ring.max_slots, used_slots, _onda_on())" in _inv32
    and '"can_upgrade":' not in _inv32,
    "anel/dono: o bloco `ring` do inventario sai do retrato do dono (nao de um dict a' mao)")

# ── 32.2 OS NOMES DO QUE NAO E' PILULA, ERVA NEM MINERIO ─────────────────────
# Os tipos que tocam a mochila, descobertos no CODIGO: os escritores (com o
# tipo literal), o construtor `PlayerInventory(item_type=...)` e as consultas
# a `PlayerInventory.item_type`. A 1a medicao achou 3 que nenhuma tabela
# nomeava (ovo de besta, anel de jade, receita).
_ESCR32 = {"add_item_to_inventory": 2, "_add_inventory": 2, "_give_item": 2, "_add_inventory_item": 2}


def _lits32(_no):
    if isinstance(_no, _ast32.Constant) and isinstance(_no.value, str):
        return [_no.value]
    if isinstance(_no, (_ast32.Tuple, _ast32.List, _ast32.Set)):
        return [_e.value for _e in _no.elts if isinstance(_e, _ast32.Constant) and isinstance(_e.value, str)]
    return []


_tipos32 = set()
for _d32 in ("core", "handlers"):
    for _f32 in sorted(os.listdir(os.path.join(ROOT, _d32))):
        if not _f32.endswith(".py"):
            continue
        for _n32 in _ast32.walk(_ast32.parse(rd(_d32 + "/" + _f32))):
            if isinstance(_n32, _ast32.Call):
                _nm32 = (_n32.func.id if isinstance(_n32.func, _ast32.Name)
                         else _n32.func.attr if isinstance(_n32.func, _ast32.Attribute) else None)
                if _nm32 in _ESCR32:
                    _i32 = _ESCR32[_nm32]
                    _arg32 = (_n32.args[_i32] if len(_n32.args) > _i32
                              else next((_k.value for _k in _n32.keywords if _k.arg == "item_type"), None))
                    _tipos32.update(_lits32(_arg32))
                if _nm32 == "PlayerInventory":
                    for _k32 in _n32.keywords:
                        if _k32.arg == "item_type":
                            _tipos32.update(_lits32(_k32.value))
                if (isinstance(_n32.func, _ast32.Attribute) and _n32.func.attr in ("in_", "notin_")
                        and isinstance(_n32.func.value, _ast32.Attribute) and _n32.func.value.attr == "item_type"
                        and isinstance(_n32.func.value.value, _ast32.Name)
                        and _n32.func.value.value.id == "PlayerInventory"):
                    for _a32 in _n32.args:
                        _tipos32.update(_lits32(_a32))
            if (isinstance(_n32, _ast32.Compare) and isinstance(_n32.left, _ast32.Attribute)
                    and _n32.left.attr == "item_type" and isinstance(_n32.left.value, _ast32.Name)
                    and _n32.left.value.id == "PlayerInventory"):
                for _c32 in _n32.comparators:
                    _tipos32.update(_lits32(_c32))
_outros32 = sorted(_tipos32 - {"pill", "herb", "ore"})
chk(len(_outros32) >= 6 and {"technique_scroll", "beast_trap", "beast_core"} <= set(_outros32),
    "nomes: ANTI-GUARDA — o localizador ve os tipos que tocam a mochila (%r)" % _outros32)
chk(set(_outros32) <= _IT32.TIPOS,
    "nomes: TODO tipo que o jogo escreve/consulta na mochila tem nome no dono "
    "(sem nome: %r)" % sorted(set(_outros32) - _IT32.TIPOS))
_sem32 = []
for _tp32 in sorted(_IT32.TIPOS):
    for _lg32 in ("pt", "en", "es"):
        _nm32 = _IT32.nome(_lg32, _tp32, 3, tecnica=("X" if _tp32 == "technique_scroll" else None))
        if not _nm32 or _tp32 in _nm32 or _nm32 == _IT32.nome(_lg32, "__nada__"):
            _sem32.append("%s:%s=%r" % (_lg32, _tp32, _nm32))
chk(not _sem32,
    "nomes: os %d tipos tem nome PROPRIO nas 3 linguas — nem o tipo cru, nem o generico "
    "(%r)" % (len(_IT32.TIPOS), _sem32[:4]))
_fi32 = _ast32.parse(_WS32)
_apiinv32 = next(_n for _n in _ast32.walk(_fi32)
                 if isinstance(_n, _ast32.AsyncFunctionDef) and _n.name == "api_inventory")
_crus32 = [_ast32.unparse(_n)[:40] for _n in _ast32.walk(_apiinv32)
           if isinstance(_n, _ast32.JoinedStr)
           and any(isinstance(_v, _ast32.FormattedValue) and isinstance(_v.value, _ast32.Name)
                   and _v.value.id == "itype" for _v in _n.values)]
chk(not _crus32,
    "nomes: o inventario ja' nao monta o nome com o tipo cru (`f\"{itype} #{iid}\"`) — %r" % _crus32)
chk("_itens.nome(" in _inv32 and "scrolls_map" in _inv32,
    "nomes: o inventario nomeia pelo dono, e o pergaminho pela TECNICA (em bloco)")
chk("_MISC_LABELS" not in _hic32
    and _hic32.count("_itens.nome(lang, inv.item_type, inv.item_id)") == 2,
    "nomes: o chat nomeia os 'outros' pelo MESMO dono (a tabela inglesa `_MISC_LABELS` saiu)")
chk(_LO31["es"].get("beast_core_name") == "Núcleo Bestial",
    "nomes: o nucleo bestial tem acento em es (dizia \"Nucleo\")")
_LO32 = {_lg: _json32.loads(rd("locales/%s.json" % _lg)) for _lg in ("pt", "en", "es")}
_chaves32 = sorted(set(_IT32._CHAVE.values()) | {"inv_item_technique_scroll", "inv_item_ore_pack",
                                                  "inv_item_generic", "dng_drop_scroll"})
chk(all(_k in _LO32[_lg] for _k in _chaves32 for _lg in ("pt", "en", "es")),
    "nomes: as %d chaves do dono existem nas 3 linguas do servidor" % len(_chaves32))

# ── 32.3 A TABELA — "tabela para gerir, carta para ver" ──────────────────────
_TB32 = rd("miniapp/components/tabs.js")
_INVT32 = _fn25(_TB32, "    function InventoryTab(")
_CT32 = _fn25(_TB32, "    function ColecaoTabela(")
chk(len(_INVT32) > 5000 and len(_CT32) > 800,
    "tabela: ANTI-GUARDA — a aba e a tabela foram fatiadas (%d / %d)" % (len(_INVT32), len(_CT32)))
chk(_INVT32.count("const tabela = obraOn();") == 1 and "ondaCultOn()" not in _INVT32,
    "tabela: UM leitor da chave-mestra na aba (`obraOn`) — nunca o portao lido a' mao")
_i32h = _INVT32.find("const [anelGanho, setAnelGanho] = useState(null);")
_i32r = _INVT32.find("if (loading && !data) return")
chk(0 < _i32h < _i32r,
    "tabela: o estado novo nasce ANTES dos `return` antecipados (React #310 — um hook "
    "depois de um return parte a aba)")
chk("{(showAll || section === \"equipment\") && tabela && (" in _INVT32
    and "{(showAll || section === \"equipment\") && !tabela && (" in _INVT32
    and "if (tabela) {" in _INVT32,
    "tabela: a pilha e as familias so' viram tabela COM a onda; sem ela, a mochila de hoje")
chk('aria-hidden="true"' in _CT32 and "aria-label={l.aria}" in _CT32 and "<button" in _CT32,
    "tabela: cada linha e' um botao que diz TUDO no aria-label; o cabecalho das colunas e' visual")
_LI32 = _fn25(_TB32, "    function linhaItem(")
chk("fmtFull(it.quantity" in _LI32 and "fmtNum(" not in _LI32,
    "tabela: a quantidade sai INTEIRA (9.369.341 e' a maior erva medida) — nunca abreviada")
chk('"inv_card_kind_pill"' in _INVT32 and '"inv_card_kind_herb"' in _INVT32
    and 'rotulo: t("inv_card_kind_artifact")' in _INVT32,
    "tabela: o TIPO sobe para o cabecalho das colunas (a linha deixa de o repetir)")
chk("const comQualidade = list.some(it => qualidadeDoItem(it) != null);" in _INVT32,
    "tabela: a coluna da qualidade so' existe onde a qualidade existe (erva/minerio sao sempre "
    "\"normal\" — 1.301 linhas de erva medidas)")
_BE32 = rd("core/beast_engine.py")
_ord32 = re.search(r"TRAP_QUALITY_ORDER\s*=\s*(\{[^}]*\})", _BE32)
_rar32 = sorted(_ast32.literal_eval(_ord32.group(1))) if _ord32 else []
chk(len(_rar32) >= 5,
    "tabela: ANTI-GUARDA — as raridades da armadilha lidas do MOTOR da captura (%r)" % _rar32)
chk(all(("inv_tab_raridade_" + _r) in _MI31[_lg] for _r in _rar32 for _lg in ("pt", "en", "es")),
    "tabela: toda raridade que a captura conhece tem palavra nas 3 linguas (a carta nunca a dizia)")
# ⚠️ SEM comentarios de bloco NEM de linha: a 1a versao so' tirava os `//` e
# ficou vermelha a ler o `/* era "Awakened Spirit" cru */` que explica a
# correccao — a guarda lia a prosa (licao de 13/09, outra vez).
_TBc32 = "\n".join(_l for _l in re.sub(r"/\*.*?\*/", "", _TB32, flags=re.S).split("\n")
                   if not _l.lstrip().startswith("//"))
chk('{entry.quality || "normal"}' not in _TBc32 and '"Awakened Spirit"' not in _TBc32
    and "{entry.type || entry.slot}" not in _TBc32,
    "detalhe: a qualidade, o tipo e o espirito ja' nao saem crus em ingles (\"PERFECT\", \"Weapon\")")
_gn32 = [_l.strip()[:70] for _l in _TBc32.split("\n") if ".grade_name" in _l and "nomeDoGrau(" not in _l]
chk(not _gn32,
    "detalhe: todo `grade_name` do servidor (ingles) passa pelo `nomeDoGrau` — %r" % _gn32[:3])

# ── 32.4 O ANEL NO ECRA ──────────────────────────────────────────────────────
_AC32 = _fn25(_TB32, "    function AnelCorpo(")
_MO32 = _fn25(_TB32, "    function MarcaOnda(")
chk(len(_AC32) > 2000 and len(_MO32) > 800,
    "anel/ecra: ANTI-GUARDA — o corpo do anel e a marca foram fatiados")
chk(_TBc32.count('"corpo-nucleo-acende"') == 1 and '"corpo-nucleo-acende"' in _MO32,
    "anel/ecra: a marca tem UM dono (`MarcaOnda`) — o Corpo e o anel desenham a mesma "
    "(duas copias da gramatica divergem sempre)")
chk("<MarcaOnda" in _fn25(_TB32, "    function CorpoFigura(") and _AC32.count("<MarcaOnda") == 1,
    "anel/ecra: o Corpo e a inscricao do anel pedem a marca ao dono; a ocupacao nao tem marca "
    "(e' estado, nao conquista)")
chk("const max = Number(ring.max_tier) || 0;" in _AC32 and "MAX_RING_TIER" not in _AC32,
    "anel/ecra: o denominador e' o do servidor — sem ele, nenhuma inscricao (nunca um `|| 5`)")
_EA32 = _INVT32.split("const expandirAnel = async () => {")[1].split("\n      };")[0] if "const expandirAnel" in _INVT32 else ""
chk("if (res.ok === true && res.anel_ganho) setAnelGanho(res.anel_ganho);" in _EA32
    and _INVT32.count("setAnelGanho(") == 1,
    "anel/ecra: so' uma resposta `ok: true` com `anel_ganho` acende — nunca o toque (e e' o "
    "UNICO sitio que escreve o ganho)")
chk(all(_k in _AC32 for _k in ('"inv_ring_nivel_de"', '"inv_ring_ganho"', '"inv_ring_faltam"',
                                '"inv_ring_expandir"', '"inv_ring_limite"')),
    "anel/ecra: o numero acompanha a luz — nivel N de M, antes->depois confirmado, a "
    "condicao que falta e o limite")
# (um prefixo DINAMICO — `"inv_tab_raridade_" + q` — nao e' uma chave: as que
#  ele forma entram pelo motor da captura)
_k32 = sorted({_k for _k in re.findall(r't\("((?:inv_tab|inv_ring)_[a-z0-9_]+)"', _TBc32)
               if not _k.endswith("_")}
              | {"inv_tab_raridade_" + _r for _r in _rar32})
chk(len(_k32) >= 30 and all(_k in _MI31[_lg] for _k in _k32 for _lg in ("pt", "en", "es")),
    "anel/i18n: as %d chaves do inventario que o codigo pede existem nas 3 linguas "
    "(falta %r)" % (len(_k32), [_k for _k in _k32 if _k not in _MI31["es"]][:4]))

# ── 32.5 O ARNES nao mente sobre o anel ──────────────────────────────────────
_AR32 = rd("scripts/_dev_serve_miniapp.py")
chk("_ANEL_DONO.retrato(" in _AR32 and "_ANEL_DONO.expandir(" in _AR32
    and "_ANEL_DONO.resposta_expansao(" in _AR32 and '"ring": {"tier"' not in _AR32,
    "arnes: o anel encenado e a expansao passam pelo DONO (era tier 3 com 150 lugares — impossivel)")


# ══════════════════════════════════════════════════════════════════════════
# §33 — 🐾 AS BESTAS: o selo de crescimento, o ganho e os nomes (3.3, 2026-10-01)
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 O QUE SE MEDIU ANTES (Lei 0 passo 1 — `tools/db_readonly_bestas_1001.py`):
#   · `main` 242 jogadores / 1.107 bestas; p50 = UMA besta (148 so' a inicial),
#     p90 = 16, max. 32; 288 no nivel 100 (162 com XP a sobrar no tecto); 74 ja'
#     evoluiram; 124 prontas a evoluir AGORA;
#   · o limiar de XP (`level * 100`) escrito a' mao em OITO sitios;
#   · posto, elemento e habilidade crus em ingles; o arnes dava a TODAS as
#     bestas a mesma evolucao ("Uncommon, nivel 20, 3 nucleos").
#
#   33.1 o DONO — o limiar, a linha, o retrato e o ganho; as portas que mudam
#        nivel/posto sao DESCOBERTAS nos motores e nas rotas, e CORREM numa
#        sessao que compila no dialecto do Postgres (a licao do 500 de 30/09)
#   33.2 os NOMES — posto, elemento, bonus e habilidade nas 3 linguas
#   33.3 o ECRA — a besta selecionada, o selo, so' o confirmado acende
#   33.4 o ARNES corre as rotas reais
print("\n=== 33. 🐾 AS BESTAS: o selo de crescimento, o ganho e os nomes ===")

import ast as _ast33
import asyncio as _aio33
import json as _json33
from types import SimpleNamespace as _NS33
from sqlalchemy.dialects import postgresql as _pg33
import config as _CF33
import core.bestas as _BS33
import core.beast_engine as _BE33
import core.portas as _PO33
import core.webserver as _W33
from database.seeds.beasts_seeds import BEASTS as _SEED33, EXPEDITIONS as _SEEDX33

_CAT33 = {_c["id"]: _NS33(**_c) for _c in _SEED33}
_EXP33 = [_NS33(**_e) for _e in _SEEDX33]

# ── 33.1 O DONO ──────────────────────────────────────────────────────────────
# (a) o LIMIAR de XP tem um dono — as copias sao descobertas na AST: um
#     `<qualquer>.level * 100` fora do `limiar_xp`.
_limiar33, _chamam33, _motor33 = [], set(), 0
for _d33 in ("core", "handlers"):
    for _f33 in sorted(os.listdir(os.path.join(ROOT, _d33))):
        if not _f33.endswith(".py"):
            continue
        _rel33 = _d33 + "/" + _f33
        for _n33 in _ast33.walk(_ast33.parse(rd(_rel33))):
            if isinstance(_n33, _ast33.BinOp) and isinstance(_n33.op, _ast33.Mult):
                for _a33, _b33 in ((_n33.left, _n33.right), (_n33.right, _n33.left)):
                    if (isinstance(_a33, _ast33.Attribute) and _a33.attr == "level"
                            and isinstance(_b33, _ast33.Constant) and _b33.value == 100):
                        _limiar33.append("%s:%d" % (_rel33, _n33.lineno))
            if isinstance(_n33, _ast33.Call):
                _nm33 = (_n33.func.id if isinstance(_n33.func, _ast33.Name)
                         else _n33.func.attr if isinstance(_n33.func, _ast33.Attribute) else None)
                if _nm33 == "limiar_xp":
                    _chamam33.add(_rel33)
                    if _rel33 == "core/beast_engine.py":
                        _motor33 += 1
chk(not _limiar33,
    "bestas/dono: nenhum `X.level * 100` fora do `limiar_xp` — o fio que a tela desenha e' "
    "a conta com que o motor sobe (%r)" % _limiar33)
chk({"core/beast_engine.py", "core/bestas.py", "handlers/beasts.py"} <= _chamam33 and _motor33 >= 6,
    "bestas/dono: ANTI-GUARDA — o treino, o lote, a recolha, a lista e o chat pedem o limiar "
    "ao dono (%r, %d no motor)" % (sorted(_chamam33), _motor33))
chk(_BE33.limiar_xp(12) == 1200 and _BE33.limiar_xp(1) == 100,
    "bestas/dono: o limiar e' `nivel x 100` (12 -> 1.200)")

# (b) a LINHA: as mesmas chaves, pela mesma ordem, de quando era um dict no
#     endpoint; e o retrato e' um subconjunto dela (o cliente poe o "depois"
#     por cima do que ja' mostra).
_CH33 = ["id", "catalog_id", "name", "art_key", "rank", "rank_idx", "level", "max_level", "exp",
         "exp_needed", "is_companion", "is_on_expedition", "expedition_returns_at_ms", "emoji",
         "element", "special_ability", "base_stats", "effective_stats", "evolution", "train_cost",
         "train_xp_per_step"]


def _besta33(bid=7, cid=2, rank="Uncommon", level=12, exp=640, comp=False, exped=False):
    return _NS33(id=bid, player_id=77, catalog_id=cid, custom_name=_CAT33[cid].name, rank=rank,
                 level=level, exp=exp, is_companion=comp, is_on_expedition=exped,
                 expedition_type=("Herb Expedition" if exped else None),
                 expedition_returns_at=None)


_lin33 = _BS33.serializar(_besta33(), _CAT33[2], "pt")
chk(list(_lin33) == _CH33,
    "bestas/linha: a linha de `beasts/list.owned[]` tem as chaves de HOJE, pela mesma ordem (%r)"
    % [k for k in _lin33 if k not in _CH33])
chk(set(_BS33.retrato(_besta33(), _CAT33[2])) <= set(_CH33),
    "bestas/linha: o retrato usa as chaves da LINHA (o 'depois' pousa por cima sem traducao)")
chk(_lin33["evolution"]["next_rank"] == "Rare" and _lin33["evolution"]["level_needed"] == 20
    and _lin33["exp_needed"] == 1200 and _lin33["name"] == "Tartaruga de Jade",
    "bestas/linha: a evolucao, o limiar e o nome saem dos DONOS (Incomum -> Raro no nivel 20)")
_WS33 = rd("core/webserver.py")
_bbp33 = _WS33.split("async def _build_beasts_payload(")[1].split("\nasync def ")[0]
chk("_bestas.serializar(b, catalog_map.get(b.catalog_id), _lang_b, food_mult)" in _bbp33
    and '"effective_stats":' not in _bbp33 and "* 100" not in _bbp33,
    "bestas/linha: a lista do mini-app pede a linha ao dono (nao um dict a' mao)")

# (c) o GANHO: so' o nivel e o posto acendem; o XP e' traco.
def _r33(level, idx, exp=0):
    return {"level": level, "exp": exp, "rank_idx": idx}


chk(_BS33.ganho(_r33(12, 1, 640), _r33(12, 1, 740))["acende"] == []
    and _BS33.ganho(_r33(12, 1), _r33(13, 1))["acende"] == ["nivel"]
    and _BS33.ganho(_r33(50, 4), _r33(50, 5))["acende"] == ["posto"]
    and _BS33.ganho(_r33(12, 1), _r33(22, 2))["acende"] == ["nivel", "posto"],
    "bestas/ganho: o XP sozinho nao acende; o nivel e o posto confirmados acendem (juntos num lote)")
chk(tuple(_BS33.EIXOS_QUE_ACENDEM) == ("nivel", "posto"),
    "bestas/ganho: so' DUAS conquistas — companheira, expedicao, pedras e nucleos nunca acendem")
# o espelho da chave-mestra: o ganho so' viaja com a onda (a rota OFF nem o le',
# mas o dono do payload tem de dizer o mesmo sozinho)
chk(_BS33.no_payload({"acende": []}, lambda _k: False) == {}
    and _BS33.no_payload({"acende": []}, lambda _k: _k == "a_obra") == {"besta_ganho": {"acende": []}}
    and _BS33.no_payload(None, lambda _k: True) == {},
    "bestas/ganho: `besta_ganho` so' viaja com a chave-mestra — sem ela, o payload de HOJE")


# (d) as PORTAS que mudam nivel/posto — descobertas nos MOTORES (quem atribui
#     `.level`/`.rank`) e nas ROTAS do servidor (quem os chama).
_esc33 = set()
for _n33 in _ast33.walk(_ast33.parse(rd("core/beast_engine.py"))):
    if isinstance(_n33, (_ast33.FunctionDef, _ast33.AsyncFunctionDef)):
        for _m33 in _ast33.walk(_n33):
            if isinstance(_m33, (_ast33.Assign, _ast33.AugAssign)):
                _als33 = _m33.targets if isinstance(_m33, _ast33.Assign) else [_m33.target]
                if any(isinstance(_t, _ast33.Attribute) and _t.attr in ("level", "rank") for _t in _als33):
                    _esc33.add(_n33.name)
chk({"train_beast", "train_beast_bulk", "evolve_beast", "collect_expedition"} <= _esc33,
    "bestas/portas: ANTI-GUARDA — os escritores de nivel/posto lidos no MOTOR (%r)" % sorted(_esc33))
_rotas33 = dict(re.findall(r'add_post\("/api/miniapp/(beasts/[a-z_]+)", (api_[a-z_]+)\)', _WS33))
_fws33 = {_n.name: _n for _n in _ast33.walk(_ast33.parse(_WS33))
          if isinstance(_n, _ast33.AsyncFunctionDef)}
_portas33, _sem33 = {}, []
for _rota33, _fn33 in sorted(_rotas33.items()):
    _no33 = _fws33.get(_fn33)
    if _no33 is None:
        continue
    _ch33 = [_c.func.id for _c in _ast33.walk(_no33) if isinstance(_c, _ast33.Call)
             and isinstance(_c.func, _ast33.Name) and _c.func.id in _esc33]
    if _ch33:
        _portas33[_rota33] = _ch33
        _src33 = _ast33.unparse(_no33)
        if not ("_bestas.ler_antes(session, user_id, beast_id) if _onda_on() else None" in _src33
                and _src33.count("_bestas.ganho_da_acao(") == len(_ch33)
                and _src33.count("_bestas.no_payload(_g)") == len(_ch33)):
            _sem33.append(_rota33)
chk(set(_portas33) == {"beasts/level_up", "beasts/evolve", "beasts/collect_expedition"},
    "bestas/portas: ANTI-GUARDA — as rotas que mudam nivel/posto, descobertas nas ROTAS (%r)"
    % sorted(_portas33))
chk(not _sem33,
    "bestas/portas: TODA porta que muda nivel/posto le' o 'antes' (so' com a onda) e devolve o "
    "ganho por cada motor que chama (%r)" % _sem33)


# (e) as portas CORREM — de ponta a ponta, numa sessao que compila no dialecto
#     do Postgres (uma coluna que nao existe rebenta aqui como em producao).
class _Res33:
    def __init__(self, rows=None, scalar=None, first=None, rowcount=0):
        self._rows, self._scalar, self._first, self.rowcount = list(rows or []), scalar, first, rowcount

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        _rows = self._rows
        return _NS33(all=lambda: list(_rows), first=lambda: (_rows[0] if _rows else None))

    def scalar(self):
        return self._scalar

    def first(self):
        return self._first

    def all(self):
        return list(self._rows)


class _Sess33:
    def __init__(self, jogador, bestas, inv):
        self.j, self.bestas, self.inv = jogador, bestas, inv
        self.sql, self.commits = [], 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        self.commits += 1

    async def flush(self):
        return None

    async def rollback(self):
        return None

    def add(self, o):
        return None

    async def get(self, ent, ident):
        _nm = getattr(ent, "__name__", "")
        if _nm == "PlayerBeast":
            return next((b for b in self.bestas if b.id == int(ident)), None)
        if _nm == "BeastCatalog":
            return _CAT33.get(int(ident))
        return None

    async def execute(self, stmt):
        from sqlalchemy.sql.dml import Update
        _txt = str(stmt.compile(dialect=_pg33.dialect()))
        try:
            _lit = str(stmt.compile(dialect=_pg33.dialect(), compile_kwargs={"literal_binds": True}))
        except Exception:
            _lit = _txt
        self.sql.append(_txt)
        if isinstance(stmt, Update):
            return _Res33()
        _cd = stmt.column_descriptions
        _ent = _cd[0].get("entity")
        _nm = getattr(_ent, "__name__", "")
        _inteira = len(_cd) == 1 and _cd[0].get("expr") is _ent
        _mid = re.search(r"\b\w+\.id = (\d+)", _lit)
        if _nm == "Player":
            return _Res33([self.j])
        if _nm == "PlayerBeast":
            _rows = [b for b in self.bestas if not _mid or b.id == int(_mid.group(1))]
            if "is_on_expedition = true" in _lit:
                _rows = [b for b in _rows if b.is_on_expedition]
            if _inteira:
                return _Res33(_rows)
            _r0 = _rows[0] if _rows else None
            return _Res33(first=(_NS33(**{c["name"]: getattr(_r0, c["name"]) for c in _cd}) if _r0 else None))
        if _nm == "BeastCatalog":
            return _Res33([c for c in _CAT33.values() if not _mid or c.id == int(_mid.group(1))])
        if _nm == "ExpeditionCatalog":
            _mn = re.search(r"expeditions_catalog\.name = '([^']*)'", _lit)
            return _Res33([e for e in _EXP33 if (not _mn or e.name == _mn.group(1))
                           and (not _mid or e.id == int(_mid.group(1)))])
        if _nm == "PlayerInventory":
            _rows = [r for r in self.inv if r.quantity > 0 and ("'%s'" % r.item_type) in _lit]
            return _Res33(_rows) if _inteira else _Res33(scalar=sum(r.quantity for r in _rows))
        if "count(" in _lit.lower() or "sum(" in _lit.lower():
            return _Res33(scalar=0)
        return _Res33()


def _corre33(fn, payload, onda, bestas, pedras=50000, nucleos=0):
    _j = _NS33(telegram_id=77, spirit_stones=pedras, language="pt", luck=0, realm=3, hunt_essence=0)
    _inv = [_NS33(player_id=77, item_type="beast_core", item_id=0, quantity=nucleos, quality="normal")]
    _s = _Sess33(_j, bestas, _inv)
    _orig = (_W33.get_session_factory, _PO33.onda_on)
    _W33.get_session_factory = lambda: (lambda: _s)
    _PO33.onda_on = lambda *a, **k: onda
    try:
        _resp = _aio33.run(getattr(_W33, fn)({"user_id": 77, "payload": payload}))
        return _json33.loads(_resp.text), _j, _s, _inv
    except Exception as _ex:
        return "%s: %s" % (type(_ex).__name__, str(_ex)[:120]), _j, _s, _inv
    finally:
        _W33.get_session_factory, _PO33.onda_on = _orig


_COLS33 = "SELECT player_beasts.level, player_beasts.exp, player_beasts.rank, player_beasts.catalog_id"
# um treino que sobe UM nivel (1.150 + 100 >= 1.200)
_b33 = _besta33(level=12, exp=1150)
_c33, _j33, _s33, _ = _corre33("api_beasts_level_up", {"beast_id": 7, "count": 1}, True, [_b33])
_g33 = _c33.get("besta_ganho") if isinstance(_c33, dict) else None
chk(isinstance(_g33, dict) and _g33["antes"]["level"] == 12 and _g33["depois"]["level"] == 13
    and _g33["acende"] == ["nivel"] and _j33.spirit_stones == 50000 - 600 and _b33.level == 13,
    "bestas/rota: o treino CORRE e devolve `besta_ganho` 12 -> 13 com o nivel aceso (%r)" % (_c33,))
_ic33 = next((i for i, q in enumerate(_s33.sql) if q.startswith(_COLS33)), -1)
_ie33 = next((i for i, q in enumerate(_s33.sql) if q.startswith("SELECT player_beasts.id")), -1)
chk(0 <= _ic33 < _ie33 and "FOR UPDATE" in _s33.sql[_ic33],
    "bestas/rota: o 'antes' le' COLUNAS (nunca a entidade — o mapa de identidade daria ao motor "
    "os valores velhos) e TRANCADO, ANTES do motor")
_b33 = _besta33(level=12, exp=640)
_c33, _j33, _s33, _ = _corre33("api_beasts_level_up", {"beast_id": 7, "count": 1}, False, [_b33])
chk(isinstance(_c33, dict) and list(_c33) == ["ok", "reason", "error_params", "cost", "xp_gained",
                                              "levels_gained", "new_level", "exp", "exp_needed",
                                              "xp_boosted"]
    and not any(q.startswith(_COLS33) for q in _s33.sql),
    "bestas/rota: com a onda OFF a resposta do treino e' a de HOJE e nao ha' leitura nem trinco "
    "a mais (%r)" % (_c33,))
_b33 = _besta33(level=12, exp=640)
_c33, _j33, _s33, _ = _corre33("api_beasts_level_up", {"beast_id": 7, "count": 10}, True, [_b33],
                               pedras=10 ** 7)
_g33 = _c33.get("besta_ganho") if isinstance(_c33, dict) else None
chk(isinstance(_g33, dict) and _g33["antes"]["level"] == 12 and _g33["depois"]["level"] == 22
    and _g33["acende"] == ["nivel"] and _c33.get("levels_gained") == 10,
    "bestas/rota: o lote assenta os 10 niveis JUNTOS, um ganho so' (12 -> 22) (%r)" % (_g33 and _g33["acende"],))
_b33 = _besta33(level=12, exp=640)
_c33, _j33, _s33, _ = _corre33("api_beasts_level_up", {"beast_id": 7, "count": 1}, True, [_b33], pedras=10)
chk(isinstance(_c33, dict) and _c33.get("ok") is False and "besta_ganho" not in _c33
    and _b33.level == 12 and _b33.exp == 640,
    "bestas/rota: sem pedras recusa, e uma recusa NUNCA leva ganho (nada acende sem confirmacao)")
_b33 = _besta33(cid=8, rank="Legendary", level=50, exp=0)
_c33, _j33, _s33, _inv33 = _corre33("api_beasts_evolve", {"beast_id": 7}, True, [_b33], nucleos=20)
_g33 = _c33.get("besta_ganho") if isinstance(_c33, dict) else None
chk(isinstance(_g33, dict) and _g33["antes"]["rank"] == "Legendary" and _g33["depois"]["rank"] == "Mythic"
    and _g33["acende"] == ["posto"] and _inv33[0].quantity == 5
    and _g33["depois"]["effective_stats"]["luck_mult"] > _g33["antes"]["effective_stats"]["luck_mult"],
    "bestas/rota: a evolucao CORRE — Lendario -> Mitico, o posto aceso, 15 nucleos gastos, a "
    "Sorte antes->depois (%r)" % (_c33 if not isinstance(_g33, dict) else _g33["acende"],))
_b33 = _besta33(cid=8, rank="Legendary", level=50, exp=0)
_c33, _, _s33, _ = _corre33("api_beasts_evolve", {"beast_id": 7}, False, [_b33], nucleos=20)
chk(isinstance(_c33, dict) and list(_c33) == ["ok", "reason", "error_params", "old_rank", "new_rank",
                                              "cores_used"],
    "bestas/rota: com a onda OFF a resposta da evolucao e' a de HOJE (%r)" % (_c33,))
_b33 = _besta33(cid=1, rank="Common", level=3, exp=0, exped=True)
_c33, _, _s33, _ = _corre33("api_beasts_collect_expedition", {"beast_id": 7}, True, [_b33])
_g33 = _c33.get("besta_ganho") if isinstance(_c33, dict) else None
chk(isinstance(_g33, dict) and _g33["depois"]["exp"] > _g33["antes"]["exp"] and _g33["acende"] == []
    and _b33.is_on_expedition is False,
    "bestas/rota: a recolha da expedicao CORRE e devolve o XP antes->depois (traco, sem luz) (%r)"
    % (_c33 if not isinstance(_g33, dict) else (_g33["antes"]["exp"], _g33["depois"]["exp"]),))

# ── 33.2 OS NOMES ────────────────────────────────────────────────────────────
_LO33 = {_lg: _json33.loads(rd("locales/%s.json" % _lg)) for _lg in ("pt", "en", "es")}
_MI33 = {_lg: _json33.loads(rd("miniapp/i18n/%s.json" % _lg)) for _lg in ("pt", "en", "es")}
_hab33 = []
for _s in _SEED33:
    _k = "beast_%d_ability" % _s["id"]
    if not (_LO33["en"].get(_k) == _s["special_ability"]
            and all(_LO33[_lg].get(_k) and _LO33[_lg][_k] != _s["special_ability"] for _lg in ("pt", "es"))):
        _hab33.append(_k)
chk(len(_SEED33) == 15 and not _hab33,
    "nomes: as 15 habilidades tem frase propria em pt e es (en = o catalogo, tal e qual) — %r" % _hab33)
chk(_BE33.beast_ability_text("pt", _CAT33[2]) == _LO33["pt"]["beast_2_ability"]
    and _BE33.beast_ability_text("en", _CAT33[2]) == _CAT33[2].special_ability
    and _BE33.beast_ability_text("pt", None) == "",
    "nomes: o dono da habilidade (`beast_ability_text`) le' a frase da lingua — sem chave, o catalogo")
_HB33 = rd("handlers/beasts.py")
_hbc33 = "\n".join(_l.split("#")[0] for _l in _HB33.split("\n"))
chk("catalog.special_ability" not in _hbc33 and "beast_ability_text(lang, catalog)" in _hbc33,
    "nomes: o detalhe do chat diz a habilidade pelo MESMO dono (era a frase inglesa)")
_scat33 = _bbp33.split("def _serialize_catalog(")[1] if "def _serialize_catalog(" in _bbp33 else ""
chk('"special_ability": beast_ability_text(_lang_b, c),' in _scat33,
    "nomes: o catalogo da captura diz a habilidade na lingua do jogador")
chk(all("Beast " not in _LO33[_lg][_k] and "trap" not in _LO33[_lg][_k]
        for _lg in ("pt", "es") for _k in ("beast_egg_drop", "beast_level_up")),
    "nomes: o espolio da expedicao ja' nao diz \"Beast Egg\"/\"Beast subiu\" em pt e es")
_elem33 = sorted({_s["element"] for _s in _SEED33})
chk(len(_elem33) >= 9 and all(("world_element_" + _e.lower()) in _MI33[_lg]
                              for _e in _elem33 for _lg in ("pt", "en", "es")),
    "nomes: TODO elemento das especies (lidos nos SEEDS: %d) tem palavra nas 3 linguas — %r"
    % (len(_elem33), [_e for _e in _elem33 if ("world_element_" + _e.lower()) not in _MI33["pt"]]))
_bon33 = sorted({_k for _s in _SEED33 for _k in _s["base_stats"]})
chk(len(_bon33) >= 6 and all(("beasts_bonus_" + _k) in _MI33[_lg] for _k in _bon33 for _lg in ("pt", "en", "es")),
    "nomes: TODO bonus das especies (lidos nos SEEDS: %r) tem nome nas 3 linguas" % _bon33)
chk(all(("beast_rank_" + _r.lower()) in _MI33[_lg] for _r in _CF33.BEAST_RANKS for _lg in ("pt", "en", "es")),
    "nomes: os %d postos do motor (`config.BEAST_RANKS`) tem palavra nas 3 linguas" % len(_CF33.BEAST_RANKS))

_TB33 = rd("miniapp/components/tabs.js")
_TBc33 = "\n".join(_l for _l in re.sub(r"/\*.*?\*/", "", _TB33, flags=re.S).split("\n")
                   if not _l.lstrip().startswith("//"))
_corpos33 = {_f: _fn25(_TBc33, "    function %s(" % _f)
             for _f in ("BestasOnda", "BestaLinha", "BeastsCompanionPanel", "BeastsCapturePanel",
                        "BeastCaptureOutcomeModal", "BeastExpeditionModal")}
chk(all(len(_v) > 400 for _v in _corpos33.values()),
    "nomes: ANTI-GUARDA — as seis telas que a onda alcanca foram fatiadas (%r)"
    % {_k: len(_v) for _k, _v in _corpos33.items()})
_crus33 = []
for _f, _v in _corpos33.items():
    for _m in re.finditer(r"(?<!rank=)\{\s*[\w.]+\.(rank|element)\s*\}|rank:\s*[\w.]+\.(rank|req_beast_rank)\b"
                          r"|\{\s*result\.rank \|\| target\.rank\s*\}", _v):
        _crus33.append("%s: %s" % (_f, _m.group(0)))
chk(not _crus33,
    "nomes: nenhuma tela das bestas imprime o posto/elemento CRU (`{b.rank}`) — passa por "
    "`postoDaBesta`/`elementoDaBesta` (%r)" % _crus33[:4])
chk(sum(_v.count("postoDaBesta(") for _v in _corpos33.values()) >= 10
    and sum(_v.count("elementoDaBesta(") for _v in _corpos33.values()) >= 4,
    "nomes: ANTI-GUARDA — as telas pedem o nome ao dono (postoDaBesta/elementoDaBesta)")
_pd33 = _fn25(_TBc33, "    function postoDaBesta(")
_ed33 = _fn25(_TBc33, "    function elementoDaBesta(")
chk("if (!obraOn()) return rank;" in _pd33 and "if (!obraOn() || !el) return el;" in _ed33,
    "nomes: SEM a chave-mestra o dono devolve o valor de HOJE (a OFF-identidade e' por construcao)")
_mir33 = re.search(r"function _BEAST_RANK_INDEX\(rank\) \{.*?const list = (\[[^\]]*\]);", _TBc33, re.S)
chk(_mir33 is not None and _ast33.literal_eval(_mir33.group(1)) == list(_CF33.BEAST_RANKS)
    and "typeof beast.rank_idx === \"number\" ? beast.rank_idx" in _corpos33["BeastExpeditionModal"],
    "nomes: o espelho dos postos segue o `config.BEAST_RANKS` (tinha Mitico ANTES de Lendario) e o "
    "indice do SERVIDOR le'-se primeiro")

# ── 33.3 O ECRA ──────────────────────────────────────────────────────────────
_BT33 = _fn25(_TBc33, "    function BeastsTab(")
_BO33 = _corpos33["BestasOnda"]
_BL33 = _corpos33["BestaLinha"]
chk(_BT33.count("const onda = obraOn();") == 1 and "ondaCultOn()" not in _BT33
    and "(onda\n            ? <BestasOnda data={data} onChanged={refreshAll} falhou={!!error} />\n"
        "            : <BeastsListPanel data={data} onChanged={refreshAll} />" in _BT33,
    "ecra: UM leitor da chave-mestra na aba; sem ela, a `BeastsListPanel` de sempre")
_hooks33 = [_m.start() for _m in re.finditer(r"\buse(State|Effect|Ref)\(", _BO33)]
_ret33 = _BO33.find("if (!owned.length) {")
chk(len(_hooks33) >= 10 and 0 < max(_hooks33) < _ret33,
    "ecra: todos os estados nascem ANTES do 1.o `return` (React #310)")
_ag33 = _BO33.split("async function agir(acao) {")[1].split("\n      }\n")[0] if "async function agir(acao) {" in _BO33 else ""
_iok33 = _ag33.find("if (res && res.ok === true) {")
_ielse33 = _ag33.find("} else {")
# (o `setAcende(null)` do temporizador apaga; so' o `setAcende({` ACENDE)
chk(_BO33.count("setAcende({") == 1 and _BO33.count("setOv({") == 1
    and 0 <= _iok33 < _ag33.find("setAcende({") < _ielse33
    and 0 <= _iok33 < _ag33.find("setOv({") < _ielse33
    and "res.besta_ganho" in _ag33,
    "ecra: so' uma resposta `ok: true` com `besta_ganho` acende e poe o 'depois' — nunca o toque, "
    "num sitio so'")
_ac33 = re.findall(r"acende=\{([^}]*)\}", _BO33)
chk(sorted(_ac33) == sorted(['eixos.indexOf("posto") >= 0 && i === idx', 'eixos.indexOf("nivel") >= 0']),
    "ecra: so' o posto e o nivel acendem (%r) — companheira, expedicao e pedras nunca" % _ac33)
chk(_BO33.count("<MarcaOnda") >= 3 and "corpo-nucleo-acende" not in _BO33 and "corpo-halo-acende" not in _BO33,
    "ecra: a marca e' a do dono (`MarcaOnda`) — o selo nao escreve a gramatica a' mao")
chk("const ranks = Array.isArray(data.ranks) ? data.ranks : [];" in _BO33 and "ranks.map(" in _BO33
    and "nPostos > 0 ?" in _BO33 and not re.search(r"\|\|\s*(7|100)\b", _BO33),
    "ecra: os denominadores vem do SERVIDOR (a escada `ranks`, o `max_level`) — sem eles, nenhuma "
    "inscricao; nunca um `|| 7`")
chk("!noTecto && precisa > 0 &&" in _BO33 and '"beasts_onda_limite"' in _BO33,
    "ecra: no tecto nao ha' fio — \"Limite atual\" (162 bestas do `main` tem XP a sobrar no 100)")
chk(re.search(r"const podeTreinar = fresco &&", _BO33) and re.search(r"const podeEvoluir = fresco &&", _BO33),
    "ecra: enquanto os dados nao apanham a confirmacao, a proxima accao nao se oferece (o preco "
    "do treino seguinte ainda e' o de antes)")
chk("owned.length > 1 ?" in _BO33,
    "ecra: a lista so' existe quando ha' OUTRAS bestas (p50 = uma: 148 dos 242)")
chk("aria-pressed={sel}" in _BL33 and "aria-label={[b.name, postoDaBesta(b.rank), nv, estado]" in _BL33,
    "ecra: cada linha e' um botao que diz TUDO no aria-label e marca a seleccao")
_EMO33 = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿←-⇿⭐〰〽]")
chk(not _EMO33.findall(_BO33 + _BL33),
    "ecra: o corpo novo nasce sem emoji nem seta tipografica (a catraca do §15)")
_k33 = sorted(set(re.findall(r't\("(beasts_onda_[a-z0-9_]+)"', _TBc33)))
chk(len(_k33) >= 35 and all(_k in _MI33[_lg] for _k in _k33 for _lg in ("pt", "en", "es")),
    "ecra/i18n: as %d chaves da onda das bestas existem nas 3 linguas (falta %r)"
    % (len(_k33), [_k for _k in _k33 if _k not in _MI33["es"]][:4]))
_rb33 = _fn25(_TBc33, "    function reciboDaBesta(")
chk("g && g.antes" in _rb33 and "g && g.depois" in _rb33 and "limiar" not in _rb33 and "* 100" not in _rb33,
    "ecra: o recibo sai do `besta_ganho` (antes->depois da MESMA transaccao) — nunca de uma conta "
    "feita no cliente")

# ── 33.4 O ARNES corre as rotas reais ────────────────────────────────────────
_AR33 = rd("scripts/_dev_serve_miniapp.py")
_ra33 = re.search(r"_ROTAS_BESTAS = \{(.*?)\}", _AR33, re.S)
chk(_ra33 is not None and set(re.findall(r'"(beasts/[a-z_]+)"', _ra33.group(1))) == set(_rotas33)
    and "getattr(_Wb, fn_nome)" in _AR33 and "BEASTS = {" not in _AR33
    and '"evolution": {"can_evolve": True' not in _AR33,
    "arnes: as %d rotas das bestas correm o HANDLER REAL (o mock a' mao dava a todas a mesma "
    "evolucao)" % len(_rotas33))

# ══════════════════════════════════════════════════════════════════════════
# §34 — 宗 A SEITA: o selo do posto na casa, o ganho e as portas (4.1, 2026-10-05)
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 O QUE SE MEDIU ANTES (Lei 0 passo 1 — `tools/db_readonly_seita_1005.py`; e
# porquê a Seita e não a Facção que o prompt pedia — `tools/db_readonly_faccao_1005.py`:
# a Facção é LEGADO no próprio jogo e no Beta UM jogador fez as 99 recolhas):
#   · `main` 21 membros (12 activos em 30 dias) · 18 herdeiros (o topo), todos com
#     contribuição a sobrar · 3 com próximo posto (falta p50 = 140) · 3 herdeiros
#     ABAIXO do portão de reino (renasceram — o motor nunca rebaixa);
#   · o Salão mostrava a contribuição ABREVIADA ("1.4K") numa barra, o posto num
#     badge e o tributo "1.0K → +40"; o arnês nem tinha o Salão (catch-all: "não
#     és membro").
#
#   34.1 o DONO — a escada do motor, o retrato (o posto GRAVADO e a contribuição
#        da escada; o mérito nem entra), o ganho (só o posto acende)
#   34.2 as PORTAS — os mutadores que promovem são DESCOBERTOS no motor, as rotas
#        que os alcançam nas ROTAS; todas leem o "antes" só com a onda e devolvem
#        o ganho — e CORREM numa sessão que compila no dialecto do Postgres
#   34.3 o ECRÃ — o selo, só o confirmado acende, o mérito sem luz, OFF = o de hoje
#   34.4 o ARNÊS corre as rotas reais
print("\n=== 34. 宗 A SEITA: o selo do posto, o ganho e as portas ===")

import collections as _col34
import core.seita as _SE34
import core.world_sects_engine as _WSE34
from database.seeds.quests_seeds import QUEST_SEEDS as _QS34
from database.seeds.combat_seeds import TECHNIQUES as _TS34

# ── 34.1 O DONO ──────────────────────────────────────────────────────────────
_esc34 = _SE34.escada()
chk([_e["rank"] for _e in _esc34] == list(_WSE34.SECT_RANKS) and len(_esc34) == 5
    and [_e["threshold"] for _e in _esc34] == [_WSE34.SECT_RANK_THRESHOLDS[_r] for _r in _WSE34.SECT_RANKS]
    and [_e["realm_gate"] for _e in _esc34] == [_WSE34.SECT_RANK_REALM_GATES[_r] for _r in _WSE34.SECT_RANKS]
    and [_e["rank_key"] for _e in _esc34] == ["wsect_rank_" + _r for _r in _WSE34.SECT_RANKS],
    "seita/dono: a escada das insígnias é a do MOTOR (5 postos, o limiar e o portão de reino de "
    "cada um) — nunca uma cópia")
chk(_SE34.retrato("azure_cloud", "elder", 1360, 900, None)
    == {"rank": "elder", "rank_key": "wsect_rank_elder", "rank_index": 3, "contribution": 1360}
    and _SE34.retrato(None, "elder", 1, 1, None) is None,
    "seita/dono: o retrato é o posto GRAVADO e a contribuição da ESCADA (a ganha) — o mérito "
    "(900) nem entra; sem casa, nada a retratar")
chk(_SE34.retrato("azure_cloud", "heir", 0, 400, None)["contribution"] == 400
    and _SE34.retrato("azure_cloud", "heir", 0, 400, {"doou": 1})["contribution"] == 0
    and _SE34.retrato("azure_cloud", "heir", 5, 1, None)["rank_index"] == 4,
    "seita/dono: a contribuição é a de `ladder_contribution` (o compat do saldo só para quem "
    "nunca doou pergaminho) e o posto é o gravado (um herdeiro renascido continua herdeiro)")


def _r34(idx, c):
    return {"rank": "x", "rank_key": "k", "rank_index": idx, "contribution": c}


chk(_SE34.ganho(_r34(3, 1360), _r34(3, 1390))["acende"] == []
    and _SE34.ganho(_r34(3, 1390), _r34(4, 1590))["acende"] == ["posto"]
    and _SE34.ganho(_r34(0, 30), _r34(2, 230))["acende"] == ["posto"]
    and _SE34.ganho(_r34(3, 1360), _r34(3, 1360)) is None
    and _SE34.ganho(None, _r34(3, 1)) is None,
    "seita/ganho: a contribuição sozinha só traça; o posto confirmado acende (dois de uma vez num "
    "salto); sem mudança — a doação de pergaminho, uma missão sem contribuição — sem ganho")
chk(tuple(_SE34.EIXOS_QUE_ACENDEM) == ("posto",),
    "seita/ganho: UMA conquista — o mérito, as pedras, as regalias e a força da casa nunca acendem")
chk(_SE34.no_payload({"acende": []}, lambda _k: False) == {}
    and _SE34.no_payload({"acende": []}, lambda _k: _k == "a_obra") == {"seita_ganho": {"acende": []}}
    and _SE34.no_payload(None, lambda _k: True) == {}
    and _SE34.escada_no_payload(lambda _k: False) == {}
    and list(_SE34.escada_no_payload(lambda _k: _k == "cultivador_jogavel")) == ["escada"],
    "seita/ganho: `seita_ganho` e a `escada` só viajam com a chave-mestra — sem ela, o payload de HOJE")

# ── 34.2 AS PORTAS ───────────────────────────────────────────────────────────
# (a) os mutadores que PROMOVEM, descobertos no motor: quem chama
#     `_apply_promotion` (a única função que sobe `sect_rank`)
_mut34 = set()
for _n34 in _ast33.walk(_ast33.parse(rd("core/world_sects_engine.py"))):
    if isinstance(_n34, (_ast33.FunctionDef, _ast33.AsyncFunctionDef)) and _n34.name != "_apply_promotion":
        if any(isinstance(_c, _ast33.Call) and isinstance(_c.func, _ast33.Name)
               and _c.func.id == "_apply_promotion" for _c in _ast33.walk(_n34)):
            _mut34.add(_n34.name)
chk(_mut34 == {"award_sect_contribution", "tribute_stones", "recompute_player_rank"},
    "seita/portas: ANTI-GUARDA — os mutadores que promovem, lidos no MOTOR (%r)" % sorted(_mut34))
# quem, fora do motor, credita contribuição: a missão e a escolha creditam a
# ESCADA (por `claim_quest_reward`); a doação de pergaminho só o SALDO
_award34 = {}
for _f34 in sorted(os.listdir(os.path.join(ROOT, "core"))):
    if not _f34.endswith(".py") or _f34 == "world_sects_engine.py":
        continue
    for _n34 in _ast33.walk(_ast33.parse(rd("core/" + _f34))):
        if isinstance(_n34, _ast33.Call) and getattr(_n34.func, "id", getattr(_n34.func, "attr", None)) == "award_sect_contribution":
            _so_saldo = any(_k.arg == "credit_earned" and isinstance(_k.value, _ast33.Constant)
                            and _k.value.value is False for _k in _n34.keywords)
            _award34["core/" + _f34] = "saldo" if _so_saldo else "escada"
chk(_award34 == {"core/quest_engine.py": "escada", "core/quest_choice_engine.py": "escada",
                 "core/scroll_economy_engine.py": "saldo"},
    "seita/portas: ANTI-GUARDA — quem credita contribuição: a missão e a escolha a escada, a "
    "doação só o saldo (%r)" % _award34)
# (b) as ROTAS que chamam um mutador (ou a recolha da missão, que chega a ele)
_alvo34 = _mut34 | {"claim_quest_reward"}
_rotas34 = dict(re.findall(r'add_post\("/api/miniapp/([a-z_/]+)", (api_[a-z_]+)\)', _WS33))
_portas34, _sem34 = {}, []
for _rota34, _fn34 in sorted(_rotas34.items()):
    _no34 = _fws33.get(_fn34)
    if _no34 is None:
        continue
    _ch34 = sorted({_c.func.id for _c in _ast33.walk(_no34) if isinstance(_c, _ast33.Call)
                    and isinstance(_c.func, _ast33.Name) and _c.func.id in _alvo34})
    if not _ch34:
        continue
    _portas34[_rota34] = _ch34
    _src34 = _ast33.unparse(_no34)
    _ia34 = _src34.find("_seita.ler_antes(session, user_id) if _onda_on() else None")
    _im34 = min([_src34.find(_x + "(") for _x in _ch34 if _src34.find(_x + "(") >= 0] or [-1])
    if not (0 <= _ia34 < _im34 and "_seita.ganho_da_acao(session, user_id, _antes)" in _src34
            and "_seita.no_payload(_g)" in _src34):
        _sem34.append(_rota34)
chk(set(_portas34) == {"world/sect_hall", "world/sect_tribute", "quests/claim"},
    "seita/portas: ANTI-GUARDA — as rotas que mudam o posto, descobertas nas ROTAS (%r)" % sorted(_portas34))
chk(not _sem34,
    "seita/portas: TODA porta que muda o posto lê o 'antes' (só com a onda) ANTES do motor e "
    "devolve o ganho (%r)" % _sem34)
_cq34 = _ast33.unparse(_fws33["api_quests_claim"])
chk(_cq34.count("_seita.ganho_da_acao(session, user_id, _antes)") == 2
    and _cq34.count("_seita.no_payload(_g)") == 2,
    "seita/portas: a recolha da missão devolve o ganho nos DOIS caminhos (a recompensa e a escolha)")
_sh34 = _ast33.unparse(_fws33["api_world_sect_hall"])
chk("_seita.escada_no_payload()" in _sh34,
    "seita/portas: o Salão manda a escada (o denominador das insígnias) — só com a onda")

# (c) as portas CORREM — numa sessão que compila no dialecto do Postgres
_QCAT34 = {int(_q["id"]): _NS33(**dict({"choices": None, "sect_id": None, "is_active": True,
                                         "emoji": "🏯"}, **_q))
           for _q in _QS34 if _q.get("type") == "sect"}
_TCAT34 = {int(_t["id"]): _NS33(**dict({"sect_key": None, "library_tier": None,
                                         "library_cp_cost": None, "tech_type": "combat"}, **_t))
           for _t in _TS34}


class _Sess34:
    def __init__(self, j, missoes):
        self.j, self.missoes, self.sql = j, missoes, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def rollback(self):
        return None

    def add(self, o):
        return None

    async def get(self, ent, ident):
        return None

    def begin_nested(self):
        class _Nada34:
            async def __aenter__(s2):
                return s2

            async def __aexit__(s2, *a):
                return False
        return _Nada34()

    async def execute(self, stmt):
        _txt = str(stmt.compile(dialect=_pg33.dialect()))
        try:
            _lit = str(stmt.compile(dialect=_pg33.dialect(), compile_kwargs={"literal_binds": True}))
        except Exception:
            _lit = _txt
        self.sql.append(_txt)
        _cd = stmt.column_descriptions
        _nomes = [getattr(_c.get("entity"), "__name__", "") for _c in _cd]
        _inteira = len(_cd) == 1 and _cd[0].get("expr") is _cd[0].get("entity")
        if _nomes[:1] == ["Player"]:
            if _inteira:
                return _Res33([self.j])
            _campos = [_c["name"] for _c in _cd]
            _l = _col34.namedtuple("L34", _campos)(*[getattr(self.j, _c, None) for _c in _campos])
            return _Res33([_l], first=_l)
        if _nomes[:1] == ["WorldSect"]:
            return _Res33(scalar=1000)
        if _nomes[:2] == ["PlayerQuest", "QuestCatalog"]:
            _rows = list(self.missoes)
            _m = re.search(r"player_quests\.quest_id = (\d+)", _lit)
            if _m:
                _rows = [(_p, _q) for _p, _q in _rows if _p.quest_id == int(_m.group(1))]
            if "player_quests.claimed = false" in _lit:
                _rows = [(_p, _q) for _p, _q in _rows if not _p.claimed]
            if "player_quests.is_completed = true" in _lit:
                _rows = [(_p, _q) for _p, _q in _rows if _p.is_completed]
            return _Res33(_rows, first=(_rows[0] if _rows else None))
        if _nomes[:1] == ["PlayerQuest"]:
            return _Res33([_p.quest_id for _p, _ in self.missoes]) if not _inteira else _Res33([_p for _p, _ in self.missoes])
        if _nomes[:1] == ["QuestCatalog"]:
            return _Res33([_q for _q in _QCAT34.values() if _q.sect_id in (None, self.j.sect_id)])
        if _nomes[:1] == ["TechniqueCatalog"]:
            if "JOIN player_techniques" in _lit:
                return _Res33([])
            _mi = re.search(r"techniques_catalog\.id IN \(([^)]*)\)", _lit)
            _rows = sorted(_TCAT34.values(), key=lambda _t: _t.id)
            if _mi:
                _ids = {int(_v) for _v in re.findall(r"\d+", _mi.group(1))}
                _rows = [_t for _t in _rows if _t.id in _ids]
            return _Res33(_rows)
        if _nomes[:1] in (["PlayerTechnique"], ["PlayerSectTechnique"]):
            return _Res33([])
        if "count(" in _lit.lower() or "sum(" in _lit.lower():
            return _Res33(scalar=0)
        return _Res33()


def _j34(rank="elder", ganha=1360, saldo=1360, reino=7, pedras=50000):
    return _NS33(telegram_id=77, language="pt", realm=reino, karma=0, sect_id="azure_cloud",
                 sect_rank=rank, sect_contribution=saldo, sect_contribution_earned=ganha,
                 scroll_econ=None, sect_master_name="X", sect_joined_at=None, spirit_stones=pedras,
                 unlocked_titles=[], core_quality="x")


def _missao34(qid=600, feita=True):
    _q = _QCAT34[qid]
    return (_NS33(player_id=77, quest_id=qid, progress=int(_q.objective_value), is_completed=feita,
                  claimed=False, chosen_choice_id=None, reset_at=None), _q)


def _corre34(fn, payload, onda, j, missoes=None):
    _s = _Sess34(j, list(missoes or []))
    _orig = (_W33.get_session_factory, _PO33.onda_on)
    _W33.get_session_factory = lambda: (lambda: _s)
    _PO33.onda_on = lambda *a, **k: onda
    try:
        _resp = _aio33.run(getattr(_W33, fn)({"user_id": 77, "payload": payload}))
        return _json33.loads(_resp.text), _s
    except Exception as _ex:
        return "%s: %s" % (type(_ex).__name__, str(_ex)[:160]), _s
    finally:
        _W33.get_session_factory, _PO33.onda_on = _orig


_ANTES34 = ("SELECT players.sect_id, players.sect_rank, players.sect_contribution_earned, "
            "players.sect_contribution, players.scroll_econ")
# o tributo que CRUZA o limiar (Ancião 1.360 + 200 >= 1.500, reino 7)
_jj34 = _j34()
_c34, _s34 = _corre34("api_world_sect_tribute", {"stones": 5000}, True, _jj34)
_g34 = _c34.get("seita_ganho") if isinstance(_c34, dict) else None
chk(isinstance(_g34, dict) and _g34["antes"]["rank_index"] == 3 and _g34["depois"]["rank_index"] == 4
    and _g34["antes"]["contribution"] == 1360 and _g34["depois"]["contribution"] == 1560
    and _g34["acende"] == ["posto"] and _jj34.sect_rank == "heir" and _jj34.spirit_stones == 45000,
    "seita/rota: o tributo CORRE e devolve `seita_ganho` Ancião -> Herdeiro com o posto aceso (%r)" % (_c34,))
_ia34 = next((_i for _i, _q in enumerate(_s34.sql) if _q.startswith(_ANTES34)), -1)
_ie34 = next((_i for _i, _q in enumerate(_s34.sql) if _q.startswith("SELECT players.id, players.telegram_id")
              and "FOR UPDATE" in _q), -1)
chk(0 <= _ia34 < _ie34 and "FOR UPDATE" in _s34.sql[_ia34],
    "seita/rota: o 'antes' lê COLUNAS (nunca a entidade) e TRANCADO, ANTES do motor")
_jj34 = _j34()
_c34, _s34 = _corre34("api_world_sect_tribute", {"stones": 5000}, False, _jj34)
chk(isinstance(_c34, dict)
    and list(_c34) == ["ok", "points", "stones_spent", "contribution", "spirit_stones", "promotion"]
    and not any(_q.startswith(_ANTES34) for _q in _s34.sql),
    "seita/rota: com a onda OFF a resposta do tributo é a de HOJE e não há leitura nem trinco a mais (%r)" % (_c34,))
_jj34 = _j34(pedras=10)
_c34, _ = _corre34("api_world_sect_tribute", {"stones": 10}, True, _jj34)
chk(isinstance(_c34, dict) and _c34.get("ok") is False and "seita_ganho" not in _c34
    and _jj34.sect_contribution_earned == 1360,
    "seita/rota: o tributo recusado nunca leva ganho (nada acende sem confirmação)")
# o Salão que PROMOVE ao abrir (Ancião com 1.600 e reino 7: o portão caiu)
_jj34 = _j34(ganha=1600, saldo=1600)
_c34, _ = _corre34("api_world_sect_hall", {}, True, _jj34)
_g34 = _c34.get("seita_ganho") if isinstance(_c34, dict) else None
chk(isinstance(_g34, dict) and _g34["acende"] == ["posto"] and _g34["depois"]["rank"] == "heir"
    and _g34["antes"]["contribution"] == _g34["depois"]["contribution"] == 1600
    and len(_c34.get("escada") or []) == 5,
    "seita/rota: o Salão que promove ao abrir devolve o posto aceso e a escada (%r)"
    % (_c34 if not isinstance(_g34, dict) else _g34["acende"],))
_jj34 = _j34()
_c34, _ = _corre34("api_world_sect_hall", {}, True, _jj34)
chk(isinstance(_c34, dict) and "seita_ganho" not in _c34 and len(_c34.get("escada") or []) == 5
    and _c34.get("contribution") == 1360,
    "seita/rota: o Salão sem promoção manda a escada e NENHUM ganho (abrir não é conquista)")
_jj34 = _j34(ganha=1600, saldo=1600)
_c34, _ = _corre34("api_world_sect_hall", {}, False, _jj34)
chk(isinstance(_c34, dict) and "escada" not in _c34 and "seita_ganho" not in _c34
    and _c34.get("rank") == "heir",
    "seita/rota: com a onda OFF o Salão é o de HOJE (promove como sempre, sem escada nem ganho)")
# a recolha de uma missão da casa (a 600: +30 de contribuição, sem cruzar)
_jj34 = _j34()
_c34, _ = _corre34("api_quests_claim", {"quest_id": 600}, True, _jj34, [_missao34(600)])
_g34 = _c34.get("seita_ganho") if isinstance(_c34, dict) else None
chk(isinstance(_g34, dict) and _g34["acende"] == [] and _g34["antes"]["contribution"] == 1360
    and _g34["depois"]["contribution"] == 1390
    and _c34.get("rewards") == {"spirit_stones": 300, "sect_contribution": 30},
    "seita/rota: a missão da casa CORRE e devolve a contribuição antes->depois (traço, sem luz) (%r)" % (_c34,))
_jj34 = _j34()
_c34, _ = _corre34("api_quests_claim", {"quest_id": 600}, False, _jj34, [_missao34(600)])
chk(_c34 == {"ok": True, "rewards": {"spirit_stones": 300, "sect_contribution": 30}},
    "seita/rota: com a onda OFF a recolha da missão é a de HOJE, chave a chave (%r)" % (_c34,))

# ── 34.3 O ECRÃ ──────────────────────────────────────────────────────────────
_SH34 = _fn25(_TBc33, "    function SectHallModal(")
_SS34 = _fn25(_TBc33, "    function SeitaSelo(")
_RS34 = _fn25(_TBc33, "    function reciboDaSeita(")
chk(len(_SH34) > 4000 and len(_SS34) > 1500 and len(_RS34) > 200,
    "ecrã: ANTI-GUARDA — o Salão, o selo e o recibo foram fatiados (%d · %d · %d)"
    % (len(_SH34), len(_SS34), len(_RS34)))
chk(_SH34.count("const onda = obraOn();") == 1 and "ondaCultOn()" not in _SH34,
    "ecrã: UM leitor da chave-mestra no Salão")
_hk34 = [_m.start() for _m in re.finditer(r"\buse(State|Effect|Ref)\(", _SH34)]
_r1_34 = _SH34.find("if (choiceQuest) {")
chk(len(_hk34) >= 15 and 0 < max(_hk34) < _r1_34,
    "ecrã: todos os estados do Salão nascem ANTES do 1.º `return` (React #310)")
_ag34 = _SH34.split("function aplicarGanhoSeita(g, res, origem, dadosVelhos) {")[1].split("\n      }\n")[0] \
    if "function aplicarGanhoSeita(" in _SH34 else ""
chk(_SH34.count("setSeitaAcende({") == 1 and _SH34.count("setSeitaOv({") == 1
    and "setSeitaAcende({" in _ag34 and "setSeitaOv({" in _ag34
    and '(g.acende || []).indexOf("posto") >= 0' in _ag34 and "if (!onda || !g) return;" in _ag34,
    "ecrã: só o `seita_ganho` do servidor acende e põe o 'depois' — num sítio só, com a onda")
_ap34 = re.findall(r"aplicarGanhoSeita\(([a-z.]+)\.seita_ganho", _SH34)
_to34 = _SH34.split("async function tributoOnda(amt) {")[1].split("\n      }\n")[0] if "async function tributoOnda(" in _SH34 else ""
chk(sorted(set(_ap34)) == ["data", "res"] and len(_ap34) == 4
    and 0 <= _to34.find("if (res && res.ok) {") < _to34.find("aplicarGanhoSeita(res.seita_ganho"),
    "ecrã: o ganho chega das QUATRO portas (o tributo depois do `ok`, a missão, a escolha e o "
    "Salão que promove ao abrir) e só delas (%r)" % _ap34)
_ac34 = re.findall(r"acende=\{([^}]*)\}", _SS34)
chk(_ac34 == ["!!acende && i === idx"],
    "ecrã: só a insígnia do posto acende (%r) — o mérito, o tributo e as regalias nunca" % _ac34)
chk(_SS34.count("<MarcaOnda") == 1 and "corpo-nucleo-acende" not in _SS34 and "corpo-halo-acende" not in _SS34,
    "ecrã: a marca é a do dono (`MarcaOnda`) — o selo não escreve a gramática à mão")
chk("const escada = Array.isArray(data.escada) ? data.escada : [];" in _SS34 and "escada.map(" in _SS34
    and "nPostos > 0 &&" in _SS34 and not re.search(r"\|\|\s*5\b", _SS34),
    "ecrã: os denominadores vêm do SERVIDOR (a escada) — sem ela, nenhuma inscrição; nunca um `|| 5`")
_me34 = _SS34.split('t("seita_onda_merito"')[0].rsplit("<div", 1)[-1] if 't("seita_onda_merito"' in _SS34 else ""
chk(_me34 and "acende" not in _me34 and "MarcaOnda" not in _me34 and "gold" not in _me34,
    "ecrã: o MÉRITO (o saldo que se gasta) é uma linha sem marca, sem luz, sem ouro")
chk("{!onda && <Badge variant=\"jade\">{safeT(data.rank_key)}</Badge>}" in _SH34
    and "{onda ? (\n                <SeitaSelo " in _SH34 and "{!onda && (\n              <Card style={{ padding:\"12px 14px\" }}>" in _SH34,
    "ecrã: sem a chave-mestra o Salão é o de hoje — o badge, o cartão da contribuição e o do tributo")
chk("fmtNum(" not in _SS34 and _SS34.count("fmtFull(") >= 6,
    "ecrã: o selo escreve os números INTEIROS (`fmtFull`) — o Salão de hoje abreviava (\"1.4K\")")
_EMO34 = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿←-⇿⭐〰〽]")
chk(not _EMO34.findall(_SS34),
    "ecrã: o selo nasce sem emoji nem seta tipográfica (a catraca do §15)")
_k34 = sorted(set(re.findall(r't\("(seita_onda_[a-z0-9_]+)"', _TBc33)))
chk(len(_k34) >= 18 and all(_k in _MI33[_lg] for _k in _k34 for _lg in ("pt", "en", "es")),
    "ecrã/i18n: as %d chaves do selo existem nas 3 línguas (falta %r)"
    % (len(_k34), [_k for _k in _k34 if _k not in _MI33["es"]][:4]))
chk("g && g.antes" in _RS34 and "g && g.depois" in _RS34 and "threshold" not in _RS34,
    "ecrã: o recibo sai do `seita_ganho` (antes->depois da MESMA transacção) — nunca de uma conta "
    "com a escada no cliente")
_qr34 = _fn25(_TBc33, "    function QuestRow(")
chk("onClaimed && onClaimed(res);" in _qr34,
    "ecrã: a linha da missão entrega a resposta a quem pediu (o Salão lê o ganho dela)")

# ── 34.4 O ARNÊS corre as rotas reais ────────────────────────────────────────
_ra34 = re.search(r"_ROTAS_SEITA = \{(.*?)\}", _AR33, re.S)
chk(_ra34 is not None and set(_portas34) <= set(re.findall(r'"([a-z_/]+)":', _ra34.group(1)))
    and "getattr(_Ws, fn_nome)" in _AR33 and "QUEST_SEEDS" in _AR33,
    "arnês: as portas da seita correm o HANDLER REAL, com as missões das SEMENTES (o Salão "
    "nunca tinha estado no arnês)")

# ══════════════════════════════════════════════════════════════════════════
# §35 — 幫 A GUILDA: a planta das seis instalações, o ganho e a porta (4.2, 2026-10-07)
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 O QUE SE MEDIU ANTES (Lei 0 passo 1 — `tools/db_readonly_guilda_1007.py`):
#   · a Guilda VIVE (o precedente da Facção não se aplica): `main` 9 guildas, 97
#     membros, 30 activos em 30 dias (de 36 jogadores activos no mundo), 7.644
#     melhorias (70 em 30 dias); Beta 4 guildas, 13 de 18 activos, 380 melhorias
#     em 30 dias;
#   · os níveis NÃO têm teto (até 856 no `main`) — sem denominador do servidor,
#     nenhuma inscrição "N de M";
#   · a aba de hoje SOMAVA as seis instalações num "Edifícios: 1.381" (o "nível
#     da guilda" fictício que a linha do Astra proíbe), abreviava o tesouro
#     ("18.9B") e repetia no cliente a fórmula do custo (dois donos);
#   · o motor (`upgrade_building`) não tranca a guilda — 30 pares de melhorias da
#     mesma guilda por pessoas diferentes a menos de 2 s no `main` (maio);
#   · a cadeia do efeito arredondava para BAIXO um float: "+14% CB" no Treino 3
#     (o motor aplica ×1,15) — 211 combinações em 0..1000;
#   · o arnês nem tinha a Guilda (catch-all: "criar ou entrar").
#
#   35.1 o DONO — a lista do motor, o número do efeito (UMA conta, exacta), a
#        planta, o ganho (só o nível acende)
#   35.2 a PORTA — os escritores do nível DESCOBERTOS no código, as rotas que os
#        alcançam nas ROTAS; o "antes" só com a onda, trancado ANTES de a guilda
#        ser carregada — e CORREM numa sessão que compila no dialecto do Postgres
#   35.3 o ECRÃ — a planta, só o confirmado acende, nada soma, OFF = o de hoje
#   35.4 o ARNÊS corre as rotas reais
print("\n=== 35. 幫 A GUILDA: a planta, o ganho e a porta ===")

import core.guilda as _GU35
import core.sect_engine as _SEN35

_INST35 = ("training", "herb_garden", "forge", "library", "defense", "spirit_vein")

# ── 35.1 O DONO ──────────────────────────────────────────────────────────────
chk(tuple(_SEN35.BUILDINGS) == _INST35 and _GU35.instalacoes() == _INST35,
    "guilda/dono: as seis instalações são as do MOTOR (`BUILDINGS`), pela ordem da planta")
_WSs35 = _ast33.unparse(_fws33["api_sect"])
_WSu35 = _ast33.unparse(_fws33["api_sect_upgrade"])
chk("for _k in _BUILDINGS" in _WSs35 and "building not in BUILDINGS" in _WSu35
    and '"training", "herb_garden"' not in _WSs35 + _WSu35,
    "guilda/dono: a aba e a melhoria lêem a lista do motor — nenhuma cópia das seis chaves nas rotas")
_exacto35 = {"training": lambda _l: 5 * min(_l, 20), "herb_garden": lambda _l: 10 * _l,
             "forge": lambda _l: 3 * _l, "library": lambda _l: _l,
             "defense": lambda _l: 5 * _l, "spirit_vein": lambda _l: 5 * _l}
_ruim35 = [(_k, _l) for _k in _INST35 for _l in range(0, 1001)
           if _SEN35.building_effect_value(_k, _l) != _exacto35[_k](_l)
           or int(re.sub(r"[^0-9]", "", _SEN35.format_building_effect(_k, _l))) != _SEN35.building_effect_value(_k, _l)]
chk(not _ruim35,
    "guilda/dono: o NÚMERO do efeito é UMA conta, exacta (o que o motor aplica: +15%% no Treino 3, "
    "nunca o '+14%%' do float) e a cadeia do chat escreve esse mesmo número (%r)" % (_ruim35[:4],))
chk("building_effect_value(building_key, level)" in rd("core/sect_engine.py")
    and "int(" not in "".join(_l for _l in rd("core/sect_engine.py").replace("\r\n", "\n")
                              .split("def format_building_effect(", 1)[1].split("\ndef ", 1)[0]
                              .split("\n") if not _l.strip().startswith(("#", '"""')) and "return f" in _l),
    "guilda/dono: `format_building_effect` não faz conta sua — formata o número do dono")
# ⚠️ a guarda de VALOR acima fica verde com uma CÓPIA da fórmula (dá os mesmos
# números): esta afirma o que o dono É — pede ao motor, não conta
_GUs35 = "\n".join(_l for _l in rd("core/guilda.py").split("\n") if not _l.strip().startswith("#"))
_GUc35 = re.sub(r'""".*?"""', "", _GUs35, flags=re.S)
chk("calculate_upgrade_cost(lv)" in _GUc35 and _GUc35.count("building_effect_value(chave, lv)") == 2
    and not re.search(r"\*\*\s*2|1000\s*\*|\*\s*0\.0[35]|min\(\s*lv", _GUc35),
    "guilda/dono: a planta e o retrato PEDEM o custo e o efeito ao motor — nenhuma fórmula em `core/guilda.py`")
_sect35 = _NS33(training_lvl=255, herb_garden_lvl=240, forge_lvl=300, library_lvl=239,
                defense_lvl=856, spirit_vein_lvl=720, spirit_stones=18893071686)
_pl35 = _GU35.planta(_sect35)
chk([_i["key"] for _i in _pl35] == list(_INST35)
    and _pl35[0] == {"key": "training", "level": 255, "effect_n": 100, "next_cost": 65536000}
    and all(_i["next_cost"] == _SEN35.calculate_upgrade_cost(_i["level"])
            and _i["effect_n"] == _SEN35.building_effect_value(_i["key"], _i["level"]) for _i in _pl35),
    "guilda/dono: a planta é o nível GRAVADO, o número do efeito e o custo do próximo — tudo do motor")


def _rt35(lv, t):
    return {"key": "forge", "level": lv, "effect_n": 3 * lv, "next_cost": 1, "treasury": t}


chk(_GU35.ganho(_rt35(300, 1000), _rt35(301, 10))["acende"] == ["nivel"]
    and _GU35.ganho(_rt35(300, 1000), _rt35(300, 1000)) is None
    and _GU35.ganho(_rt35(300, 1000), _rt35(300, 900))["acende"] == []
    and _GU35.ganho(None, _rt35(1, 1)) is None,
    "guilda/ganho: o nível confirmado acende; o tesouro sozinho só se conta; sem mudança, sem ganho")
chk(tuple(_GU35.EIXOS_QUE_ACENDEM) == ("nivel",),
    "guilda/ganho: UMA conquista — o tesouro, a contribuição e os membros nunca acendem")
chk(_GU35.no_payload({"acende": []}, lambda _k: False) == {}
    and _GU35.no_payload({"acende": []}, lambda _k: _k == "a_obra") == {"guilda_ganho": {"acende": []}}
    and _GU35.no_payload(None, lambda _k: True) == {}
    and _GU35.planta_no_payload(_sect35, lambda _k: False) == {}
    and list(_GU35.planta_no_payload(_sect35, lambda _k: _k == "cultivador_jogavel")) == ["planta"],
    "guilda/ganho: `guilda_ganho` e a `planta` só viajam com a chave-mestra — sem ela, o payload de HOJE")

# ── 35.2 A PORTA ─────────────────────────────────────────────────────────────
# (a) quem ESCREVE o nível de uma instalação, descoberto no código: uma escrita
#     a `<x>_lvl` (atribuição, `+=` ou `setattr(…, "…_lvl", …)`) em core/ e handlers/
_esc35 = set()
for _d35 in ("core", "handlers"):
    for _f35 in sorted(os.listdir(os.path.join(ROOT, _d35))):
        if not _f35.endswith(".py"):
            continue
        for _fn35 in _ast33.walk(_ast33.parse(rd(_d35 + "/" + _f35))):
            if not isinstance(_fn35, (_ast33.FunctionDef, _ast33.AsyncFunctionDef)):
                continue
            for _n35 in _ast33.walk(_fn35):
                _alvos35 = []
                if isinstance(_n35, (_ast33.Assign, _ast33.AugAssign)):
                    _alvos35 = _n35.targets if isinstance(_n35, _ast33.Assign) else [_n35.target]
                if any(isinstance(_t, _ast33.Attribute) and _t.attr in {_k + "_lvl" for _k in _INST35}
                       for _t in _alvos35):
                    _esc35.add(_d35 + "/" + _f35 + ":" + _fn35.name)
                if (isinstance(_n35, _ast33.Call) and getattr(_n35.func, "id", None) == "setattr"
                        and len(_n35.args) >= 2 and "_lvl" in _ast33.unparse(_n35.args[1])):
                    _esc35.add(_d35 + "/" + _f35 + ":" + _fn35.name)
chk(_esc35 == {"core/sect_engine.py:upgrade_building"},
    "guilda/porta: ANTI-GUARDA — UM escritor do nível de uma instalação, lido no CÓDIGO (%r)" % sorted(_esc35))
# (b) quem CHAMA o escritor: as rotas do mini-app (nas ROTAS) e o chat
_rotas35 = dict(re.findall(r'add_post\("/api/miniapp/([a-z_/]+)", (api_[a-z_]+)\)', _WS33))
_portas35 = sorted(_r for _r, _fn in _rotas35.items() if _fn in _fws33 and any(
    isinstance(_c, _ast33.Call) and getattr(_c.func, "id", None) == "upgrade_building"
    for _c in _ast33.walk(_fws33[_fn])))
chk(_portas35 == ["sect/upgrade"],
    "guilda/porta: ANTI-GUARDA — as rotas do mini-app que mudam um nível, descobertas nas ROTAS (%r)" % _portas35)
_chat35 = sorted(_n.name for _n in _ast33.walk(_ast33.parse(rd("handlers/sect.py")))
                 if isinstance(_n, (_ast33.FunctionDef, _ast33.AsyncFunctionDef))
                 and any(isinstance(_c, _ast33.Call) and getattr(_c.func, "id", None) == "upgrade_building"
                         for _c in _ast33.walk(_n)))
chk(_chat35 == ["sect_upgrade_callback"],
    "guilda/porta: a outra porta é o CHAT (legado, só no `main`, sem luz) — contada (%r)" % _chat35)
_ia35 = _WSu35.find("_guilda.ler_antes(session, user_id, building) if _onda_on() else None")
_ii35 = _WSu35.find("get_player_sect_info(session, user_id)")
_im35 = _WSu35.find("upgrade_building(session,")
chk(0 <= _ia35 < _ii35 < _im35 and "_guilda.ganho_da_acao(session, user_id, building, _antes)" in _WSu35
    and "**_guilda.no_payload(_g)" in _WSu35,
    "guilda/porta: a melhoria lê o 'antes' (só com a onda) ANTES de carregar a guilda e do motor, "
    "e devolve o ganho")
chk("**_guilda.planta_no_payload(sect)" in _WSs35,
    "guilda/porta: a aba manda a planta (o nível, o efeito e o custo do motor) — só com a onda")


# (c) as portas CORREM — numa sessão que compila no dialecto do Postgres
class _Sess35:
    def __init__(self, guilda, eu, membros):
        self.g, self.eu, self.membros, self.sql = guilda, eu, membros, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def rollback(self):
        return None

    def add(self, o):
        return None

    async def execute(self, stmt):
        _txt = str(stmt.compile(dialect=_pg33.dialect()))
        self.sql.append(_txt)
        _cd = stmt.column_descriptions
        _nomes = [getattr(_c.get("entity"), "__name__", "") for _c in _cd]
        _inteira = len(_cd) == 1 and _cd[0].get("expr") is _cd[0].get("entity")
        if _nomes == ["SectMember", "Sect"]:
            return _Res33(first=((self.eu, self.g) if self.eu is not None else None))
        if _nomes[:1] == ["SectMember"] and _inteira:
            return _Res33([self.eu] if self.eu is not None else [])
        if _nomes[:1] == ["Sect"] and _inteira:
            return _Res33([self.g] if self.eu is not None else [])
        if _nomes and all(_n == "Sect" for _n in _nomes):
            _campos = [_c["name"] for _c in _cd]
            _l = _col34.namedtuple("L35", _campos)(*[getattr(self.g, _c, None) for _c in _campos])
            return _Res33([_l], first=_l)
        if _nomes[:2] == ["SectMember", "SectMember"]:
            return _Res33(list(self.membros))
        if _nomes[:1] == ["Player"]:
            _campos = [_c["name"] for _c in _cd]
            _vals = {"dao_name": "Eu", "username": None, "language": "pt"}
            _l = _col34.namedtuple("P35", _campos)(*[_vals.get(_c) for _c in _campos])
            return _Res33([_l[0]] if len(_campos) == 1 else [_l], first=_l)
        return _Res33()


def _g35(tesouro=18893071686, forja=300):
    return _NS33(id="7a1d0c3e-0000-4000-8000-000000000042", name="G", description=None, bulletin=None,
                 member_count=49, max_members=50, spirit_stones=tesouro, training_lvl=255,
                 herb_garden_lvl=240, forge_lvl=forja, library_lvl=239, defense_lvl=856,
                 spirit_vein_lvl=720, group_link=None, lineage_key=None, lineage_chosen_at=None)


def _corre35(fn, payload, onda, g, posto="elder"):
    _eu = _NS33(sect_id=g.id, player_id=77, rank=posto, contribution_points=3002845993) if posto else None
    _s = _Sess35(g, _eu, [(posto or "disciple", 1, "Eu", None, 7, 4, 1)])
    _orig = (_W33.get_session_factory, _PO33.onda_on)
    _W33.get_session_factory = lambda: (lambda: _s)
    _PO33.onda_on = lambda *a, **k: onda
    try:
        _resp = _aio33.run(getattr(_W33, fn)({"user_id": 77, "payload": payload}))
        return _json33.loads(_resp.text), _s
    except Exception as _ex:
        return "%s: %s" % (type(_ex).__name__, str(_ex)[:160]), _s
    finally:
        _W33.get_session_factory, _PO33.onda_on = _orig


_ANTES35 = "SELECT sects.forge_lvl, sects.spirit_stones \nFROM sects JOIN sect_members"
_gg35 = _g35()
_c35, _s35 = _corre35("api_sect_upgrade", {"building": "forge"}, True, _gg35)
_k35 = _c35.get("guilda_ganho") if isinstance(_c35, dict) else None
chk(isinstance(_k35, dict) and _k35["antes"]["level"] == 300 and _k35["depois"]["level"] == 301
    and _k35["antes"]["treasury"] == 18893071686 and _k35["depois"]["treasury"] == 18893071686 - 90601000
    and _k35["depois"]["next_cost"] == _SEN35.calculate_upgrade_cost(301)
    and _k35["acende"] == ["nivel"] and _gg35.forge_lvl == 301,
    "guilda/rota: a melhoria CORRE pelo motor e devolve `guilda_ganho` 300 -> 301 com o nível aceso (%r)"
    % (_c35 if not isinstance(_k35, dict) else _k35["acende"],))
_ia35 = next((_i for _i, _q in enumerate(_s35.sql) if _q.startswith(_ANTES35)), -1)
_ie35 = next((_i for _i, _q in enumerate(_s35.sql) if _q.startswith("SELECT sect_members.sect_id")
              and "JOIN sects" in _q), -1)
chk(0 <= _ia35 < _ie35 and "FOR UPDATE OF sects" in _s35.sql[_ia35],
    "guilda/rota: o 'antes' lê COLUNAS (nunca a entidade), TRANCADO, ANTES de a rota carregar a guilda")
_gg35 = _g35()
_c35, _s35 = _corre35("api_sect_upgrade", {"building": "forge"}, False, _gg35)
chk(_c35 == {"ok": True, "building": "forge", "new_level": 301, "cost": 90601000}
    and not any(_q.startswith(_ANTES35) for _q in _s35.sql),
    "guilda/rota: com a onda OFF a resposta da melhoria é a de HOJE e não há leitura nem trinco a mais (%r)"
    % (_c35,))
_c35, _ = _corre35("api_sect_upgrade", {"building": "forge"}, True, _g35(), posto="disciple")
chk(_c35 == {"ok": False, "reason": "rank_too_low"},
    "guilda/rota: o discípulo é recusado e nada acende (%r)" % (_c35,))
_gg35 = _g35(tesouro=10)
_c35, _ = _corre35("api_sect_upgrade", {"building": "forge"}, True, _gg35)
chk(isinstance(_c35, dict) and _c35.get("ok") is False and _c35.get("reason") == "insufficient_stones"
    and "guilda_ganho" not in _c35 and _gg35.forge_lvl == 300,
    "guilda/rota: o tesouro que não paga é recusado e nada acende (%r)" % (_c35,))
_c35, _ = _corre35("api_sect", {}, True, _g35())
_p35 = ((_c35.get("sect") or {}).get("planta") if isinstance(_c35, dict) else None) or []
chk([_i["key"] for _i in _p35] == list(_INST35) and _p35[4] == {"key": "defense", "level": 856,
                                                                  "effect_n": 4280, "next_cost": 734449000},
    "guilda/rota: a aba CORRE e manda a planta das seis com os números do motor (%r)" % (_c35 if not _p35 else ""))
_c35, _ = _corre35("api_sect", {}, False, _g35())
_s35k = list((_c35.get("sect") or {}).keys()) if isinstance(_c35, dict) else []
chk(_s35k == ["id", "name", "description", "bulletin", "member_count", "max_members", "spirit_stones",
              "buildings", "group_link", "your_rank", "your_contribution", "your_dao_name",
              "lineage_key", "lineage_chosen_at_ms", "lineage_meta_resolved"]
    and _c35["sect"]["buildings"] == {_k: {"level": getattr(_g35(), _k + "_lvl"),
                                           "effect": _SEN35.format_building_effect(_k, getattr(_g35(), _k + "_lvl"))}
                                      for _k in _INST35},
    "guilda/rota: com a onda OFF a aba é a de HOJE, chave a chave (e as instalações {level, effect}) (%r)"
    % (_s35k,))

# ── 35.3 O ECRÃ ──────────────────────────────────────────────────────────────
_ST35 = _fn25(_TBc33, "    function SectTab(")
_GP35 = _fn25(_TBc33, "    function GuildaPlanta(")
_RG35 = _fn25(_TBc33, "    function reciboDaGuilda(")
chk(len(_ST35) > 6000 and len(_GP35) > 3000 and len(_RG35) > 200,
    "ecrã: ANTI-GUARDA — a aba, a planta e o recibo foram fatiados (%d · %d · %d)"
    % (len(_ST35), len(_GP35), len(_RG35)))
chk(_ST35.count("const onda = obraOn();") == 1 and "ondaCultOn()" not in _ST35,
    "ecrã: UM leitor da chave-mestra na aba da Guilda")
_hk35 = [_m.start() for _m in re.finditer(r"\buse(State|Effect|Ref|Callback|Api)\(", _ST35)]
_r1_35 = _ST35.find("return <ListSkeleton")
chk(len(_hk35) >= 16 and 0 < max(_hk35) < _r1_35,
    "ecrã: todos os estados da aba nascem ANTES do 1.º `return` (React #310)")
chk("if (loading && !(onda && data && data.sect)) return <ListSkeleton rows={8} />;" in _ST35,
    "ecrã: com a onda a planta fica à vista na releitura; sem ela, o esqueleto de hoje")
_ag35 = _ST35.split("function aplicarGanhoGuilda(g, dadosVelhos) {")[1].split("\n      }\n")[0] \
    if "function aplicarGanhoGuilda(" in _ST35 else ""
chk(_ST35.count("setGuildaAcende({") == 1 and _ST35.count("setGuildaOv({") == 1
    and "setGuildaAcende({" in _ag35 and "setGuildaOv({" in _ag35
    and '(g.acende || []).indexOf("nivel") >= 0' in _ag35 and "if (!onda || !g) return;" in _ag35,
    "ecrã: só o `guilda_ganho` do servidor acende e põe o 'depois' — num sítio só, com a onda")
_mo35 = _ST35.split("async function melhorarOnda(key) {")[1].split("\n      }\n")[0] if "async function melhorarOnda(" in _ST35 else ""
_ap35 = re.findall(r"aplicarGanhoGuilda\(([a-z.]+)\.guilda_ganho", _ST35)
chk(_ap35 == ["res"] and 0 <= _mo35.find("if (res && res.ok) {") < _mo35.find("aplicarGanhoGuilda(res.guilda_ganho"),
    "ecrã: o ganho chega da melhoria DEPOIS do `ok` e só dela (%r)" % _ap35)
_ac35 = re.findall(r"acende=\{([^}]*)\}", _GP35)
chk(_ac35 == ["!!acende && acende.key === inst.key"],
    "ecrã: só a instalação melhorada acende (%r) — o tesouro, a contribuição e os membros nunca" % _ac35)
chk(_GP35.count("<MarcaOnda") == 1 and "corpo-nucleo-acende" not in _GP35 and "corpo-halo-acende" not in _GP35,
    "ecrã: a marca é a do dono (`MarcaOnda`) — a planta não escreve a gramática à mão")
chk("upgradeCost(" not in _GP35 and "Math.pow" not in _GP35 and "1000 *" not in _GP35
    and "atual.next_cost" in _GP35 and "atual.effect_n" in _GP35,
    "ecrã: o custo e o efeito vêm do SERVIDOR — a planta não repete a fórmula do motor")
_rama35 = _ST35.split("<StatGrid stats={plantaOk ? [")[1].split("] : [")[0] if "<StatGrid stats={plantaOk ? [" in _ST35 else ""
chk(_rama35 and ".reduce(" not in _rama35 and "fmtNum(" not in _rama35 and "guilda_onda_membros_de" in _rama35
    and _rama35.count("fmtFull(") >= 4,
    "ecrã: com a onda os números são INTEIROS e nomeados (\"49 de 50\") — e NADA soma as seis "
    "instalações num 'nível da guilda'")
chk("const plantaOk = onda && Array.isArray(s.planta) && s.planta.length > 0;" in _ST35,
    "ecrã: sem a planta do servidor não há planta — a aba de hoje inteira, nunca números do cliente")
_off35 = _ST35.split("{plantaOk ? (")[1] if "{plantaOk ? (" in _ST35 else ""
chk("<GuildaPlanta " in _off35.split(") : (")[0] and "BUILDING_ICONS[k]" in _off35.split(") : (", 1)[-1]
    and "<SectUpgradeBtn" in _off35.split(") : (", 1)[-1]
    and "{ label: t(\"buildings\"), value: Object.values(s.buildings).reduce(" in _ST35
    and 'value: `🪨 ${fmtNum(s.spirit_stones)}`' in _ST35,
    "ecrã: sem a chave-mestra a aba é a de hoje — o cartão dos edifícios, a soma e o tesouro abreviado")
chk("fmtNum(" not in _GP35 + _RG35 and (_GP35 + _RG35).count("fmtFull(") >= 8,
    "ecrã: a planta e o recibo escrevem os números INTEIROS (`fmtFull`)")
chk(not _EMO34.findall(_GP35 + _RG35 + _rama35),
    "ecrã: a planta nasce sem emoji nem seta tipográfica (a catraca do §15)")
chk("g && g.antes" in _RG35 and "g && g.depois" in _RG35 and "next_cost" not in _RG35,
    "ecrã: o recibo sai do `guilda_ganho` (antes->depois da MESMA transacção)")
_mk35 = re.search(r"var GUILDA_MARCA = \{(.*?)\};", _TBc33, re.S)
_mapa35 = dict(re.findall(r"([a-z_]+): \"([a-z]+)\"", _mk35.group(1))) if _mk35 else {}
_marcas35 = set(re.findall(r"^\s{6}([a-z_]+):\s*\{", rd("miniapp/components/ui.js").split("var NIV_MARKS = {", 1)[1]
                           .split("\n    };", 1)[0], re.M))
chk(set(_mapa35) == set(_INST35) and all(_v in _marcas35 for _v in _mapa35.values()) and len(_marcas35) > 30,
    "ecrã: cada instalação do MOTOR tem uma marca que EXISTE (%r)" % {_k: _v for _k, _v in _mapa35.items()
                                                                     if _v not in _marcas35})
_k35 = sorted(set(re.findall(r't\("(guilda_onda_[a-z0-9_]+)"', _TBc33)))
_kk35 = _k35 + ["guilda_inst_" + _i for _i in _INST35] + ["guilda_efeito_" + _i for _i in _INST35]
chk(len(_k35) >= 14 and all(_k in _MI33[_lg] for _k in _kk35 for _lg in ("pt", "en", "es")),
    "ecrã/i18n: as %d chaves da planta (e o nome e o efeito de cada instalação do motor) existem nas "
    "3 línguas (falta %r)" % (len(_kk35), [_k for _k in _kk35 if _k not in _MI33["es"]][:4]))
chk("scrollMarginBottom: GUILDA_FOLGA_BAIXO" in _GP35 and "GUILDA_FOLGA_BAIXO) return;" in _ST35,
    "ecrã: a planta volta à vista ACIMA da barra de baixo (olhado a 390: o recibo ficava por trás dela)")
_bl35 = "\n".join(_GP35.split('t("guilda_onda_para"')[0].split("\n")[-5:]) if 't("guilda_onda_para"' in _GP35 else "fresco &&"
chk("fresco" not in _bl35 and "!!busy || !fresco || !basta" in _GP35,
    "ecrã: o bloco do próximo nível nunca some à espera da releitura (o salto de 70 px olhado a 390); "
    "só o botão espera")

# ── 35.4 O ARNÊS corre as rotas reais ────────────────────────────────────────
_ra35 = re.search(r"_ROTAS_GUILDA = \{(.*?)\}", _AR33, re.S)
chk(_ra35 is not None and set(_portas35) | {"sect"} <= set(re.findall(r'"([a-z_/]+)":', _ra35.group(1)))
    and "getattr(_Wg, fn_nome)" in _AR33,
    "arnês: a aba e a porta da Guilda correm o HANDLER REAL (a Guilda nunca tinha estado no arnês)")

# ══════════════════════════════════════════════════════════════════════════
# §36 — 層 AS MASMORRAS: o corte em patamares, o ganho e as portas (4.3, 2026-10-08)
# ══════════════════════════════════════════════════════════════════════════
#
# 🔴 O QUE SE MEDIU ANTES (Lei 0 passo 1 — `tools/db_readonly_masmorras_1008.py`):
#   · as Masmorras VIVEM: no Beta 10 dos 16 activos mexeram em 30 dias e houve
#     1.822 duelos do Chefe (8 jogadores; UM faz 1.687, mediana de 48 s entre
#     Chefes); no `main` 22 dos 36 mexeram, mas quase só VARREM (2 Chefes em 30 d);
#   · "alcançado" NÃO é "subir ao entrar": `current_floor` e `max_floor_reached`
#     só se escrevem no ramo da VITÓRIA (as rotas e o chat) e o andar do Chefe no
#     fim do duelo — `current_floor = N` quer dizer "N vencido nesta expedição";
#   · "por dificuldade" NÃO existe no servidor (UM `max_floor_reached` por
#     masmorra): só as dificuldades ≤ `best_difficulty` (o gate da varredura);
#   · o arnês nem tinha as masmorras (catch-all).
#
#   36.1 o DONO — o alcance (UMA conta, o heal de 23/07), o corte, o ganho
#   36.2 a PORTA — os escritores DESCOBERTOS no código; as rotas CORREM numa
#        sessão que compila no dialecto do Postgres; ON/OFF chave a chave; o fim
#        do Chefe corre o settle REAL
#   36.3 o ECRÃ — o corte, só o confirmado acende, a acção antes do recibo, OFF
#   36.4 o ARNÊS corre as rotas reais (as masmorras nunca lá tinham estado)
print("\n=== 36. 層 AS MASMORRAS: o corte, o ganho e as portas ===")

import core.masmorra as _MA36
import core.pve_duel_settle as _PDS36
import handlers.dungeons as _HD36
import core.combat_engine as _CE36
import core.duel_engine as _DE36
import database.db as _DB36
from database.seeds.dungeon_seeds import DUNGEON_SEEDS as _SD36
from database.models import PlayerDungeon as _PD36
from core.i18n import catalog_name

_CAT36 = {int(_d["id"]): _NS33(**dict(_d, continent=None)) for _d in _SD36}
_SM36 = _CAT36[9]          # Spirit Mine: 6/12/15/19 andares (a do agricultor do Beta)

# ── 36.1 O DONO ──────────────────────────────────────────────────────────────
chk(tuple(_MA36.EIXOS_QUE_ACENDEM) == ("andar", "dificuldade"),
    "masmorra/dono: DUAS conquistas — o andar vencido e a dificuldade concluída; a posição, o "
    "alcance, o saco, a Vida e o Qi nunca acendem")


def _rt36(cur, mf, best, comp, dif):
    return _MA36.retrato(_SM36, cur, mf, best, comp, dif)


_a36 = _rt36(11, 19, 4, True, "nightmare")
_g36 = _MA36.ganho(_a36, _rt36(12, 19, 4, True, "nightmare"), 12)
chk(_g36 is not None and _g36["acende"] == ["andar"] and _g36["andar"] == 12
    and _MA36.ganho(_a36, _rt36(0, 19, 4, True, None), None) is None,
    "masmorra/ganho: o andar vencido acende (11 -> 12); a MORTE não passa andar e não acende")
chk(_MA36.ganho(_a36, _rt36(0, 19, 4, True, None), 12) is None
    and _MA36.ganho(_rt36(3, 3, 0, False, "easy"), _rt36(5, 5, 0, False, "easy"), 5) is None
    and _MA36.ganho(_rt36(18, 19, 4, True, "nightmare"), _rt36(0, 19, 4, True, None), 18) is None,
    "masmorra/ganho: as COLUNAS têm de provar o andar — um andar passado no ramo da morte de uma "
    "masmorra já concluída, um salto de dois andares ou um andar que não é o último não acendem")
_gc36 = _MA36.ganho(_rt36(18, 18, 3, True, "nightmare"), _rt36(0, 19, 4, True, None), 19)
_gr36 = _MA36.ganho(_rt36(18, 19, 4, True, "nightmare"), _rt36(0, 19, 4, True, None), 19)
chk(_gc36 is not None and _gc36["acende"] == ["andar", "dificuldade"] and _gc36["andar"] == 19
    and _gr36 is not None and _gr36["acende"] == ["andar"],
    "masmorra/ganho: o Chefe vencido acende o último andar — e a dificuldade só quando o "
    "`best_difficulty` SOBE (a 2.ª conclusão em Pesadelo não volta a acender a dificuldade)")
_ge36 = _MA36.ganho(_rt36(0, 0, 0, False, None), _rt36(1, 1, 0, False, "easy"), 1)
chk(_ge36 is not None and _ge36["acende"] == ["andar"] and _ge36["andar"] == 1
    and _MA36.ganho(None, _rt36(1, 1, 0, False, "easy"), 1) is None,
    "masmorra/ganho: a entrada acende o andar 1; sem 'antes' (a onda desligada) não há ganho")
chk(_MA36.alcance(_SM36, 11, True, 2) == 12 and _MA36.alcance(_SM36, 5, False, 0) == 5
    and _MA36.alcance(_SM36, 19, True, 1) == 19,
    "masmorra/dono: o alcance é UMA conta com o heal de 23/07 (concluída em Normal => venceu o "
    "andar 12, mesmo com o `max_floor_reached` cru em 11)")
chk(_rt36(0, 5, 0, False, None)["floor_count"] is None and _rt36(4, 4, 0, False, "hard")["floor_count"] == 15,
    "masmorra/dono: sem expedição não há percurso, logo nenhum denominador (lei §5.2); com ela, os "
    "andares da dificuldade dela (Spirit Mine em Difícil = 15)")
_MAc36 = re.sub(r'""".*?"""', "", "\n".join(_l for _l in rd("core/masmorra.py").split("\n")
                                            if not _l.strip().startswith("#")), flags=re.S)
chk("_get_floor_count(dungeon, dificuldade)" in _MAc36 and "DIFF_ORDER" in _MAc36
    and not re.search(r'"easy"|"nightmare"|floor_counts\[|\.floor_count\b', _MAc36),
    "masmorra/dono: os andares e as dificuldades vêm do MOTOR (`_get_floor_count`, `DIFF_ORDER`) — "
    "nenhuma cópia em `core/masmorra.py`")
_WSl36 = _ast33.unparse(_fws33["api_dungeons_list"])
chk("_masmorra.alcance(d, pd_row.max_floor_reached, pd_row.completed, bd)" in _WSl36
    and "fc.get(DUNGEON_DIFFICULTIES[bd - 1], 0)" not in _WSl36,
    "masmorra/dono: a lista lê o alcance do DONO — o heal escrito à mão dentro dela saiu (duas "
    "contas divergem)")
chk(_MA36.no_payload({"acende": []}, lambda _k: False) == {}
    and _MA36.no_payload({"acende": []}, lambda _k: _k == "a_obra") == {"masmorra_ganho": {"acende": []}}
    and _MA36.no_payload({"acende": []}, lambda _k: _k == "cultivador_jogavel") == {"masmorra_ganho": {"acende": []}}
    and _MA36.no_payload(None, lambda _k: True) == {}
    and _MA36.corte_no_payload(_SM36, _NS33(current_floor=1, max_floor_reached=1, best_difficulty=0,
                                            completed=False, difficulty="easy"), lambda _k: False) == {},
    "masmorra/ganho: `masmorra_ganho` e o `corte` só viajam com a chave-mestra (`a_obra` ou "
    "`cultivador_jogavel`) — sem ela, o payload de HOJE")

# ── 36.2 A PORTA ─────────────────────────────────────────────────────────────
# (a) quem ESCREVE o andar, descoberto no código: uma atribuição a
#     `current_floor` / `max_floor_reached` / `best_difficulty` em core/ e handlers/
_ATR36 = {"current_floor", "max_floor_reached", "best_difficulty"}
_esc36 = set()
for _d36 in ("core", "handlers"):
    for _f36 in sorted(os.listdir(os.path.join(ROOT, _d36))):
        if not _f36.endswith(".py"):
            continue
        for _fn36 in _ast33.walk(_ast33.parse(rd(_d36 + "/" + _f36))):
            if not isinstance(_fn36, (_ast33.FunctionDef, _ast33.AsyncFunctionDef)):
                continue
            for _n36 in _ast33.walk(_fn36):
                _alv36 = []
                if isinstance(_n36, (_ast33.Assign, _ast33.AugAssign)):
                    _alv36 = _n36.targets if isinstance(_n36, _ast33.Assign) else [_n36.target]
                if any(isinstance(_t, _ast33.Attribute) and _t.attr in _ATR36 for _t in _alv36):
                    _esc36.add(_d36 + "/" + _f36 + ":" + _fn36.name)
chk(_esc36 == {"core/webserver.py:api_dungeons_enter", "core/webserver.py:api_dungeons_advance",
               "core/webserver.py:api_dungeons_retreat", "core/pve_duel_settle.py:_settle_dungeon_boss",
               "handlers/dungeons.py:_dungeon_start_with_stance", "handlers/dungeons.py:dungeon_advance",
               "handlers/dungeons.py:dungeon_auto_advance", "handlers/dungeons.py:dungeon_retreat"},
    "masmorra/porta: ANTI-GUARDA — os escritores do andar, lidos no CÓDIGO: 3 rotas, o fim do Chefe e "
    "o chat (legado, sem luz) (%r)" % sorted(_esc36))
# (b) as ROTAS do mini-app que escrevem o andar, descobertas nas rotas
_rotas36 = dict(re.findall(r'add_post\("/api/miniapp/([a-z_/]+)", (api_[a-z_]+)\)', _WS33))
_portas36 = sorted(_r for _r, _fn in _rotas36.items()
                   if "core/webserver.py:" + _fn in _esc36)
chk(_portas36 == ["dungeons/advance", "dungeons/enter", "dungeons/retreat"],
    "masmorra/porta: ANTI-GUARDA — as rotas que escrevem o andar, descobertas nas ROTAS (%r)" % _portas36)
# (c) só as que VENCEM um andar dão o ganho — e o andar só no ramo da vitória
_WSe36 = _ast33.unparse(_fws33["api_dungeons_enter"])
_WSa36 = _ast33.unparse(_fws33["api_dungeons_advance"])
_WSr36 = _ast33.unparse(_fws33["api_dungeons_retreat"])
_WSw36 = _ast33.unparse(_fws33["api_dungeons_sweep"])
_ANT36 = "_masmorra.ler_antes(session, user_id, dungeon) if _onda_on() else None"
for _nm36, _src36 in (("enter", _WSe36), ("advance", _WSa36)):
    _ia36 = _src36.find(_ANT36)
    _ie36 = _src36.find("select(PlayerDungeon)")
    chk(0 <= _ia36 < _ie36 and "**_masmorra.no_payload(_g)" in _src36,
        "masmorra/porta: `%s` lê o 'antes' (só com a onda) ANTES de carregar a linha e devolve o ganho"
        % _nm36)
chk("andar=1 if won else None" in _WSe36
    and "andar=next_floor if won else None" in _WSa36 and "andar=floor_count)" in _WSa36
    and _WSa36.count("_masmorra.ganho_da_acao(") == 2,
    "masmorra/porta: o andar só se passa no ramo da VITÓRIA (o 1 na entrada, o seguinte no avanço, o "
    "último na conclusão) — a morte passa `None`; o Chefe (o duelo ainda por decidir) não passa nada")
chk("_masmorra" not in _WSr36 and "_masmorra" not in _WSw36 and "masmorra_ganho" not in _WSr36 + _WSw36,
    "masmorra/porta: o recuo e a varredura não sobem nada e não acendem nada")
_PDSs36 = rd("core/pve_duel_settle.py").replace("\r\n", "\n")
_PDSb36 = _PDSs36.split("async def _settle_dungeon_boss(", 1)[1].split("\nasync def ", 1)[0]
_ia36 = _PDSb36.find("_masmorra.ler_antes(session, player.telegram_id, dungeon)")
_ie36 = _PDSb36.find("select(PlayerDungeon)")
chk(0 <= _ia36 < _ie36 and "if _onda_on():" in _PDSb36[:_ia36]
    and "andar=floor_count if won else None" in _PDSb36
    and '**({"masmorra_ganho": _g} if _g else {})' in _PDSb36,
    "masmorra/porta: o fim do Chefe lê o 'antes' (só com a onda) antes de carregar a linha; o último "
    "andar só na vitória; o ganho vai no payload do `pve_settled`")
_WSds36 = _ast33.unparse(_fws33["api_combat_duel_state"])
chk("_mg = (_e.get('payload') or {}).get('masmorra_ganho')" in _WSds36
    and "out.update(_masmorra_ds.no_payload(_mg))" in _WSds36,
    "masmorra/porta: o `duel_state` dá o ganho do Chefe pelo espelho da chave-mestra (`no_payload`)")
chk("**_masmorra.corte_no_payload(d, pd_row)" in _WSl36,
    "masmorra/porta: a expedição aberta da lista leva o corte — só com a onda")
# (d) o espólio com nome na língua de quem o recebe — em TODOS os chamadores
_rbi36 = [_c for _fn in _fws33.values() for _c in _ast33.walk(_fn)
          if isinstance(_c, _ast33.Call) and getattr(_c.func, "id", None) == "_resolve_bag_items"]
chk(len(_rbi36) >= 6 and all(len(_c.args) == 3 and _ast33.unparse(_c.args[2]) == "_pl_lang(player)"
                             for _c in _rbi36)
    and "_nome('herb', r)" in _ast33.unparse(_fws33["_resolve_bag_items"]),
    "masmorra/porta: o espólio nomeado sai na língua do jogador em TODOS os %d chamadores (escrevia o "
    "nome cru do catálogo, em inglês)" % len(_rbi36))


# (e) as portas CORREM — numa sessão que compila no dialecto do Postgres
class _Sess36:
    def __init__(self, jog, pds):
        self.j, self.pds, self.sql = jog, pds, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def rollback(self):
        return None

    async def scalar(self, stmt):
        return 0

    async def get(self, ent, ident):
        return None

    def begin_nested(self):
        class _N36:
            async def __aenter__(s2):
                return s2

            async def __aexit__(s2, *a):
                return False
        return _N36()

    def add(self, o):
        if isinstance(o, _PD36):
            self.pds[int(o.dungeon_id)] = o

    async def execute(self, stmt):
        _cd = getattr(stmt, "column_descriptions", None)
        if _cd is None:
            return _Res33()
        try:
            _txt = str(stmt.compile(dialect=_pg33.dialect(), compile_kwargs={"literal_binds": True}))
        except Exception:
            _txt = str(stmt.compile(dialect=_pg33.dialect()))
        self.sql.append(_txt)
        _nomes = [getattr(_c.get("entity"), "__name__", "") for _c in _cd]
        _inteira = len(_cd) == 1 and _cd[0].get("expr") is _cd[0].get("entity")
        _m = re.search(r"player_dungeons\.dungeon_id = (\d+)", _txt)
        _did = int(_m.group(1)) if _m else None
        if _nomes == ["Player"] and _inteira:
            return _Res33([self.j])
        if _nomes == ["DungeonCatalog"] and _inteira:
            _mi = re.search(r"dungeons_catalog\.id = (\d+)", _txt)
            return _Res33([_CAT36[int(_mi.group(1))]] if _mi else [_CAT36[_k] for _k in sorted(_CAT36)])
        if _nomes == ["PlayerDungeon"] and _inteira:
            if _did is None:
                return _Res33(list(self.pds.values()))
            return _Res33([self.pds[_did]] if _did in self.pds else [])
        if _nomes and all(_n == "PlayerDungeon" for _n in _nomes):
            _p = self.pds.get(_did)
            if _p is None:
                return _Res33()
            _campos = [_c["name"] for _c in _cd]
            _l = _col34.namedtuple("L36", _campos)(*[getattr(_p, _c, None) for _c in _campos])
            return _Res33([_l], first=_l)
        if _nomes == ["HerbCatalog"] and _inteira:
            from database.seeds.alchemy_seeds import HERBS as _SH36
            return _Res33([_NS33(id=int(_h["id"]), name=_h["name"], emoji=_h.get("emoji"), tier=_h.get("tier"))
                           for _h in _SH36 if "herbs_catalog.id IN (2)" in _txt and int(_h["id"]) == 2])
        return _Res33()


def _pd36(cur, mf, best, comp, dif, did=9):
    return _NS33(player_id=77, dungeon_id=did, current_floor=cur, max_floor_reached=mf,
                 best_difficulty=best, completed=comp, difficulty=dif,
                 expedition_bag={"stones": 100}, last_attempt_at=None)


def _corre36(fn, payload, onda, pds, ganha=True, settle=None):
    """Corre a ROTA real (ou o settle real) sobre a sessão falsa: o combate do andar
    é encenado (o real pede a alma inteira); tudo o resto é o código de produção."""
    _j = _NS33(telegram_id=77, realm=3, qi=4120.0, qi_capacity=6800.0, spirit_stones=1000,
               current_hp=18000.0, max_hp=21400.0, language="pt", current_continent="linghe",
               home_continent="linghe", is_traveling=False, body_tempering_level=4,
               body_tempering_xp=0, core_essence=0, luck=41)
    _s = _Sess36(_j, pds)

    async def _andar(session, player, dungeon, target_floor, difficulty, lang, stance="balanced", focus_tech_id=0):
        return (True, "", {"stones": 120, "herbs": {"2": 1}}) if ganha else (False, "", {})

    async def _transf(session, player, bag):
        return None

    async def _hp(session, player):
        return 18000.0, 21400.0

    async def _chefe(session, player, **k):
        return _NS33(id="chefe-36")

    async def _destr(session, user_id):
        return 0
    _orig = (_W33.get_session_factory, _PO33.onda_on, _DB36.feature_enabled_for_world, _W33._soul_hp_pair,
             _CE36.get_current_hp, _HD36._do_dungeon_floor, _HD36._transfer_bag_to_inventory,
             _DE36.start_duel_pve, _DE36.unlock_stuck_duels_for_player)
    _W33.get_session_factory = lambda: (lambda: _s)
    _PO33.onda_on = lambda *a, **k: onda
    _DB36.feature_enabled_for_world = lambda feature, world_key=None: False
    _W33._soul_hp_pair = _hp
    _CE36.get_current_hp = lambda p: 18000.0
    _HD36._do_dungeon_floor = _andar
    _HD36._transfer_bag_to_inventory = _transf
    _DE36.start_duel_pve = _chefe
    _DE36.unlock_stuck_duels_for_player = _destr
    try:
        if settle is not None:
            _duelo = _NS33(id="chefe-36", pve_context={"dungeon_id": 9, "floor": 19, "floor_count": 19},
                           action_log=[], round_idx=3)
            return _aio33.run(_PDS36._settle_dungeon_boss(_s, _duelo, _j, settle)), _s
        _resp = _aio33.run(getattr(_W33, fn)({"user_id": 77, "payload": payload}))
        return _json33.loads(_resp.text), _s
    except Exception as _ex:
        return "%s: %s" % (type(_ex).__name__, str(_ex)[:160]), _s
    finally:
        (_W33.get_session_factory, _PO33.onda_on, _DB36.feature_enabled_for_world, _W33._soul_hp_pair,
         _CE36.get_current_hp, _HD36._do_dungeon_floor, _HD36._transfer_bag_to_inventory,
         _DE36.start_duel_pve, _DE36.unlock_stuck_duels_for_player) = _orig


_ANTES36 = "SELECT player_dungeons.current_floor, player_dungeons.max_floor_reached"
_ENT36 = "SELECT player_dungeons.player_id, player_dungeons.dungeon_id"
_pds36 = {9: _pd36(11, 19, 4, True, "nightmare")}
_c36, _s36 = _corre36("api_dungeons_advance", {"dungeon_id": 9}, True, _pds36)
_k36 = _c36.get("masmorra_ganho") if isinstance(_c36, dict) else None
chk(isinstance(_k36, dict) and _k36["antes"]["current_floor"] == 11 and _k36["depois"]["current_floor"] == 12
    and _k36["acende"] == ["andar"] and _k36["andar"] == 12 and _pds36[9].current_floor == 12,
    "masmorra/rota: o avanço CORRE e devolve `masmorra_ganho` 11 -> 12 com o andar aceso (%r)"
    % (_c36 if not isinstance(_k36, dict) else _k36["acende"],))
_ia36 = next((_i for _i, _q in enumerate(_s36.sql) if _q.startswith(_ANTES36)), -1)
_ie36 = next((_i for _i, _q in enumerate(_s36.sql) if _q.startswith(_ENT36)), -1)
chk(0 <= _ia36 < _ie36 and "FOR UPDATE OF player_dungeons" in _s36.sql[_ia36],
    "masmorra/rota: o 'antes' lê COLUNAS (nunca a entidade), TRANCADO, ANTES de a rota carregar a linha")
_nm36 = [_i.get("name") for _i in (_c36.get("loot_named_items") or [])] if isinstance(_c36, dict) else []
from database.seeds.alchemy_seeds import HERBS as _SH36b
_cru36 = next(_h["name"] for _h in _SH36b if int(_h["id"]) == 2)
chk(_nm36 == [catalog_name("pt", "herb", _NS33(id=2, name=_cru36))] and _nm36[0] != _cru36,
    "masmorra/rota: o espólio do andar sai em pt (%r, nunca o cru %r)" % (_nm36, _cru36))
_pds36 = {9: _pd36(11, 19, 4, True, "nightmare")}
_c36, _s36 = _corre36("api_dungeons_advance", {"dungeon_id": 9}, False, _pds36)
chk(isinstance(_c36, dict) and list(_c36) == ["ok", "won", "dead", "floor", "floor_count", "completed",
                                               "loot_this_floor", "loot_named_items", "current_hp", "max_hp",
                                               "qi", "qi_capacity", "spirit_stones", "bag_summary", "delta"]
    and not any(_q.startswith(_ANTES36) for _q in _s36.sql),
    "masmorra/rota: com a onda OFF a resposta do avanço é a de HOJE, chave a chave, e não há leitura nem "
    "trinco a mais (%r)" % (list(_c36) if isinstance(_c36, dict) else _c36,))
_pds36 = {9: _pd36(11, 19, 4, True, "nightmare")}
_c36, _ = _corre36("api_dungeons_advance", {"dungeon_id": 9}, True, _pds36, ganha=False)
chk(isinstance(_c36, dict) and _c36.get("dead") is True and "masmorra_ganho" not in _c36
    and _pds36[9].current_floor == 0,
    "masmorra/rota: a MORTE volta o percurso a zero e nada acende (%r)" % (_c36 if not isinstance(_c36, dict) else "",))
_pds36 = {9: _pd36(18, 19, 4, True, "nightmare")}
_c36, _ = _corre36("api_dungeons_advance", {"dungeon_id": 9}, True, _pds36)
chk(isinstance(_c36, dict) and _c36.get("is_boss_floor") is True and "masmorra_ganho" not in _c36
    and _pds36[9].current_floor == 18,
    "masmorra/rota: à porta do Chefe o avanço abre o duelo e NADA acende ainda (o Chefe decide-se no fim)")
_pds36 = {}
_c36, _ = _corre36("api_dungeons_enter", {"dungeon_id": 9, "difficulty": "easy"}, True, _pds36)
_k36 = _c36.get("masmorra_ganho") if isinstance(_c36, dict) else None
chk(isinstance(_k36, dict) and _k36["andar"] == 1 and _k36["antes"]["current_floor"] == 0
    and _k36["depois"]["floor_count"] == 6 and 9 in _pds36,
    "masmorra/rota: a entrada de quem nunca lá foi CORRE, cria a linha e acende o andar 1 (%r)"
    % (_c36 if not isinstance(_k36, dict) else "",))
_pds36 = {9: _pd36(11, 19, 4, True, "nightmare")}
_c36, _ = _corre36("api_dungeons_list", {}, True, _pds36)
_ar36 = (_c36.get("active_run") or {}) if isinstance(_c36, dict) else {}
chk(_ar36.get("corte") == {"dungeon_id": 9, "current_floor": 11, "difficulty": "nightmare", "floor_count": 19,
                           "max_floor_reached": 19, "best_difficulty": 4, "completed": True},
    "masmorra/rota: a lista CORRE e a expedição aberta leva o corte do servidor (%r)" % (_ar36,))
_c36, _ = _corre36("api_dungeons_list", {}, False, _pds36)
_ar36 = (_c36.get("active_run") or {}) if isinstance(_c36, dict) else {}
chk(list(_ar36) == ["dungeon_id", "name", "emoji", "current_floor", "floor_count", "difficulty", "bag_summary"],
    "masmorra/rota: com a onda OFF a expedição aberta é a de HOJE, chave a chave (%r)" % (list(_ar36),))
_pds36 = {9: _pd36(18, 18, 3, True, "nightmare")}
_c36, _s36 = _corre36(None, None, True, _pds36, settle=True)
_k36 = _c36.get("masmorra_ganho") if isinstance(_c36, dict) else None
chk(isinstance(_k36, dict) and _k36["acende"] == ["andar", "dificuldade"] and _k36["andar"] == 19
    and _pds36[9].best_difficulty == 4 and _pds36[9].current_floor == 0
    and any(_q.startswith(_ANTES36) and "FOR UPDATE OF player_dungeons" in _q for _q in _s36.sql),
    "masmorra/chefe: o fim do Chefe CORRE (o settle real) e acende o andar 19 e o Pesadelo (%r)"
    % (_c36 if not isinstance(_k36, dict) else "",))
_pds36 = {9: _pd36(18, 18, 3, True, "nightmare")}
_c36, _ = _corre36(None, None, True, _pds36, settle=False)
_pds36b = {9: _pd36(18, 18, 3, True, "nightmare")}
_c36b, _s36b = _corre36(None, None, False, _pds36b, settle=True)
chk(isinstance(_c36, dict) and "masmorra_ganho" not in _c36 and _pds36[9].current_floor == 0
    and isinstance(_c36b, dict) and "masmorra_ganho" not in _c36b
    and not any(_q.startswith(_ANTES36) for _q in _s36b.sql),
    "masmorra/chefe: o Chefe que ganha não acende nada; com a onda OFF o settle é o de HOJE, sem leitura "
    "a mais")

# ── 36.3 O ECRÃ ──────────────────────────────────────────────────────────────
_DT36 = _fn25(_TBc33, "    function DungeonsTab(")
_RC36 = _fn25(_TBc33, "    function DungeonRunCard(")
_EX36 = _fn25(_TBc33, "    function MasmorraExpedicao(")
_CO36 = _fn25(_TBc33, "    function MasmorraCorte(")
_DI36 = _fn25(_TBc33, "    function MasmorraDificuldades(")
_RE36 = _fn25(_TBc33, "    function reciboDaMasmorra(")
_EM36 = _fn25(_TBc33, "    function DungeonEntryModal(")
_CA36 = _fn25(_TBc33, "    function DungeonCard(")
_DA36 = _fn25(_TBc33, "    function DuelArenaModal(")
_RM36 = _fn25(_TBc33, "    function DungeonResultModal(")
chk(len(_DT36) > 5000 and len(_RC36) > 3000 and len(_EX36) > 3000 and len(_CO36) > 1200
    and len(_DI36) > 800 and len(_RE36) > 400 and len(_DA36) > 5000,
    "ecrã: ANTI-GUARDA — a aba, a expedição, o corte, as dificuldades, o recibo e o duelo foram fatiados")
_ret36 = _DT36.find("return <ListSkeleton")
chk(0 < _DT36.find("const [mOv, setMOv] = useState(null);") < _ret36
    and 0 < _DT36.find("const mReciboRef = useRef(null);") < _ret36
    and _DT36.count("const onda = obraOn();") == 1,
    "ecrã: a chave-mestra UMA vez e TODOS os estados da onda antes do 1.º `return` (React #310)")
chk(_DT36.count("setMAcende({") == 1 and "g.andar || null" in _DT36
    and '(g.acende || []).indexOf("dificuldade") >= 0' in _DT36
    and _DT36.count("aplicarGanhoMasmorra(") == 3 and "onGanho={aplicarGanhoMasmorra}" in _DT36,
    "ecrã: só o `masmorra_ganho` acende — UMA porta (`aplicarGanhoMasmorra`), chamada pelo andar, pela "
    "entrada e pelo fim do Chefe; nunca pelo toque")
chk("aplicarGanhoMasmorra" not in _DT36.split("async function sweepAgain(", 1)[1].split("useEffect(", 1)[0]
    and "setMRecibo(null); setMOv(null); setMFim(null);" in _DT36,
    "ecrã: a varredura não acende nada; a morte e o recuo limpam o recibo de uma expedição que acabou")
chk('f <= v ? "got" : f === v + 1 ? "next" : "empty"' in _CO36 and "acende={acende === f}" in _CO36
    and "MASM_POR_PATAMAR" in _CO36,
    "ecrã: o corte marca os andares VENCIDOS (ouro), o próximo (contorno) e o resto — e acende só o "
    "andar do ganho")
chk('nivel <= m ? "got" : nivel === m + 1 ? "next" : "empty"' in _DI36,
    "ecrã: por dificuldade, só o que o servidor deixa fazer — as vencidas (≤ `best_difficulty`)")
chk(not _EMO34.findall(_CO36 + _DI36 + _EX36 + _RE36),
    "ecrã: o corte, as dificuldades, a expedição e o recibo nascem sem emoji (a catraca do §15)")
chk("fmtNum(" not in _CO36 + _DI36 + _EX36 + _RE36 and (_EX36 + _RE36).count("fmtFull(") >= 8,
    "ecrã: os números do corte e do recibo são INTEIROS (`fmtFull`)")
_ol36 = _EX36.find("data-masmorra-leitura")
_oa36 = _EX36.find("onClick={onAvancar}")
_or36 = _EX36.find("data-masmorra-recibo")
_oh36 = _EX36.find("<HPBar")
chk(0 < _ol36 < _oa36 < _or36 < _oh36,
    "ecrã: a ACÇÃO vem antes do recibo e dentro da leitura (olhado: a 390 o recibo empurrava o 'Avançar' "
    "90 px para trás da barra; a 1440 os botões esticavam a 1.050 px)")
chk("scrollMarginBottom: MASM_FOLGA_BAIXO" in _EX36 and "MASM_FOLGA_BAIXO) return;" in _DT36
    and "var MASM_FOLGA_BAIXO = GUILDA_FOLGA_BAIXO;" in _TBc33,
    "ecrã: o recibo volta à vista ACIMA da barra de baixo — a MESMA folga da Guilda (um valor)")
_dar36 = _DA36.find("if (!state) {")
chk("function DuelArenaModal({ duelId, onClose, playerLang, onFim })" in _TBc33
    and 0 < _DA36.find("const _fimDado = useRef(false);") < _dar36,
    "ecrã: o duelo entrega o fim CONFIRMADO a quem o abriu (`onFim`), com o hook antes do 1.º `return`")
chk("onFim={onda ?" in _RC36 and "if (g && onFimMasmorra) onFimMasmorra(g, run);" in _RC36,
    "ecrã: o ganho do Chefe só se mostra quando a janela do duelo FECHA (a luz debaixo dela não se vê)")
chk("if (corteOk) {" in _RC36 and 't("dungeon_floor_progress"' in _RC36 and 't("dungeon_advance_btn")' in _RC36
    and "onda ? (" in _CA36 and "DUNGEON_DIFF_EMOJI[st.best_difficulty_key]" in _CA36
    and "onda ? (" in _EM36 and "DUNGEON_DIFF_EMOJI[key]" in _EM36,
    "ecrã: sem a chave-mestra a expedição, o cartão e a janela de entrada são os de HOJE")
chk("floor: res.won ? res.floor : (Number(run.current_floor) || 0) + 1" in _RC36,
    "ecrã: a morte diz o andar onde se caiu (dizia 'andar 0' — o `floor` da morte é a posição DEPOIS de "
    "cair; escondido pelo título cortado)")
chk("function dngEspolioLinhas(" in _TBc33 and "dngEspolioLinhas(result.loot, named)" in _RM36
    and "fmtBagSummary(aggBag)" not in _RM36 and "dngEspolioLinhas(" in _DT36
    and "res.regional_bonus && res.regional_bonus.line" in _DT36,
    "ecrã: o espólio tem UMA conta (o modal e o recibo lêem a mesma) e o Tributo da Terra da conclusão "
    "vem no recibo")
_k36 = sorted(set(re.findall(r't\("(masm_onda_[a-z0-9_]+)"', _TBc33)))
chk(len(_k36) >= 20 and all(_k in _MI33[_lg] for _k in _k36 for _lg in ("pt", "en", "es")),
    "ecrã/i18n: as %d chaves do corte existem nas 3 línguas (falta %r)"
    % (len(_k36), [_k for _k in _k36 if _k not in _MI33["es"] or _k not in _MI33["en"]][:4]))
_rep36 = [(_lg, _k) for _lg in ("pt", "en", "es") for _k, _v in _MI33[_lg].items()
          if isinstance(_v, str) and any(_v.count("{%s}" % _p) > 1 for _p in set(re.findall(r"\{(\w+)\}", _v)))]
chk(not _rep36,
    "ecrã/i18n: NENHUMA frase repete um marcador — o `t()` troca só a 1.ª ocorrência (olhado: saía "
    "'12 de {n} andares') (%r)" % (_rep36[:4],))
chk(_MI33["pt"]["tab_dungeons"] == "Masmorras"
    and not re.search(r"dungeon|quests", " ".join(_MI33["pt"][_k] for _k in _MI33["pt"]
                                                   if _k.startswith("dng_quest_modal")), re.I),
    "ecrã/i18n: em pt as masmorras dizem-se 'Masmorras' e as missões 'Missões' (o trilho dizia 'Dungeons')")
chk('<Mark name="dragon"' in _CO36 and "dragon" in rd("miniapp/components/ui.js").split("var NIV_MARKS = {", 1)[1][:9000],
    "ecrã: a marca do Chefe EXISTE no registo das marcas")

# ── 36.4 O ARNÊS corre as rotas reais ────────────────────────────────────────
_ra36 = re.search(r"_ROTAS_MASMORRA = \{(.*?)\}", _AR33, re.S)
chk(_ra36 is not None and {"dungeons/list", "dungeons/enter", "dungeons/advance", "dungeons/retreat"}
    <= set(re.findall(r'"([a-z_/]+)":', _ra36.group(1)))
    and "getattr(_Wm, fn_nome)" in _AR33 and "_PDSm._settle_dungeon_boss(" in _AR33,
    "arnês: as masmorras correm o HANDLER REAL e o fim do Chefe o SETTLE REAL (nunca lá tinham estado)")

print("\n" + "=" * 62)
print("  %d asserts verdes, %d vermelhos" % (_ok, len(_bad)))
if _bad:
    print("\n  VERMELHOS:")
    for m in _bad:
        print("   x " + m)
print("=" * 62)
sys.exit(1 if _bad else 0)
