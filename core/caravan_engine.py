"""MV-9.5 商队 — A Caravana (Mundo Vivo v2, pilar §3-P1 "Geografia real", parte 2).

Origem: report do jogador **[jogador]** (2026-08-06) — *"the world is divided
likewise the locations to dungeons, the common raw materials could be sold by
NPC"*.

O pedido literal (vender material comum por pedras) está REFUTADO por
aritmética e o veto está escrito no `database/db.py`: para o novato medido
(~553 pedras) levar 10 Qi Root o preço tem de ser ≤ 55; para a mediana ativa
(846.985.667) ficar limitada a 1.000 unidades tem de ser ≥ 846.986. Conjunto
vazio, 4,2 ordens de grandeza. **Nenhum preço em pedras existe.**

O que falta ao jogador não é uma prateleira — é SABER onde nasce o material que
falta na receita dele, e ter como trazê-lo. Esta onda faz as duas coisas:

    §1  A DISCLOSURE (vale mais do que a caravana e é metade do ficheiro):
        hoje NÃO existe uma única tela em todo o Nivrael que diga onde nasce um
        material. O `Iron Skin Pill` fica cinzento no reino 2 e o jogo não diz
        porquê nem onde.

    §2  A CARAVANA: o velho da cidade MANDA VIR o que a montanha do outro lado
        guarda. Escambo material↔material, com prazo, razão desfavorável e
        recusa por alma. **ZERO pedras no fluxo.**

⚠️ A REGRA QUE MANDA NESTE FICHEIRO — e que derrubou o spec de 07/08:
    **A origem impressa é a UNIÃO MEDIDA das fontes vivas, nunca uma
    exclusividade que o código não sustenta.**

    O spec afirmava três "exclusivos verdadeiros". A medição derrubou dois:
      · Frost Dew (erva 11) — o spec dizia "só nas águas de Qiānhé". Mas
        `combat_engine.NPC_LOOT_TABLE["hard"]` pede `{"type":"herb","tier":3}` e
        os três resolvedores fazem `random.choice` sobre TODAS as ervas t3
        ({3, 6, 11}) sem olhar para o continente ⇒ ~13% por caçada difícil
        ganha, em qualquer lado (`core/pve_duel_settle.py:142-156`,
        `core/webserver.py:16792`, `handlers/combat.py:2461`).
      · Phoenix Ash (minério 8) — o spec dizia "só em Yǎnshān". Mas
        `dungeon_regions.REGIONAL_BONUS_LOOT["fenghuo"] = {"ores": {"8": 1}}`
        (`:45`) dá-o a Fēnghuǒ a 12% por run hard/nightmare. **Fēnghuǒ produz
        Phoenix Ash**, e é por isso que a caravana de Tiānhuǒ NÃO o pode mandar
        vir (recusa "isso o senhor tira do chão aqui" — a recusa lê o MESMO mapa
        e por isso é verdadeira, não decorativa).
      · Dragon Scale (minério 9) — o continente aguenta (Fēnghuǒ), mas são DUAS
        masmorras (13 mr3 e 19 mr8), não uma.

    Imprimir a exclusividade falsa seria criar um display-lie para vender a
    caravana. A união medida é mais honesta E mais útil.

Desenho (molde literal de `core/city_engine.py`):
    * `CARAVAN_META` é engine data, NOT DB — wipe-safe, Lei §5. **ZERO tabela,
      ZERO coluna, ZERO migration.** O ESTADO (a carga em trânsito) é uma linha
      de `transactions` com `type='caravan'`, escrita pelo escritor único que já
      existe (`economy.create_transaction`).
    * O MAPA DE ORIGEM é **derivado** das fontes vivas (seeds de masmorra +
      `EXPLORATION_NODES` + `REGIONAL_BONUS_LOOT` + as fontes sem geografia),
      nunca autorado. Se alguém mexer numa seed, a disclosure acompanha sozinha.
    * TODA string visível é `*_key` de i18n resolvida NO SERVIDOR (padrão
      Crônica/cidades) — as duas superfícies imprimem a MESMA frase.
    * O prazo é aritmética sobre `created_at`: **imune à deriva do World Pulse**
      (medida em 07/08 — o batimento anda 00/06/12/18 → 03:52/09:52/15:52 porque
      o trigger de intervalo re-agenda a partir do boot). Se o pulse nunca mais
      correr, a carga chega na mesma.

CONJUNÇÃO DURA (doutrina TEC-3 — o AND faz a feature DESAPARECER, não
meio-existir), declarada aqui porque não há registo Python de dependências:
    `caravana` ∧ `cidades` ∧ `dungeons_regionais`
    · sem `cidades` a caravana não tem cidade onde morar;
    · sem `dungeons_regionais` **a geografia não existe**: `region_gate`
      devolve None e as 23 masmorras são entráveis de qualquer continente
      (`core/dungeon_regions.py:129-144`) ⇒ "vá a Qiānhé" seria mentira e a
      caravana venderia a solução de um problema que não existe. É por isso que
      a disclosure NÃO pode sair para `main`: `main` lê sempre os defaults
      (`database/db.py:430-431`) e tem as três flags OFF.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from core.continent_engine import CONTINENT_KEYS, CONTINENT_META, is_valid_continent

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Gate da flag (molde city_engine.cidades_on) — fail-safe → False
# ══════════════════════════════════════════════════════════════════════════

def _flag(name: str, world_key: str | None = None) -> bool:
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world(name, world_key))
    except Exception:
        return False


def caravana_on(world_key: str | None = None) -> bool:
    """Gate estável da onda. **AND duro** das três flags (ver docstring).

    Fail-safe → False. Nunca levanta.
    """
    try:
        return (_flag("caravana", world_key)
                and _flag("cidades", world_key)
                and _flag("dungeons_regionais", world_key))
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════
# Tuning (engine, not DB — wipe-safe; env-overridable para ops)
# ══════════════════════════════════════════════════════════════════════════

# Quanto chega numa carga. Medido contra a fonte: o Rio Subterrâneo (Qiānhé,
# min_realm 2, 16 andares no normal) rende ~1 erva/andar e o Frost Dew é peso
# 3 de 13 no pool ⇒ ~3,7 unidades por varredura. Três é MENOS do que ir.
CRV_LOAD_UNITS = int(os.getenv("CRV_LOAD_UNITS", "3"))

# O prazo. Duas coisas ao mesmo tempo: é sempre pior do que ir (a viagem é
# INSTANTÂNEA — `travel_engine.do_travel` não tem estado de trânsito, só um
# cooldown de 4h) e é curto o bastante para caber num dia de jogo.
CRV_ETA_HOURS = float(os.getenv("CRV_ETA_HOURS", "6"))

# A razão de troca. Desfavorável de propósito: é a primeira coisa em todo o
# jogo que CONSOME material sem devolver nada em quantidade.
CRV_RATIO = int(os.getenv("CRV_RATIO", "4"))
# Wànshì manda vir QUALQUER um dos três (é o entreposto) e paga por isso.
CRV_RATIO_HUB = int(os.getenv("CRV_RATIO_HUB", "5"))

# Quantas cargas abertas por jogador. Um. Não existe corrida por estoque
# partilhado — logo não existe "1 varre, 29 batem na porta fechada".
CRV_MAX_OPEN = int(os.getenv("CRV_MAX_OPEN", "1"))

# O pagamento tem de ser material da MESMA faixa: tier >= alvo - 1. Sem isto o
# jogador paga t1 (abundante: mediana medida de 236.242 ervas paradas) por t3/t4
# e a caravana vira uma lavandaria de tier em vez de um sink.
CRV_PAY_TIER_SLACK = int(os.getenv("CRV_PAY_TIER_SLACK", "1"))

# O que a caravana transporta (ver `is_walled` — os dois números que impedem a
# onda de virar prateleira). Env-overridable para o owner apertar/alargar.
CRV_ROUTE_MAX_CONTINENTS = int(os.getenv("CRV_ROUTE_MAX_CONTINENTS", "2"))
CRV_ROUTE_MIN_TIER = int(os.getenv("CRV_ROUTE_MIN_TIER", "3"))

# Recusa por ALMA — o de Qiānhé (Templo do Punho de Ferro, casa marcial reta)
# não pega no material de quem tem karma abaixo disto. -100 é o corte de
# `tainted` em `karma_engine.KARMA_LABEL_BANDS` — alcança gente real (prod tem
# karma -1200 medido no MV-8), ao contrário de gatear por reputação (o tier
# `respected` alcança UMA pessoa nas 2 DBs; vetado no spec).
CRV_KARMA_MIN = int(os.getenv("CRV_KARMA_MIN", "-100"))

# Karma: a primeira carga honesta do dia. Liga `honest_market_trade` (+1), que
# está declarado em `karma_engine.KARMA_EVENTS:120` desde a v16.3 com ZERO
# consumidores — o jogo escreveu que o comércio tem peso moral, mostra a linha
# no KarmaModal (o catálogo itera o dict) e nunca pagou. 1×/dia, nunca por carga.
CRV_KARMA_EVENT = "honest_market_trade"


# ══════════════════════════════════════════════════════════════════════════
# As caravanas — engine data, NOT DB (wipe-safe, Lei §5)
# ══════════════════════════════════════════════════════════════════════════
# Campos:
#   caravan   : a cidade TEM caravana? Mòyǔ não tem, e isso é identidade, não
#               falta — é o único lugar onde só se chega indo (§3.3 do spec).
#   ratio     : unidades pagas por unidade recebida.
#   soul      : a recusa por ALMA. `karma_min` e/ou `reject_path`.
#               `karma_engine` e `path_engine` são os ÚNICOS eixos de alma sem
#               gate de flag nenhum (verificado) — funcionam em todo o mundo.
#   npc_*_key : i18n de CHAT (server-resolved), SEM placeholders.
#
# ⚠️ As ROTAS não vivem aqui. São DERIVADAS do mapa de origem (§ abaixo): a
#    caravana de uma cidade manda vir o que é geograficamente confinado E que o
#    continente dela NÃO produz. Autorar as rotas era o que punha a caravana de
#    Tiānhuǒ a vender Phoenix Ash que Fēnghuǒ já larga de graça.
CARAVAN_META: dict[str, dict[str, Any]] = {
    "wanshi": {
        "continent": "linghe",
        "caravan": True,
        "ratio": CRV_RATIO_HUB,
        "soul": {},
        "npc_name_key": "crv_npc_wanshi_name",
        "npc_intro_key": "crv_npc_wanshi_intro",
    },
    "tiequan": {
        "continent": "qianhe",
        "caravan": True,
        "ratio": CRV_RATIO,
        # A casa marcial reta olha o karma antes de pegar no cobre.
        "soul": {"karma_min": CRV_KARMA_MIN},
        "npc_name_key": "crv_npc_tiequan_name",
        "npc_intro_key": "crv_npc_tiequan_intro",
    },
    "wanhua": {
        "continent": "yanshan",
        "caravan": True,
        "ratio": CRV_RATIO,
        # O Jardim vira as costas ao demoníaco declarado.
        "soul": {"reject_path": "demonic"},
        "npc_name_key": "crv_npc_wanhua_name",
        "npc_intro_key": "crv_npc_wanhua_intro",
    },
    "tianhuo": {
        "continent": "fenghuo",
        "caravan": True,
        "ratio": CRV_RATIO,
        "soul": {},
        "npc_name_key": "crv_npc_tianhuo_name",
        "npc_intro_key": "crv_npc_tianhuo_intro",
    },
    "huiyin": {
        "continent": "moyu",
        # A Cidade dos Ecos não tem caravana. Nenhum velho vai lá.
        "caravan": False,
        "ratio": CRV_RATIO,
        "soul": {},
        "npc_name_key": "crv_npc_huiyin_name",
        "npc_intro_key": "crv_npc_huiyin_intro",
    },
}

CARAVAN_CONTINENT_TO_CITY: dict[str, str] = {
    m["continent"]: k for k, m in CARAVAN_META.items()
}


# ══════════════════════════════════════════════════════════════════════════
# O MAPA DE ORIGEM — derivado das fontes VIVAS, nunca autorado
# ══════════════════════════════════════════════════════════════════════════
# Construído uma vez, em memória, na primeira leitura. Cada fonte entra no seu
# próprio try/except: uma que falhe degrada-se a si própria e nunca cala o
# resto (é a diferença entre "a disclosure perdeu uma linha" e "a disclosure
# mentiu por omissão").
#
# Fontes GEOGRÁFICAS (dizem um continente):
#   1. `DUNGEON_SEEDS`        — a masmorra ancorada (MV-1). A verdade principal.
#   2. `EXPLORATION_NODES`    — o SEGUNDO mapa continente→masmorra, que NÃO bate
#                               com o `continent` das seeds em 6 dos 23 nós. A
#                               exploração rola o pool da masmorra NO NÓ, logo o
#                               continente do nó também produz aquele material.
#                               Ler só um dos mapas era sub-declarar a origem.
#   3. `REGIONAL_BONUS_LOOT`  — o Tributo da Terra (12% por run hard/nightmare).
#                               É o que dá Phoenix Ash a Fēnghuǒ.
#   4. `CAVE_HOUSES`          — as Grutas do Legado pagam o mesmo mapa (3).
#
# Fontes SEM geografia (a honestidade da frase depende delas):
#   5. `NPC_LOOT_TABLE`       — a caçada solta erva/minério POR TIER, resolvido
#                               com `random.choice` sobre o catálogo inteiro
#                               daquele tier. É o furo que mata a exclusividade
#                               do Frost Dew.
#   6. Expedições de fera · World Boss · desmonte de artefato · Encargo 城务.
#
# ⚠️ Esta onda LÊ os dois mapas de geografia e não toca em nenhum. Eleger UMA
#    verdade entre `DungeonCatalog.continent` e `EXPLORATION_NODES` continua a
#    ser dívida herdada do MV-1, anotada desde 06/08.

_ORIGINS: dict[tuple[str, int], dict[str, Any]] | None = None

# Chaves i18n das fontes sem geografia (`crv_src_*`).
SRC_HUNT = "hunt"
SRC_BEAST = "beast"
SRC_BOSS = "boss"
SRC_DISMANTLE = "dismantle"
SRC_ENCARGO = "encargo"

_NON_GEO_KEYS: tuple[str, ...] = (SRC_HUNT, SRC_BEAST, SRC_BOSS, SRC_DISMANTLE, SRC_ENCARGO)


def _blank() -> dict[str, Any]:
    return {"continents": set(), "gate_realm": {}, "sources": set(), "tier": None}


def _touch(acc: dict, kind: str, item_id: int) -> dict[str, Any]:
    return acc.setdefault((str(kind), int(item_id)), _blank())


def _add_geo(acc: dict, kind: str, item_id: int, continent: str, min_realm: int | None) -> None:
    if not is_valid_continent(continent):
        return
    e = _touch(acc, kind, item_id)
    e["continents"].add(str(continent))
    if min_realm is not None:
        cur = e["gate_realm"].get(str(continent))
        # O degrau de entrada é o MENOR — é o que o jogador precisa de saber.
        if cur is None or int(min_realm) < int(cur):
            e["gate_realm"][str(continent)] = int(min_realm)


def _add_src(acc: dict, kind: str, item_id: int, src: str) -> None:
    _touch(acc, kind, item_id)["sources"].add(str(src))


def _tiers() -> tuple[dict[int, int], dict[int, int]]:
    """(tier por erva, tier por minério), a partir das seeds. Fail-safe → {}."""
    herbs: dict[int, int] = {}
    ores: dict[int, int] = {}
    try:
        from database.seeds.alchemy_seeds import HERBS
        herbs = {int(h["id"]): int(h["tier"]) for h in HERBS}
    except Exception:
        logger.debug("caravan tiers: herbs failed", exc_info=True)
    try:
        from database.seeds.artifacts_seeds import ORES
        ores = {int(o["id"]): int(o["tier"]) for o in ORES}
    except Exception:
        logger.debug("caravan tiers: ores failed", exc_info=True)
    return herbs, ores


def _build_origins() -> dict[tuple[str, int], dict[str, Any]]:
    acc: dict[tuple[str, int], dict[str, Any]] = {}
    herb_tier, ore_tier = _tiers()

    # ── 1+2. Masmorras ancoradas + os nós de exploração ──────────────────
    seeds_by_id: dict[int, dict] = {}
    try:
        from database.seeds.dungeon_seeds import DUNGEON_SEEDS
        for d in DUNGEON_SEEDS:
            seeds_by_id[int(d["id"])] = d
            cont = d.get("continent")
            mr = d.get("min_realm")
            drops = d.get("drops") or {}
            for entry in (drops.get("herbs") or []):
                _add_geo(acc, "herb", int(entry["id"]), cont, mr)
            for entry in (drops.get("ores") or []):
                _add_geo(acc, "ore", int(entry["id"]), cont, mr)
    except Exception:
        logger.exception("caravan origins: dungeon seeds failed")

    try:
        from core.exploration_engine import EXPLORATION_NODES
        for cont, ids in EXPLORATION_NODES.items():
            for did in ids:
                d = seeds_by_id.get(int(did))
                if not d:
                    continue
                drops = d.get("drops") or {}
                mr = d.get("min_realm")
                for entry in (drops.get("herbs") or []):
                    _add_geo(acc, "herb", int(entry["id"]), cont, mr)
                for entry in (drops.get("ores") or []):
                    _add_geo(acc, "ore", int(entry["id"]), cont, mr)
    except Exception:
        logger.exception("caravan origins: exploration nodes failed")

    # ── 3+4. Tributo da Terra e Grutas do Legado (o mesmo mapa) ──────────
    # Sem degrau de reino próprio: o tributo sai da run que o jogador já podia
    # fazer, portanto herda o gate da masmorra e não acrescenta requisito.
    try:
        from core.dungeon_regions import REGIONAL_BONUS_LOOT
        for cont, loot in REGIONAL_BONUS_LOOT.items():
            for bucket, kind in (("herbs", "herb"), ("ores", "ore")):
                for raw_id in (loot.get(bucket) or {}):
                    _add_geo(acc, kind, int(raw_id), cont, None)
    except Exception:
        logger.exception("caravan origins: regional bonus failed")

    # ── 5. A caçada — o furo que mata a exclusividade por tier ───────────
    try:
        from core.combat_engine import NPC_LOOT_TABLE
        by_tier = {"herb": {}, "ore": {}}
        for iid, tr in herb_tier.items():
            by_tier["herb"].setdefault(tr, []).append(iid)
        for iid, tr in ore_tier.items():
            by_tier["ore"].setdefault(tr, []).append(iid)
        for _diff, drops in NPC_LOOT_TABLE.items():
            for drop in drops:
                kind = str(drop.get("type") or "")
                if kind not in ("herb", "ore") or drop.get("tier") is None:
                    continue
                for iid in by_tier[kind].get(int(drop["tier"]), []):
                    _add_src(acc, kind, iid, SRC_HUNT)
    except Exception:
        logger.exception("caravan origins: npc loot failed")

    # ── 6. Fera · Chefe · Desmonte · Encargo ─────────────────────────────
    def _scan(entries, src: str) -> None:
        for entry in (entries or []):
            if not isinstance(entry, dict):
                continue
            kind = str(entry.get("type") or "")
            if kind in ("herb", "ore") and entry.get("item_id") is not None:
                _add_src(acc, kind, int(entry["item_id"]), src)

    try:
        # `drops` = {"guaranteed": [...], "bonus": [...], "beast_egg_chance": f}
        from database.seeds.beasts_seeds import EXPEDITIONS
        for exp in EXPEDITIONS:
            drops = exp.get("drops") or {}
            _scan(drops.get("guaranteed"), SRC_BEAST)
            _scan(drops.get("bonus"), SRC_BEAST)
    except Exception:
        logger.debug("caravan origins: expeditions failed", exc_info=True)

    try:
        # `loot_table` = {"rank_1": [...], ..., "participant": [...]}
        from database.seeds.boss_seeds import WORLD_BOSS_POOL
        for boss in WORLD_BOSS_POOL:
            for bucket in (boss.get("loot_table") or {}).values():
                _scan(bucket, SRC_BOSS)
    except Exception:
        logger.debug("caravan origins: boss loot failed", exc_info=True)

    try:
        # Desmontar um artefato devolve `ceil(qty*ratio)` de CADA minério da
        # receita (`forge_engine.refund_recipe_materials`) — é faucet indireto
        # de Phoenix Ash e Dragon Scale sem passar por geografia nenhuma.
        from database.seeds.forge_seeds import FORGE_RECIPES
        for rec in FORGE_RECIPES:
            for mat in (rec.get("materials") or []):
                if mat.get("ore_id") is not None:
                    _add_src(acc, "ore", int(mat["ore_id"]), SRC_DISMANTLE)
    except Exception:
        logger.debug("caravan origins: forge recipes failed", exc_info=True)

    try:
        from database.seeds.storylet_seeds import STORYLET_SEEDS
        for st in STORYLET_SEEDS:
            for item in ((st.get("reward") or {}).get("items") or []):
                kind = str(item.get("type") or "")
                if kind in ("herb", "ore") and item.get("id") is not None:
                    _add_src(acc, kind, int(item["id"]), SRC_ENCARGO)
    except Exception:
        logger.debug("caravan origins: storylet rewards failed", exc_info=True)

    # Tier em cada entrada (a razão de troca precisa dele).
    for (kind, iid), e in acc.items():
        e["tier"] = (herb_tier if kind == "herb" else ore_tier).get(int(iid))
    return acc


def origins() -> dict[tuple[str, int], dict[str, Any]]:
    """O mapa completo, construído à primeira leitura. PURO (zero I/O de DB)."""
    global _ORIGINS
    if _ORIGINS is None:
        try:
            _ORIGINS = _build_origins()
        except Exception:
            logger.exception("caravan origins: build failed")
            _ORIGINS = {}
    return _ORIGINS


def material_origin(kind: str, item_id: int) -> dict[str, Any] | None:
    """{continents, gate_realm, sources, tier} daquele material, ou None.

    **PURA e sem gate de flag** — a verdade sobre a geografia não depende de
    nenhum switch; quem decide se ela é DITA é o chamador. Nunca levanta.
    """
    try:
        e = origins().get((str(kind), int(item_id)))
        if not e:
            return None
        return {
            "continents": sorted(e["continents"]),
            "gate_realm": dict(e["gate_realm"]),
            "sources": sorted(e["sources"]),
            "tier": e["tier"],
        }
    except Exception:
        logger.debug("material_origin failed kind=%s id=%s", kind, item_id, exc_info=True)
        return None


def is_confined(kind: str, item_id: int) -> bool:
    """O material é geograficamente confinado? (cai em 1..3 continentes, não em
    todos, e cai em ALGUM). Puro."""
    o = material_origin(kind, item_id)
    if not o:
        return False
    n = len(o["continents"])
    return 0 < n < len(CONTINENT_KEYS)


def produced_in(kind: str, item_id: int, continent: str) -> bool:
    """Aquele continente larga este material? Puro. É a recusa nº1."""
    o = material_origin(kind, item_id)
    return bool(o and str(continent) in o["continents"])


# ══════════════════════════════════════════════════════════════════════════
# A frase — server-resolved, uma verdade para as duas superfícies
# ══════════════════════════════════════════════════════════════════════════

def _cont_label(key: str, lang: str) -> str:
    try:
        from core.i18n import t as i18n_t
        emoji = str((CONTINENT_META.get(key) or {}).get("emoji", ""))
        return f"{emoji} {i18n_t(lang, 'continent_' + str(key))}".strip()
    except Exception:
        return str(key)


def origin_line(kind: str, item_id: int, lang: str) -> str:
    """*"⛰️ Qiānhé (a partir do reino 2) · também de caçada"* — a linha que
    faltava ao jogo inteiro.

    **Nunca promete exclusividade.** Nomeia TODOS os continentes onde o
    material cai e, se houver fonte sem geografia, di-lo na mesma frase. Devolve
    "" quando não há nada honesto a dizer. Nunca levanta.
    """
    try:
        o = material_origin(kind, item_id)
        if not o or not o["continents"]:
            return ""
        from core.i18n import t as i18n_t
        parts = []
        for ck in o["continents"]:
            label = _cont_label(ck, lang)
            gate = o["gate_realm"].get(ck)
            if gate:
                label += " " + i18n_t(lang, "crv_origin_gate", r=int(gate))
            parts.append(label)
        line = i18n_t(lang, "crv_origin_born", places=" · ".join(parts))
        extra = [s for s in o["sources"] if s in _NON_GEO_KEYS]
        if extra:
            names = [i18n_t(lang, "crv_src_" + s) for s in sorted(extra)]
            line += " · " + i18n_t(lang, "crv_origin_also", sources=", ".join(names))
        return line
    except Exception:
        logger.debug("origin_line failed kind=%s id=%s", kind, item_id, exc_info=True)
        return ""


def origin_note(kind: str, item_id: int, lang: str, viewer_continent: str | None = None
                ) -> dict[str, Any] | None:
    """A disclosure projetada para uma superfície: `{line, here, confined}`.

    `here=True` quando o continente do leitor já produz o material — é o que
    permite à tela dizer *"você tira isso do chão aqui"* em vez de mandar viajar
    à toa. Gated: com a flag OFF devolve **None** ⇒ o chamador não emite a key
    ⇒ payload byte-idêntico ao de hoje (a lente dos 57).
    """
    try:
        if not caravana_on():
            return None
        line = origin_line(kind, item_id, lang)
        if not line:
            return None
        return {
            "line": line,
            "here": bool(viewer_continent and produced_in(kind, item_id, viewer_continent)),
            "confined": is_confined(kind, item_id),
        }
    except Exception:
        logger.debug("origin_note failed", exc_info=True)
        return None


# ══════════════════════════════════════════════════════════════════════════
# As rotas e a razão de troca — derivadas, puras
# ══════════════════════════════════════════════════════════════════════════

def is_walled(kind: str, item_id: int) -> bool:
    """O material é um MURO geográfico — vale uma caravana? Puro.

    ⚠️ "Confinado" sozinho não serve, e a medição prova: 21 dos 25 materiais do
    jogo caem em menos de cinco continentes (quase nada cai em todos), logo um
    critério de `< 5` punha a caravana a transportar **Qi Root t1** — e a
    prateleira refutada pelo §0.4 do spec voltava pela porta das traseiras.

    Duas condições, ambas com número medido:
      · **≤ 2 continentes** — em 3 ou mais o material não é um muro, é uma
        caminhada; e a caravana nunca deve competir com a masmorra ao lado.
      · **tier ≥ 3** — t1/t2 são a abundância medida (mediana de 236.242 ervas
        PARADAS por ativo-30d, contra um teto de consumo de 144-250/dia: 2,6 a
        4,5 ANOS de estoque). Ninguém precisa que lhe mandem vir Ferro Mortal.

    O resultado é derivado, não autorado: hoje dá **quatro** — 🪷 Foundation
    Lotus (t3, Línghé/Qiānhé) · ❄️ Frost Dew (t3, só Qiānhé) · 🔥 Phoenix Ash
    (t3, Yǎnshān/Fēnghuǒ) · 🐉 Dragon Scale (t4, só Fēnghuǒ). Os três do spec,
    mais um que o spec não viu e que é muro para 3 dos 5 continentes.
    """
    o = material_origin(kind, item_id)
    if not o:
        return False
    n = len(o["continents"])
    if not (0 < n <= CRV_ROUTE_MAX_CONTINENTS):
        return False
    return int(o["tier"] or 0) >= CRV_ROUTE_MIN_TIER


def confined_materials() -> list[tuple[str, int]]:
    """Todo material que é MURO geográfico, em ordem estável. Puro."""
    try:
        return sorted(
            (k for k in origins() if is_walled(*k)),
            key=lambda k: (k[0], k[1]),
        )
    except Exception:
        return []


def city_for_continent(continent: str | None) -> str | None:
    return CARAVAN_CONTINENT_TO_CITY.get(str(continent or ""))


def has_caravan(continent: str | None) -> bool:
    ck = city_for_continent(continent)
    return bool(ck and CARAVAN_META[ck].get("caravan"))


def ratio_for(continent: str | None) -> int:
    ck = city_for_continent(continent)
    return int(CARAVAN_META[ck]["ratio"]) if ck else CRV_RATIO


def routes_for(continent: str | None) -> list[tuple[str, int]]:
    """O que a caravana DAQUELE continente pode mandar vir. **Derivado.**

    Regra única: material confinado que este continente **não produz**. É por
    isso que Tiānhuǒ (Fēnghuǒ) não manda vir Phoenix Ash — o Tributo da Terra
    de Fēnghuǒ já o larga (`REGIONAL_BONUS_LOOT["fenghuo"]`), e vender ao
    jogador o que o chão dele dá é o no-op que o MV-9 aprendeu a recusar.

    Puro. Fail-safe → [].
    """
    try:
        if not is_valid_continent(continent) or not has_caravan(continent):
            return []
        return [k for k in confined_materials() if not produced_in(k[0], k[1], str(continent))]
    except Exception:
        logger.debug("routes_for failed continent=%s", continent, exc_info=True)
        return []


# ── O balcão de recompra, espelhado ──────────────────────────────────────
# Estes três valores são cópia LITERAL de `handlers/inventory.py:43,46` — a
# única saída material→pedras do jogo. Copiados de propósito (um engine não
# importa um handler, e `handlers.inventory` puxa `telegram`) e **guardados por
# assert na suite**: se lá mudarem e aqui não, o teste parte.
#
# ⚠️ `_ORE_SELL_PER_UNIT` só cobre t1-t5; t6 (Void Crystal) e t7 (Dao Essence)
#    caem no fallback e valem o mesmo que Ferro Mortal. Isso é um defeito VIVO
#    e está sob VETO explícito (consertá-lo imprimiria +382,4 bilhões de pedras
#    — o estoque medido de Dao Essence sozinho vale 371,6bi ao preço corrigido).
#    A Caravana não o conserta: **lê-o como está** e defende-se dele.
_HERB_SELL_RATIO = 0.6
_ORE_SELL_PER_UNIT = {1: 80, 2: 250, 3: 800, 4: 2500, 5: 8000}
_ORE_SELL_FALLBACK = 80


def stone_value(kind: str, item_id: int) -> int:
    """Quanto o jogador recebe em pedras por UMA unidade, no balcão de recompra.

    É o único preço real de material no jogo — e é por ele que se mede se a
    Caravana é sink. Puro. Fail-safe → 0 (que exclui o material do pagamento,
    o lado seguro).
    """
    try:
        if str(kind) == "ore":
            tier = int((material_origin("ore", item_id) or {}).get("tier") or 0)
            return int(_ORE_SELL_PER_UNIT.get(tier, _ORE_SELL_FALLBACK))
        from database.seeds.alchemy_seeds import HERBS
        for h in HERBS:
            if int(h["id"]) == int(item_id):
                return max(1, int(int(h["base_price"]) * _HERB_SELL_RATIO))
        return 0
    except Exception:
        logger.debug("stone_value failed %s %s", kind, item_id, exc_info=True)
        return 0


def accepted_payments(continent: str | None, target_kind: str, target_id: int
                      ) -> list[tuple[str, int]]:
    """O que aquela caravana aceita como pagamento por AQUELE alvo. Derivado.

    TRÊS condições, todas medidas:
      · o material tem de ser produzido pelo PRÓPRIO continente (a caravana
        leva o que a terra dá — não é um balcão de câmbio universal);
      · `tier >= tier_do_alvo - CRV_PAY_TIER_SLACK`. Sem isto o jogador paga em
        t1 (mediana medida: 236.242 ervas paradas por ativo, 2,6 a 4,5 anos do
        teto de consumo) e a caravana vira lavandaria de tier em vez de sink;
      · **SINK EM PEDRAS, não só em unidades.** O que sai tem de valer MENOS,
        ao balcão de recompra, do que o que entra.

    ⚠️ A terceira condição foi acrescentada depois de a bancada a medir, e é a
    correção mais importante desta onda. Em UNIDADES a caravana sempre foi sink
    (12 entram, 3 saem). Em PEDRAS era uma impressora, porque erva e minério
    vivem em escalas de preço ~15× diferentes: 12 Foundation Lotus (t3 erva,
    48/un = 576) por 3 Dragon Scale (t4 minério, 2.500/un = 7.500) rendia
    **+6.924 pedras por carga**, ~4 cargas/dia. E o §8 do spec afirma, em letra
    grande, "é um SINK" — seria exatamente o display-lie que esta onda existe
    para não cometer. A régua em unidades não bastava; a régua é o VALOR.

    Puro. Fail-safe → [].
    """
    try:
        tgt = material_origin(target_kind, target_id)
        if not tgt or not is_valid_continent(continent):
            return []
        floor = max(1, int(tgt["tier"] or 1) - max(0, CRV_PAY_TIER_SLACK))
        q = quote(continent, target_kind, target_id)
        # Valor que SAI da caravana, em pedras.
        out_value = int(stone_value(target_kind, target_id)) * int(
            q["units"] if q else max(1, CRV_LOAD_UNITS))
        cost = int(q["cost"] if q else max(1, CRV_LOAD_UNITS) * CRV_RATIO)
        out: list[tuple[str, int]] = []
        for (kind, iid), e in origins().items():
            if str(continent) not in e["continents"]:
                continue
            if (kind, iid) == (str(target_kind), int(target_id)):
                continue
            if int(e["tier"] or 0) < floor:
                continue
            if int(stone_value(kind, iid)) * cost <= out_value:
                continue
            out.append((kind, iid))
        # Ordenado pelo que CUSTA MENOS ao jogador em pedras — a UI põe o mais
        # barato primeiro, e o chat escolhe esse. Ordenar por tier punia quem
        # tem o material caro-mas-abundante.
        return sorted(out, key=lambda k: (stone_value(*k) * cost, k[0], k[1]))
    except Exception:
        logger.debug("accepted_payments failed", exc_info=True)
        return []


def quote(continent: str | None, target_kind: str, target_id: int) -> dict[str, Any] | None:
    """{units, cost, ratio, eta_hours} — o preço em MATERIAL. Puro.

    A mesma carga custa o mesmo ao r0 de 553 pedras e ao r10 de 258 bilhões:
    o preço não é dinheiro.
    """
    try:
        if not is_valid_continent(continent) or not has_caravan(continent):
            return None
        r = ratio_for(continent)
        units = max(1, CRV_LOAD_UNITS)
        return {
            "units": units,
            "ratio": r,
            "cost": units * r,
            "eta_hours": CRV_ETA_HOURS,
            "kind": str(target_kind),
            "item_id": int(target_id),
        }
    except Exception:
        logger.debug("quote failed", exc_info=True)
        return None


# ══════════════════════════════════════════════════════════════════════════
# Helpers de tempo (molde city_engine)
# ══════════════════════════════════════════════════════════════════════════

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def eta_of(row, now: datetime | None = None) -> datetime:
    """Quando aquela carga chega. Aritmética sobre `created_at` — **imune à
    deriva do World Pulse**, que re-agenda a partir do boot."""
    created = _aware(getattr(row, "created_at", None)) or (now or _utcnow())
    return created + timedelta(hours=max(0.0, CRV_ETA_HOURS))


# ══════════════════════════════════════════════════════════════════════════
# A CARGA — estado derivado do ledger (ZERO tabela, ZERO coluna)
# ══════════════════════════════════════════════════════════════════════════
# Uma carga é UMA linha de `transactions`:
#     type='caravan' · from_player=<eu> · to_player=NULL
#     item_type='herb'|'ore' · item_id=<o alvo> · quantity=<CRV_LOAD_UNITS>
#     price=0 · tax_paid=0
#     details={"city","continent","paid":{...},"eta_h", "delivered_at"?}
#
# Escrita pelo escritor ÚNICO que já existe (`economy.create_transaction`) —
# uma verdade, e o ledger continua a ter um só dono.
#
# ⚠️ `price=0` de propósito: `economy.py:190` calcula `buyer_pays` mas grava
#    `total_price`, logo qualquer contador derivado de `transactions.price` já
#    mente 5% assim que um continente sai de `prospera`. A Caravana não escreve
#    dinheiro nenhum e por isso não polui o Relatório do Mercado Imperial
#    (`profession_engine.py:865-871` filtra `type IN ('buy','auction')`).

CARAVAN_TX_TYPE = "caravan"


def _delivered(row) -> bool:
    return bool((getattr(row, "details", None) or {}).get("delivered_at"))


async def _pending_rows(session, player_id: int, *, lock: bool = False):
    """As cargas ainda não creditadas deste jogador (em trânsito + chegadas).

    O predicado é `details->>'delivered_at' IS NULL` — o índice
    `idx_transactions_from_player` cobre o resto. `lock=True` serializa o
    crédito: a segunda chamada concorrente bloqueia, e quando passa já lê a
    linha com `delivered_at` posto (READ COMMITTED) ⇒ nunca credita duas vezes.
    """
    from database.models import Transaction
    stmt = select(Transaction).where(
        Transaction.from_player == int(player_id),
        Transaction.type == CARAVAN_TX_TYPE,
        Transaction.details["delivered_at"].astext.is_(None),
    ).order_by(Transaction.created_at.asc())
    if lock:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalars().all()


async def _grant(session, player_id: int, kind: str, item_id: int, qty: int) -> bool:
    """Credita material ao jogador. Erva → `player_inventory`; minério →
    `player_ores` (a tabela que a forja, o mercado e o escrow realmente leem).

    Passa pelo chokepoint `core.utils.add_item_to_inventory`, que desde esta
    onda desvia `ore` para `PlayerOre` — ver §4.5 do spec (três escritores
    escreviam minério na tabela errada e a forja não o enxergava).
    """
    from core.utils import add_item_to_inventory
    return bool(await add_item_to_inventory(
        session, int(player_id), str(kind), int(item_id), int(qty)))


async def credit_arrived(session, player, *, now: datetime | None = None,
                         lang: str | None = None) -> list[dict[str, Any]]:
    """**QUEM FINALIZA CREDITA.** Entrega toda carga cujo prazo já passou.

    Chamada em TODOS os pontos que podem "chegar primeiro" — praça do mini,
    praça do chat, a própria vitrine da caravana e a chegada de viagem. Sem
    isso o progresso come-se em silêncio (a lição está escrita em
    `feedback_quem_finaliza_credita`: 3 finalizadores cobertos e 7 a apagar).

    Idempotente por construção (`FOR UPDATE` + `delivered_at` no JSONB).
    Nunca levanta — é chamada de caminhos de leitura.
    """
    out: list[dict[str, Any]] = []
    try:
        if player is None or not caravana_on():
            return out
        now = now or _utcnow()
        lang = (lang or getattr(player, "language", None) or "pt").lower()
        rows = await _pending_rows(session, int(player.telegram_id), lock=True)
        for row in rows:
            if _delivered(row) or eta_of(row, now) > now:
                continue
            kind = str(row.item_type or "")
            iid = int(row.item_id or 0)
            qty = max(1, int(row.quantity or 0))
            if kind not in ("herb", "ore") or iid <= 0:
                # Linha impossível: marca como entregue para não ficar presa
                # para sempre a bloquear o slot do jogador (Lei §1 — nunca
                # deixar o jogador trancado por uma row que ninguém consegue
                # resolver). Fica o rasto no log.
                logger.warning("caravan: linha inválida tx=%s kind=%s id=%s",
                               getattr(row, "id", None), kind, iid)
                row.details = {**(row.details or {}), "delivered_at": now.isoformat(),
                               "void": True}
                continue
            ok = await _grant(session, int(player.telegram_id), kind, iid, qty)
            if not ok:
                # Mochila cheia (só acontece com erva). A carga ESPERA — não se
                # perde e não se marca entregue. A superfície diz porquê.
                out.append({"ok": False, "reason": "bag_full",
                            "kind": kind, "item_id": iid, "qty": qty})
                continue
            # MERGE no JSONB — nunca substituir o payload (armadilha da casa:
            # mutar in-place não dispara o change tracking do SQLAlchemy).
            row.details = {**(row.details or {}), "delivered_at": now.isoformat()}
            out.append({"ok": True, "kind": kind, "item_id": iid, "qty": qty,
                        "city": (row.details or {}).get("city")})
        return out
    except Exception:
        logger.exception("credit_arrived failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return out


# ══════════════════════════════════════════════════════════════════════════
# As quatro recusas — cada uma DIZ o motivo e o requisito (Lei §1)
# ══════════════════════════════════════════════════════════════════════════

async def _encargo_materials(session, continent: str, lang: str
                             ) -> tuple[set[tuple[str, int]], str]:
    """O material que o Encargo VIGENTE daquela cidade paga, e o nome dele.

    §Q5: a caravana nunca aceita como pagamento, nem entrega, o que o Encargo
    do dia já paga — senão a razão de troca pública põe etiqueta em 73% das
    recompensas de uma onda de ontem (11 dos 15 encargos pagam material t1-t3).
    O encargo vigente lê-se pela função pura que já existe: UMA verdade.
    """
    try:
        from core.city_engine import encargo_view
        enc = await encargo_view(session, continent, lang)
        if not enc or enc.get("locked") or not enc.get("key"):
            return set(), ""
        from database.models import StoryletCatalog
        cat = await session.get(StoryletCatalog, str(enc["key"]))
        items = ((getattr(cat, "reward", None) or {}).get("items") or []) if cat else []
        mats = {
            (str(i["type"]), int(i["id"]))
            for i in items
            if isinstance(i, dict) and i.get("type") in ("herb", "ore") and i.get("id") is not None
        }
        return mats, str(enc.get("name") or "")
    except Exception:
        logger.debug("caravan encargo materials failed", exc_info=True)
        return set(), ""


async def _soul_refusal(session, player, city_key: str, lang: str) -> dict[str, Any] | None:
    """A recusa que só existe neste jogo. `karma_engine` e `path_engine` são os
    únicos eixos de alma SEM gate de flag nenhum — funcionam em todo o mundo."""
    try:
        from core.i18n import t as i18n_t
        soul = (CARAVAN_META.get(city_key) or {}).get("soul") or {}
        if not soul:
            return None
        pid = int(player.telegram_id)
        if "karma_min" in soul:
            from core.karma_engine import get_karma
            k = int(await get_karma(session, pid))
            if k < int(soul["karma_min"]):
                return {"reason": "soul_karma",
                        "line": i18n_t(lang, "crv_refuse_karma",
                                       k=k, min=int(soul["karma_min"]))}
        if soul.get("reject_path"):
            from core.path_engine import get_player_path
            p = str(await get_player_path(session, pid))
            if p == str(soul["reject_path"]):
                return {"reason": "soul_path",
                        "line": i18n_t(lang, "crv_refuse_path")}
        return None
    except Exception:
        logger.debug("caravan soul refusal failed", exc_info=True)
        return None


# ══════════════════════════════════════════════════════════════════════════
# MANDAR VIR — a escrita
# ══════════════════════════════════════════════════════════════════════════

async def send_load(session, player, *, target_kind: str, target_id: int,
                    pay_kind: str, pay_id: int, lang: str | None = None,
                    now: datetime | None = None) -> dict[str, Any]:
    """Manda vir uma carga. **Escambo puro: nenhuma pedra atravessa o fluxo.**

    O caller trava a row do jogador FOR UPDATE e é dono do commit — o contrato
    de `city_engine.accept_encargo` / `bounty_engine.claim_bounty`.

    Toda recusa é NOMEADA e devolve `reason` + `line` (Lei §1). Devolver
    `{"ok": False}` NUNCA muta nada: o débito é a última coisa que acontece, e
    é all-or-nothing row-locked (`formation_engine.debit_materials`).
    """
    from core.i18n import t as i18n_t
    lang = (lang or getattr(player, "language", None) or "pt").lower()
    now = now or _utcnow()

    def _no(reason: str, key: str, **kw) -> dict[str, Any]:
        return {"ok": False, "reason": reason, "line": i18n_t(lang, key, **kw)}

    try:
        if player is None:
            return {"ok": False, "reason": "no_player"}
        if not caravana_on():
            return _no("caravana_off", "crv_refuse_flag")

        cont = getattr(player, "current_continent", None)
        if not is_valid_continent(cont):
            cont = "linghe"
        cont = str(cont)
        city = city_for_continent(cont)

        # ── Recusa 0 — não há velho nenhum aqui (Mòyǔ) ────────────────────
        if not city or not has_caravan(cont):
            return _no("no_caravan", "crv_refuse_no_caravan")

        target_kind, pay_kind = str(target_kind), str(pay_kind)
        target_id, pay_id = int(target_id), int(pay_id)

        # ── Recusa 4 — por ALMA (antes de qualquer conta) ─────────────────
        soul = await _soul_refusal(session, player, city, lang)
        if soul:
            return {"ok": False, **soul}

        # ── Recusa 2 — a última ainda não chegou ──────────────────────────
        # Creditar ANTES de contar: uma carga que já chegou não pode passar por
        # aberta só porque o jogador entrou por outra porta.
        await credit_arrived(session, player, now=now, lang=lang)
        pend = [r for r in await _pending_rows(session, int(player.telegram_id))
                if not _delivered(r)]
        if len(pend) >= max(1, CRV_MAX_OPEN):
            left = max(0.0, (eta_of(pend[0], now) - now).total_seconds() / 3600.0)
            return _no("load_open", "crv_refuse_open", h=max(1, int(round(left))))

        # ── Recusa 1 — isso o senhor tira do chão aqui ────────────────────
        if produced_in(target_kind, target_id, cont):
            return _no("produced_here", "crv_refuse_here",
                       place=_cont_label(cont, lang))
        if (target_kind, target_id) not in routes_for(cont):
            return _no("not_routable", "crv_refuse_not_routable")

        # ── Recusa 3 — o que tínhamos foi tudo para o Encargo ─────────────
        enc_mats, enc_name = await _encargo_materials(session, cont, lang)
        if (target_kind, target_id) in enc_mats or (pay_kind, pay_id) in enc_mats:
            return _no("encargo_conflict", "crv_refuse_encargo",
                       name=enc_name or i18n_t(lang, "crv_encargo_generic"))

        # ── O pagamento tem de ser aceite ─────────────────────────────────
        if (pay_kind, pay_id) not in accepted_payments(cont, target_kind, target_id):
            return _no("pay_invalid", "crv_refuse_pay_invalid")

        q = quote(cont, target_kind, target_id)
        if not q:
            return _no("no_quote", "crv_refuse_flag")
        cost = int(q["cost"])

        # ── O débito: all-or-nothing, row-locked. É a ÚLTIMA coisa ────────
        from core.formation_engine import debit_materials
        ok = await debit_materials(
            session, int(player.telegram_id),
            [{"herb_id": pay_id, "qty": cost}] if pay_kind == "herb" else [],
            [{"ore_id": pay_id, "qty": cost}] if pay_kind == "ore" else [],
        )
        if not ok:
            return _no("pay_short", "crv_refuse_pay_short", n=cost)

        from core.economy import create_transaction
        # Savepoint PRÓPRIO: um duplo-tap perdido desfaz só isto e nunca
        # envenena a transação do caller (o contrato do MV-5/MV-9).
        async with session.begin_nested():
            await create_transaction(
                session, int(player.telegram_id), None, CARAVAN_TX_TYPE,
                item_type=target_kind, item_id=target_id, qty=int(q["units"]),
                price=0, tax=0,
                details={"city": city, "continent": cont,
                         "eta_h": float(CRV_ETA_HOURS),
                         "paid": {"type": pay_kind, "id": pay_id, "qty": cost}},
            )
            await session.flush()

        karma = await _karma_for_trade(session, player)

        return {
            "ok": True,
            "city": city,
            "kind": target_kind,
            "item_id": target_id,
            "units": int(q["units"]),
            "paid": {"type": pay_kind, "id": pay_id, "qty": cost},
            "eta_hours": float(CRV_ETA_HOURS),
            "karma": karma,
            "line": i18n_t(lang, "crv_sent", h=int(round(CRV_ETA_HOURS)),
                           n=int(q["units"])),
        }
    except Exception:
        logger.exception("send_load failed (player=%s)",
                         getattr(player, "telegram_id", None))
        # Até o erro interno DIZ algo: `ok:false` com HTTP 200 não dispara o
        # `catch` do cliente, e sem `line` o botão fica um clique silencioso.
        try:
            from core.i18n import t as _t
            return {"ok": False, "reason": "internal_error",
                    "line": _t(lang, "crv_refuse_busy")}
        except Exception:
            return {"ok": False, "reason": "internal_error"}


async def _karma_for_trade(session, player) -> dict[str, Any] | None:
    """A primeira carga honesta do dia dá +1 de karma.

    `honest_market_trade` está declarado em `karma_engine.KARMA_EVENTS:120`
    desde a v16.3, aparece no catálogo do KarmaModal (que itera o dict) e tinha
    **zero consumidores** — o jogo prometia peso moral ao comércio e nunca
    pagava. Ligar o fio FECHA essa mentira.

    ⚠️ **1×/dia, nunca por carga.** É o primeiro faucet de karma da casa com
    teto diário; o molde é o COUNT sobre `karma_log` por `created_at >=`
    meia-noite UTC, que custa ZERO migration (o índice
    `idx_karma_log_player(player_id, created_at DESC)` já cobre o predicado).
    A razão do teto está escrita na sessão de 2026-06-19, que deixou este
    evento de fora precisamente por ser farmável sem dedup.

    Nunca levanta: um faucet de karma nunca pode derrubar a entrega da carga.
    """
    try:
        from sqlalchemy import func
        from database.models import KarmaLog
        pid = int(player.telegram_id)
        day_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        already = (await session.execute(
            select(func.count()).select_from(KarmaLog).where(
                KarmaLog.player_id == pid,
                KarmaLog.event_type == CRV_KARMA_EVENT,
                KarmaLog.created_at >= day_start,
            )
        )).scalar_one_or_none()
        if int(already or 0) > 0:
            return None
        from core.karma_engine import apply_karma
        res = await apply_karma(session, pid, CRV_KARMA_EVENT, {"source": "caravan"})
        if not res or not res.get("ok"):
            return None
        # Ler o delta REALMENTE aplicado (o clamp em ±1000 pode zerá-lo).
        return {"delta": int(res.get("delta") or 0),
                "new_value": int(res.get("new_value") or 0)}
    except Exception:
        logger.debug("caravan karma failed", exc_info=True)
        return None


# ══════════════════════════════════════════════════════════════════════════
# A VITRINE — server-resolved, uma verdade para as três superfícies
# ══════════════════════════════════════════════════════════════════════════

async def resolve_names(session, keys) -> dict[tuple[str, int], dict[str, str]]:
    """{(kind, id): {name, emoji}} a partir dos catálogos. Duas queries, no máximo.

    O nome de erva/minério **nunca passa por i18n** — é a coluna `name` (inglês)
    de `HerbCatalog`/`OreCatalog`, e é assim que TODAS as telas do jogo já o
    imprimem (`handlers/inventory.py:602,647`, `handlers/alchemy.py:483`, ...).
    Inventar uma camada de tradução só para a caravana criaria uma segunda
    verdade sobre o nome do mesmo item.
    """
    out: dict[tuple[str, int], dict[str, str]] = {}
    try:
        from database.models import HerbCatalog, OreCatalog
        for kind, model in (("herb", HerbCatalog), ("ore", OreCatalog)):
            ids = sorted({int(i) for (k, i) in keys if k == kind})
            if not ids:
                continue
            rows = (await session.execute(
                select(model).where(model.id.in_(ids))
            )).scalars().all()
            for r in rows:
                out[(kind, int(r.id))] = {
                    "name": str(r.name or ""),
                    "emoji": str(getattr(r, "emoji", "") or ("🌿" if kind == "herb" else "🪨")),
                }
    except Exception:
        logger.debug("caravan resolve_names failed", exc_info=True)
    return out


async def caravan_view(session, player, lang: str, *,
                       now: datetime | None = None) -> dict[str, Any] | None:
    """O bloco da Caravana para a praça (chat + mini-app + ui_v2).

    Flag OFF → **None** ⇒ o chamador não emite a key ⇒ payload byte-idêntico ao
    de hoje, e nenhuma query é feita (a lente dos 57).

    Traz SEMPRE as rotas — inclusive as trancadas, com o motivo dito ao lado
    (Lei §1: opção trancada APARECE trancada com o requisito). E traz sempre o
    aviso de que ir a pé é melhor: o velho diz isso na cara.
    """
    try:
        if player is None or not caravana_on():
            return None
        from core.i18n import t as i18n_t
        now = now or _utcnow()
        lang = (lang or "pt").lower()

        cont = getattr(player, "current_continent", None)
        if not is_valid_continent(cont):
            cont = "linghe"
        cont = str(cont)
        city = city_for_continent(cont)
        if not city:
            return None

        # Quem finaliza credita — a praça é um dos pontos de contenção.
        delivered = await credit_arrived(session, player, now=now, lang=lang)

        meta = CARAVAN_META[city]
        out: dict[str, Any] = {
            "city": city,
            "continent": cont,
            "has_caravan": bool(meta.get("caravan")),
            "npc_name": i18n_t(lang, meta["npc_name_key"]),
            "npc_intro": i18n_t(lang, meta["npc_intro_key"]),
            "ratio": ratio_for(cont),
            "units": max(1, CRV_LOAD_UNITS),
            "eta_hours": float(CRV_ETA_HOURS),
            # O velho NUNCA se vende como o melhor caminho.
            "honest_line": i18n_t(lang, "crv_better_to_go"),
            "delivered": [d for d in delivered if d.get("ok")],
            "bag_full": [d for d in delivered if not d.get("ok")],
        }

        if not meta.get("caravan"):
            # Mòyǔ: a ausência é identidade, e é DITA.
            out["locked_line"] = i18n_t(lang, "crv_no_caravan_here")
            return out

        soul = await _soul_refusal(session, player, city, lang)
        if soul:
            out["soul_locked"] = soul

        pend = [r for r in await _pending_rows(session, int(player.telegram_id))
                if not _delivered(r)]
        if pend:
            row = pend[0]
            left = max(0.0, (eta_of(row, now) - now).total_seconds() / 3600.0)
            out["in_transit"] = {
                "kind": str(row.item_type or ""),
                "item_id": int(row.item_id or 0),
                "units": int(row.quantity or 0),
                "hours_left": round(left, 1),
                "line": i18n_t(lang, "crv_in_transit", h=max(1, int(round(left)))),
            }

        enc_mats, enc_name = await _encargo_materials(session, cont, lang)

        # Nomes resolvidos DE UMA VEZ — rotas + pagamentos + atlas + a carga em
        # trânsito. Duas queries no total, nunca uma por linha.
        wanted: set[tuple[str, int]] = set(confined_materials())
        for k in routes_for(cont):
            wanted.add(k)
            wanted.update(accepted_payments(cont, *k))
        if pend:
            wanted.add((str(pend[0].item_type or ""), int(pend[0].item_id or 0)))
        for d in delivered:
            if d.get("kind"):
                wanted.add((str(d["kind"]), int(d["item_id"])))
        names = await resolve_names(session, {w for w in wanted if w[0] in ("herb", "ore")})

        def _nm(k) -> dict[str, str]:
            return names.get(k) or {"name": "", "emoji": ""}

        for d in out["delivered"] + out["bag_full"]:
            d.update(_nm((str(d.get("kind")), int(d.get("item_id") or 0))))
        if "in_transit" in out:
            it = out["in_transit"]
            it.update(_nm((it["kind"], it["item_id"])))

        routes: list[dict[str, Any]] = []
        for kind, iid in routes_for(cont):
            q = quote(cont, kind, iid)
            entry: dict[str, Any] = {
                "kind": kind,
                "item_id": iid,
                **_nm((kind, iid)),
                "tier": (material_origin(kind, iid) or {}).get("tier"),
                "units": int(q["units"]) if q else max(1, CRV_LOAD_UNITS),
                "cost": int(q["cost"]) if q else 0,
                "origin_line": origin_line(kind, iid, lang),
                "locked": False,
            }
            if (kind, iid) in enc_mats:
                entry["locked"] = True
                entry["reason"] = "encargo_conflict"
                entry["reason_line"] = i18n_t(
                    lang, "crv_refuse_encargo",
                    name=enc_name or i18n_t(lang, "crv_encargo_generic"))
            elif soul:
                entry["locked"] = True
                entry["reason"] = soul["reason"]
                entry["reason_line"] = soul["line"]
            elif pend:
                entry["locked"] = True
                entry["reason"] = "load_open"
                entry["reason_line"] = out["in_transit"]["line"]
            else:
                entry["pays"] = [
                    {"kind": k, "item_id": i, **_nm((k, i)),
                     "tier": (material_origin(k, i) or {}).get("tier")}
                    for (k, i) in accepted_payments(cont, kind, iid)
                    if (k, i) not in enc_mats
                ]
            routes.append(entry)
        out["routes"] = routes

        # A geografia dita, mesmo do que ela NÃO traz — o valor que serve
        # todos, sempre, de graça (§3.6 do spec).
        out["atlas"] = [
            {"kind": k, "item_id": i, **_nm((k, i)),
             "tier": (material_origin(k, i) or {}).get("tier"),
             "origin_line": origin_line(k, i, lang),
             "here": produced_in(k, i, cont)}
            for (k, i) in confined_materials()
        ]
        return out
    except Exception:
        logger.exception("caravan_view failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return None
