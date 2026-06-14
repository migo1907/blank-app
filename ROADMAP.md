# Migo Sniper Pro — ML Trading System Roadmap

---

## 📋 TOMORROW — To Do (June 5, 2026)

| # | Task | Notes |
|---|------|-------|
| 1 | **Heartbeat alert** — Pine Script fires F1–F25 every bar close to keep feature cache fresh | Backend needs to handle `outcome="HEARTBEAT"` — update cache only, do NOT store as trade record. This fixes `Signal NEUTRAL conf=0.00` between real trade webhooks |
| 2 | **Update CLAUDE.md** — remove "F25 computed server-side" (outdated since June 4 fix) | Small but important for next session context |
| 3 | **Verify pool-specific trade history on GitHub** — Railway loaded 109/54/20 trades but GitHub directory only showed 2 files | Check if files exist on branch or only in Railway's cached state |
| 4 | **Check Railway logs after market open** — confirm fresh webhooks firing with non-zero F22–F25 values | Proof that Pine Script new features are flowing correctly |

---

## PHASE 1 — Current: Data Collection & Learning
**Goal:** Build a statistically significant dataset, let ML find real edges

| Task | Status |
|------|--------|
| 25-feature KNN adaptive weights | ✅ Live |
| RF + GBM ensemble | ✅ Live |
| Multi-pool (Gold + Stocks) | ✅ Live |
| Pool TF architecture (XAUUSD 2M/5M/30M/1H + stocks 30M/4H) | ✅ Live |
| Trigger quality scoring | ✅ Live |
| Session intelligence (London fixed — was wrongly 0.60, now 1.15) | ✅ Fixed June 4 |
| VWAP stretch boost (now MTF-gated — no boost when 1H opposing) | ✅ Fixed June 4 |
| Pullback confirmation gate | ✅ Live |
| MFE-based ML outcome labeling | ✅ Live |
| FJ breaking news (red items only) | ✅ Live |
| Direction-change Telegram signals | ✅ Live |
| KNN label encoding fix (LOSS+SHORT now +1, PARTIAL uses PnL) | ✅ Fixed June 4 |
| Counter-trend penalty: swing pools 0.80, scalp pools 0.95 exempt | ✅ Fixed June 4 |
| F1–F25 all from Pine Script (F25 entry-time, not server-side) | ✅ Fixed June 4 |
| TVC:GOLD as XAUUSD data source (daily levels) | ✅ Fixed June 4 |
| MIN_CONFIDENCE raised to 0.62 (conservative until data grows) | ✅ Fixed June 4 |

**Exit criteria:** 150+ XAUUSD trades per TF pool, 50+ per stock pool, trigger win rates stabilized

---

## PHASE 2 — Next: Advanced ML Layers
**Goal:** Add intelligence layers that a professional quant desk would use

**2A — Market Regime Model (Priority 1)**
```
Current: Simple ADX + ATR regime detection
Next:    Hidden Markov Model — detects regime TRANSITIONS before they complete
         "Market is 73% likely shifting from RANGING to TRENDING_BEAR"
         Act on the transition, not after it's confirmed
```

**2A — Market Regime Model — ✅ DONE (2026-06-14)**
```
Gaussian HMM (regime_model.py) — probabilistic TRENDING/RANGING/VOLATILE with
forward-looking transition detection. Bounded confidence modulator in
signal_engine. Refreshed hourly, persisted, surfaced in /health.
```

**2B — Multi-Timeframe Confluence Engine — ✅ DONE (2026-06-14, backend-side)**
```
Implemented in the BACKEND (mtf_confluence.py) via yfinance 1H + 4H + Daily —
no Pine Script changes, no alert re-creation, no feature cold-start. Each TF
scored, higher TF weighted more (1H=1, 4H=2, 1D=3). Signal confidence boosted
on 2-of-3 / 3-of-3 agreement, dampened when <2 agree.
```

**2C — Volatility-Adjusted Position Sizing — ➡️ MOVED TO PHASE 3**
```
Deferred: sizing is advisory-only until execution exists (Phase 4). Revisit
with the Phase 3 signal-validation layer.
```

**2D — News Intelligence Layer — 🟡 calendar DONE, post-event scoring DONE (2026-06-14)**
```
Economic calendar (Finnhub) — forward NFP/FOMC/CPI awareness, de-risk before. ✅
Post-event volatility scoring (post_event.py) — after a high-impact print,
classify SETTLING / BREAKOUT / FADE from the asset's own price reaction and
modulate signal confidence accordingly. ✅
```

