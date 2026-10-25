"""Onda 4a — Bounty Board engine (the hunt with meaning).

The Onda 3 NPC-cultivator population gave the world a body. Onda 4a gives the
dark half of that population a CONSEQUENCE: a world-issued Bounty Board of
contracts on cultivators who walked into darkness (``karma <=
BOUNTY_TARGET_MAX_KARMA`` — the ``tainted``/``demonic`` bands). A bounty is
fulfilled by the SAME ``npc_cultivator`` duel the plaza already uses — there is
no new combat path, no new cooldown; a bounty is just a curated target + a
reward on top of the existing encounter, resolved by the existing spare/execute
moral fork.

Design (mirrors core/npc_cultivator_engine + core/heavens_whispers_engine):
    * module-level env-tunable constants (engine, not DB — wipe-safe, Lei §5)
    * a low-freq refill/expire worker (``refresh_bounties``) the scheduler calls
    * read helpers for the board + a continent count for the plaza header
    * one row-locked, idempotent mutator (``claim_bounty``)

Production safety (57 live players — Lei §5 + §1):
    * ADDITIVE — a bounty never locks any existing farm; the plaza is a NEW
      surface and the hunt reuses the SEPARATE cultivator cooldown.
    * BOUNDED — a hard per-continent cap (``BOUNTY_POOL_PER_CONTINENT``) + a
      board read cap; never an unbounded list.
    * SINGLE-CLAIM, PAYS ONCE — the first hunter to beat the named target
      claims it (status open -> claimed). The claim is row-locked + duel-proven
      + duel-stamped, so it can never double-pay or fund two bounties.
    * NO PII / honest — a bounty references an NPC id only; the cartaz is
      projected live via ``project_npc_for_profile`` (always the 🤖 chip, Lei §1).
    * NPCs are NEVER mutated — completion lives on the bounty row, not the NPC.
"""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update

from core.continent_engine import CONTINENT_KEYS, CONTINENT_META
from core.npc_cultivator_engine import get_npc_cultivator, project_npc_for_profile
from database.models import Bounty, NpcCultivator

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# Tuning constants (engine, not DB — wipe-safe; env-overridable for ops tuning)
# ══════════════════════════════════════════════════════════════════════════

# Hard per-continent cap on simultaneous OPEN contracts (the lesson of Onda 3:
# keep the NPC surface BOUNDED, never a global flood). The board read is capped
# again below.
BOUNTY_POOL_PER_CONTINENT = int(os.getenv("BOUNTY_POOL_PER_CONTINENT", "4"))

# A contract expires after this long (a stale villain "fled"); the tick refills.
BOUNTY_TTL_HOURS = int(os.getenv("BOUNTY_TTL_HOURS", "48"))

# Only cultivators of DARK karma are hunted (the prompt: tainted/demonic, karma
# <= -100). Demonic seeds carry -120..-620; this is comfortably populated.
BOUNTY_TARGET_MAX_KARMA = int(os.getenv("BOUNTY_TARGET_MAX_KARMA", "-100"))

# Karma at/below this is the deepest ``demonic`` band (mirrors the karma_engine
# crystallization threshold) — purely for the cartaz tier flavor + disclosure.
BOUNTY_DEMONIC_KARMA = int(os.getenv("BOUNTY_DEMONIC_KARMA", "-250"))

# Reward = spirit_stones (NOT jade — Lei §4: jade is acceleration/cosmetic, not
# a grind faucet), scaled to the target's realm. Roughly 2-3× the base
# npc_cultivator win reward (40 + 12·realm), so a bounty is worth the curation —
# but there is a cooldown, so it is a challenge, not a farm.
BOUNTY_REWARD_BASE = int(os.getenv("BOUNTY_REWARD_BASE", "120"))
BOUNTY_REWARD_PER_REALM = int(os.getenv("BOUNTY_REWARD_PER_REALM", "30"))

# Board read cap (how many contracts a player sees at once).
BOUNTY_BOARD_CAP = int(os.getenv("BOUNTY_BOARD_CAP", "12"))

# ── Track A item 3 — player-posted bounties ("colocar a cabeça a prêmio") ──
# A player can fund a contract on a dark-karma NPC. The reward is spirit_stones
# (NEVER jade — Lei §4), a REAL sink: it is debited on posting and is
# NON-REFUNDABLE (expiry/claim never returns it — posting is a deliberate act).
# Anti-grief (all DISCLOSED before posting, Lei §1):
#   * only dark-karma NPCs (karma <= BOUNTY_TARGET_MAX_KARMA) — never players
#     this wave (player-vs-player needs PvP consent → deferred to the wipe).
#   * a hard floor on the prize, and a hard cap on simultaneous OPEN posts.
#   * one OPEN bounty per target (the existing uq_bounty_open_npc index).
MIN_PLAYER_BOUNTY = int(os.getenv("MIN_PLAYER_BOUNTY", "500"))
MAX_PLAYER_BOUNTIES = int(os.getenv("MAX_PLAYER_BOUNTIES", "3"))
# Player contracts live longer than the world's roaming villains (a sworn blood
# debt persists); at TTL they expire WITHOUT a refund (Lei §4) and the poster is
# notified (Lei §1 — narrative closure, never a silent void).
PLAYER_BOUNTY_TTL_HOURS = int(os.getenv("PLAYER_BOUNTY_TTL_HOURS", "168"))


