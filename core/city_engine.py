"""MV-9 城 — As Cinco Cidades (Mundo Vivo v2, pilar §3-P1 "Geografia real").

Cada continente deixa de ser um rótulo e passa a ter UM lugar com nome, cara e
um pedido. Os cinco nomes vêm do `world_lore.md §3` — zero invenção:

    🏔️ Línghé   → Cidade de Wànshì 万事城        (universal · sects)
    ⛰️ Qiānhé   → Templo do Punho de Ferro       (body · ores)
    🌸 Yǎnshān  → Jardim das Dez Mil Flores      (herbs · alchemy)
    🌋 Fēnghuǒ  → Forja de Tiānhuǒ               (forge · combat)
    🌑 Mòyǔ     → Cidade dos Ecos                (forbidden · demonic)

Design (molde travel_engine / jianghu_engine):
    * `CITY_META` é engine data, NOT DB — wipe-safe, Lei §5. **ZERO tabela, ZERO
      row, ZERO migration.** É o 8º mapa geográfico da família (CONTINENT_META,
      EXPLORATION_NODES, TEMPER_SITES, CAVE_HOUSES, REGIONAL_BONUS_LOOT,
      WORLD_SECT_META, LINEAGE_META) e segue a convenção mais recente da casa:
      keyed por slug ASCII + `CITY_KEYS` para ordem estável + índice reverso
      `CONTINENT_TO_CITY` derivado por compreensão (molde
      `legacy_cave_engine.CONTINENT_TO_NPC`).
    * TODA string visível é uma `*_key` de i18n, resolvida NO SERVIDOR (padrão
      Crônica/jiānghú: `title`/`intro` chegam prontos ao cliente). Nenhuma
      dessas keys pode conter placeholder — são resolvidas por `t()` SEM kwargs
      (a lição escrita em `region_state_engine.py:106-110`).
    * O ENCARGO 城务 é DERIVADO: função pura de `(world_key, continent,
      tick_epoch)` modulada pelo estado regional (MV-3) e pelo evento do Céu
      (MV-2). Sem tabela de encargos, sem sweep de órfãos, sem kill-switch a
      construir — o desenho do MV-8, que se provou.
    * O CONTEÚDO do encargo (objetivo, contagem, recompensa) vive no
      `storylet_catalog` (seeds), NUNCA aqui: UMA verdade. Este engine escolhe
      QUAL encargo está vigente; o MV-5 responde O QUE ele é.

⚠️ `continent_key` continua a ser o CONTINENTE, SEMPRE. Nunca escrever uma
chave de cidade em `world_events.continent_key` / `world_chronicle.continent_key`
/ `bounties.continent_key`: mata oito consumidores em silêncio (o incidente
`legacy_cave` de 2026-08-04, post-mortem em `tiandao_engine.py:74-86`). A cidade
viaja como `params["city_key"]`, campo ADITIVO, nunca como lugar do row.

Conjunção DECLARADA (não existe registo Python de dependências entre flags — o
precedente é TEC-3 × TEC-1): o **Encargo** exige `quests_vivas` ON porque o motor
é o storylet do MV-5. Com `quests_vivas` OFF a cidade continua a ter nome,
identidade e razão-de-ir — e a superfície DIZ que o encargo está fechado, com o
requisito nomeado (Lei §1). A flag `cidades` sozinha nunca produz um botão morto.

Segurança de produção (Lei §5): flag `cidades` OFF em TODO mundo, `main` lê
sempre os defaults (`db.py:428-429`). Todo bloco de payload é ADITIVO
(`**({...} if x else {})`) ⇒ com a flag OFF o payload é byte-idêntico ao de hoje.
"""
from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from core.continent_engine import CONTINENT_KEYS, is_valid_continent

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Gate da flag (molde tiandao_engine.director_on) — fail-safe → False
# ══════════════════════════════════════════════════════════════════════════

