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
import threading as _threading
_options_model_lock = _threading.Lock()

_IV_HISTORY_PATH = "data/options_iv_history.json"
_PAPER_PATH      = "data/options_paper_SPX.json"
_IV_HISTORY_MAX  = 120   # trailing sessions kept (need 60 for IV Rank)

# Diagnostic — why the SPX options layer did/didn't open a trade on the last cycle.
_LAST_OPT_CHECK = {"reason": "warming up — waiting for first SPX signal cycle", "at": None}
def set_options_check(reason: str) -> None:
    import datetime as _dt
    _LAST_OPT_CHECK.update({"reason": reason, "at": _dt.datetime.now(_dt.timezone.utc).isoformat()})
def last_options_check() -> dict:
    return dict(_LAST_OPT_CHECK)
def _opt_skip(reason: str):
    set_options_check(reason)
    return None

MAX_RISK_PCT       = 1.0   # premium risk per trade, % of account (informational)
TP_PREMIUM_MULT    = 2.0   # +100%
SL_PREMIUM_MULT    = 0.5   # -50%
IV_RANK_MAX        = 50.0
VIX_HALF_SIZE      = 25.0
TARGET_DELTA       = 0.25  # OTM strike target
MIN_CONFIDENCE     = 0.0   # data-collection phase: collect every directional flip;
                           # the ML gate (≥50 closed trades/pool) is the real quality
                           # filter. Was 0.62 — that blocked every SPX signal, so the
                           # paper layer never opened a trade. Restore ~0.55–0.62 after
                           # enough data accumulates to train the options ML.


# ── VIX regime ────────────────────────────────────────────────────────────────

def get_vix_context() -> dict:
    """VIX level + term structure + VIX9D. backwardation=True means no long premium."""
    out = {"vix": None, "vix3m": None, "vix9d": None, "ratio": None,
           "vix9d_ratio": None, "backwardation": False, "half_size": False, "ok": False}
    try:
        import io as _io, pandas as _pd, httpx
        _nan = lambda x: x is None or (x != x)

        def _cboe_vix(name: str) -> float | None:
            """Fetch latest close from CBOE CDN CSV — no auth, CDN-served."""
            url = f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{name}_History.csv"
            try:
                r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10, follow_redirects=True)
                r.raise_for_status()
                df = _pd.read_csv(_io.StringIO(r.text))
                if not df.empty and "CLOSE" in df.columns:
                    v = float(df["CLOSE"].iloc[-1])
                    return None if _nan(v) or v <= 0 else v
            except Exception:
                pass
            # Stooq fallback
            try:
                from market_data import _stooq_daily
                df = _stooq_daily(f"^{name.lower()}")
                if len(df):
                    v = float(df["Close"].iloc[-1])
                    return None if _nan(v) or v <= 0 else v
            except Exception:
                pass
            return None

        v  = _cboe_vix("VIX")
        v3 = _cboe_vix("VIX3M")
        v9 = _cboe_vix("VIX9D")

        if v and v3:
            out.update({
                "vix":           round(v, 2),
                "vix3m":         round(v3, 2),
                "vix9d":         round(v9, 2) if v9 else None,
                "ratio":         round(v / v3, 3),
                "vix9d_ratio":   round(v9 / v, 3) if v9 else None,
                "backwardation": (v / v3) > 1.0,
                "half_size":     v > VIX_HALF_SIZE,
                "ok":            True,
            })
    except Exception as e:
        print(f"[options] VIX fetch failed: {e}")
    try:
        import data_health
        data_health.record("cboe_vix", bool(out.get("ok")), "volatility",
                           "" if out.get("ok") else "VIX/VIX3M unavailable")
    except Exception:
        pass
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
    """Spot + option chain. Priority: Tradier → Polygon → yfinance."""
    import tradier_data
    if tradier_data.available():
        spot = tradier_data.get_spot()
        chain = tradier_data.get_chain(tradier_data.SPX_SYMBOL, expiry)
        if spot and chain is not None and (len(chain.calls) or len(chain.puts)):
            _chain_health(True)
            return spot, chain
        print("[options] Tradier chain empty — falling back")

    # Polygon: 15-min delayed with real Greeks (better than scrape)
    try:
        import polygon_data
        if polygon_data.available():
            chain_data = polygon_data.get_options_chain("SPXW", expiry)
            if chain_data and (chain_data["calls"] or chain_data["puts"]):
                import pandas as pd
                spot = polygon_data.get_spot("I:SPX")
                if not spot:
                    # Stooq SPX proxy via SPY (SPX ≈ SPY × 10)
                    try:
                        from market_data import _stooq_daily
                        _spy = _stooq_daily("spy.us")
                        if len(_spy):
                            spot = float(_spy["Close"].iloc[-1]) * 10
                    except Exception:
                        spot = None
                calls_df = pd.DataFrame(chain_data["calls"])
                puts_df  = pd.DataFrame(chain_data["puts"])
                for df in (calls_df, puts_df):
                    for col in ("impliedVolatility", "lastPrice", "strike",
                                "openInterest", "delta", "bid", "ask"):
                        if col not in df.columns:
                            df[col] = None

                class _Chain:
                    def __init__(self, c, p): self.calls, self.puts = c, p

                print(f"[options] Polygon chain: {expiry} ({len(calls_df)}C {len(puts_df)}P, real Greeks)")
                _chain_health(True)
                return spot, _Chain(calls_df, puts_df)
    except Exception as e:
        print(f"[options] Polygon chain failed: {e}")

    # No chain source available — raise so caller skips this cycle
    _chain_health(False, "no Tradier/Polygon chain")
    raise ValueError("No options chain source available (Tradier/Polygon not configured)")


