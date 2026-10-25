-- Migration 121 — Track A (B4): Lifespan 寿命 ("Mar de Longevidade 寿海")
-- Grand Design Apêndice A, bucket B4 + Atlas W-14 + Gap 4. ADDITIVE + WIPE-SAFE.
--
-- Adds the "mortality clock" as VISIBLE DATA only — the pillar that defines the
-- genre (Mortal's Journey / Coiling Dragon / Reverend Insanity): cultivation is the
-- race against your finite longevity, and each realm raises the ceiling. The ceiling
-- itself is DERIVED per realm in core.lifespan_engine.REALM_LIFESPAN (engine-not-DB),
-- NOT a column — so the table only stores the two MUTABLE counters:
--   * age_years            — longevity already consumed. Stays 0 this wave; the
--                            real ageing tick (World Pulse) lights up at the WIPE.
--   * lifespan_bonus_years — extensions earned from future longevity pills/treasures
--                            (0 now; the pill economy is wipe-bound, Lei §4).
--
-- DISCLOSURE-ONLY this wave: NOTHING ticks, ages, or dies; no combat/cultivation/
-- alchemy/scheduler path reads these columns (defensive grep enforced). The ageing
-- tick, Twilight → reincarnation/pill/demonic escape (never delete), real NPC death,
-- and sect vengeance are all Track B (wipe-bound). See GameDesign/lifespan_design.md.
--
-- Backwards-compatible for the 57+ beta players: both columns NOT NULL DEFAULT 0, so
-- ALTER backfills every existing row to 0 (neutral — no one ages, no one dies). No
-- Python backfill needed (unlike root_elements, which is per-id derived).
--
-- IMPORTANT: comments here are FULL-LINE only. An inline "--" comment containing a
-- stray ";" would split a statement mid-flight (see migration 108 prod crash).

ALTER TABLE players ADD COLUMN IF NOT EXISTS age_years INTEGER NOT NULL DEFAULT 0;
ALTER TABLE players ADD COLUMN IF NOT EXISTS lifespan_bonus_years INTEGER NOT NULL DEFAULT 0;
