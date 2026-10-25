# -*- coding: utf-8 -*-
"""印记 Marca do Traçado — Item B do lote QoL 06-08/08 (report [jogador] "Script Master").

Owner deu o override da migration em 2026-08-09. Standalone, ZERO base de dados:

    python -X utf8 scripts/_test_marca_tracado.py

Cobre, por secção:
  1. OFF-identity — com a flag OFF nada conta, nada desconta, nada entra no payload
  2. A escada — degraus, limiares, e o que cada um faz (e o que NUNCA faz)
  3. A duração — o Traço estica, nunca encurta, e a vitrine promete o que entrega
  4. O custo — o Sulco desconta BOUNDED, nunca zera uma linha, nunca vai a negativo
  5. A ARMADILHA — `_consume_one` apagava a row e levava a maestria junto
  6. O título é COSMÉTICO (Lei §4) e está registado no mapa de descrições
  7. Wiring por grep — engine → payload → as 2 superfícies
  8. i18n — paridade ×3 ×2, placeholders simétricos, PT-BR (anti EU-PT)
  9. A migration 138 — existe, é aditiva e é backwards compatible
"""
from __future__ import annotations

import inspect
import json
import os
import re
import sys
import types

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
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


import core.formation_engine as fe
from core.formation_engine import (
    MARCA_DURATION_BONUS, MARCA_MATERIAL_CUT, MARCA_STONE_DISCOUNT, MARCA_TIERS,
    MARCA_TITLE, marca_discount_recipe, marca_duration_minutes, marca_next,
    marca_tier, marca_view,
)
from database.seeds.formation_seeds import FORMATION_SEEDS

LANGS = ("pt", "en", "es")
CHAT = {lg: json.loads(_read(f"locales/{lg}.json")) for lg in LANGS}
MINI = {lg: json.loads(_read(f"miniapp/i18n/{lg}.json")) for lg in LANGS}
_fe_src = _read("core/formation_engine.py")
_tabs = _read("miniapp/components/tabs.js")
_sect = _read("handlers/sect.py")
_db = _read("database/db.py")
_models = _read("database/models.py")
_ach = _read("core/achievement_engine.py")

_ORIG_ON = fe.marca_on

print("\n── 1. OFF-identity ─────────────────────────────────────────────")

fe.marca_on = lambda *a, **k: False
check("off/marca_on tem fail-safe para False",
      "except Exception:\n        return False" in inspect.getsource(_ORIG_ON))
check("off/a leitura de ativações nem toca na coluna com a flag OFF",
      "if not marca_on():\n        return 0" in inspect.getsource(fe._marca_uses))
_src_list = inspect.getsource(fe.list_formations)
check("off/o mapa de maestria da lista é gated",
      "if marca_on():" in _src_list)
check("off/a key `marca` do item é CONDICIONAL (payload OFF byte-idêntico)",
      '**({"marca": _marca} if _marca else {}),' in _src_list)
check("off/a key `cost_stones_full` é CONDICIONAL",
      '**({"cost_stones_full": _full_stones} if _full_stones > r_stones else {}),' in _src_list)
_src_act = inspect.getsource(fe.activate_on_body)
check("off/o crédito da ativação é gated", "if marca_on():" in _src_act)
_src_craft = inspect.getsource(fe.craft_formation)
check("off/a key `marca_saved_stones` do craft é CONDICIONAL",
      "if full_stones > r_stones:" in _src_craft)
check("off/a flag nasce OFF em DEFAULT_WORLD_FEATURES (Lei §5/§11)",
      '"marca_do_tracado":    False,' in _db)
fe.marca_on = _ORIG_ON

print("\n── 2. A escada ─────────────────────────────────────────────────")

check("escada/são 3 degraus", len(MARCA_TIERS) == 3, str(MARCA_TIERS))
check("escada/os limiares são 50 / 200 / 1000",
      [n for _l, n, _k in MARCA_TIERS] == [50, 200, 1000], str(MARCA_TIERS))
check("escada/os limiares são estritamente crescentes",
      all(MARCA_TIERS[i][1] < MARCA_TIERS[i + 1][1] for i in range(len(MARCA_TIERS) - 1)))
