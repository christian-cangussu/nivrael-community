-- World Boss v2: Multi-Tier + Phases
-- Adds tier (mortal/spirit/immortal) and phase (normal/enrage/shield/final) columns
ALTER TABLE world_bosses ADD COLUMN IF NOT EXISTS tier VARCHAR(16) DEFAULT 'mortal' NOT NULL;
ALTER TABLE world_bosses ADD COLUMN IF NOT EXISTS phase VARCHAR(16) DEFAULT 'normal' NOT NULL;
