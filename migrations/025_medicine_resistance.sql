CREATE TABLE IF NOT EXISTS player_medicine_resistance (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    pill_id INTEGER NOT NULL,
    consumption_count INTEGER DEFAULT 0 NOT NULL,
    CONSTRAINT uq_player_pill_resistance UNIQUE (player_id, pill_id)
);
CREATE INDEX IF NOT EXISTS idx_medicine_resistance_player ON player_medicine_resistance(player_id);
