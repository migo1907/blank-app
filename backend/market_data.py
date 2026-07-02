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


_IBKR_BAR = {"1min": "1min", "5min": "5min", "15min": "15min", "30min": "30min",
             "60min": "1h", "1h": "1h", "4h": "4h", "1d": "1d"}


def fetch_intraday(ticker: str, interval: str = "1h", period: str = "60d"):
    """Intraday OHLC — IBKR gateway first (live, same feed we trade), then Alpha
    Vantage for mapped equities (SPY/QQQ), budget-guarded. IBKR is inert unless a
    Client Portal Gateway is configured (IBKR_GATEWAY_URL), so this is a no-op
    upgrade until then."""
    import pandas as pd
    try:
        import ibkr_data
        if ibkr_data.available():
            bar = _IBKR_BAR.get(interval, "1h")
            per = "6m" if bar in ("1h", "4h", "1d") else "5d"
            df = ibkr_data.fetch_history(ticker, period=per, bar=bar)
            if len(df):
                _health("ibkr_intraday", True, "price")
                return df
    except Exception as e:
        print(f"[mktdata] IBKR intraday {ticker} failed: {e}")
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


# ── TradingView scanner batch quotes ─────────────────────────────────────────
# Same scanner the daily brief (`daily_analysis._fetch_live_price_tv`) and the
# GitHub Actions daily-levels job already rely on — the most reliable live-quote
# source from Railway cloud IPs (Yahoo blocks/rate-limits them).
_TV_SCAN_URL = "https://scanner.tradingview.com/global/scan"
_TV_SCAN_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://www.tradingview.com",
}


_TV_QUOTE_FIELDS = ["lp", "ch", "chp", "high", "low"]


def _tv_num(v, nd=4):
    try:
        return round(float(v), nd) if v is not None else None
    except (TypeError, ValueError):
        return None


def _tv_quote_from_values(vals: list) -> dict | None:
    """[lp, ch, chp, high, low] → quote dict, or None when no usable price."""
    price = _tv_num(vals[0]) if len(vals) >= 1 else None
    if price is None or price <= 0:
        return None
    change = _tv_num(vals[1]) if len(vals) >= 2 else None
    change_pct = _tv_num(vals[2], 2) if len(vals) >= 3 else None
    if change_pct is None and change is not None and price != change:
        # some /symbol responses omit chp — derive it from ch and prev close
        change_pct = round(change / (price - change) * 100, 2)
    return {
        "price":      price,
        "change":     change,
        "change_pct": change_pct,
        "day_high":   _tv_num(vals[3]) if len(vals) >= 4 else None,
        "day_low":    _tv_num(vals[4]) if len(vals) >= 5 else None,
    }


def _tv_single_quote(tv_symbol: str) -> dict | None:
    """Per-symbol GET /symbol quote — the exact request shape daily_analysis and
    the GitHub Actions levels job already use successfully from cloud IPs.
    Fallback path when the batch POST endpoint is unavailable."""
    from urllib.parse import quote as _q
    url = (f"https://scanner.tradingview.com/symbol"
           f"?symbol={_q(tv_symbol)}&fields={','.join(_TV_QUOTE_FIELDS + ['close'])}&no_404=1")
    try:
        with httpx.Client(timeout=8) as client:
            r = client.get(url, headers=_TV_SCAN_HEADERS)
            if r.status_code != 200:
                return None
            d = r.json() or {}
    except Exception:
        return None
    vals = [d.get("lp") if d.get("lp") is not None else d.get("close"),
            d.get("ch"), d.get("chp"), d.get("high"), d.get("low")]
    return _tv_quote_from_values(vals)


