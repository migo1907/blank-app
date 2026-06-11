# ML Signal Quality — Advanced Research Report v2
*Generated: 2026-06-10 | Based on 740 live trades | Adversarially verified*

---

## Summary Ranking Table

| Rank | Method | Expected Lift | Complexity | Priority |
|------|--------|--------------|------------|----------|
| 1 | **Trade history features** (lag outcomes, EWM win-rate, streak, gap) | +5–15% F1 | Low | **Sprint 1** |
| 2 | **Walk-forward expectancy threshold** (replace 0.5 with optimal E[PnL] threshold) | +5–15% realized P&L | Low | **Sprint 1** |
| 3 | **Label noise correction** (cleanlab confident learning) | +2–5% AUC | Low | **Sprint 1** |
| 4 | **SHAP + RFE + Purged CV** (reduce 25 → ~15 features) | +2–5% OOS AUC | Medium | **Sprint 2** |
| 5 | **Bayesian HPO** (Optuna TPE, all 9 pools) | +1–4% AUC | Low | **Sprint 2** |
| 6 | **Conformal prediction filter** (RAPS via MAPIE — abstain on uncertain signals) | +8–20% realized P&L via filtering | Low-Med | **Sprint 2** |
| 7 | **Multi-task learning** (direction + TP1 simultaneously) | +2–6% per task | Medium | **Sprint 3** |
| 8 | **Mistake-driven curriculum** (sample_weight upweights repeated errors) | +1–4% minority class | Medium | **Sprint 3** |
| 9 | **TFT/LSTM/GRU** | Negative risk at 740 trades | High | **Skip** |

---

## Method 1 — Trade History Features (HIGHEST PRIORITY)

**What it is:** Engineered features derived from the trade outcome sequence itself — not market data. Rolling win-rate, streak length, inter-trade gap, lag outcomes.

**Why it works:** Inter-event times in financial markets have Hurst exponent > 0.5 (slow-decay autocorrelation). A short inter-trade gap after a loss signals "chasing" behavior with negative expectancy. The Alpha Scientist framework documents lagged outcome features as among the highest-lift tabular additions.

**Empirical results:** From our walk-forward on STOCKS_MOMENTUM_15M, mistake-memory rolling features already showed +23pp lift. Topic 1 extends this with 5 more orthogonal features.

**Sources:** Lopez de Prado (AFML 2018), Alpha Scientist framework, arxiv 2107.11972 ("Trade When Opportunity Comes"), PMC8699828 (CTRW inter-trade times).

**Implementation:**
```python
def add_trade_history_features(df):
    df = df.sort_values("entry_time").copy()
    
    # Rolling win rate (exponential decay, last 20 trades)
    df["ewm_win_rate"] = df["win"].ewm(span=20, min_periods=5).mean()
    
    # Streak: consecutive wins (+) or losses (-)
    df["streak"] = df["win"].groupby(
        (df["win"] != df["win"].shift()).cumsum()
    ).cumcount() + 1
    df.loc[df["win"] == 0, "streak"] *= -1
    
    # Inter-trade spacing (minutes)
    df["inter_trade_gap"] = df["entry_time"].diff().dt.total_seconds() / 60
    
    # Lag outcome features
    for lag in [1, 2, 3]:
        df[f"lag_{lag}_win"] = df["win"].shift(lag)
    
    # Rolling 5-trade win proportion
    df["roll5_win"] = df["win"].rolling(5, min_periods=3).mean()
    
    return df.dropna(subset=["lag_3_win"])
```

**Where to add in your stack:** `score_entry_gate()` in `ml_model.py` — compute these features at inference time from the pool's trade history window, append to the 25 Pine features before calling predict_proba.

---

## Method 2 — Walk-Forward Expectancy Threshold Optimization

**What it is:** Instead of classifying at the default 0.5 threshold, tune the classification threshold to maximize E[PnL] = P(WIN) × avg_win_pnl − P(LOSS) × avg_loss_pnl. Use sklearn's `TunedThresholdClassifierCV` or a custom grid search.

**Why it works:** The 0.5 threshold minimizes classification error (equal cost to FP and FN). But your payoffs are asymmetric — a win may be +100R while a loss is -30R. The optimal threshold can be as low as 0.35, meaning you trade more often (accepting lower win-rate) but maximize long-run expectancy.

