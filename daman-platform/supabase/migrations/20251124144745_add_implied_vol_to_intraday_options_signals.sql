/*
  # Add Implied Volatility Column to Intraday Options Signals

  1. Changes
    - Add `implied_vol` column to `intraday_options_signals` table
    - Column stores estimated implied volatility for options signals
    - Default value of 0 for backward compatibility

  2. Notes
    - Non-breaking change, existing data will have default IV of 0
    - IV is calculated based on RSI and market conditions
*/

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'intraday_options_signals' AND column_name = 'implied_vol'
  ) THEN
    ALTER TABLE intraday_options_signals ADD COLUMN implied_vol numeric NOT NULL DEFAULT 0;
  END IF;
END $$;
