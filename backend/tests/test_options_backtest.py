"""
Tests for options_backtest.grade_from_series — grading 0/1DTE option trades
on REAL premium bar series (IBKR) instead of Black-Scholes repricing.

Written test-first. Conventions mirror options_engine paper rules:
  TP +100% of paid premium, SL -50%, hard exit 15:30 ET (0DTE) /
  14:00 ET next session (1DTE), SL checked before TP on the same bar
  (pessimistic), gap opens fill at the open (worse than the level).
"""
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from options_backtest import (grade_from_series, bars_from_arrays,
                              hard_exit_utc, series_fit_stats)


def _t(hh, mm, day=1):
    return datetime(2026, 7, day, hh, mm, tzinfo=timezone.utc)


def _bar(hh, mm, o, h, l, c, day=1):
    return {"time": _t(hh, mm, day), "o": o, "h": h, "l": l, "c": c}


# 13:30 UTC = 09:30 ET (EDT). Hard exit 19:30 UTC = 15:30 ET.
ENTRY = _t(13, 30)
HARD = _t(19, 30)


def test_tp_hit():
    bars = [
        _bar(13, 30, 1.00, 1.10, 0.95, 1.05),
        _bar(13, 31, 1.05, 2.10, 1.00, 2.00),
    ]
    g = grade_from_series(bars, ENTRY, HARD)
    assert g["result"] == "TP"
    assert g["paid"] == 1.00
    assert g["exit"] == 2.00          # exit AT the TP level
    assert g["pnl_pct"] == 100.0
    assert g["exit_time"] == _t(13, 31)


def test_sl_hit():
    bars = [
        _bar(13, 30, 1.00, 1.05, 0.95, 1.00),
        _bar(13, 31, 0.90, 0.95, 0.48, 0.60),
    ]
    g = grade_from_series(bars, ENTRY, HARD)
    assert g["result"] == "SL"
    assert g["exit"] == 0.50
    assert g["pnl_pct"] == -50.0


def test_sl_before_tp_same_bar():
    # Both levels breached in one bar -> pessimistic SL
    bars = [
        _bar(13, 30, 1.00, 1.00, 1.00, 1.00),
        _bar(13, 31, 1.00, 2.50, 0.40, 2.00),
    ]
    g = grade_from_series(bars, ENTRY, HARD)
    assert g["result"] == "SL"


def test_gap_open_below_sl_fills_at_open():
    bars = [
        _bar(13, 30, 1.00, 1.05, 0.95, 1.00),
        _bar(13, 40, 0.30, 0.35, 0.25, 0.30),   # gapped through the -50% level
    ]
    g = grade_from_series(bars, ENTRY, HARD)
    assert g["result"] == "SL"
    assert g["exit"] == 0.30                     # open fill, worse than 0.50
    assert g["pnl_pct"] == -70.0


def test_gap_open_above_tp_fills_at_open():
    bars = [
        _bar(13, 30, 1.00, 1.05, 0.95, 1.00),
        _bar(13, 40, 2.40, 2.60, 2.30, 2.50),
    ]
    g = grade_from_series(bars, ENTRY, HARD)
    assert g["result"] == "TP"
    assert g["exit"] == 2.40                     # open fill, better than 2.00


def test_hard_exit_at_bar_open():
    bars = [
        _bar(13, 30, 1.00, 1.20, 0.90, 1.10),
        _bar(19, 29, 1.10, 1.15, 1.05, 1.12),
        _bar(19, 30, 1.15, 1.30, 1.10, 1.25),   # first bar at/after hard exit
        _bar(19, 31, 1.25, 3.00, 0.10, 2.00),   # must be ignored
    ]
    g = grade_from_series(bars, ENTRY, HARD)
    assert g["result"] == "EXPIRED"
    assert g["exit"] == 1.15
    assert g["exit_time"] == _t(19, 30)


def test_data_end_before_hard_exit():
    bars = [
        _bar(13, 30, 1.00, 1.20, 0.90, 1.10),
        _bar(14, 0, 1.10, 1.25, 1.05, 1.20),
    ]
    g = grade_from_series(bars, ENTRY, HARD)
    assert g["result"] == "DATA_END"
    assert g["exit"] == 1.20                     # last close
    assert round(g["pnl_pct"], 1) == 20.0


