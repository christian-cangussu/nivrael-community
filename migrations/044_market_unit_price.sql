-- Migration 044: Convert price_stones (total) → unit_price (per-unit) in marketplace_listings
-- For existing listings with quantity > 1, divide total price by quantity to get unit price.
-- For auctions and qty=1 listings, the value stays the same.

-- Step 1: Rename column (guarded — a FRESH world DB already has `unit_price`
-- from create_all and never had `price_stones`, so an unguarded RENAME would
-- HARD FAIL the whole boot. `main` already has this migration in
-- applied_migrations, so it never re-runs there — the guard only matters when a
-- brand-new world (s2, …) provisions. The runner is dollar-quote aware, so the
-- `DO $$ … END $$;` block is executed as a single statement.)
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'marketplace_listings'
               AND column_name = 'price_stones') THEN
    ALTER TABLE marketplace_listings RENAME COLUMN price_stones TO unit_price;
  END IF;
END $$;

-- Step 2: Convert existing total prices to per-unit prices
-- Only for non-auction, non-sold listings with qty > 1
UPDATE marketplace_listings
SET unit_price = GREATEST(1, unit_price / quantity)
WHERE quantity > 1
  AND is_auction = false
  AND is_sold = false;
