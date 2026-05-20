import json
import re
import time
from datetime import datetime

import anthropic
import streamlit as st

st.set_page_config(
    page_title="XAU/USD Live Analysis | IC Markets",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

try:
    from streamlit_autorefresh import st_autorefresh as _autorefresh
except ImportError:
    _autorefresh = None

REFRESH_INTERVAL = 30 * 60  # seconds

PROMPT = """You are a professional gold (XAUUSD) trading analyst for IC Markets. \
Generate comprehensive real-time analysis. Use web search for current price and news.

Return ONLY valid JSON (no markdown, no backticks) in this exact structure:
{
  "timestamp": "2026-05-20T16:30:00Z",
  "currentPrice": 4485.50,
  "priceChange": -12.30,
  "trend": "BEARISH",
  "timeframes": {
    "daily": "Strong bearish, below all MAs",
    "h4": "Downtrend intact, testing support",
    "h1": "Consolidating near lows",
    "m15": "Short-term bounce possible"
  },
  "keyLevels": {
    "resistance": [4510, 4530, 4566, 4600],
    "support": [4476, 4464, 4450, 4423]
  },
  "fvg": [
    {"zone": "4520-4530", "type": "bearish", "priority": 1},
    {"zone": "4642-4667", "type": "bearish", "priority": 2}
  ],
  "supplyDemand": {
    "supply": [
      {"zone": "4520-4566", "strength": "strong"},
      {"zone": "4600-4650", "strength": "medium"}
    ],
    "demand": [
      {"zone": "4464-4480", "strength": "medium"},
      {"zone": "4420-4450", "strength": "strong"}
    ]
  },
  "smartMoney": {
    "liquidityZones": [
      "BSL at 4600 (buy-side liquidity grab expected)",
      "SSL at 4450 swept"
    ],
    "orderBlocks": [
      "Bearish OB: 4520-4566 (fresh supply)",
      "Bullish OB: 4420-4450 (extreme demand)"
    ]
  },
  "news": [
    {
      "event": "FOMC Minutes",
      "time": "22:00 Dubai",
      "impact": "high",
      "expected": "Hawkish tone likely, USD strength"
    }
  ],
  "entrySetups": [
    {
      "type": "SHORT",
      "confidence": 85,
      "entry": "4520-4530",
      "stop": 4545,
      "targets": [4476, 4464, 4450],
      "reason": "Bounce into resistance + FVG + supply OB confluence",
      "timeframe": "2-4 hours"
    }
  ],
  "movementExpectation": {
    "direction": "DOWN",
    "targetRange": "4450-4464",
    "timeframe": "4-6 hours",
    "probability": 75
  }
}

Return ONLY the JSON, nothing else."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _confidence_color(conf: int) -> str:
    if conf >= 80:
        return "#4ade80"
    if conf >= 65:
        return "#facc15"
    return "#fb923c"


def _impact_color(impact: str) -> str:
    return {"high": "#f87171", "medium": "#facc15"}.get(impact.lower(), "#4ade80")


def fetch_analysis(api_key: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": PROMPT}],
    )
    text = "".join(
        block.text for block in response.content if hasattr(block, "text")
    )
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("No JSON found in Claude response")
    return json.loads(m.group())


# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [("analysis", None), ("last_fetch", None), ("error", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Auto-refresh every 60 s (updates countdown + triggers 30-min re-fetch) ───
if _autorefresh:
    _autorefresh(interval=60_000, key="ticker")

# ── API key ───────────────────────────────────────────────────────────────────
try:
    api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
except Exception:
    api_key = ""

if not api_key:
    with st.sidebar:
        st.markdown("### API Key")
        api_key = st.text_input(
            "Anthropic API Key",
            type="password",
            placeholder="sk-ant-...",
            key="api_key_input",
        )

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {
    background-color: #0a0e1a !important;
    font-family: 'JetBrains Mono', monospace !important;
    color: #e5e7eb !important;
}
[data-testid="stHeader"], [data-testid="stToolbar"] { background: transparent !important; }
#MainMenu, footer { visibility: hidden; }
section.main > div { max-width: 100% !important; padding: 1.5rem 2rem !important; }

@keyframes glowPulse {
    0%, 100% { box-shadow: 0 0 18px rgba(34,211,238,.28); }
    50%       { box-shadow: 0 0 38px rgba(34,211,238,.58); }
}

.card { border-radius: 12px; padding: 20px; margin-bottom: 8px; }
.card-cyan   { background: linear-gradient(135deg,rgba(8,145,178,.14),rgba(7,89,133,.14));
               border: 1px solid rgba(34,211,238,.4); animation: glowPulse 2s ease-in-out infinite; }
.card-purple { background: linear-gradient(135deg,rgba(88,28,135,.18),rgba(112,26,117,.18));
               border: 1px solid rgba(168,85,247,.4); }
.card-green  { background: linear-gradient(135deg,rgba(6,78,59,.18),rgba(6,95,70,.18));
               border: 1px solid rgba(52,211,153,.4); }
.card-orange { background: linear-gradient(135deg,rgba(124,45,18,.18),rgba(127,29,29,.18));
               border: 1px solid rgba(251,146,60,.4); }

.lbl { color:#6b7280; font-size:.68rem; letter-spacing:2px; margin-bottom:6px; }
.sh  { color:#22d3ee; font-size:.95rem; font-weight:700; letter-spacing:2px; margin-bottom:10px; }

.setup-long  { background:rgba(6,78,59,.22); border:2px solid rgba(52,211,153,.5);
               border-radius:10px; padding:16px; }
.setup-short { background:rgba(127,29,29,.22); border:2px solid rgba(239,68,68,.5);
               border-radius:10px; padding:16px; }

.tf-card { background:rgba(17,24,39,.7); border:1px solid rgba(75,85,99,.5);
           border-radius:8px; padding:14px; }

.lvl-row  { background:rgba(17,24,39,.55); border-radius:6px; padding:8px 12px;
            margin-bottom:5px; display:flex; justify-content:space-between; align-items:center; }
.zone-item { border-radius:8px; padding:10px 14px; margin-bottom:7px; }
.supply-zone { background:rgba(127,29,29,.2); }
.demand-zone { background:rgba(6,78,59,.2); }
.fvg-bull    { background:rgba(6,78,59,.25); }
.fvg-bear    { background:rgba(127,29,29,.25); }
.sm-item     { background:rgba(120,60,10,.22); border-radius:6px; padding:10px 14px; margin-bottom:6px; }
.news-row    { background:rgba(120,90,10,.18); border-radius:8px; padding:12px 16px;
               margin-bottom:7px; display:flex; justify-content:space-between; align-items:center; }

.error-box { background:rgba(127,29,29,.22); border:1px solid rgba(239,68,68,.5);
             border-radius:8px; padding:14px; color:#f87171; margin-bottom:16px; }
.divider   { border:none; border-top:1px solid rgba(34,211,238,.15); margin:20px 0; }

.stButton > button {
    background:#0891b2 !important; color:#fff !important; border:none !important;
    border-radius:8px !important; padding:10px 24px !important;
    font-family:'JetBrains Mono',monospace !important; font-weight:700 !important;
    letter-spacing:1px !important; transition:background .2s !important;
}
.stButton > button:hover { background:#06b6d4 !important; }
</style>
""", unsafe_allow_html=True)


