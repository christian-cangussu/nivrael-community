-- v14.3 D-6 — Endgame Apex filler (DESIGN_DECISIONS_v14.md §D-6).
-- Adds the column for the Apex Reflection Chamber's special currency.
-- Achievement #21 (Apex Cultivator) is added as seed data, no migration needed.
-- Backwards-compatible 100% — DEFAULT 0 for the 57+ live players.

-- D-6b Apex Reflection Chamber — `/camara_reflexao` lets max-realm players
-- meditate contemplatively (0% CB gain) for a small chance of earning a
-- "Insight de Lei Divina" — currency reserved for the launch sprint, gives
-- pre-Apex players something to chase post-cap (filosofia §1: nunca silent void).
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS divine_law_insights INTEGER DEFAULT 0 NOT NULL;

-- Tracks when the player entered the Reflection Chamber. NULL = not in chamber.
-- Kept separate from `meditation_*` fields so the chamber doesn't interfere
-- with the regular meditation flow (different reward path, different gating).
ALTER TABLE players
    ADD COLUMN IF NOT EXISTS apex_chamber_entered_at TIMESTAMP WITH TIME ZONE;
