"""
Forward intraday backtest harness.

Pulls real intraday OHLCV from Polygon, faithfully reproduces the "AI MLM 26"
TradingView indicator (features F1..F26 + Lorentzian KNN + RQ kernel + sideways
filter), grades ATR-based TP/SL bar-by-bar, summarizes per (symbol, timeframe),
and reuses exit_optimizer.optimize_pool / optimize_stop on the simulated trades.

Designed to run ON RAILWAY (which has POLYGON_API_KEY + outbound to api.polygon.io).
This sandbox cannot reach Polygon, so fetch_bars() degrades gracefully (returns []
on any error / missing key) and the math is validated locally with synthetic bars.

NOTES on faithfulness:
  • F17 (DXY correlation) is set to 0.0 — there is no DXY series in single-symbol
    OHLCV. Documented, intentional.
  • Seeded weights are FROZEN — no adaptive update is performed here (the live
    backend adapts; the backtest reproduces the seeded Pine baseline).
"""
from __future__ import annotations

import os
import math
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import httpx

_BASE = "https://api.polygon.io"
_KEY = ""

# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------

def _key() -> str:
    global _KEY
    if not _KEY:
        _KEY = os.environ.get("POLYGON_API_KEY", "")
    return _KEY


def available() -> bool:
    return bool(_key())


_POLY_MAP = {
    "XAUUSD": "C:XAUUSD",
    "SPX":    "I:SPX",
    "SPX500": "I:SPX",
    "SP500":  "I:SPX",
    "US500":  "I:SPX",
    "QQQ":    "QQQ",
    "SPY":    "SPY",
}


def _poly_ticker(symbol: str) -> str:
    return _POLY_MAP.get(str(symbol).upper().strip(), str(symbol).upper().strip())


_TF_AGG = {
    "5":   (5, "minute"),
    "15":  (15, "minute"),
    "30":  (30, "minute"),
    "60":  (1, "hour"),
    "240": (4, "hour"),
}


def _tf_agg(tf: str) -> tuple[int, str]:
    return _TF_AGG.get(str(tf).strip(), (15, "minute"))


def fetch_bars(ticker: str, multiplier: int, timespan: str,
               from_date: str, to_date: str) -> list[dict]:
    """Fetch aggregate bars from Polygon, following next_url pagination.
    Returns [{t,o,h,l,c,v}] sorted ascending. Degrades to [] on any error."""
    k = _key()
    if not k:
        print("[poly_bt] POLYGON_API_KEY absent — returning [] (use synthetic bars locally)")
        return []
    out: list[dict] = []
    url = (f"{_BASE}/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/"
           f"{from_date}/{to_date}")
    params: dict = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": k}
    try:
        with httpx.Client(timeout=20) as client:
            while url:
                r = client.get(url, params=params)
                if r.status_code != 200:
                    print(f"[poly_bt] {ticker} → HTTP {r.status_code}")
                    break
                data = r.json()
                for b in (data.get("results") or []):
                    out.append({"t": b["t"], "o": b["o"], "h": b["h"],
                                "l": b["l"], "c": b["c"], "v": b.get("v", 0)})
                nxt = data.get("next_url")
                if nxt:
                    url, params = nxt, {"apiKey": k}  # next_url already has query params
                else:
                    url = None
    except Exception as e:
        print(f"[poly_bt] {ticker} fetch failed: {e}")
        return []
    out.sort(key=lambda x: x["t"])
    return out


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _clamp(s):
    return np.clip(s, -1.0, 1.0)


def _rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's RMA (EMA with alpha=1/n)."""
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    rs = _rma(up, n) / _rma(dn, n).replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50.0)


def _atr(h, l, c, n=14):
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return _rma(tr, n)


def _dmi(h, l, c, n=14):
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = _rma(tr, n)
    di_plus = 100 * _rma(pd.Series(plus_dm, index=h.index), n) / atr.replace(0, np.nan)
    di_minus = 100 * _rma(pd.Series(minus_dm, index=h.index), n) / atr.replace(0, np.nan)
    dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
    adx = _rma(dx.fillna(0), n)
    return di_plus.fillna(0), di_minus.fillna(0), adx.fillna(0)


def _cmo(close, n=14):
    d = close.diff()
    up = d.clip(lower=0.0).rolling(n).sum()
    dn = (-d).clip(lower=0.0).rolling(n).sum()
    return (100 * (up - dn) / (up + dn).replace(0, np.nan)).fillna(0)


