# -*- coding: utf-8 -*-
"""MV-9 城 "As Cinco Cidades" — suite COMMITTED.

Molde: `scripts/_test_mv8_jianghu.py`. Corre standalone, ZERO base de dados:
    python -X utf8 scripts/_test_mv9_cidades.py

Cobre, por secção:
  1. OFF-identity — flag OFF não faz UMA query e não emite UMA key
  2. CITY_META — estrutura, cobertura dos 5 continentes, keys de i18n reais
  3. A DERIVAÇÃO — pureza, world_key na semente, modulação por estado/evento,
     e a caça à modulação MORTA (a falha que a simulação apanhou)
  4. As seeds dos 15 encargos — weight 0 deliberado, trackers vivos e SOLO
  5. A Crônica — o ramo {city}/{encargo}; nenhuma chaveta crua na tela
  6. WIRING por grep — todo helper tem call site real
  7. i18n — paridade ×3×2, placeholders simétricos, PT-BR (anti EU-PT)
  8. O fix do report do [jogador] — crédito de `cultivate` em quem finaliza à mão
  9. As dívidas do §P6 — travel_available, daily id 3, o apagador do MV-1
"""
from __future__ import annotations

import os
import sys
import types
import json
import re
import inspect
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── stub do telegram ANTES de qualquer core.* (convenção da casa) ────────────
if "telegram" not in sys.modules:
    _tg = types.ModuleType("telegram")
    _tg.Update = object
    _err = types.ModuleType("telegram.error")

    class _TgErr(Exception):
        retry_after = 0

    _err.RetryAfter = _err.TimedOut = _err.NetworkError = _err.BadRequest = _TgErr
    _tg.error = _err
    sys.modules["telegram"] = _tg
    sys.modules["telegram.error"] = _err

PASS = 0
FAIL: list[str] = []


def check(name: str, cond, detail: str = "") -> None:
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(f"{name} {detail}")
        print(f"  FAIL: {name} {detail}")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


# ⚠️ NOW ancorado ao AGORA, nunca a uma data fixa: uma data fixa faz a suite
# ficar vermelha sozinha no dia seguinte (foi o que aconteceu ao _test_tec4).
NOW = datetime.now(timezone.utc)

import core.city_engine as cid
from core.city_engine import (
    CITY_META, CITY_KEYS, CONTINENT_TO_CITY, ENCARGO_KEYS,
    encargo_key_for, city_key_for, city_view, tick_epoch, seed_for,
    CITY_TICK_HOURS, ENCARGO_EXPIRES_HOURS, ENCARGO_REPEAT_HOURS,
)
from core.continent_engine import CONTINENT_KEYS
from database.seeds.storylet_seeds import STORYLET_SEEDS

SEEDS = {s["key"]: s for s in STORYLET_SEEDS}
LANGS = ("pt", "en", "es")
CHAT = {lg: json.loads(_read(f"locales/{lg}.json")) for lg in LANGS}
MINI = {lg: json.loads(_read(f"miniapp/i18n/{lg}.json")) for lg in LANGS}

_ORIG_ON = cid.cidades_on
_ORIG_QV = cid._quests_vivas_on


def _set_flags(cidades: bool, quests: bool = True) -> None:
    cid.cidades_on = lambda world_key=None: cidades
    cid._quests_vivas_on = lambda: quests


class ExplodingSession:
    """Qualquer query com a flag OFF é um bug — a OFF-identity é literal."""

    def __getattr__(self, name):
        if name in ("rollback",):
            return lambda *a, **k: None
        raise AssertionError(f"query executada com flag OFF ({name})")


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] OFF-identity — a flag OFF não toca em nada")
# ═══════════════════════════════════════════════════════════════════════════
_set_flags(False)
check("off/city_view devolve None", city_view("linghe", "pt") is None)
check("off/city_view em TODO continente",
      all(city_view(c, "pt") is None for c in CONTINENT_KEYS))
import asyncio
check("off/city_plaza_view não faz query",
      asyncio.run(cid.city_plaza_view(ExplodingSession(), types.SimpleNamespace(
          telegram_id=1, current_continent="linghe", language="pt"), "pt")) is None)