def project_bounty_tier(realm: int, karma: int) -> str:
    """A coarse cartaz tier from how dark the target is (display/flavor only)."""
    return "demonic" if int(karma) <= BOUNTY_DEMONIC_KARMA else "tainted"


def continent_badge(continent_key: str | None, lang: str = "pt") -> dict[str, str]:
    """{continent, continent_emoji, continent_name} for a bounty row/receipt —
    the board is PER-CONTINENT (MV-3 §0 fix: a poster must always be able to
    SAY where their non-refundable contract lives, Lei §1). Server-resolved
    name (the mini-app has no continent_* keys of its own). Never raises."""
    key = continent_key if continent_key in CONTINENT_KEYS else "linghe"
    meta = CONTINENT_META.get(key) or {}
    name = key
    try:
        from core.i18n import t as i18n_t
        if meta.get("name_key"):
            name = i18n_t(lang, meta["name_key"])
    except Exception:
        logger.debug("continent_badge i18n failed (continent=%s)", key, exc_info=True)
    return {
        "continent": key,
        "continent_emoji": str(meta.get("emoji", "🗺️")),
        "continent_name": str(name),
    }


# ══════════════════════════════════════════════════════════════════════════
# Refill / expire — the scheduler worker (idempotent, best-effort, own commit)
# ══════════════════════════════════════════════════════════════════════════

async def _pick_dark_targets(session, continent: str, n: int, exclude_ids: set[int]) -> list[NpcCultivator]:
    """Pick up to ``n`` active dark-karma NPCs to post contracts on, PREFERRING
    the plaza's continent and falling back to any continent (a roaming demon
    "sighted near the city") so a righteous continent's board is never empty.
    Excludes NPCs already named by an open bounty (one contract per target)."""
    out: list[NpcCultivator] = []
    seen = set(int(i) for i in exclude_ids)
    # MV-6 — o rival de ALGUÉM nunca recebe contrato (sem loop com o board:
    # a rivalidade é pessoal, o board é público). Gated (flag OFF → set()
    # sem query); fail-safe → sem exclusão.
    try:
        from core.reputation_engine import rival_npc_ids
        seen |= await rival_npc_ids(session)
    except Exception:
        logger.debug("_pick_dark_targets: rival exclusion failed", exc_info=True)
    base = select(NpcCultivator).where(
        NpcCultivator.status == "active",
        NpcCultivator.karma <= BOUNTY_TARGET_MAX_KARMA,
    )
    if seen:
        base = base.where(~NpcCultivator.id.in_(list(seen)))
    rng = random.Random()
    # Continent-first.
    cand = (await session.execute(
        base.where(NpcCultivator.continent_key == continent).limit(40)
    )).scalars().all()
    rng.shuffle(cand)
    for npc in cand:
        if int(npc.id) in seen:
            continue
        out.append(npc)
        seen.add(int(npc.id))
        if len(out) >= n:
            return out
    # Fallback — any other continent.
    cand2 = (await session.execute(
        base.where(NpcCultivator.continent_key != continent).limit(60)
    )).scalars().all()
    rng.shuffle(cand2)
    for npc in cand2:
        if int(npc.id) in seen:
            continue
        out.append(npc)
        seen.add(int(npc.id))
        if len(out) >= n:
            return out
    return out


async def open_npc_ids(session) -> set[int]:
    """Os NPC ids com contrato ABERTO e ainda não vencido — exclusão para quem
    precisa evitar colidir com o Quadro (o MV-8 não deve mandar um NPC agir
    enquanto ele é alvo de um contrato: seria o mundo disputando o mesmo rosto
    consigo mesmo). Irmão de `reputation_engine.rival_npc_ids`. Fail-safe → set().

    ⚠️ NÃO confundir com a variável local homónima dentro de `refresh_bounties`:
    aquela é o conjunto do spawn e usa só `status == 'open'`, o que INCLUI
    contratos já vencidos que o sweep ainda não varreu. Aqui o vencimento é
    filtrado — quem chama isto quer os contratos VIVOS.

    Sem gate de flag: o Quadro de Recompensas é Onda 4a, live em todo mundo (não
    está atrás de feature flag nenhuma) — ao contrário do irmão, que gateia por
    `reputacao_on()`.
    """
    try:
        now = datetime.now(timezone.utc)
        rows = (await session.execute(
            select(Bounty.npc_id).where(
                Bounty.status == "open",
                (Bounty.expires_at.is_(None)) | (Bounty.expires_at > now),
            )
        )).scalars().all()
        return {int(i) for i in rows if i}
    except Exception:
        logger.exception("open_npc_ids failed")
        return set()


