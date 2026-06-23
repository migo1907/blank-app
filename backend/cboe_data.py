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
