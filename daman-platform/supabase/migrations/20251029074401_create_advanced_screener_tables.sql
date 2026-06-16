/*
  # Advanced Stock Screener Tables
  
  1. New Tables
    - `screening_presets`
      - Predefined screening strategies (Growth, Value, Dividend, Momentum)
      - User custom presets
    - `screening_results`
      - Cached screening results for performance
    - `technical_indicators_cache`
      - Cached technical indicator calculations
      
  2. Security
    - Enable RLS on all tables
    - Public read for preset strategies
    - Users can create/manage own presets
*/

-- Screening presets table (predefined + user custom)
CREATE TABLE IF NOT EXISTS screening_presets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES user_profiles(id),
  name text NOT NULL,
  description text DEFAULT '',
  category text NOT NULL, -- 'growth', 'value', 'dividend', 'momentum', 'custom'
  criteria jsonb NOT NULL,
  is_public boolean DEFAULT false,
  usage_count integer DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_screening_presets_category ON screening_presets(category);
CREATE INDEX IF NOT EXISTS idx_screening_presets_user ON screening_presets(user_id);
CREATE INDEX IF NOT EXISTS idx_screening_presets_public ON screening_presets(is_public) WHERE is_public = true;

ALTER TABLE screening_presets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public presets are readable by everyone"
  ON screening_presets FOR SELECT
  TO anon, authenticated
  USING (is_public = true OR user_id IS NULL);

CREATE POLICY "Users can create their own presets"
  ON screening_presets FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own presets"
  ON screening_presets FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own presets"
  ON screening_presets FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- Technical indicators cache table
CREATE TABLE IF NOT EXISTS technical_indicators_cache (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  indicator_type text NOT NULL, -- 'rsi', 'macd', 'sma', 'ema', 'bb'
  timeframe text NOT NULL, -- '1d', '1w', '1m'
  indicator_data jsonb NOT NULL,
  calculated_at timestamptz DEFAULT now(),
  expires_at timestamptz NOT NULL,
  UNIQUE(symbol, indicator_type, timeframe)
);

CREATE INDEX IF NOT EXISTS idx_tech_indicators_symbol ON technical_indicators_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_tech_indicators_expires ON technical_indicators_cache(expires_at);

ALTER TABLE technical_indicators_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Technical indicators are publicly readable"
  ON technical_indicators_cache FOR SELECT
  TO anon, authenticated
  USING (expires_at > now());

CREATE POLICY "Authenticated users can insert indicators"
  ON technical_indicators_cache FOR INSERT
  TO authenticated
  WITH CHECK (true);

-- Screening results cache
CREATE TABLE IF NOT EXISTS screening_results_cache (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  preset_id uuid REFERENCES screening_presets(id),
  criteria_hash text NOT NULL,
  results jsonb NOT NULL,
  result_count integer NOT NULL,
  cached_at timestamptz DEFAULT now(),
  expires_at timestamptz NOT NULL,
  UNIQUE(criteria_hash)
);

CREATE INDEX IF NOT EXISTS idx_screening_cache_hash ON screening_results_cache(criteria_hash);
CREATE INDEX IF NOT EXISTS idx_screening_cache_expires ON screening_results_cache(expires_at);

ALTER TABLE screening_results_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Screening results are publicly readable"
  ON screening_results_cache FOR SELECT
  TO anon, authenticated
  USING (expires_at > now());

