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
- **Never push to:** `main`
- **Stable baseline tag:** `checkpoint-v1` (05:54 UTC 2026-06-04)

## Security
- Webhook secret: `gold2026`
- Personal Telegram chat ID: `966897595` (critical alerts only)
- No Telegram for errors — Railway console only

## Architecture
- FastAPI backend on Railway (Python 3.13)
- Scheduler: 4 jobs — signal every 15min, breaking news every 2min, system check every 60min, daily brief at 08:00 UTC
- ML: AdaptiveKNN + RandomForest + GradientBoosting, pool-aware (9 pools)
- `get_rf(pool)` and `get_gbm(pool)` always take a pool argument
- Features: 25 features (F1-F25); F25 = time-of-day sine, computed server-side (not from webhook)
- XAUUSD data: TVC:GOLD scanner (spot, ~$1-3 from ICMARKETS) + GC=F prev day H/L/C → pivot levels
- Daily levels written to `data/daily_levels.json` by GitHub Actions (07:50 UTC Mon-Fri), fetched at runtime from GitHub raw URL
