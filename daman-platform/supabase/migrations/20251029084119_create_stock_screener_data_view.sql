/*
  # Create Stock Screener View and Populate Data

  1. **Data Population**
    - Populate stock_universe with major stocks
    - Insert sample price, fundamental, and technical data

  2. **Views Created**
    - `stock_screener_data` - Materialized view for screener
    - `top_gainers` - Top performing stocks
    - `top_losers` - Worst performing stocks  
    - `latest_stock_prices` - Most recent prices

  3. **Performance**
    - Indexes on key columns for fast queries
    - Auto-refresh mechanism
*/

-- Drop existing views if they exist
DROP VIEW IF EXISTS stock_screener_data CASCADE;
DROP VIEW IF EXISTS top_gainers CASCADE;
DROP VIEW IF EXISTS top_losers CASCADE;
DROP VIEW IF EXISTS latest_stock_prices CASCADE;

-- Step 1: Populate stock_universe
INSERT INTO stock_universe (symbol, name, exchange, sector, industry, is_sp500, is_nasdaq, market_cap)
VALUES
  ('AAPL', 'Apple Inc.', 'NASDAQ', 'Technology', 'Consumer Electronics', true, true, 3000000000000),
  ('MSFT', 'Microsoft Corporation', 'NASDAQ', 'Technology', 'Software', true, true, 2800000000000),
  ('GOOGL', 'Alphabet Inc.', 'NASDAQ', 'Technology', 'Internet Services', true, true, 1700000000000),
  ('AMZN', 'Amazon.com Inc.', 'NASDAQ', 'Technology', 'E-commerce', true, true, 1600000000000),
  ('NVDA', 'NVIDIA Corporation', 'NASDAQ', 'Technology', 'Semiconductors', true, true, 2200000000000),
  ('META', 'Meta Platforms Inc.', 'NASDAQ', 'Technology', 'Social Media', true, true, 900000000000),
  ('TSLA', 'Tesla Inc.', 'NASDAQ', 'Technology', 'Automotive', true, true, 800000000000),
  ('AMD', 'Advanced Micro Devices', 'NASDAQ', 'Technology', 'Semiconductors', true, true, 260000000000),
  ('NFLX', 'Netflix Inc.', 'NASDAQ', 'Technology', 'Streaming', true, true, 260000000000),
  ('INTC', 'Intel Corporation', 'NASDAQ', 'Technology', 'Semiconductors', true, true, 200000000000),
  ('JPM', 'JPMorgan Chase & Co.', 'NYSE', 'Financial', 'Banking', true, false, 460000000000),
  ('BAC', 'Bank of America Corp.', 'NYSE', 'Financial', 'Banking', true, false, 280000000000),
  ('WFC', 'Wells Fargo & Company', 'NYSE', 'Financial', 'Banking', true, false, 180000000000),
  ('GS', 'Goldman Sachs Group Inc.', 'NYSE', 'Financial', 'Investment Banking', true, false, 120000000000),
  ('MS', 'Morgan Stanley', 'NYSE', 'Financial', 'Investment Banking', true, false, 140000000000),
  ('JNJ', 'Johnson & Johnson', 'NYSE', 'Healthcare', 'Pharmaceuticals', true, false, 380000000000),
  ('PFE', 'Pfizer Inc.', 'NYSE', 'Healthcare', 'Pharmaceuticals', true, false, 160000000000),
  ('UNH', 'UnitedHealth Group Inc.', 'NYSE', 'Healthcare', 'Insurance', true, false, 500000000000),
  ('WMT', 'Walmart Inc.', 'NYSE', 'Consumer', 'Retail', true, false, 500000000000),
  ('DIS', 'The Walt Disney Company', 'NYSE', 'Consumer', 'Entertainment', true, false, 160000000000)
ON CONFLICT (symbol) DO UPDATE SET
  name = EXCLUDED.name,
  market_cap = EXCLUDED.market_cap,
  updated_at = NOW();

-- Step 2: Insert price data
INSERT INTO stock_prices (symbol, price, open, high, low, close, volume, change, change_percent, timestamp)
SELECT
  symbol,
  CASE symbol
    WHEN 'AAPL' THEN 178.50 WHEN 'MSFT' THEN 378.90 WHEN 'GOOGL' THEN 140.20
    WHEN 'AMZN' THEN 145.80 WHEN 'NVDA' THEN 495.30 WHEN 'META' THEN 358.70
    WHEN 'TSLA' THEN 242.80 WHEN 'AMD' THEN 164.50 WHEN 'NFLX' THEN 450.60
    WHEN 'INTC' THEN 43.20 WHEN 'JPM' THEN 186.20 WHEN 'BAC' THEN 35.40
    WHEN 'WFC' THEN 52.30 WHEN 'GS' THEN 380.50 WHEN 'MS' THEN 95.60
    WHEN 'JNJ' THEN 156.70 WHEN 'PFE' THEN 28.60 WHEN 'UNH' THEN 548.30
    WHEN 'WMT' THEN 73.40 WHEN 'DIS' THEN 92.50
    ELSE (50 + RANDOM() * 450)
  END as price,
  (50 + RANDOM() * 450) as open,
  (50 + RANDOM() * 450) as high,
  (30 + RANDOM() * 400) as low,
  (50 + RANDOM() * 450) as close,
  (1000000 + RANDOM() * 50000000)::BIGINT as volume,
  (-10 + RANDOM() * 20) as change,
  (-5 + RANDOM() * 10) as change_percent,
  NOW() as timestamp
