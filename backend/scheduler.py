import asyncio
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

_scheduler:          AsyncIOScheduler | None = None
_latest_news_agg:    float = 0.0
_latest_velocity:    dict  = {"multiplier": 1.0, "label": "NORMAL"}
_latest_event:       dict  = {"detected": False, "event_type": "", "urgency": 0.0}
_fj_seen_headlines:  set   = set()
_last_sent_direction: str  = "NEUTRAL"
_last_sent_direction_spy: str = "NEUTRAL"

_SEEN_HEADLINES_PATH = "data/seen_headlines.json"
_SEEN_HEADLINES_MAX  = 500


def get_latest_news_sentiment() -> float:
    return _latest_news_agg

def get_latest_velocity() -> dict:
    return _latest_velocity

def get_latest_event() -> dict:
    return _latest_event


def _load_seen_headlines() -> set:
    global _fj_seen_headlines, _last_sent_direction, _last_sent_direction_spy
    try:
        from db import _get_file
        data, _ = _get_file(_SEEN_HEADLINES_PATH)
        if isinstance(data, list):
            _fj_seen_headlines = set(data)
            print(f"[scheduler] Loaded {len(_fj_seen_headlines)} seen headlines from GitHub.")
    except Exception as e:
        print(f"[scheduler] Could not load seen headlines (first run?): {e}")
        _fj_seen_headlines = set()

    try:
        from db import _get_file
        signals, _ = _get_file("data/signals.json")
        if isinstance(signals, list) and signals:
            for sig in reversed(signals):
                sym = sig.get("symbol", "XAUUSD")
                d   = sig.get("direction")
                if d not in ("NEUTRAL", None, ""):
                    if sym == "SPY" and _last_sent_direction_spy == "NEUTRAL":
                        _last_sent_direction_spy = d
                        print(f"[scheduler] SPY last sent direction restored: {d}")
                    elif sym != "SPY" and _last_sent_direction == "NEUTRAL":
                        _last_sent_direction = d
                        print(f"[scheduler] Last sent direction restored: {d}")
                if _last_sent_direction != "NEUTRAL" and _last_sent_direction_spy != "NEUTRAL":
                    break
    except Exception as e:
        print(f"[scheduler] Could not restore last sent direction: {e}")


def _save_seen_headlines() -> None:
    try:
        from db import _get_file, _put_file
        headlines_list = list(_fj_seen_headlines)[-_SEEN_HEADLINES_MAX:]
        _, sha = _get_file(_SEEN_HEADLINES_PATH)
        _put_file(_SEEN_HEADLINES_PATH, headlines_list, sha, "chore: update seen headlines")
    except Exception as e:
        print(f"[scheduler] Could not save seen headlines: {e}")


async def _breaking_news_cycle() -> None:
    global _fj_seen_headlines
    try:
        from news_fetcher import fetch_fj_breaking_direct, fetch_breaking_news
        from telegram_bot import send_text, send_critical_alert
        from datetime import datetime, timezone

        # ── 1. FJ breaking banner (flash/popup item) ──────────────────────────
        breaking, is_401 = await asyncio.to_thread(fetch_fj_breaking_direct)

        if is_401:
            await send_critical_alert(
                "FinancialJuice Session Expired",
                "Breaking news alerts have stopped — FJ cookie is no longer valid.",
                "Log in to financialjuice.com in your browser, then copy the new .ASPXAUTH cookie value to Railway → Variables → FJ_SESSION_COOKIE and redeploy.",
            )
            return

        alerts: list[str] = []
        if breaking:
            alerts.append(breaking)

        # ── 2. FJ red ticker items (high-impact keywords in RSS feed) ─────────
        ticker_items = await asyncio.to_thread(fetch_breaking_news)
        for item in ticker_items:
            headline = item.get("title", "").strip()
            if headline:
                alerts.append(headline)

        if not alerts:
            return

        # Breaking news Telegram alerts paused — set BREAKING_NEWS_TELEGRAM=true to re-enable
        telegram_enabled = os.environ.get("BREAKING_NEWS_TELEGRAM", "false").lower() == "true"

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        new_seen = set(_fj_seen_headlines)
        sent_any = False

        for headline in alerts:
            key = headline[:80]
            if key in new_seen:
                continue
            new_seen.add(key)
            sent_any = True
            if telegram_enabled:
                msg = (
                    f"\U0001f6a8 <b>BREAKING</b> — FinancialJuice\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"\U0001f534 {headline}\n\n"
                    f"⏰ {now}"
                )
                await send_text(msg)
                print(f"[breaking] Sent to Telegram: {headline[:80]}")
            else:
                print(f"[breaking] (Telegram paused) {headline[:80]}")

        if sent_any:
            _fj_seen_headlines = new_seen
            await asyncio.to_thread(_save_seen_headlines)

    except Exception as e:
        print(f"[breaking] cycle error: {e}")


