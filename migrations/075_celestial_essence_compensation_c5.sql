-- C-5: Body Tempering tier 12 was mathematically impossible (1400 essence
-- required vs 770 obtainable from existing sources). This migration grants
-- +200 Celestial Essence to every Mahayana (realm 8+) player as historical
-- debt closure. Migrations are tracked via applied_migrations, so this runs
-- exactly once even across restarts/redeploys.

UPDATE players
SET celestial_essence = COALESCE(celestial_essence, 0) + 200
WHERE realm >= 8;
