from sqlalchemy import select
from database.models import CelestialEvent


CELESTIAL_EVENTS = [
    {
        "name": "Meteor Shower",
        "type": "meteor_shower",
        "description": "Heavenly stones rain from the sky, blessing dungeons and expeditions with bountiful loot.",
        "multipliers": {"loot_mult": 2.0},
        "duration_hours": 48,
        "emoji": "☄️",
    },
    {
        "name": "Dao Convergence",
        "type": "dao_convergence",
        "description": "The Dao Laws converge, flooding the world with spiritual energy and tripling cultivation gains.",
        "multipliers": {"cb_mult": 3.0},
        "duration_hours": 6,
        "emoji": "☯️",
    },
    {
        "name": "Immortal Auction",
        "type": "immortal_auction",
        "description": "A mysterious Immortal merchant appears, injecting rare artifacts and pills into the marketplace.",
        "multipliers": {"market_npc": 1.0},
        "duration_hours": 48,
        "emoji": "🏮",
    },
    {
        "name": "Spirit Tide",
        "type": "spirit_tide",
        "description": "A great tide of spiritual energy washes over Qiankun, dramatically accelerating Qi regeneration.",
        "multipliers": {"qi_regen_mult": 3.0},
        "duration_hours": 24,
        "emoji": "🌊",
    },
    {
        "name": "Demonic Invasion",
        "type": "demonic_invasion",
        "description": "A great Demon Lord descends upon the mortal world. The World Boss gains double HP but drops triple loot.",
        "multipliers": {"boss_hp_mult": 2.0, "boss_loot_mult": 3.0},
        "duration_hours": 24,
        "emoji": "👹",
    },
]


async def run_events_seeds(session):
    for ev_data in CELESTIAL_EVENTS:
        existing = (
            await session.execute(
                select(CelestialEvent).where(CelestialEvent.type == ev_data["type"])
            )
        ).scalar_one_or_none()

        if existing:
            # Update fields in case they changed, but never touch is_active/started_at/expires_at
            existing.name = ev_data["name"]
            existing.description = ev_data["description"]
            existing.multipliers = ev_data["multipliers"]
            existing.duration_hours = ev_data["duration_hours"]
            existing.emoji = ev_data["emoji"]
        else:
            session.add(
                CelestialEvent(
                    name=ev_data["name"],
                    type=ev_data["type"],
                    description=ev_data["description"],
                    multipliers=ev_data["multipliers"],
                    duration_hours=ev_data["duration_hours"],
                    emoji=ev_data["emoji"],
                    is_active=False,
                )
            )

    await session.commit()
