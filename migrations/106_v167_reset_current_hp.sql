-- 106_v167_reset_current_hp.sql
-- v16.7 Combat Rebalance (Três Tesouros). The HP formula changed to the two-pool
-- model (core/combat_model.combat_hp), so max HP is now on a smaller scale. A beta
-- player whose stored current_hp is still on the OLD (much larger) scale would
-- render an overflowing HP bar (current > new max) until the next combat write
-- re-clamps it. current_hp NULL = full HP (get_current_hp clamps to max on read),
-- so this is a clean, backwards-compatible reset to full. Pre-wipe + HP regens via
-- meditation; no player is penalised. Idempotent (re-running is a no-op).
UPDATE players SET current_hp = NULL WHERE current_hp IS NOT NULL;
