# -*- coding: utf-8 -*-
"""⚔️ A CENA CABE NO ECRÃ — a guarda de GEOMETRIA do duelo (report do [jogador], 03/10/2026).

    python -X utf8 scripts/_test_cena_cabe.py

*"@saint_nivrael, bug: in PvE arena, popup of combat shows opponent's hp out of
bound on screen."* — e não era a primeira vez. O comentário da 2.2, na própria
cena, já dizia: *"1070 guardas verdes, e o transbordo estava a um screenshot de
distância"*. Um transbordo é GEOMETRIA, e nenhuma leitura de ficheiro o vê: as
guardas da casa liam o CSS e ficavam verdes enquanto o número do adversário
saía 20px pelo lado direito do telemóvel.

Esta suite mede o que o jogador vê:

  1. compila o cliente ACTUAL (`miniapp/components`) numa pasta temporária —
     nunca toca no `miniapp/dist` da árvore, para a bateria de sabotagem a poder
     correr com o código sabotado sem deixar um bundle partido para trás;
  2. serve-o no arnês (`NV_BUNDLE`) com as flags do Beta — a chave-mestra
     ligada, porque a cena só existe com ela — e o duelo encenado pelo
     `NV_DUELO_HP` com números de PRODUÇÃO;
  3. abre o duelo como um jogador (Combate → Caçada → dificuldade → Lutar) num
     Chrome headless (`scripts/_olhar_cdp.mjs`) e mede, a cada largura, CADA
     rectângulo de texto (por `Range`, o glifo e não a caixa) e de barra do
     confronto contra a sua coluna e contra o ecrã.

Os casos (os números saem de `tools/db_readonly_duelo_hp_1005.py`):
  · o REPORT — 557.790.433.292 contra 1.212.935.443, a arena, em pt;
  · o PIOR   — 13 dígitos dos dois lados (o maior HP do Beta), a origem com a
               palavra mais larga do vão ("Exploration"), em en.

Afirma, a cada largura: nada sai da coluna nem do ecrã; nenhuma palavra do vão
se parte a meio; NENHUM NÚMERO PARTE — cada vida e cada máximo ficam inteiros
numa linha, a encolher se for preciso (a regra da §28: `158.977.287.8` / `26`
lê-se como outro número); onde cabe (≥390px), a vida fica no tamanho inteiro (o
vão encolhe PRIMEIRO — a regra que a grelha desrespeitava); e o vão diz a origem
do duelo. E o caminho de RESERVA (um browser sem container queries, simulado):
nada sai, e o número quebra só entre grupos de milhar, nunca a meio de um.

⚠️ Sem Chrome ou sem node a suite FALHA — não salta. Uma guarda de geometria que
fica verde por não ter medido nada é a guarda que já falhou duas vezes nesta tela.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PASS = 0
FAIL: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {detail}")
        print(f"  FAIL: {name} {detail}")


# As 40 flags do Nivrael Beta, lidas do registo dos servidores a 05/10/2026
# (`tools/db_readonly_duelo_hp_1005.py`, secção D). A chave-mestra (`a_obra`,
# `cultivador_jogavel`) é a que importa: sem ela a cena nem se desenha.
FLAGS_BETA = (
    "a_obra,arena_encontro_rapido,biblioteca_seitas,breakthrough_trials,caravana,"
    "cartas,cena_cultivo,cidades,combate_unificado,corpo_profundo,cultivador,"
    "cultivador_jogavel,cultivo_corpo_r0,dungeons_regionais,escassez_scrolls,"
    "estados_regionais,estantes_seladas,forbidden_path,formacoes,ftue_espinha,"
    "golpe_padrao,horta,iconografia,item_vivo,jianghu,legacy_caves,manifest_canary,"
    "marca_do_tracado,masmorra_unica,o_mapa,pele_quente,profissoes,progressao_visivel,"
    "quests_vivas,racas,reputacao_rival,superficie_desktop,tempo_do_ceu,"
    "tiandao_director,ui_v2"
)

# (nome, NV_DUELO_HP, origem, chave do nome da origem, língua, hp jogador, hp adversário,
#  larguras de telemóvel)
CASOS = [
    ("report", "relato", "arena_npc_fallback", "cena_fonte_arena", "pt",
     557790433292, 1212935443, (390, 320, 360, 375, 412)),
    ("pior", "max", "exploration", "cena_fonte_exploracao", "en",
     1146050083754, 1124861821452, (390, 320, 360, 375, 412, 430)),
]
SEP = {"pt": ".", "en": ",", "es": "."}
LINHA_UNICA_DESDE = 390       # a partir daqui cada vida cabe numa linha

# ── a medição (corre NA página) ─────────────────────────────────────────────
MEDE = r"""(() => {
  const vw = document.documentElement.clientWidth;
  const conf = document.querySelector('.cena-confronto');
  if (!conf) return JSON.stringify({ erro: 'sem .cena-confronto', vw });
  const cols = [...conf.querySelectorAll('.cena-lado, .cena-vao')];
  const caixa = el => { const b = el.getBoundingClientRect(); return { l: b.left, r: b.right }; };
  const TOL = 1, confB = caixa(conf), fora = [];
  let textos = 0, caixas = 0;
  const verifica = (rc, col, quem) => {
    const c = caixa(col);
    if (rc.left < c.l - TOL || rc.right > c.r + TOL || rc.left < -TOL || rc.right > vw + TOL
        || rc.left < confB.l - TOL || rc.right > confB.r + TOL)
      fora.push(quem.slice(0, 32) + ' [' + Math.round(rc.left) + '..' + Math.round(rc.right)
                + '] fora de [' + Math.round(c.l) + '..' + Math.round(c.r) + '] vw=' + vw);
  };
  for (const col of cols) {
    const tw = document.createTreeWalker(col, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = tw.nextNode())) {
      if (!n.textContent.trim()) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const rc of rg.getClientRects()) if (rc.width > 0) { textos++; verifica(rc, col, n.textContent.trim()); }
    }
    for (const el of col.querySelectorAll('.cena-faixa-trilho, .cena-faixa-trilho > i, .cena-emblema')) {
      caixas++; verifica(el.getBoundingClientRect(), col, String(el.className || el.tagName));
    }
  }
  const partidas = [];
  const aMeio = (node, re) => {
    const s = node.textContent, rg = document.createRange();
    let pt = null, pc = null;
    for (let i = 0; i < s.length; i++) {
      rg.setStart(node, i); rg.setEnd(node, i + 1);
      const rs = rg.getClientRects();
      if (!rs.length) { pc = s[i]; continue; }
      const top = Math.round(rs[0].top);
      if (pt !== null && top - pt > 2 && re.test(pc) && re.test(s[i])) return true;
      pt = top; pc = s[i];
    }
    return false;
  };
  const varre = (sel, re) => {
    for (const el of conf.querySelectorAll(sel)) {
      const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let n;
      while ((n = tw.nextNode()))
        if (n.textContent.trim() && aMeio(n, re)) partidas.push(sel + ' «' + n.textContent.trim().slice(0, 24) + '»');
    }
  };
  varre('.cena-vao', /[\p{L}\p{N}]/u);
  varre('.cena-faixa-val, .cena-faixa-max', /[0-9]/);
  // as LINHAS de uma unidade contam-se pelos rectângulos de TEXTO e só deles:
  // um `inline-block` lá dentro (o número do máximo) entra no Range com a
  // caixa dele, de topo diferente do texto, e contava uma linha que não existe.
  const linhas = el => {
    if (!el) return null;
    const tops = [];
    const tw = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = tw.nextNode())) {
      if (!n.textContent.trim()) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const r of rg.getClientRects()) if (r.width > 0) tops.push(r.top);
    }
    tops.sort((a, b) => a - b);
    let k = 0, ult = null;
    for (const t of tops) { if (ult === null || t - ult > 3) k++; ult = t; }
    return k;
  };
  const val = q => { const l = conf.querySelector('.cena-lado--' + q); return l && l.querySelector('.cena-faixa-val'); };
  return JSON.stringify({
    vw, colunas: cols.length, textos, caixas, fora, partidas,
    n_vals: conf.querySelectorAll('.cena-faixa-val').length,
    hp_voce: val('voce') ? val('voce').textContent : null,
    hp_opp: val('opp') ? val('opp').textContent : null,
    linhas_voce: linhas(val('voce')), linhas_opp: linhas(val('opp')),
    linhas_max: [...conf.querySelectorAll('.cena-faixa-max')].map(linhas),
    linhas_maxn: [...conf.querySelectorAll('.cena-faixa-maxn')].map(linhas),
    fs_hp: [val('voce'), val('opp')].map(e => e ? getComputedStyle(e).fontSize : null),
    fonte: (conf.querySelector('.cena-vao-fonte') || {}).textContent || null,
  });
})()"""


# O caminho de RESERVA: um browser sem container queries não aplica o ajuste
# (está dentro de um @supports) e o número fica no tamanho inteiro — aí, e só
# aí, quebra entre grupos de milhar (os <wbr>). Simula-se desligando o ajuste.
SEM_CQ = r"""(() => {
  const s = document.createElement('style');
  s.textContent = '.cena-duelo .cena-faixa{container-type:normal!important}'
    + '.cena-duelo .cena-faixa-val{font-size:12px!important}'
    + '.cena-duelo .cena-faixa-max{font-size:9.5px!important}';
  document.head.appendChild(s);
  return 'ok';
})()"""


def _clica(js_achar: str) -> str:
    return ("(() => { const el = (%s); if (!el) return 'NAO ACHEI'; el.scrollIntoView({block:'center'});"
            " el.click(); return 'ok'; })()" % js_achar)


def _navega(i18n: dict) -> list:
    """Combate → Caçada → a dificuldade mais fácil → Lutar, pelos TEXTOS da
    língua (o telemóvel tem a barra de ícones com aria-label; o PC o trilho de
    texto). Cada passo devolve 'ok' — e a suite exige-o."""
    combate = json.dumps(i18n["hub_combate"])
    caca = json.dumps(i18n["combat_seg_npc"])
    facil = json.dumps(i18n["combat_npc_difficulty_easy"])
    lutar = json.dumps(i18n["combat_npc_btn_fight"])
    vis = "x.getClientRects().length && getComputedStyle(x).visibility === 'visible'"
    return [
        {"click": None, "eval": _clica(
            "document.querySelector('[aria-label=' + JSON.stringify(%s) + ']') || "
            "[...document.querySelectorAll('button,a,[role=tab],[role=button]')]"
            ".filter(x => %s && (x.innerText || '').trim() === %s).pop()" % (combate, vis, combate)),
         "nome": "nav combate", "depois": 1800},
        {"eval": _clica("[...document.querySelectorAll('button,[role=tab]')]"
                        ".find(x => %s && (x.innerText || '').indexOf(%s) >= 0)" % (vis, caca)),
         "nome": "nav caca", "depois": 1200},
        {"eval": _clica("[...document.querySelectorAll('button')]"
                        ".find(x => %s && (x.innerText || '').indexOf(%s) >= 0)" % (vis, facil)),
         "nome": "nav facil", "depois": 800},
        {"eval": _clica("[...document.querySelectorAll('button')]"
                        ".find(x => %s && !x.disabled && (x.innerText || '').indexOf(%s) >= 0)" % (vis, lutar)),
         "nome": "nav lutar", "depois": 2800},
    ]


def _porta_livre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _espera(porta: int, seg: float = 20.0) -> bool:
    fim = time.time() + seg
    while time.time() < fim:
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/app" % porta, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def _corre_plano(tmp: str, nome: str, porta: int, w: int, h: int, passos: list) -> dict:
    plano = {"url": "http://127.0.0.1:%d/app" % porta, "w": w, "h": h, "boot": 3500,
             "passos": [{k: v for k, v in p.items() if v is not None} for p in passos]}
    pp = os.path.join(tmp, "plano_%s.json" % nome)
    with io.open(pp, "w", encoding="utf-8") as fh:
        json.dump(plano, fh)
    env = dict(os.environ, NV_OLHAR_OUT=os.path.join(tmp, "olhar"))
    r = subprocess.run(["node", os.path.join(ROOT, "scripts", "_olhar_cdp.mjs"), pp],
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=240)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"saida": [], "erros": ["o driver nao respondeu: " + (r.stdout[-400:] + r.stderr[-400:])]}


def _fmt(n: int, lang: str) -> str:
    return "{:,}".format(n).replace(",", SEP[lang])


def main() -> int:
    print("=== ⚔️ a cena do duelo cabe no ecrã (report do [jogador], 03/10) ===")
    tmp = tempfile.mkdtemp(prefix="nv_cena_cabe_")
    procs = []
    try:
        # 1. o cliente ACTUAL, compilado à parte
        comp = os.path.join(tmp, "miniapp", "components")
        os.makedirs(comp)
        for f in ("ui.js", "tabs.js", "app.js"):
            shutil.copy2(os.path.join(ROOT, "miniapp", "components", f), comp)
        b = subprocess.run(["node", os.path.join(ROOT, "scripts", "build_miniapp.mjs"),
                            os.path.join(tmp, "miniapp")],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        bundle = os.path.join(tmp, "miniapp", "dist", "bundle.js")
        check("o cliente actual compila", b.returncode == 0 and os.path.isfile(bundle),
              (b.stdout + b.stderr)[-300:])
        if FAIL:
            return 1

        for nome, hp, origem, chave, lang, hp_v, hp_o, telefones in CASOS:
            i18n = json.load(io.open(os.path.join(ROOT, "miniapp", "i18n", lang + ".json"),
                                     encoding="utf-8"))
            porta = _porta_livre()
            env = dict(os.environ, NV_FEATURES=FLAGS_BETA, NV_DUELO_HP=hp,
                       NV_DUELO_ORIGEM=origem, NV_LANG=lang, NV_BUNDLE=bundle)
            p = subprocess.Popen([sys.executable, "-X", "utf8",
                                  os.path.join(ROOT, "scripts", "_dev_serve_miniapp.py"), str(porta)],
                                 env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            procs.append(p)
            check("%s: o arnês responde" % nome, _espera(porta))
            # ANTI-GUARDA: o arnês serve o bundle compilado AGORA, byte a byte —
            # e não o `miniapp/dist` da árvore (a lição de 29/09: comparar código
            # velho com código velho e chamar-lhe olhar).
            try:
                with urllib.request.urlopen("http://127.0.0.1:%d/miniapp/dist/bundle.js" % porta,
                                            timeout=10) as r:
                    servido = r.read()
            except Exception as e:
                servido = repr(e).encode()
            with open(bundle, "rb") as fh:
                check("%s: ANTI-GUARDA o arnês serve o bundle compilado agora" % nome,
                      servido == fh.read(), "%d bytes servidos" % len(servido))
            esperado_v, esperado_o = _fmt(hp_v, lang), _fmt(hp_o, lang)
            fonte = i18n.get(chave)

            # o telemóvel: abre-se a 390 e mede-se em cada largura
            passos = _navega(i18n)
            for w in telefones:
                if w != telefones[0]:
                    passos.append({"viewport": [w, 844], "nome": "vp", "depois": 700})
                passos.append({"eval": MEDE, "nome": "mede %d" % w})
            # e o caminho de reserva, na largura mais estreita
            passos += [{"eval": SEM_CQ, "nome": "semcq"},
                       {"viewport": [320, 844], "nome": "vp", "depois": 700},
                       {"eval": MEDE, "nome": "reserva 320"}]
            # o PC: navegação própria (o trilho lateral), a 1440
            for ecra, larguras, ps in (("telemovel", telefones, passos),
                                       ("pc", (1440,), _navega(i18n) + [{"eval": MEDE, "nome": "mede 1440"}])):
                w0 = larguras[0]
                out = _corre_plano(tmp, "%s_%s" % (nome, ecra), porta, w0, 844 if w0 < 800 else 900, ps)
                saida = out.get("saida") or []
                navs = [s["v"] for s in saida if str(s.get("passo", "")).startswith("nav")]
                check("%s/%s: a navegação chega ao duelo (4 passos)" % (nome, ecra),
                      navs == ["ok"] * 4, str(navs) + " " + str(out.get("erros"))[:300])
                check("%s/%s: a página não rebenta" % (nome, ecra), not out.get("erros"),
                      str(out.get("erros"))[:300])
                medidas = [s["v"] for s in saida if str(s.get("passo", "")).startswith("mede")]
                check("%s/%s: mediu %d larguras" % (nome, ecra, len(larguras)),
                      len(medidas) == len(larguras), str(len(medidas)))
                for w, raw in zip(larguras, medidas):
                    try:
                        m = json.loads(raw)
                    except Exception:
                        check("%s/%d: a medição devolve JSON" % (nome, w), False, str(raw)[:200])
                        continue
                    tag = "%s/%d" % (nome, w)
                    # ANTI-GUARDA: mediu a cena certa, com os números certos
                    check(tag + ": ANTI-GUARDA a cena está aberta (3 colunas)",
                          m.get("colunas") == 3, str(m.get("erro") or m.get("colunas")))
                    check(tag + ": ANTI-GUARDA havia texto e barras para medir",
                          (m.get("textos") or 0) >= 20 and (m.get("caixas") or 0) >= 6,
                          "%s textos · %s caixas" % (m.get("textos"), m.get("caixas")))
                    check(tag + ": ANTI-GUARDA os números de produção chegaram",
                          m.get("hp_voce") == esperado_v and m.get("hp_opp") == esperado_o,
                          "%r %r" % (m.get("hp_voce"), m.get("hp_opp")))
                    check(tag + ": a janela tem a largura pedida", m.get("vw") == w, str(m.get("vw")))
                    # o que o jogador vê
                    check(tag + ": nada sai da coluna nem do ecrã", not m.get("fora"),
                          str(m.get("fora"))[:400])
                    check(tag + ": nenhuma palavra nem grupo de milhar partido a meio",
                          not m.get("partidas"), str(m.get("partidas"))[:300])
                    # 🔴 O NÚMERO NÃO PARTE, em largura NENHUMA (a regra da §28 de
                    # `_test_web_c_superficies`: `158.977.287.8` / `26` lê-se como
                    # outro número). Num browser com container queries ele
                    # encolhe para caber — cada número inteiro numa linha só.
                    check(tag + ": cada vida fica inteira numa linha",
                          m.get("linhas_voce") == 1 and m.get("linhas_opp") == 1,
                          "voce %s · opp %s" % (m.get("linhas_voce"), m.get("linhas_opp")))
                    check(tag + ": o número de cada máximo fica inteiro numa linha",
                          m.get("linhas_maxn") and all(x == 1 for x in m["linhas_maxn"]),
                          str(m.get("linhas_maxn")))
                    if w >= 360:
                        # "de máx" é UMA unidade: desce inteira ou não desce —
                        # nunca "1.212.935.443 de 1." / "212.935.443"
                        check(tag + ": cada 'de máx' fica inteiro numa linha",
                              m.get("linhas_max") and all(x == 1 for x in m["linhas_max"]),
                              str(m.get("linhas_max")))
                    if w >= LINHA_UNICA_DESDE:
                        # o vão encolhe PRIMEIRO; o número só encolhe onde não há
                        # mais de onde tirar
                        check(tag + ": onde cabe, a vida fica no tamanho inteiro (12px)",
                              m.get("fs_hp") == ["12px", "12px"], str(m.get("fs_hp")))
                if ecra == "telemovel":
                    res = [s["v"] for s in saida if str(s.get("passo", "")).startswith("reserva")]
                    try:
                        mr = json.loads(res[0]) if res else {}
                    except Exception:
                        mr = {}
                    tag = "%s/320 sem container queries" % nome
                    check(tag + ": ANTI-GUARDA o tamanho ficou mesmo inteiro (o ajuste desligado)",
                          mr.get("fs_hp") == ["12px", "12px"], str(mr.get("fs_hp")))
                    check(tag + ": nada sai da coluna nem do ecrã", mr.get("colunas") == 3
                          and not mr.get("fora"), str(mr.get("fora"))[:300])
                    check(tag + ": quebra só entre grupos de milhar, nunca a meio de um",
                          not mr.get("partidas"), str(mr.get("partidas"))[:300])
                    check(tag + ": o vão diz a origem (%s)" % fonte, m.get("fonte") == fonte,
                          repr(m.get("fonte")))
    finally:
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{PASS} passed · {len(FAIL)} failed")
    if FAIL:
        print("\nFALHAS:")
        for f in FAIL:
            print("  ·", f)
        return 1
    print(f"OK — {PASS} asserts. A vida dos dois lados cabe no ecrã, inteira, em "
          "todas as larguras; o vão diz de onde vem a luta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