check("off/city_map_overlay não faz query",
      asyncio.run(cid.city_map_overlay(ExplodingSession(), "pt", "linghe")) == {})
check("off/pulse_cities não faz query",
      asyncio.run(cid.pulse_cities(ExplodingSession())) is None)
_acc = asyncio.run(cid.accept_encargo(ExplodingSession(),
                                      types.SimpleNamespace(telegram_id=1, current_continent="linghe",
                                                            language="pt")))
check("off/accept_encargo recusa NOMEADA", _acc.get("ok") is False and bool(_acc.get("line")),
      str(_acc))
check("off/a recusa não vaza chaveta", "{" not in str(_acc.get("line", "")))

# ═══════════════════════════════════════════════════════════════════════════
print("[2] CITY_META — as cinco cidades")
# ═══════════════════════════════════════════════════════════════════════════
_set_flags(True)
check("meta/5 cidades", len(CITY_META) == 5, str(len(CITY_META)))
check("meta/CITY_KEYS na ordem dos continentes",
      [CITY_META[k]["continent"] for k in CITY_KEYS] == list(CONTINENT_KEYS),
      str([CITY_META[k]["continent"] for k in CITY_KEYS]))
check("meta/cobertura = os 5 continentes",
      sorted(CONTINENT_TO_CITY) == sorted(CONTINENT_KEYS))
check("meta/uma cidade por continente (índice reverso não perde ninguém)",
      len(CONTINENT_TO_CITY) == len(CITY_META))
for k, m in CITY_META.items():
    check(f"meta/{k}: slug ASCII", k.isascii() and k.islower() and k.isalpha(), k)
    check(f"meta/{k}: emoji literal", bool(m["emoji"]) and not m["emoji"].isascii())
    for f in ("name_key", "intro_key", "trait_key"):
        key = m[f]
        for lg in LANGS:
            check(f"meta/{k}.{f} existe em {lg}", key in CHAT[lg], key)
            # ⚠️ estas keys são resolvidas por t() SEM kwargs (lição
            # region_state_engine:106-110): um placeholder vazaria a chaveta.
            check(f"meta/{k}.{f} SEM placeholder em {lg}",
                  "{" not in CHAT[lg].get(key, ""), CHAT[lg].get(key, ""))
    check(f"meta/{k}: 3 encargos", len(m["encargos"]) == 3, str(len(m["encargos"])))
check("meta/15 encargos ao todo", len(ENCARGO_KEYS) == 15, str(len(ENCARGO_KEYS)))
check("meta/keys de encargo únicas", len(set(ENCARGO_KEYS)) == 15)
check("meta/city_key_for inválido → None", city_key_for("nope") is None and city_key_for(None) is None)
_cv = city_view("moyu", "pt")
check("meta/city_view resolve nome server-side",
      _cv and _cv["name"] == CHAT["pt"]["city_huiyin_name"], str(_cv))

# ═══════════════════════════════════════════════════════════════════════════
print("[3] A DERIVAÇÃO do encargo")
# ═══════════════════════════════════════════════════════════════════════════
check("der/tick de 24h > latência máxima do rumor (12h)",
      CITY_TICK_HOURS >= 24, str(CITY_TICK_HOURS))
check("der/prazo do encargo cabe dentro do tick",
      ENCARGO_EXPIRES_HOURS <= CITY_TICK_HOURS, str(ENCARGO_EXPIRES_HOURS))
check("der/anti-repeat cobre quase um tick", ENCARGO_REPEAT_HOURS >= 12)
check("der/pura: mesma entrada → mesma saída",
      encargo_key_for("linghe", now=NOW, world_key="w") ==
      encargo_key_for("linghe", now=NOW, world_key="w"))
check("der/continente inválido → None", encargo_key_for("nope", now=NOW) is None)
check("der/nunca devolve None para continente válido",
      all(encargo_key_for(c, now=NOW + timedelta(hours=24 * i)) for c in CONTINENT_KEYS
          for i in range(20)))
