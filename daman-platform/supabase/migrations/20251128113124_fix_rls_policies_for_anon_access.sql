/*
  # Fix RLS Policies for Anonymous Access

  1. Changes to Existing Tables
    - Add policies to allow anonymous (public) users to read from materialized views
    - Add policies to allow anonymous users to insert into scanner results tables
    - Fix missing tick_data table or update references

  2. Security
    - Maintain security while allowing read-only access to public data
    - Allow anonymous users to insert scanner results (informational data)
    - Keep write restrictions for authenticated users where appropriate

  3. Affected Tables
    - stock_screener_data (materialized view) - Add public SELECT policy
    - spx_scanner_results - Add anonymous INSERT policy
*/

-- Create tick_data table if it doesn't exist (for sector performance data)
CREATE TABLE IF NOT EXISTS tick_data (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  sector text,
  price numeric DEFAULT 0,
  change_percent numeric DEFAULT 0,
  volume bigint DEFAULT 0,
  market_cap numeric DEFAULT 0,
  last_updated timestamptz DEFAULT now(),
  created_at timestamptz DEFAULT now()
);

ALTER TABLE tick_data ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public can read tick data"
  ON tick_data
  FOR SELECT
  TO public
  USING (true);

CREATE POLICY "Service role can manage tick data"
  ON tick_data
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_tick_data_symbol ON tick_data(symbol);
CREATE INDEX IF NOT EXISTS idx_tick_data_last_updated ON tick_data(last_updated DESC);

-- Grant SELECT on materialized view to anonymous users
DO $$
BEGIN
  -- Grant usage on schema
  GRANT USAGE ON SCHEMA public TO anon;
  
  -- Grant SELECT on the materialized view
  GRANT SELECT ON stock_screener_data TO anon;
  GRANT SELECT ON stock_screener_data TO authenticated;
END $$;

-- Add policy to allow anonymous users to insert into spx_scanner_results
DROP POLICY IF EXISTS "Anonymous can insert SPX scanner results" ON spx_scanner_results;
CREATE POLICY "Anonymous can insert SPX scanner results"
  ON spx_scanner_results
  FOR INSERT
  TO anon
  WITH CHECK (true);

-- Ensure anonymous can also insert into other scanner tables
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'intraday_options_signals') THEN
    EXECUTE 'DROP POLICY IF EXISTS "Anonymous can insert intraday options signals" ON intraday_options_signals';
    EXECUTE 'CREATE POLICY "Anonymous can insert intraday options signals" ON intraday_options_signals FOR INSERT TO anon WITH CHECK (true)';
  END IF;
END $$;
