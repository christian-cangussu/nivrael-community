CREATE TABLE IF NOT EXISTS dao_partners (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player1_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    player2_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    intimacy_level INT NOT NULL DEFAULT 0,
    married_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ring_level INT NOT NULL DEFAULT 1,
    CONSTRAINT uq_dao_partners UNIQUE (player1_id, player2_id)
);

CREATE TABLE IF NOT EXISTS dao_partner_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposer_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    target_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '48 hours'),
    CONSTRAINT uq_dao_proposal UNIQUE (proposer_id, target_id)
)
