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


def _parse_ts(ts: str) -> datetime:
    """Parse ISO timestamp to timezone-aware UTC datetime, safe for both naive and aware strings."""
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ── Low-level GitHub file API ─────────────────────────────────────────────────

def _github_retry_wait(resp) -> None:
    """Sleep if GitHub signals rate limiting via Retry-After or x-ratelimit-reset headers."""
    import time
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            time.sleep(min(int(retry_after), 60))
            return
        except (ValueError, TypeError):
            pass
    reset = resp.headers.get("x-ratelimit-reset")
    if reset:
        try:
            wait = max(0, int(reset) - int(time.time()))
            time.sleep(min(wait, 60))
        except (ValueError, TypeError):
            pass


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
    if resp.status_code in (403, 429):
        _github_retry_wait(resp)
        resp.raise_for_status()
    resp.raise_for_status()
    data = resp.json()
    content = json.loads(base64.b64decode(data["content"]).decode())
    return content, data["sha"]


def _put_file(path: str, content: dict | list, sha: str | None, message: str) -> None:
    """Create or update a file in the repo. Retries on 409 SHA conflict (re-fetches SHA)."""
    encoded = base64.b64encode(json.dumps(content, indent=2).encode()).decode()
    current_sha = sha
    for attempt in range(3):
        payload: dict = {
            "message": message,
            "content": encoded,
            "branch":  GITHUB_BRANCH,
        }
        if current_sha:
            payload["sha"] = current_sha
        with httpx.Client(timeout=15) as client:
            resp = client.put(
                f"{BASE_URL}/repos/{GITHUB_REPO}/contents/{path}",
                headers=HEADERS,
                json=payload,
            )
        if resp.status_code in (403, 429) and attempt < 2:
            _github_retry_wait(resp)
            continue
        if resp.status_code == 409 and attempt < 2:
            # SHA stale — re-fetch and retry
            _, current_sha = _get_file(path)
            continue
        if resp.status_code == 422 and attempt < 2:
            # Unprocessable — re-fetch SHA/state and retry after short wait
            import time as _time; _time.sleep(0.5)
            _, current_sha = _get_file(path)
            continue
        resp.raise_for_status()
        return


# ── Symbol → ML pool routing ───────────────────────────────────────────────────

STOCKS_MOMENTUM = {
    "TSLA","TSLL","MSTR","UPST","HTZ","SMCI","BLNK","PLUG","HOOD",
    "BBAI","PLTR","SOXL","TNA","AMD","MU","NVDA","RR",
}
STOCKS_QUALITY = {
    "META","GOOGL","GOOG","MSFT","AAPL","ADBE","IBKR","PATH","NOW","CRM",
}
STOCKS_INDEX = {"QQQ","SPY","SPX"}


def symbol_to_pool(symbol: str, timeframe: str = "") -> str:
    """Map a ticker + timeframe to its ML pool name."""
    ticker = symbol.split(":")[-1].upper()

    # Normalise TradingView timeframe.period → suffix
    # TradingView sends minutes as strings: "2","5","30","60","240"
    def _tf_suffix(tf: str) -> str:
        t = str(tf).strip().upper().replace("MIN","").replace("H","")
        if t in ("1", "2"):          return "2M"
        if t in ("3", "4", "5"):     return "5M"
        if t in ("15",):             return "15M"
        if t in ("20", "30"):        return "30M"
        if t in ("60",):             return "1H"
        if t in ("240",):            return "4H"
        return ""

    suffix = _tf_suffix(timeframe) if timeframe else ""

    if ticker in ("XAUUSD", "GOLD", "GC"):
        return f"XAUUSD_{suffix}" if suffix else "XAUUSD"
    if ticker in STOCKS_INDEX:
        base = "STOCKS_INDEX"
    elif ticker in STOCKS_QUALITY:
        base = "STOCKS_QUALITY"
    elif ticker in STOCKS_MOMENTUM:
        base = "STOCKS_MOMENTUM"
    else:
        base = "STOCKS_MOMENTUM"
    return f"{base}_{suffix}" if suffix else base


