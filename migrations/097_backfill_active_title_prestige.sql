-- v15.1.5-hf5 — Backfill `active_title` for players who bought prestige
-- titles but never saw them in their profile.
--
-- Root cause (now fixed in core/prestige_shop_engine.py:_apply_effect):
-- the title-kind effect appended to `unlocked_titles` JSONB but never set
-- `active_title`. The profile reads `active_title`, so the purchase was
-- invisible. Owner reported real money spent by players with nothing
-- equipped on their header — fix is twofold:
--   1. New code auto-equips on purchase (deployed alongside this migration)
--   2. THIS MIGRATION retroactively equips the first owned title for any
--      player who currently has `active_title=NULL` (or empty string) AND
--      `unlocked_titles` has at least one entry.
--
-- Safety:
--   • Only touches rows where `active_title` is missing — never overwrites
--     a player's already-equipped title.
--   • Picks `unlocked_titles->>0` — the first title added (oldest purchase),
--     preserving choice when the player only bought one (the common case).
--   • If a player wants to swap, the title manager UI in PrestigeShopModal
--     (mini-app) + AchievementsModal already supports it via
--     `api_achievements_equip_title` (works for any title in the merged
--     unlocked list, prestige + VIP + achievement).
--
-- Backwards-compat: pure UPDATE, no schema change. Idempotent — if run a
-- second time, the WHERE clause excludes anything we already fixed.

UPDATE players
SET active_title = (unlocked_titles->>0)
WHERE coalesce(active_title, '') = ''
  AND jsonb_typeof(unlocked_titles) = 'array'
  AND jsonb_array_length(unlocked_titles) > 0;
