"""MV-5 Mundo Vivo v2 — Quests VIVAS: storylets/QBN.

O MV-1 deu geografia, o MV-2 movimento, o MV-3 consequência, o MV-4
profundidade ao corpo. O MV-5 dá VIDA ÀS QUESTS: pedaços de história com
``requirements`` JSONB declarativos (lugar, estado regional, evento ativo,
karma, path, reino, meridianos, flag) que só EXISTEM quando o mundo os torna
verdadeiros — oferecidos por encontros com NPC (praça / chegada de viagem /
explore) com diálogo → aceitar/recusar → uma seção "Quests aceitas" dinâmica.
A quest deixa de ser um checklist eterno e vira uma CONSEQUÊNCIA do mundo.

Tudo atrás da flag per-world ``quests_vivas`` (OFF por defeito → main
byte-idêntico; ver DEFAULT_WORLD_FEATURES em database/db.py).

Regras (padrão meridian_engine — tudo fail-safe, nada aqui quebra nada):
- Flag OFF → ``quests_vivas_on()`` False → TODA função é no-op sem UMA query.
- Progresso REUSA os trackers existentes: ``track_storylets`` é chamado
  aditivamente por ``quest_engine.track_quest`` (o chokepoint por onde TODO
  objective_type já passa — lição MV-1: nunca objetivo órfão).
- Recompensa NUNCA é concedida dentro do tracker (sessões alheias sem lock do
  player): o jogador RECLAMA (claim) com o row FOR UPDATE — padrão
  claim_quest_reward. O caller do claim segura ``player`` FOR UPDATE e é dono
  do commit (padrão claim_bounty/meridian).
- Expiry é LAZY (padrão WorldSectRecruiterPending): ``expires_at`` filtrado na
  leitura + flip honesto em ``sync_player_storylets`` (a expiração DIZ o que se
  perdeu — Lei §1). Storylet COMPLETA (progress ≥ count) NUNCA expira: a
  recompensa espera pelo jogador.
- O fork moral (proposta demoníaca) vive NA OFERTA: aceitar É a escolha, o
  karma vai no reward via apply_karma(delta_override) — recusar é livre e sem
  punição (Lei §1). O padrão qch_ (escolha no claim) fica com as quests.
- Pacer: 1 oferta aberta por jogador + cooldown STORYLET_OFFER_COOLDOWN_HOURS
  entre ofertas + janela anti-repetição STORYLET_REPEAT_DAYS por storylet.

Knobs: env ``STORYLET_*`` (engine, não DB — launch-server-ready, Lei §13).
"""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, text as _sql_text

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Flag + tuning (engine, não DB — env-overridable; padrão MERIDIAN_*/RST_*)
# ══════════════════════════════════════════════════════════════════════════

def quests_vivas_on(world_key: str | None = None) -> bool:
    """Gate estável da flag (padrão corpo_profundo_on). Fail-safe → False."""
    try:
        from database.db import feature_enabled_for_world
        return bool(feature_enabled_for_world("quests_vivas", world_key))
    except Exception:
        return False


# Pacer da oferta: 1 oferta aberta por vez + cooldown entre ofertas (conta da
# ÚLTIMA oferta feita, qualquer desfecho — recusar não acelera a próxima).
STORYLET_OFFER_COOLDOWN_HOURS = float(os.getenv("STORYLET_OFFER_COOLDOWN_HOURS", "12"))
# TTL da OFERTA em si (não respondida → expira lazy; o prazo da quest aceita
# vem de storylet_catalog.expires_hours, por storylet).
STORYLET_OFFER_TTL_HOURS = float(os.getenv("STORYLET_OFFER_TTL_HOURS", "24"))
# Janela anti-repetição: o mesmo storylet não re-oferece por N dias.
STORYLET_REPEAT_DAYS = int(os.getenv("STORYLET_REPEAT_DAYS", "7"))
# Chance do encontro raro no EXPLORE (por advance resolvido; o pacer morde em cima).
STORYLET_EXPLORE_CHANCE = float(os.getenv("STORYLET_EXPLORE_CHANCE", "0.10"))

_OPEN_STATUSES = ("offered", "accepted")
_GIVER_KINDS = ("npc_cultivator", "service_npc", "mendigo")


async def _rep_pacer_mods(session, player) -> dict:
    """MV-6 — os modificadores da rep no pacer (leitor gated do irmão; flag
    dele OFF → neutro sem query): {cooldown_hours: float|None, suppressed}.
    Reverência (≥50) acelera o chamado (12h→8h); desprezo (≤−25) cala os NPCs
    do continente (disclosed na praça — a linha de desprezo DIZ o porquê).
    Fail-safe → neutro. Consumido por maybe_offer E project_storylets (o
    timer disclosed nunca mente)."""
    try:
        from core.reputation_engine import offer_pacer_mods
        return await offer_pacer_mods(session, player)
    except Exception:
        logger.debug("storylet rep pacer mods failed", exc_info=True)
        return {"cooldown_hours": None, "suppressed": False}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ══════════════════════════════════════════════════════════════════════════
# Requirements (QBN — o coração): UM avaliador declarativo, AND entre presentes
# ══════════════════════════════════════════════════════════════════════════

# Keys que este engine sabe avaliar. Requirement desconhecido → FAIL-CLOSED
# (um seed futuro com requirement novo nunca oferece por engano).
_KNOWN_REQS = frozenset((
    "continent", "region_state", "world_event",
    "karma_min", "karma_max", "realm_min", "realm_max",
    "path", "meridians_min", "flag",
    "region_rep_min",  # MV-6 — rep local mínima (só um nome conhecido recebe)
))


