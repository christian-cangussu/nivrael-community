"""Onda 3 — Heaven's Whispers (the world breathing).

A narrative broadcaster that makes the world feel ALIVE: NPC cultivators ascend,
beast tides roll across a continent, demonic energy breaches the frontier, the
Nine Houses seek disciples, ancient ruins surface. These atmospheric world-events
are written to a global feed (``heavens_whisper_log``) and delivered, sparingly,
to players' inboxes.

Two layers:
    * GENERATION (`generate_world_whispers`) — synthesizes new whispers from the
      current world state (the NPC-cultivator lifecycle + sect/continent flavour).
      One source feeds the Plaza / Explorable Realms / Rivalry that come next.
    * DELIVERY (`deliver_whispers`) — picks a whisper relevant to each eligible
      player (by continent / sect) and writes ONE inbox row, gated HARD against
      churn (Lei §1): `filter_recipients('whisper')` opt-out + a coarse daily
      ref_id so the notify() unique index caps it to one whisper per player per
      day + priority 8 (sorts last) + NO Telegram DM (atmospheric, in-app only).

Everything here is cosmetic/atmospheric — ZERO balance, wipe-safe. The feed and
the bell render server-side per the reader's language, so place/sect names are
localized correctly even though a whisper is global (params stay
language-neutral; localized names are merged in at render time).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from database.models import HeavensWhisperLog, NpcCultivator, Player
from core.continent_engine import CONTINENT_KEYS, CONTINENT_META, is_valid_continent
from core.world_sects_engine import WORLD_SECT_KEYS, WORLD_SECT_META, is_valid_sect

logger = logging.getLogger(__name__)


# ── Tuning (engine constants, wipe-safe) ──────────────────────────────────
WHISPER_FEED_TTL_HOURS = 72          # how long a whisper lingers in the feed
WHISPER_DELIVER_RECENT_HOURS = 36    # only deliver whispers fresher than this
WHISPER_DELIVER_ELIGIBLE_DAYS = 7    # only to players seen in the last week
WHISPER_DELIVER_MAX_PLAYERS = 400    # per-tick safety cap
WHISPERS_PER_GENERATION = 2          # new whispers synthesized per tick

# Spawn-able continents (Mòyǔ is demonic-locked — used only as an intrusion
# *target* flavour, never a recruiting/ruin host).
_OPEN_CONTINENTS = tuple(c for c in CONTINENT_KEYS if CONTINENT_META[c].get("spawn_allowed"))


# ── Theme catalog ─────────────────────────────────────────────────────────
# Each theme → its icon + i18n keys (CHAT locales; rendered server-side via
# core.i18n.t / str.format into both the feed and the bell). Bodies use distinct
# {placeholders} anyway — that keeps them safe for the mini-app t() too (the
# client resolver replaces only the FIRST occurrence; the verify script guards it).
WHISPER_THEMES: dict[str, dict[str, str]] = {
    "npc_ascension":     {"icon": "🌠", "title_key": "wsp_npc_ascension_title",     "body_key": "wsp_npc_ascension_body"},
    "beast_tide":        {"icon": "🐾", "title_key": "wsp_beast_tide_title",        "body_key": "wsp_beast_tide_body"},
    "demonic_intrusion": {"icon": "👹", "title_key": "wsp_demonic_intrusion_title", "body_key": "wsp_demonic_intrusion_body"},
    "sect_recruiting":   {"icon": "🏯", "title_key": "wsp_sect_recruiting_title",   "body_key": "wsp_sect_recruiting_body"},
    "ruin_discovered":   {"icon": "🏚️", "title_key": "wsp_ruin_discovered_title",   "body_key": "wsp_ruin_discovered_body"},
    # World Pulse Fase 1 — the loud (major) beats of the sect simulation get an
    # atmospheric whisper too (the chronicle carries the full detail incl. the
    # rival name; these stay {sect}/{place}-only so the shipped render path is
    # untouched). Minor beats (recruit/fortify) are chronicle-only — no whisper
    # spam (Director rhythm, not noise).
    "pulse_raid":        {"icon": "⚔️", "title_key": "wsp_pulse_raid_title",        "body_key": "wsp_pulse_raid_body"},
    "pulse_claim":       {"icon": "🚩", "title_key": "wsp_pulse_claim_title",       "body_key": "wsp_pulse_claim_body"},
    "pulse_inheritance": {"icon": "⚰️", "title_key": "wsp_pulse_inheritance_title", "body_key": "wsp_pulse_inheritance_body"},
    "pulse_strife":      {"icon": "🩸", "title_key": "wsp_pulse_strife_title",      "body_key": "wsp_pulse_strife_body"},
    # TEC-4 — a tumba REALMENTE abriu (a continuação do pulse_inheritance): a
    # Gruta do Legado 传承洞 está visitável em {place} por um prazo. Params
    # carregam {npc} (nome próprio, idêntico nas 3 línguas).
    "cave_open":         {"icon": "🏮", "title_key": "wsp_cave_open_title",         "body_key": "wsp_cave_open_body"},
}


# ── Localized-name merge (place/sect rendered per reader language) ─────────
def _localized_names(continent_key: str | None, sect_id: str | None, lang: str) -> dict[str, str]:
    from core.i18n import t as i18n_t
    place = ""
    if is_valid_continent(continent_key):
        place = i18n_t(lang, CONTINENT_META[continent_key]["name_key"])
    sect = ""
    if is_valid_sect(sect_id):
        sect = i18n_t(lang, WORLD_SECT_META[sect_id]["name_key"])
    return {"place": place, "sect": sect}


def render_whisper(row: HeavensWhisperLog, lang: str) -> dict[str, Any]:
    """Project a whisper row to ready strings for the feed (or a bell payload).
    Merges localized place/sect names into the language-neutral params."""
    from core.i18n import t as i18n_t
    params = dict(row.params or {})
    params.update(_localized_names(row.continent_key, row.sect_id, lang))
    created_ms = int(row.created_at.timestamp() * 1000) if row.created_at else None
    return {
        "id": int(row.id),
        "theme": row.theme,
        "icon": row.icon or "🌌",
        "title": i18n_t(lang, row.title_key, **params),
        "body": i18n_t(lang, row.body_key, **params),
        "created_at_ms": created_ms,
    }


# ── Emit + generate ────────────────────────────────────────────────────────
async def emit_whisper(
    session,
    theme: str,
    *,
    params: dict | None = None,
    continent_key: str | None = None,
    sect_id: str | None = None,
    expires_hours: int | None = WHISPER_FEED_TTL_HOURS,
) -> HeavensWhisperLog | None:
    """Append one whisper to the global feed. Best-effort, never raises. Other
    engines may call this directly when a real world-event happens (e.g. a sect
    join, an NPC ascension)."""
    spec = WHISPER_THEMES.get(theme)
    if spec is None:
        logger.debug("emit_whisper: unknown theme %s", theme)
        return None
    try:
        now = datetime.now(timezone.utc)
        row = HeavensWhisperLog(
            theme=theme,
            title_key=spec["title_key"],
            body_key=spec["body_key"],
            params=params or {},
            continent_key=continent_key if is_valid_continent(continent_key) else None,
            sect_id=sect_id if is_valid_sect(sect_id) else None,
            icon=spec["icon"],
            created_at=now,
            expires_at=(now + timedelta(hours=expires_hours)) if expires_hours else None,
        )
        session.add(row)
        await session.flush()
        return row
    except Exception:
        logger.exception("emit_whisper failed theme=%s", theme)
        return None


async def _whisper_npc_ascension(session, rng: random.Random) -> HeavensWhisperLog | None:
    """Lifecycle event: a high-realm NPC transcends and leaves the population.
    Marks it 'ascended' (the snapshot/bootstrap ticks refill), and broadcasts."""
    rows = (await session.execute(
        select(NpcCultivator)
        .where(NpcCultivator.status == "active", NpcCultivator.realm >= 4)
        .order_by(NpcCultivator.power.desc())
        .limit(15)
    )).scalars().all()
    if not rows:
        return None
    npc = rng.choice(rows)
    npc.status = "ascended"
    npc.updated_at = datetime.now(timezone.utc)
    return await emit_whisper(
        session, "npc_ascension",
        params={"name": npc.name},
        continent_key=npc.continent_key, sect_id=npc.sect_id,
    )


async def generate_world_whispers(session, *, n: int = WHISPERS_PER_GENERATION) -> list[HeavensWhisperLog]:
    """Synthesize up to ``n`` fresh whispers from current world state. Does NOT
    commit (the scheduler tick owns the commit)."""
    rng = random.Random()
    created: list[HeavensWhisperLog] = []
    themes = list(WHISPER_THEMES.keys())
    rng.shuffle(themes)
    for theme in themes:
        if len(created) >= n:
            break
        row = None
        try:
            if theme == "npc_ascension":
                # Rare — don't drain the population every tick.
                if rng.random() < 0.5:
                    row = await _whisper_npc_ascension(session, rng)
            elif theme == "beast_tide":
                row = await emit_whisper(session, "beast_tide",
                                         continent_key=rng.choice(_OPEN_CONTINENTS))
            elif theme == "demonic_intrusion":
                # Demons breach a righteous frontier (not their own Mòyǔ home).
                row = await emit_whisper(session, "demonic_intrusion",
                                         continent_key=rng.choice(_OPEN_CONTINENTS))
            elif theme == "sect_recruiting":
                sect_id = rng.choice(WORLD_SECT_KEYS)
                row = await emit_whisper(session, "sect_recruiting", sect_id=sect_id,
                                         continent_key=WORLD_SECT_META[sect_id]["continent_key"])
            elif theme == "ruin_discovered":
                row = await emit_whisper(session, "ruin_discovered",
                                         continent_key=rng.choice(_OPEN_CONTINENTS))
        except Exception:
            logger.debug("generate_world_whispers: theme %s failed", theme, exc_info=True)
        if row is not None:
            created.append(row)
    return created


# ── Feed (mini-app + chat) ─────────────────────────────────────────────────
async def list_recent_whispers(session, *, limit: int = 20, lang: str = "pt",
                               continent: str | None = None) -> list[dict[str, Any]]:
    """Recent, non-expired whispers projected for the feed (newest first).

    When ``continent`` is given (Onda 4a plaza feed) the feed is scoped to that
    continent — whispers tagged with it OR global whispers (``continent_key`` is
    NULL, e.g. ascensions/ruins with no place). Backwards-compatible: omit
    ``continent`` for the unscoped global feed (chat /sussurros, leaderboard)."""
    try:
        now = datetime.now(timezone.utc)
        stmt = (
            select(HeavensWhisperLog)
            .where(
                (HeavensWhisperLog.expires_at.is_(None)) | (HeavensWhisperLog.expires_at > now)
            )
        )
        if continent:
            stmt = stmt.where(
                (HeavensWhisperLog.continent_key == continent)
                | (HeavensWhisperLog.continent_key.is_(None))
            )
        rows = (await session.execute(
            stmt.order_by(HeavensWhisperLog.created_at.desc()).limit(int(limit))
        )).scalars().all()
        return [render_whisper(r, lang) for r in rows]
    except Exception:
        logger.exception("list_recent_whispers failed")
        return []


# ── Delivery (anti-churn, opt-out, daily-capped, in-app only) ──────────────
def _pick_relevant(whispers: list[HeavensWhisperLog], continent: str | None, sect_id: str | None,
                   rng: random.Random) -> HeavensWhisperLog | None:
    """Prefer a whisper about the player's continent or sect; else a random one."""
    if not whispers:
        return None
    relevant = [w for w in whispers
                if (continent and w.continent_key == continent) or (sect_id and w.sect_id == sect_id)]
    return rng.choice(relevant) if relevant else rng.choice(whispers)


