-- 042: Fix dungeon herb drops and Phoenix Rebirth Pill alchemy tier
-- Abyssal Rift (id=4): herb 9 (Moonlight Moss, tier 2) -> herb 10 (Phoenix Tear Petal, tier 5)
-- Immortal Trial (id=5): herb 9 (Moonlight Moss, tier 2) -> herb 8 (Void Root, tier 5)
-- Phoenix Rebirth Pill (id=13): required_alchemy_tier 1 -> 4

-- ── Abyssal Rift: replace herb id 9 with herb id 10 in JSONB drops.herbs ──
UPDATE dungeons_catalog
SET drops = jsonb_set(
    drops,
    '{herbs}',
    (
        SELECT jsonb_agg(
            CASE
                WHEN (elem->>'id')::int = 9
                THEN jsonb_set(elem, '{id}', '10'::jsonb)
                ELSE elem
            END
        )
        FROM jsonb_array_elements(drops->'herbs') AS elem
    )
)
WHERE id = 4
  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(drops->'herbs') AS e
    WHERE (e->>'id')::int = 9
  );

-- ── Immortal Trial: replace herb id 9 with herb id 8 in JSONB drops.herbs ──
UPDATE dungeons_catalog
SET drops = jsonb_set(
    drops,
    '{herbs}',
    (
        SELECT jsonb_agg(
            CASE
                WHEN (elem->>'id')::int = 9
                THEN jsonb_set(elem, '{id}', '8'::jsonb)
                ELSE elem
            END
        )
        FROM jsonb_array_elements(drops->'herbs') AS elem
    )
)
WHERE id = 5
  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(drops->'herbs') AS e
    WHERE (e->>'id')::int = 9
  );

-- ── Phoenix Rebirth Pill: fix required alchemy tier ──
UPDATE pills_catalog
SET required_alchemy_tier = 4
WHERE id = 13
  AND required_alchemy_tier < 4;
