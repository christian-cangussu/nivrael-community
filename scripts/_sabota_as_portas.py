# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM da §29 — uma guarda que nao morde nao guarda.

Mesmo contrato das outras (`_sabota_a_cena`, `_sabota_a_macaneta`, ...): cada
entrada estraga UMA coisa no codigo de producao, corre a suite, e exige que ela
fique VERMELHA **a dizer o que e'** — nunca a rebentar, e nunca por um motivo
diferente do esperado.

Os quatro grupos de ataque:

  O DONO NO SERVIDOR — um endpoint a voltar a ter a sua propria comparacao, o
      chat a voltar a ter o seu 3, a porta do Corpo a esquecer uma camada, um
      gate que rebenta a sair ABERTO.

  O PAYLOAD — o `/player` a mandar as portas sem a onda, a chave a ficar
      sempre presente (o `main` deixava de ser byte-identico), o espelho da
      chave-mestra a divergir do `ondaCultOn()`.

  O CLIENTE — a incerta a sair aberta, o marco a desaparecer, a onda OFF a
      deixar de ser o ecra de hoje, um limiar escrito no cliente.

  OS SITIOS — a faixa e o Ceu a desenharem sem perguntar, a maçaneta do
      primeiro ecra a sumir, a consulta a sair do VOLTAR, o cadeado a virar
      emoji, um `kind` novo sem caminho, e o mais importante: **um gate novo a
      nascer no Mercado**, que a guarda tem de apanhar SOZINHA na cena da
      Caverna que o mostraria aberto — sem ninguem lhe ter dito onde olhar.

