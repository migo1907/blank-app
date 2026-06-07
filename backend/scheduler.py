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
_last_ml_direction: str   = "NEUTRAL"
_last_ml_direction_spy: str = "NEUTRAL"
_startup_cycle: bool = True  # suppress intelligence alert on first cycle after restart
_webhook_errors:  int = 0   # count of failed trade webhooks since last hourly check
_webhook_ok:      int = 0   # count of successful trade webhooks since last hourly check

_SEEN_HEADLINES_PATH = "data/seen_headlines.json"
_SEEN_HEADLINES_MAX  = 500


def get_latest_news_sentiment() -> float:
    return _latest_news_agg

def get_latest_velocity() -> dict:
    return _latest_velocity

def get_latest_event() -> dict:
    return _latest_event

def record_webhook_ok() -> None:
    global _webhook_ok
    _webhook_ok += 1

def record_webhook_error() -> None:
    global _webhook_errors
    _webhook_errors += 1


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
                sym   = sig.get("symbol", "XAUUSD")
                d     = sig.get("direction")
                score = sig.get("combined_score", 0.0)
                ml_d  = "LONG" if score > 0 else "SHORT" if score < 0 else "NEUTRAL"

                if d not in ("NEUTRAL", None, ""):
                    if sym == "SPY" and _last_sent_direction_spy == "NEUTRAL":
                        _last_sent_direction_spy = d
                        print(f"[scheduler] SPY last sent direction restored: {d}")
                    elif sym != "SPY" and _last_sent_direction == "NEUTRAL":
                        _last_sent_direction = d
                        print(f"[scheduler] Last sent direction restored: {d}")

                if ml_d != "NEUTRAL":
                    if sym == "SPY" and _last_ml_direction_spy == "NEUTRAL":
                        _last_ml_direction_spy = ml_d
                        print(f"[scheduler] SPY last ML direction restored: {ml_d}")
                    elif sym != "SPY" and _last_ml_direction == "NEUTRAL":
                        _last_ml_direction = ml_d
                        print(f"[scheduler] Last ML direction restored: {ml_d}")

                all_restored = (
                    _last_sent_direction != "NEUTRAL" and _last_sent_direction_spy != "NEUTRAL" and
                    _last_ml_direction   != "NEUTRAL" and _last_ml_direction_spy   != "NEUTRAL"
                )
                if all_restored:
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
    global _latest_news_agg, _latest_velocity, _latest_event, _fj_seen_headlines, _last_sent_direction, _last_sent_direction_spy, _last_ml_direction, _last_ml_direction_spy, _startup_cycle
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
            current_features=get_latest_features("XAUUSD_2M"),
            news_agg=_latest_news_agg,
            news_velocity=_latest_velocity,
            high_impact_event=_latest_event,
            symbol="XAUUSD",
            pool="XAUUSD_2M",
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

        # ── Market Intelligence — fire on ML direction flip (regardless of confidence) ──
        from telegram_bot import send_market_intelligence
        ml_direction = "LONG" if signal.get("combined_score", 0) > 0 else "SHORT" if signal.get("combined_score", 0) < 0 else "NEUTRAL"
        if ml_direction != "NEUTRAL" and ml_direction != _last_ml_direction:
            if _startup_cycle:
                print(f"[scheduler] Startup cycle — suppressing intelligence alert, direction={ml_direction}.")
            else:
                await send_market_intelligence(signal, ml_direction)
                print(f"[scheduler] ML direction flipped → {ml_direction} — intelligence alert sent.")
            _last_ml_direction = ml_direction

        try:
            spy_signal = generate_signal(
                current_features=get_latest_features("STOCKS_INDEX_30M"),
                news_agg=_latest_news_agg,
                news_velocity=_latest_velocity,
                high_impact_event=_latest_event,
                symbol="SPY",
                pool="STOCKS_INDEX_30M",
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

            # SPY ML direction flip intelligence
            spy_ml_dir = "LONG" if spy_signal.get("combined_score", 0) > 0 else "SHORT" if spy_signal.get("combined_score", 0) < 0 else "NEUTRAL"
            if spy_ml_dir != "NEUTRAL" and spy_ml_dir != _last_ml_direction_spy:
                if _startup_cycle:
                    print(f"[scheduler] Startup cycle — suppressing SPY intelligence alert, direction={spy_ml_dir}.")
                else:
                    await send_market_intelligence(spy_signal, spy_ml_dir)
                    print(f"[scheduler] SPY ML direction flipped → {spy_ml_dir} — intelligence alert sent.")
                _last_ml_direction_spy = spy_ml_dir
        except Exception as e:
            print(f"[scheduler] SPY signal error: {e}")

        _startup_cycle = False  # first cycle complete — normal firing from here on
        asyncio.create_task(_write_health_status(signal, _latest_news_agg, _latest_velocity, len(fj_breaking)))

    except Exception as e:
        print(f"[scheduler] Cycle error: {e}")


async def _write_health_status(signal: dict, news_agg: float, velocity: dict, breaking_count: int) -> None:
    try:
        from db import _get_file, _put_file
        from datetime import datetime, timezone
        from ml_model import get_model
        from ml_ensemble import get_rf
        from db import recent_outcomes
        model  = get_model("XAUUSD_2M")
        rf     = get_rf("XAUUSD_2M")
        trades = await asyncio.to_thread(recent_outcomes, "XAUUSD_2M", 500)
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
        history_2m, _ = await asyncio.to_thread(_get_file, "data/trade_history_XAUUSD_2M.json")
        trade_count = len(history_2m) if isinstance(history_2m, list) else 0
        if trade_count >= 15:
            ok.append(f"XAUUSD_2M pool — {trade_count} trades ✅")
        elif trade_count > 0:
            issues.append(f"XAUUSD_2M pool — only {trade_count} trades (need 15 for RF) ⚠️")
        else:
            issues.append("XAUUSD_2M pool empty ❌")
    except Exception as e:
        issues.append(f"GitHub db layer error: {e} ❌")

    try:
        from ml_model import get_model
        model = get_model("XAUUSD_2M")
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
        rf = get_rf("XAUUSD_2M")
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
            expected = {"news_signal_cycle", "breaking_news_cycle", "hourly_system_check", "daily_market_brief", "stocks_session_report", "daily_trade_count_report"}
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
        hist_2m, _ = await asyncio.to_thread(_get_file, "data/trade_history_XAUUSD_2M.json")
        if isinstance(hist_2m, list) and len(hist_2m) > 0:
            last_trade = hist_2m[-1]
            f25_present = "f25_tod"  in last_trade
            f9_present  = "f9_fvg"   in last_trade
            if f25_present and f9_present:
                ok.append("Feature vector f1-f25 present in latest XAUUSD_2M trade ✅")
            else:
                missing_f = []
                if not f9_present:  missing_f.append("f9_fvg")
                if not f25_present: missing_f.append("f25_tod")
                issues.append(f"Latest XAUUSD_2M trade missing features: {missing_f} ⚠️")
        else:
            issues.append("XAUUSD_2M has no trades — feature check skipped ⚠️")
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
        hist_2m, _ = await asyncio.to_thread(_get_file, "data/trade_history_XAUUSD_2M.json")
        if isinstance(hist_2m, list) and len(hist_2m) > 0:
            last_trade_time = datetime.fromisoformat(hist_2m[-1].get("created_at", "2000-01-01T00:00:00").replace("Z", "+00:00"))
            if last_trade_time.tzinfo is None:
                last_trade_time = last_trade_time.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_trade_time).total_seconds() / 3600
            dow = datetime.now(timezone.utc).weekday()
            market_hour = 7 <= datetime.now(timezone.utc).hour < 20
            if dow < 5 and market_hour and hours_since > 6:
                critical_alerts.append(("Webhook Silence Detected", f"No XAUUSD_2M trade data received for {hours_since:.0f} hours during market hours.", "Check TradingView alerts — they may have expired or been disabled."))
                issues.append(f"No XAUUSD_2M webhook activity for {hours_since:.0f}h during market hours ⚠️")
            else:
                ok.append(f"XAUUSD_2M last webhook: {hours_since:.1f}h ago ✅")
        else:
            issues.append("XAUUSD_2M pool empty — webhook silence check skipped ⚠️")
    except Exception as e:
        print(f"[system_check] Webhook silence check failed: {e}")

    # ── Webhook trade flow check (per pool) ──────────────────────────────────────
    try:
        global _webhook_errors, _webhook_ok
        now_utc  = datetime.now(timezone.utc)
        dow      = now_utc.weekday()           # 0=Mon … 4=Fri
        hour_utc = now_utc.hour
        gold_active   = (dow < 5)              # gold trades Mon-Fri; skip weekend silence alerts
        stocks_active = (dow < 5 and 13 <= hour_utc < 21)  # stocks 09:30–17:00 ET ≈ 13:30–21:00 UTC

        active_pools = [
            ("data/trade_history_XAUUSD_2M.json",            "XAUUSD_2M",            gold_active,    6),
            ("data/trade_history_XAUUSD_5M.json",            "XAUUSD_5M",            gold_active,    8),
            ("data/trade_history_XAUUSD_30M.json",           "XAUUSD_30M",           gold_active,   12),
            ("data/trade_history_XAUUSD_1H.json",            "XAUUSD_1H",            gold_active,   16),
            ("data/trade_history_STOCKS_MOMENTUM_15M.json",  "STOCKS_MOMENTUM_15M",  stocks_active,  3),
            ("data/trade_history_STOCKS_MOMENTUM_30M.json",  "STOCKS_MOMENTUM_30M",  stocks_active,  4),
            ("data/trade_history_STOCKS_QUALITY_15M.json",   "STOCKS_QUALITY_15M",   stocks_active,  3),
            ("data/trade_history_STOCKS_QUALITY_30M.json",   "STOCKS_QUALITY_30M",   stocks_active,  4),
            ("data/trade_history_STOCKS_INDEX_15M.json",     "STOCKS_INDEX_15M",     stocks_active,  3),
            ("data/trade_history_STOCKS_INDEX_30M.json",     "STOCKS_INDEX_30M",     stocks_active,  4),
            ("data/trade_history_STOCKS_MOMENTUM_4H.json",   "STOCKS_MOMENTUM_4H",   stocks_active,  8),
            ("data/trade_history_STOCKS_QUALITY_4H.json",    "STOCKS_QUALITY_4H",    stocks_active,  8),
            ("data/trade_history_STOCKS_INDEX_4H.json",      "STOCKS_INDEX_4H",      stocks_active,  8),
        ]

        silent_pools = []
        for path, pool_name, is_active, max_silent_hours in active_pools:
            if not is_active:
                continue
            try:
                hist, _ = await asyncio.to_thread(_get_file, path)
                if isinstance(hist, list) and hist:
                    last_ts = datetime.fromisoformat(hist[-1].get("created_at", "2000-01-01T00:00:00+00:00").replace("Z", "+00:00"))
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    hours_since = (now_utc - last_ts).total_seconds() / 3600
                    if hours_since > max_silent_hours:
                        silent_pools.append(f"{pool_name}: {hours_since:.0f}h since last trade")
            except Exception:
                pass

        if silent_pools:
            detail = "\n".join(silent_pools)
            critical_alerts.append((
                "Trade Flow Gap Detected",
                f"Pools with no new trades during active hours:\n{detail}",
                "Check TradingView webhook log for 422 errors or expired alerts."
            ))
            issues.append(f"Trade flow gap in {len(silent_pools)} pool(s) ⚠️")
        else:
            ok.append("Trade flow — all active pools receiving data ✅")

        # Webhook error counter check
        if _webhook_errors > 0:
            critical_alerts.append((
                "Webhook Errors Detected",
                f"{_webhook_errors} webhook(s) failed in the last hour — {_webhook_ok} succeeded.",
                "Check Railway logs for details. Trades may not be recording correctly."
            ))
            issues.append(f"{_webhook_errors} webhook error(s) in last hour ⚠️")
            _webhook_errors = 0
            _webhook_ok     = 0
        else:
            ok.append(f"Webhook errors — none in last hour ({_webhook_ok} ok) ✅")
            _webhook_ok = 0

    except Exception as e:
        print(f"[system_check] Trade flow check failed: {e}")

    # ── Auto-repair missing trades from webhook log ───────────────────────────────
    try:
        from db import repair_missing_trades
        repaired = await asyncio.to_thread(repair_missing_trades)
        if repaired:
            detail = "\n".join(repaired)
            await send_critical_alert(
                "Auto-Repair: Missing Trades Recovered",
                f"{len(repaired)} trade(s) missing from pools were auto-inserted:\n{detail}",
                "Trades recovered from webhook_log.json — check data branch to verify.",
            )
            issues.append(f"Auto-repaired {len(repaired)} missing trade(s) ✅")
        else:
            ok.append("Auto-repair scan — no missing trades found ✅")
    except Exception as e:
        print(f"[system_check] Auto-repair failed: {e}")

    try:
        from db import _get_file, _put_file
        for _dedup_pool in ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_30M", "XAUUSD_1H",
                             "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_4H",
                             "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_4H",
                             "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H"]:
            _path = f"data/trade_history_{_dedup_pool}.json"
            _hist, _sha = await asyncio.to_thread(_get_file, _path)
            if not isinstance(_hist, list) or len(_hist) == 0:
                continue
            seen_keys: set = set()
            deduped = []
            for trade in _hist:
                key = f"{trade.get('symbol','')}|{trade.get('direction','')}|{trade.get('entry_price',0)}|{trade.get('timeframe','')}|{trade.get('exit_price',0)}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    deduped.append(trade)
            if len(deduped) < len(_hist):
                removed = len(_hist) - len(deduped)
                await asyncio.to_thread(_put_file, _path, deduped, _sha, f"chore: deduplicate {removed} dupes in {_dedup_pool}")
                print(f"[system_check] Auto-dedup: removed {removed} dupes from {_dedup_pool}.")
    except Exception as e:
        print(f"[system_check] Dedup auto-fix failed: {e}")

    try:
        from ml_ensemble import get_rf, get_gbm
        from db import recent_outcomes
        retrain_pools = ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_30M", "XAUUSD_1H",
                         "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_4H",
                         "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_4H",
                         "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H"]
        for _pool in retrain_pools:
            _trades = await asyncio.to_thread(recent_outcomes, _pool, 500)
            if len(_trades) >= 50:
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