async def refresh_bounties(session) -> dict[str, int]:
    """Expire stale contracts, then top each continent back up to
    ``BOUNTY_POOL_PER_CONTINENT`` from active dark-karma NPCs. Idempotent (only
    fills the deficit; a partial UNIQUE index keeps one open bounty per target).
    Best-effort: owns its commits, never raises. Returns {expired, created}."""
    expired = 0
    created = 0
    # 1) Expire by TTL. World contracts (posted_by IS NULL) just lapse; a
    # PLAYER-posted one that lapses notifies its poster (Lei §1 — narrative
    # closure) and is NEVER refunded (Lei §4 — the stones were a real sink).
    try:
        now = datetime.now(timezone.utc)
        lapsing_player = (await session.execute(
            select(Bounty).where(
                Bounty.status == "open",
                Bounty.expires_at.is_not(None),
                Bounty.expires_at < now,
                Bounty.posted_by.is_not(None),
            )
        )).scalars().all()
        res = await session.execute(
            update(Bounty)
            .where(Bounty.status == "open",
                   Bounty.expires_at.is_not(None),
                   Bounty.expires_at < now)
            .values(status="expired")
        )
        expired = res.rowcount or 0
        if lapsing_player:
            from core.notification_engine import notify
            for b in lapsing_player:
                try:
                    npc = await get_npc_cultivator(session, b.npc_id)
                    await notify(
                        session, int(b.posted_by), "bounty_expired",
                        title_key="notif_bounty_expired_title",
                        body_key="notif_bounty_expired_body",
                        payload={"target": (npc.name if npc else "?")},
                        ref_id=f"bexp:{int(b.id)}", icon="🏴",
                        target_tab="plaza", priority=4,
                    )
                except Exception:
                    logger.debug("refresh_bounties: expire-notify failed (bounty=%s)", b.id, exc_info=True)
        await session.commit()
    except Exception:
        logger.exception("refresh_bounties: expire pass failed")
        try:
            await session.rollback()
        except Exception:
            pass
    # 2) Refill the deficit per continent.
    try:
        now = datetime.now(timezone.utc)
        open_npc_ids = set(int(i) for i in (await session.execute(
            select(Bounty.npc_id).where(Bounty.status == "open")
        )).scalars().all())
        # Count WORLD contracts only (posted_by IS NULL) toward the per-continent
        # pool, so a busy continent's player-posted bounties never starve the
        # world board's refill (open_npc_ids above still excludes player-targeted
        # NPCs, so the refill never collides with a player's contract).
        rows = (await session.execute(
            select(Bounty.continent_key, func.count())
            .where(Bounty.status == "open", Bounty.posted_by.is_(None))
            .group_by(Bounty.continent_key)
        )).all()
        counts = {c: int(n) for c, n in rows}
        rng = random.Random()
        for continent in CONTINENT_KEYS:
            deficit = max(0, BOUNTY_POOL_PER_CONTINENT - counts.get(continent, 0))
            if deficit <= 0:
                continue
            picked = await _pick_dark_targets(session, continent, deficit, open_npc_ids)
            for npc in picked:
                open_npc_ids.add(int(npc.id))  # never reuse a target within this run
                realm = int(npc.realm or 0)
                reward = int((BOUNTY_REWARD_BASE + BOUNTY_REWARD_PER_REALM * realm)
                             * rng.uniform(0.85, 1.15))
                # Per-insert SAVEPOINT (mirror post_bounty_on_npc / post_player_bounty):
                # a player can now post on a dark-karma NPC concurrently, so a refill
                # pick can race uq_bounty_open_npc between our SELECT and commit. Without
                # the savepoint that single collision would abort the WHOLE batch; with
                # it, only the losing row drops and the rest of the tick still lands.
                try:
                    from sqlalchemy.exc import IntegrityError
                    async with session.begin_nested():
                        session.add(Bounty(
                            npc_id=int(npc.id), continent_key=continent,
                            realm=realm, karma=int(npc.karma or 0),
                            reward_stones=reward, status="open",
                            created_at=now, expires_at=now + timedelta(hours=BOUNTY_TTL_HOURS),
                        ))
                        await session.flush()
                    created += 1
                except IntegrityError:
                    logger.debug("refresh_bounties: refill insert lost a race (npc=%s)", npc.id, exc_info=True)
        if created:
            await session.commit()
            logger.info("refresh_bounties: +%s contract(s) (expired %s)", created, expired)
    except Exception:
        logger.exception("refresh_bounties: refill pass failed")
        try:
            await session.rollback()
        except Exception:
            pass
    return {"expired": expired, "created": created}


