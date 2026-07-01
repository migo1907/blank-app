"""
Strategy Lab — the system's autonomous measure → validate → improve loop.

Closes the self-improvement circle the pieces already hint at (self_diagnosis,
exit_optimizer, weekly autopsy) into one owned cycle:

  1. MEASURE   — segment_report(): rolling win%/PF by pool, trigger and session
                 from the live ledgers, with split-half agreement so a bleeding
                 segment must lose in BOTH halves before it is trusted as real.
  2. VALIDATE  — gate_calibration(): once gate scores are persisted on outcomes
                 (main.py attaches them at close), measures whether the backend
                 ensemble actually separates winners from losers on live labels.
  3. ACT (backend only, reversible) — auto_quarantine(): env-gated
                 (STRATEGY_AUTO_QUARANTINE, default OFF). Flagged segments get a
                 +ML-threshold bump written to data/strategy_config.json, which
                 score_entry_gate reads live. No Pine change, no code change,
                 regenerated every cycle → a segment that recovers is released
                 automatically. Thin pools are never touched (Rule 8).
  4. PROPOSE (Pine, never auto) — when the IBKR gateway is live, re-runs the
                 ladder + trail comparisons; any split-half-robust winner is
                 written to the lab report as a paste-ready proposal and pinged
                 to the owner. TradingView cannot be pushed to — a human paste
                 is the deploy step, so the lab's job is to arrive with proof.

Design: pure analysis functions take data as arguments (locally testable);
the impure lab_cycle() shell does the fetching/persisting/notifying. Never
raises out of lab_cycle; never blocks the event loop (callers use to_thread).
"""
from __future__ import annotations
import os
from datetime import datetime, timezone

MIN_SEGMENT_N   = 100    # a segment needs this many closed trades to be judged
BLEED_PF        = 0.70   # full-sample PF below this → candidate bleeder
BLEED_HALF_PF   = 0.85   # ...and BOTH halves must be below this (regime-robust)
QUARANTINE_BUMP = 0.08   # ML-threshold bump applied to quarantined segments
THIN_POOL_N     = 50     # Rule 8 — never quarantine below this
_CONFIG_PATH    = "data/strategy_config.json"
_REPORT_PATH    = "data/strategy_lab_report.json"


# ── pure analysis ──────────────────────────────────────────────────────────────

def _pf(trades) -> float | None:
    gw = sum(float(t.get("pnl_pct") or 0) for t in trades if float(t.get("pnl_pct") or 0) > 0)
    gl = -sum(float(t.get("pnl_pct") or 0) for t in trades if float(t.get("pnl_pct") or 0) <= 0)
    return round(gw / gl, 3) if gl > 0 else None


def _win(trades) -> float:
    if not trades:
        return 0.0
    return round(sum(1 for t in trades if float(t.get("pnl_pct") or 0) > 0) / len(trades) * 100, 1)


def _seg_stats(trades) -> dict:
    half = len(trades) // 2
    return {"n": len(trades), "win_pct": _win(trades), "pf": _pf(trades),
            "h1_pf": _pf(trades[:half]), "h2_pf": _pf(trades[half:])}