def _rolling_max(s, n):
    return s.rolling(n, min_periods=1).max()


def _rolling_min(s, n):
    return s.rolling(n, min_periods=1).min()


def _sign(s):
    return np.sign(s)


# ---------------------------------------------------------------------------
# Feature computation F1..F26
# ---------------------------------------------------------------------------

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """df indexed by UTC datetime with columns o,h,l,c,v. Returns df with f1..f26
    plus helper columns (adx, atr, atrSma, ema50, ema200, mlBull placeholder)."""
    o, h, l, c, v = df["o"], df["h"], df["l"], df["c"], df["v"]

    rsi = _rsi(c, 14)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    ema200 = c.ewm(span=200, adjust=False).mean()
    atr = _atr(h, l, c, 14)
    atr_sma = atr.rolling(20, min_periods=1).mean()
    di_plus, di_minus, adx = _dmi(h, l, c, 14)
    macd_line = ema12 - ema26
    macd_hist = macd_line - macd_line.ewm(span=9, adjust=False).mean()
    bb_mid = c.rolling(20, min_periods=1).mean()
    bb_std = c.rolling(20, min_periods=1).std().fillna(0)
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_pct = (c - bb_lower) / (bb_upper - bb_lower).clip(lower=1e-4)
    hh14 = _rolling_max(h, 14); ll14 = _rolling_min(l, 14)
    will_r = -100 * (hh14 - c) / (hh14 - ll14).replace(0, np.nan)
    will_r = will_r.fillna(-50)
    cmo = _cmo(c, 14) / 100.0
    stoch_k = (100 * (c - ll14) / (hh14 - ll14).replace(0, np.nan)).fillna(50)
    stoch_d = stoch_k.rolling(3, min_periods=1).mean()

    F = pd.DataFrame(index=df.index)
    F["f1"] = (rsi - 50) / 50
    F["f2"] = np.minimum(adx / 50, 1.0) * _sign(di_plus - di_minus)
    F["f3"] = _clamp((atr / atr_sma.replace(0, np.nan) - 1) * 2).fillna(0)
    F["f4"] = _clamp((bb_pct - 0.5) * 2)
    F["f5"] = _clamp(macd_hist / np.maximum(atr * 0.1, 1e-4))
    F["f6"] = -(will_r + 50) / 50
    F["f7"] = cmo

    F["f8"] = _clamp((c - ema200) / (atr * 5).replace(0, np.nan)).fillna(0)
    F["f9"] = np.where(l > h.shift(2), 1.0, np.where(h < l.shift(2), -1.0, 0.0))

    bull_imp = (c > h.shift(1)) & (c > o)
    bear_imp = (c < l.shift(1)) & (c < o)
    F["f10"] = np.where(bull_imp & (c.shift(1) < o.shift(1)), 1.0,
               np.where(bear_imp & (c.shift(1) > o.shift(1)), -1.0, 0.0))

    hh20 = _rolling_max(h, 20); ll20 = _rolling_min(l, 20)
    F["f11"] = np.where(c > hh20.shift(1), 1.0, np.where(c < ll20.shift(1), -1.0, 0.0))

    hh10 = _rolling_max(h, 10); ll10 = _rolling_min(l, 10)
    F["f12"] = np.where((l < ll10.shift(1)) & (c > ll10.shift(1)), 1.0,
               np.where((h > hh10.shift(1)) & (c < hh10.shift(1)), -1.0, 0.0))

    hh50 = _rolling_max(h, 50); ll50 = _rolling_min(l, 50)
    midpt50 = (hh50 + ll50) / 2
    rng50 = (hh50 - ll50).clip(lower=1e-4)
    F["f13"] = _clamp((midpt50 - c) / (rng50 * 0.5))

    higher_low = (l > l.shift(1)) & (l.shift(1) < l.shift(2)) & (c < ema50)
    lower_high = (h < h.shift(1)) & (h.shift(1) > h.shift(2)) & (c > ema50)
    F["f14"] = np.where(higher_low, 0.7, np.where(lower_high, -0.7, 0.0))

    hr = df.index.hour
    F["f15"] = np.select(
        [(hr >= 13) & (hr < 17), (hr >= 8) & (hr < 13), (hr >= 17) & (hr < 22)],
        [1.0, 0.8, 0.3], default=-0.5)

    # F16 MTF align — resample to 1h and 4h, forward-fill back
    c1h = c.resample("60min").last().dropna()
    ema50_1h = c1h.ewm(span=50, adjust=False).mean().reindex(df.index, method="ffill")
    ema200_1h = c1h.ewm(span=200, adjust=False).mean().reindex(df.index, method="ffill")
    c4h = c.resample("240min").last().dropna()
    ema50_4h = c4h.ewm(span=50, adjust=False).mean().reindex(df.index, method="ffill")
    bull_align = (ema50_1h > ema200_1h) & (c > ema50_4h)
    bear_align = (ema50_1h < ema200_1h) & (c < ema50_4h)
    F["f16"] = np.where(bull_align, 1.0, np.where(bear_align, -1.0, 0.0))

    F["f17"] = 0.0  # DXY correlation — no DXY series in single-symbol OHLCV

    rng = (h - l).clip(lower=1e-4)
    buy_vol = v * (c - l) / rng
    sell_vol = v * (h - c) / rng
    avg_vol = v.rolling(20, min_periods=1).mean()
    F["f18"] = _clamp((buy_vol - sell_vol) / np.maximum(avg_vol, 1e-4))

    rsi_ll14 = rsi.rolling(14, min_periods=1).min()
    rsi_hh14 = rsi.rolling(14, min_periods=1).max()
    bull_div = (l <= ll14) & (rsi > rsi_ll14)
    bear_div = (h >= hh14) & (rsi < rsi_hh14)
    F["f19"] = np.where(bull_div, 1.0, np.where(bear_div, -1.0, 0.0))

    hh100 = _rolling_max(h, 100); ll100 = _rolling_min(l, 100)
    rng100 = (hh100 - ll100).clip(lower=1e-4)
    fib50 = ll100 + rng100 * 0.5
    fib618 = ll100 + rng100 * 0.618
    in_gbuy = (c >= fib50) & (c <= fib618)
    in_gsell = (c >= (hh100 - rng100 * 0.618)) & (c <= (hh100 - rng100 * 0.5))
    F["f20"] = np.where(in_gbuy, 0.8, np.where(in_gsell, -0.8,
               _clamp((c - fib50) / (rng100 * 0.5))))

    # F21 VWAP — cumulative, daily reset
    hlc3 = (h + l + c) / 3
    day = pd.Series(df.index.date, index=df.index)
    cum_pv = (hlc3 * v).groupby(day).cumsum()
    cum_v = v.groupby(day).cumsum().replace(0, np.nan)
    vwap = (cum_pv / cum_v).fillna(hlc3)
    F["f21"] = _clamp((c - vwap) / np.maximum(atr * 3, 1e-4))

    body = (c - o).abs()
    full_rng = (h - l).clip(lower=1e-6)
    F["f22"] = _sign(c - o) * np.minimum(body / full_rng, 1.0)

    F["f23"] = _clamp(((rsi - rsi.shift(3)) / 3) / 15)

    sw_low20_2 = ll20.shift(2)
    sw_high20_2 = hh20.shift(2)
    sweep_down = (l.shift(1) < sw_low20_2) & (c.shift(1) > sw_low20_2)
    sweep_up = (h.shift(1) > sw_high20_2) & (c.shift(1) < sw_high20_2)
    fvg_bull = sweep_down & (l > h.shift(2)) & (c > o)
    fvg_bear = sweep_up & (h < l.shift(2)) & (c < o)
    F["f24"] = np.where(fvg_bull, 1.0, np.where(fvg_bear, -1.0, 0.0))

    mins = df.index.hour * 60 + df.index.minute
    F["f25"] = np.sin(mins / 1440 * 2 * math.pi)

    F["f26"] = _clamp((stoch_k - stoch_d) / 20)

    F = F.fillna(0.0)

    # helpers for signal core
    F["_atr"] = atr
    F["_atr_sma"] = atr_sma
    F["_adx"] = adx
    F["_ema50"] = ema50
    F["_ema200"] = ema200
    F["_close"] = c
    return F


