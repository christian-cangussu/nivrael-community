-- v15.2 — Intent System (Sword/Fist/Body/Dao/Killing).
--
-- The 5 canonical Wuxia "yì" (意, intent) tracks. Each cultivator has 5 rows
-- (one per intent) that level up as they fight with techniques tied to that
-- intent. The matchup matrix (Sword > Body > Fist > Sword, Dao > Killing,
-- Killing > Sword/Body) modulates damage in duel_engine._compute_one_side_damage.
--
-- Schema (one row per player per intent):
--   player_id  BIGINT      — FK to players.telegram_id
--   intent     VARCHAR(16) — 'sword' | 'fist' | 'body' | 'dao' | 'killing'
--   rank       INTEGER     — 0..9 (rank curve, see core/intent_engine.py)
--   xp         INTEGER     — XP toward next rank (resets to 0 on rank-up)
--   updated_at TIMESTAMPTZ
--   PRIMARY KEY (player_id, intent)
--
-- techniques_catalog gains `intent_affinity` (nullable) — the seed assigns
-- one of the 5 intents to each combat technique. Meditation / interior
-- techniques stay NULL (they don't fight).
--
-- Backwards-compat: CREATE TABLE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS.
-- Zero touch to existing rows; combat keeps working untouched if the seed
-- runner hasn't repopulated intent_affinity yet — duel_engine treats NULL
-- affinity as "no intent active this round" (zero modifier).
--
-- WIPE-friendly: ranks/xp reset to 0 on launch wipe naturally (player rows
-- get truncated). Catalog intent_affinity is structural metadata that
-- survives wipes.

CREATE TABLE IF NOT EXISTS player_intents (
    player_id  BIGINT NOT NULL,
    intent     VARCHAR(16) NOT NULL,
    rank       INTEGER NOT NULL DEFAULT 0,
    xp         INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, intent),
    CONSTRAINT fk_player_intents_player
        FOREIGN KEY (player_id) REFERENCES players(telegram_id) ON DELETE CASCADE
);

-- Lookup is always by player_id (the PK already covers it). Sparse index on
-- intent is unnecessary — only 5 values exist, the planner uses the PK.

ALTER TABLE techniques_catalog
    ADD COLUMN IF NOT EXISTS intent_affinity VARCHAR(16) DEFAULT NULL;