def segment_report(histories: dict[str, list[dict]]) -> dict:
    """histories: {pool: [closed trade rows, oldest→newest]}. Returns per-segment
    stats + the list of robust bleeders (real, both-halves-confirmed leaks)."""
    segments: dict[str, dict] = {}
    bleeders: list[dict] = []

    def _consider(key: str, trades: list[dict], kind: str, thin_guard_n: int):
        s = _seg_stats(trades)
        segments[key] = s
        pf, h1, h2 = s["pf"], s["h1_pf"], s["h2_pf"]
        if (s["n"] >= MIN_SEGMENT_N and thin_guard_n >= THIN_POOL_N
                and pf is not None and pf < BLEED_PF
                and (h1 is not None and h1 < BLEED_HALF_PF)
                and (h2 is not None and h2 < BLEED_HALF_PF)):
            bleeders.append({"segment": key, "kind": kind, **s})

    # per-pool
    for pool, hist in histories.items():
        _consider(f"pool:{pool}", hist, "pool", len(hist))
    # per-trigger and per-session across all pools (pool thinness irrelevant here)
    all_trades = [t for h in histories.values() for t in h]
    for field, kind in (("trigger", "trigger"), ("session", "session")):
        groups: dict[str, list[dict]] = {}
        for t in all_trades:
            v = str(t.get(field) or "?")
            groups.setdefault(v, []).append(t)
        for v, trades in groups.items():
            if v not in ("?", "", "UNKNOWN"):
                _consider(f"{kind}:{v}", trades, kind, len(trades))
    # per-hour (UTC) for stocks — IBKR backtest 2026-07-01 found the NY lunch hour
    # (17:00 UTC) bleeding -0.26%/trade across 85 entries; hour segments let the
    # quarantine catch time-of-day leaks the coarse session buckets blur over.
    hgroups: dict[str, list[dict]] = {}
    for t in all_trades:
        if str(t.get("pool", "")).startswith("XAUUSD"):
            continue
        ts = str(t.get("created_at") or "")
        if len(ts) >= 13 and ts[11:13].isdigit():
            hgroups.setdefault(f"stock_hour:{ts[11:13]}", []).append(t)
    for key, trades in hgroups.items():
        _consider(key, trades, "hour", len(trades))

    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "segments": segments, "bleeders": bleeders}


def gate_calibration(histories: dict[str, list[dict]]) -> dict:
    """Do persisted backend gate scores separate winners on live labels?
    Buckets outcomes by gate_score; needs main.py's gate-score attachment to
    have been live long enough. Returns {'n_scored': .., 'buckets': [...]}"""
    scored = [t for h in histories.values() for t in h if t.get("gate_score") is not None]
    buckets = []
    for lo, hi in ((0.0, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 1.01)):
        b = [t for t in scored if lo <= float(t["gate_score"]) < hi]
        if b:
            buckets.append({"range": f"{lo:.2f}-{hi:.2f}", "n": len(b),
                            "win_pct": _win(b), "pf": _pf(b)})
    return {"n_scored": len(scored), "buckets": buckets}


def build_quarantine(report: dict) -> dict:
    """Bleeders → per-segment ML-threshold bumps. Regenerated whole each cycle:
    recovery releases the bump automatically."""
    return {"generated_at": report["generated_at"],
            "note": "auto-quarantine: ML-threshold bumps for both-halves-confirmed "
                    "bleeding segments; regenerated every lab cycle",
            "segment_bumps": {b["segment"]: QUARANTINE_BUMP for b in report["bleeders"]}}


# ── impure shell (scheduled) ───────────────────────────────────────────────────

def _fetch_histories(limit: int = 400) -> dict[str, list[dict]]:
    from db import recent_outcomes
    from ml_ensemble import GOLD_TF_IDS, STOCK_POOL_IDS
    pools = list(GOLD_TF_IDS.keys()) + list(STOCK_POOL_IDS.keys())
    out = {}
    for p in pools:
        try:
            hist = recent_outcomes(p, limit)          # newest-first
            closed = [t for t in reversed(hist)       # oldest→newest for halves
                      if t.get("outcome") in ("WIN", "LOSS", "PARTIAL")]
            if closed:
                out[p] = closed
        except Exception as e:
            print(f"[lab] fetch {p} failed: {e}")
    return out


def quarantine_enabled() -> bool:
    """ON by default (owner-approved 2026-07-01). Set STRATEGY_AUTO_QUARANTINE=false
    in Railway to disable. Bumps are threshold-raises only, regenerated weekly,
    thin pools never touched — the safe end of autonomy."""
    return os.environ.get("STRATEGY_AUTO_QUARANTINE", "true").lower() in ("1", "true", "yes")


