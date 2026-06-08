# blank-app — Claude Code Notes

## Railway
- **Production URL:** https://blank-app-production-a8bd.up.railway.app
- **Health:** https://blank-app-production-a8bd.up.railway.app/health
- **Daily brief:** https://blank-app-production-a8bd.up.railway.app/daily-brief?secret=gold2026
- **Signal now:** https://blank-app-production-a8bd.up.railway.app/signal/now?secret=gold2026
- **Project ID:** bcc5442d-2f19-4dfa-ad25-219a5c70868a
- **Service ID:** e4310b2b-3a37-440e-a3b7-a14ea476f8a1

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
- **Known gap:** No `isTF30` bucket — 30M chart uses 1H/4H ATR multipliers (too wide). See TODO.


- [ ] Pine Script: add `isTF30` bucket — 30M chart currently falls through to 1H/4H ATR multipliers (too wide TP/SL for 30M). Add dedicated 30M values to all multiplier chains. Backend ready — Pine Script only change.


- FastAPI backend on Railway (Python 3.13)
- Scheduler: 4 jobs — signal every 15min, breaking news every 2min, system check every 60min, daily brief at 08:00 UTC
- ML: AdaptiveKNN + RandomForest + GradientBoosting, pool-aware (9 pools)
- `get_rf(pool)` and `get_gbm(pool)` always take a pool argument
- Features: 25 features (F1-F25), all computed in Pine Script and sent via webhook
- XAUUSD data: TVC:GOLD scanner (spot, ~$1-3 from ICMARKETS) + GC=F prev day H/L/C → pivot levels
- Daily levels written to `data/daily_levels.json` by GitHub Actions (07:50 UTC Mon-Fri), fetched at runtime from GitHub raw URL
