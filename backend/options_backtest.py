"""
SPX 0/1DTE options backtest — grades the live options-engine rules on history.

The options engine (options_engine.py) fires a long call/put when an SPX signal
flips, picks a ~Δ0.25 OTM strike, and manages TP +100% / SL -50% / hard-exit
(15:30 ET for 0DTE, 14:00 ET next session for 1DTE). This harness replays those
exact rules over historical underlying bars and reports realized expectancy per
pool — the piece the intraday exit work never covered.

Two pricing modes, same grading:
  • bs  (default, runs NOW)  — reprice the option every bar with Black-Scholes on
    the realized spot path + shrinking time-to-expiry. Theta decay is intrinsic to
    the shrinking-tau term, so a signal that's "right but slow" correctly loses to
    decay. IV is estimated from the underlying's own realized vol (VIX proxy).
  • ticks (when available)   — feed real IBKR historical option premiums per entry
    via grade_from_series(); BS is only the fallback until those are wired.

Approximation, not a fill simulator: no bid/ask spread, no early-assignment, no
skew (single ATM IV). Directionally honest for "does this strategy have edge",
which is the question. Refine with real option ticks once IBKR options data lands.

Shares the intraday harness's signal core so entries match production exactly.
"""
from __future__ import annotations
import math

# Mirror the live engine's constants so the backtest can't drift from production.
TARGET_DELTA = 0.25
TP_MULT      = 2.0    # +100% premium
SL_MULT      = 0.5    # -50% premium
CUTOFF_0DTE_ET = 13   # hour (ET) — signals after this roll to 1DTE
HARD_EXIT_0DTE_ET = (15, 30)   # 15:30 ET same day
HARD_EXIT_1DTE_ET = (14, 0)    # 14:00 ET next session
_SPX_STRIKE_STEP = 5.0
_TRADING_DAYS = 252.0
_MINUTES_YEAR = 525600.0


def _bs_price(spot: float, strike: float, iv: float, tau_years: float, is_call: bool) -> float:
    """Black-Scholes option price, r=0 (negligible at 0-1DTE). tau in years."""
    if tau_years <= 0 or iv <= 0:
        return max(0.0, (spot - strike) if is_call else (strike - spot))  # intrinsic
    srt = iv * math.sqrt(tau_years)
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * tau_years) / srt
    d2 = d1 - srt
    nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    nd2 = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
    if is_call:
        return spot * nd1 - strike * nd2
    return strike * (1 - nd2) - spot * (1 - nd1)


def _bs_delta(spot: float, strike: float, iv: float, tau_years: float, is_call: bool) -> float:
    if iv <= 0 or tau_years <= 0:
        return 0.5
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * tau_years) / (iv * math.sqrt(tau_years))
    nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    return nd1 if is_call else nd1 - 1.0


def _pick_strike(spot: float, iv: float, tau_years: float, is_call: bool) -> float:
    """OTM strike whose |delta| is closest to TARGET_DELTA, on the SPX 5-pt grid."""
    best, best_err = None, 9e9
    steps = int(40)
    for k in range(-steps, steps + 1):
        strike = round((spot + k * _SPX_STRIKE_STEP) / _SPX_STRIKE_STEP) * _SPX_STRIKE_STEP
        if is_call and strike <= spot:   # OTM calls above spot
            continue
        if (not is_call) and strike >= spot:
            continue
        d = _bs_delta(spot, strike, iv, tau_years, is_call)
        err = abs(abs(d) - TARGET_DELTA)
        if err < best_err:
            best_err, best = err, strike
    return best if best is not None else spot


def _realized_iv(closes, i, window: int = 30) -> float:
    """Annualized realized vol from the trailing `window` bar log-returns → IV proxy.
    Falls back to 0.15 (≈VIX 15) when there isn't enough history."""
    lo = max(1, i - window)
    rets = []
    for j in range(lo, i + 1):
        p0, p1 = closes[j - 1], closes[j]
        if p0 > 0 and p1 > 0:
            rets.append(math.log(p1 / p0))
    if len(rets) < 5:
        return 0.15
    m = sum(rets) / len(rets)
    var = sum((r - m) ** 2 for r in rets) / (len(rets) - 1)
    # per-bar vol → annualized. bars_per_year inferred from count vs trading days is
    # unreliable intraday, so scale by trading days * bars/day passed in via closure.
    return max(0.05, min(1.5, math.sqrt(var) * math.sqrt(_TRADING_DAYS * _BARS_PER_DAY[0])))


_BARS_PER_DAY = [26]  # ~6.5h RTH / 15min; overridden per run in run_bars


def _et_hour_min(ts):
    """UTC pandas Timestamp → (hour, minute) in US/Eastern (approx: UTC-4, summer)."""
    # RTH data is summer-heavy; ET = UTC-4. Good enough for the 13:00/15:30 gates.
    et = ts.tz_convert("America/New_York") if ts.tzinfo else ts
    return et.hour, et.minute


