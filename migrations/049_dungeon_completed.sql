-- Migration 049: add completed flag to player_dungeons
ALTER TABLE player_dungeons
    ADD COLUMN IF NOT EXISTS completed BOOLEAN NOT NULL DEFAULT FALSE;
