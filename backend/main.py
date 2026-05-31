"""
XAU/USD Migo Sniper Pro — Level 2 ML Backend
FastAPI app that receives TradingView webhooks, updates adaptive weights
in Supabase, fetches news sentiment, and sends signals to Telegram.
"""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Literal
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


# ── Lifespan: start scheduler, load ML model ────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] Loading ML model from Supabase…")
    from ml_model import get_model
    get_model()  # pre-loads weights

    print("[startup] Starting scheduler…")
    from scheduler import start_scheduler, _news_signal_cycle
    start_scheduler()
    # Run one immediate cycle so Telegram gets a signal on startup
    asyncio.create_task(_news_signal_cycle())

    yield

    from scheduler import stop_scheduler
    stop_scheduler()
    print("[shutdown] Done.")


app = FastAPI(
    title="Migo Sniper Pro — ML Backend",
    description="Adaptive KNN + news sentiment for XAU/USD",
    version="2.0.0",
    lifespan=lifespan,
)


# ── Request / Response models ────────────────────────────────────────────────

class TradeOutcomePayload(BaseModel):
    secret:      str
    trade_id:    str
    direction:   Literal["LONG", "SHORT"]
    outcome:     Literal["WIN", "LOSS", "PARTIAL"]
    tp_stage:    str = ""          # "TP1" | "TP2" | "TP3" | "SL"
    entry_price: float
    exit_price:  float
    ml_score:    float = 0.5
    # Feature snapshot at entry
    f1: float = 0.0
    f2: float = 0.0
    f3: float = 0.0
    f4: float = 0.0
    f5: float = 0.0
    f6: float = 0.0
    f7: float = 0.0
    f8: float = 0.0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _validate_secret(secret: str) -> None:
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret.")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/trade-outcome")
async def trade_outcome(payload: TradeOutcomePayload):
    """
    Called by TradingView alert webhook when a trade closes.
    Updates adaptive KNN weights in Supabase.
    """
    _validate_secret(payload.secret)

    from ml_model import get_model, Features
    from db import insert_outcome, recent_outcomes

    model = get_model()
    features = Features(
        f1=payload.f1, f2=payload.f2, f3=payload.f3, f4=payload.f4,
        f5=payload.f5, f6=payload.f6, f7=payload.f7, f8=payload.f8,
    )

    model.update_on_outcome(features, payload.direction, payload.outcome)
    model.save()

    # Store outcome in Supabase for future KNN history
    insert_outcome({
        "symbol": "XAUUSD",
        "direction": payload.direction,
        "entry_price": payload.entry_price,
        "exit_price": payload.exit_price,
        "outcome": payload.outcome,
        "pnl_pct": round((payload.exit_price - payload.entry_price) / payload.entry_price * 100, 4),
        "f1_rsi":      payload.f1,
        "f2_adx":      payload.f2,
        "f3_atr":      payload.f3,
        "f4_bb":       payload.f4,
        "f5_macd":     payload.f5,
        "f6_willr":    payload.f6,
        "f7_cmo":      payload.f7,
        "f8_ema_dist": payload.f8,
        "ml_bull_score": payload.ml_score,
    })

    return {
        "status": "ok",
        "outcome": payload.outcome,
        "new_weights": {f"w{i+1}": round(w, 4) for i, w in enumerate(model.weights)},
        "total_wins": model._total_wins,
        "total_losses": model._total_losses,
        "win_rate": round(model.win_rate * 100, 1),
    }


@app.get("/weights")
async def get_weights(secret: str = ""):
    """Return current adaptive weights (Pine Script can poll this)."""
    _validate_secret(secret)
    from ml_model import get_model
    model = get_model()
    return {
        "weights": {f"w{i+1}": round(w, 4) for i, w in enumerate(model.weights)},
        "total_wins": model._total_wins,
        "total_losses": model._total_losses,
        "win_rate": round(model.win_rate * 100, 1),
        "top_feature": model.top_feature(),
    }


@app.get("/signal/now")
async def signal_now(secret: str = ""):
    """Trigger an immediate signal generation cycle."""
    _validate_secret(secret)
    from scheduler import _news_signal_cycle
    asyncio.create_task(_news_signal_cycle())
    return {"status": "signal cycle triggered"}


@app.get("/dashboard")
async def dashboard(secret: str = ""):
    """Quick status dashboard."""
    _validate_secret(secret)
    from ml_model import get_model
    from db import recent_outcomes, recent_news
    from scheduler import get_latest_news_sentiment

    model = get_model()
    recent_trades = recent_outcomes(limit=10)
    recent_news_items = recent_news(hours=4)

    return {
        "model": {
            "weights": {f"w{i+1}": round(w, 4) for i, w in enumerate(model.weights)},
            "win_rate": round(model.win_rate * 100, 1),
            "total_trades": model._total_wins + model._total_losses,
            "top_feature": model.top_feature(),
        },
        "news_sentiment": round(get_latest_news_sentiment(), 4),
        "recent_news_count": len(recent_news_items),
        "recent_trades": [
            {"direction": t["direction"], "outcome": t["outcome"], "created_at": t["created_at"]}
            for t in recent_trades
        ],
    }
