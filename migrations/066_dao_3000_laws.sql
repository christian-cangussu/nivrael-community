-- 066: 3000 Dao Laws system — categories, paths, discoverable laws
-- Backwards compatible: new tables only, no changes to existing dao_laws_catalog / player_dao_fragments

CREATE TABLE IF NOT EXISTS dao_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL UNIQUE,
    name_pt VARCHAR(64),
    name_es VARCHAR(64),
    emoji VARCHAR(8) NOT NULL,
    description TEXT,
    min_realm INT NOT NULL DEFAULT 5,
    bonus_type VARCHAR(32) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dao_paths (
    id SERIAL PRIMARY KEY,
    category_id INT NOT NULL REFERENCES dao_categories(id),
    name VARCHAR(64) NOT NULL,
    name_pt VARCHAR(64),
    name_es VARCHAR(64),
    emoji VARCHAR(8) NOT NULL,
    element VARCHAR(32),
    total_laws INT NOT NULL DEFAULT 20,
    min_realm INT NOT NULL DEFAULT 5,
    bonus_type VARCHAR(32) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dao_path_laws (
    id SERIAL PRIMARY KEY,
    path_id INT NOT NULL REFERENCES dao_paths(id),
    name VARCHAR(128) NOT NULL,
    name_pt VARCHAR(128),
    name_es VARCHAR(128),
    rarity VARCHAR(16) NOT NULL DEFAULT 'common',
    min_realm INT NOT NULL DEFAULT 5,
    description TEXT
);

CREATE TABLE IF NOT EXISTS player_dao_discoveries (
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    law_id INT NOT NULL REFERENCES dao_path_laws(id),
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (player_id, law_id)
);

CREATE INDEX IF NOT EXISTS idx_player_dao_disc_player ON player_dao_discoveries(player_id);
CREATE INDEX IF NOT EXISTS idx_dao_path_laws_path ON dao_path_laws(path_id);
CREATE INDEX IF NOT EXISTS idx_dao_paths_category ON dao_paths(category_id);
