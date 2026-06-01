"""
APScheduler: runs the news → velocity → sentiment → signal pipeline every N minutes.
"""
import asyncio
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

_scheduler:          AsyncIOScheduler | None = None
_latest_news_agg:    float = 0.0
_latest_velocity:    dict  = {"multiplier": 1.0, "label": "NORMAL"}
_latest_event:       dict  = {"detected": False, "event_type": "", "urgency": 0.0}
_fj_seen_headlines:  set   = set()   # dedup FinancialJuice breaking news across cycles


def get_latest_news_sentiment() -> float:
    return _latest_news_agg

def get_latest_velocity() -> dict:
    return _latest_velocity

def get_latest_event() -> dict:
    return _latest_event


async def _news_signal_cycle() -> None:
    global _latest_news_agg, _latest_velocity, _latest_event, _fj_seen_headlines
    print("[scheduler] Starting news + velocity + signal cycle…")

    try:
        from news_fetcher import run_news_cycle
        from db import insert_news
        from signal_engine import generate_signal
        from telegram_bot import send_signal, send_text, send_breaking_news

        # Pass previous aggregation so velocity can measure acceleration
        scored_items, agg, velocity, event, fj_breaking = run_news_cycle(previous_agg=_latest_news_agg)

        if scored_items:
            insert_news(scored_items)
            _latest_news_agg = agg
            _latest_velocity = velocity
            _latest_event    = event

        # ── FinancialJuice red breaking news → instant Telegram alert ──────────
        if fj_breaking:
            _fj_seen_headlines = await send_breaking_news(fj_breaking, _fj_seen_headlines)

        # ── High-impact event alert (NFP, FOMC, war etc.) ──────────────────────
        if event.get("detected") and event.get("urgency", 0) >= 0.9:
            print(f"[scheduler] ⚡ HIGH-IMPACT EVENT: {event['event_type']}")
            await send_text(
                f"⚡ <b>HIGH IMPACT EVENT: {event['event_type']}</b>\n"
                f"Headlines: {', '.join(event.get('headlines', []))[:200]}\n"
                f"News sentiment: {agg:+.3f} | Velocity: {velocity['label']} ×{velocity['multiplier']}"
            )

        signal = generate_signal(
            news_agg=_latest_news_agg,
            news_velocity=_latest_velocity,
            high_impact_event=_latest_event,
        )
        print(
            f"[scheduler] Signal: {signal['direction']} "
            f"conf={signal['confidence']:.2f} "
            f"velocity={signal['news_velocity']} ×{signal['velocity_mult']}"
        )

        if signal["direction"] != "NEUTRAL":
            sent = await send_signal(signal)
            if not sent:
                print("[scheduler] Telegram send failed (check TOKEN/CHAT_ID).")
        else:
            print("[scheduler] Signal is NEUTRAL — not sending to Telegram.")

    except Exception as e:
        print(f"[scheduler] Cycle error: {e}")
        try:
            from telegram_bot import send_text
            await send_text(f"⚠️ Migo Sniper backend error: {e}")
        except Exception:
            pass


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    interval   = int(os.environ.get("SIGNAL_INTERVAL_MINUTES", "15"))
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _news_signal_cycle,
        trigger="interval",
        minutes=interval,
        id="news_signal_cycle",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"[scheduler] Started — running every {interval} minutes.")
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[scheduler] Stopped.")
