# Deep Research — Increasing Signal Quality via Self-Improving ML
**Date:** 10 Jun 2026 · **Method:** 5-angle literature sweep (20+ sources, confidence-rated) + 3 empirical experiments walk-forward-tested on 740 live trades from the `data` branch

---

## TL;DR

1. **Your own data is the strongest evidence, and it says:** the current deep RF/GBM configs are *harmful* out-of-sample on gold 2M (top-scored trades did WORSE, −6pp). Shallow trees fix the harm. **Nothing tested produces real lift on gold 2M with the current 25 features** — that pool has no learnable pre-trade edge yet.
2. **Mistake-memory features are the single best addition tested** — rolling hit-rates per direction/session/trigger + loss-streak length, fed as model inputs. On STOCKS_MOMENTUM_15M: **+23pp tercile lift, top-half hit-rate 63% vs 55% base**. On gold 5M: +13→27pp (small n, promising-not-proven). This is literally "the ML learning from its own mistakes."
3. **Platt calibration makes probabilities honest everywhere** (Brier 0.26→0.22) even where there's no lift — essential for trustworthy quality grades.
4. **Recency-decay weighting HURTS on your data** (−6pp at half-life 50) — your streams are stationary; decay just throws away samples. Generic advice rejected by experiment.
5. **Drift detection (DDM) never fires on your gold 2M stream** — there was never an edge to lose. Build it for the future, but it's not the current bottleneck.
6. The path to "never repeat mistakes + self-healing": **mistake ledger → memory features → champion-challenger with shadow validation → auto-rollback**. All four are buildable on your existing GitHub-data-branch architecture.

---

## Part 1 — Empirical results (walk-forward, leakage-free, expanding window)

Label = reached TP1+ (WIN/PARTIAL=1, LOSS=0). Train on trades [0:i], predict trade i, step forward. `lift` = top-scored tercile hit-rate minus bottom tercile.

### XAUUSD_2M (n=248 OOS predictions — most reliable)
| Config | lift | top-half HR | Brier |
|---|---:|---:|---:|
| RF current (deep, balanced) | **−5.9pp** | 27.8% | 0.260 |
| GBM current | **−6.0pp** | 33.9% | 0.288 |
| RF shallow (depth4, leaf8) | +2.4pp | 31.5% | 0.257 |
| GBM shallow (d2, sub0.8) | 0.0pp | 30.6% | **0.250** |
| Logistic L2 | +2.4pp | 31.5% | 0.263 |
| RF shallow + recency hl=50 | −6.0pp | 27.4% | 0.263 |
| Calibrated variants (all) | −12→−4pp | — | **0.220-0.222** |

**Verdict:** no config finds edge. Base rate 31.5%; everything lands 28–34%. The 25 features don't separate winners from losers at 2M granularity. The DDM drift simulation confirms: rolling hit-rate oscillates 23–40% with zero drift events — stationary no-edge, not a decayed model.

### XAUUSD_5M (n=45 OOS — indicative only)
| Config | lift | top-half HR |
|---|---:|---:|
| LogitCal top8 | +26.7pp | 30.4% |
| RFshallow+Cal top8 | +20.0pp | **43.5%** (base 31%) |
| GBMshallow+Cal **+MEMORY** | **+26.7pp** | 39.1% |

### STOCKS_MOMENTUM_15M (n=38 OOS — indicative only)
| Config | lift | top-half HR | Brier |
|---|---:|---:|---:|
| LogitCal top8 (no memory) | −7.7pp | 52.6% | 0.266 |
| LogitCal top8 **+MEMORY** | **+23.1pp** | **63.2%** (base 55%) | **0.249** |
| GBMshallow+Cal **+MEMORY** | +7.7pp | 57.9% | 0.247 |

**The MEMORY features** (computed leakage-free from past trades only): rolling TP1+ rate of last-10 overall / same-direction / same-session / same-trigger trades + current loss-streak length. Adding them flipped MOMENTUM_15M from −7.7pp to +23.1pp with the same model.