def tv_batch_quotes(candidates: dict) -> dict:
    """Live quotes for many instruments in ONE TradingView scanner POST, with a
    per-symbol GET fallback (the repo's proven-from-Railway request shape) if
    the batch endpoint itself is unreachable.

    candidates: {caller_key: [TV symbol candidates in priority order]}
                e.g. {"GC=F": ["TVC:GOLD", "OANDA:XAUUSD"]}.
    Returns {caller_key: {price, change, change_pct, day_high, day_low}} for
    every key the scanner resolved (first candidate with data wins); keys the
    scanner couldn't serve are simply absent. Never raises.
    """
    tickers: list = []
    for cands in candidates.values():
        for tv in cands or []:
            if tv and tv not in tickers:
                tickers.append(tv)
    if not tickers:
        return {}
    payload = {
        "symbols": {"tickers": tickers, "query": {"types": []}},
        "columns": _TV_QUOTE_FIELDS,
    }
    out: dict = {}
    batch_ok = False
    try:
        with httpx.Client(timeout=10) as client:
            r = client.post(_TV_SCAN_URL, json=payload, headers=_TV_SCAN_HEADERS)
            r.raise_for_status()
            rows = (r.json() or {}).get("data") or []
        batch_ok = True
        by_tv = {row.get("s"): row.get("d") for row in rows
                 if isinstance(row, dict) and row.get("s") and isinstance(row.get("d"), list)}
        for key, cands in candidates.items():
            for tv in cands or []:
                q = _tv_quote_from_values(by_tv.get(tv) or [])
                if q:
                    out[key] = q
                    break
    except Exception as e:
        print(f"[mktdata] TV scanner batch failed: {e}")
    # Per-symbol GET (the proven-from-Railway shape) for every key the batch
    # did NOT resolve — the batch POST can return 200 yet resolve nothing for
    # index/futures symbols, so gating this on batch failure alone left the
    # overview empty. Bounded: ≤2 candidates per unresolved instrument.
    missing = [k for k in candidates if k not in out]
    for key in missing:
        for tv in (candidates.get(key) or [])[:2]:
            q = _tv_single_quote(tv)
            if q:
                out[key] = q
                break
    _health("tv_scanner_batch", bool(out), "price",
            "" if out else "no quotes resolved")
    return out


_STOOQ_CACHE: dict = {}   # stooq_symbol -> (epoch_fetched, df) — shared across consumers
_STOOQ_TTL = 1800         # 30 min: daily bars don't change intraday


def _stooq_daily(stooq_symbol: str):
    """Daily OHLC CSV from Stooq → yfinance-shaped DataFrame (or empty).

    Stooq is the shared daily source for regime + MTF + macro + daily-levels +
    the swing 70-stock scan. The market-open burst (all consumers at once) got
    everything throttled together, leaving regime UNKNOWN / MTF all-zero. The fix
    is the 30-min in-memory cache below: consumers SHARE one fetch instead of each
    hammering Stooq, which is what actually prevents the burst rate-limiting.

    NOTE: single fetch, NO blocking sleep/retry — several callers run on the async
    event loop, and a blocking time.sleep() there freezes it and times out every
    concurrent webhook. The cache (not retries) is the real defense; a transient
    miss just isn't cached and self-corrects on the next call. Short timeout so a
    slow Stooq can't stall the loop for long."""
    import pandas as pd
    import time as _time
    _c = _STOOQ_CACHE.get(stooq_symbol)
    if _c and (_time.time() - _c[0]) < _STOOQ_TTL and len(_c[1]):
        return _c[1]
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
    with httpx.Client(timeout=8) as client:
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
    result = df[keep]
    if len(result):
        _STOOQ_CACHE[stooq_symbol] = (_time.time(), result)   # share across consumers
    return result


def _health(source: str, ok: bool, category: str = "", detail: str = "") -> None:
    """Report a fetch outcome to the data-flow health registry (never raises)."""
    try:
        import data_health
        data_health.record(source, ok, category, detail)
    except Exception:
        pass


def _stooq_symbol_for(ticker: str) -> str | None:
    """Resolve a ticker to a Stooq symbol. Known aliases (indices/futures/ETFs)
    come from STOOQ_SYMBOLS; any other plain US equity uses Stooq's '<ticker>.us'
    convention (lowercased, '.' → '-', e.g. BRK.B → brk-b.us). Returns None for
    symbols Stooq can't serve this way (^indices, =futures not in the map)."""
    mapped = STOOQ_SYMBOLS.get(ticker)
    if mapped:
        return mapped
    t = (ticker or "").strip().lower()
    if not t or t.startswith("^") or "=" in t or ":" in t:
        return None
    if t.endswith(".us"):
        return t
    return f"{t.replace('.', '-')}.us"


