"""MV-4 Mundo Vivo v2 — Corpo Profundo: os 12 MERIDIANOS 经脉 + refino ancorado em LUGAR.

O MV-1 deu geografia, o MV-2 movimento, o MV-3 consequência. O MV-4 dá
PROFUNDIDADE AO CORPO: os 12 canais clássicos (十二正经 — 手三阴/手三阳/
足三阴/足三阳) abrem-se UM A UM, por um ritual multi-etapa BEM difícil
(Lei "progressão dura + visível"), e a eficiência de refinar/temperar passa a
ser f(ONDE você está) — a caverna com Formação viva vira BASE, o sítio de
têmpera do continente é a linha de base, e refinar na estrada é amador.

Tudo atrás da flag per-world ``corpo_profundo`` (OFF por defeito → main
byte-idêntico; ver DEFAULT_WORLD_FEATURES em database/db.py).

Regras (padrão region_state_engine — tudo fail-safe, nada aqui quebra nada):
- Flag OFF → ``corpo_profundo_on()`` False → TODA função é no-op sem UMA query
  (``refine_place_mult`` devolve neutro 1.0; os WRITEs recusam disclosed).
- O ritual tem 3 etapas (Lei §1 — nunca um void):
    (1) PREPARAR o corpo — custo real: pedras + mortal_temper_progress (a
        Horta/Caça/Ambiental/Combate passam a SERVIR os meridianos) +
        hunt_essence (a essência de caça do Sprint 5);
    (2) CIRCULAR qi — sessão idle de N horas (tipo expedição, não spam),
        mais RÁPIDA no lugar certo (place mult);
    (3) ROMPER — chance HONESTA de falha com progresso parcial: cada falha
        soma bónus permanente à próxima tentativa e NADA do que foi pago se
        perde (só se re-circula, mais curto). Nunca perder tudo.
- O bónus por canal NÃO vive aqui: folda na Alma via
  ``body_tempering_engine.body_durability_mult`` (o único chokepoint que o
  pool de HP, a mitigação E o Poder de Combate leem) — nenhuma tela recalcula.
- Refino ancorado (UM helper, duas superfícies): ``refine_place_mult``:
    🏯 caverna própria (você NO continente dela) com Formação VIVA no slot 1.25
    ⛰️ continente com sítio de têmpera (Sprint 6)                          1.00
    🗺️ qualquer outro lugar (Mòyǔ / sem âncora)                            0.75
  🏮 o festival do MV-3 modula EM CIMA (region_overrides.qi_tick_mult — os
  pilares conversam). Consumidores: a ação de temperar (qi cost ÷ mult) e a
  etapa de circular do ritual (duração ÷ mult).
- Concorrência: os WRITEs assumem que o CALLER segura ``player`` FOR UPDATE e
  é dono do commit (padrão claim_bounty); revalidam tudo e falham atómicos.
- JSONB: as colunas (Migration 132) são sempre REATRIBUÍDAS (nunca mutadas
  in-place) para o SQLAlchemy marcar dirty.

Knobs: env ``MERIDIAN_*`` / ``REFINE_*`` (engine, não DB — launch-server-ready,
Lei §13; o owner afina por servidor via env).
"""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, text as _sql_text

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Flag + tuning (engine, não DB — env-overridable; padrão TIANDAO_*/RST_*)
# ══════════════════════════════════════════════════════════════════════════

def corpo_profundo_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão estados_on). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("corpo_profundo", world_key))
    except Exception:
        return False


# Realm gate: 1º canal exige R2; cada reino acima libera +2 canais
# (R2→2, R3→4, R4→6, R5→8, R6→10, R7+→12). O corpo acompanha o reino —
# nunca se abre tudo num fim de semana (BEM difícil, mandato do owner).
MERIDIAN_MIN_REALM = int(os.getenv("MERIDIAN_MIN_REALM", "2"))
MERIDIAN_CHANNELS_PER_REALM = int(os.getenv("MERIDIAN_CHANNELS_PER_REALM", "2"))

