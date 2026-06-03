import os
import httpx
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

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
    ml_score   = signal.get("ml_score", 0.5)
    news_score = signal.get("news_score", 0.0)
    combined   = signal.get("combined_score", 0.0)
    reasoning  = signal.get("reasoning", "")
    wins       = signal.get("total_wins", 0)
    losses     = signal.get("total_losses", 0)
    win_rate   = signal.get("win_rate", 0.0)
    top_feat   = signal.get("top_feature", "—")
    velocity   = signal.get("news_velocity", "NORMAL")
    v_mult     = signal.get("velocity_mult", 1.0)
    event      = signal.get("high_impact_event", "")
    symbol     = signal.get("symbol", "XAUUSD").split(":")[-1]
    pool       = signal.get("pool", "XAUUSD")

    dir_emoji  = "🟢" if direction == "LONG" else "🔴"
    conf_emoji = "🔥" if confidence >= 0.75 else "✅" if confidence >= 0.60 else "⚠️"
    news_label = "📰 Bullish" if news_score > 0.2 else "📰 Bearish" if news_score < -0.2 else "📰 Neutral"
    now        = signal.get("timestamp", datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y"))
    pool_label = "" if pool == "XAUUSD" else f"  |  Pool: {pool.replace('STOCKS_', '')}"

    msg = (
        f"{dir_emoji} <b>{direction}</b> {conf_emoji}  Confidence: <b>{confidence*100:.0f}%</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 ML Score: {ml_score*100:.0f}%  |  Combined: {combined:+.3f}\n"
        f"{news_label} ({news_score:+.3f})  |  📡 {velocity} ×{v_mult:.1f}\n"
        f"🏆 Top Feature: <b>{top_feat}</b>\n\n"
        f"📈 Wins: {wins}  Losses: {losses}  Win Rate: {win_rate*100:.1f}%\n"
    )

    if event:
        msg += f"⚡ <b>BREAKING:</b> {event}\n"

    if reasoning:
        msg += f"\n💬 <i>{reasoning}</i>\n"

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