---

## Part 2 — Research findings (5 agents, confidence-rated, key claims)

### Meta-labeling / triple-barrier (López de Prado)
- Mechanism is sound and matches your architecture: Pine = primary (direction), backend = secondary (bet/no-bet). Documented gains: precision 0.48→0.54; 0.21→0.39 (Hudson & Thames JFDS). **HIGH confidence.**
- **No published evidence at 300–800 trades** — small-sample efficacy is unvalidated. Practitioner guidance for limited data: logistic regression or depth-2/3 trees, ≤5–8 features, calibrated, threshold ~0.5–0.55. **The absence of evidence is itself the finding.**
- Triple-barrier labeling = exactly your TP/SL/(no time barrier yet) scheme — you already do this naturally.

### Sample weighting & calibration
- **Isotonic calibration overfits below ~1000 samples — use Platt/sigmoid** (sklearn docs, Niculescu-Mizil & Caruana). **HIGH.** ✅ Confirmed by our Brier improvements.
- **SMOTE/oversampling at n<1000 wrecks calibration with no AUC gain** (van den Goorbergh, JAMIA 2022). Train natural distribution → calibrate → move the threshold. **HIGH.**
- Your 35/65 imbalance is mild — needs threshold choice only, not resampling.
- min_samples_leaf ≥5, RF depth 4–8, GBM depth 2–3 at n<1000. ✅ Confirmed: shallow beat deep on your data.
- Recency decay "tune by experiment, no universal value" — ⚠️ our experiment says: **don't use it on your data today.**

### Validation (leakage control)
- Purged K-fold + ~1% embargo for overlapping labels; walk-forward efficiency ≥50% as pass bar. Anchored (expanding) window correct at your scale; switch to rolling only past ~200–500 trades/pool.
- **AUC is unreliable at your scale** — RF needs ~3,400 samples for stable AUC (JMIR); with 25 features and ~100–150 positive events you have 6–16 events/variable, below even logistic's threshold. **Use hit-rate lift vs base + Brier skill score instead** (what we did), and **cut to ≤8 features**.

### Drift & retraining
- Practical detectors on a slow stream: DDM (warning 2σ → start shadow retrain; drift 3σ → swap), Page-Hinkley on per-trade PnL as second vote; both in `river`. **HIGH.**
- Consensus cadence: weekly scheduled retrain as floor + drift-trigger override.
- **Do NOT split per-regime models at current data size** — regime as a feature only, until ≥100 trades/regime. (You already learned this lesson with pools.)

### Self-healing ops & mistake ledgers
- **Champion-challenger:** challenger shadow-scores every entry, promoted only after ≥100 trades AND ≥2 weeks beating champion on expectancy. Trading-specific minimums: 100 trades = noise floor, 200–300+ for confidence. **HIGH.**
- **Rollback:** versioned weights + pointer swap (your data branch already gives you this for free — keep last-known-good weights files, revert when rolling metric drops below champion baseline).
- **Mistake ledger (practitioner-documented):** tag every LOSS with cause category + condition tags, aggregate R-impact per tag ("moved-stop trades = −14R this quarter"), convert repeat offenders into hard rules. Review cadence matters as much as logging.
- **Streak circuit-breakers:** 3-loss stops are statistically noise (12.5% at 50% WR); 6–7 consecutive rule-compliant losses (<2%) is a defensible trigger — and should mean "regime mismatch, de-weight this setup," not panic-stop.

---

## Part 3 — Implementation plan (mapped to your three goals)

