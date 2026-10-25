-- MV-4 Mundo Vivo v2 — Corpo Profundo: os 12 MERIDIANOS 经脉 (Migration 132).
--
-- Duas colunas novas em players, ambas ADITIVAS e neutras (Lei §5 — launch-
-- server-ready; os 57 do main ficam byte-idênticos porque a flag per-world
-- `corpo_profundo` fica OFF e NENHUM caminho de código escreve aqui sem ela):
--
--   * meridians_opened  — canal aberto -> {opened_at, attempts}. '{}' = nenhum
--                         canal aberto (o estado de TODOS os jogadores hoje).
--   * meridian_ritual   — o ritual EM CURSO (1 por jogador): {channel, stage,
--                         started_at, ends_at, place_key, place_mult, attempts,
--                         chance}. NULL = nenhum ritual em curso.
--
-- Nunca DROP, nunca UPDATE em massa. O engine é core/meridian_engine.py.
--
-- IMPORTANTE: o runner faz split em ";". Todo comentário é FULL-LINE — um "--"
-- inline com um ";" perdido truncaria a statement (ver o crash da migration 108).

ALTER TABLE players ADD COLUMN IF NOT EXISTS meridians_opened JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE players ADD COLUMN IF NOT EXISTS meridian_ritual JSONB DEFAULT NULL;
