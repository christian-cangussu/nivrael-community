-- v14.9 round 4 (2026-05-20): owner reportou que após enviar um desafio
-- e o adversário aceitar, o challenger nunca via o resultado — só o
-- target via o CombatResultModal. Owner: "Enviei combate pro cara dentro
-- do app nao saiu log nem mensagem nem nada, eu nao sei quem ganhou ou
-- quem perdeu".
--
-- Fix: per-party `seen_at` timestamps. Endpoints podem detectar outcomes
-- não vistos pelo challenger e (a) emitir notif na bell, (b) listar no
-- novo "Histórico" segment do PvP inbox modal. Marca seen quando o
-- player abre o histórico.
--
-- Backwards-compatible 100% — colunas nullable, default NULL.

ALTER TABLE pvp_challenges
    ADD COLUMN IF NOT EXISTS challenger_seen_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS target_seen_at     TIMESTAMPTZ NULL;

-- Resolved + unseen lookup index — fast filter for notif bell + history list.
CREATE INDEX IF NOT EXISTS idx_pvp_unseen_challenger
    ON pvp_challenges (challenger_id, resolved_at DESC)
    WHERE status IN ('completed', 'declined', 'cancelled', 'expired')
      AND challenger_seen_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_pvp_unseen_target
    ON pvp_challenges (target_id, resolved_at DESC)
    WHERE status IN ('completed', 'declined', 'cancelled', 'expired')
      AND target_seen_at IS NULL;
