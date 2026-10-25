# -*- coding: utf-8 -*-
"""MV-11 天时 "O Tempo do Céu" — suite COMMITTED.

Molde: `scripts/_test_mv95_caravana.py` (a mais recente, e a que patcha o gate
ATÓMICO `_flag` em vez do agregado — assim o gate real é exercitado de verdade
em vez de curto-circuitado). Corre standalone, ZERO base de dados:

    python -X utf8 scripts/_test_mv11_tianshi.py

Cobre, por secção:
  1. OFF-identity — flag OFF não faz UMA query, não emite UMA key, e
     `get_tribulation_power` devolve EXATAMENTE o que sempre devolveu
  2. A camada PURA — determinismo, `world_key` na semente, ordem contratada,
     epoch wall-clock (imune ao drift de boot)
  3. Os três céus — o neutro é 1.00 EXATO, pesos, simetria
  4. O DENTE no chokepoint — e a armadilha dos TRÊS `return` que o spec não viu
  5. `sky_view` — o antes→depois é DERIVADO por divisão, nunca por 2ª chamada
  6. O ÚNICO futuro escrito — `epoch+1`, as horas, e o ramo honesto de <1h
  7. A Crônica — só quando VIRA, idempotente por epoch, OFF sem query
  8. WIRING por grep — todo helper tem call site real
  9. AS SUPERFÍCIES por grep — as 2 telas do chat e os 3 renders do mini
 10. i18n / PT-BR / a lei dual-surface (zero markdown)
 11. ZERO migration
"""
from __future__ import annotations

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

import core.tianshi_engine as tsh  # noqa: E402
import core.tribulation_engine as trib  # noqa: E402
from core.tianshi_engine import (  # noqa: E402
    CHRON_EVENT_TYPE, SKIES, TIANSHI_TICK_HOURS, _ORDER,
    hours_to_next, next_change_at, seed_for, sky_for, sky_mult,
    sky_of, sky_plaza_view, sky_view, tianshi_on, tick_epoch,
)
from core.tribulation_engine import (  # noqa: E402
    TRIBULATION_POWER_BY_REALM, calculate_rounds, estimate_success_chance,
    get_tribulation_power,
)

LANGS = ("pt", "en", "es")
CHAT = {lg: json.loads(_read(f"locales/{lg}.json")) for lg in LANGS}
MINI = {lg: json.loads(_read(f"miniapp/i18n/{lg}.json")) for lg in LANGS}

_ORIG_FLAG = tsh._flag
_ORIG_SKY_FOR = tsh.sky_for


def _set_flag(on: bool) -> None:
    """Patch do gate ATÓMICO (`_flag`), não do agregado — assim o gate real
    continua a ser exercitado de verdade em vez de curto-circuitado."""
    tsh._flag = lambda name, world_key=None: bool(on and name == "tempo_do_ceu")


class ExplodingSession:
    """Qualquer query com a flag OFF é um bug — a OFF-identity é literal."""

    def __getattr__(self, name):
        if name in ("rollback",):
            return lambda *a, **k: None

        def _boom(*a, **k):
            raise AssertionError(f"query executada com flag OFF ({name})")
        return _boom


def _epoch_of(sky: str, world: str = "main") -> int:
    """Um epoch REAL cujo céu é `sky` (procurado a partir do de agora). Não
    inventa nada: usa a função pura que shipa."""
    e0 = tick_epoch(NOW)
    for i in range(500):
        if sky_for(world, e0 + i) == sky:
            return e0 + i
    raise AssertionError(f"nenhum epoch com céu {sky} em 500 ticks")


def _now_of(epoch: int) -> datetime:
    """Um instante DENTRO daquele epoch (a meio, longe das fronteiras)."""
    step = TIANSHI_TICK_HOURS * 3600.0
    return datetime.fromtimestamp(epoch * step + step / 2.0, tz=timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] OFF-identity — a flag OFF não toca em nada")
# ═══════════════════════════════════════════════════════════════════════════
_set_flag(False)
check("off/tianshi_on é False", tianshi_on() is False)
check("off/sky_mult é 1.0 EXATO", sky_mult() == 1.0)
check("off/current_sky é None", tsh.current_sky() is None)
check("off/sky_view devolve None (key ausente, nunca null)",
      sky_view("pt", soul=5000, power=7700.0, rounds=9, defense_mult=0.05) is None)
check("off/sky_plaza_view devolve None", sky_plaza_view("pt") is None)
check("off/pulse_sky não faz UMA query",
      asyncio.run(tsh.pulse_sky(ExplodingSession())) is None)

# O contrato mais importante da onda: com a flag OFF o chokepoint é
# BYTE-IDÊNTICO ao que sempre foi — em todos os três ramos.
for realm in sorted(TRIBULATION_POWER_BY_REALM):
    base = float(TRIBULATION_POWER_BY_REALM[realm])
    check(f"off/trib_power r{realm} sem karma", get_tribulation_power(realm) == base)
    check(f"off/trib_power r{realm} karma=0", get_tribulation_power(realm, 0) == base)
    check(f"off/trib_power r{realm} karma=-900 (forbidden OFF)",
          get_tribulation_power(realm, -900) == base)