-- Insert predefined screening presets
INSERT INTO screening_presets (name, description, category, criteria, is_public, user_id) VALUES
(
  'Growth Stocks',
  'High revenue growth companies with strong momentum',
  'growth',
  '{
    "revenue_growth_yoy": {"min": 20, "max": null},
    "eps_growth_yoy": {"min": 15, "max": null},
    "price_change_52w": {"min": 10, "max": null},
    "market_cap": {"min": 1000000000, "max": null},
    "rsi": {"min": 50, "max": 70},
    "volume": {"min": 1000000, "max": null}
  }'::jsonb,
  true,
  NULL
),
(
  'Value Stocks',
  'Undervalued companies with strong fundamentals',
  'value',
  '{
    "pe_ratio": {"min": 5, "max": 15},
    "price_to_book": {"min": 0.5, "max": 2},
    "dividend_yield": {"min": 2, "max": null},
    "debt_to_equity": {"min": null, "max": 1},
    "current_ratio": {"min": 1.5, "max": null}
  }'::jsonb,
  true,
  NULL
),
(
  'Dividend Aristocrats',
  'Consistent dividend payers with increasing payouts',
  'dividend',
  '{
    "dividend_yield": {"min": 3, "max": null},
    "dividend_growth_5y": {"min": 5, "max": null},
    "payout_ratio": {"min": null, "max": 60},
    "consecutive_years": {"min": 10, "max": null},
    "market_cap": {"min": 5000000000, "max": null}
  }'::jsonb,
  true,
  NULL
),
(
  'Momentum Leaders',
  'Strong price momentum with technical confirmation',
  'momentum',
  '{
    "price_change_1m": {"min": 5, "max": null},
    "price_change_3m": {"min": 10, "max": null},
    "rsi": {"min": 60, "max": 80},
    "macd_signal": "positive_crossover",
    "volume_20d_avg": {"min": 2000000, "max": null},
    "above_sma_50": true,
    "above_sma_200": true
  }'::jsonb,
  true,
  NULL
),
(
  'Quality Large Caps',
  'High quality large cap companies with stable performance',
  'growth',
  '{
    "market_cap": {"min": 50000000000, "max": null},
    "roe": {"min": 15, "max": null},
    "profit_margin": {"min": 15, "max": null},
    "debt_to_equity": {"min": null, "max": 0.5},
    "beta": {"min": 0.5, "max": 1.2},
    "pe_ratio": {"min": 10, "max": 30}
  }'::jsonb,
  true,
  NULL
),
(
  'Breakout Candidates',
  'Stocks approaching 52-week highs with strong volume',
  'momentum',
  '{
    "price_vs_52w_high": {"min": 95, "max": 100},
    "volume_vs_avg": {"min": 150, "max": null},
    "rsi": {"min": 55, "max": 75},
    "price_change_1w": {"min": 3, "max": null},
    "above_sma_20": true,
    "above_sma_50": true
  }'::jsonb,
  true,
  NULL
),
(
  'Oversold Opportunities',
  'Fundamentally strong stocks that are temporarily oversold',
  'value',
  '{
    "rsi": {"min": 20, "max": 35},
    "price_vs_52w_high": {"min": null, "max": 70},
    "pe_ratio": {"min": 5, "max": 20},
    "debt_to_equity": {"min": null, "max": 1},
    "profit_margin": {"min": 10, "max": null},
    "analyst_rating": {"min": 3.5, "max": 5}
  }'::jsonb,
  true,
  NULL
),
(
  'Small Cap Growth',
  'High growth potential small cap companies',
  'growth',
  '{
    "market_cap": {"min": 300000000, "max": 2000000000},
    "revenue_growth_yoy": {"min": 25, "max": null},
    "eps_growth_yoy": {"min": 20, "max": null},
    "insider_buying": true,
    "institutional_ownership": {"min": 20, "max": 70}
  }'::jsonb,
  true,
  NULL
);

