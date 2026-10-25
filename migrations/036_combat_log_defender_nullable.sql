-- Fix: combat_log.defender_id must be nullable for NPC arena fights
-- (arena timeout generates a fight vs NPC, which has no player defender_id)
ALTER TABLE combat_log
    ALTER COLUMN defender_id DROP NOT NULL;
