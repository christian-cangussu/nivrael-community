-- Migration 021: Add last_tick_at column for scheduler tick optimistic locking
-- Prevents double-ticking if two scheduler cycles overlap.

ALTER TABLE players ADD COLUMN IF NOT EXISTS last_tick_at TIMESTAMPTZ;
