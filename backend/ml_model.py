"""
Lorentzian KNN classifier with GitHub-persistent adaptive weights.
Expanded to 20 features (v3).
Weights survive across sessions — true cross-session learning.
"""
import math
from dataclasses import dataclass
from db import load_weights, save_weights, recent_outcomes

SYMBOL = "XAUUSD"
CLAMP_MIN = 0.2
CLAMP_MAX = 3.0

FEATURE_NAMES = [
    "f1_rsi",      # RSI normalized
    "f2_adx",      # ADX × DI direction
    "f3_atr",      # ATR ratio
    "f4_bb",       # BB%
    "f5_macd",     # MACD histogram
    "f6_willr",    # Williams %R
    "f7_cmo",      # CMO
    "f8_ema_dist", # EMA-200 distance
    "f9_fvg",      # Fair Value Gap
    "f10_ob",      # Order Block
    "f11_bos",     # Break of Structure
    "f12_liq",     # Liquidity Sweep
    "f13_pd",      # Premium/Discount
    "f14_choch",   # Change of Character
    "f15_sess",    # Session Kill Zone
    "f16_mtf",     # MTF Alignment
    "f17_dxy",     # DXY Inverse
    "f18_vold",    # Volume Delta
    "f19_rsidiv",  # RSI Divergence
    "f20_fib",     # Fibonacci Position
]

N_FEATURES = 20


@dataclass
class Features:
    f1:  float = 0.0   # RSI norm
    f2:  float = 0.0   # ADX×DI
    f3:  float = 0.0   # ATR ratio
    f4:  float = 0.0   # BB%
    f5:  float = 0.0   # MACD hist
    f6:  float = 0.0   # Williams %R
    f7:  float = 0.0   # CMO
    f8:  float = 0.0   # EMA-200 dist
    f9:  float = 0.0   # FVG
    f10: float = 0.0   # Order Block
    f11: float = 0.0   # BOS
    f12: float = 0.0   # Liquidity Sweep
    f13: float = 0.0   # Premium/Discount
    f14: float = 0.0   # CHoCH
    f15: float = 0.0   # Session Kill Zone
    f16: float = 0.0   # MTF Alignment
    f17: float = 0.0   # DXY Inverse
    f18: float = 0.0   # Volume Delta
    f19: float = 0.0   # RSI Divergence
    f20: float = 0.0   # Fibonacci Position

    def as_list(self) -> list[float]:
        return [
            self.f1,  self.f2,  self.f3,  self.f4,  self.f5,
            self.f6,  self.f7,  self.f8,  self.f9,  self.f10,
            self.f11, self.f12, self.f13, self.f14, self.f15,
            self.f16, self.f17, self.f18, self.f19, self.f20,
        ]

    @classmethod
    def from_payload(cls, payload: dict) -> "Features":
        """Build Features from a webhook payload dict (f1..f20 keys)."""
        return cls(
            f1=float(payload.get("f1", 0.0)),
            f2=float(payload.get("f2", 0.0)),
            f3=float(payload.get("f3", 0.0)),
            f4=float(payload.get("f4", 0.0)),
            f5=float(payload.get("f5", 0.0)),
            f6=float(payload.get("f6", 0.0)),
            f7=float(payload.get("f7", 0.0)),
            f8=float(payload.get("f8", 0.0)),
            f9=float(payload.get("f9", 0.0)),
            f10=float(payload.get("f10", 0.0)),
            f11=float(payload.get("f11", 0.0)),
            f12=float(payload.get("f12", 0.0)),
            f13=float(payload.get("f13", 0.0)),
            f14=float(payload.get("f14", 0.0)),
            f15=float(payload.get("f15", 0.0)),
            f16=float(payload.get("f16", 0.0)),
            f17=float(payload.get("f17", 0.0)),
            f18=float(payload.get("f18", 0.0)),
            f19=float(payload.get("f19", 0.0)),
            f20=float(payload.get("f20", 0.0)),
        )

    def as_db_dict(self) -> dict:
        """Return a dict keyed by DB column names (FEATURE_NAMES)."""
        return dict(zip(FEATURE_NAMES, self.as_list()))


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
        self._weights: list[float] = [1.0] * N_FEATURES
        self._total_wins = 0
        self._total_losses = 0
        self._dirty = False

    # ── Persistence ──────────────────────────────────────────

    def load(self, symbol: str = SYMBOL) -> None:
        row = load_weights(symbol)
        # Support both old (8-weight) and new (20-weight) stored formats
        loaded = []
        for i in range(1, N_FEATURES + 1):
            loaded.append(float(row.get(f"w{i}", 1.0)))
        self._weights = loaded
        self._total_wins = row.get("total_wins", 0)
        self._total_losses = row.get("total_losses", 0)
        self._dirty = False
        print(f"[ml] Loaded weights (20F) from storage: {[round(w, 3) for w in self._weights]}")

    def save(self, symbol: str = SYMBOL) -> None:
        if not self._dirty:
            return
        payload = {f"w{i+1}": self._weights[i] for i in range(N_FEATURES)}
        payload["total_wins"] = self._total_wins
        payload["total_losses"] = self._total_losses
        save_weights(symbol, payload)
        self._dirty = False
        print(f"[ml] Weights saved. Wins={self._total_wins} Losses={self._total_losses}")

    # ── KNN inference ────────────────────────────────────────

    def predict(self, current: Features, history: list[dict]) -> tuple[float, float]:
        """
        Returns (bull_score, bear_score) in [0, 1].
        history: list of trade_outcome rows with f1_rsi..f20_fib and outcome fields.
        """
        if len(history) < self.k:
            return 0.5, 0.5

        current_vec = current.as_list()
        distances: list[tuple[float, int]] = []  # (dist, label: +1 bull / -1 bear)

        for row in history:
            hist_vec = [float(row.get(col, 0.0)) for col in FEATURE_NAMES]
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

    def top_features(self, n: int = 3) -> list[tuple[str, float]]:
        """Return top-n features by weight as [(name, weight), ...]."""
        short_names = [
            "RSI", "ADX", "ATR", "BB%", "MACD", "WillR", "CMO", "EMA-dist",
            "FVG", "OB", "BOS", "Liq", "P/D", "CHoCH",
            "Session", "MTF", "DXY", "VolDelta", "RSIDiv", "Fib",
        ]
        paired = list(zip(short_names, self._weights))
        paired.sort(key=lambda x: x[1], reverse=True)
        return paired[:n]

    def top_feature(self) -> str:
        return self.top_features(1)[0][0]


# Singleton instance used by the FastAPI app
_model: AdaptiveKNN | None = None


def get_model() -> AdaptiveKNN:
    global _model
    if _model is None:
        _model = AdaptiveKNN()
        _model.load()
    return _model
