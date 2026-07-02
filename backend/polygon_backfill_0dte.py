"""
Backfill REAL SPX 0DTE option premiums from Polygon and grade the paper
strategy on actual traded prices.

Polygon serves EXPIRED SPXW contracts (IBKR does not), with minute bars up
to 2 years back on the free tier — so the real-price backtest that IBKR
could only collect forward one day at a time can be backfilled here in one
run. Free tier is 5 req/min; ~2 calls per session day, so ~90 days takes
roughly 40 minutes (429s are waited out).

Per session day:
  - SPX open + VIX1D open (one upfront aggs call each for the whole range)
  - strike at ~0.25 delta via the same BS picker as ibkr_backtest
  - contract ticker constructed directly (O:SPXW{yymmdd}{C/P}{strike*1000:08d});
    falls back to the reference endpoint if the aggs come back empty
  - minute bars for the expiry day -> options_backtest.grade_from_series
    (entry 09:30 and 10:00 ET, TP +100%, SL -50%, hard exit 15:30 ET,
    pessimistic same-bar SL, gap-aware fills)

Outputs (backtest_data/):
  - polygon_0dte_grades.json  — every graded trade + summaries (committed)
  - polygon_0dte_bars.json.gz — raw minute series per contract, for
    re-grading with different rules later

Run:  POLYGON_API_KEY=... python polygon_backfill_0dte.py [--days 90]
"""
from __future__ import annotations
import os, json, gzip, argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from polygon_backtest import _get
from ibkr_backtest import pick_strike, SESSION_MIN
from ibkr_backtest_suite import bootstrap_ci
from options_backtest import grade_from_series, hard_exit_utc

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_data")
_ET = ZoneInfo("America/New_York")
COST = 0.22          # half-spread + commission, index points (matches suite)
DEFAULT_IV = 0.14    # fallback when VIX1D is missing for a day


def option_ticker(expiry: str, right: str, strike: float) -> str:
    """O:SPXW260626C07425000 — OCC-style Polygon options ticker."""
    d = expiry.replace("-", "")[2:]
    cp = "C" if right == "call" else "P"
    return f"O:SPXW{d}{cp}{int(round(strike * 1000)):08d}"


def bars_from_aggs(results: list[dict]) -> list[dict]:
    """Polygon aggs (epoch-ms t) -> grade_from_series bar dicts, sorted."""
    bars = [{"time": datetime.fromtimestamp(r["t"] / 1000.0, tz=timezone.utc),
             "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"],
             "v": r.get("v", 0)} for r in results]
    bars.sort(key=lambda b: b["time"])
    return bars


def _daily_map(ticker: str, frm: str, to: str, field: str = "o") -> dict:
    data = _get(f"/v2/aggs/ticker/{ticker}/range/1/day/{frm}/{to}",
                {"limit": 50000, "sort": "asc"})
    out = {}
    for r in (data or {}).get("results", []):
        day = datetime.fromtimestamp(r["t"] / 1000.0, tz=timezone.utc)
        out[day.astimezone(_ET).date().isoformat()] = r[field]
    return out


def fetch_contract_bars(expiry: str, right: str, strike: float) -> tuple[list[dict], str]:
    tk = option_ticker(expiry, right, strike)
    data = _get(f"/v2/aggs/ticker/{tk}/range/1/minute/{expiry}/{expiry}",
                {"limit": 50000, "sort": "asc"})
    if data and data.get("results"):
        return bars_from_aggs(data["results"]), tk
    # constructed ticker missed (odd strike grid?) — ask the reference API
    ref = _get("/v3/reference/options/contracts", {
        "underlying_ticker": "SPXW", "expiration_date": expiry,
        "contract_type": right, "expired": "true", "limit": 50,
        "strike_price.gte": strike - 15, "strike_price.lte": strike + 15})
    best = None
    for c in (ref or {}).get("results", []):
        if best is None or abs(c["strike_price"] - strike) < abs(best["strike_price"] - strike):
            best = c
    if not best:
        return [], tk
    tk = best["ticker"]
    data = _get(f"/v2/aggs/ticker/{tk}/range/1/minute/{expiry}/{expiry}",
                {"limit": 50000, "sort": "asc"})
    return bars_from_aggs((data or {}).get("results", [])), tk


def summarize(trades: list[dict]) -> dict:
    n = len(trades)
    if not n:
        return {"n": 0}
    wins = sum(1 for t in trades if t["result"] == "TP")
    sls = sum(1 for t in trades if t["result"] == "SL")
    return {"n": n, "wins": wins, "losses": sls, "expired": n - wins - sls,
            "win_rate_pct": round(wins / n * 100, 1),
            "avg_pnl_pct": round(sum(t["pnl_pct"] for t in trades) / n, 1),
            **bootstrap_ci([{"pnl_pct": t["pnl_pct"],
                             "result": t["result"]} for t in trades])}


