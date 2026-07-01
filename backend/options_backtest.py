"""
Grade 0/1DTE option trades on REAL premium bar series.

ibkr_backtest.py / ibkr_backtest_suite.py reprice the option path with
Black-Scholes because IBKR does not serve expired contracts. This module is
the other half: when a real premium series exists (live contracts pulled
from IBKR, or series accumulated day by day going forward), grade the trade
on actual traded prices — no model.

Exit conventions mirror options_engine paper rules:
  - TP  +100% of the paid premium  (tp_mult=2.0)
  - SL  -50%  of the paid premium  (sl_mult=0.5)
  - Hard exit 15:30 ET same day (0DTE) / 14:00 ET next session (1DTE),
    filled at the first bar open at/after the deadline
  - SL checked before TP on the same bar (pessimistic, matches the
    swing_tracker / ibkr_backtest convention)
  - A bar that OPENS through a level fills at the open (gaps are real in
    sparse option prints — never assume the level price)

Entry is the open of the first bar at/after entry_time unless entry_price
is given (e.g. the recommendation's quoted mid).
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_ET = ZoneInfo("America/New_York")


def bars_from_arrays(data: dict) -> list[dict]:
    """{"time": [iso...], "open": [...], ...} -> sorted list of bar dicts
    with tz-aware UTC datetimes and o/h/l/c keys."""
    bars = []
    for i, t in enumerate(data["time"]):
        dt = datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        bars.append({"time": dt, "o": data["open"][i], "h": data["high"][i],
                     "l": data["low"][i], "c": data["close"][i]})
    bars.sort(key=lambda b: b["time"])
    return bars


def hard_exit_utc(entry_time_utc: datetime, dte: int) -> datetime:
    """Production hard-exit deadline as UTC: 15:30 ET today for 0DTE,
    14:00 ET next session (weekend-aware, not holiday-aware) for 1DTE."""
    et = entry_time_utc.astimezone(_ET)
    if dte == 0:
        deadline = et.replace(hour=15, minute=30, second=0, microsecond=0)
    else:
        nxt = et + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        deadline = nxt.replace(hour=14, minute=0, second=0, microsecond=0)
    return deadline.astimezone(timezone.utc)


def grade_from_series(bars: list[dict], entry_time: datetime,
                      hard_exit_time: datetime, tp_mult: float = 2.0,
                      sl_mult: float = 0.5, entry_price: float | None = None,
                      cost_per_side: float = 0.0) -> dict | None:
    """Grade one long-premium trade on a real option bar series.

    Returns None when no bar exists at/after entry_time or the entry premium
    is not positive. Otherwise a dict with result TP | SL | EXPIRED |
    DATA_END (series ended before the hard exit — disclosed, not hidden).
    """
    live = [b for b in bars if b["time"] >= entry_time]
    if not live:
        return None
    entry_bar = live[0]
    raw_entry = entry_price if entry_price is not None else entry_bar["o"]
    if raw_entry is None or raw_entry <= 0:
        return None
    paid = raw_entry + cost_per_side
    tp_level = paid * tp_mult
    sl_level = paid * sl_mult

    result = exit_px = exit_time = None
    n_bars = 0
    for b in live:
        if b["time"] >= hard_exit_time:
            result, exit_px, exit_time = "EXPIRED", b["o"] - cost_per_side, b["time"]
            break
        n_bars += 1
        o = b["o"] - cost_per_side
        lo = b["l"] - cost_per_side
        hi = b["h"] - cost_per_side
        if o <= sl_level:                       # gapped through the stop
            result, exit_px, exit_time = "SL", o, b["time"]
            break
        if o >= tp_level:                       # gapped through the target
            result, exit_px, exit_time = "TP", o, b["time"]
            break
        if lo <= sl_level:                      # pessimistic: SL before TP
            result, exit_px, exit_time = "SL", sl_level, b["time"]
            break
        if hi >= tp_level:
            result, exit_px, exit_time = "TP", tp_level, b["time"]
            break

    if result is None:                          # series ran out early
        last = live[-1]
        result, exit_px = "DATA_END", last["c"] - cost_per_side
        exit_time = last["time"]

    return {
        "result": result,
        "paid": round(paid, 4),
        "exit": round(exit_px, 4),
        "entry_time": entry_bar["time"],
        "exit_time": exit_time,
        "pnl_pct": round((exit_px - paid) / paid * 100.0, 2),
        "tp_level": round(tp_level, 4),
        "sl_level": round(sl_level, 4),
        "n_bars": n_bars,
    }


def series_fit_stats(real: list[float], model: list[float]) -> dict:
    """How well a model premium path tracks the real one. Pairs where either
    side is missing/non-positive are dropped. median_ratio > 1 means the
    model prices rich vs the market."""
    pairs = [(r, m) for r, m in zip(real, model)
             if r is not None and m is not None and r > 0 and m > 0]
    if not pairs:
        return {"n": 0}
    ratios = sorted(m / r for r, m in pairs)
    n = len(ratios)
    med = (ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2)
    mae = sum(abs(m - r) / r for r, m in pairs) / n * 100.0
    return {"n": n, "median_ratio": round(med, 4), "mae_pct": round(mae, 2)}
