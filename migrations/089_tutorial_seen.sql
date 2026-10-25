-- Sprint v14.13 — MA-47 Tutorial / Onboarding
-- Adds Player.tutorial_seen flag for the mini-app welcome modal first-launch
-- gating. Persists cross-device (server-side) so the tutorial doesn't reappear
-- after a player switches phones / clears Telegram WebView storage.
--
-- WIPE-friendly: existing players are auto-flagged TRUE so they don't see the
-- tutorial after deploy (they already know the game). New players (and anyone
-- explicitly resetting via Settings → "Mostrar tutorial novamente") see it.

ALTER TABLE players
  ADD COLUMN IF NOT EXISTS tutorial_seen BOOLEAN NOT NULL DEFAULT FALSE;

-- Backfill: every existing beta player has, by definition, played the bot —
-- they don't need the welcome tutorial. Only fresh /start invocations after
-- this deploy will trigger it.
UPDATE players SET tutorial_seen = TRUE WHERE tutorial_seen = FALSE;
