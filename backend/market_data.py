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

import httpx

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


def fetch_intraday(ticker: str, interval: str = "1h", period: str = "60d"):
    """Intraday OHLC — yfinance only. Empty DataFrame on failure."""
    import pandas as pd
    try:
        df = _yf_history(ticker, period, interval)
        if len(df):
            return df
    except Exception as e:
        print(f"[mktdata] yfinance intraday {ticker} failed: {e}")
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
