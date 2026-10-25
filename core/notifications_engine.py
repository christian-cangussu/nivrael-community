"""v14.5 — Notifications Pack scheduler job.

Consolidates four opt-out player notifications wired to existing
`PlayerNotificationPref` toggles (M-9). State-tracking columns added by
migration 086 prevent duplicate DMs across ticks.

  • Pill buff pre-expiry alert (N-10)        — pref ``pill_finished``
  • Alchemy energy back to full (Q-2)        — pref ``alchemy_energy_full``
  • Breakthrough threshold reached (Q-3)     — pref ``breakthrough_ready``
  • Tribulation cooldown ended (Q-4)         — pref ``trib_cooldown_done``

The whole job is best-effort — a failure on one branch must not block the
others. We log and continue. RetryAfter is honoured so flood waits do not
crash the tick.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from telegram import Bot
from telegram.error import RetryAfter

from config import TRIBULATION_COOLDOWN_FAILURE_LIGHT, REALM_NAMES, get_threshold
from core.alchemy_engine import get_alchemy_energy
from core.i18n import t
from core.monetization import get_player_vip_level
from core.notification_prefs import filter_recipients
from core.utils import normalize_lang
from database.db import get_session_factory
from database.models import Player, PlayerBuff, Tribulation

logger = logging.getLogger(__name__)

# Window: notify when expires_at is within (now, now + PILL_PRE_EXPIRY_WINDOW).
# 90s gives ~30s overlap with our 60s scheduler interval so we never miss an
# expiry that lands between ticks.
PILL_PRE_EXPIRY_WINDOW = timedelta(seconds=90)


async def _safe_send(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    # ⚠️ WEB-B Fase 2 — o jogador web tem `telegram_id` NEGATIVO, e 19 sítios
    # mandam DM usando o `telegram_id` como `chat_id`. Sem este guarda seria uma
    # chamada desperdiçada à API do Telegram e um aviso no log **por jogador
    # web, por ciclo, para sempre** — e um negativo é um id de GRUPO na
    # semântica do Telegram, portanto o pior caso não é falhar: é acertar no
    # sítio errado. Um guarda, num sítio, antes de existir o primeiro negativo.
    if not chat_id or int(chat_id) <= 0:
        return False
    try:
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        return True
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 0.5)
        try:
            await bot.send_message(chat_id=chat_id, text=text, **kwargs)
            return True
        except Exception:
            logger.warning("retry send failed for %s after flood wait", chat_id)
            return False
    except Exception as e:
        logger.warning("notif send failed for %s: %s", chat_id, e)
        return False


async def _notify_pill_expiring(bot: Bot) -> int:
    """Find player_buffs whose expires_at is approaching and DM the owner."""
    now = datetime.now(timezone.utc)
    cutoff = now + PILL_PRE_EXPIRY_WINDOW
    sent = 0

    async with get_session_factory()() as session:
        stmt = (
            select(PlayerBuff)
            .where(
                PlayerBuff.expiry_notified == False,
                PlayerBuff.expires_at > now,
                PlayerBuff.expires_at <= cutoff,
            )
            .order_by(PlayerBuff.expires_at)
        )
        rows = (await session.execute(stmt)).scalars().all()

        if not rows:
            return 0

        # Honour pref toggle in one query.
        candidates = list({b.player_id for b in rows})
        allowed = await filter_recipients(session, candidates, "pill_finished")

        # Mark all as notified up-front so we never DM twice even if Telegram
        # send fails — the pref toggle is the user's escape hatch.
        ids = [b.id for b in rows]
        await session.execute(
            update(PlayerBuff).where(PlayerBuff.id.in_(ids)).values(expiry_notified=True)
        )
        # Player language lookup
        player_langs = dict((await session.execute(
            select(Player.telegram_id, Player.language).where(Player.telegram_id.in_(candidates))
        )).all())
        await session.commit()

    for buff in rows:
        if buff.player_id not in allowed:
            continue
        lang = normalize_lang(player_langs.get(buff.player_id))
        remaining = max(0, int((buff.expires_at - now).total_seconds()))
        # `source` was set by alchemy_engine as "<pill name> (<quality>)" — the
        # buff_type is the canonical fallback when source is missing (rare).
        # Onda 5 Fase 2: formation activations stamp source="formation:<key>" —
        # resolve the localized name instead of leaking the machine string.
        label = buff.source or buff.buff_type
        if label.startswith("formation:"):
            label = "🔯 " + t(lang, f"formation_name_{label[len('formation:'):]}")
        msg = t(lang, "notif_pill_expiring", pill=label, seconds=remaining)
        if await _safe_send(bot, buff.player_id, msg, parse_mode="Markdown"):
            sent += 1
        await asyncio.sleep(0.05)
    return sent


async def _notify_alchemy_full(bot: Bot) -> int:
    """DM players whose alchemy energy has just topped back up to max.

    Skips:
      • Players who never crafted (`alchemy_energy_updated_at` NULL).
      • Players already notified for the current refill cycle.
    """
    sent = 0

    async with get_session_factory()() as session:
        # Pull only candidates: never-notified OR last-notified is older than
        # the most recent consume. That way once we flag a player, they only
        # re-trigger after they consume again.
        stmt = (
            select(Player)
            .where(
                Player.alchemy_energy_updated_at != None,
            )
        )
        rows = (await session.execute(stmt)).scalars().all()

        # 2026-08-18 — o tecto passou a depender do tier de Alquimia (火候). Sem
        # o tier este varredor diria "energia cheia" aos 100 a um Celestial cujo
        # tecto é 240 — e pior: gravaria `last_alchemy_full_notified_at`, logo o
        # enchimento VERDADEIRO nunca mais avisaria. UMA query para todos.
        from core.alchemy_engine import get_alchemy_tiers_bulk
        tiers = await get_alchemy_tiers_bulk(session, [int(p.telegram_id) for p in rows])

        # Filter in Python to keep SQL portable across players who haven't been
        # consuming. We only DM if energy has actually reached cap.
        candidates: list[tuple[Player, int, int]] = []
        for player in rows:
            last_notified = player.last_alchemy_full_notified_at
            updated_at = player.alchemy_energy_updated_at
            if last_notified is not None and updated_at is not None and last_notified >= updated_at:
                continue
            try:
                vip_lvl = await get_player_vip_level(session, player.telegram_id)
            except Exception:
                vip_lvl = 0
            current, energy_max, _ = get_alchemy_energy(player, vip_lvl, tiers.get(int(player.telegram_id), 1))
            if current < energy_max:
                continue
            candidates.append((player, current, energy_max))

        if not candidates:
            return 0

        candidate_ids = [p.telegram_id for p, _, _ in candidates]
        allowed = await filter_recipients(session, candidate_ids, "alchemy_energy_full")

        now = datetime.now(timezone.utc)
        # Mark all candidates as notified. Even players opted-out are flagged
        # so we don't re-evaluate their state on every tick.
        await session.execute(
            update(Player)
            .where(Player.telegram_id.in_(candidate_ids))
            .values(last_alchemy_full_notified_at=now)
        )
        await session.commit()

        for player, current, energy_max in candidates:
            if player.telegram_id not in allowed:
                continue
            lang = normalize_lang(player.language)
            msg = t(lang, "notif_alchemy_energy_full", current=current, max=energy_max)
            if await _safe_send(bot, player.telegram_id, msg, parse_mode="Markdown"):
                sent += 1
            await asyncio.sleep(0.05)
    return sent


async def _notify_breakthrough_ready(bot: Bot) -> int:
    """DM players whose CB has hit threshold for their current realm/sub-layer.

    Snapshot is keyed on (realm, sub_layer) so the alert re-fires after every
    breakthrough. We only emit once per (realm, sub_layer) per player.
    """
    sent = 0

    async with get_session_factory()() as session:
        # Players plausibly at threshold — skip already-notified for the same
        # (realm, sub) tuple. Skip the very top: realm 10 sub_layer 9 caps.
        stmt = select(Player).where(Player.cultivation_base > 0)
        rows = (await session.execute(stmt)).scalars().all()

        candidates: list[Player] = []
        for player in rows:
            if player.realm >= len(REALM_NAMES) - 1 and player.sub_layer >= 9:
                continue  # at the cap; nothing to break through
            already = (
                player.last_breakthrough_notified_realm == player.realm
                and player.last_breakthrough_notified_sub == player.sub_layer
            )
            if already:
                continue
            try:
                threshold = get_threshold(player.realm, player.sub_layer)
            except Exception:
                continue
            if (player.cultivation_base or 0) < threshold:
                continue
            candidates.append(player)

        if not candidates:
            return 0

        candidate_ids = [p.telegram_id for p in candidates]
        allowed = await filter_recipients(session, candidate_ids, "breakthrough_ready")

        # Snapshot the realm/sub for every candidate up-front.
        for player in candidates:
            player.last_breakthrough_notified_realm = player.realm
            player.last_breakthrough_notified_sub = player.sub_layer
        await session.commit()

        for player in candidates:
            if player.telegram_id not in allowed:
                continue
            lang = normalize_lang(player.language)
            realm_name = REALM_NAMES[min(player.realm, len(REALM_NAMES) - 1)]
            msg = t(
                lang, "notif_breakthrough_ready",
                realm=realm_name, sub=player.sub_layer,
            )
            if await _safe_send(bot, player.telegram_id, msg, parse_mode="Markdown"):
                sent += 1
            await asyncio.sleep(0.05)
    return sent


async def _notify_trib_cooldown_done(bot: Bot) -> int:
    """DM players whose tribulation failure cooldown has ended."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=TRIBULATION_COOLDOWN_FAILURE_LIGHT)
    sent = 0

    async with get_session_factory()() as session:
        stmt = (
            select(Tribulation)
            .where(
                Tribulation.status == "failed",
                Tribulation.cooldown_notified == False,
                Tribulation.completed_at != None,
                Tribulation.completed_at <= cutoff,
            )
            .order_by(Tribulation.completed_at)
        )
        rows = (await session.execute(stmt)).scalars().all()

        if not rows:
            return 0

        # Suppress stale alerts if there is a NEWER tribulation row for the
        # same (player, realm) — only the most recent failure deserves the DM.
        keep: list[Tribulation] = []
        seen_keys: set[tuple[int, int]] = set()
        rows_sorted = sorted(rows, key=lambda x: x.completed_at, reverse=True)
        for trib in rows_sorted:
            key = (trib.player_id, trib.realm)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            keep.append(trib)

        ids = [r.id for r in rows]
        # Mark ALL rows (including superseded ones) as notified to avoid
        # re-scanning them next tick.
        await session.execute(
            update(Tribulation).where(Tribulation.id.in_(ids)).values(cooldown_notified=True)
        )

        candidate_ids = list({t.player_id for t in keep})
        allowed = await filter_recipients(session, candidate_ids, "trib_cooldown_done")
        player_langs = dict((await session.execute(
            select(Player.telegram_id, Player.language).where(Player.telegram_id.in_(candidate_ids))
        )).all())
        await session.commit()

        for trib in keep:
            if trib.player_id not in allowed:
                continue
            lang = normalize_lang(player_langs.get(trib.player_id))
            realm_idx = min(trib.realm, len(REALM_NAMES) - 1)
            realm_name = REALM_NAMES[realm_idx]
            msg = t(lang, "notif_trib_cooldown_done", realm=realm_name)
            if await _safe_send(bot, trib.player_id, msg, parse_mode="Markdown"):
                sent += 1
            await asyncio.sleep(0.05)
    return sent


async def notifications_pack_job(bot: Bot) -> None:
    """Single consolidated job — runs the four branches independently."""
    if bot is None:
        return
    totals: dict[str, int] = {}
    for label, coro in (
        ("pill_expiring", _notify_pill_expiring(bot)),
        ("alchemy_full", _notify_alchemy_full(bot)),
        ("breakthrough_ready", _notify_breakthrough_ready(bot)),
        ("trib_cooldown_done", _notify_trib_cooldown_done(bot)),
    ):
        try:
            totals[label] = await coro
        except Exception as e:
            logger.error("notifications_pack_job branch %s failed: %s", label, e, exc_info=True)
            totals[label] = -1
    if any(v > 0 for v in totals.values()):
        logger.info("📨 notifications_pack: %s", totals)
