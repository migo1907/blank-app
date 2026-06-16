/*
  # Create accumulated_signals table for continuous market scanning

  1. New Tables
    - `accumulated_signals`
      - `id` (uuid, primary key)
      - `scanner_type` (text) - 'fusion' or 'sniper'
      - `ticker` (text) - Stock symbol
      - `side` (text) - 'LONG', 'SHORT', 'BUY', 'SELL'
      - `entry` (numeric) - Entry price
      - `stop` (numeric) - Stop loss price
      - `target` (numeric) - Target price (or target1)
      - `target2` (numeric, nullable) - Second target for multi-target signals
      - `rr` (numeric) - Risk/Reward ratio
      - `position_size` (numeric) - Position size
      - `atr` (numeric, nullable) - ATR value
      - `rsi` (numeric, nullable) - RSI value
      - `macd_hist` (numeric, nullable) - MACD histogram
      - `vwap` (numeric, nullable) - VWAP value
      - `signal_data` (jsonb) - Complete signal data for flexibility
      - `triggered_at` (timestamptz) - When signal was triggered
      - `scan_session` (date) - Trading day session (Dubai date)
      - `created_at` (timestamptz)

  2. Security
    - Enable RLS on `accumulated_signals` table
    - Add policy for public read access
    - Add policy for authenticated users to insert/update

  3. Indexes
    - Index on (scanner_type, scan_session) for fast session queries
    - Index on triggered_at for time-based queries
    - Index on ticker for symbol lookups
*/

CREATE TABLE IF NOT EXISTS accumulated_signals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scanner_type text NOT NULL CHECK (scanner_type IN ('fusion', 'sniper')),
  ticker text NOT NULL,
  side text NOT NULL,
  entry numeric NOT NULL DEFAULT 0,
  stop numeric NOT NULL DEFAULT 0,
  target numeric NOT NULL DEFAULT 0,
  target2 numeric DEFAULT 0,
  rr numeric NOT NULL DEFAULT 0,
  position_size numeric DEFAULT 0,
  atr numeric DEFAULT 0,
  rsi numeric DEFAULT 0,
  macd_hist numeric DEFAULT 0,
  vwap numeric DEFAULT 0,
  signal_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  triggered_at timestamptz NOT NULL,
  scan_session date NOT NULL,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_accumulated_signals_scanner_session 
  ON accumulated_signals(scanner_type, scan_session);

CREATE INDEX IF NOT EXISTS idx_accumulated_signals_triggered_at 
  ON accumulated_signals(triggered_at DESC);

CREATE INDEX IF NOT EXISTS idx_accumulated_signals_ticker 
  ON accumulated_signals(ticker);

ALTER TABLE accumulated_signals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access to accumulated signals"
  ON accumulated_signals
  FOR SELECT
  TO public
  USING (true);

CREATE POLICY "Allow authenticated users to insert signals"
  ON accumulated_signals
  FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Allow authenticated users to delete old signals"
  ON accumulated_signals
  FOR DELETE
  TO authenticated
  USING (true);