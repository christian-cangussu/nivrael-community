-- v15.1.5 — Arena ELO queue moves from chat-side bot_data to DB.
--
-- Sprint v15.1.5 pays the canonical-surface debt for the arena queue.
-- Until now the matchmaking pool lived in `context.bot_data["arena_queue"]`
-- on the chat worker process — invisible to the webserver, so mini-app
-- players had no way to enter or leave the queue. With this migration the
-- queue becomes a thin DB-backed projection that both surfaces can read
-- and write through `core/arena_engine`.
--
-- Schema (one row per active queue entry):
--   player_id   BIGINT PK             — only one slot per player
--   elo         INTEGER NOT NULL      — snapshot at join time
--   joined_at   TIMESTAMPTZ NOT NULL
--   status      VARCHAR(16) NOT NULL  — 'waiting' | 'matched' | 'expired'
--   duel_id     UUID                  — set when matched (FK to duel_sessions)
--   chat_id     BIGINT                — for chat-surface DM notifications
--   message_id  BIGINT                — anchor message id (chat surface)
--   expires_at  TIMESTAMPTZ NOT NULL  — ARENA_QUEUE_TIMEOUT_SECONDS from join
--
-- Backwards-compat: NEW TABLE. Zero touch to existing tables. The
-- `simulate_combat(mode="arena")` chat path is being replaced by a
-- DuelSession spawn, but ArenaRanking + CombatLog stay intact. PvP
-- challenges + PvE duels + world boss are untouched.
--
-- WIPE-friendly: arena pool is by definition ephemeral state — wipe will
-- truncate this table as part of the launch reset, no jade/items at stake.
-- The migration itself is structural; no seed data.

CREATE TABLE IF NOT EXISTS arena_queue (
    player_id   BIGINT PRIMARY KEY,
    elo         INTEGER NOT NULL,
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    status      VARCHAR(16) NOT NULL DEFAULT 'waiting',
    duel_id     UUID DEFAULT NULL,
    chat_id     BIGINT DEFAULT NULL,
    message_id  BIGINT DEFAULT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_arena_queue_player
        FOREIGN KEY (player_id) REFERENCES players(telegram_id) ON DELETE CASCADE
);

-- Matchmaking scan = `SELECT ... WHERE status='waiting' ORDER BY elo`.
-- Partial index keeps it cheap even after the table grows with historic
-- 'matched' / 'expired' rows.
CREATE INDEX IF NOT EXISTS idx_arena_queue_waiting
    ON arena_queue (elo)
    WHERE status = 'waiting';

-- Settle dispatcher in apply_post_duel_effects looks the duel up by its
-- id to decide arena vs pvp routing. Sparse index — most rows are still
-- 'waiting', only matched rows carry a non-NULL duel_id.
CREATE INDEX IF NOT EXISTS idx_arena_queue_duel
    ON arena_queue (duel_id)
    WHERE duel_id IS NOT NULL;
