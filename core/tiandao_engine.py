"""MV-2 — Mundo Vivo v2: Tiandao Director 天道 (o Céu faz coisas ACONTECEREM em lugares).

UM helper para as DUAS superfícies (chat + mini-app): o Director pega carona no
World Pulse de 6h (core/scheduler.py:world_pulse_tick) e gera eventos celestiais
com LOCAL + TIMER + RESOLUÇÃO + consequência-se-ignorado — tudo atrás da flag
per-world ``tiandao_director`` (OFF por defeito → main byte-idêntico; ver
DEFAULT_WORLD_FEATURES em database/db.py).

Regras (padrão dungeon_regions — tudo fail-safe, nada aqui pode quebrar combate):
- Flag OFF → ``director_on()`` False → TODA função é no-op sem UMA query.
- Nunca 2 eventos ativos ao mesmo tempo (mundo pequeno — escassez é drama).
- 🌊 Maré de Bestas (48h): goal = N vitórias PvE de QUALQUER jogador NO
  continente (``record_pve_victory`` — hookado nos choke points PvE). Contida →
  recompensa 1x por contribuinte (stones + material nativo do MV-1) + Chronicle;
  ignorada → estrada fechada: travel de/para o continente custa +50% por 48h
  (estado DERIVADO do próprio row expirado — sem coluna nova, sem job novo).
- ☄️ Meteoro Celestial (72h, qianhe/yanshan/fenghuo): POI de colheita — "minerar
  o céu" (cooldown 6h/jogador em ``payload["miners"]``, custo pequeno de qi)
  dá 1-2 materiais nativos; expira sozinho → Chronicle, sem punição.
- Resolução/expiração: sweep no MESMO pulse de 6h (lição sect_war — job dinâmico
  SEMPRE com recovery sweep); a resolução inline no goal é o caminho feliz, o
  sweep é a rede.
- Idempotência da recompensa: o flip active→resolved acontece com o row do
  evento FOR UPDATE (só UMA transação distribui) + ``notify()`` deduplica por
  (player, kind, ref_id) como rede extra.
- Ordem de locks: SEMPRE player → evento (o settle já chega com o player
  lockado; nunca lockar players DENTRO da distribuição — beta scale, ver
  _resolve_tide).
"""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from core.continent_engine import CONTINENT_META
from core.dungeon_regions import REGIONAL_BONUS_LOOT, continent_emoji, player_continent
from database.models import Player, WorldEvent

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Tuning (engine, não DB — launch-server-ready; env-overridable para ops).
# A "personalidade do Céu" fica hardcoded nesta onda (Lei §6 — knob
# `director_intensity` só se o s2 pedir).
# ══════════════════════════════════════════════════════════════════════════

DIRECTOR_SPAWN_CHANCE = float(os.getenv("TIANDAO_SPAWN_CHANCE", "0.35"))

EVENT_BEAST_TIDE = "beast_tide"
EVENT_METEOR = "meteor"

TIDE_DURATION_HOURS = float(os.getenv("TIANDAO_TIDE_HOURS", "48"))
TIDE_GOAL = int(os.getenv("TIANDAO_TIDE_GOAL", "40"))
TIDE_REWARD_STONES = int(os.getenv("TIANDAO_TIDE_REWARD_STONES", "300"))
TIDE_PENALTY_HOURS = float(os.getenv("TIANDAO_TIDE_PENALTY_HOURS", "48"))
TRAVEL_PENALTY_MULT = float(os.getenv("TIANDAO_TRAVEL_PENALTY_MULT", "1.5"))

METEOR_DURATION_HOURS = float(os.getenv("TIANDAO_METEOR_HOURS", "72"))
METEOR_COOLDOWN_SECONDS = int(os.getenv("TIANDAO_METEOR_COOLDOWN", "21600"))  # 6h
METEOR_QI_COST = int(os.getenv("TIANDAO_METEOR_QI_COST", "25"))

# A maré nunca nasce em Mòyǔ (demonic-only — a maioria não pode ir lá conter,
# e a punição de estrada seria injusta). O meteoro só cai onde o spec manda.
TIDE_CONTINENTS: tuple[str, ...] = ("linghe", "qianhe", "yanshan", "fenghuo")
METEOR_CONTINENTS: tuple[str, ...] = ("qianhe", "yanshan", "fenghuo")