Uso:  python scripts/_sabota_as_portas.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
APP = os.path.join(ROOT, "miniapp", "components", "app.js")
WS = os.path.join(ROOT, "core", "webserver.py")
PORTAS = os.path.join(ROOT, "core", "portas.py")
CHAT = os.path.join(ROOT, "handlers", "faction.py")
SUITE = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")
CR = chr(13) + chr(10)

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── O DONO NO SERVIDOR ────────────────────────────────────────────────
    # 🔴 A forma exacta do defeito de antes: o mesmo 3, comparado a' mao. O
    # valor e' IGUAL — nenhum teste de comportamento o apanharia hoje. O que a
    # guarda tem de ver e' o segundo dono a nascer.
    ("a Faccao volta a comparar o reino a' mao", WS,
     '    locked = porta_faccao(player)["open"] is not True\n',
     "    locked = realm < FACTION_MIN_REALM\n",
     "`_build_faction_payload` decide"),
    ("a escolha de Faccao volta a comparar a' mao", WS,
     '        if porta_faccao(player)["open"] is not True:\n',
     "        if int(player.realm or 0) < FACTION_MIN_REALM:\n",
     "`api_faction_pick` decide"),
    ("a Celestial volta a comparar a' mao", WS,
     '        unlocked = porta_celestial(player)["open"] is True\n',
     "        unlocked = realm >= MAHAYANA_REALM\n",
     "`api_celestial_status` decide"),
    ("o chat volta a ter o SEU 3", CHAT,
     "ITEMS_PER_PAGE = 5\n",
     "ITEMS_PER_PAGE = 5\nMIN_REALM_FACTION = 3\n",
     "escrito UMA vez"),
    ("a porta do Corpo esquece o Refino Mortal", PORTAS,
     '    if flag("cultivo_corpo_r0"):\n        return {"open": True}\n',
     "",
     "bate com o motor"),
    ("um gate que rebenta sai ABERTO", PORTAS,
     '            out[tab] = {"open": None}',
     '            out[tab] = {"open": True}',
     "rebenta"),

    # ── O PAYLOAD ─────────────────────────────────────────────────────────
    ("o /player manda as portas SEM a onda", WS,
     "            if _onda_on():\n                _nav_gates = portas_do_jogador(player)",
     "            if True:\n                _nav_gates = portas_do_jogador(player)",
     "so' com a onda ON"),
    ("a chave fica SEMPRE presente (main deixa de ser byte-identico)", WS,
     '            **({"nav_gates": _nav_gates} if _nav_gates is not None else {}),',
     '            "nav_gates": _nav_gates,',
     "CONDICIONAL"),
    ("o espelho da chave-mestra diverge do ondaCultOn()", PORTAS,
     'ONDA_FLAGS = ("a_obra", "cultivador_jogavel")',
     'ONDA_FLAGS = ("a_obra",)',
     "MESMAS chaves"),

    # ── O CLIENTE ─────────────────────────────────────────────────────────
    ("a porta INCERTA sai aberta (a opcao (c) por falha)", UI,
     '      return { estado: "incerta" };\n    }\n\n    // A regra do marco',
     '      return { estado: "aberta" };\n    }\n\n    // A regra do marco',
     "sob node"),
    ("o marco desaparece: todas as trancadas a' vista", UI,
     "|| x.porta.precisa === marco ||",
     "|| true ||",
     "sob node"),
    ("com a onda OFF as portas continuam a trancar", UI,
     '      if (!portasOn(player)) return { estado: "aberta" };',
     '      if (!player || !player.nav_gates) return { estado: "aberta" };',
     "sob node"),
    ("um limiar de reino nasce no cliente", UI,
     "      const largura = recolhida ? 64 : 216;\n",
     "      const largura = recolhida ? 64 : 216;\n"
     "      const _facOk = player && player.realm >= 3;\n",
     "nenhum limiar"),

    # ── OS SITIOS ─────────────────────────────────────────────────────────
    ("a faixa do hub deixa de perguntar ao dono", UI,
     "      const ph = portasDoHub(player, todos.map(td => td.key), tab);\n"
     "      const chips = todos.filter(td => ph.lista.some(x => x.key === td.key));",
     "      const ph = { lista: todos.map(td => ({ key: td.key })), distantes: [] };\n"
     "      const chips = todos;",
     "V2HubStrip"),
    ("o Ceu desenha a Faccao sem perguntar", TABS,
     '              const pp = h.tab ? portaDe(player, h.tab) : { estado: "aberta" };',
     '              const pp = { estado: "aberta" };',
     "HubMundoScreen"),
    ("a maçaneta do PRIMEIRO ecra some outra vez", TABS,
     "                     portas={onAbrirSeletor ? euPortasVisiveis(player, EU_PORTAS).nomes : undefined}\n",
     "",
     "chegadas"),
    ("a consulta sai do VOLTAR nativo", APP,
     "        if (portaConsulta) { setPortaConsulta(null); return; }" + CR,
     "",
     "VOLTAR nativo fecha-a"),
    ("o cadeado vira um emoji", UI,
     '          {!incerta && <Mark name="lock" size={12} />}',
     "          {!incerta && <span>\U0001f512</span>}",
     "portas/selo"),

    # ── A FORMA (decidida pelo Astra, MESA [020]) ─────────────────────────
    ("o selo volta a 11px (a decisao era 12)", UI,
     '          {!incerta && <Mark name="lock" size={12} />}',
     '          {!incerta && <Mark name="lock" size={11} />}',
     "12px"),
    ("«Desbloqueios» volta a parecer outra porta trancada", TABS,
     "                                     border: portaTom().consulta, borderRadius:10,",
     "                                     border: portaTom().trancada, borderRadius:10,",
     "CONTINUO"),
    ("o contador perde o + (conta destinos ADICIONAIS)", UI,
     '          {"+" + n}',
     "          {n}",
     "+N"),
    # 🔴 A que o OLHAR apanhou: o nome em papel a' letra fazia a porta que nao
    # abre gritar mais alto do que as que abrem.
    ("a porta trancada grita mais alto que as abertas", UI,
     '                          background:"transparent", border: portaTom().trancada,\n'
     '                          color:"var(--muted)", cursor:"pointer", fontFamily:"inherit",',
     '                          background:"transparent", border: portaTom().trancada,\n'
     '                          color: NIV_ONDA.paper, cursor:"pointer", fontFamily:"inherit",',
     "MESMA cor"),
    ("um tracejado escrito a' mao volta a um sitio", TABS,
     "                            background:\"transparent\", border: portaTom().trancada,\n"
     "                            color:\"var(--text)\", cursor:\"pointer\", fontFamily:\"inherit\", fontSize:11.5,",
     "                            background:\"transparent\", border:\"1px dashed rgba(var(--gold2-rgb),.22)\",\n"
     "                            color:\"var(--text)\", cursor:\"pointer\", fontFamily:\"inherit\", fontSize:11.5,",
     "nenhum `dashed`"),
    ("um `kind` novo no servidor sem caminho no cliente", PORTAS,
     'KIND_REALM = "realm"\n',
     'KIND_REALM = "realm"\nKIND_QUEST = "quest"\n',
     "tem caminho no cliente"),
    # 🔴 A QUE JUSTIFICA A §29.3. Ninguem diz a' guarda onde o Mercado aparece:
    # a lista de gates vem do SERVIDOR, e ela tem de encontrar sozinha a cena da
    # Caverna (e a Praca) que o mostrariam como uma porta aberta.
    ("um gate NOVO nasce no Mercado", PORTAS,
     '    ("body_tempering", porta_corpo),\n)',
     '    ("body_tempering", porta_corpo),\n    ("market", porta_faccao),\n)',
     "consulta o dono (sem dono"),
]


def run():
    falhas = []
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        if orig.count(de) != 1:
            falhas.append("%-56s o PEDACO nao existe (x%d) — a bateria esta' "
                          "desactualizada" % (rot, orig.count(de)))
            print("  XX  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(
            orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run(
                [sys.executable, SUITE],
                capture_output=True, text=True, env=env, cwd=ROOT, timeout=900,
                # ⚠️ `text=True` sozinho descodifica com o codec do LOCALE
                # (cp1252 no Windows) e rebenta no primeiro 漢字 da suite.
                encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n") if l.strip().startswith("x ")]
            # ⚠️ O sinal honesto de crash e' o RODAPE, nunca "Traceback" no
            # stderr: a propria suite acende dois de proposito (§1 e §29).
            rebentou = "asserts verdes" not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and (not agulha
                                  or any(agulha in l for l in vermelhos))
            if acertou:
                print("  ok  %-56s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-56s REBENTOU — uma guarda que rebenta nao e' "
                              "uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-56s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-56s ficou vermelha pelo motivo ERRADO "
                              "(esperava %r; veio %r)" % (rot, agulha, vermelhos[:2]))
                print("  XX  " + falhas[-1])
        finally:
            io.open(path, "w", encoding="utf-8", newline="").write(orig)
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas),
                                       len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
