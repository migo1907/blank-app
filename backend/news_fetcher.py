"""
Enhanced news fetcher — RSS feeds + NewsAPI + velocity engine + breaking news detection.
Sources: Reuters, FXStreet, Kitco, MarketWatch + NewsAPI
"""
import os
import json
import httpx
import anthropic
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

# ── RSS feeds (no API key required, real-time) ───────────────────────────────
RSS_FEEDS = [
    ("Kitco Gold News",   "https://www.kitco.com/rss/"),
    ("FXStreet Gold",     "https://www.fxstreet.com/rss/news"),
    ("MarketWatch Top",   "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("Investing.com Comm","https://www.investing.com/rss/news_25.rss"),   # Commodities
    ("Investing.com Forex","https://www.investing.com/rss/news_1.rss"),   # Forex
    ("BullionVault",      "https://www.bullionvault.com/gold-news/rss.do"),
    ("Mining.com",        "https://www.mining.com/feed/"),
]

# Gold/forex relevance filter
RELEVANCE_TERMS = [
    "gold", "xau", "silver", "precious metal", "bullion",
    "dollar", "usd", "dxy", "fed", "federal reserve", "rate", "inflation", "cpi", "fomc",
    "powell", "treasury", "yuan", "war", "conflict", "sanction", "china",
    "economy", "gdp", "nfp", "nonfarm", "payroll", "ism", "pmi", "ecb",
    "oil", "crude", "geopolit", "ukraine", "russia", "middle east",
    "safe haven", "risk off", "recession", "bond", "yield", "10-year",
]

# Terms that indicate crypto-only news — skip these even if other terms match
CRYPTO_NOISE_TERMS = [
    "bitcoin", "ethereum", "crypto", "blockchain", "stablecoin",
    "defi", "nft", "altcoin", "solana", "binance", "coinbase",
    "tokenis", "web3", "metaverse",
]

# NewsAPI search queries
NEWSAPI_QUERIES = [
    "gold XAU price",
    "Federal Reserve interest rates",
    "inflation CPI US dollar",
    "geopolitical risk war conflict",
    "safe haven demand gold",
    "FOMC Fed Powell",
    "China gold demand",
    "US Treasury yields bond",
]

# ── Breaking news event detector ─────────────────────────────────────────────
HIGH_IMPACT_EVENTS = {
    "NFP":             (["NFP", "NON-FARM", "NONFARM", "PAYROLL"], 1.0),
    "CPI":             (["CPI", "CONSUMER PRICE", "INFLATION DATA"], 0.9),
    "FOMC":            (["FOMC", "FED RATE DECISION", "FEDERAL RESERVE RATE", "POWELL SPEECH", "FED DECISION"], 1.0),
    "GDP":             (["GDP", "GROSS DOMESTIC PRODUCT"], 0.7),
    "WAR/CONFLICT":    (["WAR BROKE", "MILITARY STRIKE", "CONFLICT ESCALAT", "MISSILE ATTACK", "NUCLEAR", "INVASION"], 0.95),
    "SANCTIONS":       (["SANCTIONS", "EMBARGO", "TRADE WAR"], 0.8),
    "CENTRAL_BANK":    (["CENTRAL BANK GOLD", "CHINA GOLD BUY", "GOLD RESERVE", "GOLD PURCHASE"], 0.8),
    "FLASH_CRASH":     (["FLASH CRASH", "MARKET CRASH", "CIRCUIT BREAKER", "HALT TRADING"], 0.95),
}

XAU_SENTIMENT_PROMPT = """You are a specialist gold (XAU/USD) market analyst.

For each news headline below, score the IMMEDIATE impact on XAU/USD price direction:
  +1.0 = very bullish for gold (gold price likely rises strongly)
   0.0 = neutral / no impact
  -1.0 = very bearish for gold (gold price likely falls strongly)

Also classify impact magnitude: HIGH / MEDIUM / LOW
And extract up to 3 key driving keywords.

Headlines:
{headlines}

Return ONLY valid JSON array — one object per headline, same order:
[
  {{"score": 0.8, "impact": "HIGH", "keywords": ["Fed", "rate cut", "dovish"]}},
  ...
]"""


# ── RSS parser ────────────────────────────────────────────────────────────────

def _parse_rss(xml_text: str, source_name: str) -> list[dict]:
    articles = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        # RSS 2.0
        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el  = item.find("link")
            if title_el is not None and title_el.text:
                articles.append({
                    "title":  title_el.text.strip(),
                    "source": source_name,
                    "url":    link_el.text.strip() if link_el is not None and link_el.text else "",
                })
        # Atom fallback
        if not articles:
            for entry in root.findall(".//atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                link_el  = entry.find("atom:link",  ns)
                if title_el is not None and title_el.text:
                    articles.append({
                        "title":  title_el.text.strip(),
                        "source": source_name,
                        "url":    link_el.get("href", "") if link_el is not None else "",
                    })
    except Exception:
        pass
    return articles


def fetch_rss_headlines() -> list[dict]:
    """Fetch & filter gold-relevant headlines from all RSS feeds."""
    articles  = []
    seen      = set()

    with httpx.Client(timeout=10, follow_redirects=True) as client:
        for source_name, url in RSS_FEEDS:
            try:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MigoSniperBot/1.0)"})
                if resp.status_code == 200:
                    items = _parse_rss(resp.text, source_name)
                    for item in items[:15]:
                        title = item["title"]
                        key   = title[:60].lower()
                        if key in seen or len(title) < 15:
                            continue
                        lower = title.lower()
                        if any(t in lower for t in RELEVANCE_TERMS) and not any(t in lower for t in CRYPTO_NOISE_TERMS):
                            seen.add(key)
                            articles.append(item)
            except Exception as e:
                print(f"[rss] {source_name} failed: {e}")

    print(f"[rss] {len(articles)} relevant articles from RSS")
    return articles[:30]


def fetch_newsapi_headlines(max_articles: int = 20) -> list[dict]:
    """Fetch gold-relevant headlines from NewsAPI."""
    if not NEWSAPI_KEY:
        return []

    articles = []
    seen     = set()

    with httpx.Client(timeout=15) as client:
        for query in NEWSAPI_QUERIES[:4]:
            try:
                resp = client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q":        query,
                        "language": "en",
                        "sortBy":   "publishedAt",
                        "pageSize": 6,
                        "apiKey":   NEWSAPI_KEY,
                    },
                )
                resp.raise_for_status()
                for art in resp.json().get("articles", []):
                    title = art.get("title", "").strip()
                    key   = title[:60].lower()
                    if title and key not in seen and len(title) > 20:
                        seen.add(key)
                        articles.append({
                            "title":  title,
                            "source": art.get("source", {}).get("name", "unknown"),
                            "url":    art.get("url", ""),
                        })
            except Exception:
                pass

    return articles[:max_articles]


