"""
Unified market-data fetch for the Phase 2 context layers.

Primary source: yfinance (intraday + daily). Fallback: Stooq daily CSV — free,
no API key, no login — used when yfinance drops/rate-limits on a DAILY fetch
(Stooq's free tier has no intraday, so intraday stays yfinance-only with the
existing graceful-neutral fallback in each layer).

Every function returns a pandas DataFrame shaped like yfinance's `.history()`
(Open/High/Low/Close columns, tz-aware DatetimeIndex) or an EMPTY DataFrame on
total failure — callers already treat empty as "no data → stay neutral".
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone

import httpx

# Alpha Vantage — optional TERTIARY intraday fallback for stocks (SPY/QQQ) when
# yfinance intraday drops. Free tier is tightly rate-limited (≈25 req/day), so a
# conservative daily budget guard prevents quota exhaustion. Dormant if no key.
ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_KEY", "")
_AV_DAILY_BUDGET = 20
_av_calls: dict = {"date": None, "count": 0}

# yfinance ticker → Alpha Vantage equity symbol (intraday TIME_SERIES_INTRADAY).
# Only equities AV serves cleanly on the free tier; gold/VIX/DXY are not mapped.
AV_SYMBOLS = {"SPY": "SPY", "QQQ": "QQQ"}

# yfinance ticker → Stooq daily symbol (no key). Best-effort; unknown symbols
# simply skip the fallback and the layer degrades to neutral.
STOOQ_SYMBOLS = {
    "GC=F":      "xauusd",   # gold (spot proxy on Stooq)
    "SPY":       "spy.us",
    "QQQ":       "qqq.us",
    "^VIX":      "^vix",
    "^VIX3M":    "^vix3m",
    "DX-Y.NYB":  "^dxy",     # US dollar index
    "UUP":       "uup.us",
}

_STOOQ_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _yf_history(ticker: str, period: str, interval: str):
    import yfinance as yf
    return yf.Ticker(ticker).history(period=period, interval=interval)


def _av_budget_ok() -> bool:
    """True if we're under the conservative daily Alpha Vantage call budget."""
    today = datetime.now(timezone.utc).date().isoformat()
    if _av_calls["date"] != today:
        _av_calls["date"], _av_calls["count"] = today, 0
    return _av_calls["count"] < _AV_DAILY_BUDGET


def _alphavantage_intraday(ticker: str, interval: str = "60min"):
    """Alpha Vantage intraday for a mapped equity → yfinance-shaped DataFrame."""
    import pandas as pd
    sym = AV_SYMBOLS.get(ticker)
    if not sym or not ALPHAVANTAGE_KEY or not _av_budget_ok():
        return pd.DataFrame()
    url = "https://www.alphavantage.co/query"
    params = {"function": "TIME_SERIES_INTRADAY", "symbol": sym,
              "interval": interval, "outputsize": "full", "apikey": ALPHAVANTAGE_KEY}
    try:
        _av_calls["count"] += 1
        with httpx.Client(timeout=15) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"[mktdata] Alpha Vantage {sym} failed: {e}")
        return pd.DataFrame()
    series = data.get(f"Time Series ({interval})")
    if not series:
        # Rate-limit / info responses arrive as {"Note"|"Information": ...}
        msg = data.get("Note") or data.get("Information") or "no series"
        print(f"[mktdata] Alpha Vantage {sym}: {str(msg)[:80]}")
        return pd.DataFrame()
    rows = []
    for ts, vals in series.items():
        rows.append({
            "Open":  float(vals.get("1. open", 0)),
            "High":  float(vals.get("2. high", 0)),
            "Low":   float(vals.get("3. low", 0)),
            "Close": float(vals.get("4. close", 0)),
            "Volume": float(vals.get("5. volume", 0)),
            "_ts": ts,
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["_ts"] = pd.to_datetime(df["_ts"], utc=True)
    df = df.set_index("_ts").sort_index()
    df.index.name = "Date"
    print(f"[mktdata] {ticker} intraday via Alpha Vantage fallback ({len(df)} bars)")
    return df


def fetch_intraday(ticker: str, interval: str = "1h", period: str = "60d"):
    """Intraday OHLC — yfinance primary, Alpha Vantage fallback (stocks, budgeted)."""
    import pandas as pd
    try:
        df = _yf_history(ticker, period, interval)
        if len(df):
            return df
    except Exception as e:
        print(f"[mktdata] yfinance intraday {ticker} failed: {e}")
    # Tertiary: Alpha Vantage for mapped equities (SPY/QQQ), budget-guarded.
    av = _alphavantage_intraday(ticker, interval="60min")
    if len(av):
        return av
    return pd.DataFrame()


def _stooq_daily(stooq_symbol: str):
    """Daily OHLC CSV from Stooq → yfinance-shaped DataFrame (or empty)."""
    import pandas as pd
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    with httpx.Client(timeout=12) as client:
        r = client.get(url, headers={"User-Agent": _STOOQ_UA})
        r.raise_for_status()
        text = r.text or ""
    lines = text.splitlines()
    if not lines or "Date" not in lines[0] or "Close" not in lines[0]:
        return pd.DataFrame()      # Stooq returns "N/D" / HTML for bad symbols
    df = pd.read_csv(io.StringIO(text))
    if df.empty or "Close" not in df.columns:
        return pd.DataFrame()
    df["Date"] = pd.to_datetime(df["Date"], utc=True)
    df = df.set_index("Date").sort_index()
    # Already Open/High/Low/Close-cased; keep only what callers use.
    keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in df.columns]
    return df[keep]


def fetch_daily(ticker: str, period: str = "1y"):
    """Daily OHLC — yfinance primary, Stooq fallback. Empty DataFrame if both fail."""
    import pandas as pd
    try:
        df = _yf_history(ticker, period, "1d")
        if len(df):
            return df
    except Exception as e:
        print(f"[mktdata] yfinance daily {ticker} failed: {e}")

    sym = STOOQ_SYMBOLS.get(ticker)
    if sym:
        try:
            df = _stooq_daily(sym)
            if len(df):
                print(f"[mktdata] {ticker} served via Stooq fallback ({len(df)} daily bars)")
                return df
        except Exception as e:
            print(f"[mktdata] Stooq fallback {sym} failed: {e}")
    return pd.DataFrame()
