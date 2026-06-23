"""
CNN Fear & Greed Index — single cross-asset risk-appetite number (0-100).

Free JSON endpoint, updates daily. Used as a SOFT regime/sentiment read across
all three sections (gold, stocks, options) — surfaced in health.json, the morning
brief, and the PWA. NOT a hard trade gate; it is contextual risk-appetite info.

Contrarian reads: <25 (extreme fear) often marks capitulation lows; >75 (extreme
greed) often marks froth. The middle band is neutral.

Network note: the CNN host must be reachable from the runtime egress. If it is
blocked or returns non-200, every function degrades gracefully to the last cached
value (or None) — nothing raises, nothing blocks.
"""
from __future__ import annotations

from datetime import datetime, timezone

_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://edition.cnn.com",
    "Referer": "https://edition.cnn.com/",
}

_FG_PATH = "data/fear_greed.json"
_cache: dict = {"score": None, "rating": None, "label": None,
                "previous_close": None, "updated_at": None}


def _label(score: float | None) -> str:
    if score is None:
        return "UNKNOWN"
    if score < 25:  return "EXTREME FEAR"
    if score < 45:  return "FEAR"
    if score <= 55: return "NEUTRAL"
    if score <= 75: return "GREED"
    return "EXTREME GREED"


def fetch_fear_greed() -> dict:
    """Fetch the latest Fear & Greed score, update + persist cache. Graceful no-op."""
    global _cache
    try:
        import httpx
        with httpx.Client(timeout=10, headers=_HEADERS) as c:
            r = c.get(_URL)
            if r.status_code != 200:
                print(f"[fear_greed] HTTP {r.status_code} — keeping cached value")
                return dict(_cache)
            fg = (r.json() or {}).get("fear_and_greed", {})
            score = fg.get("score")
            if score is None:
                return dict(_cache)
            score = round(float(score), 1)
            _cache = {
                "score":          score,
                "rating":         fg.get("rating"),
                "label":          _label(score),
                "previous_close": round(float(fg["previous_close"]), 1)
                                  if fg.get("previous_close") is not None else None,
                "updated_at":     datetime.now(timezone.utc).isoformat(),
            }
            try:
                from db import _get_file, _put_file
                _, sha = _get_file(_FG_PATH)
                _put_file(_FG_PATH, _cache, sha, "data: fear & greed update")
            except Exception as _pe:
                print(f"[fear_greed] persist failed (non-fatal): {_pe}")
    except Exception as e:
        print(f"[fear_greed] fetch failed: {e}")
    return dict(_cache)


def get_fear_greed() -> dict:
    """Return the last cached Fear & Greed reading (no network)."""
    return dict(_cache)


def load_fear_greed() -> None:
    """Restore the cached reading from the data branch on startup."""
    global _cache
    try:
        from db import _get_file
        data, _ = _get_file(_FG_PATH)
        if isinstance(data, dict) and data.get("score") is not None:
            _cache = data
            print(f"[startup] Fear & Greed loaded: {data.get('score')} ({data.get('label')})")
    except Exception as e:
        print(f"[fear_greed] load failed (non-fatal): {e}")
