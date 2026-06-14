"""
Swing addon — Fundamental data fetcher (all free sources).

Pulls the fundamental / sentiment picture for a single stock and reduces it to a
structured dict plus a normalized fundamental score ∈ [-1, +1] (positive =
bullish). Powers the swing screener and the narrative synthesis layer.

Sources (all free, no paid keys):
  • yfinance  — earnings calendar + surprise, analyst targets/consensus, insider
                transactions, institutional ownership, quarterly revenue/EPS
                growth, short interest.
  • Finnhub   — company-specific news + sentiment (FINNHUB_KEY in Railway).
                Graceful no-op if unset.
  • Finviz    — supplemental valuation ratios (P/E, forward P/E, EPS growth,
                debt/equity, dividend, analyst rating, insider/inst ownership
                cross-check). Scraped from finviz.com with a real browser UA.
                Augments / fills gaps in yfinance data.
  • SEC EDGAR — insider filing activity via EDGAR full-text search API (no auth
                required). Confirms yfinance insider signal with Form 4 counts.
  • CNBC RSS  — company-specific headline count (past 7d) via RSS.
  • MarketWatch RSS — same, as a second news-volume signal.
  • Benzinga RSS — financial news RSS for additional headline count.

Every fetch is best-effort: a failed source contributes 0 to the score rather
than blocking the others. A stock with no data at all returns a neutral dict.

Note on SeekingAlpha / TradingView: both block cloud IPs aggressively or have
no public REST API; not viable from Railway without a paid proxy/API key.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree

import httpx

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ── yfinance readers ───────────────────────────────────────────────────────────

def _earnings(tkr) -> dict:
    """Next earnings date + last surprise %. Drift-aware: imminent earnings flagged."""
    out = {"next_days": None, "last_surprise_pct": None, "imminent": False}
    try:
        cal = tkr.calendar
        ed = None
        if isinstance(cal, dict):
            ev = cal.get("Earnings Date")
            if isinstance(ev, (list, tuple)) and ev:
                ed = ev[0]
            elif ev:
                ed = ev
        if ed is not None:
            d = ed if isinstance(ed, datetime) else datetime.combine(ed, datetime.min.time())
            days = (d.date() - datetime.now(timezone.utc).date()).days
            out["next_days"] = days
            out["imminent"] = 0 <= days <= 7
    except Exception:
        pass
    try:
        hist = tkr.earnings_history
        if hist is not None and len(hist):
            row = hist.iloc[-1]
            sp = row.get("surprisePercent")
            if sp is not None:
                out["last_surprise_pct"] = round(float(sp) * 100, 2) if abs(sp) < 5 else round(float(sp), 2)
    except Exception:
        pass
    return out


def _analyst(tkr) -> dict:
    """Consensus + median price-target upside vs current price."""
    out = {"recommendation": None, "target_upside_pct": None, "num_analysts": None}
    try:
        info = tkr.info or {}
        out["recommendation"] = info.get("recommendationKey")
        out["num_analysts"] = info.get("numberOfAnalystOpinions")
        target = info.get("targetMedianPrice") or info.get("targetMeanPrice")
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if target and price:
            out["target_upside_pct"] = round((float(target) / float(price) - 1) * 100, 2)
    except Exception:
        pass
    return out


def _insider(tkr) -> dict:
    """Net insider buying signal over the recent window."""
    out = {"net_buy_signal": 0.0, "buy_count": 0, "sell_count": 0}
    try:
        tx = tkr.insider_transactions
        if tx is not None and len(tx):
            recent = tx.head(20)
            txt = recent.astype(str)
            col = None
            for c in recent.columns:
                if "Transaction" in str(c) or "Text" in str(c):
                    col = c
                    break
            if col is not None:
                vals = txt[col].str.lower()
                buys = int(vals.str.contains("buy|purchase|acqui").sum())
                sells = int(vals.str.contains("sale|sell|dispos").sum())
                out["buy_count"], out["sell_count"] = buys, sells
                tot = buys + sells
                if tot:
                    out["net_buy_signal"] = round((buys - sells) / tot, 3)
    except Exception:
        pass
    return out


def _institutional(tkr) -> dict:
    """Institutional ownership % held — high conviction proxy."""
    out = {"inst_held_pct": None}
    try:
        info = tkr.info or {}
        h = info.get("heldPercentInstitutions")
        if h is not None:
            out["inst_held_pct"] = round(float(h) * 100, 1)
    except Exception:
        pass
    return out


def _growth(tkr) -> dict:
    """Revenue + earnings YoY growth (acceleration is bullish)."""
    out = {"revenue_growth_pct": None, "earnings_growth_pct": None}
    try:
        info = tkr.info or {}
        rg = info.get("revenueGrowth")
        eg = info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")
        if rg is not None:
            out["revenue_growth_pct"] = round(float(rg) * 100, 1)
        if eg is not None:
            out["earnings_growth_pct"] = round(float(eg) * 100, 1)
    except Exception:
        pass
    return out


def _short_interest(tkr) -> dict:
    """Short % of float — high + catalyst = squeeze potential."""
    out = {"short_pct_float": None}
    try:
        info = tkr.info or {}
        s = info.get("shortPercentOfFloat")
        if s is not None:
            out["short_pct_float"] = round(float(s) * 100, 1)
    except Exception:
        pass
    return out


# ── Finnhub ───────────────────────────────────────────────────────────────────

def _news_sentiment(ticker: str) -> dict:
    """Finnhub company news count + headline sample for the last 7 days."""
    out = {"news_7d": 0, "headlines": [], "sentiment": 0.0}
    if not FINNHUB_KEY:
        return out
    try:
        today = datetime.now(timezone.utc).date()
        frm = (today - timedelta(days=7)).isoformat()
        url = "https://finnhub.io/api/v1/company-news"
        params = {"symbol": ticker, "from": frm, "to": today.isoformat(), "token": FINNHUB_KEY}
        with httpx.Client(timeout=12) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        if isinstance(data, list):
            out["news_7d"] = len(data)
            out["headlines"] = [a.get("headline", "")[:120] for a in data[:5] if a.get("headline")]
    except Exception as e:
        print(f"[fundamental] Finnhub news {ticker} failed: {e}")
    return out


# ── Finviz ────────────────────────────────────────────────────────────────────

def _parse_finviz_pct(val: str) -> float | None:
    """Parse a Finviz percentage string like '12.34%' → 12.34."""
    if not val or val == "-":
        return None
    try:
        return float(val.replace("%", "").replace(",", "").strip())
    except Exception:
        return None


def _parse_finviz_num(val: str) -> float | None:
    """Parse a Finviz numeric string (handles B/M suffixes)."""
    if not val or val == "-":
        return None
    try:
        v = val.replace(",", "").strip()
        if v.endswith("B"):
            return float(v[:-1]) * 1e9
        if v.endswith("M"):
            return float(v[:-1]) * 1e6
        return float(v)
    except Exception:
        return None


def _finviz(ticker: str) -> dict:
    """
    Scrape Finviz stock page for supplemental fundamentals.
    Returns a best-effort dict; all fields None on failure.
    """
    out = {
        "pe_ratio": None,
        "forward_pe": None,
        "eps_growth_next_year_pct": None,
        "debt_equity": None,
        "dividend_pct": None,
        "insider_own_pct": None,
        "inst_own_pct": None,
        "short_float_pct": None,
        "analyst_rating": None,
        "price_target": None,
        "52w_high_pct": None,
        "52w_low_pct": None,
        "perf_week_pct": None,
        "perf_month_pct": None,
        "perf_ytd_pct": None,
    }
    try:
        url = f"https://finviz.com/quote.ashx?t={ticker}&p=d"
        with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            r = client.get(url)
            if r.status_code != 200:
                return out
            html = r.text

        # Finviz stores data in a <table class="snapshot-table2"> or similar;
        # parse key/value pairs from the HTML table cells.
        rows = re.findall(r'<td[^>]*class="[^"]*snapshot-td2[^"]*"[^>]*>(.*?)</td>', html, re.DOTALL)
        labels = re.findall(r'<td[^>]*class="[^"]*snapshot-td2-cp[^"]*"[^>]*>(.*?)</td>', html, re.DOTALL)

        def _strip(s: str) -> str:
            return re.sub(r"<[^>]+>", "", s).strip()

        pairs: dict[str, str] = {}
        for i, lab in enumerate(labels):
            key = _strip(lab)
            if i < len(rows):
                pairs[key] = _strip(rows[i])

        # Alternative: zip adjacent cells (label, value) from snapshot table
        if not pairs:
            cells = re.findall(r'<td[^>]*>(.*?)</td>', html, re.DOTALL)
            stripped = [_strip(c) for c in cells]
            for i in range(0, len(stripped) - 1, 2):
                if stripped[i] and stripped[i + 1]:
                    pairs[stripped[i]] = stripped[i + 1]

        _map = {
            "P/E":            ("pe_ratio",                _parse_finviz_num),
            "Forward P/E":    ("forward_pe",              _parse_finviz_num),
            "EPS next Y":     ("eps_growth_next_year_pct",_parse_finviz_pct),
            "Debt/Eq":        ("debt_equity",             _parse_finviz_num),
            "Dividend %":     ("dividend_pct",            _parse_finviz_pct),
            "Insider Own":    ("insider_own_pct",         _parse_finviz_pct),
            "Inst Own":       ("inst_own_pct",            _parse_finviz_pct),
            "Short Float":    ("short_float_pct",         _parse_finviz_pct),
            "Recom":          ("analyst_rating",          lambda v: v),
            "Target Price":   ("price_target",            _parse_finviz_num),
            "52W High":       ("52w_high_pct",            _parse_finviz_pct),
            "52W Low":        ("52w_low_pct",             _parse_finviz_pct),
            "Perf Week":      ("perf_week_pct",           _parse_finviz_pct),
            "Perf Month":     ("perf_month_pct",          _parse_finviz_pct),
            "Perf YTD":       ("perf_ytd_pct",            _parse_finviz_pct),
        }
        for label, (field, fn) in _map.items():
            if label in pairs:
                val = fn(pairs[label])
                if val is not None:
                    out[field] = val

    except Exception as e:
        print(f"[fundamental] Finviz {ticker} failed: {e}")
    return out


# ── SEC EDGAR ─────────────────────────────────────────────────────────────────

def _edgar_insider(ticker: str) -> dict:
    """
    Count Form 4 filings (insider buy/sell) via EDGAR full-text search.
    Free, no auth required. Uses SEC EDGAR company search to get CIK first.
    """
    out = {"form4_buys": 0, "form4_sells": 0, "form4_total": 0}
    try:
        # Step 1: resolve ticker → CIK
        url = f"https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt={_edgar_since()}&enddt={datetime.now(timezone.utc).date().isoformat()}&forms=4"
        with httpx.Client(timeout=15, headers={"User-Agent": "SwingScreener/1.0 research@example.com"}) as client:
            r = client.get(url)
            if r.status_code != 200:
                return out
            data = r.json()

        hits = data.get("hits", {}).get("hits", [])
        buys = sells = 0
        for h in hits[:30]:
            src = h.get("_source", {})
            # transaction_type: A = acquisition (buy), D = disposal (sell)
            tx_type = str(src.get("transaction_type", "")).upper()
            if "A" in tx_type:
                buys += 1
            elif "D" in tx_type:
                sells += 1
        out["form4_buys"] = buys
        out["form4_sells"] = sells
        out["form4_total"] = buys + sells
    except Exception as e:
        print(f"[fundamental] EDGAR insider {ticker} failed: {e}")
    return out


def _edgar_since() -> str:
    """90-day lookback date string."""
    return (datetime.now(timezone.utc).date() - timedelta(days=90)).isoformat()


# ── News RSS (CNBC, MarketWatch, Benzinga) ────────────────────────────────────

def _rss_headline_count(ticker: str, feed_url: str, timeout: int = 10) -> int:
    """
    Count headlines in an RSS feed that mention the ticker (last 7 days).
    Returns 0 on any failure.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    count = 0
    try:
        with httpx.Client(timeout=timeout, headers=_HEADERS, follow_redirects=True) as client:
            r = client.get(feed_url)
            if r.status_code != 200:
                return 0
        root = ElementTree.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)
        ticker_up = ticker.upper()
        for item in items:
            # date check
            pub = item.findtext("pubDate") or item.findtext("atom:published", namespaces=ns) or ""
            try:
                from email.utils import parsedate_to_datetime
                pub_dt = parsedate_to_datetime(pub).astimezone(timezone.utc) if pub else None
            except Exception:
                pub_dt = None
            if pub_dt and pub_dt < cutoff:
                continue
            title = item.findtext("title") or ""
            desc = item.findtext("description") or ""
            if ticker_up in (title + desc).upper():
                count += 1
    except Exception:
        pass
    return count


