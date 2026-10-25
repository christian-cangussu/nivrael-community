-- Phase 3: VIP milestones tracking
ALTER TABLE player_vip ADD COLUMN IF NOT EXISTS vip_milestones_claimed JSONB DEFAULT '[]';
