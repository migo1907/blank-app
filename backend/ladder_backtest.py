"""
Replication of the deployed Pine Script exit ladder (migo_sniper_f26.pine)
so real IBKR bars can validate the shipped TP/SL/trail multipliers.

The state machine mirrors the Pine source exactly — including its quirks:
  - Entry on bar close; exits evaluated from the NEXT bar (in Pine the exit
    block runs before the entry block arms activeTrade).
  - Per-bar order: trail update (uses the CURRENT bar extreme) -> TP1 ->
    TP2 -> TP3 (full exit, skips the SL check) -> SL.
  - TP1 arms the trail at close -/+ ATR*1.2 with a break-even guarantee
    (never worse than entry). TP2 tightens the trail to atrMultTrl2 off the
    bar extreme — on most bars that trail sits INSIDE the bar's own range,
    so post-TP2 exits are usually immediate.
  - All-in / all-out: Pine never scales out. "PARTIAL" = trailed stop after
    TP1 (booked as a win upstream), "LOSS" = stop before TP1.

R-multiples are normalized by the entry risk (ATR at entry x SL mult), so
-1.0 R is a clean initial stop-out.
"""
from __future__ import annotations

# autoTF ladder from migo_sniper_f26.pine (lines 56-61)
TF_LADDERS = {
    "2m":  {"tp1": 1.0, "tp2": 1.8, "tp3": 3.0, "sl": 0.8, "trail2": 0.5},
    "5m":  {"tp1": 1.5, "tp2": 2.5, "tp3": 4.0, "sl": 1.5, "trail2": 0.7},
    "15m": {"tp1": 2.0, "tp2": 3.5, "tp3": 5.5, "sl": 2.0, "trail2": 0.9},
    "30m": {"tp1": 2.2, "tp2": 3.8, "tp3": 6.0, "sl": 2.2, "trail2": 1.0},
    "1h":  {"tp1": 2.5, "tp2": 4.5, "tp3": 7.0, "sl": 2.5, "trail2": 1.2},
    "4h":  {"tp1": 3.0, "tp2": 5.5, "tp3": 9.0, "sl": 3.0, "trail2": 1.5},
}
TRAIL_TP1 = 1.2   # trailMult input default — trail width between TP1 and TP2


