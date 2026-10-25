-- Track A item 3 — Os Arquivos de Wànshì 万事阁: player-posted bounties.
-- Onda 4a gave the world a Bounty Board of WORLD-issued contracts on dark-karma
-- NPC cultivators. This wave lets a PLAYER post a contract too ("colocar a
-- cabeça a prêmio"): the SAME bounty row, the SAME npc_cultivator duel + claim,
-- only the ORIGIN differs. World-issued bounties keep posted_by = NULL; a
-- player-posted one carries the poster's telegram_id + the moment it was posted.
--
-- Player-vs-player bounties are DEFERRED to the wipe (they need the PvP-consent
-- system, Track B) — this wave only adds dark-karma NPC targets, so it opens NO
-- forced PvP and is 100% additive.
--
-- Everything here is ADDITIVE + WIPE-SAFE (Lei Primordial §5):
--   * ADD COLUMN IF NOT EXISTS only, DEFAULT NULL — no DROP, no rename, no data
--     rewrite on the 57 live players' tables.
--   * Backwards-compatible: every CURRENT bounty becomes posted_by = NULL, i.e.
--     world-issued, exactly its present meaning. The refill/expire job, the
--     board read, and the claim path all keep working unchanged.
--
-- NB: this migration runner splits on ";". Keep every comment on its OWN full
-- line starting with "--" (NEVER an inline comment containing a ";").

ALTER TABLE bounties ADD COLUMN IF NOT EXISTS posted_by BIGINT REFERENCES players(telegram_id) DEFAULT NULL;
ALTER TABLE bounties ADD COLUMN IF NOT EXISTS posted_at TIMESTAMPTZ DEFAULT NULL;

-- The post path counts a poster's OPEN contracts (the max-active anti-grief cap)
-- and the board splits the two origins; index posted_by for both.
CREATE INDEX IF NOT EXISTS idx_bounty_posted_by ON bounties(posted_by) WHERE posted_by IS NOT NULL;
