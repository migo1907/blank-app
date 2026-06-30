"""
Ensemble models for XAU/USD trade outcome prediction.
  - RandomForestEnsemble   : existing RF model
  - GradientBoostEnsemble  : XGBoost-equivalent via sklearn GradientBoosting (item 2)
Both support session-weighted training (item 5): London/NY trades weighted 1.3×.
Both support quality-weighted training: full TP3 run > TP2 stopped > TP1 stopped.
Requires scikit-learn >= 1.4.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

MIN_TRADES = 30  # minimum history before models will train


def _win_label(row: dict) -> int:
    """Binary training label — delegates to the canonical is_win() so gates and
    models share one win definition (PARTIAL counts only when pnl_pct > 0)."""
    from ml_model import is_win
    return 1 if is_win(row) else 0

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import TimeSeriesSplit
    import numpy as np
    _SKLEARN_AVAILABLE = True
except Exception:
    _SKLEARN_AVAILABLE = False

# Minimum trades before isotonic calibration is fitted (needs enough OOS data)
_ISO_MIN_TRADES = 150

from ml_model import FEATURE_NAMES, row_to_vector


def _session_weight(created_at: str) -> float:
    """Return sample weight based on session quality. London/NY = 1.3, Asian/Off = 0.6."""
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        h = dt.hour
        if 7 <= h < 10:   return 1.30   # London open
        if 12 <= h < 16:  return 1.25   # NY + overlap
        if 0 <= h < 7:    return 0.60   # Asian
        if 20 <= h < 24:  return 0.60   # Off hours
        return 1.00
    except Exception:
        return 1.00


# tp_stage values sent by Pine: "TP3" | "SL_TP2" | "SL_TP1" | "SL" | ""
_QUALITY_WEIGHT: dict[str, float] = {
    "TP3":    1.00,   # full run — strongest learning signal
    "SL_TP2": 0.70,   # hit TP2, stopped at tightened trail — good signal
    "SL_TP1": 0.35,   # hit TP1 only, stopped at trail — weak positive
    "SL":     1.00,   # clean loss before TP1 — penalise fully
    "":       0.60,   # unknown / legacy trade — moderate weight
}

def _quality_weight(row: dict) -> float:
    """Return sample weight based on how far the trade ran (tp_stage)."""
    stage = row.get("tp_stage", "") or ""
    return _QUALITY_WEIGHT.get(stage, 0.60)


def _label_noise_weight(row: dict) -> float:
    """Label-noise correction (Phase 5).

    A LOSS that ran meaningfully in our favour (high max-favorable-excursion) before
    reversing into a stop is a NOISY direction label: the entry call wasn't wrong —
    the trade got stopped by the exit (spread / slippage / trail). Downweighting these
    stops the models from 'learning to avoid' setups that were actually right; the R:R
    leak is handled separately by the exit optimizer, not by penalising the entry.

    Wins and clean immediate losses keep full weight. Scale-invariant (MFE-vs-loss
    ratio) so it works across gold scalps and stock swings. Floors at 0.5 so a noisy
    loss is never fully discarded. Graceful 1.0 when mfe/pnl are missing (legacy rows).
    """
    if _win_label(row) == 1:
        return 1.0
    try:
        mfe   = abs(float(row.get("mfe") or 0.0))
        entry = float(row.get("entry_price") or 0.0)
        pnl   = abs(float(row.get("pnl_pct") or 0.0))
        if entry <= 0 or pnl <= 0:
            return 1.0
        # How far it went in our favour vs the realized loss. ratio ≤ 1 → it never
        # really went our way (clean loss, full weight). ratio ≥ 3 → it ran 3× the
        # loss in our favour then reversed (very noisy) → floor at 0.5.
        ratio = (mfe / entry * 100.0) / pnl
        if ratio <= 1.0:
            return 1.0
        return max(0.5, 1.0 - min((ratio - 1.0) / 2.0, 1.0) * 0.5)
    except Exception:
        return 1.0


class RandomForestEnsemble:
    """
    Wraps sklearn RandomForestClassifier for XAU/USD WIN/LOSS prediction.

    Usage:
        rf = RandomForestEnsemble()
        rf.retrain(history)          # list[dict] from recent_outcomes()
        prob = rf.predict(feat_list) # list[float], 20 values
    """

    def __init__(self, n_estimators: int = 200, max_depth: int = 4, min_samples_leaf: int = 8, random_state: int = 42):
        self._n_estimators = n_estimators
        self._max_depth = max_depth
        self._min_samples_leaf = min_samples_leaf
        self._random_state = random_state
        self._model: Optional[object] = None  # CalibratedClassifierCV(RF) once trained
        self._prev_model: Optional[object] = None  # champion-challenger rollback point
        self._trained = False
        self._lock = threading.Lock()
        self._feature_importances: list[float] = [1.0 / len(FEATURE_NAMES)] * len(FEATURE_NAMES)
        self._feature_indices: list[int] = list(range(len(FEATURE_NAMES)))  # selected feature subset
        self._iso_calibrator: Optional[object] = None  # isotonic post-hoc calibrator (≥150 trades)
        self._conformal_q: float = 0.20  # 90th-pctile OOS error — conformal interval half-width

    # ── Training ─────────────────────────────────────────────────────────────

    def retrain(self, history: list[dict]) -> bool:
        """
        Train (or retrain) the RF on stored trade history.

        Args:
            history: list of trade_outcome dicts from recent_outcomes().
                     Each dict must contain FEATURE_NAMES columns + 'outcome'.

        Returns:
            True if training succeeded, False otherwise.
        """
        if not _SKLEARN_AVAILABLE:
            print("[rf] scikit-learn not available — RF disabled.")
            return False

        if len(history) < MIN_TRADES:
            print(f"[rf] Only {len(history)} trades available (need {MIN_TRADES}) — skipping retrain.")
            return False

        # Sort chronologically so TimeSeriesSplit never leaks future trades into calibration
        history = sorted(history, key=lambda r: r.get("created_at", ""))

        # Build X, y
        X_rows = []
        y_rows = []
        for row in history:
            feat_vec = row_to_vector(row)
            X_rows.append(feat_vec)
            y_rows.append(_win_label(row))

        X = np.array(X_rows, dtype=np.float64)
        y = np.array(y_rows, dtype=np.int32)

        # Walk-forward split computed up front so feature selection never sees OOS labels.
        oos_size = max(int(len(X_rows) * 0.20), 1)
        train_size = len(X_rows) - oos_size

        # Feature selection: top-8 by |correlation| when n>=80 (validated: +3.5–20pp lift).
        # Correlation is computed on the TRAINING slice only — selecting on the full set
        # leaked OOS labels into which features were kept, inflating the OOS metric.
        if len(X_rows) >= 80:
            try:
                _Xsel, _ysel = X[:train_size], y[:train_size]
                corr_matrix = np.corrcoef(_Xsel.T, _ysel)
                corr = np.abs(corr_matrix[:-1, -1])
                corr = np.where(np.isnan(corr), 0.0, corr)
            except Exception:
                corr = np.zeros(X.shape[1])
            new_feature_indices = np.argsort(corr)[::-1][:8].tolist()
        else:
            new_feature_indices = list(range(len(FEATURE_NAMES)))
        X = X[:, new_feature_indices]

        # Shallow RF: depth=4, min_leaf=8 — walk-forward validated (+3.5pp vs -7.7pp for deep)
        base_clf = RandomForestClassifier(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            min_samples_leaf=self._min_samples_leaf,
            class_weight="balanced",
            random_state=self._random_state,
            n_jobs=-1,
        )

        # Combined weight: session quality × signal quality (tp_stage) × label-noise correction
        sample_weights = np.array(
            [_session_weight(row.get("created_at", "")) * _quality_weight(row) * _label_noise_weight(row) for row in history],
            dtype=np.float64
        )

        # Walk-forward OOS eval (split already computed above) — honest accuracy + isotonic data
        new_iso = None
        if train_size >= MIN_TRADES and oos_size >= 5 and len(set(y[:train_size].tolist())) >= 2:
            try:
                _n_splits_oos = 2 if train_size < 45 else 3
                _oos_tscv = TimeSeriesSplit(n_splits=_n_splits_oos)
                _oos_clf = CalibratedClassifierCV(
                    RandomForestClassifier(
                        n_estimators=self._n_estimators, max_depth=self._max_depth,
                        min_samples_leaf=self._min_samples_leaf, class_weight="balanced",
                        random_state=self._random_state, n_jobs=-1,
                    ), method="sigmoid", cv=_oos_tscv,
                )
                _oos_clf.fit(X[:train_size], y[:train_size], sample_weight=sample_weights[:train_size])
                _oos_proba = _oos_clf.predict_proba(X[train_size:])
                _oos_classes = list(_oos_clf.classes_)
                _win_idx = _oos_classes.index(1) if 1 in _oos_classes else -1
                if _win_idx >= 0:
                    _oos_proba_win = _oos_proba[:, _win_idx]
                    _oos_preds = (_oos_proba_win >= 0.5).astype(int)
                    _oos_acc = float(np.mean(_oos_preds == y[train_size:]))
                    print(f"[rf] Walk-forward OOS accuracy ({oos_size} trades): {_oos_acc:.3f}")
                    _oos_errors = np.abs(_oos_proba_win - y[train_size:].astype(float))
                    # Floor q so a near-perfect (often degenerate) OOS fold can't
                    # collapse the interval to ~0 and masquerade as max certainty.
                    self._conformal_q = max(0.05, float(np.percentile(_oos_errors, 90)))
                    print(f"[rf] Conformal q={self._conformal_q:.3f} (90th-pctile OOS error, {oos_size} trades)")
                    # Isotonic needs both classes present in the OOS slice it fits on,
                    # else it degenerates to a flat mapping that poisons inference.
                    if len(X_rows) >= _ISO_MIN_TRADES and len(set(y[train_size:].tolist())) >= 2:
                        _iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
                        _iso.fit(_oos_proba_win, y[train_size:])
                        new_iso = _iso
                        print(f"[rf] Isotonic calibrator fitted on {oos_size} OOS trades")
            except Exception as _oos_exc:
                print(f"[rf] OOS eval failed: {_oos_exc}")

        # Platt calibration: TimeSeriesSplit prevents future-data leakage into calibration folds
        n_splits = 3 if len(X_rows) >= 45 else 2
        tscv = TimeSeriesSplit(n_splits=n_splits)
        clf = CalibratedClassifierCV(base_clf, method="sigmoid", cv=tscv)

        try:
            clf.fit(X, y, sample_weight=sample_weights)
        except Exception as exc:
            print(f"[rf] Training failed: {exc}")
            return False

        # Feature importances from the underlying estimators inside CalibratedClassifierCV
        imps_list = [
            est.estimator.feature_importances_
            for est in clf.calibrated_classifiers_
            if hasattr(est.estimator, "feature_importances_")
        ]
        raw_imps = np.mean(imps_list, axis=0) if imps_list else np.ones(len(FEATURE_NAMES)) / len(FEATURE_NAMES)

        with self._lock:
            self._prev_model = self._model  # save champion for rollback
            self._model = clf
            self._trained = True
            self._feature_indices = new_feature_indices  # swap atomically with the model
            self._feature_importances = raw_imps.tolist()
            self._iso_calibrator = new_iso

        top_feat = FEATURE_NAMES[new_feature_indices[int(np.argmax(raw_imps))]]
        n_feats = len(new_feature_indices)
        iso_tag = "+iso" if new_iso else ""
        print(f"[rf] Retrained on {len(X_rows)} trades (shallow+Platt{iso_tag}, {n_feats}f). Top feature: {top_feat}")
        return True

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict(self, features: list[float]) -> float:
        """
        Predict WIN probability for a given 26-feature vector.

        Returns:
            float in [0.0, 1.0]. Returns 0.5 if model not yet trained.
        """
        if not _SKLEARN_AVAILABLE or not self._trained or self._model is None:
            return 0.5

        if len(features) != len(FEATURE_NAMES):
            print(f"[ensemble] Feature vector length {len(features)} != expected {len(FEATURE_NAMES)} — returning 0.5")
            return 0.5

        X = np.array([[features[i] for i in self._feature_indices]], dtype=np.float64)
        try:
            with self._lock:
                proba = self._model.predict_proba(X)[0]
                iso = self._iso_calibrator
            classes = list(self._model.classes_)
            win_idx = classes.index(1) if 1 in classes else -1
            p = float(proba[win_idx]) if win_idx >= 0 else 0.5
            if iso is not None:
                p = float(iso.predict([p])[0])
            return p
        except Exception as exc:
            print(f"[rf] predict error: {exc}")
            return 0.5

    def predict_with_interval(self, features: list[float]) -> tuple[float, float, float, float]:
        """Return (score, lo, hi, width) using conformal prediction interval.
        Width reflects calibration uncertainty — narrow = reliable, wide = uncertain."""
        score = self.predict(features)
        q = self._conformal_q
        lo, hi = max(0.0, score - q), min(1.0, score + q)
        return score, lo, hi, hi - lo

    # ── Feature importance ────────────────────────────────────────────────────

    @property
    def feature_importances(self) -> list[float]:
        """RF feature importances (25 values, sum to 1.0). Uniform if not trained."""
        return list(self._feature_importances)

    @property
    def is_trained(self) -> bool:
        return self._trained

    def top_features(self, n: int = 5) -> list[tuple[str, float]]:
        """Return top-n features by RF importance as [(name, importance), ...]."""
        paired = list(zip(FEATURE_NAMES, self._feature_importances))
        paired.sort(key=lambda x: x[1], reverse=True)
        return paired[:n]


    def rollback(self) -> bool:
        """Restore previous champion model (champion-challenger safety net)."""
        if self._prev_model is None:
            return False
        with self._lock:
            self._model, self._prev_model = self._prev_model, self._model
        print("[rf] Rolled back to previous champion model.")
        return True

    # Alias so scheduler.py can call rf.train() interchangeably
    def train(self, history: list[dict]) -> bool:
        return self.retrain(history)


# ── Pool-aware singletons — one RF per pool ──────────────────────────────────

_rf_pool: dict[str, RandomForestEnsemble] = {}
_rf_pool_lock = threading.Lock()


def get_rf(pool: str = "XAUUSD") -> RandomForestEnsemble:
    """Get or create a RandomForestEnsemble for the given pool."""
    if pool not in _rf_pool:
        with _rf_pool_lock:
            if pool not in _rf_pool:  # double-checked locking
                _rf_pool[pool] = RandomForestEnsemble()
    return _rf_pool[pool]


# ── Gradient Boosting Ensemble (item 2 — XGBoost equivalent) ─────────────────

class GradientBoostEnsemble:
    """
    sklearn GradientBoostingClassifier as XGBoost equivalent.
    Better than RF on small datasets (42-200 trades) due to sequential boosting.
    Uses session-weighted training (item 5).
    """

    def __init__(self, n_estimators: int = 60, max_depth: int = 2, learning_rate: float = 0.08):
        self._n_estimators  = n_estimators
        self._max_depth     = max_depth
        self._learning_rate = learning_rate
        self._model: Optional[object] = None
        self._prev_model: Optional[object] = None
        self._trained = False
        self._lock = threading.Lock()
        self._feature_importances: list[float] = [1.0 / len(FEATURE_NAMES)] * len(FEATURE_NAMES)
        self._feature_indices: list[int] = list(range(len(FEATURE_NAMES)))
        self._iso_calibrator: Optional[object] = None  # isotonic post-hoc calibrator (≥150 trades)
        self._conformal_q: float = 0.20  # 90th-pctile OOS error — conformal interval half-width

    def train(self, history: list[dict]) -> bool:
        if not _SKLEARN_AVAILABLE:
            return False
        if len(history) < MIN_TRADES:
            print(f"[gbm] Only {len(history)} trades — skipping train.")
            return False

        # Sort chronologically so TimeSeriesSplit never leaks future trades into calibration
        history = sorted(history, key=lambda r: r.get("created_at", ""))

        X_rows, y_rows, w_rows = [], [], []
        for row in history:
            X_rows.append(row_to_vector(row))
            y_rows.append(_win_label(row))
            w_rows.append(_session_weight(row.get("created_at", "")) * _quality_weight(row) * _label_noise_weight(row))

        if len(set(y_rows)) < 2:
            print(f"[gbm] Only one class in training data ({set(y_rows)}) — skipping train until wins accumulate.")
            return False

        X = np.array(X_rows, dtype=np.float64)
        y = np.array(y_rows, dtype=np.int32)
        w = np.array(w_rows, dtype=np.float64)

        # Walk-forward split up front so feature selection never sees OOS labels.
        oos_size_gbm = max(int(len(X_rows) * 0.20), 1)
        train_size_gbm = len(X_rows) - oos_size_gbm

        # Feature selection: top-8 by |correlation| when n>=80 — TRAINING slice only.
        if len(X_rows) >= 80:
            try:
                _Xsel, _ysel = X[:train_size_gbm], y[:train_size_gbm]
                corr_matrix = np.corrcoef(_Xsel.T, _ysel)
                corr = np.abs(corr_matrix[:-1, -1])
                corr = np.where(np.isnan(corr), 0.0, corr)
            except Exception:
                corr = np.zeros(X.shape[1])
            new_feature_indices = np.argsort(corr)[::-1][:8].tolist()
        else:
            new_feature_indices = list(range(len(FEATURE_NAMES)))
        X = X[:, new_feature_indices]

        # Walk-forward OOS eval (split already computed above) — honest accuracy + isotonic data
        new_iso_gbm = None
        if train_size_gbm >= MIN_TRADES and oos_size_gbm >= 5 and len(set(y[:train_size_gbm].tolist())) >= 2:
            try:
                _n_splits_oos = 2 if train_size_gbm < 45 else 3
                _oos_tscv = TimeSeriesSplit(n_splits=_n_splits_oos)
                _oos_base = GradientBoostingClassifier(
                    n_estimators=self._n_estimators, max_depth=self._max_depth,
                    learning_rate=self._learning_rate, subsample=0.8, random_state=42,
                )
                _oos_clf = CalibratedClassifierCV(_oos_base, method="sigmoid", cv=_oos_tscv)
                _oos_clf.fit(X[:train_size_gbm], y[:train_size_gbm], sample_weight=w[:train_size_gbm])
                _oos_proba = _oos_clf.predict_proba(X[train_size_gbm:])
                _oos_classes = list(_oos_clf.classes_)
                _win_idx = _oos_classes.index(1) if 1 in _oos_classes else -1
                if _win_idx >= 0:
                    _oos_proba_win = _oos_proba[:, _win_idx]
                    _oos_preds = (_oos_proba_win >= 0.5).astype(int)
                    _oos_acc = float(np.mean(_oos_preds == y[train_size_gbm:]))
                    print(f"[gbm] Walk-forward OOS accuracy ({oos_size_gbm} trades): {_oos_acc:.3f}")
                    _oos_errors = np.abs(_oos_proba_win - y[train_size_gbm:].astype(float))
                    # Floor q (see RF note) so a degenerate OOS fold can't fake max certainty.
                    self._conformal_q = max(0.05, float(np.percentile(_oos_errors, 90)))
                    print(f"[gbm] Conformal q={self._conformal_q:.3f} (90th-pctile OOS error, {oos_size_gbm} trades)")
                    # Isotonic needs both classes in the OOS slice (see RF note).
                    if len(X_rows) >= _ISO_MIN_TRADES and len(set(y[train_size_gbm:].tolist())) >= 2:
                        _iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
                        _iso.fit(_oos_proba_win, y[train_size_gbm:])
                        new_iso_gbm = _iso
                        print(f"[gbm] Isotonic calibrator fitted on {oos_size_gbm} OOS trades")
            except Exception as _oos_exc:
                print(f"[gbm] OOS eval failed: {_oos_exc}")

        # Shallow GBM: depth=2, 60 trees — walk-forward validated (-1.2pp vs -5.9pp for deep)
        base_clf = GradientBoostingClassifier(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            learning_rate=self._learning_rate,
            subsample=0.8,
            random_state=42,
        )
        # Platt calibration: TimeSeriesSplit prevents future-data leakage into calibration folds
        n_splits = 3 if len(X_rows) >= 45 else 2
        tscv = TimeSeriesSplit(n_splits=n_splits)
        clf = CalibratedClassifierCV(base_clf, method="sigmoid", cv=tscv)
        try:
            clf.fit(X, y, sample_weight=w)
        except Exception as exc:
            print(f"[gbm] Training failed: {exc}")
            return False

        imps_list2 = [
            est.estimator.feature_importances_
            for est in clf.calibrated_classifiers_
            if hasattr(est.estimator, "feature_importances_")
        ]
        raw_imps = np.mean(imps_list2, axis=0) if imps_list2 else np.ones(len(FEATURE_NAMES)) / len(FEATURE_NAMES)

        with self._lock:
            self._prev_model = self._model
            self._model = clf
            self._trained = True
            self._feature_indices = new_feature_indices  # swap atomically with the model
            self._feature_importances = raw_imps.tolist()
            self._iso_calibrator = new_iso_gbm

        top_idx = new_feature_indices[int(np.argmax(raw_imps))]
        n_feats = len(new_feature_indices)
        iso_tag = "+iso" if new_iso_gbm else ""
        print(f"[gbm] Trained on {len(X_rows)} trades (shallow+Platt{iso_tag}, {n_feats}f). Top feature: {FEATURE_NAMES[top_idx]}")
        return True

    def predict(self, features: list[float]) -> float:
        if not _SKLEARN_AVAILABLE or not self._trained or self._model is None:
            return 0.5
        if len(features) != len(FEATURE_NAMES):
            print(f"[gbm] Feature vector length {len(features)} != expected {len(FEATURE_NAMES)} — returning 0.5")
            return 0.5
        X = np.array([[features[i] for i in self._feature_indices]], dtype=np.float64)
        try:
            with self._lock:
                proba = self._model.predict_proba(X)[0]
                iso = self._iso_calibrator
            classes = list(self._model.classes_)
            win_idx = classes.index(1) if 1 in classes else -1
            p = float(proba[win_idx]) if win_idx >= 0 else 0.5
            if iso is not None:
                p = float(iso.predict([p])[0])
            return p
        except Exception as exc:
            print(f"[gbm] predict error: {exc}")
            return 0.5

    def predict_with_interval(self, features: list[float]) -> tuple[float, float, float, float]:
        """Return (score, lo, hi, width) using conformal prediction interval."""
        score = self.predict(features)
        q = self._conformal_q
        lo, hi = max(0.0, score - q), min(1.0, score + q)
        return score, lo, hi, hi - lo

    def rollback(self) -> bool:
        """Restore previous champion model."""
        if self._prev_model is None:
            return False
        with self._lock:
            self._model, self._prev_model = self._prev_model, self._model
        print("[gbm] Rolled back to previous champion model.")
        return True

    @property
    def is_trained(self) -> bool:
        return self._trained

    def top_features(self, n: int = 5) -> list[tuple[str, float]]:
        paired = list(zip(FEATURE_NAMES, self._feature_importances))
        paired.sort(key=lambda x: x[1], reverse=True)
        return paired[:n]

    def retrain(self, history: list[dict]) -> bool:
        return self.train(history)


# ── Pool-aware singletons — one GBM per pool ─────────────────────────────────

_gbm_pool: dict[str, GradientBoostEnsemble] = {}
_gbm_pool_lock = threading.Lock()


def get_gbm(pool: str = "XAUUSD") -> GradientBoostEnsemble:
    """Get or create a GradientBoostEnsemble for the given pool."""
    if pool not in _gbm_pool:
        with _gbm_pool_lock:
            if pool not in _gbm_pool:  # double-checked locking
                _gbm_pool[pool] = GradientBoostEnsemble()
    return _gbm_pool[pool]


# ── Joint pool training — v3 small-data method ───────────────────────────────
# Pools with n<200 suffer from high variance. Combining related pools multiplies
# effective n (JFE 2024: pooled >> per-asset at small n). A single LightGBM with
# a pool-identifier feature learns pool-specific decision boundaries naturally.

# Gold pool → timeframe ID mapping
GOLD_TF_IDS: dict[str, int] = {
    "XAUUSD_2M": 0, "XAUUSD_5M": 1, "XAUUSD_15M": 2, "XAUUSD_30M": 3, "XAUUSD_1H": 4,
}

# Stock pool → (cluster_id, timeframe_id) mapping
# cluster: 0=MOMENTUM 1=QUALITY 2=INDEX 3=QQQ 4=SPX500
# tf:      0=15M 1=30M 2=1H 3=4H
STOCK_POOL_IDS: dict[str, tuple[int, int]] = {
    "STOCKS_MOMENTUM_15M": (0, 0), "STOCKS_MOMENTUM_30M": (0, 1), "STOCKS_MOMENTUM_1H": (0, 2), "STOCKS_MOMENTUM_4H": (0, 3),
    "STOCKS_QUALITY_15M":  (1, 0), "STOCKS_QUALITY_30M":  (1, 1), "STOCKS_QUALITY_1H":  (1, 2), "STOCKS_QUALITY_4H":  (1, 3),
    "STOCKS_INDEX_15M":    (2, 0), "STOCKS_INDEX_30M":    (2, 1), "STOCKS_INDEX_1H":    (2, 2), "STOCKS_INDEX_4H":    (2, 3),
    "STOCKS_QQQ_15M":      (3, 0), "STOCKS_QQQ_30M":      (3, 1), "STOCKS_QQQ_1H":      (3, 2), "STOCKS_QQQ_4H":      (3, 3),
    "STOCKS_SPX500_15M":   (4, 0), "STOCKS_SPX500_30M":   (4, 1), "STOCKS_SPX500_1H":   (4, 2), "STOCKS_SPX500_4H":   (4, 3),
}

def _preload_libgomp() -> None:
    """lib_lightgbm.so needs libgomp.so.1, absent from Railway's Railpack runtime
    image. scikit-learn vendors its own copy in scikit_learn.libs/ — load it
    RTLD_GLOBAL so the dynamic linker resolves lightgbm's dependency from it."""
    import ctypes, glob, sysconfig
    site = sysconfig.get_paths()["purelib"]
    patterns = [
        f"{site}/scikit_learn.libs/libgomp*.so*",
        f"{site}/../**/scikit_learn.libs/libgomp*.so*",
        "/app/.venv/lib/python*/site-packages/scikit_learn.libs/libgomp*.so*",
    ]
    for pattern in patterns:
        for path in glob.glob(pattern, recursive=True):
            try:
                ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
                print(f"[lgbm] preloaded bundled libgomp: {path}")
                return
            except OSError:
                continue


