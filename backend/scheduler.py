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
_fj_seen_headlines:  set   = set()   # dedup breaking news across cycles (persisted to GitHub)

_SEEN_HEADLINES_PATH = "data/seen_headlines.json"
_SEEN_HEADLINES_MAX  = 500          # cap size to avoid growing forever


def get_latest_news_sentiment() -> float:
    return _latest_news_agg

def get_latest_velocity() -> dict:
    return _latest_velocity

def get_latest_event() -> dict:
    return _latest_event


def _load_seen_headlines() -> set:
    """Load previously seen headlines from GitHub data branch (survives restarts)."""
    global _fj_seen_headlines
    try:
        from db import _get_file
        data, _ = _get_file(_SEEN_HEADLINES_PATH)
        if isinstance(data, list):
            _fj_seen_headlines = set(data)
            print(f"[scheduler] Loaded {len(_fj_seen_headlines)} seen headlines from GitHub.")
    except Exception as e:
        print(f"[scheduler] Could not load seen headlines (first run?): {e}")
        _fj_seen_headlines = set()


def _save_seen_headlines() -> None:
    """Persist seen headlines to GitHub data branch."""
    try:
        from db import _get_file, _put_file
        headlines_list = list(_fj_seen_headlines)[-_SEEN_HEADLINES_MAX:]
        _, sha = _get_file(_SEEN_HEADLINES_PATH)
        _put_file(_SEEN_HEADLINES_PATH, headlines_list, sha, "chore: update seen headlines")
    except Exception as e:
        print(f"[scheduler] Could not save seen headlines: {e}")


async def _breaking_news_cycle() -> None:
    """Runs every 2 minutes — fetches breaking news and fires Telegram instantly."""
    global _fj_seen_headlines
    try:
        from news_fetcher import fetch_breaking_news
        from telegram_bot import send_breaking_news
        items = fetch_breaking_news()
        if items:
            updated = await send_breaking_news(items, _fj_seen_headlines)
            if updated != _fj_seen_headlines:
                _fj_seen_headlines = updated
                asyncio.create_task(asyncio.to_thread(_save_seen_headlines))
    except Exception as e:
        print(f"[scheduler] Breaking news cycle error: {e}")


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

        # ── Write health status to GitHub data branch every cycle ─────────────
        asyncio.create_task(_write_health_status(signal, agg, velocity, len(fj_breaking)))

    except Exception as e:
        print(f"[scheduler] Cycle error: {e}")
        try:
            from telegram_bot import send_text
            await send_text(f"⚠️ Migo Sniper backend error: {e}")
        except Exception:
            pass


async def _write_health_status(signal: dict, news_agg: float, velocity: dict, breaking_count: int) -> None:
    """Write backend health snapshot to GitHub data branch every 15-min cycle."""
    try:
        from db import _get_file, _put_file
        from datetime import datetime, timezone
        from ml_model import get_model
        from ml_ensemble import get_rf
        from db import recent_outcomes
        model  = get_model()
        rf     = get_rf()
        trades = recent_outcomes(limit=500)
        status = {
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "signal":         signal["direction"],
            "confidence":     round(signal["confidence"], 4),
            "news_score":     round(news_agg, 4),
            "velocity":       velocity.get("label", "NORMAL"),
            "breaking_count": breaking_count,
            "trades_total":   len(trades),
            "rf_trained":     rf.is_trained,
            "win_rate":       round(model.win_rate * 100, 1),
            "knn_bearish_pct": round(signal.get("ml_score", 0) * 100, 1),
            "scheduler":      "running",
        }
        _, sha = _get_file("data/health.json")
        _put_file("data/health.json", status, sha, "chore: update health status")
        print(f"[scheduler] Health status written to GitHub.")
    except Exception as e:
        print(f"[scheduler] Health write failed: {e}")


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _load_seen_headlines()
    interval   = int(os.environ.get("SIGNAL_INTERVAL_MINUTES", "15"))
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _news_signal_cycle,
        trigger="interval",
        minutes=interval,
        id="news_signal_cycle",
        replace_existing=True,
    )
    _scheduler.add_job(
        _breaking_news_cycle,
        trigger="interval",
        minutes=2,
        id="breaking_news_cycle",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"[scheduler] Started — signal every {interval} min, breaking news every 2 min.")
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[scheduler] Stopped.")
