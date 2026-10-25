-- Fix quest 10: change "Top 100 in Arena" to "Top 3 in Arena"
-- The old quest was never tracked and meaningless with < 100 players.
UPDATE quests_catalog
SET name = 'Top 3 in Arena',
    description = 'Reach the top 3 in the Arena rankings',
    objective_type = 'arena_top3'
WHERE id = 10 AND objective_type = 'arena_top100';

-- Reset progress for any players who had this quest assigned with the old type
UPDATE player_quests
SET progress = 0, is_completed = false, claimed = false
WHERE quest_id = 10;
