"""Tests for place extraction (geocode network calls are not required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TRACK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK_ROOT))

from facility_geocode import extract_location_queries


class ExtractLocationTests(unittest.TestCase):
    def test_belle_chasse_refinery(self):
        text = (
            "Phillips 66 announced that it plans to convert its Alliance Refinery "
            "in Belle Chasse, Louisiana, to a terminal facility."
        )
        queries = extract_location_queries(text)
        self.assertTrue(any("Belle Chasse" in q for q in queries))
        self.assertTrue(any("Alliance Refinery" in q for q in queries))

    def test_sinton_texas_mill(self):
        text = 'press release titled "Sinton Texas Flat Roll Steel Mill Hot Mill Outage."'
        queries = extract_location_queries(text)
        self.assertTrue(any("Sinton" in q and "TX" in q for q in queries) or any("Sinton" in q and "Texas" in q for q in queries))

    def test_european_city(self):
        text_ascii = "shut down an ethylene facility in Bohlen, Germany."
        queries = extract_location_queries(text_ascii)
        self.assertTrue(any("Bohlen" in q and "Germany" in q for q in queries))

    def test_ignores_prose_false_positives(self):
        text = "In total, these costs are expected to be in the range of $630 million."
        queries = extract_location_queries(text)
        self.assertEqual(queries, [])


if __name__ == "__main__":
    unittest.main()
