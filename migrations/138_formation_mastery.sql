-- 138 — 印记 "Marca do Traçado": maestria POR FORMAÇÃO (report [jogador] 06/08 "Script Master").
--
-- O report pedia que a formação usada mil vezes ficasse TATUADA no corpo. A
-- objeção do [jogador] está certa no mecanismo: ativar "no corpo" cria um
-- `PlayerBuff` COMUM com `expires_at` (core/formation_engine.py) — uma formação
-- permanente seria um buff que nunca expira, o sink morreria e o reabastecimento
-- com ele. E título com bônus reabriria a Lei §4, fechada em 04/08 (título é
-- COSMÉTICO). O instinto do [jogador], esse, é Wuxia puro e fica: repetição não vira
-- POSSE, vira MAESTRIA — e a maestria é POR FORMAÇÃO, logo trocar de formação
-- custa o que se acumulou (a escolha corpo-vs-caverna e formação-vs-formação
-- continua a ter peso, que é exatamente a preocupação do [jogador]).
--
-- `player_formations` era `(player_id, formation_id, qty)` e não tinha onde
-- guardar a contagem. Esta é a coluna — na tabela que JÁ é dona do assunto,
-- nunca pendurada num JSONB de outro dono (lição da tabela compartilhada, 04/08).
--
-- Backwards compatible por construção: NOT NULL DEFAULT 0 ⇒ toda row existente
-- nasce a zero, nenhum jogador é penalizado, e a feature está atrás da flag
-- `marca_do_tracado` (OFF em TODO mundo — main byte-idêntica, Lei §5/§11).
--
-- ⚠️ NOTA para quem ler isto depois: `formation_engine._consume_one` APAGAVA a
-- row do bolso quando `qty` chegava a 0. Com esta coluna isso apagaria a
-- maestria junto — a row passa a sobreviver a `qty = 0` quando `body_uses > 0`.

ALTER TABLE player_formations
    ADD COLUMN IF NOT EXISTS body_uses INTEGER NOT NULL DEFAULT 0;
