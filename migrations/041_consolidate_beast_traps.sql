-- Migration 041: Consolidate duplicate beast_trap rows per player
-- Keeps the row with the lowest id, sums all quantities into it, then deletes duplicates.

-- Step 1: Update the "keeper" row with the total quantity
UPDATE player_inventory pi
SET quantity = d.total_qty
FROM (
    SELECT player_id, item_type, item_id,
           MIN(id) AS keep_id,
           SUM(quantity) AS total_qty
    FROM player_inventory
    WHERE item_type = 'beast_trap'
    GROUP BY player_id, item_type, item_id
    HAVING COUNT(*) > 1
) d
WHERE pi.id = d.keep_id;

-- Step 2: Delete all duplicate rows (keep the one with MIN(id) per group)
DELETE FROM player_inventory
WHERE item_type = 'beast_trap'
  AND id NOT IN (
      SELECT MIN(id)
      FROM player_inventory
      WHERE item_type = 'beast_trap'
      GROUP BY player_id, item_type, item_id
  );
