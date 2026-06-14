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

_NY = ZoneInfo("America/New_York")

_IV_HISTORY_PATH = "data/options_iv_history.json"
_PAPER_PATH      = "data/options_paper_SPX.json"
_IV_HISTORY_MAX  = 120   # trailing sessions kept (need 60 for IV Rank)

MAX_RISK_PCT       = 1.0   # premium risk per trade, % of account (informational)
TP_PREMIUM_MULT    = 2.0   # +100%
SL_PREMIUM_MULT    = 0.5   # -50%
IV_RANK_MAX        = 50.0
VIX_HALF_SIZE      = 25.0
TARGET_DELTA       = 0.40
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
                              atr_tp1_points: float | None = None) -> dict | None:
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

    return {
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
                dirty = True
                closed.append(f"{rec['tv_symbol']} → {reason} ({rec.get('pnl_pct','?')}%)")
        if dirty:
            _put_file(_PAPER_PATH, ledger, sha, "options: paper position management")
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
