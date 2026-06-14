"""
Phase 2D (completion) — Post-event volatility scoring.

The economic calendar (news_fetcher.fetch_upcoming_events) already de-risks
BEFORE high-impact prints. This closes the loop AFTER the print: once NFP/CPI/
FOMC has released, classify the asset's own reaction so signal_engine can
"fade the spike or follow the breakout" instead of trading blind into chaos.

Phases (per asset, from its 5-minute price reaction):
  • SETTLING  — first ~15 min after the print: maximal whipsaw → de-risk hard.
  • BREAKOUT  — the post-print move has held → trend established, follow it.
  • FADE      — the spike has reverted toward the pre-print level → fade risk.

Cheap-first: only fetches price bars when the calendar shows a high-impact US
event actually fired in the last ~2 hours. Refreshed by the news cycle and
cached in memory; signal_engine reads the cache. Graceful no-op on any failure.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

# Reuse the calendar credentials/endpoint + asset mapping already in the system.
from news_fetcher import FINNHUB_KEY, _FINNHUB_CALENDAR_URL

POST_EVENT_ASSETS = {
    "XAUUSD": "GC=F",
    "SPY":    "SPY",
    "QQQ":    "QQQ",
}

_HIGH_IMPACT = {
    "non-farm": "NFP", "nonfarm": "NFP", "payroll": "NFP",
    "cpi": "CPI", "consumer price": "CPI",
    "fomc": "FOMC", "fed interest rate": "FOMC", "interest rate decision": "FOMC",
    "federal funds": "FOMC", "pce": "PCE", "powell": "FED_SPEAK",
}

_LOOKBACK_MIN = 120     # how far back a print still counts as "post-event"
_SETTLE_MIN   = 15      # initial whipsaw window


def _recent_fired_event() -> dict | None:
    """Most recent high-impact US event that printed within the last 2 hours."""
    if not FINNHUB_KEY:
        return None
    now = datetime.now(timezone.utc)
    try:
        with httpx.Client(timeout=12) as client:
            resp = client.get(_FINNHUB_CALENDAR_URL, params={
                "from": (now - timedelta(days=1)).date().isoformat(),
                "to":   now.date().isoformat(),
                "token": FINNHUB_KEY,
            })
            resp.raise_for_status()
            events = resp.json().get("economicCalendar", []) or []
    except Exception as e:
        if "403" not in str(e):
            print(f"[post_event] calendar fetch failed: {e}")
        return None

    best = None
    for ev in events:
        if (ev.get("country") or "").upper() not in ("US", "USA"):
            continue
        name = (ev.get("event") or "").lower()
        impact = (ev.get("impact") or "").lower()
        etype = next((v for k, v in _HIGH_IMPACT.items() if k in name), None)
        if etype is None and impact != "high":
            continue
        try:
            ts = datetime.fromisoformat((ev.get("time") or "").replace(" ", "T"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        mins_since = (now - ts).total_seconds() / 60.0
        if 0 <= mins_since <= _LOOKBACK_MIN:
            cand = {"event_type": etype or "HIGH", "fired_at": ts,
                    "minutes_since": int(mins_since)}
            if best is None or cand["minutes_since"] < best["minutes_since"]:
                best = cand
    return best


def _reaction(ticker: str, fired_at: datetime) -> dict | None:
    """Measure the asset's 5-minute price reaction since the print."""
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period="1d", interval="5m")
        if not len(df):
            return None
        idx = df.index
        closes = df["Close"].astype(float)
        # Baseline = last close at or before the event; else the earliest bar.
        before = closes[idx <= fired_at]
        baseline = float(before.iloc[-1]) if len(before) else float(closes.iloc[0])
        after = closes[idx > fired_at]
        if not len(after):
            return None
        current = float(after.iloc[-1])
        hi = float(after.max())
        lo = float(after.min())
        # Extreme excursion from baseline (signed by which side moved more)
        up_move = hi - baseline
        dn_move = baseline - lo
        if up_move >= dn_move:
            extreme, move_dir = up_move, 1
        else:
            extreme, move_dir = dn_move, -1
        held = (current - baseline) * move_dir   # how much of the move is retained
        retention = held / extreme if extreme > 1e-9 else 0.0
        return {"baseline": baseline, "current": current,
                "extreme": round(extreme, 4), "move_dir": move_dir,
                "retention": round(retention, 3)}
    except Exception as e:
        print(f"[post_event] reaction fetch failed for {ticker}: {e}")
        return None


def compute_post_event(asset_key: str, fired: dict) -> dict:
    """Classify the post-event phase for one asset given a fired event."""
    ticker = POST_EVENT_ASSETS.get(asset_key, asset_key)
    mins = fired["minutes_since"]
    base = {"active": True, "asset": asset_key, "event_type": fired["event_type"],
            "minutes_since": mins, "updated_at": _now()}

    if mins < _SETTLE_MIN:
        base.update({"phase": "SETTLING", "move_dir": 0, "size_factor": 0.70})
        return base

    react = _reaction(ticker, fired["fired_at"])
    if react is None:
        # Past the settle window but no clean read — mild caution.
        base.update({"phase": "SETTLING", "move_dir": 0, "size_factor": 0.85})
        return base

    if react["retention"] >= 0.5:
        phase, sf = "BREAKOUT", 1.0
    else:
        phase, sf = "FADE", 0.85
    base.update({"phase": phase, "move_dir": react["move_dir"],
                 "size_factor": sf, "retention": react["retention"]})
    return base


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Cache + refresh ───────────────────────────────────────────────────────────

_cached_post_event: dict = {}   # asset_key → state (only while an event is live)


def get_post_event(asset_key: str) -> dict:
    return _cached_post_event.get(asset_key, {"active": False})


def get_post_event_for_pool(pool: str) -> dict:
    if pool.startswith("XAUUSD"):
        return get_post_event("XAUUSD")
    if "QQQ" in pool:
        return get_post_event("QQQ")
    return get_post_event("SPY")


def refresh_post_event() -> dict:
    """Called by the news cycle. Cheap calendar check first; only fetches price
    reactions when a high-impact event actually fired in the last 2 hours."""
    global _cached_post_event
    fired = _recent_fired_event()
    if not fired:
        if _cached_post_event:
            print("[post_event] no recent high-impact event — clearing state")
        _cached_post_event = {}
        return {}
    fresh = {a: compute_post_event(a, fired) for a in POST_EVENT_ASSETS}
    _cached_post_event = fresh
    summary = " | ".join(f"{a}:{s.get('phase','?')}(sf{s.get('size_factor',1.0)})"
                         for a, s in fresh.items())
    print(f"[post_event] {fired['event_type']} +{fired['minutes_since']}min — {summary}")
    return fresh
