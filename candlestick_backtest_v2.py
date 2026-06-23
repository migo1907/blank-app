#!/usr/bin/env python3
"""
Candlestick pattern backtest on XAUUSD_2M and XAUUSD_5M trade history.
Uses f22_body (body/range ratio, normalized [-1,+1]) stored in each trade record.

Since external OHLCV fetching (yfinance) is unavailable in this environment,
we use the body/range feature (f22_body) that Pine Script already computed and
stored at entry time — this is the actual value from TradingView, so it IS the
real entry-candle body ratio. It captures:

  DOJI:             |f22_body| <= 0.10  (body <= 10% of range)
  HAMMER/SHOOTING STAR proxy:
      Small body with imbalanced wicks. We approximate as |f22_body| <= 0.30
      AND body NOT in the 0-0.10 doji zone → 0.10 < |f22_body| <= 0.30
      (can't split upper/lower wick without raw OHLCV, but these are the
       candles where wick dominates the range)
  ENGULFING proxy:
      Strong body candle where direction aligns with trade direction.
      |f22_body| >= 0.70 AND body direction == trade direction.
      (real engulfing needs previous candle; this captures the same
       "conviction" signal — a full-body candle in your direction)

Additional analysis:
  BODY ALIGNMENT:   body direction matches trade direction (99%+ of entries)
  BODY STRENGTH TIERS: weak / moderate / strong / marubozu
"""
import json
import math
from collections import defaultdict


# ── helpers ──────────────────────────────────────────────────────────────────

def load_trades(path):
    with open(path) as f:
        wrapper = json.load(f)
    text = wrapper[1]['text']
    idx = text.index('[\n  {')
    return json.loads(text[idx:])


def closed_trades(trades):
    return [t for t in trades if t.get('outcome') in ('WIN', 'PARTIAL', 'LOSS')]


def is_win(trade):
    return trade.get('outcome') in ('WIN', 'PARTIAL')


# ── Pattern detectors (using f22_body) ───────────────────────────────────────

def pattern_doji(trade):
    """Body <= 10% of total range → |f22_body| <= 0.10"""
    body = abs(trade.get('f22_body', 0.5))
    return body <= 0.10


def pattern_hammer_ss(trade):
    """
    Wick-dominant candle: body between 10–30% of range.
    These are candles where wicks account for >=70% of range — the classic
    hammer/shooting star zone. Directional wick split unavailable without raw
    OHLCV, but the body size threshold is the canonical filter.
    """
    body = abs(trade.get('f22_body', 0.5))
    return 0.10 < body <= 0.30


def pattern_engulfing(trade):
    """
    Strong conviction candle in trade direction: |f22_body| >= 0.70.
    Proxy for engulfing / marubozu — same "strong close" signal.
    Body direction is verified to match trade direction.
    """
    f22 = trade.get('f22_body', 0.0)
    body = abs(f22)
    direction = trade.get('direction', '')
    body_bullish = f22 > 0
    aligned = (body_bullish and direction == 'LONG') or (not body_bullish and direction == 'SHORT')
    return body >= 0.70 and aligned


def pattern_body_aligned(trade):
    """Entry candle direction matches trade direction (most should pass)."""
    f22 = trade.get('f22_body', 0.0)
    direction = trade.get('direction', '')
    body_bullish = f22 > 0
    return (body_bullish and direction == 'LONG') or (not body_bullish and direction == 'SHORT')


# ── Stats ──────────────────────────────────────────────────────────────────────

def compute_stats(group):
    """group: list of (is_win, pnl_pct)"""
    if not group:
        return dict(n=0, wr=0.0, avg_win=0.0, avg_loss=0.0, rr=0.0, score=0.0)

    wins  = [p for w, p in group if w]
    losses = [abs(p) for w, p in group if not w]
    n = len(group)
    wr = len(wins) / n * 100
    avg_win  = sum(wins)   / len(wins)   if wins   else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    rr = avg_win / avg_loss if avg_loss > 0 else float('inf')
    score = (wr / 100) * rr
    return dict(n=n, wr=wr, avg_win=avg_win, avg_loss=avg_loss, rr=rr, score=score)


def fmt_rr(rr):
    return f"{rr:.2f}" if rr != float('inf') else "∞"


