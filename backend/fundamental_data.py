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


_CIK_MAP: dict[str, str] = {}  # ticker → CIK string, lazy-loaded from SEC


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def cik_for(ticker: str) -> str | None:
    """Resolve a ticker → SEC CIK (cached). Used by EDGAR insider + 8-K readers."""
    global _CIK_MAP
    if not _CIK_MAP:
        try:
            with httpx.Client(timeout=15, headers={"User-Agent": "SwingScreener research contact@example.com"}) as c:
                r = c.get("https://www.sec.gov/files/company_tickers.json")
                r.raise_for_status()
                for row in (r.json() or {}).values():
                    t = str(row.get("ticker", "")).upper()
                    if t:
                        _CIK_MAP[t] = str(row.get("cik_str", "")).zfill(10)
        except Exception as e:
            print(f"[fundamental] CIK map load failed: {e}")
            return None
    return _CIK_MAP.get(ticker.upper())


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


# ── Business-model archetype classification ───────────────────────────────────

# Metric set + weights per archetype. Every metric is normalized to [-1,+1] by
# _metrics(); the fundamental score is the weight-average over the metrics that
# are actually computable for that name. Different businesses are judged on the
# numbers that actually drive them (banks on ROE/book value, growth-tech on
# Rule of 40, REITs on yield/coverage — never on metrics that misfire for them).
ARCHETYPE_WEIGHTS = {
    "growth_tech":   {"rev_growth": .25, "rule40": .20, "gross_margin": .15,
                      "fcf_yield": .10, "peg": .10, "pt_upside": .10, "eps_growth": .10},
    "mega_tech":     {"roe": .20, "fcf_yield": .20, "op_margin": .15, "eps_growth": .15,
                      "rev_growth": .10, "pt_upside": .10, "peg": .10},
    "bank":          {"roe": .30, "roa": .20, "pb": .25, "div_yield": .15, "pt_upside": .10},
    "nonbank_fin":   {"roe": .25, "pb": .20, "profit_margin": .15, "peg": .15,
                      "div_yield": .10, "pt_upside": .15},
    "energy":        {"fcf_yield": .25, "div_yield": .20, "debt_equity": .15,
                      "roa": .15, "pt_upside": .10, "piotroski": .15},
    "staples":       {"div_yield": .25, "payout": .20, "gross_margin": .15,
                      "roe": .15, "debt_equity": .10, "rev_growth": .15},
    "discretionary": {"rev_growth": .25, "eps_growth": .20, "op_margin": .20,
                      "pt_upside": .15, "piotroski": .20},
    "healthcare":    {"fcf_yield": .15, "profit_margin": .15, "peg": .15, "eps_growth": .15,
                      "rev_growth": .15, "pt_upside": .15, "div_yield": .10},
    "industrial":    {"roe": .20, "op_margin": .20, "piotroski": .20, "rev_growth": .15,
                      "debt_equity": .10, "pt_upside": .15},
    "reit":          {"div_yield": .35, "payout": .20, "debt_equity": .20,
                      "pb": .15, "pt_upside": .10},
    "utility":       {"div_yield": .30, "payout": .25, "debt_equity": .20,
                      "roe": .15, "pt_upside": .10},
    "materials":     {"fcf_yield": .20, "roa": .20, "op_margin": .15, "debt_equity": .15,
                      "rev_growth": .15, "pt_upside": .15},
    "default":       {"pt_upside": .20, "rev_growth": .20, "eps_growth": .20,
                      "roe": .20, "fcf_yield": .20},
}

# Archetypes where Altman Z / Piotroski / leverage tests misfire (balance sheet
# IS the business) — never apply distress-leverage logic to these.
_NO_ZSCORE = {"bank", "nonbank_fin", "reit", "utility"}


