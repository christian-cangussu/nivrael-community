-- v14.9 round 3 (2026-05-20): MA-35 PvP duels via mini-app.
-- Owner request: "fico pensando o jogador quando envia o duelo seleciona
-- alguem online ou vai entrar na arena, decide se e um duelo apostado
-- coloca o dao name e envie, o outro recebe em notificcao etc e meio que
-- quando abre tem ai 5 minutos pra expirar ou cancelar".
--
-- Persists pending PvP challenges across restarts (chat-side uses bot_data
-- in-memory which mini-app cannot read). Auto-expire via expires_at +
-- on-read filter (no scheduler needed — every endpoint that lists pending
-- rows checks expires_at > NOW()).
--
-- Backwards-compatible: brand new table, no existing column changes.

CREATE TABLE IF NOT EXISTS pvp_challenges (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    challenger_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    target_id     BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    wager         INTEGER NOT NULL DEFAULT 0,
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',
    -- pending | accepted | declined | cancelled | expired | completed
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL,
    resolved_at   TIMESTAMPTZ NULL,
    winner_id     BIGINT NULL,
    rounds_data   JSONB NULL
);

-- Hot lookup paths: target's incoming pending list + challenger's outgoing
-- pending list + scheduler/on-read sweep for stale rows.
CREATE INDEX IF NOT EXISTS idx_pvp_target_pending
    ON pvp_challenges (target_id, expires_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_pvp_challenger_pending
    ON pvp_challenges (challenger_id, expires_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_pvp_recent_resolved
    ON pvp_challenges (challenger_id, resolved_at DESC)
    WHERE status IN ('completed', 'declined', 'cancelled', 'expired');
