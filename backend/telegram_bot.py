import os
import html
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

# Display name overrides — map broker/feed tickers to canonical names shown in Telegram
_DISPLAY_NAME: dict[str, str] = {
    "US500":  "SPX500",
    "SP500":  "SPX500",
}

load_dotenv()

TOKEN           = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID         = os.environ.get("TELEGRAM_CHAT_ID", "")
PERSONAL_CHAT_ID = os.environ.get("TELEGRAM_PERSONAL_CHAT_ID", "966897595")

TRIGGER_NAMES = {
    "RSI":  "RSI Momentum Cross",
    "FVG":  "Fair Value Gap",
    "LIQ":  "Liquidity Sweep",
    "OB":   "Order Block Bounce",
    "BOS":  "Break of Structure",
}


async def _send(text: str) -> bool:
    if not TOKEN or not CHAT_ID:
        print("[telegram] TOKEN or CHAT_ID not set — skipping.")
        return False
    import asyncio as _asyncio
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id":    CHAT_ID,
                    "text":       text,
                    "parse_mode": "HTML",
                })
                resp.raise_for_status()
                return True
        except Exception as e:
            if attempt < 2:
                wait = 1 if attempt == 0 else 3
                print(f"[telegram] Send failed (attempt {attempt+1}/3): {e} — retrying in {wait}s")
                await _asyncio.sleep(wait)
            else:
                print(f"[telegram] Send failed after 3 attempts: {e}")
    return False


async def send_entry_signal(s: dict) -> bool:
    """Send a clean entry signal message — fires instantly when trade opens."""
    direction = s.get("direction", "LONG")
    tf        = s.get("timeframe", "5")
    symbol    = s.get("symbol", "XAUUSD")
    entry     = s.get("entry_price", 0.0)
    tp1       = s.get("tp1", 0.0)
    tp2       = s.get("tp2", 0.0)
    tp3       = s.get("tp3", 0.0)
    sl        = s.get("sl", 0.0)
    tier      = s.get("tier", "LOW")

    dir_emoji    = "🟢" if direction == "LONG" else "🔴"
    symbol_clean = html.escape(_DISPLAY_NAME.get(symbol.split(":")[-1].upper(), symbol.split(":")[-1]))
    is_gold      = symbol_clean in ("XAUUSD", "GOLD", "GC")
    asset_emoji  = "🥇" if is_gold else "📊"
    now          = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")

    strength_map = {"HIGH": "🔥 HIGH", "MED": "✅ MED", "LOW": "⚡ LOW"}
    strength_str = strength_map.get(tier.upper(), "⚡ LOW")

    htf_context  = s.get("htf_context", "")
    tf_label_map = {"2": "2M", "5": "5M", "15": "15M", "30": "30M", "60": "1H", "240": "4H"}
    tf_display   = tf_label_map.get(str(tf), f"{tf}M")
    htf_badge    = " 🏔 HTF" if htf_context == "htf_direct" else ""

    # Backend ML quality grade — P(reach TP1+) from KNN+RF+GBM (annotate-only).
    q_score  = s.get("quality_score")
    q_reason = s.get("quality_reason", "")
    if q_reason in ("no_features_cached", "cold_start_bypass") or q_score is None:
        quality_line = "🧠 ML Quality: — (model warming up)\n"
    elif q_score >= 0.55:
        quality_line = f"🧠 ML Quality: 🔥 STRONG ({q_score*100:.0f}%)\n"
    elif q_score >= 0.40:
        quality_line = f"🧠 ML Quality: ✅ FAIR ({q_score*100:.0f}%)\n"
    else:
        quality_line = f"🧠 ML Quality: ⚠️ WEAK ({q_score*100:.0f}%) — similar setups mostly stopped out\n"

    msg = (
        f"{dir_emoji} <b>{direction} SIGNAL{htf_badge}</b> — {asset_emoji} {symbol_clean}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Timeframe: {tf_display}\n"
        f"Strength:  {strength_str}\n"
        f"{quality_line}\n"
        f"📍 Entry:  {entry:.2f}\n"
        f"🎯 TP1:    {tp1:.2f}\n"
        f"🎯 TP2:    {tp2:.2f}\n"
        f"🚀 TP3:    {tp3:.2f}\n"
        f"🛑 SL:     {sl:.2f}\n\n"
        f"⏰ {now}"
    )
    return await _send(msg)


