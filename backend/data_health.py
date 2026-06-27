"""
Central data-flow health registry.

Every external data fetch reports its outcome here via record(), so a stale or
failing source is visible at a glance (GET /data/health, hourly system check)
instead of silently degrading the signals/brief. Purely observational — it never
changes fetch behavior and record() can never raise into a caller.

In-memory only (resets on restart, like the rest of the scheduler state); the
hourly system check re-probes within an hour of any restart, and each source
re-reports the next time it runs.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

_lock = threading.Lock()
_state: dict = {}   # source -> status dict

# How long a source may go without a success before it's flagged "stale" (minutes).
# Keyed by category so slow-cadence sources (daily macro) aren't false-flagged.
_STALE_MIN = {
    "price": 180, "options": 180, "volatility": 180, "news": 30,
    "fundamentals": 1440, "calendar": 1440, "macro": 1440, "": 360,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record(source: str, ok: bool, category: str = "", detail: str = "",
           latency_ms: float | None = None) -> None:
    """Report one fetch outcome. Never raises — safe to call from any except block."""
    try:
        now_iso = _now().isoformat()
        with _lock:
            s = _state.setdefault(source, {
                "category": category, "ok": None, "fails": 0,
                "last_ok": None, "last_attempt": None, "last_error": "",
                "latency_ms": None,
            })
            if category:
                s["category"] = category
            s["ok"] = bool(ok)
            s["last_attempt"] = now_iso
            s["latency_ms"] = round(latency_ms, 1) if latency_ms is not None else s["latency_ms"]
            if ok:
                s["last_ok"] = now_iso
                s["fails"] = 0
                s["last_error"] = ""
            else:
                s["fails"] = int(s["fails"]) + 1
                if detail:
                    s["last_error"] = str(detail)[:200]
    except Exception:
        pass


def snapshot() -> dict:
    with _lock:
        return {k: dict(v) for k, v in _state.items()}


def _age_min(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return (_now() - datetime.fromisoformat(iso)).total_seconds() / 60.0
    except Exception:
        return None


def degraded() -> list[dict]:
    """Sources whose last attempt failed, or that haven't succeeded within the
    category's staleness window. Returns [] when everything is healthy."""
    out = []
    for src, s in snapshot().items():
        cat = s.get("category") or ""
        limit = _STALE_MIN.get(cat, _STALE_MIN[""])
        age = _age_min(s.get("last_ok"))
        failing = s.get("ok") is False
        stale = age is not None and age > limit
        never = s.get("last_ok") is None and s.get("last_attempt") is not None
        if failing or stale or never:
            out.append({
                "source": src, "category": cat,
                "fails": s.get("fails", 0),
                "minutes_since_ok": round(age, 1) if age is not None else None,
                "last_error": s.get("last_error", ""),
                "reason": "failing" if failing else ("never_succeeded" if never else "stale"),
            })
    out.sort(key=lambda x: (x["category"], x["source"]))
    return out


def report() -> dict:
    """Full health report for the /data/health endpoint."""
    snap = snapshot()
    deg = degraded()
    return {
        "checked_at": _now().isoformat(),
        "total_sources": len(snap),
        "healthy": len(snap) - len(deg),
        "degraded_count": len(deg),
        "degraded": deg,
        "sources": snap,
    }


def summary_line() -> str:
    """One-liner for the hourly system check. Empty string when all healthy."""
    deg = degraded()
    if not deg:
        return ""
    names = ", ".join(f"{d['source']}({d['reason']})" for d in deg[:8])
    return f"⚠️ Data flow: {len(deg)} source(s) degraded — {names}"