async def deliver_whispers(session) -> int:
    """Write ONE inbox whisper to each eligible, opted-in player (anti-churn).
    Does NOT commit (the scheduler tick owns the commit). Returns rows written."""
    from core.notification_engine import notify
    from core.notification_prefs import filter_recipients

    rng = random.Random()
    now = datetime.now(timezone.utc)
    recent_cut = now - timedelta(hours=WHISPER_DELIVER_RECENT_HOURS)
    active_cut = now - timedelta(days=WHISPER_DELIVER_ELIGIBLE_DAYS)
    day_bucket = now.strftime("%Y%m%d")  # coarse ref_id ⇒ ≤1 whisper / player / day

    whispers = (await session.execute(
        select(HeavensWhisperLog)
        .where(HeavensWhisperLog.created_at >= recent_cut)
        .order_by(HeavensWhisperLog.created_at.desc())
        .limit(12)
    )).scalars().all()
    if not whispers:
        return 0

    players = (await session.execute(
        select(Player.telegram_id, Player.language, Player.current_continent, Player.sect_id)
        .where(Player.last_online >= active_cut)
        .limit(WHISPER_DELIVER_MAX_PLAYERS)
    )).all()
    if not players:
        return 0

    candidate_ids = [int(p[0]) for p in players]
    try:
        allowed = await filter_recipients(session, candidate_ids, "whisper")
    except Exception:
        # Fail CLOSED (Lei §1 anti-churn): if the opt-out gate can't be read,
        # skip this tick entirely rather than spam players who muted whispers.
        # A whisper is atmospheric — losing one 6h tick is harmless; the next
        # tick retries. Delivering to a muted player is NOT acceptable.
        logger.debug("deliver_whispers: filter_recipients failed — skipping tick", exc_info=True)
        return 0

    written = 0
    for pid, lang, continent, sect_id in players:
        if int(pid) not in allowed:
            continue
        nlang = (lang or "pt").lower()
        if nlang not in ("pt", "en", "es"):
            nlang = "pt"
        w = _pick_relevant(whispers, continent, sect_id, rng)
        if w is None:
            continue
        # Localize place/sect for THIS reader (params stay language-neutral on the
        # row; we merge the localized names into this player's notif payload).
        payload = dict(w.params or {})
        payload.update(_localized_names(w.continent_key, w.sect_id, nlang))
        try:
            row = await notify(
                session, int(pid), "whisper",
                title_key=w.title_key, body_key=w.body_key, payload=payload,
                ref_id=f"whisper:{day_bucket}",  # daily dedup ⇒ anti-churn
                icon=w.icon or "🌌", target_tab="whispers", priority=8,
            )
            if row is not None:
                written += 1
        except Exception:
            logger.debug("deliver_whispers: notify failed for %s", pid, exc_info=True)
    return written
