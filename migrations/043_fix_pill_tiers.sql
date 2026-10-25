-- Fix pill tiers: powerful pills should require higher alchemy tier
-- Pills 3,4,7,8,9: difficulty 3-4 should be tier 2
UPDATE pills_catalog SET required_alchemy_tier = 2 WHERE id IN (3, 4, 7, 8, 9) AND required_alchemy_tier < 2;

-- Pills 10,14: seeds were fixed but never migrated
UPDATE pills_catalog SET required_alchemy_tier = 3 WHERE id = 10 AND required_alchemy_tier < 3;
UPDATE pills_catalog SET required_alchemy_tier = 4 WHERE id = 14 AND required_alchemy_tier < 4;
