"""
Phase 2A — Probabilistic market-regime model (Gaussian HMM).

Upgrades the instantaneous ADX/ATR regime tag in signal_engine with a
*probabilistic* view that detects regime TRANSITIONS before they complete:
"XAUUSD is 73% TRENDING_BEAR, but transition probability is rising" — act on
the shift, not after it is confirmed.

Design choices (deployment-safe on Railway's Railpack runtime):
  • Pure numpy Gaussian HMM (Baum-Welch fit + forward filtering). No hmmlearn /
    no new native deps — numpy ships with the existing sklearn stack.
  • OHLC pulled via yfinance (already a dependency) on a slow hourly cycle and
    cached in memory + persisted to the data branch, exactly like market_macro.
  • Graceful degradation: any failure falls back to a deterministic heuristic
    regime so signal_engine never loses its regime input.

States are fit unsupervised (3 hidden states) then *named* by their emission
characteristics: the highest-volatility state → VOLATILE; of the rest, the one
with the larger directional drift → TRENDING_BULL/BEAR (sign of mean return);
the calm low-drift state → RANGING.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

# Assets we model. Pool → asset mapping lives in get_regime_for_pool().
REGIME_ASSETS = {
    "XAUUSD": "GC=F",   # COMEX gold futures — clean continuous OHLC on yfinance
    "SPY":    "SPY",
    "QQQ":    "QQQ",
}

_REGIME_PATH = "data/regime_state.json"
_HIST_BARS   = 400      # bars used to fit the HMM
_INTERVAL    = "1h"     # bar size — responsive without being noisy
_PERIOD      = "60d"    # lookback window for the fetch
_N_STATES    = 3
_SEED        = 7

_NAMES = ("TRENDING_BULL", "TRENDING_BEAR", "RANGING", "VOLATILE", "UNKNOWN")


# ── Feature extraction ────────────────────────────────────────────────────────

def _features_from_ohlc(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> np.ndarray:
    """Per-bar feature matrix: [log_return, realized_vol, norm_range, trend_slope]."""
    close = np.asarray(close, dtype=float)
    high  = np.asarray(high,  dtype=float)
    low   = np.asarray(low,   dtype=float)

    ret = np.diff(np.log(np.clip(close, 1e-9, None)), prepend=np.log(max(close[0], 1e-9)))
    # rolling realized vol (std of returns over 10 bars)
    vol = _rolling_std(ret, 10)
    norm_range = (high - low) / np.clip(close, 1e-9, None)
    ema_fast = _ema(close, 10)
    ema_slow = _ema(close, 30)
    trend_slope = (ema_fast - ema_slow) / np.clip(close, 1e-9, None)

    X = np.column_stack([ret, vol, norm_range, trend_slope])
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


def _rolling_std(x: np.ndarray, w: int) -> np.ndarray:
    out = np.zeros_like(x, dtype=float)
    for i in range(len(x)):
        lo = max(0, i - w + 1)
        seg = x[lo:i + 1]
        out[i] = seg.std() if len(seg) > 1 else 0.0
    return out


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


# ── Gaussian HMM (numpy) ──────────────────────────────────────────────────────

class GaussianHMM:
    """Compact diagonal-covariance Gaussian HMM trained with Baum-Welch."""

    def __init__(self, n_states: int = _N_STATES, n_iter: int = 25, seed: int = _SEED):
        self.K = n_states
        self.n_iter = n_iter
        self.rng = np.random.default_rng(seed)
        self.start = None
        self.trans = None
        self.means = None
        self.vars = None

    def _gauss_logprob(self, X: np.ndarray) -> np.ndarray:
        # log N(x | mean_k, diag(var_k)) for each state → (T, K)
        T, D = X.shape
        logp = np.empty((T, self.K))
        for k in range(self.K):
            var = np.clip(self.vars[k], 1e-9, None)
            diff = X - self.means[k]
            logp[:, k] = -0.5 * (np.sum(diff * diff / var, axis=1)
                                 + np.sum(np.log(2 * np.pi * var)))
        return logp

    def fit(self, X: np.ndarray) -> "GaussianHMM":
        T, D = X.shape
        # init: k-means-ish seeding by quantiles of realized vol (column 1)
        order = np.argsort(X[:, 1])
        chunks = np.array_split(order, self.K)
        self.means = np.array([X[c].mean(axis=0) for c in chunks])
        self.vars = np.array([X[c].var(axis=0) + 1e-6 for c in chunks])
        self.start = np.full(self.K, 1.0 / self.K)
        self.trans = np.full((self.K, self.K), 1.0 / self.K)

        prev_ll = -np.inf
        for _ in range(self.n_iter):
            logB = self._gauss_logprob(X)                      # (T,K)
            log_alpha, ll = self._forward(logB)
            log_beta = self._backward(logB)

            log_gamma = log_alpha + log_beta
            log_gamma -= _logsumexp(log_gamma, axis=1, keepdims=True)
            gamma = np.exp(log_gamma)                          # (T,K)

            # xi sum over t for transition re-estimation
            log_xi_sum = np.full((self.K, self.K), -np.inf)
            for t in range(T - 1):
                m = (log_alpha[t][:, None] + np.log(self.trans + 1e-300)
                     + logB[t + 1][None, :] + log_beta[t + 1][None, :])
                m -= _logsumexp(m.reshape(-1))
                log_xi_sum = np.logaddexp(log_xi_sum, m)

            # M-step
            self.start = gamma[0] / gamma[0].sum()
            trans = np.exp(log_xi_sum)
            self.trans = trans / np.clip(trans.sum(axis=1, keepdims=True), 1e-300, None)
            for k in range(self.K):
                w = gamma[:, k]
                wsum = w.sum() + 1e-9
                self.means[k] = (w[:, None] * X).sum(axis=0) / wsum
                diff = X - self.means[k]
                self.vars[k] = (w[:, None] * diff * diff).sum(axis=0) / wsum + 1e-6

            if abs(ll - prev_ll) < 1e-4:
                break
            prev_ll = ll
        return self

    def _forward(self, logB: np.ndarray):
        T = logB.shape[0]
        log_alpha = np.empty((T, self.K))
        log_alpha[0] = np.log(self.start + 1e-300) + logB[0]
        log_trans = np.log(self.trans + 1e-300)
        for t in range(1, T):
            for k in range(self.K):
                log_alpha[t, k] = _logsumexp(log_alpha[t - 1] + log_trans[:, k]) + logB[t, k]
        ll = _logsumexp(log_alpha[-1])
        return log_alpha, ll

    def _backward(self, logB: np.ndarray):
        T = logB.shape[0]
        log_beta = np.zeros((T, self.K))
        log_trans = np.log(self.trans + 1e-300)
        for t in range(T - 2, -1, -1):
            for k in range(self.K):
                log_beta[t, k] = _logsumexp(log_trans[k] + logB[t + 1] + log_beta[t + 1])
        return log_beta

    def filter_last(self, X: np.ndarray) -> np.ndarray:
        """Posterior state distribution at the final bar."""
        logB = self._gauss_logprob(X)
        log_alpha, _ = self._forward(logB)
        post = np.exp(log_alpha[-1] - _logsumexp(log_alpha[-1]))
        return post


def _logsumexp(a: np.ndarray, axis=None, keepdims=False):
    a = np.asarray(a, dtype=float)
    m = np.max(a, axis=axis, keepdims=True)
    m = np.where(np.isfinite(m), m, 0.0)
    out = m + np.log(np.sum(np.exp(a - m), axis=axis, keepdims=True))
    if axis is None:
        val = out.reshape(()).item()
        return val
    if not keepdims:
        out = np.squeeze(out, axis=axis)
    return out


# ── State naming ──────────────────────────────────────────────────────────────

def _name_states(hmm: GaussianHMM) -> list[str]:
    """Map fitted hidden states → human regime names by emission characteristics.
    Feature columns: [log_return, realized_vol, norm_range, trend_slope]."""
    means = hmm.means
    vol = means[:, 1] + means[:, 2]          # realized vol + range = turbulence
    drift = means[:, 3]                        # trend slope sign/magnitude
    names = [""] * hmm.K

    # Highest-turbulence state → VOLATILE
    vol_idx = int(np.argmax(vol))
    names[vol_idx] = "VOLATILE"

    remaining = [k for k in range(hmm.K) if k != vol_idx]
    # Of the rest, the larger |drift| is the trending state
    remaining.sort(key=lambda k: abs(drift[k]), reverse=True)
    if remaining:
        trend_k = remaining[0]
        names[trend_k] = "TRENDING_BULL" if drift[trend_k] >= 0 else "TRENDING_BEAR"
    for k in remaining[1:]:
        names[k] = "RANGING"
    # Fill any blanks defensively
    return [n or "RANGING" for n in names]


# ── Public: compute regime for one asset ──────────────────────────────────────

def _heuristic_regime(close: np.ndarray, high: np.ndarray, low: np.ndarray) -> dict:
    """Deterministic fallback when the HMM can't fit (too little data / error)."""
    X = _features_from_ohlc(close, high, low)
    recent = X[-20:]
    vol = float(recent[:, 1].mean() + recent[:, 2].mean())
    drift = float(recent[:, 3].mean())
    vol_hist = float(X[:, 1].mean() + X[:, 2].mean()) or 1e-9
    if vol > 1.8 * vol_hist:
        regime = "VOLATILE"
    elif abs(drift) > 1.5e-3:
        regime = "TRENDING_BULL" if drift > 0 else "TRENDING_BEAR"
    else:
        regime = "RANGING"
    return {
        "regime": regime, "confidence": 0.50, "transition_prob": 0.0,
        "probs": {regime: 1.0}, "method": "heuristic",
    }