# ⚠️ O Director é dono APENAS destes tipos. A tabela `world_events` é COMPARTILHADA
# (o TEC-4 pôs a Gruta do Legado nela, e o TEC-5 acordou-a por gatilho próprio), então
# TODA leitura daqui filtra por esta tupla. Sem o filtro (bug encontrado em prod no s2,
# 2026-08-04, por print do owner) acontecia isto, tudo pelo mesmo motivo:
#   · o mapa imprimia a key CRUA `legacy_cave` no chip do evento (EVENT_META não a tem
#     ⇒ `event_view` cai no fallback `ev.event_type`) e a gruta aparecia DUAS vezes no
#     mesmo card (o chip errado + o card certo do TEC-4);
#   · o rumor de outros continentes anunciava a mesma key crua;
#   · **e o pior: uma gruta aberta (TTL 72h) contava como `still_active` e BLOQUEAVA o
#     Director por até 3 dias** — nenhuma Maré, nenhum Meteoro — quando as duas flags
#     foram desenhadas INDEPENDENTES (o TEC-4 tem sweep próprio de propósito);
#   · e o sweep do Director expirava a gruta com a crônica ERRADA (a dele, não `lgc_faded`).
# Lição de 'A Volta', outra vez: enum novo em estrutura compartilhada ⇒ varrer TODO leitor.
DIRECTOR_EVENT_TYPES: tuple[str, ...] = (EVENT_BEAST_TIDE, EVENT_METEOR)

EVENT_META: dict[str, dict[str, Any]] = {
    EVENT_BEAST_TIDE: {
        "emoji": "🌊", "name_key": "wev_tide_name", "desc_key": "wev_tide_desc",
        "duration_hours": TIDE_DURATION_HOURS,
    },
    EVENT_METEOR: {
        "emoji": "☄️", "name_key": "wev_meteor_name", "desc_key": "wev_meteor_desc",
        "duration_hours": METEOR_DURATION_HOURS,
    },
}


def director_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão regionais_on). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("tiandao_director", world_key))
    except Exception:
        return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def event_emoji(event_type: str | None) -> str:
    return str((EVENT_META.get(event_type or "") or {}).get("emoji", "🌀"))


def _fmt_time_left(ms: int) -> str:
    """'31h' / '45m' — o timer curto do badge/linha de chat."""
    s = max(0, int(ms / 1000))
    h = s // 3600
    if h > 0:
        return f"{h}h"
    return f"{max(1, s // 60)}m"


# ══════════════════════════════════════════════════════════════════════════
# Reads — eventos ativos projetados para as superfícies
# ══════════════════════════════════════════════════════════════════════════

async def _active_events(session, now: datetime | None = None) -> list[WorldEvent]:
    now = now or _utcnow()
    rows = (await session.execute(
        select(WorldEvent).where(
            WorldEvent.state == "active",
            WorldEvent.event_type.in_(DIRECTOR_EVENT_TYPES),
        ).order_by(WorldEvent.id)
    )).scalars().all()
    return [ev for ev in rows if not (_aware(ev.expires_at) and _aware(ev.expires_at) <= now)]


def _mine_cooldown_remaining(ev: WorldEvent, player_id: int, now: datetime | None = None) -> int:
    """Segundos restantes do cooldown 6h/jogador do meteoro (payload['miners'])."""
    try:
        raw = ((ev.payload or {}).get("miners") or {}).get(str(player_id))
        if not raw:
            return 0
        last = _aware(datetime.fromisoformat(str(raw)))
        rem = METEOR_COOLDOWN_SECONDS - ((now or _utcnow()) - last).total_seconds()
        return int(rem) if rem > 0 else 0
    except Exception:
        return 0


