-- Migration 045: Sect Contribution Log
-- Tracks all sect contributions (donations, quests, wars) for visibility

CREATE TABLE IF NOT EXISTS sect_contribution_log (
    id SERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    sect_id UUID NOT NULL REFERENCES sects(id) ON DELETE CASCADE,
    type VARCHAR(32) NOT NULL,          -- donation, quest, war
    amount BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sect_contrib_sect_id ON sect_contribution_log(sect_id);
CREATE INDEX IF NOT EXISTS idx_sect_contrib_created_at ON sect_contribution_log(created_at);
CREATE INDEX IF NOT EXISTS idx_sect_contrib_player_sect ON sect_contribution_log(player_id, sect_id);
