ALTER TABLE tribulations ADD COLUMN IF NOT EXISTS tribulation_type VARCHAR(32) DEFAULT 'thunder';
ALTER TABLE tribulations ADD COLUMN IF NOT EXISTS phases_completed JSONB DEFAULT '[]'::jsonb;
