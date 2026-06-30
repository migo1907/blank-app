"""
XAU/USD Migo Sniper Pro — Level 3 ML Backend (v3·26F)
FastAPI app that receives TradingView webhooks, updates adaptive weights
in GitHub storage, runs RF ensemble, fetches news sentiment, sends signals to Telegram.
"""
import os
import math
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional
from dotenv import load_dotenv

load_dotenv()

# In-memory TTL dedup: prevents double KNN weight updates when TradingView fires the
# same trade outcome to both /webhook/trade-outcome and /webhook within 1-2 seconds.
_outcome_dedup_seen: dict[str, float] = {}   # dedup_key → monotonic seconds
_OUTCOME_DEDUP_TTL = 30.0  # seconds

# Entry price cache: when Pine Script fires a trade entry, store the entry price so
# that outcome payloads (TP1_HIT, WIN, LOSS) can recover it if the field is missing/NaN.
# Key: "SYMBOL|DIRECTION|TF"  Value: (entry_price, tp1, tp2, tp3, sl, monotonic_ts)
_entry_price_cache: dict[str, tuple] = {}
_ENTRY_CACHE_TTL = 86400.0  # 24h — covers overnight/multi-day trades

# Triggered signal feed — mirrors what is sent to Telegram (last 100)
# Persisted to data branch so signals survive Railway restarts.
_signal_feed: list[dict] = []
_SIGNAL_FEED_MAX = 100
_SIGNAL_FEED_PATH = "data/signal_feed.json"

def _feed_push(entry: dict) -> None:
    """Append a triggered signal to the in-memory feed and persist to data branch."""
    global _signal_feed
    _signal_feed.append(entry)
    if len(_signal_feed) > _SIGNAL_FEED_MAX:
        _signal_feed = _signal_feed[-_SIGNAL_FEED_MAX:]
    # Persist in a background thread — best-effort, never blocks signal delivery
    _snap = list(_signal_feed)
    def _persist():
        try:
            from db import _get_file, _put_file
            _, sha = _get_file(_SIGNAL_FEED_PATH)
            _put_file(_SIGNAL_FEED_PATH, {"signals": _snap}, sha, "data: signal feed update")
        except Exception as _e:
            print(f"[feed] persist failed (non-fatal): {_e}")
    import threading
    threading.Thread(target=_persist, daemon=True).start()

def _load_signal_feed() -> None:
    """Load persisted signal feed from data branch on startup."""
    global _signal_feed
    try:
        from db import _get_file
        data, _ = _get_file(_SIGNAL_FEED_PATH)
        if isinstance(data, dict) and isinstance(data.get("signals"), list):
            _signal_feed = data["signals"][-_SIGNAL_FEED_MAX:]
            print(f"[startup] Signal feed loaded: {len(_signal_feed)} signals from data branch")
    except Exception as _e:
        print(f"[startup] Signal feed load failed (non-fatal): {_e}")

_SESSION_LABELS = {
    "OVERLAP": "London/NY Overlap", "LONDON": "London", "LONDON_OPEN": "London Open",
    "NEW_YORK": "New York", "NY_LATE": "New York Late", "ASIAN": "Asian", "OFF": "Off-Hours",
    "NYSE_OPEN": "NYSE Open", "NYSE_AFTERNOON": "NYSE Afternoon",
    "PRE_MARKET": "Pre-Market", "CLOSED": "Closed",
}

def _session_label(symbol: str) -> str:
    """Friendly current-session label, matching the Telegram alert wording."""
    try:
        from signal_engine import _session_multiplier
        is_stock = (symbol or "").upper() not in ("XAUUSD", "GOLD", "GC")
        _, name = _session_multiplier(datetime.now(timezone.utc), is_stock)
        return _SESSION_LABELS.get(name, name)
    except Exception:
        return ""


def _outcome_is_duplicate(symbol: str, direction: str, entry_price: float, exit_price: float, timeframe: str) -> bool:
    """Returns True if this exact outcome was already processed within TTL window."""
    import time
    now = time.monotonic()
    key = f"{symbol}|{direction}|{entry_price}|{exit_price}|{timeframe}"
    # Evict stale entries
    stale = [k for k, ts in _outcome_dedup_seen.items() if now - ts > _OUTCOME_DEDUP_TTL]
    for k in stale:
        del _outcome_dedup_seen[k]
    if key in _outcome_dedup_seen:
        return True
    _outcome_dedup_seen[key] = now
    return False


def _tod_sine() -> float:
    """Time-of-Day sine: 0→2π over 24 h, peaks ~06:00 UTC (London open)."""
    _now = datetime.now(timezone.utc); h = _now.hour + _now.minute / 60
    return math.sin(2 * math.pi * h / 24)

WEBHOOK_SECRET    = os.environ.get("WEBHOOK_SECRET", "")
VALID_POOLS = {
    "XAUUSD_2M", "XAUUSD_5M", "XAUUSD_15M", "XAUUSD_30M", "XAUUSD_1H",
    "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_1H", "STOCKS_MOMENTUM_4H",
    "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_1H",  "STOCKS_QUALITY_4H",
    "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_1H",    "STOCKS_INDEX_4H",
    "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_1H",      "STOCKS_QQQ_4H",
    "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_1H",   "STOCKS_SPX500_4H",
}
RAILWAY_API_TOKEN  = os.environ.get("RAILWAY_API_TOKEN", "")
RAILWAY_PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID", "")
RAILWAY_SERVICE_ID = os.environ.get("RAILWAY_SERVICE_ID", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Loading ML model (26F) from storage…")
    from ml_model import get_model
    get_model("XAUUSD_2M")

    print("[startup] Priming RF + GBM ensembles for all pools…")
    from ml_ensemble import get_rf, get_gbm
    from db import recent_outcomes
    for _pool in ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_15M", "XAUUSD_30M", "XAUUSD_1H",
                  "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_1H", "STOCKS_MOMENTUM_4H",
                  "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_1H",  "STOCKS_QUALITY_4H",
                  "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_1H",    "STOCKS_INDEX_4H",
                  "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_1H",      "STOCKS_QQQ_4H",
                  "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_1H",   "STOCKS_SPX500_4H"]:
        _hist = recent_outcomes(_pool, limit=500)
        if len(_hist) >= 50:
            get_rf(_pool).retrain(_hist)
            get_gbm(_pool).train(_hist)
            print(f"[startup] RF+GBM trained for {_pool} on {len(_hist)} trades.")
        else:
            print(f"[startup] {_pool}: {len(_hist)} trades — RF/GBM will train when data grows.")

    print("[startup] Priming joint models (gold + stocks)…")
    try:
        from ml_ensemble import get_joint_gold, get_joint_stocks, GOLD_TF_IDS, STOCK_POOL_IDS
        _gold_hists = {p: recent_outcomes(p, 500) for p in GOLD_TF_IDS}
        _gold_hists = {p: h for p, h in _gold_hists.items() if h}
        if _gold_hists:
            get_joint_gold().train(_gold_hists)
            print(f"[startup] JointGoldGBM primed on {sum(len(h) for h in _gold_hists.values())} gold trades")
        _stock_hists = {p: recent_outcomes(p, 500) for p in STOCK_POOL_IDS}
        _stock_hists = {p: h for p, h in _stock_hists.items() if h}
        if _stock_hists:
            get_joint_stocks().train(_stock_hists)
            print(f"[startup] JointStocksGBM primed on {sum(len(h) for h in _stock_hists.values())} stock trades")
    except Exception as _je:
        print(f"[startup] ⚠ Joint model priming skipped (non-fatal): {_je}")

    print("[startup] Resyncing pool win/loss counters…")
    from db import resync_pool_counters
    for _pool in ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_15M", "XAUUSD_30M", "XAUUSD_1H",
                  "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_1H", "STOCKS_MOMENTUM_4H",
                  "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_1H",  "STOCKS_QUALITY_4H",
                  "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_1H",    "STOCKS_INDEX_4H",
                  "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_1H",      "STOCKS_QQQ_4H",
                  "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_1H",   "STOCKS_SPX500_4H"]:
        resync_pool_counters(_pool)

    print("[startup] Verifying data branch is writable…")
    try:
        from db import _get_file, _put_file
        _hc_data, _hc_sha = _get_file("data/health.json")
        if not isinstance(_hc_data, dict):
            _hc_data = {}
        _hc_data["startup_at"] = datetime.now(timezone.utc).isoformat()
        _put_file("data/health.json", _hc_data, _hc_sha, "chore: startup health check")
        print("[startup] Data branch writable ✓")
    except Exception as _e:
        print(f"[startup] ⚠ DATA BRANCH NOT WRITABLE: {_e}. Check GITHUB_TOKEN scope.")

    print("[startup] Loading feature cache from GitHub…")
    from signal_engine import load_feature_cache
    load_feature_cache()

    print("[startup] Loading HTF bias store from GitHub…")
    from htf_bias import load_bias_store
    load_bias_store()

    print("[startup] Loading market macro bias from GitHub…")
    from market_macro import load_macro_bias
    load_macro_bias()

    print("[startup] Loading HMM regime state from GitHub…")
    from regime_model import load_regimes
    load_regimes()

    print("[startup] Loading MTF confluence stack from GitHub…")
    from mtf_confluence import load_mtf
    load_mtf()

    print("[startup] Loading swing candidates from GitHub…")
    from swing_screener import load_candidates
    load_candidates()

    print("[startup] Loading signal feed from GitHub…")
    _load_signal_feed()

    print("[startup] Loading Fear & Greed index from GitHub…")
    try:
        from fear_greed import load_fear_greed
        load_fear_greed()
    except Exception as _fg_e:
        print(f"[startup] Fear & Greed load failed (non-fatal): {_fg_e}")

    print("[startup] Loading CBOE put/call ratio from GitHub…")
    try:
        from cboe_data import load_pc_ratio
        load_pc_ratio()
    except Exception as _pc_e:
        print(f"[startup] CBOE P/C load failed (non-fatal): {_pc_e}")

    if not WEBHOOK_SECRET:
        print("[startup] ⚠ WARNING: WEBHOOK_SECRET is not set — all webhook endpoints are open to unauthenticated requests.")

    print("[startup] Starting scheduler…")
    from scheduler import start_scheduler, _news_signal_cycle
    start_scheduler()
    asyncio.create_task(_news_signal_cycle())

    yield

    from scheduler import stop_scheduler
    stop_scheduler()
    print("[shutdown] Done.")


app = FastAPI(
    title="Migo Sniper Pro — ML Backend v3·26F",
    description="Adaptive KNN + RF + GBM ensemble + news sentiment for XAU/USD",
    version="3.1.0",
    lifespan=lifespan,
)


# Pine Script str.tostring(na, "#.##") emits unquoted NaN — invalid JSON.
# Pure ASGI middleware patches the receive() callable directly so the sanitized
# body reaches FastAPI's JSON parser. BaseHTTPMiddleware cannot do this because
# call_next() ignores the request object and uses the original ASGI receive channel.
# Also handles Infinity/-Infinity which Pine Script produces on division-by-zero
# (e.g. ATR-based ratios on high-priced assets like SPX500).
import re as _re

_NAN_RE  = _re.compile(rb':\s*NaN\b')
_NAN_RE2 = _re.compile(rb',\s*NaN\b')
_INF_RE  = _re.compile(rb':\s*-?Infinity\b')
_INF_RE2 = _re.compile(rb',\s*-?Infinity\b')


class _SanitizeNaNMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Only intercept POST/PUT/PATCH — GET/HEAD have no body
        if scope.get("method", "GET") not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        # Consume the full body from the real receive channel
        body_parts: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            body_parts.append(message.get("body", b""))
            more_body = message.get("more_body", False)

        body = b"".join(body_parts)

        # TradingView sometimes sends webhooks without Content-Type header.
        # FastAPI won't parse the body as JSON without it → Pydantic gets raw bytes → 500.
        # Ensure Content-Type: application/json is always present for POST bodies.
        headers = list(scope.get("headers", []))
        has_ct = any(name.lower() == b"content-type" for name, _ in headers)
        if not has_ct and body.lstrip()[:1] == b"{":
            headers.append((b"content-type", b"application/json"))
            scope = dict(scope)
            scope["headers"] = headers

        # Sanitize regardless of Content-Type — TradingView sometimes omits it.
        # Replace unquoted NaN / Infinity / -Infinity with 0 so JSON parses cleanly.
        patched = False
        if b"NaN" in body:
            body = _NAN_RE.sub(b":null", body)
            body = _NAN_RE2.sub(b",null", body)
            patched = True
        if b"Infinity" in body:
            body = _INF_RE.sub(b":null", body)
            body = _INF_RE2.sub(b",null", body)
            patched = True
        if patched:
            print(f"[nan_middleware] Sanitized invalid JSON literals in {scope.get('path','?')} ({len(body)} bytes)")

        # Replace receive with one that yields the (possibly patched) body
        _sent = False
        async def _patched_receive():
            nonlocal _sent
            if not _sent:
                _sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, _patched_receive, send)


app.add_middleware(_SanitizeNaNMiddleware)


