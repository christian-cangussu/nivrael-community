# -*- coding: utf-8 -*-
"""本地之門 A porta local — o login de desenvolvimento da edição comunitária.

No jogo oficial entra-se pelo Telegram, pelo Google/Apple ou por e-mail. Numa
máquina de quem quer só jogar ou mexer no código não há nada disso configurado,
e a porta de verdade (`/login`) ficaria sem nenhum caminho que funcione (Lei §1).
Esta porta troca um NOME por uma sessão — a mesma sessão web do jogo oficial
(`core.web_session`), pelo mesmo `link_identity` + `issue_session` que o Firebase
usa, com o provider `dev`. O cliente do jogo não sabe por que porta se entrou.

⚠️ Não há senha. Por isso a porta só abre quando TUDO isto é verdade:
  1. `NIVRAEL_DEV_LOGIN=1` (dito em voz alta; nenhum default a liga);
  2. `WEBHOOK_URL` vazio — com ele definido isto é uma implantação a sério, e a
     porta recusa-se a abrir mesmo com a flag;
  3. o pedido vem DESTA máquina ou da rede local (o par TCP, nunca o
     `X-Forwarded-For`, que qualquer cliente escreve).

As frases vivem aqui, nas três línguas lado a lado, pela mesma razão de
`core/legal.py`: é uma página que só existe nesta edição, e enfiá-la nos
catálogos do jogo misturava-a com as 4.000 chaves que a cópia partilha com o
jogo oficial.
"""
from __future__ import annotations

import html
import ipaddress
import logging
import os
import re
from string import Template

from aiohttp import web

logger = logging.getLogger("community.dev_login")

FLAG = "NIVRAEL_DEV_LOGIN"
PROVIDER = "dev"
LOGIN_PATHS = frozenset({"/login", "/login/"})
POST_PATH = "/dev/login"
NAME_RE = re.compile(r"^[^\W_][\w \-]{0,22}[\w]$")
LANGS = ("pt", "en", "es")


def state() -> tuple[bool, str]:
    """(aberta?, porquê). Lida a cada pedido: mudar o `.env` e reiniciar basta."""
    raw = (os.getenv(FLAG) or "").strip().lower()
    if raw not in ("1", "true", "yes"):
        return False, f"{FLAG} não está ligado"
    if (os.getenv("WEBHOOK_URL") or "").strip():
        return False, "WEBHOOK_URL está definido — isto parece produção, e a porta sem senha recusa-se a abrir"
    return True, "aberta"


def peer_is_local(peer: str | None) -> bool:
    """O par TCP é esta máquina ou a rede local (onde vive o Docker)."""
    try:
        ip = ipaddress.ip_address((peer or "").split("%", 1)[0])
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private


def valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name or ""))


def account_key(name: str) -> str:
    """O mesmo nome, escrito de outra maneira, é a mesma conta."""
    return " ".join((name or "").split()).casefold()