# Custo de PREPARAR o canal i (1..12) — cresce por canal:
#   pedras   = BASE × GROWTH^(i-1)          (1.5k → ~86k)
#   progresso= PBASE + PSTEP×(i-1)          (80 → 630; a MESMA moeda paciente
#              da Horta/Caça/Ambiental/Combate — os 4 faucets passam a SERVIR)
#   essência = EBASE + ESTEP×(i-1)          (15 → 125; hunt_essence, Sprint 5)
MERIDIAN_STONES_BASE = int(os.getenv("MERIDIAN_STONES_BASE", "1500"))
MERIDIAN_STONES_GROWTH = float(os.getenv("MERIDIAN_STONES_GROWTH", "1.45"))
MERIDIAN_PROGRESS_BASE = int(os.getenv("MERIDIAN_PROGRESS_BASE", "80"))
MERIDIAN_PROGRESS_STEP = int(os.getenv("MERIDIAN_PROGRESS_STEP", "50"))
MERIDIAN_ESSENCE_BASE = int(os.getenv("MERIDIAN_ESSENCE_BASE", "15"))
MERIDIAN_ESSENCE_STEP = int(os.getenv("MERIDIAN_ESSENCE_STEP", "10"))

# CIRCULAR qi: sessão idle de N horas (cresce por canal), dividida pelo mult
# do lugar (a caverna canaliza; a estrada arrasta).
MERIDIAN_CIRCULATE_HOURS_BASE = float(os.getenv("MERIDIAN_CIRCULATE_HOURS_BASE", "6.0"))
MERIDIAN_CIRCULATE_GROWTH = float(os.getenv("MERIDIAN_CIRCULATE_GROWTH", "0.20"))
# Após uma falha, a re-circulação é mais curta (o canal ficou "amaciado").
MERIDIAN_RETRY_FRACTION = float(os.getenv("MERIDIAN_RETRY_FRACTION", "0.5"))

# ROMPER: chance honesta, cai por canal, sobe a cada falha (progresso parcial
# — Lei §1: uma falha NUNCA é perda total).
MERIDIAN_BREAK_CHANCE_BASE = float(os.getenv("MERIDIAN_BREAK_CHANCE_BASE", "0.55"))
MERIDIAN_BREAK_CHANCE_STEP = float(os.getenv("MERIDIAN_BREAK_CHANCE_STEP", "0.02"))
MERIDIAN_BREAK_CHANCE_FLOOR = float(os.getenv("MERIDIAN_BREAK_CHANCE_FLOOR", "0.30"))
MERIDIAN_BREAK_RETRY_BONUS = float(os.getenv("MERIDIAN_BREAK_RETRY_BONUS", "0.10"))
MERIDIAN_BREAK_CHANCE_CAP = float(os.getenv("MERIDIAN_BREAK_CHANCE_CAP", "0.90"))

# Cooldown entre RITUAIS (dias — conta a partir do último canal ABERTO). Com
# circulação + cooldown, 12 canais ≈ 4-6 semanas de jogo real: BEM difícil.
MERIDIAN_RITUAL_COOLDOWN_HOURS = float(os.getenv("MERIDIAN_RITUAL_COOLDOWN_HOURS", "48"))

# O que cada canal DÁ (progressão visível, pequena e legível): +2% de
# durabilidade (HP/DEF) por canal, foldado na Alma via body_durability_mult.
# 12/12 = +24% — sente-se, não quebra. Antes→depois obrigatório no resultado.
MERIDIAN_DURABILITY_PER_CHANNEL = float(os.getenv("MERIDIAN_DURABILITY_PER_CHANNEL", "0.02"))

# R7+ (Integração Corporal): TODOS os faucets de mortal_temper_progress e
# hunt_essence são gated realm<7 — sem isto, os canais 11-12 (gate R7) pediriam
# um recurso IMPOSSÍVEL de ganhar (classe dead-end Lei §1, lição BT-gate). No
# ápex o preparo troca carne mortal por riqueza: progresso/essência = 0 e as
# pedras escalam (continua BEM difícil, nunca impossível).
MERIDIAN_APEX_STONES_MULT = float(os.getenv("MERIDIAN_APEX_STONES_MULT", "3.0"))
_APEX_REALM = 7  # = body_tempering_engine.MIN_REALM_REQUIRED (sem import p/ evitar ciclo)

# ── Refino ancorado em lugar (P6; consumido também pelo temperar) ──────────
REFINE_MULT_CAVERN = float(os.getenv("REFINE_MULT_CAVERN", "1.25"))
REFINE_MULT_SITE = float(os.getenv("REFINE_MULT_SITE", "1.0"))
REFINE_MULT_ANYWHERE = float(os.getenv("REFINE_MULT_ANYWHERE", "0.75"))


# ══════════════════════════════════════════════════════════════════════════
# Os 12 canais (十二正经) — a ordem clássica da circulação do qi. Lei §3:
# 12 canais com nuance, não 100 skills. Nomes server-resolved (mer_ch_<key>
# nos locales de CHAT, padrão Chronicle/continentes).
# ══════════════════════════════════════════════════════════════════════════

