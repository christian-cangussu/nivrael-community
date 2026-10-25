-- Migration 051: Pill Mastery, Recipes & Soul Fire
-- Adds mastery tracking per pill, recipe unlock system, and soul fire progression

-- 1. Player Pill Mastery: tracks crafts per pill for mastery bonuses
CREATE TABLE IF NOT EXISTS player_pill_mastery (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    pill_id INTEGER NOT NULL,
    mastery_level INTEGER NOT NULL DEFAULT 1,
    crafts_count INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_player_pill_mastery UNIQUE (player_id, pill_id)
);
CREATE INDEX IF NOT EXISTS idx_pill_mastery_player ON player_pill_mastery(player_id);

-- 2. Player Recipes: tracks which pills/artifacts the player has unlocked
CREATE TABLE IF NOT EXISTS player_recipes (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    item_type VARCHAR(16) NOT NULL,  -- 'pill' or 'artifact'
    item_id INTEGER NOT NULL,
    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_player_recipe UNIQUE (player_id, item_type, item_id)
);
CREATE INDEX IF NOT EXISTS idx_recipes_player ON player_recipes(player_id);

-- 3. Player Soul Fire: alchemist flame progression
CREATE TABLE IF NOT EXISTS player_soul_fire (
    player_id BIGINT PRIMARY KEY REFERENCES players(telegram_id) ON DELETE CASCADE,
    fire_tier INTEGER NOT NULL DEFAULT 0,
    fire_exp INTEGER NOT NULL DEFAULT 0
);

-- 4. Seed default T1 pill recipes for all existing players
-- T1 pills are IDs 1, 2, 3 (Qi Gathering, Foundation, Qi Amass)
INSERT INTO player_recipes (player_id, item_type, item_id)
SELECT p.telegram_id, 'pill', pill_id
FROM players p
CROSS JOIN (VALUES (1), (2), (3)) AS t1_pills(pill_id)
WHERE EXISTS (SELECT 1 FROM player_alchemy_skills WHERE player_id = p.telegram_id)
ON CONFLICT ON CONSTRAINT uq_player_recipe DO NOTHING;

-- 5. Seed mastery records for existing crafters based on total_crafts
-- Give existing players a baseline mastery for pills they've likely crafted
INSERT INTO player_pill_mastery (player_id, pill_id, mastery_level, crafts_count)
SELECT pas.player_id, pill_id, 1, 0
FROM player_alchemy_skills pas
CROSS JOIN (VALUES (1), (2), (3)) AS t1_pills(pill_id)
WHERE pas.total_crafts > 0
ON CONFLICT ON CONSTRAINT uq_player_pill_mastery DO NOTHING;

-- 6. Initialize soul fire for existing realm 3+ players
INSERT INTO player_soul_fire (player_id, fire_tier, fire_exp)
SELECT telegram_id, 1, 0
FROM players
WHERE realm >= 3
ON CONFLICT DO NOTHING;