try:
    import lightgbm as _lgb
    _LGBM_AVAILABLE = True
except Exception:
    try:
        _preload_libgomp()
        import lightgbm as _lgb
        _LGBM_AVAILABLE = True
        print("[lgbm] lightgbm loaded after libgomp preload")
    except Exception as _lgb_err:
        _LGBM_AVAILABLE = False
        print(f"[lgbm] lightgbm import failed: {_lgb_err}")


class JointGoldGBM:
    """
    LightGBM trained on all 4 XAUUSD pools combined (2M+5M+30M+1H).
    Adds timeframe_id as a feature so the tree learns pool-specific boundaries.
    Effective n grows from ~84 (5M alone) to ~497 (all gold pools combined).
    """

    def __init__(self):
        self._model = None
        self._trained = False
        self._n_trained = 0
        self._lock = threading.Lock()

    def train(self, pool_histories: dict[str, list[dict]]) -> bool:
        if not _LGBM_AVAILABLE:
            print("[joint_gold] lightgbm not available — skipping joint training")
            return False

        X_rows, y_rows, w_rows = [], [], []
        for pool, history in pool_histories.items():
            tf_id = GOLD_TF_IDS.get(pool)
            if tf_id is None:
                continue
            for row in history:
                feat = row_to_vector(row) + [float(tf_id)]
                label = _win_label(row)
                X_rows.append(feat)
                y_rows.append(label)
                w_rows.append(_session_weight(row.get("created_at", "")) * _quality_weight(row) * _label_noise_weight(row))

        if len(X_rows) < MIN_TRADES or len(set(y_rows)) < 2:
            print(f"[joint_gold] Not enough data ({len(X_rows)} rows, classes={set(y_rows)}) — skipping")
            return False

        X = np.array(X_rows, dtype=np.float64)
        y = np.array(y_rows, dtype=np.int32)
        w = np.array(w_rows, dtype=np.float64)

        model = _lgb.LGBMClassifier(
            n_estimators=80, max_depth=3, learning_rate=0.08,
            num_leaves=7, class_weight="balanced", subsample=0.8,
            colsample_bytree=0.8, random_state=42, verbose=-1,
        )
        try:
            model.fit(X, y, sample_weight=w)
        except Exception as exc:
            print(f"[joint_gold] Training failed: {exc}")
            return False

        with self._lock:
            self._model = model
            self._trained = True
            self._n_trained = len(X_rows)
        print(f"[joint_gold] Trained on {len(X_rows)} trades across {len([p for p in pool_histories if p in GOLD_TF_IDS])} gold pools")
        return True

    def predict(self, features: list[float], pool: str) -> float:
        if not self._trained or self._model is None:
            return 0.5
        tf_id = GOLD_TF_IDS.get(pool)
        if tf_id is None:
            return 0.5
        X = np.array([features[:len(FEATURE_NAMES)] + [float(tf_id)]], dtype=np.float64)
        try:
            import warnings
            with self._lock:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    proba = self._model.predict_proba(X)[0]
            classes = list(self._model.classes_)
            win_idx = classes.index(1) if 1 in classes else -1
            return float(proba[win_idx]) if win_idx >= 0 else 0.5
        except Exception as exc:
            print(f"[joint_gold] predict error: {exc}")
            return 0.5

    @property
    def is_trained(self) -> bool:
        return self._trained


