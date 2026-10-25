-- Onda 5 (Fase 1) — Reinos Exploráveis: the ADDITIVE exploration loop.
-- The player enters the continent they are in and explores by Divine Sense
-- (神識): picks directions, fights cultivators (incl. the "hidden monsters" =
-- the Onda 3 NPC Cultivators), makes book-game choices, gathers MATERIALS, and
-- decides "safe return" or "go deeper". It COEXISTS with the 23 dungeons
-- (/dungeons is untouched) and reuses what is already alive: NPC Cultivators
-- (OFF the ranking), the duel engine, the Karmic Crossroads moral-fork pattern,
-- and Travel/continents.
--
-- Everything here is ADDITIVE + WIPE-SAFE (Lei Primordial §5):
--   * ONE new table (player_exploration) — light per-player expedition STATE,
--     net-new, no existing player data touched.
--   * The node map + themes + loot pools live in the ENGINE
--     (core/exploration_engine.py mirrors CONTINENT_META), NOT in the DB —
--     so the whole map survives the wipe with zero migration.
--   * NO column added to the dungeons (that conversion is the wipe — Cenário B);
--     DungeonCatalog / PlayerDungeon are NOT touched.
--   * CREATE TABLE IF NOT EXISTS only; no DROP, no rename, no ALTER on the
--     57 live players' tables.
--
-- Model: a player has AT MOST one active expedition (PK = player_id). It tracks
-- the continent being explored, the current `depth`, the in-flight loot `bag`
-- (JSONB — same shape as the dungeon expedition bag, materials only, NEVER
-- techniques — Lei §5), the expedition's own cooldown stamp `last_explore_at`
-- (NEVER shared with last_cultivator_fight / farm — Lei §5), and `started_at`.
-- "Safe return" banks the bag and clears the row's depth/bag; dying deep loses
-- 90% of the bag (reuses the dungeon death penalty) and resets the expedition.
--
-- NB: this migration runner splits on ";". Keep every comment on its OWN full
-- line starting with "--" (NEVER an inline comment containing a ";") — an
-- inline ";" inside a comment truncated a CREATE TABLE in migration 108 and
-- crash-looped prod. (db.py now also strips inline comments, but do not rely
-- on luck.)

CREATE TABLE IF NOT EXISTS player_exploration (
    player_id        BIGINT       PRIMARY KEY REFERENCES players(telegram_id) ON DELETE CASCADE,
    continent_key    VARCHAR(16)  NOT NULL DEFAULT 'linghe',
    depth            INTEGER      NOT NULL DEFAULT 0,
    bag              JSONB        NOT NULL DEFAULT '{}'::jsonb,
    last_explore_at  TIMESTAMPTZ,
    started_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);
