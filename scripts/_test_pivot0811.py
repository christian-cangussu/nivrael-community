# -*- coding: utf-8 -*-
"""PIVOT 2026-08-11 — suite COMMITTED.

    python -X utf8 scripts/_test_pivot0811.py

Cobre, por secção:
  1. Bug [jogador] #1 — 内功: as artes internas/de meditação ganham Compreensão
  2. Bug [jogador] #2 — a quest da Spirit Mine aponta para a masmorra CERTA
  3. Bug [jogador] #3 — a resistência a pílulas limpa em TODO realm-up
  4. ROUTING — o mundo de nascimento, e a regra de ferro dos 240 do `main`
  5. FASE A do motor — A1/A2/A3/A4, e a OFF-identity da camada nova
  6. i18n / PT-BR / dual-surface
  7. Nada de descartável: migrations, seeds, wiring por grep
"""
from __future__ import annotations

import io
import json
import os
import random
import re
import sys
import types
from types import SimpleNamespace

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


LANGS = ("pt", "en", "es")
CHAT = {lg: json.loads(_read(f"locales/{lg}.json")) for lg in LANGS}
MINI = {lg: json.loads(_read(f"miniapp/i18n/{lg}.json")) for lg in LANGS}

import asyncio  # noqa: E402

import core.technique_engine as tec  # noqa: E402
import core.world_pulse_engine as wp  # noqa: E402

# ═══════════════════════════════════════════════════════════════════════════
print("\n[1] BUG [jogador] #1 — 内功: as artes internas ganham Compreensão")
# ═══════════════════════════════════════════════════════════════════════════
check("1/os dois tipos passivos são os do catálogo",
      set(tec.PASSIVE_TECH_TYPES) == {"meditation", "interior"})
check("1/uma meditação leve (30min) vale XP", tec.passive_mastery_xp_for(30) > 0)
check("1/o vazio (120min) vale mais que a leve (30min)",
      tec.passive_mastery_xp_for(120) > tec.passive_mastery_xp_for(30))
check("1/zero minutos não paga nada (anti-farm)", tec.passive_mastery_xp_for(0) == 0)
check("1/negativo não paga", tec.passive_mastery_xp_for(-99) == 0)
# ⚠️ QUEM FINALIZA CREDITA — a regra de ferro. São QUATRO os finalizadores de
# meditação, e o fix de 2026-07-21 já se pagou uma vez por esquecer UM deles.
_finalizers = {
    "core/game_logic.py": 2,      # process_tick + credit_meditation_if_earned
    "core/scheduler.py": 1,       # meditation_sweep
    "core/webserver.py": 1,       # o poll do mini-app
}
for rel, n in _finalizers.items():
    src = _read(rel)
    # ⚠️ contar a CHAMADA, nunca o nome: cada site tem o import function-local
    # E o await, logo um `count()` cru dá sempre o dobro.
    check(f"1/{rel} credita a Compreensão ({n}×)",
          src.count("await credit_passive_mastery(") == n,
          str(src.count("await credit_passive_mastery(")))
check("1/o crédito corre num SAVEPOINT (o flush não pode envenenar o tick)",
      "begin_nested" in _read("core/technique_engine.py"))
check("1/a notificação é key NOVA (nunca placeholder em key antiga)",
      "notif_neigong_up" in _read("core/technique_engine.py"))
# A DISCLOSURE — a metade da Lei §1 que faltava.
check("1/a frase de ganho existe para os dois casos",
      tec.technique_gain_key("interior") == "tech_gain_passive"
      and tec.technique_gain_key("meditation") == "tech_gain_passive"
      and tec.technique_gain_key("combat") == "tech_gain_combat")
check("1/tipo desconhecido degrada para a frase de combate",
      tec.technique_gain_key(None) == "tech_gain_combat")
