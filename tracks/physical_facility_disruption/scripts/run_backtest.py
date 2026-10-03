#!/usr/bin/env python
"""Event-study backtest entry for facility disruptions (stub).

Will filter to ``facility_group == brief`` and sell premium via eightk
structures (cash-secured put / covered call). Persistent events remain the
control arm for implied-vs-realized reporting.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "physical_facility_disruption: run_backtest not implemented yet.\n"
        "1) Build / label events (see data/events/schema_example.json)\n"
        "2) Confirm A/B split: python tracks/physical_facility_disruption/scripts/describe_groups.py\n"
        "3) Implement short-premium path on group A using infrastructure/eightk\n"
        "See tracks/physical_facility_disruption/STRATEGY.md"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