async def _prefetch_world_ctx(session, player) -> dict[str, Any]:
    """Prefetch 1× do estado do mundo que os requirements leem (zero query nova
    por requirement): estado regional do continente atual + tipos de evento
    ativos nele. Leitores gated dos irmãos MV-2/MV-3 — flag deles OFF → neutro
    sem query. Fail-safe → neutro."""
    cont = getattr(player, "current_continent", None) or "linghe"
    ctx: dict[str, Any] = {"continent": cont, "region_state": "prospera", "events": set()}
    try:
        from core.region_state_engine import region_state
        ctx["region_state"] = await region_state(session, cont)
    except Exception:
        logger.debug("storylet ctx region_state failed", exc_info=True)
    try:
        from core.tiandao_engine import director_on
        if director_on():
            from database.models import WorldEvent
            rows = (await session.execute(
                select(WorldEvent.event_type).where(
                    WorldEvent.state == "active",
                    WorldEvent.continent_key == cont,
                    WorldEvent.expires_at > _utcnow(),
                )
            )).scalars().all()
            ctx["events"] = {str(r) for r in rows}
    except Exception:
        logger.debug("storylet ctx events failed", exc_info=True)
    # MV-6 — rep local para o requirement region_rep_min (leitor gated do
    # irmão: flag dele OFF → 0 sem query; o requirement nunca casa → o seed
    # que exige um nome conhecido fica mudo, fail-safe por construção).
    ctx["region_rep"] = 0
    try:
        from core.reputation_engine import get_region_rep
        ctx["region_rep"] = await get_region_rep(session, int(player.telegram_id), cont)
    except Exception:
        logger.debug("storylet ctx region_rep failed", exc_info=True)
    return ctx


def _matches(player, requirements: dict | None, ctx: dict[str, Any]) -> bool:
    """O avaliador puro: TODOS os requirements presentes têm de ser verdadeiros
    (AND). Puro sobre o player carregado + ctx prefetchado — zero queries."""
    req = requirements if isinstance(requirements, dict) else {}
    try:
        for k in req:
            if k not in _KNOWN_REQS:
                return False  # fail-closed: requirement desconhecido nunca oferece
        if "continent" in req:
            if ctx.get("continent") not in (req["continent"] or []):
                return False
        if "region_state" in req:
            if ctx.get("region_state") not in (req["region_state"] or []):
                return False
        if "world_event" in req:
            if req["world_event"] not in (ctx.get("events") or set()):
                return False
        karma = int(getattr(player, "karma", 0) or 0)
        if "karma_min" in req and karma < int(req["karma_min"]):
            return False
        if "karma_max" in req and karma > int(req["karma_max"]):
            return False
        realm = int(getattr(player, "realm", 0) or 0)
        if "realm_min" in req and realm < int(req["realm_min"]):
            return False
        if "realm_max" in req and realm > int(req["realm_max"]):
            return False
        if "path" in req:
            path = getattr(player, "path", None) or "rogue"
            if path not in (req["path"] or []):
                return False
        if "meridians_min" in req:
            from core.meridian_engine import meridian_count
            if meridian_count(player) < int(req["meridians_min"]):
                return False
        if "region_rep_min" in req:
            if int(ctx.get("region_rep", 0) or 0) < int(req["region_rep_min"]):
                return False
        if "flag" in req:
            from database.db import feature_enabled_for_world
            if not feature_enabled_for_world(str(req["flag"])):
                return False
        return True
    except Exception:
        logger.debug("storylet _matches failed", exc_info=True)
        return False


async def storylet_available(session, player, storylet) -> bool:
    """O avaliador do spec (§2): este storylet é verdadeiro para este jogador,
    AGORA? Prefetch 1× + avaliador puro. Flag OFF → False sem query."""
    if player is None or not quests_vivas_on():
        return False
    ctx = await _prefetch_world_ctx(session, player)
    return _matches(player, getattr(storylet, "requirements", None), ctx)


# ══════════════════════════════════════════════════════════════════════════
# Views (server-resolved ×2 superfícies — nomes/diálogos nos locales de CHAT)
# ══════════════════════════════════════════════════════════════════════════

def _reward_line(reward: dict | None, lang: str) -> str:
    """A recompensa como UMA linha honesta (Lei §1 — o jogador vê o que ganha
    ANTES de aceitar e o que perde quando expira)."""
    from core.i18n import t as i18n_t
    r = reward if isinstance(reward, dict) else {}
    parts: list[str] = []
    stones = int(r.get("stones", 0) or 0)
    if stones:
        parts.append(f"🪨 {stones}")
    karma = int(r.get("karma", 0) or 0)
    if karma:
        parts.append(i18n_t(lang, "sty_reward_karma", delta=f"{'+' if karma > 0 else '−'}{abs(karma)}"))
    herbs = sum(int(i.get("qty", 1) or 1) for i in (r.get("items") or [])
                if isinstance(i, dict) and i.get("type") == "herb")
    if herbs:
        parts.append(i18n_t(lang, "sty_reward_herbs", n=herbs))
    ores = sum(int(i.get("qty", 1) or 1) for i in (r.get("items") or [])
               if isinstance(i, dict) and i.get("type") == "ore")
    if ores:
        parts.append(i18n_t(lang, "sty_reward_ores", n=ores))
    return " · ".join(parts) if parts else "—"