def _pool_weights_file(pool: str) -> str:
    if pool == "XAUUSD":
        return "data/weights.json"
    return f"data/weights_{pool}.json"


def _pool_history_file(pool: str) -> str:
    if pool == "XAUUSD":
        return "data/trade_history.json"
    return f"data/trade_history_{pool}.json"


# ── Weights ───────────────────────────────────────────────────────────────────

def load_weights(pool: str = "XAUUSD") -> dict:
    path = _pool_weights_file(pool)
    data, _ = _get_file(path)
    if data is None:
        print(f"[db] {path} not found — cloning XAUUSD baseline weights.")
        # Transfer learning: all new pools start from XAUUSD legacy weights
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


def save_weights(pool: str, weights: dict) -> None:
    path = _pool_weights_file(pool)
    weights["updated_at"] = datetime.now(timezone.utc).isoformat()
    weights["symbol"] = pool
    msg = f"chore: update {pool} weights — wins={weights.get('total_wins',0)} losses={weights.get('total_losses',0)}"
    for attempt in range(3):
        _, sha = _get_file(path)  # always re-fetch SHA to avoid overwriting concurrent updates
        try:
            _put_file(path, weights, sha, msg)
            return
        except Exception as e:
            if attempt < 2 and "409" in str(e):
                continue
            raise


# ── Trade outcomes ─────────────────────────────────────────────────────────────

def insert_outcome(outcome: dict) -> None:
    pool = symbol_to_pool(outcome.get("symbol", "XAUUSD"), outcome.get("timeframe", ""))
    path = _pool_history_file(pool)

    outcome.setdefault("id",         str(uuid.uuid4())[:8])
    outcome.setdefault("pool",       pool)
    outcome.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    dedup_key = (
        f"{outcome.get('symbol','')}|{outcome.get('direction','')}|"
        f"{outcome.get('entry_price',0)}|{outcome.get('timeframe','')}|"
        f"{outcome.get('exit_price',0)}"
    )

    for attempt in range(3):
        history, sha = _get_file(path)
        if history is None:
            history = []

        existing_keys = {
            f"{t.get('symbol','')}|{t.get('direction','')}|{t.get('entry_price',0)}|{t.get('timeframe','')}"
            for t in history
        }
        if dedup_key in existing_keys:
            print(f"[db] Duplicate trade skipped: {dedup_key} pool={pool}")
            return

        history.append(outcome)
        if len(history) > 1000:
            history = history[-1000:]
        try:
            _put_file(
                path,
                history,
                sha,
                f"data: record {outcome['outcome']} {outcome.get('direction','')} {pool} trade",
            )
            return
        except Exception as e:
            if attempt < 2 and "409" in str(e):
                continue  # SHA stale — re-fetch and retry
            raise


def recent_outcomes(pool: str = "XAUUSD", limit: int = 200) -> list[dict]:
    path = _pool_history_file(pool)
    history, _ = _get_file(path)
    if not history:
        return []
    return list(reversed(history))[:limit]


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
        if _parse_ts(n.get("fetched_at", "2000-01-01T00:00:00+00:00")) >= cutoff
    ]


# ── Signals ────────────────────────────────────────────────────────────────────

def insert_signal(signal: dict) -> dict:
    signal.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    for attempt in range(3):
        signals, sha = _get_file("data/signals.json")
        if signals is None:
            signals = []
        if "id" not in signal:  # assign ID once — don't mutate on retry
            signal["id"] = len(signals) + 1
        signals.append(signal)
        if len(signals) > 100:
            signals = signals[-100:]
        try:
            _put_file("data/signals.json", signals, sha, f"data: new {signal.get('direction','?')} signal")
            return signal
        except Exception as e:
            if attempt < 2 and "409" in str(e):
                signals = []            # reset so next attempt re-fetches clean list
                signal.pop("id", None)  # re-assign ID from fresh list on next iteration
                continue
            raise
    return signal


