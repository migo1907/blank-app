#!/usr/bin/env python3
"""
Candlestick pattern backtest on XAUUSD_2M and XAUUSD_5M trade history.
Patterns: Engulfing, Hammer/Shooting Star, Doji
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import yfinance as yf
import pandas as pd


# ── helpers ──────────────────────────────────────────────────────────────────

def load_trades(tool_result_path):
    with open(tool_result_path) as f:
        wrapper = json.load(f)
    text = wrapper[1]['text']
    idx = text.index('[\n  {')
    return json.loads(text[idx:])


def closed_trades(trades):
    return [t for t in trades if t.get('outcome') in ('WIN', 'PARTIAL', 'LOSS')]


def parse_ts(ts_str):
    """Parse ISO timestamp → UTC datetime."""
    if not ts_str:
        return None
    try:
        ts_str = ts_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ── OHLCV fetching ────────────────────────────────────────────────────────────

_ohlcv_cache = {}  # key: (ticker, interval, date_key) -> df


def fetch_ohlcv(entry_dt: datetime, interval: str) -> pd.DataFrame | None:
    """
    Fetch ~3 hours of OHLCV around entry_dt. Returns df or None.
    Tries GC=F first, then XAUUSD=X.
    """
    # yfinance 2m/5m only goes back ~60 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=59)
    if entry_dt < cutoff:
        return None

    # Cache key: ticker+interval+day
    day_key = entry_dt.strftime('%Y-%m-%d')
    cache_key = (interval, day_key)
    if cache_key in _ohlcv_cache:
        return _ohlcv_cache[cache_key]

    start = entry_dt - timedelta(hours=2)
    end = entry_dt + timedelta(hours=2)

    for ticker in ['GC=F', 'XAUUSD=X']:
        try:
            df = yf.download(
                ticker,
                start=start.strftime('%Y-%m-%d %H:%M:%S'),
                end=end.strftime('%Y-%m-%d %H:%M:%S'),
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
            if df is not None and len(df) >= 2:
                df.index = pd.to_datetime(df.index, utc=True)
                _ohlcv_cache[cache_key] = df
                return df
        except Exception:
            continue

    _ohlcv_cache[cache_key] = None
    return None


def get_entry_candles(entry_dt: datetime, df: pd.DataFrame):
    """
    Return (prev_candle, entry_candle) as Series, or (None, None).
    Finds the bar whose open <= entry_dt < close (or nearest).
    """
    if df is None or len(df) < 2:
        return None, None

    # Find the bar index at or just before entry_dt
    idx = df.index.searchsorted(entry_dt, side='right') - 1
    if idx < 1 or idx >= len(df):
        return None, None

    prev_row = df.iloc[idx - 1]
    curr_row = df.iloc[idx]
    return prev_row, curr_row


# ── Pattern detection ─────────────────────────────────────────────────────────

def is_engulfing(prev, curr) -> bool:
    """
    Bull engulfing: prev is bearish, curr is bullish and fully engulfs prev body.
    Bear engulfing: prev is bullish, curr is bearish and fully engulfs prev body.
    """
    prev_open = float(prev['Open'])
    prev_close = float(prev['Close'])
    curr_open = float(curr['Open'])
    curr_close = float(curr['Close'])

    prev_bullish = prev_close > prev_open
    curr_bullish = curr_close > curr_open

    if prev_bullish and not curr_bullish:
        # Bear engulfing
        return curr_open > prev_close and curr_close < prev_open
    elif not prev_bullish and curr_bullish:
        # Bull engulfing
        return curr_open < prev_close and curr_close > prev_open
    return False


def is_hammer_shooting_star(candle) -> bool:
    """
    Hammer: lower wick >= 2× body, small upper wick, body in upper 1/3 of range.
    Shooting star: upper wick >= 2× body, small lower wick, body in lower 1/3.
    """
    o = float(candle['Open'])
    c = float(candle['Close'])
    h = float(candle['High'])
    l = float(candle['Low'])

    total_range = h - l
    if total_range < 1e-6:
        return False

    body = abs(c - o)
    body_top = max(o, c)
    body_bot = min(o, c)
    upper_wick = h - body_top
    lower_wick = body_bot - l

    if body < 1e-6:
        body = total_range * 0.01  # treat tiny body as 1% range

    # Hammer
    if lower_wick >= 2 * body and upper_wick <= body and body_bot >= l + total_range * (2/3):
        return True
    # Shooting star
    if upper_wick >= 2 * body and lower_wick <= body and body_top <= l + total_range * (1/3):
        return True

    return False


def is_doji(candle) -> bool:
    """Body <= 10% of total range."""
    o = float(candle['Open'])
    c = float(candle['Close'])
    h = float(candle['High'])
    l = float(candle['Low'])

    total_range = h - l
    if total_range < 1e-6:
        return True  # flat candle = doji

    body = abs(c - o)
    return body <= 0.10 * total_range


# ── Stats ──────────────────────────────────────────────────────────────────────

def compute_stats(group):
    """group: list of (is_win, pnl_pct)"""
    if not group:
        return dict(n=0, wr=0.0, avg_win=0.0, avg_loss=0.0, rr=0.0, score=0.0)

    wins = [p for w, p in group if w]
    losses = [p for w, p in group if not w]
    n = len(group)
    wr = len(wins) / n * 100
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
    rr = avg_win / avg_loss if avg_loss > 0 else float('inf')
    score = (wr / 100) * rr
    return dict(n=n, wr=wr, avg_win=avg_win, avg_loss=avg_loss, rr=rr, score=score)


def print_pattern_block(name, with_pattern, without_pattern):
    sw = compute_stats(with_pattern)
    swo = compute_stats(without_pattern)
    wr_edge = sw['wr'] - swo['wr']
    rr_edge = sw['rr'] - swo['rr']

    print(f"\n{name}")
    if sw['n'] == 0:
        print("  With pattern:    0 trades — no data")
    else:
        print(f"  With pattern:    {sw['n']:3d} trades | WR: {sw['wr']:.1f}% | "
              f"avg_win: {sw['avg_win']:.3f}% | avg_loss: {sw['avg_loss']:.3f}% | "
              f"R:R: {sw['rr']:.2f} | score: {sw['score']:.3f}")
    print(f"  Without pattern: {swo['n']:3d} trades | WR: {swo['wr']:.1f}% | "
          f"avg_win: {swo['avg_win']:.3f}% | avg_loss: {swo['avg_loss']:.3f}% | "
          f"R:R: {swo['rr']:.2f} | score: {swo['score']:.3f}")
    sign_wr = '+' if wr_edge >= 0 else ''
    sign_rr = '+' if rr_edge >= 0 else ''
    print(f"  Edge: {sign_wr}{wr_edge:.1f}pp win rate, {sign_rr}{rr_edge:.2f} R:R")


# ── Main backtest ─────────────────────────────────────────────────────────────

def run_backtest(trades, label, interval):
    closed = closed_trades(trades)
    print(f"\n{'='*55}")
    print(f"=== {label} Candlestick Pattern Backtest ===")
    print(f"{'='*55}")
    print(f"Total closed trades: {len(closed)}")

    # Buckets: pattern_name -> {'with': list, 'without': list}
    buckets = {
        'ENGULFING': {'with': [], 'without': []},
        'HAMMER/SHOOTING STAR': {'with': [], 'without': []},
        'DOJI': {'with': [], 'without': []},
    }

    matched = 0
    skipped_old = 0
    skipped_no_data = 0

    for trade in closed:
        entry_dt = parse_ts(trade.get('created_at'))
        if not entry_dt:
            skipped_no_data += 1
            continue

        df = fetch_ohlcv(entry_dt, interval)
        if df is None:
            skipped_old += 1
            continue

        prev_c, curr_c = get_entry_candles(entry_dt, df)
        if curr_c is None:
            skipped_no_data += 1
            continue

        matched += 1
        is_win = trade.get('outcome') in ('WIN', 'PARTIAL')
        pnl = float(trade.get('pnl_pct', 0.0))

        record = (is_win, pnl)

        # Engulfing needs prev candle
        engulf = is_engulfing(prev_c, curr_c) if prev_c is not None else False
        if engulf:
            buckets['ENGULFING']['with'].append(record)
        else:
            buckets['ENGULFING']['without'].append(record)

        hss = is_hammer_shooting_star(curr_c)
        if hss:
            buckets['HAMMER/SHOOTING STAR']['with'].append(record)
        else:
            buckets['HAMMER/SHOOTING STAR']['without'].append(record)

        doji = is_doji(curr_c)
        if doji:
            buckets['DOJI']['with'].append(record)
        else:
            buckets['DOJI']['without'].append(record)

    print(f"Trades with OHLCV data: {matched} / {len(closed)} total")
    print(f"  (skipped: {skipped_old} too old >60d, {skipped_no_data} no data/parse error)")

    for pattern_name, groups in buckets.items():
        print_pattern_block(pattern_name, groups['with'], groups['without'])


def main():
    base = '/root/.claude/projects/-home-user-blank-app/eaf97e7a-fb77-52c0-83c7-86a6fd1c0353/tool-results'

    trades_2m = load_trades(f'{base}/mcp-github-get_file_contents-1782126379538.txt')
    trades_5m = load_trades(f'{base}/mcp-github-get_file_contents-1782126379567.txt')

    run_backtest(trades_2m, 'XAUUSD_2M', '2m')
    run_backtest(trades_5m, 'XAUUSD_5M', '5m')

    print("\nDone.")


if __name__ == '__main__':
    main()
