"""
Market-macro intelligence layer for XAU/USD.

Fills gold's real macro-driver blind spots that headline sentiment can't see:
  • Real yields  (FRED DFII10)   — gold's #1 driver: rising real yields ⇒ bearish gold
  • US dollar    (FRED DTWEXBGS) — rising dollar ⇒ bearish gold
  • Breakeven    (FRED T10YIE)   — rising inflation expectations ⇒ bullish gold
  • COT          (CFTC 088691)   — speculative net positioning (smart-money lean)
  • GLD flows    (SPDR CSV)      — physical ETF demand (rising tonnes ⇒ bullish)

All sources are genuinely free. FRED + Finnhub use free API keys read from env
(graceful no-op if absent). CFTC + SPDR need no auth.

Data is slow-moving (daily/weekly), so we fetch on a slow cycle and persist the
computed bias to the GitHub data branch (data/market_macro.json) so it survives
Railway restarts and is available immediately on boot.
"""
import os
import io
import csv
import json
import httpx
from datetime import datetime, timezone, timedelta

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

_FRED_BASE   = "https://api.stlouisfed.org/fred/series/observations"
_CFTC_GOLD   = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"  # Legacy futures-only (Socrata)
_GOLD_CODE   = "088691"  # Gold, COMEX
_SPDR_CSV_URLS = [
    "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv",
    "https://www.ssga.com/us/en/individual/etfs/funds/spdr-gold-shares-gld/fund-data/gld-us-fund-data.csv",
]
_MACRO_PATH        = "data/market_macro.json"
_EQUITY_MACRO_PATH = "data/equity_macro.json"

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ── FRED: last two observations of a series ───────────────────────────────────

def _fred_latest_two(series_id: str) -> tuple[float | None, float | None]:
    """Return (latest, previous) numeric observations for a FRED series, skipping '.' gaps."""
    if not FRED_API_KEY:
        return None, None
    try:
        with httpx.Client(timeout=12) as client:
            resp = client.get(_FRED_BASE, params={
                "series_id":   series_id,
                "api_key":     FRED_API_KEY,
                "file_type":   "json",
                "sort_order":  "desc",
                "limit":       10,
            })
        resp.raise_for_status()
        obs = resp.json().get("observations", [])
        vals = []
        for o in obs:
            v = o.get("value", ".")
            if v not in (".", "", None):
                try:
                    vals.append(float(v))
                except ValueError:
                    continue
            if len(vals) >= 2:
                break
        latest = vals[0] if len(vals) >= 1 else None
        prev   = vals[1] if len(vals) >= 2 else None
        return latest, prev
    except Exception as e:
        print(f"[macro] FRED {series_id} fetch failed: {e}")
        return None, None


# ── CFTC COT: latest gold speculative net positioning ─────────────────────────

def _cftc_gold_cot() -> dict | None:
    """Latest non-commercial (speculator) net position for COMEX gold. No auth."""
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(_CFTC_GOLD, params={
                "cftc_contract_market_code": _GOLD_CODE,
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$limit": "2",
            }, headers={"User-Agent": _BROWSER_UA, "Accept": "application/json"})
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return None

        def _net(r: dict) -> tuple[int, int, int]:
            long_  = int(float(r.get("noncomm_positions_long_all", 0) or 0))
            short_ = int(float(r.get("noncomm_positions_short_all", 0) or 0))
            return long_, short_, long_ - short_

        cur = rows[0]
        cl, cs, cnet = _net(cur)
        pnet = _net(rows[1])[2] if len(rows) > 1 else cnet
        return {
            "report_date": cur.get("report_date_as_yyyy_mm_dd", "")[:10],
            "spec_long":   cl,
            "spec_short":  cs,
            "spec_net":    cnet,
            "spec_net_prev": pnet,
            "net_change":  cnet - pnet,
        }
    except Exception as e:
        print(f"[macro] CFTC COT fetch failed: {e}")
        return None


