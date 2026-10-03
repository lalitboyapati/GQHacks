#!/usr/bin/env python
"""Summarize a saved event set before any trading logic is applied.

Worth reading first for two reasons. It shows whether the sample is large
enough to support a conclusion at all, and it shows how the events are
distributed across filing sessions -- which caps how much of any reaction is
actually reachable, since an in-session filing can only be entered at the
close.

    python scripts/describe_events.py --events data/events/universe_events.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_ROOT = REPO_ROOT / "infrastructure"
sys.path.insert(0, str(INFRA_ROOT))
os.environ.setdefault("GQH_TRACK", "disclosure_advantage")

from eightk.config import Settings


def _pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:5.1f}%" if whole else "    -"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--events", default=None, help="Path to the events JSON")
    args = parser.parse_args()

    settings = Settings.from_env()
    path = Path(args.events) if args.events else settings.events_dir / "events.json"
    if not path.exists():
        print(f"No event file at {path}. Run scripts/fetch_events.py first.")
        return 1

    rows = json.loads(path.read_text())
    if not rows:
        print("Event file is empty.")
        return 1

    total = len(rows)
    print(f"\n{'=' * 74}")
    print(f"EVENT SET: {path}")
    print(f"{'=' * 74}")
    print(f"events: {total}   tickers: {len({r['ticker'] for r in rows})}   "
          f"window: {min(r['filing_date'] for r in rows)} to "
          f"{max(r['filing_date'] for r in rows)}")

    print("\nEVENT TYPE")
    types = Counter(t for r in rows for t in r.get("event_types", []))
    for name, count in types.most_common():
        print(f"  {name:22s} {count:5d}  {_pct(count, total)}")

    print("\nFILING SESSION  (PRE/POST are gap-tradable; RTH enters at the close)")
    for name, count in Counter(r["session_bucket"] for r in rows).most_common():
        print(f"  {name:22s} {count:5d}  {_pct(count, total)}")

    confounded = sum(1 for r in rows if r.get("confounded_by_earnings"))
    print(f"\nCO-FILED WITH EARNINGS (Item 2.02): {confounded} "
          f"({_pct(confounded, total).strip()}) - excluded by default")

    exec_rows = [r for r in rows if r.get("exec_is_departure")]
    if exec_rows:
        print(f"\nEXECUTIVE DEPARTURES: {len(exec_rows)}")
        print("  by role:")
        for role, count in Counter(r.get("exec_top_role") for r in exec_rows).most_common():
            print(f"    {str(role):20s} {count:5d}")
        senior = [r for r in exec_rows if r.get("exec_is_senior_departure")]
        print(f"  senior (CEO/CFO/President/COO): {len(senior)}")
        for flag, label in [
            ("exec_for_cause", "for cause / investigation"),
            ("exec_disagreement", "admitted disagreement"),
            ("exec_abrupt", "effective immediately"),
            ("exec_interim_successor", "interim successor only"),
            ("exec_successor_named", "successor named"),
            ("exec_retirement", "framed as retirement"),
        ]:
            count = sum(1 for r in exec_rows if r.get(flag))
            print(f"    {label:28s} {count:5d}  {_pct(count, len(exec_rows))}")
        sevs = sorted(r.get("exec_severity") or 0.0 for r in exec_rows)
        if sevs:
            mid = sevs[len(sevs) // 2]
            tradable = sum(1 for s in sevs if s >= 0.35)
            print(f"  severity: median {mid:.2f}, max {sevs[-1]:.2f}, "
                  f"{tradable} at/above the 0.35 trading threshold")

    plan_rows = [r for r in rows if r.get("plan_is_plan")]
    if plan_rows:
        print(f"\nEFFICIENCY / RESTRUCTURING PLANS: {len(plan_rows)}")
        with_charge = [r for r in plan_rows if r.get("plan_charge_usd")]
        with_savings = [r for r in plan_rows if r.get("plan_savings_usd")]
        with_horizon = [r for r in plan_rows if r.get("plan_savings_horizon_years") is not None]
        print(f"  disclosed a charge:          {len(with_charge):5d}  "
              f"{_pct(len(with_charge), len(plan_rows))}")
        print(f"  disclosed annual savings:    {len(with_savings):5d}  "
              f"{_pct(len(with_savings), len(plan_rows))}")
        print(f"  disclosed a savings horizon: {len(with_horizon):5d}  "
              f"{_pct(len(with_horizon), len(plan_rows))}")
        both = [r for r in plan_rows
                if r.get("plan_charge_usd") and r.get("plan_savings_usd")]
        print(f"  BOTH charge and savings:     {len(both):5d}  "
              f"{_pct(len(both), len(plan_rows))}  <- the only rows where the")
        print("                                          cost-now/benefit-later")
        print("                                          gap is directly measurable")
        if with_charge:
            charges = sorted(r["plan_charge_usd"] for r in with_charge)
            print(f"  charge: median ${charges[len(charges)//2]/1e6:,.0f}M  "
                  f"range ${charges[0]/1e6:,.0f}M - ${charges[-1]/1e6:,.0f}M")

    novelties = [r.get("novelty_score") for r in rows if r.get("novelty_score") is not None]
    if novelties:
        repeats = sum(1 for r in rows if r.get("is_repeat"))
        selfrep = sum(1 for r in rows if r.get("self_reported_repeat"))
        news_rows = sum(1 for r in rows if (r.get("prior_news_count") or 0) > 0)
        print(f"\nDISCLOSURE NOVELTY  (n={len(novelties)})")
        ordered = sorted(novelties)
        print(f"  score: median {ordered[len(ordered)//2]:.2f}  "
              f"range {ordered[0]:.2f} - {ordered[-1]:.2f}")
        print(f"  classified as repeat (<0.40): {repeats:5d}  {_pct(repeats, total)}")
        print(f"  self-reported repetition:     {selfrep:5d}  {_pct(selfrep, total)}")
        print(f"  had prior news coverage:      {news_rows:5d}  {_pct(news_rows, total)}")
        if news_rows == 0:
            print("  ! no news data - set MASSIVE_API_KEY so novelty can use prior")
            print("    coverage rather than filing text and report-lag alone")
        lags = Counter(min(int(r.get("report_lag_days") or 0), 8) for r in rows)
        print("  filing lag (days from the event it reports):")
        for lag in sorted(lags):
            label = f"{lag}+" if lag == 8 else str(lag)
            print(f"    {label:>3s} day(s)  {lags[lag]:5d}  {_pct(lags[lag], total)}")

    print(f"\nTOP TICKERS BY EVENT COUNT")
    for ticker, count in Counter(r["ticker"] for r in rows).most_common(12):
        print(f"  {ticker:8s} {count:4d}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
