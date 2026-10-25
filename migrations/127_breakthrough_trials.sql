-- Migration 127 — Sprint 8: Cerimónia-Semente (Breakthrough Trials, BT-1..4)
-- Prompts/early_game_breakthrough_trials.md. ADDITIVE + WIPE-SAFE.
--
-- O realm-up early (R0→R1 e R3→R4, hoje silenciosos) vira uma CERIMÓNIA com aposta:
-- Consolidar (稳, seguro) vs Forçar (冲, aposta por um arranque). Se o Cultivo do Corpo
-- está atrasado (gap D = realm − mortal_body_level, BT-3), as odds de Forçar pioram — o
-- aviso do Velho Mendigo vira VERDADE no umbral, e as 4 vias do corpo (Horta/Caça/
-- Ambiental/Combate) finalmente IMPORTAM no breakthrough. Uma luta à-beira-da-morte
-- (Sprint 7) dá uma carga de 顿悟 que deixa Forçar SEM risco (BT-4). Lei §1: Consolidar
-- avança SEMPRE; falhar Forçar NUNCA perde CB/progresso — o realm-up acontece na mesma,
-- o único custo é um revés recuperável (o próximo Forçar fica bloqueado até expirar).
--
-- Esta migration só adiciona DOIS timestamps nullable:
--   • insight_charge_expires_at  — a carga de 顿悟 (Sprint 7 concede; Sprint 8 consome).
--   • breakthrough_setback_until — o revés recuperável após um Forçar falhado.
--
-- ⚠️ REGRA DE FERRO DOS 57 (Lei §1): ambas DEFAULT NULL → os 57 do `main` ficam em NULL =
-- NEUTRO. NADA lê isto no `main`: `breakthrough_trials` está OFF lá (o gate da cerimónia
-- nunca dispara — check_breakthrough fica byte-idêntico), por isso os realm-ups dos 57 são
-- exactamente os de hoje. O combate não lê estes campos.
--
-- IMPORTANTE: o runner faz split em ";". Todo comentário é FULL-LINE (ver migration 108).

ALTER TABLE players ADD COLUMN IF NOT EXISTS insight_charge_expires_at TIMESTAMPTZ DEFAULT NULL;

ALTER TABLE players ADD COLUMN IF NOT EXISTS breakthrough_setback_until TIMESTAMPTZ DEFAULT NULL;
