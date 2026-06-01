"""
Combines ML KNN score + Random Forest score + news sentiment into a final XAU/USD signal.
v3 weights: 40% KNN, 30% RF ensemble, 30% news sentiment.
"""
from datetime import datetime, timezone, timedelta
from ml_model import get_model, Features
from ml_ensemble import get_rf
from db import recent_outcomes, recent_news, insert_signal, expire_old_signals

KNN_WEIGHT  = 0.40
RF_WEIGHT   = 0.30
NEWS_WEIGHT = 0.30
MIN_CONFIDENCE = 0.55   # below this → NEUTRAL


def generate_signal(
    current_features: Features | None = None,
    news_agg: float = 0.0,
    symbol: str = "XAUUSD",
) -> dict:
    """
    Generate a trading signal using KNN + RF + news.

    current_features: latest bar's normalized features (can be None → fallback to win-rate)
    news_agg: aggregate news sentiment in [-1, +1]
    """
    model = get_model()
    rf    = get_rf()
    history = recent_outcomes(symbol, limit=300)

    # ── KNN score ──────────────────────────────────────────────────────────────
    if current_features and len(history) >= model.k:
        bull_score, bear_score = model.predict(current_features, history)
    else:
        wr = model.win_rate
        bull_score = wr
        bear_score = 1.0 - wr

    # ── RF score ───────────────────────────────────────────────────────────────
    if current_features is not None:
        rf_win_prob = rf.predict(current_features.as_list())
    else:
        rf_win_prob = 0.5

    # rf_directional: +1 = expects WIN (direction is from KNN context), map symmetrically
    # rf_directional in [-1, +1]: positive means RF leans toward win
    rf_directional = (rf_win_prob - 0.5) * 2.0    # scale: [0,1] → [-1,+1]

    # ── Combined score ─────────────────────────────────────────────────────────
    knn_directional  = bull_score - bear_score   # [-1, +1]
    combined_score   = (KNN_WEIGHT  * knn_directional
                        + RF_WEIGHT  * rf_directional
                        + NEWS_WEIGHT * news_agg)

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

    # ── Build reasoning ─────────────────────────────────────────────────────────
    news_desc = "bullish" if news_agg > 0.2 else "bearish" if news_agg < -0.2 else "neutral"
    ml_desc   = "bullish" if knn_directional > 0 else "bearish"
    rf_desc   = "bullish" if rf_directional > 0 else "bearish"
    reasoning = (
        f"KNN is {ml_desc} ({knn_directional*100:+.0f}%), "
        f"RF is {rf_desc} ({rf_directional*100:+.0f}%), "
        f"news is {news_desc} ({news_agg:+.3f}). "
        f"Combined: {combined_score:+.3f}."
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
        "id":           saved.get("id"),
        "timestamp":    now.strftime("%Y-%m-%d %H:%M UTC"),
        "total_wins":   model._total_wins,
        "total_losses": model._total_losses,
        "win_rate":     model.win_rate,
        "weights":      model.weights,
        "top_feature":  model.top_feature(),
        "rf_trained":   rf.is_trained,
    }