async def _daily_trade_count_report() -> None:
    """Send a daily trade-count summary to Telegram at 21:15 UTC (after US session close)."""
    from datetime import datetime, timezone, date
    if datetime.now(timezone.utc).weekday() >= 5:
        return
    try:
        from db import _get_file
        from telegram_bot import send_text

        today = date.today().isoformat()
        pools = [
            ("XAUUSD_2M",           "data/trade_history_XAUUSD_2M.json"),
            ("XAUUSD_5M",           "data/trade_history_XAUUSD_5M.json"),
            ("XAUUSD_30M",          "data/trade_history_XAUUSD_30M.json"),
            ("XAUUSD_1H",           "data/trade_history_XAUUSD_1H.json"),
            ("STOCKS_MOM_30M",      "data/trade_history_STOCKS_MOMENTUM_30M.json"),
            ("STOCKS_QUAL_30M",     "data/trade_history_STOCKS_QUALITY_30M.json"),
            ("STOCKS_IDX_30M",      "data/trade_history_STOCKS_INDEX_30M.json"),
            ("STOCKS_MOM_4H",       "data/trade_history_STOCKS_MOMENTUM_4H.json"),
            ("STOCKS_QUAL_4H",      "data/trade_history_STOCKS_QUALITY_4H.json"),
            ("STOCKS_IDX_4H",       "data/trade_history_STOCKS_INDEX_4H.json"),
        ]

        lines = []
        total_new = 0
        for pool_name, path in pools:
            hist, _ = await asyncio.to_thread(_get_file, path)
            if not isinstance(hist, list):
                continue
            today_trades = [t for t in hist if t.get("created_at", "").startswith(today)]
            if not today_trades:
                continue
            total = len(hist)
            n = len(today_trades)
            total_new += n
            w = sum(1 for t in today_trades if t.get("outcome") == "WIN")
            l = sum(1 for t in today_trades if t.get("outcome") == "LOSS")
            p = sum(1 for t in today_trades if t.get("outcome") == "PARTIAL")
            rf_ready = "✅" if total >= 15 else f"⏳{total}/15"
            lines.append(f"<b>{pool_name}</b>: +{n} today (W{w}/L{l}/P{p}) — total:{total} {rf_ready}")

        if not lines:
            lines.append("No trades recorded today.")

        now = datetime.now(timezone.utc).strftime("%d %b %Y")
        msg = (
            f"📊 <b>DAILY TRADE REPORT — {now}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines) +
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"Total new trades today: <b>{total_new}</b>\n"
            f"Webhook logger: ✅ active | Auto-repair: ✅ hourly"
        )
        await send_text(msg)
        print(f"[daily_report] Trade count report sent — {total_new} trades today.")
    except Exception as e:
        print(f"[daily_report] Error: {e}")