# MV-5 §0 — o título cosmético do 12/12 (string canónica única, padrão
# Pavilhão de Mérito; a descrição ×3 idiomas vive em title_desc_vaso_perfeito).
MERIDIAN_TITLE_12 = "🏮 Vaso Perfeito"

MERIDIAN_CHANNELS: tuple[dict[str, str], ...] = (
    {"key": "pulmao",            "emoji": "🌬️", "group": "手太阴"},
    {"key": "intestino_grosso",  "emoji": "🌫️", "group": "手阳明"},
    {"key": "estomago",          "emoji": "🏔️", "group": "足阳明"},
    {"key": "baco",              "emoji": "🌾", "group": "足太阴"},
    {"key": "coracao",           "emoji": "🔥", "group": "手少阴"},
    {"key": "intestino_delgado", "emoji": "☀️", "group": "手太阳"},
    {"key": "bexiga",            "emoji": "🌊", "group": "足太阳"},
    {"key": "rim",               "emoji": "💧", "group": "足少阴"},
    {"key": "pericardio",        "emoji": "🛡️", "group": "手厥阴"},
    {"key": "triplo_aquecedor",  "emoji": "🕯️", "group": "手少阳"},
    {"key": "vesicula",          "emoji": "🌿", "group": "足少阳"},
    {"key": "figado",            "emoji": "🌳", "group": "足厥阴"},
)
MERIDIAN_TOTAL = len(MERIDIAN_CHANNELS)  # 12
_CHANNEL_INDEX = {c["key"]: i for i, c in enumerate(MERIDIAN_CHANNELS)}  # 0-based


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════════════════
# Puros — contagem, bónus (a Alma lê ESTES), gates e curvas
# ══════════════════════════════════════════════════════════════════════════

def _opened_map(player) -> dict:
    m = getattr(player, "meridians_opened", None)
    return m if isinstance(m, dict) else {}


def meridian_count(player) -> int:
    """Canais abertos (0..12). Puro — só lê o row já carregado."""
    return sum(1 for k in _opened_map(player) if k in _CHANNEL_INDEX)


def meridian_durability_bonus(player) -> float:
    """O bónus ADITIVO de durabilidade que body_durability_mult folda
    (+MERIDIAN_DURABILITY_PER_CHANNEL por canal aberto). Gated pela flag —
    mundo OFF → 0.0 SEMPRE (main byte-idêntico mesmo se a coluna tivesse
    lixo). Puro + fail-safe: nunca levanta, nunca toca a sessão."""
    try:
        if not corpo_profundo_on():
            return 0.0
        n = meridian_count(player)
        return float(n) * MERIDIAN_DURABILITY_PER_CHANNEL if n > 0 else 0.0
    except Exception:
        return 0.0


def channels_allowed(realm: int) -> int:
    """Quantos canais o reino atual suporta (o corpo acompanha o reino)."""
    realm = int(realm or 0)
    if realm < MERIDIAN_MIN_REALM:
        return 0
    return min(MERIDIAN_TOTAL, MERIDIAN_CHANNELS_PER_REALM * (realm - MERIDIAN_MIN_REALM + 1))


def next_channel(player) -> dict[str, str] | None:
    """O próximo canal na ordem clássica (None = 12/12). A abertura é
    SEQUENCIAL — o qi circula na ordem dos canais, não à la carte."""
    opened = _opened_map(player)
    for ch in MERIDIAN_CHANNELS:
        if ch["key"] not in opened:
            return ch
    return None


def channel_cost(index0: int, realm: int = 0) -> dict[str, int]:
    """Custo de PREPARAR o canal de índice 0-based i: {stones, progress, essence}.
    R7+ → progresso/essência = 0 (faucets mortos no ápex — dead-end Lei §1) e
    pedras × MERIDIAN_APEX_STONES_MULT (a dureza muda de moeda, não morre)."""
    i = max(0, int(index0))
    stones = MERIDIAN_STONES_BASE * (MERIDIAN_STONES_GROWTH ** i)
    if int(realm or 0) >= _APEX_REALM:
        return {"stones": int(round(stones * MERIDIAN_APEX_STONES_MULT)),
                "progress": 0, "essence": 0}
    return {
        "stones": int(round(stones)),
        "progress": MERIDIAN_PROGRESS_BASE + MERIDIAN_PROGRESS_STEP * i,
        "essence": MERIDIAN_ESSENCE_BASE + MERIDIAN_ESSENCE_STEP * i,
    }