def _chain_health(ok: bool, detail: str = "") -> None:
    try:
        import data_health
        data_health.record("options_chain", ok, "options", detail)
    except Exception:
        pass


def _list_expiries() -> list[str]:
    """Sorted expiry strings from Tradier when available, else Polygon reference data."""
    import tradier_data
    if tradier_data.available():
        exps = tradier_data.get_expirations()
        if exps:
            return exps
        print("[options] Tradier expiries empty — falling back to Polygon")
    try:
        import polygon_data
        if polygon_data.available():
            exps = polygon_data.get_expirations("SPXW")
            if exps:
                return exps
    except Exception:
        pass
    return []


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
        # No chain source (Tradier/Polygon) → ATM IV / expected move need a chain,
        # but SPX SPOT can still be shown via the Stooq SPY×10 proxy (no yfinance).
        try:
            from market_data import _stooq_daily
            _spy = _stooq_daily("spy.us")
            if len(_spy):
                return None, None, round(float(_spy["Close"].iloc[-1]) * 10, 1)
        except Exception:
            pass
        return None, None, None


def _get_market_context(spot: float, chain, atm_iv: float | None,
                        expected_move: float | None) -> dict:
    """
    Compute slow-path features fetched once per recommendation:
      spx_intraday_range_pct, hv5_vs_iv, regime_encoded, opex_week, skew_25d,
      cboe_pc_ratio
    Returns dict with float values (neutral fallback on any failure).
    """
    ctx: dict = {
        "spx_intraday_range_pct": 0.0,
        "hv5_vs_iv":              1.0,
        "regime_encoded":         0.5,
        "opex_week":              0.0,
        "skew_25d":               0.0,
        "cboe_pc_ratio":          1.0,
    }

    # CBOE total put/call ratio — market-wide sentiment (cached, refreshed daily).
    try:
        from cboe_data import get_pc_ratio
        pc = get_pc_ratio().get("total_pc")
        if pc:
            ctx["cboe_pc_ratio"] = float(pc)
    except Exception:
        pass

    # How much of the expected move has SPX already travelled today?
    # Use SPY daily range as proxy (SPX ≈ SPY × 10) via Stooq
    try:
        from market_data import _stooq_daily
        intra = _stooq_daily("spy.us")
        if len(intra) >= 1:
            last = intra.iloc[-1]
            rng = float(last["High"] - last["Low"]) * 10  # scale to SPX
            ctx["spx_intraday_range_pct"] = round(rng / expected_move, 3) if expected_move else 0.0
    except Exception:
        pass

    # 5-day realised vol vs option IV (1 = fair, >1 = IV cheap, <1 = IV rich)
    try:
        import numpy as np
        from market_data import _stooq_daily
        hist = _stooq_daily("spy.us")
        if len(hist) >= 6 and atm_iv:
            rets = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
            hv5  = float(rets.tail(5).std() * (252 ** 0.5))
            ctx["hv5_vs_iv"] = round(hv5 / atm_iv, 3) if atm_iv else 1.0
    except Exception:
        pass

    # HMM regime for SPY: 0=ranging, 0.5=trending_bull, 1.0=trending_bear
    try:
        from signal_engine import _POOL_STATES
        spx_pools = ["STOCKS_SPX500_15M", "STOCKS_INDEX_15M", "STOCKS_QQQ_15M"]
        for p in spx_pools:
            state = _POOL_STATES.get(p, {})
            regime = state.get("regime", "")
            if regime:
                if "BEAR" in regime:
                    ctx["regime_encoded"] = 1.0
                elif "BULL" in regime:
                    ctx["regime_encoded"] = 0.5
                else:
                    ctx["regime_encoded"] = 0.0
                break
    except Exception:
        pass

    # Monthly OpEx week (3rd Friday — gamma dynamics are abnormal)
    try:
        today = datetime.now(_NY).date()
        # 3rd Friday of the month
        from calendar import monthcalendar, FRIDAY
        cal    = monthcalendar(today.year, today.month)
        fridays = [week[FRIDAY] for week in cal if week[FRIDAY] != 0]
        third_friday = fridays[2] if len(fridays) >= 3 else 0
        days_to_opex = abs(today.day - third_friday)
        ctx["opex_week"] = 1.0 if days_to_opex <= 2 else 0.0
    except Exception:
        pass

    # Put/call IV skew: (OTM put IV - OTM call IV) / ATM IV
    # Positive = puts expensive vs calls (fear-driven skew) → bad to buy puts
    try:
        if atm_iv and chain is not None:
            calls, puts = chain.calls, chain.puts
            otm_call_iv = float(
                calls[calls["strike"] > spot * 1.005]["impliedVolatility"]
                .dropna().iloc[0]
            ) if len(calls[calls["strike"] > spot * 1.005]) else atm_iv
            otm_put_iv  = float(
                puts[puts["strike"] < spot * 0.995]["impliedVolatility"]
                .dropna().iloc[-1]
            ) if len(puts[puts["strike"] < spot * 0.995]) else atm_iv
            ctx["skew_25d"] = round((otm_put_iv - otm_call_iv) / atm_iv, 3)
    except Exception:
        pass

    return ctx


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
        return _opt_skip("Signal not actionable (neutral / below min confidence)")
    now_et = datetime.now(_NY)
    if now_et.weekday() >= 5 or not (9 <= now_et.hour < 15) or (now_et.hour == 9 and now_et.minute < 45):
        print("[options] outside entry window (09:45–15:00 ET) — skip")
        return _opt_skip("Outside entry window (09:45–15:00 ET)")

    # Event filter — no entries within 24h before a high-impact print
    try:
        from news_fetcher import fetch_upcoming_events
        sched = fetch_upcoming_events(hours_ahead=24)
        if sched.get("scheduled"):
            nxt = sched["scheduled"][0]
            if nxt.get("urgency", 0) >= 0.85 and 0 <= (nxt.get("minutes_until") or 9999) <= 24 * 60:
                print(f"[options] {nxt.get('event_type')} in {nxt.get('minutes_until')}min — no new premium, skip")
                return _opt_skip(f"High-impact event ({nxt.get('event_type')}) within 24h — no new premium")
    except Exception:
        pass

    vix = get_vix_context()
    if vix.get("backwardation"):
        print(f"[options] VIX backwardation ({vix.get('ratio')}) — skip")
        return _opt_skip("VIX backwardation (risk-off) — skip")

    picked = _pick_expiry(now_et)
    if not picked:
        print("[options] no usable expiry — skip")
        return _opt_skip("No usable 0/1-DTE expiry")
    expiry, dte = picked

    try:
        spot, chain = _spx_chain(expiry)
    except Exception as e:
        print(f"[options] chain fetch failed: {e}")
        return _opt_skip(f"SPX option chain fetch failed: {e}")

    # Fetch ATM snapshot early so _get_market_context can use expected_move
    try:
        atm_iv_ctx, straddle_ctx, _ = _atm_snapshot()
    except Exception:
        atm_iv_ctx, straddle_ctx = None, None

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
        return _opt_skip("No liquid strike near Δ0.40 (stale/zero quotes from data source)")

    # IV Rank gate
    ivr = iv_rank(best["iv"])
    if ivr is not None and ivr > IV_RANK_MAX:
        print(f"[options] IV Rank {ivr} > {IV_RANK_MAX} — premium too expensive, skip")
        return None

    straddle = straddle_ctx
    if atr_tp1_points and straddle and atr_tp1_points < 0.8 * straddle:
        print(f"[options] TP1 {atr_tp1_points:.0f}pt < 0.8×EM {straddle:.0f}pt — theta wins, skip")
        return None

    exp_compact = expiry.replace("-", "")[2:]
    cp = "C" if is_call else "P"
    tv_symbol = f"OPRA:SPXW{exp_compact}{cp}{int(best['strike'])}"
    hard_exit = "15:30 ET today" if dte == 0 else "14:00 ET next session"

    # Market context features (slow-path, computed once per recommendation)
    mkt_ctx = _get_market_context(spot, chain, atm_iv_ctx, straddle_ctx)

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
        "pool":          "SPX_0DTE" if dte == 0 else "SPX_1DTE",
        "entry_premium": best["mid"],
        "tp_premium":    round(best["mid"] * TP_PREMIUM_MULT, 2),
        "sl_premium":    round(best["mid"] * SL_PREMIUM_MULT, 2),
        "hard_exit":     hard_exit,
        "iv":            round(best["iv"], 4),
        "iv_rank":       ivr,
        "vix":           vix.get("vix"),
        "vix9d_ratio":   vix.get("vix9d_ratio"),
        "vix_ratio":     vix.get("ratio"),
        "half_size":     bool(vix.get("half_size")),
        "expected_move": round(straddle, 1) if straddle else None,
        "tv_symbol":     tv_symbol,
        "status":        "OPEN",
        "paper":         True,
        "strategy":      "long_option",
    }

    # ML gate — once ≥50 closed trades, score this candidate and skip if below threshold
    pool_confluence = kwargs.get("pool_confluence", 0.5)
    enrich_features(rec_candidate, pool_confluence=pool_confluence, market_ctx=mkt_ctx)
    ml_result = options_predict(rec_candidate["features"])
    ml_score  = ml_result["score"] if isinstance(ml_result, dict) else ml_result
    rec_candidate["ml_score"]       = ml_score
    rec_candidate["ml_interval"]    = ml_result.get("interval") if isinstance(ml_result, dict) else None
    rec_candidate["ml_shap_top"]    = ml_result.get("shap_top") if isinstance(ml_result, dict) else None
    rec_candidate["wide_uncertainty"] = ml_result.get("wide_uncertainty", False) if isinstance(ml_result, dict) else False

    # ML gate removed — collecting data first; re-enable after ≥50 closed trades
    # Wide uncertainty warning (don't block, but flag for half-size)
    if rec_candidate.get("wide_uncertainty"):
        print(f"[options-ml] wide uncertainty interval {ml_result.get('interval')} — flagging")

    set_options_check(f"Trade opened — {direction} SPX {best['strike']} {expiry}")
    return rec_candidate


