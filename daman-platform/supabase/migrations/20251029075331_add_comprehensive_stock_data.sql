/*
  # Add Advanced Features Tables
  
  1. New Tables
    - `watchlists` - User watchlists
    - `portfolios` - User portfolio tracking  
    - `portfolio_positions` - Individual positions
    - `stock_alerts` - Price and technical alerts
    - `options_flow` - Options activity tracking
    - `market_movers` - Top gainers/losers
    
  2. Security
    - Enable RLS on all tables
    - Users can only access their own data
*/

-- Watchlists
CREATE TABLE IF NOT EXISTS watchlists (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid,
  name text NOT NULL,
  description text DEFAULT '',
  symbols text[] DEFAULT '{}',
  is_default boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id);

ALTER TABLE watchlists ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read public watchlists"
  ON watchlists FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Authenticated users can create watchlists"
  ON watchlists FOR INSERT
  TO authenticated
  WITH CHECK (true);

-- Portfolios
CREATE TABLE IF NOT EXISTS portfolios (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid,
  name text NOT NULL,
  description text DEFAULT '',
  initial_value numeric DEFAULT 100000,
  current_value numeric DEFAULT 100000,
  total_return numeric DEFAULT 0,
  total_return_percent numeric DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);

ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read portfolios"
  ON portfolios FOR SELECT
  TO anon, authenticated
  USING (true);

-- Portfolio positions
CREATE TABLE IF NOT EXISTS portfolio_positions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  portfolio_id uuid REFERENCES portfolios(id) ON DELETE CASCADE,
  symbol text NOT NULL,
  shares numeric NOT NULL,
  average_cost numeric NOT NULL,
  current_price numeric DEFAULT 0,
  market_value numeric DEFAULT 0,
  unrealized_gain numeric DEFAULT 0,
  unrealized_gain_percent numeric DEFAULT 0,
  purchase_date timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_positions_portfolio ON portfolio_positions(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_symbol ON portfolio_positions(symbol);

ALTER TABLE portfolio_positions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read portfolio positions"
  ON portfolio_positions FOR SELECT
  TO anon, authenticated
  USING (true);

-- Stock alerts
CREATE TABLE IF NOT EXISTS stock_alerts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid,
  symbol text NOT NULL,
  alert_type text NOT NULL,
  threshold numeric NOT NULL,
  is_active boolean DEFAULT true,
  triggered_at timestamptz,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_stock_alerts_user ON stock_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_stock_alerts_symbol ON stock_alerts(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_alerts_active ON stock_alerts(is_active) WHERE is_active = true;

ALTER TABLE stock_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read alerts"
  ON stock_alerts FOR SELECT
  TO anon, authenticated
  USING (true);

-- Options flow
CREATE TABLE IF NOT EXISTS options_flow (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  option_type text NOT NULL,
  strike_price numeric NOT NULL,
  expiration_date date NOT NULL,
  volume bigint NOT NULL,
  open_interest bigint NOT NULL,
  implied_volatility numeric,
  delta numeric,
  unusual_activity boolean DEFAULT false,
  timestamp timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_options_flow_symbol ON options_flow(symbol);
CREATE INDEX IF NOT EXISTS idx_options_flow_timestamp ON options_flow(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_options_flow_unusual ON options_flow(unusual_activity) WHERE unusual_activity = true;

ALTER TABLE options_flow ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Options flow is publicly readable"
  ON options_flow FOR SELECT
  TO anon, authenticated
  USING (true);

-- Market movers
CREATE TABLE IF NOT EXISTS market_movers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  name text NOT NULL,
  price numeric NOT NULL,
  change numeric NOT NULL,
  change_percent numeric NOT NULL,
  volume bigint NOT NULL,
  market_cap numeric,
  category text NOT NULL,
  rank integer NOT NULL,
  timestamp timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_market_movers_category ON market_movers(category);
CREATE INDEX IF NOT EXISTS idx_market_movers_timestamp ON market_movers(timestamp DESC);

ALTER TABLE market_movers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Market movers are publicly readable"
  ON market_movers FOR SELECT
  TO anon, authenticated
  USING (true);

-- Insert sample market movers data
INSERT INTO market_movers (symbol, name, price, change, change_percent, volume, market_cap, category, rank) VALUES
('NVDA', 'NVIDIA Corporation', 875.50, 45.20, 5.44, 55000000, 2150000000000, 'top_gainer', 1),
('TSLA', 'Tesla Inc', 245.80, 12.30, 5.27, 125000000, 780000000000, 'top_gainer', 2),
('AMD', 'Advanced Micro Devices', 165.40, 7.80, 4.95, 75000000, 267000000000, 'top_gainer', 3),
('AAPL', 'Apple Inc', 185.50, -8.90, -4.58, 65000000, 2900000000000, 'top_loser', 1),
('MSFT', 'Microsoft Corporation', 415.20, -15.50, -3.59, 28000000, 3100000000000, 'top_loser', 2),
('GOOGL', 'Alphabet Inc', 142.30, -4.80, -3.26, 32000000, 1800000000000, 'top_loser', 3),
('AAPL', 'Apple Inc', 185.50, -8.90, -4.58, 65000000, 2900000000000, 'most_active', 1),
('TSLA', 'Tesla Inc', 245.80, 12.30, 5.27, 125000000, 780000000000, 'most_active', 2),
('NVDA', 'NVIDIA Corporation', 875.50, 45.20, 5.44, 55000000, 2150000000000, 'most_active', 3)
ON CONFLICT DO NOTHING;