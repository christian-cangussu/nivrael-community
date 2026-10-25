-- Migration 018: Persistent gacha pity counter
-- Replaces runtime pity calculation from gacha_history with a dedicated table.
-- Pity is reset only when a legendary is obtained (handled in core/monetization.py).

CREATE TABLE IF NOT EXISTS gacha_pity (
    id          BIGSERIAL PRIMARY KEY,
    player_id   BIGINT      NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    banner_id   VARCHAR(64) NOT NULL REFERENCES gacha_banners(id)   ON DELETE CASCADE,
    current_pity INTEGER    NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_gacha_pity UNIQUE (player_id, banner_id)
);

CREATE INDEX IF NOT EXISTS idx_gacha_pity_player ON gacha_pity(player_id);

-- Backfill existing pity from gacha_history (last recorded pity_count per player/banner)
INSERT INTO gacha_pity (player_id, banner_id, current_pity, updated_at)
SELECT DISTINCT ON (player_id, banner_id)
    player_id,
    banner_id,
    pity_count,
    created_at
FROM gacha_history
WHERE banner_id IS NOT NULL
ORDER BY player_id, banner_id, created_at DESC
ON CONFLICT (player_id, banner_id) DO NOTHING;
