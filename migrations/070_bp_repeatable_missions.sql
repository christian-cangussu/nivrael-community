-- 070: Battle Pass repeatable missions (daily/weekly)
-- Adds reset_type to missions, times_completed + last_completed_at to player progress

ALTER TABLE battle_pass_missions
    ADD COLUMN IF NOT EXISTS reset_type VARCHAR(10) DEFAULT 'none' NOT NULL;

ALTER TABLE player_bp_missions
    ADD COLUMN IF NOT EXISTS times_completed INT DEFAULT 0 NOT NULL;

ALTER TABLE player_bp_missions
    ADD COLUMN IF NOT EXISTS last_completed_at TIMESTAMP WITH TIME ZONE;

-- Backfill: existing completed missions get times_completed = 1
UPDATE player_bp_missions SET times_completed = 1 WHERE is_completed = TRUE AND times_completed = 0;
