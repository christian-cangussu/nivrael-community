-- v16.1 — Sect Lineage (Pilar 2 do v16 Living World)
--
-- Adiciona herança ancestral às sects player-created. Cada sect pode agora
-- "herdar" uma das 8 sects anciãs (Azure Cloud, Eternal Flame, Jade
-- Harmony, Iron Mountain, Frozen Peak, Thousand Bloom, Silent Wind,
-- Blazing Sun) + 1 demonic (Abyssal Depths). Define filosofia, bónus
-- (display only em v16.1), continente nativo, rival ancestral.
--
-- Backwards-compat:
--   • Ambas as colunas são NULL-able. Sects existentes ficam com
--     lineage_key=NULL e o engine trata isso como "lineage pendente"
--     (UI oferece o picker com botão dourado no SectTab).
--   • Owner do sect tem ~30 dias para escolher após o deploy
--     (Lei §1 honest disclosure — não auto-default silencioso).
--   • Nenhum CASCADE / FK adicional — `lineage_key` é uma string-key
--     validada no engine (LINEAGE_KEYS tuple).
--
-- WIPE-friendly: as colunas sobrevivem ao wipe do launch (sects table
-- vai truncar, mas a coluna fica para a nova geração escolher.)
--
-- NUNCA DROP, NUNCA RENAME. Defensive contra re-runs.

ALTER TABLE sects
    ADD COLUMN IF NOT EXISTS lineage_key VARCHAR(32) NULL;

ALTER TABLE sects
    ADD COLUMN IF NOT EXISTS lineage_chosen_at TIMESTAMPTZ NULL;

-- Index para rivalry queries futuras (v16.7) e para o "sects by lineage"
-- leaderboard. Predicate-free porque filtramos por exact match.
CREATE INDEX IF NOT EXISTS idx_sect_lineage ON sects(lineage_key);
