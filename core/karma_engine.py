"""v16.3 — Karma Spine (Pillar 4 of the v16 Living World).

The silent stat that defines the cultivator's Path. Karma never policies
the path: it *derives* it. Every righteous act nudges the score up; every
forbidden act drags it down. When the cultivator reaches Core Formation
(R3) the karma engine reads the accumulated score and crystallizes the
Path (Righteous / Demonic / Rogue) automatically. There is no menu, no
picker, no choice prompt — the Dao watches what the cultivator DOES.

Where this lives in the v16 stack
=================================
This engine is the **driver** for the Path system. v16.2 built the path
table + meta + display surfaces; v16.2.1 stripped the picker and turned
PathModal read-only; v16.3 wires the actual mover:

    apply_karma  ──→  clamp to [-1000, +1000]
                 ──→  audit row in karma_log
                 ──→  crystallize_path_for_player (if R3+ and NULL)
                                     │
                                     └──→ path_engine.set_player_path
                                          (internal-only after v16.3)
                                                  │
                                                  └──→ achievement bus
                                                       event `path_chosen`

Post-crystallization, if karma drifts far from the path alignment (a
Righteous cultivator drowning in malice, or a Demonic one finding
compassion) the engine *notifies* — it never auto-flips. The player gets
a Heart Demon DM with 72h grace; the divergence quest itself lives in
v16.7 Forbidden Path. Lei §1 honest disclosure: the path you walked is
yours; the Heavens warn before they judge.

Tribulation severity also feeds from |karma|. Cultivators heavy with
karmic weight — saint or demon, the Dao does not care — face harsher
heavenly trials. Plugged in tribulation_engine via :func:`get_tribulation_modifier`.

Architecture mirrors :mod:`core.path_engine` and :mod:`core.intent_engine`:
    • Constants block at the top (events, thresholds, labels).
    • Pure helper functions for derivation / lookup / display.
    • One mutator (`apply_karma`) wrapped in `session.begin_nested()`
      SAVEPOINT so a karma write failure can never poison the outer
      transaction (combat/quest/dungeon callers stay safe).
    • Defensive try/except on every caller-facing helper — a karma engine
      crash must NEVER take down combat, cultivation, or breakthroughs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: F401  (reserved for v16.10)

from database.models import KarmaLog, Player

logger = logging.getLogger(__name__)


# ── Bounds + thresholds ───────────────────────────────────────────────────────

KARMA_MIN: int = -1000
KARMA_MAX: int = 1000
KARMA_BOUNDS: tuple[int, int] = (KARMA_MIN, KARMA_MAX)

# Path derivation thresholds for the R3 crystallization moment.
#
# Net karma at R3:
#   >= +250  → Righteous (the cultivator has earned the trust of the 8 sects)
#   <= -250  → Demonic   (the abyss has answered the calls)
#   between  → Rogue     (no clear alignment — the freelancer's path)
#
# The window |karma| < 250 is intentional. At R3 (Core Formation) the
# average player has accumulated dozens of events; a +/- 100 karma is
# easy to drift through normal play. 250 forces a deliberate moral arc.
KARMA_PATH_THRESHOLDS: dict[str, int] = {
    "righteous": 250,
    "demonic": -250,
}

# Post-crystallization divergence triggers (Heart Demon DM only — never
# auto-flip the path). The numbers are deliberately further from zero
# than the crystallization thresholds: a Righteous cultivator can drift
# down to -200 without alarm; the heavens only step in past -500.
KARMA_DIVERGENCE_THRESHOLDS: dict[str, int] = {
    "righteous": -500,  # Righteous + karma <= -500 → Heart Demon
    "demonic": +500,    # Demonic   + karma >= +500 → Heart Demon
    # Rogue has no divergence — neutrality is, by definition, never wrong.
}

# Hours of grace between divergence DM and the Heart Demon quest's
# narrative consequences (v16.7 wires the actual quest; v16.3 only
# schedules the notification + reserves the window).
KARMA_DIVERGENCE_GRACE_HOURS: int = 72


# ── Canon karma events ────────────────────────────────────────────────────────

# Every karma-mutating event must use a key from this dict. The deltas
# are deliberately scaled so a player following the canon naturally
# accumulates enough to crystallize by R3 without needing to grind:
#
#   • +25 (saint quest complete) × 10 = +250  → Righteous threshold
#   • -25 (abyssal quest complete) × 10 = -250 → Demonic threshold
#   • Smaller events (+/-1 to +/-5) are the "slow drift" karma —
#     meditation void, honest trades, qi deviation recover.
#   • Catastrophic events (-100 soul devour, -75 betray sect) are the
#     "fork in the road" karma — single act, lasting consequence.
#
# Owner has carte-blanche to tweak any value pre-launch (Lei §6 — owner
# override stands). The semantics are stable; only magnitudes flex.
KARMA_EVENTS: dict[str, int] = {
    # ── Righteous side ───────────────────────────────────
    "saint_quest_complete":     +25,   # v16.3.5 moral quest engine
    "sect_donate_contribution":  +5,   # per donation event (caller filters by amount)
    "heal_ally_combat":          +2,   # passive partner-assist in PvE
    "tribulation_survive":      +10,   # passing a heavenly trial
    "rogue_kill_demonic":       +30,   # slaying a Demonic NPC encounter
    "rescue_npc":               +20,   # rescue/spare quest beats
    "honest_market_trade":       +1,   # fixed-price market sale
    # ── Demonic side ─────────────────────────────────────
    "forbidden_tech_use":       -20,   # per use (v16.7 wires the consumer)
    "kill_righteous_player":    -50,   # PvP/PvE Demonic-side kill of a Righteous target
    "soul_devour_event":       -100,   # the cardinal Demonic sin (v16.7+)
    "abyssal_quest_complete":   -25,   # v16.3.5 demonic quest line
    "steal_technique":          -15,   # forbidden acquisition path
    "betray_sect_oath":         -75,   # leaving a sect under specific conditions
    # ── Neutral / context ────────────────────────────────
    "dao_meditation_void":       +1,   # rare void-mode meditation tick
    "qi_deviation_recover":      -5,   # surviving qi deviation leaves a stain
    "tribulation_fail":         -10,   # failed trials breed resentment
    # ── Onda 3 — combat outcome moral fork (spare vs execute a defeated foe).
    # Conservative magnitudes (balance-sensitive — touches paying players'
    # karma/path): ~25 mercies cross the ±250 path-crystallization line, so a
    # single fight never flips identity, but a pattern of cruelty/mercy defines
    # you over time ("os teus actos definem quem és"). Disclosed in the
    # KarmaModal via get_canonical_events_for_display (Lei §1).
    "combat_spare":             +10,   # mercy on a defeated NPC cultivator
    "combat_execute":           -10,   # executing/humiliating a defeated foe
}


# ── Karma labels (5 bands, mapped to colors/emoji in the UI) ──────────────────

# Bands are intentionally wider than the path thresholds — most players
# spend their lives in "Neutral" or one step toward their alignment.
# "Saint" / "Demonic" are the spiritual extremes, reached only by the
# committed few. Each band has an emoji + color tone consumed by both
# chat (/status, /karma) and miniapp (KarmaModal gauge).
KARMA_LABEL_BANDS: list[tuple[int, int, str]] = [
    # (min_inclusive, max_inclusive, label_key)
    (KARMA_MIN, -500, "demonic"),
    (-499, -100, "tainted"),
    (-99, 99, "neutral"),
    (100, 499, "pure"),
    (500, KARMA_MAX, "saint"),
]

KARMA_LABEL_EMOJI: dict[str, str] = {
    "saint":   "✨",
    "pure":    "☀️",
    "neutral": "☯️",
    "tainted": "🌑",
    "demonic": "👹",
}


# ── Pure helpers (no DB) ──────────────────────────────────────────────────────

def _clamp_karma(value: int) -> int:
    """Clamp ``value`` into ``KARMA_BOUNDS``. Pure function."""
    if value < KARMA_MIN:
        return KARMA_MIN
    if value > KARMA_MAX:
        return KARMA_MAX
    return value


def get_karma_label(karma: int) -> str:
    """Return the band label key for a karma value.

    The five bands (demonic / tainted / neutral / pure / saint) drive
    both the chat /status line emoji and the miniapp KarmaModal gauge
    color. Pure function — safe to call from anywhere.
    """
    for low, high, key in KARMA_LABEL_BANDS:
        if low <= karma <= high:
            return key
    # Defensive: should be unreachable given clamp, but never crash on
    # an unexpected out-of-range value.
    return "neutral"


def get_karma_emoji(karma: int) -> str:
    """Return the emoji glyph paired with the band label."""
    return KARMA_LABEL_EMOJI.get(get_karma_label(karma), "☯️")


def derive_path_from_karma(karma: int) -> str:
    """Pure helper: given a karma value, return the canonical Path key.

    Used by :func:`crystallize_path_for_player` at R3 to lock in the
    cultivator's alignment. Thresholds live in :data:`KARMA_PATH_THRESHOLDS`.

    Mapping:
        karma >= +250  → 'righteous'
        karma <= -250  → 'demonic'
        otherwise      → 'rogue'  (the neutral default)
    """
    if karma >= KARMA_PATH_THRESHOLDS["righteous"]:
        return "righteous"
    if karma <= KARMA_PATH_THRESHOLDS["demonic"]:
        return "demonic"
    return "rogue"


async def rebirth_path_preview(session, player, lang: str = "pt") -> str | None:
    """A linha do CAMINHO no aviso de renascer — antes→depois, ANTES do tap.

    Molde literal: `dungeon_regions.rebirth_portal_warning` (QoL 09/08), pelo
    mesmo motivo — renascer é irreversível, logo tudo o que ele muda tem de
    estar escrito na tela do botão (Lei §1) e com o valor de antes e o de
    depois (Lei §10).

    Desde 2026-08-14 (pergunta do [jogador]) o renascimento RE-DERIVA o Caminho a
    partir do karma que a alma carrega. Sem esta linha, um cultivador justo com
    o karma afundado renasceria demoníaco **de surpresa** — e uma surpresa
    irreversível é pior do que o dead-end que se estava a corrigir.

    Devolve None quando o caminho NÃO muda (a esmagadora maioria: o karma
    atravessa o renascimento, logo quem não mudou de vida moral mantém-se).
    Nunca levanta.
    """
    try:
        from core.path_engine import PATH_META, is_valid_path
        from core.i18n import t as i18n_t
        cur = getattr(player, "path", None)
        karma = int(getattr(player, "karma", 0) or 0)
        nxt = derive_path_from_karma(karma)
        if not is_valid_path(cur) or nxt == cur:
            return None
        cm, nm = PATH_META[cur], PATH_META[nxt]
        return i18n_t(
            lang, "prestige_path_change",
            from_emoji=cm["emoji"], from_name=i18n_t(lang, cm["name_key"]),
            to_emoji=nm["emoji"], to_name=i18n_t(lang, nm["name_key"]),
            karma=karma,
        )
    except Exception:
        logger.debug("rebirth_path_preview failed", exc_info=True)
        return None


def get_tribulation_modifier(karma_abs: int) -> float:
    """Return the severity multiplier the tribulation engine should apply.

    Cultivators heavy with karma — saint or demon, the heavens do not
    discriminate — face harsher trials. The breakpoints are tuned so a
    neutral player feels no change (1.0×); a Saint at +900 or a Demon at
    -900 faces triple-strength heavens.

    Pure function. Defensive against negative inputs (callers may pass
    raw karma; we abs() ourselves).
    """
    karma_abs = abs(int(karma_abs or 0))
    if karma_abs >= 900:
        return 3.0
    if karma_abs >= 750:
        return 2.0
    if karma_abs >= 500:
        return 1.5
    return 1.0


def get_karma_event_delta(event_type: str) -> int:
    """Return the canonical delta for ``event_type``. 0 if unknown.

    Callers should generally let :func:`apply_karma` look this up rather
    than pre-computing — but the lookup is exposed for previews (e.g. the
    KarmaModal "What changes my karma?" expandable list).
    """
    return int(KARMA_EVENTS.get(event_type, 0))


# ── Player accessors (single-row reads) ───────────────────────────────────────

async def get_karma(session, player_id: int) -> int:
    """Return the current karma for ``player_id``. Defensive — 0 on any error.

    Used by the chat /status line, /karma sub-menu, and tribulation
    engine. Never raises; an unexpected DB failure logs at debug and
    returns 0 so callers can keep rendering.
    """
    try:
        row = (await session.execute(
            select(Player.karma).where(Player.telegram_id == player_id)
        )).first()
    except Exception:
        logger.debug("get_karma failed for player_id=%s", player_id, exc_info=True)
        return 0
    if not row:
        return 0
    return int(row[0] or 0)


async def get_recent_karma_events(
    session, player_id: int, limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the most recent karma events for ``player_id``.

    Used by the KarmaModal recent events log and the chat /karma history
    view. Each entry: ``{id, delta, new_value, event_type, metadata,
    created_at_ms}``. Returns an empty list on any error (defensive).
    """
    try:
        rows = (await session.execute(
            select(KarmaLog)
            .where(KarmaLog.player_id == player_id)
            .order_by(desc(KarmaLog.created_at))
            .limit(int(max(1, limit)))
        )).scalars().all()
    except Exception:
        logger.debug("get_recent_karma_events failed for player_id=%s", player_id, exc_info=True)
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        created = row.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        # KarmaLog.metadata_ → DB column `metadata` (SQLAlchemy reserved
        # attr workaround). Returned to clients as plain `metadata`.
        meta = getattr(row, "metadata_", None)
        out.append({
            "id": int(row.id),
            "delta": int(row.delta or 0),
            "new_value": int(row.new_value or 0),
            "event_type": row.event_type or "",
            "metadata": dict(meta) if meta else None,
            "created_at_ms": int(created.timestamp() * 1000) if created else None,
        })
    return out


