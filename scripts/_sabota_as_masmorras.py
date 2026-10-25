# -*- coding: utf-8 -*-
"""層 A BATERIA DE SABOTAGEM da §36 (`_test_web_c_superficies.py`) — 4.3, 08/10.

Uma guarda que não morde não guarda. Cada entrada estraga UMA coisa no código,
corre a suite, e exige que ela fique VERMELHA a dizer o quê.

As regras são as das baterias anteriores:
  · uma guarda que REBENTA não é uma guarda vermelha (exige-se o rodapé);
  · uma sabotagem que não encontra o alvo dá-se por boa — cada alvo tem de
    aparecer EXACTAMENTE uma vez, verificado antes, ruidosamente;
  · os BYTES voltam iguais (lê com `newline=""`; o alvo ganha o fim de linha
    do ficheiro) — e cada ficheiro é conferido no fim.

Uma guarda nasceu a escrever o dono, ANTES da bateria: a 1.ª confirmação do
andar só olhava o "depois", e um andar passado no ramo da MORTE de uma masmorra
já concluída passava (o percurso a zero e o `completed` antigo pareciam uma
conclusão) — agora o "antes" também tem de o provar, e a bateria morde as duas
metades.

Uso:  python -X utf8 scripts/_sabota_as_masmorras.py      (~38 × a suite)
⚠️ Enquanto corre: não correr a suite, não arrancar o arnês, não editar os
ficheiros abaixo (a bateria escreve neles e repõe-nos byte a byte).
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUP = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")
DONO = os.path.join(ROOT, "core", "masmorra.py")
WEB = os.path.join(ROOT, "core", "webserver.py")
SETTLE = os.path.join(ROOT, "core", "pve_duel_settle.py")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
ARNES = os.path.join(ROOT, "scripts", "_dev_serve_miniapp.py")
MI_ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")
MI_PT = os.path.join(ROOT, "miniapp", "i18n", "pt.json")

# (rótulo, ficheiro, de, para, pedaço que TEM de aparecer no vermelho)
SABOTAGENS = [
    # ── 36.1 o dono ─────────────────────────────────────────────────────────
    ("a POSICAO passa a acender", DONO,
     'EIXOS_QUE_ACENDEM = ("andar", "dificuldade")',
     'EIXOS_QUE_ACENDEM = ("andar", "dificuldade", "posicao")',
     "DUAS conquistas"),
    ("o andar acende sem as colunas o provarem", DONO,
     "    if andar is not None and int(andar) > 0 and _andar_confirmado(antes, depois, int(andar)):",
     "    if andar is not None and int(andar) > 0:",
     "as COLUNAS têm de provar"),
    ("a confirmacao so' olha o DEPOIS (a 1.a versao)", DONO,
     '    if int(depois["current_floor"]) == a and a == int(antes["current_floor"]) + 1:',
     '    if int(depois["current_floor"]) == a:',
     "as COLUNAS têm de provar"),
    ("a conclusao aceita um andar que nao e' o ultimo", DONO,
     ' and a == int(antes["floor_count"] or 0)',
     "",
     "as COLUNAS têm de provar"),
    ("a dificuldade acende sem SUBIR", DONO,
     '    if int(depois["best_difficulty"]) > int(antes["best_difficulty"]):',
     '    if int(depois["best_difficulty"]) >= int(antes["best_difficulty"]) and int(depois["best_difficulty"]) > 0:',
     "SOBE"),
    ("o alcance perde o heal de 23/07", DONO,
     "    if bool(completed) and bd > 0:",
     "    if False and bool(completed) and bd > 0:",
     "UMA conta com o heal"),
    ("o dono COPIA os andares (os mesmos numeros)", DONO,
     "    return int(_get_floor_count(dungeon, dificuldade) or 0)",
     "    return int((dungeon.floor_counts or {}).get(dificuldade) or dungeon.floor_count or 0)",
     "vêm do MOTOR"),
    ("sem expedicao inventa-se um denominador", DONO,
     '        "floor_count": andares(dungeon, dif) if dif else None,',
     '        "floor_count": andares(dungeon, dif or "normal"),',
     "nenhum denominador"),
    ("o ganho viaja SEM a chave-mestra", DONO,
     '    return {"masmorra_ganho": g} if onda_on(flag) else {}',
     '    return {"masmorra_ganho": g}',
     "só viajam com a chave-mestra"),
    ("o corte viaja SEM a chave-mestra", DONO,
     '    return {"corte": retrato_de(dungeon, pd_row)} if onda_on(flag) else {}',
     '    return {"corte": retrato_de(dungeon, pd_row)}',
     "só viajam com a chave-mestra"),
    ("o 'antes' deixa de TRANCAR a linha", DONO,
     "        q = q.with_for_update(of=PlayerDungeon)",
     "        q = q",
     "TRANCADO"),
    # ── 36.2 a porta ────────────────────────────────────────────────────────
    ("a lista volta ao heal escrito a' mao", WEB,
     "                _mf = (_masmorra.alcance(d, pd_row.max_floor_reached, pd_row.completed, bd)",
     "                _mf = (int(pd_row.max_floor_reached)",
     "a lista lê o alcance do DONO"),
    ("a entrada passa o andar 1 tambem na MORTE", WEB,
     "andar=1 if won else None)",
     "andar=1)",
     "ramo da VITÓRIA"),
    ("o avanco passa o andar tambem na MORTE", WEB,
     "andar=next_floor if won else None)",
     "andar=next_floor)",
     "ramo da VITÓRIA"),
    ("o recuo passa a falar do ganho", WEB,
     "        floor_reached = int(pd_row.current_floor or 0)\n",
     "        floor_reached = int(pd_row.current_floor or 0)\n        _masmorra_g = None\n",
     "o recuo e a varredura"),
    ("o fim do Chefe le' o 'antes' SEM a chave-mestra", SETTLE,
     "            if _onda_on():\n                from core import masmorra as _masmorra",
     "            if True:\n                from core import masmorra as _masmorra",
     "o fim do Chefe lê o 'antes'"),
    ("o Chefe que GANHA passa o andar", SETTLE,
     "andar=floor_count if won else None)",
     "andar=floor_count)",
     "o fim do Chefe lê o 'antes'"),
    ("o duel_state da' o ganho do Chefe SEM a chave", WEB,
     "                            out.update(_masmorra_ds.no_payload(_mg))",
     '                            out["masmorra_ganho"] = _mg',
     "espelho da chave-mestra"),
    ("a lista manda o corte sem o dono (e sem a chave)", WEB,
     "                        **_masmorra.corte_no_payload(d, pd_row),",
     '                        "corte": _masmorra.retrato_de(d, pd_row),',
     "a expedição aberta da lista leva o corte"),
    ("um chamador volta ao nome CRU do espolio", WEB,
     '                named = await _resolve_bag_items(session, result.get("loot") or {}, _pl_lang(player))',
     '                named = await _resolve_bag_items(session, result.get("loot") or {})',
     "TODOS os"),
    ("o resolve ignora a lingua", WEB,
     "        return catalog_name(lang, kind, r) if lang else r.name",
     "        return r.name",
     "o espólio do andar sai em pt"),
    # ── 36.3 o ecrã ─────────────────────────────────────────────────────────
    ("o TOQUE acende (uma 2.a porta da luz)", TABS,
     "        if (onda) { setMRecibo(null); setMOv(null); setMFim(null); }",
     "        if (onda) { setMRecibo(null); setMOv(null); setMFim(null); setMAcende({ andar: 1, dif: false, k: 1 }); }",
     "só o `masmorra_ganho` acende"),
    ("a varredura acende", TABS,
     '          haptic("success");\n          setResultBanner({\n            kind:"sweep",',
     '          haptic("success");\n          aplicarGanhoMasmorra(res, null);\n          setResultBanner({\n            kind:"sweep",',
     "a varredura não acende"),
    ("o corte acende o andar em que SE ESTA' (nao o vencido)", TABS,
     'const estado = f <= v ? "got" : f === v + 1 ? "next" : "empty";',
     'const estado = f <= v + 1 ? "got" : "empty";',
     "o corte marca os andares VENCIDOS"),
    ("um emoji entra no corte", TABS,
     '                                 textTransform: "uppercase" }}>{t("masm_onda_chefe")}</span>',
     '                                 textTransform: "uppercase" }}>\U0001F451 {t("masm_onda_chefe")}</span>',
     "nascem sem emoji"),
    ("o numero da expedicao abrevia", TABS,
     't("masm_onda_de", { n: fmtFull(fim ? N : v), total: fmtFull(N) })',
     't("masm_onda_de", { n: fmtNum(fim ? N : v), total: fmtNum(N) })',
     "INTEIROS"),
    ("o recibo volta para CIMA dos botoes", TABS,
     '                  <div style={rotulo}>{t("masm_onda_difs")}</div>',
     '                  <div data-masmorra-recibo="" style={rotulo}>{t("masm_onda_difs")}</div>',
     "a ACÇÃO vem antes do recibo"),
    ("o recibo perde a folga da barra de baixo", TABS,
     "scrollMarginBottom: MASM_FOLGA_BAIXO, scrollMarginTop: 8 }}>\n                    {(recibo.linhas",
     "scrollMarginTop: 8 }}>\n                    {(recibo.linhas",
     "ACIMA da barra de baixo"),
    ("o fim do duelo deixa de ser um hook", TABS,
     "      const _fimDado = useRef(false);",
     "      const _fimDado = { current: false };",
     "o duelo entrega o fim CONFIRMADO"),
    ("o ganho do Chefe acende DEBAIXO da janela", TABS,
     "            if (g && onFimMasmorra) onFimMasmorra(g, run);\n",
     "",
     "só se mostra quando a janela do duelo FECHA"),
    ("a morte volta a dizer 'andar 0'", TABS,
     "floor: res.won ? res.floor : (Number(run.current_floor) || 0) + 1,",
     "floor: res.floor,",
     "a morte diz o andar onde se caiu"),
    ("o modal volta a ter a SUA conta do espolio", TABS,
     "      const aggRows = dngEspolioLinhas(result.loot, named);",
     "      const aggRows = result.loot ? fmtBagSummary(result.loot) : [];",
     "o espólio tem UMA conta"),
    ("o Tributo da Terra some do recibo", TABS,
     "        const tributo = res.regional_bonus && res.regional_bonus.line;",
     "        const tributo = null;",
     "o Tributo da Terra"),
    ("sem a chave-mestra o cartao da lista ja' muda", TABS,
     "              {onda ? (\n                /* 層 4.3 — o recorde SEPARADO",
     "              {true ? (\n                /* 層 4.3 — o recorde SEPARADO",
     "são os de HOJE"),
    # ── as línguas ──────────────────────────────────────────────────────────
    ("uma chave do corte falta numa lingua", MI_ES,
     '  "masm_onda_espolio": "Botín",\n',
     "",
     "existem nas 3 línguas"),
    ("um marcador REPETIDO numa frase", MI_ES,
     '"Jefe derrotado — {dif} completada: {n} de {total} pisos"',
     '"Jefe derrotado — {dif} completada: {n} de {n} pisos"',
     "NENHUMA frase repete um marcador"),
    ("o trilho volta a dizer 'Dungeons' em pt", MI_PT,
     '  "tab_dungeons": "Masmorras",\n',
     '  "tab_dungeons": "Dungeons",\n',
     "dizem-se 'Masmorras'"),
    # ── 36.4 o arnês ────────────────────────────────────────────────────────
    ("o arnes perde a rota real do avanco", ARNES,
     '    "dungeons/advance": "api_dungeons_advance",\n',
     "",
     "HANDLER REAL e o fim do Chefe"),
]


def _ler(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _gravar(path, texto):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(texto)


def run():
    falhas = []
    originais = {}
    for _r, path, _d, _p, _a in SABOTAGENS:
        originais.setdefault(path, _ler(path))
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = _ler(path)
        if "\r\n" in orig:
            de, para = de.replace("\n", "\r\n"), para.replace("\n", "\r\n")
        if orig.count(de) != 1:
            falhas.append("%-58s ALVO NAO ENCONTRADO (%d ocorrencias) — a sabotagem "
                          "dava-se por boa sem nunca ter corrido" % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        _gravar(path, orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, "-X", "utf8", SUP], capture_output=True,
                               text=True, env=env, cwd=ROOT, timeout=900,
                               encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n") if l.startswith("  XX  ")]
            rebentou = "asserts verdes" not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and any(agulha in l for l in vermelhos)
            if acertou:
                print("  ok  %-58s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-58s REBENTOU — uma guarda que rebenta nao e' uma guarda "
                              "vermelha" % rot)
                print("  XX  " + falhas[-1])
                print("      " + (saida.strip().split("\n") or [""])[-1][:200])
            elif not mordeu:
                falhas.append("%-58s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-58s ficou vermelha pelo motivo ERRADO (esperava %r)"
                              % (rot, agulha))
                print("  XX  " + falhas[-1])
                for l in vermelhos[:3]:
                    print("      " + l.strip()[:200])
        finally:
            _gravar(path, orig)
            if _ler(path) != orig:
                print("  !!  %s NAO VOLTOU IGUAL — parar e ver a mao" % path)
                return 2
    for path, orig in originais.items():
        if _ler(path) != orig:
            print("  !!  %s NAO VOLTOU IGUAL no fim" % path)
            return 2
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas), len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(run())