async def post_bounty_on_npc(session, *, rival_sect_id: str | None = None,
                             continent_key: str | None = None) -> Bounty | None:
    """World Pulse (Fase 1, slice E): when a sect RAIDS a rival and "wins", the
    offended house posts a contract on a dark-karma cultivator the raid exposed.

    Reuses the Bounty model — target is an NPC ONLY (Lei §1: the player-bounty
    needs PvP consent and is deferred to Pulse Fase 2). Picks one active dark-karma
    NPC (``karma <= BOUNTY_TARGET_MAX_KARMA``) that has no OPEN bounty yet,
    PREFERRING the rival house's own cultivators, then the raid's continent, then
    any dark cultivator — so the slice still fires even though most rivalries are
    righteous-vs-righteous (whose NPCs carry positive karma and are never hunted).
    ADDS one Bounty row; does NOT commit (the caller's SAVEPOINT/transaction owns
    it — the World Pulse beat). Returns the row or None (no dark target free)."""
    try:
        now = datetime.now(timezone.utc)
        open_ids = set(int(i) for i in (await session.execute(
            select(Bounty.npc_id).where(Bounty.status == "open")
        )).scalars().all())
        # MV-6 — rival de alguém nunca recebe contrato (mesma exclusão do
        # refill; gated + fail-safe).
        try:
            from core.reputation_engine import rival_npc_ids
            open_ids |= await rival_npc_ids(session)
        except Exception:
            logger.debug("post_bounty_on_npc: rival exclusion failed", exc_info=True)

        def _base():
            q = select(NpcCultivator).where(
                NpcCultivator.status == "active",
                NpcCultivator.karma <= BOUNTY_TARGET_MAX_KARMA,
            )
            if open_ids:
                q = q.where(~NpcCultivator.id.in_(list(open_ids)))
            return q

        cands: list[NpcCultivator] = []
        if rival_sect_id:
            cands = (await session.execute(
                _base().where(NpcCultivator.sect_id == rival_sect_id).limit(25)
            )).scalars().all()
        if not cands and continent_key:
            cands = (await session.execute(
                _base().where(NpcCultivator.continent_key == continent_key).limit(25)
            )).scalars().all()
        if not cands:
            cands = (await session.execute(_base().limit(40))).scalars().all()
        if not cands:
            return None

        rng = random.Random()
        npc = rng.choice(cands)
        realm = int(npc.realm or 0)
        reward = int((BOUNTY_REWARD_BASE + BOUNTY_REWARD_PER_REALM * realm)
                     * rng.uniform(0.85, 1.15))
        row = Bounty(
            npc_id=int(npc.id),
            continent_key=continent_key or npc.continent_key or "linghe",
            realm=realm, karma=int(npc.karma or 0),
            reward_stones=reward, status="open",
            created_at=now, expires_at=now + timedelta(hours=BOUNTY_TTL_HOURS),
        )
        # SAVEPOINT the INSERT (mirror snapshot_player_to_npc): a concurrent
        # bounty_refresh_tick could open a bounty on this NPC between our SELECT
        # and flush, tripping uq_bounty_open_npc. Without an inner savepoint that
        # unique-violation would poison the CALLER's transaction/savepoint (the
        # World Pulse beat); with one, only this insert rolls back and we return
        # None (the beat keeps its chronicle + mutation).
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
            return row
        except Exception:
            logger.debug("post_bounty_on_npc: insert lost a race (npc=%s)", npc.id, exc_info=True)
            return None
    except Exception:
        logger.debug("post_bounty_on_npc failed (rival=%s)", rival_sect_id, exc_info=True)
        return None


# ══════════════════════════════════════════════════════════════════════════
# Reads — the board + a continent count for the plaza header
# ══════════════════════════════════════════════════════════════════════════

