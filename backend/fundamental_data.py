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
  • SEC EDGAR — CIK-based Form 4 insider-filing count + 8-K text (no auth).
  • CNBC / MarketWatch / Benzinga RSS — company headline counts (past 7d).

Advanced valuation/quality ratios (P/E, forward P/E, PEG, ROE/ROA, P/B, FCF
yield, Rule of 40, Piotroski F-Score, Altman Z) are computed directly from
yfinance `info` + statements in _advanced() — no scraping needed.

Every fetch is best-effort: a failed source contributes 0 to the score rather
than blocking the others. A stock with no data at all returns a neutral dict.

Note on Finviz / SeekingAlpha / TradingView: all block cloud/datacenter IPs or
have no free REST API; not viable from Railway. yfinance covers their fields.
"""

from __future__ import annotations

import os
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
           "price_to_book": None, "pe_ratio": None, "forward_pe": None}
    try:
        out["pe_ratio"] = round(float(info["trailingPE"]), 1) if info.get("trailingPE") is not None else None
        out["forward_pe"] = round(float(info["forwardPE"]), 1) if info.get("forwardPE") is not None else None
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

def _finnhub_metrics(ticker: str) -> dict:
    """
    Finnhub /stock/metric — 80+ pre-computed financial ratios updated daily.
    More reliable than yfinance from Railway cloud IPs. Used as primary source;
    yfinance fills any gaps.

    Key fields mapped:
      peNormalizedAnnual, pbAnnual, pegAnnual, roeTTM, roaTTM,
      grossMarginTTM, operatingMarginTTM, netMarginTTM,
      revenueGrowthTTMYoy, epsGrowthTTMYoy, revenueGrowth3Y,
      dividendYieldIndicatedAnnual, payoutRatioAnnual,
      debtEquityAnnual, currentRatioAnnual, fcfYieldTTM,
      52WeekHigh, 52WeekLow, marketCapitalization
    """
    if not FINNHUB_KEY:
        return {}
    try:
        with httpx.Client(timeout=12) as c:
            r = c.get(
                "https://finnhub.io/api/v1/stock/metric",
                params={"symbol": ticker, "metric": "all", "token": FINNHUB_KEY},
            )
            if r.status_code != 200:
                return {}
            return r.json().get("metric", {})
    except Exception as e:
        print(f"[fundamental] Finnhub metric {ticker} failed: {e}")
        return {}


def _finnhub_earnings_quality(ticker: str) -> dict:
    """
    Finnhub /stock/earnings — last 4 quarters EPS surprise history.
    Returns: beat_rate (0-1), avg_surprise_pct, consecutive_beats.
    Beat rate 1.0 = 4/4 quarters beat; consecutive_beats = unbroken recent streak.
    """
    out = {"beat_rate": None, "avg_surprise_pct": None, "consecutive_beats": 0}
    if not FINNHUB_KEY:
        return out
    try:
        with httpx.Client(timeout=12) as c:
            r = c.get(
                "https://finnhub.io/api/v1/stock/earnings",
                params={"symbol": ticker, "limit": 4, "token": FINNHUB_KEY},
            )
            if r.status_code != 200:
                return out
            data = r.json()
        if not isinstance(data, list) or not data:
            return out
        beats, surprises, consecutive = 0, [], 0
        for q in data:
            actual = q.get("actual")
            est = q.get("estimate")
            if actual is None or est is None or est == 0:
                continue
            surprise = (actual - est) / abs(est) * 100
            surprises.append(surprise)
            if actual > est:
                beats += 1
                consecutive += 1
            else:
                consecutive = 0
        if surprises:
            out["beat_rate"] = round(beats / len(surprises), 2)
            out["avg_surprise_pct"] = round(sum(surprises) / len(surprises), 1)
            out["consecutive_beats"] = consecutive
    except Exception as e:
        print(f"[fundamental] Finnhub earnings quality {ticker} failed: {e}")
    return out


def _finnhub_analyst_revision(ticker: str) -> dict:
    """
    Finnhub /stock/recommendation — monthly analyst rating trend.
    Compares current buy% vs 3-month average to detect revision momentum.
    revision_score > 0 = analysts upgrading; < 0 = downgrading cycle.
    """
    out = {"revision_score": 0.0, "buy_pct_now": None, "buy_pct_3m_avg": None}
    if not FINNHUB_KEY:
        return out
    try:
        with httpx.Client(timeout=12) as c:
            r = c.get(
                "https://finnhub.io/api/v1/stock/recommendation",
                params={"symbol": ticker, "token": FINNHUB_KEY},
            )
            if r.status_code != 200:
                return out
            data = r.json()
        if not isinstance(data, list) or len(data) < 2:
            return out

        def buy_pct(row: dict) -> float:
            sb, b = row.get("strongBuy", 0), row.get("buy", 0)
            h, s, ss = row.get("hold", 0), row.get("sell", 0), row.get("strongSell", 0)
            total = sb + b + h + s + ss
            return (sb + b) / total if total > 0 else 0.0

        now_pct = buy_pct(data[0])
        out["buy_pct_now"] = round(now_pct * 100, 1)
        hist = data[1:4]
        if hist:
            avg = sum(buy_pct(row) for row in hist) / len(hist)
            out["buy_pct_3m_avg"] = round(avg * 100, 1)
            out["revision_score"] = round((now_pct - avg) / max(avg, 0.01), 3)
    except Exception as e:
        print(f"[fundamental] Finnhub revision {ticker} failed: {e}")
    return out


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
    Compute every candidate metric, normalized to [-1,+1].
    Finnhub /stock/metric is the primary source (reliable from cloud IPs, updated
    daily); yfinance info fills any gaps. New signals: earnings beat rate,
    analyst revision momentum, 52W range position, margin quality.
    """
    m: dict[str, float] = {}
    a, g, adv = f["analyst"], f["growth"], f.get("advanced", {})
    fh  = f.get("finnhub_metrics", {})   # Finnhub /stock/metric blob
    info = f.get("_info", {})            # yfinance info fallback

    # ── Valuation upside ──────────────────────────────────────────────────────
    if a.get("target_upside_pct") is not None:
        m["pt_upside"] = _clamp(a["target_upside_pct"] / 25.0)      # +25% → +1

    # ── Growth — Finnhub primary, yfinance fallback ───────────────────────────
    rev_g = fh.get("revenueGrowthTTMYoy") or g.get("revenue_growth_pct")
    if rev_g is not None:
        m["rev_growth"] = _clamp(float(rev_g) / 30.0)               # +30% → +1

    eps_g = fh.get("epsGrowthTTMYoy") or g.get("earnings_growth_pct")
    if eps_g is not None:
        m["eps_growth"] = _clamp(float(eps_g) / 40.0)               # +40% → +1

    # Revenue growth acceleration: 1Y vs 3Y rate — rising growth rate is a buy signal
    rev_g3 = fh.get("revenueGrowth3Y")
    if rev_g is not None and rev_g3 is not None and rev_g3 != 0:
        accel = (float(rev_g) - float(rev_g3)) / abs(float(rev_g3))
        m["rev_accel"] = _clamp(accel / 1.0)                        # 100% acceleration → +1

    # ── Profitability — Finnhub primary ───────────────────────────────────────
    roe = fh.get("roeTTM") or (adv.get("roe_pct", 0) / 100 if adv.get("roe_pct") else None)
    if roe is not None:
        m["roe"] = _clamp(float(roe) / 0.25)                        # 25% ROE → +1

    roa = fh.get("roaTTM") or (adv.get("roa_pct", 0) / 100 if adv.get("roa_pct") else None)
    if roa is not None:
        m["roa"] = _clamp(float(roa) / 0.10)                        # 10% ROA → +1

    gm = fh.get("grossMarginTTM") or info.get("grossMargins")
    if gm is not None:
        m["gross_margin"] = _clamp((float(gm) - 0.40) / 0.40)       # 40% neutral, 80% → +1

    om = fh.get("operatingMarginTTM") or info.get("operatingMargins")
    if om is not None:
        m["op_margin"] = _clamp((float(om) - 0.15) / 0.20)

    pm = fh.get("netMarginTTM") or info.get("profitMargins")
    if pm is not None:
        m["profit_margin"] = _clamp((float(pm) - 0.10) / 0.20)

    # ── Valuation quality ─────────────────────────────────────────────────────
    fcf = fh.get("fcfYieldTTM") or (adv.get("fcf_yield_pct", 0) / 100 if adv.get("fcf_yield_pct") else None)
    if fcf is not None:
        m["fcf_yield"] = _clamp(float(fcf) / 0.08)                  # 8% FCF yield → +1

    if adv.get("rule_of_40") is not None:
        m["rule40"] = _clamp((adv["rule_of_40"] - 40.0) / 40.0)     # 40 = neutral, 80 → +1

    peg = fh.get("pegAnnual") or adv.get("peg")
    if peg is not None and float(peg) > 0:
        m["peg"] = _clamp((2.0 - float(peg)) / 2.0)                 # PEG 1 → +0.5, 0 → +1, 4 → -1

    pb = fh.get("pbAnnual") or adv.get("price_to_book")
    if pb is not None and float(pb) > 0:
        m["pb"] = _clamp((2.0 - float(pb)) / 2.0)

    # ── Quality scores ────────────────────────────────────────────────────────
    if adv.get("piotroski_f") is not None:
        m["piotroski"] = _clamp((adv["piotroski_f"] - 4.5) / 4.5)   # 9 → +1, 0 → -1

    # ── Income / leverage ─────────────────────────────────────────────────────
    dy = fh.get("dividendYieldIndicatedAnnual") or info.get("dividendYield")
    if dy is not None:
        dyv = float(dy) / 100.0 if float(dy) > 1.5 else float(dy)
        m["div_yield"] = _clamp(dyv / 0.04)                         # 4% yield → +1

    pr = fh.get("payoutRatioAnnual") or info.get("payoutRatio")
    if pr is not None:
        m["payout"] = _clamp((0.60 - float(pr)) / 0.60)

    de = fh.get("debtEquityAnnual") or info.get("debtToEquity")
    if de is not None:
        # Finnhub returns as ratio (e.g. 0.5); yfinance as % (e.g. 50). Normalise.
        dev = float(de) / 100.0 if float(de) > 10 else float(de)
        m["debt_equity"] = _clamp((1.0 - dev) / 1.0)               # D/E 0 → +1, 2.0 → -1

    # ── 52-week range position — proximity to high signals breakout setup ─────
    high52 = fh.get("52WeekHigh")
    low52  = fh.get("52WeekLow")
    if high52 and low52 and high52 > low52:
        # current price implicitly in the target_upside calc; approximate from analyst data
        price = a.get("current_price") or info.get("currentPrice")
        if price:
            rng = float(high52) - float(low52)
            pos = (float(price) - float(low52)) / rng   # 0 = at 52W low, 1 = at high
            # Strong fundamentals + near 52W high = trend confirmation, not overextension
            m["range_pos"] = _clamp((pos - 0.5) / 0.5)  # above midrange = positive

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

    # ── Overlays (applied on top of archetype-weighted base) ────────────────
    overlay = 0.0

    # Insider net buying direction
    overlay += 0.08 * f.get("insider", {}).get("net_buy_signal", 0.0)

    # Altman Z distress penalty (non-financials only)
    adv = f.get("advanced", {})
    z = adv.get("altman_z")
    if z is not None:
        if z < 1.8:
            overlay -= 0.10
        elif z > 3.0:
            overlay += 0.05

    # Earnings conference-call event delta
    overlay += f.get("earnings_call", {}).get("score_delta", 0.0)

    # Earnings beat rate: 4/4 quarters = +0.08, 0/4 = -0.08
    eq = f.get("earnings_quality", {})
    beat_rate = eq.get("beat_rate")
    if beat_rate is not None:
        overlay += 0.08 * _clamp((beat_rate - 0.5) / 0.5)

    # Consecutive beat streak bonus (3+ unbroken beats = momentum signal)
    consec = eq.get("consecutive_beats", 0)
    if consec >= 3:
        overlay += 0.05
    elif consec == 0 and beat_rate is not None:
        overlay -= 0.03  # missed most recent quarter

    # Analyst revision momentum: upgrading cycle → buy
    ar = f.get("analyst_revision", {})
    rev_score = ar.get("revision_score", 0.0)
    if rev_score:
        overlay += 0.07 * _clamp(rev_score * 3)  # 33% improvement in buy% → full weight

    return round(_clamp(base + overlay), 3)