check("der/só devolve keys que existem no catálogo",
      all(encargo_key_for(c, now=NOW + timedelta(hours=24 * i)) in SEEDS
          for c in CONTINENT_KEYS for i in range(20)))
check("der/só devolve encargo DAQUELA cidade",
      all(encargo_key_for(c, now=NOW + timedelta(hours=24 * i))
          in [e["key"] for e in CITY_META[CONTINENT_TO_CITY[c]]["encargos"]]
          for c in CONTINENT_KEYS for i in range(20)))
check("der/seed_for carrega o world_key", "main" in seed_for("main", "linghe", 1)
      and "s2" in seed_for("s2", "linghe", 1))
check("der/seed_for carrega o continente", "linghe" in seed_for("m", "linghe", 1))
# A lição do MV-8: main e s2 não podem contar a mesma história.
_same = sum(1 for c in CONTINENT_KEYS for i in range(60)
            if encargo_key_for(c, now=NOW + timedelta(hours=24 * i), world_key="main")
            == encargo_key_for(c, now=NOW + timedelta(hours=24 * i), world_key="s2"))
check("der/main × s2 divergem (a semente inclui o mundo)", _same < 300 * 0.75, f"{_same}/300")
# E as 5 cidades não pedem a mesma coisa no mesmo dia.
_allsame = sum(1 for i in range(60)
               if len({encargo_key_for(c, now=NOW + timedelta(hours=24 * i)) for c in CONTINENT_KEYS}) == 1)
check("der/as 5 cidades nunca pedem tudo igual", _allsame == 0, str(_allsame))
# Rodízio em paz: os TRÊS têm de aparecer (o defeito que a simulação apanhou).
for c in CONTINENT_KEYS:
    seen = {encargo_key_for(c, now=NOW + timedelta(hours=24 * i), region_state="prospera")
            for i in range(120)}
    check(f"der/{c}: os 3 encargos rodam em paz", len(seen) == 3, str(sorted(seen)))
# Crise: o estado MANDA (bônus > jitter).
_CRISIS = {"linghe": "enc_linghe_escolta", "qianhe": "enc_qianhe_provas",
           "yanshan": "enc_yanshan_remedio", "fenghuo": "enc_fenghuo_tempera",
           "moyu": "enc_moyu_ecos"}
for c, want in _CRISIS.items():
    hits = sum(1 for i in range(60)
               if encargo_key_for(c, now=NOW + timedelta(hours=24 * i), region_state="sitiada") == want)
    check(f"der/{c}: sitiada manda ({want})", hits >= 57, f"{hits}/60")
# ⚠️ NENHUM bônus de `prospera`: um polegar no estado neutro (70% dos dias)
# colapsa o rodízio — foi exatamente a 1ª versão desta onda.
for k, m in CITY_META.items():
    for e in m["encargos"]:
        check(f"der/{e['key']}: sem bônus de prospera", "prospera" not in e["util"],
              str(e["util"]))
        check(f"der/{e['key']}: bases iguais", abs(float(e["util"]["base"]) - 0.30) < 1e-9,
              str(e["util"]))
# ⚠️ Modulação de evento tem de usar o event_type REAL e existir só onde o
# evento PODE nascer — senão é letra morta que ninguém vê falhar.
from core.tiandao_engine import DIRECTOR_EVENT_TYPES, TIDE_CONTINENTS, METEOR_CONTINENTS
_STATES = {"tensa", "sitiada", "festival"}
for k, m in CITY_META.items():
    cont = m["continent"]
    for e in m["encargos"]:
        for bonus in e["util"]:
            if bonus == "base" or bonus in _STATES:
                continue
            check(f"der/{e['key']}: '{bonus}' é event_type REAL",
                  bonus in DIRECTOR_EVENT_TYPES, bonus)
            allowed = TIDE_CONTINENTS if bonus == "beast_tide" else METEOR_CONTINENTS
            check(f"der/{e['key']}: '{bonus}' pode nascer em {cont}",
                  cont in allowed, f"{cont} não está em {allowed}")