# ── Path crystallization ──────────────────────────────────────────────────────

async def crystallize_path_for_player(
    session, player_id: int, *, source: str = "karma_threshold",
) -> dict[str, Any] | None:
    """Derive the player's Path from current karma and persist it.

    Called automatically by :func:`apply_karma` whenever:
        • player has reached :data:`path_engine.PATH_PICK_MIN_REALM`
          (Core Formation, R3) AND
        • Player.path column is still NULL ("never crystallized").

    Also callable directly by the breakthrough handler the moment a
    cultivator first hits R3 — that's the canonical crystallization
    moment ("at Core Formation, the river crystallizes"). Re-fires on a
    NULL path are no-ops (set_player_path returns `path_already_set`).

    Returns:
        ``{ok: True, path: 'righteous'|'demonic'|'rogue', karma: int,
            source: str}`` on success;
        ``{ok: False, reason: str, ...}`` on rejection;
        ``None`` if there was no player to crystallize.

    Internally calls :func:`path_engine.set_player_path`, which is the
    sole writer for ``Player.path`` post-v16.3. The mini-app picker UI
    was retired in v16.2.1 and the public endpoint became a 410 dead-
    route at the same time — this function is now the only legitimate
    path of mutation.
    """
    from core.path_engine import (
        PATH_PICK_MIN_REALM,
        is_valid_path,
        set_player_path,
    )

    try:
        player = (await session.execute(
            select(Player).where(Player.telegram_id == player_id)
        )).scalar_one_or_none()
    except Exception:
        logger.debug("crystallize lookup failed for player_id=%s", player_id, exc_info=True)
        return None
    if player is None:
        return None

    realm = int(player.realm or 0)
    if realm < PATH_PICK_MIN_REALM:
        return {"ok": False, "reason": "realm_too_low",
                "required_realm": PATH_PICK_MIN_REALM, "current_realm": realm}

    if is_valid_path(player.path):
        # One-shot crystallization (Lei §3 — depth, not variety). Re-firing
        # is a no-op; v16.7 Forbidden Path will introduce the Heart Demon
        # quest as the narrative re-derivation channel.
        return {"ok": False, "reason": "path_already_set", "current": player.path}

    karma_value = int(player.karma or 0)
    derived = derive_path_from_karma(karma_value)

    try:
        res = await set_player_path(session, player_id, derived)
    except Exception:
        logger.exception(
            "set_player_path crashed in crystallization (player_id=%s, derived=%s)",
            player_id, derived,
        )
        return {"ok": False, "reason": "internal_error"}

    if not res.get("ok"):
        # Engine rejected (e.g. realm gate). Pass through with the karma
        # context so the caller can log it.
        return {**res, "karma_at_crystallization": karma_value}

    # QoL-Feedback 2 2026-07-30 (report [jogador] s2): o card "cristalizou com
    # karma {value}" do PathModal lia o KarmaLog mais RECENTE — karma ATUAL
    # rotulado como o do momento da cristalização (display-lie). Persistir o
    # snapshot AQUI (zero migration — é uma linha de KarmaLog com delta 0);
    # o endpoint passa a preferir esta linha e, sem ela (cristalizações
    # antigas), o card se cala em vez de mentir (Lei §1).
    try:
        session.add(KarmaLog(
            player_id=player_id,
            delta=0,
            new_value=karma_value,
            event_type="path_crystallized",
            metadata_={"path": derived, "source": source},
        ))
    except Exception:
        logger.exception("path_crystallized snapshot log failed (player_id=%s)", player_id)

    # Fire the achievement event bus. `path_chosen` is the same trigger
    # the v16.2 catalog row was seeded with; v16.3 only activates the
    # actual write hook. Retroactive grant for the ~57 beta players
    # whose `path` was backfilled by Migration 102 is handled in
    # ``sync_player_snapshot``.
    try:
        from core.achievement_engine import check_achievements
        await check_achievements(session, player_id, "path_chosen", 1)
    except Exception:
        logger.exception(
            "path_chosen achievement bus failed (player_id=%s)", player_id,
        )

    logger.info(
        "path_crystallized: player_id=%s path=%s karma=%s source=%s",
        player_id, derived, karma_value, source,
    )
    return {
        "ok": True,
        "path": derived,
        "karma_at_crystallization": karma_value,
        "source": source,
    }