# ── Breaking news & event detection ──────────────────────────────────────────

def detect_high_impact_event(articles: list[dict]) -> dict:
    """
    Scan headlines for high-impact economic/geopolitical events.
    Returns {"detected": bool, "event_type": str, "urgency": float, "headlines": []}
    """
    all_text  = " ".join(a["title"] for a in articles).upper()
    triggered = []

    for event_type, (keywords, urgency) in HIGH_IMPACT_EVENTS.items():
        if any(kw in all_text for kw in keywords):
            matched_headlines = [
                a["title"] for a in articles
                if any(kw in a["title"].upper() for kw in keywords)
            ]
            triggered.append((event_type, urgency, matched_headlines))

    if triggered:
        triggered.sort(key=lambda x: x[1], reverse=True)
        best = triggered[0]
        return {
            "detected":   True,
            "event_type": best[0],
            "urgency":    best[1],
            "headlines":  best[2][:3],
            "all_events": [t[0] for t in triggered],
        }

    return {"detected": False, "event_type": "", "urgency": 0.0, "headlines": [], "all_events": []}


# ── News velocity engine ──────────────────────────────────────────────────────

def calculate_velocity(scored_items: list[dict], previous_agg: float) -> dict:
    """
    Measures news velocity — how fast and how consistently news is moving sentiment.

    Factors:
      - Volume:       count of HIGH/MEDIUM impact articles
      - Consistency:  fraction of articles pointing same direction
      - Acceleration: magnitude of sentiment shift vs last cycle

    Multiplier applied to NEWS_WEIGHT in signal engine:
      HIGH VELOCITY  → ×2.0  (breaking news, all same direction)
      ELEVATED       → ×1.5  (moderate flow, consistent)
      NORMAL         → ×1.0  (standard)
      CONFLICTED     → ×0.6  (mixed signals, reduce noise)
      SILENT         → ×0.3  (no relevant news)
    """
    if not scored_items:
        return {
            "multiplier":   0.3,
            "volume":       0,
            "consistency":  0.0,
            "acceleration": 0.0,
            "label":        "SILENT",
        }

    high_items = [s for s in scored_items if s.get("impact") == "HIGH"]
    med_items  = [s for s in scored_items if s.get("impact") == "MEDIUM"]
    scores     = [s["sentiment_score"] for s in scored_items]

    # Volume: weight HIGH more than MEDIUM
    volume = len(high_items) * 2 + len(med_items)

    # Consistency: how aligned are directional articles
    positives = sum(1 for s in scores if s >  0.15)
    negatives = sum(1 for s in scores if s < -0.15)
    directional = positives + negatives
    consistency = abs(positives - negatives) / directional if directional > 0 else 0.0

    # Acceleration: how much did sentiment shift since last cycle
    current_agg  = sum(scores) / len(scores)
    acceleration = abs(current_agg - previous_agg)

    # Dominant direction
    direction = "BULLISH" if positives > negatives else "BEARISH" if negatives > positives else "MIXED"

    # Multiplier logic
    if volume >= 4 and consistency >= 0.70 and acceleration >= 0.20:
        multiplier = 2.0
        label      = "HIGH VELOCITY"
    elif volume >= 3 and consistency >= 0.60:
        multiplier = 1.5
        label      = "ELEVATED"
    elif volume >= 1 and consistency >= 0.40:
        multiplier = 1.0
        label      = "NORMAL"
    elif consistency < 0.30 and volume >= 2:
        multiplier = 0.6
        label      = "CONFLICTED"
    else:
        multiplier = 0.8
        label      = "LOW"

    return {
        "multiplier":   multiplier,
        "volume":       volume,
        "consistency":  round(consistency, 3),
        "acceleration": round(acceleration, 3),
        "direction":    direction,
        "label":        label,
        "high_count":   len(high_items),
        "total_count":  len(scored_items),
    }


