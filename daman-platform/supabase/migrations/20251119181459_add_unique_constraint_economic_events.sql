/*
  # Add Unique Constraint to Economic Events

  1. Changes
    - Add unique constraint on (event_date, event_title, country)
    - This prevents duplicate events from being inserted
*/

-- Add unique constraint to prevent duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_economic_events_unique 
  ON economic_events(event_date, event_title, country);