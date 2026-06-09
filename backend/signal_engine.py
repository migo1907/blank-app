"""
XAU/USD Signal Engine — Market-Aware Intelligence Layer

Scoring pipeline:
  1. KNN similarity (adaptive weights on 25 features F1–F25)
  2. Random Forest ensemble (pattern recognition)
  3. Gradient Boosting ensemble — XGBoost equivalent (item 2)
  4. News sentiment + velocity
  5. Regime detection — trending/ranging/volatile (item 1)
     Counter-trend on 2min/5min = valid pullback, NOT blocked
  6. Session kill-zone boost with quality weighting (item 5)
  7. Feature confluence score (how many of 21 features agree)
  8. KNN + RF agreement gate — boosts when both models agree (item 4)
  9. Trade clustering prevention — reduces confidence on same-dir streak (item 3)
 10. News-gate (block signals when velocity is CONFLICTED)
 11. Day-of-week penalty (Monday open / Friday close are thin)
 12. Dynamic weight adjustment based on recent win rates per component
"""
from datetime import datetime, timezone, timedelta
from ml_model import get_model, Features
from ml_ensemble import get_rf, get_gbm
from db import recent_outcomes, recent_news, insert_signal, expire_old_signals

# ── Latest feature cache — updated on every webhook, read by scheduler ────────────
# Persisted to GitHub data branch so it survives Railway restarts.
# Keyed by pool name — scheduler passes real market state to generate_signal().
import threading as _threading
_latest_features: dict[str, Features] = {}
_FEATURE_CACHE_PATH = "data/feature_cache.json"
_feature_cache_lock = _threading.Lock()


def update_latest_features(pool: str, features: Features) -> None:
    """Cache latest features in memory and persist to GitHub data branch."""
    _latest_features[pool] = features
    # Serialize GitHub writes — concurrent heartbeats race on the same SHA
    if not _feature_cache_lock.acquire(blocking=False):
        return  # another thread is already writing; in-memory is updated, skip duplicate write
    try:
        from db import _get_file, _put_file
        from datetime import datetime, timezone as _tz
        for attempt in range(3):
            try:
                existing, sha = _get_file(_FEATURE_CACHE_PATH)
                # Merge valid in-memory pools — exclude empty-string pool (XAUUSD_4H etc.)
                payload = {k: v for k, v in (existing if isinstance(existing, dict) else {}).items() if k}
                for _pool, _feat in _latest_features.items():
                    if not _pool:
                        continue  # skip unmapped pools
                    payload[_pool] = {
                        "f1":  _feat.f1,  "f2":  _feat.f2,  "f3":  _feat.f3,
                        "f4":  _feat.f4,  "f5":  _feat.f5,  "f6":  _feat.f6,
                        "f7":  _feat.f7,  "f8":  _feat.f8,  "f9":  _feat.f9,
                        "f10": _feat.f10, "f11": _feat.f11, "f12": _feat.f12,
                        "f13": _feat.f13, "f14": _feat.f14, "f15": _feat.f15,
                        "f16": _feat.f16, "f17": _feat.f17, "f18": _feat.f18,
                        "f19": _feat.f19, "f20": _feat.f20, "f21": _feat.f21,
                        "f22": _feat.f22, "f23": _feat.f23, "f24": _feat.f24,
                        "f25": _feat.f25,
                        "timestamp": datetime.now(_tz.utc).isoformat(),
                    }
                _put_file(_FEATURE_CACHE_PATH, payload, sha,
                          f"chore: update feature cache ({len(payload)} pools)")
                break
            except Exception as put_err:
                if attempt < 2 and "409" in str(put_err):
                    continue  # SHA stale — re-fetch on next iteration
                print(f"[features] Cache persist failed: {put_err}")
                break
    finally:
        _feature_cache_lock.release()


