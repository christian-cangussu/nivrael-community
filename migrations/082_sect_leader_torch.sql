-- v14.2 D-3 — Sect Leader patch (DESIGN_DECISIONS_v14.md §D-3).
-- Adds the columns required for:
--   • /decreto_supremo (24h sect-wide announcement, master only).
--   • /passar_tocha ritual (master → elder consent flow, 30-day cooldown).
-- All columns NULL/default-safe; backwards compatible with 57+ live players.

-- D-3a /decreto_supremo: separate from sect.bulletin (which is permanent until
-- the master rewrites it). Edicts are timed 24h motivational/strategic posts.
ALTER TABLE sects
    ADD COLUMN IF NOT EXISTS decree_text TEXT;
ALTER TABLE sects
    ADD COLUMN IF NOT EXISTS decree_expires_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE sects
    ADD COLUMN IF NOT EXISTS decree_author_id BIGINT;

-- D-3b /passar_tocha: cooldown enforcement + pending-consent state.
-- Only one torch can be pending per sect at any moment.
ALTER TABLE sects
    ADD COLUMN IF NOT EXISTS last_torch_passed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE sects
    ADD COLUMN IF NOT EXISTS pending_torch_to_id BIGINT;
ALTER TABLE sects
    ADD COLUMN IF NOT EXISTS pending_torch_at TIMESTAMP WITH TIME ZONE;
