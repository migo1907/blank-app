"""
Unified market-data fetch for the Phase 2 context layers.

Daily OHLCV: Stooq (primary, free, no key, works from Railway cloud IPs)
             → Alpha Vantage (secondary for stocks, budget-limited)
Intraday:    Alpha Vantage (stocks only) — no reliable free intraday source.

yfinance removed — it silently breaks from cloud IPs and requires no-auth
Yahoo scraping which is increasingly unreliable.

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


_av_4h_cache: dict = {}   # ticker -> (epoch_fetched, df)


def alphavantage_4h(ticker: str, max_age_min: int = 90):
    """4-hour bars for ANY US equity, for swing entry confirmation. Pulls AV 60-min
    and resamples to 4H. Budget-guarded (shares the ~25/day AV pool) + cached in
    memory for max_age_min. Returns an EMPTY DataFrame when key absent / over budget
    / rate-limited, so callers degrade to daily-only gracefully."""
    import pandas as pd, time as _t
    sym = ticker.upper()
    ent = _av_4h_cache.get(sym)
    if ent and (_t.time() - ent[0]) < max_age_min * 60:
        return ent[1]
    if not ALPHAVANTAGE_KEY or not _av_budget_ok():
        return ent[1] if ent else pd.DataFrame()
    url = "https://www.alphavantage.co/query"
    params = {"function": "TIME_SERIES_INTRADAY", "symbol": sym,
              "interval": "60min", "outputsize": "compact", "apikey": ALPHAVANTAGE_KEY}
    try:
        _av_calls["count"] += 1
        with httpx.Client(timeout=15) as client:
            r = client.get(url, params=params); r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"[mktdata] AV 4H {sym} failed: {e}")
        _health("alphavantage_4h", False, "price", str(e))
        return ent[1] if ent else pd.DataFrame()
    series = data.get("Time Series (60min)")
    if not series:
        _health("alphavantage_4h", False, "price",
                str(data.get("Note") or data.get("Information") or "no series")[:80])
        return ent[1] if ent else pd.DataFrame()
    rows = [{"Open": float(v["1. open"]), "High": float(v["2. high"]),
             "Low": float(v["3. low"]), "Close": float(v["4. close"]),
             "Volume": float(v.get("5. volume", 0)), "_ts": ts}
            for ts, v in series.items()]
    df = pd.DataFrame(rows)
    df["_ts"] = pd.to_datetime(df["_ts"], utc=True)
    df = df.set_index("_ts").sort_index()
    # Resample 60-min → 4-hour bars
    df4 = df.resample("4h").agg({"Open": "first", "High": "max", "Low": "min",
                                 "Close": "last", "Volume": "sum"}).dropna()
    df4.index.name = "Date"
    _av_4h_cache[sym] = (_t.time(), df4)
    _health("alphavantage_4h", True, "price")
    return df4


def fetch_intraday(ticker: str, interval: str = "1h", period: str = "60d"):
    """Intraday OHLC — Alpha Vantage for mapped equities (SPY/QQQ), budget-guarded."""
    import pandas as pd
    av = _alphavantage_intraday(ticker, interval="60min")
    if len(av):
        _health("alphavantage_intraday", True, "price")
        return av
    return pd.DataFrame()


# ── Alpha Vantage OVERVIEW — cloud-reliable fundamentals incl. analyst target ──
# Free tier is rate-limited (~25/day, shared budget with intraday), but company
# fundamentals + analyst targets move slowly, so the result is cached on the data
# branch for 7 days per ticker. Over a few nightly scans the whole universe fills
# in. This replaces the swing valuation gate's dependence on yfinance analyst
# targets (which silently fail from Railway cloud IPs).
_AV_OVERVIEW_CACHE_PATH = "data/av_overview_cache.json"
_av_overview_cache: dict | None = None


def _load_av_overview_cache() -> dict:
    global _av_overview_cache
    if _av_overview_cache is None:
        try:
            from db import _get_file
            d, _ = _get_file(_AV_OVERVIEW_CACHE_PATH)
            _av_overview_cache = d if isinstance(d, dict) else {}
        except Exception:
            _av_overview_cache = {}
    return _av_overview_cache


def alphavantage_overview(ticker: str, max_age_days: int = 7) -> dict:
    """AV OVERVIEW fundamentals (incl. AnalystTargetPrice). Cached 7d on data branch.
    Returns {} when key absent / over budget / rate-limited (graceful)."""
    from datetime import timedelta
    sym = ticker.upper()
    cache = _load_av_overview_cache()
    ent = cache.get(sym)
    now = datetime.now(timezone.utc)
    if ent:
        try:
            if now - datetime.fromisoformat(ent["fetched_at"]) < timedelta(days=max_age_days):
                return ent.get("data") or {}
        except Exception:
            pass
    if not ALPHAVANTAGE_KEY or not _av_budget_ok():
        return (ent.get("data") if ent else {}) or {}
    try:
        _av_calls["count"] += 1
        with httpx.Client(timeout=15) as client:
            r = client.get("https://www.alphavantage.co/query", params={
                "function": "OVERVIEW", "symbol": sym, "apikey": ALPHAVANTAGE_KEY})
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        print(f"[mktdata] AV OVERVIEW {sym} failed: {e}")
        _health("alphavantage_overview", False, "fundamentals", str(e))
        return (ent.get("data") if ent else {}) or {}
    if not isinstance(data, dict) or "Symbol" not in data:
        # rate-limit / Note / Information response
        _health("alphavantage_overview", False, "fundamentals", str(data)[:80])
        return (ent.get("data") if ent else {}) or {}
    cache[sym] = {"fetched_at": now.isoformat(), "data": data}
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_AV_OVERVIEW_CACHE_PATH)
        _put_file(_AV_OVERVIEW_CACHE_PATH, cache, sha, f"chore: AV overview cache {sym}")
    except Exception as e:
        print(f"[mktdata] AV overview cache persist skipped: {e}")
    _health("alphavantage_overview", True, "fundamentals")
    return data


def alphavantage_target_upside(ticker: str, current_price: float | None):
    """(upside_pct, target_price) from AV AnalystTargetPrice vs current price, or (None, None)."""
    if not current_price or current_price <= 0:
        return None, None
    ov = alphavantage_overview(ticker)
    raw = ov.get("AnalystTargetPrice")
    if not raw or raw in ("None", "-"):
        return None, None
    try:
        target = float(raw)
        if target <= 0:
            return None, None
        return round((target - current_price) / current_price * 100, 1), round(target, 2)
    except Exception:
        return None, None


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


def _health(source: str, ok: bool, category: str = "", detail: str = "") -> None:
    """Report a fetch outcome to the data-flow health registry (never raises)."""
    try:
        import data_health
        data_health.record(source, ok, category, detail)
    except Exception:
        pass


def fetch_daily(ticker: str, period: str = "1y"):
    """Daily OHLC — Stooq primary (free, cloud-reliable). Empty DataFrame if unavailable."""
    import pandas as pd
    sym = STOOQ_SYMBOLS.get(ticker)
    if sym:
        try:
            df = _stooq_daily(sym)
            if len(df):
                _health("stooq_daily", True, "price")
                return df
            _health("stooq_daily", False, "price", f"empty for {sym}")
        except Exception as e:
            print(f"[mktdata] Stooq {sym} failed: {e}")
            _health("stooq_daily", False, "price", str(e))
    return pd.DataFrame()
