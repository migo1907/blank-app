"""
Daily technical analysis commentary for SPY, QQQ, XAUUSD.
Runs at 08:00 UTC every weekday. Sends a clean price-level brief to Telegram.
"""
import os
import json
from datetime import datetime, timezone, timedelta
import anthropic

try:
    import yfinance as yf
    _YF_AVAILABLE = True
except ImportError:
    _YF_AVAILABLE = False

SYMBOLS = {
    "XAUUSD": {"ticker": "GC=F",  "label": "XAUUSD 🥇", "decimals": 2},
    "SPY":    {"ticker": "SPY",   "label": "SPY 📊",     "decimals": 2},
    "QQQ":    {"ticker": "QQQ",   "label": "QQQ 📊",     "decimals": 2},
}

ANALYSIS_PROMPT = """You are a professional institutional trader writing a daily pre-market technical brief.

For each asset below, write a SHORT (4-6 lines max) technical outlook for TODAY only.
Rules:
- Use ONLY the price levels provided — do not invent or round numbers
- Never mention indicator names (no RSI, MACD, ATR, Fibonacci, EMA, etc.)
- State key price levels naturally: "above X holds bullish", "break of X targets Y"
- Give one BULL scenario and one BEAR scenario with specific price targets
- Write in plain conversational English, no jargon
- Keep it tight — traders read this fast

Asset data:
{asset_data}

Format your response EXACTLY like this for each asset (replace placeholders):

🥇 XAUUSD
Price: $X,XXX.XX
Key levels: X,XXX / X,XXX / X,XXX
Bull: [1 sentence with target]
Bear: [1 sentence with target]
Range today: $X,XXX – $X,XXX

📊 SPY
Price: $XXX.XX
Key levels: XXX / XXX / XXX
Bull: [1 sentence with target]
Bear: [1 sentence with target]
Range today: $XXX – $XXX

📊 QQQ
Price: $XXX.XX
Key levels: XXX / XXX / XXX
Bull: [1 sentence with target]
Bear: [1 sentence with target]
Range today: $XXX – $XXX"""


def _fetch_levels(ticker_sym: str, decimals: int = 2) -> dict | None:
    """Fetch OHLCV and calculate pivot levels using yfinance."""
    if not _YF_AVAILABLE:
        return None
    try:
        tk   = yf.Ticker(ticker_sym)
        hist = tk.history(period="5d", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            return None

        prev  = hist.iloc[-2]   # yesterday (complete candle)
        today = hist.iloc[-1]   # today (may be incomplete)

        ph = float(prev["High"])
        pl = float(prev["Low"])
        pc = float(prev["Close"])

        # Classic pivot points from yesterday's OHLC
        pivot = (ph + pl + pc) / 3
        r1    = 2 * pivot - pl
        r2    = pivot + (ph - pl)
        r3    = ph + 2 * (pivot - pl)
        s1    = 2 * pivot - ph
        s2    = pivot - (ph - pl)
        s3    = pl - 2 * (ph - pivot)

        # Weekly range for broader context
        week_hist = tk.history(period="5d", interval="1d", auto_adjust=True)
        week_high = float(week_hist["High"].max())
        week_low  = float(week_hist["Low"].min())

        current = float(today["Close"]) if not today.empty else pc

        fmt = f"{{:.{decimals}f}}"
        return {
            "current":  round(current, decimals),
            "prev_high": round(ph, decimals),
            "prev_low":  round(pl, decimals),
            "prev_close": round(pc, decimals),
            "pivot": round(pivot, decimals),
            "r1":    round(r1, decimals),
            "r2":    round(r2, decimals),
            "r3":    round(r3, decimals),
            "s1":    round(s1, decimals),
            "s2":    round(s2, decimals),
            "s3":    round(s3, decimals),
            "week_high": round(week_high, decimals),
            "week_low":  round(week_low, decimals),
            "expected_range_low":  round(min(s2, current - (r1 - pivot)), decimals),
            "expected_range_high": round(max(r2, current + (r1 - pivot)), decimals),
        }
    except Exception as e:
        print(f"[daily] yfinance fetch failed for {ticker_sym}: {e}")
        return None


def _format_levels_for_prompt(levels: dict, label: str, decimals: int) -> str:
    """Format levels dict into a readable string for the Claude prompt."""
    fmt = f"{{:.{decimals}f}}"
    return (
        f"{label}\n"
        f"  Current price: {fmt.format(levels['current'])}\n"
        f"  Previous day H/L/C: {fmt.format(levels['prev_high'])} / {fmt.format(levels['prev_low'])} / {fmt.format(levels['prev_close'])}\n"
        f"  Pivot: {fmt.format(levels['pivot'])}\n"
        f"  Resistance: R1={fmt.format(levels['r1'])}  R2={fmt.format(levels['r2'])}  R3={fmt.format(levels['r3'])}\n"
        f"  Support:    S1={fmt.format(levels['s1'])}  S2={fmt.format(levels['s2'])}  S3={fmt.format(levels['s3'])}\n"
        f"  Week range: {fmt.format(levels['week_low'])} – {fmt.format(levels['week_high'])}\n"
        f"  Expected day range: {fmt.format(levels['expected_range_low'])} – {fmt.format(levels['expected_range_high'])}\n"
    )


def generate_daily_brief() -> str | None:
    """
    Fetch live price data for SPY, QQQ, XAUUSD, calculate pivot levels,
    and generate a clean daily brief via Claude.
    Returns formatted Telegram message string, or None on failure.
    """
    if not _YF_AVAILABLE:
        print("[daily] yfinance not installed — skipping daily brief.")
        return None

    asset_blocks = []
    for name, cfg in SYMBOLS.items():
        levels = _fetch_levels(cfg["ticker"], cfg["decimals"])
        if not levels:
            print(f"[daily] Could not fetch levels for {name} — skipping.")
            continue
        block = _format_levels_for_prompt(levels, cfg["label"], cfg["decimals"])
        asset_blocks.append(block)

    if not asset_blocks:
        print("[daily] No asset data fetched — aborting brief.")
        return None

    asset_data = "\n".join(asset_blocks)

    try:
        client   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
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

    now     = datetime.now(timezone.utc)
    weekday = now.strftime("%A")
    date_str = now.strftime("%d %b %Y")

    msg = (
        f"📅 <b>DAILY MARKET BRIEF — {weekday}, {date_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{analysis}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now.strftime('%H:%M UTC')} | Pre-market analysis"
    )
    return msg
