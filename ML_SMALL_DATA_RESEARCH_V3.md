# ML for Small Data — Research Report v3
*Generated: 2026-06-10 | Focus: data scarcity at n=50–319 per pool | Adversarially verified*

---

## The Core Problem

| Pool | Trades | ML Viability |
|------|--------|-------------|
| XAUUSD_2M | 319 | Marginal edge (RF shallow +3.5pp walk-forward) |
| XAUUSD_5M | ~84 | Feature selection helps (+26pp), unstable at this n |
| STOCKS_MOMENTUM_15M | ~81 | Memory features +23pp — real edge |
| STOCKS_MOMENTUM_30M | ~51 | Too thin for walk-forward |
| Everything else | <60 | Pure noise — training on this hurts |

15 of 19 pools have fewer than 60 trades. No algorithm fixes that — but three approaches can multiply the *effective* training data without needing more live trades.

---

## Ranking Table (validated, adversarially verified)

| Rank | Method | Min n | Financial Validation | Complexity | Expected Lift (n<200) | Risk |
|------|--------|-------|---------------------|------------|----------------------|------|
| **1** | **Joint pool training** (timeframe_id feature) | 50/pool, joint ~300+ | ✅ High (JFE volatility 2024, pooled >> per-asset at small n) | Low | **+5–15% F1** | Low |
| **2** | **TabPFN v2** (pre-trained in-context learner) | 10 | ✅ Moderate (Nature 2025, beats XGBoost at n<10K) | Very Low | **+5–20% F1** | Medium (IID assumption) |
| **3** | **GBM warm-start transfer** (2M→5M) | ~30 target | Moderate (arXiv:2311.03283) | Low | **+3–12% F1** | Low-Medium |
| 4 | SMOTE + BaggingClassifier | 50 | ✅ High (financial distress literature) | Very Low | +3–8% F1 | Medium |
| 5 | Gaussian Process Classifier | 20 | Moderate | Low | +2–8% vs RF | Low |
| 6 | TabDDPM synthetic augmentation | 200+ | Low (not validated at n<100) | High | +0–8% | HIGH at n<100 |
| 7 | MAML / ProtoNets | ~500+ tasks | ❌ Not validated tabular financial | Very High | Unknown | High |
| 8 | CTGAN | 200+ | ❌ F1 utility ratio 0.44 at n<150 (2026 study) | High | **NEGATIVE** | Very High |

---

## Method 1 — Joint Pool Training (HIGHEST PRIORITY)

**What it is:** Instead of training one model per pool, train a single LightGBM on all related pools together, with a `timeframe_id` feature (0=2M, 1=5M, 2=30M, 3=1H). The tree splits learn timeframe-specific boundaries naturally.

**Why it works:** With n=50–100 per pool, variance dominates over bias. Pooling reduces variance by multiplying effective n (JFE 2024: pooled neural nets outperformed per-asset across all horizons; the same principle applies to tree models). Your 4 gold pools combined = ~497 trades — 4× more signal for each pool.

**Key precondition met:** All pools share identical feature space (F1–F25). The `timeframe_id` feature is the only addition needed.

**Negative transfer risk:** Low. Same asset (XAUUSD), same feature definitions, adjacent regimes. Risk would be high for daily→intraday (different regime), but 2M/5M/30M/1H are the same microstructure regime at different scales.

**Stock pooling:** Keep separate from gold. Add `symbol_cluster_id` feature within stock clusters (MOMENTUM / QUALITY / INDEX / QQQ / SPX500). 5 stock clusters × 3 timeframes each = ~15 pools → ~300 stock trades combined.

```python
# Two joint models replace 19 per-pool models:
# 1. JointGoldGBM — trains on XAUUSD_2M + 5M + 30M + 1H (timeframe_id 0-3)
# 2. JointStocksGBM — trains on all stock pools (cluster_id 0-4, tf_id 0-2)
```

---

## Method 2 — TabPFN v2 as 4th Signal

**What it is:** A tabular foundation model pre-trained on 130 million synthetic tabular tasks (Bayesian in-context learning). Pass (X_train, y_train, X_test) — no training, no hyperparameters, predictions in <3 seconds.

**Why it's remarkable for small data:** Works at n≥10. Beats tuned XGBoost at n<10,000 (Nature 2025). No overfitting possible because it doesn't train on your data — it uses it as in-context examples. Version 2.5 (Nov 2025) supports up to 500 features.

**Critical limitation:** Assumes IID data (no temporal structure). Mitigate by using it as one signal alongside your walk-forward GBM, not as a standalone. Also degrades on class imbalance — threshold tuning (already implemented) fixes this.

**Integration:** Add as 4th component in `score_entry_gate()` alongside KNN/RF/GBM. Blend at 30% weight initially; increase if walk-forward shows lift.

**Cost:** `pip install tabpfn` — single dependency, CPU-only is fast enough for inference.

---

## Method 3 — GBM Warm-Start Transfer (2M → Thin Pools)

**What it is:** Train GBM on XAUUSD_2M (n=319), save model, then fine-tune on XAUUSD_5M (n=84) using XGBoost's `xgb_model` warm-start. The source trees provide a better initialization than random — target model only needs to add 40–60 correction trees.

