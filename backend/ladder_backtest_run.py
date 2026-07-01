"""
Validate the deployed exit ladders on real IBKR bars.

Runs the Pine-faithful ladder simulator (ladder_backtest.py) over every
instrument x timeframe series pulled from IBKR, signal-agnostic (long AND
short every N bars), so the numbers measure the LADDER's mechanics — hit
rates, R distribution, trail behavior — not entry edge. A ladder that is
sane shows: TP1 rate well above the ~1R-random baseline is not required,
but LOSS avg must sit near -1R (stops honored), PARTIALs must be >= 0R
(break-even guarantee), and expectancy across both directions should sit
near the spread/no-edge zone rather than deeply negative.

Discipline (per CLAUDE.md):
  - Split-half: the series is cut in two; regime thresholds (ATR%% terciles)
    come from the FIRST half only, and both halves are reported separately.
    Nothing is tuned on the second half.
  - Regime slices: trend (EMA20 vs EMA50, in ATR units) and volatility
    (ATR%% of price vs first-half terciles).

Run:  python ladder_backtest_run.py [--output backtest_data/ladder_validation.json]
"""
from __future__ import annotations
import os, json, argparse

from ladder_backtest import (TF_LADDERS, wilder_atr, simulate_ladder,
                             summarize_trades, scrub_bad_prints)

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_data")

# instrument, tf-bucket, data file, entry cadence (bars)
SERIES = [
    ("XAUUSD", "2m",  "xauusd_2m_ibkr.json",  15),
    ("XAUUSD", "5m",  "xauusd_5m_ibkr.json",  12),
    ("XAUUSD", "30m", "xauusd_30m_ibkr.json", 8),
    ("XAUUSD", "1h",  "xauusd_1h_ibkr.json",  6),
    ("SPX",    "2m",  "spx_2min_ibkr.json",   15),
    ("SPX",    "5m",  "spx_5min_ibkr.json",   12),
    ("SPX",    "15m", "spx_15min_ibkr.json",  10),
    ("SPX",    "30m", "spx_30min_ibkr.json",  8),
    ("SPX",    "1h",  "spx_1h_ibkr.json",     6),
]


def _load_bars(name: str) -> list[dict] | None:
    path = os.path.join(_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        d = json.load(f)
    bars = [{"time": d["time"][i], "o": d["open"][i], "h": d["high"][i],
             "l": d["low"][i], "c": d["close"][i]} for i in range(len(d["time"]))]
    return bars


def _ema(vals: list[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    out, e = [], vals[0]
    for v in vals:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def classify_regimes(bars: list[dict], atr: list) -> tuple[list, list]:
    """Per-bar trend + vol labels. Vol thresholds come from the FIRST HALF
    only (split-half discipline)."""
    closes = [b["c"] for b in bars]
    e20, e50 = _ema(closes, 20), _ema(closes, 50)
    trend = []
    for i in range(len(bars)):
        a = atr[i]
        if a is None or i < 50:
            trend.append(None)
            continue
        gap = (e20[i] - e50[i]) / a
        trend.append("trend_up" if gap > 0.5 else
                     "trend_down" if gap < -0.5 else "ranging")

    atr_pct = [(atr[i] / closes[i] if atr[i] else None) for i in range(len(bars))]
    half = [v for v in atr_pct[: len(bars) // 2] if v is not None]
    if not half:
        return trend, [None] * len(bars)
    half.sort()
    lo_t = half[len(half) // 3]
    hi_t = half[2 * len(half) // 3]
    vol = [None if v is None else
           ("low_vol" if v <= lo_t else "high_vol" if v > hi_t else "mid_vol")
           for v in atr_pct]
    return trend, vol


def run_series(bars: list[dict], tf_key: str, every: int) -> dict:
    ladder = TF_LADDERS[tf_key]
    bars, n_bad = scrub_bad_prints(bars)
    atr = wilder_atr(bars)
    trend, vol = classify_regimes(bars, atr)
    first = next((i for i, a in enumerate(atr) if a is not None), len(bars))
    first = max(first, 50)                     # regime warmup too

    trades = []
    for i in range(first, len(bars) - 1, every):
        for d in ("LONG", "SHORT"):
            t = simulate_ladder(bars, atr, i, d, ladder)
            if t:
                t["trend"] = trend[i]
                t["vol"] = vol[i]
                t["half"] = "H1" if i < len(bars) // 2 else "H2"
                trades.append(t)

    # exclude trades cut off by the end of data from the graded stats
    graded = [t for t in trades if t["stage"] != "DATA_END"]

    def _slice(key):
        groups: dict[str, list] = {}
        for t in graded:
            k = t.get(key)
            if k:
                groups.setdefault(k, []).append(t)
        return {k: summarize_trades(v) for k, v in sorted(groups.items())}

    losses = [t["r"] for t in graded if t["outcome"] == "LOSS"]
    partials = [t["r"] for t in graded if t["outcome"] == "PARTIAL"]
    return {
        "bars": len(bars),
        "bad_prints_dropped": n_bad,
        "span": f'{bars[0]["time"]} -> {bars[-1]["time"]}',
        "entries_every": every,
        "n_graded": len(graded),
        "n_data_end": len(trades) - len(graded),
        "overall": summarize_trades(graded),
        "sanity": {
            "loss_avg_r": round(sum(losses) / len(losses), 3) if losses else None,
            "partial_min_r": round(min(partials), 3) if partials else None,
            "partial_avg_r": round(sum(partials) / len(partials), 3) if partials else None,
        },
        "by_half": _slice("half"),
        "by_trend": _slice("trend"),
        "by_vol": _slice("vol"),
        "by_direction": _slice("direction"),
    }


def main(output: str = "") -> dict:
    results: dict = {}
    for inst, tf, fname, every in SERIES:
        bars = _load_bars(fname)
        if not bars:
            print(f"{inst} {tf:>3s} — {fname} missing, skipped")
            continue
        r = run_series(bars, tf, every)
        results[f"{inst}_{tf}"] = r
        o = r["overall"]
        s = r["sanity"]
        print(f"{inst} {tf:>3s} n={o['n']:<5d} tp1={o['tp1_rate_pct']:5.1f}% "
              f"avgR={o['avg_r']:+.3f} lossR={s['loss_avg_r']} "
              f"partial_minR={s['partial_min_r']}  [{r['span']}]")
        for h in ("H1", "H2"):
            hh = r["by_half"].get(h, {})
            if hh.get("n"):
                print(f"         {h}: n={hh['n']:<4d} tp1={hh['tp1_rate_pct']:5.1f}% "
                      f"avgR={hh['avg_r']:+.3f}")
    if output:
        with open(output, "w") as f:
            json.dump(results, f, indent=1)
        print(f"Saved -> {output}")
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="backtest_data/ladder_validation.json")
    main(p.parse_args().output)
