/*
  # Add Foreign Key Indexes

  This migration adds indexes for foreign key columns to improve query performance.
  Foreign keys without indexes can cause suboptimal performance, especially for JOIN operations.

  ## Changes
  
  1. **portfolio_positions table** - Index on portfolio_id
  2. **portfolios table** - Index on user_id
  3. **price_alerts table** - Index on user_id
  4. **screener_presets table** - Index on user_id
  5. **screening_presets table** - Index on user_id
  6. **screening_results_cache table** - Index on preset_id
  7. **watchlist_items table** - Index on watchlist_id
  8. **watchlists table** - Index on user_id

  ## Performance Impact
  
  - Improves JOIN performance on foreign key relationships
  - Speeds up queries filtering by foreign key columns
  - Enhances referential integrity checks
*/

-- Index for portfolio_positions.portfolio_id foreign key
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_portfolio_id 
ON portfolio_positions(portfolio_id);

-- Index for portfolios.user_id foreign key
CREATE INDEX IF NOT EXISTS idx_portfolios_user_id 
ON portfolios(user_id);

-- Index for price_alerts.user_id foreign key
CREATE INDEX IF NOT EXISTS idx_price_alerts_user_id 
ON price_alerts(user_id);

-- Index for screener_presets.user_id foreign key
CREATE INDEX IF NOT EXISTS idx_screener_presets_user_id 
ON screener_presets(user_id);

-- Index for screening_presets.user_id foreign key
CREATE INDEX IF NOT EXISTS idx_screening_presets_user_id 
ON screening_presets(user_id);

-- Index for screening_results_cache.preset_id foreign key
CREATE INDEX IF NOT EXISTS idx_screening_results_cache_preset_id 
ON screening_results_cache(preset_id);

-- Index for watchlist_items.watchlist_id foreign key
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id 
ON watchlist_items(watchlist_id);

-- Index for watchlists.user_id foreign key
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id 
ON watchlists(user_id);
