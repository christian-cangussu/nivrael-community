# -*- coding: utf-8 -*-
"""🩸 A BATERIA DE SABOTAGEM da §31 (冶 3.1, OS OFÍCIOS) — uma guarda que não
morde não guarda.

Mesmo contrato das outras (`_sabota_a_reducao`, `_sabota_as_portas`, …): cada
entrada estraga UMA coisa no código de produção, corre a suite, e exige que ela
fique VERMELHA **a dizer o que é** — nunca a rebentar, e nunca por um motivo
diferente do esperado.

Os cinco grupos de ataque:

  O GATE — 🔴 a que justifica a §31.1: uma rota NOVA dos ofícios passa a
      recusar por reino com um número à mão, e ninguém diz à guarda que ela
      existe; ela tem de a achar SOZINHA na tabela de rotas. E o `< 1` a voltar,
      o payload a mandar `1`, o chat com o seu próprio limiar, o número de volta
      para dentro do texto, o texto do chat a mudar de reino, o cliente sem o
      caminho de "sem número".

  O RETRATO — uma cópia do "quanto falta" a voltar, a lista a regressar ao `10`
      escrito, o retrato a errar o limiar, o 0 real a virar 1.

  O GANHO — 🔴 a que justifica a §31.3: o MOTOR ganha uma coluna de progresso
      nova (o refino passa a contar maestria) e ninguém diz à guarda que o
      endpoint do refino passou a confirmar progresso; ela tem de o achar pelos
      MOTORES. E a forja sem o "antes", o "antes" lido depois do motor, um
      endpoint novo que sobe maestria, a chave escrita à mão, a chave sem a
      onda, o leitor que cria a linha, a energia a acender, o traço a acender.

  OS NOMES — o artefacto cru, o nome sem a chave da arte, um ajudante com o
      caldeirão cru, um caldeirão sem tradução em es, o catálogo a esquecer a
      família, e (na suite do nome) o varredor a voltar a engolir a linha e o
      caldeirão cru no chat.

  O TEXTO E O CONTENTOR — "heavenly" de volta, o botão a "Forjar" de novo, e
      uma f-string que só o Python 3.12 aceita (o contentor é 3.11).

Uso:  python scripts/_sabota_os_oficios.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS = os.path.join(ROOT, "core", "webserver.py")
OF = os.path.join(ROOT, "core", "oficios.py")
AE = os.path.join(ROOT, "core", "alchemy_engine.py")
FE = os.path.join(ROOT, "core", "forge_engine.py")
I18 = os.path.join(ROOT, "core", "i18n.py")
CH = os.path.join(ROOT, "handlers", "alchemy.py")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
MPT = os.path.join(ROOT, "miniapp", "i18n", "pt.json")
LPT = os.path.join(ROOT, "locales", "pt.json")
LES = os.path.join(ROOT, "locales", "es.json")
AUD = os.path.join(ROOT, "scripts", "_audit_nomes_crus.py")
SUITE = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")
NOME = os.path.join(ROOT, "scripts", "_test_relatos_0814.py")


def _nl(path, txt):
    """O pedaço segue os fins de linha do ficheiro (CRLF ou LF)."""
    orig = io.open(path, encoding="utf-8", newline="").read()
    return txt.replace("\n", "\r\n") if "\r\n" in orig else txt


# (rotulo, ficheiro, de, para, pedaco que TEM de aparecer no vermelho[, suite])
SABOTAGENS = [
    # ── O GATE ────────────────────────────────────────────────────────────
    # 🔴 A QUE JUSTIFICA A §31.1. Ninguém diz à guarda que a troca de
    # caldeirão passou a recusar por reino: ela acha-a na tabela de rotas.
    ("uma rota NOVA dos oficios recusa por reino a' mao", WS,
     '    raw_id = payload.get("cauldron_id")\n',
     '    raw_id = payload.get("cauldron_id")\n'
     '    if int(getattr(request, "realm", 0) or 0) < 1:\n'
     '        return _json({"ok": False, "reason": "realm_locked"}, status=200)\n',
     "`api_alchemy_equip_cauldron`"),
    ("a leitura volta ao `< 1` escrito", WS,
     "        realm_locked = alchemy_realm_locked(player)\n",
     "        realm_locked = int(player.realm or 0) < 1\n",
     "`api_alchemy_recipes` (/alchemy_recipes) decide pelo dono"),
    ("o payload volta a mandar `1`", WS,
     '        "min_realm_required": ALCHEMY_MIN_REALM,\n        "alchemy": {\n',
     '        "min_realm_required": 1,\n        "alchemy": {\n',
     "limiar do MOTOR"),
    ("um SEGUNDO limiar nasce no motor", AE,
     "ALCHEMY_MIN_REALM = 1\n",
     "ALCHEMY_MIN_REALM = 1\nif True:\n    ALCHEMY_MIN_REALM = 1\n",
     "escrito UMA vez"),
    ("o chat volta ao seu `realm < 1`", CH,
     "        if alchemy_realm_locked(player):\n            from telegram import",
     "        if player.realm < 1:\n            from telegram import",
     "o chat (`/alquimia`)"),
    ("o numero volta para DENTRO do texto", MPT,
     '"alch_locked_msg": "Avance para {realm} (Reino {n}) para começar a refinar pílulas.",',
     '"alch_locked_msg": "Avance para Qi Condensation (Reino 1) para começar a refinar pílulas.",',
     "`alch_locked_msg` (pt)"),
    ("o texto do chat passa a dizer outro reino", LPT,
     "(Reino 1) para desbloquear a Alquimia.",
     "(Reino 2) para desbloquear a Alquimia.",
     "o texto do chat (pt)"),
    ("o cliente perde o caminho de 'sem numero'", TABS,
     "                {Number.isInteger(data.min_realm_required)\n"
     '                  ? t("alch_locked_msg", { realm: realmName(data.min_realm_required), n: data.min_realm_required })\n'
     '                  : t("alch_err_realm_locked")}\n',
     '                {t("alch_locked_msg", { realm: realmName(data.min_realm_required), n: data.min_realm_required })}\n',
     "o cliente escreve o reino"),

    # ── O RETRATO ─────────────────────────────────────────────────────────
    ("uma copia do 'quanto falta' volta (o Fogo)", WS,
     '                "xp_to_next": _rf["xp_to_next"],\n',
     '                "xp_to_next": (SOUL_FIRE_TIERS[sf_tier + 1]["xp_req"] if not at_max else None),\n',
     "nenhuma copia"),
    ("a lista da Forja volta ao `10` escrito", WS,
     "            m_info = retrato_receita_forja(mastery)\n",
     '            m_info = get_forge_mastery_next_info(mastery) if mastery else {\n'
     '                "at_max": False, "forges": 0, "next_forges": 10, "next_level": 2,\n'
     '            }\n',
     "monta o oficio e a maestria pelo dono"),
    ("o retrato erra o limiar da maestria", OF,
     '    nxt = _proximo(MASTERY_LEVELS, level, MAX_MASTERY_LEVEL, "crafts_req")\n',
     '    nxt = _proximo(MASTERY_LEVELS, level - 1, MAX_MASTERY_LEVEL, "crafts_req")\n',
     "o retrato bate"),
    ("o 0 real vira o valor de criacao", OF,
     "    return int(omissao if v is None else v)\n",
     "    return int(v or omissao)\n",
     "um 0 real"),

    # ── O GANHO ───────────────────────────────────────────────────────────
    # 🔴 A QUE JUSTIFICA A §31.3. O refino passa a contar maestria no MOTOR e
    # ninguém diz à guarda que o endpoint do refino confirma progresso.
    ("o MOTOR ganha progresso novo (o refino conta maestria)", FE,
     '    if not duplicate: return None, "no_duplicate_found"\n',
     '    if not duplicate: return None, "no_duplicate_found"\n'
     '    target.forges_count += 1\n',
     "`api_forge_refine`"),
    ("a forja deixa de ler o 'antes'", WS,
     "        _antes_of = (await _of.ler_antes_forja(session, user_id, recipe_id)\n"
     "                     if _onda_on() else None)\n",
     "        _antes_of = None\n",
     "`api_forge_craft` confirma progresso"),
    ("o Fogo le' o 'antes' DEPOIS do motor", WS,
     "        _antes_fogo = await _of.ler_antes_fogo(session, user_id) if _onda_on() else None\n\n"
     "        sf, xp_gained, leveled = await feed_beast_core_to_soul_fire(\n"
     "            session, user_id, realm)\n",
     "        sf, xp_gained, leveled = await feed_beast_core_to_soul_fire(\n"
     "            session, user_id, realm)\n"
     "        _antes_fogo = await _of.ler_antes_fogo(session, user_id) if _onda_on() else None\n",
     "`api_alchemy_feed_core` confirma progresso"),
    ("um endpoint NOVO sobe maestria sem ganho", WS,
     "async def _resolve_ore_refund(",
     "async def api_forge_treino(request):\n"
     "    from core.forge_engine import increment_forge_mastery\n"
     "    async with get_session_factory()() as session:\n"
     "        await increment_forge_mastery(session, 1, 1)\n"
     "    return _json({\"ok\": True})\n\n\n"
     "async def _resolve_ore_refund(",
     "`api_forge_treino`"),
    ("a chave escrita a' mao", WS,
     '        "mastery_leveled_up": any_mastery_leveled,\n',
     '        "mastery_leveled_up": any_mastery_leveled,\n        "oficio_ganho": None,\n',
     "nunca escreve `oficio_ganho`"),
    ("a chave sai sem a onda", OF,
     '    return {"oficio_ganho": g} if onda_on(flag) else {}\n',
     '    return {"oficio_ganho": g}\n',
     "so' viaja com a onda"),
    ("o leitor do 'antes' passa a criar", OF,
     '    return {"oficio": retrato_forja(skill), "receita": retrato_receita_forja(mastery)}\n',
     '    await session.flush()\n'
     '    return {"oficio": retrato_forja(skill), "receita": retrato_receita_forja(mastery)}\n',
     "`ler_antes_forja` so' LE"),
    ("a ENERGIA passa a acender", OF,
     'EIXOS = ("oficio", "receita", "fogo")\n',
     'EIXOS = ("oficio", "receita", "fogo", "energia")\n',
     "REBENTA"),
    ("o TRACO passa a acender", OF,
     '_CONQUISTA = {"oficio": "tier", "receita": "level", "fogo": "tier"}\n',
     '_CONQUISTA = {"oficio": "tier", "receita": "crafts_count", "fogo": "tier"}\n',
     "acende SO'"),

    # ── OS NOMES ──────────────────────────────────────────────────────────
    ("a receita da Forja volta ao nome cru", WS,
     '                "artifact_name": catalog_name(lang, "art", blueprint),\n',
     '                "artifact_name": blueprint.name,\n',
     "nenhuma leitura crua"),
    ("o nome traduzido SEM a chave da arte", WS,
     '                "artifact_art_key": catalog_art_key(blueprint),\n',
     "",
     "CHAVE da arte"),
    ("um AJUDANTE devolve o caldeirao cru", WS,
     '        "name": catalog_name(lang, "cauldron", cauldron),\n',
     '        "name": cauldron.name,\n',
     "_alchemy_cauldron_dict"),
    ("um caldeirao fica sem nome em es", LES,
     '"cauldron_7_name":',
     '"cauldron_7_nome":',
     "os 7 caldeiroes"),
    ("o catalogo esquece a familia `cauldron`", I18,
     '                  "cauldron"}\n',
     '                  }\n',
     "serve a familia `cauldron`"),
    ("o varredor volta a engolir a LINHA (`pill_name`)", AUD,
     "                # 冶 2026-09-29 — o `NOT_CATALOG` deixou de tirar a LINHA da conta.\n",
     "                if NOT_CATALOG.search(line):\n                    continue\n",
     "CONTINUA A VER", NOME),
    ("o caldeirao volta cru no chat", CH,
     "*{_cname(lang, 'cauldron', cauldron)}* (Tier",
     "*{cauldron.name}* (Tier",
     "CATRACA", NOME),

    # ── O TEXTO E O CONTENTOR ─────────────────────────────────────────────
    ("'HEAVENLY' volta ao pt", MPT,
     '"alch_result_heavenly": "✦ CELESTIAL ✦",',
     '"alch_result_heavenly": "✦ HEAVENLY ✦",',
     "\"heavenly\""),
    ("o botao da Alquimia volta a 'Forjar'", MPT,
     '"alch_craft_btn": "Refinar Pílula",',
     '"alch_craft_btn": "Forjar Pílula",',
     "REFINA"),
    ("uma f-string que so' o 3.12 aceita", CH,
     "*{_cname(lang, 'cauldron', cauldron)}* (Tier",
     '*{_cname(lang, "cauldron", cauldron)}* (Tier',
     "py311"),
]


def _corre(suite):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(
        [sys.executable, suite],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=900,
        # ⚠️ `text=True` sozinho descodifica com o codec do LOCALE (cp1252 no
        # Windows) e rebenta no primeiro 漢字 da suite.
        encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.returncode and (r.stderr or "") or "")


def _vermelhos(saida, suite):
    if suite == NOME:
        # a suite do nome escreve `  FAIL  <rotulo> — <detalhe>`
        return [l for l in saida.split("\n") if "FAIL" in l and "0 failed" not in l]
    return [l for l in saida.split("\n") if l.strip().startswith("x ")]


def _rodape_ok(saida, suite):
    return ("passed" in saida) if suite == NOME else ("asserts verdes" in saida)


def run():
    falhas = []
    for ent in SABOTAGENS:
        rot, path, de, para, agulha = ent[:5]
        suite = ent[5] if len(ent) > 5 else SUITE
        orig = io.open(path, encoding="utf-8", newline="").read()
        de, para = _nl(path, de), _nl(path, para)
        if orig.count(de) != 1:
            falhas.append("%-54s o PEDACO nao existe (x%d) — a bateria esta' "
                          "desactualizada" % (rot, orig.count(de)))
            print("  XX  " + falhas[-1])
            continue
        io.open(path, "w", encoding="utf-8", newline="").write(orig.replace(de, para, 1))
        try:
            rc, saida = _corre(suite)
            verm = _vermelhos(saida, suite)
            rebentou = not _rodape_ok(saida, suite)
            mordeu = rc == 1 and verm and not rebentou
            acertou = mordeu and (not agulha or any(agulha in l for l in verm))
            if acertou:
                print("  ok  %-54s mordeu (%d vermelhos)" % (rot, len(verm)))
            elif rebentou:
                falhas.append("%-54s REBENTOU — uma guarda que rebenta nao e' uma "
                              "guarda vermelha (%s)" % (rot, saida.strip()[-160:]))
                print("  XX  " + falhas[-1])
            elif not mordeu:
                falhas.append("%-54s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-54s ficou vermelha pelo motivo ERRADO (esperava %r; "
                              "veio %r)" % (rot, agulha, [v.strip()[:140] for v in verm[:2]]))
                print("  XX  " + falhas[-1])
        finally:
            io.open(path, "w", encoding="utf-8", newline="").write(orig)
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas), len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