# ── Divergence checks (post-crystallization Heart Demon trigger) ──────────────

def _divergence_for_path_and_karma(path: str | None, karma: int) -> dict[str, Any]:
    """Pure check: does ``karma`` diverge from ``path`` alignment?

    Returns ``{diverged: bool, threshold: int|None}``. Rogue never
    diverges (neutral by canon). Invalid paths never diverge.
    """
    if not isinstance(path, str):
        return {"diverged": False, "threshold": None}
    if path == "righteous":
        thr = KARMA_DIVERGENCE_THRESHOLDS["righteous"]
        return {"diverged": karma <= thr, "threshold": thr}
    if path == "demonic":
        thr = KARMA_DIVERGENCE_THRESHOLDS["demonic"]
        return {"diverged": karma >= thr, "threshold": thr}
    if path == "rogue":
        # TEC-5 (flag `forbidden_path`) — a válvula do Errante. Canon ajustado:
        # *"a neutralidade nunca é errada — mas um Errante a −500 não é neutro;
        # é um mentiroso."* Com a flag OFF o helper devolve `não divergiu` e os
        # TRÊS consumidores (apply_karma · api_player · KarmaModal) ficam
        # byte-idênticos ao que sempre foram.
        try:
            from core.forbidden_path_engine import rogue_divergence
            rog = rogue_divergence(karma)
            if rog.get("diverged"):
                return {"diverged": True, "threshold": rog.get("threshold")}
        except Exception:
            logger.debug("rogue divergence check failed", exc_info=True)
    return {"diverged": False, "threshold": None}