async def send_signal(signal: dict) -> bool:
    """Send a direction change alert — fires only when market direction flips."""
    direction  = signal.get("direction", "NEUTRAL")
    confidence = signal.get("confidence", 0.0)
    symbol     = _DISPLAY_NAME.get(signal.get("symbol", "XAUUSD").split(":")[-1].upper(),
                                   signal.get("symbol", "XAUUSD").split(":")[-1])
    session    = signal.get("session", "")
    event      = signal.get("high_impact_event", "")

    dir_emoji  = "🟢" if direction == "LONG" else "🔴"
    is_gold    = symbol in ("XAUUSD", "GOLD", "GC")
    asset_emoji = "🥇" if is_gold else "📊"
    now        = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")

    session_map = {
        "OVERLAP":        "London/NY Overlap",
        "LONDON":         "London",
        "NEW_YORK":       "New York",
        "NY_LATE":        "New York Late",
        "ASIAN":          "Asian",
        "NYSE_OPEN":      "NYSE Open",
        "NYSE_AFTERNOON": "NYSE Afternoon",
        "PRE_MARKET":     "Pre-Market",
        "CLOSED":         "Closed",
    }
    sess_label = session_map.get(session, session)

    msg = (
        f"{dir_emoji} <b>{direction} — {asset_emoji} {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Confidence: <b>{confidence*100:.0f}%</b>\n"
        f"Session: {sess_label}\n"
    )
    if event:
        msg += f"⚡ {html.escape(event)}\n"
    msg += f"\n⏰ {now}"
    return await _send(msg)


async def send_text(text: str) -> None:
    """Send a plain text message."""
    await _send(text)


async def send_breaking_news(items: list[dict], seen_headlines: set) -> set:
    """
    Send FinancialJuice high-impact (red) breaking news to Telegram instantly.
    Only skips headlines already sent before (dedup by title).
    Returns a NEW set (copy + new items) so the caller can detect changes via !=.
    """
    new_items = [i for i in items if i["title"][:80] not in seen_headlines]
    if not new_items:
        return seen_headlines  # same object → caller knows nothing changed

    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = "\n".join(f"🔴 {item['title']}" for item in new_items[:5])

    msg = (
        f"🚨 <b>BREAKING NEWS</b> — {now}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{lines}\n\n"
        f"⚡ <i>High-impact market news via FinancialJuice</i>"
    )
    await _send(msg)

    # Return a NEW set so the caller's identity check (updated != _fj_seen_headlines)
    # correctly detects that new headlines were added and GitHub must be saved.
    updated = set(seen_headlines)
    for item in new_items:
        updated.add(item["title"][:80])
    return updated


