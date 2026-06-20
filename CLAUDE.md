# blank-app — Claude Code Notes

## Roadmap

### Phase 1 — Foundation ✅ Complete
- 26-feature pipeline (F1–F26), Pine Script v6, unified webhook
- AdaptiveKNN + RandomForest + GradientBoosting + LightGBM (joint_gold + joint_stocks)
- HMM regime detection, MTF confluence, macro intelligence (FRED + COT + GLD)
- Pool architecture: 9 pools × up to 4 timeframes
- Daily market brief (09:00 UTC), swing brain (fundamental + technical screener)
- Swing paper-trade tracker (training data pipeline for future swing ML)

### Phase 2 — Intelligence Layers ✅ Complete
- F26 Stochastic (%K/%D) added to Pine Script + backend
- Swing addon: fundamental_data (archetype-aware), earnings_call monitor, swing_narrative (Haiku prose)
- Adaptive Pine Script (ai_mlm_26.pine) seeded from backend weights (52W/73L baseline)
- Post-event volatility state, equity macro (VIX + yield curve)
- checkpoint-v3 tag (SHA 9dae7bdec)

### Phase 3 — Calibration & Quality ✅ Complete (2026-06-19)
- **Isotonic calibration** ✅ — RF + GBM: `IsotonicRegression` fitted on last-20% OOS fold, stacked on top of existing Platt sigmoid. Applied at inference via `_iso_calibrator`. Activates at n≥150. Eligible pools at deploy: XAUUSD_2M (~1,156), XAUUSD_5M (~356), STOCKS_MOMENTUM_15M (~349), STOCKS_QUALITY_15M (~206), STOCKS_MOMENTUM_30M (~175), STOCKS_QUALITY_30M (~118).
- **Walk-forward OOS validation** ✅ — Last 20% held out before each retrain; honest OOS accuracy logged every cycle (e.g. `[rf] Walk-forward OOS accuracy (231 trades): 0.573`).
- **Mean reversion levels in morning brief** ✅ — 20MA/50MA/200MA distances computed in `_technical_context()`, surfaced as `🔁 Reversion:` line per asset. Event calendar still at brief bottom.
- **Swing ML ensemble** ⏳ — Waiting on ≥50 closed swing paper trades. Auto-enables. Uncomment 2 lines in scheduler.py ~L1668-1669 when ready.

### Phase 4 — Dashboard & Intelligence ✅ Partially Complete (2026-06-20)

#### PWA Dashboard ✅ Complete
- **14-tab React PWA** served from `/app/` on Railway — phone-installable
- Tabs: Markets · Brief · Pulse · Signals · ML · Swing · Macro · News · Portfolio · Watchlist · Research · Compare · Wrap-Up · Options
- Live P&L portfolio tracker (localStorage, 30s refresh)
- Watchlist with live prices (localStorage, 30s refresh)
- Ticker research: fundamentals + news for any symbol
- Side-by-side compare up to 6 tickers
- AI market wrap-up (Claude Haiku, cached daily)
- AI 3-sentence market commentary on Markets tab
- Options tab: VIX, ATM IV, P/C ratio, paper positions, flow table

#### Options ML v2 ✅ Complete (2026-06-20)
- **Features: 18 → 25** — added vix9d_ratio, hour_dte_interaction, hv5_vs_iv, spx_intraday_range_pct, regime_encoded, opex_week, skew_25d
- **Ensemble: RF+GBM → RF+GBM+LightGBM** (3-model average)
- **Calibration stack:** Platt sigmoid per model → isotonic on OOS ensemble average
- **Focal loss** sample weights — downweights spread/slippage stops, upweights uncertain edge cases
- **SHAP explanations** — top 3 feature drivers shown per trade in Telegram + ledger
- **Conformal prediction interval** — 80% coverage band; wide_uncertainty flag (>0.30) triggers half-size warning
- **VIX9D** now fetched alongside VIX/VIX3M in `get_vix_context()`

