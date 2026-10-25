-- 073_tribulation_active_uniqueness.sql
-- Ensure only one active tribulation per (player_id, realm).
-- COMPAT beta/live may already contain duplicates, older rows are expired first.

WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY player_id, realm
            ORDER BY started_at DESC, id DESC
        ) AS rn
    FROM tribulations
    WHERE status IN ('pending', 'in_progress')
)
UPDATE tribulations t
SET
    status = 'expired',
    completed_at = COALESCE(t.completed_at, NOW())
FROM ranked r
WHERE t.id = r.id
  AND r.rn > 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_tribulation_active_unique
ON tribulations (player_id, realm)
WHERE status IN ('pending', 'in_progress');
