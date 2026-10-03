"""Tests for NASA FIRMS CSV parsing and anomaly persistence (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_ROOT = REPO_ROOT / "infrastructure"
sys.path.insert(0, str(INFRA_ROOT))

from webull_bt.firms import (
    FirmsHotspot,
    bbox_around,
    haversine_km,
    parse_firms_csv,
    summarize_anomaly,
)


SAMPLE_CSV = """latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,confidence,version,bright_t31,frp,daynight
41.610,-87.340,330.1,1.0,1.0,2025-06-02,0130,N,h,2.0NRT,290.0,12.5,N
41.612,-87.338,328.0,1.0,1.0,2025-06-03,0145,N,n,2.0NRT,289.0,10.1,N
41.900,-87.100,340.0,1.0,1.0,2025-06-04,0200,N,h,2.0NRT,295.0,20.0,N
"""


class FirmsParseTests(unittest.TestCase):
    def test_parse_csv(self):
        spots = parse_firms_csv(SAMPLE_CSV)
        self.assertEqual(len(spots), 3)
        self.assertEqual(spots[0].acq_date, "2025-06-02")

    def test_summarize_brief_vs_persistent(self):
        spots = [
            FirmsHotspot(41.6, -87.3, "2025-06-02"),
            FirmsHotspot(41.6, -87.3, "2025-06-03"),
        ]
        summary = summarize_anomaly(spots, persist_days=3)
        self.assertTrue(summary["anomaly_detected"])
        self.assertEqual(summary["anomaly_persist_days"], 2)

        long = spots + [FirmsHotspot(41.6, -87.3, "2025-06-04")]
        self.assertEqual(summarize_anomaly(long, persist_days=3)["anomaly_persist_days"], 3)

    def test_haversine_and_bbox(self):
        self.assertLess(haversine_km(41.6, -87.3, 41.601, -87.301), 2.0)
        box = bbox_around(41.6, -87.3, half_box_deg=0.05)
        west, south, east, north = (float(x) for x in box.split(","))
        self.assertLess(west, east)
        self.assertLess(south, north)


if __name__ == "__main__":
    unittest.main()
