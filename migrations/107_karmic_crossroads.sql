-- v16.3.5 — Karmic Crossroads (Moral Quest Engine). Onda 1 do CAMINHO.
--
-- Gives the (already-live, v16.3) karma spine its first agency-driven input:
-- when a player CLAIMS a quest that carries `choices`, instead of a single
-- fixed reward they pick a moral fork (Wuxia: mercy vs power vs greed) whose
-- deltas move karma / reputation / spirit-stones / items + show an outcome.
--
-- Backwards-compat (Lei §5 WIPE-friendly), zero risk for the 57+ live players:
--   • quests_catalog.choices DEFAULT NULL → every existing quest keeps its
--     EXACT current behavior (quest_has_choices() returns False → today's path).
--   • player_quests.chosen_choice_id DEFAULT NULL → existing progress rows
--     untouched. It records WHICH fork was taken this cycle; resets to NULL
--     together with `claimed` on the next daily/weekly reset, so idempotency is
--     auto-scoped to the cycle (the lock-protected `claimed` flag stays the
--     single source of truth for "already granted").
--   • quest_choice_log mirrors karma_log (audit trail; future analytics on
--     which path players walk). CASCADE ON DELETE → wipe cleans it up.
--   • NEVER DROP / NEVER RENAME. All ALTER/CREATE are IF NOT EXISTS → re-runnable.

ALTER TABLE quests_catalog
    ADD COLUMN IF NOT EXISTS choices JSONB DEFAULT NULL;

ALTER TABLE player_quests
    ADD COLUMN IF NOT EXISTS chosen_choice_id VARCHAR(32) DEFAULT NULL;

-- Append-only audit of every moral choice. Mirrors karma_log's shape.
CREATE TABLE IF NOT EXISTS quest_choice_log (
    id               BIGSERIAL PRIMARY KEY,
    player_id        BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    quest_id         INTEGER NOT NULL,
    chosen_choice_id VARCHAR(32) NOT NULL,
    karma_delta      INTEGER NOT NULL DEFAULT 0,
    new_karma        INTEGER,
    reputation_delta INTEGER NOT NULL DEFAULT 0,
    stones_delta     BIGINT NOT NULL DEFAULT 0,
    item_gained      VARCHAR(64),
    item_lost        VARCHAR(64),
    reset_at         TIMESTAMPTZ,
    metadata         JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qcl_player ON quest_choice_log(player_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_qcl_quest  ON quest_choice_log(player_id, quest_id);