async def list_active_bounties(session, player, *, lang: str = "pt", realm_label=None,
                               cap: int = BOUNTY_BOARD_CAP) -> list[dict[str, Any]]:
    """Open contracts for the player's continent (newest-reward first), capped
    PER ORIGIN so neither board starves the other (Track A item 3 split the
    feed into 🏴 world-issued vs 🎁 player-posted). Each row carries the live,
    honest target projection (🤖, Lei §1) + reward + a coarse tier + a
    ``source`` ('world'|'player'); player-posted ones also carry the poster's
    public dao_name (no PII beyond the handle the plaza already shows).
    ``realm_label`` is the optional (realm)->(name,emoji) callable passed by the
    caller (webserver._realm_label) so this engine stays free of a webserver
    import.

    MV-3 §0 fix (owner report 2026-07-15): the player feed ALWAYS includes the
    contracts posted BY the viewer, whatever continent they were stamped with —
    a poster who paid non-refundable stones must never lose sight of their own
    cartaz (Lei §1). Those rows carry ``mine`` + an ``elsewhere`` flag + the
    continent badge so the UI can chip "🌋 seu contrato" without a hunt CTA
    (self-claim stays blocked; everyone ELSE only ever sees local contracts,
    so the hunt remains geo-scoped)."""
    out: list[dict[str, Any]] = []
    try:
        now = datetime.now(timezone.utc)
        continent = player.current_continent

        async def _fetch(world: bool):
            q = select(Bounty).where(
                Bounty.status == "open",
                (Bounty.expires_at.is_(None)) | (Bounty.expires_at > now),
                # World contracts: strictly local. Player contracts: local OR
                # posted by the viewer (their own cartaz follows them anywhere).
                (Bounty.continent_key == continent) if world else (
                    (Bounty.continent_key == continent)
                    | (Bounty.posted_by == int(player.telegram_id))
                ),
                Bounty.posted_by.is_(None) if world else Bounty.posted_by.is_not(None),
            ).order_by(Bounty.reward_stones.desc()).limit(int(cap))
            return (await session.execute(q)).scalars().all()

        # Two independent capped queries so neither origin can ever starve the
        # other's tab regardless of counts (world first, then player).
        world_rows = await _fetch(world=True)
        player_rows = await _fetch(world=False)
        # Batch-resolve poster dao_names (no N+1; only the public handle).
        poster_names: dict[int, str] = {}
        poster_ids = {int(b.posted_by) for b in player_rows}
        if poster_ids:
            from database.models import Player as _Player
            prows = (await session.execute(
                select(_Player.telegram_id, _Player.dao_name).where(_Player.telegram_id.in_(list(poster_ids)))
            )).all()
            poster_names = {int(tid): nm for tid, nm in prows}
        # Continent badges resolved once per continent (≤5), not per row.
        badges: dict[str, dict[str, str]] = {}
        for b in world_rows + player_rows:
            npc = await get_npc_cultivator(session, b.npc_id)
            if npc is None or npc.status != "active":
                continue  # target ascended/retired — skip (the tick will expire it)
            is_player = b.posted_by is not None
            b_cont = b.continent_key or "linghe"
            if b_cont not in badges:
                badges[b_cont] = continent_badge(b_cont, lang)
            out.append({
                "bounty_id": int(b.id),
                "reward_stones": int(b.reward_stones or 0),
                "tier": project_bounty_tier(int(b.realm or 0), int(b.karma or 0)),
                "expires_at_ms": int(b.expires_at.timestamp() * 1000) if b.expires_at else None,
                "source": "player" if is_player else "world",
                "posted_by_name": poster_names.get(int(b.posted_by)) if is_player else None,
                # The viewer's OWN posted contract — the UI hides the hunt CTA
                # (you can't claim your own bounty; the server enforces it too).
                "mine": bool(is_player and int(b.posted_by) == int(player.telegram_id)),
                # MV-3 §0 fix — every cartaz says which board it hangs on; the
                # viewer's own contract on ANOTHER continent flags `elsewhere`.
                **badges[b_cont],
                "elsewhere": bool(b_cont != continent),
                "npc": project_npc_for_profile(npc, lang, realm_label=realm_label),
            })
    except Exception:
        logger.exception("list_active_bounties failed")
    return out


async def bounty_board_count(session, continent: str | None) -> int:
    """Count of open, non-expired contracts on a continent (plaza header chip)."""
    try:
        now = datetime.now(timezone.utc)
        return int((await session.execute(
            select(func.count()).select_from(Bounty).where(
                Bounty.status == "open",
                (Bounty.expires_at.is_(None)) | (Bounty.expires_at > now),
                Bounty.continent_key == continent,
            )
        )).scalar() or 0)
    except Exception:
        logger.debug("bounty_board_count failed", exc_info=True)
        return 0


# ══════════════════════════════════════════════════════════════════════════
# Claim — row-locked, duel-proven, idempotent, pays ONCE
# ══════════════════════════════════════════════════════════════════════════

