-- Onda 3 — NPC Cultivators + Heaven's Whispers. Gives the empty world a
-- POPULATION (persistent, autonomous NPC cultivators generated from anonymized
-- snapshots of real players' PUBLIC combat state) and a narrative broadcaster
-- (Heaven's Whispers — atmospheric world-event notifications).
--
-- Everything here is ADDITIVE + WIPE-SAFE (Lei Primordial §5):
--   * two NEW tables (npc_cultivators, heavens_whisper_log) — net-new, no
--     existing player data touched
--   * two ADD COLUMN IF NOT EXISTS on existing tables, neutral defaults for the
--     57 live players (whisper = TRUE = on by default; last_cultivator_fight =
--     NULL = no cooldown yet)
--   * CREATE INDEX IF NOT EXISTS only; no DROP, no rename
--
-- The NPC snapshot is a DERIVED, READ-ONLY, ANONYMIZED copy of public combat
-- state (realm / loadout / power). It carries NO PII: no telegram_id, no real
-- dao_name, no live FK back to the player. `source_hash` is a one-way,
-- non-reversible hash of the source telegram_id used ONLY for idempotent
-- upsert (one echo per source player) — it is never exposed to any surface.
--
-- NPCs are generated at RUNTIME by a scheduler job (core/npc_cultivator_engine
-- + core/scheduler), NOT seeded, but a first-arrival bootstrap fills each
-- continent so the world is never born empty.

-- ── A) NPC Cultivators — the persistent population ──────────────────────────
CREATE TABLE IF NOT EXISTS npc_cultivators (
    id              BIGSERIAL    PRIMARY KEY,
    name            VARCHAR(48)  NOT NULL,
    realm           INTEGER      NOT NULL DEFAULT 0,
    sub_layer       INTEGER      NOT NULL DEFAULT 1,
    continent_key   VARCHAR(16)  NOT NULL DEFAULT 'linghe',
    sect_id         VARCHAR(32)  REFERENCES world_sects(id),
    sect_rank       VARCHAR(16),
    path            VARCHAR(16),
    karma           INTEGER      NOT NULL DEFAULT 0,
    power           BIGINT       NOT NULL DEFAULT 0,
    loadout         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    status          VARCHAR(16)  NOT NULL DEFAULT 'active',
    origin          VARCHAR(16)  NOT NULL DEFAULT 'seed',
    source_hash     VARCHAR(64),
    generated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Encounters & "X discípulos" sect population scan by continent / sect / realm.
CREATE INDEX IF NOT EXISTS idx_npc_cult_continent ON npc_cultivators(continent_key) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_npc_cult_sect ON npc_cultivators(sect_id) WHERE sect_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_npc_cult_realm ON npc_cultivators(realm);
-- Leaderboard merge orders by power desc.
CREATE INDEX IF NOT EXISTS idx_npc_cult_power ON npc_cultivators(power DESC);
-- One anonymized echo per source player — idempotent upsert key (non-reversible).
CREATE UNIQUE INDEX IF NOT EXISTS uq_npc_cult_source ON npc_cultivators(source_hash) WHERE source_hash IS NOT NULL;

-- ── B) Heaven's Whispers — the global narrative feed ───────────────────────
-- A read-only, atmospheric world-event log. The mini-app Whispers feed reads
-- recent rows; the delivery job picks relevant recent rows and notify()s a
-- capped, opted-in, cooldowned subset of players (anti-churn, Lei §1).
CREATE TABLE IF NOT EXISTS heavens_whisper_log (
    id              BIGSERIAL    PRIMARY KEY,
    theme           VARCHAR(32)  NOT NULL,
    title_key       VARCHAR(96)  NOT NULL,
    body_key        VARCHAR(96)  NOT NULL,
    params          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    continent_key   VARCHAR(16),
    sect_id         VARCHAR(32),
    icon            VARCHAR(16)  NOT NULL DEFAULT '🌌',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_heavens_whisper_created ON heavens_whisper_log(created_at DESC);

-- ── C) Heaven's Whispers opt-out toggle (anti-churn, /conf + mini-app) ─────
-- Default TRUE = whispers on for the 57 live players; they can mute via /conf.
ALTER TABLE player_notification_prefs
    ADD COLUMN IF NOT EXISTS whisper BOOLEAN NOT NULL DEFAULT TRUE;

-- ── D) Separate cooldown for NPC-cultivator challenges ─────────────────────
-- NOT the regular NPC-hunt cooldown (last_npc_fight) — keeps the 57 players'
-- farming loop untouched (Lei §5). NULL = never challenged yet.
ALTER TABLE player_npc_cooldowns
    ADD COLUMN IF NOT EXISTS last_cultivator_fight TIMESTAMPTZ;