# ── SPDR GLD: latest holdings in tonnes ───────────────────────────────────────

def _parse_spdr_csv(text: str) -> dict | None:
    """Parse SPDR GLD CSV text — finds header row with gold holdings, returns latest tonnes."""
    rows = list(csv.reader(io.StringIO(text, newline='')))
    header_idx = tonnes_col = date_col = None
    # Accept multiple possible column names for tonnes/oz/holdings
    _TONNES_SYNONYMS = ("tonnes", "metric tons", "gold (oz)", "holdings", "oz", "ounces")
    for i, row in enumerate(rows):
        joined = ",".join(c.lower() for c in row)
        if any(s in joined for s in _TONNES_SYNONYMS):
            header_idx = i
            for j, c in enumerate(row):
                cl = c.strip().lower()
                if any(s in cl for s in _TONNES_SYNONYMS):
                    tonnes_col = j
                if cl == "date" or cl.startswith("date"):
                    date_col = j
            break
    if header_idx is None or tonnes_col is None:
        return None

    def _row_tonnes(r: list) -> float | None:
        try:
            return float(r[tonnes_col].replace(",", ""))
        except (ValueError, IndexError):
            return None

    data_rows = [r for r in rows[header_idx + 1:] if len(r) > tonnes_col and _row_tonnes(r) is not None]
    if not data_rows:
        return None
    latest = data_rows[0]
    cur_t  = _row_tonnes(latest)
    prev_t = _row_tonnes(data_rows[1]) if len(data_rows) > 1 else cur_t
    return {
        "date":          latest[date_col].strip() if date_col is not None and len(latest) > date_col else "",
        "tonnes":        round(cur_t, 2),
        "tonnes_prev":   round(prev_t, 2),
        "tonnes_change": round(cur_t - prev_t, 2),
    }


def _gld_holdings() -> dict | None:
    """
    Latest GLD tonnes-in-trust from SPDR CSV (tries multiple URLs).
    Falls back to yfinance GLD price-change proxy if all CSV sources fail.
    """
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        for url in _SPDR_CSV_URLS:
            try:
                resp = client.get(url, headers={"User-Agent": _BROWSER_UA})
                if resp.status_code == 200 and resp.text.strip():
                    result = _parse_spdr_csv(resp.text)
                    if result:
                        print(f"[macro] GLD holdings from {url.split('/')[2]}: {result['tonnes']}t")
                        return result
                    print(f"[macro] SPDR CSV parse failed ({url.split('/')[2]}) — no 'tonnes' column found")
            except Exception as e:
                print(f"[macro] SPDR CSV fetch failed ({url.split('/')[2]}): {e}")

    # Fallback: use yfinance GLD ETF price change as a flow proxy
    # Not tonnes, but direction is the same: rising GLD price = rising demand
    try:
        import yfinance as yf
        tk   = yf.Ticker("GLD")
        hist = tk.history(period="5d", interval="1d", auto_adjust=True)
        if hist is not None and len(hist) >= 2:
            cur  = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2])
            pct_chg = (cur - prev) / prev * 100.0
            # Express as a pseudo-tonnes change (directional signal only)
            print(f"[macro] GLD yfinance fallback: price {prev:.2f}→{cur:.2f} ({pct_chg:+.2f}%)")
            return {
                "date":           str(hist.index[-1].date()),
                "price":          round(cur, 2),
                "price_prev":     round(prev, 2),
                "price_change":   round(cur - prev, 4),
                "tonnes":         None,
                "tonnes_change":  round(cur - prev, 4),  # directional proxy only
                "source":         "yfinance_proxy",
            }
    except Exception as e:
        print(f"[macro] GLD yfinance fallback failed: {e}")

    return None


# ── Macro bias computation ────────────────────────────────────────────────────

