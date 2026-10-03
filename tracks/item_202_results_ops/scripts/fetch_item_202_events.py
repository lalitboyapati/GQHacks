"""Fetch and cache Massive Item 2.02 8-K events for this track.

Usage (from repo root):
    uv run --project infrastructure python tracks/item_202_results_ops/scripts/fetch_item_202_events.py --symbols AAPL,MSFT
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

TRACK_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = TRACK_ROOT.parents[1]
INFRA_ROOT = REPO_ROOT / "infrastructure"
sys.path.insert(0, str(INFRA_ROOT))

from webull_bt.logging_utils import get_logger, setup_logging
from webull_bt.massive_filings import load_item_202_events, save_events_cache

logger = get_logger("fetch_item_202")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache Massive Item 2.02 events")
    parser.add_argument(
        "--symbols",
        default=os.environ.get("WEBULL_SYMBOLS", "AAPL"),
        help="Comma-separated tickers",
    )
    parser.add_argument("--gte", default=os.environ.get("MASSIVE_FILING_DATE_GTE", ""), help="filing_date >= YYYY-MM-DD")
    parser.add_argument("--lte", default=os.environ.get("MASSIVE_FILING_DATE_LTE", ""), help="filing_date <= YYYY-MM-DD")
    parser.add_argument(
        "--out",
        default=str(TRACK_ROOT / "data" / "item_202_events.json"),
        help="Output JSON cache path",
    )
    parser.add_argument(
        "--benzinga",
        action="store_true",
        help="Try Benzinga earnings enrichment (requires Massive Benzinga entitlement)",
    )
    args = parser.parse_args()

    load_dotenv(INFRA_ROOT / "backtest" / ".env")
    setup_logging()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    events = load_item_202_events(
        symbols,
        filing_date_gte=args.gte or None,
        filing_date_lte=args.lte or None,
        cache_path=None,
        refresh=True,
        enrich_benzinga=bool(args.benzinga),
        enrich_disclosures=True,
    )
    path = save_events_cache(events, args.out)
    logger.info("Cached %d Item 2.02 event(s) -> %s", len(events), path)
    for event in events:
        logger.info(
            "  %s filing=%s trade=%s primary=%s tertiary=%s polarity=%s",
            event.ticker,
            event.filing_date,
            event.trade_date,
            event.primary_category or "n/a",
            event.tertiary_category or "n/a",
            event.category_polarity,
        )


if __name__ == "__main__":
    main()