# ---------------------------------------------------------------------------
# Signal core — Lorentzian KNN + RQ kernel + sideways filter
# ---------------------------------------------------------------------------

# Seeded weights (F1..F26 order) — FROZEN. No adaptive update in the backtest.
_WEIGHTS = np.array([
    0.200, 0.200, 0.944, 0.200, 0.200,
    3.000, 0.200, 0.231, 0.200, 0.257,
    0.200, 2.601, 3.000, 1.501, 1.568,
    0.220, 0.221, 0.200, 2.402, 0.200,
    0.291, 0.200, 0.200, 1.773, 0.641,
    0.200,
])

_FCOLS = [f"f{i}" for i in range(1, 27)]


def _ml_depth(tf: str) -> int:
    return {"5": 250, "15": 350, "30": 400}.get(str(tf), 500)


def _k_window(tf: str) -> int:
    return {"5": 8, "15": 12, "30": 14, "60": 16}.get(str(tf), 20)


def _rq_kernel(close: pd.Series, h: float, alpha: float, window: int) -> pd.Series:
    """Rational quadratic kernel regression estimate."""
    vals = close.values
    n = len(vals)
    est = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - window + 1)
        w_sum = 0.0
        wv_sum = 0.0
        for j in range(lo, i + 1):
            d = i - j
            w = (1 + (d * d) / (2 * alpha * h * h)) ** (-alpha)
            w_sum += w
            wv_sum += w * vals[j]
        est[i] = wv_sum / w_sum if w_sum else vals[i]
    return pd.Series(est, index=close.index)


