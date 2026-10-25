-- 057: Fix early-game progression gaps
-- 1. Add herbs 9 (Moonlight Moss) and 12 (Spirit Vine) to Mortal Catacombs drop table
-- 2. Grant Grade 0 starter artifacts to ALL existing players who don't have them

-- ── Clean up orphan rows from failed migration attempts ──────────────────────
DELETE FROM player_artifacts WHERE created_at IS NULL;

-- ── Update Mortal Catacombs (dungeon id=1) herb drops ────────────────────────
UPDATE dungeons_catalog
SET drops = jsonb_set(
    drops,
    '{herbs}',
    '[{"id": 1, "weight": 5}, {"id": 12, "weight": 4}, {"id": 2, "weight": 3}, {"id": 9, "weight": 3}, {"id": 3, "weight": 2}]'::jsonb
)
WHERE id = 1;

-- ── Grant starter artifacts to existing players ──────────────────────────────
-- Black Iron Sword (catalog_id=1, weapon)
INSERT INTO player_artifacts (player_id, catalog_id, grade, slot, is_equipped, has_spirit, custom_stats, created_at)
SELECT p.telegram_id, 1, 0, 'weapon', FALSE, FALSE, '{"battle_power": 50}'::jsonb, NOW()
FROM players p
WHERE NOT EXISTS (
    SELECT 1 FROM player_artifacts pa
    WHERE pa.player_id = p.telegram_id AND pa.catalog_id = 1
);

-- Spiritual Linen Tunic (catalog_id=2, armor)
INSERT INTO player_artifacts (player_id, catalog_id, grade, slot, is_equipped, has_spirit, custom_stats, created_at)
SELECT p.telegram_id, 2, 0, 'armor', FALSE, FALSE, '{"soul_strength": 30}'::jsonb, NOW()
FROM players p
WHERE NOT EXISTS (
    SELECT 1 FROM player_artifacts pa
    WHERE pa.player_id = p.telegram_id AND pa.catalog_id = 2
);

-- Ancient Copper Ring (catalog_id=3, accessory)
INSERT INTO player_artifacts (player_id, catalog_id, grade, slot, is_equipped, has_spirit, custom_stats, created_at)
SELECT p.telegram_id, 3, 0, 'accessory1', FALSE, FALSE, '{"luck": 5}'::jsonb, NOW()
FROM players p
WHERE NOT EXISTS (
    SELECT 1 FROM player_artifacts pa
    WHERE pa.player_id = p.telegram_id AND pa.catalog_id = 3
);
