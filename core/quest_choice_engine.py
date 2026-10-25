"""v16.3.5 — Karmic Crossroads (Moral Quest Engine).

Onda 1 do CAMINHO. A generic engine for moral CHOICES on quest claim: a quest
that carries a `choices` JSONB list lets the player pick a Wuxia fork (mercy vs
power vs greed) whose deltas move karma / reputation / spirit-stones / items.

Design contract (mirrors core/karma_engine.py):
    • constants/helpers at the top, one mutator (`apply_quest_choice`) that runs
      INSIDE the caller's transaction + row lock — it opens NO outer transaction.
    • Idempotency is owned by the caller (`claim_quest_reward`): the lock-protected
      `pq.claimed` flag is the single source of truth for "already granted". This
      module never sets `pq.claimed`; it only stamps `pq.chosen_choice_id` and
      writes the audit row. The caller flips `claimed` after a successful apply.
    • Quests WITHOUT choices never reach this module — `quest_has_choices()` is the
      single chokepoint that keeps the legacy reward path byte-for-byte unchanged.

Karma is applied via karma_engine.apply_karma with event ``quest_moral_choice``
and ``delta_override`` = the choice's karma_delta. We deliberately do NOT register
``quest_moral_choice`` in KARMA_EVENTS: apply_karma's override path doesn't need
it, and the per-choice delta is variable (a fixed catalog entry would mislead the
KarmaModal "what changes my karma?" disclosure list). The karma_log label is
resolved via the i18n key ``karma_event_quest_moral_choice``.
"""

import logging

from sqlalchemy import select, and_

from database.models import PlayerInventory, QuestChoiceLog
from core.karma_engine import apply_karma

logger = logging.getLogger(__name__)


# ── Pure helpers ──────────────────────────────────────────────────────────────

def quest_has_choices(quest) -> bool:
    """The single branch point: True ⇒ moral picker, False ⇒ today's reward path."""
    choices = getattr(quest, "choices", None)
    return bool(choices) and isinstance(choices, list) and len(choices) > 0


def _find_choice(quest, choice_id: str) -> dict | None:
    """Resolve a choice by its stable `id` (never by index — input is untrusted)."""
    if not quest_has_choices(quest):
        return None
    for c in quest.choices:
        if isinstance(c, dict) and c.get("id") == choice_id:
            return c
    return None


def get_quest_choices_raw(quest) -> list[dict]:
    """Raw projection for the mini-app API. The client localizes label_key/
    result_key itself against its own i18n dict (Lei: no strings server-side)."""
    if not quest_has_choices(quest):
        return []
    out: list[dict] = []
    for c in quest.choices:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        out.append({
            "id": c.get("id"),
            "label_key": c.get("label_key"),
            "result_key": c.get("result_key"),
            "karma_delta": int(c.get("karma_delta", 0) or 0),
            "reputation_delta": int(c.get("reputation_delta", 0) or 0),
            "stones_delta": int(c.get("stones_delta", 0) or 0),
            # v16.4c — a Sect-Quest fork can award NPC-sect contribution.
            "sect_contribution_delta": int(c.get("sect_contribution_delta", 0) or 0),
            "item_gained": c.get("item_gained"),
            "item_lost": c.get("item_lost"),
        })
    return out


def get_quest_choices(lang: str, quest) -> list[dict]:
    """Chat-localized projection — label/result resolved via i18n t(lang, key)."""
    from core.i18n import t as i18n_t
    out: list[dict] = []
    for c in get_quest_choices_raw(quest):
        out.append({
            **c,
            "label": i18n_t(lang, c["label_key"]) if c.get("label_key") else "",
            "result": i18n_t(lang, c["result_key"]) if c.get("result_key") else "",
        })
    return out


def _item_tag(item: dict | None) -> str | None:
    """Compact ``type:idxqty`` string for the audit log's VARCHAR(64) columns."""
    if not item or not isinstance(item, dict):
        return None
    itype, iid = item.get("type"), item.get("id")
    if itype is None or iid is None:
        return None
    qty = int(item.get("quantity", 1) or 1)
    return f"{itype}:{iid}x{qty}"


async def _remove_item(session, player_id: int, item: dict) -> bool:
    """Decrement (and delete-if-empty) an inventory row. No-op if absent.

    Mirrors the inventory_actions._decrement_inv idiom. There is no canonical
    remove helper in core/utils, so we inline the established pattern here.
    """
    itype, iid = item.get("type"), item.get("id")
    if itype is None or iid is None:
        return False
    qty = int(item.get("quantity", 1) or 1)
    quality = item.get("quality")
    conds = [
        PlayerInventory.player_id == player_id,
        PlayerInventory.item_type == itype,
        PlayerInventory.item_id == int(iid),
    ]
    if quality is not None:
        conds.append(PlayerInventory.quality == quality)
    row = (await session.execute(select(PlayerInventory).where(and_(*conds)))).scalars().first()
    if not row:
        return False
    row.quantity -= qty
    if row.quantity <= 0:
        await session.delete(row)
    return True


# ── Mutator ───────────────────────────────────────────────────────────────────

