-- Migration 047: Add Dao Law requirements to techniques_catalog
-- Allows tier 5+ techniques to require a minimum number of Dao Law fragments.

ALTER TABLE techniques_catalog
    ADD COLUMN IF NOT EXISTS required_dao_law_id INTEGER REFERENCES dao_laws_catalog(id),
    ADD COLUMN IF NOT EXISTS required_dao_insight INTEGER NOT NULL DEFAULT 0;