async def _stocks_session_report() -> None:
    from datetime import datetime, timezone
    if datetime.now(timezone.utc).weekday() >= 5:
        return
    print("[scheduler] Generating stocks session report…")
    try:
        from telegram_bot import send_stocks_session_report
        await send_stocks_session_report()
    except Exception as e:
        print(f"[session_report] Error: {e}")


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
    _scheduler = AsyncIOScheduler(
        job_defaults={
            "coalesce":           True,
            "max_instances":      1,
            "misfire_grace_time": 30,
        }
    )
    _scheduler.add_job(_news_signal_cycle, trigger="interval", minutes=interval, id="news_signal_cycle", replace_existing=True)
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    _scheduler.add_job(_breaking_news_cycle, trigger="interval", minutes=2, id="breaking_news_cycle", replace_existing=True,
                       start_date=_dt.now(_tz.utc) + _td(seconds=90))
    _scheduler.add_job(_hourly_system_check, trigger="interval", hours=1, id="hourly_system_check", replace_existing=True)
    _scheduler.add_job(_daily_market_brief, trigger="cron", hour=8, minute=0, id="daily_market_brief", replace_existing=True, misfire_grace_time=600)
    _scheduler.add_job(_stocks_session_report, trigger="cron", hour=21, minute=5, id="stocks_session_report", replace_existing=True, misfire_grace_time=600)
    _scheduler.add_job(_daily_trade_count_report, trigger="cron", hour=21, minute=15, id="daily_trade_count_report", replace_existing=True, misfire_grace_time=600)
    _scheduler.start()
    print(f"[scheduler] Started — signal every {interval} min, breaking news every 2 min (Telegram paused), system check every 60 min, daily brief at 08:00 UTC.")
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        print("[scheduler] Stopped.")
