"""QoL-Feedback 2026-08-04 — teste isolado dos 2 reports (SEM DB).

Roda: python -X utf8 scripts/_test_qol_feedback_0804.py

  · **[jogador]** — *"some of the titles are not indicating their benefits,
    especially the ones pertaining to sect like sect heir and co"*.
    DECISÃO ASSADA: título é **cosmético** (Lei §4 — há títulos que vêm de
    marcos VIP/Passe Celestial; se dessem bônus, jade compraria poder). O que
    faltava era a tela DIZER isso. E o pior estava escondido: na `main` os 57
    liam **"+105% cb mult"** de um bônus que, sem `combate_unificado`, vale
    ZERO. Aqui trava-se: (a) `bonus_display` como verdade única — só anuncia o
    que ESTE mundo aplica; (b) os 3 bônus órfãos (evasion/alchemy_quality/
    tribulation_severity_mult) deixam de ser anunciados; (c) a nota honorífica
    nas 2 superfícies; (d) a #28 "Sect Heir" passa a DIZER que dispara ao
    ENTRAR (o posto heir é a #30) — por force-sync, porque o runner é
    insert-only e a string do título não se toca (vive no unlocked_titles de
    19 jogadores).

  · **[jogador]** — *"when sweeping dungeon, sometimes getting 'tribute of the land'
    but it is general"*. A linha nomeava o CONTINENTE e nunca o item; o
    servidor tinha o `loot` e a tela deitava-o fora. Aqui trava-se: a linha
    server-resolved com item+quantidade, Línghé a dizer PEDRAS (a frase
    "material nativo" mentia lá), `×N` quando a varredura acerta mais de uma
    vez, e o tributo do CHEFE — que rolava e ninguém dizia — a chegar às 2
    superfícies.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

if "telegram" not in sys.modules:
    _tg = types.ModuleType("telegram")
    _tg.Update = type("Update", (), {})
    _tg_err = types.ModuleType("telegram.error")

    class _TgErr(Exception):
        retry_after = 0
    _tg_err.RetryAfter = _TgErr
    _tg_err.TimedOut = _TgErr
    _tg_err.NetworkError = _TgErr
    _tg.error = _tg_err
    sys.modules["telegram"] = _tg
    sys.modules["telegram.error"] = _tg_err

import core.achievement_engine as ach  # noqa: E402
import core.dungeon_regions as dr  # noqa: E402

PASS = 0
FAILS: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAILS.append(f"{name} {('— ' + detail) if detail else ''}")


def _read(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        rows = self._rows

        class _S:
            def all(self):
                return list(rows)
        return _S()


class FakeSession:
    """Devolve os catálogos de erva/minério pedidos pelo resolvedor de nomes."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = 0

    async def execute(self, stmt, params=None):
        self.queries += 1
        sql = str(stmt).lower()
        kind = "ore" if "ore" in sql else "herb"
        return FakeResult([r for r in self.rows if r.kind == kind])


ORES = [Obj(id=3, name="Mystic Silver", emoji="⬜", kind="ore"),
        Obj(id=8, name="Phoenix Ash", emoji="🔥", kind="ore"),
        Obj(id=6, name="Void Crystal", emoji="🌑", kind="ore")]
HERBS = [Obj(id=9, name="Moonlight Moss", emoji="🌿", kind="herb")]


def _on(v: bool) -> None:
    dr.regionais_on = (lambda world_key=None: v)