# A key da CRÔNICA (`wev_*`) não é a do `world_events` — não pode mover nada.
check("der/`wev_beast_tide` é letra morta (era o bug da 1ª versão)",
      all(encargo_key_for(c, now=NOW + timedelta(hours=24 * i), events={"wev_beast_tide"})
          == encargo_key_for(c, now=NOW + timedelta(hours=24 * i))
          for c in CONTINENT_KEYS for i in range(20)))

# ═══════════════════════════════════════════════════════════════════════════
print("[4] As seeds dos 15 encargos")
# ═══════════════════════════════════════════════════════════════════════════
import core.storylet_engine as sty
_PVP = {"sparring", "win_sparring"}
_SOLO = {"cultivate", "craft_pill", "use_pill", "npc_combat", "beast_expedition",
         "dungeon_floor", "forge_artifact", "arena_win"}
for k in ENCARGO_KEYS:
    check(f"seed/{k}: existe", k in SEEDS)
    s = SEEDS.get(k) or {}
    check(f"seed/{k}: weight 0 (fora do sorteio, afixado na cidade)", s.get("weight") == 0)
    check(f"seed/{k}: tracker NUNCA depende de outro jogador",
          s.get("objective_type") not in _PVP, str(s.get("objective_type")))
    check(f"seed/{k}: tracker solo-completável",
          s.get("objective_type") in _SOLO, str(s.get("objective_type")))
    # `_KNOWN_REQS` é FAIL-CLOSED: uma key desconhecida devolve False para TODO
    # jogador, sem log e sem erro. Reusámos só `continent` + `flag`.
    check(f"seed/{k}: requirements ⊆ _KNOWN_REQS",
          set(s.get("requirements", {})) <= set(sty._KNOWN_REQS),
          str(set(s.get("requirements", {}))))
    check(f"seed/{k}: gated pela flag `cidades`", s.get("requirements", {}).get("flag") == "cidades")
    check(f"seed/{k}: preso ao continente certo",
          s.get("requirements", {}).get("continent") == [CITY_META[
              next(c for c in CITY_META if k in [e["key"] for e in CITY_META[c]["encargos"]])
          ]["continent"]], str(s.get("requirements", {}).get("continent")))
    rw = s.get("reward", {})
    check(f"seed/{k}: paga material NATIVO, nunca só pedras", bool(rw.get("items")), str(rw))
    check(f"seed/{k}: reward limpo (nunca jade/técnica)",
          set(rw) <= {"stones", "karma", "items"}, str(set(rw)))
# O prefiltro quente lê os objective_types DESTE ficheiro — um tipo fora dele
# faria o progresso morrer em silêncio.
_tt = sty._tracked_types()
check("seed/todos os trackers do encargo estão no prefiltro",
      _tt is None or all(SEEDS[k]["objective_type"] in _tt for k in ENCARGO_KEYS))

# ═══════════════════════════════════════════════════════════════════════════
print("[5] A Crônica — {city}/{encargo} nunca cru")
# ═══════════════════════════════════════════════════════════════════════════
from core.world_pulse_engine import _chronicle_localized_names, render_chronicle_row
_row = types.SimpleNamespace(
    id=1, ts=NOW, event_type="cid_encargo", text_key="cid_chron_encargo",
    importance=1, sect_id=None, continent_key="fenghuo",
    params={"city_key": "tianhuo", "encargo_key": "enc_fenghuo_forja"})
for lg in LANGS:
    names = _chronicle_localized_names(_row, lg)
    check(f"chron/{lg}: {{city}} resolvido", names.get("city") == CHAT[lg]["city_tianhuo_name"],
          str(names))
    check(f"chron/{lg}: {{encargo}} resolvido",
          names.get("encargo") == CHAT[lg]["sty_enc_fenghuo_forja_name"], str(names))
    txt = render_chronicle_row(_row, lg)["text"]
    check(f"chron/{lg}: nenhuma chaveta na tela", "{" not in txt and "}" not in txt, txt)
    check(f"chron/{lg}: o nome da cidade aparece", CHAT[lg]["city_tianhuo_name"] in txt, txt)
