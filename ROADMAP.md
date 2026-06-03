# Migo Sniper Pro — ML Trading System Roadmap

---

## PHASE 1 — Current: Data Collection & Learning
**Goal:** Build a statistically significant dataset, let ML find real edges

| Task | Status |
|------|--------|
| 25-feature KNN adaptive weights | ✅ Live |
| RF + GBM ensemble | ✅ Live |
| Multi-pool (Gold + Stocks) | ✅ Live |
| 10-pool TF architecture (2M/5M/30M/1H + stocks 30M/4H) | ✅ Live |
| Trigger quality scoring | ✅ Live |
| Session intelligence | ✅ Live |
| VWAP stretch boost | ✅ Live |
| Pullback confirmation gate | ✅ Live |
| MFE-based ML outcome labeling | ✅ Live |
| FJ breaking news (red items only) | ✅ Live |
| Direction-change Telegram signals | ✅ Live |

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

**2B — Multi-Timeframe Confluence Engine**
```
Current: f16_mtf = single 1H value
Next:    Full MTF stack — 1H + 4H + Daily all scored and weighted
         Signal only fires when 2 of 3 timeframes agree
         Higher TF = higher weight in the decision
```

**2C — Volatility-Adjusted Position Sizing**
```
Current: Fixed TP/SL multipliers
Next:    ATR-normalized sizing — wider market = wider SL, smaller size
         R:R stays constant regardless of market conditions
         Protects capital during high-volatility sessions
```

**2D — News Intelligence Layer**
```
Current: Basic sentiment score
Next:    Economic calendar integration — know BEFORE high-impact events
         NFP / FOMC / CPI = reduce position size or pause signals 30min before
         Post-event volatility scoring — fade the spike or follow the breakout
```

**2E — Correlation & Intermarket Analysis**
```
Gold:   DXY, US10Y real yield, Silver ratio
Stocks: SPY leadership, sector rotation, VIX term structure
When DXY breaks key level → gold signal gets context boost
When VIX spikes → stock signals get size reduction
```

---

## PHASE 3 — Semi-Autonomous: Signal Validation Layer
**Goal:** System validates its own signals before sending them

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

**Phase 1 started: June 1, 2026 | Today: June 3, 2026**

### Pool-by-Pool Progress (as of June 3, 2026)

| Pool | Trades | Target | Remaining | Rate/day | ETA | Status |
|------|--------|--------|-----------|----------|-----|--------|
| XAUUSD (legacy) | 109 | 150 | 41 | ~55 | **~June 4** | 🟢 Nearly done |
| XAUUSD_2M | 2 | 150 | 148 | ~2-3 | ~Aug 1 | 🔵 Data flowing |
| XAUUSD_5M | 1 | 150 | 149 | ~2-3 | ~Aug 5 | 🔵 Data flowing |
| XAUUSD_30M | 0 | 150 | 150 | ~1-2 | ~Sep 1 | ⏳ Starting |
| XAUUSD_1H | 0 | 150 | 150 | ~0-1 | ~Oct 1 | ⏳ Starting |
| STOCKS_MOMENTUM_30M | 0 | 50 | 50 | ~1-2 | ~Aug 15 | ⏳ Starting |
| STOCKS_MOMENTUM_4H | 0 | 50 | 50 | ~0-1 | ~Sep 15 | ⏳ Starting |
| STOCKS_QUALITY_30M | 1 | 50 | 49 | ~1-2 | ~Aug 14 | 🔵 Data flowing |
| STOCKS_QUALITY_4H | 0 | 50 | 50 | ~0-1 | ~Sep 15 | ⏳ Starting |
| STOCKS_INDEX_30M/4H | 0 | 50 | 50 | ~1-2 | ~Aug 15 | ⏳ Starting |

> Rates estimated conservatively. Gold TF pools fire ~2-3 signals/day per pool; stock pools ~1-2/day on active sessions.

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

## The Non-Negotiable Before Phase 4

**Win rate must sustain 58%+ over minimum 200 consecutive trades before any auto-execution is considered.** Not a cherry-picked period — sustained performance across different market regimes.

A system that wins 65% in a trending bear market but 40% in ranging conditions is not ready for auto trading. It needs to prove itself across all regimes.