def event_view(ev: WorldEvent, lang: str, *, player=None, now: datetime | None = None) -> dict[str, Any]:
    """Projeção de UM evento para as superfícies. name/desc server-resolved
    (locales de chat, padrão Chronicle) — o cliente só exibe."""
    from core.i18n import t as i18n_t
    now = now or _utcnow()
    meta = EVENT_META.get(ev.event_type) or {}
    exp = _aware(ev.expires_at)
    time_left_ms = max(0, int((exp - now).total_seconds() * 1000)) if exp else 0
    cont_meta = CONTINENT_META.get(ev.continent_key) or {}
    view: dict[str, Any] = {
        "id": int(ev.id),
        "event_type": ev.event_type,
        "emoji": event_emoji(ev.event_type),
        "continent": ev.continent_key,
        "continent_emoji": continent_emoji(ev.continent_key),
        "continent_name": i18n_t(lang, cont_meta["name_key"]) if cont_meta.get("name_key") else ev.continent_key,
        # Nunca a key CRUA na cara do jogador: sem meta, o evento não é do
        # Director e não devia estar aqui — mas se chegar, mostra-se genérico.
        "name": (i18n_t(lang, meta["name_key"]) if meta.get("name_key")
                 else i18n_t(lang, "wev_unknown_name")),
        "desc": i18n_t(lang, meta.get("desc_key", "")) if meta.get("desc_key") else "",
        "time_left_ms": time_left_ms,
        "time_left_label": _fmt_time_left(time_left_ms),
        "progress": int(ev.progress or 0),
        "goal": int(ev.goal or 0),
    }
    if ev.event_type == EVENT_METEOR:
        view["qi_cost"] = METEOR_QI_COST
        if player is not None:
            rem = _mine_cooldown_remaining(ev, player.telegram_id, now)
            view["mine_cooldown_remaining_s"] = rem
            view["can_mine"] = bool(player_continent(player) == ev.continent_key and rem == 0)
    return view


async def list_active_event_views(session, *, player=None, lang: str = "pt",
                                  now: datetime | None = None) -> list[dict[str, Any]]:
    """Eventos ativos prontos para exibir (mapa v2 / chat / praça). Flag OFF →
    lista vazia SEM query. Defensivo — nunca levanta."""
    if not director_on():
        return []
    try:
        now = now or _utcnow()
        return [event_view(ev, lang, player=player, now=now)
                for ev in await _active_events(session, now)]
    except Exception:
        logger.exception("list_active_event_views failed")
        return []


async def chat_event_lines(session, lang: str, *, now: datetime | None = None,
                           views: list[dict[str, Any]] | None = None) -> list[str]:
    """As linhas do /viajar ('🌊 Maré de Bestas em ⛰️ Qiānhé — 31h restantes').
    ``views`` pré-computadas evitam a query dupla quando o caller já as tem."""
    from core.i18n import t as i18n_t
    if views is None:
        views = await list_active_event_views(session, lang=lang, now=now)
    lines: list[str] = []
    for v in views:
        line = i18n_t(lang, "wev_chat_line", event=f"{v['emoji']} {v['name']}",
                      emoji=v["continent_emoji"], name=v["continent_name"],
                      time=v["time_left_label"])
        if v["event_type"] == EVENT_BEAST_TIDE and v["goal"] > 0:
            line += i18n_t(lang, "wev_chat_progress", progress=v["progress"], goal=v["goal"])
        lines.append(line)
    return lines