#### Options Strategies ✅ Complete (2026-06-20)
- **Long option** (existing) — both timeframes agree, TP +100%, SL -50%
- **Debit spread** (NEW) — one timeframe agrees, buy near-ATM sell further OTM, TP +80% net debit, SL -50%
- **Straddle** (NEW) — conflicting signals but big move expected, ATM call+put, TP +60% either leg, SL -40%, 0DTE only before 13:00 ET

#### Polygon.io Integration ✅ Complete (2026-06-20)
- `backend/polygon_data.py` — REST client with graceful fallback when key absent
- Priority chain for SPX chain: Tradier → Polygon → yfinance
- P/C ratio: tries Polygon snapshots, falls back to yfinance SPX chain volume
- Free-tier backtest script: `backend/polygon_backtest.py` — uses `/v3/reference/options/contracts` + `/v2/aggs/` (no paid tier needed)
- Note: `/v3/snapshot/options/` (real-time flow) returns 403 on free tier — needs paid Polygon plan (~$29/mo Starter) to unlock live flow

### Phase 5 — Improvements Backlog (To-Do, No Timeline)

#### ML Methods — Intraday (Gold + Stocks)
- **Conformal prediction** — calibrated uncertainty interval per signal instead of a single probability. Flags wide-uncertainty signals to avoid oversizing. ~10 lines on top of existing models. Low effort, medium lift. *(Done for options — replicate for intraday pools)*
- **Label noise correction** — use joint LightGBM confidence as a label quality weight; downweight low-confidence LOSS labels (likely stopped by spread/slippage, not wrong direction). Expected 2–5pp accuracy lift.
- **Regime-conditional retraining** — separate RF/GBM model per HMM regime (trending vs ranging), route inference through current regime. Medium effort. Wait until pools have more history.

#### ML Methods — Options (SPX 0-1DTE)
- ✅ ~~VIX9D term structure feature~~ — done 2026-06-20
- ✅ ~~Put/call skew feature~~ — done 2026-06-20 (`skew_25d`)
- ✅ ~~Hour × DTE interaction feature~~ — done 2026-06-20 (`hour_dte_interaction`)
- **CBOE daily put/call ratio** — free daily download, strong next-day sentiment signal. Low effort.
- **Scaling exits** — take 50% off at +50% gain, let rest ride. Better real-world expectancy. Add after 50+ closed trades to analyse exit patterns first.
- **Iron condor** — sell both sides in RANGING regime + VIX <15. Requires selling premium — add only after paper long-option edge is confirmed.

#### ML Methods — Swing
- **Analyst revision momentum** — Finnhub `/stock/recommendation` (free, existing key). EPS estimate revisions over 30/60/90 days is one of the most consistent swing predictors. Low effort, medium lift.
- **Relative volume** — current volume vs 20-day average at entry. Breakouts on low relative volume fail 70%+ of the time. Computable from yfinance history. Low effort.
- **Sector rotation rate-of-change** — rate of change of XL* ETF relative strength, not just the level. Catches rotation earlier. Medium effort.
- **Short interest** — FINRA bi-monthly data (free, no auth). High short + positive catalyst = squeeze setup. Medium effort.

#### Architecture
- **Half-Kelly position sizing output** — use calibrated win probability (now properly isotonic-calibrated) to compute Kelly fraction, capped at 0.5× for safety. Completes the signal from direction+confidence → direction+confidence+size. Medium effort. Most valuable when live capital is deployed.
- **Concurrent signal correlation filter** — if two stock pools fire simultaneously on correlated names (correlation > 0.7), block the second signal. Prevents counting one move as two independent signals. Medium effort.
- **Fear & Greed Index** (CNN) — free JSON endpoint, updates daily. Single cross-asset risk appetite number. Use as a soft regime gate across all three sections. Low effort.
- **DXY 15-min proxy via UUP ETF** — add UUP to TradingView heartbeat for faster dollar signal on gold. Current macro refresh is hourly; correlation with gold is near-instant. Low effort.

