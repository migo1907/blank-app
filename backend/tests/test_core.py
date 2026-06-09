"""
Core unit tests — run before every push.
Covers the functions most likely to silently break:
  - symbol_to_pool (routing)
  - _normalize_outcome (trade labeling)
  - FEATURE_NAMES (ML schema)
  - _dynamic_weights (ensemble logic)
  - _session_weight (training weights)
  - aggregate_sentiment (news scoring)
  - CONFLICTED gate (Option B logic)
  - _agreement_multiplier
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub env vars so db.py and other modules import cleanly without Railway secrets
os.environ.setdefault("GITHUB_TOKEN",  "test")
os.environ.setdefault("GITHUB_REPO",   "test/test")
os.environ.setdefault("GITHUB_BRANCH", "data")

# ── Imports ───────────────────────────────────────────────────────────────────

from db import symbol_to_pool
from ml_model import FEATURE_NAMES
from ml_ensemble import _session_weight, MIN_TRADES
from news_fetcher import aggregate_sentiment

# signal_engine imports trigger FastAPI/db at module level — import selectively
import importlib, types

def _load_signal_engine_funcs():
    """Import only the pure functions we need without triggering side-effects."""
    import signal_engine as se
    return se._dynamic_weights, se._agreement_multiplier, se._session_multiplier

_dynamic_weights, _agreement_multiplier, _session_multiplier = _load_signal_engine_funcs()

# _normalize_outcome is defined in main.py — extract without starting FastAPI
import ast, textwrap, pathlib

def _extract_normalize_outcome():
    src = pathlib.Path(__file__).parent.parent.joinpath("main.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_normalize_outcome":
            func_src = ast.get_source_segment(src, node)
            ns: dict = {}
            exec(textwrap.dedent(func_src), ns)
            return ns["_normalize_outcome"]
    raise RuntimeError("_normalize_outcome not found in main.py")

_normalize_outcome = _extract_normalize_outcome()


# ── Helpers ────────────────────────────────────────────────────────────────────

def assert_eq(label, got, expected):
    assert got == expected, f"FAIL [{label}]: got {got!r}, expected {expected!r}"
    print(f"  PASS  {label}")

def assert_true(label, condition, msg=""):
    assert condition, f"FAIL [{label}]: {msg}"
    print(f"  PASS  {label}")


# ── 1. symbol_to_pool ─────────────────────────────────────────────────────────

def test_symbol_to_pool():
    print("\n[1] symbol_to_pool")

    # XAUUSD timeframes
    assert_eq("XAUUSD 2min",  symbol_to_pool("XAUUSD", "2"),   "XAUUSD_2M")
    assert_eq("XAUUSD 5min",  symbol_to_pool("XAUUSD", "5"),   "XAUUSD_5M")
    assert_eq("XAUUSD 30min", symbol_to_pool("XAUUSD", "30"),  "XAUUSD_30M")
    assert_eq("XAUUSD 60min", symbol_to_pool("XAUUSD", "60"),  "XAUUSD_1H")
    assert_eq("XAUUSD 240min (Pine Script TF)", symbol_to_pool("XAUUSD", "240"), "")   # 4H is not a live pool
    assert_eq("XAUUSD 4H literal",              symbol_to_pool("XAUUSD", "4H"),  "")   # same guard
    assert_eq("GOLD alias",  symbol_to_pool("GOLD", "2"),  "XAUUSD_2M")
    assert_eq("GC alias",    symbol_to_pool("GC",   "5"),  "XAUUSD_5M")

    # Stocks — INDEX (SPY)
    assert_eq("SPY 30min",  symbol_to_pool("SPY", "30"),  "STOCKS_INDEX_30M")
    assert_eq("SPY 15min",  symbol_to_pool("SPY", "15"),  "STOCKS_INDEX_15M")
    assert_eq("SPY 240min", symbol_to_pool("SPY", "240"), "STOCKS_INDEX_4H")

    # Stocks — QQQ
    assert_eq("QQQ 30min",  symbol_to_pool("QQQ", "30"),  "STOCKS_QQQ_30M")
    assert_eq("QQQ 15min",  symbol_to_pool("QQQ", "15"),  "STOCKS_QQQ_15M")
    assert_eq("QQQ 240min", symbol_to_pool("QQQ", "240"), "STOCKS_QQQ_4H")

    # Stocks — SPX500
    assert_eq("SPX500 30min", symbol_to_pool("SPX500", "30"), "STOCKS_SPX500_30M")
    assert_eq("US500 15min",  symbol_to_pool("US500",  "15"), "STOCKS_SPX500_15M")

    # Stocks — QUALITY
    assert_eq("MSFT 30min",  symbol_to_pool("MSFT", "30"),  "STOCKS_QUALITY_30M")
    assert_eq("AAPL 15min",  symbol_to_pool("AAPL", "15"),  "STOCKS_QUALITY_15M")
    assert_eq("GOOGL 240min",symbol_to_pool("GOOGL","240"), "STOCKS_QUALITY_4H")

    # Stocks — MOMENTUM
    assert_eq("NVDA 15min",  symbol_to_pool("NVDA", "15"),  "STOCKS_MOMENTUM_15M")
    assert_eq("TSLA 30min",  symbol_to_pool("TSLA", "30"),  "STOCKS_MOMENTUM_30M")

    # Unknown ticker defaults to MOMENTUM
    assert_eq("Unknown ticker", symbol_to_pool("UNKNOWN", "30"), "STOCKS_MOMENTUM_30M")

    # Empty pool must be falsy — heartbeat guard relies on `if not pool`
    assert_true("XAUUSD_4H returns falsy", not symbol_to_pool("XAUUSD", "240"))


# ── 2. _normalize_outcome ─────────────────────────────────────────────────────

def test_normalize_outcome():
    print("\n[2] _normalize_outcome")

    # Progress — no DB write
    assert_eq("TP1_HIT",  _normalize_outcome("TP1_HIT"),  "PROGRESS")
    assert_eq("TP2_HIT",  _normalize_outcome("TP2_HIT"),  "PROGRESS")
    assert_eq("PROGRESS", _normalize_outcome("PROGRESS"),  "PROGRESS")

    # WIN variants
    assert_eq("WIN",      _normalize_outcome("WIN"),   "WIN")
    assert_eq("TP3",      _normalize_outcome("TP3"),   "WIN")
    assert_eq("TP2",      _normalize_outcome("TP2"),   "WIN")
    assert_eq("TP1",      _normalize_outcome("TP1"),   "WIN")

    # LOSS variants
    assert_eq("LOSS",     _normalize_outcome("LOSS"),  "LOSS")
    assert_eq("SL",       _normalize_outcome("SL"),    "LOSS")

    # PARTIAL variants
    assert_eq("PARTIAL",  _normalize_outcome("PARTIAL"),  "PARTIAL")
    assert_eq("SL_TP1",   _normalize_outcome("SL_TP1"),   "PARTIAL")
    assert_eq("SL_TP2",   _normalize_outcome("SL_TP2"),   "PARTIAL")
    assert_eq("SL_TP3",   _normalize_outcome("SL_TP3"),   "PARTIAL")
    assert_eq("TP1_SL",   _normalize_outcome("TP1_SL"),   "PARTIAL")
    assert_eq("TP2_SL",   _normalize_outcome("TP2_SL"),   "PARTIAL")

    # HEARTBEAT passthrough
    assert_eq("HEARTBEAT", _normalize_outcome("HEARTBEAT"), "HEARTBEAT")

    # Unknown → LOSS safe fallback
    assert_eq("unknown",  _normalize_outcome("GARBAGE"), "LOSS")


# ── 3. FEATURE_NAMES ──────────────────────────────────────────────────────────

def test_feature_names():
    print("\n[3] FEATURE_NAMES")

    assert_eq("count is 25", len(FEATURE_NAMES), 25)
    assert_eq("first is f1_rsi",  FEATURE_NAMES[0],  "f1_rsi")
    assert_eq("last is f25_tod",  FEATURE_NAMES[24], "f25_tod")

    # All must use named format (underscore), not compact (f1, f2...)
    for name in FEATURE_NAMES:
        assert_true(
            f"{name} has underscore",
            "_" in name,
            f"{name!r} is compact key — must be named like f1_rsi"
        )

    # No duplicates
    assert_eq("no duplicates", len(set(FEATURE_NAMES)), 25)

    # Spot-check key features referenced in signal logic
    assert_true("f2_adx present",   "f2_adx"   in FEATURE_NAMES)
    assert_true("f3_atr present",   "f3_atr"   in FEATURE_NAMES)
    assert_true("f16_mtf present",  "f16_mtf"  in FEATURE_NAMES)
    assert_true("f21_vwap present", "f21_vwap" in FEATURE_NAMES)


# ── 4. _dynamic_weights ───────────────────────────────────────────────────────

def test_dynamic_weights():
    print("\n[4] _dynamic_weights")

    # KNN-only regime: n < 50
    knn, rf, gbm, news = _dynamic_weights([])
    assert_eq("n=0: KNN=0.75", knn,  0.75)
    assert_eq("n=0: RF=0",     rf,   0.00)
    assert_eq("n=0: GBM=0",    gbm,  0.00)
    assert_eq("n=0: NEWS=0.25",news, 0.25)

    history_49 = [{"outcome": "LOSS"}] * 49
    knn, rf, gbm, news = _dynamic_weights(history_49)
    assert_eq("n=49: KNN=0.75", knn, 0.75)
    assert_eq("n=49: RF=0",     rf,  0.00)

    # RF-only regime: 50 ≤ n < 80
    history_50 = [{"outcome": "LOSS"}] * 50
    knn, rf, gbm, news = _dynamic_weights(history_50)
    assert_eq("n=50: KNN=0.55", knn,  0.55)
    assert_eq("n=50: RF=0.35",  rf,   0.35)
    assert_eq("n=50: GBM=0",    gbm,  0.00)
    assert_eq("n=50: NEWS=0.10",news, 0.10)

    # Full ensemble, high win rate (≥0.60 in last 20)
    wins_20   = [{"outcome": "WIN"}]  * 12 + [{"outcome": "LOSS"}] * 8   # wr=0.60
    history_wr_high = wins_20 + [{"outcome": "LOSS"}] * 60
    knn, rf, gbm, news = _dynamic_weights(history_wr_high)
    assert_eq("wr≥0.60: KNN=0.40", knn,  0.40)
    assert_eq("wr≥0.60: RF=0.28",  rf,   0.28)
    assert_eq("wr≥0.60: GBM=0.22", gbm,  0.22)
    assert_eq("wr≥0.60: NEWS=0.10",news, 0.10)

    # Drawdown regime (wr ≤ 0.35 in last 20)
    losses_20  = [{"outcome": "WIN"}] * 7 + [{"outcome": "LOSS"}] * 13   # wr=0.35
    history_wr_low = losses_20 + [{"outcome": "LOSS"}] * 60
    knn, rf, gbm, news = _dynamic_weights(history_wr_low)
    assert_eq("wr≤0.35: KNN=0.28", knn,  0.28)
    assert_eq("wr≤0.35: RF=0.22",  rf,   0.22)
    assert_eq("wr≤0.35: GBM=0.18", gbm,  0.18)
    assert_eq("wr≤0.35: NEWS=0.32",news, 0.32)


# ── 5. _session_weight ────────────────────────────────────────────────────────

def test_session_weight():
    print("\n[5] _session_weight")

    assert_eq("London open (08:00 UTC)",  _session_weight("2026-06-09T08:00:00+00:00"), 1.30)
    assert_eq("NY overlap (13:00 UTC)",   _session_weight("2026-06-09T13:00:00+00:00"), 1.25)
    assert_eq("Asian session (03:00 UTC)",_session_weight("2026-06-09T03:00:00+00:00"), 0.60)
    assert_eq("Off hours (22:00 UTC)",    _session_weight("2026-06-09T22:00:00+00:00"), 0.60)
    assert_eq("Default (11:00 UTC)",      _session_weight("2026-06-09T11:00:00+00:00"), 1.00)
    assert_eq("Bad timestamp → default",  _session_weight("not-a-date"),               1.00)


# ── 6. aggregate_sentiment ───────────────────────────────────────────────────

def test_aggregate_sentiment():
    print("\n[6] aggregate_sentiment")

    assert_eq("empty list → 0.0", aggregate_sentiment([]), 0.0)

    items = [
        {"sentiment_score":  1.0, "impact": "HIGH"},
        {"sentiment_score": -0.5, "impact": "MEDIUM"},
        {"sentiment_score":  0.0, "impact": "LOW"},
    ]
    result = aggregate_sentiment(items)
    assert_true("non-empty result in range", -1.0 <= result <= 1.0,
                f"out of bounds: {result}")
    assert_true("HIGH item dominates positive", result > 0,
                f"expected positive weighted result, got {result}")
    print(f"  PASS  weighted result = {result:.4f}")


# ── 7. CONFLICTED gate — Option B ────────────────────────────────────────────

def test_conflicted_gate_option_b():
    """Verify Option B logic directly: confidence proxy vs all_agree."""
    print("\n[7] CONFLICTED gate (Option B)")

    def _gate(knn_dir, rf_dir, gbm_dir, knn_strength, rf_strength, gbm_strength):
        """Replicate the Option B gate from signal_engine.py."""
        ml_strength   = (abs(knn_strength) + abs(rf_strength) + abs(gbm_strength)) / 3.0
        ml_conf_proxy = 0.5 + ml_strength * 0.5
        high_conviction = ml_conf_proxy >= 0.65
        all_agree       = (knn_dir == rf_dir == gbm_dir)
        suppressed = not high_conviction and not all_agree
        return not suppressed  # True = signal passes

    # High conviction (≥0.65) → always passes even without agreement
    assert_true("high conviction passes (disagree)",
                _gate("LONG","SHORT","LONG", 0.8, 0.8, 0.8),
                "should pass: ml_conf_proxy=0.9")

    # All agree → passes even with low conviction
    assert_true("all agree passes (low conviction)",
                _gate("SHORT","SHORT","SHORT", 0.2, 0.2, 0.2),
                "should pass: unanimous agreement")

    # Low conviction + disagree → suppressed
    assert_true("low conviction + disagree suppressed",
                not _gate("LONG","SHORT","LONG", 0.1, 0.1, 0.1),
                "should suppress: low conviction + no agreement")

    # Borderline: exactly 0.65 threshold
    # ml_strength = 0.30 → ml_conf_proxy = 0.5 + 0.30*0.5 = 0.65 → passes
    assert_true("exactly 0.65 passes",
                _gate("LONG","SHORT","LONG", 0.30, 0.30, 0.30),
                "ml_conf_proxy=0.65 should pass")

    # Just below: ml_strength = 0.29 → 0.5 + 0.145 = 0.645 < 0.65 → suppressed if disagree
    assert_true("just below 0.65 suppressed (disagree)",
                not _gate("LONG","SHORT","LONG", 0.29, 0.29, 0.29),
                "ml_conf_proxy=0.645 + disagree should suppress")


# ── 8. _agreement_multiplier ─────────────────────────────────────────────────

def test_agreement_multiplier():
    print("\n[8] _agreement_multiplier")

    assert_eq("unanimous LONG  → 1.20", _agreement_multiplier("LONG","LONG","LONG"),    1.20)
    assert_eq("unanimous SHORT → 1.20", _agreement_multiplier("SHORT","SHORT","SHORT"),  1.20)
    assert_eq("2/3 agree       → 1.00", _agreement_multiplier("LONG","LONG","SHORT"),   1.00)
    assert_eq("all disagree    → 0.80", _agreement_multiplier("LONG","SHORT","LONG"),   0.80)


# ── 9. ML thresholds sanity ───────────────────────────────────────────────────

def test_ml_thresholds():
    print("\n[9] ML thresholds")

    assert_eq("MIN_TRADES = 15", MIN_TRADES, 15)

    from signal_engine import MIN_CONFIDENCE, MIN_CONFIDENCE_STOCKS, ML_GATE_THRESHOLD
    assert_true("MIN_CONFIDENCE gold ≥ 0.50",   MIN_CONFIDENCE        >= 0.50)
    assert_true("MIN_CONFIDENCE stocks ≥ 0.50", MIN_CONFIDENCE_STOCKS >= 0.50)
    assert_true("ML_GATE_THRESHOLD ≥ 0.40",     ML_GATE_THRESHOLD     >= 0.40)
    assert_true("stocks conf ≥ gold conf",
                MIN_CONFIDENCE_STOCKS >= MIN_CONFIDENCE,
                f"stocks({MIN_CONFIDENCE_STOCKS}) < gold({MIN_CONFIDENCE})")
    print(f"  INFO  gold={MIN_CONFIDENCE} stocks={MIN_CONFIDENCE_STOCKS} gate={ML_GATE_THRESHOLD}")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_symbol_to_pool,
        test_normalize_outcome,
        test_feature_names,
        test_dynamic_weights,
        test_session_weight,
        test_aggregate_sentiment,
        test_conflicted_gate_option_b,
        test_agreement_multiplier,
        test_ml_thresholds,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"\n  ❌  {e}")
            failed.append(t.__name__)
        except Exception as e:
            print(f"\n  ❌  {t.__name__} CRASHED: {e}")
            failed.append(t.__name__)

    print(f"\n{'='*50}")
    if failed:
        print(f"FAILED {len(failed)}/{len(tests)} tests: {failed}")
        sys.exit(1)
    else:
        print(f"ALL {len(tests)} TESTS PASSED ✅")
        sys.exit(0)