check("off/trib_power fora da tabela mantém o fallback realm*150",
      get_tribulation_power(99) == 99 * 150.0)

# ═══════════════════════════════════════════════════════════════════════════
print("[2] A CAMADA PURA — derivada, determinística, sem I/O")
# ═══════════════════════════════════════════════════════════════════════════
e0 = tick_epoch(NOW)
check("pure/mesma semente → mesmo céu", sky_for("main", e0 + 3) == sky_for("main", e0 + 3))
check("pure/o céu só sai do conjunto contratado",
      all(sky_for("main", e0 + i) in _ORDER for i in range(200)))
check("pure/a ordem é o contrato (reordenar SKIES mudaria a história toda)",
      tuple(_ORDER) == ("sereno", "irado", "velado"))
check("pure/a semente leva o world_key DENTRO (lição MV-8)",
      "main" in seed_for("main", 1) and seed_for("main", 1) != seed_for("s2", 1))
check("pure/a semente NÃO leva continente (o céu é do MUNDO)",
      all(c not in seed_for("main", 1)
          for c in ("linghe", "qianhe", "fenghuo", "yanshan", "moyu")))
_coin = sum(1 for i in range(200) if sky_for("main", e0 + i) == sky_for("s2", e0 + i))
check("pure/main e s2 contam histórias DIFERENTES", _coin < 200, f"{_coin}/200 coincidem")

