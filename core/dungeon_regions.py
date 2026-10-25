"""MV-1 — Mundo Vivo v2: dungeons ancoradas por continente.

UM helper para as DUAS superfícies (chat + mini-app): a lista filtra, o
enter/sweep recusa e o loot regional rola — tudo atrás da flag per-world
`dungeons_regionais` (OFF por defeito → main byte-idêntico; ver
DEFAULT_WORLD_FEATURES em database/db.py).

Regras:
- `DungeonCatalog.continent` NULL = portal não-ancorado → visível em todo lado.
- Flag OFF → tudo passa (lista global de hoje), nenhuma recusa, nenhum roll.
- Flag ON → só se veem/entram os portais do continente atual do jogador
  (+ os NULL); os restantes aparecem no bloco "Além do horizonte" (Lei §1:
  disclosure com CTA de viagem, nunca silent void).
- Loot regional (§5): runs hard/nightmare em dungeon ancorada ganham 1 roll
  extra de material NATIVO do continente — ADITIVO, runtime, nunca em seeds.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from core.continent_engine import (
    CONTINENT_KEYS,
    CONTINENT_META,
    DEFAULT_SPAWN_CONTINENT,
    is_valid_continent,
)

logger = logging.getLogger(__name__)


# ── Loot regional aditivo (§5) — reusa ids EXISTENTES de herb/ore ────────────
# qianhe → Mystic Silver (minério raro) · yanshan → Moonlight Moss (erva rara)
# fenghuo → Phoenix Ash (material de forja) · moyu → Void Crystal (essência
# sombria) · linghe → pedras espirituais. Chance modesta POR RUN, não por floor.
# Ids como STRING — a convenção dos bags (_roll_floor_loot faz str(id); os
# lookups de nome em _format_loot/_load_item_names são str-keyed).
REGIONAL_BONUS_CHANCE = 0.12
REGIONAL_BONUS_LOOT: dict[str, dict[str, Any]] = {
    "linghe":  {"stones": 250},
    "qianhe":  {"ores": {"3": 1}},   # Mystic Silver ⬜
    "yanshan": {"herbs": {"9": 1}},  # Moonlight Moss
    "fenghuo": {"ores": {"8": 1}},   # Phoenix Ash 🔥
    "moyu":    {"ores": {"6": 1}},   # Void Crystal 🌑
}


async def regional_bonus_line(session, regional: dict | None, lang: str = "pt") -> str:
    """QoL 04/08 (report [jogador]) — a linha do Tributo da Terra, com o ITEM e a
    QUANTIDADE ditos.

    Antes esta linha só nomeava o CONTINENTE ("🧭 Tributo da terra: 🏔️ Qiānhé
    cedeu um material nativo!") — e o servidor sabia exatamente o quê e quanto,
    porque `roll_regional_bonus` devolve o `loot` já multiplicado pelos `hits`.
    Era "payload entregue ≠ payload visto" ao pé da letra. E em Línghé a frase
    MENTIA: o que cai ali são 250 pedras espirituais, não "material nativo".

    Server-resolved (as 2 superfícies imprimem a MESMA string — nenhuma tela
    recalcula). Devolve "" quando não há nada a dizer; nunca levanta."""
    if not regional:
        return ""
    try:
        from core.i18n import t as i18n_t
        loot = regional.get("loot") or {}
        hits = max(1, int(regional.get("hits") or 1))
        parts: list[str] = []

        stones = int(loot.get("stones") or 0)
        if stones > 0:
            parts.append(i18n_t(lang, "dng_tribute_stones", stones=stones))

        # Os baldes por-id (minério/erva) resolvem no catálogo — emoji + nome +
        # quantidade, o mesmo formato que o resto do espólio já usa.
        from sqlalchemy import select as _select

        from database.models import HerbCatalog, OreCatalog
        for bucket, model in (("ores", OreCatalog), ("herbs", HerbCatalog)):
            ids = [int(k) for k in (loot.get(bucket) or {}).keys()]
            if not ids:
                continue
            rows = (await session.execute(
                _select(model).where(model.id.in_(ids))
            )).scalars().all()
            by_id = {int(r.id): r for r in rows}
            for raw_id, qty in (loot.get(bucket) or {}).items():
                row = by_id.get(int(raw_id))
                if row is None or int(qty) <= 0:
                    continue
                parts.append(f"{row.emoji or ''} {row.name} ×{int(qty)}".strip())

        if not parts:
            return ""
        line = i18n_t(lang, "dng_tribute_named",
                      emoji=regional.get("continent_emoji", "🧭"),
                      name=i18n_t(lang, "continent_" + str(regional.get("continent") or "")),
                      loot=", ".join(parts))
        # Lei §10 — numa varredura de 50 runs o tributo pode cair N vezes, e a
        # linha era IDÊNTICA à de 1 acerto. O número é dito.
        if hits > 1:
            line += " " + i18n_t(lang, "dng_tribute_hits", hits=hits)
        return line
    except Exception:
        logger.debug("regional_bonus_line failed", exc_info=True)
        return ""


def regionais_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão bt_ceremony_on). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("dungeons_regionais", world_key))
    except Exception:
        return False


def player_continent(player) -> str:
    """Continente atual do jogador (defensivo, fallback linghe)."""
    key = getattr(player, "current_continent", None)
    return key if is_valid_continent(key) else DEFAULT_SPAWN_CONTINENT


def continent_emoji(key: str | None) -> str:
    meta = CONTINENT_META.get(key or "") or {}
    return str(meta.get("emoji", ""))


def region_gate(dungeon, player) -> dict[str, Any] | None:
    """None = portal acessível daqui. Senão, payload de recusa honesta
    (`wrong_continent`) com o continente onde o portal REALMENTE fica.
    Server-side: o cliente esconde, o servidor garante."""
    if not regionais_on():
        return None
    cont = getattr(dungeon, "continent", None)
    if not cont or not is_valid_continent(cont):
        return None  # não-ancorada → visível em todo lado
    if player_continent(player) == cont:
        return None
    return {
        "reason": "wrong_continent",
        "continent": cont,
        "continent_emoji": continent_emoji(cont),
    }


def dungeon_visible_here(dungeon, player) -> bool:
    return region_gate(dungeon, player) is None


def elsewhere_summary(dungeons, player) -> list[dict[str, Any]]:
    """Bloco "🧭 Além do horizonte" (Lei §1): os portais ancorados NOUTROS
    continentes, na ordem canónica dos continentes.

    ⚠️ MV-9 §P6 — ISTO ERA UM APAGADOR. A versão original devolvia só
    ``{continent, emoji, count}``: com `dungeons_regionais` ON, um jogador em
    Yǎnshān perdia de vista 20 dos 23 portais do mundo — sem nome, sem reino
    exigido, sem nada. O objeto rico (nome, BP, reinos, drops) é CONSTRUÍDO uma
    linha acima em `webserver.py` e deitado fora. "Contagem anônima" não é
    disclosure: é um número que não deixa ninguém decidir nada.

    O molde correto é o que a casa já pratica em três sítios
    (`environment_engine.project_environment`, `legacy_cave_engine.cave_view`,
    `travel_engine.list_travel_destinations`): lista COMPLETA, cada item com o
    seu lugar e o motivo de não poder agir agora. Aqui: `name`/`emoji`/
    `min_realm` por portal, e a contagem preservada para quem só a queira.

    `count` continua no dicionário — os dois renders antigos leem-no, e trocar a
    forma sem trocar os leitores é a armadilha "payload-shape change varre TODOS
    os consumers". Vazio com flag OFF (nenhum dungeon é filtrado).
    """
    if not regionais_on():
        return []
    cur = player_continent(player)
    by_cont: dict[str, list[dict[str, Any]]] = {}
    for d in dungeons:
        cont = getattr(d, "continent", None)
        if cont and is_valid_continent(cont) and cont != cur:
            by_cont.setdefault(cont, []).append({
                "id": int(getattr(d, "id", 0) or 0),
                "name": getattr(d, "name", "") or "",
                "emoji": getattr(d, "emoji", None) or "🗺️",
                "min_realm": int(getattr(d, "min_realm", 0) or 0),
            })
    return [
        {
            "continent": key,
            "emoji": continent_emoji(key),
            "count": len(by_cont[key]),
            # A lista COMPLETA — nenhum portal fica sem nome (Lei §1).
            "portals": sorted(by_cont[key], key=lambda p: (p["min_realm"], p["id"])),
        }
        for key in CONTINENT_KEYS
        if key in by_cont
    ]


async def rebirth_portal_warning(session, player, lang: str = "pt") -> str:
    """QoL 09/08 Item D (report [jogador] 08/08) — o aviso ANTES de renascer.

    `prestige_engine.process_prestige` põe ``realm = 0`` e **não toca no
    continente**. Com `dungeons_regionais` ON isso é uma armadilha silenciosa
    e IRREVERSÍVEL: as 23 masmorras estão ancoradas, e as de reino baixo
    simplesmente não existem nos continentes distantes. Renascer em 🌑 Mòyǔ
    deixa o cultivador **cinco reinos** sem uma única porta (o 1º portal de lá
    abre no reino 5); em 🌋 Fēnghuǒ são três.

    Não é punição que alguém desenhou — é um aviso que nunca foi escrito. O
    jogador carrega no botão e só descobre depois. (Medido nas 2 DBs em 08/08:
    ZERO jogadores presos hoje — armadilha armada e nunca disparada. Ela é um
    problema do **servidor de launch**, onde renascer é loop central e
    `dungeons_regionais` nasce ON.)

    Devolve ``""`` quando não há nada a dizer — flag OFF (lista global, nenhuma
    geografia) ou o continente atual já tem porta para o reino 0. Server-
    resolved e **PLAIN TEXT**: as 2 superfícies imprimem a MESMA string, e o
    chat manda isto dentro de um bloco Markdown (lição "string dual-surface =
    plain text"). Nunca levanta.
    """
    try:
        if not regionais_on():
            return ""
        from sqlalchemy import select as _select

        from core.i18n import t as i18n_t
        from database.models import DungeonCatalog

        rows = (await session.execute(_select(DungeonCatalog))).scalars().all()
        # A MESMA régua da lista de Portais — nada de reimplementar o filtro
        # aqui (os não-ancorados contam: são visíveis em todo lado). O
        # continente do jogador não muda ao renascer, então `player` já é o
        # estado pós-renascimento para efeitos de geografia.
        here = [d for d in rows if dungeon_visible_here(d, player)]
        lowest = min(
            (int(getattr(d, "min_realm", 0) or 0) for d in here), default=None
        )
        if lowest is not None and lowest <= 0:
            return ""

        cont = player_continent(player)
        emoji = continent_emoji(cont)
        name = i18n_t(lang, "continent_" + cont)
        if lowest is None:
            # Nenhum portal ancorado aqui — pior do que tarde, é nenhum.
            return i18n_t(lang, "prestige_warn_no_portal_here", emoji=emoji, name=name)
        return i18n_t(
            lang, "prestige_warn_no_low_portal", emoji=emoji, name=name, realm=lowest
        )
    except Exception:
        logger.debug("rebirth_portal_warning failed", exc_info=True)
        return ""


def roll_regional_bonus(dungeon, difficulty: str | None, runs: int = 1) -> dict[str, Any] | None:
    """1 roll extra de material nativo por run hard/nightmare (flag ON,
    dungeon ancorada). ADITIVO: o caller faz `_merge_bag(bag, ret["loot"])`
    ANTES do transfer. Devolve None quando não aplica ou não caiu nada."""
    if difficulty not in ("hard", "nightmare"):
        return None
    if not regionais_on():
        return None
    cont = getattr(dungeon, "continent", None)
    if not cont or cont not in REGIONAL_BONUS_LOOT:
        return None
    hits = sum(1 for _ in range(max(1, int(runs))) if random.random() < REGIONAL_BONUS_CHANCE)
    if hits <= 0:
        return None
    base = REGIONAL_BONUS_LOOT[cont]
    loot: dict[str, Any] = {}
    for key, val in base.items():
        if isinstance(val, dict):
            loot[key] = {item_id: qty * hits for item_id, qty in val.items()}
        else:
            loot[key] = val * hits
    return {
        "loot": loot,
        "continent": cont,
        "continent_emoji": continent_emoji(cont),
        "hits": hits,
    }
