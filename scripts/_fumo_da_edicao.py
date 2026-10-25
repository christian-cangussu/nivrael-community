# -*- coding: utf-8 -*-
"""煙 THE SMOKE TEST — a running instance, walked like a player walks it.

    python scripts/_fumo_da_edicao.py --url http://127.0.0.1:8080
    python scripts/_fumo_da_edicao.py --url … --wait 900 --bundle --shots ./shots

Why it exists (community edition, F2 — 2026-10-22)
--------------------------------------------------
The suites prove the engines without a database; nothing proved that the game,
as a whole, boots and lets someone in. This script talks to a RUNNING instance —
`python -m community.local` or `docker compose up` — over plain HTTP, and does
what a newcomer does on day one:

  1. waits for `/healthz` to say the game is ready — `"ready": true` in the body,
     not just the 200, which answers from the first second (the first boot runs every
     migration and seed on two worlds — be patient);
  2. opens `/login` and finds the LOCAL gate (the development login);
  3. signs in with a fresh name → `303 /app`, the session cookie (HttpOnly)
     and the CSRF cookie;
  4. loads `/app`, and with `--bundle` the compiled client, as the Docker image
     must serve it;
  5. creates the cultivator in the local world (`/api/miniapp/world/start`) and
     reads them back (`/api/miniapp/player`): the name, born in the local world;
  6. starts a light meditation (`/api/miniapp/meditate/start`) and sees it on
     the player;
  7. with `--shots DIR`, signs in with a real browser at 390×844 and 1440×900
     and saves what the player sees (`scripts/_olhar_cdp.mjs`; set `NV_CHROME`).

It needs the instance to run with `NIVRAEL_DEV_LOGIN=1` (the compose file and
`community.local` do). It never runs against a public server: the local login
refuses to open there, and so does this test.

Exit code 0 only when every step passed. The continuous integration runs it
against `docker compose up` (the `compose` job of `.github/workflows/ci.yml`).
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from run_tests import chrome_vivo, fechar_chrome  # noqa: E402 — one owner of "close the browser you opened"

PASS = 0
FAIL: list[str] = []


def check(nome: str, cond, detalhe="") -> bool:
    global PASS
    if cond:
        PASS += 1
        print(f"  ok  {nome}", flush=True)
        return True
    FAIL.append(f"{nome} — {detalhe}" if detalhe else nome)
    print(f"  XX  {nome}" + (f"  ({str(detalhe)[:400]})" if detalhe else ""), flush=True)
    return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Browserless:
    """Just enough of a browser: a cookie jar, no redirects followed."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), _NoRedirect)

    def get(self, path: str, timeout: float = 30):
        return self._open(urllib.request.Request(self.base + path, method="GET"), timeout)

    def post_form(self, path: str, campos: dict):
        dados = urllib.parse.urlencode(campos).encode()
        req = urllib.request.Request(self.base + path, data=dados, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        return self._open(req, 30)

    def api(self, path: str, payload: dict | None = None):
        csrf = self.cookie("nv_csrf") or ""
        req = urllib.request.Request(self.base + path, data=json.dumps(payload or {}).encode(),
                                     method="POST", headers={"Content-Type": "application/json",
                                                             "X-Nivrael-Session": csrf})
        status, headers, corpo = self._open(req, 60)
        try:
            return status, json.loads(corpo or b"{}")
        except ValueError:
            return status, {"_bruto": corpo[:300].decode("utf-8", "replace")}

    def cookie(self, nome: str) -> str | None:
        return next((c.value for c in self.jar if c.name == nome), None)

    def _open(self, req, timeout):
        try:
            r = self.op.open(req, timeout=timeout)
            return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:  # 3xx/4xx/5xx arrive here (no redirects followed)
            return e.code, e.headers, e.read()


def pronto(corpo: bytes) -> bool:
    """`/healthz` answers 200 ALWAYS — that is the process being alive, which is what
    the official servers' health check reads. Readiness is in the BODY: `"ready": true`
    only after every migration, every seed and the local world."""
    try:
        return json.loads(corpo or b"{}").get("ready") is True
    except (ValueError, AttributeError):
        return False


def esperar_pronto(nav: Browserless, segundos: int) -> bool:
    # ⚠️ Measured on 2026-10-25 (the emulated compose, before the first CI run):
    # waiting for the 200 alone walked in during the first boot — the local world did
    # not exist yet, the newcomer was born in `main`, and `main` had no tables yet.
    limite = time.time() + segundos
    ultimo = None
    while time.time() < limite:
        try:
            status, _h, corpo = nav.get("/healthz", timeout=10)
            ultimo = f"{status} {corpo[:60]!r}"
            if status == 200 and pronto(corpo):
                return True
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            ultimo = type(e).__name__
        time.sleep(3)
    print(f"     /healthz never said ready (last: {ultimo})")
    return False


def capturas(base: str, nome: str, destino: str) -> None:
    os.makedirs(destino, exist_ok=True)
    estava_vivo = chrome_vivo()
    trabalho = tempfile.mkdtemp(prefix="nv_fumo_")
    env = dict(os.environ, NV_OLHAR_OUT=os.path.join(trabalho, "olhar"))
    try:
        for w, h in ((390, 844), (1440, 900)):
            png = os.path.abspath(os.path.join(destino, f"app-{w}x{h}.png"))
            jogo = os.path.abspath(os.path.join(destino, f"game-{w}x{h}.png"))
            gate = os.path.abspath(os.path.join(destino, f"login-{w}x{h}.png"))
            entrar = ("(() => { const i = document.querySelector('input[name=nome]');"
                      " if (!i) return 'no local gate'; i.value = %s;"
                      " i.form.submit(); return 'submitted'; })()" % json.dumps(nome))
            # a 1.ª entrada abre o tutorial de boas-vindas; "Skip" fecha-o, para a
            # segunda captura mostrar o ecrã do jogo (se não houver tutorial, nada)
            saltar = "[...document.querySelectorAll('button')].find(b => /^skip$/i.test(b.textContent.trim()))"
            plano = {"url": base + "/login?lang=en", "w": w, "h": h, "boot": 2500, "passos": [
                {"shot": gate},
                {"eval": entrar, "nome": "sign in", "depois": 9000},
                {"eval": "location.pathname", "nome": "path"},
                {"shot": png},
                {"click": saltar, "nome": "skip", "depois": 1500},
                {"shot": jogo},
            ]}
            pp = os.path.join(trabalho, f"plano-{w}.json")
            with open(pp, "w", encoding="utf-8") as fh:
                json.dump(plano, fh)
            r = subprocess.run(["node", os.path.join(ROOT, "scripts", "_olhar_cdp.mjs"), pp],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               env=env, timeout=180)
            try:
                saida = json.loads(r.stdout)
            except ValueError:
                saida = {"saida": [], "erros": [(r.stdout + r.stderr)[-400:]]}
            passos = {p["passo"]: p["v"] for p in saida.get("saida", [])}
            check(f"{w}×{h}: the browser signs in through the local gate", passos.get("sign in") == "submitted",
                  passos.get("sign in") or saida.get("erros"))
            check(f"{w}×{h}: …and lands in the game (/app)", passos.get("path") == "/app", passos.get("path"))
            for arq in (png, jogo):
                check(f"{w}×{h}: the screen was saved ({os.path.basename(arq)})",
                      os.path.isfile(arq) and os.path.getsize(arq) > 10_000,
                      os.path.getsize(arq) if os.path.isfile(arq) else "missing")
            graves = [e for e in saida.get("erros", []) if "favicon" not in e]
            check(f"{w}×{h}: no script error on the way", not graves, graves[:3])
    finally:
        if not estava_vivo:
            fechar_chrome()
        shutil.rmtree(trabalho, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="the smoke test of a running instance")
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--wait", type=int, default=600, help="seconds to wait for /healthz")
    ap.add_argument("--bundle", action="store_true", help="the compiled client must be served")
    ap.add_argument("--shots", help="directory for the 390×844 and 1440×900 screenshots")
    a = ap.parse_args()

    nav = Browserless(a.url)
    # um nome de Dao: letra primeiro, só letras e algarismos, 3 a 20 (`validate_dao_name`)
    nome = "Fumo%04d" % random.randint(0, 9999)
    print(f"煙 the smoke test — {a.url} · sign-in name {nome!r}")

    if not check("the game says it is ready (/healthz: ready true)", esperar_pronto(nav, a.wait)):
        return 1

    status, _h, corpo = nav.get("/login")
    pagina = corpo.decode("utf-8", "replace")
    check("/login is the local gate (NIVRAEL_DEV_LOGIN=1)",
          status == 200 and 'name="nome"' in pagina and "本地之門" in pagina, status)

    status, headers, _c = nav.post_form("/dev/login", {"nome": nome, "lang": "en"})
    check("signing in answers 303 → /app", status == 303 and headers.get("Location") == "/app",
          (status, headers.get("Location") if headers else None))
    sessao = next((c for c in nav.jar if c.name == "nv_session"), None)
    check("…with the session cookie, HttpOnly", sessao is not None
          and (sessao.has_nonstandard_attr("HttpOnly") or sessao.has_nonstandard_attr("httponly")),
          [c.name for c in nav.jar])
    check("…and the CSRF cookie", bool(nav.cookie("nv_csrf")))

    status, _h, corpo = nav.get("/app")
    check("/app serves the client page (it asks for the client's code)",
          status == 200 and b"<html" in corpo.lower()
          and (b"dist/bundle.js" in corpo or b"components/ui.js" in corpo), status)
    if a.bundle:
        status, _h, corpo = nav.get("/miniapp/dist/bundle.js")
        check("the compiled client is served (/miniapp/dist/bundle.js)",
              status == 200 and len(corpo) > 100_000, (status, len(corpo)))

    status, criado = nav.api("/api/miniapp/world/start", {"dao_name": nome})
    check("the cultivator is born (/api/miniapp/world/start)", status == 200 and criado.get("ok") is True,
          (status, criado))
    check("…in the local world", criado.get("world_key") not in (None, "main"), criado.get("world_key"))
    status, jogador = nav.api("/api/miniapp/player")
    p = jogador.get("player") if isinstance(jogador.get("player"), dict) else jogador
    check("the player reads back with their name", status == 200 and p.get("dao_name") == nome,
          (status, {k: p.get(k) for k in ("dao_name", "realm", "error", "reason")}))

    status, med = nav.api("/api/miniapp/meditate/start", {"type": "light"})
    check("a light meditation starts", status == 200 and med.get("ok") is not False and "error" not in med,
          (status, med))
    status, jogador = nav.api("/api/miniapp/player")
    p = jogador.get("player") if isinstance(jogador.get("player"), dict) else jogador
    check("…and the player is meditating", (p.get("meditation_type") or p.get("meditation", {}) or {}) not in
          (None, "", {}), {k: p.get(k) for k in ("meditation_type", "meditation_end", "meditation")})

    if a.shots:
        capturas(a.url, nome, a.shots)

    print(f"\n{PASS} passed · {len(FAIL)} failed")
    if FAIL:
        print("\nFAILED:")
        for f in FAIL:
            print("  ·", f)
        return 1
    print("OK — the game boots, lets a newcomer in, gives them a cultivator and lets them meditate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
