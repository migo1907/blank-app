import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        _client = create_client(url, key)
    return _client


# ── Weights ──────────────────────────────────────────────────

def load_weights(symbol: str = "XAUUSD") -> dict:
    db = get_db()
    row = db.table("model_weights").select("*").eq("symbol", symbol).single().execute()
    return row.data


def save_weights(symbol: str, weights: dict) -> None:
    db = get_db()
    db.table("model_weights").update({**weights, "updated_at": "now()"}).eq("symbol", symbol).execute()


# ── Trade outcomes ────────────────────────────────────────────

def insert_outcome(outcome: dict) -> None:
    get_db().table("trade_outcomes").insert(outcome).execute()


def recent_outcomes(symbol: str = "XAUUSD", limit: int = 200) -> list[dict]:
    db = get_db()
    result = (
        db.table("trade_outcomes")
        .select("*")
        .eq("symbol", symbol)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


# ── News sentiment ────────────────────────────────────────────

def insert_news(items: list[dict]) -> None:
    if items:
        get_db().table("news_sentiment").insert(items).execute()


def recent_news(hours: int = 4) -> list[dict]:
    db = get_db()
    result = (
        db.table("news_sentiment")
        .select("sentiment_score, impact, headline, fetched_at")
        .gte("fetched_at", f"now() - interval '{hours} hours'")
        .order("fetched_at", desc=True)
        .limit(50)
        .execute()
    )
    return result.data


# ── Signals ───────────────────────────────────────────────────

def insert_signal(signal: dict) -> dict:
    result = get_db().table("signals").insert(signal).execute()
    return result.data[0]


def expire_old_signals(symbol: str = "XAUUSD") -> None:
    db = get_db()
    db.table("signals").update({"status": "EXPIRED"}).eq("symbol", symbol).eq("status", "ACTIVE").lt("expires_at", "now()").execute()
