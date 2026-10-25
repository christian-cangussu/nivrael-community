-- F-8: Technique Types (combat/meditation/interior) and Grade Evolution
-- Backwards compatible: all existing techniques default to 'combat' type, 'common' grade

-- Add tech_type to catalog (combat, meditation, interior)
ALTER TABLE techniques_catalog ADD COLUMN IF NOT EXISTS tech_type VARCHAR(16) NOT NULL DEFAULT 'combat';

-- Add grade to player_techniques (common, refined, perfected, transcendent, celestial)
ALTER TABLE player_techniques ADD COLUMN IF NOT EXISTS grade VARCHAR(16) NOT NULL DEFAULT 'common';
