# -*- coding: utf-8 -*-
"""Lote do [jogador] (17-18/08/2026) — 火候 Ponto do Fogo + Identidade que transbordava.

Roda: python -X utf8 scripts/_test_relatos_0818_chama.py

O que este teste protege, por ordem de gravidade:

  1. **NÃO-REGRESSÃO É O CONTRATO.** Tier 1 (ou tier ausente/inválido) tem de
     devolver EXACTAMENTE o jogo de ontem: tecto 100, 1pt/3min. 46 jogadores
     no main estão em tier 1; se este assert cair, mudei o jogo deles.
  2. **O eixo pago nunca é desvalorizado.** Para todo o VIP 0..5, o tecto e o
     ritmo com posto têm de ser melhores ou iguais aos do mesmo VIP sem posto,
     e o VIP mais alto continua estritamente à frente no mesmo posto. Lei §4.
  3. **TODA espera encurta.** O tecto sobe (240 no Celestial), o que faria a
     "barra cheia" demorar mais — a métrica honesta é o tempo até UMA síntese.
  4. **O ritmo formatado nunca regride para "3.0".** O `{regen}` das 3 línguas
     recebia int; agora recebe float.
  5. **Nenhum call site ficou para trás.** Uma tela sem o tier diz 100 enquanto
     a do lado diz 240 — mentira de display. 12 sites.
  6. **O varredor de notificações não avisa cedo** (e não grava o carimbo de
     dedup em falso, o que mataria o aviso verdadeiro para sempre).
  7. **O renascimento devolve a chama** (o report do [jogador]), no tecto do POSTO.
  8. **A Identidade encolhe.** `1fr` = `minmax(auto,1fr)`: sem minWidth:0 o
     ellipsis nunca dispara e a coluna estica. 3ª recorrência do defeito.
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import types
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Padrão _test_relatos_0814: o motor de alquimia re-exporta core.utils, que importa
# `telegram`. Stub mínimo — este teste não toca em rede nem em handlers.
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

from config import (
    ALCHEMY_ENERGY_BASE, ALCHEMY_ENERGY_REGEN_MINUTES, ALCHEMY_ENERGY_COSTS,
)
from core.alchemy_engine import (
    get_alchemy_energy, consume_alchemy_energy, get_flame_mastery,
    format_regen_minutes, MAX_ALCHEMY_TIER,
)

OK = 0
FAIL = []


def chk(cond, label):
    global OK
    if cond:
        OK += 1
    else:
        FAIL.append(label)
        print("  x " + label)


class FakePlayer:
    """Só os campos que a energia lê."""

    def __init__(self, energy=None, cap=None, updated=None):
        self.alchemy_energy = energy
        self.alchemy_energy_max = cap
        self.alchemy_energy_updated_at = updated


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rd(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


print("\n=== 1. NAO-REGRESSAO — tier 1 e o jogo de ontem ===")
p = FakePlayer()
cur, mx, rg = get_alchemy_energy(p, 0, 1)
chk(mx == ALCHEMY_ENERGY_BASE == 100, "tier1 vip0 tecto == 100 (veio %s)" % mx)
chk(abs(rg - ALCHEMY_ENERGY_REGEN_MINUTES) < 1e-9, "tier1 vip0 ritmo == 3 (veio %s)" % rg)
for bad in (None, 0, -3, 99):
    try:
        _, mx_b, _ = get_alchemy_energy(p, 0, bad)
        chk(mx_b in (100, 240), "tier invalido %r nao explode (tecto %s)" % (bad, mx_b))
    except Exception as exc:
        chk(False, "tier invalido %r levantou %s" % (bad, exc))
chk(get_flame_mastery(1) == (0, 1.0), "get_flame_mastery(1) == (0, 1.0) — identidade")
chk(get_flame_mastery(0) == (0, 1.0), "tier 0 clampa para 1")
chk(get_flame_mastery(99) == get_flame_mastery(MAX_ALCHEMY_TIER), "tier acima da escala clampa no TOPO")

print("\n=== 2. O eixo pago nunca e desvalorizado (Lei 4) ===")
for vip in range(0, 6):
    _, mx_t1, rg_t1 = get_alchemy_energy(p, vip, 1)
    for tier in range(1, MAX_ALCHEMY_TIER + 1):
        _, mx_t, rg_t = get_alchemy_energy(p, vip, tier)
        chk(mx_t >= mx_t1, "vip%d tier%d: tecto >= tier1 (%s >= %s)" % (vip, tier, mx_t, mx_t1))
        chk(rg_t <= rg_t1 + 1e-9, "vip%d tier%d: ritmo <= tier1 (%.3f <= %.3f)" % (vip, tier, rg_t, rg_t1))
for tier in range(1, MAX_ALCHEMY_TIER + 1):
    for vip in range(0, 5):
        _, mx_lo, rg_lo = get_alchemy_energy(p, vip, tier)
        _, mx_hi, rg_hi = get_alchemy_energy(p, vip + 1, tier)
        chk(mx_hi > mx_lo, "tier%d: VIP%d tem tecto > VIP%d" % (tier, vip + 1, vip))
        chk(rg_hi < rg_lo, "tier%d: VIP%d regenera mais rapido que VIP%d" % (tier, vip + 1, vip))

print("\n=== 3. TODA espera encurta (tempo ate UMA sintese T5) ===")
cost_t5 = ALCHEMY_ENERGY_COSTS[5]
_, _, rg_base = get_alchemy_energy(p, 0, 1)
base_wait = cost_t5 * rg_base
prev = base_wait
for tier in range(1, MAX_ALCHEMY_TIER + 1):
    _, mx_t, rg_t = get_alchemy_energy(p, 0, tier)
    wait = cost_t5 * rg_t
    chk(wait <= prev + 1e-9, "tier%d: espera por 1 craft T5 nao aumenta (%.0fmin)" % (tier, wait))
    prev = wait
    if tier == MAX_ALCHEMY_TIER:
        print("     Celestial F2P: tecto %s, %.1f energia/h, 1 craft T5 em %.0fmin (era %.0fmin)"
              % (mx_t, 60 / rg_t, wait, base_wait))
chk(prev < base_wait, "Celestial espera ESTRITAMENTE menos (%.0f < %.0f)" % (prev, base_wait))

print("\n=== 4. O ritmo formatado nunca regride ===")
chk(format_regen_minutes(3.0) == "3", "3.0 -> 3 (veio %s)" % format_regen_minutes(3.0))
chk(format_regen_minutes(2.5) == "2.5", "2.5 -> 2.5")
chk(format_regen_minutes(2.04) == "2.04", "2.04 -> 2.04")
chk(format_regen_minutes(3.0 * 0.68) == "2.04", "3.0x0.68 -> 2.04 (sem cauda binaria)")
chk("0000" not in format_regen_minutes(0.5 * 0.68), "VIP5 Celestial sem cauda binaria")

print("\n=== 5. Nenhum call site ficou para tras ===")
# -- '*.py' restringe ao CODIGO: sem isto o Cerebro/*.md (documentacao que cita
# a assinatura antiga) entra na lista e da um vermelho falso.
# 開 Lido do disco, não com `git grep`: a cópia comunitária corre também fora
# de um repositório (um zip, um fork antes do primeiro commit), e aí o git
# devolvia ZERO linhas em silêncio. O formato é o mesmo: `ficheiro:linha:texto`.
def _grep_py(padrao):
    rx, out = re.compile(padrao), []
    for d, subs, nomes in os.walk(ROOT):
        subs[:] = [s for s in subs if s not in (".git", "node_modules", "__pycache__", "dist", ".venv", "venv")]
        for n in nomes:
            if n.endswith(".py"):
                p = os.path.join(d, n)
                rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
                for i, l in enumerate(io.open(p, encoding="utf-8", errors="replace"), 1):
                    if rx.search(l):
                        out.append("%s:%d:%s" % (rel, i, l.rstrip()))
    return out

sites = _grep_py(r"(get|consume)_alchemy_energy\(")
calls = [l for l in sites if "def " not in l and "import" not in l
         and not l.startswith("scripts/_test_") and ".pyc" not in l]
chk(len(calls) >= 12, "encontrados %d call sites (esperado >= 12)" % len(calls))
orphans = [l for l in calls if not re.search(r"(skill\.tier|a_tier|tiers\.get|_a_tier|alchemy_tier)", l)]
chk(not orphans, "nenhum call site sem tier — orfaos: %s" % orphans)

print("\n=== 6. O varredor de notificacoes leva o tier ===")
notif = rd("core/notifications_engine.py")
chk("get_alchemy_tiers_bulk" in notif, "notificador usa a busca EM LOTE (1 query, nao N)")
chk("tiers.get(int(player.telegram_id), 1)" in notif, "notificador passa o tier de cada jogador")
chk(notif.index("get_alchemy_tiers_bulk(session") < notif.index("for player in rows:"),
    "o lote e buscado ANTES do laco (senao volta a ser N queries)")

print("\n=== 7. O renascimento devolve a chama, no tecto do POSTO ===")
prest = rd("core/prestige_engine.py")
chk("player.alchemy_energy = _energy_cap" in prest, "renascer repoe a energia")
chk("player.alchemy_energy_updated_at = datetime.now(timezone.utc)" in prest,
    "renascer carimba o relogio (senao regenera a partir do passado)")
chk("get_alchemy_tier(session, player.telegram_id)" in prest, "usa o tier REAL, nao o do Aprendiz")
chk(prest.index("_energy_cap, _ = get_alchemy_energy") < prest.index("player.alchemy_energy = _energy_cap"),
    "cap calculado antes de atribuido")

print("\n=== 8. A Identidade encolhe (o overflow do [jogador]) ===")
tabs = rd("miniapp/components/tabs.js")
chk('gridTemplateColumns:"minmax(0,1fr) minmax(0,1fr)", gap:7' in tabs,
    "grelha 2x2 da Identidade usa minmax(0,1fr) — colunas encolhiveis")
i_card = tabs.index("const _identityCard = (icon, labelKey, value")
card_src = tabs[i_card:i_card + 2600]
chk("minWidth:0," in card_src, "o botao-cartao tem minWidth:0 (item de grid)")
chk('display:"flex", alignItems:"center", gap:7, minWidth:0' in card_src, "a linha do icone+etiqueta tem minWidth:0")
chk("flex:1, minWidth:0," in card_src, "a etiqueta com flex:1 tem minWidth:0")
chk(card_src.count('textOverflow:"ellipsis"') >= 2, "etiqueta e valor mantem o ellipsis")
chk('gridTemplateColumns:"1fr 1fr", gap:7' not in tabs, "nao sobrou a grelha antiga de gap:7")

print("\n=== 9. Disclosure nas DUAS superficies (Lei dual-surface) ===")
alch = rd("handlers/alchemy.py")
chk("alch_flame_mastery" in alch, "chat mostra o Ponto do Fogo")
chk("alch_flame_mastery_next" in alch, "chat mostra o degrau SEGUINTE a quem ainda nao tem")
chk("if flame_line:" in alch, "tier 1 nao ve um +0 celebrado")
chk("format_regen_minutes(regen_minutes)" in alch, "chat formata o ritmo")
chk("_, _, regen_minutes = get_alchemy_energy(player, vip_lvl, skill.tier)" in alch,
    "a RECUSA por falta de energia diz o ritmo real (era a tabela do VIP crua)")
chk('"flame": _flame_payload' in rd("core/webserver.py"), "mini-app recebe o payload da chama")
chk("en.flame.max_bonus > 0" in tabs, "mini-app mostra o bonus ganho")
chk("en.flame.next.tier_name" in tabs, "mini-app mostra o degrau seguinte")
chk("Math.round((en.regen_minutes || 0) * 100) / 100" in tabs, "mini-app arredonda o ritmo")

print("\n=== 10. i18n — paridade e PT-BR ===")
chat = {l: json.loads(rd("locales/%s.json" % l)) for l in ("pt", "en", "es")}
mini = {l: json.loads(rd("miniapp/i18n/%s.json" % l)) for l in ("pt", "en", "es")}
chk(len({len(v) for v in chat.values()}) == 1,
    "chat em paridade: %s" % {k: len(v) for k, v in chat.items()})
chk(len({len(v) for v in mini.values()}) == 1,
    "mini-app em paridade: %s" % {k: len(v) for k, v in mini.items()})
for src, name in ((chat, "chat"), (mini, "mini")):
    for k in ("alch_flame_mastery", "alch_flame_mastery_next"):
        chk(all(k in src[l] for l in ("pt", "en", "es")), "%s: %s nas 3 linguas" % (name, k))
        ph = [set(re.findall(r"\{(\w+)\}", src[l][k])) for l in ("pt", "en", "es")]
        chk(ph[0] == ph[1] == ph[2], "%s: %s com os MESMOS placeholders (%s)" % (name, k, ph))
EUPT = ("tecto", "facto", "optim", "accao", "objectiv", "directo", "efectiv", "contacto")
for src, name in ((chat, "chat"), (mini, "mini")):
    for k in ("alch_flame_mastery", "alch_flame_mastery_next"):
        low = src["pt"][k].lower()
        bad = [w for w in EUPT if w in low]
        chk(not bad, "%s: %s em PT-BR, sem grafia europeia %s" % (name, k, bad))

print("\n=== 11. Consumo continua honesto ===")
p2 = FakePlayer(energy=100, cap=100, updated=datetime.now(timezone.utc))
ok, new_e, mx2 = consume_alchemy_energy(p2, 50, 0, 5)
chk(ok and new_e == 50 and mx2 == 240, "Celestial com 100 gasta 50 -> 50 (veio ok=%s %s/%s)" % (ok, new_e, mx2))
p3 = FakePlayer(energy=10, cap=100, updated=datetime.now(timezone.utc))
ok3, cur3, _ = consume_alchemy_energy(p3, 50, 0, 5)
chk(not ok3 and p3.alchemy_energy == 10, "sem energia: recusa e NAO debita")
p4 = FakePlayer(energy=0, cap=100, updated=datetime.now(timezone.utc) - timedelta(minutes=60))
c4t1, _, _ = get_alchemy_energy(p4, 0, 1)
c4t5, _, _ = get_alchemy_energy(p4, 0, 5)
chk(c4t5 > c4t1, "1h parado: Celestial recuperou mais que Aprendiz (%s > %s)" % (c4t5, c4t1))
chk(c4t1 == 20, "Aprendiz recupera 20/h exactamente como ontem (veio %s)" % c4t1)

print("\n" + "=" * 62)
print("  %d asserts verdes, %d vermelhos" % (OK, len(FAIL)))
if FAIL:
    print("\n  VERMELHOS:")
    for f in FAIL:
        print("   x " + f)
print("=" * 62)
sys.exit(1 if FAIL else 0)