# ── Fetch helpers ─────────────────────────────────────────────────────────────
def _needs_refresh() -> bool:
    return (
        st.session_state.last_fetch is None
        or (time.time() - st.session_state.last_fetch) >= REFRESH_INTERVAL
    )


def _do_fetch():
    try:
        st.session_state.analysis = fetch_analysis(api_key)
        st.session_state.last_fetch = time.time()
        st.session_state.error = None
    except Exception as exc:
        st.session_state.error = str(exc)


if api_key and _needs_refresh():
    with st.spinner("Fetching live data & generating analysis..."):
        _do_fetch()
elif not api_key and st.session_state.analysis is None:
    st.session_state.error = (
        "No API key. Add ANTHROPIC_API_KEY to .streamlit/secrets.toml "
        "or enter it in the sidebar."
    )


# ── Header ────────────────────────────────────────────────────────────────────
col_h, col_ctrl = st.columns([3, 1])

with col_h:
    st.markdown("""
    <h1 style="color:#22d3ee;letter-spacing:4px;font-size:1.9rem;margin:0;
               font-family:'JetBrains Mono',monospace;font-weight:700;">
        XAU/USD LIVE ANALYSIS
    </h1>
    <div style="color:#6b7280;font-size:.78rem;margin-top:4px;">
        IC Markets | Multi-Source Intelligence
    </div>
    """, unsafe_allow_html=True)