async def apply_quest_choice(session, player, quest, pq, choice_id: str) -> dict:
    """Apply one moral choice to ``player``. MUST run inside the caller's txn +
    ``with_for_update`` lock on ``pq`` (claim_quest_reward provides both).

    Validation is fail-closed. Reward side-effects are best-effort additive: a
    full bag on item_gained does NOT abort (karma/stones already moved); a missing
    item_lost is a no-op. Everything is atomic with the caller's later
    ``pq.claimed = True`` write, so a thrown exception rolls the whole claim back.

    Returns ``{"ok": True, ...}`` or ``{"ok": False, "reason": ...}``.
    """
    if not quest_has_choices(quest):
        return {"ok": False, "reason": "no_choices"}
    choice = _find_choice(quest, choice_id)
    if choice is None:
        return {"ok": False, "reason": "invalid_choice"}
    if pq.claimed:  # belt-and-suspenders; the claim WHERE already filters this
        return {"ok": False, "reason": "already_claimed"}

    pid = player.telegram_id
    karma_delta = int(choice.get("karma_delta", 0) or 0)
    rep_delta = int(choice.get("reputation_delta", 0) or 0)
    stones_delta = int(choice.get("stones_delta", 0) or 0)
    item_gained = choice.get("item_gained")
    item_lost = choice.get("item_lost")

    # 1. Karma — apply_karma owns its own SAVEPOINT and is silent-by-design;
    #    wrap anyway (defense in depth, like every other karma caller).
    new_karma = None
    karma_result = {"delta": 0, "new_value": int(getattr(player, "karma", 0) or 0), "label": None}
    if karma_delta != 0:
        try:
            kr = await apply_karma(
                session, pid, "quest_moral_choice",
                metadata={"quest_id": quest.id, "choice_id": choice_id},
                delta_override=karma_delta,
            )
            if kr.get("ok"):
                new_karma = kr.get("new_value")
                karma_result = {
                    "delta": kr.get("delta", 0),
                    "new_value": kr.get("new_value"),
                    "label": kr.get("label"),
                }
        except Exception:
            logger.exception(
                "apply_quest_choice: karma failed (player=%s quest=%s choice=%s)",
                pid, quest.id, choice_id,
            )

    # 2. Spirit stones (floor at 0 so a "greed costs stones" fork can't go negative).
    if stones_delta:
        player.spirit_stones = max(0, int(player.spirit_stones or 0) + stones_delta)

    # 3. Item gained — bag full ⇒ flag it, do NOT abort the choice.
    item_gained_failed = False
    if item_gained:
        from core.utils import add_item_to_inventory
        ok = await add_item_to_inventory(
            session, pid,
            item_gained.get("type"), int(item_gained.get("id")),
            int(item_gained.get("quantity", 1) or 1),
            item_gained.get("quality", "normal"),
        )
        if not ok:
            item_gained_failed = True

    # 4. Item lost — no-op if the player doesn't hold it.
    if item_lost:
        await _remove_item(session, pid, item_lost)

    # 4.5 Sect contribution (v16.4c) — a Sect-Quest fork can earn NPC-sect rank
    #     currency (and trigger an auto-promotion). Routes through the single
    #     mutator; defensive (a non-member or failure never aborts the claim).
    sect_contribution_delta = int(choice.get("sect_contribution_delta", 0) or 0)
    if sect_contribution_delta > 0:
        try:
            from core.world_sects_engine import award_sect_contribution
            await award_sect_contribution(
                session, pid, sect_contribution_delta, source="sect_quest_choice"
            )
        except Exception:
            logger.exception(
                "apply_quest_choice: sect_contribution failed (player=%s quest=%s)",
                pid, quest.id,
            )

    # 5. Reputation — faction-scoped (deprecated v16.2+); ~0 players today.
    if rep_delta:
        try:
            from core.faction_engine import get_player_faction
            pf = await get_player_faction(session, pid)
            if pf:
                pf.reputation = int(pf.reputation or 0) + rep_delta
                if rep_delta > 0:
                    pf.total_rep_earned = int(pf.total_rep_earned or 0) + rep_delta
        except Exception:
            logger.exception("apply_quest_choice: reputation failed (player=%s)", pid)

    # 6. Stamp the cycle + audit. `pq.claimed = True` is the caller's job
    #    (single writer) so the lock contract stays clean.
    pq.chosen_choice_id = choice_id
    session.add(QuestChoiceLog(
        player_id=pid,
        quest_id=quest.id,
        chosen_choice_id=choice_id,
        karma_delta=int(karma_result["delta"] or 0),
        new_karma=new_karma,
        reputation_delta=rep_delta,
        stones_delta=stones_delta,
        item_gained=_item_tag(item_gained),
        item_lost=_item_tag(item_lost),
        reset_at=pq.reset_at,
        metadata_={"quest_id": quest.id, "choice_id": choice_id},
    ))

    return {
        "ok": True,
        "choice_id": choice_id,
        "result_key": choice.get("result_key"),
        "karma": karma_result,
        "stones_delta": stones_delta,
        "sect_contribution_delta": sect_contribution_delta,
        "item_gained": item_gained,
        "item_gained_failed": item_gained_failed,
        "item_lost": item_lost,
        "reputation_delta": rep_delta,
    }
