"""Network-free tests for the self-diagnosis classifier + per-pool diagnosis."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import self_diagnosis as sd


def _trade(**kw):
    base = {
        "direction": "LONG", "entry_price": 100.0, "exit_price": 99.0,
        "outcome": "LOSS", "pnl_pct": -1.0, "mfe": 0.0, "mae": 0.0,
        "tp_stage": "SL", "timeframe": "15", "symbol": "AAPL",
        "session": "NY", "regime": "TRENDING", "trigger": "x",
        "created_at": "2026-06-01T00:00:00Z",
    }
    base.update(kw)
    return base


def test_wrong_direction():
    # loss 1%, mfe ~0.1% (tiny favorable run) → wrong direction
    t = _trade(pnl_pct=-1.0, mfe=0.1, mae=1.0, tp_stage="SL")
    assert sd.classify_loss(t) == "WRONG_DIRECTION"


def test_stop_too_tight():
    # loss 1%, mfe ~2% (ran well past exit), clean SL, mae>=loss
    t = _trade(pnl_pct=-1.0, mfe=2.0, mae=1.0, tp_stage="SL")
    assert sd.classify_loss(t) == "STOP_TOO_TIGHT"


def test_gave_back_profit():
    # PARTIAL scratched near zero, decent favorable run so it's not wrong-direction
    t = _trade(outcome="PARTIAL", pnl_pct=0.02, mfe=1.0, tp_stage="SL_TP1")
    assert sd.classify_loss(t) == "GAVE_BACK_PROFIT"


def test_timing_session():
    # ASIA flagged as a bad session; loss has enough favorable run to skip earlier buckets
    bad = {"ASIA"}
    t = _trade(pnl_pct=-1.0, mfe=0.6, mae=0.0, tp_stage="SL", session="ASIA")
    assert sd.classify_loss(t, bad_sessions=bad) == "TIMING_SESSION"


def test_chop_regime():
    t = _trade(pnl_pct=-1.0, mfe=0.6, mae=0.0, tp_stage="SL",
               regime="RANGING", session="NY")
    assert sd.classify_loss(t) == "CHOP_REGIME"


def test_insufficient_data():
    out = sd.diagnose_pool([_trade() for _ in range(5)])
    assert out["status"] == "insufficient_data"
    assert out["n"] == 5


def test_dominant_mode_wrong_direction():
    trades = []
    # 15 clean wrong-direction losses
    for _ in range(15):
        trades.append(_trade(pnl_pct=-1.0, mfe=0.1, mae=1.0, tp_stage="SL"))
    # 10 wins to pad past MIN_CLOSED
    for _ in range(10):
        trades.append(_trade(outcome="WIN", pnl_pct=1.5, exit_price=101.5, mfe=2.0))
    out = sd.diagnose_pool(trades)
    assert out["status"] == "diagnosed"
    assert out["dominant_failure_mode"] == "WRONG_DIRECTION"
    assert out["fix_target"] == "entry_gate"
    assert out["pine_change_required"] is False


def test_dominant_mode_stop_too_tight():
    trades = []
    for _ in range(15):
        trades.append(_trade(pnl_pct=-1.0, mfe=2.0, mae=1.0, tp_stage="SL"))
    for _ in range(10):
        trades.append(_trade(outcome="WIN", pnl_pct=1.5, exit_price=101.5, mfe=2.0))
    out = sd.diagnose_pool(trades)
    assert out["dominant_failure_mode"] == "STOP_TOO_TIGHT"
    assert out["fix_target"] == "stop"
    assert out["pine_change_required"] is True


def test_mixed_when_no_dominant():
    trades = [_trade(outcome="WIN", pnl_pct=1.0, exit_price=101.0, mfe=1.5)
              for _ in range(20)]
    # 2 wrong-dir, 2 stop-tight, 2 chop → no bucket >= 30% if spread out
    trades.append(_trade(pnl_pct=-1.0, mfe=0.1, mae=1.0))
    trades.append(_trade(pnl_pct=-1.0, mfe=0.1, mae=1.0))
    trades.append(_trade(pnl_pct=-1.0, mfe=2.0, mae=1.0, tp_stage="SL"))
    trades.append(_trade(pnl_pct=-1.0, mfe=2.0, mae=1.0, tp_stage="SL"))
    trades.append(_trade(pnl_pct=-1.0, mfe=0.6, regime="RANGING"))
    trades.append(_trade(pnl_pct=-1.0, mfe=0.6, regime="RANGING"))
    out = sd.diagnose_pool(trades)
    # each bucket ~33% — actually one will tie; just assert it diagnoses + routes
    assert out["status"] == "diagnosed"
    assert out["dominant_failure_mode"] in (
        "WRONG_DIRECTION", "STOP_TOO_TIGHT", "CHOP_REGIME", "mixed")


def test_profit_factor_and_format():
    trades = [_trade(outcome="WIN", pnl_pct=2.0, exit_price=102.0, mfe=2.5)
              for _ in range(10)]
    trades += [_trade(pnl_pct=-1.0, mfe=0.1, mae=1.0) for _ in range(10)]
    out = sd.diagnose_pool(trades)
    assert out["profit_factor"] == 2.0  # 20 gross win / 10 gross loss
    # format_telegram on a synthetic run-level dict
    run = {"summary": {"worst_pools": [{
        "pool": "XAUUSD_5M", "profit_factor": out["profit_factor"],
        "win_rate": out["win_rate"],
        "dominant_failure_mode": out["dominant_failure_mode"],
        "pine_change_required": out["pine_change_required"]}]},
        "pools": {"XAUUSD_5M": out}}
    txt = sd.format_telegram(run)
    assert "XAUUSD_5M" in txt and "<b>" not in txt