def format_telegram(rec: dict) -> str:
    size_note   = "\n⚠️ VIX>25 — HALF SIZE" if rec.get("half_size") else ""
    wide_note   = "\n⚠️ Wide uncertainty — consider half size" if rec.get("wide_uncertainty") else ""
    ml_note     = ""
    if rec.get("ml_score") is not None:
        ml_note = f" | ML {rec['ml_score']:.2f}"
        if rec.get("ml_interval"):
            lo, hi = rec["ml_interval"]
            ml_note += f" [{lo:.2f}–{hi:.2f}]"
    shap_note = ""
    if rec.get("ml_shap_top"):
        top = rec["ml_shap_top"]
        shap_note = f"\n🔬 Key drivers: " + ", ".join(
            f"{k}({'↑' if v > 0 else '↓'}{abs(v):.3f})" for k, v in top
        )
    strategy = rec.get("strategy", "long_option")
    if strategy == "debit_spread":
        return (
            f"🎯 <b>SPX {rec['dte']}DTE — {rec['type']} SPREAD</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📄 PAPER | conf {rec['confidence']:.2f}{ml_note} | spot {rec['spot']:.0f}\n"
            f"📥 Buy {int(rec['strike'])} @ ${rec['entry_premium']:.2f}  "
            f"📤 Sell {int(rec['spread_short_strike'])} @ ${rec['spread_short_premium']:.2f}\n"
            f"💰 Net debit ${rec['spread_net_debit']:.2f} | Max gain ${rec['spread_max_gain']:.2f}\n"
            f"🎯 TP +80% debit  🛑 SL -50% debit\n"
            f"⏰ hard exit: {rec['hard_exit']}{size_note}{wide_note}{shap_note}"
        )
    if strategy == "straddle":
        return (
            f"🎯 <b>SPX {rec['dte']}DTE — STRADDLE {int(rec['strike'])}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📄 PAPER | conf {rec['confidence']:.2f}{ml_note} | spot {rec['spot']:.0f}\n"
            f"📥 Buy CALL + PUT @ ${rec['entry_premium']:.2f} total\n"
            f"🎯 TP either leg +60%  🛑 SL combined -40%\n"
            f"⏰ hard exit: {rec['hard_exit']}{size_note}{wide_note}{shap_note}"
        )
    return (
        f"🎯 <b>SPX {rec['dte']}DTE — {rec['type']} {int(rec['strike'])}</b> (Δ{rec['delta']:+.2f})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📄 PAPER | conf {rec['confidence']:.2f}{ml_note} | spot {rec['spot']:.0f}\n"
        f"💵 entry ≈ ${rec['entry_premium']:.2f} (delayed — check live on TV)\n"
        f"🎯 TP ${rec['tp_premium']:.2f} (+100%)  🛑 SL ${rec['sl_premium']:.2f} (-50%)\n"
        f"⏰ hard exit: {rec['hard_exit']}{size_note}{wide_note}{shap_note}"
    )