async def check_path_divergence(session, player_id: int) -> dict[str, Any]:
    """Inspect the player row and report whether path+karma diverge.

    Used by:
        • api endpoints (KarmaModal divergence warning card)
        • apply_karma (post-write detection of newly-triggered divergence)

    Returns ``{diverged: bool, current_path: str|None, current_karma: int,
              threshold: int|None}``. Defensive against DB errors.
    """
    try:
        row = (await session.execute(
            select(Player.path, Player.karma).where(Player.telegram_id == player_id)
        )).first()
    except Exception:
        logger.debug("divergence lookup failed for player_id=%s", player_id, exc_info=True)
        return {"diverged": False, "current_path": None, "current_karma": 0, "threshold": None}
    if not row:
        return {"diverged": False, "current_path": None, "current_karma": 0, "threshold": None}

    path = row[0]
    karma = int(row[1] or 0)
    div = _divergence_for_path_and_karma(path, karma)
    return {
        "diverged": div["diverged"],
        "current_path": path,
        "current_karma": karma,
        "threshold": div["threshold"],
    }


# ── apply_karma — THE mutator (SAVEPOINT-wrapped) ─────────────────────────────

async def apply_karma(
    session,
    player_id: int,
    event_type: str,
    metadata: dict[str, Any] | None = None,
    *,
    delta_override: int | None = None,
) -> dict[str, Any]:
    """Mutate karma for ``player_id`` based on ``event_type``.

    Steps (atomic via SAVEPOINT):
        1. Look up the player row (SELECT ... FOR UPDATE).
        2. Resolve ``delta`` from :data:`KARMA_EVENTS` (or ``delta_override``).
        3. Clamp the new value to ``KARMA_BOUNDS``.
        4. Write the karma_log audit row.
        5. Update ``Player.karma``.
        6. If R3+ and path is still NULL → crystallize.
        7. If path is crystallized and karma diverges → return flag
           (caller schedules the DM via apply_path_divergence_notification).

    Returns::

        {
            "ok": True,
            "delta": int,
            "previous_value": int,
            "new_value": int,
            "label": str,             # band key
            "event_type": str,
            "crystallized": dict|None,  # set if path crystallized this call
            "diverged": bool,
            "divergence_threshold": int|None,
        }

    Failure modes (all return ``{"ok": False, ...}``):
        • Unknown ``event_type`` (no override) → ``unknown_event``
        • Player not found → ``player_not_found``
        • DB error during write → ``internal_error``

    SAVEPOINT (``session.begin_nested()``) is mandatory because callers
    (combat, sect donate, dungeon clear, meditation tick) need karma
    failures to be silent — never aborting the outer transaction. The
    wire patterns in PART 4 of the v16.3 spec all wrap apply_karma in
    try/except for the same reason: defense in depth.
    """
    if delta_override is not None:
        try:
            delta = int(delta_override)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "invalid_delta_override"}
    else:
        if event_type not in KARMA_EVENTS:
            return {"ok": False, "reason": "unknown_event", "event_type": event_type}
        delta = int(KARMA_EVENTS[event_type])

    if delta == 0:
        # Event known but neutralized (e.g. owner-tuned to 0 pre-launch).
        # Still write the audit row so the log preserves the event happened.
        pass

    try:
        async with session.begin_nested():
            player = (await session.execute(
                select(Player).where(Player.telegram_id == player_id).with_for_update()
            )).scalar_one_or_none()
            if player is None:
                return {"ok": False, "reason": "player_not_found"}

            previous = int(player.karma or 0)
            new_value = _clamp_karma(previous + delta)
            applied_delta = new_value - previous

            log_row = KarmaLog(
                player_id=player_id,
                delta=applied_delta,
                new_value=new_value,
                event_type=event_type,
                # Python attr is `metadata_` to avoid the SQLAlchemy
                # declarative-base reserved name; DB column is `metadata`.
                metadata_=dict(metadata) if metadata else None,
            )
            session.add(log_row)

            player.karma = new_value
            realm = int(player.realm or 0)
            current_path_raw = player.path
    except Exception:
        logger.exception(
            "apply_karma SAVEPOINT failed (player_id=%s, event=%s)",
            player_id, event_type,
        )
        return {"ok": False, "reason": "internal_error"}

    # Crystallization is a separate concern from the karma write — runs
    # OUTSIDE the SAVEPOINT so set_player_path's own SAVEPOINT can wrap
    # cleanly. If crystallization fails the karma write still stands.
    crystallized: dict[str, Any] | None = None
    from core.path_engine import is_valid_path, PATH_PICK_MIN_REALM
    if realm >= PATH_PICK_MIN_REALM and not is_valid_path(current_path_raw):
        try:
            crystallized = await crystallize_path_for_player(
                session, player_id, source="karma_event",
            )
            if crystallized and crystallized.get("ok"):
                # Refresh the local path so divergence check below uses
                # the fresh value (otherwise it would still see NULL).
                current_path_raw = crystallized.get("path")
        except Exception:
            logger.exception(
                "crystallize_path_for_player failed inside apply_karma "
                "(player_id=%s)", player_id,
            )

    # Achievement bus — every karma_log write increments #27 Karmic
    # Devotee (lifetime audit count, target 1000). When new_value crosses
    # +KARMA_MAX (+1000) the Saint Walker #25 fires (single-shot); when it
    # crosses KARMA_MIN (−1000) the Demon Sovereign #31 fires (the demonic
    # mirror, quick-wins 2026-06-10). All three are defensive — failure
    # NEVER aborts the karma write.
    try:
        from core.achievement_engine import check_achievements
        await check_achievements(session, player_id, "karma_event_logged", 1)
        if new_value >= KARMA_MAX and previous < KARMA_MAX:
            await check_achievements(session, player_id, "karma_reached_max", 1)
        if new_value <= KARMA_MIN and previous > KARMA_MIN:
            await check_achievements(session, player_id, "karma_reached_min", 1)
    except Exception:
        logger.exception(
            "achievement bus failed inside apply_karma (player_id=%s)", player_id,
        )

    # Post-crystallization divergence check — pure compute, no write.
    div = _divergence_for_path_and_karma(current_path_raw, new_value)

    # If newly diverged, dispatch the Heart Demon DM via notify() (which
    # is dedup-safe via the unique index — repeated calls within the
    # 24h day-bucket collapse). The notification SAVEPOINT failing here
    # never aborts the karma write; defense in depth.
    notified = False
    if div["diverged"] and isinstance(current_path_raw, str):
        try:
            dm = await apply_path_divergence_notification(
                session, player_id,
                current_path=current_path_raw,
                current_karma=new_value,
            )
            notified = bool(dm and dm.get("notified"))
        except Exception:
            logger.exception(
                "apply_path_divergence_notification failed inside apply_karma "
                "(player_id=%s, path=%s)", player_id, current_path_raw,
            )

    return {
        "ok": True,
        "delta": applied_delta,
        "previous_value": previous,
        "new_value": new_value,
        "label": get_karma_label(new_value),
        "event_type": event_type,
        "crystallized": crystallized if (crystallized and crystallized.get("ok")) else None,
        "diverged": bool(div["diverged"]),
        "divergence_threshold": div["threshold"],
        "divergence_notified": notified,
    }


