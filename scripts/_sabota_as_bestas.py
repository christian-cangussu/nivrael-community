# -*- coding: utf-8 -*-
"""🐾 A BATERIA DE SABOTAGEM da §33 (`_test_web_c_superficies.py`) — 3.3, 01/10.

Uma guarda que não morde não guarda. Cada entrada estraga UMA coisa no código,
corre a suite, e exige que ela fique VERMELHA a dizer o quê.

As regras são as das baterias anteriores:
  · uma guarda que REBENTA não é uma guarda vermelha (exige-se o rodapé);
  · uma sabotagem que não encontra o alvo dá-se por boa — cada alvo tem de
    aparecer EXACTAMENTE uma vez, verificado antes, ruidosamente;
  · os BYTES voltam iguais (lê com `newline=""`; o alvo ganha o fim de linha
    do ficheiro) — e cada ficheiro é conferido no fim.

Uso:  python scripts/_sabota_as_bestas.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUP = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")
BESTAS = os.path.join(ROOT, "core", "bestas.py")
MOTOR = os.path.join(ROOT, "core", "beast_engine.py")
WEB = os.path.join(ROOT, "core", "webserver.py")
CHAT = os.path.join(ROOT, "handlers", "beasts.py")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
ARNES = os.path.join(ROOT, "scripts", "_dev_serve_miniapp.py")
MI_ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")
MI_EN = os.path.join(ROOT, "miniapp", "i18n", "en.json")
LO_PT = os.path.join(ROOT, "locales", "pt.json")

# (rótulo, ficheiro, de, para, pedaço que TEM de aparecer no vermelho)
SABOTAGENS = [
    # ── 33.1 o dono ─────────────────────────────────────────────────────────
    ("o treino volta a escrever o limiar a' mao", MOTOR,
     "    player.spirit_stones -= cost\n"
     "    beast.exp = (beast.exp or 0) + xp_gained\n"
     "    exp_needed = limiar_xp(beast.level)",
     "    player.spirit_stones -= cost\n"
     "    beast.exp = (beast.exp or 0) + xp_gained\n"
     "    exp_needed = beast.level * 100",
     "nenhum `X.level * 100`"),
    ("a lista volta a montar a linha a' mao", WEB,
     "        return _bestas.serializar(b, catalog_map.get(b.catalog_id), _lang_b, food_mult)",
     '        return {"id": int(b.id), "effective_stats": {}}',
     "pede a linha ao dono"),
    ("a linha troca a ORDEM das chaves", BESTAS,
     '        "rank": r["rank"],\n        "rank_idx": r["rank_idx"],',
     '        "rank_idx": r["rank_idx"],\n        "rank": r["rank"],',
     "chaves de HOJE"),
    ("o XP passa a ACENDER", BESTAS,
     '_CONQUISTA = {"nivel": "level", "posto": "rank_idx"}',
     '_CONQUISTA = {"nivel": "level", "posto": "rank_idx", "xp": "exp"}',
     "XP sozinho nao acende"),
    ("o 'antes' le' a ENTIDADE (o motor herdaria os valores velhos)", BESTAS,
     "        select(PlayerBeast.level, PlayerBeast.exp, PlayerBeast.rank, PlayerBeast.catalog_id)",
     "        select(PlayerBeast)",
     "COLUNAS"),
    ("o 'antes' deixa de TRANCAR a linha", BESTAS,
     "        .with_for_update()\n    )).first()",
     "    )).first()",
     "TRANCADO"),
    ("o treino le' o 'antes' mesmo SEM a onda", WEB,
     "        _antes = await _bestas.ler_antes(session, user_id, beast_id) if _onda_on() else None\n"
     "        if count is None or count == 1:",
     "        _antes = await _bestas.ler_antes(session, user_id, beast_id)\n"
     "        if count is None or count == 1:",
     "nem trinco a mais"),
    ("a evolucao esquece o ganho na resposta", WEB,
     '        "cores_used": int(result.get("cores_used", 0)) if result.get("cores_used") else 0,\n'
     "        **_bestas.no_payload(_g),\n",
     '        "cores_used": int(result.get("cores_used", 0)) if result.get("cores_used") else 0,\n',
     "TODA porta que muda nivel/posto"),
    ("a recolha esquece o 'antes'", WEB,
     "        _antes = await _bestas.ler_antes(session, user_id, beast_id) if _onda_on() else None\n"
     "        result = await collect_expedition(",
     "        _antes = None\n"
     "        result = await collect_expedition(",
     "TODA porta que muda nivel/posto"),
    ("o ganho viaja SEM a chave-mestra", BESTAS,
     '    return {"besta_ganho": g} if onda_on(flag) else {}',
     '    return {"besta_ganho": g}',
     "so' viaja com a chave-mestra"),
    ("uma RECUSA leva ganho", WEB,
     '            _g = await _bestas.ganho_da_acao(session, beast_id, _antes) if res.get("success") else None\n'
     "            await session.commit()\n"
     "            return _json({",
     "            _g = await _bestas.ganho_da_acao(session, beast_id, _antes)\n"
     "            await session.commit()\n"
     "            return _json({",
     "uma recusa NUNCA leva ganho"),

    # ── 33.2 os nomes ───────────────────────────────────────────────────────
    ("o dono da habilidade devolve a frase inglesa", MOTOR,
     '    return catalog_text(lang, "beast", getattr(catalog, "id", None), "ability", raw)',
     "    return raw",
     "o dono da habilidade"),
    ("o chat volta a ler a habilidade crua", CHAT,
     "{escape_markdown(beast_ability_text(lang, catalog) if catalog else '?')}",
     "{escape_markdown(catalog.special_ability if catalog else '?')}",
     "o detalhe do chat"),
    ("uma habilidade em pt volta ao ingles", LO_PT,
     '"beast_9_ability": "Renascimento — +25% de Base de Cultivo e revive 1x por tribulação",',
     '"beast_9_ability": "Rebirth — +25% CB and revives 1x per tribulation",',
     "15 habilidades"),
    ("o elemento Ouro perde a palavra em es", MI_ES,
     '  "world_element_gold": "Oro",\n',
     "",
     "TODO elemento"),
    ("um bonus perde o nome em en", MI_EN,
     '  "beasts_bonus_hp_mult": "Health",\n',
     "",
     "TODO bonus"),
    ("o companheiro volta a imprimir o posto e o elemento CRUS", TABS,
     "{postoDaBesta(companion.rank)} · {nvDaBesta(companion.level)} · {elementoDaBesta(companion.element)}",
     "{companion.rank} · {nvDaBesta(companion.level)} · {companion.element}",
     "imprime o posto/elemento CRU"),
    ("o dono do posto traduz mesmo SEM a chave-mestra", TABS,
     "      if (!obraOn()) return rank;\n",
     "",
     "SEM a chave-mestra"),
    ("o espelho volta a ter Mitico antes de Lendario", TABS,
     '      const list = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Divine"];',
     '      const list = ["Common", "Uncommon", "Rare", "Epic", "Mythic", "Legendary", "Divine"];',
     "o espelho dos postos"),

    # ── 33.3 o ecra ─────────────────────────────────────────────────────────
    ("a aba le' a chave-mestra a' mao", TABS,
     "      const onda = obraOn();",
     "      const onda = ondaCultOn();",
     "UM leitor da chave-mestra"),
    ("um estado nasce DEPOIS do return (React #310)", TABS,
     "      const b = owned.find(x => x.id === selId) || owned.find(x => x.is_companion) || owned[0];",
     "      const [tarde33, setTarde33] = useState(0);\n"
     "      const b = owned.find(x => x.id === selId) || owned.find(x => x.is_companion) || owned[0];",
     "React #310"),
    ("acende ao TOQUE, antes da confirmacao", TABS,
     "          const res = await api(rota, corpo);",
     '          setAcende({ id: alvo.id, eixos: ["nivel"], k: 1 });\n'
     "          const res = await api(rota, corpo);",
     "so' uma resposta `ok: true`"),
    ("a companheira passa a ACENDER", TABS,
     '              <MarcaOnda estado="got" acende={eixos.indexOf("nivel") >= 0} />',
     '              <MarcaOnda estado="got" acende={eixos.indexOf("nivel") >= 0 || !!v.is_companion} />',
     "so' o posto e o nivel acendem"),
    ("o cliente inventa o denominador da escada", TABS,
     "      const nPostos = ranks.length;",
     "      const nPostos = ranks.length || 7;",
     "nunca um `|| 7`"),
    ("o fio de XP aparece no TECTO", TABS,
     "            {!noTecto && precisa > 0 && (",
     "            {precisa > 0 && (",
     "no tecto nao ha' fio"),
    ("o treino oferece-se com os dados VELHOS", TABS,
     "      const podeTreinar = fresco && !busy && !naExp && !noTecto && faltaPedras <= 0;",
     "      const podeTreinar = !busy && !naExp && !noTecto && faltaPedras <= 0;",
     "enquanto os dados nao apanham"),
    ("a lista aparece com UMA besta so'", TABS,
     "      const lista = owned.length > 1 ? (",
     "      const lista = owned.length > 0 ? (",
     "a lista so' existe"),
    ("nasce um emoji no corpo novo", TABS,
     '            <span>{t("beasts_onda_tuas")}</span>',
     '            <span>{"\U0001F43E " + t("beasts_onda_tuas")}</span>',
     "sem emoji"),
    ("uma chave da onda falta em es", MI_ES,
     '  "beasts_onda_limite": "Límite actual — la bestia está en su nivel máximo.",\n',
     "",
     "chaves da onda das bestas"),
    ("o recibo faz a conta do limiar no cliente", TABS,
     "{ xp: fmtFull(res.xp_gained || 0), a: fmtFull(a.exp),\n"
     "                                               b: fmtFull(d.exp), need: fmtFull(d.exp_needed) }",
     "{ xp: fmtFull(res.xp_gained || 0), a: fmtFull(a.exp),\n"
     "                                               b: fmtFull(d.exp), need: fmtFull(d.level * 100) }",
     "o recibo sai do `besta_ganho`"),

    # ── 33.4 o arnes ────────────────────────────────────────────────────────
    ("o arnes deixa uma rota no catch-all", ARNES,
     '    "beasts/level_up": "api_beasts_level_up",\n',
     "",
     "correm o HANDLER REAL"),
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
    # a conferencia final: TODOS os ficheiros tocados voltaram byte a byte
    for path, orig in originais.items():
        if _ler(path) != orig:
            print("  !!  %s NAO VOLTOU IGUAL no fim" % path)
            return 2
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas), len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
