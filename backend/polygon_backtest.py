"""
Polygon.io options backtest — free tier compatible.

Uses:
  /v3/reference/options/contracts  — list SPXW contracts
  /v2/aggs/ticker/{ticker}/range/1/day/{from}/{to} — OHLC bars

Simulates the options paper trade strategy:
  - Entry: buy OTM call/put near 0.25 delta at open
  - TP:    +100% of entry premium
  - SL:    -50%  of entry premium
  - Hard exit: end of DTE day

Run:
  python polygon_backtest.py [--days 30] [--direction call|put|both]
"""
from __future__ import annotations
import os, sys, httpx, json, argparse
from datetime import date, timedelta, datetime

_KEY  = os.environ.get("POLYGON_API_KEY", "")
_BASE = "https://api.polygon.io"


def _get(path: str, params: dict = {}) -> dict | None:
    try:
        r = httpx.get(f"{_BASE}{path}", params={"apiKey": _KEY, **params}, timeout=15)
        if r.status_code == 200:
            return r.json()
        print(f"  [polygon] {path} → HTTP {r.status_code}")
    except Exception as e:
        print(f"  [polygon] {path} failed: {e}")
    return None


def list_contracts(underlying: str, expiry: str, contract_type: str = "call") -> list[dict]:
    """List all SPXW options expiring on a given date."""
    data = _get("/v3/reference/options/contracts", {
        "underlying_ticker": underlying,
        "expiration_date":   expiry,
        "contract_type":     contract_type,
        "expired":           "true",
        "limit":             250,
    })
    if data and data.get("results"):
        return data["results"]
    return []


def get_bars(ticker: str, from_date: str, to_date: str) -> list[dict]:
    """Daily OHLC bars for a contract."""
    data = _get(f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}", {
        "adjusted": "false", "limit": 5, "sort": "asc",
    })
    if data and data.get("results"):
        return data["results"]
    return []


def get_spx_bars(from_date: str, to_date: str) -> dict[str, float]:
    """SPX daily closing prices keyed by YYYY-MM-DD."""
    data = _get(f"/v2/aggs/ticker/I:SPX/range/1/day/{from_date}/{to_date}", {
        "adjusted": "false", "limit": 365, "sort": "asc",
    })
    if not data or not data.get("results"):
        return {}
    out = {}
    for r in data["results"]:
        dt = datetime.fromtimestamp(r["t"] / 1000).strftime("%Y-%m-%d")
        out[dt] = r["c"]
    return out


def nearest_otm_strike(spot: float, strikes: list[float], direction: str, pct: float = 0.005) -> float | None:
    """Find strike ~0.5% OTM (rough delta-0.25 proxy without live Greeks)."""
    target = spot * (1 + pct) if direction == "call" else spot * (1 - pct)
    if not strikes:
        return None
    return min(strikes, key=lambda s: abs(s - target))


