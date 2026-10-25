# -*- coding: utf-8 -*-
"""Servir o mini-app REAL para OLHAR para ele. (WEB-D §1, 2026-09-01)

Porque isto existe
------------------
A WEB-C construiu o trilho de desktop, cobriu-o de testes e **nunca o viu**: o
harness que montava o `SideRail` isolado saiu branco, e a suspeita registada foi
"o React do unpkg nao carrega". Estava errada — **medido a 2026-09-01, o React do
unpkg carrega sem problema; o que nao funciona e' o contexto `file://`.**

Servir o jogo a serio pelo `main.py` exige o Postgres de producao, que nao se
toca. Este servidor e' o meio-termo honesto: os ficheiros `index.html`,
`ui.js`, `tabs.js`, `app.js` e a i18n sao os de **producao, byte a byte**,
servidos por HTTP real. So a API e' encenada.

Dez minutos a olhar por aqui encontraram duas feridas que nenhum teste apanhava:
o trilho escondia 8 destinos a 1280x720 e os cartoes da Home viravam quadrados
de 514x514 no desktop. Ver o que o utilizador ve nao e' um extra do processo.

Uso
---
    python scripts/_dev_serve_miniapp.py [porta]           # default 8899
    NV_FEATURES=pele_quente,superficie_desktop python scripts/_dev_serve_miniapp.py
    NV_STATE=idle|ceiling python scripts/_dev_serve_miniapp.py   # os outros estados da tela

    # noutro terminal (o `open` demora ~2 min na 1a vez):
    agent-browser set viewport 1280 720
    agent-browser open http://127.0.0.1:8899/app
    agent-browser screenshot look.png

⚠️ NAO e' um servidor de producao e nao fala com base de dados nenhuma. Nao
importar isto de lado nenhum do jogo.

⚠️ O payload encenado nao substitui o servidor: serve para ver LAYOUT, COR e
NAVEGACAO. Regras, gates e numeros continuam a ser verificados pelas suites.
"""
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 🎒 3.2 — NV_CLIENTE=<pasta> serve o CLIENTE (index.html, componentes, dist,
# i18n do ecra) de OUTRA arvore — p.ex. uma worktree de HEAD — contra os MESMOS
# dados encenados desta. E' a unica comparacao OFF honesta: o "antes" e o
# "depois" a desenhar o mesmo payload. A 29/09 compararam-se dois arneses, cada
# um com o seu mock, e ai' so' se pode comparar estrutura.
CLIENT_ROOT = os.path.abspath(os.environ.get("NV_CLIENTE") or ROOT)

# `superficie_desktop` liga por defeito porque a razao de este ficheiro existir
# e' olhar para a superficie larga. Tudo o resto so' com NV_FEATURES.
FEATURES = {"superficie_desktop": True}
# 圖 2026-09-11 — `NV_NO_DESKTOP=1` desliga o trilho.
# ⚠️ Nao e' um capricho: `superficie_desktop` esta' OFF em TODO mundo, portanto
# um ecra largo hoje ve' a barra de TELEMOVEL, e e' essa a unica configuracao em
# que uma tela de hub (e logo a cena do mapa) renderiza a 1440. Sem este
# interruptor eu estaria a julgar a superficie larga por uma tela que ela nunca
# mostra.
if (os.environ.get("NV_NO_DESKTOP") or "").strip() not in ("", "0"):
    FEATURES.pop("superficie_desktop", None)
for _k in (os.environ.get("NV_FEATURES") or "").split(","):
    _k = _k.strip()
    if _k:
        FEATURES[_k] = True

# ── Estados encenaveis (WEB-E) ───────────────────────────────────────────────
# Uma tela tem MAIS DO QUE UM estado, e olhar so' para o feliz e' como testar so'
# o caminho verde. NV_STATE escolhe qual se serve:
#   seated  (default) — a meditar, com tempo que CABE na linha (o valor antigo,
#                       ano 2100, imprimia "642820h 51m" e mentia sobre o layout)
#   idle              — de pe': a tela tem de OFERECER onde sentar
#   ceiling           — reino 10 camada 9: 21 dos 37 activos-30d do `main` (57%).
#                       `check_breakthrough` fixa a base no limiar e devolve None
#                       ⇒ encher a barra ali nao produz evento nenhum.
#   extremos          — 🔴 OS VALORES REAIS DA BASE DE PRODUCAO (medidos
#                       2026-09-15). Existem porque a onda 1 foi construida por
#                       causa deles e nenhum outro estado os mostra:
#                         current_hp ......... 158 977 287 826  (12 DIGITOS)
#                         cultivation_base ... 2 117 547 824    (10)
#                         cb_threshold ....... 970 422 834      (9 — JA PASSOU)
#                         qi / qi_capacity ... 1 370 315 / 1 263 799 (ACIMA)
#                         nome ............... 63 caracteres
#                       Um ensaio com numeros confortaveis prova nada sobre o
#                       layout que tem de aguentar estes.
import time as _time

STATE = (os.environ.get("NV_STATE") or "seated").strip().lower()
# NV_LANG=en|es — as tres linguas nao tem o mesmo comprimento, e um rotulo
# que cabe em PT pode partir a linha em EN/ES. Ver e' mais barato que adivinhar.
LANG = (os.environ.get("NV_LANG") or "pt").strip().lower()
_SEATED = STATE != "idle"
_CEILING = STATE == "ceiling"
_EXTREMOS = STATE == "extremos"
_MED_END_MS = int((_time.time() + 47 * 60) * 1000)  # 47 min — uma "Profunda" a meio

PLAYER = {
    "telegram_id": 123456789, "dao_name": "Chen Wuyan", "language": LANG,
    # 性 NV_GENDER=male|female|none — os TRES estados tem de ser olhados, e o
    # terceiro (None) e' o dos ~248 do beta, nao um caso de canto.
    "gender": (None if (os.environ.get("NV_GENDER") or "male").lower() in ("none", "null", "")
               else (os.environ.get("NV_GENDER") or "male").lower()),
    "realm": 3, "realm_name": "Núcleo Dourado", "realm_emoji": "🔮", "sub_layer": 4,
    # 🔴 2026-09-13 — ESTE CAMPO TINHA A FORMA ERRADA, e o custo so' apareceu
    # quando alguem OLHOU. "central" NAO e' uma chave de continente: o canon e'
    # `core/continent_engine.CONTINENT_META` = linghe/qianhe/yanshan/fenghuo/moyu.
    # Com um valor invalido, `isle.key === current` era falso para as CINCO
    # ilhas — o badge "📍 Voce esta' aqui" nunca renderizava aqui, e a cena do
    # Mundo saiu com os cinco continentes APAGADOS. O codigo estava certo; o
    # arnes e' que mentia, pela terceira vez em tres lotes.
    # (Regra da skill: *"um mock com a forma errada e' uma mentira dita no
    # codigo certo"*. NV_CONTINENT troca-o, para se poder ver o outro ramo.)
    "current_continent": (os.environ.get("NV_CONTINENT") or "linghe").strip().lower(),
    "current_continent_emoji": "🏔️",
    "current_continent_name": "Línghé", "home_continent": "linghe",
    "is_traveling": False,
    "path": "righteous", "path_raw": "righteous", "path_emoji": "☯️",
    "path_name": "Caminho Justo",
    "path_meta_resolved": {"emoji": "☯️", "name": "Caminho Justo", "key": "righteous"},
    "path_can_pick": False, "path_gate_realm": 2,
    "karma": 340, "karma_label": "Virtuoso", "karma_label_key": "karma_band_virtuous",
    "karma_emoji": "🕊️", "karma_band": "virtuous", "karma_chip_visible": True,
    "karma_diverged": False,
    "sect_id": 3, "sect_emoji": "🏯", "sect_name": "Palácio da Neve Eterna",
    "sect_rank": 3, "sect_rank_key": "sect_rank_inner", "sect_chip_visible": True,
    "sect_master_name": "Anciã Bai Ling", "sect_contribution": 1420,
    "cultivation_base": 184000.0, "cb_threshold": 320000.0,
    "qi": 4120.0, "qi_capacity": 6800.0,
    "spirit_root": "Raiz de Gelo Celestial", "spirit_root_emoji": "❄️",
    # ⚠️ WEB-E 2026-09-02: estes 4 blocos estavam com uma FORMA INVENTADA e a tela
    # desenhava "undefined: undefined anos" / "Dao Heart Tier Undefined". Um mock
    # e' honesto quando o CODIGO e' o de producao — mas se o PAYLOAD tiver outra
    # forma, olha-se para uma mentira. As chaves abaixo sao as que os
    # `project_*_for_display` devolvem de verdade (root_engine / lifespan_engine /
    # mind_sea_engine / dao_heart_engine). Mudar um engine ⇒ mudar aqui tambem.
    "root_elements": {"elements": [{"key": "water", "emoji": "💧", "rare": False},
                                   {"key": "metal", "emoji": "⚔️", "rare": False}],
                      "base_count": 2, "has_variant": False,
                      "is_single": False, "is_penta": False, "archetype": "dual"},
    "lifespan": {"realm": 3, "realm_name": "Golden Core", "ceiling": 500,
                 "is_immortal": False, "next_realm": 4,
                 "next_realm_name": "Nascent Soul", "next_ceiling": 1000,
                 "next_is_immortal": False, "age_years": 68, "bonus_years": 0},
    "mind_sea": {"tier": "deep", "tier_emoji": "🌊", "depth": 964,
                 "soul": 118, "perception": 96, "realm": 3},
    "dao_heart": {"tendency": "righteous", "is_crystallized": True,
                  "firmeza": "firm", "firmeza_emoji": "🛡️",
                  "heart_demon_near": False,
                  "tendency_variant": "tendency", "demon_variant": "demon"},
    "race": None, "body_cultivation": None, "profession_view": None,
    "spirit_stones": 184320, "spirit_jade": 412, "celestial_fragments": 23,
    "world_key": "s2", "is_admin": True,
    "manifest": {"realm": "mortal", "features": FEATURES},
    "battle_power": 48200, "soul_strength": 118, "perception": 96, "luck": 41,
    "display_combat_power": None, "current_hp": None, "max_hp": 21400.0,
    "is_meditating": True, "meditation_type": "deep",
    "meditation_end_ms": 4102444800000, "meditation_multiplier": 1.8,
    "prestige_level": 1, "prestige_points": 3, "active_title": None,
    "unlocked_titles": [],
    "foundation_quality": "flawless", "foundation_mult": 1.35,
    "core_quality": "superior", "foundation_locked": True, "core_locked": True,
    "core_essence": 12, "body_tempering_level": 4,
    "sect": {"id": 7, "name": "Seita do Vento Errante", "role": "elder",
             "level": 4, "members": 12},
    "tutorial_seen": True,
}

# ⚠️ O CATALOGO SAI DO `config.py`, importado. Escreve-lo aqui a mao seria
# fabricar exactamente o defeito que a onda 1 foi corrigir: uma segunda lista
# de modalidades, com outro dono, a divergir em silencio.
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.webserver import _meditation_catalog as _mc
    MED_CATALOG = _mc()
except Exception as _e:  # o encenador nunca rebenta por causa de um import
    print("[dev_serve] catalogo indisponivel (%s) — a tela mostra a"
          " recuperacao de dados, que E um estado legitimo" % _e)
    MED_CATALOG = []

CULTIVATION = {
    "is_meditating": _SEATED, "meditation_type": "deep" if _SEATED else None,
    "meditation_end_ms": _MED_END_MS if _SEATED else None,
    "meditation_multiplier": 1.8 if _SEATED else 1.0,
    "qi": 4120.0, "qi_capacity": 6800.0,
    "cultivation_base": 184000.0, "cb_threshold": 320000.0,
    "realm": 10 if _CEILING else 3, "sub_layer": 9 if _CEILING else 4,
    "qi_per_hour": 380.0,
    "can_breakthrough": False, "techniques": [], "buffs": [],
    "meditation_catalog": MED_CATALOG,
}

# 🔴 OS EXTREMOS. Aplicados DEPOIS do dicionario base para a diferenca ficar
# a' vista numa leitura so', e para nenhum outro estado os herdar por engano.
if _EXTREMOS:
    CULTIVATION["qi"] = 1370315.0
    CULTIVATION["qi_capacity"] = 1263799.0
    CULTIVATION["cultivation_base"] = 2117547824.0
    CULTIVATION["cb_threshold"] = 970422834.0
    CULTIVATION["realm"] = 10
    CULTIVATION["sub_layer"] = 9

# o PLAYER tem de concordar com a CULTIVATION — as duas metades da mesma tela
PLAYER["is_meditating"] = CULTIVATION["is_meditating"]
PLAYER["meditation_type"] = CULTIVATION["meditation_type"]
PLAYER["meditation_end_ms"] = CULTIVATION["meditation_end_ms"]
PLAYER["meditation_multiplier"] = CULTIVATION["meditation_multiplier"]
PLAYER["realm"] = CULTIVATION["realm"]
PLAYER["sub_layer"] = CULTIVATION["sub_layer"]
if _EXTREMOS:
    # ⚠️ `current_hp` leva o valor MEDIDO e nao `None`: o estado
    # "NULL = cheio" ja' e' o default dos outros, e o que falta VER e' a
    # linha com doze digitos la' dentro.
    PLAYER["current_hp"] = 158977287826.0
    PLAYER["max_hp"] = 216480119540.0
    PLAYER["qi"] = CULTIVATION["qi"]
    PLAYER["qi_capacity"] = CULTIVATION["qi_capacity"]
    PLAYER["cultivation_base"] = CULTIVATION["cultivation_base"]
    PLAYER["cb_threshold"] = CULTIVATION["cb_threshold"]
    # 63 caracteres — o maior nome medido em producao.
    PLAYER["dao_name"] = "Chen Wuyan, o Soberano do Vazio Devorador de Mil Estrelas Vivas"
if _CEILING:
    PLAYER["foundation_locked"] = False
    PLAYER["core_locked"] = False
    PLAYER["lifespan"]["realm"] = 10
    PLAYER["lifespan"]["is_immortal"] = True

HOME = {
    # ⚠️ 2026-09-14 — O MOCK TINHA A FORMA ERRADA e por isso nao mostrava nada:
    # "Serpente do Abismo Escarlate" nao e' nenhum dos 9 chefes do
    # `WORLD_BOSS_POOL`, e nao havia `art_key`. Servir isto era olhar para uma
    # tela que o jogo nunca desenha — 4a vez em 4 lotes que o ARNES, e nao o
    # produto, e' que estava a mentir. Agora e' um chefe REAL, com o nome ja'
    # traduzido (como o servidor manda) e a chave canonica ao lado.
    "boss": {"name": "Besta do Vazio", "art_key": "Void Beast",
             "emoji": "☯️", "tier": 3,
             "hp_pct": 62, "cooldown_remaining_ms": 0, "tier_mismatch": False},
    "quests": {"ready": 2, "total": 6},
    # 至 P3 — os dois atalhos, com a forma do servidor: `name` TRADUZIDO e
    # `art_key` CANONICO ao lado. Sem a segunda a arte nao e' encontrada.
    "atalhos": {
        "tecnica": {"name": "Mandato do Ceu", "art_key": "Heaven's Mandate",
                    "emoji": "⚔️", "mastery_level": 3},
        "arma": {"name": "Espada do Arbitro", "art_key": "Celestial Arbiter Sword",
                 "emoji": "🗡️", "grade": 7},
    },
    # 至 A CHEGADA (P2) — o `acao` que o `api_home_summary` passou a mandar.
    # ⚠️ A FORMA E' A DO SERVIDOR, byte a byte: `duelo` com `duel_id:null`
    # quando nao ha' (que E' uma resposta), e `avanco` com `eligible`+`blocker`.
    # NV_ACAO=duelo|avanco|nada escolhe o ramo que se quer OLHAR — sem isto
    # so' se ve' um dos cinco botoes e os outros quatro nunca sao vistos.
    "acao": {
        "duelo": ({"duel_id": "3f2a-mock", "state": "waiting_actions"}
                  if (os.environ.get("NV_ACAO") or "") == "duelo"
                  else {"duel_id": None, "state": None}),
        "avanco": {"eligible": (os.environ.get("NV_ACAO") or "") == "avanco",
                   "blocker": None},
    },
    "sect": {"id": 7, "name": "Seita do Vento Errante", "role": "elder",
             "level": 4, "members": 12, "contribution": 1420},
    "your_rank": 14, "spirit_jade": 412, "spirit_stones": 184320,
    "announcements": {"latest_id": 9, "recent_count": 2},
}


# ── 牌 A CARTA (2026-09-05) — os TRES conteudos da prova ─────────────────────
#
# ⚠️ "Um mock com a FORMA errada e' uma mentira contada no codigo certo" (WEB-E).
# As chaves abaixo nao sao inventadas: sao as que os handlers devolvem de
# verdade — `_build_combat_loadout_payload` (core/webserver.py), o bloco
# `tier_recipes` de `api_alchemy_recipes`, e `_serialize_owned` de
# `api_beasts_list`. Os NOMES, descricoes, graus e emojis vem dos seeds
# (`database/seeds/{combat,alchemy,beasts}_seeds.py`), porque o comprimento
# real do texto e' metade do que se esta' a julgar numa carta de 158px.
#
# Estao ca' os cinco graus da tecnica (common → celestial), quatro degraus da
# pilula e postos de besta nas duas pontas da escala de SETE — e' a unica forma
# de ver se o lombo contado le' bem escalas de comprimentos diferentes lado a
# lado.

# 🔴 A FORMA TEM DE SER A DE PRODUCAO, OU OLHAR NAO PROVA NADA.
# Ate' 2026-09-23 este construtor mandava o nome CANONICO em ingles e nenhum
# `art_key` — e assim a arte era encontrada PELO NOME, no mock, exactamente onde
# o servidor a serio a perdia. Ou seja: o arnes FABRICAVA o sucesso da avaria
# que este lote existe para corrigir (a 5a vez medida que ele mente antes do
# codigo). Agora imita o real: `name` TRADUZIDO (o `/app` do mock serve `pt`),
# `art_key` canonico ao lado, e `qi_cost` — sem ele a tira de preparo diria que
# a arte e' de graca.
def _tech(tid, name, emoji, ttype, grade, gmult, mlevel, memoji, mmult, xp, nxt,
          active, intent, desc, req_realm=1, nome_pt=None, qi_cost=25):
    return {
        "id": tid, "name": nome_pt or name, "art_key": name, "qi_cost": qi_cost,
        "emoji": emoji, "tech_type": ttype,
        "effect_type": "damage_mult", "effect_value": 0.5, "effect_round": 0,
        "req_realm": req_realm, "description": desc, "is_active": active,
        "grade": grade, "grade_emoji": "", "grade_mult": gmult,
        "mastery_level": mlevel, "mastery_xp": xp, "mastery_emoji": memoji,
        "mastery_mult": mmult, "next_mastery_xp": nxt,
        "gain_hint": None, "upgrade": None, "intent_affinity": intent,
    }


LOADOUT = {
    "techniques": {
        "learned": [
            _tech(1, "Thunder Step", "⚡", "combat", "celestial", 3.0, 5,
                  "\U0001f451", 2.0, 900, None, True, "sword",
                  "Lightning-fast steps that grant 30% evasion in the first round.", nome_pt="Passo do Trovão", qi_cost=30),
            _tech(6, "Celestial Palm", "✋", "combat", "transcendent", 2.0, 4,
                  "\U0001f31f", 1.6, 420, 800, True, "fist",
                  "Celestial Palm — +50% damage in all rounds.", nome_pt="Palma Celestial", qi_cost=45),
            _tech(3, "Iron Body", "\U0001f30d", "combat", "perfected", 1.5, 3,
                  "\U0001f4a0", 1.35, 210, 400, False, "body",
                  "Iron Body — reduces received damage by 50% in all rounds.", nome_pt="Corpo de Ferro", qi_cost=20),
            _tech(4, "Shadow Step", "\U0001f311", "combat", "refined", 1.2, 2,
                  "\U0001f537", 1.15, 60, 200, False, "killing",
                  "Shadow Step — completely dodges an attack.", nome_pt="Passo das Sombras", qi_cost=15),
            _tech(31, "Heart of Still Water", "\U0001f4a7", "meditation", "common", 1.0, 1,
                  "⚪", 1.0, 10, 100, False, None,
                  "Stillness of the heart — +15% cultivation while meditating.", nome_pt="Heart of Still Water", qi_cost=10),
            _tech(44, "Nine Abyss Scripture", "\U0001f573", "interior", "common", 1.0, 1,
                  "⚪", 1.0, 0, 100, False, None,
                  "A core art of another house — sealed to outsiders.", nome_pt="Nine Abyss Scripture", qi_cost=0),
        ],
        "learnable": [], "scrolls": [],
    },
    "arena": None,
    "npc": {"cooldown_seconds": 0},
    "stats": {},
    "dao_locked": False,
}
# a arte do Nucleo de outra casa: o estado TRANCADO da carta (TEC-1)
LOADOUT["techniques"]["learned"][5]["lib_locked"] = True

# ⚔️ O GOLPE PADRAO — o bloco so' existe com a flag `golpe_padrao` ligada, e a
# AUSENCIA dele e' o estado de todo mundo hoje. NV_GP escolhe qual se serve:
#   NV_GP=1 (default) — a flag ligada: o painel aparece
#   NV_GP=0           — a flag desligada: o bloco nao existe, e a seccao das
#                       Equipadas tem de ficar exactamente como estava
#   NV_GP=stale       — a escolha gravada ja' nao esta' equipada (o motor
#                       dispararia o basico, e a tela tem de o dizer)
_GP = (os.environ.get("NV_GP") or "1").strip().lower()
if _GP != "0":
    _gp_elig = [{"id": t_["id"], "name": t_["name"], "emoji": t_["emoji"]}
                for t_ in LOADOUT["techniques"]["learned"]
                if t_["tech_type"] == "combat" and t_["is_active"]]
    LOADOUT["default_strike"] = {
        "current": 0 if _GP == "stale" else (_gp_elig[0]["id"] if _gp_elig else 0),
        "stored": 999 if _GP == "stale" else (_gp_elig[0]["id"] if _gp_elig else 0),
        "eligible": _gp_elig,
        # ha' UMA arte proibida encenada de proposito: o texto que explica
        # porque' ela fica de fora e' metade do ponto (Lei §1).
        "forbidden_hidden": 1,
    }



# ⚠️ 2026-09-15 — este bloco SUBIU. Estava definido depois do `BEASTS`,
# que o usa no momento do import: `NameError: _PT_NOMES` mal se arrancava o
# servidor. Um mock que nem arranca nao mente sobre a tela — rebenta, que e'
# o modo de falha bom — mas custa o mesmo tempo a descobrir.
def _carrega_nomes_pt():
    tab = {}
    try:
        # 冶 3.1 — a lingua do MOCK (`NV_LANG`), nao so' `pt`: o servidor
        # traduz pela lingua do jogador, e um mock que mandasse pt a um ecra
        # `en` julgava uma tela que producao nunca desenha.
        _fn = os.path.join(ROOT, "locales", "%s.json" % LANG)
        if not os.path.exists(_fn):
            _fn = os.path.join(ROOT, "locales", "pt.json")
        with open(_fn, encoding="utf-8") as f:
            loc = json.load(f)
    except Exception:
        return tab
    import re as _re
    for k, v in loc.items():
        # 獸 2026-09-15 — a BESTA entrou aqui: desde este lote o servidor manda
        # o nome TRADUZIDO tambem para as 15, e um mock que mandasse ingles
        # mostrava-me uma tela que producao nunca desenha.
        m = _re.match(r"^(art|pill|herb|ore|beast)_(\d+)_name$", k)
        if m:
            tab[(m.group(1), int(m.group(2)))] = v
    return tab


_PT_NOMES = _carrega_nomes_pt()


# ══ 冶 3.1 — OS OFÍCIOS, com a FORMA de produção (2026-09-29) ═══════════════
#
# 🔴 PORQUE ISTO FOI REESCRITO. O mock antigo da Alquimia e da Forja tinha
# números IMPOSSÍVEIS ("T3 · 320 / 800 XP" — o T3 começa nos 2.000), nomes de
# posto que o jogo não tem ("Alquimista Celeste"), ids que não batiam com os
# seeds (o "9" era outra pílula) e as pílulas iam com o nome INGLÊS e sem
# `art_key` — a arte era encontrada pelo NOME aqui, exactamente onde o
# servidor a serio a encontra pela CHAVE. Era a 6.a vez que o arnês mentia
# antes do código.
#
# Agora: as receitas saem dos SEEDS (41 pílulas, 14 ervas, 31 receitas da
# Forja, 51 artefactos, 11 minérios), o nome vem traduzido na língua do mock
# (`NV_LANG`) com a chave canónica ao lado, os postos e limiares vêm das
# TABELAS dos motores e o "quanto falta" e o ganho passam pelo DONO real
# (`core/oficios.py`). O estado vive aqui e a feitura muda-o — a lista que se
# pede depois de forjar mostra o número novo, como o servidor.
#
#   NV_OFICIO=meio   (defeito) Alquimia T2 · Forja T3 · a 1.a receita a UM
#                    feito do selo seguinte — uma feitura acende a RECEITA
#   NV_OFICIO=baixo  T1 nos dois, a UM passo do posto — uma feitura acende o
#                    OFICIO (e a receita)
#   NV_OFICIO=max    tudo no máximo — nada acende, o traço diz "Concluído"
#   NV_OFICIO=r0     o jogador R0: a Alquimia recusa (`realm_locked`), a Forja
#                    abre as 6 receitas de reino 0
#   NV_OFICIO_ROTO=1 a feitura responde 500 (a falha do pedido)
from types import SimpleNamespace as _NSo

try:
    from database.seeds.alchemy_seeds import HERBS as _S_HERBS, PILLS as _S_PILLS
    from database.seeds.forge_seeds import FORGE_RECIPES as _S_FORGE
    from database.seeds.artifacts_seeds import ARTIFACTS as _S_ARTS, ORES as _S_ORES
    from core.alchemy_engine import (
        get_tier_name as _alc_tier_name, ALCHEMY_TIERS as _ALC_TIERS,
        get_mastery_name as _alc_m_name, get_soul_fire_name as _sf_name,
        SOUL_FIRE_TIERS as _SF_TIERS, XP_REWARDS as _ALC_XP,
    )
    from core.forge_engine import (
        get_forge_tier_name as _frg_tier_name, FORGE_TIERS as _FRG_TIERS,
        get_forge_mastery_name as _frg_m_name, get_recipe_tier_name as _frg_rt_name,
        FORGE_RECIPE_TIER_INFO as _FRG_RT_INFO,
    )
    import core.oficios as _OFC
except Exception as _e:  # o encenador nunca rebenta por causa de um import
    print("[dev_serve] oficios indisponiveis (%s)" % _e)
    _OFC = None

OFICIO = (os.environ.get("NV_OFICIO") or "meio").strip().lower()
try:
    with open(os.path.join(ROOT, "miniapp", "i18n", "%s.json" % LANG), encoding="utf-8") as _fm:
        _OF_LOC_MINI = json.load(_fm)
except Exception:
    _OF_LOC_MINI = {}
OFICIO_ROTO = (os.environ.get("NV_OFICIO_ROTO") or "").strip() not in ("", "0")

# O estado do ofício: (tier, xp) de cada posto e a maestria de cada receita.
_OF_ESTADOS = {
    "meio":  {"alc": (2, 1240), "frg": (3, 3900), "fogo": (2, 1300),
              "m_pilula": {1: (2, 29), 5: (3, 41), 6: (1, 4)},
              "m_forja": {1: (2, 29), 2: (3, 41)}},
    "baixo": {"alc": (1, 490), "frg": (1, 290), "fogo": (1, 60),
              "m_pilula": {1: (1, 9)}, "m_forja": {1: (1, 9)}},
    "max":   {"alc": (5, 17340), "frg": (5, 21000), "fogo": (6, 36000),
              "m_pilula": {1: (5, 212), 5: (5, 160)}, "m_forja": {1: (5, 212)}},
    "r0":    {"alc": (1, 0), "frg": (1, 60), "fogo": (0, 0),
              "m_pilula": {}, "m_forja": {1: (1, 3)}},
}
_OF = {k: (dict(v) if isinstance(v, dict) else v)
       for k, v in _OF_ESTADOS.get(OFICIO, _OF_ESTADOS["meio"]).items()}
if OFICIO == "r0":
    # a mesma canalizacao do `NV_REINO`: a chegada le' o reino do `/cultivation`,
    # e um cabecalho "Reino 3" com a Alquimia a recusar em R0 seria uma
    # contradicao que so' o arnes tem.
    PLAYER["realm"] = CULTIVATION["realm"] = 0
    PLAYER["sub_layer"] = CULTIVATION["sub_layer"] = 7
    PLAYER["realm_name"] = _OF_LOC_MINI.get("realm_0", "Mortal")


_OF_LOC = {}
try:
    with open(os.path.join(ROOT, "locales", "%s.json" % LANG), encoding="utf-8") as _f:
        _OF_LOC = json.load(_f)
except Exception:
    pass


def _of_desc(kind, rid, canon):
    """A descricao que o servidor manda (`catalog_desc`): `<kind>_<id>_desc`."""
    return _OF_LOC.get("%s_%d_desc" % (kind, rid)) or canon


def _of_nome(kind, rid, canon):
    """O nome que o servidor manda: TRADUZIDO na língua do mock, com o canónico
    como chave ao lado (nunca o contrário — lição de 14/09)."""
    return _PT_NOMES.get((kind, rid), canon)


def _of_flag(k):
    return bool(FEATURES.get(k))


def _of_skill(par):
    return _NSo(tier=par[0], xp=par[1])


def _of_maestria_p(pid):
    lv, n = _OF["m_pilula"].get(pid, (1, 0))
    return _NSo(mastery_level=lv, crafts_count=n) if pid in _OF["m_pilula"] else None


def _of_maestria_f(rid):
    lv, n = _OF["m_forja"].get(rid, (1, 0))
    return _NSo(mastery_level=lv, forges_count=n) if rid in _OF["m_forja"] else None


_HERB_TEM = {h["id"]: (400 if h["tier"] <= 1 else (12 if h["tier"] == 2 else 0))
             for h in (_S_HERBS if _OFC else [])}
_ORE_TEM = {o["id"]: (240 if o["tier"] <= 1 else (18 if o["tier"] == 2 else 0))
            for o in (_S_ORES if _OFC else [])}


def _alchemy_payload():
    if _OFC is None:
        return {"ok": False, "error": "oficios_indisponiveis"}
    lang = LANG
    realm = int(PLAYER.get("realm") or 0)
    ra = _OFC.retrato_alquimia(_of_skill(_OF["alc"]))
    rf = _OFC.retrato_fogo(_NSo(fire_tier=_OF["fogo"][0], fire_exp=_OF["fogo"][1]))
    energy = {"current": 180, "max": 200, "regen_minutes": 6.0, "vip_level": 0,
              "flame": {"tier": ra["tier"], "max_bonus": 10 * (ra["tier"] - 1),
                        "regen_pct": 5 * (ra["tier"] - 1)}}
    herbs = {h["id"]: h for h in _S_HERBS}
    grupos = {}
    for p in _S_PILLS:
        grupos.setdefault(int(p.get("required_alchemy_tier") or 1), []).append(p)
    tiers = []
    for tier in sorted(grupos):
        tlock = tier > ra["tier"]
        recs = []
        for p in grupos[tier]:
            m = _OFC.retrato_receita_pilula(_of_maestria_p(p["id"]))
            ings, ok_all = [], True
            for ing in p.get("ingredients") or []:
                h = herbs.get(ing["herb_id"], {})
                tem = _HERB_TEM.get(ing["herb_id"], 0)
                ok = tem >= ing["qty"]
                ok_all = ok_all and ok
                ings.append({"herb_id": ing["herb_id"], "qty": ing["qty"], "owned": tem,
                             "name": _of_nome("herb", ing["herb_id"], h.get("name", "?")),
                             "emoji": h.get("emoji", "🌿"), "tier": h.get("tier", 1), "ok": ok})
            cost = 10 * tier
            blocked = []
            if tlock:
                blocked.append("tier_locked")
            if realm < int(p.get("min_realm") or 0):
                blocked.append("realm_too_low")
            if not ok_all:
                blocked.append("missing_ingredients")
            if energy["current"] < cost:
                blocked.append("not_enough_energy")
            chance = max(5.0, min(98.0, 96.0 - 11 * int(p.get("difficulty") or 1)
                                  + (0, 0, 5, 12, 20, 30)[m["level"]]))
            recs.append({
                "id": p["id"], "name": _of_nome("pill", p["id"], p["name"]),
                "art_key": p["name"], "emoji": p.get("emoji", "💊"),
                "description": _of_desc("pill", p["id"], p.get("description", "")),
                "difficulty": p.get("difficulty", 1), "effect_type": p.get("effect_type", ""),
                "effect_value": p.get("effect_value", 0),
                "duration_minutes": p.get("duration_minutes", 0),
                "min_realm": p.get("min_realm", 0), "required_alchemy_tier": tier,
                "energy_cost": cost, "unlocked": not tlock, "owned": 3 if p["id"] == 1 else 0,
                "ingredients": ings, "ingredients_ok": ok_all,
                "mastery": {"level": m["level"], "name": _alc_m_name(m["level"], lang),
                            "crafts_count": m["crafts_count"], "next_crafts": m["next_crafts"],
                            "next_level": m["next_level"], "at_max": m["at_max"],
                            "bonus": (0, 0, 5.0, 12.0, 20.0, 30.0)[m["level"]]},
                "success_chance": round(chance, 1), "resistance": None,
                "can_craft": not blocked, "blocked_reasons": blocked,
            })
        tiers.append({"tier": tier, "name": _alc_tier_name(tier, lang),
                      "emoji": _ALC_TIERS.get(tier, _ALC_TIERS[1])["emoji"],
                      "locked": tlock, "is_current": tier == ra["tier"], "recipes": recs})
    return {
        "ok": True,
        "realm_locked": realm < 1,
        "min_realm_required": 1,
        "alchemy": {"tier": ra["tier"], "tier_name": _alc_tier_name(ra["tier"], lang),
                    "tier_emoji": _ALC_TIERS[ra["tier"]]["emoji"], "xp": ra["xp"],
                    "xp_to_next": ra["xp_to_next"], "at_max": ra["at_max"],
                    "max_tier": ra["max_tier"]},
        "soul_fire": {"tier": rf["tier"], "name": _sf_name(rf["tier"], lang),
                      "bonus_pct": float(_SF_TIERS.get(rf["tier"], {}).get("bonus", 0.0)),
                      "xp": rf["xp"], "xp_to_next": rf["xp_to_next"], "at_max": rf["at_max"],
                      "min_realm": 3, "unlocked": realm >= 3, "max_tier": rf["max_tier"],
                      "cores": 4},
        "energy": energy,
        "equipped_cauldron": {"id": 1, "catalog_id": 1, "name": "Caldeirão de Cobre",
                              "emoji": "🟤", "grade": 1, "durability": 80,
                              "max_durability": 100, "success_bonus": 5.0, "slots": 3,
                              "is_equipped": True},
        "owned_cauldrons": [],
        "tiers": tiers,
        "qi": 4120, "qi_capacity": 6800,
    }


def _forge_payload():
    if _OFC is None:
        return {"ok": False, "error": "oficios_indisponiveis"}
    lang = LANG
    realm = int(PLAYER.get("realm") or 0)
    rj = _OFC.retrato_forja(_of_skill(_OF["frg"]))
    arts = {a["id"]: a for a in _S_ARTS}
    ores = {o["id"]: o for o in _S_ORES}
    grupos = {}
    for r in _S_FORGE:
        grupos.setdefault(int(r["tier"]), []).append(r)
    tiers = []
    for tier in sorted(grupos):
        tlock = tier > rj["tier"] + 1
        recs = []
        for r in grupos[tier]:
            a = arts.get(r["artifact_id"])
            if not a:
                continue
            m = _OFC.retrato_receita_forja(_of_maestria_f(r["id"]))
            mats, ok_all = [], True
            for mat in r.get("materials") or []:
                o = ores.get(mat["ore_id"], {})
                tem = _ORE_TEM.get(mat["ore_id"], 0)
                ok = tem >= mat["qty"]
                ok_all = ok_all and ok
                mats.append({"ore_id": mat["ore_id"],
                             "name": _of_nome("ore", mat["ore_id"], o.get("name", "?")),
                             "emoji": o.get("emoji", "🪨"), "tier": o.get("tier", 1),
                             "required": mat["qty"], "owned": tem, "ok": ok})
            blocked = []
            if realm < int(r.get("required_realm") or 0):
                blocked.append("realm_too_low")
            if tlock:
                blocked.append("forge_tier_too_low")
            if not ok_all:
                blocked.append("not_enough_materials")
            chance = min(98.0, float(r.get("base_success_rate") or 80.0)
                         + (0, 0, 5, 12, 20, 30)[m["level"]])
            bulk = min((_ORE_TEM.get(x["ore_id"], 0) // max(1, x["qty"]))
                       for x in (r.get("materials") or [{"ore_id": 0, "qty": 1}]))
            recs.append({
                "id": r["id"], "artifact_id": a["id"],
                "artifact_name": _of_nome("art", a["id"], a["name"]),
                "artifact_art_key": a["name"],
                "artifact_emoji": a.get("emoji", "🗡️"), "artifact_grade": a.get("grade", 0),
                "artifact_type": a.get("type", ""),
                "artifact_base_stats": dict(a.get("base_stats") or {}),
                "artifact_description": _of_desc("art", a["id"], a.get("description", "")),
                "tier": tier, "required_realm": r.get("required_realm", 0),
                "base_success_rate": r.get("base_success_rate", 80.0),
                "bp_bonus": r.get("bp_bonus", 0), "materials": mats, "materials_ok": ok_all,
                "mastery": {"level": m["level"], "name": _frg_m_name(m["level"], lang),
                            "forges_count": m["forges_count"], "next_forges": m["next_forges"],
                            "next_level": m["next_level"], "at_max": m["at_max"],
                            "bonus": float((0, 0, 5, 12, 20, 30)[m["level"]])},
                "success_chance": round(chance, 1), "xp_capped": False, "xp_cap": 99999,
                "max_bulk": int(bulk), "can_craft": not blocked, "blocked_reasons": blocked,
            })
        tiers.append({"tier": tier, "name": _frg_rt_name(tier, lang),
                      "emoji": _FRG_RT_INFO.get(tier, _FRG_RT_INFO[1])["emoji"],
                      "locked": tlock, "is_current": tier <= rj["tier"], "recipes": recs})
    fi = _FRG_TIERS.get(rj["tier"], _FRG_TIERS[1])
    return {
        "ok": True,
        "forge": {"tier": rj["tier"], "tier_name": _frg_tier_name(rj["tier"], lang),
                  "tier_emoji": fi["emoji"], "xp": rj["xp"], "xp_to_next": rj["xp_to_next"],
                  "at_max": rj["at_max"], "max_tier": rj["max_tier"],
                  "total_forges": 412, "divine_forges": 9,
                  "quality_bonus": int(fi["quality_bonus"]),
                  "ore_discount": float(fi["ore_discount"])},
        "soul_fire_tier": _OF["fogo"][0],
        "sect_bonus": {"forge_lvl": 0, "forge_discount": 0.0},
        "tiers": tiers,
        "ores": [{"id": o["id"], "name": _of_nome("ore", o["id"], o["name"]),
                  "emoji": o.get("emoji", "🪨"), "tier": o["tier"],
                  "qty": _ORE_TEM.get(o["id"], 0)}
                 for o in sorted(_S_ORES, key=lambda x: (x["tier"], x["id"]))
                 if _ORE_TEM.get(o["id"], 0) > 0],
    }


def _of_sobe(par, tabela, maximo, ganho_xp):
    """Aplica XP a um (tier, xp) pela TABELA do motor (acumulada)."""
    tier, xp = par
    xp += ganho_xp
    while tier < maximo and xp >= tabela[tier + 1]["xp_req"]:
        tier += 1
    return (tier, xp)


def _of_maestria_sobe(dic, rid, reqs, maximo, n=1):
    lv, cnt = dic.get(rid, (1, 0))
    cnt += n
    while lv < maximo and cnt >= reqs[lv + 1]:
        lv += 1
    dic[rid] = (lv, cnt)


def _alchemy_craft(body, bulk=False):
    """A feitura de pílula, pela forma de `api_alchemy_craft(_bulk)`. Passa
    pelo DONO real do ganho e muda o estado."""
    if OFICIO_ROTO:
        raise RuntimeError("feitura encenada rota (NV_OFICIO_ROTO)")
    from core.alchemy_engine import MASTERY_LEVELS, MAX_MASTERY_LEVEL, MAX_ALCHEMY_TIER
    pid = int((body or {}).get("pill_id") or 1)
    n = max(1, min(30, int((body or {}).get("count") or 1))) if bulk else 1
    antes = {"oficio": _OFC.retrato_alquimia(_of_skill(_OF["alc"])),
             "receita": _OFC.retrato_receita_pilula(_of_maestria_p(pid)),
             "fogo": _OFC.retrato_fogo(_NSo(fire_tier=_OF["fogo"][0], fire_exp=_OF["fogo"][1]))}
    xp = _ALC_XP["success"] * n
    _OF["alc"] = _of_sobe(_OF["alc"], _ALC_TIERS, MAX_ALCHEMY_TIER, xp)
    _of_maestria_sobe(_OF["m_pilula"], pid, {k: v["crafts_req"] for k, v in MASTERY_LEVELS.items()},
                      MAX_MASTERY_LEVEL, n)
    _OF["fogo"] = (_OF["fogo"][0], _OF["fogo"][1] + 5 * n)
    g = _OFC.ganho_alquimia(antes, _of_skill(_OF["alc"]), _of_maestria_p(pid),
                            _NSo(fire_tier=_OF["fogo"][0], fire_exp=_OF["fogo"][1]))
    ra = g["oficio"]["depois"]
    rp = g["receita"]["depois"]
    out = {
        "ok": True, "result": "success", "quality": "normal", "potency_mult": 1.0,
        "success_chance": 84.0, "energy_after": 170, "energy_max": 200,
        "durability_after": 80, "durability_max": 100,
        "alchemy_xp_gained": xp, "alchemy_tier": ra["tier"], "alchemy_xp": ra["xp"],
        "alchemy_xp_to_next": ra["xp_to_next"],
        "alchemy_leveled_up": "oficio" in g["acende"],
        "mastery_level": rp["level"], "mastery_crafts": rp["crafts_count"],
        "mastery_leveled_up": "receita" in g["acende"],
        "soul_fire_tier": _OF["fogo"][0], "soul_fire_xp": _OF["fogo"][1],
        "soul_fire_leveled_up": False, "core_essence_added": 0, "charm_used": False,
        "delta": {"qi": 4120},
    }
    if bulk:
        out.update({"bulk": True, "crafts_requested": n, "crafts_done": n,
                    "early_stop_reason": None,
                    "results": {"failure": 0, "success": n, "perfect": 0, "divine": 0,
                                "explosion": 0},
                    "ingredients_consumed": [], "energy_spent": 10 * n, "tribulation": None})
    out.update(_OFC.no_payload(g, _of_flag))
    return out

# ══ 獸 3.3 — AS BESTAS, pelas ROTAS REAIS (2026-10-01) ═════════════════════
#
# 🔴 PORQUE ISTO FOI REESCRITO — a 9.a vez que o arnes mentia antes do codigo.
# O `BEASTS` daqui era um dict escrito a' mao: a MESMA evolucao para as cinco
# bestas ("proximo posto: Uncommon, nivel 20, 3 nucleos" numa Divina e numa
# Incomum), `rank_idx` 0 em todas, bonus inventados (Percepcao numa tartaruga
# que da' Vida) — e `beasts/level_up`/`evolve`/`collect_expedition` caiam no
# catch-all com `ok: true` SEM numeros: o ecra acenderia sobre nada.
#
# Agora as bestas vivem numa base em MEMORIA (linhas com a forma do
# `PlayerBeast`, especies e expedicoes dos SEEDS) e cada rota corre o HANDLER
# REAL do `core/webserver.py` — `_build_beasts_payload`, `train_beast`,
# `evolve_beast`, `collect_expedition`, `core/bestas` — sobre uma sessao falsa
# que responde as consultas pela ENTIDADE. O que o ecra recebe e' o que o
# servidor mandaria com estes dados; a chave-mestra e' a do arnes.
#
#   NV_BESTAS=varias (defeito) — sete bestas, uma por estado: a companheira
#                                (nivel 12, longe de evoluir), uma pronta a
#                                evoluir, uma em expedicao, uma que VOLTOU, uma
#                                no tecto (nivel 100 com XP a sobrar, posto
#                                maximo) e duas comuns
#   NV_BESTAS=uma              — so' a inicial (o p50: 148 dos 242 do `main`)
#   NV_BESTAS_NUCLEOS=N        — os nucleos bestiais (defeito 20)
#   NV_BESTAS_ROTA=1           — as rotas de escrita rebentam (500): nada acende
import asyncio as _aio_b
import datetime as _dt_b
import re as _re_b
from types import SimpleNamespace as _NS_b

_BESTAS_MODO = (os.environ.get("NV_BESTAS") or "varias").strip().lower()
_BESTAS_ROTA = (os.environ.get("NV_BESTAS_ROTA") or "").strip() not in ("", "0")
_BESTAS_UID = 123456789


def _bestas_base():
    from database.seeds.beasts_seeds import BEASTS as _SB, EXPEDITIONS as _SE
    from database.seeds.alchemy_seeds import HERBS as _SH
    from database.seeds.artifacts_seeds import ORES as _SO
    agora = _dt_b.datetime.now(_dt_b.timezone.utc)
    cat = {c["id"]: _NS_b(**c) for c in _SB}
    exps = {e["id"]: _NS_b(**e) for e in _SE}
    ervas = {}
    for i, h in enumerate(_SH, start=1):
        ervas[int(h.get("id", i))] = _NS_b(id=int(h.get("id", i)), name=h.get("name", ""))

    def linha(bid, cid, rank, level, exp, comp=False, exped=None, volta_min=None):
        return _NS_b(id=bid, player_id=_BESTAS_UID, catalog_id=cid, rank=rank,
                     custom_name=cat[cid].name, level=level, exp=exp,
                     is_companion=comp, is_on_expedition=exped is not None,
                     expedition_type=exped,
                     expedition_returns_at=(agora + _dt_b.timedelta(minutes=volta_min)
                                            if volta_min is not None else None))
    if _BESTAS_MODO == "uma":
        bestas = [linha(1, 1, "Common", 1, 0, comp=True)]
    else:
        bestas = [
            linha(1, 1, "Common", 4, 120),
            linha(2, 2, "Uncommon", 12, 640, comp=True),
            # pronta a evoluir: Lendaria nivel 50 (pede 50) e 15 nucleos (ha' 20)
            linha(3, 8, "Legendary", 50, 1200),
            linha(4, 6, "Epic", 21, 900, exped="Ancient Ruins", volta_min=131),
            linha(5, 4, "Rare", 9, 300, exped="Spirit Mountain", volta_min=-5),
            # o tecto: nivel 100 com XP a sobrar (162 assim no `main`), Divino
            linha(6, 10, "Divine", 100, 350),
            linha(7, 11, "Common", 2, 40),
        ]
    nucleos = int(os.environ.get("NV_BESTAS_NUCLEOS") or 20)
    inv = [_NS_b(player_id=_BESTAS_UID, item_type="beast_trap", item_id=0, quantity=3, quality="rare"),
           _NS_b(player_id=_BESTAS_UID, item_type="beast_core", item_id=0, quantity=nucleos, quality="normal")]
    jogador = _NS_b(telegram_id=_BESTAS_UID, language=LANG, luck=41, realm=3, hunt_essence=0,
                    spirit_stones=int(PLAYER.get("spirit_stones") or 0))
    # o espolio nomeia o minerio pela linha do catalogo — sem ela dizia "Ore #1"
    minerios = {int(o["id"]): _NS_b(id=int(o["id"]), name=o.get("name", "")) for o in _SO}
    return _NS_b(catalogo=cat, expedicoes=exps, ervas=ervas, minerios=minerios, bestas=bestas,
                 inv=inv, jogador=jogador)


_BESTAS = _bestas_base()


class _BRes:
    def __init__(self, rows=None, scalar=None, first=None, rowcount=0):
        self._rows = list(rows or [])
        self._scalar = scalar
        self._first = first
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        rows = self._rows
        return _NS_b(all=lambda: list(rows), first=lambda: (rows[0] if rows else None))

    def scalar(self):
        return self._scalar

    def first(self):
        return self._first

    def all(self):
        return list(self._rows)


def _bsql(stmt):
    from sqlalchemy.dialects import postgresql as _pgb
    try:
        return str(stmt.compile(dialect=_pgb.dialect(), compile_kwargs={"literal_binds": True}))
    except Exception:
        return str(stmt.compile(dialect=_pgb.dialect()))


class _BSessao:
    """Responde as consultas das rotas e dos motores das bestas pela ENTIDADE
    (e pelo WHERE, lido no SQL compilado). O que nao conhece devolve vazio —
    o mesmo que uma base sem essa linha."""

    def __init__(self, base):
        self.b = base

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def rollback(self):
        return None

    def add(self, obj):
        # a CAPTURA cria uma besta (`PlayerBeast(...)` + `session.add`): entra na
        # base em memoria com o id seguinte, como o INSERT daria
        if type(obj).__name__ == "PlayerBeast":
            nid = max([x.id for x in self.b.bestas] or [0]) + 1
            self.b.bestas.append(_NS_b(id=nid, player_id=obj.player_id, catalog_id=obj.catalog_id,
                                       rank=obj.rank, custom_name=None, level=obj.level or 1,
                                       exp=obj.exp or 0, is_companion=False,
                                       is_on_expedition=False, expedition_type=None,
                                       expedition_returns_at=None))
        return None

    async def delete(self, obj):
        # a ultima armadilha gasta apaga a linha
        if obj in self.b.inv:
            self.b.inv.remove(obj)
        return None

    async def get(self, ent, ident):
        nome = getattr(ent, "__name__", "")
        if nome == "PlayerBeast":
            return next((x for x in self.b.bestas if x.id == int(ident)), None)
        if nome == "BeastCatalog":
            return self.b.catalogo.get(int(ident))
        if nome == "HerbCatalog":
            return self.b.ervas.get(int(ident))
        if nome == "OreCatalog":
            return self.b.minerios.get(int(ident))
        return None

    async def execute(self, stmt):
        from sqlalchemy.sql.dml import Update
        sql = _bsql(stmt)
        if isinstance(stmt, Update):
            n = 0
            if stmt.table.name == "player_beasts":
                vals = {getattr(k, "key", str(k)): getattr(v, "value", v) for k, v in stmt._values.items()}
                for x in self.b.bestas:
                    if "is_companion = true" in sql and not x.is_companion:
                        continue
                    for k, v in vals.items():
                        setattr(x, k, v)
                    n += 1
            return _BRes(rowcount=n)
        cd = stmt.column_descriptions
        ent = cd[0].get("entity")
        nome = getattr(ent, "__name__", "")
        inteira = len(cd) == 1 and cd[0].get("expr") is ent
        m_id = _re_b.search(r"\b\w+\.id = (\d+)", sql)
        if nome == "Player":
            return _BRes([self.b.jogador])
        if nome == "PlayerBeast":
            rows = [x for x in self.b.bestas if x.player_id == _BESTAS_UID]
            if m_id:
                rows = [x for x in rows if x.id == int(m_id.group(1))]
            if "is_on_expedition = true" in sql:
                rows = [x for x in rows if x.is_on_expedition]
            if "count(" in sql.lower():
                return _BRes(scalar=len(rows))
            if inteira:
                rows.sort(key=lambda x: (not x.is_companion, -x.level, x.id))
                return _BRes(rows)
            r0 = rows[0] if rows else None
            return _BRes(first=(_NS_b(**{c["name"]: getattr(r0, c["name"]) for c in cd}) if r0 else None))
        if nome == "BeastCatalog":
            rows = sorted(self.b.catalogo.values(), key=lambda c: c.id)
            m_in = _re_b.search(r"beasts_catalog\.id IN \(([^)]*)\)", sql)
            if m_id:
                rows = [c for c in rows if c.id == int(m_id.group(1))]
            elif m_in:
                ids = {int(v) for v in _re_b.findall(r"\d+", m_in.group(1))}
                rows = [c for c in rows if c.id in ids]
            return _BRes(rows)
        if nome == "ExpeditionCatalog":
            rows = sorted(self.b.expedicoes.values(), key=lambda e: e.id)
            m_nome = _re_b.search(r"expeditions_catalog\.name = '([^']*)'", sql)
            if m_id:
                rows = [e for e in rows if e.id == int(m_id.group(1))]
            elif m_nome:
                rows = [e for e in rows if e.name == m_nome.group(1)]
            return _BRes(rows)
        if nome == "PlayerInventory":
            rows = [r for r in self.b.inv if r.quantity > 0]
            for tp in ("beast_trap", "beast_core"):
                if "'%s'" % tp in sql:
                    rows = [r for r in rows if r.item_type == tp]
                    break
            else:
                rows = []
            if not inteira:
                return _BRes(scalar=sum(int(r.quantity) for r in rows))
            return _BRes(rows)
        if "count(" in sql.lower() or "sum(" in sql.lower():
            return _BRes(scalar=0)
        return _BRes()


# ⚠️ a funcao ORIGINAL, guardada antes de qualquer remendo: a rota corre com
# `core.portas.onda_on` remendado para as flags do arnes, e um remendo que
# chamasse `core.portas.onda_on` chamava-se a si proprio (recursao infinita —
# foi o 1.o arranque).
import core.portas as _PORTAS_b  # noqa: E402
_ONDA_ON_ORIG_b = _PORTAS_b.onda_on


def _bestas_onda():
    return _ONDA_ON_ORIG_b(lambda k: bool(FEATURES.get(k)))


_ROTAS_BESTAS = {
    "beasts/list": "api_beasts_list",
    "beasts/capture_attempt": "api_beasts_capture_attempt",
    "beasts/level_up": "api_beasts_level_up",
    "beasts/evolve": "api_beasts_evolve",
    "beasts/collect_expedition": "api_beasts_collect_expedition",
    "beasts/equip_companion": "api_beasts_equip_companion",
    "beasts/expeditions": "api_beasts_expeditions",
    "beasts/send_expedition": "api_beasts_send_expedition",
}


def _bestas_rota(endpoint, body):
    """Corre o HANDLER REAL da rota sobre a base em memoria. None = nao e' comigo."""
    fn_nome = _ROTAS_BESTAS.get(endpoint)
    if fn_nome is None:
        return None
    if _BESTAS_ROTA and endpoint != "beasts/list":
        raise RuntimeError("NV_BESTAS_ROTA: %s rebentou" % endpoint)
    import core.webserver as _Wb
    import core.portas as _POb
    _BESTAS.jogador.spirit_stones = int(PLAYER.get("spirit_stones") or 0)
    _sessao = _BSessao(_BESTAS)
    _orig = (_Wb.get_session_factory, _POb.onda_on)
    _Wb.get_session_factory = lambda: (lambda: _sessao)
    _POb.onda_on = lambda *a, **k: _bestas_onda()
    try:
        resp = _aio_b.run(getattr(_Wb, fn_nome)({"user_id": _BESTAS_UID, "payload": dict(body or {})}))
    finally:
        _Wb.get_session_factory, _POb.onda_on = _orig
    # as pedras gastas voltam ao jogador do arnes (o cabecalho le-as dali)
    PLAYER["spirit_stones"] = int(_BESTAS.jogador.spirit_stones or 0)
    return json.loads(resp.text)

# ══ 宗 4.1 — A SEITA, pelas ROTAS REAIS (2026-10-05) ════════════════════════
#
# O Pavilhão da Seita (`SectHallModal`) NUNCA esteve no arnês: `world/sect_hall`
# caía no catch-all e a janela dizia "não és membro" — ninguém o tinha olhado
# aqui. Nasce já pelo molde da 3.3: um jogador em memória (as COLUNAS que os
# motores da seita lêem), as missões da casa das SEMENTES (`QUEST_SEEDS`), as
# artes das estantes das SEMENTES (`combat_seeds.TECHNIQUES`), e cada rota corre
# o HANDLER REAL do `core/webserver.py` sobre uma sessão falsa que responde pela
# entidade. A promoção, o tributo e a contribuição da missão passam pelos
# MUTADORES REAIS (`recompute_player_rank`, `tribute_stones`,
# `award_sect_contribution`, `claim_quest_reward`).
#
#   NV_SEITA=meio (defeito) — Ancião, 1.360 / 1.500 para Herdeiro (faltam 140 —
#                             o p50 medido no `main`), reino 7: um tributo de
#                             5.000 pedras (+200) cruza o limiar e a insígnia
#                             acende; a missão 600 (+30) só traça
#   NV_SEITA=portao         — Ancião com 1.600 (a contribuição chega) e reino 6:
#                             preso no portão de reino (o Herdeiro pede 7)
#   NV_SEITA=promove        — Ancião com 1.600 e reino 7: ABRIR o Salão promove
#                             (o recompute) e a insígnia acende ao abrir
#   NV_SEITA=topo           — Herdeiro com 20.000 (o maior do `main`): "Posto máximo"
#   NV_SEITA=discipulo      — Discípulo com 0 (o caso do Beta)
#   NV_SEITA=fora           — sem casa (o Salão diz que não é membro)
#   NV_SEITA_ROTA=1         — as escritas rebentam (500): nada acende
#
# ⚠️ `quests/claim` passa a correr aqui para TODAS as missões: no arnês só as da
# casa existem; uma missão de outra aba responde 404 (`quest_not_claimable`).
import collections as _col_s

_SEITA_MODO = (os.environ.get("NV_SEITA") or "meio").strip().lower()
_SEITA_ROTA = (os.environ.get("NV_SEITA_ROTA") or "").strip() not in ("", "0")
_SEITA_UID = 123456789
_SEITA_CASA = "azure_cloud"   # a casa com mais membros no `main` (11 de 21)


def _seita_base():
    from database.seeds.combat_seeds import TECHNIQUES as _ST
    from database.seeds.quests_seeds import QUEST_SEEDS as _SQ
    modos = {   # posto, contribuição ganha, saldo (o mérito), reino
        "meio":      ("elder", 1360, 1360, 7),
        "portao":    ("elder", 1600, 1600, 6),
        "promove":   ("elder", 1600, 1600, 7),
        "topo":      ("heir", 20000, 11940, 10),
        "discipulo": ("disciple", 0, 0, 10),
    }
    posto, ganha, saldo, reino = modos.get(_SEITA_MODO, modos["meio"])
    fora = _SEITA_MODO == "fora"
    jogador = _NS_b(telegram_id=_SEITA_UID, language=LANG, realm=reino, karma=340,
                    sect_id=None if fora else _SEITA_CASA,
                    sect_rank=None if fora else posto,
                    sect_contribution=saldo, sect_contribution_earned=ganha,
                    scroll_econ=None, sect_master_name="Anciã Bai Ling",
                    sect_joined_at=_dt_b.datetime(2026, 7, 2, tzinfo=_dt_b.timezone.utc),
                    spirit_stones=int(PLAYER.get("spirit_stones") or 0),
                    unlocked_titles=[], core_quality="x")
    _vazio = {"sect_key": None, "library_tier": None, "library_cp_cost": None,
              "tech_type": "combat", "grade": None, "art_key": None}
    tecs = {int(t["id"]): _NS_b(**dict(_vazio, **t)) for t in _ST}
    cat_q = {}
    for q in _SQ:
        if q.get("type") == "sect":
            cat_q[int(q["id"])] = _NS_b(**dict({"choices": None, "sect_id": None,
                                                "is_active": True, "emoji": "🏯"}, **q))
    agora = _dt_b.datetime.now(_dt_b.timezone.utc)

    def linha(qid, prog, feita):
        return (_NS_b(player_id=_SEITA_UID, quest_id=qid, progress=prog, is_completed=feita,
                      claimed=False, chosen_choice_id=None,
                      reset_at=agora + _dt_b.timedelta(days=1)), cat_q[qid])
    # a 600 está PRONTA (+30 contribuição), a 601 a caminho — reais das sementes
    missoes = [] if fora else [linha(600, int(cat_q[600].objective_value), True),
                               linha(601, 1, False)]
    return _NS_b(jogador=jogador, tecs=tecs, catalogo_q=cat_q, missoes=missoes)


_SEITA = _seita_base()


class _SSessao:
    """Responde às consultas dos motores da seita pela ENTIDADE (e pelo WHERE,
    lido no SQL compilado). As colunas do jogador saem como linha com nome E
    índice — os motores lêem `row[0]`; o que não conhece devolve vazio."""

    def __init__(self, base):
        self.b = base

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def rollback(self):
        return None

    def add(self, obj):
        # o `ensure_sect_quests` materializa as missões da casa que faltam
        if type(obj).__name__ == "PlayerQuest":
            qid = int(obj.quest_id)
            q = self.b.catalogo_q.get(qid)
            if q is not None and not any(pq.quest_id == qid for pq, _ in self.b.missoes):
                self.b.missoes.append((_NS_b(player_id=obj.player_id, quest_id=qid,
                                             progress=int(getattr(obj, "progress", 0) or 0),
                                             is_completed=bool(getattr(obj, "is_completed", False)),
                                             claimed=bool(getattr(obj, "claimed", False)),
                                             chosen_choice_id=None,
                                             reset_at=getattr(obj, "reset_at", None)), q))
        return None

    async def delete(self, obj):
        return None

    async def get(self, ent, ident):
        return None

    def begin_nested(self):
        # as notificações (`notify`) abrem um SAVEPOINT: aqui não há transacção
        # para proteger — um contexto que não faz nada
        class _Nada:
            async def __aenter__(s2):
                return s2

            async def __aexit__(s2, *a):
                return False
        return _Nada()

    async def execute(self, stmt):
        sql = _bsql(stmt)
        cd = stmt.column_descriptions
        nomes = [getattr(c.get("entity"), "__name__", "") for c in cd]
        inteira = len(cd) == 1 and cd[0].get("expr") is cd[0].get("entity")
        j = self.b.jogador
        if nomes[:1] == ["Player"]:
            if inteira:
                return _BRes([j])
            campos = [c["name"] for c in cd]
            linha = _col_s.namedtuple("Linha", campos)(*[getattr(j, c, None) for c in campos])
            return _BRes([linha], first=linha)
        if nomes[:1] == ["WorldSect"]:
            return _BRes(scalar=4120)
        if nomes[:2] == ["PlayerQuest", "QuestCatalog"]:
            rows = list(self.b.missoes)
            m = _re_b.search(r"player_quests\.quest_id = (\d+)", sql)
            if m:
                rows = [(pq, q) for pq, q in rows if pq.quest_id == int(m.group(1))]
            if "player_quests.claimed = false" in sql:
                rows = [(pq, q) for pq, q in rows if not pq.claimed]
            if "player_quests.is_completed = true" in sql:
                rows = [(pq, q) for pq, q in rows if pq.is_completed]
            return _BRes(rows, first=(rows[0] if rows else None))
        if nomes[:1] == ["PlayerQuest"]:
            if not inteira:
                return _BRes([pq.quest_id for pq, _ in self.b.missoes])
            return _BRes([pq for pq, _ in self.b.missoes])
        if nomes[:1] == ["QuestCatalog"]:
            return _BRes([q for q in self.b.catalogo_q.values()
                          if q.type == "sect" and q.sect_id in (None, j.sect_id)])
        if nomes[:1] == ["TechniqueCatalog"]:
            # o loadout EQUIPADO (JOIN às artes do jogador): o jogador do arnês
            # não aprendeu nenhuma arte da casa — nada equipado daqui
            if "JOIN player_techniques" in sql:
                return _BRes([])
            rows = sorted(self.b.tecs.values(), key=lambda t: t.id)
            m_in = _re_b.search(r"techniques_catalog\.id IN \(([^)]*)\)", sql)
            m_sk = _re_b.search(r"techniques_catalog\.sect_key = '([^']*)'", sql)
            m_lt = _re_b.search(r"techniques_catalog\.library_tier IN \(([^)]*)\)", sql)
            m_id = _re_b.search(r"techniques_catalog\.id = (\d+)", sql)
            if m_in:
                ids = {int(v) for v in _re_b.findall(r"\d+", m_in.group(1))}
                rows = [t for t in rows if t.id in ids]
            if m_id:
                rows = [t for t in rows if t.id == int(m_id.group(1))]
            if m_sk:
                rows = [t for t in rows if t.sect_key == m_sk.group(1)]
            if m_lt:
                ts = {int(v) for v in _re_b.findall(r"\d+", m_lt.group(1))}
                rows = [t for t in rows if t.library_tier in ts]
            if not inteira:
                # colunas pedidas → linhas com nome E índice (os motores lêem r[0])
                campos = [c["name"] for c in cd]
                tup = _col_s.namedtuple("LinhaT", campos)
                rows = [tup(*[getattr(t, c, None) for c in campos]) for t in rows]
            return _BRes(rows)
        if nomes[:1] in (["PlayerTechnique"], ["PlayerSectTechnique"]):
            return _BRes([])
        if "count(" in sql.lower() or "sum(" in sql.lower():
            return _BRes(scalar=0)
        return _BRes()


_ROTAS_SEITA = {
    "world/sect_hall": "api_world_sect_hall",
    "world/sect_tribute": "api_world_sect_tribute",
    "world/merit_list": "api_world_merit_list",
    "world/sect_library": "api_world_sect_library",
    "quests/claim": "api_quests_claim",
}


def _seita_rota(endpoint, body):
    """Corre o HANDLER REAL da rota sobre o jogador em memória. None = não é comigo."""
    fn_nome = _ROTAS_SEITA.get(endpoint)
    if fn_nome is None:
        return None
    if _SEITA_ROTA and endpoint in ("world/sect_tribute", "quests/claim"):
        raise RuntimeError("NV_SEITA_ROTA: %s rebentou" % endpoint)
    import core.webserver as _Ws
    import core.portas as _POs
    import database.db as _DBs
    _SEITA.jogador.spirit_stones = int(PLAYER.get("spirit_stones") or 0)
    _sessao = _SSessao(_SEITA)
    _orig = (_Ws.get_session_factory, _POs.onda_on, _DBs.feature_enabled_for_world)
    _Ws.get_session_factory = lambda: (lambda: _sessao)
    _POs.onda_on = lambda *a, **k: _bestas_onda()
    _DBs.feature_enabled_for_world = lambda feature, world_key=None: bool(FEATURES.get(feature))
    try:
        resp = _aio_b.run(getattr(_Ws, fn_nome)({"user_id": _SEITA_UID, "payload": dict(body or {})}))
    finally:
        _Ws.get_session_factory, _POs.onda_on, _DBs.feature_enabled_for_world = _orig
    # as pedras gastas no tributo voltam ao jogador do arnês (o cabeçalho lê-as dali)
    PLAYER["spirit_stones"] = int(_SEITA.jogador.spirit_stones or 0)
    return json.loads(resp.text)


# ── 幫 4.2 — A GUILDA (a tabela `sects`, a aba `SectTab`) ──────────────────
# A Guilda NUNCA tinha estado no arnês: `sect` caía no catch-all e a aba dizia
# "criar ou entrar numa guilda" — ninguém a tinha olhado aqui. Nasce pelo molde
# da 3.3 e da 4.1: uma guilda em memória (as COLUNAS que o motor lê) com os
# números da PRODUÇÃO (`tools/db_readonly_guilda_1007.py`), e cada rota corre o
# HANDLER REAL do `core/webserver.py` sobre uma sessão falsa que responde pela
# entidade. A melhoria passa pelo MOTOR REAL (`upgrade_building`).
#
#   NV_GUILDA=anciao (defeito) — Ancião de uma guilda com os números MAIORES do
#                                `main`: 49 de 50 membros, tesouro 18.893.071.686
#                                (11 dígitos), níveis 255/240/300/239/856/720,
#                                contribuição 3.002.845.993 (o maior membro)
#   NV_GUILDA=mestre           — o Mestre da mesma guilda
#   NV_GUILDA=membro           — um Discípulo: a planta lê-se, não se melhora
#   NV_GUILDA=pobre            — Ancião de uma guilda cujo tesouro não paga nada:
#                                258.326 contra 529.000 (o caso medido no `main`)
#   NV_GUILDA=nova             — guilda acabada de criar: só o Treino no 1 (o caso
#                                medido no Beta) — as outras "por construir"
#   NV_GUILDA=fora             — sem guilda (a entrada de hoje: criar ou entrar)
#   NV_GUILDA_ROTA=1           — a melhoria rebenta (500): nada acende
_GUILDA_MODO = (os.environ.get("NV_GUILDA") or "anciao").strip().lower()
_GUILDA_ROTA = (os.environ.get("NV_GUILDA_ROTA") or "").strip() not in ("", "0")
_GUILDA_UID = 123456789


def _guilda_base():
    import uuid as _uuid_g
    modos = {   # posto, tesouro, níveis (treino, jardim, forja, biblioteca, defesa, veia), membros
        "anciao": ("elder", 18893071686, (255, 240, 300, 239, 856, 720), 49),
        "mestre": ("master", 18893071686, (255, 240, 300, 239, 856, 720), 49),
        "membro": ("disciple", 18893071686, (255, 240, 300, 239, 856, 720), 49),
        "pobre": ("elder", 258326, (28, 22, 25, 26, 34, 32), 4),
        "nova": ("master", 499000, (1, 0, 0, 0, 0, 0), 1),
    }
    posto, tesouro, nv, n_membros = modos.get(_GUILDA_MODO, modos["anciao"])
    sid = _uuid_g.UUID("7a1d0c3e-0000-4000-8000-000000000042")
    guilda = _NS_b(id=sid, name="Pavilhão da Nuvem Errante", master_id=1,
                   description=None, bulletin="Quem sobe a montanha sobe junto.",
                   member_count=n_membros, max_members=50, spirit_stones=tesouro,
                   training_lvl=nv[0], herb_garden_lvl=nv[1], forge_lvl=nv[2],
                   library_lvl=nv[3], defense_lvl=nv[4], spirit_vein_lvl=nv[5],
                   group_link=None, lineage_key=None, lineage_chosen_at=None,
                   created_at=_dt_b.datetime(2026, 5, 19, tzinfo=_dt_b.timezone.utc))
    eu = None if _GUILDA_MODO == "fora" else _NS_b(
        sect_id=sid, player_id=_GUILDA_UID, rank=posto,
        contribution_points=3002845993 if posto != "disciple" else 101800)
    nomes = ["Lin Xiao", "Mei Hua", "Bai Yun", "Zhao Feng", "Qing Shan", "Yue Ling",
             "Han Bing", "Lei Ming", "Su Yan", "Long Tian", "Feng Wu", "Shui Lian"]
    membros = []
    if eu is not None:
        membros.append((posto, eu.contribution_points, PLAYER.get("dao_name") or "Cultivador",
                        None, 7, 4, 1212935443))
        outros = n_membros - 1
        for i in range(outros):
            rk = "master" if (i == 0 and posto != "master") else ("elder" if i < 15 else "disciple")
            contrib = max(0, int(55805718 * (0.82 ** i)))
            membros.append((rk, contrib, "%s %d" % (nomes[i % len(nomes)], i // len(nomes) + 1),
                            None, 3 + (i % 6), 1 + (i % 9), 40000000 + 9000000 * (outros - i)))
        membros.sort(key=lambda r: -r[1])
    return _NS_b(guilda=guilda, eu=eu, membros=membros)


_GUILDA = _guilda_base()


class _GSessao:
    """Responde às consultas das rotas e do motor da guilda pela ENTIDADE. As
    colunas saem como linha com nome E índice (o motor lê `row[0]`); uma só
    coluna sai como escalar (`scalar_one_or_none`); o que não conhece devolve
    vazio — o mesmo que uma base sem essa linha."""

    def __init__(self, base):
        self.b = base
        self.sql = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def rollback(self):
        return None

    def add(self, obj):
        return None

    async def get(self, ent, ident):
        return None

    def begin_nested(self):
        class _Nada:
            async def __aenter__(s2):
                return s2

            async def __aexit__(s2, *a):
                return False
        return _Nada()

    async def execute(self, stmt):
        sql = _bsql(stmt)
        self.sql.append(sql)
        cd = stmt.column_descriptions
        nomes = [getattr(c.get("entity"), "__name__", "") for c in cd]
        inteira = len(cd) == 1 and cd[0].get("expr") is cd[0].get("entity")
        g, eu = self.b.guilda, self.b.eu
        if nomes == ["SectMember", "Sect"]:
            return _BRes(first=((eu, g) if eu is not None else None))
        if nomes[:1] == ["SectMember"] and inteira:
            return _BRes([eu] if eu is not None else [])
        if nomes[:1] == ["Sect"] and inteira:
            # o directório (`list_open_sects`, com ORDER BY) mostra a guilda do
            # arnês a quem ainda não é de guilda nenhuma — como a produção
            if "ORDER BY" in sql:
                return _BRes([g])
            return _BRes([g] if eu is not None else [])
        if "count(sects.id)" in sql.lower():
            return _BRes(scalar=1)
        if nomes and all(n == "Sect" for n in nomes):
            if eu is None:
                return _BRes()
            campos = [c["name"] for c in cd]
            linha = _col_s.namedtuple("LinhaG", campos)(*[getattr(g, c, None) for c in campos])
            return _BRes([linha], first=linha)
        if nomes[:2] == ["SectMember", "SectMember"]:
            return _BRes(list(self.b.membros))
        if nomes[:1] == ["Player"]:
            if inteira:
                return _BRes([_NS_b(telegram_id=_GUILDA_UID, spirit_stones=int(PLAYER.get("spirit_stones") or 0),
                                    language=LANG, karma=0)])
            campos = [c["name"] for c in cd]
            vals = {"dao_name": PLAYER.get("dao_name") or "Cultivador", "username": None, "language": LANG}
            linha = _col_s.namedtuple("LinhaP", campos)(*[vals.get(c) for c in campos])
            if len(campos) == 1:
                return _BRes([linha[0]], first=linha)
            return _BRes([linha], first=linha)
        if "count(" in sql.lower() or "sum(" in sql.lower():
            return _BRes(scalar=0)
        return _BRes()


_ROTAS_GUILDA = {
    "sect": "api_sect",
    "sect/upgrade": "api_sect_upgrade",
    "sect/list": "api_sect_list",
}


def _guilda_rota(endpoint, body):
    """Corre o HANDLER REAL da rota sobre a guilda em memória. None = não é comigo."""
    fn_nome = _ROTAS_GUILDA.get(endpoint)
    if fn_nome is None:
        return None
    if _GUILDA_ROTA and endpoint == "sect/upgrade":
        raise RuntimeError("NV_GUILDA_ROTA: %s rebentou" % endpoint)
    import core.webserver as _Wg
    import core.portas as _POg
    import database.db as _DBg
    _sessao = _GSessao(_GUILDA)
    _orig = (_Wg.get_session_factory, _POg.onda_on, _DBg.feature_enabled_for_world)
    _Wg.get_session_factory = lambda: (lambda: _sessao)
    _POg.onda_on = lambda *a, **k: _bestas_onda()
    _DBg.feature_enabled_for_world = lambda feature, world_key=None: bool(FEATURES.get(feature))
    try:
        resp = _aio_b.run(getattr(_Wg, fn_nome)({"user_id": _GUILDA_UID, "payload": dict(body or {})}))
    finally:
        _Wg.get_session_factory, _POg.onda_on, _DBg.feature_enabled_for_world = _orig
    return json.loads(resp.text)


# ── 層 4.3 AS MASMORRAS (`api_dungeons_*`) — o HANDLER REAL ───────────────────
# ⚠️ As masmorras NUNCA tinham estado no arnês (caíam no catch-all) — o mesmo
# vazio da Guilda antes da 4.2. Molde da 3.3/4.1/4.2: as masmorras em memória (o
# catálogo das SEMENTES — nomes, andares por dificuldade, espólio — e as COLUNAS
# de `player_dungeons`), e cada rota corre o HANDLER REAL do `core/webserver.py`
# sobre uma sessão falsa que responde pela entidade. O combate de cada andar é
# ENCENADO (o `_do_dungeon_floor` real precisa da alma inteira do jogador); o
# espólio sai do `_roll_floor_loot` REAL sobre o espólio da semente. O fim do
# Chefe corre o SETTLE REAL (`_settle_dungeon_boss`) e o `masmorra_ganho` sai do
# dono (`core/masmorra.py`), só com a onda — como no servidor.
#
# Os números são os da PRODUÇÃO (`tools/db_readonly_masmorras_1008.py`):
#   NV_MASMORRA=farm (defeito) — o agricultor do Beta: Spirit Mine em Pesadelo (19
#                                andares, 1.157 Chefes em 30 dias), 11 vencidos,
#                                as 4 dificuldades vencidas, mais fundo 19
#   NV_MASMORRA=porta          — à porta do Chefe: Sect Ruins em Fácil, 11 de 12 (a
#                                run aberta do Beta), nunca concluída — o Chefe
#                                acende o andar E a dificuldade
#   NV_MASMORRA=funda          — o corte maior: Ancient Battlefield em Pesadelo (95
#                                andares), 49 vencidos, Normal concluída, mais
#                                fundo 60 (o `main`)
#   NV_MASMORRA=nova           — nunca entrou em masmorra nenhuma (entrar acende o 1)
#   NV_MASMORRA_MORTE=1        — o próximo andar perde-se (o modal de hoje)
#   NV_MASMORRA_CHEFE=perde    — o Chefe ganha (nada acende)
_MASM_MODO = (os.environ.get("NV_MASMORRA") or "farm").strip().lower()
_MASM_MORTE = (os.environ.get("NV_MASMORRA_MORTE") or "").strip() not in ("", "0")
_MASM_CHEFE_PERDE = (os.environ.get("NV_MASMORRA_CHEFE") or "").strip().lower() == "perde"
_MASM_UID = 123456789


def _masmorra_base():
    from database.seeds.dungeon_seeds import DUNGEON_SEEDS as _SD
    from database.seeds.alchemy_seeds import HERBS as _SH, PILLS as _SP
    from database.seeds.artifacts_seeds import ORES as _SO
    # ⚠️ continente None: o portal vê-se de qualquer continente (o arnês olha
    # para a masmorra, não para a viagem — essa é a MV-1)
    cat = {int(d["id"]): _NS_b(**dict(d, continent=None)) for d in _SD}

    def _linhas(seed):
        out = {}
        for i, r in enumerate(seed, start=1):
            rid = int(r.get("id", i))
            out[rid] = _NS_b(id=rid, name=r.get("name", ""), emoji=r.get("emoji"), tier=r.get("tier"))
        return out
    agora = _dt_b.datetime.now(_dt_b.timezone.utc)

    def pd(did, cur, mf, best, comp, dif, bag=None):
        return _NS_b(player_id=_MASM_UID, dungeon_id=did, current_floor=cur, max_floor_reached=mf,
                     best_difficulty=best, completed=comp, difficulty=dif,
                     expedition_bag=dict(bag or {}), last_attempt_at=agora)
    saco = {"stones": 2840, "herbs": {"2": 3}, "ores": {"2": 2}, "qi_pills": 1, "qi_pill_id": 6}
    modos = {
        "farm": [pd(9, 11, 19, 4, True, "nightmare", saco), pd(1, 0, 15, 4, True, None),
                 pd(6, 0, 8, 2, True, None), pd(8, 0, 7, 1, True, None), pd(10, 0, 5, 0, False, None)],
        "porta": [pd(14, 11, 11, 0, False, "easy", saco), pd(1, 0, 10, 2, True, None)],
        "funda": [pd(22, 49, 60, 2, True, "nightmare", saco), pd(18, 0, 65, 4, True, None)],
        "nova": [],
    }
    pds = {p.dungeon_id: p for p in modos.get(_MASM_MODO, modos["farm"])}
    max_hp = float(PLAYER.get("max_hp") or 21400)
    jogador = _NS_b(telegram_id=_MASM_UID, language=LANG,
                    realm=10 if _MASM_MODO == "funda" else int(PLAYER.get("realm") or 0),
                    qi=float(PLAYER.get("qi") or 0), qi_capacity=float(PLAYER.get("qi_capacity") or 100),
                    spirit_stones=int(PLAYER.get("spirit_stones") or 0),
                    current_hp=round(max_hp * 0.86), max_hp=max_hp,
                    current_continent=PLAYER.get("current_continent") or "linghe",
                    home_continent="linghe", is_traveling=False, luck=41,
                    body_tempering_level=4, body_tempering_xp=0, core_essence=0)
    return _NS_b(catalogo=cat, pds=pds, jogador=jogador, ervas=_linhas(_SH), minerios=_linhas(_SO),
                 pilulas=_linhas(_SP), chefe=None)


_MASMORRA = _masmorra_base()


def _masm_ids(sql, coluna):
    """Os ids de `coluna = N` ou `coluna IN (a, b)` no SQL compilado; None se não há."""
    m = _re_b.search(_re_b.escape(coluna) + r" = (\d+)", sql)
    if m:
        return [int(m.group(1))]
    m = _re_b.search(_re_b.escape(coluna) + r" IN \(([^)]*)\)", sql)
    if m:
        return [int(x) for x in _re_b.findall(r"\d+", m.group(1))]
    return None


class _MSessao:
    """Responde às consultas das rotas das masmorras (e do settle do Chefe) pela
    ENTIDADE: a linha de `player_dungeons` é UM objecto em memória, portanto o
    "antes" (colunas lidas antes de a rota escrever) e o "depois" (relidas a
    seguir) saem dele como sairiam da base. O que não conhece devolve vazio."""

    def __init__(self, base):
        self.b = base

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def commit(self):
        return None

    async def flush(self):
        return None

    async def rollback(self):
        return None

    def add(self, obj):
        # a linha nova de quem entra numa masmorra pela 1.a vez (`enter`)
        if type(obj).__name__ == "PlayerDungeon":
            self.b.pds[int(obj.dungeon_id)] = obj
        return None

    async def get(self, ent, ident):
        return None

    def begin_nested(self):
        class _Nada:
            async def __aenter__(s2):
                return s2

            async def __aexit__(s2, *a):
                return False
        return _Nada()

    async def execute(self, stmt):
        cd = getattr(stmt, "column_descriptions", None)
        if cd is None:          # um UPDATE/INSERT de um motor lateral: nada a dizer
            return _BRes()
        sql = _bsql(stmt)
        b = self.b
        nomes = [getattr(c.get("entity"), "__name__", "") for c in cd]
        inteira = len(cd) == 1 and cd[0].get("expr") is cd[0].get("entity")
        if nomes == ["Player"] and inteira:
            return _BRes([b.jogador])
        if nomes == ["DungeonCatalog"] and inteira:
            ids = _masm_ids(sql, "dungeons_catalog.id")
            if ids is not None:
                return _BRes([b.catalogo[i] for i in ids if i in b.catalogo])
            return _BRes([b.catalogo[k] for k in sorted(b.catalogo)])
        if nomes == ["PlayerDungeon", "DungeonCatalog"]:
            # a run aberta noutra masmorra (`dungeon_run_engine.active_run`)
            fora = _re_b.search(r"player_dungeons\.dungeon_id != (\d+)", sql)
            so = _masm_ids(sql, "player_dungeons.dungeon_id")
            abertas = [(p, b.catalogo[i]) for i, p in sorted(b.pds.items())
                       if int(p.current_floor or 0) > 0
                       and (fora is None or i != int(fora.group(1)))
                       and (so is None or fora is not None or i in so)]
            return _BRes(abertas[:1], first=(abertas[0] if abertas else None))
        if nomes == ["PlayerDungeon"] and inteira:
            ids = _masm_ids(sql, "player_dungeons.dungeon_id")
            if ids is None:
                return _BRes(list(b.pds.values()))
            return _BRes([b.pds[i] for i in ids if i in b.pds])
        if nomes and all(n == "PlayerDungeon" for n in nomes):
            # as COLUNAS — o "antes"/"depois" de `core/masmorra._ler`
            ids = _masm_ids(sql, "player_dungeons.dungeon_id") or []
            p = b.pds.get(ids[0]) if ids else None
            if p is None:
                return _BRes()
            campos = [c["name"] for c in cd]
            linha = _col_s.namedtuple("LinhaM", campos)(*[getattr(p, c, None) for c in campos])
            return _BRes([linha], first=linha)
        if inteira and nomes in (["HerbCatalog"], ["OreCatalog"], ["PillCatalog"]):
            tab, col = {"HerbCatalog": (b.ervas, "herbs_catalog.id"),
                        "OreCatalog": (b.minerios, "ores_catalog.id"),
                        "PillCatalog": (b.pilulas, "pills_catalog.id")}[nomes[0]]
            ids = _masm_ids(sql, col)
            return _BRes([tab[i] for i in (ids if ids is not None else sorted(tab)) if i in tab])
        if "count(" in sql.lower() or "sum(" in sql.lower():
            return _BRes(scalar=0)
        return _BRes()


_ROTAS_MASMORRA = {
    "dungeons/list": "api_dungeons_list",
    "dungeons/enter": "api_dungeons_enter",
    "dungeons/advance": "api_dungeons_advance",
    "dungeons/retreat": "api_dungeons_retreat",
}


def _masmorra_com_remendos(fazer):
    """Corre `fazer(sessao)` (uma corrotina) com o servidor remendado para as
    masmorras em memória — e repõe TUDO no fim, aconteça o que acontecer."""
    import core.webserver as _Wm
    import core.portas as _POm
    import database.db as _DBm
    import core.combat_engine as _CEm
    import core.duel_engine as _DEm
    import handlers.dungeons as _HDm
    b = _MASMORRA
    sessao = _MSessao(b)

    async def _hp_par(session, player):
        return float(player.current_hp), float(player.max_hp)

    async def _andar(session, player, dungeon, target_floor, difficulty, lang,
                     stance="balanced", focus_tech_id=0):
        # o COMBATE é encenado; o custo de Qi é o da rota e o espólio é o REAL
        import random as _rnd_m
        custo = _Wm._dungeon_eff_qi_cost(int(dungeon.qi_cost_per_floor), int(player.realm or 0))
        player.qi = max(0.0, float(player.qi or 0) - float(custo))
        player.current_hp = max(1.0, float(player.current_hp) - 0.02 * float(player.max_hp))
        if _MASM_MORTE:
            return False, "", {}
        _rnd_m.seed(int(dungeon.id) * 1000 + int(target_floor))
        loot = _HDm._apply_difficulty_loot_mult(
            _HDm._roll_floor_loot(dungeon.drops or {}, difficulty, min_realm=int(dungeon.min_realm or 0)),
            difficulty)
        return True, "", loot

    async def _transferir(session, player, bag):
        # o inventário não vive no arnês: as pedras entram, o resto fica dito
        player.spirit_stones = int(player.spirit_stones or 0) + int((bag or {}).get("stones") or 0)

    async def _chefe(session, player, archetype=None, difficulty=None, source=None,
                     context=None, npc_realm=None, **k):
        b.chefe = {"ctx": dict(context or {}), "payload": None, "won": None, "archetype": archetype,
                   "difficulty": difficulty}
        return _NS_b(id="mock-chefe")

    async def _destrancar(session, user_id):
        return 0

    orig = (_Wm.get_session_factory, _POm.onda_on, _DBm.feature_enabled_for_world, _Wm._soul_hp_pair,
            _CEm.get_current_hp, _HDm._do_dungeon_floor, _HDm._transfer_bag_to_inventory,
            _DEm.start_duel_pve, _DEm.unlock_stuck_duels_for_player)
    _Wm.get_session_factory = lambda: (lambda: sessao)
    _POm.onda_on = lambda *a, **k: _bestas_onda()
    _DBm.feature_enabled_for_world = lambda feature, world_key=None: bool(FEATURES.get(feature))
    _Wm._soul_hp_pair = _hp_par
    _CEm.get_current_hp = lambda p: float(p.current_hp)
    _HDm._do_dungeon_floor = _andar
    _HDm._transfer_bag_to_inventory = _transferir
    _DEm.start_duel_pve = _chefe
    _DEm.unlock_stuck_duels_for_player = _destrancar
    try:
        return _aio_b.run(fazer(sessao))
    finally:
        (_Wm.get_session_factory, _POm.onda_on, _DBm.feature_enabled_for_world, _Wm._soul_hp_pair,
         _CEm.get_current_hp, _HDm._do_dungeon_floor, _HDm._transfer_bag_to_inventory,
         _DEm.start_duel_pve, _DEm.unlock_stuck_duels_for_player) = orig


def _masmorra_rota(endpoint, body):
    """Corre o HANDLER REAL da rota sobre as masmorras em memória. None = não é comigo."""
    fn_nome = _ROTAS_MASMORRA.get(endpoint)
    if fn_nome is None:
        return None
    import core.webserver as _Wm
    resp = _masmorra_com_remendos(
        lambda s: getattr(_Wm, fn_nome)({"user_id": _MASM_UID, "payload": dict(body or {})}))
    return json.loads(resp.text)


def _masmorra_chefe_estado():
    """O duelo do Chefe da masmorra, encenado: acaba no 1.o pedido — e o fim corre
    o SETTLE REAL (`_settle_dungeon_boss`) UMA vez. O `masmorra_ganho` sai do
    payload do settle pelo mesmo espelho da rota (`masmorra.no_payload`)."""
    b = _MASMORRA
    if b.chefe is None:
        return None
    if b.chefe["payload"] is None:
        import core.pve_duel_settle as _PDSm
        won = not _MASM_CHEFE_PERDE
        duelo = _NS_b(id="mock-chefe", pve_context=dict(b.chefe["ctx"]), action_log=[], round_idx=3)
        b.chefe["payload"] = _masmorra_com_remendos(
            lambda s: _PDSm._settle_dungeon_boss(s, duelo, b.jogador, won)) or {}
        b.chefe["won"] = won
    pay = b.chefe["payload"]
    won = b.chefe["won"]
    out = {
        "ok": True, "duel_id": "mock-chefe", "state": "finished", "round_idx": 3, "max_rounds": 10,
        "sudden_death": False, "winner_id": _MASM_UID if won else 0,
        "you_side": "a", "pve": True, "npc_archetype": b.chefe.get("archetype") or "boss",
        "npc_difficulty": b.chefe.get("difficulty") or "normal", "pve_source": "dungeon_boss",
        "you": {"telegram_id": _MASM_UID, "dao_name": PLAYER.get("dao_name") or "Cultivador",
                "hp": float(b.jogador.current_hp), "hp_max": float(b.jogador.max_hp),
                "combat_qi": 40, "combat_qi_max": 120, "techniques": [], "pending": None},
        "opponent": {"telegram_id": None, "dao_name": "Guardião do Fundo",
                     "hp": 0 if won else 880000, "hp_max": 880000,
                     "combat_qi": 0, "combat_qi_max": 100, "submitted": True},
        "action_log": [], "expires_at": _dt_b.datetime.now(_dt_b.timezone.utc).isoformat(),
    }
    if pay.get("tribute_line"):
        out["tribute_line"] = pay["tribute_line"]
    if pay.get("masmorra_ganho") and _bestas_onda():
        from core import masmorra as _MASM_DONO
        out.update(_MASM_DONO.no_payload(pay["masmorra_ganho"], lambda k: bool(FEATURES.get(k))))
    return out


# ── A MOCHILA (`api_inventory`) ──────────────────────────────────────────────
# ⚠️ Tambem faltava, e a mochila e' o item 1 da conversao: e' a unica tela que
# serve os QUATRO conteudos (artefacto/pilula/erva/minerio) e a unica onde os 51
# artefactos ilustrados podem aparecer. As chaves sao as de `api_inventory`
# (core/webserver.py) e os nomes/graus vem de `artifacts_seeds.py`/`alchemy_seeds.py`.
# ⚠️ `quality` aqui e' a QUALIDADE DE FORJA (inferida, `normal|perfect|divine|
# spirit|refined`) — NAO e' o posto. O posto do artefacto e' o `grade` 0..8.

# Os nomes em pt vem dos locales REAIS, nao de uma copia a' mao: uma segunda
# tabela divergiria no dia seguinte (Lei F-7 §2).


def _art(aid, cat, name, atype, emoji, grade, slot, equipped, quality,
         bp, locked=False, spirit=False, min_realm=0):
    # 名 2026-09-14 — O ARNES TEM DE MENTIR COMO O SERVIDOR MENTE. Em producao
    # o `name` vai TRADUZIDO e a chave da arte vai a' parte; um mock que mande o
    # nome cru nas duas coisas nunca mostraria o defeito que este lote corrige
    # (a arte a desaparecer em pt e es). O `art_key` e' sempre o canonico.
    return {
        "id": aid, "catalog_id": cat,
        "name": _PT_NOMES.get(("art", cat), name), "art_key": name,
        "type": atype,
        "emoji": emoji, "description": "", "grade": grade,
        "grade_name": ["Mortal", "Yellow", "Mystic", "Earth", "Heaven",
                       "Spirit", "Divine", "Dao", "Celestial"][grade],
        "slot": slot, "is_equipped": equipped, "locked": locked,
        "enchant_rune": None, "has_spirit": spirit, "spirit_name": None,
        "min_realm": min_realm, "base_stats": {"battle_power": bp},
        "custom_stats": {"battle_power": bp}, "quality": quality,
    }


def _pilula_seed(cat):
    from database.seeds.alchemy_seeds import PILLS as _PS
    return next((p for p in _PS if p.get("id") == cat), None)


def _itm(itype, cat, name, emoji, qty, quality="normal", timed=False, tier=1):
    # 名 2026-09-14 — mesmo contrato do `_art`: nome traduzido + chave canonica.
    # ⚠️ 🎒 3.2 (30/09) — a chave da PILULA sai dos SEEDS pelo id, como no
    # servidor (`art_key` = nome cru do catalogo). O `name` escrito a' mao nas
    # chamadas de baixo mentia: a 9 dizia "Heaven Defying Pill" e a 31
    # "Immortal Ascension Pill", e nos seeds sao "Soul Clarity Pill" e "Qi
    # Condensation Pill" — a carta procurava a arte de OUTRA pilula.
    _ps = _pilula_seed(cat) if itype == "pill" else None
    e = {"type": itype, "catalog_id": cat,
         "name": _PT_NOMES.get((itype, cat), name),
         "art_key": _ps["name"] if _ps else name,
         "emoji": emoji,
         "description": "", "quality": quality, "quantity": qty}
    if itype == "pill":
        e["required_alchemy_tier"] = int(_ps.get("required_alchemy_tier") or tier) if _ps else tier
        e["effect_type"] = _ps["effect_type"] if _ps else "cb_boost"
        e["duration_minutes"] = int(_ps.get("duration_minutes") or 0) if _ps else (60 if timed else 0)
        e["is_timed"] = bool(e["duration_minutes"] > 0 or e["effect_type"] == "revive")
    return e


def _pill_info(body):
    """`pill/info` pela parte PURA da rota (`core.webserver._scale_pill_display`)
    e pelos seeds. ⚠️ 🎒 3.2: caia no catch-all (`ok: true` sem `pill`) e o
    `PillUsePanel` rebentava a aba inteira ao ler `info.pill.effect_type` — o
    arnes nao deixava OLHAR o detalhe de uma pilula. Em producao a rota recusa
    com 400/404 (o `api()` lanca e o painel diz o erro)."""
    import types as _types
    from core.webserver import _scale_pill_display as _sc
    try:
        pid = int((body or {}).get("pill_id"))
    except (TypeError, ValueError):
        return {"error": "invalid_pill_id"}
    q = ((body or {}).get("quality") or "normal").lower()
    ps = _pilula_seed(pid)
    if not ps:
        return {"error": "pill_not_found"}
    obj = _types.SimpleNamespace(**{k: ps.get(k) for k in (
        "id", "name", "emoji", "description", "effect_type", "effect_value",
        "duration_minutes", "min_realm", "required_alchemy_tier")})
    stock = {}
    for it in INVENTORY["items"]:
        if it["type"] == "pill" and it["catalog_id"] == pid:
            stock[it["quality"]] = stock.get(it["quality"], 0) + int(it["quantity"])
    from core.alchemy_engine import BULK_REFILL_TYPES as _BR
    return {"ok": True,
            "pill": {"id": pid, "name": _PT_NOMES.get(("pill", pid), ps["name"]),
                     "emoji": ps.get("emoji") or "💊", "description": ps.get("description") or "",
                     "effect_type": ps["effect_type"], "effect_value": float(ps["effect_value"]),
                     "duration_minutes": int(ps.get("duration_minutes") or 0),
                     "min_realm": int(ps.get("min_realm") or 0),
                     "required_alchemy_tier": int(ps.get("required_alchemy_tier") or 1)},
            "quality": q, "scaled": _sc(obj, q), "stock_by_quality": stock,
            "effectiveness": 1.0, "active_buff_conflict": None,
            "supports_bulk": (ps["effect_type"] == "stat_boost" or ps["effect_type"] in _BR)}


INVENTORY = {
    "artifacts": [
        _art(101, 8, "Heaven's Edge", "weapon", "⚡", 4, "weapon", True, "divine", 900),
        _art(102, 15, "Heaven Guardian Mail", "armor", "⚡", 4, "armor", True, "perfect", 200),
        _art(103, 20, "Spirit Bead Bracelet", "accessory", "\U0001f4ff", 2, "accessory1", True, "normal", 0),
        # o quarto slot fica VAZIO de proposito — e' o estado que a carta-fantasma
        # tem de saber dizer por palavras ("ACESSORIO · VAZIO").
        _art(104, 10, "Divine Cosmic Blade", "weapon", "\U0001f48e", 6, None, False, "spirit", 3000, spirit=True),
        # ⚠️ 器 2026-09-10 — os TRES patamares tem de estar todos na tela, senao
        # o ornamento do topo desenha-se sem nunca ter sido visto. O grau mais
        # alto encenado era 6 (= notavel); faltava o CELESTE. Pecas reais de
        # `artifacts_seeds.py`, com o grau verdadeiro e com arte no indice.
        _art(110, 46, "Celestial Sundering Blade", "weapon", "\u2600\ufe0f", 8, None, False, "divine", 9000, min_realm=8),
        _art(111, 11, "Dao Annihilation Lance", "weapon", "\U0001f49c", 7, None, False, "normal", 6000),
        _art(105, 1, "Black Iron Sword", "weapon", "⚔️", 0, None, False, "normal", 50),
        _art(106, 4, "Flaming Sword", "weapon", "\U0001f525", 2, None, False, "refined", 250, locked=True),
        _art(107, 13, "Azure Dragon Robe", "armor", "\U0001f409", 2, None, False, "normal", 40),
        _art(108, 22, "Void Eye Pendant", "accessory", "\U0001f441️", 4, None, False, "perfect", 0),
        _art(109, 2, "Spiritual Linen Tunic", "armor", "\U0001f94b", 0, None, False, "normal", 0),
    ],
    "items": [
        # ⚠️ o `tier` nunca era passado, portanto as tres pilulas nasciam
        # `required_alchemy_tier` 1 — e a "Heaven Defying Pill" e' **4** nos
        # seeds. O lombo desenhava 1 de 5 para todas e nenhuma chegava ao topo.
        _itm("pill", 1, "Qi Gathering Pill", "\U0001f48a", 7, "high", True, tier=1),
        # 🎒 3.2 — os ids REAIS (14 e 19): o 9 e o 31 eram OUTRAS pilulas nos
        # seeds (Soul Clarity e Qi Condensation), e a arte procurada era a delas.
        _itm("pill", 14, "Heaven Defying Pill", "\U0001f31f", 1, "heavenly", tier=4),
        _itm("pill", 2, "Foundation Pill", "\U0001f3ef", 3, "perfect", tier=2),
        _itm("pill", 19, "Immortal Ascension Pill", "\U0001f320", 2, "heavenly", tier=5),
        # ⚠️ ervas e minerios NAO tem arte (ARTE_PROVENIENCIA §2.5) — e e' por
        # isso que tem de haver aqui: sao a prova de que o VERSO honesto aguenta
        # uma familia inteira sem ilustracao, ao lado de uma que tem.
        _itm("herb", 1, "Qi Root Herb", "\U0001f331", 12),
        _itm("herb", 2, "Spirit Grass", "\U0001f33f", 4),
        _itm("herb", 4, "Soul Herb", "\U0001f47b", 1),
        _itm("ore", 1, "Iron Ore", "\U0001faa8", 240),
        _itm("ore", 3, "Spirit Stone Ore", "\U0001f48e", 18),
    ],
    # ⚠️ 30/09 — o anel encenado era IMPOSSIVEL: tier 3 com 150 lugares e a
    # expansao a 12.000, quando o dono (`handlers/inventory.py`) da' 200 ao
    # tier 3 e cobra 25.000 pela seguinte. Era a armadilha de sempre (o arnes
    # mente antes do codigo). O bloco passa a ser montado mais abaixo pelo
    # MESMO dono que o servidor usa — ver `_anel_encenado`.
    "ring": None,
}


# ── 🎒 3.2 — o que a mochila tem FORA das tres familias ─────────────────────
# O servidor nomeava estes tipos `f"{itype} #{iid}"` e o ecra mostrava
# "technique_scroll #12". Os tipos e os ids sao os que existem em PRODUCAO
# (`tools/db_readonly_anel_0930.py` §E: pergaminhos 1..30, armadilha 0, nucleo 0,
# planta 1, bilhete 0), e o nome sai do DONO (`core/itens.py`) com a mesma
# conta do `api_inventory` — nunca escrito a' mao aqui.
def _outro(itype, iid, qty):
    from core import itens as _I
    from core.i18n import catalog_text as _ct
    _sc = None
    if itype == "technique_scroll":
        from database.seeds.combat_seeds import TECHNIQUES as _TS
        _sc = next(((x["name"], x.get("emoji")) for x in _TS if x.get("id") == iid), None)
    nome = _I.nome(LANG, itype, iid,
                   tecnica=(_ct(LANG, "tech", iid, "name", _sc[0]) if _sc else None))
    return {"type": itype, "catalog_id": iid, "name": nome,
            "art_key": _sc[0] if _sc else nome,
            "emoji": (_sc[1] if _sc and _sc[1] else _I.emoji(itype)),
            "description": "", "quality": "normal", "quantity": qty}


# NV_OUTROS=0 tira-os (o estado de quem nao tem nada fora das tres familias).
if (os.environ.get("NV_OUTROS") or "1").strip() != "0":
    INVENTORY["items"] += [
        _outro("technique_scroll", 1, 3),
        _outro("technique_scroll", 6, 1),
        _outro("beast_trap", 0, 12),
        _outro("beast_core", 0, 4),
        _outro("blueprint", 1, 2),
        _outro("gacha_ticket", 0, 1),
    ]


# ── 💍 O ANEL ENCENADO — pelo DONO (`core/anel.py`), o mesmo do servidor ─────
#   NV_ANEL=3  (default) — tier 3, 200 lugares: ha' proxima expansao
#   NV_ANEL=1            — tier 1, 50 (o inicio: 147 dos 237 aneis do `main`)
#   NV_ANEL=4p           — tier 4 com +10 comprados no Pavilhao (510) — o anel
#                          a quem o botao do chat anunciava 1000 em vez de 1010
#   NV_ANEL=5            — o topo: sem proxima expansao
#   NV_ANEL_PEDRAS=N     — as pedras para a expansao (defeito: as do PLAYER)
class _AnelRow:
    def __init__(self, tier, max_slots):
        self.tier, self.max_slots = tier, max_slots


def _anel_onda():
    from core.portas import onda_on as _oo
    return _oo(lambda k: bool(FEATURES.get(k)))


def _anel_usados():
    # a mesma conta do `_count_used_slots`: linhas distintas das tres tabelas
    return len(INVENTORY["artifacts"]) + len(INVENTORY["items"])


_ANEL_MODO = (os.environ.get("NV_ANEL") or "3").strip().lower()
from core import anel as _ANEL_DONO  # noqa: E402
_ANEL = (_AnelRow(4, _ANEL_DONO.RING_MAX_SLOTS[4] + 10) if _ANEL_MODO == "4p"
         else _AnelRow(int(_ANEL_MODO) if _ANEL_MODO.isdigit() else 3, None))
if _ANEL.max_slots is None:
    _ANEL.max_slots = _ANEL_DONO.RING_MAX_SLOTS.get(_ANEL.tier, 50)
if os.environ.get("NV_ANEL_PEDRAS"):
    PLAYER["spirit_stones"] = int(os.environ["NV_ANEL_PEDRAS"])


def _anel_encenado():
    INVENTORY["ring"] = _ANEL_DONO.retrato(_ANEL.tier, _ANEL.max_slots,
                                           _anel_usados(), _anel_onda())
    return INVENTORY["ring"]


def _anel_expande():
    """A MESMA sequencia do `api_inventory_ring_upgrade`: recusa no topo,
    recusa sem pedras, cobra, `expandir`, e a resposta pelo dono."""
    cost = _ANEL_DONO.custo_proximo(_ANEL.tier)
    if cost is None:
        return {"ok": False, "reason": "ring_max"}
    pedras = int(PLAYER.get("spirit_stones") or 0)
    if pedras < cost:
        return {"ok": False, "reason": "not_enough_stones", "cost": cost, "have": pedras}
    PLAYER["spirit_stones"] = pedras - cost
    ad = _ANEL_DONO.expandir(_ANEL)
    _anel_encenado()
    return _ANEL_DONO.resposta_expansao(_ANEL, cost, PLAYER["spirit_stones"], ad,
                                        _anel_onda())


_anel_encenado()


# ── 圖 O MAPA — o `world/cavern`, e porque' ele precisa dos DOIS estados ─────
# A cena da Caverna tem UMA porta com estado vivo (o Salao), e o estado que
# interessa olhar e' o APAGADO: e' o do jogador que ainda nao estabeleceu a
# caverna, que e' a maioria de quem comeca.
#
# ⚠️ A forma e' a do `core/cavern_engine.project_cavern`, campo a campo. Um mock
# com a forma errada e' uma mentira dita no codigo certo: estar-se-ia a julgar
# uma tela que desenha `undefined`.
#   NV_CAVERN=open  (default) — estabelecida, com qi acumulado  ⇒ porta ACESA
#   NV_CAVERN=none            — por estabelecer                 ⇒ porta APAGADA
CAVERN_STATE = (os.environ.get("NV_CAVERN") or "open").strip().lower()
CAVERN = ({
    "ok": True, "has_cavern": False,
    "continent": "linghe", "qi": 812.0, "qi_capacity": 1400, "stones": 41200,
    "establish_cost_stones": 5000, "establish_materials": [], "can_establish": True,
    "rate_per_hour_preview": 18.0, "cap_hours": 24,
} if CAVERN_STATE == "none" else {
    "ok": True, "has_cavern": True,
    "continent": "linghe", "continent_name": "Vale Linghe",
    "qi": 812.0, "qi_capacity": 1400, "stones": 41200,
    "accrued_qi": 437.0, "rate_per_hour": 18.0, "cap_hours": 24,
    "active_formation_id": None, "formation": None,
})


# ── ⚒️ A FORJA EM LOTE — a parede de 50 cartas (report [jogador] 10/09) ────────────
#
# PORQUE ISTO EXISTE: o `ForgeResultModal` ramifica por quantidade (<=3 lista
# rica · >=4 grelha de `ArtifactCell`), e desde o 器 O ITEM VIVO cada celula
# dessas e' uma carta ILUSTRADA. Uma forja de 50 desenha 50 cartas pintadas de
# 54px dentro de um modal com altura limitada. Nenhuma suite ve' isso — so' se
# ve' a SERVIR E OLHAR (Lei 0 passo 3), e para olhar e' preciso chegar la'.
#
# ⚠️ A FORMA E' A DO SERVIDOR, campo a campo: `api_forge_craft` devolve
# `bulk`/`crafts_requested`/`crafts_done`/`results`/`artifacts_created`, e cada
# artefacto vem de `_artifact_payload` (id, catalog_id, name, emoji, type,
# grade, grade_name, slot, is_equipped, locked, has_spirit, stats, quality...).
# Um mock com a forma errada julga uma tela que desenha `undefined`.
#
#   NV_FORGE=50   quantos artefactos o lote devolve (default 50)
#   NV_FORGE=3    o outro ramo — a lista rica de 1-3
FORGE_N = max(0, min(50, int(os.environ.get("NV_FORGE") or 50)))

# Nomes REAIS de `artifacts_seeds.py` que tem arte no indice (senao a parede
# que se olha nao e' a parede que o jogador ve').
_FORGE_NAMES = [
    ("Black Iron Sword", "⚔️", "weapon", 0), ("Flaming Sword", "\U0001f525", "weapon", 2),
    ("Iron Scale Vest", "\U0001f6e1\ufe0f", "armor", 1), ("Jade Pendant", "\U0001f48d", "accessory", 1),
    ("Mystic Tiger Fang", "\U0001f42f", "weapon", 2), ("Earth Cleaver", "\U0001faa8", "weapon", 3),
    ("Azure Dragon Robe", "\U0001f409", "armor", 2), ("Spirit Wind Blade", "\U0001f4a8", "weapon", 3),
    ("Ancient Copper Ring", "\U0001f4ff", "accessory", 1), ("Earth Core Plate", "\U0001faa8", "armor", 3),
    ("Spiritual Linen Tunic", "\U0001f94b", "armor", 0), ("Spirit Bead Bracelet", "\U0001f4ff", "accessory", 2),
    ("Fanged Shadow Blade", "\U0001f311", "weapon", 4), ("Heaven's Edge", "⚡", "weapon", 4),
    ("Void Eye Pendant", "\U0001f441\ufe0f", "accessory", 4), ("Divine Cosmic Blade", "\U0001f48e", "weapon", 6),
]
_FORGE_GRADE_NAMES = ["Mortal", "Yellow", "Mystic", "Earth", "Heaven",
                      "Spirit", "Divine", "Dao", "Celestial"]


def _forge_art(i):
    name, emoji, atype, grade = _FORGE_NAMES[i % len(_FORGE_NAMES)]
    # um punhado de graus altos no meio do lote — o jogador quer ver o bom
    # achado sem ter de procurar, e e' isso que a ordenacao promete.
    if i == 4:
        name, emoji, atype, grade = "Celestial Sundering Blade", "\u2600\ufe0f", "weapon", 8
    elif i == 9:
        name, emoji, atype, grade = "Dao Annihilation Lance", "\U0001f49c", "weapon", 7
    bp = 50 + grade * 420 + (i % 7) * 13
    # 冶 3.1 — o nome TRADUZIDO e a chave canonica ao lado, como o
    # `_artifact_payload` real (o mock mandava o ingles e achava a arte pelo nome).
    _aid = next((x["id"] for x in (_S_ARTS if _OFC else []) if x["name"] == name), 1)
    return {
        "quality": ["normal", "refined", "perfect", "divine"][i % 4],
        "id": 9000 + i, "catalog_id": _aid, "name": _of_nome("art", _aid, name),
        "art_key": name,
        "emoji": emoji, "type": atype, "grade": grade,
        "grade_name": _FORGE_GRADE_NAMES[grade],
        "slot": None, "is_equipped": False,
        "locked": (i % 17 == 3), "has_spirit": (i == 4),
        "spirit_name": None, "enchant_rune": None,
        "stats": {"battle_power": bp, "attack": 20 + grade * 9,
                  "defense": 10 + grade * 6},
        "min_realm": 0, "description": "",
    }


def _forge_result(n, rid=1):
    if OFICIO_ROTO:
        raise RuntimeError("forja encenada rota (NV_OFICIO_ROTO)")
    from core.forge_engine import FORGE_MASTERY_LEVELS, MAX_FORGE_MASTERY, MAX_FORGE_TIER
    antes = {"oficio": _OFC.retrato_forja(_of_skill(_OF["frg"])),
             "receita": _OFC.retrato_receita_forja(_of_maestria_f(rid))}
    _xp = 25 * n
    _OF["frg"] = _of_sobe(_OF["frg"], _FRG_TIERS, MAX_FORGE_TIER, _xp)
    _of_maestria_sobe(_OF["m_forja"], rid,
                      {k: v["forges_req"] for k, v in FORGE_MASTERY_LEVELS.items()},
                      MAX_FORGE_MASTERY, n)
    g = _OFC.ganho_forja(antes, _of_skill(_OF["frg"]), _of_maestria_f(rid))
    _rj, _rm = g["oficio"]["depois"], g["receita"]["depois"]
    arts = [_forge_art(i) for i in range(n)]
    divine = sum(1 for a in arts if a["quality"] == "divine")
    perfect = sum(1 for a in arts if a["quality"] == "perfect")
    success = len(arts) - divine - perfect
    return {
        "ok": True, "bulk": n > 1, "crafts_requested": n,
        "crafts_done": n, "early_stop_reason": None,
        "results": {"failure": max(0, n // 9), "success": success,
                    "perfect": perfect, "divine": divine},
        "artifacts_created": arts,
        "spirit_awakened": n >= 10, "charm_saved": False,
        "xp_gain": _xp, "forge_tier": _rj["tier"], "forge_xp": _rj["xp"],
        "forge_xp_to_next": _rj["xp_to_next"], "forge_at_max": _rj["at_max"],
        "leveled_up": "oficio" in g["acende"], "mastery_level": _rm["level"],
        "mastery_count": _rm["forges_count"],
        "mastery_leveled_up": "receita" in g["acende"],
        **_OFC.no_payload(g, _of_flag),
    }




# ── 星 2.1 O CORPO — os estados da figura que acende ─────────────────────────
# ⚠️ A FORMA vem dos MOTORES, nao da minha mao. `project_body_for_display`,
# `can_temper`, `perform_mortal_temper`, `project_meridians`, `start_ritual` e
# `attempt_break` correm aqui sobre um jogador em memoria — e' a unica maneira
# de o ecra servido ver exactamente os campos que o servidor manda (4 lotes
# desta casa ja' olharam para um mock com a forma errada). So' o que precisa de
# BASE DE DADOS e' neutralizado: as flags (ON, que e' o que se quer ver), o
# lugar do refino (None / 1.0) e o 1o-do-servidor (Falso).
#
#   NV_CORPO=zero   Reino 0 · refino 0/7 · pode forjar
#            meio   Reino 3 · refino 2/7 · pode forjar          (defeito)
#            cap    Reino 3 · refino 4/7 · limite do reino
#            max    Reino 6 · refino 7/7
#            r7     Reino 7 · Transformacoes 0/12 · 2 canais
#            apex   Reino 8 · Transformacoes 5/12 · 7 canais + ritual PRONTO
#   NV_MER_SORTE=falha|sucesso   o rompimento (defeito: falha — o caso honesto)
#   NV_CORPO_ROTO=transf|mer     essa leitura responde erro (o ecra nao inventa zeros)
CORPO_STATE = (os.environ.get("NV_CORPO") or "").strip().lower()
_MER_SORTE = (os.environ.get("NV_MER_SORTE") or "falha").strip().lower()
_CORPO_ROTO = (os.environ.get("NV_CORPO_ROTO") or "").strip().lower()
_CORPO = None
if CORPO_STATE:
    import asyncio as _aio
    import datetime as _dt
    from types import SimpleNamespace as _NS
    import core.body_tempering_engine as _bte
    import core.meridian_engine as _mer
    _bte._cultivo_corpo_on = lambda *a, **k: True
    _mer.corpo_profundo_on = lambda *a, **k: True

    async def _sem_lugar(*a, **k):
        return None

    async def _mult_neutro(*a, **k):
        return {"mult": 1.0, "place_key": None}

    async def _nunca_primeiro(*a, **k):
        return False
    _mer.refine_place_view = _sem_lugar
    _mer.refine_place_mult = _mult_neutro
    _mer._is_first_open_on_server = _nunca_primeiro

    class _Sorte:
        def random(self):
            return 0.0 if _MER_SORTE == "sucesso" else 0.999
    _mer.random.Random = _Sorte

    def _iso(d):
        return d.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    _agora = _dt.datetime.now(_dt.timezone.utc)
    _base = dict(realm=3, mortal_body_level=2, mortal_temper_progress=60,
                 spirit_stones=184320, qi=5200.0, qi_capacity=8000.0,
                 battle_power=48200, body_tempering_level=0,
                 body_tempering_progress=0, celestial_essence=0,
                 meridians_opened={}, meridian_ritual=None, hunt_essence=40,
                 language=LANG, telegram_id=123456789, body_transformed=False,
                 sub_layer=4, cultivation_base=0, prestige_level=0)
    _estados = {
        "zero": dict(realm=0, mortal_body_level=0),
        "meio": dict(),
        "cap":  dict(mortal_body_level=4),
        "max":  dict(realm=6, mortal_body_level=7),
        "r7":   dict(realm=7, mortal_body_level=7, body_tempering_level=0,
                     battle_power=900000, spirit_stones=2400000, qi=9000.0,
                     body_tempering_progress=40,
                     meridians_opened={"pulmao": {"opened_at": _iso(_agora - _dt.timedelta(days=9))},
                                       "intestino_grosso": {"opened_at": _iso(_agora - _dt.timedelta(days=3))}}),
        "apex": dict(realm=8, mortal_body_level=7, body_tempering_level=5,
                     battle_power=9000000, spirit_stones=90000000, qi=90000.0,
                     body_tempering_progress=180, celestial_essence=0,
                     meridians_opened={k: {"opened_at": _iso(_agora - _dt.timedelta(days=12 - i))}
                                       for i, k in enumerate(["pulmao", "intestino_grosso", "estomago",
                                                              "baco", "coracao", "intestino_delgado",
                                                              "bexiga"])},
                     meridian_ritual={"channel": "rim", "stage": "circulate",
                                      "started_at": _iso(_agora - _dt.timedelta(hours=9)),
                                      "ends_at": _iso(_agora - _dt.timedelta(minutes=5)),
                                      "attempts": 1, "place_key": None, "place_mult": 1.0}),
    }
    _CORPO = _NS(**dict(_base, **_estados.get(CORPO_STATE, {})))
    PLAYER["realm"] = _CORPO.realm


def _corpo_bc():
    return _bte.project_body_for_display(_CORPO, eff_qi_cap=_CORPO.qi_capacity)


def _corpo_status():
    """A forma do `api_body_tempering_status`, pelo mesmo motor."""
    from core.body_tempering_engine import (get_tempering_info, get_next_level_info,
                                            can_temper, MAX_TEMPERING_LEVEL,
                                            MIN_REALM_REQUIRED, TEMPERING_LEVELS)
    p = _CORPO
    cur = int(p.body_tempering_level or 0)
    ci = get_tempering_info(cur)
    out = {"ok": True, "unlocked": p.realm >= MIN_REALM_REQUIRED,
           "min_realm_required": MIN_REALM_REQUIRED, "realm": p.realm,
           "current_level": cur, "max_level": MAX_TEMPERING_LEVEL,
           "current_info": {"name_key": ci["name_key"], "emoji": ci.get("emoji", ""),
                            "hp_def_mult": float(ci["hp_def_mult"])},
           "body_tempering_progress": p.body_tempering_progress,
           "spirit_stones": p.spirit_stones, "qi": p.qi,
           "celestial_essence": p.celestial_essence,
           "levels": [{"level": lv, "name_key": inf["name_key"],
                       "min_realm": int(inf.get("min_realm", MIN_REALM_REQUIRED))}
                      for lv, inf in sorted(TEMPERING_LEVELS.items())
                      if 1 <= lv <= MAX_TEMPERING_LEVEL]}
    nx = get_next_level_info(cur)
    if nx is None:
        out["next"] = None
        return out
    chk = can_temper(p, total_battle_power=p.battle_power)
    out["total_battle_power"] = p.battle_power
    out["next"] = {"level": cur + 1, "name_key": nx["name_key"], "emoji": nx.get("emoji", ""),
                   "hp_def_mult": float(nx["hp_def_mult"]), "cost_stones": nx["cost_stones"],
                   "cost_qi": nx["cost_qi"], "min_battle_power": nx["min_battle_power"],
                   "progress_required": nx["progress_required"],
                   "min_realm": int(nx.get("min_realm", MIN_REALM_REQUIRED)),
                   "essence_cost": int(nx.get("essence_cost", 0)),
                   "can_ascend": bool(chk["can"]), "blocked_reason_key": chk.get("reason_key")}
    return out


def _corpo(endpoint):
    """None = este endpoint nao e' do Corpo (segue para o resto do `canned`)."""
    if _CORPO is None:
        return None
    if endpoint == "body_tempering/status":
        if _CORPO_ROTO == "transf":
            raise RuntimeError("roto")
        return _corpo_status()
    if endpoint == "world/meridians":
        if _CORPO_ROTO == "mer":
            raise RuntimeError("roto")
        return _aio.run(_mer.project_meridians(None, _CORPO, lang=LANG))
    if endpoint == "world/body_temper":
        chk = _bte.can_temper_mortal(_CORPO, eff_qi_cap=_CORPO.qi_capacity)
        if not chk["can"]:
            return {"ok": False, "reason": chk["reason_key"], "cost": chk.get("cost")}
        res = _bte.perform_mortal_temper(_CORPO, eff_qi_cap=_CORPO.qi_capacity)
        return dict({"ok": True}, **res) if res.get("success") else {"ok": False, "reason": res.get("reason_key")}
    if endpoint == "body_tempering/ascend":
        chk = _bte.can_temper(_CORPO, total_battle_power=_CORPO.battle_power)
        if not chk["can"]:
            return {"ok": False, "reason": chk.get("reason_key") or "blocked"}
        res = _bte.perform_tempering(_CORPO)
        return {"ok": True, "new_level": res["new_level"], "mult": res["mult"],
                "name_key": res["name_key"], "qi_cap_bonus": res["qi_cap_bonus"],
                "power_delta": None}
    if endpoint == "world/meridian_start":
        return _aio.run(_mer.start_ritual(None, _CORPO))
    if endpoint == "world/meridian_break":
        return _aio.run(_mer.attempt_break(None, _CORPO))
    return None


# ── 門 P6 — AS PORTAS, pelo dono REAL ────────────────────────────────────────
# O `nav_gates` NAO se escreve aqui a' mao: sai de `core/portas.py`, o mesmo que
# o `api_player` chama, com as flags deste arnes como fonte. Um mock com a forma
# certa e os valores inventados era a mentira de 23/09 outra vez (o arnes
# mandava o nome canonico onde o servidor manda o traduzido).
#   NV_REINO=0..10        o reino encenado (defeito: o do PLAYER, 3)
#   NV_RENASCIDO=0|1      prestige_level (o PLAYER nasce com 1 — e um renascido
#                         mantem TODAS as portas trancadas a' vista, porque ja'
#                         esteve do outro lado delas; para ver o marco, use 0)
#   NV_PORTA_ROTA=faction essa porta chega como `open:null` (estado desconhecido)
_REINO_ENC = (os.environ.get("NV_REINO") or "").strip()
_RENASC_ENC = (os.environ.get("NV_RENASCIDO") or "").strip()
_PORTA_ROTA = (os.environ.get("NV_PORTA_ROTA") or "").strip()


def _portas_no_player():
    if _REINO_ENC:
        PLAYER["realm"] = int(_REINO_ENC)
        # ⚠️ A chegada le' o reino VIVO do `/cultivation` — sem esta linha o ecra
        # dizia "Reino 3" no cabecalho e "voce esta' no Reino 0" na porta, e eu
        # estaria a julgar a consulta por uma contradicao que so' o arnes tem.
        CULTIVATION["realm"] = PLAYER["realm"]
        try:
            with open(os.path.join(ROOT, "miniapp", "i18n", LANG + ".json"),
                      encoding="utf-8") as _fh:
                _nomes = json.load(_fh)
            PLAYER["realm_name"] = _nomes.get("realm_%d" % PLAYER["realm"], PLAYER["realm_name"])
        except Exception:
            pass
    if _RENASC_ENC:
        PLAYER["prestige_level"] = int(_RENASC_ENC)
    from types import SimpleNamespace as _NSp
    from core.portas import onda_on, portas_do_jogador

    def _fl(k):
        return bool(FEATURES.get(k))
    if not onda_on(_fl):
        PLAYER.pop("nav_gates", None)
        return
    g = portas_do_jogador(_NSp(realm=PLAYER["realm"]), _fl)
    if _PORTA_ROTA:
        g[_PORTA_ROTA] = {"open": None}
    PLAYER["nav_gates"] = g


# ── 減 P7 — AS EXPLICACOES, pelo dono REAL ───────────────────────────────────
# Como as portas: o estado NAO se escreve aqui a' mao. Sai de
# `core/explicacoes.py`, o mesmo que o `api_player` e o `settings/update`
# chamam, com as flags deste arnes como fonte — e o `settings/update` e a
# meditacao/equip encenados passam pelas MESMAS funcoes, para se poder ver a
# frase ganhar «Ja' entendi» depois da accao e recolher com o toque.
#   NV_EXPLICA=                (defeito) nada gravado: a 1a vez
#   NV_EXPLICA=apto            todos os sistemas aptos (a accao ja' aconteceu)
#   NV_EXPLICA=recolhido       todos recolhidos
#   NV_EXPLICA=meditar:apto,equipar:recolhido   por sistema
#   NV_EXPLICA_ROTA=1          o `settings/update` rebenta (500): nada muda
_EXPLICA_ENC = (os.environ.get("NV_EXPLICA") or "").strip().lower()
_EXPLICA_ROTA = (os.environ.get("NV_EXPLICA_ROTA") or "").strip() not in ("", "0")


def _explica_fl(k):
    return bool(FEATURES.get(k))


def _explica_jogador():
    from types import SimpleNamespace as _NSe
    from core.explicacoes import SISTEMAS
    _est = {}
    if _EXPLICA_ENC in ("apto", "recolhido"):
        _est = {k: _EXPLICA_ENC for k in SISTEMAS}
    elif _EXPLICA_ENC:
        for _par in _EXPLICA_ENC.split(","):
            if ":" in _par:
                _k, _v = _par.split(":", 1)
                _est[_k.strip()] = _v.strip()
    return _NSe(explicacoes=_est or None)


_EXPLICA_JOG = _explica_jogador()


def _explica_no_player():
    from core.explicacoes import para_payload
    _v = para_payload(_EXPLICA_JOG, _explica_fl)
    if _v is None:
        PLAYER.pop("explicacoes", None)
    else:
        PLAYER["explicacoes"] = _v


def _explica_canned(endpoint, body):
    """As rotas que o P7 toca, pelo dono. None = nao e' comigo."""
    import core.explicacoes as _E
    body = body or {}
    if endpoint == "settings/update" and ("explicacao_recolher" in body
                                          or "explicacoes_repor" in body):
        if _EXPLICA_ROTA:
            raise RuntimeError("NV_EXPLICA_ROTA: o settings/update rebentou")
        if "explicacao_recolher" in body:
            _ok, _why = _E.recolher(_EXPLICA_JOG, str(body.get("explicacao_recolher") or ""),
                                    _explica_fl)
        else:
            _ok, _why = _E.repor(_EXPLICA_JOG, _explica_fl)
        _out = {"ok": bool(_ok)}
        if not _ok:
            _out["reason"] = _why
        _v = _E.para_payload(_EXPLICA_JOG, _explica_fl)
        if _ok and _v is not None:
            _out["explicacoes"] = _v
        return _out
    if endpoint in ("meditate/start", "dao/meditate_start"):
        _E.marcar_apto(_EXPLICA_JOG, "meditar", _explica_fl)
        return {"ok": True}
    if endpoint == "combat/equip_technique" and body.get("equip", True):
        _E.marcar_apto(_EXPLICA_JOG, "equipar", _explica_fl)
        return {"ok": True, "active_count": 1}
    # as accoes do Corpo correm os MOTORES do 2.1 (`_corpo`); so' um `ok`
    # deles marca a camada — a mesma regra do servidor.
    _acao_corpo = {"world/body_temper": "corpo_mortal",
                   "body_tempering/ascend": "corpo_transf",
                   "world/meridian_start": "corpo_mer",
                   "world/meridian_break": "corpo_mer"}.get(endpoint)
    if _acao_corpo:
        _r = _corpo(endpoint)
        if isinstance(_r, dict) and _r.get("ok"):
            _E.marcar_apto(_EXPLICA_JOG, _acao_corpo, _explica_fl)
        return _r
    return None


def canned(endpoint, body=None):
    """Payload encenado. Um endpoint sem caso cai numa forma vazia mas VALIDA —
    o objetivo e' a tela desenhar, nao simular o jogo."""
    _e = _explica_canned(endpoint, body)
    if _e is not None:
        return _e
    _c = _corpo(endpoint)
    if _c is not None:
        return _c
    if endpoint == "player":
        if _CORPO is not None:
            PLAYER["body_cultivation"] = _corpo_bc()
            PLAYER["realm"] = _CORPO.realm
            PLAYER["spirit_stones"] = _CORPO.spirit_stones
        _portas_no_player()
        _explica_no_player()
        return PLAYER
    if endpoint == "cultivation":
        return CULTIVATION
    if endpoint == "home_summary":
        return HOME
    if endpoint == "combat/loadout":
        return LOADOUT
    if endpoint == "alchemy_recipes":
        return _alchemy_payload()
    if endpoint == "alchemy/craft":
        return _alchemy_craft(body)
    # 獸 3.3 — as rotas das bestas correm o HANDLER REAL (ver `_bestas_rota`)
    _b = _bestas_rota(endpoint, body)
    if _b is not None:
        return _b
    # 宗 4.1 — o Pavilhão da Seita corre o HANDLER REAL (ver `_seita_rota`)
    _s = _seita_rota(endpoint, body)
    if _s is not None:
        return _s
    # 幫 4.2 — a Guilda corre o HANDLER REAL (ver `_guilda_rota`)
    _g = _guilda_rota(endpoint, body)
    if _g is not None:
        return _g
    # 層 4.3 — as Masmorras correm o HANDLER REAL (ver `_masmorra_rota`)
    _m = _masmorra_rota(endpoint, body)
    if _m is not None:
        return _m
    if endpoint == "inventory":
        return INVENTORY
    # 🎒 3.2 — caia no catch-all e devolvia `ok: true` SEM numeros: o toast
    # dizia "Anel expandido: undefined slots". Agora passa pelo dono.
    if endpoint == "inventory/ring_upgrade":
        return _anel_expande()
    if endpoint == "pill/info":
        return _pill_info(body)
    # 凶 2026-09-14 — o ecra do CHEFE nao tinha encenacao nenhuma, e por isso
    # nunca se OLHOU para ele. Forma copiada do `api_world_boss` real: nome ja'
    # traduzido + `art_key` canonico ao lado.
    if endpoint == "world_boss":
        # ⚠️ A FORMA E' PLANA — `data.boss` so' leva a ficha do chefe; o dano, a
        # espera e o ranking vivem no TOPO. A 1a versao deste mock aninhou tudo
        # dentro de `boss` e a aba rebentou com `reading 'length'`: eu estaria a
        # olhar para um ecra de erro a fingir que era a tela. Copiado campo a
        # campo do `api_world_boss` real.
        return {
            "boss": {
                "id": 1, "name": "Besta do Vazio", "art_key": "Void Beast",
                "emoji": "☯️", "tier": "mortal", "phase": "normal",
                "hp": 217560000, "current_hp": 217560000,
                "expires_at_ms": int((_time.time() + 5 * 3600) * 1000),
            },
            # ⚠️ `rank` e `name` — nao `dao_name`. A 1a versao usou o nome da
            # COLUNA em vez do nome do CAMPO do payload e o ecra mostrou
            # "#UNDEFINED" nos dois cultivadores. 5a vez neste lote que o arnes,
            # e nao o produto, e' que estava errado.
            "ranking": [
                {"rank": 1, "name": "Ligma", "realm": 4, "realm_emoji": "✨",
                 "total_damage": 1900, "hits": 8, "is_you": False},
                {"rank": 2, "name": "ChristianCangussu", "realm": 3,
                 "realm_emoji": "✨",
                 "total_damage": 220, "hits": 1, "is_you": True},
            ],
            "your_damage": 220, "your_hits": 1, "your_last_hit_ms": 0,
            "cooldown_remaining_ms": 0,
            "player_tier": "mortal", "tier_mismatch": False,
        }
    if endpoint == "world/cavern":
        return CAVERN
    # 圖 V7 (2026-09-15) — a forma e' a de `api_world_events` (webserver §MV-9).
    # ⚠️ Este endpoint FALTAVA ao mock, e a consequencia so' se viu a OLHAR: as
    # 20 portas das ilhas remotas dizem "⛵ <cidade>" e a linha nascia VAZIA
    # aqui, portanto eu estaria a julgar o estado apagado por um ecra que o
    # servidor a serio nunca mostra. E' a licao da WEB-E — *um mock com a FORMA
    # errada e' uma mentira contada no codigo certo*.
    if endpoint == "world/events":
        return {
            "ok": True,
            "events": [],
            "cities": {
                "linghe":  {"key": "linghe_city",  "emoji": "🏙️", "name": "Vale do Espírito"},
                "qianhe":  {"key": "qianhe_city",  "emoji": "🏙️", "name": "Porto dos Mil Rios"},
                "yanshan": {"key": "yanshan_city", "emoji": "🏙️", "name": "Colina das Flores"},
                "fenghuo": {"key": "fenghuo_city", "emoji": "🏙️", "name": "Forja do Fogo"},
                "moyu":    {"key": "moyu_city",    "emoji": "🏙️", "name": "Véu de Tinta"},
            },
        }
    # 武 2.2 — O DUELO, ENCENADO. Este endpoint NAO TINHA CASO nenhum, e por
    # isso a tela de 605 linhas do `DuelArenaModal` nunca foi OLHADA: caia na
    # forma vazia valida, o `state` ficava `null` e o modal mostrava para sempre
    # "Entrando na arena...". Um ecra que nunca se ve' e' um ecra que ninguem
    # mede.
    #
    # A forma e' copiada CAMPO A CAMPO do `get_duel_state` real, incluindo o que
    # este lote mudou: o `name` da tecnica vem TRADUZIDO e o `art_key` canonico
    # anda ao lado (a leitura, nunca a gravacao). E o `action_log` tem os DOIS
    # estados que importam: um lado com tecnica identificada (⇒ destaque
    # legitimo) e o outro a ESQUIVAR com `tech: null` (⇒ sem destaque, que e' o
    # estado honesto).
    #
    # ⚠️ `NV_DUELO` escolhe o que se serve, porque tres estados diferentes tem
    # de ser olhados:
    #   NV_DUELO=live (default) — rodada aberta, relogio a correr
    #   NV_DUELO=r1             — a PRIMEIRA rodada (log vazio: a faixa da
    #                             ultima rodada tem de dizer que ainda nao
    #                             houve nenhuma, nao ficar em branco)
    #   NV_DUELO=fim            — terminado, com as consequencias condicionais
    # as portas que LEVAM ao duelo: sem elas nao ha' como chegar a' cena
    # (o `fight()` punha `setPveDuelId(undefined)` e o modal nunca abria).
    if endpoint in ("combat/npc_duel_create", "combat/duel_create"):
        return {"ok": True, "duel_id": "mock-duelo"}
    if endpoint in ("combat/duel_submit", "combat/duel_forfeit"):
        return {"ok": True}
    if endpoint == "combat/duel_state":
        # 層 4.3 — o duelo do Chefe da masmorra: o fim corre o SETTLE REAL
        if (body or {}).get("duel_id") == "mock-chefe":
            _mc = _masmorra_chefe_estado()
            if _mc is not None:
                return _mc
        import datetime as _dt
        _modo = (os.environ.get("NV_DUELO") or "live").strip().lower()
        _tecs = [
            {"id": 1, "name": "Passo do Trovão", "art_key": "Thunder Step",
             "emoji": "⚡", "effect_type": "evasion", "effect_value": 30.0,
             "effect_round": 1, "qi_cost": 30, "mastery_level": 5,
             "grade": "celestial", "grade_mult": 3.0, "intent_affinity": "sword"},
            {"id": 6, "name": "Palma Celestial", "art_key": "Celestial Palm",
             "emoji": "✋", "effect_type": "damage_mult", "effect_value": 50.0,
             "effect_round": 0, "qi_cost": 45, "mastery_level": 4,
             "grade": "transcendent", "grade_mult": 2.0, "intent_affinity": "fist"},
            {"id": 3, "name": "Corpo de Ferro", "art_key": "Iron Body",
             "emoji": "🌍", "effect_type": "damage_reduce",
             "effect_value": 50.0, "effect_round": 0, "qi_cost": 20,
             "mastery_level": 3, "grade": "perfected", "grade_mult": 1.35,
             "intent_affinity": "body"},
            {"id": 4, "name": "Passo das Sombras", "art_key": "Shadow Step",
             "emoji": "🌑", "effect_type": "dodge", "effect_value": 100.0,
             "effect_round": 0, "qi_cost": 15, "mastery_level": 2,
             "grade": "refined", "grade_mult": 1.15, "intent_affinity": "killing"},
            # a 5a existe de PROPOSITO: e' ela que faz nascer o "Todas as artes
            # (5)" e a seleccao vertical. E custa mais do que o Qi disponivel,
            # portanto tambem encena o estado PRESO.
            {"id": 17, "name": "Golpe Eterno", "art_key": "Eternal Strike",
             "emoji": "⚔️", "effect_type": "armor_ignore",
             "effect_value": 40.0, "effect_round": 0, "qi_cost": 900,
             "mastery_level": 1, "grade": "common", "grade_mult": 1.0,
             "intent_affinity": "sword"},
        ]
        _log = [] if _modo == "r1" else [{
            "round": 1,
            "a": {"tech": {"id": 6, "name": "Palma Celestial",
                           "art_key": "Celestial Palm", "emoji": "✋"},
                  "damage": 1284000},
            # 🔴 a ESQUIVA: `tech` a `null`. Sem tecnica, sem nome e sem
            # destaque — e a tela tem de o aguentar sem inventar nada.
            "b": {"tech": None, "evaded": True, "damage": 0},
        }]
        # 🔴 05/10 — O REPORT ([jogador], 03/10 20:06): *"in PvE arena, popup of
        # combat shows opponent's hp out of bound on screen."* Este mock punha
        # o ADVERSARIO com 7 digitos (4.200.000) e por isso o olhar de 2.2 nunca
        # viu o lado direito transbordar: o NPC da arena tem 10 na producao
        # (medido, `tools/db_readonly_duelo_hp_1005.py`: 909 de 1.009 duelos PvE
        # do `main` em 30 dias; o do report era 1.212.935.443 contra os
        # 557.790.433.292 do jogador, no Beta). O HP passa a ser escolhido:
        #   NV_DUELO_HP=relato    — o duelo do report, numero a numero
        #   NV_DUELO_HP=max   — o maior de sempre no Beta, 13 digitos dos dois lados
        #   NV_DUELO_HP=<hp>/<max>:<hp>/<max>  — jogador:adversario, a mao
        # Sem ele, os numeros de sempre (a OFF-identidade das capturas antigas).
        _hp_pre = {
            "relato": "557790433292/557790433292:1212935443/1212935443",
            "max": "1146050083754/1146050083754:1124861821452/1124861821452",
        }
        _hp_raw = (os.environ.get("NV_DUELO_HP") or "").strip().lower()
        _hp_raw = _hp_pre.get(_hp_raw, _hp_raw) or "158977287826/201000000000:4200000/9000000"
        try:
            _hp_v, _hp_o = [tuple(int(x) for x in lado.split("/"))
                            for lado in _hp_raw.split(":")]
        except ValueError:
            _hp_v, _hp_o = (158977287826, 201000000000), (4200000, 9000000)

        _fim = _modo == "fim"
        _out = {
            "ok": True, "duel_id": "mock-duelo",
            "state": "finished" if _fim else "waiting_actions",
            "round_idx": 1 if _modo == "r1" else 2, "max_rounds": 10,
            "sudden_death": False,
            "winner_id": 123456789 if _fim else None,
            "you_side": "a", "pve": True, "npc_archetype": "bandit",
            "npc_difficulty": "normal",
            "pve_source": (os.environ.get("NV_DUELO_ORIGEM") or "npc_hunt").strip(),
            "you": {"telegram_id": 123456789, "dao_name": "Kuu",
                    "hp": _hp_v[0], "hp_max": _hp_v[1],
                    "combat_qi": 62, "combat_qi_max": 120,
                    "techniques": _tecs, "pending": None},
            "opponent": {"telegram_id": None, "dao_name": "Lobo Cinza",
                         "hp": _hp_o[0], "hp_max": _hp_o[1],
                         "combat_qi": 40, "combat_qi_max": 100,
                         "submitted": _modo != "r1"},
            "action_log": _log,
            "expires_at": _dt.datetime.now(_dt.timezone.utc).replace(
                microsecond=0).isoformat().replace("+00:00", "+00:00")
            if _fim else (_dt.datetime.now(_dt.timezone.utc)
                          + _dt.timedelta(seconds=42)).isoformat(),
        }
        if _fim:
            # as consequencias CONDICIONAIS: o que este lote nao podia perder.
            _out["tribute_line"] = ("O Tributo da Terra levou 12% do espólio "
                                    "— 5.400 pedras ficaram na masmorra.")
            # 道 07/10 — o que os CINCO CAMINHOS ganharam (o report do [jogador]: o
            # caminho subia e nenhum ecra o dizia). A forma sai do DONO
            # (`intent_engine.caminho_ganho`) e so' com a onda, como no servidor;
            # os numeros sao os medidos do [jogador] (Espada R5, 602 de 1.048, um
            # golpe da arte padrao + a vitoria = +18).
            if _bestas_onda():
                from core.intent_engine import caminho_ganho as _cg
                _out["caminho_ganho"] = _cg(
                    {"sword": {"rank": 5, "xp": 602}}, {"sword": 1}, "sword", True,
                    {"results": [{"intent": "sword", "rank": 5, "xp": 620}]})
        return _out
    if endpoint == "combat/default_strike":
        # ⚠️ 30/09 — este mock dizia `ok: true` a QUALQUER id sem nunca passar
        # pela rota: foi assim que o 500 do report (a rota filtrava
        # `PlayerTechnique.is_active`, uma coluna que nao existe) ficou
        # invisivel ao olhar de 13/09. Agora espelha o CONTRATO da rota: recusa
        # a arte que nao esta' na lista elegivel e GUARDA a escolha, para a tela
        # recarregada mostrar o que ficou gravado. A query verdadeira nao se ve
        # daqui (o mock nao tem base) — quem a CORRE e' a `_test_relatos_0814.py` §9.
        _ds = LOADOUT.get("default_strike") or {}
        try:
            _tid = int((body or {}).get("tech_id") or 0)
        except (TypeError, ValueError):
            return {"error": "bad_request"}
        if _tid and _tid not in {e["id"] for e in _ds.get("eligible") or []}:
            return {"ok": False, "reason": "technique_not_equipped"}
        if _ds:
            _ds["current"] = _ds["stored"] = _tid
        return {"ok": True, "default_technique_id": _tid}
    if endpoint == "forge_recipes":
        return _forge_payload()
    # ⚗️ o OUTRO lado da Lei F-7: o report disse "i think also alchemy", e a
    # unica forma honesta de responder e' abrir a tela e OLHAR. A forma e' a de
    # `api_alchemy_craft_bulk` (core/webserver.py).
    if endpoint == "alchemy/craft_bulk":
        return _alchemy_craft(body, bulk=True)
    if endpoint == "forge/craft":
        try:
            _n = int((body or {}).get("count") or FORGE_N)
        except (TypeError, ValueError):
            _n = FORGE_N
        return _forge_result(max(1, min(50, _n)), int((body or {}).get("recipe_id") or 1))
    return {"ok": True, "items": [], "list": [], "entries": [], "events": [],
            "quests": [], "data": {}, "count": 0, "unread": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        path = self.path.split("?")[0]
        prefix = "/api/miniapp/"
        endpoint = path[len(prefix):] if path.startswith(prefix) else ""
        # ⚒️ a forja e' o unico endpoint encenado que LE o pedido: o tamanho do
        # lote e' a variavel que se esta' a julgar, e obrigar a um servidor por
        # tamanho era so' atrito (e o `crafts_requested` do servidor a serio
        # tambem e' o que o cliente pediu).
        body = {}
        if raw:
            try:
                body = json.loads(raw.decode("utf-8")) or {}
            except Exception:
                body = {}
        # 星 2.1 — uma leitura ROTA responde 500, como o servidor a serio
        # quando rebenta; derrubar a ligacao seria outro modo de falha.
        try:
            out = canned(endpoint, body)
        except Exception as _e:
            self._send(500, json.dumps({"ok": False, "error": str(_e)}),
                       "application/json; charset=utf-8")
            return
        self._send(200, json.dumps(out, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def do_GET(self):
        path = self.path.split("?")[0]
        # ⚠️ Nem toda a leitura do cliente e' POST: o `useApi(..., null)`
        # sai em GET, e sem este ramo o ecra do Chefe respondia 404 e eu estaria
        # a olhar para um ecra de erro a fingir que era a tela.
        if path.startswith("/api/miniapp/"):
            self._send(200, json.dumps(canned(path[len("/api/miniapp/"):], {}),
                                       ensure_ascii=False),
                       "application/json; charset=utf-8")
            return
        if path in ("/", "/app", "/miniapp"):
            fp = os.path.join(CLIENT_ROOT, "miniapp", "index.html")
        elif path.startswith("/miniapp/assets/"):
            # 牌 2026-09-05 — o MESMO desvio que o `_MINIAPP_SUBDIR_RULES` do
            # `core/webserver.py` faz em producao: a rota e' `/miniapp/assets/`,
            # a pasta e' `miniapp/newapp/assets/`. Sem esta linha o servidor de
            # desenvolvimento devolvia 404 para toda a arte, e eu estaria a
            # OLHAR para o fallback a fingir que era a tela — que e' exactamente
            # a classe de mentira que este ficheiro existe para evitar.
            name = os.path.basename(path)
            fp = os.path.join(CLIENT_ROOT, "miniapp", "newapp", "assets", name)
        elif path == "/miniapp/dist/bundle.js" and os.environ.get("NV_BUNDLE"):
            # 05/10 — NV_BUNDLE=<ficheiro>: o bundle compilado A PARTE. A guarda
            # de geometria (`scripts/_test_cena_cabe.py`) compila o codigo ACTUAL
            # numa pasta temporaria e serve-o daqui: mede o que esta escrito e
            # nunca deixa um `miniapp/dist` sabotado para tras quando a bateria
            # de sabotagem a corre. Tudo o resto (index, i18n, arte) vem da arvore.
            fp = os.path.abspath(os.environ.get("NV_BUNDLE"))
        elif path.startswith("/miniapp/"):
            # ⚠️ o `index.html` usa caminhos ABSOLUTOS `/miniapp/...` (ver o
            # comentario do bootstrap la dentro) — servir noutra rota nao parte
            # nada, mas os assets tem sempre este prefixo.
            rel = os.path.normpath(path[1:]).replace("\\", os.sep)
            fp = os.path.join(CLIENT_ROOT, rel)
            if not os.path.abspath(fp).startswith(os.path.abspath(CLIENT_ROOT)):
                self._send(403, "nope", "text/plain")
                return
        else:
            self._send(404, "not found: " + path, "text/plain")
            return
        if not os.path.isfile(fp):
            self._send(404, "missing " + path, "text/plain")
            return
        ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        if fp.endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        elif fp.endswith(".json"):
            ctype = "application/json; charset=utf-8"
        elif fp.endswith(".html"):
            ctype = "text/html; charset=utf-8"
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print("[dev] http://127.0.0.1:%d/app   features=%s   state=%s   cavern=%s"
          % (port, ",".join(sorted(FEATURES)), STATE, CAVERN_STATE), flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
