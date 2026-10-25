-- 性 O GÉNERO DO CULTIVADOR — 2026-09-07
--
-- Ordem do owner: "como ainda nao colocamos de escolher masculino e feminino
-- que vamos precisar pro casamento no futuro" + escolha ESCOLHIDA (não sorteada)
-- na criação do personagem.
--
-- ⚠️ DECISÃO REGISTADA (owner, 2026-09-07): o género é **ESCOLHIDO**, e isso é
-- uma **excepção declarada** à espinha "nascer é destino" — raça, raízes e mundo
-- continuam SORTEADOS; o género não. Está escrito aqui porque a próxima pessoa
-- que ler a lei vai perguntar porquê.
--
-- ⚠️ O QUE ESTA COLUNA **NÃO** FAZ, e é o mais importante:
-- o sistema de casamento (道侶, `dao_partners`) **já existe e está no ar** com
-- `player1_id`/`player2_id`, `married_at`, intimidade, anel de jade e coração
-- partido — e **nunca teve género**. Esta coluna NÃO o toca. Fazer o casamento
-- passar a exigir par masculino/feminino **removeria** algo que os jogadores
-- fazem hoje, e isso é decisão do owner, à parte e explícita.
-- (Regra de segurança da casa: nunca quebrar o que jogadores reais já usam.)
--
-- ⚠️ NULL É UM ESTADO LEGÍTIMO, não um defeito a corrigir: os ~248 jogadores
-- existentes nascem sem género e o jogo tem de os servir inteiros. É por isso
-- que existe uma TERCEIRA figura de cultivador (背影, de costas) — o estado
-- honesto de quem ainda não escolheu. Nada é gated por esta coluna.
--
-- Aditiva, idempotente, sem DROP, sem backfill. Compatível para trás.

ALTER TABLE players
    ADD COLUMN IF NOT EXISTS gender VARCHAR(8) DEFAULT NULL;

COMMENT ON COLUMN players.gender IS
    'male | female | NULL. NULL = ainda nao escolheu (os 248 do beta). Escolhido na criacao (excepcao declarada a lei "nascer e destino"). NAO e usado por dao_partners: o casamento e gender-free por desenho.';
