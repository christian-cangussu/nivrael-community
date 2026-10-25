import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DaoPartner, DaoPartnerProposal, Player, PlayerBuff, PlayerInventory

logger = logging.getLogger(__name__)


async def get_player_partner(session: AsyncSession, player_id: int):
    """Returns (DaoPartner, partner_player) or (None, None)."""
    stmt = select(DaoPartner).where(
        or_(DaoPartner.player1_id == player_id, DaoPartner.player2_id == player_id)
    )
    partner_rec = (await session.execute(stmt)).scalar_one_or_none()
    if not partner_rec:
        return None, None

    partner_id = partner_rec.player2_id if partner_rec.player1_id == player_id else partner_rec.player1_id
    partner_player = (await session.execute(
        select(Player).where(Player.telegram_id == partner_id)
    )).scalar_one_or_none()
    return partner_rec, partner_player


async def get_partner_cb_mult(session: AsyncSession, player_id: int) -> float:
    """Returns 1.1 if both partners were online in the last 24h (Dual Cultivation)."""
    stmt = select(DaoPartner).where(
        or_(DaoPartner.player1_id == player_id, DaoPartner.player2_id == player_id)
    )
    partner_rec = (await session.execute(stmt)).scalar_one_or_none()
    if not partner_rec:
        return 1.0

    partner_id = partner_rec.player2_id if partner_rec.player1_id == player_id else partner_rec.player1_id
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    player_last_online = (await session.execute(
        select(Player.last_online).where(Player.telegram_id == player_id)
    )).scalar_one_or_none()
    partner_online = (await session.execute(
        select(Player.last_online).where(Player.telegram_id == partner_id)
    )).scalar_one_or_none()

    if not player_last_online or not partner_online:
        return 1.0
    if player_last_online > cutoff and partner_online > cutoff:
        return 1.1
    return 1.0


async def get_pending_proposals(session: AsyncSession, player_id: int) -> list:
    """Returns non-expired pending proposals targeting this player."""
    now = datetime.now(timezone.utc)
    stmt = select(DaoPartnerProposal).where(
        DaoPartnerProposal.target_id == player_id,
        DaoPartnerProposal.status == "pending",
        DaoPartnerProposal.expires_at > now,
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_sent_proposal(session: AsyncSession, proposer_id: int):
    """Returns a pending proposal sent by this player, if any."""
    now = datetime.now(timezone.utc)
    stmt = select(DaoPartnerProposal).where(
        DaoPartnerProposal.proposer_id == proposer_id,
        DaoPartnerProposal.status == "pending",
        DaoPartnerProposal.expires_at > now,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def has_jade_ring(session: AsyncSession, player_id: int) -> bool:
    stmt = select(PlayerInventory).where(
        PlayerInventory.player_id == player_id,
        PlayerInventory.item_type == "jade_ring",
        PlayerInventory.quantity > 0,
    )
    return (await session.execute(stmt)).scalars().first() is not None


async def consume_jade_ring(session: AsyncSession, player_id: int) -> bool:
    stmt = select(PlayerInventory).where(
        PlayerInventory.player_id == player_id,
        PlayerInventory.item_type == "jade_ring",
        PlayerInventory.quantity > 0,
    )
    inv = (await session.execute(stmt)).scalars().first()
    if not inv:
        return False
    inv.quantity -= 1
    if inv.quantity <= 0:
        await session.delete(inv)
    return True


async def has_romantic_cooldown(session: AsyncSession, player_id: int) -> bool:
    now = datetime.now(timezone.utc)
    stmt = select(PlayerBuff).where(
        PlayerBuff.player_id == player_id,
        PlayerBuff.buff_type == "romantic_cooldown",
        PlayerBuff.expires_at > now,
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def get_romantic_cooldown_remaining(session: AsyncSession, player_id: int) -> float:
    """Returns seconds remaining in romantic cooldown, 0 if none."""
    now = datetime.now(timezone.utc)
    stmt = select(PlayerBuff).where(
        PlayerBuff.player_id == player_id,
        PlayerBuff.buff_type == "romantic_cooldown",
        PlayerBuff.expires_at > now,
    )
    buff = (await session.execute(stmt)).scalar_one_or_none()
    if not buff:
        return 0.0
    return (buff.expires_at - now).total_seconds()


async def get_heartbreak_remaining(session: AsyncSession, player_id: int) -> float:
    """Returns seconds remaining in heartbreak CB penalty, 0 if none."""
    now = datetime.now(timezone.utc)
    stmt = select(PlayerBuff).where(
        PlayerBuff.player_id == player_id,
        PlayerBuff.buff_type == "heartbreak",
        PlayerBuff.expires_at > now,
    )
    buff = (await session.execute(stmt)).scalar_one_or_none()
    if not buff:
        return 0.0
    return (buff.expires_at - now).total_seconds()


async def apply_heartbreak(session: AsyncSession, player_id: int):
    """Apply heartbreak debuffs (romantic cooldown + −10% CB penalty) for 48h."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=48)

    for buff_type, buff_value in [("romantic_cooldown", 1.0), ("heartbreak", 0.9)]:
        existing = (await session.execute(
            select(PlayerBuff).where(
                PlayerBuff.player_id == player_id,
                PlayerBuff.buff_type == buff_type,
            )
        )).scalar_one_or_none()
        if existing:
            existing.expires_at = expires
        else:
            session.add(PlayerBuff(
                player_id=player_id,
                buff_type=buff_type,
                buff_value=buff_value,
                source="heartbreak",
                expires_at=expires,
            ))


async def increment_intimacy_if_both_online(session: AsyncSession, partner_rec: DaoPartner) -> bool:
    """Increments intimacy by 1 if both partners were online in the last hour. Returns True if incremented."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=1)

    p1_online = (await session.execute(
        select(Player.last_online).where(Player.telegram_id == partner_rec.player1_id)
    )).scalar_one_or_none()
    p2_online = (await session.execute(
        select(Player.last_online).where(Player.telegram_id == partner_rec.player2_id)
    )).scalar_one_or_none()

    if not p1_online or not p2_online:
        return False
    if p1_online > cutoff and p2_online > cutoff:
        partner_rec.intimacy_level += 1
        return True
    return False
