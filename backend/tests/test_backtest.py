"""
Local tests for polygon_intraday_backtest — NO network.

Builds a synthetic OHLCV series (noisy uptrend then downtrend), stubs fetch_bars,
and validates:
  (a) all features F1..F26 present and within [-1, 1]
  (b) run() with stubbed fetch produces a results dict with >=1 trade and metric keys
  (c) exit_optimizer integration runs without error
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GITHUB_TOKEN", "test")
os.environ.setdefault("GITHUB_REPO", "test/test")
os.environ.setdefault("GITHUB_BRANCH", "data")
os.environ.setdefault("TELEGRAM_TOKEN", "test")
os.environ.setdefault("TELEGRAM_CHAT_ID", "12345")

import numpy as np
import pandas as pd

import polygon_intraday_backtest as pbt


def _synthetic_bars(n=400, tf_minutes=15, seed=42):
    """Noisy uptrend (first half) then downtrend (second half), 15-min bars."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2025-01-02 09:00", tz="UTC")
    base = 100.0
    bars = []
    price = base
    for i in range(n):
        drift = 0.15 if i < n // 2 else -0.15
        price += drift + rng.normal(0, 0.4)
        o = price + rng.normal(0, 0.1)
        c = price + rng.normal(0, 0.1)
        h = max(o, c) + abs(rng.normal(0, 0.25))
        l = min(o, c) - abs(rng.normal(0, 0.25))
        t = int((start + pd.Timedelta(minutes=tf_minutes * i)).timestamp() * 1000)
        bars.append({"t": t, "o": float(o), "h": float(h), "l": float(l),
                     "c": float(c), "v": float(1000 + rng.integers(0, 500))})
    return bars


def test_features_in_range():
    bars = _synthetic_bars()
    df = pbt._bars_to_df(bars)
    F = pbt.compute_features(df)
    fcols = [f"f{i}" for i in range(1, 27)]
    for col in fcols:
        assert col in F.columns, f"missing {col}"
    # All features must be finite and within [-1, 1] (F15/F25 also fit this range)
    sub = F[fcols]
    assert np.isfinite(sub.values).all(), "non-finite feature values"
    assert sub.values.min() >= -1.0001, f"feature < -1: {sub.values.min()}"
    assert sub.values.max() <= 1.0001, f"feature > 1: {sub.values.max()}"


def test_run_produces_trades(monkeypatch):
    monkeypatch.setattr(pbt, "fetch_bars",
                        lambda *a, **k: _synthetic_bars(n=400))
    # Skip GitHub persistence in the test
    monkeypatch.setattr(pbt, "_persist", lambda out: None)

    out = pbt.run(symbols=["XAUUSD"], timeframes=["15"], days=30)
    assert "results" in out
    key = "XAUUSD_15"
    assert key in out["results"]
    res = out["results"][key]
    assert res["n_trades"] >= 1, f"expected >=1 trade, got {res}"
    for k in ("win_rate", "avg_pnl_pct", "profit_factor",
              "pct_SL", "pct_TP1", "pct_TP2", "pct_TP3"):
        assert k in res, f"missing metric {k}"


def test_exit_optimizer_integration(monkeypatch):
    monkeypatch.setattr(pbt, "fetch_bars",
                        lambda *a, **k: _synthetic_bars(n=400))
    monkeypatch.setattr(pbt, "_persist", lambda out: None)
    out = pbt.run(symbols=["XAUUSD"], timeframes=["15"], days=30)
    res = out["results"]["XAUUSD_15"]
    # exit_optimizer key present; value is either a dict (>=30 trades) or None
    assert "exit_optimizer" in res
    eo = res["exit_optimizer"]
    assert eo is None or isinstance(eo, dict)