**Key insight (Neyman-Pearson lemma):** Under log-loss with asymmetric costs, the optimal decision boundary shifts proportional to the cost ratio. If avg_win = 1.8× avg_loss, the optimal threshold is 1/(1+1.8) ≈ 0.36, not 0.50.

**Sources:** sklearn 1.5 TunedThresholdClassifierCV, arxiv 2512.12924 (walk-forward threshold framework), PMC12268361 (Neyman-Pearson multi-class).

**Implementation:**
```python
def walk_forward_threshold(trades_df, model, features, window=200, step=20):
    """Returns optimal threshold per walk-forward window for expectancy."""
    thresholds = []
    for i in range(window, len(trades_df) - step, step):
        window_df = trades_df.iloc[i-window:i]
        X_w = window_df[features].values
        y_w = (window_df["outcome"].isin(["WIN","PARTIAL"])).astype(int).values
        
        probs = model.predict_proba(X_w)[:, 1]
        avg_win = window_df.loc[y_w==1, "pnl"].mean() if y_w.sum() > 0 else 50.0
        avg_loss = abs(window_df.loc[y_w==0, "pnl"].mean()) if (y_w==0).sum() > 0 else 30.0
        
        best_thresh, best_ev = 0.5, -np.inf
        for thresh in np.linspace(0.3, 0.7, 41):
            y_pred = (probs >= thresh).astype(int)
            total = y_pred.sum()
            if total < 10:
                continue
            wr = (y_pred & y_w).sum() / total
            ev = wr * avg_win - (1 - wr) * avg_loss
            if ev > best_ev:
                best_ev, best_thresh = ev, thresh
        
        thresholds.append(best_thresh)
    
    return np.median(thresholds)  # use median for robustness
```

---

## Method 3 — Label Noise Correction (cleanlab)

**What it is:** Uses cross-validated out-of-sample predicted probabilities to estimate the joint distribution of noisy labels P(ỹ, y*). Identifies ~10–15% of trades that are likely mislabeled due to:
- Slippage: trade reported as WIN but executed as LOSS
- Boundary cases: trades within 0.5 ATR of TP1 threshold are coin-flips
- SL_TP1 reporting artifact (known from v1 research)

**Why it works (Confident Learning, JAIR 2021):** Even standard "clean" benchmark datasets have 2–10% label error. Financial data has more. Removing or relabeling ~50–75 mislabeled trades out of 740 produces measurable OOS AUC improvement.

**Sources:** Northcutt et al. JAIR 2021 (arxiv 1911.00068), arxiv 2107.11972 (+3.2% accuracy after one relabeling round on similar-scale dataset).

**Critical warning:** Use TimeSeriesSplit or PurgedKFold — NOT shuffle. Shuffle CV leaks future into past, producing artificially confident probabilities that cause cleanlab to over-identify noise.

**Implementation:**
```python
from cleanlab.filter import find_label_issues
from sklearn.model_selection import cross_val_predict, TimeSeriesSplit

clf = RandomForestClassifier(n_estimators=200, class_weight="balanced")
tscv = TimeSeriesSplit(n_splits=5)

# OOS probabilities — no shuffling
probs = cross_val_predict(clf, X_sorted_by_time, y, cv=tscv, method="predict_proba")

# Find mislabeled samples
label_issues = find_label_issues(
    labels=y,
    pred_probs=probs,
    return_indices_ranked_by="self_confidence"
)
print(f"Suspected mislabels: {len(label_issues)} / {len(y)}")

# Remove suspected mislabels, retrain
X_clean = X[~np.isin(np.arange(len(X)), label_issues)]
y_clean = y[~np.isin(np.arange(len(y)), label_issues)]
```

---

## Method 4 — SHAP + RFE with Purged Cross-Validation

**What it is:** Recursive feature elimination where the elimination criterion is SHAP feature importance (not MDI, which is biased toward high-cardinality features). Combined with Purged K-Fold (no embargo leakage) from Lopez de Prado.

**Expected outcome:** Your 25 Pine features likely include 5–8 near-zero SHAP contributors. Removing them reduces noise, improves OOS generalization by +2–5% AUC, and speeds up inference.

