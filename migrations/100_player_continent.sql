-- v16.0 — World Foundation: Player.home_continent + Player.current_continent.
--
-- Pillar 1 of the v16 Living World refactor (see
-- `Cerebro/Nivrael/GameDesign/v16_living_world_master_plan.md` §2 Pillar 1).
-- Adds the geographic dimension to every player. The five canonical
-- continents (Línghé, Qiānhé, Yǎnshān, Fēnghuǒ, Mòyǔ) are tracked in
-- `core/continent_engine.py` (single source of truth).
--
-- Schema:
--   home_continent     VARCHAR(16) NOT NULL DEFAULT 'linghe'
--     — the continent the cultivator was BORN in. Set at onboarding,
--       persists across travel. Reborn (prestige) is the only way to
--       change it (v16-future spec).
--   current_continent  VARCHAR(16) NOT NULL DEFAULT 'linghe'
--     — the continent the cultivator is currently in. v16.0 keeps this
--       equal to `home_continent` for all players (travel mechanic
--       arrives in v16.0b). Read by the mini-app PlayerHeader chip.
--
-- Backwards-compat:
--   - IF NOT EXISTS guards re-application during rolling deploys.
--   - DEFAULT 'linghe' means the 57+ existing beta players migrate
--     transparently to Línghé (the lore-canonical neutral starter
--     continent — "the heart of the world, where new cultivators
--     awaken"). No player ends up orphaned.
--   - NOT NULL is safe because the DEFAULT fills every existing row.
--
-- Index:
--   idx_player_current_continent — enables fast O(log n) queries on
--   "who is currently in continent X" for future lobby / encounter /
--   continent-wide events (v16.10). Cheap on 57 rows, future-proof at
--   10k+ players.
--
-- WIPE-friendly: column survives the launch wipe (players truncate,
-- defaults re-apply on first /start of each rebooted account).
--
-- NEVER: DROP COLUMN, RENAME, type narrowing. Future v16.0b travel
-- writes still target the same column; v16.1 sect_lineage will add a
-- separate column, not touch these.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS home_continent    VARCHAR(16) NOT NULL DEFAULT 'linghe',
    ADD COLUMN IF NOT EXISTS current_continent VARCHAR(16) NOT NULL DEFAULT 'linghe';

CREATE INDEX IF NOT EXISTS idx_player_current_continent
    ON players(current_continent);
