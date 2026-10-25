-- Fase A3 do Motor de Mundo Vivo (pivot 2026-08-11) — RANCOR QUE NASCE NO JOGO.
--
-- Até aqui a rivalidade entre as 9 Casas era ESTÁTICA: escrita à mão em
-- `WORLD_SECT_META[...]["rival"]`, semeada uma vez em `world_sects.rival_id`, e
-- nunca mais mexida. Uma casa saqueada não guardava ódio nenhum de quem a
-- saqueou — no batimento seguinte decidia exatamente igual. É por isso que as
-- cadeias de consequência do mundo morriam em 2-4 saltos: nada realimentava o
-- que podia acontecer a seguir.
--
-- `grudges` é o primeiro estado do mundo que o PRÓPRIO mundo escreve:
--     {"<sect_id>": <intensidade>}   — quem me deve, e quanto.
-- Sobe quando levo um saque, decai devagar a cada batimento (ódio eterno é tão
-- morto quanto ódio nenhum), e enviesa para quem escolher atacar.
--
-- ⚠️ ESTADO DE RUNTIME, NUNCA SEMEADO. É a mesma regra do `momentum` e do
-- `strength` (ver o comentário do Pass 4 em `database/seeds/world_sects_seeds.py`):
-- o seed runner reescreve `signature_techs` e os escalares de personalidade a
-- CADA boot, e uma coluna de runtime que ele tocasse seria zerada a cada deploy.
-- Nenhum Pass do seed pode aprender a escrever aqui.
--
-- Backwards compatible: DEFAULT '{}' ⇒ toda linha existente nasce sem rancor e o
-- comportamento é byte-idêntico até o primeiro saque do primeiro batimento.

ALTER TABLE world_sects
    ADD COLUMN IF NOT EXISTS grudges JSONB NOT NULL DEFAULT '{}'::jsonb;
