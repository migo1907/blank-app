-- Add comprehensive stock data fields for deep market analysis
-- Extends existing stock tables with detailed financial information

-- Add detailed fields to stock_fundamentals table
ALTER TABLE stock_fundamentals ADD COLUMN IF NOT EXISTS shares_outstanding bigint DEFAULT 0;
ALTER TABLE stock_fundamentals ADD COLUMN IF NOT EXISTS float_shares bigint DEFAULT 0;
ALTER TABLE stock_fundamentals ADD COLUMN IF NOT EXISTS description text DEFAULT '';
ALTER TABLE stock_fundamentals ADD COLUMN IF NOT EXISTS headquarters text DEFAULT '';
ALTER TABLE stock_fundamentals ADD COLUMN IF NOT EXISTS employees integer DEFAULT 0;
ALTER TABLE stock_fundamentals ADD COLUMN IF NOT EXISTS website text DEFAULT '';
ALTER TABLE stock_fundamentals ADD COLUMN IF NOT EXISTS ceo text DEFAULT '';

-- Create dividend history table
CREATE TABLE IF NOT EXISTS dividend_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  ex_date date NOT NULL,
  payment_date date,
  amount numeric NOT NULL,
  frequency text DEFAULT 'quarterly',
  created_at timestamptz DEFAULT now(),
  UNIQUE(symbol, ex_date)
);

CREATE INDEX IF NOT EXISTS idx_dividend_history_symbol ON dividend_history(symbol);
CREATE INDEX IF NOT EXISTS idx_dividend_history_ex_date ON dividend_history(ex_date DESC);

ALTER TABLE dividend_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Dividend history is publicly readable"
  ON dividend_history FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Authenticated users can insert dividend history"
  ON dividend_history FOR INSERT
  TO authenticated
  WITH CHECK (true);

-- Create company profiles table for detailed information
CREATE TABLE IF NOT EXISTS company_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text UNIQUE NOT NULL,
  company_name text NOT NULL,
  description text DEFAULT '',
  industry text DEFAULT '',
  sector text DEFAULT '',
  website text DEFAULT '',
  headquarters text DEFAULT '',
  ceo text DEFAULT '',
  employees integer DEFAULT 0,
  founded_year integer,
  business_summary text DEFAULT '',
  key_executives jsonb DEFAULT '[]'::jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_company_profiles_symbol ON company_profiles(symbol);
CREATE INDEX IF NOT EXISTS idx_company_profiles_sector ON company_profiles(sector);
CREATE INDEX IF NOT EXISTS idx_company_profiles_industry ON company_profiles(industry);

ALTER TABLE company_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Company profiles are publicly readable"
  ON company_profiles FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Authenticated users can manage company profiles"
  ON company_profiles FOR ALL
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- Create comprehensive stock detail view
CREATE OR REPLACE VIEW stock_detail_view AS
SELECT
  su.symbol,
  su.name,
  su.exchange,
  su.sector,
  su.industry,
  su.market_cap,
  cp.description,
  cp.website,
  cp.headquarters,
  cp.ceo,
  cp.employees,
  cp.founded_year,
  cp.business_summary,
  sf.pe_ratio,
  sf.peg_ratio,
  sf.price_to_book,
  sf.dividend_yield,
  sf.eps,
  sf.beta,
  sf.shares_outstanding,
  sf.float_shares,
  sf.fifty_two_week_high,
  sf.fifty_two_week_low,
  sf.short_interest,
  sf.avg_volume,
  (SELECT price FROM stock_prices WHERE symbol = su.symbol ORDER BY timestamp DESC LIMIT 1) as current_price,
  (SELECT change_percent FROM stock_prices WHERE symbol = su.symbol ORDER BY timestamp DESC LIMIT 1) as change_percent,
  (SELECT COUNT(*) > 0 FROM dividend_history WHERE symbol = su.symbol) as has_dividends,
  (SELECT amount FROM dividend_history WHERE symbol = su.symbol ORDER BY ex_date DESC LIMIT 1) as last_dividend_amount,
  (SELECT ex_date FROM dividend_history WHERE symbol = su.symbol ORDER BY ex_date DESC LIMIT 1) as last_dividend_date
FROM stock_universe su
LEFT JOIN company_profiles cp ON su.symbol = cp.symbol
LEFT JOIN stock_fundamentals sf ON su.symbol = sf.symbol;

GRANT SELECT ON stock_detail_view TO anon, authenticated;

-- Create search results view with comprehensive data
CREATE OR REPLACE VIEW stock_search_results AS
SELECT
  su.symbol,
  su.name,
  su.exchange,
  su.sector,
  su.industry,
  su.market_cap,
  COALESCE((SELECT price FROM stock_prices WHERE symbol = su.symbol ORDER BY timestamp DESC LIMIT 1), 0) as price,
  COALESCE((SELECT change_percent FROM stock_prices WHERE symbol = su.symbol ORDER BY timestamp DESC LIMIT 1), 0) as change_percent,
  COALESCE((SELECT volume FROM stock_prices WHERE symbol = su.symbol ORDER BY timestamp DESC LIMIT 1), 0) as volume,
  COALESCE(sf.dividend_yield, 0) as dividend_yield,
  COALESCE(sf.pe_ratio, 0) as pe_ratio,
  CASE WHEN EXISTS (SELECT 1 FROM dividend_history WHERE symbol = su.symbol) THEN true ELSE false END as has_dividends
FROM stock_universe su
LEFT JOIN stock_fundamentals sf ON su.symbol = sf.symbol;

GRANT SELECT ON stock_search_results TO anon, authenticated;