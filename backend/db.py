"""
GitHub-based persistence layer.
Reads/writes JSON files in your GitHub repo instead of a database.
No Supabase needed — 100% free.

Files stored in repo (branch: data or main):
  data/weights.json       — adaptive KNN weights (one object)
  data/trade_history.json — array of all trade outcomes
  data/news_cache.json    — recent news sentiment items
  data/signals.json       — recent generated signals
"""
import os
import json
import base64
import uuid
import httpx
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = os.environ.get("GITHUB_REPO", "")        # e.g. "migo1907/blank-app"
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "data")  # dedicated data branch

BASE_URL = "https://api.github.com"
HEADERS  = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Default weights file content
DEFAULT_WEIGHTS = {
    "symbol": "XAUUSD",
    "w1": 1.0,  "w2": 1.0,  "w3": 1.0,  "w4": 1.0,  "w5": 1.0,
    "w6": 1.0,  "w7": 1.0,  "w8": 1.0,  "w9": 1.0,  "w10": 1.0,
    "w11": 1.0, "w12": 1.0, "w13": 1.0, "w14": 1.0, "w15": 1.0,
    "w16": 1.0, "w17": 1.0, "w18": 1.0, "w19": 1.0, "w20": 1.0,
    "w21": 1.0, "w22": 1.0, "w23": 1.0, "w24": 1.0, "w25": 1.0,
    "total_wins": 0,
    "total_losses": 0,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}


# ── Low-level GitHub file API ─────────────────────────────────────────────────

def _get_file(path: str) -> tuple[dict | list | None, str | None]:
    """Returns (content, sha). sha is needed for updates."""
    with httpx.Client(timeout=10) as client:
        resp = client.get(
            f"{BASE_URL}/repos/{GITHUB_REPO}/contents/{path}",
            headers=HEADERS,
            params={"ref": GITHUB_BRANCH},
        )
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()
    data = resp.json()
    content = json.loads(base64.b64decode(data["content"]).decode())
    return content, data["sha"]