# ══════════════════════════════════════════════════════════════════════════
# O OBJETIVO EM PALAVRAS — QoL-Feedback 07/08 (report do [jogador], Item C)
# ══════════════════════════════════════════════════════════════════════════
#
# *"'the furnace must not cool' quest — it is unclear what is required to be
#  done (?) … no clear indication where to go to complete it"*
#
# Ele tinha razão nas duas metades. As duas superfícies desenhavam
# `nome → desc (atmosfera) → barra → "0 / 3"` e o `objective_type` chegava ao
# payload e morria lá — **um contador sem substantivo**.
#
# ⚠️ CORREÇÃO do próprio diagnóstico (review adversarial): a primeira versão
# desta nota culpava também o diálogo do catálogo
# (`sty_enc_fenghuo_forja_d2`, "bata em alguma coisa até ela ficar quente
# outra vez" — combate, num encargo de FORJA). O texto era mesmo enganador e
# foi corrigido nas 3 línguas, **mas o jogador nunca o viu**: `d1`/`d2` só
# saem por `_offer_view` (abaixo), o pacer só sorteia `weight > 0` (:555) e os
# 15 encargos são semeados com `weight 0`, e `city_engine.accept_encargo`
# materializa a row já em `accepted` — logo um encargo nunca passa por
# `offered`. O que confundiu o [jogador] foi a AUSÊNCIA da linha de objetivo, não a
# presença de uma frase errada. A reescrita fica por ser forward-correct.
#
# A frase é resolvida AQUI, no servidor, e não em cada tela — pela mesma razão
# de sempre: a mesma quest tem de dizer a mesma coisa no chat e no mini
# (nenhuma tela recalcula). O estilo é copiado do que já existia para o Battle
# Pass (`bp_miss_forge_artifact` = "Forjar {value} artefato(s)"), não inventado.
#
# ⚠️ Mapa de enum ⇒ ele TEM de cobrir todo `objective_type` que uma seed possa
# usar, e degradar em silêncio (None) no que não conhecer — nunca imprimir uma
# key crua na cara do jogador. `_verify_*_i18n` e o teste desta onda batem
# `STORYLET_SEEDS` contra estas duas tabelas para o próximo tipo novo não
# repetir o defeito (é a enésima recorrência de "enum novo exige grep a TODOS
# os mapas").
_OBJ_EMOJI: dict[str, str] = {
    "cultivate":        "🧘",
    "craft_pill":       "⚗️",
    "use_pill":         "💊",
    "npc_combat":       "⚔️",
    "arena_win":        "🏟️",
    "dungeon_floor":    "🏛️",
    "beast_expedition": "🐾",
    "forge_artifact":   "⚒️",
}

# O ATALHO do chat (no mini o salto é o chip "→" da própria tela). Comandos
# reais, conferidos em main.py — nunca inventar um comando que não existe.
_OBJ_CHAT_CMD: dict[str, str] = {
    "cultivate":        "/meditar",
    "craft_pill":       "/alquimia",
    "use_pill":         "/inventario",
    "npc_combat":       "/combate",
    "arena_win":        "/arena",
    "dungeon_floor":    "/dungeons",
    "beast_expedition": "/bestiario",
    "forge_artifact":   "/forjar",
}


def objective_line(objective_type: str | None, count: int, lang: str) -> str | None:
    """*"⚒️ Forjar 3 artefatos"* — o objetivo DITO, server-resolved.

    None quando o tipo é desconhecido (a tela simplesmente não desenha a linha:
    Lei §1 prefere ausência a uma key crua). Nunca levanta."""
    try:
        tt = str(objective_type or "")
        if tt not in _OBJ_EMOJI:
            return None
        from core.i18n import t as i18n_t
        n = max(1, int(count or 1))
        return f"{_OBJ_EMOJI[tt]} {i18n_t(lang, f'sty_obj_{tt}', n=n)}"
    except Exception:
        logger.debug("objective_line failed type=%s", objective_type, exc_info=True)
        return None


def objective_chat_cmd(objective_type: str | None) -> str | None:
    """O comando de chat que leva ao lugar do objetivo (None se não houver)."""
    return _OBJ_CHAT_CMD.get(str(objective_type or "")) or None


def _giver_name(row_context: dict | None, giver_kind: str, lang: str) -> str:
    """Nome do giver: o nome REAL estampado no context (npc_cultivator local)
    ou o rótulo genérico do kind (sty_giver_<kind>)."""
    from core.i18n import t as i18n_t
    ctx = row_context if isinstance(row_context, dict) else {}
    name = ctx.get("giver_name")
    if name:
        return str(name)
    kind = giver_kind if giver_kind in _GIVER_KINDS else "npc_cultivator"
    return i18n_t(lang, f"sty_giver_{kind}")


def _offer_view(row, cat, lang: str, now: datetime | None = None) -> dict[str, Any]:
    """A projeção de UMA oferta aberta (diálogo incluído) — ambas superfícies."""
    from core.i18n import t as i18n_t
    now = now or _utcnow()
    exp = _aware(row.expires_at)
    return {
        "id": int(row.id),
        "key": row.storylet_key,
        "emoji": cat.emoji or "📜",
        "giver_kind": cat.giver_kind,
        "giver": _giver_name(row.context, cat.giver_kind, lang),
        "name": i18n_t(lang, f"sty_{row.storylet_key}_name"),
        "desc": i18n_t(lang, f"sty_{row.storylet_key}_desc"),
        "dialogue": [
            i18n_t(lang, f"sty_{row.storylet_key}_d1"),
            i18n_t(lang, f"sty_{row.storylet_key}_d2"),
        ],
        "objective_type": cat.objective_type,
        "objective_count": int(cat.objective_count or 1),
        # QoL 07/08 ([jogador]) — o objetivo DITO, não só contado. Aditivo: as telas
        # antigas ignoram a key e continuam byte-idênticas.
        "objective_line": objective_line(cat.objective_type, int(cat.objective_count or 1), lang),
        "objective_cmd": objective_chat_cmd(cat.objective_type),
        "deadline_hours": int(cat.expires_hours or 48),
        "reward_line": _reward_line(cat.reward, lang),
        "offer_expires_in": max(0, int((exp - now).total_seconds())) if exp else 0,
    }


