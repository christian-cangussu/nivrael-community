-- Migration 014: Celestial Events system
CREATE TABLE IF NOT EXISTS celestial_events (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    type VARCHAR(32) NOT NULL,
    description TEXT NOT NULL,
    multipliers JSONB NOT NULL DEFAULT '{}',
    duration_hours INTEGER NOT NULL DEFAULT 24,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    started_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    emoji VARCHAR(8) NOT NULL DEFAULT '🌌'
);

CREATE INDEX IF NOT EXISTS ix_celestial_events_type ON celestial_events (type);
CREATE INDEX IF NOT EXISTS ix_celestial_events_is_active ON celestial_events (is_active)