#### Priority Order (what to pick up next)
| Priority | Item | Effort | Condition to start |
|----------|------|--------|--------------------|
| 1 | CBOE daily P/C ratio (options) | Low | Any time |
| 2 | Analyst revision momentum (swing) | Low | Any time |
| 3 | Relative volume (swing) | Low | Any time |
| 4 | Fear & Greed Index (all sections) | Low | Any time |
| 5 | Conformal prediction for intraday pools | Low | Any time — clone from options |
| 6 | Label noise correction (intraday) | Medium | When XAUUSD_2M OOS acc stabilises |
| 7 | Scaling exits (options) | Low | After 50+ closed options trades |
| 8 | Half-Kelly sizing | Medium | When live capital deployed |
| 9 | Regime-conditional retraining | Medium | After pools reach 300+ trades each |
| 10 | Correlation filter | Medium | When 3+ stock pools fire concurrently |
| 11 | Iron condor strategy | Medium | After paper long-option edge confirmed |
| 12 | Polygon paid tier (live options flow) | External | If Polygon plan upgraded |

---

### Phase 2C — SPX 0-1DTE Options Layer (Data Collection — Silent)
- **Status:** Running silently — paper trades logged to `data/options_paper_SPX.json` on data branch. No Telegram until ≥50 closed trades per pool (auto-unlocks).
- **Trigger:** STOCKS_SPX500_15M (0DTE, before 13:00 ET, conf≥0.60) or STOCKS_SPX500_30M (1DTE, after 13:00 ET, conf≥0.55) directional flip fires `build_spx_recommendation()`.
- **Strike selection:** Δ0.25 target (OTM), Black-Scholes picker, yfinance `^SPX` chain.
- **Hard rules:** IV Rank <50, no VIX backwardation, no entries 24h before FOMC/CPI/NFP, 0DTE cutoff 13:00 ET (→ rolls to 1DTE).
- **Exits:** +100% premium (TP), -50% premium (SL), hard exit 15:30 ET (0DTE) / 14:00 ET next session (1DTE). Managed hourly by `_options_paper_manage_cycle`.
- **IV history:** ATM IV recorded daily at 15:45 ET → `data/options_iv_history.json`. IV Rank unlocks after 20 sessions, meaningful at 60.
- **Training features (25):** confidence, iv, iv_rank, vix, vix_ratio, vix_backwardation_margin, vix9d_ratio, delta, entry_premium, spot_vs_strike_pct, premium_vs_em_pct, iv_over_vix_ratio, dte, hour_et, day_of_week, entry_time_norm, time_to_hard_exit_hours, hour_dte_interaction, expected_move, pool_confluence, spx_intraday_range_pct, hv5_vs_iv, regime_encoded, opex_week, skew_25d.
- **Loss categorization:** WRONG_DIRECTION / THETA_DECAY / IV_CRUSH / OVERPAID / LATE_ENTRY / WIN — tagged at close in `manage_paper_positions()`.
- **ML gate:** RF(200)+GBM(150)+LGB(200) ensemble, Platt sigmoid per model → isotonic calibration on OOS ensemble. Focal-loss weights + SHAP explanations + conformal prediction interval. `_ML_SCORE_GATE = 0.52` activates at ≥50 closed trades. Auto-retrains after every close.
- **Strategies (all paper):** long_option (both TFs agree, TP+100% SL-50%), debit_spread (one TF agrees, TP+80% net debit), straddle (conflicting signals, TP+60% either leg, 0DTE only).
- **Weekly autopsy:** Monday 17:00 ET → personal Telegram via `send_critical_alert()`.
- **Pools:** `SPX_0DTE` (entered before 13:00 ET) / `SPX_1DTE` (after 13:00 ET or explicit roll).
- **Training readiness:** `GET /options/trades?secret=gold2026` — shows n_closed, win_rate, ready flag per pool.
- **Files:** `backend/options_engine.py` (core), `backend/tradier_data.py` (data provider).
- **Never suggest Tradier as a quick action** — requires full KYC brokerage onboarding. yfinance is the fallback and is sufficient.