check("chron/continent_key é o CONTINENTE, nunca a cidade",
      "continent_key=cont" in _read("core/city_engine.py").replace(" ", "").replace("\n", "")
      or "continent_key=cont," in _read("core/city_engine.py"))

# ═══════════════════════════════════════════════════════════════════════════
print("[6] WIRING por grep — todo helper tem call site")
# ═══════════════════════════════════════════════════════════════════════════
_db, _ws, _sch, _tv, _wp, _tabs, _sect = (
    _read("database/db.py"), _read("core/webserver.py"), _read("core/scheduler.py"),
    _read("core/travel_engine.py"), _read("core/world_pulse_engine.py"),
    _read("miniapp/components/tabs.js"), _read("handlers/sect.py"))
check("wire/flag declarada em DEFAULT_WORLD_FEATURES", '"cidades":' in _db)
check("wire/flag nasce OFF", re.search(r'"cidades":\s*False', _db) is not None)
check("wire/pulse ligado ao World Pulse", "pulse_cities" in _sch)
check("wire/pulse tem commit próprio",
      re.search(r"pulse_cities\(session\)[\s\S]{0,200}session\.commit\(\)", _sch) is not None)
check("wire/praça (API) lê a cidade", "city_plaza_view" in _ws)
check("wire/praça (chat) lê a cidade", "city_plaza_view" in _sect)
check("wire/viagem lê o overlay", "city_map_overlay" in _tv)
check("wire/rota do encargo registada", '"/api/miniapp/world/city_encargo"' in _ws)
check("wire/endpoint do encargo existe", "async def api_world_city_encargo" in _ws)
check("wire/endpoint trava a row do jogador",
      re.search(r"api_world_city_encargo[\s\S]{0,900}with_for_update\(\)", _ws) is not None)
check("wire/ramo da Crônica existe", "encargo_key" in _wp and "city_key" in _wp)
check("wire/mini-app LÊ d.city (a superfície canônica)", "d.city ?" in _tabs or "d.city &&" in _tabs)
check("wire/mini-app desenha o encargo", "cid_encargo_head" in _tabs)
check("wire/TravelModal mostra a cidade", "dst.city_name" in _tabs)
check("wire/TravelModal mostra o pedido", "dst.city_encargo_line" in _tabs)
check("wire/ui_v2: porta desabilitada DIZ o motivo", "isleCity" in _tabs)
check("wire/endpoint do mapa manda as cidades", '"cities"' in _ws)
check("wire/ZERO migration", not any(
    f.startswith(("14", "15")) and "cidade" in f.lower()
    for f in os.listdir(os.path.join(ROOT, "migrations"))))
check("wire/nenhum ficheiro de migration novo cita `cidades`",
      not any("cidades" in _read(f"migrations/{f}")
              for f in os.listdir(os.path.join(ROOT, "migrations")) if f.endswith(".sql")))

# ═══════════════════════════════════════════════════════════════════════════
print("[7] i18n — paridade, placeholders, PT-BR")
# ═══════════════════════════════════════════════════════════════════════════
check("i18n/chat em paridade", len({len(v) for v in CHAT.values()}) == 1,
      str([len(v) for v in CHAT.values()]))
check("i18n/mini em paridade", len({len(v) for v in MINI.values()}) == 1,
      str([len(v) for v in MINI.values()]))
_MV9 = [k for k in CHAT["pt"] if k.startswith(("cid_", "city_", "sty_enc_"))]
check("i18n/keys do MV-9 nas 3 línguas",
      all(k in CHAT[lg] for k in _MV9 for lg in LANGS))
_ph = lambda s: set(re.findall(r"\{(\w+)\}", s))
for k in _MV9 + ["wbounty_post_chat_hint", "notif_bounty_claimed_body"]:
    sets = {lg: _ph(CHAT[lg].get(k, "")) for lg in LANGS}
    check(f"i18n/{k}: placeholders simétricos",
          len({frozenset(v) for v in sets.values()}) == 1, str(sets))
