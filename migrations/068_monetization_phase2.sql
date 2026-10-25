-- Migration 068: Monetization Phase 2
-- Root Reroll Pity counter + Monthly Cards + Celestial Fragments

-- Root Reroll Pity: track total rerolls on player_vip
ALTER TABLE player_vip ADD COLUMN IF NOT EXISTS total_rerolls INTEGER DEFAULT 0;

-- Monthly Cards: track card type, expiry, and daily claim
ALTER TABLE player_vip ADD COLUMN IF NOT EXISTS monthly_card_type VARCHAR(16) DEFAULT NULL;
ALTER TABLE player_vip ADD COLUMN IF NOT EXISTS monthly_card_expires TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE player_vip ADD COLUMN IF NOT EXISTS monthly_card_claimed_today DATE DEFAULT NULL;

-- Celestial Fragments: stored on player directly (like spirit_stones)
ALTER TABLE players ADD COLUMN IF NOT EXISTS celestial_fragments INTEGER DEFAULT 0;