# ── Claude sentiment scoring ──────────────────────────────────────────────────

def score_headlines_with_claude(articles: list[dict]) -> list[dict]:
    """Use claude-haiku to score each headline's XAU/USD sentiment."""
    if not articles:
        return []

    client   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    numbered = "\n".join(f"{i+1}. {a['title']}" for i, a in enumerate(articles))

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": XAU_SENTIMENT_PROMPT.format(headlines=numbered)}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        scores = json.loads(raw)
    except Exception as e:
        print(f"[news] Claude scoring failed: {e}")
        scores = [{"score": 0.0, "impact": "LOW", "keywords": []}] * len(articles)

    results = []
    for i, art in enumerate(articles):
        s = scores[i] if i < len(scores) else {"score": 0.0, "impact": "LOW", "keywords": []}
        results.append({
            "source":          art["source"],
            "headline":        art["title"],
            "url":             art["url"],
            "sentiment_score": float(s.get("score", 0.0)),
            "impact":          s.get("impact", "LOW"),
            "keywords":        s.get("keywords", []),
        })
    return results


def aggregate_sentiment(scored_items: list[dict]) -> float:
    """Weighted average: HIGH=3×, MEDIUM=1.5×, LOW=1×. Returns [-1, +1]."""
    if not scored_items:
        return 0.0

    weight_map   = {"HIGH": 3.0, "MEDIUM": 1.5, "LOW": 1.0}
    total_weight = 0.0
    weighted_sum = 0.0

    for item in scored_items:
        w = weight_map.get(item.get("impact", "LOW"), 1.0)
        weighted_sum += item["sentiment_score"] * w
        total_weight += w

    return round(weighted_sum / total_weight, 4) if total_weight > 0 else 0.0


# ── Main cycle ────────────────────────────────────────────────────────────────

def run_news_cycle(previous_agg: float = 0.0) -> tuple[list[dict], float, dict, dict]:
    """
    Full enhanced cycle:
      1. Fetch RSS (real-time) + NewsAPI
      2. Deduplicate & merge
      3. Score with Claude Haiku
      4. Calculate velocity
      5. Detect high-impact events

    Returns: (scored_items, aggregate_score, velocity, event)
    """
    rss_articles = fetch_rss_headlines()
    api_articles = fetch_newsapi_headlines()

    # Merge & deduplicate
    seen    = set()
    unique  = []
    for a in rss_articles + api_articles:
        key = a["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)

    if not unique:
        print("[news] No articles fetched.")
        empty_velocity = {"multiplier": 0.3, "volume": 0, "consistency": 0.0,
                          "acceleration": 0.0, "label": "SILENT", "high_count": 0, "total_count": 0}
        return [], 0.0, empty_velocity, {"detected": False, "event_type": "", "urgency": 0.0}

    print(f"[news] Scoring {len(unique)} unique headlines with Claude…")
    scored   = score_headlines_with_claude(unique)
    agg      = aggregate_sentiment(scored)
    velocity = calculate_velocity(scored, previous_agg)
    event    = detect_high_impact_event(unique)

    print(
        f"[news] Sentiment: {agg:+.3f} | "
        f"Velocity: {velocity['label']} ×{velocity['multiplier']} | "
        f"Event: {event.get('event_type') or 'none'}"
    )
    return scored, agg, velocity, event
