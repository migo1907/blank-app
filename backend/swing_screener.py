"""
Swing addon — Screener engine.

Scans a watchlist (top 50 S&P 500 by weight) twice daily (09:45 ET + 16:30 ET),
scoring each name on two axes, then applies two hard gates before ranking:

  Gate 1 — Fundamental quality: fundamental score > 0  (positive composite)
  Gate 2 — Valuation upside:    analyst mean target ≥ 20% above current price

  • Fundamental score  (fundamental_data.fetch_fundamentals) — the "why":
    analyst consensus, earnings surprise/drift, insider buying, growth, news.
  • Technical score     (computed here from daily bars) — the "when": daily-bar
    trend / momentum / RSI read, fused with the existing backend context layers
    (MTF confluence + HMM regime, both already computed for the intraday system).

Locks on the best 10 stocks that pass both gates. Each candidate carries
entry price, TP1/TP2/TP3 and SL (ATR-based) + entry quality flag so the
Telegram brief + PWA show actionable levels.

Cached in memory + persisted to the data branch. Graceful neutral fallback.
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


def _analyst_target(ticker: str) -> dict:
    """
    Fetch analyst consensus price target from Finnhub.
    Returns {mean_target, upside_pct, n_analysts} or {} on failure.
    Upside gate: mean_target >= current * 1.20  (≥20% upside).
    """
    import os, httpx
    key = os.environ.get("FINNHUB_KEY", "")
    if not key:
        return {}
    try:
        r = httpx.get(
            "https://finnhub.io/api/v1/stock/price-target",
            params={"symbol": ticker, "token": key},
            timeout=8,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        mean_t = data.get("targetMean") or data.get("targetMedian")
        n = data.get("lastUpdated") and data.get("symbol") and 1  # just check it came back
        if not mean_t:
            return {}
        # Get current price from yfinance fast_info
        import yfinance as yf
        price = yf.Ticker(ticker).fast_info.last_price
        if not price or price <= 0:
            return {}
        upside = (mean_t - price) / price
        return {
            "analyst_target": round(float(mean_t), 2),
            "current_price":  round(float(price), 2),
            "upside_pct":     round(upside * 100, 1),
        }
    except Exception as e:
        print(f"[swing] analyst target {ticker} failed: {e}")
        return {}


def _technical_score(ticker: str) -> dict:
    """
    Daily-bar timing read → score ∈ [-1, +1].
    Now also returns:
      entry_quality: STRONG | FAIR | WAIT | AVOID
      entry_now:     bool — True when RSI + price position indicate a good entry TODAY
    """
    out = {"score": 0.0, "rsi": None, "trend": "NEUTRAL", "rel_strength_pct": None,
           "entry": None, "atr": None, "stop": None, "t1": None, "t2": None, "t3": None,
           "entry_quality": "WAIT", "entry_now": False}
    try:
        from market_data import fetch_daily

        d = fetch_daily(ticker, period="1y")
        if not len(d):
            return out
        c = d["Close"].to_numpy(dtype=float)
        if len(c) < 60:
            return out

        atr = _atr(d)
        if atr:
            entry = float(c[-1])
            out["entry"] = round(entry, 2)
            out["atr"]   = round(atr, 2)
            out["stop"]  = round(entry - 1.0 * atr, 2)   # -1 ATR  SL
            out["t1"]    = round(entry + 2.0 * atr, 2)   # +2 ATR  TP1
            out["t2"]    = round(entry + 3.0 * atr, 2)   # +3 ATR  TP2
            out["t3"]    = round(entry + 5.0 * atr, 2)   # +5 ATR  TP3 (swing extension)

        ef20, es50, el200 = _ema(c, 20), _ema(c, 50), _ema(c, 200)
        spread = (ef20[-1] - es50[-1]) / max(abs(es50[-1]), 1e-9)
        trend_score = float(np.clip(spread / 0.05, -1, 1))

        mom20 = (c[-1] / c[-20] - 1.0) if len(c) >= 20 else 0.0
        mom_score = float(np.clip(mom20 / 0.10, -1, 1))

        rsi = _rsi(c)
        out["rsi"] = round(rsi, 1)

        if rsi >= 75:
            rsi_score = -0.5
        elif rsi <= 30:
            rsi_score = 0.3
        elif 40 <= rsi <= 58:
            rsi_score = 0.4   # healthy pullback — best entry zone
        else:
            rsi_score = 0.0

        score = 0.45 * trend_score + 0.35 * mom_score + 0.20 * rsi_score

        # Sector relative strength tilt
        etf = _TICKER_SECTOR.get(ticker, "SPY")
        rel = 0.0
        try:
            ed = fetch_daily(etf, period="3mo")
            if len(ed) >= 20:
                ec = ed["Close"].to_numpy(dtype=float)
                stock_20 = c[-1] / c[-20] - 1.0
                etf_20   = ec[-1] / ec[-20] - 1.0
                rel = stock_20 - etf_20
                out["rel_strength_pct"] = round(rel * 100, 1)
                score += float(np.clip(rel / 0.10, -0.2, 0.2))
        except Exception:
            pass

        if np.isnan(score):
            score = 0.0
        out["score"] = round(float(np.clip(score, -1, 1)), 3)
        out["trend"] = "BULL" if trend_score > 0.15 else "BEAR" if trend_score < -0.15 else "NEUTRAL"

        # ── Entry quality assessment ─────────────────────────────────
        # STRONG: uptrend (price > EMA20 > EMA50 > EMA200) + RSI pullback 40-58
        # FAIR:   uptrend + RSI 58-65 (a bit stretched but ok)
        # WAIT:   mixed trend or RSI overbought
        # AVOID:  downtrend or RSI > 70
        price_above_200 = c[-1] > el200[-1]
        price_above_50  = c[-1] > es50[-1]
        ema_stack_bull  = ef20[-1] > es50[-1] > el200[-1]
        near_ema20      = abs(c[-1] - ef20[-1]) / ef20[-1] < 0.03  # within 3% of 20EMA

        if rsi > 70 or trend_score < -0.1:
            entry_quality = "AVOID"
            entry_now = False
        elif ema_stack_bull and 40 <= rsi <= 58:
            entry_quality = "STRONG"
            entry_now = True
        elif (price_above_50 or price_above_200) and rsi <= 65:
            entry_quality = "FAIR"
            entry_now = (rsi <= 60 and near_ema20)
        else:
            entry_quality = "WAIT"
            entry_now = False

        out["entry_quality"] = entry_quality
        out["entry_now"]     = entry_now

    except Exception as e:
        print(f"[swing] technical {ticker} failed: {e}")
    return out


def _combined(fund_score: float, tech_score: float, imminent_earnings: bool) -> float:
    """Fundamental 'why' (0.55) + technical 'when' (0.45). De-risk into earnings."""
    combined = 0.55 * fund_score + 0.45 * tech_score
    if imminent_earnings:
        combined *= 0.6
    return round(combined, 3)


def screen_one(ticker: str) -> dict:
    """Full swing read for one ticker: fundamental + technical + valuation upside."""
    from fundamental_data import fetch_fundamentals

    fund    = fetch_fundamentals(ticker)
    tech    = _technical_score(ticker)
    val     = _analyst_target(ticker)
    imminent = bool(fund["earnings"]["imminent"])
    combined = _combined(fund["score"], tech["score"], imminent)
    return {
        "ticker":         ticker,
        "combined_score": combined,
        "upside_pct":     val.get("upside_pct"),
        "analyst_target": val.get("analyst_target"),
        "current_price":  val.get("current_price"),
        "entry_quality":  tech.get("entry_quality", "WAIT"),
        "entry_now":      tech.get("entry_now", False),
        "fundamental":    fund,
        "technical":      tech,
        "updated_at":     _now(),
    }


def run_screen(top_n: int = 10) -> dict:
    """
    Scan full watchlist, apply fundamental + 20% upside gates, rank by combined
    score, lock the best 10. Runs twice daily: 09:45 ET (morning) + 16:30 ET (close).
    """
    global _cached
    rows = []
    skipped_upside   = 0
    skipped_fundament = 0

    for t in WATCHLIST:
        try:
            r = screen_one(t)
            # Gate 1: positive fundamental score
            if r["fundamental"]["score"] <= 0:
                skipped_fundament += 1
                continue
            # Gate 2: ≥20% analyst upside (skip if target unavailable — don't penalise)
            upside = r.get("upside_pct")
            if upside is not None and upside < 20.0:
                skipped_upside += 1
                continue
            rows.append(r)
        except Exception as e:
            print(f"[swing] screen {t} failed: {e}")

    # Sort: entry_now stocks first, then by combined score
    rows.sort(key=lambda r: (r.get("entry_now", False), r["combined_score"]), reverse=True)
    top = rows[:top_n]

    result = {
        "candidates":         top,
        "scanned":            len(WATCHLIST),
        "passed_gates":       len(rows),
        "top_n":              top_n,
        "skipped_upside":     skipped_upside,
        "skipped_fundamental": skipped_fundament,
        "updated_at":         _now(),
    }
    _cached = result
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_SWING_PATH)
        _put_file(_SWING_PATH, result, sha, "data: update swing candidates")
    except Exception as e:
        print(f"[swing] persist failed: {e}")

    summary = " | ".join(
        f"{r['ticker']}({r['combined_score']:+.2f} ↑{r['upside_pct']:.0f}%{'⚡' if r['entry_now'] else ''})"
        for r in top
    )
    print(f"[swing] {len(WATCHLIST)} scanned → {len(rows)} passed gates → top {len(top)}: {summary}")
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
