import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

DIRECTION_EMOJI = {"LONG": "🟢", "SHORT": "🔴", "NEUTRAL": "⚪"}
CONF_EMOJI = lambda c: "🔥" if c >= 0.75 else "✅" if c >= 0.60 else "⚠️"


def _sentiment_bar(score: float) -> str:
    """Visual bar: -1..+1 → 10-char bar."""
    filled = round((score + 1) / 2 * 10)
    return "█" * filled + "░" * (10 - filled)


async def send_signal(signal: dict) -> bool:
    """Send a trading signal message to the Telegram channel."""
    if not TOKEN or not CHAT_ID:
        print("[telegram] TOKEN or CHAT_ID not set — skipping.")
        return False

    direction  = signal.get("direction", "NEUTRAL")
    confidence = signal.get("confidence", 0.0)
    ml_score   = signal.get("ml_score", 0.5)
    news_score = signal.get("news_score", 0.0)
    combined   = signal.get("combined_score", 0.5)
    reasoning  = signal.get("reasoning", "")
    wins       = signal.get("total_wins", 0)
    losses     = signal.get("total_losses", 0)
    win_rate   = signal.get("win_rate", 0.0)
    weights    = signal.get("weights", [1.0] * 8)
    top_feat   = signal.get("top_feature", "—")
    velocity   = signal.get("news_velocity", "NORMAL")
    v_mult     = signal.get("velocity_mult", 1.0)
    event      = signal.get("high_impact_event", "")

    dir_emoji  = DIRECTION_EMOJI.get(direction, "⚪")
    conf_emoji = CONF_EMOJI(confidence)

    weight_line = "  ".join(
        f"W{i+1}:{w:.2f}" for i, w in enumerate(weights)
    )

    news_bar  = _sentiment_bar(news_score)
    news_label = "📰 Bullish for XAU" if news_score > 0.2 else "📰 Bearish for XAU" if news_score < -0.2 else "📰 Neutral"

    msg = (
        f"*🤖 MIGO SNIPER PRO — ML + ADAPTIVE*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{dir_emoji} *{direction}* {conf_emoji}  Confidence: *{confidence*100:.0f}%*\n\n"
        f"📊 *Scores*\n"
        f"  ML Bull/Bear : {ml_score*100:.0f}%\n"
        f"  News Sentiment: `{news_bar}` {news_score:+.3f}\n"
        f"  {news_label}\n"
        f"  Combined Score: *{combined:+.3f}*\n\n"
        f"🧠 *Adaptive Weights*\n"
        f"  {weight_line}\n"
        f"  Top Feature: *{top_feat}*\n\n"
        f"📈 *Session Stats*\n"
        f"  Wins: {wins}  Losses: {losses}  Win Rate: {win_rate*100:.1f}%\n\n"
    )

    velocity_emoji = "🚨" if velocity == "HIGH VELOCITY" else "📈" if velocity == "ELEVATED" else "📊"
    msg += f"{velocity_emoji} *News Velocity:* {velocity} ×{v_mult:.1f}\n"
    if event:
        msg += f"⚡ *BREAKING EVENT:* {event}\n"
    msg += "\n"

    if reasoning:
        msg += f"💬 _{reasoning}_\n\n"

    msg += f"⏰ XAU/USD · 5m · {signal.get('timestamp', '')}"

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "chat_id": CHAT_ID,
                "text": msg,
                "parse_mode": "Markdown",
            })
            resp.raise_for_status()
            return True
    except Exception as e:
        print(f"[telegram] Send failed: {e}")
        return False


async def send_text(text: str) -> None:
    """Send a plain text message."""
    if not TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(url, json={"chat_id": CHAT_ID, "text": text})
        except Exception:
            pass
