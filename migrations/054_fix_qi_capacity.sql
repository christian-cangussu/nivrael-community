-- Fix qi_capacity for existing players: bonus_qi from REALM_MILESTONES was never applied.
-- Add the cumulative missing bonus_qi based on current realm.
-- The flat bonuses missed: R1=50, R2=100, R3=200, R4=300, R5=500, R6=700, R7=1000, R8=1500, R9=2000, R10=5000
-- These would have compounded through subsequent realm multipliers (1.1 + realm*0.05).
-- We use pre-computed expected qi_capacity per realm (base 100, with both mult and bonus)
-- and add the difference vs what they got (mult only, no bonus).

-- Expected qi_capacity WITH bonus_qi applied (rounded):
--   R0: 100,  R1: 165,  R2: 298,  R3: 573,  R4: 1044,
--   R5: 1910, R6: 3374, R7: 5892, R8: 10338, R9: 18023, R10: 33837
-- Actual qi_capacity WITHOUT bonus_qi (mult only):
--   R0: 100,  R1: 115,  R2: 138,  R3: 173,  R4: 224,
--   R5: 303,  R6: 424,  R7: 615,  R8: 922,  R9: 1429,  R10: 2287
-- Difference to add:
--   R0: 0, R1: 50, R2: 160, R3: 400, R4: 820,
--   R5: 1607, R6: 2950, R7: 5277, R8: 9416, R9: 16594, R10: 31550

UPDATE players SET qi_capacity = qi_capacity + 50 WHERE realm = 1;
UPDATE players SET qi_capacity = qi_capacity + 160 WHERE realm = 2;
UPDATE players SET qi_capacity = qi_capacity + 400 WHERE realm = 3;
UPDATE players SET qi_capacity = qi_capacity + 820 WHERE realm = 4;
UPDATE players SET qi_capacity = qi_capacity + 1607 WHERE realm = 5;
UPDATE players SET qi_capacity = qi_capacity + 2950 WHERE realm = 6;
UPDATE players SET qi_capacity = qi_capacity + 5277 WHERE realm = 7;
UPDATE players SET qi_capacity = qi_capacity + 9416 WHERE realm = 8;
UPDATE players SET qi_capacity = qi_capacity + 16594 WHERE realm = 9;
UPDATE players SET qi_capacity = qi_capacity + 31550 WHERE realm = 10;

-- Also restore qi to full for affected players so they can use the new capacity
UPDATE players SET qi = qi_capacity WHERE realm >= 1;