def load_feature_cache() -> None:
    """Load persisted feature cache from GitHub on startup — call once from lifespan."""
    try:
        from db import _get_file
        data, _ = _get_file(_FEATURE_CACHE_PATH)
        if not isinstance(data, dict):
            return
        for pool, fv in data.items():
            if not isinstance(fv, dict) or "f1" not in fv:
                continue
            if "f25" not in fv:
                print(f"[features] WARNING: pool {pool} cache missing f25 — will use 0.0 until next heartbeat")
            _latest_features[pool] = Features(
                f1=fv.get("f1",0.0),  f2=fv.get("f2",0.0),  f3=fv.get("f3",0.0),
                f4=fv.get("f4",0.0),  f5=fv.get("f5",0.0),  f6=fv.get("f6",0.0),
                f7=fv.get("f7",0.0),  f8=fv.get("f8",0.0),  f9=fv.get("f9",0.0),
                f10=fv.get("f10",0.0),f11=fv.get("f11",0.0),f12=fv.get("f12",0.0),
                f13=fv.get("f13",0.0),f14=fv.get("f14",0.0),f15=fv.get("f15",0.0),
                f16=fv.get("f16",0.0),f17=fv.get("f17",0.0),f18=fv.get("f18",0.0),
                f19=fv.get("f19",0.0),f20=fv.get("f20",0.0),f21=fv.get("f21",0.0),
                f22=fv.get("f22",0.0),f23=fv.get("f23",0.0),f24=fv.get("f24",0.0),
                f25=fv.get("f25",0.0),
            )
        print(f"[features] Loaded feature cache for {len(_latest_features)} pools from GitHub.")
    except Exception as e:
        print(f"[features] Cache load failed (first run?): {e}")


def get_latest_features(pool: str) -> Features | None:
    """Returns the most recent feature vector for a pool, or None if no data yet."""
    return _latest_features.get(pool)


# ── Option B: Backend ML entry gate ───────────────────────────────────────────
# Pine Script fires entries from its own (non-persistent) on-chart KNN. The backend
# re-scores each entry with its PERSISTENT, trained KNN + RF + GBM models before
# forwarding to Telegram. This is the only place the accumulated ML learning
# actually influences what signals reach the user.
import os as _os

# Lenient default — only blocks entries the trained models actively distrust.
ML_GATE_THRESHOLD = float(_os.environ.get("ML_GATE_THRESHOLD", "0.45"))

# Short-TTL in-memory cache for pool trade history. recent_outcomes() hits GitHub
# on every call (db._get_file has no caching), so without this a burst of entries
# during an active session would each trigger a full history fetch — latency +
# GitHub quota burn. A 60s TTL collapses same-minute bursts to one fetch while
# keeping history fresh enough for gate scoring.
import time as _time
_HISTORY_TTL_SECONDS = 60.0
_history_cache: dict[str, tuple[float, list[dict]]] = {}


def _cached_history(pool: str, limit: int = 500) -> list[dict]:
    now = _time.monotonic()
    cached = _history_cache.get(pool)
    if cached and (now - cached[0]) < _HISTORY_TTL_SECONDS:
        return cached[1]
    history = recent_outcomes(pool, limit)
    _history_cache[pool] = (now, history)
    return history


def invalidate_history_cache(pool: str) -> None:
    """Call after inserting a new outcome so the gate sees it on the next entry."""
    _history_cache.pop(pool, None)


def score_entry_gate(pool: str, direction: str) -> dict:
    """
    Re-score a Pine-fired entry using the backend's trained models.

    Returns a dict:
      {
        "pass":      bool,    # True → forward to Telegram
        "score":     float,   # combined win-probability in [0,1]
        "reason":    str,     # human-readable gate decision
        "components": {...},  # per-model scores for logging
      }

    Cold-start rule: if NONE of the pool's models are trained yet, the gate
    bypasses (always passes) so new pools can accumulate trades. Gating only
    kicks in once a pool has enough history to train.
    """
    features = get_latest_features(pool)
    if features is None:
        # No heartbeat features cached yet — can't score, let it through.
        return {"pass": True, "score": 0.5, "reason": "no_features_cached", "components": {}}

    history = _cached_history(pool, 500)
    knn = get_model(pool)
    rf  = get_rf(pool)
    gbm = get_gbm(pool)

    feat_list   = features.as_list()
    is_long     = direction == "LONG"
    components: dict[str, float] = {}

    # KNN — bull/bear probability, aligned to the trade direction.
    if len(history) >= knn.k:
        bull, bear = knn.predict(features, history)
        components["knn"] = bull if is_long else bear

    # RF — P(win) for this setup (direction-agnostic; trained on win/loss labels).
    if rf.is_trained:
        components["rf"] = rf.predict(feat_list)

    # GBM — P(win) for this setup.
    if gbm.is_trained:
        components["gbm"] = gbm.predict(feat_list)

    if not components:
        # Nothing trained yet → bypass so the pool can mature.
        return {"pass": True, "score": 0.5, "reason": "cold_start_bypass", "components": {}}

    score   = sum(components.values()) / len(components)
    passed  = score >= ML_GATE_THRESHOLD
    reason  = "approved" if passed else "rejected_low_confidence"
    return {"pass": passed, "score": round(score, 4), "reason": reason, "components": components}


