"""
Self-diagnosis engine — per-pool failure-mode autopsy, SHADOW/ADVISORY only.

The ML learns entry direction; exit_optimizer.py learns TP/SL. This module answers
the missing question: for each pool, WHY does it bleed? It classifies every losing
trade into a single dominant failure mode, finds the pool's dominant leak, and routes
a concrete recommended fix — backend-adaptable vs Pine-paste-required.

ADVISORY ONLY: writes a diagnosis + recommendations to data/self_diagnosis.json on the
data branch. It NEVER mutates live trading (Rule 4 — verify before changing live).
Pine-level fixes are flagged (`pine_change_required`) for a human to paste.

Failure-mode buckets (classified per LOSS / scratched PARTIAL, first match wins in the
priority order below). All thresholds are module-level constants and tunable:

  1. WRONG_DIRECTION   — went against us with little favorable run:
                         mfe_pct < WRONG_DIR_MFE_FRAC * loss_pct. Entry model was wrong.
  2. STOP_TOO_TIGHT    — ran well in our favor then got stopped:
                         mfe_pct >= STOP_TIGHT_MFE_FRAC * loss_pct AND tp_stage in (SL, "")
                         (and, when mae is present, mae_pct >= loss_pct). Stop too early.
  3. GAVE_BACK_PROFIT  — hit TP1 then trailed out near scratch:
                         tp_stage in (SL_TP1, TP1_SL) OR (PARTIAL and pnl_pct <= PARTIAL_SCRATCH_PCT).
  4. TIMING_SESSION    — loss sits in a session bucket whose pool win-rate is poor:
                         session WR < SESSION_WR_FLOOR over >= SESSION_MIN_TRADES trades.
  5. CHOP_REGIME       — regime in CHOP_REGIMES (entered in a non-trending regime).
  6. UNCLASSIFIED      — anything left.

A pool needs >= MIN_CLOSED closed trades to be diagnosed. A bucket is the DOMINANT
failure mode only if it is >= DOMINANT_LOSS_SHARE of all losses, else "mixed".
"""

from __future__ import annotations

import statistics as _st

from exit_optimizer import _mfe_pct, _mae_pct, _POOLS, optimize_pool

# ── Tunable thresholds ──────────────────────────────────────────────────────
MIN_CLOSED = 20             # min closed trades before a pool is diagnosable
DOMINANT_LOSS_SHARE = 0.30  # a bucket must own >= 30% of losses to be "dominant"

WRONG_DIR_MFE_FRAC = 0.25   # mfe% < 0.25 * loss% → entry was simply wrong
STOP_TIGHT_MFE_FRAC = 1.20  # mfe% >= 1.20 * loss% → ran past our exit then stopped
PARTIAL_SCRATCH_PCT = 0.05  # a PARTIAL closing <= +0.05% counts as gave-back

SESSION_WR_FLOOR = 0.35     # session win-rate below this is a "bad session"
SESSION_MIN_TRADES = 8      # min trades in a session bucket to trust its win-rate

CHOP_REGIMES = ("RANGING", "SIDEWAYS", "VOLATILE")
STOP_STAGES = ("SL", "")
GAVE_BACK_STAGES = ("SL_TP1", "TP1_SL")

_DIAG_PATH = "data/self_diagnosis.json"

# Pools to diagnose — exit_optimizer's traded set, plus the gold scalps.
_DIAG_POOLS = ["XAUUSD_2M", "XAUUSD_5M"] + [p for p in _POOLS if p not in ("XAUUSD_2M", "XAUUSD_5M")]


def _is_loser(t: dict) -> bool:
    """A trade we want to autopsy: an outright LOSS, or a scratched PARTIAL."""
    out = t.get("outcome")
    if out == "LOSS":
        return True
    if out == "PARTIAL":
        try:
            return float(t.get("pnl_pct") or 0.0) <= PARTIAL_SCRATCH_PCT
        except Exception:
            return False
    return False


def _win_rate(trades: list[dict]) -> float:
    closed = [t for t in trades if t.get("outcome") in ("WIN", "LOSS", "PARTIAL")]
    if not closed:
        return 0.0
    wins = sum(1 for t in closed if t.get("outcome") == "WIN")
    return wins / len(closed)


