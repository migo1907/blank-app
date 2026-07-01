"""
Interactive Brokers (IBKR) data provider — Client Portal Web API adapter.

This is the SERVER-SIDE always-on path for IBKR data. Unlike the phone/chat
connector (tied to an interactive session that IBKR logs out daily), a Client
Portal Gateway can run headless with auto-restart, re-authenticating itself and
feeding the backend 24/7 across all sections (intraday, swing, options).

Enable by pointing the backend at a reachable gateway:
    IBKR_GATEWAY_URL = https://your-gateway-host:5000   (no trailing /v1/api)

Falls back gracefully — every function returns None/empty when the gateway is
absent, unauthenticated, or unreachable, so callers transparently drop to the
existing Stooq / AlphaVantage / CBOE chain. IBKR is PREFERRED when live, since
it is the same feed the account trades on (no basis premium, real Greeks).

Design mirrors polygon_data.py / tradier_data.py: thin REST, short timeouts,
in-memory caches so concurrent event-loop callers share one fetch and never
block. No blocking sleeps (would freeze the async loop → webhook timeouts).
"""
from __future__ import annotations
import os, time, httpx

_BASE = ""
_VERIFY = True          # gateways often use a self-signed cert on localhost
_AUTH_OK = False
_AUTH_TS = 0.0
_AUTH_TTL = 60.0        # re-check auth status at most once a minute

# conid resolution and snapshot/history caches (shared across consumers)
_CONID_CACHE: dict[str, int] = {}
_SNAP_CACHE: dict[str, tuple[float, float]] = {}
_HIST_CACHE: dict[str, tuple[float, object]] = {}
_SNAP_TTL = 5.0         # live price: fresh but shared within a burst
_HIST_TTL = 900.0       # bars: 15-min cache (regime/MTF/swing share one pull)


def _base() -> str:
    """Gateway base incl. /v1/api, or '' when unconfigured. Reads env lazily
    so a mid-run Railway variable change takes effect without a code deploy."""
    global _BASE, _VERIFY
    raw = os.environ.get("IBKR_GATEWAY_URL", "").strip()
    if not raw:
        _BASE = ""
        return ""
    raw = raw.rstrip("/")
    if raw.endswith("/v1/api"):
        base = raw
    else:
        base = raw + "/v1/api"
    _BASE = base
    # allow disabling TLS verify for a self-signed localhost gateway only
    _VERIFY = os.environ.get("IBKR_GATEWAY_INSECURE", "false").lower() not in ("1", "true", "yes")
    return base


def _get(path: str, params: dict | None = None, timeout: float = 8.0):
    base = _base()
    if not base:
        return None
    try:
        with httpx.Client(timeout=timeout, verify=_VERIFY) as client:
            r = client.get(f"{base}{path}", params=params or {})
        if r.status_code == 200:
            return r.json()
        print(f"[ibkr] GET {path} → HTTP {r.status_code}")
    except Exception as e:
        print(f"[ibkr] GET {path} failed: {e}")
    return None


def _post(path: str, json_body: dict | None = None, timeout: float = 8.0):
    base = _base()
    if not base:
        return None
    try:
        with httpx.Client(timeout=timeout, verify=_VERIFY) as client:
            r = client.post(f"{base}{path}", json=json_body or {})
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[ibkr] POST {path} failed: {e}")
    return None


def authenticated() -> bool:
    """True when the gateway reports an authenticated, non-competing session.
    Cached briefly so per-signal calls don't spam /auth/status. Attempts a
    /reauthenticate when connected-but-not-authenticated (the daily-logout case)."""
    global _AUTH_OK, _AUTH_TS
    if not _base():
        return False
    now = time.time()
    if (now - _AUTH_TS) < _AUTH_TTL:
        return _AUTH_OK
    _AUTH_TS = now
    st = _get("/iserver/auth/status", timeout=6.0)
    if isinstance(st, dict):
        ok = bool(st.get("authenticated"))
        if not ok and st.get("connected"):
            # session dropped (IBKR forces a daily logout) → nudge a reauth
            _post("/iserver/reauthenticate", timeout=6.0)
        _AUTH_OK = ok
    else:
        _AUTH_OK = False
    return _AUTH_OK


