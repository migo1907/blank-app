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

NEWSAPI_KEY        = os.environ.get("NEWSAPI_KEY", "")
FJ_SESSION_COOKIE  = os.environ.get("FJ_SESSION_COOKIE", "")
FJ_ASPNET_SESSION  = os.environ.get("FJ_ASPNET_SESSION", "")
FJ_UID             = os.environ.get("FJ_UID", "")
FJ_UNAME           = os.environ.get("FJ_UNAME", "")
FJ_EMAIL           = os.environ.get("FJ_EMAIL", "")
FJ_BREAKING_URL    = "https://www.financialjuice.com/widgets/initial-data.ashx"
FJ_PASSWORD        = os.environ.get("FJ_PASSWORD", "")
FJ_SESSION_PATH    = "data/fj_session.json"   # GitHub data branch — persists across restarts

# In-memory cookie cache — loaded from GitHub on first use, refreshed after each success
_fj_cookie_cache: dict = {}
FJ_RSS_URL         = "https://www.financialjuice.com/feed.ashx?xy=rss"

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

# Breaking news RSS feeds — fetched separately for instant Telegram alerts
BREAKING_NEWS_FEEDS = [
    ("ForexLive",   "https://www.forexlive.com/feed/"),
    ("FXStreet",    "https://www.fxstreet.com/rss/news"),
]