def _bad_sessions(trades: list[dict]) -> set[str]:
    """Session buckets with a poor pool win-rate (enough trades to trust)."""
    by_sess: dict[str, list[dict]] = {}
    for t in trades:
        if t.get("outcome") not in ("WIN", "LOSS", "PARTIAL"):
            continue
        sess = t.get("session") or "UNKNOWN"
        by_sess.setdefault(sess, []).append(t)
    bad = set()
    for sess, rows in by_sess.items():
        if len(rows) >= SESSION_MIN_TRADES and _win_rate(rows) < SESSION_WR_FLOOR:
            bad.add(sess)
    return bad


def classify_loss(t: dict, bad_sessions: set[str] | None = None) -> str:
    """Classify a single losing trade into ONE failure bucket (first match wins)."""
    bad_sessions = bad_sessions or set()
    mfe_pct = _mfe_pct(t) or 0.0
    mae_pct = _mae_pct(t)  # None when entry_price missing; 0 when mae absent
    try:
        loss_pct = abs(float(t.get("pnl_pct") or 0.0))
    except Exception:
        loss_pct = 0.0
    tp_stage = (t.get("tp_stage") or "")
    outcome = t.get("outcome")

    # 1. WRONG_DIRECTION — little favorable run before it went against us.
    if outcome == "LOSS" and loss_pct > 0 and mfe_pct < WRONG_DIR_MFE_FRAC * loss_pct:
        return "WRONG_DIRECTION"

    # 2. STOP_TOO_TIGHT — ran well past our exit then got cleanly stopped.
    if (outcome == "LOSS" and loss_pct > 0
            and mfe_pct >= STOP_TIGHT_MFE_FRAC * loss_pct
            and tp_stage in STOP_STAGES
            and (mae_pct is None or mae_pct <= 0 or mae_pct >= loss_pct)):
        return "STOP_TOO_TIGHT"

    # 3. GAVE_BACK_PROFIT — banked TP1 then trailed out near scratch.
    if tp_stage in GAVE_BACK_STAGES:
        return "GAVE_BACK_PROFIT"
    if outcome == "PARTIAL":
        try:
            if float(t.get("pnl_pct") or 0.0) <= PARTIAL_SCRATCH_PCT:
                return "GAVE_BACK_PROFIT"
        except Exception:
            pass

    # 4. TIMING_SESSION — loss sits in a chronically weak session bucket.
    if (t.get("session") or "UNKNOWN") in bad_sessions:
        return "TIMING_SESSION"

    # 5. CHOP_REGIME — entered in a non-trending regime.
    if (t.get("regime") or "").upper() in CHOP_REGIMES:
        return "CHOP_REGIME"

    return "UNCLASSIFIED"


def _profit_factor(realized: list[float]) -> float | None:
    gross_win = sum(p for p in realized if p > 0)
    gross_loss = -sum(p for p in realized if p < 0)
    if gross_loss <= 0:
        return None  # no losses → undefined / infinite
    return gross_win / gross_loss


# Dominant-mode → routed fix. (fix_string, fix_target, pine_change_required)
_FIX_MAP = {
    "WRONG_DIRECTION": (
        "Raise the pool's ML gate threshold; the direction model needs more data "
        "or a feature review.", "entry_gate", False),
    "STOP_TOO_TIGHT": (
        "Widen SL — see exit_optimizer.optimize_stop recommendation.", "stop", True),
    "GAVE_BACK_PROFIT": (
        "Take profit earlier / loosen the post-TP1 trail — see exit_optimizer "
        "recommended_tp_pct.", "trail_tp", True),
    "TIMING_SESSION": (
        "Gate out the chronically weak session bucket(s).", "session_gate", False),
    "CHOP_REGIME": (
        "Strengthen the sideways/chop block.", "regime_filter", True),
    "mixed": (
        "No single dominant leak — manual review.", "review", False),
}


