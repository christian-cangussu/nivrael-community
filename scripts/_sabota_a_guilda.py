# -*- coding: utf-8 -*-
"""幫 A BATERIA DE SABOTAGEM da §35 (`_test_web_c_superficies.py`) — 4.2, 07/10.

Uma guarda que não morde não guarda. Cada entrada estraga UMA coisa no código,
corre a suite, e exige que ela fique VERMELHA a dizer o quê.

As regras são as das baterias anteriores:
  · uma guarda que REBENTA não é uma guarda vermelha (exige-se o rodapé);
  · uma sabotagem que não encontra o alvo dá-se por boa — cada alvo tem de
    aparecer EXACTAMENTE uma vez, verificado antes, ruidosamente;
  · os BYTES voltam iguais (lê com `newline=""`; o alvo ganha o fim de linha
    do ficheiro) — e cada ficheiro é conferido no fim.

Duas guardas nasceram AQUI, pela própria bateria (a lição de 07/10: a guarda
afirma o que o sítio É, não o que CONTÉM): uma cópia da fórmula do custo em
`core/guilda.py` dava os mesmos números e passava a guarda de VALOR; e o bloco
do próximo nível escondido por um ternário (`display: fresco ? … : "none"`)
passava a guarda que só procurava `fresco &&`.

Uso:  python -X utf8 scripts/_sabota_a_guilda.py        (~10 min: 29 × a suite)
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUP = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")
GUILDA = os.path.join(ROOT, "core", "guilda.py")
MOTOR = os.path.join(ROOT, "core", "sect_engine.py")
WEB = os.path.join(ROOT, "core", "webserver.py")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
ARNES = os.path.join(ROOT, "scripts", "_dev_serve_miniapp.py")
MI_ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")

# (rótulo, ficheiro, de, para, pedaço que TEM de aparecer no vermelho)
SABOTAGENS = [
    # ── 35.1 o dono ─────────────────────────────────────────────────────────
    ("o TESOURO passa a acender", GUILDA,
     '_CONQUISTA = {"nivel": "level"}',
     '_CONQUISTA = {"nivel": "level", "tesouro": "treasury"}',
     "UMA conquista"),
    ("o numero do efeito volta ao float (+14% no Treino 3)", MOTOR,
     "        return int(round((get_training_bonus(lv) - 1) * 100))",
     "        return int((get_training_bonus(lv) - 1) * 100)",
     "UMA conta, exacta"),
    ("a cadeia do chat volta a fazer conta sua", MOTOR,
     '        return f"-{v}% cost"',
     '        return f"-{int(get_forge_discount(level) * 100)}% cost"',
     "não faz conta sua"),
    ("a planta COPIA a formula do custo (os mesmos numeros)", GUILDA,
     '        "next_cost": int(calculate_upgrade_cost(lv)),\n    }\n\n\ndef planta(sect)',
     '        "next_cost": 1000 * (lv + 1) ** 2,\n    }\n\n\ndef planta(sect)',
     "PEDEM o custo e o efeito ao motor"),
    ("a planta viaja SEM a chave-mestra (o main recebe chave nova)", GUILDA,
     '    return {"planta": planta(sect)} if onda_on(flag) else {}',
     '    return {"planta": planta(sect)}',
     "só viajam com a chave-mestra"),
    ("o ganho viaja SEM a chave-mestra", GUILDA,
     '    return {"guilda_ganho": g} if onda_on(flag) else {}',
     '    return {"guilda_ganho": g}',
     "só viajam com a chave-mestra"),
    ("o 'antes' deixa de TRANCAR", GUILDA,
     "    if trancar:\n        q = q.with_for_update(of=Sect)",
     "    if trancar:\n        pass",
     "TRANCADO"),
    ("o 'antes' le' a ENTIDADE", GUILDA,
     "    q = (select(coluna, Sect.spirit_stones)",
     "    q = (select(Sect)",
     "guilda/rota"),
    # ── 35.2 a porta ────────────────────────────────────────────────────────
    ("um 2.o ESCRITOR do nivel (o jardim mexe no nivel)", MOTOR,
     "        amount = get_herb_garden_yield(sect.herb_garden_lvl)",
     "        sect.herb_garden_lvl += 0\n        amount = get_herb_garden_yield(sect.herb_garden_lvl)",
     "UM escritor do nível"),
    ("uma ROTA nova alcanca o escritor (a doacao)", WEB,
     "    from core.sect_engine import donate_to_sect\n",
     "    from core.sect_engine import donate_to_sect, upgrade_building\n"
     "    if False:\n        await upgrade_building(None, None, None, None)\n",
     "rotas do mini-app que mudam um nível"),
    ("a validacao volta a ter as seis chaves a mao", WEB,
     "    if not isinstance(building, str) or building not in BUILDINGS:",
     '    if not isinstance(building, str) or building not in {"training", "herb_garden", '
     '"forge", "library", "defense", "spirit_vein"}:',
     "nenhuma cópia das seis chaves"),
    ("a melhoria le' o 'antes' mesmo SEM a onda", WEB,
     "        _antes = await _guilda.ler_antes(session, user_id, building) if _onda_on() else None",
     "        _antes = await _guilda.ler_antes(session, user_id, building)",
     "OFF a resposta da melhoria"),
    ("o 'antes' le'-se DEPOIS de carregar a guilda", WEB,
     "        _antes = await _guilda.ler_antes(session, user_id, building) if _onda_on() else None\n"
     "        info = await get_player_sect_info(session, user_id)",
     "        info = await get_player_sect_info(session, user_id)\n"
     "        _antes = await _guilda.ler_antes(session, user_id, building) if _onda_on() else None",
     "ANTES de"),
    ("a melhoria esquece o ganho na resposta", WEB,
     "                **_guilda.no_payload(_g),\n",
     "",
     "devolve"),
    ("a aba esquece a planta", WEB,
     "                **_guilda.planta_no_payload(sect),\n",
     "",
     "a aba manda a planta"),
    # ── 35.3 o ecrã ─────────────────────────────────────────────────────────
    ("a luz acende com o TOQUE (antes do servidor)", TABS,
     '        setGuildaBusy(key); setGuildaErro(null); haptic("warning");',
     '        setGuildaBusy(key); setGuildaErro(null); haptic("warning"); setGuildaAcende({ key, k: Date.now() });',
     "só o `guilda_ganho` do servidor acende"),
    ("TODAS as instalacoes acendem", TABS,
     "acende={!!acende && acende.key === inst.key} />",
     "acende={!!acende} />",
     "só a instalação melhorada acende"),
    ("a aba volta a SOMAR as seis num 'nivel da guilda'", TABS,
     '                value: t("guilda_onda_membros_de", { n: fmtFull(s.member_count), max: fmtFull(s.max_members) }) },\n'
     "            ] : [",
     '                value: t("guilda_onda_membros_de", { n: fmtFull(s.member_count), max: fmtFull(s.max_members) }) },\n'
     '              { label: t("buildings"), value: Object.values(s.buildings).reduce((a,b)=>a + (b.level||0), 0) },\n'
     "            ] : [",
     "NADA soma"),
    ("a planta ABREVIA o nivel", TABS,
     "{fmtFull(lv)}</span>",
     "{fmtNum(lv)}</span>",
     "INTEIROS (`fmtFull`)"),
    ("a planta REPETE a formula do custo", TABS,
     "      const custo = Number(atual.next_cost) || 0;",
     "      const custo = 1000 * Math.pow(nivel + 1, 2);",
     "não repete a fórmula"),
    ("a aba le' a chave-mestra por OUTRA porta", TABS,
     "      const onda = obraOn();\n      const [guildaSel, setGuildaSel]",
     "      const onda = ondaCultOn();\n      const [guildaSel, setGuildaSel]",
     "UM leitor da chave-mestra"),
    ("um estado nasce DEPOIS do return (React #310)", TABS,
     "      if (loading && !(onda && data && data.sect)) return <ListSkeleton rows={8} />;",
     "      if (loading && !(onda && data && data.sect)) return <ListSkeleton rows={8} />;\n"
     "      const [_tarde, _setTarde] = useState(null);",
     "ANTES do 1.º `return`"),
    ("a planta desenha-se SEM a chave-mestra", TABS,
     "      const plantaOk = onda && Array.isArray(s.planta) && s.planta.length > 0;",
     "      const plantaOk = Array.isArray(s.planta) && s.planta.length > 0;",
     "sem a planta do servidor"),
    ("a planta nasce com EMOJI", TABS,
     '          <CardTitle left={t("guilda_onda_planta")} />',
     '          <CardTitle left={"🏯 " + t("guilda_onda_planta")} />',
     "sem emoji"),
    ("uma instalacao pede uma marca que NAO EXISTE", TABS,
     'library: "brush", defense: "formation", spirit_vein: "stone",',
     'library: "brush", defense: "formation", spirit_vein: "vein",',
     "marca que EXISTE"),
    ("o efeito de uma instalacao falta numa lingua", MI_ES,
     '  "guilda_efeito_forge": "−{n}% en el coste de mineral",\n',
     "",
     "3 línguas"),
    ("o recibo volta a ficar POR TRAS da barra", TABS,
     "scrollMarginBottom: GUILDA_FOLGA_BAIXO, scrollMarginTop: 8",
     "scrollMarginBottom: 0, scrollMarginTop: 8",
     "ACIMA da barra"),
    ("o bloco do proximo nivel some a espera da releitura (ternario)", TABS,
     "              <div style={{ marginTop: 8 }}>\n"
     "                <div style={Object.assign({}, rotulo, { color: P.gold })}>",
     '              <div style={{ marginTop: 8, display: fresco ? undefined : "none" }}>\n'
     "                <div style={Object.assign({}, rotulo, { color: P.gold })}>",
     "nunca some à espera da releitura"),
    # ── 35.4 o arnês ────────────────────────────────────────────────────────
    ("o arnes devolve a melhoria ao catch-all", ARNES,
     '    "sect/upgrade": "api_sect_upgrade",\n',
     "",
     "HANDLER REAL (a Guilda"),
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
