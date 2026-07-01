"""
SPX 0DTE options backtest suite — IBKR data, Black-Scholes repriced.

Extends ibkr_backtest.py with the realism and robustness tests it lacked:

  1. Longer history (whatever spx_15min_ibkr.json holds — target ~3 months)
  2. Real intraday IV path — VIX1D hourly bars (piecewise-linear knots) instead
     of a straight line between the daily open and close
  3. Transaction costs — half-spread + commission charged on entry AND exit
  4. Entry-time sweep (09:30 / 10:00 / 10:30 / 11:00 / 12:00 / 13:00 ET)
  5. TP/SL grid search (TP +50/+75/+100/+150% x SL -30/-40/-50%)
  6. Scaling exit (half off at +50%, rest rides to TP/SL) — backlog item #7
  7. Naive momentum filter (10:00 entry in the direction of the first 30 min)
  8. Slices by direction / VIX1D regime / weekday
  9. Bootstrap 90% confidence intervals on win rate and avg P&L

Same core simulation as ibkr_backtest.py: 0.25-delta strike on the 5-point
grid, per-bar BS repricing, SL checked before TP on the same bar (pessimistic),
hard exit 15:30 ET. Premiums are model prices (no vol smile) — the cost model
makes results conservative rather than optimistic.

Run:  python ibkr_backtest_suite.py [--output backtest_data/ibkr_suite_results.json]
"""
from __future__ import annotations
import os, json, math, random, argparse
from datetime import datetime

from ibkr_backtest import bs_price, pick_strike, _load, _sessions, SESSION_MIN, HARD_EXIT_MIN

HALF_SPREAD = 0.20   # SPXW 0DTE ~0.25-delta: ~$0.30-0.60 wide -> pay ~half each way
COMMISSION  = 0.02   # ~$2/contract in index points (multiplier 100)
COST        = HALF_SPREAD + COMMISSION
MIN_PREMIUM = 0.30   # skip entries where costs dwarf the premium
YEAR_MIN    = 60.0 * 24.0 * 365.0


# ---------------------------------------------------------------- IV curves
def _iv_curves(vix_hourly: dict, vix_daily: dict) -> tuple[dict, int]:
    """Per-session piecewise-linear IV knots [(minute, iv)] from VIX1D hourly
    bars; falls back to the daily open->close line where hourly is missing."""
    knots: dict[str, list[tuple[float, float]]] = {}
    for i, t in enumerate(vix_hourly["time"]):
        day = t[:10]
        dt = datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ")
        m = (dt.hour - 13) * 60.0 + dt.minute - 30.0
        if not 0 <= m < SESSION_MIN:
            continue
        ks = knots.setdefault(day, [])
        ks.append((m, vix_hourly["open"][i] / 100.0))
        ks.append((min(m + 60.0, SESSION_MIN), vix_hourly["close"][i] / 100.0))

    fallbacks = 0
    for i, t in enumerate(vix_daily["time"]):
        day = t[:10]
        if day not in knots:
            knots[day] = [(0.0, vix_daily["open"][i] / 100.0),
                          (SESSION_MIN, vix_daily["close"][i] / 100.0)]
            fallbacks += 1

    curves = {}
    for day, ks in knots.items():
        pts = sorted({m: iv for m, iv in ks}.items())  # last knot wins per minute

        def iv_at(minute: float, pts=pts) -> float:
            if minute <= pts[0][0]:
                return pts[0][1]
            for (m0, v0), (m1, v1) in zip(pts, pts[1:]):
                if minute <= m1:
                    return v0 if m1 == m0 else v0 + (v1 - v0) * (minute - m0) / (m1 - m0)
            return pts[-1][1]

        curves[day] = iv_at
    return curves, fallbacks