class JointStocksGBM:
    """
    LightGBM trained on all stock pools combined.
    Adds cluster_id + timeframe_id features (2 extra columns).
    """

    def __init__(self):
        self._model = None
        self._trained = False
        self._n_trained = 0
        self._lock = threading.Lock()

    def train(self, pool_histories: dict[str, list[dict]]) -> bool:
        if not _LGBM_AVAILABLE:
            print("[joint_stocks] lightgbm not available")
            return False

        X_rows, y_rows, w_rows = [], [], []
        for pool, history in pool_histories.items():
            ids = STOCK_POOL_IDS.get(pool)
            if ids is None:
                continue
            cluster_id, tf_id = ids
            for row in history:
                feat = row_to_vector(row) + [float(cluster_id), float(tf_id)]
                label = _win_label(row)
                X_rows.append(feat)
                y_rows.append(label)
                w_rows.append(_session_weight(row.get("created_at", "")) * _quality_weight(row) * _label_noise_weight(row))

        if len(X_rows) < MIN_TRADES or len(set(y_rows)) < 2:
            print(f"[joint_stocks] Not enough data ({len(X_rows)} rows) — skipping")
            return False

        X = np.array(X_rows, dtype=np.float64)
        y = np.array(y_rows, dtype=np.int32)
        w = np.array(w_rows, dtype=np.float64)

        model = _lgb.LGBMClassifier(
            n_estimators=80, max_depth=3, learning_rate=0.08,
            num_leaves=7, class_weight="balanced", subsample=0.8,
            colsample_bytree=0.8, random_state=42, verbose=-1,
        )
        try:
            model.fit(X, y, sample_weight=w)
        except Exception as exc:
            print(f"[joint_stocks] Training failed: {exc}")
            return False

        with self._lock:
            self._model = model
            self._trained = True
            self._n_trained = len(X_rows)
        print(f"[joint_stocks] Trained on {len(X_rows)} trades across {len([p for p in pool_histories if p in STOCK_POOL_IDS])} stock pools")
        return True

    def predict(self, features: list[float], pool: str) -> float:
        if not self._trained or self._model is None:
            return 0.5
        ids = STOCK_POOL_IDS.get(pool)
        if ids is None:
            return 0.5
        cluster_id, tf_id = ids
        X = np.array([features[:len(FEATURE_NAMES)] + [float(cluster_id), float(tf_id)]], dtype=np.float64)
        try:
            import warnings
            with self._lock:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    proba = self._model.predict_proba(X)[0]
            classes = list(self._model.classes_)
            win_idx = classes.index(1) if 1 in classes else -1
            return float(proba[win_idx]) if win_idx >= 0 else 0.5
        except Exception as exc:
            print(f"[joint_stocks] predict error: {exc}")
            return 0.5

    @property
    def is_trained(self) -> bool:
        return self._trained


