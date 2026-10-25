-- Rebuild achievements tables with correct schema.
-- Safe to drop: no player data exists yet (seeds were failing).

DROP TABLE IF EXISTS player_achievements;
DROP TABLE IF EXISTS achievements_catalog;

CREATE TABLE achievements_catalog (
    id INTEGER PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    description TEXT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    target_value INTEGER NOT NULL,
    title_granted VARCHAR(64),
    stat_bonus JSONB,
    emoji VARCHAR(8) DEFAULT '🏆' NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_achievements_catalog_event_type ON achievements_catalog (event_type);

CREATE TABLE player_achievements (
    player_id BIGINT REFERENCES players(telegram_id) ON DELETE CASCADE,
    achievement_id INTEGER REFERENCES achievements_catalog(id) ON DELETE CASCADE,
    progress INTEGER DEFAULT 0 NOT NULL,
    unlocked_at TIMESTAMPTZ,
    PRIMARY KEY (player_id, achievement_id)
);
