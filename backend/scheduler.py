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
_last_sent_direction: str     = "NEUTRAL"
_last_sent_direction_spy: str = "NEUTRAL"
_last_sent_direction_qqq: str = "NEUTRAL"
_startup_cycle: bool = True  # suppress alert on first cycle after restart
_webhook_errors:  int = 0   # count of failed trade webhooks since last hourly check
_webhook_ok:      int = 0   # count of successful trade webhooks since last hourly check

_SEEN_HEADLINES_PATH = "data/seen_headlines.json"
_SEEN_HEADLINES_MAX  = 500


def _cached_macro_label() -> str:
    try:
        from market_macro import get_macro_bias
        m = get_macro_bias()
        return f"{m.get('label','?')} ({m.get('bias', 0):+.2f})"
    except Exception:
        return "n/a"


def _live_macro_bias() -> float:
    try:
        from market_macro import get_macro_bias
        return float(get_macro_bias().get("bias", 0.0) or 0.0)
    except Exception:
        return 0.0


def _live_macro_label() -> str:
    try:
        from market_macro import get_macro_bias
        return get_macro_bias().get("label", "n/a") or "n/a"
    except Exception:
        return "n/a"


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
    global _fj_seen_headlines, _last_sent_direction, _last_sent_direction_spy, _last_sent_direction_qqq
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
                    elif sym == "QQQ" and _last_sent_direction_qqq == "NEUTRAL":
                        _last_sent_direction_qqq = d
                        print(f"[scheduler] QQQ last sent direction restored: {d}")
                    elif sym not in ("SPY", "QQQ") and _last_sent_direction == "NEUTRAL":
                        _last_sent_direction = d
                        print(f"[scheduler] XAUUSD last sent direction restored: {d}")

                all_restored = (
                    _last_sent_direction     != "NEUTRAL" and
                    _last_sent_direction_spy != "NEUTRAL" and
                    _last_sent_direction_qqq != "NEUTRAL"
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
    global _latest_news_agg, _latest_velocity, _latest_event, _fj_seen_headlines, _last_sent_direction, _last_sent_direction_spy, _last_sent_direction_qqq, _startup_cycle
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

        from market_macro import get_macro_bias, get_equity_macro_bias
        _gold_macro   = get_macro_bias()
        _equity_macro = get_equity_macro_bias()
        signal = generate_signal(
            current_features=get_latest_features("XAUUSD_2M"),
            news_agg=_latest_news_agg,
            news_velocity=_latest_velocity,
            high_impact_event=_latest_event,
            symbol="XAUUSD",
            pool="XAUUSD_2M",
            macro_bias=_gold_macro,
        )
        print(
            f"[scheduler] Signal: {signal['direction']} "
            f"conf={signal['confidence']:.2f} "
            f"velocity={signal['news_velocity']} ×{signal['velocity_mult']}"
        )

        # ── Send direction alert — only on explicit LONG/SHORT flip with confidence > 0 ──
        new_dir  = signal["direction"]
        new_conf = signal.get("confidence", 0.0)
        direction_changed = (
            new_dir not in ("NEUTRAL", "") and
            new_conf > 0 and
            new_dir != _last_sent_direction and
            not _startup_cycle
        )

        if direction_changed:
            sent = await send_signal(signal)
            if sent:
                _last_sent_direction = new_dir
                print(f"[scheduler] XAUUSD direction → {new_dir} conf={new_conf:.2f} — signal sent.")
            else:
                print("[scheduler] Telegram send failed (check TOKEN/CHAT_ID).")
        else:
            print(f"[scheduler] XAUUSD: {new_dir} conf={new_conf:.2f} — no flip, not sending.")

        try:
            spy_signal = generate_signal(
                current_features=get_latest_features("STOCKS_INDEX_30M"),
                news_agg=_latest_news_agg,
                news_velocity=_latest_velocity,
                high_impact_event=_latest_event,
                symbol="SPY",
                pool="STOCKS_INDEX_30M",
                macro_bias=_equity_macro,
            )
            spy_dir  = spy_signal["direction"]
            spy_conf = spy_signal.get("confidence", 0.0)
            print(f"[scheduler] SPY: {spy_dir} conf={spy_conf:.2f} sess={spy_signal['session']}")

            spy_changed = (
                spy_dir not in ("NEUTRAL", "") and
                spy_conf > 0 and
                spy_dir != _last_sent_direction_spy and
                not _startup_cycle
            )

            if spy_changed:
                sent_spy = await send_signal(spy_signal)
                if sent_spy:
                    _last_sent_direction_spy = spy_dir
                    print(f"[scheduler] SPY direction → {spy_dir} conf={spy_conf:.2f} — signal sent.")
            else:
                print(f"[scheduler] SPY: {spy_dir} conf={spy_conf:.2f} — no flip, not sending.")
        except Exception as e:
            print(f"[scheduler] SPY signal error: {e}")

        try:
            qqq_signal = generate_signal(
                current_features=get_latest_features("STOCKS_QQQ_30M"),
                news_agg=_latest_news_agg,
                news_velocity=_latest_velocity,
                high_impact_event=_latest_event,
                symbol="QQQ",
                pool="STOCKS_QQQ_30M",
                macro_bias=_equity_macro,
            )
            qqq_dir  = qqq_signal["direction"]
            qqq_conf = qqq_signal.get("confidence", 0.0)
            print(f"[scheduler] QQQ: {qqq_dir} conf={qqq_conf:.2f} sess={qqq_signal['session']}")

            qqq_changed = (
                qqq_dir not in ("NEUTRAL", "") and
                qqq_conf > 0 and
                qqq_dir != _last_sent_direction_qqq and
                not _startup_cycle
            )

            if qqq_changed:
                sent_qqq = await send_signal(qqq_signal)
                if sent_qqq:
                    _last_sent_direction_qqq = qqq_dir
                    print(f"[scheduler] QQQ direction → {qqq_dir} conf={qqq_conf:.2f} — signal sent.")
            else:
                print(f"[scheduler] QQQ: {qqq_dir} conf={qqq_conf:.2f} — no flip, not sending.")
        except Exception as e:
            print(f"[scheduler] QQQ signal error: {e}")

        _startup_cycle = False  # first cycle complete — normal firing from here on
        asyncio.create_task(_write_health_status(signal, _latest_news_agg, _latest_velocity, len(fj_breaking), _equity_macro))

    except Exception as e:
        print(f"[scheduler] Cycle error: {e}")


async def _write_health_status(signal: dict, news_agg: float, velocity: dict, breaking_count: int, equity_macro: dict | None = None) -> None:
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
            "macro_bias":         _live_macro_bias(),
            "macro_label":        _live_macro_label(),
            "equity_macro_bias":  (equity_macro or {}).get("bias", 0.0),
            "equity_macro_label": (equity_macro or {}).get("label", "n/a"),
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
            expected = {"news_signal_cycle", "breaking_news_cycle", "hourly_system_check", "macro_refresh_cycle", "daily_market_brief", "stocks_session_report", "daily_trade_count_report"}
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
            ("data/trade_history_XAUUSD_30M.json",           "XAUUSD_30M",           gold_active,   48),
            ("data/trade_history_XAUUSD_1H.json",            "XAUUSD_1H",            gold_active,   72),
            ("data/trade_history_STOCKS_MOMENTUM_15M.json",  "STOCKS_MOMENTUM_15M",  stocks_active,  3),
            ("data/trade_history_STOCKS_MOMENTUM_30M.json",  "STOCKS_MOMENTUM_30M",  stocks_active,  4),
            ("data/trade_history_STOCKS_QUALITY_15M.json",   "STOCKS_QUALITY_15M",   stocks_active,  3),
            ("data/trade_history_STOCKS_QUALITY_30M.json",   "STOCKS_QUALITY_30M",   stocks_active,  4),
            ("data/trade_history_STOCKS_INDEX_15M.json",     "STOCKS_INDEX_15M",     stocks_active,  3),
            ("data/trade_history_STOCKS_INDEX_30M.json",     "STOCKS_INDEX_30M",     stocks_active,  4),
            ("data/trade_history_STOCKS_QQQ_15M.json",       "STOCKS_QQQ_15M",       stocks_active,  3),
            ("data/trade_history_STOCKS_QQQ_30M.json",       "STOCKS_QQQ_30M",       stocks_active,  4),
            ("data/trade_history_STOCKS_SPX500_15M.json",    "STOCKS_SPX500_15M",    stocks_active,  6),
            ("data/trade_history_STOCKS_SPX500_30M.json",    "STOCKS_SPX500_30M",    stocks_active,  8),
            ("data/trade_history_STOCKS_MOMENTUM_4H.json",   "STOCKS_MOMENTUM_4H",   stocks_active,  8),
            ("data/trade_history_STOCKS_QUALITY_4H.json",    "STOCKS_QUALITY_4H",    stocks_active,  8),
            ("data/trade_history_STOCKS_INDEX_4H.json",      "STOCKS_INDEX_4H",      stocks_active,  8),
            ("data/trade_history_STOCKS_QQQ_4H.json",        "STOCKS_QQQ_4H",        stocks_active,  8),
            ("data/trade_history_STOCKS_SPX500_4H.json",     "STOCKS_SPX500_4H",     stocks_active, 12),
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
                             "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H",
                             "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_4H",
                             "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_4H"]:
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
                         "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H",
                         "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_4H",
                         "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_4H"]
        for _pool in retrain_pools:
            _trades = await asyncio.to_thread(recent_outcomes, _pool, 500)
            if len(_trades) >= 50:
                await asyncio.to_thread(get_rf(_pool).retrain, _trades)
                await asyncio.to_thread(get_gbm(_pool).train, _trades)
                print(f"[system_check] RF+GBM refreshed for {_pool} on {len(_trades)} trades.")
    except Exception as e:
        print(f"[system_check] Ensemble retrain failed: {e}")

    try:
        from db import resync_pool_counters
        sync_pools = ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_30M", "XAUUSD_1H",
                      "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_4H",
                      "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_4H",
                      "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H",
                      "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_4H",
                      "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_4H"]
        for _pool in sync_pools:
            await asyncio.to_thread(resync_pool_counters, _pool)
    except Exception as e:
        print(f"[system_check] Counter resync failed: {e}")

    n_issue = len(issues)
    print(f"[system_check] {len(ok)}/{len(ok)+n_issue} checks passed.")
    for iss in issues:
        print(f"[system_check] ISSUE: {iss}")
    for title, detail, action in critical_alerts:
        print(f"[system_check] CRITICAL: {title} — {detail}")
        await send_critical_alert(title, detail, action)


