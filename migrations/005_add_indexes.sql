CREATE INDEX IF NOT EXISTS idx_players_realm ON players(realm);
CREATE INDEX IF NOT EXISTS idx_players_sub_layer ON players(sub_layer);
CREATE INDEX IF NOT EXISTS idx_players_cultivation_base ON players(cultivation_base);
CREATE INDEX IF NOT EXISTS idx_player_artifacts_player_id ON player_artifacts(player_id);
CREATE INDEX IF NOT EXISTS idx_player_inventory_player_id ON player_inventory(player_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_listings_seller_id ON marketplace_listings(seller_id);
CREATE INDEX IF NOT EXISTS idx_tribulations_player_id ON tribulations(player_id);
