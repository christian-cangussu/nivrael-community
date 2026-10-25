-- Migration 115 — lifetime jade earned counter (2026-06-12).
-- Achievement #12 "Jade Collector" (event jade_accumulated, target 10000) was a
-- CURRENT-BALANCE high-water mark sampled passively on /status — players who
-- spend as they earn ([jogador]: pass daily +10 / mission jade -> 500-jade
-- rerolls) could NEVER reach it. The counter below is monotonic lifetime
-- EARNINGS; every jade grant path now routes through core.monetization.grant_jade
-- which increments it and fires the achievement with the lifetime value.
-- Backwards compatible: new column, DEFAULT 0, no DROP, no data deleted.

ALTER TABLE players ADD COLUMN IF NOT EXISTS lifetime_jade_earned BIGINT NOT NULL DEFAULT 0;

-- One-shot HONEST FLOOR backfill for beta players (full history is not
-- reconstructible: monthly-card and pass daily-claim counts only keep the
-- latest timestamp; quest/streak/faction jade has no per-grant log).
-- Two independent provable floors, take the MAX of them (NEVER their sum:
-- purchased jade still sitting in the balance would be counted twice and a
-- payer holding unspent jade would insta-unlock the 10k achievement —
-- adversarial-review medium):
--   floor A = current balance + jade provably SPENT on spirit-root rerolls
--             (500 each, lower bound: protected rerolls cost 800 but the
--             split is not recorded). balance + spends <= lifetime, always.
--   floor B = real-money jade actually granted (purchases.spirit_jade_granted,
--             completed; convenience jade-SPENDS log 0 there). A subset of
--             lifetime income, always.
-- GREATEST keeps this idempotent on re-run and never regresses a value the
-- new grant path has already accumulated.
UPDATE players p
SET lifetime_jade_earned = GREATEST(
    p.lifetime_jade_earned,
    GREATEST(COALESCE(p.spirit_jade, 0), 0)::BIGINT
    + COALESCE((SELECT v.total_rerolls * 500 FROM player_vip v
                WHERE v.player_id = p.telegram_id), 0)::BIGINT,
    COALESCE((SELECT SUM(pu.spirit_jade_granted) FROM purchases pu
              WHERE pu.player_id = p.telegram_id
                AND pu.status = 'completed'), 0)::BIGINT
);