-- Create comprehensive screener view with all metrics
CREATE OR REPLACE VIEW comprehensive_screener_data AS
SELECT
  su.symbol,
  su.name,
  su.exchange,
  su.sector,
  su.industry,
  su.market_cap,
  su.is_sp500,
  su.is_nasdaq,
  
  -- Price data
  lsp.price as current_price,
  lsp.change,
  lsp.change_percent,
  lsp.volume,
  lsp.open,
  lsp.high,
  lsp.low,
  
  -- Fundamental data
  sf.pe_ratio,
  sf.peg_ratio,
  sf.price_to_book,
  sf.price_to_sales,
  sf.dividend_yield,
  sf.eps,
  sf.beta,
  sf.shares_outstanding,
  sf.float_shares,
  sf.fifty_two_week_high,
  sf.fifty_two_week_low,
  sf.avg_volume,
  sf.short_interest,
  sf.short_ratio,
  
  -- Technical indicators (from latest calculation)
  st.rsi_14,
  st.macd,
  st.macd_signal,
  st.macd_histogram,
  st.sma_20,
  st.sma_50,
  st.sma_200,
  st.ema_12,
  st.ema_26,
  st.bb_upper,
  st.bb_middle,
  st.bb_lower,
  st.signal as technical_signal,
  
  -- Calculated fields
  CASE 
    WHEN sf.fifty_two_week_high > 0 THEN 
      ((lsp.price - sf.fifty_two_week_low) / (sf.fifty_two_week_high - sf.fifty_two_week_low)) * 100
    ELSE 0
  END as price_range_percent,
  
  CASE 
    WHEN sf.fifty_two_week_high > 0 THEN 
      (lsp.price / sf.fifty_two_week_high) * 100
    ELSE 0
  END as price_vs_52w_high,
  
  CASE 
    WHEN st.sma_20 > 0 THEN lsp.price > st.sma_20
    ELSE false
  END as above_sma_20,
  
  CASE 
    WHEN st.sma_50 > 0 THEN lsp.price > st.sma_50
    ELSE false
  END as above_sma_50,
  
  CASE 
    WHEN st.sma_200 > 0 THEN lsp.price > st.sma_200
    ELSE false
  END as above_sma_200,
  
  -- Volume analysis
  CASE 
    WHEN sf.avg_volume > 0 THEN (lsp.volume::float / sf.avg_volume::float) * 100
    ELSE 0
  END as volume_vs_avg_percent,
  
  -- Dividend status
  (SELECT COUNT(*) > 0 FROM dividend_history WHERE symbol = su.symbol) as has_dividends,
  
  -- Last update
  lsp.timestamp as last_updated
  
FROM stock_universe su
LEFT JOIN latest_stock_prices lsp ON su.symbol = lsp.symbol
LEFT JOIN stock_fundamentals sf ON su.symbol = sf.symbol
LEFT JOIN (
  SELECT DISTINCT ON (symbol)
    symbol, rsi_14, macd, macd_signal, macd_histogram,
    sma_20, sma_50, sma_200, ema_12, ema_26,
    bb_upper, bb_middle, bb_lower, signal, timestamp
  FROM stock_technicals
  ORDER BY symbol, timestamp DESC
) st ON su.symbol = st.symbol;

GRANT SELECT ON comprehensive_screener_data TO anon, authenticated;

-- Function to clean expired cache entries
CREATE OR REPLACE FUNCTION clean_expired_cache()
RETURNS void AS $$
BEGIN
  DELETE FROM technical_indicators_cache WHERE expires_at < now();
  DELETE FROM screening_results_cache WHERE expires_at < now();
END;
$$ LANGUAGE plpgsql;

-- Create indexes for screener performance
CREATE INDEX IF NOT EXISTS idx_stock_fundamentals_pe ON stock_fundamentals(pe_ratio) WHERE pe_ratio > 0;
CREATE INDEX IF NOT EXISTS idx_stock_fundamentals_dividend ON stock_fundamentals(dividend_yield) WHERE dividend_yield > 0;
CREATE INDEX IF NOT EXISTS idx_stock_fundamentals_market_cap ON stock_fundamentals(market_cap);
CREATE INDEX IF NOT EXISTS idx_stock_technicals_rsi ON stock_technicals(rsi_14);
CREATE INDEX IF NOT EXISTS idx_stock_technicals_signal ON stock_technicals(signal);