def cidades_on(world_key: str | None = None) -> bool:
    """Gate estável da flag `cidades`. Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("cidades", world_key))
    except Exception:
        return False


def _quests_vivas_on() -> bool:
    """A conjunção declarada (MV-5). Fail-safe → False."""
    try:
        from core.storylet_engine import quests_vivas_on
        return bool(quests_vivas_on())
    except Exception:
        return False


def current_world_key() -> str:
    """O mundo atual (molde literal `jianghu_engine.current_world_key`).

    ⚠️ Lê a ContextVar `current_world` DIRETO — não existe função pública
    `current_world_key` em `database.db`. Fail-safe → 'main'.
    """
    try:
        from database.db import current_world, MAIN_WORLD_KEY
        return str(current_world.get() or MAIN_WORLD_KEY)
    except Exception:
        return "main"


# ══════════════════════════════════════════════════════════════════════════
# Tuning (engine, not DB — wipe-safe; env-overridable para ops)
# ══════════════════════════════════════════════════════════════════════════

# ⚠️ UM DIA, não um batimento de 6h — e a razão é o UNFOLDING, medida na
# simulação de 7 dias antes de existir superfície nenhuma.
#
# A latência de leitura da Crônica (MV-8, `rumor_delay_hours`) é de 6h a 12h. Com
# o encargo a mudar de 6 em 6 horas, quem está longe leria SEMPRE um pedido que
# já não é verdade: a notícia chegava depois de a cidade ter mudado de ideias, e
# a promessa da onda ("você sabia antes de chegar") virava mentira. Pior, cinco
# cidades × ~2,7 mudanças/dia = ~13 linhas/dia só de encargos, afogando o resto
# da Crônica (o pulse inteiro escreve ~36).
#
# Com 24h: a notícia percorre o mundo inteiro em 12h e o pedido continua de pé
# outras 12h — há um dia inteiro para agir sobre o que se leu — e a Crônica
# ganha 5 linhas/dia, uma por cidade. O `pulse_cities` continua a correr de 6 em
# 6h e só escreve quando o dia virou (3 de 4 batimentos são no-op).
CITY_TICK_HOURS = float(os.getenv("CITY_TICK_HOURS", "24"))

# Prazo do encargo aceito. Duas janelas de 6h: dá para atravessar um sono sem
# perder, e é curto o bastante para o pedido continuar a ser DESTE momento.
ENCARGO_EXPIRES_HOURS = float(os.getenv("CITY_ENCARGO_EXPIRES_HOURS", "12"))

# Anti-farm honesto: depois de ENTREGAR um encargo, aquele MESMO encargo não
# volta a ser aceitável por N horas. Sem isto, um jogador parado na cidade
# entregaria o mesmo pedido de 6 em 6 horas para sempre. Não tranca a cidade —
# tranca a repetição (e a recusa DIZ quanto falta, Lei §1).
ENCARGO_REPEAT_HOURS = float(os.getenv("CITY_ENCARGO_REPEAT_HOURS", "20"))



# ══════════════════════════════════════════════════════════════════════════
# As cinco cidades — engine data, NOT DB (wipe-safe, Lei §5)
# ══════════════════════════════════════════════════════════════════════════
# Campos:
#   continent : o continente que a cidade ocupa (chave de CONTINENT_KEYS). A
#               cidade NUNCA substitui o continente — ela mora nele.
#   emoji     : dado literal (emojis nunca são i18n — `race_engine.py:43-48`).
#   name_key / intro_key / trait_key : i18n de CHAT (server-resolved). SEM
#               placeholders — são resolvidas por t() sem kwargs.
#   encargos  : os pedidos possíveis daquela cidade, em ordem estável. Cada um:
#                 key  -> a row de `storylet_catalog` (o CONTEÚDO vive lá)
#                 icon -> o ícone da linha
#                 util -> a utilidade: `base` + bônus por estado regional (MV-3)
#                         e por evento do Céu ativo (MV-2). Molde JH_GOALS.
#               Três por cidade: o bastante para o pedido MUDAR de dia a dia
#               (senão o "estado da cidade" era decoração), poucos o bastante
#               para cada um ter dente (Lei §3 — profundidade > variedade).
#
# ⚠️ DUAS regras que a SIMULAÇÃO de 7 dias impôs (a 1ª versão falhou nas duas,
#    e nenhuma das duas falhas seria visível numa tela):
#
#  (a) `base` é IGUAL nos três e NÃO existe bônus de `prospera`. Um bônus no
#      estado NEUTRO não é modulação — é um polegar permanente na balança:
#      medido em s2, 70% dos dias têm os cinco continentes em `prospera`, e um
#      +0.10 ali fazia UM encargo sair 22-25 vezes em 28 e outro sair 0-1 (a
#      cidade de Qiānhé passou 7 dias sem NUNCA pedir o terceiro). Em paz os
#      três rodam por sorteio; na CRISE o bônus (0.28-0.30, maior que o jitter
#      de 0.30) manda — que é exatamente o que "o estado modula" quer dizer.
#
#  (b) Os bônus de evento usam os event_type REAIS de `world_events`
#      (`beast_tide` / `meteor` — `tiandao_engine.DIRECTOR_EVENT_TYPES`), e só
#      onde o evento PODE nascer: `TIDE_CONTINENTS` exclui Mòyǔ e
#      `METEOR_CONTINENTS` é só qianhe/yanshan/fenghuo. Um bônus de meteoro em
#      Línghé, ou qualquer bônus de evento em Mòyǔ, seria modulação MORTA — não
#      dispararia nunca e ninguém daria por isso. (A 1ª versão escreveu
#      `wev_beast_tide`, que é o event_type da CRÔNICA e não o do `world_events`:
#      as cinco cidades nasceram com a modulação de evento morta, e foi a
#      simulação — não a tela — que disse.)
#
# ⚠️ Os `objective_type` usados aqui existem TODOS hoje e são SOLO-completáveis.
#    `sparring` / `win_sparring` estão VETADOS: exigem um segundo jogador vivo e
#    consentido (0 sparrings em 30d no main, 0 desde sempre no s2 — a 4ª
#    recorrência do mesmo dead-end). `arena_win` é seguro: a fila da arena
#    gera um oponente NPC por timeout (`arena_engine._spawn_npc_fallback`) e o
#    settle rastreia `arena_win` no MESMO ramo (`arena_duel_settle.py:301`).
CITY_META: dict[str, dict[str, Any]] = {
    "wanshi": {
        "continent": "linghe",
        "emoji": "🏙️",
        "name_key": "city_wanshi_name",
        "intro_key": "city_wanshi_intro",
        "trait_key": "city_wanshi_trait",
        # Línghé tem Maré (TIDE_CONTINENTS) mas NÃO tem meteoro.
        "encargos": (
            {"key": "enc_linghe_selos", "icon": "🏛️",
             "util": {"base": 0.30}},
            {"key": "enc_linghe_vigilia", "icon": "🧘",
             "util": {"base": 0.30, "festival": 0.16}},
            {"key": "enc_linghe_escolta", "icon": "🛡️",
             "util": {"base": 0.30, "sitiada": 0.30, "tensa": 0.16, "beast_tide": 0.25}},
        ),
    },
    "tiequan": {
        "continent": "qianhe",
        "emoji": "🏯",
        "name_key": "city_tiequan_name",
        "intro_key": "city_tiequan_intro",
        "trait_key": "city_tiequan_trait",
        # Qiānhé tem Maré E meteoro (o metal do céu cai aqui).
        "encargos": (
            {"key": "enc_qianhe_minerio", "icon": "⛏️",
             "util": {"base": 0.30, "meteor": 0.24}},
            {"key": "enc_qianhe_provas", "icon": "👊",
             "util": {"base": 0.30, "sitiada": 0.30, "tensa": 0.18}},
            {"key": "enc_qianhe_carga", "icon": "🐾",
             "util": {"base": 0.30, "festival": 0.20, "beast_tide": 0.16}},
        ),
    },
    "wanhua": {
        "continent": "yanshan",
        "emoji": "🌺",
        "name_key": "city_wanhua_name",
        "intro_key": "city_wanhua_intro",
        "trait_key": "city_wanhua_trait",
        # Yǎnshān tem Maré E meteoro.
        "encargos": (
            {"key": "enc_yanshan_pilulas", "icon": "⚗️",
             "util": {"base": 0.30, "festival": 0.20, "meteor": 0.16}},
            {"key": "enc_yanshan_remedio", "icon": "💊",
             "util": {"base": 0.30, "sitiada": 0.30, "beast_tide": 0.25}},
            {"key": "enc_yanshan_colheita", "icon": "🌿",
             "util": {"base": 0.30, "tensa": 0.18}},
        ),
    },
    "tianhuo": {
        "continent": "fenghuo",
        "emoji": "🔥",
        "name_key": "city_tianhuo_name",
        "intro_key": "city_tianhuo_intro",
        "trait_key": "city_tianhuo_trait",
        # Fēnghuǒ tem Maré E meteoro (o minério estelar alimenta a forja).
        "encargos": (
            {"key": "enc_fenghuo_forja", "icon": "🔨",
             "util": {"base": 0.30, "meteor": 0.24}},
            {"key": "enc_fenghuo_tempera", "icon": "⚔️",
             "util": {"base": 0.30, "sitiada": 0.30, "tensa": 0.18, "beast_tide": 0.20}},
            {"key": "enc_fenghuo_arena", "icon": "🏟️",
             "util": {"base": 0.30, "festival": 0.22}},
        ),
    },
    "huiyin": {
        "continent": "moyu",
        "emoji": "🕯️",
        "name_key": "city_huiyin_name",
        "intro_key": "city_huiyin_intro",
        "trait_key": "city_huiyin_trait",
        # ⚠️ Mòyǔ não recebe NENHUM evento do Céu: está fora de
        # `TIDE_CONTINENTS` e de `METEOR_CONTINENTS`. Qualquer bônus de evento
        # aqui seria letra morta — a Cidade dos Ecos modula só pelo estado.
        "encargos": (
            {"key": "enc_moyu_ruinas", "icon": "🕳️",
             "util": {"base": 0.30}},
            {"key": "enc_moyu_ecos", "icon": "👁️",
             "util": {"base": 0.30, "sitiada": 0.28, "tensa": 0.18}},
            {"key": "enc_moyu_vigilia", "icon": "🌑",
             "util": {"base": 0.30, "festival": 0.16}},
        ),
    },
}

# Ordem canónica de exibição = a ordem dos continentes (centro primeiro, o
# proibido no fim) — para as cinco linhas do /viajar saírem sempre iguais.
CITY_KEYS: tuple[str, ...] = tuple(
    ck for cont in CONTINENT_KEYS
    for ck, meta in CITY_META.items() if meta["continent"] == cont
)

# Índice reverso derivado (molde `legacy_cave_engine.CONTINENT_TO_NPC`).
CONTINENT_TO_CITY: dict[str, str] = {m["continent"]: k for k, m in CITY_META.items()}

# Todas as keys de encargo, achatadas — o teste e o verificador de i18n leem daqui.
ENCARGO_KEYS: tuple[str, ...] = tuple(
    e["key"] for ck in CITY_KEYS for e in CITY_META[ck]["encargos"]
)


# ══════════════════════════════════════════════════════════════════════════
# Helpers puros
# ══════════════════════════════════════════════════════════════════════════

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def city_key_for(continent: str | None) -> str | None:
    """A cidade daquele continente (None se o continente for inválido)."""
    if not is_valid_continent(continent):
        return None
    return CONTINENT_TO_CITY.get(str(continent))


def city_continent(city_key: str | None) -> str | None:
    meta = CITY_META.get(str(city_key or ""))
    return meta["continent"] if meta else None


def city_emoji(city_key: str | None) -> str:
    return str((CITY_META.get(str(city_key or "")) or {}).get("emoji", "🏙️"))


def city_name(city_key: str | None, lang: str) -> str:
    """O nome da cidade no idioma do leitor. Fail-safe → a key crua NUNCA sai:
    sem meta devolve string vazia (o chamador decide o fallback)."""
    meta = CITY_META.get(str(city_key or ""))
    if not meta:
        return ""
    try:
        from core.i18n import t as i18n_t
        return str(i18n_t(lang, meta["name_key"]))
    except Exception:
        return ""


def tick_epoch(now: datetime | None = None) -> int:
    """O batimento da cidade (molde literal `jianghu_engine.tick_epoch`)."""
    now = now or _utcnow()
    return int(now.timestamp() // max(1.0, CITY_TICK_HOURS * 3600.0))


def seed_for(world_key: str, continent: str, epoch: int) -> str:
    """A semente do RNG — **com o `world_key` DENTRO**.

    A lição do MV-8, medida: o World Pulse semeava só com `(sect_id, epoch)` e
    main e s2 contaram a MESMA história durante 7 dias. Uma cidade que pede a
    mesma coisa em todo servidor não é um mundo vivo, é um roteiro.
    """
    return f"cidades:{world_key}:{continent}:{epoch}"


def encargo_key_for(
    continent: str | None,
    *,
    now: datetime | None = None,
    world_key: str | None = None,
    region_state: str | None = None,
    events: set[str] | tuple[str, ...] | None = None,
) -> str | None:
    """O encargo VIGENTE daquela cidade neste batimento. **PURA** — zero I/O.

    Utilidade = `base` + bônus do estado regional (MV-3) + bônus do evento do
    Céu ativo (MV-2) + um jitter semeado por `(world, continent, epoch, key)`.
    O jitter é o que faz o pedido MUDAR quando nada no mundo mudou — e é ele
    que garante que as cinco cidades não pedem a mesma coisa no mesmo dia
    (a semente inclui o continente).

    Fail-safe → None (continente inválido / mapa vazio). Nunca levanta.
    """
    try:
        city = city_key_for(continent)
        if not city:
            return None
        encargos = CITY_META[city]["encargos"]
        if not encargos:
            return None
        epoch = tick_epoch(now)
        world = world_key or current_world_key()
        ev = set(events or ())
        st = str(region_state or "prospera")
        best_key, best_score = None, float("-inf")
        for e in encargos:
            util = e.get("util") or {}
            score = float(util.get("base", 0.0))
            score += float(util.get(st, 0.0))
            for evt in ev:
                score += float(util.get(evt, 0.0))
            # Jitter determinístico por encargo: o RNG é re-semeado por chave
            # para a ordem de iteração nunca influenciar o resultado.
            rng = random.Random(seed_for(world, str(continent), epoch) + ":" + str(e["key"]))
            score += rng.random() * 0.30
            if score > best_score:
                best_key, best_score = str(e["key"]), score
        return best_key
    except Exception:
        logger.exception("encargo_key_for failed continent=%s", continent)
        return None


def encargo_icon(encargo_key: str | None) -> str:
    for ck in CITY_KEYS:
        for e in CITY_META[ck]["encargos"]:
            if e["key"] == encargo_key:
                return str(e.get("icon", "📜"))
    return "📜"


# ══════════════════════════════════════════════════════════════════════════
# Reads — a cidade projetada para as superfícies (server-resolved)
# ══════════════════════════════════════════════════════════════════════════

def city_view(continent: str | None, lang: str) -> dict[str, Any] | None:
    """A IDENTIDADE da cidade daquele continente: {key, emoji, name, intro,
    trait}. Server-resolved (padrão Crônica) — o cliente só exibe. PURA.

    Flag OFF → None ⇒ o chamador não emite a key ⇒ payload byte-idêntico.
    """
    try:
        if not cidades_on():
            return None
        city = city_key_for(continent)
        if not city:
            return None
        from core.i18n import t as i18n_t
        meta = CITY_META[city]
        return {
            "key": city,
            "continent": meta["continent"],
            "emoji": meta["emoji"],
            "name": i18n_t(lang, meta["name_key"]),
            "intro": i18n_t(lang, meta["intro_key"]),
            "trait": i18n_t(lang, meta["trait_key"]),
        }
    except Exception:
        logger.exception("city_view failed continent=%s", continent)
        return None


async def _world_ctx(session, continent: str) -> tuple[str, set[str]]:
    """(estado regional, tipos de evento ativos) daquele continente. Leitores
    gated dos irmãos MV-2/MV-3 — flag deles OFF → neutro sem query."""
    st = "prospera"
    events: set[str] = set()
    try:
        from core.region_state_engine import region_state
        st = await region_state(session, continent)
    except Exception:
        logger.debug("city world ctx region_state failed", exc_info=True)
    try:
        from core.tiandao_engine import director_on, DIRECTOR_EVENT_TYPES
        if director_on():
            from database.models import WorldEvent
            rows = (await session.execute(
                select(WorldEvent.event_type).where(
                    WorldEvent.state == "active",
                    WorldEvent.continent_key == continent,
                    WorldEvent.event_type.in_(DIRECTOR_EVENT_TYPES),
                    WorldEvent.expires_at > _utcnow(),
                )
            )).scalars().all()
            events = {str(r) for r in rows}
    except Exception:
        logger.debug("city world ctx events failed", exc_info=True)
    return st, events


async def _encargo_catalog_row(session, encargo_key: str):
    """A row do `storylet_catalog` — a ÚNICA verdade do conteúdo do encargo."""
    try:
        from database.models import StoryletCatalog
        return await session.get(StoryletCatalog, str(encargo_key))
    except Exception:
        logger.debug("encargo catalog row failed key=%s", encargo_key, exc_info=True)
        return None


def _encargo_labels(encargo_key: str, lang: str, cat) -> dict[str, Any]:
    """Nome/descrição/objetivo/recompensa do encargo, server-resolved.

    Reusa a convenção de keys do MV-5 (`sty_<key>_name` / `_desc`) — o encargo
    É um storylet, e ter duas convenções para a mesma row era garantir que uma
    delas ficasse para trás.
    """
    from core.i18n import t as i18n_t
    out: dict[str, Any] = {
        "key": encargo_key,
        "icon": encargo_icon(encargo_key),
        "name": i18n_t(lang, f"sty_{encargo_key}_name"),
        "desc": i18n_t(lang, f"sty_{encargo_key}_desc"),
    }
    if cat is not None:
        # Os MESMOS campos que `storylet_engine._accepted_view` já entrega
        # (`objective_type` / `objective_count` / `reward_line`).
        #
        # ⚠️ CORREÇÃO 2026-08-07 (report do [jogador] sobre "A Fornalha Não Pode
        # Esfriar"): o comentário que estava aqui dizia que "as duas superfícies
        # já sabem desenhar isto (`progress / objective_count` +
        # `QUEST_OBJECTIVE_TAB[objective_type]`)" e que uma frase de objetivo
        # seria "uma key de UI nova que ninguém pediu". As duas metades eram
        # falsas: nenhuma das superfícies desenhava o objetivo (só a barra e o
        # "0 / 3" — um contador sem substantivo), e `forge_artifact` era o ÚNICO
        # `objective_type` do jogo inteiro fora do `QUEST_OBJECTIVE_TAB`, logo o
        # deep-link presumido nunca existiu para este encargo. Um jogador ficou
        # bloqueado por isso. A frase agora vem pronta do storylet_engine — UMA
        # verdade para o encargo e para a quest.
        out["objective_type"] = str(getattr(cat, "objective_type", "") or "")
        out["objective_count"] = max(1, int(getattr(cat, "objective_count", 1) or 1))
        try:
            from core.storylet_engine import _reward_line
            out["reward_line"] = _reward_line(
                getattr(cat, "reward", None) or {}, lang)
        except Exception:
            logger.debug("encargo reward line failed", exc_info=True)
        try:
            from core.storylet_engine import objective_chat_cmd, objective_line
            out["objective_line"] = objective_line(
                out["objective_type"], out["objective_count"], lang)
            out["objective_cmd"] = objective_chat_cmd(out["objective_type"])
        except Exception:
            logger.debug("encargo objective line failed", exc_info=True)
    return out


async def encargo_view(session, continent: str | None, lang: str, *,
                       now: datetime | None = None,
                       delay_hours: float = 0.0) -> dict[str, Any] | None:
    """O encargo VIGENTE de uma cidade, projetado.

    ``delay_hours`` é o UNFOLDING (§Q3): quem está longe lê o encargo que a
    cidade tinha **quando a notícia partiu**. Como a derivação é pura, isso é
    literalmente `encargo_key_for(now - delay)` — zero storage, zero row nova.
    O estado regional usado na modulação é o de AGORA (o eixo do MV-3 move-se
    devagar: medido em s2, 70% dos dias têm os cinco continentes no mesmo
    estado) — a aproximação está declarada aqui de propósito.

    Flag OFF → None. `quests_vivas` OFF → devolve a RECUSA nomeada (Lei §1: a
    cidade diz que o encargo está fechado e porquê), nunca silêncio.
    """
    try:
        if not cidades_on() or not is_valid_continent(continent):
            return None
        now = now or _utcnow()
        if not _quests_vivas_on():
            from core.i18n import t as i18n_t
            return {"locked": True, "reason": "quests_vivas_off",
                    "line": i18n_t(lang, "cid_encargo_locked")}
        st, events = await _world_ctx(session, str(continent))
        at = now - timedelta(hours=max(0.0, float(delay_hours)))
        key = encargo_key_for(continent, now=at, region_state=st, events=events)
        if not key:
            return None
        cat = await _encargo_catalog_row(session, key)
        view = _encargo_labels(key, lang, cat)
        view["locked"] = False
        view["stale_hours"] = int(delay_hours) if delay_hours else 0
        return view
    except Exception:
        logger.exception("encargo_view failed continent=%s", continent)
        return None


# ══════════════════════════════════════════════════════════════════════════
# O ENCARGO — estado do jogador (o storylet do MV-5 com dono fixo)
# ══════════════════════════════════════════════════════════════════════════

async def _my_encargo_rows(session, player_id: int):
    """As rows de encargo DESTE jogador (abertas + resolvidas recentes)."""
    from database.models import PlayerStorylet
    cut = _utcnow() - timedelta(hours=max(ENCARGO_REPEAT_HOURS, 24.0))
    return (await session.execute(
        select(PlayerStorylet).where(
            PlayerStorylet.player_id == int(player_id),
            PlayerStorylet.storylet_key.in_(ENCARGO_KEYS),
            (PlayerStorylet.status.in_(("offered", "accepted")))
            | (PlayerStorylet.resolved_at >= cut),
        )
    )).scalars().all()


async def city_plaza_view(session, player, lang: str) -> dict[str, Any] | None:
    """O bloco da CIDADE para a praça (chat + mini-app): identidade + encargo
    vigente + o meu estado nele (aceito? quanto falta? posso aceitar?).

    Flag OFF → None ⇒ a key nem existe no payload (byte-idêntico).
    """
    try:
        if player is None or not cidades_on():
            return None
        cont = getattr(player, "current_continent", None)
        if not is_valid_continent(cont):
            cont = "linghe"
        view = city_view(cont, lang)
        if not view:
            return None
        enc = await encargo_view(session, cont, lang)
        if enc:
            view["encargo"] = enc
        if enc and not enc.get("locked"):
            view["encargo"]["mine"] = await _my_encargo_state(
                session, player, str(enc["key"]), lang)
        return view
    except Exception:
        logger.exception("city_plaza_view failed")
        return None


async def _my_encargo_state(session, player, encargo_key: str, lang: str) -> dict[str, Any]:
    """{status, progress, count, can_accept, reason} — a RECUSA sempre nomeada."""
    from core.i18n import t as i18n_t
    out: dict[str, Any] = {"status": "none", "can_accept": True, "reason": None}
    try:
        now = _utcnow()
        rows = await _my_encargo_rows(session, int(player.telegram_id))
        cat = await _encargo_catalog_row(session, encargo_key)
        count = max(1, int(getattr(cat, "objective_count", 1) or 1)) if cat else 1
        for r in rows:
            if r.status == "accepted":
                exp = _aware(r.expires_at)
                # ⚠️ A contagem tem de ser a DESTA row, nunca a do encargo hoje
                # afixado. `count` é do encargo vigente; usá-lo aqui comparava o
                # progresso de uma quest com o objetivo de OUTRA — e como os
                # encargos de `cultivate` pedem 120/180 enquanto os restantes
                # pedem 2-12, a linha "vencida" quase nunca disparava: uma row
                # expirada há horas passava por aberta e a cidade RECUSAVA para
                # sempre o encargo do dia, mandando "termine ou deixe vencer"
                # uma quest que já tinha vencido. A praça nunca chama
                # `sync_player_storylets` (isso vive no caminho de Missões),
                # portanto nada desfazia o bloqueio sozinho.
                _rcat = await _encargo_catalog_row(session, r.storylet_key)
                _rcount = max(1, int(getattr(_rcat, "objective_count", 1) or 1)) if _rcat else 1
                if exp and exp <= now and int(r.progress or 0) < _rcount:
                    continue  # vencida — o sync do MV-5 faz o flip honesto
                mine_is_current = (r.storylet_key == encargo_key)
                out.update({
                    "status": "accepted" if mine_is_current else "busy",
                    "progress": int(r.progress or 0),
                    "count": count if mine_is_current else None,
                    "can_accept": False,
                    "reason": None if mine_is_current else "other_encargo_open",
                })
                if not mine_is_current:
                    out["reason_line"] = i18n_t(
                        lang, "cid_refuse_other_open",
                        name=i18n_t(lang, f"sty_{r.storylet_key}_name"))
                elif int(r.progress or 0) >= count:
                    out["status"] = "ready"
                out["row_id"] = int(r.id)
                return out
            if r.storylet_key == encargo_key and r.status == "done":
                res = _aware(r.resolved_at)
                if res and (now - res) < timedelta(hours=ENCARGO_REPEAT_HOURS):
                    left = ENCARGO_REPEAT_HOURS - (now - res).total_seconds() / 3600.0
                    out.update({
                        "status": "cooldown", "can_accept": False,
                        "reason": "encargo_repeat",
                        "reason_line": i18n_t(lang, "cid_refuse_repeat",
                                              h=max(1, int(round(left)))),
                    })
                    return out
        return out
    except Exception:
        logger.exception("_my_encargo_state failed")
        out["can_accept"] = False
        out["reason"] = "internal_error"
        return out


async def accept_encargo(session, player, *, lang: str | None = None) -> dict[str, Any]:
    """ACEITAR o encargo da cidade onde o jogador ESTÁ.

    Materializa uma row `player_storylets` já em `accepted` — o encargo não é
    uma oferta sorteada, é um pedido PERMANENTE afixado na cidade; passar pelo
    `maybe_offer` seria submetê-lo ao pacer de 12h e torná-lo invisível de
    longe, que é exatamente o que esta onda existe para consertar.

    O caller trava a row do jogador FOR UPDATE e é dono do commit (contrato de
    `claim_storylet` / `bounty_engine.claim_bounty`).

    Toda recusa é NOMEADA (Lei §1) e devolve `reason` + `line`.
    """
    from core.i18n import t as i18n_t
    lang = (lang or getattr(player, "language", None) or "pt").lower()

    def _no(reason: str, key: str, **kw) -> dict[str, Any]:
        return {"ok": False, "reason": reason, "line": i18n_t(lang, key, **kw)}

    try:
        if player is None:
            return {"ok": False, "reason": "no_player"}
        if not cidades_on():
            return _no("cidades_off", "cid_refuse_flag")
        if not _quests_vivas_on():
            return _no("quests_vivas_off", "cid_encargo_locked")
        cont = getattr(player, "current_continent", None)
        if not is_valid_continent(cont):
            return _no("invalid_continent", "cid_refuse_flag")
        city = city_key_for(cont)
        enc = await encargo_view(session, cont, lang)
        if not enc or enc.get("locked"):
            return _no("no_encargo", "cid_encargo_locked")
        key = str(enc["key"])
        state = await _my_encargo_state(session, player, key, lang)
        if not state.get("can_accept"):
            return {"ok": False, "reason": state.get("reason") or "busy",
                    "line": state.get("reason_line") or i18n_t(lang, "cid_refuse_busy")}

        from database.models import PlayerStorylet
        now = _utcnow()
        row = PlayerStorylet(
            player_id=int(player.telegram_id),
            storylet_key=key,
            status="accepted",
            progress=0,
            # A quest LEMBRA de onde nasceu (convenção MV-5). `city` é campo
            # ADITIVO do context JSONB — nunca sai daqui para uma coluna
            # `continent_key` de ninguém.
            context={"continent": str(cont), "city": city, "source": "encargo"},
            offered_at=now,
            accepted_at=now,
            expires_at=now + timedelta(hours=ENCARGO_EXPIRES_HOURS),
        )
        # Savepoint PRÓPRIO: uma corrida perdida (duplo-tap) desfaz só isto e
        # nunca envenena a transação do caller — o contrato do MV-5.
        async with session.begin_nested():
            session.add(row)
            await session.flush()

        return {
            "ok": True,
            "city": city,
            "city_name": city_name(city, lang),
            "encargo": enc,
            "row_id": int(row.id),
            "expires_hours": int(ENCARGO_EXPIRES_HOURS),
            "line": i18n_t(lang, "cid_encargo_accepted",
                           city=city_name(city, lang), name=enc["name"]),
        }
    except Exception:
        logger.exception("accept_encargo failed (player=%s)",
                         getattr(player, "telegram_id", None))
        # ⚠️ Até o erro interno tem de DIZER algo (Lei §1). Sem `line`, o mini-app
        # recebia HTTP 200 com `ok:false` — o `api()` do cliente só levanta em
        # !res.ok, portanto o `catch` nunca dispara — e o botão "Assumir o
        # encargo" ficava um clique SILENCIOSO: nada acontecia, nada era dito.
        try:
            from core.i18n import t as _t
            return {"ok": False, "reason": "internal_error",
                    "line": _t(lang, "cid_refuse_busy")}
        except Exception:
            return {"ok": False, "reason": "internal_error"}


# A reputação regional da ENTREGA não vive aqui: `storylet_engine.claim_storylet`
# já credita `REP_STORYLET_DONE` a todo storylet resolvido, lendo o continente do
# `context` da row (gated `reputacao_rival`, bônus DISCLOSED e nunca dependência
# — Lei §1). O encargo É um storylet, portanto herda esse faucet de graça. Somar
# um segundo aqui seria pagar duas vezes pela mesma entrega.


# ══════════════════════════════════════════════════════════════════════════
# O mapa — as cinco cidades no /viajar, com o UNFOLDING
# ══════════════════════════════════════════════════════════════════════════

async def city_map_overlay(session, lang: str, viewer_continent: str | None
                           ) -> dict[str, dict[str, Any]]:
    """{continent: {city_name, city_emoji, encargo_line}} para o mapa de viagem.

    As CINCO cidades aparecem SEMPRE, com nome e emoji — o unfolding controla
    **o quanto se sabe**, nunca **se existe** (Lei §1; esconder o destino
    inteiro reproduziria o `elsewhere_summary` do MV-1, o padrão a NÃO copiar).
    O que chega com atraso é o que a cidade QUER: perto, na hora; longe, o
    pedido de 6-12h atrás, com a idade dita na própria linha.

    Flag OFF → {} sem UMA query ⇒ nenhuma key nova no payload (byte-idêntico).
    """
    out: dict[str, dict[str, Any]] = {}
    try:
        if not cidades_on():
            return out
        from core.i18n import t as i18n_t
        from core.region_state_engine import rumor_delay_hours
        now = _utcnow()
        for cont in CONTINENT_KEYS:
            city = city_key_for(cont)
            if not city:
                continue
            entry: dict[str, Any] = {
                "city_key": city,
                "city_emoji": city_emoji(city),
                "city_name": city_name(city, lang),
            }
            delay = float(rumor_delay_hours(viewer_continent, cont))
            enc = await encargo_view(session, cont, lang, now=now, delay_hours=delay)
            if enc and enc.get("locked"):
                entry["city_encargo_line"] = enc.get("line") or ""
            elif enc:
                entry["city_encargo_line"] = i18n_t(
                    lang, "cid_travel_wants", icon=enc["icon"], name=enc["name"])
                if delay > 0:
                    entry["city_encargo_line"] += " " + i18n_t(
                        lang, "cid_travel_stale", h=int(delay))
            out[cont] = entry
        return out
    except Exception:
        logger.exception("city_map_overlay failed")
        return {}


# ══════════════════════════════════════════════════════════════════════════
# O batimento — a Crônica anuncia quando a cidade muda de pedido
# ══════════════════════════════════════════════════════════════════════════

async def pulse_cities(session, now: datetime | None = None) -> dict[str, Any] | None:
    """Um passo do World Pulse: para cada cidade, se o encargo DESTE batimento
    é diferente do batimento anterior, escreve UMA linha na Crônica.

    Sem estado: o encargo é derivado, portanto o "anterior" é literalmente
    `encargo_key_for(now - 1 tick)`. Zero row de controlo, zero sweep.

    ⚠️ O `{city}` viaja em `params`, NUNCA dentro de `text_key` — `core.i18n.t`
    engole o KeyError e devolve o TEMPLATE CRU, chaveta na cara do jogador
    (a nota do MV-8 em `region_state_engine.py:106-110`). O ramo que resolve
    `{city}`/`{encargo}` por leitor vive em
    `world_pulse_engine._chronicle_localized_names`.

    Flag OFF → None sem UMA query. Nunca levanta (o caller é o pulse).
    """
    try:
        if not cidades_on():
            return None
        from core.world_pulse_engine import emit_chronicle, WORLD_PULSE_INTERVAL_HOURS
        from database.models import WorldChronicle
        now = now or _utcnow()
        # ⚠️ O "anterior" é o BATIMENTO DO MUNDO atrás (6h), não o tick da
        # cidade (24h). Comparar contra `now - CITY_TICK_HOURS` daria "mudou"
        # em TODOS os quatro pulses do dia — quatro linhas iguais na Crônica
        # por cidade, todos os dias. Com o intervalo do pulse, três dos quatro
        # batimentos são no-op e só o que vira o dia escreve.
        prev_at = now - timedelta(hours=float(WORLD_PULSE_INTERVAL_HOURS))
        changed = 0
        for cont in CONTINENT_KEYS:
            city = city_key_for(cont)
            if not city:
                continue
            st, events = await _world_ctx(session, cont)
            cur = encargo_key_for(cont, now=now, region_state=st, events=events)
            prev = encargo_key_for(cont, now=prev_at, region_state=st, events=events)
            # ⚠️ `prev` usa o estado de AGORA, não o de há 6h — não há histórico
            # de estado para ler. Consequência ACEITE e declarada: uma mudança
            # de pedido causada só pelo ESTADO (o continente virou `sitiada` no
            # mesmo batimento e a cidade passou a pedir defesa) não é detetada
            # aqui, porque ambos os lados da comparação já veem `sitiada`. Essa
            # notícia não se perde: o MV-3 escreve a SUA linha de mudança de
            # estado na mesma Crônica (`rst_*`), e é essa que conta a história
            # ("o continente foi sitiado"), com o pedido novo visível na praça e
            # no /viajar. Duplicar aqui seria anunciar a mesma coisa duas vezes.
            if not cur or cur == prev:
                continue
            # ⚠️ IDEMPOTÊNCIA por tick. O job do pulse tem `coalesce=True` +
            # `misfire_grace_time=3600`, e o trigger de intervalo re-agenda a
            # partir do BOOT — logo um deploy pode fazer o batimento disparar
            # fora da grelha e repetir a comparação. Sem esta guarda, a mesma
            # notícia entrava duas vezes na Crônica ("Correu voz de X" a dobrar),
            # e a Crônica nunca é podada. Uma linha por (cidade, encargo, tick):
            # se já existe uma para este encargo dentro da janela do tick, não
            # se escreve outra. O molde é o `_is_first_done_on_server` do MV-5.
            since = now - timedelta(hours=CITY_TICK_HOURS)
            dup = (await session.execute(
                select(WorldChronicle.id).where(
                    WorldChronicle.event_type == "cid_encargo",
                    WorldChronicle.continent_key == cont,
                    WorldChronicle.ts >= since,
                    WorldChronicle.params["encargo_key"].astext == cur,
                ).limit(1)
            )).scalar_one_or_none()
            if dup is not None:
                continue
            await emit_chronicle(
                session,
                event_type="cid_encargo",
                text_key="cid_chron_encargo",
                params={"city_key": city, "encargo_key": cur},
                continent_key=cont,   # o CONTINENTE, sempre — nunca a cidade
                importance=1,
                now=now,
            )
            changed += 1
        return {"cities": len(CITY_KEYS), "changed": changed}
    except Exception:
        logger.exception("pulse_cities failed")
        return None