def expire_old_signals(symbol: str = "XAUUSD") -> None:
    """Mark ACTIVE signals past their expires_at as EXPIRED in the signals file."""
    now = datetime.now(timezone.utc)
    try:
        signals, sha = _get_file("data/signals.json")
        if not isinstance(signals, list):
            return
        changed = False
        for s in signals:
            if s.get("status") != "ACTIVE":
                continue
            try:
                exp = _parse_ts(s.get("expires_at", "2000-01-01T00:00:00+00:00"))
                if now > exp:
                    s["status"] = "EXPIRED"
                    changed = True
            except Exception:
                continue
        if changed:
            _put_file("data/signals.json", signals, sha, "chore: expire stale ACTIVE signals")
    except Exception as e:
        print(f"[db] expire_old_signals failed (non-fatal): {e}")


_WEBHOOK_LOG_PATH = "data/webhook_log.json"
_WEBHOOK_LOG_MAX  = 2000  # keep last 2000 trade-close entries

def log_raw_webhook(payload: dict) -> None:
    """
    Append raw trade-close webhooks to data/webhook_log.json.
    Only stores payloads with exit_price (actual closes, not signal entries).
    Capped at _WEBHOOK_LOG_MAX entries (oldest dropped first).
    Never raises — logging must not block or break the main flow.
    """
    # Only log trade closes — signal entries (no exit_price) can't be repaired and waste space
    if not payload.get("exit_price"):
        return
    try:
        entry = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "payload":     payload,
        }
        for attempt in range(3):
            log, sha = _get_file(_WEBHOOK_LOG_PATH)
            if not isinstance(log, list):
                log = []
            log.append(entry)
            if len(log) > _WEBHOOK_LOG_MAX:
                log = log[-_WEBHOOK_LOG_MAX:]
            try:
                _put_file(_WEBHOOK_LOG_PATH, log, sha, "chore: webhook log")
                break
            except Exception as put_err:
                if attempt < 2 and "409" in str(put_err):
                    continue
                raise put_err
    except Exception as e:
        print(f"[webhook_log] Failed to log payload: {e}")