def run_backtest(days: int = 30, direction: str = "both") -> dict:
    if not _KEY:
        print("ERROR: POLYGON_API_KEY not set")
        sys.exit(1)

    today     = date.today()
    from_date = (today - timedelta(days=days + 10)).isoformat()
    to_date   = today.isoformat()

    print(f"\nFetching SPX closes {from_date} → {to_date} …")
    spx_closes = get_spx_bars(from_date, to_date)
    trading_days = sorted(spx_closes.keys())
    # Only use days within requested range
    cutoff = (today - timedelta(days=days)).isoformat()
    trading_days = [d for d in trading_days if d >= cutoff]

    print(f"  {len(trading_days)} trading days found")

    directions = ["call", "put"] if direction == "both" else [direction]
    trades: list[dict] = []

    for expiry in trading_days:
        spot = spx_closes.get(expiry)
        if not spot:
            continue

        for ctype in directions:
            print(f"  {expiry} {ctype.upper()} — spot={spot:.0f}", end="")

            contracts = list_contracts("SPXW", expiry, ctype)
            if not contracts:
                print(" → no contracts")
                continue

            strikes = [c["strike_price"] for c in contracts if c.get("strike_price")]
            target_strike = nearest_otm_strike(spot, strikes, ctype)
            if not target_strike:
                print(" → no strike")
                continue

            # Find matching contract ticker
            contract = next(
                (c for c in contracts if c.get("strike_price") == target_strike),
                None
            )
            if not contract:
                print(" → no match")
                continue

            ticker = contract.get("ticker")
            if not ticker:
                print(" → no ticker")
                continue

            # Get bars for this contract on the expiry day
            bars = get_bars(ticker, expiry, expiry)
            if not bars:
                print(f" → no bars for {ticker}")
                continue

            b = bars[0]
            entry   = b.get("o") or b.get("c")  # open price = entry
            high    = b.get("h", entry)
            low     = b.get("l", entry)
            close   = b.get("c", entry)

            if not entry or entry <= 0:
                print(f" → bad entry price")
                continue

            tp_price = entry * 2.0    # +100% TP
            sl_price = entry * 0.5    # -50% SL

            # Simulate intraday: did price hit TP or SL?
            # Using high = potential TP hit, low = potential SL hit
            if ctype == "call":
                hit_tp = high >= tp_price
                hit_sl = low  <= sl_price
            else:  # put: inverse price movement
                hit_tp = high >= tp_price
                hit_sl = low  <= sl_price

            # Pessimistic: SL before TP if same bar (low hits before high)
            if hit_tp and hit_sl:
                result = "SL"
                exit_price = sl_price
            elif hit_tp:
                result = "TP"
                exit_price = tp_price
            elif hit_sl:
                result = "SL"
                exit_price = sl_price
            else:
                # Hard exit at close
                result = "EXPIRED"
                exit_price = close

            pnl_pct = (exit_price - entry) / entry * 100

            trades.append({
                "date":    expiry,
                "type":    ctype,
                "strike":  target_strike,
                "ticker":  ticker,
                "entry":   round(entry, 2),
                "exit":    round(exit_price, 2),
                "pnl_pct": round(pnl_pct, 1),
                "result":  result,
                "spot":    round(spot, 0),
            })
            print(f" strike={target_strike:.0f} entry={entry:.2f} → {result} ({pnl_pct:+.1f}%)")

    if not trades:
        print("\nNo trades to analyze.")
        return {}

    wins     = [t for t in trades if t["result"] == "TP"]
    losses   = [t for t in trades if t["result"] == "SL"]
    expired  = [t for t in trades if t["result"] == "EXPIRED"]
    total    = len(trades)
    win_rate = len(wins) / total if total else 0
    avg_pnl  = sum(t["pnl_pct"] for t in trades) / total if total else 0

    summary = {
        "days_backtested": days,
        "direction":       direction,
        "total_trades":    total,
        "wins":            len(wins),
        "losses":          len(losses),
        "expired":         len(expired),
        "win_rate_pct":    round(win_rate * 100, 1),
        "avg_pnl_pct":     round(avg_pnl, 1),
        "trades":          trades,
    }

    print(f"\n{'='*50}")
    print(f"BACKTEST SUMMARY — last {days} trading days, direction={direction}")
    print(f"  Total trades:  {total}")
    print(f"  Wins (TP):     {len(wins)}  ({win_rate*100:.1f}%)")
    print(f"  Losses (SL):   {len(losses)}")
    print(f"  Expired:       {len(expired)}")
    print(f"  Avg P&L:       {avg_pnl:+.1f}%")
    print(f"{'='*50}\n")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",      type=int, default=30,   help="Trading days to backtest")
    parser.add_argument("--direction", default="both",         help="call | put | both")
    parser.add_argument("--output",    default="",             help="Save JSON results to file")
    args = parser.parse_args()

    result = run_backtest(args.days, args.direction)

    if args.output and result:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Results saved to {args.output}")