# ── Base weights ────────────────────────────────────────────────────────────────
KNN_WEIGHT     = 0.35
RF_WEIGHT      = 0.25
GBM_WEIGHT     = 0.20
NEWS_WEIGHT    = 0.20
MIN_CONFIDENCE = 0.55        # XAUUSD — lowered from 0.62 (Option F: allow strong ML signals through)
MIN_CONFIDENCE_STOCKS = 0.60 # Stocks — lowered from 0.65


# ── Session intelligence (item 5) ─────────────────────────────────────────────
def _session_multiplier(now_utc: datetime, is_stock: bool = False) -> tuple[float, str]:
    h = now_utc.hour
    if is_stock:
        if 13 <= h < 16:  return 1.25, "NYSE_OPEN"       # 09:00–12:00 ET (incl. open half-hour)
        if 16 <= h < 21:  return 1.10, "NYSE_AFTERNOON"  # 12:00–17:00 ET (extended hours)
        if 11 <= h < 13:  return 0.90, "PRE_MARKET"      # 07:00–09:00 ET
        return 0.60, "CLOSED"
    if 13 <= h < 17:  return 1.30, "OVERLAP"      # London/NY overlap — highest gold volatility
    if 8  <= h < 13:  return 1.15, "LONDON"       # London session
    if 7  <= h < 8:   return 0.90, "LONDON_OPEN"  # First hour — erratic spreads
    if 17 <= h < 20:  return 1.10, "NEW_YORK"     # NY afternoon (London closed)
    if 20 <= h < 22:  return 0.90, "NY_LATE"      # Thin NY close
    if 0  <= h < 7:   return 0.85, "ASIAN"        # Low XAUUSD volume
    return 0.65, "OFF"


def _day_of_week_multiplier(now_utc: datetime) -> float:
    dow = now_utc.weekday()
    if dow == 0:        return 0.85
    if dow == 4:        return 0.85
    if dow in (5, 6):   return 0.0
    return 1.0


# ── Regime detection (item 1) ────────────────────────────────────────────────────
def _detect_regime(features: Features | None) -> str:
    if features is None:
        return "UNKNOWN"
    adx = abs(features.f2)
    atr = abs(features.f3)
    mtf = features.f16
    if atr > 0.70:
        return "VOLATILE"
    if adx > 0.40 and abs(mtf) >= 1.0:
        return "TRENDING_BULL" if mtf > 0 else "TRENDING_BEAR"
    if adx < 0.25:
        return "RANGING"
    return "NORMAL"


def _regime_context(regime: str, direction: str, pool: str = "") -> tuple[float, str]:
    is_scalp = pool.endswith("_2M") or pool.endswith("_5M")
    if regime == "TRENDING_BULL":
        if direction == "LONG":
            return 1.15, "TREND_FOLLOW"
        # Counter-trend short in bull: scalps allowed, swings penalised
        return (0.95, "PULLBACK_SHORT") if is_scalp else (0.80, "PULLBACK_SHORT")
    if regime == "TRENDING_BEAR":
        if direction == "SHORT":
            return 1.15, "TREND_FOLLOW"
        # Counter-trend long in bear: scalps allowed (ICT pullback), swings penalised
        return (0.95, "PULLBACK_LONG") if is_scalp else (0.80, "PULLBACK_LONG")
    if regime == "RANGING":
        return 0.82, "RANGING"
    if regime == "VOLATILE":
        return 0.92, "VOLATILE"
    return 1.00, "NORMAL"


