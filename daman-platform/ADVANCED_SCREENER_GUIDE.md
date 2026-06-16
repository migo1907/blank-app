# Advanced Financial Market Screener - Implementation Guide

## Overview

This document provides comprehensive documentation for the Advanced Financial Market Screener application - a professional-grade stock screening platform with real-time data, technical indicators, fundamental analysis, and user personalization features.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Schema](#database-schema)
3. [Core Features](#core-features)
4. [Technical Indicators](#technical-indicators)
5. [API Integration](#api-integration)
6. [User Guide](#user-guide)
7. [Development Roadmap](#development-roadmap)

---

## Architecture Overview

### Technology Stack

**Frontend:**
- React 18.3+ with TypeScript
- Vite 5.4+ for build tooling
- Tailwind CSS for styling
- Lucide React for icons

**Backend:**
- Supabase (PostgreSQL database)
- Supabase Edge Functions (Deno runtime)
- Yahoo Finance API for market data

**Key Libraries:**
- `@supabase/supabase-js` - Database client
- Technical indicators calculated in-house

### Application Structure

```
src/
├── components/          # Reusable UI components
│   ├── MarketDataTable.tsx
│   ├── StockChart.tsx
│   ├── NewsCard.tsx
│   └── ...
├── pages/              # Main application pages
│   ├── HomePage.tsx
│   ├── MarketAnalysisAndNews.tsx
│   ├── AdvancedScreener.tsx
│   └── ...
├── services/           # Business logic & API calls
│   ├── marketDataService.ts
│   ├── stockDataService.ts
│   ├── technicalIndicatorsService.ts
│   └── ...
├── utils/              # Utility functions
│   └── tickColorUtils.ts
└── lib/                # Third-party integrations
    └── supabase.ts
```

---

## Database Schema

### Core Tables

#### 1. **user_profiles**
User account information and preferences
- `id` (uuid, PK) - Links to Supabase auth.users
- `email` (text, unique)
- `full_name` (text)
- `avatar_url` (text)
- `theme_preference` (text) - 'light' or 'dark'
- `created_at`, `updated_at` (timestamptz)

**Security:** Users can only read/update their own profile

#### 2. **watchlists**
User-created stock watchlists
- `id` (uuid, PK)
- `user_id` (uuid, FK → user_profiles)
- `name` (text) - Watchlist name
- `description` (text)
- `is_default` (boolean)
- `created_at`, `updated_at` (timestamptz)

**Security:** Users can only manage their own watchlists

#### 3. **watchlist_items**
Stocks within watchlists
- `id` (uuid, PK)
- `watchlist_id` (uuid, FK → watchlists)
- `symbol` (text)
- `added_at` (timestamptz)
- `notes` (text)

#### 4. **screener_presets**
Saved filter configurations
- `id` (uuid, PK)
- `user_id` (uuid, FK → user_profiles)
- `name` (text)
- `description` (text)
- `filters` (jsonb) - JSON object with filter criteria
- `is_public` (boolean) - Share with other users
- `created_at`, `updated_at` (timestamptz)

**Security:** Users can view own + public presets, manage only their own

#### 5. **price_alerts**
Price and percentage change alerts
- `id` (uuid, PK)
- `user_id` (uuid, FK → user_profiles)
- `symbol` (text)
- `alert_type` (text) - 'price_above', 'price_below', 'percent_change'
- `target_value` (numeric)
- `is_active` (boolean)
- `triggered_at` (timestamptz)
- `created_at` (timestamptz)

#### 6. **portfolios**
User investment portfolios
- `id` (uuid, PK)
- `user_id` (uuid, FK → user_profiles)
- `name` (text)
- `description` (text)
- `initial_value` (numeric)
- `created_at`, `updated_at` (timestamptz)

#### 7. **portfolio_positions**
Individual holdings within portfolios
- `id` (uuid, PK)
- `portfolio_id` (uuid, FK → portfolios)
- `symbol` (text)
- `shares` (numeric)
- `average_cost` (numeric)
- `purchase_date` (timestamptz)
- `notes` (text)
- `created_at`, `updated_at` (timestamptz)

#### 8. **stock_technicals**
Technical indicator data
- `id` (uuid, PK)
- `symbol` (text)
- `rsi_14` (numeric) - Relative Strength Index (14-period)
- `macd` (numeric) - MACD line
- `macd_signal` (numeric) - Signal line
- `macd_histogram` (numeric) - MACD histogram
- `sma_20`, `sma_50`, `sma_200` (numeric) - Simple Moving Averages
- `ema_12`, `ema_26` (numeric) - Exponential Moving Averages
- `bb_upper`, `bb_middle`, `bb_lower` (numeric) - Bollinger Bands
- `signal` (text) - 'strong_buy', 'buy', 'neutral', 'sell', 'strong_sell'
- `timestamp` (timestamptz)

**Security:** Publicly readable, authenticated write

#### 9. **stock_fundamentals**
Fundamental metrics and ratios
- `id` (uuid, PK)
- `symbol` (text, unique)
- `pe_ratio` (numeric) - Price-to-Earnings ratio
- `peg_ratio` (numeric) - Price/Earnings to Growth
- `price_to_book` (numeric)
- `price_to_sales` (numeric)
- `dividend_yield` (numeric)
- `eps` (numeric) - Earnings Per Share
- `market_cap` (bigint)
- `shares_outstanding` (bigint)
- `short_interest` (numeric) - % of float sold short
- `short_ratio` (numeric) - Days to cover
- `beta` (numeric) - Market volatility measure
- `fifty_two_week_high`, `fifty_two_week_low` (numeric)
- `avg_volume` (bigint)
- `updated_at` (timestamptz)

**Security:** Publicly readable, authenticated write

### Database Views

#### **latest_stock_technicals**
Latest technical indicator reading per symbol
```sql
SELECT DISTINCT ON (symbol) *
FROM stock_technicals
ORDER BY symbol, timestamp DESC
```

#### **stock_screener_data**
Comprehensive view joining all stock data
```sql
SELECT
  su.symbol, su.name, su.exchange, su.sector, su.industry,
  sp.price, sp.change, sp.change_percent, sp.volume,
  sf.pe_ratio, sf.market_cap, sf.dividend_yield, sf.beta, sf.short_interest,
  sf.fifty_two_week_high, sf.fifty_two_week_low,
  st.rsi_14, st.macd, st.sma_20, st.sma_50, st.sma_200, st.signal
FROM stock_universe su
LEFT JOIN (latest stock_prices) sp ON su.symbol = sp.symbol
LEFT JOIN stock_fundamentals sf ON su.symbol = sf.symbol
LEFT JOIN latest_stock_technicals st ON su.symbol = st.symbol
```

---

## Core Features

### 1. Advanced Stock Screener

**Location:** `/src/pages/AdvancedScreener.tsx`

**Filter Categories:**

**Price & Volume:**
- Min/Max price range
- Minimum volume threshold
- Market cap ranges (Micro, Small, Mid, Large, Mega cap)

**Technical Indicators:**
- RSI (14-period) range filtering
- MACD conditions
- Moving average crossovers (SMA 20/50/200)
- Bollinger Band position
- Buy/Sell signal detection

**Fundamental Metrics:**
- P/E ratio ranges
- Dividend yield minimum
- Beta (volatility) ranges
- Short interest filtering
- 52-week high/low proximity

**Classification:**
- Sector filtering (Technology, Healthcare, Financial, etc.)
- Exchange filtering (NASDAQ, NYSE, AMEX)
- Industry sub-categories

**Features:**
- Real-time filtering with database queries
- Sortable columns
- CSV export functionality
- Save filter presets (requires authentication)
- Search by symbol or company name
- Top 100 results display
- Responsive design for mobile/tablet

**Usage Example:**
```typescript
// Apply custom filters
const filters = {
  priceMin: 10,
  priceMax: 500,
  marketCapMin: 1e9, // $1B minimum
  rsiMin: 30,
  rsiMax: 70,
  signal: ['strong_buy', 'buy'],
  sectors: ['Technology'],
};
```

### 2. Technical Indicators Service

**Location:** `/src/services/technicalIndicatorsService.ts`

**Implemented Indicators:**

#### RSI (Relative Strength Index)
```typescript
calculateRSI(prices: number[], period: number = 14): number
```
- Momentum oscillator (0-100)
- Oversold: < 30 (potential buy)
- Overbought: > 70 (potential sell)

#### MACD (Moving Average Convergence Divergence)
```typescript
calculateMACD(prices: number[]): { macd, signal, histogram }
```
- Trend-following momentum indicator
- Buy signal: MACD crosses above signal line
- Sell signal: MACD crosses below signal line

#### Moving Averages
```typescript
calculateSMA(prices: number[], period: number): number
calculateEMA(prices: number[], period: number): number
```
- SMA 20/50/200 for trend identification
- EMA 12/26 for MACD calculation
- Golden Cross: SMA 50 > SMA 200 (bullish)
- Death Cross: SMA 50 < SMA 200 (bearish)

#### Bollinger Bands
```typescript
calculateBollingerBands(prices: number[], period: 20, stdDev: 2)
```
- Volatility indicator
- Price at lower band: potential buy
- Price at upper band: potential sell

#### Buy/Sell Signal Generation
```typescript
generateBuySignal(indicators, currentPrice):
  'strong_buy' | 'buy' | 'neutral' | 'sell' | 'strong_sell'
```

**Scoring System:**
- RSI < 30: +2 points
- RSI 30-40: +1 point
- MACD histogram > 0: +1 point
- SMA 20 > SMA 50: +1 point
- SMA 50 > SMA 200: +1 point
- Price > SMA 20: +1 point
- Price near lower Bollinger Band: +1 point

**Signal Thresholds:**
- Strong Buy: ≥ 4 points
- Buy: 2-3 points
- Neutral: -1 to 1 points
- Sell: -2 to -3 points
- Strong Sell: ≤ -4 points

### 3. Market Analysis Dashboard

**Location:** `/src/pages/MarketAnalysisAndNews.tsx`

**Features:**
- Live market indicators (S&P 500, NASDAQ, Dow Jones, VIX)
- Top 5 Gainers/Losers with real-time updates
- Interactive stock price charts
- News feed integration
- 30-second auto-refresh

**Data Sources:**
- Yahoo Finance API for market indices
- Database views for top movers
- NewsAPI for financial news

### 4. Interactive Stock Charts

**Location:** `/src/components/StockChart.tsx`

**Features:**
- Canvas-based rendering for performance
- 50-point historical price data
- Hover to view price at specific times
- Color-coded trends (green for gains, red for losses)
- Real-time updates when stock selection changes
- Responsive scaling across devices

### 5. Live Data Integration

**Market Data Service** (`src/services/marketDataService.ts`):
- Fetches real-time quotes from Yahoo Finance
- 1-minute client-side caching
- Automatic fallback to cached data on API failure

**Stock Data Service** (`src/services/stockDataService.ts`):
- Top gainers/losers queries
- Stock universe filtering
- Latest price fetching
- Auto-update mechanisms (30-second intervals)

---

## Technical Indicators

### Implementation Details

All technical indicators are calculated client-side using historical price data. The calculations follow industry-standard formulas:

**RSI Calculation:**
1. Calculate price changes over period (default 14 days)
2. Separate gains and losses
3. Calculate average gain and average loss
4. RS = Average Gain / Average Loss
5. RSI = 100 - (100 / (1 + RS))

**MACD Calculation:**
1. Calculate 12-period EMA
2. Calculate 26-period EMA
3. MACD Line = EMA(12) - EMA(26)
4. Signal Line = 9-period EMA of MACD Line
5. Histogram = MACD Line - Signal Line

**Bollinger Bands Calculation:**
1. Calculate 20-period SMA (middle band)
2. Calculate standard deviation of prices
3. Upper Band = SMA + (2 × StdDev)
4. Lower Band = SMA - (2 × StdDev)

---

## API Integration

### Edge Functions

**1. fetch-market-data**
```typescript
GET /functions/v1/fetch-market-data?symbols=^GSPC,^IXIC,^DJI,^VIX
```
Fetches real-time quotes for market indices from Yahoo Finance.

**2. fetch-stock-data**
```typescript
GET /functions/v1/fetch-stock-data?symbols=AAPL,MSFT&mode=fetch
```
Fetches stock prices and stores in database when mode=update.

**3. fetch-news**
```typescript
GET /functions/v1/fetch-news?category=business&pageSize=50
```
Fetches financial news from NewsAPI.org (requires API key).

### External APIs

**Yahoo Finance:**
- Free, no authentication required
- Real-time stock quotes
- Historical price data
- Market indices

**NewsAPI.org:**
- Requires API key (free tier available)
- Financial news from multiple sources
- Categorized by topic

---

## User Guide

### Getting Started

1. **Browse Market Data**
   - Navigate to "Market Analysis & News" to view live market indicators
   - Click on any stock in Top 5 Gainers/Losers to view chart

2. **Use Advanced Screener**
   - Navigate to "Advanced Screener"
   - Apply filters using the sidebar:
     - Set price range (e.g., $10-$500)
     - Choose market cap range
     - Select RSI range for momentum filtering
     - Choose technical signals (Strong Buy, Buy, etc.)
     - Filter by sector or exchange
   - Click "Apply Filters" to see results
   - Click "Export CSV" to download results

3. **Interpret Technical Signals**
   - **Strong Buy (Green):** Multiple bullish indicators align
   - **Buy (Light Green):** Some bullish signals present
   - **Neutral (Gray):** No clear direction
   - **Sell (Light Red):** Some bearish signals present
   - **Strong Sell (Red):** Multiple bearish indicators align

### Filter Examples

**Value Stocks:**
```
- P/E Ratio: 0-15
- Market Cap: > $1B
- Dividend Yield: > 2%
```

**Growth Momentum:**
```
- RSI: 50-70
- Signal: Strong Buy or Buy
- Market Cap: > $10B
- Sector: Technology
```

**Oversold Opportunities:**
```
- RSI: 20-35
- Signal: Strong Buy
- 52-week low: within 10% of current price
```

**High Short Interest:**
```
- Short Interest: > 15%
- Volume: > 1M shares
- Signal: Strong Buy
```

---

## Development Roadmap

### Phase 1: Foundation (✅ Completed)
- [x] Database schema with RLS policies
- [x] Technical indicators service
- [x] Advanced screener UI with filters
- [x] Live market data integration
- [x] Interactive charts

### Phase 2: User Features (Next)
- [ ] Authentication system (Supabase Auth)
- [ ] User profiles and preferences
- [ ] Watchlist management
- [ ] Saved screener presets
- [ ] Dark/light theme toggle

### Phase 3: Advanced Features
- [ ] Stock detail pages with full analytics
- [ ] Portfolio tracking with P&L calculation
- [ ] Price alerts and notifications
- [ ] Email/SMS alert delivery
- [ ] Historical performance tracking

### Phase 4: Analytics & Insights
- [ ] Backtesting capabilities
- [ ] Strategy builder
- [ ] AI-powered stock recommendations
- [ ] Sentiment analysis from news
- [ ] Peer comparison tools

### Phase 5: Social & Community
- [ ] Share screener presets publicly
- [ ] Follow other traders
- [ ] Discussion forums per stock
- [ ] Social sentiment indicators
- [ ] Leaderboards

---

## Performance Optimization

### Current Optimizations
- Client-side caching (1-minute for market data)
- Database indices on frequently queried columns
- Database views for complex joins
- Pagination (top 100 results)
- Debounced filter application

### Future Optimizations
- Redis caching layer
- WebSocket connections for real-time updates
- Server-side rendered stock pages
- CDN for static assets
- Database query optimization with EXPLAIN ANALYZE

---

## Security Considerations

### Implemented Security
- Row-Level Security (RLS) on all user tables
- Authentication required for write operations
- Public read access for market data (appropriate for public financial data)
- CORS properly configured on edge functions
- Environment variables for API keys

### Best Practices
- Never expose API keys in client code
- Proxy all external API calls through edge functions
- Validate user input on both client and server
- Rate limiting on edge functions (Supabase built-in)
- Regular security audits

---

## Deployment

### Production Checklist
- [ ] Configure NEWS_API_KEY in Supabase secrets
- [ ] Set up scheduled jobs for data updates
- [ ] Configure custom domain
- [ ] Enable edge function monitoring
- [ ] Set up error tracking (Sentry)
- [ ] Configure backup schedule
- [ ] Performance monitoring (Vercel Analytics)
- [ ] SEO optimization

### Environment Variables
```env
VITE_SUPABASE_URL=your_supabase_url
VITE_SUPABASE_ANON_KEY=your_anon_key
```

---

## Support & Maintenance

### Data Updates
- Stock prices: Real-time via API calls
- Technical indicators: Calculated on-demand
- Fundamentals: Should be updated daily via scheduled job
- News: Automatic updates every 5 minutes (when configured)

### Monitoring
- Edge function logs in Supabase dashboard
- Database performance metrics
- API rate limit usage
- Error rates and types

---

## Conclusion

This Advanced Financial Market Screener provides a solid foundation for a professional-grade stock analysis platform. The modular architecture allows for easy extension of features, and the comprehensive database schema supports advanced user features.

The application demonstrates:
- ✅ Real-time market data integration
- ✅ Advanced filtering with technical & fundamental criteria
- ✅ Professional UI/UX design
- ✅ Scalable architecture
- ✅ Security best practices
- ✅ Performance optimization

For questions or support, refer to the inline code documentation or contact the development team.
