-- Migration 015: Allow NULL seller_id for NPC/system marketplace listings (Immortal Auction)
ALTER TABLE marketplace_listings ALTER COLUMN seller_id DROP NOT NULL