## Railway
- **Production URL:** https://blank-app-production-a8bd.up.railway.app
- **Health:** https://blank-app-production-a8bd.up.railway.app/health
- **Daily brief:** https://blank-app-production-a8bd.up.railway.app/daily-brief?secret=gold2026
- **Signal now:** https://blank-app-production-a8bd.up.railway.app/signal/now?secret=gold2026
- **Project ID:** bcc5442d-2f19-4dfa-ad25-219a5c70868a
- **Service ID:** e4310b2b-3a37-440e-a3b7-a14ea476f8a1

## Railway Deployment — CRITICAL knowledge (2026-06-11)
- **Builder is Railpack, NOT Nixpacks** — `backend/nixpacks.toml` is IGNORED. Do not edit it expecting changes.
- Forcing Nixpacks via railway.toml fails (nix gfortran-wrapper collision). Don't retry.
- **Custom Start Command (Railway UI, Deploy section): `bash start.sh`** — stages sklearn's vendored libgomp as `/tmp/libs/libgomp.so.1` + sets LD_LIBRARY_PATH, then execs uvicorn. This is what makes LightGBM work (Railpack runtime image has no system libgomp).
- Custom Build Command must stay EMPTY (apt-get not available; putting start.sh there crashes the build — no $PORT at build time).
- `RAILWAY_API_TOKEN` is set in Railway Variables (backend hourly check uses it).
- ✅ LightGBM working in production since 2026-06-11 16:10 UTC (joint_gold 516 trades, joint_stocks 276 trades).

## Non-Negotiable Rules
These are permanent agreements — never override, skip, or work around them under any circumstance:

1. **CI must be green before any push is reported as done.** After every `git push`, wait for the Backend CI run on that exact commit SHA to complete with `conclusion: success`. Do not tell the user the work is done until that green line is confirmed. If CI fails, fix it before reporting.
2. **Never push to `main`.**
3. **Credentials (tokens, passwords, secrets) stay in Railway env only — never committed to the repo.**
4. **Self-awareness, learning from mistakes, continuous improvement — always.** Check the simplest, most obvious explanation FIRST (market closed? weekend? holiday? wrong time?) before reaching for a complex one. State assumptions out loud so they can be challenged. Do not propose or make fixes on incomplete context — verify the real cause first (e.g., validate on a live trading day, not weekend data). When a mistake is caught, own it specifically, extract the lesson, and apply it going forward. Hold yourself to the same standard the system is built on (mistake ledger + weekly autopsy).
5. **Pine Script backup sync — always.** Any change touching F-numbers, feature formulas, or webhook payload fields must update `data/pine_script_backup/migo_sniper_ml_v3.pine` on the `data` branch in the same push. Never let the backup drift from production.
6. **Trade history analysis — never use WebFetch agents.** WebFetch truncates large JSON files and returns wrong counts/timestamps. Always use `mcp__github__get_file_contents` + local Python/regex to parse trade data. For files >100KB, parse the saved tool-result file with Python regex directly.
7. **APScheduler has no persistent state across Railway restarts.** `misfire_grace_time` only helps while the scheduler is running — it does NOT catch jobs missed during a cold restart. Startup catch-up logic in `start_scheduler()` handles this (scheduler.py). If a scheduled job is missed, trigger it manually via its `/endpoint?secret=gold2026` URL. Manual endpoints: `/daily-brief`, `/daily-report`, `/signal/now`, `/swing/now`.
8. **Thin-pool cold-start deadlock.** Pools with <50 trades return KNN confidence=0 → NEUTRAL → no entries stored → pool never grows. Signal engine bypasses both the CONFLICTED gate and the min_conf threshold for _n<50 (signal_engine.py). Do NOT re-add those gates for thin pools. The bypass self-deactivates at 50 trades.

---

