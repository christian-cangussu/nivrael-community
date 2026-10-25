-- v16.4c — Sect Library + Ranks + Sect Quests. Gives the 9 NPC houses an
-- INTERIOR: a rank ladder the disciple climbs, a contribution counter that
-- earns the climb, member-gated narrative quests, and a Library of signature
-- techniques the house teaches by rank.
--
-- This migration is the STRUCTURE layer only. Three additive columns:
--   * players.sect_contribution   — the NPC-sect rank currency. SEPARATE from
--     the player-GUILD's contribution (sect_members.contribution_points /
--     sect_contribution_log, migration 045) — those are the UUID `sects` table
--     (a player alliance); this is the String(32) `world_sects` house. Never
--     conflate the two economies.
--   * quests_catalog.sect_id      — tags a quest to a house (NULL = universal
--     sect quest, shown to ANY member; a key = house-specific). Member-gating
--     is enforced in the quest engine (only sect members materialize them).
--   * techniques_catalog.sect_key — marks a technique as a house signature art.
--     v16.4c grants these ADDITIVELY (a normal player_techniques row, no scroll)
--     and EXCLUDES them from the live drop/scroll/learnable pools so they never
--     collide with the scrolls the 57 paying players already own. The
--     "Library = primary technique source + drop-rate cut" switch stays DEFERRED
--     to the wipe (v16.5) — Lei §5.
--
-- The `world_sects.signature_techs` JSONB column ALREADY exists (migration 105)
-- so the Library payload needs NO migration — it is a pure seed-sync
-- (database/seeds/world_sects_seeds.py force-updates the 9 live rows).
--
-- Backwards-compat contract (CLAUDE.md security rules + Lei Primordial §5):
--   * ADD COLUMN IF NOT EXISTS only — neutral default for the 57 live players
--     (sect_contribution = 0; sect_id / sect_key = NULL)
--   * CREATE INDEX IF NOT EXISTS
--   * no DROP, no rename of any existing object
--   * survives the launch wipe (columns are launch-permanent)

-- The NPC-sect rank currency. DEFAULT 0 is neutral: every existing player
-- (affiliated or not) starts the ladder at zero contribution.
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS sect_contribution INTEGER NOT NULL DEFAULT 0;

-- Tags a quest to a house. NULL = universal sect quest (any member sees it);
-- a world_sects.id = house-specific. FK keeps it referentially honest.
ALTER TABLE quests_catalog
    ADD COLUMN IF NOT EXISTS sect_id VARCHAR(32) REFERENCES world_sects(id);

-- Marks a catalog technique as a house signature art (== world_sects.id).
-- NULL = an ordinary technique (drops/scrolls as today). A key = Library-only,
-- excluded from drop/scroll pools until the wipe wires the new economy.
ALTER TABLE techniques_catalog
    ADD COLUMN IF NOT EXISTS sect_key VARCHAR(32);

-- Sect-quest listing scans by (type='sect', sect_id) — a partial index keeps it cheap.
CREATE INDEX IF NOT EXISTS idx_quests_sect ON quests_catalog(sect_id) WHERE sect_id IS NOT NULL;
-- Drop/learnable pools exclude house signatures via sect_key IS NULL — index the marked rows.
CREATE INDEX IF NOT EXISTS idx_tech_sect_key ON techniques_catalog(sect_key) WHERE sect_key IS NOT NULL;
