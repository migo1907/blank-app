"""
Daily technical analysis commentary for SPY, QQQ, XAUUSD.
Runs at 09:00 UTC (1 PM Dubai / UTC+4) every weekday.

Price source priority:
  1. GitHub raw daily_levels.json — pre-fetched by GitHub Actions at 07:50 UTC via TradingView
  2. TradingView live (tvdatafeed) — direct fetch if GitHub JSON missing/stale
  3. yfinance XAUUSD=X / SPY / QQQ — last resort fallback
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

SYMBOLS_TV = {
    "XAUUSD": ("XAUUSD", "ICMARKETS", 2, "XAUUSD 🥇"),
    "SPY":    ("SPY",    "AMEX",      2, "SPY 📊"),
    "QQQ":    ("QQQ",    "NASDAQ",    2, "QQQ 📊"),
}

SYMBOLS_YF_FALLBACK = {
    "XAUUSD": ["XAUUSD=X"],
    "SPY":    ["SPY"],
    "QQQ":    ["QQQ"],
}

ANALYSIS_PROMPT = """You are a professional institutional trader writing a daily pre-market technical brief.

For each asset below, write a concise technical outlook for TODAY only.
Rules:
- Use ONLY the price levels provided — do not invent or round numbers
- Never mention indicator names (no RSI, MACD, ATR, Fibonacci, EMA, etc.)
- State key price levels naturally: "above X holds bullish", "break of X targets Y"
- Give one BULL scenario and one BEAR scenario with specific price targets
- Write in plain conversational English, no jargon
- Keep it tight — traders read this fast

Asset data:
{asset_data}

Format your response EXACTLY like this for each asset (no deviations):

🥇 XAUUSD
Price: $X,XXX.XX
Expected today range : $X,XXX – $X,XXX
Key levels: X,XXX / X,XXX / X,XXX
📈 Bull: [1 sentence with specific price target]
📉 Bear: [1 sentence with specific price target]

📊 SPY
Price: $XXX.XX
Expected today range : $XXX – $XXX
Key levels: XXX / XXX / XXX
📈 Bull: [1 sentence with specific price target]
📉 Bear: [1 sentence with specific price target]