async def _news_signal_cycle() -> None:
    global _latest_news_agg, _latest_velocity, _latest_event, _fj_seen_headlines, _last_sent_direction, _last_sent_direction_spy
    print("[scheduler] Starting news + velocity + signal cycle…")

    try:
        from news_fetcher import run_news_cycle
        from db import insert_news
        from signal_engine import generate_signal, get_latest_features
        from telegram_bot import send_signal, send_text, send_breaking_news

        prev_agg = _latest_news_agg
        try:
            scored_items, agg, velocity, event, fj_breaking = await asyncio.wait_for(
                asyncio.to_thread(run_news_cycle, prev_agg), timeout=90
            )
        except asyncio.TimeoutError:
            print("[scheduler] run_news_cycle timed out after 90s — using cached values.")
            scored_items, agg, velocity, event, fj_breaking = [], _latest_news_agg, _latest_velocity, _latest_event, []

        if scored_items:
            await asyncio.to_thread(insert_news, scored_items)
            _latest_news_agg = agg
            _latest_velocity = velocity
            _latest_event    = event

        signal = generate_signal(
            current_features=get_latest_features("XAUUSD"),
            news_agg=_latest_news_agg,
            news_velocity=_latest_velocity,
            high_impact_event=_latest_event,
        )
        print(
            f"[scheduler] Signal: {signal['direction']} "
            f"conf={signal['confidence']:.2f} "
            f"velocity={signal['news_velocity']} ×{signal['velocity_mult']}"
        )

        new_dir = signal["direction"]
        if new_dir != "NEUTRAL" and new_dir != _last_sent_direction:
            sent = await send_signal(signal)
            if sent:
                _last_sent_direction = new_dir
                print(f"[scheduler] Direction changed → {new_dir} — signal sent.")
            else:
                print("[scheduler] Telegram send failed (check TOKEN/CHAT_ID).")
        else:
            print("[scheduler] Signal is NEUTRAL — not sending to Telegram.")

        try:
            spy_signal = generate_signal(
                current_features=get_latest_features("STOCKS_INDEX_30M"),
                news_agg=_latest_news_agg,
                news_velocity=_latest_velocity,
                high_impact_event=_latest_event,
                symbol="SPY",
            )
            spy_dir = spy_signal["direction"]
            print(
                f"[scheduler] SPY Signal: {spy_dir} "
                f"conf={spy_signal['confidence']:.2f} "
                f"sess={spy_signal['session']}"
            )
            if spy_dir != "NEUTRAL" and spy_dir != _last_sent_direction_spy:
                sent_spy = await send_signal(spy_signal)
                if sent_spy:
                    _last_sent_direction_spy = spy_dir
                    print(f"[scheduler] SPY direction changed → {spy_dir} — signal sent.")
                else:
                    print("[scheduler] SPY Telegram send failed.")
            else:
                print(f"[scheduler] SPY signal is {spy_dir} — not sending.")
        except Exception as e:
            print(f"[scheduler] SPY signal error: {e}")

        asyncio.create_task(_write_health_status(signal, agg, velocity, len(fj_breaking)))

    except Exception as e:
        print(f"[scheduler] Cycle error: {e}")


