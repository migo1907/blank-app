"""
Tests for ladder_backtest — replication of the deployed Pine Script exit
ladder (migo_sniper_f26.pine) so real IBKR bars can grade it.

The simulator must match the Pine state machine EXACTLY:
  - Entry on bar close; exits evaluated from the NEXT bar (Pine's exit block
    runs before the entry block sets activeTrade).
  - Per bar order: trail update (uses current bar high/low) -> TP1 -> TP2 ->
    TP3 (full exit) -> SL check.
  - TP1 hit: trail ON at close -/+ atr*1.2, floored/capped at entry
    (break-even guarantee). After TP2: tighter trail (atrMultTrl2).
  - SL before TP1 = LOSS. SL after TP1/TP2 = PARTIAL (trailed exit).
  - Single position, all-in/all-out (Pine does not scale out).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ladder_backtest import (TF_LADDERS, TRAIL_TP1, wilder_atr,
                             simulate_ladder, run_grid, summarize_trades)


def _bars(rows):
    return [{"o": o, "h": h, "l": l, "c": c} for o, h, l, c in rows]


def _flat(n, px=100.0, rng=1.0):
    """n flat bars with constant true range -> ATR converges to rng."""
    return _bars([(px, px + rng / 2, px - rng / 2, px)] * n)


def test_deployed_ladder_table():
    # Must stay in lockstep with migo_sniper_f26.pine autoTF block
    assert TF_LADDERS["2m"] == {"tp1": 1.0, "tp2": 1.8, "tp3": 3.0, "sl": 0.8, "trail2": 0.5}
    assert TF_LADDERS["5m"] == {"tp1": 1.5, "tp2": 2.5, "tp3": 4.0, "sl": 1.5, "trail2": 0.7}
    assert TF_LADDERS["30m"] == {"tp1": 2.2, "tp2": 3.8, "tp3": 6.0, "sl": 2.2, "trail2": 1.0}
    assert TF_LADDERS["1h"] == {"tp1": 2.5, "tp2": 4.5, "tp3": 7.0, "sl": 2.5, "trail2": 1.2}
    assert TRAIL_TP1 == 1.2


def test_wilder_atr():
    bars = _flat(50, px=100.0, rng=2.0)
    atr = wilder_atr(bars, period=14)
    assert atr[0] is None and atr[12] is None      # warmup
    assert atr[13] is not None
    assert abs(atr[-1] - 2.0) < 1e-6               # constant TR -> ATR = TR
    assert len(atr) == len(bars)


def test_immediate_stop_loss_is_minus_one_r():
    bars = _flat(20, px=100.0, rng=1.0)
    # entry bar, then a crash bar through the SL (sl mult 0.8 -> ~99.23)
    bars += _bars([(100, 100.2, 99.7, 100.0),      # i=20 entry (ATR ~0.964)
                   (99.9, 99.9, 98.0, 98.2)])      # SL
    t = simulate_ladder(bars, wilder_atr(bars), 20, "LONG", TF_LADDERS["2m"])
    assert t["outcome"] == "LOSS"
    assert t["stage"] == "SL"
    assert abs(t["r"] + 1.0) < 1e-6                # exit exactly at -1R
    assert t["bars_held"] == 1


def test_full_run_tp3():
    bars = _flat(20, px=100.0, rng=1.0)
    # 2m ladder from entry 100 (ATR ~0.964 after the 0.5-range entry bar):
    # TP1 ~100.96, TP2 ~101.74, TP3 ~102.89, SL ~99.23. Bars are chosen so the
    # post-TP1/TP2 trail (which uses the CURRENT bar extreme) never triggers.
    bars += _bars([(100, 100.2, 99.7, 100.0),      # i=20 entry
                   (100.3, 101.1, 100.2, 101.0),   # TP1
                   (101.6, 101.9, 101.6, 101.85),  # TP2 (narrow bar clears trail)
                   (102, 103.2, 101.8, 103.0)])    # TP3
    t = simulate_ladder(bars, wilder_atr(bars), 20, "LONG", TF_LADDERS["2m"])
    assert t["outcome"] == "WIN"
    assert t["stage"] == "TP3"
    assert t["tp1_hit"] and t["tp2_hit"]
    # exit booked at the TP3 level (conservative), r = 3.0/0.8
    assert abs(t["r"] - 3.0 / 0.8) < 1e-6


def test_breakeven_guarantee_after_tp1():
    bars = _flat(20, px=100.0, rng=1.0)
    # TP1 hits, close well above -> trail = max(close - 1.2*atr, entry) = entry
    bars += _bars([(100, 100.2, 99.8, 100.0),      # i=20 entry
                   (100, 101.1, 100.0, 100.9),     # TP1 hit, trail -> 100.0
                   (100.5, 100.6, 99.0, 99.1)])    # collapse through entry
    t = simulate_ladder(bars, wilder_atr(bars), 20, "LONG", TF_LADDERS["2m"])
    assert t["outcome"] == "PARTIAL"
    assert t["stage"] == "SL_TP1"
    assert t["exit"] >= t["entry"]                 # never worse than breakeven
    assert t["r"] >= 0.0


def test_same_bar_tp1_then_trail_stop():
    bars = _flat(20, px=100.0, rng=1.0)
    # One bar spikes to TP1 then collapses: Pine sets tp1Hit and the trail in
    # the same block, then the SL check sees low <= trailSL -> PARTIAL.
    bars += _bars([(100, 100.2, 99.8, 100.0),          # i=20 entry
                   (100, 101.2, 99.0, 99.0)])          # TP1 + collapse
    t = simulate_ladder(bars, wilder_atr(bars), 20, "LONG", TF_LADDERS["2m"])
    assert t["outcome"] == "PARTIAL"
    assert t["stage"] == "SL_TP1"
    assert t["exit"] >= t["entry"]                     # breakeven floor held


def test_short_symmetry():
    bars = _flat(20, px=100.0, rng=1.0)
    bars += _bars([(100, 100.2, 99.7, 100.0),      # i=20 entry SHORT
                   (99.8, 99.8, 98.9, 99.0),       # TP1 (~99.04)
                   (98.3, 98.35, 98.2, 98.25),     # TP2 (~98.26, narrow bar)
                   (98.2, 98.4, 97.0, 97.2)])      # TP3 (~97.11)
    t = simulate_ladder(bars, wilder_atr(bars), 20, "SHORT", TF_LADDERS["2m"])
    assert t["outcome"] == "WIN" and t["stage"] == "TP3"


def test_timeout_exits_at_close():
    bars = _flat(20, px=100.0, rng=1.0) + _flat(10, px=100.0, rng=0.2)
    t = simulate_ladder(bars, wilder_atr(bars), 20, "LONG", TF_LADDERS["2m"],
                        max_bars=5)
    assert t["outcome"] == "TIMEOUT"
    assert t["bars_held"] == 5


def test_no_entry_without_atr():
    bars = _flat(5)
    assert simulate_ladder(bars, wilder_atr(bars), 2, "LONG", TF_LADDERS["2m"]) is None


def test_run_grid_and_summary():
    bars = _flat(120, px=100.0, rng=1.0)
    trades = run_grid(bars, "2m", every=10, max_bars=20)
    assert len(trades) > 0
    assert all(t["direction"] in ("LONG", "SHORT") for t in trades)
    s = summarize_trades(trades)
    assert s["n"] == len(trades)
    assert "avg_r" in s and "outcomes" in s


def test_scrub_bad_prints():
    from ladder_backtest import scrub_bad_prints
    rows = [(100, 100.5, 99.5, 100.0)] * 60
    bars = _bars(rows)
    # inject a bad print: open/high spike +10% that reverts within the bar
    bars[30] = {"o": 110.0, "h": 110.0, "l": 99.5, "c": 100.0}
    clean, dropped = scrub_bad_prints(bars)
    assert dropped == 1
    assert len(clean) == 59
    assert all(b["h"] < 105 for b in clean)
    # a REAL gap (price jumps and STAYS at the new level) must be kept
    bars2 = _bars(rows[:30] + [(102, 102.5, 101.5, 102.0)] * 30)
    clean2, dropped2 = scrub_bad_prints(bars2)
    assert dropped2 == 0 and len(clean2) == 60