def _multi_rss_news(ticker: str) -> dict:
    """
    Count ticker mentions across CNBC, MarketWatch, and Benzinga RSS feeds.
    Returns total headline count for the last 7 days.
    """
    feeds = [
        f"https://www.cnbc.com/id/100003114/device/rss/rss.html",
        f"https://feeds.marketwatch.com/marketwatch/topstories/",
        f"https://www.benzinga.com/feed",
    ]
    total = 0
    for feed in feeds:
        try:
            total += _rss_headline_count(ticker, feed, timeout=8)
        except Exception:
            pass
    return {"rss_news_7d": total}


# ── Score ─────────────────────────────────────────────────────────────────────

def _score(f: dict) -> float:
    """Reduce the fundamental dict to a single bullish/bearish score ∈ [-1, +1]."""
    parts: list[float] = []

    # Analyst consensus + price target (yfinance primary, Finviz supplement)
    a = f["analyst"]
    if a["target_upside_pct"] is not None:
        parts.append(_clamp(a["target_upside_pct"] / 25.0))
    rec = (a["recommendation"] or "").lower()
    if rec in ("strong_buy", "buy"):
        parts.append(0.6 if rec == "strong_buy" else 0.4)
    elif rec in ("sell", "strong_sell", "underperform"):
        parts.append(-0.5)

    # Finviz analyst rating as secondary signal (numeric 1-5, lower = more bullish)
    fv = f.get("finviz", {})
    fv_rec = fv.get("analyst_rating")
    if fv_rec and a["recommendation"] is None:
        try:
            rv = float(fv_rec)
            # Finviz: 1.0=Strong Buy … 5.0=Strong Sell → map to [-1,+1]
            parts.append(_clamp((3.0 - rv) / 2.0))
        except Exception:
            pass

    # Earnings surprise
    e = f["earnings"]
    if e["last_surprise_pct"] is not None:
        parts.append(_clamp(e["last_surprise_pct"] / 20.0))

    # Insider signal — yfinance + EDGAR confirmation
    parts.append(0.5 * f["insider"]["net_buy_signal"])
    ed = f.get("edgar_insider", {})
    tot = ed.get("form4_total", 0)
    if tot:
        net = (ed.get("form4_buys", 0) - ed.get("form4_sells", 0)) / tot
        parts.append(0.3 * net)  # lighter weight — cross-confirms yfinance

    # Growth
    g = f["growth"]
    if g["revenue_growth_pct"] is not None:
        parts.append(_clamp(g["revenue_growth_pct"] / 30.0))
    if g["earnings_growth_pct"] is not None:
        parts.append(_clamp(g["earnings_growth_pct"] / 40.0))

    # Finviz EPS growth next year
    eg_next = fv.get("eps_growth_next_year_pct")
    if eg_next is not None and g["earnings_growth_pct"] is None:
        parts.append(_clamp(eg_next / 40.0))

    # Finviz 52-week position (% from 52w low — closer to low → more room)
    low_pct = fv.get("52w_low_pct")
    high_pct = fv.get("52w_high_pct")
    if low_pct is not None and high_pct is not None:
        try:
            # low_pct: e.g. +45.2 means 45.2% above 52w low
            # Range position: 0 = at low, 1 = at high
            span = abs(low_pct) + abs(high_pct) if high_pct < 0 else abs(low_pct)
            if span > 0:
                pos = abs(low_pct) / span
                # Slight pullback preference: 40-65% of range is sweet spot
                if 0.4 <= pos <= 0.65:
                    parts.append(0.15)
        except Exception:
            pass

    if not parts:
        return 0.0
    return round(_clamp(sum(parts) / len(parts)), 3)