def diagnose_pool(trades: list[dict]) -> dict:
    """Per-pool failure-mode diagnosis from an in-memory trade list (no network)."""
    closed = [t for t in trades if t.get("outcome") in ("WIN", "LOSS", "PARTIAL")]
    n = len(closed)
    if n < MIN_CLOSED:
        return {"status": "insufficient_data", "n": n}

    bad_sessions = _bad_sessions(closed)
    realized = [float(t.get("pnl_pct") or 0.0) for t in closed]

    losers = [t for t in closed if _is_loser(t)]
    buckets: dict[str, int] = {}
    for t in losers:
        b = classify_loss(t, bad_sessions)
        buckets[b] = buckets.get(b, 0) + 1

    n_losses = len(losers)
    loss_shares = {b: c / n_losses for b, c in buckets.items()} if n_losses else {}
    trade_shares = {b: c / n for b, c in buckets.items()}

    dominant = "mixed"
    if loss_shares:
        top, share = max(loss_shares.items(), key=lambda kv: kv[1])
        if share >= DOMINANT_LOSS_SHARE:
            dominant = top

    fix_string, fix_target, pine_req = _FIX_MAP.get(dominant, _FIX_MAP["mixed"])

    diag = {
        "status": "diagnosed",
        "n_closed": n,
        "win_rate": round(_win_rate(closed), 4),
        "profit_factor": (round(_profit_factor(realized), 3)
                          if _profit_factor(realized) is not None else None),
        "expectancy": round(_st.mean(realized), 5) if realized else 0.0,
        "n_losses": n_losses,
        "loss_buckets": buckets,
        "loss_shares": {b: round(s, 3) for b, s in loss_shares.items()},
        "trade_shares": {b: round(s, 3) for b, s in trade_shares.items()},
        "dominant_failure_mode": dominant,
        "recommended_fix": fix_string,
        "fix_target": fix_target,
        "pine_change_required": bool(pine_req),
    }

    # Name the worst session bucket(s) for a session-timing leak.
    if dominant == "TIMING_SESSION":
        diag["worst_sessions"] = sorted(bad_sessions)

    # Attach concrete exit numbers for stop / trail recommendations.
    if fix_target in ("stop", "trail_tp"):
        try:
            opt = optimize_pool(closed)
            if opt:
                diag["exit_optimizer"] = {
                    "recommended_tp_pct": opt.get("recommended_tp_pct"),
                    "recommended_stop_pct": (opt.get("stop_learning") or {}).get("recommended_stop_pct"),
                    "projected_expectancy": opt.get("projected_expectancy"),
                    "current_expectancy": opt.get("current_expectancy"),
                }
        except Exception as e:
            print(f"[self_diag] optimize_pool failed: {e}")

    return diag


def run_all() -> dict:
    """Diagnose every pool and persist to the data branch (3-retry on 409). SHADOW."""
    from datetime import datetime, timezone
    from db import _get_file, _put_file

    pools: dict[str, dict] = {}
    for pool in _DIAG_POOLS:
        try:
            hist, _ = _get_file(f"data/trade_history_{pool}.json")
            if not isinstance(hist, list):
                continue
            pools[pool] = diagnose_pool(hist)
        except Exception as e:
            print(f"[self_diag] {pool} failed: {e}")

    # Summary: the 2-3 worst pools by profit factor (lower = worse).
    ranked = [(p, d) for p, d in pools.items()
              if d.get("status") == "diagnosed" and d.get("profit_factor") is not None]
    ranked.sort(key=lambda kv: kv[1]["profit_factor"])
    worst = []
    for p, d in ranked[:3]:
        worst.append({
            "pool": p,
            "profit_factor": d["profit_factor"],
            "win_rate": d["win_rate"],
            "dominant_failure_mode": d["dominant_failure_mode"],
            "pine_change_required": d["pine_change_required"],
        })

    out = {"updated_at": datetime.now(timezone.utc).isoformat(),
           "mode": "shadow", "pools": pools, "summary": {"worst_pools": worst}}
    try:
        _, sha = _get_file(_DIAG_PATH)
        _put_file(_DIAG_PATH, out, sha, "data: self-diagnosis failure-mode autopsy (shadow)")
    except Exception as e:
        print(f"[self_diag] persist failed: {e}")

    print(f"[self_diag] {len(pools)} pools diagnosed — "
          f"{len(worst)} flagged as worst by profit factor")
    return out


def format_telegram(diag: dict) -> str:
    """Compact, HTML-safe text block of the worst pools for send_critical_alert."""
    worst = (diag.get("summary") or {}).get("worst_pools") or []
    pools = diag.get("pools") or {}
    if not worst:
        return "Self-diagnosis: no pools with enough data to rank yet."
    lines = ["Self-diagnosis — worst pools (SHADOW):"]
    for w in worst:
        p = w["pool"]
        d = pools.get(p, {})
        mode = w["dominant_failure_mode"]
        share = (d.get("loss_shares") or {}).get(mode)
        share_txt = f" ({int(share * 100)}% of losses)" if share is not None else ""
        fix = d.get("recommended_fix", "review")
        pine = " [PINE]" if w.get("pine_change_required") else ""
        lines.append(
            f"{p} — PF {w['profit_factor']:.2f}, win {int(w['win_rate']*100)}% — "
            f"leak: {mode}{share_txt} -> {fix}{pine}")
    return "\n".join(lines)
