# -*- coding: utf-8 -*-
"""⚔️ A BATERIA DE SABOTAGEM da §9 do `_test_relatos_0814` (report de 2026-09-30).

*"@saint, bug: error 500 on selecting default arts for duels, in Loadout
screen"* — a porta `combat/default_strike` filtrava `PlayerTechnique.is_active`,
uma coluna que não existe. Uma guarda que não morde não guarda: cada entrada
estraga UMA coisa, corre a suite e exige que ela fique VERMELHA a dizer o quê.

As regras do runner são as do `_sabota_o_golpe.py`, mais uma:

  · **Uma guarda que REBENTA não é uma guarda vermelha** — exige-se código de
    saída 1 com asserts vermelhos e o RODAPÉ da suite, nunca um traceback.
  · **Uma sabotagem que nunca encontra o alvo dá-se por boa** — cada alvo é
    verificado ANTES, ruidosamente (tem de aparecer exactamente uma vez).
  · ⚠️ **Os BYTES do ficheiro voltam iguais.** O runner antigo lia com newlines
    universais e escrevia em LF: um ficheiro CRLF (`handlers/combat.py`,
    `handlers/tribulation.py`) saía da bateria convertido. Aqui lê-se com
    `newline=""` e o alvo ganha o fim de linha do ficheiro.

A primeira é a que interessa: **o `is_active` do report, de volta**. Se ela não
morder, o 500 pode voltar e nenhum teste diz nada — que foi o que aconteceu.

Uso:  python scripts/_sabota_a_porta_do_golpe.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "core", "webserver.py")
COMBAT = os.path.join(ROOT, "handlers", "combat.py")
TRIB_H = os.path.join(ROOT, "handlers", "tribulation.py")
TRIB_E = os.path.join(ROOT, "core", "tribulation_engine.py")
ORM = os.path.join(ROOT, "scripts", "_audit_orm_colunas.py")

RELATOS = os.path.join(ROOT, "scripts", "_test_relatos_0814.py")

# (rótulo, ficheiro, de, para, pedaço que TEM de aparecer no vermelho)
SABOTAGENS = [
    # ── 🔴 O REPORT ─────────────────────────────────────────────────────────
    ("a rota volta a `is_active` (o 500 do report)", WEB,
     "PlayerTechnique.is_active_combat.is_(True),",
     "PlayerTechnique.is_active.is_(True),",
     "(era o 500)"),

    # ── a porta: grava, recusa a dizer porque, e respeita a flag ───────────
    ("a rota deixa de gravar a escolha", WEB,
     "        player.default_technique_id = tech_id or None",
     "        player.default_technique_id = None",
     "GRAVA a escolha"),

    ("a rota aceita uma arte NAO equipada", WEB,
     "            if row is None:\n"
     '                return _json({"ok": False, "reason": "technique_not_equipped"}, status=200)',
     "            if False:\n"
     '                return _json({"ok": False, "reason": "technique_not_equipped"}, status=200)',
     "NAO equipada"),

    ("a rota perde o veto da arte PROIBIDA", WEB,
     '                return _json({"ok": False, "reason": "forbidden_never_auto"}, status=200)',
     "                pass",
     "PROIBIDA"),

    ("a rota perde o gate da flag (o `main` a pagar)", WEB,
     "    if not golpe_padrao_on():\n"
     '        return _err("feature_off", 404)\n',
     "",
     "flag OFF"),

    # ── o 2.º achado: a tribulação ─────────────────────────────────────────
    ("o chat volta a `Tribulation.result`", COMBAT,
     "                    tribulation_passed_clause(user_id),",
     '                    Tribulation.player_id == user_id, Tribulation.result == "success",',
     "Modelo.coluna"),

    ("o mini-app volta a so' aceitar 'success'", WEB,
     "                    tribulation_passed_clause(user_id),",
     '                    Tribulation.player_id == user_id, Tribulation.outcome == "success",',
     "copias fora do dono"),

    ("o portao do chat deixa passar QUALQUER tribulacao", COMBAT,
     "                    tribulation_passed_clause(user_id),",
     "                    Tribulation.player_id == user_id,",
     "pergunta ao dono"),

    ("o dono esquece a PERFEITA", TRIB_E,
     'TRIBULATION_PASSED_OUTCOMES = ("success", "perfect")',
     'TRIBULATION_PASSED_OUTCOMES = ("success",)',
     "PERFEITA conta"),

    ("a resolucao do chat volta a escrever a regra a' mao", TRIB_H,
     "        if outcome in TRIBULATION_PASSED_OUTCOMES:",
     '        if outcome in ("success", "perfect"):',
     "(tuplo)"),

    # ── o varredor das colunas: tem de VER ─────────────────────────────────
    ("o varredor fica cego a' coluna que falta", ORM,
     "            if not hasattr(mods[cls], node.attr):",
     "            if False:",
     "AUTO-TESTE"),

    ("o varredor deixa de seguir o `as`", ORM,
     "                    nomes[a.asname or a.name] = a.name",
     "                    nomes[a.name] = a.name",
     "com `as`"),

    ("o varredor nao ve modelo nenhum", ORM,
     "                if a.name in mods:",
     "                if a.name in ():",
     "ANTI-GUARDA: o varredor"),
]


def _ler(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def _gravar(path, texto):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(texto)


def run():
    falhas = []
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = _ler(path)
        if "\r\n" in orig:
            de, para = de.replace("\n", "\r\n"), para.replace("\n", "\r\n")
        if orig.count(de) != 1:
            falhas.append("%-52s ALVO NAO ENCONTRADO (%d ocorrencias) — a "
                          "sabotagem dava-se por boa sem nunca ter corrido"
                          % (rot, orig.count(de)))
            print("  !!  " + falhas[-1])
            continue
        _gravar(path, orig.replace(de, para, 1))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, "-X", "utf8", RELATOS],
                               capture_output=True, text=True, env=env,
                               cwd=ROOT, timeout=900,
                               encoding="utf-8", errors="replace")
            saida = (r.stdout or "") + (r.returncode and (r.stderr or "") or "")
            vermelhos = [l for l in saida.split("\n")
                         if l.strip().startswith("FAIL:")]
            rebentou = "passed ·" not in saida
            mordeu = (r.returncode == 1) and vermelhos and not rebentou
            acertou = mordeu and any(agulha in l for l in vermelhos)
            if acertou:
                print("  ok  %-52s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-52s REBENTOU — uma guarda que rebenta nao e' "
                              "uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
                print("      " + (saida.strip().split("\n") or [""])[-1][:160])
            elif not mordeu:
                falhas.append("%-52s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-52s ficou vermelha pelo motivo ERRADO "
                              "(esperava %r)" % (rot, agulha))
                print("  XX  " + falhas[-1])
                for l in vermelhos[:3]:
                    print("      " + l.strip()[:160])
        finally:
            _gravar(path, orig)
            if _ler(path) != orig:
                print("  !!  %s NAO VOLTOU IGUAL — parar e ver a mao" % path)
                return 2
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas),
                                       len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
