-- 059: Cauldron Upgrade System
-- Add max_durability to cauldrons_catalog and adjust tier 5/6 stats

-- Add max_durability column
ALTER TABLE cauldrons_catalog ADD COLUMN IF NOT EXISTS max_durability INTEGER NOT NULL DEFAULT 100;

-- Set max_durability per grade
UPDATE cauldrons_catalog SET max_durability = 100 WHERE grade = 1;
UPDATE cauldrons_catalog SET max_durability = 150 WHERE grade = 2;
UPDATE cauldrons_catalog SET max_durability = 200 WHERE grade = 3;
UPDATE cauldrons_catalog SET max_durability = 300 WHERE grade = 4;
UPDATE cauldrons_catalog SET max_durability = 400 WHERE grade = 5;
UPDATE cauldrons_catalog SET max_durability = 500 WHERE grade = 6;
UPDATE cauldrons_catalog SET max_durability = 600 WHERE grade = 7;

-- Adjust success_bonus for Crystal (id=5) and Immortal (id=6) to match new spec
UPDATE cauldrons_catalog SET success_bonus = 35.0 WHERE id = 5;
UPDATE cauldrons_catalog SET success_bonus = 45.0 WHERE id = 6;

-- Add new ores for cauldron upgrades (Phoenix Ash, Dragon Scale, Celestial Iron)
INSERT INTO ores_catalog (id, name, tier, emoji, description)
VALUES
    (8, 'Phoenix Ash', 3, '🔥', 'Ashes left behind by a reborn phoenix. Essential for cauldron refinement.'),
    (9, 'Dragon Scale', 4, '🐉', 'A scale shed by an ancient dragon. Imbued with primal fire essence.'),
    (10, 'Celestial Iron', 5, '⚙️', 'Iron forged in celestial flames. Only Immortal-tier beings can handle it.')
ON CONFLICT (id) DO NOTHING;
