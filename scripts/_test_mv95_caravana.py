# -*- coding: utf-8 -*-
"""MV-9.5 商队 "A Caravana" — suite COMMITTED.

Molde: `scripts/_test_mv9_cidades.py`. Corre standalone, ZERO base de dados:
    python -X utf8 scripts/_test_mv95_caravana.py

Cobre, por secção:
  1. OFF-identity — flag OFF não faz UMA query e não emite UMA key
  2. A conjunção DURA (caravana ∧ cidades ∧ dungeons_regionais)
  3. CARAVAN_META — forma, cobertura ×5, keys de i18n sem placeholder
  4. O MAPA DERIVADO — a medição que derrubou o spec de 07/08
  5. Os MUROS, as rotas e o teto de tier do pagamento
  6. A carga no ledger — forma, idempotência, MERGE do JSONB
  7. As recusas — todas nomeadas, nenhuma vaza chaveta
  8. Wiring por grep — todo helper tem call site real
  9. i18n / PT-BR
 10. ZERO migration + as dívidas do §4 pagas
"""
from __future__ import annotations

import inspect
import io
import json
import os
import re
import sys
import types
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
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
    with io.open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


# ⚠️ NOW ancorado ao AGORA, nunca a uma data fixa: uma data fixa faz a suite
# ficar vermelha sozinha no dia seguinte (foi o que aconteceu ao _test_tec4).
NOW = datetime.now(timezone.utc)

import asyncio  # noqa: E402

import core.caravan_engine as crv  # noqa: E402
from core.caravan_engine import (  # noqa: E402
    CARAVAN_META, CRV_ETA_HOURS, CRV_LOAD_UNITS, CRV_PAY_TIER_SLACK,
    CRV_RATIO, CRV_RATIO_HUB, CRV_ROUTE_MAX_CONTINENTS, CRV_ROUTE_MIN_TIER,
    accepted_payments, confined_materials, is_walled, material_origin,
    origin_line, produced_in, quote, routes_for,
)
from core.continent_engine import CONTINENT_KEYS  # noqa: E402

LANGS = ("pt", "en", "es")
CHAT = {lg: json.loads(_read(f"locales/{lg}.json")) for lg in LANGS}
MINI = {lg: json.loads(_read(f"miniapp/i18n/{lg}.json")) for lg in LANGS}

_ORIG_ON = crv.caravana_on
_ORIG_FLAG = crv._flag


def _set_flag(caravana: bool, cidades: bool = True, dungeons: bool = True) -> None:
    """Patch do gate ATÓMICO (`_flag`), não do agregado — assim a conjunção
    continua a ser exercitada de verdade em vez de curto-circuitada."""
    vals = {"caravana": caravana, "cidades": cidades,
            "dungeons_regionais": dungeons}
    crv._flag = lambda name, world_key=None: bool(vals.get(name, False))


class ExplodingSession:
    """Qualquer query com a flag OFF é um bug — a OFF-identity é literal."""

    def __getattr__(self, name):
        if name in ("rollback",):
            return lambda *a, **k: None

        def _boom(*a, **k):
            raise AssertionError(f"query executada com flag OFF ({name})")
        return _boom


def _player(**kw):
    base = {"telegram_id": 1, "current_continent": "linghe", "language": "pt",
            "karma": 0, "realm": 3}
    base.update(kw)
    return types.SimpleNamespace(**base)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] OFF-identity — a flag OFF não toca em nada")
# ═══════════════════════════════════════════════════════════════════════════
_set_flag(False)
check("off/caravana_on é False", crv.caravana_on() is False)
check("off/origin_note devolve None",
      crv.origin_note("herb", 11, "pt", "linghe") is None)
check("off/origin_note em TODO material",
      all(crv.origin_note(k, i, "pt", "linghe") is None
          for (k, i) in confined_materials()))
check("off/caravan_view não faz query",
      asyncio.run(crv.caravan_view(ExplodingSession(), _player(), "pt")) is None)
check("off/credit_arrived não faz query",
      asyncio.run(crv.credit_arrived(ExplodingSession(), _player())) == [])
_snd = asyncio.run(crv.send_load(ExplodingSession(), _player(),
                                 target_kind="herb", target_id=11,
                                 pay_kind="ore", pay_id=2))
check("off/send_load recusa NOMEADA",
      _snd.get("ok") is False and bool(_snd.get("line")), str(_snd))
check("off/a recusa não vaza chaveta", "{" not in str(_snd.get("line", "")))

