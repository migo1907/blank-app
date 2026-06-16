-- Create Missing Critical Database Views
-- Creates views for top gainers, top losers, and latest stock prices

-- Latest Stock Prices View
-- Returns the most recent price for each stock symbol
CREATE OR REPLACE VIEW latest_stock_prices AS
SELECT DISTINCT ON (symbol)
  symbol,
  price,
  open,
  high,
  low,
  close,
  volume,
  change,
  change_percent,
  timestamp
FROM stock_prices
ORDER BY symbol, timestamp DESC;

-- Top Gainers View  
-- Returns top 50 stocks by percentage change
CREATE OR REPLACE VIEW top_gainers AS
SELECT
  sp.symbol,
  su.name,
  sp.price,
  sp.change,
  sp.change_percent,
  sp.volume,
  su.exchange,
  su.sector,
  sp.timestamp
FROM (
  SELECT DISTINCT ON (symbol)
    symbol,
    price,
    change,
    change_percent,
    volume,
    timestamp
  FROM stock_prices
  WHERE change_percent > 0
  ORDER BY symbol, timestamp DESC
) sp
JOIN stock_universe su ON sp.symbol = su.symbol
ORDER BY sp.change_percent DESC
LIMIT 50;

-- Top Losers View
-- Returns top 50 stocks by percentage change (negative)
CREATE OR REPLACE VIEW top_losers AS
SELECT
  sp.symbol,
  su.name,
  sp.price,
  sp.change,
  sp.change_percent,
  sp.volume,
  su.exchange,
  su.sector,
  sp.timestamp
FROM (
  SELECT DISTINCT ON (symbol)
    symbol,
    price,
    change,
    change_percent,
    volume,
    timestamp
  FROM stock_prices
  WHERE change_percent < 0
  ORDER BY symbol, timestamp DESC
) sp
JOIN stock_universe su ON sp.symbol = su.symbol
ORDER BY sp.change_percent ASC
LIMIT 50;

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_stock_prices_symbol_timestamp 
  ON stock_prices(symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_stock_prices_change_percent 
  ON stock_prices(change_percent DESC);

CREATE INDEX IF NOT EXISTS idx_news_articles_published_at 
  ON news_articles(published_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_articles_category 
  ON news_articles(category);

CREATE INDEX IF NOT EXISTS idx_stock_universe_sector 
  ON stock_universe(sector);

CREATE INDEX IF NOT EXISTS idx_stock_universe_exchange 
  ON stock_universe(exchange);

CREATE INDEX IF NOT EXISTS idx_stock_technicals_symbol 
  ON stock_technicals(symbol);

CREATE INDEX IF NOT EXISTS idx_stock_technicals_timestamp 
  ON stock_technicals(timestamp DESC);

-- Grant permissions
GRANT SELECT ON latest_stock_prices TO anon, authenticated;
GRANT SELECT ON top_gainers TO anon, authenticated;
GRANT SELECT ON top_losers TO anon, authenticated;