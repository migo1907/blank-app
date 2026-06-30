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
# Swing brief target — defaults to the main signals channel until a dedicated
# swing channel is created, then just set SWING_CHAT_ID in Railway (no code change).
SWING_CHAT_ID   = os.environ.get("SWING_CHAT_ID", "") or CHAT_ID

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
    q_score    = s.get("quality_score")
    q_reason   = s.get("quality_reason", "")
    ci         = s.get("ml_interval")
    certainty  = s.get("ml_certainty", "")
    cert_emoji = {"HIGH": "🎯", "MODERATE": "〰️", "LOW": "❓"}.get(certainty, "")
    ci_str     = f" [{ci[0]*100:.0f}–{ci[1]*100:.0f}%] {cert_emoji}" if ci else ""
    if q_reason in ("no_features_cached", "cold_start_bypass") or q_score is None:
        quality_line = "🧠 ML Quality: — (model warming up)\n"
    elif q_score >= 0.55:
        quality_line = f"🧠 ML Quality: 🔥 STRONG ({q_score*100:.0f}%{ci_str})\n"
    elif q_score >= 0.40:
        quality_line = f"🧠 ML Quality: ✅ FAIR ({q_score*100:.0f}%{ci_str})\n"
    else:
        quality_line = f"🧠 ML Quality: ⚠️ WEAK ({q_score*100:.0f}%{ci_str}) — similar setups mostly stopped out\n"

    # Entry2: pullback add-on level gated on ML Quality (not tier/strength).
    # STRONG (≥0.55) or FAIR (≥0.40) → show Entry2. WEAK → skip.
    # Multiplier is regime-aware: trending=0.3, volatile=0.4, ranging=0.5.
    # Valid until TP1 — same SL covers both entries. Display-only, no trade impact.
    entry2_line = ""
    if q_score is not None and q_score >= 0.40 and entry and sl and tp1:
        atr = abs(entry - sl)
        regime = s.get("regime", "RANGING").upper()
        if "TREND" in regime:
            e2_mult = 0.3
        elif "VOLAT" in regime:
            e2_mult = 0.4
        else:
            e2_mult = 0.5  # RANGING — deeper pullback expected
        if atr > 0:
            e2 = entry - e2_mult * atr if direction == "LONG" else entry + e2_mult * atr
            entry2_line = f"📍 Entry2: {e2:.2f}  <i>(pullback · valid until TP1)</i>\n"

    msg = (
        f"{dir_emoji} <b>{direction} SIGNAL{htf_badge}</b> — {asset_emoji} {symbol_clean}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Timeframe: {tf_display}\n"
        f"Strength:  {strength_str}\n"
        f"{quality_line}\n"
        f"📍 Entry:  {entry:.2f}\n"
        f"{entry2_line}"
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
    decimals   = 2
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

    # Live price from TradingView scanner — offloaded to a thread so the blocking
    # httpx call (up to 8s) never stalls the event loop / concurrent webhooks.
    try:
        import asyncio as _asyncio
        from daily_analysis import _fetch_live_price_tv
        live_price = await _asyncio.to_thread(_fetch_live_price_tv, symbol, decimals)
        price_line = f"💰 Current Price: <b>${live_price:,.2f}</b>\n" if live_price else ""
    except Exception:
        price_line = ""

    # Conviction header — only for LONG/SHORT, scales with confidence
    if confidence >= 1.0:
        conviction_header = "‼️ <b>MAXIMUM CONVICTION SIGNAL</b>\n"
    elif confidence >= 0.75:
        conviction_header = "‼️ <b>HIGH CONVICTION SIGNAL</b>\n"
    else:
        conviction_header = ""

    msg = (
        f"{conviction_header}"
        f"{dir_emoji} <b>{direction} — {asset_emoji} {symbol}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{price_line}"
        f"Confidence: <b>{confidence*100:.0f}%</b>\n"
        f"Session: {sess_label}\n"
    )
    if event:
        msg += f"⚡ {html.escape(event)}\n"
    msg += f"\n⏰ {now}"
    return await _send(msg)


async def send_text(text: str) -> None:
    """Send a plain text message to the main channel."""
    await _send(text)


async def send_personal_text(text: str) -> bool:
    """Send a plain Markdown message to the personal chat (same as system alerts)."""
    return await _send_to(PERSONAL_CHAT_ID, text)


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
    lines = "\n".join(f"🔴 {html.escape(item['title'])}" for item in new_items[:5])

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

    from ml_model import is_win
    wins   = [t for t in trades_today if is_win(t)]
    losses = [t for t in trades_today if not is_win(t)]
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


def _intel_dir_line(emoji: str, name: str, sig: dict, news_label: str = "") -> str:
    """One asset line for the intelligence alert: direction + confidence."""
    d = sig.get("direction", "NEUTRAL")
    c = sig.get("confidence", 0.0) or 0.0
    lean_dir = sig.get("lean_direction", "") or ""
    lean_pct = sig.get("lean_pct")

    # Only show an actionable direction if confidence cleared the send threshold (≥0.50).
    # Below that — including the 0.30 thin-pool floor — it's NO SIGNAL.
    if d in ("LONG", "SHORT") and c >= 0.50:
        tag  = "🟢 LONG" if d == "LONG" else "🔴 SHORT"
        conf = f" · conf {c*100:.0f}%"
    else:
        # NO SIGNAL: surface the ML lean so the reader understands the backdrop
        tag = "⚪ NO SIGNAL"
        # Use direction+confidence as the lean when it exists but didn't clear threshold
        lean = lean_dir or (d if d not in ("NEUTRAL", "") else "")
        pct  = lean_pct if (lean_pct is not None and lean_pct >= 55) else (int(c * 100) if c >= 0.30 else None)
        if lean and pct:
            conf = f" · ML leans {lean} {pct}%"
            if news_label:
                conf += f" · news {news_label}"
        elif news_label:
            conf = f" · news {news_label}"
        else:
            conf = ""
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

    reason_block = "\n".join(f"• {html.escape(str(r))}" for r in reasons)
    flow = html.escape(f"{vlabel}" + (f" · {vdir}" if vdir else "") + f" · alignment {consist*100:.0f}%")

    msg = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{reason_block}\n\n"
        f"📊 News flow: <b>{flow}</b>\n\n"
        f"{_intel_dir_line('🥇', 'XAUUSD', gold, vdir)}\n"
        f"{_intel_dir_line('📈', 'SPY', spy, vdir)}\n"
        f"{_intel_dir_line('📈', 'QQQ', qqq, vdir)}\n"
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
        lean_dir = signal.get("lean_direction", "")
        lean_pct = signal.get("lean_pct")
        lean_str = f"  ({lean_dir} {lean_pct}%)" if lean_dir and lean_pct is not None and lean_pct >= 55 else ""
        dir_str = f"⚪ NEUTRAL{lean_str}"
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
        f"⚠️ <b>{html.escape(str(title))}</b>\n"
        f"{html.escape(str(detail))}\n"
    )
    if action:
        msg += f"\n🔧 <i>{html.escape(str(action))}</i>\n"
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


