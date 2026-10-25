ALTER TABLE players ADD COLUMN IF NOT EXISTS active_title VARCHAR(64);
ALTER TABLE players ADD COLUMN IF NOT EXISTS shadow_mode BOOLEAN DEFAULT FALSE NOT NULL;

CREATE TABLE IF NOT EXISTS achievements_catalog (
    id INTEGER PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    target_value INTEGER NOT NULL,
    title_granted VARCHAR(64),
    stat_bonus JSONB,
    emoji VARCHAR(8) DEFAULT '🏆' NOT NULL
);

CREATE TABLE IF NOT EXISTS player_achievements (
    player_id BIGINT REFERENCES players(telegram_id) ON DELETE CASCADE,
    achievement_id INTEGER REFERENCES achievements_catalog(id) ON DELETE CASCADE,
    progress INTEGER DEFAULT 0 NOT NULL,
    unlocked_at TIMESTAMPTZ,
    PRIMARY KEY (player_id, achievement_id)
);
