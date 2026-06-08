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
}
RAILWAY_API_TOKEN  = os.environ.get("RAILWAY_API_TOKEN", "")
RAILWAY_PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID", "bcc5442d-2f19-4dfa-ad25-219a5c70868a")
RAILWAY_SERVICE_ID = os.environ.get("RAILWAY_SERVICE_ID", "e4310b2b-3a37-440e-a3b7-a14ea476f8a1")


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
                  "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",    "STOCKS_INDEX_4H"]:
        _hist = recent_outcomes(_pool, limit=500)
        if len(_hist) >= 50:
            get_rf(_pool).retrain(_hist)
            get_gbm(_pool).train(_hist)
            print(f"[startup] RF+GBM trained for {_pool} on {len(_hist)} trades.")
        else:
            print(f"[startup] {_pool}: {len(_hist)} trades — RF/GBM will train when data grows.")

    print("[startup] Loading feature cache from GitHub…")
    from signal_engine import load_feature_cache
    load_feature_cache()

    print("[startup] Loading HTF bias store from GitHub…")
    from htf_bias import load_bias_store
    load_bias_store()

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
    f25: float = 0.0

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, values: dict) -> dict:
        float_fields = {
            "ml_score", "mfe", "entry_price", "exit_price",
            "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10",
            "f11","f12","f13","f14","f15","f16","f17","f18","f19","f20",
            "f21","f22","f23","f24","f25",
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
    direction:   Literal["LONG", "SHORT"]
    timeframe:   str = "5"
    trigger:     str = "RSI"
    symbol:      str = "XAUUSD"
    entry_price: float
    tp1:         float
    tp2:         float
    tp3:         float
    sl:          float
    ml_score:    float = 0.5
    tier:        str = "MED"

    class Config:
        extra = "ignore"


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
    f25: float = 0.0

    model_config = {"extra": "ignore"}

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, values: dict) -> dict:
        """TradingView sends JSON null for Pine Script na() values. Coerce to 0.0 for float fields."""
        float_fields = {
            "ml_score", "mfe",
            "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10",
            "f11","f12","f13","f14","f15","f16","f17","f18","f19","f20",
            "f21","f22","f23","f24","f25",
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

    return {"status": "ok", "version": "3.1.0-25F", "scheduler": "running" if scheduler_ok else "restarted"}


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
    """Map Pine Script outcome strings to internal WIN/LOSS/PARTIAL/HEARTBEAT/PROGRESS."""
    v = raw.upper().strip()
    if v == "HEARTBEAT":                          return "HEARTBEAT"
    if v in ("TP1_HIT", "TP2_HIT"):              return "PROGRESS"
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
        features = Features(
            f1=payload.f1, f2=payload.f2, f3=payload.f3, f4=payload.f4,
            f5=payload.f5, f6=payload.f6, f7=payload.f7, f8=payload.f8,
            f9=payload.f9, f10=payload.f10, f11=payload.f11, f12=payload.f12,
            f13=payload.f13, f14=payload.f14, f15=payload.f15, f16=payload.f16,
            f17=payload.f17, f18=payload.f18, f19=payload.f19, f20=payload.f20,
            f21=payload.f21, f22=payload.f22, f23=payload.f23, f24=payload.f24,
            f25=payload.f25,
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

    if not payload.entry_price or not payload.exit_price:
        print(f"[trade-outcome] Missing entry/exit price for {sym} {payload.direction} — skipping")
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
            f25=payload.f25,
        )

        ml_label = payload.ml_outcome or payload.outcome
        _is_dup = _outcome_is_duplicate(sym, payload.direction, payload.entry_price, payload.exit_price, payload.timeframe or "")
        if not _is_dup:
            model.update_on_outcome(features, payload.direction, ml_label, tp_stage=payload.tp_stage or "")
        else:
            print(f"[trade-outcome] Duplicate within {_OUTCOME_DEDUP_TTL}s — skipping weight update for {sym} {payload.direction} entry={payload.entry_price}")

        raw_pct = (payload.exit_price - payload.entry_price) / max(payload.entry_price, 0.0001) * 100
        pnl_pct = raw_pct if payload.direction == "LONG" else -raw_pct

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
            history = await asyncio.to_thread(recent_outcomes, pool, 500)
            if len(history) >= 50:
                await asyncio.to_thread(get_rf(pool).retrain, history)
                await asyncio.to_thread(get_gbm(pool).train, history)
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
    from htf_bias import is_htf, store_bias, get_active_bias
    sym = payload.symbol or "XAUUSD"
    tf  = payload.timeframe or "5"

    if is_htf(tf):
        store_bias(sym, payload.direction, tf, payload.trigger or "", payload.ml_score)
        print(f"[signal-entry] HTF bias stored: {payload.direction} {sym} TF={tf}")
        return {"status": "ok", "routed_to": "htf-bias", "direction": payload.direction, "timeframe": tf}

    # 2M signals feed ML only — too noisy for Telegram
    if str(tf).strip() == "2":
        print(f"[signal-entry] 2M signal — ML only, not sent to Telegram")
        return {"status": "ok", "routed_to": "ml-only", "reason": "2m_suppressed"}

    from telegram_bot import send_entry_signal
    from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event
    entry = payload.entry_price or 0.0
    if entry <= 0:
        print(f"[signal-entry] Missing entry_price for {sym} {payload.direction} — skipping Telegram")
        return {"status": "ok", "routed_to": "suppressed", "reason": "no_entry_price"}

    # HTF bias is context only — signal always sends (5M+ can be scalp or counter-trend pullback)
    bias        = get_active_bias(sym, payload.direction)
    contra_bias = get_active_bias(sym, "SHORT" if payload.direction == "LONG" else "LONG")
    htf_context = "with_bias" if bias else ("counter_trend" if contra_bias else "scalp")
    print(f"[signal-entry] {payload.direction} {sym} TF={tf} htf={htf_context}")

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

        if is_htf(tf):
            store_bias(sym, payload.direction, tf, payload.trigger or "", payload.ml_score)
            print(f"[webhook] HTF bias stored: {payload.direction} {sym} TF={tf}")
            return {"status": "ok", "routed_to": "htf-bias", "direction": payload.direction, "timeframe": tf}

        # 2M signals feed ML only — too noisy for Telegram
        if str(tf).strip() == "2":
            print(f"[webhook] 2M signal — ML only, not sent to Telegram")
            return {"status": "ok", "routed_to": "ml-only", "reason": "2m_suppressed"}

        from telegram_bot import send_entry_signal
        from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event
        entry = payload.entry_price or 0.0
        if entry <= 0:
            print(f"[webhook] Missing entry_price for {sym} {payload.direction} — skipping Telegram")
            return {"status": "ok", "routed_to": "suppressed", "reason": "no_entry_price"}

        # HTF bias is context only — signal always sends (5M+ can be scalp or counter-trend pullback)
        bias        = get_active_bias(sym, payload.direction)
        contra_bias = get_active_bias(sym, "SHORT" if payload.direction == "LONG" else "LONG")
        htf_context = "with_bias" if bias else ("counter_trend" if contra_bias else "scalp")
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
        features = Features(
            f1=payload.f1, f2=payload.f2, f3=payload.f3, f4=payload.f4,
            f5=payload.f5, f6=payload.f6, f7=payload.f7, f8=payload.f8,
            f9=payload.f9, f10=payload.f10, f11=payload.f11, f12=payload.f12,
            f13=payload.f13, f14=payload.f14, f15=payload.f15, f16=payload.f16,
            f17=payload.f17, f18=payload.f18, f19=payload.f19, f20=payload.f20,
            f21=payload.f21, f22=payload.f22, f23=payload.f23, f24=payload.f24,
            f25=payload.f25,
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
                f25=payload.f25,
            )
            ml_label = payload.ml_outcome or payload.outcome
            _is_dup2 = _outcome_is_duplicate(sym2, payload.direction, payload.entry_price or 0.0, payload.exit_price or 0.0, payload.timeframe or "")
            if not _is_dup2:
                model.update_on_outcome(features, payload.direction, ml_label, tp_stage=payload.tp_stage or "")
            else:
                print(f"[webhook] Duplicate within {_OUTCOME_DEDUP_TTL}s — skipping weight update for {sym2} {payload.direction} entry={payload.entry_price}")

            entry = payload.entry_price or 0.0
            exit_ = payload.exit_price or 0.0
            if entry and exit_:
                raw_pct = (exit_ - entry) / max(entry, 0.0001) * 100
                pnl_pct = raw_pct if payload.direction == "LONG" else -raw_pct
            else:
                pnl_pct = 0.0

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
                history = await asyncio.to_thread(recent_outcomes, pool, 500)
                if len(history) >= 50:
                    await asyncio.to_thread(get_rf(pool).retrain, history)
                    await asyncio.to_thread(get_gbm(pool).train, history)
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