## Known Pool Architecture
- **STOCKS_INDEX** = SPY only → pools: STOCKS_INDEX_15M / 30M / 4H
- **STOCKS_SPX500** = SPX500, SP500, US500 → pools: STOCKS_SPX500_15M / 30M / 4H
- **STOCKS_QQQ** = QQQ only → pools: STOCKS_QQQ_15M / 30M / 4H
- **STOCKS_MOMENTUM / QUALITY** = individual stock tickers (AAPL, MSFT, ADBE, META, etc.)
- **Pool silence diagnosis:** check `data/feature_cache.json` on data branch first — if timestamp is fresh, charts ARE sending heartbeats (not a TradingView issue). Then check `data/signals.json` for direction=NEUTRAL pattern. If all signals for a pool are NEUTRAL with conf=0.0, it is the thin-pool deadlock (rule 8 above).
- **Trade data ground truth:** always read from `data` branch, not dev branch. Use `mcp__github__get_file_contents` + Python regex for counts and last-trade timestamps.

---

## Git
- **Development branch:** `claude/hopeful-pasteur-VVHCl`
- **DATA branch:** `data` — ALL live trade history, weights, signals, news cache, feature cache are written here by Railway at runtime (db.py GITHUB_BRANCH="data"). ALWAYS check the `data` branch for trade counts, not the dev branch.
- **Never push to:** `main`
- **Checkpoint commits (tags blocked by proxy — commits only):**
  - `checkpoint-v1` → `903adc2b` (2026-06-04) — 25-feature stable baseline
  - `checkpoint-v2` → `42312b0`  (2026-06-04) — 25-feature pipeline complete, F1-F25, TVC:GOLD, pools aligned, weights.json
  - `checkpoint-v3` → `9dae7bdec` (2026-06-14) — 26 features (F26 fixed), Phase 2 layers, macro intelligence, swing brain, LightGBM ← **current rollback point** (also GitHub branch `checkpoint-v3`)
- **Tag push is permanently blocked** (git proxy returns 403 on `refs/tags/*`). Use `git checkout <SHA>` to restore, or GitHub branch `checkpoint-v3` for v3. Do NOT attempt `git push --tags` — it will always fail.

## Security
- Webhook secret: `gold2026`
- Personal Telegram chat ID: `966897595` (critical alerts only)
- No Telegram for errors — Railway console only

## AI MLM 26 — Read-Only Indicator (separate from production)
- **File:** `pine_script_backup/ai_mlm_26.pine`
- **Purpose:** visual-only ML signal quality mirror for TradingView — NO alerts, NO webhook, NO heartbeat. Shows BUY/SELL labels with Entry/TP1/TP2/TP3/SL on chart + dashboard table (ML BULL/BEAR %, tier, win rate, regime, session, MTF, DXY).
- **Update cadence:** updated by Claude approximately weekly as ML training progresses (new weights, win rate data, feature improvements). User pastes the new version into TradingView manually — 30-second copy-paste, no alerts to re-create.
- **How to update TradingView:** copy raw contents from `pine_script_backup/ai_mlm_26.pine` on the dev branch → Pine Script Editor → paste over old version → Save. No other action needed.
- **Raw URL:** `https://raw.githubusercontent.com/migo1907/blank-app/claude/hopeful-pasteur-VVHCl/pine_script_backup/ai_mlm_26.pine`

## Pine Script
- **Current version:** `f26 Migo VS Market Sniper Pro` (Pine Script v6)
- **Sends to:** `/webhook` unified endpoint (single alert URL for all payload types)
- **Payload types:** HEARTBEAT (every bar close), entry signal, TP1_HIT, TP2_HIT, WIN, PARTIAL, LOSS
- **Timeframe format:** `timeframe.period` — always numeric strings: `"2"`,`"5"`,`"15"`,`"30"`,`"60"`,`"240"`
- **Symbol format:** `syminfo.ticker` — bare ticker, no exchange prefix
- **Features:** F1–F25 sent in outcome and heartbeat payloads; entry payload has no features (uses heartbeat cache)
- **Outcome normalization:** TP1_HIT/TP2_HIT → PROGRESS (no DB write), WIN/LOSS/PARTIAL → closed trade
- **Pine Script backup (raw):** `https://raw.githubusercontent.com/migo1907/blank-app/data/pine_script_backup/migo_sniper_ml_v3.pine`
- **isTF30 bucket:** ✅ implemented 2026-06-08 — 30M now has dedicated ATR multipliers (TP1×2.2, TP2×3.8, TP3×6.0, SL×2.2, trail×1.0)


