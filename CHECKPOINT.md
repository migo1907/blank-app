# Checkpoint v1 — Stable Baseline
**Commit:** `903adc2b3e2f6983376ebdd3ed74994859623d1c`
**Date:** 2026-06-04

## System State at This Checkpoint

### ML Architecture
- AdaptiveKNN (25 features, Lorentzian distance) — pool-aware, one model per pool
- RandomForest + GradientBoosting — pool-aware, each pool trains its own ensemble
- 4-model vote: KNN + RF + GBM + News sentiment
- Transfer learning: new pools start from XAUUSD baseline weights

### Pools
| Pool | Trades | W/L | WR |
|------|--------|-----|----|
| XAUUSD (legacy) | 125 | 52/73 | 41.6% |
| XAUUSD_2M | 43 | 17/26 | 39.5% |
| XAUUSD_5M | 16 | 4/12 | 25.0% |
| STOCKS_MOMENTUM_30M | 5 | 1/4 | 20% |
| STOCKS_MOMENTUM_4H | 5 | 0/5 | 0% |
| STOCKS_QUALITY_30M | 1 | 0/1 | 0% |
| STOCKS_QUALITY_4H | 2 | 0/2 | 0% |
| STOCKS_INDEX_30M/4H | 0 | — | — |

### Signal Engine
- Session multipliers (London/NY/Asian/NYSE hours)
- Regime detection (TRENDING/RANGING/VOLATILE)
- Feature confluence scoring (25 features)
- Trade clustering prevention
- News velocity gate (CONFLICTED = no signal)
- Day-of-week penalty (Mon/Fri)

### Scheduler
- XAUUSD signal every 15 min
- SPY signal every 15 min (NYSE hours only)
- FJ breaking news every 2 min with auto-login on session expiry
- Scheduler watchdog in /health (auto-restart if died)
- 90s timeout on news cycle (prevents APScheduler job lock)

### Infrastructure
- Railway deployment
- GitHub `data` branch as persistence layer
- UptimeRobot + GitHub Actions keepalive
- FJ auto-login with FJ_EMAIL + FJ_PASSWORD

## How to Restore This Checkpoint
```bash
git checkout 903adc2b3e2f6983376ebdd3ed74994859623d1c
```
Or on Railway: redeploy from this specific commit via the Railway dashboard.

## Next Checkpoint Trigger
User will call for update when next clear milestone is reached.