# A prova REAL da OFF-identity não é o retorno neutro (o `except Exception` do
# engine engoliria um AssertionError e devolveria o mesmo neutro — a lição está
# escrita no molde do MV-9). É a conjunção: neutro + o gate ser a PRIMEIRA coisa
# + a key ser condicional no payload.
for fn in (crv.caravan_view, crv.credit_arrived, crv.send_load, crv.origin_note):
    src = inspect.getsource(fn)
    check(f"off/{fn.__name__} testa o gate antes de qualquer I/O",
          "caravana_on()" in src)
_ws = _read("core/webserver.py")
check("off/a key `caravan` é CONDICIONAL no payload da praça",
      '**({"caravan": caravan_block} if caravan_block else {}),' in _ws)
check("off/a key `origin` é CONDICIONAL na alquimia",
      _ws.count('**({"origin": _org} if _org else {}),') >= 2)
check("off/a key `origin` do inventário é condicional",
      'if _org:\n                    entry["origin"] = _org' in _ws)

# ═══════════════════════════════════════════════════════════════════════════
print("[2] A CONJUNÇÃO DURA — sem geografia a onda não existe")
# ═══════════════════════════════════════════════════════════════════════════
_set_flag(True, cidades=True, dungeons=True)
check("conj/as três ON → ligada", crv.caravana_on() is True)
_set_flag(True, cidades=False, dungeons=True)
check("conj/sem `cidades` → desligada", crv.caravana_on() is False)
_set_flag(True, cidades=True, dungeons=False)
check("conj/sem `dungeons_regionais` → desligada", crv.caravana_on() is False)
_set_flag(False, cidades=True, dungeons=True)
check("conj/só as irmãs → desligada", crv.caravana_on() is False)
check("conj/o motivo está escrito no gate",
      "dungeons_regionais" in inspect.getsource(crv.caravana_on))
_dbsrc = _read("database/db.py")
check("conj/a desc da flag DIZ a dependência ao owner",
      "dungeons_regionais" in MINI["pt"]["feature_caravana_desc"])
check("conj/a flag nasce False", bool(re.search(r'"caravana":\s+False,', _dbsrc)))

_set_flag(True)

# ═══════════════════════════════════════════════════════════════════════════
print("[3] CARAVAN_META")
# ═══════════════════════════════════════════════════════════════════════════
check("meta/5 cidades", len(CARAVAN_META) == 5, str(len(CARAVAN_META)))
check("meta/uma por continente",
      sorted(m["continent"] for m in CARAVAN_META.values()) == sorted(CONTINENT_KEYS))
for ck, m in CARAVAN_META.items():
    for field in ("continent", "caravan", "ratio", "soul",
                  "npc_name_key", "npc_intro_key"):
        check(f"meta/{ck}.{field}", field in m)
    for kf in ("npc_name_key", "npc_intro_key"):
        key = m[kf]
        for lg in LANGS:
            check(f"meta/{ck}.{kf} existe em {lg}", key in CHAT[lg], key)
            check(f"meta/{ck}.{kf} sem placeholder em {lg}",
                  "{" not in str(CHAT[lg].get(key, "")))
check("meta/só Mòyǔ não tem caravana",
      [k for k, m in CARAVAN_META.items() if not m["caravan"]] == ["huiyin"])
check("meta/Wànshì paga a razão pior (é o entreposto)",
      CARAVAN_META["wanshi"]["ratio"] == CRV_RATIO_HUB > CRV_RATIO)
check("meta/Qiānhé gateia por karma",
      "karma_min" in CARAVAN_META["tiequan"]["soul"])
check("meta/Yǎnshān recusa o demoníaco",
      CARAVAN_META["wanhua"]["soul"].get("reject_path") == "demonic")
check("meta/nenhum gate por REPUTAÇÃO (alcança 1 pessoa nas 2 DBs)",
      not any("rep" in str(m["soul"]) for m in CARAVAN_META.values()))

# ═══════════════════════════════════════════════════════════════════════════
print("[4] O MAPA DERIVADO — a medição que derrubou o spec")
# ═══════════════════════════════════════════════════════════════════════════
check("der/o mapa não está vazio", len(crv.origins()) >= 20, str(len(crv.origins())))
check("der/é PURO — mesma entrada, mesma saída",
      material_origin("herb", 11) == material_origin("herb", 11))

