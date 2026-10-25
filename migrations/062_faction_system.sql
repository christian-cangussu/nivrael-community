-- 062_faction_system.sql — Faction System (Celestial vs Demonic)

CREATE TABLE IF NOT EXISTS factions_catalog (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(32) UNIQUE NOT NULL,
    emoji       VARCHAR(8) NOT NULL,
    bonuses     JSONB NOT NULL DEFAULT '{}',
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_factions (
    player_id   BIGINT PRIMARY KEY REFERENCES players(telegram_id) ON DELETE CASCADE,
    faction_id  INTEGER NOT NULL REFERENCES factions_catalog(id),
    reputation  INTEGER NOT NULL DEFAULT 0,
    rank        VARCHAR(32) NOT NULL DEFAULT 'Initiate',
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS faction_quests_catalog (
    id              INTEGER PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    faction_id      INTEGER NOT NULL REFERENCES factions_catalog(id),
    quest_type      VARCHAR(32) NOT NULL,
    target          JSONB NOT NULL,
    reward_rep      INTEGER NOT NULL,
    reward_items    JSONB NOT NULL DEFAULT '{}',
    min_realm       INTEGER NOT NULL DEFAULT 0,
    cooldown_hours  INTEGER NOT NULL DEFAULT 24,
    emoji           VARCHAR(8) NOT NULL DEFAULT '📋',
    description     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_faction_quests (
    id              BIGSERIAL PRIMARY KEY,
    player_id       BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    quest_id        INTEGER NOT NULL REFERENCES faction_quests_catalog(id),
    progress        INTEGER NOT NULL DEFAULT 0,
    is_completed    BOOLEAN NOT NULL DEFAULT FALSE,
    claimed         BOOLEAN NOT NULL DEFAULT FALSE,
    accepted_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_player_faction_quests_player ON player_faction_quests(player_id);

CREATE TABLE IF NOT EXISTS faction_shop_items (
    id          INTEGER PRIMARY KEY,
    name        VARCHAR(128) NOT NULL,
    faction_id  INTEGER NOT NULL REFERENCES factions_catalog(id),
    item_type   VARCHAR(32) NOT NULL,
    item_data   JSONB NOT NULL DEFAULT '{}',
    rep_cost    INTEGER NOT NULL,
    min_rank    VARCHAR(32) NOT NULL DEFAULT 'Initiate',
    emoji       VARCHAR(8) NOT NULL DEFAULT '🛒',
    description TEXT NOT NULL
);