check("1/o chat imprime a frase", "technique_gain_key" in _read("handlers/combat.py"))
check("1/o mini recebe a frase server-resolved", '"gain_hint"' in _read("core/webserver.py"))
check("1/…e o mini RENDERIZA (emitir key ≠ mostrar ao jogador)",
      "tech.gain_hint" in _read("miniapp/components/tabs.js"))

# ═══════════════════════════════════════════════════════════════════════════
print("[2] BUG [jogador] #2 — a quest aponta para a Spirit Mine (id 9), não a 2")
# ═══════════════════════════════════════════════════════════════════════════
_fs = _read("database/seeds/faction_seeds.py")
_blk_raw = _fs.split('"name": "Complete Spirit Mine (Hard)"')[1].split("},")[0]
# ⚠️ sem os comentários: o comentário do fix CITA o "dungeon_id 2" antigo,
# e um grep cru daria falso positivo no assert de ausência.
_blk = chr(10).join(l for l in _blk_raw.splitlines() if not l.strip().startswith("#"))
check("2/o alvo é a masmorra 9", '"dungeon_id": 9' in _blk, _blk[:120])
check("2/…e já não é a 2 (Haunted Mines)", '"dungeon_id": 2' not in _blk)
_ds = _read("database/seeds/dungeon_seeds.py")
check("2/a 9 chama-se mesmo Spirit Mine",
      re.search(r'"id":\s*9,[^}]*"name":\s*"Spirit Mine"', _ds, re.S) is not None)
check("2/o seed runner reescreve rows existentes (propaga sem migration)",
      "for k, v in q.items()" in _fs and "setattr(row, k, v)" in _fs)

# ═══════════════════════════════════════════════════════════════════════════
print("[3] BUG [jogador] #3 — a resistência a pílulas limpa em TODO realm-up")
# ═══════════════════════════════════════════════════════════════════════════
# O contrato está escrito na própria docstring do engine ("uses this realm"),
# mas o único reset vivia no ramo de breakthrough simples — inalcançável a
# partir do reino 4, que rompe SEMPRE por tribulação.
_ra = "reset_medicine_resistance"
_sites = {
    "handlers/tribulation.py": 1,   # _grant_realm_advancement (chat)
    "handlers/cultivation.py": 2,   # fundação + núcleo (chat)
    "core/webserver.py": 4,         # trib auto-grant + trib phased + fundação + núcleo
    "core/game_logic.py": 1,        # o ramo simples, que já existia
}
for rel, n in _sites.items():
    src = _read(rel)
    check(f"3/{rel} limpa a resistência ({n}×)",
          src.count(f"await {_ra}(") == n, str(src.count(f"await {_ra}(")))
check("3/o helper continua a ser DELETE-only (zero migration)",
      "delete(" in _read("core/alchemy_engine.py").split("async def reset_medicine_resistance")[1][:400].lower())

# ═══════════════════════════════════════════════════════════════════════════
print("[4] ROUTING — onde nasce um jogador novo")
# ═══════════════════════════════════════════════════════════════════════════
import database.db as db  # noqa: E402

_orig_registry = dict(db._world_registry)
try:
    db._world_registry.clear()
    db._ensure_main_registered()
    check("4/sem mundo marcado, nasce-se em main", db.signup_world_key() == "main")
    db._world_registry["s2"] = {"key": "s2", "status": "active", "is_default": True}
    check("4/um secundário marcado GANHA do main (o desempate)",
          db.signup_world_key() == "s2")
    db._world_registry["s2"]["status"] = "maintenance"
    check("4/um mundo em manutenção NÃO recebe recém-chegados",
          db.signup_world_key() == "main")
    db._world_registry["s2"]["status"] = "active"
    os.environ["SIGNUP_WORLD"] = "main"
    check("4/a válvula de ops (SIGNUP_WORLD) manda", db.signup_world_key() == "main")
    os.environ["SIGNUP_WORLD"] = "nao_existe"
    check("4/um SIGNUP_WORLD inválido degrada para main (fail-safe)",
          db.signup_world_key() == "main")
    os.environ.pop("SIGNUP_WORLD", None)