# ── Joint model singletons ───────────────────────────────────────────────────
_joint_gold = JointGoldGBM()
_joint_stocks = JointStocksGBM()


def get_joint_gold() -> JointGoldGBM:
    return _joint_gold


def get_joint_stocks() -> JointStocksGBM:
    return _joint_stocks


# ── TabPFN v2 — pre-trained in-context learner (Nature 2025) ─────────────────
# Works at n≥10. No training — passes (X_train, y_train) as context each call.
# IID assumption: use as one signal alongside walk-forward models, not standalone.

try:
    from tabpfn import TabPFNClassifier as _TabPFNClassifier
    _TABPFN_AVAILABLE = True
except Exception:
    _TABPFN_AVAILABLE = False


class TabPFNEnsemble:
    """
    TabPFN v2 in-context classifier. fit() stores the training context;
    predict() performs inference. Re-fit only when history length changes.
    Auth failures are remembered per-instance so we don't retry endlessly.
    """

    def __init__(self):
        self._clf = None
        self._trained = False
        self._last_n = 0
        self._auth_failed = False  # set True on HF auth error — stops retries
        self._lock = threading.Lock()

    def fit(self, history: list[dict]) -> bool:
        if not _TABPFN_AVAILABLE or self._auth_failed:
            return False
        if len(history) < 10:
            return False

        X_rows, y_rows = [], []
        for row in history:
            X_rows.append(row_to_vector(row))
            y_rows.append(_win_label(row))

        if len(set(y_rows)) < 2:
            return False

        X = np.array(X_rows, dtype=np.float64)
        y = np.array(y_rows, dtype=np.int32)

        try:
            clf = _TabPFNClassifier(device="cpu", ignore_pretraining_limits=True)
            clf.fit(X, y)
        except Exception as exc:
            err_str = str(exc)
            if "gated" in err_str or "authentication" in err_str or "HuggingFace" in err_str:
                self._auth_failed = True
                print("[tabpfn] Disabled: HuggingFace auth required (set HF_TOKEN env var to enable)")
            else:
                print(f"[tabpfn] fit failed: {exc}")
            return False

        with self._lock:
            self._clf = clf
            self._trained = True
            self._last_n = len(X_rows)
        print(f"[tabpfn] Context set: {len(X_rows)} trades")
        return True

    def fit_if_stale(self, history: list[dict]) -> bool:
        """Re-fit only when history has grown; never retry after auth failure."""
        if self._auth_failed:
            return False
        if len(history) != self._last_n:
            return self.fit(history)
        return self._trained

    def predict(self, features: list[float]) -> float:
        if not self._trained or self._clf is None:
            return 0.5
        X = np.array([features[:len(FEATURE_NAMES)]], dtype=np.float64)
        try:
            with self._lock:
                proba = self._clf.predict_proba(X)[0]
            classes = list(self._clf.classes_)
            win_idx = classes.index(1) if 1 in classes else -1
            return float(proba[win_idx]) if win_idx >= 0 else 0.5
        except Exception as exc:
            print(f"[tabpfn] predict error: {exc}")
            return 0.5

    @property
    def is_trained(self) -> bool:
        return self._trained


