"""
Integration tests for ML pipeline additions:
  - score_entry_gate full flow (mock features + history)
  - expectancy threshold (Neyman-Pearson formula)
  - memory features (rolling history)
  - champion-challenger rollback
  - mistake ledger (mocked GitHub)
  - RF/GBM feature selection (top-8 correlation)
  - JointGoldGBM / JointStocksGBM training + predict
  - TabPFNEnsemble fit + predict
  - warm-start transfer (LightGBM init_model)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GITHUB_TOKEN",  "test")
os.environ.setdefault("GITHUB_REPO",   "test/test")
os.environ.setdefault("GITHUB_BRANCH", "data")

import numpy as np

# ── Helpers ────────────────────────────────────────────────────────────────────

def assert_eq(label, got, expected):
    assert got == expected, f"FAIL [{label}]: got {got!r}, expected {expected!r}"
    print(f"  PASS  {label}")

def assert_true(label, condition, msg=""):
    assert condition, f"FAIL [{label}]: {msg}"
    print(f"  PASS  {label}")

def assert_range(label, val, lo, hi):
    assert lo <= val <= hi, f"FAIL [{label}]: {val} not in [{lo}, {hi}]"
    print(f"  PASS  {label}  ({val:.4f})")


def _make_history(n_win: int, n_loss: int, pnl_win=1.5, pnl_loss=1.0) -> list[dict]:
    """Build synthetic trade history with consistent feature vectors."""
    from ml_model import FEATURE_NAMES
    rows = []
    for i in range(n_win):
        row = {name: float((i % 10 + 1) * 0.1) for name in FEATURE_NAMES}
        row.update({"outcome": "WIN", "ml_outcome": "WIN",
                    "pnl_pct": pnl_win, "created_at": "2026-01-01T09:00:00+00:00",
                    "direction": "LONG", "session": "london", "trigger": "BOS"})
        rows.append(row)
    for i in range(n_loss):
        row = {name: float((i % 10 + 1) * 0.05) for name in FEATURE_NAMES}
        row.update({"outcome": "LOSS", "ml_outcome": "LOSS",
                    "pnl_pct": -pnl_loss, "created_at": "2026-01-01T14:00:00+00:00",
                    "direction": "SHORT", "session": "ny", "trigger": "FVG"})
        rows.append(row)
    return rows


# ── 1. Expectancy threshold ────────────────────────────────────────────────────

def test_expectancy_threshold():
    print("\n[1] compute_expectancy_threshold")
    from signal_engine import compute_expectancy_threshold, ML_GATE_THRESHOLD

    # Fewer than 30 closed → fall back to default
    small = _make_history(5, 5)
    thresh = compute_expectancy_threshold("XAUUSD_2M", small)
    assert_eq("n<30 → ML_GATE_THRESHOLD", thresh, ML_GATE_THRESHOLD)

    # 30+ trades — avg_win=1.5, avg_loss=1.0 → optimal = 1/(1+1.5) ≈ 0.4
    history = _make_history(20, 20, pnl_win=1.5, pnl_loss=1.0)
    thresh2 = compute_expectancy_threshold("XAUUSD_2M", history)
    assert_range("balanced R:R clamps to [0.30,0.65]", thresh2, 0.30, 0.65)
    # Formula: 1/(1+1.5) = 0.4
    assert_range("balanced R:R ≈ 0.40", thresh2, 0.38, 0.42)

    # Very high R:R (5:1 wins): optimal = 1/6 ≈ 0.167 → clamped to 0.30
    high_rr = _make_history(20, 20, pnl_win=5.0, pnl_loss=1.0)
    thresh3 = compute_expectancy_threshold("XAUUSD_2M", high_rr)
    assert_eq("high R:R clamped at 0.30", thresh3, 0.30)

    # Very poor R:R (1:5): optimal = 1/(1+0.2) ≈ 0.833 → clamped to 0.65
    low_rr = _make_history(20, 20, pnl_win=0.5, pnl_loss=2.5)
    thresh4 = compute_expectancy_threshold("XAUUSD_2M", low_rr)
    assert_eq("low R:R clamped at 0.65", thresh4, 0.65)


# ── 2. Memory features ─────────────────────────────────────────────────────────

def test_memory_features():
    print("\n[2] _memory_features")
    from signal_engine import _memory_features

    # Empty history → defaults
    feats = _memory_features([], "LONG")
    assert_eq("empty history length", len(feats), 5)
    assert_eq("empty overall=0.5", feats[0], 0.5)
    assert_eq("empty streak=0", feats[4], 0.0)

    # All wins, LONG direction
    wins = [{"outcome": "WIN", "direction": "LONG", "session": "london", "trigger": "BOS"}] * 10
    feats2 = _memory_features(wins, "LONG")
    assert_eq("all wins: overall=1.0", feats2[0], 1.0)
    assert_eq("all wins: same_dir=1.0", feats2[1], 1.0)
    assert_eq("all wins: streak=0", feats2[4], 0.0)

    # Loss streak detection
    losses = [{"outcome": "LOSS", "direction": "SHORT", "session": "ny", "trigger": "FVG"}] * 8
    feats3 = _memory_features(losses, "SHORT")
    assert_eq("8 losses: overall=0.0", feats3[0], 0.0)
    # streak = 8 → capped at 8 → streak_norm = 8/8 = 1.0
    assert_eq("8-loss streak: streak_norm=1.0", feats3[4], 1.0)

    # Mixed: most recent 3 = losses (history[0] = most recent), then 7 wins
    # _memory_features takes history[:n] so losses must come first in the list
    mixed = ([{"outcome": "LOSS", "direction": "LONG", "session": "london", "trigger": "BOS"}] * 3 +
             [{"outcome": "WIN", "direction": "LONG", "session": "london", "trigger": "BOS"}] * 7)
    feats4 = _memory_features(mixed, "LONG", n=10)
    assert_range("mixed: streak_norm 3/8", feats4[4], 0.37, 0.39)


# ── 3. RF/GBM feature selection ────────────────────────────────────────────────

def test_feature_selection():
    print("\n[3] RF/GBM feature selection")
    from ml_ensemble import RandomForestEnsemble, GradientBoostEnsemble, FEATURE_NAMES

    history = _make_history(60, 60)

    rf = RandomForestEnsemble()
    ok = rf.retrain(history)
    assert_true("RF trains on 120 trades", ok)
    assert_eq("RF selects 8 features at n≥80", len(rf._feature_indices), 8)
    assert_true("RF feature_indices in range",
                all(0 <= i < len(FEATURE_NAMES) for i in rf._feature_indices))

    gbm = GradientBoostEnsemble()
    ok2 = gbm.train(history)
    assert_true("GBM trains on 120 trades", ok2)
    assert_eq("GBM selects 8 features at n≥80", len(gbm._feature_indices), 8)

    # At n<80: all 25 features used
    small = _make_history(30, 30)
    rf2 = RandomForestEnsemble()
    ok3 = rf2.retrain(small)
    assert_true("RF trains on 60 trades", ok3)
    assert_eq("RF uses all 25 features at n<80", len(rf2._feature_indices), 25)


# ── 4. Champion-challenger rollback ─────────────────────────────────────────────

def test_champion_challenger_rollback():
    print("\n[4] Champion-challenger rollback")
    from ml_ensemble import RandomForestEnsemble

    history = _make_history(60, 60)
    rf = RandomForestEnsemble()
    rf.retrain(history)
    assert_true("model trained", rf.is_trained)

    # First rollback: prev_model is None (only trained once)
    result = rf.rollback()
    assert_eq("first rollback returns False (no prev)", result, False)

    # Retrain again — now prev_model is set
    rf.retrain(history)
    result2 = rf.rollback()
    assert_eq("second rollback returns True", result2, True)
    assert_true("still trained after rollback", rf.is_trained)


# ── 5. Mistake ledger (mocked GitHub) ─────────────────────────────────────────

def test_mistake_ledger():
    print("\n[5] Mistake ledger")
    import unittest.mock as mock

    with mock.patch("db._get_file", return_value=([], "sha_abc")), \
         mock.patch("db._put_file") as mock_put:

        from db import log_mistake
        trade = {
            "pool": "XAUUSD_2M", "outcome": "LOSS",
            "direction": "LONG", "session": "asian",
            "trigger": "BOS", "pnl_pct": -1.2,
            "f3_atr": 0.85,  # High ATR → volatile
            "created_at": "2026-01-01T04:30:00+00:00",
        }
        log_mistake(trade)
        assert_true("log_mistake calls _put_file", mock_put.called)
        put_args = mock_put.call_args[0]
        saved = put_args[1]
        assert_true("saved is list", isinstance(saved, list))
        entry = saved[-1]
        assert_true("entry has cause_tags", "cause_tags" in entry)
        assert_true("pool stored", entry.get("pool") == "XAUUSD_2M")
        # Volatile session (asian) + high ATR should both be tagged
        cause_tags = entry["cause_tags"]
        assert_true("off_hours tag present",
                    any("off_hours" in t or "asian" in t or "session" in t for t in cause_tags),
                    f"tags={cause_tags}")


# ── 6. JointGoldGBM ────────────────────────────────────────────────────────────

def test_joint_gold_gbm():
    print("\n[6] JointGoldGBM")
    from ml_ensemble import JointGoldGBM, GOLD_TF_IDS

    pool_histories = {
        "XAUUSD_2M":  _make_history(40, 40),
        "XAUUSD_5M":  _make_history(20, 20),
        "XAUUSD_30M": _make_history(15, 15),
        "XAUUSD_1H":  _make_history(10, 10),
    }

    jm = JointGoldGBM()
    assert_eq("not trained initially", jm.is_trained, False)

    ok = jm.train(pool_histories)
    assert_true("JointGoldGBM trains", ok)
    assert_eq("is_trained after train()", jm.is_trained, True)
    assert_eq("trained count", jm._n_trained, 170)  # 80+40+30+20

    from ml_model import FEATURE_NAMES
    feat = [0.5] * len(FEATURE_NAMES)
    for pool in GOLD_TF_IDS:
        p = jm.predict(feat, pool)
        assert_range(f"predict {pool} in [0,1]", p, 0.0, 1.0)

    # Unknown pool → 0.5
    p_unk = jm.predict(feat, "UNKNOWN_POOL")
    assert_eq("unknown pool → 0.5", p_unk, 0.5)

    # Empty histories → graceful failure
    jm2 = JointGoldGBM()
    ok2 = jm2.train({})
    assert_eq("empty histories → False", ok2, False)


# ── 7. JointStocksGBM ─────────────────────────────────────────────────────────

def test_joint_stocks_gbm():
    print("\n[7] JointStocksGBM")
    from ml_ensemble import JointStocksGBM, STOCK_POOL_IDS

    pool_histories = {
        "STOCKS_MOMENTUM_15M": _make_history(20, 20),
        "STOCKS_MOMENTUM_30M": _make_history(15, 15),
        "STOCKS_QUALITY_30M":  _make_history(15, 15),
        "STOCKS_INDEX_30M":    _make_history(10, 10),
    }

    jm = JointStocksGBM()
    ok = jm.train(pool_histories)
    assert_true("JointStocksGBM trains", ok)
    assert_eq("is_trained", jm.is_trained, True)

    from ml_model import FEATURE_NAMES
    feat = [0.4] * len(FEATURE_NAMES)
    for pool in ["STOCKS_MOMENTUM_15M", "STOCKS_QUALITY_30M"]:
        p = jm.predict(feat, pool)
        assert_range(f"predict {pool} in [0,1]", p, 0.0, 1.0)

    # Gold pool → 0.5 (not a stock)
    p_gold = jm.predict(feat, "XAUUSD_2M")
    assert_eq("gold pool → 0.5", p_gold, 0.5)


# ── 8. TabPFNEnsemble ─────────────────────────────────────────────────────────

def test_tabpfn_ensemble():
    print("\n[8] TabPFNEnsemble")
    from ml_ensemble import TabPFNEnsemble, _TABPFN_AVAILABLE, FEATURE_NAMES

    if not _TABPFN_AVAILABLE:
        print("  SKIP  TabPFN not installed")
        return

    tab = TabPFNEnsemble()
    assert_eq("not trained initially", tab.is_trained, False)

    # Below min n
    ok = tab.fit(_make_history(3, 3))
    assert_eq("n<10 → fit returns False", ok, False)

    # Good history
    history = _make_history(25, 25)
    ok2 = tab.fit(history)
    from ml_ensemble import _TABPFN_AVAILABLE as _tfav
    if not _tfav:
        print("  SKIP  TabPFN model download requires HF_TOKEN — skipping inference tests")
        return
    assert_true("fit with 50 trades succeeds", ok2)
    assert_eq("is_trained after fit", tab.is_trained, True)
    assert_eq("last_n tracked", tab._last_n, 50)

    feat = [0.5] * len(FEATURE_NAMES)
    p = tab.predict(feat)
    assert_range("predict in [0,1]", p, 0.0, 1.0)

    # fit_if_stale — same n → no re-fit (last_n unchanged)
    tab._last_n = 50
    result = tab.fit_if_stale(history)  # same len
    assert_true("fit_if_stale same n → returns True (already trained)", result)


# ── 9. Warm-start transfer ────────────────────────────────────────────────────

def test_warm_start_transfer():
    print("\n[9] Warm-start transfer")
    from ml_ensemble import train_with_warm_start, _LGBM_AVAILABLE, FEATURE_NAMES

    if not _LGBM_AVAILABLE:
        print("  SKIP  lightgbm not installed")
        return

    source = _make_history(80, 80)  # n=160 (XAUUSD_2M equivalent)
    target = _make_history(20, 20)  # n=40 (thin pool)

    model = train_with_warm_start(source, target)
    assert_true("warm-start returns a model", model is not None)

    feat = np.array([[0.5] * len(FEATURE_NAMES)], dtype=np.float32)
    proba = model.predict_proba(feat)[0]
    assert_range("transfer model predict in [0,1]", float(max(proba)), 0.0, 1.0)

    # Too few trades → None
    model2 = train_with_warm_start([], _make_history(3, 3))
    assert_eq("empty source → None", model2, None)


# ── 10. score_entry_gate cold-start bypass ────────────────────────────────────

def test_score_entry_gate_cold_start():
    print("\n[10] score_entry_gate cold-start bypass")
    import unittest.mock as mock
    import signal_engine as se

    # Ensure no features cached for this pool
    se._latest_features.pop("__TEST_POOL__", None)
    result = se.score_entry_gate("__TEST_POOL__", "LONG")
    assert_eq("no features → pass=True", result["pass"], True)
    assert_eq("reason is no_features_cached", result["reason"], "no_features_cached")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_expectancy_threshold,
        test_memory_features,
        test_feature_selection,
        test_champion_challenger_rollback,
        test_mistake_ledger,
        test_joint_gold_gbm,
        test_joint_stocks_gbm,
        test_tabpfn_ensemble,
        test_warm_start_transfer,
        test_score_entry_gate_cold_start,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"\n  FAIL  {e}")
            failed.append(t.__name__)
        except Exception as e:
            import traceback
            print(f"\n  CRASH {t.__name__}: {e}")
            traceback.print_exc()
            failed.append(t.__name__)

    print(f"\n{'='*50}")
    if failed:
        print(f"FAILED {len(failed)}/{len(tests)} tests: {failed}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} TESTS PASSED")
        sys.exit(0)
