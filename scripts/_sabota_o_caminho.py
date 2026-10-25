# -*- coding: utf-8 -*-
"""道 A BATERIA DE SABOTAGEM da §11 do `_test_relatos_0814.py` — o report do [jogador] de 07/10.

*"@saint_nivrael , bug: setting default attack for PvE arena, does not increase
relevant path experience"*. Medido: subia (+18 por duelo de arena) e nenhum ecrã
o dizia. A §11 guarda o recibo dos Cinco Caminhos de ponta a ponta. Uma guarda
que não morde não guarda: cada entrada estraga UMA coisa, corre a suite, e exige
que ela fique VERMELHA a dizer o quê.

As regras de sempre: uma suite que REBENTA não é uma guarda vermelha; um alvo
tem de aparecer EXACTAMENTE uma vez; os BYTES voltam iguais (`newline=""`).

Uso:  python -X utf8 scripts/_sabota_o_caminho.py        (~3 min)
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELATOS = os.path.join(ROOT, "scripts", "_test_relatos_0814.py")
IE = os.path.join(ROOT, "core", "intent_engine.py")
WEB = os.path.join(ROOT, "core", "webserver.py")
PVP = os.path.join(ROOT, "core", "pvp_duel_settle.py")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
MI_ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")

# (rótulo, ficheiro, de, para, pedaço que TEM de aparecer no vermelho)
SABOTAGENS = [
    ("o recibo esquece a vitoria (so' conta os golpes)", IE,
     "            xp += WIN_INTENT_XP if won else LOSS_INTENT_XP",
     "            xp += 0",
     "o recibo do report"),
    ("o recibo inventa um caminho que o settle nao deu", IE,
     "        d = depois.get(intent)\n        if not d:\n            continue",
     '        d = depois.get(intent)\n        if not d:\n            d = {"rank": 0, "xp": 0}',
     "não se inventa"),
    ("o 'antes' sai vazio (o recibo deriva-se do depois)", IE,
     "    return {r[0]: {\"rank\": int(r[1] or 0), \"xp\": int(r[2] or 0)} for r in rows if r[0] in INTENT_KEYS}",
     "    return {}",
     "grava o recibo"),
    ("o recibo grava-se SEM a onda (o main muda)", IE,
     "        _ver_a = bool(duel.pve_source) and bool(_onda_on())",
     "        _ver_a = bool(duel.pve_source)",
     "sem a onda"),
    ("o recibo vai para o action_log (parte o historico)", IE,
     '                _ctx["caminho_ganho"] = _ganho',
     '                duel.action_log = (duel.action_log or []) + [{"type": "caminho_ganho", "g": _ganho}]',
     "NUNCA para o `action_log`"),
    ("o duel_state mostra o recibo a quem NAO jogou o lado A", WEB,
     "                if user_id == duel.attacker_id and _onda_on_cg():",
     "                if _onda_on_cg():",
     "só ao lado A"),
    ("o duel_state mostra o recibo SEM a onda", WEB,
     "                if user_id == duel.attacker_id and _onda_on_cg():",
     "                if user_id == duel.attacker_id:",
     "só com a onda"),
    ("o settle do PvP deixa de dar a XP de caminho", PVP,
     "        await award_post_duel_intent_xp(session, duel, winner_id)",
     "        pass",
     "os três settles chamam o dono"),
    ("o fim da luta esquece o recibo", TABS,
     "            {Array.isArray(state.caminho_ganho) && state.caminho_ganho.length > 0 && (",
     "            {false && (",
     "desenha o recibo"),
    ("o recibo ABREVIA o XP (fmtNum)", TABS,
     "? t(\"caminho_ganho_subiu\", { nome, xp: fmtFull(cg.xp), a: a.rank, b: d.rank })",
     "? t(\"caminho_ganho_subiu\", { nome, xp: fmtNum(cg.xp), a: a.rank, b: d.rank })",
     "desenha o recibo"),
    ("uma frase do recibo falta numa lingua", MI_ES,
     '  "caminho_ganho_max": "{nome}: +{xp} XP · rango máximo"',
     '  "caminho_ganho_mx": "{nome}: +{xp} XP · rango máximo"',
     "4 frases"),
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
            falhas.append("%-58s ALVO NAO ENCONTRADO (%d ocorrencias)" % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        _gravar(path, orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, "-X", "utf8", RELATOS], capture_output=True,
                               text=True, env=env, cwd=ROOT, timeout=900,
                               encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n") if l.startswith("  FAIL: ")]
            rebentou = " passed · " not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and any(agulha in l for l in vermelhos)
            if acertou:
                print("  ok  %-58s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-58s REBENTOU" % rot)
                print("  XX  " + falhas[-1])
                print("      " + (saida.strip().split("\n") or [""])[-1][:200])
            elif not mordeu:
                falhas.append("%-58s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-58s vermelha pelo motivo ERRADO (esperava %r)" % (rot, agulha))
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