def print_pattern_block(name, with_pattern, without_pattern):
    sw  = compute_stats(with_pattern)
    swo = compute_stats(without_pattern)
    wr_edge = sw['wr'] - swo['wr']
    rr_edge = sw['rr'] - swo['rr'] if sw['rr'] != float('inf') and swo['rr'] != float('inf') else float('nan')
    sign_wr = '+' if wr_edge >= 0 else ''
    sign_rr = '+' if (not math.isnan(rr_edge) and rr_edge >= 0) else ''
    rr_edge_str = f"{sign_rr}{rr_edge:.2f}" if not math.isnan(rr_edge) else 'N/A'

    print(f"\n{name}")
    if sw['n'] == 0:
        print(f"  With pattern:      0 trades — no matches")
    else:
        print(f"  With pattern:    {sw['n']:4d} trades | WR: {sw['wr']:5.1f}% | "
              f"avg_win: {sw['avg_win']:.3f}% | avg_loss: {sw['avg_loss']:.3f}% | "
              f"R:R: {fmt_rr(sw['rr'])} | score: {sw['score']:.3f}")
    print(f"  Without pattern: {swo['n']:4d} trades | WR: {swo['wr']:5.1f}% | "
          f"avg_win: {swo['avg_win']:.3f}% | avg_loss: {swo['avg_loss']:.3f}% | "
          f"R:R: {fmt_rr(swo['rr'])} | score: {swo['score']:.3f}")
    print(f"  Edge: {sign_wr}{wr_edge:.1f}pp win rate, {rr_edge_str} R:R")


# ── Body-strength tier breakdown ─────────────────────────────────────────────

def body_tier(trade):
    body = abs(trade.get('f22_body', 0.0))
    if body <= 0.10:
        return 'doji (0–10%)'
    elif body <= 0.30:
        return 'wick-heavy (10–30%)'
    elif body <= 0.50:
        return 'moderate (30–50%)'
    elif body <= 0.70:
        return 'balanced (50–70%)'
    else:
        return 'strong (70–100%)'


TIER_ORDER = [
    'doji (0–10%)',
    'wick-heavy (10–30%)',
    'moderate (30–50%)',
    'balanced (50–70%)',
    'strong (70–100%)',
]


# ── Main backtest ─────────────────────────────────────────────────────────────

