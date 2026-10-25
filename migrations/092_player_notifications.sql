-- v15.1.2 — Notification Hub Overhaul
-- Persistent notification storage so events that happen WHILE the player is
-- offline (achievement unlock, duel challenge incoming, gacha new banner,
-- title earned, etc) are not lost between sessions. Coexists with the
-- live-state aggregation already done by api_notifications_inbox (quest_ready,
-- alchemy_full, etc — those don't need persistence because they reflect
-- current state, not events).
--
-- Online-safe pattern (matches v15.1 hotfix): CREATE TABLE only — no ALTER on
-- existing tables — so no AccessExclusiveLock contention with the live tick.
-- Indexes designed for the dominant query: "list my undismissed notifications
-- ordered by created_at DESC" and "count my unseen notifications".
--
-- WIPE-friendly: new table only, beta players boot with empty inbox.

CREATE TABLE IF NOT EXISTS player_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    kind VARCHAR(48) NOT NULL,
    -- kinds (extensible): achievement_unlock, title_unlock, duel_challenge,
    -- duel_result, gacha_new_banner, daily_streak_ready, bp_tier_up,
    -- sect_war_phase, sect_edict, body_temper_done, trial_ready,
    -- prestige_ready, partner_milestone, world_boss_event, market_sold,
    -- dao_discovery, announcement.
    ref_id VARCHAR(128),
    -- ref_id: optional dedup key. For challenge=challenge_id,
    -- achievement=achievement_code, title=title_code, market=listing_id, etc.
    -- UNIQUE (player_id, kind, ref_id) prevents double-notify on retries.
    title_key VARCHAR(96) NOT NULL,
    body_key VARCHAR(96) NOT NULL,
    -- payload: i18n params for title/body interpolation. Server pre-renders
    -- title/body using player.language before returning to client (matches
    -- the existing inbox pattern at webserver.py:8061-8087).
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    icon VARCHAR(16) NOT NULL DEFAULT '🔔',
    target_tab VARCHAR(32),
    -- Where the bell should deep-link to when tapped. NULL = no deep-link
    -- (informational only). e.g. 'combat', 'sect', 'shop', 'inventory'.
    priority SMALLINT NOT NULL DEFAULT 5,
    -- 1=urgent (toast), 3=high (badge pulse), 5=normal, 9=low
    seen_at TIMESTAMPTZ,
    -- NULL = unseen (drives bell badge count + toast emit).
    dismissed_at TIMESTAMPTZ,
    -- NULL = visible in inbox. Soft-delete preserves audit trail.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dominant query: list my live notifications ordered by recency.
CREATE INDEX IF NOT EXISTS idx_pn_player_live
    ON player_notifications (player_id, created_at DESC)
    WHERE dismissed_at IS NULL;

-- Bell badge: count my unseen.
CREATE INDEX IF NOT EXISTS idx_pn_player_unseen
    ON player_notifications (player_id)
    WHERE seen_at IS NULL AND dismissed_at IS NULL;

-- Dedup lookup for notify(): "did I already notify this (kind, ref_id)?"
CREATE UNIQUE INDEX IF NOT EXISTS idx_pn_dedup
    ON player_notifications (player_id, kind, ref_id)
    WHERE ref_id IS NOT NULL;