finally:
    db._world_registry.clear()
    db._world_registry.update(_orig_registry)

_cdb = _read("database/control_db.py")
check("4/quem não tem row cai no mundo de NASCIMENTO, não em main",
      "return key or signup_world_key()" in _cdb)
check("4/…e o backfill dos 240 está DECLARADO como pré-condição",
      "db_write_s2_abertura" in _cdb)
check("4/existe escritor do mundo ativo", "async def set_active_world" in _cdb)
check("4/o cache do chat é invalidado no switch",
      "invalidate_world_cache" in _cdb)
check("4/o bootstrap deixou de forçar is_default em main (senão o deploy desfazia)",
      "is_default           = true," not in _cdb.split("_BOOTSTRAP_MAIN_ROW")[1][:900])
_main = _read("main.py")
check("4/o chat liga-se ao mundo do jogador", "_bind_player_world" in _main)
check("4/…num grupo ANTES do jogo", "group=-99" in _main)
check("4/…e só em DM (o grupo é sempre main)", 'chat.type != "private"' in _main)
check("4/…e NUNCA escreve o contextvar quando o mundo é main (os 240 intactos)",
      "if key and key != MAIN_WORLD_KEY:" in _main)
_st = _read("handlers/start.py")
check("4/o /start cria no mundo de nascimento", "signup_world_key()" in _st)
check("4/…e só fixa a row DEPOIS do commit",
      _st.index("await session.commit()") < _st.index("set_active_world"))
check("4/o mini-app fixa a row ao criar o personagem",
      "set_active_world" in _read("core/webserver.py"))

# ═══════════════════════════════════════════════════════════════════════════
print("[5] FASE A do motor — e a OFF-identity da camada nova")
# ═══════════════════════════════════════════════════════════════════════════
_soul = {t: 0.5 for t in wp.SECT_SOUL_SCALARS}
_soul["_has_rival"] = True
_r1 = wp.score_actions(dict(_soul), random.Random("x"))
_r2 = wp.score_actions(dict(_soul), random.Random("x"), None)
_r3 = wp.score_actions(dict(_soul), random.Random("x"), {})
check("5/A1: ctx None e ctx {} são o MESMO de antes da onda (aditivo)",
      _r1 == _r2 == _r3)
_ctx_weak = {"strength": 10, "world_strength": 100, "momentum": 0, "recent_losses": 0}
_ctx_strong = {"strength": 300, "world_strength": 100, "momentum": 5, "recent_losses": 0}
check("5/A1: quem está fraco fortifica mais",
      wp._ctx_bias("fortify", _ctx_weak) > wp._ctx_bias("fortify", _ctx_strong))
check("5/A1: quem está fraco saqueia menos",
      wp._ctx_bias("raid_rival", _ctx_weak) < wp._ctx_bias("raid_rival", _ctx_strong))
# ⚠️ A lição mais cara: a régua é RELATIVA. Sem `world_strength` o contexto não
# opina sobre força — melhor mudo do que errado, porque `strength` não tem teto.
check("5/A1: sem a régua do mundo, a força NÃO opina",
      wp._ctx_bias("fortify", {"strength": 1, "momentum": 0}) == 0.0)
check("5/A1: a mesma força é FRACA num mundo rico e FORTE num mundo pobre",
      wp._ctx_bias("fortify", {"strength": 100, "world_strength": 400})
      > wp._ctx_bias("fortify", {"strength": 100, "world_strength": 40}))
# ⚠️ A separação NO TEMPO — sem ela o mundo vira nove clones a fazer a mesma briga.
_old_debt = {"strength": 100, "world_strength": 100, "grudge_max": 90, "recent_losses": 0}
_fresh_pain = {"strength": 100, "world_strength": 100, "grudge_max": 90, "recent_losses": 2}
check("5/A3: dívida ANTIGA faz sair de casa",
      wp._ctx_bias("raid_rival", _old_debt) > 0)