for uses, want in ((0, 0), (1, 0), (49, 0), (50, 1), (199, 1), (200, 2),
                   (999, 2), (1000, 3), (999999, 3)):
    check(f"escada/{uses} ativações = degrau {want}", marca_tier(uses) == want,
          str(marca_tier(uses)))
check("escada/marca_next no topo devolve None", marca_next(1000) is None)
check("escada/marca_next conta o que FALTA, não o total",
      marca_next(37) == (1, 13), str(marca_next(37)))
check("escada/marca_next atravessa o degrau certo", marca_next(50) == (2, 150),
      str(marca_next(50)))
check("escada/valores negativos degradam a 0 (nunca crasham)", marca_tier(-5) == 0)

# ⚠️ O QUE A MARCA NUNCA PODE FAZER. Estes três asserts são o coração do veto do
# [jogador] e da Lei §4 — se algum cair, o sistema virou P2W ou buff permanente.
check("veto/a marca NÃO torna a formação permanente (o buff continua a expirar)",
      "expires_at=now + timedelta(" in _src_act)
check("veto/a marca NÃO toca na POTÊNCIA do buff",
      "buff_value=float(f.effect_value or 1.0),   # POTÊNCIA nunca sobe" in _fe_src)
check("veto/nenhum degrau devolve bônus de stat",
      not re.search(r"MARCA_\w*(BP|ATK|DEF|POWER|STAT)", _fe_src))

print("\n── 3. A duração — o Traço ──────────────────────────────────────")

check("dur/abaixo de 50 a duração é a de catálogo",
      marca_duration_minutes(60, 49) == 60)
check("dur/a 50 a duração estica +15%",
      marca_duration_minutes(60, 50) == 69, str(marca_duration_minutes(60, 50)))
check("dur/o bônus é o anunciado", abs(MARCA_DURATION_BONUS - 0.15) < 1e-9)
check("dur/o degrau 2 não estica mais (um lever por degrau)",
      marca_duration_minutes(60, 200) == marca_duration_minutes(60, 50))
# Nunca encurtar: o arredondamento para baixo poderia devolver menos que a base
# em durações pequenas — o max() protege isso para TODA duração semeada.
for s in FORMATION_SEEDS:
    base = int(s["duration_minutes"])
    for u in (0, 50, 200, 1000):
        check(f"dur/{s['key']}@{u} nunca encurta",
              marca_duration_minutes(base, u) >= base,
              f"{base}->{marca_duration_minutes(base, u)}")
check("dur/base 1 minuto continua >= 1", marca_duration_minutes(1, 1000) >= 1)

print("\n── 4. O custo — o Sulco ────────────────────────────────────────")

def _rec(seed):
    r = seed.get("recipe") or {}
    return (int(r.get("stones", 0) or 0), list(r.get("herbs") or []), list(r.get("ores") or []))

for s in FORMATION_SEEDS:
    st, hb, orr = _rec(s)
    # Abaixo do degrau 2 nada muda — e as listas devolvidas são CÓPIAS.
    st0, hb0, or0 = marca_discount_recipe(st, hb, orr, 199)
    check(f"custo/{s['key']}: abaixo de 200 o preço é o cheio",
          st0 == st and [m["qty"] for m in hb0] == [m["qty"] for m in hb]
          and [m["qty"] for m in or0] == [m["qty"] for m in orr])

    st2, hb2, or2 = marca_discount_recipe(st, hb, orr, 200)
    check(f"custo/{s['key']}: as pedras caem 20%", st2 == int(st * 0.8), f"{st}->{st2}")
    check(f"custo/{s['key']}: as pedras nunca ficam negativas", st2 >= 0)
    check(f"custo/{s['key']}: o craft NUNCA fica de graça",
          st2 > 0 or sum(int(m["qty"]) for m in hb2 + or2) > 0)
    for m in hb2 + or2:
        check(f"custo/{s['key']}: nenhuma linha de material vai abaixo de 1",
              int(m["qty"]) >= 1, str(m))
    cut = (sum(int(m["qty"]) for m in hb + orr) - sum(int(m["qty"]) for m in hb2 + or2))
    check(f"custo/{s['key']}: no máximo {MARCA_MATERIAL_CUT} unidade de material poupada",
          0 <= cut <= MARCA_MATERIAL_CUT, str(cut))

