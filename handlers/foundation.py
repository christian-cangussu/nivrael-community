"""Handlers for the Foundation system — D-1 of v14 Sprint 14.4.

Three layers (DESIGN_DECISIONS_v14.md §D-1):

1. **D-1a `/recomeço`** — newbie one-shot reroll. Gates: realm ≤ 2 OR
   created_at within last 7 days. Rerolls foundation_quality + spirit_root
   without jade cost. Permanent gate after first use, NOT reset by rebirth.

2. **D-1b `/quebrar_fundacao`** — mid-game ritual. Gates: realm ≥ 5,
   cooldown 30 days OR 1 per rebirth. Costs: 50% CB current realm,
   100k spirit stones, 50 celestial essence. Three path-dependent
   philosophical questions; score determines reroll table outcome.

3. **D-1c Eternal Foundation Pill** lives in alchemy seeds (id=41). When
   crafted at Heavenly grade and the player's foundation is already
   Perfect, it grants the Sacred Foundation tier. See alchemy_engine.

Engine canonical state lives in `core/foundation_engine.py`
(FOUNDATION_QUALITIES, RITUAL_REROLL_TABLES, roll_from_table).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import SPIRIT_ROOT_NAMES, SPIRIT_ROOTS, SPIRIT_ROOT_WEIGHTS
from core.foundation_engine import (
    FOUNDATION_QUALITIES,
    RITUAL_REROLL_TABLES,
    roll_from_table,
)
from core.i18n import t
from core.utils import (
    _ensure_player,
    escape_markdown,
    rate_limit,
    safe_answer,
    safe_handler,
)
from database.db import get_session_factory
from database.models import PlayerDaoFragment

logger = logging.getLogger(__name__)


# ─── D-1a Configuration ──────────────────────────────────────────────────────

RECOMECO_MAX_REALM = 2          # Inclusive — players in realm 0/1/2 still eligible
RECOMECO_MAX_AGE_DAYS = 7       # Players younger than 7 days still eligible


# ─── D-1b Configuration ──────────────────────────────────────────────────────

BREAK_MIN_REALM = 5             # Nascent Soul or above
BREAK_COOLDOWN_DAYS = 30
BREAK_COST_STONES = 100_000
BREAK_COST_ESSENCE = 50
BREAK_CB_PERCENT = 0.50         # 50% of current realm CB

# Element → which question it makes "easy". Read from the player's strongest
# Supreme Dao fragment; if no fragments, fall back to spirit_root tier.
# Spec from DESIGN_DECISIONS_v14.md §D-1b:
#   Q1 Renúncia vs Aceitação — Wood/Earth → Aceitação
#   Q2 Velocidade vs Profundidade — Lightning/Fire → Velocidade
#   Q3 Manter vs Trilhar Novo — Chaos/Void → Novo
ELEMENTS_Q1 = {"Wood", "Earth"}
ELEMENTS_Q2 = {"Lightning", "Fire"}
ELEMENTS_Q3 = {"Chaos", "Void"}

# Default fallback element for players without any Supreme Dao fragments.
# Picks per spirit_root index 0..4 (Heavenly..Low) so the answer is still
# *deterministic per player* — re-running the trial gives the same correct
# answer set (no random gaslighting).
SPIRIT_ROOT_FALLBACK_ELEMENT = {
    0: "Lightning",  # Heavenly — speed/insight bias
    1: "Wood",       # Superior — life/growth bias
    2: "Earth",      # High — stability bias
    3: "Chaos",      # Mid — chaotic potential
    4: "Fire",       # Low — raw passion bias
}


def _is_recomeco_eligible(player) -> tuple[bool, str | None]:
    """Returns (eligible, reason_key_if_not). reason_key indexes into i18n."""
    if player.foundation_reroll_used:
        return False, "recomeco_err_already_used"
    if player.realm <= RECOMECO_MAX_REALM:
        return True, None
    age = datetime.now(timezone.utc) - player.created_at
    if age <= timedelta(days=RECOMECO_MAX_AGE_DAYS):
        return True, None
    return False, "recomeco_err_realm_too_high"


async def _dominant_supreme_element(session, player) -> str:
    """Find the player's strongest Supreme Dao fragment (laws 1-6). If they
    have zero fragments across the Supreme Daos, fall back on spirit_root.

    Returns one of {Lightning, Fire, Wood, Earth, Chaos, Void}. Never None.
    """
    rows = (await session.execute(
        select(PlayerDaoFragment).where(
            PlayerDaoFragment.player_id == player.telegram_id,
            PlayerDaoFragment.dao_law_id.in_([1, 2, 3, 4, 5, 6]),
        )
    )).scalars().all()
    # Map dao_law_id -> element (Supreme Daos, see database/seeds/dao_seeds.py)
    LAW_ELEMENT = {
        1: "Lightning", 2: "Fire", 3: "Wood",
        4: "Chaos", 5: "Earth", 6: "Chaos",
    }
    if rows:
        rows.sort(key=lambda r: r.fragments_count, reverse=True)
        if rows[0].fragments_count > 0:
            return LAW_ELEMENT.get(rows[0].dao_law_id, "Chaos")
    # Fallback: spirit_root tier (still deterministic per player).
    return SPIRIT_ROOT_FALLBACK_ELEMENT.get(player.spirit_root, "Chaos")


def _correct_answers_for(element: str) -> dict[int, str]:
    """Map element → correct answer label per question. Stable strings."""
    return {
        1: "aceitacao" if element in ELEMENTS_Q1 else "renuncia",
        2: "velocidade" if element in ELEMENTS_Q2 else "profundidade",
        3: "novo"       if element in ELEMENTS_Q3 else "manter",
    }


def _foundation_label(quality: str | None, lang: str) -> str:
    """Localised label + emoji like '🌸 Perfeita' or '🪨 Baixa'."""
    if not quality:
        return t(lang, "recomeco_foundation_none")
    info = FOUNDATION_QUALITIES.get(quality, FOUNDATION_QUALITIES["low"])
    return f"{info['emoji']} {t(lang, info['label_key'])}"


def _spirit_root_label(idx: int, lang: str) -> str:
    name = SPIRIT_ROOT_NAMES[idx] if 0 <= idx < len(SPIRIT_ROOT_NAMES) else "?"
    data = list(SPIRIT_ROOTS.values())[idx] if 0 <= idx < len(SPIRIT_ROOTS) else {}
    emoji = data.get("emoji", "")
    return f"{emoji} {name}"


# ─── D-1a: /recomeço ─────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def recomeco_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the one-shot reroll preview + confirm/cancel buttons.

    Dual trigger: works as `/recomeco` command OR as inline `cmd_recomeco`
    callback (button shown in cultivo menu when player is eligible).
    """
    if update.callback_query:
        await safe_answer(update.callback_query)
    target = update.effective_message
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player or target is None:
            return
        lang = player.language or "pt"

        ok, reason = _is_recomeco_eligible(player)
        if not ok:
            await target.reply_text(
                t(lang, reason or "recomeco_err_realm_too_high",
                  realm=player.realm, days=RECOMECO_MAX_AGE_DAYS),
                parse_mode="Markdown",
            )
            return

        text = t(
            lang, "recomeco_preview",
            foundation=escape_markdown(_foundation_label(player.foundation_quality, lang)),
            root=escape_markdown(_spirit_root_label(player.spirit_root, lang)),
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "recomeco_btn_confirm"), callback_data="recomeco_confirm")],
            [InlineKeyboardButton(t(lang, "recomeco_btn_cancel"),  callback_data="recomeco_cancel")],
        ])
        await target.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def recomeco_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"

        # Re-validate the gate atomically — defends against double-tap.
        ok, reason = _is_recomeco_eligible(player)
        if not ok:
            await query.message.edit_text(
                t(lang, reason or "recomeco_err_realm_too_high",
                  realm=player.realm, days=RECOMECO_MAX_AGE_DAYS),
                parse_mode="Markdown",
            )
            return

        old_foundation = player.foundation_quality
        old_root = player.spirit_root
        old_root_label = _spirit_root_label(old_root, lang)
        old_foundation_label = _foundation_label(old_foundation, lang)

        # Foundation reroll — uniform pick across non-Sacred tiers, no
        # weighting (this is the *newbie grace* path; nothing earned).
        # Sacred is excluded — it's reserved for the endgame pill.
        import random
        choices = ["low", "medium", "high", "perfect"]
        weights = [40.0, 35.0, 20.0, 5.0]  # gentle bias to medium-low
        new_foundation = random.choices(choices, weights=weights, k=1)[0]

        # Spirit root reroll — same weights as `vip_root_reroll` in handlers/shop.py
        # but exclude Low (idx 4) so the player can never get worse than Mid.
        # Heavenly stays at 0.01% to preserve narrative rarity.
        root_indices = list(range(len(SPIRIT_ROOT_WEIGHTS)))
        root_weights_no_low = [0.01, 1.0, 19.0, 80.0, 0.0]
        new_root = random.choices(root_indices, weights=root_weights_no_low, k=1)[0]

        player.foundation_quality = new_foundation
        player.spirit_root = new_root
        player.foundation_reroll_used = True

        await session.commit()

        new_foundation_label = _foundation_label(new_foundation, lang)
        new_root_label = _spirit_root_label(new_root, lang)

        await query.message.edit_text(
            t(
                lang, "recomeco_result",
                old_foundation=escape_markdown(old_foundation_label),
                new_foundation=escape_markdown(new_foundation_label),
                old_root=escape_markdown(old_root_label),
                new_root=escape_markdown(new_root_label),
            ),
            parse_mode="Markdown",
        )


