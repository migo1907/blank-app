"""
SPX 0DTE options backtest — IBKR data source.

IBKR does not expose expired option contracts, so past 0DTE premiums cannot be
replayed from real option prints. Instead this uses real IBKR underlying data
and reprices the option path with Black-Scholes:

  - SPX 15-min RTH bars   (backtest_data/spx_15min_ibkr.json, contract 416904 CBOE)
  - VIX1D daily open/close (backtest_data/vix1d_daily_ibkr.json) as the 0DTE IV
    input, linearly interpolated open->close across each session

Strategy simulated (same rules as options_engine paper trades / polygon_backtest):
  - Entry:     09:30 ET at the bar open, strike at ~0.25 delta OTM (BS picker,
               strikes rounded to the 5-point SPXW grid)
  - TP:        +100% of entry premium
  - SL:        -50%  of entry premium (checked before TP on the same bar —
               pessimistic, matching swing_tracker convention)
  - Hard exit: 15:30 ET at the bar open (production 0DTE hard-exit time)

Approximations (disclosed, not hidden): premiums are model prices, not traded
prices — no bid/ask spread, no vol smile (ATM VIX1D vol applied at the 0.25d
strike, which understates OTM premium slightly), and the intraday IV path is a
straight line between the day's VIX1D open and close.

Run:
  python ibkr_backtest.py [--direction call|put|both] [--output results.json]
"""
from __future__ import annotations
import os, json, math, argparse
from datetime import datetime

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_data")

RISK_FREE   = 0.04
D1_TARGET   = 0.6744897501960817   # inverse normal CDF of 0.75 -> |delta| = 0.25
STRIKE_STEP = 5.0                  # SPXW near-ATM strike grid
SESSION_MIN = 390.0                # 09:30-16:00 ET
HARD_EXIT_MIN = 360.0              # 15:30 ET, minutes after open


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price(spot: float, strike: float, tau_years: float, iv: float,
             direction: str, r: float = RISK_FREE) -> float:
    """Black-Scholes European option price (q=0). Handles tau ~ 0."""
    if tau_years <= 1e-9 or iv <= 0:
        intrinsic = spot - strike if direction == "call" else strike - spot
        return max(intrinsic, 0.0)
    sq = iv * math.sqrt(tau_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * tau_years) / sq
    d2 = d1 - sq
    if direction == "call":
        return spot * _norm_cdf(d1) - strike * math.exp(-r * tau_years) * _norm_cdf(d2)
    return strike * math.exp(-r * tau_years) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def pick_strike(spot: float, tau_years: float, iv: float, direction: str) -> float:
    """Strike whose BS delta is ~ +/-0.25, rounded to the SPXW 5-point grid."""
    d1 = -D1_TARGET if direction == "call" else D1_TARGET
    k = spot * math.exp((RISK_FREE + 0.5 * iv * iv) * tau_years - d1 * iv * math.sqrt(tau_years))
    return round(k / STRIKE_STEP) * STRIKE_STEP


def _load(name: str) -> dict:
    with open(os.path.join(_DIR, name)) as f:
        return json.load(f)


def _sessions(bars: dict) -> dict[str, list[dict]]:
    """Group 15-min bars by session date; minutes measured from the 09:30 ET open."""
    out: dict[str, list[dict]] = {}
    for i, t in enumerate(bars["time"]):
        dt = datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ")
        day = t[:10]
        open_utc = dt.replace(hour=13, minute=30)
        minute = (dt - open_utc).total_seconds() / 60.0
        out.setdefault(day, []).append({
            "minute": minute,
            "o": bars["open"][i], "h": bars["high"][i],
            "l": bars["low"][i],  "c": bars["close"][i],
        })
    return out