# ── Divergence notification (Heart Demon DM + 72h grace) ──────────────────────

async def apply_path_divergence_notification(
    session, player_id: int, *, current_path: str, current_karma: int,
) -> dict[str, Any]:
    """Persist the Heart Demon divergence notification for ``player_id``.

    Goes through :func:`core.notification_engine.notify`, which already
    handles SAVEPOINT-wrapping + dedup (via the unique index on
    ``(player_id, kind, ref_id)``). The dedup key here is the path tier
    + the karma sign + a day-bucket: the same divergence within ~24h is
    treated as the same warning; a player who diverges, returns, then
    diverges again days later gets a fresh DM.

    v16.3 ships the notification surface (DM via notification engine)
    and the 72h grace window. The Heart Demon *quest* itself (the
    narrative resolution path) is v16.7 Forbidden Path territory — v16.3
    only logs the trigger, warns the player, and reserves the window.

    Returns ``{ok: True, notified: bool, grace_until_ms: int}``.
    """
    from datetime import timedelta
    from core.notification_engine import notify as _notify

    now = datetime.now(timezone.utc)
    grace_until = now + timedelta(hours=KARMA_DIVERGENCE_GRACE_HOURS)
    # ref_id buckets by UTC day so the same divergence within 24h
    # collapses on the unique index; a separate divergence days later
    # gets its own row.
    day_bucket = now.strftime("%Y%m%d")
    ref_id = f"{current_path}:{day_bucket}"

    try:
        notif = await _notify(
            session,
            player_id,
            kind="karma_divergence",
            title_key="karma_divergence_dm_title",
            body_key="karma_divergence_dm_body",
            payload={
                "path": current_path,
                "karma": current_karma,
                "grace_until_ms": int(grace_until.timestamp() * 1000),
                "grace_hours": KARMA_DIVERGENCE_GRACE_HOURS,
            },
            ref_id=ref_id,
            icon="⚖️",
            target_tab="cultivation",
            priority=7,
        )
    except Exception:
        logger.exception(
            "divergence notify() failed (player_id=%s, path=%s)",
            player_id, current_path,
        )
        return {"ok": False, "reason": "internal_error"}

    logger.info(
        "karma_divergence_notification: player_id=%s path=%s karma=%s grace_hours=%s dedup=%s",
        player_id, current_path, current_karma, KARMA_DIVERGENCE_GRACE_HOURS,
        "no" if notif else "yes",
    )
    return {
        "ok": True,
        "notified": notif is not None,
        "grace_until_ms": int(grace_until.timestamp() * 1000),
    }


