/*
  # Fix Stock Signals RLS for Anonymous Access

  1. Changes
    - Drop existing restrictive SELECT policy
    - Add new policy allowing anonymous users to read signals
    - Keep authenticated users able to update and delete
  
  2. Security
    - READ: Allow anonymous and authenticated (signals are public data)
    - UPDATE: Only authenticated users
    - DELETE: Only authenticated users
*/

-- Drop the old restrictive policy
DROP POLICY IF EXISTS "Anyone can read stock signals" ON stock_signals;

-- Allow both anonymous and authenticated users to read signals
CREATE POLICY "Enable read access for all users"
  ON stock_signals
  FOR SELECT
  TO anon, authenticated
  USING (true);

-- Allow authenticated users to delete signals
DROP POLICY IF EXISTS "Users can delete signals" ON stock_signals;

CREATE POLICY "Authenticated users can delete signals"
  ON stock_signals
  FOR DELETE
  TO authenticated
  USING (true);
