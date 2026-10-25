"""TEC-4 — Legacy Caves 传承洞 "Grutas do Legado" (Constituição §4, Q-4 modelo D).

A gruta NASCE do próprio mundo: quando uma casa rola `seek_inheritance` no World
Pulse (o whisper "⚰️ Legado Desperto" que já roda em prod), há chance real de a
tumba despertar VISITÁVEL — um `world_events` row com LUGAR + PRAZO, exatamente
o chassi do MV-2. Dentro dela vive o Eco de UM dos 5 NPCs lendários do
`world_lore §5`, e a arte única dele (ids 600-604) é a fonte MAIS RARA do jogo
(Lei §12): roll `LGC_ART_CHANCE` por clear + pity no `LGC_PITY_CLEARS`º clear
da mesma casa.

Regras de arquitetura (recon 2026-07-30, Sessions/2026-07-30 §3ª parte):
  · flag `legacy_caves` OFF ⇒ ZERO queries em toda função pública (OFF-identity);
  · INDEPENDENTE de `tiandao_director` — o spawn vive no hook do world_pulse e
    o expiry tem sweep PRÓPRIO (o sweep do Director morre com a flag dele OFF);
  · as 5 artes têm `sect_key="legacy_<npc>"` — a ÚNICA exclusão dos pools de
    drop é sect_key não-nulo (nenhum faucet filtra library_tier; recon §0.3);
  · tentativa-por-abertura e pity DERIVADOS de `duel_sessions`
    (`pve_source="legacy_cave"` + pve_context JSONB) — ZERO migration;
  · a luta espelha o padrão `hidden_rite` do TEC-3 (start → duelo → settle →
    recompensa; lazy-settle de órfão; npc_realm FIXO pela casa — a tumba não
    se curva ao reino do visitante).
"""
from __future__ import annotations

import logging
import os
import random as _random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text as _sql_text

from core.continent_engine import CONTINENT_KEYS, CONTINENT_META
from core.dungeon_regions import (
    REGIONAL_BONUS_LOOT,
    continent_emoji,
    player_continent,
)
from database.models import (
    DuelSession,
    Player,
    PlayerSectTechnique,
    PlayerTechnique,
    TechniqueCatalog,
    WorldEvent,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Tuning (engine, não DB — env-overridable; knobs viajam no payload das views)
# ══════════════════════════════════════════════════════════════════════════

CAVE_EVENT_TYPE = "legacy_cave"
CAVE_PVE_SOURCE = "legacy_cave"          # ≤ 24 chars (duel_sessions.pve_source)

LGC_OPEN_CHANCE = float(os.getenv("LGC_OPEN_CHANCE", "0.20"))
LGC_DRIFT = float(os.getenv("LGC_DRIFT", "0.30"))
LGC_GLOBAL_COOLDOWN_H = float(os.getenv("LGC_GLOBAL_COOLDOWN_H", "48"))
LGC_TTL_H = float(os.getenv("LGC_TTL_H", "72"))
LGC_PITY_DAYS = float(os.getenv("LGC_PITY_DAYS", "7"))
LGC_ART_CHANCE = float(os.getenv("LGC_ART_CHANCE", "0.15"))
LGC_PITY_CLEARS = int(os.getenv("LGC_PITY_CLEARS", "3"))
LGC_STONES_BASE = int(os.getenv("LGC_STONES_BASE", "5000"))
LGC_NPC_DIFFICULTY = os.getenv("LGC_NPC_DIFFICULTY", "hard")

# As 5 Casas de Legado (world_lore §5 — continente DERIVADO do lore; Wúmíng,
# o sem-continente cujas caves "vagam pelo mundo", cobre Fēnghuǒ que não tem
# NPC próprio; Xuèyè é demonic pela GEOGRAFIA — Mòyǔ já é demonic-only no
# travel, nenhum gate novo aqui). npc_realm FIXO: a dificuldade é da tumba.
CAVE_HOUSES: dict[str, dict[str, Any]] = {
    "tianlei": {"npc": "Shen Tianlei", "continent": "linghe",  "tech_id": 600, "npc_realm": 7, "emoji": "⛈️"},
    "gushan":  {"npc": "Tiě Gǔshān",   "continent": "qianhe",  "tech_id": 601, "npc_realm": 7, "emoji": "🗿"},
    "wuchen":  {"npc": "Huā Wúchén",   "continent": "yanshan", "tech_id": 602, "npc_realm": 7, "emoji": "🌸"},
    "wuming":  {"npc": "Yún Wúmíng",   "continent": "fenghuo", "tech_id": 603, "npc_realm": 8, "emoji": "🌀"},
    "xueye":   {"npc": "Lǐ Xuèyè",     "continent": "moyu",    "tech_id": 604, "npc_realm": 8, "emoji": "🩸"},
}
CONTINENT_TO_NPC: dict[str, str] = {v["continent"]: k for k, v in CAVE_HOUSES.items()}


def legacy_caves_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão regionais_on). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("legacy_caves", world_key))
    except Exception:
        return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_time_left(ms: int) -> str:
    s = max(0, int(ms / 1000))
    h = s // 3600
    if h > 0:
        return f"{h}h"
    return f"{max(1, s // 60)}m"


