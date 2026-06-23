"""
Phase 2B — Multi-Timeframe Confluence Engine (backend-side).

Replaces reliance on the Pine Script's single F16 (1H MTF) value with a full
1H + 4H + Daily trend stack scored in the backend via yfinance — no Pine Script
changes, no TradingView alert re-creation, no feature cold-start.

Each timeframe votes bull (+1) / bear (-1) / neutral (0) from an EMA-trend read.
Higher timeframes carry more weight (1H=1, 4H=2, Daily=3) because a daily trend
dominates an intraday wiggle. A signal is "in confluence" when at least 2 of the
3 timeframes agree with its direction; signal_engine boosts confluent signals
and dampens signals fired against the stack.

Cached in memory + persisted to the data branch, refreshed hourly alongside the
macro/regime cycle. Graceful no-op (neutral) if a fetch fails.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

# Reuse the same asset mapping as the regime model.
MTF_ASSETS = {
    "XAUUSD": "GC=F",
    "SPY":    "SPY",
    "QQQ":    "QQQ",
}

_MTF_PATH = "data/mtf_confluence.json"
_TF_WEIGHTS = {"h1": 1.0, "h4": 2.0, "d1": 3.0}


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def _trend_vote(close: np.ndarray, fast: int, slow: int) -> int:
    """+1 bull / -1 bear / 0 neutral from EMA(fast) vs EMA(slow) and price slope."""
    if len(close) < slow + 2:
        return 0
    ef = _ema(close, fast)
    es = _ema(close, slow)
    spread = (ef[-1] - es[-1]) / max(abs(es[-1]), 1e-9)
    # Neutral band: ignore tiny EMA separation (<0.05%) as chop
    if spread > 0.0005:
        return 1
    if spread < -0.0005:
        return -1
    return 0


def compute_mtf(asset_key: str) -> dict:
    """Fetch 1H/4H/Daily bars and compute the per-TF trend stack for one asset."""
    ticker = MTF_ASSETS.get(asset_key, asset_key)
    votes = {"h1": 0, "h4": 0, "d1": 0}
    try:
        from market_data import fetch_intraday, fetch_daily

        h1 = fetch_intraday(ticker, interval="1h", period="60d")
        d1 = fetch_daily(ticker, period="1y")   # yfinance → Stooq fallback

        if len(h1):
            c1 = h1["Close"].to_numpy(dtype=float)
            votes["h1"] = _trend_vote(c1, 20, 50)
            # 4H derived by resampling the 1H series (yfinance has no native 4h)
            h4 = h1["Close"].resample("4h").last().dropna()
            c4 = h4.to_numpy(dtype=float)
            votes["h4"] = _trend_vote(c4, 10, 20)
        if len(d1):
            cd = d1["Close"].to_numpy(dtype=float)
            votes["d1"] = _trend_vote(cd, 20, 50)
    except Exception as e:
        print(f"[mtf] {asset_key} fetch/compute failed: {e}")
        return {"asset": asset_key, "votes": votes, "weighted": 0.0,
                "bias": "NEUTRAL", "updated_at": _now(), "method": "none"}

    weighted = sum(votes[tf] * _TF_WEIGHTS[tf] for tf in votes)
    total_w = sum(_TF_WEIGHTS.values())
    norm = weighted / total_w  # ∈ [-1, +1]
    bias = "BULL" if norm > 0.15 else "BEAR" if norm < -0.15 else "NEUTRAL"
    return {
        "asset":     asset_key,
        "votes":     votes,
        "weighted":  round(norm, 3),
        "bias":      bias,
        "updated_at": _now(),
        "method":    "yfinance",
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Cache + persistence ───────────────────────────────────────────────────────

_cached_mtf: dict = {}


def get_mtf(asset_key: str) -> dict:
    return _cached_mtf.get(asset_key, {"votes": {"h1": 0, "h4": 0, "d1": 0},
                                       "weighted": 0.0, "bias": "NEUTRAL"})


def get_mtf_for_pool(pool: str) -> dict:
    if pool.startswith("XAUUSD"):
        return get_mtf("XAUUSD")
    if "QQQ" in pool:
        return get_mtf("QQQ")
    return get_mtf("SPY")


def agreement(pool: str, direction: str) -> dict:
    """
    How many of the 3 timeframes agree with `direction`, and the weighted lean.
    Returns {aligned: int 0-3, against: int, weighted_for: float, confluent: bool}.
    """
    state = get_mtf_for_pool(pool)
    votes = state.get("votes", {})
    want = 1 if direction == "LONG" else -1
    aligned = sum(1 for tf in ("h1", "h4", "d1") if votes.get(tf, 0) == want)
    against = sum(1 for tf in ("h1", "h4", "d1") if votes.get(tf, 0) == -want)
    weighted = float(state.get("weighted", 0.0)) * (1 if direction == "LONG" else -1)
    return {
        "aligned":      aligned,
        "against":      against,
        "weighted_for": round(weighted, 3),
        "confluent":    aligned >= 2,
        "bias":         state.get("bias", "NEUTRAL"),
    }


def refresh_mtf() -> dict:
    """Recompute the MTF stack for every asset, cache + persist. Hourly."""
    global _cached_mtf
    fresh = {a: compute_mtf(a) for a in MTF_ASSETS}
    _cached_mtf = fresh
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_MTF_PATH)
        _put_file(_MTF_PATH, fresh, sha, "data: update MTF confluence stack")
    except Exception as e:
        print(f"[mtf] persist failed: {e}")
    summary = " | ".join(f"{a}:{r['bias']}({r['weighted']:+.2f})" for a, r in fresh.items())
    print(f"[mtf] refreshed — {summary}")
    return fresh


def load_mtf() -> None:
    """Load persisted MTF stack from the data branch on startup."""
    global _cached_mtf
    try:
        from db import _get_file
        data, _ = _get_file(_MTF_PATH)
        if isinstance(data, dict) and data:
            _cached_mtf = data
            print(f"[mtf] loaded {len(data)} cached MTF stacks from data branch")
    except Exception as e:
        print(f"[mtf] load failed: {e}")
