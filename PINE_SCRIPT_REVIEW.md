# Pine Script — proposed changes for review (DO NOT auto-apply)

Reference: `migo_sniper_ml_v3.pine` on the `data` branch. Line numbers from that backup.
These are drafts for you to review and put on the chart yourself — I have not touched the script.

## Context (verified from 308 live XAUUSD_2M + 6 other pools)
- "WIN" = reaching TP3 only → ~1% by definition. Honest hit-rate (reached TP1+) ≈ 32–70%.
- SL_TP1 partials close **net −0.92 (2M) / −1.19 (5M)**, but **net positive on 30M + all stocks**.
- TP3 sits ~3.6R (2M) / 2.7R (5M) away → fills ~1% of the time.

---

## Change 1 — Report the STOP level as exit price, not the bar low/high  ⭐ highest value
**This is the real cause of the apparent SL_TP1 leak.**

Today the break-even guarantee already clamps the trail to entry (lines 466 / 511):
```
trailSL := math.max(close - atr * trailMult, entryPrice)   // LONG
trailSL := math.min(close + atr * trailMult, entryPrice)   // SHORT
```
…so the *stop* sits at break-even. **But the exit alert reports the bar's `low`/`high`, not `slPrice`:**
```
// LONG SL exit (current):
alert(buildPayload(activeTrade, outcome, mlOut, stage, entryPrice, low,  ...))
// SHORT SL exit (current):
alert(buildPayload(activeTrade, outcome, mlOut, stage, entryPrice, high, ...))
```
A stop fills at ~`slPrice`, not the bar extreme — so the payload overstates the loss. Fix: report the stop.
```
// LONG  → replace `low`  with `slPrice`
alert(buildPayload(activeTrade, outcome, mlOut, stage, entryPrice, slPrice, ...))
// SHORT → replace `high` with `slPrice`
alert(buildPayload(activeTrade, outcome, mlOut, stage, entryPrice, slPrice, ...))
```
Expected effect: SL_TP1 reported PnL moves from −0.92 → ≈0 (true break-even), matching reality.

## Change 2 — Add a cost buffer to the break-even stop (optional)
True break-even still nets slightly red after spread/commission. Lock a token profit:
```
// LONG  (line ~466)
trailSL := math.max(close - atr * trailMult, entryPrice + atr * 0.10)
// SHORT (line ~511)
trailSL := math.min(close + atr * trailMult, entryPrice - atr * 0.10)
```
0.10 ATR ≈ enough to cover gold scalp spread. Tune to your broker's cost.

## Change 3 — Pull TP3 in for the fast pools so the runner is reachable
Current (line 57): `atrMultTP3 = isTF2 ? 3.0 : isTF5 ? 4.0 : isTF15 ? 5.5 : isTF30 ? 6.0 : 7.0`
Against SL (line 58): `isTF2 0.8 : isTF5 1.5` → TP3 is 3.75R (2M) / 2.7R (5M). Fills ~1%.
Proposed (only the two scalp pools):
```
float atrMultTP3 = autoTF ? (isTF2 ? 2.2 : isTF5 ? 3.2 : isTF15 ? 5.5 : isTF30 ? 6.0 : 7.0) : tp3_inp
```
→ TP3 ≈ 2.75R (2M) / 2.1R (5M): still a real runner, but reachable. Leave 15M/30M/1H unchanged (those already bank fine and have no TP3-fill problem).

## Note — Pine's internal ML mirrors the same SL_TP1=0.4 grade
The Pine script also does `totalWins += 1; updateWeightsLong(winReward * 0.4)` for SL_TP1.
The authoritative ML is the backend (already fixed to grade by realized PnL per pool). If you
rely on Pine's on-chart ML too, apply the same PnL-aware logic there; otherwise leave it.

---
### Suggested rollout
1. Change 1 alone first (pure reporting accuracy, zero strategy change) — confirm SL_TP1 PnL normalizes.
2. Then Change 3 (TP3 reachability) on 2M/5M only.
3. Change 2 last if costs still drag SL_TP1 slightly red after Change 1.