from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request, exc):
    import json as _json
    try:
        body = await request.body()
        body_preview = body[:300].decode("utf-8", errors="replace")
    except Exception:
        body_preview = "<unreadable>"
    errors = exc.errors()
    print(f"[422] {request.method} {request.url.path} — {len(errors)} validation error(s)")
    for e in errors[:5]:
        print(f"  field={e.get('loc')} type={e.get('type')} msg={e.get('msg')}")
    print(f"  body_preview: {body_preview}")
    # Pydantic includes raw bytes in 'input' field — JSONResponse can't serialize bytes
    safe_errors = []
    for e in errors:
        se = dict(e)
        if isinstance(se.get("input"), (bytes, bytearray)):
            se["input"] = se["input"].decode("utf-8", errors="replace")
        safe_errors.append(se)
    return JSONResponse(status_code=422, content={"detail": safe_errors})


@app.exception_handler(Exception)
async def _unhandled_error_handler(request, exc):
    """
    Catch-all for unhandled exceptions (500s). Records the traceback to
    data/error_log.json on the data branch so production errors are inspectable
    out-of-band (no Railway log access needed), then returns a clean 500.
    HTTPException / RequestValidationError have their own handlers and are
    unaffected. Logging runs in a background task so it never delays the response.
    """
    import traceback as _tb
    tb = "".join(_tb.format_exception(type(exc), exc, exc.__traceback__))
    print(f"[500] {request.method} {request.url.path}\n{tb}")
    try:
        from db import log_error
        asyncio.create_task(asyncio.to_thread(
            log_error,
            f"{request.method} {request.url.path}",
            tb,
            {"path": str(request.url.path)},
        ))
    except Exception as _le:
        print(f"[500] error-sink scheduling failed (non-fatal): {_le}")
    return JSONResponse(status_code=500, content={"detail": "internal error"})


class TradeOutcomePayload(BaseModel):
    secret:      str
    trade_id:    Optional[str]   = None
    direction:   str             = ""
    outcome:     str             = ""
    ml_outcome:  Optional[str]   = None
    mfe:         float           = 0.0
    mae:         float           = 0.0   # max adverse excursion (Phase B — stop learning)
    timeframe:   Optional[str]   = None
    tp_stage:    str             = ""
    entry_price: float           = 0.0
    exit_price:  float           = 0.0
    ml_score:    float           = 0.5
    symbol:      Optional[str]   = None
    f1:  float = 0.0; f2:  float = 0.0; f3:  float = 0.0; f4:  float = 0.0
    f5:  float = 0.0; f6:  float = 0.0; f7:  float = 0.0; f8:  float = 0.0
    f9:  float = 0.0; f10: float = 0.0; f11: float = 0.0; f12: float = 0.0
    f13: float = 0.0; f14: float = 0.0; f15: float = 0.0; f16: float = 0.0
    f17: float = 0.0; f18: float = 0.0; f19: float = 0.0; f20: float = 0.0
    f21: float = 0.0; f22: float = 0.0; f23: float = 0.0; f24: float = 0.0
    f25: float = 0.0; f26: float = 0.0

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, values):
        import json as _json
        if isinstance(values, (bytes, bytearray)):
            values = _json.loads(values.decode("utf-8", errors="replace"))
        if not isinstance(values, dict):
            return values
        float_fields = {
            "ml_score", "mfe", "mae", "entry_price", "exit_price",
            "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10",
            "f11","f12","f13","f14","f15","f16","f17","f18","f19","f20",
            "f21","f22","f23","f24","f25","f26",
        }
        for k in float_fields:
            if k in values and values[k] is None:
                values[k] = 0.0
        for k in ("tp_stage", "direction", "outcome"):
            if k in values and values[k] is None:
                values[k] = ""
        return values


class SignalEntryPayload(BaseModel):
    secret:      str
    direction:   str   = ""
    timeframe:   str   = "5"
    trigger:     str   = "RSI"
    symbol:      str   = "XAUUSD"
    entry_price: float = 0.0
    tp1:         float = 0.0
    tp2:         float = 0.0
    tp3:         float = 0.0
    sl:          float = 0.0
    ml_score:    float = 0.5
    tier:        str   = "MED"

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, values):
        import json as _json
        if isinstance(values, (bytes, bytearray)):
            values = _json.loads(values.decode("utf-8", errors="replace"))
        if not isinstance(values, dict):
            return values
        for k in ("entry_price", "tp1", "tp2", "tp3", "sl", "ml_score"):
            if k in values and values[k] is None:
                values[k] = 0.0
        for k in ("direction", "trigger", "symbol", "tier", "timeframe"):
            if k in values and values[k] is None:
                values[k] = ""
        return values


class UnifiedPayload(BaseModel):
    secret:      str
    direction:   str             = ""
    timeframe:   Optional[str]   = None
    trigger:     Optional[str]   = None
    symbol:      Optional[str]   = None
    entry_price: Optional[float] = None
    tp1:         Optional[float] = None
    tp2:         Optional[float] = None
    tp3:         Optional[float] = None
    sl:          Optional[float] = None
    ml_score:    float           = 0.5
    tier:        Optional[str]   = None
    trade_id:    Optional[str]   = None
    outcome:     Optional[str]   = None
    ml_outcome:  Optional[str]   = None
    mfe:         float           = 0.0
    mae:         float           = 0.0
    tp_stage:    str             = ""
    exit_price:  Optional[float] = None
    f1:  float = 0.0; f2:  float = 0.0; f3:  float = 0.0; f4:  float = 0.0
    f5:  float = 0.0; f6:  float = 0.0; f7:  float = 0.0; f8:  float = 0.0
    f9:  float = 0.0; f10: float = 0.0; f11: float = 0.0; f12: float = 0.0
    f13: float = 0.0; f14: float = 0.0; f15: float = 0.0; f16: float = 0.0
    f17: float = 0.0; f18: float = 0.0; f19: float = 0.0; f20: float = 0.0
    f21: float = 0.0; f22: float = 0.0; f23: float = 0.0; f24: float = 0.0
    f25: float = 0.0; f26: float = 0.0

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, values):
        """TradingView sends JSON null for Pine Script na() values. Coerce to 0.0 for float fields."""
        import json as _json
        if isinstance(values, (bytes, bytearray)):
            values = _json.loads(values.decode("utf-8", errors="replace"))
        if not isinstance(values, dict):
            return values
        float_fields = {
            "ml_score", "mfe", "mae",
            "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10",
            "f11","f12","f13","f14","f15","f16","f17","f18","f19","f20",
            "f21","f22","f23","f24","f25","f26",
        }
        for k in float_fields:
            if k in values and values[k] is None:
                values[k] = 0.0
        if "tp_stage" in values and values["tp_stage"] is None:
            values["tp_stage"] = ""
        if "direction" in values and values["direction"] is None:
            values["direction"] = ""
        return values


def _validate_secret(secret: str) -> None:
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret.")


@app.get("/auth/login")
async def auth_login(passcode: str = ""):
    """Passcode gate for the PWA. Validates against APP_PASSCODE (Railway env);
    on success returns the API secret so the client can call protected endpoints.
    The secret is therefore never shipped in the static bundle."""
    expected = os.environ.get("APP_PASSCODE") or WEBHOOK_SECRET or "gold2026"
    if passcode and passcode == expected:
        return {"ok": True, "secret": WEBHOOK_SECRET or "gold2026"}
    raise HTTPException(status_code=401, detail="Invalid passcode")


@app.get("/market-hours")
async def market_hours():
    from market_calendar import get_market_status
    return get_market_status()


@app.api_route("/health", methods=["GET", "POST", "HEAD"])
async def health():
    from scheduler import _scheduler, start_scheduler, _news_signal_cycle
    scheduler_ok = bool(_scheduler and _scheduler.running)

    if not scheduler_ok:
        print("[health] Scheduler not running — auto-restarting.")
        start_scheduler()
        asyncio.create_task(_news_signal_cycle())

    try:
        from signal_engine import get_ml_health
        ml_health = await asyncio.to_thread(get_ml_health)
    except Exception as _e:
        ml_health = {"error": str(_e)}

    try:
        from system_directive import get_directive_summary
        directive = get_directive_summary()
    except Exception:
        directive = {}

    try:
        from regime_model import get_regime, REGIME_ASSETS
        regimes = {a: get_regime(a) for a in REGIME_ASSETS}
    except Exception:
        regimes = {}

    try:
        from mtf_confluence import get_mtf, MTF_ASSETS
        mtf = {a: get_mtf(a) for a in MTF_ASSETS}
    except Exception:
        mtf = {}

    try:
        from post_event import get_post_event, POST_EVENT_ASSETS
        post_evt = {a: get_post_event(a) for a in POST_EVENT_ASSETS}
        post_evt = {k: v for k, v in post_evt.items() if v.get("active")}
    except Exception:
        post_evt = {}

    try:
        from market_macro import get_macro_bias, get_equity_macro_bias
        intermarket = {
            "vix":       (get_equity_macro_bias() or {}).get("vix"),
            "dxy_break": (get_macro_bias() or {}).get("dxy_break"),
        }
    except Exception:
        intermarket = {}

    return {
        "status":      "ok",
        "version":     "5.2.0-26F",
        "scheduler":   "running" if scheduler_ok else "restarted",
        "ml":          ml_health,
        "directive":   directive,
        "regimes":     regimes,
        "mtf":         mtf,
        "post_event":  post_evt,
        "intermarket": intermarket,
    }


@app.get("/test-personal-alert")
async def test_personal_alert(secret: str = ""):
    _validate_secret(secret)
    from scheduler import _test_personal_alert
    asyncio.create_task(_test_personal_alert())
    return {"status": "sent", "chat_id": "966897595"}


