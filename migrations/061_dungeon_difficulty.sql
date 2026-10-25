-- Add base_bp and floor_counts to dungeon catalog
ALTER TABLE dungeons_catalog ADD COLUMN IF NOT EXISTS base_bp INTEGER NOT NULL DEFAULT 200;
ALTER TABLE dungeons_catalog ADD COLUMN IF NOT EXISTS floor_counts JSONB;

-- Add difficulty tracking to player_dungeons
ALTER TABLE player_dungeons ADD COLUMN IF NOT EXISTS difficulty VARCHAR(16);
ALTER TABLE player_dungeons ADD COLUMN IF NOT EXISTS best_difficulty INTEGER NOT NULL DEFAULT 0;

-- Set base_bp for existing dungeons
UPDATE dungeons_catalog SET base_bp = 200 WHERE id = 1;
UPDATE dungeons_catalog SET base_bp = 1500 WHERE id = 2;
UPDATE dungeons_catalog SET base_bp = 15000 WHERE id = 3;
UPDATE dungeons_catalog SET base_bp = 200000 WHERE id = 4;
UPDATE dungeons_catalog SET base_bp = 5000000 WHERE id = 5;

-- Set floor_counts per difficulty for existing dungeons
UPDATE dungeons_catalog SET floor_counts = '{"easy": 5, "normal": 10, "hard": 12, "nightmare": 15}' WHERE id = 1;
UPDATE dungeons_catalog SET floor_counts = '{"easy": 8, "normal": 15, "hard": 18, "nightmare": 22}' WHERE id = 2;
UPDATE dungeons_catalog SET floor_counts = '{"easy": 10, "normal": 20, "hard": 24, "nightmare": 30}' WHERE id = 3;
UPDATE dungeons_catalog SET floor_counts = '{"easy": 12, "normal": 25, "hard": 30, "nightmare": 38}' WHERE id = 4;
UPDATE dungeons_catalog SET floor_counts = '{"easy": 25, "normal": 50, "hard": 60, "nightmare": 75}' WHERE id = 5;

-- Mark existing completed dungeons as best_difficulty=2 (normal) since old system had no difficulty
UPDATE player_dungeons SET best_difficulty = 2 WHERE completed = true;

-- Reset any in-progress runs (transition to new system)
UPDATE player_dungeons SET current_floor = 0, expedition_bag = '{}', difficulty = NULL WHERE current_floor > 0;
