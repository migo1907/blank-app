/*
  # Create Quant Filter Signals Table

  1. New Tables
    - `quant_filter_signals`
      - `id` (uuid, primary key)
      - `symbol` (text)
      - `name` (text)
      - `sector` (text)
      - `signal_type` (text) - INTRADAY or DAILY_SWING
      - `entry_price` (numeric)
      - `stop_loss` (numeric)
      - `take_profit` (numeric)
      - `share_size` (text)
      - `max_dollar_risk` (numeric)
      - `r_multiple` (numeric)
      - `dynamic_slippage` (numeric)
      - `price` (numeric)
      - `criteria_met` (integer)
      - `criteria_details` (jsonb)
      - `status` (text) - active, closed, expired
      - `outcome` (text) - WIN, LOSS, or null
      - `pnl` (numeric)
      - `created_at` (timestamptz)
      - `updated_at` (timestamptz)
  
  2. Security
    - Enable RLS on `quant_filter_signals` table
    - Add policy for anonymous and authenticated users to read signals
    - Add policy for system to insert/update signals
*/

-- Create the quant_filter_signals table
CREATE TABLE IF NOT EXISTS quant_filter_signals (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  name text,
  sector text,
  signal_type text NOT NULL,
  entry_price numeric NOT NULL,
  stop_loss numeric NOT NULL,
  take_profit numeric NOT NULL,
  share_size text NOT NULL,
  max_dollar_risk numeric NOT NULL,
  r_multiple numeric NOT NULL,
  dynamic_slippage numeric NOT NULL,
  price numeric NOT NULL,
  criteria_met integer NOT NULL,
  criteria_details jsonb,
  status text DEFAULT 'active',
  outcome text,
  pnl numeric DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Enable RLS
ALTER TABLE quant_filter_signals ENABLE ROW LEVEL SECURITY;

-- Allow anonymous and authenticated users to read all signals
CREATE POLICY "Enable read access for all users"
  ON quant_filter_signals
  FOR SELECT
  TO anon, authenticated
  USING (true);

-- Allow anonymous and authenticated users to insert signals
CREATE POLICY "Enable insert access for all users"
  ON quant_filter_signals
  FOR INSERT
  TO anon, authenticated
  WITH CHECK (true);

-- Allow authenticated users to update signals
CREATE POLICY "Enable update access for authenticated users"
  ON quant_filter_signals
  FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_quant_filter_signals_created_at ON quant_filter_signals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_quant_filter_signals_symbol ON quant_filter_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_quant_filter_signals_status ON quant_filter_signals(status);