# Os tokens que o código PROMETE têm de ser os que ele PASSA (t() engole o
# KeyError e devolve o template — a chaveta vai à cara do jogador).
check("i18n/cid_chron_encargo promete city+encargo",
      _ph(CHAT["pt"]["cid_chron_encargo"]) == {"city", "encargo"})
check("i18n/cid_travel_wants promete icon+name",
      _ph(CHAT["pt"]["cid_travel_wants"]) == {"icon", "name"})
check("i18n/as 3 keys de bounty perderam o nome COZIDO",
      all("Wànshì" not in CHAT[lg][k] and "Wanshì" not in CHAT[lg][k]
          for lg in LANGS for k in ("wbounty_post_chat_hint", "notif_bounty_claimed_body"))
      and all("Wànshì" not in MINI[lg]["wbounty_post_intro"] for lg in LANGS))
check("i18n/as 2 strings AO VIVO ganharam {city}",
      all("{city}" in CHAT[lg]["wbounty_post_chat_hint"] for lg in LANGS)
      and all("{city}" in MINI[lg]["wbounty_post_intro"] for lg in LANGS))
# ⚠️ REGRA nova (review do MV-9): uma NOTIFICAÇÃO nunca ganha placeholder novo.
# `player_notifications` guarda body_key + payload e renderiza PREGUIÇOSAMENTE,
# sem poda: dar `{city}` a esta string partia TODA linha já gravada (payload
# antigo, sem a chave) — e no `main`, onde a flag está OFF.
check("i18n/a NOTIFICAÇÃO não ganhou placeholder novo",
      all("{city}" not in CHAT[lg]["notif_bounty_claimed_body"] for lg in LANGS))
check("i18n/a notificação continua sem o nome COZIDO",
      all("Wànshì" not in CHAT[lg]["notif_bounty_claimed_body"] for lg in LANGS))
# Defesa em profundidade: `t()` degrada só o TOKEN em falta, não a frase toda.
from core.i18n import t as _t_probe
# ⚠️ passar UM kwarg (mesmo irrelevante) é o que leva `t()` ao caminho de
# `format` — sem kwargs nenhum ele devolve o template como está, e aí não há
# nada a degradar. É exatamente a forma do bug real: a notificação chegava com
# {target, hunter} e faltava-lhe {city}.
_deg = _t_probe("pt", "wbounty_post_chat_hint", irrelevante="x")
check("i18n/t() degrada só o TOKEN em falta, não a frase toda",
      "{city}" not in _deg and "mini-app" in _deg, _deg)
check("i18n/a key ANTIGA city_wanshi ficou intacta (fallback do main)",
      CHAT["pt"]["city_wanshi"] == "Praça de Wànshì")
# ⚠️ REGRESSÃO (defeito real desta sessão): dar `{city}` a uma string e esquecer
# de o PASSAR num dos call sites imprime a chaveta CRUA na cara do jogador —
# `t()` (chat E cliente) só substitui o que recebe. Um assert por call site.
check("i18n/{city} passado no hint do chat",
      re.search(r'wbounty_post_chat_hint"[\s\S]{0,120}city=', _read("handlers/sect.py")) is not None)
check("i18n/{city} passado no intro do mini",
      re.search(r'wbounty_post_intro"\s*,\s*\{\s*city:', _read("miniapp/components/tabs.js")) is not None)
check("i18n/o servidor MANDA a cidade para o intro do mini (o mini não tem keys city_*)",
      '"city": _city,' in _read("core/bounty_engine.py"))
check("i18n/o fallback com flag OFF é o nome PRÓPRIO nu, nunca 'Praça de Wànshì'",
      'or "Wànshì"' in _read("handlers/sect.py")          # Python
      and '|| "Wànshì"' in _read("miniapp/components/tabs.js"))   # JS

# ── Os defeitos que o review adversarial confirmou, agora com guarda ────────
_ce, _se, _gl = (_read("core/city_engine.py"), _read("core/storylet_engine.py"),
                 _read("core/game_logic.py"))
