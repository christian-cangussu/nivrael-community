-- M-9: per-player notification preferences. Defaults preserve existing behaviour
-- (everything ON), so existing players see no change until they tweak settings.

CREATE TABLE IF NOT EXISTS player_notification_prefs (
    player_id BIGINT PRIMARY KEY REFERENCES players(telegram_id) ON DELETE CASCADE,
    anomaly_global BOOLEAN NOT NULL DEFAULT TRUE,
    sect_edict BOOLEAN NOT NULL DEFAULT TRUE,
    pill_finished BOOLEAN NOT NULL DEFAULT TRUE,
    alchemy_energy_full BOOLEAN NOT NULL DEFAULT TRUE,
    breakthrough_ready BOOLEAN NOT NULL DEFAULT TRUE,
    trib_cooldown_done BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
