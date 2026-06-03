"""
XAU/USD Migo Sniper Pro — Level 3 ML Backend (v3·25F)
FastAPI app that receives TradingView webhooks, updates adaptive weights
in GitHub storage, runs RF ensemble, fetches news sentiment, sends signals to Telegram.
"""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_SECRET    = os.environ.get("WEBHOOK_SECRET", "")
RAILWAY_API_TOKEN  = os.environ.get("RAILWAY_API_TOKEN", "")
RAILWAY_PROJECT_ID = os.environ.get("RAILWAY_PROJECT_ID", "bcc5442d-2f19-4dfa-ad25-219a5c70868a")
RAILWAY_SERVICE_ID = os.environ.get("RAILWAY_SERVICE_ID", "e4310b2b-3a37-440e-a3b7-a14ea476f8a1")


# ── Lifespan: start scheduler, load ML model, prime RF ──────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Loading ML model (25F) from storage…")
    from ml_model import get_model
    get_model()

    print("[startup] Priming RF + GBM ensembles…")
    from ml_ensemble import get_rf, get_gbm
    from db import recent_outcomes
    rf  = get_rf()
    gbm = get_gbm()
    history = recent_outcomes(limit=500)
    if len(history) >= 15:
        rf.retrain(history)
        gbm.train(history)
        print(f"[startup] RF + GBM trained on {len(history)} trades.")
    else:
        print(f"[startup] Not enough data ({len(history)} trades) — will train later.")

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
    version="3.0.0",
    lifespan=lifespan,
)


# ── Request / Response models ────────────────────────────────────────────────

class TradeOutcomePayload(BaseModel):
    secret:      str
    trade_id:    str
    direction:   Literal["LONG", "SHORT"]
    outcome:     Literal["WIN", "LOSS", "PARTIAL"]
    tp_stage:    str = ""
    entry_price: float
    exit_price:  float
    ml_score:    float = 0.5
    f1:  float = 0.0
    f2:  float = 0.0
    f3:  float = 0.0
    f4:  float = 0.0
    f5:  float = 0.0
    f6:  float = 0.0
    f7:  float = 0.0
    f8:  float = 0.0
    f9:  float = 0.0
    f10: float = 0.0
    f11: float = 0.0
    f12: float = 0.0
    f13: float = 0.0
    f14: float = 0.0
    f15: float = 0.0
    f16: float = 0.0
    f17: float = 0.0
    f18: float = 0.0
    f19: float = 0.0
    f20: float = 0.0
    f21: float = 0.0
    f22: float = 0.0
    f23: float = 0.0
    f24: float = 0.0
    f25: float = 0.0

    class Config:
        extra = "ignore"


class SignalEntryPayload(BaseModel):
    secret:      str
    direction:   Literal["LONG", "SHORT"]
    timeframe:   str = "5m"
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
    """Catch-all payload — routes internally based on which fields are present."""
    secret:      str
    direction:   Literal["LONG", "SHORT"]
    # entry signal fields
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
    # trade outcome fields
    trade_id:    Optional[str]   = None
    outcome:     Optional[str]   = None
    tp_stage:    str             = ""
    exit_price:  Optional[float] = None
    f1:  float = 0.0; f2:  float = 0.0; f3:  float = 0.0; f4:  float = 0.0
    f5:  float = 0.0; f6:  float = 0.0; f7:  float = 0.0; f8:  float = 0.0
    f9:  float = 0.0; f10: float = 0.0; f11: float = 0.0; f12: float = 0.0
    f13: float = 0.0; f14: float = 0.0; f15: float = 0.0; f16: float = 0.0
    f17: float = 0.0; f18: float = 0.0; f19: float = 0.0; f20: float = 0.0
    f21: float = 0.0; f22: float = 0.0; f23: float = 0.0; f24: float = 0.0
    f25: float = 0.0

    class Config:
        extra = "ignore"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_secret(secret: str) -> None:
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret.")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.api_route("/health", methods=["GET", "POST", "HEAD"])
async def health():
    return {"status": "ok", "version": "3.0.0-25F"}


@app.get("/test-telegram")
async def test_telegram(secret: str = ""):
    """Send a test message to Telegram to verify bot connection."""
    _validate_secret(secret)
    from telegram_bot import send_text
    import os
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return {"status": "error", "detail": "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment."}
    await send_text("✅ Migo Sniper Pro — Telegram test OK!\n\n🤖 Backend connected.\n📡 Signals will appear here every 15 min.")
    return {"status": "sent", "chat_id": chat_id, "token_prefix": token[:10] + "..."}


