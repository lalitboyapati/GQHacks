"""Tests for disruption text filters (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TRACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRACK_ROOT.parents[1]
INFRA_ROOT = REPO_ROOT / "infrastructure"
sys.path.insert(0, str(INFRA_ROOT))
sys.path.insert(0, str(TRACK_ROOT))

from massive_disruptions import (
    classify_disruption_type,
    is_disruption_text,
)


class DisruptionFilterTests(unittest.TestCase):
    def test_plant_fire_matches(self):
        text = "Item 8.01. On June 1 a fire at the Company's steel plant temporarily halted production."
        self.assertTrue(is_disruption_text(text))
        self.assertEqual(classify_disruption_type(text), "facility_fire")

    def test_earnings_only_does_not_match(self):
        text = "Item 2.02 Results of Operations. The Company reported quarterly earnings."
        self.assertFalse(is_disruption_text(text))

    def test_force_majeure(self):
        text = "The issuer declared force majeure at its refinery following the incident."
        self.assertTrue(is_disruption_text(text))
        self.assertEqual(classify_disruption_type(text), "force_majeure")

    def test_force_majeure_receivables_noise_rejected(self):
        text = (
            "customers and/or suppliers asserting force majeure or other reasons "
            "for not performing their contractual obligations"
        )
        self.assertFalse(is_disruption_text(text))

    def test_explosion(self):
        text = "An explosion occurred at the chemical facility; operations remain suspended."
        self.assertTrue(is_disruption_text(text))
        self.assertIn(classify_disruption_type(text), {"explosion", "plant_shutdown"})


if __name__ == "__main__":
    unittest.main()