async def claim_bounty(session, player, bounty_id: int, duel_id) -> dict[str, Any]:
    """Claim a fulfilled bounty: the player must have WON the duel vs the named
    target (an npc_cultivator duel). Pays the reward ONCE.

    Idempotency + safety (mirrors apply_combat_moral_choice + the settle lock):
      * the bounty row is locked FOR UPDATE — only one writer transitions
        open -> claimed; a re-claim by the SAME player returns ok (already paid),
        a different player gets ``already_claimed``.
      * the duel is locked FOR UPDATE and validated (won + attacker + source +
        target match) and STAMPED (pve_context['bounty_claimed']) so the same
        duel can never fund a second bounty.
    The caller (endpoint) locks the ``player`` row FOR UPDATE and owns the commit.
    """
    from sqlalchemy.orm.attributes import flag_modified
    from database.models import DuelSession
    try:
        now = datetime.now(timezone.utc)
        bounty = (await session.execute(
            select(Bounty).where(Bounty.id == int(bounty_id)).with_for_update()
        )).scalar_one_or_none()
        if bounty is None:
            return {"ok": False, "reason": "not_found"}
        # Terminal states (idempotent).
        if bounty.status == "claimed":
            if bounty.claimed_by == player.telegram_id:
                return {"ok": True, "already": True, "reward_stones": int(bounty.reward_stones or 0)}
            return {"ok": False, "reason": "already_claimed"}
        if bounty.status != "open":
            return {"ok": False, "reason": "expired"}
        if bounty.expires_at is not None and bounty.expires_at < now:
            bounty.status = "expired"
            return {"ok": False, "reason": "expired"}
        # Track A item 3 — a poster may NOT claim their OWN player-posted
        # contract: the deposit is a real, non-refundable sink (Lei §4), so a
        # self-claim must never hand it back. We reject BEFORE the payout (and
        # before stamping the duel), so the contract stays open for a DIFFERENT
        # hunter (or lapses unrefunded at TTL). World bounties (posted_by NULL)
        # are unaffected. The UI also hides the hunt CTA on the poster's own
        # cartaz (Lei §1) — this is the load-bearing server guard behind it.
        if bounty.posted_by is not None and int(bounty.posted_by) == int(player.telegram_id):
            return {"ok": False, "reason": "own_bounty"}
        # Prove the kill via the duel.
        duel = (await session.execute(
            select(DuelSession).where(DuelSession.id == duel_id).with_for_update()
        )).scalar_one_or_none()
        if duel is None:
            return {"ok": False, "reason": "duel_not_found"}
        if duel.attacker_id != player.telegram_id or duel.pve_source != "npc_cultivator":
            return {"ok": False, "reason": "not_your_duel"}
        if not (duel.winner_id == duel.attacker_id and duel.state == "finished"):
            return {"ok": False, "reason": "not_won"}
        ctx = dict(duel.pve_context or {})
        if int(ctx.get("npc_id") or 0) != int(bounty.npc_id):
            return {"ok": False, "reason": "wrong_target"}
        if ctx.get("bounty_claimed"):
            return {"ok": False, "reason": "duel_used"}
        # Pay once.
        reward = int(bounty.reward_stones or 0)
        player.spirit_stones = int(player.spirit_stones or 0) + reward
        bounty.status = "claimed"
        bounty.claimed_by = player.telegram_id
        bounty.claimed_at = now
        ctx["bounty_claimed"] = int(bounty.id)
        duel.pve_context = ctx
        flag_modified(duel, "pve_context")
        # Track A item 4 — Karma: bringing a NAMED dark-karma villain to justice
        # is a Righteous-side deed (rogue_kill_demonic +30). Bounty targets are
        # always dark-karma NPCs by construction; we re-confirm the band
        # defensively before awarding. Single-claim + duel-stamped (above) means
        # one duel funds one bounty → not farmable. apply_karma owns a SAVEPOINT
        # and never aborts the claim (defense in depth; caller commits).
        try:
            from core.npc_cultivator_engine import get_npc_cultivator as _get_npc
            _tgt = await _get_npc(session, bounty.npc_id)
            if _tgt is not None and int(_tgt.karma or 0) <= -100:
                from core.karma_engine import apply_karma
                await apply_karma(
                    session, player.telegram_id, "rogue_kill_demonic",
                    metadata={"bounty_id": int(bounty.id), "npc_id": int(bounty.npc_id)},
                )
        except Exception:
            logger.debug("claim_bounty: karma wire failed (bounty=%s)", bounty.id, exc_info=True)
        # MV-6 — o continente que SOFRIA o vilão agradece ao caçador (+rep no
        # continente DO CONTRATO — bounty.continent_key, estampado no spawn;
        # é o lugar que pagou o preço, não onde o caçador está). Gancho
        # aditivo gated (flag do irmão OFF → None sem query); antes→depois
        # ride no retorno (progressão visível).
        try:
            from core.reputation_engine import REP_BOUNTY_CLAIM, add_region_rep
            _rep = await add_region_rep(
                session, int(player.telegram_id), bounty.continent_key,
                REP_BOUNTY_CLAIM, "bounty_claim",
                lang=(getattr(player, "language", None) or "pt").lower(),
            )
        except Exception:
            _rep = None
            logger.debug("claim_bounty: rep faucet failed (bounty=%s)", bounty.id, exc_info=True)
        # Track A item 3 — narrative closure for a PLAYER-posted contract (Lei
        # §1): tell the poster their bounty was fulfilled. Skip world-issued
        # (posted_by is None) and self-claims. Best-effort (notify owns a
        # SAVEPOINT and never poisons our transaction); the caller commits.
        poster_id = bounty.posted_by
        if poster_id is not None and int(poster_id) != int(player.telegram_id):
            try:
                npc = await get_npc_cultivator(session, bounty.npc_id)
                from core.notification_engine import notify
                # MV-9 — a string dizia "Arquivos de Wànshì" com o nome COZIDO
                # no valor: mentia em 4 dos 5 continentes. Agora nomeia a cidade
                # do continente ONDE O CONTRATO FOI POSTADO (nunca a de quem
                # lê — o contrato esteve pendurado ali), resolvida no idioma de
                # QUEM RECEBE. Precedente de nome já resolvido dentro do
                # payload: `notif_rep_milestone_body` (MV-6).
                _city_name = ""
                try:
                    from core.city_engine import city_key_for, city_name, cidades_on
                    if cidades_on():
                        # ⚠️ `Player` NÃO é import de módulo neste ficheiro (o
                        # único outro uso, na linha 440, também importa local
                        # como `_Player`). Um `Player` nu aqui seria NameError
                        # em runtime — e `py_compile` não apanha import em falta
                        # dentro de função.
                        from database.models import Player as _P
                        _plang = (await session.execute(
                            select(_P.language).where(_P.telegram_id == int(poster_id))
                        )).scalar() or "pt"
                        _ck = city_key_for(getattr(bounty, "continent_key", None))
                        _city_name = city_name(_ck, str(_plang).lower()) if _ck else ""
                except Exception:
                    logger.debug("claim_bounty: city name lookup failed", exc_info=True)
                await notify(
                    session, int(poster_id), "bounty_claimed",
                    title_key="notif_bounty_claimed_title",
                    body_key="notif_bounty_claimed_body",
                    payload={"target": (npc.name if npc else "?"),
                             "hunter": (player.dao_name or "?"),
                             # Flag OFF → cai no nome de sempre, e a frase fica
                             # exatamente a que os 57 já leem hoje.
                             "city": _city_name or "Wànshì",
                             # MV-9 — a aba `plaza` é 100% continent-scoped: sem
                             # dizer ONDE, a notificação é um beco quando cada
                             # cidade tem nome. `notify` não tem campo de
                             # deep-link, então o lugar viaja no payload livre.
                             "continent": getattr(bounty, "continent_key", None) or ""},
                    ref_id=f"bclaim:{int(bounty.id)}", icon="🏴",
                    target_tab="plaza", priority=4,
                )
            except Exception:
                logger.debug("claim_bounty: poster-notify failed (bounty=%s)", bounty.id, exc_info=True)
        out = {"ok": True, "reward_stones": reward, "npc_id": int(bounty.npc_id)}
        if _rep:
            out["region_rep"] = _rep
        return out
    except Exception:
        logger.exception("claim_bounty failed (player=%s, bounty=%s)",
                         getattr(player, "telegram_id", None), bounty_id)
        return {"ok": False, "reason": "internal_error"}


