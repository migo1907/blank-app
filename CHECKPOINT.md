# Checkpoint v3 — Stable Rollback Point
**Tag:** `checkpoint-v3`
**Commit:** `ad5b7c2293b559f6a87a76b87e72a4bc615b311d`
**Branch:** `claude/hopeful-pasteur-VVHCl`
**Date:** 2026-06-14
**CI:** Backend CI run #116 — `conclusion: success` ✅

> This is the current rollback point. If anything breaks, restore to this tag (see bottom).

---

## What's New Since checkpoint-v2 (`42312b0`, 2026-06-04)

### Intraday brain (core ML signal engine)
- **F26 redefined** — was normalised Stochastic %K, which was mathematically
  identical to `−F6` (Williams %R), r = −1.0, zero added information. Now the
  **Stochastic %K−%D momentum delta** — orthogonal to F6. Pine + backend at 26 features.
  Clean Pine source: `pine_script_backup/migo_sniper_f26.pine`.
- **Phase 2 layers built (ahead of schedule):**
  - 2A Gaussian HMM regime model (`regime_model.py`) — probabilistic TRENDING/RANGING/VOLATILE
  - 2B Multi-timeframe confluence (`mtf_confluence.py`) — 1H+4H+1D, backend-side, no Pine change
  - 2D News intelligence — Finnhub economic calendar + post-event volatility scoring (`post_event.py`)
- **Market macro intelligence** (`market_macro.py`) — FRED real yield/dollar/breakeven +
  CFTC COT + GLD flows, folded into gold signals at weight 0.20.
- LightGBM live in production since 2026-06-11.

### Swing brain (separate stock system)
- Archetype-aware fundamental scoring — 13 business-model buckets (`fundamental_data.py`)
- Advanced composites — Piotroski F, Altman Z, Rule-of-40, PEG, FCF yield, ROE/ROA, P/B
- Earnings-call monitor (`earnings_call.py`) — Finnhub calendar + SEC EDGAR 8-K guidance
- EDGAR Form-4 insider counts (CIK-based)
- Haiku institutional thesis (`swing_narrative.py`)
- Paper-trade engine (`swing_tracker.py`) — the ML training-data source
- **Telegram SILENT during training phase** — nightly scan paper-trades quietly; re-enable
  at ≥50 closed swing trades (uncomment 2 lines in `scheduler.py` ~L1647)

---

## ML Architecture
- AdaptiveKNN (26 features, Lorentzian distance) — pool-aware, one model per pool
- RandomForest + GradientBoosting + LightGBM — pool-aware ensembles
- Joint models (joint_gold, joint_stocks) cover pools awaiting 50+ trades
- TimeSeriesSplit calibration CV (no look-ahead bias), MIN_TRADES 30

## Pools (as of 2026-06-11 live counts, data branch)
| Pool | Trades | Status |
|------|--------|--------|
| XAUUSD_2M | 386 | ✅ target hit, 52% WR last 50 |
| XAUUSD (legacy) | 109 | 🟢 near target |
| XAUUSD_5M | 105 | 🟢 on track |
| XAUUSD_30M | 11 | 🔵 thin — needs replay |
| XAUUSD_1H | 2 | 🔵 thin — needs replay |
| STOCKS_MOMENTUM_15M/30M | 84 / 53 | ✅ target hit |
| STOCKS_QUALITY_15M/30M | 40 / 25 | 🟢/🔵 building |
| STOCKS_*_4H, SPX500, QQQ pools | 1–8 each | 🔵 building |

## Scheduler (5 jobs)
- Signal every 15 min, breaking news every 2 min, system check every 60 min,
  macro refresh every 60 min, daily brief at 08:00 UTC
- Swing: nightly screen 16:30 ET + manage 16:45 ET (paper-trade, silent)

## Infrastructure
- Railway (Railpack builder, `bash start.sh` custom start command for libgomp/LightGBM)
- GitHub `data` branch as persistence layer
- Env keys live: GITHUB_TOKEN, TELEGRAM_*, WEBHOOK_SECRET, FRED_API_KEY, FINNHUB_KEY,
  ANTHROPIC_API_KEY. Added today: Alpha Vantage (not yet wired — for Phase 2C options layer).

---

## How to Restore This Checkpoint
```bash
# Inspect / restore the exact tree
git checkout checkpoint-v3
# or by commit
git checkout ad5b7c2293b559f6a87a76b87e72a4bc615b311d
```
On Railway: redeploy from commit `ad5b7c229` via the Railway dashboard.

## Checkpoint Lineage
- `checkpoint-v1` — `903adc2b` (2026-06-04) — 25-feature stable baseline
- `checkpoint-v2` — `42312b0`  (2026-06-04) — 25-feature pipeline complete, TVC:GOLD
- `checkpoint-v3` — `ad5b7c22` (2026-06-14) — 26 features (F26 fixed), Phase 2 layers,
  macro intelligence, swing brain, LightGBM live ← **current rollback point**

## Next Checkpoint Trigger
User will call for v4 when the next clear milestone is reached (e.g. thin pools at target,
swing ML ensemble wired, or Phase 2C options layer Stage A complete).
