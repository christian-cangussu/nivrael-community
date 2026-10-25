-- TEC-1 Técnicas & Escassez — A Biblioteca da Seita (Migration 136).
--
-- Aditiva (Lei §5 — launch-server-ready; os 57 do main ficam byte-idênticos
-- porque a flag per-world `biblioteca_seitas` fica OFF e NENHUM caminho de
-- código escreve aqui sem ela):
--
--   * techniques_catalog.library_tier — a ESTANTE da Biblioteca da casa
--     (1 = Externa, grátis ao entrar; 2 = Interna, posto inner + CP;
--     3 = Núcleo, posto core + CP + 1 quest da casa). NULL = fora do novo
--     modelo de estantes (técnicas comuns E as 45 legadas v16.4c ids
--     500-544, que continuam no learn grátis por posto — intocadas).
--   * techniques_catalog.library_cp_cost — o custo em contribuição
--     (saldo do Pavilhão de Mérito, Mig 118) para destrancar a arte.
--     Seedado dos knobs LIB_T2_CP/LIB_T3_CP (0 no tier 1).
--   * player_sect_techniques — o REGISTRO de quem aprendeu o quê de qual
--     casa (a memória da Biblioteca). Sair da seita NUNCA apaga rows daqui:
--     tier 3 fica LOCKADO (não usa) até voltar à MESMA casa (regra
--     cross-sect §3 da Constituição technique_scarcity_economy.md).
--     cp_paid é auditoria do sink (nunca refund automático).
--
-- O engine é core/sect_library_engine.py. Nunca DROP, nunca UPDATE em massa.
--
-- IMPORTANTE: o runner faz split em ";". Todo comentário é FULL-LINE — um "--"
-- inline com um ";" perdido truncaria a statement (ver o crash da migration 108).

ALTER TABLE techniques_catalog ADD COLUMN IF NOT EXISTS library_tier INTEGER DEFAULT NULL;

ALTER TABLE techniques_catalog ADD COLUMN IF NOT EXISTS library_cp_cost INTEGER DEFAULT NULL;

CREATE TABLE IF NOT EXISTS player_sect_techniques (
    player_id BIGINT NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    technique_id INTEGER NOT NULL REFERENCES techniques_catalog(id),
    sect_key VARCHAR(32) NOT NULL,
    cp_paid INTEGER NOT NULL DEFAULT 0,
    unlocked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, technique_id)
);

CREATE INDEX IF NOT EXISTS idx_pst_sect ON player_sect_techniques (sect_key, technique_id);
