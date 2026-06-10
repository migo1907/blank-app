# blank-app — Claude Code Notes

## Railway
- **Production URL:** https://blank-app-production-a8bd.up.railway.app
- **Health:** https://blank-app-production-a8bd.up.railway.app/health
- **Daily brief:** https://blank-app-production-a8bd.up.railway.app/daily-brief?secret=gold2026
- **Signal now:** https://blank-app-production-a8bd.up.railway.app/signal/now?secret=gold2026
- **Project ID:** bcc5442d-2f19-4dfa-ad25-219a5c70868a
- **Service ID:** e4310b2b-3a37-440e-a3b7-a14ea476f8a1

## Non-Negotiable Rules
These are permanent agreements — never override, skip, or work around them under any circumstance:

1. **CI must be green before any push is reported as done.** After every `git push`, wait for the Backend CI run on that exact commit SHA to complete with `conclusion: success`. Do not tell the user the work is done until that green line is confirmed. If CI fails, fix it before reporting.
2. **Never push to `main`.**
3. **Credentials (tokens, passwords, secrets) stay in Railway env only — never committed to the repo.**

---

## Git
- **Development branch:** `claude/hopeful-pasteur-VVHCl`
- **DATA branch:** `data` — ALL live trade history, weights, signals, news cache, feature cache are written here by Railway at runtime (db.py GITHUB_BRANCH="data"). ALWAYS check the `data` branch for trade counts, not the dev branch.
- **Never push to:** `main`
- **Stable baseline tag:** `checkpoint-v1` (05:54 UTC 2026-06-04)
- **checkpoint-v2 commit:** `42312b0` (2026-06-04) — 25-feature pipeline complete, F1-F25 from Pine Script, TVC:GOLD data source, pools aligned to live alerts (XAUUSD 2M/5M/30M/1H + stocks 30M/4H), weights.json default, 25 live XAUUSD trades

## Security
- Webhook secret: `gold2026`
- Personal Telegram chat ID: `966897595` (critical alerts only)
- No Telegram for errors — Railway console only

## Pine Script
- **Current version:** `f25 Migo VS Market Sniper Pro` (Pine Script v6)
- **Sends to:** `/webhook` unified endpoint (single alert URL for all payload types)
- **Payload types:** HEARTBEAT (every bar close), entry signal, TP1_HIT, TP2_HIT, WIN, PARTIAL, LOSS
- **Timeframe format:** `timeframe.period` — always numeric strings: `"2"`,`"5"`,`"15"`,`"30"`,`"60"`,`"240"`
- **Symbol format:** `syminfo.ticker` — bare ticker, no exchange prefix
- **Features:** F1–F25 sent in outcome and heartbeat payloads; entry payload has no features (uses heartbeat cache)
- **Outcome normalization:** TP1_HIT/TP2_HIT → PROGRESS (no DB write), WIN/LOSS/PARTIAL → closed trade
- **Pine Script backup (raw):** `https://raw.githubusercontent.com/migo1907/blank-app/data/pine_script_backup/migo_sniper_ml_v3.pine`
- **isTF30 bucket:** ✅ implemented 2026-06-08 — 30M now has dedicated ATR multipliers (TP1×2.2, TP2×3.8, TP3×6.0, SL×2.2, trail×1.0)


- FastAPI backend on Railway (Python 3.13)
- Scheduler: 5 jobs — signal every 15min, breaking news every 2min, system check every 60min, macro refresh every 60min, daily brief at 08:00 UTC
- ML: AdaptiveKNN + RandomForest + GradientBoosting, pool-aware (9 pools)
- `get_rf(pool)` and `get_gbm(pool)` always take a pool argument
- Features: 25 features (F1-F25), all computed in Pine Script and sent via webhook
- **Phase 2 — F26:** Stochastic (%K/%D) — requires Pine Script update + backend `Features` dataclass expansion to 26 fields
- XAUUSD data: TVC:GOLD scanner (spot, ~$1-3 from ICMARKETS) + GC=F prev day H/L/C → pivot levels
- Daily levels written to `data/daily_levels.json` by GitHub Actions (07:50 UTC Mon-Fri), fetched at runtime from GitHub raw URL

## Market Macro Intelligence (`market_macro.py`)
- Fills gold's real macro-driver blind spots beyond headline sentiment. Refreshed hourly, persisted to `data/market_macro.json`, loaded on startup.
- **Sources (all free):** FRED API (real yield `DFII10`, dollar `DTWEXBGS`, breakeven `T10YIE`, nominal `DGS10`) + CFTC COT (gold `088691`, no auth) + SPDR GLD CSV (tonnes/AUM, no auth)
- **`macro_bias`** ∈ [-1,+1]: positive = bullish gold. Rising real yields/dollar = bearish; rising breakeven/GLD tonnes = bullish. Real yield + dollar lead; COT + GLD confirm.
- Folded into `generate_signal` combined_score at weight 0.20 (gold only, stocks ignore). Surfaced in `health.json` (`macro_bias`, `macro_label`).
- **Required env keys (set in Railway):** `FRED_API_KEY` (free, fred.stlouisfed.org), `FINNHUB_KEY` (free, finnhub.io). Graceful no-op if absent.

## News sources
- **Replaced NewsAPI** (free tier returns HTTP 426 from cloud servers + 24h delay — unusable on Railway) with **Finnhub** news (forex+general, 60 req/min, cloud-friendly). NewsAPI kept as legacy fallback only if `FINNHUB_KEY` unset.
- **Scheduled-event awareness:** Finnhub economic calendar gives forward NFP/CPI/FOMC warning (imminent = high-impact within 90min) — de-risk BEFORE the print, not after keyword detection.
- **FXStreet RSS:** now uses realistic browser User-Agent + Accept headers to bypass Cloudflare 403.
- RSS feeds: FinancialJuice (primary), Kitco, MarketWatch, Investing.com, BullionVault, Mining.com, FXStreet, ForexLive
