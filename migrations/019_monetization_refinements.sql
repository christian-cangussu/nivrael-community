ALTER TABLE battle_pass ADD COLUMN IF NOT EXISTS claimed_tiers JSONB DEFAULT '[]'::jsonb;
