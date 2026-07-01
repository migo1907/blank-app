"""
Calibrate the Black-Scholes repricer against REAL recorded option premiums.

The production paper tracker (data/options_paper_SPX.json on the data branch)
records actual chain premiums + per-contract IV at entry. For each ledger
entry this compares:

  A. BS priced with the RECORDED per-contract IV  -> isolates BS mechanics
     (if A matches reality, the pricing engine itself is sound)
  B. BS priced with the VIX1D-based IV the backtest uses -> measures how much
     error the ATM-index-vol proxy introduces (vol smile + IV level error)

Output: per-trade table + mean absolute % error for A and B, and the implied
premium multiplier the backtest should apply to correct its bias.

Run:  python ibkr_calibration.py
"""
from __future__ import annotations
import json, os
from datetime import datetime, timezone

from ibkr_backtest import bs_price, _load, SESSION_MIN

YEAR_MIN = 60.0 * 24.0 * 365.0


def _tau_years(created_at: str, expiry: str) -> float:
    """Calendar time from entry to expiry 16:00 ET (20:00 UTC in summer)."""
    t0 = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    t1 = datetime.strptime(expiry + "T20:00:00Z", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return max((t1 - t0).total_seconds() / 60.0, 1.0) / YEAR_MIN


def _vix1d_iv(created_at: str, vix_hourly: dict, vix_daily: dict) -> float | None:
    """VIX1D level at the entry timestamp: nearest hourly bar open, else daily open."""
    day = created_at[:10]
    t0 = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
    best, best_gap = None, 1e9
    for i, t in enumerate(vix_hourly["time"]):
        if t[:10] != day:
            continue
        gap = abs((datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ") - t0).total_seconds())
        if gap < best_gap:
            best, best_gap = vix_hourly["open"][i], gap
    if best is not None:
        return best / 100.0
    for i, t in enumerate(vix_daily["time"]):
        if t[:10] == day:
            return vix_daily["open"][i] / 100.0
    return None


def main() -> None:
    ledger = _load("options_ledger_snapshot.json")["trades"]
    vix_hr = _load("vix1d_hourly_ibkr.json")
    vix_dy = _load("vix1d_daily_ibkr.json")

    errs_a, errs_b, ratios_b = [], [], []
    print(f"{'entry (UTC)':<17s} {'type':<4s} {'dte':>3s} {'strike':>7s} "
          f"{'real':>6s} {'BS@chainIV':>10s} {'BS@VIX1D':>9s} {'errA%':>6s} {'errB%':>6s}")
    print("-" * 78)
    for t in ledger:
        tau = _tau_years(t["created_at"], t["expiry"])
        direction = t["type"].lower()
        model_a = bs_price(t["spot"], t["strike"], tau, t["iv"], direction)
        iv_b = _vix1d_iv(t["created_at"], vix_hr, vix_dy)
        model_b = bs_price(t["spot"], t["strike"], tau, iv_b, direction) if iv_b else None
        real = t["entry_premium"]
        err_a = (model_a - real) / real * 100.0
        errs_a.append(abs(err_a))
        err_b_s = "    —"
        if model_b is not None:
            err_b = (model_b - real) / real * 100.0
            errs_b.append(abs(err_b))
            ratios_b.append(real / model_b)
            err_b_s = f"{err_b:+6.1f}"
        print(f"{t['created_at'][:16]:<17s} {t['type']:<4s} {t['dte']:>3d} "
              f"{t['strike']:>7.0f} {real:>6.2f} {model_a:>10.2f} "
              f"{(f'{model_b:9.2f}' if model_b is not None else '        —')} "
              f"{err_a:+6.1f} {err_b_s}")

    print("-" * 78)
    print(f"A (BS mechanics, chain IV):   mean |err| = {sum(errs_a)/len(errs_a):5.1f}%")
    if errs_b:
        mult = sum(ratios_b) / len(ratios_b)
        print(f"B (VIX1D proxy, backtest IV): mean |err| = {sum(errs_b)/len(errs_b):5.1f}%  "
              f"real/model multiplier = {mult:.2f}x")

    # ------------------------------------------------------------------
    # Fit: which (tau convention, IV multiplier) best reproduces the REAL
    # premiums when pricing from VIX1D? Real 0DTE chains embed trading-time
    # to expiry, not calendar hours — test both conventions and scan beta.
    # In-sample on the full ledger (small n — disclosed, not hidden).
    # ------------------------------------------------------------------
    def tau_trading(created_at: str, expiry: str) -> float:
        t0 = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")
        entry_min = max((t0.hour - 13) * 60.0 + t0.minute - 30.0, 0.0)
        session_frac = max(SESSION_MIN - entry_min, 1.0) / SESSION_MIN
        days_ahead = (datetime.strptime(expiry, "%Y-%m-%d")
                      - datetime(t0.year, t0.month, t0.day)).days
        return (session_frac + days_ahead) / 252.0

    best = None
    for conv, tau_fn in (("calendar", lambda t: _tau_years(t["created_at"], t["expiry"])),
                         ("trading",  lambda t: tau_trading(t["created_at"], t["expiry"]))):
        for beta_i in range(60, 181, 5):
            beta = beta_i / 100.0
            errs = []
            for t in ledger:
                iv = _vix1d_iv(t["created_at"], vix_hr, vix_dy)
                if iv is None:
                    continue
                model = bs_price(t["spot"], t["strike"], tau_fn(t), iv * beta,
                                 t["type"].lower())
                errs.append(abs(model - t["entry_premium"]) / t["entry_premium"] * 100.0)
            score = sum(errs) / len(errs)
            if best is None or score < best["mean_abs_err_pct"]:
                best = {"tau_convention": conv, "iv_mult": beta,
                        "mean_abs_err_pct": round(score, 1), "n_fit": len(errs)}

    print(f"\nBest fit vs real premiums: tau={best['tau_convention']}, "
          f"IV x {best['iv_mult']:.2f} -> mean |err| = {best['mean_abs_err_pct']:.1f}% "
          f"(fit on {best['n_fit']} ledger entries — small sample, in-sample)")
    fit_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "backtest_data", "ibkr_calibration_fit.json")
    with open(fit_path, "w") as f:
        json.dump(best, f, indent=2)
    print(f"Fit saved to {fit_path} (ibkr_backtest_suite.py picks it up automatically)")


if __name__ == "__main__":
    main()
