-- F-11: Celestial System para Mahayana
-- Adds celestial trials progression, celestial essence currency,
-- trial cooldown, and body transformation flag.

ALTER TABLE players ADD COLUMN IF NOT EXISTS celestial_trials_passed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS celestial_essence INTEGER NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS celestial_trial_cooldown_until TIMESTAMPTZ NULL;
ALTER TABLE players ADD COLUMN IF NOT EXISTS body_transformed BOOLEAN NOT NULL DEFAULT FALSE;
