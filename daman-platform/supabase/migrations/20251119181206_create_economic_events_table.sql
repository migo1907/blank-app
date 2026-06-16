/*
  # Create Economic Events Calendar Table

  1. New Tables
    - `economic_events`
      - `id` (uuid, primary key)
      - `event_title` (text) - Name of the economic event
      - `country` (text) - Country code (USD, EUR, GBP, etc.)
      - `event_date` (timestamptz) - Date and time of the event
      - `impact` (text) - high, medium, low
      - `forecast` (text) - Forecast value
      - `previous` (text) - Previous value
      - `actual` (text) - Actual value (null until released)
      - `currency` (text) - Currency symbol
      - `source` (text) - Data source (forex_factory)
      - `created_at` (timestamptz)
      - `updated_at` (timestamptz)
  
  2. Security
    - Enable RLS on `economic_events` table
    - Add policy for public read access
    - Only service role can insert/update

  3. Indexes
    - Index on event_date for fast date queries
    - Index on impact for filtering by importance
    - Index on country for filtering by country
*/

-- Create economic_events table
CREATE TABLE IF NOT EXISTS economic_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_title text NOT NULL,
  country text NOT NULL,
  event_date timestamptz NOT NULL,
  impact text NOT NULL CHECK (impact IN ('high', 'medium', 'low')),
  forecast text,
  previous text,
  actual text,
  currency text,
  source text DEFAULT 'forex_factory',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Enable RLS
ALTER TABLE economic_events ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read economic events
CREATE POLICY "Anyone can read economic events"
  ON economic_events
  FOR SELECT
  TO public
  USING (true);

-- Only service role can insert/update events
CREATE POLICY "Service role can insert economic events"
  ON economic_events
  FOR INSERT
  TO service_role
  WITH CHECK (true);

CREATE POLICY "Service role can update economic events"
  ON economic_events
  FOR UPDATE
  TO service_role
  USING (true);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_economic_events_date 
  ON economic_events(event_date);

CREATE INDEX IF NOT EXISTS idx_economic_events_impact 
  ON economic_events(impact);

CREATE INDEX IF NOT EXISTS idx_economic_events_country 
  ON economic_events(country);

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION update_economic_events_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_economic_events_updated_at
  BEFORE UPDATE ON economic_events
  FOR EACH ROW
  EXECUTE FUNCTION update_economic_events_updated_at();