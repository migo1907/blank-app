"""
CBOE free delayed SPX options chain — network-free tests.

Verifies fetch_spx_chain():
  - keeps only SPXW-rooted contracts matching the requested expiry,
  - parses OSI strikes correctly (price × 1000),
  - emits every column the options engine expects,
  - applies the IV percent→decimal heuristic.
Plus a direct check of the OSI regex parser.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GITHUB_TOKEN",  "test")
os.environ.setdefault("GITHUB_REPO",   "test/test")
os.environ.setdefault("GITHUB_BRANCH", "data")

import pytest

import cboe_data


# ── Synthetic CBOE payload ────────────────────────────────────────────────────
# Mix of SPXW C/P for the target expiry, plus one non-SPXW and one wrong-expiry
# option that MUST be filtered out.
_TARGET_EXPIRY = "2026-07-01"

_PAYLOAD = {
    "data": {
        "current_price": 5432.10,
        "options": [
            # SPXW call, target expiry, strike 7430.0, IV in percent (14.8 → 0.148)
            {"option": "SPXW260701C07430000", "iv": 14.8, "delta": 0.31,
             "bid": 12.5, "ask": 13.0, "last_trade_price": 12.7, "open_interest": 120},
            # SPXW put, target expiry, strike 5400.0, IV already decimal (0.162)
            {"option": "SPXW260701P05400000", "iv": 0.162, "delta": -0.28,
             "bid": 8.1, "ask": 8.4, "last_trade_price": 8.2, "open_interest": 88},
            # Non-SPXW root — filtered OUT
            {"option": "SPX260701C05500000", "iv": 15.0, "delta": 0.4,
             "bid": 1.0, "ask": 1.2, "last_trade_price": 1.1, "open_interest": 5},
            # SPXW but wrong expiry (2026-07-02) — filtered OUT
            {"option": "SPXW260702C05500000", "iv": 15.0, "delta": 0.4,
             "bid": 1.0, "ask": 1.2, "last_trade_price": 1.1, "open_interest": 5},
            # Garbage symbol — must be skipped, not crash
            {"option": "NOTANOPTION", "iv": 20.0},
        ],
    }
}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *a, **k):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get(self, url):
        return _FakeResp(_PAYLOAD)


def _patch_httpx(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "Client", _FakeClient)


# ── OSI parser ────────────────────────────────────────────────────────────────

def test_parse_osi_call():
    root, iso, right, strike = cboe_data._parse_osi("SPXW260701C07430000")
    assert root == "SPXW"
    assert iso == "2026-07-01"
    assert right == "C"
    assert strike == 7430.0


def test_parse_osi_put_and_junk():
    root, iso, right, strike = cboe_data._parse_osi("SPXW260702P05400000")
    assert (root, iso, right, strike) == ("SPXW", "2026-07-02", "P", 5400.0)
    assert cboe_data._parse_osi("NOTANOPTION") is None
    assert cboe_data._parse_osi("") is None


def test_iv_heuristic():
    assert cboe_data._norm_iv(14.8) == pytest.approx(0.148)   # percent → decimal
    assert cboe_data._norm_iv(0.162) == pytest.approx(0.162)  # already decimal
    assert cboe_data._norm_iv(None) == 0.0


# ── fetch_spx_chain ───────────────────────────────────────────────────────────

def test_fetch_spx_chain(monkeypatch):
    _patch_httpx(monkeypatch)
    out = cboe_data.fetch_spx_chain(_TARGET_EXPIRY)

    assert out is not None
    assert out["spot"] == 5432.10
    # Only the two matching SPXW+target-expiry contracts survive.
    assert len(out["calls"]) == 1
    assert len(out["puts"]) == 1

    call = out["calls"][0]
    put = out["puts"][0]

    # Strike parsed correctly (price × 1000).
    assert call["strike"] == 7430.0
    assert put["strike"] == 5400.0

    # IV heuristic: 14.8 → 0.148, 0.162 stays.
    assert call["impliedVolatility"] == pytest.approx(0.148)
    assert put["impliedVolatility"] == pytest.approx(0.162)

    # Every required key present on each item.
    required = {"strike", "impliedVolatility", "lastPrice",
                "openInterest", "delta", "bid", "ask"}
    assert required <= set(call.keys())
    assert required <= set(put.keys())

    assert call["lastPrice"] == 12.7
    assert call["openInterest"] == 120
    assert put["delta"] == -0.28


def test_fetch_spx_chain_no_match(monkeypatch):
    _patch_httpx(monkeypatch)
    # Valid fetch but no SPXW option matches this expiry → dict with empty lists,
    # NOT None (lets caller distinguish "worked, empty" from "fetch failed").
    out = cboe_data.fetch_spx_chain("2030-01-01")
    assert out is not None
    assert out["calls"] == []
    assert out["puts"] == []
