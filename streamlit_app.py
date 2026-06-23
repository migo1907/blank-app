"""
Migo Sniper Pro — Dashboard
Full system view: health, signals, ML models, swing, options, macro.
"""
import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL = "https://blank-app-production-a8bd.up.railway.app"
SECRET   = "gold2026"

st.set_page_config(
    page_title="Migo Sniper Pro",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get(path: str, params: dict | None = None) -> dict | list | None:
    try:
        p = {"secret": SECRET, **(params or {})}
        r = requests.get(f"{BASE_URL}{path}", params=p, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.warning(f"API error {path}: {e}")
        return None


def _badge(val: bool, yes="✅", no="❌") -> str:
    return yes if val else no


def _age(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        mins = int((datetime.now(timezone.utc) - dt).total_seconds() / 60)
        if mins < 60:
            return f"{mins}m ago"
        return f"{mins//60}h {mins%60}m ago"
    except Exception:
        return iso[:16]


def _certainty_emoji(c: str) -> str:
    return {"HIGH": "🎯", "MODERATE": "〰️", "LOW": "❓"}.get(c, "—")


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🥇 Migo Sniper Pro — Dashboard")

col_refresh, col_ts = st.columns([1, 4])
with col_refresh:
    refresh = st.button("🔄 Refresh", use_container_width=True)
with col_ts:
    st.caption(f"Last loaded: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tabs = st.tabs([
    "📡 System Health",
    "🔮 Signals",
    "🤖 ML Models",
    "📈 Swing Brain",
    "🎰 Options",
    "🌍 Macro & Regime",
])

# ═══════════════════════════════════════════════════════════
# TAB 1 — SYSTEM HEALTH
# ═══════════════════════════════════════════════════════════
with tabs[0]:
    health = _get("/health")
    if health:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status",    health.get("status", "—").upper())
        c2.metric("Version",   health.get("version", "—"))
        c3.metric("Scheduler", health.get("scheduler", "—").upper())
        ml = health.get("ml", {})
        trained_pools = sum(
            1 for p in ml.get("pools", {}).values()
            if p.get("rf_trained") or p.get("gbm_trained")
        )
        c4.metric("Trained Pools", f"{trained_pools}/{len(ml.get('pools', {}))}")

        st.subheader("Pool ML Status")
        pools = ml.get("pools", {})
        if pools:
            rows = []
            for pool, pd_ in pools.items():
                rows.append({
                    "Pool":        pool,
                    "RF":          _badge(pd_.get("rf_trained")),
                    "GBM":         _badge(pd_.get("gbm_trained")),
                    "Threshold":   f"{pd_.get('threshold', 0):.2f}",
                    "Retrains":    pd_.get("retrain_count", 0),
                    "Last Retrain": _age(pd_.get("last_retrain")),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.subheader("System Flags")
        directive = health.get("directive", {})
        phases    = directive.get("improvement_phases", {})
        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("Joint Gold",   _badge(ml.get("joint_gold_trained")))
        fc2.metric("Joint Stocks", _badge(ml.get("joint_stocks_trained")))
        fc3.metric("Optuna",       _badge(ml.get("optuna_available")))
        fc4, fc5, fc6 = st.columns(3)
        fc4.metric("SHAP",         _badge(ml.get("shap_available")))
        fc5.metric("Phase 1",      _badge(phases.get("phase1_active")))
        fc6.metric("Phase 4 Joint",_badge(phases.get("phase4_joint")))
    else:
        st.error("Could not reach backend.")

# ═══════════════════════════════════════════════════════════
# TAB 2 — SIGNALS (per-pool dashboard)
# ═══════════════════════════════════════════════════════════
with tabs[1]:
    POOLS = [
        "XAUUSD_2M", "XAUUSD_5M", "XAUUSD_15M", "XAUUSD_30M", "XAUUSD_1H",
        "STOCKS_MOMENTUM_15M", "STOCKS_MOMENTUM_30M",
        "STOCKS_QUALITY_15M",  "STOCKS_QUALITY_30M",
        "STOCKS_INDEX_15M",    "STOCKS_INDEX_30M",
        "STOCKS_QQQ_15M",      "STOCKS_QQQ_30M",
        "STOCKS_SPX500_15M",   "STOCKS_SPX500_30M",
    ]

    selected_pool = st.selectbox("Pool", POOLS, index=0)
    dash = _get("/dashboard", {"pool": selected_pool})

    if dash:
        model_info = dash.get("model", {})
        rf_info    = dash.get("rf", {})

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Win Rate",     f"{model_info.get('win_rate', 0):.1f}%")
        mc2.metric("Total Trades", model_info.get("total_trades", 0))
        mc3.metric("RF Trained",   _badge(rf_info.get("trained")))
        mc4.metric("News Sentiment", f"{dash.get('news_sentiment', 0):+.3f}")

        c_feat, c_news = st.columns(2)
        with c_feat:
            st.subheader("Top KNN Features")
            top = model_info.get("top_features", [])
            if top:
                st.dataframe(
                    pd.DataFrame(top).rename(columns={"name": "Feature", "weight": "Weight"}),
                    use_container_width=True, hide_index=True
                )

        with c_news:
            st.subheader("RF Top Features")
            rf_top = rf_info.get("top_features", [])
            if rf_top:
                st.dataframe(
                    pd.DataFrame(rf_top).rename(columns={"name": "Feature", "importance": "Importance"}),
                    use_container_width=True, hide_index=True
                )

        st.subheader("Recent Trades")
        recent = dash.get("recent_trades", [])
        if recent:
            df = pd.DataFrame(recent)
            df["age"] = df["created_at"].apply(_age)
            df = df[["direction", "outcome", "age"]].rename(columns={
                "direction": "Dir", "outcome": "Result", "age": "When"
            })
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No recent trades for this pool.")

        vel = dash.get("news_velocity", {})
        evt = dash.get("high_impact_event", {})
        nc1, nc2 = st.columns(2)
        nc1.info(f"📰 News velocity: {vel.get('label', '—')} (×{vel.get('multiplier', 1):.1f})")
        if evt and evt.get("detected"):
            nc2.warning(f"⚡ High-impact event: urgency {evt.get('urgency', 0):.2f}")
        else:
            nc2.success("✅ No high-impact event detected")

# ═══════════════════════════════════════════════════════════
# TAB 3 — ML MODELS
# ═══════════════════════════════════════════════════════════
with tabs[2]:
    health2 = _get("/health")
    if health2:
        ml2   = health2.get("ml", {})
        pools = ml2.get("pools", {})

        st.subheader("All Pools — ML Quality")
        rows = []
        for pool, pd_ in pools.items():
            ci    = pd_.get("conformal_interval", [None, None])
            cert  = pd_.get("ml_certainty", "")
            rows.append({
                "Pool":           pool,
                "RF":             _badge(pd_.get("rf_trained")),
                "GBM":            _badge(pd_.get("gbm_trained")),
                "Threshold":      f"{pd_.get('threshold', 0):.2f}",
                "Certainty":      f"{_certainty_emoji(cert)} {cert}" if cert else "—",
                "Retrains":       pd_.get("retrain_count", 0),
                "Last Retrain":   _age(pd_.get("last_retrain")),
                "OOS Acc":        f"{pd_.get('oos_accuracy', 0)*100:.1f}%" if pd_.get("oos_accuracy") else "—",
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.subheader("Joint Models")
        jc1, jc2, jc3, jc4 = st.columns(4)
        jc1.metric("JointGoldGBM",   _badge(ml2.get("joint_gold_trained")))
        jc2.metric("JointStocksGBM", _badge(ml2.get("joint_stocks_trained")))
        jc3.metric("TabPFN",         _badge(ml2.get("tabpfn_available")))
        jc4.metric("LightGBM",       _badge(ml2.get("lgbm_available")))

        fi = _get("/feature-importance", {"pool": "XAUUSD_2M"})
        if fi:
            st.subheader("Feature Importance — XAUUSD_2M")
            rf_fi  = fi.get("rf",  {}).get("top_features", [])
            gbm_fi = fi.get("gbm", {}).get("top_features", [])
            fi_c1, fi_c2 = st.columns(2)
            with fi_c1:
                st.caption("RF")
                if rf_fi:
                    st.dataframe(pd.DataFrame(rf_fi), use_container_width=True, hide_index=True)
            with fi_c2:
                st.caption("GBM")
                if gbm_fi:
                    st.dataframe(pd.DataFrame(gbm_fi), use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════
# TAB 4 — SWING BRAIN
# ═══════════════════════════════════════════════════════════
with tabs[3]:
    swing_stats = _get("/swing/trades")
    if swing_stats:
        ss = swing_stats
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Open Positions",   ss.get("open", 0))
        sc2.metric("Closed Trades",    ss.get("closed", 0))
        sc3.metric("Win Rate",         f"{ss.get('win_rate', 0)*100:.1f}%")
        ready = ss.get("ready", False)
        sc4.metric("ML Ready",         "✅ YES" if ready else f"⏳ Need {50 - ss.get('closed', 0)} more")

    st.subheader("Swing Candidates")
    cands = _get("/swing/candidates")
    if cands and isinstance(cands, dict):
        candidate_list = cands.get("candidates", [])
        if candidate_list:
            rows = []
            for c in candidate_list[:20]:
                rows.append({
                    "Ticker":      c.get("ticker", ""),
                    "Score":       f"{c.get('combined_score', 0)*100:.0f}%",
                    "Conviction":  c.get("conviction", ""),
                    "Fundamental": f"{c.get('fundamental_score', 0)*100:.0f}%",
                    "Technical":   f"{c.get('technical_score', 0)*100:.0f}%",
                    "Entry":       f"${c.get('entry', 0):.2f}" if c.get("entry") else "—",
                    "TP":          f"${c.get('tp', 0):.2f}" if c.get("tp") else "—",
                    "SL":          f"${c.get('sl', 0):.2f}" if c.get("sl") else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # Show top candidate thesis
            top = candidate_list[0]
            if top.get("thesis"):
                st.subheader(f"Top Pick: {top.get('ticker')}")
                st.info(top["thesis"])
        else:
            st.info("No swing candidates cached. Trigger /swing/now to run a scan.")
    elif cands:
        st.json(cands)

# ═══════════════════════════════════════════════════════════
# TAB 5 — OPTIONS
# ═══════════════════════════════════════════════════════════
with tabs[4]:
    opt_stats = _get("/options/trades")
    if opt_stats and isinstance(opt_stats, dict):
        pools_data = opt_stats.get("pools", {})
        if pools_data:
            rows = []
            for pool_name, ps in pools_data.items():
                rows.append({
                    "Pool":       pool_name,
                    "Open":       ps.get("open", 0),
                    "Closed":     ps.get("closed", 0),
                    "Win Rate":   f"{ps.get('win_rate', 0)*100:.1f}%",
                    "ML Gate":    "✅ Active" if ps.get("ml_gate_active") else f"⏳ {50 - ps.get('closed', 0)} more",
                    "Last Trade": _age(ps.get("last_trade")),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No options pool data yet.")

        st.caption("SPX 0-1DTE options paper trades accumulate silently until ≥50 closed per pool.")

        # Show open positions if any
        open_pos = opt_stats.get("open_positions", [])
        if open_pos:
            st.subheader(f"Open Positions ({len(open_pos)})")
            rows = []
            for p in open_pos:
                rows.append({
                    "Pool":         p.get("pool", ""),
                    "Dir":          p.get("direction", ""),
                    "Strike":       p.get("strike", ""),
                    "DTE":          p.get("dte", ""),
                    "Entry $":      f"${p.get('entry_premium', 0):.2f}",
                    "Entry Time":   _age(p.get("entry_time")),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Options engine not returning data.")

# ═══════════════════════════════════════════════════════════
# TAB 6 — MACRO & REGIME
# ═══════════════════════════════════════════════════════════
with tabs[5]:
    health3 = _get("/health")
    if health3:
        regimes = health3.get("regimes", {})
        mtf     = health3.get("mtf", {})
        imkt    = health3.get("intermarket", {})
        post_ev = health3.get("post_event", {})

        st.subheader("Market Regimes")
        if regimes:
            rows = []
            for asset, r in regimes.items():
                rows.append({
                    "Asset":  asset,
                    "Regime": r.get("regime", "—"),
                    "Label":  r.get("label", "—"),
                    "Conf":   f"{r.get('confidence', 0)*100:.0f}%",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.subheader("MTF Confluence")
        if mtf:
            rows = []
            for asset, m in mtf.items():
                rows.append({
                    "Asset":      asset,
                    "Alignment":  m.get("alignment", "—"),
                    "Bull Score": f"{m.get('bull_score', 0):.2f}",
                    "Bear Score": f"{m.get('bear_score', 0):.2f}",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.subheader("Macro & Intermarket")
        ic1, ic2 = st.columns(2)
        ic1.metric("VIX",       imkt.get("vix", "—"))
        ic2.metric("DXY Break", _badge(imkt.get("dxy_break")) if imkt.get("dxy_break") is not None else "—")

        if post_ev:
            st.subheader("Post-Event Volatility (Active)")
            rows = []
            for asset, ev in post_ev.items():
                rows.append({
                    "Asset":  asset,
                    "State":  ev.get("state", "—"),
                    "Since":  _age(ev.get("event_time")),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(f"Migo Sniper Pro v5.2.0-26F · Backend: {BASE_URL} · Refresh page or click 🔄 to update")
