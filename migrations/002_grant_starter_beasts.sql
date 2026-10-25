-- Grant starter beast + beast traps to all existing players who don't have any beasts
-- This runs once via the migration system

INSERT INTO player_beasts (player_id, catalog_id, rank, custom_name, level, exp, is_companion, is_on_expedition)
SELECT p.telegram_id, 1, 'Common', 'Thunder Ox', 1, 0, true, false
FROM players p
WHERE NOT EXISTS (
    SELECT 1 FROM player_beasts pb WHERE pb.player_id = p.telegram_id
);

INSERT INTO player_inventory (player_id, item_type, item_id, quantity, quality)
SELECT p.telegram_id, 'beast_trap', 0, 2, 'normal'
FROM players p
WHERE NOT EXISTS (
    SELECT 1 FROM player_inventory pi 
    WHERE pi.player_id = p.telegram_id AND pi.item_type = 'beast_trap'
)
