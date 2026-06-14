"""
Swing addon — Narrative synthesis ("the why").

Turns a screener candidate's structured fundamental + technical data into a short,
readable swing thesis via Claude Haiku (cheapest capable model, ~$0.002/stock).

DORMANT BY DEFAULT — exactly like the Tradier / Alpha Vantage providers:
  • If ANTHROPIC_API_KEY is unset, `synthesize` returns a structured bullet
    summary built from the same data — no LLM call, no failure. The swing system
    runs fully without the key.
  • The moment ANTHROPIC_API_KEY is set in Railway, prose synthesis activates on
    the next deploy with zero code changes.

Model: claude-haiku-4-5 (override via SWING_NARRATIVE_MODEL).
"""

from __future__ import annotations

import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("SWING_NARRATIVE_MODEL", "claude-haiku-4-5-20251001")


def available() -> bool:
    """True when prose synthesis is active (key present)."""
    return bool(ANTHROPIC_API_KEY)


def _facts(cand: dict) -> list[str]:
    """Flatten the candidate into human-readable fact lines (shared by both paths)."""
    f = cand.get("fundamental", {})
    t = cand.get("technical", {})
    a, e, g = f.get("analyst", {}), f.get("earnings", {}), f.get("growth", {})
    ins, sh, nw = f.get("insider", {}), f.get("short", {}), f.get("news", {})
    lines = []

    if a.get("recommendation"):
        rec = a["recommendation"].replace("_", " ").title()
        up = a.get("target_upside_pct")
        lines.append(f"Analyst consensus {rec}" + (f", median PT {up:+.1f}% vs price" if up is not None else ""))
    if t.get("trend"):
        lines.append(f"Daily trend {t['trend']}")
    if t.get("rel_strength_pct") is not None:
        lines.append(f"Sector relative strength {t['rel_strength_pct']:+.1f}% (20d)")
    if e.get("next_days") is not None:
        flag = " — IMMINENT, de-risked" if e.get("imminent") else ""
        lines.append(f"Earnings in {e['next_days']}d{flag}")
    if e.get("last_surprise_pct") is not None:
        lines.append(f"Last earnings surprise {e['last_surprise_pct']:+.1f}%")
    if g.get("revenue_growth_pct") is not None:
        lines.append(f"Revenue growth {g['revenue_growth_pct']:+.1f}% YoY")
    if g.get("earnings_growth_pct") is not None:
        lines.append(f"Earnings growth {g['earnings_growth_pct']:+.1f}% YoY")
    if ins.get("net_buy_signal"):
        side = "buying" if ins["net_buy_signal"] > 0 else "selling"
        lines.append(f"Net insider {side} ({ins.get('buy_count',0)}B/{ins.get('sell_count',0)}S)")
    if sh.get("short_pct_float") is not None and sh["short_pct_float"] >= 10:
        lines.append(f"High short interest {sh['short_pct_float']:.1f}% of float (squeeze potential)")
    if nw.get("news_7d"):
        lines.append(f"{nw['news_7d']} news items in last 7d (Finnhub)")
    # Finviz supplemental
    fv = cand.get("fundamental", {}).get("finviz", {})
    if fv.get("forward_pe") is not None:
        lines.append(f"Forward P/E {fv['forward_pe']:.1f}")
    if fv.get("eps_growth_next_year_pct") is not None:
        lines.append(f"EPS growth next year {fv['eps_growth_next_year_pct']:+.1f}%")
    if fv.get("debt_equity") is not None:
        lines.append(f"Debt/Equity {fv['debt_equity']:.2f}")
    if fv.get("perf_week_pct") is not None:
        lines.append(f"1-week performance {fv['perf_week_pct']:+.1f}%")
    if fv.get("perf_month_pct") is not None:
        lines.append(f"1-month performance {fv['perf_month_pct']:+.1f}%")
    # EDGAR insider confirmation
    ed = cand.get("fundamental", {}).get("edgar_insider", {})
    if ed.get("form4_total", 0) >= 3:
        side = "buying" if ed.get("form4_buys", 0) > ed.get("form4_sells", 0) else "selling"
        lines.append(f"SEC Form 4 filings (90d): {ed['form4_buys']}B/{ed['form4_sells']}S — insiders {side}")
    # RSS news volume
    rss = cand.get("fundamental", {}).get("rss_news", {})
    if rss.get("rss_news_7d", 0) > 0:
        lines.append(f"{rss['rss_news_7d']} mentions across CNBC/MarketWatch/Benzinga (7d)")
    return lines


def _structured_summary(cand: dict) -> str:
    """Bullet fallback used when the LLM is dormant."""
    lines = _facts(cand)
    if not lines:
        return "Insufficient fundamental data for a thesis."
    return "\n".join(f"• {ln}" for ln in lines)


def synthesize(cand: dict) -> str:
    """Return a swing thesis paragraph (LLM) or structured bullets (dormant)."""
    if not available():
        return _structured_summary(cand)

    ticker = cand.get("ticker", "?")
    facts = _facts(cand)
    if not facts:
        return _structured_summary(cand)

    prompt = (
        f"You are a swing-trading analyst. Write a tight 2-3 sentence thesis for "
        f"{ticker} (3-15 day hold) from these facts. State the bull case, the key "
        f"catalyst, and the main risk. Refer to momentum/trend qualitatively — do "
        f"NOT cite raw indicator values like RSI numbers. No preamble, no "
        f"disclaimers, no bullet points — just the thesis.\n\nFacts:\n"
        + "\n".join(f"- {x}" for x in facts)
    )
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        return text.strip() or _structured_summary(cand)
    except Exception as e:
        print(f"[swing] narrative synthesis failed ({e}) — falling back to bullets")
        return _structured_summary(cand)
