/*
  # Add breaking news column

  1. **Changes**
    - Add `is_breaking` column to news_articles table
    - Defaults to false
    - Used to highlight urgent/breaking news
*/

-- Add is_breaking column
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'news_articles' AND column_name = 'is_breaking'
  ) THEN
    ALTER TABLE news_articles ADD COLUMN is_breaking BOOLEAN DEFAULT false;
  END IF;
END $$;

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_news_breaking ON news_articles(is_breaking) WHERE is_breaking = true;
