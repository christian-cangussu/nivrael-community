CREATE TABLE IF NOT EXISTS battle_pass_missions (
    id SERIAL PRIMARY KEY,
    tier INTEGER NOT NULL,
    objective_type VARCHAR(32) NOT NULL,
    objective_value INTEGER NOT NULL,
    reward_jade INTEGER DEFAULT 0,
    reward_items JSONB DEFAULT '[]',
    is_premium_only BOOLEAN DEFAULT FALSE,
    description_key VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS player_bp_missions (
    player_id BIGINT REFERENCES players(telegram_id) ON DELETE CASCADE,
    mission_id INTEGER REFERENCES battle_pass_missions(id) ON DELETE CASCADE,
    season INTEGER NOT NULL,
    progress INTEGER DEFAULT 0,
    is_completed BOOLEAN DEFAULT FALSE,
    claimed BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (player_id, mission_id, season)
);

CREATE INDEX IF NOT EXISTS idx_player_bp_missions_player_season
    ON player_bp_missions (player_id, season);
