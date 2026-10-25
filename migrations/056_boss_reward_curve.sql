-- Flatten boss reward curve: 8x/6x/5x/3x/1x instead of 30x/20x/15x/5-10x/1x
-- Doubles participant base, reduces top-rank stones to incentivize weaker players

UPDATE world_bosses SET loot_table = jsonb_set(
  jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(loot_table,
          '{rank_1,0,amount}', '80000'),
        '{rank_2,0,amount}', '60000'),
      '{rank_3,0,amount}', '50000'),
    '{rank_4_10,0,amount}', '30000'),
  '{participant,0,amount}', '10000')
WHERE name = 'Demonic Emperor' AND rewards_given = false AND is_active = true;

UPDATE world_bosses SET loot_table = jsonb_set(
  jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(loot_table,
          '{rank_1,0,amount}', '160000'),
        '{rank_2,0,amount}', '120000'),
      '{rank_3,0,amount}', '100000'),
    '{rank_4_10,0,amount}', '60000'),
  '{participant,0,amount}', '20000')
WHERE name = 'Ancient Dragon' AND rewards_given = false AND is_active = true;

UPDATE world_bosses SET loot_table = jsonb_set(
  jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(loot_table,
          '{rank_1,0,amount}', '320000'),
        '{rank_2,0,amount}', '240000'),
      '{rank_3,0,amount}', '200000'),
    '{rank_4_10,0,amount}', '120000'),
  '{participant,0,amount}', '40000')
WHERE name = 'Corrupted Immortal' AND rewards_given = false AND is_active = true;

UPDATE world_bosses SET loot_table = jsonb_set(
  jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(loot_table,
          '{rank_1,0,amount}', '120000'),
        '{rank_2,0,amount}', '90000'),
      '{rank_3,0,amount}', '75000'),
    '{rank_4_10,0,amount}', '45000'),
  '{participant,0,amount}', '15000')
WHERE name = 'Void Beast' AND rewards_given = false AND is_active = true;

UPDATE world_bosses SET loot_table = jsonb_set(
  jsonb_set(
    jsonb_set(
      jsonb_set(
        jsonb_set(loot_table,
          '{rank_1,0,amount}', '192000'),
        '{rank_2,0,amount}', '144000'),
      '{rank_3,0,amount}', '120000'),
    '{rank_4_10,0,amount}', '72000'),
  '{participant,0,amount}', '24000')
WHERE name = 'Celestial Demon' AND rewards_given = false AND is_active = true