# ══════════════════════════════════════════════════════════════════════════
# Sweep + spawn (o hook do World Pulse) — expiry PRÓPRIO, nunca do Director
# ══════════════════════════════════════════════════════════════════════════

async def sweep_caves(session, *, now: datetime | None = None) -> int:
    """Expira grutas ativas cujo prazo passou (chronicle `lgc_faded`). Chamado
    do hook do pulse ANTES de decidir spawn — a gruta nunca vira zumbi mesmo
    com `tiandao_director` OFF (o sweep do Director não é nosso). Não commita."""
    now = now or _utcnow()
    expired = 0
    rows = (await session.execute(
        select(WorldEvent).where(
            WorldEvent.event_type == CAVE_EVENT_TYPE,
            WorldEvent.state == "active",
        ).with_for_update()
    )).scalars().all()
    for ev in rows:
        exp = _aware(ev.expires_at)
        if exp is None or exp > now:
            continue
        ev.state = "expired"
        ev.resolved_at = now
        expired += 1
        try:
            from core.world_pulse_engine import emit_chronicle
            house = CAVE_HOUSES.get((ev.payload or {}).get("npc_key") or "") or {}
            await emit_chronicle(
                session, event_type="lgc_faded", text_key="chron_lgc_faded",
                params={"npc": house.get("npc", "?")},
                continent_key=ev.continent_key, importance=1, now=now,
            )
        except Exception:
            logger.debug("sweep_caves chronicle failed ev=%s", ev.id, exc_info=True)
    return expired