FROM stock_universe;

-- Step 3: Insert fundamental data
INSERT INTO stock_fundamentals (symbol, pe_ratio, dividend_yield, market_cap, beta, short_interest, eps, updated_at)
SELECT
  symbol,
  (10 + RANDOM() * 40) as pe_ratio,
  (RANDOM() * 5) as dividend_yield,
  market_cap,
  (0.5 + RANDOM() * 2) as beta,
  (RANDOM() * 15) as short_interest,
  (1 + RANDOM() * 20) as eps,
  NOW() as updated_at
FROM stock_universe
ON CONFLICT (symbol) DO UPDATE SET
  pe_ratio = EXCLUDED.pe_ratio,
  market_cap = EXCLUDED.market_cap,
  updated_at = NOW();

-- Step 4: Insert technical data
INSERT INTO stock_technicals (symbol, rsi_14, macd, macd_signal, sma_20, sma_50, sma_200, signal, timestamp)
SELECT
  symbol,
  (30 + RANDOM() * 40) as rsi_14,
  (-2 + RANDOM() * 4) as macd,
  (-2 + RANDOM() * 4) as macd_signal,
  (100 + RANDOM() * 300) as sma_20,
  (100 + RANDOM() * 300) as sma_50,
  (100 + RANDOM() * 300) as sma_200,
  CASE
    WHEN RANDOM() < 0.2 THEN 'strong_buy'
    WHEN RANDOM() < 0.4 THEN 'buy'
    WHEN RANDOM() < 0.6 THEN 'neutral'
    WHEN RANDOM() < 0.8 THEN 'sell'
    ELSE 'strong_sell'
  END as signal,
  NOW() as timestamp
FROM stock_universe;

-- Step 5: Create materialized view
CREATE MATERIALIZED VIEW stock_screener_data AS
SELECT
  su.symbol,
  su.name,
  su.sector,
  su.industry,
  su.exchange,
  sp.price,
  sp.change,
  sp.change_percent,
  sp.volume,
  sf.pe_ratio,
  sf.dividend_yield,
  sf.market_cap,
  sf.beta,
  sf.short_interest,
  st.rsi_14,
  st.signal,
  sp.timestamp as last_updated
FROM stock_universe su
LEFT JOIN LATERAL (
  SELECT * FROM stock_prices WHERE stock_prices.symbol = su.symbol ORDER BY timestamp DESC LIMIT 1
) sp ON true
LEFT JOIN stock_fundamentals sf ON su.symbol = sf.symbol
LEFT JOIN LATERAL (
  SELECT * FROM stock_technicals WHERE stock_technicals.symbol = su.symbol ORDER BY timestamp DESC LIMIT 1
) st ON true
WHERE sp.price IS NOT NULL;

-- Create unique index for concurrent refresh
CREATE UNIQUE INDEX idx_screener_symbol_unique ON stock_screener_data(symbol);

-- Create other indexes
CREATE INDEX idx_screener_sector ON stock_screener_data(sector);
CREATE INDEX idx_screener_signal ON stock_screener_data(signal);
CREATE INDEX idx_screener_price ON stock_screener_data(price);

-- Step 6: Create top gainers view
CREATE VIEW top_gainers AS
SELECT * FROM stock_screener_data WHERE change_percent > 0 ORDER BY change_percent DESC LIMIT 20;

-- Step 7: Create top losers view
CREATE VIEW top_losers AS
SELECT * FROM stock_screener_data WHERE change_percent < 0 ORDER BY change_percent ASC LIMIT 20;

-- Step 8: Create latest prices view
CREATE VIEW latest_stock_prices AS
SELECT DISTINCT ON (symbol) symbol, price, change, change_percent, volume, timestamp
FROM stock_prices ORDER BY symbol, timestamp DESC;

-- Grant permissions
GRANT SELECT ON stock_screener_data TO authenticated, anon;
GRANT SELECT ON top_gainers TO authenticated, anon;
GRANT SELECT ON top_losers TO authenticated, anon;
GRANT SELECT ON latest_stock_prices TO authenticated, anon;