def archetype_of(info: dict) -> str:
    """Map a yfinance info dict → business-model archetype (sector + industry refined)."""
    sector = (info.get("sector") or "").strip()
    industry = (info.get("industry") or "").lower()
    pm = info.get("profitMargins") or 0.0
    mcap = info.get("marketCap") or 0.0

    if sector == "Technology":
        return "mega_tech" if (pm > 0.15 and mcap > 5e11) else "growth_tech"
    if sector == "Financial Services":
        if "bank" in industry:
            return "bank"
        if "credit services" in industry:   # Visa / Mastercard / PayPal behave like quality-tech
            return "mega_tech"
        return "nonbank_fin"
    if sector == "Real Estate":
        return "reit" if "reit" in industry else "nonbank_fin"
    if sector == "Consumer Defensive":
        return "staples"
    if sector == "Consumer Cyclical":
        return "discretionary"
    if sector == "Healthcare":
        return "healthcare"
    if sector == "Industrials":
        return "industrial"
    if sector == "Energy":
        return "energy"
    if sector == "Utilities":
        return "utility"
    if sector == "Basic Materials":
        return "materials"
    if sector == "Communication Services":
        if "telecom" in industry:
            return "utility"          # telcos ≈ bond-proxy / leverage-sensitive
        return "growth_tech"          # media / internet content → growth rules
    return "default"


# ── Statement-based advanced composite scores ─────────────────────────────────

def _safe(df, *keys, col=0):
    """Pull a row value from a yfinance statement DataFrame by any matching label."""
    try:
        if df is None or not len(df.columns):
            return None
        for k in keys:
            for idx in df.index:
                if str(idx).strip().lower() == k.lower():
                    v = df.iloc[:, col][idx]
                    return float(v) if v == v else None
    except Exception:
        pass
    return None


def _statements(tkr) -> dict:
    """Pull the three core statements once; downstream advanced scores read from these."""
    out = {"income": None, "balance": None, "cash": None}
    try:
        out["income"] = tkr.income_stmt
        out["balance"] = tkr.balance_sheet
        out["cash"] = tkr.cashflow
    except Exception as e:
        print(f"[fundamental] statements failed: {e}")
    return out


def piotroski_f(st: dict, info: dict) -> int | None:
    """Piotroski F-Score (0-9). Higher = stronger fundamental quality. Needs 2 periods."""
    inc, bal, cf = st.get("income"), st.get("balance"), st.get("cash")
    if inc is None or bal is None or len(getattr(inc, "columns", [])) < 2:
        return None
    try:
        score = 0
        ni0 = _safe(inc, "Net Income", "Net Income Common Stockholders", col=0)
        ni1 = _safe(inc, "Net Income", "Net Income Common Stockholders", col=1)
        ta0 = _safe(bal, "Total Assets", col=0)
        ta1 = _safe(bal, "Total Assets", col=1)
        ocf = _safe(cf, "Operating Cash Flow", "Total Cash From Operating Activities", col=0)
        rev0 = _safe(inc, "Total Revenue", col=0)
        rev1 = _safe(inc, "Total Revenue", col=1)
        gp0 = _safe(inc, "Gross Profit", col=0)
        gp1 = _safe(inc, "Gross Profit", col=1)
        ltd0 = _safe(bal, "Long Term Debt", col=0) or 0.0
        ltd1 = _safe(bal, "Long Term Debt", col=1) or 0.0
        ca0 = _safe(bal, "Current Assets", "Total Current Assets", col=0)
        cl0 = _safe(bal, "Current Liabilities", "Total Current Liabilities", col=0)
        ca1 = _safe(bal, "Current Assets", "Total Current Assets", col=1)
        cl1 = _safe(bal, "Current Liabilities", "Total Current Liabilities", col=1)
        sh0 = info.get("sharesOutstanding")
        sh1 = _safe(bal, "Share Issued", "Ordinary Shares Number", col=1)

        if ni0 and ni0 > 0: score += 1
        if ocf and ocf > 0: score += 1
        if ni0 and ni1 and ta0 and ta1 and (ni0 / ta0) > (ni1 / ta1): score += 1
        if ocf and ni0 and ocf > ni0: score += 1
        if ta0 and ta1 and (ltd0 / ta0) < (ltd1 / ta1): score += 1
        if ca0 and cl0 and ca1 and cl1 and (ca0 / cl0) > (ca1 / cl1): score += 1
        if sh0 and sh1 and sh0 <= sh1 * 1.01: score += 1
        if gp0 and rev0 and gp1 and rev1 and (gp0 / rev0) > (gp1 / rev1): score += 1
        if rev0 and ta0 and rev1 and ta1 and (rev0 / ta0) > (rev1 / ta1): score += 1
        return score
    except Exception as e:
        print(f"[fundamental] piotroski failed: {e}")
        return None


