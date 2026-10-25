-- ─────────────────────────────────────────────────────────────────────────────
-- 035 · Rescale base stats de jogadores antigos (realm > 0)
--
-- Problema: migration 034 só corrigia realm=0. Jogadores que já avançaram
-- de realm têm stats que cresceram a partir dos antigos defaults (soul=10,
-- bp=10, perception=10, luck=10) via multiplicadores de realm-up.
--
-- Novos defaults: soul=50, bp=50, perception=40, luck=30
-- Ratio de rescale: soul/bp ×5, perception ×4, luck ×3
--
-- Condição segura: soul_strength < 50
--   · Jogadores antigos (start=10) a qualquer realm têm soul < 50
--     (max ao realm 5 com absorb = ~36)
--   · Jogadores novos (start=50) ao realm 1+ têm soul ≥ 57
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE players
SET
    soul_strength = FLOOR(soul_strength * 5),
    battle_power  = FLOOR(battle_power  * 5),
    perception    = FLOOR(perception    * 4),
    luck          = FLOOR(luck          * 3)
WHERE realm > 0
  AND soul_strength < 50;