async def _write_health_status(signal: dict, news_agg: float, velocity: dict, breaking_count: int) -> None:
    try:
        from db import _get_file, _put_file
        from datetime import datetime, timezone
        from ml_model import get_model
        from ml_ensemble import get_rf
        from db import recent_outcomes
        model  = get_model()
        rf     = get_rf()
        trades = await asyncio.to_thread(recent_outcomes, "XAUUSD", 500)
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
        _, sha = await asyncio.to_thread(_get_file, "data/health.json")
        await asyncio.to_thread(_put_file, "data/health.json", status, sha, "chore: update health status")
        print(f"[scheduler] Health status written to GitHub.")
    except Exception as e:
        print(f"[scheduler] Health write failed: {e}")


async def _hourly_system_check() -> None:
    from datetime import datetime, timezone
    from telegram_bot import send_critical_alert

    now = datetime.now(timezone.utc).strftime("%H:%M UTC — %d %b %Y")
    issues: list[str] = []
    ok:     list[str] = []
    critical_alerts: list[tuple[str, str, str]] = []

    try:
        from db import _get_file
        weights, _ = await asyncio.to_thread(_get_file, "data/weights.json")
        if weights and "w1" in weights:
            ok.append("GitHub weights.json ✅")
        else:
            issues.append("weights.json missing or corrupt ❌")
        history, _ = await asyncio.to_thread(_get_file, "data/trade_history.json")
        trade_count = len(history) if isinstance(history, list) else 0
        if trade_count >= 15:
            ok.append(f"trade_history.json — {trade_count} trades ✅")
        elif trade_count > 0:
            issues.append(f"trade_history.json — only {trade_count} trades (need 15 for RF) ⚠️")
        else:
            issues.append("trade_history.json empty ❌")
    except Exception as e:
        issues.append(f"GitHub db layer error: {e} ❌")

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

    try:
        from db import _get_file
        from datetime import timedelta
        news_cache, _ = await asyncio.to_thread(_get_file, "data/news_cache.json")
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

    try:
        from db import _get_file
        seen, _ = await asyncio.to_thread(_get_file, "data/seen_headlines.json")
        seen_count = len(seen) if isinstance(seen, list) else len(_fj_seen_headlines)
        ok.append(f"Breaking news dedup — {seen_count} headlines tracked ✅")
    except Exception as e:
        ok.append(f"Breaking news dedup — {len(_fj_seen_headlines)} in memory ✅")

    try:
        from db import _get_file
        signals, _ = await asyncio.to_thread(_get_file, "data/signals.json")
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

    try:
        if _scheduler and _scheduler.running:
            jobs = _scheduler.get_jobs()
            job_ids = [j.id for j in jobs]
            expected = {"news_signal_cycle", "breaking_news_cycle", "hourly_system_check", "daily_market_brief"}
            missing = expected - set(job_ids)
            if not missing:
                ok.append(f"Scheduler — {len(jobs)} jobs running ✅")
            else:
                issues.append(f"Scheduler — missing jobs: {missing} ⚠️")
        else:
            issues.append("Scheduler NOT running ❌")
    except Exception as e:
        issues.append(f"Scheduler check error: {e} ❌")

    import os as _os
    tg_token   = _os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat_id = _os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat_id:
        ok.append("Telegram credentials present ✅")
    else:
        issues.append("Telegram TOKEN or CHAT_ID missing ❌")

    try:
        import httpx as _httpx
        domain = _os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
        if domain:
            url = f"https://{domain}/health"
            async with _httpx.AsyncClient(timeout=8) as client:
                r = await client.get(url)
            if r.status_code == 200:
                ok.append(f"Railway keep-alive reachable — {url} ✅")
            else:
                issues.append(f"Railway /health returned {r.status_code} ⚠️")
        else:
            issues.append("RAILWAY_PUBLIC_DOMAIN not set — keep-alive disabled ⚠️")
    except Exception as e:
        issues.append(f"Railway keep-alive check failed: {e} ❌")

    v_label = _latest_velocity.get("label", "UNKNOWN")
    v_mult  = _latest_velocity.get("multiplier", 1.0)
    ok.append(f"News velocity — {v_label} ×{v_mult:.1f} | agg: {_latest_news_agg:+.3f} ✅")

    try:
        from db import _get_file
        history, _ = await asyncio.to_thread(_get_file, "data/trade_history.json")
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

    try:
        import httpx as _httpx
        railway_token = _os.environ.get("RAILWAY_API_TOKEN", "")
        if railway_token:
            query = "query { me { usage { currentPeriodUsage { usageMinutes } usageLimit { maxUsageMinutes } } } }"
            async with _httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    "https://backboard.railway.app/graphql/v2",
                    headers={"Authorization": f"Bearer {railway_token}", "Content-Type": "application/json"},
                    json={"query": query},
                )
            d = r.json()
            usage_data = ((d.get("data") or {}).get("me") or {}).get("usage") or {}
            used  = (usage_data.get("currentPeriodUsage") or {}).get("usageMinutes", 0)
            limit = (usage_data.get("usageLimit") or {}).get("maxUsageMinutes", 0)
            if limit and limit > 0:
                pct = used / limit * 100
                ok.append(f"Railway hours: {used}/{limit} min ({pct:.0f}%) ✅")
                if pct >= 95:
                    critical_alerts.append(("Railway Free Tier CRITICAL", f"Usage at {pct:.0f}% ({used}/{limit} min) — service will stop very soon.", "Upgrade Railway plan immediately or service stops."))
                elif pct >= 80:
                    critical_alerts.append(("Railway Free Tier Warning", f"Usage at {pct:.0f}% ({used}/{limit} min) — approaching monthly limit.", "Consider upgrading Railway plan before limit is reached."))
            else:
                ok.append("Railway hours: usage data unavailable (paid plan?) ✅")
    except Exception as e:
        print(f"[system_check] Railway hours check failed: {e}")

    try:
        from db import _get_file
        test, _ = await asyncio.to_thread(_get_file, "data/health.json")
        if test is None:
            issues.append("GitHub token may have expired — health.json unreadable ❌")
            critical_alerts.append(("GitHub Token May Be Expired", "Cannot read data/health.json — ML data will not save.", "Check GITHUB_TOKEN in Railway env vars and renew if expired."))
        else:
            ok.append("GitHub token valid ✅")
    except Exception as e:
        err_str = str(e)
        if "401" in err_str or "403" in err_str or "Bad credentials" in err_str:
            critical_alerts.append(("GitHub Token Expired", "GitHub API returned auth error — weights and trade history cannot be saved.", "Renew GITHUB_TOKEN in Railway environment variables immediately."))
        issues.append(f"GitHub token check failed: {e} ❌")

    try:
        from db import _get_file
        from datetime import timedelta
        history, _ = await asyncio.to_thread(_get_file, "data/trade_history.json")
        if isinstance(history, list) and len(history) > 0:
            last_trade_time = datetime.fromisoformat(history[-1].get("created_at", "2000-01-01T00:00:00").replace("Z", "+00:00"))
            if last_trade_time.tzinfo is None:
                last_trade_time = last_trade_time.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_trade_time).total_seconds() / 3600
            dow = datetime.now(timezone.utc).weekday()
            market_hour = 7 <= datetime.now(timezone.utc).hour < 20
            if dow < 5 and market_hour and hours_since > 6:
                critical_alerts.append(("Webhook Silence Detected", f"No trade data received for {hours_since:.0f} hours during market hours.", "Check TradingView alerts — they may have expired or been disabled."))
                issues.append(f"No webhook activity for {hours_since:.0f}h during market hours ⚠️")
            else:
                ok.append(f"Last webhook: {hours_since:.1f}h ago ✅")
    except Exception as e:
        print(f"[system_check] Webhook silence check failed: {e}")

    try:
        from db import _get_file, _put_file
        history, sha = await asyncio.to_thread(_get_file, "data/trade_history.json")
        if isinstance(history, list) and len(history) > 0:
            seen_ids = set()
            deduped = []
            for trade in history:
                tid = str(trade.get("id", "")) + trade.get("created_at", "")
                if tid not in seen_ids:
                    seen_ids.add(tid)
                    deduped.append(trade)
            if len(deduped) < len(history):
                removed = len(history) - len(deduped)
                await asyncio.to_thread(_put_file, "data/trade_history.json", deduped, sha, f"chore: deduplicate {removed} duplicate trades")
                print(f"[system_check] Auto-fixed: removed {removed} duplicate trades.")
            else:
                print(f"[system_check] Trade history clean — no duplicates.")
    except Exception as e:
        print(f"[system_check] Dedup auto-fix failed: {e}")

    try:
        from ml_ensemble import get_rf, get_gbm
        from db import recent_outcomes
        retrain_pools = ["XAUUSD", "XAUUSD_2M", "XAUUSD_5M", "XAUUSD_30M", "XAUUSD_1H",
                         "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_1H",
                         "STOCKS_QUALITY_30M", "STOCKS_QUALITY_1H",
                         "STOCKS_INDEX_30M", "STOCKS_INDEX_1H"]
        for _pool in retrain_pools:
            _trades = await asyncio.to_thread(recent_outcomes, _pool, 500)
            if len(_trades) >= 15:
                await asyncio.to_thread(get_rf(_pool).retrain, _trades)
                await asyncio.to_thread(get_gbm(_pool).train, _trades)
                print(f"[system_check] RF+GBM refreshed for {_pool} on {len(_trades)} trades.")
    except Exception as e:
        print(f"[system_check] Ensemble retrain failed: {e}")

    n_issue = len(issues)
    print(f"[system_check] {len(ok)}/{len(ok)+n_issue} checks passed.")
    for iss in issues:
        print(f"[system_check] ISSUE: {iss}")
    for title, detail, action in critical_alerts:
        print(f"[system_check] CRITICAL: {title} — {detail}")
        await send_critical_alert(title, detail, action)


