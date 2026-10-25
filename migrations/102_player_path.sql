-- v16.2 — Path Trinity (Pillar 3 of the v16 Living World refactor).
--
-- Evolves the existing binary `PlayerFaction` (Celestial vs Demonic) into
-- a three-Path system on the player row itself:
--
--   • righteous (正道) — successor to Celestial; aggregates the 8 elder sects.
--   • demonic   (魔道) — successor to Demonic;  unique to Abyssal Depths/Mòyǔ.
--   • rogue     (散修) — NEW first-class option: no faction, no sect lineage,
--                       +10% raw loot, free to trade with either side.
--
-- Why a new column instead of mutating `player_factions`?
--   • Path is *more* than faction: it gates continents (Mòyǔ → Demonic only),
--     gates sect lineage (Rogue cannot run a lineaged sect), and in v16.3 it
--     will be policed by karma. Storing it on the player row keeps the engine
--     read-cheap (no JOIN for every lineage/continent gate).
--   • `PlayerFaction` stays intact for backwards-compat: reputation, rank,
--     joined_at, quests, shop progress all preserved. `faction_engine` is
--     marked DEPRECATED but functional — full deletion lands in v16.4 along
--     with the Sect-Guild Split.
--
-- Data migration (idempotent):
--   • Existing `PlayerFaction` rows whose faction_id maps to a "celest..."
--     catalog entry  → player.path = 'righteous'
--   • Existing `PlayerFaction` rows whose faction_id maps to a "demon..."
--     catalog entry  → player.path = 'demonic'
--   • Players without a PlayerFaction row → path stays NULL.
--   • NULL is semantically "Rogue" at read time (engine resolves via
--     DEFAULT_PATH). We don't backfill 'rogue' so we can distinguish
--     "never picked" (NULL) from "actively chose Rogue" ('rogue').
--
-- Backwards-compat:
--   • Column is nullable (no DEFAULT enforces a value) — Lei §1 honest
--     disclosure: players without a path see a R3+ chooser, not a silent
--     auto-assign.
--   • IF NOT EXISTS guards re-application during rolling deploys.
--   • Index for fast "who walks path X" queries (v16.3 karma sweep,
--     v16.7 rivalry events, v16.10 path-faction quarterly event).
--   • NEVER DROP, NEVER RENAME. Future v16.3 karma column lands beside it,
--     not on top of it.
--
-- WIPE-friendly: column survives the launch wipe. Player rows truncate, the
-- column schema remains, the new generation picks paths fresh.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS path VARCHAR(16) NULL;

CREATE INDEX IF NOT EXISTS idx_player_path ON players(path);

-- Data migration: project pre-existing faction membership into the new
-- path column. Uses a LIKE on the lowercased FactionCatalog.name so we
-- match "Celestial Court", "Celestials", "Demonic Sect", etc. without
-- hardcoding catalog IDs (those can drift across seeds). Only updates
-- rows where path IS NULL so re-running the migration is a no-op.
UPDATE players p
SET path = sub.derived_path
FROM (
    SELECT
        pf.player_id,
        CASE
            WHEN lower(fc.name) LIKE 'celest%' THEN 'righteous'
            WHEN lower(fc.name) LIKE 'demon%'  THEN 'demonic'
            ELSE NULL
        END AS derived_path
    FROM player_factions pf
    JOIN factions_catalog fc ON fc.id = pf.faction_id
) AS sub
WHERE p.telegram_id = sub.player_id
  AND p.path IS NULL
  AND sub.derived_path IS NOT NULL;