async def local_event_lines(session, continent: str, lang: str,
                            *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Eventos NESTE continente para a praça (fix do review MV-2 — Lei §1: quem
    chega ao lugar tem de VER o evento e saber onde agir, mesmo sem o mapa v2).
    Texto server-resolved; a linha do meteoro aponta os 2 caminhos (mapa / o
    botão ⛏️ do /viajar)."""
    from core.i18n import t as i18n_t
    out: list[dict[str, Any]] = []
    for v in await list_active_event_views(session, lang=lang, now=now):
        if v["continent"] != continent:
            continue
        key = "wev_local_tide" if v["event_type"] == EVENT_BEAST_TIDE else "wev_local_meteor"
        text = i18n_t(lang, key, time=v["time_left_label"])
        if v["event_type"] == EVENT_BEAST_TIDE and v["goal"] > 0:
            text += i18n_t(lang, "wev_chat_progress", progress=v["progress"], goal=v["goal"])
        out.append({"emoji": v["emoji"], "text": text})
    return out


async def rumor_views(session, current_continent: str, lang: str,
                      *, now: datetime | None = None) -> list[dict[str, Any]]:
    """1 linha de rumor por evento NOUTRO continente (praça). Texto
    server-resolved.

    MV-3 — latência geográfica (padrão DF, gated ``estados_regionais``): a
    notícia VIAJA — o rumor só aparece depois de `distância × 6h` do nascimento
    do evento (adjacente = 1 pulse, longe = 2; ordem canónica de
    CONTINENT_KEYS como proxy). Quem ESTÁ no continente vê na hora
    (local_event_lines/mapa). Flag OFF → latência zero, lista de hoje."""
    from core.i18n import t as i18n_t
    if not director_on():
        return []
    try:
        now = now or _utcnow()
        out: list[dict[str, Any]] = []
        for ev in await _active_events(session, now):
            if ev.continent_key == current_continent:
                continue
            try:
                from core.region_state_engine import estados_on, rumor_delay_hours
                if estados_on():
                    delay_h = rumor_delay_hours(current_continent, ev.continent_key)
                    created = _aware(ev.created_at)
                    if delay_h > 0 and created and created > now - timedelta(hours=delay_h):
                        continue  # a notícia ainda não chegou até aqui
            except Exception:
                logger.debug("rumor latency check failed", exc_info=True)
            v = event_view(ev, lang, now=now)
            out.append({
                "emoji": v["emoji"],
                "text": i18n_t(lang, "wev_rumor", event=v["name"], emoji=v["continent_emoji"],
                               name=v["continent_name"], time=v["time_left_label"]),
            })
        return out
    except Exception:
        logger.exception("rumor_views failed")
        return []


# ══════════════════════════════════════════════════════════════════════════
# Consequência — estrada fechada (travel +50%), estado DERIVADO
# ══════════════════════════════════════════════════════════════════════════

async def travel_penalized_continents(session, now: datetime | None = None) -> set[str]:
    """Continentes sob 'estrada fechada': uma Maré de Bestas IGNORADA (state=
    expired) mantém a penalidade por TIDE_PENALTY_HOURS após expirar — derivado
    do próprio row, sem coluna/job novos. Flag OFF → set vazio sem query."""
    if not director_on():
        return set()
    try:
        now = now or _utcnow()
        cut = now - timedelta(hours=TIDE_PENALTY_HOURS)
        rows = (await session.execute(
            select(WorldEvent.continent_key).where(
                WorldEvent.event_type == EVENT_BEAST_TIDE,
                WorldEvent.state == "expired",
                WorldEvent.expires_at > cut,
            )
        )).scalars().all()
        return {c for c in rows if c}
    except Exception:
        logger.exception("travel_penalized_continents failed")
        return set()


# ══════════════════════════════════════════════════════════════════════════
# Contribuição — vitórias PvE alimentam a Maré (hookado nos choke points)
# ══════════════════════════════════════════════════════════════════════════

async def record_pve_victory(session, player, count: int = 1) -> dict[str, Any] | None:
    """Uma vitória PvE do jogador conta para a Maré de Bestas ATIVA do
    continente onde ele ESTÁ (current_continent — presença é o ponto). Gated +
    fail-safe: nunca levanta, nunca altera o combate; devolve
    {before, progress, goal, resolved, ...} quando contou, senão None.
    O row do evento é lockado FOR UPDATE (ordem player → evento)."""
    try:
        if player is None or not director_on():
            return None
        now = _utcnow()
        cont = player_continent(player)
        ev = (await session.execute(
            select(WorldEvent).where(
                WorldEvent.state == "active",
                WorldEvent.event_type == EVENT_BEAST_TIDE,
                WorldEvent.continent_key == cont,
            ).order_by(WorldEvent.id).with_for_update()
        )).scalars().first()
        if ev is None:
            return None
        exp = _aware(ev.expires_at)
        if exp and exp <= now:
            return None  # o sweep do próximo pulse trata a expiração
        n = max(1, int(count))
        before = int(ev.progress or 0)
        ev.progress = before + n
        payload = dict(ev.payload or {})
        contrib = dict(payload.get("contributors") or {})
        pid = str(player.telegram_id)
        contrib[pid] = int(contrib.get(pid, 0) or 0) + n
        payload["contributors"] = contrib
        ev.payload = payload  # dict NOVO → o change tracking do SQLAlchemy vê
        out = {
            "event_id": int(ev.id),
            "emoji": event_emoji(ev.event_type),
            "continent": cont,
            "before": before,
            "progress": int(ev.progress),
            "goal": int(ev.goal or 0),
            "resolved": False,
        }
        if int(ev.goal or 0) > 0 and int(ev.progress) >= int(ev.goal):
            await _resolve_tide(session, ev, now)
            out["resolved"] = True
        return out
    except Exception:
        logger.exception("record_pve_victory failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return None


def _tide_reward_bag(continent: str) -> dict[str, Any]:
    """Stones + 1 material nativo do MV-1 (REGIONAL_BONUS_LOOT). Ids STRING —
    a convenção dos bags (lição MV-1)."""
    base = REGIONAL_BONUS_LOOT.get(continent) or {}
    bag: dict[str, Any] = {"stones": TIDE_REWARD_STONES + int(base.get("stones", 0) or 0)}
    for key in ("ores", "herbs"):
        if isinstance(base.get(key), dict):
            bag[key] = {str(k): int(v) for k, v in base[key].items()}
    return bag


async def _resolve_tide(session, ev: WorldEvent, now: datetime) -> None:
    """Contida: flip do state + Chronicle + recompensa 1x por contribuinte.
    Distribuição única garantida pelo lock do evento (só UMA transação flipa
    active→resolved); ``notify()`` deduplica por ref_id como rede extra.

    Concorrência (honesto — review MV-2): os UPDATEs de recompensa adquirem
    locks IMPLÍCITOS nos rows dos contribuintes enquanto seguramos o lock do
    evento — um settle concorrente (que segura o próprio player e quer o
    evento) pode deadlockar com esta transação. O Postgres detecta e aborta
    UMA; o settle abortado re-tenta no próximo poll (idempotente via
    pve_settled) e a resolução re-dispara pelo goal ou pelo sweep de 6h.
    Aceite em beta scale (janela = só o instante da resolução); a alternativa
    (distribuir só no sweep) atrasaria a recompensa até 6h — pior."""
    ev.state = "resolved"
    ev.resolved_at = now
    try:
        from core.world_pulse_engine import emit_chronicle
        await emit_chronicle(
            session, event_type="wev_tide_contained", text_key="wev_chron_tide_contained",
            continent_key=ev.continent_key, importance=2, now=now,
        )
    except Exception:
        logger.exception("tide chronicle failed event=%s", ev.id)
    contributors = dict((ev.payload or {}).get("contributors") or {})
    bag = _tide_reward_bag(ev.continent_key)
    for pid_s in sorted(contributors, key=lambda x: int(x) if str(x).isdigit() else 0):
        try:
            pid = int(pid_s)
            p = (await session.execute(
                select(Player).where(Player.telegram_id == pid)
            )).scalar_one_or_none()
            if p is None:
                continue
            from handlers.dungeons import _transfer_bag_to_inventory
            await _transfer_bag_to_inventory(session, p, dict(bag))
            from core.notification_engine import notify
            await notify(
                session, pid, "world_event_reward",
                title_key="notif_wev_reward_title", body_key="notif_wev_reward_body",
                ref_id=f"wev:{ev.id}", icon="🌊", target_tab="inventory", priority=2,
            )
            # MV-6 — o continente defendido LEMBRA quem o defendeu (+rep por
            # contribuinte). Gancho aditivo gated (flag do irmão OFF → None
            # sem query); falha própria nunca derruba a distribuição.
            try:
                from core.reputation_engine import REP_TIDE_CONTAINED, add_region_rep
                await add_region_rep(
                    session, pid, ev.continent_key, REP_TIDE_CONTAINED, "tide_contained",
                    lang=(getattr(p, "language", None) or "pt").lower(),
                )
            except Exception:
                logger.debug("tide rep faucet failed pid=%s", pid_s, exc_info=True)
        except Exception:
            logger.exception("tide reward failed event=%s pid=%s", ev.id, pid_s)


# ══════════════════════════════════════════════════════════════════════════
# Ação do Meteoro — minerar o céu (o caller row-locka o PLAYER e faz commit)
# ══════════════════════════════════════════════════════════════════════════

async def mine_meteor(session, player, *, event_id: int | None = None,
                      now: datetime | None = None) -> dict[str, Any]:
    """Minerar o Meteoro Celestial: custo pequeno de qi + cooldown 6h/jogador
    (payload['miners']) → 1-2 materiais nativos. Recusas honestas por reason
    (Lei §1). Ordem de locks: player (caller) → evento (aqui)."""
    try:
        if not director_on():
            return {"ok": False, "reason": "wev_locked"}
        now = now or _utcnow()
        cont = player_continent(player)
        stmt = select(WorldEvent).where(
            WorldEvent.state == "active",
            WorldEvent.event_type == EVENT_METEOR,
        )
        if event_id is not None:
            stmt = stmt.where(WorldEvent.id == int(event_id))
        ev = (await session.execute(
            stmt.order_by(WorldEvent.id).with_for_update()
        )).scalars().first()
        if ev is None:
            return {"ok": False, "reason": "wev_no_event"}
        exp = _aware(ev.expires_at)
        if exp and exp <= now:
            return {"ok": False, "reason": "wev_no_event"}
        if ev.continent_key != cont:
            return {"ok": False, "reason": "wev_wrong_continent",
                    "continent": ev.continent_key,
                    "continent_emoji": continent_emoji(ev.continent_key)}
        rem = _mine_cooldown_remaining(ev, player.telegram_id, now)
        if rem > 0:
            return {"ok": False, "reason": "wev_cooldown", "remaining_seconds": rem}
        if float(player.qi or 0) < METEOR_QI_COST:
            return {"ok": False, "reason": "wev_no_qi", "qi_cost": METEOR_QI_COST,
                    "current_qi": int(player.qi or 0)}
        player.qi = max(0.0, float(player.qi or 0) - METEOR_QI_COST)
        hits = random.randint(1, 2)
        base = REGIONAL_BONUS_LOOT.get(cont) or {}
        loot: dict[str, Any] = {}
        for key, val in base.items():
            if isinstance(val, dict):
                loot[key] = {str(k): int(v) * hits for k, v in val.items()}
            else:
                loot[key] = int(val) * hits
        from handlers.dungeons import _transfer_bag_to_inventory
        await _transfer_bag_to_inventory(session, player, loot)
        payload = dict(ev.payload or {})
        miners = dict(payload.get("miners") or {})
        miners[str(player.telegram_id)] = now.isoformat()
        payload["miners"] = miners
        ev.payload = payload
        ev.progress = int(ev.progress or 0) + 1  # cosmético: nº de coletas
        return {"ok": True, "loot": loot, "hits": hits, "qi_cost": METEOR_QI_COST,
                "current_qi": int(player.qi or 0),
                "cooldown_seconds": METEOR_COOLDOWN_SECONDS, "continent": cont,
                "continent_emoji": continent_emoji(cont)}
    except Exception:
        logger.exception("mine_meteor failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return {"ok": False, "reason": "internal_error"}


# ══════════════════════════════════════════════════════════════════════════
# O Director — sweep + spawn no pulse de 6h (commits próprios, best-effort)
# ══════════════════════════════════════════════════════════════════════════

async def _expire_event(session, ev: WorldEvent, now: datetime) -> None:
    """Expirou sem resolução: a maré ignorada fecha a estrada (penalidade
    DERIVADA do row expirado — travel_penalized_continents); o meteoro apenas
    se dissipa. Chronicle honesta nas duas (Lei §1)."""
    ev.state = "expired"
    ev.resolved_at = now
    from core.world_pulse_engine import emit_chronicle
    if ev.event_type == EVENT_BEAST_TIDE:
        await emit_chronicle(
            session, event_type="wev_tide_ignored", text_key="wev_chron_tide_ignored",
            continent_key=ev.continent_key, importance=2, now=now,
        )
    else:
        await emit_chronicle(
            session, event_type="wev_meteor_faded", text_key="wev_chron_meteor_faded",
            continent_key=ev.continent_key, importance=1, now=now,
        )


# ── Fase A2 do Motor de Mundo Vivo (pivot 2026-08-11) ─────────────────────
# A DESGRAÇA ATRAI DESGRAÇA. O continente era escolhido às cegas
# (`random.choice`), o que fazia dos eventos do Céu ruído branco: uma região
# negligenciada não ficava progressivamente mais perigosa, e o jogador nunca
# podia LER o mapa. Com o peso pelo estado, o abandono tem consequência visível.
#
# ⚠️ Com `estados_regionais` OFF o mapa vem todo 'prospera' (ZERO query), todos
# os pesos ficam iguais a 1.0 e a distribuição é IDÊNTICA à de antes desta onda.
# A neutralidade sai de graça: é a mesma propriedade que torna a mudança segura
# para o `main`, onde a flag nunca liga.
EVENT_STATE_WEIGHTS: dict[str, float] = {
    "sitiada": 3.0,     # já está em ruína — o Céu não perdoa
    "ocupada": 2.5,     # bandeira estrangeira: o lugar já não se defende
    "tensa": 1.5,
    "prospera": 1.0,
    "festival": 0.5,    # a fortuna do lugar afasta o desastre
}


def _weighted_continent(conts, states: dict[str, str]) -> str:
    """Escolhe o continente do evento com peso pelo estado da região. Pura."""
    try:
        ws = [max(0.01, EVENT_STATE_WEIGHTS.get(str(states.get(c) or "prospera"), 1.0))
              for c in conts]
        return random.choices(list(conts), weights=ws, k=1)[0]
    except Exception:
        return random.choice(list(conts))


async def _spawn_event(session, now: datetime) -> WorldEvent | None:
    """1 evento novo, num continente escolhido pela FRAGILIDADE dele (Fase A2;
    nunca 2 ativos — o caller já garantiu que não há nenhum). Chronicle de
    nascimento diz o LUGAR."""
    if random.random() < 0.5:
        etype, conts, hours = EVENT_BEAST_TIDE, TIDE_CONTINENTS, TIDE_DURATION_HOURS
        goal = TIDE_GOAL
    else:
        etype, conts, hours = EVENT_METEOR, METEOR_CONTINENTS, METEOR_DURATION_HOURS
        goal = 0
    _states: dict[str, str] = {}
    try:
        from core.region_state_engine import get_states_map
        _states = await get_states_map(session) or {}
    except Exception:
        logger.debug("_spawn_event: region states unavailable", exc_info=True)
    cont = _weighted_continent(conts, _states)
    ev = WorldEvent(
        event_type=etype, continent_key=cont, state="active",
        payload={}, progress=0, goal=goal,
        created_at=now, expires_at=now + timedelta(hours=hours),
    )
    session.add(ev)
    await session.flush()
    from core.world_pulse_engine import emit_chronicle
    if etype == EVENT_BEAST_TIDE:
        await emit_chronicle(
            session, event_type="wev_tide_born", text_key="wev_chron_tide_born",
            params={"hours": int(hours)}, continent_key=cont, importance=2, now=now,
        )
    else:
        await emit_chronicle(
            session, event_type="wev_meteor_born", text_key="wev_chron_meteor_born",
            continent_key=cont, importance=2, now=now,
        )
    return ev


async def director_pulse(session) -> dict[str, Any] | None:
    """O passo do Director no World Pulse de 6h: sweep (resolve/expira — a rede
    de recuperação, lição sect_war) e DEPOIS talvez nascer 1 evento (~35%, só
    com nenhum ativo). Flag OFF → None sem UMA query (OFF-identity). Faz o
    próprio commit; qualquer falha é engolida e logada (o pulse nunca cai)."""
    if not director_on():
        return None
    now = _utcnow()
    summary: dict[str, Any] = {"resolved": 0, "expired": 0, "spawned": None}
    try:
        rows = (await session.execute(
            select(WorldEvent).where(
                WorldEvent.state == "active",
                WorldEvent.event_type.in_(DIRECTOR_EVENT_TYPES),
            ).order_by(WorldEvent.id).with_for_update()
        )).scalars().all()
        still_active = 0
        for ev in rows:
            try:
                if (ev.event_type == EVENT_BEAST_TIDE
                        and int(ev.goal or 0) > 0
                        and int(ev.progress or 0) >= int(ev.goal)):
                    # rede de recuperação — o goal foi batido mas a resolução
                    # inline não aconteceu/commitou
                    await _resolve_tide(session, ev, now)
                    summary["resolved"] += 1
                elif _aware(ev.expires_at) and _aware(ev.expires_at) <= now:
                    await _expire_event(session, ev, now)
                    summary["expired"] += 1
                else:
                    still_active += 1
            except Exception:
                logger.exception("tiandao sweep failed event=%s", ev.id)
                still_active += 1
        if still_active == 0 and random.random() < DIRECTOR_SPAWN_CHANCE:
            ev = await _spawn_event(session, now)
            if ev is not None:
                summary["spawned"] = f"{ev.event_type}@{ev.continent_key}"
        await session.commit()
        return summary
    except Exception:
        logger.exception("tiandao director_pulse failed")
        try:
            await session.rollback()
        except Exception:
            pass
        return None
