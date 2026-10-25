-- MV-5 Mundo Vivo v2 — Quests VIVAS: storylets/QBN (Migration 133).
--
-- Duas tabelas NOVAS, ambas aditivas (Lei §5 — launch-server-ready; os 57 do
-- main ficam byte-idênticos porque a flag per-world `quests_vivas` fica OFF e
-- NENHUM caminho de código escreve aqui sem ela):
--
--   * storylet_catalog — o catálogo seed-able (wipe-safe) de storylets: pedaços
--     de história com requirements JSONB (lugar, estado regional, evento ativo,
--     karma, path, reino, meridianos, flag) que só EXISTEM quando o mundo os
--     torna verdadeiros. objective_type REUSA os trackers existentes das quests
--     (lição MV-1: NUNCA deep-linkar objetivo sem tracker). reward JSONB =
--     pedras / itens nativos / karma — NUNCA técnica (Lei §12), NUNCA jade.
--     Nomes/descrições/diálogos são server-resolved via locales de CHAT
--     (keys derivadas: sty_<key>_name/_desc/_d1/_d2 — convenção, sem coluna).
--
--   * player_storylets — o estado por jogador: offered -> accepted -> done
--     (ou declined / expired). context JSONB = onde/quando a quest nasceu
--     (a quest LEMBRA o continente, o estado do mundo e quem a ofereceu).
--     Expiry é LAZY (padrão world_sect_recruiter_pending): expires_at filtrado
--     na leitura, sem sweep job; storylet COMPLETA nunca expira (Lei §1).
--
-- Nunca DROP, nunca UPDATE em massa. O engine é core/storylet_engine.py.
--
-- IMPORTANTE: o runner faz split em ";". Todo comentário é FULL-LINE — um "--"
-- inline com um ";" perdido truncaria a statement (ver o crash da migration 108).

CREATE TABLE IF NOT EXISTS storylet_catalog (
    key             VARCHAR(48)  PRIMARY KEY,
    giver_kind      VARCHAR(16)  NOT NULL DEFAULT 'npc_cultivator',
    emoji           VARCHAR(8)   NOT NULL DEFAULT '📜',
    requirements    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    objective_type  VARCHAR(32)  NOT NULL,
    objective_count INTEGER      NOT NULL DEFAULT 1,
    reward          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    expires_hours   INTEGER      NOT NULL DEFAULT 48,
    weight          INTEGER      NOT NULL DEFAULT 10,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS player_storylets (
    id            BIGSERIAL    PRIMARY KEY,
    player_id     BIGINT       NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    storylet_key  VARCHAR(48)  NOT NULL REFERENCES storylet_catalog(key),
    status        VARCHAR(16)  NOT NULL DEFAULT 'offered',
    progress      INTEGER      NOT NULL DEFAULT 0,
    context       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    offered_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    accepted_at   TIMESTAMPTZ,
    resolved_at   TIMESTAMPTZ,
    expires_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_player_storylets_player ON player_storylets (player_id, status);

-- Review fix (MV-5): o pacer "1 oferta aberta por jogador" é check-then-insert;
-- sem isto, N requests concorrentes (praça+viagem+explore) mintariam N ofertas
-- (até N duplicatas pagáveis — impressora). Defesa em profundidade: o engine
-- serializa com pg_advisory_xact_lock por jogador E este índice único parcial
-- torna a duplicata estruturalmente impossível (o insert perdedor falha no
-- savepoint e o mint devolve None — nunca envenena a transação do caller).
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_storylets_open_offer ON player_storylets (player_id) WHERE status = 'offered';