# ── TabPFN per-pool singletons ───────────────────────────────────────────────
_tabpfn_pool: dict[str, TabPFNEnsemble] = {}
_tabpfn_pool_lock = threading.Lock()


def get_tabpfn(pool: str) -> TabPFNEnsemble:
    if pool not in _tabpfn_pool:
        with _tabpfn_pool_lock:
            if pool not in _tabpfn_pool:
                _tabpfn_pool[pool] = TabPFNEnsemble()
    return _tabpfn_pool[pool]


# ── Warm-start transfer (XAUUSD_2M → thin gold pools) ───────────────────────
# When a target pool has <80 trades, initialise from the source pool's LightGBM
# Booster and add correction trees. Falls back to standalone training if lift<0.
# Walk-forward A/B is tracked per-fold; caller decides whether to keep transfer.

def train_with_warm_start(
    source_history: list[dict],
    target_history: list[dict],
) -> "object | None":
    """
    Train a LightGBM model on target_history, warm-started from a model pre-trained
    on source_history. Returns the fitted LGBMClassifier or None on failure.

    Caller should A/B test the returned model against a fresh per-pool model.
    Use this when len(target_history) < 80.
    """
    if not _LGBM_AVAILABLE:
        return None
    if len(source_history) < MIN_TRADES or len(target_history) < MIN_TRADES:
        return None

    # Train source
    def _build_arrays(hist):
        xs, ys, ws = [], [], []
        for row in hist:
            xs.append(row_to_vector(row))
            ys.append(_win_label(row))
            ws.append(_session_weight(row.get("created_at", "")))
        return (np.array(xs, np.float32), np.array(ys, np.int32), np.array(ws, np.float32))

    X_src, y_src, w_src = _build_arrays(source_history)
    X_tgt, y_tgt, w_tgt = _build_arrays(target_history)

    if len(set(y_src.tolist())) < 2 or len(set(y_tgt.tolist())) < 2:
        return None

    import tempfile, os as _os

    try:
        # Source model — more trees to build a strong initialisation
        src_clf = _lgb.LGBMClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.08,
            num_leaves=7, class_weight="balanced", subsample=0.8,
            random_state=42, verbose=-1,
        )
        src_clf.fit(X_src, y_src, sample_weight=w_src)
        # Save booster to temp file for init_model handoff
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        src_clf.booster_.save_model(tmp.name)
        tmp.close()

        # Target model — fewer correction trees on top of source init
        tgt_clf = _lgb.LGBMClassifier(
            n_estimators=40, max_depth=2, learning_rate=0.06,
            num_leaves=5, class_weight="balanced", subsample=0.8,
            random_state=42, verbose=-1,
        )
        tgt_clf.fit(X_tgt, y_tgt, sample_weight=w_tgt, init_model=tmp.name)
        _os.unlink(tmp.name)
        print(f"[warm_start] Transfer complete: {len(X_src)} src + {len(X_tgt)} tgt trades")
        return tgt_clf
    except Exception as exc:
        print(f"[warm_start] Transfer failed: {exc}")
        return None