# ── Main entry ────────────────────────────────────────────────────────────────

def fetch_fundamentals(ticker: str) -> dict:
    """Full fundamental snapshot + score for one stock. Best-effort, never raises."""
    f = {
        "ticker": ticker,
        "earnings": {"next_days": None, "last_surprise_pct": None, "imminent": False},
        "analyst": {"recommendation": None, "target_upside_pct": None, "num_analysts": None},
        "insider": {"net_buy_signal": 0.0, "buy_count": 0, "sell_count": 0},
        "institutional": {"inst_held_pct": None},
        "growth": {"revenue_growth_pct": None, "earnings_growth_pct": None},
        "short": {"short_pct_float": None},
        "news": {"news_7d": 0, "headlines": [], "sentiment": 0.0},
        "finviz": {},
        "edgar_insider": {"form4_buys": 0, "form4_sells": 0, "form4_total": 0},
        "rss_news": {"rss_news_7d": 0},
        "score": 0.0,
        "updated_at": _now(),
    }
    try:
        import yfinance as yf
        tkr = yf.Ticker(ticker)
        f["earnings"] = _earnings(tkr)
        f["analyst"] = _analyst(tkr)
        f["insider"] = _insider(tkr)
        f["institutional"] = _institutional(tkr)
        f["growth"] = _growth(tkr)
        f["short"] = _short_interest(tkr)
    except Exception as e:
        print(f"[fundamental] yfinance {ticker} failed: {e}")

    f["news"] = _news_sentiment(ticker)

    # Supplemental sources — best-effort, non-blocking
    try:
        f["finviz"] = _finviz(ticker)
    except Exception as e:
        print(f"[fundamental] finviz {ticker} error: {e}")

    try:
        f["edgar_insider"] = _edgar_insider(ticker)
    except Exception as e:
        print(f"[fundamental] edgar {ticker} error: {e}")

    try:
        f["rss_news"] = _multi_rss_news(ticker)
    except Exception as e:
        print(f"[fundamental] rss news {ticker} error: {e}")

    # Merge Finviz short float if yfinance missed it
    fv = f.get("finviz", {})
    if f["short"]["short_pct_float"] is None and fv.get("short_float_pct") is not None:
        f["short"]["short_pct_float"] = fv["short_float_pct"]

    # Merge Finviz institutional ownership
    if f["institutional"]["inst_held_pct"] is None and fv.get("inst_own_pct") is not None:
        f["institutional"]["inst_held_pct"] = fv["inst_own_pct"]

    # Merge Finviz price target → compute upside if yfinance missed it
    if f["analyst"]["target_upside_pct"] is None and fv.get("price_target"):
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info or {}
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price:
                f["analyst"]["target_upside_pct"] = round(
                    (fv["price_target"] / float(price) - 1) * 100, 2
                )
        except Exception:
            pass

    f["score"] = _score(f)
    return f
