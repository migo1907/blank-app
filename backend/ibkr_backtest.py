"""
IBKR-fed backtest runner.

Bridges IBKR OHLCV bars → the AI-MLM-26 backtest harness
(polygon_intraday_backtest.py). Two entry points, same math:

  run_bars(symbol, tf, bars)      — feed bars already in {t,o,h,l,c,v} form
                                     (e.g. from the IBKR chat-connector MCP,
                                     saved as JSON, then loaded here)
  run_live(symbol, tf, period)    — pull bars from the server-side IBKR gateway
                                     (ibkr_data.fetch_history) and backtest them,
                                     so the backend can self-evaluate once a
                                     Client Portal Gateway is configured.

Returns the per-timeframe summary + laddered TP/SL exit comparison the harness
produces, so gold-5m-style exit leaks surface the same way regardless of feed.
Kept dependency-light and side-effect-free (no writes) — a pure evaluator.
"""
from __future__ import annotations

# IBKR bar → harness bar notation
_TF_TO_BAR = {"5": "5min", "15": "15min", "30": "30min", "60": "1h", "240": "4h"}


def _normalize(bars):
    """Accept IBKR envelope ({'data':[...]}) or a raw list; coerce each row to
    the harness shape {t,o,h,l,c,v} with numeric fields. Drops malformed rows."""
    rows = bars.get("data") if isinstance(bars, dict) else bars
    out = []
    for b in rows or []:
        try:
            out.append({
                "t": int(b["t"]),
                "o": float(b["o"]), "h": float(b["h"]),
                "l": float(b["l"]), "c": float(b["c"]),
                "v": float(b.get("v", 0) or 0),
            })
        except (KeyError, ValueError, TypeError):
            continue
    out.sort(key=lambda r: r["t"])
    return out


def run_bars(symbol: str, tf: str, bars) -> dict:
    """Backtest a bar series. `tf` is Pine notation ('5','15','30','60','240').
    Returns the base trade summary + the laddered exit A/B (current vs best)."""
    import polygon_intraday_backtest as bt
    rows = _normalize(bars)
    if len(rows) < 60:
        return {"symbol": symbol, "tf": tf, "error": f"too few bars ({len(rows)})"}
    summary = bt.backtest_one(symbol, tf, rows)
    ladders = bt.compare_exits(symbol, tf, rows)
    return {"symbol": symbol, "tf": tf, "n_bars": len(rows),
            "summary": summary, "exit_ladders": ladders}


def run_live(symbol: str, tf: str, period: str = "6m") -> dict:
    """Pull bars from the live IBKR gateway and backtest. No-op-safe: returns an
    error dict (never raises) when the gateway is unconfigured/unauthenticated."""
    import ibkr_data
    if not ibkr_data.available():
        return {"symbol": symbol, "tf": tf, "error": "IBKR gateway not available"}
    bar = _TF_TO_BAR.get(tf, "15min")
    df = ibkr_data.fetch_history(symbol, period=period, bar=bar)
    if not len(df):
        return {"symbol": symbol, "tf": tf, "error": "no bars from gateway"}
    rows = [{"t": int(ts.value // 10**6), "o": r.Open, "h": r.High,
             "l": r.Low, "c": r.Close, "v": getattr(r, "Volume", 0)}
            for ts, r in df.iterrows()]
    return run_bars(symbol, tf, rows)