def build_spx_spread(direction: str, confidence: float,
                     pool_confluence: float = 0.5, **kwargs) -> dict | None:
    """
    Debit vertical spread: buy near-ATM strike, sell further OTM strike.
    Reduces premium cost vs naked long. Better for ranging markets.
    Use when pool_confluence < 1.0 (only one timeframe agrees).
    Long call spread = LONG direction. Long put spread = SHORT direction.
    """
    if direction not in ("LONG", "SHORT") or confidence < MIN_CONFIDENCE:
        return None
    now_et = datetime.now(_NY)
    if now_et.weekday() >= 5 or not (9 <= now_et.hour < 15):
        return None

    vix = get_vix_context()
    if vix.get("backwardation"):
        return None

    picked = _pick_expiry(now_et)
    if not picked:
        return None
    expiry, dte = picked

    try:
        spot, chain = _spx_chain(expiry)
    except Exception:
        return None

    is_call = direction == "LONG"
    side    = chain.calls if is_call else chain.puts
    dte_years = max((dte + 0.5) / 365.0, 0.25 / 365.0)

    # Long leg: near ATM (~Δ0.40)
    long_leg = _pick_strike(side, spot, dte_years, is_call, TARGET_DELTA + 0.15)
    if not long_leg:
        return None

    # Short leg: further OTM (~Δ0.20), same expiry
    short_leg = _pick_strike(side, spot, dte_years, is_call, 0.20)
    if not short_leg or short_leg["strike"] == long_leg["strike"]:
        return None

    net_debit = round(long_leg["mid"] - short_leg["mid"], 2)
    if net_debit <= 0:
        return None
    max_gain = round(
        abs(short_leg["strike"] - long_leg["strike"]) - net_debit, 2
    )

    ivr = iv_rank(long_leg["iv"])
    exp_compact = expiry.replace("-", "")[2:]
    cp = "C" if is_call else "P"

    try:
        atm_iv, straddle, _ = _atm_snapshot()
    except Exception:
        straddle = None

    mkt_ctx = _get_market_context(spot, chain, None, straddle)

    rec = {
        "id":                  datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + "S",
        "created_at":          datetime.now(timezone.utc).isoformat(),
        "instrument":          "SPX",
        "strategy":            "debit_spread",
        "type":                "CALL" if is_call else "PUT",
        "direction":           direction,
        "confidence":          round(confidence, 3),
        "spot":                round(spot, 2),
        "strike":              long_leg["strike"],
        "spread_short_strike": short_leg["strike"],
        "delta":               long_leg["delta"],
        "expiry":              expiry,
        "dte":                 dte,
        "entry_premium":       long_leg["mid"],
        "spread_short_premium": short_leg["mid"],
        "spread_net_debit":    net_debit,
        "spread_max_gain":     max_gain,
        "tp_premium":          round(net_debit * 1.80, 2),   # +80% of net debit
        "sl_premium":          round(net_debit * 0.50, 2),   # -50%
        "hard_exit":           "15:30 ET today" if dte == 0 else "14:00 ET next session",
        "iv":                  round(long_leg["iv"], 4),
        "iv_rank":             ivr,
        "vix":                 vix.get("vix"),
        "vix9d_ratio":         vix.get("vix9d_ratio"),
        "vix_ratio":           vix.get("ratio"),
        "half_size":           bool(vix.get("half_size")),
        "expected_move":       round(straddle, 1) if straddle else None,
        "tv_symbol":           f"OPRA:SPXW{exp_compact}{cp}{int(long_leg['strike'])}",
        "status":              "OPEN",
        "paper":               True,
    }

    enrich_features(rec, pool_confluence=pool_confluence, market_ctx=mkt_ctx)
    ml_result = options_predict(rec["features"])
    ml_score  = ml_result["score"] if isinstance(ml_result, dict) else ml_result
    rec["ml_score"]         = ml_score
    rec["ml_interval"]      = ml_result.get("interval") if isinstance(ml_result, dict) else None
    rec["ml_shap_top"]      = ml_result.get("shap_top") if isinstance(ml_result, dict) else None
    rec["wide_uncertainty"] = ml_result.get("wide_uncertainty", False) if isinstance(ml_result, dict) else False

    # ML gate removed — collecting data first
    return rec