def _knn_bull(F: pd.DataFrame, tf: str, ml_k=8, ml_lag=4) -> pd.Series:
    """Lorentzian-distance KNN — returns mlBull (bull vote fraction) per bar.
    Only computed every 2nd bar (bar_index % 2 == 0), like Pine."""
    feats = F[_FCOLS].values
    close = F["_close"].values
    n = len(feats)
    depth = _ml_depth(tf)
    out = np.full(n, 0.5)
    last = 0.5
    w = _WEIGHTS
    for bar in range(n):
        if bar % 2 != 0:
            out[bar] = last
            continue
        start = max(0, bar - depth)
        search_len = bar - start
        if search_len < ml_lag + 2:
            out[bar] = last
            continue
        step = max(2, round(search_len / 150))
        dists = []
        a = feats[bar]
        for i in range(start, bar - ml_lag, step):
            diff = np.abs(a - feats[i])
            d = float(np.sum(w * np.log1p(diff)))
            label = 1 if close[i - ml_lag] > close[i] else -1
            dists.append((d, label))
        if not dists:
            out[bar] = last
            continue
        dists.sort(key=lambda x: x[0])
        nn = dists[:ml_k]
        bull = sum(1 for _, lab in nn if lab > 0)
        bear = sum(1 for _, lab in nn if lab < 0)
        last = bull / (bull + bear) if (bull + bear) else 0.5
        out[bar] = last
    return pd.Series(out, index=F.index)


