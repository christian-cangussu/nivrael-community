# -*- coding: utf-8 -*-
"""眼 OLHAR — monta um plano e corre-o no Chrome headless por CDP.

Existe porque o `agent-browser` travou no lancador duas vezes seguidas (P6 e
P7). Serve o que a Lei 0 passo 3 pede: SERVIR e OLHAR, e medir o que se ve'.

    python scripts/_olhar.py <porta> <w> <h> <prefixo> <passos...>

Passos:
    shot | inteira              captura (o ecra / a pagina inteira)
    clica:<texto>               toca no botao cujo texto (ou de um filho) e' esse
    sel:<css>                   toca no primeiro elemento do seletor
    espera:<ms>
    m:<css da caixa>|<css do comando>
                                mede: o topo do comando RELATIVO a' caixa (a
                                rolagem e' de um contentor interno — medir contra
                                a janela deu um falso "o comando mexeu 69px") e
                                o estado de cada `.explica`
    eval:<js>  |  js:<ficheiro>  corre JS na pagina e devolve o valor
    vp:<w>x<h>                  muda a JANELA sem recarregar (05/10: medir a mesma
                                cena a 320/360/390/412 sem refazer os toques)
    hash                        SHA-256 do DOM da raiz, sem digitos (relogios) —
                                a OFF-identidade: igual antes/depois

As capturas vao para NV_OLHAR_OUT (defeito: %TEMP%/nivrael_olhar).

Exemplo (o arnes: `python scripts/_dev_serve_miniapp.py 8911`):
    python scripts/_olhar.py 8911 390 844 chegada "m:.chegada-cena|.chegada-agir > div > button" shot
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("NV_OLHAR_OUT") or os.path.join(os.environ.get("TEMP", "/tmp"), "nivrael_olhar")
os.makedirs(OUT, exist_ok=True)

MEDIR = r"""(() => {
  const box = document.querySelector(__BOX__);
  if (!box) return JSON.stringify({ erro: 'SEM ' + __BOX__ });
  const cmd = box.querySelector(__CMD__) || document.querySelector(__CMD__);
  const base = box.getBoundingClientRect().top;
  const y = el => el ? Math.round(el.getBoundingClientRect().top - base) : null;
  const vis = el => el ? getComputedStyle(el).visibility : null;
  return JSON.stringify({
    cmdTop: y(cmd), cmd: cmd ? cmd.innerText.slice(0, 40) : null,
    explicas: [...document.querySelectorAll('.explica')].map(ex => ({
      h: Math.round(ex.getBoundingClientRect().height), top: y(ex),
      frase: vis(ex.children[0]), ajuda: vis(ex.children[1]),
      botoes: [...ex.querySelectorAll('button')].map(b => vis(b) === 'visible' ? b.innerText : '-'),
    })),
  });
})()"""

HASH = r"""(async () => {
  const html = document.getElementById('root').innerHTML.replace(/[0-9]/g, '');
  const dig = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(html));
  return [...new Uint8Array(dig)].map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16)
         + ' len=' + html.length;
})()"""

CLICA = ("((T) => [...document.querySelectorAll('button,[role=tab],summary,a')]"
         ".filter(b => getComputedStyle(b).visibility === 'visible' && b.getClientRects().length)"
         ".find(b => (b.innerText||'').trim().toLowerCase() === T"
         " || [...b.querySelectorAll('*')].some(c => (c.innerText||'').trim().toLowerCase() === T)))(%s)")


def plano(porta, w, h, pref, args):
    passos, n = [], 0
    for a in args:
        if a in ("shot", "inteira"):
            n += 1
            passos.append({"shot": os.path.join(OUT, "%s_%d.png" % (pref, n)), "inteira": a == "inteira"})
        elif a.startswith("clica:"):
            passos.append({"click": CLICA % json.dumps(a[6:].lower()), "nome": "clica " + a[6:], "depois": 1500})
        elif a.startswith("sel:"):
            passos.append({"click": "document.querySelector(%s)" % json.dumps(a[4:]),
                           "nome": "sel " + a[4:], "depois": 1500})
        elif a.startswith("espera:"):
            passos.append({"wait": int(a[7:])})
        elif a.startswith("vp:"):
            vw, vh = a[3:].lower().split("x", 1)
            passos.append({"viewport": [int(vw), int(vh)], "nome": "vp " + a[3:]})
        elif a.startswith("m:"):
            box, cmd = a[2:].split("|", 1)
            passos.append({"eval": MEDIR.replace("__BOX__", json.dumps(box)).replace("__CMD__", json.dumps(cmd)),
                           "nome": "m"})
        elif a == "hash":
            passos.append({"eval": HASH, "nome": "hash"})
        elif a.startswith("eval:"):
            passos.append({"eval": a[5:], "nome": "eval"})
        elif a.startswith("js:"):
            passos.append({"eval": open(a[3:], encoding="utf-8").read(), "nome": a[3:]})
        else:
            raise SystemExit("passo desconhecido: " + a)
    return {"url": "http://127.0.0.1:%s/app" % porta, "w": w, "h": h, "passos": passos}


if __name__ == "__main__":
    if len(sys.argv) < 5:
        raise SystemExit(__doc__)
    pl = plano(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5:])
    pp = os.path.join(OUT, "plano_%s.json" % sys.argv[4])
    json.dump(pl, open(pp, "w", encoding="utf-8"))
    r = subprocess.run(["node", os.path.join(ROOT, "scripts", "_olhar_cdp.mjs"), pp],
                       capture_output=True, text=True, encoding="utf-8", timeout=300)
    try:
        d = json.loads(r.stdout)
        for s in d["saida"]:
            print("%-14s %s" % (s["passo"][:14], s["v"]))
        print("erros da pagina:", d["erros"] or "nenhum")
    except Exception:
        print(r.stdout[-4000:])
    if r.stderr.strip():
        print("STDERR:", r.stderr[-1500:])
