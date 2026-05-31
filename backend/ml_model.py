"""
Lorentzian KNN classifier with Supabase-persistent adaptive weights.
Weights survive across sessions — true cross-session learning.
"""
import math
from dataclasses import dataclass, asdict
from db import load_weights, save_weights, recent_outcomes, insert_outcome

SYMBOL = "XAUUSD"
CLAMP_MIN = 0.2
CLAMP_MAX = 3.0


@dataclass
class Features:
    f1: float  # RSI norm
    f2: float  # ADX×DI
    f3: float  # ATR ratio
    f4: float  # BB%
    f5: float  # MACD hist
    f6: float  # Williams %R
    f7: float  # CMO
    f8: float  # EMA-200 dist

    def as_list(self) -> list[float]:
        return [self.f1, self.f2, self.f3, self.f4, self.f5, self.f6, self.f7, self.f8]


def _clamp(v: float) -> float:
    return max(CLAMP_MIN, min(CLAMP_MAX, v))


def _lorentzian_dist(a: list[float], b: list[float], weights: list[float]) -> float:
    d = 0.0
    for ai, bi, wi in zip(a, b, weights):
        d += wi * math.log(1.0 + abs(ai - bi))
    return d


class AdaptiveKNN:
    def __init__(self, k: int = 8, learn_rate: float = 0.05,
                 win_reward: float = 0.15, loss_penalty: float = 0.20):
        self.k = k
        self.learn_rate = learn_rate
        self.win_reward = win_reward
        self.loss_penalty = loss_penalty
        self._weights: list[float] = [1.0] * 8
        self._total_wins = 0
        self._total_losses = 0
        self._dirty = False

    # ── Persistence ──────────────────────────────────────────

    def load(self, symbol: str = SYMBOL) -> None:
        row = load_weights(symbol)
        self._weights = [row[f"w{i}"] for i in range(1, 9)]
        self._total_wins = row["total_wins"]
        self._total_losses = row["total_losses"]
        self._dirty = False
        print(f"[ml] Loaded weights from Supabase: {[round(w, 3) for w in self._weights]}")

    def save(self, symbol: str = SYMBOL) -> None:
        if not self._dirty:
            return
        payload = {f"w{i+1}": self._weights[i] for i in range(8)}
        payload["total_wins"] = self._total_wins
        payload["total_losses"] = self._total_losses
        save_weights(symbol, payload)
        self._dirty = False
        print(f"[ml] Weights saved to Supabase. Wins={self._total_wins} Losses={self._total_losses}")

    # ── KNN inference ────────────────────────────────────────

    def predict(self, current: Features, history: list[dict]) -> tuple[float, float]:
        """
        Returns (bull_score, bear_score) in [0, 1].
        history: list of trade_outcome rows with f1..f8 and outcome fields.
        """
        if len(history) < self.k:
            return 0.5, 0.5

        current_vec = current.as_list()
        distances: list[tuple[float, int]] = []  # (dist, label: +1 bull / -1 bear)

        for row in history:
            hist_vec = [row.get(f"f{i}_rsi" if i == 1 else
                                f"f{i}_adx" if i == 2 else
                                f"f{i}_atr" if i == 3 else
                                f"f{i}_bb" if i == 4 else
                                f"f{i}_macd" if i == 5 else
                                f"f{i}_willr" if i == 6 else
                                f"f{i}_cmo" if i == 7 else
                                f"f{i}_ema_dist", 0.0)
                        for i in range(1, 9)]
            # Rename to match DB column names
            hist_vec = [
                row.get("f1_rsi", 0.0),
                row.get("f2_adx", 0.0),
                row.get("f3_atr", 0.0),
                row.get("f4_bb", 0.0),
                row.get("f5_macd", 0.0),
                row.get("f6_willr", 0.0),
                row.get("f7_cmo", 0.0),
                row.get("f8_ema_dist", 0.0),
            ]
            dist = _lorentzian_dist(current_vec, hist_vec, self._weights)
            label = 1 if row.get("outcome") == "WIN" and row.get("direction") == "LONG" else -1
            distances.append((dist, label))

        distances.sort(key=lambda x: x[0])
        top_k = distances[:self.k]

        bulls = sum(1 for _, lbl in top_k if lbl == 1)
        bears = self.k - bulls
        total = self.k
        return bulls / total, bears / total

    # ── Adaptive weight update ────────────────────────────────

    def update_on_outcome(self, features: Features, direction: str, outcome: str) -> None:
        """Call after each trade closes. outcome: 'WIN' | 'LOSS' | 'PARTIAL'"""
        feat_list = features.as_list()
        is_long = direction == "LONG"

        if outcome == "WIN":
            self._total_wins += 1
            delta = self.learn_rate * self.win_reward
            for i, fv in enumerate(feat_list):
                sign = 1.0 if (fv >= 0 and is_long) or (fv < 0 and not is_long) else -1.0
                self._weights[i] = _clamp(self._weights[i] + sign * delta)

        elif outcome == "LOSS":
            self._total_losses += 1
            delta = self.learn_rate * self.loss_penalty
            for i, fv in enumerate(feat_list):
                sign = 1.0 if (fv >= 0 and is_long) or (fv < 0 and not is_long) else -1.0
                self._weights[i] = _clamp(self._weights[i] - sign * delta)

        elif outcome == "PARTIAL":
            self._total_wins += 1
            delta = self.learn_rate * self.win_reward * 0.4
            for i, fv in enumerate(feat_list):
                sign = 1.0 if (fv >= 0 and is_long) or (fv < 0 and not is_long) else -1.0
                self._weights[i] = _clamp(self._weights[i] + sign * delta)

        self._dirty = True

    @property
    def weights(self) -> list[float]:
        return list(self._weights)

    @property
    def win_rate(self) -> float:
        total = self._total_wins + self._total_losses
        return self._total_wins / total if total > 0 else 0.0

    def top_feature(self) -> str:
        names = ["RSI", "ADX", "ATR", "BB%", "MACD", "WillR", "CMO", "EMA-dist"]
        idx = self._weights.index(max(self._weights))
        return names[idx]


# Singleton instance used by the FastAPI app
_model: AdaptiveKNN | None = None


def get_model() -> AdaptiveKNN:
    global _model
    if _model is None:
        _model = AdaptiveKNN()
        _model.load()
    return _model
