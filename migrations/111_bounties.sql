-- Onda 4a — Continental Plaza (Wànshì) + Bounty Board. Gives the persistent
-- NPC-cultivator population from Onda 3 a visible home (the continent plaza)
-- and a hunt with meaning: a Bounty Board of contracts on dark-karma NPC
-- cultivators, fulfilled by the SAME npc_cultivator duel + spare/execute fork.
--
-- Everything here is ADDITIVE + WIPE-SAFE (Lei Primordial §5):
--   * ONE new table (bounties) — net-new, no existing player data touched
--   * CREATE INDEX IF NOT EXISTS only; no DROP, no rename, no ALTER on the
--     57 live players' tables
--   * the plaza presence + feed are pure QUERIES (no table of their own)
--
-- Model (matches the prompt): a bounty is a WORLD-issued contract that names a
-- single dark-karma npc_cultivator. It pays ONCE — the first hunter who beats
-- the named target claims it (status open -> claimed, claimed_by + claimed_at).
-- The NPC row is NEVER mutated; it stays active and can be re-targeted by a new
-- contract after this one expires. A partial UNIQUE index keeps at most one
-- OPEN bounty per target NPC, so the refill job is idempotent and one duel can
-- only ever fund one bounty.
--
-- NB: this migration runner splits on ";". Keep every comment on its OWN full
-- line starting with "--" (NEVER an inline comment containing a ";") — an
-- inline ";" inside a comment truncated a CREATE TABLE in migration 108 and
-- crash-looped prod. (db.py now also strips inline comments, but do not rely
-- on luck.)

CREATE TABLE IF NOT EXISTS bounties (
    id              BIGSERIAL    PRIMARY KEY,
    npc_id          BIGINT       NOT NULL REFERENCES npc_cultivators(id) ON DELETE CASCADE,
    continent_key   VARCHAR(16)  NOT NULL DEFAULT 'linghe',
    realm           INTEGER      NOT NULL DEFAULT 0,
    karma           INTEGER      NOT NULL DEFAULT 0,
    reward_stones   BIGINT       NOT NULL DEFAULT 0,
    status          VARCHAR(16)  NOT NULL DEFAULT 'open',
    claimed_by      BIGINT       REFERENCES players(telegram_id),
    claimed_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ
);

-- The board reads open contracts by continent; the tick expires by time.
CREATE INDEX IF NOT EXISTS idx_bounty_open_continent ON bounties(continent_key) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_bounty_status ON bounties(status);
CREATE INDEX IF NOT EXISTS idx_bounty_expires ON bounties(expires_at);

-- At most one OPEN bounty per target NPC (idempotent refill, one-duel-one-bounty).
CREATE UNIQUE INDEX IF NOT EXISTS uq_bounty_open_npc ON bounties(npc_id) WHERE status = 'open';