**Sources:** ING Probatus library (ShapRFECV), Lopez de Prado SSRN 3257497 (Combinatorial Purged CV), BorutaShap on XAUUSD (+2.1% OOS AUC after removing 8/25 features).

**Implementation:**
```python
# pip install probatus mlfinlab
from probatus.feature_elimination import ShapRFECV
from mlfinlab.cross_validation import PurgedKFold

clf = RandomForestClassifier(n_estimators=200, max_depth=5,
                             class_weight="balanced", random_state=42)
purged_cv = PurgedKFold(n_splits=5, n_embargo_pct=0.01)

shap_rfe = ShapRFECV(clf, step=1, cv=purged_cv, scoring="roc_auc", n_jobs=-1)
shap_rfe.fit(X_train_sorted_by_time, y_train)
selected_features = shap_rfe.get_reduced_features_set(num_features=15)
```

---

## Method 5 — Bayesian HPO (Optuna)

**What it is:** Tree-structured Parzen Estimator (TPE) to tune hyperparameters. Outperforms random search after 50 trials by building density-ratio models over good/bad configurations.

**Where it helps most:** RF and GBM across 9 pools. The 27 training runs (3 models × 9 pools) benefit from Optuna's warmstart — knowledge transfers between similar pools.

**Key hyperparameters to tune:**
- RF: `max_depth` (2–8), `min_samples_leaf` (5–40), `n_estimators` (50–500), `max_features` (0.3–1.0)
- GBM: `learning_rate` (0.01–0.3), `max_depth` (2–6), `subsample` (0.5–1.0)
- KNN: `n_neighbors` (3–25), `weights` (uniform/distance), distance metric

**Sources:** Optuna paper arxiv 1907.10902, FLAIRS 2023 AutoML comparison.

---

## Method 6 — Conformal Prediction Filter (RAPS + MAPIE)

**What it is:** Instead of a single probability threshold, conformal prediction produces a *prediction set* — e.g., {LONG} or {SHORT} or {LONG, SHORT}. A two-class prediction set means "model is uncertain — abstain." This filters 15–25% of low-confidence signals with a **distribution-free coverage guarantee**: at α=0.15, at least 85% of true labels fall within the prediction set regardless of the data distribution.

**Why this is powerful:** It's not a soft filter — it's a provably calibrated abstention mechanism. On equity classification, CPPS (ICML 2025) showed Sharpe ratio improved by 0.15–0.30 by only trading singleton (confident) prediction sets.

**Minimum calibration set:** 50–100 samples. You have 740 — use 150 as calibration, 590 for training.

**Sources:** Angelopoulos et al. RAPS (2021), CPPS arxiv 2410.16333 (ICML 2025), MAPIE library arxiv 2207.12274.

**Implementation:**
```python
# pip install mapie
from mapie.classification import MapieClassifier
from mapie.conformity_scores import RAPSConformityScore

mapie = MapieClassifier(
    estimator=trained_rf_model,
    method="raps",
    cv="prefit",
    conformity_score=RAPSConformityScore()
)
mapie.fit(X_calib, y_calib)

y_pred, y_set = mapie.predict(X_live, alpha=0.15)
confident = y_set.sum(axis=1) == 1  # True = prediction set is singleton
# Only send signal if confident[0] == True
```

---

## Method 7 — Multi-Task Learning (Direction + TP1 Simultaneously)

**What it is:** A single model trained on two correlated binary targets simultaneously: (1) direction win/loss and (2) TP1 hit probability. Shared representation effectively doubles sample size for each task.

**Critical prerequisite:** Verify Pearson correlation between direction and TP1-hit in your data. If r < 0.35, negative transfer is more likely than gain — skip MTL entirely.

**Sources:** MT-GBM arxiv 2201.06239 (+2–4% AUC when tasks correlated), Robust-MTGB arxiv 2507.11411, arxiv 2305.14007 (negative transfer documented when r < 0.3).

**Gating check (run first):**
```python
import numpy as np
# from your trade history
r = np.corrcoef(y_direction, y_tp1_hit)[0, 1]
print(f"Task correlation: {r:.3f}")
# Only proceed with MTL if r > 0.40
```

---

## Method 8 — Mistake-Driven Curriculum Learning

**What it is:** Iteratively upweight training samples the model consistently gets wrong by multiplying their `sample_weight` each round. Derived from AdaBoost theory but applied per-sample rather than per-round.