async def _daily_trade_count_report() -> None:
    """
    Daily performance summary at 21:15 UTC (after US session close).
    Shows signals fired today, TP wins, SL hits, win ratio — consolidated across all pools,
    with a per-symbol breakdown for XAUUSD vs each stock symbol.
    """
    from datetime import datetime, timezone, date
    if datetime.now(timezone.utc).weekday() >= 5:
        return
    try:
        from db import _get_file
        from telegram_bot import send_text

        today = date.today().isoformat()
        all_paths = [
            "data/trade_history_XAUUSD_2M.json",
            "data/trade_history_XAUUSD_5M.json",
            "data/trade_history_XAUUSD_30M.json",
            "data/trade_history_XAUUSD_1H.json",
            "data/trade_history_STOCKS_MOMENTUM_15M.json",
            "data/trade_history_STOCKS_QUALITY_15M.json",
            "data/trade_history_STOCKS_INDEX_15M.json",
            "data/trade_history_STOCKS_QQQ_15M.json",
            "data/trade_history_STOCKS_SPX500_15M.json",
            "data/trade_history_STOCKS_MOMENTUM_30M.json",
            "data/trade_history_STOCKS_QUALITY_30M.json",
            "data/trade_history_STOCKS_INDEX_30M.json",
            "data/trade_history_STOCKS_QQQ_30M.json",
            "data/trade_history_STOCKS_SPX500_30M.json",
            "data/trade_history_STOCKS_MOMENTUM_4H.json",
            "data/trade_history_STOCKS_QUALITY_4H.json",
            "data/trade_history_STOCKS_INDEX_4H.json",
            "data/trade_history_STOCKS_QQQ_4H.json",
            "data/trade_history_STOCKS_SPX500_4H.json",
        ]

        # Collect all today's closed trades across every pool
        today_all: list[dict] = []
        for path in all_paths:
            hist, _ = await asyncio.to_thread(_get_file, path)
            if not isinstance(hist, list):
                continue
            for t in hist:
                if t.get("created_at", "").startswith(today):
                    today_all.append(t)

        now_utc = datetime.now(timezone.utc)
        date_str = now_utc.strftime("%d %b %Y")

        def _stats(trades: list[dict]) -> tuple[int, int, int, int]:
            """Return (total, tp_wins, sl_hits, partials)."""
            tp  = sum(1 for t in trades if t.get("outcome") == "WIN")
            sl  = sum(1 for t in trades if t.get("outcome") == "LOSS")
            par = sum(1 for t in trades if t.get("outcome") == "PARTIAL")
            return len(trades), tp, sl, par

        def _wr_line(total: int, tp: int, sl: int, par: int) -> str:
            effective_wins = tp + par  # TP1/TP2 hit = counted as win
            wr = effective_wins / total * 100 if total else 0.0
            return (
                f"Signals: <b>{total}</b>  |  "
                f"✅ TP: {tp}  🔶 Partial: {par}  ❌ SL: {sl}\n"
                f"Win ratio (TP+Partial): <b>{wr:.0f}%</b>"
            )

        # ── Overall ──────────────────────────────────────────────────────────
        tot, tp, sl, par = _stats(today_all)

        # ── Per instrument breakdown ──────────────────────────────────────────
        gold_trades   = [t for t in today_all if t.get("symbol","").upper() in ("XAUUSD","GOLD","GC")]
        spy_trades    = [t for t in today_all if t.get("symbol","").upper() == "SPY"]
        qqq_trades    = [t for t in today_all if t.get("symbol","").upper() == "QQQ"]
        other_trades  = [t for t in today_all if t.get("symbol","").upper() not in ("XAUUSD","GOLD","GC","SPY","QQQ")]

        lines = []

        if not today_all:
            lines.append("No closed trades recorded today.")
        else:
            lines.append(_wr_line(tot, tp, sl, par))

            if gold_trades:
                g_tot, g_tp, g_sl, g_par = _stats(gold_trades)
                lines.append(f"\n🥇 <b>XAUUSD</b> ({g_tot} trades)")
                lines.append(_wr_line(g_tot, g_tp, g_sl, g_par))

            if spy_trades:
                s_tot, s_tp, s_sl, s_par = _stats(spy_trades)
                lines.append(f"\n📊 <b>SPY</b> ({s_tot} trades)")
                lines.append(_wr_line(s_tot, s_tp, s_sl, s_par))

            if qqq_trades:
                q_tot, q_tp, q_sl, q_par = _stats(qqq_trades)
                lines.append(f"\n📊 <b>QQQ</b> ({q_tot} trades)")
                lines.append(_wr_line(q_tot, q_tp, q_sl, q_par))

            if other_trades:
                o_tot, o_tp, o_sl, o_par = _stats(other_trades)
                lines.append(f"\n📈 <b>Stocks</b> ({o_tot} trades)")
                lines.append(_wr_line(o_tot, o_tp, o_sl, o_par))

        # All-time totals for context
        all_hist_total = 0
        for path in all_paths:
            hist, _ = await asyncio.to_thread(_get_file, path)
            if isinstance(hist, list):
                all_hist_total += len(hist)

        msg = (
            f"📊 <b>DAILY PERFORMANCE REPORT — {date_str}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines) +
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"All-time trades: <b>{all_hist_total}</b> | "
            f"Macro: {_cached_macro_label()} | "
            f"⏰ {now_utc.strftime('%H:%M UTC')}"
        )
        await send_text(msg)
        print(f"[daily_report] Performance report sent — {tot} trades today, TP={tp} SL={sl} P={par}.")
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


