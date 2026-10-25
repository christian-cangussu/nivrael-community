-- Pedra 2 wave 3 — Pavilhão de Mérito 功德阁.
-- Split the NPC-sect contribution into a LIFETIME-earned accumulator (drives the
-- rank ladder, permanent) vs the existing `sect_contribution` (now the SPENDABLE
-- balance debited by the Merit Pavilion). Without this split, spending merit on a
-- cosmetic title would recede a player's progress toward the next rank.
--
-- Additive + backwards-compatible: the column defaults to 0, then we backfill
-- earned = sect_contribution for every current member, so eligible_rank(earned)
-- == eligible_rank(old contribution) and NO existing rank changes. The promotion
-- engine never demotes anyway (rank_index(target) > rank_index(cur) guard), so
-- even a missed backfill row could never strip a player's rank.

ALTER TABLE players ADD COLUMN IF NOT EXISTS sect_contribution_earned INTEGER NOT NULL DEFAULT 0;

UPDATE players
   SET sect_contribution_earned = sect_contribution
 WHERE sect_contribution_earned = 0
   AND sect_contribution > 0;