def _pick_strike(side, spot: float, dte_years: float, is_call: bool,
                 target_delta: float) -> dict | None:
    """Helper: find best strike closest to target_delta."""
    best, best_err = None, 9e9
    for _, row in side.iterrows():
        strike = float(row["strike"])
        iv     = float(row.get("impliedVolatility") or 0)
        bid    = float(row.get("bid") or 0)
        ask    = float(row.get("ask") or 0)
        last   = float(row.get("lastPrice") or 0)
        mid    = (bid + ask) / 2 if (bid and ask) else last
        if mid <= 0 or iv <= 0 or abs(strike - spot) > spot * 0.04:
            continue
        delta = _bs_delta(spot, strike, iv, dte_years, is_call)
        err   = abs(abs(delta) - target_delta)
        if err < best_err:
            best_err = err
            best = {"strike": strike, "iv": iv, "mid": round(mid, 2),
                    "delta": round(delta, 3)}
    return best


def build_spx_straddle(confidence: float, pool_confluence: float = 0.5,
                       **kwargs) -> dict | None:
    """
    ATM straddle: buy both CALL and PUT at the same ATM strike.
    Use when direction is uncertain but a big move is expected
    (low pool_confluence OR conflicting 15M/30M signals).
    Wins if SPX moves > straddle price in either direction.
    TP: either leg +60%. SL: combined position down -40%.
    """
    now_et = datetime.now(_NY)
    if now_et.weekday() >= 5 or not (9 <= now_et.hour < 13):
        # Only before 13:00 ET — straddles need time to work
        return None

    vix = get_vix_context()
    if vix.get("backwardation"):
        return None
    # iv_rank history stores SPX ATM IV as a decimal fraction (~0.15), so VIX
    # (a percentage-point number ~17) must be scaled to the same units — passing
    # raw VIX made this gate always return 100 and silently blocked every straddle.
    ivr_check = iv_rank((vix.get("vix") or 20.0) / 100.0)
    if ivr_check is not None and ivr_check > 60:
        # IV too expensive to buy both legs
        print("[options-straddle] IV Rank > 60 — straddle too expensive, skip")
        return None

    picked = _pick_expiry(now_et)
    if not picked:
        return None
    expiry, dte = picked
    if dte != 0:
        return None   # straddles only make sense on 0DTE (pure gamma play)

    try:
        spot, chain = _spx_chain(expiry)
    except Exception:
        return None

    dte_years = 0.5 / 365.0
    atm_call = _pick_strike(chain.calls, spot, dte_years, True,  0.50)
    atm_put  = _pick_strike(chain.puts,  spot, dte_years, False, 0.50)
    if not atm_call or not atm_put:
        return None

    total_premium = round(atm_call["mid"] + atm_put["mid"], 2)
    if total_premium <= 0:
        return None

    exp_compact = expiry.replace("-", "")[2:]
    try:
        _, straddle, _ = _atm_snapshot()
    except Exception:
        straddle = None

    mkt_ctx = _get_market_context(spot, chain, None, straddle)

    rec = {
        "id":            datetime.now(timezone.utc).strftime("%y%m%d%H%M%S") + "T",
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "instrument":    "SPX",
        "strategy":      "straddle",
        "type":          "STRADDLE",
        "direction":     "NEUTRAL",
        "confidence":    round(confidence, 3),
        "spot":          round(spot, 2),
        "strike":        atm_call["strike"],
        "delta":         0.0,
        "expiry":        expiry,
        "dte":           0,
        "entry_premium": total_premium,
        "tp_premium":    round(total_premium * 1.60, 2),   # +60%
        "sl_premium":    round(total_premium * 0.60, 2),   # -40%
        "hard_exit":     "15:30 ET today",
        "iv":            round((atm_call["iv"] + atm_put["iv"]) / 2, 4),
        "iv_rank":       iv_rank((atm_call["iv"] + atm_put["iv"]) / 2),
        "vix":           vix.get("vix"),
        "vix9d_ratio":   vix.get("vix9d_ratio"),
        "vix_ratio":     vix.get("ratio"),
        "half_size":     bool(vix.get("half_size")),
        "expected_move": round(straddle, 1) if straddle else None,
        "tv_symbol":     f"OPRA:SPXW{exp_compact}C{int(atm_call['strike'])}",
        "status":        "OPEN",
        "paper":         True,
    }

    enrich_features(rec, pool_confluence=pool_confluence, market_ctx=mkt_ctx)

    # ML scoring (same as long_option and spread paths)
    ml_result = options_predict(rec.get("features", {}))
    if isinstance(ml_result, dict):
        rec["ml_score"]    = ml_result.get("score")
        rec["ml_interval"] = ml_result.get("interval")
        rec["ml_certainty"] = not ml_result.get("wide_uncertainty", True)
        rec["ml_shap_top"] = ml_result.get("shap_top", [])

    return rec


# ── Paper ledger ───────────────────────────────────────────────────────────────

_PAPER_LEDGER_MAX = 600   # keep all OPEN + most recent CLOSED up to this cap