def _put_file(path: str, content: dict | list, sha: str | None, message: str) -> None:
    """Create or update a file in the repo."""
    encoded = base64.b64encode(json.dumps(content, indent=2).encode()).decode()
    payload: dict = {
        "message": message,
        "content": encoded,
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    with httpx.Client(timeout=15) as client:
        resp = client.put(
            f"{BASE_URL}/repos/{GITHUB_REPO}/contents/{path}",
            headers=HEADERS,
            json=payload,
        )
    resp.raise_for_status()


# ── Symbol → ML pool routing ───────────────────────────────────────────────────

STOCKS_MOMENTUM = {
    "TSLA","TSLL","MSTR","UPST","HTZ","SMCI","BLNK","PLUG","HOOD",
    "BBAI","PLTR","SOXL","TNA","AMD","MU","NVDA","RR",
}
STOCKS_QUALITY = {
    "META","GOOGL","GOOG","MSFT","AAPL","ADBE","IBKR","PATH","NOW","CRM",
}
STOCKS_INDEX = {"QQQ","SPY"}


def symbol_to_pool(symbol: str) -> str:
    """Map a ticker to its ML pool name."""
    # Strip exchange prefix (NASDAQ:TSLA → TSLA)
    ticker = symbol.split(":")[-1].upper()
    if ticker == "XAUUSD" or ticker in ("GOLD", "GC"):
        return "XAUUSD"
    if ticker in STOCKS_INDEX:
        return "STOCKS_INDEX"
    if ticker in STOCKS_QUALITY:
        return "STOCKS_QUALITY"
    if ticker in STOCKS_MOMENTUM:
        return "STOCKS_MOMENTUM"
    # Unknown stock — default to momentum pool
    return "STOCKS_MOMENTUM"


def _pool_weights_file(pool: str) -> str:
    if pool == "XAUUSD":
        return "data/weights.json"
    return f"data/weights_{pool}.json"


def _pool_history_file(pool: str) -> str:
    if pool == "XAUUSD":
        return "data/trade_history.json"
    return f"data/trade_history_{pool}.json"


# ── Weights ───────────────────────────────────────────────────────────────────

def load_weights(symbol: str = "XAUUSD") -> dict:
    pool = symbol_to_pool(symbol)
    path = _pool_weights_file(pool)
    data, _ = _get_file(path)
    if data is None:
        print(f"[db] {path} not found — cloning XAUUSD weights as baseline.")
        # Transfer learning: clone gold weights so stocks start with learned priors
        gold, _ = _get_file("data/weights.json")
        if gold:
            cloned = dict(gold)
            cloned["symbol"] = pool
            cloned["total_wins"] = 0
            cloned["total_losses"] = 0
            cloned["updated_at"] = datetime.now(timezone.utc).isoformat()
            return cloned
        return dict(DEFAULT_WEIGHTS)
    return data


def save_weights(symbol: str, weights: dict) -> None:
    pool = symbol_to_pool(symbol)
    path = _pool_weights_file(pool)
    _, sha = _get_file(path)
    weights["updated_at"] = datetime.now(timezone.utc).isoformat()
    weights["symbol"] = pool
    _put_file(
        path,
        weights,
        sha,
        f"chore: update {pool} weights — wins={weights.get('total_wins',0)} losses={weights.get('total_losses',0)}",
    )


# ── Trade outcomes ─────────────────────────────────────────────────────────────

def insert_outcome(outcome: dict) -> None:
    pool = symbol_to_pool(outcome.get("symbol", "XAUUSD"))
    path = _pool_history_file(pool)
    history, sha = _get_file(path)
    if history is None:
        history = []
    outcome["id"] = str(uuid.uuid4())[:8]
    outcome["pool"] = pool
    outcome.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    history.append(outcome)
    if len(history) > 1000:
        history = history[-1000:]
    _put_file(
        path,
        history,
        sha,
        f"data: record {outcome['outcome']} {outcome.get('direction','')} {pool} trade",
    )


def recent_outcomes(symbol: str = "XAUUSD", limit: int = 200) -> list[dict]:
    pool = symbol_to_pool(symbol)
    path = _pool_history_file(pool)
    history, _ = _get_file(path)
    if not history:
        return []
    filtered = [t for t in history if symbol_to_pool(t.get("symbol", symbol)) == pool]
    return list(reversed(filtered))[:limit]


# ── News sentiment ─────────────────────────────────────────────────────────────

def insert_news(items: list[dict]) -> None:
    if not items:
        return
    cache, sha = _get_file("data/news_cache.json")
    if cache is None:
        cache = []
    now = datetime.now(timezone.utc)
    for item in items:
        item.setdefault("fetched_at", now.isoformat())
    cache.extend(items)
    # Keep last 200 news items
    if len(cache) > 200:
        cache = cache[-200:]
    _put_file("data/news_cache.json", cache, sha, "data: update news sentiment cache")


def recent_news(hours: int = 4) -> list[dict]:
    cache, _ = _get_file("data/news_cache.json")
    if not cache:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [
        n for n in cache
        if datetime.fromisoformat(n.get("fetched_at", "2000-01-01")).replace(tzinfo=timezone.utc) >= cutoff
    ]


# ── Signals ────────────────────────────────────────────────────────────────────

def insert_signal(signal: dict) -> dict:
    signals, sha = _get_file("data/signals.json")
    if signals is None:
        signals = []
    signal["id"] = len(signals) + 1
    signal.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    signals.append(signal)
    if len(signals) > 100:
        signals = signals[-100:]
    _put_file("data/signals.json", signals, sha, f"data: new {signal.get('direction','?')} signal")
    return signal


def expire_old_signals(symbol: str = "XAUUSD") -> None:
    # Handled passively — old signals are just overwritten in the file
    pass
