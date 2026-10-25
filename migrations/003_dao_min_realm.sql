ALTER TABLE dao_laws_catalog ADD COLUMN IF NOT EXISTS min_realm INTEGER NOT NULL DEFAULT 0;

UPDATE dao_laws_catalog SET min_realm = 5 WHERE id IN (1, 2, 3);
UPDATE dao_laws_catalog SET min_realm = 6 WHERE id IN (4, 5);
UPDATE dao_laws_catalog SET min_realm = 8 WHERE id = 6
