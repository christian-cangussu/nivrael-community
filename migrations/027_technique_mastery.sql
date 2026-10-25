ALTER TABLE player_techniques ADD COLUMN IF NOT EXISTS mastery_xp INTEGER DEFAULT 0;

UPDATE player_techniques SET mastery_xp =
    CASE mastery_level
        WHEN 1 THEN 0
        WHEN 2 THEN 100
        WHEN 3 THEN 500
        WHEN 4 THEN 2000
        WHEN 5 THEN 10000
        ELSE 0
    END
WHERE mastery_xp = 0 AND mastery_level > 1
