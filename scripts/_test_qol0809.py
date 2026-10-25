# -*- coding: utf-8 -*-
"""QoL-Feedback 09/08 — Item D (renascer no lugar errado) + Item E (mapa torto).

Reports do [jogador] de 08/08 22:07 e 22:23. Molde: `scripts/_test_qol0807.py`.
Standalone, ZERO base de dados:

    python -X utf8 scripts/_test_qol0809.py

Cobre, por secção:
  1. OFF-identity — com `dungeons_regionais` OFF nada muda (main byte-idêntica)
  2. A GEOGRAFIA medida nas seeds — a armadilha existe e o número está certo
  3. O helper do aviso — régua partilhada, plain text, fail-safe
  4. A lista vazia que MENTIA — as 2 superfícies trocam a frase pela verdade
  5. O aviso ANTES do tap — as 2 superfícies, e o gate final do mini
  6. Item E — o desalinhamento do mapa (flex/grid), e o que NÃO era o defeito
  7. i18n — paridade ×3 ×2, placeholders simétricos, PT-BR (anti EU-PT)
  8. ZERO migration, ZERO flag nova
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


import asyncio as _aio

import core.dungeon_regions as dreg
from core.continent_engine import CONTINENT_KEYS
from database.seeds.dungeon_seeds import DUNGEON_SEEDS

LANGS = ("pt", "en", "es")
CHAT = {lg: json.loads(_read(f"locales/{lg}.json")) for lg in LANGS}
MINI = {lg: json.loads(_read(f"miniapp/i18n/{lg}.json")) for lg in LANGS}
_tabs = _read("miniapp/components/tabs.js")
_dng_h = _read("handlers/dungeons.py")
_prst_h = _read("handlers/prestige.py")
_web = _read("core/webserver.py")
_dreg_src = _read("core/dungeon_regions.py")
_prst_e = _read("core/prestige_engine.py")


class _FakeDungeon:
    def __init__(self, cont, min_realm):
        self.continent, self.min_realm = cont, min_realm


class _FakePlayer:
    telegram_id = 1

    def __init__(self, cont):
        self.current_continent = cont


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Devolve sempre o catálogo inteiro — é o que `rebirth_portal_warning`
    pede (o filtro é feito em Python, com a MESMA régua da lista)."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


SEED_DUNGEONS = [
    _FakeDungeon(s.get("continent"), int(s.get("min_realm") or 0))
    for s in DUNGEON_SEEDS
]


def _warn(cont, lang="pt", rows=None):
    return _aio.run(dreg.rebirth_portal_warning(
        _FakeSession(SEED_DUNGEONS if rows is None else rows),
        _FakePlayer(cont), lang,
    ))


print("\n── 1. OFF-identity ─────────────────────────────────────────────")

_ORIG_ON = dreg.regionais_on
dreg.regionais_on = lambda *a, **k: False
check("off/o aviso é VAZIO com dungeons_regionais OFF (main intocada)",
      _warn("moyu") == "", repr(_warn("moyu")))
check("off/o gate da flag é a PRIMEIRA coisa do helper",
      "if not regionais_on():" in inspect.getsource(dreg.rebirth_portal_warning))
check("off/elsewhere_summary continua vazio com a flag OFF",
      dreg.elsewhere_summary(SEED_DUNGEONS, _FakePlayer("moyu")) == [])
dreg.regionais_on = _ORIG_ON

# A frase da lista vazia só troca quando HÁ portais além do horizonte — com a
# flag OFF `_dng_elsewhere` é [] e a chave antiga volta, byte-idêntica.
check("off/a chave antiga continua a ser o ramo `else` explícito",
      'else:\n                _empty = t(lang, "dng_empty_category"' in _dng_h)
check("off/mini: a chave antiga é o ramo `else` explícito",
      't("dungeon_no_in_category")' in _tabs
      and 'elsewhere.length > 0 ? t("dungeon_no_here_elsewhere")' in _tabs)

print("\n── 2. A geografia medida nas SEEDS ─────────────────────────────")

# O report do [jogador] não era hipótese: as masmorras de reino baixo não existem
# nos continentes distantes. Este bloco fixa os números — se uma seed mudar,
# a spec do aviso muda com ela e o teste avisa.
def _first_realm(cont):
    ms = [d.min_realm for d in SEED_DUNGEONS if d.continent == cont]
    return min(ms) if ms else None


check("geo/todo continente canónico tem pelo menos 1 portal",
      all(_first_realm(c) is not None for c in CONTINENT_KEYS),
      str({c: _first_realm(c) for c in CONTINENT_KEYS}))
check("geo/Línghé abre no reino 0 (o berço)", _first_realm("linghe") == 0)
check("geo/Yǎnshān abre no reino 0", _first_realm("yanshan") == 0)
check("geo/Qiānhé só abre no reino 1", _first_realm("qianhe") == 1)
check("geo/Fēnghuǒ só abre no reino 3 (o report)", _first_realm("fenghuo") == 3)
check("geo/Mòyǔ só abre no reino 5 (o pior caso do report)",
      _first_realm("moyu") == 5)
check("geo/as 23 masmorras continuam ancoradas",
      all(d.continent for d in SEED_DUNGEONS) and len(SEED_DUNGEONS) == 23,
      str(len(SEED_DUNGEONS)))

# ⚠️ A peça em que o [jogador] se ENGANA, e que a resposta corrige: Essência de
# Núcleo NÃO vem de masmorra — vem de meditar no reino 2. Se alguém um dia
# ligar core_essence a um drop de masmorra, a resposta ao jogador passa a
# mentir e este assert cai.
_gl = _read("core/game_logic.py")
check("geo/core_essence é faucet de MEDITAÇÃO (a resposta ao [jogador] depende disto)",
      "core_essence" in _gl)
check("geo/nenhuma seed de masmorra dropa core_essence",
      "core_essence" not in _read("database/seeds/dungeon_seeds.py"))

print("\n── 3. O helper do aviso ────────────────────────────────────────")

# A flag ON é o mundo de LAUNCH (em main ela nasce OFF e a secção 1 provou que
# aí nada muda). Sem DB, `regionais_on()` degrada a False por desenho — ligá-la
# à mão é a única forma de exercitar o caminho que o jogador do s2 vai ver.
dreg.regionais_on = lambda *a, **k: True

check("aviso/rebirth_portal_warning é async (lê o catálogo)",
      inspect.iscoroutinefunction(dreg.rebirth_portal_warning))
check("aviso/Línghé (reino 0 disponível) não diz nada", _warn("linghe") == "",
      repr(_warn("linghe")))
check("aviso/Yǎnshān não diz nada", _warn("yanshan") == "", repr(_warn("yanshan")))
_w_moyu = _warn("moyu")
check("aviso/Mòyǔ AVISA", bool(_w_moyu), repr(_w_moyu))
check("aviso/Mòyǔ diz o reino 5", "5" in _w_moyu, _w_moyu)
check("aviso/Mòyǔ diz o NOME do continente", "Mòyǔ" in _w_moyu, _w_moyu)
_w_fh = _warn("fenghuo")
check("aviso/Fēnghuǒ avisa e diz o reino 3", _w_fh and "3" in _w_fh, _w_fh)
check("aviso/Qiānhé avisa (reino 1 também é armadilha, só que curta)",
      bool(_warn("qianhe")), repr(_warn("qianhe")))

# ⚠️ Lição "string dual-surface = plain text": o chat manda isto dentro de uma
# mensagem `parse_mode="Markdown"`. Um `*` ou `_` solto parte a mensagem
# INTEIRA do renascimento — o ecrã mais irreversível do jogo. Varre-se o
# CARTESIANO (todo continente × toda língua), não uma amostra: o nome do
# continente entra na frase e é ele que pode trazer o caractere solto.
for cont in CONTINENT_KEYS:
    for lg in LANGS:
        v = _warn(cont, lg) or _warn(cont, lg, rows=[])
        check(f"aviso/{cont}/{lg}: sem markdown solto (o chat renderiza Markdown)",
              not re.search(r"[*_`\[\]]", v), v)

# Fail-safe: nada aqui pode derrubar o /renascer.
check("aviso/uma sessão que explode degrada a string vazia",
      _aio.run(dreg.rebirth_portal_warning(object(), _FakePlayer("moyu"), "pt")) == "")
check("aviso/catálogo vazio usa a key do 'nenhum portal aqui'",
      _warn("moyu", "pt", rows=[]) == CHAT["pt"]["prestige_warn_no_portal_here"].format(
          emoji="🌑", name=CHAT["pt"]["continent_moyu"]),
      _warn("moyu", "pt", rows=[]))
check("aviso/um portal NÃO-ancorado (continent NULL) desarma a armadilha",
      _warn("moyu", "pt", rows=SEED_DUNGEONS + [_FakeDungeon(None, 0)]) == "")
check("aviso/continente inválido cai no fallback linghe (nunca crasha)",
      _warn("terra_do_nunca") == "", repr(_warn("terra_do_nunca")))

# A régua é PARTILHADA — reimplementar o filtro aqui era o caminho para as
# duas telas discordarem (o padrão que a casa já pagou 3 vezes).
_h_src = inspect.getsource(dreg.rebirth_portal_warning)
check("aviso/reusa dungeon_visible_here (uma verdade de geografia)",
      "dungeon_visible_here(d, player)" in _h_src)
check("aviso/não reimplementa o filtro de continente",
      "== cont" not in _h_src and ".continent ==" not in _h_src)

dreg.regionais_on = _ORIG_ON

print("\n── 4. A lista vazia que MENTIA ─────────────────────────────────")

check("lista/chat: a frase troca quando há portais além do horizonte",
      'if _dng_elsewhere:\n                _empty = t(lang, "dng_empty_here_elsewhere"' in _dng_h)
check("lista/chat: a troca acontece DEPOIS de _dng_elsewhere ser calculado",
      _dng_h.index("_dng_elsewhere = elsewhere_summary(") < _dng_h.index('_empty = t(lang, "dng_empty_here_elsewhere"'))
check("lista/chat: o bloco 'Além do horizonte' continua a seguir à frase",
      _dng_h.index('_empty = t(lang, "dng_empty_here_elsewhere"')
      < _dng_h.index('t(lang, "dng_elsewhere_header")'))
# O fallback de cada ramo tem de ser o DELE — herdar o fallback antigo era
# reintroduzir a mentira pela porta dos fundos se a key faltasse.
check("lista/chat: cada ramo tem o SEU fallback",
      'fallback="No portal of this realm range opens on this continent."' in _dng_h
      and 'fallback="No dungeons discovered in this realm yet."' in _dng_h)

# ⚠️ A frase afirma que "os que existem ficam do outro lado do mar". No mini o
# bloco `elsewhere` é GLOBAL (o MV-9 §P6 fez questão: nenhum portal sem nome),
# enquanto no chat é por categoria. Isso só é honesto enquanto TODA faixa de
# reinos existir em mais de um continente. Se uma seed futura criar uma faixa
# que só existe no continente do jogador, a frase passa a mentir — e cai aqui.
_BANDS = ((0, 2), (3, 5), (6, 8), (9, 10))
for _lo, _hi in _BANDS:
    _conts = {d.continent for d in SEED_DUNGEONS if _lo <= d.min_realm <= _hi}
    check(f"lista/a faixa {_lo}-{_hi} existe em 2+ continentes (a frase não mente)",
          len(_conts) >= 2, str(_conts))
check("lista/mini: a frase troca pelo mesmo critério",
      'elsewhere.length > 0 ? t("dungeon_no_here_elsewhere") : t("dungeon_no_in_category")'
      in _tabs)
check("lista/mini: `elsewhere` já existia no scope do render",
      "const elsewhere = (regional && regional.elsewhere) || [];" in _tabs)
for lg in LANGS:
    v = CHAT[lg]["dng_empty_here_elsewhere"]
    check(f"lista/{lg}: a frase nova não tem markdown (vai dentro de _itálico_)",
          not re.search(r"[*_`]", v), v)

print("\n── 5. O aviso ANTES do tap ─────────────────────────────────────")

# O ponto todo do item: renascer é irreversível e não muda o continente.
check("tap/o engine continua SEM tocar no continente (a premissa do aviso)",
      "current_continent" not in _prst_e)
check("tap/o engine continua a zerar o realm", "player.realm = 0" in _prst_e)

check("tap/chat: o /renascer chama o helper",
      "from core.dungeon_regions import rebirth_portal_warning" in _prst_h
      and "await rebirth_portal_warning(session, player, lang)" in _prst_h)
_ren = _prst_h.split("async def renascer_command(")[1].split("\nasync def ")[0]
check("tap/chat: o aviso é a ÚLTIMA linha do texto (antes dos botões)",
      0 < _ren.find("_geo_warn") < _ren.find("btn_cancel"))
check("tap/chat: o aviso entra depois do bloco 'sem técnicas'",
      _ren.find("prestige_no_techs_retained") < _ren.find("_geo_warn"))
check("tap/chat: nada é enviado quando o helper devolve vazio",
      "if _geo_warn:" in _ren)

check("tap/mini: o preview resolve o aviso no SERVIDOR",
      "rebirth_portal_warning as _reb_warn" in _web
      and "portal_warning = await _reb_warn(session, player, lang)" in _web)
# ⚠️ Key CONDICIONAL, não sempre-presente: "payload key sempre-presente =
# OFF-identity quebrada" (lição MV-7). Com a flag OFF o preview de main sai
# byte-idêntico ao de ontem.
check("tap/mini: a key do aviso é CONDICIONAL (OFF-identity do payload)",
      '**({"portal_warning": portal_warning} if portal_warning else {}),' in _web)
check("tap/mini: a key NUNCA é emitida incondicionalmente",
      '\n        "portal_warning": portal_warning,' not in _web)
# O payload é montado FORA do `async with` — calcular lá dentro é obrigatório.
_prev = _web.split("async def api_rebirth_preview(")[1].split("\nasync def ")[0]
check("tap/mini: o aviso é calculado DENTRO da sessão",
      0 < _prev.find("portal_warning = await _reb_warn") < _prev.find('"ok": True,'))
check("tap/mini: o painel desenha o aviso", "{data.portal_warning && (" in _tabs)
check("tap/mini: o aviso aparece DUAS vezes (preview + gate final)",
      _tabs.count("{data.portal_warning && (") == 2)
_reb_modal = _tabs.split("function RebirthModal(")[1].split("\n    function ")[0]
check("tap/mini: o gate 'really?' repete o aviso",
      0 < _reb_modal.find('phase === "confirm"')
      < _reb_modal.rfind("{data.portal_warning && ("))
check("tap/mini: o cliente NÃO recalcula geografia (nenhuma tela recalcula)",
      "moyu" not in _reb_modal and "min_realm" not in _reb_modal)

print("\n── 6. Item E — o mapa torto ────────────────────────────────────")

_doors = _tabs.split('{isleSites(isle).map(s => (')[1].split("</div>")[0]
check("mapa/a grelha das portas usa minmax(0,1fr)",
      'gridTemplateColumns:"minmax(0,1fr) minmax(0,1fr)"' in _tabs)
check("mapa/a grelha das portas já NÃO usa 1fr cru",
      '{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>\n                        {isleSites'
      not in _tabs)
check("mapa/a porta é item de grelha com minWidth:0",
      'minWidth:0, overflow:"hidden",' in _doors)
check("mapa/o ícone da porta não encolhe",
      'fontSize:17, lineHeight:1, flexShrink:0 }}>{s.ico}' in _doors)
check("mapa/o NOME da porta pode encolher (o ellipsis passa a disparar)",
      'minWidth:0, textOverflow:"ellipsis", whiteSpace:"nowrap"' in _doors)
check("mapa/o badge ⛵ da cidade não encolhe (MV-9, a gota que transbordou)",
      'flexShrink:0, whiteSpace:"nowrap"' in _doors)
# ⚠️ 2026-09-15 — RE-APONTADA. O botão de viajar saiu da grelha e ganhou dono
# próprio (`botaoViajar`), porque com a cena do mapa ele passa a ser uma faixa
# de largura toda — e porque escrevê-lo duas vezes fazia a catraca do emoji
# subir (o `⛵` em dois ramos). O `minWidth:0` continua a ser obrigatório: é o
# fix de 09/08 que impede a faixa de transbordar em meio telemóvel. Segue-se a
# indirecção; não se apaga o assert.
_viajar = _tabs.split("const botaoViajar")[1].split("</button>")[0] \
    if "const botaoViajar" in _tabs else ""
check("mapa/o localizador achou o botão de viajar pelo nome do dono",
      len(_viajar) > 200, f"{len(_viajar)} chars")
check("mapa/o botão de viajar também ganhou minWidth:0",
      'minWidth:0, fontSize:12.5, fontWeight:700,' in _viajar)
check("mapa/o ⛵ do botão de viajar tem UM dono só (catraca do emoji)",
      _tabs.count("const botaoViajar") == 1)
# Nenhum dos três filhos da PORTA pode ficar sem regra: 1 encolhível (o nome,
# que ganha o ellipsis) + 2 fixos (o ícone e o badge da cidade). `_doors` cobre
# também o botão de viajar, por isso a contagem é feita só na porta.
_door_btn = _doors.split("))}")[0]
check("mapa/a porta tem exatamente 1 filho encolhível e 2 flexShrink:0",
      _door_btn.count("flexShrink:0") == 2
      and _door_btn.count('textOverflow:"ellipsis"') == 1,
      f'shrink0={_door_btn.count("flexShrink:0")}')

# ⚠️ O segundo suspeito do relatório NÃO se confirma, e o teste fixa o porquê:
# o cabeçalho da ilha é `flexDirection:"column"`, logo as pílulas EMPILHAM —
# não competem por largura. Se alguém um dia o passar a `row`, isto cai e o
# fix (flexWrap) volta à mesa.
_hdr = _tabs.split('aria-expanded={open}')[1].split("</button>")[0]
check("mapa/o cabeçalho da ilha é coluna (as pílulas empilham, não transbordam)",
      'flexDirection:"column"' in _hdr, _hdr[:200])
# O TravelModal — o outro candidato do report — já estava são.
_trv = _tabs.split("function TravelModal(")[1].split("\n    function ")[0]
check("mapa/TravelModal já protegia o corpo com flex:1+minWidth:0",
      'flex:1, minWidth:0' in _trv)
check("mapa/TravelModal já protegia o emoji com flexShrink:0",
      'fontSize:24, flexShrink:0' in _trv)

print("\n── 7. i18n ─────────────────────────────────────────────────────")

NEW_CHAT = ("dng_empty_here_elsewhere", "prestige_warn_no_low_portal",
            "prestige_warn_no_portal_here")
NEW_MINI = ("dungeon_no_here_elsewhere",)

sizes = {lg: len(CHAT[lg]) for lg in LANGS}
check("i18n/paridade chat ×3", len(set(sizes.values())) == 1, str(sizes))
msizes = {lg: len(MINI[lg]) for lg in LANGS}
check("i18n/paridade mini ×3", len(set(msizes.values())) == 1, str(msizes))

for k in NEW_CHAT:
    for lg in LANGS:
        check(f"i18n/{k} em chat/{lg}", k in CHAT[lg])
for k in NEW_MINI:
    for lg in LANGS:
        check(f"i18n/{k} em mini/{lg}", k in MINI[lg])

for k in NEW_CHAT:
    sets = {lg: set(re.findall(r"\{(\w+)\}", CHAT[lg].get(k, ""))) for lg in LANGS}
    check(f"i18n/{k} tem os MESMOS placeholders nas 3",
          len(set(map(frozenset, sets.values()))) == 1, str(sets))
for k in NEW_MINI:
    sets = {lg: set(re.findall(r"\{(\w+)\}", MINI[lg].get(k, ""))) for lg in LANGS}
    check(f"i18n/mini {k} placeholders simétricos",
          len(set(map(frozenset, sets.values()))) == 1, str(sets))

check("i18n/prestige_warn_no_low_portal tem emoji+name+realm nas 3",
      all({"emoji", "name", "realm"} == set(
          re.findall(r"\{(\w+)\}", CHAT[lg]["prestige_warn_no_low_portal"]))
          for lg in LANGS))
check("i18n/prestige_warn_no_portal_here NÃO tem {realm} (não há reino a citar)",
      all("{realm}" not in CHAT[lg]["prestige_warn_no_portal_here"] for lg in LANGS))
check("i18n/a frase da lista vazia não tem placeholder nenhum",
      all(not re.search(r"\{\w+\}", CHAT[lg]["dng_empty_here_elsewhere"]) for lg in LANGS)
      and all(not re.search(r"\{\w+\}", MINI[lg]["dungeon_no_here_elsewhere"])
              for lg in LANGS))
check("i18n/chat e mini dizem a MESMA coisa na lista vazia (paridade de sentido)",
      CHAT["pt"]["dng_empty_here_elsewhere"] == MINI["pt"]["dungeon_no_here_elsewhere"])

# PT-BR (anti EU-PT) nas strings novas desta onda
_EU_PT = re.compile(r"\b(está a |estás|percebe-se|ecrã|utilizador|ficheiro|telemóvel|"
                    r"a fazer\b|carregue no|prima |viaje para o teu)", re.I)
for k in NEW_CHAT:
    v = CHAT["pt"][k]
    check(f"ptbr/{k} sem EU-PT", not _EU_PT.search(v), v)
    check(f"ptbr/{k} trata por você (nunca tu/teu)",
          " tu " not in f" {v.lower()} " and "teu" not in v.lower(), v)
for k in NEW_MINI:
    v = MINI["pt"][k]
    check(f"ptbr/mini {k} sem EU-PT", not _EU_PT.search(v), v)

# ES: os painéis tratam por "tú" — as strings novas não podem estrear "usted".
_ES_USTED = re.compile(r"\b(Usted|usted|Su renacer|Considere\b)")
for k in NEW_CHAT:
    check(f"es/{k} trata por tú", not _ES_USTED.search(CHAT["es"][k]), CHAT["es"][k])

print("\n── 8. ZERO migration · ZERO flag nova ──────────────────────────")

_migs = sorted(os.listdir(os.path.join(ROOT, "migrations")))
# ⚠️ A 138 é do **Item B** (印记 Marca do Traçado), que o owner destravou no
# mesmo dia — os Itens D e E continuam a ser zero migration e zero flag nova.
# ⚠️ 2026-09-07 — ver a nota igual nas outras suites: o tecto global ("nenhuma
# migration 140+") ficava vermelho por causa de ondas ALHEIAS. O invariante
# que interessa e' o do ASSUNTO.
_ASSUNTO = ("renascer", "rebirth_notice", "trv_", "qol0809")
_cita = [m for m in _migs if m.endswith(".sql")
         and any(a in (m + _read(f"migrations/{m}")).lower() for a in _ASSUNTO)]
check("mig/os itens D+E não criaram migration (nenhuma cita o assunto)",
      not _cita, str(_cita))
_db = _read("database/db.py")
check("flag/D+E não criaram flag (correm sob dungeons_regionais, que já existe)",
      '"dungeons_regionais"' in _db)
check("flag/o aviso e a lista lêem `dungeons_regionais`, nunca a flag do Item B",
      "marca_do_tracado" not in _dreg_src and "marca_do_tracado" not in _dng_h)
# Item B saiu na mesma sessão, com suite PRÓPRIA — este assert só garante que
# ele existe de facto, para o leitor não procurar o que já shipou.
_models = _read("database/models.py")
_pf = _models.split("class PlayerFormation(Base):")[1].split("\nclass ")[0]
check("B/o Item B shipou: player_formations ganhou o contador (ver _test_marca_tracado.py)",
      "body_uses" in _pf)

print(f"\n{PASS} passed · {len(FAIL)} failed")
if FAIL:
    print("\nFALHAS:")
    for f in FAIL:
        print("  ·", f)
    sys.exit(1)
print(f"OK — {PASS} asserts. O renascimento avisa, e o mapa cabe no ecrã.")