# ── As frases ────────────────────────────────────────────────────────────────
S = {
    "pt": {
        "title": "Porta local · Nivrael",
        "tag": "edição comunitária",
        "h1": "Entrar no mundo local",
        "sub": "Login de desenvolvimento — só nesta máquina.",
        "hint": "Escolha um nome. Voltar com o mesmo nome é voltar ao mesmo personagem. "
                "Não há senha — por isso esta porta só abre com NIVRAEL_DEV_LOGIN=1 e nunca "
                "em servidor público.",
        "label": "Nome de entrada",
        "submit": "Entrar",
        "err_invalid": "Use de 2 a 24 letras, números, espaços, - ou _ (sem espaço nas pontas).",
        "err_server": "O servidor não conseguiu abrir a sessão. Veja o log do jogo — quase sempre "
                      "é o banco de dados ainda iniciando — e tente de novo.",
        "err_refused": "Esta porta só aceita pedidos desta máquina ou da rede local.",
        "view_world": "Ver o mundo sem entrar",
        "official": "Porta oficial (Telegram, Google, e-mail)",
        "note": "No jogo oficial esta porta não existe: lá se entra pelo Telegram, pelo Google "
                "ou por e-mail.",
    },
    "en": {
        "title": "Local gate · Nivrael",
        "tag": "community edition",
        "h1": "Enter the local world",
        "sub": "Development login — this machine only.",
        "hint": "Pick a name. Coming back with the same name brings back the same character. "
                "There is no password — which is why this gate only opens with "
                "NIVRAEL_DEV_LOGIN=1 and never on a public server.",
        "label": "Sign-in name",
        "submit": "Enter",
        "err_invalid": "Use 2 to 24 letters, digits, spaces, - or _ (no space at either end).",
        "err_server": "The server could not open a session. Check the game log — it is almost "
                      "always the database still starting — and try again.",
        "err_refused": "This gate only accepts requests from this machine or the local network.",
        "view_world": "See the world without signing in",
        "official": "Official gate (Telegram, Google, e-mail)",
        "note": "The official game has no such gate: there you sign in through Telegram, "
                "Google or e-mail.",
    },
    "es": {
        "title": "Puerta local · Nivrael",
        "tag": "edición comunitaria",
        "h1": "Entrar al mundo local",
        "sub": "Inicio de sesión de desarrollo — solo en esta máquina.",
        "hint": "Elige un nombre. Volver con el mismo nombre es volver al mismo personaje. "
                "No hay contraseña — por eso esta puerta solo se abre con "
                "NIVRAEL_DEV_LOGIN=1 y nunca en un servidor público.",
        "label": "Nombre de entrada",
        "submit": "Entrar",
        "err_invalid": "Usa de 2 a 24 letras, números, espacios, - o _ (sin espacio en los extremos).",
        "err_server": "El servidor no pudo abrir la sesión. Mira el log del juego — casi siempre "
                      "es la base de datos que aún está arrancando — e inténtalo de nuevo.",
        "err_refused": "Esta puerta solo acepta peticiones de esta máquina o de la red local.",
        "view_world": "Ver el mundo sin entrar",
        "official": "Puerta oficial (Telegram, Google, e-mail)",
        "note": "En el juego oficial esta puerta no existe: allí se entra por Telegram, Google "
                "o e-mail.",
    },
}
LANG_LABELS = {"pt": "Português", "en": "English", "es": "Español"}