_fd = material_origin("herb", 11)
_pa = material_origin("ore", 8)
_ds = material_origin("ore", 9)
_fl = material_origin("herb", 3)
check("der/Frost Dew nasce em Qiānhé", _fd["continents"] == ["qianhe"], str(_fd))
check("der/Frost Dew entra a partir do reino 2", _fd["gate_realm"].get("qianhe") == 2)
# ⚠️ ESTES TRÊS SÃO O CORAÇÃO DA ONDA. O spec de 07/08 afirmava exclusividade
# e o código diz outra coisa; imprimir a exclusividade seria um display-lie
# criado por esta onda para vender a caravana.
check("der/⚠️ Frost Dew TAMBÉM cai da caçada (o furo que matou o spec)",
      "hunt" in _fd["sources"], str(_fd["sources"]))
check("der/⚠️ Phoenix Ash cai em DOIS continentes (REGIONAL_BONUS_LOOT dá-o a Fēnghuǒ)",
      _pa["continents"] == ["fenghuo", "yanshan"], str(_pa))
check("der/Dragon Scale é mesmo só de Fēnghuǒ", _ds["continents"] == ["fenghuo"])
check("der/Foundation Lotus é muro para 3 dos 5 continentes",
      _fl["continents"] == ["linghe", "qianhe"], str(_fl))
_reg = _read("core/dungeon_regions.py")
check("der/a fonte do furo do Phoenix Ash continua no código",
      '"fenghuo": {"ores": {"8": 1}}' in _reg)
_cbt = _read("core/combat_engine.py")
check("der/a fonte do furo do Frost Dew continua no código",
      '{"type": "herb", "tier": 3' in _cbt)

# O mapa lê AS DUAS geografias (seeds + EXPLORATION_NODES) — ler só uma
# sub-declarava a origem e a frase mentia por omissão.
_src = inspect.getsource(crv._build_origins)
for fonte in ("DUNGEON_SEEDS", "EXPLORATION_NODES", "REGIONAL_BONUS_LOOT",
              "NPC_LOOT_TABLE", "EXPEDITIONS", "WORLD_BOSS_POOL",
              "FORGE_RECIPES", "STORYLET_SEEDS"):
    check(f"der/deriva de {fonte}", fonte in _src)
check("der/cada fonte tem o seu try/except (uma que falhe não cala as outras)",
      _src.count("except Exception") >= 6, str(_src.count("except Exception")))

# ═══════════════════════════════════════════════════════════════════════════
print("[5] OS MUROS, AS ROTAS E O TETO DE TIER")
# ═══════════════════════════════════════════════════════════════════════════
_walls = confined_materials()
check("muro/são exatamente 4", len(_walls) == 4, str(_walls))
for k in (("herb", 3), ("herb", 11), ("ore", 8), ("ore", 9)):
    check(f"muro/{k} é muro", k in _walls)
# ⚠️ O critério frouxo ("< 5 continentes") daria 21 de 25 e reabria a
# prateleira que o §0.4 do spec refutou por aritmética.
check("muro/o critério NÃO é apenas 'confinado'",
      len([k for k in crv.origins() if crv.is_confined(*k)]) > len(_walls))
check("muro/nenhum t1/t2 é muro",
      all(int(material_origin(*k)["tier"]) >= CRV_ROUTE_MIN_TIER for k in _walls))
check("muro/nenhum muro cai em mais de 2 continentes",
      all(len(material_origin(*k)["continents"]) <= CRV_ROUTE_MAX_CONTINENTS
          for k in _walls))
check("muro/Qi Root (t1) NÃO é transportável", not is_walled("herb", 1))

for cont in CONTINENT_KEYS:
    rts = routes_for(cont)
    if cont == "moyu":
        check("rota/Mòyǔ não tem rota nenhuma", rts == [], str(rts))
        continue
    check(f"rota/{cont} tem rotas", len(rts) > 0)
    for k in rts:
        # A recusa nº1, provada estruturalmente: nenhuma cidade manda vir o que
        # o chão dela dá. É o que impede Tiānhuǒ de vender Phoenix Ash.
        check(f"rota/{cont} NÃO manda vir {k} (produz cá)",
              not produced_in(k[0], k[1], cont))
        q = quote(cont, *k)
        check(f"rota/{cont}/{k} é SINK estrito", q["cost"] > q["units"],
              f"{q['cost']} vs {q['units']}")
        pays = accepted_payments(cont, *k)
        check(f"rota/{cont}/{k} aceita algum pagamento", len(pays) > 0)
        floor = int(material_origin(*k)["tier"]) - CRV_PAY_TIER_SLACK
        for p in pays:
            check(f"pag/{cont}/{k}: {p} respeita o piso t{floor}",
                  int(material_origin(*p)["tier"]) >= floor)
            check(f"pag/{cont}/{k}: {p} é produzido em {cont}",
                  produced_in(p[0], p[1], cont))
        check(f"pag/{cont}/{k}: o alvo não se paga a si próprio", k not in pays)