check("custo/o desconto de pedras é o anunciado", abs(MARCA_STONE_DISCOUNT - 0.20) < 1e-9)
# A linha cortada é a de MAIOR quantidade e o corte é determinístico (o preview
# e o débito têm de concordar — senão é display-lie).
_st, _hb, _or = marca_discount_recipe(
    100, [{"herb_id": 1, "qty": 2}], [{"ore_id": 9, "qty": 5}], 1000)
check("custo/corta a linha PRINCIPAL (a de maior quantidade)",
      _hb[0]["qty"] == 2 and _or[0]["qty"] == 4, f"{_hb} {_or}")
check("custo/uma linha de qty 1 nunca é escolhida",
      marca_discount_recipe(10, [{"herb_id": 1, "qty": 1}], [], 1000)[1][0]["qty"] == 1)
check("custo/marca_discount_recipe devolve CÓPIAS (não muta a receita do catálogo)",
      (lambda src: (marca_discount_recipe(50, src, [], 1000), src[0]["qty"] == 4)[1])(
          [{"herb_id": 1, "qty": 4}]))
check("custo/receita vazia não crasha", marca_discount_recipe(0, [], [], 1000) == (0, [], []))

# display == roll: a lista e o craft chamam o MESMO helper.
check("custo/a lista desconta com o mesmo helper do craft",
      "marca_discount_recipe(r_stones, r_herbs, r_ores, _m_uses)" in _src_list
      and "marca_discount_recipe(r_stones, r_herbs, r_ores, marca_uses)" in _src_craft)
check("custo/o `craftable` é avaliado contra o preço DESCONTADO",
      _src_list.index("marca_discount_recipe(") < _src_list.index("craftable = stones >= r_stones"))
check("custo/o gate de pedras do craft corre DEPOIS do desconto",
      _src_craft.index("marca_discount_recipe(") < _src_craft.index('"not_enough_stones"'))
check("custo/`debit_materials` ficou INTOCADO (o cavern_establish partilha-o)",
      "def debit_materials(session, player_id: int, r_herbs: list, r_ores: list)" in _fe_src
      and "marca" not in inspect.getsource(fe.debit_materials))

print("\n── 5. A ARMADILHA — a row apagada ──────────────────────────────")

# `_consume_one` apagava a row quando o bolso esvaziava. Com a coluna nova isso
# apagaria 900 ativações acumuladas junto com o último item.
_src_consume = inspect.getsource(fe._consume_one)
check("armadilha/o delete passou a olhar body_uses",
      '_keep = int(getattr(pouch, "body_uses", 0) or 0) > 0' in _src_consume)
# ⚠️ O DEFEITO QUE O REVIEW APANHOU, e que apanhava o caso MAIS COMUM: com a
# flag ON, a 1ª ativação de quem tem UMA unidade zerava a qty ⇒ delete ⇒ o
# `_marca_credit` logo a seguir fazia INSERT com a MESMA PK de uma row deletada
# na mesma transação (conflito de identity-map do SQLAlchemy). Com a flag ON a
# row nunca é apagada.
check("armadilha/com a flag ON a row NUNCA é apagada (conflito de PK na mesma tx)",
      "or marca_on()" in _src_consume)
check("armadilha/com a flag OFF o delete é o de sempre (main byte-idêntica)",
      "if pouch.qty <= 0 and not _keep:" in _src_consume)
check("armadilha/_owned_map continua a filtrar qty > 0 (row de maestria não vira item)",
      "if int(r.qty or 0) > 0" in inspect.getsource(fe._owned_map))
check("armadilha/o crédito re-lê a row FOR UPDATE (pode ter sido apagada)",
      ".with_for_update()" in inspect.getsource(fe._marca_credit))
check("armadilha/o crédito recria a row com qty=0 quando ela sumiu",
      "qty=0, body_uses=0" in inspect.getsource(fe._marca_credit))
check("armadilha/a caverna NÃO conta (a escolha corpo-vs-caverna tem de doer)",
      "_marca_credit" not in _read("core/cavern_engine.py"))
