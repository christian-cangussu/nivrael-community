import logging
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from sqlalchemy import select, or_, delete, func

from core.i18n import t
from core.utils import safe_handler, rate_limit, _ensure_player, _get_player, get_display_name, escape_markdown, safe_answer
from core.game_logic import get_time_display
from core.partner_engine import (
    get_player_partner,
    get_pending_proposals,
    get_sent_proposal,
    has_jade_ring,
    consume_jade_ring,
    has_romantic_cooldown,
    get_romantic_cooldown_remaining,
    get_heartbreak_remaining,
    apply_heartbreak,
    increment_intimacy_if_both_online,
)
from database.db import get_session_factory
from database.models import DaoPartner, DaoPartnerProposal, Player

logger = logging.getLogger(__name__)


# ─── Keyboards ────────────────────────────────────────────────────────────────

def _partner_no_partner_kb(lang: str, pending_count: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(t(lang, "partner_propose_btn"), callback_data="partner_propose_init")],
    ]
    if pending_count > 0:
        rows.append([InlineKeyboardButton(
            t(lang, "partner_view_proposals_btn", count=pending_count),
            callback_data="partner_proposals_list"
        )])
    rows.append([InlineKeyboardButton(t(lang, "nav_main"), callback_data="nav_main")])
    return InlineKeyboardMarkup(rows)


def _partner_has_partner_kb(lang: str, pending_count: int = 0) -> InlineKeyboardMarkup:
    rows = []
    if pending_count > 0:
        rows.append([InlineKeyboardButton(
            t(lang, "partner_view_proposals_btn", count=pending_count),
            callback_data="partner_proposals_list"
        )])
    rows.append([InlineKeyboardButton(t(lang, "partner_cut_bond_btn"), callback_data="partner_cut_confirm")])
    rows.append([InlineKeyboardButton(t(lang, "nav_main"), callback_data="nav_main")])
    return InlineKeyboardMarkup(rows)


def _partner_cut_confirm_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "partner_cut_confirm_btn"), callback_data="partner_cut_execute")],
        [InlineKeyboardButton(t(lang, "partner_cancel_btn"), callback_data="partner_menu")],
    ])


def _proposal_kb(lang: str, proposal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t(lang, "partner_accept_btn"), callback_data=f"partner_accept_{proposal_id}"),
            InlineKeyboardButton(t(lang, "partner_reject_btn"), callback_data=f"partner_reject_{proposal_id}"),
        ]
    ])


def _proposals_list_kb(lang: str, proposals: list, proposers: dict) -> InlineKeyboardMarkup:
    rows = []
    for prop in proposals:
        proposer = proposers.get(prop.proposer_id)
        name = proposer.dao_name or get_display_name(proposer) if proposer else "???"
        rows.append([
            InlineKeyboardButton(f"✅ {name}", callback_data=f"partner_accept_{prop.id}"),
            InlineKeyboardButton(f"❌", callback_data=f"partner_reject_{prop.id}"),
        ])
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")])
    return InlineKeyboardMarkup(rows)


# ─── Text Builders ─────────────────────────────────────────────────────────────

