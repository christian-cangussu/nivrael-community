-- v15.1.3 — Link PVPChallenge → DuelSession.
--
-- Sprint v15.1.3 migrates mini-app PvP challenge acceptance from
-- instant `simulate_combat` resolution to the turn-based duel engine.
-- When a challenge is accepted, the wager stays escrowed on PVPChallenge
-- and a fresh DuelSession is spawned. The duel ID is linked back here so
-- post-duel settlement can find the wager + side-effects context.
--
-- Online-safe pattern (defender against tick contention):
-- 1) ADD COLUMN nullable (metadata-only lock, milliseconds)
-- 2) No default rewrite (column stays NULL until accept happens)
-- 3) Index is partial — only rows actually linked to an active duel
--
-- Backwards-compatible: legacy challenges resolved via simulate_combat
-- keep duel_id NULL forever; settle path skips them. WIPE-friendly.

ALTER TABLE pvp_challenges
    ADD COLUMN IF NOT EXISTS duel_id UUID DEFAULT NULL;

-- Partial index for the settle path: find the PVPChallenge row given a
-- duel.id when a duel terminates. Only rows that actually have a duel
-- attached are indexed (most legacy rows = NULL, excluded).
CREATE INDEX IF NOT EXISTS idx_pvp_duel_link
    ON pvp_challenges (duel_id)
    WHERE duel_id IS NOT NULL;
