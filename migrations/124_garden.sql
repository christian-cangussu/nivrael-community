-- Migration 124 — Sprint 4: Horta 灵田 (Campo Espiritual), a 1ª VIA de input do Corpo
-- Prompts/sprint4_horta_lingtian.md (travada 2026-06-29). ADDITIVE + WIPE-SAFE.
--
-- Adds the first RICH input source for the Mortal-flesh band (BC-6): a small grid
-- of plots where the R0–R6 cultivator plants spiritual herbs that mature over time
-- (idle, timestamp-based like the Cavern — NO per-player job) and, on harvest,
-- yield TEMPER PROGRESS toward the next Mortal tier. That progress DISCOUNTS the
-- next "Temperar a Carne" qi cost (BC-4: pace the body with TIME instead of qi),
-- so the Horta is the PATIENT path next to Sprint 3's fast pedras+qi path. Harvest
-- NEVER grants qi or qi_capacity (BC-5). Engine catalog (GARDEN_HERBS) is a code
-- constant → wipe-safe; player_garden_plots is light per-player state.
--
-- ⚠️ REGRA DE FERRO DOS 57 (Lei §1): the new column is NOT NULL DEFAULT 0 so the
-- 57 on `main` land at 0 = NEUTRAL, and player_garden_plots is born EMPTY. NOTHING
-- reads the Horta on `main`: `cultivo_corpo_r0` is OFF there (the same gate as the
-- temper ACTION — no new flag), so the endpoints refuse and api_player never
-- exposes garden state. The ONLY writers are the gated plant/harvest actions in a
-- world where `cultivo_corpo_r0` is ON AND realm < 7.
--
-- Per-world isolation: get_session_factory() routes each world to its OWN DB
-- (current_world contextvar), so player_id is unique within a world's DB — no
-- world_key column needed (mirrors player_cavern exactly).
--
-- IMPORTANT: the runner splits on ";". Every comment is FULL-LINE only — an inline
-- "--" containing a stray ";" would truncate a statement (see migration 108 crash).

ALTER TABLE players ADD COLUMN IF NOT EXISTS mortal_temper_progress INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS player_garden_plots (
    player_id   BIGINT       NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    slot_index  INTEGER      NOT NULL,
    herb_key    VARCHAR(32),
    planted_at  TIMESTAMPTZ,
    PRIMARY KEY (player_id, slot_index)
);
