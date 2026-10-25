-- Migration 007: Add dao_name to players + backfill existing records
-- All statements are idempotent (safe to re-run).

-- ============================================================
-- Add dao_name column (unique, nullable)
-- ============================================================
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS dao_name VARCHAR(32) UNIQUE;

CREATE INDEX IF NOT EXISTS idx_players_dao_name ON players(dao_name);

-- ============================================================
-- Backfill existing players: use username if available,
-- otherwise fall back to "Cultivator_" + first 6 digits of telegram_id
-- ============================================================
UPDATE players
SET dao_name = CASE
    WHEN username IS NOT NULL AND username <> '' THEN LEFT(username, 32)
    ELSE 'Cultivator_' || LEFT(telegram_id::TEXT, 6)
END
WHERE dao_name IS NULL;

-- Resolve potential collisions from duplicate usernames or id prefixes
-- by appending the last 4 digits of telegram_id to duplicates (keep first occurrence)
WITH dupes AS (
    SELECT telegram_id,
           dao_name,
           ROW_NUMBER() OVER (PARTITION BY dao_name ORDER BY created_at) AS rn
    FROM players
    WHERE dao_name IS NOT NULL
)
UPDATE players p
SET dao_name = LEFT(d.dao_name, 27) || '_' || RIGHT(p.telegram_id::TEXT, 4)
FROM dupes d
WHERE p.telegram_id = d.telegram_id
  AND d.rn > 1;
