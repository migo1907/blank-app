"""
XAU/USD Migo Sniper Pro — Level 3 ML Backend (v3·25F)
FastAPI app that receives TradingView webhooks, updates adaptive weights
in GitHub storage, runs RF ensemble, fetches news sentiment, sends signals to Telegram.
"""
import os
import math
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
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
    "XAUUSD_2M", "XAUUSD_5M", "XAUUSD_30M", "XAUUSD_1H",
    "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_4H",
    "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_4H",
    "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H",
    "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_4H",
    "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_4H",
}
RAILWAY_API_TOKEN  = os.environ.get("RAILWAY_API_TOKEN", "")
RAILWAY_PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID", "")
RAILWAY_SERVICE_ID = os.environ.get("RAILWAY_SERVICE_ID", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Loading ML model (25F) from storage…")
    from ml_model import get_model
    get_model("XAUUSD_2M")

    print("[startup] Priming RF + GBM ensembles for all pools…")
    from ml_ensemble import get_rf, get_gbm
    from db import recent_outcomes
    for _pool in ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_30M", "XAUUSD_1H",
                  "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_4H",
                  "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_4H",
                  "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H",
                  "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_4H",
                  "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_4H"]:
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
    for _pool in ["XAUUSD_2M", "XAUUSD_5M", "XAUUSD_30M", "XAUUSD_1H",
                  "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M", "STOCKS_MOMENTUM_4H",
                  "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",  "STOCKS_QUALITY_4H",
                  "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H",
                  "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",      "STOCKS_QQQ_4H",
                  "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",   "STOCKS_SPX500_4H"]:
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
    title="Migo Sniper Pro — ML Backend v3·25F",
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


class TradeOutcomePayload(BaseModel):
    secret:      str
    trade_id:    Optional[str]   = None
    direction:   str             = ""
    outcome:     str             = ""
    ml_outcome:  Optional[str]   = None
    mfe:         float           = 0.0
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
            "ml_score", "mfe", "entry_price", "exit_price",
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
            "ml_score", "mfe",
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

    try:
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

        # Signed realized move (favorable = positive). Lets the KNN re-classify a
        # partial that actually closed negative (e.g. SL_TP1 on gold scalps) as a loss.
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
        _regime     = _detect_regime(features)
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

            # Record OOS prediction for champion-challenger tracking
            _prev_score = outcome_row.get("ml_bull_score") or 0.5
            _actual_win = outcome_row.get("outcome") in ("WIN", "PARTIAL")
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
        _gate = score_entry_gate(symbol_to_pool(sym, tf), payload.direction)
    except Exception as _ge:
        print(f"[signal-entry] gate error (non-fatal): {_ge}")
        _gate = {"pass": True, "score": 0.5, "reason": "gate_error", "components": {}}
    print(f"[signal-entry] ML QUALITY {payload.direction} {sym} TF={tf} "
          f"score={_gate['score']} ({_gate['reason']}) components={_gate['components']}")

    bias        = get_active_bias(sym, payload.direction)
    contra_bias = get_active_bias(sym, "SHORT" if payload.direction == "LONG" else "LONG")
    htf_context = "htf_direct" if is_htf(tf) else ("with_bias" if bias else ("counter_trend" if contra_bias else "scalp"))
    print(f"[signal-entry] {payload.direction} {sym} TF={tf} htf={htf_context} → sending to Telegram")

    asyncio.create_task(send_entry_signal({
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
    }))
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
            _gate = score_entry_gate(symbol_to_pool(sym, tf), payload.direction)
        except Exception as _ge:
            print(f"[webhook] gate error (non-fatal): {_ge}")
            _gate = {"pass": True, "score": 0.5, "reason": "gate_error", "components": {}}
        print(f"[webhook] ML QUALITY {payload.direction} {sym} TF={tf} "
              f"score={_gate['score']} ({_gate['reason']}) components={_gate['components']}")

        bias        = get_active_bias(sym, payload.direction)
        contra_bias = get_active_bias(sym, "SHORT" if payload.direction == "LONG" else "LONG")
        htf_context = "htf_direct" if is_htf(tf) else ("with_bias" if bias else ("counter_trend" if contra_bias else "scalp"))
        print(f"[webhook] {payload.direction} {sym} TF={tf} htf={htf_context} → sending to Telegram")

        asyncio.create_task(send_entry_signal({
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
        }))
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


@app.get("/signal/now")
async def signal_now(secret: str = ""):
    _validate_secret(secret)
    from scheduler import _news_signal_cycle
    asyncio.create_task(_news_signal_cycle())
    return {"status": "signal cycle triggered"}


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