def _compute_equity_macro_bias(
    real_yield: float | None, real_yield_prev: float | None,
    nominal_yield: float | None, nominal_yield_prev: float | None,
    dollar: float | None, dollar_prev: float | None,
) -> dict:
    """
    Compute US equity (SPY/QQQ) macro bias from already-fetched FRED values.
    Rising real yields / nominal yields / dollar = bearish equities.
    Returns bias ∈ [-1, +1]: positive ⇒ bullish equities.
    """
    components: dict[str, float] = {}

    # Real yield: rising = higher discount rate = bearish growth/equities
    # Threshold 15bp: a meaningful daily TIPS move (5bp was too sensitive, maxed out on noise)
    if real_yield is not None and real_yield_prev is not None:
        chg = real_yield - real_yield_prev
        components["real_yield"] = max(-1.0, min(1.0, -chg / 0.15))

    # Nominal 10yr yield: rising risk-free rate competes with equities
    if nominal_yield is not None and nominal_yield_prev is not None:
        chg = nominal_yield - nominal_yield_prev
        components["nominal_yield"] = max(-1.0, min(1.0, -chg / 0.15))

    # Dollar: strong USD = earnings headwind for multinational S&P500
    # Threshold 1.5%: meaningful broad-dollar daily move (0.5% was too sensitive)
    if dollar is not None and dollar_prev is not None and dollar_prev:
        pct = (dollar - dollar_prev) / dollar_prev * 100.0
        components["dollar"] = max(-0.5, min(0.5, -pct / 1.5))

    weights = {"real_yield": 1.0, "nominal_yield": 0.8, "dollar": 0.4}
    num = sum(components[k] * weights[k] for k in components)
    den = sum(weights[k] for k in components)
    bias = round(num / den, 4) if den else 0.0
    label = "BULLISH" if bias > 0.15 else "BEARISH" if bias < -0.15 else "NEUTRAL"

    return {
        "bias":          bias,
        "label":         label,
        "components":    {k: round(v, 4) for k, v in components.items()},
        "real_yield":    real_yield,
        "nominal_yield": nominal_yield,
        "dollar":        dollar,
        "updated_at":    datetime.now(timezone.utc).isoformat(),
        "sources_live":  {"fred": real_yield is not None or nominal_yield is not None},
    }


# ── Phase 2E: VIX regime + DXY level break (intermarket) ──────────────────────

def _vix_context() -> dict:
    """
    VIX level + term structure → a stock-signal size factor.
    Spiking / backwardated vol = de-risk equity signals. yfinance, free.
    size_factor ∈ [0.80, 1.0]: 1.0 = calm, <1 = shrink stock signal confidence.
    """
    out = {"vix": None, "vix3m": None, "ratio": None,
           "regime": "UNKNOWN", "size_factor": 1.0, "backwardation": False}
    try:
        from market_data import fetch_daily
        vix   = fetch_daily("^VIX", period="5d")     # yfinance → Stooq fallback
        vix3m = fetch_daily("^VIX3M", period="5d")
        if not len(vix):
            return out
        v = float(vix["Close"].iloc[-1])
        out["vix"] = round(v, 2)
        v3 = float(vix3m["Close"].iloc[-1]) if len(vix3m) else None
        if v3:
            out["vix3m"] = round(v3, 2)
            out["ratio"] = round(v / v3, 3)
            out["backwardation"] = (v / v3) > 1.0
        # Size factor: calm <18, normal 18-25, elevated 25-30, stress >30
        if v >= 30:
            sf, regime = 0.80, "STRESS"
        elif v >= 25:
            sf, regime = 0.90, "ELEVATED"
        elif v >= 18:
            sf, regime = 0.97, "NORMAL"
        else:
            sf, regime = 1.00, "CALM"
        if out["backwardation"]:
            sf *= 0.92  # term-structure inversion = extra caution
        out["regime"] = regime
        out["size_factor"] = round(sf, 3)
    except Exception as e:
        print(f"[macro] VIX context failed: {e}")
    return out


