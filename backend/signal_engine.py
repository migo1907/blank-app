"""
Combines ML KNN score + news sentiment into a final XAU/USD signal.
Weights: 60% ML model, 40% news sentiment.
"""
from datetime import datetime, timezone, timedelta
from ml_model import get_model, Features
from db import recent_outcomes, recent_news, insert_signal, expire_old_signals

ML_WEIGHT   = 0.60
NEWS_WEIGHT = 0.40
MIN_CONFIDENCE = 0.55   # below this → NEUTRAL


def generate_signal(
    current_features: Features | None = None,
    news_agg: float = 0.0,
    symbol: str = "XAUUSD",
) -> dict:
    """
    Generate a trading signal.
    current_features: latest bar's normalized features (can be None → ML-only uses history stats)
    news_agg: aggregate news sentiment in [-1, +1]
    """
    model = get_model()
    history = recent_outcomes(symbol, limit=300)

    if current_features and len(history) >= model.k:
        bull_score, bear_score = model.predict(current_features, history)
    else:
        # Fallback: use win-rate as ML score
        wr = model.win_rate
        bull_score = wr
        bear_score = 1.0 - wr

    # news_agg is in [-1, +1] → map to bull probability [0, 1]
    news_bull = (news_agg + 1.0) / 2.0

    # Combined directional score (positive = bullish, negative = bearish)
    ml_directional   = bull_score - bear_score          # [-1, +1]
    combined_score   = ML_WEIGHT * ml_directional + NEWS_WEIGHT * news_agg

    # Determine direction and confidence
    confidence = abs(combined_score)
    if combined_score > 0:
        direction = "LONG"
        ml_score_out = bull_score
    else:
        direction = "SHORT"
        ml_score_out = bear_score

    if confidence < MIN_CONFIDENCE:
        direction = "NEUTRAL"
        confidence = 0.0

    # Build reasoning string
    news_desc = "bullish" if news_agg > 0.2 else "bearish" if news_agg < -0.2 else "neutral"
    ml_desc   = "bullish" if ml_directional > 0 else "bearish"
    reasoning = (
        f"ML model is {ml_desc} ({ml_directional*100:+.0f}%), "
        f"news sentiment is {news_desc} ({news_agg:+.3f}). "
        f"Combined: {combined_score:+.3f}."
    )

    expire_old_signals(symbol)
    now = datetime.now(timezone.utc)
    row = {
        "symbol": symbol,
        "direction": direction,
        "confidence": round(confidence, 4),
        "ml_score": round(ml_score_out, 4),
        "news_score": round(news_agg, 4),
        "combined_score": round(combined_score, 4),
        "reasoning": reasoning,
        "status": "ACTIVE",
        "expires_at": (now + timedelta(minutes=30)).isoformat(),
    }
    saved = insert_signal(row)

    return {
        **row,
        "id": saved.get("id"),
        "timestamp": now.strftime("%Y-%m-%d %H:%M UTC"),
        "total_wins": model._total_wins,
        "total_losses": model._total_losses,
        "win_rate": model.win_rate,
        "weights": model.weights,
        "top_feature": model.top_feature(),
    }
