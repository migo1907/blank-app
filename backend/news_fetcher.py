import os
import json
import httpx
import anthropic
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
QUERIES = [
    "gold XAU price",
    "Federal Reserve interest rates",
    "inflation CPI US dollar",
    "geopolitical risk war conflict",
    "safe haven demand gold",
    "FOMC Fed Powell",
    "China gold demand",
    "US Treasury yields bond",
]

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


def fetch_news_headlines(max_articles: int = 30) -> list[dict]:
    """Fetch recent gold-relevant headlines from NewsAPI."""
    if not NEWSAPI_KEY:
        return []

    articles: list[dict] = []
    seen_titles: set[str] = set()

    with httpx.Client(timeout=15) as client:
        for query in QUERIES[:4]:  # limit API calls on free tier
            try:
                resp = client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "language": "en",
                        "sortBy": "publishedAt",
                        "pageSize": 8,
                        "apiKey": NEWSAPI_KEY,
                    },
                )
                resp.raise_for_status()
                for art in resp.json().get("articles", []):
                    title = art.get("title", "").strip()
                    if title and title not in seen_titles and len(title) > 20:
                        seen_titles.add(title)
                        articles.append({
                            "title": title,
                            "source": art.get("source", {}).get("name", "unknown"),
                            "url": art.get("url", ""),
                        })
            except Exception:
                pass

    return articles[:max_articles]


def score_headlines_with_claude(articles: list[dict]) -> list[dict]:
    """Use claude-haiku to score each headline's XAU/USD sentiment."""
    if not articles:
        return []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    numbered = "\n".join(f"{i+1}. {a['title']}" for i, a in enumerate(articles))

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": XAU_SENTIMENT_PROMPT.format(headlines=numbered),
            }],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        scores: list[dict] = json.loads(raw)
    except Exception as e:
        print(f"[news] Claude scoring failed: {e}")
        scores = [{"score": 0.0, "impact": "LOW", "keywords": []}] * len(articles)

    results = []
    for i, art in enumerate(articles):
        s = scores[i] if i < len(scores) else {"score": 0.0, "impact": "LOW", "keywords": []}
        results.append({
            "source": art["source"],
            "headline": art["title"],
            "url": art["url"],
            "sentiment_score": float(s.get("score", 0.0)),
            "impact": s.get("impact", "LOW"),
            "keywords": s.get("keywords", []),
        })
    return results


def aggregate_sentiment(scored_items: list[dict]) -> float:
    """
    Weighted average sentiment.
    HIGH-impact articles count 3x, MEDIUM 1.5x, LOW 1x.
    Returns float in [-1, +1].
    """
    if not scored_items:
        return 0.0

    weight_map = {"HIGH": 3.0, "MEDIUM": 1.5, "LOW": 1.0}
    total_weight = 0.0
    weighted_sum = 0.0

    for item in scored_items:
        w = weight_map.get(item.get("impact", "LOW"), 1.0)
        weighted_sum += item["sentiment_score"] * w
        total_weight += w

    return round(weighted_sum / total_weight, 4) if total_weight > 0 else 0.0


def run_news_cycle() -> tuple[list[dict], float]:
    """Full cycle: fetch → score → return (items, aggregate_score)."""
    print("[news] Fetching headlines…")
    articles = fetch_news_headlines()
    if not articles:
        print("[news] No articles fetched.")
        return [], 0.0

    print(f"[news] Scoring {len(articles)} headlines with Claude…")
    scored = score_headlines_with_claude(articles)
    agg = aggregate_sentiment(scored)
    print(f"[news] Aggregate XAU sentiment: {agg:+.3f}")
    return scored, agg