async def _daily_market_brief() -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if now.weekday() >= 5:
        return
    print("[daily] Generating daily market brief…")
    try:
        from daily_analysis import generate_daily_brief
        from telegram_bot import send_text
        msg = await asyncio.to_thread(generate_daily_brief)
        if msg:
            await send_text(msg)
            print("[daily] Daily brief sent to Telegram.")
        else:
            print("[daily] Brief generation returned None — skipped.")
    except Exception as e:
        print(f"[daily] Brief error: {e}")


async def _test_personal_alert() -> None:
    from telegram_bot import send_critical_alert
    await send_critical_alert(
        "System Monitor Test",
        "Personal alerts are working correctly. You will receive warnings here for: Railway hours, GitHub token expiry, and webhook silence.",
        "No action needed — this is a test."
    )


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    _load_seen_headlines()
    interval   = int(os.environ.get("SIGNAL_INTERVAL_MINUTES", "15"))
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(_news_signal_cycle, trigger="interval", minutes=interval, id="news_signal_cycle", replace_existing=True)
    _scheduler.add_job(_breaking_news_cycle, trigger="interval", minutes=2, id="breaking_news_cycle", replace_existing=True)
    _scheduler.add_job(_hourly_system_check, trigger="interval", hours=1, id="hourly_system_check", replace_existing=True)
    _scheduler.add_job(_daily_market_brief, trigger="cron", hour=8, minute=0, id="daily_market_brief", replace_existing=True)
    _scheduler.start()
    print(f"[scheduler] Started — signal every {interval} min, breaking news every 2 min (Telegram paused), system check every 60 min, daily brief at 08:00 UTC.")
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[scheduler] Stopped.")
