-- ─────────────────────────────────────────────────────────────────────────────
-- 034 · Balance Pass — actualiza seeds existentes que o seeder não re-escreve
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Pills que estavam com required_alchemy_tier errado
--    Time Dilation Pill (id 10):  tier 1 → 3
--    Heaven Defying Pill (id 14): tier 1 → 4
UPDATE pills_catalog SET required_alchemy_tier = 3 WHERE id = 10 AND required_alchemy_tier < 3;
UPDATE pills_catalog SET required_alchemy_tier = 4 WHERE id = 14 AND required_alchemy_tier < 4;

-- 2. Alchemy XP thresholds (tabela de skills já criada pela migration 026)
--    Não existe tabela de tiers no DB (é código Python), então não há nada a migrar aqui.
--    Os novos valores de ALCHEMY_TIERS e FORGE_TIERS são lidos do código em runtime.

-- 3. Jogadores existentes: garante que stats iniciais não fiquem com valores zerados
--    (só actualiza quem tem os valores antigos de default=10)
UPDATE players SET soul_strength = 50  WHERE soul_strength  = 10  AND realm = 0;
UPDATE players SET battle_power  = 50  WHERE battle_power   = 10  AND realm = 0;
UPDATE players SET perception    = 40  WHERE perception     = 10  AND realm = 0;
UPDATE players SET luck          = 30  WHERE luck           = 10  AND realm = 0;
