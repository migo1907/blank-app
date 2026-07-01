"""
Grade SPX 0/1DTE trades on REAL option premiums pulled from IBKR, and
measure how far the Black-Scholes repricing engine (ibkr_backtest*) sits
from the market.

Input: backtest_data/spx_options_real_ibkr.json (real premium bars per
contract), spx_1min_ibkr.json (underlying), vix1d_hourly_recent_ibkr.json.

Two products:
  1. grade_from_series results for every valid 0DTE (enter 09:30/10:00 ET,
     hard exit 15:30 ET) and 1DTE (enter 13:00 ET, hard exit 14:00 ET next
     session) window present in the data — TP +100% / SL -50%, pessimistic
     same-bar SL, gap-aware fills. Windows whose series ends before the
     hard exit are graded DATA_END and disclosed, never silently dropped.
  2. Minute-level BS-vs-real fit per contract (median model/real ratio,
     MAE%) — a direct recalibration check on the iv_mult used by
     ibkr_backtest_suite (previous fit: trading-time tau, IV x 0.85 from
     ledger snapshots only).

Run:  python options_backtest_run.py [--output backtest_data/options_real_grading.json]
"""
from __future__ import annotations
import os, json, math, argparse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from options_backtest import (grade_from_series, bars_from_arrays,
                              hard_exit_utc, series_fit_stats)
from ibkr_backtest import bs_price

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_data")
_ET = ZoneInfo("America/New_York")


def _load(name):
    p = os.path.join(_DIR, name)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def _et_date(dt_utc: datetime) -> str:
    return dt_utc.astimezone(_ET).date().isoformat()


def _utc_at_et(day_iso: str, hh: int, mm: int) -> datetime:
    d = datetime.fromisoformat(day_iso)
    return d.replace(hour=hh, minute=mm, tzinfo=_ET).astimezone(timezone.utc)


def _next_trading_day(day_iso: str) -> str:
    d = datetime.fromisoformat(day_iso) + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.date().isoformat()


def _iv_curve(vix: dict):
    """timestamp -> IV fraction, step function from VIX1D hourly opens."""
    knots = sorted(
        (datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc),
         vix["open"][i] / 100.0) for i, t in enumerate(vix["time"]))

    def iv_at(ts: datetime) -> float | None:
        prev = None
        for k, v in knots:
            if k > ts:
                break
            prev = v
        return prev
    return iv_at


def grade_all(real: dict) -> list[dict]:
    """Every 0DTE / 1DTE window present in each contract's 1-min series."""
    out = []
    for c in real["contracts"]:
        bars_data = c.get("bars_1min") or c.get("bars_5min")
        if not bars_data or not bars_data.get("time"):
            continue
        bars = bars_from_arrays(bars_data)
        expiry = f'{c["expiry"][:4]}-{c["expiry"][4:6]}-{c["expiry"][6:]}'
        days = sorted({_et_date(b["time"]) for b in bars})
        for day in days:
            windows = []
            if day == expiry:                        # 0DTE session
                for hh, mm in ((9, 30), (10, 0)):
                    windows.append(("0DTE", _utc_at_et(day, hh, mm),
                                    hard_exit_utc(_utc_at_et(day, hh, mm), 0)))
            elif _next_trading_day(day) == expiry:   # 1DTE session
                ent = _utc_at_et(day, 13, 0)
                windows.append(("1DTE", ent, hard_exit_utc(ent, 1)))
            for kind, ent, hard in windows:
                g = grade_from_series(bars, ent, hard)
                if g and g["entry_time"] - ent <= timedelta(minutes=30):
                    out.append({
                        "expiry": expiry, "right": c["right"],
                        "strike": c["strike"], "kind": kind, "day": day,
                        "entry_et": ent.astimezone(_ET).strftime("%H:%M"),
                        **{k: (v.isoformat() if isinstance(v, datetime) else v)
                           for k, v in g.items()},
                    })
    return out


def bs_fit(real: dict, spx_1min: dict, vix_hourly: dict) -> dict:
    """Minute-level BS model price vs real premium, per contract and pooled."""
    spot_at = {t: spx_1min["open"][i] for i, t in enumerate(spx_1min["time"])}
    iv_at = _iv_curve(vix_hourly)
    per, pooled_real, pooled_model = {}, [], []
    for c in real["contracts"]:
        bars_data = c.get("bars_1min")
        if not bars_data or not bars_data.get("time"):
            continue
        exp_utc = datetime.strptime(c["expiry"], "%Y%m%d").replace(
            hour=16, minute=0, tzinfo=_ET).astimezone(timezone.utc)
        reals, models = [], []
        for i, t in enumerate(bars_data["time"]):
            spot = spot_at.get(t)
            if spot is None:
                continue
            ts = datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            iv = iv_at(ts)
            if iv is None:
                continue
            tau = max((exp_utc - ts).total_seconds(), 0.0) / (365.0 * 24 * 3600)
            models.append(bs_price(spot, c["strike"], tau, iv, c["right"]))
            reals.append(bars_data["open"][i])
        key = f'{c["expiry"]}_{c["right"]}_{c["strike"]:g}'
        per[key] = series_fit_stats(reals, models)
        pooled_real += reals
        pooled_model += models
    return {"per_contract": per, "pooled": series_fit_stats(pooled_real, pooled_model)}


def main(output: str = "") -> dict:
    real = _load("spx_options_real_ibkr.json")
    if not real:
        print("spx_options_real_ibkr.json missing — nothing to grade")
        return {}
    grades = grade_all(real)
    results: dict = {"fetched": real.get("fetched"), "grades": grades}

    print(f"Real-premium grading — {len(real['contracts'])} contracts")
    for g in grades:
        print(f'  {g["day"]} {g["kind"]} {g["right"]:4s} K={g["strike"]:g} '
              f'@{g["entry_et"]} paid={g["paid"]:.2f} -> {g["result"]:8s} '
              f'({g["pnl_pct"]:+7.1f}%) exit={g["exit"]:.2f}')

    spx = _load("spx_1min_ibkr.json")
    vix = _load("vix1d_hourly_recent_ibkr.json") or _load("vix1d_hourly_ibkr.json")
    if spx and vix:
        fit = bs_fit(real, spx, vix)
        results["bs_fit"] = fit
        p = fit["pooled"]
        print(f'\nBS (calendar tau, raw VIX1D) vs real, pooled: n={p.get("n", 0)} '
              f'median model/real={p.get("median_ratio")} mae={p.get("mae_pct")}%')
        for k, s in sorted(fit["per_contract"].items()):
            if s.get("n"):
                print(f'  {k:26s} n={s["n"]:<4d} ratio={s["median_ratio"]:.3f} '
                      f'mae={s["mae_pct"]:.1f}%')

    if output:
        def _ser(o):
            return o.isoformat() if isinstance(o, datetime) else str(o)
        with open(output, "w") as f:
            json.dump(results, f, indent=1, default=_ser)
        print(f"Saved -> {output}")
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="backtest_data/options_real_grading.json")
    main(p.parse_args().output)