def altman_z(st: dict, info: dict, manufacturer: bool = True) -> float | None:
    """Altman Z (manufacturers) / Z'' (non-manufacturers). Distress predictor."""
    bal, inc = st.get("balance"), st.get("income")
    if bal is None or inc is None:
        return None
    try:
        ta = _safe(bal, "Total Assets", col=0)
        if not ta:
            return None
        ca = _safe(bal, "Current Assets", "Total Current Assets", col=0) or 0.0
        cl = _safe(bal, "Current Liabilities", "Total Current Liabilities", col=0) or 0.0
        wc = ca - cl
        re = _safe(bal, "Retained Earnings", col=0) or 0.0
        ebit = _safe(inc, "EBIT", "Operating Income", col=0) or 0.0
        tl = _safe(bal, "Total Liabilities Net Minority Interest", "Total Liab", col=0) or 0.0
        rev = _safe(inc, "Total Revenue", col=0) or 0.0
        mcap = info.get("marketCap") or 0.0
        eq = _safe(bal, "Stockholders Equity", "Total Stockholder Equity", col=0) or 0.0
        if tl <= 0:
            return None
        A, B, C = wc / ta, re / ta, ebit / ta
        if manufacturer:
            D, E = mcap / tl, rev / ta
            return round(1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E, 2)
        return round(3.25 + 6.56 * A + 3.26 * B + 6.72 * C + 1.05 * (eq / tl), 2)
    except Exception as e:
        print(f"[fundamental] altman failed: {e}")
        return None


def _advanced(tkr, info: dict, archetype: str, st: dict) -> dict:
    """Compute the advanced composite scores appropriate for this archetype."""
    out = {"piotroski_f": None, "altman_z": None, "rule_of_40": None,
           "fcf_yield_pct": None, "peg": None, "roe_pct": None, "roa_pct": None,
           "price_to_book": None}
    try:
        out["roe_pct"] = round(float(info["returnOnEquity"]) * 100, 1) if info.get("returnOnEquity") is not None else None
        out["roa_pct"] = round(float(info["returnOnAssets"]) * 100, 1) if info.get("returnOnAssets") is not None else None
        out["price_to_book"] = round(float(info["priceToBook"]), 2) if info.get("priceToBook") is not None else None
        peg = info.get("trailingPegRatio") or info.get("pegRatio")
        out["peg"] = round(float(peg), 2) if peg is not None else None

        fcf = info.get("freeCashflow")
        mcap = info.get("marketCap")
        if fcf and mcap:
            out["fcf_yield_pct"] = round(fcf / mcap * 100, 2)

        # Rule of 40 — growth archetypes only
        if archetype in ("growth_tech", "mega_tech"):
            rg = info.get("revenueGrowth")
            rev = info.get("totalRevenue")
            if rg is not None and fcf and rev:
                out["rule_of_40"] = round(rg * 100 + (fcf / rev) * 100, 1)

        # Piotroski — quality/value names; skip financials/REITs (tests misfire)
        if archetype not in _NO_ZSCORE:
            out["piotroski_f"] = piotroski_f(st, info)
            manu = archetype in ("industrial", "materials", "energy", "staples")
            out["altman_z"] = altman_z(st, info, manufacturer=manu)
    except Exception as e:
        print(f"[fundamental] advanced failed: {e}")
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