check("rota/Fēnghuǒ NÃO manda vir Phoenix Ash (o chão dele dá)",
      ("ore", 8) not in routes_for("fenghuo"))

# ── SINK EM PEDRAS, não só em unidades ────────────────────────────────────
# ⚠️ Este bloco existe porque a 1ª bancada dava VERDE medindo só unidades. Em
# unidades a caravana sempre foi sink; em PEDRAS era uma impressora de +6.924
# por carga (12 Foundation Lotus a 576 por 3 Dragon Scale a 7.500), porque erva
# e minério vivem em escalas de preço ~15× diferentes. O §8 do spec afirma "é um
# SINK" — a régua tem de ser o VALOR, ou a promessa é um display-lie.
_inv_src = _read("handlers/inventory.py")
check("val/o espelho do balcão bate com handlers/inventory.py (ORE)",
      "ORE_SELL_PER_UNIT = {1: 80, 2: 250, 3: 800, 4: 2_500, 5: 8_000}" in _inv_src
      and crv._ORE_SELL_PER_UNIT == {1: 80, 2: 250, 3: 800, 4: 2500, 5: 8000})
check("val/o espelho do balcão bate com handlers/inventory.py (HERB)",
      "HERB_SELL_RATIO = 0.6" in _inv_src and crv._HERB_SELL_RATIO == 0.6)
check("val/o fallback t6/t7 é lido COMO ESTÁ (o veto não é contornado)",
      crv.stone_value("ore", 7) == 80 and crv.stone_value("ore", 6) == 80)
for cont in CONTINENT_KEYS:
    for k in routes_for(cont):
        q = quote(cont, *k)
        _out_v = crv.stone_value(*k) * q["units"]
        _pays = accepted_payments(cont, *k)
        check(f"val/{cont}/{k} tem pagamento depois do filtro de valor", bool(_pays))
        for p in _pays:
            check(f"val/{cont}/{k}: {p} é sink em PEDRAS",
                  crv.stone_value(*p) * q["cost"] > _out_v,
                  f"{crv.stone_value(*p) * q['cost']} <= {_out_v}")
        if _pays:
            check(f"val/{cont}/{k}: o mais barato vem primeiro",
                  crv.stone_value(*_pays[0]) * q["cost"]
                  == min(crv.stone_value(*p) * q["cost"] for p in _pays))
check("rota/Wànshì manda vir os três que Línghé não tem",
      set(routes_for("linghe")) == {("herb", 11), ("ore", 8), ("ore", 9)},
      str(routes_for("linghe")))

# ═══════════════════════════════════════════════════════════════════════════
print("[6] A CARGA NO LEDGER — ZERO tabela, ZERO coluna")
# ═══════════════════════════════════════════════════════════════════════════
_eng = _read("core/caravan_engine.py")
check("carga/type='caravan'", crv.CARAVAN_TX_TYPE == "caravan")
check("carga/reusa o escritor único do ledger", "create_transaction" in _eng)
check("carga/price=0 (não polui o Relatório do Mercado)", "price=0" in _eng)
check("carga/o prazo é aritmética sobre created_at",
      "created + timedelta" in _eng)
check("carga/o débito é row-locked e all-or-nothing",
      "debit_materials" in _eng)
check("carga/o débito é a ÚLTIMA coisa antes do savepoint",
      _eng.index("debit_materials(") < _eng.index("create_transaction("))
check("carga/savepoint próprio (duplo-tap não envenena o caller)",
      "begin_nested" in _eng)
check("carga/o crédito serializa com FOR UPDATE",
      "with_for_update" in inspect.getsource(crv._pending_rows))
check("carga/idempotência por delivered_at",
      "delivered_at" in inspect.getsource(crv.credit_arrived))
check("carga/MERGE no JSONB, nunca substituir o payload",
      "{**(row.details or {}), \"delivered_at\"" in _eng)
check("carga/o minério vai por `add_item_to_inventory` (que agora desvia)",
      "add_item_to_inventory" in inspect.getsource(crv._grant))
check("carga/mochila cheia NÃO marca entregue (a carga espera)",
      "bag_full" in inspect.getsource(crv.credit_arrived))


