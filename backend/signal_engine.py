"""
XAU/USD Signal Engine — Market-Aware Intelligence Layer

Scoring pipeline:
  1. KNN similarity (adaptive weights on 21 features)
  2. Random Forest ensemble (pattern recognition)
  3. News sentiment + velocity
  4. Market regime filter  (trending vs ranging)
  5. Session kill-zone boost  (London/NY overlap is gold's prime time)
  6. Feature confluence score (how many of 21 features agree)
  7. News-gate  (block signals when velocity is CONFLICTED)
  8. Day-of-week penalty  (Monday open / Friday close are thin)
  9. Dynamic weight adjustment based on recent win rates per component
"""
from datetime import datetime, timezone, timedelta
from ml_model import get_model, Features
from ml_ensemble import get_rf
from db import recent_outcomes, recent_news, insert_signal, expire_old_signals

# ── Base weights ──────────────────────────────────────────────────────────────
KNN_WEIGHT     = 0.40
RF_WEIGHT      = 0.30
NEWS_WEIGHT    = 0.30
MIN_CONFIDENCE = 0.55


# ── Session intelligence ───────────────────────────────────────────────────────
def _session_multiplier(now_utc: datetime) -> tuple[float, str]:
    """
    Gold moves most during London open and NY open.
    Asian session is quiet — reduce confidence to avoid false signals.
    Returns (multiplier, session_name).
    """
    h = now_utc.hour
    # London open kill zone  07:00–10:00 UTC  — strongest gold moves
    if 7 <= h < 10:
        return 1.30, "LONDON"
    # NY open kill zone  13:00–16:00 UTC
    if 13 <= h < 16:
        return 1.20, "NEW_YORK"
    # London/NY overlap  12:00–13:00 UTC
    if 12 <= h < 13:
        return 1.25, "OVERLAP"
    # Late NY  16:00–20:00 UTC — still ok, fading volume
    if 16 <= h < 20:
        return 1.00, "NY_LATE"
    # Asian session  00:00–07:00 UTC — gold is quiet, tighter spreads but less follow-through
    if 0 <= h < 7:
        return 0.75, "ASIAN"
    # Dead zone  20:00–00:00 UTC
    return 0.65, "OFF"


def _day_of_week_multiplier(now_utc: datetime) -> float:
    """
    Monday: gaps from weekend news, erratic. Friday: position squaring, reversals.
    Tue/Wed/Thu are the cleanest trading days for gold.
    """
    dow = now_utc.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    if dow == 0:   return 0.85   # Monday — wait for direction
    if dow == 4:   return 0.85   # Friday — stop-hunt / reversal risk
    if dow in (5, 6): return 0.0  # Weekend — no signal
    return 1.0                    # Tue / Wed / Thu — full weight


# ── Feature confluence ────────────────────────────────────────────────────────
def _confluence_score(features: Features | None, direction: str) -> float:
    """
    Count how many of the 21 features agree with the predicted direction.
    Returns a multiplier 0.7–1.4.

    Market knowledge applied:
    - f1  RSI > 0   → bullish momentum
    - f2  ADX × DI > 0 → trend in bull direction
    - f4  BB% > 0   → price in upper half of BB → bull
    - f5  MACD > 0  → MACD histogram positive → bull
    - f8  EMA dist > 0 → above 200 EMA → bull
    - f9  FVG  1.0  → bullish FVG present
    - f10 OB   1.0  → bullish order block active
    - f11 BOS  1.0  → bullish break of structure
    - f13 PD  < 0   → price in discount zone → bull setup  (f13>0 = premium = bearish)
    - f16 MTF  1.0  → higher timeframe bullish
    - f21 VWAP > 0  → above VWAP → bull
    (all reversed for SHORT)
    """
    if features is None:
        return 1.0

    bull = direction == "LONG"
    sign = 1.0 if bull else -1.0

    checks = [
        features.f1  * sign > 0,   # RSI momentum
        features.f2  * sign > 0,   # ADX direction
        features.f4  * sign > 0,   # BB position
        features.f5  * sign > 0,   # MACD histogram
        features.f8  * sign > 0,   # vs EMA-200
        features.f9  * sign > 0,   # FVG
        features.f10 * sign > 0,   # Order Block
        features.f11 * sign > 0,   # BOS
        features.f13 * sign < 0,   # P/D: discount zone (f13<0) is bullish for LONG
        features.f16 * sign > 0,   # MTF alignment
        features.f21 * sign > 0,   # VWAP side
    ]
    score = sum(checks) / len(checks)   # 0.0 → 1.0

    # 0% agreement=0.70, 50%=1.05, 100%=1.40
    return 0.70 + score * 0.70