def compute_regime(asset_key: str) -> dict:
    """Fetch OHLC, fit the HMM, return the current probabilistic regime."""
    ticker = REGIME_ASSETS.get(asset_key, asset_key)
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period=_PERIOD, interval=_INTERVAL)
        close = df["Close"].to_numpy(dtype=float)
        high  = df["High"].to_numpy(dtype=float)
        low   = df["Low"].to_numpy(dtype=float)
    except Exception as e:
        print(f"[regime] {asset_key} OHLC fetch failed: {e}")
        return {"regime": "UNKNOWN", "confidence": 0.0, "transition_prob": 0.0,
                "probs": {}, "method": "none", "updated_at": _now()}

    if len(close) < 60:
        out = _heuristic_regime(close, high, low) if len(close) >= 25 else {
            "regime": "UNKNOWN", "confidence": 0.0, "transition_prob": 0.0,
            "probs": {}, "method": "insufficient_data"}
        out["asset"] = asset_key
        out["updated_at"] = _now()
        return out

    close, high, low = close[-_HIST_BARS:], high[-_HIST_BARS:], low[-_HIST_BARS:]
    X = _features_from_ohlc(close, high, low)

    try:
        hmm = GaussianHMM().fit(X)
        names = _name_states(hmm)
        post = hmm.filter_last(X)
        cur = int(np.argmax(post))

        # Forward-looking transition signal: one-step-ahead predicted distribution.
        # transition_prob = model's probability that the NEXT bar leaves the
        # current state — this is what flags a regime shift before it completes.
        pred_next = post @ hmm.trans
        transition_prob = float(1.0 - pred_next[cur])

        # Aggregate posterior by regime name (states can share a name)
        probs: dict[str, float] = {}
        next_probs: dict[str, float] = {}
        for k, nm in enumerate(names):
            probs[nm] = probs.get(nm, 0.0) + float(post[k])
            next_probs[nm] = next_probs.get(nm, 0.0) + float(pred_next[k])
        regime = max(probs, key=probs.get)
        next_regime = max(next_probs, key=next_probs.get)
        out = {
            "asset":           asset_key,
            "regime":          regime,
            "confidence":      round(probs[regime], 3),
            "transition_prob": round(transition_prob, 3),
            "next_regime":     next_regime,
            "shifting":        bool(next_regime != regime or transition_prob >= 0.25),
            "probs":           {k: round(v, 3) for k, v in probs.items()},
            "method":          "hmm",
            "updated_at":      _now(),
        }
        return out
    except Exception as e:
        print(f"[regime] {asset_key} HMM fit failed ({e}) — using heuristic")
        out = _heuristic_regime(close, high, low)
        out["asset"] = asset_key
        out["updated_at"] = _now()
        return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── In-memory cache + persistence (mirrors market_macro) ──────────────────────