async def send_stocks_session_report() -> bool:
    """
    Send end-of-session report for all stock trades closed today (WIN/LOSS only).
    Pulls from pool-specific trade history files on GitHub data branch.
    """
    from db import _get_file
    from datetime import datetime, timezone, date

    today = date.today().isoformat()
    stock_pools = [
        "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_1H", "STOCKS_MOMENTUM_4H",
        "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_1H",  "STOCKS_QUALITY_4H",
        "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_1H",    "STOCKS_INDEX_4H",
        "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_1H",      "STOCKS_QQQ_4H",
        "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_1H",   "STOCKS_SPX500_4H",
    ]

    trades_today = []
    for pool in stock_pools:
        path = f"data/trade_history_{pool}.json"
        history, _ = _get_file(path)
        if not isinstance(history, list):
            continue
        for t in history:
            created = t.get("created_at", "")
            if not created.startswith(today):
                continue
            outcome = t.get("outcome", "")
            if outcome not in ("WIN", "LOSS", "PARTIAL"):
                continue
            trades_today.append(t)

    if not trades_today:
        print("[session_report] No stock trades today — skipping report.")
        return False

    wins   = [t for t in trades_today if t["outcome"] in ("WIN", "PARTIAL")]
    losses = [t for t in trades_today if t["outcome"] == "LOSS"]
    total  = len(trades_today)
    wr     = len(wins) / total * 100

    def _tp_label(t: dict) -> str:
        tp = t.get("tp_stage", "").upper()
        outcome = t.get("outcome", "")
        if outcome == "WIN":
            return "TP3 🚀" if not tp else f"{tp} 🚀"
        if outcome == "PARTIAL":
            if "3" in tp: return "TP3 🚀"
            if "2" in tp: return "TP2 🎯"
            return "TP1 🎯"
        return "SL 🛑"

    lines = []
    for t in trades_today:
        sym     = t.get("symbol", "?")
        entry   = t.get("entry_price", 0.0)
        outcome = t.get("outcome", "?")
        direct  = t.get("direction", "?")
        pnl     = t.get("pnl_pct", 0.0)
        tp_lbl  = _tp_label(t)
        emoji   = "✅" if outcome in ("WIN", "PARTIAL") else "❌"
        dir_e   = "🟢" if direct == "LONG" else "🔴"
        tf_raw  = str(t.get("timeframe", "?"))
        tf_disp = {"15": "15M", "30": "30M", "60": "1H", "240": "4H", "15M": "15M", "30M": "30M", "1H": "1H", "4H": "4H", "1h": "1H", "4h": "4H"}.get(tf_raw, f"{tf_raw}m")
        lines.append(f"{emoji} {dir_e} <b>{sym}</b>  {tf_disp}  Entry: {entry:.2f}  {tp_lbl}")

    now = datetime.now(timezone.utc).strftime("%d %b %Y")
    body = "\n".join(lines)

    msg = (
        f"📊 <b>STOCKS SESSION REPORT — {now}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{body}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Signals: <b>{total}</b>  ✅ Win: <b>{len(wins)}</b>  ❌ Loss: <b>{len(losses)}</b>\n"
        f"Win Rate: <b>{wr:.0f}%</b>"
    )
    return await _send(msg)


def _intel_dir_line(emoji: str, name: str, sig: dict) -> str:
    """One asset line for the intelligence alert: direction + confidence."""
    d = sig.get("direction", "NEUTRAL")
    c = sig.get("confidence", 0.0) or 0.0
    if d == "LONG":
        tag = "🟢 LONG"
    elif d == "SHORT":
        tag = "🔴 SHORT"
    else:
        tag = "⚪ NEUTRAL"
    conf = f" ({c*100:.0f}%)" if c > 0 else ""
    return f"{emoji} <b>{name}</b>: {tag}{conf}"


async def send_market_intelligence(
    reasons: list[str],
    velocity: dict,
    event: dict,
    gold: dict,
    spy: dict,
    qqq: dict,
) -> bool:
    """
    Market-movement intelligence alert. Fires on a state change when the market
    enters an elevated-activity regime: rising news velocity, an imminent
    high-impact event, an ML direction flip on rising flow, or fast sentiment
    acceleration (regime shift). `reasons` is the list of trigger lines that
    explain WHY this fired.
    """
    if not reasons:
        return False

    now      = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")
    vlabel   = velocity.get("label", "NORMAL")
    vdir     = velocity.get("direction", "")
    consist  = velocity.get("consistency", 0.0) or 0.0

    # Headline severity: imminent event = highest, then HIGH VELOCITY
    if event.get("detected") and event.get("urgency", 0.0) >= 0.85:
        header = "🚨 <b>MARKET INTELLIGENCE — EVENT INCOMING</b>"
    elif vlabel == "HIGH VELOCITY":
        header = "⚡ <b>MARKET INTELLIGENCE — HIGH MOMENTUM</b>"
    else:
        header = "📡 <b>MARKET INTELLIGENCE</b>"

    reason_block = "\n".join(f"• {r}" for r in reasons)
    flow = f"{vlabel}" + (f" · {vdir}" if vdir else "") + f" · alignment {consist*100:.0f}%"

    msg = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{reason_block}\n\n"
        f"📊 News flow: <b>{flow}</b>\n\n"
        f"{_intel_dir_line('🥇', 'XAUUSD', gold)}\n"
        f"{_intel_dir_line('📈', 'SPY', spy)}\n"
        f"{_intel_dir_line('📈', 'QQQ', qqq)}\n"
        f"\n⏰ {now}"
    )
    return await _send(msg)


