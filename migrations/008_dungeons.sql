-- Migration 008: Dungeon system tables
-- Idempotent (safe to re-run).

CREATE TABLE IF NOT EXISTS dungeons_catalog (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(64)  UNIQUE NOT NULL,
    min_realm         INTEGER      NOT NULL,
    max_realm         INTEGER      NOT NULL,
    floor_count       INTEGER      NOT NULL,
    qi_cost_per_floor INTEGER      NOT NULL,
    drops             JSONB        NOT NULL DEFAULT '{}',
    description       TEXT         NOT NULL,
    emoji             VARCHAR(8)   NOT NULL DEFAULT '🗺️'
);

CREATE TABLE IF NOT EXISTS player_dungeons (
    player_id         BIGINT  REFERENCES players(telegram_id) ON DELETE CASCADE,
    dungeon_id        INTEGER REFERENCES dungeons_catalog(id)  ON DELETE CASCADE,
    current_floor     INTEGER      NOT NULL DEFAULT 0,
    max_floor_reached INTEGER      NOT NULL DEFAULT 0,
    last_attempt_at   TIMESTAMPTZ,
    expedition_bag    JSONB        NOT NULL DEFAULT '{}',
    PRIMARY KEY (player_id, dungeon_id)
);

CREATE INDEX IF NOT EXISTS idx_player_dungeons_player ON player_dungeons(player_id);