check("rev/a contagem da expiry é a DA ROW, nunca a do encargo vigente",
      "_rcount" in _ce and "int(r.progress or 0) < _rcount" in _ce)
check("rev/o encargo NÃO conta para o pacer do MV-5",
      "ENCARGO_KEYS as _ENC" in _se and "_enc_keys" in _se)
check("rev/o gate do world/events inclui `cidades` (senão isleCity nasce morto)",
      'featureEnabled("cidades")' in _tabs)
check("rev/erro interno do encargo tem `line` (nunca botão silencioso)",
      re.search(r'"reason": "internal_error",\s*\n\s*"line"', _ce) is not None)
check("rev/o crédito manual dá a essência de núcleo do realm 2",
      "add_core_essence" in _gl and 'realm", 0) or 0) == 2' in _gl)
check("rev/o 8º caminho (dao start no mini) credita",
      _read("core/webserver.py").count("credit_meditation_if_earned") >= 3)
from database.seeds.quests_seeds import QUEST_SEEDS as _QS
_q3chk = next(q for q in _QS if q["id"] == 3)
check("rev/a daily 3 já não diz 'sparring' ao jogador",
      "spar" not in _q3chk["name"].lower() and "spar" not in _q3chk["description"].lower(),
      f"{_q3chk['name']!r} / {_q3chk['description']!r}")
# ⚠️ Medido em produção após o deploy: o sync escrevia SÓ `objective_type`, e o
# nome ficou "Participate in Sparring" nas 2 DBs enquanto o objetivo já era
# npc_combat. Mudar a seed não chega — as DBs vivas precisam do bloco de texto.
check("rev/o sync ALINHA o texto da id 3 nas DBs vivas (a seed sozinha é no-op)",
      "text_updates" in _read("database/seeds/quests_seeds.py")
      and "_q3.name = _q3seed" in _read("database/seeds/quests_seeds.py"))
check("rev/pulse_cities é idempotente por tick (deploy re-dispara o batimento)",
      'WorldChronicle.params["encargo_key"]' in _ce)
# ⚠️ BUG DE PRODUÇÃO (s2, 2026-08-06, anterior ao MV-9): uma oferta VENCIDA mas
# ainda `status='offered'` não fazia o pacer desistir, e o índice único parcial
# (que ignora a validade) rejeitava todo mint seguinte — o jogador ficava sem
# UMA oferta para sempre. Guarda: o pacer TEM de libertar a row vencida.
check("prod/o pacer liberta a oferta VENCIDA (senão o jogador morre para o mundo)",
      'r.status = "expired"' in _se and "_freed" in _se and "await session.flush()" in _se)
check("prod/o flip acontece ANTES do insert (ordem da unit-of-work não é garantida)",
      _se.index("if _freed:") < _se.index("row = PlayerStorylet("), "flush depois do insert")
check("i18n/flag no painel do owner ×3", all("feature_cidades" in MINI[lg] for lg in LANGS))
check("i18n/a conjunção quests_vivas está escrita em PROSA no _desc",
      all("quests_vivas" in MINI[lg]["feature_cidades_desc"] for lg in LANGS))
# PT-BR: nada de europeu. Lista negra cumulativa da casa + as desta onda.
_EUPT = [r"\bautoestrada\w*", r"\b(é|são|era|eram)\s+precis[oa]s?\b", r"\btu\s+(tens|és|vais|podes)\b",
         r"\bcomboio\b", r"\becrã\b", r"\bautocarro\b", r"\btelemóvel\b", r"\bcasa de banho\b",
         r"\brapariga\b", r"\bsandes\b", r"\bfixe\b", r"\bgiro\b", r"\bapanhar o\b",
         r"\bestás\b", r"\bficas\b", r"\bqueres\b", r"\bconsegues\b", r"\bdeves\b",
         r"\bfazes\b", r"\bvês\b", r"\bsabes\b", r"\bdizes\b", r"\bpões\b"]