async def main() -> None:
    # ═══ 1. O TRIBUTO DIZ O QUÊ E QUANTO (report [jogador]) ═══
    _on(True)
    sess = FakeSession(ORES + HERBS)
    reg = dr.roll_regional_bonus.__wrapped__ if hasattr(dr.roll_regional_bonus, "__wrapped__") else None

    # Qiānhé: 1 minério nomeado.
    line = await dr.regional_bonus_line(
        sess, {"loot": {"ores": {"3": 1}}, "continent": "qianhe",
               "continent_emoji": "⛰️", "hits": 1}, "pt")
    check("trib.nomeia_item", "Mystic Silver" in line and "×1" in line, line)
    check("trib.nomeia_continente", "⛰️" in line, line)
    check("trib.sem_hits_nao_diz", "×1 tributos" not in line and "tributos" not in line, line)

    # Yǎnshān: erva, e a quantidade JÁ vem multiplicada pelos hits.
    line = await dr.regional_bonus_line(
        sess, {"loot": {"herbs": {"9": 7}}, "continent": "yanshan",
               "continent_emoji": "🌸", "hits": 7}, "pt")
    check("trib.qty_multiplicada", "Moonlight Moss ×7" in line, line)
    check("trib.hits_ditos", "7" in line and ("×7 tributos" in line or "tributos" in line),
          "Lei §10 — 1 e 50 acertos liam-se IGUAL antes disto")

    # Línghé: PEDRAS. A frase antiga dizia "material nativo" — mentira.
    line = await dr.regional_bonus_line(
        sess, {"loot": {"stones": 250}, "continent": "linghe",
               "continent_emoji": "🌿", "hits": 1}, "pt")
    check("trib.linghe_diz_pedras", "250" in line and "pedras" in line.lower(), line)
    check("trib.linghe_nao_mente", "material nativo" not in line.lower(), line)

    # Nada a dizer ⇒ string vazia (nunca uma linha órfã).
    check("trib.vazio", await dr.regional_bonus_line(sess, None, "pt") == "")
    check("trib.loot_vazio", await dr.regional_bonus_line(
        sess, {"loot": {}, "continent": "qianhe", "hits": 1}, "pt") == "")
    check("trib.qty_zero", await dr.regional_bonus_line(
        sess, {"loot": {"ores": {"3": 0}}, "continent": "qianhe", "hits": 1}, "pt") == "")
    # Nunca levanta: um catálogo em falta some com a parte, não com a tela.
    check("trib.item_desconhecido", await dr.regional_bonus_line(
        sess, {"loot": {"ores": {"999": 1}}, "continent": "qianhe", "hits": 1}, "pt") == "")

    # A tabela por continente continua a ser a verdade (contada da FONTE).
    check("trib.tabela", set(dr.REGIONAL_BONUS_LOOT) == {"linghe", "qianhe", "yanshan",
                                                          "fenghuo", "moyu"})
    check("trib.so_linghe_paga_pedras",
          [c for c, v in dr.REGIONAL_BONUS_LOOT.items() if "stones" in v] == ["linghe"])
    check("trib.chance", dr.REGIONAL_BONUS_CHANCE == 0.12)

    # O roll continua gated e só hard/nightmare.
    d = Obj(continent="qianhe")
    check("trib.so_hard", dr.roll_regional_bonus(d, "normal") is None)
    _on(False)
    check("trib.flag_off", dr.roll_regional_bonus(d, "hard", runs=50) is None)
    _on(True)

    # Wiring: as 3 telas que mostram o tributo leem a MESMA linha.
    dng = _read("handlers/dungeons.py")
    check("trib.chat_usa_helper", dng.count("regional_bonus_line(session, _regional, lang)") == 2,
          "conclusão + varredura")
    check("trib.chat_sem_linha_generica", "dng_regional_bonus" not in dng,
          "a linha que só dizia o continente morreu")
    ws = _read("core/webserver.py")
    check("trib.payload_leva_linha", ws.count('"line": await _dng_tribute_line') == 2)
    check("trib.payload_leva_hits", ws.count('"hits": int(_regional.get("hits") or 1)') == 2)
    tabs = _read("miniapp/components/tabs.js")
    check("trib.mini_usa_linha", "result.regional_bonus.line ||" in tabs,
          "server-resolved, com recuo para payload em cache")
    check("trib.mini_conclusao_copia", 'regional_bonus: res.regional_bonus || null, dungeon: { name: run.name' in tabs,
          "o objeto kind:'completed' deitava fora o que o servidor mandava")
    # O chefe — o caminho que REALMENTE conclui uma masmorra.
    pve = _read("core/pve_duel_settle.py")
    check("trib.chefe_calcula", "regional_bonus_line" in pve)
    check("trib.chefe_no_payload", '"tribute_line": _tribute_line' in pve
          and "if _tribute_line else {}" in pve, "key CONDICIONAL")
    check("trib.duel_state_expoe", 'out["tribute_line"]' in ws)
    check("trib.mini_banner_chefe", "state.tribute_line" in tabs)

    # ═══ 2. TÍTULOS: o benefício é PRESTÍGIO, e agora é dito (report [jogador]) ═══
    _live = {"cb_mult": 1.05}
    ach.__dict__["_flag"] = True

    import database.db as ddb
    _orig_flag = ddb.feature_enabled_for_world

    def _flag(name, world_key=None):
        return name == "combate_unificado" and ach.__dict__["_flag"]
    ddb.feature_enabled_for_world = _flag
    try:
        # Mundo COM combate unificado: o número aparece — e é o HONESTO (+5%).
        rows = ach.bonus_display(_live)
        check("tit.bonus_honesto", len(rows) == 1 and abs(rows[0]["pct"] - 5.0) < 0.01,
              str(rows))
        check("tit.label_key", rows[0]["label_key"] == "ach_bonus_cb_mult")

        # Mundo SEM (a main dos 57): NADA é anunciado — era aqui que se lia "+105%".
        ach.__dict__["_flag"] = False
        check("tit.main_nao_promete", ach.bonus_display(_live) == [],
              "o bônus vale ZERO sem a flag; prometer 105% é display-lie")
        ach.__dict__["_flag"] = True

        # Os 3 ÓRFÃOS param de ser anunciados (seedados, lidos por ninguém).
        check("tit.orfao_evasion", ach.bonus_display({"evasion": 0.03}) == [])
        check("tit.orfao_alchemy", ach.bonus_display({"alchemy_quality": 0.10}) == [])
        check("tit.orfao_trib", ach.bonus_display({"tribulation_severity_mult": 0.95}) == [])
        check("tit.mistura", [r["key"] for r in ach.bonus_display(
            {"cb_mult": 1.05, "evasion": 0.03})] == ["cb_mult"],
            "o vivo passa, o órfão não")
        check("tit.vazio", ach.bonus_display(None) == [] and ach.bonus_display({}) == [])
        check("tit.zero_nao_e_beneficio", ach.bonus_display({"cb_mult": 1.0}) == [])
        check("tit.live_keys", ach.ACH_LIVE_BONUS_KEYS == frozenset({"cb_mult", "bp_mult"}))
    finally:
        ddb.feature_enabled_for_world = _orig_flag

    # As 2 telas leem a verdade única (nenhuma recalcula).
    acht = _read("handlers/achievements.py")
    check("tit.chat_usa_verdade", "bonus_display" in acht)
    check("tit.chat_sem_conta_propria", "v) - 1.0) if (_honest" not in acht,
          "a conta duplicada que mentia na main morreu")
    check("tit.mini_usa_verdade", "it.bonus_view" in tabs
          and 'featureEnabled("combate_unificado"));' not in tabs,
          "o card não recalcula: o servidor manda bonus_view pronto")
    check("tit.endpoint_manda", '"bonus_view": _ach_bonus_display(stat_bonus)' in ws)

    # A nota honorífica existe nas DUAS superfícies + a marca na linha do título.
    check("tit.nota_chat", "ach_title_honorary_note" in acht)
    check("tit.tag_chat", "ach_title_honorary_tag" in acht)
    check("tit.nota_mini", "ach_title_honorary_note" in tabs)
    check("tit.tag_mini", "ach_title_honorary_tag" in tabs)
    check("tit.pavilhao_nota", "merit_titles_honorary_note" in _read("handlers/sect.py"))
    check("tit.pavilhao_desc", "r['desc']" in _read("handlers/sect.py"),
          "o servidor JÁ calculava o desc e o chat deitava fora (paridade)")

    # A #28 passa a dizer o que é — sem tocar no `title_granted` (19 jogadores).
    seeds = _read("database/seeds/achievement_seeds.py")
    check("ach28.force_sync", "TEXT_SYNC" in seeds and "update(AchievementCatalog)" in seeds,
          "o runner é insert-only: sem force-sync a prod nunca vê o texto novo")
    check("ach28.texto_honesto", "not the Heir rank" in seeds)
    check("ach28.titulo_intocado", '"title_granted": "Sect Heir",' in seeds,
          "renomear órfãozaria o unlocked_titles de quem já a tem")
    from database.seeds.achievement_seeds import ACHIEVEMENT_SEEDS
    by_id = {a["id"]: a for a in ACHIEVEMENT_SEEDS}
    check("ach28.evento", by_id[28]["event_type"] == "world_sect_joined",
          "prova o report: a conquista dispara ao ENTRAR, não ao virar heir")
    check("ach30.evento", by_id[30]["event_type"] == "sect_rank_reached"
          and by_id[30]["target_value"] == 4, "a #30 é a que mede o posto heir")
    check("ach30.desc_diz_posto", "rank of Heir" in by_id[30]["description"])

    # ═══ 3. i18n ×3 ×2 ═══
    from inject_qol0804_i18n import CHAT, MINIAPP
    for label, parts, batch in (("chat", ("locales",), CHAT),
                                ("mini", ("miniapp", "i18n"), MINIAPP)):
        data = {}
        for lang in ("pt", "en", "es"):
            with open(os.path.join(ROOT, *parts, f"{lang}.json"), encoding="utf-8") as f:
                data[lang] = json.load(f)
        check(f"i18n.{label}.paridade",
              set(data["pt"]) == set(data["en"]) == set(data["es"]))
        missing = [k for k in batch["pt"] if any(k not in data[x] for x in ("pt", "en", "es"))]
        check(f"i18n.{label}.lote", not missing, str(missing))

    print(("OK " if not FAILS else "FAIL ") + f"— {PASS} asserts")
    for f in FAILS:
        print(" ✗", f)
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