def _signals(F: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Compute mlBull, kernel direction, sideways filter, and long/short entries."""
    ml_bull = _knn_bull(F, tf)
    window = _k_window(tf)
    est = _rq_kernel(F["_close"], h=8, alpha=1, window=window)
    kernel_up = est > est.shift(2)
    kernel_down = est < est.shift(2)

    adx = F["_adx"]
    atr = F["_atr"]
    atr_sma = F["_atr_sma"]
    ema50 = F["_ema50"]
    ema200 = F["_ema200"]
    adx_flat = adx < 20
    atr_compressed = atr < atr_sma * 0.75
    ema_too_close = (ema50 - ema200).abs() / ema200.replace(0, np.nan) * 100 < 0.3
    is_sideways = (adx_flat.astype(int) + atr_compressed.astype(int) +
                   ema_too_close.fillna(False).astype(int)) >= 2

    long_ok = (ml_bull >= 0.55) & kernel_up & (~is_sideways)
    short_ok = ((1 - ml_bull) >= 0.55) & kernel_down & (~is_sideways)

    out = pd.DataFrame(index=F.index)
    out["ml_bull"] = ml_bull
    out["long_ok"] = long_ok.fillna(False)
    out["short_ok"] = short_ok.fillna(False)
    out["atr"] = atr
    out["close"] = F["_close"]
    return out


# ---------------------------------------------------------------------------
# ATR TP/SL + grading
# ---------------------------------------------------------------------------

# (TP1, TP2, TP3, SL)
_ATR_MULT = {
    "5":   (1.5, 2.5, 4.0, 1.5),
    "15":  (2.0, 3.5, 5.5, 2.0),
    "30":  (2.2, 3.8, 6.0, 2.2),
    "60":  (2.5, 4.5, 7.0, 2.5),
    "240": (3.0, 5.5, 9.0, 3.0),
}

_HORIZON = {"5": 48, "15": 32, "30": 24, "60": 16, "240": 12}


def _grade_trade(direction, entry, atr_val, bars_after, tf):
    """Walk forward bar-by-bar. bars_after = list of (h,l,c). Returns trade dict."""
    tp1m, tp2m, tp3m, slm = _ATR_MULT.get(str(tf), _ATR_MULT["15"])
    if direction == "LONG":
        tp1 = entry + atr_val * tp1m
        tp2 = entry + atr_val * tp2m
        tp3 = entry + atr_val * tp3m
        sl = entry - atr_val * slm
    else:
        tp1 = entry - atr_val * tp1m
        tp2 = entry - atr_val * tp2m
        tp3 = entry - atr_val * tp3m
        sl = entry + atr_val * slm

    mfe = 0.0  # max favorable move (points)
    mae = 0.0  # max adverse move (points, positive)
    exit_reason = "timeout"
    tp_stage = ""
    exit_price = entry

    for (bh, bl, bc) in bars_after:
        if direction == "LONG":
            fav = bh - entry
            adv = entry - bl
            mfe = max(mfe, fav); mae = max(mae, adv)
            sl_hit = bl <= sl
            tp3_hit = bh >= tp3
            tp2_hit = bh >= tp2
            tp1_hit = bh >= tp1
        else:
            fav = entry - bl
            adv = bh - entry
            mfe = max(mfe, fav); mae = max(mae, adv)
            sl_hit = bh >= sl
            tp3_hit = bl <= tp3
            tp2_hit = bl <= tp2
            tp1_hit = bl <= tp1

        # pessimistic: SL-first if both SL and any TP fall in same bar
        if sl_hit:
            exit_reason, tp_stage, exit_price = "SL", "SL", sl
            break
        if tp3_hit:
            exit_reason, tp_stage, exit_price = "TP3", "TP3", tp3
            break
        if tp2_hit:
            exit_reason, tp_stage, exit_price = "TP2", "TP2", tp2
            break
        if tp1_hit:
            exit_reason, tp_stage, exit_price = "TP1", "TP1", tp1
            break
    else:
        # timeout — grade by final bar close
        exit_price = bars_after[-1][2] if bars_after else entry

    if direction == "LONG":
        pnl_pct = (exit_price - entry) / entry * 100
    else:
        pnl_pct = (entry - exit_price) / entry * 100

    if exit_reason in ("TP1", "TP2", "TP3"):
        outcome = "WIN"
    elif exit_reason == "timeout":
        outcome = "WIN" if pnl_pct > 0 else "LOSS"
    else:
        outcome = "LOSS"

    return {
        "direction": direction,
        "entry": round(entry, 5),
        "entry_price": round(entry, 5),
        "exit_reason": exit_reason,
        "tp_stage": tp_stage,
        "pnl_pct": round(pnl_pct, 5),
        "mfe": round(mfe, 5),
        "mae": round(mae, 5),
        "outcome": outcome,
    }


def simulate(sig: pd.DataFrame, tf: str) -> list[dict]:
    """Generate trades on flips (dedup via lastSig), grade each."""
    horizon = _HORIZON.get(str(tf), 32)
    trades = []
    last_sig = 0  # 0 none, 1 long, -1 short
    idx = list(range(len(sig)))
    closes = sig["close"].values
    highs = None  # we only have close in sig; need full OHLC — pass via attrs
    # sig carries close+atr; we need h/l from the source df attached as attrs
    hl = sig.attrs.get("hl")  # list of (h,l,c)
    for i in idx:
        long_ok = bool(sig["long_ok"].iloc[i])
        short_ok = bool(sig["short_ok"].iloc[i])
        new_sig = 0
        if long_ok:
            new_sig = 1
        elif short_ok:
            new_sig = -1
        if new_sig != 0 and new_sig != last_sig:
            last_sig = new_sig
            atr_val = float(sig["atr"].iloc[i])
            entry = float(closes[i])
            if atr_val <= 0 or not math.isfinite(atr_val):
                continue
            bars_after = hl[i + 1: i + 1 + horizon] if hl else []
            if not bars_after:
                continue
            direction = "LONG" if new_sig == 1 else "SHORT"
            trades.append(_grade_trade(direction, entry, atr_val, bars_after, tf))
    return trades


# ---------------------------------------------------------------------------
# Summarize
# ---------------------------------------------------------------------------

def summarize(trades: list[dict], symbol: str, tf: str) -> dict:
    import exit_optimizer
    n = len(trades)
    if n == 0:
        return {"symbol": symbol, "timeframe": tf, "n_trades": 0}

    wins = [t for t in trades if t["outcome"] == "WIN"]
    pnls = [t["pnl_pct"] for t in trades]
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    pf = round(gross_win / gross_loss, 3) if gross_loss > 0 else None

    def _pct(reason):
        return round(100 * sum(1 for t in trades if t["exit_reason"] == reason) / n, 1)

    out = {
        "symbol": symbol,
        "timeframe": tf,
        "n_trades": n,
        "win_rate": round(100 * len(wins) / n, 1),
        "avg_pnl_pct": round(sum(pnls) / n, 4),
        "profit_factor": pf,
        "pct_SL": _pct("SL"),
        "pct_TP1": _pct("TP1"),
        "pct_TP2": _pct("TP2"),
        "pct_TP3": _pct("TP3"),
        "pct_timeout": _pct("timeout"),
    }
    try:
        out["exit_optimizer"] = exit_optimizer.optimize_pool(trades)
    except Exception as e:
        out["exit_optimizer"] = {"error": str(e)}
    return out


# ---------------------------------------------------------------------------
# Per (symbol, tf) pipeline
# ---------------------------------------------------------------------------

def _bars_to_df(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    df["dt"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    df = df.set_index("dt").sort_index()
    return df[["o", "h", "l", "c", "v"]].astype(float)


def backtest_one(symbol: str, tf: str, bars: list[dict]) -> dict:
    if not bars or len(bars) < 60:
        return {"symbol": symbol, "timeframe": tf, "n_trades": 0,
                "note": f"insufficient bars ({len(bars)})"}
    df = _bars_to_df(bars)
    F = compute_features(df)
    sig = _signals(F, tf)
    hl = list(zip(df["h"].values, df["l"].values, df["c"].values))
    sig.attrs["hl"] = hl
    trades = simulate(sig, tf)
    return summarize(trades, symbol, tf)


# ---------------------------------------------------------------------------
# Entry point + persistence
# ---------------------------------------------------------------------------

def run(symbols=None, timeframes=None, days: int = 120) -> dict:
    symbols = symbols or ["QQQ", "SPX", "XAUUSD"]
    # Coarse timeframes first (far fewer bars → quick partial results), heavy 5m last.
    timeframes = timeframes or ["240", "60", "30", "15", "5"]
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=days)
    to_s, from_s = to_date.isoformat(), from_date.isoformat()

    results: dict = {}
    total = len(symbols) * len(timeframes)
    done = 0

    def _snapshot(status: str) -> dict:
        return {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": status,                       # running | complete
            "progress": f"{done}/{total}",
            "params": {"symbols": symbols, "timeframes": timeframes, "days": days,
                       "weights_frozen": True, "f17_dxy": "set to 0 (no DXY series)"},
            "results": results,
        }

    _persist(_snapshot("running"))                  # mark started immediately
    for sym in symbols:
        ticker = _poly_ticker(sym)
        for tf in timeframes:
            key = f"{sym}_{tf}"
            try:
                mult, span = _tf_agg(tf)
                bars = fetch_bars(ticker, mult, span, from_s, to_s)
                results[key] = backtest_one(sym, tf, bars)
            except Exception as e:
                print(f"[poly_bt] {key} failed: {e}")
                results[key] = {"symbol": sym, "timeframe": tf, "error": str(e)}
            done += 1
            _persist(_snapshot("running"))          # incremental — partial survives a crash

    out = _snapshot("complete")
    _persist(out)
    print(f"[poly_bt] backtest complete — {done}/{total} cells")
    return out


def _persist(out: dict) -> None:
    import time as _time, random as _random
    try:
        from db import _get_file, _put_file
    except Exception as e:
        print(f"[poly_bt] db import failed, skipping persist: {e}")
        return
    path = "data/backtest_results.json"
    for attempt in range(3):
        try:
            _, sha = _get_file(path)
            _put_file(path, out, sha, "data: intraday backtest results")
            return
        except Exception as e:
            print(f"[poly_bt] persist attempt {attempt+1} failed: {e}")
            _time.sleep(0.5 + _random.random())
    print("[poly_bt] persist gave up after 3 attempts")


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2)[:2000])