def circulate_hours(index0: int) -> float:
    """Horas base de circulação do canal i (antes do mult do lugar)."""
    return MERIDIAN_CIRCULATE_HOURS_BASE * (1.0 + MERIDIAN_CIRCULATE_GROWTH * max(0, int(index0)))


def break_chance(index0: int, attempts: int) -> float:
    """Chance HONESTA de rompimento: cai por canal, sobe por falha (progresso
    parcial — nunca perder tudo, Lei §1)."""
    base = max(MERIDIAN_BREAK_CHANCE_FLOOR,
               MERIDIAN_BREAK_CHANCE_BASE - MERIDIAN_BREAK_CHANCE_STEP * max(0, int(index0)))
    return min(MERIDIAN_BREAK_CHANCE_CAP, base + MERIDIAN_BREAK_RETRY_BONUS * max(0, int(attempts)))


def _ritual_cooldown_remaining(player, now: datetime | None = None) -> int:
    """Segundos até poder INICIAR o próximo ritual (0 = pronto). Conta do
    último canal ABERTO (o corpo assenta antes de forçar o próximo)."""
    opened = _opened_map(player)
    last: datetime | None = None
    for v in opened.values():
        dt = _parse_iso((v or {}).get("opened_at")) if isinstance(v, dict) else None
        if dt and (last is None or dt > last):
            last = dt
    if last is None:
        return 0
    now = now or _utcnow()
    ready = last + timedelta(hours=MERIDIAN_RITUAL_COOLDOWN_HOURS)
    return max(0, int((ready - now).total_seconds()))


# ══════════════════════════════════════════════════════════════════════════
# Refino ancorado em LUGAR — UM helper, duas superfícies + dois consumidores
# (a ação de temperar e a circulação do ritual)
# ══════════════════════════════════════════════════════════════════════════

async def refine_place_mult(session, player) -> dict[str, Any]:
    """A eficiência de refinar/temperar ONDE o jogador está:
      {mult, place_key ('cavern'|'site'|'road'), place_mult, festival_mult,
       site_key?, cavern_formation?}
    ``mult`` = place_mult × festival_mult (o MV-3 modula em cima — P3→P6).
    Flag OFF → neutro 1.0 SEM UMA query (byte-idêntico). Fail-safe → neutro."""
    neutral = {"mult": 1.0, "place_key": None, "place_mult": 1.0, "festival_mult": 1.0}
    try:
        if player is None or not corpo_profundo_on():
            return neutral
        now = _utcnow()
        cur = getattr(player, "current_continent", None) or "linghe"

        place_key = "road"
        place_mult = REFINE_MULT_ANYWHERE
        out: dict[str, Any] = {}

        # 🏯 Caverna própria: você NO continente dela + Formação VIVA no slot
        # (as Formações passam a SERVIR — Onda 5 Mig 114; slot expirado não
        # canaliza nada). PK lookup, barato.
        try:
            from database.models import PlayerCavern
            cavern = (await session.execute(
                select(PlayerCavern).where(PlayerCavern.player_id == int(player.telegram_id))
            )).scalar_one_or_none()
        except Exception:
            logger.exception("refine_place_mult cavern read failed")
            cavern = None
        if (cavern is not None and cavern.continent_key == cur
                and cavern.active_formation_id
                and cavern.formation_expires_at is not None
                and (cavern.formation_expires_at.replace(tzinfo=timezone.utc)
                     if cavern.formation_expires_at.tzinfo is None else cavern.formation_expires_at) > now):
            place_key = "cavern"
            place_mult = REFINE_MULT_CAVERN
            out["cavern_formation"] = int(cavern.active_formation_id)
        else:
            # ⛰️ Sítio de têmpera do continente atual (Sprint 6) — a linha de
            # base de hoje. Mòyǔ não tem sítio → estrada (disclosed).
            from core.environment_engine import local_site_key
            site = local_site_key(player)
            if site:
                place_key = "site"
                place_mult = REFINE_MULT_SITE
                out["site_key"] = site

        # 🏮 Festival do MV-3 modula EM CIMA (estados OFF → 1.0 sem query).
        festival_mult = 1.0
        try:
            from core.region_state_engine import region_overrides
            ov = await region_overrides(session, cur)
            festival_mult = float(ov.get("qi_tick_mult", 1.0) or 1.0)
        except Exception:
            logger.exception("refine_place_mult festival read failed")

        out.update({
            "mult": round(place_mult * festival_mult, 4),
            "place_key": place_key,
            "place_mult": place_mult,
            "festival_mult": festival_mult,
        })
        return out
    except Exception:
        logger.exception("refine_place_mult failed")
        return neutral


