"""
Polygon.io options data provider.

Free tier: 15-min delayed data with real Greeks.
Set POLYGON_API_KEY in Railway env to enable.
Falls back gracefully — all functions return None/empty if key absent.
"""
from __future__ import annotations
import os, httpx
from datetime import date, timedelta

_KEY = ""
_BASE = "https://api.polygon.io"


def _key() -> str:
    global _KEY
    if not _KEY:
        _KEY = os.environ.get("POLYGON_API_KEY", "")
    return _KEY


def available() -> bool:
    return bool(_key())


def _get(path: str, params: dict = {}) -> dict | list | None:
    k = _key()
    if not k:
        return None
    try:
        r = httpx.get(f"{_BASE}{path}", params={"apiKey": k, **params}, timeout=12)
        if r.status_code == 200:
            return r.json()
        print(f"[polygon] {path} → HTTP {r.status_code}")
    except Exception as e:
        print(f"[polygon] {path} failed: {e}")
    return None


def get_spot(symbol: str = "I:SPX") -> float | None:
    data = _get(f"/v2/last/trade/{symbol}")
    if data and data.get("results"):
        return data["results"].get("p")
    return None


def get_options_chain(underlying: str = "SPXW", expiration: str | None = None) -> dict | None:
    """Full options chain with real Greeks. Returns {calls:[], puts:[], expiration:str}"""
    if not available():
        return None
    exp = expiration or date.today().isoformat()
    data = _get(f"/v3/snapshot/options/{underlying}", {
        "expiration_date": exp, "limit": 250,
    })
    if not data or not data.get("results"):
        return None

    calls, puts = [], []
    for r in data["results"]:
        d = r.get("details", {})
        g = r.get("greeks", {})
        row = {
            "strike":   d.get("strike_price"),
            "delta":    g.get("delta"),
            "gamma":    g.get("gamma"),
            "theta":    g.get("theta"),
            "vega":     g.get("vega"),
            "impliedVolatility": r.get("implied_volatility"),
            "lastPrice": r.get("day", {}).get("close"),
            "volume":   r.get("day", {}).get("volume"),
            "openInterest": r.get("open_interest"),
            "contract": d.get("ticker"),
            "type":     d.get("contract_type"),
        }
        if d.get("contract_type") == "call":
            calls.append(row)
        else:
            puts.append(row)

    calls.sort(key=lambda x: x.get("strike") or 0)
    puts.sort(key=lambda x: x.get("strike") or 0)
    return {"calls": calls, "puts": puts, "expiration": exp}


def get_option_bars(contract_ticker: str, timespan: str = "day") -> list[dict]:
    """Historical OHLC bars for a specific options contract.
    contract_ticker: e.g. 'O:SPX250620C05500000'
    timespan: 'day' or 'minute'
    """
    today = date.today().isoformat()
    from_date = (date.today() - timedelta(days=365)).isoformat()
    data = _get(f"/v2/aggs/ticker/{contract_ticker}/range/1/{timespan}/{from_date}/{today}", {
        "adjusted": "true", "limit": 50000, "sort": "asc",
    })
    if not data or not data.get("results"):
        return []
    return [
        {"t": r["t"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"], "v": r.get("v")}
        for r in data["results"]
    ]


def get_options_flow(underlying: str = "SPXW", limit: int = 30) -> list[dict]:
    """Top-volume options contracts — unusual activity flow."""
    if not available():
        return []
    today = date.today().isoformat()
    data = _get(f"/v3/snapshot/options/{underlying}", {
        "expiration_date": today, "limit": limit,
    })
    if not data or not data.get("results"):
        # fallback: no date filter
        data = _get(f"/v3/snapshot/options/{underlying}", {"limit": limit})
    if not data or not data.get("results"):
        return []

    rows = []
    for r in data["results"]:
        d   = r.get("details", {})
        g   = r.get("greeks", {})
        vol = r.get("day", {}).get("volume") or 0
        oi  = r.get("open_interest") or 1
        rows.append({
            "contract":     d.get("ticker", ""),
            "type":         d.get("contract_type", ""),
            "strike":       d.get("strike_price"),
            "expiry":       d.get("expiration_date", ""),
            "volume":       vol,
            "oi":           oi,
            "vol_oi_ratio": round(vol / oi, 2) if oi else None,
            "iv":           round(r.get("implied_volatility", 0) * 100, 1) if r.get("implied_volatility") else None,
            "delta":        round(g.get("delta", 0), 3) if g.get("delta") is not None else None,
            "last":         r.get("day", {}).get("close"),
        })
    rows.sort(key=lambda x: x["volume"], reverse=True)
    return rows


def get_put_call_ratio(underlying: str = "SPXW") -> dict | None:
    """Today's put/call volume ratio. Tries Polygon (paid), falls back to yfinance."""
    if available():
        today = date.today().isoformat()
        data = _get(f"/v3/snapshot/options/{underlying}", {"expiration_date": today, "limit": 250})
        if data and data.get("results"):
            call_vol = put_vol = 0
            for r in data["results"]:
                d   = r.get("details", {})
                vol = r.get("day", {}).get("volume") or 0
                if d.get("contract_type") == "call":
                    call_vol += vol
                else:
                    put_vol  += vol
            total = call_vol + put_vol
            if total:
                return {
                    "call_volume":    call_vol,
                    "put_volume":     put_vol,
                    "total_volume":   total,
                    "put_call_ratio": round(put_vol / call_vol, 3) if call_vol else None,
                    "sentiment":      "bullish" if call_vol > put_vol else "bearish",
                    "source":         "polygon",
                }

    # Fallback: yfinance SPX options chain (nearest expiry)
    try:
        import yfinance as yf
        tk  = yf.Ticker("^SPX")
        exp = tk.options[0] if tk.options else None
        if not exp:
            return None
        chain = tk.option_chain(exp)
        call_vol = int(chain.calls["volume"].fillna(0).sum())
        put_vol  = int(chain.puts["volume"].fillna(0).sum())
        total    = call_vol + put_vol
        if not total:
            return None
        return {
            "call_volume":    call_vol,
            "put_volume":     put_vol,
            "total_volume":   total,
            "put_call_ratio": round(put_vol / call_vol, 3) if call_vol else None,
            "sentiment":      "bullish" if call_vol > put_vol else "bearish",
            "source":         "yfinance",
        }
    except Exception as e:
        print(f"[polygon] put_call_ratio yfinance fallback failed: {e}")
    return None