async def recomeco_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"
        await query.message.edit_text(t(lang, "recomeco_cancelled"), parse_mode="Markdown")


# ─── D-1b: /quebrar_fundacao ─────────────────────────────────────────────────

def _break_cooldown_remaining(player) -> timedelta | None:
    """Returns timedelta until next break is allowed, or None if ready.

    Cooldown rule: 30 real days OR 1 per rebirth (whichever is shorter).
    We resolve the second clause via `prestige_level`: if last break
    happened in a *previous* rebirth (i.e. realm dropped via prestige
    after break), the rebirth itself acts as a reset → no cooldown.

    To detect that, we compare `last_foundation_break_at` against the
    timestamp of the current rebirth, but we don't store that — so we
    use a simpler proxy: cooldown only applies if `foundation_break_count`
    was incremented *after* the last rebirth. Without a per-rebirth
    timestamp, we conservatively use the 30-day clock as the always-on
    rule and trust prestige to reset the count via prestige_engine.
    """
    if player.last_foundation_break_at is None:
        return None
    elapsed = datetime.now(timezone.utc) - player.last_foundation_break_at
    cooldown = timedelta(days=BREAK_COOLDOWN_DAYS)
    if elapsed >= cooldown:
        return None
    return cooldown - elapsed


def _fmt_remaining(td: timedelta) -> str:
    days = td.days
    hours = td.seconds // 3600
    return f"{days}d {hours}h"