# ── Display helpers (chat + miniapp) ──────────────────────────────────────────

def project_karma_for_display(karma: int, lang: str) -> dict[str, Any]:
    """Project the karma value into a UI-ready dict (chat + miniapp).

    Returns::

        {
            "value": int,
            "label_key": str,         # "karma_label_saint" etc.
            "label": str,             # localized
            "emoji": str,
            "band": str,              # "saint"|"pure"|...
            "tier_color": str,        # CSS-friendly hint
            "tribulation_modifier": float,
        }
    """
    from core.i18n import t as i18n_t

    karma = int(karma or 0)
    band = get_karma_label(karma)
    emoji = KARMA_LABEL_EMOJI.get(band, "☯️")
    color_map = {
        "saint":   "rgba(245,220,160,.95)",
        "pure":    "rgba(190,220,255,.92)",
        "neutral": "rgba(200,210,220,.85)",
        "tainted": "rgba(240,170,170,.92)",
        "demonic": "rgba(255,180,180,.95)",
    }
    return {
        "value": karma,
        "label_key": f"karma_label_{band}",
        "label": i18n_t(lang, f"karma_label_{band}"),
        "emoji": emoji,
        "band": band,
        "tier_color": color_map.get(band, "rgba(200,210,220,.85)"),
        "tribulation_modifier": get_tribulation_modifier(abs(karma)),
    }