async def refine_place_view(session, player, lang: str) -> dict[str, Any] | None:
    """A linha de disclosure do lugar (Lei §1 — a tela de temperar DIZ onde
    você está e o que isso vale). Server-resolved ×2 superfícies. None com
    flag OFF (payload byte-idêntico)."""
    try:
        if not corpo_profundo_on():
            return None
        place = await refine_place_mult(session, player)
        from core.i18n import t as i18n_t
        pk = place.get("place_key")
        pct = abs(round((float(place.get("place_mult", 1.0)) - 1.0) * 100))
        if pk == "cavern":
            line = i18n_t(lang, "refino_place_cavern", pct=pct)
            emoji = "🏯"
        elif pk == "site":
            line = i18n_t(lang, "refino_place_site")
            emoji = "⛰️"
        else:
            line = i18n_t(lang, "refino_place_road", pct=pct)
            emoji = "🗺️"
        fest = float(place.get("festival_mult", 1.0) or 1.0)
        if fest > 1.0:
            line += " " + i18n_t(lang, "refino_place_festival", pct=abs(round((fest - 1.0) * 100)))
        return {**place, "emoji": emoji, "line": line}
    except Exception:
        logger.exception("refine_place_view failed")
        return None


# ══════════════════════════════════════════════════════════════════════════
# READ — a projeção para as duas superfícies (server-resolved)
# ══════════════════════════════════════════════════════════════════════════

def _ritual_map(player) -> dict | None:
    r = getattr(player, "meridian_ritual", None)
    return r if isinstance(r, dict) and r.get("channel") in _CHANNEL_INDEX else None


async def project_meridians(session, player, *, lang: str = "pt") -> dict[str, Any]:
    """O mapa dos 12 canais + o ritual em curso + o próximo passo, tudo
    server-resolved (nomes em mer_ch_<key> dos locales de CHAT — o mini-app
    não tem keys de canal próprias, padrão continentes). O caller gate a a
    flag; isto assume ON."""
    from core.i18n import t as i18n_t
    now = _utcnow()
    opened = _opened_map(player)
    ritual = _ritual_map(player)
    realm = int(getattr(player, "realm", 0) or 0)
    allowed = channels_allowed(realm)
    n_open = meridian_count(player)

    channels = []
    for ch in MERIDIAN_CHANNELS:
        key = ch["key"]
        state = "closed"
        opened_at_ms = None
        if key in opened:
            state = "open"
            dt = _parse_iso((opened[key] or {}).get("opened_at")) if isinstance(opened[key], dict) else None
            opened_at_ms = int(dt.timestamp() * 1000) if dt else None
        elif ritual and ritual.get("channel") == key:
            state = "ritual"
        channels.append({
            "key": key,
            "emoji": ch["emoji"],
            "group": ch["group"],
            "name": i18n_t(lang, f"mer_ch_{key}"),
            "state": state,
            "opened_at_ms": opened_at_ms,
        })

    out: dict[str, Any] = {
        "ok": True,
        "opened_count": n_open,
        "total": MERIDIAN_TOTAL,
        "allowed": allowed,
        "min_realm": MERIDIAN_MIN_REALM,
        "channels": channels,
        "all_open": n_open >= MERIDIAN_TOTAL,
        "durability_bonus_pct": round(meridian_durability_bonus(player) * 100, 1),
        "per_channel_pct": round(MERIDIAN_DURABILITY_PER_CHANNEL * 100, 1),
    }

    place = await refine_place_view(session, player, lang)
    if place:
        out["place"] = place

    if ritual:
        idx = _CHANNEL_INDEX[ritual["channel"]]
        ends = _parse_iso(ritual.get("ends_at"))
        ready = bool(ends and ends <= now)
        attempts = int(ritual.get("attempts", 0) or 0)
        out["ritual"] = {
            "channel": ritual["channel"],
            "name": i18n_t(lang, f"mer_ch_{ritual['channel']}"),
            "emoji": MERIDIAN_CHANNELS[idx]["emoji"],
            "ready": ready,
            "ends_at_ms": int(ends.timestamp() * 1000) if ends else None,
            "remaining_seconds": max(0, int((ends - now).total_seconds())) if ends else 0,
            "attempts": attempts,
            "chance_pct": round(break_chance(idx, attempts) * 100),
            # QoL 05/08 (report do [jogador]) — a MEMÓRIA da falha. O `+10pp` que cada
            # tentativa falhada acumula é uma PROGRESSÃO REAL, e vivia só num
            # toast que some: durante as horas de re-circulação o jogador não
            # via nem que falhou, nem que as chances subiram. Com a chance BASE
            # ao lado da atual, as duas superfícies dizem o antes→depois de
            # forma persistente ("subiu de 45% para 65%"), que é a lei da casa
            # para toda progressão. Sempre presente: é derivado, não condicional
            # a estado novo — e `attempts == 0` faz base == atual (nada a dizer).
            "base_chance_pct": round(break_chance(idx, 0) * 100),
        }
        return out

    # Sem ritual — o próximo passo, com custo honesto ANTES do commit (Lei §1).
    nxt = next_channel(player)
    if nxt is None:
        return out
    idx = _CHANNEL_INDEX[nxt["key"]]
    cost = channel_cost(idx, realm)
    cd = _ritual_cooldown_remaining(player, now)
    can = True
    reason = None
    if realm < MERIDIAN_MIN_REALM:
        can, reason = False, "mer_need_realm"
    elif n_open >= allowed:
        can, reason = False, "mer_realm_capped"
    elif cd > 0:
        can, reason = False, "mer_cooldown"
    elif int(getattr(player, "spirit_stones", 0) or 0) < cost["stones"]:
        can, reason = False, "mer_need_stones"
    elif int(getattr(player, "mortal_temper_progress", 0) or 0) < cost["progress"]:
        can, reason = False, "mer_need_progress"
    elif int(getattr(player, "hunt_essence", 0) or 0) < cost["essence"]:
        can, reason = False, "mer_need_essence"
    mult = float((place or {}).get("mult", 1.0) or 1.0)
    out["next"] = {
        "channel": nxt["key"],
        "name": i18n_t(lang, f"mer_ch_{nxt['key']}"),
        "emoji": nxt["emoji"],
        "cost": cost,
        "circulate_hours": round(circulate_hours(idx) / max(0.1, mult), 1),
        "chance_pct": round(break_chance(idx, 0) * 100),
        "can_start": can,
        "reason_key": reason,
        "cooldown_remaining": cd,
    }
    return out