# FinancialJuice high-impact keywords — these map to "red" breaking news
FINANCIALJUICE_HIGH_IMPACT = [
    "fed", "fomc", "powell", "rate decision", "rate cut", "rate hike",
    "nfp", "non-farm", "payroll", "cpi", "inflation", "gdp",
    "war", "attack", "invasion", "strike", "nuclear", "sanction",
    "gold", "xau", "dollar", "dxy", "treasury", "yield",
    "recession", "crisis", "crash", "default", "bank",
    "china", "russia", "ukraine", "middle east", "iran", "opec",
    "emergency", "breaking", "flash", "urgent", "halt",
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

    # Pull FinancialJuice into main feed if cookie is set
    fj_rss = _fetch_fj_rss()

    with httpx.Client(timeout=10, follow_redirects=True) as client:
        # Inject ALL FJ items — no relevance filter, FJ is already curated market news
        for item in fj_rss[:60]:
            title = item["title"]
            key   = title[:60].lower()
            lower = title.lower()
            if key not in seen and len(title) >= 10:
                if not any(t in lower for t in CRYPTO_NOISE_TERMS):
                    seen.add(key)
                    articles.append(item)

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
    return articles[:80]


def _fetch_fj_rss() -> list[dict]:
    """Fetch FinancialJuice RSS using session cookie. Returns [] on failure."""
    cookie_str = _fj_cookie_str()
    if not cookie_str:
        return []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Cookie":     cookie_str,
            "Referer":    "https://www.financialjuice.com/",
            "Accept":     "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            resp = client.get(FJ_RSS_URL, headers=headers)
            print(f"[breaking] FinancialJuice HTTP {resp.status_code} (content len={len(resp.text)})")
            if resp.status_code == 200 and "<item>" in resp.text:
                items = _parse_rss(resp.text, "FinancialJuice")
                for item in items:
                    if item["title"].startswith("FinancialJuice: "):
                        item["title"] = item["title"][len("FinancialJuice: "):]
                print(f"[breaking] FinancialJuice: {len(items)} items parsed")
                return items
            else:
                print(f"[breaking] FinancialJuice bad response — falling back to ForexLive")
    except Exception as e:
        print(f"[breaking] FinancialJuice fetch error: {e}")
    return []


def _fj_cookie_str() -> str:
    """
    Build cookie string — prefer GitHub-persisted session (latest working),
    fall back to Railway env vars (original).
    GitHub version is updated after every successful call so it stays fresh.
    """
    global _fj_cookie_cache
    # Load from GitHub on first call (in-memory cache after that)
    if not _fj_cookie_cache:
        try:
            from db import _get_file
            saved, _ = _get_file(FJ_SESSION_PATH)
            if saved and saved.get("fj_session_cookie"):
                _fj_cookie_cache = saved
                print("[fj] Loaded session cookie from GitHub persistence.")
        except Exception:
            pass

    auth    = _fj_cookie_cache.get("fj_session_cookie")   or FJ_SESSION_COOKIE
    aspnet  = _fj_cookie_cache.get("fj_aspnet_session")   or FJ_ASPNET_SESSION
    uid     = _fj_cookie_cache.get("fj_uid")              or FJ_UID
    uname   = _fj_cookie_cache.get("fj_uname")            or FJ_UNAME
    email   = _fj_cookie_cache.get("fj_email")            or FJ_EMAIL

    if not auth:
        return ""
    parts = [f".ASPXAUTH={auth}"]
    if aspnet: parts.append(f"ASP.NET_SessionId={aspnet}")
    if uid:    parts.append(f"FJ-UID={uid}")
    if uname:  parts.append(f"FJ-UName={uname}")
    if email:  parts.append(f"FJ-Email={email}")
    parts.append("FJ-Pop=show; FJSignupAllowClose=0")
    return "; ".join(parts)


def _fj_save_session(resp_headers: dict) -> None:
    """
    Extract fresh cookies from a successful response and save to GitHub.
    Called after every 200 from initial-data.ashx to keep the persisted
    cookie as fresh as possible — survives Railway restarts.
    """
    global _fj_cookie_cache
    try:
        set_cookie = resp_headers.get("set-cookie", "")
        new_auth   = None
        new_aspnet = None
        for part in set_cookie.split(";"):
            p = part.strip()
            if p.startswith(".ASPXAUTH="):
                new_auth = p.split("=", 1)[1]
            elif p.startswith("ASP.NET_SessionId="):
                new_aspnet = p.split("=", 1)[1]

        new_auth_val   = new_auth   or _fj_cookie_cache.get("fj_session_cookie") or FJ_SESSION_COOKIE
        new_aspnet_val = new_aspnet or _fj_cookie_cache.get("fj_aspnet_session") or FJ_ASPNET_SESSION
        old_auth_val   = _fj_cookie_cache.get("fj_session_cookie", "")
        old_aspnet_val = _fj_cookie_cache.get("fj_aspnet_session", "")
        # Only write to GitHub if cookie actually changed — avoids ~720 commits/day
        if new_auth_val == old_auth_val and new_aspnet_val == old_aspnet_val:
            return
        payload = {
            "fj_session_cookie": new_auth_val,
            "fj_aspnet_session": new_aspnet_val,
            "fj_uid":   FJ_UID,
            "fj_uname": FJ_UNAME,
            "fj_email": FJ_EMAIL,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        from db import _get_file, _put_file
        _, sha = _get_file(FJ_SESSION_PATH)
        _put_file(FJ_SESSION_PATH, payload, sha, "chore: refresh FJ session cookie")
        _fj_cookie_cache = payload
    except Exception as e:
        print(f"[fj] Session save error: {e}")


def _fj_auto_login() -> bool:
    """
    Log in to FinancialJuice using FJ_EMAIL + FJ_PASSWORD env vars.
    Extracts the fresh .ASPXAUTH + ASP.NET_SessionId cookies and saves them
    to GitHub data branch so all future calls use the new session.
    Returns True on success, False on failure.
    """
    global _fj_cookie_cache
    email    = FJ_EMAIL
    password = FJ_PASSWORD
    if not email or not password:
        print("[fj] Auto-login skipped — FJ_EMAIL or FJ_PASSWORD not set.")
        return False

    print(f"[fj] Auto-login: attempting login for {email}…")
    login_url = "https://www.financialjuice.com/account/login"

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            # Step 1: GET login page to obtain ASP.NET form tokens
            r0 = client.get(
                login_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            )
            # Extract __RequestVerificationToken if present
            rvt = ""
            try:
                import re
                match = re.search(r'__RequestVerificationToken[^>]+value="([^"]+)"', r0.text)
                if match:
                    rvt = match.group(1)
            except Exception:
                pass

            # Step 2: POST credentials
            form_data = {
                "Email":    email,
                "Password": password,
                "RememberMe": "true",
            }
            if rvt:
                form_data["__RequestVerificationToken"] = rvt

            r1 = client.post(
                login_url,
                data=form_data,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer":    login_url,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

        # Check cookies from the client jar (follow_redirects means final cookies are in jar)
        cookies = dict(client.cookies)
        auth_cookie   = cookies.get(".ASPXAUTH", "")
        aspnet_cookie = cookies.get("ASP.NET_SessionId", "")

        if not auth_cookie:
            print(f"[fj] Auto-login failed — no .ASPXAUTH cookie received (HTTP {r1.status_code}).")
            return False

        payload = {
            "fj_session_cookie": auth_cookie,
            "fj_aspnet_session": aspnet_cookie,
            "fj_uid":   FJ_UID,
            "fj_uname": FJ_UNAME,
            "fj_email": email,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "login_method": "auto",
        }
        from db import _get_file, _put_file
        _, sha = _get_file(FJ_SESSION_PATH)
        _put_file(FJ_SESSION_PATH, payload, sha, "chore: auto-login refresh FJ session cookie")
        _fj_cookie_cache = payload
        print(f"[fj] Auto-login successful — new session saved to GitHub.")
        return True

    except Exception as e:
        print(f"[fj] Auto-login error: {e}")
        return False


def _parse_fj_breaking(raw: str) -> str:
    """
    FJ API returns breaking field as plain text OR JSON array like [{"title":"..."}].
    Always returns a clean plain-text headline string.
    """
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith("["):
        try:
            items = json.loads(raw)
            if isinstance(items, list) and items:
                return items[0].get("title", raw).strip()
        except Exception:
            pass
    return raw


def fetch_fj_breaking_direct() -> tuple[str, bool]:
    """
    Poll FJ /widgets/initial-data.ashx for the red breaking news banner field.

    Returns (headline, is_401):
      headline — breaking news text, or "" if none active
      is_401   — True if session expired AND auto-login also failed

    On 401/403: attempts auto-login first, retries once. Only returns is_401=True
    if auto-login fails (caller then sends personal alert).
    On success: saves fresh cookie to GitHub for restart resilience.
    """
    cookie_str = _fj_cookie_str()
    if not cookie_str and not (FJ_EMAIL and FJ_PASSWORD):
        return "", False

    def _do_request(cookie: str) -> tuple[int, dict]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
            "Cookie":     cookie,
            "Referer":    "https://www.financialjuice.com/home",
            "Accept":     "application/json, text/plain, */*",
        }
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            resp = client.get(FJ_BREAKING_URL, headers=headers)
        return resp.status_code, resp

    try:
        if not cookie_str:
            # No cookie at all — try auto-login first
            if not _fj_auto_login():
                return "", False
            cookie_str = _fj_cookie_str()

        status, resp = _do_request(cookie_str)

        if status == 200:
            _fj_save_session(dict(resp.headers))
            try:
                payload = resp.json()
            except Exception:
                # HTML page returned with 200 — session cookie expired but server didn't 401
                print("[breaking] FJ returned non-JSON 200 — treating as session expiry, attempting re-login…")
                if _fj_auto_login():
                    new_cookie = _fj_cookie_str()
                    status2, resp2 = _do_request(new_cookie)
                    if status2 == 200:
                        try:
                            payload = resp2.json()
                        except Exception:
                            return "", True
                        _fj_save_session(dict(resp2.headers))
                        breaking = _parse_fj_breaking(payload.get("breaking") or "")
                        return breaking, False
                return "", True
            breaking = _parse_fj_breaking(payload.get("breaking") or "")
            if breaking:
                print(f"[breaking] FJ red item: {breaking[:80]}")
            return breaking, False

        if status in (401, 403):
            print(f"[breaking] FJ session expired (HTTP {status}) — attempting auto-login…")
            if _fj_auto_login():
                # Retry once with fresh cookie
                new_cookie = _fj_cookie_str()
                status2, resp2 = _do_request(new_cookie)
                if status2 == 200:
                    _fj_save_session(dict(resp2.headers))
                    breaking = _parse_fj_breaking(resp2.json().get("breaking") or "")
                    if breaking:
                        print(f"[breaking] FJ red item (after re-login): {breaking[:80]}")
                    return breaking, False
            # Auto-login failed — signal caller to send personal alert
            print("[fj] Auto-login failed — manual cookie update required.")
            return "", True

        print(f"[breaking] initial-data.ashx HTTP {status}")
        return "", False

    except Exception as e:
        print(f"[breaking] fetch_fj_breaking_direct error: {e}")
        return "", False


def fetch_breaking_news() -> list[dict]:
    """
    Fetch breaking news — FinancialJuice RSS (if cookie set) else ForexLive + FXStreet.
    Returns only high-impact items for instant Telegram alerts.
    """
    breaking = []
    seen = set()

    # Try FinancialJuice first (best quality)
    fj_items = _fetch_fj_rss()
    source_items = fj_items if fj_items else []

    # Fall back to ForexLive/FXStreet if FJ unavailable
    if not fj_items:
        try:
            with httpx.Client(timeout=8, follow_redirects=True) as client:
                for source_name, url in BREAKING_NEWS_FEEDS:
                    try:
                        resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; MigoSniperBot/1.0)"})
                        if resp.status_code != 200:
                            print(f"[breaking] {source_name} HTTP {resp.status_code}")
                            continue
                        source_items.extend(_parse_rss(resp.text, source_name))
                    except Exception as e:
                        print(f"[breaking] {source_name} failed: {e}")
        except Exception as e:
            print(f"[breaking] fallback fetch error: {e}")

    for item in source_items[:50]:
        title = item["title"]
        key   = title[:60].lower()
        if key in seen:
            continue
        lower = title.lower()
        if any(kw in lower for kw in FINANCIALJUICE_HIGH_IMPACT):
            if not any(t in lower for t in CRYPTO_NOISE_TERMS):
                seen.add(key)
                breaking.append({**item, "fj_breaking": True})

    print(f"[breaking] {len(breaking)} high-impact items")
    return breaking[:10]


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
      HIGH VELOCITY  -> x2.0  (breaking news, all same direction)
      ELEVATED       -> x1.5  (moderate flow, consistent)
      NORMAL         -> x1.0  (standard)
      CONFLICTED     -> x0.6  (mixed signals, reduce noise)
      SILENT         -> x0.3  (no relevant news)
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

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[news] ANTHROPIC_API_KEY not set — skipping Claude sentiment scoring")
        return [{"score": 0.0, "impact": "LOW", "keywords": []}] * len(articles)
    client = anthropic.Anthropic(api_key=api_key)
    numbered = "\n".join(f"{i+1}. {a['title']}" for i, a in enumerate(articles))

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": XAU_SENTIMENT_PROMPT.format(headlines=numbered)}],
        )
        if not response.content or not response.content[0].text:
            raise ValueError("Claude returned empty response content")
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) >= 2 else raw
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
    """Weighted average: HIGH=3x, MEDIUM=1.5x, LOW=1x. Returns [-1, +1]."""
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

