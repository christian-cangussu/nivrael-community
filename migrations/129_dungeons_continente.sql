-- 129: MV-1 Mundo Vivo v2 — dungeons ancoradas por continente.
-- NULL = dungeon não-ancorada (visível em todo lado) → backwards compatible:
-- mundos com a flag `dungeons_regionais` OFF (incl. main) ignoram a coluna.
-- O seed runner (dungeon_seeds.py) popula/atualiza o valor em cada boot.

ALTER TABLE dungeons_catalog ADD COLUMN IF NOT EXISTS continent VARCHAR(16) DEFAULT NULL;