# ── Optuna Bayesian HPO (v4) ─────────────────────────────────────────────────
# Runs only when pool n≥80. Uses TimeSeriesSplit (no shuffle) to avoid lookahead.
# Caches best params per pool — re-tunes every 50 new trades.

try:
    import optuna as _optuna
    _optuna.logging.set_verbosity(_optuna.logging.WARNING)
    _OPTUNA_AVAILABLE = True
except Exception:
    _OPTUNA_AVAILABLE = False

_hpo_cache: dict[str, dict] = {}   # pool → {params, trained_at_n}
_HPO_RETUNE_EVERY = 50             # re-run HPO when pool grows by this many trades


def tune_gbm_hyperparams(pool: str, X: "np.ndarray", y: "np.ndarray",
                         n_trials: int = 60) -> dict:
    """
    Bayesian HPO for LightGBM using Optuna TPE sampler + TimeSeriesSplit CV.
    Returns best params dict. Falls back to defaults if optuna/lgbm unavailable.
    Purged walk-forward CV (gap=5) prevents lookahead leakage.
    """
    defaults = {
        "n_estimators": 80, "max_depth": 3, "learning_rate": 0.08,
        "num_leaves": 7, "subsample": 0.8,
    }
    if not _OPTUNA_AVAILABLE or not _LGBM_AVAILABLE:
        return defaults
    if len(X) < 80:
        return defaults

    # Check cache — skip re-tuning if pool hasn't grown enough
    cached = _hpo_cache.get(pool)
    if cached and abs(len(X) - cached["trained_at_n"]) < _HPO_RETUNE_EVERY:
        return cached["params"]

    from sklearn.model_selection import TimeSeriesSplit

    def _objective(trial):
        params = {
            "n_estimators":  trial.suggest_int("n_estimators", 40, 120),
            "max_depth":     trial.suggest_int("max_depth", 2, 4),
            "learning_rate": trial.suggest_float("learning_rate", 0.03, 0.20, log=True),
            "num_leaves":    trial.suggest_int("num_leaves", 4, 15),
            "subsample":     trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        }
        clf = _lgb.LGBMClassifier(
            **params, class_weight="balanced", random_state=42, verbose=-1
        )
        tscv = TimeSeriesSplit(n_splits=3, gap=5)
        scores = []
        for tr_idx, val_idx in tscv.split(X):
            X_tr, X_val = X[tr_idx], X[val_idx]
            y_tr, y_val = y[tr_idx], y[val_idx]
            if len(set(y_tr.tolist())) < 2:
                continue
            clf.fit(X_tr, y_tr)
            preds = clf.predict(X_val)
            from sklearn.metrics import f1_score
            scores.append(f1_score(y_val, preds, zero_division=0))
        return float(np.mean(scores)) if scores else 0.0

    study = _optuna.create_study(
        direction="maximize",
        sampler=_optuna.samplers.TPESampler(seed=42),
        pruner=_optuna.pruners.MedianPruner(n_startup_trials=10),
    )
    try:
        study.optimize(_objective, n_trials=n_trials, n_jobs=1, show_progress_bar=False)
        best = study.best_params
    except Exception as exc:
        print(f"[hpo] Optuna failed for pool '{pool}': {exc}")
        best = defaults

    _hpo_cache[pool] = {"params": best, "trained_at_n": len(X)}
    print(f"[hpo] Pool '{pool}' best params: {best} (F1={study.best_value:.3f})")
    return best


