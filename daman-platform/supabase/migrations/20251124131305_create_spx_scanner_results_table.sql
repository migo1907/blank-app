/*
  # Create SPX Scanner Results Table

  1. New Tables
    - `spx_scanner_results`
      - `id` (uuid, primary key)
      - `timestamp` (timestamptz) - ISO timestamp of when scan occurred
      - `dubai_time` (text) - Formatted Dubai time string for display
      - `signal` (text) - Trade signal: 'CALL', 'PUT', or 'NO_SIGNAL'
      - `reason` (text) - Detailed explanation of the signal
      - `price` (numeric) - Current SPX price at scan time
      - `vwap` (numeric) - Volume-Weighted Average Price
      - `ema5` (numeric) - 5-period Exponential Moving Average
      - `ema20` (numeric) - 20-period Exponential Moving Average
      - `rsi` (numeric) - Relative Strength Index (14-period)
      - `bias` (text) - Market bias: 'BULLISH', 'BEARISH', or 'NEUTRAL'
      - `recommendations` (jsonb) - Array of trade recommendations with strikes and targets
      - `created_at` (timestamptz) - Record creation timestamp

  2. Security
    - Enable RLS on `spx_scanner_results` table
    - Add policy for public read access (scanner results are public data)
    - Add policy for authenticated insert (only authenticated users can create scans)

  3. Indexes
    - Index on timestamp for efficient historical queries
    - Index on signal for filtering by trade type
*/

-- Create the spx_scanner_results table
CREATE TABLE IF NOT EXISTS spx_scanner_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp timestamptz NOT NULL,
  dubai_time text NOT NULL,
  signal text NOT NULL CHECK (signal IN ('CALL', 'PUT', 'NO_SIGNAL')),
  reason text NOT NULL DEFAULT '',
  price numeric NOT NULL DEFAULT 0,
  vwap numeric NOT NULL DEFAULT 0,
  ema5 numeric NOT NULL DEFAULT 0,
  ema20 numeric NOT NULL DEFAULT 0,
  rsi numeric NOT NULL DEFAULT 0,
  bias text NOT NULL DEFAULT 'NEUTRAL' CHECK (bias IN ('BULLISH', 'BEARISH', 'NEUTRAL')),
  recommendations jsonb DEFAULT '[]'::jsonb,
  created_at timestamptz DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE spx_scanner_results ENABLE ROW LEVEL SECURITY;

-- Create policy for public read access
CREATE POLICY "Public can read SPX scanner results"
  ON spx_scanner_results
  FOR SELECT
  TO public
  USING (true);

-- Create policy for authenticated insert
CREATE POLICY "Authenticated users can insert SPX scanner results"
  ON spx_scanner_results
  FOR INSERT
  TO authenticated
  WITH CHECK (true);

-- Create policy for service role full access
CREATE POLICY "Service role has full access to SPX scanner results"
  ON spx_scanner_results
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_spx_scanner_results_timestamp
  ON spx_scanner_results(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_spx_scanner_results_signal
  ON spx_scanner_results(signal);

CREATE INDEX IF NOT EXISTS idx_spx_scanner_results_created_at
  ON spx_scanner_results(created_at DESC);
