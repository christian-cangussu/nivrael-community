-- v13 H-8: allow players to mark artifacts as locked so bulk dismantle skips them.
ALTER TABLE player_artifacts
    ADD COLUMN IF NOT EXISTS locked BOOLEAN DEFAULT FALSE NOT NULL;

CREATE INDEX IF NOT EXISTS idx_player_artifacts_locked
    ON player_artifacts(player_id, locked);
