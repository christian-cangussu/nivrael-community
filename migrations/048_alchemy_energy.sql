-- Migration 048: Alchemy energy system
-- Replaces daily craft limits with an on-the-fly regen energy pool

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS alchemy_energy INTEGER NOT NULL DEFAULT 100,
    ADD COLUMN IF NOT EXISTS alchemy_energy_max INTEGER NOT NULL DEFAULT 100,
    ADD COLUMN IF NOT EXISTS alchemy_energy_updated_at TIMESTAMPTZ NULL;

-- Existing players start with full energy
UPDATE players SET alchemy_energy = 100, alchemy_energy_max = 100 WHERE alchemy_energy_updated_at IS NULL;
