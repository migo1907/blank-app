/*
  # Daily market-commentary subscribers

  Stores opt-in subscriptions for the AI daily market commentary email.

  1. New table
     - `commentary_subscribers`
       - `id` (uuid, pk)
       - `email` (text, unique, not null)
       - `frequency` (text: 'daily' | 'weekdays', default 'weekdays')
       - `active` (boolean, default true)
       - `created_at` (timestamptz, default now())

  2. Security
     - RLS enabled.
     - Anyone (anon) may INSERT a subscription (public sign-up form).
     - No public SELECT/UPDATE/DELETE — managing subscribers is a backend/admin task.
*/

CREATE TABLE IF NOT EXISTS commentary_subscribers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL,
  frequency text NOT NULL DEFAULT 'weekdays' CHECK (frequency IN ('daily', 'weekdays')),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE commentary_subscribers ENABLE ROW LEVEL SECURITY;

-- Public sign-up: allow anonymous and authenticated inserts.
DROP POLICY IF EXISTS "Anyone can subscribe" ON commentary_subscribers;
CREATE POLICY "Anyone can subscribe"
  ON commentary_subscribers
  FOR INSERT
  TO anon, authenticated
  WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_commentary_subscribers_active
  ON commentary_subscribers (active)
  WHERE active = true;
