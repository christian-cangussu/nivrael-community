-- v13 H-14: track last activity per player, used by sect masters to identify
-- and kick inactive members.
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP WITH TIME ZONE
        DEFAULT now();

-- Backfill: assume existing players were active at migration time so masters
-- aren't immediately tempted to mass-kick.
UPDATE players SET last_active_at = now() WHERE last_active_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_players_last_active
    ON players(last_active_at);
