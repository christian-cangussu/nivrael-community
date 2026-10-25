-- Migration 038: Unify BP season values to CURRENT_SEASON (value = 1)
-- Fixes: BattlePass rows created with date-based season (e.g. 202602, 202603)
-- will now match the CURRENT_SEASON=1 used by bp_engine.py.

-- Update battle_pass table
UPDATE battle_pass SET season = 1 WHERE season != 1;

-- Update player_bp_missions table
UPDATE player_bp_missions SET season = 1 WHERE season != 1;