# ── Trigger quality scoring ───────────────────────────────────────────────────
def _trigger_quality_multiplier(history: list[dict], trigger: str) -> float:
    if not history or not trigger:
        return 1.0
    trigger_trades = [
        t for t in history
        if t.get("trigger", "").upper() == trigger.upper()
    ]
    if len(trigger_trades) >= 5:
        wins = sum(
            1.0 if t.get("outcome") == "WIN" else
            0.5 if t.get("outcome") == "PARTIAL" else 0.0
            for t in trigger_trades
        )
        wr = wins / len(trigger_trades)
        if wr >= 0.55:   return 1.20
        if wr >= 0.45:   return 1.08
        if wr <= 0.25:   return 0.75
        if wr <= 0.35:   return 0.88
    return 1.0


def _rapid_fire_penalty(history: list[dict], direction: str, trigger: str, now: datetime) -> float:
    if not history:
        return 1.0
    last = history[0]
    try:
        last_time = datetime.fromisoformat(
            last.get("created_at", "2000-01-01T00:00:00").replace("Z", "+00:00")
        )
        if last_time.tzinfo is None:
            last_time = last_time.replace(tzinfo=timezone.utc)
        gap_seconds = (now - last_time).total_seconds()
        last_dir     = last.get("direction", "")
        last_trigger = last.get("trigger", "")
        if (gap_seconds < 30
                and last_dir == direction
                and last_trigger.upper() == trigger.upper()):
            return 0.15
    except Exception:
        pass
    return 1.0


# ── Trade clustering prevention (item 3) ───────────────────────────────────────────
def _clustering_multiplier(history: list[dict], direction: str, lookback: int = 4) -> float:
    if len(history) < lookback:
        return 1.0
    recent = history[:lookback]
    same_dir_losses = sum(
        1 for t in recent
        if t.get("direction") == direction and t.get("outcome") == "LOSS"
    )
    if same_dir_losses >= lookback:
        return 0.75
    if same_dir_losses >= lookback - 1:
        return 0.88
    return 1.0


# ── Feature confluence ────────────────────────────────────────────────────────────────
def _confluence_score(features: Features | None, direction: str, regime: str) -> float:
    if features is None:
        return 1.0
    bull = direction == "LONG"
    sign = 1.0 if bull else -1.0
    is_pullback = ("PULLBACK" in regime) or (
        regime == "TRENDING_BEAR" and direction == "LONG"
    ) or (
        regime == "TRENDING_BULL" and direction == "SHORT"
    )
    checks = [
        features.f1  * sign > 0,
        features.f2  * sign > 0,
        features.f4  * sign > 0,
        features.f5  * sign > 0,
        features.f8  * sign > 0,
        features.f9  * sign > 0,
        features.f10 * sign > 0,
        features.f11 * sign > 0,
        features.f13 * sign < 0,
        features.f21 * sign > 0,
    ]
    if not is_pullback:
        checks.append(features.f16 * sign > 0)
    if is_pullback:
        checks.append(abs(features.f14) > 0.5)
        checks.append(abs(features.f12) > 0.5)
    score = sum(checks) / len(checks)
    base = 0.70 + score * 0.70
    if bull and features.f21 < -0.5:
        base *= 0.78
    if bull and features.f5 > 0.5 and features.f16 < 0:
        base *= 0.82
    if not bull and features.f5 < -0.5:
        base *= 1.12
    if abs(features.f14) > 0.5:
        base *= 1.10
    vwap_stretch = abs(features.f21)
    mtf_opposing = (bull and features.f16 < -0.5) or (not bull and features.f16 > 0.5)
    if vwap_stretch > 0.6 and features.f21 * sign < 0 and not mtf_opposing:
        # Mean-reversion boost only when MTF trend is not strongly opposing
        if vwap_stretch > 0.9:
            base *= 1.18
        else:
            base *= 1.10
    elif features.f21 * sign > 0 and vwap_stretch > 0.5:
        base *= 1.05
    if abs(features.f24) > 0.5 and features.f21 * sign < 0:
        base *= 1.08
    if is_pullback:
        has_sweep   = abs(features.f12) > 0.3
        has_choch   = abs(features.f14) > 0.3
        has_fvg_q   = abs(features.f24) > 0.5
        has_willr   = features.f6 * sign > 0.3
        confirmed   = has_sweep or has_choch or has_fvg_q or has_willr
        if not confirmed:
            base *= 0.65
    return base