def _dxy_break() -> dict:
    """
    Detect a US-dollar-index break of its trailing 20-session range.
    DXY break DOWN (USD weakness) ⇒ gold tailwind; break UP ⇒ gold headwind.
    Returns {direction: 'UP'|'DOWN'|'NONE', strength ∈ [0,1]}.
    """
    out = {"direction": "NONE", "strength": 0.0, "level": None}
    try:
        from market_data import fetch_daily
        # 'DX-Y.NYB' is the ICE Dollar Index (yfinance → Stooq ^dxy fallback);
        # UUP ETF is a secondary proxy if the index is unavailable.
        df = fetch_daily("DX-Y.NYB", period="40d")
        if len(df) < 22:
            df = fetch_daily("UUP", period="40d")
        if len(df) < 22:
            return out
        close = df["Close"].to_numpy(dtype=float)
        last = float(close[-1])
        prior = close[-21:-1]   # trailing 20 sessions, excluding today
        hi, lo = float(prior.max()), float(prior.min())
        rng = max(hi - lo, 1e-9)
        out["level"] = round(last, 3)
        if last > hi:
            out["direction"] = "UP"
            out["strength"] = round(min(1.0, (last - hi) / rng), 3)
        elif last < lo:
            out["direction"] = "DOWN"
            out["strength"] = round(min(1.0, (lo - last) / rng), 3)
    except Exception as e:
        print(f"[macro] DXY break check failed: {e}")
    return out


def compute_macro_bias() -> dict:
    """
    Fetch all macro drivers and compute a single gold bias score in [-1, +1].
      positive ⇒ bullish gold,  negative ⇒ bearish gold.
    Daily drivers (real yield + dollar) carry the directional signal; COT/GLD
    provide confirmation context. Gracefully degrades if sources are unavailable.
    Also computes and caches equity macro bias in the same FRED pass.
    """
    real_yield, real_yield_prev   = _fred_latest_two("DFII10")   # 10y TIPS real yield
    dollar, dollar_prev           = _fred_latest_two("DTWEXBGS")  # broad USD index
    breakeven, breakeven_prev     = _fred_latest_two("T10YIE")    # 10y inflation expectations
    nominal_yield, nominal_yield_prev = _fred_latest_two("DGS10") # 10y nominal yield (for equities)
    cot = _cftc_gold_cot()
    gld = _gld_holdings()

    # Phase 2E intermarket — VIX regime (stocks) + DXY break (gold)
    vix = _vix_context()
    dxy = _dxy_break()

    # Cache equity macro bias as a side-effect of this fetch
    global _cached_equity_macro
    _cached_equity_macro = _compute_equity_macro_bias(
        real_yield, real_yield_prev,
        nominal_yield, nominal_yield_prev,
        dollar, dollar_prev,
    )
    _cached_equity_macro["vix"] = vix

    components: dict[str, float] = {}

    # Real yield change — gold's #1 driver. Rising real yields ⇒ bearish.
    # Threshold 15bp: a big daily TIPS move (5bp maxed out on routine noise)
    if real_yield is not None and real_yield_prev is not None:
        chg = real_yield - real_yield_prev
        components["real_yield"] = max(-1.0, min(1.0, -chg / 0.15))

    # Dollar change. Rising dollar ⇒ bearish gold.
    # Threshold 1.5%: meaningful broad-dollar daily swing (0.5% was too sensitive)
    if dollar is not None and dollar_prev is not None and dollar_prev:
        pct = (dollar - dollar_prev) / dollar_prev * 100.0
        components["dollar"] = max(-1.0, min(1.0, -pct / 1.5))

    # Breakeven inflation change. Rising inflation expectations ⇒ bullish gold.
    if breakeven is not None and breakeven_prev is not None:
        chg = breakeven - breakeven_prev
        components["breakeven"] = max(-1.0, min(1.0, chg / 0.15))

    # COT confirmation — speculators adding longs ⇒ mild bullish lean.
    if cot and cot.get("spec_net_prev"):
        denom = abs(cot["spec_net_prev"]) or 1
        comp = cot["net_change"] / denom
        components["cot"] = max(-0.5, min(0.5, comp * 5.0))          # capped — confirmation only

    # GLD flow confirmation — rising tonnes ⇒ physical demand, mild bullish.
    if gld and gld.get("tonnes_prev"):
        pct = gld["tonnes_change"] / gld["tonnes_prev"] * 100.0
        components["gld"] = max(-0.5, min(0.5, pct / 0.5))           # capped — confirmation only

    # Weighted blend — daily drivers lead, COT/GLD confirm.
    weights = {"real_yield": 1.0, "dollar": 1.0, "breakeven": 0.6, "cot": 0.4, "gld": 0.4}
    num = sum(components[k] * weights[k] for k in components)
    den = sum(weights[k] for k in components)
    bias = round(num / den, 4) if den else 0.0

    label = "BULLISH" if bias > 0.15 else "BEARISH" if bias < -0.15 else "NEUTRAL"

    return {
        "bias":       bias,
        "label":      label,
        "components": {k: round(v, 4) for k, v in components.items()},
        "real_yield": real_yield,
        "dollar":     dollar,
        "breakeven":  breakeven,
        "cot":        cot,
        "gld":        gld,
        "dxy_break":  dxy,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sources_live": {
            "fred": real_yield is not None,
            "cot":  cot is not None,
            "gld":  gld is not None,
        },
    }


