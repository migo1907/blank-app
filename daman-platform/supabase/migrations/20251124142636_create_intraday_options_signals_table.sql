/*
  # Create Intraday Options Signals Table

  1. New Tables
    - `intraday_options_signals`
      - `id` (uuid, primary key) - Unique identifier
      - `timestamp` (timestamptz) - Signal generation timestamp
      - `ticker` (text) - Stock ticker symbol
      - `side` (text) - Trade direction (LONG/SHORT)
      - `options_strike` (numeric) - Options strike price
      - `expiry_date` (date) - Options expiration date
      - `delta` (numeric) - Options delta value
      - `option_entry` (numeric) - Options entry price
      - `option_stop` (numeric) - Options stop loss price
      - `option_target` (numeric) - Options target price
      - `option_rr` (numeric) - Options risk/reward ratio
      - `stock_entry` (numeric) - Underlying stock entry price
      - `stock_stop` (numeric) - Underlying stock stop price
      - `stock_target` (numeric) - Underlying stock target price
      - `stock_rr` (numeric) - Stock risk/reward ratio
      - `atr` (numeric) - Average True Range
      - `rsi` (numeric) - Relative Strength Index
      - `macd_hist` (numeric) - MACD histogram value
      - `vwap` (numeric) - Volume Weighted Average Price
      - `signal_time` (text) - Dubai time when signal was triggered
      - `created_at` (timestamptz) - Record creation timestamp

  2. Security
    - Enable RLS on `intraday_options_signals` table
    - Add policy for public read access (signals are informational)
    - Add policy for authenticated insert access
    - Add policy for authenticated update/delete access

  3. Indexes
    - Index on ticker for fast lookups
    - Index on timestamp for chronological queries
    - Index on side for filtering by trade direction
    - Composite index on (ticker, timestamp) for optimal performance
*/

CREATE TABLE IF NOT EXISTS intraday_options_signals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp timestamptz NOT NULL DEFAULT now(),
  ticker text NOT NULL,
  side text NOT NULL CHECK (side IN ('LONG', 'SHORT')),
  options_strike numeric NOT NULL,
  expiry_date date NOT NULL,
  delta numeric NOT NULL,
  option_entry numeric NOT NULL,
  option_stop numeric NOT NULL,
  option_target numeric NOT NULL,
  option_rr numeric NOT NULL,
  stock_entry numeric NOT NULL,
  stock_stop numeric NOT NULL,
  stock_target numeric NOT NULL,
  stock_rr numeric NOT NULL,
  atr numeric NOT NULL DEFAULT 0,
  rsi numeric NOT NULL DEFAULT 50,
  macd_hist numeric NOT NULL DEFAULT 0,
  vwap numeric NOT NULL DEFAULT 0,
  signal_time text NOT NULL,
  created_at timestamptz DEFAULT now()
);

ALTER TABLE intraday_options_signals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read intraday options signals"
  ON intraday_options_signals
  FOR SELECT
  TO public
  USING (true);

CREATE POLICY "Authenticated users can insert signals"
  ON intraday_options_signals
  FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Authenticated users can update own signals"
  ON intraday_options_signals
  FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Authenticated users can delete signals"
  ON intraday_options_signals
  FOR DELETE
  TO authenticated
  USING (true);

CREATE INDEX IF NOT EXISTS idx_intraday_options_ticker ON intraday_options_signals(ticker);
CREATE INDEX IF NOT EXISTS idx_intraday_options_timestamp ON intraday_options_signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_intraday_options_side ON intraday_options_signals(side);
CREATE INDEX IF NOT EXISTS idx_intraday_options_ticker_timestamp ON intraday_options_signals(ticker, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_intraday_options_signal_time ON intraday_options_signals(signal_time DESC);