# ── Dynamic component weights based on recent accuracy ───────────────────────────────
def _dynamic_weights(history: list[dict]) -> tuple[float, float, float, float]:
    n = len(history)
    # Zero-weight RF/GBM until enough data to avoid overfitting (research: 50+ for RF, 80+ for GBM)
    if n < 50:
        return 0.75, 0.00, 0.00, 0.25
    if n < 80:
        return 0.55, 0.35, 0.00, 0.10
    recent = history[:20]  # history[0] is most recent (recent_outcomes reverses the list)
    wins   = sum(1 for t in recent if t.get("outcome") == "WIN")
    wr     = wins / len(recent)
    if wr >= 0.60:
        return 0.40, 0.28, 0.22, 0.10
    if wr <= 0.35:
        return 0.28, 0.22, 0.18, 0.32
    return KNN_WEIGHT, RF_WEIGHT, GBM_WEIGHT, NEWS_WEIGHT


# ── KNN + RF agreement gate (item 4) ─────────────────────────────────────────────
def _agreement_multiplier(knn_dir: str, rf_dir: str, gbm_dir: str) -> float:
    votes = [knn_dir, rf_dir, gbm_dir]
    bull_votes = votes.count("LONG")
    bear_votes = votes.count("SHORT")
    if bull_votes == 3 or bear_votes == 3:
        return 1.20
    if bull_votes == 2 or bear_votes == 2:
        return 1.00
    return 0.80