# ══════════════════════════════════════════════════════════════════════════
# Track A item 3 — player-posted contracts ("colocar a cabeça a prêmio")
# ══════════════════════════════════════════════════════════════════════════

async def player_bounty_context(session, player, npc) -> dict[str, Any]:
    """Disclosure block for the 'Pôr a Prêmio' CTA (Lei §1): whether THIS player
    may post a contract on THIS npc, plus the rules shown BEFORE they commit.
    Pure read — no mutation. ``npc`` is an NpcCultivator (or None)."""
    eligible = (npc is not None and npc.status == "active"
                and int(npc.karma or 0) <= BOUNTY_TARGET_MAX_KARMA)
    already_open = False
    your_open = 0
    try:
        if npc is not None:
            already_open = (await session.execute(
                select(Bounty.id).where(Bounty.npc_id == int(npc.id),
                                        Bounty.status == "open").limit(1)
            )).scalar_one_or_none() is not None
        your_open = int((await session.execute(
            select(func.count()).select_from(Bounty).where(
                Bounty.posted_by == int(player.telegram_id),
                Bounty.status == "open")
        )).scalar() or 0)
    except Exception:
        logger.debug("player_bounty_context read failed", exc_info=True)
    # MV-9 — o contrato é pendurado nos arquivos da cidade ONDE O JOGADOR ESTÁ
    # (o board é continent-scoped). A string `wbounty_post_intro` passou a ter
    # `{city}`; sem este campo o mini-app imprimia a chaveta CRUA na cara do
    # jogador (`t()` no cliente também só substitui o que lhe passam). O nome é
    # resolvido AQUI porque o mini-app não tem — nem deve ter — keys `city_*`:
    # nomes de lugar são server-resolved (lei de colocação da casa).
    _city = ""
    try:
        from core.city_engine import cidades_on, city_key_for, city_name
        if cidades_on():
            _lang = (getattr(player, "language", None) or "pt").lower()
            _ck = city_key_for(getattr(player, "current_continent", None))
            _city = city_name(_ck, _lang) if _ck else ""
    except Exception:
        logger.debug("player_bounty_context city lookup failed", exc_info=True)
    return {
        "eligible": bool(eligible),
        "already_open": bool(already_open),
        "min_stones": MIN_PLAYER_BOUNTY,
        "max_open": MAX_PLAYER_BOUNTIES,
        "your_open": your_open,
        "your_stones": int(getattr(player, "spirit_stones", 0) or 0),
        # Sempre presente (string vazia com a flag OFF) — este campo é LIDO pelo
        # cliente para preencher um placeholder, portanto ausência = chaveta na
        # tela. É a exceção justificada à regra do "key ausente com flag OFF".
        "city": _city,
    }


