"""
Swing addon — Screener engine.

Scans a watchlist (top 70 S&P 500 by weight) twice daily (09:45 ET + 16:30 ET),
scoring each name on two axes, then applies two hard gates before ranking:

  Gate 1 — Fundamental quality: fundamental score > 0  (positive composite)
  Gate 2 — Valuation upside:    analyst mean target ≥ 20% above current price

  • Fundamental score  (fundamental_data.fetch_fundamentals) — the "why":
    analyst consensus, earnings surprise/drift, insider buying, growth, news.
  • Technical score     (computed here from daily bars) — the "when": daily-bar
    trend / momentum / RSI read, fused with the existing backend context layers
    (MTF confluence + HMM regime, both already computed for the intraday system).

Locks on the best 15 stocks that pass both gates. Each candidate carries
entry price, TP1/TP2/TP3 and SL (ATR-based) + entry quality flag so the
PWA shows actionable levels. Telegram swing channel is silent — app-only.

Cached in memory + persisted to the data branch. Graceful neutral fallback.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

# Top 70 S&P 500 constituents by index weight (mega-caps + sector leaders).
# Static list — index turnover is slow; revisit quarterly.
WATCHLIST = [
    # 1-10: mega-cap tech + consumer
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "AVGO", "TSLA",
    # 11-20: healthcare, financials, consumer
    "LLY", "JPM", "V", "XOM", "UNH", "MA", "COST", "HD", "PG", "JNJ",
    # 21-30: consumer, tech, pharma, energy
    "WMT", "NFLX", "ABBV", "BAC", "CRM", "ORCL", "MRK", "CVX", "KO", "AMD",
    # 31-40: consumer, tech, financials, healthcare
    "PEP", "ADBE", "WFC", "LIN", "TMO", "MCD", "CSCO", "ACN", "ABT", "GE",
    # 41-50: healthcare, tech, consumer, industrials
    "DHR", "TXN", "QCOM", "DIS", "VZ", "INTU", "AMGN", "CAT", "PFE", "IBM",
    # 51-60: financials, tech, industrials, healthcare (new)
    "GS", "MS", "NOW", "SPGI", "RTX", "HON", "AXP", "NEE", "AMAT", "LOW",
    # 61-70: tech, healthcare, industrials, consumer (new)
    "PANW", "ISRG", "SYK", "ETN", "BSX", "BLK", "UBER", "LRCX", "T", "SBUX",
]

# Sector ETF map for relative-strength (subset — defaults to SPY if unmapped).
_SECTOR = {
    "XLK": ["AAPL", "MSFT", "NVDA", "AVGO", "CRM", "ORCL", "AMD", "ADBE", "CSCO", "ACN",
            "TXN", "QCOM", "INTU", "IBM", "NOW", "AMAT", "PANW", "LRCX"],
    "XLC": ["META", "GOOGL", "GOOG", "NFLX", "DIS", "VZ", "T", "UBER"],
    "XLY": ["AMZN", "TSLA", "HD", "MCD", "COST", "LOW", "SBUX"],
    "XLV": ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "AMGN", "PFE",
            "ISRG", "SYK", "BSX"],
    "XLF": ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "SPGI", "BLK"],
    "XLE": ["XOM", "CVX"],
    "XLP": ["PG", "WMT", "KO", "PEP"],
    "XLI": ["GE", "CAT", "RTX", "HON", "ETN"],
    "XLB": ["LIN"],
    "XLU": ["NEE"],
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
    """Wilder-smoothed RSI (α = 1/period), consistent with TradingView + Pine Script."""
    if len(close) < period + 2:
        return 50.0
    d = np.diff(close)
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    # seed with simple average over first window
    ag = gain[:period].mean()
    al = loss[:period].mean()
    alpha = 1.0 / period
    for i in range(period, len(d)):
        ag = alpha * gain[i] + (1 - alpha) * ag
        al = alpha * loss[i] + (1 - alpha) * al
    if al == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + ag / al)


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


def _self_computed_upside(fund: dict) -> float | None:
    """
    Estimate implied upside % from FCF yield + PEG when analyst target unavailable.
    Both signals are already computed inside fetch_fundamentals() — no extra calls.
    Conservative: takes the lower of the two to avoid overstating cheapness.
    """
    adv = fund.get("advanced", {})
    fh  = fund.get("finnhub_metrics", {})
    signals = []

    # FCF yield vs 5% anchor: an 8% FCF yield implies ~60% upside to a 5%-yield fair value
    fcf_raw = fh.get("fcfYieldTTM")
    if fcf_raw is None and adv.get("fcf_yield_pct") is not None:
        fcf_raw = adv["fcf_yield_pct"] / 100.0
    if fcf_raw is not None:
        fcf_v = float(fcf_raw)
        if fcf_v > 0.02:  # only positive FCF yield is meaningful
            signals.append((fcf_v / 0.05 - 1.0) * 100)

    # PEG < 1.0 implies discount to fair growth-adjusted value
    peg = fh.get("pegAnnual") or adv.get("peg")
    if peg is not None:
        peg_v = float(peg)
        if 0.1 < peg_v < 5:
            signals.append((1.0 / peg_v - 1.0) * 50)  # PEG 0.5 → +50%, PEG 2 → −25%

    if not signals:
        return None
    return round(min(signals), 1)  # conservative: take the lower signal


def _technical_score(ticker: str) -> dict:
    """
    Daily-bar timing read → score ∈ [-1, +1].
    Now also returns:
      entry_quality: STRONG | FAIR | WAIT | AVOID
      entry_now:     bool — True when RSI + price position indicate a good entry TODAY
    """
    out = {"score": 0.0, "rsi": None, "trend": "NEUTRAL", "rel_strength_pct": None,
           "entry": None, "atr": None, "stop": None, "t1": None, "t2": None, "t3": None,
           "entry_quality": "WAIT", "entry_now": False, "rel_volume": None}
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

        # 63-day (3-month) momentum — captures sustained trend, not noise
        mom63 = (c[-1] / c[-63] - 1.0) if len(c) >= 63 else (c[-1] / c[-20] - 1.0 if len(c) >= 20 else 0.0)
        mom_score = float(np.clip(mom63 / 0.15, -1, 1))  # 15% 3-month move → full score

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

        # Relative volume — current bar vs 20-day average. Breakouts on low
        # relative volume fail >70% of the time; conviction volume confirms the
        # move. Bounded tilt so it nudges ranking without dominating it.
        try:
            v = d["Volume"].to_numpy(dtype=float)
            if len(v) >= 20:
                avg20 = float(v[-20:].mean())
                if avg20 > 0:
                    rel_vol = v[-1] / avg20
                    out["rel_volume"] = round(rel_vol, 2)
                    score += float(np.clip((rel_vol - 1.0) * 0.20, -0.10, 0.15))
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

        if rsi > 70 or trend_score < -0.1 or not price_above_200:
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
    """Full swing read for one ticker: fundamental + technical + valuation upside.

    Upside source priority:
      1. yfinance analyst consensus target (already in fund["analyst"]["target_upside_pct"])
      2. Self-computed from FCF yield + PEG (fallback when analyst target unavailable)
    No extra HTTP calls — all data already fetched by fetch_fundamentals().
    """
    from fundamental_data import fetch_fundamentals

    fund    = fetch_fundamentals(ticker)
    tech    = _technical_score(ticker)
    imminent = bool(fund["earnings"]["imminent"])
    combined = _combined(fund["score"], tech["score"], imminent)

    # Primary: yfinance consensus target (targetMedianPrice)
    upside_pct     = fund["analyst"].get("target_upside_pct")
    analyst_target = None
    current_price  = fund["analyst"].get("current_price")
    upside_source  = "analyst"

    # Fallback: self-computed from FCF yield + PEG
    if upside_pct is None:
        upside_pct    = _self_computed_upside(fund)
        upside_source = "computed" if upside_pct is not None else None

    return {
        "ticker":         ticker,
        "combined_score": combined,
        "upside_pct":     upside_pct,
        "analyst_target": analyst_target,
        "current_price":  current_price,
        "upside_source":  upside_source,
        "entry_quality":  tech.get("entry_quality", "WAIT"),
        "entry_now":      tech.get("entry_now", False),
        "fundamental":    fund,
        "technical":      tech,
        "updated_at":     _now(),
    }


def _upside_score_bonus(upside_pct: float | None) -> float:
    """
    Soft upside contribution to combined score.
    15–25% upside → linear ramp 0→+0.05. Above 25% → flat +0.05.
    Applied on top of combined_score so stocks at 15% don't tie with 30%+ ones.
    """
    if upside_pct is None:
        return 0.0
    if upside_pct >= 25.0:
        return 0.05
    if upside_pct >= 15.0:
        return round((upside_pct - 15.0) / 10.0 * 0.05, 4)
    return 0.0


def run_screen(top_n: int = 15) -> dict:
    """
    Scan full watchlist, apply two gates, rank by combined score, lock the best 15.
    Also produces a watchlist of WAIT-quality stocks passing Gate 1 (not ready to
    enter but worth monitoring — may flip STRONG/FAIR within days).
    Runs twice daily: 09:45 ET (morning) + 16:30 ET (close).

    Gate 1 — Valuation (≥15% upside, soft): hard floor at 15%; stocks 15–25% get a
              small score nudge (+0–0.05) so 30%+ upside outranks 15% upside naturally.
              Skipped gracefully when no target is available (not penalised).

    Gate 2 — Technical entry: STRONG or FAIR → active candidates.
              WAIT (good value, not timed) → watchlist only.
              AVOID → rejected entirely.
    """
    global _cached
    rows        = []
    watchlist   = []   # WAIT-quality stocks that pass Gate 1
    skipped_upside    = 0
    skipped_technical = 0

    import time as _time
    for _idx, t in enumerate(WATCHLIST):
        # Finnhub free tier: 60 req/min; screen_one makes ~4 calls per ticker.
        # Throttle every 12 tickers (~48 calls) to stay under the limit.
        if _idx > 0 and _idx % 12 == 0:
            _time.sleep(5)
        try:
            r = screen_one(t)

            # Gate 1: hard floor ≥15% upside (down from 20% cliff)
            upside = r.get("upside_pct")
            if upside is not None and upside < 15.0:
                skipped_upside += 1
                continue

            # Soft upside bonus nudges score ranking between 15–25%
            bonus = _upside_score_bonus(upside)
            if bonus:
                r["combined_score"] = round(
                    float(np.clip(r["combined_score"] + bonus, -1, 1)), 3
                )

            # Gate 2: active entry vs watch-only vs reject
            eq = r.get("entry_quality") or r["technical"].get("entry_quality", "WAIT")
            if eq in ("STRONG", "FAIR"):
                rows.append(r)
            elif eq == "WAIT":
                watchlist.append(r)
            else:
                skipped_technical += 1

        except Exception as e:
            print(f"[swing] screen {t} failed: {e}")

    # Sort: entry_now first, then combined score
    rows.sort(key=lambda r: (r.get("entry_now", False), r["combined_score"]), reverse=True)
    watchlist.sort(key=lambda r: r["combined_score"], reverse=True)
    top = rows[:top_n]

    result = {
        "candidates":          top,
        "watchlist":           watchlist[:10],   # top 10 WAIT names worth monitoring
        "scanned":             len(WATCHLIST),
        "passed_gates":        len(rows),
        "watching":            len(watchlist),
        "top_n":               top_n,
        "skipped_upside":      skipped_upside,
        "skipped_technical":   skipped_technical,
        "updated_at":          _now(),
    }
    _cached = result
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_SWING_PATH)
        _put_file(_SWING_PATH, result, sha, "data: update swing candidates")
    except Exception as e:
        print(f"[swing] persist failed: {e}")

    summary = " | ".join(
        f"{r['ticker']}({r['combined_score']:+.2f} ↑{r['upside_pct']:.0f}% [{r.get('entry_quality','?')}])"
        for r in top
    )
    watch_summary = ", ".join(r['ticker'] for r in watchlist[:5])
    print(f"[swing] {len(WATCHLIST)} scanned → {skipped_upside} failed upside → "
          f"{skipped_technical} AVOID → {len(rows)} active → {len(watchlist)} watching → "
          f"top {len(top)}: {summary} | watch: {watch_summary}")
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