## Daily Market Brief — Permanent Specification
- **Schedule:** 09:00 UTC every weekday = **1:00 PM Dubai (UTC+4)**. Never change this without updating CLAUDE.md and scheduler.py together.
- **Manual trigger:** `GET /daily-brief?secret=gold2026` — backup only; should never be needed with the auto catch-up.
- **Startup catch-up (fully automatic):** on any Railway restart after 09:00 UTC on a weekday, the brief fires automatically within 30 seconds IF it has not already been sent today. `_brief_sent_date` guard in `_daily_market_brief()` prevents double-fire if cron already ran before the restart.
- **No manual intervention needed** under any normal restart scenario — the system is self-healing.
- **Data pipeline (in order):**
  1. Pivot levels — `data/daily_levels.json` from GitHub (written by GitHub Actions at **07:50 UTC** Mon-Fri from TradingView ICMARKETS/AMEX/NASDAQ prev-day OHLC)
  2. Live price at send time — yfinance `fast_info.last_price` (pre-market for SPY/QQQ, spot for XAUUSD). Falls back to TradingView spot in `levels["current"]` if Yahoo gold spot is down (frequent from cloud IPs). Never uses GC=F futures for displayed price.
  3. Gap analysis — live price vs prev close, absolute + %, flags >0.2% as significant
  4. Directional read — `_technical_context()` in `daily_analysis.py`: MA trend stacking (20/50/200), 20-day momentum %, Wilder RSI, 60-day range position, ATR. Composite bias ∈ [0,1]. **Source never disclosed** — shown in brief as "the desk's own read", never names models/indicators.
  5. Macro bias — gold only, from `market_macro.py` (FRED real yield + dollar + COT + GLD)
  6. Economic calendar — **Finnhub** (US high-impact events) + **Forex Factory** (`https://nfs.faireconomy.media/ff_calendar_thisweek.json`, impact=high, country=USD). Merged, deduped by (minute, name prefix), sorted, shown in Dubai time (+4h).
- **Brief format (Telegram, HTML parse mode):**
  ```
  📅 MORNING MARKET BRIEF — {Weekday}, {DD Mon YYYY}
  ──────────────────────
  🥇 XAUUSD
  $X,XXX.XX [↑/↓] ... · Prev close $X,XXX.XX
  🎯 Bias: Bullish/Bearish NN% · Uptrend/Downtrend/Mixed · Momentum +/-X.X%
  📍 Pivot $X,XXX.XX · [Above → Bullish / Below → Bearish]
  🔴 R1 / R2 / R3   🟢 S1 / S2 / S3
  📈 Bull: [trigger] → $X,XXX then $X,XXX
  📉 Bear: [trigger] → $X,XXX then $X,XXX
  [same for SPY 📈 / QQQ 📊]
  📆 Key Events Today (Dubai time): ...
  ```
- **Model:** `claude-haiku-4-5-20251001`, max_tokens=1200
- **File:** `backend/daily_analysis.py` — `generate_daily_brief()` is the entry point
- **Yahoo ticker split (CRITICAL — do not merge back):**
  - `_YF_LIVE` = live price lookup — gold uses spot only (`XAUUSD=X`, `XAU=X`). Never futures here — GC=F basis premium creates false gap vs prev close.
  - `_YF_HIST` = daily-bar history for direction read — gold uses `GC=F` FIRST (reliable from Railway cloud IPs), spot as fallback. Direction math is basis-insensitive.
  - `XAUUSD=X` is frequently "possibly delisted" on Yahoo from cloud IPs — always ensure GC=F is first in `_YF_HIST`.

