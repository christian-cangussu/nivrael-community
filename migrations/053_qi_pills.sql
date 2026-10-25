-- Qi Pills (stat boost pills) for foundation preparation
-- Seeds handle the actual insertion via alchemy_seeds.py (idempotent).
-- This migration ensures pills exist even if seeds haven't re-run.

INSERT INTO pills_catalog (id, name, ingredients, difficulty, effect_type, effect_value, duration_minutes, description, emoji, min_realm, required_alchemy_tier)
VALUES
    (21, 'Soul Condensation Pill', '[{"herb_id": 1, "qty": 5}, {"herb_id": 12, "qty": 3}]', 1, 'stat_boost', 5.0, 0, 'Permanently increases Soul Strength by 5 (cap: 80).', '👻', 0, 1),
    (22, 'Mind Clarity Pill', '[{"herb_id": 1, "qty": 4}, {"herb_id": 9, "qty": 3}]', 1, 'stat_boost', 5.0, 0, 'Permanently increases Perception by 5 (cap: 65).', '👁️', 0, 1),
    (23, 'Fortune Pill', '[{"herb_id": 12, "qty": 3}, {"herb_id": 2, "qty": 2}]', 1, 'stat_boost', 3.0, 0, 'Permanently increases Luck by 3 (cap: 50).', '🍀', 0, 1),
    (24, 'Greater Soul Pill', '[{"herb_id": 2, "qty": 5}, {"herb_id": 3, "qty": 3}]', 2, 'stat_boost', 10.0, 0, 'Permanently increases Soul Strength by 10 (cap: 120).', '👻', 2, 2),
    (25, 'Greater Mind Pill', '[{"herb_id": 9, "qty": 4}, {"herb_id": 6, "qty": 3}]', 2, 'stat_boost', 10.0, 0, 'Permanently increases Perception by 10 (cap: 100).', '👁️', 3, 2),
    (26, 'Greater Fortune Pill', '[{"herb_id": 3, "qty": 3}, {"herb_id": 11, "qty": 3}]', 3, 'stat_boost', 6.0, 0, 'Permanently increases Luck by 6 (cap: 80).', '🍀', 3, 3)
ON CONFLICT (id) DO NOTHING;
