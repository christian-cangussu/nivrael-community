# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM da §30 — uma guarda que nao morde nao guarda.

Mesmo contrato das outras (`_sabota_as_portas`, `_sabota_a_cena`, ...): cada
entrada estraga UMA coisa no codigo de producao, corre a suite, e exige que ela
fique VERMELHA **a dizer o que e'** — nunca a rebentar, e nunca por um motivo
diferente do esperado.

Os quatro grupos de ataque:

  O REGISTO E OS SITIOS — 🔴 o que justifica a §30.3: uma frase NOVA entra no
      registo e ninguem diz a' guarda onde ela aparece; ela tem de achar SOZINHA
      a tira de preparo que a mostra sem a poder recolher. E uma frase de PROVA
      a entrar no registo; e os sistemas do cliente a divergirem do servidor.

  O GATILHO NO SERVIDOR — marcar depois do commit, marcar a recusa do ritual,
      desequipar a contar como equipar, uma marca fora do registo, a onda OFF a
      escrever, agir outra vez a desfazer o recolhido, o TOQUE a servir de
      gatilho, o `/player` a mandar a chave sempre.

  O CLIENTE — sem preferencia lida a valer "recolhido", o recolher optimista
      (antes da resposta), o `display` no lugar do `visibility` (o comando
      volta a mexer), «Ja' percebi» a nascer so' depois da accao, o toque que
      falha em silencio.

  A PROVA E A CASA — um numero dentro do `Explica`, o estado ("ainda nao
      equipou") a recolher, a secao das Configuracoes sem a onda, o pt a virar
      Portugal, a chegada do Eu sem o refresh.

Uso:  python scripts/_sabota_a_reducao.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "miniapp", "components", "ui.js")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
APP = os.path.join(ROOT, "miniapp", "components", "app.js")
PT = os.path.join(ROOT, "miniapp", "i18n", "pt.json")
WS = os.path.join(ROOT, "core", "webserver.py")
EXP = os.path.join(ROOT, "core", "explicacoes.py")
SUITE = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")


def _nl(path, txt):
    """O `app.js` pode estar em CRLF na copia de trabalho; o pedaco segue-o."""
    orig = io.open(path, encoding="utf-8", newline="").read()
    return txt.replace("\n", "\r\n") if "\r\n" in orig else txt


# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer na mensagem vermelha)
SABOTAGENS = [
    # ── O REGISTO E OS SITIOS ─────────────────────────────────────────────
    # 🔴 A QUE JUSTIFICA A §30.3. Ninguem diz a' guarda onde "Com o que voce vai
    # lutar" aparece: a lista vem do REGISTO, e ela tem de encontrar sozinha a
    # `CenaPreparo` que a desenha fora do `Explica`.
    ("uma frase NOVA entra no registo (e ninguem a liga)", UI,
     '      equipar:      ["cena_entrada_com"],\n',
     '      equipar:      ["cena_entrada_com", "cena_preparo_titulo"],\n',
     "DENTRO do `Explica` do SEU"),
    ("uma frase de PROVA entra no registo", UI,
     '      meditar:      ["chegada_porque_meditar", "chegada_porque_meditacao"],\n',
     '      meditar:      ["chegada_porque_meditar", "chegada_porque_meditacao", "chegada_porque_recompensa"],\n',
     "NUNCA entram no registo"),
    ("o servidor perde um sistema que o cliente tem", EXP,
     '    "corpo_mer": ("api_world_meridian_start", "api_world_meridian_break"),\n',
     "",
     "sao os do servidor"),

    # ── O GATILHO NO SERVIDOR ─────────────────────────────────────────────
    ("a meditacao marca DEPOIS do commit", WS,
     '        _explica_apto(player, "meditar")\n\n        await session.commit()\n\n'
     '    return _json({\n        "ok": True,\n        "meditation_type": med_key,',
     '        await session.commit()\n        _explica_apto(player, "meditar")\n\n'
     '    return _json({\n        "ok": True,\n        "meditation_type": med_key,',
     "ANTES do commit"),
    ("o ritual RECUSADO tambem marca", WS,
     '            if isinstance(result, dict) and result.get("ok"):\n'
     '                from core.explicacoes import marcar_apto as _explica_apto\n'
     '                _explica_apto(player, "corpo_mer")\n'
     '            await session.commit()\n'
     '            return _json(result, status=200)\n'
     '    except Exception as e:\n'
     '        logger.exception("world/meridian_start failed',
     '            from core.explicacoes import marcar_apto as _explica_apto\n'
     '            _explica_apto(player, "corpo_mer")\n'
     '            await session.commit()\n'
     '            return _json(result, status=200)\n'
     '    except Exception as e:\n'
     '        logger.exception("world/meridian_start failed',
     "so' marca com o ritual ACEITE"),
    ("desequipar passa a contar como equipar", WS,
     '        if equip and tech.tech_type == "combat":\n'
     '            from core.explicacoes import marcar_apto as _explica_apto\n',
     '        if tech.tech_type == "combat":\n'
     '            from core.explicacoes import marcar_apto as _explica_apto\n',
     "equipar so' conta com equip=TRUE"),
    ("uma marca nasce FORA do registo (parar de meditar)", WS,
     "        ended_end = player.meditation_end  # capture before clearing (SEC 2026-06-01)\n",
     "        ended_end = player.meditation_end  # capture before clearing (SEC 2026-06-01)\n"
     "        from core.explicacoes import marcar_apto as _explica_apto\n"
     '        _explica_apto(player, "meditar")\n',
     "marcas no webserver = os endpoints do registo"),
    ("o `/player` manda a chave SEMPRE (o main deixa de ser igual)", WS,
     '            **({"explicacoes": _explicacoes} if _explicacoes is not None else {}),\n',
     '            "explicacoes": _explicacoes or {},\n',
     "chave CONDICIONAL"),
    ("a onda OFF passa a escrever", EXP,
     "    if not _onda(flag):\n        return False\n    atual = estados(player)\n",
     "    atual = estados(player)\n",
     "com a onda OFF a accao NAO escreve"),
    ("agir outra vez DESFAZ o recolhido", EXP,
     "    if atual.get(sistema) is not None:\n        return False\n",
     "    if atual.get(sistema) == APTO:\n        return False\n",
     "NUNCA desfaz o recolhido"),
    ("o TOQUE vira gatilho (recolhe sem accao)", EXP,
     '    if est != APTO:\n        return False, "nao_apto"\n',
     "",
     "o toque nao e' gatilho"),

    # ── O CLIENTE ─────────────────────────────────────────────────────────
    ("sem preferencia lida vale \"recolhido\"", UI,
     '      if (!estados || typeof estados !== "object") return null;\n',
     '      if (!estados || typeof estados !== "object") return "recolhido";\n',
     "sem preferencia LIDA"),
    ("recolhe ANTES da resposta (optimista)", UI,
     "        setBusy(true);\n        try {\n"
     '          const r = await api("settings/update", { explicacao_recolher: sistema });\n',
     '        setBusy(true);\n        setConf({ base: estados, estado: "recolhido" });\n        try {\n'
     '          const r = await api("settings/update", { explicacao_recolher: sistema });\n',
     "nunca perante o toque"),
    ("a frase esconde-se por `display` (o comando volta a mexer)", UI,
     '                         visibility: recolhida ? "hidden" : "visible" }}>\n',
     '                         display: recolhida ? "none" : "block" }}>\n',
     "nunca por `display`"),
    ("«Ja' percebi» so' nasce depois da accao (empurra o botao)", UI,
     '{ visibility: oferece ? "visible" : "hidden" }',
     '{ display: oferece ? "inline-block" : "none" }',
     "existe SEMPRE na linha"),
    ("o toque que falha fica CALADO", UI,
     "          // Sem resposta, nada muda: a frase continua à vista — e diz-se.\n"
     '          haptic("error");\n'
     '          showToast(t("settings_explica_erro"), "err");\n',
     "          // Sem resposta, nada muda.\n",
     "DIZ que nada mudou"),

    # ── A PROVA E A CASA ──────────────────────────────────────────────────
    ("um NUMERO entra num `Explica`", UI,
     '{t("cena_entrada_lugares", { n: usados || 0, max: max })}',
     '<Explica sistema="equipar" estados={explicacoes}>'
     '{t("cena_entrada_lugares", { n: usados || 0, max: max })}</Explica>',
     "dentro de um `Explica` so' mora a frase"),
    ("o ESTADO (\"ainda nao equipou\") passa a recolher", UI,
     '                ) : t("cena_entrada_sem")}\n',
     '                ) : <Explica sistema="equipar" estados={explicacoes}>'
     '{t("cena_entrada_sem")}</Explica>}\n',
     "e' ESTADO e fica sempre"),
    ("as Configuracoes mostram a secao sem a onda", TABS,
     "{obraOn() && <SettingsExplicacoesSection onPlayerRefresh={onPlayerRefresh} />}",
     "<SettingsExplicacoesSection onPlayerRefresh={onPlayerRefresh} />",
     "SO' com a onda"),
    ("o pt vira Portugal (\"Ja' percebi\")", PT,
     '"explica_ja_percebi": "Já entendi",',
     '"explica_ja_percebi": "Já percebi",',
     "pt e' do BRASIL"),
    ("a chegada do Eu perde o refresh", APP,
     "confirmado: sem isto, a do Eu nao o podia pedir. */\n"
     "                             onPlayerRefresh={loadPlayer}\n",
     "confirmado: sem isto, a do Eu nao o podia pedir. */\n",
     "a do Eu recebe-o do App"),
]


def run():
    falhas = []
    for rot, path, de, para, agulha in SABOTAGENS:
        orig = io.open(path, encoding="utf-8", newline="").read()
        de, para = _nl(path, de), _nl(path, para)
        if orig.count(de) != 1:
            falhas.append("%-58s o PEDACO nao existe (x%d) — a bateria esta' "
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
                print("  ok  %-58s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-58s REBENTOU — uma guarda que rebenta nao e' "
                              "uma guarda vermelha" % rot)
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-58s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-58s ficou vermelha pelo motivo ERRADO "
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