async def send_owner_message(body: str, action: str = "") -> bool:
    """
    Direct communication to the owner (Mohamed) on the personal chat — NOT a system
    alert. By agreement, a message that opens with "Mohamed —" is the system/Claude
    talking to you (usually because something needs a manual action: paste a Pine
    update, allow-list a host, run an endpoint), not an automated stat line.
    """
    if not TOKEN or not PERSONAL_CHAT_ID:
        print(f"[owner] Mohamed — {body}")
        return False
    now = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")
    msg = (
        f"💬 <b>Mohamed —</b> {html.escape(str(body))}\n"
    )
    if action:
        msg += f"\n👉 <b>Action:</b> {html.escape(str(action))}\n"
    msg += f"\n<i>(direct message — manual action may be needed, not a system alert)</i>"
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
                await _asyncio.sleep(1 if attempt == 0 else 3)
            else:
                print(f"[owner] Owner message failed after 3 attempts: {e}")
    return False


async def _send_to(chat_id: str, text: str) -> bool:
    """Generic send to an arbitrary chat id with retry (used by the swing brief)."""
    if not TOKEN or not chat_id:
        print("[telegram] TOKEN or target chat id not set — skipping.")
        return False
    import asyncio as _asyncio
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id":    chat_id,
                    "text":       text,
                    "parse_mode": "HTML",
                })
                resp.raise_for_status()
                return True
        except Exception as e:
            if attempt < 2:
                await _asyncio.sleep(1 if attempt == 0 else 3)
            else:
                print(f"[telegram] swing send failed after 3 attempts: {e}")
    return False


async def send_swing_brief(screen: dict) -> bool:
    """
    Evening swing-trade brief — top candidates with fundamental + technical read
    and a synthesized 'why'. Sent to SWING_CHAT_ID (defaults to main channel).
    """
    cands = (screen or {}).get("candidates", [])
    if not cands:
        print("[swing] no candidates to send")
        return False

    from swing_narrative import synthesize, available as narrative_on

    now = datetime.now(timezone.utc).strftime("%d %b %Y")
    head = (
        f"📈 <b>SWING WATCH — Top {len(cands)} Setups</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Scanned {screen.get('scanned', 0)} S&amp;P 500 names · {now}</i>\n"
        f"{'🤖 AI thesis' if narrative_on() else '📊 Data thesis'}\n"
    )

    def _conviction(s: float) -> str:
        if s >= 0.50: return "STRONG"
        if s >= 0.35: return "GOOD"
        if s >= 0.15: return "MODERATE"
        return "WEAK"

    blocks = [head]
    for i, c in enumerate(cands, 1):
        tkr = html.escape(str(c.get("ticker", "?")))
        score = c.get("combined_score", 0.0)
        tech = c.get("technical", {})
        emoji = "🟢" if score >= 0.35 else "🟡" if score >= 0.15 else "⚪"
        thesis = html.escape(synthesize(c))
        line = (
            f"\n{emoji} <b>{i}. {tkr}</b>  conviction {score*100:.0f}% ({_conviction(score)})\n"
            f"<i>{tech.get('trend','—')} daily trend</i>\n"
            f"{thesis}\n"
        )
        # TradingAgents second-layer block (shown when debate has run)
        try:
            from trading_agents_layer import format_agent_block
            agent_block = format_agent_block(c)
            if agent_block:
                line += agent_block
        except Exception:
            pass
        entry, stop = tech.get("entry"), tech.get("stop")
        t1, t2 = tech.get("t1"), tech.get("t2")
        if entry is not None and stop is not None and t1 is not None and t2 is not None:
            line += f"\n📍 Entry ~{entry:.2f}  🛑 Stop {stop:.2f}  🎯 T1 {t1:.2f}  🎯 T2 {t2:.2f}\n"
        blocks.append(line)

    blocks.append(
        "\n━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Swing horizon 3–15 days · not the intraday channel · "
        "size and confirm at your own entry.</i>"
    )
    return await _send_to(SWING_CHAT_ID, "".join(blocks))