def _accepted_view(row, cat, lang: str, now: datetime | None = None) -> dict[str, Any]:
    """A projeção de UMA quest aceita (a seção 'Quests aceitas')."""
    from core.i18n import t as i18n_t
    now = now or _utcnow()
    exp = _aware(row.expires_at)
    count = max(1, int(cat.objective_count or 1))
    progress = min(int(row.progress or 0), count)
    done = progress >= count
    return {
        "id": int(row.id),
        "key": row.storylet_key,
        "emoji": cat.emoji or "📜",
        "giver": _giver_name(row.context, cat.giver_kind, lang),
        "name": i18n_t(lang, f"sty_{row.storylet_key}_name"),
        "desc": i18n_t(lang, f"sty_{row.storylet_key}_desc"),
        "objective_type": cat.objective_type,
        "objective_count": count,
        "objective_line": objective_line(cat.objective_type, count, lang),
        "objective_cmd": objective_chat_cmd(cat.objective_type),
        "progress": progress,
        "is_completed": done,
        "reward_line": _reward_line(cat.reward, lang),
        # Prazo honesto: quest completa não expira (a recompensa espera).
        "expires_in": None if done else (max(0, int((exp - now).total_seconds())) if exp else None),
        "expires_at_ms": None if done else (int(exp.timestamp() * 1000) if exp else None),
    }


# ══════════════════════════════════════════════════════════════════════════
# Lazy expiry (padrão WorldSectRecruiterPending — sem sweep job)
# ══════════════════════════════════════════════════════════════════════════

async def sync_player_storylets(session, player_id: int) -> int:
    """Flip honesto das rows vencidas deste jogador: oferta não respondida →
    expired (silenciosa — a oferta é um convite, não um compromisso); quest
    aceita INCOMPLETA vencida → expired + notificação que DIZ o que se perdeu
    (Lei §1). Quest completa nunca expira. Chamado nos read-paths (padrão
    ensure_daily_quests — o caller é dono do commit). Devolve nº de flips."""
    if not quests_vivas_on():
        return 0
    try:
        from database.models import PlayerStorylet, StoryletCatalog
        now = _utcnow()
        rows = (await session.execute(
            select(PlayerStorylet, StoryletCatalog)
            .join(StoryletCatalog, StoryletCatalog.key == PlayerStorylet.storylet_key)
            .where(
                PlayerStorylet.player_id == int(player_id),
                PlayerStorylet.status.in_(_OPEN_STATUSES),
                PlayerStorylet.expires_at.is_not(None),
                PlayerStorylet.expires_at <= now,
            )
        )).all()
        flipped = 0
        for row, cat in rows:
            count = max(1, int(cat.objective_count or 1))
            if row.status == "accepted" and int(row.progress or 0) >= count:
                continue  # completa — a recompensa espera (Lei §1)
            was_accepted = row.status == "accepted"
            row.status = "expired"
            row.resolved_at = now
            flipped += 1
            if was_accepted:
                # A expiração DIZ o que se perdeu — nunca silent void.
                try:
                    from core.i18n import t as i18n_t
                    from core.notification_engine import notify
                    from database.models import Player
                    _lang = str((await session.execute(
                        select(Player.language).where(Player.telegram_id == int(player_id))
                    )).scalar() or "pt").lower()
                    await notify(
                        session, int(player_id), "storylet_expired",
                        title_key="notif_sty_expired_title",
                        body_key="notif_sty_expired_body",
                        payload={"name": i18n_t(_lang, f"sty_{row.storylet_key}_name"),
                                 "reward": _reward_line(cat.reward, _lang)},
                        ref_id=f"sty:{row.id}:exp", icon="⌛",
                        target_tab="quests", priority=4,
                    )
                except Exception:
                    logger.debug("storylet expiry notify failed", exc_info=True)
                # MV-6 — palavra dada e quebrada: o continente onde a quest
                # nasceu LEMBRA (−2 rep; o único faucet negativo — sem ele o
                # desprezo era inalcançável). Gancho aditivo gated (flag do
                # irmão OFF → None sem query); nunca derruba o sync.
                try:
                    from core.reputation_engine import REP_STORYLET_EXPIRED, add_region_rep
                    _cont = (row.context or {}).get("continent")
                    await add_region_rep(session, int(player_id), _cont,
                                         REP_STORYLET_EXPIRED, "storylet_expired")
                except Exception:
                    logger.debug("storylet expiry rep faucet failed", exc_info=True)
        return flipped
    except Exception:
        logger.exception("sync_player_storylets failed (player=%s)", player_id)
        return 0


# ══════════════════════════════════════════════════════════════════════════
# A OFERTA (o encontro vivo) — pacer + pick ponderado + notificação
# ══════════════════════════════════════════════════════════════════════════