def _edgar_insider(ticker: str, cik: str | None = None) -> dict:
    """
    Count Form 4 insider filings in the last 90 days via the SEC submissions API
    (CIK-based — reliable, unlike the prior full-text-search approach). Activity
    level only; yfinance supplies the buy/sell direction.
    """
    out = {"form4_count": 0}
    cik = cik or cik_for(ticker)
    if not cik:
        return out
    try:
        url = f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json"
        with httpx.Client(timeout=15, headers={"User-Agent": "SwingScreener research contact@example.com"}) as client:
            r = client.get(url)
            if r.status_code != 200:
                return out
            recent = (r.json() or {}).get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=90)
        cnt = 0
        for i, form in enumerate(forms):
            if form != "4":
                continue
            try:
                if datetime.fromisoformat(dates[i]).date() >= cutoff:
                    cnt += 1
                else:
                    break  # newest-first → older than 90d, stop
            except Exception:
                pass
        out["form4_count"] = cnt
    except Exception as e:
        print(f"[fundamental] EDGAR insider {ticker} failed: {e}")
    return out


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


# ── Archetype-aware scoring ───────────────────────────────────────────────────

def _metrics(f: dict) -> dict:
    """
    Compute every candidate metric, normalized to [-1,+1], from the assembled
    fundamental dict. Only metrics that are computable are returned; the scorer
    weight-averages over whichever ones exist for the archetype.
    """
    m: dict[str, float] = {}
    a, g, adv = f["analyst"], f["growth"], f.get("advanced", {})

    if a.get("target_upside_pct") is not None:
        m["pt_upside"] = _clamp(a["target_upside_pct"] / 25.0)      # +25% → +1
    if g.get("revenue_growth_pct") is not None:
        m["rev_growth"] = _clamp(g["revenue_growth_pct"] / 30.0)    # +30% → +1
    if g.get("earnings_growth_pct") is not None:
        m["eps_growth"] = _clamp(g["earnings_growth_pct"] / 40.0)   # +40% → +1
    if adv.get("roe_pct") is not None:
        m["roe"] = _clamp(adv["roe_pct"] / 25.0)                    # 25% ROE → +1
    if adv.get("roa_pct") is not None:
        m["roa"] = _clamp(adv["roa_pct"] / 10.0)                    # 10% ROA → +1
    if adv.get("fcf_yield_pct") is not None:
        m["fcf_yield"] = _clamp(adv["fcf_yield_pct"] / 8.0)         # 8% FCF yield → +1
    if adv.get("rule_of_40") is not None:
        m["rule40"] = _clamp((adv["rule_of_40"] - 40.0) / 40.0)     # 40 = neutral, 80 → +1
    if adv.get("peg") is not None and adv["peg"] > 0:
        m["peg"] = _clamp((2.0 - adv["peg"]) / 2.0)                 # PEG 1 → +0.5, 0 → +1, 4 → -1
    if adv.get("price_to_book") is not None and adv["price_to_book"] > 0:
        m["pb"] = _clamp((2.0 - adv["price_to_book"]) / 2.0)        # P/B 1 → +0.5 (financials/REIT)
    if adv.get("piotroski_f") is not None:
        m["piotroski"] = _clamp((adv["piotroski_f"] - 4.5) / 4.5)   # 9 → +1, 0 → -1

    info = f.get("_info", {})
    gm = info.get("grossMargins")
    if gm is not None:
        m["gross_margin"] = _clamp((float(gm) - 0.40) / 0.40)       # 40% neutral, 80% → +1
    om = info.get("operatingMargins")
    if om is not None:
        m["op_margin"] = _clamp((float(om) - 0.15) / 0.20)          # 15% neutral
    pm = info.get("profitMargins")
    if pm is not None:
        m["profit_margin"] = _clamp((float(pm) - 0.10) / 0.20)
    dy = info.get("dividendYield")
    if dy is not None:
        dyv = float(dy) / 100.0 if float(dy) > 1.5 else float(dy)   # yfinance returns % or frac
        m["div_yield"] = _clamp(dyv / 0.04)                         # 4% yield → +1
    pr = info.get("payoutRatio")
    if pr is not None:
        m["payout"] = _clamp((0.60 - float(pr)) / 0.60)            # lower payout = safer
    de = info.get("debtToEquity")
    if de is not None:
        m["debt_equity"] = _clamp((100.0 - float(de)) / 100.0)     # D/E 1.0 neutral, 0 → +1

    return m


