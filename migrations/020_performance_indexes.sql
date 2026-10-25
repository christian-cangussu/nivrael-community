-- Migration 020: Performance indexes for beta launch
-- Adds composite and partial indexes to avoid full table scans on hot queries.
-- All statements are idempotent (IF NOT EXISTS). No data is altered or removed.

-- 1. PlayerInventory — "does player X have item Y of type Z?"
CREATE INDEX IF NOT EXISTS idx_inventory_player_type_item
    ON player_inventory(player_id, item_type, item_id);

-- 2. SectMember — list members by role within a sect
CREATE INDEX IF NOT EXISTS idx_sect_member_sect_rank
    ON sect_members(sect_id, rank);

-- 3. ArenaRanking — leaderboard queries (season + elo descending)
CREATE INDEX IF NOT EXISTS idx_arena_ranking_season_elo
    ON arena_rankings(season, elo_points DESC);

-- 4. GachaHistory — pull history per banner
CREATE INDEX IF NOT EXISTS idx_gacha_history_player_banner
    ON gacha_history(player_id, banner_id);

-- 5. MarketplaceListing — partial index for active (unsold) listings
CREATE INDEX IF NOT EXISTS idx_marketplace_active
    ON marketplace_listings(is_sold, expires_at) WHERE is_sold = false;

-- 6. PlayerBuff — cleanup of expired buffs
CREATE INDEX IF NOT EXISTS idx_player_buff_expires
    ON player_buffs(expires_at) WHERE expires_at IS NOT NULL;

-- 7. Tribulation — pending tribulations per player
CREATE INDEX IF NOT EXISTS idx_tribulation_pending
    ON tribulations(player_id, status) WHERE status = 'pending';
