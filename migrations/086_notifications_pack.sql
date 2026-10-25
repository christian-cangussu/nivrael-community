-- v14.5 — Notifications Pack + Auto-progress Dungeon (DESIGN_DECISIONS_v14
-- §D-2 polish + Auditoria v13 backlog Q-1/Q-2/Q-3/Q-4 + N-10).
--
-- Adds the bookkeeping columns to detect-once / notify-once for:
--   • pill buff expiring (N-10)         → player_buffs.expiry_notified
--   • alchemy energy back to full (Q-2) → players.last_alchemy_full_notified_at
--   • breakthrough threshold met (Q-3)  → players.last_breakthrough_notified_realm/sub
--   • tribulation cooldown done (Q-4)   → tribulations.cooldown_notified
--   • opt-in auto-progress dungeon (Q-1)→ players.auto_progress_dungeon
--
-- Backwards-compatible 100% — every column is DEFAULT FALSE/NULL/0 so the 57+
-- live players are not migrated into a new state. The notification-prefs
-- table (`player_notification_prefs`, migration 078) already has the matching
-- pref toggles (alchemy_energy_full, breakthrough_ready, trib_cooldown_done,
-- pill_finished); this migration only adds the *state-tracking* columns the
-- scheduler reads to avoid duplicate DMs.

ALTER TABLE player_buffs
    ADD COLUMN IF NOT EXISTS expiry_notified BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE tribulations
    ADD COLUMN IF NOT EXISTS cooldown_notified BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS last_breakthrough_notified_realm INTEGER;
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS last_breakthrough_notified_sub INTEGER;
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS last_alchemy_full_notified_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS auto_progress_dungeon BOOLEAN NOT NULL DEFAULT FALSE;

-- Partial indexes for the unnotified-pending scans (most rows are notified=true
-- and we never read them after that).
CREATE INDEX IF NOT EXISTS idx_player_buff_pending_expiry
    ON player_buffs (expires_at)
    WHERE expiry_notified = FALSE;

CREATE INDEX IF NOT EXISTS idx_tribulation_failed_pending_cd
    ON tribulations (completed_at)
    WHERE status = 'failed' AND cooldown_notified = FALSE;

-- Back-fill: suppress notifications for events that already happened before
-- v14.5 was deployed. Without this, the first scheduler tick after deploy
-- would flood every player whose pre-existing buffs are mid-flight or whose
-- old failed tribulations already cooled down. Only NEW state changes after
-- deploy should fire.
UPDATE player_buffs
   SET expiry_notified = TRUE
 WHERE expires_at <= NOW() + INTERVAL '90 seconds';

UPDATE tribulations
   SET cooldown_notified = TRUE
 WHERE status = 'failed';
