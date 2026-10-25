-- Forge Recipe System & Forging Mastery

CREATE TABLE IF NOT EXISTS forge_recipes (
    id SERIAL PRIMARY KEY,
    artifact_id INTEGER NOT NULL REFERENCES artifacts_catalog(id),
    tier INTEGER NOT NULL DEFAULT 1,
    materials JSONB NOT NULL DEFAULT '[]',
    required_realm INTEGER NOT NULL DEFAULT 0,
    base_success_rate REAL NOT NULL DEFAULT 80.0,
    bp_bonus INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS player_forge_mastery (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    recipe_id INTEGER NOT NULL REFERENCES forge_recipes(id) ON DELETE CASCADE,
    mastery_level INTEGER NOT NULL DEFAULT 1,
    forges_count INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT uq_player_forge_mastery UNIQUE (player_id, recipe_id)
);

CREATE INDEX IF NOT EXISTS idx_player_forge_mastery_player ON player_forge_mastery(player_id);

ALTER TABLE player_forge_skills ADD COLUMN IF NOT EXISTS divine_forges INTEGER NOT NULL DEFAULT 0;
