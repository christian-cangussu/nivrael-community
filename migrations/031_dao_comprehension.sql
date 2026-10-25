-- Add insight_level to player_dao_fragments
ALTER TABLE player_dao_fragments ADD COLUMN IF NOT EXISTS insight_level INTEGER DEFAULT 0;