# ---------------------------------------------------------------- simulation
def sim_trade(bars: list[dict], iv_at, direction: str, entry_minute: float,
              tp: float, sl: float, cost: float = COST,
              scale: tuple[float, float] | None = None) -> dict | None:
    """One 0DTE trade. tp/sl are fractions of the PAID premium (tp=1.0 -> +100%).
    scale=(frac, level): sell `frac` of the position at +level, ride the rest.
    Returns None if no valid entry (no bar at entry_minute / premium too small)."""
    entry_bar = next((b for b in bars if b["minute"] == entry_minute), None)
    if entry_bar is None or entry_minute >= HARD_EXIT_MIN:
        return None
    spot = entry_bar["o"]
    tau0 = (SESSION_MIN - entry_minute) / YEAR_MIN
    iv0  = iv_at(entry_minute)
    strike = pick_strike(spot, tau0, iv0, direction)
    mid = bs_price(spot, strike, tau0, iv0, direction)
    if mid < MIN_PREMIUM:
        return None
    paid = mid + cost
    tp_level, sl_level = paid * (1.0 + tp), paid * (1.0 - sl)

    open_frac, proceeds = 1.0, 0.0
    scaled_out = False
    result, exit_minute = None, None

    for b in bars:
        if b["minute"] < entry_minute:
            continue
        if b["minute"] >= HARD_EXIT_MIN:
            tau = (SESSION_MIN - b["minute"]) / YEAR_MIN
            mark = bs_price(b["o"], strike, tau, iv_at(b["minute"]), direction) - cost
            proceeds += open_frac * max(mark, 0.0)
            result, exit_minute = "EXPIRED", b["minute"]
            break
        bar_end = b["minute"] + 15.0
        tau = (SESSION_MIN - bar_end) / YEAR_MIN
        iv  = iv_at(bar_end)
        worst = b["l"] if direction == "call" else b["h"]
        best  = b["h"] if direction == "call" else b["l"]
        opt_low  = bs_price(worst, strike, tau, iv, direction) - cost
        opt_high = bs_price(best,  strike, tau, iv, direction) - cost

        if opt_low <= sl_level:                      # pessimistic: SL first
            proceeds += open_frac * sl_level
            result, exit_minute = "SL", bar_end
            break
        if scale and not scaled_out and opt_high >= paid * (1.0 + scale[1]):
            frac = scale[0]
            proceeds += frac * paid * (1.0 + scale[1])
            open_frac -= frac
            scaled_out = True
        if opt_high >= tp_level:
            proceeds += open_frac * tp_level
            result, exit_minute = "TP", bar_end
            break

    if result is None:                               # defensive (no 15:30 bar)
        b = bars[-1]
        mark = bs_price(b["c"], strike, 0.0, 0.0, direction) - cost
        proceeds += open_frac * max(mark, 0.0)
        result, exit_minute = "EXPIRED", b["minute"] + 15.0

    return {
        "strike": strike, "spot": round(spot, 2), "paid": round(paid, 2),
        "iv_entry": round(iv0 * 100, 2), "result": result,
        "scaled_out": scaled_out, "exit_minute": exit_minute,
        "pnl_pct": round((proceeds - paid) / paid * 100.0, 2),
    }


def run_config(sessions: dict, curves: dict, directions: list[str],
               entry_minute: float = 0.0, tp: float = 1.0, sl: float = 0.5,
               cost: float = COST, scale=None, day_filter=None,
               direction_picker=None) -> list[dict]:
    trades = []
    for day in sorted(sessions):
        if day not in curves or (day_filter and not day_filter(day)):
            continue
        bars = sessions[day]
        if len(bars) < 26 or bars[0]["minute"] != 0.0:
            continue
        dirs = direction_picker(bars) if direction_picker else directions
        for d in dirs:
            t = sim_trade(bars, curves[day], d, entry_minute, tp, sl, cost, scale)
            if t:
                t.update({"date": day, "type": d})
                trades.append(t)
    return trades


# ---------------------------------------------------------------- statistics
def summarize(trades: list[dict]) -> dict:
    n = len(trades)
    if not n:
        return {"n": 0}
    wins = sum(1 for t in trades if t["result"] == "TP")
    sls  = sum(1 for t in trades if t["result"] == "SL")
    exp  = n - wins - sls
    return {
        "n": n, "wins": wins, "losses": sls, "expired": exp,
        "win_rate_pct": round(wins / n * 100, 1),
        "avg_pnl_pct": round(sum(t["pnl_pct"] for t in trades) / n, 1),
    }


def bootstrap_ci(trades: list[dict], iters: int = 10000, seed: int = 42) -> dict:
    """90% CI on avg P&L and win rate via resampling with replacement."""
    if not trades:
        return {}
    rng = random.Random(seed)
    pnls = [t["pnl_pct"] for t in trades]
    tps  = [1.0 if t["result"] == "TP" else 0.0 for t in trades]
    n = len(pnls)
    means, rates = [], []
    for _ in range(iters):
        idx = [rng.randrange(n) for _ in range(n)]
        means.append(sum(pnls[i] for i in idx) / n)
        rates.append(sum(tps[i] for i in idx) / n * 100)
    means.sort(); rates.sort()
    lo, hi = int(iters * 0.05), int(iters * 0.95)
    return {
        "avg_pnl_ci90": [round(means[lo], 1), round(means[hi], 1)],
        "win_rate_ci90": [round(rates[lo], 1), round(rates[hi], 1)],
    }


def slice_by(trades: list[dict], key_fn) -> dict:
    groups: dict[str, list[dict]] = {}
    for t in trades:
        groups.setdefault(key_fn(t), []).append(t)
    return {k: summarize(v) for k, v in sorted(groups.items())}


