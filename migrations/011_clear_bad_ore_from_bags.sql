-- Migration 011: Remove ore_id=8 (invalid) from all expedition bags
UPDATE player_dungeons
SET expedition_bag = expedition_bag #- '{ores,8}'
WHERE expedition_bag->'ores' ? '8'