async def _build_partner_menu_text(session, player, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    now = datetime.now(timezone.utc)
    separator = "—" * 24

    partner_rec, partner_player = await get_player_partner(session, player.telegram_id)
    pending_proposals = await get_pending_proposals(session, player.telegram_id)

    # Increment intimacy passively when viewed
    if partner_rec:
        await increment_intimacy_if_both_online(session, partner_rec)

    heartbreak_secs = await get_heartbreak_remaining(session, player.telegram_id)
    romantic_secs = await get_romantic_cooldown_remaining(session, player.telegram_id)

    lines = [t(lang, "partner_title"), separator]

    if partner_rec and partner_player:
        partner_name = escape_markdown(partner_player.dao_name or get_display_name(partner_player))

        # Check dual cultivation status
        cutoff = now - timedelta(hours=24)
        partner_online = partner_player.last_online and partner_player.last_online > cutoff
        if partner_online:
            dual_str = t(lang, "partner_dual_cult_active")
        else:
            dual_str = t(lang, "partner_dual_cult_inactive")

        # Luck sharing: 5% of partner's luck
        luck_share = int(partner_player.luck * 0.05)
        married_days = (now - partner_rec.married_at).days

        lines += [
            t(lang, "partner_info",
              name=partner_name,
              ring_level=partner_rec.ring_level,
              intimacy=partner_rec.intimacy_level,
              days=married_days),
            separator,
            dual_str,
            t(lang, "partner_luck_share", value=luck_share),
        ]

        if heartbreak_secs > 0:
            lines.append(t(lang, "partner_heartbreak_active", time=get_time_display(heartbreak_secs)))

        kb = _partner_has_partner_kb(lang, len(pending_proposals))

    else:
        lines.append(t(lang, "partner_no_partner"))

        if heartbreak_secs > 0:
            lines.append(separator)
            lines.append(t(lang, "partner_heartbreak_active", time=get_time_display(heartbreak_secs)))

        if romantic_secs > 0:
            lines.append(t(lang, "partner_romantic_cooldown", time=get_time_display(romantic_secs)))

        if pending_proposals:
            lines.append(separator)
            lines.append(t(lang, "partner_pending_proposals", count=len(pending_proposals)))

        kb = _partner_no_partner_kb(lang, len(pending_proposals))

    return "\n".join(lines), kb


# ─── Main Handler ──────────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def partner_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with get_session_factory()() as session:
        player = await _ensure_player(update, session)
        if not player:
            return
        lang = player.language or "en"
        text, kb = await _build_partner_menu_text(session, player, lang)
        await session.commit()

    if update.callback_query:
        await safe_answer(update.callback_query)
        try:
            await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
        except Exception as e:
            if "Message is not modified" not in str(e):
                raise
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")


# ─── Proposal Flow ─────────────────────────────────────────────────────────────

async def _partner_propose_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = player.language or "en"

        # Check if already partnered
        partner_rec, _ = await get_player_partner(session, player.telegram_id)
        if partner_rec:
            await query.edit_message_text(t(lang, "partner_already_partnered"), parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")]]))
            return

        # Check romantic cooldown
        if await has_romantic_cooldown(session, player.telegram_id):
            secs = await get_romantic_cooldown_remaining(session, player.telegram_id)
            await query.edit_message_text(
                t(lang, "partner_cooldown_active", time=get_time_display(secs)),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")]]),
            )
            return

        # Check jade ring
        if not await has_jade_ring(session, player.telegram_id):
            await query.edit_message_text(t(lang, "partner_no_ring"), parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")]]))
            return

        # Check already sent a proposal
        existing_proposal = await get_sent_proposal(session, player.telegram_id)
        if existing_proposal:
            target_p = (await session.execute(select(Player).where(Player.telegram_id == existing_proposal.target_id))).scalar_one_or_none()
            target_name = target_p.dao_name or get_display_name(target_p) if target_p else "???"
            await query.edit_message_text(
                t(lang, "partner_already_proposed", name=escape_markdown(target_name)),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")]]),
            )
            return

    context.user_data["awaiting_partner_proposal"] = True
    await query.edit_message_text(
        t(lang, "partner_propose_enter_name"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "partner_cancel_btn"), callback_data="partner_propose_cancel")]]),
    )


async def _partner_propose_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("awaiting_partner_proposal", None)
    await partner_menu(update, context)