_off = [(k, p) for k in _MV9 for p in _EUPT if re.search(p, CHAT["pt"][k], re.I)]
check("i18n/PT-BR: nenhum padrão europeu", not _off, str(_off[:4]))
check("i18n/PT-BR: usa 'você', nunca 'tu'",
      not any(re.search(r"\btu\b", CHAT["pt"][k]) for k in _MV9))

# ═══════════════════════════════════════════════════════════════════════════
print("[8] O fix do report do [jogador] — quem finaliza credita")
# ═══════════════════════════════════════════════════════════════════════════
from core.game_logic import meditation_credit_minutes as _mcm
_t = NOW
check("relato/meditação terminada credita a duração",
      _mcm("dao_transcend", _t - timedelta(minutes=1), now=_t) == 240)
check("relato/meditação a correr NÃO credita (anti-farm v16.6)",
      _mcm("dao_transcend", _t + timedelta(hours=2), now=_t) == 0)
check("relato/tipo de Dao é conhecido", _mcm("celestial_dao", _t, now=_t) == 480)
check("relato/tipo comum é conhecido", _mcm("deep", _t - timedelta(minutes=5), now=_t) == 60)
check("relato/tipo desconhecido → 0", _mcm("nope", _t - timedelta(minutes=5), now=_t) == 0)
check("relato/sem fim → 0", _mcm("deep", None, now=_t) == 0)
check("relato/datetime naive é tratado como UTC",
      _mcm("deep", (_t - timedelta(minutes=5)).replace(tzinfo=None), now=_t) == 60)
# Os SETE caminhos que terminam a sessão à mão têm de creditar.
_paths = {
    "core/webserver.py": 2,          # api_meditate_stop + api_dao_meditate_cancel
    "handlers/cultivation.py": 3,    # auto-end expired + trocar + cancelar
    "handlers/dao.py": 2,            # trocar + cancelar
}
for rel, n in _paths.items():
    got = _read(rel).count("credit_meditation_if_earned")
    check(f"relato/{rel}: {n} call sites", got >= n, f"tem {got}")
check("relato/o crédito corre num SAVEPOINT",
      "begin_nested" in inspect.getsource(
          __import__("core.game_logic", fromlist=["x"]).credit_meditation_if_earned))

# ═══════════════════════════════════════════════════════════════════════════
print("[9] As dívidas do §P6")
# ═══════════════════════════════════════════════════════════════════════════
check("p6/travel_available deixou de mentir", '"travel_available": True' in _ws)
from database.seeds.quests_seeds import QUEST_SEEDS, _OBJECTIVE_TYPE_SYNC_IDS
_q3 = next(q for q in QUEST_SEEDS if q["id"] == 3)
check("p6/daily id 3 já não é `sparring`", _q3["objective_type"] != "sparring",
      _q3["objective_type"])
check("p6/daily id 3 é solo-completável", _q3["objective_type"] in _SOLO, _q3["objective_type"])
check("p6/id 3 na allowlist do sync (senão a DB viva nunca converge)",
      3 in _OBJECTIVE_TYPE_SYNC_IDS)
_dr = _read("core/dungeon_regions.py")
check("p6/o apagador do MV-1 devolve a lista COMPLETA", '"portals"' in _dr)
check("p6/cada portal tem NOME", '"name": getattr(d, "name"' in _dr)
check("p6/o `count` foi preservado (os 2 renders antigos leem-no)", '"count": len(' in _dr)
check("p6/chat imprime os portais", "portals" in _read("handlers/dungeons.py"))
check("p6/mini imprime os portais", "e.portals" in _tabs)
check("p6/ProfessionCard mostra o solo do ofício",
      "prf_mini_in_native" in _tabs and "prf_mini_travel" in _tabs)
check("p6/a notificação de bounty diz ONDE", '"continent": getattr(bounty' in _read("core/bounty_engine.py"))

# restaurar os originais ANTES de sair (o teste não deixa rasto)
cid.cidades_on = _ORIG_ON
cid._quests_vivas_on = _ORIG_QV

print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)
print(f"OK — {PASS} asserts. As cinco cidades têm nome, pedido e voz na Crônica.")