check("armadilha/o crédito não pode desfazer uma ativação já feita",
      "logger.debug(\"marca credit failed\"" in _src_act)
check("armadilha/a maestria é lida ANTES do consumo (senão a duração sai errada)",
      _src_act.index("uses_before = await _marca_uses") < _src_act.index("_consume_one("))

print("\n── 6. O título é COSMÉTICO ─────────────────────────────────────")

check("titulo/a constante existe e tem emoji (padrão da casa)",
      MARCA_TITLE == "🔯 Marca do Traçado", MARCA_TITLE)
check("titulo/entra em unlocked_titles como o do MV-4/MV-6",
      "player.unlocked_titles = titles" in _fe_src)
check("titulo/só ao degrau 3", "if tier_after >= 3:" in _fe_src)
check("titulo/nunca duplica (o registo é eterno, o PK não é)",
      "if MARCA_TITLE not in titles:" in _fe_src)
# ⚠️ Lição "enum novo = grep a TODOS os mapas": sem esta linha o título listava
# com descrição VAZIA no ProfileModal.
check("titulo/está registado em EXTRA_TITLE_DESC_KEYS",
      '"🔯 Marca do Traçado": "title_desc_marca_do_tracado",' in _ach)
for lg in LANGS:
    check(f"titulo/a descrição existe em {lg}", "title_desc_marca_do_tracado" in CHAT[lg])
check("titulo/o título não concede bônus nenhum (Lei §4, decisão de 04/08)",
      "stat_bonus" not in _fe_src and "bonus_display" not in _fe_src)

print("\n── 7. Wiring por grep ──────────────────────────────────────────")

check("wiring/chat: a lista de Formações imprime a linha da maestria",
      '_mk = f.get("marca")' in _sect and 'lines.append(f"   {_mk[\'line\']}")' in _sect)
check("wiring/chat: a ativação diz o antes→depois",
      '"marca_progress_delta"' in _sect)
check("wiring/chat: o degrau novo é celebrado",
      'f"marca_up_{_mk[\'tier_up\']}"' in _sect)
check("wiring/chat: o título é dito", '"marca_title_granted"' in _sect)
check("wiring/chat: o craft diz o que o Sulco poupou",
      "'marca_craft_saved'" in _sect)
check("wiring/mini: o cartão desenha o bloco da maestria", "{f.marca && (" in _tabs)
check("wiring/mini: a barra do degrau seguinte existe", "f.marca.next_at > 0" in _tabs)
check("wiring/mini: o preço cheio riscado aparece", "f.cost_stones_full > 0" in _tabs)
check("wiring/mini: a ativação diz o antes→depois",
      't("marca_progress_delta", { before: mk.before, after: mk.after })' in _tabs)
check("wiring/mini: o degrau novo é celebrado", 't("marca_up_" + mk.tier_up' in _tabs)
check("wiring/mini: o título é dito", 't("marca_title_granted"' in _tabs)
check("wiring/mini: o craft diz o que o Sulco poupou", 't("marca_craft_saved"' in _tabs)
# O toast da ativação lia a duração do CATÁLOGO; com o Traço isso passaria a
# mentir 15% — passa a ler a do servidor.
check("wiring/mini: o toast lê a duração do SERVIDOR, não a do cartão",
      "res.duration_minutes || f.duration_minutes" in _tabs)
check("wiring/a vitrine promete a duração COM o Traço",
      '"duration_minutes": marca_duration_minutes(' in _fe_src)
# ⚠️ 2º defeito do review: o seletor mostrava UM número por cima dos DOIS
# botões, e a caverna não recebe o Traço — o ramo errado herdava a promessa.
check("wiring/a duração de CATÁLOGO é emitida (a caverna não recebe o Traço)",
      '"base_duration_minutes": int(f.duration_minutes or 60)' in _fe_src)
check("wiring/e é CONDICIONAL — só quando o Traço esticou (OFF-identity)",
      "if marca_duration_minutes(int(f.duration_minutes or 60), _m_uses)\n               > int(f.duration_minutes or 60) else {}" in _fe_src)
check("wiring/mini: o seletor diz a duração da CAVERNA",
      "pick.base_duration_minutes > 0" in _tabs and 't("marca_cavern_base"' in _tabs)