async def post_player_bounty(session, poster, npc_id: int, stones: int) -> dict[str, Any]:
    """A player funds a contract on a dark-karma NPC. The SAME Bounty row + the
    SAME npc_cultivator duel/claim — only the origin (``posted_by``) differs.
    The reward is spirit_stones (NEVER jade — Lei §4), debited NOW and
    NON-REFUNDABLE (expiry/claim never returns it).

    Anti-grief (Lei §1, all disclosed by the CTA before posting):
      * stones >= MIN_PLAYER_BOUNTY (a serious prize, no spam contracts).
      * NPC exists + active + dark karma (karma <= BOUNTY_TARGET_MAX_KARMA) —
        never a player target this wave (player-vs-player needs PvP consent and
        is deferred to the wipe).
      * one OPEN bounty per target (uq_bounty_open_npc) -> ``already_targeted``.
      * at most MAX_PLAYER_BOUNTIES simultaneous OPEN posts by this player.

    Concurrency (mirrors claim_bounty + post_bounty_on_npc):
      * the CALLER row-locks ``poster`` FOR UPDATE and owns the commit, so a
        double-tap serializes — the open-count and the stone debit can't race.
      * the INSERT runs in a SAVEPOINT so a concurrent post/refill on the same
        NPC rolls back ONLY the insert (-> ``already_targeted``), never poisoning
        the caller's transaction.
      * the stone debit happens ONLY AFTER the insert flushes (all-or-nothing),
        so a lost race never charges the player.
    """
    from sqlalchemy.exc import IntegrityError
    try:
        stones = int(stones)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "invalid_amount"}
    if stones < MIN_PLAYER_BOUNTY:
        return {"ok": False, "reason": "too_cheap", "min_stones": MIN_PLAYER_BOUNTY}
    try:
        npc = await get_npc_cultivator(session, int(npc_id))
        if npc is None or npc.status != "active" or int(npc.karma or 0) > BOUNTY_TARGET_MAX_KARMA:
            return {"ok": False, "reason": "not_eligible"}
        # MV-6 — rival de alguém nunca recebe contrato (nem por jogador: a
        # rivalidade é pessoal — pagar a praça para amaciar o SEU drama, ou o
        # de outro, quebraria o loop). Gated + fail-safe → sem bloqueio.
        try:
            from core.reputation_engine import rival_npc_ids
            if int(npc.id) in await rival_npc_ids(session):
                return {"ok": False, "reason": "not_eligible"}
        except Exception:
            logger.debug("post_player_bounty: rival exclusion failed", exc_info=True)
        if int(getattr(poster, "spirit_stones", 0) or 0) < stones:
            return {"ok": False, "reason": "not_enough_stones"}
        # Max simultaneous OPEN posts (safe under the caller's FOR UPDATE lock).
        open_count = int((await session.execute(
            select(func.count()).select_from(Bounty).where(
                Bounty.posted_by == int(poster.telegram_id),
                Bounty.status == "open")
        )).scalar() or 0)
        if open_count >= MAX_PLAYER_BOUNTIES:
            return {"ok": False, "reason": "max_active", "max_open": MAX_PLAYER_BOUNTIES}
        # Fast pre-check (the SAVEPOINT below is the truth-path against a race).
        if (await session.execute(
            select(Bounty.id).where(Bounty.npc_id == int(npc.id),
                                    Bounty.status == "open").limit(1)
        )).scalar_one_or_none() is not None:
            return {"ok": False, "reason": "already_targeted"}
        now = datetime.now(timezone.utc)
        row = Bounty(
            npc_id=int(npc.id),
            continent_key=npc.continent_key or "linghe",
            realm=int(npc.realm or 0), karma=int(npc.karma or 0),
            reward_stones=stones, status="open",
            posted_by=int(poster.telegram_id), posted_at=now,
            created_at=now, expires_at=now + timedelta(hours=PLAYER_BOUNTY_TTL_HOURS),
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError:
            logger.debug("post_player_bounty: insert lost a race (npc=%s)", npc.id, exc_info=True)
            return {"ok": False, "reason": "already_targeted"}
        # Debit ONLY after the insert succeeded (all-or-nothing).
        poster.spirit_stones = int(poster.spirit_stones or 0) - stones
        # MV-3 §0 fix — the receipt SAYS where the cartaz was hung (the board is
        # per-continent, stamped with the TARGET's continent — which can differ
        # from where the poster is standing; Lei §1 for a non-refundable spend).
        badge = continent_badge(row.continent_key, (getattr(poster, "language", None) or "pt").lower())
        return {"ok": True, "bounty_id": int(row.id), "reward_stones": stones,
                "npc_id": int(npc.id), "stones_after": int(poster.spirit_stones),
                **badge}
    except Exception:
        logger.exception("post_player_bounty failed (poster=%s, npc=%s)",
                         getattr(poster, "telegram_id", None), npc_id)
        return {"ok": False, "reason": "internal_error"}