def run_bars(symbol: str, tf: str, bars, bars_per_day: int = 26) -> dict:
    """Backtest the options engine on underlying bars. `tf` is Pine notation.
    Returns per-pool (SPX_0DTE / SPX_1DTE) expectancy summaries."""
    import polygon_intraday_backtest as bt
    _BARS_PER_DAY[0] = bars_per_day
    rows = bars.get("data") if isinstance(bars, dict) else bars
    if not rows or len(rows) < 60:
        return {"symbol": symbol, "error": f"too few bars ({len(rows) if rows else 0})"}
    df = bt._bars_to_df([{"t": int(b["t"]), "o": float(b["o"]), "h": float(b["h"]),
                          "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v", 0) or 0)}
                         for b in rows])
    F = bt.compute_features(df)
    sig = bt._signals(F, tf)
    closes = df["c"].values
    idx = df.index
    n = len(df)

    trades = []
    last_sig = 0
    for i in range(n):
        new_sig = 1 if bool(sig["long_ok"].iloc[i]) else (-1 if bool(sig["short_ok"].iloc[i]) else 0)
        if new_sig == 0 or new_sig == last_sig:
            continue
        last_sig = new_sig
        hr, mn = _et_hour_min(idx[i])
        is_call = new_sig == 1
        spot = float(closes[i])
        iv = _realized_iv(closes, i)
        dte = 0 if hr < CUTOFF_0DTE_ET else 1
        # time to expiry (years): expiry at 16:00 ET on entry day (0DTE) or next (1DTE)
        mins_to_expiry = ((16 - hr) * 60 - mn) + (dte * 24 * 60)
        if mins_to_expiry <= 5:
            continue
        tau0 = mins_to_expiry / _MINUTES_YEAR
        strike = _pick_strike(spot, iv, tau0, is_call)
        entry_prem = _bs_price(spot, strike, iv, tau0, is_call)
        if entry_prem < 0.10:
            continue
        tp, sl = entry_prem * TP_MULT, entry_prem * SL_MULT
        he_hr, he_mn = HARD_EXIT_0DTE_ET if dte == 0 else HARD_EXIT_1DTE_ET
        # walk forward, reprice each bar
        exit_prem, reason = entry_prem, "timeout"
        for j in range(i + 1, n):
            hj, mj = _et_hour_min(idx[j])
            dayspan = (idx[j].normalize() - idx[i].normalize()).days
            mins_left = ((16 - hj) * 60 - mj) + max(0, dte - dayspan) * 24 * 60
            tau = max(0.0, mins_left / _MINUTES_YEAR)
            prem = _bs_price(float(closes[j]), strike, iv, tau, is_call)
            if prem >= tp:
                exit_prem, reason = tp, "TP"; break
            if prem <= sl:
                exit_prem, reason = sl, "SL"; break
            # hard exit
            if dayspan >= dte and (hj > he_hr or (hj == he_hr and mj >= he_mn)):
                exit_prem, reason = prem, "hard_exit"; break
            if tau <= 0:
                exit_prem, reason = prem, "expiry"; break
        pnl_pct = (exit_prem - entry_prem) / entry_prem * 100.0
        trades.append({"pool": "SPX_0DTE" if dte == 0 else "SPX_1DTE",
                       "direction": "CALL" if is_call else "PUT",
                       "entry_premium": round(entry_prem, 2), "exit_premium": round(exit_prem, 2),
                       "pnl_pct": round(pnl_pct, 2), "reason": reason, "iv": round(iv, 3)})

    return {"symbol": symbol, "timeframe": tf, "n_trades": len(trades),
            "pools": {p: _summ([t for t in trades if t["pool"] == p]) for p in ("SPX_0DTE", "SPX_1DTE")},
            "overall": _summ(trades)}


def _summ(trades) -> dict:
    n = len(trades)
    if not n:
        return {"n": 0}
    wins = [t for t in trades if t["pnl_pct"] > 0]
    gross_w = sum(t["pnl_pct"] for t in wins)
    gross_l = -sum(t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0)
    reasons = {}
    for t in trades:
        reasons[t["reason"]] = reasons.get(t["reason"], 0) + 1
    return {"n": n, "win_rate": round(len(wins) / n * 100, 1),
            "avg_pnl_pct": round(sum(t["pnl_pct"] for t in trades) / n, 2),
            "profit_factor": round(gross_w / gross_l, 3) if gross_l > 0 else None,
            "exit_reasons": reasons}


def grade_from_series(entry_premium: float, premium_series: list[float]) -> dict:
    """Grade one trade against a REAL option-premium series (IBKR ticks): first
    touch of TP (+100%) or SL (-50%), else last value. Used when option history
    is available — no Black-Scholes assumption."""
    tp, sl = entry_premium * TP_MULT, entry_premium * SL_MULT
    for p in premium_series:
        if p >= tp:
            return {"exit": tp, "pnl_pct": 100.0, "reason": "TP"}
        if p <= sl:
            return {"exit": sl, "pnl_pct": -50.0, "reason": "SL"}
    last = premium_series[-1] if premium_series else entry_premium
    return {"exit": last, "pnl_pct": round((last - entry_premium) / entry_premium * 100, 2),
            "reason": "timeout"}
