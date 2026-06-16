/*
  # Create TradingView Signals Table

  1. **New Tables**
    - `tradingview_signals` - Stores buy/sell signals from TradingView indicators

  2. **Columns**
    - `id` (uuid, primary key)
    - `symbol` (text) - Stock symbol (e.g., AAPL)
    - `action` (text) - BUY or SELL
    - `price` (numeric) - Entry price when signal triggered
    - `target1` (numeric) - First profit target
    - `target2` (numeric) - Second profit target
    - `stop_loss` (numeric) - Stop loss level
    - `indicator_name` (text) - Name of TradingView indicator
    - `timeframe` (text) - Chart timeframe (e.g., 1h, 4h, 1D)
    - `strength` (text) - Signal strength (weak, moderate, strong)
    - `status` (text) - active, target1_hit, target2_hit, stopped_out, closed
    - `triggered_at` (timestamptz) - When signal was generated
    - `closed_at` (timestamptz) - When signal was closed
    - `pnl_percent` (numeric) - Profit/Loss percentage if closed
    - `notes` (text) - Additional notes
    - `created_at` (timestamptz)
    - `updated_at` (timestamptz)

  3. **Security**
    - Enable RLS
    - Public can read active signals
    - Only service role can insert/update (via webhook)

  4. **Indexes**
    - Index on symbol for fast filtering
    - Index on status for active signals query
    - Index on triggered_at for sorting

  5. **Views**
    - `active_signals` - Only show currently active signals
    - `signal_performance` - Performance metrics per symbol
*/

-- Create enum types for better data integrity
DO $$ BEGIN
  CREATE TYPE signal_action AS ENUM ('BUY', 'SELL');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE signal_strength AS ENUM ('weak', 'moderate', 'strong');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE signal_status AS ENUM ('active', 'target1_hit', 'target2_hit', 'stopped_out', 'closed', 'expired');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- Create tradingview_signals table