for lg in LANGS:
    check(f"wiring/marca_cavern_base existe em chat/{lg}", "marca_cavern_base" in CHAT[lg])
    check(f"wiring/marca_cavern_base existe em mini/{lg}", "marca_cavern_base" in MINI[lg])

# marca_view — a linha server-resolved, igual nas 2 superfícies.
_v = marca_view(37, "pt")
check("wiring/marca_view fala desde a 1ª ativação (Lei §10)", marca_view(1, "pt") is not None)
check("wiring/marca_view devolve None a zero (nada a dizer)", marca_view(0, "pt") is None)
check("wiring/marca_view traz uses/next/line", _v and _v["uses"] == 37 and _v["next_at"] == 50
      and "37" in _v["line"], str(_v))
check("wiring/no topo a linha muda e remaining é 0",
      (marca_view(1500, "pt") or {}).get("remaining") == 0
      and (marca_view(1500, "pt") or {}).get("next_at") is None)
check("wiring/os pct anunciados são os do engine",
      (marca_view(200, "pt") or {}).get("stone_discount_pct") == 20
      and (marca_view(200, "pt") or {}).get("duration_bonus_pct") == 15)
check("wiring/abaixo do degrau 1 não anuncia bônus nenhum",
      (marca_view(10, "pt") or {}).get("duration_bonus_pct") == 0
      and (marca_view(10, "pt") or {}).get("stone_discount_pct") == 0)
# A docstring promete "nunca levanta" e `list_formations` é chokepoint quente:
# um valor inesperado não pode derrubar a lista inteira de Formações.
check("wiring/marca_view nunca levanta com lixo", marca_view("x", "pt") is None)
check("wiring/marca_view aguenta None", marca_view(None, "pt") is None)

print("\n── 8. i18n ─────────────────────────────────────────────────────")

SHARED = ("marca_progress_delta", "marca_up_1", "marca_up_2", "marca_up_3",
          "marca_title_granted", "marca_craft_saved")
CHAT_ONLY = ("marca_tier_traco", "marca_tier_sulco", "marca_tier_marca",
             "marca_line_progress", "marca_line_max", "title_desc_marca_do_tracado")

sizes = {lg: len(CHAT[lg]) for lg in LANGS}
check("i18n/paridade chat ×3", len(set(sizes.values())) == 1, str(sizes))
msizes = {lg: len(MINI[lg]) for lg in LANGS}
check("i18n/paridade mini ×3", len(set(msizes.values())) == 1, str(msizes))

for k in SHARED:
    for lg in LANGS:
        check(f"i18n/{k} em chat/{lg}", k in CHAT[lg])
        check(f"i18n/{k} em mini/{lg}", k in MINI[lg])
    check(f"i18n/{k} diz o MESMO nas 2 superfícies (pt)", CHAT["pt"][k] == MINI["pt"][k])
for k in CHAT_ONLY:
    for lg in LANGS:
        check(f"i18n/{k} em chat/{lg}", k in CHAT[lg])

# ⚠️ Um degrau novo em MARCA_TIERS sem key rebenta AQUI (anti-recorrência).
for _lvl, _need, _key in MARCA_TIERS:
    for lg in LANGS:
        check(f"i18n/marca_tier_{_key} existe em {lg}", f"marca_tier_{_key}" in CHAT[lg])
        check(f"i18n/marca_up_{_lvl} existe em chat/{lg}", f"marca_up_{_lvl}" in CHAT[lg])
        check(f"i18n/marca_up_{_lvl} existe em mini/{lg}", f"marca_up_{_lvl}" in MINI[lg])

for k in SHARED:
    sets = {lg: set(re.findall(r"\{(\w+)\}", CHAT[lg][k])) for lg in LANGS}
    check(f"i18n/{k} placeholders simétricos ×3", len(set(map(frozenset, sets.values()))) == 1,
          str(sets))
    msets = {lg: set(re.findall(r"\{(\w+)\}", MINI[lg][k])) for lg in LANGS}
    check(f"i18n/mini {k} placeholders simétricos ×3",
          len(set(map(frozenset, msets.values()))) == 1, str(msets))