**Expected lift:** +3–12% F1 on target pool when target n_train<60. At n_train>80, fresh model catches up and transfer advantage shrinks. Biggest benefit for thin pools (30M, 1H, stock 4H).

**Risk mitigation built in:** Walk-forward A/B comparison explicitly measures if transfer helps or hurts. If average lift < 0, fall back to per-pool model.

---

## Method 4 — SMOTE + BaggingClassifier (Quick Win for n<80)

**What it is:** Oversample the minority class (LOSS or WIN depending on pool), then train a `BaggingClassifier(max_samples=0.8, bootstrap=False)` of shallow decision trees. The `bootstrap=False` with `max_samples=0.8` avoids duplicating samples (standard bootstrap duplicates ~37% — bad at tiny n).

**When to use:** Pools with n=40–80 where RF/GBM report "too few for walk-forward." Better than nothing, much better than training on unbalanced data.

**When NOT to use:** Pools with n<40. At that scale SMOTE creates artifacts that make things worse.

---

## Methods to NEVER Implement

**CTGAN at n<150:** F1 utility ratio 0.44–0.55 in 2026 benchmarks. The discriminator memorizes the small real dataset → mode collapse → synthetic samples that are worse than real ones. Actively harmful.

**MAML / Prototypical Networks:** Require 100+ meta-training tasks for the meta-learner itself. You have 19 pools. Theoretically inapplicable.

**TabDDPM at n<100:** Not validated at this scale. Denoising network risks memorizing training data. Revisit when pools reach n≥200.

**Active Learning:** Wrong tool — requires ability to select which samples to label. You can't choose which trades to take.

---

## Data Acceleration (Fastest Path to More Data)

| Strategy | Speed | Feasibility | Risk |
|----------|-------|-------------|------|
| **Pine Script historical replay** | ~200 trades/session per pool | High | Survivorship bias (validate carefully) |
| Joint pool training (above) | Immediate — no new data | High | None |
| Warm-start transfer | Immediate | High | Low-medium |
| Lower timeframe pools (add 1M) | 2–4× more signals | Medium | New regime characteristics |

**Pine Script replay is the most impactful non-ML action:** Run `strategy()` mode on 2 years of historical 2M/5M bars. Each session generates hundreds of historical trades with F1–F25 features already computed. This is the fastest route to n=200 for every thin pool.

**How to validate replay data:** Check that `alertcondition` in replay matches live conditions exactly. Spot-check 10 random replay trades against what the live system would have done.

---

## Implementation Sequence

### Week 1 — Joint Pool Training
- `JointGoldGBM` class in `ml_ensemble.py` — LightGBM on all 4 XAUUSD pools with `timeframe_id`
- `JointStocksGBM` class — all stock pools with `cluster_id`
- Replace per-pool RF/GBM in `score_entry_gate()` with joint models
- **Immediate effect:** XAUUSD_5M goes from n=84 to n≈497 effective training data

### Week 2 — TabPFN v2
- `pip install tabpfn` in `requirements.txt`
- `TabPFNEnsemble` wrapper class with caching (refit only when new history arrives)
- Add as 4th component in `score_entry_gate()` at 0.30 weight
- Walk-forward validate per pool before increasing weight

### Week 3 — Warm-Start Transfer
- `train_source_and_transfer(source_pool, target_pool, history)` function
- A/B test per fold: if lift>0, use transfer; else fall back to per-pool
- Apply to all thin pools (<80 trades) automatically

### Ongoing (User Action)
- Pine Script: run `strategy()` replay on 2 years of historical data for each pool
- Import replay trades into data branch as `data/trade_history_{pool}_replay.json`
- Backend: blend replay + live trades at training time (replay weighted 0.5× vs live)

---

## Connection to Previous Research

This builds on v1 (mistake memory, calibration) and v2 (feature selection, expectancy threshold):
```
Joint pool training                   ← v3 (this)
  + Memory features (v1)
  + Top-8 feature selection (v2)
  + Platt calibration (v1)
  + Expectancy threshold (v2)
  + TabPFN v2 as 4th signal           ← v3 (this)
  + Warm-start transfer               ← v3 (this)
  + Champion-challenger rollback (v2)
  + Mistake ledger + weekly autopsy (v2)
```

Every layer is independently removable — no single point of failure.

---

## Sources
- Volatility Forecasting with Pooled ML (Oxford JFE 2024)
- MT-GBM: Multi-Task Gradient Boosting Machine (arXiv:2201.06239)
- TabPFN v2: Accurate Predictions on Small Data (Nature, Jan 2025)
- TabPFN v2.5 (arXiv:2511.08667, Nov 2025)
- Risk of Transfer Learning in Finance (arXiv:2311.03283)
- Adapting tree boosting for Transfer Learning (arXiv:2002.11982)
- CTGAN/SMOTE/TabDDPM comparison (MDPI 2026)
- Characterizing and Avoiding Negative Transfer (arXiv:1811.09751)
- Day Trading with Multi-Task Learning (Springer 2014)
