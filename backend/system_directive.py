"""
╔══════════════════════════════════════════════════════════════════════════════╗
║         MIGO SNIPER PRO — SYSTEM DIRECTIVE v1.0                            ║
║         Embedded operating philosophy for every process in this backend.   ║
╚══════════════════════════════════════════════════════════════════════════════╝

MISSION
───────
Produce the highest-quality trading signals possible for XAU/USD and stock
pools with maximum win ratio.  Every line of code, every model, every job
exists to serve this single goal.

CORE PRINCIPLES
───────────────
1. SIGNAL QUALITY OVER QUANTITY
   A signal not sent is never a loss.  A bad signal costs real money.
   The ML gate annotates every entry — models must keep improving or be
   replaced.  Precision and recall are tracked; quality degrades → retrain.

2. LEARN FROM EVERY MISTAKE
   Every LOSS is recorded in the mistake ledger (db.py → log_mistake).
   Every Monday the system runs a SHAP autopsy: which features drove the
   losses?  Patterns that recur ≥3 weeks become hard-coded domain rules.

3. TEST BEFORE YOU ACT
   No model retrain, threshold update, or code change goes live without
   validation.  The champion-challenger protocol guards every pool:
   new model only replaces old if OOS performance improves.

4. SELF-HEAL FIRST, ALERT SECOND
   Hourly system check attempts auto-repair before raising an alert.
   Missing trades → auto-insert from webhook log.
   Duplicate records → auto-deduplicate.
   Stale models → auto-retrain when n≥50 and n%10==0 or regime shift detected.
   Only unresolvable issues escalate to Telegram.

5. NEVER CRASH SILENTLY
   Every background job is wrapped in try/except with structured logging.
   Optional deps (lightgbm, optuna, shap, tabpfn) degrade gracefully — the
   system keeps running on sklearn fallbacks if any dep is unavailable.

6. CONTINUOUS IMPROVEMENT — SCHEDULED
   • Every trade outcome → KNN weight update (online learning, immediate)
   • Every 10 new trades → RF + GBM retrain (batch, per pool)
   • Regime shift detected → emergency retrain (WR drop >5pp in 20 trades)
   • Every Sunday 20:00 UTC → walk-forward model comparison (RF vs GBM vs Joint)
   • Every Monday 09:00 UTC → SHAP loss autopsy (top-3 loss drivers)
   • Every 6 hours → full system inspection (models, data, health, auto-fix)

IMPROVEMENT ROADMAP (priority order)
──────────────────────────────────────
Phase 1 — ACTIVE (26 features, RF+GBM+KNN)
  Status: Live.  Pools with n≥50 have trained models.

Phase 2 — SMALL-DATA BOOSTERS (implement when pool reaches n≥30)
  [ ] Bayesian optimization of RF/GBM hyperparams via Optuna TPE
  [ ] Isotonic calibration upgrade (from Platt sigmoid) when n≥200
  [ ] Conformal prediction intervals — know WHEN the model is uncertain
  [ ] Online SGD classifier as 4th signal (updates every trade, no retrain)

Phase 3 — FEATURE ENGINEERING
  [ ] F26: Stochastic %K/%D (requires Pine Script update)
  [ ] Market microstructure: bid-ask spread proxy from ATR/volume ratio
  [ ] Session-of-week encoding (Monday open vs Friday close behave differently)
  [ ] Rolling win-rate of last 10 trades as meta-feature (regime awareness)

Phase 4 — JOINT & TRANSFER LEARNING (active for gold)
  [ ] JointGoldGBM: LightGBM on all 4 XAUUSD pools combined (435 trades)
  [ ] Warm-start transfer: init thin-pool model from XAUUSD_2M weights
  [ ] Stacked generalization: meta-learner on KNN+RF+GBM predictions

Phase 5 — SIGNAL QUALITY METRICS
  [ ] Kelly fraction sizing: bet size ∝ edge (p*b - q) / b
  [ ] Precision@recall curves: tune threshold per pool for target precision
  [ ] Expected-value gate: only pass signals where E[PnL] > 0 after slippage

ANTI-PATTERNS — NEVER DO THESE
────────────────────────────────
- Never retrain on the same data twice in a single cycle (lookahead leakage)
- Never use future bar data as features (only closed-bar values from Pine Script)
- Never suppress signals based on ML alone (annotate-only mode, trader decides)
- Never commit credentials to the repo
- Never push to main branch
- Never skip tests when modifying ML training, threshold, or scoring logic
"""

# ── Runtime constants derived from the directive ──────────────────────────────

SYSTEM_VERSION = "5.2.0-26F"

# Health thresholds
MIN_TRADES_FOR_ML          = 50     # minimum pool size before RF/GBM activate
MIN_TRADES_FOR_FBETA       = 80     # minimum pool size for F-beta threshold tuning
MIN_TRADES_FOR_OPTUNA      = 80     # minimum pool size for Bayesian HPO
REGIME_SHIFT_WINDOW        = 20     # trades in sliding window for regime detection
REGIME_SHIFT_DROP_PP       = 5.0    # win-rate drop (percentage points) = regime shift
CHAMPION_CHALLENGER_MIN_N  = 20     # minimum OOS predictions before rollback check

# Inspection schedule
FULL_INSPECTION_HOURS      = 6      # run deep inspection every N hours

# Mistake learning
MAX_MISTAKE_LEDGER         = 500    # keep last N losses in mistake ledger
AUTOPSY_LOOKBACK_LOSSES    = 20     # losses analyzed per weekly SHAP autopsy

# Signal quality gates
MIN_CONFIDENCE_TO_ANNOTATE = 0.40   # below this, mark signal as LOW quality
HIGH_CONFIDENCE_THRESHOLD  = 0.65   # above this, mark signal as HIGH quality


def get_directive_summary() -> dict:
    """Return a machine-readable summary of the system directive for /health endpoint."""
    return {
        "version":          SYSTEM_VERSION,
        "mission":          "highest signal quality + maximum win ratio",
        "learning_mode":    "online (per trade) + batch (per 10 trades) + weekly autopsy",
        "self_heal":        True,
        "test_before_act":  True,
        "champion_challenger": True,
        "inspection_every_hours": FULL_INSPECTION_HOURS,
        "improvement_phases": {
            "phase1_active":   True,   # KNN+RF+GBM, 26 features
            "phase2_boosters": False,  # Bayesian HPO, isotonic cal, conformal pred
            "phase3_features": False,  # F26 stochastic, microstructure
            "phase4_joint":    True,   # JointGoldGBM active
            "phase5_quality":  False,  # Kelly sizing, E[PnL] gate
        },
    }
