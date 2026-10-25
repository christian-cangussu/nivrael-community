-- Sprint v14.14c — Prestige Shop (endgame catalog, paid via prestige_points).
-- 1. player_prestige_purchases — tracks per-player per-item purchase count,
--    enforces max_purchases cap, exposes purchase history for UI.
-- 2. players.prestige_perks JSONB — cumulative perk state read by other engines
--    (process_prestige re-applies soul echoes after stat reset; spatial ring
--    expansion is one-shot mutation of PlayerSpatialRing.max_slots; titles
--    written to Player.unlocked_titles directly).
--
-- v15.1 hotfix (2026-05-15): rewritten online-safe to survive rolling deploy.
-- Original `ADD COLUMN ... NOT NULL DEFAULT` requires AccessExclusiveLock for
-- the entire table rewrite — deadlocks against the live container's tick query
-- which holds RowExclusiveLock on `players`. Split into:
--   step 1: ADD COLUMN nullable (metadata-only, microsecond lock)
--   step 2: SET DEFAULT (metadata-only, microsecond lock)
--   step 3: backfill existing rows (only RowExclusiveLock per row, no rewrite)
-- NOT NULL constraint deliberately omitted from DB — model defaults to {} and
-- all callers do `dict(player.prestige_perks or {})`. Tolerating NULL keeps
-- the schema change zero-rewrite and zero-deadlock under load.
--
-- WIPE-friendly: brand new table + nullable JSONB column with safe default.
-- No existing column changes. Existing beta players boot with empty perks.

CREATE TABLE IF NOT EXISTS player_prestige_purchases (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    item_id VARCHAR(64) NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    last_purchased_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (player_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_prestige_purchases_player
    ON player_prestige_purchases (player_id);

-- Step 1: add nullable column. PostgreSQL ≥11 makes this metadata-only when
-- no DEFAULT is set, so the AccessExclusiveLock is held for microseconds.
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS prestige_perks JSONB;

-- Step 2: set default for new rows (metadata-only, instant).
ALTER TABLE players
    ALTER COLUMN prestige_perks SET DEFAULT '{}'::jsonb;

-- Step 3: backfill existing rows. Each row update only takes a RowExclusiveLock,
-- which coexists with the live container's RowExclusiveLock on other rows.
UPDATE players SET prestige_perks = '{}'::jsonb WHERE prestige_perks IS NULL;
