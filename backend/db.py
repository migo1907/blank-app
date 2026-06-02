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


# ── Weights ───────────────────────────────────────────────────────────────────

def load_weights(symbol: str = "XAUUSD") -> dict:
    data, _ = _get_file("data/weights.json")
    if data is None:
        print("[db] weights.json not found — using defaults.")
        return dict(DEFAULT_WEIGHTS)
    return data


def save_weights(symbol: str, weights: dict) -> None:
    _, sha = _get_file("data/weights.json")
    weights["updated_at"] = datetime.now(timezone.utc).isoformat()
    weights["symbol"] = symbol
    _put_file(
        "data/weights.json",
        weights,
        sha,
        f"chore: update adaptive weights — wins={weights.get('total_wins',0)} losses={weights.get('total_losses',0)}",
    )


# ── Trade outcomes ─────────────────────────────────────────────────────────────

def insert_outcome(outcome: dict) -> None:
    history, sha = _get_file("data/trade_history.json")
    if history is None:
        history = []
    # UUID prevents duplicate IDs when concurrent webhooks fire simultaneously
    outcome["id"] = str(uuid.uuid4())[:8]
    outcome.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    history.append(outcome)
    # Keep last 1000 trades to avoid huge files
    if len(history) > 1000:
        history = history[-1000:]
    _put_file(
        "data/trade_history.json",
        history,
        sha,
        f"data: record {outcome['outcome']} {outcome.get('direction','')} trade",
    )


def recent_outcomes(symbol: str = "XAUUSD", limit: int = 200) -> list[dict]:
    history, _ = _get_file("data/trade_history.json")
    if not history:
        return []
    # Include trades with matching symbol OR backtest trades (no symbol field)
    filtered = [t for t in history if t.get("symbol", symbol) == symbol]
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
