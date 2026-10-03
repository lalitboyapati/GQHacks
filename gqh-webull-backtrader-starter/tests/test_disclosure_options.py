"""Unit tests for disclosure polarity and options pricing helpers."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from webull_bt.disclosure_polarity import category_polarity, resolve_signal_polarity
from webull_bt.options_sim import black_scholes_price, round_strike


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


if __name__ == "__main__":
    unittest.main()