📊 QQQ
Price: $XXX.XX
Expected today range : $XXX – $XXX
Key levels: XXX / XXX / XXX
📈 Bull: [1 sentence with specific price target]
📉 Bear: [1 sentence with specific price target]"""


def _calc_pivots(ph, pl, pc, current, decimals):
    pivot = (ph + pl + pc) / 3
    r1    = 2 * pivot - pl
    r2    = pivot + (ph - pl)
    r3    = ph + 2 * (pivot - pl)
    s1    = 2 * pivot - ph
    s2    = pivot - (ph - pl)
    s3    = pl - 2 * (ph - pivot)
    return {
        "current":             round(current, decimals),
        "prev_high":           round(ph, decimals),
        "prev_low":            round(pl, decimals),
        "prev_close":          round(pc, decimals),
        "pivot":               round(pivot, decimals),
        "r1":                  round(r1, decimals),
        "r2":                  round(r2, decimals),
        "r3":                  round(r3, decimals),
        "s1":                  round(s1, decimals),
        "s2":                  round(s2, decimals),
        "s3":                  round(s3, decimals),
        "expected_range_low":  round(min(s2, current - (r1 - pivot)), decimals),
        "expected_range_high": round(max(r2, current + (r1 - pivot)), decimals),
    }


def _load_from_json() -> dict:
    """Fetch pre-fetched levels from GitHub (written by GitHub Actions at 07:50 UTC)."""
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
            prev  = df.iloc[-2]
            today = df.iloc[-1]
            return _calc_pivots(
                float(prev["high"]), float(prev["low"]), float(prev["close"]),
                float(today["close"]), decimals,
            )
        print(f"[daily] tvdatafeed: insufficient data for {symbol}/{exchange}.")
    except Exception as e:
        print(f"[daily] tvdatafeed failed for {symbol}/{exchange}: {e}")
    return None


def _fetch_levels_yf(ticker_sym: str, decimals: int) -> dict | None:
    if not _YF_AVAILABLE:
        return None
    try:
        tk   = yf.Ticker(ticker_sym)
        hist = tk.history(period="5d", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            return None
        prev  = hist.iloc[-2]
        today = hist.iloc[-1]
        return _calc_pivots(
            float(prev["High"]), float(prev["Low"]), float(prev["Close"]),
            float(today["Close"]), decimals,
        )
    except Exception as e:
        print(f"[daily] yfinance failed for {ticker_sym}: {e}")
    return None


def _fetch_asset(name: str, prefetched: dict) -> tuple[dict | None, int, str]:
    sym, exchange, decimals, label = SYMBOLS_TV[name]

    # Source 1: pre-fetched JSON from GitHub Actions
    if name in prefetched:
        print(f"[daily] {name}: using pre-fetched TradingView data.")
        return prefetched[name], decimals, label

    # Source 2: TradingView live (tvdatafeed) — same ICMARKETS/AMEX/NASDAQ feed.
    # No Yahoo fallback: all brief prices must come from TradingView only.
    levels = _fetch_levels_tv(sym, exchange, decimals)
    if levels:
        print(f"[daily] {name}: TradingView live ({exchange}) OK.")
        return levels, decimals, label

    print(f"[daily] {name}: TradingView sources failed — skipping (no non-TV fallback).")
    return None, decimals, label


def _format_levels_for_prompt(levels: dict, label: str, decimals: int) -> str:
    fmt = f"{{:.{decimals}f}}"
    return (
        f"{label}\n"
        f"  Current price: {fmt.format(levels['current'])}\n"
        f"  Previous day H/L/C: {fmt.format(levels['prev_high'])} / {fmt.format(levels['prev_low'])} / {fmt.format(levels['prev_close'])}\n"
        f"  Pivot: {fmt.format(levels['pivot'])}\n"
        f"  Resistance: R1={fmt.format(levels['r1'])}  R2={fmt.format(levels['r2'])}  R3={fmt.format(levels['r3'])}\n"
        f"  Support:    S1={fmt.format(levels['s1'])}  S2={fmt.format(levels['s2'])}  S3={fmt.format(levels['s3'])}\n"
        f"  Expected day range: {fmt.format(levels['expected_range_low'])} – {fmt.format(levels['expected_range_high'])}\n"
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
        # Look at today + tomorrow so late-US events (like FOMC) are visible at 09:00 UTC
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

    HIGH_IMPACT = {"high"}
    dubai_tz_offset = timedelta(hours=4)
    lines = []
    for ev in events:
        if (ev.get("impact") or "").lower() not in HIGH_IMPACT:
            continue
        if (ev.get("country") or "").upper() not in ("US", "USA", ""):
            continue
        try:
            ts_utc = datetime.fromisoformat(ev.get("time", "").replace(" ", "T"))
            if ts_utc.tzinfo is None:
                ts_utc = ts_utc.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        # Only today's events (UTC date)
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
    return "📆 <b>High-Impact Events Today (Dubai time):</b>\n" + "\n".join(lines)


def generate_daily_brief() -> str | None:
    """
    Fetch price levels (JSON → TradingView live → yfinance) and generate daily brief via Claude.
    Returns formatted Telegram message string, or None on failure.
    """
    prefetched  = _load_from_json()
    asset_blocks = []

    for name in ("XAUUSD", "SPY", "QQQ"):
        levels, decimals, label = _fetch_asset(name, prefetched)
        if levels:
            asset_blocks.append(_format_levels_for_prompt(levels, label, decimals))

    if not asset_blocks:
        print("[daily] No asset data fetched — aborting brief.")
        return None

    asset_data = "\n".join(asset_blocks)

    try:
        client   = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
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
    # US regular session opens 13:30 UTC; NY close 20:00 UTC
    if now.hour < 13 or (now.hour == 13 and now.minute < 30):
        session_label = "Pre-market analysis"
    elif now.hour < 20:
        session_label = "Regular session"
    else:
        session_label = "After-hours"

    calendar_block = _fetch_todays_high_impact_events()
    calendar_section = f"\n\n{calendar_block}" if calendar_block else ""

    msg = (
        f"📅 <b>DAILY MARKET Technical BRIEF — {weekday}, {date_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{analysis}{calendar_section}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now.strftime('%H:%M UTC')} | 1:00 PM Dubai | {session_label}"
    )
    return msg