def run_backtest(direction: str = "both") -> dict:
    spx  = _sessions(_load("spx_15min_ibkr.json"))
    vix  = _load("vix1d_daily_ibkr.json")
    vix_by_day = {t[:10]: (vix["open"][i], vix["close"][i]) for i, t in enumerate(vix["time"])}

    directions = ["call", "put"] if direction == "both" else [direction]
    trades: list[dict] = []

    for day in sorted(vix_by_day):
        bars = spx.get(day)
        if not bars or len(bars) < 26 or bars[0]["minute"] != 0.0:
            print(f"  {day} — incomplete session, skipped")
            continue
        iv_open, iv_close = (v / 100.0 for v in vix_by_day[day])

        def iv_at(minute: float) -> float:
            frac = min(max(minute / SESSION_MIN, 0.0), 1.0)
            return iv_open + (iv_close - iv_open) * frac

        spot_entry = bars[0]["o"]
        tau_entry  = SESSION_MIN / (60.0 * 24.0 * 365.0)

        for ctype in directions:
            strike = pick_strike(spot_entry, tau_entry, iv_open, ctype)
            entry  = bs_price(spot_entry, strike, tau_entry, iv_open, ctype)
            if entry <= 0.05:
                print(f"  {day} {ctype.upper()} — entry premium ~0, skipped")
                continue

            tp_price, sl_price = entry * 2.0, entry * 0.5
            result, exit_price, exit_minute = None, None, None

            for b in bars:
                if b["minute"] >= HARD_EXIT_MIN:
                    result = "EXPIRED"
                    exit_minute = b["minute"]
                    tau = (SESSION_MIN - b["minute"]) / (60.0 * 24.0 * 365.0)
                    exit_price = bs_price(b["o"], strike, tau, iv_at(b["minute"]), ctype)
                    break
                bar_end = b["minute"] + 15.0
                tau = (SESSION_MIN - bar_end) / (60.0 * 24.0 * 365.0)
                iv  = iv_at(bar_end)
                # Underlying low marks the option low for calls, high for puts
                worst = b["l"] if ctype == "call" else b["h"]
                best  = b["h"] if ctype == "call" else b["l"]
                opt_low  = bs_price(worst, strike, tau, iv, ctype)
                opt_high = bs_price(best,  strike, tau, iv, ctype)
                if opt_low <= sl_price:          # pessimistic: SL before TP
                    result, exit_price, exit_minute = "SL", sl_price, bar_end
                    break
                if opt_high >= tp_price:
                    result, exit_price, exit_minute = "TP", tp_price, bar_end
                    break

            if result is None:  # no 15:30 bar found (defensive)
                b = bars[-1]
                result, exit_minute = "EXPIRED", b["minute"] + 15.0
                exit_price = bs_price(b["c"], strike, 0.0, 0.0, ctype)

            pnl_pct = (exit_price - entry) / entry * 100.0
            trades.append({
                "date": day, "type": ctype, "strike": strike,
                "spot": round(spot_entry, 2), "iv_entry": round(iv_open * 100, 2),
                "entry": round(entry, 2), "exit": round(exit_price, 2),
                "exit_minute": exit_minute, "pnl_pct": round(pnl_pct, 1),
                "result": result,
            })
            print(f"  {day} {ctype.upper():4s} spot={spot_entry:7.0f} K={strike:7.0f} "
                  f"iv={iv_open*100:5.1f} entry={entry:6.2f} → {result:7s} ({pnl_pct:+6.1f}%)")

    wins    = [t for t in trades if t["result"] == "TP"]
    losses  = [t for t in trades if t["result"] == "SL"]
    expired = [t for t in trades if t["result"] == "EXPIRED"]
    total   = len(trades)
    win_rate = len(wins) / total if total else 0.0
    avg_pnl  = sum(t["pnl_pct"] for t in trades) / total if total else 0.0

    summary = {
        "data_source":  "IBKR (SPX 15-min bars + VIX1D daily), Black-Scholes repriced",
        "direction":    direction,
        "sessions":     len(vix_by_day),
        "total_trades": total,
        "wins":         len(wins),
        "losses":       len(losses),
        "expired":      len(expired),
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_pnl_pct":  round(avg_pnl, 1),
        "expired_avg_pnl_pct": round(sum(t["pnl_pct"] for t in expired) / len(expired), 1) if expired else None,
        "trades":       trades,
    }

    print(f"\n{'=' * 56}")
    print(f"IBKR SPX 0DTE BACKTEST — {len(vix_by_day)} sessions, direction={direction}")
    print(f"  Total trades:  {total}")
    print(f"  Wins (TP):     {len(wins)}  ({win_rate * 100:.1f}%)")
    print(f"  Losses (SL):   {len(losses)}")
    print(f"  Expired:       {len(expired)}"
          + (f"  (avg {summary['expired_avg_pnl_pct']:+.1f}%)" if expired else ""))
    print(f"  Avg P&L:       {avg_pnl:+.1f}%")
    print(f"{'=' * 56}\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction", default="both", help="call | put | both")
    parser.add_argument("--output",    default="",     help="Save JSON results to file")
    args = parser.parse_args()

    result = run_backtest(args.direction)
    if args.output and result:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Results saved to {args.output}")
