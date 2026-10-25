-- 002_add_sects.sql
-- Migration to add Sects system

CREATE TABLE IF NOT EXISTS sects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) UNIQUE NOT NULL,
    master_id BIGINT NOT NULL REFERENCES players(telegram_id),
    description TEXT,
    member_count INTEGER DEFAULT 1,
    max_members INTEGER DEFAULT 50,
    spirit_stones BIGINT DEFAULT 0,
    training_lvl INTEGER DEFAULT 0,
    herb_garden_lvl INTEGER DEFAULT 0,
    forge_lvl INTEGER DEFAULT 0,
    library_lvl INTEGER DEFAULT 0,
    defense_lvl INTEGER DEFAULT 0,
    spirit_vein_lvl INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sect_members (
    sect_id UUID NOT NULL REFERENCES sects(id) ON DELETE CASCADE,
    player_id BIGINT PRIMARY KEY REFERENCES players(telegram_id) ON DELETE CASCADE,
    rank VARCHAR(16) NOT NULL DEFAULT 'member', -- master, elder, member
    contribution_points BIGINT DEFAULT 0,
    joined_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sect_members_sect_id ON sect_members(sect_id);

CREATE TABLE IF NOT EXISTS sect_buildings_log (
    id SERIAL PRIMARY KEY,
    sect_id UUID NOT NULL REFERENCES sects(id) ON DELETE CASCADE,
    building VARCHAR(32) NOT NULL,
    old_level INTEGER NOT NULL,
    new_level INTEGER NOT NULL,
    upgraded_by BIGINT NOT NULL REFERENCES players(telegram_id),
    cost BIGINT NOT NULL,
    upgraded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sect_territories (
    id SERIAL PRIMARY KEY,
    sect_id UUID REFERENCES sects(id) ON DELETE SET NULL,
    name VARCHAR(64) NOT NULL,
    bonus_stones BIGINT DEFAULT 1000,
    bonus_cb DOUBLE PRECISION DEFAULT 0.05 NOT NULL,
    captured_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sect_war_log (
    id SERIAL PRIMARY KEY,
    attacker_sect UUID NOT NULL REFERENCES sects(id) ON DELETE CASCADE,
    defender_sect UUID NOT NULL REFERENCES sects(id) ON DELETE CASCADE,
    winner_sect UUID REFERENCES sects(id) ON DELETE CASCADE,
    territory_id INTEGER NOT NULL REFERENCES sect_territories(id) ON DELETE CASCADE,
    war_date TIMESTAMPTZ DEFAULT NOW()
);

-- Seed initial territories
INSERT INTO sect_territories (name, bonus_stones, bonus_cb) VALUES 
('Nine Heavens Peak', 5000, 0.15),
('Crystal Lake Valley', 3000, 0.10),
('Spirit Herb Forest', 2000, 0.05);