**2E — Correlation & Intermarket Analysis**
```
Gold:   DXY, US10Y real yield, Silver ratio
Stocks: SPY leadership, sector rotation, VIX term structure
When DXY breaks key level → gold signal gets context boost
When VIX spikes → stock signals get size reduction
```

---

## PHASE 2C — SPX 0-1DTE Options Layer (calls/puts only, long premium)
**Goal:** Translate SPX500 directional signals into SPX (SPXW daily-expiry) CALL/PUT recommendations. 0DTE or 1DTE only. No spreads, no selling premium.

**Instrument decision (locked 2026-06-11):** SPX index options — cash-settled (no assignment risk), European exercise, $5-wide strikes, section 1256 tax treatment, daily expirations Mon-Fri. ~$100/point multiplier — position sizing must respect this.

**What already exists (reuse, don't rebuild):**
- STOCKS_SPX500 pools (15M/30M/4H) produce LONG/SHORT signals through the full ML gate
- JointStocksGBM covers SPX while per-pool models wait for 50+ trades
- Economic calendar (Finnhub) + geopolitical shock detection — critical for options (IV crush around events)
- Telegram delivery + data-branch persistence patterns

### Stage A — Data & Translation (paper only, ~1-2 weeks dev)
| Task | Method |
|------|--------|
| **VIX feed** | yfinance `^VIX` + VIX/VIX3M term structure — refresh hourly in market_macro. VIX > 25 = half size; backwardation (VIX/VIX3M > 1) = no trades, gamma too violent for long premium |
| **Options chain source** | Backend: yfinance `^SPX` (delayed, paper-ledger baseline only). **Live premiums: user's TradingView OPRA subscription** — Telegram sends the exact contract symbol, user charts it in TV for live pricing. TV alerts on the contract's premium levels (-50%/+100%) fire back into the existing `/webhook`, giving the backend live exit data |
| **IV Rank filter** | Daily ATM IV stored to data branch → IV Rank percentile over trailing 60 sessions. Only buy when IV Rank < 50 |
| **Signal → contract translator** (`options_engine.py`) | LONG→CALL, SHORT→PUT. Strike: delta ~0.40 (slightly OTM). Expiry: **15M/30M signals → 0DTE (same-day SPXW); signals after 13:00 ET or 4H-pool signals → 1DTE** (next session) — never enter 0DTE in the last 2.5h with theta at maximum burn |
| **Expected-move check** | 0DTE ATM straddle = market's expected move for the day. Skip if ATR-based TP1 target < 0.8× remaining expected move |
| **Event filter** | No entries within 24h before FOMC/CPI/NFP, AND no 0DTE entries on the morning OF those events — reuse `_check_scheduled_events` |
| **Exits — tight, time-first** | -50% premium stop / +100% premium target / **0DTE hard exit 15:30 ET no exceptions** / 1DTE time stop at next-day 14:00 ET. Intraday: exit immediately if the underlying signal flips |
| **Sizing guard** | 0DTE total-loss probability is high by design: risk per trade = premium paid, capped at 1% of account. Expect ~40-45% of trades to expire worthless even with edge — the +100%/+200% winners carry the P&L |
| **Paper ledger** | `data/options_paper_SPX.json` — entry premium, strike, delta, IV at entry, exit premium, time held. Same schema discipline as trade_history |
| **Telegram format** | `🎯 SPX 0DTE — CALL 6080 (Δ0.41) @ $14.20 | IVR 32 | exp today | TP $28.40 / SL $7.10 / hard exit 15:30 ET` |

### Stage B — ML & Validation (needs 50+ paper option trades, ~4-6 weeks data)
| Task | Method |
|------|--------|
| Label option outcomes | WIN = ≥50% premium gain, LOSS = stopped, separate from underlying WIN/LOSS — an option can lose while direction was right (theta/IV) |
| New features for option gate | f27_ivrank, f28_vix_regime, f29_term_structure, f30_dte — train a dedicated small GBM: "given the directional signal fired, will the OPTION pay?" |
| Theta-adjusted Kelly sizing | Position size = ¼ Kelly on option win-rate × payoff ratio, capped at 2% account risk per trade |
| Walk-forward validation | Same champion-challenger pattern as pools — never deploy an option gate that hasn't beaten "take every signal" out-of-sample |

### Stage C — Execution (Phase 4 territory, only after Stage B proves edge)
- Broker API: Tradier (cheapest API access, sandbox first) or IBKR
- Hard limits: max 3 open contracts, max 5% account in premium, kill-switch env var

**Prerequisites before Stage A is worth starting:**
1. ⚠️ STOCKS_SPX500 pools are thin (8/8/3 trades) — the directional signal itself needs ~30+ trades to be trustworthy. 0DTE amplifies both edge AND noise more than any other instrument.
2. ~~Instrument decision~~ ✅ **SPX, 0-1DTE** (decided 2026-06-11)

**Exit criteria for Stage A → B:** 50 paper option trades logged with full IV/Greeks data
**Exit criteria for Stage B → C:** option-gate WR ≥ 55% AND profit factor ≥ 1.5 over 50+ out-of-sample paper trades

---

## PHASE 3 — Semi-Autonomous: Signal Validation Layer
**Goal:** System validates its own signals before sending them

**3D — Volatility-Adjusted Position Sizing (moved from 2C, 2026-06-14)**
```
ATR-normalized sizing — wider market = wider SL, smaller size, constant R:R.
Advisory sizing notes in alerts now; becomes enforced sizing once Phase 4
execution exists. Reuses the HMM VOLATILE regime + intermarket VIX size factor
already built in Phase 2.
```

**3A — Pre-Signal Checklist (automatic)**
```
Before any signal fires to Telegram, system checks:
□ Is spread normal? (not pre-news wide)
□ Is session active? (not dead zone)
□ Did last 3 signals of same type lose? (streak filter)
□ Is MTF stack aligned? (2 of 3 TFs agree)
□ Is volatility within tradeable range?
□ Is there a high-impact news event in next 30 minutes?

All pass → FIRE signal
Any fail → HOLD, log reason
```

**3B — Self-Scoring After Each Signal**
```
System reviews each closed trade:
- Did it hit TP1? If yes — what features were present?
- Did it hit SL? If yes — what was the market context?
- Was the R:R actually achieved?
- Feeds directly back into ML weights
```

**3C — Performance Dashboard (Telegram weekly report)**
```
Every Sunday automated report:
- Win rate this week vs last week
- Best performing trigger / session / regime
- ML weight changes — what the model learned
- Which stocks are performing vs underperforming
- Recommended focus for next week
```

---

## PHASE 4 — Full Autonomous Algo Trading
**Goal:** System executes trades without human input

**4A — Broker API Integration**
```
Options: MT5 API / OANDA / Interactive Brokers / Alpaca (stocks)
System sends: direction, size, SL, TP1, TP2, TP3
Broker executes: real order placement
```

**4B — Autonomous Position Management**
```
- Move SL to breakeven after TP1 hit (automatic)
- Partial close at TP1 (automatic)
- Trail stop after TP2 (automatic)
- Emergency close on news spike (automatic)
```

**4C — Risk Management Engine**
```
Hard rules the system cannot override:
- Max 2% account risk per trade
- Max 3 open positions simultaneously
- Max 5 losses in a day = pause for 24hrs
- Drawdown > 10% = reduce position size 50%
- Drawdown > 20% = full stop, alert human
```

**4D — Human Override Layer**
```
Always maintain human control:
- Telegram command: /pause — stop all signals
- Telegram command: /resume — restart
- Telegram command: /close_all — emergency exit all positions
- Telegram command: /status — full system health report
- Daily summary always sent regardless of activity
```

---

## Timeline Estimate

| Phase | Trades Needed | Estimated Time |
|-------|--------------|----------------|
| Phase 1 (now) | 150 XAUUSD per TF + 50/pool stocks | 4-8 weeks |
| Phase 2 | Built during Phase 1 data flow | 3-4 weeks dev |
| Phase 3 | 300+ total trades | 6-10 weeks |
| Phase 4 | Proven 58%+ WR sustained | 3-6 months |

---

## Timetable — Live Progress Tracker

**Phase 1 started: June 1, 2026 | Today: June 4, 2026**

> ⚠️ **Note:** Backtest data (6,653 trades) was injected then removed — only 25 clean live trades remain in base XAUUSD pool. All pool-specific files reset to 0. 6 TradingView alerts now live as of June 4.

### Pool-by-Pool Progress (as of June 11, 2026 — live counts from data branch)

| Pool | Trades | Target | Remaining | Status |
|------|--------|--------|-----------|--------|
| XAUUSD (base fallback) | 109 | 150 | 41 | 🟢 Nearly done |
| XAUUSD_2M | 386 | 150 | ✅ **TARGET HIT** | 🟢 Models trained, 52% WR last 50 |
| XAUUSD_5M | 105 | 150 | 45 | 🟢 On track |
| XAUUSD_30M | 11 | 150 | 139 | 🔵 Building |
| XAUUSD_1H | 2 | 150 | 148 | 🔵 Building |
| STOCKS_MOMENTUM_15M | 84 | 50 | ✅ **TARGET HIT** | 🟢 |
| STOCKS_MOMENTUM_30M | 53 | 50 | ✅ **TARGET HIT** | 🟢 |
| STOCKS_MOMENTUM_4H | 8 | 50 | 42 | 🔵 Building |
| STOCKS_QUALITY_15M | 40 | 50 | 10 | 🟢 Nearly done |
| STOCKS_QUALITY_30M | 25 | 50 | 25 | 🔵 Building |
| STOCKS_QUALITY_4H | 5 | 50 | 45 | 🔵 Building |
| STOCKS_INDEX/SPX500/QQQ pools | 1–8 each | 50 | — | 🔵 Building |

> XAUUSD_2M WR trajectory: first 50 trades = 34% → last 50 trades = **52%**. The learning loop is working.
> Known bleed: OVERLAP session (13–17 UTC) ran 21% WR over 42 trades — session bleed guard added June 11.

### Phase Milestones

| Milestone | Target Date | Status |
|-----------|-------------|--------|
| **Phase 1 complete** — all pools at target | **~Oct 1, 2026** | 🔵 In Progress |
| **Phase 2 dev begins** (build during Phase 1) | **~July 1, 2026** | ⏳ Upcoming |
| **Phase 2 complete** (HMM, MTF, news calendar) | **~Aug 1, 2026** | ⏳ Upcoming |
| **Phase 3 begins** — signal validation layer | **~Oct 1, 2026** | ⏳ Upcoming |
| **Phase 3 complete** — 300+ trades, self-scoring | **~Dec 1, 2026** | ⏳ Upcoming |
| **Phase 4 eligibility** — 200 consecutive trades @ 58%+ WR | **~Feb 1, 2027** | ⏳ Upcoming |
| **Phase 4 live** — full autonomous algo trading | **~Mar 1, 2027** | ⏳ Upcoming |

### Schedule Status

```
Phase 1:  🟢 ON TRACK — Legacy pool nearly done (109/150), new TF pools building
Phase 2:  ⏳ Dev starts July 2026 while Phase 1 data flows in parallel
Phase 3:  ⏳ Scheduled Oct 2026
Phase 4:  ⏳ Earliest Feb–Mar 2027 (gated by 58%+ WR over 200 consecutive trades)
```

> **Key gate before Phase 4:** Win rate must sustain 58%+ over 200 consecutive trades across all market regimes — not cherry-picked. This is a hard dependency, dates shift if WR criteria aren't met.

---

## 🔴 Known Issues — Open (as of June 7, 2026)

### Recently Fixed (June 7)
| # | Issue | Status |
|---|-------|--------|
| H1 | `main.py` — `is_entry` checked before `is_outcome`: trade-close payloads with tp1/sl silently routed to HTF bias store, trade record lost | ✅ Fixed |
| H2 | `htf_bias.py` — bias store in-memory only, lost on Railway restart, signals suppressed silently after redeploy | ✅ Fixed — persists to `data/htf_bias.json`, loads on startup |
| H3 | `ml_model.py` — race condition in `get_model()` singleton init, second concurrent request overwrites first's loaded weights | ✅ Fixed — double-checked locking |
| H4 | `db.py` — `_put_file()` no retry on 409 conflict, `save_weights()` permanently lost weight update on SHA conflict | ✅ Fixed — 3-retry with SHA re-fetch |
| M3 | `ml_ensemble.py` — same race condition in `get_rf()` / `get_gbm()` singleton init | ✅ Fixed — double-checked locking |
| M6 | `db.py` — `insert_signal()` no 409 retry, concurrent signal writes silently dropped | ✅ Fixed — 3-retry loop |



| # | Issue | Impact | Fix Trigger |
|---|-------|--------|-------------|
| 1 | `weights.json` missing — KNN adaptive weights never persisted to GitHub | Medium | Auto-creates on first WIN trade |
| 2 | F19 (RSI Divergence) always `0.0` — dead feature, never fires | Low | Investigate Pine Script detection logic or replace feature |
| 3 | All 25 historical trades are LOSS/PARTIAL, 0 WIN — KNN trained on losing patterns only | Medium | Resolves naturally as new trades accumulate with wins |
| 4 | F22–F25 absent from the 25 historical trades (old Pine Script didn't have them) | Low | Resolves naturally — new trades have all 25 features |
| 5 | CLAUDE.md still says "F25 computed server-side" — outdated after June 4 fix | Low | Update CLAUDE.md next session |
| 6 | Stocks alerts: only 2 active (30M + 4H) — STOCKS_QUALITY and STOCKS_INDEX pools have no alerts | Medium | Add TradingView alerts for quality/index stocks when ready |
| 7 | `main.py` lines ~347 & ~540 — `update_latest_features()` called synchronously in async handler, blocks event loop on every trade outcome | High | ✅ Fixed June 7 |
| 8 | `scheduler.py` line ~192 — `get_latest_features("XAUUSD")` wrong pool; heartbeats update `XAUUSD_2M` only, so 15-min signal cycle runs with None features — ML ensemble contributes nothing, signals driven by news only | High | ✅ Fixed June 7 |
| 9 | `main.py` `/weights`, `/feature-importance`, `/dashboard` — `get_model()` and `get_rf()` called without pool, defaults to base `XAUUSD` instead of `XAUUSD_2M` | Medium | ✅ Fixed June 7 |

---

## 🟡 Next Actions — When Trades Accumulate

| Milestone | Trigger | Action |
|-----------|---------|--------|
| 15+ trades per pool | ~1–3 days per active pool | RF + GBM auto-train, confidence scores start improving |
| First WIN recorded | Unknown | KNN weights save to GitHub for first time — adaptive learning begins |
| 50+ trades per pool | ~1–2 weeks | Consider lowering MIN_CONFIDENCE back toward 0.58 |
| 100+ trades per pool | ~3–4 weeks | Evaluate whether F19 (RSI div) should be replaced |
| 150+ trades XAUUSD pools | ~Phase 1 exit | Begin Phase 2 development (HMM regime model) |

---

## 🔵 Deferred — Future Improvements (not yet scheduled)

| Item | Description | Phase |
|------|-------------|-------|
| **F19 replacement** | RSI Divergence never fires — replace with Stochastic RSI or Volume Profile distance | Phase 1 exit |
| ~~Heartbeat alert~~ | ✅ Done — fires F1–F26 every bar close, keeps feature cache fresh | Done June 8 |
| ~~F26 Stochastic~~ | ✅ Done June 11 — Pine + backend at 26 features (alerts need re-creation on TradingView) | Done |
| ~~News calendar integration~~ | ✅ Done — Finnhub economic calendar, de-risk alert fires up to 90min before NFP/CPI/FOMC | Done (Phase 2D partial) |
| **Breaking news Telegram** | Currently disabled (`BREAKING_NEWS_TELEGRAM=false`) — enable when user ready | Anytime |
| **Hidden Markov Model (HMM)** | Replace simple ADX regime detection with probabilistic regime transition model — detects regime shifts before they complete | Phase 2A |
| **Full MTF stack** | Replace single F16 (1H) with 1H + 4H + Daily all scored — signal requires 2 of 3 TF agreement | Phase 2B |
| **ATR position sizing** | Dynamic SL/TP based on current volatility — wider market = wider SL, smaller size | Phase 2C |
| **DXY / US10Y intermarket** | When DXY breaks key level → gold signal gets context boost; VIX spike → reduce stock signal size | Phase 2E |
| **Weekly Telegram report** | Every Sunday: win rate, best trigger/session/regime, ML weight changes | Phase 3C |
| **Telegram bot commands** | `/pause`, `/resume`, `/close_all`, `/status` — human override layer | Phase 4D |

---

## The Non-Negotiable Before Phase 4

**Win rate must sustain 58%+ over minimum 200 consecutive trades before any auto-execution is considered.** Not a cherry-picked period — sustained performance across different market regimes.

A system that wins 65% in a trending bear market but 40% in ranging conditions is not ready for auto trading. It needs to prove itself across all regimes.
