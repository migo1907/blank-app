"""
Trail-stop backtest — replicates the LIVE Pine exit management, not just the ladder.

Why this exists: the ladder backtests graded pure TP/SL (PF 1.3–1.6) while live
P&L runs PF 0.5–0.96. The difference is the Pine trail machinery this module
models bar-by-bar, in Pine's execution order:

  1. trail ratchet (before exit checks, as in the script):
       after TP1: trailSL ratchets to high − atr·trailMult (long), tighter
       atrMultTrl2 after TP2; slPrice follows the trail.
  2. exits in written order: TP1 → TP2 → TP3(full WIN) → SL/trail touch.
  3. TP1 hit sets the break-even guarantee: trail = max(close − atr·trailMult,
       entry + be_buffer·atr)   (live be_buffer = 0).
  4. near-TP proximity reset: before TP1, if the 3-bar high reached 80% of the
       way to TP1 but close fell back below, the trade is silently abandoned
       (scratched at close) — exactly the live behavior that also hides these
       trades from training data.

Config knobs swept by run_sweep (live values marked):
    trail_mult   ATR multiple for the post-TP1 trail      (live: 1.2)
    tighten2     post-TP2 trail multiple                  (live: per-TF 0.5–1.5)
    be_buffer    BE floor offset in ATRs above entry      (live: 0.0)
    use_be       break-even guarantee on TP1              (live: True)
    use_prox     proximity reset                          (live: True)
    trail_mult=None disables the trail entirely → pure ladder (the old backtest).

Uses the shared signal core (polygon_intraday_backtest) so entries are identical
to production; forward bars carry per-bar ATR because the live trail ratchets on
the CURRENT bar's ATR, not the entry bar's.
"""
from __future__ import annotations
import math

# live per-TF post-TP2 tighten values (Pine atrMultTrl2)
_TRL2 = {"2": 0.5, "5": 0.7, "15": 0.9, "30": 1.0, "60": 1.2, "240": 1.5}
_PROX = 0.8  # live tpProximity default 80%


def build_trail_entries(symbol: str, tf: str, bars: list[dict]) -> list[dict]:
    """Entries from the shared signal core, with forward (h,l,c,atr) tuples."""
    import polygon_intraday_backtest as bt
    df = bt._bars_to_df(bars)
    F = bt.compute_features(df)
    sig = bt._signals(F, tf)
    horizon = bt._HORIZON.get(str(tf), 32) * 2   # trails need room to play out
    highs = df["h"].values; lows = df["l"].values
    closes = df["c"].values; atrs = F["_atr"].values
    entries, last_sig = [], 0
    for i in range(len(sig)):
        new_sig = 1 if bool(sig["long_ok"].iloc[i]) else (-1 if bool(sig["short_ok"].iloc[i]) else 0)
        if new_sig == 0 or new_sig == last_sig:
            continue
        last_sig = new_sig
        atr0 = float(atrs[i])
        if atr0 <= 0 or not math.isfinite(atr0):
            continue
        fwd = [(float(highs[j]), float(lows[j]), float(closes[j]), float(atrs[j]))
               for j in range(i + 1, min(i + 1 + horizon, len(sig)))]
        if not fwd:
            continue
        entries.append({"dir": new_sig, "entry": float(closes[i]), "atr": atr0, "fwd": fwd})
    return entries