check("5/A3: com pancada RECENTE, o portão fecha em vez de revidar",
      wp._ctx_bias("fortify", _fresh_pain) > wp._ctx_bias("raid_rival", _fresh_pain))
_row = SimpleNamespace(id="a", grudges={})
_row.grudges = wp.bump_grudge(_row, "b")
check("5/A3: o rancor acumula", _row.grudges.get("b") == wp.GRUDGE_ON_RAID)
_row.grudges = wp.bump_grudge(_row, "b", 999)
check("5/A3: …com teto", _row.grudges["b"] == wp.GRUDGE_MAX)
_row.grudges = wp.decay_grudges(_row)
check("5/A3: …e decai (ódio eterno é tão morto quanto ódio nenhum)",
      _row.grudges["b"] == wp.GRUDGE_MAX - wp.GRUDGE_DECAY)
check("5/A3: um rancor pequeno NÃO destrona o rival semeado",
      wp.grudge_target(SimpleNamespace(id="a", grudges={"b": 5}), {"b"}) is None)
check("5/A3: um rancor grande destrona",
      wp.grudge_target(SimpleNamespace(id="a", grudges={"b": 99}), {"b"}) == "b")
check("5/A3: a vingança exige DOIS saques, nunca um azar",
      wp.GRUDGE_TARGET_MIN > wp.GRUDGE_ON_RAID)
check("5/A3: nunca se odeia a si próprio",
      wp.grudge_target(SimpleNamespace(id="a", grudges={"a": 99}), {"a"}) is None)
check("5/A3: leitura fail-safe de lixo", wp.read_grudges(SimpleNamespace(grudges="nao é dict")) == {})
# A2
import core.tiandao_engine as td  # noqa: E402
check("5/A2: a sitiada pesa mais que a próspera",
      td.EVENT_STATE_WEIGHTS["sitiada"] > td.EVENT_STATE_WEIGHTS["prospera"])
check("5/A2: o festival pesa menos", td.EVENT_STATE_WEIGHTS["festival"] < 1.0)
check("5/A2: a próspera é EXATAMENTE 1.0 (⇒ neutro com a flag OFF)",
      td.EVENT_STATE_WEIGHTS["prospera"] == 1.0)
_conts = ("linghe", "qianhe", "yanshan")
_uniform = {c: "prospera" for c in _conts}
_picks = [td._weighted_continent(_conts, _uniform) for _ in range(3000)]
check("5/A2: com tudo próspero a distribuição é ~uniforme",
      all(900 < _picks.count(c) < 1100 for c in _conts),
      str({c: _picks.count(c) for c in _conts}))
_picks2 = [td._weighted_continent(_conts, dict(_uniform, qianhe="sitiada")) for _ in range(3000)]
check("5/A2: a sitiada atrai mais desgraça",
      _picks2.count("qianhe") > _picks2.count("linghe") * 1.8)
check("5/A2: fail-safe com estados de lixo",
      td._weighted_continent(_conts, {"qianhe": None}) in _conts)
# A4
_jh = _read("core/jianghu_engine.py")
check("5/A4: a vendeta lê o desafeto guardado", "jh_wronged" in _jh)
check("5/A4: o perdedor guarda quem lhe fez isto", 'if steps[npc_id] < 0:' in _jh)
check("5/A4: JSON-safe (isoformat, nunca datetime cru)",
      "now.isoformat()" in _jh.split("jh_wronged")[2][:400])
check("5/A4: o chron_params continua exatamente {npc, other}",
      '"chron_params": {"npc": winner.name, "other": loser.name}' in _jh)
# Migration
_mig = "139_house_grudges.sql"
check("5/a Mig 139 existe", os.path.exists(os.path.join(ROOT, "migrations", _mig)))
_msql = _read(f"migrations/{_mig}")
check("5/…é ADD COLUMN IF NOT EXISTS com default (backwards compatible)",
      "ADD COLUMN IF NOT EXISTS" in _msql and "DEFAULT '{}'" in _msql)
