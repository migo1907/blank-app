/*
  # Per-user cloud data (portfolio / watchlist / settings sync)

  1. New table
     - `user_data`
       - `user_id` (uuid, pk, references auth.users)
       - `data` (jsonb) — opaque bag of the user's localStorage-backed state
       - `updated_at` (timestamptz)

  2. Security
     - RLS enabled.
     - A user can SELECT/INSERT/UPDATE/DELETE only their own row (auth.uid() = user_id).
*/

CREATE TABLE IF NOT EXISTS user_data (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  data jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE user_data ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users manage their own data" ON user_data;
CREATE POLICY "Users manage their own data"
  ON user_data
  FOR ALL
  TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);
