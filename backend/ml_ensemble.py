"""
Random Forest ensemble for XAU/USD trade outcome prediction.
Trains on stored trade history; used as a second opinion alongside AdaptiveKNN.
Requires scikit-learn >= 1.4.
"""
from __future__ import annotations

import threading
from typing import Optional

MIN_TRADES = 30  # minimum history before RF will train

# Lazy import so the module can be imported even without scikit-learn installed
# (falls back to 0.5 probability gracefully)
try:
    from sklearn.ensemble import RandomForestClassifier
    import numpy as np
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

from ml_model import FEATURE_NAMES


class RandomForestEnsemble:
    """
    Wraps sklearn RandomForestClassifier for XAU/USD WIN/LOSS prediction.

    Usage:
        rf = RandomForestEnsemble()
        rf.retrain(history)          # list[dict] from recent_outcomes()
        prob = rf.predict(feat_list) # list[float], 20 values
    """

    def __init__(self, n_estimators: int = 200, max_depth: int = 8, random_state: int = 42):
        self._n_estimators = n_estimators
        self._max_depth = max_depth
        self._random_state = random_state
        self._model: Optional[object] = None  # RandomForestClassifier once trained
        self._trained = False
        self._lock = threading.Lock()
        self._feature_importances: list[float] = [1.0 / len(FEATURE_NAMES)] * len(FEATURE_NAMES)

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
            feat_vec = [float(row.get(col, 0.0)) for col in FEATURE_NAMES]
            # Label: WIN=1, anything else=0
            label = 1 if row.get("outcome") == "WIN" else 0
            X_rows.append(feat_vec)
            y_rows.append(label)

        X = np.array(X_rows, dtype=np.float32)
        y = np.array(y_rows, dtype=np.int32)

        # Balance classes via class_weight if needed
        clf = RandomForestClassifier(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            class_weight="balanced",
            random_state=self._random_state,
            n_jobs=-1,
        )

        try:
            clf.fit(X, y)
        except Exception as exc:
            print(f"[rf] Training failed: {exc}")
            return False

        with self._lock:
            self._model = clf
            self._trained = True
            self._feature_importances = clf.feature_importances_.tolist()

        print(f"[rf] Retrained on {len(X_rows)} trades. "
              f"Top feature: {FEATURE_NAMES[int(np.argmax(clf.feature_importances_))]}")
        return True

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict(self, features: list[float]) -> float:
        """
        Predict WIN probability for a given 20-feature vector.

        Returns:
            float in [0.0, 1.0]. Returns 0.5 if model not yet trained.
        """
        if not _SKLEARN_AVAILABLE or not self._trained or self._model is None:
            return 0.5

        if not _SKLEARN_AVAILABLE:
            return 0.5

        import numpy as np  # already imported at module level but kept for clarity

        X = np.array([features], dtype=np.float32)
        try:
            with self._lock:
                proba = self._model.predict_proba(X)[0]
            # proba shape: [p_loss, p_win] if classes are [0, 1]
            classes = list(self._model.classes_)
            win_idx = classes.index(1) if 1 in classes else -1
            return float(proba[win_idx]) if win_idx >= 0 else 0.5
        except Exception as exc:
            print(f"[rf] predict error: {exc}")
            return 0.5

    # ── Feature importance ────────────────────────────────────────────────────

    @property
    def feature_importances(self) -> list[float]:
        """RF feature importances (20 values, sum to 1.0). Uniform if not trained."""
        return list(self._feature_importances)

    @property
    def is_trained(self) -> bool:
        return self._trained

    def top_features(self, n: int = 5) -> list[tuple[str, float]]:
        """Return top-n features by RF importance as [(name, importance), ...]."""
        paired = list(zip(FEATURE_NAMES, self._feature_importances))
        paired.sort(key=lambda x: x[1], reverse=True)
        return paired[:n]


# ── Module-level singleton ───────────────────────────────────────────────────

_rf: RandomForestEnsemble | None = None


def get_rf() -> RandomForestEnsemble:
    global _rf
    if _rf is None:
        _rf = RandomForestEnsemble()
    return _rf