# A pele é a da porta oficial (`miniapp/login.html`) — tinta quente, papel, o selo
# de cinábrio uma vez por página, Cormorant no título. Só o conteúdo muda.
PAGE = Template("""<!DOCTYPE html>
<html lang="$lang">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="robots" content="noindex">
  <meta name="theme-color" content="#0b0a0c">
  <title>$title</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400&family=Cinzel:wght@400;500&family=Noto+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --ink: #0b0a0c; --paper: #ece5d8; --gold: #c9903a; --seal: #c8442f;
      --muted: #baad97; --line: rgba(236,229,216,.17);
      --serif: 'Cormorant Garamond', Georgia, serif;
      --body: 'Noto Sans', system-ui, sans-serif;
      --label: 'Cinzel', Georgia, serif;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html { -webkit-text-size-adjust: 100%; background: var(--ink); color-scheme: dark; }
    body {
      min-height: 100svh; background: var(--ink); color: var(--paper);
      font: 14px/1.65 var(--body); -webkit-font-smoothing: antialiased; isolation: isolate;
    }
    ::selection { color: var(--ink); background: var(--gold); }
    body::before, body::after { content: ""; position: fixed; inset: 0; pointer-events: none; z-index: -1; }
    body::before {
      left: 21%;
      background: url('/miniapp/assets/isle-linghe-scene.webp') 58% center / cover no-repeat;
      filter: saturate(.7) brightness(.82);
    }
    body::after {
      background:
        linear-gradient(90deg, var(--ink) 9%, rgba(11,10,12,.95) 30%, rgba(11,10,12,.70) 47%, rgba(11,10,12,.12) 76%),
        linear-gradient(0deg, var(--ink), transparent 32%, transparent 76%, rgba(11,10,12,.35));
    }
    .gate {
      position: relative; min-height: 100svh; max-width: 1440px; margin: 0 auto;
      padding: 42px clamp(28px, 6vw, 88px) 48px;
      display: grid; grid-template-columns: 56px minmax(0, 460px); gap: 18px; align-content: start;
    }
    .seal-rail { position: relative; display: flex; justify-content: flex-start; padding-top: 113px; }
    .seal {
      writing-mode: vertical-rl; align-self: start;
      font: 500 15px/1.6 var(--body); letter-spacing: .34em;
      color: var(--paper); background: var(--seal); padding: 13px 7px 16px;
    }
    .seal-rail::after {
      content: ""; position: absolute; top: 254px; bottom: 8px; left: 19px; width: 1px;
      background: linear-gradient(180deg, var(--line), transparent 82%);
    }
    .body { min-width: 0; }
    .masthead { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px 20px; margin-bottom: 46px; }
    .eyebrow { font: 500 25px/1.4 var(--serif); letter-spacing: .22em; color: var(--paper); }
    .eyebrow small { display: block; font: 10px/1.7 var(--label); letter-spacing: .2em; color: var(--gold); text-transform: uppercase; }
    .langbar { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; }
    .langbar a {
      display: inline-flex; align-items: center; min-height: 44px; padding: 8px;
      font-size: 11px; color: var(--muted); text-decoration: none;
      border-bottom: 1px solid transparent; white-space: nowrap; transition: color .18s, border-color .18s;
    }
    .langbar a:hover { color: var(--paper); border-color: var(--line); }
    .langbar a[aria-current="true"] { color: var(--paper); border-color: var(--gold); cursor: default; }
    h1 {
      font: 400 clamp(60px, 5.8vw, 82px)/.98 var(--serif);
      letter-spacing: -.045em; margin-bottom: 18px; text-wrap: balance; overflow-wrap: break-word;
    }
    .sub { font: italic 400 23px/1.4 var(--serif); color: var(--muted); margin-bottom: 20px; }
    .hint { font-size: 13px; line-height: 1.85; color: var(--muted); max-width: 370px; margin-bottom: 27px; }
    .hint code { font-size: 12px; color: var(--paper); }
    button, input { font: inherit; }
    button { cursor: pointer; color: inherit; }
    button, a { -webkit-tap-highlight-color: transparent; }
    :is(button, a, input):focus-visible { outline: 2px solid var(--gold); outline-offset: 4px; }
    label { display: block; font: 10px/1.7 var(--label); letter-spacing: .16em; color: var(--muted); margin-bottom: 4px; text-transform: uppercase; }
    input {
      display: block; width: 100%; min-height: 50px; padding: 12px 0; margin-bottom: 20px;
      border: 0; border-bottom: 1px solid rgba(236,229,216,.36); border-radius: 0;
      background: rgba(11,10,12,.35); color: var(--paper); font-size: 16px;
      transition: border-color .18s, background .18s;
    }
    input:focus { border-bottom-color: var(--gold); background: rgba(11,10,12,.68); }
    .primary {
      display: flex; align-items: center; justify-content: space-between; gap: 20px;
      width: 100%; min-height: 54px; padding: 13px 22px;
      border: 1px solid var(--paper); border-radius: 0;
      background: var(--paper); color: var(--ink); font-size: 13px; font-weight: 500;
      transition: background .18s, border-color .18s;
    }
    .primary::after { content: "\\2192"; font: 24px/1 var(--serif); }
    .primary:hover { background: var(--muted); border-color: var(--muted); }
    .status { font-size: 13px; line-height: 1.65; margin-top: 12px; min-height: 22px; padding-left: 12px; border-left: 2px solid transparent; }
    .status.err { color: var(--paper); border-left-color: var(--seal); }
    footer { margin-top: 22px; padding-top: 17px; border-top: 1px solid var(--line); }
    .view-world {
      display: inline-flex; align-items: center; gap: 25px; min-height: 44px;
      color: var(--paper); font: 400 22px/1.4 var(--serif); text-decoration: none;
      margin-bottom: 12px; transition: color .18s;
    }
    .view-world::after { content: "\\2192"; }
    .view-world:hover { color: var(--gold); }
    .official { display: inline-flex; min-height: 44px; align-items: center; font-size: 12px; color: var(--muted); margin-bottom: 8px; }
    .official:hover { color: var(--paper); }
    .note { font-size: 12px; line-height: 1.8; color: var(--muted); }
    @keyframes arrive { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
    .body > :first-child, .seal { animation: arrive .6s ease-out both; }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
    @media (max-width: 1000px) {
      body::before { left: 12%; }
      body::after { background: linear-gradient(90deg, rgba(11,10,12,.97), rgba(11,10,12,.82) 46%, rgba(11,10,12,.35)), linear-gradient(0deg, var(--ink), transparent 60%); }
      .gate { grid-template-columns: 40px minmax(0, 440px); gap: 14px; }
      .seal { font-size: 13px; }
      .seal-rail::after { left: 17px; }
    }
    @media (max-width: 620px) {
      body::before { position: absolute; left: 0; bottom: auto; height: 540px; background-position: 55% 32%; }
      body::after { position: absolute; bottom: auto; height: 560px; background: linear-gradient(0deg, var(--ink) 2%, rgba(11,10,12,.55) 70%, rgba(11,10,12,.76)); }
      .gate { display: block; padding: 24px 24px calc(32px + env(safe-area-inset-bottom)); max-width: 510px; }
      .seal-rail { position: absolute; right: 24px; top: 121px; padding: 0; opacity: .82; }
      .seal-rail::after { display: none; }
      .seal { font-size: 11px; padding: 9px 4px 11px; }
      .masthead { margin-bottom: 36px; gap: 4px 16px; }
      .eyebrow { font-size: 23px; }
      .langbar { margin-left: -8px; }
      h1 { font-size: clamp(50px, 12vw, 66px); max-width: calc(100% - 30px); margin-bottom: 15px; }
      .sub { font-size: 21px; margin-bottom: 17px; }
      input { background: rgba(11,10,12,.76); }
      .view-world { font-size: 21px; }
    }
    @media (max-width: 360px) {
      .gate { padding-inline: 20px; }
      .seal-rail { right: 20px; top: 125px; }
      .langbar { flex-basis: 100%; }
    }
  </style>
</head>
<body>
  <div class="gate">
    <div class="seal-rail">
      <!-- 本地之門 — "o portão deste lugar". Decorativo: o h1 já diz o que é. -->
      <div class="seal" aria-hidden="true" lang="zh">本地之門</div>
    </div>
    <div class="body">
      <div>
        <div class="masthead">
          <p class="eyebrow">NIVRAEL<small>$tag</small></p>
          <nav class="langbar" aria-label="Language">$langbar</nav>
        </div>
        <h1>$h1</h1>
        <p class="sub">$sub</p>
      </div>
      <p class="hint">$hint</p>
      <form method="post" action="$post" autocomplete="on">
        <input type="hidden" name="lang" value="$lang">
        <label for="nome">$label</label>
        <input id="nome" name="nome" type="text" required minlength="2" maxlength="24"
               autocomplete="username" autocapitalize="words" spellcheck="false" value="$nome" autofocus>
        <button class="primary" type="submit">$submit</button>
      </form>
      <p class="status$status_cls" role="status" aria-live="polite">$status</p>
      <footer>
        <a class="view-world" href="/play">$view_world</a>
        $official
        <p class="note">$note</p>
      </footer>
    </div>
  </div>
</body>
</html>
""")


