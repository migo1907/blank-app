/*
  # Fix Security Issues - Indexes and Functions

  1. Performance Improvements
    - Add covering indexes for all unindexed foreign keys
    - Remove unused indexes that add overhead without benefit

  2. Security Fixes
    - Fix function search path mutability issues
    - Review and document materialized view API access

  3. Foreign Key Indexes Added
    - portfolio_positions.portfolio_id
    - portfolios.user_id
    - price_alerts.user_id
    - screener_presets.user_id
    - screening_presets.user_id
    - screening_results_cache.preset_id
    - watchlist_items.watchlist_id
    - watchlists.user_id

  4. Unused Indexes Removed
    - Various unused indexes on dividend_history, spx_scanner_results, 
      intraday_options_signals, stock_signals, quant_filter_signals,
      ibkr_options_realtime, and tick_data tables
*/

-- Add covering indexes for foreign keys
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_portfolio_id 
  ON portfolio_positions(portfolio_id);

CREATE INDEX IF NOT EXISTS idx_portfolios_user_id 
  ON portfolios(user_id);

CREATE INDEX IF NOT EXISTS idx_price_alerts_user_id 
  ON price_alerts(user_id);

CREATE INDEX IF NOT EXISTS idx_screener_presets_user_id 
  ON screener_presets(user_id);

CREATE INDEX IF NOT EXISTS idx_screening_presets_user_id 
  ON screening_presets(user_id);

CREATE INDEX IF NOT EXISTS idx_screening_results_cache_preset_id 
  ON screening_results_cache(preset_id);

CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id 
  ON watchlist_items(watchlist_id);

CREATE INDEX IF NOT EXISTS idx_watchlists_user_id 
  ON watchlists(user_id);

-- Remove unused indexes that add overhead without providing value
DROP INDEX IF EXISTS idx_dividend_history_symbol;
DROP INDEX IF EXISTS idx_spx_scanner_results_signal;
DROP INDEX IF EXISTS idx_intraday_options_ticker;
DROP INDEX IF EXISTS idx_intraday_options_timestamp;
DROP INDEX IF EXISTS idx_intraday_options_side;
DROP INDEX IF EXISTS idx_intraday_options_ticker_timestamp;
DROP INDEX IF EXISTS idx_stock_signals_ticker;
DROP INDEX IF EXISTS idx_stock_signals_type;
DROP INDEX IF EXISTS idx_stock_signals_active;
DROP INDEX IF EXISTS idx_quant_filter_signals_symbol;
DROP INDEX IF EXISTS idx_quant_filter_signals_status;
DROP INDEX IF EXISTS idx_ibkr_options_symbol;
DROP INDEX IF EXISTS idx_ibkr_options_expiration;
DROP INDEX IF EXISTS idx_ibkr_options_timestamp;
DROP INDEX IF EXISTS idx_tick_data_symbol;

-- Fix function search path mutability issue
-- Drop trigger first, then function, then recreate both
DROP TRIGGER IF EXISTS update_ibkr_options_realtime_updated_at ON ibkr_options_realtime;
DROP TRIGGER IF EXISTS update_ibkr_options_updated_at_trigger ON ibkr_options_realtime;

DROP FUNCTION IF EXISTS update_ibkr_options_updated_at() CASCADE;

CREATE OR REPLACE FUNCTION update_ibkr_options_updated_at()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- Recreate the trigger with proper naming
CREATE TRIGGER update_ibkr_options_realtime_updated_at
  BEFORE UPDATE ON ibkr_options_realtime
  FOR EACH ROW
  EXECUTE FUNCTION update_ibkr_options_updated_at();

-- Add comment explaining materialized view API access
COMMENT ON MATERIALIZED VIEW stock_screener_data IS 
  'Public read access is intentional - this aggregates stock data for screening. 
   Data is non-sensitive market information. Refresh is controlled by service role only.
   RLS is not applicable to materialized views - access is controlled via grants.';