def available() -> bool:
    """Cheap gate for callers: gateway configured AND authenticated."""
    return authenticated()


def _conid(symbol: str, sec_type: str = "STK") -> int | None:
    """Resolve a ticker to an IBKR contract id (cached for the process life).
    Picks the primary US listing for equities; first match otherwise."""
    key = f"{sec_type}:{symbol.upper()}"
    if key in _CONID_CACHE:
        return _CONID_CACHE[key]
    res = _get("/iserver/secdef/search", {"symbol": symbol, "secType": sec_type})
    if isinstance(res, list) and res:
        conid = None
        for row in res:
            cid = row.get("conid")
            if cid:
                conid = int(cid)
                break
        if conid is not None:
            _CONID_CACHE[key] = conid
            return conid
    return None


def get_spot(symbol: str, sec_type: str = "STK") -> float | None:
    """Live last price via marketdata snapshot (field 31). None if unavailable.
    IBKR snapshots need one warm-up call to prime the subscription; we prime
    then read, and cache the result for a few seconds to share across callers."""
    if not authenticated():
        return None
    c = _SNAP_CACHE.get(symbol.upper())
    if c and (time.time() - c[0]) < _SNAP_TTL:
        return c[1]
    conid = _conid(symbol, sec_type)
    if conid is None:
        return None
    params = {"conids": str(conid), "fields": "31"}
    _get("/iserver/marketdata/snapshot", params, timeout=6.0)  # prime
    data = _get("/iserver/marketdata/snapshot", params, timeout=6.0)
    if isinstance(data, list) and data:
        raw = data[0].get("31")
        if raw is not None:
            try:
                # IBKR prefixes some fields (e.g. 'C123.4' halted) — strip non-numeric
                px = float(str(raw).lstrip("CHB"))
                _SNAP_CACHE[symbol.upper()] = (time.time(), px)
                return px
            except (ValueError, TypeError):
                return None
    return None


def fetch_history(symbol: str, period: str = "1y", bar: str = "1d",
                  sec_type: str = "STK"):
    """OHLCV history as a yfinance-shaped DataFrame (Open/High/Low/Close/Volume,
    UTC DatetimeIndex) — the same shape Stooq/AlphaVantage return, so callers need
    no changes. Empty DataFrame when the gateway is down or the symbol is unknown.

    period: 1d,1w,1m,6m,1y ...   bar: 1min,5min,15min,30min,1h,1d (IBKR notation).
    Cached 15 min so regime + MTF + swing share a single pull per symbol/bar."""
    import pandas as pd
    if not authenticated():
        return pd.DataFrame()
    ck = f"{symbol.upper()}|{period}|{bar}"
    c = _HIST_CACHE.get(ck)
    if c and (time.time() - c[0]) < _HIST_TTL:
        return c[1]
    conid = _conid(symbol, sec_type)
    if conid is None:
        return pd.DataFrame()
    data = _get("/iserver/marketdata/history",
                {"conid": str(conid), "period": period, "bar": bar, "outsideRth": "true"},
                timeout=12.0)
    rows = (data or {}).get("data") if isinstance(data, dict) else None
    if not rows:
        return pd.DataFrame()
    recs = []
    for b in rows:
        try:
            recs.append({
                "Date": pd.to_datetime(int(b["t"]), unit="ms", utc=True),
                "Open": float(b["o"]), "High": float(b["h"]),
                "Low": float(b["l"]), "Close": float(b["c"]),
                "Volume": float(b.get("v", 0) or 0),
            })
        except (KeyError, ValueError, TypeError):
            continue
    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame(recs).set_index("Date").sort_index()
    _HIST_CACHE[ck] = (time.time(), df)
    return df


def status() -> dict:
    """Diagnostic snapshot for /health and the /owner/test endpoint."""
    if not _base():
        return {"configured": False, "authenticated": False}
    return {
        "configured": True,
        "authenticated": authenticated(),
        "conids_cached": len(_CONID_CACHE),
    }
