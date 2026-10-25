-- v14.4 D-1 — Foundation system completo (DESIGN_DECISIONS_v14.md §D-1).
-- Adds the bookkeeping columns for `/recomeço` (newbie one-shot reroll)
-- and the ritual `/quebrar_fundacao` (mid-game break-and-rebuild trial).
--
-- Backwards-compatible 100% — DEFAULT FALSE/0/NULL for the 57+ live players.
-- No DROP, no rename, no enum change (foundation_quality is VARCHAR(16),
-- not a real enum — Sacred Foundation tier is wired in seed/code only and
-- will validate at the model layer).

-- D-1a /recomeço (≤ realm 2 OR ≤ 7 days from creation): one-shot reroll of
-- foundation_quality + spirit_root, no jade cost. Permanent gate after first
-- use, NOT reset by rebirth (otherwise it would be infinite-loop abuse).
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS foundation_reroll_used BOOLEAN DEFAULT FALSE NOT NULL;

-- D-1b /quebrar_fundacao (realm 5+): ritual that voluntarily breaks the
-- foundation to rebuild it. Counter for stats / lore tracking. Cooldown
-- timestamp to enforce 30-day cooldown OR 1 break per rebirth.
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS foundation_break_count INTEGER DEFAULT 0 NOT NULL;
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS last_foundation_break_at TIMESTAMP WITH TIME ZONE;