# ══════════════════════════════════════════════════════════════════════════
# WRITE — o ritual (caller segura player FOR UPDATE + é dono do commit)
# ══════════════════════════════════════════════════════════════════════════

async def start_ritual(session, player) -> dict[str, Any]:
    """Etapas 1+2 — PREPARAR (debita pedras + progresso + essência, tudo
    all-or-nothing) e começar a CIRCULAR (sessão idle; duração ÷ mult do
    lugar, estampada AGORA — viajar depois não muda a sessão em curso).
    Revalida tudo; qualquer recusa é disclosed e não muta NADA."""
    if not corpo_profundo_on():
        return {"ok": False, "reason": "mer_locked"}
    if _ritual_map(player) is not None:
        return {"ok": False, "reason": "mer_ritual_active"}
    realm = int(getattr(player, "realm", 0) or 0)
    if realm < MERIDIAN_MIN_REALM:
        return {"ok": False, "reason": "mer_need_realm", "min_realm": MERIDIAN_MIN_REALM}
    nxt = next_channel(player)
    if nxt is None:
        return {"ok": False, "reason": "mer_all_open"}
    if meridian_count(player) >= channels_allowed(realm):
        return {"ok": False, "reason": "mer_realm_capped"}
    cd = _ritual_cooldown_remaining(player)
    if cd > 0:
        return {"ok": False, "reason": "mer_cooldown", "remaining_seconds": cd}

    idx = _CHANNEL_INDEX[nxt["key"]]
    cost = channel_cost(idx, realm)
    if int(getattr(player, "spirit_stones", 0) or 0) < cost["stones"]:
        return {"ok": False, "reason": "mer_need_stones", "cost": cost}
    if int(getattr(player, "mortal_temper_progress", 0) or 0) < cost["progress"]:
        return {"ok": False, "reason": "mer_need_progress", "cost": cost}
    if int(getattr(player, "hunt_essence", 0) or 0) < cost["essence"]:
        return {"ok": False, "reason": "mer_need_essence", "cost": cost}

    place = await refine_place_mult(session, player)
    mult = max(0.1, float(place.get("mult", 1.0) or 1.0))
    now = _utcnow()
    hours = circulate_hours(idx) / mult
    # MV-7 — 🩺 sinergia do Médico: circular −10% tempo. Fora do
    # refine_place_mult de propósito (aquele helper é compartilhado com o
    # temperar); gated (1.0 com flag OFF → byte-idêntico).
    try:
        from core.profession_engine import medic_circulate_mult
        hours *= float(medic_circulate_mult(player) or 1.0)
    except Exception:
        pass

    # Débito all-or-nothing (depois de TODAS as validações).
    player.spirit_stones = int(player.spirit_stones or 0) - cost["stones"]
    player.mortal_temper_progress = max(0, int(player.mortal_temper_progress or 0) - cost["progress"])
    player.hunt_essence = max(0, int(player.hunt_essence or 0) - cost["essence"])
    player.meridian_ritual = {
        "channel": nxt["key"],
        "stage": "circulate",
        "started_at": _iso(now),
        "ends_at": _iso(now + timedelta(hours=hours)),
        "place_key": place.get("place_key"),
        "place_mult": mult,
        "attempts": 0,
    }
    return {
        "ok": True,
        "channel": nxt["key"],
        "emoji": nxt["emoji"],
        "cost": cost,
        "circulate_hours": round(hours, 1),
        "ends_at_ms": int((now + timedelta(hours=hours)).timestamp() * 1000),
        "place_key": place.get("place_key"),
        "mult": mult,
        "chance_pct": round(break_chance(idx, 0) * 100),
    }


