-- v14.4 D-1c — Sacred Foundation tier (DESIGN_DECISIONS_v14.md §D-1c).
--
-- "Sacred" is a new foundation_quality tier above "perfect", granted only
-- by the Eternal Foundation Pill at Heavenly craft grade when the player's
-- current foundation is already Perfect. +25% all_mult vs Perfect's 1.6.
--
-- IMPORTANT: `players.foundation_quality` is `VARCHAR(16)` (see migration
-- 022_foundation_quality.sql) — NOT a Postgres ENUM type. So no
-- `ALTER TYPE ... ADD VALUE` is needed; the new "sacred" string is simply
-- accepted by the column. This file is a marker so the migration log
-- records the tier introduction at this point in time.
--
-- Backwards-compatible 100% — no schema change, all 57+ live players keep
-- whatever quality they currently have (low/medium/high/perfect/NULL).

SELECT 1;