def get_canonical_events_for_display(lang: str) -> list[dict[str, Any]]:
    """Return the canonical event catalog projected for the KarmaModal
    "What changes my karma?" expandable list.

    Lei §1 honest disclosure: the player always knows which actions move
    karma in which direction. Hidden mechanics breed bad faith.
    """
    from core.i18n import t as i18n_t

    out: list[dict[str, Any]] = []
    for event_key, delta in KARMA_EVENTS.items():
        label = i18n_t(lang, f"karma_event_{event_key}")
        # If the locale doesn't have a translation, fall back to a
        # title-cased version of the key (safeT pattern from the miniapp).
        if label == f"karma_event_{event_key}":
            label = event_key.replace("_", " ").title()
        out.append({
            "event_key": event_key,
            "label": label,
            "delta": int(delta),
            "sign": "+" if delta > 0 else ("−" if delta < 0 else "·"),
        })
    # Stable order: positive first (descending magnitude), then negative
    # (descending magnitude), so the UI list reads like "best ↓ worst".
    out.sort(key=lambda r: (-r["delta"], r["event_key"]))
    return out


# ── Track A item 4 — the world READS your karma ───────────────────────────────
#
# These helpers turn the silent karma score into a world that *reacts and says
# why* (Grand Design §9 item 4). All pure / display-only — zero combat, no jade,
# no mutation, wipe-safe (Lei §5). The reaction is derived on the fly from
# (npc_karma × player_karma); no NPC is ever mutated (Lei §2).


def _karma_align(karma: int) -> str:
    """Collapse the 5 karma bands into a 3-way moral alignment for reactions.

    dark   = demonic | tainted  (karma <= -100)
    light  = pure    | saint     (karma >= +100)
    neutral= the middle band     (-99..+99)
    """
    band = get_karma_label(int(karma or 0))
    if band in ("demonic", "tainted"):
        return "dark"
    if band in ("pure", "saint"):
        return "light"
    return "neutral"


# Emoji per reaction tone (engine-side, mirrors KARMA_LABEL_EMOJI).
NPC_REACTION_EMOJI: dict[str, str] = {
    "ally":    "🤝",
    "hostile": "⚔️",
    "feared":  "😨",
    "revered": "🙏",
    "wary":    "🌫️",
    "neutral": "☯️",
}

# How an NPC (row alignment) regards a player (column alignment). The Wuxia
# logic (Lei §2 — "o mundo sente o teu Dao"): a demon recognizes a kindred
# shadow (ally) and bristles at a saint (hostile); a righteous cultivator
# reveres a fellow paragon and recoils from a demon (feared). Purely narrative —
# the existing spare/execute fork remains the only mechanical consequence.
_NPC_REACTION_MATRIX: dict[tuple[str, str], str] = {
    ("dark", "dark"):       "ally",
    ("dark", "neutral"):    "wary",
    ("dark", "light"):      "hostile",
    ("neutral", "dark"):    "wary",
    ("neutral", "neutral"): "neutral",
    ("neutral", "light"):   "neutral",
    ("light", "dark"):      "feared",
    ("light", "neutral"):   "neutral",
    ("light", "light"):     "revered",
}


def project_npc_reaction(npc_karma: int, player_karma: int, lang: str) -> dict[str, Any]:
    """How an NPC of ``npc_karma`` reacts to a viewer of ``player_karma``.

    Pure, defensive, server-localized. Returns ``{tone, emoji, line}`` where
    ``line`` is the localized one-liner that *explains* the reaction (Lei §1 —
    the player always sees why they are treated this way). ``line`` is "" if the
    locale is missing the key, so the caller can simply hide an empty reaction.

    ZERO mechanical effect (Lei §5): this is greeting text crossed from
    (npc_karma × player_karma); no NPC is mutated, no stat/loot/price changes.
    """
    try:
        npc_align = _karma_align(int(npc_karma or 0))
        player_align = _karma_align(int(player_karma or 0))
        tone = _NPC_REACTION_MATRIX.get((npc_align, player_align), "neutral")
        emoji = NPC_REACTION_EMOJI.get(tone, "☯️")
        from core.i18n import t as i18n_t
        line = i18n_t(lang, f"npc_react_{tone}")
        if line == f"npc_react_{tone}":
            line = ""  # missing locale → hide rather than leak the raw key
        return {"tone": tone, "emoji": emoji, "line": line}
    except Exception:
        logger.debug("project_npc_reaction failed", exc_info=True)
        return {"tone": "neutral", "emoji": "☯️", "line": ""}