_cached_regimes: dict = {}   # asset_key → regime dict


def get_regime(asset_key: str) -> dict:
    """Cached regime for an asset. Empty/UNKNOWN until first refresh."""
    return _cached_regimes.get(asset_key, {
        "regime": "UNKNOWN", "confidence": 0.0, "transition_prob": 0.0, "probs": {}})


def get_regime_for_pool(pool: str) -> dict:
    """Map an ML pool to its underlying asset's regime."""
    if pool.startswith("XAUUSD"):
        return get_regime("XAUUSD")
    if "QQQ" in pool:
        return get_regime("QQQ")
    # SPX500 / INDEX / MOMENTUM / QUALITY all track broad equities via SPY
    return get_regime("SPY")


def refresh_regimes() -> dict:
    """Recompute every asset regime, cache + persist. Called hourly by scheduler."""
    global _cached_regimes
    fresh = {}
    for asset_key in REGIME_ASSETS:
        fresh[asset_key] = compute_regime(asset_key)
    _cached_regimes = fresh
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_REGIME_PATH)
        _put_file(_REGIME_PATH, fresh, sha, "data: update HMM regime state")
    except Exception as e:
        print(f"[regime] persist failed: {e}")
    summary = " | ".join(
        f"{a}:{r['regime']}({r['confidence']:.2f},Δ{r['transition_prob']:.2f})"
        for a, r in fresh.items())
    print(f"[regime] refreshed — {summary}")
    return fresh


def load_regimes() -> None:
    """Load persisted regime state from the data branch on startup."""
    global _cached_regimes
    try:
        from db import _get_file
        data, _ = _get_file(_REGIME_PATH)
        if isinstance(data, dict) and data:
            _cached_regimes = data
            print(f"[regime] loaded {len(data)} cached regimes from data branch")
    except Exception as e:
        print(f"[regime] load failed: {e}")