# ── SHAP TreeSHAP feature attribution (v4) ───────────────────────────────────
# Per-trade explanation: which F1–F26 features drove the signal.
# Uses TreeSHAP (O(TL) exact) — fast enough for real-time with top-8 features.

try:
    import shap as _shap
    _SHAP_AVAILABLE = True
except Exception:
    _SHAP_AVAILABLE = False


def explain_prediction(model, features: list[float], feature_names: list[str],
                       top_n: int = 3) -> list[tuple[str, float]]:
    """
    Return top_n (feature_name, shap_value) pairs that most influenced the prediction.
    Works with any sklearn-compatible tree model (RF, GBM, LightGBM).
    Returns empty list if SHAP unavailable or model not fitted.
    """
    if not _SHAP_AVAILABLE or model is None:
        return []
    try:
        X = np.array([features[:len(feature_names)]], dtype=np.float64)
        # CalibratedClassifierCV wraps the base estimator — unwrap for TreeExplainer
        base_model = model
        if hasattr(model, "calibrated_classifiers_"):
            inner = model.calibrated_classifiers_[0]
            if hasattr(inner, "estimator"):
                base_model = inner.estimator
        explainer = _shap.TreeExplainer(base_model, feature_perturbation="tree_path_dependent")
        shap_vals = explainer.shap_values(X, check_additivity=False)
        # For binary classification shap_values may be a list [class0, class1]
        if isinstance(shap_vals, list) and len(shap_vals) == 2:
            sv = shap_vals[1][0]   # class=WIN shap values
        else:
            sv = shap_vals[0] if shap_vals.ndim == 2 else shap_vals
        pairs = sorted(zip(feature_names, sv.tolist()), key=lambda x: abs(x[1]), reverse=True)
        return [(name, round(float(val), 4)) for name, val in pairs[:top_n]]
    except Exception as exc:
        print(f"[shap] explain_prediction failed: {exc}")
        return []
