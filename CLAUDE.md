# blank-app — Claude Code Notes

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


- FastAPI backend on Railway (Python 3.13)
- Scheduler: 5 jobs — signal every 15min, breaking news every 2min, system check every 60min, macro refresh every 60min, daily brief at 08:00 UTC
- ML: AdaptiveKNN + RandomForest + GradientBoosting, pool-aware (9 pools)
- `get_rf(pool)` and `get_gbm(pool)` always take a pool argument
- Features: 25 features (F1-F25), all computed in Pine Script and sent via webhook
- **Phase 2 — F26:** Stochastic (%K/%D) — ✅ implemented 2026-06-11 — Pine Script + backend expanded to 26 fields
- XAUUSD data: TVC:GOLD scanner (spot, ~$1-3 from ICMARKETS) + GC=F prev day H/L/C → pivot levels
- Daily levels written to `data/daily_levels.json` by GitHub Actions (07:50 UTC Mon-Fri), fetched at runtime from GitHub raw URL

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
