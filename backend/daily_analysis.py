"""
Daily technical analysis commentary for SPY, QQQ, XAUUSD.
Runs at 09:00 UTC (1 PM Dubai / UTC+4) every weekday.

Price source priority for pivot levels:
  1. GitHub raw daily_levels.json — pre-fetched by GitHub Actions at 07:50 UTC via TradingView
  2. TradingView live (tvdatafeed) — direct fetch if GitHub JSON missing/stale

Live price at send time (gap-aware):
  yfinance fast_info — includes pre-market for SPY/QQQ, live spot for XAUUSD
"""
import os
import json
from datetime import datetime, timezone, timedelta
import anthropic
import httpx

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

try:
    from tvdatafeed import TvDatafeed, Interval
    _TV_AVAILABLE = True
except ImportError:
    _TV_AVAILABLE = False

# GitHub raw URL for pre-fetched levels (updated by GitHub Actions at 07:50 UTC)
_LEVELS_URL = (
    "https://raw.githubusercontent.com/migo1907/blank-app/"
    "data/data/daily_levels.json"
)

# yfinance tickers for live price lookup
_YF_LIVE = {
    "XAUUSD": ["XAUUSD=X", "GC=F"],
    "SPY":    ["SPY"],
    "QQQ":    ["QQQ"],
}

SYMBOLS_TV = {
    "XAUUSD": ("XAUUSD", "ICMARKETS", 2, "XAUUSD 🥇"),
    "SPY":    ("SPY",    "AMEX",      2, "SPY 📊"),
    "QQQ":    ("QQQ",    "NASDAQ",    2, "QQQ 📊"),
}

ANALYSIS_PROMPT = """You are a senior institutional trader writing a concise morning market brief for professional traders.

Asset data (live prices, prev-session OHLC, pivot levels, plus a proprietary directional read and trend/momentum/range stats):
{asset_data}

Rules:
- Open with ONE sentence covering the cross-asset risk tone (all three together).
- For each asset: state the live price and gap, the directional bias %, trend, where price sits vs pivot, 2–3 actionable levels, one bull and one bear scenario with real numbers.
- Use the provided "Signal bias", "Trend", "Momentum", and "Range position" numbers directly. Present them as the desk's own read.
- CRITICAL: NEVER reveal, name, or hint at how any number is produced. No mention of models, machine learning, KNN, RF, GBM, ensembles, algorithms, RSI, MACD, EMA, ATR, moving averages, or any indicator/method name. Just state the numbers as conclusions.
- Be direct. No filler. Prices with $ and comma formatting.
- Arrow ↑ for positive gap, ↓ for negative gap.

Output EXACTLY this format — no extra lines, no deviations, use HTML bold tags as shown:

📊 <b>Market Tone:</b> [1 sentence]

──────────────────────
🥇 <b>XAUUSD</b>
<b>$X,XXX.XX</b>  [↑/↓] [+/-X.XX] ([+/-X.XX]%) · Prev close $X,XXX.XX
🎯 Bias: <b>[Bullish/Bearish] NN%</b> · [Uptrend/Downtrend/Mixed] · Momentum [+/-X.X]%
📍 Pivot <b>$X,XXX.XX</b> · [Above → Bullish / Below → Bearish]
🔴 R1 $X,XXX · R2 $X,XXX · R3 $X,XXX
🟢 S1 $X,XXX · S2 $X,XXX · S3 $X,XXX
📈 <b>Bull:</b> [trigger] → $X,XXX then $X,XXX
📉 <b>Bear:</b> [trigger] → $X,XXX then $X,XXX

──────────────────────
📈 <b>SPY</b>
<b>$XXX.XX</b>  [↑/↓] [+/-X.XX] ([+/-X.XX]%) · Prev close $XXX.XX
🎯 Bias: <b>[Bullish/Bearish] NN%</b> · [Uptrend/Downtrend/Mixed] · Momentum [+/-X.X]%
📍 Pivot <b>$XXX.XX</b> · [Above → Bullish / Below → Bearish]
🔴 R1 $XXX · R2 $XXX · R3 $XXX
🟢 S1 $XXX · S2 $XXX · S3 $XXX
📈 <b>Bull:</b> [trigger] → $XXX then $XXX
📉 <b>Bear:</b> [trigger] → $XXX then $XXX

──────────────────────
📊 <b>QQQ</b>
<b>$XXX.XX</b>  [↑/↓] [+/-X.XX] ([+/-X.XX]%) · Prev close $XXX.XX
🎯 Bias: <b>[Bullish/Bearish] NN%</b> · [Uptrend/Downtrend/Mixed] · Momentum [+/-X.X]%
📍 Pivot <b>$XXX.XX</b> · [Above → Bullish / Below → Bearish]
🔴 R1 $XXX · R2 $XXX · R3 $XXX
🟢 S1 $XXX · S2 $XXX · S3 $XXX
📈 <b>Bull:</b> [trigger] → $XXX then $XXX
📉 <b>Bear:</b> [trigger] → $XXX then $XXX"""


