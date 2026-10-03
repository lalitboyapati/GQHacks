#!/usr/bin/env python
"""Deprecated for this track — use the shared Webull runner.

    python run.py --track physical_facility_disruption PSX,STLD -c 1200
"""

from __future__ import annotations


def main() -> int:
    print(
        "Use the Webull/Backtrader runner instead:\n"
        "  python run.py --track physical_facility_disruption PSX,STLD -c 1200\n"
        "Optional: -p structure=covered_call\n"
        "Refresh events first with scripts/fetch_disruption_events.py --firms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