async def _macro_refresh_cycle() -> None:
    """Refresh gold macro drivers (FRED real yields/dollar, CFTC COT, GLD flows) hourly."""
    try:
        from market_macro import refresh_macro_bias
        await asyncio.to_thread(refresh_macro_bias)
    except Exception as e:
        print(f"[scheduler] macro refresh failed: {e}")


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
    _scheduler.add_job(_macro_refresh_cycle, trigger="interval", hours=1, id="macro_refresh_cycle", replace_existing=True,
                       start_date=_dt.now(_tz.utc) + _td(seconds=20))
    _scheduler.add_job(_daily_market_brief, trigger="cron", hour=8, minute=0, id="daily_market_brief", replace_existing=True, misfire_grace_time=3600)
    _scheduler.add_job(_stocks_session_report, trigger="cron", hour=21, minute=5, id="stocks_session_report", replace_existing=True, misfire_grace_time=3600)
    _scheduler.add_job(_daily_trade_count_report, trigger="cron", hour=21, minute=1, id="daily_trade_count_report", replace_existing=True, misfire_grace_time=3600)
    _scheduler.start()

    _now = _dt.now(_tz.utc)

    # Startup catch-up: fire daily brief if missed today (redeploy between 08:00–11:00)
    if _now.weekday() < 5 and 8 <= _now.hour < 11:
        print("[scheduler] Startup catch-up: firing missed daily brief.")
        _scheduler.add_job(_daily_market_brief, trigger="date", run_date=_now + _td(seconds=30),
                           id="daily_brief_catchup", replace_existing=True)

    # Startup catch-up: fire daily performance report only if we missed the 21:01 cron (boot after 21:00 UTC)
    if _now.weekday() < 5 and _now.hour >= 21:
        print("[scheduler] Startup catch-up: firing daily performance report on boot.")
        _scheduler.add_job(_daily_trade_count_report, trigger="date", run_date=_now + _td(seconds=45),
                           id="daily_report_catchup", replace_existing=True)

    print(f"[scheduler] Started — signal every {interval} min, breaking news every 2 min (Telegram paused), system check every 60 min, daily brief at 08:00 UTC.")
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        print("[scheduler] Stopped.")
