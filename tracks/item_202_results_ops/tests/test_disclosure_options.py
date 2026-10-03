"""Unit tests for disclosure polarity and options pricing helpers."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

TRACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRACK_ROOT.parents[1]
INFRA_ROOT = REPO_ROOT / "infrastructure"
sys.path.insert(0, str(INFRA_ROOT))

from webull_bt.disclosure_polarity import category_polarity, resolve_signal_polarity
from webull_bt.options_sim import black_scholes_price, round_strike
from webull_bt.timespan_scale import (
    bars_per_session,
    hours_to_bars,
    scale_hold_params,
    sessions_to_bars,
)


class PolarityTests(unittest.TestCase):
    def test_negative_risk_is_put(self):
        self.assertEqual(category_polarity("risk_events", "material_litigation"), -1)

    def test_positive_deal_is_call(self):
        self.assertEqual(category_polarity("strategic_transactions", "acquisition_agreement"), 1)

    def test_earnings_unsigned_uses_gap(self):
        self.assertEqual(category_polarity("financial_results", "quarterly_earnings"), 0)
        self.assertEqual(
            resolve_signal_polarity(
                primary_category="financial_results",
                tertiary_category="quarterly_earnings",
                gap_pct=0.03,
            ),
            1,
        )
        self.assertEqual(
            resolve_signal_polarity(
                primary_category="financial_results",
                tertiary_category="quarterly_earnings",
                gap_pct=-0.03,
            ),
            -1,
        )


class OptionsPricingTests(unittest.TestCase):
    def test_call_put_positive(self):
        call = black_scholes_price(100, 100, 30 / 365, 0.04, 0.4, "call")
        put = black_scholes_price(100, 100, 30 / 365, 0.04, 0.4, "put")
        self.assertGreater(call, 0)
        self.assertGreater(put, 0)

    def test_round_strike(self):
        self.assertEqual(round_strike(103.2), 102.5)


class TimespanScaleTests(unittest.TestCase):
    def test_daily_matches_sessions(self):
        scaled = scale_hold_params(
            timespan="D",
            min_hold_sessions=2,
            max_hold_sessions=5,
            atr_sessions=14,
        )
        self.assertEqual(scaled["min_hold_bars"], 2)
        self.assertEqual(scaled["max_hold_bars"], 5)
        self.assertEqual(scaled["atr_period"], 14)

    def test_m5_scales_sessions(self):
        self.assertEqual(bars_per_session("M5"), 78.0)
        self.assertEqual(sessions_to_bars(2, "M5"), 156)
        self.assertEqual(sessions_to_bars(5, "M5"), 390)

    def test_hour_cap_on_intraday(self):
        scaled = scale_hold_params(
            timespan="M5",
            min_hold_sessions=2,
            max_hold_sessions=5,
            max_hold_hours=3,
        )
        # 3h / 5min = 36 bars, tighter than 5 sessions.
        self.assertEqual(hours_to_bars(3, "M5"), 36)
        self.assertEqual(scaled["max_hold_bars"], 36)
        self.assertLessEqual(scaled["min_hold_bars"], scaled["max_hold_bars"])

    def test_explicit_bar_override(self):
        scaled = scale_hold_params(
            timespan="M5",
            min_hold_sessions=2,
            max_hold_sessions=5,
            max_hold_bars=20,
            min_hold_bars=5,
        )
        self.assertEqual(scaled["min_hold_bars"], 5)
        self.assertEqual(scaled["max_hold_bars"], 20)


if __name__ == "__main__":
    unittest.main()