async def _is_first_open_on_server(session, channel: str, exclude_player_id: int) -> bool:
    """True se NENHUM OUTRO jogador deste mundo tem `channel` aberto (o 1º
    rompimento da era é um evento social — Chronicle). Exclui o próprio
    jogador porque a probe corre DEPOIS da mutação (autoflush veria o próprio
    row). jsonb_exists() em vez do operador `?` (driver-safe). Query rara
    (só no momento de um open). Fail-safe → False (sem Chronicle, nunca quebra).

    Review fix (MV-4): advisory lock transaction-scoped por canal ANTES da
    probe — dois rompimentos simultâneos do MESMO canal serializam, o segundo
    só proba depois do commit do primeiro (READ COMMITTED relê) e vê o row →
    UMA linha 'mer_first' por canal, nunca duas."""
    try:
        await session.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext('mer_first:' || :ch))"),
            {"ch": channel},
        )
        row = (await session.execute(
            _sql_text("SELECT 1 FROM players WHERE jsonb_exists(meridians_opened, :ch) "
                      "AND telegram_id != :me LIMIT 1"),
            {"ch": channel, "me": int(exclude_player_id)},
        )).scalar()
        return row is None
    except Exception:
        logger.debug("meridian first-open probe failed", exc_info=True)
        return False


