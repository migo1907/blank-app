/*
  # Recreate Views with Security Invoker

  This migration drops and recreates all views with explicit security_invoker = true option.
  The previous migration may not have properly set this option.

  ## Changes
  
  1. **Drop All Security-Related Views**
  2. **Recreate with Explicit Security Invoker**
     - top_gainers
     - top_losers
     - latest_stock_prices
     - latest_stock_technicals
     - active_signals
     - signal_performance

  ## Security Notes
  
  - Views execute with invoker's privileges (SECURITY INVOKER)
  - RLS policies on underlying tables apply
  - More secure than SECURITY DEFINER
*/

-- Drop all views
DROP VIEW IF EXISTS top_gainers CASCADE;
DROP VIEW IF EXISTS top_losers CASCADE;
DROP VIEW IF EXISTS latest_stock_prices CASCADE;
DROP VIEW IF EXISTS latest_stock_technicals CASCADE;
DROP VIEW IF EXISTS active_signals CASCADE;
DROP VIEW IF EXISTS signal_performance CASCADE;

-- Recreate top_gainers with security_invoker
CREATE VIEW top_gainers
WITH (security_invoker = true)
AS
SELECT 
  symbol,
  name,
  price,
  change_percent,
  volume,
  market_cap
FROM stock_screener_data
WHERE change_percent > 0
ORDER BY change_percent DESC
LIMIT 20;

-- Recreate top_losers with security_invoker
CREATE VIEW top_losers
WITH (security_invoker = true)
AS
SELECT 
  symbol,
  name,
  price,
  change_percent,
  volume,
  market_cap
FROM stock_screener_data
WHERE change_percent < 0
ORDER BY change_percent ASC
LIMIT 20;

-- Recreate latest_stock_prices with security_invoker
CREATE VIEW latest_stock_prices
WITH (security_invoker = true)
AS
SELECT DISTINCT ON (symbol)
  symbol,
  price,
  change_percent,
  change,
  volume,
  high,
  low,
  timestamp
FROM stock_prices
ORDER BY symbol, timestamp DESC;

-- Recreate latest_stock_technicals with security_invoker
CREATE VIEW latest_stock_technicals
WITH (security_invoker = true)
AS
SELECT DISTINCT ON (symbol)
  symbol,
  rsi_14,
  macd,
  macd_signal,
  macd_histogram,
  sma_20,
  sma_50,
  sma_200,
  ema_12,
  ema_26,
  bb_upper,
  bb_middle,
  bb_lower,
  signal,
  timestamp
FROM stock_technicals
ORDER BY symbol, timestamp DESC;

-- Recreate active_signals with security_invoker
CREATE VIEW active_signals
WITH (security_invoker = true)
AS
SELECT 
  id,
  symbol,
  action,
  price,
  target1,
  target2,
  stop_loss,
  indicator_name,
  timeframe,
  strength,
  status,
  triggered_at,
  notes
FROM tradingview_signals
WHERE status = 'active'
ORDER BY triggered_at DESC;

-- Recreate signal_performance with security_invoker
CREATE VIEW signal_performance
WITH (security_invoker = true)
AS
SELECT 
  action,
  indicator_name,
  COUNT(*) as total_signals,
  AVG(pnl_percent) as avg_return_percent,
  COUNT(CASE WHEN pnl_percent > 0 THEN 1 END) as winning_signals,
  COUNT(CASE WHEN pnl_percent <= 0 THEN 1 END) as losing_signals,
  MAX(pnl_percent) as best_return,
  MIN(pnl_percent) as worst_return
FROM tradingview_signals
WHERE triggered_at > NOW() - INTERVAL '30 days'
  AND pnl_percent IS NOT NULL
GROUP BY action, indicator_name
ORDER BY avg_return_percent DESC;

-- Grant appropriate permissions
GRANT SELECT ON top_gainers TO anon, authenticated;
GRANT SELECT ON top_losers TO anon, authenticated;
GRANT SELECT ON latest_stock_prices TO anon, authenticated;
GRANT SELECT ON latest_stock_technicals TO anon, authenticated;
GRANT SELECT ON active_signals TO anon, authenticated;
GRANT SELECT ON signal_performance TO anon, authenticated;
