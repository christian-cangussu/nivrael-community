# -*- coding: utf-8 -*-
"""⚔️ A BATERIA DE SABOTAGEM do §7 (`_test_relatos_0814`) e do §18 (superfícies).

Uma guarda que não morde não guarda. Cada entrada estraga UMA coisa no código de
produção, corre a suite indicada, e exige que ela fique VERMELHA a dizer o que é.

As regras do runner são as mesmas do `_sabota_o_mapa.py` / `_sabota_a_forja.py`:

  · **Uma guarda que REBENTA não é uma guarda vermelha** — exige-se código de
    saída 1 com asserts vermelhos, nunca um traceback. O sinal de "chegou ao
    fim" é o RODAPÉ, porque a suite acende tracebacks de propósito.
  · **Uma sabotagem que nunca encontra o alvo dá-se por boa** — cada alvo é
    verificado ANTES, ruidosamente.
  · **`text=True` sozinho rebenta no primeiro 漢字** (codec do locale).

⚠️ A sabotagem que mais interessa aqui é a primeira: **a arte do Caminho
Proibido a disparar sozinha**. Ela cobra karma e ANOS DE VIDA por uso. Se essa
guarda deixar de morder, o jogo passa a poder gastar a vida de quem está a
dormir — e nenhum teste diria nada.

Uso:  python scripts/_sabota_o_golpe.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUEL = os.path.join(ROOT, "core", "duel_engine.py")
ARENA = os.path.join(ROOT, "core", "arena_engine.py")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
DB = os.path.join(ROOT, "database", "db.py")
LOC_PT = os.path.join(ROOT, "locales", "pt.json")

RELATOS = os.path.join(ROOT, "scripts", "_test_relatos_0814.py")
SUP = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")

# (rótulo, suite, ficheiro, de, para, pedaço que TEM de aparecer no vermelho)
SABOTAGENS = [
    # ── ⚠️ A TRAVA SÉRIA ────────────────────────────────────────────────────
    ("a arte PROIBIDA passa a disparar sozinha", RELATOS, DUEL,
     "        from core.forbidden_path_engine import is_forbidden\n"
     "        if is_forbidden(tech_id):\n"
     '            return dict(basic, fell_back="forbidden_never_auto", wanted=tech_id)\n',
     "        pass\n",
     "PROIBIDA nunca dispara"),

    ("sem qi o automático RECUSA a ronda (prende o duelo)", RELATOS, DUEL,
     '        return dict(basic, fell_back="not_enough_combat_qi", wanted=tech_id)',
     '        return None',
     "sem qi cai no básico"),

    ("a arte já não precisa de estar equipada", RELATOS, DUEL,
     "    tech = _find_technique(fighter or {}, tech_id)",
     "    tech = {}",
     "equipada nesta luta"),

    # ── ⚠️ A OFF-IDENTITY: o `main` a pagar uma query por ronda ────────────
    ("o gate da flag vai para DEPOIS do select", RELATOS, DUEL,
     "    basic = dict(BASIC_STRIKE)\n"
     "    if not golpe_padrao_on():\n"
     "        return basic\n",
     "    basic = dict(BASIC_STRIKE)\n",
     "ZERO queries"),

    ("um dos lados fica esquecido no preenchimento", RELATOS, DUEL,
     '            duel.pending_action_b = await resolve_default_strike(session, duel, "b")',
     '            duel.pending_action_b = dict(BASIC_STRIKE)',
     "nos DOIS lados"),

    ("o automático volta a ser MUDO", RELATOS, DUEL,
     "            if _said:\n"
     "                _entry[\"default_strike\"] = _said\n",
     "",
     "ESCRITA no registro"),

    # ── ⏳ O ENCONTRO RÁPIDO ────────────────────────────────────────────────
    ("a espera encurta MESMO com gente na fila", RELATOS, ARENA,
     "    if others > 0:\n"
     "        return ARENA_QUEUE_TIMEOUT_SECONDS, False\n",
     "",
     "a espera é a de sempre"),

    ("a contagem corre mesmo com a flag OFF", RELATOS, ARENA,
     "    if not encontro_rapido_on():\n"
     "        return ARENA_QUEUE_TIMEOUT_SECONDS, False\n",
     "",
     "SEM a query da contagem"),

    # ⚠️ O alvo tem de ser ÚNICO: a constante aparece duas vezes no ficheiro (a
    # definição e a prosa que a explica). Uma sabotagem de alvo ambíguo não é
    # uma sabotagem — e é melhor que se recuse a correr, que foi o que fez.
    ("a janela curta vai a zero (mata o PvP)", RELATOS, ARENA,
     "\nARENA_QUEUE_SOLO_TIMEOUT_SECONDS = 30\n",
     "\nARENA_QUEUE_SOLO_TIMEOUT_SECONDS = 0\n",
     "NÃO é zero"),

    ("a mensagem volta a culpar o ELO", RELATOS, LOC_PT,
     '"combat_arena_expired_chat_hint": "\\n⌛ _Sua fila terminou sem que outra alma entrasse nela.',
     '"combat_arena_expired_chat_hint": "\\n⌛ _Sua fila expirou — ninguem com ELO compativel.',
     "já não culpa o ELO"),

    # ── ⚠️ AS FLAGS NASCEM OFF ──────────────────────────────────────────────
    ("a flag `golpe_padrao` nasce LIGADA", RELATOS, DB,
     '    "golpe_padrao":        False,',
     '    "golpe_padrao":        True, ',
     "nasce OFF"),

    ("a flag `arena_encontro_rapido` nasce LIGADA", RELATOS, DB,
     '    "arena_encontro_rapido": False,',
     '    "arena_encontro_rapido": True, ',
     "nasce OFF"),

    # ── A TELA (§18) ────────────────────────────────────────────────────────
    ("o painel nasce em todo mundo (sem o gate do servidor)", SUP, TABS,
     "            {data.default_strike && (\n"
     "              <DefaultStrikePicker ds={data.default_strike} onChanged={onChanged} />\n"
     "            )}",
     "            <DefaultStrikePicker ds={data.default_strike || {}} onChanged={onChanged} />",
     "so' nasce quando o servidor manda"),

    ("a tela esconde que a escolha morreu", SUP, TABS,
     "          {!!ds.stored && ds.stored !== cur && (",
     "          {false && (",
     "por agora sai o basico"),

    ("a proibida fica de fora EM SILÊNCIO", SUP, TABS,
     "          {ds.forbidden_hidden > 0 && (",
     "          {false && (",
     "esconder em silencio"),

    ("a fila perde o caso normal (fica só o vazio)", SUP, TABS,
     '                : t("combat_arena_q_waiting_meta", {\n'
     "                    mins: mm, secs: ss,\n"
     "                    range: (status && status.elo_range) || 200,\n"
     "                  })}",
     '                : ""}',
     "o ramo de sempre continua"),

    # ── ⚠️ AS ANTI-GUARDAS: se o localizador falhar, tudo compara o vazio ──
    ("o localizador perde a função do motor", RELATOS, DUEL,
     "async def resolve_default_strike(session, duel: DuelSession, side: str) -> dict:",
     "async def resolver_o_golpe(session, duel: DuelSession, side: str) -> dict:",
     ""),

    ("o localizador perde o painel da tela", SUP, TABS,
     "    function DefaultStrikePicker({ ds, onChanged }) {",
     "    function PainelDoGolpe({ ds, onChanged }) {",
     ""),
]


def run():
    falhas = []
    for rot, suite, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8").read()
        if orig.count(de) != 1:
            falhas.append("%-52s ALVO NAO ENCONTRADO (%d ocorrencias) — a "
                          "sabotagem dava-se por boa sem nunca ter corrido"
                          % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(
            orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, suite], capture_output=True,
                               text=True, env=env, cwd=ROOT, timeout=600,
                               encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            # as duas suites marcam o vermelho de forma diferente
            vermelhos = [l for l in saida.split("\n")
                         if l.strip().startswith("x ")
                         or l.strip().startswith("FAIL:")
                         or l.strip().startswith("· ")]
            rebentou = ("asserts verdes" not in saida) and ("passed ·" not in saida)
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and (not agulha
                                  or any(agulha in l for l in vermelhos))
            if acertou:
                print("  ok  %-52s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-52s REBENTOU — uma guarda que rebenta nao e' "
                              "uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-52s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-52s ficou vermelha pelo motivo ERRADO "
                              "(esperava %r)" % (rot, agulha))
                print("  XX  " + falhas[-1])
        finally:
            io.open(path, "w", encoding="utf-8", newline="").write(orig)
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas),
                                       len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
