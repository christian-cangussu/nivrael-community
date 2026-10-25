CREATE TABLE IF NOT EXISTS player_npc_cooldowns (
    player_id BIGINT PRIMARY KEY REFERENCES players(telegram_id) ON DELETE CASCADE,
    last_npc_fight TIMESTAMP WITH TIME ZONE DEFAULT NULL,
    fights_today INTEGER DEFAULT 0 NOT NULL,
    last_reset_date DATE DEFAULT CURRENT_DATE
);
