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

try:
    from tvdatafeed import TvDatafeed, Interval
    _TV_AVAILABLE = True
except ImportError:
    _TV_AVAILABLE = False

SYMBOLS_YF = {
    "SPY": {"ticker": "SPY", "label": "SPY 📊", "decimals": 2},
    "QQQ": {"ticker": "QQQ", "label": "QQQ 📊", "decimals": 2},
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


def _fetch_xauusd_tv(decimals: int = 2) -> dict | None:
    """Fetch XAUUSD OHLCV from TradingView (ICMARKETS) via tvdatafeed."""
    if not _TV_AVAILABLE:
        print("[daily] tvdatafeed not installed — cannot fetch XAUUSD.")
        return None
    try:
        tv   = TvDatafeed()
        df   = tv.get_hist("XAUUSD", "ICMARKETS", interval=Interval.in_daily, n_bars=5)
        if df is None or len(df) < 2:
            print("[daily] tvdatafeed returned insufficient data for XAUUSD.")
            return None

        prev    = df.iloc[-2]
        today   = df.iloc[-1]
        ph      = float(prev["high"])
        pl      = float(prev["low"])
        pc      = float(prev["close"])
        current = float(today["close"])

        return _calc_pivots(ph, pl, pc, current, decimals)
    except Exception as e:
        print(f"[daily] tvdatafeed fetch failed for XAUUSD: {e}")
        return None


def _fetch_levels_yf(ticker_sym: str, decimals: int = 2) -> dict | None:
    """Fetch OHLCV and calculate pivot levels using yfinance."""
    if not _YF_AVAILABLE:
        return None
    try:
        tk   = yf.Ticker(ticker_sym)
        hist = tk.history(period="5d", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 2:
            return None

        prev    = hist.iloc[-2]
        today   = hist.iloc[-1]
        ph      = float(prev["High"])
        pl      = float(prev["Low"])
        pc      = float(prev["Close"])
        current = float(today["Close"])

        return _calc_pivots(ph, pl, pc, current, decimals)
    except Exception as e:
        print(f"[daily] yfinance fetch failed for {ticker_sym}: {e}")
        return None


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


def generate_daily_brief() -> str | None:
    """
    Fetch live price data for XAUUSD (TradingView/ICMARKETS) and SPY/QQQ (yfinance),
    calculate pivot levels, and generate a clean daily brief via Claude.
    Returns formatted Telegram message string, or None on failure.
    """
    asset_blocks = []

    # XAUUSD from TradingView (ICMARKETS)
    xau_levels = _fetch_xauusd_tv(decimals=2)
    if xau_levels:
        asset_blocks.append(_format_levels_for_prompt(xau_levels, "XAUUSD 🥇", 2))
    else:
        print("[daily] XAUUSD data unavailable — skipping.")

    # SPY and QQQ from yfinance
    for name, cfg in SYMBOLS_YF.items():
        levels = _fetch_levels_yf(cfg["ticker"], cfg["decimals"])
        if levels:
            asset_blocks.append(_format_levels_for_prompt(levels, cfg["label"], cfg["decimals"]))
        else:
            print(f"[daily] Could not fetch levels for {name} — skipping.")

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

    now      = datetime.now(timezone.utc)
    weekday  = now.strftime("%A")
    date_str = now.strftime("%d %b %Y")

    msg = (
        f"📅 <b>DAILY MARKET Technical BRIEF — {weekday}, {date_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{analysis}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now.strftime('%H:%M UTC')} | Pre-market analysis"
    )
    return msg
