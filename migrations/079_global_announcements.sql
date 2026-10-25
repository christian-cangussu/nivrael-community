-- Mini-app: persistent global feed shown in /miniapp Announcements tab.
-- Populated by core.announcement_engine.broadcast() each time a global
-- broadcast goes out. Decoupled from the in-memory rate-limit cache so the
-- mini-app never misses an event.

CREATE TABLE IF NOT EXISTS global_announcements (
    id BIGSERIAL PRIMARY KEY,
    kind VARCHAR(32) NOT NULL,
    icon VARCHAR(8) NOT NULL DEFAULT '📜',
    message_key VARCHAR(64) NOT NULL,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    rendered_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_global_announcements_created
    ON global_announcements (created_at DESC);
