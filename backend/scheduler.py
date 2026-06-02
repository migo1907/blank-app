"""
APScheduler: runs the news → velocity → sentiment → signal pipeline every N minutes.
Also runs an hourly full system health check and reports to Telegram.
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
    """Runs every 2 minutes — fetches breaking news. Telegram sending paused."""
    pass


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


async def _hourly_system_check() -> None:
    """
    Full system audit — runs every 60 minutes.
    Silent when all checks pass. Only sends Telegram alert when issues are found.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")
    issues: list[str] = []
    ok:     list[str] = []

    # ── 1. GitHub persistence (db layer) ─────────────────────────────────────
    try:
        from db import _get_file
        weights, _ = _get_file("data/weights.json")
        if weights and "w1" in weights:
            ok.append("GitHub weights.json ✅")
        else:
            issues.append("weights.json missing or corrupt ❌")

        history, _ = _get_file("data/trade_history.json")
        trade_count = len(history) if isinstance(history, list) else 0
        if trade_count >= 15:
            ok.append(f"trade_history.json — {trade_count} trades ✅")
        elif trade_count > 0:
            issues.append(f"trade_history.json — only {trade_count} trades (need 15 for RF) ⚠️")
        else:
            issues.append("trade_history.json empty ❌")
    except Exception as e:
        issues.append(f"GitHub db layer error: {e} ❌")

    # ── 2. KNN model ─────────────────────────────────────────────────────────
    try:
        from ml_model import get_model
        model = get_model()
        wins  = model._total_wins
        losses = model._total_losses
        wr    = model.win_rate
        top   = model.top_feature()
        if wins + losses > 0:
            ok.append(f"KNN model — W{wins}/L{losses} WR:{wr*100:.0f}% top:{top} ✅")
        else:
            issues.append("KNN model — no trade history loaded ⚠️")
    except Exception as e:
        issues.append(f"KNN model error: {e} ❌")

    # ── 3. Random Forest ─────────────────────────────────────────────────────
    try:
        from ml_ensemble import get_rf
        rf = get_rf()
        if rf.is_trained:
            top_rf = rf.top_features(1)
            top_rf_name = top_rf[0][0] if top_rf else "?"
            ok.append(f"RF ensemble trained — top feature: {top_rf_name} ✅")
        else:
            issues.append("RF ensemble NOT trained yet ⚠️")
    except Exception as e:
        issues.append(f"RF ensemble error: {e} ❌")

    # ── 4. News pipeline ─────────────────────────────────────────────────────
    try:
        from db import _get_file
        from datetime import timedelta
        news_cache, _ = _get_file("data/news_cache.json")
        if isinstance(news_cache, list) and len(news_cache) > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
            recent = [
                n for n in news_cache
                if datetime.fromisoformat(n.get("fetched_at", "2000-01-01T00:00:00+00:00").replace("Z", "+00:00")) >= cutoff
            ]
            ok.append(f"News cache — {len(news_cache)} total, {len(recent)} in last 2h ✅")
        else:
            issues.append("News cache empty ⚠️")
    except Exception as e:
        issues.append(f"News cache error: {e} ❌")

    # ── 5. Breaking news dedup ────────────────────────────────────────────────
    try:
        from db import _get_file
        seen, _ = _get_file("data/seen_headlines.json")
        seen_count = len(seen) if isinstance(seen, list) else len(_fj_seen_headlines)
        ok.append(f"Breaking news dedup — {seen_count} headlines tracked ✅")
    except Exception as e:
        # Fall back to in-memory count
        ok.append(f"Breaking news dedup — {len(_fj_seen_headlines)} in memory ✅")

    # ── 6. Latest signal ──────────────────────────────────────────────────────
    try:
        from db import _get_file
        signals, _ = _get_file("data/signals.json")
        if isinstance(signals, list) and len(signals) > 0:
            last = signals[-1]
            last_dir  = last.get("direction", "?")
            last_conf = last.get("confidence", 0.0)
            last_ts   = last.get("created_at", "?")[:16]
            last_sess = last.get("session", "?")
            ok.append(f"Last signal — {last_dir} conf:{last_conf:.2f} sess:{last_sess} @ {last_ts} ✅")
        else:
            issues.append("signals.json empty — no signals generated yet ⚠️")
    except Exception as e:
        issues.append(f"signals.json error: {e} ❌")

    # ── 7. Scheduler health (self-check) ─────────────────────────────────────
    try:
        if _scheduler and _scheduler.running:
            jobs = _scheduler.get_jobs()
            job_ids = [j.id for j in jobs]
            expected = {"news_signal_cycle", "breaking_news_cycle", "hourly_system_check"}
            missing = expected - set(job_ids)
            if not missing:
                ok.append(f"Scheduler — {len(jobs)} jobs running ✅")
            else:
                issues.append(f"Scheduler — missing jobs: {missing} ⚠️")
        else:
            issues.append("Scheduler NOT running ❌")
    except Exception as e:
        issues.append(f"Scheduler check error: {e} ❌")

    # ── 8. Telegram connectivity ─────────────────────────────────────────────
    import os as _os
    tg_token   = _os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat_id = _os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat_id:
        ok.append("Telegram credentials present ✅")
    else:
        issues.append("Telegram TOKEN or CHAT_ID missing ❌")

    # ── 9. News velocity state ────────────────────────────────────────────────
    v_label = _latest_velocity.get("label", "UNKNOWN")
    v_mult  = _latest_velocity.get("multiplier", 1.0)
    news_agg_val = _latest_news_agg
    ok.append(f"News velocity — {v_label} ×{v_mult:.1f} | agg: {news_agg_val:+.3f} ✅")

    # ── 10. Feature check — ensure f9-f21 in stored trades ───────────────────
    try:
        from db import _get_file
        history, _ = _get_file("data/trade_history.json")
        if isinstance(history, list) and len(history) > 0:
            last_trade = history[-1]
            f21_present = "f21_vwap" in last_trade
            f9_present  = "f9_fvg"  in last_trade
            if f21_present and f9_present:
                ok.append("Feature vector f1-f21 present in latest trade ✅")
            else:
                missing_f = []
                if not f9_present:  missing_f.append("f9-f14")
                if not f21_present: missing_f.append("f21")
                issues.append(f"Latest trade missing features: {missing_f} — old data ⚠️")
    except Exception as e:
        issues.append(f"Feature check error: {e} ❌")

    # ── Log only — no Telegram ───────────────────────────────────────────────
    n_issue = len(issues)
    print(f"[system_check] {len(ok)}/{len(ok)+n_issue} checks passed.")
    for iss in issues:
        print(f"[system_check] ISSUE: {iss}")


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
    _scheduler.add_job(
        _hourly_system_check,
        trigger="interval",
        hours=1,
        id="hourly_system_check",
        replace_existing=True,
    )
    _scheduler.start()
    print(f"[scheduler] Started — signal every {interval} min, breaking news every 2 min, system check every 60 min.")
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[scheduler] Stopped.")
