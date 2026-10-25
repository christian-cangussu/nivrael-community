# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM da §25 — 星 o Corpo que acende, a janela da
prévia e o frescor do report do [jogador] (21-22/09).

Mesmo contrato das outras (`_sabota_a_decisao`, `_sabota_o_cultivador`, …):
cada entrada estraga UMA coisa no código de produção, corre a suíte, e exige
que ela fique VERMELHA **a dizer o que é** — nunca a rebentar, e nunca por um
motivo diferente do esperado. O alvo é verificado ANTES: uma sabotagem que não
encontra o que estragar dava-se por boa.

O que esta bateria guarda, e porquê:

  · SÓ A CONFIRMAÇÃO ACENDE (1-3). A regra que o Astra escreveu contra os dois:
    tentativa falhada, ritual iniciado e timeout não conquistam um ponto.
  · SEM DADOS NUNCA É ZERO (4-5). A forma genérica do arnês (`ok:true` e mais
    nada) e uma lista parcial não podem virar `0 / 12` nem um número menor.
  · O MAPA É DO MOTOR (6-10). A ordem da resposta, as âncoras e o máximo do
    payload mandam; uma confirmação nunca passa do máximo.
  · UM DONO (11-13). A aba monta pela chave-mestra; a pintura tem UM
    renderizador; o modo diagrama não finge meditação.
  · A JANELA (14-17). O selector de 80px, a medida enganada pela animação, a
    moldura de cada sítio, a escala da prévia.
  · O FRESCOR DO [jogador] (18-19). Voltar ao separador e mudar de ecrã refrescam.
  · AS PALAVRAS E O SERVIDOR (20-22).

Uso:  python scripts/_sabota_o_corpo.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
APP = os.path.join(ROOT, "miniapp", "components", "app.js")
ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")
BTE = os.path.join(ROOT, "core", "body_tempering_engine.py")
SUITE = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")
NL = chr(10)

# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── 1-3. SÓ A CONFIRMAÇÃO ACENDE ──────────────────────────────────────
    ("o canal acende com `ok:true` sem `opened`", TABS,
     "if (res && res.ok === true && res.opened === true) {",
     "if (res && res.ok === true) {",
     "opened:true"),
    ("iniciar o ritual acende um ponto", TABS,
     "            // ⚠️ Iniciar NÃO acende nada. Um ritual é uma espera, não um canal." + NL,
     "            setAcende({ camada: \"mer\", id: res.channel });" + NL,
     "iniciar o ritual NAO acende"),
    ("um erro de rede na forja acende", TABS,
     "          await reconciliar(\"mortal\");",
     "          setAcende({ camada: \"mortal\", id: 1 });" + NL + "          await reconciliar(\"mortal\");",
     "`temperar`"),

    # ── 4-5. SEM DADOS NUNCA É ZERO ───────────────────────────────────────
    ("a forma genérica do arnês vira 0 / 12", TABS,
     "if (!d || d.ok === false || typeof d.current_level !== \"number\"" + NL
     + "          || typeof d.max_level !== \"number\" || d.max_level < 1) return null;",
     "if (!d || d.ok === false) return null;",
     "as TRES leituras REAIS"),
    ("a lista PARCIAL de canais dá um número", TABS,
     "      else if (chs.length === d.total) L = chs.filter(function (c) { return c.state === \"open\"; }).length;" + NL
     + "      else return null;",
     "      else L = chs.filter(function (c) { return c.state === \"open\"; }).length;",
     "as TRES leituras REAIS"),

    # ── 6-10. O MAPA É DO MOTOR ───────────────────────────────────────────
    ("os canais passam a ser postos pela POSIÇÃO na resposta", TABS,
     "var lugar = mapaOk ? CORPO_MER_LUGAR[c.key] : null;",
     "var lugar = mapaOk ? [Math.floor(chs.indexOf(c) / 2), chs.indexOf(c) % 2] : null;",
     "as TRES leituras REAIS"),
    ("o mapa dos canais diverge do motor", TABS,
     "bexiga: [3, 0], rim: [3, 1],",
     "bexiga: [3, 1], rim: [3, 0],",
     "as TRES leituras REAIS"),
    ("a figura masculina perde uma âncora", TABS,
     "male:   { seam: [[50, 64], [50, 58], [50, 52], [50, 46], [50, 40], [50, 35], [50, 23]],",
     "male:   { seam: [[50, 64], [50, 58], [50, 52], [50, 46], [50, 40], [50, 35]],",
     "as TRES leituras REAIS"),
    ("o Refino ignora o máximo do payload", TABS,
     "var M = Number(bc.max_level), L = Number(bc.mortal_level);",
     "var M = 7, L = Number(bc.mortal_level);",
     "as TRES leituras REAIS"),
    ("a confirmação passa do máximo", TABS,
     "      if (confirmado != null && confirmado > L && confirmado <= M) L = confirmado;" + NL
     + "      var chaves",
     "      if (confirmado != null) L = confirmado;" + NL + "      var chaves",
     "as TRES leituras REAIS"),

    # ── 11-13. UM DONO ────────────────────────────────────────────────────
    ("o Corpo deixa de montar", TABS,
     "if (obraOn()) return <CorpoQueAcende",
     "if (false) return <CorpoQueAcende",
     "a aba despacha"),
    ("nasce uma segunda pintura do cultivador", TABS,
     "        <CultivatorFigure diagrama gender={gender} size={_S} rotulo={rotulo}>" + NL,
     "        <CultivatorFigure diagrama gender={gender} size={_S} rotulo={rotulo}>" + NL
     + "          <img src={cultivatorArtUrl(gender)} alt=\"\" />" + NL,
     "F-7 (B)"),
    ("o modo diagrama passa a exigir meditação", UI,
     "      if (diagrama) {",
     "      if (diagrama && meditating) {",
     "modo diagrama"),

    # ── 14-17. A JANELA ───────────────────────────────────────────────────
    ("o corpo da janela volta a ter base zero", UI,
     "const bodyFlex = _conteudo ? \"0 1 auto\" : \"1 1 0\";",
     "const bodyFlex = \"1 1 0\";",
     "base zero"),
    ("a medida volta ao rectângulo transformado", UI,
     "const b = c.offsetTop - base + c.offsetHeight;",
     "const b = c.getBoundingClientRect().bottom;",
     "LAYOUT"),
    ("cada sítio volta a pintar a moldura", UI,
     "...(_onda && !fs ? semMoldura(cardStyle) : cardStyle),",
     "...cardStyle,",
     "MOLDURA"),
    ("a janela do PC volta aos 912px", UI,
     "if (onda) return `min(${Math.round(d * 1.6)}px, 1120px, 88vw)`;",
     "if (onda) return `min(${Math.round(d * 2.4)}px, 1120px, 88vw)`;",
     "escala da previa"),

    # ── 18-19. O FRESCOR DO [jogador] ───────────────────────────────────────────
    ("voltar ao separador deixa de pedir já", UI,
     "regresso(); start();",
     "start();",
     "voltar ao separador"),
    ("mudar de ecrã deixa de refrescar o jogador", APP,
     "if (Date.now() - _ultimoPlayerRef.current > 10000) loadPlayer();",
     "if (false) loadPlayer();",
     "mudar de ecra"),

    # ── 20-21. A TRAVA VOLTA A NASCER NUMA PORTA SÓ ───────────────────────
    # O defeito que o [jogador] encontrou duas vezes: a mesma acção com duas regras.
    # Uma trava que renasça num endpoint sozinho tem de ficar vermelha AQUI,
    # antes de chegar ao jogador que a descobre a tentar.
    ("uma porta volta a travar por meditação", TABS.replace(
        os.path.join("miniapp", "components", "tabs.js"),
        os.path.join("core", "webserver.py")),
     "async def api_arena_queue_join(request: web.Request) -> web.Response:",
     "async def api_arena_queue_join(request: web.Request) -> web.Response:" + NL
     + "    from config import RESTRICTED_MEDITATION  # sabotagem",
     "ZERO portas travam"),
    ("o catálogo volta a prometer a trava", TABS.replace(
        os.path.join("miniapp", "components", "tabs.js"),
        os.path.join("core", "webserver.py")),
     "            \"multiplier\": float(info.get(\"multiplier\", 0.0)),",
     "            \"multiplier\": float(info.get(\"multiplier\", 0.0))," + NL
     + "            \"restricts_combat\": False,",
     "NAO promete uma trava"),

    # ── 22-24. AS PALAVRAS E O SERVIDOR ───────────────────────────────────
    ("o espanhol perde uma frase do Corpo", ES,
     "    \"corpo_res_nivel\"",
     "    \"corpo_res_nivel_ROTO\"",
     "es.json"),
    ("o servidor deixa de mandar a ordem das etapas", BTE,
     "        \"tier_keys\": [k for k, _e in MORTAL_TIERS],",
     "",
     "tier_keys"),
    ("o servidor manda só 9 dos 12 níveis", BTE,
     "            if 1 <= int(lv) <= int(MAX_TEMPERING_LEVEL)",
     "            if 1 <= int(lv) <= 9",
     "`levels` traz"),
]


def run():
    falhas = []
    print("=" * 78)
    print("  \U0001fa78 SABOTAGEM da §25 — %d ataques" % len(SABOTAGENS))
    print("=" * 78)
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        # o alvo pode ter CRLF no disco; o ataque escreve-se com LF
        alvo = de if orig.count(de) == 1 else de.replace(NL, chr(13) + NL)
        novo = para if alvo == de else para.replace(NL, chr(13) + NL)
        if orig.count(alvo) != 1:
            falhas.append("%-52s ALVO NAO ENCONTRADO (%d ocorrencias)" % (rot, orig.count(alvo)))
            print("  !!  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(orig.replace(alvo, novo, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, SUITE], capture_output=True, text=True,
                               env=env, cwd=ROOT, timeout=900, encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split(NL) if l.strip().startswith("x ")]
            rebentou = "asserts verdes" not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and any(agulha in l for l in vermelhos)
            if acertou:
                print("  ok  %-52s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-52s REBENTOU — uma guarda que rebenta nao e' uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-52s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-52s ficou vermelha pelo motivo ERRADO (esperava %r; veio %r)"
                              % (rot, agulha, (vermelhos[:1] or [""])[0][:90]))
                print("  XX  " + falhas[-1])
        finally:
            io.open(path, "w", encoding="utf-8", newline="").write(orig)
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas), len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