def main(days: int = 90, output: str = "", bars_out: str = "") -> dict:
    if not os.environ.get("POLYGON_API_KEY"):
        print("POLYGON_API_KEY not set — aborting")
        return {}
    today = datetime.now(tz=_ET).date()
    frm = (today - timedelta(days=days + 10)).isoformat()
    to = (today - timedelta(days=1)).isoformat()   # only fully closed sessions

    print(f"SPX opens {frm} -> {to} ...", flush=True)
    spx_open = _daily_map("I:SPX", frm, to, "o")
    vix_open = _daily_map("I:VIX1D", frm, to, "o")
    sessions = sorted(spx_open)[-days:]
    print(f"{len(sessions)} sessions, VIX1D coverage {len(vix_open)}", flush=True)

    tau0 = SESSION_MIN / (60.0 * 24.0 * 365.0)
    grades, raw = [], {}
    for day in sessions:
        spot = spx_open[day]
        iv = vix_open.get(day, DEFAULT_IV * 100) / 100.0
        for right in ("call", "put"):
            strike = pick_strike(spot, tau0, iv, right)
            bars, tk = fetch_contract_bars(day, right, strike)
            if not bars:
                print(f"  {day} {right} K={strike:g} — no bars, skipped", flush=True)
                continue
            raw[tk] = {"expiry": day, "right": right, "strike": strike,
                       "time": [b["time"].strftime("%Y-%m-%dT%H:%M:%SZ") for b in bars],
                       "open": [round(b["o"], 2) for b in bars],
                       "high": [round(b["h"], 2) for b in bars],
                       "low": [round(b["l"], 2) for b in bars],
                       "close": [round(b["c"], 2) for b in bars],
                       "volume": [b["v"] for b in bars]}
            for hh, mm in ((9, 30), (10, 0)):
                ent = datetime.fromisoformat(day).replace(
                    hour=hh, minute=mm, tzinfo=_ET).astimezone(timezone.utc)
                for cost in (0.0, COST):
                    g = grade_from_series(bars, ent, hard_exit_utc(ent, 0),
                                          cost_per_side=cost)
                    # stale/no prints near the entry minute -> not a real fill
                    if not g or g["entry_time"] - ent > timedelta(minutes=10):
                        continue
                    grades.append({
                        "day": day, "right": right, "strike": strike,
                        "spot_open": round(spot, 2), "iv_open": round(iv * 100, 2),
                        "entry_et": f"{hh:02d}:{mm:02d}", "cost": cost,
                        "ticker": tk,
                        **{k: (v.isoformat() if isinstance(v, datetime) else v)
                           for k, v in g.items()}})
            done = [g for g in grades if g["cost"] == 0 and g["entry_et"] == "09:30"]
            if done:
                w = sum(1 for t in done if t["result"] == "TP")
                print(f"  {day} {right:4s} K={strike:g} bars={len(bars)} "
                      f"| running 09:30 free: n={len(done)} win={w / len(done) * 100:.0f}%",
                      flush=True)

    results: dict = {"source": "Polygon expired SPXW minute aggs",
                     "fetched": datetime.now(timezone.utc).isoformat(),
                     "sessions": len(sessions), "first": sessions[0] if sessions else None,
                     "last": sessions[-1] if sessions else None,
                     "cost_per_side": COST, "grades": grades}

    for label, ent, cost in (("0930_frictionless", "09:30", 0.0),
                             ("0930_with_costs", "09:30", COST),
                             ("1000_frictionless", "10:00", 0.0),
                             ("1000_with_costs", "10:00", COST)):
        sub = [g for g in grades if g["entry_et"] == ent and g["cost"] == cost]
        results[label] = summarize(sub)
        # split-half discipline: judge stability, tune nothing on H2
        half = len(sessions) // 2
        h1d = set(sessions[:half])
        results[label]["H1"] = summarize([g for g in sub if g["day"] in h1d])
        results[label]["H2"] = summarize([g for g in sub if g["day"] not in h1d])
        results[f"{label}_by_direction"] = {
            r: summarize([g for g in sub if g["right"] == r])
            for r in ("call", "put")}

    print("\n==== REAL-PRICE 0DTE BACKTEST (Polygon) ====")
    for label in ("0930_frictionless", "0930_with_costs",
                  "1000_frictionless", "1000_with_costs"):
        s = results[label]
        if s.get("n"):
            print(f'{label:20s} n={s["n"]:<4d} win={s["win_rate_pct"]:4.1f}% '
                  f'avg={s["avg_pnl_pct"]:+6.1f}%  '
                  f'H1 {s["H1"].get("avg_pnl_pct")} / H2 {s["H2"].get("avg_pnl_pct")}')

    if output:
        with open(output, "w") as f:
            json.dump(results, f, indent=1)
        print(f"Saved -> {output}")
    if bars_out and raw:
        with gzip.open(bars_out, "wt") as f:
            json.dump(raw, f, separators=(",", ":"))
        print(f"Saved raw bars -> {bars_out} ({os.path.getsize(bars_out)} bytes)")
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--output", default="backtest_data/polygon_0dte_grades.json")
    p.add_argument("--bars-out", default="backtest_data/polygon_0dte_bars.json.gz")
    a = p.parse_args()
    main(a.days, a.output, a.bars_out)
