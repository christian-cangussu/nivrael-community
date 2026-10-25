-- v15.1 — Combate Turn-Based + Qi Consumption
-- Adds qi_cost to techniques_catalog (gate per-technique combat usage)
-- and creates duel_sessions (state machine for round-by-round PvP duels).
--
-- Backwards compat: existing combat (simulate_combat / duel_npc / sparring)
-- ignora qi_cost. Apenas o novo state-machine duel verifica combat_qi >= qi_cost.
-- duel_sessions é tabela nova — não toca em pvp_challenges (que continua
-- canónico para o desafio assíncrono pré-arena).
--
-- Hotfix 2026-05-15: ADD COLUMN split into nullable-first + SET DEFAULT to
-- avoid AccessExclusiveLock deadlock with the live tick query under rolling
-- deploy. The qi_cost column defaults via Python model (default=10), and the
-- combat_seeds runner backfills concrete tiered values per technique id —
-- so leaving the column nullable in DB is safe (no caller reads qi_cost
-- without first joining via the seeded catalog).

-- Step 1: add nullable column (metadata-only, microsecond lock)
ALTER TABLE techniques_catalog
    ADD COLUMN IF NOT EXISTS qi_cost INTEGER;

-- Step 2: set default for new rows
ALTER TABLE techniques_catalog
    ALTER COLUMN qi_cost SET DEFAULT 10;

-- Step 3: backfill any nulls with the conservative default. Seed runner
-- (database/seeds/combat_seeds.py:run_combat_seeds) overrides with tiered
-- values from QI_COSTS on the next startup.
UPDATE techniques_catalog SET qi_cost = 10 WHERE qi_cost IS NULL;

-- duel_sessions: brand new table, no contention with existing schema.
CREATE TABLE IF NOT EXISTS duel_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    attacker_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    defender_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    state VARCHAR(24) NOT NULL DEFAULT 'waiting_actions',
    round_idx INTEGER NOT NULL DEFAULT 0,
    max_rounds INTEGER NOT NULL DEFAULT 9,
    combat_qi_a INTEGER NOT NULL,
    combat_qi_b INTEGER NOT NULL,
    combat_qi_a_max INTEGER NOT NULL,
    combat_qi_b_max INTEGER NOT NULL,
    hp_a DOUBLE PRECISION NOT NULL,
    hp_b DOUBLE PRECISION NOT NULL,
    hp_a_max DOUBLE PRECISION NOT NULL,
    hp_b_max DOUBLE PRECISION NOT NULL,
    bp_a INTEGER NOT NULL,
    bp_b INTEGER NOT NULL,
    armor_a DOUBLE PRECISION NOT NULL DEFAULT 0,
    armor_b DOUBLE PRECISION NOT NULL DEFAULT 0,
    fighter_a JSONB NOT NULL DEFAULT '{}'::jsonb,
    fighter_b JSONB NOT NULL DEFAULT '{}'::jsonb,
    pending_action_a JSONB,
    pending_action_b JSONB,
    action_log JSONB NOT NULL DEFAULT '[]'::jsonb,
    winner_id BIGINT,
    sudden_death BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_duel_state
    ON duel_sessions (state, expires_at);

CREATE INDEX IF NOT EXISTS idx_duel_attacker_state
    ON duel_sessions (attacker_id, state);

CREATE INDEX IF NOT EXISTS idx_duel_defender_state
    ON duel_sessions (defender_id, state);
