"""
In-memory HTF bias store with GitHub persistence.

When a 30M/1H/4H signal fires, it is stored here instead of sent to Telegram.
When a 2M/5M signal fires in the same direction, the bias is confirmed and the
LTF signal is sent with the HTF label attached.

Expiry windows: 30M=2h, 1H=4h (60min), 4H=8h (240min)

Persistence: bias store is saved to data/htf_bias.json on every write and
loaded on startup — survives Railway restarts.

Key: "{symbol}_{tf}" — one entry per symbol+timeframe pair so 30M and 1H biases
coexist independently without overwriting each other.
"""
import threading
from datetime import datetime, timezone, timedelta

_bias_store: dict[str, dict] = {}
_bias_lock  = threading.Lock()

# Accept both numeric strings and shorthand labels from Pine Script
_HTF_TIMEFRAMES = {"30", "60", "240", "1H", "4H", "1h", "4h"}
_EXPIRY_HOURS   = {"30": 2, "60": 4, "240": 8, "1H": 4, "4H": 8, "1h": 4, "4h": 8}
_GITHUB_PATH    = "data/htf_bias.json"


def _normalize_tf(timeframe: str) -> str:
    """Normalize timeframe to canonical numeric string."""
    tf = str(timeframe).strip()
    return {"1H": "60", "1h": "60", "4H": "240", "4h": "240"}.get(tf, tf)


def _normalize_symbol(symbol: str) -> str:
    """Strip exchange prefix so 'TVC:GOLD' and 'ICMARKETS:XAUUSD' both resolve to the bare ticker."""
    return symbol.split(":")[-1].upper()


def is_htf(timeframe: str) -> bool:
    return _normalize_tf(timeframe) in {"30", "60", "240"}


def _parse_ts(ts: str) -> datetime:
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _do_persist() -> None:
    """Blocking GitHub write — always called from a background thread."""
    with _bias_lock:
        snapshot = dict(_bias_store)
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_GITHUB_PATH)
        _put_file(_GITHUB_PATH, snapshot, sha, "chore: update htf_bias store")
    except Exception as e:
        print(f"[htf_bias] persist failed (non-fatal): {e}")


def _persist() -> None:
    """Fire-and-forget persist — spawns a daemon thread so the event loop is never blocked."""
    t = threading.Thread(target=_do_persist, daemon=True)
    t.start()


def load_bias_store() -> None:
    """Load persisted bias store from GitHub on startup. Discards expired entries."""
    global _bias_store
    try:
        from db import _get_file
        data, _ = _get_file(_GITHUB_PATH)
        if not isinstance(data, dict):
            return
        now = datetime.now(timezone.utc)
        loaded = {}
        for key, bias in data.items():
            try:
                expires = _parse_ts(bias["expires_at"])
                if now < expires:
                    loaded[key] = bias
            except Exception:
                continue
        with _bias_lock:
            _bias_store = loaded
        if loaded:
            print(f"[htf_bias] Loaded {len(loaded)} active bias(es) from GitHub: {list(loaded.keys())}")
    except Exception as e:
        print(f"[htf_bias] load failed (non-fatal): {e}")


def store_bias(symbol: str, direction: str, timeframe: str, trigger: str = "", ml_score: float = 0.5) -> None:
    sym   = _normalize_symbol(symbol)
    tf    = _normalize_tf(timeframe)
    hours = _EXPIRY_HOURS.get(tf, 2)
    key   = f"{sym}_{tf}"
    with _bias_lock:
        existing = _bias_store.get(key)
        if existing and existing["direction"] != direction:
            print(f"[htf_bias] ⚠ Direction flip for {sym} TF={tf}m: {existing['direction']} → {direction} — previous bias overwritten")
        _bias_store[key] = {
            "direction":  direction,
            "timeframe":  tf,
            "symbol":     sym,
            "trigger":    trigger,
            "ml_score":   ml_score,
            "stored_at":  datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(),
        }
    print(f"[htf_bias] Stored {direction} bias for {sym} TF={tf}m expires_in={hours}h")
    _persist()


def get_active_bias(symbol: str, direction: str) -> dict | None:
    """Return the most recent non-expired bias matching symbol+direction across all HTF timeframes."""
    sym = _normalize_symbol(symbol)
    now = datetime.now(timezone.utc)
    best: dict | None = None
    expired_keys = []

    with _bias_lock:
        for key, bias in list(_bias_store.items()):
            if not key.startswith(f"{sym}_"):
                continue
            try:
                expires = _parse_ts(bias["expires_at"])
            except Exception:
                expired_keys.append(key)
                continue
            if now > expires:
                expired_keys.append(key)
                continue
            if bias["direction"] != direction:
                continue
            # Pick the bias with the longest remaining validity (most recent HTF confirmation)
            if best is None or expires > _parse_ts(best["expires_at"]):
                best = bias

        for k in expired_keys:
            _bias_store.pop(k, None)
            print(f"[htf_bias] Bias expired: {k}")

    if expired_keys:
        _persist()
    return best


def bias_remaining_label(bias: dict) -> str:
    """Human-readable time remaining, e.g. '1h 40m'."""
    expires   = _parse_ts(bias["expires_at"])
    remaining = expires - datetime.now(timezone.utc)
    total_mins = max(0, int(remaining.total_seconds() // 60))
    h, m = divmod(total_mins, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def tf_label(tf: str) -> str:
    return {"30": "30M", "60": "1H", "240": "4H"}.get(_normalize_tf(tf), f"{tf}M")