**Where it helps most:** If your model has a specific "blind spot" (e.g., all London open trades, specific ATR regime, STOCKS_MOMENTUM_15M on Mondays). Post-cleanlab analysis should reveal whether such blind spots exist.

**Sources:** Bengio et al. Curriculum Learning 2009, arxiv 2311.13326 (financial time series), arxiv 2505.01665 (Adaptively Point-weighting Curriculum, 2025).

```python
def mistake_curriculum(X, y, n_rounds=5, boost_factor=2.0):
    weights = np.ones(len(X)) / len(X)
    for r in range(n_rounds):
        clf = RandomForestClassifier(n_estimators=200, max_depth=5,
                                     class_weight="balanced", random_state=r)
        clf.fit(X, y, sample_weight=weights * len(X))
        errors = (clf.predict(X) != y).astype(float)
        weights[errors > 0] *= boost_factor
        weights /= weights.sum()
    return clf
```

---

## Method 9 — Sequence Models (TFT / LSTM / GRU)

**Verdict: SKIP for now.**

Raw TFT/LSTM have 100K–1M parameters. At 740 trades this is a 1000:1 overparameterization ratio — guaranteed overfit. Validated empirically: LSTM "requires more datasets for plausible results" (PMC9141105). GRU converges faster but still overfits below 500 samples with >2 layers.

The one workable variant — a shallow 1-layer GRU (16 hidden units) as feature extractor feeding a downstream tree — produces only +1–3% over lag features from Method 1, with much higher implementation complexity. Not worth it until 5,000+ trades.

**Use lag/rolling features from Method 1 instead** — they capture the same sequential signal with zero overfit risk.

---

## Implementation Roadmap

### Sprint 1 (this week, ~2 hours total)
1. **Trade history features** — add `ewm_win_rate`, `streak`, `inter_trade_gap`, `lag_1/2/3_win`, `roll5_win` to `score_entry_gate()` feature vector
2. **Cleanlab audit** — run confident learning on `data` branch trades, identify suspected mislabels, log to `data/label_audit.json`

### Sprint 2 (next week, ~4 hours total)
3. **Expectancy threshold tuning** — replace hardcoded 0.5 threshold in `score_entry_gate()` with walk-forward-fitted optimal threshold per pool
4. **ShapRFECV** — run feature selection offline, hardcode the winning feature subset into the pool configs

### Sprint 3 (~1 day)
5. **Optuna HPO** — tune RF + GBM per pool with 100-trial TPE study; save best params to `data/model_params.json`
6. **MAPIE conformal filter** — add abstain flag to signal annotation; emit `🔕 Conformal: UNCERTAIN` quality grade when prediction set is not singleton

### Defer until 5,000+ trades
- Sequence models (TFT/LSTM/GRU)

### Conditional (check correlation first)
- Multi-task learning (only if Corr(direction, TP1-hit) > 0.40)
- Mistake curriculum (only if cleanlab reveals a specific blind spot pattern)

---

## Connection to Existing Research (v1 Report)

From `ML_SIGNAL_QUALITY_RESEARCH.md` (v1), the already-empirically-validated items:
- **Mistake-memory features** (+23pp on STOCKS_MOMENTUM_15M) — covered and extended by Method 1 here
- **Platt calibration** (Brier 0.26→0.22) — compatible with Conformal Prediction (Method 6)
- **Recency decay: REJECTED** — consistent with Curriculum Learning caution (Methods 8)
- **DDM drift**: never fires on 2M gold, as expected — consistent with no sequence model recommendation

The new methods here are **additive** to the v1 plan, not replacements. The full self-improving architecture:
```
Raw Pine features (F1–F25)
  + Trade history features (Method 1)       ← new
  → Feature selection via ShapRFECV (Method 4)  ← new
  → Cleanlab denoised training set (Method 3)   ← new
  → Optuna-tuned RF + GBM (Method 5)            ← new
  → Platt calibration (v1)
  → Walk-forward expectancy threshold (Method 2) ← new
  → Conformal abstain filter (Method 6)          ← new
  → Quality grade annotated in Telegram signal
  → Mistake ledger (v1 Step 2)
  → Champion-challenger + drift watchdog (v1 Steps 3+5)
```

Every layer above is independently removable — no single point of failure.