def _score(f: dict) -> float:
    """
    Archetype-aware fundamental score ∈ [-1,+1]. Weight-averages the metrics that
    matter for this business model, then overlays insider direction, an Altman
    distress penalty (non-financials), and the just-reported earnings event.
    """
    archetype = f.get("archetype", "default")
    weights = ARCHETYPE_WEIGHTS.get(archetype, ARCHETYPE_WEIGHTS["default"])
    m = _metrics(f)

    num = den = 0.0
    for metric, w in weights.items():
        if metric in m:
            num += w * m[metric]
            den += w
    base = (num / den) if den else 0.0

    # Overlays (applied on top of the archetype-weighted base)
    overlay = 0.0
    overlay += 0.10 * f.get("insider", {}).get("net_buy_signal", 0.0)

    adv = f.get("advanced", {})
    z = adv.get("altman_z")
    if z is not None:                                  # distress penalty (non-financials only)
        if z < 1.8:
            overlay -= 0.10
        elif z > 3.0:
            overlay += 0.05

    overlay += f.get("earnings_call", {}).get("score_delta", 0.0)  # conference-call event

    return round(_clamp(base + overlay), 3)


# ── Main entry ────────────────────────────────────────────────────────────────

def fetch_fundamentals(ticker: str) -> dict:
    """Full fundamental snapshot + score for one stock. Best-effort, never raises."""
    f = {
        "ticker": ticker,
        "archetype": "default",
        "earnings": {"next_days": None, "last_surprise_pct": None, "imminent": False},
        "analyst": {"recommendation": None, "target_upside_pct": None, "num_analysts": None},
        "insider": {"net_buy_signal": 0.0, "buy_count": 0, "sell_count": 0},
        "institutional": {"inst_held_pct": None},
        "growth": {"revenue_growth_pct": None, "earnings_growth_pct": None},
        "short": {"short_pct_float": None},
        "advanced": {"piotroski_f": None, "altman_z": None, "rule_of_40": None,
                     "fcf_yield_pct": None, "peg": None, "roe_pct": None,
                     "roa_pct": None, "price_to_book": None},
        "earnings_call": {"reported": False, "score_delta": 0.0},
        "news": {"news_7d": 0, "headlines": [], "sentiment": 0.0},
        "finviz": {},
        "edgar_insider": {"form4_count": 0},
        "rss_news": {"rss_news_7d": 0},
        "score": 0.0,
        "updated_at": _now(),
    }
    cik = cik_for(ticker)
    try:
        import yfinance as yf
        tkr = yf.Ticker(ticker)
        info = tkr.info or {}
        f["_info"] = info
        f["archetype"] = archetype_of(info)
        f["earnings"] = _earnings(tkr)
        f["analyst"] = _analyst(tkr)
        f["insider"] = _insider(tkr)
        f["institutional"] = _institutional(tkr)
        f["growth"] = _growth(tkr)
        f["short"] = _short_interest(tkr)
        try:
            st = _statements(tkr)
            f["advanced"] = _advanced(tkr, info, f["archetype"], st)
        except Exception as e:
            print(f"[fundamental] advanced {ticker} error: {e}")
    except Exception as e:
        print(f"[fundamental] yfinance {ticker} failed: {e}")
        tkr = None

    f["news"] = _news_sentiment(ticker)

    # Earnings conference-call / event monitor (folds a bounded delta into score)
    try:
        from earnings_call import earnings_update
        f["earnings_call"] = earnings_update(ticker, tkr=tkr, cik=cik)
    except Exception as e:
        print(f"[fundamental] earnings_call {ticker} error: {e}")

    # Supplemental sources — best-effort, non-blocking
    try:
        f["finviz"] = _finviz(ticker)
    except Exception as e:
        print(f"[fundamental] finviz {ticker} error: {e}")

    try:
        f["edgar_insider"] = _edgar_insider(ticker, cik=cik)
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
            info = f.get("_info", {})
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if price:
                f["analyst"]["target_upside_pct"] = round(
                    (fv["price_target"] / float(price) - 1) * 100, 2
                )
        except Exception:
            pass

    f["score"] = _score(f)
    f.pop("_info", None)   # drop the bulky yfinance info blob before persisting
    return f
