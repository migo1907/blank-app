/*
  # Add Breaking News Timestamp

  1. Changes
    - Add breaking_news_time column to track when breaking news was first identified
    - This will be used to display breaking news for 30 minutes in red color
*/

-- Add breaking news timestamp column
DO $$ 
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'news_articles' AND column_name = 'breaking_news_time'
  ) THEN
    ALTER TABLE news_articles ADD COLUMN breaking_news_time timestamptz;
  END IF;
END $$;

-- Set breaking_news_time for existing breaking news articles
UPDATE news_articles 
SET breaking_news_time = published_at 
WHERE is_breaking = true AND breaking_news_time IS NULL;