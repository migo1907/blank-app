/*
  # Create Stock Market Data Tables

  ## Overview
  This migration creates comprehensive tables for storing real-time stock market data,
  including S&P 500 and NASDAQ listings with real-time price updates.

  ## 1. New Tables
    
    ### `stock_universe`
    Master list of all tracked stocks
    - `id` (uuid, primary key) - Unique identifier
    - `symbol` (text, required, unique) - Stock ticker symbol (e.g., AAPL)
    - `name` (text, required) - Company name
    - `exchange` (text, required) - Exchange (NYSE, NASDAQ)
    - `sector` (text) - Business sector
    - `industry` (text) - Specific industry
    - `is_sp500` (boolean, default false) - S&P 500 constituent
    - `is_nasdaq` (boolean, default false) - NASDAQ listed
    - `market_cap` (bigint) - Market capitalization
    - `created_at` (timestamptz) - Record creation time
    - `updated_at` (timestamptz) - Last update time
    
    ### `stock_prices`
    Real-time and historical price data
    - `id` (uuid, primary key) - Unique identifier
    - `symbol` (text, required) - Stock ticker symbol
    - `price` (numeric, required) - Current/historical price
    - `open` (numeric) - Opening price
    - `high` (numeric) - Day high
    - `low` (numeric) - Day low
    - `close` (numeric) - Closing price
    - `volume` (bigint) - Trading volume
    - `change` (numeric) - Price change ($)
    - `change_percent` (numeric) - Percentage change
    - `timestamp` (timestamptz, required) - Price timestamp
    - `created_at` (timestamptz) - Record creation time

  ## 2. Indexes
    - Index on `symbol` for fast lookups
    - Index on `timestamp` for time-series queries
    - Composite index on `symbol` and `timestamp`
    - Index on `is_sp500` and `is_nasdaq` for filtering
    - Index on `change_percent` for screener queries

  ## 3. Security
    - Enable Row Level Security (RLS) on both tables
    - Add policy for public read access (market data is public)
    - Add policy for authenticated users to insert/update (for API sync)

  ## 4. Important Notes
    - Prices are stored with high precision (numeric type)
    - Volume stored as bigint for large numbers
    - Timestamp includes timezone for accuracy
    - Indexes optimized for screener queries
*/

-- Create stock_universe table
CREATE TABLE IF NOT EXISTS stock_universe (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL UNIQUE,
  name text NOT NULL,
  exchange text NOT NULL,
  sector text DEFAULT '',
  industry text DEFAULT '',
  is_sp500 boolean DEFAULT false,
  is_nasdaq boolean DEFAULT false,
  market_cap bigint DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Create stock_prices table
CREATE TABLE IF NOT EXISTS stock_prices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  price numeric(12, 4) NOT NULL,
  open numeric(12, 4) DEFAULT 0,
  high numeric(12, 4) DEFAULT 0,
  low numeric(12, 4) DEFAULT 0,
  close numeric(12, 4) DEFAULT 0,
  volume bigint DEFAULT 0,
  change numeric(12, 4) DEFAULT 0,
  change_percent numeric(8, 4) DEFAULT 0,
  timestamp timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz DEFAULT now()
);

-- Create indexes for stock_universe
CREATE INDEX IF NOT EXISTS idx_stock_universe_symbol ON stock_universe(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_universe_sp500 ON stock_universe(is_sp500) WHERE is_sp500 = true;
CREATE INDEX IF NOT EXISTS idx_stock_universe_nasdaq ON stock_universe(is_nasdaq) WHERE is_nasdaq = true;
CREATE INDEX IF NOT EXISTS idx_stock_universe_exchange ON stock_universe(exchange);

-- Create indexes for stock_prices
CREATE INDEX IF NOT EXISTS idx_stock_prices_symbol ON stock_prices(symbol);
CREATE INDEX IF NOT EXISTS idx_stock_prices_timestamp ON stock_prices(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_stock_prices_symbol_timestamp ON stock_prices(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_stock_prices_change_percent ON stock_prices(change_percent DESC);

-- Enable Row Level Security
ALTER TABLE stock_universe ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock_prices ENABLE ROW LEVEL SECURITY;

-- Policies for stock_universe
CREATE POLICY "Stock universe is publicly readable"
  ON stock_universe
  FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Authenticated users can insert stock universe"
  ON stock_universe
  FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated users can update stock universe"
  ON stock_universe
  FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- Policies for stock_prices
CREATE POLICY "Stock prices are publicly readable"
  ON stock_prices
  FOR SELECT
  TO anon, authenticated
  USING (true);

CREATE POLICY "Authenticated users can insert stock prices"
  ON stock_prices
  FOR INSERT
  TO authenticated
  WITH CHECK (true);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_stock_universe_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for stock_universe
CREATE TRIGGER update_stock_universe_updated_at_trigger
  BEFORE UPDATE ON stock_universe
  FOR EACH ROW
  EXECUTE FUNCTION update_stock_universe_updated_at();

-- Create view for latest stock prices
CREATE OR REPLACE VIEW latest_stock_prices AS
SELECT DISTINCT ON (symbol)
  symbol,
  price,
  open,
  high,
  low,
  close,
  volume,
  change,
  change_percent,
  timestamp
FROM stock_prices
ORDER BY symbol, timestamp DESC;

-- Create view for top gainers
CREATE OR REPLACE VIEW top_gainers AS
SELECT 
  sp.symbol,
  su.name,
  sp.price,
  sp.change,
  sp.change_percent,
  sp.volume,
  su.exchange,
  su.sector
FROM latest_stock_prices sp
JOIN stock_universe su ON sp.symbol = su.symbol
WHERE sp.change_percent > 0
ORDER BY sp.change_percent DESC
LIMIT 100;

-- Create view for top losers
CREATE OR REPLACE VIEW top_losers AS
SELECT 
  sp.symbol,
  su.name,
  sp.price,
  sp.change,
  sp.change_percent,
  sp.volume,
  su.exchange,
  su.sector
FROM latest_stock_prices sp
JOIN stock_universe su ON sp.symbol = su.symbol
WHERE sp.change_percent < 0
ORDER BY sp.change_percent ASC
LIMIT 100;
