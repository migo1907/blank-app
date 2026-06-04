# Migo Sniper Pro — ML Backend

## Railway Deployment
- **URL**: https://blank-app-production-a8bd.up.railway.app
- **Branch**: `claude/hopeful-pasteur-VVHCl` (Railway watches this branch, NOT main)
- **Webhook secret**: `gold2026`

## Key Endpoints
- `/health` — service health check
- `/daily-brief?secret=gold2026` — trigger daily market brief immediately
- `/signal/now?secret=gold2026` — trigger news signal cycle
- `/webhook` — unified TradingView webhook (POST)
- `/dashboard?secret=gold2026` — model stats
- `/weights?secret=gold2026` — current feature weights

## Architecture
- FastAPI + APScheduler (4 cron jobs)
- ML: Adaptive KNN (`ml_model.py`) + RandomForest + GBM ensemble (`ml_ensemble.py`)
- 25 features (F1–F25)
- Data persistence: GitHub `data` branch via `db.py`
- News: FinancialJuice RSS + breaking news + NewsAPI
- Daily brief: XAUUSD from TradingView (`tvdatafeed`, ICMARKETS:XAUUSD), SPY/QQQ from yfinance

## Scheduler Jobs
1. `news_signal_cycle` — every 15 min
2. `breaking_news_cycle` — every 2 min
3. `hourly_system_check` — every hour
4. `daily_market_brief` — 08:00 UTC weekdays

## Telegram
- Signals → `TELEGRAM_CHAT_ID`
- Critical alerts only → personal chat `966897595`
- No error messages to Telegram (Railway console only)

## Critical Rules
- `get_rf()` and `get_gbm()` take ZERO arguments (global singletons)
- `get_model(pool)` takes a pool argument
- Never push to `main` branch for Railway — always push to `claude/hopeful-pasteur-VVHCl`
