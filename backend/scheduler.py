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
_intel_active:    bool = False  # True while market is in an elevated-activity regime (alert already sent)
_shock_sent:      dict = {}     # headline_hash → monotonic time; suppresses duplicate shock alerts for 4h
_fj_expiry_alert_at: float = 0.0  # monotonic time of last FJ-session-expired alert; throttles to 1/12h

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


_INTEL_HOT_VELOCITY = {"HIGH VELOCITY", "ELEVATED"}


def _evaluate_intel_triggers(velocity: dict, event: dict, gold_signal: dict, gold_flipped: bool) -> list[str]:
    """
    Build the list of trigger reasons for a Market Intelligence alert.
    Empty list = no elevated activity, no alert. Covers all four triggers:
    velocity spike, imminent high-impact event, ML flip on rising flow,
    and fast sentiment acceleration (regime shift).
    """
    reasons: list[str] = []
    vlabel = velocity.get("label", "NORMAL")
    vdir   = velocity.get("direction", "")
    accel  = velocity.get("acceleration", 0.0) or 0.0
    vol    = velocity.get("volume", 0) or 0

    # 1. Velocity spike — news flow entered an elevated state
    if vlabel in _INTEL_HOT_VELOCITY:
        reasons.append(f"{vlabel} news flow{(' · ' + vdir) if vdir else ''}")

    # 2. Imminent high-impact event (NFP/CPI/FOMC within ~90 min).
    # Only fire on SCHEDULED calendar events (minutes_until present) — reactive
    # keyword matches keep flagging "CPI" from analysis headlines for hours
    # AFTER the release, which is noise, not a de-risk warning.
    mins = event.get("minutes_until")
    if (event.get("detected") and event.get("urgency", 0.0) >= 0.85
            and isinstance(mins, (int, float)) and 0 <= mins <= 90):
        etype = event.get("event_type") or "High-impact event"
        reasons.append(f"{etype} in {int(mins)} min — volatility expected, de-risk")

    # 3. ML direction flip while news flow is hot — the move is news-backed
    if gold_flipped and vlabel in _INTEL_HOT_VELOCITY:
        reasons.append(f"ML direction flip → {gold_signal.get('direction','')} on rising flow")

    # 4. Regime shift — sentiment accelerating fast on real volume
    if accel >= 0.20 and vol >= 3:
        reasons.append(f"Sentiment accelerating fast (Δ{accel:.2f}) — regime shifting")

    # 5. Geopolitical / market shock — single-headline reactive events that are
    # time-critical by nature (no calendar). Unlike CPI-style releases, these
    # warrant an immediate heads-up even when overall news flow is calm.
    # Deduplication: same headline is suppressed for 4 hours to prevent repeat
    # alerts on every 15-min cycle when the headline stays in the feed.
    import time as _time
    _SHOCK_EVENTS = {"WAR/CONFLICT", "GEOPOLITICAL", "FLASH_CRASH"}
    _SHOCK_TTL = 4 * 3600
    if (event.get("detected") and event.get("event_type") in _SHOCK_EVENTS
            and event.get("urgency", 0.0) >= 0.9):
        heads = event.get("headlines") or []
        lead_text = heads[0][:90] if heads else ""
        shock_key = f"{event['event_type']}|{lead_text}"
        now_mono = _time.monotonic()
        # evict stale entries
        stale = [k for k, t in _shock_sent.items() if now_mono - t > _SHOCK_TTL]
        for k in stale:
            del _shock_sent[k]
        if shock_key not in _shock_sent:
            _shock_sent[shock_key] = now_mono
            lead = f' — “{lead_text}”' if lead_text else ""
            reasons.append(f"{event['event_type']} shock headline{lead}")

    return reasons


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
            # Throttle: the breaking cycle runs every ~2 min, so alert at most once
            # per 12h to flag the expiry without spamming the personal chat.
            global _fj_expiry_alert_at
            import time as _time
            _now_mono = _time.monotonic()
            if _now_mono - _fj_expiry_alert_at >= 12 * 3600:
                _fj_expiry_alert_at = _now_mono
                await send_critical_alert(
                    "FinancialJuice Session Expired",
                    "FJ breaking-banner login has stopped working (cookie expired or auto-login failing). "
                    "Your RSS-based news + ML intelligence is unaffected — only the live breaking banner is down.",
                    "Optional fix: log in to financialjuice.com in your browser, copy the new .ASPXAUTH cookie "
                    "value into Railway → Variables → FJ_SESSION_COOKIE, and redeploy.",
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

        # Breaking news Telegram — paused by default, set BREAKING_NEWS_TELEGRAM=true to enable
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

        # Phase 2D — refresh post-event volatility state (cheap calendar check
        # first; only fetches price reactions when a high-impact event just fired)
        try:
            from post_event import refresh_post_event
            await asyncio.to_thread(refresh_post_event)
        except Exception as _pe:
            print(f"[scheduler] post-event refresh failed: {_pe}")

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

        _neutral_sig = {"direction": "NEUTRAL", "confidence": 0.0}
        spy_signal = dict(_neutral_sig)
        qqq_signal = dict(_neutral_sig)
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
                # Phase 2C — SPX 0-1DTE options layer (paper): translate the SPY
                # directional flip into an SPX long CALL/PUT recommendation.
                # Silent mode: ledger only, no Telegram until Stage B proves edge.
                # Set OPTIONS_TELEGRAM=true in Railway to enable messages.
                try:
                    from options_engine import build_spx_recommendation, format_telegram, append_paper_trade
                    rec = await asyncio.to_thread(build_spx_recommendation, spy_dir, spy_conf)
                    if rec:
                        await asyncio.to_thread(append_paper_trade, rec)
                        if os.environ.get("OPTIONS_TELEGRAM", "false").lower() == "true":
                            from telegram_bot import send_text
                            await send_text(format_telegram(rec))
                except Exception as _opt_err:
                    print(f"[options] recommendation failed: {_opt_err}")
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

        # ── Market Intelligence alert — fires on STATE CHANGE into an elevated regime ──
        # (velocity spike / imminent event / ML flip on flow / fast acceleration).
        # Fires once per episode; re-arms only after conditions fully clear.
        global _intel_active
        try:
            intel_reasons = _evaluate_intel_triggers(
                _latest_velocity, _latest_event, signal, direction_changed
            )
            if intel_reasons and not _intel_active and not _startup_cycle:
                from telegram_bot import send_market_intelligence
                sent_intel = await send_market_intelligence(
                    intel_reasons, _latest_velocity, _latest_event,
                    signal, spy_signal, qqq_signal,
                )
                if sent_intel:
                    _intel_active = True
                    print(f"[scheduler] Market Intelligence alert sent — {len(intel_reasons)} trigger(s): {intel_reasons}")
            elif not intel_reasons and _intel_active:
                _intel_active = False
                print("[scheduler] Market Intelligence: conditions cleared — re-armed.")
        except Exception as e:
            print(f"[scheduler] Market Intelligence alert error: {e}")

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
            expected = {"news_signal_cycle", "breaking_news_cycle", "hourly_system_check", "macro_refresh_cycle", "daily_trade_count_report", "fj_session_refresh", "market_pulse"}
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
            from db import _parse_ts as _pts
            last_trade_time = _pts(hist_2m[-1].get("created_at", "2000-01-01T00:00:00"))
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
        # Holiday-aware market status (market_calendar handles NYSE + forex holidays).
        # Falls back to the weekday/hour heuristic if the calendar import fails.
        try:
            from market_calendar import is_nyse_open, is_forex_open
            gold_active   = is_forex_open(now_utc)
            stocks_active = is_nyse_open(now_utc)
        except Exception as _mc_err:
            print(f"[system_check] market_calendar unavailable ({_mc_err}) — using weekday heuristic")
            gold_active   = (dow < 5)
            stocks_active = (dow < 5 and 13 <= hour_utc < 21)

        # max_silent_hours is calibrated to each pool's REAL trade cadence (verified
        # against the live webhook log), not a flat value. Thin pools (INDEX/QQQ) and
        # all slow 4H pools trade <1×/day, so short thresholds produce daily false
        # "flow gap" alarms. Windows are sized so the alert only fires when a pool that
        # SHOULD trade daily goes dark for 1.5–3 days — the real signature of an
        # expired/broken TradingView alert. XAUUSD_1H is ultra-thin (a few trades ever)
        # so it gets a full week before alerting.
        active_pools = [
            ("data/trade_history_XAUUSD_2M.json",            "XAUUSD_2M",            gold_active,     6),
            ("data/trade_history_XAUUSD_5M.json",            "XAUUSD_5M",            gold_active,    12),
            ("data/trade_history_XAUUSD_15M.json",           "XAUUSD_15M",           gold_active,    24),
            ("data/trade_history_XAUUSD_30M.json",           "XAUUSD_30M",           gold_active,    48),
            ("data/trade_history_XAUUSD_1H.json",            "XAUUSD_1H",            gold_active,    168),
            ("data/trade_history_STOCKS_MOMENTUM_15M.json",  "STOCKS_MOMENTUM_15M",  stocks_active,    6),
            ("data/trade_history_STOCKS_MOMENTUM_30M.json",  "STOCKS_MOMENTUM_30M",  stocks_active,    8),
            ("data/trade_history_STOCKS_QUALITY_15M.json",   "STOCKS_QUALITY_15M",   stocks_active,   12),
            ("data/trade_history_STOCKS_QUALITY_30M.json",   "STOCKS_QUALITY_30M",   stocks_active,   24),
            ("data/trade_history_STOCKS_INDEX_15M.json",     "STOCKS_INDEX_15M",     stocks_active,   48),
            ("data/trade_history_STOCKS_INDEX_30M.json",     "STOCKS_INDEX_30M",     stocks_active,   48),
            ("data/trade_history_STOCKS_QQQ_15M.json",       "STOCKS_QQQ_15M",       stocks_active,   48),
            ("data/trade_history_STOCKS_QQQ_30M.json",       "STOCKS_QQQ_30M",       stocks_active,   48),
            ("data/trade_history_STOCKS_SPX500_15M.json",    "STOCKS_SPX500_15M",    stocks_active,   24),
            ("data/trade_history_STOCKS_SPX500_30M.json",    "STOCKS_SPX500_30M",    stocks_active,   24),
            # 1H pools — alert after 48h of silence
            ("data/trade_history_STOCKS_MOMENTUM_1H.json",   "STOCKS_MOMENTUM_1H",   stocks_active,   48),
            ("data/trade_history_STOCKS_QUALITY_1H.json",    "STOCKS_QUALITY_1H",    stocks_active,   48),
            ("data/trade_history_STOCKS_INDEX_1H.json",      "STOCKS_INDEX_1H",      stocks_active,   48),
            ("data/trade_history_STOCKS_QQQ_1H.json",        "STOCKS_QQQ_1H",        stocks_active,   48),
            ("data/trade_history_STOCKS_SPX500_1H.json",     "STOCKS_SPX500_1H",     stocks_active,   48),
            # 4H pools resolve trades over many hours — only alert after ~2 sessions of silence
            ("data/trade_history_STOCKS_MOMENTUM_4H.json",   "STOCKS_MOMENTUM_4H",   stocks_active,   72),
            ("data/trade_history_STOCKS_QUALITY_4H.json",    "STOCKS_QUALITY_4H",    stocks_active,   72),
            ("data/trade_history_STOCKS_INDEX_4H.json",      "STOCKS_INDEX_4H",      stocks_active,   72),
            ("data/trade_history_STOCKS_QQQ_4H.json",        "STOCKS_QQQ_4H",        stocks_active,   72),
            ("data/trade_history_STOCKS_SPX500_4H.json",     "STOCKS_SPX500_4H",     stocks_active,   72),
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
            total = _webhook_errors + _webhook_ok
            fail_pct = (_webhook_errors / total * 100) if total else 0
            critical_alerts.append((
                "Trade Persistence Errors Detected",
                f"{_webhook_errors} of {total} trade saves failed in the last hour "
                f"({fail_pct:.0f}%) — likely GitHub write conflicts on busy pools.",
                "These are background GitHub-save failures (not 422s). Check Railway logs for the persist error."
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
        for _dedup_pool in ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_15M", "XAUUSD_30M", "XAUUSD_1H",
                             "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_1H", "STOCKS_MOMENTUM_4H",
                             "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_1H",  "STOCKS_QUALITY_4H",
                             "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_1H",    "STOCKS_INDEX_4H",
                             "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_1H",      "STOCKS_QQQ_4H",
                             "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_1H",   "STOCKS_SPX500_4H"]:
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
        retrain_pools = ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_15M", "XAUUSD_30M", "XAUUSD_1H",
                         "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_1H", "STOCKS_MOMENTUM_4H",
                         "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_1H",  "STOCKS_QUALITY_4H",
                         "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_1H",    "STOCKS_INDEX_4H",
                         "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_1H",      "STOCKS_QQQ_4H",
                         "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_1H",   "STOCKS_SPX500_4H"]
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
        sync_pools = ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_15M", "XAUUSD_30M", "XAUUSD_1H",
                      "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_1H", "STOCKS_MOMENTUM_4H",
                      "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_1H",  "STOCKS_QUALITY_4H",
                      "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_1H",    "STOCKS_INDEX_4H",
                      "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_1H",      "STOCKS_QQQ_4H",
                      "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_1H",   "STOCKS_SPX500_4H"]
        for _pool in sync_pools:
            await asyncio.to_thread(resync_pool_counters, _pool)
    except Exception as e:
        print(f"[system_check] Counter resync failed: {e}")

    # ── News-feed freshness (catches a dead source like an expired FJ session) ──
    try:
        from db import _get_file
        news, _ = await asyncio.to_thread(_get_file, "data/news_cache.json")
        if isinstance(news, list) and news:
            now_utc = datetime.now(timezone.utc)
            def _age_min(items):
                ts = [i.get("fetched_at") for i in items if i.get("fetched_at")]
                if not ts:
                    return None
                newest = max(datetime.fromisoformat(str(t).replace("Z", "+00:00")) for t in ts)
                if newest.tzinfo is None:
                    newest = newest.replace(tzinfo=timezone.utc)
                return (now_utc - newest).total_seconds() / 60
            overall_age = _age_min(news)
            # Overall feed: breaking-news cycle runs every 2 min, so >60 min stale = dead pipeline
            if overall_age is not None and overall_age > 60:
                critical_alerts.append((
                    "News Feed Stale",
                    f"No news fetched for {overall_age:.0f} min — the news pipeline may be down.",
                    "Check Railway logs for the breaking-news cycle / RSS+Finnhub errors."
                ))
                issues.append(f"News feed stale ({overall_age:.0f}m) ⚠️")
            else:
                ok.append(f"News feed fresh ({overall_age:.0f}m ago) ✅" if overall_age is not None else "News feed present ✅")
            # FinancialJuice specifically — its session can lapse; flag if FJ silent >6h while feed alive
            fj = [i for i in news if "juice" in str(i.get("source", "")).lower()]
            fj_age = _age_min(fj)
            if (fj_age is None or fj_age > 360) and overall_age is not None and overall_age < 60:
                critical_alerts.append((
                    "FinancialJuice Feed Silent",
                    f"FJ has no fresh items ({'none in cache' if fj_age is None else f'{fj_age:.0f} min old'}) "
                    f"while other sources are live — FJ session likely lapsed.",
                    "Auto-relogin should recover it; if not, check FJ_EMAIL/FJ_PASSWORD in Railway."
                ))
                issues.append("FJ feed silent ⚠️")
            elif fj_age is not None:
                ok.append(f"FJ feed fresh ({fj_age:.0f}m ago) ✅")
    except Exception as e:
        print(f"[system_check] News freshness check failed: {e}")

    # ── Daily levels staleness (GitHub Action writes pivots ~07:50 UTC Mon-Fri) ──
    try:
        from db import _get_file
        levels, _ = await asyncio.to_thread(_get_file, "data/daily_levels.json")
        if isinstance(levels, dict) and levels.get("fetched_at"):
            now_utc = datetime.now(timezone.utc)
            lvl_ts = datetime.fromisoformat(str(levels["fetched_at"]).replace("Z", "+00:00"))
            if lvl_ts.tzinfo is None:
                lvl_ts = lvl_ts.replace(tzinfo=timezone.utc)
            lvl_age_h = (now_utc - lvl_ts).total_seconds() / 3600
            # Refreshed every weekday; >30h means the GitHub Action failed (signals use stale pivots)
            if now_utc.weekday() < 5 and lvl_age_h > 30:
                critical_alerts.append((
                    "Daily Levels Stale",
                    f"daily_levels.json is {lvl_age_h:.0f}h old — the pivot-fetch GitHub Action may have failed.",
                    "Signals are using stale pivot levels. Check the fetch_daily_levels workflow run."
                ))
                issues.append(f"Daily levels stale ({lvl_age_h:.0f}h) ⚠️")
            else:
                ok.append(f"Daily levels fresh ({lvl_age_h:.0f}h ago) ✅")
    except Exception as e:
        print(f"[system_check] Daily levels staleness check failed: {e}")

    n_issue = len(issues)
    print(f"[system_check] {len(ok)}/{len(ok)+n_issue} checks passed.")
    for iss in issues:
        print(f"[system_check] ISSUE: {iss}")
    for title, detail, action in critical_alerts:
        print(f"[system_check] CRITICAL: {title} — {detail}")
        await send_critical_alert(title, detail, action)


async def _daily_trade_count_report() -> None:
    """
    RULE: One daily performance report, fired once after NY session closes (16:15 ET).
    Consolidated across all pools — XAUUSD + all stocks.
    No other daily brief fires; this is the only end-of-day message.
    """
    from datetime import datetime, timezone, date
    if datetime.now(timezone.utc).weekday() >= 5:
        return
    try:
        from db import _get_file, repair_missing_trades
        from telegram_bot import send_text

        # Recover any trades that arrived but failed to save (SHA conflicts etc.)
        repaired = await asyncio.to_thread(repair_missing_trades)
        if repaired:
            print(f"[daily_report] Pre-report repair: {len(repaired)} trades recovered.")

        today = date.today().isoformat()
        all_paths = [
            "data/trade_history.json",          # legacy XAUUSD pool (pre-timeframe era)
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

        def _realized_pct(t: dict) -> float | None:
            """Signed realized move as % (favorable = positive), or None if no prices."""
            try:
                e = float(t.get("entry_price")); x = float(t.get("exit_price"))
            except (TypeError, ValueError):
                return None
            if not e:
                return None
            raw = (x - e) / e * 100
            return raw if t.get("direction") == "LONG" else -raw

        def _stats(trades: list[dict]) -> tuple[int, int, int, int]:
            """Return (total, tp_wins, sl_hits, partials)."""
            tp  = sum(1 for t in trades if t.get("outcome") == "WIN")
            sl  = sum(1 for t in trades if t.get("outcome") == "LOSS")
            par = sum(1 for t in trades if t.get("outcome") == "PARTIAL")
            return len(trades), tp, sl, par

        def _wr_line(total: int, tp: int, sl: int, par: int, trades: list[dict] | None = None) -> str:
            # "Reached TP1+" = hit at least the first target (TP win or any partial).
            # This is the honest hit-rate; the headline WIN count only counts full TP3.
            reached_tp1 = tp + par
            hit_rate = reached_tp1 / total * 100 if total else 0.0
            line = (
                f"Signals: <b>{total}</b>  |  "
                f"✅ TP: {tp}  🔶 Partial: {par}  ❌ SL: {sl}\n"
                f"Reached TP1+: <b>{hit_rate:.0f}%</b>"
            )
            # Net-positive rate + expectancy from realized price (catches SL_TP1 partials
            # that actually closed red on the fast gold scalps).
            if trades:
                moves = [m for m in (_realized_pct(t) for t in trades) if m is not None]
                if moves:
                    net_pos = sum(1 for m in moves if m > 0) / len(moves) * 100
                    expectancy = sum(moves) / len(moves)
                    line += (
                        f"\nNet positive: <b>{net_pos:.0f}%</b>  |  "
                        f"Expectancy: <b>{expectancy:+.2f}%</b>/trade"
                    )
            return line

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
            lines.append(_wr_line(tot, tp, sl, par, today_all))

            if gold_trades:
                g_tot, g_tp, g_sl, g_par = _stats(gold_trades)
                lines.append(f"\n🥇 <b>XAUUSD</b> ({g_tot} trades)")
                lines.append(_wr_line(g_tot, g_tp, g_sl, g_par, gold_trades))

            if spy_trades:
                s_tot, s_tp, s_sl, s_par = _stats(spy_trades)
                lines.append(f"\n📊 <b>SPY</b> ({s_tot} trades)")
                lines.append(_wr_line(s_tot, s_tp, s_sl, s_par, spy_trades))

            if qqq_trades:
                q_tot, q_tp, q_sl, q_par = _stats(qqq_trades)
                lines.append(f"\n📊 <b>QQQ</b> ({q_tot} trades)")
                lines.append(_wr_line(q_tot, q_tp, q_sl, q_par, qqq_trades))

            if other_trades:
                o_tot, o_tp, o_sl, o_par = _stats(other_trades)
                lines.append(f"\n📈 <b>Stocks</b> ({o_tot} trades)")
                lines.append(_wr_line(o_tot, o_tp, o_sl, o_par, other_trades))

        msg = (
            f"📊 <b>DAILY PERFORMANCE REPORT — {date_str}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            + "\n".join(lines) +
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ {now_utc.strftime('%H:%M UTC')}"
        )
        await send_text(msg)
        print(f"[daily_report] Performance report sent — {tot} trades today, TP={tp} SL={sl} P={par}.")
    except Exception as e:
        print(f"[daily_report] Error: {e}")


async def _weekly_mistake_autopsy() -> None:
    """Every Monday 09:00 UTC — summarise top bleeding patterns from the mistake ledger."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if now.weekday() != 0:   # Monday only (safety guard)
        return
    print("[autopsy] Running weekly mistake autopsy…")
    try:
        from db import get_mistake_summary, recent_outcomes, symbol_to_pool
        summary = await asyncio.to_thread(get_mistake_summary, "", 100)
        if not summary or not summary.get("top_patterns"):
            return
        lines = ["🔬 *Weekly Mistake Autopsy*\n"]
        lines.append("Last 100 losses analysed:\n")
        for pat in summary["top_patterns"][:8]:
            lines.append(f"  • `{pat['tag']}` — {pat['count']} losses")
        lines.append(f"\nTotal mistakes logged: {summary['total_mistakes']}")

        # Add SHAP attribution from best-populated pool
        try:
            from ml_ensemble import get_gbm, explain_prediction, GOLD_TF_IDS
            from ml_model import FEATURE_NAMES
            best_pool = "XAUUSD_2M"
            hist = await asyncio.to_thread(recent_outcomes, best_pool, 500)
            _losses = [r for r in hist if r.get("outcome") == "LOSS"][:20]
            if _losses and get_gbm(best_pool).is_trained:
                from ml_model import row_to_vector
                shap_counts: dict[str, float] = {}
                for _r in _losses:
                    _fv = row_to_vector(_r)
                    _drivers = explain_prediction(get_gbm(best_pool)._model, _fv, FEATURE_NAMES, top_n=3)
                    for _name, _val in _drivers:
                        shap_counts[_name] = shap_counts.get(_name, 0) + abs(_val)
                if shap_counts:
                    top3 = sorted(shap_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                    lines.append(f"\n🔍 *SHAP — top drivers in losses ({best_pool}):*")
                    for fname, score in top3:
                        lines.append(f"  • `{fname}` (cumul. |SHAP|={score:.3f})")
        except Exception as _se:
            print(f"[autopsy] SHAP section failed: {_se}")

        from telegram_bot import send_text
        await send_text("\n".join(lines))
        print("[autopsy] Weekly autopsy sent.")
    except Exception as e:
        print(f"[autopsy] Error: {e}")


async def _weekly_model_comparison() -> None:
    """
    Every Sunday 20:00 UTC — walk-forward backtest all models on the last 100 trades
    per pool and log which model (RF/GBM/joint) has the best OOS F1. Auto-promotes
    the gate threshold if the winner beats the current model by >3pp.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if now.weekday() != 6:   # Sunday only
        return
    print("[model_compare] Running weekly model comparison…")
    try:
        import numpy as _np
        from sklearn.metrics import f1_score as _f1
        from sklearn.model_selection import TimeSeriesSplit
        from db import recent_outcomes
        from ml_model import row_to_vector, FEATURE_NAMES
        from ml_ensemble import get_rf, get_gbm, get_joint_gold, get_joint_stocks, GOLD_TF_IDS, STOCK_POOL_IDS

        results: list[str] = ["📊 *Weekly Model Comparison*\n"]
        all_pools = list(GOLD_TF_IDS.keys()) + list(STOCK_POOL_IDS.keys())

        for pool in all_pools:
            hist = await asyncio.to_thread(recent_outcomes, pool, 200)
            if len(hist) < 40:
                continue
            X = _np.array([row_to_vector(r) for r in hist], dtype=_np.float32)
            y = _np.array([1 if r.get("outcome") in ("WIN","PARTIAL") else 0 for r in hist])

            tscv = TimeSeriesSplit(n_splits=3, gap=5)
            model_scores: dict[str, list[float]] = {"rf": [], "gbm": [], "joint": []}

            for tr, val in tscv.split(X):
                if len(tr) < 15 or len(set(y[tr].tolist())) < 2:
                    continue
                from signal_engine import _pool_thresholds, ML_GATE_THRESHOLD
                _thresh = _pool_thresholds.get(pool, ML_GATE_THRESHOLD)
                for name, m in [("rf", get_rf(pool)), ("gbm", get_gbm(pool))]:
                    if not m.is_trained:
                        continue
                    try:
                        preds = [(m.predict(X[i].tolist()) >= _thresh) for i in val]
                        model_scores[name].append(_f1(y[val], preds, zero_division=0))
                    except Exception:
                        pass
                jm = get_joint_gold() if pool in GOLD_TF_IDS else get_joint_stocks()
                if jm.is_trained:
                    try:
                        preds = [(jm.predict(X[i].tolist(), pool) >= _thresh) for i in val]
                        model_scores["joint"].append(_f1(y[val], preds, zero_division=0))
                    except Exception:
                        pass

            avgs = {k: round(float(_np.mean(v)), 3) for k, v in model_scores.items() if v}
            if avgs:
                winner = max(avgs, key=avgs.get)
                results.append(f"  `{pool}`: winner=*{winner}* "
                                + " ".join(f"{k}={v:.2f}" for k, v in sorted(avgs.items())))

        if len(results) > 1:
            from telegram_bot import send_text
            await send_text("\n".join(results))
            print("[model_compare] Weekly comparison sent.")
    except Exception as e:
        print(f"[model_compare] Error: {e}")


async def _test_personal_alert() -> None:
    from telegram_bot import send_critical_alert
    await send_critical_alert(
        "System Monitor Test",
        "Personal alerts are working correctly. You will receive warnings here for: Railway hours, GitHub token expiry, and webhook silence.",
        "No action needed — this is a test."
    )


async def _macro_refresh_cycle() -> None:
    """Refresh gold macro drivers (FRED real yields/dollar, CFTC COT, GLD flows) hourly,
    plus the probabilistic HMM regime state for XAUUSD/SPY/QQQ (Phase 2A)."""
    try:
        from market_macro import refresh_macro_bias
        await asyncio.to_thread(refresh_macro_bias)
    except Exception as e:
        print(f"[scheduler] macro refresh failed: {e}")
    try:
        from regime_model import refresh_regimes
        await asyncio.to_thread(refresh_regimes)
    except Exception as e:
        print(f"[scheduler] regime refresh failed: {e}")
    try:
        from mtf_confluence import refresh_mtf
        await asyncio.to_thread(refresh_mtf)
    except Exception as e:
        print(f"[scheduler] MTF refresh failed: {e}")


async def _fj_session_refresh_cycle() -> None:
    """
    Proactively renew the FinancialJuice login session on a timer so the cookie
    never lapses. The breaking-news path already re-logins reactively on 401/403
    or non-JSON 200, but this keeps the session fresh ahead of expiry so the FJ
    feed never silently goes quiet. No-op if FJ_EMAIL/FJ_PASSWORD are unset.
    """
    try:
        from news_fetcher import _fj_auto_login, FJ_EMAIL, FJ_PASSWORD
        if not (FJ_EMAIL and FJ_PASSWORD):
            return  # credentials not configured — nothing to refresh
        ok = await asyncio.to_thread(_fj_auto_login)
        print(f"[scheduler] FJ session refresh: {'success' if ok else 'failed'}")
    except Exception as e:
        print(f"[scheduler] FJ session refresh error: {e}")


async def _market_pulse_cycle() -> None:
    """
    Periodic market-direction summary to Telegram (London open / NY open / NY close).
    Sends current bias for XAUUSD/SPY/QQQ + regime + macro, regardless of flips.
    """
    try:
        from signal_engine import generate_signal, get_latest_features
        from market_macro import get_macro_bias, get_equity_macro_bias
        from telegram_bot import send_market_pulse

        _gold_macro   = get_macro_bias()
        _equity_macro = get_equity_macro_bias()

        gold = await asyncio.to_thread(
            generate_signal,
            current_features=get_latest_features("XAUUSD_2M"),
            news_agg=_latest_news_agg, news_velocity=_latest_velocity,
            high_impact_event=_latest_event, symbol="XAUUSD",
            pool="XAUUSD_2M", macro_bias=_gold_macro,
        )
        spy = await asyncio.to_thread(
            generate_signal,
            current_features=get_latest_features("STOCKS_INDEX_30M"),
            news_agg=_latest_news_agg, news_velocity=_latest_velocity,
            high_impact_event=_latest_event, symbol="SPY",
            pool="STOCKS_INDEX_30M", macro_bias=_equity_macro,
        )
        qqq = await asyncio.to_thread(
            generate_signal,
            current_features=get_latest_features("STOCKS_QQQ_30M"),
            news_agg=_latest_news_agg, news_velocity=_latest_velocity,
            high_impact_event=_latest_event, symbol="QQQ",
            pool="STOCKS_QQQ_30M", macro_bias=_equity_macro,
        )
        await send_market_pulse(gold, spy, qqq, _gold_macro)
        print(f"[pulse] Market pulse sent — XAU={gold['direction']} SPY={spy['direction']} QQQ={qqq['direction']}")
    except Exception as e:
        print(f"[pulse] Market pulse error: {e}")


async def _full_system_inspection():
    """
    Deep system inspection — runs every 6 hours per system_directive.FULL_INSPECTION_HOURS.
    Tests every component, auto-fixes issues, logs a structured health report.
    Protocol: detect → test → fix → verify → report. Never fixes blindly.
    """
    from datetime import datetime, timezone
    from system_directive import (MIN_TRADES_FOR_ML, REGIME_SHIFT_WINDOW,
                                   REGIME_SHIFT_DROP_PP, get_directive_summary)
    started_at = datetime.now(timezone.utc)
    print(f"[inspection] ═══ Full system inspection started at {started_at.strftime('%H:%M UTC')} ═══")

    report: dict = {
        "started_at":   started_at.isoformat(),
        "checks":       [],
        "fixes_applied": [],
        "warnings":     [],
        "errors":       [],
    }

    def _ok(msg: str):
        report["checks"].append(f"✅ {msg}")
        print(f"[inspection] ✅ {msg}")

    def _warn(msg: str):
        report["warnings"].append(f"⚠️ {msg}")
        print(f"[inspection] ⚠️  {msg}")

    def _err(msg: str):
        report["errors"].append(f"❌ {msg}")
        print(f"[inspection] ❌ {msg}")

    def _fix(msg: str):
        report["fixes_applied"].append(f"🔧 {msg}")
        print(f"[inspection] 🔧 {msg}")

    ALL_POOLS = [
        "XAUUSD_2M", "XAUUSD_5M", "XAUUSD_30M", "XAUUSD_1H",
        "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_4H",
        "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_4H",
        "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H",
        "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_4H",
        "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_4H",
    ]

    # ── 1. Import health: verify all core modules load without error ──────────
    core_modules = ["ml_model", "ml_ensemble", "signal_engine", "db",
                    "market_macro", "news_fetcher", "telegram_bot"]
    for mod in core_modules:
        try:
            __import__(mod)
            _ok(f"Module {mod} imports cleanly")
        except Exception as exc:
            _err(f"Module {mod} import failed: {exc}")

    # ── 2. Optional deps availability ─────────────────────────────────────────
    try:
        from ml_ensemble import _LGBM_AVAILABLE, _OPTUNA_AVAILABLE, _SHAP_AVAILABLE, _SKLEARN_AVAILABLE
        if _SKLEARN_AVAILABLE: _ok("scikit-learn available")
        else:                   _err("scikit-learn NOT available — RF/GBM disabled")
        if _LGBM_AVAILABLE:     _ok("LightGBM available — joint models active")
        else:                   _warn("LightGBM not available — joint models using sklearn fallback")
        if _OPTUNA_AVAILABLE:   _ok("Optuna available — Bayesian HPO active")
        else:                   _warn("Optuna not available — HPO disabled (fixed hyperparams)")
        if _SHAP_AVAILABLE:     _ok("SHAP available — loss attribution active")
        else:                   _warn("SHAP not available — loss autopsy uses feature importance fallback")
    except Exception as exc:
        _err(f"Dep check failed: {exc}")

    # ── 3. Pool data integrity ─────────────────────────────────────────────────
    from db import recent_outcomes, resync_pool_counters
    pool_sizes: dict[str, int] = {}
    for pool in ALL_POOLS:
        try:
            hist = await asyncio.to_thread(recent_outcomes, pool, 500)
            n = len(hist)
            pool_sizes[pool] = n
            if n == 0:
                _warn(f"{pool}: 0 trades — pool empty")
            elif n < MIN_TRADES_FOR_ML:
                _warn(f"{pool}: {n} trades (need {MIN_TRADES_FOR_ML} for ML)")
            else:
                _ok(f"{pool}: {n} trades")

            # Detect corrupted records (missing required fields)
            if hist:
                bad = [i for i, r in enumerate(hist[:20])
                       if not r.get("outcome") or not r.get("direction")]
                if bad:
                    _warn(f"{pool}: {len(bad)} corrupted records in last 20 (missing outcome/direction)")
        except Exception as exc:
            _err(f"{pool} data read failed: {exc}")

    # ── 4. Model training status ───────────────────────────────────────────────
    from ml_ensemble import get_rf, get_gbm
    for pool in ALL_POOLS:
        n = pool_sizes.get(pool, 0)
        if n < MIN_TRADES_FOR_ML:
            continue
        try:
            rf  = get_rf(pool)
            gbm = get_gbm(pool)
            if not rf.is_trained:
                _warn(f"{pool}: RF not trained despite n={n} — attempting retrain")
                hist = await asyncio.to_thread(recent_outcomes, pool, 500)
                ok_rf = await asyncio.to_thread(rf.retrain, hist)
                if ok_rf: _fix(f"{pool}: RF retrained on {n} trades")
                else:     _err(f"{pool}: RF retrain failed")
            else:
                _ok(f"{pool}: RF trained")
            if not gbm.is_trained:
                _warn(f"{pool}: GBM not trained despite n={n} — attempting retrain")
                hist = await asyncio.to_thread(recent_outcomes, pool, 500)
                ok_gbm = await asyncio.to_thread(gbm.train, hist)
                if ok_gbm: _fix(f"{pool}: GBM retrained on {n} trades")
                else:       _err(f"{pool}: GBM retrain failed")
            else:
                _ok(f"{pool}: GBM trained")
        except Exception as exc:
            _err(f"{pool} model check failed: {exc}")

    # ── 5. Win-rate sanity check — detect regime shifts ───────────────────────
    for pool in ALL_POOLS:
        n = pool_sizes.get(pool, 0)
        if n < REGIME_SHIFT_WINDOW * 2:
            continue
        try:
            hist = await asyncio.to_thread(recent_outcomes, pool, 500)
            wins_recent = sum(1 for r in hist[:REGIME_SHIFT_WINDOW]
                              if r.get("outcome") in ("WIN", "PARTIAL"))
            wins_prior  = sum(1 for r in hist[REGIME_SHIFT_WINDOW:REGIME_SHIFT_WINDOW*2]
                              if r.get("outcome") in ("WIN", "PARTIAL"))
            wr_recent = wins_recent / REGIME_SHIFT_WINDOW * 100
            wr_prior  = wins_prior  / REGIME_SHIFT_WINDOW * 100
            drop = wr_prior - wr_recent
            if drop > REGIME_SHIFT_DROP_PP:
                _warn(f"{pool}: regime shift detected — WR dropped {drop:.1f}pp "
                      f"({wr_prior:.0f}%→{wr_recent:.0f}%) in last {REGIME_SHIFT_WINDOW} trades")
            else:
                _ok(f"{pool}: WR stable ({wr_recent:.0f}% recent vs {wr_prior:.0f}% prior)")
        except Exception as exc:
            _warn(f"{pool} WR check failed: {exc}")

    # ── 6. Feature cache freshness ─────────────────────────────────────────────
    try:
        from signal_engine import _latest_features
        cached_pools = [p for p, f in _latest_features.items() if f is not None]
        if len(cached_pools) >= 3:
            _ok(f"Feature cache: {len(cached_pools)} pools have live features")
        else:
            _warn(f"Feature cache thin: only {len(cached_pools)} pools cached — "
                  f"heartbeats may not be arriving")
    except Exception as exc:
        _warn(f"Feature cache check failed: {exc}")

    # ── 7. Data branch write test ──────────────────────────────────────────────
    try:
        from db import _get_file, _put_file
        d, sha = await asyncio.to_thread(_get_file, "data/health.json")
        if not isinstance(d, dict):
            d = {}
        d["last_inspection"] = started_at.isoformat()
        d["inspection_checks"] = len(report["checks"])
        d["inspection_fixes"]  = len(report["fixes_applied"])
        d["inspection_warnings"] = len(report["warnings"])
        await asyncio.to_thread(_put_file, "data/health.json", d, sha,
                                "chore: inspection health update")
        _ok("Data branch writable")
    except Exception as exc:
        _err(f"Data branch write failed: {exc}")

    # ── 8. Scheduler jobs alive check ─────────────────────────────────────────
    try:
        if _scheduler and _scheduler.running:
            job_ids = {j.id for j in _scheduler.get_jobs()}
            required = {"news_signal_cycle", "breaking_news_cycle",
                        "hourly_system_check", "macro_refresh_cycle",
                        "full_system_inspection"}
            missing = required - job_ids
            if missing:
                _warn(f"Scheduler jobs missing: {missing}")
            else:
                _ok(f"All {len(required)} required scheduler jobs alive")
        else:
            _err("Scheduler is not running!")
    except Exception as exc:
        _warn(f"Scheduler job check failed: {exc}")

    # ── 9. Counter resync ─────────────────────────────────────────────────────
    try:
        for pool in ALL_POOLS:
            await asyncio.to_thread(resync_pool_counters, pool)
        _fix("Win/loss counters resynced for all pools")
    except Exception as exc:
        _warn(f"Counter resync failed: {exc}")

    # ── Summary ────────────────────────────────────────────────────────────────
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    n_ok    = len(report["checks"])
    n_warn  = len(report["warnings"])
    n_err   = len(report["errors"])
    n_fix   = len(report["fixes_applied"])

    summary = (f"[inspection] ═══ Complete in {elapsed:.0f}s — "
               f"✅{n_ok} ok  ⚠️{n_warn} warn  ❌{n_err} err  🔧{n_fix} fixed ═══")
    print(summary)

    # Send Telegram alert only if there are errors or fixes were applied
    if n_err > 0 or n_fix > 0:
        from telegram_bot import send_critical_alert as _send_crit
        lines = []
        if report["fixes_applied"]: lines += report["fixes_applied"][:5]
        if report["errors"]:        lines += report["errors"][:5]
        if report["warnings"][:3]:  lines += report["warnings"][:3]
        body  = "\n".join(lines)
        await _send_crit(
            f"System Inspection: {n_fix} fix(es), {n_err} error(s)",
            body,
            f"Full report: {n_ok} ok / {n_warn} warn / {n_err} err / {n_fix} fixed in {elapsed:.0f}s",
        )

    report["elapsed_seconds"] = round(elapsed, 1)
    report["summary"] = f"{n_ok} ok / {n_warn} warn / {n_err} err / {n_fix} fixed"
    return report


async def _options_iv_record_cycle() -> None:
    """Daily SPX ATM IV snapshot — builds the 60-session IV Rank history."""
    try:
        from options_engine import record_daily_iv
        await asyncio.to_thread(record_daily_iv)
    except Exception as e:
        print(f"[options] IV record cycle failed: {e}")


async def _options_paper_manage_cycle() -> None:
    """Hourly during RTH: enforce TP/SL/time exits on open paper option trades.
    Silent mode: closes logged to console/ledger only unless OPTIONS_TELEGRAM=true."""
    try:
        from options_engine import manage_paper_positions
        closed = await asyncio.to_thread(manage_paper_positions)
        tg_on = os.environ.get("OPTIONS_TELEGRAM", "false").lower() == "true"
        for line in closed:
            print(f"[options] paper closed: {line}")
            if tg_on:
                from telegram_bot import send_text
                await send_text(f"📄 <b>SPX PAPER CLOSED</b>\n{line}")
    except Exception as e:
        print(f"[options] paper manage cycle failed: {e}")


async def _market_open_data_check() -> None:
    """
    Shortly after the US market opens (holiday-aware), force a fresh fetch of the
    Phase 2 context layers during LIVE hours and verify all three assets actually
    got real data. Weekend/holiday data can mask a yfinance drop; this validates
    the layers when the market is genuinely open. Alerts the personal chat only
    when something looks wrong (healthy = console only, no noise).
    """
    try:
        from market_calendar import is_nyse_open
        if not is_nyse_open():
            print("[data_check] NYSE closed (holiday) — skipping market-open data check")
            return

        # Force a fresh fetch now that markets are live.
        try:
            from regime_model import refresh_regimes, REGIME_ASSETS, get_regime
            from mtf_confluence import refresh_mtf, get_mtf
            await asyncio.to_thread(refresh_regimes)
            await asyncio.to_thread(refresh_mtf)
        except Exception as _re:
            print(f"[data_check] refresh failed: {_re}")
            return

        problems: list[str] = []
        lines: list[str] = []
        for a in REGIME_ASSETS:
            reg = get_regime(a)
            mtf = get_mtf(a)
            votes = mtf.get("votes", {})
            reg_ok = reg.get("method") in ("hmm", "heuristic")
            mtf_ok = any(votes.get(k, 0) != 0 for k in ("h1", "h4", "d1")) or mtf.get("bias") not in (None, "NEUTRAL")
            tag = "✅" if (reg_ok and mtf_ok) else "⚠️"
            if not reg_ok:
                problems.append(f"{a} regime={reg.get('method','?')}")
            if not mtf_ok:
                problems.append(f"{a} MTF empty/flat")
            lines.append(f"{tag} {a}: regime {reg.get('regime','?')}({reg.get('method','?')}) · "
                         f"MTF {mtf.get('bias','?')} {votes}")

        status = "healthy ✅" if not problems else "issues ⚠️ — " + ", ".join(problems)
        print(f"[data_check] market-open data layers: {status}\n  " + "\n  ".join(lines))

        if problems:
            from telegram_bot import send_critical_alert
            await send_critical_alert(
                "Data Layer Check (market open)",
                "\n".join(lines),
                "yfinance likely dropped during the open burst — Stooq/Alpha Vantage "
                "fallback should cover. Investigate if this persists across days.",
            )
    except Exception as e:
        print(f"[data_check] market-open data check failed: {e}")


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
    # ONE daily performance report — fires at 16:15 ET (after NY session close).
    # DST-safe via America/New_York so it always fires 15 min after market close.
    from zoneinfo import ZoneInfo
    _ny_tz = ZoneInfo("America/New_York")
    _scheduler.add_job(_daily_trade_count_report, trigger="cron", hour=16, minute=15, timezone=_ny_tz, id="daily_trade_count_report", replace_existing=True, misfire_grace_time=3600)
    # Proactively renew the FinancialJuice session twice daily so the cookie never lapses.
    _scheduler.add_job(_fj_session_refresh_cycle, trigger="cron", hour="5,17", minute=30, id="fj_session_refresh", replace_existing=True, misfire_grace_time=3600)
    # Market pulse — direction summary at London open (10:00), NY open (14:00), NY close (20:00) UTC.
    _scheduler.add_job(_market_pulse_cycle, trigger="cron", hour="10,14,20", minute=0, id="market_pulse", replace_existing=True, misfire_grace_time=600)
    # Phase 2 data-layer health check — 30 min after NYSE open (10:00 ET, DST-safe),
    # verifies the context layers fetched live data; holiday-aware (skips when closed).
    _scheduler.add_job(_market_open_data_check, trigger="cron", day_of_week="mon-fri", hour=10, minute=0,
                       timezone=_ny_tz, id="market_open_data_check", replace_existing=True, misfire_grace_time=1800)
    # Weekly mistake autopsy — every Monday 09:00 UTC
    _scheduler.add_job(_weekly_mistake_autopsy, trigger="cron", day_of_week="mon", hour=9, minute=0, id="weekly_autopsy", replace_existing=True, misfire_grace_time=3600)
    # Weekly model comparison — every Sunday 20:00 UTC
    _scheduler.add_job(_weekly_model_comparison, trigger="cron", day_of_week="sun", hour=20, minute=0, id="weekly_model_compare", replace_existing=True, misfire_grace_time=3600)
    # Phase 2C — SPX options: record ATM IV once per session (15:45 ET, after the
    # bulk of the day's IV is realized) + manage open paper positions hourly.
    _scheduler.add_job(_options_iv_record_cycle, trigger="cron", day_of_week="mon-fri", hour=15, minute=45,
                       timezone=_ny_tz, id="options_iv_record", replace_existing=True, misfire_grace_time=3600)
    _scheduler.add_job(_options_paper_manage_cycle, trigger="cron", day_of_week="mon-fri", hour="10-16", minute=5,
                       timezone=_ny_tz, id="options_paper_manage", replace_existing=True, misfire_grace_time=600)
    # Full system inspection — every 6 hours (system_directive.FULL_INSPECTION_HOURS)
    from system_directive import FULL_INSPECTION_HOURS
    _scheduler.add_job(_full_system_inspection, trigger="interval", hours=FULL_INSPECTION_HOURS,
                       id="full_system_inspection", replace_existing=True, misfire_grace_time=3600,
                       start_date=_dt.now(_tz.utc) + _td(minutes=10))
    _scheduler.start()

    _now = _dt.now(_tz.utc)

    # Startup: refresh the FJ session shortly after boot so every deploy starts
    # with a fresh login cookie instead of waiting for the next cron window.
    _scheduler.add_job(_fj_session_refresh_cycle, trigger="date", run_date=_now + _td(seconds=60),
                       id="fj_session_refresh_boot", replace_existing=True)

    # Startup catch-up: fire daily performance report if we missed the 16:15 ET cron
    # (e.g. redeployed after NY close). Uses NY time so it tracks DST automatically.
    _now_ny = _now.astimezone(_ny_tz)
    if _now_ny.weekday() < 5 and (_now_ny.hour, _now_ny.minute) >= (16, 15):
        print("[scheduler] Startup catch-up: firing daily performance report on boot.")
        _scheduler.add_job(_daily_trade_count_report, trigger="date", run_date=_now + _td(seconds=45),
                           id="daily_report_catchup", replace_existing=True)

    print(f"[scheduler] Started — signal every {interval} min, breaking news every 2 min, system check every 60 min, daily performance report at 16:15 ET.")
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        print("[scheduler] Stopped.")
