#!/usr/bin/env python
"""Build the 8-K event set and write it to JSON.

Separating event construction from the backtest matters for two reasons:
the filing pull is the slow, network-bound half and should happen once, and
a committed event file makes every later backtest reproducible and lets the
classifications be audited by hand before any money logic touches them.

Examples
--------
    # MongoDB only, exactly the case the research started from
    python scripts/fetch_events.py --symbols MDB --start 2019-01-01

    # Full default universe of smaller issuers
    python scripts/fetch_events.py --universe default --start 2019-01-01

    # Executive changes only, skipping the news lookup
    python scripts/fetch_events.py --items 5.02 --no-news
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_ROOT = REPO_ROOT / "infrastructure"
sys.path.insert(0, str(INFRA_ROOT))
os.environ.setdefault("GQH_TRACK", "disclosure_advantage")

from eightk.config import Settings
from eightk.edgar import EdgarClient
from eightk.events import (
    EXEC_ITEMS,
    PLAN_CANDIDATE_ITEMS,
    build_events,
    save_events,
)
from eightk.http import CachedSession
from eightk.massive_src import MassiveClient
from eightk.universe import load_tickers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--symbols", default=None,
                        help="Comma-separated tickers (overrides --universe)")
    parser.add_argument("--universe", default="default",
                        help="'default', a sector name, or a path to a ticker file")
    parser.add_argument("--start", default="2019-01-01", help="Earliest filing date")
    parser.add_argument("--end", default=None, help="Latest filing date (default: today)")
    parser.add_argument("--items", default=None,
                        help="Comma-separated 8-K item codes (default: exec + plan items)")
    parser.add_argument("--out", default=None, help="Output JSON path")
    parser.add_argument("--no-news", action="store_true",
                        help="Skip the Massive news lookup used for novelty scoring")
    parser.add_argument("--offline", action="store_true",
                        help="Fail instead of fetching anything not already cached")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("fetch_events")

    settings = Settings.from_env()
    settings.ensure_dirs()
    if args.offline:
        settings.offline = True

    tickers = load_tickers(args.symbols or args.universe)
    end = args.end or date.today().isoformat()
    items = (
        {code.strip() for code in args.items.split(",") if code.strip()}
        if args.items else (EXEC_ITEMS | PLAN_CANDIDATE_ITEMS)
    )

    log.info("universe: %d ticker(s); window %s to %s; items %s",
             len(tickers), args.start, end, sorted(items))

    session = CachedSession(
        settings.cache_dir, settings.sec_user_agent,
        requests_per_second=settings.sec_requests_per_second,
        offline=settings.offline,
    )
    edgar = EdgarClient(session)

    massive = None
    if settings.has_massive:
        massive = MassiveClient(settings.massive_api_key, settings.cache_dir,
                                offline=settings.offline)
        log.info("Massive enabled: news, market cap, and option data available")
    else:
        log.warning(
            "MASSIVE_API_KEY not set - novelty scoring falls back to filing text "
            "and EDGAR report-lag only, and market caps will be unknown"
        )

    records = build_events(
        tickers, edgar=edgar, massive=massive,
        date_gte=args.start, date_lte=end,
        items=items, fetch_news=not args.no_news,
    )

    out = Path(args.out) if args.out else settings.events_dir / "events.json"
    save_events(records, out)

    # A short breakdown so the event set can be sanity-checked immediately.
    by_type: dict[str, int] = {}
    for record in records:
        for event_type in record.event_types:
            by_type[event_type] = by_type.get(event_type, 0) + 1
    log.info("event types: %s", by_type or "none")
    log.info("HTTP cache: %s", session.stats)
    if massive:
        log.info("Massive API calls: %d", massive.calls)
    print(f"\nWrote {len(records)} events to {out}")
    for event_type, count in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"  {event_type:20s} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
