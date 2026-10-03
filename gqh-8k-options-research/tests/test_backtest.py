"""Tests for entry timing, exit accounting, and cost application.

Entry timing is the single assumption most able to fabricate an edge, so the
session-bucket rules are pinned down here against a synthetic calendar that
includes a weekend and a gap.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eightk.backtest import _capital_at_risk, determine_entry
from eightk.edgar import Filing
from eightk.massive_src import Bar
from eightk.options_book import CostModel
from eightk.options_model import Leg, Structure
from eightk.prices import PriceSeries


def make_series() -> PriceSeries:
    """Five sessions spanning a weekend: Thu, Fri, Mon, Tue, Wed."""
    days = [date(2025, 11, 6), date(2025, 11, 7), date(2025, 11, 10),
            date(2025, 11, 11), date(2025, 11, 12)]
    bars = [
        Bar(day=day, open=100.0 + i, high=102.0 + i, low=98.0 + i,
            close=101.0 + i, volume=1e6, vwap=100.5 + i)
        for i, day in enumerate(days)
    ]
    return PriceSeries("TEST", bars)


def make_filing(acceptance_utc: datetime, filing_date: str) -> Filing:
    return Filing(
        ticker="TEST", cik="0000000001", accession="0000000001-25-000001",
        form="8-K", filing_date=filing_date, acceptance_utc=acceptance_utc,
        items=("5.02",), primary_document="t.htm",
    )


class TestSessionBuckets:
    def test_premarket_filing(self):
        # 13:31 UTC on 2025-11-06 is 08:31 ET, before the open.
        filing = make_filing(datetime(2025, 11, 6, 13, 31, tzinfo=timezone.utc), "2025-11-06")
        assert filing.session_bucket == "PRE"

    def test_after_close_filing(self):
        # 21:10 UTC is 16:10 ET, after the close.
        filing = make_filing(datetime(2025, 11, 6, 21, 10, tzinfo=timezone.utc), "2025-11-06")
        assert filing.session_bucket == "POST"

    def test_intraday_filing(self):
        # 17:00 UTC is 12:00 ET, mid-session.
        filing = make_filing(datetime(2025, 11, 6, 17, 0, tzinfo=timezone.utc), "2025-11-06")
        assert filing.session_bucket == "RTH"


class TestEntryTiming:
    def test_premarket_enters_same_day_open(self):
        series = make_series()
        filing = make_filing(datetime(2025, 11, 6, 13, 31, tzinfo=timezone.utc), "2025-11-06")
        entry_day, spot, _ref, note = determine_entry(filing, series)
        assert entry_day == date(2025, 11, 6)
        assert spot == pytest.approx(100.0)   # that session's open
        assert note == "pre_open"

    def test_after_close_enters_next_session_open(self):
        series = make_series()
        filing = make_filing(datetime(2025, 11, 6, 21, 10, tzinfo=timezone.utc), "2025-11-06")
        entry_day, spot, _ref, note = determine_entry(filing, series)
        assert entry_day == date(2025, 11, 7)
        assert spot == pytest.approx(101.0)
        assert note == "post_next_open"

    def test_friday_after_close_skips_the_weekend(self):
        """The next tradable session after Friday's close is Monday."""
        series = make_series()
        filing = make_filing(datetime(2025, 11, 7, 21, 30, tzinfo=timezone.utc), "2025-11-07")
        entry_day, _spot, _ref, _note = determine_entry(filing, series)
        assert entry_day == date(2025, 11, 10)

    def test_intraday_enters_at_the_close_not_the_open(self):
        """An in-session filing cannot be filled at that morning's open.

        Assuming otherwise would hand the backtest the very reaction it is
        trying to measure.
        """
        series = make_series()
        filing = make_filing(datetime(2025, 11, 6, 17, 0, tzinfo=timezone.utc), "2025-11-06")
        entry_day, spot, _ref, note = determine_entry(filing, series)
        assert entry_day == date(2025, 11, 6)
        assert spot == pytest.approx(101.0)   # close, strictly worse than open
        assert note == "rth_close"

    def test_intraday_can_be_disabled(self):
        series = make_series()
        filing = make_filing(datetime(2025, 11, 6, 17, 0, tzinfo=timezone.utc), "2025-11-06")
        assert determine_entry(filing, series, allow_rth=False) is None


class TestTradingCalendar:
    def test_shift_counts_sessions_not_calendar_days(self):
        series = make_series()
        assert series.shift(date(2025, 11, 7), 1) == date(2025, 11, 10)
        assert series.shift(date(2025, 11, 6), 3) == date(2025, 11, 11)

    def test_closes_before_excludes_the_event_day(self):
        """Pre-event vol must not peek at the event bar itself."""
        series = make_series()
        closes = series.closes_before(date(2025, 11, 10), 10)
        assert closes == [101.0, 102.0]

    def test_shift_past_the_end_returns_none(self):
        assert make_series().shift(date(2025, 11, 12), 5) is None


class TestCostModel:
    def test_buyer_pays_up_and_seller_receives_less(self):
        costs = CostModel(spread_pct_of_premium=0.05, min_spread_abs=0.01)
        assert costs.fill_premium(4.00, side=+1) == pytest.approx(4.20)
        assert costs.fill_premium(4.00, side=-1) == pytest.approx(3.80)

    def test_absolute_floor_protects_cheap_options(self):
        costs = CostModel(spread_pct_of_premium=0.01, min_spread_abs=0.05)
        assert costs.fill_premium(0.10, side=+1) == pytest.approx(0.15)

    def test_fills_never_go_negative(self):
        costs = CostModel(spread_pct_of_premium=2.0, min_spread_abs=5.0)
        assert costs.fill_premium(0.05, side=-1) > 0


class TestCapitalAtRisk:
    def test_debit_structure_risks_its_premium(self):
        put = Structure("p", [Leg("put", 90.0, 2, 4.0)])
        assert _capital_at_risk(put, 100.0) == pytest.approx(800.0)

    def test_credit_structure_uses_a_margin_proxy_not_the_credit(self):
        """Return on premium collected would wildly flatter short vol.

        A naked strangle's risk is not the credit received, so the margin a
        broker would actually demand is used instead.
        """
        strangle = Structure("s", [
            Leg("put", 90.0, -1, 3.0),
            Leg("call", 110.0, -1, 2.5),
        ])
        capital = _capital_at_risk(strangle, 100.0)
        assert capital > 550.0
        assert capital == pytest.approx(0.20 * 2 * 100 * 100.0 * 0.5)

    def test_collar_capital_is_the_stock_position(self):
        collar = Structure("c", [
            Leg("stock", None, 100, 100.0),
            Leg("put", 90.0, 1, 3.0),
            Leg("call", 110.0, -1, 2.0),
        ])
        assert _capital_at_risk(collar, 100.0) == pytest.approx(10_000.0)