# ---------------------------------------------------------------- the suite
def main(output: str = "") -> dict:
    spx      = _sessions(_load("spx_15min_ibkr.json"))
    vix_hr   = _load("vix1d_hourly_ibkr.json")
    vix_day  = _load("vix1d_daily_ibkr.json")
    curves, fallbacks = _iv_curves(vix_hr, vix_day)

    full = {d: b for d, b in spx.items() if len(b) >= 26 and b[0]["minute"] == 0.0}
    print(f"Sessions: {len(full)} full ({min(full)} → {max(full)}), "
          f"{fallbacks} day(s) on daily-IV fallback\n")

    results: dict = {"sessions": len(full), "first": min(full), "last": max(full),
                     "cost_per_side": COST}

    # 1. Baseline, frictionless (comparable to ibkr_backtest.py v1)
    base_free = run_config(full, curves, ["call", "put"], cost=0.0)
    results["baseline_frictionless"] = {**summarize(base_free), **bootstrap_ci(base_free)}

    # 2. Baseline with costs — the honest headline number
    base = run_config(full, curves, ["call", "put"])
    results["baseline_with_costs"] = {**summarize(base), **bootstrap_ci(base)}

    # 3. Entry-time sweep (with costs)
    results["entry_time_sweep"] = {}
    for m, label in [(0, "09:30"), (30, "10:00"), (60, "10:30"),
                     (90, "11:00"), (150, "12:00"), (210, "13:00")]:
        ts = run_config(full, curves, ["call", "put"], entry_minute=float(m))
        results["entry_time_sweep"][label] = summarize(ts)

    # 4. TP/SL grid (with costs)
    results["tp_sl_grid"] = {}
    for tp in (0.5, 0.75, 1.0, 1.5):
        for sl in (0.3, 0.4, 0.5):
            ts = run_config(full, curves, ["call", "put"], tp=tp, sl=sl)
            results["tp_sl_grid"][f"TP+{int(tp*100)}/SL-{int(sl*100)}"] = summarize(ts)

    # 5. Scaling exit: half off at +50%, rest to TP+100%/SL-50%
    scaled = run_config(full, curves, ["call", "put"], scale=(0.5, 0.5))
    results["scaling_exit"] = {**summarize(scaled), **bootstrap_ci(scaled)}

    # 6. Naive momentum filter: 10:00 entry in the direction of the first 30 min
    def momentum(bars):
        move = bars[1]["c"] - bars[0]["o"]
        return ["call"] if move > 0 else ["put"] if move < 0 else []
    mom = run_config(full, curves, [], entry_minute=30.0, direction_picker=momentum)
    results["momentum_10am"] = {**summarize(mom), **bootstrap_ci(mom)}

    # 7. Slices of the with-costs baseline
    vix_open = {t[:10]: vix_day["open"][i] for i, t in enumerate(vix_day["time"])}

    def bucket(t):
        v = vix_open.get(t["date"], t["iv_entry"])
        return "vix<10" if v < 10 else "vix 10-15" if v < 15 else "vix>=15"
    results["by_direction"] = slice_by(base, lambda t: t["type"])
    results["by_vix_regime"] = slice_by(base, bucket)
    results["by_weekday"] = slice_by(
        base, lambda t: datetime.strptime(t["date"], "%Y-%m-%d").strftime("%a"))

    # ------------------------------------------------------------- report
    def line(name, s):
        if not s.get("n"):
            return f"  {name:<22s} —"
        ci = (f"  CI90 pnl [{s['avg_pnl_ci90'][0]:+.1f},{s['avg_pnl_ci90'][1]:+.1f}]"
              if "avg_pnl_ci90" in s else "")
        return (f"  {name:<22s} n={s['n']:<4d} win={s['win_rate_pct']:4.1f}%  "
                f"avg={s['avg_pnl_pct']:+6.1f}%{ci}")

    print("=" * 74)
    print(f"IBKR SPX 0DTE SUITE — {len(full)} sessions, cost {COST:.2f}/side")
    print("=" * 74)
    print(line("frictionless", results["baseline_frictionless"]))
    print(line("with costs", results["baseline_with_costs"]))
    print(line("scaling exit", results["scaling_exit"]))
    print(line("momentum @10:00", results["momentum_10am"]))
    print("\nEntry time (with costs):")
    for k, s in results["entry_time_sweep"].items():
        print(line(k, s))
    print("\nTP/SL grid (with costs):")
    for k, s in results["tp_sl_grid"].items():
        print(line(k, s))
    print("\nBy direction:")
    for k, s in results["by_direction"].items():
        print(line(k, s))
    print("\nBy VIX1D regime:")
    for k, s in results["by_vix_regime"].items():
        print(line(k, s))
    print("\nBy weekday:")
    for k, s in results["by_weekday"].items():
        print(line(k, s))
    print("=" * 74)

    if output:
        with open(output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {output}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="backtest_data/ibkr_suite_results.json")
    args = parser.parse_args()
    main(args.output)
