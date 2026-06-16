# News API Integration Guide

## Overview
The application now features a comprehensive multi-source news feed that can fetch real-time financial news from NewsAPI.org and display articles from major financial news outlets including:

- **Bloomberg**
- **Reuters**
- **Wall Street Journal**
- **Financial Times**
- **Associated Press**
- **CNBC**
- **MarketWatch**

## Features Implemented

### 1. Enhanced Mock Data (Currently Active)
- **24 curated news articles** from diverse sources
- **12 category filters**: All News, Markets, Technology, Economy, Energy, Finance, Healthcare, Crypto, Automotive, Commodities, Real Estate, Retail
- **Multi-source simulation**: Articles attributed to different major news outlets
- **Source-specific badges**: Color-coded badges for each news source
- **Realistic timestamps**: Dynamic time-based article publishing

### 2. Supabase Database Integration
- **Database Table**: `news_articles` table created with full schema
- **Columns**: title, description, content, url, source, author, published_at, category, image_url
- **Indexes**: Optimized for quick filtering by category, source, and date
- **Row Level Security**: Public read access, authenticated write access
- **Auto-timestamps**: Automatic created_at and updated_at tracking

### 3. NewsAPI.org Edge Function (Ready to Use)
- **Edge Function**: `fetch-news` deployed to Supabase
- **Functionality**: Fetches news from NewsAPI.org and stores in database
- **Features**:
  - Category filtering
  - Source filtering
  - Duplicate prevention (URL-based)
  - Automatic categorization
  - Error handling and logging

## How to Enable NewsAPI.org Integration

### Step 1: Get NewsAPI.org API Key

1. Visit [NewsAPI.org](https://newsapi.org/)
2. Sign up for a free account
3. Copy your API key from the dashboard

**Free Tier Limits:**
- 100 requests per day
- Articles from last 30 days
- No commercial use

**Paid Tiers:**
- Developer ($49/month): 500 requests/day
- Business ($249/month): 50,000 requests/day
- Enterprise (custom): Unlimited requests

### Step 2: Configure Environment Variable

The edge function requires the `NEWS_API_KEY` environment variable. This is automatically configured in your Supabase project.

To verify or update:
1. Go to your Supabase Dashboard
2. Navigate to Project Settings > Edge Functions
3. Add/update the secret: `NEWS_API_KEY` with your API key value

### Step 3: Call the Edge Function

You can trigger news fetching in two ways:

#### Option A: Manual API Call
```bash
curl -X GET "https://[your-project].supabase.co/functions/v1/fetch-news?category=business&pageSize=50" \
  -H "Authorization: Bearer [your-anon-key]"
```

#### Option B: Scheduled Job (Recommended)
Set up a cron job or scheduled function to automatically fetch news every hour:

```sql
-- Create a scheduled job (requires pg_cron extension)
SELECT cron.schedule(
  'fetch-hourly-news',
  '0 * * * *', -- Every hour
  $$
  SELECT net.http_post(
    url:='https://[your-project].supabase.co/functions/v1/fetch-news?category=business&pageSize=50',
    headers:='{"Authorization": "Bearer [your-service-role-key]"}'::jsonb
  );
  $$
);
```

### Step 4: Frontend Integration

The frontend is already configured to:
1. Fetch news from the database on page load
2. Fall back to mock data if database is empty
3. Refresh news from database when clicking the Refresh button
4. Display source-specific badges with color coding

## API Parameters

### Edge Function Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `category` | string | `business` | News category (business, technology, general, health, science) |
| `sources` | string | - | Comma-separated list of source IDs (optional) |
| `pageSize` | number | `50` | Number of articles to fetch (max 100) |

### Example Requests

**Fetch Business News:**
```
GET /functions/v1/fetch-news?category=business&pageSize=50
```

**Fetch from Specific Sources:**
```
GET /functions/v1/fetch-news?sources=bloomberg,reuters,the-wall-street-journal&pageSize=50
```

**Fetch Technology News:**
```
GET /functions/v1/fetch-news?category=technology&pageSize=30
```

## NewsAPI Source IDs

Popular financial news sources and their NewsAPI IDs:

| Publication | NewsAPI Source ID |
|------------|-------------------|
| Bloomberg | `bloomberg` |
| Reuters | `reuters` |
| Wall Street Journal | `the-wall-street-journal` |
| Financial Times | `financial-times` |
| CNBC | Not available in NewsAPI |
| Associated Press | `associated-press` |
| Business Insider | `business-insider` |
| Fortune | `fortune` |

**Note**: Not all sources are available through NewsAPI. For comprehensive coverage of CNBC, WSJ, and FT, you may need direct API access from those publishers.

## Database Queries

### Fetch Latest News by Category
```sql
SELECT * FROM news_articles
WHERE category = 'Technology'
ORDER BY published_at DESC
LIMIT 20;
```

### Fetch News from Specific Source
```sql
SELECT * FROM news_articles
WHERE source = 'Bloomberg'
ORDER BY published_at DESC
LIMIT 20;
```

### Get News Statistics by Source
```sql
SELECT
  source,
  COUNT(*) as article_count,
  MAX(published_at) as latest_article
FROM news_articles
GROUP BY source
ORDER BY article_count DESC;
```

## Current Implementation Status

✅ **Completed:**
- Mock data with 24 articles from 7 sources
- Database schema with full RLS policies
- Edge function for NewsAPI integration
- Frontend with multi-source display
- Source-specific badges and colors
- Category filtering (12 categories)
- Automatic fallback to mock data
- Refresh functionality
- Responsive design

🔜 **To Enable Real Data:**
1. Obtain NewsAPI.org API key
2. Configure `NEWS_API_KEY` environment variable in Supabase
3. Call the edge function or set up automated fetching
4. News will automatically populate from database

## Source Badge Colors

Each news source has a unique color-coded badge:

- **CNBC**: Red (CN)
- **Bloomberg**: Amber (BB)
- **Reuters**: Orange (RT)
- **Wall Street Journal**: Slate (WSJ)
- **Financial Times**: Pink (FT)
- **Associated Press**: Blue (AP)
- **MarketWatch**: Green (MW)

## Best Practices

1. **Rate Limiting**: Respect NewsAPI rate limits (100/day on free tier)
2. **Caching**: Store articles in database to reduce API calls
3. **Cleanup**: Periodically delete old articles (30+ days)
4. **Error Handling**: Always have fallback data available
5. **Attribution**: Display source prominently on each article
6. **Links**: Always link to original article URL

## Troubleshooting

### No Articles Displaying
1. Check if database has articles: `SELECT COUNT(*) FROM news_articles;`
2. Verify edge function is working: Check Supabase logs
3. Ensure RLS policies allow public read access
4. Falls back to mock data automatically

### Edge Function Errors
1. Verify `NEWS_API_KEY` is set correctly
2. Check NewsAPI quota hasn't been exceeded
3. Review Supabase edge function logs
4. Ensure Supabase client has proper permissions

### Duplicate Articles
- The system uses URL as unique constraint
- Duplicates are automatically ignored during insert
- No action needed

## Alternative News Sources

If you need more comprehensive coverage, consider:

1. **Alpha Vantage** - Financial market data and news
2. **Finnhub** - Stock market and news API
3. **Polygon.io** - Real-time and historical market data
4. **IEX Cloud** - Financial data API
5. **Direct APIs** - Bloomberg Terminal, Dow Jones API (expensive)

## Support

For issues or questions:
- Check Supabase dashboard logs
- Review NewsAPI.org documentation
- Verify database permissions and policies
- Test edge function with curl/Postman first
