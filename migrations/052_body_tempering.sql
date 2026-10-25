-- Body Tempering (Nine Transformations) system
ALTER TABLE players ADD COLUMN IF NOT EXISTS body_tempering_level INTEGER NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS body_tempering_progress INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_players_body_tempering ON players (body_tempering_level);