def repair_missing_trades() -> list[str]:
    """
    Read webhook_log.json, compare each logged payload against the pool it belongs to.
    Any payload not found in the pool → insert it automatically.
    Returns a list of repair messages (one per inserted trade).
    Match key: symbol + direction + entry_price + timeframe (unique per trade).
    """
    repaired = []
    try:
        log, _ = _get_file(_WEBHOOK_LOG_PATH)
        if not isinstance(log, list) or not log:
            return repaired

        # Build a set of existing trade keys per pool for fast lookup
        pool_keys: dict[str, set] = {}

        def _get_pool_keys(pool: str) -> set:
            if pool not in pool_keys:
                path = _pool_history_file(pool)
                hist, _ = _get_file(path)
                if isinstance(hist, list):
                    pool_keys[pool] = {
                        f"{t.get('symbol','')}|{t.get('direction','')}|{t.get('entry_price',0)}|{t.get('timeframe','')}"
                        for t in hist
                    }
                else:
                    pool_keys[pool] = set()
            return pool_keys[pool]

        _pending: dict[str, list] = {}

        for entry in log:
            p = entry.get("payload", {})
            outcome = p.get("outcome", "")
            # Only process trade closes — skip heartbeats, signal entries, and progress events
            outcome_up = outcome.upper()
            if not outcome or outcome_up in ("HEARTBEAT", ""):
                continue
            if p.get("trade_id") == "heartbeat":
                continue
            if outcome_up in ("TP1_HIT", "TP2_HIT", "PROGRESS"):
                continue
            # Skip if no exit price (signal entry, not a close)
            if not p.get("exit_price"):
                continue

            symbol    = p.get("symbol", "") or ""
            if not symbol:
                # Infer symbol from trade_id prefix: "SPY_123" → "SPY"
                tid = p.get("trade_id", "") or ""
                prefix = tid.split("_")[0] if "_" in tid else ""
                if not prefix:
                    print(f"[auto-repair] Skipping entry — no symbol and no recoverable trade_id prefix")
                    continue
                symbol = prefix
            direction = p.get("direction", "")
            entry_px  = float(p.get("entry_price", 0) or 0)
            exit_px   = float(p.get("exit_price", 0) or 0)
            timeframe = str(p.get("timeframe", "") or "")

            if not direction or entry_px == 0:
                continue

            pool    = symbol_to_pool(symbol, timeframe)
            key     = f"{symbol}|{direction}|{entry_px}|{timeframe}"
            keys    = _get_pool_keys(pool)

            if key in keys:
                continue  # already stored — skip

            # Reconstruct trade record and insert
            raw_pct = (exit_px - entry_px) / max(entry_px, 0.0001) * 100
            pnl_pct = raw_pct if direction == "LONG" else -raw_pct

            # Normalize outcome
            norm = outcome_up.strip()
            if norm in ("WIN", "TP3", "TP2", "TP1"):           norm = "WIN"
            elif norm in ("LOSS", "SL"):                        norm = "LOSS"
            elif norm in ("PARTIAL", "SL_TP1", "SL_TP2",
                          "SL_TP3", "TP1_SL", "TP2_SL"):       norm = "PARTIAL"
            else:                                               norm = "LOSS"

            trade_row: dict = {
                "symbol":       symbol,
                "direction":    direction,
                "trigger":      p.get("trigger", "") or "",
                "entry_price":  entry_px,
                "exit_price":   exit_px,
                "outcome":      norm,
                "ml_outcome":   p.get("ml_outcome") or norm,
                "mfe":          float(p.get("mfe", 0) or 0),
                "tp_stage":     p.get("tp_stage", "") or "",
                "timeframe":    timeframe,
                "pnl_pct":      round(pnl_pct, 4),
                "ml_bull_score": float(p.get("ml_score", 0.5) or 0.5),
                "created_at":   entry.get("received_at", datetime.now(timezone.utc).isoformat()),
                "_repaired":    True,
            }
            # Attach features f1-f25
            for i in range(1, 26):
                trade_row[f"f{i}"] = float(p.get(f"f{i}", 0) or 0)

            # Batch: accumulate rows per pool, write once per pool at the end
            pool_keys[pool].add(key)
            _pending.setdefault(pool, []).append(trade_row)
            msg = f"[auto-repair] Queued missing {norm} {direction} {symbol} {timeframe}m entry={entry_px} pool={pool}"
            print(msg)
            repaired.append(msg)

        # Flush batched rows — one GitHub read+write per pool
        for _pool, rows in _pending.items():
            try:
                path = _pool_history_file(_pool)
                for attempt in range(3):
                    history, sha = _get_file(path)
                    if history is None:
                        history = []
                    existing_keys = {
                        f"{t.get('symbol','')}|{t.get('direction','')}|{t.get('entry_price',0)}|{t.get('timeframe','')}"
                        for t in history
                    }
                    for row in rows:
                        dk = f"{row.get('symbol','')}|{row.get('direction','')}|{row.get('entry_price',0)}|{row.get('timeframe','')}"
                        if dk not in existing_keys:
                            row.setdefault("id", str(uuid.uuid4())[:8])
                            row.setdefault("pool", _pool)
                            row.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                            history.append(row)
                            existing_keys.add(dk)
                    if len(history) > 1000:
                        history = history[-1000:]
                    try:
                        _put_file(path, history, sha, f"data: auto-repair batch {_pool} +{len(rows)}")
                        break
                    except Exception as e:
                        if attempt < 2 and "409" in str(e):
                            continue
                        raise
            except Exception as e:
                print(f"[auto-repair] Batch flush failed for {_pool}: {e}")

    except Exception as e:
        print(f"[auto-repair] repair_missing_trades failed: {e}")

    return repaired
