"""
CBOE daily put/call ratio — free, no-auth market-wide sentiment signal.

The total/equity put-call ratio is one of the more consistent next-day sentiment
reads: a spike in puts (high ratio) marks fear/capitulation (contrarian bullish),
a collapse (low ratio) marks complacency. Used as a feature for the SPX options
ML model and surfaced as options context.

Source: CBOE's published daily P/C CSVs (canonical free endpoint). Updates once
per trading day after the close. Every function degrades gracefully — if the host
is unreachable or the format changes, it returns the last cached value (or None)
and never raises or blocks.
"""
from __future__ import annotations

from datetime import datetime, timezone

# CBOE published daily put/call ratio CSVs (free, no auth).
_URLS = {
    "total":  "https://www.cboe.com/publish/scheduledtask/mktdata/datahouse/totalpc.csv",
    "equity": "https://www.cboe.com/publish/scheduledtask/mktdata/datahouse/equitypc.csv",
    "index":  "https://www.cboe.com/publish/scheduledtask/mktdata/datahouse/indexpc.csv",
}
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"),
    "Accept": "text/csv, text/plain, */*",
}

_PC_PATH = "data/cboe_pc.json"
_cache: dict = {"total_pc": None, "equity_pc": None, "index_pc": None,
                "date": None, "updated_at": None}


def _last_ratio(csv_text: str) -> tuple[str | None, float | None]:
    """Parse the most recent (date, P/C ratio) from a CBOE P/C CSV.

    Format varies but the data rows are `DATE,CALL,PUT,TOTAL,P/C Ratio` (the ratio
    is the last numeric column). Header/preamble lines are skipped by requiring the
    first field to parse as a date and the last field as a float.
    """
    import csv as _csv
    import io
    last_date, last_ratio = None, None
    for row in _csv.reader(io.StringIO(csv_text)):
        if len(row) < 2:
            continue
        date_str = row[0].strip()
        ratio_str = row[-1].strip()
        # Date sanity: must contain a separator and a digit
        if not any(ch.isdigit() for ch in date_str):
            continue
        try:
            ratio = float(ratio_str)
        except ValueError:
            continue
        if 0 < ratio < 10:   # sane P/C ratio bound
            last_date, last_ratio = date_str, ratio
    return last_date, last_ratio


def fetch_pc_ratio() -> dict:
    """Fetch latest CBOE put/call ratios, update + persist cache. Graceful no-op."""
    global _cache
    try:
        import httpx
        out = {"total_pc": None, "equity_pc": None, "index_pc": None, "date": None}
        with httpx.Client(timeout=12, headers=_HEADERS, follow_redirects=True) as c:
            for key, url in _URLS.items():
                try:
                    r = c.get(url)
                    if r.status_code != 200:
                        continue
                    d, ratio = _last_ratio(r.text)
                    if ratio is not None:
                        out[f"{key}_pc"] = round(ratio, 3)
                        out["date"] = d or out["date"]
                except Exception:
                    continue
        if any(out[k] is not None for k in ("total_pc", "equity_pc", "index_pc")):
            out["updated_at"] = datetime.now(timezone.utc).isoformat()
            _cache = out
            try:
                from db import _get_file, _put_file
                _, sha = _get_file(_PC_PATH)
                _put_file(_PC_PATH, _cache, sha, "data: cboe p/c ratio update")
            except Exception as _pe:
                print(f"[cboe] persist failed (non-fatal): {_pe}")
        else:
            print("[cboe] no P/C data parsed — keeping cached value")
    except Exception as e:
        print(f"[cboe] fetch failed: {e}")
    return dict(_cache)


import re as _re

# Match an OSI/OCC option symbol tail: ROOT + YYMMDD + C|P + 8-digit strike.
# e.g. "SPXW260701C07430000" → root=SPXW, date=260701, C, strike=07430000
_OSI_RE = _re.compile(r"([A-Z]+)(\d{6})([CP])(\d{8})$")


def _parse_osi(symbol: str) -> tuple[str, str, str, float] | None:
    """Parse an OSI/OCC option symbol → (root, iso_expiry, right, strike).

    Format: ROOT + YYMMDD + C|P + STRIKE(8 digits, price × 1000).
    "SPXW260701C07430000" → ("SPXW", "2026-07-01", "C", 7430.0).
    Returns None if the symbol doesn't match (skip that option safely).
    """
    if not symbol:
        return None
    m = _OSI_RE.search(symbol.strip())
    if not m:
        return None
    root, yymmdd, right, strike8 = m.groups()
    try:
        iso = f"20{yymmdd[0:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
        strike = int(strike8) / 1000.0
    except Exception:
        return None
    return root, iso, right, strike