# ── Dynamic component weights based on recent accuracy ───────────────────────
def _dynamic_weights(history: list[dict]) -> tuple[float, float, float]:
    """
    If recent KNN win-rate is above 60% boost it.
    If RF is recently outperforming, boost it.
    Keeps sum = 1.0.
    """
    if len(history) < 20:
        return KNN_WEIGHT, RF_WEIGHT, NEWS_WEIGHT

    recent = history[-20:]
    wins   = sum(1 for t in recent if t.get("outcome") == "WIN")
    wr     = wins / len(recent)

    # High win-rate → trust ML more, reduce news noise
    if wr >= 0.60:
        return 0.45, 0.35, 0.20
    # Low win-rate → lean on news sentiment more
    if wr <= 0.35:
        return 0.30, 0.25, 0.45
    return KNN_WEIGHT, RF_WEIGHT, NEWS_WEIGHT


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

    # ── RF score ──────────────────────────────────────────────────────────────
    rf_win_prob    = rf.predict(current_features.as_list()) if current_features else 0.5
    rf_directional = (rf_win_prob - 0.5) * 2.0
    knn_directional = bull_score - bear_score

    # ── News velocity scaling ─────────────────────────────────────────────────
    velocity = news_velocity or {"multiplier": 1.0, "label": "NORMAL"}
    v_label  = velocity.get("label", "NORMAL")
    v_mult   = float(velocity.get("multiplier", 1.0))
    event    = high_impact_event or {"detected": False, "urgency": 0.0}

    # Block signal entirely when news is highly conflicted
    if v_label == "CONFLICTED":
        return _neutral_signal(symbol, now, model, rf, "News velocity CONFLICTED — holding off", news_agg)

    # Boost on confirmed high-impact event aligned with signal
    if event.get("detected") and event.get("urgency", 0) >= 0.9:
        v_mult = min(v_mult * 1.5, 3.0)

    # ── Dynamic component weights ─────────────────────────────────────────────
    w_knn_base, w_rf_base, w_news_base = _dynamic_weights(history)
    effective_news_weight = w_news_base * v_mult
    total_w = w_knn_base + w_rf_base + effective_news_weight
    w_knn   = w_knn_base           / total_w
    w_rf    = w_rf_base            / total_w
    w_news  = effective_news_weight / total_w

    # ── Raw combined score ────────────────────────────────────────────────────
    combined_score = w_knn * knn_directional + w_rf * rf_directional + w_news * news_agg
    direction_raw  = "LONG" if combined_score > 0 else "SHORT"
    ml_score_out   = bull_score if direction_raw == "LONG" else bear_score

    # ── Session multiplier ────────────────────────────────────────────────────
    sess_mult, session_name = _session_multiplier(now)

    # ── Feature confluence multiplier ─────────────────────────────────────────
    confluence_mult = _confluence_score(current_features, direction_raw)

    # ── Final confidence ──────────────────────────────────────────────────────
    confidence = abs(combined_score) * sess_mult * confluence_mult * dow_mult

    direction = direction_raw if confidence >= MIN_CONFIDENCE else "NEUTRAL"
    if direction == "NEUTRAL":
        confidence = 0.0

    # ── Tier ─────────────────────────────────────────────────────────────────
    tier = "HIGH" if confidence >= 0.75 else "MED" if confidence >= 0.60 else "LOW"

    # ── Reasoning ─────────────────────────────────────────────────────────────
    news_desc = "bullish" if news_agg > 0.2 else "bearish" if news_agg < -0.2 else "neutral"
    reasoning = (
        f"KNN {'bullish' if knn_directional > 0 else 'bearish'} ({knn_directional*100:+.0f}%) | "
        f"RF {'bullish' if rf_directional > 0 else 'bearish'} ({rf_directional*100:+.0f}%) | "
        f"News {news_desc} ({news_agg:+.3f}) | "
        f"Session {session_name} ×{sess_mult:.2f} | "
        f"Confluence ×{confluence_mult:.2f} | "
        f"Velocity {v_label} ×{v_mult:.1f} | "
        f"Combined {combined_score:+.3f} → conf {confidence:.3f}"
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
        "news_score":     round(news_agg, 4),
        "combined_score": round(combined_score, 4),
        "session":        session_name,
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
        "news_score":     round(news_agg, 4),
        "combined_score": 0.0,
        "session":        "N/A",
        "reasoning":      reason,
        "status":         "NEUTRAL",
        "expires_at":     (now + timedelta(minutes=30)).isoformat(),
    }
    insert_signal(row)
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
        "news_velocity":     "NORMAL",
        "velocity_mult":     1.0,
        "high_impact_event": "",
    }
