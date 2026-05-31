"""
APScheduler: runs the news → sentiment → signal pipeline every N minutes.
"""
import asyncio
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

_scheduler: AsyncIOScheduler | None = None
_latest_news_agg: float = 0.0   # shared state between scheduler and signal endpoint


def get_latest_news_sentiment() -> float:
    return _latest_news_agg


async def _news_signal_cycle() -> None:
    global _latest_news_agg
    print("[scheduler] Starting news + signal cycle…")

    try:
        from news_fetcher import run_news_cycle
        from db import insert_news
        from signal_engine import generate_signal
        from telegram_bot import send_signal, send_text

        scored_items, agg = run_news_cycle()

        if scored_items:
            insert_news(scored_items)
            _latest_news_agg = agg

        signal = generate_signal(news_agg=_latest_news_agg)
        print(f"[scheduler] Signal: {signal['direction']} conf={signal['confidence']:.2f}")

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
    interval = int(os.environ.get("SIGNAL_INTERVAL_MINUTES", "15"))
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