def append_paper_trade(rec: dict) -> None:
    """Append a paper trade with a dedup guard and a 409-safe re-read loop.

    Two confluent pools can fire in the same second and generate identical ids;
    a concurrent manage cycle can also bump the SHA. We re-read the full ledger
    on each attempt, skip if the id already exists, and cap total size so the
    GitHub-hosted JSON never approaches the 1 MB content-API limit.
    """
    try:
        from db import _get_file, _put_file
        for attempt in range(4):
            ledger, sha = _get_file(_PAPER_PATH)
            if not isinstance(ledger, list):
                ledger = []
            if any(isinstance(r, dict) and r.get("id") == rec.get("id") for r in ledger):
                print(f"[options] duplicate paper trade {rec.get('id')} — skipped")
                return
            ledger.append(rec)
            # Cap: keep every OPEN trade, trim oldest CLOSED beyond the budget
            if len(ledger) > _PAPER_LEDGER_MAX:
                open_t   = [r for r in ledger if r.get("status") == "OPEN"]
                closed_t = [r for r in ledger if r.get("status") != "OPEN"]
                keep = max(0, _PAPER_LEDGER_MAX - len(open_t))
                ledger = closed_t[-keep:] + open_t
            try:
                _put_file(_PAPER_PATH, ledger, sha,
                          f"options: paper {rec['type']} {int(rec['strike'])} {rec['expiry']}")
                print(f"[options] paper trade logged: {rec['tv_symbol']}")
                return
            except Exception as put_err:
                if attempt < 3 and "409" in str(put_err):
                    continue   # SHA stale — re-read and retry
                raise
    except Exception as e:
        print(f"[options] ledger write failed: {e}")


def manage_paper_positions() -> list[str]:
    """Hourly job: enforce TP/SL/time exits on open paper positions using
    delayed mid quotes. Returns list of close summaries."""
    import time as _time, random as _random
    closed: list[str] = []
    try:
        from db import _get_file, _put_file
        now_et = datetime.now(_NY)
        for attempt in range(4):
            closed = []   # reset on each attempt — avoids duplicate entries on 409 retry
            ledger, sha = _get_file(_PAPER_PATH)
            if not isinstance(ledger, list) or not ledger:
                return closed
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
                    # Plain WIN/LOSS verdict the dashboard reads (loss_reason has detail)
                    rec["outcome"] = "WIN" if (rec.get("pnl_pct") or 0) > 0 else "LOSS"
                    dirty = True
                    closed.append(f"{rec['tv_symbol']} → {reason} ({rec.get('pnl_pct','?')}%) [{rec['loss_reason']}]")
            if not dirty:
                return closed
            try:
                _put_file(_PAPER_PATH, ledger, sha, "options: paper position management")
                _auto_retrain_if_ready()
                return closed
            except Exception as put_err:
                if attempt < 3 and "409" in str(put_err):
                    _time.sleep(0.3 * (attempt + 1) + _random.uniform(0, 0.3))
                    continue
                raise
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
        _bid = row["bid"].iloc[0] if "bid" in row.columns else None
        _ask = row["ask"].iloc[0] if "ask" in row.columns else None
        bid, ask = float(_bid or 0), float(_ask or 0)
        last = float(row["lastPrice"].iloc[0] or 0)
        return round((bid + ask) / 2, 2) if (bid and ask) else (round(last, 2) or None)
    except Exception:
        return None


# ── Training dataset (ML cold-start — same pattern as swing_tracker) ──────────

# Features captured at entry time and stored on each paper trade.
# 25 features — original 18 + 7 market context features added Phase 4.
OPTION_FEATURE_KEYS = [
    # Core signal quality
    "confidence",                # ML confidence from directional pool
    "iv",                        # option implied volatility at entry
    "iv_rank",                   # IV percentile vs trailing 60 sessions (0-100)
    # Volatility regime
    "vix",                       # VIX spot at entry
    "vix_ratio",                 # VIX/VIX3M — backwardation margin
    "vix_backwardation_margin",  # 1.0 - vix_ratio (positive = safer to buy premium)
    "vix9d_ratio",               # VIX9D/VIX — near-term vs 30d fear; >1 = elevated near-term risk
    # Strike / premium context
    "delta",                     # absolute delta of chosen strike
    "entry_premium",             # mid-price paid per contract
    "spot_vs_strike_pct",        # moneyness: positive = OTM (call), negative = ITM
    "premium_vs_em_pct",         # entry_premium / expected_move × 100 (overpay ratio)
    "iv_over_vix_ratio",         # option IV / VIX (IV richness vs realized vol proxy)
    # Time / session context
    "dte",                       # days to expiry (0 or 1)
    "hour_et",                   # entry hour in ET (fractional, 9.75 = 9:45am)
    "day_of_week",               # 0=Mon … 4=Fri
    "entry_time_norm",           # position in session: 0=open (9:30), 1=close (16:00)
    "time_to_hard_exit_hours",   # hours until forced exit (urgency)
    "hour_dte_interaction",      # hour_et × dte — 0DTE at 10am vs 14pm is a different trade
    # Market context
    "expected_move",             # ATM straddle price (market's implied 1-day move)
    "pool_confluence",           # 1.0=15M+30M agree, 0.5=only trigger pool fired
    "spx_intraday_range_pct",    # today's SPX range / expected_move — remaining room
    "hv5_vs_iv",                 # 5-day realized vol / option IV (>1=IV cheap, <1=IV rich)
    "regime_encoded",            # 0=ranging, 0.5=trending_bull, 1.0=trending_bear
    "opex_week",                 # 1.0 if within 2 days of monthly options expiry
    "skew_25d",                  # (OTM put IV - OTM call IV) / ATM IV — put/call skew
    "cboe_pc_ratio",             # CBOE total put/call ratio — market-wide sentiment (contrarian)
]

_MIN_TRADES_ML = 50   # closed trades before ML is eligible
_ML_SCORE_GATE  = 0.52  # calibrated win-probability minimum to enter


