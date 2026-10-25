-- Migration 125 — Sprint 5: Caça de 3 partes 狩猎, a 2ª VIA de input do Corpo
-- Prompts/sprint5_caca_3partes.md (travada 2026-06-29). ADDITIVE + WIPE-SAFE.
--
-- Adds the SECOND input source for the Mortal-flesh band (BC-3): caçar (via the
-- existing beast EXPEDITION system) brings back body-tempering materials distilled
-- into `hunt_essence`, which the player REFINES into mortal_temper_progress (the
-- same patient currency the Horta produces — Sprint 4). So the hunt is a 2nd faucet
-- into the existing progress→qi-discount pipe, NOT a new system. Refining NEVER
-- grants qi/qi_capacity (BC-5).
--
-- ⚠️ REGRA DE FERRO DOS 57 (Lei §1): NOT NULL DEFAULT 0 → the 57 on `main` land at 0
-- = NEUTRAL. The drop hook in collect_expedition is GATED (cultivo_corpo_r0 ON AND
-- realm < 7) and purely ADDITIVE, so on `main`/OFF the expedition loot is byte-
-- identical and hunt_essence stays 0. The ONLY writers are the gated expedition
-- drop + the gated refine action. Nothing reads hunt_essence on `main`.
--
-- IMPORTANT: comments are FULL-LINE only (an inline "--" with a stray ";" truncated
-- a statement in migration 108 — never inline).

ALTER TABLE players ADD COLUMN IF NOT EXISTS hunt_essence INTEGER NOT NULL DEFAULT 0;