def project_world_reactions(karma: int, path: str | None) -> dict[str, Any]:
    """"O que o mundo vê" — the structured disclosure for the KarmaModal.

    Pure + lang-free (the client localizes via safeT). Returns the current
    band, the distance to the NEXT karmic threshold (crystallization if the
    Path is not yet locked, divergence/Heart-Demon if it is), and the list of
    world systems that *react* to karma (Lei §1). Defensive — never raises.

    Shape::

        {
          band: str,                       # demonic|tainted|neutral|pure|saint
          path: str|None,                  # crystallized path, or None
          next: {kind, target, distance, direction},
                # kind: 'crystallize' | 'diverge' | 'none'
          reacts: [{key, active, mod?}],   # npc / sect / bounty / tribulation
        }
    """
    try:
        karma = int(karma or 0)
        band = get_karma_label(karma)
        from core.path_engine import is_valid_path
        crystallized = is_valid_path(path)

        nxt: dict[str, Any] = {"kind": "none", "target": None,
                               "distance": None, "direction": None}
        if not crystallized:
            # Not yet locked. Crystallization fires at Core Formation (R3) and
            # reads the karma AT THAT MOMENT (derive_path_from_karma): the neutral
            # band locks as ROGUE, not righteous/demonic. So the honest projection
            # is "the Path your CURRENT karma would crystallize as" + the R3
            # trigger — NOT a karma "distance" (karma never triggers the lock;
            # the R3 breakthrough does). Mis-stating either breaks Lei §1.
            projected = derive_path_from_karma(karma)  # rogue | righteous | demonic
            nxt = {"kind": "crystallize", "projected": projected,
                   "direction": projected, "target": None, "distance": None}
        elif path == "righteous":
            tgt = KARMA_DIVERGENCE_THRESHOLDS["righteous"]  # -500
            nxt = {"kind": "diverge", "target": tgt,
                   "distance": max(0, karma - tgt), "direction": "demonic"}
        elif path == "demonic":
            tgt = KARMA_DIVERGENCE_THRESHOLDS["demonic"]  # +500
            nxt = {"kind": "diverge", "target": tgt,
                   "distance": max(0, tgt - karma), "direction": "righteous"}
        elif path == "rogue":
            # TEC-5 — com `forbidden_path` ON o Errante também tem um limite, e
            # o card TEM de o dizer (Lei §1: se o Coração pode vir buscá-lo, ele
            # sabe quanto falta). Flag OFF ⇒ `kind` continua 'none' como sempre.
            try:
                from core.forbidden_path_engine import rogue_divergence
                rog = rogue_divergence(karma)
                tgt = rog.get("threshold")
                if tgt is not None:
                    nxt = {"kind": "diverge", "target": int(tgt),
                           "distance": max(0, abs(int(tgt)) - abs(karma)),
                           "direction": rog.get("toward")}
            except Exception:
                logger.debug("rogue divergence projection failed", exc_info=True)

        trib_mod = get_tribulation_modifier(abs(karma))
        reacts = [
            {"key": "npc", "active": True},
            {"key": "sect", "active": True},
            {"key": "bounty", "active": karma <= -100},
            {"key": "tribulation", "active": trib_mod > 1.0, "mod": trib_mod},
        ]
        return {
            "band": band,
            "path": path if crystallized else None,
            "next": nxt,
            "reacts": reacts,
        }
    except Exception:
        logger.debug("project_world_reactions failed", exc_info=True)
        return {"band": get_karma_label(int(karma or 0)), "path": None,
                "next": {"kind": "none", "target": None, "distance": None, "direction": None},
                "reacts": []}


# ── Tribulation karma wire (survive / fail) ───────────────────────────────────

async def apply_tribulation_karma(
    session, player_id: int, *, survived: bool,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Defensive wrapper that wires the tribulation karma event.

    Surviving a heavenly trial is a Righteous-side event (``tribulation_survive``
    +10); failing it breeds resentment (``tribulation_fail`` -10) — the catalog's
    intended mirror. Centralizes the try/except so the ~8 call sites (chat phases
    + mini-app realm grants/fails) stay one-liners and a karma failure can NEVER
    abort a breakthrough (apply_karma owns a SAVEPOINT; this adds defense in
    depth). Returns the apply_karma result or ``None`` on a swallowed error.
    """
    event = "tribulation_survive" if survived else "tribulation_fail"
    try:
        return await apply_karma(session, player_id, event, metadata=metadata)
    except Exception:
        logger.warning("apply_tribulation_karma failed (player=%s, event=%s)",
                       player_id, event, exc_info=True)
        return None
