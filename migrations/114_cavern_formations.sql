-- Onda 5 (Fase 2) — Cavernas Pessoais 洞府 + Matrizes/Formações 阵法.
-- Gives PURPOSE to the Fase 1 exploration loot: the player CRAFTS Formações
-- (timed consumables — a Formação activated "on the body" is just a PlayerBuff
-- row, NO new buff table) from the herbs/ores/stones that exploration and the
-- dungeons already drop (a REAL material sink — Lei §3), and ESTABLISHES one
-- Personal Cavern per player (capped idle qi accrual + one Formação slot).
--
-- Everything here is ADDITIVE + WIPE-SAFE (Lei Primordial §5):
--   * formation_catalog is SEED-able content (the seed runner upserts it on
--     startup — database/seeds/formation_seeds.py); rows survive the wipe.
--   * player_formations / player_cavern are light per-player state, net-new,
--     no existing player data touched. No jade anywhere (Lei §4) — costs are
--     materials + spirit stones only.
--   * A Formação active "on the body" reuses the existing player_buffs table
--     (created long ago) — NO parallel buff system (Lei §3).
--   * CREATE TABLE IF NOT EXISTS only; no DROP, no rename, no ALTER on the
--     57 live players' tables.
--
-- NB: this migration runner splits on ";". Keep every comment on its OWN full
-- line starting with "--" (NEVER an inline comment containing a ";") — an
-- inline ";" inside a comment truncated a CREATE TABLE in migration 108 and
-- crash-looped prod. (db.py now also strips inline comments, but do not rely
-- on luck.)

-- The craftable catalog. `key` is the stable i18n slug (formation_name_<key>).
-- `effect_type` matches the EXISTING PlayerBuff vocabulary (bp_boost /
-- defense_boost / qi_regen_boost / dao_fragment_chance / perception_boost)
-- plus the ONE new exploration consumer `explore_protection`.
-- `recipe` JSONB: {"stones": int, "herbs": [{"herb_id": int, "qty": int}],
-- "ores": [{"ore_id": int, "qty": int}]} — mirrors ForgeRecipe/PillCatalog.
CREATE TABLE IF NOT EXISTS formation_catalog (
    id                INTEGER      PRIMARY KEY,
    key               VARCHAR(32)  UNIQUE NOT NULL,
    emoji             VARCHAR(8)   NOT NULL DEFAULT '🔯',
    effect_type       VARCHAR(32)  NOT NULL,
    effect_value      FLOAT        NOT NULL DEFAULT 1.0,
    duration_minutes  INTEGER      NOT NULL DEFAULT 60,
    tier              INTEGER      NOT NULL DEFAULT 1,
    min_realm         INTEGER      NOT NULL DEFAULT 0,
    recipe            JSONB        NOT NULL DEFAULT '{}'::jsonb
);

-- Crafted-but-not-yet-activated Formações (the player's formation pouch).
CREATE TABLE IF NOT EXISTS player_formations (
    player_id     BIGINT   NOT NULL REFERENCES players(telegram_id) ON DELETE CASCADE,
    formation_id  INTEGER  NOT NULL REFERENCES formation_catalog(id),
    qty           INTEGER  NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, formation_id)
);

-- The Personal Cavern 洞府 — ONE per player (PK player_id). Idle qi accrues
-- from last_claimed_at (capped at CAVERN_CAP_HOURS in the engine, scaled to
-- realm — conservative, a retention net, NEVER pay-to-win). The Formação slot
-- (active_formation_id + set_at/expires_at window) boosts the idle yield
-- (qi_regen_boost) or grants Dao-fragment comprehension (dao_fragment_chance).
CREATE TABLE IF NOT EXISTS player_cavern (
    player_id             BIGINT       PRIMARY KEY REFERENCES players(telegram_id) ON DELETE CASCADE,
    continent_key         VARCHAR(16)  NOT NULL DEFAULT 'linghe',
    established_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_claimed_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    total_qi_claimed      BIGINT       NOT NULL DEFAULT 0,
    active_formation_id   INTEGER      REFERENCES formation_catalog(id),
    formation_set_at      TIMESTAMPTZ,
    formation_expires_at  TIMESTAMPTZ
);
