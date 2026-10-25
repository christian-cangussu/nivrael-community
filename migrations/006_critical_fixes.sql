-- Migration 006: Critical fixes — unique constraints, performance indexes, sect_war_state table
-- All statements are idempotent (safe to re-run).

-- ============================================================
-- Unique constraints (prevent duplicate inventory/ore rows)
-- Note: CREATE UNIQUE INDEX enforces uniqueness identically to ADD CONSTRAINT UNIQUE
-- and supports IF NOT EXISTS, unlike ALTER TABLE ADD CONSTRAINT
-- ============================================================
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_inventory
    ON player_inventory(player_id, item_type, item_id, quality);

CREATE UNIQUE INDEX IF NOT EXISTS uq_player_ore
    ON player_ores(player_id, ore_id);

-- ============================================================
-- Performance indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_inventory_player_type ON player_inventory(player_id, item_type);
CREATE INDEX IF NOT EXISTS idx_market_type_sold      ON marketplace_listings(item_type, is_sold);
CREATE INDEX IF NOT EXISTS idx_market_expires        ON marketplace_listings(expires_at);
CREATE INDEX IF NOT EXISTS idx_sect_members_sect     ON sect_members(sect_id);
CREATE INDEX IF NOT EXISTS idx_boss_dmg_ranking      ON world_boss_damage(boss_id, total_damage DESC);
CREATE INDEX IF NOT EXISTS idx_p2p_status            ON p2p_trades(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_combat_defender       ON combat_log(defender_id);
CREATE INDEX IF NOT EXISTS idx_transactions_type     ON transactions(type, created_at);

-- ============================================================
-- Sect war state table (persists war state across bot restarts)
-- ============================================================
CREATE TABLE IF NOT EXISTS sect_war_state (
    id                  SERIAL PRIMARY KEY,
    is_active           BOOLEAN      NOT NULL DEFAULT FALSE,
    started_at          TIMESTAMPTZ,
    participating_sects JSONB        NOT NULL DEFAULT '[]',
    attacks             JSONB        NOT NULL DEFAULT '{}',
    attacked_players    JSONB        NOT NULL DEFAULT '[]',
    sect_names          JSONB        NOT NULL DEFAULT '{}'
);
