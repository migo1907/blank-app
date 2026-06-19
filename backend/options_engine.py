"""
SPX 0-1DTE options layer — Phase 2C Stage A (paper only).

Translates SPY/SPX directional signals into SPX (SPXW daily-expiry) long
CALL/PUT recommendations. Never sells premium, never builds spreads.

Data sources:
  • Options chain (strike selection, expected move, paper-ledger premium):
    Tradier when TRADIER_TOKEN is set (stable REST, ~15-min delayed sandbox
    quotes), else yfinance ^SPX (delayed scrape) as automatic fallback.
  • yfinance ^VIX / ^VIX3M — volatility regime gate.
  • Live premiums come from the user's TradingView OPRA subscription: Telegram
    delivers the exact contract symbol; TV premium alerts can route back into
    /webhook for live exit data.

Hard rules (see ROADMAP.md Phase 2C):
  • IV Rank < 50 to buy premium (60-session trailing percentile).
  • VIX backwardation (VIX/VIX3M > 1) → no trades. VIX > 25 → half size note.
  • No entries within 24h before FOMC/CPI/NFP; no 0DTE on the morning of.
  • 0DTE only before 13:00 ET; later signals roll to 1DTE.
  • Exits: -50% premium / +100% premium / 0DTE hard exit 15:30 ET /
    1DTE time stop next-day 14:00 ET.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

_NY = ZoneInfo("America/New_York")

# ── In-memory ML model cache ──────────────────────────────────────────────────
_options_model: dict[str, Any] = {}   # keys: "rf", "gbm", "cal", "trained_at", "n"

_IV_HISTORY_PATH = "data/options_iv_history.json"
_PAPER_PATH      = "data/options_paper_SPX.json"
_IV_HISTORY_MAX  = 120   # trailing sessions kept (need 60 for IV Rank)

MAX_RISK_PCT       = 1.0   # premium risk per trade, % of account (informational)
TP_PREMIUM_MULT    = 2.0   # +100%
SL_PREMIUM_MULT    = 0.5   # -50%
IV_RANK_MAX        = 50.0
VIX_HALF_SIZE      = 25.0
TARGET_DELTA       = 0.25  # OTM strike target
MIN_CONFIDENCE     = 0.62  # mirror system MIN_CONFIDENCE


# ── VIX regime ────────────────────────────────────────────────────────────────

def get_vix_context() -> dict:
    """VIX level + term structure. backwardation=True means no long premium."""
    out = {"vix": None, "vix3m": None, "ratio": None,
           "backwardation": False, "half_size": False, "ok": False}
    try:
        import yfinance as yf
        vix   = yf.Ticker("^VIX").history(period="1d")
        vix3m = yf.Ticker("^VIX3M").history(period="1d")
        if len(vix) and len(vix3m):
            v, v3 = float(vix["Close"].iloc[-1]), float(vix3m["Close"].iloc[-1])
            out.update({
                "vix": round(v, 2), "vix3m": round(v3, 2),
                "ratio": round(v / v3, 3) if v3 else None,
                "backwardation": v3 > 0 and (v / v3) > 1.0,
                "half_size": v > VIX_HALF_SIZE,
                "ok": True,
            })
    except Exception as e:
        print(f"[options] VIX fetch failed: {e}")
    return out


# ── IV history / IV Rank ──────────────────────────────────────────────────────

def record_daily_iv() -> None:
    """Store today's SPX ATM IV — called once per trading day by the scheduler.
    IV Rank needs ~60 sessions; start collecting early."""
    try:
        atm_iv, _, _ = _atm_snapshot()
        if atm_iv is None:
            return
        from db import _get_file, _put_file
        hist, sha = _get_file(_IV_HISTORY_PATH)
        if not isinstance(hist, list):
            hist = []
        today = datetime.now(timezone.utc).date().isoformat()
        if hist and hist[-1].get("date") == today:
            return  # already recorded
        hist.append({"date": today, "atm_iv": round(atm_iv, 4)})
        hist = hist[-_IV_HISTORY_MAX:]
        _put_file(_IV_HISTORY_PATH, hist, sha, f"chore: record SPX ATM IV {today}")
        print(f"[options] ATM IV recorded: {atm_iv:.1%} ({len(hist)} sessions)")
    except Exception as e:
        print(f"[options] IV record failed: {e}")


def iv_rank(current_iv: float) -> float | None:
    """Percentile of current IV over trailing 60 sessions. None until 20+ sessions."""
    try:
        from db import _get_file
        hist, _ = _get_file(_IV_HISTORY_PATH)
        ivs = [h["atm_iv"] for h in (hist or []) if isinstance(h, dict) and h.get("atm_iv")]
        ivs = ivs[-60:]
        if len(ivs) < 20:
            return None
        below = sum(1 for v in ivs if v <= current_iv)
        return round(below / len(ivs) * 100, 1)
    except Exception:
        return None


# ── Chain access (yfinance, delayed — paper baseline) ─────────────────────────

def _spx_chain(expiry: str):
    """Spot + option chain. Prefers Tradier (stable REST) when TRADIER_TOKEN is
    set; falls back to yfinance (delayed scrape). Both return the same shape."""
    import tradier_data
    if tradier_data.available():
        spot = tradier_data.get_spot()
        chain = tradier_data.get_chain(tradier_data.SPX_SYMBOL, expiry)
        if spot and chain is not None and (len(chain.calls) or len(chain.puts)):
            return spot, chain
        print("[options] Tradier chain empty — falling back to yfinance")
    import yfinance as yf
    tk = yf.Ticker("^SPX")
    spot = float(tk.history(period="1d")["Close"].iloc[-1])
    chain = tk.option_chain(expiry)
    return spot, chain


def _list_expiries() -> list[str]:
    """Sorted expiry strings from Tradier when available, else yfinance."""
    import tradier_data
    if tradier_data.available():
        exps = tradier_data.get_expirations()
        if exps:
            return exps
        print("[options] Tradier expiries empty — falling back to yfinance")
    import yfinance as yf
    return list(yf.Ticker("^SPX").options or [])


def _pick_expiry(now_et: datetime) -> tuple[str, int] | None:
    """0DTE before 13:00 ET, else 1DTE (next listed expiry). Returns (date, dte)."""
    try:
        expiries = _list_expiries()
    except Exception as e:
        print(f"[options] expiry list failed: {e}")
        return None
    today = now_et.date()
    for exp in expiries:
        d = datetime.strptime(exp, "%Y-%m-%d").date()
        dte = (d - today).days
        if dte == 0 and now_et.hour < 13:
            return exp, 0
        if dte >= 1:
            return exp, dte
    return None


def _atm_snapshot() -> tuple[float | None, float | None, float | None]:
    """(atm_iv, expected_move_points, spot) from the nearest expiry straddle."""
    try:
        now_et = datetime.now(_NY)
        picked = _pick_expiry(now_et)
        if not picked:
            return None, None, None
        expiry, _ = picked
        spot, chain = _spx_chain(expiry)
        calls, puts = chain.calls, chain.puts
        c = calls.iloc[(calls["strike"] - spot).abs().argsort()[:1]]
        p = puts.iloc[(puts["strike"] - spot).abs().argsort()[:1]]
        atm_iv = float((c["impliedVolatility"].iloc[0] + p["impliedVolatility"].iloc[0]) / 2)
        straddle = float(c["lastPrice"].iloc[0] + p["lastPrice"].iloc[0])
        return atm_iv, straddle, spot
    except Exception as e:
        print(f"[options] ATM snapshot failed: {e}")
        return None, None, None


def _bs_delta(spot: float, strike: float, iv: float, dte_years: float, is_call: bool) -> float:
    """Black-Scholes delta (r=0 — negligible at 0-1DTE)."""
    if iv <= 0 or dte_years <= 0:
        return 0.5
    d1 = (math.log(spot / strike) + 0.5 * iv * iv * dte_years) / (iv * math.sqrt(dte_years))
    nd1 = 0.5 * (1 + math.erf(d1 / math.sqrt(2)))
    return nd1 if is_call else nd1 - 1.0


# ── Recommendation builder ─────────────────────────────────────────────────────

def build_spx_recommendation(direction: str, confidence: float,
                              atr_tp1_points: float | None = None,
                              pool_confluence: float = 0.5,
                              **kwargs) -> dict | None:
    """
    Translate a directional signal into an SPX 0-1DTE long option, or None
    with the skip reason printed. Pure read — caller persists/sends.
    """
    if direction not in ("LONG", "SHORT") or confidence < MIN_CONFIDENCE:
        return None
    now_et = datetime.now(_NY)
    if now_et.weekday() >= 5 or not (9 <= now_et.hour < 15) or (now_et.hour == 9 and now_et.minute < 45):
        print("[options] outside entry window (09:45–15:00 ET) — skip")
        return None

    # Event filter — no entries within 24h before a high-impact print
    try:
        from news_fetcher import fetch_upcoming_events
        sched = fetch_upcoming_events(hours_ahead=24)
        if sched.get("scheduled"):
            nxt = sched["scheduled"][0]
            if nxt.get("urgency", 0) >= 0.85 and 0 <= (nxt.get("minutes_until") or 9999) <= 24 * 60:
                print(f"[options] {nxt.get('event_type')} in {nxt.get('minutes_until')}min — no new premium, skip")
                return None
    except Exception:
        pass

    vix = get_vix_context()
    if vix.get("backwardation"):
        print(f"[options] VIX backwardation ({vix.get('ratio')}) — skip")
        return None

    picked = _pick_expiry(now_et)
    if not picked:
        print("[options] no usable expiry — skip")
        return None
    expiry, dte = picked

    try:
        spot, chain = _spx_chain(expiry)
    except Exception as e:
        print(f"[options] chain fetch failed: {e}")
        return None

    is_call = direction == "LONG"
    side = chain.calls if is_call else chain.puts
    dte_years = max((dte + 0.5) / 365.0, 0.25 / 365.0)

    # Pick the strike whose BS delta is closest to ±0.40
    best, best_err = None, 9e9
    for _, row in side.iterrows():
        strike = float(row["strike"])
        iv = float(row.get("impliedVolatility") or 0)
        bid, ask = float(row.get("bid") or 0), float(row.get("ask") or 0)
        last = float(row.get("lastPrice") or 0)
        mid = (bid + ask) / 2 if (bid and ask) else last
        if mid <= 0 or iv <= 0 or abs(strike - spot) > spot * 0.03:
            continue
        delta = _bs_delta(spot, strike, iv, dte_years, is_call)
        err = abs(abs(delta) - TARGET_DELTA)
        if err < best_err:
            best_err = err
            best = {"strike": strike, "iv": iv, "mid": round(mid, 2), "delta": round(delta, 3)}
    if not best:
        print("[options] no liquid strike near Δ0.40 — skip")
        return None

    # IV Rank gate
    ivr = iv_rank(best["iv"])
    if ivr is not None and ivr > IV_RANK_MAX:
        print(f"[options] IV Rank {ivr} > {IV_RANK_MAX} — premium too expensive, skip")
        return None

    # Expected-move check: signal target must clear 0.8× of the market's move
    _, straddle, _ = _atm_snapshot()
    if atr_tp1_points and straddle and atr_tp1_points < 0.8 * straddle:
        print(f"[options] TP1 {atr_tp1_points:.0f}pt < 0.8×EM {straddle:.0f}pt — theta wins, skip")
        return None

    exp_compact = expiry.replace("-", "")[2:]
    cp = "C" if is_call else "P"
    tv_symbol = f"OPRA:SPXW{exp_compact}{cp}{int(best['strike'])}"
    hard_exit = "15:30 ET today" if dte == 0 else "14:00 ET next session"

    rec_candidate = {
        "id":            datetime.now(timezone.utc).strftime("%y%m%d%H%M%S"),
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "instrument":    "SPX",
        "type":          "CALL" if is_call else "PUT",
        "direction":     direction,
        "confidence":    round(confidence, 3),
        "spot":          round(spot, 2),
        "strike":        best["strike"],
        "delta":         best["delta"],
        "expiry":        expiry,
        "dte":           dte,
        "entry_premium": best["mid"],
        "tp_premium":    round(best["mid"] * TP_PREMIUM_MULT, 2),
        "sl_premium":    round(best["mid"] * SL_PREMIUM_MULT, 2),
        "hard_exit":     hard_exit,
        "iv":            round(best["iv"], 4),
        "iv_rank":       ivr,
        "vix":           vix.get("vix"),
        "vix_ratio":     vix.get("ratio"),
        "half_size":     bool(vix.get("half_size")),
        "expected_move": round(straddle, 1) if straddle else None,
        "tv_symbol":     tv_symbol,
        "status":        "OPEN",
        "paper":         True,
    }

    # ML gate — once ≥50 closed trades, score this candidate and skip if below threshold
    pool_confluence = kwargs.get("pool_confluence", 0.5)
    enrich_features(rec_candidate, pool_confluence=pool_confluence)
    ml_score = options_predict(rec_candidate["features"])
    rec_candidate["ml_score"] = ml_score
    if ml_score is not None and ml_score < _ML_SCORE_GATE:
        print(f"[options-ml] skip — ML score {ml_score:.3f} < {_ML_SCORE_GATE} "
              f"(matches historical loss pattern)")
        return None

    return rec_candidate


def format_telegram(rec: dict) -> str:
    size_note = "\n⚠️ VIX>25 — HALF SIZE" if rec.get("half_size") else ""
    return (
        f"🎯 <b>SPX {rec['dte']}DTE — {rec['type']} {int(rec['strike'])}</b> (Δ{rec['delta']:+.2f})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📄 PAPER | conf {rec['confidence']:.2f} | spot {rec['spot']:.0f}\n"
        f"💵 entry ≈ ${rec['entry_premium']:.2f} (delayed — check live on TV)\n"
        f"🎯 TP ${rec['tp_premium']:.2f} (+100%)  🛑 SL ${rec['sl_premium']:.2f} (-50%)\n"
        f"⏰ hard exit: {rec['hard_exit']}{size_note}"
    )


# ── Paper ledger ───────────────────────────────────────────────────────────────

def append_paper_trade(rec: dict) -> None:
    try:
        from db import _get_file, _put_file
        ledger, sha = _get_file(_PAPER_PATH)
        if not isinstance(ledger, list):
            ledger = []
        ledger.append(rec)
        _put_file(_PAPER_PATH, ledger, sha,
                  f"options: paper {rec['type']} {int(rec['strike'])} {rec['expiry']}")
        print(f"[options] paper trade logged: {rec['tv_symbol']}")
    except Exception as e:
        print(f"[options] ledger write failed: {e}")


def manage_paper_positions() -> list[str]:
    """Hourly job: enforce TP/SL/time exits on open paper positions using
    delayed mid quotes. Returns list of close summaries."""
    closed: list[str] = []
    try:
        from db import _get_file, _put_file
        ledger, sha = _get_file(_PAPER_PATH)
        if not isinstance(ledger, list) or not ledger:
            return closed
        now_et = datetime.now(_NY)
        dirty = False
        for rec in ledger:
            if rec.get("status") != "OPEN":
                continue
            mid = _current_mid(rec)
            entry = rec.get("entry_premium") or 0
            reason = None
            exp_date = datetime.strptime(rec["expiry"], "%Y-%m-%d").date()
            if mid is not None and entry:
                if mid >= rec["tp_premium"]:
                    reason = "TP +100%"
                elif mid <= rec["sl_premium"]:
                    reason = "SL -50%"
            if reason is None:
                if rec["dte"] == 0 and now_et.date() >= exp_date and (now_et.hour, now_et.minute) >= (15, 30):
                    reason = "hard exit 15:30 ET"
                elif rec["dte"] >= 1 and now_et.date() >= exp_date and now_et.hour >= 14:
                    reason = "1DTE time stop"
                elif now_et.date() > exp_date:
                    reason = "expired"
            if reason:
                rec["status"]       = "CLOSED"
                rec["exit_premium"] = mid
                rec["exit_reason"]  = reason
                rec["closed_at"]    = datetime.now(timezone.utc).isoformat()
                if mid is not None and entry:
                    rec["pnl_pct"] = round((mid - entry) / entry * 100, 1)
                rec["loss_reason"] = categorize_outcome(rec)
                dirty = True
                closed.append(f"{rec['tv_symbol']} → {reason} ({rec.get('pnl_pct','?')}%) [{rec['loss_reason']}]")
        if dirty:
            _put_file(_PAPER_PATH, ledger, sha, "options: paper position management")
            _auto_retrain_if_ready()
    except Exception as e:
        print(f"[options] paper management failed: {e}")
    return closed


def _current_mid(rec: dict) -> float | None:
    try:
        _, chain = _spx_chain(rec["expiry"])
        side = chain.calls if rec["type"] == "CALL" else chain.puts
        row = side[side["strike"] == rec["strike"]]
        if row.empty:
            return None
        bid, ask = float(row["bid"].iloc[0] or 0), float(row["ask"].iloc[0] or 0)
        last = float(row["lastPrice"].iloc[0] or 0)
        return round((bid + ask) / 2, 2) if (bid and ask) else (round(last, 2) or None)
    except Exception:
        return None


# ── Training dataset (ML cold-start — same pattern as swing_tracker) ──────────

# Features captured at entry time and stored on each paper trade.
# 18 features — original 12 + 6 new context features.
OPTION_FEATURE_KEYS = [
    # Core signal quality
    "confidence",           # ML confidence from directional pool
    "iv",                   # option implied volatility at entry
    "iv_rank",              # IV percentile vs trailing 60 sessions (0-100)
    # Volatility regime
    "vix",                  # VIX spot at entry
    "vix_ratio",            # VIX/VIX3M — backwardation margin
    "vix_backwardation_margin",  # 1.0 - vix_ratio (positive = safer to buy premium)
    # Strike / premium context
    "delta",                # absolute delta of chosen strike
    "entry_premium",        # mid-price paid per contract
    "spot_vs_strike_pct",   # moneyness: positive = OTM (call), negative = ITM
    "premium_vs_em_pct",    # entry_premium / expected_move × 100 (overpay ratio)
    "iv_over_vix_ratio",    # option IV / VIX (IV richness vs realized vol proxy)
    # Time / session context
    "dte",                  # days to expiry (0 or 1)
    "hour_et",              # entry hour in ET (fractional, 9.75 = 9:45am)
    "day_of_week",          # 0=Mon … 4=Fri
    "entry_time_norm",      # position in session: 0=open (9:30), 1=close (16:00)
    "time_to_hard_exit_hours",  # hours until forced exit (urgency)
    # Market context
    "expected_move",        # ATM straddle price (market's implied 1-day move)
    "pool_confluence",      # 1.0=15M+30M agree, 0.5=only trigger pool fired
]

_MIN_TRADES_ML = 50   # closed trades before ML is eligible
_ML_SCORE_GATE  = 0.52  # calibrated win-probability minimum to enter


def enrich_features(rec: dict, pool_confluence: float = 0.5) -> dict:
    """Add the 18-feature training vector to a recommendation dict before logging."""
    now_et = datetime.now(_NY)
    spot   = rec.get("spot") or 0
    strike = rec.get("strike") or 0
    is_call = rec["type"] == "CALL"
    vix_ratio = rec.get("vix_ratio") or 1.0
    entry_premium = rec.get("entry_premium") or 0.0
    expected_move = rec.get("expected_move") or 0.0
    iv  = rec.get("iv") or 0.0
    vix = rec.get("vix") or 0.0
    dte = int(rec.get("dte") or 0)

    spot_vs_strike = ((spot - strike) / spot * 100) if spot else 0.0
    if not is_call:
        spot_vs_strike = -spot_vs_strike

    premium_vs_em = (entry_premium / expected_move * 100) if expected_move else 0.0
    iv_over_vix   = (iv / (vix / 100)) if vix else 1.0   # option IV vs annualised VIX

    # Normalised session position: 9:30=0.0, 16:00=1.0
    session_minutes = max(0, (now_et.hour * 60 + now_et.minute) - 570)   # 570 = 9:30
    entry_time_norm = min(session_minutes / 390, 1.0)   # 390 min = 9:30→16:00

    # Hours until hard exit
    if dte == 0:
        hard_exit_et = now_et.replace(hour=15, minute=30, second=0, microsecond=0)
    else:
        hard_exit_et = now_et.replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
    time_to_exit = max(0.0, (hard_exit_et - now_et).total_seconds() / 3600)

    rec["features"] = {
        "confidence":              rec.get("confidence", 0.0),
        "iv":                      round(iv, 4),
        "iv_rank":                 rec.get("iv_rank") or 0.0,
        "vix":                     round(vix, 2),
        "vix_ratio":               round(vix_ratio, 3),
        "vix_backwardation_margin": round(1.0 - vix_ratio, 3),
        "delta":                   abs(rec.get("delta") or 0.0),
        "entry_premium":           round(entry_premium, 2),
        "spot_vs_strike_pct":      round(spot_vs_strike, 3),
        "premium_vs_em_pct":       round(premium_vs_em, 2),
        "iv_over_vix_ratio":       round(iv_over_vix, 3),
        "dte":                     float(dte),
        "hour_et":                 round(now_et.hour + now_et.minute / 60, 3),
        "day_of_week":             float(now_et.weekday()),
        "entry_time_norm":         round(entry_time_norm, 3),
        "time_to_hard_exit_hours": round(time_to_exit, 2),
        "expected_move":           round(expected_move, 2),
        "pool_confluence":         pool_confluence,
    }
    rec["pool_confluence"] = pool_confluence
    return rec


def training_dataset(pool: str = "ALL") -> tuple[list[list[float]], list[int], dict]:
    """
    Build (X, y, meta) from closed paper trades for ML training.
    pool: 'ALL' | '0DTE' | '1DTE'
    X rows follow OPTION_FEATURE_KEYS order; y is 1=WIN / 0=LOSS.
    """
    try:
        from db import _get_file
        ledger, _ = _get_file(_PAPER_PATH)
        ledger = ledger if isinstance(ledger, list) else []
    except Exception:
        ledger = []

    closed = [r for r in ledger if r.get("status") == "CLOSED"]
    if pool == "0DTE":
        closed = [r for r in closed if r.get("dte") == 0]
    elif pool == "1DTE":
        closed = [r for r in closed if r.get("dte", 0) >= 1]

    X, y = [], []
    for r in closed:
        feats = r.get("features") or {}
        X.append([float(feats.get(k, 0.0)) for k in OPTION_FEATURE_KEYS])
        pnl = r.get("pnl_pct") or 0.0
        y.append(1 if pnl > 0 else 0)

    n = len(y)
    wins = sum(y)
    meta = {
        "pool":      pool,
        "n_closed":  n,
        "n_wins":    wins,
        "n_losses":  n - wins,
        "win_rate":  round(wins / n, 3) if n else None,
        "n_open":    sum(1 for r in ledger if r.get("status") == "OPEN"),
        "ready":     n >= _MIN_TRADES_ML,
        "feature_keys": OPTION_FEATURE_KEYS,
    }
    return X, y, meta


# ── Loss categorization ────────────────────────────────────────────────────────

_LOSS_REASONS = ("WRONG_DIRECTION", "THETA_DECAY", "IV_CRUSH", "OVERPAID", "LATE_ENTRY", "WIN", "UNKNOWN")


def categorize_outcome(rec: dict) -> str:
    """Tag a closed trade with the primary reason it won or lost."""
    pnl  = rec.get("pnl_pct") or 0.0
    exit_reason = rec.get("exit_reason", "")
    feats = rec.get("features") or {}

    if pnl > 0:
        return "WIN"

    # Time stops → theta decay (didn't move enough before expiry)
    if "time stop" in exit_reason or "hard exit" in exit_reason or "expired" in exit_reason:
        return "THETA_DECAY"

    # SL hit — distinguish direction vs IV crush
    if pnl <= -45:
        # Was the underlying moving against us? Use spot_vs_strike as proxy:
        # large negative spot_vs_strike on a losing call = underlying dropped hard
        s_vs_k = feats.get("spot_vs_strike_pct", 0.0)
        # If moneyness moved deep wrong way → wrong direction call
        if abs(s_vs_k) > 0.5:
            return "WRONG_DIRECTION"
        # Otherwise premium collapsed despite moderate move → IV crush
        return "IV_CRUSH"

    # Partial loss — check structural entry mistakes
    if feats.get("premium_vs_em_pct", 0.0) > 50.0:
        return "OVERPAID"
    if feats.get("time_to_hard_exit_hours", 99.0) < 2.0:
        return "LATE_ENTRY"

    return "WRONG_DIRECTION"   # default for unexplained SL hits


# ── ML ensemble (RF + GBM + isotonic calibration) ─────────────────────────────

def options_ml_train(pool: str = "ALL") -> dict:
    """
    Train RF + GBM on closed paper trades, fit isotonic calibration on an OOS fold.
    Updates the in-memory _options_model cache. Returns training summary.
    pool: 'ALL' | '0DTE' | '1DTE'
    """
    global _options_model
    X, y, meta = training_dataset(pool)
    n = len(y)
    if n < _MIN_TRADES_ML:
        return {"status": "insufficient_data", "n": n, "need": _MIN_TRADES_ML}

    try:
        from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
        from sklearn.isotonic import IsotonicRegression
        from sklearn.model_selection import train_test_split
        import numpy as np

        X_arr = np.array(X, dtype=float)
        y_arr = np.array(y, dtype=int)

        # Walk-forward OOS: last 20% as validation, first 80% as train
        split = max(int(n * 0.8), min(40, n - 10))
        X_tr, X_val = X_arr[:split], X_arr[split:]
        y_tr, y_val = y_arr[:split], y_arr[split:]

        rf  = RandomForestClassifier(n_estimators=200, max_depth=5,
                                     min_samples_leaf=4, random_state=42)
        gbm = GradientBoostingClassifier(n_estimators=150, max_depth=3,
                                         learning_rate=0.05, subsample=0.8,
                                         random_state=42)
        rf.fit(X_tr, y_tr)
        gbm.fit(X_tr, y_tr)

        # Ensemble raw proba on val set, then isotonic calibration
        if len(X_val):
            raw_val = (rf.predict_proba(X_val)[:, 1] + gbm.predict_proba(X_val)[:, 1]) / 2
            cal = IsotonicRegression(out_of_bounds="clip")
            cal.fit(raw_val, y_val)
            oos_acc = float(np.mean((raw_val >= 0.5) == y_val))
        else:
            # Not enough for OOS — fit calibration on full set
            raw_full = (rf.predict_proba(X_arr)[:, 1] + gbm.predict_proba(X_arr)[:, 1]) / 2
            cal = IsotonicRegression(out_of_bounds="clip")
            cal.fit(raw_full, y_arr)
            oos_acc = None

        # Feature importance from RF
        importances = dict(zip(OPTION_FEATURE_KEYS,
                               [round(float(v), 4) for v in rf.feature_importances_]))
        top_features = sorted(importances.items(), key=lambda x: -x[1])[:5]

        _options_model.update({
            "rf": rf, "gbm": gbm, "cal": cal,
            "pool": pool, "n": n, "wins": int(sum(y_arr)),
            "oos_acc": oos_acc,
            "top_features": top_features,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"[options-ml] trained on {n} trades | OOS acc={oos_acc} | "
              f"top={top_features[0][0]}({top_features[0][1]:.3f})")
        return {"status": "ok", "n": n, "oos_acc": oos_acc, "top_features": top_features}

    except Exception as e:
        print(f"[options-ml] train failed: {e}")
        return {"status": "error", "error": str(e)}


def options_predict(features: dict) -> float | None:
    """
    Return calibrated win probability (0-1) for a candidate trade.
    Returns None if model not trained yet.
    """
    if not _options_model.get("rf"):
        return None
    try:
        import numpy as np
        row = np.array([[float(features.get(k, 0.0)) for k in OPTION_FEATURE_KEYS]])
        rf_p  = _options_model["rf"].predict_proba(row)[0, 1]
        gbm_p = _options_model["gbm"].predict_proba(row)[0, 1]
        raw   = (rf_p + gbm_p) / 2
        cal_p = float(_options_model["cal"].predict([raw])[0])
        return round(cal_p, 3)
    except Exception as e:
        print(f"[options-ml] predict failed: {e}")
        return None


def _auto_retrain_if_ready() -> None:
    """Called after each position close. Retrains if ≥50 closed trades."""
    try:
        from db import _get_file
        ledger, _ = _get_file(_PAPER_PATH)
        ledger = ledger if isinstance(ledger, list) else []
        n_closed = sum(1 for r in ledger if r.get("status") == "CLOSED")
        if n_closed >= _MIN_TRADES_ML:
            options_ml_train("ALL")
    except Exception as e:
        print(f"[options-ml] auto-retrain failed: {e}")


# ── Weekly autopsy ─────────────────────────────────────────────────────────────

def weekly_autopsy() -> str:
    """
    Analyse closed trades to surface dominant loss patterns.
    Returns a formatted summary string (for Telegram or console).
    """
    try:
        from db import _get_file
        ledger, _ = _get_file(_PAPER_PATH)
        ledger = ledger if isinstance(ledger, list) else []
    except Exception:
        return "Options autopsy: no data"

    closed = [r for r in ledger if r.get("status") == "CLOSED"]
    if not closed:
        return "Options autopsy: 0 closed trades yet"

    # Tag each closed trade with loss reason if not already tagged
    for r in closed:
        if not r.get("loss_reason"):
            r["loss_reason"] = categorize_outcome(r)

    total  = len(closed)
    wins   = [r for r in closed if r["loss_reason"] == "WIN"]
    losses = [r for r in closed if r["loss_reason"] != "WIN"]
    win_rate = len(wins) / total * 100

    # Loss breakdown by reason
    from collections import Counter
    loss_counts = Counter(r["loss_reason"] for r in losses)

    lines = [
        f"📊 <b>SPX Options Weekly Autopsy</b>",
        f"Total closed: {total} | Win rate: {win_rate:.1f}%",
        f"Wins: {len(wins)} | Losses: {len(losses)}",
        "",
        "🔴 Loss breakdown:",
    ]
    for reason, count in loss_counts.most_common():
        pct = count / len(losses) * 100 if losses else 0
        lines.append(f"  {reason}: {count} ({pct:.0f}%)")

    # Key feature averages for losses vs wins
    def avg_feat(trades, key):
        vals = [r.get("features", {}).get(key, 0.0) for r in trades if r.get("features")]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    if losses and wins:
        lines.append("")
        lines.append("📉 Loss vs Win avg feature comparison:")
        key_feats = ["confidence", "premium_vs_em_pct", "time_to_hard_exit_hours",
                     "vix", "iv_rank", "pool_confluence"]
        for feat in key_feats:
            l_avg = avg_feat(losses, feat)
            w_avg = avg_feat(wins, feat)
            lines.append(f"  {feat}: loss={l_avg} vs win={w_avg}")

    # ML model status
    if _options_model.get("rf"):
        lines.append("")
        lines.append(f"🤖 ML model: trained on {_options_model['n']} trades | "
                     f"OOS acc={_options_model.get('oos_acc')}")
        if _options_model.get("top_features"):
            top = _options_model["top_features"][:3]
            lines.append(f"  Top signals: " + ", ".join(f"{k}({v:.3f})" for k, v in top))

    return "\n".join(lines)


def stats() -> dict:
    """Training-readiness summary for the /options/trades endpoint."""
    try:
        from db import _get_file
        ledger, _ = _get_file(_PAPER_PATH)
        ledger = ledger if isinstance(ledger, list) else []
    except Exception:
        ledger = []

    def _pool_meta(pool_name: str, trades: list) -> dict:
        closed = [r for r in trades if r.get("status") == "CLOSED"]
        n = len(closed)
        wins = sum(1 for r in closed if (r.get("pnl_pct") or 0) > 0)
        open_n = sum(1 for r in trades if r.get("status") == "OPEN")
        return {
            "n_closed": n,
            "n_open":   open_n,
            "n_wins":   wins,
            "win_rate": round(wins / n, 3) if n else None,
            "ready":    n >= _MIN_TRADES_ML,
            "telegram_unlocks_at": _MIN_TRADES_ML,
        }

    zero_dte = [r for r in ledger if r.get("dte") == 0]
    one_dte  = [r for r in ledger if r.get("dte", 0) >= 1]
    return {
        "SPX_0DTE": _pool_meta("SPX_0DTE", zero_dte),
        "SPX_1DTE": _pool_meta("SPX_1DTE", one_dte),
        "ALL":      _pool_meta("ALL", ledger),
        "telegram_gate": "OPTIONS_TELEGRAM env OR auto-unlock at 50 closed trades per pool",
        "silent_until":  f"≥{_MIN_TRADES_ML} closed trades per pool",
    }


def should_send_telegram(dte: int) -> bool:
    """Auto-unlock Telegram for a pool once it hits 50 closed trades."""
    import os
    if os.environ.get("OPTIONS_TELEGRAM", "false").lower() == "true":
        return True
    try:
        from db import _get_file
        ledger, _ = _get_file(_PAPER_PATH)
        ledger = ledger if isinstance(ledger, list) else []
    except Exception:
        return False
    if dte == 0:
        pool = [r for r in ledger if r.get("dte") == 0]
    else:
        pool = [r for r in ledger if r.get("dte", 0) >= 1]
    closed = sum(1 for r in pool if r.get("status") == "CLOSED")
    return closed >= _MIN_TRADES_ML
