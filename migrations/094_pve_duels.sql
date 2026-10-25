-- v15.1.4 — PvE duels (NPC Hunt + Dungeon Boss turn-based).
--
-- Sprint v15.1.4 extends the duel engine to support NPC opponents:
--   - NPC Hunt (mini-app CombatNPCPanel "Lutar"): spawn a turn-based
--     duel against an archetype-driven NPC instead of the instant
--     `simulate_combat` path.
--   - Dungeon BOSS floors (last floor of any dungeon): spawn a turn-based
--     boss duel via mini-app DuelArenaModal. Trash floors keep the
--     instant `simulate_combat` farm-pace path INTACT.
--
-- Schema changes (all backwards-compatible, additive, DEFAULT NULL):
--   1) DROP NOT NULL from `defender_id` — NPC duels have NULL defender_id
--      as the sentinel. PvP duels keep populating it as before.
--   2) Add `npc_archetype VARCHAR(24)` — 'bandit' / 'sect_disciple' /
--      'beast' / 'demon' / 'boss'. NULL for PvP.
--   3) Add `npc_difficulty VARCHAR(16)` — 'easy' / 'normal' / 'hard' /
--      'nightmare'. NULL for PvP.
--   4) Add `pve_source VARCHAR(24)` — 'npc_hunt' / 'dungeon_boss'.
--      NULL for PvP.
--   5) Add `pve_context JSONB` — opaque per-source context (e.g.,
--      {dungeon_id, floor} for dungeon_boss). NULL for PvP and npc_hunt
--      when no extra context is needed.
--
-- Online-safe: every change is metadata-only (millisecond lock).
-- Legacy PvP duels are 100% untouched: defender_id stays populated, all
-- new columns are NULL, `pve_source IS NULL` is the PvP sentinel for the
-- settle dispatcher.
--
-- WIPE-friendly: no DROP, no destructive defaults. Existing rows survive.

ALTER TABLE duel_sessions
    ALTER COLUMN defender_id DROP NOT NULL;

ALTER TABLE duel_sessions
    ADD COLUMN IF NOT EXISTS npc_archetype VARCHAR(24) DEFAULT NULL;

ALTER TABLE duel_sessions
    ADD COLUMN IF NOT EXISTS npc_difficulty VARCHAR(16) DEFAULT NULL;

ALTER TABLE duel_sessions
    ADD COLUMN IF NOT EXISTS pve_source VARCHAR(24) DEFAULT NULL;

ALTER TABLE duel_sessions
    ADD COLUMN IF NOT EXISTS pve_context JSONB DEFAULT NULL;

-- Partial index for the dungeon boss lookup: when a duel terminates and
-- the settle path needs to find the linked dungeon run, it joins on
-- (attacker_id, pve_context->>'dungeon_id'). Only PvE-source rows are
-- indexed (most rows = PvP, excluded).
CREATE INDEX IF NOT EXISTS idx_duel_pve_source
    ON duel_sessions (attacker_id, pve_source)
    WHERE pve_source IS NOT NULL;