- FastAPI backend on Railway (Python 3.13)
- Scheduler: 5 jobs — signal every 15min, breaking news every 2min, system check every 60min, macro refresh every 60min, daily brief at 09:00 UTC (1 PM Dubai / UTC+4)
- ML: AdaptiveKNN + RandomForest + GradientBoosting, pool-aware (9 pools)
- `get_rf(pool)` and `get_gbm(pool)` always take a pool argument
- Features: 25 features (F1-F25), all computed in Pine Script and sent via webhook
- **Phase 2 — F26:** Stochastic (%K/%D) — ✅ implemented 2026-06-11 — Pine Script + backend expanded to 26 fields
- XAUUSD data: TVC:GOLD scanner (spot, ~$1-3 from ICMARKETS) + GC=F prev day H/L/C → pivot levels
- Daily levels written to `data/daily_levels.json` by GitHub Actions (**07:50 UTC** Mon-Fri, changed from 11:50 UTC on 2026-06-16 to run before the 09:00 UTC brief)

## Market Macro Intelligence (`market_macro.py`)
- Fills gold's real macro-driver blind spots beyond headline sentiment. Refreshed hourly, persisted to `data/market_macro.json`, loaded on startup.
- **Sources (all free):** FRED API (real yield `DFII10`, dollar `DTWEXBGS`, breakeven `T10YIE`, nominal `DGS10`) + CFTC COT (gold `088691`, no auth) + SPDR GLD CSV (tonnes/AUM, no auth)
- **`macro_bias`** ∈ [-1,+1]: positive = bullish gold. Rising real yields/dollar = bearish; rising breakeven/GLD tonnes = bullish. Real yield + dollar lead; COT + GLD confirm.
- Folded into `generate_signal` combined_score at weight 0.20 (gold only, stocks ignore). Surfaced in `health.json` (`macro_bias`, `macro_label`).
- **Required env keys (set in Railway):** `FRED_API_KEY` (free, fred.stlouisfed.org), `FINNHUB_KEY` (free, finnhub.io). Graceful no-op if absent.

## Swing Trading Addon (separate brain from intraday)
- **Goal:** swing trades (3–15 day holds) for stocks — Fundamental + news + sentiment "why" fused with a daily-bar technical "when". Backend-only (yfinance/Finnhub/Stooq), NO Pine Script / TradingView involvement.
- **`fundamental_data.py`** — per-stock free fundamentals: yfinance + Finnhub company news + Finviz scrape + SEC EDGAR (CIK-based Form 4 count, 8-K). Reduces to `score` ∈ [-1,+1].
  - **Archetype-aware scoring (advanced):** `archetype_of(info)` buckets each name by business model from yfinance `sector`/`industry` (growth_tech, mega_tech, bank, nonbank_fin, energy, staples, discretionary, healthcare, industrial, reit, utility, materials, default). `ARCHETYPE_WEIGHTS` gives each archetype its OWN metric set — banks on ROE/ROA/P-B/yield, growth-tech on Rule-of-40/rev-growth/gross-margin/PEG, REITs/utilities on yield+payout+leverage, etc. `_score` weight-averages only the metrics that matter for that type, then overlays insider direction, an Altman-Z distress penalty (non-financials only), and the just-reported earnings event delta.
  - **Advanced composite scores** (`_advanced()` from yfinance `info` + 3 statements): `piotroski_f` (0-9, skips financials/REITs), `altman_z` (Z manufacturers / Z'' non-manufacturers, never financials/REITs), Rule-of-40 (growth only), PEG, FCF yield, ROE/ROA, P/B.