async def maybe_open_cave(session, *, sect_id: str | None, continent_key: str | None,
                          rng: _random.Random | None = None,
                          now: datetime | None = None,
                          force_npc_key: str | None = None,
                          payload_extra: dict[str, Any] | None = None) -> WorldEvent | None:
    """O gatilho: chamado pelo `run_world_pulse` DEPOIS dos side-effects de um
    beat `seek_inheritance`. Guards em ordem: flag → sweep → 1 ativa no mundo →
    cooldown global → (pity 7d força; senão chance) → drift de continente.
    Best-effort: o caller embrulha em try/except (nunca mata o beat).

    TEC-5 (`force_npc_key`/`payload_extra`, ambos opcionais e default None ⇒
    comportamento byte-idêntico): um gatilho EXTERNO — atravessar o Rito do
    Coração-Demônio para o caminho demoníaco — pode acordar UMA casa específica
    (a tumba de Lǐ Xuèyè, que o drift natural só abre em ~6% das aberturas).
    Ele PULA a chance/pity de abertura (a chance dele é a do próprio gatilho) e
    o drift de continente (a casa está fixada), mas continua a respeitar TODOS
    os guards do mundo: flag, sweep, 1 gruta ativa, cooldown global e TTL —
    bloqueado ⇒ None, e o próximo sobrevivente rola."""
    if not legacy_caves_on():
        return None
    now = now or _utcnow()
    rng = rng or _random

    await sweep_caves(session, now=now)

    active = (await session.execute(
        select(func.count()).select_from(WorldEvent).where(
            WorldEvent.event_type == CAVE_EVENT_TYPE,
            WorldEvent.state == "active",
        )
    )).scalar() or 0
    if active > 0:
        return None

    last = (await session.execute(
        select(WorldEvent).where(WorldEvent.event_type == CAVE_EVENT_TYPE)
        .order_by(WorldEvent.id.desc()).limit(1)
    )).scalar_one_or_none()
    if last is not None:
        closed_at = _aware(last.resolved_at) or _aware(last.expires_at) or _aware(last.created_at)
        if closed_at is not None and now < closed_at + timedelta(hours=LGC_GLOBAL_COOLDOWN_H):
            return None

    if force_npc_key is not None:
        # Gatilho externo (TEC-5): a casa está escolhida e a chance já foi
        # rolada por quem chamou — aqui só os guards do mundo mandam.
        npc_key = force_npc_key if force_npc_key in CAVE_HOUSES else None
        if npc_key is None:
            return None
        cont = CAVE_HOUSES[npc_key]["continent"]
    else:
        # Pity global (Lei §1): 7 dias sem gruta ⇒ o próximo seek_inheritance abre
        # garantido. Senão, o roll — gated ANTES do random (lição MV-7).
        pity = last is None or (now - _aware(last.created_at)) >= timedelta(days=LGC_PITY_DAYS)
        if not pity and rng.random() >= LGC_OPEN_CHANCE:
            return None

        # Drift 70/30 (recon §0.2: blazing_sun/abyssal_depths NUNCA rolam a ação —
        # sem drift, Fēnghuǒ/Mòyǔ jamais veriam uma gruta).
        cont = continent_key if continent_key in CONTINENT_TO_NPC else None
        if cont is None or rng.random() < LGC_DRIFT:
            cont = rng.choice(list(CONTINENT_KEYS))
        npc_key = CONTINENT_TO_NPC.get(cont)
        if npc_key is None:                  # mapa incompleto — nunca acontece
            return None
    house = CAVE_HOUSES[npc_key]

    ev = WorldEvent(
        event_type=CAVE_EVENT_TYPE,
        continent_key=cont,
        state="active",
        payload={"npc_key": npc_key, "sect_id": sect_id, **(payload_extra or {})},
        progress=0, goal=0,
        created_at=now,
        expires_at=now + timedelta(hours=LGC_TTL_H),
    )
    session.add(ev)
    await session.flush()

    try:
        from core.world_pulse_engine import emit_chronicle
        await emit_chronicle(
            session, event_type="lgc_open", text_key="chron_lgc_open",
            params={"npc": house["npc"]}, continent_key=cont, sect_id=sect_id,
            importance=2, now=now,
        )
    except Exception:
        logger.debug("maybe_open_cave chronicle failed", exc_info=True)
    try:
        from core.heavens_whispers_engine import emit_whisper
        await emit_whisper(
            session, "cave_open", params={"npc": house["npc"]},
            continent_key=cont, sect_id=sect_id,
        )
    except Exception:
        logger.debug("maybe_open_cave whisper failed", exc_info=True)
    return ev


# ══════════════════════════════════════════════════════════════════════════
# Reads — a gruta ativa projetada para as superfícies (filtra, nunca escreve)
# ══════════════════════════════════════════════════════════════════════════

async def _active_cave(session, now: datetime | None = None) -> WorldEvent | None:
    """A gruta ativa (no máx. 1 por construção). Filtra expirada SEM escrever
    (padrão _active_events do MV-2 — quem escreve é o sweep do pulse)."""
    now = now or _utcnow()
    rows = (await session.execute(
        select(WorldEvent).where(
            WorldEvent.event_type == CAVE_EVENT_TYPE,
            WorldEvent.state == "active",
        ).order_by(WorldEvent.id.desc())
    )).scalars().all()
    for ev in rows:
        exp = _aware(ev.expires_at)
        if exp is None or exp > now:
            return ev
    return None


async def attempted_this_opening(session, player_id: int, event_id: int) -> bool:
    """1 tentativa por jogador por ABERTURA — derivada de duel_sessions
    (pve_context JSONB ->> event_id; zero migration)."""
    row = (await session.execute(
        select(DuelSession.id).where(
            DuelSession.attacker_id == player_id,
            DuelSession.pve_source == CAVE_PVE_SOURCE,
            DuelSession.pve_context["event_id"].astext == str(int(event_id)),
        ).limit(1)
    )).first()
    return row is not None


