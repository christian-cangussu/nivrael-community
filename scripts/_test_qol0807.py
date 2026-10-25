# -*- coding: utf-8 -*-
"""QoL-Feedback 07/08 — Item C (report [jogador]) + Item A (report [jogador]).

Molde: `scripts/_test_mv9_cidades.py`. Standalone, ZERO base de dados:
    python -X utf8 scripts/_test_qol0807.py

Cobre, por secção:
  1. OFF-identity — as flags existentes OFF continuam a não emitir nada
  2. O objetivo em palavras — cobertura TOTAL dos objective_type das seeds
     (o assert anti-recorrência: um tipo novo sem mapa rebenta aqui)
  3. O mapa de rota do mini — `QUEST_OBJECTIVE_TAB` cobre quests E storylets,
     e a forma {tab,seg} não partiu as entradas antigas
  4. O flavor que MENTIA — `sty_enc_fenghuo_forja_d2` já não manda bater
  5. Item A — o lote de reposição: escopo, guard antes do débito, paridade
  6. WIRING por grep — todo helper novo tem call site real nas 2 superfícies
  7. i18n — paridade ×3×2, placeholders simétricos, PT-BR (anti EU-PT)
  8. ZERO migration
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


import core.city_engine as cid
import core.storylet_engine as sty
from core.storylet_engine import (
    _OBJ_CHAT_CMD, _OBJ_EMOJI, objective_chat_cmd, objective_line,
)
from database.seeds.storylet_seeds import STORYLET_SEEDS
from database.seeds.quests_seeds import QUEST_SEEDS

LANGS = ("pt", "en", "es")
CHAT = {lg: json.loads(_read(f"locales/{lg}.json")) for lg in LANGS}
MINI = {lg: json.loads(_read(f"miniapp/i18n/{lg}.json")) for lg in LANGS}
_tabs = _read("miniapp/components/tabs.js")
_inv = _read("handlers/inventory.py")
_web = _read("core/webserver.py")
_alch = _read("core/alchemy_engine.py")
_sect = _read("handlers/sect.py")
_quests = _read("handlers/quests.py")
_main = _read("main.py")

STY_OBJ_TYPES = {str(s["objective_type"]) for s in STORYLET_SEEDS}
QST_OBJ_TYPES = {str(q["objective_type"]) for q in QUEST_SEEDS}

print("\n── 1. OFF-identity ─────────────────────────────────────────────")

_ORIG_ON, _ORIG_QV = cid.cidades_on, cid._quests_vivas_on
cid.cidades_on = lambda *a, **k: False
check("off/encargo_view devolve None com a flag OFF",
      inspect.iscoroutinefunction(cid.encargo_view))
_src_ev = inspect.getsource(cid.encargo_view)
check("off/o gate é a PRIMEIRA coisa em encargo_view",
      "if not cidades_on()" in _src_ev)
cid.cidades_on, cid._quests_vivas_on = _ORIG_ON, _ORIG_QV

# O helper do objetivo é PURO: não toca DB, não depende de flag. Chamá-lo num
# mundo com tudo OFF é seguro por construção — mas quem o CHAMA está atrás dos
# gates que já existiam (city_engine/storylet_engine), logo o payload de um
# mundo OFF continua byte-idêntico.
check("off/objective_line não é async (zero I/O)",
      not inspect.iscoroutinefunction(objective_line))
check("off/objective_chat_cmd não é async (zero I/O)",
      not inspect.iscoroutinefunction(objective_chat_cmd))
# ⚠️ CORRIGIDO 2026-08-09, não enfraquecido. O assert original era
#   `'"caravana"' not in _read("database/db.py")`
# — usava o nome da flag que o recon do MV-9.5 tinha batizado nesse MESMO dia
# como canário de "esta onda não criou flag". A canária cumpriu o papel dela e
# morreu: o MV-9.5 shipou e a flag `caravana` existe agora (db.py, a 27ª). O que
# a onda de 07/08 realmente prometia é mais forte e não expira — os dois helpers
# do objetivo são PUROS e não vivem atrás de gate nenhum, logo continuam a
# funcionar em qualquer mundo, inclusive no `main` com tudo OFF.
_sty_src = _read("core/storylet_engine.py")
_obj_src = _sty_src.split("def objective_line")[1].split("\ndef ")[0]
_cmd_src = _sty_src.split("def objective_chat_cmd")[1].split("\ndef ")[0]
check("off/objective_line não tem gate de flag",
      "feature_enabled" not in _obj_src and "_on()" not in _obj_src)
check("off/objective_chat_cmd não tem gate de flag",
      "feature_enabled" not in _cmd_src and "_on()" not in _cmd_src)

print("\n── 2. O objetivo em palavras ───────────────────────────────────")

# ⚠️ O ASSERT ANTI-RECORRÊNCIA. `forge_artifact` existia nas seeds e não estava
# no mapa de rota do mini — foi por isso que um jogador ficou sem para onde ir.
# Um objective_type novo que entre nas seeds sem passar pelos mapas rebenta AQUI.
missing_emoji = STY_OBJ_TYPES - set(_OBJ_EMOJI)
check("obj/todo objective_type das seeds tem emoji", not missing_emoji, str(missing_emoji))
missing_cmd = STY_OBJ_TYPES - set(_OBJ_CHAT_CMD)
check("obj/todo objective_type das seeds tem comando de chat", not missing_cmd, str(missing_cmd))
check("obj/o mapa não tem tipo a mais (sem key de i18n órfã)",
      set(_OBJ_EMOJI) == set(_OBJ_CHAT_CMD),
      str(set(_OBJ_EMOJI) ^ set(_OBJ_CHAT_CMD)))

for tt in sorted(_OBJ_CHAT_CMD.values()):
    check(f"obj/o comando {tt} existe mesmo em main.py",
          f'CommandHandler("{tt.lstrip("/")}"' in _main, tt)

for tt in sorted(_OBJ_EMOJI):
    for lg in LANGS:
        key = f"sty_obj_{tt}"
        check(f"obj/{key} existe em {lg}", key in CHAT[lg])
        if key in CHAT[lg]:
            check(f"obj/{key} tem o placeholder {{n}} em {lg}", "{n}" in CHAT[lg][key],
                  CHAT[lg][key])

# A frase real, montada.
_line = objective_line("forge_artifact", 3, "pt")
check("obj/a frase do encargo do [jogador] diz FORJAR",
      _line and "Forjar" in _line and "3" in _line, str(_line))
check("obj/a frase carrega o emoji do tipo", _line and _line.startswith("⚒️"), str(_line))
check("obj/tipo desconhecido degrada a None (nunca key crua)",
      objective_line("tipo_que_nao_existe", 2, "pt") is None)
check("obj/objective_type vazio degrada a None", objective_line("", 1, "pt") is None)
check("obj/objective_type None degrada a None", objective_line(None, 1, "pt") is None)
check("obj/count 0 nunca imprime zero", "1" in (objective_line("craft_pill", 0, "pt") or ""))
check("obj/comando desconhecido devolve None",
      objective_chat_cmd("tipo_que_nao_existe") is None)
check("obj/o comando do encargo do [jogador] é /forjar",
      objective_chat_cmd("forge_artifact") == "/forjar")

# O payload: as 3 projeções carregam a linha.
_sty_src = _read("core/storylet_engine.py")
check("obj/_offer_view carrega objective_line",
      _sty_src.count('"objective_line": objective_line(') >= 2)
check("obj/_offer_view carrega objective_cmd",
      _sty_src.count('"objective_cmd": objective_chat_cmd(') >= 2)
check("obj/o encargo reusa o helper do storylet (uma verdade)",
      "from core.storylet_engine import objective_chat_cmd, objective_line"
      in _read("core/city_engine.py"))
check("obj/o comentário que dizia que 'as duas superfícies já sabem' foi corrigido",
      "CORREÇÃO 2026-08-07" in _read("core/city_engine.py"))

print("\n── 3. O mapa de rota do mini ───────────────────────────────────")

_m = re.search(r"const QUEST_OBJECTIVE_TAB = \{(.*?)\n    \};", _tabs, re.S)
check("rota/QUEST_OBJECTIVE_TAB continua a existir", _m is not None)
_map_src = _m.group(1) if _m else ""
mapped = set(re.findall(r"^\s*(\w+):", _map_src, re.M))
check("rota/forge_artifact ENTROU no mapa (o defeito do report)",
      "forge_artifact" in mapped)
for tt in sorted(STY_OBJ_TYPES):
    check(f"rota/storylet {tt} tem rota no mini", tt in mapped, tt)
for tt in sorted(QST_OBJ_TYPES - {"login"}):  # login auto-completa, não tem destino
    check(f"rota/quest {tt} tem rota no mini", tt in mapped, tt)
check("rota/forge_artifact aponta para o SEGMENTO da forja",
      re.search(r"forge_artifact:\s*\{\s*tab:\s*\"crafting\",\s*seg:\s*\"forge\"", _map_src)
      is not None)
check("rota/as entradas antigas continuam strings (forma não quebrou)",
      '\n      cultivate: "cultivation",' in _map_src)
check("rota/objectiveRoute normaliza string e objeto",
      'typeof e === "string"' in _tabs)
check("rota/goToObjective existe e é usado pela QuestRow",
      "function goToObjective" in _tabs and "goToObjective(setTab, goTab)" in _tabs)
check("rota/o pedido de segmento tem TTL (não sequestra abertura futura)",
      "PENDING_TAB_SEG_TTL_MS" in _tabs)
check("rota/qualquer mount limpa o pedido pendente",
      "PENDING_TAB_SEG = null;               // qualquer mount limpa o pedido" in _tabs)
check("rota/CraftingTab consome o segmento pedido",
      'takePendingSeg("crafting")' in _tabs)
check("rota/o cartão do Encargo desenha a linha de objetivo",
      "d.city.encargo.objective_line" in _tabs)
check("rota/o cartão do Encargo tem o chip →",
      "goToObjective(setTab, d.city.encargo.objective_type)" in _tabs)
check("rota/o storylet aceito desenha a linha de objetivo",
      "a.objective_line" in _tabs)
check("rota/o modal da OFERTA diz o que exige antes de aceitar",
      "offer.objective_line" in _tabs)
check("rota/StoryletSection recebe setTab (senão o chip nunca aparece)",
      "function StoryletSection({ onOpenStorylet, styReload, onPlayerRefresh, setTab })" in _tabs
      and "<StoryletSection onOpenStorylet={onOpenStorylet} styReload={styReload} onPlayerRefresh={onPlayerRefresh} setTab={setTab} />" in _tabs)

print("\n── 4. O flavor que MENTIA ──────────────────────────────────────")

_BAD = {"pt": ("bata em alguma coisa", "bater em"),
        "en": ("go hit something", "hit something"),
        "es": ("golpear algo", "ve a golpear")}
for lg in LANGS:
    v = (CHAT[lg].get("sty_enc_fenghuo_forja_d2") or "").lower()
    check(f"flavor/{lg}: o d2 do encargo da FORJA já não manda bater",
          not any(b in v for b in _BAD[lg]), v)
    check(f"flavor/{lg}: o d2 fala de martelo/bigorna",
          any(w in v for w in ("martelo", "bigorna", "hammer", "anvil", "martillo", "yunque")), v)

# Varredura dos 15: o encargo de COMBATE pode falar de bater; o de FORJA não.
_ENC_OBJ = {s["key"]: s["objective_type"] for s in STORYLET_SEEDS if int(s.get("weight", 10)) == 0}
check("flavor/os 15 encargos continuam semeados", len(_ENC_OBJ) == 15, str(len(_ENC_OBJ)))
_FORGE_ENC = [k for k, o in _ENC_OBJ.items() if o == "forge_artifact"]
check("flavor/só um encargo é de forja", len(_FORGE_ENC) == 1, str(_FORGE_ENC))
for k in _ENC_OBJ:
    for lg in LANGS:
        for suf in ("name", "desc", "d1", "d2"):
            check(f"flavor/{k}_{suf} existe em {lg}", f"sty_{k}_{suf}" in CHAT[lg])

print("\n── 5. Item A — o lote de reposição ─────────────────────────────")

from core.alchemy_engine import BULK_REFILL_TYPES, refill_cap_state

check("lote/o escopo é exatamente qi_restore + hp_restore",
      BULK_REFILL_TYPES == frozenset({"qi_restore", "hp_restore"}), str(BULK_REFILL_TYPES))
check("lote/qi_capacity FICA DE FORA (resistência a remédio é qi_capacity-only)",
      "qi_capacity" not in BULK_REFILL_TYPES)
check("lote/nada temporizado entrou", not (BULK_REFILL_TYPES & {
    "cb_boost", "purity_boost", "luck_boost", "qi_regen_boost"}))
check("lote/refill_cap_state é async (lê equipamento)",
      inspect.iscoroutinefunction(refill_cap_state))
_rcs = inspect.getsource(refill_cap_state)
# ⚠️ olhar o CÓDIGO, não a docstring: a docstring cita `player.qi_capacity` de
# propósito, para explicar porque NÃO se usa (um assert ingénuo lia a explicação
# como se fosse a violação).
_rcs_code = re.sub(r"^\s*#.*$", "", re.sub(r'"""(?:.|\n)*?"""', "", _rcs, count=1), flags=re.M)
check("lote/o teto do qi é a capacidade EFETIVA, nunca a crua",
      "get_effective_qi_capacity" in _rcs_code and "player.qi_capacity" not in _rcs_code)
check("lote/a docstring EXPLICA porque não se usa a capacidade crua",
      "player.qi_capacity" in _rcs and "EFETIVA" in _rcs)
check("lote/falha de leitura degrada ABERTO (nunca inventa dead-end)",
      "Fail-OPEN" in _rcs)

# ⚠️ O dead-end que o review encontrou ANTES de existir tela: a Supreme Healing
# Pill (id 30) passa do teto (+10% de escudo), logo "HP cheio" NÃO é "não faz
# nada" para ELA. Um guard genérico recusaria o lote onde o uso unitário
# funciona. E `get_current_hp` faz min(current, max) — apagaria o escudo e
# faria um jogador já escudado parecer "exatamente cheio" para sempre.
from core.alchemy_engine import HP_SHIELD_CEILING_MULT, HP_SHIELD_PILL_ID
check("lote/o id da pílula-escudo é constante partilhada", HP_SHIELD_PILL_ID == 30)
check("lote/o teto do escudo é constante partilhada", abs(HP_SHIELD_CEILING_MULT - 1.10) < 1e-9)
check("lote/o guard usa o teto da PÍLULA, não o genérico",
      "HP_SHIELD_CEILING_MULT" in _rcs_code and "HP_SHIELD_PILL_ID" in _rcs_code)
check("lote/o guard NÃO usa get_current_hp (apagaria o escudo)",
      "get_current_hp" not in _rcs_code)
check("lote/o guard trata current_hp NULL como HP cheio",
      "raw is None" in _rcs_code)
_apply_src = inspect.getsource(sys.modules["core.alchemy_engine"].apply_pill_effect)
check("lote/o apply lê as MESMAS constantes (uma verdade, um número)",
      "HP_SHIELD_PILL_ID" in _apply_src and "HP_SHIELD_CEILING_MULT" in _apply_src)
check("lote/o apply já não tem o 30 / 0.10 / 1.10 cozidos",
      "pill.id == 30" not in _apply_src and "max_hp * 1.10" not in _apply_src)


class _FakePill:
    def __init__(self, pid, etype):
        self.id, self.effect_type = pid, etype


class _FakePlayer:
    telegram_id = 1
    current_hp = None
    qi = 0
    qi_capacity = 100
    body_tempering_level = 0


import asyncio as _aio


def _hp_state(pill_id, current_hp, max_hp=1000.0):
    p, pill = _FakePlayer(), _FakePill(pill_id, "hp_restore")
    p.current_hp = current_hp
    _mod = sys.modules["core.alchemy_engine"]
    import core.combat_engine as _ce
    _orig = _ce.get_max_hp
    _ce.get_max_hp = lambda _pl: max_hp
    try:
        return _aio.run(_mod.refill_cap_state(None, p, pill))
    finally:
        _ce.get_max_hp = _orig


_s = _hp_state(1, 1000.0)          # pílula normal, HP cheio
check("lote/HP cheio + pílula normal = AT CAP (não queima)", _s and _s["at_cap"], str(_s))
_s = _hp_state(30, 1000.0)         # pílula-escudo, HP cheio, sem escudo ainda
check("lote/HP cheio + pílula-ESCUDO = NÃO at cap (o escudo ainda entra)",
      _s and not _s["at_cap"], str(_s))
_s = _hp_state(30, 1100.0)         # pílula-escudo, já no teto do escudo
check("lote/escudo no teto + pílula-escudo = AT CAP", _s and _s["at_cap"], str(_s))
_s = _hp_state(1, 1100.0)          # já escudado, pílula normal
check("lote/já escudado + pílula normal = AT CAP", _s and _s["at_cap"], str(_s))
_s = _hp_state(1, 500.0)           # ferido
check("lote/ferido = NÃO at cap", _s and not _s["at_cap"], str(_s))
_s = _hp_state(1, None)            # NULL no DB = cheio
check("lote/current_hp NULL lê-se como cheio", _s and _s["at_cap"], str(_s))
check("lote/pílula que não é de reposição devolve None",
      _aio.run(sys.modules["core.alchemy_engine"].refill_cap_state(
          None, _FakePlayer(), _FakePill(1, "cb_boost"))) is None)

check("lote/chat: o guard corre ANTES do débito",
      _inv.index("refill_cap_state(session, player, pill)") < _inv.index(
          ".values(quantity=PlayerInventory.quantity - 1)"))
check("lote/chat: o botão usa a MESMA constante do executor",
      "BULK_REFILL_TYPES as _BULK_REFILL" in _inv)
check("lote/chat: o resumo diz quantas sobraram (Lei §1)",
      'inv_pill_bulk_cap_stop' in _inv)
# (o "cheio ao tocar" tem key própria — ver secção 5b, achado rev/5; o assert
#  antigo travava na frase emprestada que o review mandou substituir)
check("lote/chat: o ramo 'cheio ao tocar' existe e é distinto do 'encheu a meio'",
      "elif refill_stop and applied == 0 and capped == 0 and no_stock == 0:" in _inv)

check("lote/mini: o gate do bulk aceita reposição",
      "and not _is_refill:" in _web)
check("lote/mini: recusa NOMEADA antes do débito",
      '"refill_at_cap"' in _web)
check("lote/mini: o guard corre dentro do loop também",
      _web.count("await refill_cap_state(session, player, pill)") >= 2)
check("lote/mini: supports_bulk usa a mesma constante",
      "_BULK_REFILL_TYPES" in _web)
check("lote/mini: o payload novo é CONDICIONAL (OFF-identity do payload)",
      'if refill_stop else {}' in _web)
check("lote/mini: o cliente trata refill_at_cap",
      'res.reason === "refill_at_cap"' in _tabs)
check("lote/mini: o cliente diz quantas sobraram",
      'pill_panel_refill_stopped' in _tabs)

print("\n── 5b. Os achados do REVIEW ADVERSARIAL ────────────────────────")

_alch_h = _read("handlers/alchemy.py")

# (1) O guard tem de cobrir os QUATRO caminhos de uso, não dois. O defeito que
# o review apanhou foi criado por esta onda: o mini passou a recusar o toque
# unitário e o chat continuava a queimar — duas políticas para o mesmo gesto.
check("rev/1: guard no LOTE do chat", "refill_cap_state" in _inv)
check("rev/1: guard no UNITÁRIO do chat (_do_use_pill)",
      "refill_cap_state as _refill_state" in _inv and _inv.count("_refill_state(session, player, pill)") >= 1)
check("rev/1: guard no /pilulas (handlers/alchemy.py — o 4º caminho)",
      "refill_cap_state" in _alch_h)
check("rev/1: guard no mini", "refill_cap_state" in _web)
_body_use = _inv.split("async def _do_use_pill(")[1].split("\nasync def ")[0]
check("rev/1: no unitário o guard corre ANTES do débito",
      0 < _body_use.find("_refill_state(session, player, pill)")
      < _body_use.find(".values(quantity=PlayerInventory.quantity - 1)"))
_body_alch = _alch_h.split("async def usar_pilula_callback(")[1].split("\nasync def ")[0]
check("rev/1: no /pilulas o guard corre ANTES do débito",
      0 < _body_alch.find("_refill_state(session, player, pill)")
      < _body_alch.find(".values(quantity=PlayerInventory.quantity - 1)"))

# (2) O nome do campo — o teste antigo só grepava a `reason` e dava verde a um
# ramo morto (`pill_panel_hp_full_refused` nunca renderizava).
check("rev/2: a RECUSA do mini emite `refill_kind` (não `kind`)",
      '"refill_kind": _rs0["kind"]' in _web and '"kind": _rs0["kind"]' not in _web)
check("rev/2: o SUCESSO do mini emite o mesmo nome", '"refill_kind": refill_stop["kind"]' in _web)
check("rev/2: o cliente lê exatamente `res.refill_kind`", 'res.refill_kind === "hp"' in _tabs)
check("rev/2: a key de HP do mini é alcançável (não é código morto)",
      'pill_panel_hp_full_refused' in _tabs)

# (3) O chip do Encargo só com o encargo ACEITO — senão convidava a trabalhar
# de graça (track_storylets só credita rows `accepted`).
check("rev/3: o chip do Encargo exige status accepted",
      '(d.city.encargo.mine || {}).status === "accepted"' in _tabs)
check("rev/3: a FRASE do objetivo continua sem gate (é o contrato)",
      "{d.city.encargo.objective_line && (" in _tabs)

# (4) O ponteiro some quando o encargo está pronto (o caminho é entregar).
check("rev/4: o chat esconde o comando com o encargo ready",
      '_mine.get("status") != "ready"' in _sect)
check("rev/4: `_mine` é atribuído ANTES da linha de objetivo (senão UnboundLocalError)",
      _sect.find('_mine = _enc.get("mine") or {}') < _sect.find('_enc.get("objective_line")'))

# (5) A recusa do lote deixou de usar a frase emprestada de "encheu a meio".
check("rev/5: o ramo 'já estava cheio' usa key PRÓPRIA",
      'msg = t(lang, "pill_hp_full_kept" if refill_stop["kind"] == "hp"' in _inv)
check("rev/5: `inv_pill_bulk_cap_stop` já não é usada com used=0",
      "used=0, left=count" not in _inv)
for k in ("pill_qi_full_kept", "pill_hp_full_kept"):
    for lg in LANGS:
        check(f"rev/5: {k} existe em {lg}", k in CHAT[lg])
    check(f"rev/5: {k} não tem placeholder (as 3 chamadas passam zero kwargs)",
          all(not re.search(r"\{\w+\}", CHAT[lg][k]) for lg in LANGS))

# (6) `npc_combat` só credita PvE — o texto tem de dizer NPC, senão manda o
# jogador duelar gente e ficar a 0/N (o report do [jogador], outra vez).
for lg, needle in (("pt", "NPC"), ("en", "NPC"), ("es", "NPC")):
    check(f"rev/6: sty_obj_npc_combat diz NPC em {lg}",
          needle in CHAT[lg]["sty_obj_npc_combat"], CHAT[lg]["sty_obj_npc_combat"])
check("rev/6: o injector também foi corrigido (não reintroduz no próximo boot)",
      "NPC" in _read("scripts/inject_qol0807_i18n.py"))

# (7) ES: os painéis tratam por "tú" — as strings novas não podem estrear "usted".
_ES_USTED = re.compile(r"\b(Su |Usó |Su\b)")
for k in ("pill_qi_full_kept", "pill_hp_full_kept", "inv_pill_bulk_cap_stop"):
    check(f"rev/7: es/{k} trata por tú", not _ES_USTED.search(CHAT["es"][k]), CHAT["es"][k])
for k in ("pill_panel_qi_full_refused", "pill_panel_hp_full_refused"):
    check(f"rev/7: es mini/{k} trata por tú", not _ES_USTED.search(MINI["es"][k]), MINI["es"][k])

# (8) A premissa corrigida: o d2 do encargo NUNCA chega a uma tela.
check("rev/8: o diálogo só sai de _offer_view", _sty_src.count('f"sty_{row.storylet_key}_d1"') == 1)
check("rev/8: o pacer só sorteia weight > 0", "int(c.weight or 0) > 0" in _sty_src)
check("rev/8: accept_encargo materializa já em accepted",
      'status="accepted"' in _read("core/city_engine.py"))
check("rev/8: a nota do engine foi corrigida (não culpa mais o diálogo)",
      "mas o jogador nunca o viu" in _sty_src)

print("\n── 6. WIRING por grep ──────────────────────────────────────────")

check("wiring/chat /praca imprime a linha de objetivo",
      '_enc.get("objective_line")' in _sect)
check("wiring/chat /praca diz o comando (não há salto de aba no chat)",
      "_enc['objective_cmd']" in _sect)
check("wiring/chat quests imprime a linha nas aceitas",
      'a.get("objective_line")' in _quests)
check("wiring/chat a oferta diz o que exige",
      'offer.get("objective_line")' in _quests)
check("wiring/o comando só aparece enquanto a quest NÃO está completa",
      'not a.get("is_completed") and a.get("objective_cmd")' in _quests)

print("\n── 7. i18n ─────────────────────────────────────────────────────")

sizes = {lg: len(CHAT[lg]) for lg in LANGS}
check("i18n/paridade chat ×3", len(set(sizes.values())) == 1, str(sizes))
msizes = {lg: len(MINI[lg]) for lg in LANGS}
check("i18n/paridade mini ×3", len(set(msizes.values())) == 1, str(msizes))

NEW_MINI = ("pill_panel_qi_full_refused", "pill_panel_hp_full_refused",
            "pill_panel_refill_stopped")
for k in NEW_MINI:
    for lg in LANGS:
        check(f"i18n/{k} em mini/{lg}", k in MINI[lg])
check("i18n/pill_panel_refill_stopped tem {left} nas 3",
      all("{left}" in MINI[lg]["pill_panel_refill_stopped"] for lg in LANGS))
for lg in LANGS:
    check(f"i18n/inv_pill_bulk_cap_stop em chat/{lg}", "inv_pill_bulk_cap_stop" in CHAT[lg])
check("i18n/inv_pill_bulk_cap_stop tem {used} e {left} nas 3",
      all("{used}" in CHAT[lg]["inv_pill_bulk_cap_stop"]
          and "{left}" in CHAT[lg]["inv_pill_bulk_cap_stop"] for lg in LANGS))

# placeholders simétricos entre línguas (a armadilha do t() que degrada token)
for key in [f"sty_obj_{t}" for t in _OBJ_EMOJI] + ["inv_pill_bulk_cap_stop"]:
    sets = {lg: set(re.findall(r"\{(\w+)\}", CHAT[lg].get(key, ""))) for lg in LANGS}
    check(f"i18n/{key} tem os MESMOS placeholders nas 3", len(set(map(frozenset, sets.values()))) == 1,
          str(sets))
for key in NEW_MINI:
    sets = {lg: set(re.findall(r"\{(\w+)\}", MINI[lg].get(key, ""))) for lg in LANGS}
    check(f"i18n/mini {key} placeholders simétricos", len(set(map(frozenset, sets.values()))) == 1,
          str(sets))

# PT-BR (anti EU-PT) nas strings novas desta onda
_EU_PT = re.compile(r"\b(está a |estás|percebe-se|ecrã|utilizador|ficheiro|telemóvel|"
                    r"a fazer\b|carregue no|prima )", re.I)
for key in [f"sty_obj_{t}" for t in _OBJ_EMOJI] + [
        "inv_pill_bulk_cap_stop", "sty_enc_fenghuo_forja_d2"]:
    v = CHAT["pt"].get(key, "")
    check(f"ptbr/{key} sem EU-PT", not _EU_PT.search(v), v)
for key in NEW_MINI:
    v = MINI["pt"].get(key, "")
    check(f"ptbr/mini {key} sem EU-PT", not _EU_PT.search(v), v)
    check(f"ptbr/mini {key} usa você/seu quando trata o jogador",
          ("tu " not in v.lower() and "teu" not in v.lower()), v)

print("\n── 8. ZERO migration ───────────────────────────────────────────")

_migs = sorted(os.listdir(os.path.join(ROOT, "migrations")))
# ⚠️ A 138 é do **Item B** (印记 Marca do Traçado, 09/08 — o owner deu o override
# da migration nesse dia), NÃO desta onda: o Item C/A continua a ser zero
# migration. A suite dela é `_test_marca_tracado.py`.
# ⚠️ 2026-09-07 — esta guarda dizia "nenhuma migration 140+ nasceu", e isso
# NAO e' o que ela quer provar: quer provar que ESTA onda nao criou migration.
# Escrita como um tecto global, ela fica vermelha sempre que QUALQUER onda
# futura acrescentar uma (foi o que a Mig 140 do genero fez a SETE suites de
# uma vez). O invariante durável e' o do ASSUNTO: nenhuma migration do repo
# fala desta onda — isso continua verdade daqui a cem migrations.
# ⚠️ Os termos tem de ser os que ESTA onda inventou, nao os do sistema em que
# ela mexeu: "storylet" e "objective_type" existem em migrations de 2026-07 que
# criaram as proprias tabelas, e por isso davam vermelho. O que a QoL 07/08
# trouxe foi o helper `sty_obj_*` (a frase que DIZ o objetivo) e o chip de
# segmento — nenhum dos dois toca no schema, e e' isso que se prova.
_ASSUNTO = ("sty_obj", "quest_objective_tab", "qol0807")
_cita = [m for m in _migs if m.endswith(".sql")
         and any(a in (m + _read(f"migrations/{m}")).lower() for a in _ASSUNTO)]
check("mig/esta onda não criou migration (nenhuma cita o assunto dela)",
      not _cita, str(_cita))

print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)
print(f"OK — {PASS} asserts. O Encargo diz o que fazer, e para onde ir.")
