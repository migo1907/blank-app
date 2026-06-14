"""
Swing addon — Screener engine.

Scans a watchlist (top 50 S&P 500 by weight) once per evening after the close,
scoring each name on two axes and ranking the best swing-trade candidates:

  • Fundamental score  (fundamental_data.fetch_fundamentals) — the "why":
    analyst consensus, earnings surprise/drift, insider buying, growth, news.
  • Technical score     (computed here from daily bars) — the "when": daily-bar
    trend / momentum / RSI read, fused with the existing backend context layers
    (MTF confluence + HMM regime, both already computed for the intraday system).

This is deliberately a separate brain from the intraday signal engine: daily
horizon (3–15 day holds), no Pine Script / TradingView involvement, pure backend
yfinance pulls (with the Stooq daily fallback baked into market_data).

The ML entry-timing ensemble is intentionally NOT wired in yet — there are no
closed swing trades to train it on. Per the cold-start rule, the technical score
is rules-based until the swing pool accumulates real outcomes, at which point the
ensemble plugs into `_technical_score` exactly like the intraday pools.

Cached in memory + persisted to the data branch, refreshed nightly. Graceful
neutral fallback at every layer.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

# Top 50 S&P 500 constituents by index weight (mega-caps + sector leaders).
# Static list — index turnover is slow; revisit quarterly.
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "AVGO", "TSLA",
    "LLY", "JPM", "V", "XOM", "UNH", "MA", "COST", "HD", "PG", "JNJ",
    "WMT", "NFLX", "ABBV", "BAC", "CRM", "ORCL", "MRK", "CVX", "KO", "AMD",
    "PEP", "ADBE", "WFC", "LIN", "TMO", "MCD", "CSCO", "ACN", "ABT", "GE",
    "DHR", "TXN", "QCOM", "DIS", "VZ", "INTU", "AMGN", "CAT", "PFE", "IBM",
]

# Sector ETF map for relative-strength (subset — defaults to SPY if unmapped).
_SECTOR = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "CRM", "ORCL", "AMD", "ADBE", "CSCO", "ACN",
            "TXN", "QCOM", "INTU", "IBM"],
    "XLC": ["META", "GOOGL", "GOOG", "NFLX", "DIS", "VZ"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "COST"],
    "XLV": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "AMGN", "PFE"],
    "XLF": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC"],
    "XLE": ["XOM", "CVX"],
    "XLP": ["PG", "WMT", "KO", "PEP"],
    "XLI": ["GE", "CAT"],
    "XLB": ["LIN"],
}
_TICKER_SECTOR = {t: etf for etf, ts in _SECTOR.items() for t in ts}

_SWING_PATH = "data/swing_candidates.json"
_cached: dict = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    alpha = 2.0 / (span + 1.0)
    out = np.empty_like(x, dtype=float)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(close: np.ndarray, period: int = 14) -> float:
    if len(close) < period + 1:
        return 50.0
    d = np.diff(close)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    ag = gain[-period:].mean()
    al = loss[-period:].mean()
    if al == 0:
        return 100.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(d, period: int = 14) -> float | None:
    """Daily ATR(14) from an OHLC frame (simple mean of true range)."""
    try:
        h = d["High"].to_numpy(dtype=float)
        l = d["Low"].to_numpy(dtype=float)
        c = d["Close"].to_numpy(dtype=float)
        if len(c) < period + 1:
            return None
        prev = c[:-1]
        tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - prev), np.abs(l[1:] - prev)])
        return float(tr[-period:].mean())
    except Exception:
        return None


def _technical_score(ticker: str) -> dict:
    """
    Daily-bar timing read → score ∈ [-1, +1]. Combines EMA trend, momentum, and a
    mean-reversion-aware RSI band. Sector relative strength applied as a tilt.
    """
    out = {"score": 0.0, "rsi": None, "trend": "NEUTRAL", "rel_strength_pct": None,
           "entry": None, "atr": None, "stop": None, "t1": None, "t2": None}
    try:
        from market_data import fetch_daily

        d = fetch_daily(ticker, period="1y")
        if not len(d):
            return out
        c = d["Close"].to_numpy(dtype=float)
        if len(c) < 60:
            return out

        # Suggested levels — same ATR basis the paper-trade tracker grades on, so the
        # displayed entry/stop/targets match how WIN/LOSS is later judged.
        atr = _atr(d)
        if atr:
            entry = float(c[-1])
            out["entry"] = round(entry, 2)
            out["atr"]   = round(atr, 2)
            out["stop"]  = round(entry - 1.0 * atr, 2)   # -1 ATR  (paper SL)
            out["t1"]    = round(entry + 2.0 * atr, 2)   # +2 ATR  (paper TP)
            out["t2"]    = round(entry + 3.0 * atr, 2)   # +3 ATR  (stretch)

        ef, es = _ema(c, 20), _ema(c, 50)
        spread = (ef[-1] - es[-1]) / max(abs(es[-1]), 1e-9)
        trend_score = float(np.clip(spread / 0.05, -1, 1))  # ±5% EMA gap → ±1

        mom = (c[-1] / c[-20] - 1.0) if len(c) >= 20 else 0.0
        mom_score = float(np.clip(mom / 0.10, -1, 1))        # ±10% in 20d → ±1

        rsi = _rsi(c)
        out["rsi"] = round(rsi, 1)
        # Reward pullbacks inside an uptrend (RSI 40–55), penalize overbought
        if rsi >= 75:
            rsi_score = -0.5
        elif rsi <= 30:
            rsi_score = 0.3   # oversold bounce candidate
        elif 40 <= rsi <= 55:
            rsi_score = 0.4   # healthy pullback entry zone
        else:
            rsi_score = 0.0

        score = 0.45 * trend_score + 0.35 * mom_score + 0.20 * rsi_score
        out["trend"] = "BULL" if trend_score > 0.15 else "BEAR" if trend_score < -0.15 else "NEUTRAL"

        # Sector relative strength tilt (stock 20d vs its sector ETF 20d)
        etf = _TICKER_SECTOR.get(ticker, "SPY")
        try:
            ed = fetch_daily(etf, period="3mo")
            if len(ed) >= 20:
                ec = ed["Close"].to_numpy(dtype=float)
                stock_20 = c[-1] / c[-20] - 1.0
                etf_20 = ec[-1] / ec[-20] - 1.0
                rel = stock_20 - etf_20
                out["rel_strength_pct"] = round(rel * 100, 1)
                score += float(np.clip(rel / 0.10, -0.2, 0.2))  # bounded tilt
        except Exception:
            pass

        out["score"] = round(float(np.clip(score, -1, 1)), 3)
    except Exception as e:
        print(f"[swing] technical {ticker} failed: {e}")
    return out


def _combined(fund_score: float, tech_score: float, imminent_earnings: bool) -> float:
    """Fundamental 'why' (0.55) + technical 'when' (0.45). De-risk into earnings."""
    combined = 0.55 * fund_score + 0.45 * tech_score
    if imminent_earnings:
        combined *= 0.6   # binary-event risk — shrink conviction before the print
    return round(combined, 3)


def screen_one(ticker: str) -> dict:
    """Full swing read for one ticker: fundamental + technical + combined score."""
    from fundamental_data import fetch_fundamentals

    fund = fetch_fundamentals(ticker)
    tech = _technical_score(ticker)
    imminent = bool(fund["earnings"]["imminent"])
    combined = _combined(fund["score"], tech["score"], imminent)
    return {
        "ticker":        ticker,
        "combined_score": combined,
        "fundamental":   fund,
        "technical":     tech,
        "updated_at":    _now(),
    }


def run_screen(top_n: int = 5) -> dict:
    """Scan the full watchlist, rank by combined score, cache + persist. Nightly."""
    global _cached
    rows = []
    for t in WATCHLIST:
        try:
            rows.append(screen_one(t))
        except Exception as e:
            print(f"[swing] screen {t} failed: {e}")

    rows.sort(key=lambda r: r["combined_score"], reverse=True)
    result = {
        "candidates": rows[:top_n],
        "scanned":    len(rows),
        "top_n":      top_n,
        "updated_at": _now(),
    }
    _cached = result
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_SWING_PATH)
        _put_file(_SWING_PATH, result, sha, "data: update swing candidates")
    except Exception as e:
        print(f"[swing] persist failed: {e}")

    top = " | ".join(f"{r['ticker']}({r['combined_score']:+.2f})" for r in rows[:top_n])
    print(f"[swing] screened {len(rows)} names — top: {top}")
    return result


def get_candidates() -> dict:
    return _cached or {"candidates": [], "scanned": 0}


def load_candidates() -> None:
    """Load persisted swing candidates from the data branch on startup."""
    global _cached
    try:
        from db import _get_file
        data, _ = _get_file(_SWING_PATH)
        if isinstance(data, dict) and data.get("candidates"):
            _cached = data
            print(f"[swing] loaded {len(data['candidates'])} cached swing candidates")
    except Exception as e:
        print(f"[swing] load failed: {e}")
