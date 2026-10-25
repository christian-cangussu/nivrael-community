-- Add foundation columns to players table
ALTER TABLE players ADD COLUMN IF NOT EXISTS foundation_quality VARCHAR(16) DEFAULT NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS foundation_locked BOOLEAN DEFAULT FALSE;
