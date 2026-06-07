"""
In-memory HTF bias store with GitHub persistence.

When a 30M/1H/4H signal fires, it is stored here instead of sent to Telegram.
When a 2M/5M signal fires in the same direction, the bias is confirmed and the
LTF signal is sent with the HTF label attached.

Expiry windows: 30M=2h, 1H=4h (60min), 4H=8h (240min)

Persistence: bias store is saved to data/htf_bias.json on every write and
loaded on startup — survives Railway restarts.
"""
import threading
from datetime import datetime, timezone, timedelta

_bias_store: dict[str, dict] = {}

_HTF_TIMEFRAMES = {"30", "60", "240"}
_EXPIRY_HOURS   = {"30": 2, "60": 4, "240": 8}
_GITHUB_PATH    = "data/htf_bias.json"


def is_htf(timeframe: str) -> bool:
    return str(timeframe).strip() in _HTF_TIMEFRAMES


def _do_persist() -> None:
    """Blocking GitHub write — always called from a background thread."""
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_GITHUB_PATH)
        _put_file(_GITHUB_PATH, _bias_store, sha, "chore: update htf_bias store")
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
        for sym, bias in data.items():
            try:
                expires = datetime.fromisoformat(bias["expires_at"])
                if now < expires:
                    loaded[sym] = bias
            except Exception:
                continue
        _bias_store = loaded
        if loaded:
            print(f"[htf_bias] Loaded {len(loaded)} active bias(es) from GitHub: {list(loaded.keys())}")
    except Exception as e:
        print(f"[htf_bias] load failed (non-fatal): {e}")


def store_bias(symbol: str, direction: str, timeframe: str, trigger: str = "", ml_score: float = 0.5) -> None:
    tf    = str(timeframe).strip()
    hours = _EXPIRY_HOURS.get(tf, 2)
    existing = _bias_store.get(symbol)
    if existing and existing["direction"] != direction:
        print(f"[htf_bias] ⚠ Direction flip for {symbol}: {existing['direction']} → {direction} TF={tf}m — previous bias overwritten")
    _bias_store[symbol] = {
        "direction":  direction,
        "timeframe":  tf,
        "trigger":    trigger,
        "ml_score":   ml_score,
        "stored_at":  datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(),
    }
    print(f"[htf_bias] Stored {direction} bias for {symbol} TF={tf}m expires_in={hours}h")
    _persist()


def get_active_bias(symbol: str, direction: str) -> dict | None:
    """Return the stored bias if it matches direction and hasn't expired."""
    bias = _bias_store.get(symbol)
    if not bias:
        return None
    expires = datetime.fromisoformat(bias["expires_at"])
    if datetime.now(timezone.utc) > expires:
        _bias_store.pop(symbol, None)
        print(f"[htf_bias] Bias expired for {symbol}")
        _persist()
        return None
    if bias["direction"] != direction:
        return None
    return bias


def bias_remaining_label(bias: dict) -> str:
    """Human-readable time remaining, e.g. '1h 40m'."""
    expires = datetime.fromisoformat(bias["expires_at"])
    remaining = expires - datetime.now(timezone.utc)
    total_mins = max(0, int(remaining.total_seconds() // 60))
    h, m = divmod(total_mins, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def tf_label(tf: str) -> str:
    return {"30": "30M", "60": "1H", "240": "4H"}.get(tf, f"{tf}M")