# ── Main signal generator ───────────────────────────────────────────────────────────────
def generate_signal(
    current_features: Features | None = None,
    news_agg: float = 0.0,
    news_velocity: dict | None = None,
    high_impact_event: dict | None = None,
    symbol: str = "XAUUSD",
    trigger: str = "",
    pool: str | None = None,
    macro_bias: dict | None = None,
) -> dict:
    from db import symbol_to_pool
    pool     = pool or symbol_to_pool(symbol)
    is_stock = not pool.startswith("XAUUSD")
    min_conf = MIN_CONFIDENCE_STOCKS if is_stock else MIN_CONFIDENCE

    model   = get_model(pool)
    rf      = get_rf(pool)
    gbm     = get_gbm(pool)
    history = recent_outcomes(pool, limit=300)
    now     = datetime.now(timezone.utc)

    # ── Weekend guard ──────────────────────────────────────────────────────────
    dow_mult = _day_of_week_multiplier(now)
    if dow_mult == 0.0:
        return _neutral_signal(symbol, now, model, rf, "Weekend — market closed", news_agg, pool, current_features, is_stock=is_stock)

    # ── KNN score ─────────────────────────────────────────────────────────────────
    if current_features and len(history) >= model.k:
        bull_score, bear_score = model.predict(current_features, history)
    else:
        bull_score = 0.5
        bear_score = 0.5

    # ── RF + GBM scores ─────────────────────────────────────────────────────────────
    feat_list      = current_features.as_list() if current_features else [0.0] * 25
    rf_win_prob    = rf.predict(feat_list)
    gbm_win_prob   = gbm.predict(feat_list)

    knn_directional = bull_score - bear_score
    rf_directional  = (rf_win_prob  - 0.5) * 2.0
    gbm_directional = (gbm_win_prob - 0.5) * 2.0

    knn_dir = "LONG" if knn_directional > 0 else "SHORT"
    rf_dir  = "LONG" if rf_directional  > 0 else "SHORT"
    gbm_dir = "LONG" if gbm_directional > 0 else "SHORT"

    # ── News velocity ───────────────────────────────────────────────────────────────
    velocity = news_velocity or {"multiplier": 1.0, "label": "NORMAL"}
    v_label  = velocity.get("label", "NORMAL")
    v_mult   = float(velocity.get("multiplier", 1.0))
    event    = high_impact_event or {"detected": False, "urgency": 0.0}

    if v_label == "CONFLICTED":
        # Option B: high-conviction ML signal overrides noisy news immediately.
        # ml_conf_proxy ≥ 0.65 OR unanimous model agreement → send instantly.
        # Only suppress low-conviction disagreeing signals — genuine noise.
        ml_strength    = (abs(knn_directional) + abs(rf_directional) + abs(gbm_directional)) / 3.0
        ml_conf_proxy  = 0.5 + ml_strength * 0.5
        high_conviction = ml_conf_proxy >= 0.65
        all_agree       = (knn_dir == rf_dir == gbm_dir)
        if not high_conviction and not all_agree:
            return _neutral_signal(symbol, now, model, rf, "News CONFLICTED — low conviction", news_agg, pool, current_features, is_stock=is_stock)

    if event.get("detected") and event.get("urgency", 0) >= 0.9:
        v_mult = min(v_mult * 1.5, 3.0)

    # ── Dynamic component weights ───────────────────────────────────────────────────
    w_knn_base, w_rf_base, w_gbm_base, w_news_base = _dynamic_weights(history)
    effective_news_weight = w_news_base * v_mult
    total_w = w_knn_base + w_rf_base + w_gbm_base + effective_news_weight
    w_knn  = w_knn_base           / total_w
    w_rf   = w_rf_base            / total_w
    w_gbm  = w_gbm_base           / total_w
    w_news = effective_news_weight / total_w

    # ── Macro bias — real yields, dollar, breakeven; equities also use nominal yield ──
    macro_val   = 0.0
    macro_label = "n/a"
    if isinstance(macro_bias, dict):
        macro_val   = float(macro_bias.get("bias", 0.0) or 0.0)
        macro_label = macro_bias.get("label", "NEUTRAL")
    w_macro = (0.15 if is_stock else 0.20) if macro_val != 0.0 else 0.0

    # ── Raw combined score ─────────────────────────────────────────────────────────────
    combined_score = (
        w_knn  * knn_directional +
        w_rf   * rf_directional  +
        w_gbm  * gbm_directional +
        w_news * news_agg        +
        w_macro * macro_val
    )
    direction_raw = "LONG" if combined_score > 0 else "SHORT"
    ml_score_out  = bull_score if direction_raw == "LONG" else bear_score

    regime = _detect_regime(current_features)
    regime_mult, regime_label = _regime_context(regime, direction_raw, pool)
    sess_mult, session_name = _session_multiplier(now, is_stock=is_stock)
    confluence_mult = _confluence_score(current_features, direction_raw, regime)
    agreement_mult = _agreement_multiplier(knn_dir, rf_dir, gbm_dir)
    trigger_mult = _trigger_quality_multiplier(history, trigger)
    rapid_mult   = _rapid_fire_penalty(history, direction_raw, trigger, now)
    cluster_mult = _clustering_multiplier(history, direction_raw)

    confidence = (
        abs(combined_score)
        * sess_mult
        * confluence_mult
        * dow_mult
        * regime_mult
        * agreement_mult
        * cluster_mult
        * trigger_mult
        * rapid_mult
    )

    confidence = min(1.0, confidence)  # multipliers can compound above 1.0 — clamp to valid range
    raw_confidence = confidence
    direction = direction_raw if confidence >= min_conf else "NEUTRAL"
    if direction == "NEUTRAL":
        confidence = 0.0

    tier = "HIGH" if confidence >= 0.75 else "MED" if confidence >= 0.60 else "LOW"

    news_desc = "bullish" if news_agg > 0.2 else "bearish" if news_agg < -0.2 else "neutral"
    model_votes = f"KNN:{knn_dir} RF:{rf_dir} GBM:{gbm_dir}"
    vwap_dist = current_features.f21 if current_features else 0.0
    vwap_ctx  = "STRETCHED" if abs(vwap_dist) > 0.6 else "NEAR"
    conf_str  = f"{raw_confidence:.3f}" if direction == "NEUTRAL" else f"{confidence:.3f}"
    reasoning = (
        f"{model_votes} | agree×{agreement_mult:.2f} | "
        f"regime:{regime}({regime_label})×{regime_mult:.2f} | "
        f"sess:{session_name}×{sess_mult:.2f} | "
        f"confluence×{confluence_mult:.2f} | "
        f"cluster×{cluster_mult:.2f} | "
        f"trigger:{trigger}×{trigger_mult:.2f} | "
        f"rapid×{rapid_mult:.2f} | "
        f"vwap:{vwap_ctx}({vwap_dist:+.2f}) | "
        f"news:{news_desc}({news_agg:+.3f}) | "
        + (f"macro:{macro_label}({macro_val:+.3f}) | " if w_macro > 0 else "")
        + f"combined:{combined_score:+.3f} → conf:{conf_str}"
    )
    if event.get("detected"):
        reasoning += f" ⚡ {event['event_type']}"

    expire_old_signals(symbol)
    row = {
        "symbol":         symbol,
        "pool":           pool,
        "direction":      direction,
        "confidence":     round(confidence, 4),
        "tier":           tier,
        "ml_score":       round(ml_score_out, 4),
        "rf_score":       round(rf_win_prob, 4),
        "gbm_score":      round(gbm_win_prob, 4),
        "news_score":     round(news_agg, 4),
        "macro_bias":     round(macro_val, 4),
        "macro_label":    macro_label,
        "combined_score": round(combined_score, 4),
        "session":        session_name,
        "regime":         regime,
        "regime_label":   regime_label,
        "reasoning":      reasoning,
        "status":         "ACTIVE",
        "expires_at":     (now + timedelta(minutes=30)).isoformat(),
    }
    saved = insert_signal(row)

    return {
        **row,
        "id":                saved.get("id"),
        "timestamp":         now.strftime("%Y-%m-%d %H:%M UTC"),
        "total_wins":        model._total_wins,
        "total_losses":      model._total_losses,
        "win_rate":          model.win_rate,
        "weights":           model.weights,
        "top_feature":       model.top_feature(),
        "rf_trained":        rf.is_trained,
        "gbm_trained":       gbm.is_trained,
        "news_velocity":     v_label,
        "velocity_mult":     round(v_mult, 2),
        "high_impact_event": event.get("event_type", ""),
    }


