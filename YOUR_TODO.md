# Your Action List — Things Only You Can Do
*Last updated: 2026-06-11 | Keep this file open — add to it, cross off when done*

---

## 🔴 URGENT — System Won't Work Without These

- [ ] **RE-CREATE your TradingView alerts — f26 is NOT arriving**
  - The Pine Script editor was updated to the f26 version, but TradingView alerts
    snapshot the script at creation time. The live heartbeats still send only f1–f25.
  - Delete each of the 6 alerts and re-create them from the updated f26 script
    (same webhook URL: `/webhook`, same message: `{{strategy.order.alert_message}}` / alert() payload)
  - **Verify:** after re-creating, the dashboard table should show the "Stoch:" value,
    and `data/feature_cache.json` on the data branch will include an `f26` key.

- [ ] **Fix `FJ_EMAIL` and `FJ_PASSWORD` in Railway — FinancialJuice login is failing**
  - Log shows: `Auto-login failed — no .ASPXAUTH cookie received`
  - In Railway → Variables → check `FJ_EMAIL` and `FJ_PASSWORD` are correct
  - These are your FinancialJuice.com login credentials
  - **Why:** Without login, FJ premium breaking news feed falls back to public RSS only — fewer high-impact events detected.

- [ ] **Set `HF_TOKEN` in Railway environment variables**
  - Get a free read token: https://huggingface.co/settings/tokens
  - In Railway → Variables → add `HF_TOKEN = hf_xxxx`
  - **Why:** Unlocks TabPFN v2 as a 4th independent ML signal (works even on pools with only 10 trades). Currently disabled — will be re-enabled once the token is set.


---

## 🟡 HIGH PRIORITY — Do This Week

- [ ] **Verify Railway deployed the latest fix (build was crashing)**
  - Open Railway → your service → Deployments
  - Confirm the most recent deployment shows "Deployment successful" (not FAILED)
  - The fix pins Python to 3.13.13 — the build was failing because mise couldn't find 3.13.14
  - If still FAILED: take a screenshot and send it to me

- [ ] **Run Pine Script historical replay for thin pools**
  - Open TradingView → your `f25 Migo VS Market Sniper Pro` strategy
  - Switch to `strategy()` mode and run on **2 years of historical data** for each pool:
    - XAUUSD 5M (currently n=84 — most urgent)
    - XAUUSD 30M (n≈51)
    - XAUUSD 1H
    - All STOCKS_* pools with n<60
  - Export the trades and import to `data/trade_history_{POOL}_replay.json` on the data branch
  - **Why:** This is the fastest route to n≥200 per pool. No ML change can substitute for more real data. Every extra 50 trades = meaningfully better models.
  - **Validation:** Spot-check 10 random replay trades vs live alerts to verify conditions match exactly.

- [ ] **Verify Pine Script backup is current**
  - Check: https://raw.githubusercontent.com/migo1907/blank-app/data/pine_script_backup/migo_sniper_ml_v3.pine
  - Make sure this matches your current live Pine Script version exactly
  - **Why:** If Railway goes down or you lose the script, this is your only backup.

---

## 🟠 MEDIUM PRIORITY — Do This Month

- [ ] **Review the weekly model comparison Telegram message (first one arrives Sunday 20:00 UTC)**
  - The new system sends a walk-forward F1 comparison: RF vs GBM vs Joint model per pool
  - **Your job:** Look at which pools show a consistent winner. If one model wins 3+ Sundays in a row, tell me and I'll increase its weight in `score_entry_gate()`.

- [ ] **Review the Monday 09:00 UTC SHAP autopsy message**
  - The weekly autopsy now includes the top-3 features driving losses (e.g. "high ATR during Asian session")
  - **Your job:** If you see a pattern that matches what you observe on-chart, confirm it. That's ground truth I can use to add a domain rule.

- [ ] **Decide on F-beta setting (ML_FBETA env var)**
  - Currently beta=2.0 (recall 2× more important than precision — catches more wins, more false signals)
  - Options: `ML_FBETA=1.0` (balanced), `ML_FBETA=2.0` (more wins, more noise), `ML_FBETA=0.5` (fewer signals, higher quality)
  - Set in Railway → Variables → `ML_FBETA = 2.0`
  - **Why:** This controls how the ML gate threshold is tuned. Match it to your trading style.

- [ ] **Check Railway health endpoint after next deploy**
  - URL: https://blank-app-production-a8bd.up.railway.app/health?secret=gold2026
  - Returns full ML state: per-pool trained/threshold/retrain count + joint model status
  - **Your job:** Confirm it shows `"joint_gold_trained": true`

---

## 🔵 LOWER PRIORITY — When You Have Time

- [ ] **Test the `/daily-brief` endpoint manually**
  - URL: https://blank-app-production-a8bd.up.railway.app/daily-brief?secret=gold2026
  - Confirm the format is still useful and the levels look correct

- [ ] **Consider adding a 1-minute XAUUSD pool**
  - Would give 2-4× more signals per day
  - Risk: 1M has more noise, different microstructure regime
  - If you want this, enable it in Pine Script and tell me — I'll add pool routing in `db.py`

---

## ✅ DONE — No Further Action Needed

- [x] GITHUB_TOKEN set in Railway (db.py writes to data branch)
- [x] TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID set in Railway
- [x] WEBHOOK_SECRET (`gold2026`) set in Railway
- [x] Pine Script updated to f25 version (all 25 features sending correctly)
- [x] `isTF30` bucket implemented (30M has dedicated ATR multipliers)
- [x] TVC:GOLD data source set (spot gold, ~$1-3 from ICMARKETS)
- [x] Daily levels GitHub Actions job set (07:50 UTC Mon-Fri)
- [x] `FRED_API_KEY` set in Railway — confirmed working in logs (`live.fred: true`, real yield + dollar + breakeven all loading)
- [x] `FINNHUB_KEY` set in Railway — confirmed working for news feed (free tier, calendar endpoint intentionally skipped)
- [x] `FINNHUB_KEY` rotated 2026-06-11 after log exposure
- [x] F26 Stochastic implemented backend-side (Pine + backend + tests, merged via PR #13) — pending alert re-creation on TradingView
- [x] Stale CPI/NFP de-risk alert fix (24h→4h keyword window) — PR #14
- [x] TimeSeriesSplit calibration CV + MIN_TRADES 30 — no more look-ahead bias in RF/GBM

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

---

*This file lives at `YOUR_TODO.md` in the repo root. I update it whenever there's a new action for you.*
*Claude handles everything else automatically — research, implementation, testing, CI, deployment.*
