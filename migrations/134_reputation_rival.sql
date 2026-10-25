-- MV-6 Mundo Vivo v2 — Reputação regional + RIVAL com memória (Migration 134).
--
-- Aditiva (Lei §5 — launch-server-ready; os 57 do main ficam byte-idênticos
-- porque a flag per-world `reputacao_rival` fica OFF e NENHUM caminho de
-- código escreve aqui sem ela):
--
--   * player_region_rep — 1 INT por (jogador, continente): a memória do LUGAR
--     sobre você. Sobe com o que você FAZ ali (storylet concluído, bounty
--     caçado, maré contida, cultivador local vencido) e decai −1/semana rumo a
--     zero nos continentes onde você NÃO está (o lugar esquece — nos dois
--     sentidos: fama esvai, rancor cicatriza; Lei §1 — nunca um poço eterno).
--     payload JSONB = contadores auxiliares (cap diário de vitórias, carimbo
--     do decay) — nunca a verdade do rep.
--
--   * players.rival_npc_id + players.rival_state — O RIVAL (patent-safe:
--     1 rival por jogador, sem hierarquia, memória = texto + power scaling).
--     rival_state JSONB = {defeats, last_defeat_at, taunt_seed, returned,
--     spared_count, last_spared_at} — o rival LEMBRA quantas vezes caiu e
--     quantas vezes te poupou. FK → npc_cultivators ON DELETE SET NULL
--     (NPCs nunca são apagados hoje; cinto-e-suspensórios).
--
-- Nunca DROP, nunca UPDATE em massa. O engine é core/reputation_engine.py.
--
-- IMPORTANTE: o runner faz split em ";". Todo comentário é FULL-LINE — um "--"
-- inline com um ";" perdido truncaria a statement (ver o crash da migration 108).

CREATE TABLE IF NOT EXISTS player_region_rep (
    player_id      BIGINT       NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    continent_key  VARCHAR(16)  NOT NULL,
    rep            INTEGER      NOT NULL DEFAULT 0,
    payload        JSONB        NOT NULL DEFAULT '{}'::jsonb,
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (player_id, continent_key)
);

ALTER TABLE players ADD COLUMN IF NOT EXISTS rival_npc_id BIGINT DEFAULT NULL REFERENCES npc_cultivators(id) ON DELETE SET NULL;

ALTER TABLE players ADD COLUMN IF NOT EXISTS rival_state JSONB DEFAULT NULL;

-- O board de bounties exclui NPCs que são rival de ALGUÉM (sem loop com o
-- board) — este índice parcial torna essa probe barata (poucos rivais vivos).
CREATE INDEX IF NOT EXISTS idx_players_rival_npc ON players (rival_npc_id) WHERE rival_npc_id IS NOT NULL;
