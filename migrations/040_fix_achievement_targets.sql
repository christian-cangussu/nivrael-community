-- Fix achievement "Dao Seeker" target: Foundation Establishment = realm 2 (not 1)
UPDATE achievements_catalog SET target_value = 2 WHERE id = 1 AND target_value = 1;

-- Fix achievement "Nascent Awakening" target: Nascent Soul = realm 4 (not 5)
UPDATE achievements_catalog SET target_value = 4 WHERE id = 3 AND target_value = 5;
