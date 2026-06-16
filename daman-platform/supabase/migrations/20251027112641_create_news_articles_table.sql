/*
  # Create News Articles Table

  ## Overview
  This migration creates a comprehensive news articles table to store financial news from multiple sources
  (CNBC, Bloomberg, Reuters, Wall Street Journal, Financial Times, Associated Press, MarketWatch).

  ## 1. New Tables
    - `news_articles`
      - `id` (uuid, primary key) - Unique identifier for each article
      - `title` (text, required) - Article headline
      - `description` (text) - Article summary/description
      - `content` (text) - Full article content (if available from API)
      - `url` (text, required, unique) - Original article URL
      - `source` (text, required) - News source (e.g., "Bloomberg", "Reuters")
      - `author` (text) - Article author
      - `published_at` (timestamptz, required) - When article was published
      - `category` (text, required) - News category (Markets, Technology, Economy, etc.)
      - `image_url` (text) - Article thumbnail/image URL
      - `created_at` (timestamptz) - When record was created in our database
      - `updated_at` (timestamptz) - When record was last updated
      
  ## 2. Indexes
    - Index on `published_at` for efficient time-based queries
    - Index on `category` for category filtering
    - Index on `source` for source-based queries
    - Composite index on `category` and `published_at` for combined filters

  ## 3. Security
    - Enable Row Level Security (RLS) on `news_articles` table
    - Add policy for public read access (news is public information)
    - Add policy for authenticated users to insert news (for admin/API use)

  ## 4. Important Notes
    - URL field is unique to prevent duplicate articles
    - Articles older than 30 days could be archived/deleted via scheduled job
    - Default values ensure data consistency
    - Timestamps use timezone-aware types for accuracy
*/

-- Create news_articles table
CREATE TABLE IF NOT EXISTS news_articles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  description text DEFAULT '',
  content text DEFAULT '',
  url text NOT NULL UNIQUE,
  source text NOT NULL,
  author text DEFAULT '',
  published_at timestamptz NOT NULL,
  category text NOT NULL,
  image_url text DEFAULT '',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_news_articles_published_at ON news_articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_articles_category ON news_articles(category);
CREATE INDEX IF NOT EXISTS idx_news_articles_source ON news_articles(source);
CREATE INDEX IF NOT EXISTS idx_news_articles_category_published ON news_articles(category, published_at DESC);

-- Enable Row Level Security
ALTER TABLE news_articles ENABLE ROW LEVEL SECURITY;

-- Policy: Allow public read access to all news articles
CREATE POLICY "News articles are publicly readable"
  ON news_articles
  FOR SELECT
  TO anon, authenticated
  USING (true);

-- Policy: Allow authenticated users to insert news articles
CREATE POLICY "Authenticated users can insert news articles"
  ON news_articles
  FOR INSERT
  TO authenticated
  WITH CHECK (true);

-- Policy: Allow authenticated users to update news articles
CREATE POLICY "Authenticated users can update news articles"
  ON news_articles
  FOR UPDATE
  TO authenticated
  USING (true)
  WITH CHECK (true);

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_news_articles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
CREATE TRIGGER update_news_articles_updated_at_trigger
  BEFORE UPDATE ON news_articles
  FOR EACH ROW
  EXECUTE FUNCTION update_news_articles_updated_at();