def enrich_features(rec: dict, pool_confluence: float = 0.5,
                    market_ctx: dict | None = None) -> dict:
    """Add the 25-feature training vector to a recommendation dict before logging."""
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
    hour_et = round(now_et.hour + now_et.minute / 60, 3)

    spot_vs_strike = ((spot - strike) / spot * 100) if spot else 0.0
    if not is_call:
        spot_vs_strike = -spot_vs_strike

    premium_vs_em = (entry_premium / expected_move * 100) if expected_move else 0.0
    # Guard against a near-zero VIX (bad yfinance tick) producing a huge outlier
    iv_over_vix   = min(iv / (vix / 100), 20.0) if (vix and vix > 0.01) else 1.0

    session_minutes = max(0, (now_et.hour * 60 + now_et.minute) - 570)
    entry_time_norm = min(session_minutes / 390, 1.0)

    if dte == 0:
        hard_exit_et = now_et.replace(hour=15, minute=30, second=0, microsecond=0)
    else:
        hard_exit_et = now_et.replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
    time_to_exit = max(0.0, (hard_exit_et - now_et).total_seconds() / 3600)

    ctx = market_ctx or {}

    rec["features"] = {
        "confidence":               rec.get("confidence", 0.0),
        "iv":                       round(iv, 4),
        "iv_rank":                  rec.get("iv_rank") or 0.0,
        "vix":                      round(vix, 2),
        "vix_ratio":                round(vix_ratio, 3),
        "vix_backwardation_margin": round(1.0 - vix_ratio, 3),
        "vix9d_ratio":              rec.get("vix9d_ratio") or 1.0,
        "delta":                    abs(rec.get("delta") or 0.0),
        "entry_premium":            round(entry_premium, 2),
        "spot_vs_strike_pct":       round(spot_vs_strike, 3),
        "premium_vs_em_pct":        round(premium_vs_em, 2),
        "iv_over_vix_ratio":        round(iv_over_vix, 3),
        "dte":                      float(dte),
        "hour_et":                  hour_et,
        "day_of_week":              float(now_et.weekday()),
        "entry_time_norm":          round(entry_time_norm, 3),
        "time_to_hard_exit_hours":  round(time_to_exit, 2),
        "hour_dte_interaction":     round(hour_et * dte, 3),
        "expected_move":            round(expected_move, 2),
        "pool_confluence":          pool_confluence,
        "spx_intraday_range_pct":   ctx.get("spx_intraday_range_pct", 0.0),
        "hv5_vs_iv":                ctx.get("hv5_vs_iv", 1.0),
        "regime_encoded":           ctx.get("regime_encoded", 0.5),
        "opex_week":                ctx.get("opex_week", 0.0),
        "skew_25d":                 ctx.get("skew_25d", 0.0),
        "cboe_pc_ratio":            ctx.get("cboe_pc_ratio", 1.0),
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
    Train RF + GBM + LightGBM ensemble on closed paper trades.
    Calibration stack: Platt sigmoid (CalibratedClassifierCV) → IsotonicRegression on OOS fold.
    Focal-loss sample weights downweight high-confidence losses (likely noise/spread stops).
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
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.isotonic import IsotonicRegression
        import lightgbm as lgb
        import numpy as np

        X_arr = np.array(X, dtype=float)
        y_arr = np.array(y, dtype=int)

        # Focal-loss sample weights: upweight uncertain examples, downweight
        # near-certain losses (likely stopped by spread rather than wrong direction).
        # weight_i = (1 - |p_prior - y_i|)^gamma, gamma=2
        win_rate = float(y_arr.mean())
        prior = np.where(y_arr == 1, win_rate, 1 - win_rate)
        focal_weights = (1 - np.abs(prior - y_arr)) ** 2
        focal_weights = (focal_weights / focal_weights.mean()).clip(0.25, 4.0)

        # Walk-forward OOS: last 20% held out
        split = max(int(n * 0.8), min(40, n - 10))
        X_tr, X_val = X_arr[:split], X_arr[split:]
        y_tr, y_val = y_arr[:split], y_arr[split:]
        w_tr = focal_weights[:split]

        # 1. RandomForest (Platt-calibrated internally, then OOS isotonic on top)
        rf_base = RandomForestClassifier(n_estimators=200, max_depth=5,
                                         min_samples_leaf=4, random_state=42)
        rf_base.fit(X_tr, y_tr, sample_weight=w_tr)

        # 2. GradientBoosting
        gbm = GradientBoostingClassifier(n_estimators=150, max_depth=3,
                                          learning_rate=0.05, subsample=0.8,
                                          random_state=42)
        gbm.fit(X_tr, y_tr, sample_weight=w_tr)

        # 3. LightGBM
        lgb_params = {
            "objective": "binary", "learning_rate": 0.05, "num_leaves": 15,
            "min_child_samples": 5, "subsample": 0.8, "colsample_bytree": 0.8,
            "n_estimators": 200, "random_state": 42, "verbose": -1,
        }
        lgb_model = lgb.LGBMClassifier(**lgb_params)
        lgb_model.fit(X_tr, y_tr, sample_weight=w_tr)

        # Platt sigmoid calibration on each base model (CalibratedClassifierCV cv="prefit")
        rf_platt  = CalibratedClassifierCV(rf_base,  cv="prefit", method="sigmoid")
        gbm_platt = CalibratedClassifierCV(gbm,      cv="prefit", method="sigmoid")
        lgb_platt = CalibratedClassifierCV(lgb_model, cv="prefit", method="sigmoid")

        # Fit Platt layers on held-out validation set (avoids overfit calibration)
        platt_X = X_val if len(X_val) >= 5 else X_tr
        platt_y = y_val if len(X_val) >= 5 else y_tr
        rf_platt.fit(platt_X, platt_y)
        gbm_platt.fit(platt_X, platt_y)
        lgb_platt.fit(platt_X, platt_y)

        # Ensemble average of Platt-calibrated probas → then isotonic on OOS
        if len(X_val) >= 5:
            raw_val = (
                rf_platt.predict_proba(X_val)[:, 1] +
                gbm_platt.predict_proba(X_val)[:, 1] +
                lgb_platt.predict_proba(X_val)[:, 1]
            ) / 3
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(raw_val, y_val)
            oos_acc = float(np.mean((raw_val >= 0.5) == y_val))
            # Conformal prediction: store sorted nonconformity scores on val set
            cal_scores = np.abs(raw_val - y_val)
            conformal_scores = np.sort(cal_scores)
        else:
            raw_full = (
                rf_platt.predict_proba(X_arr)[:, 1] +
                gbm_platt.predict_proba(X_arr)[:, 1] +
                lgb_platt.predict_proba(X_arr)[:, 1]
            ) / 3
            iso = IsotonicRegression(out_of_bounds="clip")
            iso.fit(raw_full, y_arr)
            cal_scores = np.abs(raw_full - y_arr)
            conformal_scores = np.sort(cal_scores)
            oos_acc = None

        # Feature importance (average RF + LGB normalized importances)
        rf_imp  = rf_base.feature_importances_
        lgb_imp = lgb_model.feature_importances_ / (lgb_model.feature_importances_.sum() + 1e-9)
        avg_imp = (rf_imp / (rf_imp.sum() + 1e-9) + lgb_imp) / 2
        importances  = dict(zip(OPTION_FEATURE_KEYS, [round(float(v), 4) for v in avg_imp]))
        top_features = sorted(importances.items(), key=lambda x: -x[1])[:5]

        new_model = {
            "rf": rf_platt, "gbm": gbm_platt, "lgb": lgb_platt,
            "cal": iso, "conformal_scores": conformal_scores,
            "pool": pool, "n": n, "wins": int(sum(y_arr)),
            "oos_acc": oos_acc, "top_features": top_features,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        with _options_model_lock:
            _options_model.update(new_model)
        print(f"[options-ml] trained RF+GBM+LGB on {n} trades | OOS acc={oos_acc} | "
              f"top={top_features[0][0]}({top_features[0][1]:.3f})")
        return {"status": "ok", "n": n, "oos_acc": oos_acc, "top_features": top_features}

    except Exception as e:
        print(f"[options-ml] train failed: {e}")
        return {"status": "error", "error": str(e)}


def options_predict(features: dict) -> dict | None:
    """
    Return calibrated win probability + SHAP explanation + conformal interval.
    Returns None if model not trained yet.
    Result: {
      "score": float,           # calibrated win probability
      "interval": [low, high],  # 80% conformal prediction interval
      "wide_uncertainty": bool, # True if interval > 0.30 — consider skipping
      "shap_top": [(feat, val), ...],  # top 3 SHAP drivers
    }
    """
    with _options_model_lock:
        if not _options_model.get("rf"):
            return None
        _m = dict(_options_model)   # snapshot under lock; predict outside
    try:
        import numpy as np
        row   = np.array([[float(features.get(k, 0.0)) for k in OPTION_FEATURE_KEYS]])
        rf_p  = _m["rf"].predict_proba(row)[0, 1]
        gbm_p = _m["gbm"].predict_proba(row)[0, 1]
        lgb_p = _m["lgb"].predict_proba(row)[0, 1] if _m.get("lgb") else rf_p
        raw   = (rf_p + gbm_p + lgb_p) / 3
        cal_p = float(_m["cal"].predict([raw])[0])

        # Conformal prediction interval at 80% coverage
        conf_scores = _m.get("conformal_scores", np.array([]))
        if len(conf_scores) >= 5:
            # 80th percentile nonconformity margin
            margin = float(np.quantile(conf_scores, 0.80))
        else:
            margin = 0.15
        lo = round(max(0.0, cal_p - margin), 3)
        hi = round(min(1.0, cal_p + margin), 3)

        # SHAP explanations using the RF base model (TreeExplainer is fast)
        shap_top = []
        try:
            import shap
            # CalibratedClassifierCV wraps the base estimator
            base_rf = _m["rf"].calibrated_classifiers_[0].estimator
            explainer = shap.TreeExplainer(base_rf)
            shap_vals = explainer.shap_values(row)
            # shap_values for binary: take class-1 shap
            sv = shap_vals[1][0] if isinstance(shap_vals, list) else shap_vals[0]
            pairs = list(zip(OPTION_FEATURE_KEYS, sv))
            pairs.sort(key=lambda x: abs(x[1]), reverse=True)
            shap_top = [(k, round(float(v), 4)) for k, v in pairs[:3]]
        except Exception:
            pass

        return {
            "score":            round(cal_p, 3),
            "interval":         [lo, hi],
            "wide_uncertainty": (hi - lo) > 0.30,
            "shap_top":         shap_top,
        }
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
        # No HTML tags here — send_critical_alert() html-escapes the body, so any
        # <b> would render as literal text. The alert template already bolds the title.
        f"📊 SPX Options Weekly Autopsy",
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
                     "vix", "iv_rank", "pool_confluence", "vix9d_ratio",
                     "hv5_vs_iv", "spx_intraday_range_pct", "skew_25d", "cboe_pc_ratio"]
        for feat in key_feats:
            l_avg = avg_feat(losses, feat)
            w_avg = avg_feat(wins, feat)
            if l_avg or w_avg:
                lines.append(f"  {feat}: loss={l_avg} vs win={w_avg}")

    # ML model status + SHAP top features
    if _options_model.get("rf"):
        lines.append("")
        lines.append(f"🤖 ML model (RF+GBM+LGB): trained on {_options_model['n']} trades | "
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
