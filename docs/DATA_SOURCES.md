# Data Sources — Inventory, Health & Consolidation Plan

This documents every external data source the system depends on, how its health is
monitored, and the target for consolidating to 1–2 paid subscriptions later. The
core intraday ML features come from **TradingView Pine Script via webhook** — none
of the sources below feed those; they provide *context* (daily bars, options, VIX,
news, fundamentals, calendar, macro).

## Data-flow observability (live)

- **`backend/data_health.py`** — central registry. Every instrumented fetch calls
  `data_health.record(source, ok, category, detail)`.
- **`GET /data/health?secret=gold2026`** — per-source success/failure/freshness;
  `degraded` lists anything failing or stale.
- **Hourly system check** appends a "Data flow — N/M sources degraded" line to the
  Telegram system report when a source breaks.
- Categories + staleness windows: price/options/volatility 180 min, news 30 min,
  fundamentals/calendar/macro 24 h.

Instrumented sources: `stooq_daily`, `alphavantage_intraday`, `cboe_vix`,
`options_chain`, `news_rss_aggregate`, `financialjuice`, `finnhub_news`,
`forexfactory_calendar`, `macro_fred_cot_gld`, `cnn_fear_greed`.

## Inventory by category

| Category | Source | Data | Free/Paid | Notes |
|---|---|---|---|---|
| **Price/OHLCV** | Stooq | daily OHLCV (gold, SPY, QQQ, VIX, DXY, GLD) | Free | primary, cloud-reliable |
| | Alpha Vantage | intraday 60m (SPY/QQQ) | Free ~25/day | budget-guarded |
| | TradingView scanner | live spot | Free | daily-levels GitHub Action |
| **Options** | Tradier | SPX chain/Greeks/IV | Free sandbox (KYC for live) | 15-min delayed |
| | Polygon | SPX chain + real Greeks, flow | Free 15-min; flow paid | `get_expirations` reference endpoint |
| | CBOE | daily Put/Call CSV | Free | egress-allowlist sensitive |
| **Volatility** | CBOE CDN | VIX / VIX3M / VIX9D | Free | primary |
| | Stooq | ^vix / ^vix3m | Free | fallback |
| **News** | Finnhub | forex+general headlines | Free 60/min | primary |
| | FinancialJuice | breaking + RSS | Free (cookie) | fast geopolitical flow |
| | RSS ×6 | Kitco, FXStreet, MarketWatch, Investing, BullionVault, Mining, ForexLive | Free | breadth |
| | ~~NewsAPI~~ | — | **retired** | HTTP 426 from cloud — removed |
| **Fundamentals** | Finnhub | metrics, earnings, analyst revisions, profile | Free | primary |
| | yfinance | statements, insider, institutional, short interest | Free | best-effort, cloud-fragile |
| | SEC EDGAR | Form 4, 8-K guidance | Free | official |
| **Calendar** | Forex Factory | weekly high-impact USD events | Free | GitHub Action writes `data/economic_calendar.json` (cloud egress can't reach FF directly) |
| | Finnhub | economic + earnings calendar | Free | merged/deduped |
| **Macro** | FRED | real yield, dollar, breakeven, nominal | Free (key) | core macro_bias |
| | CFTC COT | gold positioning | Free | confirm |
| | SPDR GLD | tonnes/AUM | Free | confirm |
| | CNN Fear & Greed | cross-asset risk | Free | soft regime gate |
| **Infra** | Anthropic, Telegram, GitHub, Railway | LLM, delivery, persistence, hosting | — | non-market |

**Count: ~22 logical market-data providers across 25 hosts** (excl. infra).

## Consolidation target (when ready to subscribe)

Split along the one hard requirement — **real-time SPX 0DTE options**.

1. **Options + VIX:** `marketdata.app` (~$49/mo real-time SPX options chain + Greeks)
   — cheapest real-time-0DTE option. Keep **Stooq (free)** for daily OHLCV.
   → retires Tradier, Polygon-free, CBOE-for-VIX, yfinance options fallback.
2. **Fundamentals + Earnings + Calendar + News:** one vendor — EODHD or FMP
   (~$20–80/mo) consolidates yfinance fundamentals, the RSS feeds, Forex Factory,
   and Finnhub-premium bits.

**Keep free/official (no worthwhile paid equivalent):** FRED, CFTC COT, SPDR GLD,
CNN Fear & Greed, SEC EDGAR. **Keep:** TradingView Pine (intraday features).

### Field-requirement checklist (for the future gap-check)

Tick these against any candidate vendor before paying:

- **Options:** chain by expiry · strike · bid/ask · lastPrice · impliedVolatility ·
  delta · openInterest · **0DTE same-day expiries** · real-time (≤ a few min)
- **Volatility:** VIX, VIX3M, VIX9D daily close (term structure + backwardation)
- **Price:** daily OHLCV for XAUUSD(GC=F), SPY, QQQ, SPX, DXY, GLD; intraday 60m SPY/QQQ
- **Fundamentals:** P/E, P/B, P/S, EV/EBITDA, ROE, ROA, revenue growth, gross/net
  margin, debt/equity, dividend yield, beta, sector/industry, market cap
- **Earnings:** next date, EPS estimate/actual, surprise %, analyst recommendation
  trend (revisions)
- **Calendar:** high-impact US events (NFP, CPI, FOMC, PCE, GDP) with date/time +
  forecast/previous, ≥1 week forward
- **News:** market/forex headlines with timestamp + source, low latency from cloud IPs
- **Macro (keep free):** DFII10, DTWEXBGS, T10YIE, DGS10 (FRED); COT gold; GLD flows