def _lang(request: web.Request, forced: str | None = None) -> str:
    lang = (forced or request.query.get("lang") or "").strip().lower()
    if lang in LANGS:
        return lang
    try:
        from core.webserver import public_lang
        lang = public_lang(request)
    except Exception:
        lang = "pt"
    return lang if lang in LANGS else "pt"


def _official_configured() -> bool:
    try:
        from core.webserver import firebase_web_config
        return bool(firebase_web_config().get("apiKey"))
    except Exception:
        return False


def render(request: web.Request, *, lang: str | None = None, error: str | None = None,
           name: str = "", status: int = 200) -> web.Response:
    lang = _lang(request, lang)
    s = S[lang]
    esc = html.escape
    # (sem barra invertida dentro das chavetas: produção é Python 3.11)
    current = ' aria-current="true"'
    langbar = "".join(
        f'<a href="/login?lang={code}" hreflang="{code}" lang="{code}"'
        f'{current if code == lang else ""}>{LANG_LABELS[code]}</a>'
        for code in LANGS)
    official = (f'<a class="official" href="/login?porta=oficial&amp;lang={lang}">{esc(s["official"])}</a>'
                if _official_configured() else "")
    hint = esc(s["hint"]).replace("NIVRAEL_DEV_LOGIN=1", "<code>NIVRAEL_DEV_LOGIN=1</code>")
    body = PAGE.substitute(
        lang=lang, title=esc(s["title"]), tag=esc(s["tag"]), langbar=langbar,
        h1=esc(s["h1"]), sub=esc(s["sub"]), hint=hint, post=POST_PATH,
        label=esc(s["label"]), nome=esc(name, quote=True), submit=esc(s["submit"]),
        status=esc(s[error]) if error else "", status_cls=" err" if error else "",
        view_world=esc(s["view_world"]), official=official, note=esc(s["note"]),
    )
    resp = web.Response(text=body, content_type="text/html", status=status,
                        headers={"Cache-Control": "no-store"})
    if request.query.get("lang") in LANGS:
        try:
            from core.webserver import LANG_COOKIE_NAME, LANG_COOKIE_MAX_AGE
            resp.set_cookie(LANG_COOKIE_NAME, lang, max_age=LANG_COOKIE_MAX_AGE,
                            samesite="Lax", path="/")
        except Exception:
            pass
    return resp