def run_news_cycle(previous_agg: float = 0.0) -> tuple[list[dict], float, dict, dict, list[dict]]:
    """
    Full enhanced cycle:
      1. Fetch FinancialJuice breaking news (red highlights) — highest priority
      2. Fetch RSS feeds + NewsAPI
      3. Deduplicate & merge
      4. Score with Claude Haiku
      5. Calculate velocity
      6. Detect high-impact events

    Returns: (scored_items, aggregate_score, velocity, event, fj_breaking_items)
    fj_breaking_items — FinancialJuice high-impact items for instant Telegram alert
    """
    fj_breaking  = fetch_breaking_news()
    rss_articles = fetch_rss_headlines()
    api_articles = fetch_newsapi_headlines()

    # Merge & deduplicate — FJ first so it takes priority
    seen    = set()
    unique  = []
    for a in fj_breaking + rss_articles + api_articles:
        key = a["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)

    if not unique:
        print("[news] No articles fetched.")
        empty_velocity = {"multiplier": 0.3, "volume": 0, "consistency": 0.0,
                          "acceleration": 0.0, "label": "SILENT", "high_count": 0, "total_count": 0}
        return [], 0.0, empty_velocity, {"detected": False, "event_type": "", "urgency": 0.0}, []

    print(f"[news] Scoring {len(unique)} unique headlines with Claude…")
    scored   = score_headlines_with_claude(unique)
    agg      = aggregate_sentiment(scored)
    velocity = calculate_velocity(scored, previous_agg)
    event    = detect_high_impact_event(unique)

    print(
        f"[news] Sentiment: {agg:+.3f} | "
        f"Velocity: {velocity['label']} x{velocity['multiplier']} | "
        f"Event: {event.get('event_type') or 'none'} | "
        f"FJ Breaking: {len(fj_breaking)}"
    )
    return scored, agg, velocity, event, fj_breaking
