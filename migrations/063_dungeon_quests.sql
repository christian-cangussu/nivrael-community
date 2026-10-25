-- Migration 063: Dungeon Quests System (F-7)
-- Story-driven quests tied to specific dungeons

CREATE TABLE IF NOT EXISTS dungeon_quests_catalog (
    id SERIAL PRIMARY KEY,
    dungeon_id INTEGER NOT NULL REFERENCES dungeons_catalog(id),
    name VARCHAR(128) NOT NULL,
    description_key VARCHAR(64) NOT NULL,
    story_intro_key VARCHAR(64) NOT NULL,
    story_complete_key VARCHAR(64) NOT NULL,
    objective_type VARCHAR(32) NOT NULL,
    objective_target VARCHAR(64),
    objective_count INTEGER NOT NULL DEFAULT 1,
    reward_rep INTEGER NOT NULL DEFAULT 0,
    reward_stones INTEGER NOT NULL DEFAULT 0,
    reward_items JSONB NOT NULL DEFAULT '{}',
    cooldown_hours INTEGER NOT NULL DEFAULT 24,
    min_difficulty VARCHAR(16) NOT NULL DEFAULT 'easy',
    emoji VARCHAR(8) NOT NULL DEFAULT '📜'
);

CREATE TABLE IF NOT EXISTS player_dungeon_quests (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    quest_id INTEGER NOT NULL REFERENCES dungeon_quests_catalog(id),
    progress INTEGER NOT NULL DEFAULT 0,
    completed_count INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_completed_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pdq_player ON player_dungeon_quests(player_id);
CREATE INDEX IF NOT EXISTS idx_pdq_quest ON player_dungeon_quests(quest_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pdq_player_quest ON player_dungeon_quests(player_id, quest_id);