# ── Persistence + in-memory cache ─────────────────────────────────────────────

_cached_macro: dict        = {"bias": 0.0, "label": "NEUTRAL", "components": {}, "updated_at": None}
_cached_equity_macro: dict = {"bias": 0.0, "label": "NEUTRAL", "components": {}, "updated_at": None}


def get_macro_bias() -> dict:
    """Return the most recently computed gold macro bias (in-memory)."""
    return _cached_macro


def get_equity_macro_bias() -> dict:
    """Return the most recently computed equity (SPY/QQQ) macro bias (in-memory)."""
    return _cached_equity_macro


def refresh_macro_bias() -> dict:
    """Compute fresh macro bias for gold + equity, cache both in memory, persist both to data branch."""
    global _cached_macro
    macro = compute_macro_bias()  # also updates _cached_equity_macro as side-effect
    _cached_macro = macro
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_MACRO_PATH)
        _put_file(_MACRO_PATH, macro, sha, "data: update market macro bias")
    except Exception as e:
        print(f"[macro] gold persist failed: {e}")
    try:
        from db import _get_file, _put_file
        _, sha = _get_file(_EQUITY_MACRO_PATH)
        _put_file(_EQUITY_MACRO_PATH, _cached_equity_macro, sha, "data: update equity macro bias")
    except Exception as e:
        print(f"[macro] equity persist failed: {e}")
    print(
        f"[macro] gold bias={macro['bias']:+.3f} ({macro['label']}) "
        f"equity bias={_cached_equity_macro['bias']:+.3f} ({_cached_equity_macro['label']}) "
        f"components={macro['components']} live={macro['sources_live']}"
    )
    return macro


def load_macro_bias() -> None:
    """Load persisted macro biases (gold + equity) from the data branch on startup."""
    global _cached_macro, _cached_equity_macro
    try:
        from db import _get_file
        data, _ = _get_file(_MACRO_PATH)
        if isinstance(data, dict) and "bias" in data:
            _cached_macro = data
            print(f"[macro] Loaded gold bias={data.get('bias')} ({data.get('label')})")
    except Exception as e:
        print(f"[macro] gold load failed (first run?): {e}")
    try:
        from db import _get_file
        data, _ = _get_file(_EQUITY_MACRO_PATH)
        if isinstance(data, dict) and "bias" in data:
            _cached_equity_macro = data
            print(f"[macro] Loaded equity bias={data.get('bias')} ({data.get('label')})")
    except Exception as e:
        print(f"[macro] equity load failed (first run?): {e}")