def _required_cb(player) -> int:
    """50% of the player's current cultivation_base — what they pay if they pass."""
    return max(0, int(player.cultivation_base * BREAK_CB_PERCENT))


def _can_afford_break(player) -> tuple[bool, list[str]]:
    """Returns (ok, missing_keys). missing_keys are i18n suffixes for messaging."""
    missing: list[str] = []
    if player.realm < BREAK_MIN_REALM:
        missing.append("realm")
    if player.spirit_stones < BREAK_COST_STONES:
        missing.append("stones")
    if (player.celestial_essence or 0) < BREAK_COST_ESSENCE:
        missing.append("essence")
    return (len(missing) == 0, missing)


@safe_handler
@rate_limit(1)
async def quebrar_fundacao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the ritual preview + costs + start button.

    Dual trigger: works as `/quebrar_fundacao` command OR as inline
    `cmd_quebrar_fund` callback (button shown in cultivo menu for realm 5+
    when cooldown expired).
    """
    if update.callback_query:
        await safe_answer(update.callback_query)
    target = update.effective_message
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player or target is None:
            return
        lang = player.language or "pt"

        if player.realm < BREAK_MIN_REALM:
            await target.reply_text(
                t(lang, "break_err_realm", min_realm=BREAK_MIN_REALM),
                parse_mode="Markdown",
            )
            return

        cooldown = _break_cooldown_remaining(player)
        if cooldown is not None:
            await target.reply_text(
                t(lang, "break_err_cooldown", remaining=_fmt_remaining(cooldown)),
                parse_mode="Markdown",
            )
            return

        cb_cost = _required_cb(player)
        text = t(
            lang, "break_preview",
            foundation=escape_markdown(_foundation_label(player.foundation_quality, lang)),
            cb_cost=cb_cost,
            stones_cost=BREAK_COST_STONES,
            essence_cost=BREAK_COST_ESSENCE,
            stones_have=player.spirit_stones,
            essence_have=player.celestial_essence or 0,
        )

        ok, missing = _can_afford_break(player)
        if ok:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "break_btn_begin"),  callback_data="break_begin")],
                [InlineKeyboardButton(t(lang, "break_btn_cancel"), callback_data="break_cancel")],
            ])
        else:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(t(lang, "break_btn_cancel"), callback_data="break_cancel")],
            ])
            text += "\n\n" + t(lang, "break_err_missing", which=", ".join(missing))

        await target.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def break_begin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open Q1. Costs are charged here, before the trial — failure does NOT refund."""
    query = update.callback_query
    await safe_answer(query)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"

        # Re-validate atomically — guards double-tap and stale clicks.
        if player.realm < BREAK_MIN_REALM:
            await query.message.edit_text(
                t(lang, "break_err_realm", min_realm=BREAK_MIN_REALM),
                parse_mode="Markdown",
            )
            return
        if _break_cooldown_remaining(player) is not None:
            await query.message.edit_text(
                t(lang, "break_err_cooldown",
                  remaining=_fmt_remaining(_break_cooldown_remaining(player))),
                parse_mode="Markdown",
            )
            return
        ok, missing = _can_afford_break(player)
        if not ok:
            await query.message.edit_text(
                t(lang, "break_err_missing", which=", ".join(missing)),
                parse_mode="Markdown",
            )
            return

        # Charge costs IMMEDIATELY — the act of breaking the foundation
        # is the cost. Outcome only modulates the rebuild quality.
        cb_cost = _required_cb(player)
        player.cultivation_base = max(0.0, player.cultivation_base - cb_cost)
        player.spirit_stones -= BREAK_COST_STONES
        player.celestial_essence = max(0, (player.celestial_essence or 0) - BREAK_COST_ESSENCE)

        # Pre-compute correct answers based on the player's path; cache in
        # context.user_data so the trial flow doesn't need DB hits per Q.
        element = await _dominant_supreme_element(session, player)
        correct = _correct_answers_for(element)
        context.user_data["break_score"] = 0
        context.user_data["break_correct"] = correct
        context.user_data["break_element"] = element

        await session.commit()

        # Render Q1
        await _render_break_question(query, lang, q_idx=1)