# ── Main entry ────────────────────────────────────────────────────────────────

def fetch_fundamentals(ticker: str) -> dict:
    """
    Full fundamental snapshot + score for one stock. Best-effort, never raises.

    Data priority:
      1. Finnhub /stock/metric — primary ratios (cloud-reliable, daily refresh)
      2. Finnhub /stock/earnings — EPS beat rate + surprise history
      3. Finnhub /stock/recommendation — analyst revision momentum
      4. yfinance — archetype classification, earnings calendar, insider transactions,
                    institutional ownership, short interest, financial statements
                    (Piotroski, Altman Z, Rule of 40). Fallback for any Finnhub gap.
      5. SEC EDGAR — Form 4 count (insider activity confirmation)
      6. RSS feeds  — CNBC / MarketWatch / Benzinga headline count
    """
    f = {
        "ticker": ticker,
        "archetype": "default",
        "finnhub_metrics":    {},
        "earnings_quality":   {"beat_rate": None, "avg_surprise_pct": None, "consecutive_beats": 0},
        "analyst_revision":   {"revision_score": 0.0, "buy_pct_now": None, "buy_pct_3m_avg": None},
        "earnings": {"next_days": None, "last_surprise_pct": None, "imminent": False},
        "analyst":  {"recommendation": None, "target_upside_pct": None, "num_analysts": None},
        "insider":  {"net_buy_signal": 0.0, "buy_count": 0, "sell_count": 0},
        "institutional": {"inst_held_pct": None},
        "growth":   {"revenue_growth_pct": None, "earnings_growth_pct": None},
        "short":    {"short_pct_float": None},
        "advanced": {"piotroski_f": None, "altman_z": None, "rule_of_40": None,
                     "fcf_yield_pct": None, "peg": None, "roe_pct": None,
                     "roa_pct": None, "price_to_book": None},
        "earnings_call": {"reported": False, "score_delta": 0.0},
        "news":          {"news_7d": 0, "headlines": [], "sentiment": 0.0},
        "edgar_insider": {"form4_count": 0},
        "rss_news":      {"rss_news_7d": 0},
        "score": 0.0,
        "updated_at": _now(),
    }

    # ── Finnhub (primary — cloud-reliable) ───────────────────────────────────
    try:
        f["finnhub_metrics"]  = _finnhub_metrics(ticker)
    except Exception as e:
        print(f"[fundamental] finnhub_metrics {ticker} error: {e}")
    try:
        f["earnings_quality"] = _finnhub_earnings_quality(ticker)
    except Exception as e:
        print(f"[fundamental] earnings_quality {ticker} error: {e}")
    try:
        f["analyst_revision"] = _finnhub_analyst_revision(ticker)
    except Exception as e:
        print(f"[fundamental] analyst_revision {ticker} error: {e}")

    # ── yfinance (secondary — gaps + statements + archetype) ─────────────────
    cik = cik_for(ticker)
    tkr = None
    try:
        import yfinance as yf
        tkr  = yf.Ticker(ticker)
        info = tkr.info or {}
        f["_info"]         = info
        f["archetype"]     = archetype_of(info)
        f["earnings"]      = _earnings(tkr)
        f["analyst"]       = _analyst(tkr)
        f["insider"]       = _insider(tkr)
        f["institutional"] = _institutional(tkr)
        f["growth"]        = _growth(tkr)
        f["short"]         = _short_interest(tkr)

        # Patch analyst current_price into f so _metrics() can read 52W range
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price:
            f["analyst"]["current_price"] = float(price)

        try:
            st = _statements(tkr)
            f["advanced"] = _advanced(tkr, info, f["archetype"], st)
        except Exception as e:
            print(f"[fundamental] advanced {ticker} error: {e}")
    except Exception as e:
        print(f"[fundamental] yfinance {ticker} failed: {e}")

    # ── Finnhub company news ──────────────────────────────────────────────────
    f["news"] = _news_sentiment(ticker)

    # ── Earnings conference-call event monitor ────────────────────────────────
    try:
        from earnings_call import earnings_update
        f["earnings_call"] = earnings_update(ticker, tkr=tkr, cik=cik)
    except Exception as e:
        print(f"[fundamental] earnings_call {ticker} error: {e}")

    # ── SEC EDGAR Form 4 count ────────────────────────────────────────────────
    try:
        f["edgar_insider"] = _edgar_insider(ticker, cik=cik)
    except Exception as e:
        print(f"[fundamental] edgar {ticker} error: {e}")

    # ── RSS headline count ────────────────────────────────────────────────────
    try:
        f["rss_news"] = _multi_rss_news(ticker)
    except Exception as e:
        print(f"[fundamental] rss news {ticker} error: {e}")

    f["score"] = _score(f)
    f.pop("_info", None)   # drop the bulky yfinance info blob before persisting
    return f
