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
MIN_CONFIDENCE = 0.55   # XAUUSD threshold

# Stocks need higher bar — longer TF signals should be higher quality
MIN_CONFIDENCE_STOCKS = 0.58


# ── Session intelligence (item 5) ─────────────────────────────────────────────
def _session_multiplier(now_utc: datetime, is_stock: bool = False) -> tuple[float, str]:
    h = now_utc.hour
    if is_stock:
        # Stocks: NYSE hours only — pre-market/after-hours are noise
        if 13 <= h < 16:  return 1.25, "NYSE_OPEN"    # first 2.5hrs — most volume
        if 16 <= h < 19:  return 1.10, "NYSE_AFTERNOON"
        if 12 <= h < 13:  return 0.90, "PRE_MARKET"
        return 0.60, "CLOSED"                          # outside market hours
    # Gold — 24hr market
    # DATA FINDING: London session (7-12 UTC) = 0% WR over 5 trades — hard reduce
    # Asian (0-7 UTC) = 33% WR — best session in data
    if 7 <= h < 12:   return 0.60, "LONDON"      # 0% WR in live data — penalise hard
    if 12 <= h < 13:  return 1.25, "OVERLAP"
    if 13 <= h < 16:  return 1.20, "NEW_YORK"
    if 16 <= h < 20:  return 1.00, "NY_LATE"
    if 0 <= h < 7:    return 1.10, "ASIAN"        # 33% WR — boosted from 0.75
    return 0.70, "OFF"


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
        # Soft reduction only — don't hard-block (breakouts start from ranging markets)
        return 0.82, "RANGING"

    if regime == "VOLATILE":
        return 0.92, "VOLATILE"           # news-driven — slight reduction

    return 1.00, "NORMAL"


# ── Trigger quality scoring ───────────────────────────────────────────────────
def _trigger_quality_multiplier(history: list[dict], trigger: str) -> float:
    """
    Track win rate per trigger method and boost/penalise accordingly.
    Different triggers (BOS, CHoCH, FVG, OB, RSI, Liq) have different edge.
    Each trigger earns its own reputation from live outcomes.

    Same trigger + same direction within 30s = true duplicate → penalise.
    Different trigger or different direction = independent signal → let it through.
    """
    if not history or not trigger:
        return 1.0

    # Score this trigger's historical win rate
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
        # Boost high-performing triggers, penalise low-performing ones
        if wr >= 0.55:   return 1.20   # proven trigger — strong boost
        if wr >= 0.45:   return 1.08   # decent trigger — mild boost
        if wr <= 0.25:   return 0.75   # poor trigger — penalise
        if wr <= 0.35:   return 0.88   # below-average — mild reduction

    return 1.0   # not enough data yet — neutral


