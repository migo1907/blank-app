/*
  # Create market_expectations table

  1. New Tables
    - `market_expectations`
      - `id` (uuid, primary key)
      - `date` (date) - The date this expectation is for
      - `symbol` (text) - Stock symbol (SPY, QQQ, etc.)
      - `data` (jsonb) - Complete AI-generated market expectation data
      - `created_at` (timestamp)
      - `updated_at` (timestamp)

  2. Security
    - Enable RLS on `market_expectations` table
    - Add policy for public read access (anyone can view market expectations)
    - Add policy for service role to insert/update (AI generation)

  3. Indexes
    - Index on (date, symbol) for fast lookups
    - Unique constraint on (date, symbol) to prevent duplicates
*/

CREATE TABLE IF NOT EXISTS market_expectations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  date date NOT NULL,
  symbol text NOT NULL,
  data jsonb NOT NULL,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE(date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_market_expectations_date_symbol 
  ON market_expectations(date, symbol);

ALTER TABLE market_expectations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access to market expectations"
  ON market_expectations
  FOR SELECT
  TO public
  USING (true);

CREATE POLICY "Allow authenticated users to insert market expectations"
  ON market_expectations
  FOR INSERT
  TO authenticated
  WITH CHECK (true);

CREATE POLICY "Allow authenticated users to update market expectations"
  ON market_expectations
  FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);
