"""
XAU/USD Signal Engine — Market-Aware Intelligence Layer

Scoring pipeline:
  1. KNN similarity (adaptive weights on 21 features)
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

# ── Base weights ──────────────────────────────────────────────────────────────
KNN_WEIGHT     = 0.35
RF_WEIGHT      = 0.25
GBM_WEIGHT     = 0.20
NEWS_WEIGHT    = 0.20
MIN_CONFIDENCE = 0.55


# ── Session intelligence (item 5) ─────────────────────────────────────────────
def _session_multiplier(now_utc: datetime) -> tuple[float, str]:
    h = now_utc.hour
    if 7 <= h < 10:   return 1.30, "LONDON"
    if 13 <= h < 16:  return 1.20, "NEW_YORK"
    if 12 <= h < 13:  return 1.25, "OVERLAP"
    if 16 <= h < 20:  return 1.00, "NY_LATE"
    if 0 <= h < 7:    return 0.75, "ASIAN"
    return 0.65, "OFF"


def _day_of_week_multiplier(now_utc: datetime) -> float:
    dow = now_utc.weekday()
    if dow == 0:        return 0.85
    if dow == 4:        return 0.85
    if dow in (5, 6):   return 0.0
    return 1.0


# ── Regime detection (item 1) ─────────────────────────────────────────────────
def _detect_regime(features: Features | None) -> str:
    """
    Detect market regime from the 21-feature vector.
    Uses f2 (ADX strength), f3 (ATR volatility), f16 (1H MTF trend).

    IMPORTANT: Counter-trend on 2min/5min is a valid PULLBACK in a trending market.
    This function provides CONTEXT, not a block on direction.
    """
    if features is None:
        return "UNKNOWN"

    adx = abs(features.f2)   # ADX: high = strong trend
    atr = abs(features.f3)   # ATR: high = volatile
    mtf = features.f16       # 1H trend: 1=bull, -1=bear, 0=neutral

    if atr > 0.70:
        return "VOLATILE"
    if adx > 0.40 and abs(mtf) >= 1.0:
        return "TRENDING_BULL" if mtf > 0 else "TRENDING_BEAR"
    if adx < 0.25:
        return "RANGING"
    return "NORMAL"


def _regime_context(regime: str, direction: str) -> tuple[float, str]:
    """
    Returns (multiplier, context_label).

    Trend-following trades get a boost.
    Counter-trend (pullback scalps on 2min/5min) are VALID and NOT blocked —
    they just don't get the trend-follow bonus.
    Ranging market slightly reduces confidence (choppy, no follow-through).
    """
    if regime == "TRENDING_BULL":
        if direction == "LONG":
            return 1.15, "TREND_FOLLOW"
        return 1.00, "PULLBACK_SHORT"     # valid 2min counter-trend scalp

    if regime == "TRENDING_BEAR":
        if direction == "SHORT":
            return 1.15, "TREND_FOLLOW"
        return 1.00, "PULLBACK_LONG"      # valid 2min counter-trend scalp

    if regime == "RANGING":
        return 0.88, "RANGING"            # choppy — reduce confidence

    if regime == "VOLATILE":
        return 0.92, "VOLATILE"           # news-driven — slight reduction

    return 1.00, "NORMAL"


# ── Trade clustering prevention (item 3) ──────────────────────────────────────
def _clustering_multiplier(history: list[dict], direction: str, lookback: int = 4) -> float:
    """
    Detects consecutive same-direction losses. Reduces confidence on a streak.
    Does NOT block — just reduces conviction to prevent overtrading one direction.

    lookback=4: if last 4 trades all same direction AND all losses → 0.75×
    """
    if len(history) < lookback:
        return 1.0

    recent = history[:lookback]
    same_dir_losses = sum(
        1 for t in recent
        if t.get("direction") == direction and t.get("outcome") == "LOSS"
    )
    if same_dir_losses >= lookback:
        return 0.75     # heavy streak penalty
    if same_dir_losses >= lookback - 1:
        return 0.88     # mild streak warning
    return 1.0


# ── Feature confluence ────────────────────────────────────────────────────────
def _confluence_score(features: Features | None, direction: str, regime: str) -> float:
    """
    Count how many of the 21 features agree with the predicted direction.
    Regime-aware: in pullback context, MTF alignment check is skipped
    (it will always disagree in a counter-trend scalp — that's expected).
    """
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
        features.f1  * sign > 0,   # RSI momentum
        features.f2  * sign > 0,   # ADX direction
        features.f4  * sign > 0,   # BB position
        features.f5  * sign > 0,   # MACD histogram
        features.f8  * sign > 0,   # vs EMA-200
        features.f9  * sign > 0,   # FVG
        features.f10 * sign > 0,   # Order Block
        features.f11 * sign > 0,   # BOS
        features.f13 * sign < 0,   # P/D discount zone (f13<0 = bullish for LONG)
        features.f21 * sign > 0,   # VWAP side
    ]

    # In pullback context skip MTF (it will be opposite — that's the point of a pullback)
    if not is_pullback:
        checks.append(features.f16 * sign > 0)   # MTF alignment

    # CHoCH and liquidity are key for pullback entries
    if is_pullback:
        checks.append(abs(features.f14) > 0.5)   # CHoCH present
        checks.append(abs(features.f12) > 0.5)   # Liquidity sweep present

    score = sum(checks) / len(checks)
    return 0.70 + score * 0.70


# ── Dynamic component weights based on recent accuracy ───────────────────────
def _dynamic_weights(history: list[dict]) -> tuple[float, float, float, float]:
    if len(history) < 20:
        return KNN_WEIGHT, RF_WEIGHT, GBM_WEIGHT, NEWS_WEIGHT

    recent = history[-20:]
    wins   = sum(1 for t in recent if t.get("outcome") == "WIN")
    wr     = wins / len(recent)

    if wr >= 0.60:
        return 0.40, 0.28, 0.22, 0.10
    if wr <= 0.35:
        return 0.28, 0.22, 0.18, 0.32
    return KNN_WEIGHT, RF_WEIGHT, GBM_WEIGHT, NEWS_WEIGHT


# ── KNN + RF agreement gate (item 4) ─────────────────────────────────────────
def _agreement_multiplier(knn_dir: str, rf_dir: str, gbm_dir: str) -> float:
    """
    All 3 models agree → strong boost.
    2 of 3 agree → normal.
    All disagree → reduce confidence (conflicted signal).
    """
    votes = [knn_dir, rf_dir, gbm_dir]
    bull_votes = votes.count("LONG")
    bear_votes = votes.count("SHORT")

    if bull_votes == 3 or bear_votes == 3:
        return 1.20    # unanimous agreement
    if bull_votes == 2 or bear_votes == 2:
        return 1.00    # majority agreement
    return 0.80        # split — all different (shouldn't happen with 3, but guard)


# ── Main signal generator ─────────────────────────────────────────────────────
def generate_signal(
    current_features: Features | None = None,
    news_agg: float = 0.0,
    news_velocity: dict | None = None,
    high_impact_event: dict | None = None,
    symbol: str = "XAUUSD",
) -> dict:

    model   = get_model()
    rf      = get_rf()
    gbm     = get_gbm()
    history = recent_outcomes(symbol, limit=300)
    now     = datetime.now(timezone.utc)

    # ── Weekend guard ────────────────────────────────────────────────────────
    dow_mult = _day_of_week_multiplier(now)
    if dow_mult == 0.0:
        return _neutral_signal(symbol, now, model, rf, "Weekend — market closed", news_agg)

    # ── KNN score ─────────────────────────────────────────────────────────────
    if current_features and len(history) >= model.k:
        bull_score, bear_score = model.predict(current_features, history)
    else:
        wr         = model.win_rate
        bull_score = wr
        bear_score = 1.0 - wr

    # ── RF + GBM scores ───────────────────────────────────────────────────────
    feat_list      = current_features.as_list() if current_features else [0.0] * 21
    rf_win_prob    = rf.predict(feat_list)
    gbm_win_prob   = gbm.predict(feat_list)

    knn_directional = bull_score - bear_score
    rf_directional  = (rf_win_prob  - 0.5) * 2.0
    gbm_directional = (gbm_win_prob - 0.5) * 2.0

    # Directional votes for agreement gate
    knn_dir = "LONG" if knn_directional > 0 else "SHORT"
    rf_dir  = "LONG" if rf_directional  > 0 else "SHORT"
    gbm_dir = "LONG" if gbm_directional > 0 else "SHORT"

    # ── News velocity ─────────────────────────────────────────────────────────
    velocity = news_velocity or {"multiplier": 1.0, "label": "NORMAL"}
    v_label  = velocity.get("label", "NORMAL")
    v_mult   = float(velocity.get("multiplier", 1.0))
    event    = high_impact_event or {"detected": False, "urgency": 0.0}

    if v_label == "CONFLICTED":
        return _neutral_signal(symbol, now, model, rf, "News velocity CONFLICTED", news_agg)

    if event.get("detected") and event.get("urgency", 0) >= 0.9:
        v_mult = min(v_mult * 1.5, 3.0)

    # ── Dynamic component weights ─────────────────────────────────────────────
    w_knn_base, w_rf_base, w_gbm_base, w_news_base = _dynamic_weights(history)
    effective_news_weight = w_news_base * v_mult
    total_w = w_knn_base + w_rf_base + w_gbm_base + effective_news_weight
    w_knn  = w_knn_base           / total_w
    w_rf   = w_rf_base            / total_w
    w_gbm  = w_gbm_base           / total_w
    w_news = effective_news_weight / total_w

    # ── Raw combined score ────────────────────────────────────────────────────
    combined_score = (
        w_knn  * knn_directional +
        w_rf   * rf_directional  +
        w_gbm  * gbm_directional +
        w_news * news_agg
    )
    direction_raw = "LONG" if combined_score > 0 else "SHORT"
    ml_score_out  = bull_score if direction_raw == "LONG" else bear_score

    # ── Regime detection (item 1) ─────────────────────────────────────────────
    regime = _detect_regime(current_features)
    regime_mult, regime_label = _regime_context(regime, direction_raw)

    # ── Session multiplier (item 5) ───────────────────────────────────────────
    sess_mult, session_name = _session_multiplier(now)

    # ── Feature confluence ────────────────────────────────────────────────────
    confluence_mult = _confluence_score(current_features, direction_raw, regime_label)

    # ── KNN+RF+GBM agreement gate (item 4) ───────────────────────────────────
    agreement_mult = _agreement_multiplier(knn_dir, rf_dir, gbm_dir)

    # ── Trade clustering prevention (item 3) ─────────────────────────────────
    cluster_mult = _clustering_multiplier(history, direction_raw)

    # ── Final confidence ──────────────────────────────────────────────────────
    confidence = (
        abs(combined_score)
        * sess_mult
        * confluence_mult
        * dow_mult
        * regime_mult
        * agreement_mult
        * cluster_mult
    )

    direction = direction_raw if confidence >= MIN_CONFIDENCE else "NEUTRAL"
    if direction == "NEUTRAL":
        confidence = 0.0

    tier = "HIGH" if confidence >= 0.75 else "MED" if confidence >= 0.60 else "LOW"

    # ── Reasoning ─────────────────────────────────────────────────────────────
    news_desc = "bullish" if news_agg > 0.2 else "bearish" if news_agg < -0.2 else "neutral"
    model_votes = f"KNN:{knn_dir} RF:{rf_dir} GBM:{gbm_dir}"
    reasoning = (
        f"{model_votes} | agree×{agreement_mult:.2f} | "
        f"regime:{regime}({regime_label})×{regime_mult:.2f} | "
        f"sess:{session_name}×{sess_mult:.2f} | "
        f"confluence×{confluence_mult:.2f} | "
        f"cluster×{cluster_mult:.2f} | "
        f"news:{news_desc}({news_agg:+.3f}) | "
        f"combined:{combined_score:+.3f} → conf:{confidence:.3f}"
    )
    if event.get("detected"):
        reasoning += f" ⚡ {event['event_type']}"

    expire_old_signals(symbol)
    row = {
        "symbol":         symbol,
        "direction":      direction,
        "confidence":     round(confidence, 4),
        "tier":           tier,
        "ml_score":       round(ml_score_out, 4),
        "rf_score":       round(rf_win_prob, 4),
        "gbm_score":      round(gbm_win_prob, 4),
        "news_score":     round(news_agg, 4),
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


def _neutral_signal(symbol, now, model, rf, reason, news_agg):
    row = {
        "symbol":         symbol,
        "direction":      "NEUTRAL",
        "confidence":     0.0,
        "tier":           "LOW",
        "ml_score":       0.5,
        "rf_score":       0.5,
        "gbm_score":      0.5,
        "news_score":     round(news_agg, 4),
        "combined_score": 0.0,
        "session":        "N/A",
        "regime":         "UNKNOWN",
        "regime_label":   "UNKNOWN",
        "reasoning":      reason,
        "status":         "NEUTRAL",
        "expires_at":     (now + timedelta(minutes=30)).isoformat(),
    }
    insert_signal(row)
    gbm = get_gbm()
    return {
        **row,
        "id":                None,
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