check("5/…e NUNCA um DROP", "DROP" not in _msql.upper())
check("5/o seed NÃO toca em grudges (senão o deploy zerava a memória)",
      "grudges" not in _read("database/seeds/world_sects_seeds.py"))

# ═══════════════════════════════════════════════════════════════════════════
print("[6] i18n / PT-BR / dual-surface")
# ═══════════════════════════════════════════════════════════════════════════
check("6/paridade ×3 no chat", len({len(v) for v in CHAT.values()}) == 1,
      str([len(v) for v in CHAT.values()]))
check("6/paridade ×3 no mini", len({len(v) for v in MINI.values()}) == 1)
_new = ("tech_gain_combat", "tech_gain_passive",
        "notif_neigong_up_title", "notif_neigong_up_body")
for lg in LANGS:
    for k in _new:
        check(f"6/{lg}/{k} existe", bool(CHAT[lg].get(k)))
        # ⚠️ DUAL-SURFACE: a frase de ganho é impressa pelo chat (Markdown) E
        # pelo mini-app (React puro). Um `*` sai literal numa das duas.
        check(f"6/{lg}/{k}: zero markdown",
              not re.search(r"[*_`\[\]]", str(CHAT[lg][k])), str(CHAT[lg][k])[:40])
_TU = re.compile(r"\b(tu|teu|tua|teus|tuas|vosso|vossa|contigo)\b", re.IGNORECASE)
for k in _new:
    _m = _TU.search(str(CHAT["pt"][k]))
    check(f"6/pt/{k}: PT-BR (sem tuteamento)", not _m, _m.group(0) if _m else "")
check("6/as keys novas NÃO foram parar ao mini (lei de colocação)",
      not [k for k in _new if k in MINI["pt"]])
# A notificação nova tem de trazer o payload dela desde a 1ª row.
_te = _read("core/technique_engine.py")
for tok in ("emoji", "name", "before", "after"):
    check(f"6/o payload da notif traz {{{tok}}}",
          f'"{tok}"' in _te.split("body_key=\"notif_neigong_up_body\"")[1][:500])

# ═══════════════════════════════════════════════════════════════════════════
print("[7] ZERO lixo — migrations, seeds, wiring")
# ═══════════════════════════════════════════════════════════════════════════
_migs = sorted(m for m in os.listdir(os.path.join(ROOT, "migrations")) if m.endswith(".sql"))
# ⚠️ 2026-09-07 — esta guarda dizia "nenhuma migration 140+ nasceu", e isso
# NAO e' o que ela quer provar: quer provar que ESTA onda nao criou migration.
# Escrita como um tecto global, ela fica vermelha sempre que QUALQUER onda
# futura acrescentar uma (foi o que a Mig 140 do genero fez a SETE suites de
# uma vez). O invariante durável e' o do ASSUNTO: nenhuma migration do repo
# fala desta onda — isso continua verdade daqui a cem migrations.
check("7/a migration do pivot existe e é a única que fala dele",
      _mig in _migs
      and [m for m in _migs if m.endswith(".sql")
           and "grudge" in (m + _read(f"migrations/{m}")).lower()] == [_mig],
      _mig)
# 開 Edição comunitária — 5 verificações deste bloco mediam pastas que só existem
# no repositório do jogo oficial: o motor extraído (`motor_mestres/`, um serviço
# à parte), a pasta de publicação (`Publicacao/`) e a simulação da Fase A
# (`tools/`). Ficam lá; aqui fica escrito quantas e porquê, em vez de sumirem.
print("  ·  5 verificações do repositório oficial fora desta cópia "
      "(motor_mestres/, Publicacao/, tools/)")

print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)
print(f"OK — {PASS} asserts. Os três bugs do [jogador] estão mortos, o jogador novo "
      "nasce no mundo certo, e o mundo lembra-se de quem lhe fez mal.")