for k in ("marca_line_progress", "marca_line_max"):
    sets = {lg: set(re.findall(r"\{(\w+)\}", CHAT[lg][k])) for lg in LANGS}
    check(f"i18n/{k} placeholders simétricos ×3", len(set(map(frozenset, sets.values()))) == 1,
          str(sets))
check("i18n/marca_progress_delta tem before E after nas 3",
      all({"before", "after"} == set(re.findall(r"\{(\w+)\}", CHAT[lg]["marca_progress_delta"]))
          for lg in LANGS))
check("i18n/marca_up_* tem {name} nas 3", all("{name}" in CHAT[lg][f"marca_up_{n}"]
      for lg in LANGS for n in (1, 2, 3)))

# O chat imprime isto SEM parse_mode — mas o banner viaja junto de outras
# linhas; markdown solto continua a ser lixo visível. Varre-se tudo.
for k in SHARED + CHAT_ONLY:
    for lg in LANGS:
        check(f"i18n/{lg}/{k} sem markdown solto", not re.search(r"[*_`]", CHAT[lg][k]),
              CHAT[lg][k])

_EU_PT = re.compile(r"\b(está a |estás|ecrã|utilizador|ficheiro|telemóvel|"
                    r"a fazer\b|carregue no|prima |fixou-se|abriu-se)", re.I)
for k in SHARED + CHAT_ONLY:
    v = CHAT["pt"][k]
    check(f"ptbr/{k} sem EU-PT", not _EU_PT.search(v), v)
for k in SHARED:
    v = MINI["pt"][k]
    check(f"ptbr/mini {k} sem EU-PT", not _EU_PT.search(v), v)
check("ptbr/as celebrações tratam por você (nunca tu/teu)",
      all("teu" not in CHAT["pt"][f"marca_up_{n}"].lower()
          and " tu " not in f" {CHAT['pt'][f'marca_up_{n}'].lower()} " for n in (1, 2, 3)))

print("\n── 9. A migration 138 ──────────────────────────────────────────")

_migs = sorted(os.listdir(os.path.join(ROOT, "migrations")))
_mig = [m for m in _migs if m.startswith("138")]
check("mig/existe exatamente UMA migration 138", len(_mig) == 1, str(_mig))
_sql = _read(f"migrations/{_mig[0]}") if _mig else ""
check("mig/é aditiva com IF NOT EXISTS (re-run seguro)",
      "ADD COLUMN IF NOT EXISTS body_uses" in _sql)
check("mig/tem DEFAULT 0 (nenhum jogador existente é penalizado)",
      "DEFAULT 0" in _sql)
check("mig/NUNCA faz DROP", "DROP" not in _sql.upper())
check("mig/o modelo tem a coluna", "body_uses: Mapped[int]" in _models)
check("mig/o modelo declara server_default (paridade com o SQL)",
      'body_uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default=text("0"))'
      in _models)
# PIVOT 2026-08-11: a 139 e da Fase A3 do Motor (world_sects.grudges), nao desta
# onda. O literal antigo virou falso vermelho no dia em que a onda seguinte shipou.
# ⚠️ 2026-09-07 — esta guarda dizia "nenhuma migration 140+ nasceu", e isso
# NAO e' o que ela quer provar: quer provar que ESTA onda nao criou migration.
# Escrita como um tecto global, ela fica vermelha sempre que QUALQUER onda
# futura acrescentar uma (foi o que a Mig 140 do genero fez a SETE suites de
# uma vez). O invariante durável e' o do ASSUNTO: nenhuma migration do repo
# fala desta onda — isso continua verdade daqui a cem migrations.
# ⚠️ Esta onda TEM migration propria (a 138, body_uses) — o override do owner
# de 09/08. O que se prova aqui e' que ela e' a UNICA que fala do assunto.
_cita = [m for m in _migs if m.endswith(".sql")
         and any(a in (m + _read(f"migrations/{m}")).lower()
                 for a in ("body_uses", "formation_mastery"))]
check("mig/so' a 138 fala da Marca do Tracado",
      _cita == ["138_formation_mastery.sql"], str(_cita))

print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)
print(f"OK — {PASS} asserts. O corpo lembra as curvas, e a formação continua a expirar.")
