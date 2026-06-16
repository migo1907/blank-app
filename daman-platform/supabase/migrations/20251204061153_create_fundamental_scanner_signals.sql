/*
  # Create Fundamental Scanner Signals Table

  1. New Tables
    - `fundamental_scanner_signals`
      - `id` (uuid, primary key)
      - `ticker` (text)
      - `price` (decimal)
      - `signal` (text)
      - `rsi` (decimal)
      - `valuation_model` (text)
      - `valuation_ratio` (decimal, nullable)
      - `target_price` (decimal, nullable)
      - `reasons` (text)
      - `score` (integer)
      - `created_at` (timestamptz)

  2. Security
    - Enable RLS on `fundamental_scanner_signals` table
    - Add policy for anonymous read access (scanner results are public)
    - Add policy for anonymous insert access (scanner can write signals)
*/

CREATE TABLE IF NOT EXISTS fundamental_scanner_signals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker text NOT NULL,
  price decimal NOT NULL,
  signal text NOT NULL,
  rsi decimal NOT NULL,
  valuation_model text NOT NULL,
  valuation_ratio decimal,
  target_price decimal,
  reasons text NOT NULL,
  score integer NOT NULL,
  created_at timestamptz DEFAULT now()
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_fundamental_signals_ticker ON fundamental_scanner_signals(ticker);
CREATE INDEX IF NOT EXISTS idx_fundamental_signals_created_at ON fundamental_scanner_signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fundamental_signals_signal ON fundamental_scanner_signals(signal);

-- Enable RLS
ALTER TABLE fundamental_scanner_signals ENABLE ROW LEVEL SECURITY;

-- Allow anonymous users to read all signals
CREATE POLICY "Allow anonymous read access to fundamental scanner signals"
  ON fundamental_scanner_signals
  FOR SELECT
  TO anon
  USING (true);

-- Allow anonymous users to insert signals
CREATE POLICY "Allow anonymous insert access to fundamental scanner signals"
  ON fundamental_scanner_signals
  FOR INSERT
  TO anon
  WITH CHECK (true);

-- Allow authenticated users to read all signals
CREATE POLICY "Allow authenticated read access to fundamental scanner signals"
  ON fundamental_scanner_signals
  FOR SELECT
  TO authenticated
  USING (true);

-- Allow authenticated users to insert signals
CREATE POLICY "Allow authenticated insert access to fundamental scanner signals"
  ON fundamental_scanner_signals
  FOR INSERT
  TO authenticated
  WITH CHECK (true);
