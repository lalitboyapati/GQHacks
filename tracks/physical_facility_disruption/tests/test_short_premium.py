"""Tests for synthetic short-premium P&L used by facility disruption CSP."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_ROOT = REPO_ROOT / "infrastructure"
sys.path.insert(0, str(INFRA_ROOT))

from webull_bt.options_sim import OptionPosition


class ShortPremiumTests(unittest.TestCase):
    def test_short_put_profits_when_premium_falls(self):
        pos = OptionPosition(
            symbol="STLD",
            option_type="put",
            strike=100.0,
            expiry=date(2023, 8, 18),
            contracts=1,
            entry_premium=5.0,
            entry_underlying=100.0,
            entry_date=date(2023, 7, 10),
            entry_bar=10,
            side="short",
            entry_vol=0.5,
        )
        # Spot unchanged, lower vol → cheaper put → short profits.
        pnl = pos.pnl(100.0, date(2023, 7, 20), vol=0.25)
        self.assertGreater(pnl, 0.0)
        self.assertLess(pos.cost_basis(), 0.0)  # credit


if __name__ == "__main__":
    unittest.main()
