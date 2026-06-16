/*
  # Create IBKR Real-Time Options Data Table

  1. New Tables
    - `ibkr_options_realtime`
      - `id` (uuid, primary key) - Unique identifier
      - `symbol` (text) - Underlying stock symbol
      - `expiration` (date) - Options expiration date
      - `strike` (numeric) - Strike price
      - `option_type` (text) - Option type (CALL/PUT)
      - `bid` (numeric) - Current bid price
      - `ask` (numeric) - Current ask price
      - `last` (numeric) - Last traded price
      - `mid` (numeric) - Mid price (bid+ask)/2
      - `volume` (numeric) - Trading volume
      - `open_interest` (numeric) - Open interest
      - `implied_volatility` (numeric) - Implied volatility
      - `delta` (numeric) - Option delta
      - `gamma` (numeric) - Option gamma
      - `theta` (numeric) - Option theta
      - `vega` (numeric) - Option vega
      - `underlying_price` (numeric) - Current underlying stock price
      - `timestamp` (timestamptz) - Data timestamp
      - `created_at` (timestamptz) - Record creation timestamp
      - `updated_at` (timestamptz) - Last update timestamp

  2. Security
    - Enable RLS on `ibkr_options_realtime` table
    - Add policy for public read access (market data is informational)
    - Add policy for service role write access (only backend can write)

  3. Indexes
    - Index on symbol for fast lookups
    - Index on expiration for filtering by date
    - Composite index on (symbol, expiration, strike, option_type) for unique constraint
    - Index on timestamp for time-series queries

  4. Important Notes
    - Data is updated in real-time from IBKR
    - Uses upsert pattern to update existing records
    - Automatically tracks last update time
*/

CREATE TABLE IF NOT EXISTS ibkr_options_realtime (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  expiration date NOT NULL,
  strike numeric NOT NULL,
  option_type text NOT NULL CHECK (option_type IN ('CALL', 'PUT', 'C', 'P')),
  bid numeric DEFAULT 0,
  ask numeric DEFAULT 0,
  last numeric DEFAULT 0,
  mid numeric DEFAULT 0,
  volume numeric DEFAULT 0,
  open_interest numeric DEFAULT 0,
  implied_volatility numeric DEFAULT 0,
  delta numeric,
  gamma numeric,
  theta numeric,
  vega numeric,
  underlying_price numeric DEFAULT 0,
  timestamp timestamptz DEFAULT now(),
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

ALTER TABLE ibkr_options_realtime ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read IBKR options data"
  ON ibkr_options_realtime
  FOR SELECT
  TO public
  USING (true);

CREATE POLICY "Service role can insert IBKR options data"
  ON ibkr_options_realtime
  FOR INSERT
  TO service_role
  WITH CHECK (true);

CREATE POLICY "Service role can update IBKR options data"
  ON ibkr_options_realtime
  FOR UPDATE
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Service role can delete IBKR options data"
  ON ibkr_options_realtime
  FOR DELETE
  TO service_role
  USING (true);

CREATE INDEX IF NOT EXISTS idx_ibkr_options_symbol ON ibkr_options_realtime(symbol);
CREATE INDEX IF NOT EXISTS idx_ibkr_options_expiration ON ibkr_options_realtime(expiration);
CREATE INDEX IF NOT EXISTS idx_ibkr_options_timestamp ON ibkr_options_realtime(timestamp DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ibkr_options_unique_contract 
  ON ibkr_options_realtime(symbol, expiration, strike, option_type);

CREATE OR REPLACE FUNCTION update_ibkr_options_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'update_ibkr_options_realtime_updated_at'
  ) THEN
    CREATE TRIGGER update_ibkr_options_realtime_updated_at
      BEFORE UPDATE ON ibkr_options_realtime
      FOR EACH ROW
      EXECUTE FUNCTION update_ibkr_options_updated_at();
  END IF;
END $$;
