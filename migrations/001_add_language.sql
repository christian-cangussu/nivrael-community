-- Migration: Add language column to players table
-- Run this in Supabase SQL Editor

ALTER TABLE players
ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'pt' NOT NULL;