def _norm_iv(raw) -> float:
    """CBOE 'iv' may be a fraction (0.148) or a percent (14.8). Heuristic:
    values > 3 are assumed to be in percent and divided by 100 (an IV of 300%
    is already implausible for SPX, so >3 unambiguously means percent form)."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return v / 100.0 if v > 3 else v


def _f(raw, default=0.0):
    """Best-effort float coercion — never raises."""
    try:
        v = float(raw)
        return default if v != v else v
    except (TypeError, ValueError):
        return default


def fetch_spx_chain(expiry: str) -> dict | None:
    """Free delayed SPX (SPXW) options chain from CBOE's CDN.

    Returns {"calls": [...], "puts": [...], "spot": float|None} where each option
    is a dict with keys strike/impliedVolatility/lastPrice/openInterest/delta/bid/ask
    — the same shape the options engine expects from Tradier/Polygon.

    Keeps ONLY SPXW-rooted contracts (PM-settled daily/weekly series used for
    0/1DTE) whose parsed expiry equals the requested ISO `expiry`.

    Returns None on fetch failure; returns the dict with (possibly empty) lists
    when the fetch worked but nothing matched, so the caller can distinguish.
    """
    url = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
    ok = False
    detail = ""
    try:
        import httpx
        with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            payload = r.json()
        data = (payload or {}).get("data", {}) or {}
        spot = data.get("current_price")
        try:
            spot = float(spot) if spot is not None else None
        except (TypeError, ValueError):
            spot = None

        calls, puts = [], []
        for opt in data.get("options", []) or []:
            try:
                sym = opt.get("option") or opt.get("symbol") or ""
                parsed = _parse_osi(sym)
                if not parsed:
                    continue
                root, iso, right, strike = parsed
                if root != "SPXW" or iso != expiry:
                    continue
                item = {
                    "strike":            strike,
                    "impliedVolatility": _norm_iv(opt.get("iv")),
                    "lastPrice":         _f(opt.get("last_trade_price")),
                    "openInterest":      int(_f(opt.get("open_interest"))),
                    "delta":             _f(opt.get("delta")),
                    "bid":               _f(opt.get("bid")),
                    "ask":               _f(opt.get("ask")),
                }
                (calls if right == "C" else puts).append(item)
            except Exception:
                continue  # never let one bad option abort the whole chain

        calls.sort(key=lambda x: x["strike"])
        puts.sort(key=lambda x: x["strike"])
        ok = True
        detail = f"{len(calls)}C {len(puts)}P for {expiry}"
        print(f"[cboe] SPX chain: {detail}")
        result = {"calls": calls, "puts": puts, "spot": spot}
    except Exception as e:
        detail = str(e)
        print(f"[cboe] SPX chain fetch failed: {e}")
        result = None

    try:
        import data_health
        data_health.record("cboe_options_chain", ok, "options", detail)
    except Exception:
        pass
    return result


def _get_spx_payload() -> dict:
    """Raw CBOE _SPX.json 'data' object (current_price + options list). {} on error."""
    import httpx
    url = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
    with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return (r.json() or {}).get("data", {}) or {}


def fetch_spx_expiries() -> list[str]:
    """Sorted unique SPXW expiry dates (ISO) listed on CBOE — the free fallback for
    the options engine's expiry list. Returns [] on any failure."""
    try:
        data = _get_spx_payload()
        exps = set()
        for opt in data.get("options", []) or []:
            p = _parse_osi(opt.get("option") or opt.get("symbol") or "")
            if p and p[0] == "SPXW":
                exps.add(p[1])
        out = sorted(exps)
        print(f"[cboe] SPX expiries: {len(out)} found")
        return out
    except Exception as e:
        print(f"[cboe] SPX expiries fetch failed: {e}")
        return []


def probe_spx() -> dict:
    """Diagnostic snapshot of what CBOE actually returns — for debugging the chain
    path (HTTP status, option count, roots seen, a few raw symbols, current_price)."""
    out: dict = {"url": "cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"}
    try:
        import httpx
        url = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
        with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as c:
            r = c.get(url)
            out["http_status"] = r.status_code
            r.raise_for_status()
            data = (r.json() or {}).get("data", {}) or {}
        opts = data.get("options", []) or []
        out["current_price"] = data.get("current_price")
        out["n_options"] = len(opts)
        roots: dict = {}
        samples = []
        for opt in opts:
            sym = opt.get("option") or opt.get("symbol") or ""
            p = _parse_osi(sym)
            if p:
                roots[p[0]] = roots.get(p[0], 0) + 1
            if len(samples) < 4:
                samples.append({"sym": sym, "keys": list(opt.keys())[:10]})
        out["roots"] = roots
        out["sample_options"] = samples
    except Exception as e:
        out["error"] = str(e)
    return out


def get_pc_ratio() -> dict:
    """Return last cached CBOE put/call ratios (no network)."""
    return dict(_cache)


def load_pc_ratio() -> None:
    """Restore cached ratios from the data branch on startup."""
    global _cache
    try:
        from db import _get_file
        data, _ = _get_file(_PC_PATH)
        if isinstance(data, dict) and data.get("total_pc") is not None:
            _cache = data
            print(f"[startup] CBOE P/C loaded: total={data.get('total_pc')} ({data.get('date')})")
    except Exception as e:
        print(f"[cboe] load failed (non-fatal): {e}")
