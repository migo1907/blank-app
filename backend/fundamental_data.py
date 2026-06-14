"""
Swing addon — Fundamental data fetcher (all free sources).

Pulls the fundamental / sentiment picture for a single stock and reduces it to a
structured dict plus a normalized fundamental score ∈ [-1, +1] (positive =
bullish). Powers the swing screener and the narrative synthesis layer.

Sources (all free, no paid keys):
  • yfinance  — earnings calendar + surprise, analyst targets/consensus, insider
                transactions, institutional ownership, quarterly revenue/EPS
                growth, short interest. Cached, daily refresh is plenty for
                fundamentals.
  • Finnhub   — company-specific news + sentiment (already integrated for the
                intraday system; FINNHUB_KEY in Railway). Graceful no-op if unset.

Every fetch is best-effort: a failed source contributes 0 to the score rather
than blocking the others. A stock with no data at all returns a neutral dict.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import httpx

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ── Individual source readers (each returns a small dict; never raises) ────────

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
            # yfinance labels vary; classify by the transaction-text column
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


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(f: dict) -> float:
    """Reduce the fundamental dict to a single bullish/bearish score ∈ [-1, +1]."""
    parts: list[float] = []

    a = f["analyst"]
    if a["target_upside_pct"] is not None:
        parts.append(_clamp(a["target_upside_pct"] / 25.0))  # +25% upside → +1
    rec = (a["recommendation"] or "").lower()
    if rec in ("strong_buy", "buy"):
        parts.append(0.6 if rec == "strong_buy" else 0.4)
    elif rec in ("sell", "strong_sell", "underperform"):
        parts.append(-0.5)

    e = f["earnings"]
    if e["last_surprise_pct"] is not None:
        parts.append(_clamp(e["last_surprise_pct"] / 20.0))

    parts.append(0.5 * f["insider"]["net_buy_signal"])

    g = f["growth"]
    if g["revenue_growth_pct"] is not None:
        parts.append(_clamp(g["revenue_growth_pct"] / 30.0))
    if g["earnings_growth_pct"] is not None:
        parts.append(_clamp(g["earnings_growth_pct"] / 40.0))

    if not parts:
        return 0.0
    return round(_clamp(sum(parts) / len(parts)), 3)


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
    f["score"] = _score(f)
    return f
