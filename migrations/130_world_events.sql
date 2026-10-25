-- 130: MV-2 Mundo Vivo v2 — Tiandao Director: eventos celestiais com LUGAR + prazo.
-- Tabela nova, nunca DROP. Mundos com a flag `tiandao_director` OFF (incl. main)
-- nunca escrevem aqui: o Director só corre com a flag ON (OFF = zero queries).
-- payload JSONB: contributors {pid: n} (Maré de Bestas) · miners {pid: iso} (Meteoro).
-- state: active → resolved (contida) | expired (ignorada/dissipada).

CREATE TABLE IF NOT EXISTS world_events (
    id              BIGSERIAL    PRIMARY KEY,
    event_type      VARCHAR(32)  NOT NULL,
    continent_key   VARCHAR(16)  NOT NULL,
    state           VARCHAR(16)  NOT NULL DEFAULT 'active',
    payload         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    progress        INTEGER      NOT NULL DEFAULT 0,
    goal            INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ  DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_world_events_state ON world_events(state, expires_at);