async def _clears_of_house(session, player_id: int, npc_key: str,
                           exclude_duel_id=None) -> int:
    """Clears VITORIOSOS deste jogador nesta casa de legado (insumo do pity)."""
    q = select(func.count()).select_from(DuelSession).where(
        DuelSession.attacker_id == player_id,
        DuelSession.pve_source == CAVE_PVE_SOURCE,
        DuelSession.state == "finished",
        DuelSession.winner_id == player_id,
        DuelSession.pve_context["npc_key"].astext == str(npc_key),
    )
    if exclude_duel_id is not None:
        q = q.where(DuelSession.id != exclude_duel_id)
    return int((await session.execute(q)).scalar() or 0)


async def _last_cave_duel(session, player_id: int):
    return (await session.execute(
        select(DuelSession).where(
            DuelSession.attacker_id == player_id,
            DuelSession.pve_source == CAVE_PVE_SOURCE,
        ).order_by(DuelSession.created_at.desc()).limit(1)
    )).scalar_one_or_none()


async def cave_view(session, ev: WorldEvent, lang: str, *, player=None,
                    now: datetime | None = None) -> dict[str, Any] | None:
    """Projeção da gruta para as superfícies (padrão event_view do MV-2 —
    name/desc server-resolved; a vitrine DIZ a chance da arte e a tentativa
    única ANTES do tap: display = roll, Lei §1/§10)."""
    from core.i18n import t as i18n_t, t_optional, catalog_name
    now = now or _utcnow()
    npc_key = (ev.payload or {}).get("npc_key") or ""
    house = CAVE_HOUSES.get(npc_key)
    if house is None:
        return None
    exp = _aware(ev.expires_at)
    time_left_ms = max(0, int((exp - now).total_seconds() * 1000)) if exp else 0
    cont_meta = CONTINENT_META.get(ev.continent_key) or {}
    tech = (await session.execute(
        select(TechniqueCatalog).where(TechniqueCatalog.id == house["tech_id"])
    )).scalar_one_or_none()
    view: dict[str, Any] = {
        "id": int(ev.id),
        "event_type": CAVE_EVENT_TYPE,
        "emoji": "🏮",
        "npc": house["npc"],
        "npc_emoji": house["emoji"],
        "npc_key": npc_key,
        "continent": ev.continent_key,
        "continent_emoji": continent_emoji(ev.continent_key),
        "continent_name": i18n_t(lang, cont_meta["name_key"]) if cont_meta.get("name_key") else ev.continent_key,
        "name": i18n_t(lang, "lgc_cave_name", npc=house["npc"]),
        "desc": i18n_t(lang, f"lgc_house_{npc_key}"),
        "time_left_ms": time_left_ms,
        "time_left_label": _fmt_time_left(time_left_ms),
        "art_chance_pct": round(LGC_ART_CHANCE * 100),
        "pity_clears": LGC_PITY_CLEARS,
        "npc_realm": int(house["npc_realm"]),
    }
    if tech is not None:
        view["art"] = {
            "tech_id": int(tech.id),
            "name": catalog_name(lang, "tech", tech),
            "emoji": tech.emoji,
        }
    if player is not None:
        here = player_continent(player) == ev.continent_key
        attempted = await attempted_this_opening(session, player.telegram_id, ev.id)
        has_art = (await session.execute(
            select(PlayerTechnique.technique_id).where(
                PlayerTechnique.player_id == player.telegram_id,
                PlayerTechnique.technique_id == house["tech_id"],
            ).limit(1)
        )).first() is not None
        view["here"] = bool(here)
        view["attempted"] = bool(attempted)
        view["has_art"] = bool(has_art)
        view["can_enter"] = bool(here and not attempted)
    return view


async def active_cave_view(session, lang: str, *, player=None,
                           now: datetime | None = None) -> dict[str, Any] | None:
    """A view pronta da gruta ativa, ou None. Flag OFF → None SEM query
    (OFF-identity). Defensiva — nunca levanta."""
    if not legacy_caves_on():
        return None
    try:
        now = now or _utcnow()
        ev = await _active_cave(session, now)
        if ev is None:
            return None
        return await cave_view(session, ev, lang, player=player, now=now)
    except Exception:
        logger.exception("active_cave_view failed")
        return None


