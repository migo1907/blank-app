"""
Memory-pressure guard.

On the Railway Hobby plan the ML stack (sklearn + LightGBM + pandas + HMM,
retraining in-process) can approach the container memory ceiling and get
OOM-killed. Those restarts are what caused the in-memory-state bugs this session
(duplicate alerts, regime UNKNOWN). This module gives an early warning: it reads
the process RSS and the container's cgroup memory limit, and the hourly system
check raises a Telegram alert when usage crosses a threshold — so you hear about
it *before* an OOM restart instead of finding out from a bug.

Pure stdlib (no psutil dependency). Every function is best-effort and never raises.
"""

from __future__ import annotations

# Alert when RSS exceeds this fraction of the container memory limit.
_WARN_FRACTION = 0.85


def _rss_bytes() -> int | None:
    """Resident set size of this process, from /proc (Linux)."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024   # kB → bytes
    except Exception:
        pass
    return None


def _limit_bytes() -> int | None:
    """Container memory limit from cgroup v2 then v1. None if unbounded/unknown."""
    # cgroup v2
    try:
        with open("/sys/fs/cgroup/memory.max") as f:
            v = f.read().strip()
            if v and v != "max":
                n = int(v)
                if 0 < n < (1 << 62):
                    return n
    except Exception:
        pass
    # cgroup v1
    try:
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes") as f:
            n = int(f.read().strip())
            if 0 < n < (1 << 62):   # v1 reports a huge sentinel when unbounded
                return n
    except Exception:
        pass
    return None


def memory_status() -> dict:
    """Current memory picture. Keys: rss_mb, limit_mb, pct, ok, warn."""
    rss = _rss_bytes()
    lim = _limit_bytes()
    out = {"rss_mb": round(rss / 1e6, 1) if rss else None,
           "limit_mb": round(lim / 1e6, 1) if lim else None,
           "pct": None, "ok": rss is not None, "warn": False}
    if rss and lim:
        pct = rss / lim
        out["pct"] = round(pct * 100, 1)
        out["warn"] = pct >= _WARN_FRACTION
    return out


def status_line() -> str:
    """One-liner for the hourly system check. '' when memory can't be read."""
    s = memory_status()
    if s["rss_mb"] is None:
        return ""
    if s["limit_mb"] is None:
        return f"Memory — {s['rss_mb']:.0f} MB RSS (no container limit detected) ✅"
    flag = "⚠️ HIGH" if s["warn"] else "✅"
    return f"Memory — {s['rss_mb']:.0f}/{s['limit_mb']:.0f} MB ({s['pct']:.0f}%) {flag}"


def is_pressured() -> bool:
    """True when RSS is at/above the warn fraction of the container limit."""
    return bool(memory_status().get("warn"))
