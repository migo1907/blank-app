# Your Action List — Things Only You Can Do
*Last updated: 2026-06-14 | Keep this file open — add to it, cross off when done*

---

## 🔴 URGENT — System Won't Work Without These

- [x] **RE-CREATE your TradingView alerts — DONE 2026-06-14**
  - All 9 alerts re-created from the updated f26 script (F26 is now Stochastic %K−%D delta,
    no longer a redundant mirror of F6 Williams %R)
  - Verify Monday after London open: `data/feature_cache.json` on the `data` branch —
    `f26` should no longer equal `−f6`

- [ ] **Fix `FJ_EMAIL` and `FJ_PASSWORD` in Railway — FinancialJuice login is failing**
  - Log shows: `Auto-login failed — no .ASPXAUTH cookie received`
  - In Railway → Variables → check `FJ_EMAIL` and `FJ_PASSWORD` are correct
  - **Note:** public RSS still works as fallback — lower priority, not breaking anything

- [ ] **Set `HF_TOKEN` in Railway environment variables** *(low priority — defer until pools at n≥100)*
  - Get a free read token: https://huggingface.co/settings/tokens
  - In Railway → Variables → add `HF_TOKEN = hf_xxxx`

---

## 🟡 HIGH PRIORITY — Do This Week

- [ ] **Verify Alpha Vantage API key is working in Railway**
  - Added to Railway Variables today (2026-06-14)
  - Test: hit `/health?secret=gold2026` and look for `alpha_vantage` in the response,
    OR check Railway logs for `[alpha_vantage]` lines at next hourly scheduler run
  - **What it's used for:** premium options chain data (IV rank, Greeks) for the Phase 2C
    SPX 0-1DTE options layer. Not used in current intraday signals or swing screening.
  - **Options trading use:** YES — Alpha Vantage is the planned source for IV Rank
    percentile (60-session ATM IV history) and options chain data when Stage A of the
    options layer is built. It is NOT yet wired into any live code — that's Phase 2C work.

- [ ] **Verify Railway deployed the latest commits (build was crashing on older deploys)**
  - Open Railway → your service → Deployments
  - Confirm the most recent deployment shows "Deployment successful"
  - Latest pushed commit: `56dcff528` (fix: F26 redefined as StochΔ)

- [ ] **Run Pine Script historical replay for thin pools**
  - Open TradingView → your `f26 Migo VS Market Sniper Pro` strategy
  - Switch to `strategy()` mode and run on **2 years of historical data** for each pool:
    - XAUUSD 30M (n≈11 — most urgent)
    - XAUUSD 1H  (n≈2 — critical)
    - STOCKS_*_4H pools (n=5–8 each)
  - Export trades and import to `data/trade_history_{POOL}_replay.json` on the data branch
  - **Why:** fastest route to n≥150/50 per pool. No ML change can substitute for more data.

- [ ] **Verify Pine Script backup is current**
  - Check: https://github.com/migo1907/blank-app/blob/claude/hopeful-pasteur-VVHCl/pine_script_backup/migo_sniper_f26.pine
  - This is the canonical backup — the version you pasted into TradingView today

---

## 🟠 MEDIUM PRIORITY — Do This Month

- [ ] **Review the weekly model comparison Telegram message (Sundays 20:00 UTC)**
  - Walk-forward F1 comparison: RF vs GBM vs Joint model per pool
  - **Your job:** note which pools show a consistent winner (3+ Sundays in a row) → tell me

- [ ] **Review the Monday 09:00 UTC SHAP autopsy message**
  - Top-3 features driving losses
  - **Your job:** if a pattern matches what you see on-chart, confirm it — that's ground truth

- [ ] **Decide on F-beta setting (ML_FBETA env var)**
  - Currently beta=2.0 (recall 2× more important than precision)
  - Options: `1.0` balanced / `2.0` more wins+noise / `0.5` fewer signals higher quality
  - Set in Railway → Variables → `ML_FBETA = 2.0` (or change it)

---

## 🔵 LOWER PRIORITY — When You Have Time

- [ ] **Enable swing Telegram when training data is ready**
  - Swing Telegram is currently SILENT (training phase — accumulating paper trades)
  - Re-enable when ≥50 closed swing trades exist: uncomment 2 lines in `scheduler.py`
    around line 1647 (`send_swing_brief`). Check `/swing/trades?secret=gold2026` for count.

- [ ] **Test the `/daily-brief` endpoint manually**
  - URL: https://blank-app-production-a8bd.up.railway.app/daily-brief?secret=gold2026

- [ ] **Consider adding a 1-minute XAUUSD pool**
  - Would give 2-4× more signals per day
  - Risk: 1M has more noise, different microstructure regime
  - Tell me if you want it — I'll add pool routing in `db.py`

---

## ✅ DONE — No Further Action Needed

- [x] GITHUB_TOKEN set in Railway
- [x] TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set in Railway
- [x] WEBHOOK_SECRET (`gold2026`) set in Railway
- [x] Pine Script updated to f26 version (all 26 features sending correctly)
- [x] `isTF30` bucket implemented (30M has dedicated ATR multipliers)
- [x] TVC:GOLD data source set
- [x] Daily levels GitHub Actions job set (07:50 UTC Mon-Fri)
- [x] `FRED_API_KEY` set in Railway
- [x] `FINNHUB_KEY` set in Railway + rotated 2026-06-11
- [x] F26 Stochastic implemented — Pine + backend — alerts re-created 2026-06-14
- [x] **F26 REDEFINED 2026-06-14** — old normalised %K was r=−1.0 with F6 (Williams %R),
      zero new information. Redefined as Stochastic %K−%D momentum delta (orthogonal to F6).
      Commit `56dcff528`. Pine backup: `pine_script_backup/migo_sniper_f26.pine`.
- [x] Stale CPI/NFP de-risk alert fix (24h→4h keyword window)
- [x] TimeSeriesSplit calibration CV + MIN_TRADES 30
- [x] Swing Telegram set to SILENT during training phase (2026-06-14)

---

## 📋 ONGOING — Weekly Habits

Every Monday:
- Read the Telegram autopsy message (09:00 UTC)
- Note any loss pattern that repeats 3+ weeks → tell me, I'll add a rule

Every Sunday:
- Read the model comparison Telegram message (20:00 UTC)
- Note which model wins which pool consistently

When a new pool reaches n=50:
- Tell me the pool name
- I'll verify the models trained correctly and adjust the threshold

When swing closed trades reach n=50:
- Tell me — I'll re-enable Telegram and wire up the ML ensemble for swing scoring

---

*This file lives at `YOUR_TODO.md` in the repo root. Claude updates it each session.*
*Claude handles everything else automatically — research, implementation, testing, CI, deployment.*
