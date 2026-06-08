import os
import html
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
    htf_bias  = s.get("htf_bias")  # dict from htf_bias store, or None

    dir_emoji    = "🟢" if direction == "LONG" else "🔴"
    symbol_clean = html.escape(symbol.split(":")[-1])
    is_gold      = symbol_clean in ("XAUUSD", "GOLD", "GC")
    asset_emoji  = "🥇" if is_gold else "📊"
    now          = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")

    htf_context  = s.get("htf_context", "")
    contra_bias  = s.get("contra_bias")

    if htf_bias and isinstance(htf_bias, dict) and htf_bias.get("timeframe") and htf_bias.get("expires_at"):
        from htf_bias import bias_remaining_label, tf_label
        htf_tf      = tf_label(htf_bias["timeframe"])
        remaining   = bias_remaining_label(htf_bias)
        confirmation = f"✅ HTF Bias: {htf_tf} {direction}  (⏳ {remaining})\n"
    elif contra_bias and isinstance(contra_bias, dict) and contra_bias.get("timeframe"):
        from htf_bias import tf_label
        contra_dir = "SHORT" if direction == "LONG" else "LONG"
        htf_tf     = tf_label(contra_bias["timeframe"])
        confirmation = f"⚠️ Counter-trend: {htf_tf} is {contra_dir}  — scalp / pullback entry\n"
    else:
        confirmation = "📈 Scalp — no HTF bias active\n"

    msg = (
        f"{dir_emoji} <b>{direction} SIGNAL</b> — {asset_emoji} {symbol_clean}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{confirmation}"
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
    now_fmt    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Session label
    session_map = {
        "OVERLAP":        "London/NY Overlap",
        "LONDON":         "London",
        "NEW_YORK":       "New York",
        "NY_LATE":        "New York Late",
        "ASIAN":          "Asian",
        "NYSE_OPEN":      "NYSE Open",
        "NYSE_AFTERNOON": "NYSE Afternoon",
        "PRE_MARKET":     "Pre-Market",
    }
    sess_label = session_map.get(session, session)

    msg = (
        f"{dir_emoji} <b>{direction}  {symbol}  Direction Expected</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Confidence: <b>{confidence*100:.0f}%</b>  |  Strength: {conf_emoji} {strength}\n"
        f"Session: {sess_label}\n"
    )

    if event:
        msg += f"⚡ <b>{event}</b>\n"

    msg += f"\n⏰ {now_fmt}"
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
        "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_4H",
        "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_4H",
        "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H",
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
        tf_disp = {"60": "1H", "240": "4H", "1H": "1H", "4H": "4H", "1h": "1H", "4h": "4H"}.get(tf_raw, f"{tf_raw}m")
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


async def send_market_intelligence(signal: dict, ml_direction: str) -> bool:
    """
    Send market intelligence alert when ML direction changes.
    Fires regardless of confidence — purely on direction flip.
    """
    confidence = signal.get("confidence", 0.0)
    regime     = signal.get("regime", "UNKNOWN")
    session    = signal.get("session", "")
    event      = signal.get("high_impact_event", "")
    symbol     = signal.get("symbol", "XAUUSD").split(":")[-1]
    now        = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")

    dir_emoji  = "🟢" if ml_direction == "LONG" else "🔴"

    regime_map = {
        "TRENDING_BEAR": "📉 Trending Bear",
        "TRENDING_BULL": "📈 Trending Bull",
        "RANGING":       "↔️ Ranging",
        "VOLATILE":      "⚡ Volatile",
        "NORMAL":        "〰️ Normal",
        "UNKNOWN":       "❓ Unknown",
    }
    regime_label = regime_map.get(regime, regime)

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

    conf_str = f"{confidence*100:.0f}%" if confidence > 0 else "—"

    msg = (
        f"{dir_emoji} <b>DIRECTION — {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Direction:  <b>{ml_direction}</b>\n"
        f"Confidence: <b>{conf_str}</b>\n\n"
        f"📊 Regime:  {regime_label}\n"
        f"⏱ Session: {sess_label}\n"
    )
    if event:
        msg += f"⚡ Event:   <b>{event}</b>\n"
    msg += f"\n⏰ {now}"
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