async def maybe_offer(session, player, source: str = "plaza") -> dict[str, Any] | None:
    """Tenta MINTAR uma oferta para este jogador AGORA (praça / chegada de
    viagem / explore). Pacer: 1 oferta aberta + cooldown + anti-repetição.
    Flag OFF → None sem UMA query. Devolve a view da oferta nova (com diálogo)
    ou None. O caller é dono do commit. Best-effort — nunca levanta."""
    try:
        if player is None or not quests_vivas_on():
            return None
        from database.models import PlayerStorylet, StoryletCatalog
        now = _utcnow()
        pid = int(player.telegram_id)

        # Review fix (MV-5): o pacer inteiro é check-then-insert — sem
        # serialização, N requests concorrentes (praça×2, praça+viagem, etc.)
        # leriam o MESMO snapshot (zero ofertas, cooldown limpo) e mintariam N
        # ofertas pagáveis. Advisory lock transaction-scoped POR JOGADOR
        # (padrão mer_first/sty_first): o segundo mint bloqueia aqui, e quando
        # o primeiro commita, o re-read abaixo (READ COMMITTED) vê a oferta
        # nova → None. Belt-and-suspenders: índice único parcial na Mig 133
        # (1 row status='offered' por jogador) + savepoint no insert.
        await session.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext('sty_offer:' || :pid))"),
            {"pid": str(pid)},
        )

        # 1 query: rows abertas + histórico recente (pacer + anti-repetição).
        cutoff = now - timedelta(days=STORYLET_REPEAT_DAYS)
        recent = (await session.execute(
            select(PlayerStorylet).where(
                PlayerStorylet.player_id == pid,
                (PlayerStorylet.status.in_(_OPEN_STATUSES)) | (PlayerStorylet.offered_at >= cutoff),
            )
        )).scalars().all()

        # MV-9 — os ENCARGOS 城务 vivem nesta MESMA tabela mas NÃO são ofertas do
        # mundo: o jogador foi à cidade e assumiu um. `accept_encargo` grava a
        # row com `offered_at=now` (a coluna é NOT NULL), e sem esta exclusão
        # essa data virava "a última vez que o mundo te ofereceu algo" — assumir
        # um encargo SILENCIAVA todos os encontros de NPC por 12h, e a row ainda
        # entrava em `blocked_keys`. O pacer regula o que o MUNDO oferece.
        # Fail-safe: sem o engine das cidades, o set é vazio e nada muda.
        try:
            from core.city_engine import ENCARGO_KEYS as _ENC
            _enc_keys = frozenset(_ENC)
        except Exception:
            _enc_keys = frozenset()

        blocked_keys: set[str] = set()
        last_offered: datetime | None = None
        _freed = False
        for r in recent:
            if r.storylet_key in _enc_keys:
                continue   # encargo da cidade — nunca conta para o pacer
            off_at = _aware(r.offered_at)
            if off_at and (last_offered is None or off_at > last_offered):
                last_offered = off_at
            if r.status == "offered":
                if (_aware(r.expires_at) or now) > now:
                    return None  # já há uma oferta VIVA — 1 por vez
                # ⚠️ BUG DE PRODUÇÃO (s2, 2026-08-06): oferta VENCIDA mas ainda
                # com `status='offered'`. O teste acima só desistia da oferta
                # VIVA, então o fluxo seguia e tentava mintar — e o índice único
                # parcial `uq_player_storylets_open_offer` é sobre
                # `status='offered'` SEM olhar à validade. Resultado: uma row
                # vencida bloqueava TODO mint futuro daquele jogador, para
                # sempre, com IntegrityError a cada abertura da praça (medido:
                # 1 jogador em s2 sem receber UMA oferta desde 28/07, porque a
                # expiração é LAZY e só corre em `sync_player_storylets`, no
                # caminho de Missões — que ele nunca abria).
                # Flip honesto aqui, espelhando `sync_player_storylets`: a row
                # sai de 'offered', o índice liberta-se e o jogador volta a
                # existir para o mundo. Auto-curativo — não precisa de UPDATE
                # manual em produção.
                r.status = "expired"
                r.resolved_at = now
                _freed = True
            if r.status in _OPEN_STATUSES or (off_at and off_at >= cutoff):
                blocked_keys.add(r.storylet_key)
        if _freed:
            # O flush TEM de acontecer antes do INSERT: sem ele, a ordem em que
            # a unit-of-work emite UPDATE e INSERT não é garantida e o índice
            # ainda veria a row antiga como 'offered'.
            await session.flush()
        # MV-6 — a rep local modula o pacer: reverência acelera (12h→8h),
        # desprezo cala os NPCs (supressão disclosed via linha da praça).
        mods = await _rep_pacer_mods(session, player)
        if mods.get("suppressed"):
            return None  # ninguém se aproxima de um nome malvisto (Lei §1: a praça diz)
        cooldown_h = float(mods.get("cooldown_hours") or STORYLET_OFFER_COOLDOWN_HOURS)
        if last_offered and (now - last_offered) < timedelta(hours=cooldown_h):
            return None  # cooldown entre ofertas — o mundo não é um vending machine

        # O catálogo inteiro (16 rows — barato) + prefetch do mundo 1×.
        catalog = (await session.execute(
            select(StoryletCatalog).where(StoryletCatalog.is_active == True)  # noqa: E712
        )).scalars().all()
        if not catalog:
            return None
        ctx = await _prefetch_world_ctx(session, player)
        pool = [c for c in catalog
                if c.key not in blocked_keys
                and int(c.weight or 0) > 0
                and _matches(player, c.requirements, ctx)]
        if not pool:
            return None
        cat = random.choices(pool, weights=[int(c.weight or 1) for c in pool], k=1)[0]

        # O giver: um cultivador REAL da presença local (o encontro tem rosto);
        # service_npc/mendigo usam o rótulo do kind (sty_giver_*).
        context: dict[str, Any] = {
            "continent": ctx["continent"],
            "region_state": ctx["region_state"],
            "source": source,
        }
        if "world_event" in (cat.requirements or {}):
            context["world_event"] = (cat.requirements or {}).get("world_event")
        if cat.giver_kind == "npc_cultivator":
            try:
                from database.models import NpcCultivator
                npc_name = (await session.execute(
                    select(NpcCultivator.name).where(
                        NpcCultivator.status == "active",
                        NpcCultivator.continent_key == ctx["continent"],
                    ).order_by(func.random()).limit(1)
                )).scalar()
                if npc_name:
                    context["giver_name"] = str(npc_name)
            except Exception:
                logger.debug("storylet giver pick failed", exc_info=True)

        row = PlayerStorylet(
            player_id=pid,
            storylet_key=cat.key,
            status="offered",
            progress=0,
            context=context,
            offered_at=now,
            expires_at=now + timedelta(hours=STORYLET_OFFER_TTL_HOURS),
        )
        # SAVEPOINT no insert (review fix): se o índice único parcial disparar
        # (corrida que escapou ao lock — ex.: mundo sem a Mig por algum motivo
        # ter o lock desligado), o rollback é do savepoint, NUNCA da transação
        # do caller (a praça continua respondendo). O erro cai no except de
        # fora → mint devolve None, honesto.
        async with session.begin_nested():
            session.add(row)
            await session.flush()  # row.id para o ref_id/callback

        lang = (getattr(player, "language", None) or "pt").lower()
        view = _offer_view(row, cat, lang, now)

        # Notificação da oferta (lição MV-2: notif_* keys no CHAT i18n; o
        # target_tab "quests" MOSTRA a oferta — lição do dead-end de notif).
        try:
            from core.notification_engine import notify
            await notify(
                session, pid, "storylet_offer",
                title_key="notif_sty_offer_title",
                body_key="notif_sty_offer_body",
                payload={"giver": view["giver"], "name": view["name"]},
                ref_id=f"sty:{row.id}:offer", icon="📜",
                target_tab="quests", priority=3,
            )
        except Exception:
            logger.debug("storylet offer notify failed", exc_info=True)
        return view
    except Exception:
        logger.exception("maybe_offer failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return None


async def open_offer_view(session, player, lang: str) -> dict[str, Any] | None:
    """A oferta ABERTA atual deste jogador (não expirada), projetada — ou None.
    Flag OFF → None sem query."""
    if player is None or not quests_vivas_on():
        return None
    try:
        from database.models import PlayerStorylet, StoryletCatalog
        now = _utcnow()
        row = (await session.execute(
            select(PlayerStorylet, StoryletCatalog)
            .join(StoryletCatalog, StoryletCatalog.key == PlayerStorylet.storylet_key)
            .where(
                PlayerStorylet.player_id == int(player.telegram_id),
                PlayerStorylet.status == "offered",
                PlayerStorylet.expires_at > now,
            )
            .order_by(PlayerStorylet.offered_at.desc())
            .limit(1)
        )).first()
        if not row:
            return None
        return _offer_view(row[0], row[1], lang, now)
    except Exception:
        logger.debug("open_offer_view failed", exc_info=True)
        return None


async def respond_offer(session, player, storylet_id: int, accept: bool) -> dict[str, Any]:
    """Aceitar/recusar a oferta. Recusar = sem punição, cooldown normal (Lei
    §1). Aceitar = entra em 'Quests aceitas' com prazo honesto
    (expires_hours do catálogo). Idempotente: o row é lockado FOR UPDATE e o
    status re-validado. O caller é dono do commit."""
    if not quests_vivas_on():
        return {"ok": False, "reason": "sty_locked"}
    try:
        from database.models import PlayerStorylet, StoryletCatalog
        now = _utcnow()
        row = (await session.execute(
            select(PlayerStorylet).where(
                PlayerStorylet.id == int(storylet_id),
                PlayerStorylet.player_id == int(player.telegram_id),
            ).with_for_update()
        )).scalar_one_or_none()
        if row is None or row.status != "offered":
            return {"ok": False, "reason": "sty_offer_gone"}
        if (_aware(row.expires_at) or now) <= now:
            row.status = "expired"
            row.resolved_at = now
            return {"ok": False, "reason": "sty_offer_expired"}
        cat = await session.get(StoryletCatalog, row.storylet_key)
        if cat is None or not cat.is_active:
            row.status = "expired"
            row.resolved_at = now
            return {"ok": False, "reason": "sty_offer_gone"}

        lang = (getattr(player, "language", None) or "pt").lower()
        if not accept:
            row.status = "declined"
            row.resolved_at = now
            return {"ok": True, "declined": True}

        row.status = "accepted"
        row.accepted_at = now
        row.progress = 0
        row.expires_at = now + timedelta(hours=int(cat.expires_hours or 48))
        return {"ok": True, "accepted": True, "view": _accepted_view(row, cat, lang, now)}
    except Exception:
        logger.exception("respond_offer failed (player=%s, id=%s)",
                         getattr(player, "telegram_id", None), storylet_id)
        return {"ok": False, "reason": "internal_error"}


# ══════════════════════════════════════════════════════════════════════════
# Progresso — o gancho ÚNICO no tracker existente (track_quest chama isto)
# ══════════════════════════════════════════════════════════════════════════

# Review fix (MV-5): track_quest dispara em caminhos QUENTES (`login` = toda
# interação; `boss_damage` = todo ataque de boss) — sem prefiltro, cada evento
# pagaria 1 join query que devolve 0 rows. O set vem dos SEEDS (o catálogo é
# seed-synced a cada boot; convenção do projeto: conteúdo novo entra pelos
# seeds, nunca por SQL à mão — se algum dia entrar, o objective_type novo TEM
# de existir também nos seeds, senão o progresso não trackeia; documentado em
# Mecanicas/storylets.md). Falha do import → None = sem prefiltro (fail-open:
# uma query a mais é melhor que progresso silenciosamente morto).
_TRACKED_TYPES: frozenset | None = None
_TRACKED_TYPES_LOADED = False


def _tracked_types() -> frozenset | None:
    global _TRACKED_TYPES, _TRACKED_TYPES_LOADED
    if not _TRACKED_TYPES_LOADED:
        try:
            from database.seeds.storylet_seeds import STORYLET_SEEDS
            _TRACKED_TYPES = frozenset(str(s["objective_type"]) for s in STORYLET_SEEDS)
        except Exception:
            logger.exception("storylet tracked-types load failed (prefiltro OFF)")
            _TRACKED_TYPES = None
        _TRACKED_TYPES_LOADED = True
    return _TRACKED_TYPES


async def track_storylets(session, player_id: int, objective_type: str, amount: int = 1) -> None:
    """Gancho aditivo chamado por quest_engine.track_quest: TODO objective_type
    que já alimenta as quests alimenta os storylets aceitos — zero hooks novos,
    zero objetivos órfãos (lição MV-1). Flag OFF → return sem UMA query.
    NUNCA concede recompensa aqui (a sessão do caller pode não ter o player
    lockado) — só progresso + notificação de 'pronto'. Nunca levanta."""
    if not quests_vivas_on():
        return
    tt = _tracked_types()
    if tt is not None and str(objective_type) not in tt:
        return  # nenhum storylet usa este objetivo — zero query no hot path
    try:
        from database.models import PlayerStorylet, StoryletCatalog
        now = _utcnow()
        rows = (await session.execute(
            select(PlayerStorylet, StoryletCatalog)
            .join(StoryletCatalog, StoryletCatalog.key == PlayerStorylet.storylet_key)
            .where(
                PlayerStorylet.player_id == int(player_id),
                PlayerStorylet.status == "accepted",
                StoryletCatalog.objective_type == str(objective_type),
                StoryletCatalog.is_active == True,  # noqa: E712
            )
        )).all()
        for row, cat in rows:
            count = max(1, int(cat.objective_count or 1))
            if int(row.progress or 0) >= count:
                continue
            exp = _aware(row.expires_at)
            if exp and exp <= now:
                continue  # vencida — o sync fará o flip honesto; não acumula
            row.progress = min(int(row.progress or 0) + max(0, int(amount)), count)
            if row.progress >= count:
                try:
                    from core.i18n import t as i18n_t
                    from core.notification_engine import notify
                    from database.models import Player
                    _lang = (await session.execute(
                        select(Player.language).where(Player.telegram_id == int(player_id))
                    )).scalar() or "pt"
                    await notify(
                        session, int(player_id), "storylet_ready",
                        title_key="notif_sty_ready_title",
                        body_key="notif_sty_ready_body",
                        payload={"name": i18n_t(str(_lang).lower(), f"sty_{row.storylet_key}_name")},
                        ref_id=f"sty:{row.id}:ready", icon="📜",
                        target_tab="quests", priority=2,
                    )
                except Exception:
                    logger.debug("storylet ready notify failed", exc_info=True)
    except Exception:
        logger.exception("track_storylets failed (player=%s, type=%s)",
                         player_id, objective_type)


# ══════════════════════════════════════════════════════════════════════════
# CLAIM — recompensa row-locked (caller segura player FOR UPDATE + commit)
# ══════════════════════════════════════════════════════════════════════════

async def _is_first_done_on_server(session, storylet_key: str, exclude_id: int) -> bool:
    """True se NENHUM OUTRO row 'done' deste storylet existe no mundo — o 1º a
    concluir é um evento social (Chronicle). Advisory lock transaction-scoped
    por key ANTES da probe (padrão mer_first do MV-4: dois claims simultâneos
    serializam, o 2º proba após o commit do 1º → UMA linha, nunca duas).
    Exclui o próprio row (a probe corre DEPOIS da mutação). Fail-safe → False."""
    try:
        await session.execute(
            _sql_text("SELECT pg_advisory_xact_lock(hashtext('sty_first:' || :k))"),
            {"k": storylet_key},
        )
        row = (await session.execute(
            _sql_text("SELECT 1 FROM player_storylets WHERE storylet_key = :k "
                      "AND status = 'done' AND id != :me LIMIT 1"),
            {"k": storylet_key, "me": int(exclude_id)},
        )).scalar()
        return row is None
    except Exception:
        logger.debug("storylet first-done probe failed", exc_info=True)
        return False


async def claim_storylet(session, player, storylet_id: int) -> dict[str, Any]:
    """Concluir: concede a recompensa (pedras direto no player LOCKADO pelo
    caller; karma via apply_karma delta_override — SAVEPOINT próprio; itens
    nativos via add_item_to_inventory — bag cheia é DISCLOSED, não aborta,
    padrão apply_quest_choice) e marca 'done'. Idempotente pelo lock do row +
    re-check do status. Chronicle no 1º 'done' do servidor."""
    if not quests_vivas_on():
        return {"ok": False, "reason": "sty_locked"}
    try:
        from database.models import PlayerStorylet, StoryletCatalog
        now = _utcnow()
        row = (await session.execute(
            select(PlayerStorylet).where(
                PlayerStorylet.id == int(storylet_id),
                PlayerStorylet.player_id == int(player.telegram_id),
            ).with_for_update()
        )).scalar_one_or_none()
        if row is None or row.status != "accepted":
            return {"ok": False, "reason": "sty_nothing_to_claim"}
        cat = await session.get(StoryletCatalog, row.storylet_key)
        if cat is None:
            return {"ok": False, "reason": "sty_nothing_to_claim"}
        count = max(1, int(cat.objective_count or 1))
        if int(row.progress or 0) < count:
            return {"ok": False, "reason": "sty_not_done",
                    "progress": int(row.progress or 0), "count": count}

        reward = cat.reward if isinstance(cat.reward, dict) else {}
        out: dict[str, Any] = {"ok": True, "key": row.storylet_key, "emoji": cat.emoji or "📜"}

        stones = int(reward.get("stones", 0) or 0)
        if stones:
            player.spirit_stones = int(player.spirit_stones or 0) + stones
            out["stones"] = stones

        karma_delta = int(reward.get("karma", 0) or 0)
        if karma_delta:
            try:
                from core.karma_engine import apply_karma
                kr = await apply_karma(
                    session, int(player.telegram_id), "storylet_resolve",
                    metadata={"storylet_key": row.storylet_key, "row_id": int(row.id)},
                    delta_override=karma_delta,
                )
                if kr.get("ok"):
                    out["karma"] = {"delta": kr.get("delta", 0),
                                    "new_value": kr.get("new_value"),
                                    "label": kr.get("label")}
            except Exception:
                logger.exception("storylet karma failed (player=%s)", player.telegram_id)

        bag_full = False
        granted_items = 0
        for item in (reward.get("items") or []):
            if not isinstance(item, dict) or item.get("type") is None or item.get("id") is None:
                continue
            try:
                from core.utils import add_item_to_inventory
                ok = await add_item_to_inventory(
                    session, int(player.telegram_id),
                    str(item["type"]), int(item["id"]),
                    int(item.get("qty", 1) or 1),
                )
                if ok:
                    granted_items += int(item.get("qty", 1) or 1)
                else:
                    bag_full = True  # disclosed, não aborta (padrão apply_quest_choice)
            except Exception:
                logger.exception("storylet item grant failed (player=%s)", player.telegram_id)
        if granted_items:
            out["items"] = granted_items
        if bag_full:
            out["bag_full"] = True

        row.status = "done"
        row.resolved_at = now

        lang = (getattr(player, "language", None) or "pt").lower()
        out["name"] = _resolve_name(row.storylet_key, lang)
        out["reward_line"] = _reward_line(reward, lang)

        # MV-6 — o lugar LEMBRA: +rep no continente onde a quest NASCEU
        # (context — a quest lembra de onde veio; fallback presença). Gancho
        # aditivo gated (flag do irmão OFF → None sem query); antes→depois
        # ride no out (progressão visível).
        try:
            from core.reputation_engine import REP_STORYLET_DONE, add_region_rep
            _cont = (row.context or {}).get("continent") or getattr(player, "current_continent", None)
            _rep = await add_region_rep(session, int(player.telegram_id), _cont,
                                        REP_STORYLET_DONE, "storylet_done", lang=lang)
            if _rep:
                out["region_rep"] = _rep
        except Exception:
            logger.debug("storylet rep faucet failed", exc_info=True)

        # Chronicle — só o 1º 'done' DESTE storylet no servidor (evento social).
        try:
            if await _is_first_done_on_server(session, row.storylet_key, int(row.id)):
                from core.world_pulse_engine import emit_chronicle
                cont = (row.context or {}).get("continent") or getattr(player, "current_continent", None)
                await emit_chronicle(
                    session, event_type="sty_first", text_key="sty_chron_first",
                    continent_key=cont, importance=1, now=now,
                )
                out["first_on_server"] = True
        except Exception:
            logger.debug("storylet chronicle failed", exc_info=True)

        return out
    except Exception:
        logger.exception("claim_storylet failed (player=%s, id=%s)",
                         getattr(player, "telegram_id", None), storylet_id)
        return {"ok": False, "reason": "internal_error"}


def _resolve_name(storylet_key: str, lang: str) -> str:
    try:
        from core.i18n import t as i18n_t
        return i18n_t(lang, f"sty_{storylet_key}_name")
    except Exception:
        return storylet_key


# ══════════════════════════════════════════════════════════════════════════
# READ — a projeção para as duas superfícies
# ══════════════════════════════════════════════════════════════════════════

async def project_storylets(session, player, *, lang: str = "pt") -> dict[str, Any] | None:
    """A seção 'Quests aceitas' + a oferta aberta, server-resolved. Faz o sync
    lazy da expiração ANTES de projetar (padrão ensure_daily_quests — o caller
    é dono do commit). Flag OFF → None sem UMA query (payload byte-idêntico)."""
    if player is None or not quests_vivas_on():
        return None
    try:
        from database.models import PlayerStorylet, StoryletCatalog
        now = _utcnow()
        pid = int(player.telegram_id)
        await sync_player_storylets(session, pid)
        rows = (await session.execute(
            select(PlayerStorylet, StoryletCatalog)
            .join(StoryletCatalog, StoryletCatalog.key == PlayerStorylet.storylet_key)
            .where(
                PlayerStorylet.player_id == pid,
                PlayerStorylet.status.in_(_OPEN_STATUSES),
            )
            .order_by(PlayerStorylet.offered_at.asc())
        )).all()
        offer = None
        accepted: list[dict[str, Any]] = []
        last_offered: datetime | None = None
        for row, cat in rows:
            if row.status == "offered":
                offer = _offer_view(row, cat, lang, now)
            else:
                accepted.append(_accepted_view(row, cat, lang, now))
        # Disclosure honesta do pacer: quando o mundo pode voltar a chamar.
        try:
            last_offered = (await session.execute(
                select(func.max(PlayerStorylet.offered_at)).where(PlayerStorylet.player_id == pid)
            )).scalar()
        except Exception:
            last_offered = None
        next_in = 0
        lo = _aware(last_offered)
        if lo:
            # MV-6 — o MESMO override do maybe_offer (o timer disclosed nunca
            # mente): reverência 12h→8h. A supressão do desprezo não muda o
            # timer (a linha de desprezo da praça é a disclosure).
            mods = await _rep_pacer_mods(session, player)
            cooldown_h = float(mods.get("cooldown_hours") or STORYLET_OFFER_COOLDOWN_HOURS)
            ready_at = lo + timedelta(hours=cooldown_h)
            next_in = max(0, int((ready_at - now).total_seconds()))
        return {"ok": True, "offer": offer, "accepted": accepted,
                "next_offer_in": next_in}
    except Exception:
        logger.exception("project_storylets failed (player=%s)",
                         getattr(player, "telegram_id", None))
        return None
