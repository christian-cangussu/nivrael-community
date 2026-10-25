-- 071: Add unlocked_titles JSONB column to players
-- Stores extra titles from VIP milestones, Battle Pass, etc.
-- Achievement titles remain in achievement_catalog.title_granted
ALTER TABLE players ADD COLUMN IF NOT EXISTS unlocked_titles JSONB DEFAULT '[]'::jsonb;