@app.post("/webhook/trade-outcome")
async def trade_outcome(payload: TradeOutcomePayload):
    """
    Called by TradingView alert webhook when a trade closes.
    Updates adaptive KNN weights and retrains RF if enough data.
    """
    _validate_secret(payload.secret)

    from ml_model import get_model, Features
    from ml_ensemble import get_rf
    from db import insert_outcome, recent_outcomes

    sym = getattr(payload, "symbol", "XAUUSD") or "XAUUSD"
    model = get_model(sym)
    features = Features(
        f1=payload.f1,   f2=payload.f2,   f3=payload.f3,   f4=payload.f4,
        f5=payload.f5,   f6=payload.f6,   f7=payload.f7,   f8=payload.f8,
        f9=payload.f9,   f10=payload.f10, f11=payload.f11, f12=payload.f12,
        f13=payload.f13, f14=payload.f14, f15=payload.f15, f16=payload.f16,
        f17=payload.f17, f18=payload.f18, f19=payload.f19, f20=payload.f20,
        f21=payload.f21, f22=payload.f22, f23=payload.f23, f24=payload.f24,
        f25=payload.f25,
    )

    from db import symbol_to_pool
    model.update_on_outcome(features, payload.direction, payload.outcome)
    model.save(symbol_to_pool(sym))

    # Store outcome in GitHub for future KNN/RF history
    outcome_row = {
        "symbol":        sym,
        "direction":     payload.direction,
        "trigger":       getattr(payload, "trigger", "") or "",
        "entry_price":   payload.entry_price,
        "exit_price":    payload.exit_price,
        "outcome":       payload.outcome,
        "pnl_pct":       round((payload.exit_price - payload.entry_price) / max(payload.entry_price, 0.0001) * 100, 4),
        "ml_bull_score": payload.ml_score,
    }
    # Add all 25 feature columns
    outcome_row.update(features.as_db_dict())
    insert_outcome(outcome_row)

    # Opportunistic RF retrain (async, non-blocking)
    async def _retrain():
        history = recent_outcomes(sym, limit=500)
        if len(history) >= 15:
            get_rf().retrain(history)
            get_gbm().train(history)

    asyncio.create_task(_retrain())

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
    """
    Called by TradingView on trade ENTRY.
    Sends formatted signal instantly to Telegram.
    """
    _validate_secret(payload.secret)
    from telegram_bot import send_entry_signal
    from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event
    asyncio.create_task(send_entry_signal({
        "direction":   payload.direction,
        "timeframe":   payload.timeframe,
        "trigger":     payload.trigger,
        "symbol":      payload.symbol,
        "entry_price": payload.entry_price,
        "tp1":         payload.tp1,
        "tp2":         payload.tp2,
        "tp3":         payload.tp3,
        "sl":          payload.sl,
        "ml_score":    payload.ml_score,
        "tier":        payload.tier,
        "news_score":  get_latest_news_sentiment(),
        "velocity":    get_latest_velocity().get("label", "NORMAL"),
        "event":       get_latest_event().get("event_type", ""),
    }))
    return {"status": "ok", "direction": payload.direction, "timeframe": payload.timeframe}


