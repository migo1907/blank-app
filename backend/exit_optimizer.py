"""
Adaptive exit optimizer — self-improving, SHADOW mode.

The ML learns the ENTRY (direction). This module learns the EXIT — the take-profit
structure — from each pool's OWN trade history, the same self-improvement concept as
the adaptive KNN weights. As more trades close, the recommended exits re-derive
themselves automatically.

SHADOW-ONLY: it computes and persists recommended take-profit levels + projected
expectancy per pool. It does NOT change live trading. Recommendations feed the Pine
Script (manual/seeded) only after a human validates them — keeping Rule 4 (verify
before changing live) and Rule 5 (Pine backup sync) intact.

Data basis (per closed trade, already recorded):
  • mfe         — max favorable excursion in PRICE POINTS
  • entry_price — to convert mfe → % move
  • pnl_pct     — realized result under the CURRENT fixed exit rule
  • tp_stage    — TP3 / SL_TP2 / SL_TP1 / SL

Method: simulate alternative fixed take-profit levels. A trade whose favorable
excursion reached the candidate TP banks that TP; one that didn't keeps its actual
realized result. The TP that maximizes mean expectancy is the recommendation. This
directly attacks the confirmed leak — the tight post-TP1 trail that scratches
winners (SL_TP1 banks ~0 while the move ran further).

LIMITATION (honest): MAE (adverse excursion) is not yet captured, so this optimizes
the take-profit / let-winners-run side only; stop placement is held as-is and flagged
for Phase B. Projections are estimates pending live shadow validation.
"""

from __future__ import annotations

import statistics as _st

# Round-trip cost (spread + slippage) charged to a simulated TP fill, in % of price.
# Conservative default; can be tuned per pool later from realized fill data.
_COST_PCT = 0.01

# Candidate take-profit grid, in % of entry price. Scaled per pool to its own move
# distribution so a 2M gold scalp and a 4H stock swing each search a sane range.
_GRID_STEPS = 40


def _mfe_pct(t: dict) -> float | None:
    try:
        mfe = float(t.get("mfe"))
        ep = float(t.get("entry_price"))
        if ep <= 0:
            return None
        return max(0.0, mfe / ep * 100.0)   # favorable move only
    except Exception:
        return None


def _expectancy_at_tp(trades: list[dict], tp_pct: float) -> float:
    """Mean simulated pnl% if take-profit were a fixed tp_pct (cost-adjusted).
    Reached → bank tp_pct − cost; not reached → keep actual realized pnl_pct."""
    sims = []
    for t in trades:
        mp = _mfe_pct(t)
        realized = t.get("pnl_pct")
        if mp is None or realized is None:
            continue
        if mp >= tp_pct:
            sims.append(tp_pct - _COST_PCT)
        else:
            sims.append(float(realized))
    return _st.mean(sims) if sims else 0.0


def optimize_pool(trades: list[dict]) -> dict | None:
    """Derive the expectancy-maximizing fixed take-profit for one pool.
    Returns None when there isn't enough usable data (need ≥30 trades with mfe)."""
    usable = [t for t in trades
              if _mfe_pct(t) is not None and t.get("pnl_pct") is not None
              and t.get("outcome") in ("WIN", "PARTIAL", "LOSS")]
    if len(usable) < 30:
        return None

    realized = [float(t["pnl_pct"]) for t in usable]
    current_exp = _st.mean(realized)

    mfes = sorted(_mfe_pct(t) for t in usable)
    # Search from a small floor up to the 90th-percentile favorable move — beyond
    # that, almost nothing reaches the TP so it just degrades to the stop.
    hi = mfes[min(len(mfes) - 1, int(len(mfes) * 0.90))]
    if hi <= 0.02:
        return None
    lo = 0.02
    step = (hi - lo) / _GRID_STEPS

    best_tp, best_exp = None, current_exp
    grid = []
    for i in range(_GRID_STEPS + 1):
        tp = lo + step * i
        exp = _expectancy_at_tp(usable, tp)
        reach = sum(1 for t in usable if (_mfe_pct(t) or 0) >= tp) / len(usable)
        grid.append({"tp_pct": round(tp, 4), "expectancy": round(exp, 5),
                     "reach_rate": round(reach, 3)})
        if exp > best_exp:
            best_tp, best_exp = tp, exp

    n_scratch = sum(1 for t in usable if t.get("tp_stage") == "SL_TP1")
    return {
        "n": len(usable),
        "current_expectancy": round(current_exp, 5),
        "current_net": round(sum(realized), 2),
        "recommended_tp_pct": round(best_tp, 4) if best_tp else None,
        "projected_expectancy": round(best_exp, 5),
        "expectancy_gain": round(best_exp - current_exp, 5),
        "flips_positive": current_exp <= 0 < best_exp,
        "scratched_sl_tp1": n_scratch,
        "median_favorable_move_pct": round(_st.median(mfes), 4),
        "grid": grid,
        "note": ("Optimizes take-profit only — MAE not captured, so stop placement "
                 "is held as-is (Phase B). SHADOW: not applied to live trades."),
    }


# Pools to analyze (5M and above — the timeframes actually traded).
_POOLS = [
    "XAUUSD_5M", "XAUUSD_15M", "XAUUSD_30M", "XAUUSD_1H",
    "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_4H",
    "STOCKS_QUALITY_15M", "STOCKS_QUALITY_30M",
    "STOCKS_SPX500_15M", "STOCKS_SPX500_30M",
    "STOCKS_QQQ_15M", "STOCKS_INDEX_15M",
]

_OPT_PATH = "data/exit_optimization.json"


def run_all() -> dict:
    """Re-derive recommended exits for every traded pool and persist to the data
    branch. Self-improving: re-runs on a schedule, sharpening as trades accumulate."""
    from datetime import datetime, timezone
    from db import _get_file, _put_file

    results = {}
    for pool in _POOLS:
        try:
            hist, _ = _get_file(f"data/trade_history_{pool}.json")
            if not isinstance(hist, list):
                continue
            r = optimize_pool(hist)
            if r:
                results[pool] = r
        except Exception as e:
            print(f"[exit_opt] {pool} failed: {e}")

    out = {"updated_at": datetime.now(timezone.utc).isoformat(),
           "mode": "shadow", "pools": results}
    try:
        _, sha = _get_file(_OPT_PATH)
        _put_file(_OPT_PATH, out, sha, "data: adaptive exit optimization (shadow)")
    except Exception as e:
        print(f"[exit_opt] persist failed: {e}")

    pos = sum(1 for r in results.values() if r.get("flips_positive"))
    print(f"[exit_opt] {len(results)} pools optimized — {pos} flip to positive expectancy")
    return out
