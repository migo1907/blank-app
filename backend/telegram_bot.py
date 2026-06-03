import os
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

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
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
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
        print(f"[telegram] Send failed: {e}")
        return False


async def send_entry_signal(s: dict) -> bool:
    """Send a clean entry signal message — fires instantly when trade opens."""
    direction = s.get("direction", "LONG")
    tf        = s.get("timeframe", "5m")
    trigger   = s.get("trigger", "RSI")
    symbol    = s.get("symbol", "XAUUSD")
    entry     = s.get("entry_price", 0.0)
    tp1       = s.get("tp1", 0.0)
    tp2       = s.get("tp2", 0.0)
    tp3       = s.get("tp3", 0.0)
    sl        = s.get("sl", 0.0)
    ml_score  = s.get("ml_score", 0.5)
    tier      = s.get("tier", "MED")
    news      = s.get("news_score", 0.0)
    velocity  = s.get("velocity", "NORMAL")
    event     = s.get("event", "")

    dir_emoji    = "🟢" if direction == "LONG" else "🔴"
    symbol_clean = symbol.split(":")[-1]
    is_gold      = symbol_clean in ("XAUUSD", "GOLD", "GC")
    asset_emoji  = "🥇" if is_gold else "📊"
    now          = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")

    msg = (
        f"{dir_emoji} <b>{direction} SIGNAL</b> — {asset_emoji} {symbol_clean}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Timeframe: {tf}\n"
        f"Strength:  {tier}\n\n"
        f"📍 Entry:  {entry:.2f}\n"
        f"🎯 TP1:    {tp1:.2f}\n"
        f"🎯 TP2:    {tp2:.2f}\n"
        f"🚀 TP3:    {tp3:.2f}\n"
        f"🛑 SL:     {sl:.2f}\n\n"
        f"⏰ {now}"
    )
    return await _send(msg)


async def send_signal(signal: dict) -> bool:
    """Send a scheduler-generated signal (15-min cycle)."""
    direction  = signal.get("direction", "NEUTRAL")
    confidence = signal.get("confidence", 0.0)
    event      = signal.get("high_impact_event", "")
    session    = signal.get("session", "")
    symbol     = signal.get("symbol", "XAUUSD").split(":")[-1]
    pool       = signal.get("pool", "XAUUSD")
    top_feat   = signal.get("top_feature", "—")
    now        = signal.get("timestamp", datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y"))

    dir_emoji  = "🟢" if direction == "LONG" else "🔴"
    conf_emoji = "🔥" if confidence >= 0.75 else "✅" if confidence >= 0.60 else "⚠️"
    strength   = "HIGH 🔥" if confidence >= 0.75 else "MED ✅" if confidence >= 0.60 else "LOW ⚠️"
    pool_label = "" if pool == "XAUUSD" else f"  |  {pool.replace('STOCKS_', '')}"

    # Session label
    session_map = {
        "OVERLAP":   "London/NY Overlap",
        "LONDON":    "London",
        "NEW_YORK":  "New York",
        "ASIAN":     "Asian",
    }
    sess_label = session_map.get(session, session)

    msg = (
        f"{dir_emoji} <b>{direction} direction expected</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Confidence: <b>{confidence*100:.0f}%</b>  |  Strength: {conf_emoji} {strength}\n"
        f"Session: {sess_label}\n"
    )

    if event:
        msg += f"⚡ <b>{event}</b>\n"

    msg += f"\n⏰ {now}  |  {symbol}{pool_label}"
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
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
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
        print(f"[critical] Personal alert failed: {e}")
        return False
