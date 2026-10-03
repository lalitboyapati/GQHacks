#!/usr/bin/env python
"""Summarize brief vs persistent vs unknown facility-disruption events.

    python tracks/physical_facility_disruption/scripts/describe_groups.py
    python tracks/physical_facility_disruption/scripts/describe_groups.py --events path/to/events.json --persist-days 3
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

TRACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRACK_ROOT.parents[1]
sys.path.insert(0, str(TRACK_ROOT))

from facility_groups import partition_events  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--events",
        default=str(TRACK_ROOT / "data" / "events" / "schema_example.json"),
        help="JSON with an ``events`` list (schema_example.json format)",
    )
    parser.add_argument("--persist-days", type=int, default=3)
    args = parser.parse_args()

    path = Path(args.events)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve() if not path.exists() else path.resolve()
    if not path.exists():
        print(f"No event file at {path}")
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    events = payload.get("events", payload if isinstance(payload, list) else [])
    parts = partition_events(events, persist_days=args.persist_days)

    print(f"file: {path}")
    print(f"persist_days threshold: {args.persist_days}")
    print(f"total events: {len(events)}")
    for name in ("brief", "persistent", "unknown"):
        rows = parts[name]
        print(f"  {name:11s} {len(rows):4d}   (tradeable={'yes' if name == 'brief' else 'no'})")

    types = Counter(
        (e.get("disruption_type") or "unspecified")
        for e in parts["brief"] + parts["persistent"]
    )
    if types:
        print("disruption_type (labeled A/B only):")
        for key, n in types.most_common():
            print(f"  {key}: {n}")

    print(
        "\nNext: join real filings + satellite labels, then implement "
        "scripts/run_backtest.py (CSP / covered call on group A only)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
