-- 058: Add persistent HP system
-- NULL means full HP (backwards compatible). On first access, set to max_hp.
ALTER TABLE players ADD COLUMN IF NOT EXISTS current_hp FLOAT DEFAULT NULL;
