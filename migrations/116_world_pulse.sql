-- Grand Design Track A, Pedra 1 — World Pulse 世界脉动 Fase 1 ("O Coração que Bate").
-- The 9 ancient sects stop being static metadata and become AUTONOMOUS ACTORS
-- driven by a deterministic scheduler job (core/world_pulse_engine), and the
-- world gains a living CHRONICLE (Registos Celestiais 天记) anyone can read.
--
-- Everything here is ADDITIVE + WIPE-SAFE (Lei Primordial §5):
--   * 10 ADD COLUMN IF NOT EXISTS on world_sects — 5 hidden personality scalars
--     (Crusader-Kings souls) + dynamic state (strength/momentum/last_action) +
--     idempotency stamp (last_pulse_at). `strength` is an ABSTRACT new number that
--     does NOT buff any of the 57 live players (Lei §5) — it only moves the
--     world's narrative (and, in a future phase, scales the Guild blessing §4).
--   * ONE net-new table world_chronicle (append-only world log) — no existing
--     player data touched.
--   * CREATE INDEX IF NOT EXISTS only; no DROP, no rename; backwards-compatible.
--
-- NOTE on part B of the sprint (npc_cultivators.sect_id): the column + sect_rank
-- ALREADY EXIST since migration 110 (the Onda 3 NPC population), seeds already
-- assign sect_id by continent+path (_make_seed_npc), echoes inherit the source's
-- sect_id (snapshot_player_to_npc), and project_npc_for_profile already renders
-- the 🏯 sect chip. So no column add / backfill is needed here — B is pre-shipped.

-- ── A) Sect personality scalars (Crusader Kings) + dynamic state ─────────────
-- 5 hidden FLOAT scalars (0..1), seeded per-sect from WORLD_SECT_SOUL ("cada uma
-- com a sua alma") via the seed-sync force-update; demonic = high ambition/greed/
-- aggression + low honor, righteous = high honor/zeal. `strength` starts from a
-- per-sect baseline (initialized once when last_pulse_at IS NULL, then accrues),
-- `momentum` swings with wins/losses, `last_pulse_at` is the per-sect idempotency
-- guard, `last_action`/`last_action_at` power the "the house is alive" disclosure.
ALTER TABLE world_sects
    ADD COLUMN IF NOT EXISTS ambition       DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS honor          DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS greed          DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS zeal           DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS aggression     DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS strength       INTEGER          NOT NULL DEFAULT 100,
    ADD COLUMN IF NOT EXISTS momentum       INTEGER          NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS last_action    VARCHAR(32),
    ADD COLUMN IF NOT EXISTS last_action_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_pulse_at  TIMESTAMPTZ;

-- ── B) world_chronicle — "Os Registos Celestiais" 天记 (Dwarf Fortress Legends) ─
-- Append-only world log. Each pulse beat writes one row (and any future world
-- event can too). text_key + params (server-resolved per the reader's language —
-- {sect}/{rival}/{continent} are merged in at render time, params stay
-- language-neutral). Nearly free, sells the "alive even without me", and is the
-- ready corpus for the future LLM Dao Celestial (§6 Camada B).
CREATE TABLE IF NOT EXISTS world_chronicle (
    id              BIGSERIAL    PRIMARY KEY,
    ts              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    continent_key   VARCHAR(16),
    sect_id         VARCHAR(32),
    event_type      VARCHAR(32)  NOT NULL,
    text_key        VARCHAR(96)  NOT NULL,
    params          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    importance      INTEGER      NOT NULL DEFAULT 1
);

-- The feed reads newest-first, capped; the partial index serves the plaza's
-- continent-scoped strip (+ global rows where continent_key IS NULL).
CREATE INDEX IF NOT EXISTS idx_world_chronicle_ts ON world_chronicle(ts DESC);
CREATE INDEX IF NOT EXISTS idx_world_chronicle_continent ON world_chronicle(continent_key) WHERE continent_key IS NOT NULL;