def lab_cycle() -> dict:
    """Weekly cycle: measure → calibrate → (optionally) quarantine → report.
    Returns the report dict; persists to data branch; never raises."""
    try:
        histories = _fetch_histories()
        report = segment_report(histories)
        report["gate_calibration"] = gate_calibration(histories)
        report["quarantine_active"] = quarantine_enabled()

        # IBKR gateway live? re-validate exits on fresh bars (proposal-only).
        try:
            import ibkr_data
            if ibkr_data.available():
                import ibkr_backtest
                proposals = []
                for sym, tf in (("XAUUSD", "5"), ("XAUUSD", "30"), ("QQQ", "15"),
                                ("SPY", "30"), ("XAUUSD", "60")):
                    r = ibkr_backtest.run_live(sym, tf)
                    el = (r or {}).get("exit_ladders") or {}
                    if el.get("status") == "complete" and el.get("beats_current") \
                            and el.get("flips_positive"):
                        proposals.append({"symbol": sym, "tf": tf,
                                          "recommended": el["best"]["multipliers"],
                                          "gain": el.get("expectancy_gain")})
                report["pine_proposals"] = proposals
        except Exception as e:
            print(f"[lab] ibkr revalidation skipped: {e}")

        # persist report + (flag-gated) quarantine config
        try:
            import db
            _, sha = db._get_file(_REPORT_PATH)
            db._put_file(_REPORT_PATH, report, sha, "strategy lab report")
            if quarantine_enabled():
                q = build_quarantine(report)
                _, qsha = db._get_file(_CONFIG_PATH)
                db._put_file(_CONFIG_PATH, q, qsha, "strategy lab quarantine config")
        except Exception as e:
            print(f"[lab] persist failed: {e}")

        # owner summary (only when there is something actionable)
        try:
            n_bleed = len(report["bleeders"])
            n_prop = len(report.get("pine_proposals", []))
            if n_bleed or n_prop:
                lines = [f"🧪 Strategy Lab — {n_bleed} bleeding segment(s), "
                         f"{n_prop} validated Pine proposal(s)"]
                for b in report["bleeders"][:6]:
                    lines.append(f"• {b['segment']}: n={b['n']} PF={b['pf']} "
                                 f"(halves {b['h1_pf']}/{b['h2_pf']})"
                                 + (" → quarantined" if quarantine_enabled() else ""))
                for p in report.get("pine_proposals", [])[:4]:
                    lines.append(f"• PASTE-READY {p['symbol']} {p['tf']}m → {p['recommended']}")
                import asyncio
                from telegram_bot import send_owner_message
                asyncio.get_event_loop().create_task(
                    send_owner_message("\n".join(lines),
                                       action="review data/strategy_lab_report.json"))
        except Exception as e:
            print(f"[lab] notify failed: {e}")

        print(f"[lab] cycle complete: {len(report['segments'])} segments, "
              f"{len(report['bleeders'])} bleeders, quarantine={'ON' if quarantine_enabled() else 'off'}")
        return report
    except Exception as e:
        print(f"[lab] cycle failed: {e}")
        return {"error": str(e)}


# ── live gate hook ─────────────────────────────────────────────────────────────

_cfg_cache: tuple[float, dict] | None = None


def threshold_bump(pool: str, trigger: str = "", session: str = "") -> float:
    """Quarantine bump for this entry's segments (max of matching bumps).
    10-min cached read of strategy_config.json; graceful 0.0 on any failure."""
    global _cfg_cache
    import time
    if not quarantine_enabled():
        return 0.0
    try:
        now = time.monotonic()
        if _cfg_cache is None or (now - _cfg_cache[0]) > 600:
            import db
            content, _ = db._get_file(_CONFIG_PATH)
            _cfg_cache = (now, content if isinstance(content, dict) else {})
        bumps = _cfg_cache[1].get("segment_bumps", {})
        keys = [f"pool:{pool}"]
        if trigger:
            keys.append(f"trigger:{trigger}")
        if session:
            keys.append(f"session:{session}")
        if not pool.startswith("XAUUSD"):
            keys.append(f"stock_hour:{datetime.now(timezone.utc).strftime('%H')}")
        return max([float(bumps.get(k, 0.0)) for k in keys] + [0.0])
    except Exception:
        return 0.0