def scrub_bad_prints(bars: list[dict], mult: float = 8.0,
                     window: int = 50) -> tuple[list[dict], int]:
    """Drop single-bar bad prints (e.g. IBKR midpoint glitches where the
    open/high spikes ~10% and reverts within the same bar). A bar is bad
    when its open sits more than `mult` x median-true-range away from BOTH
    the previous close and its own close — a real gap persists into the
    close, a glitch reverts. Returns (clean_bars, n_dropped)."""
    if len(bars) < 3:
        return bars, 0
    trs = [bars[i]["h"] - bars[i]["l"] for i in range(len(bars))]
    clean, dropped = [bars[0]], 0
    for i in range(1, len(bars)):
        b, prev_c = bars[i], clean[-1]["c"]
        w = sorted(trs[max(0, i - window):i + 1])
        med_tr = w[len(w) // 2] or 1e-9
        if (min(abs(b["o"] - prev_c), abs(b["o"] - b["c"])) > mult * med_tr):
            dropped += 1
            continue
        clean.append(b)
    return clean, dropped


def wilder_atr(bars: list[dict], period: int = 14) -> list:
    """Wilder ATR aligned to bars; None during the warmup window. Matches
    Pine ta.atr: TR at bar 0 is high-low, first value at index period-1."""
    n = len(bars)
    atr: list = [None] * n
    if n < period:
        return atr
    trs = [bars[0]["h"] - bars[0]["l"]]
    for i in range(1, n):
        b, pc = bars[i], bars[i - 1]["c"]
        trs.append(max(b["h"] - b["l"], abs(b["h"] - pc), abs(b["l"] - pc)))
    a = sum(trs[:period]) / period
    atr[period - 1] = a
    for i in range(period, n):
        a = (a * (period - 1) + trs[i]) / period
        atr[i] = a
    return atr


def simulate_ladder(bars: list[dict], atr: list, i_entry: int, direction: str,
                    ladder: dict, trail_tp1: float = TRAIL_TP1,
                    max_bars: int | None = None) -> dict | None:
    """One trade through the deployed exit ladder. Returns None when ATR is
    not warmed up or there is no bar after entry."""
    a0 = atr[i_entry] if i_entry < len(atr) else None
    if a0 is None or i_entry + 1 >= len(bars):
        return None
    entry = bars[i_entry]["c"]
    long = direction == "LONG"
    sgn = 1.0 if long else -1.0
    tp1 = entry + sgn * a0 * ladder["tp1"]
    tp2 = entry + sgn * a0 * ladder["tp2"]
    tp3 = entry + sgn * a0 * ladder["tp3"]
    sl = trail_sl = entry - sgn * a0 * ladder["sl"]
    risk = a0 * ladder["sl"]
    tp1_hit = tp2_hit = False

    def _book(exit_px: float, outcome: str, stage: str, j: int) -> dict:
        return {"direction": direction, "i_entry": i_entry, "entry": round(entry, 4),
                "exit": round(exit_px, 4), "outcome": outcome, "stage": stage,
                "tp1_hit": tp1_hit, "tp2_hit": tp2_hit,
                "bars_held": j - i_entry,
                "r": round(sgn * (exit_px - entry) / risk, 4)}

    last_j = i_entry
    for j in range(i_entry + 1, len(bars)):
        last_j = j
        b, aj = bars[j], atr[j] or a0
        hi, lo, close = b["h"], b["l"], b["c"]
        fav = hi if long else lo                       # favorable extreme
        adv = lo if long else hi                       # adverse extreme

        # 1. Trail update (Pine lines 466-474) — uses the current bar extreme
        if tp1_hit:
            tm = ladder["trail2"] if tp2_hit else trail_tp1
            cand = fav - sgn * aj * tm
            trail_sl = max(trail_sl, cand) if long else min(trail_sl, cand)
            sl = trail_sl

        # 2. TP1 — arm the trail with the break-even guarantee
        if not tp1_hit and (fav >= tp1 if long else fav <= tp1):
            tp1_hit = True
            cand = close - sgn * aj * trail_tp1
            trail_sl = max(cand, entry) if long else min(cand, entry)
            sl = trail_sl

        # 3. TP2 — tighten the trail
        if tp1_hit and not tp2_hit and (fav >= tp2 if long else fav <= tp2):
            tp2_hit = True
            cand = fav - sgn * aj * ladder["trail2"]
            trail_sl = max(trail_sl, cand) if long else min(trail_sl, cand)
            sl = trail_sl

        # 4. TP3 — full run, skips the SL check (Pine's closedTP3 guard)
        if tp1_hit and tp2_hit and (fav >= tp3 if long else fav <= tp3):
            return _book(tp3, "WIN", "TP3", j)

        # 5. SL / trailed stop. Gap-aware: an open through the stop fills
        #    at the open (Pine books the level; the gap fill is the honest
        #    price for validation).
        if (adv <= sl if long else adv >= sl):
            opn = b["o"]
            gap = (opn <= sl if long else opn >= sl)
            px = opn if gap else sl
            if not tp1_hit:
                return _book(px, "LOSS", "SL", j)
            return _book(px, "PARTIAL", "SL_TP2" if tp2_hit else "SL_TP1", j)

        if max_bars is not None and j - i_entry >= max_bars:
            return _book(close, "TIMEOUT", "TIMEOUT", j)

    return _book(bars[last_j]["c"], "TIMEOUT", "DATA_END", last_j)


def run_grid(bars: list[dict], tf_key: str, every: int = 10,
             max_bars: int | None = None, atr: list | None = None,
             directions: tuple = ("LONG", "SHORT")) -> list[dict]:
    """Signal-agnostic sweep: enter both directions every `every` bars.
    Measures the ladder's mechanics independent of entry edge."""
    ladder = TF_LADDERS[tf_key]
    atr = atr if atr is not None else wilder_atr(bars)
    first = next((i for i, a in enumerate(atr) if a is not None), len(bars))
    trades = []
    for i in range(first, len(bars) - 1, every):
        for d in directions:
            t = simulate_ladder(bars, atr, i, d, ladder, max_bars=max_bars)
            if t:
                trades.append(t)
    return trades


def summarize_trades(trades: list[dict]) -> dict:
    n = len(trades)
    if not n:
        return {"n": 0}
    outcomes: dict[str, int] = {}
    stages: dict[str, int] = {}
    for t in trades:
        outcomes[t["outcome"]] = outcomes.get(t["outcome"], 0) + 1
        stages[t["stage"]] = stages.get(t["stage"], 0) + 1
    rs = [t["r"] for t in trades]
    tp1 = sum(1 for t in trades if t["tp1_hit"])
    return {
        "n": n,
        "outcomes": outcomes,
        "stages": stages,
        "tp1_rate_pct": round(tp1 / n * 100, 1),
        "avg_r": round(sum(rs) / n, 3),
        "median_r": round(sorted(rs)[n // 2], 3),
        "avg_bars_held": round(sum(t["bars_held"] for t in trades) / n, 1),
    }