def _neutral_signal(symbol, now, model, rf, reason, news_agg, pool: str = "XAUUSD_2M",
                    features=None, is_stock: bool = False):
    _sess_mult, _session = _session_multiplier(now, is_stock=is_stock)
    _regime = _detect_regime(features)
    row = {
        "symbol":         symbol,
        "pool":           pool,
        "direction":      "NEUTRAL",
        "confidence":     0.0,
        "tier":           "LOW",
        "ml_score":       0.5,
        "rf_score":       0.5,
        "gbm_score":      0.5,
        "news_score":     round(news_agg, 4),
        "combined_score": 0.0,
        "session":        _session,
        "regime":         _regime,
        "regime_label":   _regime,
        "reasoning":      reason,
        "status":         "NEUTRAL",
        "expires_at":     (now + timedelta(minutes=30)).isoformat(),
    }
    insert_signal(row)
    gbm = get_gbm(pool)
    return {
        **row,
        "id":                None,
        "pool":              pool,
        "symbol":            symbol,
        "timestamp":         now.strftime("%Y-%m-%d %H:%M UTC"),
        "total_wins":        model._total_wins,
        "total_losses":      model._total_losses,
        "win_rate":          model.win_rate,
        "weights":           model.weights,
        "top_feature":       model.top_feature(),
        "rf_trained":        rf.is_trained,
        "gbm_trained":       gbm.is_trained,
        "news_velocity":     "NORMAL",
        "velocity_mult":     1.0,
        "high_impact_event": "",
    }
