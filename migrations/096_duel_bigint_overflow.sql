-- v15.1.5 hotfix — Widen DuelSession bp/combat_qi columns to BIGINT.
--
-- Trigger: Tang (True Immortal 9, Apex Cultivator, BP=2.98B) reported
-- HTTP 500 on the NPC Hunt "Fight" button. Root cause: the new turn-based
-- duel writes `bp_a/bp_b/combat_qi_a/b/_max` snapshots from the live
-- player stats. Column type was Postgres `integer` (4 bytes, signed,
-- max=2,147,483,647 ≈ 2.147B). Tang's BP (2.98B) exceeds that, so the
-- INSERT in `start_duel_pve` raised `NumericValueOutOfRange` →
-- aiohttp returned generic HTTP 500.
--
-- Same overflow potential for `combat_qi_a/b/_max`: combat pool =
-- 20% × qi_capacity. Endgame qi_capacity can reach >10B, breaking the
-- 32-bit ceiling on the pool snapshot.
--
-- Affected players: anyone with BP ≥ ~2.14B. Currently Tang for sure,
-- and likely 1-2 other end-game players (590W/1L ELO 5712 cohort).
--
-- Fix is purely structural: widen 6 columns to BIGINT (8 bytes signed,
-- max=9.22 × 10^18). Online-safe in Postgres — `ALTER TYPE integer →
-- bigint` rewrites the column in place but doesn't break readers.
-- Backwards-compatible 100% (existing values within int range cast
-- losslessly).
--
-- WIPE-friendly: zero side-effect on launch wipe. New schema is just
-- bigger headroom.

ALTER TABLE duel_sessions
    ALTER COLUMN bp_a TYPE BIGINT,
    ALTER COLUMN bp_b TYPE BIGINT,
    ALTER COLUMN combat_qi_a TYPE BIGINT,
    ALTER COLUMN combat_qi_b TYPE BIGINT,
    ALTER COLUMN combat_qi_a_max TYPE BIGINT,
    ALTER COLUMN combat_qi_b_max TYPE BIGINT;
