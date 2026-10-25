-- 減 P7 — A REDUÇÃO PROGRESSIVA: o jogo deixa de repetir o que você já sabe
-- (decisão do Astra, MESA [017] §4; lote de 2026-09-27)
--
-- A REGRA, textual: *"Depois de uma acção bem-sucedida nesse sistema, oferecer
-- «Já percebi»: a frase introdutória recolhe; «Ajuda» permite recuperá-la. Sem
-- presumir domínio pelo tempo de conta e sem mudar a posição dos comandos."*
--
-- O QUE ESTA COLUNA GUARDA: por SISTEMA, em que ponto está a frase que o explica
-- a este jogador —
--     {"meditar": "apto", "equipar": "recolhido", ...}
--   · ausente   = o jogador ainda não agiu nesse sistema ⇒ a frase aparece e
--                 «Já percebi» NÃO é oferecido;
--   · "apto"    = agiu com sucesso (o SERVIDOR escreve-o, na mesma transacção
--                 da acção confirmada) ⇒ «Já percebi» é oferecido;
--   · "recolhido" = ele escolheu recolher ⇒ a frase recolhe e «Ajuda» a traz.
--
-- ⚠️ PORQUE NO SERVIDOR E NÃO NO APARELHO: a preferência segue o JOGADOR. Quem
-- recolheu no Telegram não pode ver a frase voltar no navegador (UMA CONTA,
-- QUALQUER PLATAFORMA). O precedente da casa é `tutorial_seen`.
--
-- ⚠️ NULL = nada recolhido, nada oferecido = a tela de HOJE, frase a frase. Só é
-- escrita num mundo com a onda ligada (`core/portas.onda_on`); o `main` nunca a
-- escreve, e os 57 do Legado nunca vêem diferença.
--
-- Backwards compatible: ADD COLUMN IF NOT EXISTS, DEFAULT NULL, zero backfill,
-- zero DROP.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS explicacoes JSONB DEFAULT NULL;