_REGIME_MAP = {
    "TRENDING_BEAR": "📉 Trending Bear",
    "TRENDING_BULL": "📈 Trending Bull",
    "RANGING":       "↔️ Ranging",
    "VOLATILE":      "⚡ Volatile",
    "NORMAL":        "〰️ Normal",
    "UNKNOWN":       "❓ Unknown",
}


def _bias_line(label_emoji: str, name: str, signal: dict) -> str:
    """One asset line: '🥇 XAUUSD Bias: 🟢 LONG (68%)  ·  📈 Trending Bull'."""
    direction  = signal.get("direction", "NEUTRAL")
    confidence = signal.get("confidence", 0.0)
    regime     = signal.get("regime", "UNKNOWN")
    if direction == "LONG":
        dir_str = f"🟢 LONG ({confidence*100:.0f}%)"
    elif direction == "SHORT":
        dir_str = f"🔴 SHORT ({confidence*100:.0f}%)"
    else:
        dir_str = "⚪ NEUTRAL"
    regime_str = _REGIME_MAP.get(regime, regime)
    return f"{label_emoji} <b>{name} Bias:</b> {dir_str}  ·  {regime_str}"


async def send_market_pulse(gold: dict, spy: dict, qqq: dict, macro: dict) -> bool:
    """
    Periodic market-direction summary across XAUUSD/SPY/QQQ.
    Sent on a schedule (London open / NY open / NY close), regardless of flips.
    """
    now        = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")
    macro_bias = macro.get("bias", 0.0)
    macro_lbl  = macro.get("label", "NEUTRAL")

    msg = (
        f"📡 <b>MARKET PULSE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Macro:  <b>{macro_lbl}</b> ({macro_bias:+.2f})\n\n"
        f"{_bias_line('🥇', 'XAUUSD', gold)}\n"
        f"{_bias_line('📊', 'SPY', spy)}\n"
        f"{_bias_line('📊', 'QQQ', qqq)}\n"
        f"\n⏰ {now}"
    )
    return await _send(msg)


async def send_critical_alert(title: str, detail: str, action: str = "") -> bool:
    """
    Send a critical system alert to the personal chat only.
    Used for: Railway down, hours warning, GitHub token expired, webhook silence.
    Never used for normal signals or health noise.
    """
    if not TOKEN or not PERSONAL_CHAT_ID:
        print(f"[critical] {title} — {detail}")
        return False
    now = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")
    msg = (
        f"🚨 <b>SYSTEM ALERT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>{title}</b>\n"
        f"{detail}\n"
    )
    if action:
        msg += f"\n🔧 <i>{action}</i>\n"
    msg += f"\n⏰ {now}"
    import asyncio as _asyncio
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id":    PERSONAL_CHAT_ID,
                    "text":       msg,
                    "parse_mode": "HTML",
                })
                resp.raise_for_status()
                return True
        except Exception as e:
            if attempt < 2:
                wait = 1 if attempt == 0 else 3
                print(f"[critical] Personal alert failed (attempt {attempt+1}/3): {e} — retrying in {wait}s")
                await _asyncio.sleep(wait)
            else:
                print(f"[critical] Personal alert failed after 3 attempts: {e}")
    return False
