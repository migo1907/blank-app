"""
TradingAgents second-layer filter for swing candidates.

Runs a multi-agent bull/bear debate (TauricResearch/TradingAgents v0.3.0)
on the top swing candidates every 3 days (Mon/Thu 17:30 ET).
Enriches swing_candidates.json with agent conviction scores and summaries.

Uses Anthropic Claude natively:
  quick_think_llm  → claude-haiku-4-5-20251001  (fast analyst tasks)
  deep_think_llm   → claude-sonnet-4-6           (risk manager synthesis)

Results are ephemeral — stored in /tmp/tradingagents/ (Railway ephemeral FS).
Enriched swing_candidates.json is persisted to the data branch via db.py.

Design: TradingAgents is imported only if available. Missing package returns
a graceful no-op so the rest of the system is never blocked.
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_RESULTS_DIR = Path("/tmp/tradingagents")
_MAX_CANDIDATES = 15   # only run on top N to limit API spend
_HAIKU  = "claude-haiku-4-5-20251001"
_SONNET = "claude-sonnet-4-6"


def _ta_available() -> bool:
    """Return True if tradingagents package is importable."""
    try:
        import tradingagents  # noqa: F401
        return True
    except ImportError:
        return False


def _build_graph():
    """Build a TradingAgentsGraph configured for Anthropic Claude."""
    from tradingagents.graph.trading_state_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG

    cfg = {**DEFAULT_CONFIG}
    cfg["llm_provider"]     = "anthropic"
    cfg["backend_url"]      = ""          # not used for anthropic
    cfg["quick_think_llm"]  = _HAIKU
    cfg["deep_think_llm"]   = _SONNET
    cfg["max_debate_rounds"] = 1          # one round — cost-efficient for screening
    cfg["online_tools"]     = False       # use our own data; avoid external search deps
    cfg["results_dir"]      = str(_RESULTS_DIR)

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return TradingAgentsGraph(debug=False, config=cfg)


def _run_one(graph, ticker: str, date_str: str) -> dict:
    """
    Run the bull/bear debate for one ticker on a given date.
    Returns a dict with keys: recommendation, confidence, bull_summary, bear_summary.
    """
    try:
        state, decision = graph.propagate(ticker, date_str)

        # TradingAgents decision is a dict with 'action' and 'confidence'
        action     = str(decision.get("action", "HOLD")).upper()
        confidence = float(decision.get("confidence", 0.5))

        # Extract analyst summaries from state messages when present
        bull_summary = ""
        bear_summary = ""
        try:
            msgs = state.get("messages", [])
            for m in msgs:
                content = getattr(m, "content", "") or ""
                role    = getattr(m, "name", "") or getattr(m, "role", "") or ""
                if "bull" in role.lower() and not bull_summary:
                    bull_summary = content[:300]
                elif "bear" in role.lower() and not bear_summary:
                    bear_summary = content[:300]
        except Exception:
            pass

        return {
            "recommendation": action,
            "agent_confidence": round(confidence, 3),
            "bull_summary":    bull_summary,
            "bear_summary":    bear_summary,
            "agent_updated":   datetime.now(timezone.utc).isoformat(),
            "agent_error":     None,
        }
    except Exception as e:
        return {
            "recommendation":  "HOLD",
            "agent_confidence": 0.5,
            "bull_summary":    "",
            "bear_summary":    "",
            "agent_updated":   datetime.now(timezone.utc).isoformat(),
            "agent_error":     str(e)[:200],
        }


def run_agents_on_candidates(
    candidates: list[dict],
    max_candidates: int = _MAX_CANDIDATES,
) -> list[dict]:
    """
    Enrich the top N swing candidates with TradingAgents bull/bear debate scores.
    Returns the same candidate list with 'agent' key added to each dict.
    If TradingAgents is unavailable, returns candidates unchanged.
    """
    if not _ta_available():
        print("[ta_layer] tradingagents not installed — skipping agent layer")
        return candidates

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    top = candidates[:max_candidates]
    rest = candidates[max_candidates:]

    # Build graph once — reuse across all tickers (one session)
    try:
        graph = _build_graph()
    except Exception as e:
        print(f"[ta_layer] graph build failed: {e}")
        return candidates

    enriched = []
    for c in top:
        ticker = c.get("ticker", "")
        if not ticker:
            enriched.append(c)
            continue

        print(f"[ta_layer] running agent debate on {ticker} …")
        agent_result = _run_one(graph, ticker, date_str)
        c = {**c, "agent": agent_result}
        enriched.append(c)
        _cache_result(ticker, date_str, agent_result)

    return enriched + rest


def _cache_result(ticker: str, date_str: str, result: dict) -> None:
    """Persist individual ticker result to /tmp for debugging."""
    try:
        _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = _RESULTS_DIR / f"{ticker}_{date_str}.json"
        path.write_text(json.dumps(result, indent=2))
    except Exception:
        pass


def format_agent_block(candidate: dict) -> str:
    """
    Return a 2-line Telegram HTML snippet summarising the agent debate for one ticker.
    Safe to call even if 'agent' key is missing.
    """
    agent = candidate.get("agent")
    if not agent:
        return ""

    rec   = agent.get("recommendation", "HOLD")
    conf  = agent.get("agent_confidence", 0.5)
    err   = agent.get("agent_error")

    if err:
        return f"<i>🤖 Agent: error — {err[:80]}</i>\n"

    emoji = "🟢" if rec == "BUY" else "🔴" if rec == "SELL" else "⚪"
    line  = f"{emoji} <b>Agent:</b> {rec} ({conf*100:.0f}% confidence)\n"

    bull = agent.get("bull_summary", "")
    bear = agent.get("bear_summary", "")
    if bull:
        line += f"  📈 <i>{bull[:120]}</i>\n"
    if bear:
        line += f"  📉 <i>{bear[:120]}</i>\n"

    return line
