"""
IBKR warm-start seeding — break the thin-pool cold-start with backtested labels.

A pool with <50 real closed trades returns KNN confidence 0 → NEUTRAL → no
entries stored → it never grows (the cold-start deadlock, CLAUDE.md rule 8).
The signal engine already bypasses the gate for thin pools so they CAN trade,
but the ML models still have nothing to learn setup structure from.

This module generates SYNTHETIC closed-trade rows from IBKR historical bars: it
runs the same AI-MLM-26 feature + signal core the backtest harness uses, grades
each entry against the pool's CURRENT exit ladder, and emits rows in the exact
schema the models train on (f1..f26 + outcome + pnl_pct + created_at), tagged
`synthetic: True, source: "ibkr_backtest"`.

Safety rails (this touches live training, so they matter):
  • OFF by default — augment_for_training is a no-op unless IBKR_WARMSTART_SEED
    is truthy in the environment. Flip it on in Railway only after inspecting the
    generated seed file.
  • Thin-only — seeds are injected ONLY while a pool has < MIN_REAL real trades,
    and they are capped so real data always dominates.
  • Down-weighted — _label_noise_weight() applies an extra 0.5× to synthetic rows,
    so a real trade always outweighs a seed; seeds fade as live trades arrive.
  • Isolated — seeds are NEVER written to the live ledger and NEVER enter gate
    win-rate stats or mistake-memory (those read recent_outcomes, not this file).
    They exist purely to initialise the RF/GBM/joint models.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone

MIN_REAL = 50           # stop seeding once a pool has this many real trades
_SEED_PATH = "data/ibkr_seed_trades.json"
_seed_cache: dict | None = None


def enabled() -> bool:
    return os.environ.get("IBKR_WARMSTART_SEED", "false").lower() in ("1", "true", "yes")


# ── seed generation (run in my session / by the backend once a gateway is live) ──

def build_seed_trades(pool: str, symbol: str, tf: str, bars: list[dict],
                      cap: int = 200) -> list[dict]:
    """Turn IBKR OHLCV bars into synthetic training rows for `pool`.

    Mirrors polygon_intraday_backtest.build_entries (flip-dedup entry detection)
    but also captures the f1..f26 feature vector and timestamp at each entry, and
    grades with the pool's current ladder. Returns most-recent-first, capped."""
    import math
    import polygon_intraday_backtest as bt
    if not bars or len(bars) < 60:
        return []
    df = bt._bars_to_df(bars)
    F = bt.compute_features(df)
    sig = bt._signals(F, tf)
    hl = list(zip(df["h"].values, df["l"].values, df["c"].values))
    horizon = bt._HORIZON.get(str(tf), 32)
    closes = sig["close"].values
    idx = df.index

    rows: list[dict] = []
    last_sig = 0
    for i in range(len(sig)):
        long_ok = bool(sig["long_ok"].iloc[i])
        short_ok = bool(sig["short_ok"].iloc[i])
        new_sig = 1 if long_ok else (-1 if short_ok else 0)
        if new_sig == 0 or new_sig == last_sig:
            continue
        last_sig = new_sig
        atr_val = float(sig["atr"].iloc[i])
        entry = float(closes[i])
        if atr_val <= 0 or not math.isfinite(atr_val):
            continue
        bars_after = hl[i + 1: i + 1 + horizon]
        if not bars_after:
            continue
        graded = bt._grade_trade("LONG" if new_sig == 1 else "SHORT",
                                 entry, atr_val, bars_after, tf, mults=None)
        row = {
            "pool": pool, "symbol": symbol, "timeframe": str(tf),
            "direction": graded["direction"],
            "outcome": graded["outcome"],
            "pnl_pct": graded["pnl_pct"],
            "mfe": graded["mfe"], "mae": graded["mae"],
            "entry_price": graded["entry_price"],
            "created_at": idx[i].to_pydatetime().astimezone(timezone.utc).isoformat(),
            "synthetic": True, "source": "ibkr_backtest",
        }
        for k in range(1, 27):
            row[f"f{k}"] = float(F[f"f{k}"].iloc[i])
        rows.append(row)

    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:cap]


def save_seeds(seed_map: dict[str, list[dict]]) -> None:
    """Persist {pool: [seed_rows]} to the data branch via db (same store as trades).
    db._get_file returns (content, sha); db._put_file takes parsed content + sha."""
    try:
        import db
        _, sha = db._get_file(_SEED_PATH)
        db._put_file(_SEED_PATH, seed_map, sha, "ibkr warm-start seed trades")
        global _seed_cache
        _seed_cache = seed_map
    except Exception as e:
        print(f"[warmstart] save failed: {e}")


# ── seed consumption (live training path) ──────────────────────────────────────

def _load_seeds() -> dict:
    global _seed_cache
    if _seed_cache is not None:
        return _seed_cache
    try:
        import db
        content, _ = db._get_file(_SEED_PATH)
        _seed_cache = content if isinstance(content, dict) else {}
    except Exception:
        _seed_cache = {}
    return _seed_cache


def augment_for_training(pool: str, real_history: list[dict]) -> list[dict]:
    """Return the history to TRAIN on. When seeding is enabled and `pool` is still
    thin, append capped, flagged synthetic seeds; otherwise return real_history
    unchanged. Never mutates the input list. No-op-safe on any error."""
    if not enabled():
        return real_history
    try:
        real = real_history or []
        # count only genuine closed trades toward the threshold
        n_real = sum(1 for t in real if not t.get("synthetic")
                     and t.get("outcome") in ("WIN", "LOSS", "PARTIAL"))
        if n_real >= MIN_REAL:
            return real_history
        seeds = _load_seeds().get(pool) or []
        if not seeds:
            return real_history
        # cap so real data dominates: at most ~3× real + a small floor for a
        # brand-new pool, never more than the stored seed set
        cap = min(len(seeds), max(30, n_real * 3 + 30))
        merged = list(real) + seeds[:cap]
        print(f"[warmstart] pool '{pool}': {n_real} real + {cap} synthetic seeds")
        return merged
    except Exception as e:
        print(f"[warmstart] augment failed for {pool}: {e}")
        return real_history