# O epoch é wall-clock PURO — é isto que o torna imune ao drift de boot do
# World Pulse (que re-agenda a partir do BOOT: medido 00/06/12/18 → 03:52/…).
step = TIANSHI_TICK_HOURS * 3600.0
check("pure/epoch é wall-clock puro",
      tick_epoch(NOW) == int(NOW.timestamp() // step))
check("pure/epoch avança exatamente 1 por tick",
      tick_epoch(NOW + timedelta(hours=TIANSHI_TICK_HOURS)) == tick_epoch(NOW) + 1)
check("pure/epoch NÃO avança dentro do mesmo tick",
      tick_epoch(_now_of(e0)) == tick_epoch(_now_of(e0) + timedelta(minutes=1)))
_b = next_change_at(_now_of(e0))
check("pure/a fronteira do próximo epoch é exata",
      tick_epoch(_b) == e0 + 1 and tick_epoch(_b - timedelta(seconds=1)) == e0)
check("pure/hours_to_next nunca é negativo nem passa do tick",
      0.0 <= hours_to_next(_now_of(e0)) <= TIANSHI_TICK_HOURS)
check("pure/2 céus por dia (o default assado)", TIANSHI_TICK_HOURS == 12.0)

# ═══════════════════════════════════════════════════════════════════════════
print("[3] OS TRÊS CÉUS — o neutro é 1.00 EXATO")
# ═══════════════════════════════════════════════════════════════════════════
check("skies/são exatamente três (Lei §3)", len(SKIES) == 3)
# ⚠️ O veto do MV-9, à letra: bônus no estado neutro colapsa o rodízio (medido:
# uma opção saía 22-25× em 28). Aqui é `== 1.00`, nunca `~= 1.00`.
check("skies/o sereno é ×1.00 EXATO", SKIES["sereno"]["mult"] == 1.00)
check("skies/o irado é ×1.12 (a varredura decidiu)", SKIES["irado"]["mult"] == 1.12)
check("skies/o velado é ×0.88 (simétrico)", SKIES["velado"]["mult"] == 0.88)
check("skies/irado e velado são simétricos em torno de 1.0",
      abs((SKIES["irado"]["mult"] - 1.0) + (SKIES["velado"]["mult"] - 1.0)) < 1e-9)
check("skies/os pesos somam 100", sum(s["weight"] for s in SKIES.values()) == 100)
check("skies/o neutro é o mais provável", SKIES["sereno"]["weight"] == 50)
check("skies/sky_of degrada para o NEUTRO (nunca inventa severidade)",
      sky_of("nao_existe")["mult"] == 1.00 and sky_of(None)["mult"] == 1.00)
for sk in _ORDER:
    for f in ("emoji", "mult", "weight", "name_key", "phrase_key", "chron_key"):
        check(f"skies/{sk} tem {f}", f in SKIES[sk])

# ═══════════════════════════════════════════════════════════════════════════
print("[4] O DENTE — um chokepoint, cinco superfícies")
# ═══════════════════════════════════════════════════════════════════════════
_set_flag(True)
_R = 7
_base = float(TRIBULATION_POWER_BY_REALM[_R])
for sk in _ORDER:
    tsh.sky_for = lambda wk, ep, _s=sk: _s      # céu determinístico p/ o assert
    _m = float(SKIES[sk]["mult"])
    check(f"dente/{sk}: sky_mult devolve o multiplicador", sky_mult() == _m)
    check(f"dente/{sk}: get_tribulation_power multiplica a base",
          abs(get_tribulation_power(_R) - _base * _m) < 1e-9,
          f"{get_tribulation_power(_R)} vs {_base * _m}")
    # ⚠️ A ARMADILHA QUE O SPEC NÃO VIU: `get_tribulation_power` tinha TRÊS
    # `return`, e o do `if not karma` saía ANTES do passo do karma. O patch de
    # 4 linhas "depois do karma do TEC-5" seria código MORTO para toda a gente
    # com karma 0 — que é a esmagadora maioria dos jogadores. Este assert é o
    # que prova que o ramo karma-falsy também morde.
    check(f"dente/{sk}: o ramo karma=0 TAMBÉM morde (os 3 returns)",
          abs(get_tribulation_power(_R, 0) - _base * _m) < 1e-9)
    check(f"dente/{sk}: karma=None idem",
          abs(get_tribulation_power(_R, None) - _base * _m) < 1e-9)
tsh.sky_for = _ORIG_SKY_FOR

# Fail-safe: o céu NUNCA pode impedir uma tribulação.
def _boom_sky(*a, **k):
    raise RuntimeError("o céu explodiu")


_saved = tsh.sky_for
tsh.sky_for = _boom_sky
# O engine LOGA a exceção (é o que se quer: degrada mas deixa rasto). Aqui o
# rasto é ruído previsto — silenciado para o output da suite ficar legível.
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
try:
    check("dente/fail-safe: sky_mult degrada para 1.0", sky_mult() == 1.0)
    check("dente/fail-safe: o chokepoint devolve a base intacta",
          get_tribulation_power(_R) == _base)
    check("dente/fail-safe: sky_view degrada para None",
          sky_view("pt", soul=5000, power=_base, rounds=9) is None)
    check("dente/fail-safe: sky_plaza_view degrada para None",
          sky_plaza_view("pt") is None)
finally:
    logging.disable(logging.NOTSET)
tsh.sky_for = _saved

# O chokepoint continua a ser UM só — se alguém aplicar o céu por call-site,
# a previsão e a rolagem divergem no dia em que esquecer um.
_te = _read("core/tribulation_engine.py")
check("dente/o céu entra UMA vez, dentro do chokepoint",
      _te.count("from core.tianshi_engine import sky_mult") == 1)
check("dente/o import é FUNCTION-LOCAL (este ficheiro não tem core.* no topo)",
      not re.search(r"^from core\.|^import core\.", _te, re.M))
# ⚠️ UM único ponto de saída. Antes desta onda havia TRÊS `return`, e o do
# `if not karma` saía ANTES do passo do karma — qualquer modificador colocado
# "depois do karma" seria código morto para quem tem karma 0. O corpo termina
# no próximo `def`/`async def` a começo de linha.
_gtp = re.split(r"\n(?:async )?def ", _te.split("def get_tribulation_power")[1])[0]
check("dente/get_tribulation_power tem UM único return",
      len(re.findall(r"^    return ", _gtp, re.M)) == 1,
      str(re.findall(r"^    return .*", _gtp, re.M)))
check("dente/…e o céu é aplicado ANTES desse return", _gtp.rindex("sky_mult") < _gtp.rindex("return base"))
for _f in ("handlers/tribulation.py", "core/webserver.py"):
    check(f"dente/{_f} NÃO aplica o céu por call-site",
          "sky_mult(" not in _read(_f))

# ═══════════════════════════════════════════════════════════════════════════
print("[5] sky_view — o antes→depois é DERIVADO, não re-perguntado")
# ═══════════════════════════════════════════════════════════════════════════
_set_flag(True)
_soul, _rounds, _dm = 6254, calculate_rounds(_R), 0.05
for sk in _ORDER:
    ep = _epoch_of(sk)
    now = _now_of(ep)
    m = float(SKIES[sk]["mult"])
    power = _base * m                     # o que o chokepoint devolveria
    v = sky_view("pt", soul=_soul, power=power, rounds=_rounds,
                 defense_mult=_dm, now=now)
    check(f"view/{sk}: devolve bloco", isinstance(v, dict) and v.get("key") == sk)
    check(f"view/{sk}: mult certo", v["mult"] == m)
    check(f"view/{sk}: pct sinalizado e inteiro",
          v["pct"] == int(round((m - 1.0) * 100)))
    exp_after = estimate_success_chance(_soul, power, "resist", _rounds, defense_mult=_dm)
    exp_before = estimate_success_chance(_soul, _base, "resist", _rounds, defense_mult=_dm)
    check(f"view/{sk}: o DEPOIS é a chance que a tela já imprime",
          v["after"] == exp_after, f"{v['after']} vs {exp_after}")
    # ⚠️ O "antes" NÃO pode vir de uma 2ª chamada ao chokepoint: uma 2ª chamada
    # com outro `now` podia cair do outro lado da fronteira do epoch e imprimir
    # um antes→depois que nunca existiu. Vem de `power / mult`.
    check(f"view/{sk}: o ANTES é derivado por divisão (bate com a base)",
          abs(v["before"] - exp_before) < 1e-9, f"{v['before']} vs {exp_before}")
    check(f"view/{sk}: os números viajam CRUS (o mesmo float das 3 chances)",
          isinstance(v["after"], float))
    check(f"view/{sk}: a linha não vaza chaveta", "{" not in v["line"])
    check(f"view/{sk}: a linha não tem markdown (dual-surface)",
          not re.search(r"[*_`]", v["line"]))
    check(f"view/{sk}: a linha diz o nome e a frase",
          str(CHAT["pt"][SKIES[sk]["name_key"]]) in v["line"]
          and str(CHAT["pt"][SKIES[sk]["phrase_key"]]) in v["line"])

# O sereno é ×1.00 EXATO: um "84% → 84%" seria ruído a fingir mudança.
_v_ser = sky_view("pt", soul=_soul, power=_base, rounds=_rounds,
                  defense_mult=_dm, now=_now_of(_epoch_of("sereno")))
check("view/sereno: antes == depois", _v_ser["before"] == _v_ser["after"])
check("view/sereno: a linha NÃO desenha uma seta de mudança",
      "→" not in _v_ser["line"])
for sk in ("irado", "velado"):
    _v = sky_view("pt", soul=_soul, power=_base * SKIES[sk]["mult"], rounds=_rounds,
                  defense_mult=_dm, now=_now_of(_epoch_of(sk)))
    check(f"view/{sk}: a linha DESENHA o antes→depois (Lei §10)", "→" in _v["line"])
check("view/irado: a chance PIORA",
      sky_view("pt", soul=_soul, power=_base * 1.12, rounds=_rounds, defense_mult=_dm,
               now=_now_of(_epoch_of("irado")))["after"] < _v_ser["after"])
check("view/velado: a chance MELHORA",
      sky_view("pt", soul=_soul, power=_base * 0.88, rounds=_rounds, defense_mult=_dm,
               now=_now_of(_epoch_of("velado")))["after"] > _v_ser["after"])

# Sem alma/poder/rounds (a praça) não há números inventados.
_p = sky_plaza_view("pt", now=_now_of(e0))
check("view/praça: devolve bloco", isinstance(_p, dict))
check("view/praça: NÃO inventa chance", "before" not in _p and "after" not in _p)
check("view/praça: sem markdown", not re.search(r"[*_`]", _p["line"]))
check("view/praça: sem chaveta", "{" not in _p["line"])
check("view/as 3 línguas resolvem",
      all(sky_plaza_view(lg, now=_now_of(e0))["line"] for lg in LANGS))
check("view/as 3 línguas dão frases DIFERENTES (não é fallback mudo)",
      len({sky_plaza_view(lg, now=_now_of(e0))["line"] for lg in LANGS}) == 3)

# ═══════════════════════════════════════════════════════════════════════════
print("[6] O ÚNICO FUTURO ESCRITO — `epoch + 1`, de graça")
# ═══════════════════════════════════════════════════════════════════════════
for sk in _ORDER:
    ep = _epoch_of(sk)
    v = sky_plaza_view("pt", now=_now_of(ep))
    nxt = v["next"]
    check(f"futuro/{sk}: o próximo céu é sky_for(epoch+1)",
          nxt["key"] == sky_for("main", ep + 1))
    check(f"futuro/{sk}: a linha do futuro não vaza chaveta", "{" not in nxt["line"])
    check(f"futuro/{sk}: diz quantas horas faltam", nxt["hours"] >= 1)
# O ramo honesto: a menos de 1h não se diz "~1h" (seria mentira de até 59 min
# numa frase cuja única função é ajudar a decidir se se espera).
# ⚠️ ESTE ASSERT ERA INSTÁVEL (corrigido 2026-08-14). Ele fixava a frase em
# `tsh_next_soon` — mas o pivot de 11/08 acrescentou o ramo "o próximo céu é o
# MESMO", que tem frase própria (`tsh_next_same_soon`) e acontece em ~37,5% dos
# epochs. Como `e0` depende do AGORA, a suite ficava vermelha em pouco mais de
# um terço das execuções, ao acaso da hora a que fosse corrida. O que se trava
# aqui é o CONTRATO — a menos de 1h nenhuma das duas frases promete um número de
# horas — e não qual dos dois ramos calhou.
_soon = sky_plaza_view("pt", now=next_change_at(_now_of(e0)) - timedelta(minutes=20))
check("futuro/<1h: hours é 0 e a frase muda", _soon["next"]["hours"] == 0)
_soon_key = "tsh_next_same_soon" if _soon["next"].get("same") else "tsh_next_soon"
check("futuro/<1h: a frase NÃO promete um número de horas",
      _soon["next"]["line"] == CHAT["pt"][_soon_key].format(
          emoji=_soon["next"]["emoji"], name=_soon["next"]["name"]),
      f"ramo={_soon_key}")
check("futuro/<1h: nenhuma das duas frases leva {hours}",
      "{hours}" not in CHAT["pt"]["tsh_next_soon"]
      and "{hours}" not in CHAT["pt"]["tsh_next_same_soon"])
_far = sky_plaza_view("pt", now=_now_of(e0))
check("futuro/>=1h: usa a frase com horas",
      "{hours}" in CHAT["pt"]["tsh_next_line"]
      and str(_far["next"]["hours"]) in _far["next"]["line"])

# ⚠️ REVIEW ADVERSARIAL — O PRÓXIMO CÉU É O MESMO EM ~37,5% DAS LEITURAS. Os
# epochs são sorteados independentemente, logo repetem: 0,5²+0,25²+0,25² =
# 37,5% (medido 37,4% em 4000 epochs). Dizer "o próximo céu — X — CHEGA em ~6h"
# quando o céu de agora JÁ É X promete uma mudança que não vem — e é na
# frase-bandeira da onda, a que existe para o jogador decidir se espera.
_same_n = sum(1 for i in range(2000)
              if sky_for("main", e0 + i) == sky_for("main", e0 + i + 1))
check("futuro/o próximo céu repete ~37,5% das vezes (não é caso de borda)",
      0.33 <= _same_n / 2000 <= 0.42, f"{_same_n/2000:.1%}")
_e_same_sky = next(e0 + i for i in range(500)
                   if sky_for("main", e0 + i) == sky_for("main", e0 + i + 1))
_e_diff_sky = next(e0 + i for i in range(500)
                   if sky_for("main", e0 + i) != sky_for("main", e0 + i + 1))
_v_same = sky_plaza_view("pt", now=_now_of(_e_same_sky))
_v_diff = sky_plaza_view("pt", now=_now_of(_e_diff_sky))
check("futuro/repetido: o bloco marca `same`", _v_same["next"]["same"] is True)
check("futuro/diferente: o bloco NÃO marca `same`", _v_diff["next"]["same"] is False)
check("futuro/repetido: usa a frase de CONTINUIDADE, não a de chegada",
      _v_same["next"]["line"] == CHAT["pt"]["tsh_next_same"].format(
          emoji=_v_same["next"]["emoji"], name=_v_same["next"]["name"],
          hours=_v_same["next"]["hours"]))
check("futuro/repetido: a frase NÃO promete que algo 'chega'",
      "chega" not in _v_same["next"]["line"])
check("futuro/diferente: essa continua a dizer que chega",
      "chega" in _v_diff["next"]["line"])
_v_same_soon = sky_plaza_view(
    "pt", now=next_change_at(_now_of(_e_same_sky)) - timedelta(minutes=15))
check("futuro/repetido E <1h: tem a sua própria frase",
      _v_same_soon["next"]["line"] == CHAT["pt"]["tsh_next_same_soon"].format(
          emoji=_v_same_soon["next"]["emoji"], name=_v_same_soon["next"]["name"]))
for lg in LANGS:
    for k in ("tsh_next_same", "tsh_next_same_soon"):
        check(f"futuro/{lg}/{k} existe", bool(CHAT[lg].get(k)))

# ⚠️ REVIEW ADVERSARIAL — O CLAMP ENGOLE O CÉU. `estimate_success_chance` limita
# a sobrevivência por round a 0,995 ANTES de a elevar aos rounds, logo acima de
# certa alma o ±12% é integralmente absorvido e o roll fica GENUINAMENTE
# idêntico. Desenhar `94.6% → 94.6%` com "(-12% de severidade)" ao lado é uma
# linha que se contradiz. Reproduz com a alma CALIBRADA de produção (11546, do
# §A da simulação) no reino-alvo 9.
_R9, _SOUL_SAT = 8, 11546
_b9 = float(TRIBULATION_POWER_BY_REALM[_R9])
_r9 = calculate_rounds(_R9)
_v_abs = sky_view("pt", soul=_SOUL_SAT, power=_b9 * 0.88, rounds=_r9,
                  defense_mult=0.05, now=_now_of(_epoch_of("velado")))
check("clamp/o cenário de saturação REPRODUZ (before == after)",
      _v_abs["before"] == _v_abs["after"], f"{_v_abs['before']} vs {_v_abs['after']}")
check("clamp/o bloco marca `absorbed`", _v_abs.get("absorbed") is True)
check("clamp/NÃO desenha uma seta entre dois números iguais",
      "→" not in _v_abs["line"], _v_abs["line"])
check("clamp/…mas continua a DIZER que o céu está lá (Lei §1)",
      str(CHAT["pt"]["tsh_sky_velado"]) in _v_abs["line"]
      and "-12%" in _v_abs["line"])
check("clamp/imprime a chance UMA vez",
      _v_abs["line"].count(f"{_v_abs['after']:g}") >= 1)
# E o caso normal continua a desenhar a seta.
check("clamp/alma normal continua com antes→depois",
      "→" in sky_view("pt", soul=1200, power=_b9 * 0.88, rounds=_r9,
                      defense_mult=0.05, now=_now_of(_epoch_of("velado")))["line"])
for lg in LANGS:
    check(f"clamp/{lg}/tsh_trib_line_absorbed existe",
          bool(CHAT[lg].get("tsh_trib_line_absorbed")))
    check(f"clamp/{lg}: a frase absorvida NÃO tem seta",
          "→" not in str(CHAT[lg]["tsh_trib_line_absorbed"]))

# ⚠️ REVIEW ADVERSARIAL — A PRAÇA ANUNCIAVA O HUMOR E NUNCA O PREÇO. O `pct`
# viajava no payload sem UM leitor (a armadilha do `karma_severity`). O ±12% é
# universal — não depende de alma nem de reino — logo dizê-lo é honesto.
for sk in ("irado", "velado"):
    _pv = sky_plaza_view("pt", now=_now_of(_epoch_of(sk)))
    check(f"praça/{sk}: a linha DIZ o preço", f"{_pv['pct']}%" in _pv["line"], _pv["line"])
_pv_ser = sky_plaza_view("pt", now=_now_of(_epoch_of("sereno")))
check("praça/sereno: NÃO inventa um preço (é ×1.00 exato)",
      "%" not in _pv_ser["line"], _pv_ser["line"])
for lg in LANGS:
    check(f"praça/{lg}/tsh_plaza_line_sev existe", bool(CHAT[lg].get("tsh_plaza_line_sev")))

# ═══════════════════════════════════════════════════════════════════════════
print("[7] A CRÔNICA — só quando VIRA, e uma só vez por epoch")
# ═══════════════════════════════════════════════════════════════════════════
class _FakeResult:
    def __init__(self, val):
        self._v = val

    def scalar_one_or_none(self):
        return self._v


class _RecSession:
    """Sessão de mentira que conta execuções e regista o que foi emitido."""

    def __init__(self, dup=None):
        self.dup, self.executed, self.added = dup, 0, []

    async def execute(self, *a, **k):
        self.executed += 1
        return _FakeResult(self.dup)

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None


# Um epoch em que o céu VIRA (cur != prev) e outro em que NÃO vira.
_e_turn = next(e0 + i for i in range(500)
               if sky_for("main", e0 + i) != sky_for("main", e0 + i - 1))
_e_same = next((e0 + i for i in range(500)
                if sky_for("main", e0 + i) == sky_for("main", e0 + i - 1)), None)
check("crônica/existe um epoch de virada para testar", _e_turn is not None)
check("crônica/existe um epoch SEM virada para testar", _e_same is not None)

_s = _RecSession()
_r = asyncio.run(tsh.pulse_sky(_s, now=_now_of(_e_turn)))
check("crônica/virada: escreve 1 linha", _r and _r.get("changed") == 1, str(_r))
check("crônica/virada: emitiu exatamente uma row", len(_s.added) == 1)
_row = _s.added[0] if _s.added else None
check("crônica/o event_type é o contratado",
      getattr(_row, "event_type", None) == CHRON_EVENT_TYPE)
check("crônica/o text_key é o do céu que entrou",
      getattr(_row, "text_key", None) == SKIES[sky_for("main", _e_turn)]["chron_key"])
check("crônica/o text_key existe nas 3 línguas",
      all(CHAT[lg].get(getattr(_row, "text_key", "")) for lg in LANGS))
check("crônica/o epoch viaja em params (é a chave de deduplicação)",
      (getattr(_row, "params", {}) or {}).get("epoch") == _e_turn)
# ⚠️ continent_key=None de propósito: o céu é GLOBAL. É a ÚNICA notícia do jogo
# que alcança Mòyǔ (fora de TIDE_CONTINENTS e METEOR_CONTINENTS, 0 eventos em
# toda a história) — o filtro do feed é `continent == X OR continent IS NULL`.
check("crônica/a linha é GLOBAL (continent_key None → visível nas 5 praças)",
      getattr(_row, "continent_key", "x") is None)

_s2 = _RecSession()
_r2 = asyncio.run(tsh.pulse_sky(_s2, now=_now_of(_e_same)))
check("crônica/sem virada: NÃO escreve", _r2 and _r2.get("changed") == 0, str(_r2))
check("crônica/sem virada: nem sequer faz a query de duplicados",
      _s2.executed == 0, str(_s2.executed))

# Idempotência: o pulse tem coalesce + misfire_grace e re-agenda a partir do
# BOOT — o mesmo epoch pode ser reavaliado. A 2ª passagem não pode duplicar.
_s3 = _RecSession(dup=1234)
_r3 = asyncio.run(tsh.pulse_sky(_s3, now=_now_of(_e_turn)))
check("crônica/idempotente: com row já gravada não escreve outra",
      _r3 and _r3.get("changed") == 0 and _r3.get("dup") is True, str(_r3))
check("crônica/idempotente: não emitiu row", not _s3.added)

_set_flag(False)
check("crônica/flag OFF: None sem UMA query",
      asyncio.run(tsh.pulse_sky(ExplodingSession(), now=_now_of(_e_turn))) is None)
_set_flag(True)

# ═══════════════════════════════════════════════════════════════════════════
print("[8] WIRING — todo helper tem call site real")
# ═══════════════════════════════════════════════════════════════════════════
_paths = {
    "core/tribulation_engine.py": ["sky_mult"],
    "handlers/tribulation.py": ["sky_view", "tianshi"],
    "core/webserver.py": ["sky_view", "sky_plaza_view", '"tianshi"'],
    "handlers/sect.py": ["sky_plaza_view", "_sky"],
    "core/scheduler.py": ["pulse_sky", "tempo_do_ceu"],
    "database/db.py": ["tempo_do_ceu"],
}
for rel, needles in _paths.items():
    src = _read(rel)
    for n in needles:
        check(f"wire/{rel} usa {n}", n in src)

_ws = _read("core/webserver.py")
_ht = _read("handlers/tribulation.py")
_sect = _read("handlers/sect.py")
_sch = _read("core/scheduler.py")

# As DUAS telas de chat: a preview E a de preparação (é nela que está o TAP —
# o spec só nomeava a primeira, e sem a segunda o número dos botões mudava sem
# ninguém dizer porquê).
check("wire/chat: a linha do céu entra nas DUAS telas da tribulação",
      _ht.count("from core.tianshi_engine import sky_view") == 2,
      str(_ht.count("from core.tianshi_engine import sky_view")))
check("wire/chat: a preview usa rounds_total",
      "rounds=rounds_total" in _ht)
check("wire/chat: a tela do TAP usa os rounds dela",
      "rounds=rounds," in _ht.split("trib_prep_strategy")[1][:900])
check("wire/chat: cada bloco tem try PRÓPRIO (o de fora só loga e apagaria a secção)",
      _ht.count("tianshi block failed") == 2)
# O mini: a key condicional e o render.
check("wire/mini: a key é CONDICIONAL (nunca `null`)",
      'payload["tianshi"] = _sky_blk' in _ws and "if _sky_blk:" in _ws)
check("wire/mini: a praça usa o spread condicional da casa",
      '**({"tianshi": sky_block} if sky_block else {}),' in _ws)
check("wire/mini: o payload da tribulação usa a MESMA alma das 3 chances",
      "soul=soul_int" in _ws)
# A praça do chat: a variável tem de entrar na guarda do espaçador, senão a
# linha em branco antes do quadro de recompensas sai errada.
check("wire/praça-chat: `_sky` entra na guarda do espaçador",
      re.search(r"if rst_local or rep_local or wev_local or wev_rumors or _enc or _crv or _sky:",
                _sect) is not None)
check("wire/praça-chat: try PRÓPRIO (o try partilhado do tiandao cala dois)",
      "praca tianshi view failed" in _sect)
# O 8º sub-passo do pulse.
check("wire/pulse: o passo comita (emit_chronicle só faz flush)",
      "await session.commit()" in _sch.split("from core.tianshi_engine import pulse_sky")[1][:400])
check("wire/pulse: falha nunca derruba o batimento",
      "tianshi pulse failed" in _sch)
check("wire/pulse: é o ÚLTIMO passo (depois das cidades)",
      _sch.index("pulse_sky") > _sch.index("pulse_cities"))

# ═══════════════════════════════════════════════════════════════════════════
print("[9] AS SUPERFÍCIES — por grep (o cliente não tem outra rede)")
# ═══════════════════════════════════════════════════════════════════════════
_tabs = _read("miniapp/components/tabs.js")
# ⚠️ O precedente que obriga esta secção: `karma_severity` é emitida por
# `core/webserver.py:10350` desde a v16.3 e NUNCA foi renderizada em lado
# nenhum — emitir key ≠ mostrar ao jogador. Por isso o assert aqui não é
# "existe um render algures", é o PAR: cada key condicional que este lote
# acrescenta ao payload tem de ter o seu leitor no cliente.
for _srv, _cli in ((r'payload\["tianshi"\]', "trib.tianshi"),
                   (r'"tianshi": sky_block', "d.tianshi")):
    check(f"cli/PAR emitir→mostrar: {_cli}",
          bool(re.search(_srv, _ws)) and _cli in _tabs, _cli)
check("cli/o céu TEM render na preview da tribulação", "trib.tianshi" in _tabs)
check("cli/…e na tela do TAP (a dos 3 botões)",
      _tabs.count("trib.tianshi.line") == 2, str(_tabs.count("trib.tianshi.line")))
check("cli/…e na praça", "d.tianshi" in _tabs)
check("cli/a praça imprime a linha e o futuro",
      "d.tianshi.line" in _tabs and "d.tianshi.next.line" in _tabs)
# Server-resolved: imprimir CRU. Passar por t() criaria uma 2ª fonte da frase
# (e o t() do mini nem sequer tem os placeholders).
check("cli/NUNCA passa a linha por t()",
      not re.search(r't\(\s*["\']tsh_', _tabs))
check("cli/nenhuma key tsh_ foi parar ao mini-app i18n",
      not [k for k in MINI["pt"] if k.startswith("tsh_")])
# O guard é a KEY do payload (o molde da casa), nunca o componente.
for needle in ("{trib.tianshi && (", "{d.tianshi && ("):
    check(f"cli/guard pela key do payload: {needle}", needle in _tabs)
check("cli/o céu NÃO tem botão (é ambiente — §5 do spec)",
      not re.search(r'callback_data=f?["\'](wth_|tsh_|cli_)', _sect + _ht))
check("cli/nenhum prefixo de callback novo no main.py",
      not re.search(r'startswith\("(wth_|tsh_|cli_)"\)', _read("main.py")))

# ═══════════════════════════════════════════════════════════════════════════
print("[10] i18n / PT-BR / a lei dual-surface")
# ═══════════════════════════════════════════════════════════════════════════
check("i18n/paridade ×3 no chat", len({len(v) for v in CHAT.values()}) == 1,
      str([len(v) for v in CHAT.values()]))
check("i18n/paridade ×3 no mini", len({len(v) for v in MINI.values()}) == 1,
      str([len(v) for v in MINI.values()]))
_tsh_keys = [k for k in CHAT["pt"] if k.startswith("tsh_")]
check("i18n/as 19 keys do lote existem", len(_tsh_keys) == 19, str(len(_tsh_keys)))
for lg in LANGS:
    for k in _tsh_keys:
        check(f"i18n/{lg}/{k} existe", bool(CHAT[lg].get(k)))
        # ⚠️ A invariante dual-surface: a MESMA string é impressa pelo chat com
        # parse_mode="Markdown" (tribulação), pelo chat SEM parse_mode (praça)
        # e pelo mini-app em React puro. Um `*` sai literal em duas das três.
        check(f"i18n/{lg}/{k}: ZERO markdown",
              not re.search(r"[*_`\[\]]", str(CHAT[lg][k])), str(CHAT[lg][k])[:50])
_TU = re.compile(r"\b(tu|teu|tua|teus|tuas|vosso|vossa|contigo)\b", re.IGNORECASE)
for k in _tsh_keys:
    _m = _TU.search(str(CHAT["pt"][k]))
    check(f"i18n/pt/{k}: PT-BR (sem tuteamento)", not _m, _m.group(0) if _m else "")
for k in ("feature_tempo_do_ceu", "feature_tempo_do_ceu_desc"):
    for lg in LANGS:
        check(f"i18n/mini/{lg}/{k}: a 28ª flag tem rótulo no painel",
              bool(MINI[lg].get(k)))
check("i18n/zero keys notif_ nesta onda",
      not [k for k in _tsh_keys if k.startswith("notif_")])

# ═══════════════════════════════════════════════════════════════════════════
print("[11] ZERO migration — o céu é DERIVADO")
# ═══════════════════════════════════════════════════════════════════════════
_migs = sorted(os.listdir(os.path.join(ROOT, "migrations")))
# PIVOT 2026-08-11: a 139 e da Fase A3 do Motor, nao do MV-11.
# ⚠️ 2026-09-07 — esta guarda dizia "nenhuma migration 140+ nasceu", e isso
# NAO e' o que ela quer provar: quer provar que ESTA onda nao criou migration.
# Escrita como um tecto global, ela fica vermelha sempre que QUALQUER onda
# futura acrescentar uma (foi o que a Mig 140 do genero fez a SETE suites de
# uma vez). O invariante durável e' o do ASSUNTO: nenhuma migration do repo
# fala desta onda — isso continua verdade daqui a cem migrations.
_cita = [m for m in _migs if m.endswith(".sql")
         and any(a in (m + _read(f"migrations/{m}")).lower()
                 for a in ("tianshi", "tempo_do_ceu", "heaven_time"))]
check("mig/o MV-11 nao criou migration (nenhuma cita o Tempo do Ceu)",
      not _cita, str(_cita))
for m in _migs:
    if m.endswith(".sql"):
        _sql = _read(f"migrations/{m}").lower()
        check(f"mig/{m} não fala de tianshi/tempo_do_ceu",
              "tianshi" not in _sql and "tempo_do_ceu" not in _sql)
_eng = _read("core/tianshi_engine.py")
check("mig/o engine não define UMA tabela", "Table(" not in _eng and "Column(" not in _eng)
check("mig/o engine só LÊ a Crônica (a escrita é do emit_chronicle)",
      "session.add(" not in _eng and "select(WorldChronicle.id)" in _eng)
check("mig/o céu não toca world_events (bloquearia Marés e Meteoros)",
      "world_events" not in _eng and "WorldEvent" not in _eng)
# ⚠️ `region_states` é CITADO no docstring (a medição que girou o eixo: 0 rows
# em `main`). O que não pode existir é código — import ou query.
_eng_code = "\n".join(l for l in _eng.splitlines()
                      if not l.lstrip().startswith(("#", "·", "*")))
check("mig/o céu não é um 6º estado regional (zero import/query)",
      "region_state_engine" not in _eng and "RegionState" not in _eng_code)
check("mig/o céu não toca qi_tick_mult (morderia meridianos e têmpera)",
      "qi_tick_mult" not in _eng)
check("mig/o céu não toca cultivator_soul (o mandato eterno)",
      "cultivator_soul" not in _eng)

# restaurar os originais ANTES de sair (o teste não deixa rasto)
tsh._flag = _ORIG_FLAG
tsh.sky_for = _ORIG_SKY_FOR

print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)
print(f"OK — {PASS} asserts. O céu tem temperamento, morde num só lugar, "
      "e diz o que vem a seguir antes de você tocar no botão.")
