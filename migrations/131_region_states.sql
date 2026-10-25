-- 131: MV-3 Mundo Vivo v2 — Estados Regionais: cada continente ganha um estado
-- vivo (prospera/tensa/sitiada/festival) com overrides mecânicos (preços,
-- risco de explore, densidade de qi). Tabela nova, nunca DROP. Mundos com a
-- flag `estados_regionais` OFF (incl. main) nunca escrevem aqui: as transições
-- só acontecem no sync do World Pulse com a flag ON (OFF = zero queries).
-- payload JSONB: reservado (ex.: causa da última transição, contadores).
-- state: prospera (default) | tensa | sitiada | festival.

CREATE TABLE IF NOT EXISTS region_states (
    continent_key   VARCHAR(16)  PRIMARY KEY,
    state           VARCHAR(16)  NOT NULL DEFAULT 'prospera',
    since           TIMESTAMPTZ  NOT NULL DEFAULT now(),
    payload         JSONB        NOT NULL DEFAULT '{}'::jsonb
);
