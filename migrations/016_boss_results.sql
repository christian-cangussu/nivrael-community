-- Migration 016: Add ended_at and rewards_given to world_bosses for result screen
ALTER TABLE world_bosses ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
ALTER TABLE world_bosses ADD COLUMN IF NOT EXISTS rewards_given BOOLEAN NOT NULL DEFAULT FALSE