@safe_handler
async def process_partner_proposal_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called from message dispatcher when awaiting_partner_proposal is True."""
    context.user_data.pop("awaiting_partner_proposal", None)
    user = update.effective_user
    dao_name_input = update.message.text.strip()

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = player.language or "en"

        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")]])

        # Find target by dao_name — case-insensitive
        target = (await session.execute(
            select(Player).where(func.lower(Player.dao_name) == dao_name_input.lower())
        )).scalar_one_or_none()
        if not target:
            await update.message.reply_text(t(lang, "partner_not_found"), reply_markup=back_kb, parse_mode="Markdown")
            return

        if target.telegram_id == player.telegram_id:
            await update.message.reply_text(t(lang, "partner_self_propose"), reply_markup=back_kb, parse_mode="Markdown")
            return

        # Check neither is already partnered
        for pid in [player.telegram_id, target.telegram_id]:
            rec, _ = await get_player_partner(session, pid)
            if rec:
                await update.message.reply_text(t(lang, "partner_already_partnered"), reply_markup=back_kb, parse_mode="Markdown")
                return

        # Check romantic cooldown on proposer
        if await has_romantic_cooldown(session, player.telegram_id):
            secs = await get_romantic_cooldown_remaining(session, player.telegram_id)
            await update.message.reply_text(t(lang, "partner_cooldown_active", time=get_time_display(secs)), reply_markup=back_kb, parse_mode="Markdown")
            return

        # Check target romantic cooldown
        if await has_romantic_cooldown(session, target.telegram_id):
            await update.message.reply_text(t(lang, "partner_already_partnered"), reply_markup=back_kb, parse_mode="Markdown")
            return

        # Consume jade ring
        if not await consume_jade_ring(session, player.telegram_id):
            await update.message.reply_text(t(lang, "partner_no_ring"), reply_markup=back_kb, parse_mode="Markdown")
            return

        # Delete any existing proposal between these two
        await session.execute(
            delete(DaoPartnerProposal).where(
                DaoPartnerProposal.proposer_id == player.telegram_id,
                DaoPartnerProposal.target_id == target.telegram_id,
            )
        )

        # Create proposal
        proposal = DaoPartnerProposal(
            proposer_id=player.telegram_id,
            target_id=target.telegram_id,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        )
        session.add(proposal)
        await session.commit()

        proposal_id = str(proposal.id)
        proposer_name = escape_markdown(player.dao_name or get_display_name(player))
        target_lang = target.language

    # Notify proposer
    await update.message.reply_text(
        t(lang, "partner_proposal_sent", name=escape_markdown(target.dao_name or get_display_name(target))),
        reply_markup=back_kb,
        parse_mode="Markdown",
    )

    # Notify target
    try:
        target_kb = _proposal_kb(target_lang, proposal_id)
        await context.bot.send_message(
            chat_id=target.telegram_id,
            text=t(target_lang, "partner_proposal_notification", name=proposer_name),
            reply_markup=target_kb,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Could not notify partner proposal target {target.telegram_id}: {e}")


# ─── Accept / Reject ──────────────────────────────────────────────────────────

async def _partner_accept(update: Update, context: ContextTypes.DEFAULT_TYPE, proposal_id: str):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = player.language or "en"

        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")]])

        try:
            import uuid
            prop_uuid = uuid.UUID(proposal_id)
        except ValueError:
            await query.edit_message_text("❌ Invalid proposal.", reply_markup=back_kb)
            return

        proposal = (await session.execute(
            select(DaoPartnerProposal).where(
                DaoPartnerProposal.id == prop_uuid,
                DaoPartnerProposal.target_id == player.telegram_id,
                DaoPartnerProposal.status == "pending",
            )
        )).scalar_one_or_none()

        if not proposal:
            await query.edit_message_text(t(lang, "partner_not_found"), reply_markup=back_kb, parse_mode="Markdown")
            return

        now = datetime.now(timezone.utc)
        if proposal.expires_at < now:
            proposal.status = "expired"
            await session.commit()
            await query.edit_message_text(t(lang, "partner_not_found"), reply_markup=back_kb, parse_mode="Markdown")
            return

        # Check neither is partnered
        for pid in [proposal.proposer_id, proposal.target_id]:
            rec, _ = await get_player_partner(session, pid)
            if rec:
                proposal.status = "cancelled"
                await session.commit()
                await query.edit_message_text(t(lang, "partner_already_partnered"), reply_markup=back_kb, parse_mode="Markdown")
                return

        proposer = (await session.execute(
            select(Player).where(Player.telegram_id == proposal.proposer_id)
        )).scalar_one_or_none()

        # Create partnership
        p1, p2 = sorted([proposal.proposer_id, proposal.target_id])
        session.add(DaoPartner(
            player1_id=p1,
            player2_id=p2,
            intimacy_level=0,
            married_at=now,
            ring_level=1,
        ))

        proposal.status = "accepted"

        # Cancel all other proposals for both players
        await session.execute(
            delete(DaoPartnerProposal).where(
                DaoPartnerProposal.id != prop_uuid,
                or_(
                    DaoPartnerProposal.proposer_id.in_([proposal.proposer_id, proposal.target_id]),
                    DaoPartnerProposal.target_id.in_([proposal.proposer_id, proposal.target_id]),
                ),
            )
        )
        await session.commit()

        proposer_name = escape_markdown(proposer.dao_name or get_display_name(proposer)) if proposer else "???"
        player_name = escape_markdown(player.dao_name or get_display_name(player))
        proposer_lang = proposer.language if proposer else "pt"

    # Notify acceptor
    await query.edit_message_text(
        t(lang, "partner_you_accepted", name=proposer_name),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_dao_partner"), callback_data="partner_menu")]]),
    )

    # Notify proposer
    if proposer:
        try:
            await context.bot.send_message(
                chat_id=proposal.proposer_id,
                text=t(proposer_lang, "partner_proposal_accepted", name=player_name),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(proposer_lang, "btn_dao_partner"), callback_data="partner_menu")]]),
            )
        except Exception as e:
            logger.warning(f"Could not notify proposer {proposal.proposer_id}: {e}")


async def _partner_reject(update: Update, context: ContextTypes.DEFAULT_TYPE, proposal_id: str):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = player.language or "en"

        try:
            import uuid
            prop_uuid = uuid.UUID(proposal_id)
        except ValueError:
            await safe_answer(query, "Invalid.")
            return

        proposal = (await session.execute(
            select(DaoPartnerProposal).where(
                DaoPartnerProposal.id == prop_uuid,
                DaoPartnerProposal.target_id == player.telegram_id,
                DaoPartnerProposal.status == "pending",
            )
        )).scalar_one_or_none()

        if not proposal:
            await query.edit_message_text(
                t(lang, "partner_not_found"),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")]]),
            )
            return

        proposer_id = proposal.proposer_id
        proposer = (await session.execute(
            select(Player).where(Player.telegram_id == proposer_id)
        )).scalar_one_or_none()
        proposer_lang = proposer.language if proposer else "pt"
        player_name = escape_markdown(player.dao_name or get_display_name(player))

        proposal.status = "rejected"
        await session.commit()

    await query.edit_message_text(
        t(lang, "partner_you_rejected"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")]]),
    )

    try:
        await context.bot.send_message(
            chat_id=proposer_id,
            text=t(proposer_lang, "partner_proposal_rejected", name=player_name),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Could not notify rejection to {proposer_id}: {e}")


# ─── Proposals List ───────────────────────────────────────────────────────────

async def _partner_proposals_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = player.language or "en"

        proposals = await get_pending_proposals(session, player.telegram_id)
        if not proposals:
            await query.edit_message_text(
                t(lang, "partner_no_proposals"),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="partner_menu")]]),
            )
            return

        proposers = {}
        for prop in proposals:
            p = (await session.execute(select(Player).where(Player.telegram_id == prop.proposer_id))).scalar_one_or_none()
            proposers[prop.proposer_id] = p

    lines = [t(lang, "partner_proposals_title"), "—" * 24]
    now = datetime.now(timezone.utc)
    for prop in proposals:
        proposer = proposers.get(prop.proposer_id)
        name = escape_markdown(proposer.dao_name or get_display_name(proposer)) if proposer else "???"
        remaining = max(0, (prop.expires_at - now).total_seconds())
        lines.append(t(lang, "partner_proposal_from", name=name, time=get_time_display(remaining)))

    kb = _proposals_list_kb(lang, proposals, proposers)
    await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode="Markdown")


# ─── Cut Bond ─────────────────────────────────────────────────────────────────

async def _partner_cut_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = player.language or "en"

        partner_rec, partner_player = await get_player_partner(session, player.telegram_id)
        if not partner_rec:
            await partner_menu(update, context)
            return

        partner_name = escape_markdown(partner_player.dao_name or get_display_name(partner_player)) if partner_player else "???"

    await query.edit_message_text(
        t(lang, "partner_cut_confirm_title", name=partner_name),
        parse_mode="Markdown",
        reply_markup=_partner_cut_confirm_kb(lang),
    )


async def _partner_cut_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    user = update.effective_user

    async with get_session_factory()() as session:
        player = await _get_player(user.id, session)
        if not player:
            return
        lang = player.language or "en"

        partner_rec, partner_player = await get_player_partner(session, player.telegram_id)
        if not partner_rec:
            await partner_menu(update, context)
            return

        partner_id = partner_player.telegram_id if partner_player else None
        partner_lang = partner_player.language if partner_player else "pt"
        partner_name = escape_markdown(partner_player.dao_name or get_display_name(partner_player)) if partner_player else "???"
        player_name = escape_markdown(player.dao_name or get_display_name(player))

        # Delete partnership
        await session.delete(partner_rec)

        # Apply heartbreak to both players
        await apply_heartbreak(session, player.telegram_id)
        if partner_id:
            await apply_heartbreak(session, partner_id)

        await session.commit()

    await query.edit_message_text(
        t(lang, "partner_cut_done"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_dao_partner"), callback_data="partner_menu")]]),
    )

    if partner_id and partner_player:
        try:
            await context.bot.send_message(
                chat_id=partner_id,
                text=t(partner_lang, "partner_bond_severed_notify", name=player_name),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.warning(f"Could not notify bond severance to {partner_id}: {e}")


# ─── Button Router ─────────────────────────────────────────────────────────────

@safe_handler
@rate_limit(1)
async def partner_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    query = update.callback_query
    data = query.data

    if data == "partner_menu":
        await partner_menu(update, context)
        return True
    if data == "partner_propose_init":
        await _partner_propose_init(update, context)
        return True
    if data == "partner_propose_cancel":
        context.user_data.pop("awaiting_partner_proposal", None)
        await partner_menu(update, context)
        return True
    if data == "partner_proposals_list":
        await _partner_proposals_list(update, context)
        return True
    if data == "partner_cut_confirm":
        await _partner_cut_confirm(update, context)
        return True
    if data == "partner_cut_execute":
        await _partner_cut_execute(update, context)
        return True
    if data.startswith("partner_accept_"):
        proposal_id = data[len("partner_accept_"):]
        await _partner_accept(update, context, proposal_id)
        return True
    if data.startswith("partner_reject_"):
        proposal_id = data[len("partner_reject_"):]
        await _partner_reject(update, context, proposal_id)
        return True

    return False