async def _render_break_question(query, lang: str, q_idx: int):
    """Render Q1/Q2/Q3 prompt + 2 answer buttons. Stateless beyond q_idx."""
    if q_idx == 1:
        text = t(lang, "break_q1_prompt")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "break_q1_a_renuncia"),  callback_data="break_a1_renuncia")],
            [InlineKeyboardButton(t(lang, "break_q1_a_aceitacao"), callback_data="break_a1_aceitacao")],
        ])
    elif q_idx == 2:
        text = t(lang, "break_q2_prompt")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "break_q2_a_velocidade"),   callback_data="break_a2_velocidade")],
            [InlineKeyboardButton(t(lang, "break_q2_a_profundidade"), callback_data="break_a2_profundidade")],
        ])
    else:
        text = t(lang, "break_q3_prompt")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "break_q3_a_manter"), callback_data="break_a3_manter")],
            [InlineKeyboardButton(t(lang, "break_q3_a_novo"),   callback_data="break_a3_novo")],
        ])
    await query.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


async def break_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process Q1/Q2/Q3 answer. Format: break_a{q}_{answer_key}."""
    query = update.callback_query
    await safe_answer(query)

    correct = context.user_data.get("break_correct")
    if correct is None:
        # State lost (bot restart, /quebrar_fundacao not started). Cannot resume safely.
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            lang = (player.language if player else None) or "pt"
        await query.message.edit_text(t(lang, "break_err_state_lost"), parse_mode="Markdown")
        return

    # Parse data: break_a{q}_{answer}
    payload = query.data.replace("break_a", "", 1)
    try:
        q_str, answer = payload.split("_", 1)
        q_idx = int(q_str)
    except (ValueError, IndexError):
        return

    is_correct = correct.get(q_idx) == answer
    if is_correct:
        context.user_data["break_score"] = context.user_data.get("break_score", 0) + 1

    if q_idx < 3:
        async with get_session_factory()() as session:
            player = await _ensure_player(update, session)
            lang = (player.language if player else None) or "pt"
        await _render_break_question(query, lang, q_idx + 1)
        return

    # All 3 questions answered → settle
    score = context.user_data.get("break_score", 0)
    element = context.user_data.get("break_element", "Chaos")
    context.user_data.pop("break_score", None)
    context.user_data.pop("break_correct", None)
    context.user_data.pop("break_element", None)

    await _settle_break_trial(update, context, query, score, element)


async def _settle_break_trial(update, context, query, score: int, element: str):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "pt"

        old_foundation = player.foundation_quality

        table = RITUAL_REROLL_TABLES.get(score, RITUAL_REROLL_TABLES[1])
        new_foundation = roll_from_table(table)
        player.foundation_quality = new_foundation
        player.foundation_break_count = (player.foundation_break_count or 0) + 1
        player.last_foundation_break_at = datetime.now(timezone.utc)

        await session.commit()

        old_label = _foundation_label(old_foundation, lang)
        new_label = _foundation_label(new_foundation, lang)

        # Result render — distinct copy for each score band so the player
        # *feels* the verdict differently. 0/3 is the public humiliation.
        if score == 3:
            result_key = "break_result_perfect_run"
        elif score == 2:
            result_key = "break_result_good_run"
        elif score == 1:
            result_key = "break_result_weak_run"
        else:
            result_key = "break_result_failed_run"

        text = t(
            lang, result_key,
            element=element,
            score=score,
            old_foundation=escape_markdown(old_label),
            new_foundation=escape_markdown(new_label),
        )
        await query.message.edit_text(text, parse_mode="Markdown")


async def break_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    # No charges made yet — just clear local state.
    context.user_data.pop("break_score", None)
    context.user_data.pop("break_correct", None)
    context.user_data.pop("break_element", None)
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        lang = (player.language if player else None) or "pt"
    await query.message.edit_text(t(lang, "break_cancelled"), parse_mode="Markdown")


# ─── Router glue (called from main.combined_button_router) ───────────────────

async def foundation_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Returns True if the callback was handled by this module."""
    query = update.callback_query
    if query is None or query.data is None:
        return False
    data = query.data

    if data == "recomeco_confirm":
        await recomeco_confirm_callback(update, context)
        return True
    if data == "recomeco_cancel":
        await recomeco_cancel_callback(update, context)
        return True
    if data == "break_begin":
        await break_begin_callback(update, context)
        return True
    if data == "break_cancel":
        await break_cancel_callback(update, context)
        return True
    if data.startswith("break_a"):
        await break_answer_callback(update, context)
        return True
    # 2026-05-17: inline entry points (replace standalone `/recomeco` and
    # `/quebrar_fundacao` commands per owner UX feedback). The buttons appear
    # in cultivo_menu_keyboard only when the player is eligible.
    if data == "cmd_recomeco":
        await recomeco_command(update, context)
        return True
    if data == "cmd_quebrar_fund":
        await quebrar_fundacao_command(update, context)
        return True
    return False