# ══════════════════════════════════════════════════════════════════════════
# A run — start (gates disclosed em ordem) → duelo → settle (recompensa)
# ══════════════════════════════════════════════════════════════════════════

async def start_cave_run(session, player_id: int) -> dict[str, Any]:
    """Entrar na gruta = 1 duelo vs o Eco do Legado. Gates em ordem disclosed:
    flag → gruta ativa → continente → tentativa única → duelo aberto → HP.
    Devolve ``{ok, duel_id}``; o caller commita. Espelha `start_hidden_rite`
    (incluindo o lazy-settle de órfão §5-C)."""
    if not legacy_caves_on():
        return {"ok": False, "reason": "lgc_off"}

    now = _utcnow()
    player = (await session.execute(
        select(Player).where(Player.telegram_id == player_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if player is None:
        return {"ok": False, "reason": "player_not_found"}

    ev = await _active_cave(session, now)
    if ev is None:
        return {"ok": False, "reason": "no_cave"}
    npc_key = (ev.payload or {}).get("npc_key") or ""
    house = CAVE_HOUSES.get(npc_key)
    if house is None:
        return {"ok": False, "reason": "no_cave"}

    if player_continent(player) != ev.continent_key:
        return {"ok": False, "reason": "wrong_continent",
                "continent": ev.continent_key,
                "continent_emoji": continent_emoji(ev.continent_key)}

    # Curar a run anterior órfã ANTES do check de tentativa (o settle tardio
    # entrega o loot que ficou preso — lição hidden_rite §5-C).
    prev = await _last_cave_duel(session, player_id)
    if prev is not None:
        if prev.state in ("waiting_actions", "pending_acceptance"):
            prev_event = str((prev.pve_context or {}).get("event_id") or "")
            if prev_event == str(ev.id):
                # npc no payload também no RESUME — o chat monta o resultado
                # com res["npc"] (sem isto o auto-play retomado diria "Eco de ?").
                return {"ok": True, "duel_id": str(prev.id), "resumed": True,
                        "npc": house["npc"], "npc_emoji": house["emoji"]}
            return {"ok": False, "reason": "duel_already_active", "duel_id": str(prev.id)}
        if prev.state in ("finished", "forfeited"):
            try:
                from core.duel_engine import apply_post_duel_effects
                await apply_post_duel_effects(session, prev)
                await session.flush()
            except Exception:
                logger.exception("start_cave_run: stale-duel settle failed duel=%s", prev.id)

    if await attempted_this_opening(session, player_id, ev.id):
        return {"ok": False, "reason": "already_attempted",
                "time_left_ms": int(max(0, (_aware(ev.expires_at) - now).total_seconds() * 1000))
                if ev.expires_at else 0}

    # UMA verdade do "um duelo de cada vez" (o helper também cura estagnados).
    try:
        from core.sect_trial_engine import _has_open_duel
        open_duel = await _has_open_duel(session, player_id)
    except Exception:
        logger.debug("start_cave_run open-duel check failed (player_id=%s)",
                     player_id, exc_info=True)
        open_duel = None
    if open_duel is not None:
        return {"ok": False, "reason": "duel_already_active", "duel_id": str(open_duel.id)}

    try:
        from core.combat_engine import get_current_hp
        if get_current_hp(player) <= 0:
            return {"ok": False, "reason": "hp_depleted"}
    except Exception:
        logger.debug("start_cave_run hp check failed (player_id=%s)",
                     player_id, exc_info=True)

    try:
        from core.duel_engine import start_duel_pve
        duel = await start_duel_pve(
            session, player,
            archetype="elder",                    # o Eco do Legado
            difficulty=LGC_NPC_DIFFICULTY,
            source=CAVE_PVE_SOURCE,
            context={"event_id": int(ev.id), "npc_key": npc_key,
                     "tech_id": int(house["tech_id"])},
            npc_realm=int(house["npc_realm"]),    # a tumba NÃO escala com você
        )
        await session.flush()
        return {"ok": True, "duel_id": str(duel.id), "npc": house["npc"],
                "npc_emoji": house["emoji"]}
    except Exception:
        logger.exception("start_cave_run failed (player_id=%s)", player_id)
        return {"ok": False, "reason": "internal_error"}


async def _grant_cave_art(session, player, tech, npc_key: str) -> dict[str, Any]:
    """O ATO de transmitir a arte de legado — espelho do `_grant_library_art`
    do TEC-3 (auto-equip slot-aware + registro eterno), mas SEM débito (o preço
    foi a gruta) e com `sect_key="legacy_<npc>"` no registro (independente da
    casa do jogador; `is_library_locked` ignora — library_tier é NULL)."""
    from core.i18n import t_optional, catalog_name
    player_id = int(player.telegram_id)
    lang = getattr(player, "language", None) or "pt"

    auto_equip = True
    try:
        from core.combat_engine import get_max_combat_techniques
        equipped = (await session.execute(
            select(func.count()).select_from(PlayerTechnique).where(
                PlayerTechnique.player_id == player_id,
                PlayerTechnique.is_active_combat == True,  # noqa: E712
            )
        )).scalar() or 0
        if equipped >= get_max_combat_techniques(int(player.realm or 0)):
            auto_equip = False
    except Exception:
        logger.debug("_grant_cave_art slot check failed (player_id=%s)",
                     player_id, exc_info=True)

    session.add(PlayerTechnique(
        player_id=player_id, technique_id=int(tech.id),
        mastery_level=1, is_active_combat=auto_equip,
    ))
    # Registro eterno SÓ se ainda não existe — um renascido re-conquistando a
    # arte tem PlayerTechnique wipado mas o registro (PK player+tech) INTACTO;
    # re-inserir estouraria a PK (lição TEC-1 F3, o bug do relearn).
    prior_reg = (await session.execute(
        select(PlayerSectTechnique).where(
            PlayerSectTechnique.player_id == player_id,
            PlayerSectTechnique.technique_id == int(tech.id),
        )
    )).scalar_one_or_none()
    if prior_reg is None:
        session.add(PlayerSectTechnique(
            player_id=player_id, technique_id=int(tech.id),
            sect_key=f"legacy_{npc_key}", cp_paid=0,
        ))
        await _chronicle_first_claim(session, player_id, npc_key)
    return {
        "tech_id": int(tech.id),
        "name": catalog_name(lang, "tech", tech),
        "emoji": tech.emoji,
        "auto_equipped": auto_equip,
    }


async def _chronicle_first_claim(session, player_id: int, npc_key: str) -> None:
    """Chronicle `lgc_claim` — a 1ª arte do servidor POR casa de legado
    (advisory lock namespaced, padrão sel_first/lib_first)."""
    try:
        await session.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext('lgc_first:' || :k))"),
            {"k": npc_key},
        )
        house = CAVE_HOUSES.get(npc_key) or {}
        other = (await session.execute(
            select(PlayerSectTechnique.player_id).where(
                PlayerSectTechnique.sect_key == f"legacy_{npc_key}",
                PlayerSectTechnique.player_id != player_id,
            ).limit(1)
        )).first()
        if other is not None:
            return
        from core.world_pulse_engine import emit_chronicle
        await emit_chronicle(
            session, event_type="lgc_claim", text_key="chron_lgc_claim",
            params={"npc": house.get("npc", "?")},
            continent_key=house.get("continent"), importance=2,
        )
    except Exception:
        logger.debug("_chronicle_first_claim failed (npc=%s)", npc_key, exc_info=True)


async def resolve_legacy_cave_from_duel(session, duel, player, won: bool,
                                        rng: _random.Random | None = None) -> dict[str, Any]:
    """Liquida a run da gruta (chamado por `settle_pve_duel`; player row já
    LOCKED pelo settle). Derrota ⇒ a tentativa foi consumida (dito na UI).
    Vitória ⇒ SEMPRE paga (pedras + material regional + fragmento R5+); a ARTE
    sai por roll `LGC_ART_CHANCE` + pity no `LGC_PITY_CLEARS`º clear da casa;
    já tem a arte ⇒ recheio ×2 (dito ANTES de entrar, na vitrine)."""
    payload: dict[str, Any] = {"cave": "won" if won else "lost"}
    if not won:
        return payload
    rng = rng or _random
    try:
        ctx = duel.pve_context or {}
        npc_key = str(ctx.get("npc_key") or "")
        house = CAVE_HOUSES.get(npc_key)
        if house is None:
            return payload
        player_id = int(player.telegram_id)

        has_art = (await session.execute(
            select(PlayerTechnique.technique_id).where(
                PlayerTechnique.player_id == player_id,
                PlayerTechnique.technique_id == int(house["tech_id"]),
            ).limit(1)
        )).first() is not None
        loot_mult = 2 if has_art else 1

        # 1) Pedras — o "sempre paga" (escala com o reino da tumba, não o seu).
        stones = LGC_STONES_BASE * int(house["npc_realm"]) * loot_mult
        player.spirit_stones = int(player.spirit_stones or 0) + stones
        payload["stones"] = stones

        # 2) Material nativo do continente (o MESMO mapa do loot regional MV-1).
        try:
            from core.utils import add_item_to_inventory
            base = REGIONAL_BONUS_LOOT.get(house["continent"]) or {}
            for kind, val in base.items():
                if kind == "stones":
                    extra = int(val) * loot_mult
                    player.spirit_stones = int(player.spirit_stones or 0) + extra
                    payload["stones"] = payload["stones"] + extra
                elif isinstance(val, dict):
                    item_type = {"ores": "ore", "herbs": "herb"}.get(kind)
                    if not item_type:
                        continue
                    for item_id, qty in val.items():
                        added = await add_item_to_inventory(
                            session, player_id, item_type, int(item_id),
                            int(qty) * loot_mult,
                        )
                        if added:
                            payload.setdefault("materials", []).append(
                                {"item_type": item_type, "item_id": int(item_id),
                                 "qty": int(qty) * loot_mult})
                        else:
                            payload["bag_full"] = True
        except Exception:
            logger.exception("resolve_legacy_cave: material grant failed duel=%s", duel.id)

        # 3) Fragmento de Dao (R5+ — o helper CANÔNICO gate-a por dentro).
        try:
            from core.dao_engine import grant_random_fragments
            frags = await grant_random_fragments(
                session, player_id, 1, int(player.realm or 0))
            if frags:
                payload["dao_fragments"] = len(frags)
        except Exception:
            logger.exception("resolve_legacy_cave: dao fragment failed duel=%s", duel.id)

        # TEC-5 — "A Noite de Sangue viu você": quem desceu pelo Rito e venceu
        # NA TUMBA DELA é notado por Lǐ Xuèyè (ela está VIVA no lore, R9). Key
        # CONDICIONAL; `begin_nested` PRÓPRIO lá dentro (o try/except deste
        # settle não tem savepoint). Flag OFF ⇒ None sem query.
        try:
            from core.forbidden_path_engine import xueye_notice
            _seen = await xueye_notice(session, player, npc_key)
            if _seen:
                payload["xueye_notice"] = _seen
        except Exception:
            logger.exception("resolve_legacy_cave: xueye notice failed duel=%s", duel.id)

        # 4) A ARTE (Lei §12 — a fonte mais rara do jogo; pity = Lei §1).
        if has_art:
            payload["already_has_art"] = True
            return payload
        clears = await _clears_of_house(
            session, player_id, npc_key, exclude_duel_id=duel.id) + 1
        payload["clears"] = clears
        granted = clears >= LGC_PITY_CLEARS or rng.random() < LGC_ART_CHANCE
        if not granted:
            payload["art_missed"] = {"clears": clears, "pity_at": LGC_PITY_CLEARS}
            return payload
        tech = (await session.execute(
            select(TechniqueCatalog).where(TechniqueCatalog.id == int(house["tech_id"]))
        )).scalar_one_or_none()
        if tech is None:
            return payload
        art = await _grant_cave_art(session, player, tech, npc_key)
        payload["art"] = art
        return payload
    except Exception:
        logger.exception("resolve_legacy_cave_from_duel failed (duel=%s)", duel.id)
        return payload
