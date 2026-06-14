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
    adv, ec = f.get("advanced", {}), f.get("earnings_call", {})
    lines = []

    arch = f.get("archetype")
    if arch and arch != "default":
        lines.append(f"Business model: {arch.replace('_', '-')} (scored on the metrics that drive this type)")
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
    # Valuation
    if adv.get("pe_ratio") is not None:
        lines.append(f"Trailing P/E {adv['pe_ratio']:.1f}")
    if adv.get("forward_pe") is not None:
        lines.append(f"Forward P/E {adv['forward_pe']:.1f}")
    # Advanced composite fundamental scores
    if adv.get("roe_pct") is not None:
        lines.append(f"Return on equity {adv['roe_pct']:+.1f}%")
    if adv.get("fcf_yield_pct") is not None:
        lines.append(f"Free-cash-flow yield {adv['fcf_yield_pct']:+.1f}%")
    if adv.get("rule_of_40") is not None:
        lines.append(f"Rule of 40 score {adv['rule_of_40']:.0f} ({'passes' if adv['rule_of_40'] >= 40 else 'below'} 40)")
    if adv.get("peg") is not None:
        lines.append(f"PEG ratio {adv['peg']:.2f} ({'cheap' if adv['peg'] < 1 else 'fair' if adv['peg'] < 2 else 'rich'} vs growth)")
    if adv.get("price_to_book") is not None:
        lines.append(f"Price/Book {adv['price_to_book']:.2f}")
    if adv.get("piotroski_f") is not None:
        lines.append(f"Piotroski F-Score {adv['piotroski_f']}/9 ({'strong' if adv['piotroski_f'] >= 7 else 'weak' if adv['piotroski_f'] <= 2 else 'mid'} quality)")
    if adv.get("altman_z") is not None:
        zone = "safe" if adv["altman_z"] > 2.6 else "distress" if adv["altman_z"] < 1.8 else "grey"
        lines.append(f"Altman Z-Score {adv['altman_z']:.2f} ({zone} zone)")
    # Just-reported earnings event (conference-call monitor)
    if ec.get("reported"):
        bits = []
        if ec.get("surprise_pct") is not None:
            bits.append(f"EPS {ec['surprise_pct']:+.1f}% vs est")
        if ec.get("rev_beat_pct") is not None:
            bits.append(f"revenue {ec['rev_beat_pct']:+.1f}% vs est")
        if ec.get("guidance") and ec["guidance"] != "none":
            bits.append(f"guidance {ec['guidance']}")
        if ec.get("buyback"):
            bits.append("new buyback")
        if ec.get("dividend_raise"):
            bits.append("dividend raised")
        when = f"{ec['days_ago']}d ago" if ec.get("days_ago") is not None else "recently"
        if bits:
            lines.append(f"Just reported ({when}): " + ", ".join(bits))
    # EDGAR insider activity
    ed = cand.get("fundamental", {}).get("edgar_insider", {})
    if ed.get("form4_count", 0) >= 3:
        lines.append(f"{ed['form4_count']} SEC Form 4 insider filings in last 90d")
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
        f"You are an institutional equity analyst. Write a sharp, professional "
        f"swing thesis for {ticker} (3-15 day hold) — MAX 2 sentences, ~45 words. "
        f"Lead with the bull case and cite the hard fundamental figures that back "
        f"it (analyst PT upside %, growth %, earnings surprise %, valuation, "
        f"insider/short data — use the actual numbers from the facts). Close with "
        f"the single biggest risk. Refer to price momentum/trend qualitatively — "
        f"do NOT cite technical indicator values (no RSI numbers). No preamble, no "
        f"hedging, no disclaimers, no bullet points — just the thesis prose.\n\n"
        f"Facts:\n"
        + "\n".join(f"- {x}" for x in facts)
    )
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=180,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        return text.strip() or _structured_summary(cand)
    except Exception as e:
        print(f"[swing] narrative synthesis failed ({e}) — falling back to bullets")
        return _structured_summary(cand)
