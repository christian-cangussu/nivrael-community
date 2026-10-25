from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import MarketplaceListing


async def run_partner_seeds(session: AsyncSession):
    """Ensure the Jade Ring NPC listing exists in the marketplace."""
    # Temporarily disabled: Jade rings should not be listed on the market in stacks of 999.
    pass