- **`earnings_call.py`** — conference-call / earnings-event monitor. Detects "just reported within 10d" via Finnhub `/calendar/earnings` (free) → yfinance `get_earnings_dates` fallback. Pulls SEC EDGAR 8-K (Item 2.02) press-release text for guidance direction (raised/cut/reaffirmed regex), buyback/dividend flags, tone lexicon. Folds bounded `score_delta` ∈ [-0.4,+0.4] into the fundamental score; optional Haiku one-liner (dormant without `ANTHROPIC_API_KEY`). No premium transcript APIs (all paywalled/IP-blocked from cloud) — EDGAR 8-K + numeric beat/miss is the free stack.
- **`swing_screener.py`** — top-50 S&P 500 watchlist (`WATCHLIST`), nightly scan. `combined = 0.55·fundamental + 0.45·technical`, ×0.6 into imminent earnings. Technical score = daily EMA trend + 20d momentum + RSI band + sector relative strength (XL* ETFs). Persisted to `data/swing_candidates.json`. **ML ensemble NOT wired yet** — cold-start, no closed swing trades to train on; rules-based until the swing pool accumulates outcomes (then plugs into `_technical_score`).
- **`swing_narrative.py`** — Claude Haiku thesis ("why"). **Dormant-by-default:** if `ANTHROPIC_API_KEY` unset → structured bullet summary (no LLM, no failure). Key is ALREADY on Railway (used by news_fetcher + daily_analysis) → prose synthesis active. Model `claude-haiku-4-5-20251001`. ~$0.10/night for 50 stocks.
- **Brief format:** header shows `conviction NN% (STRONG≥50/GOOD≥35/MODERATE≥15/WEAK)` — displayed as `combined_score×100`%; underlying score is ∈ [−1,+1]. Raw RSI hidden (kept out of header AND the LLM prose). Each pick shows ATR-based levels: `Entry ~close · Stop −1 ATR · T1 +2 ATR · T2 +3 ATR` (same ATR basis the tracker grades WIN/LOSS on). No footer legend (kept minimal per user).
- **Telegram:** `send_swing_brief` → `SWING_CHAT_ID` (defaults to main `TELEGRAM_CHAT_ID` until a dedicated swing channel exists — then just set `SWING_CHAT_ID` in Railway, no code change).
- **Schedule:** nightly `_swing_screen_cycle` at 16:30 ET Mon-Fri (after NYSE close), holiday-aware (skips closed days).
- **`swing_tracker.py`** — paper-trade engine = the ML training-data source. Nightly opens top picks as paper trades (entry=close, TP=+2·ATR14, SL=-1·ATR14, 15-day max), captures the 13-feature vector at entry (`FEATURE_KEYS`). `_swing_manage_cycle` (16:45 ET) resolves opens against fresh daily bars → WIN/LOSS labels. Persisted to `data/swing_trades.json` ({open, closed}). `training_dataset()` → (X, y, meta); `ready` flips True at ≥50 closed trades, at which point the ensemble trains and `_technical_score` goes ML-scored. SL-before-TP on same-bar touch (pessimistic label).
- **Discipline (auto-enforced, not memory):** weekly autopsy (Mon) appends swing accumulation + `sanity_flag` (warns only at win-rate <25% / >75% — the "real bug vs noise" line; otherwise explicitly says do NOT tune on noise). Weekly model comparison (Sun) appends `shadow_eval` — walk-forward ML candidate vs rules baseline (combined_score>0). Shadow only: ML never drives live scoring until it beats baseline on live data, then promote after a shadow period.
- **Manual triggers:** `GET /swing/now?secret=gold2026` (rescan+send), `GET /swing/candidates?secret=...` (cached), `GET /swing/trades?secret=...` (training-readiness: open/closed/win-rate/ready).

## News sources
- **Replaced NewsAPI** (free tier returns HTTP 426 from cloud servers + 24h delay — unusable on Railway) with **Finnhub** news (forex+general, 60 req/min, cloud-friendly). NewsAPI kept as legacy fallback only if `FINNHUB_KEY` unset.
- **Scheduled-event awareness:** Finnhub economic calendar gives forward NFP/CPI/FOMC warning (imminent = high-impact within 90min) — de-risk BEFORE the print, not after keyword detection.
- **FXStreet RSS:** now uses realistic browser User-Agent + Accept headers to bypass Cloudflare 403.
- RSS feeds: FinancialJuice (primary), Kitco, MarketWatch, Investing.com, BullionVault, Mining.com, FXStreet, ForexLive
