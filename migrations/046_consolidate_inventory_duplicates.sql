-- Migration 046: Consolidate duplicate beast_trap and beast_core rows per player
-- Players can have multiple rows with the same (player_id, item_type) but different
-- item_id or quality. This migration consolidates them into a single row per
-- (player_id, item_type, item_id, quality) group.

-- Step 1: Consolidate beast_trap duplicates (same player_id + item_type + item_id + quality)
UPDATE player_inventory pi
SET quantity = d.total_qty
FROM (
    SELECT player_id, item_type, item_id, quality,
           MIN(id) AS keep_id,
           SUM(quantity) AS total_qty
    FROM player_inventory
    WHERE item_type IN ('beast_trap', 'beast_core')
    GROUP BY player_id, item_type, item_id, quality
    HAVING COUNT(*) > 1
) d
WHERE pi.id = d.keep_id;

-- Step 2: Delete all duplicate rows (keep the one with MIN(id) per group)
DELETE FROM player_inventory
WHERE item_type IN ('beast_trap', 'beast_core')
  AND id NOT IN (
      SELECT MIN(id)
      FROM player_inventory
      WHERE item_type IN ('beast_trap', 'beast_core')
      GROUP BY player_id, item_type, item_id, quality
  );
