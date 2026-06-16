-- Advanced Market Screener Database Schema
-- Creates comprehensive structure for market screener with user features

-- User Profiles Table
CREATE TABLE IF NOT EXISTS user_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL,
  full_name text DEFAULT '',
  avatar_url text DEFAULT '',
  theme_preference text DEFAULT 'light',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own profile"
  ON user_profiles FOR SELECT
  TO authenticated
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
  ON user_profiles FOR UPDATE
  TO authenticated
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can insert own profile"
  ON user_profiles FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = id);

-- Watchlists Table
CREATE TABLE IF NOT EXISTS watchlists (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES user_profiles(id) ON DELETE CASCADE,
  name text NOT NULL,
  description text DEFAULT '',
  is_default boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

ALTER TABLE watchlists ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own watchlists"
  ON watchlists FOR ALL
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Watchlist Items Table
CREATE TABLE IF NOT EXISTS watchlist_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  watchlist_id uuid REFERENCES watchlists(id) ON DELETE CASCADE,
  symbol text NOT NULL,
  added_at timestamptz DEFAULT now(),
  notes text DEFAULT ''
);

ALTER TABLE watchlist_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own watchlist items"
  ON watchlist_items FOR ALL
  TO authenticated
  USING (
    watchlist_id IN (
      SELECT id FROM watchlists WHERE user_id = auth.uid()
    )
  )
  WITH CHECK (
    watchlist_id IN (
      SELECT id FROM watchlists WHERE user_id = auth.uid()
    )
  );

-- Screener Presets Table
CREATE TABLE IF NOT EXISTS screener_presets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES user_profiles(id) ON DELETE CASCADE,
  name text NOT NULL,
  description text DEFAULT '',
  filters jsonb DEFAULT '{}'::jsonb,
  is_public boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

ALTER TABLE screener_presets ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own and public presets"
  ON screener_presets FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id OR is_public = true);

CREATE POLICY "Users can manage own presets"
  ON screener_presets FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own presets"
  ON screener_presets FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own presets"
  ON screener_presets FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- Price Alerts Table
CREATE TABLE IF NOT EXISTS price_alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES user_profiles(id) ON DELETE CASCADE,
  symbol text NOT NULL,
  alert_type text NOT NULL,
  target_value numeric NOT NULL,
  is_active boolean DEFAULT true,
  triggered_at timestamptz,
  created_at timestamptz DEFAULT now()
);

ALTER TABLE price_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own alerts"
  ON price_alerts FOR ALL
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Portfolios Table
CREATE TABLE IF NOT EXISTS portfolios (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES user_profiles(id) ON DELETE CASCADE,
  name text NOT NULL,
  description text DEFAULT '',
  initial_value numeric DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own portfolios"
  ON portfolios FOR ALL
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- Portfolio Positions Table
CREATE TABLE IF NOT EXISTS portfolio_positions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  portfolio_id uuid REFERENCES portfolios(id) ON DELETE CASCADE,
  symbol text NOT NULL,
  shares numeric NOT NULL,
  average_cost numeric NOT NULL,
  purchase_date timestamptz DEFAULT now(),
  notes text DEFAULT '',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

ALTER TABLE portfolio_positions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own portfolio positions"
  ON portfolio_positions FOR ALL
  TO authenticated
  USING (
    portfolio_id IN (
      SELECT id FROM portfolios WHERE user_id = auth.uid()
    )
  )
  WITH CHECK (
    portfolio_id IN (
      SELECT id FROM portfolios WHERE user_id = auth.uid()
    )
  );

-- Stock Technicals Table
CREATE TABLE IF NOT EXISTS stock_technicals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  rsi_14 numeric DEFAULT 0,
  macd numeric DEFAULT 0,
  macd_signal numeric DEFAULT 0,
  macd_histogram numeric DEFAULT 0,
  sma_20 numeric DEFAULT 0,
  sma_50 numeric DEFAULT 0,
  sma_200 numeric DEFAULT 0,
  ema_12 numeric DEFAULT 0,
  ema_26 numeric DEFAULT 0,
  bb_upper numeric DEFAULT 0,
  bb_middle numeric DEFAULT 0,
  bb_lower numeric DEFAULT 0,
  signal text DEFAULT 'neutral',
  timestamp timestamptz DEFAULT now(),
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stock_technicals_symbol ON stock_technicals(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_technicals_timestamp ON stock_technicals(timestamp);

ALTER TABLE stock_technicals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Stock technicals are publicly readable"
  ON stock_technicals FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Authenticated users can insert stock technicals"
  ON stock_technicals FOR INSERT
  TO authenticated
  WITH CHECK (true);

-- Stock Fundamentals Table
CREATE TABLE IF NOT EXISTS stock_fundamentals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text UNIQUE NOT NULL,
  pe_ratio numeric DEFAULT 0,
  peg_ratio numeric DEFAULT 0,
  price_to_book numeric DEFAULT 0,
  price_to_sales numeric DEFAULT 0,
  dividend_yield numeric DEFAULT 0,
  eps numeric DEFAULT 0,
  market_cap bigint DEFAULT 0,
  shares_outstanding bigint DEFAULT 0,
  short_interest numeric DEFAULT 0,
  short_ratio numeric DEFAULT 0,
  beta numeric DEFAULT 0,
  fifty_two_week_high numeric DEFAULT 0,
  fifty_two_week_low numeric DEFAULT 0,
  avg_volume bigint DEFAULT 0,
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stock_fundamentals_symbol ON stock_fundamentals(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_fundamentals_market_cap ON stock_fundamentals(market_cap);

ALTER TABLE stock_fundamentals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Stock fundamentals are publicly readable"
  ON stock_fundamentals FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Authenticated users can upsert stock fundamentals"
  ON stock_fundamentals FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated users can update stock fundamentals"
  ON stock_fundamentals FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- Create view for latest technicals per symbol
CREATE OR REPLACE VIEW latest_stock_technicals AS
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

-- Create comprehensive stock screener view
CREATE OR REPLACE VIEW stock_screener_data AS
SELECT 
  su.symbol,
  su.name,
  su.exchange,
  su.sector,
  su.industry,
  sp.price,
  sp.change,
  sp.change_percent,
  sp.volume,
  sf.pe_ratio,
  sf.market_cap,
  sf.dividend_yield,
  sf.beta,
  sf.short_interest,
  sf.fifty_two_week_high,
  sf.fifty_two_week_low,
  st.rsi_14,
  st.macd,
  st.sma_20,
  st.sma_50,
  st.sma_200,
  st.signal,
  sp.timestamp as price_updated,
  sf.updated_at as fundamentals_updated,
  st.timestamp as technicals_updated
FROM stock_universe su
LEFT JOIN LATERAL (
  SELECT * FROM stock_prices
  WHERE symbol = su.symbol
  ORDER BY timestamp DESC
  LIMIT 1
) sp ON true
LEFT JOIN stock_fundamentals sf ON su.symbol = sf.symbol
LEFT JOIN latest_stock_technicals st ON su.symbol = st.symbol;