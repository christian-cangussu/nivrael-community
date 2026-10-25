-- F-11.5 Celestial v2 — Heavenly Dao Laws + category flag
-- Adds is_heavenly boolean to dao_categories and dao_paths so the Celestial
-- (tier 5) Heavenly Laws can be gated by passing the 1st Celestial Trial
-- instead of only by min_realm. Backwards-compatible: defaults FALSE.

ALTER TABLE dao_categories ADD COLUMN IF NOT EXISTS is_heavenly BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE dao_paths ADD COLUMN IF NOT EXISTS is_heavenly BOOLEAN NOT NULL DEFAULT FALSE;

-- Index to quickly fetch heavenly paths when computing bonuses / filtering during
-- Celestial Meditation.
CREATE INDEX IF NOT EXISTS idx_dao_paths_is_heavenly ON dao_paths (is_heavenly) WHERE is_heavenly = TRUE;
