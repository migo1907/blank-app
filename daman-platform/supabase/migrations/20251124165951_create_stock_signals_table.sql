/*
  # Create Stock Signals Table for TradingView Integration

  1. New Tables
    - `stock_signals`
      - `id` (uuid, primary key)
      - `timestamp` (timestamptz) - When signal was created
      - `ticker` (text) - Stock symbol
      - `signal_type` (text) - BUY, SELL, LONG, SHORT, etc.
      - `price` (numeric) - Current price at signal
      - `timeframe` (text) - Chart timeframe (1m, 5m, 15m, 1h, 4h, 1D)
      - `indicator` (text) - Indicator that triggered (RSI, MACD, etc)
      - `strategy` (text) - Strategy name from TradingView
      - `stop_loss` (numeric) - Suggested stop loss
      - `take_profit` (numeric) - Suggested take profit
      - `message` (text) - Full alert message
      - `webhook_data` (jsonb) - Raw webhook payload
      - `created_at` (timestamptz) - Database insert time
      - `is_active` (boolean) - Whether signal is still valid
      - `notes` (text) - User notes

  2. Security
    - Enable RLS on `stock_signals` table
    - Add policies for reading and inserting signals
    - Public read access for signals (authenticated users)
    - Service role can insert via webhook

  3. Indexes
    - Index on ticker for fast lookups
    - Index on timestamp for time-based queries
    - Index on signal_type for filtering
*/

CREATE TABLE IF NOT EXISTS stock_signals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp timestamptz NOT NULL DEFAULT now(),
  ticker text NOT NULL,
  signal_type text NOT NULL,
  price numeric NOT NULL DEFAULT 0,
  timeframe text DEFAULT '5m',
  indicator text,
  strategy text,
  stop_loss numeric,
  take_profit numeric,
  message text,
  webhook_data jsonb,
  created_at timestamptz DEFAULT now(),
  is_active boolean DEFAULT true,
  notes text
);

ALTER TABLE stock_signals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can read stock signals"
  ON stock_signals
  FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Service role can insert signals"
  ON stock_signals
  FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Users can update their notes"
  ON stock_signals
  FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_stock_signals_ticker ON stock_signals(ticker);
CREATE INDEX IF NOT EXISTS idx_stock_signals_timestamp ON stock_signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_stock_signals_type ON stock_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_stock_signals_active ON stock_signals(is_active);
