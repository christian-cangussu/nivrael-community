# -*- coding: utf-8 -*-
"""🎒 A BATERIA DE SABOTAGEM da §32 (`_test_web_c_superficies.py`) — 3.2, 30/09.

Uma guarda que não morde não guarda. Cada entrada estraga UMA coisa no código,
corre a suite, e exige que ela fique VERMELHA a dizer o quê.

As regras são as das baterias anteriores, mais a de hoje:
  · uma guarda que REBENTA não é uma guarda vermelha (exige-se o rodapé);
  · uma sabotagem que não encontra o alvo dá-se por boa — cada alvo tem de
    aparecer EXACTAMENTE uma vez, verificado antes, ruidosamente;
  · ⚠️ os BYTES voltam iguais (lê com `newline=""`; o alvo ganha o fim de linha
    do ficheiro) — a bateria antiga convertia CRLF em LF sem dizer nada.

Uso:  python scripts/_sabota_o_inventario.py
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUP = os.path.join(ROOT, "scripts", "_test_web_c_superficies.py")
ANEL = os.path.join(ROOT, "core", "anel.py")
ITENS = os.path.join(ROOT, "core", "itens.py")
WEB = os.path.join(ROOT, "core", "webserver.py")
INV = os.path.join(ROOT, "handlers", "inventory.py")
MON = os.path.join(ROOT, "core", "monetization.py")
BEAST = os.path.join(ROOT, "core", "beast_engine.py")
TABS = os.path.join(ROOT, "miniapp", "components", "tabs.js")
ES = os.path.join(ROOT, "miniapp", "i18n", "es.json")

# (rótulo, ficheiro, de, para, pedaço que TEM de aparecer no vermelho)
SABOTAGENS = [
    # ── 32.1 o dono do anel ─────────────────────────────────────────────────
    ("a expansao volta a ser ABSOLUTA (apaga os lugares comprados)", ANEL,
     "    return int(max_slots or base) + (RING_MAX_SLOTS[t + 1] - base)",
     "    return RING_MAX_SLOTS[t + 1]",
     "ADITIVA"),
    ("o retrato manda as chaves novas mesmo OFF", ANEL,
     '    if onda:\n        out["max_tier"] = MAX_RING_TIER',
     '    if True:\n        out["max_tier"] = MAX_RING_TIER',
     "chaves de HOJE"),
    ("os lugares passam a ACENDER", ANEL,
     'EIXOS_QUE_ACENDEM = ("tier",)',
     'EIXOS_QUE_ACENDEM = ("tier", "max_slots")',
     "NUNCA acendem"),
    ("a resposta leva o ganho mesmo OFF", ANEL,
     '    if onda:\n        out["anel_ganho"] = ganho(antes_depois)',
     '    if True:\n        out["anel_ganho"] = ganho(antes_depois)',
     "resposta e' a de HOJE"),
    ("a rota volta a fazer a conta a' mao", WEB,
     "            _ad = _anel.expandir(ring)",
     "            ring.tier = tier + 1\n"
     "            ring.max_slots = int(ring.max_slots or 50) + 300\n"
     '            _ad = {"tier": {"antes": tier, "depois": tier + 1}, '
     '"max_slots": {"antes": 0, "depois": int(ring.max_slots)}}',
     "nenhuma conta do anel fora"),
    ("a rota deixa de TRANCAR o jogador", WEB,
     "                select(Player).where(Player.telegram_id == user_id).with_for_update()\n"
     "            )).scalar_one_or_none()\n"
     "            if not player:\n"
     '                return _err("player_not_found", 404)\n'
     "            # 🎒 3.2",
     "                select(Player).where(Player.telegram_id == user_id)\n"
     "            )).scalar_one_or_none()\n"
     "            if not player:\n"
     '                return _err("player_not_found", 404)\n'
     "            # 🎒 3.2",
     "TRANCADO"),
    ("o inventario volta a montar o anel a' mao", WEB,
     '            "ring": _anel.retrato(ring.tier, ring.max_slots, used_slots, _onda_on()),',
     '            "ring": {"tier": int(ring.tier or 1), "max_slots": int(ring.max_slots or 50), '
     '"used_slots": int(used_slots), "can_upgrade": True},',
     "retrato do dono"),
    ("o botao do chat volta a anunciar o maximo ABSOLUTO", INV,
     "        next_max = _anel.proximo_max(ring.tier, ring.max_slots)",
     "        next_max = RING_MAX_SLOTS[next_tier]",
     "conta que a expansao FAZ"),

    # ── 32.2 os nomes ───────────────────────────────────────────────────────
    ("a armadilha perde o nome no dono", ITENS,
     '    "beast_trap": "inv_item_beast_trap",\n',
     "",
     "nome PROPRIO"),
    ("o inventario volta ao nome CRU", WEB,
     "                name = _itens.nome(",
     '                name = f"{itype} #{iid}" or _itens.nome(',
     "tipo cru"),
    ("o chat volta ao ingles fixo", INV,
     "            name = _itens.nome(lang, inv.item_type, inv.item_id)\n"
     '            lines.append(f"{emoji} *{name}* ×{inv.quantity}")',
     '            name = inv.item_type.replace("_", " ").title()\n'
     '            lines.append(f"{emoji} *{name}* ×{inv.quantity}")',
     "MESMO dono"),
    ("um escritor novo mete um tipo SEM nome na mochila", MON,
     'add_item_to_inventory(session, player.telegram_id, "beast_egg", int(beast_id), qty)',
     'add_item_to_inventory(session, player.telegram_id, "beast_pup", int(beast_id), qty)',
     "TODO tipo"),

    # ── 32.3 a tabela ───────────────────────────────────────────────────────
    ("a tabela aparece SEM a onda", TABS,
     "      const tabela = obraOn();",
     "      const tabela = true;",
     "UM leitor"),
    ("a quantidade volta a ser ABREVIADA", TABS,
     "      const qtd = fmtFull(it.quantity || 0);",
     "      const qtd = fmtNum(it.quantity || 0);",
     "INTEIRA"),
    ("a coluna da qualidade aparece em TODA a familia", TABS,
     "                const comQualidade = list.some(it => qualidadeDoItem(it) != null);",
     "                const comQualidade = true;",
     "coluna da qualidade"),
    ("a captura ganha uma raridade SEM palavra", BEAST,
     'TRAP_QUALITY_ORDER = {"normal": 0, "common": 1, "rare": 2, "epic": 3, "mythic": 4, "legendary": 5}',
     'TRAP_QUALITY_ORDER = {"normal": 0, "common": 1, "rare": 2, "epic": 3, "mythic": 4, "legendary": 5, "celestial": 6}',
     "toda raridade"),
    ("o espirito volta a sair em ingles", TABS,
     '{entry.spirit_name || t("market_art_spirit")',
     '{entry.spirit_name || "Awakened Spirit"',
     "espirito ja' nao saem crus"),
    ("o mercado volta a mostrar o grau em ingles", TABS,
     "${nomeDoGrau(listing.grade, listing.grade_name)}",
     "${listing.grade_name}",
     "grade_name"),

    # ── 32.4 o anel no ecra ─────────────────────────────────────────────────
    ("o anel desenha a SUA marca (duas copias da gramatica)", TABS,
     "<MarcaOnda estado={estado} acende={acendeTier && i === Number(g.tier.depois)} />",
     '<span className="corpo-nucleo-acende" />',
     "a marca tem UM dono"),
    ("o anel acende ao TOQUE, antes da confirmacao", TABS,
     '          const res = await api("inventory/ring_upgrade", {});',
     '          setAnelGanho({ acende: ["tier"] });\n'
     '          const res = await api("inventory/ring_upgrade", {});',
     "UNICO sitio"),
    ("o cliente inventa o denominador", TABS,
     "      const max = Number(ring.max_tier) || 0;",
     "      const max = Number(ring.max_tier) || 5;",
     "nunca um `|| 5`"),
    ("uma chave do anel falta em es", ES,
     '  "inv_ring_faltam": "Faltan {n} piedras espirituales",\n',
     "",
     "chaves do inventario"),
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
            falhas.append("%-56s ALVO NAO ENCONTRADO (%d ocorrencias) — a sabotagem "
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
                print("  ok  %-56s mordeu (%d vermelhos)" % (rot, len(vermelhos)))
            elif rebentou:
                falhas.append("%-56s REBENTOU — uma guarda que rebenta nao e' uma guarda "
                              "vermelha" % rot)
                print("  XX  " + falhas[-1])
                print("      " + (saida.strip().split("\n") or [""])[-1][:200])
            elif not mordeu:
                falhas.append("%-56s FICOU VERDE" % rot)
                print("  XX  " + falhas[-1])
            else:
                falhas.append("%-56s ficou vermelha pelo motivo ERRADO (esperava %r)"
                              % (rot, agulha))
                print("  XX  " + falhas[-1])
                for l in vermelhos[:3]:
                    print("      " + l.strip()[:200])
        finally:
            _gravar(path, orig)
            if _ler(path) != orig:
                print("  !!  %s NAO VOLTOU IGUAL — parar e ver a mao" % path)
                return 2
    print()
    print("%d/%d sabotagens mordem" % (len(SABOTAGENS) - len(falhas), len(SABOTAGENS)))
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(run())
