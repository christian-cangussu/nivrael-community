"""MV-3 — Mundo Vivo v2: Estados Regionais (os Registros Celestiais passam a SER o mundo).

UM helper para as DUAS superfícies (chat + mini-app): cada continente ganha um
``state`` persistente (🌾 prospera · ⚡ tensa · 🏚️ sitiada · 🏮 festival) com
overrides MECÂNICOS que o jogador sente — preços do mercado local, risco de
explore, densidade de qi no cultivo. Eventos do MV-2 (Tiandao) são a CAUSA;
o estado é o EFEITO persistente. Tudo atrás da flag per-world
``estados_regionais`` (OFF por defeito → main byte-idêntico; ver
DEFAULT_WORLD_FEATURES em database/db.py).

Regras (padrão tiandao_engine — tudo fail-safe, nada aqui pode quebrar nada):
- Flag OFF → ``estados_on()`` False → TODA função é no-op sem UMA query.
- Transições SÓ em ``sync_region_states`` (pega carona no World Pulse de 6h,
  logo APÓS o director_pulse — o sweep do decay vive no MESMO passo, lição
  sect_war). As 5 rows são seedadas lazy aqui (upsert idempotente — sem seed
  runner novo); row ausente lê-se SEMPRE como 'prospera'.
- Ordem de severidade por pulse: sitiada (maré ignorada, janela de 48h do
  próprio row expirado — a MESMA janela derivada do MV-2) > tensa (maré ATIVA)
  > festival (meteoro colhido ≥N ou maré contida, 48h) > decay (sitiada→tensa→
  prospera, um degrau por pulse) > prospera.
- A penalidade de travel do MV-2 é ABSORVIDA: com estados ON, a estrada fechada
  lê ``state == 'sitiada'`` (``road_penalized_continents`` — UMA verdade); com
  estados OFF e tiandao ON, o derivado do MV-2 continua a valer (fallback —
  as 2 flags são independentes).
- Economia (Lei §13 — nunca loop fechado): o override de preço é um KNOB no
  COMPRADOR (paga total×mult onde ele ESTÁ); o vendedor recebe SEMPRE
  base−taxa (nunca é punido por um estado que não controla). Sobretaxa =
  sink; desconto = faucet. Nunca tocar qi_cap/fórmula do qi: o override de
  cultivo multiplica APENAS o ganho de CB do tick (padrão event_cb_mult).
- Chronicle em TODA transição de estado ({continent} resolve no render).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from core.continent_engine import CONTINENT_KEYS, CONTINENT_META, is_valid_continent
from core.dungeon_regions import continent_emoji, player_continent
from database.models import RegionState, WorldEvent

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Tuning (engine, não DB — launch-server-ready; env-overridable para ops,
# padrão TIANDAO_*). Lei §3: 4 estados com nuance > 10 estados decorativos.
# ══════════════════════════════════════════════════════════════════════════

STATE_PROSPERA = "prospera"
STATE_TENSA = "tensa"
STATE_SITIADA = "sitiada"
STATE_FESTIVAL = "festival"
# MV-8 — a 🚩 BANDEIRA: o "ocupada pela Seita X" que o MV-3 deixou por fazer.
# O gatilho NÃO é `claim_node` (que all-time nunca tocou Mòyǔ nem Qiánhé) e NÃO
# é "a casa mais forte" (`world_sects.strength` é um int GLOBAL congelado e
# idêntico nas 2 DBs — daria um rótulo estático). O gatilho é a MARCHA do MV-8:
# os NPCs querem coisas → eles se mudam → o mapa muda de cor.
STATE_OCUPADA = "ocupada"

VALID_STATES = (STATE_PROSPERA, STATE_TENSA, STATE_SITIADA, STATE_FESTIVAL,
                STATE_OCUPADA)

# Janela da sitiada = a MESMA janela derivada do MV-2 (o estado absorve a
# penalidade — uma verdade). Festival dura 48h a partir da entrada.
SITIADA_HOURS = float(os.getenv("RST_SITIADA_HOURS", os.getenv("TIANDAO_TIDE_PENALTY_HOURS", "48")))
FESTIVAL_HOURS = float(os.getenv("RST_FESTIVAL_HOURS", "48"))
# Quanto uma ocupação DURA depois de a presença cair abaixo do gatilho — a
# bandeira não desce no minuto em que o último NPC vai embora. A saída é por
# TEMPO e com rescaldo: ocupada → tensa → prospera (o degrau que já existe).
OCUPADA_HOURS = float(os.getenv("RST_OCUPADA_HOURS", "72"))
# Meteoro "colhido" = progress (nº de coletas) ≥ N quando o evento fecha.
FESTIVAL_METEOR_PROGRESS = int(os.getenv("RST_FESTIVAL_METEOR_PROGRESS", "5"))

# Overrides por estado (knobs, nunca estoque — Lei §13).
# ⚠️ Desconto NUNCA pode exceder a taxa do mercado (5%): comprador pagando
# MENOS do que o vendedor recebe = impressora de pedras via compra-revenda
# (achado do review MV-3). O festival fica em −5% (a assinatura dele é o qi
# +5%); e core/economy.py tem o clamp estrutural buyer_pays ≥ seller_receive
# — nenhum valor de env consegue reintroduzir a cunhagem.
PRICE_MULTS: dict[str, float] = {
    STATE_PROSPERA: float(os.getenv("RST_PRICE_PROSPERA", "0.95")),
    STATE_TENSA: 1.0,
    STATE_SITIADA: float(os.getenv("RST_PRICE_SITIADA", "1.10")),
    STATE_FESTIVAL: float(os.getenv("RST_PRICE_FESTIVAL", "0.95")),
    # A Bandeira cobra a sua taxa: sobretaxa = SINK (nunca desconto — um
    # desconto aqui seria faucet de graça). O `market_note` já anuncia o
    # número sozinho, de graça (Lei §1).
    STATE_OCUPADA: float(os.getenv("RST_PRICE_OCUPADA", "1.10")),
}
EXPLORE_RISK_BUMPS: dict[str, int] = {
    STATE_TENSA: 1,
    STATE_SITIADA: 1,
    STATE_OCUPADA: 1,   # patrulhas estrangeiras nas estradas
}
QI_TICK_MULTS: dict[str, float] = {
    STATE_FESTIVAL: float(os.getenv("RST_QI_TICK_FESTIVAL", "1.05")),
}

NEUTRAL_OVERRIDES: dict[str, Any] = {"price_mult": 1.0, "explore_risk_bump": 0, "qi_tick_mult": 1.0}

# Apresentação (name/desc server-resolved nos locales de CHAT, padrão Chronicle).
# ⚠️ `name_key`/`desc_key` são resolvidos por `t()` **SEM kwargs** (ver
# state_views/local_state_view). Logo NENHUMA destas strings pode conter um
# placeholder: um `{sect}` no nome da ocupada vazaria a chaveta na tela do
# jogador. O nome do ocupante viaja como campo ADITIVO do dict projetado.
STATE_META: dict[str, dict[str, str]] = {
    STATE_PROSPERA: {"emoji": "🌾", "name_key": "rst_prospera_name", "desc_key": "rst_prospera_desc"},
    STATE_TENSA:    {"emoji": "⚡", "name_key": "rst_tensa_name", "desc_key": "rst_tensa_desc"},
    STATE_SITIADA:  {"emoji": "🏚️", "name_key": "rst_sitiada_name", "desc_key": "rst_sitiada_desc"},
    STATE_FESTIVAL: {"emoji": "🏮", "name_key": "rst_festival_name", "desc_key": "rst_festival_desc"},
    STATE_OCUPADA:  {"emoji": "🚩", "name_key": "rst_ocupada_name", "desc_key": "rst_ocupada_desc"},
}

_CHRON_KEYS: dict[str, tuple[str, str, int]] = {
    # state -> (event_type, text_key, importance)
    STATE_TENSA:    ("rst_tensa", "rst_chron_tensa", 2),
    STATE_SITIADA:  ("rst_sitiada", "rst_chron_sitiada", 2),
    STATE_FESTIVAL: ("rst_festival", "rst_chron_festival", 2),
    STATE_PROSPERA: ("rst_prospera", "rst_chron_prospera", 1),
    # A ocupação é a maior notícia que o mapa produz — e é a ÚNICA transição
    # cuja linha nomeia uma casa, logo o `sect_id` do ocupante TEM de ser
    # passado ao emit (é ele que resolve `{sect}` no render).
    STATE_OCUPADA:  ("rst_ocupada", "rst_chron_ocupada", 3),
}


def estados_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão director_on). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("estados_regionais", world_key))
    except Exception:
        return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_state(state: str | None) -> str:
    return state if state in VALID_STATES else STATE_PROSPERA


def state_emoji(state: str | None) -> str:
    return str((STATE_META.get(normalize_state(state)) or {}).get("emoji", "🌾"))


def overrides_for_state(state: str | None) -> dict[str, Any]:
    """Os 3 overrides de UM estado (puro — a tabela é a verdade)."""
    s = normalize_state(state)
    return {
        "price_mult": float(PRICE_MULTS.get(s, 1.0)),
        "explore_risk_bump": int(EXPLORE_RISK_BUMPS.get(s, 0)),
        "qi_tick_mult": float(QI_TICK_MULTS.get(s, 1.0)),
    }


def rumor_delay_hours(current_continent: str | None, event_continent: str | None) -> float:
    """MV-3 §3 — latência geográfica do rumor (padrão DF): a ordem canónica de
    CONTINENT_KEYS é a proxy de distância. Adjacente = 1 pulse (6h), longe =
    2 pulses (12h). Distância 0 (mesmo continente) = 0h — quem ESTÁ no lugar
    vê na hora (mas a praça local já usa local_event_lines). Puro, sem I/O."""
    try:
        a = CONTINENT_KEYS.index(current_continent) if current_continent in CONTINENT_KEYS else 0
        b = CONTINENT_KEYS.index(event_continent) if event_continent in CONTINENT_KEYS else 0
        dist = abs(a - b)
        if dist <= 0:
            return 0.0
        return float(min(dist, 2) * 6)
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════════════════════════
# Reads — estado por continente projetado para as superfícies
# ══════════════════════════════════════════════════════════════════════════

async def get_states_map(session) -> dict[str, str]:
    """{continent: state} para os 5 continentes (row ausente → 'prospera').
    Flag OFF → tudo 'prospera' SEM query. Defensivo — nunca levanta."""
    base = {key: STATE_PROSPERA for key in CONTINENT_KEYS}
    if not estados_on():
        return base
    try:
        rows = (await session.execute(select(RegionState))).scalars().all()
        for row in rows:
            if row.continent_key in base:
                base[row.continent_key] = normalize_state(row.state)
        return base
    except Exception:
        logger.exception("get_states_map failed")
        return base


async def region_state(session, continent: str | None) -> str:
    """O estado de UM continente (flag OFF / erro / desconhecido → 'prospera')."""
    if not estados_on() or not is_valid_continent(continent):
        return STATE_PROSPERA
    try:
        row = (await session.execute(
            select(RegionState).where(RegionState.continent_key == continent)
        )).scalar_one_or_none()
        return normalize_state(row.state if row else None)
    except Exception:
        logger.exception("region_state failed continent=%s", continent)
        return STATE_PROSPERA


async def region_overrides(session, continent: str | None) -> dict[str, Any]:
    """O helper ÚNICO dos overrides: {price_mult, explore_risk_bump,
    qi_tick_mult} do continente. Flag OFF → neutro SEM query."""
    if not estados_on():
        return dict(NEUTRAL_OVERRIDES)
    return overrides_for_state(await region_state(session, continent))


async def market_price_mult(session, player) -> float:
    """Multiplicador de preço do mercado ONDE O COMPRADOR ESTÁ (o 'mercado
    local' é o lugar onde você negocia). Fail-safe 1.0 — a compra nunca
    quebra por causa do estado."""
    try:
        if player is None or not estados_on():
            return 1.0
        ov = await region_overrides(session, player_continent(player))
        return float(ov.get("price_mult", 1.0) or 1.0)
    except Exception:
        logger.exception("market_price_mult failed")
        return 1.0


async def explore_risk_bump(session, player) -> int:
    """+N degraus de dificuldade no explore do continente atual (tensa/
    sitiada). Fail-safe 0."""
    try:
        if player is None or not estados_on():
            return 0
        ov = await region_overrides(session, player_continent(player))
        return int(ov.get("explore_risk_bump", 0) or 0)
    except Exception:
        logger.exception("explore_risk_bump failed")
        return 0


async def qi_tick_mult_map(session) -> dict[str, float]:
    """{continent: qi_tick_mult} SÓ dos continentes ≠ 1.0 — o prefetch do
    cultivation_tick (1 query por mundo por tick, nunca 1 por jogador).
    Flag OFF → {} sem query."""
    if not estados_on():
        return {}
    try:
        states = await get_states_map(session)
        out: dict[str, float] = {}
        for cont, st in states.items():
            mult = float(QI_TICK_MULTS.get(st, 1.0))
            if mult != 1.0:
                out[cont] = mult
        return out
    except Exception:
        logger.exception("qi_tick_mult_map failed")
        return {}


async def road_penalized_continents(session) -> set[str]:
    """A verdade ÚNICA da 'estrada fechada' (travel +50%): com estados ON, o
    estado ABSORVE a penalidade derivada do MV-2 (sitiada = estrada cara);
    com estados OFF, o derivado do MV-2 continua a valer (as 2 flags são
    independentes). Fail-safe → set vazio."""
    try:
        if estados_on():
            states = await get_states_map(session)
            return {cont for cont, st in states.items() if st == STATE_SITIADA}
        from core.tiandao_engine import travel_penalized_continents
        return await travel_penalized_continents(session)
    except Exception:
        logger.exception("road_penalized_continents failed")
        return set()


def _occupant_view(payload: Any, lang: str) -> dict[str, str] | None:
    """A linha da 🚩 Bandeira — campo **ADITIVO** do dict projetado, resolvido
    com kwargs próprios.

    ⚠️ É por isto que o `{sect}` NÃO pode viver no `name_key`/`desc_key`: as
    duas projeções abaixo chamam `t()` **sem kwargs**, e `t()` sem o kwarg
    devolve o TEMPLATE CRU — o jogador leria `{sect}` na cara. Aqui a key é
    chamada COM o nome já resolvido. Ausente → None ⇒ key ausente no payload.
    """
    try:
        jh = ((payload or {}).get("jianghu") or {}) if isinstance(payload, dict) else {}
        sect_id = jh.get("sect_id")
        if not sect_id:
            return None
        from core.i18n import t as i18n_t
        from core.world_sects_engine import WORLD_SECT_META, is_valid_sect
        if not is_valid_sect(sect_id):
            return None
        meta = WORLD_SECT_META[sect_id]
        name = i18n_t(lang, meta["name_key"])
        return {
            "sect_id": str(sect_id),
            "sect_emoji": str(meta.get("emoji", "🏯")),
            "sect_name": name,
            "line": i18n_t(lang, "rst_ocupada_by", sect=name),
        }
    except Exception:
        logger.debug("_occupant_view failed", exc_info=True)
        return None


async def state_views(session, lang: str) -> dict[str, dict[str, Any]]:
    """{continent: {state, emoji, name, desc, line, occupant?}} server-resolved
    para as superfícies (/viajar, trv_d_, mapa, mercado). Flag OFF → {} sem
    query."""
    if not estados_on():
        return {}
    try:
        from core.i18n import t as i18n_t
        rows = (await session.execute(select(RegionState))).scalars().all()
        by_key = {r.continent_key: r for r in rows}
        out: dict[str, dict[str, Any]] = {}
        for cont in CONTINENT_KEYS:
            row = by_key.get(cont)
            st = normalize_state(row.state if row else None)
            meta = STATE_META.get(st) or STATE_META[STATE_PROSPERA]
            name = i18n_t(lang, meta["name_key"])
            desc = i18n_t(lang, meta["desc_key"])
            occupant = _occupant_view(row.payload if row else None, lang) if st == STATE_OCUPADA else None
            out[cont] = {
                "state": st,
                "emoji": meta["emoji"],
                "name": name,
                "desc": desc,
                "line": f"{meta['emoji']} {name} — {desc}",
                **({"occupant": occupant} if occupant else {}),
            }
        return out
    except Exception:
        logger.exception("state_views failed")
        return {}


async def local_state_view(session, continent: str | None, lang: str) -> dict[str, str] | None:
    """MV-4 §0 (dívida do MV-3, TODO #1 de region_states.md): a linha do estado
    LOCAL para a praça — {emoji, text} de UM continente, server-resolved (o
    padrão world_event_local). Mostra SEMPRE que a flag está ON (a 'prospera'
    também é clima — o /viajar já mostra a linha do continente atual). Flag
    OFF / erro → None SEM sujar a superfície."""
    try:
        if not estados_on() or not is_valid_continent(continent):
            return None
        from core.i18n import t as i18n_t
        row = (await session.execute(
            select(RegionState).where(RegionState.continent_key == continent)
        )).scalar_one_or_none()
        st = normalize_state(row.state if row else None)
        meta = STATE_META.get(st) or STATE_META[STATE_PROSPERA]
        name = i18n_t(lang, meta["name_key"])
        desc = i18n_t(lang, meta["desc_key"])
        occupant = _occupant_view(row.payload if row else None, lang) if st == STATE_OCUPADA else None
        return {"emoji": meta["emoji"], "text": f"{name} — {desc}",
                **({"occupant_line": occupant["line"]} if occupant else {})}
    except Exception:
        logger.exception("local_state_view failed continent=%s", continent)
        return None


async def market_note(session, player, lang: str) -> str | None:
    """A linha de disclosure do mercado (Lei §1 — nunca um preço mudo): dita
    quando o multiplicador local ≠ 1.0. None com flag OFF/estado neutro."""
    try:
        if player is None or not estados_on():
            return None
        cont = player_continent(player)
        st = await region_state(session, cont)
        mult = float(PRICE_MULTS.get(st, 1.0))
        if mult == 1.0:
            return None
        from core.i18n import t as i18n_t
        pct = abs(round((mult - 1.0) * 100))
        key = "rst_market_note_up" if mult > 1.0 else "rst_market_note_down"
        return i18n_t(lang, key, emoji=state_emoji(st), pct=pct)
    except Exception:
        logger.exception("market_note failed")
        return None


# ══════════════════════════════════════════════════════════════════════════
# O sync — transições SÓ aqui (World Pulse 6h, logo após o director_pulse)
# ══════════════════════════════════════════════════════════════════════════

async def _transition_inputs(session, now: datetime) -> dict[str, dict[str, bool]]:
    """Lê os eventos do MV-2 que CAUSAM estados, numa query: maré ativa ·
    maré ignorada (janela derivada de 48h do expires_at — a MESMA do MV-2) ·
    festival recente (maré contida OU meteoro colhido ≥N, via resolved_at)."""
    from core.tiandao_engine import EVENT_BEAST_TIDE, EVENT_METEOR
    cut_sitiada = now - timedelta(hours=SITIADA_HOURS)
    cut_festival = now - timedelta(hours=FESTIVAL_HOURS)
    cut = min(cut_sitiada, cut_festival)
    rows = (await session.execute(
        select(WorldEvent).where(
            (WorldEvent.state == "active")
            | (WorldEvent.resolved_at > cut)
            | ((WorldEvent.state == "expired") & (WorldEvent.expires_at > cut_sitiada))
        )
    )).scalars().all()
    inputs: dict[str, dict[str, bool]] = {
        key: {"tide_active": False, "tide_ignored": False, "festival": False}
        for key in CONTINENT_KEYS
    }
    for ev in rows:
        slot = inputs.get(ev.continent_key)
        if slot is None:
            continue
        exp = _aware(ev.expires_at)
        res = _aware(ev.resolved_at)
        if ev.event_type == EVENT_BEAST_TIDE:
            if ev.state == "active" and (exp is None or exp > now):
                slot["tide_active"] = True
            elif ev.state == "expired" and exp and exp > cut_sitiada:
                slot["tide_ignored"] = True
            elif ev.state == "resolved" and res and res > cut_festival:
                slot["festival"] = True  # maré contida → a cidade celebra
        elif ev.event_type == EVENT_METEOR:
            if (ev.state != "active" and res and res > cut_festival
                    and int(ev.progress or 0) >= FESTIVAL_METEOR_PROGRESS):
                slot["festival"] = True  # meteoro colhido ≥N vezes
    return inputs


def _next_state(current: str, since: datetime | None, inp: dict[str, Any], now: datetime) -> str:
    """A máquina de estados de UM continente para UM pulse (pura, testável).

    Severidade assada: **sitiada > ocupada > tensa > festival > decay** (um
    degrau por pulse).

    ⚠️ Esta função termina num catch-all `return STATE_PROSPERA`. Um estado
    novo SEM ramo próprio aqui viveria exatamente UM pulse (6h) e voltaria a
    'prospera' sozinho — o defeito que mataria a Bandeira em silêncio. Por isso
    a ocupada tem DOIS ramos: o de ENTRADA (a presença manda) e o de SAÍDA (a
    janela `OCUPADA_HOURS` + rescaldo em 'tensa').

    Com `jianghu` OFF, `inp["occupied_by"]` é sempre None e o resultado é
    byte-idêntico ao de antes do MV-8.
    """
    cur = normalize_state(current)
    occupied_by = inp.get("occupied_by")
    if inp.get("tide_ignored"):
        return STATE_SITIADA
    if inp.get("tide_active") and cur == STATE_SITIADA:
        # sitiada NÃO é rebaixada por uma maré nova — o pior estado persiste
        # até a janela da sitiada fechar (aí o decay desce para tensa).
        return STATE_SITIADA
    if occupied_by:
        return STATE_OCUPADA
    if inp.get("tide_active"):
        return STATE_TENSA
    if inp.get("festival"):
        return STATE_FESTIVAL
    if cur == STATE_SITIADA:
        return STATE_TENSA  # decay: sitiada → tensa → prospera (1 degrau/pulse)
    if cur == STATE_OCUPADA:
        aware_since = _aware(since)
        if aware_since and now - aware_since < timedelta(hours=OCUPADA_HOURS):
            return STATE_OCUPADA
        return STATE_TENSA  # a bandeira desce, mas a cidade não esquece
    if cur == STATE_FESTIVAL:
        aware_since = _aware(since)
        if aware_since and now - aware_since < timedelta(hours=FESTIVAL_HOURS):
            return STATE_FESTIVAL
        return STATE_PROSPERA
    return STATE_PROSPERA


async def sync_region_states(session) -> dict[str, Any] | None:
    """O passo do MV-3 no World Pulse de 6h (logo após o director_pulse):
    seeda lazy as 5 rows (upsert idempotente), aplica a máquina de estados e
    faz o decay no MESMO passo (lição sect_war). Chronicle em TODA transição.
    Flag OFF → None sem UMA query (OFF-identity). Faz o próprio commit;
    qualquer falha é engolida e logada (o pulse nunca cai)."""
    if not estados_on():
        return None
    now = _utcnow()
    summary: dict[str, Any] = {"changed": 0, "states": {}}
    try:
        rows = (await session.execute(
            select(RegionState).order_by(RegionState.continent_key).with_for_update()
        )).scalars().all()
        by_key = {r.continent_key: r for r in rows}
        for key in CONTINENT_KEYS:
            if key not in by_key:
                row = RegionState(continent_key=key, state=STATE_PROSPERA, since=now, payload={})
                session.add(row)
                by_key[key] = row
        await session.flush()

        inputs = await _transition_inputs(session, now)
        # MV-8 — a 🚩 Bandeira. Leitor GATED do irmão (`jianghu` OFF → {} sem
        # UMA query ⇒ `occupied_by` nunca existe ⇒ este sync fica byte-idêntico
        # ao de antes). A presença é DERIVADA da população, nunca armazenada.
        occupation: dict[str, dict[str, Any]] = {}
        try:
            from core.jianghu_engine import occupation_map
            occupation = await occupation_map(session)
        except Exception:
            logger.debug("sync_region_states: occupation map failed", exc_info=True)
        for key in CONTINENT_KEYS:
            row = by_key[key]
            cur = normalize_state(row.state)
            inp = dict(inputs.get(key) or {})
            occ = occupation.get(key)
            inp["occupied_by"] = (occ or {}).get("sect_id")
            nxt = _next_state(cur, row.since, inp, now)
            summary["states"][key] = nxt
            # A bandeira pode TROCAR DE DONO sem o estado mudar (outra casa
            # supera a presença). Sem este ramo o payload continuaria a nomear
            # o ocupante antigo para sempre — o `cur == nxt: continue` abaixo
            # nunca reavaliaria a linha.
            if nxt == cur == STATE_OCUPADA:
                _pl = dict(row.payload or {})
                prev_occ = (_pl.get("jianghu") or {}).get("sect_id")
                # ⚠️ A JANELA DE GRAÇA conta a partir da última vez que a
                # presença FOI VISTA, não de quando a bandeira subiu. Sem este
                # refresh, `row.since` ficava congelado na entrada: uma
                # ocupação que durasse mais de OCUPADA_HOURS queimava a graça
                # inteira com os ocupantes ainda lá, e no primeiro pulse em que
                # um NPC saísse a bandeira caía NA HORA — o oposto exato do que
                # a docstring promete ("a bandeira não desce no minuto em que o
                # último NPC vai embora"), e a bandeira passava a piscar de 6
                # em 6 horas, com uma linha de Crônica a cada piscada.
                if occ:
                    row.since = now
                if occ and prev_occ != occ.get("sect_id"):
                    _pl["jianghu"] = {"sect_id": occ["sect_id"],
                                      "presence": int(occ["presence"]),
                                      "since": now.isoformat()}
                    row.payload = _pl
                    summary["changed"] += 1
                    try:
                        etype, text_key, importance = _CHRON_KEYS[STATE_OCUPADA]
                        from core.world_pulse_engine import emit_chronicle
                        await emit_chronicle(
                            session, event_type=etype, text_key=text_key,
                            continent_key=key, sect_id=occ["sect_id"],
                            importance=importance, now=now,
                        )
                    except Exception:
                        logger.exception("region state chronicle failed continent=%s", key)
                continue
            if nxt == cur:
                continue
            row.state = nxt
            row.since = now
            # MV-7 fix (armadilha #1 do recon): MERGE em vez de substituir —
            # o payload agora também carrega o market_report do MV-7 (e o que
            # mais vier); substituir o dict apagaria tudo a cada transição.
            # Continua um dict NOVO → change tracking vê.
            _pl = dict(row.payload or {})
            _pl["prev"] = cur
            if nxt == STATE_OCUPADA and occ:
                _pl["jianghu"] = {"sect_id": occ["sect_id"],
                                  "presence": int(occ["presence"]),
                                  "since": now.isoformat()}
            elif nxt != STATE_OCUPADA:
                _pl.pop("jianghu", None)   # a bandeira desceu: nada de ocupante fantasma
            row.payload = _pl
            summary["changed"] += 1
            try:
                # ⚠️ `.get()`, nunca `_CHRON_KEYS[nxt]`: o index direto vive
                # dentro de um `except Exception` que só loga, então um estado
                # sem entrada aqui seria a única transição MUDA do jogo — e
                # justamente a mais importante da onda.
                spec = _CHRON_KEYS.get(nxt)
                if spec is None:
                    logger.warning("region state sem entrada em _CHRON_KEYS: %s", nxt)
                else:
                    etype, text_key, importance = spec
                    from core.world_pulse_engine import emit_chronicle
                    await emit_chronicle(
                        session, event_type=etype, text_key=text_key,
                        continent_key=key,
                        # A linha da ocupada é a única que nomeia uma casa.
                        sect_id=(occ or {}).get("sect_id") if nxt == STATE_OCUPADA else None,
                        importance=importance, now=now,
                    )
            except Exception:
                logger.exception("region state chronicle failed continent=%s", key)
        await session.commit()
        return summary
    except Exception:
        logger.exception("sync_region_states failed")
        try:
            await session.rollback()
        except Exception:
            pass
        return None
