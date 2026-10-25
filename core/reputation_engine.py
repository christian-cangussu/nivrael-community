"""MV-6 Mundo Vivo v2 — Reputação regional + O RIVAL com memória.

O MV-1 deu geografia, o MV-2 movimento, o MV-3 consequência, o MV-4
profundidade, o MV-5 vida às quests. O MV-6 dá MEMÓRIA PESSOAL:

* **Reputação regional** — 1 INT por (jogador, continente), clamp [-100, +100].
  Sobe com o que você FAZ ali (storylet concluído +3 · bounty caçado +2 · maré
  contida +2 · cultivador local vencido +1 com cap diário) e decai 1/semana
  RUMO A ZERO nos continentes onde você não está (fama esvai, rancor cicatriza
  — Lei §1: nunca um poço eterno). O que ela FAZ (Onda 1, Lei §3 — poucos e
  sentidos): ≥+25 desconto no mercado local (clamp: o desconto TOTAL nunca
  excede a taxa de 5% — regra eterna do MV-3) · ≥+50 reverência na praça +
  prioridade de oferta de storylet (pacer 12h→8h) · ≤−25 preços +5% e os NPCs
  RECUSAM se aproximar com ofertas (com desprezo disclosed na praça — a
  adaptação wuxia da "recusa de escolta"; não existe sistema de escolta).

* **O RIVAL** — patent-safe vs Nemesis: 1 rival por jogador, sem hierarquia,
  memória = TEXTO (taunt determinístico, sem LLM) + power scaling (strike-only,
  o MESMO lever harness-validado do npc_cultivator_engine). Nascimento: 8% ao
  vencer um NpcCultivator ativo (se você não tem rival). Volta: pulse 6h;
  passa `RIVAL_RETURN_HOURS × defeats` → reaparece MAIS FORTE (+12%/derrota,
  cap +60%) na praça do jogador. Perder para ele: ele te POUPA (nunca kill —
  a humilhação é o custo) e cita isso na próxima. Na 5ª derrota: asciende ou
  cai (50/50, NARRATIVO — Chronicle + notificação; o row compartilhado do NPC
  NUNCA é mutado, porque o snapshot job ressuscitaria um echo e a praça dos
  outros jogadores não tem culpa) + título "💢 Quebra-Rivais" + slot livre.

Tudo atrás da flag per-world ``reputacao_rival`` (OFF por defeito → main
byte-idêntico; ver DEFAULT_WORLD_FEATURES em database/db.py).

Regras (padrão storylet_engine — tudo fail-safe, nada aqui quebra nada):
- Flag OFF → ``reputacao_on()`` False → TODA função é no-op sem UMA query.
- UM mutador: ``add_region_rep`` (clamp + antes→depois no retorno — progressão
  visível + milestone notify). Faucets são ganchos aditivos try/except nos
  settles EXISTENTES (claim_storylet / claim_bounty / _resolve_tide /
  resolve_npc_cultivator_from_duel) — zero engine de combate novo.
- O rival NUNCA muta o NpcCultivator compartilhado (echoes são re-assinados
  pelo snapshot job; ver acima). Toda a memória vive em players.rival_state.
- NPC 'fallen'/'ascended' nunca VIRA rival; rival cujo NPC caiu/ascendeu por
  conta própria é limpo com honestidade no pulse (notificação — nunca sumiço
  mudo, Lei §1). Rival não recebe bounty (exclusão nos spawns — sem loop).

Knobs: env ``REP_*`` / ``RIVAL_*`` (engine, não DB — launch-server-ready,
Lei §13).
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
# Flag + tuning (engine, não DB — env-overridable; padrão STORYLET_*/RST_*)
# ══════════════════════════════════════════════════════════════════════════

def reputacao_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão quests_vivas_on). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("reputacao_rival", world_key))
    except Exception:
        return False


# Reputação — clamp e faucets (Lei §13: knobs, nunca estoque).
REP_MIN = -100
REP_MAX = 100
REP_STORYLET_DONE = int(os.getenv("REP_STORYLET_DONE", "3"))
REP_BOUNTY_CLAIM = int(os.getenv("REP_BOUNTY_CLAIM", "2"))
REP_TIDE_CONTAINED = int(os.getenv("REP_TIDE_CONTAINED", "2"))
REP_NPC_WIN = int(os.getenv("REP_NPC_WIN", "1"))
# O ÚNICO faucet negativo (review MV-6: sem ele o desprezo era inalcançável —
# tier morto): storylet ACEITA que expira = palavra dada e quebrada; o
# continente onde a quest nasceu lembra. Bounded pelo pacer (1 oferta por vez).
REP_STORYLET_EXPIRED = int(os.getenv("REP_STORYLET_EXPIRED", "-2"))
# Cap diário do faucet de vitórias vs NpcCultivator (o único farmável).
REP_NPC_WIN_DAILY_CAP = int(os.getenv("REP_NPC_WIN_DAILY_CAP", "3"))
# Decay: 1 ponto RUMO A ZERO por semana, por continente ≠ atual.
REP_DECAY_DAYS = float(os.getenv("REP_DECAY_DAYS", "7"))

# O que a rep FAZ (Onda 1 — poucos e sentidos, Lei §3).
REP_DISCOUNT_THRESHOLD = int(os.getenv("REP_DISCOUNT_THRESHOLD", "25"))
REP_DISCOUNT_MULT = float(os.getenv("REP_DISCOUNT_MULT", "0.95"))
REP_REVERENCE_THRESHOLD = int(os.getenv("REP_REVERENCE_THRESHOLD", "50"))
REP_PRIORITY_COOLDOWN_HOURS = float(os.getenv("REP_PRIORITY_COOLDOWN_HOURS", "8"))
REP_CONTEMPT_THRESHOLD = int(os.getenv("REP_CONTEMPT_THRESHOLD", "-25"))
REP_CONTEMPT_MULT = float(os.getenv("REP_CONTEMPT_MULT", "1.05"))

# Milestones que notificam ao cruzar PARA CIMA (progressão visível).
REP_MILESTONES = (25, 50)

# O RIVAL.
RIVAL_BIRTH_CHANCE = float(os.getenv("RIVAL_BIRTH_CHANCE", "0.08"))
RIVAL_RETURN_HOURS = float(os.getenv("RIVAL_RETURN_HOURS", "48"))
RIVAL_POWER_PER_DEFEAT = float(os.getenv("RIVAL_POWER_PER_DEFEAT", "0.12"))
RIVAL_POWER_CAP = float(os.getenv("RIVAL_POWER_CAP", "0.60"))
RIVAL_MAX_DEFEATS = int(os.getenv("RIVAL_MAX_DEFEATS", "5"))

RIVAL_TITLE = "💢 Quebra-Rivais"

_TAUNT_VARIANTS = 6
_TAUNT_SPARED_VARIANTS = 2


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_iso(value: Any) -> datetime | None:
    try:
        if not value:
            return None
        return _aware(datetime.fromisoformat(str(value)))
    except Exception:
        return None


def clamp_rep(value: Any) -> int:
    try:
        return max(REP_MIN, min(REP_MAX, int(value or 0)))
    except (TypeError, ValueError):
        return 0


# ══════════════════════════════════════════════════════════════════════════
# Reputação — leitura
# ══════════════════════════════════════════════════════════════════════════

async def get_region_rep(session, player_id: int, continent: str | None) -> int:
    """O rep de UM continente (flag OFF / erro / inválido → 0 sem query)."""
    if not reputacao_on() or not is_valid_continent(continent):
        return 0
    try:
        from database.models import PlayerRegionRep
        row = (await session.execute(
            select(PlayerRegionRep.rep).where(
                PlayerRegionRep.player_id == int(player_id),
                PlayerRegionRep.continent_key == continent,
            )
        )).scalar()
        return clamp_rep(row)
    except Exception:
        logger.exception("get_region_rep failed (player=%s, cont=%s)", player_id, continent)
        return 0


async def get_rep_map(session, player_id: int) -> dict[str, int]:
    """{continent: rep} dos 5 continentes (row ausente → 0). Flag OFF → tudo 0
    SEM query. Defensivo — nunca levanta."""
    base = {key: 0 for key in CONTINENT_KEYS}
    if not reputacao_on():
        return base
    try:
        from database.models import PlayerRegionRep
        rows = (await session.execute(
            select(PlayerRegionRep).where(PlayerRegionRep.player_id == int(player_id))
        )).scalars().all()
        for row in rows:
            if row.continent_key in base:
                base[row.continent_key] = clamp_rep(row.rep)
        return base
    except Exception:
        logger.exception("get_rep_map failed (player=%s)", player_id)
        return base


def rep_tier(rep: int) -> str:
    """O tier narrativo de UM valor de rep (puro): reverence ≥50 · respected
    ≥25 · contempt ≤−25 · neutral no meio."""
    r = clamp_rep(rep)
    if r >= REP_REVERENCE_THRESHOLD:
        return "reverence"
    if r >= REP_DISCOUNT_THRESHOLD:
        return "respected"
    if r <= REP_CONTEMPT_THRESHOLD:
        return "contempt"
    return "neutral"


_TIER_META: dict[str, dict[str, str]] = {
    "reverence": {"emoji": "🏮", "name_key": "rep_tier_reverence"},
    "respected": {"emoji": "🤝", "name_key": "rep_tier_respected"},
    "neutral":   {"emoji": "🍃", "name_key": "rep_tier_neutral"},
    "contempt":  {"emoji": "🥀", "name_key": "rep_tier_contempt"},
}


def rep_chip(rep: int, lang: str) -> dict[str, Any]:
    """O chip de UM valor de rep, server-resolved (padrão state_views):
    {rep, tier, emoji, name, line}."""
    from core.i18n import t as i18n_t
    tier = rep_tier(rep)
    meta = _TIER_META[tier]
    name = i18n_t(lang, meta["name_key"])
    r = clamp_rep(rep)
    signed = f"+{r}" if r > 0 else str(r)
    return {
        "rep": r,
        "tier": tier,
        "emoji": meta["emoji"],
        "name": name,
        "line": f"{meta['emoji']} {name} · {signed}",
    }


async def rep_chip_map(session, player, lang: str) -> dict[str, dict[str, Any]]:
    """{continent: chip} para as superfícies (mapa v2, /viajar, TravelModal).
    Flag OFF → {} sem query (payload byte-idêntico)."""
    if player is None or not reputacao_on():
        return {}
    try:
        rep_map = await get_rep_map(session, int(player.telegram_id))
        return {cont: rep_chip(rep, lang) for cont, rep in rep_map.items()}
    except Exception:
        logger.exception("rep_chip_map failed")
        return {}


async def local_rep_view(session, player, lang: str) -> dict[str, Any] | None:
    """A visão do rep LOCAL para a praça: chip + linha de reverência (≥50,
    cumprimenta pelo dao_name) ou de desprezo (≤−25 — e DIZ que os NPCs não
    trazem ofertas: disclosure da supressão, Lei §1). Flag OFF/erro → None."""
    if player is None or not reputacao_on():
        return None
    try:
        from core.i18n import t as i18n_t
        cont = getattr(player, "current_continent", None) or "linghe"
        rep = await get_region_rep(session, int(player.telegram_id), cont)
        out = {"chip": rep_chip(rep, lang)}
        tier = rep_tier(rep)
        if tier == "reverence":
            name = getattr(player, "dao_name", None) or getattr(player, "username", None) or "—"
            out["line"] = i18n_t(lang, "rep_line_reverence", name=str(name))
        elif tier == "contempt":
            out["line"] = i18n_t(lang, "rep_line_contempt")
        return out
    except Exception:
        logger.exception("local_rep_view failed")
        return None


# ══════════════════════════════════════════════════════════════════════════
# Reputação — O mutador único (clamp + antes→depois + milestone)
# ══════════════════════════════════════════════════════════════════════════

async def _get_rep_row_locked(session, player_id: int, continent: str):
    """Busca (FOR UPDATE) ou cria a row de rep. Corrida do insert (PK) morre
    num SAVEPOINT e re-lê — padrão maybe_offer. Devolve a row lockada."""
    from database.models import PlayerRegionRep
    # populate_existing: se a MESMA sessão (pulse compartilhado) já carregou a
    # row antes de um commit intermediário, o FOR UPDATE deve re-hidratar do
    # DB — nunca confiar no identity map (lição v16.4c populate_existing).
    row = (await session.execute(
        select(PlayerRegionRep).where(
            PlayerRegionRep.player_id == int(player_id),
            PlayerRegionRep.continent_key == continent,
        ).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if row is not None:
        return row
    row = PlayerRegionRep(player_id=int(player_id), continent_key=continent,
                          rep=0, payload={}, updated_at=_utcnow())
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
        return row
    except Exception:
        return (await session.execute(
            select(PlayerRegionRep).where(
                PlayerRegionRep.player_id == int(player_id),
                PlayerRegionRep.continent_key == continent,
            ).with_for_update()
        )).scalar_one_or_none()


async def add_region_rep(session, player_id: int, continent: str | None,
                         delta: int, source: str,
                         lang: str | None = None) -> dict[str, Any] | None:
    """O mutador ÚNICO da reputação: clamp [-100, +100], antes→depois no
    retorno (progressão visível), milestone notify ao cruzar 25/50 para cima.
    Flag OFF → None sem UMA query. O caller é dono do commit. Nunca levanta."""
    try:
        if not reputacao_on() or not is_valid_continent(continent) or not delta:
            return None
        row = await _get_rep_row_locked(session, player_id, continent)
        if row is None:
            return None
        now = _utcnow()
        before = clamp_rep(row.rep)
        after = clamp_rep(before + int(delta))
        if after != before:
            row.rep = after
            row.updated_at = now
        out = {"continent": continent, "before": before, "after": after,
               "delta": after - before, "source": source}

        # Milestone (só cruzamento PARA CIMA — o rito social da rep).
        crossed = [m for m in REP_MILESTONES if before < m <= after]
        if crossed:
            try:
                from core.i18n import t as i18n_t
                from core.notification_engine import notify
                from core.continent_engine import CONTINENT_META
                if lang is None:
                    from database.models import Player
                    lang = str((await session.execute(
                        select(Player.language).where(Player.telegram_id == int(player_id))
                    )).scalar() or "pt").lower()
                cont_meta = CONTINENT_META.get(continent) or {}
                cont_name = i18n_t(lang, cont_meta.get("name_key", "")) if cont_meta.get("name_key") else continent
                await notify(
                    session, int(player_id), "region_rep_milestone",
                    title_key="notif_rep_milestone_title",
                    body_key="notif_rep_milestone_body",
                    payload={"continent": cont_name, "rep": after},
                    ref_id=f"rep:{player_id}:{continent}:{max(crossed)}", icon="🏮",
                    target_tab="plaza", priority=3,
                )
                out["milestone"] = max(crossed)
            except Exception:
                logger.debug("rep milestone notify failed", exc_info=True)
        return out
    except Exception:
        logger.exception("add_region_rep failed (player=%s, cont=%s, delta=%s, source=%s)",
                         player_id, continent, delta, source)
        return None


async def add_npc_win_rep(session, player, continent: str | None) -> dict[str, Any] | None:
    """O faucet de vitória vs NpcCultivator LOCAL (+1) com CAP DIÁRIO (o único
    faucet farmável — knob REP_NPC_WIN_DAILY_CAP). O contador do dia vive no
    payload da própria row (nunca a verdade do rep). Flag OFF → None sem query."""
    try:
        if player is None or not reputacao_on() or not is_valid_continent(continent):
            return None
        row = await _get_rep_row_locked(session, int(player.telegram_id), continent)
        if row is None:
            return None
        now = _utcnow()
        today = now.date().isoformat()
        payload = dict(row.payload or {})
        wins_today = int(payload.get("wins", 0) or 0) if payload.get("day") == today else 0
        if wins_today >= REP_NPC_WIN_DAILY_CAP:
            return None  # cap diário — o lugar já ouviu falar de você hoje
        payload["day"] = today
        payload["wins"] = wins_today + 1
        row.payload = payload  # dict NOVO → change tracking vê
        lang = (getattr(player, "language", None) or "pt").lower()
        return await add_region_rep(session, int(player.telegram_id), continent,
                                    REP_NPC_WIN, "npc_win", lang=lang)
    except Exception:
        logger.exception("add_npc_win_rep failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return None


# ══════════════════════════════════════════════════════════════════════════
# Reputação — efeitos (mercado + pacer de storylet)
# ══════════════════════════════════════════════════════════════════════════

async def market_rep_mult(session, player) -> float:
    """Multiplicador de preço do COMPRADOR pela rep LOCAL: ≥+25 → 0.95 ·
    ≤−25 → 1.05 · senão 1.0. Empilha com o estado do MV-3 no core/economy.py;
    o desconto COMBINADO é clampado lá (nunca excede a taxa de 5% — regra
    eterna do MV-3, além do clamp estrutural buyer_pays ≥ seller_receive).
    Fail-safe 1.0 — a compra nunca quebra pela rep."""
    try:
        if player is None or not reputacao_on():
            return 1.0
        cont = getattr(player, "current_continent", None) or "linghe"
        rep = await get_region_rep(session, int(player.telegram_id), cont)
        tier = rep_tier(rep)
        if tier in ("reverence", "respected"):
            return REP_DISCOUNT_MULT
        if tier == "contempt":
            return REP_CONTEMPT_MULT
        return 1.0
    except Exception:
        logger.exception("market_rep_mult failed")
        return 1.0


async def market_rep_note(session, player, lang: str) -> str | None:
    """A linha de disclosure do mercado pela rep (Lei §1 — nunca um preço
    mudo). None com flag OFF/tier neutro."""
    try:
        if player is None or not reputacao_on():
            return None
        cont = getattr(player, "current_continent", None) or "linghe"
        rep = await get_region_rep(session, int(player.telegram_id), cont)
        tier = rep_tier(rep)
        if tier in ("reverence", "respected"):
            mult = REP_DISCOUNT_MULT
        elif tier == "contempt":
            mult = REP_CONTEMPT_MULT
        else:
            return None
        from core.i18n import t as i18n_t
        pct = abs(round((mult - 1.0) * 100))
        key = "rep_market_note_down" if mult < 1.0 else "rep_market_note_up"
        return i18n_t(lang, key, pct=pct)
    except Exception:
        logger.exception("market_rep_note failed")
        return None


async def offer_pacer_mods(session, player) -> dict[str, Any]:
    """Os modificadores da rep no pacer de storylet (consumido por
    storylet_engine.maybe_offer E project_storylets — o timer disclosed nunca
    mente): {cooldown_hours: float|None, suppressed: bool}. ≥+50 → cooldown
    8h (prioridade de oferta); ≤−25 → suppressed (os NPCs do continente não
    se aproximam — disclosed na praça via local_rep_view). Flag OFF → neutro
    sem query."""
    neutral = {"cooldown_hours": None, "suppressed": False}
    try:
        if player is None or not reputacao_on():
            return neutral
        cont = getattr(player, "current_continent", None) or "linghe"
        rep = await get_region_rep(session, int(player.telegram_id), cont)
        tier = rep_tier(rep)
        if tier == "reverence":
            return {"cooldown_hours": REP_PRIORITY_COOLDOWN_HOURS, "suppressed": False}
        if tier == "contempt":
            return {"cooldown_hours": None, "suppressed": True}
        return neutral
    except Exception:
        logger.exception("offer_pacer_mods failed")
        return neutral


# ══════════════════════════════════════════════════════════════════════════
# Reputação — decay semanal (pega carona no World Pulse 6h; lição sect_war)
# ══════════════════════════════════════════════════════════════════════════

async def decay_region_rep(session) -> dict[str, Any] | None:
    """O passo do decay no World Pulse: 1 ponto RUMO A ZERO por semana em cada
    continente ≠ atual do jogador. Âncora = payload['last_decay'] (fallback
    updated_at — engajamento com o lugar segura a memória). Flag OFF → None
    sem UMA query (OFF-identity). Faz o próprio commit; falha engolida e
    logada (o pulse nunca cai)."""
    if not reputacao_on():
        return None
    now = _utcnow()
    summary = {"decayed": 0}
    try:
        from database.models import Player, PlayerRegionRep
        rows = (await session.execute(
            select(PlayerRegionRep).where(PlayerRegionRep.rep != 0)
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().all()
        if not rows:
            return summary
        pids = {int(r.player_id) for r in rows}
        conts = dict((await session.execute(
            select(Player.telegram_id, Player.current_continent)
            .where(Player.telegram_id.in_(pids))
        )).all())
        window = timedelta(days=REP_DECAY_DAYS)
        for row in rows:
            cur_cont = conts.get(int(row.player_id)) or "linghe"
            if row.continent_key == cur_cont:
                continue  # presença segura a memória — só o AUSENTE decai
            payload = dict(row.payload or {})
            anchor = _parse_iso(payload.get("last_decay")) or _aware(row.updated_at) or now
            if now - anchor < window:
                continue
            before = clamp_rep(row.rep)
            after = before - 1 if before > 0 else before + 1
            row.rep = after
            payload["last_decay"] = now.isoformat()
            row.payload = payload
            row.updated_at = now
            summary["decayed"] += 1
        await session.commit()
        return summary
    except Exception:
        logger.exception("decay_region_rep failed")
        try:
            await session.rollback()
        except Exception:
            pass
        return None


# ══════════════════════════════════════════════════════════════════════════
# O RIVAL — memória (rival_state JSONB), taunt determinístico, escala
# ══════════════════════════════════════════════════════════════════════════

def rival_power_mult(state: dict | None) -> float:
    """1 + min(0.12 × derrotas, 0.60) — puro. A memória vira força.
    Sem estado (None/{}) → 1.0: sem memória, sem escala."""
    try:
        if not state:
            return 1.0
        defeats = int(state.get("defeats", 1) or 1)
        return 1.0 + min(RIVAL_POWER_PER_DEFEAT * defeats, RIVAL_POWER_CAP)
    except Exception:
        return 1.0


def apply_rival_scaling(fighter: dict, state: dict | None) -> dict:
    """Aplica a escala do rival ao fighter REHIDRATADO (em cima do
    NPC_CULTIVATOR_POWER_SCALE): multiplicador STRIKE-ONLY em
    combat_profile['faction_dmg'] — o MESMO lever harness-validado do
    npc_cultivator_engine; nunca toca eff_hp/mitigação (o duelo continua
    ganhável; a pressão é que sobe). Devolve o próprio dict (mutado)."""
    try:
        mult = rival_power_mult(state)
        if mult == 1.0:
            return fighter
        prof = dict(fighter.get("combat_profile") or {})
        if prof:
            prof["faction_dmg"] = float(prof.get("faction_dmg", 1.0) or 1.0) * mult
            fighter["combat_profile"] = prof
        fighter["rival_power_mult"] = mult
        return fighter
    except Exception:
        logger.exception("apply_rival_scaling failed")
        return fighter


def rival_taunt(state: dict | None, lang: str) -> str:
    """O taunt server-resolved e DETERMINÍSTICO (seed + derrotas — sem LLM):
    cita a última derrota; se ele te POUPOU, cita a misericórdia (a humilhação
    é o custo). Fail-safe → string vazia."""
    try:
        from core.i18n import t as i18n_t
        st = state or {}
        seed = int(st.get("taunt_seed", 0) or 0)
        defeats = int(st.get("defeats", 1) or 1)
        if st.get("spared"):
            idx = 1 + (seed + defeats) % _TAUNT_SPARED_VARIANTS
            return i18n_t(lang, f"rvl_taunt_spared_{idx}", defeats=defeats)
        idx = 1 + (seed + defeats) % _TAUNT_VARIANTS
        return i18n_t(lang, f"rvl_taunt_{idx}", defeats=defeats)
    except Exception:
        logger.debug("rival_taunt failed", exc_info=True)
        return ""


def _rival_return_window(state: dict | None) -> timedelta:
    """Quanto tempo o rival some após cair: 48h × derrotas (ele lambe as
    feridas por mais tempo a cada queda)."""
    defeats = max(1, int((state or {}).get("defeats", 1) or 1))
    return timedelta(hours=RIVAL_RETURN_HOURS * defeats)


async def rival_npc_ids(session) -> set[int]:
    """Os NPC ids que são rival de ALGUÉM — exclusão nos spawns de bounty
    (sem loop com o board). Flag OFF → set() sem query. Fail-safe → set()."""
    if not reputacao_on():
        return set()
    try:
        from database.models import Player
        rows = (await session.execute(
            select(Player.rival_npc_id).where(Player.rival_npc_id.is_not(None))
        )).scalars().all()
        return {int(r) for r in rows if r}
    except Exception:
        logger.exception("rival_npc_ids failed")
        return set()


# ══════════════════════════════════════════════════════════════════════════
# O RIVAL — o gancho de settle (nascimento · derrota · misericórdia · fim)
# ══════════════════════════════════════════════════════════════════════════

async def on_npc_duel_settled(session, player, npc_id: Any, won: bool) -> dict[str, Any] | None:
    """O gancho ÚNICO pós-settle de um duelo vs NpcCultivator (chamado
    aditivamente por resolve_npc_cultivator_from_duel — o player já está
    FOR UPDATE na sessão do settle). Faz, nesta ordem:
      1. vitória → +1 rep local (cap diário);
      2. o NPC é o SEU rival → derrota (defeats+1 / conclusão no 5º) ou
         misericórdia (ele te POUPA e lembrará);
      3. sem rival + vitória + NPC ativo → chance de NASCER um rival.
    Flag OFF → None sem UMA query. Nunca levanta; devolve o ride do payload."""
    try:
        if player is None or npc_id is None or not reputacao_on():
            return None
        out: dict[str, Any] = {}
        now = _utcnow()
        lang = (getattr(player, "language", None) or "pt").lower()

        # 1. O faucet de vitória local (cap diário) — presença é o ponto.
        if won:
            cont = getattr(player, "current_continent", None) or "linghe"
            rep_out = await add_npc_win_rep(session, player, cont)
            if rep_out:
                out["rep"] = rep_out

        from database.models import NpcCultivator
        npc = (await session.execute(
            select(NpcCultivator).where(NpcCultivator.id == int(npc_id))
        )).scalar_one_or_none()
        if npc is None:
            return out or None

        rival_id = getattr(player, "rival_npc_id", None)

        # 2. O rival caiu (ou te poupou) — a memória cresce. SÓ quando ele está
        # PRESENTE (returned/spared): a janela de volta é o RITMO do arco
        # (review MV-6 — sem este gate, o rival "sumido" seguia desafiável
        # pela lista de NPCs e o arco inteiro + título caíam em ~40min).
        # Ausente, a luta é um duelo NPC comum (o +1 de rep acima já contou).
        if rival_id is not None and int(rival_id) == int(npc.id):
            state = dict(player.rival_state or {})
            if not state.get("returned") and not state.get("spared"):
                return out or None  # ele lambe as feridas — a memória espera a volta
            if won:
                defeats = int(state.get("defeats", 1) or 1) + 1
                if defeats >= RIVAL_MAX_DEFEATS:
                    out["rival"] = await _conclude_rivalry(session, player, npc, state, now, lang)
                else:
                    state["defeats"] = defeats
                    state["last_defeat_at"] = now.isoformat()
                    state["returned"] = False
                    state["spared"] = False
                    player.rival_state = state  # dict NOVO → change tracking vê
                    out["rival"] = {"event": "defeated", "name": npc.name,
                                    "defeats": defeats,
                                    "returns_in_hours": RIVAL_RETURN_HOURS * defeats}
                    # Review MV-6 (Lei §1): a derrota não-final era um void
                    # silencioso — o card sumia mudo. A notificação FECHA o
                    # beat: ele caiu, sumiu, e VOLTARÁ mais forte.
                    try:
                        from core.notification_engine import notify
                        await notify(
                            session, int(player.telegram_id), "rival_defeated",
                            title_key="notif_rvl_defeated_title",
                            body_key="notif_rvl_defeated_body",
                            payload={"name": npc.name},
                            ref_id=f"rvl:{player.telegram_id}:{npc.id}:def:{defeats}",
                            icon="😤", target_tab="plaza", priority=3,
                        )
                    except Exception:
                        logger.debug("rival defeated notify failed", exc_info=True)
            else:
                state["spared"] = True
                state["spared_count"] = int(state.get("spared_count", 0) or 0) + 1
                state["last_spared_at"] = now.isoformat()
                player.rival_state = state
                out["rival"] = {"event": "spared", "name": npc.name,
                                "taunt": rival_taunt(state, lang)}
            return out or None

        # 3. Nascimento: ele sobreviveu. E lembrará. (Nunca de um NPC caído —
        # kill-switch honesto do Onda 3.)
        if won and rival_id is None and npc.status == "active" \
                and random.random() < RIVAL_BIRTH_CHANCE:
            state = {
                "defeats": 1,
                "last_defeat_at": now.isoformat(),
                "taunt_seed": random.randint(0, 9999),
                "returned": False,
                "spared": False,
                "continent": npc.continent_key,
            }
            player.rival_npc_id = int(npc.id)
            player.rival_state = state
            out["rival"] = {"event": "born", "name": npc.name}
            try:
                from core.notification_engine import notify
                await notify(
                    session, int(player.telegram_id), "rival_born",
                    title_key="notif_rvl_born_title",
                    body_key="notif_rvl_born_body",
                    payload={"name": npc.name},
                    ref_id=f"rvl:{player.telegram_id}:{npc.id}:born", icon="😤",
                    target_tab="plaza", priority=3,
                )
            except Exception:
                logger.debug("rival born notify failed", exc_info=True)
        return out or None
    except Exception:
        logger.exception("on_npc_duel_settled failed (player=%s, npc=%s)",
                         getattr(player, "telegram_id", None), npc_id)
        return None


async def _conclude_rivalry(session, player, npc, state: dict, now: datetime,
                            lang: str) -> dict[str, Any]:
    """A 5ª derrota FECHA o arco: ele asciende ou cai (50/50 — NARRATIVO:
    Chronicle + notificação; o row do NPC não é mutado, ver docstring do
    módulo) + título "💢 Quebra-Rivais" (idempotente, padrão Vaso Perfeito) +
    slot livre para um novo rival."""
    fate = "ascended" if random.random() < 0.5 else "fallen"
    player.rival_npc_id = None
    player.rival_state = None
    out: dict[str, Any] = {"event": "concluded", "fate": fate, "name": npc.name,
                           "defeats": RIVAL_MAX_DEFEATS}
    # Título cosmético (reatribuição → dirty, lição unlocked_titles JSONB).
    try:
        titles = list(getattr(player, "unlocked_titles", None) or [])
        if RIVAL_TITLE not in titles:
            titles.append(RIVAL_TITLE)
            player.unlocked_titles = titles
            out["title_granted"] = RIVAL_TITLE
    except Exception:
        logger.debug("rival title grant failed", exc_info=True)
    # Chronicle — o mundo narra o fim do arco ({rival} resolve no render).
    try:
        from core.world_pulse_engine import emit_chronicle
        text_key = "rvl_chron_end_asc" if fate == "ascended" else "rvl_chron_end_fall"
        await emit_chronicle(
            session, event_type="rvl_end", text_key=text_key,
            params={"rival": npc.name},
            continent_key=getattr(player, "current_continent", None),
            importance=2, now=now,
        )
    except Exception:
        logger.debug("rival end chronicle failed", exc_info=True)
    try:
        from core.notification_engine import notify
        title_key = "notif_rvl_end_asc_title" if fate == "ascended" else "notif_rvl_end_fall_title"
        body_key = "notif_rvl_end_asc_body" if fate == "ascended" else "notif_rvl_end_fall_body"
        await notify(
            session, int(player.telegram_id), "rival_end",
            title_key=title_key, body_key=body_key,
            payload={"name": npc.name},
            ref_id=f"rvl:{player.telegram_id}:{npc.id}:end", icon="💢",
            target_tab="plaza", priority=2,
        )
    except Exception:
        logger.debug("rival end notify failed", exc_info=True)
    return out


# ══════════════════════════════════════════════════════════════════════════
# O RIVAL — a volta (pulse 6h) + kill-switch honesto
# ══════════════════════════════════════════════════════════════════════════

async def rival_pulse(session) -> dict[str, Any] | None:
    """O passo do rival no World Pulse: (a) rival cujo NPC caiu/ascendeu por
    conta própria (whispers/shadow) → limpa com honestidade (notificação —
    nunca sumiço mudo, Lei §1); (b) rival ausente há mais de 48h×derrotas →
    VOLTA mais forte (returned=True + notificação com o taunt). Flag OFF →
    None sem UMA query. Faz o próprio commit; falha engolida (o pulse nunca
    cai)."""
    if not reputacao_on():
        return None
    now = _utcnow()
    summary = {"returned": 0, "cleared": 0}
    try:
        from database.models import NpcCultivator, Player
        # populate_existing: um Player carregado antes neste MESMO pulse (ex.:
        # _resolve_tide) não pode servir stale sob o lock (lição v16.4c).
        players = (await session.execute(
            select(Player).where(Player.rival_npc_id.is_not(None))
            .with_for_update().execution_options(populate_existing=True)
        )).scalars().all()
        if not players:
            return summary
        npc_ids = {int(p.rival_npc_id) for p in players if p.rival_npc_id}
        npcs = {int(n.id): n for n in (await session.execute(
            select(NpcCultivator).where(NpcCultivator.id.in_(npc_ids))
        )).scalars().all()}
        from core.notification_engine import notify
        for p in players:
            try:
                npc = npcs.get(int(p.rival_npc_id or 0))
                state = dict(p.rival_state or {})
                lang = (getattr(p, "language", None) or "pt").lower()
                # (a) Kill-switch honesto: o mundo levou o rival embora.
                if npc is None or npc.status != "active":
                    name = npc.name if npc is not None else "—"
                    p.rival_npc_id = None
                    p.rival_state = None
                    summary["cleared"] += 1
                    try:
                        await notify(
                            session, int(p.telegram_id), "rival_gone",
                            title_key="notif_rvl_gone_title",
                            body_key="notif_rvl_gone_body",
                            payload={"name": name},
                            ref_id=f"rvl:{p.telegram_id}:gone:{int(now.timestamp())}",
                            icon="🌫️", target_tab="plaza", priority=4,
                        )
                    except Exception:
                        logger.debug("rival gone notify failed", exc_info=True)
                    continue
                # (b) A volta: mais forte, citando a derrota.
                if not state.get("returned"):
                    last = _parse_iso(state.get("last_defeat_at"))
                    if last is not None and now - last >= _rival_return_window(state):
                        state["returned"] = True
                        p.rival_state = state
                        summary["returned"] += 1
                        try:
                            await notify(
                                session, int(p.telegram_id), "rival_return",
                                title_key="notif_rvl_return_title",
                                body_key="notif_rvl_return_body",
                                payload={"name": npc.name,
                                         "taunt": rival_taunt(state, lang)},
                                ref_id=f"rvl:{p.telegram_id}:{npc.id}:ret:{int(state.get('defeats', 1) or 1)}",
                                icon="😤", target_tab="plaza", priority=3,
                            )
                        except Exception:
                            logger.debug("rival return notify failed", exc_info=True)
            except Exception:
                logger.exception("rival_pulse row failed (player=%s)",
                                 getattr(p, "telegram_id", None))
        await session.commit()
        return summary
    except Exception:
        logger.exception("rival_pulse failed")
        try:
            await session.rollback()
        except Exception:
            pass
        return None


# ══════════════════════════════════════════════════════════════════════════
# O RIVAL — a presença na praça (a view das duas superfícies)
# ══════════════════════════════════════════════════════════════════════════

async def rival_view(session, player, lang: str) -> dict[str, Any] | None:
    """O card do rival na praça do JOGADOR (a volta é per-player — o row
    compartilhado do NPC nunca é movido): só quando `returned` (ele está AQUI)
    ou `spared` (ele ficou, saboreando a vitória). NPC inativo → None (o pulse
    limpa e notifica em ≤6h — nunca um card morto). Flag OFF → None sem query."""
    if player is None or not reputacao_on():
        return None
    try:
        rival_id = getattr(player, "rival_npc_id", None)
        if not rival_id:
            return None
        state = dict(player.rival_state or {})
        if not state.get("returned") and not state.get("spared"):
            return None  # ele ainda lambe as feridas — a ausência é a presença
        from database.models import NpcCultivator
        npc = (await session.execute(
            select(NpcCultivator).where(NpcCultivator.id == int(rival_id))
        )).scalar_one_or_none()
        if npc is None or npc.status != "active":
            return None
        mult = rival_power_mult(state)
        return {
            "npc_id": int(npc.id),
            "name": npc.name,
            "realm": int(npc.realm or 0),
            "defeats": int(state.get("defeats", 1) or 1),
            "spared": bool(state.get("spared")),
            "power_bonus_pct": int(round((mult - 1.0) * 100)),
            "taunt": rival_taunt(state, lang),
        }
    except Exception:
        logger.exception("rival_view failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return None
