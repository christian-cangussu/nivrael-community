-- Grand Design Track A, Pedra 2 — "O Chamado da Seita" 宗门征召 (parte 1).
-- The Master-Disciple bond 师徒: when a cultivator wins the Elder's trial and
-- joins an Ancient Sect, the Elder who courted them becomes their NAMED shifu.
--
-- ADDITIVE + WIPE-SAFE (Lei Primordial §5). One nullable column, no backfill,
-- no DROP, no rename — backwards-compatible:
--   * players.sect_master_name — the Wuxia name of the disciple's master
--     (cosmetic identity only, the bond's MECHANICAL bonus stays DEFERRED to the
--     wipe, §4). NULL for every existing member. Display falls back to a
--     DETERMINISTIC name seeded by (sect_id, player_id) so the 57 live members
--     see a stable master even before the column is filled on their next join.
--     New joins persist it here (core/world_sects_engine.join_player_to_sect).
--
-- Comments are FULL-LINE only (a stray ';' inside an inline '--' once split a
-- statement mid-way and crash-looped prod — migration runner caveat).
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS sect_master_name VARCHAR(48);
