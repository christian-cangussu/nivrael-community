-- Migration 050: Spatial Ring inventory system
-- Adds player_spatial_rings table for the Spatial Ring feature

CREATE TABLE IF NOT EXISTS player_spatial_rings (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL UNIQUE REFERENCES players(telegram_id) ON DELETE CASCADE,
    tier INTEGER NOT NULL DEFAULT 1,
    max_slots INTEGER NOT NULL DEFAULT 50
);

CREATE INDEX IF NOT EXISTS idx_spatial_ring_player ON player_spatial_rings(player_id);

-- Give all existing players a tier-1 ring (50 slots)
INSERT INTO player_spatial_rings (player_id, tier, max_slots)
SELECT telegram_id, 1, 50 FROM players
ON CONFLICT (player_id) DO NOTHING;
