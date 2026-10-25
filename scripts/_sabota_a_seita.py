# -*- coding: utf-8 -*-
"""宗 A BATERIA DE SABOTAGEM da §34 (`_test_web_c_superficies.py`) — 4.1, 05/10.

Uma guarda que não morde não guarda. Cada entrada estraga UMA coisa no código,
corre a suite, e exige que ela fique VERMELHA a dizer o quê.

As regras são as das baterias anteriores:
  · uma guarda que REBENTA não é uma guarda vermelha (exige-se o rodapé);
  · uma sabotagem que não encontra o alvo dá-se por boa — cada alvo tem de
    aparecer EXACTAMENTE uma vez, verificado antes, ruidosamente;
  · os BYTES voltam iguais (lê com `newline=""`; o alvo ganha o fim de linha
    do ficheiro) — e cada ficheiro é conferido no fim.

Uso:  python -X utf8 scripts/_sabota_a_seita.py        (~7 min: 20 × a suite)
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUP = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")
SEITA = os.path.join(ROOT, "core", "seita.py")
WEB = os.path.join(ROOT, "core", "webserver.py")
ESCOLHA = os.path.join(ROOT, "core", "quest_choice_engine.py")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
ARNES = os.path.join(ROOT, "scripts", "_dev_serve_miniapp.py")
MI_ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")

# (rótulo, ficheiro, de, para, pedaço que TEM de aparecer no vermelho)
SABOTAGENS = [
    # ── 34.1 o dono ─────────────────────────────────────────────────────────
    ("o merito passa a ACENDER", SEITA,
     '_CONQUISTA = {"posto": "rank_index"}',
     '_CONQUISTA = {"posto": "rank_index", "merito": "contribution"}',
     "UMA conquista"),
    ("o retrato le' o SALDO (o merito) em vez da escada", SEITA,
     '        "contribution": int(ladder_contribution(earned, balance, scroll_econ is not None)),',
     '        "contribution": int(balance or 0),',
     "contribuição da ESCADA"),
    ("o retrato RECALCULA o posto (rebaixaria o renascido)", SEITA,
     "    r = rank if rank in SECT_RANKS else DEFAULT_SECT_RANK",
     "    r = rank if (rank in SECT_RANKS and int(earned or 0) >= 1500) else DEFAULT_SECT_RANK",
     "o posto é o gravado"),
    ("o ganho viaja SEM a chave-mestra (o main recebe chave nova)", SEITA,
     '    return {"seita_ganho": g} if onda_on(flag) else {}',
     '    return {"seita_ganho": g}',
     "só viajam com a chave-mestra"),
    ("a escada viaja SEM a chave-mestra", SEITA,
     '    return {"escada": escada()} if onda_on(flag) else {}',
     '    return {"escada": escada()}',
     "só viajam com a chave-mestra"),
    ("o 'antes' le' a ENTIDADE", SEITA,
     "    q = select(*_colunas()).where(Player.telegram_id == player_id)",
     "    q = select(Player).where(Player.telegram_id == player_id)",
     "seita/rota"),
    ("o 'antes' deixa de TRANCAR", SEITA,
     "    if trancar:\n        q = q.with_for_update()",
     "    if trancar:\n        pass",
     "TRANCADO, ANTES do motor"),
    # ── 34.2 as portas ──────────────────────────────────────────────────────
    ("o tributo le' o 'antes' mesmo SEM a onda", WEB,
     "            _antes = await _seita.ler_antes(session, user_id) if _onda_on() else None\n"
     "            res = await tribute_stones(session, user_id, stones)",
     "            _antes = await _seita.ler_antes(session, user_id)\n"
     "            res = await tribute_stones(session, user_id, stones)",
     "TODA porta que muda o posto"),
    ("o Salao esquece o 'antes' (a promocao ao abrir nao acende)", WEB,
     "            _antes = await _seita.ler_antes(session, user_id) if _onda_on() else None\n"
     "            # Promote if a realm gate",
     "            _antes = None\n"
     "            # Promote if a realm gate",
     "TODA porta que muda o posto"),
    ("a escolha da missao esquece o ganho na resposta", WEB,
     '            return _json({"ok": True, "choice_result": result["choice_result"],\n'
     "                          **_seita.no_payload(_g)})",
     '            return _json({"ok": True, "choice_result": result["choice_result"]})',
     "nos DOIS caminhos"),
    ("a escolha passa a creditar so' o saldo (o mapa dos escritores muda)", ESCOLHA,
     '                session, pid, sect_contribution_delta, source="sect_quest_choice"',
     '                session, pid, sect_contribution_delta, source="sect_quest_choice", credit_earned=False',
     "quem credita contribuição"),
    # ── 34.3 o ecrã ─────────────────────────────────────────────────────────
    ("o tributo acende no TOQUE (antes do ok)", TABS,
     '          const res = await api("world/sect_tribute", { stones: amt });\n'
     "          if (res && res.ok) {\n"
     '            haptic("success");\n'
     '            aplicarGanhoSeita(res.seita_ganho, res, "tributo", dadosVelhos);',
     '          const res = await api("world/sect_tribute", { stones: amt });\n'
     '          aplicarGanhoSeita(res.seita_ganho, res, "tributo", dadosVelhos);\n'
     "          if (res && res.ok) {\n"
     '            haptic("success");',
     "QUATRO portas"),
    ("a insignia acende fora do posto (arvore de Natal)", TABS,
     "<MarcaOnda estado={estado} acende={!!acende && i === idx} />",
     '<MarcaOnda estado={estado} acende={!!acende || estado === "next"} />',
     "só a insígnia do posto"),
    ("o denominador INVENTADO no cliente", TABS,
     "      const escada = Array.isArray(data.escada) ? data.escada : [];",
     '      const escada = Array.isArray(data.escada) ? data.escada : [{ rank: "disciple" }, { rank: "inner" }, { rank: "core" }, { rank: "elder" }, { rank: "heir" }];',
     "denominadores vêm do SERVIDOR"),
    ("o merito ganha OURO (luz que nao e' progresso)", TABS,
     '                                                      fontSize: 12.5, lineHeight: (18 / 12.5), color: P.muted })}>\n'
     '            {t("seita_onda_merito"',
     '                                                      fontSize: 12.5, lineHeight: (18 / 12.5), color: P.gold })}>\n'
     '            {t("seita_onda_merito"',
     "o MÉRITO"),
    ("o Salao OFF perde o badge do posto", TABS,
     '{!onda && <Badge variant="jade">{safeT(data.rank_key)}</Badge>}',
     '{false && <Badge variant="jade">{safeT(data.rank_key)}</Badge>}',
     "o Salão é o de hoje"),
    ("o selo ABREVIA o merito (fmtNum)", TABS,
     '{t("seita_onda_merito", { n: fmtFull(data.merit_balance) })}',
     '{t("seita_onda_merito", { n: fmtNum(data.merit_balance) })}',
     "INTEIROS"),
    ("a linha da missao esquece a resposta", TABS,
     "          onClaimed && onClaimed(res);",
     "          onClaimed && onClaimed();",
     "entrega a resposta"),
    ("uma frase do selo falta numa lingua", MI_ES,
     '  "seita_onda_portao": "Tu contribución ya basta — falta llegar al Reino {n}.",\n',
     "",
     "3 línguas"),
    # ── 34.4 o arnês ────────────────────────────────────────────────────────
    ("o arnes devolve o Salao ao catch-all", ARNES,
     '    "world/sect_hall": "api_world_sect_hall",\n',
     "",
     "HANDLER REAL, com as missões"),
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
    raise SystemExit(run())
