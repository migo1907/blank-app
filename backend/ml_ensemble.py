"""
Ensemble models for XAU/USD trade outcome prediction.
  - RandomForestEnsemble   : existing RF model
  - GradientBoostEnsemble  : XGBoost-equivalent via sklearn GradientBoosting (item 2)
Both support session-weighted training (item 5): London/NY trades weighted 1.3×.
Requires scikit-learn >= 1.4.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Optional

MIN_TRADES = 15  # minimum history before models will train

try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.calibration import CalibratedClassifierCV
    import numpy as np
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

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

        # Build X, y
        X_rows = []
        y_rows = []
        for row in history:
            feat_vec = row_to_vector(row)
            # PARTIAL is a profitable close (hit TP1+) — treat as win, not loss
            outcome_val = row.get("ml_outcome") or row.get("outcome", "LOSS")
            label = 1 if outcome_val in ("WIN", "PARTIAL") else 0
            X_rows.append(feat_vec)
            y_rows.append(label)

        X = np.array(X_rows, dtype=np.float32)
        y = np.array(y_rows, dtype=np.int32)

        # Feature selection: top-8 by |correlation| when n>=80 (validated: +3.5–20pp lift)
        if len(X_rows) >= 80:
            corr = np.array([abs(np.corrcoef(X[:, j], y)[0, 1]) if not np.isnan(np.corrcoef(X[:, j], y)[0, 1]) else 0.0
                             for j in range(X.shape[1])])
            self._feature_indices = np.argsort(corr)[::-1][:8].tolist()
        else:
            self._feature_indices = list(range(len(FEATURE_NAMES)))
        X = X[:, self._feature_indices]

        # Shallow RF: depth=4, min_leaf=8 — walk-forward validated (+3.5pp vs -7.7pp for deep)
        base_clf = RandomForestClassifier(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            min_samples_leaf=self._min_samples_leaf,
            class_weight="balanced",
            random_state=self._random_state,
            n_jobs=-1,
        )

        # Session-weighted training: London/NY trades count more
        sample_weights = np.array(
            [_session_weight(row.get("created_at", "")) for row in history],
            dtype=np.float32
        )

        # Platt calibration: sigmoid wrapper, cv=3 (isotonic overfits below ~1000 samples)
        n_splits = 3 if len(X_rows) >= 45 else 2
        clf = CalibratedClassifierCV(base_clf, method="sigmoid", cv=n_splits)

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
            self._feature_importances = raw_imps.tolist()

        top_feat = FEATURE_NAMES[self._feature_indices[int(np.argmax(raw_imps))]]
        n_feats = len(self._feature_indices)
        print(f"[rf] Retrained on {len(X_rows)} trades (shallow+Platt, {n_feats}f). Top feature: {top_feat}")
        return True

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict(self, features: list[float]) -> float:
        """
        Predict WIN probability for a given 25-feature vector.

        Returns:
            float in [0.0, 1.0]. Returns 0.5 if model not yet trained.
        """
        if not _SKLEARN_AVAILABLE or not self._trained or self._model is None:
            return 0.5

        if len(features) != len(FEATURE_NAMES):
            print(f"[ensemble] Feature vector length {len(features)} != expected {len(FEATURE_NAMES)} — returning 0.5")
            return 0.5

        X = np.array([[features[i] for i in self._feature_indices]], dtype=np.float32)
        try:
            with self._lock:
                proba = self._model.predict_proba(X)[0]
            classes = list(self._model.classes_)
            win_idx = classes.index(1) if 1 in classes else -1
            return float(proba[win_idx]) if win_idx >= 0 else 0.5
        except Exception as exc:
            print(f"[rf] predict error: {exc}")
            return 0.5

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

    def train(self, history: list[dict]) -> bool:
        if not _SKLEARN_AVAILABLE:
            return False
        if len(history) < MIN_TRADES:
            print(f"[gbm] Only {len(history)} trades — skipping train.")
            return False

        X_rows, y_rows, w_rows = [], [], []
        for row in history:
            X_rows.append(row_to_vector(row))
            # PARTIAL is a profitable close (hit TP1+) — treat as win, not loss
            outcome_val = row.get("ml_outcome") or row.get("outcome", "LOSS")
            y_rows.append(1 if outcome_val in ("WIN", "PARTIAL") else 0)
            w_rows.append(_session_weight(row.get("created_at", "")))

        if len(set(y_rows)) < 2:
            print(f"[gbm] Only one class in training data ({set(y_rows)}) — skipping train until wins accumulate.")
            return False

        X = np.array(X_rows, dtype=np.float32)
        y = np.array(y_rows, dtype=np.int32)
        w = np.array(w_rows, dtype=np.float32)

        # Feature selection: top-8 by |correlation| when n>=80
        if len(X_rows) >= 80:
            corr = np.array([abs(np.corrcoef(X[:, j], y)[0, 1]) if not np.isnan(np.corrcoef(X[:, j], y)[0, 1]) else 0.0
                             for j in range(X.shape[1])])
            self._feature_indices = np.argsort(corr)[::-1][:8].tolist()
        else:
            self._feature_indices = list(range(len(FEATURE_NAMES)))
        X = X[:, self._feature_indices]

        # Shallow GBM: depth=2, 60 trees — walk-forward validated (-1.2pp vs -5.9pp for deep)
        base_clf = GradientBoostingClassifier(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            learning_rate=self._learning_rate,
            subsample=0.8,
            random_state=42,
        )
        # Platt calibration wrapper
        n_splits = 3 if len(X_rows) >= 45 else 2
        clf = CalibratedClassifierCV(base_clf, method="sigmoid", cv=n_splits)
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
            self._feature_importances = raw_imps.tolist()

        top_idx = self._feature_indices[int(np.argmax(raw_imps))]
        n_feats = len(self._feature_indices)
        print(f"[gbm] Trained on {len(X_rows)} trades (shallow+Platt, {n_feats}f). Top feature: {FEATURE_NAMES[top_idx]}")
        return True

    def predict(self, features: list[float]) -> float:
        if not _SKLEARN_AVAILABLE or not self._trained or self._model is None:
            return 0.5
        if len(features) != len(FEATURE_NAMES):
            print(f"[gbm] Feature vector length {len(features)} != expected {len(FEATURE_NAMES)} — returning 0.5")
            return 0.5
        X = np.array([[features[i] for i in self._feature_indices]], dtype=np.float32)
        try:
            with self._lock:
                proba = self._model.predict_proba(X)[0]
            classes = list(self._model.classes_)
            win_idx = classes.index(1) if 1 in classes else -1
            return float(proba[win_idx]) if win_idx >= 0 else 0.5
        except Exception as exc:
            print(f"[gbm] predict error: {exc}")
            return 0.5

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
