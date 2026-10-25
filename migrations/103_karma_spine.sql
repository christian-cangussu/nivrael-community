-- v16.3 — Karma Spine (Pillar 4 of the v16 Living World refactor).
--
-- Adds the karma column on the player row + the karma_log audit table.
-- Karma is the silent stat that DEFINES the player's path: at R3 the
-- karma_engine reads accumulated karma, derives Righteous / Demonic /
-- Rogue, and crystallizes the path automatically. No menu, no picker —
-- the cultivator AGE, and the heavens respond.
--
-- Range narrativo: [-1000, +1000]. 0 = neutral. The engine clamps every
-- write at apply time so out-of-range values can never reach the DB.
--
-- Why a dedicated audit table (karma_log) instead of inlining into the
-- player row? Because:
--   • KarmaModal in the mini-app shows the last 10 events (delta + event
--     type + timestamp) — that needs a log, not a counter.
--   • v16.10 Rivalry Events will aggregate sect-level karma flows, which
--     requires per-event rows to GROUP BY sect.
--   • Lei §1 honest disclosure — the player must be able to see WHY their
--     karma moved, not just the current number.
--
-- Backwards-compat (Lei §5 WIPE-friendly):
--   • Player.karma column is added with `IF NOT EXISTS` + `DEFAULT 0` so
--     all 57+ beta players land on a clean 0 / "Neutral" band.
--   • karma_log is CASCADE ON DELETE so when the wipe truncates players
--     the audit rows clean up automatically.
--   • NEVER DROP, NEVER RENAME columns — future v16.x additions land
--     beside, never on top.
--   • Indexes are non-unique and IF NOT EXISTS — re-runs are no-ops.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS karma INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_player_karma ON players(karma);

-- Karma audit log — every karma event (positive or negative) recorded.
-- Used by: KarmaModal recent events display, chat /karma history view,
-- future Rivalry Events (v16.10) sect-level karma aggregates, and the
-- karma_events achievement #27 (target = 1000 log entries lifetime).
CREATE TABLE IF NOT EXISTS karma_log (
    id           BIGSERIAL PRIMARY KEY,
    player_id    BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    delta        INTEGER NOT NULL,
    new_value    INTEGER NOT NULL,
    event_type   VARCHAR(48) NOT NULL,
    metadata     JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_karma_log_player ON karma_log(player_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_karma_log_event ON karma_log(event_type);