def run_backtest(trades, label):
    closed = closed_trades(trades)
    print(f"\n{'='*60}")
    print(f"=== {label} Candlestick Pattern Backtest ===")
    print(f"{'='*60}")
    print(f"Total closed trades: {len(closed)}")

    patterns = {
        'DOJI  (|body| <= 10% of range)': pattern_doji,
        'WICK-HEAVY / Hammer+SS proxy  (10–30% body)': pattern_hammer_ss,
        'STRONG BODY / Engulfing proxy  (|body| >= 70%, aligned)': pattern_engulfing,
        'BODY ALIGNED with trade direction': pattern_body_aligned,
    }

    for name, detector in patterns.items():
        with_pat  = []
        without_pat = []
        for t in closed:
            record = (is_win(t), float(t.get('pnl_pct', 0.0)))
            if detector(t):
                with_pat.append(record)
            else:
                without_pat.append(record)
        print_pattern_block(name, with_pat, without_pat)

    # Body-strength tier breakdown
    print(f"\n{'─'*60}")
    print("BODY STRENGTH TIERS (|f22_body| buckets)")
    print(f"{'─'*60}")
    tier_groups = defaultdict(list)
    for t in closed:
        tier = body_tier(t)
        tier_groups[tier].append((is_win(t), float(t.get('pnl_pct', 0.0))))

    print(f"  {'Tier':<32} {'N':>5}  {'WR':>6}  {'avg_win':>8}  {'avg_loss':>9}  {'R:R':>6}  {'score':>6}")
    print(f"  {'─'*32}  {'─'*5}  {'─'*6}  {'─'*8}  {'─'*9}  {'─'*6}  {'─'*6}")
    for tier in TIER_ORDER:
        g = tier_groups.get(tier, [])
        s = compute_stats(g)
        if s['n'] == 0:
            print(f"  {tier:<32}  {0:>5}  {'—':>6}")
            continue
        print(f"  {tier:<32}  {s['n']:>5}  {s['wr']:>5.1f}%  {s['avg_win']:>7.3f}%  {s['avg_loss']:>8.3f}%  {fmt_rr(s['rr']):>6}  {s['score']:>6.3f}")

    # Direction analysis (LONG vs SHORT)
    print(f"\n{'─'*60}")
    print("BY TRADE DIRECTION")
    print(f"{'─'*60}")
    for direction in ('LONG', 'SHORT'):
        group = [(is_win(t), float(t.get('pnl_pct',0))) for t in closed if t.get('direction') == direction]
        s = compute_stats(group)
        print(f"  {direction:<6}: {s['n']:>4} trades | WR: {s['wr']:.1f}% | avg_win: {s['avg_win']:.3f}% | avg_loss: {s['avg_loss']:.3f}% | R:R: {fmt_rr(s['rr'])} | score: {s['score']:.3f}")

    # STRONG BODY: LONG vs SHORT separately
    print(f"\n{'─'*60}")
    print("STRONG BODY (>=70%) × DIRECTION interaction")
    print(f"{'─'*60}")
    for direction in ('LONG', 'SHORT'):
        strong = [(is_win(t), float(t.get('pnl_pct',0))) for t in closed
                  if t.get('direction') == direction and abs(t.get('f22_body',0)) >= 0.70]
        weak   = [(is_win(t), float(t.get('pnl_pct',0))) for t in closed
                  if t.get('direction') == direction and abs(t.get('f22_body',0)) < 0.70]
        ss = compute_stats(strong)
        sw = compute_stats(weak)
        print(f"  {direction} + strong body: {ss['n']:>4} | WR: {ss['wr']:.1f}% | R:R: {fmt_rr(ss['rr'])} | score: {ss['score']:.3f}")
        print(f"  {direction} + weak body:   {sw['n']:>4} | WR: {sw['wr']:.1f}% | R:R: {fmt_rr(sw['rr'])} | score: {sw['score']:.3f}")

    # DOJI: are thin-body entries worse?
    print(f"\n{'─'*60}")
    print("DOJI × DIRECTION interaction")
    print(f"{'─'*60}")
    for direction in ('LONG', 'SHORT'):
        doji_g   = [(is_win(t), float(t.get('pnl_pct',0))) for t in closed
                    if t.get('direction') == direction and abs(t.get('f22_body',0)) <= 0.10]
        nodoji_g = [(is_win(t), float(t.get('pnl_pct',0))) for t in closed
                    if t.get('direction') == direction and abs(t.get('f22_body',0)) > 0.10]
        sd = compute_stats(doji_g)
        sn = compute_stats(nodoji_g)
        nd = sd['n']
        if nd > 0:
            print(f"  {direction} + doji:     {sd['n']:>4} | WR: {sd['wr']:.1f}% | R:R: {fmt_rr(sd['rr'])} | score: {sd['score']:.3f}")
        else:
            print(f"  {direction} + doji:        0")
        print(f"  {direction} + non-doji:  {sn['n']:>4} | WR: {sn['wr']:.1f}% | R:R: {fmt_rr(sn['rr'])} | score: {sn['score']:.3f}")


def main():
    base = '/root/.claude/projects/-home-user-blank-app/eaf97e7a-fb77-52c0-83c7-86a6fd1c0353/tool-results'

    trades_2m = load_trades(f'{base}/mcp-github-get_file_contents-1782126379538.txt')
    trades_5m = load_trades(f'{base}/mcp-github-get_file_contents-1782126379567.txt')

    run_backtest(trades_2m, 'XAUUSD_2M')
    run_backtest(trades_5m, 'XAUUSD_5M')

    print(f"\n{'='*60}")
    print("METHODOLOGY NOTE")
    print(f"{'='*60}")
    print("""
Feature used: f22_body = (close-open)/(high-low) normalized to [-1,+1]
  - Positive = bullish candle, negative = bearish candle
  - |f22_body| = body as fraction of total range

Pattern definitions (f22_body proxy):
  DOJI:        |f22_body| <= 0.10  (body <= 10% of candle range)
  HAMMER/SS:   0.10 < |f22_body| <= 0.30  (wick-dominant, body 10-30%)
  ENGULFING:   |f22_body| >= 0.70 AND body direction == trade direction
               (strong body candle in signal direction — same "conviction" signal)

Source: f22_body is computed by Pine Script on the entry bar and stored at
        signal-entry time. It is the actual TradingView candle value.
        yfinance OHLCV was unavailable (network blocked in this environment).
""")


if __name__ == '__main__':
    main()
