"""
Swing addon — Paper-trade tracker (the training-data engine).

This is what "starts the training clock". The screener ranks candidates; this
module turns the top picks into PAPER trades, records the full feature vector at
entry, then closes each trade as WIN/LOSS by an ATR target/stop with a 15-day
cap. Those labeled (features → outcome) rows are exactly what the ML ensemble
needs — until ~50-100 closed trades per cluster accumulate, the screener stays
rules-based (cold-start rule).

Exit rule (chosen): entry at the daily close; TP = +2·ATR(14), SL = -1·ATR(14),
force-close at 15 trading days (WIN if green, else LOSS). Conservative on
same-bar ambiguity — if a bar touches both SL and TP, count it as the SL (the
pessimistic label).

Persistence: data/swing_trades.json = {"open": [...], "closed": [...]}.
Everything is best-effort; a failed fetch leaves a trade open for the next day.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

_TRADES_PATH = "data/swing_trades.json"
_ATR_PERIOD = 14
_TP_MULT = 2.0
_SL_MULT = 1.0
_MAX_HOLD_DAYS = 15

# Flat numeric feature vector captured at entry — the ML training inputs.
FEATURE_KEYS = [
    "combined_score", "fund_score", "tech_score", "rsi", "rel_strength_pct",
    "target_upside_pct", "last_surprise_pct", "revenue_growth_pct",
    "earnings_growth_pct", "insider_net_buy", "short_pct_float", "news_7d",
    "imminent_earnings",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _atr(d, period: int = _ATR_PERIOD) -> float | None:
    """Daily ATR from an OHLC frame (Wilder-style simple mean of true range)."""
    try:
        h = d["High"].to_numpy(dtype=float)
        l = d["Low"].to_numpy(dtype=float)
        c = d["Close"].to_numpy(dtype=float)
        if len(c) < period + 1:
            return None
        prev_c = c[:-1]
        tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - prev_c), np.abs(l[1:] - prev_c)])
        return float(tr[-period:].mean())
    except Exception:
        return None


def _features(cand: dict) -> dict:
    """Flatten a screener candidate into the numeric training feature vector."""
    f = cand.get("fundamental", {})
    t = cand.get("technical", {})
    a, e, g = f.get("analyst", {}), f.get("earnings", {}), f.get("growth", {})

    def num(x, default=0.0):
        return float(x) if isinstance(x, (int, float)) else default

    return {
        "combined_score":     num(cand.get("combined_score")),
        "fund_score":         num(f.get("score")),
        "tech_score":         num(t.get("score")),
        "rsi":                num(t.get("rsi"), 50.0),
        "rel_strength_pct":   num(t.get("rel_strength_pct")),
        "target_upside_pct":  num(a.get("target_upside_pct")),
        "last_surprise_pct":  num(e.get("last_surprise_pct")),
        "revenue_growth_pct": num(g.get("revenue_growth_pct")),
        "earnings_growth_pct": num(g.get("earnings_growth_pct")),
        "insider_net_buy":    num(f.get("insider", {}).get("net_buy_signal")),
        "short_pct_float":    num(f.get("short", {}).get("short_pct_float")),
        "news_7d":            num(f.get("news", {}).get("news_7d")),
        "imminent_earnings":  1.0 if e.get("imminent") else 0.0,
    }


def _load() -> dict:
    try:
        from db import _get_file
        data, _ = _get_file(_TRADES_PATH)
        if isinstance(data, dict):
            data.setdefault("open", [])
            data.setdefault("closed", [])
            return data
    except Exception as e:
        print(f"[swing_trk] load failed: {e}")
    return {"open": [], "closed": []}


def _save(store: dict, msg: str) -> None:
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_TRADES_PATH)
        _put_file(_TRADES_PATH, store, sha, msg)
    except Exception as e:
        print(f"[swing_trk] persist failed: {e}")


def open_paper_trades(screen: dict) -> int:
    """Open a paper trade for each top candidate not already open. Returns count."""
    cands = (screen or {}).get("candidates", [])
    if not cands:
        return 0
    store = _load()
    open_tickers = {t["ticker"] for t in store["open"]}
    from market_data import fetch_daily

    opened = 0
    for c in cands:
        tkr = c.get("ticker")
        if not tkr or tkr in open_tickers:
            continue
        try:
            d = fetch_daily(tkr, period="6mo")
            if not len(d):
                continue
            entry = float(d["Close"].to_numpy(dtype=float)[-1])
            atr = _atr(d)
            if not atr or entry <= 0:
                continue
            trade = {
                "id":         f"{tkr}-{_today()}",
                "ticker":     tkr,
                "entry_date": _today(),
                "entry_price": round(entry, 2),
                "atr":        round(atr, 2),
                "tp":         round(entry + _TP_MULT * atr, 2),
                "sl":         round(entry - _SL_MULT * atr, 2),
                "combined_score": c.get("combined_score", 0.0),
                "features":   _features(c),
                "opened_at":  _now(),
            }
            store["open"].append(trade)
            open_tickers.add(tkr)
            opened += 1
        except Exception as e:
            print(f"[swing_trk] open {tkr} failed: {e}")

    if opened:
        _save(store, f"data: open {opened} swing paper trades")
        print(f"[swing_trk] opened {opened} paper trades")
    return opened


def _trading_days_between(start_iso: str, bars_dates) -> int:
    """Count daily bars strictly after the entry date (≈ trading days held)."""
    start = datetime.fromisoformat(start_iso).date()
    return sum(1 for d in bars_dates if d.date() > start)


def manage_paper_trades() -> dict:
    """
    Resolve open paper trades against fresh daily bars. TP/SL/max-hold → WIN/LOSS.
    Returns {closed: int, wins: int, losses: int}.
    """
    store = _load()
    if not store["open"]:
        return {"closed": 0, "wins": 0, "losses": 0}
    from market_data import fetch_daily

    still_open, newly_closed = [], []
    for tr in store["open"]:
        tkr = tr["ticker"]
        try:
            d = fetch_daily(tkr, period="3mo")
            if not len(d):
                still_open.append(tr)
                continue
            entry_date = datetime.fromisoformat(tr["entry_date"]).date()
            after = d[d.index.map(lambda x: x.date() > entry_date)]
            if not len(after):
                still_open.append(tr)
                continue

            highs = after["High"].to_numpy(dtype=float)
            lows = after["Low"].to_numpy(dtype=float)
            closes = after["Close"].to_numpy(dtype=float)
            tp, sl = tr["tp"], tr["sl"]

            outcome = exit_price = exit_idx = None
            for i in range(len(after)):
                # Conservative: SL checked before TP on a same-bar touch
                if lows[i] <= sl:
                    outcome, exit_price, exit_idx = "LOSS", sl, i
                    break
                if highs[i] >= tp:
                    outcome, exit_price, exit_idx = "WIN", tp, i
                    break

            held = len(after)
            if outcome is None and held >= _MAX_HOLD_DAYS:
                exit_price = float(closes[_MAX_HOLD_DAYS - 1])
                outcome = "WIN" if exit_price > tr["entry_price"] else "LOSS"
                exit_idx = _MAX_HOLD_DAYS - 1

            if outcome is None:
                still_open.append(tr)
                continue

            pnl = (exit_price / tr["entry_price"] - 1.0) * 100.0
            tr.update({
                "exit_date":  after.index[exit_idx].date().isoformat(),
                "exit_price": round(float(exit_price), 2),
                "outcome":    outcome,
                "pnl_pct":    round(pnl, 2),
                "bars_held":  int(exit_idx + 1),
                "label":      1 if outcome == "WIN" else 0,
                "closed_at":  _now(),
            })
            newly_closed.append(tr)
        except Exception as e:
            print(f"[swing_trk] manage {tkr} failed: {e}")
            still_open.append(tr)

    if newly_closed:
        store["open"] = still_open
        store["closed"].extend(newly_closed)
        _save(store, f"data: close {len(newly_closed)} swing paper trades")

    wins = sum(1 for t in newly_closed if t["outcome"] == "WIN")
    losses = len(newly_closed) - wins
    if newly_closed:
        print(f"[swing_trk] closed {len(newly_closed)} ({wins}W/{losses}L)")
    return {"closed": len(newly_closed), "wins": wins, "losses": losses}


def training_dataset() -> tuple[list[list[float]], list[int], dict]:
    """
    Build (X, y, meta) from all closed paper trades for ML training.
    X rows follow FEATURE_KEYS order; y is 1=WIN / 0=LOSS.
    """
    store = _load()
    closed = store["closed"]
    X, y = [], []
    for t in closed:
        feats = t.get("features", {})
        X.append([float(feats.get(k, 0.0)) for k in FEATURE_KEYS])
        y.append(int(t.get("label", 0)))
    n = len(y)
    meta = {
        "n_closed":  n,
        "n_wins":    sum(y),
        "n_losses":  n - sum(y),
        "win_rate":  round(sum(y) / n, 3) if n else None,
        "n_open":    len(store["open"]),
        "ready":     n >= 50,   # rough threshold to flip ML on
        "feature_keys": FEATURE_KEYS,
    }
    return X, y, meta


def stats() -> dict:
    """Lightweight training-readiness summary for the /swing/trades endpoint."""
    _, _, meta = training_dataset()
    return meta


def sanity_flag(meta: dict) -> str | None:
    """
    Return a human-readable warning if the win-rate looks pathological — the
    signal that the rules-based score or exit rule has a real bug worth a look
    (vs. normal noise). None when nothing's off. Mirrors the autopsy discipline:
    only flag the extremes, don't invite tuning on noise.
    """
    n, wr = meta.get("n_closed", 0), meta.get("win_rate")
    if n < 20 or wr is None:
        return None
    if wr < 0.25:
        return f"win-rate {wr:.0%} over {n} trades — abnormally low, investigate exit rule / technical score"
    if wr > 0.75:
        return f"win-rate {wr:.0%} over {n} trades — abnormally high, verify labels aren't leaking"
    return None


def shadow_eval() -> dict:
    """
    Once enough closed trades exist, walk-forward compare the ML ensemble candidate
    against the rules baseline (combined_score > 0 ⇒ WIN). Pure shadow — does NOT
    drive live scoring. Returns {ready, baseline_f1, ml_f1, verdict, ...}.
    """
    X, y, meta = training_dataset()
    out = {"ready": meta["ready"], "n_closed": meta["n_closed"], "win_rate": meta["win_rate"]}
    if meta["n_closed"] < 50 or len(set(y)) < 2:
        out["verdict"] = "accumulating — not enough closed trades to evaluate ML yet"
        return out
    try:
        import numpy as np
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import TimeSeriesSplit
        from sklearn.metrics import f1_score

        Xa, ya = np.array(X, dtype=float), np.array(y)
        ci = FEATURE_KEYS.index("combined_score")
        tscv = TimeSeriesSplit(n_splits=3, gap=2)
        base_f1, ml_f1 = [], []
        for tr, val in tscv.split(Xa):
            if len(tr) < 20 or len(set(ya[tr].tolist())) < 2:
                continue
            base_pred = (Xa[val, ci] > 0).astype(int)
            base_f1.append(f1_score(ya[val], base_pred, zero_division=0))
            clf = RandomForestClassifier(n_estimators=100, max_depth=4, random_state=42)
            clf.fit(Xa[tr], ya[tr])
            ml_f1.append(f1_score(ya[val], clf.predict(Xa[val]), zero_division=0))
        if not base_f1:
            out["verdict"] = "insufficient class balance for walk-forward eval"
            return out
        b, m = round(float(np.mean(base_f1)), 3), round(float(np.mean(ml_f1)), 3)
        out["baseline_f1"], out["ml_f1"] = b, m
        if m > b + 0.03:
            out["verdict"] = f"ML beats rules baseline ({m} vs {b}) — candidate to promote after a shadow period"
        else:
            out["verdict"] = f"ML not yet beating rules baseline ({m} vs {b}) — keep rules-based"
    except Exception as e:
        out["verdict"] = f"shadow eval error: {e}"
    return out
