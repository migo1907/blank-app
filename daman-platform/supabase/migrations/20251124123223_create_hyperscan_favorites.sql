/*
  # Create HyperScan Favorites Table

  1. New Tables
    - `hyperscan_favorites`
      - `id` (uuid, primary key)
      - `user_id` (uuid, references auth.users - nullable for now)
      - `symbol` (text, stock ticker)
      - `name` (text, company name)
      - `added_at` (timestamptz, when added)
      - `notes` (text, optional user notes)
  
  2. Security
    - Enable RLS on `hyperscan_favorites` table
    - Add policy for public access (can be restricted later with auth)
    - Add unique constraint on symbol to prevent duplicates
  
  3. Indexes
    - Index on symbol for fast lookups
*/

CREATE TABLE IF NOT EXISTS hyperscan_favorites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE DEFAULT NULL,
  symbol text NOT NULL,
  name text DEFAULT '',
  notes text DEFAULT '',
  added_at timestamptz DEFAULT now(),
  UNIQUE(symbol)
);

ALTER TABLE hyperscan_favorites ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access to favorites"
  ON hyperscan_favorites
  FOR SELECT
  USING (true);

CREATE POLICY "Allow public insert to favorites"
  ON hyperscan_favorites
  FOR INSERT
  WITH CHECK (true);

CREATE POLICY "Allow public update to favorites"
  ON hyperscan_favorites
  FOR UPDATE
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Allow public delete from favorites"
  ON hyperscan_favorites
  FOR DELETE
  USING (true);

CREATE INDEX IF NOT EXISTS idx_hyperscan_favorites_symbol ON hyperscan_favorites(symbol);
CREATE INDEX IF NOT EXISTS idx_hyperscan_favorites_added_at ON hyperscan_favorites(added_at DESC);