def grade_trail(e: dict, tf: str, ladder, trail_mult, be_buffer=0.0,
                use_be=True, use_prox=True, tighten2=None,
                trail_mult_pre=1.2, lock_levels=False) -> dict:
    """Walk one entry through the live exit machinery. Returns pnl_pct + stage.
    trail_mult=None → pure ladder (no trail, no proximity reset unless use_prox).
    lock_levels=True → stop moves to entry at TP1 and to TP1 at TP2 (structure
    locking, no ATR ratchet) — overrides trail_mult."""
    tp1m, tp2m, tp3m, slm = ladder
    s = e["dir"]                     # +1 long / -1 short
    entry, atr0 = e["entry"], e["atr"]
    tp1 = entry + s * atr0 * tp1m
    tp2 = entry + s * atr0 * tp2m
    tp3 = entry + s * atr0 * tp3m
    sl  = entry - s * atr0 * slm
    trl2 = tighten2 if tighten2 is not None else _TRL2.get(str(tf), 1.0)
    slp, trail = sl, sl
    tp1h = tp2h = False
    last3 = []

    def fav(px):   # signed favorable move
        return s * (px - entry)

    for (h, l, c, a) in e["fwd"]:
        hi, lo = (h, l) if s == 1 else (l, h)   # 'hi' = favorable extreme
        # 1) trail ratchet (Pine: trail block runs before exit blocks)
        if trail_mult is not None and tp1h:
            tm = trl2 if tp2h else trail_mult
            cand = hi - s * a * tm
            trail = max(trail, cand) if s == 1 else min(trail, cand)
            slp = trail
        # 2) exits in Pine's order
        if not tp1h and fav(hi) >= fav(tp1):
            tp1h = True
            if lock_levels:
                slp = entry
            elif trail_mult is not None:
                cand = c - s * a * trail_mult
                if use_be:
                    floor = entry + s * be_buffer * atr0
                    trail = max(cand, floor) if s == 1 else min(cand, floor)
                else:
                    trail = cand
                slp = trail
        if tp1h and not tp2h and fav(hi) >= fav(tp2):
            tp2h = True
            if lock_levels:
                slp = tp1
            elif trail_mult is not None:
                cand = hi - s * a * trl2
                trail = max(trail, cand) if s == 1 else min(trail, cand)
                slp = trail
        if tp1h and tp2h and fav(hi) >= fav(tp3):
            return {"pnl_pct": s * (tp3 - entry) / entry * 100, "stage": "TP3"}
        if fav(lo) <= fav(slp):
            stage = "SL_TP2" if tp2h else ("SL_TP1" if tp1h else "SL")
            return {"pnl_pct": s * (slp - entry) / entry * 100, "stage": stage}
        # 3) proximity reset (before TP1 only)
        if use_prox and not tp1h:
            last3.append(hi)
            if len(last3) > 3:
                last3.pop(0)
            near = entry + (tp1 - entry) * _PROX
            best3 = max(last3) if s == 1 else min(last3)
            if fav(best3) >= fav(near) and fav(c) < fav(near):
                return {"pnl_pct": s * (c - entry) / entry * 100, "stage": "PROX"}
    c_last = e["fwd"][-1][2]
    return {"pnl_pct": s * (c_last - entry) / entry * 100, "stage": "timeout"}


def summarize(results) -> dict:
    n = len(results)
    if not n:
        return {"n": 0}
    import collections
    wins = [r for r in results if r["pnl_pct"] > 0]
    gw = sum(r["pnl_pct"] for r in wins)
    gl = -sum(r["pnl_pct"] for r in results if r["pnl_pct"] <= 0)
    stages = collections.Counter(r["stage"] for r in results)
    return {"n": n, "win_pct": round(len(wins) / n * 100, 1),
            "exp": round(sum(r["pnl_pct"] for r in results) / n, 4),
            "pf": round(gw / gl, 3) if gl > 0 else None,
            "tp3_pct": round(stages.get("TP3", 0) / n * 100, 1),
            "stages": dict(stages)}


# The sweep grid: (name, trail_mult, be_buffer, use_be, use_prox, tighten2)
CONFIGS = [
    ("LIVE (1.2/BE0/prox)",   1.2, 0.0, True,  True,  None),
    ("trail1.8",              1.8, 0.0, True,  True,  None),
    ("trail2.5",              2.5, 0.0, True,  True,  None),
    ("trail1.2+buf0.3",       1.2, 0.3, True,  True,  None),
    ("trail1.8+buf0.3",       1.8, 0.3, True,  True,  None),
    ("trail1.2 noBE",         1.2, 0.0, False, True,  None),
    ("no-tighten2",           1.2, 0.0, True,  True,  9.0),
    ("trail1.8 no-tighten2",  1.8, 0.0, True,  True,  9.0),
    ("no-prox",               1.2, 0.0, True,  False, None),
    ("trail1.8 no-prox",      1.8, 0.0, True,  False, None),
    ("PURE LADDER",          None, 0.0, True,  False, None),
    ("pure+prox",            None, 0.0, True,  True,  None),
]


def run_cell(symbol: str, tf: str, bars: list[dict], ladder=None) -> dict:
    """Sweep all configs on one (symbol, tf) cell. Ladder defaults to _ATR_MULT."""
    import polygon_intraday_backtest as bt
    if ladder is None:
        ladder = bt._ATR_MULT.get(str(tf), bt._ATR_MULT["15"])
    entries = build_trail_entries(symbol, tf, bars)
    if len(entries) < 20:
        return {"symbol": symbol, "tf": tf, "error": f"insufficient ({len(entries)})"}
    out = {"symbol": symbol, "tf": tf, "n_entries": len(entries), "configs": {}}
    half = len(entries) // 2
    for (name, tm, buf, be, prox, t2) in CONFIGS:
        full = summarize([grade_trail(e, tf, ladder, tm, buf, be, prox, t2) for e in entries])
        h1 = summarize([grade_trail(e, tf, ladder, tm, buf, be, prox, t2) for e in entries[:half]])
        h2 = summarize([grade_trail(e, tf, ladder, tm, buf, be, prox, t2) for e in entries[half:]])
        out["configs"][name] = {"full": full, "h1_exp": h1.get("exp"), "h2_exp": h2.get("exp")}
    return out