def _rapid_fire_penalty(history: list[dict], direction: str, trigger: str, now: datetime) -> float:
    """
    Only penalise TRUE duplicates: same trigger + same direction within 30 seconds.
    Different trigger or different direction = independent signal, let through normally.
    This allows the ML to learn which trigger wins when two conflict simultaneously.
    """
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

        # True duplicate: same trigger + same direction within 30s
        if (gap_seconds < 30
                and last_dir == direction
                and last_trigger.upper() == trigger.upper()):
            return 0.15   # exact duplicate — near-block

    except Exception:
        pass
    return 1.0


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
    base = 0.70 + score * 0.70

    # ── DATA-DRIVEN FILTERS (from 68-trade live analysis) ────────────────────
    # Finding 1: f21_vwap < -0.5 (well below VWAP) = 17.5% WR vs 28%+ above
    # LONG signals taken far below VWAP in a bearish trend = consistent losers
    if bull and features.f21 < -0.5:
        base *= 0.78   # well below VWAP on LONG — mean-reversion risk

    # Finding 2: f5_macd = +1 (bullish MACD) in bearish MTF = 16% WR
    # Bullish MACD in bearish trend = lagging indicator chasing price
    if bull and features.f5 > 0.5 and features.f16 < 0:
        base *= 0.82   # MACD bullish but 1H bearish — lagging, fade

    # Finding 3: f5_macd = -1 (bearish MACD) = 26% WR — best filter with n=23
    # Bearish MACD aligns with bearish MTF = trend-confirmed signal
    if not bull and features.f5 < -0.5:
        base *= 1.12   # MACD bearish + SHORT = trend-confirmed, boost

    # Finding 4: CHoCH present = 37.5% WR (best single factor, n=4)
    # Small sample but consistent — CHoCH = institutional reversal evidence
    if abs(features.f14) > 0.5:
        base *= 1.10   # CHoCH present — reversal confirmed by structure

    # ── VWAP Stretch mean-reversion boost ────────────────────────────────────
    # When price is stretched far from VWAP in the signal direction,
    # the mean-reversion magnet INCREASES probability of the trade working.
    # f21 = VWAP distance (positive = above VWAP, negative = below VWAP)
    # For LONG: price below VWAP (f21 < 0) = stretched down = reversion UP = boost
    # For SHORT: price above VWAP (f21 > 0) = stretched up = reversion DOWN = boost
    vwap_stretch = abs(features.f21)
    if vwap_stretch > 0.6 and features.f21 * sign < 0:
        # Price is stretched AGAINST direction of signal = mean reversion setup
        if vwap_stretch > 0.9:
            base *= 1.18   # extreme stretch — strongest magnet pull
        else:
            base *= 1.10   # moderate stretch — good reversion setup
    elif features.f21 * sign > 0 and vwap_stretch > 0.5:
        # Price already past VWAP on signal side = trend continuation, slight boost
        base *= 1.05

    # ── HV AVWAP magnet boost (f24 repurposed context) ───────────────────────
    # When a quality FVG exists post-sweep (f24 > 0.5), it often coincides with
    # HV AVWAP acting as a magnet — this is the highest-quality reversion setup
    if abs(features.f24) > 0.5 and features.f21 * sign < 0:
        base *= 1.08   # FVG quality + VWAP stretch = institutional magnet confirmed

    # ── Pullback confirmation gate ────────────────────────────────────────────
    # Counter-trend scalps (2min/5min pullbacks) are VALID but need reversal
    # evidence. Without sweep OR CHoCH OR quality FVG, it's a random counter-trend
    # entry with no institutional confirmation — reduce confidence.
    # A single confirmed reversal signal is enough to trade normally.
    if is_pullback:
        has_sweep   = abs(features.f12) > 0.3           # liquidity swept
        has_choch   = abs(features.f14) > 0.3           # change of character
        has_fvg_q   = abs(features.f24) > 0.5           # quality FVG post-sweep
        has_willr   = features.f6 * sign > 0.3          # Williams %R oversold/overbought
        confirmed   = has_sweep or has_choch or has_fvg_q or has_willr
        if not confirmed:
            base *= 0.65   # no reversal evidence — significantly reduce

    return base


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
    trigger: str = "",
) -> dict:
    from db import symbol_to_pool
    pool     = symbol_to_pool(symbol)
    is_stock = pool != "XAUUSD"
    min_conf = MIN_CONFIDENCE_STOCKS if is_stock else MIN_CONFIDENCE

    model   = get_model(pool)
    rf      = get_rf()
    gbm     = get_gbm()
    history = recent_outcomes(pool, limit=300)
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
    feat_list      = current_features.as_list() if current_features else [0.0] * 25
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
    sess_mult, session_name = _session_multiplier(now, is_stock=is_stock)

    # ── Feature confluence ────────────────────────────────────────────────────
    confluence_mult = _confluence_score(current_features, direction_raw, regime_label)

    # ── KNN+RF+GBM agreement gate (item 4) ───────────────────────────────────
    agreement_mult = _agreement_multiplier(knn_dir, rf_dir, gbm_dir)

    # ── Trigger quality + true-duplicate dedup ───────────────────────────────
    trigger_mult = _trigger_quality_multiplier(history, trigger)
    rapid_mult   = _rapid_fire_penalty(history, direction_raw, trigger, now)

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
        * trigger_mult
        * rapid_mult
    )

    raw_confidence = confidence  # preserve before zeroing for reasoning
    direction = direction_raw if confidence >= min_conf else "NEUTRAL"
    if direction == "NEUTRAL":
        confidence = 0.0

    tier = "HIGH" if confidence >= 0.75 else "MED" if confidence >= 0.60 else "LOW"

    # ── Reasoning ─────────────────────────────────────────────────────────────
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
        f"combined:{combined_score:+.3f} → conf:{conf_str}"
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