CREATE TABLE IF NOT EXISTS tradingview_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol TEXT NOT NULL,
  action signal_action NOT NULL,
  price NUMERIC NOT NULL,
  target1 NUMERIC NOT NULL,
  target2 NUMERIC NOT NULL,
  stop_loss NUMERIC NOT NULL,
  indicator_name TEXT DEFAULT 'TradingView Custom Indicator',
  timeframe TEXT DEFAULT '1D',
  strength signal_strength DEFAULT 'moderate',
  status signal_status DEFAULT 'active',
  triggered_at TIMESTAMPTZ DEFAULT NOW(),
  closed_at TIMESTAMPTZ,
  pnl_percent NUMERIC DEFAULT 0,
  notes TEXT DEFAULT '',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON tradingview_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_status ON tradingview_signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_triggered_at ON tradingview_signals(triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_action ON tradingview_signals(action);

-- Create view for active signals only
CREATE OR REPLACE VIEW active_signals AS
SELECT
  id,
  symbol,
  action,
  price,
  target1,
  target2,
  stop_loss,
  indicator_name,
  timeframe,
  strength,
  status,
  triggered_at,
  ROUND(((CASE 
    WHEN action = 'BUY' THEN ((target1 - price) / price * 100)
    ELSE ((price - target1) / price * 100)
  END))::numeric, 2) as potential_gain_t1,
  ROUND(((CASE 
    WHEN action = 'BUY' THEN ((target2 - price) / price * 100)
    ELSE ((price - target2) / price * 100)
  END))::numeric, 2) as potential_gain_t2,
  ROUND(((CASE 
    WHEN action = 'BUY' THEN ((stop_loss - price) / price * 100)
    ELSE ((price - stop_loss) / price * 100)
  END))::numeric, 2) as risk_percent,
  notes
FROM tradingview_signals
WHERE status = 'active'
ORDER BY triggered_at DESC;

-- Create view for signal performance
CREATE OR REPLACE VIEW signal_performance AS
SELECT
  symbol,
  COUNT(*) as total_signals,
  COUNT(*) FILTER (WHERE status IN ('target1_hit', 'target2_hit', 'closed')) as winning_signals,
  COUNT(*) FILTER (WHERE status = 'stopped_out') as losing_signals,
  ROUND(AVG(pnl_percent), 2) as avg_pnl_percent,
  ROUND(SUM(CASE WHEN pnl_percent > 0 THEN pnl_percent ELSE 0 END), 2) as total_profit_percent,
  ROUND(SUM(CASE WHEN pnl_percent < 0 THEN pnl_percent ELSE 0 END), 2) as total_loss_percent,
  MAX(triggered_at) as last_signal_at
FROM tradingview_signals
WHERE status != 'active'
GROUP BY symbol
ORDER BY total_signals DESC;

-- Enable Row Level Security
ALTER TABLE tradingview_signals ENABLE ROW LEVEL SECURITY;

-- Policy: Anyone can read signals (public data)
CREATE POLICY "Anyone can read trading signals"
  ON tradingview_signals
  FOR SELECT
  TO authenticated, anon
  USING (true);

-- Policy: Only service role can insert signals (webhook)
CREATE POLICY "Service role can insert signals"
  ON tradingview_signals
  FOR INSERT
  TO service_role
  WITH CHECK (true);

-- Policy: Only service role can update signals
CREATE POLICY "Service role can update signals"
  ON tradingview_signals
  FOR UPDATE
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_signals_updated_at ON tradingview_signals;
CREATE TRIGGER update_signals_updated_at
  BEFORE UPDATE ON tradingview_signals
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- Insert sample signals for testing
INSERT INTO tradingview_signals (symbol, action, price, target1, target2, stop_loss, indicator_name, timeframe, strength, status, notes)
VALUES
  ('AAPL', 'BUY', 178.50, 185.00, 192.00, 172.00, 'RSI Divergence + MACD Cross', '1D', 'strong', 'active', 'Strong bullish divergence on daily chart'),
  ('MSFT', 'BUY', 378.90, 390.00, 405.00, 370.00, 'Breakout Above Resistance', '4H', 'moderate', 'active', 'Breaking out of consolidation zone'),
  ('NVDA', 'SELL', 495.30, 480.00, 465.00, 505.00, 'Overbought RSI + Bearish Engulfing', '1D', 'strong', 'active', 'Severe overbought conditions'),
  ('TSLA', 'BUY', 242.80, 255.00, 268.00, 235.00, 'Golden Cross Formation', '1W', 'moderate', 'active', '50MA crossing above 200MA'),
  ('GOOGL', 'BUY', 140.20, 148.00, 155.00, 135.00, 'Volume Spike + Bullish Hammer', '1D', 'strong', 'active', 'Unusual volume with reversal candle'),
  ('META', 'SELL', 358.70, 345.00, 332.00, 368.00, 'Double Top Pattern', '4H', 'moderate', 'active', 'Formed double top at resistance'),
  ('AMD', 'BUY', 164.50, 172.00, 180.00, 158.00, 'Cup and Handle Pattern', '1D', 'strong', 'active', 'Classic cup and handle breakout'),
  ('AMZN', 'BUY', 145.80, 152.00, 160.00, 141.00, 'Bullish Pennant Breakout', '4H', 'moderate', 'active', 'Consolidation breakout with volume')
ON CONFLICT DO NOTHING;

-- Grant permissions on views
GRANT SELECT ON active_signals TO authenticated, anon;
GRANT SELECT ON signal_performance TO authenticated, anon;

-- Create function to automatically close expired signals
CREATE OR REPLACE FUNCTION expire_old_signals()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE tradingview_signals
  SET status = 'expired',
      closed_at = NOW(),
      updated_at = NOW()
  WHERE status = 'active'
    AND triggered_at < NOW() - INTERVAL '7 days';
END;
$$;

-- Note: Set up a cron job or scheduled function to call expire_old_signals() daily