with col_ctrl:
    elapsed = int(time.time() - st.session_state.last_fetch) if st.session_state.last_fetch else REFRESH_INTERVAL
    secs_left = max(0, REFRESH_INTERVAL - elapsed)
    m, s = divmod(secs_left, 60)
    st.markdown(f"""
    <div style="text-align:right;margin-bottom:6px;">
        <div style="color:#6b7280;font-size:.62rem;letter-spacing:2px;">NEXT UPDATE</div>
        <div style="color:#22d3ee;font-size:1.5rem;font-weight:700;">{m}:{s:02d}</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("↺  Refresh Now", use_container_width=True):
        st.session_state.last_fetch = None
        st.rerun()

if st.session_state.last_fetch:
    ts = datetime.fromtimestamp(st.session_state.last_fetch).strftime("%Y-%m-%d %H:%M:%S")
    st.markdown(
        f'<div style="color:#4b5563;font-size:.72rem;margin-top:-6px;">Last Updated: {ts}</div>',
        unsafe_allow_html=True,
    )

st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ── Error banner ──────────────────────────────────────────────────────────────
if st.session_state.error:
    st.markdown(f'<div class="error-box">⚠ {st.session_state.error}</div>', unsafe_allow_html=True)

# ── Dashboard ─────────────────────────────────────────────────────────────────
a = st.session_state.analysis
if a:
    pc = a.get("priceChange", 0)
    pc_arrow = "▲" if pc >= 0 else "▼"
    pc_color = "#4ade80" if pc >= 0 else "#f87171"
    trend = a.get("trend", "—")
    t_color = "#4ade80" if trend == "BULLISH" else "#f87171" if trend == "BEARISH" else "#facc15"
    me = a.get("movementExpectation", {})
    d_color = "#4ade80" if me.get("direction") == "UP" else "#f87171"

    # Price overview
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="card card-cyan">
            <div class="lbl">CURRENT PRICE</div>
            <div style="color:#22d3ee;font-size:2rem;font-weight:700;">${a.get('currentPrice', 0):.2f}</div>
            <div style="color:{pc_color};margin-top:6px;font-size:.9rem;">{pc_arrow} ${abs(pc):.2f}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        t_icon = "▲" if trend == "BULLISH" else "▼" if trend == "BEARISH" else "—"
        st.markdown(f"""
        <div class="card card-purple">
            <div class="lbl">MARKET TREND</div>
            <div style="color:{t_color};font-size:1.5rem;font-weight:700;margin-top:8px;">{t_icon} {trend}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="card card-green">
            <div class="lbl">DIRECTION</div>
            <div style="color:{d_color};font-size:1.5rem;font-weight:700;margin-top:8px;">{me.get('direction', '—')}</div>
            <div style="color:#9ca3af;font-size:.78rem;margin-top:4px;">{me.get('probability', 0)}% confidence</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="card card-orange">
            <div class="lbl">TARGET</div>
            <div style="color:#fb923c;font-size:1.1rem;font-weight:700;margin-top:8px;">{me.get('targetRange', '—')}</div>
            <div style="color:#9ca3af;font-size:.78rem;margin-top:4px;">{me.get('timeframe', '—')}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)

    # Entry setups
    setups = a.get("entrySetups", [])
    if setups:
        st.markdown("""
        <div style="background:rgba(8,145,178,.07);border:2px solid rgba(34,211,238,.38);
             border-radius:12px;padding:20px 20px 8px;
             animation:glowPulse 2s ease-in-out infinite;margin-bottom:16px;">
            <div class="sh">◎ HIGH CONFIDENCE SETUPS</div>""",
            unsafe_allow_html=True,
        )
        s_cols = st.columns(min(len(setups), 3))
        for i, s in enumerate(setups[:3]):
            with s_cols[i]:
                stype = s.get("type", "")
                cls = "setup-long" if stype == "LONG" else "setup-short"
                tc = "#4ade80" if stype == "LONG" else "#f87171"
                conf = s.get("confidence", 0)
                tp_html = "".join(
                    f"<div>TP{j+1}: ${t}</div>"
                    for j, t in enumerate(s.get("targets", []))
                )
                st.markdown(f"""
                <div class="{cls}">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                        <span style="color:{tc};font-size:1.3rem;font-weight:700;">{stype}</span>
                        <span style="color:{_confidence_color(conf)};font-size:1.7rem;font-weight:700;">{conf}%</span>
                    </div>
                    <div style="font-size:.82rem;line-height:1.9;">
                        <div><span style="color:#6b7280;">Entry:</span>
                             <span style="color:#22d3ee;font-weight:700;"> {s.get('entry', '—')}</span></div>
                        <div><span style="color:#6b7280;">Stop:</span>
                             <span style="color:#f87171;font-weight:700;"> ${s.get('stop', '—')}</span></div>
                        <div style="color:#6b7280;">Targets:</div>
                        <div style="color:#4ade80;font-weight:700;padding-left:8px;">{tp_html}</div>
                    </div>
                    <div style="border-top:1px solid rgba(255,255,255,.1);margin-top:10px;padding-top:8px;">
                        <div style="color:#9ca3af;font-size:.72rem;">{s.get('reason', '')}</div>
                        <div style="color:#6b7280;font-size:.68rem;margin-top:3px;">⏱ {s.get('timeframe', '')}</div>
                    </div>
                </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Multi-timeframe
    tfs = a.get("timeframes", {})
    if tfs:
        st.markdown("""
        <div style="background:rgba(17,24,39,.55);border:1px solid rgba(75,85,99,.35);
             border-radius:12px;padding:20px 20px 8px;margin-bottom:16px;">
            <div class="sh">MULTI-TIMEFRAME</div>""",
            unsafe_allow_html=True,
        )
        tf_cols = st.columns(len(tfs))
        for i, (label, desc) in enumerate(tfs.items()):
            with tf_cols[i]:
                st.markdown(f"""
                <div class="tf-card">
                    <div style="color:#6b7280;font-size:.62rem;letter-spacing:2px;margin-bottom:7px;">{label.upper()}</div>
                    <div style="color:#d1d5db;font-size:.8rem;line-height:1.5;">{desc}</div>
                </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Key levels
    kl = a.get("keyLevels", {})
    rl, sl = st.columns(2)
    with rl:
        rows = "".join(
            f'<div class="lvl-row"><span style="color:#6b7280;">R{i+1}</span>'
            f'<span style="color:#f87171;font-weight:700;">${lvl}</span></div>'
            for i, lvl in enumerate(kl.get("resistance", []))
        )
        st.markdown(f"""
        <div style="background:rgba(127,29,29,.13);border:1px solid rgba(239,68,68,.28);
             border-radius:12px;padding:20px;margin-bottom:14px;">
            <div style="color:#f87171;font-size:.9rem;font-weight:700;letter-spacing:2px;margin-bottom:10px;">RESISTANCE</div>
            {rows}</div>""", unsafe_allow_html=True)
    with sl:
        rows = "".join(
            f'<div class="lvl-row"><span style="color:#6b7280;">S{i+1}</span>'
            f'<span style="color:#4ade80;font-weight:700;">${lvl}</span></div>'
            for i, lvl in enumerate(kl.get("support", []))
        )
        st.markdown(f"""
        <div style="background:rgba(6,78,59,.13);border:1px solid rgba(52,211,153,.28);
             border-radius:12px;padding:20px;margin-bottom:14px;">
            <div style="color:#4ade80;font-size:.9rem;font-weight:700;letter-spacing:2px;margin-bottom:10px;">SUPPORT</div>
            {rows}</div>""", unsafe_allow_html=True)

    # Fair Value Gaps
    fvgs = a.get("fvg", [])
    if fvgs:
        fvg_html = "".join(f"""
        <div class="zone-item {'fvg-bull' if g.get('type') == 'bullish' else 'fvg-bear'}"
             style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:{'#4ade80' if g.get('type') == 'bullish' else '#f87171'};font-weight:700;">
                {g.get('type', '').upper()}
            </span>
            <span style="color:#22d3ee;">{g.get('zone', '')}</span>
            <span style="color:#6b7280;font-size:.72rem;">P{g.get('priority', '')}</span>
        </div>""" for g in fvgs)
        st.markdown(f"""
        <div style="background:rgba(88,28,135,.13);border:1px solid rgba(168,85,247,.28);
             border-radius:12px;padding:20px;margin-bottom:14px;">
            <div style="color:#c084fc;font-size:.9rem;font-weight:700;letter-spacing:2px;margin-bottom:10px;">
                FAIR VALUE GAPS
            </div>
            {fvg_html}</div>""", unsafe_allow_html=True)

    # Supply / Demand
    sd = a.get("supplyDemand", {})
    sc, dc = st.columns(2)
    with sc:
        rows = "".join(
            f'<div class="zone-item supply-zone">'
            f'<div style="color:#22d3ee;">{z.get("zone","")}</div>'
            f'<div style="color:#9ca3af;font-size:.72rem;">Strength: {z.get("strength","")}</div></div>'
            for z in sd.get("supply", [])
        )
        st.markdown(f"""
        <div style="background:rgba(17,24,39,.5);border:1px solid rgba(239,68,68,.28);
             border-radius:12px;padding:20px;margin-bottom:14px;">
            <div style="color:#f87171;font-size:.9rem;font-weight:700;letter-spacing:2px;margin-bottom:10px;">SUPPLY ZONES</div>
            {rows}</div>""", unsafe_allow_html=True)
    with dc:
        rows = "".join(
            f'<div class="zone-item demand-zone">'
            f'<div style="color:#22d3ee;">{z.get("zone","")}</div>'
            f'<div style="color:#9ca3af;font-size:.72rem;">Strength: {z.get("strength","")}</div></div>'
            for z in sd.get("demand", [])
        )
        st.markdown(f"""
        <div style="background:rgba(17,24,39,.5);border:1px solid rgba(52,211,153,.28);
             border-radius:12px;padding:20px;margin-bottom:14px;">
            <div style="color:#4ade80;font-size:.9rem;font-weight:700;letter-spacing:2px;margin-bottom:10px;">DEMAND ZONES</div>
            {rows}</div>""", unsafe_allow_html=True)

    # Smart Money
    sm = a.get("smartMoney", {})
    lz_html = "".join(
        f'<div class="sm-item"><span style="color:#d1d5db;font-size:.82rem;">{z}</span></div>'
        for z in sm.get("liquidityZones", [])
    )
    ob_html = "".join(
        f'<div class="sm-item"><span style="color:#d1d5db;font-size:.82rem;">{b}</span></div>'
        for b in sm.get("orderBlocks", [])
    )
    lc, oc = st.columns(2)
    with lc:
        st.markdown(f"""
        <div style="background:rgba(120,53,15,.13);border:1px solid rgba(251,146,60,.28);
             border-radius:12px;padding:20px;margin-bottom:14px;">
            <div style="color:#fb923c;font-size:.9rem;font-weight:700;letter-spacing:2px;margin-bottom:6px;">SMART MONEY</div>
            <div style="color:#9ca3af;font-size:.62rem;letter-spacing:2px;margin-bottom:9px;">LIQUIDITY ZONES</div>
            {lz_html}</div>""", unsafe_allow_html=True)
    with oc:
        st.markdown(f"""
        <div style="background:rgba(120,53,15,.13);border:1px solid rgba(251,146,60,.28);
             border-radius:12px;padding:20px;margin-bottom:14px;">
            <div style="color:#fb923c;font-size:.9rem;font-weight:700;letter-spacing:2px;margin-bottom:6px;">ORDER BLOCKS</div>
            <div style="color:#9ca3af;font-size:.62rem;letter-spacing:2px;margin-bottom:9px;">INSTITUTIONAL LEVELS</div>
            {ob_html}</div>""", unsafe_allow_html=True)

    # News
    news = a.get("news", [])
    if news:
        n_html = "".join(f"""
        <div class="news-row">
            <div style="flex:1;">
                <div style="color:#fbbf24;font-weight:700;">{ev.get('event', '')}</div>
                <div style="color:#9ca3af;font-size:.78rem;margin-top:3px;">{ev.get('expected', '')}</div>
            </div>
            <div style="text-align:right;margin-left:14px;">
                <div style="color:#6b7280;font-size:.78rem;">{ev.get('time', '')}</div>
                <div style="color:{_impact_color(ev.get('impact', 'low'))};font-size:.68rem;
                     font-weight:700;margin-top:3px;">{ev.get('impact', '').upper()}</div>
            </div>
        </div>""" for ev in news)
        st.markdown(f"""
        <div style="background:rgba(113,63,18,.13);border:1px solid rgba(234,179,8,.28);
             border-radius:12px;padding:20px;margin-bottom:14px;">
            <div style="color:#fbbf24;font-size:.9rem;font-weight:700;letter-spacing:2px;margin-bottom:10px;">
                ⏰ NEWS & EVENTS
            </div>
            {n_html}</div>""", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<hr class="divider">
<div style="color:#4b5563;font-size:.72rem;text-align:center;padding-bottom:1rem;">
    <div>Automated Analysis | Updates Every 30 Minutes</div>
    <div style="margin-top:3px;">Multi-Source: TradingView • IC Markets • News APIs • Economic Calendar</div>
    <div style="margin-top:3px;color:#a16207;">⚠ Educational purposes. Verify before trading.</div>
</div>
""", unsafe_allow_html=True)