def fetch_daily(ticker: str, period: str = "1y"):
    """Daily OHLC — Stooq primary (free, cloud-reliable). Empty DataFrame if unavailable.
    Resolves arbitrary US equities (swing universe) via the '<ticker>.us' convention,
    not just the hardcoded alias map — without this, yfinance's removal left every
    individual stock with no daily bars (swing screener + tracker went dark)."""
    import pandas as pd
    # IBKR gateway first when live — same feed the account trades on, no basis
    # premium on gold. Inert (returns []) unless IBKR_GATEWAY_URL is configured,
    # so Stooq stays the effective default until a gateway is pointed at us.
    try:
        import ibkr_data
        if ibkr_data.available():
            df = ibkr_data.fetch_history(ticker, period="1y", bar="1d")
            if len(df):
                _health("ibkr_daily", True, "price")
                return df
    except Exception as e:
        print(f"[mktdata] IBKR daily {ticker} failed: {e}")
    sym = _stooq_symbol_for(ticker)
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
    # TradingView daily bars — last resort when Stooq is rate-limited from the
    # cloud IP. tvdatafeed anonymous mode; same lib daily_analysis levels use.
    try:
        df = _tv_daily(ticker)
        if df is not None and len(df):
            _health("tv_daily", True, "price")
            return df
        _health("tv_daily", False, "price", f"empty for {ticker}")
    except Exception as e:
        print(f"[mktdata] TV daily {ticker} failed: {e}")
        _health("tv_daily", False, "price", str(e))
    return pd.DataFrame()


_TV_DAILY_MAP = {
    "GC=F": ("GOLD", "TVC"), "XAUUSD": ("GOLD", "TVC"),
    "SPY": ("SPY", "AMEX"), "QQQ": ("QQQ", "NASDAQ"),
    "^GSPC": ("SPX", "SP"), "^IXIC": ("IXIC", "NASDAQ"), "^DJI": ("DJI", "TVC"),
    "^RUT": ("RUT", "TVC"), "^VIX": ("VIX", "TVC"),
    "CL=F": ("USOIL", "TVC"), "SI=F": ("SILVER", "TVC"), "NG=F": ("NG1!", "NYMEX"),
    "BTC-USD": ("BTCUSD", "BITSTAMP"), "ETH-USD": ("ETHUSD", "BITSTAMP"),
    "^TNX": ("US10Y", "TVC"), "^IRX": ("US02Y", "TVC"),
}

_tv_daily_cache: dict = {}

def _tv_daily(ticker: str):
    """Daily OHLC via tvdatafeed (anonymous). 30-min cache per ticker."""
    import time
    import pandas as pd
    hit = _tv_daily_cache.get(ticker)
    if hit and time.time() - hit[0] < 1800:
        return hit[1]
    try:
        from tvDatafeed import TvDatafeed, Interval
    except Exception:
        return None
    sym, exch = _TV_DAILY_MAP.get(ticker, (ticker.upper().replace("-", "").replace(".", ""), "NASDAQ"))
    tv = TvDatafeed()
    df = None
    for ex in ([exch] + (["NYSE", "AMEX"] if exch == "NASDAQ" else [])):
        try:
            raw = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=260)
            if raw is not None and len(raw) >= 30:
                df = raw.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
                df = df[["Open", "High", "Low", "Close"] + (["Volume"] if "Volume" in df.columns else [])]
                break
        except Exception:
            continue
    if df is not None and len(df):
        _tv_daily_cache[ticker] = (time.time(), df)
        return df
    return None


_tv_4h_cache: dict = {}

def tv_4h(ticker: str):
    """4-hour OHLC via tvdatafeed (anonymous) — free fallback for the swing 4H
    entry trigger now that Alpha Vantage intraday is a premium-only endpoint.
    60-min cache per ticker; NYSE/AMEX retry for NASDAQ-guessed equities."""
    import time
    hit = _tv_4h_cache.get(ticker)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    try:
        from tvDatafeed import TvDatafeed, Interval
    except Exception:
        return None
    sym, exch = _TV_DAILY_MAP.get(ticker, (ticker.upper().replace("-", "").replace(".", ""), "NASDAQ"))
    tv = TvDatafeed()
    for ex in ([exch] + (["NYSE", "AMEX"] if exch == "NASDAQ" else [])):
        try:
            raw = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_4_hour, n_bars=80)
            if raw is not None and len(raw) >= 25:
                df = raw.rename(columns={"open": "Open", "high": "High",
                                         "low": "Low", "close": "Close", "volume": "Volume"})
                df = df[["Open", "High", "Low", "Close"] + (["Volume"] if "Volume" in df.columns else [])]
                _tv_4h_cache[ticker] = (time.time(), df)
                return df
        except Exception:
            continue
    return None