def test_no_bars_after_entry_returns_none():
    bars = [_bar(13, 0, 1.00, 1.05, 0.95, 1.00)]
    assert grade_from_series(bars, ENTRY, HARD) is None
    assert grade_from_series([], ENTRY, HARD) is None


def test_bars_before_entry_ignored():
    bars = [
        _bar(13, 0, 5.00, 5.00, 0.01, 5.00),    # pre-entry crash — irrelevant
        _bar(13, 30, 1.00, 1.05, 0.95, 1.00),
        _bar(13, 31, 1.00, 2.10, 0.90, 2.00),
    ]
    g = grade_from_series(bars, ENTRY, HARD)
    assert g["paid"] == 1.00
    assert g["result"] == "TP"


def test_explicit_entry_price_override():
    bars = [
        _bar(13, 30, 1.00, 1.05, 0.95, 1.00),
        _bar(13, 31, 1.00, 1.65, 0.90, 1.60),
    ]
    # paid 0.80 -> TP at 1.60
    g = grade_from_series(bars, ENTRY, HARD, entry_price=0.80)
    assert g["paid"] == 0.80
    assert g["result"] == "TP"
    assert g["exit"] == 1.60


def test_costs_widen_levels_and_reduce_proceeds():
    # paid = 1.00 + 0.10; TP level on paid; sell side pays cost too
    bars = [
        _bar(13, 30, 1.00, 1.05, 0.95, 1.00),
        _bar(13, 31, 1.00, 2.40, 0.95, 2.30),   # net high 2.30 >= 2.20 TP
    ]
    g = grade_from_series(bars, ENTRY, HARD, cost_per_side=0.10)
    assert g["paid"] == 1.10
    assert g["result"] == "TP"
    assert g["exit"] == 2.20
    assert round(g["pnl_pct"], 1) == 100.0


def test_custom_tp_sl_mults():
    bars = [
        _bar(13, 30, 1.00, 1.00, 1.00, 1.00),
        _bar(13, 31, 1.00, 1.55, 0.95, 1.50),
    ]
    g = grade_from_series(bars, ENTRY, HARD, tp_mult=1.5, sl_mult=0.6)
    assert g["result"] == "TP"
    assert g["exit"] == 1.50


def test_bars_from_arrays_parses_and_sorts():
    data = {"time": ["2026-07-01T13:31:00Z", "2026-07-01T13:30:00Z"],
            "open": [1.05, 1.00], "high": [1.10, 1.02],
            "low": [1.00, 0.99], "close": [1.08, 1.01]}
    bars = bars_from_arrays(data)
    assert [b["time"].minute for b in bars] == [30, 31]
    assert bars[0]["o"] == 1.00 and bars[1]["h"] == 1.10
    assert bars[0]["time"].tzinfo is not None


def test_hard_exit_utc_0dte_and_1dte():
    # 2026-07-01 is a Wednesday, EDT (UTC-4)
    entry = datetime(2026, 7, 1, 14, 0, tzinfo=timezone.utc)
    h0 = hard_exit_utc(entry, dte=0)
    assert h0 == datetime(2026, 7, 1, 19, 30, tzinfo=timezone.utc)   # 15:30 ET
    h1 = hard_exit_utc(entry, dte=1)
    assert h1 == datetime(2026, 7, 2, 18, 0, tzinfo=timezone.utc)    # 14:00 ET next day
    # Friday entry -> 1DTE hard exit rolls over the weekend to Monday
    fri = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    assert hard_exit_utc(fri, dte=1).date().isoformat() == "2026-07-13"


def test_series_fit_stats():
    real = [1.0, 2.0, 4.0]
    model = [1.1, 2.2, 4.4]                      # model 10% rich everywhere
    s = series_fit_stats(real, model)
    assert round(s["median_ratio"], 2) == 1.10   # model / real
    assert s["n"] == 3
    assert round(s["mae_pct"], 0) == 10.0
    assert series_fit_stats([], []) == {"n": 0}