### Goal A — "ML learns from mistakes and self-improves"
**A1. Mistake-memory features (HIGHEST PRIORITY — empirically validated on your data).**
Add 5 features to the gate/ensemble input: rolling TP1+ rate last-10 overall / same-direction / same-session / same-trigger + loss-streak length. Computed from the pool's own history at score time — zero new data needed, leakage-free by construction.
**A2. Calibrated shallow models.** Replace deep RF/GBM with: GBM(d2, sub0.8) + RF(d4, leaf8) + logistic, all wrapped in `CalibratedClassifierCV(method="sigmoid", cv=3)`, max 8 features (selected on train only). Honest probabilities even before lift appears.
**A3. PnL-graded rewards** — ✅ already shipped (`ab727d5f`).
**A4. Gold 2M: stop pretending.** Show "model warming up" grade until a config proves lift in shadow. The fix for 2M is *features* (entry-time spread, distance-to-level, burst momentum), not more model tuning.

### Goal B — "System never repeats past mistakes"
**B1. Mistake ledger (`data/mistake_ledger.json`).** Auto-tag every LOSS: {pool, trigger, session, regime, direction, streak-at-entry, quality-grade-given}. Weekly job aggregates cost per tag and posts the top-3 bleeding patterns to Telegram ("OVERLAP-session gold scalps: −31R lifetime").
**B2. Hard-rule promotion.** When a tag's pattern shows ≥30 trades AND hit-rate ≥10pp below pool base across 2+ regimes → auto-add to a `learned_rules.json` blocklist the gate consults. Rules never silently expire; monthly re-validation only.
**B3. Streak de-weighting.** 6+ consecutive losses on a {pool, trigger} combo → gate score ×0.5 for that combo until a win resets it.

### Goal C — "Self-healing, solid base for Phases 2–4"
**C1. Champion-challenger registry.** `data/models/{pool}/champion.json` + `challenger.json`. Challenger (new config/features) shadow-scores every entry; its would-have-been grades logged beside champion's. Promotion: ≥100 shadow trades AND ≥2 weeks AND higher calibrated expectancy. Demotion/rollback: champion's rolling-50 Brier or hit-rate drops below challenger or below "always-predict-base-rate" → swap, alert Telegram.
**C2. Drift watchdog.** DDM on per-trade outcomes + Page-Hinkley on per-trade PnL per pool (river or ~40 lines hand-rolled). Warning → spawn challenger retrain; drift → alert + force shadow re-validation. Weekly scheduled retrain stays as floor.
**C3. Evaluation standard (lock it in now).** Every future model claim must show: walk-forward (no shuffling), hit-rate lift vs base + Brier skill score (never AUC at this scale), ≥50% walk-forward efficiency, and shadow-mode confirmation before gating live. This single discipline is what makes Phases 2–4 trustworthy.

### Sequencing
| Step | What | Effort | Why first |
|---|---|---|---|
| 1 | A1 memory features + A2 calibrated shallow models in `score_entry_gate` | ~1 day | Only change with empirical lift on your data |
| 2 | B1 mistake ledger + weekly Telegram autopsy | ~half day | Starts accumulating structured mistake data immediately |
| 3 | C1 champion-challenger + versioned weights rollback | ~1 day | Safety rail before any future model change |
| 4 | B2/B3 rule promotion + streak de-weighting | ~half day | Needs ledger data from step 2 |
| 5 | C2 drift watchdog | ~half day | Lowest urgency (no drift detected today) |

### Honest expectations
- Stocks pools: grades should become genuinely useful within weeks (signal confirmed).
- Gold 5M: promising, needs ~100 more trades to confirm.
- Gold 2M: no pre-trade edge with current features — volume + new features are the only fixes. Don't let any model gate it until shadow-proven.
- All lifts measured on ≤45 OOS samples except gold 2M; treat as direction, not destination — that's exactly what shadow mode (C1) is for.

---
*Sources available in the research transcripts; key ones: López de Prado AFML ch.3/4/7; Hudson & Thames JFDS meta-labeling papers; sklearn calibration docs; Niculescu-Mizil & Caruana 2005; van den Goorbergh et al. JAMIA 2022; van der Ploeg et al. (events-per-variable); river drift docs; DataRobot/MLflow champion-challenger patterns; EdgeFlo/BacktestBase trade-sample minimums.*
