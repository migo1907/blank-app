"""
Combines ML KNN score + Random Forest score + news sentiment + velocity into final XAU/USD signal.
Base weights: 40% KNN, 30% RF, 30% news — news weight scales with velocity multiplier.
"""
from datetime import datetime, timezone, timedelta
from ml_model import get_model, Features
from ml_ensemble import get_rf
from db import recent_outcomes, recent_news, insert_signal, expire_old_signals

KNN_WEIGHT     = 0.40
RF_WEIGHT      = 0.30
NEWS_WEIGHT    = 0.30
MIN_CONFIDENCE = 0.55   # below this → NEUTRAL


def generate_signal(
    current_features: Features | None = None,
    news_agg: float = 0.0,
    news_velocity: dict | None = None,
    high_impact_event: dict | None = None,
    symbol: str = "XAUUSD",
) -> dict:
    """
    Generate a trading signal using KNN + RF + news velocity.

    current_features:  latest bar's normalized features (None → fallback to win-rate)
    news_agg:          aggregate news sentiment in [-1, +1]
    news_velocity:     velocity dict from calculate_velocity()
    high_impact_event: event dict from detect_high_impact_event()
    """
    model   = get_model()
    rf      = get_rf()
    history = recent_outcomes(symbol, limit=300)

    # ── KNN score ─────────────────────────────────────────────────────────────
    if current_features and len(history) >= model.k:
        bull_score, bear_score = model.predict(current_features, history)
    else:
        wr         = model.win_rate
        bull_score = wr
        bear_score = 1.0 - wr

    # ── RF score ──────────────────────────────────────────────────────────────
    if current_features is not None:
        rf_win_prob = rf.predict(current_features.as_list())
    else:
        rf_win_prob = 0.5

    rf_directional  = (rf_win_prob - 0.5) * 2.0   # [0,1] → [-1,+1]
    knn_directional = bull_score - bear_score       # [-1,+1]

    # ── News velocity scaling ─────────────────────────────────────────────────
    velocity = news_velocity or {"multiplier": 1.0, "label": "NORMAL"}
    v_mult   = float(velocity.get("multiplier", 1.0))
    event    = high_impact_event or {"detected": False, "urgency": 0.0}

    # Boost multiplier further on confirmed high-impact events (NFP, FOMC, WAR)
    if event.get("detected") and event.get("urgency", 0) >= 0.9:
        v_mult = min(v_mult * 1.5, 3.0)

    effective_news_weight = NEWS_WEIGHT * v_mult

    # Renormalize so weights still sum to 1.0
    total_w = KNN_WEIGHT + RF_WEIGHT + effective_news_weight
    w_knn   = KNN_WEIGHT           / total_w
    w_rf    = RF_WEIGHT            / total_w
    w_news  = effective_news_weight / total_w

    # ── Combined score ────────────────────────────────────────────────────────
    combined_score = (w_knn  * knn_directional
                    + w_rf   * rf_directional
                    + w_news * news_agg)

    confidence = abs(combined_score)
    if combined_score > 0:
        direction    = "LONG"
        ml_score_out = bull_score
    else:
        direction    = "SHORT"
        ml_score_out = bear_score

    if confidence < MIN_CONFIDENCE:
        direction  = "NEUTRAL"
        confidence = 0.0

    # ── Build reasoning ───────────────────────────────────────────────────────
    news_desc     = "bullish" if news_agg >  0.2 else "bearish" if news_agg < -0.2 else "neutral"
    ml_desc       = "bullish" if knn_directional > 0 else "bearish"
    rf_desc       = "bullish" if rf_directional  > 0 else "bearish"
    velocity_desc = velocity.get("label", "NORMAL")
    event_desc    = f" ⚡ {event['event_type']} EVENT DETECTED!" if event.get("detected") else ""

    reasoning = (
        f"KNN is {ml_desc} ({knn_directional*100:+.0f}%), "
        f"RF is {rf_desc} ({rf_directional*100:+.0f}%), "
        f"news is {news_desc} ({news_agg:+.3f}). "
        f"Velocity: {velocity_desc} ×{v_mult:.1f} (news weight {w_news*100:.0f}%). "
        f"Combined: {combined_score:+.3f}.{event_desc}"
    )

    expire_old_signals(symbol)
    now = datetime.now(timezone.utc)
    row = {
        "symbol":         symbol,
        "direction":      direction,
        "confidence":     round(confidence, 4),
        "ml_score":       round(ml_score_out, 4),
        "rf_score":       round(rf_win_prob, 4),
        "news_score":     round(news_agg, 4),
        "combined_score": round(combined_score, 4),
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
        "news_velocity":     velocity_desc,
        "velocity_mult":     round(v_mult, 2),
        "high_impact_event": event.get("event_type", ""),
    }
