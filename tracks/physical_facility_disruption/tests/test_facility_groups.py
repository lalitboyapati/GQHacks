"""Tests for brief vs persistent facility-group assignment."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TRACK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACK_ROOT))

from facility_groups import (
    BRIEF,
    PERSISTENT,
    UNKNOWN,
    assign_facility_group,
    partition_events,
    tradeable_events,
)


class FacilityGroupTests(unittest.TestCase):
    def test_no_anomaly_is_brief(self):
        self.assertEqual(
            assign_facility_group(anomaly_detected=False, anomaly_persist_days=0),
            BRIEF,
        )

    def test_short_spike_is_brief(self):
        self.assertEqual(
            assign_facility_group(
                anomaly_detected=True,
                anomaly_persist_days=1,
                persist_days=3,
            ),
            BRIEF,
        )

    def test_multi_day_is_persistent(self):
        self.assertEqual(
            assign_facility_group(
                anomaly_detected=True,
                anomaly_persist_days=5,
                persist_days=3,
            ),
            PERSISTENT,
        )

    def test_missing_site_unknown(self):
        self.assertEqual(
            assign_facility_group(
                anomaly_detected=True,
                anomaly_persist_days=1,
                has_site=False,
            ),
            UNKNOWN,
        )

    def test_partition_and_tradeable(self):
        events = [
            {"anomaly_detected": False, "has_site": True, "ticker": "A"},
            {
                "anomaly_detected": True,
                "anomaly_persist_days": 4,
                "has_site": True,
                "ticker": "B",
            },
            {"has_site": False, "ticker": "C"},
        ]
        parts = partition_events(events, persist_days=3)
        self.assertEqual(len(parts[BRIEF]), 1)
        self.assertEqual(len(parts[PERSISTENT]), 1)
        self.assertEqual(len(parts[UNKNOWN]), 1)
        traded = tradeable_events(events, persist_days=3)
        self.assertEqual([e["ticker"] for e in traded], ["A"])


if __name__ == "__main__":
    unittest.main()