@app.post("/webhook")
async def unified_webhook(payload: UnifiedPayload):
    """
    Single endpoint that auto-routes:
    - entry signal  → when tp1/tp2/tp3/sl are present
    - trade outcome → when trade_id + outcome are present
    Eliminates 422 errors from TradingView sending both payload types to both URLs.
    """
    _validate_secret(payload.secret)

    is_entry  = payload.tp1 is not None and payload.sl is not None
    is_outcome = payload.trade_id is not None and payload.outcome is not None

    if is_entry:
        from telegram_bot import send_entry_signal
        from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event
        asyncio.create_task(send_entry_signal({
            "direction":   payload.direction,
            "timeframe":   payload.timeframe or "5",
            "trigger":     payload.trigger or "RSI",
            "symbol":      payload.symbol or "XAUUSD",
            "entry_price": payload.entry_price or 0.0,
            "tp1":         payload.tp1 or 0.0,
            "tp2":         payload.tp2 or 0.0,
            "tp3":         payload.tp3 or 0.0,
            "sl":          payload.sl or 0.0,
            "ml_score":    payload.ml_score,
            "tier":        payload.tier or "MED",
            "news_score":  get_latest_news_sentiment(),
            "velocity":    get_latest_velocity().get("label", "NORMAL"),
            "event":       get_latest_event().get("event_type", ""),
        }))
        return {"status": "ok", "routed_to": "signal-entry", "direction": payload.direction}

    if is_outcome:
        from ml_model import get_model, Features
        from ml_ensemble import get_rf, get_gbm
        from db import insert_outcome, recent_outcomes, symbol_to_pool
        sym2     = payload.symbol or "XAUUSD"
        model    = get_model(sym2)
        features = Features(
            f1=payload.f1, f2=payload.f2, f3=payload.f3, f4=payload.f4,
            f5=payload.f5, f6=payload.f6, f7=payload.f7, f8=payload.f8,
            f9=payload.f9, f10=payload.f10, f11=payload.f11, f12=payload.f12,
            f13=payload.f13, f14=payload.f14, f15=payload.f15, f16=payload.f16,
            f17=payload.f17, f18=payload.f18, f19=payload.f19, f20=payload.f20,
            f21=payload.f21, f22=payload.f22, f23=payload.f23, f24=payload.f24,
            f25=payload.f25,
        )
        model.update_on_outcome(features, payload.direction, payload.outcome)
        model.save(symbol_to_pool(sym2))
        outcome_row = {
            "symbol":        sym2,
            "direction":     payload.direction,
            "entry_price":   payload.entry_price or 0.0,
            "exit_price":    payload.exit_price or 0.0,
            "outcome":       payload.outcome,
            "pnl_pct":       round((payload.exit_price - payload.entry_price) / max(payload.entry_price or 1, 0.0001) * 100, 4) if payload.exit_price and payload.entry_price else 0.0,
            "ml_bull_score": payload.ml_score,
        }
        outcome_row.update(features.as_db_dict())
        insert_outcome(outcome_row)

        async def _retrain():
            history = recent_outcomes(sym2, limit=500)
            if len(history) >= 15:
                get_rf().retrain(history)
                get_gbm().train(history)
        asyncio.create_task(_retrain())

        return {"status": "ok", "routed_to": "trade-outcome", "outcome": payload.outcome}

    return {"status": "ignored", "reason": "payload did not match entry or outcome pattern"}


@app.get("/weights")
async def get_weights(secret: str = ""):
    """Return current adaptive weights."""
    _validate_secret(secret)
    from ml_model import get_model
    model = get_model()
    top3 = model.top_features(3)
    return {
        "weights":      {f"w{i+1}": round(w, 4) for i, w in enumerate(model.weights)},
        "total_wins":   model._total_wins,
        "total_losses": model._total_losses,
        "win_rate":     round(model.win_rate * 100, 1),
        "top_features": [{"name": n, "weight": round(w, 4)} for n, w in top3],
    }


@app.get("/feature-importance")
async def feature_importance(secret: str = ""):
    """
    Returns top features ranked by both KNN adaptive weights and RF importance.
    """
    _validate_secret(secret)
    from ml_model import get_model, FEATURE_NAMES
    from ml_ensemble import get_rf

    model = get_model()
    rf    = get_rf()

    knn_top = model.top_features(5)
    rf_top  = rf.top_features(5)

    # Combined ranking: average normalized rank from both
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


@app.get("/signal/now")
async def signal_now(secret: str = ""):
    """Trigger an immediate signal generation cycle."""
    _validate_secret(secret)
    from scheduler import _news_signal_cycle
    asyncio.create_task(_news_signal_cycle())
    return {"status": "signal cycle triggered"}


@app.get("/railway-status")
async def railway_status(secret: str = ""):
    """Query Railway API for live service status and recent logs."""
    _validate_secret(secret)
    if not RAILWAY_API_TOKEN:
        return {"error": "RAILWAY_API_TOKEN not set"}

    import httpx, traceback

    if not RAILWAY_API_TOKEN:
        return {"error": "RAILWAY_API_TOKEN not set"}

    headers = {
        "Authorization": f"Bearer {RAILWAY_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        # ── 1. Get latest deployment ID ───────────────────────────────────────
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

        # ── 2. Get logs for latest deployment ─────────────────────────────────
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
async def dashboard(secret: str = ""):
    """Quick status dashboard."""
    _validate_secret(secret)
    from ml_model import get_model
    from ml_ensemble import get_rf
    from db import recent_outcomes, recent_news
    from scheduler import get_latest_news_sentiment, get_latest_velocity, get_latest_event

    model = get_model()
    rf    = get_rf()
    recent_trades     = recent_outcomes(limit=10)
    recent_news_items = recent_news(hours=4)
    top3              = model.top_features(3)

    return {
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