async def attempt_break(session, player) -> dict[str, Any]:
    """Etapa 3 — o ROMPIMENTO. Exige a circulação completa. Chance honesta;
    FALHA = progresso parcial (bónus permanente na próxima tentativa + só
    re-circular, mais curto — nada do que foi pago se perde). SUCESSO = canal
    aberto com antes→depois VISÍVEL (HP/durabilidade via a Alma), notificação
    pessoal e Chronicle se for o 1º do servidor."""
    if not corpo_profundo_on():
        return {"ok": False, "reason": "mer_locked"}
    ritual = _ritual_map(player)
    if ritual is None:
        return {"ok": False, "reason": "mer_no_ritual"}
    now = _utcnow()
    ends = _parse_iso(ritual.get("ends_at"))
    if ends is None or ends > now:
        return {"ok": False, "reason": "mer_still_circulating",
                "remaining_seconds": max(0, int((ends - now).total_seconds())) if ends else 0}

    channel = ritual["channel"]
    idx = _CHANNEL_INDEX[channel]
    attempts = int(ritual.get("attempts", 0) or 0)
    chance = break_chance(idx, attempts)
    rng = random.Random()

    if rng.random() >= chance:
        # FALHA HONESTA — progresso parcial: +bónus permanente, re-circular
        # mais curto (o lugar é relido AGORA — mudar de lugar muda a espera).
        place = await refine_place_mult(session, player)
        mult = max(0.1, float(place.get("mult", 1.0) or 1.0))
        hours = circulate_hours(idx) * MERIDIAN_RETRY_FRACTION / mult
        # MV-7 — 🩺 sinergia do Médico também no re-circular da falha (os
        # DOIS call sites, senão o retry perde o bônus — recon MV-7).
        try:
            from core.profession_engine import medic_circulate_mult
            hours *= float(medic_circulate_mult(player) or 1.0)
        except Exception:
            pass
        new_attempts = attempts + 1
        player.meridian_ritual = {
            **ritual,
            "attempts": new_attempts,
            "ends_at": _iso(now + timedelta(hours=hours)),
            "place_key": place.get("place_key"),
            "place_mult": mult,
        }
        return {
            "ok": True,
            "opened": False,
            "channel": channel,
            "chance_pct": round(chance * 100),
            "next_chance_pct": round(break_chance(idx, new_attempts) * 100),
            "recirculate_hours": round(hours, 1),
            "ends_at_ms": int((now + timedelta(hours=hours)).timestamp() * 1000),
        }

    # SUCESSO — antes→depois VISÍVEL: o bónus folda na Alma
    # (body_durability_mult), então o delta de HP é real em toda superfície.
    try:
        from core.combat_engine import get_max_hp
        hp_before = float(get_max_hp(player))
    except Exception:
        hp_before = 0.0
    dur_before = meridian_durability_bonus(player)

    opened = dict(_opened_map(player))
    opened[channel] = {"opened_at": _iso(now), "attempts": attempts + 1}
    player.meridians_opened = opened          # reatribuição → dirty (JSONB)
    player.meridian_ritual = None
    n_open = meridian_count(player)

    try:
        from core.combat_engine import get_max_hp
        hp_after = float(get_max_hp(player))
    except Exception:
        hp_after = hp_before
    dur_after = meridian_durability_bonus(player)

    out: dict[str, Any] = {
        "ok": True,
        "opened": True,
        "channel": channel,
        "emoji": MERIDIAN_CHANNELS[idx]["emoji"],
        "opened_count": n_open,
        "total": MERIDIAN_TOTAL,
        "all_open": n_open >= MERIDIAN_TOTAL,
        "chance_pct": round(chance * 100),
        "hp_before": int(round(hp_before)),
        "hp_after": int(round(hp_after)),
        "hp_gain": int(round(hp_after - hp_before)),
        "durability_pct_before": round(dur_before * 100, 1),
        "durability_pct_after": round(dur_after * 100, 1),
    }

    # Notificação pessoal (lição MV-2: notif_* keys no CHAT i18n — o server
    # resolve). O nome do canal vai já resolvido na lang DO jogador (params
    # de notify são strings cruas). Best-effort, nunca derruba o open.
    try:
        from core.i18n import t as i18n_t
        from core.notification_engine import notify
        _lang = (getattr(player, "language", None) or "pt").lower()
        await notify(
            session, int(player.telegram_id), "meridian_open",
            title_key="notif_meridian_open_title",
            body_key="notif_meridian_open_body",
            payload={"name": i18n_t(_lang, f"mer_ch_{channel}"),
                     "n": n_open, "total": MERIDIAN_TOTAL},
            ref_id=f"mer:{channel}", icon="⛩️",
            target_tab="body_tempering", priority=3,
        )
    except Exception:
        logger.debug("meridian open notify failed", exc_info=True)

    # MV-5 §0 (dívida MV-4) — o título cosmético do 12/12: "🏮 Vaso Perfeito"
    # entra em unlocked_titles (o MESMO cofre do Pavilhão de Mérito/VIP/BP;
    # desc em EXTRA_TITLE_DESC_KEYS → title_desc_vaso_perfeito ×3). Idempotente
    # (dedupe por string) e retroativo por construção: o 12º open É o único
    # caminho até aqui. Best-effort — nunca derruba o open.
    try:
        if n_open >= MERIDIAN_TOTAL:
            titles = list(getattr(player, "unlocked_titles", None) or [])
            if MERIDIAN_TITLE_12 not in titles:
                titles.append(MERIDIAN_TITLE_12)
                player.unlocked_titles = titles  # reatribuição → dirty (JSONB)
                out["title_granted"] = MERIDIAN_TITLE_12
    except Exception:
        logger.debug("meridian 12/12 title grant failed", exc_info=True)

    # Chronicle — só o 1º rompimento DESTE canal no servidor (evento social).
    try:
        if await _is_first_open_on_server(session, channel, int(player.telegram_id)):
            from core.world_pulse_engine import emit_chronicle
            cont = getattr(player, "current_continent", None)
            await emit_chronicle(
                session, event_type="mer_first", text_key="mer_chron_first",
                continent_key=cont, importance=2, now=now,
            )
            out["first_on_server"] = True
    except Exception:
        logger.debug("meridian chronicle failed", exc_info=True)

    return out
