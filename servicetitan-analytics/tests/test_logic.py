"""Unit tests for the pure logic that does not need the live API:
period (YoY) computation, LMDI decomposition exactness, call-lead rule."""
import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from pipeline.build_funnel import Funnel, lmdi_decompose
from servicetitan import telecom


def test_periods_yoy_alignment():
    cur, prev = config.get_periods(today=date(2026, 6, 29))
    # default = last full month = May 2026
    assert cur.start == date(2026, 5, 1) and cur.end == date(2026, 5, 31)
    assert prev.start == date(2025, 5, 1) and prev.end == date(2025, 5, 31)


def test_lmdi_is_additive():
    prev = Funnel("year_ago", 1000, 600, 900, 300, 270, 200, 200_000.0)
    cur = Funnel("current", 1000, 480, 850, 200, 180, 140, 140_000.0)
    contrib = lmdi_decompose(cur, prev)
    total = cur.revenue - prev.revenue
    assert math.isclose(sum(contrib.values()), total, rel_tol=1e-6)
    # booking_rate dropped most here, so it should carry a large negative share
    assert contrib["booking_rate (b)"] < 0


def test_call_lead_rule():
    assert telecom.is_call_lead({"direction": "Inbound", "duration": 75})
    assert telecom.is_call_lead({"direction": "Inbound", "isLead": True, "duration": 5})
    assert not telecom.is_call_lead({"direction": "Inbound", "duration": 30})
    assert not telecom.is_call_lead({"direction": "Outbound", "duration": 600})
    assert telecom.is_call_lead({"direction": "Inbound", "duration": "00:01:30"})


if __name__ == "__main__":
    test_periods_yoy_alignment()
    test_lmdi_is_additive()
    test_call_lead_rule()
    print("ALL TESTS PASSED")
