ALTER TABLE players ADD COLUMN IF NOT EXISTS prestige_level INTEGER NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS prestige_points INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS prestige_log (
    id SERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL,
    prestige_level INTEGER NOT NULL,
    prestige_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    retained_technique INTEGER,
    retained_dao_laws JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT prestige_log_player_id_fkey FOREIGN KEY (player_id) REFERENCES players (telegram_id) ON DELETE CASCADE
);