async def sign_in(request: web.Request) -> web.Response:
    """POST /dev/login — nome → identidade `dev` → sessão web → /app."""
    if not peer_is_local(request.remote):
        logger.warning("porta local recusada: pedido de %s (fora da rede local)", request.remote)
        return render(request, error="err_refused", status=403)
    form = await request.post()
    lang = _lang(request, str(form.get("lang") or ""))
    name = " ".join(str(form.get("nome") or "").split())
    if not valid_name(name):
        return render(request, lang=lang, error="err_invalid", name=name, status=400)

    from core.web_session import (WebSessionError, find_identity, issue_session,
                                  link_identity, set_session_cookies)
    from database.control_db import allocate_synthetic_player_id
    uid = account_key(name)
    # O que o `world/start` lê para dar nome e língua ao personagem novo.
    profile = {"first_name": name, "username": "", "language_code": lang}
    try:
        found = await find_identity(PROVIDER, uid)
        if found is not None:
            identity_id, player_id = found
        else:
            synthetic = await allocate_synthetic_player_id()
            if synthetic is None:
                return render(request, lang=lang, error="err_server", name=name, status=503)
            linked = await link_identity(PROVIDER, uid, synthetic, profile)
            if linked is None:
                return render(request, lang=lang, error="err_server", name=name, status=503)
            identity_id, player_id = linked
        cookie_value, csrf, expires = await issue_session(player_id, PROVIDER, identity_id, profile)
    except WebSessionError:
        logger.exception("porta local: emissão de sessão falhou")
        return render(request, lang=lang, error="err_server", name=name, status=503)
    except Exception:
        logger.exception("porta local: falha inesperada")
        return render(request, lang=lang, error="err_server", name=name, status=500)

    resp = web.Response(status=303, headers={"Location": "/app", "Cache-Control": "no-store"})
    set_session_cookies(resp, cookie_value, csrf, expires)
    try:
        from core.webserver import LANG_COOKIE_NAME, LANG_COOKIE_MAX_AGE
        resp.set_cookie(LANG_COOKIE_NAME, lang, max_age=LANG_COOKIE_MAX_AGE, samesite="Lax", path="/")
    except Exception:
        pass
    logger.info("porta local: sessão emitida pid=%s (%s)", player_id, "conta existente" if found else "conta nova")
    return resp


@web.middleware
async def middleware(request: web.Request, handler):
    """Fica à frente de tudo — mas só intercepta os dois caminhos da porta."""
    path = request.path
    if path in LOGIN_PATHS and request.method == "GET" and request.query.get("porta") != "oficial":
        if state()[0]:
            return render(request)
    elif path == POST_PATH:
        if not state()[0]:
            raise web.HTTPNotFound()
        if request.method != "POST":
            raise web.HTTPMethodNotAllowed(request.method, ["POST"])
        return await sign_in(request)
    return await handler(request)


def install(app: web.Application) -> bool:
    """Põe a porta à frente da aplicação. Devolve se ficou aberta."""
    aberta, porque = state()
    app.middlewares.insert(0, middleware)
    if aberta:
        logger.warning("🔓 PORTA LOCAL ABERTA (%s=1): /login entra por NOME, sem senha. "
                       "Só para desenvolvimento — nunca num servidor público.", FLAG)
    else:
        logger.info("porta local fechada: %s", porque)
    return aberta
