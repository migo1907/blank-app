# ML System — v4 Research & Improvement Log
*Generated: 2026-06-10 | Focus: hardening + next-wave signal quality*

---

## What Was Found (Audit v3 → v4)

| Bug | File | Severity | Status |
|-----|------|----------|--------|
| TabPFN auth failure not remembered per-instance | ml_ensemble.py | Medium | ✅ Fixed |
| Local import inside champion-challenger (duplicate of top-level) | signal_engine.py | Low | ✅ Fixed |
| score_entry_gate() not wrapped in try/except in main.py | main.py | High | ✅ Fixed |
| LightGBM feature-name UserWarning in predict() | ml_ensemble.py | Low | ✅ Fixed |
| No alert when rollback fails (both RF+GBM have no prev model) | signal_engine.py | Medium | ✅ Fixed |

---

## v4 Improvements Implemented

### 1. Optuna Bayesian HPO (`tune_gbm_hyperparams`)
- **What:** TPE sampler + TimeSeriesSplit(n_splits=3, gap=5) CV — no shuffling, no lookahead
- **When:** Triggered when pool n≥80; cached per pool, re-tunes every 50 new trades
- **Tunes:** n_estimators (40–120), max_depth (2–4), learning_rate (0.03–0.20), num_leaves (4–15), subsample, colsample_bytree
- **Expected lift:** +2–6% F1 (purged CV prevents overfitting financial time series)
- **Risk:** Low — falls back to hardcoded defaults if Optuna unavailable or n<80
- **Citation:** MQL5 Bayesian HPO (2026), Optuna paper (NeurIPS 2019)

### 2. SHAP TreeSHAP Attribution (`explain_prediction`)
- **What:** Per-trade top-3 feature drivers (SHAP values). Unwraps CalibratedClassifierCV to get base estimator.
- **Where:** Added to score_entry_gate() response as `"shap_drivers"` field
- **Why:** Surfaces which F1–F25 features drove each signal — enables debugging poor signals, verifying domain logic
- **Speed:** O(TL) for tree models — ~5–15ms per inference (negligible)
- **Risk:** Very low — returns empty list on any error

### 3. requirements.txt hardened
Added: `lightgbm>=4.0.0`, `tabpfn>=8.0.0`, `optuna>=4.0.0`, `shap>=0.45.0`

---

## Methods Researched & Ranked (v4 candidates)

| Rank | Method | Min n | Expected Lift | Ease | Risk | Status |
|------|--------|-------|---------------|------|------|--------|
| 1 | Optuna TPE HPO + purged CV | 80 | +2–6% F1 | Low | Low | ✅ Implemented |
| 2 | SHAP TreeSHAP attribution | 50 | +1–3% (via debug) | Low | Very Low | ✅ Implemented |
| 3 | Monotonic constraints (LightGBM) | 50 | +3–8% F1 | Low | Medium* | 🔄 Pending validation |
| 4 | Expanding walk-forward retrain trigger | 30 | +5–12% F1 | Medium | Low | 🔄 Next sprint |
| 5 | Isotonic calibration (at n≥500) | 500 | +1–3% | Low | High if n<500 | ❌ Blocked (pool n too low) |
| 6 | Ensemble stacking (meta-learner) | 200 | +2–5% | Medium | High | ❌ Blocked (n too low) |
| 7 | Conformal prediction intervals | 300 | uncertainty bounds | Medium | High | ❌ Blocked |
| 8 | Quantile regression forest | 150 | asymmetric loss | Medium | High | ❌ Blocked |

*Monotonic constraints risk: direction-coded features (f2_adx = bullish/bearish) may not satisfy monotonic assumptions across LONG+SHORT mixed training data.

---

## Monotonic Constraints — Pending Validation Plan

Gold features with potential positive constraint (higher value → P(WIN) increases):
- `f2_adx` (ADX × DI direction): trend alignment → +1 IF we split LONG/SHORT training sets
- `f3_atr` (ATR volatility): **direction unclear** — high ATR increases volatility (harder to predict) but also increases R:R. **Do NOT constrain without empirical testing.**
- `f5_macd` (MACD histogram): directional momentum → +1 IF training is direction-conditional
- `f16_mtf` (multi-timeframe bias): higher = stronger HTF alignment → +1

**Validation approach:**
1. Train JointGoldGBM with and without constraints on XAUUSD_2M walk-forward
2. Compare OOS F1 for 5 folds — if constrained model wins ≥3/5 folds, enable
3. Test separately for LONG-only and SHORT-only subsets

---

## Expanding Walk-Forward Retrain Trigger (Next Sprint)

Current: retrain triggered only when pool n≥50 after each trade close.

Proposed enhancement:
- Keep last 150 trades max (cap prevents stale data dominating)  
- Re-trigger HPO when recent 20-trade win rate drops >5pp vs prev 20
- Signal regime shift — force recalibration immediately (not just at next trade close)

```python
def should_retrigger(history, window=20, drop_pp=5.0):
    if len(history) < window * 2:
        return False
    recent_wr = sum(1 for r in history[:window] if r.get("outcome") in ("WIN","PARTIAL")) / window
    prev_wr   = sum(1 for r in history[window:window*2] if r.get("outcome") in ("WIN","PARTIAL")) / window
    return (prev_wr - recent_wr) * 100 > drop_pp
```

---

## Never Implement (Confirmed Harmful)

| Method | Reason |
|--------|--------|
| CTGAN at n<150 | F1 utility ratio 0.44 (2026 MDPI benchmark) |
| MAML / ProtoNets | Requires 100+ meta-tasks; we have 19 pools |
| TabDDPM at n<100 | Memorizes training data at this scale |
| Standard (shuffled) cross-validation | Causes future leakage in time-series → false accuracy |
| Isotonic calibration at n<500 | Overfits calibration curve; Platt is strictly better below 500 |

---

## Connection to Previous Research

```
v1: Mistake memory, Platt calibration, session weights
v2: Feature selection (top-8), expectancy threshold (NP), champion-challenger, weekly autopsy
v3: Joint pool training (JFE 2024), TabPFN v2 (Nature 2025), warm-start transfer
v4: Optuna HPO + purged walk-forward CV, SHAP TreeSHAP per-trade attribution
    Bug hardening: TabPFN instance auth state, gate error handling, rollback alerts
v5 (planned): Monotonic constraints (validated), expanding walk-forward retrigger
```

---

## Sources
- Optuna: "Optuna: A Next-generation Hyperparameter Optimization Framework" (NeurIPS 2019)
- LightGBM monotonic constraints: ethan8181.github.io/machine-learning/trees/monotonic.html
- Monotonic credit benchmark: arXiv:2512.17945 (2025)
- TimeSeriesSplit purged CV: sklearn docs + "Advances in Financial ML" (Lopez de Prado)
- SHAP production guide: python.elitedev.in/machine_learning/complete-guide-to-shap
- Walk-forward analysis: blog.quantinsti.com/walk-forward-optimization-introduction/
- Hypothesis-driven trading validation: arXiv:2512.12924 (2025)