@app.get("/test-telegram")
async def test_telegram(secret: str = ""):
    _validate_secret(secret)
    from telegram_bot import send_text
    import os
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return {"status": "error", "detail": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment."}
    await send_text("✅ Migo Sniper Pro — Telegram test OK!\n\n🤖 Backend connected.\n📡 Signals will appear here every 15 min.")
    return {"status": "sent", "chat_id": chat_id, "token_prefix": token[:10] + "..."}


def _normalize_outcome(raw: str) -> str:
    """Map Pine Script outcome strings to internal WIN/LOSS/PARTIAL/HEARTBEAT/PROGRESS.

    TP1_HIT = trade closed at first target → WIN.
    TP2_HIT / TP3_HIT = addon score on an already-open trade → PROGRESS (no new DB record).
    """
    v = raw.upper().strip()
    if v == "HEARTBEAT":                          return "HEARTBEAT"
    if v == "TP1_HIT":                            return "WIN"
    if v in ("TP2_HIT", "TP3_HIT"):              return "PROGRESS"
    if v in ("WIN", "TP3", "TP2", "TP1"):         return "WIN"
    if v in ("LOSS", "SL"):                        return "LOSS"
    if v in ("PARTIAL", "SL_TP1", "SL_TP2",
             "SL_TP3", "TP1_SL", "TP2_SL"):       return "PARTIAL"
    return "LOSS"  # unknown → treat as loss


@app.post("/webhook/trade-outcome")
async def trade_outcome(payload: TradeOutcomePayload):
    _validate_secret(payload.secret)
    payload.outcome = _normalize_outcome(payload.outcome)

    # Log raw payload before any processing (skip heartbeats to save space)
    if payload.outcome != "HEARTBEAT":
        asyncio.create_task(asyncio.to_thread(
            __import__("db").log_raw_webhook, payload.model_dump()
        ))

    # HEARTBEAT — update feature cache only, no trade record
    if payload.outcome == "HEARTBEAT":
        from ml_model import Features
        from db import symbol_to_pool
        from signal_engine import update_latest_features
        sym  = getattr(payload, "symbol", "XAUUSD") or "XAUUSD"
        pool = symbol_to_pool(sym, payload.timeframe or "")
        if not pool:
            # Unmapped pool (e.g. XAUUSD 4H) — drop silently, no cache write
            return {"status": "ok", "outcome": "HEARTBEAT", "pool": "ignored"}
        features = Features(
            f1=payload.f1, f2=payload.f2, f3=payload.f3, f4=payload.f4,
            f5=payload.f5, f6=payload.f6, f7=payload.f7, f8=payload.f8,
            f9=payload.f9, f10=payload.f10, f11=payload.f11, f12=payload.f12,
            f13=payload.f13, f14=payload.f14, f15=payload.f15, f16=payload.f16,
            f17=payload.f17, f18=payload.f18, f19=payload.f19, f20=payload.f20,
            f21=payload.f21, f22=payload.f22, f23=payload.f23, f24=payload.f24,
            f25=payload.f25, f26=payload.f26,
        )
        # Update in-memory cache immediately, persist to GitHub in background
        from signal_engine import _latest_features
        _latest_features[pool] = features
        async def _persist_heartbeat():
            try:
                await asyncio.to_thread(update_latest_features, pool, features)
            except Exception as e:
                print(f"[heartbeat] persist error: {e}")
        asyncio.create_task(_persist_heartbeat())
        print(f"[heartbeat] Cache updated for pool={pool}")
        return {"status": "ok", "outcome": "HEARTBEAT", "pool": pool}

    # PROGRESS — TP1/TP2 milestone reached but trade still open; log only, no ML or DB write
    if payload.outcome == "PROGRESS":
        print(f"[progress] {payload.symbol} {payload.direction} {payload.tp_stage} @ {payload.exit_price}")
        return {"status": "ok", "outcome": "PROGRESS", "stage": payload.tp_stage}

    from ml_model import get_model, Features
    from ml_ensemble import get_rf, get_gbm
    from db import insert_outcome, recent_outcomes, symbol_to_pool

    sym  = payload.symbol or "XAUUSD"

    # Recover entry_price from cache if Pine Script sent NaN/0 (NaN is sanitized to 0)
    import time as _time
    if not payload.entry_price:
        _ck = f"{sym.upper()}|{payload.direction}|{payload.timeframe or ''}"
        _cached = _entry_price_cache.get(_ck)
        if _cached and (_time.monotonic() - _cached[5]) < _ENTRY_CACHE_TTL:
            payload.entry_price = _cached[0]
            # Backfill TP/SL levels if also missing
            if not payload.tp1: payload.tp1 = _cached[1]
            if not payload.tp2: payload.tp2 = _cached[2]
            if not payload.tp3: payload.tp3 = _cached[3]
            if not payload.sl:  payload.sl  = _cached[4]
            print(f"[trade-outcome] Recovered entry_price={payload.entry_price} from cache for {sym} {payload.direction}")

    # If exit_price still missing but we have a TP level, use tp1 as exit for TP1 wins
    if not payload.exit_price and payload.tp1:
        payload.exit_price = payload.tp1
        print(f"[trade-outcome] Used tp1={payload.tp1} as exit_price for {sym} {payload.direction}")

    if not payload.entry_price or not payload.exit_price:
        print(f"[trade-outcome] Missing entry/exit price for {sym} {payload.direction} — skipping (no cache hit)")
        return {"status": "ok", "skipped": "missing_prices"}

    def _sync_process_outcome():
        pool = symbol_to_pool(sym, payload.timeframe or "")
        model = get_model(pool)
        features = Features(
            f1=payload.f1,   f2=payload.f2,   f3=payload.f3,   f4=payload.f4,
            f5=payload.f5,   f6=payload.f6,   f7=payload.f7,   f8=payload.f8,
            f9=payload.f9,   f10=payload.f10, f11=payload.f11, f12=payload.f12,
            f13=payload.f13, f14=payload.f14, f15=payload.f15, f16=payload.f16,
            f17=payload.f17, f18=payload.f18, f19=payload.f19, f20=payload.f20,
            f21=payload.f21, f22=payload.f22, f23=payload.f23, f24=payload.f24,
            f25=payload.f25, f26=payload.f26,
        )
        raw_pct = (payload.exit_price - payload.entry_price) / max(payload.entry_price, 0.0001) * 100
        pnl_pct = raw_pct if payload.direction == "LONG" else -raw_pct
        ml_label = payload.ml_outcome or payload.outcome
        _is_dup = _outcome_is_duplicate(sym, payload.direction, payload.entry_price, payload.exit_price, payload.timeframe or "")
        if not _is_dup:
            model.update_on_outcome(features, payload.direction, ml_label, tp_stage=payload.tp_stage or "", pnl=pnl_pct)
        else:
            print(f"[trade-outcome] Duplicate within {_OUTCOME_DEDUP_TTL}s — skipping weight update for {sym} {payload.direction} entry={payload.entry_price}")
        from signal_engine import _detect_regime, _session_multiplier
        _is_stock_pool = not pool.startswith("XAUUSD")
        _, _session = _session_multiplier(datetime.now(timezone.utc), is_stock=_is_stock_pool)
        _regime = _detect_regime(features)
        return pool, model, features, pnl_pct, ml_label, _regime, _session

    try:
        pool, model, features, pnl_pct, ml_label, _regime, _session = await asyncio.to_thread(_sync_process_outcome)
    except Exception as _exc:
        print(f"[trade-outcome] ERROR processing {sym} {payload.direction} outcome={payload.outcome}: {_exc}")
        import traceback; traceback.print_exc()
        return {"status": "error", "detail": str(_exc)}

    outcome_row = {
        "symbol":        sym,
        "direction":     payload.direction,
        "trigger":       getattr(payload, "trigger", "") or "",
        "entry_price":   payload.entry_price,
        "exit_price":    payload.exit_price,
        "outcome":       payload.outcome,
        "ml_outcome":    ml_label,
        "mfe":           payload.mfe,
        "mae":           payload.mae,
        "tp_stage":      payload.tp_stage or "",
        "timeframe":     payload.timeframe or "",
        "pnl_pct":       round(pnl_pct, 4),
        "ml_bull_score": payload.ml_score,
        "regime":        _regime,
        "session":       _session,
    }
    outcome_row.update(features.as_db_dict())

    # Forward audit instrumentation: store the backend ensemble's P(win) on this
    # trade's own features alongside the Pine KNN `ml_bull_score`. The Pine score
    # is anti-predictive on gold; the backend ensemble is what the live gate uses,
    # but it was never persisted, so the gate could not be audited from history.
    # Recording it per close lets future autopsies compare the real gate vs outcome.
    try:
        from signal_engine import backend_ensemble_prob
        outcome_row["ensemble_prob"] = await asyncio.to_thread(
            backend_ensemble_prob, pool, features, payload.direction
        )
    except Exception as _ep_err:
        print(f"[trade-outcome] ensemble_prob annotate failed (non-fatal): {_ep_err}")

    async def _persist():
        try:
            for _save_attempt in range(3):
                try:
                    await asyncio.to_thread(model.save, pool)
                    break
                except Exception as _se:
                    if _save_attempt < 2:
                        await asyncio.sleep(1 << _save_attempt)
                    else:
                        raise
            await asyncio.to_thread(insert_outcome, outcome_row)

            # Log to mistake ledger for weekly autopsy
            if outcome_row.get("outcome") == "LOSS":
                from db import log_mistake
                await asyncio.to_thread(log_mistake, outcome_row)

            from signal_engine import (
                invalidate_history_cache, refresh_pool_models,
                refresh_joint_models, record_oob_prediction,
                should_retrigger_retrain,
            )
            invalidate_history_cache(pool)
            history = await asyncio.to_thread(recent_outcomes, pool, 500)

            # Record OOS prediction for champion-challenger tracking.
            # PARTIAL is only a true win when pnl_pct > 0 — 43% of PARTIAL trades
            # across all pools have negative PnL (SL hit after TP1 breakeven move).
            # This mirrors the same guard already applied to the KNN weight update.
            _prev_score = outcome_row.get("ml_bull_score") or 0.5
            _pnl = outcome_row.get("pnl_pct", 0.0) or 0.0
            _raw_outcome = outcome_row.get("outcome")
            _actual_win = _raw_outcome == "WIN" or (_raw_outcome == "PARTIAL" and _pnl > 0)
            record_oob_prediction(pool, float(_prev_score), bool(_actual_win))

            # Retrain when: (a) pool first reaches 50 trades, OR
            #               (b) regime shift detected (WR dropped >5pp in last 20 vs prev 20)
            _needs_retrain = (len(history) >= 50 and
                              (len(history) % 10 == 0 or  # normal cadence every 10 new trades
                               should_retrigger_retrain(pool, history)))
            if _needs_retrain:
                await asyncio.to_thread(get_rf(pool).retrain, history)
                await asyncio.to_thread(get_gbm(pool).train, history)
                # Update threshold (F-beta≥80 trades, NP otherwise) + champion-challenger check
                await asyncio.to_thread(refresh_pool_models, pool, history)

            # Retrain joint models (combines all related pools — most valuable for thin pools)
            from db import symbol_to_pool as _stp
            from ml_ensemble import GOLD_TF_IDS, STOCK_POOL_IDS
            _related_pools = list(GOLD_TF_IDS.keys()) if pool in GOLD_TF_IDS else list(STOCK_POOL_IDS.keys())
            _all_hists = {}
            for _p in _related_pools:
                _h = await asyncio.to_thread(recent_outcomes, _p, 500)
                if _h:
                    _all_hists[_p] = _h
            if _all_hists:
                await asyncio.to_thread(refresh_joint_models, _all_hists)
            from scheduler import record_webhook_ok
            record_webhook_ok()
        except Exception as e:
            from scheduler import record_webhook_error
            record_webhook_error()
            print(f"[trade-outcome] background persist error: {e}")
    asyncio.create_task(_persist())

    return {
        "status":       "ok",
        "outcome":      payload.outcome,
        "new_weights":  {f"w{i+1}": round(w, 4) for i, w in enumerate(model.weights)},
        "total_wins":   model._total_wins,
        "total_losses": model._total_losses,
        "win_rate":     round(model.win_rate * 100, 1),
    }


@app.post("/webhook/signal-entry")
async def signal_entry(payload: SignalEntryPayload):
    _validate_secret(payload.secret)
    if payload.direction not in ("LONG", "SHORT"):
        print(f"[signal-entry] Ignoring entry with direction={payload.direction!r} — not LONG/SHORT")
        return {"status": "ignored", "reason": "invalid_direction"}

    from htf_bias import is_htf, store_bias, get_active_bias
    sym = payload.symbol or "XAUUSD"
    tf  = payload.timeframe or "5"

    # Only XAUUSD 2M is suppressed — all other timeframes send to Telegram
    if str(tf).strip() == "2" and sym.upper() == "XAUUSD":
        print(f"[signal-entry] XAUUSD 2M — ML only, not sent to Telegram")
        return {"status": "ok", "routed_to": "ml-only", "reason": "2m_suppressed"}

    # HTF signals: store bias AND send to Telegram
    if is_htf(tf):
        store_bias(sym, payload.direction, tf, payload.trigger or "", payload.ml_score)
        print(f"[signal-entry] HTF bias stored: {payload.direction} {sym} TF={tf}")

    from telegram_bot import send_entry_signal
    from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event
    entry = payload.entry_price or 0.0
    if entry <= 0:
        print(f"[signal-entry] Missing entry_price for {sym} {payload.direction} — skipping Telegram")
        return {"status": "ok", "routed_to": "suppressed", "reason": "no_entry_price"}

    # Cache the entry price so outcome payloads can recover it if missing/NaN
    import time as _time
    _cache_key = f"{sym.upper()}|{payload.direction}|{tf}"
    _entry_price_cache[_cache_key] = (entry, payload.tp1 or 0.0, payload.tp2 or 0.0,
                                      payload.tp3 or 0.0, payload.sl or 0.0, _time.monotonic())

    # Backend ML quality grade — annotate-only: never suppress,
    # tag the entry with P(TP1+) so the trader decides.
    from signal_engine import score_entry_gate
    from db import symbol_to_pool
    try:
        _gate = await asyncio.to_thread(
            score_entry_gate, symbol_to_pool(sym, tf), payload.direction, payload.trigger or ""
        )
    except Exception as _ge:
        print(f"[signal-entry] gate error (non-fatal): {_ge}")
        _gate = {"pass": True, "score": 0.5, "reason": "gate_error", "components": {}}
    print(f"[signal-entry] ML QUALITY {payload.direction} {sym} TF={tf} "
          f"score={_gate['score']} ({_gate['reason']}) components={_gate['components']}")

    bias        = get_active_bias(sym, payload.direction)
    contra_bias = get_active_bias(sym, "SHORT" if payload.direction == "LONG" else "LONG")
    htf_context = "htf_direct" if is_htf(tf) else ("with_bias" if bias else ("counter_trend" if contra_bias else "scalp"))
    print(f"[signal-entry] {payload.direction} {sym} TF={tf} htf={htf_context} → sending to Telegram")

    _sig_payload = {
        "direction":   payload.direction,
        "timeframe":   tf,
        "trigger":     payload.trigger or "RSI",
        "symbol":      sym,
        "entry_price": entry,
        "tp1":         payload.tp1 or 0.0,
        "tp2":         payload.tp2 or 0.0,
        "tp3":         payload.tp3 or 0.0,
        "sl":          payload.sl or 0.0,
        "ml_score":    payload.ml_score,
        "tier":        payload.tier or "MED",
        "quality_score":  _gate["score"],
        "quality_reason": _gate["reason"],
        "news_score":  get_latest_news_sentiment(),
        "velocity":    get_latest_velocity().get("label", "NORMAL"),
        "event":       get_latest_event().get("event_type", ""),
        "htf_bias":    bias,
        "contra_bias": contra_bias,
        "htf_context": htf_context,
        "session":     _session_label(sym),
        "fired_at":    datetime.now(timezone.utc).isoformat(),
    }
    _feed_push(_sig_payload)
    asyncio.create_task(send_entry_signal(_sig_payload))
    return {"status": "ok", "routed_to": "signal-entry", "direction": payload.direction, "htf_context": htf_context}


@app.post("/webhook")
async def unified_webhook(payload: UnifiedPayload):
    _validate_secret(payload.secret)

    if payload.outcome is not None:
        payload.outcome = _normalize_outcome(payload.outcome)

    # Log raw payload before processing (skip heartbeats to save space)
    if payload.outcome != "HEARTBEAT" and payload.trade_id != "heartbeat":
        asyncio.create_task(asyncio.to_thread(
            __import__("db").log_raw_webhook, payload.model_dump()
        ))

    # Outcome payloads always carry trade_id + outcome — they must be checked FIRST.
    # Entry payloads can also carry tp1/sl but never trade_id + outcome together.
    # Checking is_entry first was a bug: a trade-close that happened to include tp1/sl
    # would be routed to HTF bias store and the trade record would be permanently lost.
    is_outcome = payload.trade_id is not None and payload.outcome is not None and \
                 payload.outcome not in ("HEARTBEAT", "PROGRESS")
    is_entry   = payload.tp1 is not None and payload.sl is not None and not is_outcome

    if is_entry:
        if payload.direction not in ("LONG", "SHORT"):
            print(f"[webhook] Ignoring entry with direction={payload.direction!r} — not LONG/SHORT")
            return {"status": "ignored", "reason": "invalid_direction"}
        from htf_bias import is_htf, store_bias, get_active_bias
        sym = payload.symbol or "XAUUSD"
        tf  = payload.timeframe or "5"

        # Only XAUUSD 2M is suppressed — all other timeframes send to Telegram
        if str(tf).strip() == "2" and sym.upper() == "XAUUSD":
            print(f"[webhook] XAUUSD 2M — ML only, not sent to Telegram")
            return {"status": "ok", "routed_to": "ml-only", "reason": "2m_suppressed"}

        # HTF signals: store bias AND send to Telegram
        if is_htf(tf):
            store_bias(sym, payload.direction, tf, payload.trigger or "", payload.ml_score)
            print(f"[webhook] HTF bias stored: {payload.direction} {sym} TF={tf}")

        from telegram_bot import send_entry_signal
        from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event
        entry = payload.entry_price or 0.0
        if entry <= 0:
            print(f"[webhook] Missing entry_price for {sym} {payload.direction} — skipping Telegram")
            return {"status": "ok", "routed_to": "suppressed", "reason": "no_entry_price"}

        # Cache the entry price so outcome payloads can recover it if missing/NaN
        import time as _time
        _cache_key = f"{sym.upper()}|{payload.direction}|{tf}"
        _entry_price_cache[_cache_key] = (entry, payload.tp1 or 0.0, payload.tp2 or 0.0,
                                          payload.tp3 or 0.0, payload.sl or 0.0, _time.monotonic())

        # Backend ML quality grade — annotate-only mode. Re-score the Pine-fired
        # entry with the trained KNN+RF+GBM (P of reaching TP1+), but never
        # suppress: every entry reaches Telegram tagged with its grade so the
        # trader decides. (Switched from silent suppression: the models are
        # young and suppression was wrongly blocking some winners.)
        from signal_engine import score_entry_gate
        from db import symbol_to_pool
        try:
            _gate = await asyncio.to_thread(
                score_entry_gate, symbol_to_pool(sym, tf), payload.direction, payload.trigger or ""
            )
        except Exception as _ge:
            print(f"[webhook] gate error (non-fatal): {_ge}")
            _gate = {"pass": True, "score": 0.5, "reason": "gate_error", "components": {}}
        print(f"[webhook] ML QUALITY {payload.direction} {sym} TF={tf} "
              f"score={_gate['score']} ({_gate['reason']}) components={_gate['components']}")

        # Higher-quality-only gate: suppress signals the backend ensemble grades
        # below the pool's own adaptive threshold (F-beta / expectancy tuned,
        # default 0.45) — i.e. honor _gate["pass"] instead of a flat 0.40 cutoff.
        # Why: a walk-forward audit of the live gold ledger showed the backend
        # ensemble ranks outcomes (AUC ~0.52–0.56; top-quartile +2–11pp over base)
        # while the Pine on-chart KNN that fires the entry is anti-predictive
        # (AUC ~0.46). The flat 0.40 cutoff sat *below* the gate's own 0.45
        # threshold, so trades the ensemble already judged sub-par still reached
        # Telegram. Suppressing them puts the calibrated, OOS-validated model in
        # the driver's seat.
        # Guards: never suppress while models are warming up (cold-start / no
        # features / gate error), and never suppress a THIN pool (Rule 8 — a
        # low-confidence miss must not starve the cold-start data the pool needs
        # to reach 50 trades). Suppression only silences the Telegram alert; the
        # HTF bias store + entry-price cache already ran and the trade still feeds
        # the ML at close.
        _warming = _gate["reason"] in ("no_features_cached", "cold_start_bypass", "gate_error")
        if not _warming and not _gate.get("thin_pool") and not _gate["pass"]:
            print(f"[webhook] SUPPRESSED weak {payload.direction} {sym} TF={tf} "
                  f"score={_gate['score']} < threshold={_gate.get('threshold')} "
                  f"({_gate['reason']})")
            return {"status": "ok", "routed_to": "suppressed",
                    "reason": "weak_ml_quality", "score": _gate["score"]}

        bias        = get_active_bias(sym, payload.direction)
        contra_bias = get_active_bias(sym, "SHORT" if payload.direction == "LONG" else "LONG")
        htf_context = "htf_direct" if is_htf(tf) else ("with_bias" if bias else ("counter_trend" if contra_bias else "scalp"))
        print(f"[webhook] {payload.direction} {sym} TF={tf} htf={htf_context} → sending to Telegram")

        _sig_payload2 = {
            "direction":   payload.direction,
            "timeframe":   tf,
            "trigger":     payload.trigger or "RSI",
            "symbol":      sym,
            "entry_price": entry,
            "tp1":         payload.tp1 or 0.0,
            "tp2":         payload.tp2 or 0.0,
            "tp3":         payload.tp3 or 0.0,
            "sl":          payload.sl or 0.0,
            "ml_score":    payload.ml_score,
            "tier":        payload.tier or "MED",
            "quality_score":  _gate["score"],
            "quality_reason": _gate["reason"],
            "news_score":  get_latest_news_sentiment(),
            "velocity":    get_latest_velocity().get("label", "NORMAL"),
            "event":       get_latest_event().get("event_type", ""),
            "htf_bias":    bias,
            "contra_bias": contra_bias,
            "htf_context": htf_context,
            "session":     _session_label(sym),
            "fired_at":    datetime.now(timezone.utc).isoformat(),
        }
        _feed_push(_sig_payload2)
        asyncio.create_task(send_entry_signal(_sig_payload2))
        return {"status": "ok", "routed_to": "signal-entry", "direction": payload.direction, "htf_context": htf_context}

    if payload.outcome == "HEARTBEAT":
        from ml_model import Features
        from db import symbol_to_pool
        from signal_engine import update_latest_features
        sym2 = payload.symbol or "XAUUSD"
        pool = symbol_to_pool(sym2, payload.timeframe or "")
        if not pool:
            return {"status": "ok", "outcome": "HEARTBEAT", "pool": "ignored"}
        features = Features(
            f1=payload.f1, f2=payload.f2, f3=payload.f3, f4=payload.f4,
            f5=payload.f5, f6=payload.f6, f7=payload.f7, f8=payload.f8,
            f9=payload.f9, f10=payload.f10, f11=payload.f11, f12=payload.f12,
            f13=payload.f13, f14=payload.f14, f15=payload.f15, f16=payload.f16,
            f17=payload.f17, f18=payload.f18, f19=payload.f19, f20=payload.f20,
            f21=payload.f21, f22=payload.f22, f23=payload.f23, f24=payload.f24,
            f25=payload.f25, f26=payload.f26,
        )
        from signal_engine import _latest_features
        _latest_features[pool] = features
        async def _persist_hb():
            try:
                await asyncio.to_thread(update_latest_features, pool, features)
            except Exception as e:
                print(f"[heartbeat] persist error: {e}")
        asyncio.create_task(_persist_hb())
        print(f"[heartbeat] Cache updated for pool={pool}")
        return {"status": "ok", "outcome": "HEARTBEAT", "pool": pool}

    # PROGRESS — TP1/TP2 milestone; log only (webhook_log already written above), no ML or DB
    if payload.outcome == "PROGRESS":
        print(f"[progress] {payload.symbol} {payload.direction} {payload.tp_stage} @ {payload.exit_price}")
        return {"status": "ok", "outcome": "PROGRESS", "stage": payload.tp_stage}

    if is_outcome:
        if payload.direction not in ("LONG", "SHORT"):
            print(f"[webhook] Ignoring outcome with direction={payload.direction!r} — not LONG/SHORT")
            return {"status": "ignored", "reason": "invalid_direction"}
        from ml_model import get_model, Features
        from ml_ensemble import get_rf, get_gbm
        from db import insert_outcome, recent_outcomes, symbol_to_pool
        sym2 = payload.symbol or "XAUUSD"

        # Recover entry_price from cache if missing/NaN-sanitized-to-zero
        import time as _time2
        if not payload.entry_price:
            _ck2 = f"{sym2.upper()}|{payload.direction}|{payload.timeframe or ''}"
            _cached2 = _entry_price_cache.get(_ck2)
            if _cached2 and (_time2.monotonic() - _cached2[5]) < _ENTRY_CACHE_TTL:
                payload.entry_price = _cached2[0]
                if not payload.tp1: payload.tp1 = _cached2[1]
                if not payload.tp2: payload.tp2 = _cached2[2]
                if not payload.tp3: payload.tp3 = _cached2[3]
                if not payload.sl:  payload.sl  = _cached2[4]
                print(f"[webhook] Recovered entry_price={payload.entry_price} from cache for {sym2} {payload.direction}")
        if not payload.exit_price and payload.tp1:
            payload.exit_price = payload.tp1
            print(f"[webhook] Used tp1={payload.tp1} as exit_price for {sym2} {payload.direction}")

        try:
            pool     = symbol_to_pool(sym2, payload.timeframe or "")
            model    = get_model(pool)
            features = Features(
                f1=payload.f1, f2=payload.f2, f3=payload.f3, f4=payload.f4,
                f5=payload.f5, f6=payload.f6, f7=payload.f7, f8=payload.f8,
                f9=payload.f9, f10=payload.f10, f11=payload.f11, f12=payload.f12,
                f13=payload.f13, f14=payload.f14, f15=payload.f15, f16=payload.f16,
                f17=payload.f17, f18=payload.f18, f19=payload.f19, f20=payload.f20,
                f21=payload.f21, f22=payload.f22, f23=payload.f23, f24=payload.f24,
                f25=payload.f25, f26=payload.f26,
            )
            # Signed realized move (favorable = positive) — lets the KNN re-classify a
            # partial that actually closed negative (e.g. SL_TP1 on gold scalps) as a loss.
            entry = payload.entry_price or 0.0
            exit_ = payload.exit_price or 0.0
            if entry and exit_:
                raw_pct = (exit_ - entry) / max(entry, 0.0001) * 100
                pnl_pct = raw_pct if payload.direction == "LONG" else -raw_pct
            else:
                pnl_pct = 0.0

            ml_label = payload.ml_outcome or payload.outcome
            _pnl_for_ml = pnl_pct if (entry and exit_) else None  # don't reclassify on missing prices
            _is_dup2 = _outcome_is_duplicate(sym2, payload.direction, payload.entry_price or 0.0, payload.exit_price or 0.0, payload.timeframe or "")
            if not _is_dup2:
                model.update_on_outcome(features, payload.direction, ml_label, tp_stage=payload.tp_stage or "", pnl=_pnl_for_ml)
            else:
                print(f"[webhook] Duplicate within {_OUTCOME_DEDUP_TTL}s — skipping weight update for {sym2} {payload.direction} entry={payload.entry_price}")

            from signal_engine import _detect_regime, _session_multiplier
            _is_stock_pool2 = not pool.startswith("XAUUSD")
            _, _session = _session_multiplier(datetime.now(timezone.utc), is_stock=_is_stock_pool2)
            _regime     = _detect_regime(features)
        except Exception as _exc:
            print(f"[webhook] ERROR processing outcome {sym2} {payload.direction} outcome={payload.outcome}: {_exc}")
            import traceback; traceback.print_exc()
            return {"status": "error", "detail": str(_exc)}
        outcome_row = {
            "symbol":        sym2,
            "direction":     payload.direction,
            "trigger":       getattr(payload, "trigger", "") or "",
            "entry_price":   entry,
            "exit_price":    exit_,
            "outcome":       payload.outcome,
            "ml_outcome":    ml_label,
            "mfe":           payload.mfe,
            "mae":           payload.mae,
            "tp_stage":      payload.tp_stage or "",
            "timeframe":     payload.timeframe or "",
            "pnl_pct":       round(pnl_pct, 4),
            "ml_bull_score": payload.ml_score,
            "regime":        _regime,
            "session":       _session,
        }
        outcome_row.update(features.as_db_dict())

        async def _persist():
            try:
                for _save_attempt in range(3):
                    try:
                        await asyncio.to_thread(model.save, pool)
                        break
                    except Exception as _se:
                        if _save_attempt < 2:
                            await asyncio.sleep(1 << _save_attempt)
                        else:
                            raise
                await asyncio.to_thread(insert_outcome, outcome_row)
                from signal_engine import invalidate_history_cache
                invalidate_history_cache(pool)
                # NOTE: RF/GBM retraining is intentionally NOT done here. sklearn fit()
                # is CPU/GIL-bound; retraining on every outcome stalled the event loop
                # during trade bursts (e.g. post-CPI) → webhook timeouts. The hourly
                # system check retrains RF+GBM for every pool, keeping models fresh
                # without blocking the webhook hot path.
                from scheduler import record_webhook_ok
                record_webhook_ok()
            except Exception as e:
                from scheduler import record_webhook_error
                record_webhook_error()
                print(f"[webhook] background persist error: {e}")
        asyncio.create_task(_persist())

        return {"status": "ok", "routed_to": "trade-outcome", "outcome": payload.outcome, "ml_outcome": ml_label}

    print(f"[webhook] Unmatched payload — tp1={payload.tp1} sl={payload.sl} trade_id={payload.trade_id} outcome={payload.outcome}")
    return {"status": "ignored", "reason": "payload did not match entry or outcome pattern"}


@app.get("/weights")
async def get_weights(secret: str = "", pool: str = "XAUUSD_2M"):
    _validate_secret(secret)
    if pool not in VALID_POOLS:
        raise HTTPException(status_code=400, detail=f"Unknown pool '{pool}'. Valid: {sorted(VALID_POOLS)}")
    from ml_model import get_model
    model = get_model(pool)
    top3 = model.top_features(3)
    return {
        "pool":         pool,
        "weights":      {f"w{i+1}": round(w, 4) for i, w in enumerate(model.weights)},
        "total_wins":   model._total_wins,
        "total_losses": model._total_losses,
        "win_rate":     round(model.win_rate * 100, 1),
        "top_features": [{"name": n, "weight": round(w, 4)} for n, w in top3],
    }


@app.get("/feature-importance")
async def feature_importance(secret: str = "", pool: str = "XAUUSD_2M"):
    _validate_secret(secret)
    if pool not in VALID_POOLS:
        raise HTTPException(status_code=400, detail=f"Unknown pool '{pool}'. Valid: {sorted(VALID_POOLS)}")
    from ml_model import get_model, FEATURE_NAMES
    from ml_ensemble import get_rf

    model = get_model(pool)
    rf    = get_rf(pool)

    knn_top = model.top_features(5)
    rf_top  = rf.top_features(5)

    knn_weights = model.weights
    knn_max     = max(knn_weights) if knn_weights else 1.0
    knn_norm    = [w / knn_max for w in knn_weights]

    rf_imps  = rf.feature_importances
    rf_max   = max(rf_imps) if rf_imps else 1.0
    rf_norm  = [v / rf_max for v in rf_imps]

    combined = []
    for i, name in enumerate(FEATURE_NAMES):
        combined.append({
            "feature":        name,
            "knn_weight":     round(knn_weights[i], 4),
            "knn_weight_norm": round(knn_norm[i], 4),
            "rf_importance":  round(rf_imps[i], 4),
            "rf_importance_norm": round(rf_norm[i], 4),
            "combined_score": round((knn_norm[i] + rf_norm[i]) / 2.0, 4),
        })

    combined.sort(key=lambda x: x["combined_score"], reverse=True)

    return {
        "rf_trained":        rf.is_trained,
        "knn_top_features":  [{"name": n, "weight": round(w, 4)} for n, w in knn_top],
        "rf_top_features":   [{"name": n, "importance": round(v, 4)} for n, v in rf_top],
        "combined_ranking":  combined,
    }


@app.get("/test-session-report")
async def test_session_report(secret: str = ""):
    _validate_secret(secret)
    from telegram_bot import send_stocks_session_report
    sent = await send_stocks_session_report()
    return {"status": "sent" if sent else "no_trades_today"}


@app.get("/signals/feed")
async def signals_feed(secret: str = "", limit: int = 50):
    """Return the last N triggered entry signals (same data sent to Telegram)."""
    _validate_secret(secret)
    feed = list(reversed(_signal_feed[-limit:]))
    return {"signals": feed, "count": len(feed)}


@app.get("/errors")
async def errors_log(secret: str = "", limit: int = 50):
    """Return the last N backend errors recorded to data/error_log.json."""
    _validate_secret(secret)
    from db import _get_file, _ERROR_LOG_PATH
    log, _ = await asyncio.to_thread(_get_file, _ERROR_LOG_PATH)
    if not isinstance(log, list):
        log = []
    return {"errors": list(reversed(log[-limit:])), "count": len(log)}


@app.get("/owner/test")
async def owner_test(secret: str = "", message: str = ""):
    """Send a test 'Mohamed —' direct message to the personal Telegram to confirm
    the owner-communication channel + format work."""
    _validate_secret(secret)
    from telegram_bot import send_owner_message
    body = message or ("channel test — this is how I'll reach you when something "
                       "needs a manual step (paste Pine, allow-list a host, run an endpoint).")
    ok = await send_owner_message(body, action="reply here or in chat if you got this.")
    return {"sent": ok}


# Strong refs to detached background tasks so the event loop doesn't GC them mid-run.
_BACKGROUND_TASKS: set = set()


@app.get("/backtest")
async def backtest(secret: str = "", symbols: str = "", timeframes: str = "", days: int = 120):
    """Run the Polygon intraday forward backtest (AI MLM 26 reproduction).
    Reproduces features F1..F26 + KNN + RQ kernel, grades ATR TP/SL bar-by-bar,
    summarizes per symbol/timeframe, and persists to data/backtest_results.json."""
    _validate_secret(secret)
    import polygon_intraday_backtest as pbt
    syms = [s.strip() for s in symbols.split(",") if s.strip()] or None
    tfs = [t.strip() for t in timeframes.split(",") if t.strip()] or None
    # Fire-and-forget: the backtest takes minutes (months of bars × KNN per bar),
    # far longer than an HTTP request survives. Launch it in the background — it
    # persists incrementally to data/backtest_results.json — and return at once.
    task = asyncio.create_task(asyncio.to_thread(pbt.run, syms, tfs, days))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return {"status": "started",
            "note": "Backtest running in background. Results stream into "
                    "data/backtest_results.json (status: running → complete).",
            "params": {"symbols": syms or "default", "timeframes": tfs or "default",
                       "days": days}}


@app.get("/signals/levels")
async def signals_levels(secret: str = ""):
    """Return cached entry/TP/SL levels per symbol+direction+timeframe."""
    _validate_secret(secret)
    import time as _time
    now = _time.monotonic()
    out = []
    for key, val in list(_entry_price_cache.items()):
        sym, direction, tf = key.split("|", 2)
        entry, tp1, tp2, tp3, sl, ts = val
        age_min = round((now - ts) / 60, 1)
        if age_min > 240:
            continue
        out.append({
            "key":       key,
            "symbol":    sym,
            "direction": direction,
            "timeframe": tf,
            "entry":     entry or None,
            "tp1":       tp1 or None,
            "tp2":       tp2 or None,
            "tp3":       tp3 or None,
            "sl":        sl  or None,
            "age_min":   age_min,
        })
    out.sort(key=lambda x: x["age_min"])
    return {"levels": out}


@app.get("/signal/now")
async def signal_now(secret: str = ""):
    _validate_secret(secret)
    from scheduler import _news_signal_cycle
    asyncio.create_task(_news_signal_cycle())
    return {"status": "signal cycle triggered"}


@app.get("/swing/now")
async def swing_now(secret: str = ""):
    """Run the swing screen + brief immediately (ignores the holiday gate)."""
    _validate_secret(secret)

    async def _run():
        from swing_screener import run_screen
        from telegram_bot import send_swing_brief
        screen = await asyncio.to_thread(run_screen, 10)
        await send_swing_brief(screen)

    asyncio.create_task(_run())
    return {"status": "swing screen triggered"}


@app.get("/swing/candidates")
async def swing_candidates(secret: str = ""):
    """Latest cached swing candidates (no rescan), flattened for the dashboard:
    surfaces fundamental/technical scores, ATR levels, conviction and the
    fundamentals+technical 'qualified' flag."""
    _validate_secret(secret)
    from swing_screener import get_candidates
    data = get_candidates() or {}
    out = []
    for c in (data.get("candidates") or []):
        f  = c.get("fundamental") or {}
        t  = c.get("technical")   or {}
        cs = c.get("combined_score", 0) or 0
        conv = ("STRONG" if cs >= 0.50 else "GOOD" if cs >= 0.35
                else "MODERATE" if cs >= 0.15 else "WEAK")
        fs, ts = f.get("score"), t.get("score")
        out.append({
            "ticker":            c.get("ticker"),
            "combined_score":    cs,
            "fundamental_score": fs,
            "technical_score":   ts,
            "entry":             t.get("entry"),
            "tp":                t.get("t1"),
            "sl":                t.get("stop"),
            "rsi":               t.get("rsi"),
            "trend":             t.get("trend"),
            "conviction":        conv,
            "qualified":         c.get("qualified", bool((fs or 0) > 0 and (ts or 0) > 0)),
            "thesis":            c.get("thesis"),
            # full nested objects for the dashboard
            "fundamental":       f,
            "technical":         t,
            "upside_pct":        c.get("upside_pct"),
            "analyst_target":    c.get("analyst_target"),
            "current_price":     c.get("current_price"),
            "entry_quality":     c.get("entry_quality") or t.get("entry_quality"),
            "entry_now":         c.get("entry_now") or t.get("entry_now", False),
            "upside_source":     c.get("upside_source"),
        })

    # Watchlist: WAIT-quality stocks that passed Gate 1 (good value, not yet timed)
    watch_out = []
    for c in (data.get("watchlist") or []):
        f = c.get("fundamental") or {}
        t = c.get("technical")   or {}
        watch_out.append({
            "ticker":        c.get("ticker"),
            "combined_score": c.get("combined_score"),
            "upside_pct":    c.get("upside_pct"),
            "upside_source": c.get("upside_source"),
            "entry_quality": "WAIT",
            "rsi":           t.get("rsi"),
            "trend":         t.get("trend"),
            "entry":         t.get("entry"),
            "stop":          t.get("stop"),
            "t1":            t.get("t1"),
            "fundamental":   f,
            "technical":     t,
        })

    return {
        "candidates":      out,
        "watchlist":       watch_out,
        "watching":        data.get("watching", 0),
        "qualified_count": data.get("qualified_count"),
        "scanned":         data.get("scanned"),
        "updated_at":      data.get("updated_at"),
    }


@app.get("/swing/trades")
async def swing_trades(secret: str = ""):
    """Swing paper-trade training-readiness summary (open/closed/win-rate)."""
    _validate_secret(secret)
    from swing_tracker import stats
    return stats()


@app.get("/options/trades")
async def options_trades(secret: str = ""):
    """SPX 0-1DTE options paper-trade training-readiness summary per pool."""
    _validate_secret(secret)
    from options_engine import stats as options_stats
    return options_stats()


@app.get("/swing/one")
async def swing_one(ticker: str = "", secret: str = "", send: bool = False):
    """
    On-demand single-stock swing read — full fundamental + technical + combined
    score plus the synthesized thesis, for any ticker regardless of rank.
    Pass send=true to also push the formatted brief to the swing Telegram channel.
    Example: /swing/one?ticker=META&secret=...&send=true
    """
    _validate_secret(secret)
    tkr = (ticker or "").strip().upper()
    if not tkr:
        return {"error": "ticker query param required, e.g. ?ticker=META"}
    from swing_screener import screen_one
    from swing_narrative import synthesize, available
    cand = await asyncio.to_thread(screen_one, tkr)
    cand["thesis"] = await asyncio.to_thread(synthesize, cand)
    cand["llm_active"] = available()
    if send:
        from telegram_bot import send_swing_brief
        cand["telegram_sent"] = await send_swing_brief({"candidates": [cand], "scanned": 1})
    return cand


@app.get("/inspect")
async def inspect_now(secret: str = ""):
    """Run the full system inspection on demand and return the structured report."""
    _validate_secret(secret)
    from scheduler import _full_system_inspection
    report = await _full_system_inspection()
    return report


@app.get("/daily-brief")
async def daily_brief_now(secret: str = ""):
    """Trigger daily market brief for SPY/QQQ/XAUUSD immediately and send to Telegram."""
    _validate_secret(secret)
    from scheduler import _daily_market_brief
    asyncio.create_task(_daily_market_brief())
    return {"status": "daily brief triggered — check Telegram in ~15 seconds"}


@app.get("/daily-report")
async def daily_report_now(secret: str = ""):
    """Trigger end-of-day performance report immediately and send to Telegram."""
    _validate_secret(secret)
    from scheduler import _daily_trade_count_report
    asyncio.create_task(_daily_trade_count_report())
    return {"status": "daily performance report triggered — check Telegram in ~15 seconds"}


@app.get("/railway-status")
async def railway_status(secret: str = ""):
    _validate_secret(secret)
    if not RAILWAY_API_TOKEN:
        return {"error": "RAILWAY_API_TOKEN not set"}

    import httpx, traceback

    headers = {
        "Authorization": f"Bearer {RAILWAY_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        deploy_query = """
        query($serviceId: String!, $projectId: String!) {
          deployments(
            first: 1
            input: { serviceId: $serviceId, projectId: $projectId }
          ) {
            edges {
              node {
                id
                status
                createdAt
                meta
              }
            }
          }
        }
        """
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://backboard.railway.app/graphql/v2",
                headers=headers,
                json={
                    "query": deploy_query,
                    "variables": {
                        "serviceId": RAILWAY_SERVICE_ID,
                        "projectId": RAILWAY_PROJECT_ID,
                    },
                },
            )
        d = r.json()
        deployments = (d.get("data") or {}).get("deployments", {}).get("edges", [])

        if not deployments:
            return {"error": "No deployments found", "raw": d}

        deploy = deployments[0]["node"]
        deploy_id = deploy["id"]

        logs_query = """
        query($deploymentId: String!) {
          deploymentLogs(deploymentId: $deploymentId, limit: 30) {
            timestamp
            message
            severity
          }
        }
        """
        async with httpx.AsyncClient(timeout=30) as client:
            r2 = await client.post(
                "https://backboard.railway.app/graphql/v2",
                headers=headers,
                json={
                    "query": logs_query,
                    "variables": {"deploymentId": deploy_id},
                },
            )
        l = r2.json()
        logs = (l.get("data") or {}).get("deploymentLogs", [])

        return {
            "deployment": {
                "id":        deploy_id,
                "status":    deploy["status"],
                "createdAt": deploy["createdAt"],
            },
            "logs": [
                f"[{lg.get('severity','INFO')}] {lg.get('timestamp','')} {lg.get('message','')}"
                for lg in logs[-30:]
            ],
            "log_errors": l.get("errors"),
        }

    except Exception as e:
        return {"error": str(e), "trace": traceback.format_exc()[-500:]}


@app.get("/dashboard")
async def dashboard(secret: str = "", pool: str = "XAUUSD_2M"):
    _validate_secret(secret)
    if pool not in VALID_POOLS:
        raise HTTPException(status_code=400, detail=f"Unknown pool '{pool}'. Valid: {sorted(VALID_POOLS)}")
    from ml_model import get_model
    from ml_ensemble import get_rf
    from db import recent_outcomes, recent_news
    from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event

    model = get_model(pool)
    rf    = get_rf(pool)
    recent_trades     = recent_outcomes(pool, limit=10)
    recent_news_items = recent_news(hours=4)
    top3              = model.top_features(3)

    return {
        "pool": pool,
        "model": {
            "weights":      {f"w{i+1}": round(w, 4) for i, w in enumerate(model.weights)},
            "win_rate":     round(model.win_rate * 100, 1),
            "total_trades": model._total_wins + model._total_losses,
            "top_features": [{"name": n, "weight": round(w, 4)} for n, w in top3],
        },
        "rf": {
            "trained":      rf.is_trained,
            "top_features": [{"name": n, "importance": round(v, 4)} for n, v in rf.top_features(3)],
        },
        "news_sentiment":    round(get_latest_news_sentiment(), 4),
        "news_velocity":     get_latest_velocity(),
        "high_impact_event": get_latest_event(),
        "recent_news_count": len(recent_news_items),
        "recent_trades": [
            {"direction": t["direction"], "outcome": t["outcome"], "created_at": t["created_at"]}
            for t in recent_trades
        ],
    }


# ── PWA endpoints ─────────────────────────────────────────────────────────────

_GOLD_POOLS   = ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_15M", "XAUUSD_30M", "XAUUSD_1H"]
_STOCK_POOLS  = [
    "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M",
    "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",
    "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",
    "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",
    "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",
]


def _session_now() -> str:
    h = datetime.now(timezone.utc).hour
    if 7 <= h < 16:
        return "london" if h < 12 else "ny"
    if 0 <= h < 7:
        return "asian"
    return "off"


@app.get("/pulse")
async def pulse():
    from ml_model     import get_model
    from ml_ensemble  import get_rf, get_gbm
    from db           import recent_outcomes
    from scheduler    import get_latest_news_sentiment, get_latest_velocity, get_latest_event
    from market_macro import get_macro_bias, get_equity_macro_bias

    pools_out: dict = {}
    gold_scores:  list[float] = []
    stock_scores: list[float] = []

    for pool in _GOLD_POOLS + _STOCK_POOLS:
        try:
            model = get_model(pool)
            rf    = get_rf(pool)
            gbm   = get_gbm(pool)
            # Use cached last signal from signals.json to avoid re-computing features
            from db import _get_file as _db_get
            sigs, _ = _db_get("data/signals.json")
            last_sig = next(
                (s for s in reversed(sigs or []) if s.get("pool") == pool),
                None
            )
            if last_sig:
                direction  = last_sig.get("direction", "NEUTRAL")
                confidence = last_sig.get("confidence", 0.0)
                ml_score   = last_sig.get("rf_score") or last_sig.get("ml_score") or 0.0
                certainty  = last_sig.get("ml_certainty", "")
            else:
                direction, confidence, ml_score, certainty = "NEUTRAL", 0.0, 0.0, ""
            pools_out[pool] = {
                "direction":  direction,
                "confidence": round(float(confidence), 3),
                "ml_score":   round(float(ml_score), 3),
                "certainty":  certainty,
            }
            # Directional score for aggregate bias
            score = float(confidence) if direction == "LONG" else (-float(confidence) if direction == "SHORT" else 0.0)
            if pool in _GOLD_POOLS:
                gold_scores.append(score)
            else:
                stock_scores.append(score)
        except Exception:
            pools_out[pool] = {"direction": "NEUTRAL", "confidence": 0.0, "ml_score": 0.0, "certainty": ""}

    def _bias(scores: list[float]) -> tuple[str, float]:
        if not scores:
            return "NEUTRAL", 0.0
        avg = sum(scores) / len(scores)
        label = "BULLISH" if avg > 0.05 else ("BEARISH" if avg < -0.05 else "NEUTRAL")
        return label, round(avg, 3)

    gold_bias,   gold_score   = _bias(gold_scores)
    stocks_bias, stocks_score = _bias(stock_scores)
    all_scores = gold_scores + stock_scores
    overall_bias, _ = _bias(all_scores)

    macro_gold   = get_macro_bias()   or {}
    macro_equity = get_equity_macro_bias() or {}

    try:
        from fear_greed import get_fear_greed
        fg = get_fear_greed()
    except Exception:
        fg = {}

    return {
        "gold_bias":    gold_bias,
        "gold_score":   gold_score,
        "stocks_bias":  stocks_bias,
        "stocks_score": stocks_score,
        "overall_bias": overall_bias,
        "session":      _session_now(),
        "next_event":   get_latest_event(),
        "pools":        pools_out,
        "macro_bias":   round(float(macro_gold.get("bias") or 0.0), 3),
        "macro_label":  macro_gold.get("label", ""),
        "vix":          macro_equity.get("vix"),
        "fear_greed":       fg.get("score"),
        "fear_greed_label": fg.get("label"),
        "news_velocity": get_latest_velocity(),
        "updated_at":   datetime.now(timezone.utc).isoformat(),
    }


@app.get("/news/feed")
async def news_feed(secret: str = ""):
    _validate_secret(secret)
    from db        import recent_news
    from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event

    items_raw = recent_news(hours=24)
    items_raw.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)
    items: list[dict] = []
    for n in items_raw[:20]:
        s = float(n.get("sentiment", 0.0) or 0.0)
        if s > 0.1:
            sent_label = "BULLISH"
        elif s < -0.1:
            sent_label = "BEARISH"
        else:
            sent_label = "NEUTRAL"
        try:
            from datetime import datetime as _dt
            dt  = _dt.fromisoformat(n["fetched_at"].replace("Z", "+00:00"))
            age = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
        except Exception:
            age = 0
        items.append({
            "headline":  n.get("title", n.get("headline", "")),
            "source":    n.get("source", ""),
            "sentiment": sent_label,
            "score":     round(s, 3),
            "age_min":   age,
            "url":       n.get("url", ""),
        })

    return {
        "items":             items,
        "velocity":          get_latest_velocity().get("label", "NORMAL"),
        "agg_score":         round(float(get_latest_news_sentiment()), 3),
        "high_impact_event": get_latest_event(),
    }


@app.post("/push/subscribe")
async def push_subscribe(request: Request, secret: str = ""):
    _validate_secret(secret)
    from db import _get_file, _put_file
    body = await request.json()
    sub  = body.get("subscription")
    if not sub:
        raise HTTPException(status_code=400, detail="Missing subscription")
    subs, sha = _get_file("data/push_subscriptions.json")
    subs = subs or []
    endpoint = sub.get("endpoint", "")
    if not any(s.get("endpoint") == endpoint for s in subs):
        subs.append(sub)
        _put_file("data/push_subscriptions.json", subs, sha, "data: new push subscription")
    return {"ok": True, "total": len(subs)}


@app.get("/brief/data")
async def brief_data(secret: str = ""):
    _validate_secret(secret)
    from daily_analysis import _technical_context, _load_from_json, _fetch_todays_high_impact_events, _ff_calendar_events, _finnhub_calendar_events
    from market_macro import get_macro_bias, get_equity_macro_bias
    from scheduler import get_latest_event, get_latest_velocity, get_latest_news_sentiment
    from datetime import datetime as _dt, timezone as _tz

    now = _dt.now(_tz.utc)

    # Technical context per asset
    assets_out = {}
    for name, decimals in [("XAUUSD", 2), ("SPY", 2), ("QQQ", 2)]:
        try:
            tc = _technical_context(name, decimals)
            if tc:
                assets_out[name] = tc
        except Exception as e:
            assets_out[name] = {"error": str(e)}

    # Pivot levels from GitHub Actions
    try:
        levels_raw = _load_from_json()
    except Exception:
        levels_raw = {}

    # Today's economic events
    try:
        events_str = _fetch_todays_high_impact_events()
    except Exception:
        events_str = ""

    # Calendar events as structured list
    try:
        cal = _finnhub_calendar_events(now) + _ff_calendar_events(now)
        cal.sort(key=lambda x: x[0])
        events_list = [{"time_dubai": t, "name": n, "impact": imp} for t, n, imp in cal[:10]]
    except Exception:
        events_list = []

    macro  = get_macro_bias()        or {}
    equity = get_equity_macro_bias() or {}

    return {
        "generated_at": now.isoformat(),
        "assets":       assets_out,
        "levels":       levels_raw,
        "events_text":  events_str,
        "events_list":  events_list,
        "macro": {
            "bias":        macro.get("bias", 0.0),
            "label":       macro.get("label", ""),
            "components":  macro.get("components", {}),
            "vix":         equity.get("vix"),
            "real_yield":  macro.get("components", {}).get("real_yield"),
            "dxy":         macro.get("components", {}).get("dxy"),
        },
        "news_sentiment": get_latest_news_sentiment(),
        "news_velocity":  get_latest_velocity(),
        "next_event":     get_latest_event(),
    }


# ── Market data endpoints ────────────────────────────────────────────────────
_OVERVIEW_SYMBOLS = {
    "Indices":    {"S&P 500":"^GSPC","NASDAQ":"^IXIC","Dow Jones":"^DJI","Russell 2000":"^RUT","VIX":"^VIX"},
    "Commodities":{"Gold":"GC=F","Oil (WTI)":"CL=F","Silver":"SI=F","Natural Gas":"NG=F"},
    "Crypto":     {"Bitcoin":"BTC-USD","Ethereum":"ETH-USD"},
    "Bonds":      {"10Y Yield":"^TNX","2Y Yield":"^IRX"},
}
_overview_cache = {"ts": 0, "data": None}

_OVERVIEW_STOOQ = {
    "^GSPC": "^spx", "^IXIC": "^ndq", "^DJI": "^dji", "^RUT": "^rut",
    "^VIX": "^vix", "GC=F": "xauusd", "CL=F": "cl.f", "SI=F": "si.f",
    "NG=F": "ng.f", "BTC-USD": "btcusd", "ETH-USD": "ethusd",
    "^TNX": "^tnx", "^IRX": "^irx",
}

def _stooq_quote(sym: str) -> dict | None:
    """Last close from Stooq daily data — used for indices/commodities/crypto."""
    from market_data import _stooq_daily
    stooq_sym = _OVERVIEW_STOOQ.get(sym)
    if not stooq_sym:
        return None
    try:
        df = _stooq_daily(stooq_sym)
        if len(df) < 2:
            return None
        price = float(df["Close"].iloc[-1])
        prev  = float(df["Close"].iloc[-2])
        hi    = float(df["High"].iloc[-1]) if "High" in df.columns else None
        lo    = float(df["Low"].iloc[-1])  if "Low"  in df.columns else None
        chg   = price - prev
        return {"price": round(price, 4), "change": round(chg, 4),
                "change_pct": round(chg / prev * 100 if prev else 0, 2),
                "day_high": hi, "day_low": lo}
    except Exception:
        return None


def _finnhub_quote(sym: str) -> dict | None:
    """Live quote from Finnhub for US equities."""
    import httpx, os
    fk = os.environ.get("FINNHUB_KEY", "")
    if not fk:
        return None
    try:
        r = httpx.get("https://finnhub.io/api/v1/quote",
                      params={"symbol": sym, "token": fk}, timeout=8)
        if r.status_code != 200:
            return None
        d = r.json()
        price = d.get("c")
        prev  = d.get("pc")
        if not price:
            return None
        chg = price - (prev or price)
        return {"price": round(price, 4), "change": round(chg, 4),
                "change_pct": round(chg / prev * 100 if prev else 0, 2),
                "day_high": d.get("h"), "day_low": d.get("l")}
    except Exception:
        return None


@app.get("/market/overview")
def market_overview(secret: str = ""):
    _validate_secret(secret)
    import time
    if time.time() - _overview_cache["ts"] < 60 and _overview_cache["data"]:
        return _overview_cache["data"]
    out = {}
    all_syms = [(grp, name, sym) for grp, items in _OVERVIEW_SYMBOLS.items() for name, sym in items.items()]
    for grp, name, sym in all_syms:
        q = _stooq_quote(sym) or _finnhub_quote(sym)
        if q:
            out.setdefault(grp, []).append({"name": name, "symbol": sym, **q})
        else:
            out.setdefault(grp, []).append({"name": name, "symbol": sym, "error": "no data"})
    _overview_cache.update({"ts": time.time(), "data": out})
    return out


@app.get("/market/quotes")
async def market_quotes(symbols: str = "", secret: str = ""):
    _validate_secret(secret)
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not syms:
        return {}
    result = {}
    for sym in syms:
        q = _stooq_quote(sym) or _finnhub_quote(sym)
        if q:
            result[sym] = {**q, "name": sym}
        else:
            result[sym] = {"error": "no data"}
    return result


@app.get("/market/ticker/{symbol}")
def market_ticker(symbol: str, secret: str = ""):
    _validate_secret(secret)
    import httpx, os, datetime as _dtt
    sym = symbol.upper()
    fk = os.environ.get("FINNHUB_KEY", "")

    profile, metrics, quote_raw = {}, {}, {}
    if fk:
        try:
            r = httpx.get("https://finnhub.io/api/v1/stock/profile2",
                          params={"symbol": sym, "token": fk}, timeout=8)
            if r.status_code == 200:
                profile = r.json() or {}
        except Exception:
            pass
        try:
            r = httpx.get("https://finnhub.io/api/v1/stock/metric",
                          params={"symbol": sym, "metric": "all", "token": fk}, timeout=8)
            if r.status_code == 200:
                metrics = (r.json() or {}).get("metric", {})
        except Exception:
            pass
        try:
            r = httpx.get("https://finnhub.io/api/v1/quote",
                          params={"symbol": sym, "token": fk}, timeout=8)
            if r.status_code == 200:
                quote_raw = r.json() or {}
        except Exception:
            pass

    price  = quote_raw.get("c") or 0.0
    prev   = quote_raw.get("pc") or price
    fi = {
        "price":       round(price, 4),
        "change_pct":  round((price - prev) / prev * 100 if prev else 0, 2),
        "day_high":    quote_raw.get("h"),
        "day_low":     quote_raw.get("l"),
        "week52_high": metrics.get("52WeekHigh"),
        "week52_low":  metrics.get("52WeekLow"),
        "market_cap":  (profile.get("marketCapitalization") or 0) * 1e6 or None,
        "volume":      metrics.get("3MonthADTV"),
    }
    fundamentals = {
        "pe":             metrics.get("peBasicExclExtraTTM"),
        "forward_pe":     metrics.get("peNormalizedAnnual"),
        "pb":             metrics.get("pbAnnual"),
        "ps":             metrics.get("psTTM"),
        "ev_ebitda":      metrics.get("evEbitdaTTM"),
        "roe":            metrics.get("roeTTM"),
        "revenue_growth": metrics.get("revenueGrowthTTMYoy"),
        "gross_margin":   metrics.get("grossMarginTTM"),
        "profit_margin":  metrics.get("netProfitMarginTTM"),
        "debt_to_equity": metrics.get("totalDebt/totalEquityAnnual"),
        "dividend_yield": metrics.get("dividendYieldIndicatedAnnual"),
        "beta":           metrics.get("beta"),
        "sector":         profile.get("finnhubIndustry"),
        "industry":       profile.get("finnhubIndustry"),
        "description":    (profile.get("description") or "")[:500],
    }
    news = []
    if fk:
        try:
            r = httpx.get("https://finnhub.io/api/v1/company-news",
                          params={"symbol": sym,
                                  "from": (_dtt.date.today() - _dtt.timedelta(days=7)).isoformat(),
                                  "to": _dtt.date.today().isoformat(),
                                  "token": fk}, timeout=8)
            if r.status_code == 200:
                news = [{"headline": n["headline"], "url": n["url"], "datetime": n["datetime"]}
                        for n in r.json()[:8]]
        except Exception:
            pass
    return {"symbol": sym, "name": profile.get("name", sym), "price_data": fi,
            "fundamentals": fundamentals, "news": news}


@app.get("/market/compare")
def market_compare(symbols: str = "", secret: str = ""):
    _validate_secret(secret)
    import httpx, os
    fk = os.environ.get("FINNHUB_KEY", "")
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()][:6]
    if not syms:
        return []
    result = []
    for sym in syms:
        try:
            profile, metrics, q = {}, {}, {}
            if fk:
                try:
                    r = httpx.get("https://finnhub.io/api/v1/stock/profile2",
                                  params={"symbol": sym, "token": fk}, timeout=8)
                    if r.status_code == 200:
                        profile = r.json() or {}
                except Exception:
                    pass
                try:
                    r = httpx.get("https://finnhub.io/api/v1/stock/metric",
                                  params={"symbol": sym, "metric": "all", "token": fk}, timeout=8)
                    if r.status_code == 200:
                        metrics = (r.json() or {}).get("metric", {})
                except Exception:
                    pass
                try:
                    r = httpx.get("https://finnhub.io/api/v1/quote",
                                  params={"symbol": sym, "token": fk}, timeout=8)
                    if r.status_code == 200:
                        q = r.json() or {}
                except Exception:
                    pass
            price = q.get("c") or 0.0
            prev  = q.get("pc") or price
            result.append({
                "symbol":       sym,
                "name":         profile.get("name", sym),
                "price":        round(price, 2),
                "change_pct":   round((price - prev) / prev * 100 if prev else 0, 2),
                "market_cap":   (profile.get("marketCapitalization") or 0) * 1e6 or None,
                "pe":           metrics.get("peBasicExclExtraTTM"),
                "forward_pe":   metrics.get("peNormalizedAnnual"),
                "pb":           metrics.get("pbAnnual"),
                "roe":          metrics.get("roeTTM"),
                "revenue_growth": metrics.get("revenueGrowthTTMYoy"),
                "gross_margin": metrics.get("grossMarginTTM"),
                "beta":         metrics.get("beta"),
                "dividend_yield": metrics.get("dividendYieldIndicatedAnnual"),
                "sector":       profile.get("finnhubIndustry"),
                "week52_high":  metrics.get("52WeekHigh"),
                "week52_low":   metrics.get("52WeekLow"),
            })
        except Exception as e:
            result.append({"symbol": sym, "error": str(e)})
    return result


_wrap_cache = {"date": None, "text": None, "sections": None}

@app.get("/market/wrap")
def market_wrap(secret: str = ""):
    _validate_secret(secret)
    import anthropic, os, datetime as _dtt
    today = str(_dtt.date.today())
    if _wrap_cache["date"] == today and _wrap_cache["text"]:
        return {"date": today, "wrap": _wrap_cache["text"], "sections": _wrap_cache["sections"], "cached": True}
    try:
        from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event
        from market_macro import get_macro_bias, get_equity_macro_bias
        macro   = get_macro_bias()        or {}
        equity  = get_equity_macro_bias() or {}
        sentiment = get_latest_news_sentiment()
        velocity  = get_latest_velocity()
        event     = get_latest_event()
        ctx = f"Date: {today}\nGold macro bias: {macro.get('label','N/A')} ({macro.get('bias',0):.2f})\nEquity macro: {equity.get('label','N/A')}\nVIX: {equity.get('vix','N/A')}\nNews sentiment: {sentiment:.3f}\nNews velocity: {velocity}\nNext key event: {event}"
    except Exception as e:
        ctx = f"Date: {today}. Market data unavailable: {e}"
    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            messages=[{"role":"user","content":f"""Write a professional daily market wrap-up commentary for a trading dashboard. Be concise, insightful, data-driven. Use this context:\n{ctx}\n\nStructure: 3 sections — (1) Market Overview (2-3 sentences on overall tone), (2) Key Themes (bullet points on major drivers/risks), (3) Outlook (1-2 sentences forward-looking). Keep each section tight. No fluff."""}]
        )
        text = msg.content[0].text
        sections = {"overview": "", "themes": [], "outlook": ""}
        lines = text.split("\n")
        current = None
        for line in lines:
            ll = line.lower().strip()
            if "market overview" in ll or "overview" in ll:
                current = "overview"
            elif "key theme" in ll or "theme" in ll:
                current = "themes"
            elif "outlook" in ll:
                current = "outlook"
            elif current == "overview" and line.strip():
                sections["overview"] += " " + line.strip()
            elif current == "themes" and line.strip().startswith(("-","•","*","1","2","3","4","5")):
                sections["themes"].append(line.strip().lstrip("-•* 1234567890.").strip())
            elif current == "outlook" and line.strip():
                sections["outlook"] += " " + line.strip()
        _wrap_cache.update({"date": today, "text": text, "sections": sections})
        return {"date": today, "wrap": text, "sections": sections, "cached": False}
    except Exception as e:
        return {"date": today, "wrap": f"Market wrap unavailable: {e}", "sections": None, "cached": False}


_commentary_cache = {"date": None, "text": None}

def _build_commentary_context() -> dict:
    """Gather per-asset technicals + pivot levels + macro/fundamental backdrop
    for a professional, numbers-and-levels market commentary."""
    from daily_analysis import _technical_context, _load_from_json, _fetch_live_price
    from market_macro import get_macro_bias, get_equity_macro_bias
    from scheduler import get_latest_news_sentiment

    try:
        levels_raw = _load_from_json()
    except Exception:
        levels_raw = {}

    assets = {}
    for name, dec in [("XAUUSD", 2), ("SPY", 2), ("QQQ", 2)]:
        try:
            tc = _technical_context(name, dec) or {}
        except Exception:
            tc = {}
        try:
            price = _fetch_live_price(name, dec)
        except Exception:
            price = None
        assets[name] = {"tc": tc, "lv": levels_raw.get(name, {}) or {}, "price": price}

    macro  = get_macro_bias()        or {}
    macro_c = macro.get("components", {}) or {}
    equity = get_equity_macro_bias() or {}
    try:
        news = get_latest_news_sentiment()
    except Exception:
        news = 0.0
    return {
        "assets": assets,
        "macro": {
            "label":      macro.get("label", "?"),
            "bias":       macro.get("bias", 0.0),
            "real_yield": macro_c.get("real_yield"),
            "dxy":        macro_c.get("dxy"),
            "vix":        equity.get("vix"),
            "equity_label": equity.get("label", "?"),
            "news":       news,
        },
    }


def _commentary_lines(ctx: dict) -> list[str]:
    """Deterministic, data-rich commentary used as the LLM prompt source AND as a
    graceful fallback when no LLM key is present — always cites real numbers/levels."""
    names = {"XAUUSD": "Gold", "SPY": "S&P 500 (SPY)", "QQQ": "Nasdaq 100 (QQQ)"}
    lines = []
    for key, label in names.items():
        a = ctx["assets"].get(key, {})
        tc, lv, price = a.get("tc", {}), a.get("lv", {}), a.get("price")
        if not tc:
            continue
        px = f"${price:,.2f}" if isinstance(price, (int, float)) else "—"
        seg = (f"{label}: {px} · {tc.get('direction','?')} {tc.get('bias_pct','?')}% "
               f"({tc.get('trend','?')}, RSI {tc.get('rsi','?')} {tc.get('rsi_band','')}, "
               f"20d mom {tc.get('mom20','?')}%). MAs 20/50/200 = "
               f"{tc.get('ma20','n/a')}/{tc.get('ma50','n/a')}/{tc.get('ma200','n/a')}.")
        if lv.get("pivot") is not None:
            seg += (f" Pivot {lv.get('pivot')}; R {lv.get('r1')}/{lv.get('r2')}, "
                    f"S {lv.get('s1')}/{lv.get('s2')}. ATR {tc.get('atr','?')}.")
        lines.append(seg)
    m = ctx["macro"]
    macro_bits = [f"Backdrop: {m['equity_label']} equities"]
    if m.get("vix") is not None:        macro_bits.append(f"VIX {m['vix']}")
    if m.get("real_yield") is not None: macro_bits.append(f"10y real yield {m['real_yield']}%")
    if m.get("dxy") is not None:        macro_bits.append(f"DXY {m['dxy']}")
    macro_bits.append(f"gold macro {m['label']} ({m['bias']:+.2f})")
    macro_bits.append(f"news sentiment {m['news']:+.2f}")
    lines.append(" · ".join(macro_bits) + ".")
    return lines


@app.get("/market/commentary")
def market_commentary(secret: str = ""):
    _validate_secret(secret)
    import anthropic, os, datetime as _dtt
    today = str(_dtt.date.today())
    if _commentary_cache["date"] == today and _commentary_cache["text"]:
        return {"date": today, "commentary": _commentary_cache["text"], "cached": True}

    try:
        ctx = _build_commentary_context()
        data_lines = _commentary_lines(ctx)
    except Exception as e:
        return {"date": today, "commentary": f"Commentary unavailable: {e}", "cached": False}

    data_block = "\n".join(data_lines)
    prompt = (
        f"You are a senior markets desk strategist. Using ONLY the data below for {today}, write a concise, "
        "professional market commentary (3 short paragraphs). Paragraph 1: the cross-market read and the macro/"
        "fundamental backdrop (real yields, the dollar, VIX, risk tone). Paragraph 2: the technical posture for gold "
        "and the equity indices — trend, momentum and RSI. Paragraph 3: the key actionable levels to watch today "
        "(cite specific pivot, support and resistance numbers). Reference concrete numbers and price levels throughout. "
        "Be direct and analytical, no hedging or filler, no disclaimers.\n\nDATA:\n" + data_block
    )
    try:
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        _commentary_cache.update({"date": today, "text": text})
        return {"date": today, "commentary": text, "cached": False}
    except Exception:
        # Graceful fallback: deterministic data-rich note (still has numbers + levels)
        text = "\n\n".join(data_lines)
        return {"date": today, "commentary": text, "cached": False, "fallback": True}


_sparkline_cache = {"ts": 0, "data": None}

@app.get("/market/sparklines")
def market_sparklines(secret: str = ""):
    """~1 month of daily closes per overview instrument, for inline sparklines."""
    _validate_secret(secret)
    import time, math
    from market_data import _stooq_daily
    if time.time() - _sparkline_cache["ts"] < 900 and _sparkline_cache["data"]:
        return _sparkline_cache["data"]
    syms = [s for items in _OVERVIEW_SYMBOLS.values() for s in items.values()]
    out = {}
    for s in syms:
        stooq_sym = _OVERVIEW_STOOQ.get(s)
        closes = []
        if stooq_sym:
            try:
                df = _stooq_daily(stooq_sym)
                if len(df) and "Close" in df.columns:
                    closes = [round(float(c), 4) for c in df["Close"].tolist()
                              if c is not None and not math.isnan(float(c))]
            except Exception:
                pass
        out[s] = closes[-22:]
    res = {"series": out}
    _sparkline_cache.update({"ts": time.time(), "data": res})
    return res


@app.get("/calendar/economic")
def calendar_economic(secret: str = ""):
    """This-week high/medium-impact US economic events. Forex Factory primary, Finnhub fallback."""
    _validate_secret(secret)
    import httpx
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    def _parse_ff(data: list) -> list:
        out = []
        for ev in data:
            impact = (ev.get("impact") or "").lower()
            if impact not in ("high", "medium"):
                continue
            if (ev.get("country") or "").upper() not in ("USD", "US", "USA"):
                continue
            try:
                ts = _dt.fromisoformat(ev.get("date", "")).astimezone(_tz.utc)
            except Exception:
                continue
            dubai = ts + _td(hours=4)
            out.append({
                "date":       dubai.strftime("%Y-%m-%d"),
                "weekday":    dubai.strftime("%a"),
                "time_dubai": dubai.strftime("%H:%M"),
                "ts":         ts.isoformat(),
                "name":       ev.get("title") or ev.get("event") or "Event",
                "impact":     impact,
                "forecast":   ev.get("forecast") or "",
                "previous":   ev.get("previous") or "",
                "actual":     ev.get("actual") or "",
            })
        return out

    def _parse_finnhub(data: list) -> list:
        out = []
        _impact_map = {"high": "high", "medium": "medium", "low": None}
        for ev in data:
            if (ev.get("country") or "").upper() not in ("US", "USD", "USA"):
                continue
            impact = _impact_map.get((ev.get("impact") or "").lower())
            if not impact:
                continue
            raw_time = ev.get("time") or ""
            try:
                ts = _dt.fromisoformat(f"{ev['date']}T{raw_time or '00:00'}:00+00:00")
            except Exception:
                try:
                    ts = _dt.strptime(ev.get("date",""), "%Y-%m-%d").replace(tzinfo=_tz.utc)
                except Exception:
                    continue
            dubai = ts + _td(hours=4)
            out.append({
                "date":       dubai.strftime("%Y-%m-%d"),
                "weekday":    dubai.strftime("%a"),
                "time_dubai": dubai.strftime("%H:%M") if raw_time else "All day",
                "ts":         ts.isoformat(),
                "name":       ev.get("event") or "Event",
                "impact":     impact,
                "forecast":   str(ev.get("estimate") or ""),
                "previous":   str(ev.get("prev") or ""),
                "actual":     str(ev.get("actual") or ""),
            })
        return out

    ff_err = None
    out = []

    # Primary: Forex Factory
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.get(
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://www.forexfactory.com/",
                },
            )
            resp.raise_for_status()
            out = _parse_ff(resp.json() or [])
    except Exception as e:
        ff_err = str(e)

    # Fallback: Finnhub economic calendar
    if not out:
        try:
            from news_fetcher import FINNHUB_KEY
            if FINNHUB_KEY:
                today = _dt.now(_tz.utc).date()
                frm   = today.isoformat()
                to    = (today + _td(days=7)).isoformat()
                with httpx.Client(timeout=10) as client:
                    resp = client.get(
                        "https://finnhub.io/api/v1/calendar/economic",
                        params={"from": frm, "to": to, "token": FINNHUB_KEY},
                    )
                    resp.raise_for_status()
                    out = _parse_finnhub(resp.json().get("economicCalendar", []) or [])
        except Exception:
            pass

    out.sort(key=lambda x: x["ts"])
    result = {"events": out, "tz": "Dubai (UTC+4)"}
    if ff_err and not out:
        result["error"] = f"Forex Factory blocked ({ff_err}); Finnhub fallback also empty"
    elif ff_err:
        result["source"] = "finnhub"
    return result


# Curated large/mega-cap universe for the earnings calendar (symbol → display name)
_EARNINGS_MAJORS = {
    "AAPL": "Apple", "MSFT": "Microsoft", "GOOGL": "Alphabet", "AMZN": "Amazon",
    "NVDA": "NVIDIA", "META": "Meta", "TSLA": "Tesla", "AVGO": "Broadcom",
    "BRK.B": "Berkshire", "JPM": "JPMorgan", "V": "Visa", "MA": "Mastercard",
    "UNH": "UnitedHealth", "XOM": "ExxonMobil", "CVX": "Chevron", "LLY": "Eli Lilly",
    "JNJ": "Johnson & Johnson", "PG": "Procter & Gamble", "HD": "Home Depot",
    "COST": "Costco", "WMT": "Walmart", "ABBV": "AbbVie", "KO": "Coca-Cola",
    "PEP": "PepsiCo", "BAC": "Bank of America", "ADBE": "Adobe", "CRM": "Salesforce",
    "NFLX": "Netflix", "AMD": "AMD", "INTC": "Intel", "QCOM": "Qualcomm",
    "ORCL": "Oracle", "CSCO": "Cisco", "MCD": "McDonald's", "DIS": "Disney",
    "NKE": "Nike", "WFC": "Wells Fargo", "GS": "Goldman Sachs", "MS": "Morgan Stanley",
    "PFE": "Pfizer", "TMO": "Thermo Fisher", "BA": "Boeing", "CAT": "Caterpillar",
    "GE": "GE Aerospace", "PYPL": "PayPal", "UBER": "Uber", "T": "AT&T",
    "VZ": "Verizon", "C": "Citigroup", "PLTR": "Palantir",
}


def _finnhub_eps_surprise(sym: str):
    """Return last-quarter EPS surprise % and beat/miss via Finnhub earnings calendar."""
    import httpx, os
    from datetime import date, timedelta
    fk = os.environ.get("FINNHUB_KEY", "")
    if not fk:
        return None, None
    try:
        to = date.today().isoformat()
        frm = (date.today() - timedelta(days=120)).isoformat()
        r = httpx.get("https://finnhub.io/api/v1/calendar/earnings",
                      params={"from": frm, "to": to, "symbol": sym, "token": fk}, timeout=8)
        if r.status_code != 200:
            return None, None
        evs = r.json().get("earningsCalendar", []) or []
        reported = [e for e in evs if e.get("epsActual") is not None]
        if not reported:
            return None, None
        latest = sorted(reported, key=lambda e: e.get("date", ""), reverse=True)[0]
        actual = latest.get("epsActual")
        est    = latest.get("epsEstimate")
        if actual is None or est is None or est == 0:
            return None, None
        surprise_pct = round((actual - est) / abs(est) * 100, 1)
        beat = "BEAT" if surprise_pct > 1 else ("MISS" if surprise_pct < -1 else "IN-LINE")
        return surprise_pct, beat
    except Exception:
        return None, None


@app.get("/calendar/earnings")
def calendar_earnings(secret: str = ""):
    """Upcoming earnings (next 7 days) for major caps. Finnhub for dates/estimates + yfinance for last-quarter surprise."""
    _validate_secret(secret)
    import httpx
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    from news_fetcher import FINNHUB_KEY
    today = _dt.now(_tz.utc).date()
    frm, to = today.isoformat(), (today + _td(days=7)).isoformat()

    # Primary: Finnhub earnings calendar
    data = []
    source_err = None
    if FINNHUB_KEY:
        try:
            with httpx.Client(timeout=12) as client:
                resp = client.get("https://finnhub.io/api/v1/calendar/earnings", params={
                    "from": frm, "to": to, "token": FINNHUB_KEY,
                })
                resp.raise_for_status()
                data = resp.json().get("earningsCalendar", []) or []
        except Exception as e:
            source_err = str(e)

    _HR = {"bmo": "Pre-mkt", "amc": "After-close", "dmh": "Mid-day"}
    out = []
    for ev in data:
        sym = (ev.get("symbol") or "").upper()
        if sym not in _EARNINGS_MAJORS:
            continue
        surprise_pct, beat_miss = _finnhub_eps_surprise(sym)
        out.append({
            "symbol":       sym,
            "name":         _EARNINGS_MAJORS[sym],
            "date":         ev.get("date"),
            "when":         _HR.get((ev.get("hour") or "").lower(), ev.get("hour") or ""),
            "eps_estimate": ev.get("epsEstimate"),
            "eps_actual":   ev.get("epsActual"),
            "rev_estimate": ev.get("revenueEstimate"),
            "last_surprise_pct": surprise_pct,
            "last_beat_miss":    beat_miss,
        })
    out.sort(key=lambda x: (x["date"] or "", x["symbol"]))
    result = {"earnings": out, "from": frm, "to": to}
    if source_err and not out:
        result["error"] = f"Finnhub failed ({source_err})"
    return result


@app.get("/data/health")
def data_health_report(secret: str = ""):
    """Data-flow observability: per-source success/failure/freshness across every
    external feed (price, options, VIX, news, calendar, macro). `degraded` lists
    anything failing or stale so a broken source surfaces instead of silently
    degrading the signals/brief."""
    _validate_secret(secret)
    import data_health
    rep = data_health.report()
    try:
        import memory_guard
        rep["memory"] = memory_guard.memory_status()
    except Exception:
        pass
    return rep


@app.get("/exit/optimization")
def exit_optimization(secret: str = "", run: int = 0):
    """Adaptive exit optimizer (SHADOW) — per-pool learned take-profit + projected
    expectancy. `run=1` recomputes now; otherwise serves the last persisted result."""
    _validate_secret(secret)
    if run:
        import exit_optimizer
        return exit_optimizer.run_all()
    from db import _get_file
    data, _ = _get_file("data/exit_optimization.json")
    return data if isinstance(data, dict) else {"pools": {}, "note": "not computed yet — call with run=1"}


@app.get("/options/flow")
async def options_flow(secret: str = ""):
    _validate_secret(secret)
    import polygon_data
    flow    = polygon_data.get_options_flow("SPXW", limit=30) if polygon_data.available() else []
    pc      = polygon_data.get_put_call_ratio("SPXW") if polygon_data.available() else None
    # Also return current paper trades status
    from options_engine import iv_rank, get_vix_context, _atm_snapshot
    vix_ctx = get_vix_context()
    atm_iv, em, spot = _atm_snapshot()
    ivr = iv_rank(atm_iv) if atm_iv else None
    from db import _get_file
    ledger, _ = _get_file("data/options_paper_SPX.json")
    if not isinstance(ledger, list):
        ledger = []
    open_trades   = [r for r in ledger if r.get("status") == "OPEN"]
    closed_trades = [r for r in ledger if r.get("status") == "CLOSED"][-10:]

    # Backfill the two fields the dashboard reads (pool / outcome) for older rows
    # written before they were stored at the source. pool is implied by dte;
    # outcome is win iff the trade closed positive (loss_reason carries the detail).
    def _enrich(r: dict) -> dict:
        pool = r.get("pool") or ("SPX_0DTE" if r.get("dte") == 0 else "SPX_1DTE")
        outcome = r.get("outcome") or ("WIN" if (r.get("pnl_pct") or 0) > 0 else "LOSS")
        return {**r, "pool": pool, "outcome": outcome,
                "loss_reason": r.get("loss_reason")}
    closed_trades = [_enrich(r) for r in closed_trades]
    open_trades   = [{**r, "pool": r.get("pool") or ("SPX_0DTE" if r.get("dte") == 0 else "SPX_1DTE")}
                     for r in open_trades]
    from options_engine import last_options_check
    iv_sessions = 0
    try:
        from db import _get_file
        _ivh, _ = _get_file("data/options_iv_history.json")
        iv_sessions = len(_ivh) if isinstance(_ivh, list) else 0
    except Exception:
        pass
    return {
        "polygon_available": polygon_data.available(),
        "flow":              flow,
        "put_call_ratio":    pc,
        "vix":               vix_ctx,
        "atm_iv":            round(atm_iv * 100, 1) if atm_iv else None,
        "iv_rank":           ivr,
        "iv_sessions":       iv_sessions,       # IV Rank unlocks at 20
        "expected_move":     round(em, 1) if em else None,
        "spot":              round(spot, 1) if spot else None,
        "open_positions":    open_trades,
        "open_trades":       open_trades,
        "closed_recent":     closed_trades,
        "last_check":        last_options_check(),
    }


# ── Serve PWA static files ────────────────────────────────────────────────────
import os as _os
_pwa_dirs = [
    _os.path.join(_os.path.dirname(__file__), "static_pwa"),      # committed build (Railway)
    _os.path.join(_os.path.dirname(__file__), "..", "frontend", "dist"),  # local dev
]
for _pwa_dir in _pwa_dirs:
    if _os.path.isdir(_pwa_dir):
        from fastapi.staticfiles import StaticFiles
        app.mount("/app", StaticFiles(directory=_pwa_dir, html=True), name="pwa")
        print(f"[startup] PWA mounted from {_pwa_dir}")
        break
