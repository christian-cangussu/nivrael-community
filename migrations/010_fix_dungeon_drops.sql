-- Migration 010: Fix Immortal Trial drops — remove ore_id=8 (not in ores_catalog)
UPDATE dungeons_catalog
SET drops = jsonb_set(
    drops,
    '{ores}',
    '[{"id": 7, "weight": 5}]'::jsonb
)
WHERE id = 5
