-- v16.4b — Sect Recruitment Engine: the REAL trial.
--
-- The recruiter encounter (v16.4) used to grant membership the instant a
-- cultivator accepted. v16.4b makes the encounter EARN it: the player must
-- best a Sect Elder (a turn-based duel vs an NPC scaled to their realm,
-- reusing the v16.7 combat model). Victory ⇒ the house takes them in;
-- defeat ⇒ a short cooldown before another attempt — never a soft-lock
-- (Lei Primordial §1, the cultivator is never stuck).
--
-- This table tracks each trial attempt: which house, the linked duel, the
-- outcome, and the retry cooldown. The recruiter encounter that invited the
-- cultivator is referenced via `pending_id` so a win can mark it accepted.
--
-- Backwards-compat contract (CLAUDE.md security rules + Lei §5):
--   * CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS
--   * additive only — no existing object touched, no DROP, no rename
--   * neutral for all 57+ live players (a cultivator starts with no trial row)
--   * survives the launch wipe (table is launch-permanent)

CREATE TABLE IF NOT EXISTS world_sect_trial (
    id             BIGSERIAL PRIMARY KEY,
    player_id      BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    sect_id        VARCHAR(32) NOT NULL REFERENCES world_sects(id),
    status         VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending | won | lost
    duel_id        UUID REFERENCES duel_sessions(id),       -- the trial duel (nullable)
    pending_id     BIGINT,                                  -- recruiter encounter that invited
    affinity_score INTEGER,                                 -- snapshot at trial start (audit)
    cooldown_until TIMESTAMPTZ,                             -- set on loss, gates the retry
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at    TIMESTAMPTZ
);

-- Latest attempt per (player, house) lookup — drives "resume / on cooldown / new".
CREATE INDEX IF NOT EXISTS idx_sect_trial_player ON world_sect_trial(player_id, sect_id, created_at DESC);
-- Settle path resolves the trial from its linked duel.
CREATE INDEX IF NOT EXISTS idx_sect_trial_duel ON world_sect_trial(duel_id);
