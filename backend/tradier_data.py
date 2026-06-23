"""
Tradier market-data provider for the options layer.

Drop-in replacement for the yfinance ^SPX option-chain calls in
options_engine.py. Returns pandas DataFrames with the SAME column names
yfinance produces (strike, impliedVolatility, bid, ask, lastPrice) so the
downstream strike-selection / management code is untouched.

Free sandbox: sign up at developer.tradier.com → grab the access token →
set TRADIER_TOKEN in Railway. Sandbox quotes are ~15-min delayed (same as
yfinance) but come from a stable REST contract instead of a scraper, which
matters on Railway where yfinance silently breaks when Yahoo changes its page.

Env (set in Railway, never committed):
  • TRADIER_TOKEN — sandbox (or live) access token. If unset, available()
    returns False and options_engine falls back to yfinance.
  • TRADIER_BASE  — defaults to the sandbox host; override for live.

No-op safe: every function degrades to None/empty on any error so the caller
can fall back to yfinance.
"""

from __future__ import annotations

import os

import httpx

TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN", "")
TRADIER_BASE  = os.environ.get("TRADIER_BASE", "https://sandbox.tradier.com/v1")

# Tradier indexes the S&P 500 cash index as "SPX"; chains under it include the
# daily-expiry SPXW weeklys the options engine trades.
SPX_SYMBOL = os.environ.get("TRADIER_SPX_SYMBOL", "SPX")


def available() -> bool:
    """True only when a token is configured — gates the whole provider."""
    return bool(TRADIER_TOKEN)


def _headers() -> dict:
    return {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}


def _get(path: str, params: dict) -> dict | None:
    try:
        with httpx.Client(timeout=12) as client:
            r = client.get(f"{TRADIER_BASE}{path}", params=params, headers=_headers())
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"[tradier] GET {path} failed: {e}")
        return None


def get_spot(symbol: str = SPX_SYMBOL) -> float | None:
    data = _get("/markets/quotes", {"symbols": symbol})
    try:
        q = data["quotes"]["quote"]
        if isinstance(q, list):
            q = q[0]
        # Index quotes sometimes carry price only in 'last'; fall back to close.
        return float(q.get("last") or q.get("close") or 0) or None
    except Exception:
        return None


def get_expirations(symbol: str = SPX_SYMBOL) -> list[str]:
    """Sorted list of expiry dates as 'YYYY-MM-DD' strings."""
    data = _get("/markets/options/expirations",
                {"symbol": symbol, "includeAllRoots": "true"})
    try:
        dates = data["expirations"]["date"]
        if isinstance(dates, str):
            dates = [dates]
        return sorted(dates)
    except Exception:
        return []


class _Chain:
    """Mirrors yfinance's option_chain() result: .calls / .puts DataFrames."""
    __slots__ = ("calls", "puts")

    def __init__(self, calls, puts):
        self.calls = calls
        self.puts = puts


def get_chain(symbol: str, expiry: str):
    """
    Return a _Chain whose .calls / .puts are pandas DataFrames with columns
    strike, impliedVolatility, bid, ask, lastPrice — matching yfinance so the
    options engine needs no per-row changes.
    """
    import pandas as pd

    data = _get("/markets/options/chains",
                {"symbol": symbol, "expiration": expiry, "greeks": "true"})
    options = []
    try:
        options = data["options"]["option"] or []
        if isinstance(options, dict):
            options = [options]
    except Exception:
        options = []

    calls, puts = [], []
    for o in options:
        greeks = o.get("greeks") or {}
        row = {
            "strike":            float(o.get("strike") or 0),
            "impliedVolatility": float(greeks.get("mid_iv") or 0),
            "bid":               float(o.get("bid") or 0),
            "ask":               float(o.get("ask") or 0),
            "lastPrice":         float(o.get("last") or 0),
        }
        (calls if o.get("option_type") == "call" else puts).append(row)

    cols = ["strike", "impliedVolatility", "bid", "ask", "lastPrice"]
    calls_df = pd.DataFrame(calls, columns=cols).sort_values("strike").reset_index(drop=True)
    puts_df  = pd.DataFrame(puts,  columns=cols).sort_values("strike").reset_index(drop=True)
    return _Chain(calls_df, puts_df)