def _calc_pivots(ph, pl, pc, decimals):
    """Calculate classic floor-trader daily pivots from previous session H/L/C."""
    pivot = (ph + pl + pc) / 3
    r1    = 2 * pivot - pl
    r2    = pivot + (ph - pl)
    r3    = ph + 2 * (pivot - pl)
    s1    = 2 * pivot - ph
    s2    = pivot - (ph - pl)
    s3    = pl - 2 * (ph - pivot)
    return {
        "prev_high":  round(ph, decimals),
        "prev_low":   round(pl, decimals),
        "prev_close": round(pc, decimals),
        "pivot":      round(pivot, decimals),
        "r1":         round(r1, decimals),
        "r2":         round(r2, decimals),
        "r3":         round(r3, decimals),
        "s1":         round(s1, decimals),
        "s2":         round(s2, decimals),
        "s3":         round(s3, decimals),
    }


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI from a list of closes. Returns None if not enough data."""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        chg = closes[i] - closes[i - 1]
        gains.append(max(chg, 0.0))
        losses.append(max(-chg, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _technical_context(name: str, decimals: int) -> dict | None:
    """
    Derive daily-bar technical context for the brief: moving-average trend,
    momentum, RSI band, range position, ATR-based expected range, and a single
    composite directional bias (0–100% bullish). Self-contained — no DB writes,
    no dependency on intraday heartbeat features. Returns None if data unavailable.
    """
    if not _YF_AVAILABLE:
        return None
    for sym in _YF_LIVE.get(name, []):
        try:
            df = yf.Ticker(sym).history(period="1y", interval="1d")
            if df is None or len(df) < 60:
                continue
            highs  = [float(x) for x in df["High"].tolist()]
            lows   = [float(x) for x in df["Low"].tolist()]
            closes = [float(x) for x in df["Close"].tolist()]
            last   = closes[-1]

            def _ma(n: int) -> float | None:
                return sum(closes[-n:]) / n if len(closes) >= n else None

            ma20, ma50, ma200 = _ma(20), _ma(50), _ma(200)

            # 20-day momentum %
            mom20 = ((last / closes[-21]) - 1.0) * 100 if len(closes) >= 21 else 0.0

            rsi = _rsi(closes) or 50.0

            # Range position over the last 60 sessions (0 = at lows, 100 = at highs)
            win_hi = max(highs[-60:])
            win_lo = min(lows[-60:])
            rng_pos = ((last - win_lo) / (win_hi - win_lo) * 100) if win_hi > win_lo else 50.0

            # ATR(14) on daily bars → typical daily range
            trs = []
            for i in range(1, len(closes)):
                tr = max(highs[i] - lows[i],
                         abs(highs[i] - closes[i - 1]),
                         abs(lows[i] - closes[i - 1]))
                trs.append(tr)
            atr = sum(trs[-14:]) / 14 if len(trs) >= 14 else (sum(trs) / len(trs) if trs else 0.0)

            # Trend alignment score (0–1): price vs MAs + MA stacking
            checks, hits = 0, 0
            for m in (ma20, ma50, ma200):
                if m is not None:
                    checks += 1
                    hits += 1 if last > m else 0
            if ma20 and ma50:
                checks += 1; hits += 1 if ma20 > ma50 else 0
            if ma50 and ma200:
                checks += 1; hits += 1 if ma50 > ma200 else 0
            trend_score = (hits / checks) if checks else 0.5

            def _clamp(v, lo=-1.0, hi=1.0):
                return max(lo, min(hi, v))

            # Composite directional bias (0–1 bullish)
            bias = (
                0.50
                + 0.25 * (trend_score * 2 - 1)
                + 0.15 * _clamp(mom20 / 10.0)
                + 0.10 * _clamp((rsi - 50) / 30.0)
            )
            bias = max(0.02, min(0.98, bias))

            fmt = f"{{:.{decimals}f}}"
            trend_words = (
                "Uptrend" if trend_score >= 0.7 else
                "Downtrend" if trend_score <= 0.3 else
                "Mixed"
            )
            rsi_band = (
                "overbought" if rsi >= 70 else
                "oversold" if rsi <= 30 else
                "neutral"
            )
            return {
                "bias_pct":   round(bias * 100),
                "direction":  "Bullish" if bias >= 0.5 else "Bearish",
                "trend":      trend_words,
                "ma20":       fmt.format(ma20) if ma20 else "n/a",
                "ma50":       fmt.format(ma50) if ma50 else "n/a",
                "ma200":      fmt.format(ma200) if ma200 else "n/a",
                "mom20":      f"{mom20:+.1f}",
                "rsi":        round(rsi),
                "rsi_band":   rsi_band,
                "range_pos":  round(rng_pos),
                "atr":        fmt.format(atr),
            }
        except Exception as e:
            print(f"[daily] technical context {sym} failed: {e}")
    return None


def _fetch_live_price(name: str, decimals: int) -> float | None:
    """
    Fetch the current live/pre-market price via yfinance fast_info.
    For SPY/QQQ this includes pre-market. For XAUUSD this is the live spot price.
    Returns None if unavailable.
    """
    if not _YF_AVAILABLE:
        return None
    tickers = _YF_LIVE.get(name, [])
    for sym in tickers:
        try:
            tk = yf.Ticker(sym)
            fi = tk.fast_info
            # fast_info.last_price reflects pre/post-market when available
            price = getattr(fi, "last_price", None)
            if price and float(price) > 0:
                return round(float(price), decimals)
        except Exception as e:
            print(f"[daily] live price {sym} failed: {e}")
    return None


def _load_from_json() -> dict:
    """Fetch pre-fetched pivot levels from GitHub (written by GitHub Actions at 07:50 UTC)."""
    try:
        resp = httpx.get(_LEVELS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        fetched_at = data.get("fetched_at", "unknown")
        assets = data.get("assets", {})
        if assets:
            print(f"[daily] Fetched pre-built levels from GitHub (fetched_at={fetched_at}): {list(assets.keys())}")
        return assets
    except Exception as e:
        print(f"[daily] Failed to fetch daily_levels.json from GitHub: {e}")
        return {}


def _fetch_levels_tv(symbol: str, exchange: str, decimals: int) -> dict | None:
    if not _TV_AVAILABLE:
        return None
    try:
        tv = TvDatafeed()
        df = tv.get_hist(symbol, exchange, interval=Interval.in_daily, n_bars=5)
        if df is not None and len(df) >= 2:
            prev = df.iloc[-2]
            return _calc_pivots(
                float(prev["high"]), float(prev["low"]), float(prev["close"]), decimals,
            )
        print(f"[daily] tvdatafeed: insufficient data for {symbol}/{exchange}.")
    except Exception as e:
        print(f"[daily] tvdatafeed failed for {symbol}/{exchange}: {e}")
    return None


def _fetch_asset(name: str, prefetched: dict) -> tuple[dict | None, int, str]:
    sym, exchange, decimals, label = SYMBOLS_TV[name]

    # Source 1: pre-fetched JSON from GitHub Actions (pivot levels only, no live price)
    if name in prefetched:
        print(f"[daily] {name}: using pre-fetched TradingView pivot data.")
        levels = prefetched[name]
        # Strip old "current" field — we'll replace with live price below
        levels = {k: v for k, v in levels.items() if k != "current"}
        # Recalculate clean pivots in case the stored format differs
        if all(k in levels for k in ("prev_high", "prev_low", "prev_close")):
            levels = _calc_pivots(levels["prev_high"], levels["prev_low"], levels["prev_close"], decimals)
        return levels, decimals, label

    # Source 2: TradingView live
    levels = _fetch_levels_tv(sym, exchange, decimals)
    if levels:
        print(f"[daily] {name}: TradingView live ({exchange}) OK.")
        return levels, decimals, label

    print(f"[daily] {name}: all pivot sources failed — skipping.")
    return None, decimals, label


def _format_levels_for_prompt(name: str, levels: dict, live_price: float | None, label: str,
                              decimals: int, tech: dict | None = None) -> str:
    fmt = f"{{:.{decimals}f}}"
    pc  = levels["prev_close"]

    # Gap analysis vs previous close
    if live_price and pc:
        gap_abs = live_price - pc
        gap_pct = (gap_abs / pc) * 100
        gap_str = f"{'+' if gap_abs >= 0 else ''}{fmt.format(gap_abs)} ({'+' if gap_pct >= 0 else ''}{gap_pct:.2f}%)"
        is_significant = abs(gap_pct) >= 0.20
    else:
        live_price = pc  # fallback to prev close if live unavailable
        gap_str = "n/a"
        is_significant = False

    pivot = levels["pivot"]
    bias  = "above pivot → bullish intraday bias" if live_price > pivot else "below pivot → bearish intraday bias"

    # Macro context for gold
    macro_line = ""
    if name == "XAUUSD":
        try:
            from market_macro import get_macro_bias
            m = get_macro_bias()
            macro_line = f"  Macro bias: {m.get('label', 'n/a')} ({m.get('bias', 0):+.2f})\n"
        except Exception:
            pass

    gap_note = " ← significant gap" if is_significant else ""

    # Derived daily technical read (source not disclosed in the brief output)
    tech_line = ""
    if tech:
        tech_line = (
            f"  Signal bias: {tech['direction']} {tech['bias_pct']}%\n"
            f"  Trend: {tech['trend']} (20D MA {tech['ma20']}, 50D MA {tech['ma50']}, 200D MA {tech['ma200']})\n"
            f"  Momentum: 20-day {tech['mom20']}% · RSI {tech['rsi']} ({tech['rsi_band']})\n"
            f"  Range position: {tech['range_pos']}% of 60-day range · typical daily move {tech['atr']}\n"
        )

    return (
        f"{label}\n"
        f"  Live price: {fmt.format(live_price)}\n"
        f"  Prev close: {fmt.format(pc)}\n"
        f"  Gap: {gap_str}{gap_note}\n"
        f"  Pivot: {fmt.format(pivot)} — price is {bias}\n"
        f"  Resistance: R1={fmt.format(levels['r1'])}  R2={fmt.format(levels['r2'])}  R3={fmt.format(levels['r3'])}\n"
        f"  Support:    S1={fmt.format(levels['s1'])}  S2={fmt.format(levels['s2'])}  S3={fmt.format(levels['s3'])}\n"
        f"{tech_line}"
        f"{macro_line}"
    )


def _fetch_todays_high_impact_events() -> str:
    """
    Fetch today's high-impact economic events from Finnhub calendar.
    Returns a formatted string for the brief, or "" if none / unavailable.
    """
    from news_fetcher import FINNHUB_KEY, _FINNHUB_CALENDAR_URL
    if not FINNHUB_KEY:
        return ""
    try:
        now   = datetime.now(timezone.utc)
        today = now.date().isoformat()
        until = (now + timedelta(days=1)).date().isoformat()
        with httpx.Client(timeout=10) as client:
            resp = client.get(_FINNHUB_CALENDAR_URL, params={
                "from": today, "to": until, "token": FINNHUB_KEY,
            })
            resp.raise_for_status()
            events = resp.json().get("economicCalendar", []) or []
    except Exception as e:
        if "403" not in str(e):
            print(f"[daily_brief] calendar fetch failed: {e}")
        return ""

    dubai_tz_offset = timedelta(hours=4)
    lines = []
    for ev in events:
        if (ev.get("impact") or "").lower() != "high":
            continue
        if (ev.get("country") or "").upper() not in ("US", "USA", ""):
            continue
        try:
            ts_utc = datetime.fromisoformat(ev.get("time", "").replace(" ", "T"))
            if ts_utc.tzinfo is None:
                ts_utc = ts_utc.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if ts_utc.date() != now.date():
            continue
        ts_dubai = ts_utc + dubai_tz_offset
        time_str = ts_dubai.strftime("%I:%M %p")
        name     = ev.get("event", "Event")
        estimate = ev.get("estimate")
        actual   = ev.get("actual")
        detail   = ""
        if actual is not None:
            detail = f" · Actual: {actual}"
        elif estimate is not None:
            detail = f" · Est: {estimate}"
        lines.append(f"  • {time_str} — {name}{detail}")

    if not lines:
        return ""
    return "📆 <b>Key Events Today (Dubai time):</b>\n" + "\n".join(lines)


def generate_daily_brief() -> str | None:
    """
    Fetch pivot levels + live prices and generate institutional daily brief via Claude.
    Returns formatted Telegram message string, or None on failure.
    """
    prefetched   = _load_from_json()
    asset_blocks = []

    for name in ("XAUUSD", "SPY", "QQQ"):
        levels, decimals, label = _fetch_asset(name, prefetched)
        if not levels:
            continue
        live_price = _fetch_live_price(name, decimals)
        if live_price:
            print(f"[daily] {name}: live price = {live_price}")
        else:
            print(f"[daily] {name}: live price unavailable — using prev close")
        tech = _technical_context(name, decimals)
        if tech:
            print(f"[daily] {name}: signal bias {tech['direction']} {tech['bias_pct']}% · {tech['trend']}")
        asset_blocks.append(_format_levels_for_prompt(name, levels, live_price, label, decimals, tech))

    if not asset_blocks:
        print("[daily] No asset data fetched — aborting brief.")
        return None

    asset_data = "\n".join(asset_blocks)

    try:
        client   = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            messages=[{
                "role": "user",
                "content": ANALYSIS_PROMPT.format(asset_data=asset_data),
            }],
        )
        analysis = response.content[0].text.strip()
    except Exception as e:
        print(f"[daily] Claude generation failed: {e}")
        return None

    now      = datetime.now(timezone.utc)
    weekday  = now.strftime("%A")
    date_str = now.strftime("%d %b %Y")
    if now.hour < 13 or (now.hour == 13 and now.minute < 30):
        session_label = "Pre-market"
    elif now.hour < 20:
        session_label = "Regular session"
    else:
        session_label = "After-hours"

    calendar_block   = _fetch_todays_high_impact_events()
    calendar_section = f"\n\n{calendar_block}" if calendar_block else ""

    msg = (
        f"📅 <b>MORNING BRIEF — {weekday}, {date_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{analysis}{calendar_section}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now.strftime('%H:%M')} UTC  ·  1:00 PM Dubai  ·  {session_label}"
    )
    return msg
