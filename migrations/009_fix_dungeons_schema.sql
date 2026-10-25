-- Migration 009: Rebuild dungeon tables ONLY IF they are missing.
--
-- Originally this DROPped + recreated the dungeon tables to fix a partial schema
-- left by migration 008. That hard DROP breaks a FRESH world (new server / wipe /
-- launch / CI), where `Base.metadata.create_all` has ALREADY built the final
-- `dungeons_catalog` PLUS the later `dungeon_quests_catalog` whose FK depends on
-- it: `DROP TABLE dungeons_catalog` then fails with "cannot drop ... because other
-- objects depend on it" (2026-06-24 incident — this aborted a freshly-provisioned
-- world's migrations).
--
-- 2026-06-24 fix: guard the whole rebuild so it runs ONLY when `dungeons_catalog`
-- does not exist (the original partial-008 case). On `main` this migration is
-- long-applied and skipped; on a from-scratch world create_all already made the
-- table, so this becomes a clean no-op and migrations proceed. The DO $$ block is
-- handled as one statement by the dollar-quote-aware migration tokenizer.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = current_schema() AND table_name = 'dungeons_catalog'
    ) THEN
        CREATE TABLE dungeons_catalog (
            id                SERIAL PRIMARY KEY,
            name              VARCHAR(64)  UNIQUE NOT NULL,
            min_realm         INTEGER      NOT NULL,
            max_realm         INTEGER      NOT NULL,
            floor_count       INTEGER      NOT NULL,
            qi_cost_per_floor INTEGER      NOT NULL,
            drops             JSONB        NOT NULL DEFAULT '{}',
            description       TEXT         NOT NULL,
            emoji             VARCHAR(8)   NOT NULL DEFAULT '?'
        );

        CREATE TABLE player_dungeons (
            player_id         BIGINT  REFERENCES players(telegram_id) ON DELETE CASCADE,
            dungeon_id        INTEGER REFERENCES dungeons_catalog(id)  ON DELETE CASCADE,
            current_floor     INTEGER NOT NULL DEFAULT 0,
            max_floor_reached INTEGER NOT NULL DEFAULT 0,
            last_attempt_at   TIMESTAMPTZ,
            expedition_bag    JSONB   NOT NULL DEFAULT '{}',
            PRIMARY KEY (player_id, dungeon_id)
        );

        CREATE INDEX IF NOT EXISTS idx_player_dungeons_player ON player_dungeons(player_id);
    END IF;
END $$;
