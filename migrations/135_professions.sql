-- MV-7 Mundo Vivo v2 — Profissões Wuxia (Migration 135).
--
-- Aditiva (Lei §5 — launch-server-ready; os 57 do main ficam byte-idênticos
-- porque a flag per-world `profissoes` fica OFF e NENHUM caminho de código
-- escreve aqui sem ela):
--
--   * players.profession — o ofício escolhido (identidade, Lei §3: UMA
--     profissão por jogador; NULL = sem ofício, os 57 intactos). Keys
--     canônicas sem acento: 'alquimista' | 'ferreiro' | 'medico'.
--     Trocar = custo alto + XP zera (disclosure honesta no /oficio).
--   * players.profession_xp — XP do ofício (0 = neutro). Tiers derivados por
--     thresholds no engine (Aprendiz→Artesão→Mestre→Grão-Mestre), nunca
--     persistidos — UMA verdade (core/profession_engine.py).
--   * players.profession_started_at — quando escolheu (disclosure/cerimônia).
--
-- SEM tabela nova: 1 profissão/jogador vive no próprio players (Lei §3
-- profundidade > variedade; o catálogo é engine-data, wipe-safe).
-- O Relatório do Mercado Imperial persiste em region_states.payload
-- ('market_report') — tabela viva do MV-3, zero migration extra.
--
-- Nunca DROP, nunca UPDATE em massa. O engine é core/profession_engine.py.
--
-- IMPORTANTE: o runner faz split em ";". Todo comentário é FULL-LINE — um "--"
-- inline com um ";" perdido truncaria a statement (ver o crash da migration 108).

ALTER TABLE players ADD COLUMN IF NOT EXISTS profession VARCHAR(24) DEFAULT NULL;

ALTER TABLE players ADD COLUMN IF NOT EXISTS profession_xp INTEGER NOT NULL DEFAULT 0;

ALTER TABLE players ADD COLUMN IF NOT EXISTS profession_started_at TIMESTAMPTZ DEFAULT NULL;
