"""Offline tests for polygon_backfill_0dte 	(no network)."""
import sys
import os
from datetime import timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polygon_backfill_0dte import option_ticker, bars_from_aggs


def test_option_ticker_occ_format():
    assert option_ticker("2026-06-26", "call", 7425) == "O:SPXW260626C07425000"
    assert option_ticker("2026-06-26", "put", 7425) == "O:SPXW260626P07425000"
    assert option_ticker("2026-01-02", "call", 6002.5) == "O:SPXW260102C06002500"


def test_bars_from_aggs_sorted_utc():
    aggs = [
        {"t": 1750945800000, "o": 2.0, "h": 2.5, "l": 1.9, "c": 2.2, "v": 10},
        {"t": 1750945740000, "o": 1.8, "h": 2.1, "l": 1.7, "c": 2.0, "v": 5},
    ]
    bars = bars_from_aggs(aggs)
    assert bars[0]["o"] == 1.8 and bars[1]["o"] == 2.0
    assert bars[0]["time"] < bars[1]["time"]
    assert bars[0]["time"].tzinfo == timezone.utc
    assert bars[1]["v"] == 10
