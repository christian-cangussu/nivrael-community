-- 067_faction_total_rep.sql
-- Track total reputation earned so rank never drops on purchase

ALTER TABLE player_factions ADD COLUMN IF NOT EXISTS total_rep_earned INTEGER NOT NULL DEFAULT 0;

-- Backfill from current rep (best we can do without history)
UPDATE player_factions SET total_rep_earned = reputation WHERE total_rep_earned = 0 AND reputation > 0;