class _FakeRow:
    def __init__(self, created_at, details=None, item_type="ore", item_id=9, qty=3):
        self.id = 1
        self.created_at = created_at
        self.details = details if details is not None else {"city": "wanshi"}
        self.item_type = item_type
        self.item_id = item_id
        self.quantity = qty


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Sessão mínima para exercitar o crédito. Conta as entregas."""

    def __init__(self, rows):
        self.rows = rows
        self.granted: list[tuple] = []

    async def execute(self, _stmt):
        return _FakeResult(self.rows)


async def _credit_with(rows):
    sess = _FakeSession(rows)
    granted: list[tuple] = []

    async def _fake_grant(session, pid, kind, iid, qty):
        granted.append((kind, iid, qty))
        return True

    orig = crv._grant
    crv._grant = _fake_grant
    try:
        out = await crv.credit_arrived(sess, _player(), now=NOW)
    finally:
        crv._grant = orig
    return out, granted


_arrived = _FakeRow(NOW - timedelta(hours=CRV_ETA_HOURS + 1))
_out, _granted = asyncio.run(_credit_with([_arrived]))
check("carga/uma carga vencida é creditada", len(_granted) == 1, str(_granted))
check("carga/creditou a quantidade certa", _granted and _granted[0][2] == 3)
check("carga/marcou delivered_at", bool((_arrived.details or {}).get("delivered_at")))
check("carga/o MERGE preservou o payload antigo",
      (_arrived.details or {}).get("city") == "wanshi", str(_arrived.details))
# Segunda passagem sobre a MESMA row: nada é creditado outra vez.
_out2, _granted2 = asyncio.run(_credit_with([_arrived]))
check("carga/IDEMPOTENTE — a 2ª passagem não credita nada", _granted2 == [],
      str(_granted2))

_transit = _FakeRow(NOW - timedelta(hours=max(0.0, CRV_ETA_HOURS - 2)))
_out3, _granted3 = asyncio.run(_credit_with([_transit]))
check("carga/uma carga ainda na estrada NÃO é creditada", _granted3 == [])
check("carga/e continua sem delivered_at",
      not (_transit.details or {}).get("delivered_at"))

_lixo = _FakeRow(NOW - timedelta(hours=CRV_ETA_HOURS + 1), item_type="", item_id=0)
_out4, _granted4 = asyncio.run(_credit_with([_lixo]))
check("carga/uma linha impossível NÃO tranca o jogador para sempre",
      bool((_lixo.details or {}).get("delivered_at")) and _granted4 == [])

# ═══════════════════════════════════════════════════════════════════════════
print("[7] AS RECUSAS — todas nomeadas (Lei §1)")
# ═══════════════════════════════════════════════════════════════════════════
_send_src = inspect.getsource(crv.send_load)
for reason in ("no_caravan", "load_open", "produced_here", "not_routable",
               "encargo_conflict", "pay_invalid", "pay_short", "caravana_off"):
    check(f"recusa/{reason} existe", f'"{reason}"' in _send_src)
for key in ("crv_refuse_no_caravan", "crv_refuse_open", "crv_refuse_here",
            "crv_refuse_not_routable", "crv_refuse_encargo",
            "crv_refuse_pay_invalid", "crv_refuse_pay_short",
            "crv_refuse_flag", "crv_refuse_karma", "crv_refuse_path",
            "crv_refuse_busy"):
    check(f"recusa/{key} tem string ×3",
          all(key in CHAT[lg] for lg in LANGS))
check("recusa/o erro interno TAMBÉM diz algo (ok:false com 200 não dispara catch)",
      "crv_refuse_busy" in _send_src)
check("recusa/a recusa por ALMA vem ANTES de qualquer conta",
      _send_src.index("_soul_refusal") < _send_src.index("_pending_rows"))
check("recusa/credita ANTES de contar cargas abertas",
      _send_src.index("credit_arrived") < _send_src.index("CRV_MAX_OPEN"))
_soul_src = inspect.getsource(crv._soul_refusal)
check("alma/lê karma pelo engine sem gate de flag", "get_karma" in _soul_src)
check("alma/lê o Caminho pelo engine sem gate de flag",
      "get_player_path" in _soul_src)

# ═══════════════════════════════════════════════════════════════════════════
print("[8] WIRING — todo helper tem call site real")
# ═══════════════════════════════════════════════════════════════════════════
_paths = {
    "core/webserver.py": ["caravan_view", "send_load",
                          "world/caravan", "world/caravan_send", "_origin_note"],
    "core/travel_engine.py": ["credit_arrived"],
    "core/utils.py": ["_add_ore"],
}
for rel, needles in _paths.items():
    src = _read(rel)
    for n in needles:
        check(f"wire/{rel} usa {n}", n in src)
check("wire/as 2 rotas estão registadas",
      _ws.count('app.router.add_post("/api/miniapp/world/caravan"') == 1
      and _ws.count('app.router.add_post("/api/miniapp/world/caravan_send"') == 1)
check("wire/o endpoint da vitrine trava o jogador (credita)",
      "with_for_update" in _ws.split("async def api_world_caravan(")[1][:1500])
check("wire/o send comita SÓ no ok",
      'if result.get("ok"):' in _ws.split("async def api_world_caravan_send(")[1][:2500])
check("wire/QUEM FINALIZA CREDITA — a viagem também credita",
      "credit_arrived" in _read("core/travel_engine.py"))
check("wire/o hook da viagem tem try/except INTERNO (load-bearing)",
      "caravan credit on travel failed" in _read("core/travel_engine.py"))

# ═══════════════════════════════════════════════════════════════════════════
print("[9] i18n / PT-BR")
# ═══════════════════════════════════════════════════════════════════════════
check("i18n/paridade chat", len({len(v) for v in CHAT.values()}) == 1,
      str([len(v) for v in CHAT.values()]))
check("i18n/paridade mini", len({len(v) for v in MINI.values()}) == 1,
      str([len(v) for v in MINI.values()]))
_MV95 = [k for k in CHAT["pt"] if k.startswith("crv_")]
check("i18n/o lote existe", len(_MV95) >= 30, str(len(_MV95)))
for k in _MV95:
    for lg in LANGS:
        check(f"i18n/{k} em {lg}", k in CHAT[lg])
    sets = [set(re.findall(r"\{(\w+)\}", CHAT[lg][k])) for lg in LANGS]
    check(f"i18n/{k} placeholders simétricos", sets[0] == sets[1] == sets[2])
_EUPT = (r"\becrã\b", r"\butilizador", r"\bficheiro", r"\bapanh\w+",
         r"\bestá a \w+r\b", r"\bnoutr[ao]s?\b", r"\ba meio d[eao]\b",
         r"\bartefacto", r"\bcarregue em\b", r"\bclique em\b",
         r"\b(tu|teu|tua|teus|tuas|vosso|vossa|contigo)\b")
for k in _MV95:
    v = CHAT["pt"][k]
    for pat in _EUPT:
        check(f"ptbr/{k} sem EU-PT", not re.search(pat, v, re.I), pat)
check("i18n/o velho DIZ que ir a pé é melhor",
      all("crv_better_to_go" in CHAT[lg] for lg in LANGS))
for lg in LANGS:
    check(f"i18n/{lg}: nenhuma string promete exclusividade",
          not any(re.search(r"\b(só (nasce|cai)|only (grows|drops)|solo (nace|cae))\b",
                            str(v).lower())
                  for k, v in CHAT[lg].items() if k.startswith("crv_")))
check("i18n/zero keys notif_ nesta onda",
      not [k for k in CHAT["pt"] if k.startswith("notif_crv")])

# A linha de origem, renderizada: nunca vaza chaveta em nenhuma língua.
for (kind, iid) in _walls:
    for lg in LANGS:
        line = origin_line(kind, iid, lg)
        check(f"i18n/origin_line {kind}{iid}/{lg} não vaza chaveta",
              "{" not in line and "}" not in line, line[:60])
        check(f"i18n/origin_line {kind}{iid}/{lg} não é vazia", bool(line))
        o = material_origin(kind, iid)
        if o["sources"]:
            check(f"i18n/origin_line {kind}{iid}/{lg} DIZ as fontes sem geografia",
                  len(line) > len(str(o["continents"])), line[:60])

# ═══════════════════════════════════════════════════════════════════════════
print("[10] ZERO migration + as dívidas do §4 pagas")
# ═══════════════════════════════════════════════════════════════════════════
_migs = sorted(m for m in os.listdir(os.path.join(ROOT, "migrations"))
               if m.endswith(".sql"))
# ⚠️ 2026-09-07 — esta guarda dizia "nenhuma migration 140+ nasceu", e isso
# NAO e' o que ela quer provar: quer provar que ESTA onda nao criou migration.
# Escrita como um tecto global, ela fica vermelha sempre que QUALQUER onda
# futura acrescentar uma (foi o que a Mig 140 do genero fez a SETE suites de
# uma vez). O invariante durável e' o do ASSUNTO: nenhuma migration do repo
# fala desta onda — isso continua verdade daqui a cem migrations.
_cita = [m for m in _migs if m.endswith(".sql")
         and "caravan" in (m + _read(f"migrations/{m}")).lower()]
check("mig/esta onda não criou migration (nenhuma cita a caravana)",
      not _cita, str(_cita))
check("mig/nenhuma migration cita a caravana",
      not any("caravan" in _read(f"migrations/{m}").lower() for m in _migs))

# §4.5 — os três escritores de minério na tabela errada
_utils = _read("core/utils.py")
check("dív/o desvio do minério vive no CHOKEPOINT (fecha os 4, não só os 3)",
      'if str(item_type) == "ore":' in _utils and "_add_ore(" in _utils)
check("dív/_add_ore não filtra quantity>0 ao decidir insert-vs-update",
      "PlayerOre.ore_id == ore_id," in _utils
      and "quantity > 0" in _utils.split("async def _add_ore")[1].split("if row is not None")[0])
check("dív/_add_ore ZERA o órfão, nunca o apaga",
      "orphan.quantity = 0" in _utils and "session.delete(orphan)" not in _utils)
check("dív/api_inventory lê AS DUAS tabelas de minério",
      "PlayerOre.ore_id, PlayerOre.quantity" in _ws)
check("dív/e funde por ore_id para não duplicar", "_inv_ore_qty" in _ws)
# §4.1 — o comprador nunca era travado antes do débito
_mkt = _read("handlers/market.py")
_eco = _read("core/economy.py")
# ⚠️ O lock TEM de ser ordenado e viver no ENGINE. Travar o comprador no
# endpoint era o fix óbvio e criava um deadlock AB-BA que não existia antes:
# A segurando Player A + listing_B à espera de Player B, e B o simétrico.
check("dív/existe o lock ordenado (anti AB-BA)",
      "async def _lock_players_ordered" in _eco)
check("dív/…e ordena mesmo por telegram_id ascendente",
      "sorted({int(p) for p in player_ids" in _eco)
check("dív/buy_listing e buy_partial usam-no",
      _eco.count("_lock_players_ordered(session, buyer.telegram_id") == 2)
check("dív/o comprador NÃO é travado no endpoint (ordem errada)",
      "select(Player).where(Player.telegram_id == user_id).with_for_update()"
      not in _ws.split("async def api_market_buy")[1][:2000])
check("dív/nem no chat", "with_for_update()" not in
      _mkt.split("async def buy_confirm_callback")[1][:1800])
check("dív/o crédito do vendedor continua row-locked",
      "seller.spirit_stones += seller_receive" in _eco)
check("dív/buy_confirm_callback tem @rate_limit",
      "@rate_limit(1)\nasync def buy_confirm_callback" in _mkt)
# §4.4 — o único leitor de transactions sem filtro de type
check("dív/o histórico do mercado exclui a caravana",
      'Transaction.type != "caravan"' in _mkt)
# §4.2 — o mercado vazio deixa de ser uma lista em branco
check("dív/o mercado vazio tem hint honesto",
      all("market_empty_hint" in MINI[lg] for lg in LANGS))
# A dívida da 25ª flag
for lg in LANGS:
    check(f"dív/o painel do owner nomeia marca_do_tracado ({lg})",
          bool(MINI[lg].get("feature_marca_do_tracado")))
    check(f"dív/…e a caravana ({lg})", bool(MINI[lg].get("feature_caravana")))

# ═══════════════════════════════════════════════════════════════════════════
print("[11] AS SUPERFÍCIES — por grep (o cliente não tem outra rede)")
# ═══════════════════════════════════════════════════════════════════════════
_tabs = _read("miniapp/components/tabs.js")
_app = _read("miniapp/components/app.js")
_sect = _read("handlers/sect.py")
_main = _read("main.py")

# ── mini-app ──────────────────────────────────────────────────────────────
check("cli/CaravanCard existe", "function CaravanCard(" in _tabs)
check("cli/CaravanModal existe", "function CaravanModal(" in _tabs)
check("cli/o card é payload-driven (a key ausente = flag OFF)",
      "d.caravan" in _tabs)
check("cli/o modal chama o endpoint", 'useApi("world/caravan"' in _tabs)
check("cli/o envio chama o endpoint", '"world/caravan_send"' in _tabs)
check("cli/trata {ok:false} com HTTP 200 (o catch nunca dispara)",
      "ok === false" in _tabs)
check("cli/a linha honesta do velho aparece", "honest_line" in _tabs)
check("cli/a origem é impressa CRUA (server-resolved, nunca t())",
      "origin.line" in _tabs)
check("cli/o atlas é renderizado", "crv_atlas_title" in _tabs)
check("cli/o mercado vazio ganhou a frase honesta",
      "market_empty_hint" in _tabs)
check("cli/a porta da ilha existe", "hub_mundo_caravana" in _tabs)
# A conjunção TEM de ser respeitada no cliente, senão a porta 🐫 abre um modal
# trancado num mundo com `caravana` ON e uma das irmãs OFF.
check("cli/existe o helper da conjunção", "function caravanEnabled()" in _app)
check("cli/o helper ANDa as três flags",
      all(f in _app.split("function caravanEnabled()")[1][:320]
          for f in ("caravana", "cidades", "dungeons_regionais")))
check("cli/nenhuma entrada usa a flag solta",
      'featureEnabled("caravana")' not in _tabs
      and 'onOpenCaravan={featureEnabled("caravana")' not in _app)
# Os 4 sítios do modal root — sem eles o back nativo FECHA o webapp.
check("cli/modal root 1/4: estado", "caravanOpen" in _app)
check("cli/modal root 2/4: _anyModalOpen",
      "caravanOpen" in _app.split("const _anyModalOpen")[1][:900])
check("cli/modal root 3/4: _handleBack faz peel",
      "setCaravanOpen(false)" in _app)
check("cli/modal root 4/4: está no ModalErrorBoundary",
      _app.index("<CaravanModal") > _app.index('label="root-modal"'))

# ── chat ──────────────────────────────────────────────────────────────────
check("chat/o /praca lê a caravana", "caravan_view" in _sect)
check("chat/o router existe", "async def caravan_button_router" in _sect)
check("chat/o router trava o jogador", "with_for_update" in
      _sect.split("async def caravan_button_router")[1][:2200])
# UM answer por INVOCAÇÃO, não uma ocorrência no source: os ramos de saída
# antecipada respondem uma vez cada e retornam. O que mataria o alerta é um
# `safe_answer(query)` vazio a preceder o `show_alert=True` no MESMO caminho.
_NL = chr(10)
_crv_router = _sect.split("async def caravan_button_router")[1].split(
    _NL + "async def ")[0]
check("chat/exatamente UM alerta no router",
      _crv_router.count("show_alert=True") == 1,
      str(_crv_router.count("show_alert=True")))
# Todo `safe_answer(query)` VAZIO tem de ser seguido imediatamente de `return`:
# um answer vazio a preceder o alerta no MESMO caminho fá-lo-ia ser ENGOLIDO
# pelo Telegram (a lição "A Volta"). Cinco ocorrências no source não são cinco
# respostas — são cinco ramos de saída, cada um respondendo uma vez.
_vazios = _crv_router.count("await safe_answer(query)" + _NL)
_seguidos = sum(
    _crv_router.count("await safe_answer(query)" + _NL + " " * n + "return True")
    for n in (8, 12))
check("chat/todo answer vazio retorna imediatamente (não engole o alerta)",
      _vazios == _seguidos, f"{_vazios} vazios, {_seguidos} seguidos de return")
# ⚠️ O passo que TEM de ser feito ANTES: o prefixo registado no dispatcher
# central. Sem ele o callback cai no fall-through e o botão gira até timeout.
check("chat/o prefixo crv_ está no combined_button_router",
      'startswith("crv_")' in _main)
check("chat/…e o router está importado", "caravan_button_router" in _main)
check("chat/o botão só nasce depois do registo",
      'startswith("crv_")' in _main and 'f"crv_s_' in _sect)
check("chat/o callback_data cabe nos 64 bytes",
      len('crv_s_h11_o2') <= 64 and "crv_s_" in _sect)
check("chat/os botões MERGEM em rows (nunca reatribuem)",
      "rows += _crv_rows" in _sect)
check("chat/o /praca comita quando creditou", "_crv" in _sect)
# O crédito nunca pode ser desfeito por um ramo de recusa.
check("chat/o router NÃO faz rollback (descreditaria a carga)",
      "await session.rollback()" not in _crv_router)
check("chat/o router comita", "await session.commit()" in _crv_router)
# A disclosure no chat, nas 3 telas.
for rel in ("handlers/alchemy.py", "handlers/artifacts.py", "handlers/inventory.py"):
    check(f"chat/{rel} imprime a origem", "origin_note" in _read(rel))

# restaurar os originais ANTES de sair (o teste não deixa rasto)
crv.caravana_on = _ORIG_ON
crv._flag = _ORIG_FLAG

print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)
print(f"OK — {PASS} asserts. O jogo passa a dizer onde nascem as coisas, "
      "e a caravana nunca é melhor do que ir.")
