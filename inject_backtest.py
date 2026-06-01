"""
Inject 2m chart backtest trades into data/trade_history.json on GitHub.
Run once: python inject_backtest.py
"""
import csv
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
CSV_FILES = [
    "/root/.claude/uploads/315697b3-0d36-46ff-8f42-9b28f5fa4b28/f075ba3b-XAU_USD_Migo_Sniper_Pro_ML__Strategy_ICMARKETS_XAUUSD_20260602.csv",
    "/root/.claude/uploads/315697b3-0d36-46ff-8f42-9b28f5fa4b28/c70880bc-XAU_USD_Migo_Sniper_Pro_ML__Strategy_ICMARKETS_XAUUSD_20260602_1.csv",
]
TRADE_HISTORY_PATH = "data/trade_history.json"
MAX_KEEP = 1000   # db.py cap


def _outcome(pnl_pct: float, signal: str) -> str:
    sig = signal.upper()
    if "PARTIAL" in sig or "NEAR-TP" in sig:
        return "PARTIAL"
    if pnl_pct > 0:
        return "WIN"
    return "LOSS"


def parse_csv(path: str) -> list[dict]:
    trades = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            num  = row["Trade number"].strip()
            kind = row["Type"].strip().lower()
            if "entry" in kind:
                direction = "LONG" if "long" in kind else "SHORT"
                trades.setdefault(num, {})["direction"]   = direction
                trades[num]["entry_price"] = float(row["Price USD"])
                trades[num]["signal"]      = row["Signal"].strip()
                trades[num]["entry_time"]  = row["Date and time"].strip()
            elif "exit" in kind:
                trades.setdefault(num, {})["exit_price"] = float(row["Price USD"])
                trades[num]["pnl_pct"]     = float(row["Net PnL %"])
                trades[num]["exit_signal"] = row["Signal"].strip()
                trades[num]["exit_time"]   = row["Date and time"].strip()

    results = []
    for num, t in trades.items():
        if "entry_price" not in t or "exit_price" not in t:
            continue
        pnl = t.get("pnl_pct", 0.0)
        outcome = _outcome(pnl, t.get("exit_signal", ""))
        results.append({
            "id":           str(uuid.uuid4()),
            "direction":    t.get("direction", "LONG"),
            "entry_price":  t["entry_price"],
            "exit_price":   t["exit_price"],
            "pnl_pct":      round(pnl, 4),
            "outcome":      outcome,
            "ml_bull_score": 0.5,
            "source":       "backtest_2m",
            "created_at":   t.get("entry_time", ""),
            # zeroed feature vectors
            "f1_rsi": 0.0, "f2_macd": 0.0, "f3_bb": 0.0,
            "f4_atr": 0.0, "f5_ema_fast": 0.0, "f6_ema_slow": 0.0,
            "f7_stoch": 0.0, "f8_adx": 0.0, "f9_cci": 0.0,
            "f10_roc": 0.0, "f11_williams": 0.0, "f12_mfi": 0.0,
            "f13_obv": 0.0, "f14_vwap": 0.0, "f15_pivot": 0.0,
            "f16_fib": 0.0, "f17_sr": 0.0, "f18_pattern": 0.0,
            "f19_vol": 0.0, "f20_momentum": 0.0, "f21_vwap2": 0.0,
        })
    return results


def main():
    # load from GitHub
    sys.path.insert(0, "/home/user/blank-app/backend")
    from db import _get_file, _put_file

    existing, sha = _get_file(TRADE_HISTORY_PATH)
    if not isinstance(existing, list):
        existing = []
    print(f"[inject] Existing trades on GitHub: {len(existing)}")

    # parse both CSVs, deduplicate by entry_price+entry_time
    seen_keys = set()
    all_backtest = []
    for csv_path in CSV_FILES:
        trades = parse_csv(csv_path)
        print(f"[inject] Parsed {len(trades)} trades from {Path(csv_path).name}")
        for t in trades:
            key = f"{t['entry_price']}|{t['created_at']}"
            if key not in seen_keys:
                seen_keys.add(key)
                all_backtest.append(t)

    print(f"[inject] Unique backtest trades: {len(all_backtest)}")

    wins   = sum(1 for t in all_backtest if t["outcome"] == "WIN")
    losses = sum(1 for t in all_backtest if t["outcome"] == "LOSS")
    partials = sum(1 for t in all_backtest if t["outcome"] == "PARTIAL")
    print(f"[inject] Outcomes — WIN:{wins}  LOSS:{losses}  PARTIAL:{partials}  "
          f"Win-rate: {wins/(wins+losses+partials)*100:.1f}%")

    # put backtest first so live trades are at the END (recency matters for db.py cap)
    combined = all_backtest + existing
    # cap to MAX_KEEP, keeping the most recent (end of list)
    if len(combined) > MAX_KEEP:
        combined = combined[-MAX_KEEP:]

    print(f"[inject] Writing {len(combined)} trades to GitHub…")
    _put_file(TRADE_HISTORY_PATH, combined, sha, "feat: inject 2m backtest trades for ML training")
    print("[inject] Done.")


if __name__ == "__main__":
    main()
