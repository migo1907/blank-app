/*
  # Create Fundamental Data Table

  1. New Tables
    - `fundamental_data`
      - `id` (uuid, primary key)
      - `symbol` (text, unique) - Stock ticker symbol
      - `market_cap` (numeric) - Market capitalization
      - `enterprise_value` (numeric) - Enterprise value
      - `revenue` (numeric) - Total revenue (TTM)
      - `total_debt` (numeric) - Total debt
      - `total_cash` (numeric) - Total cash and equivalents
      - `shares_outstanding` (numeric) - Number of shares outstanding
      - `pe_ratio` (numeric) - Price-to-earnings ratio
      - `pb_ratio` (numeric) - Price-to-book ratio
      - `ev_to_revenue` (numeric) - Enterprise value to revenue ratio
      - `ev_to_ebitda` (numeric) - Enterprise value to EBITDA ratio
      - `debt_to_equity` (numeric) - Debt to equity ratio
      - `current_ratio` (numeric) - Current ratio
      - `quick_ratio` (numeric) - Quick ratio
      - `return_on_equity` (numeric) - Return on equity (ROE)
      - `return_on_assets` (numeric) - Return on assets (ROA)
      - `profit_margin` (numeric) - Profit margin
      - `operating_margin` (numeric) - Operating margin
      - `revenue_growth` (numeric) - Revenue growth rate
      - `earnings_growth` (numeric) - Earnings growth rate
      - `book_value_per_share` (numeric) - Book value per share
      - `price_to_book` (numeric) - Price to book ratio
      - `forward_pe` (numeric) - Forward P/E ratio
      - `peg_ratio` (numeric) - PEG ratio
      - `dividend_yield` (numeric) - Dividend yield
      - `payout_ratio` (numeric) - Dividend payout ratio
      - `beta` (numeric) - Stock beta
      - `fifty_two_week_high` (numeric) - 52-week high price
      - `fifty_two_week_low` (numeric) - 52-week low price
      - `industry` (text) - Industry classification
      - `sector` (text) - Sector classification
      - `updated_at` (timestamptz) - Last update timestamp
      - `created_at` (timestamptz) - Record creation timestamp

  2. Security
    - Enable RLS on `fundamental_data` table
    - Add policy for anonymous users to read fundamental data (public data)
    - Add policy for service role to write fundamental data

  3. Indexes
    - Add index on symbol for fast lookups
    - Add index on updated_at for cache management
    - Add index on sector and industry for filtering

  4. Notes
    - Data is sourced from Yahoo Finance API via edge function
    - Data is cached and refreshed periodically
    - All numeric fields default to 0 to prevent null issues
    - Symbol is unique to prevent duplicate records
*/

-- Create fundamental_data table
CREATE TABLE IF NOT EXISTS fundamental_data (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text UNIQUE NOT NULL,
  market_cap numeric DEFAULT 0,
  enterprise_value numeric DEFAULT 0,
  revenue numeric DEFAULT 0,
  total_debt numeric DEFAULT 0,
  total_cash numeric DEFAULT 0,
  shares_outstanding numeric DEFAULT 0,
  pe_ratio numeric DEFAULT 0,
  pb_ratio numeric DEFAULT 0,
  ev_to_revenue numeric DEFAULT 0,
  ev_to_ebitda numeric DEFAULT 0,
  debt_to_equity numeric DEFAULT 0,
  current_ratio numeric DEFAULT 0,
  quick_ratio numeric DEFAULT 0,
  return_on_equity numeric DEFAULT 0,
  return_on_assets numeric DEFAULT 0,
  profit_margin numeric DEFAULT 0,
  operating_margin numeric DEFAULT 0,
  revenue_growth numeric DEFAULT 0,
  earnings_growth numeric DEFAULT 0,
  book_value_per_share numeric DEFAULT 0,
  price_to_book numeric DEFAULT 0,
  forward_pe numeric DEFAULT 0,
  peg_ratio numeric DEFAULT 0,
  dividend_yield numeric DEFAULT 0,
  payout_ratio numeric DEFAULT 0,
  beta numeric DEFAULT 0,
  fifty_two_week_high numeric DEFAULT 0,
  fifty_two_week_low numeric DEFAULT 0,
  industry text DEFAULT 'Unknown',
  sector text DEFAULT 'Unknown',
  updated_at timestamptz DEFAULT now(),
  created_at timestamptz DEFAULT now()
);

-- Enable RLS
ALTER TABLE fundamental_data ENABLE ROW LEVEL SECURITY;

-- Create RLS policies
CREATE POLICY "Allow anonymous read access to fundamental data"
  ON fundamental_data
  FOR SELECT
  TO anon
  USING (true);

CREATE POLICY "Allow authenticated read access to fundamental data"
  ON fundamental_data
  FOR SELECT
  TO authenticated
  USING (true);

-- No public insert/update/delete policies - only service role can modify

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_fundamental_data_symbol ON fundamental_data(symbol);
CREATE INDEX IF NOT EXISTS idx_fundamental_data_updated_at ON fundamental_data(updated_at);
CREATE INDEX IF NOT EXISTS idx_fundamental_data_sector ON fundamental_data(sector);
CREATE INDEX IF NOT EXISTS idx_fundamental_data_industry ON fundamental_data(industry);
CREATE INDEX IF NOT EXISTS idx_fundamental_data_ev_revenue ON fundamental_data(ev_to_revenue);

-- Add helpful comment
COMMENT ON TABLE fundamental_data IS 'Cached fundamental data from Yahoo Finance for stock analysis';
