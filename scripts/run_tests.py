# -*- coding: utf-8 -*-
"""Run every check of the community edition — the one command before a pull request.

    python scripts/run_tests.py            # everything
    python scripts/run_tests.py mv9 tec    # only the suites whose name contains a word

What it runs, in this order:
  1. the game suites (`scripts/_test_*.py`) — standalone, no database;
     the four `_test_*.js` are helpers that `_test_web_c_superficies.py` feeds
     with the engine's cases, so they run inside it, not on their own;
  2. the community edition suite (`scripts/_test_edicao_comunitaria.py`);
  3. the audits — Python 3.11 syntax and ORM columns that do not exist;
  4. the documentation guard (`scripts/_verifica_documentacao.py`);
  5. the publication guard (`scripts/_verifica_copia_publica.py`).

Before it starts it checks what the full run needs besides Python — a Node
with the built-in WebSocket, `esbuild` from `cd website && npm ci`, and a
Chrome for the browser checks — and says how to get what is missing. The
continuous integration (`.github/workflows/ci.yml`) runs exactly this command.

Exit code 0 only when everything is green.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMUNIDADE = "scripts/_test_edicao_comunitaria.py"
AUDITORIAS = ("scripts/_audit_py311.py", "scripts/_audit_orm_colunas.py")
DOCUMENTACAO = "scripts/_verifica_documentacao.py"
GUARDA = "scripts/_verifica_copia_publica.py"
CDP_PORT = 9333  # the port scripts/_olhar_cdp.mjs drives its headless Chrome on


def chrome_vivo() -> bool:
    """Is a headless Chrome answering on the driver's port?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2):
            return True
    except Exception:
        return False


def fechar_chrome() -> None:
    """Closes the headless Chrome on the driver's port (Browser.close over CDP).

    scripts/_olhar_cdp.mjs starts it detached and leaves it running, so every run
    of the browser checks used to leave one behind. Whoever opened it closes it:
    this runner (and scripts/_fumo_da_edicao.py) call this only for a browser that
    was not there when they started."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2) as r:
            ws = json.loads(r.read())["webSocketDebuggerUrl"]
    except Exception:
        return
    node = shutil.which("node")
    if not node:
        return
    js = ("const ws=new WebSocket(process.argv[1]);ws.onopen=()=>{ws.send(JSON.stringify({id:1,"
          "method:'Browser.close'}));setTimeout(()=>process.exit(0),800)};ws.onerror=()=>process.exit(0);")
    subprocess.run([node, "-e", js, ws], capture_output=True, timeout=20)


def _chrome() -> str | None:
    """The browser scripts/_olhar_cdp.mjs will drive: NV_CHROME, or agent-browser's."""
    if os.environ.get("NV_CHROME"):
        return os.environ["NV_CHROME"] if os.path.exists(os.environ["NV_CHROME"]) else None
    base = os.path.join(os.path.expanduser("~"), ".agent-browser", "browsers")
    exe = "chrome.exe" if sys.platform == "win32" else "chrome"
    for d in sorted(glob.glob(os.path.join(base, "chrome-*")), reverse=True):
        if os.path.isfile(os.path.join(d, exe)):
            return os.path.join(d, exe)
    return None


def preflight() -> list[str]:
    """What the full run needs besides Python — each missing piece with its fix."""
    faltas = []
    node = shutil.which("node")
    if not node:
        faltas.append("Node is not on the PATH — install a recent Node (the CI uses 24)")
    else:
        r = subprocess.run([node, "-e", "process.stdout.write(typeof WebSocket)"],
                           capture_output=True, text=True)
        if r.stdout.strip() != "function":
            faltas.append(f"this Node has no built-in WebSocket ({subprocess.run([node, '--version'], capture_output=True, text=True).stdout.strip()})"
                          " — the browser driver needs a newer one (the CI uses 24)")
    if not os.path.isfile(os.path.join(ROOT, "website", "node_modules", "esbuild", "package.json")):
        faltas.append("esbuild is missing — run `cd website && npm ci` once "
                      "(scripts/_test_cena_cabe.py compiles the client with it)")
    if not _chrome():
        faltas.append("no Chrome found — set NV_CHROME to a Chrome or Chromium executable "
                      "(scripts/_test_cena_cabe.py measures the duel in a headless browser)")
    return faltas


def main() -> int:
    filtros = [a.lower() for a in sys.argv[1:]]
    suites = sorted(os.path.relpath(p, ROOT).replace(os.sep, "/")
                    for p in glob.glob(os.path.join(ROOT, "scripts", "_test_*.py")))
    suites = [s for s in suites if s != COMUNIDADE]
    alvos = suites + [COMUNIDADE] + list(AUDITORIAS) + [DOCUMENTACAO, GUARDA]
    if filtros:
        alvos = [a for a in alvos if any(f in a.lower() for f in filtros)]

    faltas = preflight()
    for f in faltas:
        print(f"⚠️  {f}", flush=True)
    if faltas:
        print("   (the suites that need it will fail; everything else still runs)\n", flush=True)

    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    falhas = []
    t_total = time.time()
    chrome_antes = chrome_vivo()
    try:
        for rel in alvos:
            t0 = time.time()
            r = subprocess.run([sys.executable, "-X", "utf8", rel], cwd=ROOT, env=env,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            dt = time.time() - t0
            ok = r.returncode == 0
            ultima = next((l for l in reversed((r.stdout or "").splitlines()) if l.strip()), "")
            print(f"{'✅' if ok else '❌'} {rel:<44} {dt:6.1f}s  {ultima.strip()[:90]}", flush=True)
            if not ok:
                falhas.append((rel, (r.stdout or "")[-2500:] + (r.stderr or "")[-2500:]))
    finally:
        # the browser checks leave their headless Chrome running — close the one this run opened
        if not chrome_antes and chrome_vivo():
            fechar_chrome()

    print(f"\n{len(alvos) - len(falhas)}/{len(alvos)} green in {time.time() - t_total:.0f}s")
    for rel, saida in falhas:
        print(f"\n──── {rel} ────\n{saida.strip()}")
    if falhas and faltas:
        print("\nMissing before the run, and probably why:")
        for f in faltas:
            print(f"  ⚠️  {f}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
