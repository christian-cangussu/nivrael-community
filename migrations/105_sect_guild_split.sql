-- v16.4 — Sect-Guild Split. NPC sects (eternal lore-canon institutions)
-- split from player guilds (the existing `sects` table, renamed lexically
-- only — its schema is UNCHANGED).
--
-- Player groups (existing `sects` table) STAY INTACT — all 57+ beta players'
-- work is preserved. Only the LANGUAGE changes (mini-app + chat call them
-- "guilds" / "guildas"). The DB schema for `sects` is not touched here.
--
-- The new `world_sects` table holds the 9 NPC institutions. Seeded with the
-- exact keys from v16.1 (azure_cloud -> abyssal_depths) so existing
-- `Sect.lineage_key` values become FK targets for the affinity holdover
-- bonus without any re-mapping.
--
-- Backwards-compat contract (CLAUDE.md security rules + Lei Primordial §5):
--   * IF NOT EXISTS on every CREATE
--   * ADD COLUMN IF NOT EXISTS, FK nullable, DEFAULT NULL — neutral for the
--     57 existing players (a cultivator starts in NO NPC sect)
--   * no DROP, no rename of any existing object
--   * survives the launch wipe (tables + columns are launch-permanent)

CREATE TABLE IF NOT EXISTS world_sects (
    id              VARCHAR(32) PRIMARY KEY,
    name_key        VARCHAR(64) NOT NULL,
    emoji           VARCHAR(8)  NOT NULL,
    tier            VARCHAR(16) NOT NULL,
    continent_key   VARCHAR(16) NOT NULL,
    rival_id        VARCHAR(32) REFERENCES world_sects(id),
    philosophy_key  VARCHAR(96) NOT NULL,
    bonuses         JSONB NOT NULL DEFAULT '{}'::jsonb,
    signature_techs JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Player FK to the NPC sect they were recruited into (NULL = unaffiliated).
-- Nullable + DEFAULT NULL so all existing players land neutral. sect_rank
-- walks disciple -> inner -> core -> heir (v16.4c expands the ladder).
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS sect_id        VARCHAR(32) REFERENCES world_sects(id),
    ADD COLUMN IF NOT EXISTS sect_rank      VARCHAR(16),
    ADD COLUMN IF NOT EXISTS sect_joined_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_player_sect ON players(sect_id);

-- Pending recruiter encounters (1 active encounter per player per week max).
-- accepted_at / declined_at NULL while pending; expires_at gates auto-expiry.
CREATE TABLE IF NOT EXISTS world_sect_recruiter_pending (
    id             BIGSERIAL PRIMARY KEY,
    player_id      BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    sect_id        VARCHAR(32) NOT NULL REFERENCES world_sects(id),
    affinity_score INTEGER NOT NULL,
    expires_at     TIMESTAMPTZ NOT NULL,
    accepted_at    TIMESTAMPTZ,
    declined_at    TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (player_id, sect_id, expires_at)
);

CREATE INDEX IF NOT EXISTS idx_recruiter_player ON world_sect_recruiter_pending(player_id, expires_at);
