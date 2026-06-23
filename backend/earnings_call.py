"""
Swing addon — Earnings conference-call monitoring.

Detects when a watchlist stock has JUST reported earnings and extracts the
swing-relevant signals from the event — beat/miss magnitude, guidance
raised/cut, management tone, buyback/dividend actions — folding a bounded
score delta into the fundamental score and a short note into the thesis.

Free, cloud-accessible stack (no premium transcript APIs — those are paywalled
or IP-blocked from cloud servers, confirmed by research):
  • Finnhub `/calendar/earnings`  — free tier — who reported + epsActual/estimate
    + revenueActual/estimate (the numeric beat/miss). One call per ticker.
  • yfinance `get_earnings_dates` — free fallback for the surprise % + the
    "reported in last N days" detection.
  • SEC EDGAR 8-K (Item 2.02) — free, cloud-friendly — the furnished earnings
    press release / guidance text, for the guidance-direction + tone read.
  • Claude Haiku (dormant-by-default, ANTHROPIC_API_KEY already on Railway) —
    optional 2-line guidance/tone synthesis when press-release text is in hand.

Every layer is best-effort: a stock outside its post-earnings window returns a
neutral {reported: False, score_delta: 0.0} with zero network cost beyond the
detection call. Only the 2-3 names actually in an earnings window pay for the
8-K fetch.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone, timedelta

import httpx

FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("SWING_NARRATIVE_MODEL", "claude-haiku-4-5-20251001")

_WINDOW_DAYS = 10  # treat a report within this many days as "just reported"

_EDGAR_HEADERS = {"User-Agent": "SwingScreener research contact@example.com"}
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

# Guidance-direction lexicon (applied to press-release / call text)
_RAISE = re.compile(
    r"\b(rais(?:e|ed|ing)|increas(?:e|ed|ing)|boost(?:ed)?|lift(?:ed)?)\b[^.]{0,40}"
    r"\b(guidance|outlook|forecast|full[- ]year|fy\d{0,2}|target)", re.I)
_CUT = re.compile(
    r"\b(lower(?:ed|ing)?|cut|reduc(?:e|ed|ing)|trim(?:med)?|slash(?:ed)?)\b[^.]{0,40}"
    r"\b(guidance|outlook|forecast|full[- ]year|fy\d{0,2}|target)", re.I)
_REAFFIRM = re.compile(
    r"\b(reaffirm(?:s|ed|ing)?|reiterat(?:e|ed|ing|es)|maintain(?:s|ed|ing)?|on track)\b"
    r"[^.]{0,40}\b(guidance|outlook|forecast)", re.I)
_BUYBACK = re.compile(
    r"\b(repurchase|buyback|authoriz(?:e|ed|ation))\b[^.]{0,30}\b(share|stock|\$)", re.I)
_DIV_RAISE = re.compile(r"\b(increas(?:e|ed)|rais(?:e|ed)|boost)\b[^.]{0,20}\bdividend", re.I)

_POS = ("strong", "record", "momentum", "accelerat", "robust", "confident", "outperform",
        "beat", "exceed", "raised", "demand", "expansion", "tailwind")
_NEG = ("headwind", "soft", "weak", "cautious", "uncertain", "challeng", "pressure",
        "decline", "miss", "lower", "slowdown", "disappoint", "macro")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Detection: did this stock just report? ─────────────────────────────────────

def _finnhub_recent(ticker: str) -> dict | None:
    """Finnhub earnings calendar: most recent reported quarter within the window."""
    if not FINNHUB_KEY:
        return None
    try:
        today = datetime.now(timezone.utc).date()
        frm = (today - timedelta(days=_WINDOW_DAYS)).isoformat()
        url = "https://finnhub.io/api/v1/calendar/earnings"
        params = {"symbol": ticker, "from": frm, "to": today.isoformat(), "token": FINNHUB_KEY}
        with httpx.Client(timeout=12) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            rows = (r.json() or {}).get("earningsCalendar", []) or []
        rows = [x for x in rows if x.get("epsActual") is not None]
        if not rows:
            return None
        row = sorted(rows, key=lambda x: x.get("date", ""))[-1]
        act, est = row.get("epsActual"), row.get("epsEstimate")
        rev_a, rev_e = row.get("revenueActual"), row.get("revenueEstimate")
        surprise = None
        if act is not None and est not in (None, 0):
            surprise = round((act - est) / abs(est) * 100, 1)
        rep_date = row.get("date")
        days_ago = None
        try:
            days_ago = (today - datetime.fromisoformat(rep_date).date()).days
        except Exception:
            pass
        return {
            "date": rep_date, "days_ago": days_ago,
            "eps_actual": act, "eps_estimate": est,
            "rev_beat_pct": (round((rev_a - rev_e) / abs(rev_e) * 100, 1)
                             if rev_a is not None and rev_e not in (None, 0) else None),
            "surprise_pct": surprise,
            "source": "finnhub",
        }
    except Exception as e:
        print(f"[earnings_call] finnhub recent {ticker} failed: {e}")
        return None


def _yf_recent(tkr) -> dict | None:
    """yfinance fallback: scan get_earnings_dates for a reported row in the window."""
    try:
        df = tkr.get_earnings_dates(limit=8)
        if df is None or not len(df):
            return None
        now = datetime.now(timezone.utc)
        for idx, row in df.iterrows():
            try:
                dt = idx.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
            days_ago = (now - dt).days
            reported = row.get("Reported EPS")
            if 0 <= days_ago <= _WINDOW_DAYS and reported is not None and reported == reported:
                sp = row.get("Surprise(%)")
                return {
                    "date": dt.date().isoformat(), "days_ago": days_ago,
                    "eps_actual": float(reported) if reported == reported else None,
                    "eps_estimate": (float(row.get("EPS Estimate"))
                                     if row.get("EPS Estimate") == row.get("EPS Estimate") else None),
                    "rev_beat_pct": None,
                    "surprise_pct": (round(float(sp), 1) if sp is not None and sp == sp else None),
                    "source": "yfinance",
                }
    except Exception as e:
        print(f"[earnings_call] yfinance recent failed: {e}")
    return None


# ── SEC EDGAR 8-K earnings press-release text ─────────────────────────────────

def _edgar_8k_text(cik: str | None) -> str:
    """Best-effort: pull the most recent 8-K primary document text for guidance read."""
    if not cik:
        return ""
    try:
        cik10 = str(cik).zfill(10)
        sub_url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
        with httpx.Client(timeout=15, headers=_EDGAR_HEADERS) as c:
            r = c.get(sub_url)
            r.raise_for_status()
            data = r.json()
            recent = data.get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            accns = recent.get("accessionNumber", [])
            docs = recent.get("primaryDocument", [])
            dates = recent.get("filingDate", [])
            cutoff = (datetime.now(timezone.utc).date() - timedelta(days=_WINDOW_DAYS + 4))
            for i, form in enumerate(forms):
                if form != "8-K":
                    continue
                try:
                    if datetime.fromisoformat(dates[i]).date() < cutoff:
                        break  # recent[] is newest-first; older than window → stop
                except Exception:
                    pass
                accn = accns[i].replace("-", "")
                doc = docs[i]
                doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{doc}"
                rd = c.get(doc_url)
                if rd.status_code == 200:
                    text = re.sub(r"<[^>]+>", " ", rd.text)
                    text = re.sub(r"\s+", " ", text)
                    return text[:20000]
    except Exception as e:
        print(f"[earnings_call] edgar 8-K failed: {e}")
    return ""


# ── Signal extraction ─────────────────────────────────────────────────────────

def _guidance_signals(text: str) -> dict:
    """Keyword + lexicon read of the press release / call text."""
    out = {"guidance": "none", "buyback": False, "dividend_raise": False, "tone": 0.0}
    if not text:
        return out
    if _CUT.search(text):
        out["guidance"] = "cut"
    elif _RAISE.search(text):
        out["guidance"] = "raised"
    elif _REAFFIRM.search(text):
        out["guidance"] = "reaffirmed"
    out["buyback"] = bool(_BUYBACK.search(text))
    out["dividend_raise"] = bool(_DIV_RAISE.search(text))
    low = text.lower()
    pos = sum(low.count(w) for w in _POS)
    neg = sum(low.count(w) for w in _NEG)
    tot = pos + neg
    if tot:
        out["tone"] = round((pos - neg) / tot, 3)
    return out


def _score_delta(surprise_pct, rev_beat_pct, sig: dict) -> float:
    """Bounded additive contribution to the fundamental score from the earnings event."""
    d = 0.0
    if surprise_pct is not None:
        d += max(-0.20, min(0.20, surprise_pct / 40.0))
    if rev_beat_pct is not None:
        d += max(-0.10, min(0.10, rev_beat_pct / 20.0))
    d += {"raised": 0.15, "cut": -0.20, "reaffirmed": 0.05, "none": 0.0}[sig["guidance"]]
    if sig["buyback"]:
        d += 0.05
    if sig["dividend_raise"]:
        d += 0.05
    d += max(-0.10, min(0.10, sig["tone"] * 0.10))
    return round(max(-0.40, min(0.40, d)), 3)


def _haiku_note(ticker: str, ev: dict, sig: dict) -> str:
    """Optional one-line guidance/tone synthesis (dormant without the key)."""
    if not ANTHROPIC_API_KEY:
        return ""
    facts = []
    if ev.get("surprise_pct") is not None:
        facts.append(f"EPS surprise {ev['surprise_pct']:+.1f}%")
    if ev.get("rev_beat_pct") is not None:
        facts.append(f"revenue {ev['rev_beat_pct']:+.1f}% vs est")
    if sig["guidance"] != "none":
        facts.append(f"guidance {sig['guidance']}")
    if sig["buyback"]:
        facts.append("new buyback authorization")
    if sig["dividend_raise"]:
        facts.append("dividend raised")
    if not facts:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=MODEL, max_tokens=90,
            messages=[{"role": "user", "content": (
                f"One sentence (max 25 words), institutional tone, on {ticker}'s just-"
                f"reported quarter for a swing trader. State the post-earnings setup. "
                f"No preamble. Facts: " + "; ".join(facts))}],
        )
        return next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "").strip()
    except Exception as e:
        print(f"[earnings_call] haiku note {ticker} failed: {e}")
        return ""


# ── Public entry ──────────────────────────────────────────────────────────────

def earnings_update(ticker: str, tkr=None, cik: str | None = None) -> dict:
    """
    Conference-call / earnings monitor for one ticker. Returns a neutral dict with
    score_delta 0.0 when the stock has not reported within the window.

    `tkr` (yfinance Ticker) and `cik` may be passed in to avoid re-fetching when the
    caller already has them (the screener does).
    """
    out = {
        "reported": False, "date": None, "days_ago": None,
        "surprise_pct": None, "rev_beat_pct": None,
        "guidance": "none", "buyback": False, "dividend_raise": False,
        "tone": 0.0, "note": "", "score_delta": 0.0, "updated_at": _now(),
    }

    ev = _finnhub_recent(ticker)
    if ev is None and tkr is not None:
        ev = _yf_recent(tkr)
    if not ev:
        return out

    out.update({k: ev.get(k) for k in ("date", "days_ago", "surprise_pct", "rev_beat_pct")})
    out["reported"] = True

    text = _edgar_8k_text(cik)
    sig = _guidance_signals(text)
    out.update({k: sig[k] for k in ("guidance", "buyback", "dividend_raise", "tone")})
    out["score_delta"] = _score_delta(ev.get("surprise_pct"), ev.get("rev_beat_pct"), sig)
    out["note"] = _haiku_note(ticker, ev, sig)
    return out
